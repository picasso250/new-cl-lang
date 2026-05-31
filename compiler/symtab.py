"""
符号表 —— Pass 1：遍历 AST，仅收集声明（函数签名 + struct 定义）。
不管变量声明（那是 Pass 2 的事）。各司其职，不跨界。
"""


class Symbol:
    def __init__(self, name: str, nc_type: str, scope_level: int):
        self.name = name
        self.nc_type = nc_type
        self.scope_level = scope_level

    def __repr__(self):
        return f"Symbol({self.name}: {self.nc_type} @{self.scope_level})"


RESERVED_RUNTIME_NAMES = {
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


def _check_runtime_name(name: str):
    if name in RESERVED_RUNTIME_NAMES or name.startswith("__nc_"):
        raise NameError(f"'{name}' conflicts with NC runtime name")


class SymbolTable:
    def __init__(self):
        self._scopes: list[dict[str, Symbol]] = [{}]
        self._level = 0
        self._structs: dict[str, dict[str, str]] = {}  # struct名 → {字段: 类型}
        self._enums: dict[str, set[str]] = {}  # enum名 → variants
        self._ifaces: dict[str, dict] = {}

    def push_scope(self):
        self._scopes.append({})
        self._level += 1

    def pop_scope(self):
        self._scopes.pop()
        self._level -= 1

    def declare(self, name: str, nc_type: str, *, allow_runtime_name: bool = False):
        if not allow_runtime_name:
            _check_runtime_name(name)
        if name in self._scopes[-1]:
            raise NameError(f"Variable '{name}' already declared in this scope")
        self._scopes[-1][name] = Symbol(name, nc_type, self._level)

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

    def declare_enum(self, name: str, variants: list[str]):
        self._enums[name] = set(variants)

    def lookup_enum(self, name: str) -> set[str]:
        if name not in self._enums:
            raise NameError(f"Enum '{name}' not found")
        return self._enums[name]

    def declare_iface(self, name: str, methods: list, embeds: list[str]):
        self._ifaces[name] = {"methods": methods, "embeds": embeds, "method_set": None}

    def lookup_iface(self, name: str) -> dict:
        if name not in self._ifaces:
            raise NameError(f"Iface '{name}' not found")
        return self._ifaces[name]

    def __repr__(self):
        return f"SymbolTable({self._scopes})"


def build_symbol_table(program: "Program") -> SymbolTable:
    """Pass 1: 遍历 AST，收集函数签名和 struct 定义。
    进入函数体以捕获形参和嵌套 struct，但不管 let 变量。
    """
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Update, Block, ForCondition, FunctionDeclaration, Return,
        StructDecl, IfaceDecl, EnumDecl, ForIn, ImportDecl, ExternBlock,
        IfExpr, BlockExpr, MatchExpr, BinaryOp, UnaryOp, FunctionCall, FunctionExpr,
        ArrayLiteral, IndexAccess, MethodCall, FieldAccess, StructLiteral, TryCatch, Throw, Defer
    )
    table = SymbolTable()

    table._methods = {}  # {type_name: {method_name: (ret_type, [(param, type)])}}
    table._functions = {}  # {function_name: (ret_type, [(param, type)])}
    table._extern_functions = set()

    def walk_stmts(stmts: list):
        for stmt in stmts:
            if isinstance(stmt, FunctionDeclaration):
                if getattr(stmt, "is_extern", False):
                    table.declare(stmt.name, stmt.return_type or "void", allow_runtime_name=True)
                    table._functions[stmt.name] = (stmt.return_type or "void", stmt.params)
                    table._extern_functions.add(stmt.name)
                    continue
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
                    table._functions[stmt.name] = (stmt.return_type, stmt.params)
                    table.push_scope()
                    for pname, ptype in stmt.params:
                        table.declare(pname, ptype)
                    walk_stmts(stmt.body.statements)
                    table.pop_scope()
            elif isinstance(stmt, StructDecl):
                table.declare_global(stmt.name, "struct")
                table.declare_struct(stmt.name, stmt.fields)
            elif isinstance(stmt, IfaceDecl):
                table.declare_global(stmt.name, "iface")
                table.declare_iface(stmt.name, stmt.methods, stmt.embeds)
            elif isinstance(stmt, EnumDecl):
                table.declare_global(stmt.name, "enum")
                table.declare_enum(stmt.name, stmt.variants)
            elif isinstance(stmt, ImportDecl):
                pass
            elif isinstance(stmt, ExternBlock):
                for fn in stmt.functions:
                    if fn.name in table._functions:
                        raise NameError(f"Function '{fn.name}' already declared")
                    table.declare(fn.name, fn.return_type or "void", allow_runtime_name=True)
                    table._functions[fn.name] = (fn.return_type or "void", fn.params)
                    table._extern_functions.add(fn.name)
            elif isinstance(stmt, (ForCondition, Block, ForIn, TryCatch)):
                _descend_stmt(stmt)
            elif isinstance(stmt, ExpressionStatement):
                _walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                _walk_expr(stmt.target)
                _walk_expr(stmt.expr)
            elif isinstance(stmt, Update):
                _walk_expr(stmt.target)
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
        elif isinstance(stmt, TryCatch):
            table.push_scope()
            walk_stmts(stmt.try_block.statements)
            table.pop_scope()
            table.push_scope()
            table.declare(stmt.error_name, "str")
            walk_stmts(stmt.catch_block.statements)
            table.pop_scope()
        elif isinstance(stmt, ForCondition):
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
        elif isinstance(node, FunctionExpr):
            table.push_scope()
            for pname, ptype in node.params:
                table.declare(pname, ptype)
            walk_stmts(node.body.statements)
            table.pop_scope()
        elif isinstance(node, IfExpr):
            _walk_expr(node.condition)
            walk_stmts(node.then_block.statements)
            if node.else_block:
                walk_stmts(node.else_block.statements)
        elif isinstance(node, BlockExpr):
            walk_stmts(node.block.statements)
        elif isinstance(node, MatchExpr):
            _walk_expr(node.scrutinee)
            for pattern, body in node.arms:
                if pattern is not None:
                    _walk_expr(pattern)
                _walk_expr(body)
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
