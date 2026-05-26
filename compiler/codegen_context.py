"""Shared mutable state helpers for C code generation."""

from compiler.codegen_collect import parse_fn_type


class CodegenContext:
    def __init__(self):
        self.gc_vars = {}
        self.struct_fields = {}
        self.tmp_id = 0
        self.expr_indent = 1

    def next_tmp(self, prefix="__nc_tmp"):
        name = f"{prefix}_{self.tmp_id}"
        self.tmp_id += 1
        return name

    def reset_function_state(self):
        self.gc_vars.clear()

    def set_structs(self, structs):
        self.struct_fields = {s.name: list(s.fields) for s in structs}

    def _array_parts(self, nc_type):
        if not (isinstance(nc_type, str) and nc_type.startswith("[")):
            return None
        size, elem = nc_type[1:].split("]", 1)
        return int(size), elem

    def root_slot_lines_for_type(self, c_name, nc_type):
        lines = []
        if nc_type == "nc_map":
            lines.append(f"__nc_gc_push_root_slot((void*)&{c_name}.entries);")
            return lines
        if nc_type == "str":
            lines.append(f"__nc_gc_push_root_slot((void*)&{c_name}.ptr);")
            return lines
        if isinstance(nc_type, str) and nc_type.startswith("[]"):
            lines.append(f"__nc_gc_push_root_slot((void*)&{c_name}.ptr);")
            return lines
        if isinstance(nc_type, str) and (nc_type.startswith("*") or nc_type.startswith("?*")):
            lines.append(f"__nc_gc_push_root_slot((void*)&{c_name});")
            return lines
        if parse_fn_type(nc_type) is not None:
            lines.append(f"__nc_gc_push_root_slot((void*)&{c_name}.env);")
            return lines
        if isinstance(nc_type, str) and nc_type in self.struct_fields:
            for fname, ftype in self.struct_fields[nc_type]:
                lines.extend(self.root_slot_lines_for_type(f"{c_name}.{fname}", ftype))
            return lines
        arr = self._array_parts(nc_type)
        if arr is not None:
            n, elem_t = arr
            for i in range(n):
                lines.extend(self.root_slot_lines_for_type(f"{c_name}[{i}]", elem_t))
            return lines
        return lines

    def tracked_root_expr(self, name, nc_type):
        lines = self.root_slot_lines_for_type(name, nc_type)
        if lines:
            self.gc_vars[name] = nc_type
        return lines

    def root_push_for_type(self, c_name, nc_type):
        return self.root_slot_lines_for_type(c_name, nc_type)

    def track_var(self, name, nc_type):
        self.gc_vars[name] = nc_type
