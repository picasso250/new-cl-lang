from llvmlite import ir

from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import (
    I8PTR, INT_TYPES, MAP_DESC_TYPE, MAP_EQ_FN_TYPE, MAP_HASH_FN_TYPE, MAP_TYPE,
    STR_TYPE,
)
from compiler.type_ref import parse_map_type


class MapEmitter:
    def __init__(self, ctx: CodegenContext, struct_fields, enum_variants, llvm_type):
        self.ctx = ctx
        self.struct_fields = struct_fields
        self.enum_variants = enum_variants
        self.llvm_type = llvm_type

    def map_value(self, desc, entries, cap, length):
        value = ir.Constant(MAP_TYPE, ir.Undefined)
        value = self.ctx.builder.insert_value(value, desc, [0], name="map.desc")
        value = self.ctx.builder.insert_value(value, entries, [1], name="map.entries")
        value = self.ctx.builder.insert_value(value, cap, [2], name="map.cap")
        value = self.ctx.builder.insert_value(value, length, [3], name="map.len")
        value = self.ctx.builder.insert_value(value, ir.Constant(ir.IntType(64), 0), [4], name="map.tombstones")
        return value

    def emit_map_literal(self, node):
        self.ctx.ensure_ncrt_runtime()
        slot = self.ctx.alloca_at_entry("__nc_map_lit", MAP_TYPE)
        self.ctx.builder.call(self.ctx.map_init_fn, [slot, self.map_desc(node.map_type)])
        for key_expr, value_expr in node.entries:
            self.emit_map_set_to_ptr(slot, node.map_type, key_expr, value_expr)
        return self.ctx.builder.load(slot, name="map.lit")

    def map_pointer_for_expr(self, map_expr):
        try:
            map_ptr, map_type = self.ctx.emit_lvalue(map_expr)
            if parse_map_type(map_type) is not None:
                return map_ptr
        except NotImplementedError:
            pass
        slot = self.ctx.alloca_at_entry("__nc_map_tmp", MAP_TYPE)
        self.ctx.builder.store(self.ctx.emit_expr(map_expr), slot)
        return slot

    def emit_map_get(self, map_expr, key_expr):
        self.ctx.ensure_ncrt_runtime()
        _key_type, value_type = parse_map_type(map_expr.type)
        map_ptr = self.map_pointer_for_expr(map_expr)
        key_ptr = self.ctx.value_to_i8_stack_ptr(
            self.ctx.emit_expr(key_expr), self.llvm_type(key_expr.type), "__nc_map_get_key"
        )
        out = self.ctx.alloca_at_entry("__nc_map_get_out", self.llvm_type(value_type))
        self.ctx.builder.call(
            self.ctx.map_get_fn,
            [self.ctx.builder.bitcast(out, I8PTR), map_ptr, self.map_desc(map_expr.type), key_ptr],
        )
        return self.ctx.builder.load(out, name="map.get")

    def emit_map_has(self, map_expr, key_expr):
        self.ctx.ensure_ncrt_runtime()
        map_ptr = self.map_pointer_for_expr(map_expr)
        key_ptr = self.ctx.value_to_i8_stack_ptr(
            self.ctx.emit_expr(key_expr), self.llvm_type(key_expr.type), "__nc_map_has_key"
        )
        return self.ctx.builder.call(self.ctx.map_has_fn, [map_ptr, self.map_desc(map_expr.type), key_ptr], name="map.has")

    def emit_map_delete(self, map_expr, key_expr):
        self.ctx.ensure_ncrt_runtime()
        map_ptr = self.map_pointer_for_expr(map_expr)
        key_ptr = self.ctx.value_to_i8_stack_ptr(
            self.ctx.emit_expr(key_expr), self.llvm_type(key_expr.type), "__nc_map_delete_key"
        )
        self.ctx.builder.call(self.ctx.map_delete_fn, [map_ptr, self.map_desc(map_expr.type), key_ptr])
        return ir.Constant(ir.IntType(1), 0)

    def emit_map_set(self, map_expr, key_expr, value_expr, assign_op="="):
        self.ctx.ensure_ncrt_runtime()
        map_ptr, map_type = self.ctx.emit_lvalue(map_expr)
        map_args = parse_map_type(map_type)
        if map_args is None:
            raise NotImplementedError(f"LLVM backend cannot map-set {map_type}")
        return self.emit_map_set_to_ptr(map_ptr, map_type, key_expr, value_expr, assign_op)

    def emit_map_set_to_ptr(self, map_ptr, map_type, key_expr, value_expr, assign_op="="):
        map_args = parse_map_type(map_type)
        if map_args is None:
            raise NotImplementedError(f"LLVM backend cannot map-set {map_type}")
        _key_type, value_type = map_args
        key = self.ctx.emit_expr(key_expr)
        key_ptr = self.ctx.value_to_i8_stack_ptr(key, self.llvm_type(key_expr.type), "__nc_map_key")
        value = self.ctx.emit_coerced_expr(value_expr, value_type)
        if assign_op != "=":
            old_out = self.ctx.alloca_at_entry("__nc_map_old_out", self.llvm_type(value_type))
            self.ctx.builder.call(
                self.ctx.map_get_fn,
                [self.ctx.builder.bitcast(old_out, I8PTR), map_ptr, self.map_desc(map_type), key_ptr],
            )
            old = self.ctx.builder.load(old_out, name="map.old")
            if value_type == "str" and assign_op == "+=":
                value = self.ctx.emit_str_cat(old, value)
            else:
                value = self.ctx.emit_binary_values(old, assign_op[:-1], value, value_type)
        value_ptr = self.ctx.value_to_i8_stack_ptr(value, self.llvm_type(value_type), "__nc_map_set_value")
        self.ctx.builder.call(self.ctx.map_set_fn, [map_ptr, self.map_desc(map_type), key_ptr, value_ptr])
        return ir.Constant(ir.IntType(1), 0)

    def map_desc(self, map_type: str):
        if map_type in self.ctx.map_descs:
            return self.ctx.map_descs[map_type]
        key_type, value_type = parse_map_type(map_type)
        key_size = self.ctx.sizeof_type(key_type)
        value_size = self.ctx.sizeof_type(value_type)
        key_align = self.ctx.alignof_type(key_type)
        value_align = self.ctx.alignof_type(value_type)
        key_offset = 0
        value_offset = self.ctx.align_to(key_offset + key_size, value_align)
        state_offset = self.ctx.align_to(value_offset + value_size, 4)
        entry_size = self.ctx.align_to(state_offset + 4, max(8, key_align, value_align, 4))
        name = "__nc_map_desc_" + self.type_label(map_type)
        glob = ir.GlobalVariable(self.ctx.module, MAP_DESC_TYPE, name=name)
        glob.linkage = "internal"
        glob.global_constant = True
        glob.initializer = ir.Constant.literal_struct([
            ir.Constant(ir.IntType(64), key_size),
            ir.Constant(ir.IntType(64), value_size),
            ir.Constant(ir.IntType(64), entry_size),
            ir.Constant(ir.IntType(64), key_offset),
            ir.Constant(ir.IntType(64), value_offset),
            ir.Constant(ir.IntType(64), state_offset),
            self.map_hash_fn(key_type),
            self.map_eq_fn(key_type),
        ])
        self.ctx.map_descs[map_type] = glob
        return glob

    def type_label(self, nc_type: str):
        out = []
        for ch in nc_type:
            out.append(ch if ch.isalnum() else "_")
        return "".join(out)

    def map_hash_fn(self, key_type: str):
        if key_type in self.ctx.map_hash_fns:
            return self.ctx.map_hash_fns[key_type]
        fn = ir.Function(self.ctx.module, MAP_HASH_FN_TYPE, name="__nc_map_hash_" + self.type_label(key_type))
        self.ctx.map_hash_fns[key_type] = fn
        entry = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry)
        key_ptr = builder.bitcast(fn.args[0], self.llvm_type(key_type).as_pointer())
        key = builder.load(key_ptr, name="key")
        h = self.emit_map_hash_value(builder, key, key_type, ir.Constant(ir.IntType(64), 14695981039346656037))
        builder.ret(h)
        return fn

    def map_eq_fn(self, key_type: str):
        if key_type in self.ctx.map_eq_fns:
            return self.ctx.map_eq_fns[key_type]
        fn = ir.Function(self.ctx.module, MAP_EQ_FN_TYPE, name="__nc_map_eq_" + self.type_label(key_type))
        self.ctx.map_eq_fns[key_type] = fn
        entry = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry)
        left_ptr = builder.bitcast(fn.args[0], self.llvm_type(key_type).as_pointer())
        right_ptr = builder.bitcast(fn.args[1], self.llvm_type(key_type).as_pointer())
        left = builder.load(left_ptr, name="left")
        right = builder.load(right_ptr, name="right")
        eq = self.emit_map_eq_value(builder, left, right, key_type)
        builder.ret(builder.zext(eq, ir.IntType(32)))
        return fn

    def emit_map_hash_mix(self, builder, h, value):
        if isinstance(value.type, ir.IntType):
            if value.type.width < 64:
                value = builder.zext(value, ir.IntType(64))
            elif value.type.width > 64:
                value = builder.trunc(value, ir.IntType(64))
        elif isinstance(value.type, ir.PointerType):
            value = builder.ptrtoint(value, ir.IntType(64))
        mixed = builder.xor(h, value)
        return builder.mul(mixed, ir.Constant(ir.IntType(64), 1099511628211))

    def emit_map_hash_value(self, builder, value, typ, h):
        if typ == "str":
            ptr = builder.extract_value(value, 0)
            length = builder.extract_value(value, 1)
            idx_slot = builder.alloca(ir.IntType(64), name="hash.idx")
            h_slot = builder.alloca(ir.IntType(64), name="hash.h")
            builder.store(ir.Constant(ir.IntType(64), 0), idx_slot)
            builder.store(h, h_slot)
            cond_bb = builder.function.append_basic_block("hash.str.cond")
            body_bb = builder.function.append_basic_block("hash.str.body")
            end_bb = builder.function.append_basic_block("hash.str.end")
            builder.branch(cond_bb)
            builder.position_at_end(cond_bb)
            idx = builder.load(idx_slot)
            builder.cbranch(builder.icmp_unsigned("<", idx, length), body_bb, end_bb)
            builder.position_at_end(body_bb)
            ch = builder.load(builder.gep(ptr, [idx], inbounds=True))
            next_h = self.emit_map_hash_mix(builder, builder.load(h_slot), ch)
            builder.store(next_h, h_slot)
            builder.store(builder.add(idx, ir.Constant(ir.IntType(64), 1)), idx_slot)
            builder.branch(cond_bb)
            builder.position_at_end(end_bb)
            return builder.load(h_slot)
        if typ in self.struct_fields:
            for i, (_field_name, field_type) in enumerate(self.struct_fields[typ]):
                h = self.emit_map_hash_value(builder, builder.extract_value(value, i), field_type, h)
            return h
        if isinstance(typ, str) and (typ.startswith("*") or typ.startswith("?*")):
            return self.emit_map_hash_mix(builder, h, value)
        if typ in self.enum_variants or typ in INT_TYPES:
            return self.emit_map_hash_mix(builder, h, value)
        raise NotImplementedError(f"LLVM backend cannot hash map key {typ}")

    def emit_map_eq_value(self, builder, left, right, typ):
        if typ == "str":
            fn = (
                self.ctx.module.globals["__nc_str_eq_ptr"]
                if "__nc_str_eq_ptr" in self.ctx.module.globals else
                ir.Function(
                    self.ctx.module,
                    ir.FunctionType(ir.IntType(32), [STR_TYPE.as_pointer(), STR_TYPE.as_pointer()]),
                    name="__nc_str_eq_ptr",
                )
            )
            left_ptr = builder.alloca(STR_TYPE)
            right_ptr = builder.alloca(STR_TYPE)
            builder.store(left, left_ptr)
            builder.store(right, right_ptr)
            eq = builder.call(fn, [left_ptr, right_ptr])
            return builder.icmp_signed("!=", eq, ir.Constant(ir.IntType(32), 0))
        if typ in self.struct_fields:
            result = ir.Constant(ir.IntType(1), 1)
            for i, (_field_name, field_type) in enumerate(self.struct_fields[typ]):
                result = builder.and_(
                    result,
                    self.emit_map_eq_value(builder, builder.extract_value(left, i), builder.extract_value(right, i), field_type),
                )
            return result
        return builder.icmp_unsigned("==", left, right)
