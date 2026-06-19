"""LLVM backend.

This backend shares the existing frontend and typed AST, then lowers to LLVM IR.
Unsupported language nodes fail explicitly.
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass, field

from llvmlite import binding, ir

from compiler.ast import (
    ArrayLiteral, Assignment, Update, BinaryOp, Block, BlockExpr, BoolLiteral, Break,
    Defer, ExternBlock, ExpressionStatement, EnumDecl, EnumRef, FieldAccess, FloatLiteral, FunctionCall,
    FunctionExpr, GenericFunctionValue, ErrReturn, FallibleOp,
    ForIn, FunctionDeclaration, Identifier, IfExpr, IfaceDecl, ImportDecl, IndexAccess, IntegerLiteral,
    MatchExpr, MethodCall, NilLiteral, Return, SizeOfType, SliceExpr, SliceLiteral, StringLiteral, InterpolatedString, RuneLiteral, StructDecl,
    StructLiteral, UnaryOp, VariableDeclaration, ForCondition,
)
from compiler.llvm_layout import (
    ENUM_VARIANTS, FLOAT_TYPES, I8PTR, IFACE_METHODS, IFACE_TYPES, INT_TYPES,
    LLVMLayout, MAP_DESC_PTR, MAP_TYPE, RAW_SLICE_TYPE, SIGNED_INT_TYPES,
    STR_TYPE, STRUCT_EMBEDS, STRUCT_FIELDS, STRUCT_FIELD_INDEX, STRUCT_TYPES,
    UNSIGNED_INT_TYPES, llvm_type,
)
from compiler.names import safe_user_ident
from compiler.ncrt import build_ncrt_obj, build_support_c_objs
from compiler.llvm_map import MapEmitter
from compiler.llvm_string import StringEmitter
from compiler.target import TargetSpec, get_target
from compiler.type_ref import parse_array_type, parse_fn_type, parse_map_type, parse_slice_type


@dataclass
class _LLVMInputs:
    structs: list[StructDecl] = field(default_factory=list)
    enums: list[EnumDecl] = field(default_factory=list)
    other_funcs: list[FunctionDeclaration] = field(default_factory=list)
    main_func: FunctionDeclaration | None = None
    top_stmts: list = field(default_factory=list)
    closures: list[FunctionExpr] = field(default_factory=list)


def _collect_llvm_inputs(program) -> _LLVMInputs:
    result = _LLVMInputs()

    def collect_top_level(stmts):
        for stmt in stmts:
            if isinstance(stmt, StructDecl):
                result.structs.append(stmt)
            elif isinstance(stmt, IfaceDecl):
                pass
            elif isinstance(stmt, EnumDecl):
                result.enums.append(stmt)
            elif isinstance(stmt, FunctionDeclaration):
                if getattr(stmt, "is_extern", False):
                    result.other_funcs.append(stmt)
                    continue
                if stmt.name == "main":
                    result.main_func = stmt
                else:
                    result.other_funcs.append(stmt)
                collect_top_level(stmt.body.statements)
            elif isinstance(stmt, ExternBlock):
                result.other_funcs.extend(stmt.functions)
            elif isinstance(stmt, Block):
                collect_top_level(stmt.statements)
            elif isinstance(stmt, ForCondition):
                collect_top_level(stmt.body.statements)
            elif isinstance(stmt, ForIn):
                collect_top_level(stmt.body.statements)
            elif isinstance(stmt, Defer):
                collect_top_level(stmt.body.statements)

    def collect_closure_expr(node):
        if isinstance(node, FunctionExpr):
            if not hasattr(node, "closure_id"):
                node.closure_id = len(result.closures)
                result.closures.append(node)
            collect_top_level(node.body.statements)
            for stmt in node.body.statements:
                collect_closure_stmt(stmt)
        elif isinstance(node, (ArrayLiteral, SliceLiteral)):
            for elem in node.elements:
                collect_closure_expr(elem)
        elif isinstance(node, SliceExpr):
            collect_closure_expr(node.array)
            if node.start:
                collect_closure_expr(node.start)
            if node.end:
                collect_closure_expr(node.end)
        elif isinstance(node, IndexAccess):
            collect_closure_expr(node.obj)
            collect_closure_expr(node.index)
        elif isinstance(node, BinaryOp):
            collect_closure_expr(node.left)
            collect_closure_expr(node.right)
        elif isinstance(node, UnaryOp):
            collect_closure_expr(node.operand)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                collect_closure_expr(arg)
        elif isinstance(node, InterpolatedString):
            for part in node.parts:
                collect_closure_expr(part)
        elif isinstance(node, IfExpr):
            collect_closure_expr(node.condition)
            for stmt in node.then_block.statements:
                collect_closure_stmt(stmt)
            if node.else_block:
                for stmt in node.else_block.statements:
                    collect_closure_stmt(stmt)
        elif isinstance(node, MatchExpr):
            collect_closure_expr(node.scrutinee)
            for pattern, body in node.arms:
                if pattern is not None:
                    collect_closure_expr(pattern)
                collect_closure_expr(body)
        elif isinstance(node, BlockExpr):
            for stmt in node.block.statements:
                collect_closure_stmt(stmt)
        elif isinstance(node, StructLiteral):
            for _name, value in node.fields:
                collect_closure_expr(value)
        elif isinstance(node, FieldAccess):
            collect_closure_expr(node.obj)
        elif isinstance(node, MethodCall):
            collect_closure_expr(node.obj)
            for arg in node.args:
                collect_closure_expr(arg)
        elif isinstance(node, FallibleOp):
            collect_closure_expr(node.expr)

    def collect_closure_stmt(stmt):
        if isinstance(stmt, ExternBlock):
            return
        if isinstance(stmt, VariableDeclaration):
            collect_closure_expr(stmt.initializer)
        elif isinstance(stmt, Assignment):
            collect_closure_expr(stmt.target)
            collect_closure_expr(stmt.expr)
        elif isinstance(stmt, Update):
            collect_closure_expr(stmt.target)
        elif isinstance(stmt, ExpressionStatement):
            collect_closure_expr(stmt.expr)
        elif isinstance(stmt, ForCondition):
            collect_closure_expr(stmt.condition)
            for child in stmt.body.statements:
                collect_closure_stmt(child)
        elif isinstance(stmt, ForIn):
            if stmt.start is not None:
                collect_closure_expr(stmt.start)
                collect_closure_expr(stmt.end)
            else:
                collect_closure_expr(stmt.iterable)
            for child in stmt.body.statements:
                collect_closure_stmt(child)
        elif isinstance(stmt, FunctionDeclaration):
            for child in stmt.body.statements:
                collect_closure_stmt(child)
        elif isinstance(stmt, Return) and stmt.expr:
            collect_closure_expr(stmt.expr)
        elif isinstance(stmt, ErrReturn):
            collect_closure_expr(stmt.expr)
        elif isinstance(stmt, Defer):
            for child in stmt.body.statements:
                collect_closure_stmt(child)
        elif isinstance(stmt, Block):
            for child in stmt.statements:
                collect_closure_stmt(child)

    collect_top_level(program.statements)
    for stmt in program.statements:
        collect_closure_stmt(stmt)
    result.top_stmts = [
        stmt for stmt in program.statements
        if not isinstance(stmt, (FunctionDeclaration, StructDecl, IfaceDecl, EnumDecl, ImportDecl, ExternBlock))
    ]
    return result


class LLVMCodegen:
    def __init__(self, target: TargetSpec | None = None):
        self.target = target or get_target()
        self.layout = LLVMLayout()
        self.module = ir.Module(name="nc")
        self.module.triple = self.target.triple
        self.builder = None
        self.func = None
        self.vars: dict[str, tuple[ir.AllocaInstr, str]] = {}
        self.printf = None
        self.fprintf = None
        self.exit_fn = None
        self.nc_stderr = None
        self.malloc = None
        self.gc_alloc = None
        self.gc_collect = None
        self.gc_live = None
        self.gc_init = None
        self.gc_root_mark = None
        self.gc_root_rewind = None
        self.gc_push_root_slot = None
        self.str_cat_fn = None
        self.str_slice_fn = None
        self.i32_to_str_fn = None
        self.i64_to_str_fn = None
        self.u64_to_str_fn = None
        self.f64_to_str_fn = None
        self.rune_to_str_fn = None
        self.str_to_i32_fn = None
        self.cstr_to_str_fn = None
        self.empty_c_string = None
        self.os_set_args_fn = None
        self.map_init_fn = None
        self.map_get_fn = None
        self.map_set_fn = None
        self.map_has_fn = None
        self.map_delete_fn = None
        self.map_clear_fn = None
        self.slice_copy_fn = None
        self.slice_append_fn = None
        self.slice_copy_into_fn = None
        self.slice_clear_fn = None
        self.gc_live_count = None
        self.memcmp = None
        self.sprintf = None
        self.atoi = None
        self.strings: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.map_descs: dict[str, ir.GlobalVariable] = {}
        self.map_hash_fns: dict[str, ir.Function] = {}
        self.map_eq_fns: dict[str, ir.Function] = {}
        self.fn_decls: dict[str, FunctionDeclaration] = {}
        self.closure_env_types: dict[int, ir.LiteralStructType] = {}
        self.break_stack = []
        self.current_return_type = "void"
        self.current_is_main = False
        self.current_is_fallible = False
        self.current_error_slot = None
        self.defer_sites = []
        self.defer_stack_slot = None
        self.defer_top_slot = None
        self.emitting_defer = False
        self.current_gc_mark = None
        self.current_return_slot = None
        self.iface_vtables: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.iface_thunks: dict[tuple[str, str, str], ir.Function] = {}
        self.function_value_thunks: dict[str, ir.Function] = {}
        self.string_emitter = StringEmitter(self)
        self.map_emitter = MapEmitter(self, STRUCT_FIELDS, ENUM_VARIANTS, llvm_type)

    def generate(self, program) -> str:
        collected = _collect_llvm_inputs(program)
        if collected.top_stmts:
            raise NotImplementedError("LLVM backend does not support top-level statements")
        self.register_enums(collected.enums)
        self.register_structs(collected.structs)
        self.register_ifaces(program)
        self.register_closure_envs(collected.closures)

        funcs = collected.other_funcs + ([collected.main_func] if collected.main_func else [])
        for fn in funcs:
            self.declare_function(fn)
        for closure in collected.closures:
            self.declare_closure_function(closure)
        for closure in collected.closures:
            self.emit_closure_function(closure)
        for fn in funcs:
            if not getattr(fn, "is_extern", False):
                self.emit_function(fn)
        return str(self.module)

    def register_enums(self, enums: list[EnumDecl]):
        ENUM_VARIANTS.clear()
        for enum in enums:
            ENUM_VARIANTS[enum.name] = {
                variant: i for i, variant in enumerate(enum.variants)
            }

    def register_structs(self, structs: list[StructDecl]):
        STRUCT_TYPES.clear()
        STRUCT_FIELDS.clear()
        STRUCT_FIELD_INDEX.clear()
        STRUCT_EMBEDS.clear()
        for struct in structs:
            STRUCT_FIELDS[struct.name] = list(struct.fields)
            STRUCT_EMBEDS[struct.name] = {
                field_name: field_type
                for field_name, field_type in struct.fields
                if field_name in getattr(struct, "embedded_fields", set())
            }
            STRUCT_FIELD_INDEX[struct.name] = {
                field_name: i for i, (field_name, _field_type) in enumerate(struct.fields)
            }
        for struct in structs:
            STRUCT_TYPES[struct.name] = ir.LiteralStructType([
                llvm_type(field_type) for _field_name, field_type in struct.fields
            ])

    def register_ifaces(self, program):
        IFACE_METHODS.clear()
        IFACE_TYPES.clear()
        raw = {}
        for stmt in program.statements:
            if isinstance(stmt, IfaceDecl):
                raw[stmt.name] = stmt

        def resolve(name, stack=None):
            stack = stack or []
            if name in IFACE_METHODS:
                return IFACE_METHODS[name]
            if name in stack:
                raise RuntimeError(f"iface {name}: embedded iface cycle")
            stmt = raw[name]
            methods = {}
            order = []
            def add(mname, params, ret):
                sig = ([ptype for _pname, ptype in params], ret or "void")
                if mname not in methods:
                    order.append(mname)
                methods[mname] = sig
            for embed in stmt.embeds:
                for mname, param_types, ret in resolve(embed, stack + [name]):
                    add(mname, [(f"arg{i}", t) for i, t in enumerate(param_types)], ret)
            for mname, params, ret in stmt.methods:
                add(mname, params, ret)
            IFACE_METHODS[name] = [(mname, methods[mname][0], methods[mname][1]) for mname in order]
            IFACE_TYPES[name] = ir.LiteralStructType([I8PTR, I8PTR])
            return IFACE_METHODS[name]

        for name in list(raw):
            resolve(name)

    def register_closure_envs(self, closures: list[FunctionExpr]):
        self.closure_env_types.clear()
        for closure in closures:
            fields = [llvm_type(capture_type) for _name, capture_type in getattr(closure, "captures", [])]
            if not fields:
                fields = [ir.IntType(8)]
            self.closure_env_types[closure.closure_id] = ir.LiteralStructType(fields)

    def declare_function(self, fn: FunctionDeclaration):
        name = self.function_symbol(fn)
        is_fallible = bool(getattr(fn, "fallible", False)) and not getattr(fn, "is_extern", False) and fn.name != "main"
        ret = ir.IntType(1) if is_fallible else (
            ir.IntType(32) if fn.name == "main" and (fn.return_type or "void") == "void" else llvm_type(fn.return_type)
        )
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        args = [ir.IntType(32), I8PTR.as_pointer()] if fn.name == "main" else []
        if is_fallible:
            if (fn.return_type or "void") != "void":
                args.append(llvm_type(fn.return_type).as_pointer())
            args.append(STR_TYPE.as_pointer())
        args.extend([llvm_type(t) for _n, t in all_params])
        fn_type = ir.FunctionType(ret, args)
        existing = self.module.globals.get(name)
        if existing is not None:
            if getattr(existing, "function_type", None) != fn_type:
                raise RuntimeError(f"extern symbol '{name}' declared with incompatible ABI")
        else:
            self.module.globals[name] = ir.Function(self.module, fn_type, name=name)
        self.fn_decls[name] = fn
        if not fn.receiver_name:
            self.fn_decls[fn.name] = fn

    def function_symbol(self, fn: FunctionDeclaration):
        if getattr(fn, "is_extern", False):
            return getattr(fn, "extern_symbol", None) or fn.name
        if fn.receiver_name:
            receiver_type = fn.receiver_type.lstrip("*").lstrip("?")
            return safe_user_ident(f"{receiver_type}_{fn.name}")
        return safe_user_ident(fn.name)

    def closure_symbol(self, closure: FunctionExpr):
        return f"__nc_lambda_{closure.closure_id}"

    def declare_closure_function(self, closure: FunctionExpr):
        ret = llvm_type(closure.return_type or "void")
        args = [I8PTR] + [llvm_type(t) for _n, t in closure.params]
        ir.Function(self.module, ir.FunctionType(ret, args), name=self.closure_symbol(closure))

    def emit_closure_function(self, closure: FunctionExpr):
        llvm_fn = self.module.globals[self.closure_symbol(closure)]
        block = llvm_fn.append_basic_block("entry")
        saved_builder, saved_func, saved_vars = self.builder, self.func, self.vars
        saved_defer = (self.defer_sites, self.defer_stack_slot, self.defer_top_slot, self.emitting_defer)
        saved_gc = (self.current_gc_mark, self.current_return_slot)
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        self.init_defer_state()
        self.init_gc_frame(is_main=False)
        llvm_fn.args[0].name = "__nc_env"
        env_type = self.closure_env_types[closure.closure_id]
        env_ptr = self.builder.bitcast(llvm_fn.args[0], env_type.as_pointer(), name="closure.env.ptr")
        env_slot = self.alloca_at_entry("__nc_env_slot", I8PTR)
        self.builder.store(llvm_fn.args[0], env_slot)
        self.root_slots_for_type(env_slot, f"*__nc_env_{closure.closure_id}")
        for i, (capture_name, capture_type) in enumerate(getattr(closure, "captures", [])):
            field_ptr = self.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{safe_user_ident(capture_name)}.ptr",
            )
            self.vars[capture_name] = (field_ptr, capture_type)
        for arg, (param_name, param_type) in zip(llvm_fn.args[1:], closure.params):
            arg.name = safe_user_ident(param_name)
            slot = self.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)
            self.root_slots_for_type(slot, param_type)
        if (closure.return_type or "void") != "void":
            self.current_return_slot = self.alloca_at_entry("__nc_ret", llvm_type(closure.return_type))
            self.root_slots_for_type(self.current_return_slot, closure.return_type)
        self.emit_callable_body(closure.body, closure.return_type or "void", f"lambda {closure.closure_id}")
        self.builder, self.func, self.vars = saved_builder, saved_func, saved_vars
        self.defer_sites, self.defer_stack_slot, self.defer_top_slot, self.emitting_defer = saved_defer
        self.current_gc_mark, self.current_return_slot = saved_gc

    def emit_function(self, fn: FunctionDeclaration):
        llvm_fn = self.module.globals[self.function_symbol(fn)]
        block = llvm_fn.append_basic_block("entry")
        saved_defer = (self.defer_sites, self.defer_stack_slot, self.defer_top_slot, self.emitting_defer)
        saved_gc = (self.current_gc_mark, self.current_return_slot, self.current_error_slot, self.current_is_fallible)
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        self.init_defer_state()
        self.init_gc_frame(is_main=fn.name == "main")
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        llvm_args = list(llvm_fn.args)
        self.current_is_fallible = bool(getattr(fn, "fallible", False)) and fn.name != "main"
        if fn.name == "main":
            llvm_args[0].name = "__nc_argc"
            llvm_args[1].name = "__nc_argv"
            self.init_os_args(llvm_args[0], llvm_args[1])
            llvm_args = llvm_args[2:]
        elif self.current_is_fallible:
            if (fn.return_type or "void") != "void":
                self.current_return_slot = llvm_args[0]
                self.root_slots_for_type(self.current_return_slot, fn.return_type)
                llvm_args = llvm_args[1:]
            self.current_error_slot = llvm_args[0]
            self.root_slots_for_type(self.current_error_slot, "error")
            llvm_args = llvm_args[1:]
        for arg, (param_name, param_type) in zip(llvm_args, all_params):
            arg.name = safe_user_ident(param_name)
            slot = self.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)
            self.root_slots_for_type(slot, param_type)
        if (fn.return_type or "void") != "void" and self.current_return_slot is None:
            self.current_return_slot = self.alloca_at_entry("__nc_ret", llvm_type(fn.return_type))
            self.root_slots_for_type(self.current_return_slot, fn.return_type)

        self.emit_function_body(fn)
        self.defer_sites, self.defer_stack_slot, self.defer_top_slot, self.emitting_defer = saved_defer
        self.current_gc_mark, self.current_return_slot, self.current_error_slot, self.current_is_fallible = saved_gc

    def emit_function_body(self, fn: FunctionDeclaration):
        self.emit_callable_body(fn.body, fn.return_type or "void", f"function {fn.name}", is_main=fn.name == "main")

    def emit_callable_body(self, body: Block, return_type: str, name: str, is_main: bool = False):
        prev_return_type, prev_is_main = self.current_return_type, self.current_is_main
        self.current_return_type = return_type
        self.current_is_main = is_main
        stmts = body.statements
        if return_type != "void" and stmts and isinstance(stmts[-1], ExpressionStatement):
            for stmt in stmts[:-1]:
                self.emit_stmt(stmt)
            if not self.builder.block.is_terminated:
                value = self.emit_coerced_expr(stmts[-1].expr, return_type)
                if self.current_return_slot is not None:
                    self.builder.store(value, self.current_return_slot)
                self.emit_success_return()
            self.current_return_type, self.current_is_main = prev_return_type, prev_is_main
            return
        self.emit_block(body)
        if not self.builder.block.is_terminated:
            self.emit_deferred()
            if is_main and return_type == "void":
                self.emit_gc_rewind()
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
            elif return_type == "void":
                self.emit_success_return()
            else:
                raise RuntimeError(f"missing ret in {name}")
        self.current_return_type, self.current_is_main = prev_return_type, prev_is_main

    def emit_success_return(self):
        self.emit_deferred()
        if self.current_is_fallible:
            self.emit_gc_rewind()
            self.builder.ret(ir.Constant(ir.IntType(1), 0))
            return
        if self.current_is_main and self.current_return_type == "void":
            self.emit_gc_rewind()
            self.builder.ret(ir.Constant(ir.IntType(32), 0))
            return
        if self.current_return_type == "void":
            self.emit_gc_rewind()
            self.builder.ret_void()
            return
        value = self.builder.load(self.current_return_slot, name="ret.value")
        self.emit_gc_rewind()
        self.builder.ret(value)

    def emit_error_return_value(self, value):
        if self.current_error_slot is not None:
            self.builder.store(self.cast_to(value, "error"), self.current_error_slot)
        self.emit_deferred()
        if self.current_is_main:
            self.emit_print_error(value)
            self.emit_gc_rewind()
            self.builder.ret(ir.Constant(self.func.function_type.return_type, 1))
            return
        if not self.current_is_fallible:
            self.emit_print_error(value)
            self.emit_exit(1)
            self.builder.unreachable()
            return
        self.emit_gc_rewind()
        self.builder.ret(ir.Constant(ir.IntType(1), 1))

    def alloca_at_entry(self, name, typ):
        return self.builder.alloca(typ, name=name)

    def root_pointer_slot(self, ptr):
        self.ensure_ncrt_runtime()
        self.builder.call(self.gc_push_root_slot, [self.builder.bitcast(ptr, I8PTR)])

    def root_slots_for_type(self, ptr, nc_type):
        if nc_type in ("str", "error"):
            field = self.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
                inbounds=True,
                name="gc.root.str.ptr",
            )
            self.root_pointer_slot(field)
            return
        if nc_type == "nc_map" or parse_map_type(nc_type) is not None:
            field = self.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 1)],
                inbounds=True,
                name="gc.root.map.entries",
            )
            self.root_pointer_slot(field)
            return
        if parse_slice_type(nc_type) is not None:
            field = self.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
                inbounds=True,
                name="gc.root.slice.ptr",
            )
            self.root_pointer_slot(field)
            return
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            self.root_pointer_slot(ptr)
            return
        if parse_fn_type(nc_type) is not None:
            field = self.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 1)],
                inbounds=True,
                name="gc.root.fn.env",
            )
            self.root_pointer_slot(field)
            return
        if nc_type in IFACE_METHODS:
            field = self.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 1)],
                inbounds=True,
                name="gc.root.iface.data",
            )
            self.root_pointer_slot(field)
            return
        if isinstance(nc_type, str) and nc_type in STRUCT_FIELDS:
            for i, (_field_name, field_type) in enumerate(STRUCT_FIELDS[nc_type]):
                field = self.builder.gep(
                    ptr,
                    [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                    inbounds=True,
                    name="gc.root.struct.field",
                )
                self.root_slots_for_type(field, field_type)
            return
        array_info = parse_array_type(nc_type)
        if array_info is not None:
            length, elem_type = array_info
            for i in range(length):
                elem = self.builder.gep(
                    ptr,
                    [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                    inbounds=True,
                    name="gc.root.array.elem",
                )
                self.root_slots_for_type(elem, elem_type)

    def init_defer_state(self):
        self.defer_sites = []
        self.defer_stack_slot = self.builder.alloca(ir.ArrayType(ir.IntType(32), 1024), name="__nc_defer_stack")
        self.defer_top_slot = self.builder.alloca(ir.IntType(32), name="__nc_defer_top")
        self.builder.store(ir.Constant(ir.IntType(32), 0), self.defer_top_slot)
        self.emitting_defer = False

    def init_gc_frame(self, is_main: bool):
        self.ensure_ncrt_runtime()
        if is_main:
            self.builder.call(self.gc_init, [])
        self.current_gc_mark = self.builder.call(self.gc_root_mark, [], name="__nc_gc_mark")
        self.current_return_slot = None

    def init_os_args(self, argc, argv):
        self.ensure_ncrt_runtime()
        self.builder.call(self.os_set_args_fn, [argc, argv])

    def emit_gc_rewind(self):
        if self.current_gc_mark is not None:
            self.ensure_ncrt_runtime()
            self.builder.call(self.gc_root_rewind, [self.current_gc_mark])

    def emit_block(self, block: Block):
        for stmt in block.statements:
            if self.builder.block.is_terminated:
                break
            self.emit_stmt(stmt)

    def emit_stmt(self, stmt):
        if isinstance(stmt, (StructDecl, EnumDecl)):
            return
        if isinstance(stmt, VariableDeclaration):
            typ = llvm_type(stmt.type)
            slot = self.alloca_at_entry(safe_user_ident(stmt.name), typ)
            self.vars[stmt.name] = (slot, stmt.type)
            self.root_slots_for_type(slot, stmt.type)
            self.builder.store(self.emit_coerced_expr(stmt.initializer, stmt.type), slot)
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, IndexAccess) and parse_map_type(stmt.target.obj.type) is not None:
                self.emit_map_set(stmt.target.obj, stmt.target.index, stmt.expr, stmt.op)
                return
            ptr, target_type = self.emit_lvalue(stmt.target)
            if stmt.op != "=" and getattr(stmt, "overload_method", None):
                old = self.builder.load(ptr, name="assign.old")
                rhs = self.emit_operator_method_value(old, target_type, stmt.overload_method, stmt.expr,
                                                      getattr(stmt, "overload_receiver_base", target_type))
            else:
                rhs = self.emit_coerced_expr(stmt.expr, target_type)
            if stmt.op != "=" and not getattr(stmt, "overload_method", None):
                old = self.builder.load(ptr, name="assign.old")
                rhs = self.emit_binary_values(old, stmt.op[:-1], rhs, target_type)
            self.builder.store(rhs, ptr)
            return
        if isinstance(stmt, Update):
            ptr, target_type = self.emit_lvalue(stmt.target)
            old = self.builder.load(ptr, name="update.old")
            one = ir.Constant(llvm_type(target_type), 1.0 if target_type in FLOAT_TYPES else 1)
            op = "+" if stmt.op == "++" else "-"
            self.builder.store(self.emit_binary_values(old, op, one, target_type), ptr)
            return
        if isinstance(stmt, ExpressionStatement):
            self.emit_expr(stmt.expr)
            return
        if isinstance(stmt, ForCondition):
            self.emit_for_condition(stmt)
            return
        if isinstance(stmt, ForIn):
            self.emit_for_in(stmt)
            return
        if isinstance(stmt, Return):
            if stmt.expr is None:
                self.emit_success_return()
            else:
                value = self.emit_coerced_expr(stmt.expr, self.current_return_type)
                if self.current_return_slot is not None:
                    self.builder.store(value, self.current_return_slot)
                self.emit_success_return()
            return
        if isinstance(stmt, ErrReturn):
            self.emit_error_return_value(self.emit_coerced_expr(stmt.expr, "error"))
            return
        if isinstance(stmt, Defer):
            self.emit_defer(stmt)
            return
        if isinstance(stmt, Break):
            if not self.break_stack:
                raise RuntimeError("break outside loop")
            self.builder.branch(self.break_stack[-1])
            return
        raise NotImplementedError(f"LLVM backend does not support statement: {type(stmt).__name__}")

    def emit_defer(self, stmt: Defer):
        if self.emitting_defer:
            self.emit_block(stmt.body)
            return
        site_id = len(self.defer_sites)
        self.defer_sites.append(stmt)
        top = self.builder.load(self.defer_top_slot, name="defer.top")
        elem_ptr = self.builder.gep(
            self.defer_stack_slot,
            [ir.Constant(ir.IntType(32), 0), top],
            inbounds=True,
            name="defer.slot",
        )
        self.builder.store(ir.Constant(ir.IntType(32), site_id), elem_ptr)
        self.builder.store(self.builder.add(top, ir.Constant(ir.IntType(32), 1)), self.defer_top_slot)

    def emit_deferred(self):
        if self.emitting_defer or self.defer_top_slot is None:
            return
        cond_bb = self.func.append_basic_block("defer.cond")
        body_bb = self.func.append_basic_block("defer.body")
        end_bb = self.func.append_basic_block("defer.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        top = self.builder.load(self.defer_top_slot, name="defer.top")
        has_defer = self.builder.icmp_signed(">", top, ir.Constant(ir.IntType(32), 0))
        self.builder.cbranch(has_defer, body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        next_top = self.builder.sub(top, ir.Constant(ir.IntType(32), 1), name="defer.next.top")
        self.builder.store(next_top, self.defer_top_slot)
        elem_ptr = self.builder.gep(
            self.defer_stack_slot,
            [ir.Constant(ir.IntType(32), 0), next_top],
            inbounds=True,
            name="defer.site.ptr",
        )
        site = self.builder.load(elem_ptr, name="defer.site")
        after_site_bb = self.func.append_basic_block("defer.after.site")
        self.emitting_defer = True
        for site_id, stmt in enumerate(self.defer_sites):
            site_bb = self.func.append_basic_block(f"defer.site.{site_id}")
            next_site_bb = self.func.append_basic_block(f"defer.next.{site_id}")
            self.builder.cbranch(
                self.builder.icmp_signed("==", site, ir.Constant(ir.IntType(32), site_id)),
                site_bb,
                next_site_bb,
            )
            self.builder.position_at_end(site_bb)
            self.emit_block(stmt.body)
            if not self.builder.block.is_terminated:
                self.builder.branch(after_site_bb)
            self.builder.position_at_end(next_site_bb)
        if not self.builder.block.is_terminated:
            self.builder.branch(after_site_bb)
        self.emitting_defer = False
        self.builder.position_at_end(after_site_bb)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def emit_print_error(self, value):
        self.ensure_fprintf()
        stderr = self.builder.call(self.nc_stderr, [], name="stderr")
        fmt = self.global_c_string("error: %.*s\n", "fmt_error")
        ptr = self.builder.extract_value(value, 0)
        length64 = self.builder.extract_value(value, 1)
        length32 = self.builder.trunc(length64, ir.IntType(32))
        self.builder.call(self.fprintf, [stderr, fmt, length32, ptr])

    def ensure_exit(self):
        if self.exit_fn is None:
            existing = self.module.globals.get("exit")
            self.exit_fn = existing if existing is not None else ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [ir.IntType(32)]),
                name="exit",
            )

    def emit_exit(self, code: int):
        self.ensure_exit()
        self.builder.call(self.exit_fn, [ir.Constant(ir.IntType(32), code)])

    def emit_for_condition(self, stmt: ForCondition):
        cond_bb = self.func.append_basic_block("for.cond")
        body_bb = self.func.append_basic_block("for.body")
        end_bb = self.func.append_basic_block("for.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        self.builder.cbranch(self.bool_value(self.emit_expr(stmt.condition)), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def emit_for_in(self, stmt: ForIn):
        if stmt.start is None:
            if parse_map_type(stmt.iterable.type) is not None:
                self.emit_map_for_in(stmt)
            else:
                self.emit_slice_for_in(stmt)
            return

        idx_type = ir.IntType(32)
        idx_slot = self.alloca_at_entry(safe_user_ident(stmt.index), idx_type)
        self.vars[stmt.index] = (idx_slot, "i32")
        start = self.cast_to(self.emit_expr(stmt.start), "i32")
        end = self.cast_to(self.emit_expr(stmt.end), "i32")
        self.builder.store(start, idx_slot)

        cond_bb = self.func.append_basic_block("for.range.cond")
        body_bb = self.func.append_basic_block("for.range.body")
        end_bb = self.func.append_basic_block("for.range.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        current = self.builder.load(idx_slot, name=safe_user_ident(stmt.index))
        self.builder.cbranch(self.builder.icmp_signed("<", current, end), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            current = self.builder.load(idx_slot, name=safe_user_ident(stmt.index))
            next_value = self.builder.add(current, ir.Constant(idx_type, 1))
            self.builder.store(next_value, idx_slot)
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def emit_slice_for_in(self, stmt: ForIn):
        elem_type = parse_slice_type(stmt.iterable.type)
        if elem_type is None or stmt.value is None:
            raise NotImplementedError("LLVM backend only supports for i, item in slice")

        saved_vars = self.vars.copy()
        idx_type = ir.IntType(32)
        idx_slot = self.alloca_at_entry(safe_user_ident(stmt.index), idx_type)
        value_slot = self.alloca_at_entry(safe_user_ident(stmt.value), llvm_type(elem_type))
        self.vars[stmt.index] = (idx_slot, "i32")
        self.vars[stmt.value] = (value_slot, elem_type)
        self.root_slots_for_type(value_slot, elem_type)

        slice_value = self.emit_expr(stmt.iterable)
        ptr = self.builder.extract_value(slice_value, 0)
        length64 = self.builder.extract_value(slice_value, 1)
        length32 = self.builder.trunc(length64, idx_type)
        self.builder.store(ir.Constant(idx_type, 0), idx_slot)

        cond_bb = self.func.append_basic_block("for.slice.cond")
        body_bb = self.func.append_basic_block("for.slice.body")
        end_bb = self.func.append_basic_block("for.slice.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        current = self.builder.load(idx_slot, name=safe_user_ident(stmt.index))
        self.builder.cbranch(self.builder.icmp_signed("<", current, length32), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        elem_ptr = self.builder.gep(ptr, [current], inbounds=True, name="for.slice.elem.ptr")
        self.builder.store(self.builder.load(elem_ptr), value_slot)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            current = self.builder.load(idx_slot, name=safe_user_ident(stmt.index))
            next_value = self.builder.add(current, ir.Constant(idx_type, 1))
            self.builder.store(next_value, idx_slot)
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        self.vars = saved_vars

    def emit_map_for_in(self, stmt: ForIn):
        map_parts = parse_map_type(stmt.iterable.type)
        if map_parts is None or stmt.value is None:
            raise NotImplementedError("LLVM backend only supports for key, value in map")
        key_type, value_type = map_parts

        saved_vars = self.vars.copy()
        key_slot = self.alloca_at_entry(safe_user_ident(stmt.index), llvm_type(key_type))
        value_slot = self.alloca_at_entry(safe_user_ident(stmt.value), llvm_type(value_type))
        cursor_slot = self.alloca_at_entry("__nc_map_cursor", ir.IntType(64))
        found_slot = self.alloca_at_entry("__nc_map_found", ir.IntType(64))
        map_slot = self.alloca_at_entry("__nc_map_iter", MAP_TYPE)
        self.vars[stmt.index] = (key_slot, key_type)
        self.vars[stmt.value] = (value_slot, value_type)
        self.root_slots_for_type(key_slot, key_type)
        self.root_slots_for_type(value_slot, value_type)

        map_value = self.emit_expr(stmt.iterable)
        self.builder.store(map_value, map_slot)
        self.builder.store(ir.Constant(ir.IntType(64), 0), cursor_slot)

        cond_bb = self.func.append_basic_block("for.map.cond")
        body_bb = self.func.append_basic_block("for.map.body")
        end_bb = self.func.append_basic_block("for.map.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        cursor = self.builder.load(cursor_slot, name="for.map.cursor")
        key_ptr = self.builder.bitcast(key_slot, I8PTR)
        value_ptr = self.builder.bitcast(value_slot, I8PTR)
        found = self.builder.call(self.map_next_fn, [map_slot, cursor, key_ptr, value_ptr], name="for.map.next")
        self.builder.store(found, found_slot)
        self.builder.cbranch(
            self.builder.icmp_signed(">=", found, ir.Constant(ir.IntType(64), 0)),
            body_bb,
            end_bb,
        )
        self.builder.position_at_end(body_bb)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            found = self.builder.load(found_slot, name="for.map.found")
            next_cursor = self.builder.add(found, ir.Constant(ir.IntType(64), 1))
            self.builder.store(next_cursor, cursor_slot)
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        self.vars = saved_vars

    def emit_expr(self, node):
        if isinstance(node, IntegerLiteral):
            return ir.Constant(llvm_type(node.type), node.value)
        if isinstance(node, RuneLiteral):
            return ir.Constant(ir.IntType(32), node.value)
        if isinstance(node, FloatLiteral):
            return ir.Constant(llvm_type(node.type), float(node.value))
        if isinstance(node, BoolLiteral):
            return ir.Constant(ir.IntType(1), 1 if node.value else 0)
        if isinstance(node, NilLiteral):
            return ir.Constant(I8PTR, None)
        if isinstance(node, StringLiteral):
            ptr = self.global_c_string(node.value, "str_lit")
            return ir.Constant.literal_struct([
                ptr,
                ir.Constant(ir.IntType(64), len(node.value.encode("utf-8"))),
            ])
        if isinstance(node, InterpolatedString):
            return self.emit_interpolated_string(node)
        if isinstance(node, EnumRef):
            return ir.Constant(ir.IntType(32), ENUM_VARIANTS[node.enum_name][node.variant])
        if isinstance(node, Identifier):
            slot, _typ = self.vars[node.name]
            return self.builder.load(slot, name=safe_user_ident(node.name))
        if isinstance(node, StructLiteral):
            return self.emit_struct_literal(node)
        if isinstance(node, FieldAccess):
            ptr, _field_type = self.emit_lvalue(node)
            return self.builder.load(ptr, name="field")
        if isinstance(node, ArrayLiteral):
            value = ir.Constant(llvm_type(node.type), ir.Undefined)
            for i, elem in enumerate(node.elements):
                elem_value = self.emit_coerced_expr(elem, node.elem_type)
                value = self.builder.insert_value(value, elem_value, [i], name="arr.ins")
            return value
        if isinstance(node, SliceLiteral):
            return self.emit_slice_literal(node)
        if isinstance(node, SliceExpr):
            return self.emit_slice_expr(node)
        if isinstance(node, IndexAccess):
            if parse_map_type(node.obj.type) is not None:
                return self.emit_map_get(node.obj, node.index)
            if node.obj.type == "str":
                string_value = self.emit_expr(node.obj)
                ptr = self.builder.extract_value(string_value, 0)
                idx = self.cast_to(self.emit_expr(node.index), "i32")
                elem_ptr = self.builder.gep(ptr, [idx], inbounds=True, name="str.idx.ptr")
                byte_value = self.builder.load(elem_ptr, name="str.byte")
                return self.builder.zext(byte_value, ir.IntType(32), name="str.byte.i32")
            ptr, elem_type = self.emit_lvalue(node)
            return self.builder.load(ptr, name="idx")
        if isinstance(node, UnaryOp):
            val = self.emit_expr(node.operand)
            if node.op == "!":
                return self.builder.not_(self.bool_value(val))
            if node.op == "-":
                if node.operand.type in FLOAT_TYPES:
                    return self.builder.fneg(val)
                return self.builder.neg(val)
            if node.op == "~":
                return self.builder.xor(val, ir.Constant(llvm_type(node.operand.type), -1))
            raise NotImplementedError(f"LLVM backend does not support unary operator {node.op}")
        if isinstance(node, BinaryOp):
            return self.emit_binary(node)
        if isinstance(node, IfExpr):
            return self.emit_if_expr(node)
        if isinstance(node, MatchExpr):
            return self.emit_match_expr(node)
        if isinstance(node, BlockExpr):
            return self.emit_block_expr(node)
        if isinstance(node, FunctionCall):
            return self.emit_call(node)
        if isinstance(node, FallibleOp):
            return self.emit_fallible_op(node)
        if isinstance(node, SizeOfType):
            return ir.Constant(ir.IntType(64), self.sizeof_type(node.type_name))
        if isinstance(node, MethodCall):
            return self.emit_method_call(node)
        if isinstance(node, FunctionExpr):
            return self.emit_function_expr(node)
        if isinstance(node, GenericFunctionValue):
            return self.emit_generic_function_value(node)
        raise NotImplementedError(f"LLVM backend does not support expression: {type(node).__name__}")

    def emit_block_expr(self, node: BlockExpr):
        saved_vars = self.vars.copy()
        try:
            return self.emit_block_value(node.block)
        finally:
            self.vars = saved_vars

    def emit_struct_literal(self, node: StructLiteral):
        fields = STRUCT_FIELDS[node.name]
        given = {name: value for name, value in node.fields}
        struct_type = llvm_type(node.name)
        value = ir.Constant(struct_type, ir.Undefined)
        for i, (field_name, field_type) in enumerate(fields):
            field_value = self.emit_coerced_expr(given[field_name], field_type)
            value = self.builder.insert_value(value, field_value, [i], name="struct.ins")
        if node.heap:
            ptr = self.malloc_struct(node.name)
            self.builder.store(value, ptr)
            return ptr
        return value

    def emit_interpolated_string(self, node: InterpolatedString):
        if not node.parts:
            return self.emit_expr(StringLiteral(""))
        current = None
        for part in node.parts:
            if getattr(part, "type", None) == "str":
                value = self.emit_expr(part)
            else:
                value = self.emit_to_str(part)
            current = value if current is None else self.emit_str_cat(current, value)
        return current

    def malloc_struct(self, struct_name: str):
        self.ensure_gc_runtime()
        size = ir.Constant(ir.IntType(64), self.sizeof_type(struct_name))
        raw = self.builder.call(self.gc_alloc, [size], name="struct.gc.raw")
        return self.builder.bitcast(raw, llvm_type(struct_name).as_pointer(), name="struct.ptr")

    def emit_slice_literal(self, node: SliceLiteral):
        elem_type = node.elem_type
        count = len(node.elements)
        ptr = self.malloc_array(elem_type, ir.Constant(ir.IntType(64), count))
        for i, elem in enumerate(node.elements):
            elem_ptr = self.builder.gep(ptr, [ir.Constant(ir.IntType(32), i)], inbounds=True, name="slice.elem.ptr")
            self.builder.store(self.cast_to(self.emit_expr(elem), elem_type), elem_ptr)
        return self.slice_value(elem_type, ptr, count, count)

    def emit_slice_expr(self, node: SliceExpr):
        source_type = node.array.type
        if source_type == "str":
            return self.emit_str_slice(node)
        array_info = parse_array_type(source_type)
        slice_elem_type = parse_slice_type(source_type)
        if array_info is None and slice_elem_type is None:
            raise NotImplementedError(f"LLVM backend cannot slice {source_type}")
        if array_info is not None:
            _array_len, elem_type = array_info
            default_end = ir.Constant(ir.IntType(32), _array_len)
            source_ptr, _source_type = self.emit_lvalue(node.array)
            source_indices = lambda i: [ir.Constant(ir.IntType(32), 0), i]
        else:
            elem_type = slice_elem_type
            source_value = self.emit_expr(node.array)
            source_ptr = self.builder.extract_value(source_value, 0)
            source_len = self.builder.extract_value(source_value, 1)
            default_end = self.builder.trunc(source_len, ir.IntType(32))
            source_indices = lambda i: [i]
        start = self.cast_to(self.emit_expr(node.start), "i32") if node.start else ir.Constant(ir.IntType(32), 0)
        end = self.cast_to(self.emit_expr(node.end), "i32") if node.end else default_end
        count32 = self.builder.sub(end, start, name="slice.count32")
        count64 = self.builder.sext(count32, ir.IntType(64), name="slice.count64")
        source_i = self.builder.add(start, ir.Constant(ir.IntType(32), 0), name="slice.source.start")
        source_elem_ptr = self.builder.gep(source_ptr, source_indices(source_i))
        return self.emit_slice_copy_raw(elem_type, source_elem_ptr, count64)

    def emit_str_slice(self, node: SliceExpr):
        self.ensure_ncrt_runtime()
        source = self.emit_expr(node.array)
        source_len = self.builder.extract_value(source, 1)
        start = self.cast_to(self.emit_expr(node.start), "i32") if node.start else ir.Constant(ir.IntType(32), 0)
        end = self.cast_to(self.emit_expr(node.end), "i32") if node.end else self.builder.trunc(source_len, ir.IntType(32))
        start64 = self.builder.zext(start, ir.IntType(64), name="str.slice.start64")
        end64 = self.builder.zext(end, ir.IntType(64), name="str.slice.end64")
        out = self.alloca_at_entry("__nc_str_slice_out", STR_TYPE)
        source_ptr = self.value_to_stack_ptr(source, STR_TYPE, "__nc_str_slice_source")
        self.builder.call(self.str_slice_fn, [out, source_ptr, start64, end64])
        return self.builder.load(out, name="str.slice")

    def slice_value(self, elem_type, ptr, length, cap):
        if isinstance(length, int):
            length = ir.Constant(ir.IntType(64), length)
        if isinstance(cap, int):
            cap = ir.Constant(ir.IntType(64), cap)
        value = ir.Constant(llvm_type(f"[]{elem_type}"), ir.Undefined)
        value = self.builder.insert_value(value, ptr, [0], name="slice.ptr")
        value = self.builder.insert_value(value, length, [1], name="slice.len")
        value = self.builder.insert_value(value, cap, [2], name="slice.cap")
        return value

    def emit_slice_copy_raw(self, elem_type: str, source_ptr, count64):
        self.ensure_ncrt_runtime()
        slice_type = llvm_type(f"[]{elem_type}")
        out = self.alloca_at_entry("__nc_slice_copy_out", slice_type)
        self.builder.call(
            self.slice_copy_fn,
            [
                self.builder.bitcast(out, RAW_SLICE_TYPE.as_pointer()),
                self.builder.bitcast(source_ptr, I8PTR),
                count64,
                ir.Constant(ir.IntType(64), self.aligned_sizeof_type(elem_type)),
            ],
        )
        return self.builder.load(out, name="slice.copy")

    def emit_lvalue(self, node):
        if isinstance(node, Identifier):
            return self.vars[node.name]
        if isinstance(node, FieldAccess):
            obj_ptr, obj_type = self.emit_lvalue(node.obj)
            if obj_type == "str":
                field_index = 0 if node.field == "ptr" else 1
                field_type = "?*i8" if node.field == "ptr" else "u64"
                zero = ir.Constant(ir.IntType(32), 0)
                index = ir.Constant(ir.IntType(32), field_index)
                field_ptr = self.builder.gep(obj_ptr, [zero, index], inbounds=True, name="str.field.ptr")
                return field_ptr, field_type
            if parse_slice_type(obj_type) is not None:
                elem_type = parse_slice_type(obj_type)
                field_index = {"ptr": 0, "len": 1, "cap": 2}[node.field]
                field_type = f"?*{elem_type}" if node.field == "ptr" else "u64"
                zero = ir.Constant(ir.IntType(32), 0)
                index = ir.Constant(ir.IntType(32), field_index)
                field_ptr = self.builder.gep(obj_ptr, [zero, index], inbounds=True, name="slice.field.ptr")
                return field_ptr, field_type
            if obj_type.startswith("*") or obj_type.startswith("?*"):
                struct_type_name = obj_type[2:] if obj_type.startswith("?*") else obj_type[1:]
                struct_ptr = self.builder.load(obj_ptr, name="field.obj.ptr")
                field_index = STRUCT_FIELD_INDEX[struct_type_name][node.field]
                field_type = STRUCT_FIELDS[struct_type_name][field_index][1]
                zero = ir.Constant(ir.IntType(32), 0)
                index = ir.Constant(ir.IntType(32), field_index)
                field_ptr = self.builder.gep(struct_ptr, [zero, index], inbounds=True, name="field.ptr")
                return field_ptr, field_type
            field_index = STRUCT_FIELD_INDEX[obj_type][node.field]
            field_type = STRUCT_FIELDS[obj_type][field_index][1]
            zero = ir.Constant(ir.IntType(32), 0)
            index = ir.Constant(ir.IntType(32), field_index)
            field_ptr = self.builder.gep(obj_ptr, [zero, index], inbounds=True, name="field.ptr")
            return field_ptr, field_type
        if isinstance(node, IndexAccess):
            if parse_slice_type(node.obj.type) is not None:
                slice_value = self.emit_expr(node.obj)
                elem_type = parse_slice_type(node.obj.type)
                ptr = self.builder.extract_value(slice_value, 0)
                idx = self.cast_to(self.emit_expr(node.index), "i32")
                elem_ptr = self.builder.gep(ptr, [idx], inbounds=True, name="slice.idx.ptr")
                return elem_ptr, elem_type
            array_ptr, array_type = self.emit_lvalue(node.obj)
            array_info = parse_array_type(array_type)
            if array_info is None:
                raise NotImplementedError(f"LLVM backend cannot index {array_type}")
            _length, elem_type = array_info
            idx = self.cast_to(self.emit_expr(node.index), "i32")
            zero = ir.Constant(ir.IntType(32), 0)
            elem_ptr = self.builder.gep(array_ptr, [zero, idx], inbounds=True, name="idx.ptr")
            return elem_ptr, elem_type
        raise NotImplementedError(f"LLVM backend cannot take lvalue of {type(node).__name__}")

    def emit_binary(self, node: BinaryOp):
        if getattr(node, "overload_method", None):
            receiver_expr = node.left
            for field in getattr(node, "overload_receiver_path", []):
                receiver_expr = FieldAccess(receiver_expr, field)
            return self.emit_operator_method_call(receiver_expr, node.overload_method, node.right,
                                                  getattr(node, "overload_receiver_base", node.left.type))
        left = self.emit_expr(node.left)
        right = self.emit_expr(node.right)
        typ = node.left.type
        if node.op in ("==", "!=") and (node.left.type == "__nil" or node.right.type == "__nil"):
            if node.left.type == "__nil":
                left = self.cast_to(left, node.right.type)
            if node.right.type == "__nil":
                right = self.cast_to(right, node.left.type)
            eq = self.builder.icmp_unsigned("==", left, right)
            return self.builder.not_(eq) if node.op == "!=" else eq
        if typ == "str" and node.op in ("==", "!="):
            eq = self.emit_str_eq(left, right)
            if node.op == "!=":
                return self.builder.not_(eq)
            return eq
        if typ in STRUCT_FIELDS and node.op in ("==", "!="):
            eq = self.emit_struct_eq(left, right, typ)
            if node.op == "!=":
                return self.builder.not_(eq)
            return eq
        if typ == "str" and node.op == "+":
            return self.emit_str_cat(left, right)
        return self.emit_binary_values(left, node.op, right, typ)

    def emit_binary_values(self, left, op, right, typ):
        if typ in FLOAT_TYPES:
            return self.emit_float_binary(left, op, right)
        if op == "+":
            return self.builder.add(left, right)
        if op == "-":
            return self.builder.sub(left, right)
        if op == "*":
            return self.builder.mul(left, right)
        if op == "/":
            return self.builder.sdiv(left, right) if typ in SIGNED_INT_TYPES else self.builder.udiv(left, right)
        if op == "%":
            return self.builder.srem(left, right) if typ in SIGNED_INT_TYPES else self.builder.urem(left, right)
        if op == "&":
            return self.builder.and_(left, right)
        if op == "|":
            return self.builder.or_(left, right)
        if op == "^":
            return self.builder.xor(left, right)
        if op == "<<":
            return self.builder.shl(left, right)
        if op == ">>":
            return self.builder.ashr(left, right) if typ in SIGNED_INT_TYPES else self.builder.lshr(left, right)
        if op in ("==", "!=", "<", "<=", ">", ">="):
            pred = {
                "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">=",
            }[op]
            if typ in UNSIGNED_INT_TYPES:
                return self.builder.icmp_unsigned(pred, left, right)
            else:
                return self.builder.icmp_signed(pred, left, right)
        if op == "&&":
            return self.builder.and_(self.bool_value(left), self.bool_value(right))
        if op == "||":
            return self.builder.or_(self.bool_value(left), self.bool_value(right))
        raise NotImplementedError(f"LLVM backend does not support binary operator {op}")

    def emit_float_binary(self, left, op, right):
        if op == "+":
            return self.builder.fadd(left, right)
        if op == "-":
            return self.builder.fsub(left, right)
        if op == "*":
            return self.builder.fmul(left, right)
        if op == "/":
            return self.builder.fdiv(left, right)
        if op in ("==", "!=", "<", "<=", ">", ">="):
            pred = {"==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}[op]
            return self.builder.fcmp_ordered(pred, left, right)
        raise NotImplementedError(f"LLVM backend does not support float operator {op}")

    def emit_receiver_arg(self, obj, receiver_base: str):
        obj_type = obj.type
        if obj_type == f"*{receiver_base}":
            return self.emit_expr(obj)
        if obj_type == receiver_base:
            if isinstance(obj, (Identifier, FieldAccess, IndexAccess)):
                ptr, _typ = self.emit_lvalue(obj)
                return ptr
            value = self.emit_expr(obj)
            slot = self.alloca_at_entry("__nc_receiver_tmp", llvm_type(receiver_base))
            self.builder.store(value, slot)
            return slot
        value = self.emit_expr(obj)
        slot = self.alloca_at_entry("__nc_receiver_tmp", llvm_type(receiver_base))
        self.builder.store(value, slot)
        return slot

    def emit_operator_method_call(self, receiver_expr, method_name: str, rhs, receiver_base: str):
        name = safe_user_ident(f"{receiver_base}_{method_name}")
        fn = self.module.globals[name]
        fn_decl = self.fn_decls[name]
        args = [self.emit_receiver_arg(receiver_expr, receiver_base), self.emit_coerced_expr(rhs, receiver_base)]
        return self.builder.call(fn, args)

    def emit_operator_method_value(self, value, value_type: str, method_name: str, rhs, receiver_base: str):
        name = safe_user_ident(f"{receiver_base}_{method_name}")
        fn = self.module.globals[name]
        slot = self.alloca_at_entry("__nc_operator_receiver", llvm_type(value_type))
        self.builder.store(value, slot)
        args = [slot, self.emit_coerced_expr(rhs, value_type)]
        return self.builder.call(fn, args)

    def emit_if_expr(self, node: IfExpr):
        cond = self.bool_value(self.emit_expr(node.condition))
        then_bb = self.func.append_basic_block("if.then")
        else_bb = self.func.append_basic_block("if.else")
        end_bb = self.func.append_basic_block("if.end")
        self.builder.cbranch(cond, then_bb, else_bb)
        self.builder.position_at_end(then_bb)
        then_val = self.emit_block_value(node.then_block)
        then_block = self.builder.block
        if not self.builder.block.is_terminated:
            self.builder.branch(end_bb)
        self.builder.position_at_end(else_bb)
        else_val = self.emit_block_value(node.else_block) if node.else_block else None
        else_block = self.builder.block
        if not self.builder.block.is_terminated:
            self.builder.branch(end_bb)
        self.builder.position_at_end(end_bb)
        if node.type == "void":
            return ir.Constant(ir.IntType(1), 0)
        phi = self.builder.phi(llvm_type(node.type))
        phi.add_incoming(self.cast_to(then_val, node.type), then_block)
        phi.add_incoming(self.cast_to(else_val, node.type), else_block)
        return phi

    def emit_match_expr(self, node: MatchExpr):
        scrutinee = self.emit_expr(node.scrutinee)
        end_bb = self.func.append_basic_block("match.end")
        incoming = []

        for i, (pattern, body) in enumerate(node.arms):
            body_bb = self.func.append_basic_block(f"match.arm.{i}")
            next_bb = self.func.append_basic_block(f"match.next.{i}")
            if pattern is None:
                self.builder.branch(body_bb)
            else:
                cond = self.match_condition(scrutinee, node.scrutinee.type, pattern)
                self.builder.cbranch(cond, body_bb, next_bb)
            self.builder.position_at_end(body_bb)
            body_val = self.emit_expr(body)
            body_block = self.builder.block
            if not self.builder.block.is_terminated:
                self.builder.branch(end_bb)
            incoming.append((body_val, body_block))
            self.builder.position_at_end(next_bb)

        if not self.builder.block.is_terminated:
            self.builder.unreachable()
        self.builder.position_at_end(end_bb)
        if node.type == "void":
            return ir.Constant(ir.IntType(1), 0)
        phi = self.builder.phi(llvm_type(node.type))
        for value, block in incoming:
            phi.add_incoming(self.cast_to(value, node.type), block)
        return phi

    def match_condition(self, scrutinee, scrutinee_type, pattern):
        pattern_value = self.emit_expr(pattern)
        if scrutinee_type == "str":
            return self.emit_str_eq(scrutinee, pattern_value)
        if scrutinee_type in FLOAT_TYPES:
            return self.builder.fcmp_ordered("==", scrutinee, pattern_value)
        return self.builder.icmp_signed("==", scrutinee, pattern_value)

    def emit_block_value(self, block: Block):
        if not block.statements:
            return ir.Constant(ir.IntType(1), 0)
        *prefix, tail = block.statements
        for stmt in prefix:
            self.emit_stmt(stmt)
        if isinstance(tail, ExpressionStatement):
            return self.emit_expr(tail.expr)
        self.emit_stmt(tail)
        return ir.Constant(ir.IntType(1), 0)

    def emit_call(self, node: FunctionCall):
        if node.name in ("io.print", "io.println"):
            if len(node.args) != 1:
                raise RuntimeError(f"{node.name} expects one argument")
            return self.emit_print(node.args[0], newline=node.name == "io.println")
        if getattr(node, "is_closure_call", False):
            closure = self.emit_expr(Identifier(node.name))
            call_ptr = self.builder.extract_value(closure, 0)
            env = self.builder.extract_value(closure, 1)
            param_types = getattr(node, "closure_param_types", [arg.type for arg in node.args])
            args = [env] + [self.emit_coerced_expr(arg, ptype) for arg, ptype in zip(node.args, param_types)]
            return self.builder.call(call_ptr, args)
        if node.name == "len":
            if len(node.args) != 1:
                raise RuntimeError("len expects one argument")
            arg = self.emit_expr(node.args[0])
            if node.args[0].type == "str":
                length64 = self.builder.extract_value(arg, 1)
                return self.builder.trunc(length64, ir.IntType(32))
            if parse_slice_type(node.args[0].type) is not None:
                length64 = self.builder.extract_value(arg, 1)
                return self.builder.trunc(length64, ir.IntType(32))
            if parse_map_type(node.args[0].type) is not None:
                length64 = self.builder.extract_value(arg, 3)
                return self.builder.trunc(length64, ir.IntType(32))
            raise NotImplementedError(f"LLVM backend cannot take len of {node.args[0].type}")
        if node.name == "cap":
            if len(node.args) != 1:
                raise RuntimeError("cap expects one argument")
            if parse_slice_type(node.args[0].type) is None:
                raise NotImplementedError(f"LLVM backend cannot take cap of {node.args[0].type}")
            arg = self.emit_expr(node.args[0])
            cap64 = self.builder.extract_value(arg, 2)
            return self.builder.trunc(cap64, ir.IntType(32))
        if parse_map_type(node.name) is not None:
            return self.emit_map_new(node.name)
        if node.name == "delete":
            if len(node.args) != 2:
                raise RuntimeError("delete expects two arguments")
            return self.emit_map_delete(node.args[0], node.args[1])
        if node.name == "clear":
            if len(node.args) != 1:
                raise RuntimeError("clear expects one argument")
            return self.emit_clear(node.args[0])
        if node.name == "copy":
            if len(node.args) != 2:
                raise RuntimeError("copy expects two arguments")
            return self.emit_slice_copy_into(node.args[0], node.args[1])
        if node.name in ("min", "max"):
            if len(node.args) != 2:
                raise RuntimeError(f"{node.name} expects two arguments")
            return self.emit_min_max(node.name, node.args[0], node.args[1])
        if node.name == "abs":
            if len(node.args) != 1:
                raise RuntimeError("abs expects one argument")
            return self.emit_abs(node.args[0])
        if node.name == "str":
            if len(node.args) != 1:
                raise RuntimeError("str expects one argument")
            return self.emit_to_str(node.args[0])
        if node.name == "append":
            if len(node.args) != 2:
                raise RuntimeError("append expects two arguments")
            slice_type = node.args[0].type
            elem_type = parse_slice_type(slice_type)
            if elem_type is None:
                raise NotImplementedError(f"LLVM backend cannot append to {slice_type}")
            return self.emit_append(node.args[0], node.args[1], elem_type)
        if node.name == "__nc_str_alloc":
            if len(node.args) != 1:
                raise RuntimeError("__nc_str_alloc expects one argument")
            return self.emit_str_alloc(node.args[0])
        if node.name == "__nc_bytes_alloc":
            if len(node.args) != 1:
                raise RuntimeError("__nc_bytes_alloc expects one argument")
            return self.emit_bytes_alloc(node.args[0])
        if node.name == "runtime.gc_collect":
            if len(node.args) != 0:
                raise RuntimeError("runtime.gc_collect expects no arguments")
            return self.emit_gc_collect()
        if node.name == "runtime.gc_live":
            if len(node.args) != 0:
                raise RuntimeError("runtime.gc_live expects no arguments")
            return self.emit_gc_live()
        if node.name == "rune":
            if len(node.args) != 1:
                raise RuntimeError("rune expects one argument")
            return self.cast_to(self.emit_expr(node.args[0]), "rune")
        if node.name in INT_TYPES or node.name in FLOAT_TYPES:
            if len(node.args) != 1:
                raise RuntimeError(f"{node.name} expects one argument")
            if node.name == "i32" and node.args[0].type == "str":
                return self.emit_str_to_i32(node.args[0])
            if node.name in ("i32", "u32") and node.args[0].type == "rune":
                return self.cast_to(self.emit_expr(node.args[0]), node.name)
            return self.cast_numeric(self.emit_expr(node.args[0]), node.args[0].type, node.name)
        if node.name not in self.fn_decls:
            raise NotImplementedError(f"LLVM backend cannot call {node.name}")
        fn_decl = self.fn_decls[node.name]
        if getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"fallible call {node.name} must be lowered through a fallible operator")
        fn = self.module.globals[self.function_symbol(fn_decl)]
        coerced_args = [
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ]
        return self.builder.call(fn, coerced_args)

    def emit_fallible_op(self, node: FallibleOp):
        status, value_slot, error_slot, success_type = self.emit_fallible_call_raw(node.expr)
        if node.op == "is_err":
            return status
        err_bb = self.func.append_basic_block("fallible.err")
        ok_bb = self.func.append_basic_block("fallible.ok")
        self.builder.cbranch(status, err_bb, ok_bb)
        self.builder.position_at_end(err_bb)
        err_value = self.builder.load(error_slot, name="fallible.err.value")
        if node.op == "??":
            self.emit_error_return_value(err_value)
        elif node.op == "!!":
            self.emit_print_error(err_value)
            self.emit_exit(1)
            self.builder.unreachable()
        else:
            raise RuntimeError(f"unknown fallible operator {node.op}")
        self.builder.position_at_end(ok_bb)
        if success_type == "void":
            return ir.Constant(ir.IntType(1), 0)
        return self.builder.load(value_slot, name="fallible.ok.value")

    def emit_fallible_call_raw(self, call_node):
        if isinstance(call_node, FunctionCall):
            return self.emit_fallible_function_call_raw(call_node)
        if isinstance(call_node, MethodCall):
            return self.emit_fallible_method_call_raw(call_node)
        raise RuntimeError(f"fallible operator requires a fallible call, got {type(call_node).__name__}")

    def fallible_out_slots(self, success_type):
        value_slot = None
        if success_type != "void":
            value_slot = self.alloca_at_entry("__nc_fallible_value", llvm_type(success_type))
            self.root_slots_for_type(value_slot, success_type)
        error_slot = self.alloca_at_entry("__nc_fallible_error", STR_TYPE)
        self.root_slots_for_type(error_slot, "error")
        return value_slot, error_slot

    def emit_fallible_function_call_raw(self, node: FunctionCall):
        fn_decl = self.fn_decls[node.name]
        if not getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"{node.name} is not fallible")
        fn = self.module.globals[self.function_symbol(fn_decl)]
        success_type = fn_decl.return_type or "void"
        value_slot, error_slot = self.fallible_out_slots(success_type)
        args = []
        if value_slot is not None:
            args.append(value_slot)
        args.append(error_slot)
        args.extend([
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ])
        status = self.builder.call(fn, args, name="fallible.status")
        return status, value_slot, error_slot, success_type

    def emit_function_expr(self, node: FunctionExpr):
        closure_type = llvm_type(node.type)
        fn = self.module.globals[self.closure_symbol(node)]
        env_ptr = self.emit_closure_env(node)
        value = ir.Constant(closure_type, ir.Undefined)
        value = self.builder.insert_value(value, fn.bitcast(closure_type.elements[0]), [0], name="closure.call")
        value = self.builder.insert_value(value, env_ptr, [1], name="closure.env")
        return value

    def emit_generic_function_value(self, node: GenericFunctionValue):
        closure_type = llvm_type(node.type)
        thunk = self.function_value_thunk(node.name, node.type)
        value = ir.Constant(closure_type, ir.Undefined)
        value = self.builder.insert_value(value, thunk.bitcast(closure_type.elements[0]), [0], name="fn.value.call")
        value = self.builder.insert_value(value, ir.Constant(I8PTR, None), [1], name="fn.value.env")
        return value

    def function_value_thunk(self, fn_name: str, fn_value_type: str):
        if fn_name in self.function_value_thunks:
            return self.function_value_thunks[fn_name]
        parsed = parse_fn_type(fn_value_type)
        if parsed is None:
            raise RuntimeError(f"{fn_name} is not a function value")
        param_types, ret_type = parsed
        thunk_name = f"__nc_fnval_{safe_user_ident(fn_name)}"
        thunk_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types])
        thunk = ir.Function(self.module, thunk_type, name=thunk_name)
        self.function_value_thunks[fn_name] = thunk

        block = thunk.append_basic_block("entry")
        saved_builder = self.builder
        self.builder = ir.IRBuilder(block)
        target = self.module.globals[self.function_symbol(self.fn_decls[fn_name])]
        result = self.builder.call(target, [arg for arg in thunk.args[1:]])
        if ret_type == "void":
            self.builder.ret_void()
        else:
            self.builder.ret(result)
        self.builder = saved_builder
        return thunk

    def emit_closure_env(self, node: FunctionExpr):
        captures = getattr(node, "captures", [])
        if not captures:
            return ir.Constant(I8PTR, None)
        env_type = self.closure_env_types[node.closure_id]
        size = self.sizeof_fields([capture_type for _name, capture_type in captures])
        raw = self.malloc_bytes(ir.Constant(ir.IntType(64), max(size, 1)))
        env_ptr = self.builder.bitcast(raw, env_type.as_pointer(), name="closure.env.alloc")
        for i, (capture_name, capture_type) in enumerate(captures):
            source_ptr, _source_type = self.vars[capture_name]
            capture_value = self.builder.load(source_ptr, name=f"capture.{safe_user_ident(capture_name)}")
            field_ptr = self.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{safe_user_ident(capture_name)}.store.ptr",
            )
            self.builder.store(self.cast_to(capture_value, capture_type), field_ptr)
        return self.builder.bitcast(env_ptr, I8PTR, name="closure.env.i8")

    def emit_method_call(self, node: MethodCall):
        obj_type = node.obj.type
        if obj_type == "str" and node.method == "c_str":
            value = self.emit_expr(node.obj)
            ptr = self.builder.extract_value(value, 0)
            is_null = self.builder.icmp_unsigned("==", ptr, ir.Constant(I8PTR, None), name="str.c_str.is_null")
            return self.builder.select(is_null, self.empty_string_ptr(), ptr, name="str.c_str")
        if parse_map_type(obj_type) is not None and node.method == "has":
            if len(node.args) != 1:
                raise RuntimeError("method has expects one argument")
            return self.emit_map_has(node.obj, node.args[0])
        if obj_type in IFACE_METHODS:
            iface_value = self.emit_expr(node.obj)
            method_index = next(i for i, (name, _params, _ret) in enumerate(IFACE_METHODS[obj_type]) if name == node.method)
            _mname, param_types, ret_type = IFACE_METHODS[obj_type][method_index]
            vt_i8 = self.builder.extract_value(iface_value, 0, name="iface.vtable")
            data = self.builder.extract_value(iface_value, 1, name="iface.data")
            fn_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types]).as_pointer()
            vt_type = ir.LiteralStructType(self.iface_vtable_function_ptr_types(obj_type)).as_pointer()
            vt_ptr = self.builder.bitcast(vt_i8, vt_type, name="iface.vtable.ptr")
            fn_ptr_ptr = self.builder.gep(
                vt_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), method_index)],
                inbounds=True,
                name="iface.method.ptr.ptr",
            )
            fn_ptr = self.builder.load(fn_ptr_ptr, name="iface.method.ptr")
            fn_ptr = self.builder.bitcast(fn_ptr, fn_type, name="iface.method.cast")
            args = [data] + [self.emit_coerced_expr(arg, ptype) for arg, ptype in zip(node.args, param_types)]
            return self.builder.call(fn_ptr, args)
        if obj_type.startswith("?*"):
            receiver_base = obj_type[2:]
        elif obj_type.startswith("*"):
            receiver_base = obj_type[1:]
        else:
            receiver_base = obj_type
        name = safe_user_ident(f"{receiver_base}_{node.method}")
        if name not in self.module.globals:
            raise NotImplementedError(f"LLVM backend cannot call method {receiver_base}.{node.method}")
        fn = self.module.globals[name]
        fn_decl = self.fn_decls[name]
        if getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"fallible method call {receiver_base}.{node.method} must be lowered through a fallible operator")
        args = [self.emit_receiver_arg(node.obj, receiver_base)] + [
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ]
        return self.builder.call(fn, args)

    def emit_fallible_method_call_raw(self, node: MethodCall):
        obj_type = node.obj.type
        if obj_type.startswith("?*"):
            receiver_base = obj_type[2:]
        elif obj_type.startswith("*"):
            receiver_base = obj_type[1:]
        else:
            receiver_base = obj_type
        name = safe_user_ident(f"{receiver_base}_{node.method}")
        if name not in self.module.globals:
            raise RuntimeError(f"method {receiver_base}.{node.method} is not fallible")
        fn_decl = self.fn_decls[name]
        if not getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"method {receiver_base}.{node.method} is not fallible")
        fn = self.module.globals[name]
        success_type = fn_decl.return_type or "void"
        value_slot, error_slot = self.fallible_out_slots(success_type)
        args = []
        if value_slot is not None:
            args.append(value_slot)
        args.append(error_slot)
        args.append(self.emit_receiver_arg(node.obj, receiver_base))
        args.extend([
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ])
        status = self.builder.call(fn, args, name="fallible.method.status")
        return status, value_slot, error_slot, success_type

    def iface_vtable_function_ptr_types(self, iface_name):
        return [
            ir.FunctionType(llvm_type(ret), [I8PTR] + [llvm_type(t) for t in params]).as_pointer()
            for _name, params, ret in IFACE_METHODS[iface_name]
        ]

    def emit_print(self, arg, newline: bool):
        self.ensure_printf()
        val = self.emit_expr(arg)
        typ = arg.type
        line = "\n" if newline else ""
        if typ == "str":
            fmt = self.global_c_string("%.*s" + line, "fmt_str")
            ptr = self.builder.extract_value(val, 0)
            length64 = self.builder.extract_value(val, 1)
            length32 = self.builder.trunc(length64, ir.IntType(32))
            return self.builder.call(self.printf, [fmt, length32, ptr])
        if typ == "rune":
            s = self.emit_rune_value_to_str(val)
            fmt = self.global_c_string("%.*s" + line, "fmt_rune")
            ptr = self.builder.extract_value(s, 0)
            length64 = self.builder.extract_value(s, 1)
            length32 = self.builder.trunc(length64, ir.IntType(32))
            return self.builder.call(self.printf, [fmt, length32, ptr])
        if typ == "bool":
            fmt = self.global_c_string("%d" + line, "fmt_bool")
            as_i32 = self.builder.zext(self.bool_value(val), ir.IntType(32), name="bool.i32")
            return self.builder.call(self.printf, [fmt, as_i32])
        if typ in ("f32", "f64"):
            fmt = self.global_c_string("%g" + line, "fmt_float")
            if typ == "f32":
                val = self.builder.fpext(val, ir.DoubleType())
            return self.builder.call(self.printf, [fmt, val])
        if typ in INT_TYPES:
            fmt = self.global_c_string("%lld" + line, "fmt_int")
            if val.type.width < 64:
                val = self.builder.sext(val, ir.IntType(64)) if typ in SIGNED_INT_TYPES else self.builder.zext(val, ir.IntType(64))
            return self.builder.call(self.printf, [fmt, val])
        raise NotImplementedError(f"LLVM backend cannot print type: {typ}")

    def emit_to_str(self, arg_expr):
        typ = arg_expr.type
        if typ == "str":
            return self.emit_expr(arg_expr)
        if typ == "[]u8":
            return self.emit_u8_slice_to_str(arg_expr)
        if typ in ("*i8", "?*i8", "*u8", "?*u8"):
            return self.emit_cstr_to_str(arg_expr)
        if typ == "rune":
            return self.emit_rune_value_to_str(self.emit_expr(arg_expr))
        if typ == "bool":
            return self.emit_i32_value_to_str(self.builder.zext(self.bool_value(self.emit_expr(arg_expr)), ir.IntType(32), name="bool.str.i32"))
        if typ in INT_TYPES:
            value = self.emit_expr(arg_expr)
            if typ in UNSIGNED_INT_TYPES and typ != "bool":
                return self.emit_u64_value_to_str(self.cast_to(value, "u64"))
            return self.emit_i64_value_to_str(self.cast_to(value, "i64"))
        if typ in FLOAT_TYPES:
            value = self.emit_expr(arg_expr)
            if typ == "f32":
                value = self.builder.fpext(value, ir.DoubleType())
            return self.emit_f64_value_to_str(value)
        raise NotImplementedError(f"LLVM backend cannot convert {typ} to str")

    def emit_append(self, slice_expr, elem_expr, elem_type: str):
        self.ensure_ncrt_runtime()
        slice_type = llvm_type(f"[]{elem_type}")
        source = self.emit_expr(slice_expr)
        source_slot = self.value_to_stack_ptr(source, slice_type, "__nc_append_source")
        elem_value = self.cast_to(self.emit_expr(elem_expr), elem_type)
        elem_slot = self.value_to_stack_ptr(elem_value, llvm_type(elem_type), "__nc_append_elem")
        out = self.alloca_at_entry("__nc_append_out", slice_type)
        self.builder.call(
            self.slice_append_fn,
            [
                self.builder.bitcast(out, RAW_SLICE_TYPE.as_pointer()),
                self.builder.bitcast(source_slot, RAW_SLICE_TYPE.as_pointer()),
                self.builder.bitcast(elem_slot, I8PTR),
                ir.Constant(ir.IntType(64), self.aligned_sizeof_type(elem_type)),
            ],
        )
        return self.builder.load(out, name="slice.append")

    def emit_slice_copy_into(self, dst_expr, src_expr):
        self.ensure_ncrt_runtime()
        elem_type = parse_slice_type(dst_expr.type)
        if elem_type is None:
            raise NotImplementedError(f"LLVM backend cannot copy into {dst_expr.type}")
        slice_type = llvm_type(dst_expr.type)
        dst = self.emit_expr(dst_expr)
        src = self.emit_expr(src_expr)
        dst_slot = self.value_to_stack_ptr(dst, slice_type, "__nc_copy_dst")
        src_slot = self.value_to_stack_ptr(src, slice_type, "__nc_copy_src")
        return self.builder.call(
            self.slice_copy_into_fn,
            [
                self.builder.bitcast(dst_slot, RAW_SLICE_TYPE.as_pointer()),
                self.builder.bitcast(src_slot, RAW_SLICE_TYPE.as_pointer()),
                ir.Constant(ir.IntType(64), self.aligned_sizeof_type(elem_type)),
            ],
            name="slice.copy.into",
        )

    def emit_clear(self, expr):
        self.ensure_ncrt_runtime()
        elem_type = parse_slice_type(expr.type)
        if elem_type is not None:
            value = self.emit_expr(expr)
            slot = self.value_to_stack_ptr(value, llvm_type(expr.type), "__nc_clear_slice")
            self.builder.call(
                self.slice_clear_fn,
                [
                    self.builder.bitcast(slot, RAW_SLICE_TYPE.as_pointer()),
                    ir.Constant(ir.IntType(64), self.aligned_sizeof_type(elem_type)),
                ],
            )
            return ir.Constant(ir.IntType(1), 0)
        if parse_map_type(expr.type) is not None:
            self.builder.call(self.map_clear_fn, [self.map_pointer_for_expr(expr)])
            return ir.Constant(ir.IntType(1), 0)
        raise NotImplementedError(f"LLVM backend cannot clear {expr.type}")

    def emit_min_max(self, name: str, left_expr, right_expr):
        typ = left_expr.type
        left = self.emit_expr(left_expr)
        right = self.emit_coerced_expr(right_expr, typ)
        if typ in FLOAT_TYPES:
            pred = "<=" if name == "min" else ">="
            cond = self.builder.fcmp_ordered(pred, left, right, name=f"{name}.cmp")
        elif typ in UNSIGNED_INT_TYPES:
            pred = "<=" if name == "min" else ">="
            cond = self.builder.icmp_unsigned(pred, left, right, name=f"{name}.cmp")
        else:
            pred = "<=" if name == "min" else ">="
            cond = self.builder.icmp_signed(pred, left, right, name=f"{name}.cmp")
        return self.builder.select(cond, left, right, name=name)

    def emit_abs(self, arg_expr):
        typ = arg_expr.type
        value = self.emit_expr(arg_expr)
        if typ in FLOAT_TYPES:
            zero = ir.Constant(value.type, 0.0)
            neg = self.builder.fsub(zero, value, name="abs.neg")
            cond = self.builder.fcmp_ordered("<", value, zero, name="abs.cmp")
            return self.builder.select(cond, neg, value, name="abs")
        zero = ir.Constant(value.type, 0)
        neg = self.builder.sub(zero, value, name="abs.neg")
        cond = self.builder.icmp_signed("<", value, zero, name="abs.cmp")
        return self.builder.select(cond, neg, value, name="abs")

    def emit_str_cat(self, left, right):
        return self.string_emitter.emit_str_cat(left, right)

    def str_value(self, ptr, length):
        return self.string_emitter.str_value(ptr, length)

    def map_value(self, desc, entries, cap, length):
        return self.map_emitter.map_value(desc, entries, cap, length)

    def emit_map_new(self, map_type):
        return self.map_emitter.emit_map_new(map_type)

    def map_pointer_for_expr(self, map_expr):
        return self.map_emitter.map_pointer_for_expr(map_expr)

    def emit_map_get(self, map_expr, key_expr):
        return self.map_emitter.emit_map_get(map_expr, key_expr)

    def emit_map_has(self, map_expr, key_expr):
        return self.map_emitter.emit_map_has(map_expr, key_expr)

    def emit_map_delete(self, map_expr, key_expr):
        return self.map_emitter.emit_map_delete(map_expr, key_expr)

    def emit_map_set(self, map_expr, key_expr, value_expr, assign_op="="):
        return self.map_emitter.emit_map_set(map_expr, key_expr, value_expr, assign_op)

    def map_desc(self, map_type: str):
        return self.map_emitter.map_desc(map_type)

    def type_label(self, nc_type: str):
        return self.map_emitter.type_label(nc_type)

    def map_hash_fn(self, key_type: str):
        return self.map_emitter.map_hash_fn(key_type)

    def map_eq_fn(self, key_type: str):
        return self.map_emitter.map_eq_fn(key_type)

    def emit_map_hash_mix(self, builder, h, value):
        return self.map_emitter.emit_map_hash_mix(builder, h, value)

    def emit_map_hash_value(self, builder, value, typ, h):
        return self.map_emitter.emit_map_hash_value(builder, value, typ, h)

    def emit_map_eq_value(self, builder, left, right, typ):
        return self.map_emitter.emit_map_eq_value(builder, left, right, typ)

    def ensure_printf(self):
        if self.printf is None:
            i8ptr = ir.IntType(8).as_pointer()
            self.printf = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [i8ptr], var_arg=True), name="printf")

    def ensure_fprintf(self):
        if self.fprintf is None:
            self.fprintf = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR], var_arg=True),
                name="fprintf",
            )
            self.nc_stderr = ir.Function(
                self.module,
                ir.FunctionType(I8PTR, []),
                name="__nc_stderr",
            )

    def ensure_sprintf(self):
        if self.sprintf is None:
            self.sprintf = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR], var_arg=True),
                name="sprintf",
            )

    def ensure_atoi(self):
        if self.atoi is None:
            self.atoi = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR]),
                name="atoi",
            )

    def ensure_malloc(self):
        if self.malloc is None:
            self.malloc = ir.Function(self.module, ir.FunctionType(I8PTR, [ir.IntType(64)]), name="malloc")

    def ensure_gc_runtime(self):
        self.ensure_ncrt_runtime()

    def ensure_ncrt_runtime(self):
        if self.gc_alloc is None:
            self.gc_alloc = ir.Function(
                self.module,
                ir.FunctionType(I8PTR, [ir.IntType(64)]),
                name="__nc_gc_alloc",
            )
            self.gc_collect = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="__nc_gc_collect")
            self.gc_live = ir.Function(self.module, ir.FunctionType(ir.IntType(64), []), name="__nc_gc_live")
            self.gc_init = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="__nc_gc_init")
            self.gc_root_mark = ir.Function(self.module, ir.FunctionType(ir.IntType(64), []), name="__nc_gc_root_mark")
            self.gc_root_rewind = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [ir.IntType(64)]), name="__nc_gc_root_rewind")
            self.gc_push_root_slot = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR]), name="__nc_gc_push_root_slot")
            str_ptr = STR_TYPE.as_pointer()
            self.str_cat_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, str_ptr, str_ptr]), name="__nc_str_cat_out")
            self.str_slice_fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, str_ptr, ir.IntType(64), ir.IntType(64)]),
                name="__nc_str_slice_copy_out",
            )
            self.i32_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(32)]), name="__nc_i32_to_str_out")
            self.i64_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(64)]), name="__nc_i64_to_str_out")
            self.u64_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(64)]), name="__nc_u64_to_str_out")
            self.f64_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, ir.DoubleType()]), name="__nc_f64_to_str_out")
            self.rune_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(32)]), name="__nc_rune_to_str_out")
            self.str_to_i32_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [str_ptr]), name="__nc_str_to_i32_ptr")
            self.cstr_to_str_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [str_ptr, I8PTR]), name="__nc_cstr_to_str_out")
            raw_slice_ptr = RAW_SLICE_TYPE.as_pointer()
            self.os_set_args_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [ir.IntType(32), I8PTR.as_pointer()]), name="__nc_os_set_args")
            self.map_init_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR]), name="__nc_map_init")
            self.map_get_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I8PTR, MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]), name="__nc_map_get")
            self.map_set_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR, I8PTR]), name="__nc_map_set")
            self.map_has_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]), name="__nc_map_has")
            self.map_delete_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]), name="__nc_map_delete")
            self.map_clear_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer()]), name="__nc_map_clear")
            self.map_next_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(64), [MAP_TYPE.as_pointer(), ir.IntType(64), I8PTR, I8PTR]), name="__nc_map_next")
            self.slice_copy_fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, I8PTR, ir.IntType(64), ir.IntType(64)]),
                name="__nc_slice_copy_raw",
            )
            self.slice_append_fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, raw_slice_ptr, I8PTR, ir.IntType(64)]),
                name="__nc_slice_append_raw",
            )
            self.slice_copy_into_fn = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [raw_slice_ptr, raw_slice_ptr, ir.IntType(64)]),
                name="__nc_slice_copy_into_raw",
            )
            self.slice_clear_fn = ir.Function(
                self.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, ir.IntType(64)]),
                name="__nc_slice_clear_raw",
            )

    def value_to_stack_ptr(self, value, typ, name):
        slot = self.alloca_at_entry(name, typ)
        self.builder.store(value, slot)
        return slot

    def value_to_i8_stack_ptr(self, value, typ, name):
        return self.builder.bitcast(self.value_to_stack_ptr(value, typ, name), I8PTR)

    def malloc_array(self, elem_type: str, count):
        self.ensure_gc_runtime()
        elem_size = ir.Constant(ir.IntType(64), self.aligned_sizeof_type(elem_type))
        size = self.builder.mul(count, elem_size, name="malloc.size")
        raw = self.builder.call(self.gc_alloc, [size], name="gc.alloc.raw")
        return self.builder.bitcast(raw, llvm_type(elem_type).as_pointer(), name="malloc.typed")

    def malloc_bytes(self, count):
        self.ensure_gc_runtime()
        return self.builder.call(self.gc_alloc, [count], name="malloc.bytes")

    def emit_i32_to_str(self, arg_expr):
        return self.string_emitter.emit_i32_to_str(arg_expr)

    def emit_i32_value_to_str(self, value):
        return self.string_emitter.emit_i32_value_to_str(value)

    def emit_i64_value_to_str(self, value):
        return self.string_emitter.emit_i64_value_to_str(value)

    def emit_u64_value_to_str(self, value):
        return self.string_emitter.emit_u64_value_to_str(value)

    def emit_rune_value_to_str(self, value):
        return self.string_emitter.emit_rune_value_to_str(value)

    def emit_f64_value_to_str(self, value):
        return self.string_emitter.emit_f64_value_to_str(value)

    def emit_str_to_i32(self, arg_expr):
        return self.string_emitter.emit_str_to_i32(arg_expr)

    def emit_gc_live(self):
        self.ensure_ncrt_runtime()
        self.ensure_printf()
        fmt = self.global_c_string("%d\n", "fmt_gc_live")
        live64 = self.builder.call(self.gc_live, [], name="gc.live")
        live = self.builder.trunc(live64, ir.IntType(32), name="gc.live.i32")
        self.builder.call(self.printf, [fmt, live])
        return live

    def emit_gc_collect(self):
        self.ensure_ncrt_runtime()
        self.builder.call(self.gc_collect, [])
        return ir.Constant(ir.IntType(1), 0)

    def copy_bytes(self, dest, dest_offset, source, source_offset, count, label):
        idx_slot = self.alloca_at_entry(f"__nc_{label}_i", ir.IntType(64))
        self.builder.store(ir.Constant(ir.IntType(64), 0), idx_slot)
        cond_bb = self.func.append_basic_block(f"{label}.copy.cond")
        body_bb = self.func.append_basic_block(f"{label}.copy.body")
        end_bb = self.func.append_basic_block(f"{label}.copy.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        i = self.builder.load(idx_slot, name=f"{label}.i")
        self.builder.cbranch(self.builder.icmp_unsigned("<", i, count), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        src_i = self.builder.add(source_offset, i, name=f"{label}.src.i")
        dst_i = self.builder.add(dest_offset, i, name=f"{label}.dst.i")
        src_ptr = self.builder.gep(source, [src_i], inbounds=True)
        dst_ptr = self.builder.gep(dest, [dst_i], inbounds=True)
        self.builder.store(self.builder.load(src_ptr), dst_ptr)
        next_i = self.builder.add(i, ir.Constant(ir.IntType(64), 1))
        self.builder.store(next_i, idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def sizeof_type(self, nc_type: str) -> int:
        return self.layout.sizeof_type(nc_type)

    def alignof_type(self, nc_type: str) -> int:
        return self.layout.alignof_type(nc_type)

    def align_to(self, value: int, alignment: int) -> int:
        return self.layout.align_to(value, alignment)

    def aligned_sizeof_type(self, nc_type: str) -> int:
        return self.layout.aligned_sizeof_type(nc_type)

    def sizeof_fields(self, field_types: list[str]) -> int:
        return self.layout.sizeof_fields(field_types)

    def ensure_memcmp(self):
        if self.memcmp is None:
            self.memcmp = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR, ir.IntType(64)]),
                name="memcmp",
            )

    def emit_str_alloc(self, len_expr):
        return self.string_emitter.emit_str_alloc(len_expr)

    def emit_bytes_alloc(self, len_expr):
        return self.string_emitter.emit_bytes_alloc(len_expr)

    def emit_u8_slice_to_str(self, arg_expr):
        return self.string_emitter.emit_u8_slice_to_str(arg_expr)

    def emit_cstr_to_str(self, arg_expr):
        return self.string_emitter.emit_cstr_to_str(arg_expr)

    def emit_str_eq(self, left, right):
        return self.string_emitter.emit_str_eq(left, right)

    def emit_struct_eq(self, left, right, typ):
        result = ir.Constant(ir.IntType(1), 1)
        for i, (_field_name, field_type) in enumerate(STRUCT_FIELDS[typ]):
            left_field = self.builder.extract_value(left, [i], name="struct.eq.left")
            right_field = self.builder.extract_value(right, [i], name="struct.eq.right")
            field_eq = self.emit_eq_values(left_field, right_field, field_type)
            result = self.builder.and_(result, field_eq, name="struct.eq.and")
        return result

    def emit_eq_values(self, left, right, typ):
        if typ == "str":
            return self.emit_str_eq(left, right)
        if typ in STRUCT_FIELDS:
            return self.emit_struct_eq(left, right, typ)
        return self.emit_binary_values(left, "==", right, typ)

    def global_c_string(self, text: str, hint: str):
        key = (hint, text)
        if key in self.strings:
            return self.strings[key].bitcast(ir.IntType(8).as_pointer())
        raw = bytearray(text.encode("utf-8")) + b"\00"
        typ = ir.ArrayType(ir.IntType(8), len(raw))
        glob = ir.GlobalVariable(self.module, typ, name=f"__nc_{hint}_{len(self.strings)}")
        glob.linkage = "internal"
        glob.global_constant = True
        glob.initializer = ir.Constant(typ, raw)
        self.strings[key] = glob
        return glob.bitcast(ir.IntType(8).as_pointer())

    def empty_string_ptr(self):
        if self.empty_c_string is None:
            self.empty_c_string = self.global_c_string("", "empty_c_str")
        return self.empty_c_string

    def bool_value(self, value):
        if isinstance(value.type, ir.IntType) and value.type.width == 1:
            return value
        return self.builder.icmp_unsigned("!=", value, ir.Constant(value.type, 0))

    def default_llvm_value(self, typ):
        if typ == ir.VoidType():
            return None
        if isinstance(typ, ir.IntType):
            return ir.Constant(typ, 0)
        if isinstance(typ, (ir.FloatType, ir.DoubleType)):
            return ir.Constant(typ, 0.0)
        if isinstance(typ, ir.PointerType):
            return ir.Constant(typ, None)
        if isinstance(typ, ir.LiteralStructType):
            return ir.Constant.literal_struct([
                self.default_llvm_value(elem) for elem in typ.elements
            ])
        if isinstance(typ, ir.ArrayType):
            return ir.Constant(typ, None)
        return ir.Constant(typ, None)

    def cast_to(self, value, nc_type):
        if nc_type == "error":
            nc_type = "str"
        target = llvm_type(nc_type)
        if value.type == target:
            return value
        if isinstance(value.type, ir.IntType) and isinstance(target, ir.IntType):
            if value.type.width < target.width:
                return self.builder.sext(value, target) if nc_type in SIGNED_INT_TYPES else self.builder.zext(value, target)
            if value.type.width > target.width:
                return self.builder.trunc(value, target)
        if isinstance(value.type, ir.PointerType) and isinstance(target, ir.PointerType):
            if value.type == target:
                return value
            if isinstance(value, ir.Constant) and value.constant is None:
                return ir.Constant(target, None)
            return self.builder.bitcast(value, target)
        return value

    def emit_coerced_expr(self, expr, target_type):
        value = self.emit_expr(expr)
        if target_type in IFACE_METHODS and getattr(expr, "type", None) != target_type:
            return self.box_iface(value, expr.type, target_type)
        return self.cast_to(value, target_type)

    def box_iface(self, value, source_type, iface_name):
        if not isinstance(source_type, str) or not source_type.startswith("*") or source_type.startswith("?*"):
            raise RuntimeError(f"cannot box {source_type} as iface {iface_name}")
        concrete = source_type[1:]
        vtable = self.get_iface_vtable(iface_name, concrete)
        iface_type = llvm_type(iface_name)
        boxed = ir.Constant(iface_type, ir.Undefined)
        boxed = self.builder.insert_value(boxed, self.builder.bitcast(vtable, I8PTR), [0], name="iface.vtable.ins")
        boxed = self.builder.insert_value(boxed, self.builder.bitcast(value, I8PTR), [1], name="iface.data.ins")
        return boxed

    def get_iface_vtable(self, iface_name, concrete):
        key = (iface_name, concrete)
        if key in self.iface_vtables:
            return self.iface_vtables[key]
        field_types = self.iface_vtable_function_ptr_types(iface_name)
        vt_type = ir.LiteralStructType(field_types)
        values = []
        for mname, param_types, ret_type in IFACE_METHODS[iface_name]:
            thunk = self.get_iface_thunk(iface_name, concrete, mname, param_types, ret_type)
            values.append(thunk.bitcast(field_types[len(values)]))
        glob = ir.GlobalVariable(self.module, vt_type, name=safe_user_ident(f"__nc_iface_{iface_name}_{concrete}_vtable"))
        glob.linkage = "internal"
        glob.global_constant = True
        glob.initializer = ir.Constant.literal_struct(values)
        self.iface_vtables[key] = glob
        return glob

    def get_iface_thunk(self, iface_name, concrete, method_name, param_types, ret_type):
        key = (iface_name, concrete, method_name)
        if key in self.iface_thunks:
            return self.iface_thunks[key]
        fn_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types])
        name = safe_user_ident(f"__nc_iface_{iface_name}_{concrete}_{method_name}_thunk")
        thunk = ir.Function(self.module, fn_type, name=name)
        self.iface_thunks[key] = thunk
        block = thunk.append_basic_block("entry")
        saved_builder, saved_func = self.builder, self.func
        self.builder, self.func = ir.IRBuilder(block), thunk
        receiver_base, path = self.resolve_concrete_method(concrete, method_name)
        method_sym = safe_user_ident(f"{receiver_base}_{method_name}")
        method_fn = self.module.globals[method_sym]
        receiver = self.builder.bitcast(thunk.args[0], llvm_type(f"*{concrete}"), name="iface.receiver")
        current_type = concrete
        for field_name in path:
            field_index = STRUCT_FIELD_INDEX[current_type][field_name]
            zero = ir.Constant(ir.IntType(32), 0)
            receiver = self.builder.gep(receiver, [zero, ir.Constant(ir.IntType(32), field_index)], inbounds=True, name="iface.embed.receiver")
            current_type = STRUCT_FIELDS[current_type][field_index][1]
        receiver = self.builder.bitcast(receiver, llvm_type(f"*{receiver_base}"), name="iface.receiver.cast")
        args = [receiver] + list(thunk.args[1:])
        result = self.builder.call(method_fn, args)
        if ret_type == "void":
            self.builder.ret_void()
        else:
            self.builder.ret(result)
        self.builder, self.func = saved_builder, saved_func
        return thunk

    def resolve_concrete_method(self, concrete, method_name):
        if safe_user_ident(f"{concrete}_{method_name}") in self.module.globals:
            return concrete, []
        for field_name, field_type in STRUCT_EMBEDS.get(concrete, {}).items():
            embed_base = field_type[1:] if field_type.startswith("*") else field_type
            if safe_user_ident(f"{embed_base}_{method_name}") in self.module.globals:
                return embed_base, [field_name]
            try:
                nested_base, nested_path = self.resolve_concrete_method(embed_base, method_name)
                return nested_base, [field_name] + nested_path
            except KeyError:
                pass
        raise KeyError(safe_user_ident(f"{concrete}_{method_name}"))

    def cast_numeric(self, value, from_type, to_type):
        target = llvm_type(to_type)
        if value.type == target:
            return value
        if from_type in INT_TYPES and to_type in INT_TYPES:
            if value.type.width < target.width:
                return self.builder.sext(value, target) if from_type in SIGNED_INT_TYPES else self.builder.zext(value, target)
            if value.type.width > target.width:
                return self.builder.trunc(value, target)
            return value
        if from_type in INT_TYPES and to_type in FLOAT_TYPES:
            return self.builder.sitofp(value, target) if from_type in SIGNED_INT_TYPES else self.builder.uitofp(value, target)
        if from_type in FLOAT_TYPES and to_type in INT_TYPES:
            return self.builder.fptosi(value, target) if to_type in SIGNED_INT_TYPES else self.builder.fptoui(value, target)
        if from_type in FLOAT_TYPES and to_type in FLOAT_TYPES:
            if from_type == "f32" and to_type == "f64":
                return self.builder.fpext(value, target)
            if from_type == "f64" and to_type == "f32":
                return self.builder.fptrunc(value, target)
        raise NotImplementedError(f"LLVM backend cannot cast {from_type} to {to_type}")


def generate_llvm_ir(program, target_name: str | None = None) -> str:
    return LLVMCodegen(get_target(target_name)).generate(program)


def object_from_llvm_ir(llvm_ir: str, target_name: str | None = None) -> bytes:
    target_spec = get_target(target_name)
    binding.initialize_all_targets()
    binding.initialize_all_asmprinters()
    target = binding.Target.from_triple(target_spec.triple)
    tm = target.create_target_machine(reloc="static")
    backing = binding.parse_assembly(llvm_ir)
    backing.verify()
    return tm.emit_object(backing)


def build_llvm_ir(
    llvm_ir: str,
    out_dir: str,
    name: str = "main",
    link_libs: list[str] | None = None,
    support_c_sources: list[str] | None = None,
    target_name: str | None = None,
) -> tuple[str, str, str]:
    target_spec = get_target(target_name)
    os.makedirs(out_dir, exist_ok=True)
    ll_path = os.path.join(out_dir, f"{name}.ll")
    obj_path = os.path.join(out_dir, f"{name}{target_spec.object_ext}")
    exe_path = os.path.join(out_dir, f"{name}{target_spec.exe_ext}")
    ncrt_obj = build_ncrt_obj(out_dir, target_spec.name)
    support_objs = build_support_c_objs(out_dir, support_c_sources, target_spec.name)
    with open(ll_path, "w", encoding="utf-8") as f:
        f.write(llvm_ir)
    with open(obj_path, "wb") as f:
        f.write(object_from_llvm_ir(llvm_ir, target_spec.name))
    link_inputs = [obj_path, ncrt_obj, *support_objs]
    link_cmd = ["gcc", *link_inputs, "-o", exe_path] + [target_spec.resolve_link_lib(lib) for lib in list(link_libs or [])]
    result = subprocess.run(link_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LLVM object link failed:\n{result.stderr}")
    return ll_path, obj_path, exe_path


def run_llvm_ir(
    llvm_ir: str,
    link_libs: list[str] | None = None,
    support_c_sources: list[str] | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    target_name: str | None = None,
) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as tmpdir:
        _ll, _obj, exe = build_llvm_ir(llvm_ir, tmpdir, "out", link_libs, support_c_sources, target_name=target_name)
        run_env = os.environ.copy()
        if env is not None:
            run_env.update(env)
        result = subprocess.run([exe] + list(args or []), capture_output=True, text=True, encoding="utf-8", env=run_env)
        return result.stdout, result.stderr, result.returncode
