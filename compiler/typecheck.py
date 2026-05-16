"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


def infer_types(program: "Program", symtab: "SymbolTable"):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, If, While, FunctionDeclaration, Return,
        IntegerLiteral, BinaryOp, FunctionCall, Identifier,
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
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                walk_expr(arg)
            # 查符号表中函数名对应的返回类型
            try:
                sym = symtab.lookup(node.name)
                node.type = sym.nc_type
            except NameError:
                node.type = "void"  # 内置函数（如 print）

    def walk_stmts(stmts: list):
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                walk_expr(stmt.initializer)
                stmt.type = stmt.initializer.type
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.expr)
            elif isinstance(stmt, If):
                walk_expr(stmt.condition)
                symtab.push_scope()
                walk_stmts(stmt.then_block.statements)
                symtab.pop_scope()
                if stmt.else_block:
                    symtab.push_scope()
                    walk_stmts(stmt.else_block.statements)
                    symtab.pop_scope()
            elif isinstance(stmt, While):
                walk_expr(stmt.condition)
                symtab.push_scope()
                walk_stmts(stmt.body.statements)
                symtab.pop_scope()
            elif isinstance(stmt, FunctionDeclaration):
                symtab.push_scope()
                for pname, _ptype in stmt.params:
                    # 参数已在 symtab 中，重新声明到当前作用域
                    symtab.declare(pname, _ptype)
                walk_stmts(stmt.body.statements)
                symtab.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
            elif isinstance(stmt, Block):
                symtab.push_scope()
                walk_stmts(stmt.statements)
                symtab.pop_scope()

    walk_stmts(program.statements)
