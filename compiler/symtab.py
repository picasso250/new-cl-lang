"""
符号表 —— Pass 1：遍历 AST，收集所有声明。
支持嵌套作用域（Block / If 引入新作用域）。
"""


class Symbol:
    def __init__(self, name: str, nc_type: str, scope_level: int, is_mut: bool = False):
        self.name = name
        self.nc_type = nc_type
        self.scope_level = scope_level
        self.is_mut = is_mut

    def __repr__(self):
        m = "mut " if self.is_mut else ""
        return f"Symbol({m}{self.name}: {self.nc_type} @{self.scope_level})"


class SymbolTable:
    def __init__(self):
        self._scopes: list[dict[str, Symbol]] = [{}]  # 栈式作用域
        self._level = 0
        self._structs: dict[str, dict[str, str]] = {}  # struct名 → {字段: 类型}

    def push_scope(self):
        self._scopes.append({})
        self._level += 1

    def pop_scope(self):
        self._scopes.pop()
        self._level -= 1

    def declare(self, name: str, nc_type: str, is_mut: bool = False):
        if name in self._scopes[-1]:
            raise NameError(f"Variable '{name}' already declared in this scope")
        self._scopes[-1][name] = Symbol(name, nc_type, self._level, is_mut)

    def lookup(self, name: str) -> Symbol:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        raise NameError(f"Variable '{name}' not found")

    def declare_struct(self, name: str, fields: list[tuple[str, str]]):
        self._structs[name] = {fname: ftype for fname, ftype in fields}

    def lookup_struct(self, name: str) -> dict[str, str]:
        if name not in self._structs:
            raise NameError(f"Struct '{name}' not found")
        return self._structs[name]

    def __repr__(self):
        return f"SymbolTable({self._scopes})"


def build_symbol_table(program: "Program") -> SymbolTable:
    """Pass 1: 遍历 Program，建立符号表（支持嵌套作用域）。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, If, While, FunctionDeclaration, Return,
        StructDecl,
    )
    table = SymbolTable()

    def walk_stmts(stmts: list):
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                table.declare(stmt.name, "i32", stmt.mut)
            elif isinstance(stmt, If):
                walk_expr(stmt.condition)
                table.push_scope()
                walk_stmts(stmt.then_block.statements)
                table.pop_scope()
                if stmt.else_block:
                    table.push_scope()
                    walk_stmts(stmt.else_block.statements)
                    table.pop_scope()
            elif isinstance(stmt, While):
                walk_expr(stmt.condition)
                table.push_scope()
                walk_stmts(stmt.body.statements)
                table.pop_scope()
            elif isinstance(stmt, FunctionDeclaration):
                # 函数名注册到外层作用域
                table.declare(stmt.name, stmt.return_type or "void")
                table.push_scope()
                # 参数也注册
                for pname, ptype in stmt.params:
                    table.declare(pname, ptype)
                walk_stmts(stmt.body.statements)
                table.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
            elif isinstance(stmt, StructDecl):
                table.declare(stmt.name, "struct")
                table.declare_struct(stmt.name, stmt.fields)
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.expr)
            # Block standalone（暂不用到）
            elif isinstance(stmt, Block):
                table.push_scope()
                walk_stmts(stmt.statements)
                table.pop_scope()

    def walk_expr(node):
        from compiler.ast import BinaryOp, FunctionCall, Identifier, IntegerLiteral
        if isinstance(node, BinaryOp):
            walk_expr(node.left)
            walk_expr(node.right)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                walk_expr(arg)
        # Identifier / IntegerLiteral 不需处理

    walk_stmts(program.statements)
    return table
