"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


def infer_types(program: "Program", symtab: "SymbolTable"):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, If, While, FunctionDeclaration, Return,
        StructDecl, StructLiteral, FieldAccess,
        EnumDecl, EnumRef, Switch, ForIn,
        IntegerLiteral, StringLiteral, BinaryOp, UnaryOp, FunctionCall, Identifier,
        ArrayLiteral, IndexAccess, SliceExpr
    )

    def walk_expr(node):
        if isinstance(node, IntegerLiteral):
            node.type = "i32"
        elif isinstance(node, StringLiteral):
            node.type = "str"
        elif isinstance(node, Identifier):
            sym = symtab.lookup(node.name)
            node.type = sym.nc_type
        elif isinstance(node, UnaryOp):
            walk_expr(node.operand)
            node.type = node.operand.type
        elif isinstance(node, BinaryOp):
            walk_expr(node.left)
            walk_expr(node.right)
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                walk_expr(arg)
            # 内置函数
            if node.name == "read_file":
                node.type = "str"
                return
            if node.name == "write_file":
                node.type = "void"
                return
            if node.name == "append":
                node.type = node.args[0].type if node.args else "i32"
                return
            try:
                sym = symtab.lookup(node.name)
                node.type = sym.nc_type
            except NameError:
                node.type = "void"
        elif isinstance(node, EnumRef):
            # 验证 enum 类型存在
            symtab.lookup(node.enum_name)
            node.type = node.enum_name
        elif isinstance(node, StructLiteral):
            node.type = node.name  # 类型名即 struct 名
            for _fname, fval in node.fields:
                walk_expr(fval)
        elif isinstance(node, FieldAccess):
            walk_expr(node.obj)
            obj_type = node.obj.type
            fields = symtab.lookup_struct(obj_type)
            node.type = fields.get(node.field, "i32")
        elif isinstance(node, ArrayLiteral):
            for elem in node.elements:
                walk_expr(elem)
            node.type = node.elem_type if node.elements else "i32"
        elif isinstance(node, IndexAccess):
            walk_expr(node.obj)
            walk_expr(node.index)
            node.type = node.obj.type
        elif isinstance(node, SliceExpr):
            walk_expr(node.array)
            if node.start:
                walk_expr(node.start)
            if node.end:
                walk_expr(node.end)
            node.type = node.array.type

    def walk_stmts(stmts: list):
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                walk_expr(stmt.initializer)
                stmt.type = stmt.initializer.type
                symtab.declare(stmt.name, stmt.type, stmt.mut)
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
                    symtab.declare(pname, _ptype)
                walk_stmts(stmt.body.statements)
                symtab.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
            elif isinstance(stmt, StructDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, EnumDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, Switch):
                walk_expr(stmt.scrutinee)
                for case_val, case_stmt in stmt.cases:
                    walk_expr(case_val)
                    walk_stmts([case_stmt])
            elif isinstance(stmt, ForIn):
                walk_expr(stmt.iterable)
                symtab.push_scope()
                symtab.declare(stmt.index, "i32")
                symtab.declare(stmt.value, "i32")
                walk_stmts(stmt.body.statements)
                symtab.pop_scope()
            elif isinstance(stmt, Block):
                symtab.push_scope()
                walk_stmts(stmt.statements)
                symtab.pop_scope()

    walk_stmts(program.statements)
