"""
符号表 —— Pass 1：遍历 AST，收集所有声明。
暂不支持嵌套作用域（当前无块结构），结构已预留 scope 字段。
"""


class Symbol:
    def __init__(self, name: str, nc_type: str, is_mut: bool = False):
        self.name = name
        self.nc_type = nc_type    # "i32", "f64", "str", ...
        self.is_mut = is_mut

    def __repr__(self):
        m = "mut " if self.is_mut else ""
        return f"Symbol({m}{self.name}: {self.nc_type})"


class SymbolTable:
    def __init__(self):
        self._vars: dict[str, Symbol] = {}

    def declare(self, name: str, nc_type: str, is_mut: bool = False):
        if name in self._vars:
            raise NameError(f"Variable '{name}' already declared")
        self._vars[name] = Symbol(name, nc_type, is_mut)

    def lookup(self, name: str) -> Symbol:
        if name not in self._vars:
            raise NameError(f"Variable '{name}' not found")
        return self._vars[name]

    def __repr__(self):
        return f"SymbolTable({list(self._vars.values())})"


def build_symbol_table(program: "Program") -> SymbolTable:
    """Pass 1: 遍历 Program，建立符号表。"""
    from compiler.ast import Program, VariableDeclaration
    table = SymbolTable()
    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration):
            # 目前所有变量推断为 i32
            table.declare(stmt.name, "i32", stmt.mut)
    return table
