"""AST 节点定义。"""


class Node:
    pass


class Program(Node):
    def __init__(self, statements: list):
        self.statements = statements

    def __repr__(self):
        return f"Program({self.statements})"


# ===== 语句 =====

class VariableDeclaration(Node):
    """let x = expr;  或  let mut x = expr;"""
    def __init__(self, name: str, mut: bool, initializer):
        self.name = name
        self.mut = mut
        self.initializer = initializer

    def __repr__(self):
        m = "mut " if self.mut else ""
        return f"Let({m}{self.name} = {self.initializer})"


class ExpressionStatement(Node):
    """表达式语句，如 print(x);"""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"ExprStmt({self.expr})"


class Assignment(Node):
    """x = expr;  重赋值"""
    def __init__(self, name: str, expr):
        self.name = name
        self.expr = expr

    def __repr__(self):
        return f"Assign({self.name} = {self.expr})"


class Block(Node):
    """{ statement* }"""
    def __init__(self, statements: list):
        self.statements = statements

    def __repr__(self):
        return f"Block({self.statements})"


class While(Node):
    """while expr { block }"""
    def __init__(self, condition, body: Block):
        self.condition = condition
        self.body = body

    def __repr__(self):
        return f"While({self.condition} {self.body})"


class StructDecl(Node):
    """struct Name { field: type, ... }"""
    def __init__(self, name: str, fields: list):
        self.name = name
        self.fields = fields  # [(name, type), ...]

    def __repr__(self):
        fs = ', '.join(f'{n}: {t}' for n, t in self.fields)
        return f"Struct({self.name} {{ {fs} }})"


class EnumDecl(Node):
    """enum Name { A, B, C } —— 纯标签，无变体数据。"""
    def __init__(self, name: str, variants: list[str]):
        self.name = name
        self.variants = variants

    def __repr__(self):
        vs = ', '.join(self.variants)
        return f"Enum({self.name} {{ {vs} }})"


class EnumRef(Node):
    """Color::Red"""
    def __init__(self, enum_name: str, variant: str):
        self.enum_name = enum_name
        self.variant = variant

    def __repr__(self):
        return f"EnumRef({self.enum_name}::{self.variant})"


class StructLiteral(Node):
    """Name { field: value, ... }"""
    def __init__(self, name: str, fields: list):
        self.name = name
        self.fields = fields  # [(name, expr), ...]

    def __repr__(self):
        fs = ', '.join(f'{n}: {v}' for n, v in self.fields)
        return f"StructLit({self.name} {{ {fs} }})"


class FieldAccess(Node):
    """expr.field"""
    def __init__(self, obj, field: str):
        self.obj = obj
        self.field = field

    def __repr__(self):
        return f"Field({self.obj}.{self.field})"


class FunctionDeclaration(Node):
    """fun name(params): return_type { body }"""
    def __init__(self, name: str, params: list, return_type: str | None, body: Block):
        self.name = name
        self.params = params   # [(name, type), ...]
        self.return_type = return_type  # None = void
        self.body = body

    def __repr__(self):
        p = ', '.join(f'{n}: {t}' for n, t in self.params)
        r = f': {self.return_type}' if self.return_type else ''
        return f"Fun({self.name}({p}){r} {self.body})"


class Return(Node):
    """return expr;"""
    def __init__(self, expr = None):
        self.expr = expr

    def __repr__(self):
        return f"Return({self.expr})"


class If(Node):
    """if expr { block } [else { block }]"""
    def __init__(self, condition, then_block: Block, else_block: Block | None = None):
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

    def __repr__(self):
        e = f" else {self.else_block}" if self.else_block else ""
        return f"If({self.condition} {self.then_block}{e})"


# ===== 表达式 =====

class StringLiteral(Node):
    def __init__(self, value: str):
        self.value = value

    def __repr__(self):
        return f'String("{self.value}")'


class IntegerLiteral(Node):
    def __init__(self, value: int):
        self.value = value

    def __repr__(self):
        return f"Integer({self.value})"


class BinaryOp(Node):
    def __init__(self, left, op: str, right):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self):
        return f"BinOp({self.left} {self.op} {self.right})"


class UnaryOp(Node):
    """!expr 等前缀运算符。"""
    def __init__(self, op: str, operand):
        self.op = op
        self.operand = operand

    def __repr__(self):
        return f"UnaryOp({self.op}{self.operand})"


class FunctionCall(Node):
    def __init__(self, name: str, args: list):
        self.name = name
        self.args = args

    def __repr__(self):
        return f"Call({self.name}, {self.args})"


class Identifier(Node):
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Id({self.name})"
