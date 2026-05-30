"""Internal helpers for NC type strings.

The public AST still stores type annotations as strings.  This module is the
single parser/formatter for those strings so passes do not slice type syntax by
hand.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NamedType:
    name: str


@dataclass(frozen=True)
class PointerType:
    inner: "TypeRef"
    nullable: bool = False


@dataclass(frozen=True)
class SliceType:
    elem: "TypeRef"


@dataclass(frozen=True)
class ArrayTypeRef:
    length: int
    elem: "TypeRef"


@dataclass(frozen=True)
class FunctionType:
    params: tuple["TypeRef", ...]
    ret: "TypeRef"


@dataclass(frozen=True)
class GenericType:
    base: "TypeRef"
    args: tuple["TypeRef", ...]


TypeRef = NamedType | PointerType | SliceType | ArrayTypeRef | FunctionType | GenericType


class TypeParseError(ValueError):
    pass


def split_top_level(s: str, sep: str = ",") -> list[str]:
    parts = []
    start = 0
    square = 0
    paren = 0
    for i, ch in enumerate(s):
        if ch == "[":
            square += 1
        elif ch == "]":
            square -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == sep and square == 0 and paren == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def _find_matching(s: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    raise TypeParseError(f"unclosed {open_ch} in type {s!r}")


def parse_type_ref(t: str | None) -> TypeRef | None:
    if t is None or not isinstance(t, str):
        return t
    t = t.strip()
    if t.startswith("?*"):
        return PointerType(parse_type_ref(t[2:]), nullable=True)
    if t.startswith("*"):
        return PointerType(parse_type_ref(t[1:]), nullable=False)
    if t.startswith("[]"):
        return SliceType(parse_type_ref(t[2:]))
    if t.startswith("["):
        close = t.find("]")
        if close < 0:
            raise TypeParseError(f"invalid array type {t!r}")
        return ArrayTypeRef(int(t[1:close]), parse_type_ref(t[close + 1:]))
    if t.startswith("fn("):
        close = _find_matching(t, 2, "(", ")")
        if not t.startswith("->", close + 1):
            raise TypeParseError(f"invalid function type {t!r}")
        args_s = t[3:close]
        params = tuple(parse_type_ref(a) for a in split_top_level(args_s)) if args_s else ()
        ret = parse_type_ref(t[close + 3:])
        return FunctionType(params, ret)
    lb = t.find("[")
    if lb >= 0 and t.endswith("]"):
        close = _find_matching(t, lb, "[", "]")
        if close == len(t) - 1:
            base = parse_type_ref(t[:lb])
            args = tuple(parse_type_ref(a) for a in split_top_level(t[lb + 1:close]))
            return GenericType(base, args)
    return NamedType(t)


def format_type_ref(ref) -> str | None:
    if ref is None or not isinstance(ref, (NamedType, PointerType, SliceType, ArrayTypeRef, FunctionType, GenericType)):
        return ref
    if isinstance(ref, NamedType):
        return ref.name
    if isinstance(ref, PointerType):
        return ("?*" if ref.nullable else "*") + format_type_ref(ref.inner)
    if isinstance(ref, SliceType):
        return "[]" + format_type_ref(ref.elem)
    if isinstance(ref, ArrayTypeRef):
        return f"[{ref.length}]{format_type_ref(ref.elem)}"
    if isinstance(ref, FunctionType):
        return f"fn({','.join(format_type_ref(p) for p in ref.params)})->{format_type_ref(ref.ret)}"
    if isinstance(ref, GenericType):
        return f"{format_type_ref(ref.base)}[{','.join(format_type_ref(a) for a in ref.args)}]"
    raise TypeParseError(f"unknown type ref {ref!r}")


def rewrite_type(t, fn):
    ref = parse_type_ref(t)

    def walk(r):
        if r is None:
            return None
        if isinstance(r, NamedType):
            repl = fn(r.name)
            return parse_type_ref(repl) if repl != r.name else r
        if isinstance(r, PointerType):
            return PointerType(walk(r.inner), r.nullable)
        if isinstance(r, SliceType):
            return SliceType(walk(r.elem))
        if isinstance(r, ArrayTypeRef):
            return ArrayTypeRef(r.length, walk(r.elem))
        if isinstance(r, FunctionType):
            return FunctionType(tuple(walk(p) for p in r.params), walk(r.ret))
        if isinstance(r, GenericType):
            return GenericType(walk(r.base), tuple(walk(a) for a in r.args))
        return r

    return format_type_ref(walk(ref))


def parse_type_app(t: str) -> tuple[str, list[str]] | None:
    ref = parse_type_ref(t)
    if isinstance(ref, GenericType) and isinstance(ref.base, NamedType):
        return ref.base.name, [format_type_ref(a) for a in ref.args]
    return None


def parse_fn_type(t: str):
    ref = parse_type_ref(t)
    if isinstance(ref, FunctionType):
        return [format_type_ref(p) for p in ref.params], format_type_ref(ref.ret)
    return None


def parse_slice_type(t: str):
    ref = parse_type_ref(t)
    if isinstance(ref, SliceType):
        return format_type_ref(ref.elem)
    return None


def parse_array_type(t: str):
    ref = parse_type_ref(t)
    if isinstance(ref, ArrayTypeRef):
        return ref.length, format_type_ref(ref.elem)
    return None
