"""Internal helpers for NC type references.

TypeRef is the structured representation used by the frontend.  The compiler
still keeps a canonical string form for ABI names, map descriptors and a few
legacy codegen paths; user diagnostics should use format_type_ref_user().
"""

from __future__ import annotations

from dataclasses import dataclass


class TypeRefBase:
    def __str__(self):
        return format_type_ref_user(self)

    def __eq__(self, other):
        try:
            return type_key(self) == type_key(other)
        except TypeParseError:
            return False

    def __hash__(self):
        return hash(type_key(self))

    def startswith(self, prefix):
        return type_key(self).startswith(prefix)

    def endswith(self, suffix):
        return type_key(self).endswith(suffix)

    def lstrip(self, chars=None):
        return type_key(self).lstrip(chars)

    def split(self, sep=None, maxsplit=-1):
        return type_key(self).split(sep, maxsplit)

    def rsplit(self, sep=None, maxsplit=-1):
        return type_key(self).rsplit(sep, maxsplit)

    def __len__(self):
        return len(type_key(self))

    def __getitem__(self, item):
        return type_key(self)[item]

    def __iter__(self):
        return iter(type_key(self))

    def __contains__(self, item):
        return item in type_key(self)

    def __add__(self, other):
        return type_key(self) + other

    def __radd__(self, other):
        return other + type_key(self)


@dataclass(frozen=True, eq=False)
class NamedType(TypeRefBase):
    name: str


@dataclass(frozen=True, eq=False)
class PointerType(TypeRefBase):
    inner: "TypeRef"
    nullable: bool = False


@dataclass(frozen=True, eq=False)
class SliceType(TypeRefBase):
    elem: "TypeRef"


@dataclass(frozen=True, eq=False)
class ArrayTypeRef(TypeRefBase):
    length: int
    elem: "TypeRef"


@dataclass(frozen=True, eq=False)
class FunctionType(TypeRefBase):
    params: tuple["TypeRef", ...]
    ret: "TypeRef"
    fallible: bool = False


@dataclass(frozen=True, eq=False)
class GenericType(TypeRefBase):
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
    if t is None:
        return t
    if isinstance(t, (NamedType, PointerType, SliceType, ArrayTypeRef, FunctionType, GenericType)):
        return t
    if not isinstance(t, str):
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
        ret_s = t[close + 3:].strip()
        fallible = False
        if ret_s.endswith(" err"):
            fallible = True
            ret_s = ret_s[:-4].strip()
        ret = parse_type_ref(ret_s)
        return FunctionType(params, ret, fallible)
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
        suffix = " err" if ref.fallible else ""
        return f"fn({','.join(format_type_ref(p) for p in ref.params)})->{format_type_ref(ref.ret)}{suffix}"
    if isinstance(ref, GenericType):
        return f"{format_type_ref(ref.base)}[{','.join(format_type_ref(a) for a in ref.args)}]"
    raise TypeParseError(f"unknown type ref {ref!r}")


def format_type_ref_user(ref) -> str | None:
    ref = parse_type_ref(ref)
    if ref is None or not isinstance(ref, (NamedType, PointerType, SliceType, ArrayTypeRef, FunctionType, GenericType)):
        return ref
    if isinstance(ref, NamedType):
        return ref.name
    if isinstance(ref, PointerType):
        return ("?*" if ref.nullable else "*") + format_type_ref_user(ref.inner)
    if isinstance(ref, SliceType):
        return "[]" + format_type_ref_user(ref.elem)
    if isinstance(ref, ArrayTypeRef):
        return f"[{ref.length}]{format_type_ref_user(ref.elem)}"
    if isinstance(ref, FunctionType):
        suffix = " err" if ref.fallible else ""
        return f"fun({', '.join(format_type_ref_user(p) for p in ref.params)}) {format_type_ref_user(ref.ret)}{suffix}"
    if isinstance(ref, GenericType):
        return f"{format_type_ref_user(ref.base)}[{','.join(format_type_ref_user(a) for a in ref.args)}]"
    raise TypeParseError(f"unknown type ref {ref!r}")


def ensure_type_ref(t):
    return parse_type_ref(t)


def type_key(t) -> str | None:
    return format_type_ref(parse_type_ref(t))


def same_type(a, b) -> bool:
    return type_key(a) == type_key(b)


def type_name(t) -> str | None:
    ref = parse_type_ref(t)
    return ref.name if isinstance(ref, NamedType) else None


def rewrite_type_ref(t, fn):
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
            return FunctionType(tuple(walk(p) for p in r.params), walk(r.ret), r.fallible)
        if isinstance(r, GenericType):
            return GenericType(walk(r.base), tuple(walk(a) for a in r.args))
        return r

    return walk(ref)


def rewrite_type(t, fn):
    return format_type_ref(rewrite_type_ref(t, fn))


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


def is_fallible_fn_type(t: str) -> bool:
    ref = parse_type_ref(t)
    return isinstance(ref, FunctionType) and ref.fallible


def parse_slice_type(t: str):
    ref = parse_type_ref(t)
    if isinstance(ref, SliceType):
        return format_type_ref(ref.elem)
    return None


def parse_map_type(t: str):
    app = parse_type_app(t)
    if app is None:
        return None
    base, args = app
    if base == "map":
        return args
    return None


def parse_array_type(t: str):
    ref = parse_type_ref(t)
    if isinstance(ref, ArrayTypeRef):
        return ref.length, format_type_ref(ref.elem)
    return None


def as_pointer_type(t):
    ref = parse_type_ref(t)
    return ref if isinstance(ref, PointerType) else None


def as_slice_type(t):
    ref = parse_type_ref(t)
    return ref if isinstance(ref, SliceType) else None


def as_array_type(t):
    ref = parse_type_ref(t)
    return ref if isinstance(ref, ArrayTypeRef) else None


def as_function_type(t):
    ref = parse_type_ref(t)
    return ref if isinstance(ref, FunctionType) else None


def as_map_type(t):
    ref = parse_type_ref(t)
    if (isinstance(ref, GenericType)
            and isinstance(ref.base, NamedType)
            and ref.base.name == "map"
            and len(ref.args) == 2):
        return ref.args
    return None
