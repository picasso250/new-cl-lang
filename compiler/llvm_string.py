from llvmlite import ir

from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import I8PTR, STR_TYPE


class StringEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_str_cat(self, left, right):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_str_cat_out", STR_TYPE)
        left_ptr = self.ctx.value_to_stack_ptr(left, STR_TYPE, "__nc_str_cat_left")
        right_ptr = self.ctx.value_to_stack_ptr(right, STR_TYPE, "__nc_str_cat_right")
        self.ctx.builder.call(self.ctx.str_cat_fn, [out, left_ptr, right_ptr])
        return self.ctx.builder.load(out, name="str.cat")

    def str_value(self, ptr, length):
        value = ir.Constant(STR_TYPE, ir.Undefined)
        value = self.ctx.builder.insert_value(value, ptr, [0], name="str.ptr")
        value = self.ctx.builder.insert_value(value, length, [1], name="str.len")
        return value

    def emit_i32_to_str(self, arg_expr):
        value = self.ctx.cast_to(self.ctx.emit_expr(arg_expr), "i32")
        return self.emit_i32_value_to_str(value)

    def emit_i32_value_to_str(self, value):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_i32_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.i32_to_str_fn, [out, value])
        return self.ctx.builder.load(out, name="i32.str")

    def emit_i64_value_to_str(self, value):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_i64_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.i64_to_str_fn, [out, value])
        return self.ctx.builder.load(out, name="i64.str")

    def emit_u64_value_to_str(self, value):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_u64_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.u64_to_str_fn, [out, value])
        return self.ctx.builder.load(out, name="u64.str")

    def emit_rune_value_to_str(self, value):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_rune_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.rune_to_str_fn, [out, self.ctx.cast_to(value, "rune")])
        return self.ctx.builder.load(out, name="rune.str")

    def emit_f64_value_to_str(self, value):
        self.ctx.ensure_ncrt_runtime()
        out = self.ctx.alloca_at_entry("__nc_f64_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.f64_to_str_fn, [out, value])
        return self.ctx.builder.load(out, name="f64.str")

    def emit_str_to_i32(self, arg_expr):
        self.ctx.ensure_ncrt_runtime()
        value = self.ctx.emit_expr(arg_expr)
        ptr = self.ctx.value_to_stack_ptr(value, STR_TYPE, "__nc_str_to_i32_arg")
        return self.ctx.builder.call(self.ctx.str_to_i32_fn, [ptr], name="str.i32")

    def emit_str_alloc(self, len_expr):
        fn = (
            self.ctx.module.globals["__nc_str_alloc_out"]
            if "__nc_str_alloc_out" in self.ctx.module.globals
            else ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.VoidType(), [STR_TYPE.as_pointer(), ir.IntType(64)]),
                name="__nc_str_alloc_out",
            )
        )
        length = self.ctx.cast_to(self.ctx.emit_expr(len_expr), "u64")
        out = self.ctx.alloca_at_entry("__nc_str_alloc_out", STR_TYPE)
        self.ctx.builder.call(fn, [out, length])
        return self.ctx.builder.load(out, name="str.alloc")

    def emit_bytes_alloc(self, len_expr):
        self.ctx.ensure_ncrt_runtime()
        length = self.ctx.cast_to(self.ctx.emit_expr(len_expr), "u64")
        ptr = self.ctx.builder.call(self.ctx.gc_alloc, [length], name="bytes.alloc.ptr")
        return self.ctx.slice_value("u8", self.ctx.builder.bitcast(ptr, ir.IntType(8).as_pointer()), length, length)

    def emit_u8_slice_to_str(self, arg_expr):
        self.ctx.ensure_ncrt_runtime()
        source = self.ctx.emit_expr(arg_expr)
        source_ptr = self.ctx.builder.extract_value(source, 0, name="u8str.source.ptr")
        length = self.ctx.builder.extract_value(source, 1, name="u8str.len")
        alloc_len = self.ctx.builder.add(length, ir.Constant(ir.IntType(64), 1), name="u8str.alloc.len")
        dest = self.ctx.builder.call(self.ctx.gc_alloc, [alloc_len], name="u8str.dest")
        dest_u8 = self.ctx.builder.bitcast(dest, ir.IntType(8).as_pointer(), name="u8str.dest.u8")
        self.ctx.copy_bytes(
            dest_u8,
            ir.Constant(ir.IntType(64), 0),
            source_ptr,
            ir.Constant(ir.IntType(64), 0),
            length,
            "u8str",
        )
        nul_ptr = self.ctx.builder.gep(dest_u8, [length], inbounds=True, name="u8str.nul.ptr")
        self.ctx.builder.store(ir.Constant(ir.IntType(8), 0), nul_ptr)
        value = ir.Constant(STR_TYPE, None)
        value = self.ctx.builder.insert_value(value, dest_u8, [0], name="u8str.ptr")
        value = self.ctx.builder.insert_value(value, length, [1], name="u8str.out.len")
        return value

    def emit_cstr_to_str(self, arg_expr):
        self.ctx.ensure_ncrt_runtime()
        value = self.ctx.emit_expr(arg_expr)
        ptr = self.ctx.builder.bitcast(value, I8PTR, name="cstr.ptr")
        out = self.ctx.alloca_at_entry("__nc_cstr_to_str_out", STR_TYPE)
        self.ctx.builder.call(self.ctx.cstr_to_str_fn, [out, ptr])
        return self.ctx.builder.load(out, name="cstr.str")

    def emit_str_eq(self, left, right):
        self.ctx.ensure_ncrt_runtime()
        fn = (
            ir.Function(
                self.ctx.module,
                ir.FunctionType(ir.IntType(32), [STR_TYPE.as_pointer(), STR_TYPE.as_pointer()]),
                name="__nc_str_eq_ptr",
            )
            if "__nc_str_eq_ptr" not in self.ctx.module.globals
            else self.ctx.module.globals["__nc_str_eq_ptr"]
        )
        left_ptr = self.ctx.value_to_stack_ptr(left, STR_TYPE, "__nc_str_eq_left")
        right_ptr = self.ctx.value_to_stack_ptr(right, STR_TYPE, "__nc_str_eq_right")
        eq = self.ctx.builder.call(fn, [left_ptr, right_ptr], name="str.eq.i32")
        return self.ctx.builder.icmp_signed("!=", eq, ir.Constant(ir.IntType(32), 0), name="str.eq")
