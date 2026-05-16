"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
目前所有值均为 i32，无报错路径。
"""


def infer_types(program: "Program", symtab: "SymbolTable"):
    """Pass 2: 标注 Program 中所有表达式的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, IntegerLiteral, BinaryOp, FunctionCall, Identifier,
    )

    def walk_expr(node):
        if isinstance(node, IntegerLiteral):
            node.type = "i32"
        elif isinstance(node, Identifier):
            sym = symtab.lookup(node.name)
            node.type = sym.nc_type
        elif isinstance(node, BinaryOp):
            walk_expr(node.left)
            walk_expr(node.right)
            # 简单规则：两边同类型，结果即该类型
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                walk_expr(arg)
            node.type = "void"
        else:
            raise NotImplementedError(f"typecheck for {type(node).__name__}")

    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration):
            walk_expr(stmt.initializer)
            stmt.type = stmt.initializer.type
        elif isinstance(stmt, ExpressionStatement):
            walk_expr(stmt.expr)
        elif isinstance(stmt, Assignment):
            walk_expr(stmt.expr)
