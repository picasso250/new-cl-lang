"""Builtin function signatures.

This is the temporary boundary between language core, runtime test hooks,
and functions that should eventually move behind std imports.
"""

from compiler.type_ref import PointerType, SliceType, as_map_type, as_pointer_type, as_slice_type, parse_type_ref


NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}
SIGNED_NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "f32", "f64"}
SCALAR_TYPES = NUMERIC_TYPES | {"str", "bool", "rune", "error"}
STRINGIFIABLE_TYPES = SCALAR_TYPES


def infer_builtin_call(node, require_arg_count, require_type, fail) -> str | None:
    name = node.name
    args = node.args

    if name in {"io.print", "io.println"}:
        require_arg_count(args, 1, name, node)
        return "void"
    if name == "append":
        require_arg_count(args, 2, "append", node)
        slice_type = as_slice_type(args[0].type)
        if slice_type is None:
            fail(f"append: expected slice, got {args[0].type}", node)
        require_type(args[1].type, slice_type.elem, "append element", node)
        return args[0].type
    if name == "cap":
        require_arg_count(args, 1, "cap", node)
        if as_slice_type(args[0].type) is None:
            fail(f"cap: expected slice, got {args[0].type}", node)
        return "i32"
    if name == "copy":
        require_arg_count(args, 2, "copy", node)
        if as_slice_type(args[0].type) is None:
            fail(f"copy dst: expected slice, got {args[0].type}", node)
        if as_slice_type(args[1].type) is None:
            fail(f"copy src: expected slice, got {args[1].type}", node)
        require_type(args[1].type, args[0].type, "copy src", args[1])
        return "i32"
    if name == "clear":
        require_arg_count(args, 1, "clear", node)
        if not (as_slice_type(args[0].type) is not None or as_map_type(args[0].type) is not None):
            fail(f"clear: expected slice or map, got {args[0].type}", node)
        return "void"
    if name == "delete":
        require_arg_count(args, 2, "delete", node)
        map_args = as_map_type(args[0].type)
        if map_args is None:
            fail(f"delete: expected map, got {args[0].type}", node)
        key_type, _value_type = map_args
        require_type(args[1].type, key_type, "delete key", args[1])
        return "void"
    if name == "str":
        require_arg_count(args, 1, "str", node)
        if args[0].type == "[]u8":
            return "str"
        ptr = as_pointer_type(args[0].type)
        if ptr is not None and ptr.inner in {"i8", "u8"}:
            return "str"
        if args[0].type not in STRINGIFIABLE_TYPES:
            fail(f"str: cannot convert {args[0].type} to str", node)
        return "str"
    if name == "__nc_bytes_alloc":
        require_arg_count(args, 1, "__nc_bytes_alloc", node)
        require_type(args[0].type, "u64", "__nc_bytes_alloc len", node)
        return "[]u8"
    if name in {"min", "max"}:
        require_arg_count(args, 2, name, node)
        if args[0].type not in NUMERIC_TYPES:
            fail(f"{name}: expected numeric value, got {args[0].type}", node)
        require_type(args[1].type, args[0].type, f"{name} rhs", args[1])
        return args[0].type
    if name == "abs":
        require_arg_count(args, 1, "abs", node)
        if args[0].type not in SIGNED_NUMERIC_TYPES:
            fail(f"abs: expected signed numeric value, got {args[0].type}", node)
        return args[0].type
    if name == "rune":
        require_arg_count(args, 1, "rune", node)
        if args[0].type not in {"i32", "u32"}:
            fail(f"rune: expected i32 or u32 value, got {args[0].type}", node)
        return "rune"
    if name in NUMERIC_TYPES:
        require_arg_count(args, 1, name, node)
        arg_type = args[0].type
        if name == "i32" and arg_type == "str":
            return "i32"
        if name in {"i32", "u32"} and arg_type == "rune":
            return name
        if arg_type not in NUMERIC_TYPES:
            fail(f"{name}: expected numeric value, got {arg_type}", node)
        return name
    if name == "runtime.gc_collect":
        require_arg_count(args, 0, "runtime.gc_collect", node)
        return "void"
    if name == "runtime.gc_live":
        require_arg_count(args, 0, "runtime.gc_live", node)
        return "i32"
    if name == "len":
        require_arg_count(args, 1, "len", node)
        arg_type = args[0].type
        if not (arg_type == "str" or as_map_type(arg_type) is not None or as_slice_type(arg_type) is not None):
            fail(f"len: expected str, map, or slice, got {arg_type}", node)
        return "i32"
    return None
