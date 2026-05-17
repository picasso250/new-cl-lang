"""
符号表 —— Pass 1：遍历 AST，仅收集声明（函数签名 + struct 定义）。
不管变量声明（那是 Pass 2 的事）。各司其职，不跨界。
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


C_RUNTIME_NAMES = {
    "div",
    "exit",
    "malloc",
    "free",
    "printf",
    "strlen",
    "memcpy",
    "memcmp",
    "str",
}


def _check_c_runtime_name(name: str):
    if name in C_RUNTIME_NAMES or name.startswith("__nc_"):
        raise NameError(f"'{name}' conflicts with NC/C runtime name")


class SymbolTable:
    def __init__(self):
        self._scopes: list[dict[str, Symbol]] = [{}]
        self._level = 0
        self._structs: dict[str, dict[str, str]] = {}  # struct名 → {字段: 类型}

    def push_scope(self):
        self._scopes.append({})
        self._level += 1

    def pop_scope(self):
        self._scopes.pop()
        self._level -= 1

    def declare(self, name: str, nc_type: str, is_mut: bool = False):
        _check_c_runtime_name(name)
        if name in self._scopes[-1]:
            raise NameError(f"Variable '{name}' already declared in this scope")
        self._scopes[-1][name] = Symbol(name, nc_type, self._level, is_mut)

    def declare_global(self, name: str, nc_type: str):
        """类型定义统一入全局层（struct/enum），不随作用域弹出。"""
        if name in self._scopes[0]:
            raise NameError(f"'{name}' already declared globally")
        self._scopes[0][name] = Symbol(name, nc_type, 0)

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
    """Pass 1: 遍历 AST，收集函数签名和 struct 定义。
    进入函数体以捕获形参和嵌套 struct，但不管 let 变量。
    """
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, If, While, FunctionDeclaration, Return,
        StructDecl, EnumDecl, Switch, ForIn,
        BinaryOp, UnaryOp, FunctionCall,
        ArrayLiteral, IndexAccess, MethodCall, FieldAccess, StructLiteral, TryCatch, Throw, Defer
    )
    table = SymbolTable()

    table.declare_global("str", "struct")
    table.declare_struct("str", [("ptr", "i64"), ("len", "i64")])
    table._methods = {}  # {type_name: {method_name: (ret_type, [(param, type)])}}
    table._functions = {}  # {function_name: (ret_type, [(param, type)])}

    def walk_stmts(stmts: list):
        for stmt in stmts:
            if isinstance(stmt, FunctionDeclaration):
                if stmt.receiver_name:
                    # 方法：注册为 TypeName_methodName
                    rtype = stmt.receiver_type  # e.g. "*Stack"
                    type_name = rtype.lstrip("*")
                    mangled = f"{type_name}_{stmt.name}"
                    table.declare(mangled, stmt.return_type or "void")
                    if type_name not in table._methods:
                        table._methods[type_name] = {}
                    table._methods[type_name][stmt.name] = (stmt.return_type, stmt.params)
                    table.push_scope()
                    table.declare(stmt.receiver_name, rtype)
                    for pname, ptype in stmt.params:
                        table.declare(pname, ptype)
                    walk_stmts(stmt.body.statements)
                    table.pop_scope()
                else:
                    table.declare(stmt.name, stmt.return_type or "void")
                    table._functions[stmt.name] = (stmt.return_type or "void", stmt.params)
                    table.push_scope()
                    for pname, ptype in stmt.params:
                        table.declare(pname, ptype)
                    walk_stmts(stmt.body.statements)
                    table.pop_scope()
            elif isinstance(stmt, StructDecl):
                table.declare_global(stmt.name, "struct")
                table.declare_struct(stmt.name, stmt.fields)
            elif isinstance(stmt, EnumDecl):
                table.declare_global(stmt.name, "enum")
            elif isinstance(stmt, (If, While, Block, Switch, ForIn, TryCatch)):
                _descend_stmt(stmt)
            elif isinstance(stmt, ExpressionStatement):
                _walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                _walk_expr(stmt.expr)
            elif isinstance(stmt, Return):
                if stmt.expr:
                    _walk_expr(stmt.expr)
            elif isinstance(stmt, Throw):
                _walk_expr(stmt.expr)
            elif isinstance(stmt, Defer):
                walk_stmts(stmt.body.statements)
            # VariableDeclaration: 跳过 —— Pass 2 负责

    def _descend_stmt(stmt):
        if isinstance(stmt, ForIn):
            table.push_scope()
            table.declare(stmt.index, "i32")
            if stmt.start is not None:
                _walk_expr(stmt.start)
                _walk_expr(stmt.end)
            else:
                table.declare(stmt.value, "i32")
                _walk_expr(stmt.iterable)
            walk_stmts(stmt.body.statements)
            table.pop_scope()
        elif isinstance(stmt, Switch):
            _walk_expr(stmt.scrutinee)
            for case_val, case_stmt in stmt.cases:
                _walk_expr(case_val)
                walk_stmts([case_stmt])
        elif isinstance(stmt, TryCatch):
            table.push_scope()
            walk_stmts(stmt.try_block.statements)
            table.pop_scope()
            table.push_scope()
            table.declare(stmt.error_name, "str")
            walk_stmts(stmt.catch_block.statements)
            table.pop_scope()
        elif isinstance(stmt, If):
            _walk_expr(stmt.condition)
            table.push_scope()
            walk_stmts(stmt.then_block.statements)
            table.pop_scope()
            if stmt.else_block:
                table.push_scope()
                walk_stmts(stmt.else_block.statements)
                table.pop_scope()
        elif isinstance(stmt, While):
            _walk_expr(stmt.condition)
            table.push_scope()
            walk_stmts(stmt.body.statements)
            table.pop_scope()
        elif isinstance(stmt, Block):
            table.push_scope()
            walk_stmts(stmt.statements)
            table.pop_scope()

    def _walk_expr(node):
        if isinstance(node, BinaryOp):
            _walk_expr(node.left)
            _walk_expr(node.right)
        elif isinstance(node, UnaryOp):
            _walk_expr(node.operand)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                _walk_expr(arg)
        elif isinstance(node, ArrayLiteral):
            for elem in node.elements:
                _walk_expr(elem)
        elif isinstance(node, IndexAccess):
            _walk_expr(node.obj)
            _walk_expr(node.index)
        elif isinstance(node, MethodCall):
            _walk_expr(node.obj)
            for arg in node.args:
                _walk_expr(arg)
        elif isinstance(node, FieldAccess):
            _walk_expr(node.obj)
        elif isinstance(node, StructLiteral):
            for _fn, fv in node.fields:
                _walk_expr(fv)

    walk_stmts(program.statements)
    return table
