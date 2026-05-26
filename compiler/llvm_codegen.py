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
    Assignment, BinaryOp, Block, BoolLiteral, ExpressionStatement, FloatLiteral,
    FunctionCall, FunctionDeclaration, Identifier, IfExpr, IntegerLiteral,
    Return, StringLiteral, UnaryOp, VariableDeclaration, While,
)
from compiler.c_abi import c_user_ident
from compiler.codegen_collect import collect_codegen_inputs


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
    raise NotImplementedError(f"LLVM backend does not support type: {nc_type}")


class LLVMCodegen:
    def __init__(self):
        self.module = ir.Module(name="nc")
        self.module.triple = DEFAULT_TRIPLE
        self.builder = None
        self.func = None
        self.vars: dict[str, tuple[ir.AllocaInstr, str]] = {}
        self.printf = None
        self.memcmp = None
        self.strings: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.fn_decls: dict[str, FunctionDeclaration] = {}

    def generate(self, program) -> str:
        collected = collect_codegen_inputs(program)
        if collected.top_stmts:
            raise NotImplementedError("LLVM backend v1 does not support top-level statements")
        unsupported = collected.structs or collected.enums or collected.closures
        if unsupported:
            raise NotImplementedError("LLVM backend v1 does not support structs, enums, or closures")

        funcs = collected.other_funcs + ([collected.main_func] if collected.main_func else [])
        for fn in funcs:
            self.declare_function(fn)
        for fn in funcs:
            self.emit_function(fn)
        return str(self.module)

    def declare_function(self, fn: FunctionDeclaration):
        if fn.receiver_name:
            raise NotImplementedError("LLVM backend v1 does not support methods")
        name = c_user_ident(fn.name)
        ret = ir.IntType(32) if fn.name == "main" and (fn.return_type or "void") == "void" else llvm_type(fn.return_type)
        args = [llvm_type(t) for _n, t in fn.params]
        self.module.globals[name] = ir.Function(self.module, ir.FunctionType(ret, args), name=name)
        self.fn_decls[fn.name] = fn

    def emit_function(self, fn: FunctionDeclaration):
        llvm_fn = self.module.globals[c_user_ident(fn.name)]
        block = llvm_fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.func = llvm_fn
        self.vars = {}
        for arg, (param_name, param_type) in zip(llvm_fn.args, fn.params):
            arg.name = c_user_ident(param_name)
            slot = self.alloca_at_entry(c_user_ident(param_name), llvm_type(param_type))
            self.builder.store(arg, slot)
            self.vars[param_name] = (slot, param_type)

        self.emit_block(fn.body)
        if not self.builder.block.is_terminated:
            if fn.name == "main" and (fn.return_type or "void") == "void":
                self.builder.ret(ir.Constant(ir.IntType(32), 0))
            elif (fn.return_type or "void") == "void":
                self.builder.ret_void()
            else:
                raise RuntimeError(f"missing return in function {fn.name}")

    def alloca_at_entry(self, name, typ):
        return self.builder.alloca(typ, name=name)

    def emit_block(self, block: Block):
        for stmt in block.statements:
            self.emit_stmt(stmt)

    def emit_stmt(self, stmt):
        if isinstance(stmt, VariableDeclaration):
            typ = llvm_type(stmt.type)
            slot = self.alloca_at_entry(c_user_ident(stmt.name), typ)
            self.vars[stmt.name] = (slot, stmt.type)
            self.builder.store(self.cast_to(self.emit_expr(stmt.initializer), stmt.type), slot)
            return
        if isinstance(stmt, Assignment):
            if not isinstance(stmt.target, Identifier):
                raise NotImplementedError("LLVM backend v1 only supports identifier assignment")
            slot, target_type = self.vars[stmt.target.name]
            self.builder.store(self.cast_to(self.emit_expr(stmt.expr), target_type), slot)
            return
        if isinstance(stmt, ExpressionStatement):
            self.emit_expr(stmt.expr)
            return
        if isinstance(stmt, While):
            self.emit_while(stmt)
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
        raise NotImplementedError(f"LLVM backend v1 does not support statement: {type(stmt).__name__}")

    def emit_while(self, stmt: While):
        cond_bb = self.func.append_basic_block("while.cond")
        body_bb = self.func.append_basic_block("while.body")
        end_bb = self.func.append_basic_block("while.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        self.builder.cbranch(self.bool_value(self.emit_expr(stmt.condition)), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        self.emit_block(stmt.body)
        if not self.builder.block.is_terminated:
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def emit_expr(self, node):
        if isinstance(node, IntegerLiteral):
            return ir.Constant(llvm_type(node.type), node.value)
        if isinstance(node, FloatLiteral):
            return ir.Constant(llvm_type(node.type), float(node.value))
        if isinstance(node, BoolLiteral):
            return ir.Constant(ir.IntType(1), 1 if node.value else 0)
        if isinstance(node, StringLiteral):
            ptr = self.global_c_string(node.value, "str_lit")
            return ir.Constant.literal_struct([
                ptr,
                ir.Constant(ir.IntType(64), len(node.value.encode("utf-8"))),
            ])
        if isinstance(node, Identifier):
            slot, _typ = self.vars[node.name]
            return self.builder.load(slot, name=c_user_ident(node.name))
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
        if isinstance(node, FunctionCall):
            return self.emit_call(node)
        raise NotImplementedError(f"LLVM backend v1 does not support expression: {type(node).__name__}")

    def emit_binary(self, node: BinaryOp):
        left = self.emit_expr(node.left)
        right = self.emit_expr(node.right)
        typ = node.left.type
        if typ == "str" and node.op in ("==", "!="):
            eq = self.emit_str_eq(left, right)
            if node.op == "!=":
                return self.builder.not_(eq)
            return eq
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
        if node.name == "len":
            if len(node.args) != 1:
                raise RuntimeError("len expects one argument")
            arg = self.emit_expr(node.args[0])
            if node.args[0].type == "str":
                length64 = self.builder.extract_value(arg, 1)
                return self.builder.trunc(length64, ir.IntType(32))
            raise NotImplementedError(f"LLVM backend v1 cannot take len of {node.args[0].type}")
        if node.name in INT_TYPES or node.name in FLOAT_TYPES:
            if len(node.args) != 1:
                raise RuntimeError(f"{node.name} expects one argument")
            return self.cast_numeric(self.emit_expr(node.args[0]), node.args[0].type, node.name)
        if node.name not in self.fn_decls:
            raise NotImplementedError(f"LLVM backend v1 cannot call {node.name}")
        fn = self.module.globals[c_user_ident(node.name)]
        return self.builder.call(fn, [self.emit_expr(arg) for arg in node.args])

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

    def ensure_printf(self):
        if self.printf is None:
            i8ptr = ir.IntType(8).as_pointer()
            self.printf = ir.Function(self.module, ir.FunctionType(ir.IntType(32), [i8ptr], var_arg=True), name="printf")

    def ensure_memcmp(self):
        if self.memcmp is None:
            self.memcmp = ir.Function(
                self.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR, ir.IntType(64)]),
                name="memcmp",
            )

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
