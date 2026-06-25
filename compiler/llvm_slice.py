from llvmlite import ir

from compiler.ast import SliceExpr, SliceLiteral
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import I8PTR, RAW_SLICE_TYPE, STR_TYPE, llvm_type
from compiler.type_ref import parse_array_type, parse_map_type, parse_slice_type


class SliceEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_slice_literal(self, node: SliceLiteral):
        elem_type = node.elem_type
        count = len(node.elements)
        ptr = self.ctx.malloc_array(elem_type, ir.Constant(ir.IntType(64), count))
        for i, elem in enumerate(node.elements):
            elem_ptr = self.ctx.builder.gep(
                ptr,
                [ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name="slice.elem.ptr",
            )
            self.ctx.builder.store(self.ctx.cast_to(self.ctx.emit_expr(elem), elem_type), elem_ptr)
        return self.slice_value(elem_type, ptr, count, count)

    def emit_slice_expr(self, node: SliceExpr):
        source_type = node.array.type
        if source_type == "str":
            return self.emit_str_slice(node)
        array_info = parse_array_type(source_type)
        slice_elem_type = parse_slice_type(source_type)
        if array_info is None and slice_elem_type is None:
            raise NotImplementedError(f"LLVM backend cannot slice {source_type}")
        if array_info is not None:
            array_len, elem_type = array_info
            default_end = ir.Constant(ir.IntType(32), array_len)
            source_slot, _source_type = self.ctx.emit_lvalue(node.array)
            source_ptr = self.ctx.builder.load(source_slot, name="array.ptr")
            source_indices = lambda i: [i]
        else:
            elem_type = slice_elem_type
            source_value = self.ctx.emit_expr(node.array)
            source_ptr = self.ctx.builder.extract_value(source_value, 0)
            source_len = self.ctx.builder.extract_value(source_value, 1)
            default_end = self.ctx.builder.trunc(source_len, ir.IntType(32))
            source_indices = lambda i: [i]
        start = self.ctx.cast_to(self.ctx.emit_expr(node.start), "i32") if node.start else ir.Constant(ir.IntType(32), 0)
        end = self.ctx.cast_to(self.ctx.emit_expr(node.end), "i32") if node.end else default_end
        count32 = self.ctx.builder.sub(end, start, name="slice.count32")
        count64 = self.ctx.builder.sext(count32, ir.IntType(64), name="slice.count64")
        source_i = self.ctx.builder.add(start, ir.Constant(ir.IntType(32), 0), name="slice.source.start")
        source_elem_ptr = self.ctx.builder.gep(source_ptr, source_indices(source_i))
        return self.emit_slice_copy_raw(elem_type, source_elem_ptr, count64)

    def emit_str_slice(self, node: SliceExpr):
        self.ctx.ensure_ncrt_runtime()
        source = self.ctx.emit_expr(node.array)
        source_len = self.ctx.builder.extract_value(source, 1)
        start = self.ctx.cast_to(self.ctx.emit_expr(node.start), "i32") if node.start else ir.Constant(ir.IntType(32), 0)
        end = self.ctx.cast_to(self.ctx.emit_expr(node.end), "i32") if node.end else self.ctx.builder.trunc(source_len, ir.IntType(32))
        start64 = self.ctx.builder.zext(start, ir.IntType(64), name="str.slice.start64")
        end64 = self.ctx.builder.zext(end, ir.IntType(64), name="str.slice.end64")
        out = self.ctx.alloca_at_entry("__nc_str_slice_out", STR_TYPE)
        source_ptr = self.ctx.value_to_stack_ptr(source, STR_TYPE, "__nc_str_slice_source")
        self.ctx.builder.call(self.ctx.str_slice_fn, [out, source_ptr, start64, end64])
        return self.ctx.builder.load(out, name="str.slice")

    def slice_value(self, elem_type, ptr, length, cap):
        if isinstance(length, int):
            length = ir.Constant(ir.IntType(64), length)
        if isinstance(cap, int):
            cap = ir.Constant(ir.IntType(64), cap)
        value = ir.Constant(llvm_type(f"[]{elem_type}"), ir.Undefined)
        value = self.ctx.builder.insert_value(value, ptr, [0], name="slice.ptr")
        value = self.ctx.builder.insert_value(value, length, [1], name="slice.len")
        value = self.ctx.builder.insert_value(value, cap, [2], name="slice.cap")
        return value

    def emit_slice_copy_raw(self, elem_type: str, source_ptr, count64):
        self.ctx.ensure_ncrt_runtime()
        slice_type = llvm_type(f"[]{elem_type}")
        out = self.ctx.alloca_at_entry("__nc_slice_copy_out", slice_type)
        self.ctx.builder.call(
            self.ctx.slice_copy_fn,
            [
                self.ctx.builder.bitcast(out, RAW_SLICE_TYPE.as_pointer()),
                self.ctx.builder.bitcast(source_ptr, I8PTR),
                count64,
                ir.Constant(ir.IntType(64), self.ctx.aligned_sizeof_type(elem_type)),
            ],
        )
        return self.ctx.builder.load(out, name="slice.copy")

    def emit_append(self, slice_expr, elem_expr, elem_type: str):
        self.ctx.ensure_ncrt_runtime()
        slice_type = llvm_type(f"[]{elem_type}")
        source = self.ctx.emit_expr(slice_expr)
        source_slot = self.ctx.value_to_stack_ptr(source, slice_type, "__nc_append_source")
        elem_value = self.ctx.cast_to(self.ctx.emit_expr(elem_expr), elem_type)
        elem_slot = self.ctx.value_to_stack_ptr(elem_value, llvm_type(elem_type), "__nc_append_elem")
        out = self.ctx.alloca_at_entry("__nc_append_out", slice_type)
        self.ctx.builder.call(
            self.ctx.slice_append_fn,
            [
                self.ctx.builder.bitcast(out, RAW_SLICE_TYPE.as_pointer()),
                self.ctx.builder.bitcast(source_slot, RAW_SLICE_TYPE.as_pointer()),
                self.ctx.builder.bitcast(elem_slot, I8PTR),
                ir.Constant(ir.IntType(64), self.ctx.aligned_sizeof_type(elem_type)),
            ],
        )
        return self.ctx.builder.load(out, name="slice.append")

    def emit_slice_copy_into(self, dst_expr, src_expr):
        self.ctx.ensure_ncrt_runtime()
        elem_type = parse_slice_type(dst_expr.type)
        if elem_type is None:
            raise NotImplementedError(f"LLVM backend cannot copy into {dst_expr.type}")
        slice_type = llvm_type(dst_expr.type)
        dst = self.ctx.emit_expr(dst_expr)
        src = self.ctx.emit_expr(src_expr)
        dst_slot = self.ctx.value_to_stack_ptr(dst, slice_type, "__nc_copy_dst")
        src_slot = self.ctx.value_to_stack_ptr(src, slice_type, "__nc_copy_src")
        return self.ctx.builder.call(
            self.ctx.slice_copy_into_fn,
            [
                self.ctx.builder.bitcast(dst_slot, RAW_SLICE_TYPE.as_pointer()),
                self.ctx.builder.bitcast(src_slot, RAW_SLICE_TYPE.as_pointer()),
                ir.Constant(ir.IntType(64), self.ctx.aligned_sizeof_type(elem_type)),
            ],
            name="slice.copy.into",
        )

    def emit_clear(self, expr):
        self.ctx.ensure_ncrt_runtime()
        elem_type = parse_slice_type(expr.type)
        if elem_type is not None:
            value = self.ctx.emit_expr(expr)
            slot = self.ctx.value_to_stack_ptr(value, llvm_type(expr.type), "__nc_clear_slice")
            self.ctx.builder.call(
                self.ctx.slice_clear_fn,
                [
                    self.ctx.builder.bitcast(slot, RAW_SLICE_TYPE.as_pointer()),
                    ir.Constant(ir.IntType(64), self.ctx.aligned_sizeof_type(elem_type)),
                ],
            )
            return ir.Constant(ir.IntType(1), 0)
        if parse_map_type(expr.type) is not None:
            self.ctx.builder.call(self.ctx.map_clear_fn, [self.ctx.map_pointer_for_expr(expr)])
            return ir.Constant(ir.IntType(1), 0)
        raise NotImplementedError(f"LLVM backend cannot clear {expr.type}")
