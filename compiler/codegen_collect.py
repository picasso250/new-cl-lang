"""Pre-generation collection for backend code generation."""

from dataclasses import dataclass, field

from compiler.ast import (
    Assignment, Update, ArrayLiteral, BinaryOp, Block, BlockExpr, Defer, EnumDecl,
    ExternBlock, FieldAccess, ForIn, FunctionCall, FunctionDeclaration, FunctionExpr,
    IfExpr, ImportDecl, IndexAccess, MatchExpr, MethodCall, Return, SliceExpr,
    SliceLiteral, StructDecl, IfaceDecl, StructLiteral, Throw, TryCatch, UnaryOp,
    VariableDeclaration, ExpressionStatement, ForCondition,
    InterpolatedString,
)
from compiler.type_ref import parse_fn_type


@dataclass
class CodegenInputs:
    structs: list = field(default_factory=list)
    enums: list = field(default_factory=list)
    other_funcs: list = field(default_factory=list)
    main_func: object | None = None
    top_stmts: list = field(default_factory=list)
    closures: list = field(default_factory=list)
    slice_types: set[str] = field(default_factory=set)
    fn_types: set[str] = field(default_factory=set)


def collect_codegen_inputs(program) -> CodegenInputs:
    result = CodegenInputs()

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

    def collect_slice_type(nc_type):
        if isinstance(nc_type, str) and nc_type.startswith("[]"):
            result.slice_types.add(nc_type[2:])

    def collect_fn_type(nc_type):
        if parse_fn_type(nc_type) is not None:
            result.fn_types.add(nc_type)

    def collect_expr_types(node):
        collect_slice_type(getattr(node, "type", None))
        collect_fn_type(getattr(node, "type", None))
        if isinstance(node, (ArrayLiteral, SliceLiteral)):
            if isinstance(node, SliceLiteral):
                result.slice_types.add(node.elem_type)
            for elem in node.elements:
                collect_expr_types(elem)
        elif isinstance(node, SliceExpr):
            collect_expr_types(node.array)
            if node.start:
                collect_expr_types(node.start)
            if node.end:
                collect_expr_types(node.end)
        elif isinstance(node, IndexAccess):
            collect_expr_types(node.obj)
            collect_expr_types(node.index)
        elif isinstance(node, BinaryOp):
            collect_expr_types(node.left)
            collect_expr_types(node.right)
        elif isinstance(node, UnaryOp):
            collect_expr_types(node.operand)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                collect_expr_types(arg)
        elif isinstance(node, InterpolatedString):
            for part in node.parts:
                collect_expr_types(part)
        elif isinstance(node, IfExpr):
            collect_expr_types(node.condition)
            for stmt in node.then_block.statements:
                collect_stmt_types(stmt)
            if node.else_block:
                for stmt in node.else_block.statements:
                    collect_stmt_types(stmt)
        elif isinstance(node, MatchExpr):
            collect_expr_types(node.scrutinee)
            for pattern, body in node.arms:
                if pattern is not None:
                    collect_expr_types(pattern)
                collect_expr_types(body)
        elif isinstance(node, BlockExpr):
            for stmt in node.block.statements:
                collect_stmt_types(stmt)
        elif isinstance(node, StructLiteral):
            for _name, value in node.fields:
                collect_expr_types(value)
        elif isinstance(node, FieldAccess):
            collect_expr_types(node.obj)
        elif isinstance(node, MethodCall):
            collect_expr_types(node.obj)
            for arg in node.args:
                collect_expr_types(arg)
        elif isinstance(node, FunctionExpr):
            for _name, param_type in node.params:
                collect_slice_type(param_type)
                collect_fn_type(param_type)
            collect_slice_type(node.return_type)
            collect_fn_type(node.return_type)
            for _name, capture_type in getattr(node, "captures", []):
                collect_slice_type(capture_type)
                collect_fn_type(capture_type)
            for stmt in node.body.statements:
                collect_stmt_types(stmt)

    def collect_stmt_types(stmt):
        collect_slice_type(getattr(stmt, "type", None))
        collect_fn_type(getattr(stmt, "type", None))
        if isinstance(stmt, ExternBlock):
            return
        if isinstance(stmt, VariableDeclaration):
            collect_expr_types(stmt.initializer)
        elif isinstance(stmt, Assignment):
            collect_expr_types(stmt.target)
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, Update):
            collect_expr_types(stmt.target)
        elif isinstance(stmt, ExpressionStatement):
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, ForCondition):
            collect_expr_types(stmt.condition)
            for child in stmt.body.statements:
                collect_stmt_types(child)
        elif isinstance(stmt, ForIn):
            if stmt.start is not None:
                collect_expr_types(stmt.start)
                collect_expr_types(stmt.end)
            else:
                collect_expr_types(stmt.iterable)
            for child in stmt.body.statements:
                collect_stmt_types(child)
        elif isinstance(stmt, FunctionDeclaration):
            collect_slice_type(stmt.return_type)
            collect_fn_type(stmt.return_type)
            for _name, param_type in stmt.params:
                collect_slice_type(param_type)
                collect_fn_type(param_type)
            for child in stmt.body.statements:
                collect_stmt_types(child)
        elif isinstance(stmt, Return) and stmt.expr:
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, TryCatch):
            for child in stmt.try_block.statements + stmt.catch_block.statements:
                collect_stmt_types(child)
        elif isinstance(stmt, Throw):
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, Defer):
            for child in stmt.body.statements:
                collect_stmt_types(child)
        elif isinstance(stmt, Block):
            for child in stmt.statements:
                collect_stmt_types(child)

    collect_top_level(program.statements)
    for stmt in program.statements:
        collect_closure_stmt(stmt)
        collect_stmt_types(stmt)

    result.top_stmts = [
        stmt for stmt in program.statements
        if not isinstance(stmt, (FunctionDeclaration, StructDecl, IfaceDecl, EnumDecl, ImportDecl, ExternBlock))
    ]
    return result
