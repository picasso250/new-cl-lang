"""LLVM Lite backend v1.

This backend is intentionally small: it shares the existing frontend and typed
AST, then lowers a conservative subset to LLVM IR. Unsupported language nodes
fail explicitly so the C backend remains the authority for the full language.
"""

import os
import subprocess
import tempfile

from llvmlite import binding, ir

from compiler.ast import (
    ArrayLiteral, Assignment, BinaryOp, Block, BlockExpr, BoolLiteral, Break,
    ExpressionStatement, EnumDecl, EnumRef, FieldAccess, FloatLiteral, FunctionCall,
    FunctionExpr,
    ForIn, FunctionDeclaration, Identifier, IfExpr, IndexAccess, IntegerLiteral,
    MatchExpr, MethodCall, NilLiteral, Return, SliceExpr, SliceLiteral, StringLiteral, StructDecl,
    StructLiteral, UnaryOp, VariableDeclaration, While,
)
from compiler.c_abi import c_user_ident
from compiler.codegen_collect import collect_codegen_inputs, parse_fn_type


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
}
SIGNED_INT_TYPES = {"i8", "i16", "i32", "i64"}
UNSIGNED_INT_TYPES = {"u8", "u16", "u32", "u64", "bool"}
FLOAT_TYPES = {"f32": ir.FloatType(), "f64": ir.DoubleType()}
DEFAULT_TRIPLE = "x86_64-w64-windows-gnu"
I8PTR = ir.IntType(8).as_pointer()
STR_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64)])
MAP_ENTRY_TYPE = ir.LiteralStructType([STR_TYPE, STR_TYPE])
MAP_TYPE = ir.LiteralStructType([MAP_ENTRY_TYPE.as_pointer(), ir.IntType(64), ir.IntType(64)])
STRUCT_TYPES: dict[str, ir.LiteralStructType] = {}
STRUCT_FIELDS: dict[str, list[tuple[str, str]]] = {}
STRUCT_FIELD_INDEX: dict[str, dict[str, int]] = {}
ENUM_VARIANTS: dict[str, dict[str, int]] = {}


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
    if nc_type == "nc_map":
        return MAP_TYPE
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


def parse_array_type(nc_type: str | None):
    if not isinstance(nc_type, str) or not nc_type.startswith("[") or nc_type.startswith("[]"):
        return None
    end = nc_type.find("]")
    if end < 0:
        return None
    return int(nc_type[1:end]), nc_type[end + 1:]


def parse_slice_type(nc_type: str | None):
    if isinstance(nc_type, str) and nc_type.startswith("[]"):
        return nc_type[2:]
    return None


class LLVMCodegen:
    def __init__(self):
        self.module = ir.Module(name="nc")
        self.module.triple = DEFAULT_TRIPLE
        self.builder = None
        self.func = None
        self.vars: dict[str, tuple[ir.AllocaInstr, str]] = {}
        self.printf = None
        self.malloc = None
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

    def generate(self, program) -> str:
        collected = collect_codegen_inputs(program)
        if collected.top_stmts:
            raise NotImplementedError("LLVM backend v1 does not support top-level statements")
        self.register_enums(collected.enums)
        self.register_structs(collected.structs)
        self.register_closure_envs(collected.closures)

        funcs = collected.other_funcs + ([collected.main_func] if collected.main_func else [])
        for fn in funcs:
            self.declare_function(fn)
        for closure in collected.closures:
            self.declare_closure_function(closure)
        for closure in collected.closures:
            self.emit_closure_function(closure)
        for fn in funcs:
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
        if fn.receiver_name:
            receiver_type = fn.receiver_type.lstrip("*").lstrip("?")
            return c_user_ident(f"{receiver_type}_{fn.name}")
        return c_user_ident(fn.name)

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
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        llvm_fn.args[0].name = "__nc_env"
        env_type = self.closure_env_types[closure.closure_id]
        env_ptr = self.builder.bitcast(llvm_fn.args[0], env_type.as_pointer(), name="closure.env.ptr")
        for i, (capture_name, capture_type) in enumerate(getattr(closure, "captures", [])):
            field_ptr = self.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{c_user_ident(capture_name)}.ptr",
            )
            self.vars[capture_name] = (field_ptr, capture_type)
        for arg, (param_name, param_type) in zip(llvm_fn.args[1:], closure.params):
            arg.name = c_user_ident(param_name)
            slot = self.alloca_at_entry(c_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)
        self.emit_callable_body(closure.body, closure.return_type or "void", f"lambda {closure.closure_id}")
        self.builder, self.func, self.vars = saved_builder, saved_func, saved_vars

    def emit_function(self, fn: FunctionDeclaration):
        llvm_fn = self.module.globals[self.function_symbol(fn)]
        block = llvm_fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        for arg, (param_name, param_type) in zip(llvm_fn.args, all_params):
            arg.name = c_user_ident(param_name)
            slot = self.alloca_at_entry(c_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)

        self.emit_function_body(fn)

    def emit_function_body(self, fn: FunctionDeclaration):
        self.emit_callable_body(fn.body, fn.return_type or "void", f"function {fn.name}", is_main=fn.name == "main")

    def emit_callable_body(self, body: Block, return_type: str, name: str, is_main: bool = False):
        stmts = body.statements
        if return_type != "void" and stmts and isinstance(stmts[-1], ExpressionStatement):
            for stmt in stmts[:-1]:
                self.emit_stmt(stmt)
            if not self.builder.block.is_terminated:
                self.builder.ret(self.cast_to(self.emit_expr(stmts[-1].expr), return_type))
            return
        self.emit_block(body)
        if not self.builder.block.is_terminated:
            if is_main and return_type == "void":
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
            elif return_type == "void":
                self.builder.ret_void()
            else:
                raise RuntimeError(f"missing return in {name}")

    def alloca_at_entry(self, name, typ):
        return self.builder.alloca(typ, name=name)

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
            slot = self.alloca_at_entry(c_user_ident(stmt.name), typ)
            self.vars[stmt.name] = (slot, stmt.type)
            self.builder.store(self.cast_to(self.emit_expr(stmt.initializer), stmt.type), slot)
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, IndexAccess) and stmt.target.obj.type == "nc_map":
                self.emit_map_set(stmt.target.obj, stmt.target.index, stmt.expr)
                return
            ptr, target_type = self.emit_lvalue(stmt.target)
            self.builder.store(self.cast_to(self.emit_expr(stmt.expr), target_type), ptr)
            return
        if isinstance(stmt, ExpressionStatement):
            self.emit_expr(stmt.expr)
            return
        if isinstance(stmt, While):
            self.emit_while(stmt)
            return
        if isinstance(stmt, ForIn):
            self.emit_for_in(stmt)
            return
        if isinstance(stmt, Return):
            if stmt.expr is None:
                if self.func.function_type.return_type == ir.VoidType():
                    self.builder.ret_void()
                else:
                    self.builder.ret(ir.Constant(self.func.function_type.return_type, 0))
            else:
                self.builder.ret(self.cast_to(self.emit_expr(stmt.expr), stmt.expr.type))
            return
        if isinstance(stmt, Break):
            if not self.break_stack:
                raise RuntimeError("break outside loop")
            self.builder.branch(self.break_stack[-1])
            return
        raise NotImplementedError(f"LLVM backend v1 does not support statement: {type(stmt).__name__}")

    def emit_while(self, stmt: While):
        cond_bb = self.func.append_basic_block("while.cond")
        body_bb = self.func.append_basic_block("while.body")
        end_bb = self.func.append_basic_block("while.end")
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
        idx_slot = self.alloca_at_entry(c_user_ident(stmt.index), idx_type)
        self.vars[stmt.index] = (idx_slot, "i32")
        start = self.cast_to(self.emit_expr(stmt.start), "i32")
        end = self.cast_to(self.emit_expr(stmt.end), "i32")
        self.builder.store(start, idx_slot)

        cond_bb = self.func.append_basic_block("for.range.cond")
        body_bb = self.func.append_basic_block("for.range.body")
        end_bb = self.func.append_basic_block("for.range.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        current = self.builder.load(idx_slot, name=c_user_ident(stmt.index))
        self.builder.cbranch(self.builder.icmp_signed("<", current, end), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            current = self.builder.load(idx_slot, name=c_user_ident(stmt.index))
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
        idx_slot = self.alloca_at_entry(c_user_ident(stmt.index), idx_type)
        value_slot = self.alloca_at_entry(c_user_ident(stmt.value), llvm_type(elem_type))
        self.vars[stmt.index] = (idx_slot, "i32")
        self.vars[stmt.value] = (value_slot, elem_type)

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
        current = self.builder.load(idx_slot, name=c_user_ident(stmt.index))
        self.builder.cbranch(self.builder.icmp_signed("<", current, length32), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        elem_ptr = self.builder.gep(ptr, [current], inbounds=True, name="for.slice.elem.ptr")
        self.builder.store(self.builder.load(elem_ptr), value_slot)
        self.break_stack.append(end_bb)
        self.emit_block(stmt.body)
        self.break_stack.pop()
        if not self.builder.block.is_terminated:
            current = self.builder.load(idx_slot, name=c_user_ident(stmt.index))
            next_value = self.builder.add(current, ir.Constant(idx_type, 1))
            self.builder.store(next_value, idx_slot)
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        self.vars = saved_vars

    def emit_expr(self, node):
        if isinstance(node, IntegerLiteral):
            return ir.Constant(llvm_type(node.type), node.value)
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
        if isinstance(node, EnumRef):
            return ir.Constant(ir.IntType(32), ENUM_VARIANTS[node.enum_name][node.variant])
        if isinstance(node, Identifier):
            slot, _typ = self.vars[node.name]
            return self.builder.load(slot, name=c_user_ident(node.name))
        if isinstance(node, StructLiteral):
            return self.emit_struct_literal(node)
        if isinstance(node, FieldAccess):
            ptr, _field_type = self.emit_lvalue(node)
            return self.builder.load(ptr, name="field")
        if isinstance(node, ArrayLiteral):
            value = ir.Constant(llvm_type(node.type), ir.Undefined)
            for i, elem in enumerate(node.elements):
                elem_value = self.cast_to(self.emit_expr(elem), node.elem_type)
                value = self.builder.insert_value(value, elem_value, [i], name="arr.ins")
            return value
        if isinstance(node, SliceLiteral):
            return self.emit_slice_literal(node)
        if isinstance(node, SliceExpr):
            return self.emit_slice_expr(node)
        if isinstance(node, IndexAccess):
            if node.obj.type == "nc_map":
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
            field_value = self.cast_to(self.emit_expr(given[field_name]), field_type)
            value = self.builder.insert_value(value, field_value, [i], name="struct.ins")
        if node.heap:
            ptr = self.malloc_struct(node.name)
            self.builder.store(value, ptr)
            return ptr
        return value

    def malloc_struct(self, struct_name: str):
        self.ensure_malloc()
        size = ir.Constant(ir.IntType(64), self.sizeof_type(struct_name))
        raw = self.builder.call(self.malloc, [size], name="struct.malloc.raw")
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
        dest = self.malloc_array(elem_type, count64)

        cond_bb = self.func.append_basic_block("slice.copy.cond")
        body_bb = self.func.append_basic_block("slice.copy.body")
        end_bb = self.func.append_basic_block("slice.copy.end")
        idx_slot = self.alloca_at_entry("__nc_slice_i", ir.IntType(32))
        self.builder.store(ir.Constant(ir.IntType(32), 0), idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        i = self.builder.load(idx_slot, name="slice.i")
        self.builder.cbranch(self.builder.icmp_signed("<", i, count32), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        source_i = self.builder.add(start, i, name="slice.source.i")
        source_elem_ptr = self.builder.gep(source_ptr, source_indices(source_i), inbounds=True)
        dest_elem_ptr = self.builder.gep(dest, [i], inbounds=True)
        self.builder.store(self.builder.load(source_elem_ptr), dest_elem_ptr)
        next_i = self.builder.add(i, ir.Constant(ir.IntType(32), 1))
        self.builder.store(next_i, idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        return self.slice_value(elem_type, dest, count64, count64)

    def emit_str_slice(self, node: SliceExpr):
        source = self.emit_expr(node.array)
        source_ptr = self.builder.extract_value(source, 0)
        source_len = self.builder.extract_value(source, 1)
        start = self.cast_to(self.emit_expr(node.start), "i32") if node.start else ir.Constant(ir.IntType(32), 0)
        end = self.cast_to(self.emit_expr(node.end), "i32") if node.end else self.builder.trunc(source_len, ir.IntType(32))
        count32 = self.builder.sub(end, start, name="str.slice.count32")
        count64 = self.builder.zext(count32, ir.IntType(64), name="str.slice.count64")
        dest = self.malloc_bytes(count64)

        cond_bb = self.func.append_basic_block("str.slice.copy.cond")
        body_bb = self.func.append_basic_block("str.slice.copy.body")
        end_bb = self.func.append_basic_block("str.slice.copy.end")
        idx_slot = self.alloca_at_entry("__nc_str_slice_i", ir.IntType(32))
        self.builder.store(ir.Constant(ir.IntType(32), 0), idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        i = self.builder.load(idx_slot, name="str.slice.i")
        self.builder.cbranch(self.builder.icmp_signed("<", i, count32), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        source_i = self.builder.add(start, i, name="str.slice.source.i")
        source_elem_ptr = self.builder.gep(source_ptr, [source_i], inbounds=True)
        dest_elem_ptr = self.builder.gep(dest, [i], inbounds=True)
        self.builder.store(self.builder.load(source_elem_ptr), dest_elem_ptr)
        next_i = self.builder.add(i, ir.Constant(ir.IntType(32), 1))
        self.builder.store(next_i, idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        return self.str_value(dest, count64)

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
        if typ in FLOAT_TYPES:
            return self.emit_float_binary(left, node.op, right)
        if node.op == "+":
            return self.builder.add(left, right)
        if node.op == "-":
            return self.builder.sub(left, right)
        if node.op == "*":
            return self.builder.mul(left, right)
        if node.op == "/":
            return self.builder.sdiv(left, right) if typ in SIGNED_INT_TYPES else self.builder.udiv(left, right)
        if node.op == "%":
            return self.builder.srem(left, right) if typ in SIGNED_INT_TYPES else self.builder.urem(left, right)
        if node.op in ("==", "!=", "<", "<=", ">", ">="):
            pred = {
                "==": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">=",
            }[node.op]
            if typ in UNSIGNED_INT_TYPES:
                return self.builder.icmp_unsigned(pred, left, right)
            else:
                return self.builder.icmp_signed(pred, left, right)
        if node.op == "&&":
            return self.builder.and_(self.bool_value(left), self.bool_value(right))
        if node.op == "||":
            return self.builder.or_(self.bool_value(left), self.bool_value(right))
        raise NotImplementedError(f"LLVM backend v1 does not support binary operator {node.op}")

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
        if node.name == "io.println":
            if len(node.args) != 1:
                raise RuntimeError("io.println expects one argument")
            return self.emit_println(node.args[0])
        if getattr(node, "is_closure_call", False):
            closure = self.emit_expr(Identifier(node.name))
            call_ptr = self.builder.extract_value(closure, 0)
            env = self.builder.extract_value(closure, 1)
            args = [env] + [self.emit_expr(arg) for arg in node.args]
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
            if node.args[0].type == "nc_map":
                length64 = self.builder.extract_value(arg, 2)
                return self.builder.trunc(length64, ir.IntType(32))
            raise NotImplementedError(f"LLVM backend v1 cannot take len of {node.args[0].type}")
        if node.name == "map_new":
            return self.emit_map_new()
        if node.name == "map_has":
            if len(node.args) != 2:
                raise RuntimeError("map_has expects two arguments")
            return self.emit_map_has(node.args[0], node.args[1])
        if node.name == "map_get_s":
            if len(node.args) != 2:
                raise RuntimeError("map_get_s expects two arguments")
            return self.emit_map_get(node.args[0], node.args[1])
        if node.name == "map_set_s":
            if len(node.args) != 3:
                raise RuntimeError("map_set_s expects three arguments")
            return self.emit_map_set(node.args[0], node.args[1], node.args[2])
        if node.name == "str":
            if len(node.args) != 1:
                raise RuntimeError("str expects one argument")
            if node.args[0].type == "i32":
                return self.emit_i32_to_str(node.args[0])
            if node.args[0].type == "str":
                return self.emit_expr(node.args[0])
            raise NotImplementedError(f"LLVM backend v1 cannot convert {node.args[0].type} to str")
        if node.name == "append":
            if len(node.args) != 2:
                raise RuntimeError("append expects two arguments")
            slice_type = node.args[0].type
            elem_type = parse_slice_type(slice_type)
            if elem_type is None:
                raise NotImplementedError(f"LLVM backend v1 cannot append to {slice_type}")
            return self.emit_append(node.args[0], node.args[1], elem_type)
        if node.name == "read_file":
            if len(node.args) != 1:
                raise RuntimeError("read_file expects one argument")
            return self.emit_read_file(node.args[0])
        if node.name == "write_file":
            if len(node.args) != 2:
                raise RuntimeError("write_file expects two arguments")
            return self.emit_write_file(node.args[0], node.args[1])
        if node.name == "gc_collect":
            if len(node.args) != 0:
                raise RuntimeError("gc_collect expects no arguments")
            return ir.Constant(ir.IntType(1), 0)
        if node.name == "gc_live":
            if len(node.args) != 0:
                raise RuntimeError("gc_live expects no arguments")
            return self.emit_gc_live()
        if node.name in INT_TYPES or node.name in FLOAT_TYPES:
            if len(node.args) != 1:
                raise RuntimeError(f"{node.name} expects one argument")
            if node.name == "i32" and node.args[0].type == "str":
                return self.emit_str_to_i32(node.args[0])
            return self.cast_numeric(self.emit_expr(node.args[0]), node.args[0].type, node.name)
        if node.name not in self.fn_decls:
            raise NotImplementedError(f"LLVM backend v1 cannot call {node.name}")
        fn = self.module.globals[c_user_ident(node.name)]
        return self.builder.call(fn, [self.emit_expr(arg) for arg in node.args])

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
        size = sum(self.sizeof_type(capture_type) for _name, capture_type in captures)
        raw = self.malloc_bytes(ir.Constant(ir.IntType(64), max(size, 1)))
        env_ptr = self.builder.bitcast(raw, env_type.as_pointer(), name="closure.env.alloc")
        for i, (capture_name, capture_type) in enumerate(captures):
            source_ptr, _source_type = self.vars[capture_name]
            capture_value = self.builder.load(source_ptr, name=f"capture.{c_user_ident(capture_name)}")
            field_ptr = self.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{c_user_ident(capture_name)}.store.ptr",
            )
            self.builder.store(self.cast_to(capture_value, capture_type), field_ptr)
        return self.builder.bitcast(env_ptr, I8PTR, name="closure.env.i8")

    def emit_method_call(self, node: MethodCall):
        obj_type = node.obj.type
        if obj_type.startswith("?*"):
            receiver_base = obj_type[2:]
        elif obj_type.startswith("*"):
            receiver_base = obj_type[1:]
        else:
            receiver_base = obj_type
        name = c_user_ident(f"{receiver_base}_{node.method}")
        if name not in self.module.globals:
            raise NotImplementedError(f"LLVM backend v1 cannot call method {receiver_base}.{node.method}")
        fn = self.module.globals[name]
        args = [self.emit_expr(node.obj)] + [self.emit_expr(arg) for arg in node.args]
        return self.builder.call(fn, args)

    def emit_println(self, arg):
        self.ensure_printf()
        val = self.emit_expr(arg)
        typ = arg.type
        if typ == "str":
            fmt = self.global_c_string("%.*s\n", "fmt_str")
            ptr = self.builder.extract_value(val, 0)
            length64 = self.builder.extract_value(val, 1)
            length32 = self.builder.trunc(length64, ir.IntType(32))
            return self.builder.call(self.printf, [fmt, length32, ptr])
        if typ == "bool":
            true_s = self.global_c_string("true", "bool_true")
            false_s = self.global_c_string("false", "bool_false")
            selected = self.builder.select(self.bool_value(val), true_s, false_s)
            fmt = self.global_c_string("%s\n", "fmt_bool")
            return self.builder.call(self.printf, [fmt, selected])
        if typ in ("f32", "f64"):
            fmt = self.global_c_string("%f\n", "fmt_float")
            if typ == "f32":
                val = self.builder.fpext(val, ir.DoubleType())
            return self.builder.call(self.printf, [fmt, val])
        if typ in INT_TYPES:
            fmt = self.global_c_string("%lld\n", "fmt_int")
            if val.type.width < 64:
                val = self.builder.sext(val, ir.IntType(64)) if typ in SIGNED_INT_TYPES else self.builder.zext(val, ir.IntType(64))
            return self.builder.call(self.printf, [fmt, val])
        raise NotImplementedError(f"LLVM backend v1 cannot print type: {typ}")

    def emit_append(self, slice_expr, elem_expr, elem_type: str):
        source = self.emit_expr(slice_expr)
        source_ptr = self.builder.extract_value(source, 0)
        source_len = self.builder.extract_value(source, 1)
        one64 = ir.Constant(ir.IntType(64), 1)
        new_len = self.builder.add(source_len, one64, name="append.new.len")
        dest = self.malloc_array(elem_type, new_len)

        cond_bb = self.func.append_basic_block("append.copy.cond")
        body_bb = self.func.append_basic_block("append.copy.body")
        end_bb = self.func.append_basic_block("append.copy.end")
        idx_slot = self.alloca_at_entry("__nc_append_i", ir.IntType(64))
        self.builder.store(ir.Constant(ir.IntType(64), 0), idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        i = self.builder.load(idx_slot, name="append.i")
        self.builder.cbranch(self.builder.icmp_unsigned("<", i, source_len), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        source_elem_ptr = self.builder.gep(source_ptr, [i], inbounds=True)
        dest_elem_ptr = self.builder.gep(dest, [i], inbounds=True)
        self.builder.store(self.builder.load(source_elem_ptr), dest_elem_ptr)
        next_i = self.builder.add(i, one64)
        self.builder.store(next_i, idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

        appended_ptr = self.builder.gep(dest, [source_len], inbounds=True)
        self.builder.store(self.cast_to(self.emit_expr(elem_expr), elem_type), appended_ptr)
        return self.slice_value(elem_type, dest, new_len, new_len)

    def emit_str_cat(self, left, right):
        left_ptr = self.builder.extract_value(left, 0)
        left_len = self.builder.extract_value(left, 1)
        right_ptr = self.builder.extract_value(right, 0)
        right_len = self.builder.extract_value(right, 1)
        total_len = self.builder.add(left_len, right_len, name="str.cat.len")
        dest = self.malloc_bytes(total_len)
        self.copy_bytes(dest, ir.Constant(ir.IntType(64), 0), left_ptr, ir.Constant(ir.IntType(64), 0), left_len, "str.cat.left")
        self.copy_bytes(dest, left_len, right_ptr, ir.Constant(ir.IntType(64), 0), right_len, "str.cat.right")
        return self.str_value(dest, total_len)

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
        return value

    def emit_map_new(self):
        cap = ir.Constant(ir.IntType(64), 16)
        entries = self.malloc_map_entries(cap)
        return self.map_value(entries, cap, ir.Constant(ir.IntType(64), 0))

    def malloc_map_entries(self, count):
        self.ensure_malloc()
        size = self.builder.mul(count, ir.Constant(ir.IntType(64), 32), name="map.malloc.size")
        raw = self.builder.call(self.malloc, [size], name="map.malloc.raw")
        return self.builder.bitcast(raw, MAP_ENTRY_TYPE.as_pointer(), name="map.entries.ptr")

    def map_entry_key_ptr(self, entries, idx):
        zero = ir.Constant(ir.IntType(32), 0)
        return self.builder.gep(entries, [idx, zero], inbounds=True, name="map.key.ptr")

    def map_entry_value_ptr(self, entries, idx):
        one = ir.Constant(ir.IntType(32), 1)
        return self.builder.gep(entries, [idx, one], inbounds=True, name="map.value.ptr")

    def emit_map_find_index(self, map_value, key_value, label):
        entries = self.builder.extract_value(map_value, 0)
        length = self.builder.extract_value(map_value, 2)
        result_slot = self.alloca_at_entry(f"__nc_{label}_result", ir.IntType(64))
        idx_slot = self.alloca_at_entry(f"__nc_{label}_i", ir.IntType(64))
        self.builder.store(ir.Constant(ir.IntType(64), -1), result_slot)
        self.builder.store(ir.Constant(ir.IntType(64), 0), idx_slot)

        cond_bb = self.func.append_basic_block(f"{label}.find.cond")
        body_bb = self.func.append_basic_block(f"{label}.find.body")
        hit_bb = self.func.append_basic_block(f"{label}.find.hit")
        step_bb = self.func.append_basic_block(f"{label}.find.step")
        end_bb = self.func.append_basic_block(f"{label}.find.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        i = self.builder.load(idx_slot, name=f"{label}.i")
        self.builder.cbranch(self.builder.icmp_unsigned("<", i, length), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        entry_key = self.builder.load(self.map_entry_key_ptr(entries, i), name=f"{label}.key")
        self.builder.cbranch(self.emit_str_eq(entry_key, key_value), hit_bb, step_bb)
        self.builder.position_at_end(hit_bb)
        self.builder.store(i, result_slot)
        self.builder.branch(end_bb)
        self.builder.position_at_end(step_bb)
        self.builder.store(self.builder.add(i, ir.Constant(ir.IntType(64), 1)), idx_slot)
        self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)
        return self.builder.load(result_slot, name=f"{label}.result")

    def emit_map_get(self, map_expr, key_expr):
        map_value = self.emit_expr(map_expr)
        key = self.emit_expr(key_expr)
        found = self.emit_map_find_index(map_value, key, "map.get")
        has_value = self.builder.icmp_signed("!=", found, ir.Constant(ir.IntType(64), -1))
        found_bb = self.func.append_basic_block("map.get.found")
        empty_bb = self.func.append_basic_block("map.get.empty")
        end_bb = self.func.append_basic_block("map.get.end")
        self.builder.cbranch(has_value, found_bb, empty_bb)

        self.builder.position_at_end(found_bb)
        entries = self.builder.extract_value(map_value, 0)
        value = self.builder.load(self.map_entry_value_ptr(entries, found), name="map.get.value")
        self.builder.branch(end_bb)
        value_incoming = self.builder.block

        self.builder.position_at_end(empty_bb)
        empty = self.str_value(ir.Constant(I8PTR, None), ir.Constant(ir.IntType(64), 0))
        self.builder.branch(end_bb)
        empty_incoming = self.builder.block

        self.builder.position_at_end(end_bb)
        phi = self.builder.phi(STR_TYPE, name="map.get.result")
        phi.add_incoming(value, value_incoming)
        phi.add_incoming(empty, empty_incoming)
        return phi

    def emit_map_has(self, map_expr, key_expr):
        map_value = self.emit_expr(map_expr)
        key = self.emit_expr(key_expr)
        found = self.emit_map_find_index(map_value, key, "map.has")
        has_value = self.builder.icmp_signed("!=", found, ir.Constant(ir.IntType(64), -1))
        return self.builder.zext(has_value, ir.IntType(32), name="map.has.i32")

    def emit_map_set(self, map_expr, key_expr, value_expr):
        map_ptr, map_type = self.emit_lvalue(map_expr)
        if map_type != "nc_map":
            raise NotImplementedError(f"LLVM backend v1 cannot map-set {map_type}")
        map_value = self.builder.load(map_ptr, name="map.set.map")
        key = self.emit_expr(key_expr)
        value = self.emit_expr(value_expr)
        found = self.emit_map_find_index(map_value, key, "map.set")
        has_value = self.builder.icmp_signed("!=", found, ir.Constant(ir.IntType(64), -1))

        update_bb = self.func.append_basic_block("map.set.update")
        append_bb = self.func.append_basic_block("map.set.append")
        end_bb = self.func.append_basic_block("map.set.end")
        self.builder.cbranch(has_value, update_bb, append_bb)

        self.builder.position_at_end(update_bb)
        entries = self.builder.extract_value(map_value, 0)
        self.builder.store(value, self.map_entry_value_ptr(entries, found))
        self.builder.branch(end_bb)

        self.builder.position_at_end(append_bb)
        new_map = self.emit_map_append(map_value, key, value)
        self.builder.store(new_map, map_ptr)
        self.builder.branch(end_bb)

        self.builder.position_at_end(end_bb)
        return ir.Constant(ir.IntType(1), 0)

    def emit_map_append(self, map_value, key, value):
        entries = self.builder.extract_value(map_value, 0)
        cap = self.builder.extract_value(map_value, 1)
        length = self.builder.extract_value(map_value, 2)
        full = self.builder.icmp_unsigned(">=", length, cap)
        grow_bb = self.func.append_basic_block("map.grow")
        keep_bb = self.func.append_basic_block("map.keep")
        copy_bb = self.func.append_basic_block("map.copy")
        end_bb = self.func.append_basic_block("map.grow.end")
        self.builder.cbranch(full, grow_bb, keep_bb)

        self.builder.position_at_end(grow_bb)
        new_cap = self.builder.mul(cap, ir.Constant(ir.IntType(64), 2), name="map.new.cap")
        new_entries = self.malloc_map_entries(new_cap)
        idx_slot = self.alloca_at_entry("__nc_map_copy_i", ir.IntType(64))
        self.builder.store(ir.Constant(ir.IntType(64), 0), idx_slot)
        self.builder.branch(copy_bb)

        self.builder.position_at_end(copy_bb)
        i = self.builder.load(idx_slot, name="map.copy.i")
        copy_body_bb = self.func.append_basic_block("map.copy.body")
        copy_done_bb = self.func.append_basic_block("map.copy.done")
        self.builder.cbranch(self.builder.icmp_unsigned("<", i, length), copy_body_bb, copy_done_bb)
        self.builder.position_at_end(copy_body_bb)
        old_entry = self.builder.load(self.builder.gep(entries, [i], inbounds=True), name="map.old.entry")
        self.builder.store(old_entry, self.builder.gep(new_entries, [i], inbounds=True))
        self.builder.store(self.builder.add(i, ir.Constant(ir.IntType(64), 1)), idx_slot)
        self.builder.branch(copy_bb)
        self.builder.position_at_end(copy_done_bb)
        self.builder.branch(end_bb)
        grow_incoming = self.builder.block

        self.builder.position_at_end(keep_bb)
        self.builder.branch(end_bb)
        keep_incoming = self.builder.block

        self.builder.position_at_end(end_bb)
        entries_phi = self.builder.phi(MAP_ENTRY_TYPE.as_pointer(), name="map.entries.active")
        cap_phi = self.builder.phi(ir.IntType(64), name="map.cap.active")
        entries_phi.add_incoming(new_entries, grow_incoming)
        entries_phi.add_incoming(entries, keep_incoming)
        cap_phi.add_incoming(new_cap, grow_incoming)
        cap_phi.add_incoming(cap, keep_incoming)

        self.builder.store(key, self.map_entry_key_ptr(entries_phi, length))
        self.builder.store(value, self.map_entry_value_ptr(entries_phi, length))
        new_len = self.builder.add(length, ir.Constant(ir.IntType(64), 1), name="map.len.next")
        return self.map_value(entries_phi, cap_phi, new_len)

    def ensure_printf(self):
        if self.printf is None:
            i8ptr = ir.IntType(8).as_pointer()
            self.printf = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [i8ptr], var_arg=True), name="printf")

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

    def malloc_array(self, elem_type: str, count):
        self.ensure_malloc()
        elem_size = ir.Constant(ir.IntType(64), self.sizeof_type(elem_type))
        size = self.builder.mul(count, elem_size, name="malloc.size")
        raw = self.builder.call(self.malloc, [size], name="malloc.raw")
        return self.builder.bitcast(raw, llvm_type(elem_type).as_pointer(), name="malloc.typed")

    def malloc_bytes(self, count):
        self.ensure_malloc()
        return self.builder.call(self.malloc, [count], name="malloc.bytes")

    def emit_i32_to_str(self, arg_expr):
        self.ensure_sprintf()
        buf = self.malloc_bytes(ir.Constant(ir.IntType(64), 24))
        fmt = self.global_c_string("%d", "fmt_i32_to_str")
        value = self.cast_to(self.emit_expr(arg_expr), "i32")
        length = self.builder.call(self.sprintf, [buf, fmt, value], name="i32.str.len")
        length64 = self.builder.sext(length, ir.IntType(64), name="i32.str.len64")
        return self.str_value(buf, length64)

    def emit_str_to_i32(self, arg_expr):
        self.ensure_atoi()
        value = self.emit_expr(arg_expr)
        ptr = self.builder.extract_value(value, 0)
        return self.builder.call(self.atoi, [ptr], name="str.i32")

    def emit_gc_live(self):
        self.ensure_printf()
        fmt = self.global_c_string("%d\n", "fmt_gc_live")
        zero = ir.Constant(ir.IntType(32), 0)
        self.builder.call(self.printf, [fmt, zero])
        return zero

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
        if nc_type in ("i8", "u8", "bool"):
            return 1
        if nc_type in ("i16", "u16"):
            return 2
        if nc_type in ("i32", "u32", "f32") or nc_type in ENUM_VARIANTS:
            return 4
        if nc_type in ("i64", "u64", "f64"):
            return 8
        if nc_type == "str":
            return 16
        if nc_type == "nc_map":
            return 24
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            return 8
        if parse_fn_type(nc_type) is not None:
            return 16
        if parse_slice_type(nc_type) is not None:
            return 24
        array_info = parse_array_type(nc_type)
        if array_info is not None:
            length, elem_type = array_info
            return length * self.sizeof_type(elem_type)
        if nc_type in STRUCT_FIELDS:
            return sum(self.sizeof_type(field_type) for _field_name, field_type in STRUCT_FIELDS[nc_type])
        raise NotImplementedError(f"LLVM backend v1 cannot sizeof {nc_type}")

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
        self.ensure_file_io()
        path = self.emit_expr(path_expr)
        path_ptr = self.builder.extract_value(path, 0)
        mode = self.global_c_string("rb", "file_mode")
        fp = self.builder.call(self.fopen, [path_ptr, mode], name="read.fp")
        fp_is_null = self.builder.icmp_unsigned("==", fp, ir.Constant(I8PTR, None))

        open_bb = self.func.append_basic_block("read.open")
        empty_bb = self.func.append_basic_block("read.empty")
        end_bb = self.func.append_basic_block("read.end")
        self.builder.cbranch(fp_is_null, empty_bb, open_bb)

        self.builder.position_at_end(empty_bb)
        empty_value = self.str_value(ir.Constant(I8PTR, None), ir.Constant(ir.IntType(64), 0))
        self.builder.branch(end_bb)
        empty_incoming = self.builder.block

        self.builder.position_at_end(open_bb)
        self.builder.call(self.fseek, [fp, ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 2)])
        len32 = self.builder.call(self.ftell, [fp], name="read.len32")
        self.builder.call(self.fseek, [fp, ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)])
        len64 = self.builder.zext(len32, ir.IntType(64), name="read.len64")
        alloc_len = self.builder.add(len64, ir.Constant(ir.IntType(64), 1), name="read.alloc.len")
        buf = self.malloc_bytes(alloc_len)
        self.builder.call(self.fread, [buf, ir.Constant(ir.IntType(64), 1), len64, fp])
        nul_ptr = self.builder.gep(buf, [len64], inbounds=True)
        self.builder.store(ir.Constant(ir.IntType(8), 0), nul_ptr)
        self.builder.call(self.fclose, [fp])
        file_value = self.str_value(buf, len64)
        self.builder.branch(end_bb)
        file_incoming = self.builder.block

        self.builder.position_at_end(end_bb)
        phi = self.builder.phi(STR_TYPE, name="read.result")
        phi.add_incoming(empty_value, empty_incoming)
        phi.add_incoming(file_value, file_incoming)
        return phi

    def emit_write_file(self, path_expr, content_expr):
        self.ensure_file_io()
        path = self.emit_expr(path_expr)
        content = self.emit_expr(content_expr)
        path_ptr = self.builder.extract_value(path, 0)
        mode = self.global_c_string("wb", "file_mode")
        fp = self.builder.call(self.fopen, [path_ptr, mode], name="write.fp")
        fp_is_null = self.builder.icmp_unsigned("==", fp, ir.Constant(I8PTR, None))

        body_bb = self.func.append_basic_block("write.body")
        end_bb = self.func.append_basic_block("write.end")
        self.builder.cbranch(fp_is_null, end_bb, body_bb)
        self.builder.position_at_end(body_bb)
        ptr = self.builder.extract_value(content, 0)
        length = self.builder.extract_value(content, 1)
        self.builder.call(self.fwrite, [ptr, ir.Constant(ir.IntType(64), 1), length, fp])
        self.builder.call(self.fclose, [fp])
        self.builder.branch(end_bb)
        self.builder.position_at_end(end_bb)
        return ir.Constant(ir.IntType(1), 0)

    def emit_str_eq(self, left, right):
        self.ensure_memcmp()
        left_ptr = self.builder.extract_value(left, 0)
        left_len = self.builder.extract_value(left, 1)
        right_ptr = self.builder.extract_value(right, 0)
        right_len = self.builder.extract_value(right, 1)
        len_eq = self.builder.icmp_unsigned("==", left_len, right_len)
        cmp_val = self.builder.call(self.memcmp, [left_ptr, right_ptr, left_len])
        bytes_eq = self.builder.icmp_signed("==", cmp_val, ir.Constant(ir.IntType(32), 0))
        return self.builder.and_(len_eq, bytes_eq)

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


def build_llvm_ir(llvm_ir: str, out_dir: str, name: str = "main") -> tuple[str, str, str]:
    os.makedirs(out_dir, exist_ok=True)
    ll_path = os.path.join(out_dir, f"{name}.ll")
    obj_path = os.path.join(out_dir, f"{name}.obj")
    exe_path = os.path.join(out_dir, f"{name}.exe")
    with open(ll_path, "w", encoding="utf-8") as f:
        f.write(llvm_ir)
    with open(obj_path, "wb") as f:
        f.write(object_from_llvm_ir(llvm_ir))
    result = subprocess.run(["gcc", obj_path, "-o", exe_path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LLVM object link failed:\n{result.stderr}")
    return ll_path, obj_path, exe_path


def run_llvm_ir(llvm_ir: str) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as tmpdir:
        _ll, _obj, exe = build_llvm_ir(llvm_ir, tmpdir, "out")
        result = subprocess.run([exe], capture_output=True, text=True)
        return result.stdout, result.stderr, result.returncode
