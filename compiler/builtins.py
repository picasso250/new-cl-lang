"""Builtin function signatures.

This is the temporary boundary between language core, runtime test hooks,
and functions that should eventually move behind std imports.
"""

NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}


def infer_builtin_call(node, require_arg_count, require_type, fail) -> str | None:
    name = node.name
    args = node.args

    if name == "io.println":
        require_arg_count(args, 1, "io.println", node)
        return "void"
    if name == "read_file":
        require_arg_count(args, 1, "read_file", node)
        require_type(args[0].type, "str", "read_file path", node)
        return "str"
    if name == "write_file":
        require_arg_count(args, 2, "write_file", node)
        require_type(args[0].type, "str", "write_file path", node)
        require_type(args[1].type, "str", "write_file content", node)
        return "void"
    if name == "append":
        require_arg_count(args, 2, "append", node)
        if not args[0].type.startswith("[]"):
            fail(f"append: expected slice, got {args[0].type}", node)
        require_type(args[1].type, args[0].type[2:], "append element", node)
        return args[0].type
    if name == "map_new":
        return "nc_map"
    if name == "map_set_s":
        return "void"
    if name == "map_get_s":
        return "str"
    if name == "map_has":
        return "i32"
    if name == "str":
        require_arg_count(args, 1, "str", node)
        return "str"
    if name in NUMERIC_TYPES:
        require_arg_count(args, 1, name, node)
        arg_type = args[0].type
        if name == "i32" and arg_type == "str":
            return "i32"
        if arg_type not in NUMERIC_TYPES:
            fail(f"{name}: expected numeric value, got {arg_type}", node)
        return name
    if name == "gc_collect":
        return "void"
    if name == "gc_live":
        return "i32"
    if name == "len":
        require_arg_count(args, 1, "len", node)
        arg_type = args[0].type
        if not (arg_type == "str" or arg_type == "nc_map" or arg_type.startswith("[]")):
            fail(f"len: expected str, map, or slice, got {arg_type}", node)
        return "i32"
    return None
