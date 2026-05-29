"""Small C fragments that remain program-specialized."""

from compiler.c_abi import slice_append_name, slice_copy_name, slice_type_name, type_to_c


def emit_slice(slice_types: set[str]) -> list[str]:
    lines = []
    for elem_type in sorted(slice_types):
        slice_name = slice_type_name(elem_type)
        elem_c = type_to_c(elem_type)
        append_name = slice_append_name(elem_type)
        copy_name = slice_copy_name(elem_type)
        lines.extend([
            f"typedef struct {{ {elem_c}* ptr; uint64_t len; uint64_t cap; }} {slice_name};",
            "",
            f"static {slice_name} {copy_name}({elem_c}* src, uint64_t len) {{",
            f"    {slice_name} s = {{0, 0, 0}};",
            f"    __nc_slice_copy_raw((nc_slice_raw*)&s, src, len, sizeof({elem_c}));",
            "    return s;",
            "}",
            "",
            f"static {slice_name} {append_name}({slice_name} s, {elem_c} elem) {{",
            f"    {slice_name} out = {{0, 0, 0}};",
            f"    __nc_slice_append_raw((nc_slice_raw*)&out, (const nc_slice_raw*)&s, &elem, sizeof({elem_c}));",
            "    return out;",
            "}",
            "",
        ])
    return lines


def emit_runtime(slice_types: set[str]) -> list[str]:
    lines = [
        '#include "ncrt.h"',
        "#include <stdio.h>",
        "#include <string.h>",
        "",
    ]
    lines.extend(emit_slice(slice_types))
    return lines
