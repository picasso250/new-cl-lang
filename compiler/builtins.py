"""Builtin function signatures.

This is the temporary boundary between language core, runtime test hooks,
and functions that should eventually move behind std imports.
"""

from compiler.type_ref import parse_map_type


NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}
SIGNED_NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "f32", "f64"}
SCALAR_TYPES = NUMERIC_TYPES | {"str", "bool", "rune"}
STRINGIFIABLE_TYPES = SCALAR_TYPES


def infer_builtin_call(node, require_arg_count, require_type, fail) -> str | None:
    name = node.name
    args = node.args

    if name in {"io.print", "io.println"}:
        require_arg_count(args, 1, name, node)
        return "void"
    if name == "fs.read_file":
        require_arg_count(args, 1, "fs.read_file", node)
        require_type(args[0].type, "str", "fs.read_file path", node)
        return "str"
    if name == "fs.write_file":
        require_arg_count(args, 2, "fs.write_file", node)
        require_type(args[0].type, "str", "fs.write_file path", node)
        require_type(args[1].type, "str", "fs.write_file content", node)
        return "void"
    if name == "append":
        require_arg_count(args, 2, "append", node)
        if not args[0].type.startswith("[]"):
            fail(f"append: expected slice, got {args[0].type}", node)
        require_type(args[1].type, args[0].type[2:], "append element", node)
        return args[0].type
    if name == "cap":
        require_arg_count(args, 1, "cap", node)
        if not args[0].type.startswith("[]"):
            fail(f"cap: expected slice, got {args[0].type}", node)
        return "i32"
    if name == "copy":
        require_arg_count(args, 2, "copy", node)
        if not args[0].type.startswith("[]"):
            fail(f"copy dst: expected slice, got {args[0].type}", node)
        if not args[1].type.startswith("[]"):
            fail(f"copy src: expected slice, got {args[1].type}", node)
        require_type(args[1].type, args[0].type, "copy src", args[1])
        return "i32"
    if name == "clear":
        require_arg_count(args, 1, "clear", node)
        if not (args[0].type.startswith("[]") or parse_map_type(args[0].type) is not None):
            fail(f"clear: expected slice or map, got {args[0].type}", node)
        return "void"
    if name == "map_has":
        require_arg_count(args, 2, "map_has", node)
        map_args = parse_map_type(args[0].type)
        if map_args is None:
            fail(f"map_has: expected map, got {args[0].type}", node)
        key_type, _value_type = map_args
        require_type(args[1].type, key_type, "map_has key", args[1])
        return "i32"
    if name == "delete":
        require_arg_count(args, 2, "delete", node)
        map_args = parse_map_type(args[0].type)
        if map_args is None:
            fail(f"delete: expected map, got {args[0].type}", node)
        key_type, _value_type = map_args
        require_type(args[1].type, key_type, "delete key", args[1])
        return "void"
    map_args = parse_map_type(name)
    if map_args is not None:
        require_arg_count(args, 0, name, node)
        if len(map_args) != 2:
            fail(f"map: expected 2 type args, got {len(map_args)}", node)
        key_type, value_type = map_args
        if key_type not in SCALAR_TYPES:
            fail(f"map key type: expected scalar, got {key_type}", node)
        if value_type not in SCALAR_TYPES:
            fail(f"map value type: expected scalar, got {value_type}", node)
        return name
    if name == "str":
        require_arg_count(args, 1, "str", node)
        if args[0].type not in STRINGIFIABLE_TYPES:
            fail(f"str: cannot convert {args[0].type} to str", node)
        return "str"
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
        if not (arg_type == "str" or parse_map_type(arg_type) is not None or arg_type.startswith("[]")):
            fail(f"len: expected str, map, or slice, got {arg_type}", node)
        return "i32"
    return None
