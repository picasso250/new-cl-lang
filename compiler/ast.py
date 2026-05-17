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
    """let x = expr;  或  let mut x: T = expr;"""
    def __init__(self, name: str, mut: bool, initializer, annotation: str | None = None):
        self.name = name
        self.mut = mut
        self.initializer = initializer
        self.annotation = annotation

    def __repr__(self):
        m = "mut " if self.mut else ""
        t = f": {self.annotation}" if self.annotation else ""
        return f"Let({m}{self.name}{t} = {self.initializer})"


class ExpressionStatement(Node):
    """表达式语句，如 print(x);"""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"ExprStmt({self.expr})"


class Assignment(Node):
    """x = expr;  重赋值。target 为 Identifier 或 IndexAccess。"""
    def __init__(self, target, expr):
        self.target = target
        self.expr = expr

    def __repr__(self):
        return f"Assign({self.target} = {self.expr})"


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


class Switch(Node):
    """switch expr { case -> stmt; ... }"""
    def __init__(self, scrutinee, cases: list):
        self.scrutinee = scrutinee
        self.cases = cases  # [(value_expr, statement), ...]

    def __repr__(self):
        cs = ', '.join(f"{v} -> {s}" for v, s in self.cases)
        return f"Switch({self.scrutinee} {{ {cs} }})"


class Break(Node):
    """break;"""
    def __repr__(self):
        return "Break"


class ForIn(Node):
    """for index, value in iterable { body }
       或  for i in start..end { body }"""
    def __init__(self, index: str, value: str | None, iterable, body: "Block",
                 start=None, end=None):
        self.index = index
        self.value = value
        self.iterable = iterable
        self.body = body
        self.start = start  # 区间范围
        self.end = end

    def __repr__(self):
        if self.start is not None:
            return f"ForRange({self.index} in {self.start}..{self.end})"
        return f"ForIn({self.index}, {self.value} in {self.iterable})"


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
    """Name { field: value, ... }  或  new Name { field: value, ... }"""
    def __init__(self, name: str, fields: list, heap: bool = False):
        self.name = name
        self.fields = fields  # [(name, expr), ...]
        self.heap = heap

    def __repr__(self):
        fs = ', '.join(f'{n}: {v}' for n, v in self.fields)
        pre = "new " if self.heap else ""
        return f"{pre}StructLit({self.name} {{ {fs} }})"


class FieldAccess(Node):
    """expr.field"""
    def __init__(self, obj, field: str):
        self.obj = obj
        self.field = field

    def __repr__(self):
        return f"Field({self.obj}.{self.field})"


class ArrayType:
    """非 AST 节点，仅供类型描述：[N]elem_type"""
    def __init__(self, length: int, elem_type: str):
        self.length = length
        self.elem_type = elem_type

    def __repr__(self):
        return f"[{self.length}]{self.elem_type}"

    def __str__(self):
        return self.__repr__()


class ArrayLiteral(Node):
    """[N]T { e1, e2, ... }"""
    def __init__(self, length: int, elem_type: str, elements: list):
        self.length = length
        self.elem_type = elem_type
        self.elements = elements

    def __repr__(self):
        es = ', '.join(str(e) for e in self.elements)
        return f"ArrayLit([{self.length}]{self.elem_type} {{ {es} }})"


class SliceLiteral(Node):
    """[]T { e1, e2, ... }"""
    def __init__(self, elem_type: str, elements: list):
        self.elem_type = elem_type
        self.elements = elements

    def __repr__(self):
        es = ', '.join(str(e) for e in self.elements)
        return f"SliceLit([]{self.elem_type} {{ {es} }})"


class IndexAccess(Node):
    """expr[index]"""
    def __init__(self, obj, index):
        self.obj = obj
        self.index = index

    def __repr__(self):
        return f"Index({self.obj}[{self.index}])"


class SliceExpr(Node):
    """arr[start:end]"""
    def __init__(self, array, start, end):
        self.array = array
        self.start = start  # None 表示 [:end]
        self.end = end      # None 表示 [start:]

    def __repr__(self):
        s = str(self.start) if self.start else ""
        e = str(self.end) if self.end else ""
        return f"Slice({self.array}[{s}:{e}])"


class TryCatch(Node):
    """try { block } catch e { block }"""
    def __init__(self, try_block: Block, error_name: str, catch_block: Block):
        self.try_block = try_block
        self.error_name = error_name
        self.catch_block = catch_block

    def __repr__(self):
        return f"Try({self.try_block}) catch {self.error_name} {{ {self.catch_block} }}"


class Throw(Node):
    """throw expr"""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"Throw({self.expr})"


class Defer(Node):
    """defer { block }"""
    def __init__(self, body: Block):
        self.body = body

    def __repr__(self):
        return f"Defer({self.body})"


class FunctionDeclaration(Node):
    """fun name(params): return_type { body }
       或  fun (r *T) name(params): return_type { body }"""
    def __init__(self, name: str, params: list, return_type: str | None, body: Block,
                 receiver_name: str | None = None, receiver_type: str | None = None):
        self.name = name
        self.params = params   # [(name, type), ...]
        self.return_type = return_type  # None = void
        self.body = body
        self.receiver_name = receiver_name  # 方法接收者名
        self.receiver_type = receiver_type  # 方法接收者类型 (如 "*Stack")

    def __repr__(self):
        p = ', '.join(f'{n}: {t}' for n, t in self.params)
        r = f': {self.return_type}' if self.return_type else ''
        if self.receiver_name:
            return f"Method({self.receiver_type}.{self.name}({p}){r})"
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

class IfExpr(Node):
    """if expr { block } else { block } 作为表达式。"""
    def __init__(self, condition, then_block: Block, else_block: Block):
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

    def __repr__(self):
        return f"IfExpr({self.condition} {self.then_block} else {self.else_block})"

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


class BoolLiteral(Node):
    def __init__(self, value: bool):
        self.value = value

    def __repr__(self):
        return "Bool(true)" if self.value else "Bool(false)"


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


class MethodCall(Node):
    """obj.method(args...)"""
    def __init__(self, obj, method: str, args: list):
        self.obj = obj
        self.method = method
        self.args = args

    def __repr__(self):
        as_ = ', '.join(str(a) for a in self.args)
        return f"MethodCall({self.obj}.{self.method}({as_}))"


class Identifier(Node):
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Id({self.name})"
