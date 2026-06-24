"""AST 节点定义。"""

from __future__ import annotations

from typing import Any


class Node:
    type: str | None
    span: tuple[int, int] | None
    source_file: Any
    generic_type_args: list[Any]
    generic_type_args_candidate: list[Any]
    is_capture: bool
    capture_type: str | None


class Program(Node):
    def __init__(self, statements: list):
        self.statements = statements

    def __repr__(self):
        return f"Program({self.statements})"


# ===== 语句 =====

class ImportDecl(Node):
    """import module_name"""
    def __init__(self, module_name: str):
        self.module_name = module_name

    def __repr__(self):
        return f"Import({self.module_name})"

class VariableDeclaration(Node):
    """let x = expr;  或  let x: T = expr;"""
    def __init__(self, name: str, initializer, annotation: str | None = None):
        self.name = name
        self.initializer = initializer
        self.annotation = annotation
        self.type: str | None = None

    def __repr__(self):
        t = f": {self.annotation}" if self.annotation else ""
        return f"Let({self.name}{t} = {self.initializer})"


class ExpressionStatement(Node):
    """表达式语句，如 io.println(x);"""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"ExprStmt({self.expr})"


class Assignment(Node):
    """x = expr 或 x += expr 等重赋值。"""
    def __init__(self, target, expr, op: str = "="):
        self.target = target
        self.expr = expr
        self.op = op
        self.overload_method: str | None = None
        self.overload_receiver_path: list[str] = []
        self.overload_receiver_base: str | None = None

    def __repr__(self):
        return f"Assign({self.target} {self.op} {self.expr})"


class Update(Node):
    """x++ / x--，只作为语句。"""
    def __init__(self, target, op: str):
        self.target = target
        self.op = op

    def __repr__(self):
        return f"Update({self.target}{self.op})"


class Block(Node):
    """{ statement* }"""
    def __init__(self, statements: list):
        self.statements = statements
        self._narrowed_vars: dict[str, str] | None = None

    def __repr__(self):
        return f"Block({self.statements})"


class ForCondition(Node):
    """for expr { block }"""
    def __init__(self, condition, body: Block):
        self.condition = condition
        self.body = body

    def __repr__(self):
        return f"ForCondition({self.condition} {self.body})"


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
    def __init__(self, name: str, fields: list, type_params: list[str] | None = None,
                 type_param_constraints: dict[str, str] | None = None,
                 embedded_fields: set[str] | None = None):
        self.name = name
        self.fields = fields  # [(name, type), ...]
        self.embedded_fields = embedded_fields or set()
        self.type_params = type_params or []
        self.type_param_constraints = type_param_constraints or {}

    def __repr__(self):
        fs = ', '.join(t if n in self.embedded_fields else f'{n}: {t}' for n, t in self.fields)
        return f"Struct({self.name} {{ {fs} }})"


class IfaceDecl(Node):
    """iface Name { fun method(params): ret; EmbeddedIface; ... }"""
    def __init__(self, name: str, methods: list, embeds: list[str] | None = None):
        self.name = name
        self.methods = methods  # [(name, [(param, type), ...], return_type), ...]
        self.embeds: list[Any] = embeds or []

    def __repr__(self):
        ms = ', '.join(f'{m[0]}({m[1]}): {m[2]}' + (' err' if len(m) > 3 and m[3] else '') for m in self.methods)
        es = ', '.join(self.embeds)
        return f"Iface({self.name} embeds [{es}] {{ {ms} }})"


class TypeAlias(Node):
    """type Name = Type"""
    def __init__(self, name: str, target_type: str):
        self.name = name
        self.target_type = target_type

    def __repr__(self):
        return f"TypeAlias({self.name} = {self.target_type})"


class ExternBlock(Node):
    """extern { fun name(params): ret } or extern "lib" { ... }"""
    def __init__(self, lib: str | None, functions: list):
        self.lib = lib
        self.functions = functions
        self.trusted_stdlib = False

    def __repr__(self):
        lib = f'"{self.lib}"' if self.lib is not None else "<default>"
        return f"Extern({lib}, {self.functions})"


class Param(Node):
    """Function parameter with optional default expression."""
    def __init__(self, name: str, type_name: str | None, default=None):
        self.name = name
        self.type = type_name
        self.default = default

    def __iter__(self):
        yield self.name
        yield self.type

    def __repr__(self):
        type_part = f": {self.type}" if self.type is not None else ""
        default = f" = {self.default}" if self.default is not None else ""
        return f"{self.name}{type_part}{default}"


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
        self.type: str | None = None

    def __repr__(self):
        return f"EnumRef({self.enum_name}::{self.variant})"


class StructLiteral(Node):
    """Name { field: value, ... }  或  new Name { field: value, ... }"""
    def __init__(self, name: str, fields: list, heap: bool = False):
        self.name: Any = name
        self.fields = fields  # [(name, expr), ...]
        self.heap = heap
        self.type: str | None = None

    def __repr__(self):
        fs = ', '.join(f'{n}: {v}' for n, v in self.fields)
        pre = "new " if self.heap else ""
        return f"{pre}StructLit({self.name} {{ {fs} }})"


class FieldAccess(Node):
    """expr.field"""
    def __init__(self, obj, field: str):
        self.obj = obj
        self.field = field
        self.type: str | None = None

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
        self.type: str | None = None

    def __repr__(self):
        es = ', '.join(str(e) for e in self.elements)
        return f"ArrayLit([{self.length}]{self.elem_type} {{ {es} }})"


class SliceLiteral(Node):
    """[]T { e1, e2, ... }"""
    def __init__(self, elem_type: str | None, elements: list):
        self.elem_type = elem_type
        self.elements = elements
        self.type: str | None = None

    def __repr__(self):
        es = ', '.join(str(e) for e in self.elements)
        return f"SliceLit([]{self.elem_type} {{ {es} }})"


class MapLiteral(Node):
    """map[K,V] { key: value, ... } or inferred map { key: value, ... }"""
    def __init__(self, map_type: str | None, entries: list):
        self.map_type = map_type
        self.entries = entries  # [(key_expr, value_expr), ...]
        self.type: str | None = None

    def __repr__(self):
        entries = ', '.join(f'{k}: {v}' for k, v in self.entries)
        return f"MapLit({self.map_type} {{ {entries} }})"


class IndexAccess(Node):
    """expr[index]"""
    def __init__(self, obj, index):
        self.obj = obj
        self.index = index
        self.name: str | None = None
        self.type_args: list[Any] = []
        self.type: str | None = None

    def __repr__(self):
        return f"Index({self.obj}[{self.index}])"


class SliceExpr(Node):
    """arr[start:end]"""
    def __init__(self, array, start, end):
        self.array = array
        self.start = start  # None 表示 [:end]
        self.end = end      # None 表示 [start:]
        self.type: str | None = None

    def __repr__(self):
        s = str(self.start) if self.start else ""
        e = str(self.end) if self.end else ""
        return f"Slice({self.array}[{s}:{e}])"


class ErrReturn(Node):
    """err expr"""
    def __init__(self, expr):
        self.expr = expr

    def __repr__(self):
        return f"Err({self.expr})"


class Defer(Node):
    """defer { block }"""
    def __init__(self, body: Block):
        self.body = body

    def __repr__(self):
        return f"Defer({self.body})"


class TryStatement(Node):
    """try name = call() { ok } else err_name { err }"""
    def __init__(self, call, success_block: Block, success_name: str | None = None,
                 error_name: str | None = None, error_block: Block | None = None):
        self.call = call
        self.success_name = success_name
        self.success_block = success_block
        self.error_name = error_name
        self.error_block = error_block
        self.type: str | None = None

    def __repr__(self):
        bind = f"{self.success_name} = " if self.success_name else ""
        else_part = f" else {self.error_name} {self.error_block}" if self.error_block else ""
        return f"Try({bind}{self.call} {self.success_block}{else_part})"


class FunctionDeclaration(Node):
    """fun name(params): return_type { body }
       或  fun (r *T) name(params): return_type { body }"""
    def __init__(self, name: str, params: list, return_type: str | None, body: Block,
                 receiver_name: str | None = None, receiver_type: str | None = None,
                 return_type_explicit: bool = False, type_params: list[str] | None = None,
                 type_param_constraints: dict[str, str] | None = None,
                 fallible_explicit: bool = False):
        self.name = name
        self.extern_symbol: Any = None
        self.extern_lib: Any = None
        self.is_extern = False
        self.trusted_stdlib = False
        self.fallible = False
        self.fallible_explicit = fallible_explicit
        self.params = params   # [Param, ...]
        self.return_type = return_type
        self.return_type_explicit = return_type_explicit
        self.body = body
        self.receiver_name = receiver_name  # 方法接收者名
        self.receiver_type = receiver_type  # 方法接收者类型 (如 "*Stack")
        self.type_params = type_params or []
        self.type_param_constraints = type_param_constraints or {}

    def __repr__(self):
        p = ', '.join(str(param) for param in self.params)
        r = f': {self.return_type}' if self.return_type else ''
        if self.receiver_name:
            return f"Method({self.receiver_type}.{self.name}({p}){r})"
        return f"Fun({self.name}({p}){r} {self.body})"


class FunctionExpr(Node):
    """fun(params): return_type { body } 作为表达式。"""
    def __init__(self, params: list, return_type: str | None, body: Block,
                 return_type_explicit: bool = False, fallible_explicit: bool = False):
        self.params = params
        self.return_type = return_type
        self.return_type_explicit = return_type_explicit
        self.body = body
        self.captures = []  # [(name, type), ...] filled by typecheck
        self.type: str | None = None
        self.fallible = False
        self.fallible_explicit = fallible_explicit
        self.closure_id: int | None = None

    def __repr__(self):
        p = ', '.join(str(param) for param in self.params)
        r = f': {self.return_type}' if self.return_type else ''
        return f"FunExpr({p}{r} {self.body})"


class GenericFunctionValue(Node):
    """foo[T] as a first-class function value after monomorphization."""
    def __init__(self, name: str, type_args: list[str] | None = None):
        self.name = name
        self.type_args: list[Any] = type_args or []
        self.type: str | None = None
        self.fallible = False

    def __repr__(self):
        args = f"[{','.join(self.type_args)}]" if self.type_args else ""
        return f"GenericFunValue({self.name}{args})"


class Return(Node):
    """ret expr;"""
    def __init__(self, expr = None):
        self.expr = expr

    def __repr__(self):
        return f"Return({self.expr})"


class FallibleOp(Node):
    """expr??, expr!!"""
    def __init__(self, expr, op: str):
        self.expr = expr
        self.op = op
        self.type: str | None = None

    def __repr__(self):
        return f"FallibleOp({self.expr} {self.op})"


class ErrorHandlerExpr(Node):
    """expr err? name { handler }"""
    def __init__(self, expr, error_name: str, handler_block: Block):
        self.expr = expr
        self.error_name = error_name
        self.handler_block = handler_block
        self.type: str | None = None
        self.success_type: str | None = None

    def __repr__(self):
        return f"ErrorHandler({self.expr} err? {self.error_name} {self.handler_block})"


class ErrorMatchExpr(Node):
    """expr match? name { "message" -> expr; else -> expr }"""
    def __init__(self, expr, error_name: str, arms: list[tuple]):
        self.expr = expr
        self.error_name = error_name
        self.arms = arms
        self.type: str | None = None
        self.success_type: str | None = None

    def __repr__(self):
        arms = "; ".join(("else" if p is None else str(p)) + " -> " + str(b) for p, b in self.arms)
        return f"ErrorMatch({self.expr} match? {self.error_name} {{ {arms} }})"


# ===== 表达式 =====

class IfExpr(Node):
    """if expr { block } else { block } 作为表达式。"""
    def __init__(self, condition, then_block: Block, else_block: Block | None = None):
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block
        self.type: str | None = None

    def __repr__(self):
        e = f" else {self.else_block}" if self.else_block else ""
        return f"IfExpr({self.condition} {self.then_block}{e})"


class BlockExpr(Node):
    """{ statements; tail_expr } 作为表达式。"""
    def __init__(self, block: Block):
        self.block = block
        self.type: str | None = None

    def __repr__(self):
        return f"BlockExpr({self.block})"


class MatchExpr(Node):
    """match expr { pattern -> expr; else -> expr } 作为表达式。"""
    def __init__(self, scrutinee, arms: list):
        self.scrutinee = scrutinee
        self.arms = arms  # [(pattern_expr | None, body_expr), ...]; None 表示 else
        self.type: str | None = None

    def __repr__(self):
        arms = ', '.join(f"{p if p is not None else 'else'} -> {b}" for p, b in self.arms)
        return f"MatchExpr({self.scrutinee} {{ {arms} }})"

class StringLiteral(Node):
    def __init__(self, value: str):
        self.value = value
        self.type: str | None = None

    def __repr__(self):
        return f'String("{self.value}")'


class InterpolatedString(Node):
    """String with literal/expression parts."""
    def __init__(self, parts: list):
        self.parts = parts
        self.type: str | None = None

    def __repr__(self):
        return f"InterpolatedString({self.parts})"


class RuneLiteral(Node):
    def __init__(self, value: int):
        self.value = value
        self.type: str | None = None

    def __repr__(self):
        return f"Rune({self.value})"


class IntegerLiteral(Node):
    def __init__(self, value: int, suffix_type: str | None = None):
        self.value = value
        self.suffix_type = suffix_type
        self.type: str | None = None

    def __repr__(self):
        suffix = self.suffix_type or ""
        return f"Integer({self.value}{suffix})"


class FloatLiteral(Node):
    def __init__(self, value: str, suffix_type: str | None = None):
        self.value = value
        self.suffix_type = suffix_type
        self.type: str | None = None

    def __repr__(self):
        suffix = self.suffix_type or ""
        return f"Float({self.value}{suffix})"


class BoolLiteral(Node):
    def __init__(self, value: bool):
        self.value = value
        self.type: str | None = None

    def __repr__(self):
        return "Bool(true)" if self.value else "Bool(false)"


class NilLiteral(Node):
    def __init__(self):
        self.type: str | None = None

    def __repr__(self):
        return "Nil"


class MagicConst(Node):
    """Compiler-provided source location constants."""
    def __init__(self, name: str):
        self.name = name
        self.type: str | None = None

    def __repr__(self):
        return f"MagicConst({self.name})"


class BinaryOp(Node):
    def __init__(self, left, op: str, right):
        self.left = left
        self.op = op
        self.right = right
        self.type: str | None = None
        self.overload_method: str | None = None
        self.overload_receiver_path: list[str] = []
        self.overload_receiver_base: str | None = None
        self.overload_receiver_side: str = "left"
        self.overload_negate: bool = False

    def __repr__(self):
        return f"BinOp({self.left} {self.op} {self.right})"


class UnaryOp(Node):
    """!expr 等前缀运算符。"""
    def __init__(self, op: str, operand):
        self.op = op
        self.operand = operand
        self.type: str | None = None
        self.overload_method: str | None = None
        self.overload_receiver_path: list[str] = []
        self.overload_receiver_base: str | None = None

    def __repr__(self):
        return f"UnaryOp({self.op}{self.operand})"


class FunctionCall(Node):
    def __init__(self, name: str, args: list, type_args: list[str] | None = None):
        self.name = name
        self.args = args
        self.type_args: list[Any] = type_args or []
        self.type: str | None = None
        self.fallible = False
        self.is_closure_call = False
        self.closure_param_types: list[Any] = []

    def __repr__(self):
        return f"Call({self.name}, {self.args})"


class SizeOfType(Node):
    """size_of(T) compile-time builtin expression."""
    def __init__(self, type_name: str):
        self.type_name: Any = type_name
        self.type: str | None = None

    def __repr__(self):
        return f"SizeOf({self.type_name})"


class MethodCall(Node):
    """obj.method(args...)"""
    def __init__(self, obj, method: str, args: list):
        self.obj = obj
        self.method = method
        self.args = args
        self.type: str | None = None
        self.fallible = False
        self.promoted_receiver_base: str | None = None

    def __repr__(self):
        as_ = ', '.join(str(a) for a in self.args)
        return f"MethodCall({self.obj}.{self.method}({as_}))"


class Identifier(Node):
    def __init__(self, name: str):
        self.name = name
        self.type: str | None = None
        self.is_capture = False
        self.capture_type: str | None = None

    def __repr__(self):
        return f"Id({self.name})"
