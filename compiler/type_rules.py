"""Type rule helpers used by the typechecker.

This module keeps low-state semantic predicates out of the AST traversal pass.
It intentionally preserves the existing string-based type boundary for now.
"""

from compiler.builtins import NUMERIC_TYPES
from compiler.constraints import EQ_CONSTRAINT, HASH_CONSTRAINT, ORD_CONSTRAINT, ZERO_CONSTRAINT
from compiler.type_ref import (
    ArrayTypeRef,
    FunctionType,
    GenericType,
    NamedType,
    PointerType,
    SliceType,
    format_type_ref,
    parse_fn_type,
    parse_map_type,
    parse_type_ref,
)


FLOAT_TYPES = {"f32", "f64"}


class TypeRules:
    def __init__(self, symtab, fail, require_public_qualified):
        self.symtab = symtab
        self.fail = fail
        self.require_public_qualified = require_public_qualified

    def is_pointer_type(self, t):
        return isinstance(t, str) and t.startswith("*") and not t.startswith("?*")

    def is_nullable_pointer_type(self, t):
        return isinstance(t, str) and t.startswith("?*")

    def nonnullable_pointer_type(self, t):
        return "*" + t[2:] if self.is_nullable_pointer_type(t) else t

    def is_nil_type(self, t):
        return t == "__nil"

    def is_numeric_type(self, t):
        return t in NUMERIC_TYPES

    def is_integer_type(self, t):
        return t in {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}

    def is_rune_type(self, t):
        return t == "rune"

    def is_iface_type(self, t):
        return isinstance(t, str) and t in getattr(self.symtab, "_ifaces", {})

    def hash_comparable_error_type(self, t, seen=None):
        seen = seen or set()
        if t in seen:
            return None
        seen.add(t)
        if t in FLOAT_TYPES:
            return t
        if t in NUMERIC_TYPES or t in {"bool", "str", "rune"}:
            return None
        if t == "error":
            return t
        if self.is_pointer_type(t) or self.is_nullable_pointer_type(t):
            return None
        if parse_map_type(t) is not None:
            return t
        if parse_fn_type(t) is not None:
            return t
        ref = parse_type_ref(t)
        if isinstance(ref, SliceType) or isinstance(ref, ArrayTypeRef) or isinstance(ref, FunctionType):
            return t
        if self.is_iface_type(t):
            return t
        try:
            sym = self.symtab.lookup(t)
        except NameError:
            return t
        if sym.nc_type == "enum":
            return None
        if sym.nc_type == "struct":
            for _fname, ftype in self.symtab.lookup_struct(t).items():
                err = self.hash_comparable_error_type(ftype, seen)
                if err is not None:
                    return err
            return None
        return t

    def require_hash_comparable(self, t, node=None):
        err = self.hash_comparable_error_type(t)
        if err is not None:
            self.fail(f"map key type: expected hash-comparable, got {err}", node)

    def zero_value_error_type(self, t, seen=None):
        seen = seen or set()
        if t in seen:
            return None
        seen.add(t)
        if t == "void":
            return t
        if t in NUMERIC_TYPES or t in {"bool", "str", "rune"}:
            return None
        if self.is_pointer_type(t):
            return t
        if self.is_nullable_pointer_type(t):
            return None
        if parse_map_type(t) is not None:
            return None
        if parse_fn_type(t) is not None:
            return None
        ref = parse_type_ref(t)
        if isinstance(ref, SliceType):
            return None
        if isinstance(ref, ArrayTypeRef):
            return self.zero_value_error_type(format_type_ref(ref.elem), seen)
        if isinstance(ref, FunctionType):
            return None
        if self.is_iface_type(t):
            return None
        try:
            sym = self.symtab.lookup(t)
        except NameError:
            return t
        if sym.nc_type == "enum":
            return None
        if sym.nc_type == "struct":
            for _fname, ftype in self.symtab.lookup_struct(t).items():
                err = self.zero_value_error_type(ftype, seen)
                if err is not None:
                    return err
            return None
        return t

    def require_zero_value_type(self, t, node=None):
        err = self.zero_value_error_type(t)
        if err is not None:
            self.fail(f"map value type: expected zero-value type, got {err}", node)

    def validate_map_type(self, t, node=None):
        map_args = parse_map_type(t)
        if map_args is None:
            return None
        if len(map_args) != 2:
            self.fail(f"map: expected 2 type args, got {len(map_args)}", node)
        key_type, value_type = map_args
        self.require_hash_comparable(key_type, node)
        self.validate_sized_type(value_type, node)
        self.require_zero_value_type(value_type, node)
        return key_type, value_type

    def validate_sized_type(self, t, node=None, *, allow_void=False):
        if t == "void":
            if allow_void:
                return
            self.fail("size_of: void has no size", node)
        ref = parse_type_ref(t)

        def walk(r, *, allow_void_here=False):
            if isinstance(r, NamedType):
                name = r.name
                if name == "void":
                    if allow_void_here:
                        return
                    self.fail("size_of: void has no size", node)
                self.require_public_qualified(name, node)
                if name in NUMERIC_TYPES or name in {"bool", "str", "rune", "error"}:
                    return
                if name == "map":
                    self.fail("size_of: map requires type arguments", node)
                try:
                    sym = self.symtab.lookup(name)
                except NameError:
                    self.fail(f"size_of: unknown type {name}", node)
                if sym.nc_type not in {"struct", "enum", "iface"}:
                    self.fail(f"size_of: unknown type {name}", node)
                return
            if isinstance(r, PointerType):
                walk(r.inner, allow_void_here=True)
                return
            if isinstance(r, SliceType):
                walk(r.elem)
                return
            if isinstance(r, ArrayTypeRef):
                walk(r.elem)
                return
            if isinstance(r, FunctionType):
                for p in r.params:
                    walk(p)
                walk(r.ret, allow_void_here=True)
                return
            if isinstance(r, GenericType):
                if not isinstance(r.base, NamedType):
                    self.fail(f"size_of: unsupported type {t}", node)
                    return
                base = r.base.name
                if base != "map":
                    self.fail(f"size_of: unknown type {base}", node)
                if len(r.args) != 2:
                    self.fail(f"map: expected 2 type args, got {len(r.args)}", node)
                for arg in r.args:
                    walk(arg)
                self.validate_map_type(t, node)
                return
            self.fail(f"size_of: unsupported type {t}", node)

        walk(ref, allow_void_here=allow_void)

    def comparable_error_type(self, t, seen=None):
        seen = seen or set()
        if t in seen:
            return None
        seen.add(t)
        if t in NUMERIC_TYPES or t in {"bool", "str", "rune"}:
            return None
        if t == "error":
            return t
        if self.is_pointer_type(t) or self.is_nullable_pointer_type(t):
            return None
        if parse_map_type(t) is not None:
            return t
        if parse_fn_type(t) is not None:
            return t
        ref = parse_type_ref(t)
        if isinstance(ref, SliceType) or isinstance(ref, ArrayTypeRef) or isinstance(ref, FunctionType):
            return t
        if self.is_iface_type(t):
            return t
        try:
            sym = self.symtab.lookup(t)
        except NameError:
            return t
        if sym.nc_type == "enum":
            return None
        if sym.nc_type == "struct":
            for _fname, ftype in self.symtab.lookup_struct(t).items():
                err = self.comparable_error_type(ftype, seen)
                if err is not None:
                    return err
            return None
        return t

    def require_comparable(self, t, node=None):
        err = self.comparable_error_type(t)
        if err is not None:
            self.fail(f"comparison: type {err} is not comparable", node)

    def constraint_error_type(self, t, constraint):
        if constraint == "any":
            return None
        if constraint == EQ_CONSTRAINT:
            return self.comparable_error_type(t)
        if constraint == ORD_CONSTRAINT:
            return None if t in NUMERIC_TYPES else t
        if constraint == HASH_CONSTRAINT:
            return self.hash_comparable_error_type(t)
        if constraint == ZERO_CONSTRAINT:
            return self.zero_value_error_type(t)
        return t

    def validate_generic_constraints(self, stmt):
        constraints = getattr(stmt, "_generic_constraints", None)
        if not constraints:
            return
        origin_kind = getattr(stmt, "_generic_origin_kind", "function")
        origin_name = getattr(stmt, "_generic_origin_name", getattr(stmt, "name", "<generic>"))
        for _param, arg, constraint in constraints:
            err = self.constraint_error_type(arg, constraint)
            if err is not None:
                self.fail(f"generic {origin_kind} {origin_name}: type arg {arg} does not satisfy {constraint}", stmt)

    def is_extern_abi_type(self, t):
        if t == "void":
            return True
        if t in {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64", "bool"}:
            return True
        if isinstance(t, str) and t.startswith("*"):
            return self.is_extern_abi_type(t[1:])
        if isinstance(t, str) and t.startswith("?*"):
            return self.is_extern_abi_type(t[2:])
        return False
