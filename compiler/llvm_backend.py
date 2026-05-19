"""Experimental LLVM IR backend for the typed NC AST.

This backend intentionally supports only the small i32/bool subset needed to
validate the LLVM route. It does not replace the C backend.
"""

from llvmlite import ir


I32 = ir.IntType(32)
I1 = ir.IntType(1)
VOID = ir.VoidType()


class LLVMBackendError(NotImplementedError):
    pass


class LLVMGenerator:
    def __init__(self):
        self.module = ir.Module(name="nc_module")
        self.builder: ir.IRBuilder | None = None
        self.functions: dict[str, ir.Function] = {}
        self.locals: list[dict[str, ir.AllocaInstr]] = []
        self.current_function: ir.Function | None = None
        self.print_fn = ir.Function(
            self.module,
            ir.FunctionType(VOID, [I32]),
            name="__nc_print_i32",
        )

    def generate(self, program: "Program") -> str:
        from compiler.ast import FunctionDeclaration

        funcs = [s for s in program.statements if isinstance(s, FunctionDeclaration)]
        for func in funcs:
            self.declare_function(func)
        for func in funcs:
            self.emit_function(func)

        if "main" not in self.functions:
            main_ty = ir.FunctionType(I32, [])
            main = ir.Function(self.module, main_ty, name="main")
            self.functions["main"] = main
            block = main.append_basic_block("entry")
            builder = ir.IRBuilder(block)
            builder.ret(ir.Constant(I32, 0))

        return str(self.module)

    def declare_function(self, func):
        ret_ty = self.nc_type(func.return_type or "void")
        arg_tys = [self.nc_type(t) for _n, t in func.params]
        if func.name == "main":
            ret_ty = I32
            arg_tys = []
        self.functions[func.name] = ir.Function(
            self.module,
            ir.FunctionType(ret_ty, arg_tys),
            name=func.name,
        )

    def emit_function(self, func):
        llvm_func = self.functions[func.name]
        self.current_function = llvm_func
        entry = llvm_func.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry)
        self.locals = [{}]

        for arg, (name, _type) in zip(llvm_func.args, func.params):
            arg.name = name
            slot = self.alloca(name, self.nc_type(_type))
            self.builder.store(arg, slot)
            self.locals[-1][name] = slot

        for i, stmt in enumerate(func.body.statements):
            if self.is_terminated():
                break
            if i == len(func.body.statements) - 1 and (func.return_type or "void") != "void":
                from compiler.ast import ExpressionStatement, If

                if isinstance(stmt, ExpressionStatement):
                    self.builder.ret(self.to_i32(self.emit_expr(stmt.expr)))
                    continue
                if isinstance(stmt, If):
                    self.emit_if_tail_return(stmt)
                    continue
            self.emit_stmt(stmt)

        if not self.is_terminated():
            if func.name == "main":
                self.builder.ret(ir.Constant(I32, 0))
            elif (func.return_type or "void") == "void":
                self.builder.ret_void()
            else:
                self.builder.ret(ir.Constant(self.nc_type(func.return_type), 0))

        self.builder = None
        self.current_function = None
        self.locals = []

    def nc_type(self, nc_type: str):
        if nc_type == "i32":
            return I32
        if nc_type == "bool":
            return I1
        if nc_type == "void":
            return VOID
        raise LLVMBackendError(f"LLVM backend does not support type {nc_type!r}")

    def alloca(self, name: str, typ):
        assert self.builder is not None
        with self.builder.goto_entry_block():
            return self.builder.alloca(typ, name=name)

    def lookup(self, name: str):
        for scope in reversed(self.locals):
            if name in scope:
                return scope[name]
        raise NameError(f"Variable '{name}' not found")

    def push_scope(self):
        self.locals.append({})

    def pop_scope(self):
        self.locals.pop()

    def is_terminated(self):
        return self.builder is None or self.builder.block.is_terminated

    def emit_block(self, block):
        self.push_scope()
        for stmt in block.statements:
            if self.is_terminated():
                break
            self.emit_stmt(stmt)
        self.pop_scope()

    def emit_stmt(self, stmt):
        from compiler.ast import (
            Assignment,
            Block,
            ExpressionStatement,
            FunctionCall,
            Identifier,
            If,
            Return,
            VariableDeclaration,
            While,
        )

        if isinstance(stmt, VariableDeclaration):
            value = self.emit_expr(stmt.initializer)
            typ = self.nc_type(stmt.type)
            slot = self.alloca(stmt.name, typ)
            self.builder.store(self.cast_value(value, typ), slot)
            self.locals[-1][stmt.name] = slot
            return
        if isinstance(stmt, Assignment):
            if not isinstance(stmt.target, Identifier):
                raise LLVMBackendError("LLVM backend only supports assignment to identifiers")
            slot = self.lookup(stmt.target.name)
            value = self.cast_value(self.emit_expr(stmt.expr), slot.type.pointee)
            self.builder.store(value, slot)
            return
        if isinstance(stmt, ExpressionStatement):
            if isinstance(stmt.expr, FunctionCall) and stmt.expr.name == "print":
                self.builder.call(self.print_fn, [self.to_i32(self.emit_expr(stmt.expr.args[0]))])
            else:
                self.emit_expr(stmt.expr)
            return
        if isinstance(stmt, If):
            self.emit_if(stmt)
            return
        if isinstance(stmt, While):
            self.emit_while(stmt)
            return
        if isinstance(stmt, Return):
            if stmt.expr is None:
                self.builder.ret_void()
            else:
                self.builder.ret(self.cast_value(self.emit_expr(stmt.expr), self.current_function.function_type.return_type))
            return
        if isinstance(stmt, Block):
            self.emit_block(stmt)
            return
        raise LLVMBackendError(f"LLVM backend does not support statement {type(stmt).__name__}")

    def emit_if(self, stmt):
        cond = self.to_i1(self.emit_expr(stmt.condition))
        then_bb = self.current_function.append_basic_block("if.then")
        else_bb = self.current_function.append_basic_block("if.else") if stmt.else_block else None
        end_bb = self.current_function.append_basic_block("if.end")
        self.builder.cbranch(cond, then_bb, else_bb or end_bb)

        self.builder.position_at_end(then_bb)
        self.emit_block(stmt.then_block)
        if not self.is_terminated():
            self.builder.branch(end_bb)

        if stmt.else_block:
            self.builder.position_at_end(else_bb)
            self.emit_block(stmt.else_block)
            if not self.is_terminated():
                self.builder.branch(end_bb)

        self.builder.position_at_end(end_bb)

    def emit_if_tail_return(self, stmt):
        cond = self.to_i1(self.emit_expr(stmt.condition))
        then_bb = self.current_function.append_basic_block("ret.then")
        else_bb = self.current_function.append_basic_block("ret.else")
        self.builder.cbranch(cond, then_bb, else_bb)
        self.builder.position_at_end(then_bb)
        self.emit_tail_return_block(stmt.then_block)
        self.builder.position_at_end(else_bb)
        self.emit_tail_return_block(stmt.else_block)

    def emit_tail_return_block(self, block):
        from compiler.ast import ExpressionStatement, If

        self.push_scope()
        body = block.statements
        for stmt in body[:-1]:
            self.emit_stmt(stmt)
        tail = body[-1]
        if isinstance(tail, ExpressionStatement):
            self.builder.ret(self.to_i32(self.emit_expr(tail.expr)))
        elif isinstance(tail, If):
            self.emit_if_tail_return(tail)
        else:
            self.emit_stmt(tail)
        self.pop_scope()

    def emit_while(self, stmt):
        cond_bb = self.current_function.append_basic_block("while.cond")
        body_bb = self.current_function.append_basic_block("while.body")
        end_bb = self.current_function.append_basic_block("while.end")
        self.builder.branch(cond_bb)
        self.builder.position_at_end(cond_bb)
        self.builder.cbranch(self.to_i1(self.emit_expr(stmt.condition)), body_bb, end_bb)
        self.builder.position_at_end(body_bb)
        self.emit_block(stmt.body)
        if not self.is_terminated():
            self.builder.branch(cond_bb)
        self.builder.position_at_end(end_bb)

    def emit_expr(self, node):
        from compiler.ast import BinaryOp, BoolLiteral, FunctionCall, Identifier, IntegerLiteral, UnaryOp

        if isinstance(node, IntegerLiteral):
            return ir.Constant(I32, node.value)
        if isinstance(node, BoolLiteral):
            return ir.Constant(I1, 1 if node.value else 0)
        if isinstance(node, Identifier):
            return self.builder.load(self.lookup(node.name), name=node.name)
        if isinstance(node, UnaryOp):
            value = self.emit_expr(node.operand)
            if node.op == "!":
                return self.builder.not_(self.to_i1(value))
            if node.op == "-":
                return self.builder.neg(self.to_i32(value))
            raise LLVMBackendError(f"LLVM backend does not support unary operator {node.op!r}")
        if isinstance(node, BinaryOp):
            return self.emit_binary(node)
        if isinstance(node, FunctionCall):
            if node.name == "print":
                self.builder.call(self.print_fn, [self.to_i32(self.emit_expr(node.args[0]))])
                return ir.Constant(I32, 0)
            if node.name not in self.functions:
                raise LLVMBackendError(f"LLVM backend does not support builtin/function {node.name!r}")
            callee = self.functions[node.name]
            args = [self.cast_value(self.emit_expr(arg), param.type) for arg, param in zip(node.args, callee.args)]
            return self.builder.call(callee, args)
        raise LLVMBackendError(f"LLVM backend does not support expression {type(node).__name__}")

    def emit_binary(self, node):
        left = self.emit_expr(node.left)
        right = self.emit_expr(node.right)
        op = node.op
        if op == "+":
            return self.builder.add(self.to_i32(left), self.to_i32(right))
        if op == "-":
            return self.builder.sub(self.to_i32(left), self.to_i32(right))
        if op == "*":
            return self.builder.mul(self.to_i32(left), self.to_i32(right))
        if op == "/":
            return self.builder.sdiv(self.to_i32(left), self.to_i32(right))
        if op == "%":
            return self.builder.srem(self.to_i32(left), self.to_i32(right))
        if op in ("==", "!=", "<", ">", "<=", ">="):
            pred = {"==": "==", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">="}[op]
            return self.builder.icmp_signed(pred, self.to_i32(left), self.to_i32(right))
        if op == "&&":
            return self.builder.and_(self.to_i1(left), self.to_i1(right))
        if op == "||":
            return self.builder.or_(self.to_i1(left), self.to_i1(right))
        raise LLVMBackendError(f"LLVM backend does not support binary operator {op!r}")

    def to_i32(self, value):
        if value.type == I32:
            return value
        if value.type == I1:
            return self.builder.zext(value, I32)
        raise LLVMBackendError(f"cannot cast {value.type} to i32")

    def to_i1(self, value):
        if value.type == I1:
            return value
        if value.type == I32:
            return self.builder.icmp_signed("!=", value, ir.Constant(I32, 0))
        raise LLVMBackendError(f"cannot cast {value.type} to i1")

    def cast_value(self, value, typ):
        if value.type == typ:
            return value
        if typ == I32:
            return self.to_i32(value)
        if typ == I1:
            return self.to_i1(value)
        raise LLVMBackendError(f"cannot cast {value.type} to {typ}")


def generate_llvm_ir(program: "Program") -> str:
    return LLVMGenerator().generate(program)
