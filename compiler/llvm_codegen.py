"""LLVM Lite backend v1.

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
    FunctionExpr,
    ForIn, FunctionDeclaration, Identifier, IfExpr, IfaceDecl, ImportDecl, IndexAccess, IntegerLiteral,
    MatchExpr, MethodCall, NilLiteral, Return, SizeOfType, SliceExpr, SliceLiteral, StringLiteral, InterpolatedString, RuneLiteral, StructDecl,
    StructLiteral, Throw, TryCatch, UnaryOp, VariableDeclaration, ForCondition,
)
from compiler.names import safe_user_ident
from compiler.ncrt import build_ncrt_obj
from compiler.type_ref import parse_array_type, parse_fn_type, parse_map_type, parse_slice_type


INT_TYPES = {
    "i8": ir.IntType(8),
    "i16": ir.IntType(16),
    "i32": ir.IntType(32),
    "i64": ir.IntType(64),
    "u8": ir.IntType(8),
    "u16": ir.IntType(16),
    "u32": ir.IntType(32),
    "u64": ir.IntType(64),
    "bool": ir.IntType(1),
    "rune": ir.IntType(32),
}
SIGNED_INT_TYPES = {"i8", "i16", "i32", "i64"}
UNSIGNED_INT_TYPES = {"u8", "u16", "u32", "u64", "bool", "rune"}
FLOAT_TYPES = {"f32": ir.FloatType(), "f64": ir.DoubleType()}
NC_VAL_TAGS = {
    "i8": 1, "i16": 2, "i32": 3, "i64": 4,
    "u8": 5, "u16": 6, "u32": 7, "u64": 8,
    "f32": 9, "f64": 10, "bool": 11, "rune": 12, "str": 13,
}
DEFAULT_TRIPLE = "x86_64-w64-windows-gnu"
I8PTR = ir.IntType(8).as_pointer()
STR_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64)])
MAP_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64), ir.IntType(64), ir.IntType(64)])
NC_VAL_TYPE = ir.LiteralStructType([ir.IntType(32), ir.IntType(64), ir.IntType(64)])
RAW_SLICE_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64), ir.IntType(64)])
STRUCT_TYPES: dict[str, ir.LiteralStructType] = {}
STRUCT_FIELDS: dict[str, list[tuple[str, str]]] = {}
STRUCT_FIELD_INDEX: dict[str, dict[str, int]] = {}
ENUM_VARIANTS: dict[str, dict[str, int]] = {}
IFACE_METHODS: dict[str, list[tuple[str, list[str], str]]] = {}
IFACE_TYPES: dict[str, ir.LiteralStructType] = {}


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
            elif isinstance(stmt, TryCatch):
                collect_top_level(stmt.try_block.statements)
                collect_top_level(stmt.catch_block.statements)
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
        elif isinstance(stmt, TryCatch):
            for child in stmt.try_block.statements + stmt.catch_block.statements:
                collect_closure_stmt(child)
        elif isinstance(stmt, Throw):
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


def llvm_type(nc_type: str | None):
    nc_type = nc_type or "void"
    if nc_type == "void":
        return ir.VoidType()
    if nc_type in INT_TYPES:
        return INT_TYPES[nc_type]
    if nc_type in FLOAT_TYPES:
        return FLOAT_TYPES[nc_type]
    if nc_type == "str":
        return STR_TYPE
    if nc_type == "nc_map" or parse_map_type(nc_type) is not None:
        return MAP_TYPE
    if nc_type in IFACE_METHODS:
        if nc_type not in IFACE_TYPES:
            IFACE_TYPES[nc_type] = ir.LiteralStructType([I8PTR, I8PTR])
        return IFACE_TYPES[nc_type]
    if nc_type in ("*void", "?*void"):
        return I8PTR
    fn_info = parse_fn_type(nc_type)
    if fn_info is not None:
        arg_types, ret_type = fn_info
        call_type = ir.FunctionType(
            llvm_type(ret_type),
            [I8PTR] + [llvm_type(arg_type) for arg_type in arg_types],
        ).as_pointer()
        return ir.LiteralStructType([call_type, I8PTR])
    if isinstance(nc_type, str) and nc_type.startswith("?*"):
        return llvm_type(nc_type[2:]).as_pointer()
    if isinstance(nc_type, str) and nc_type.startswith("*"):
        return llvm_type(nc_type[1:]).as_pointer()
    if nc_type in ENUM_VARIANTS:
        return ir.IntType(32)
    if nc_type in STRUCT_TYPES:
        return STRUCT_TYPES[nc_type]
    slice_info = parse_slice_type(nc_type)
    if slice_info is not None:
        elem_type = slice_info
        return ir.LiteralStructType([
            llvm_type(elem_type).as_pointer(),
            ir.IntType(64),
            ir.IntType(64),
        ])
    array_info = parse_array_type(nc_type)
    if array_info is not None:
        length, elem_type = array_info
        return ir.ArrayType(llvm_type(elem_type), length)
    raise NotImplementedError(f"LLVM backend does not support type: {nc_type}")


class LLVMCodegen:
    def __init__(self):
        self.module = ir.Module(name="nc")
        self.module.triple = DEFAULT_TRIPLE
        self.builder = None
        self.func = None
        self.vars: dict[str, tuple[ir.AllocaInstr, str]] = {}
        self.printf = None
        self.fprintf = None
        self.acrt_iob_func = None
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
        self.read_file_fn = None
        self.write_file_fn = None
        self.fs_exists_fn = None
        self.fs_remove_fn = None
        self.fs_rename_fn = None
        self.fs_mkdir_fn = None
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
        self.ex_active = None
        self.ex_value = None
        self.memcmp = None
        self.fopen = None
        self.fread = None
        self.fwrite = None
        self.fclose = None
        self.fseek = None
        self.ftell = None
        self.sprintf = None
        self.atoi = None
        self.strings: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.fn_decls: dict[str, FunctionDeclaration] = {}
        self.closure_env_types: dict[int, ir.LiteralStructType] = {}
        self.break_stack = []
        self.exception_stack = []
        self.current_return_type = "void"
        self.current_is_main = False
        self.defer_sites = []
        self.defer_stack_slot = None
        self.defer_top_slot = None
        self.emitting_defer = False
        self.current_gc_mark = None
        self.current_return_slot = None
        self.iface_vtables: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.iface_thunks: dict[tuple[str, str, str], ir.Function] = {}

    def generate(self, program) -> str:
        collected = _collect_llvm_inputs(program)
        if collected.top_stmts:
            raise NotImplementedError("LLVM backend v1 does not support top-level statements")
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
        for struct in structs:
            STRUCT_FIELDS[struct.name] = list(struct.fields)
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
        ret = ir.IntType(32) if fn.name == "main" and (fn.return_type or "void") == "void" else llvm_type(fn.return_type)
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        args = [llvm_type(t) for _n, t in all_params]
        self.module.globals[name] = ir.Function(self.module, ir.FunctionType(ret, args), name=name)
        self.fn_decls[name] = fn
        if not fn.receiver_name:
            self.fn_decls[fn.name] = fn

    def function_symbol(self, fn: FunctionDeclaration):
        if getattr(fn, "is_extern", False):
            return fn.name
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
        saved_gc = (self.current_gc_mark, self.current_return_slot)
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        self.init_defer_state()
        self.init_gc_frame(is_main=fn.name == "main")
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        for arg, (param_name, param_type) in zip(llvm_fn.args, all_params):
            arg.name = safe_user_ident(param_name)
            slot = self.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)
            self.root_slots_for_type(slot, param_type)
        if (fn.return_type or "void") != "void":
            self.current_return_slot = self.alloca_at_entry("__nc_ret", llvm_type(fn.return_type))
            self.root_slots_for_type(self.current_return_slot, fn.return_type)

        self.emit_function_body(fn)
        self.defer_sites, self.defer_stack_slot, self.defer_top_slot, self.emitting_defer = saved_defer
        self.current_gc_mark, self.current_return_slot = saved_gc

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
                self.emit_deferred()
                if self.current_return_slot is not None:
                    value = self.builder.load(self.current_return_slot, name="ret.value")
                self.emit_gc_rewind()
                self.builder.ret(value)
            self.current_return_type, self.current_is_main = prev_return_type, prev_is_main
            return
        self.emit_block(body)
        if not self.builder.block.is_terminated:
            self.emit_deferred()
            if is_main and return_type == "void":
                self.emit_gc_rewind()
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
            elif return_type == "void":
                self.emit_gc_rewind()
                self.builder.ret_void()
            else:
                raise RuntimeError(f"missing return in {name}")
        self.current_return_type, self.current_is_main = prev_return_type, prev_is_main

    def alloca_at_entry(self, name, typ):
        return self.builder.alloca(typ, name=name)

    def root_pointer_slot(self, ptr):
        self.ensure_ncrt_runtime()
        self.builder.call(self.gc_push_root_slot, [self.builder.bitcast(ptr, I8PTR)])

    def root_slots_for_type(self, ptr, nc_type):
        if nc_type == "str":
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
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
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
            self.branch_on_exception()
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, IndexAccess) and parse_map_type(stmt.target.obj.type) is not None:
                self.emit_map_set(stmt.target.obj, stmt.target.index, stmt.expr, stmt.op)
                self.branch_on_exception()
                return
            ptr, target_type = self.emit_lvalue(stmt.target)
            rhs = self.emit_coerced_expr(stmt.expr, target_type)
            if stmt.op != "=":
                old = self.builder.load(ptr, name="assign.old")
                rhs = self.emit_binary_values(old, stmt.op[:-1], rhs, target_type)
            self.builder.store(rhs, ptr)
            self.branch_on_exception()
            return
        if isinstance(stmt, Update):
            ptr, target_type = self.emit_lvalue(stmt.target)
            old = self.builder.load(ptr, name="update.old")
            one = ir.Constant(llvm_type(target_type), 1.0 if target_type in FLOAT_TYPES else 1)
            op = "+" if stmt.op == "++" else "-"
            self.builder.store(self.emit_binary_values(old, op, one, target_type), ptr)
            self.branch_on_exception()
            return
        if isinstance(stmt, ExpressionStatement):
            self.emit_expr(stmt.expr)
            self.branch_on_exception()
            return
        if isinstance(stmt, ForCondition):
            self.emit_for_condition(stmt)
            return
        if isinstance(stmt, ForIn):
            self.emit_for_in(stmt)
            return
        if isinstance(stmt, Return):
            if stmt.expr is None:
                self.emit_deferred()
                self.emit_gc_rewind()
                if self.func.function_type.return_type == ir.VoidType():
                    self.builder.ret_void()
                else:
                    self.builder.ret(ir.Constant(self.func.function_type.return_type, 0))
            else:
                value = self.emit_coerced_expr(stmt.expr, self.current_return_type)
                if self.current_return_slot is not None:
                    self.builder.store(value, self.current_return_slot)
                self.emit_deferred()
                if self.current_return_slot is not None:
                    value = self.builder.load(self.current_return_slot, name="ret.value")
                self.emit_gc_rewind()
                self.builder.ret(value)
            return
        if isinstance(stmt, Defer):
            self.emit_defer(stmt)
            return
        if isinstance(stmt, TryCatch):
            self.emit_try_catch(stmt)
            return
        if isinstance(stmt, Throw):
            self.emit_throw(stmt)
            return
        if isinstance(stmt, Break):
            if not self.break_stack:
                raise RuntimeError("break outside loop")
            self.builder.branch(self.break_stack[-1])
            return
        raise NotImplementedError(f"LLVM backend v1 does not support statement: {type(stmt).__name__}")

    def emit_try_catch(self, stmt: TryCatch):
        self.ensure_exception_runtime()
        catch_bb = self.func.append_basic_block("try.catch")
        end_bb = self.func.append_basic_block("try.end")
        self.exception_stack.append(catch_bb)
        for inner in stmt.try_block.statements:
            if self.builder.block.is_terminated:
                break
            self.emit_stmt(inner)
        self.exception_stack.pop()
        if not self.builder.block.is_terminated:
            self.builder.branch(end_bb)

        saved_vars = self.vars.copy()
        self.builder.position_at_end(catch_bb)
        err_slot = self.alloca_at_entry(safe_user_ident(stmt.error_name), STR_TYPE)
        self.vars[stmt.error_name] = (err_slot, "str")
        self.root_slots_for_type(err_slot, "str")
        self.builder.store(self.builder.load(self.ex_value, name="catch.ex"), err_slot)
        self.builder.store(ir.Constant(ir.IntType(1), 0), self.ex_active)
        self.emit_block(stmt.catch_block)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_bb)
        self.vars = saved_vars
        self.builder.position_at_end(end_bb)

    def emit_throw(self, stmt: Throw):
        self.ensure_exception_runtime()
        value = self.cast_to(self.emit_expr(stmt.expr), "str")
        throw_slot = self.alloca_at_entry("__nc_throw_value", STR_TYPE)
        self.root_slots_for_type(throw_slot, "str")
        self.builder.store(value, throw_slot)
        value = self.builder.load(throw_slot, name="throw.value")
        self.builder.store(value, self.ex_value)
        self.builder.store(ir.Constant(ir.IntType(1), 1), self.ex_active)
        self.emit_deferred()
        if self.exception_stack:
            self.builder.branch(self.exception_stack[-1])
            return
        self.return_or_abort_on_exception(run_defer=False)

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

    def branch_on_exception(self):
        if self.builder.block.is_terminated:
            return
        self.ensure_exception_runtime()
        active = self.builder.load(self.ex_active, name="ex.active")
        has_exception = self.builder.icmp_unsigned("!=", active, ir.Constant(ir.IntType(1), 0))
        exception_bb = self.exception_stack[-1] if self.exception_stack else self.func.append_basic_block("ex.propagate")
        cont_bb = self.func.append_basic_block("ex.cont")
        self.builder.cbranch(has_exception, exception_bb, cont_bb)
        if not self.exception_stack:
            self.builder.position_at_end(exception_bb)
            self.return_or_abort_on_exception()
        self.builder.position_at_end(cont_bb)

    def return_or_abort_on_exception(self, run_defer=True):
        if run_defer:
            self.emit_deferred()
        if self.current_is_main:
            self.emit_uncaught_exception()
            self.emit_gc_rewind()
            self.builder.ret(ir.Constant(self.func.function_type.return_type, 1))
            return
        ret_type = self.func.function_type.return_type
        self.emit_gc_rewind()
        if ret_type == ir.VoidType():
            self.builder.ret_void()
        else:
            self.builder.ret(self.default_llvm_value(ret_type))

    def emit_uncaught_exception(self):
        self.ensure_exception_runtime()
        self.ensure_fprintf()
        stderr = self.builder.call(self.acrt_iob_func, [ir.Constant(ir.IntType(32), 2)], name="stderr")
        fmt = self.global_c_string("uncaught: %.*s\n", "fmt_uncaught")
        ex = self.builder.load(self.ex_value, name="uncaught.ex")
        ptr = self.builder.extract_value(ex, 0)
        length64 = self.builder.extract_value(ex, 1)
        length32 = self.builder.trunc(length64, ir.IntType(32))
        self.builder.call(self.fprintf, [stderr, fmt, length32, ptr])

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
            raise NotImplementedError("LLVM backend v1 only supports for i, item in slice")

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
            raise NotImplementedError(f"LLVM backend v1 does not support unary operator {node.op}")
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
        if isinstance(node, SizeOfType):
            return ir.Constant(ir.IntType(64), self.sizeof_type(node.type_name))
        if isinstance(node, MethodCall):
            return self.emit_method_call(node)
        if isinstance(node, FunctionExpr):
            return self.emit_function_expr(node)
        raise NotImplementedError(f"LLVM backend v1 does not support expression: {type(node).__name__}")

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
            raise NotImplementedError(f"LLVM backend v1 cannot slice {source_type}")
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
                raise NotImplementedError(f"LLVM backend v1 cannot index {array_type}")
            _length, elem_type = array_info
            idx = self.cast_to(self.emit_expr(node.index), "i32")
            zero = ir.Constant(ir.IntType(32), 0)
            elem_ptr = self.builder.gep(array_ptr, [zero, idx], inbounds=True, name="idx.ptr")
            return elem_ptr, elem_type
        raise NotImplementedError(f"LLVM backend v1 cannot take lvalue of {type(node).__name__}")

    def emit_binary(self, node: BinaryOp):
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
        raise NotImplementedError(f"LLVM backend v1 does not support binary operator {op}")

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
        raise NotImplementedError(f"LLVM backend v1 does not support float operator {op}")

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
                length64 = self.builder.extract_value(arg, 2)
                return self.builder.trunc(length64, ir.IntType(32))
            raise NotImplementedError(f"LLVM backend v1 cannot take len of {node.args[0].type}")
        if node.name == "cap":
            if len(node.args) != 1:
                raise RuntimeError("cap expects one argument")
            if parse_slice_type(node.args[0].type) is None:
                raise NotImplementedError(f"LLVM backend v1 cannot take cap of {node.args[0].type}")
            arg = self.emit_expr(node.args[0])
            cap64 = self.builder.extract_value(arg, 2)
            return self.builder.trunc(cap64, ir.IntType(32))
        if parse_map_type(node.name) is not None:
            return self.emit_map_new()
        if node.name == "map_has":
            if len(node.args) != 2:
                raise RuntimeError("map_has expects two arguments")
            return self.emit_map_has(node.args[0], node.args[1])
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
                raise NotImplementedError(f"LLVM backend v1 cannot append to {slice_type}")
            return self.emit_append(node.args[0], node.args[1], elem_type)
        if node.name == "fs.read_file":
            if len(node.args) != 1:
                raise RuntimeError("fs.read_file expects one argument")
            return self.emit_read_file(node.args[0])
        if node.name == "fs.write_file":
            if len(node.args) != 2:
                raise RuntimeError("fs.write_file expects two arguments")
            return self.emit_write_file(node.args[0], node.args[1])
        if node.name == "fs.exists":
            if len(node.args) != 1:
                raise RuntimeError("fs.exists expects one argument")
            return self.emit_fs_exists(node.args[0])
        if node.name == "fs.remove":
            if len(node.args) != 1:
                raise RuntimeError("fs.remove expects one argument")
            return self.emit_fs_remove(node.args[0])
        if node.name == "fs.rename":
            if len(node.args) != 2:
                raise RuntimeError("fs.rename expects two arguments")
            return self.emit_fs_rename(node.args[0], node.args[1])
        if node.name == "fs.mkdir":
            if len(node.args) != 1:
                raise RuntimeError("fs.mkdir expects one argument")
            return self.emit_fs_mkdir(node.args[0])
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
            raise NotImplementedError(f"LLVM backend v1 cannot call {node.name}")
        fn_decl = self.fn_decls[node.name]
        fn = self.module.globals[self.function_symbol(fn_decl)]
        coerced_args = [
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ]
        return self.builder.call(fn, coerced_args)

    def emit_function_expr(self, node: FunctionExpr):
        closure_type = llvm_type(node.type)
        fn = self.module.globals[self.closure_symbol(node)]
        env_ptr = self.emit_closure_env(node)
        value = ir.Constant(closure_type, ir.Undefined)
        value = self.builder.insert_value(value, fn.bitcast(closure_type.elements[0]), [0], name="closure.call")
        value = self.builder.insert_value(value, env_ptr, [1], name="closure.env")
        return value

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
            raise NotImplementedError(f"LLVM backend v1 cannot call method {receiver_base}.{node.method}")
        fn = self.module.globals[name]
        fn_decl = self.fn_decls[name]
        args = [self.emit_expr(node.obj)] + [
            self.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ]
        return self.builder.call(fn, args)

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
        raise NotImplementedError(f"LLVM backend v1 cannot print type: {typ}")

    def emit_to_str(self, arg_expr):
        typ = arg_expr.type
        if typ == "str":
            return self.emit_expr(arg_expr)
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
        raise NotImplementedError(f"LLVM backend v1 cannot convert {typ} to str")

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
            raise NotImplementedError(f"LLVM backend v1 cannot copy into {dst_expr.type}")
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
        raise NotImplementedError(f"LLVM backend v1 cannot clear {expr.type}")

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
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_str_cat_out", STR_TYPE)
        left_ptr = self.value_to_stack_ptr(left, STR_TYPE, "__nc_str_cat_left")
        right_ptr = self.value_to_stack_ptr(right, STR_TYPE, "__nc_str_cat_right")
        self.builder.call(self.str_cat_fn, [out, left_ptr, right_ptr])
        return self.builder.load(out, name="str.cat")

    def str_value(self, ptr, length):
        value = ir.Constant(STR_TYPE, ir.Undefined)
        value = self.builder.insert_value(value, ptr, [0], name="str.ptr")
        value = self.builder.insert_value(value, length, [1], name="str.len")
        return value

    def map_value(self, entries, cap, length):
        value = ir.Constant(MAP_TYPE, ir.Undefined)
        value = self.builder.insert_value(value, entries, [0], name="map.entries")
        value = self.builder.insert_value(value, cap, [1], name="map.cap")
        value = self.builder.insert_value(value, length, [2], name="map.len")
        value = self.builder.insert_value(value, ir.Constant(ir.IntType(64), 0), [3], name="map.tombstones")
        return value

    def emit_map_new(self):
        self.ensure_ncrt_runtime()
        slot = self.alloca_at_entry("__nc_map_new", MAP_TYPE)
        self.builder.call(self.map_init_fn, [slot])
        return self.builder.load(slot, name="map.new")

    def map_pointer_for_expr(self, map_expr):
        try:
            map_ptr, map_type = self.emit_lvalue(map_expr)
            if parse_map_type(map_type) is not None:
                return map_ptr
        except NotImplementedError:
            pass
        slot = self.alloca_at_entry("__nc_map_tmp", MAP_TYPE)
        self.builder.store(self.emit_expr(map_expr), slot)
        return slot

    def emit_map_get(self, map_expr, key_expr):
        self.ensure_ncrt_runtime()
        _key_type, value_type = parse_map_type(map_expr.type)
        map_ptr = self.map_pointer_for_expr(map_expr)
        key_val = self.scalar_to_nc_val(self.emit_expr(key_expr), key_expr.type)
        key_ptr = self.value_to_stack_ptr(key_val, NC_VAL_TYPE, "__nc_map_get_key")
        out = self.alloca_at_entry("__nc_map_get_out", NC_VAL_TYPE)
        self.builder.call(self.map_get_fn, [out, map_ptr, key_ptr, ir.Constant(ir.IntType(32), NC_VAL_TAGS[value_type])])
        return self.nc_val_to_scalar(self.builder.load(out, name="map.raw"), value_type)

    def emit_map_has(self, map_expr, key_expr):
        self.ensure_ncrt_runtime()
        map_ptr = self.map_pointer_for_expr(map_expr)
        key = self.scalar_to_nc_val(self.emit_expr(key_expr), key_expr.type)
        key_ptr = self.value_to_stack_ptr(key, NC_VAL_TYPE, "__nc_map_has_key")
        return self.builder.call(self.map_has_fn, [map_ptr, key_ptr], name="map.has")

    def emit_map_delete(self, map_expr, key_expr):
        self.ensure_ncrt_runtime()
        map_ptr = self.map_pointer_for_expr(map_expr)
        key = self.scalar_to_nc_val(self.emit_expr(key_expr), key_expr.type)
        key_ptr = self.value_to_stack_ptr(key, NC_VAL_TYPE, "__nc_map_delete_key")
        self.builder.call(self.map_delete_fn, [map_ptr, key_ptr])
        return ir.Constant(ir.IntType(1), 0)

    def emit_map_set(self, map_expr, key_expr, value_expr, assign_op="="):
        self.ensure_ncrt_runtime()
        map_ptr, map_type = self.emit_lvalue(map_expr)
        map_args = parse_map_type(map_type)
        if map_args is None:
            raise NotImplementedError(f"LLVM backend v1 cannot map-set {map_type}")
        _key_type, value_type = map_args
        key = self.scalar_to_nc_val(self.emit_expr(key_expr), key_expr.type)
        value = self.emit_coerced_expr(value_expr, value_type)
        if assign_op != "=":
            key_ptr_for_get = self.value_to_stack_ptr(key, NC_VAL_TYPE, "__nc_map_get_key")
            old_out = self.alloca_at_entry("__nc_map_old_out", NC_VAL_TYPE)
            self.builder.call(self.map_get_fn, [old_out, map_ptr, key_ptr_for_get, ir.Constant(ir.IntType(32), NC_VAL_TAGS[value_type])])
            old = self.nc_val_to_scalar(self.builder.load(old_out, name="map.old.raw"), value_type)
            if value_type == "str" and assign_op == "+=":
                value = self.emit_str_cat(old, value)
            else:
                value = self.emit_binary_values(old, assign_op[:-1], value, value_type)
        key_ptr = self.value_to_stack_ptr(key, NC_VAL_TYPE, "__nc_map_set_key")
        value_ptr = self.value_to_stack_ptr(self.scalar_to_nc_val(value, value_type), NC_VAL_TYPE, "__nc_map_set_value")
        self.builder.call(self.map_set_fn, [map_ptr, key_ptr, value_ptr])
        return ir.Constant(ir.IntType(1), 0)

    def scalar_to_nc_val(self, value, nc_type: str):
        if nc_type not in NC_VAL_TAGS:
            raise NotImplementedError(f"LLVM backend v1 cannot use {nc_type} as map scalar")
        raw_a = ir.Constant(ir.IntType(64), 0)
        raw_b = ir.Constant(ir.IntType(64), 0)
        if nc_type == "str":
            ptr = self.builder.extract_value(value, 0)
            raw_a = self.builder.ptrtoint(ptr, ir.IntType(64), name="map.str.ptr.int")
            raw_b = self.builder.extract_value(value, 1)
        elif nc_type in FLOAT_TYPES:
            if nc_type == "f32":
                bits32 = self.builder.bitcast(value, ir.IntType(32), name="map.f32.bits")
                raw_a = self.builder.zext(bits32, ir.IntType(64), name="map.f32.bits64")
            else:
                raw_a = self.builder.bitcast(value, ir.IntType(64), name="map.f64.bits")
        else:
            int_value = value
            if int_value.type.width < 64:
                int_value = self.builder.sext(int_value, ir.IntType(64)) if nc_type in SIGNED_INT_TYPES else self.builder.zext(int_value, ir.IntType(64))
            elif int_value.type.width > 64:
                int_value = self.builder.trunc(int_value, ir.IntType(64))
            raw_a = int_value
        out = ir.Constant(NC_VAL_TYPE, ir.Undefined)
        out = self.builder.insert_value(out, ir.Constant(ir.IntType(32), NC_VAL_TAGS[nc_type]), [0], name="map.val.tag")
        out = self.builder.insert_value(out, raw_a, [1], name="map.val.a")
        out = self.builder.insert_value(out, raw_b, [2], name="map.val.b")
        return out

    def nc_val_to_scalar(self, value, nc_type: str):
        raw_a = self.builder.extract_value(value, 1, name="map.val.a")
        raw_b = self.builder.extract_value(value, 2, name="map.val.b")
        if nc_type == "str":
            ptr = self.builder.inttoptr(raw_a, I8PTR, name="map.str.ptr")
            return self.str_value(ptr, raw_b)
        if nc_type == "f32":
            return self.builder.bitcast(self.builder.trunc(raw_a, ir.IntType(32), name="map.f32.bits32"), ir.FloatType(), name="map.f32")
        if nc_type == "f64":
            return self.builder.bitcast(raw_a, ir.DoubleType(), name="map.f64")
        target_type = llvm_type(nc_type)
        if target_type.width < 64:
            return self.builder.trunc(raw_a, target_type, name="map.int.trunc")
        return raw_a

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
            self.acrt_iob_func = ir.Function(
                self.module,
                ir.FunctionType(I8PTR, [ir.IntType(32)]),
                name="__acrt_iob_func",
            )

    def ensure_exception_runtime(self):
        if self.ex_active is None:
            self.ex_active = ir.GlobalVariable(self.module, ir.IntType(1), name="__nc_ex_active")
            self.ex_active.linkage = "internal"
            self.ex_active.initializer = ir.Constant(ir.IntType(1), 0)
            self.ex_value = ir.GlobalVariable(self.module, STR_TYPE, name="__nc_ex_value")
            self.ex_value.linkage = "internal"
            self.ex_value.initializer = self.default_llvm_value(STR_TYPE)

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
            self.read_file_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [str_ptr, I8PTR]), name="__nc_read_file_status")
            self.write_file_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR, str_ptr]), name="__nc_write_file_status")
            self.fs_exists_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR]), name="__nc_fs_exists")
            self.fs_remove_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR]), name="__nc_fs_remove")
            self.fs_rename_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR]), name="__nc_fs_rename")
            self.fs_mkdir_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [I8PTR]), name="__nc_fs_mkdir")
            self.map_init_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer()]), name="__nc_map_init")
            nc_val_ptr = NC_VAL_TYPE.as_pointer()
            self.map_get_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [nc_val_ptr, MAP_TYPE.as_pointer(), nc_val_ptr, ir.IntType(32)]), name="__nc_map_get")
            self.map_set_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), nc_val_ptr, nc_val_ptr]), name="__nc_map_set")
            self.map_has_fn = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [MAP_TYPE.as_pointer(), nc_val_ptr]), name="__nc_map_has")
            self.map_delete_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), nc_val_ptr]), name="__nc_map_delete")
            self.map_clear_fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer()]), name="__nc_map_clear")
            raw_slice_ptr = RAW_SLICE_TYPE.as_pointer()
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
        value = self.cast_to(self.emit_expr(arg_expr), "i32")
        return self.emit_i32_value_to_str(value)

    def emit_i32_value_to_str(self, value):
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_i32_str_out", STR_TYPE)
        self.builder.call(self.i32_to_str_fn, [out, value])
        return self.builder.load(out, name="i32.str")

    def emit_i64_value_to_str(self, value):
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_i64_str_out", STR_TYPE)
        self.builder.call(self.i64_to_str_fn, [out, value])
        return self.builder.load(out, name="i64.str")

    def emit_u64_value_to_str(self, value):
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_u64_str_out", STR_TYPE)
        self.builder.call(self.u64_to_str_fn, [out, value])
        return self.builder.load(out, name="u64.str")

    def emit_rune_value_to_str(self, value):
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_rune_str_out", STR_TYPE)
        self.builder.call(self.rune_to_str_fn, [out, self.cast_to(value, "rune")])
        return self.builder.load(out, name="rune.str")

    def emit_f64_value_to_str(self, value):
        self.ensure_ncrt_runtime()
        out = self.alloca_at_entry("__nc_f64_str_out", STR_TYPE)
        self.builder.call(self.f64_to_str_fn, [out, value])
        return self.builder.load(out, name="f64.str")

    def emit_str_to_i32(self, arg_expr):
        self.ensure_ncrt_runtime()
        value = self.emit_expr(arg_expr)
        return self.builder.call(self.str_to_i32_fn, [self.value_to_stack_ptr(value, STR_TYPE, "__nc_str_to_i32_arg")], name="str.i32")

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
        if nc_type == "void":
            raise NotImplementedError("LLVM backend v1 cannot sizeof void")
        if nc_type in ("i8", "u8", "bool"):
            return 1
        if nc_type in ("i16", "u16"):
            return 2
        if nc_type in ("i32", "u32", "f32", "rune") or nc_type in ENUM_VARIANTS:
            return 4
        if nc_type in ("i64", "u64", "f64"):
            return 8
        if nc_type == "str":
            return 16
        if nc_type == "nc_map" or parse_map_type(nc_type) is not None:
            return 32
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            return 8
        if parse_fn_type(nc_type) is not None:
            return 16
        if nc_type in IFACE_METHODS:
            return 16
        if parse_slice_type(nc_type) is not None:
            return 24
        array_info = parse_array_type(nc_type)
        if array_info is not None:
            length, elem_type = array_info
            return length * self.aligned_sizeof_type(elem_type)
        if nc_type in STRUCT_FIELDS:
            return self.sizeof_fields([field_type for _field_name, field_type in STRUCT_FIELDS[nc_type]])
        raise NotImplementedError(f"LLVM backend v1 cannot sizeof {nc_type}")

    def alignof_type(self, nc_type: str) -> int:
        if nc_type == "void":
            raise NotImplementedError("LLVM backend v1 cannot alignof void")
        if nc_type in ("i8", "u8", "bool"):
            return 1
        if nc_type in ("i16", "u16"):
            return 2
        if nc_type in ("i32", "u32", "f32", "rune") or nc_type in ENUM_VARIANTS:
            return 4
        if nc_type in ("i64", "u64", "f64", "str", "nc_map") or parse_map_type(nc_type) is not None:
            return 8
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            return 8
        if parse_fn_type(nc_type) is not None or nc_type in IFACE_METHODS:
            return 8
        if parse_slice_type(nc_type) is not None:
            return 8
        array_info = parse_array_type(nc_type)
        if array_info is not None:
            _length, elem_type = array_info
            return self.alignof_type(elem_type)
        if nc_type in STRUCT_FIELDS:
            aligns = [self.alignof_type(field_type) for _field_name, field_type in STRUCT_FIELDS[nc_type]]
            return max(aligns, default=1)
        raise NotImplementedError(f"LLVM backend v1 cannot alignof {nc_type}")

    def align_to(self, value: int, alignment: int) -> int:
        return ((value + alignment - 1) // alignment) * alignment

    def aligned_sizeof_type(self, nc_type: str) -> int:
        return self.align_to(self.sizeof_type(nc_type), self.alignof_type(nc_type))

    def sizeof_fields(self, field_types: list[str]) -> int:
        offset = 0
        max_align = 1
        for field_type in field_types:
            align = self.alignof_type(field_type)
            max_align = max(max_align, align)
            offset = self.align_to(offset, align)
            offset += self.sizeof_type(field_type)
        return self.align_to(offset, max_align)

    def ensure_memcmp(self):
        if self.memcmp is None:
            self.memcmp = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR, ir.IntType(64)]),
                name="memcmp",
            )

    def ensure_file_io(self):
        if self.fopen is None:
            file_ptr = I8PTR
            self.fopen = ir.Function(
                self.module,
                ir.FunctionType(file_ptr, [I8PTR, I8PTR]),
                name="fopen",
            )
            self.fread = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(64), [I8PTR, ir.IntType(64), ir.IntType(64), file_ptr]),
                name="fread",
            )
            self.fwrite = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(64), [I8PTR, ir.IntType(64), ir.IntType(64), file_ptr]),
                name="fwrite",
            )
            self.fclose = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [file_ptr]),
                name="fclose",
            )
            self.fseek = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [file_ptr, ir.IntType(32), ir.IntType(32)]),
                name="fseek",
            )
            self.ftell = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [file_ptr]),
                name="ftell",
            )

    def emit_read_file(self, path_expr):
        self.ensure_ncrt_runtime()
        path = self.emit_expr(path_expr)
        path_ptr = self.builder.extract_value(path, 0)
        out = self.alloca_at_entry("__nc_read_file_out", STR_TYPE)
        status = self.builder.call(self.read_file_fn, [out, path_ptr], name="fs.read.status")
        self.raise_fs_error_if_failed(status, "fs.read_file failed")
        return self.builder.load(out, name="read.result")

    def emit_write_file(self, path_expr, content_expr):
        self.ensure_ncrt_runtime()
        path = self.emit_expr(path_expr)
        content = self.emit_expr(content_expr)
        path_ptr = self.builder.extract_value(path, 0)
        content_ptr = self.value_to_stack_ptr(content, STR_TYPE, "__nc_write_file_content")
        status = self.builder.call(self.write_file_fn, [path_ptr, content_ptr], name="fs.write.status")
        self.raise_fs_error_if_failed(status, "fs.write_file failed")
        return ir.Constant(ir.IntType(1), 0)

    def emit_fs_exists(self, path_expr):
        self.ensure_ncrt_runtime()
        path = self.emit_expr(path_expr)
        path_ptr = self.builder.extract_value(path, 0)
        result = self.builder.call(self.fs_exists_fn, [path_ptr], name="fs.exists.i32")
        return self.builder.icmp_signed("!=", result, ir.Constant(ir.IntType(32), 0), name="fs.exists")

    def emit_fs_remove(self, path_expr):
        self.ensure_ncrt_runtime()
        path = self.emit_expr(path_expr)
        path_ptr = self.builder.extract_value(path, 0)
        status = self.builder.call(self.fs_remove_fn, [path_ptr], name="fs.remove.status")
        self.raise_fs_error_if_failed(status, "fs.remove failed")
        return ir.Constant(ir.IntType(1), 0)

    def emit_fs_rename(self, old_path_expr, new_path_expr):
        self.ensure_ncrt_runtime()
        old_path = self.emit_expr(old_path_expr)
        new_path = self.emit_expr(new_path_expr)
        old_path_ptr = self.builder.extract_value(old_path, 0)
        new_path_ptr = self.builder.extract_value(new_path, 0)
        status = self.builder.call(self.fs_rename_fn, [old_path_ptr, new_path_ptr], name="fs.rename.status")
        self.raise_fs_error_if_failed(status, "fs.rename failed")
        return ir.Constant(ir.IntType(1), 0)

    def emit_fs_mkdir(self, path_expr):
        self.ensure_ncrt_runtime()
        path = self.emit_expr(path_expr)
        path_ptr = self.builder.extract_value(path, 0)
        status = self.builder.call(self.fs_mkdir_fn, [path_ptr], name="fs.mkdir.status")
        self.raise_fs_error_if_failed(status, "fs.mkdir failed")
        return ir.Constant(ir.IntType(1), 0)

    def raise_fs_error_if_failed(self, status, message: str):
        self.ensure_exception_runtime()
        failed = self.builder.icmp_signed("!=", status, ir.Constant(ir.IntType(32), 0), name="fs.failed")
        fail_bb = self.func.append_basic_block("fs.fail")
        ok_bb = self.func.append_basic_block("fs.ok")
        self.builder.cbranch(failed, fail_bb, ok_bb)
        self.builder.position_at_end(fail_bb)
        value = ir.Constant.literal_struct([
            self.global_c_string(message, "fs_error"),
            ir.Constant(ir.IntType(64), len(message.encode("utf-8"))),
        ])
        self.builder.store(value, self.ex_value)
        self.builder.store(ir.Constant(ir.IntType(1), 1), self.ex_active)
        self.builder.branch(ok_bb)
        self.builder.position_at_end(ok_bb)

    def emit_str_eq(self, left, right):
        self.ensure_ncrt_runtime()
        fn = (
            ir.Function(self.module, ir.FunctionType(ir.IntType(32), [STR_TYPE.as_pointer(), STR_TYPE.as_pointer()]), name="__nc_str_eq_ptr")
            if "__nc_str_eq_ptr" not in self.module.globals else self.module.globals["__nc_str_eq_ptr"]
        )
        left_ptr = self.value_to_stack_ptr(left, STR_TYPE, "__nc_str_eq_left")
        right_ptr = self.value_to_stack_ptr(right, STR_TYPE, "__nc_str_eq_right")
        eq = self.builder.call(fn, [left_ptr, right_ptr], name="str.eq.i32")
        return self.builder.icmp_signed("!=", eq, ir.Constant(ir.IntType(32), 0), name="str.eq")

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
        method_sym = safe_user_ident(f"{concrete}_{method_name}")
        method_fn = self.module.globals[method_sym]
        receiver = self.builder.bitcast(thunk.args[0], llvm_type(f"*{concrete}"), name="iface.receiver")
        args = [receiver] + list(thunk.args[1:])
        result = self.builder.call(method_fn, args)
        if ret_type == "void":
            self.builder.ret_void()
        else:
            self.builder.ret(result)
        self.builder, self.func = saved_builder, saved_func
        return thunk

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
        raise NotImplementedError(f"LLVM backend v1 cannot cast {from_type} to {to_type}")


def generate_llvm_ir(program) -> str:
    return LLVMCodegen().generate(program)


def object_from_llvm_ir(llvm_ir: str) -> bytes:
    binding.initialize_all_targets()
    binding.initialize_all_asmprinters()
    target = binding.Target.from_triple(DEFAULT_TRIPLE)
    tm = target.create_target_machine(reloc="static")
    backing = binding.parse_assembly(llvm_ir)
    backing.verify()
    return tm.emit_object(backing)


def build_llvm_ir(llvm_ir: str, out_dir: str, name: str = "main", link_libs: list[str] | None = None) -> tuple[str, str, str]:
    os.makedirs(out_dir, exist_ok=True)
    ll_path = os.path.join(out_dir, f"{name}.ll")
    obj_path = os.path.join(out_dir, f"{name}.obj")
    exe_path = os.path.join(out_dir, f"{name}.exe")
    ncrt_obj = build_ncrt_obj(out_dir)
    with open(ll_path, "w", encoding="utf-8") as f:
        f.write(llvm_ir)
    with open(obj_path, "wb") as f:
        f.write(object_from_llvm_ir(llvm_ir))
    link_cmd = ["gcc", obj_path, ncrt_obj, "-o", exe_path] + list(link_libs or [])
    result = subprocess.run(link_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LLVM object link failed:\n{result.stderr}")
    return ll_path, obj_path, exe_path


def run_llvm_ir(llvm_ir: str, link_libs: list[str] | None = None) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as tmpdir:
        _ll, _obj, exe = build_llvm_ir(llvm_ir, tmpdir, "out", link_libs)
        result = subprocess.run([exe], capture_output=True, text=True, encoding="utf-8")
        return result.stdout, result.stderr, result.returncode
