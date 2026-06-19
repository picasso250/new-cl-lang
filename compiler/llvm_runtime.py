from llvmlite import ir

from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import I8PTR, MAP_DESC_PTR, MAP_TYPE, RAW_SLICE_TYPE, STR_TYPE, llvm_type


class RuntimeEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_print_error(self, value):
        self.ensure_fprintf()
        stderr = self.ctx.builder.call(self.ctx.nc_stderr, [], name="stderr")
        fmt = self.global_c_string("error: %.*s\n", "fmt_error")
        ptr = self.ctx.builder.extract_value(value, 0)
        length64 = self.ctx.builder.extract_value(value, 1)
        length32 = self.ctx.builder.trunc(length64, ir.IntType(32))
        self.ctx.builder.call(self.ctx.fprintf, [stderr, fmt, length32, ptr])

    def ensure_exit(self):
        if self.ctx.exit_fn is None:
            existing = self.ctx.module.globals.get("exit")
            self.ctx.exit_fn = existing if existing is not None else ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [ir.IntType(32)]),
                name="exit",
            )

    def emit_exit(self, code: int):
        self.ensure_exit()
        self.ctx.builder.call(self.ctx.exit_fn, [ir.Constant(ir.IntType(32), code)])

    def ensure_printf(self):
        if self.ctx.printf is None:
            i8ptr = ir.IntType(8).as_pointer()
            self.ctx.printf = ir.Function(self.ctx.module, ir.FunctionType(ir.IntType(32), [i8ptr], var_arg=True), name="printf")

    def ensure_fprintf(self):
        if self.ctx.fprintf is None:
            self.ctx.fprintf = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR], var_arg=True),
                name="fprintf",
            )
            self.ctx.nc_stderr = ir.Function(
                self.ctx.module,
                ir.FunctionType(I8PTR, []),
                name="__nc_stderr",
            )

    def ensure_sprintf(self):
        if self.ctx.sprintf is None:
            self.ctx.sprintf = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR], var_arg=True),
                name="sprintf",
            )

    def ensure_atoi(self):
        if self.ctx.atoi is None:
            self.ctx.atoi = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [I8PTR]),
                name="atoi",
            )

    def ensure_malloc(self):
        if self.ctx.malloc is None:
            self.ctx.malloc = ir.Function(self.ctx.module, ir.FunctionType(I8PTR, [ir.IntType(64)]), name="malloc")

    def ensure_gc_runtime(self):
        self.ensure_ncrt_runtime()

    def ensure_ncrt_runtime(self):
        if self.ctx.gc_alloc is None:
            self.ctx.gc_alloc = ir.Function(
                self.ctx.module,
                ir.FunctionType(I8PTR, [ir.IntType(64)]),
                name="__nc_gc_alloc",
            )
            self.ctx.gc_collect = ir.Function(self.ctx.module, ir.FunctionType(ir.VoidType(), []), name="__nc_gc_collect")
            self.ctx.gc_live = ir.Function(self.ctx.module, ir.FunctionType(ir.IntType(64), []), name="__nc_gc_live")
            self.ctx.gc_init = ir.Function(self.ctx.module, ir.FunctionType(ir.VoidType(), []), name="__nc_gc_init")
            self.ctx.gc_root_mark = ir.Function(self.ctx.module, ir.FunctionType(ir.IntType(64), []), name="__nc_gc_root_mark")
            self.ctx.gc_root_rewind = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [ir.IntType(64)]),
                name="__nc_gc_root_rewind",
            )
            self.ctx.gc_push_root_slot = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [I8PTR]),
                name="__nc_gc_push_root_slot",
            )
            str_ptr = STR_TYPE.as_pointer()
            self.ctx.str_cat_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, str_ptr, str_ptr]),
                name="__nc_str_cat_out",
            )
            self.ctx.str_slice_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, str_ptr, ir.IntType(64), ir.IntType(64)]),
                name="__nc_str_slice_copy_out",
            )
            self.ctx.i32_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(32)]),
                name="__nc_i32_to_str_out",
            )
            self.ctx.i64_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(64)]),
                name="__nc_i64_to_str_out",
            )
            self.ctx.u64_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(64)]),
                name="__nc_u64_to_str_out",
            )
            self.ctx.f64_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, ir.DoubleType()]),
                name="__nc_f64_to_str_out",
            )
            self.ctx.rune_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, ir.IntType(32)]),
                name="__nc_rune_to_str_out",
            )
            self.ctx.str_to_i32_fn = ir.Function(self.ctx.module, ir.FunctionType(ir.IntType(32), [str_ptr]), name="__nc_str_to_i32_ptr")
            self.ctx.cstr_to_str_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [str_ptr, I8PTR]),
                name="__nc_cstr_to_str_out",
            )
            raw_slice_ptr = RAW_SLICE_TYPE.as_pointer()
            self.ctx.os_set_args_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [ir.IntType(32), I8PTR.as_pointer()]),
                name="__nc_os_set_args",
            )
            self.ctx.map_init_fn = ir.Function(self.ctx.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR]), name="__nc_map_init")
            self.ctx.map_get_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [I8PTR, MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]),
                name="__nc_map_get",
            )
            self.ctx.map_set_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR, I8PTR]),
                name="__nc_map_set",
            )
            self.ctx.map_has_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]),
                name="__nc_map_has",
            )
            self.ctx.map_delete_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer(), MAP_DESC_PTR, I8PTR]),
                name="__nc_map_delete",
            )
            self.ctx.map_clear_fn = ir.Function(self.ctx.module, ir.FunctionType(ir.VoidType(), [MAP_TYPE.as_pointer()]), name="__nc_map_clear")
            self.ctx.map_next_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(64), [MAP_TYPE.as_pointer(), ir.IntType(64), I8PTR, I8PTR]),
                name="__nc_map_next",
            )
            self.ctx.slice_copy_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, I8PTR, ir.IntType(64), ir.IntType(64)]),
                name="__nc_slice_copy_raw",
            )
            self.ctx.slice_append_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, raw_slice_ptr, I8PTR, ir.IntType(64)]),
                name="__nc_slice_append_raw",
            )
            self.ctx.slice_copy_into_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [raw_slice_ptr, raw_slice_ptr, ir.IntType(64)]),
                name="__nc_slice_copy_into_raw",
            )
            self.ctx.slice_clear_fn = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [raw_slice_ptr, ir.IntType(64)]),
                name="__nc_slice_clear_raw",
            )

    def malloc_array(self, elem_type: str, count):
        self.ensure_gc_runtime()
        elem_size = ir.Constant(ir.IntType(64), self.ctx.aligned_sizeof_type(elem_type))
        size = self.ctx.builder.mul(count, elem_size, name="malloc.size")
        raw = self.ctx.builder.call(self.ctx.gc_alloc, [size], name="gc.alloc.raw")
        return self.ctx.builder.bitcast(raw, llvm_type(elem_type).as_pointer(), name="malloc.typed")

    def malloc_bytes(self, count):
        self.ensure_gc_runtime()
        return self.ctx.builder.call(self.ctx.gc_alloc, [count], name="malloc.bytes")

    def emit_gc_live(self):
        self.ensure_ncrt_runtime()
        self.ensure_printf()
        fmt = self.global_c_string("%d\n", "fmt_gc_live")
        live64 = self.ctx.builder.call(self.ctx.gc_live, [], name="gc.live")
        live = self.ctx.builder.trunc(live64, ir.IntType(32), name="gc.live.i32")
        self.ctx.builder.call(self.ctx.printf, [fmt, live])
        return live

    def emit_gc_collect(self):
        self.ensure_ncrt_runtime()
        self.ctx.builder.call(self.ctx.gc_collect, [])
        return ir.Constant(ir.IntType(1), 0)

    def ensure_memcmp(self):
        if self.ctx.memcmp is None:
            self.ctx.memcmp = ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR, ir.IntType(64)]),
                name="memcmp",
            )

    def global_c_string(self, text: str, hint: str):
        key = (hint, text)
        if key in self.ctx.strings:
            return self.ctx.strings[key].bitcast(ir.IntType(8).as_pointer())
        raw = bytearray(text.encode("utf-8")) + b"\00"
        typ = ir.ArrayType(ir.IntType(8), len(raw))
        glob = ir.GlobalVariable(self.ctx.module, typ, name=f"__nc_{hint}_{len(self.ctx.strings)}")
        glob.linkage = "internal"
        glob.global_constant = True
        glob.initializer = ir.Constant(typ, raw)
        self.ctx.strings[key] = glob
        return glob.bitcast(ir.IntType(8).as_pointer())

    def empty_string_ptr(self):
        if self.ctx.empty_c_string is None:
            self.ctx.empty_c_string = self.global_c_string("", "empty_c_str")
        return self.ctx.empty_c_string
