"""Shared mutable state helpers for C code generation."""

from compiler.codegen_collect import parse_fn_type


class CodegenContext:
    def __init__(self):
        self.gc_vars = {}
        self.tmp_id = 0
        self.expr_indent = 1

    def next_tmp(self, prefix="__nc_tmp"):
        name = f"{prefix}_{self.tmp_id}"
        self.tmp_id += 1
        return name

    def reset_function_state(self):
        self.gc_vars.clear()

    def tracked_root_expr(self, name, nc_type):
        if nc_type == "nc_map":
            self.gc_vars[name] = nc_type
            return f"__nc_gc_push_root((void*){name}.entries);"
        if nc_type == "str":
            self.gc_vars[name] = nc_type
            return f"__nc_gc_push_root((void*){name}.ptr);"
        if isinstance(nc_type, str) and nc_type.startswith("[]"):
            self.gc_vars[name] = nc_type
            return f"__nc_gc_push_root((void*){name}.ptr);"
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            self.gc_vars[name] = nc_type
            return f"__nc_gc_push_root((void*){name});"
        if parse_fn_type(nc_type) is not None:
            self.gc_vars[name] = nc_type
            return f"__nc_gc_push_root((void*){name}.env);"
        return None

    def root_push_for_type(self, c_name, nc_type):
        if nc_type == "nc_map":
            return f"__nc_gc_push_root((void*){c_name}.entries);"
        if nc_type == "str":
            return f"__nc_gc_push_root((void*){c_name}.ptr);"
        if isinstance(nc_type, str) and nc_type.startswith("[]"):
            return f"__nc_gc_push_root((void*){c_name}.ptr);"
        if parse_fn_type(nc_type) is not None:
            return f"__nc_gc_push_root((void*){c_name}.env);"
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            return f"__nc_gc_push_root((void*){c_name});"
        return None

    def track_var(self, name, nc_type):
        self.gc_vars[name] = nc_type
