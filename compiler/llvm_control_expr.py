from llvmlite import ir

from compiler.ast import Block, BlockExpr, ExpressionStatement, IfExpr, MatchExpr
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import FLOAT_TYPES, llvm_type


class ControlExprEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_block_expr(self, node: BlockExpr):
        saved_vars = self.ctx.vars.copy()
        try:
            return self.emit_block_value(node.block)
        finally:
            self.ctx.vars = saved_vars

    def emit_if_expr(self, node: IfExpr):
        cond = self.ctx.bool_value(self.ctx.emit_expr(node.condition))
        then_bb = self.ctx.func.append_basic_block("if.then")
        else_bb = self.ctx.func.append_basic_block("if.else")
        end_bb = self.ctx.func.append_basic_block("if.end")
        self.ctx.builder.cbranch(cond, then_bb, else_bb)
        self.ctx.builder.position_at_end(then_bb)
        then_val = self.emit_block_value(node.then_block)
        then_block = self.ctx.builder.block
        if not self.ctx.builder.block.is_terminated:
            self.ctx.builder.branch(end_bb)
        self.ctx.builder.position_at_end(else_bb)
        else_val = self.emit_block_value(node.else_block) if node.else_block else None
        else_block = self.ctx.builder.block
        if not self.ctx.builder.block.is_terminated:
            self.ctx.builder.branch(end_bb)
        self.ctx.builder.position_at_end(end_bb)
        if node.type == "void":
            return ir.Constant(ir.IntType(1), 0)
        phi = self.ctx.builder.phi(llvm_type(node.type))
        phi.add_incoming(self.ctx.cast_to(then_val, node.type), then_block)
        phi.add_incoming(self.ctx.cast_to(else_val, node.type), else_block)
        return phi

    def emit_match_expr(self, node: MatchExpr):
        scrutinee = self.ctx.emit_expr(node.scrutinee)
        end_bb = self.ctx.func.append_basic_block("match.end")
        incoming = []

        for i, (pattern, body) in enumerate(node.arms):
            body_bb = self.ctx.func.append_basic_block(f"match.arm.{i}")
            next_bb = self.ctx.func.append_basic_block(f"match.next.{i}")
            if pattern is None:
                self.ctx.builder.branch(body_bb)
            else:
                cond = self.match_condition(scrutinee, node.scrutinee.type, pattern)
                self.ctx.builder.cbranch(cond, body_bb, next_bb)
            self.ctx.builder.position_at_end(body_bb)
            body_val = self.ctx.emit_expr(body)
            body_block = self.ctx.builder.block
            if not self.ctx.builder.block.is_terminated:
                self.ctx.builder.branch(end_bb)
            incoming.append((body_val, body_block))
            self.ctx.builder.position_at_end(next_bb)

        if not self.ctx.builder.block.is_terminated:
            self.ctx.builder.unreachable()
        self.ctx.builder.position_at_end(end_bb)
        if node.type == "void":
            return ir.Constant(ir.IntType(1), 0)
        phi = self.ctx.builder.phi(llvm_type(node.type))
        for value, block in incoming:
            phi.add_incoming(self.ctx.cast_to(value, node.type), block)
        return phi

    def match_condition(self, scrutinee, scrutinee_type, pattern):
        pattern_value = self.ctx.emit_expr(pattern)
        if scrutinee_type == "error":
            message = self.ctx.builder.extract_value(scrutinee, 0, name="error.match.message")
            return self.ctx.emit_str_eq(message, pattern_value)
        if scrutinee_type == "str":
            return self.ctx.emit_str_eq(scrutinee, pattern_value)
        if scrutinee_type in FLOAT_TYPES:
            return self.ctx.builder.fcmp_ordered("==", scrutinee, pattern_value)
        return self.ctx.builder.icmp_signed("==", scrutinee, pattern_value)

    def emit_block_value(self, block: Block):
        if not block.statements:
            return ir.Constant(ir.IntType(1), 0)
        *prefix, tail = block.statements
        for stmt in prefix:
            self.ctx.emit_stmt(stmt)
        if isinstance(tail, ExpressionStatement):
            return self.ctx.emit_expr(tail.expr)
        self.ctx.emit_stmt(tail)
        return ir.Constant(ir.IntType(1), 0)
