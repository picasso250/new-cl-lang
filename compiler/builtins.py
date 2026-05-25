"""Builtin function signatures and C lowering hooks.

This is the temporary boundary between language core, runtime test hooks,
and functions that should eventually move behind std imports.
"""


from compiler.c_abi import type_to_c


NUMERIC_TYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}


def infer_builtin_call(node, require_arg_count, require_type, fail) -> str | None:
    name = node.name
    args = node.args

    if name == "print":
        require_arg_count(args, 1, "print", node)
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


def lower_builtin_expr(node, gen_expr, slice_append_name) -> str | None:
    name = node.name

    if name == "read_file":
        arg = node.args[0]
        if type(arg).__name__ == "StringLiteral":
            return f'__nc_read_file("{arg.value}")'
        return f'__nc_read_file({gen_expr(arg)}.ptr)'
    if name == "append":
        slice_c = gen_expr(node.args[0])
        elem_c = gen_expr(node.args[1])
        slice_t = getattr(node.args[0], "type", "[]i32")
        elem_t = slice_t[2:] if slice_t.startswith("[]") else "i32"
        return f'{slice_append_name(elem_t)}({slice_c}, {elem_c})'
    if name == "map_set_s":
        m_c = gen_expr(node.args[0])
        k_c = gen_expr(node.args[1])
        v_c = gen_expr(node.args[2])
        return f'__nc_map_set_str(&{m_c}, {k_c}, {v_c})'
    if name == "map_get_s":
        m_c = gen_expr(node.args[0])
        k_c = gen_expr(node.args[1])
        return f'__nc_map_get_str(&{m_c}, {k_c})'
    if name == "map_has":
        m_c = gen_expr(node.args[0])
        k_c = gen_expr(node.args[1])
        return f'__nc_map_has(&{m_c}, {k_c})'
    if name == "len":
        arg_c = gen_expr(node.args[0])
        return f'(int)({arg_c}).len'
    if name == "str":
        arg_c = gen_expr(node.args[0])
        arg_t = getattr(node.args[0], "type", "i32")
        if arg_t == "i32":
            return f'__nc_i32_to_str({arg_c})'
        return arg_c
    if name in NUMERIC_TYPES:
        arg_c = gen_expr(node.args[0])
        arg_t = getattr(node.args[0], "type", "str")
        if name == "i32" and arg_t == "str":
            return f'__nc_str_to_i32({arg_c})'
        return f'(({type_to_c(name)})({arg_c}))'
    return None


def lower_builtin_stmt(expr, gen_expr, emit_line, pad) -> bool:
    name = expr.name

    if name == "gc_collect":
        emit_line(f'{pad}__nc_gc_collect();')
        return True
    if name == "gc_live":
        emit_line(f'{pad}printf("%d\\n", (int)__nc_gc_live());')
        return True
    if name == "write_file":
        path = expr.args[0]
        content = expr.args[1]
        path_c = f'"{path.value}"' if type(path).__name__ == "StringLiteral" else f'{gen_expr(path)}.ptr'
        emit_line(f'{pad}__nc_write_file({path_c}, {gen_expr(content)});')
        return True
    if name == "print":
        arg = expr.args[0]
        arg_type = getattr(arg, "type", "i32")
        if arg_type == "str":
            arg_c = gen_expr(arg)
            emit_line(f'{pad}printf("%.*s\\n", (int)({arg_c}).len, ({arg_c}).ptr);')
        elif arg_type == "bool":
            emit_line(f'{pad}printf("%d\\n", {gen_expr(arg)});')
        elif arg_type in ("i8", "i16", "i32", "i64"):
            emit_line(f'{pad}printf("%lld\\n", (long long)({gen_expr(arg)}));')
        elif arg_type in ("u8", "u16", "u32", "u64"):
            emit_line(f'{pad}printf("%llu\\n", (unsigned long long)({gen_expr(arg)}));')
        elif arg_type in ("f32", "f64"):
            emit_line(f'{pad}printf("%g\\n", (double)({gen_expr(arg)}));')
        else:
            emit_line(f'{pad}printf("%d\\n", {gen_expr(arg)});')
        return True
    return False
