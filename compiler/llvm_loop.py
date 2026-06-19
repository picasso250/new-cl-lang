from llvmlite import ir

from compiler.ast import ForCondition, ForIn
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import I8PTR, MAP_TYPE, llvm_type
from compiler.names import safe_user_ident
from compiler.type_ref import parse_map_type, parse_slice_type


class LoopEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_for_condition(self, stmt: ForCondition):
        cond_bb = self.ctx.func.append_basic_block("for.cond")
        body_bb = self.ctx.func.append_basic_block("for.body")
        end_bb = self.ctx.func.append_basic_block("for.end")
        self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(cond_bb)
        self.ctx.builder.cbranch(self.ctx.bool_value(self.ctx.emit_expr(stmt.condition)), body_bb, end_bb)
        self.ctx.builder.position_at_end(body_bb)
        self.ctx.break_stack.append(end_bb)
        self.ctx.emit_block(stmt.body)
        self.ctx.break_stack.pop()
        if not self.ctx.builder.block.is_terminated:
            self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(end_bb)

    def emit_for_in(self, stmt: ForIn):
        if stmt.start is None:
            if parse_map_type(stmt.iterable.type) is not None:
                self.emit_map_for_in(stmt)
            else:
                self.emit_slice_for_in(stmt)
            return

        idx_type = ir.IntType(32)
        idx_slot = self.ctx.alloca_at_entry(safe_user_ident(stmt.index), idx_type)
        self.ctx.vars[stmt.index] = (idx_slot, "i32")
        start = self.ctx.cast_to(self.ctx.emit_expr(stmt.start), "i32")
        end = self.ctx.cast_to(self.ctx.emit_expr(stmt.end), "i32")
        self.ctx.builder.store(start, idx_slot)

        cond_bb = self.ctx.func.append_basic_block("for.range.cond")
        body_bb = self.ctx.func.append_basic_block("for.range.body")
        end_bb = self.ctx.func.append_basic_block("for.range.end")
        self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(cond_bb)
        current = self.ctx.builder.load(idx_slot, name=safe_user_ident(stmt.index))
        self.ctx.builder.cbranch(self.ctx.builder.icmp_signed("<", current, end), body_bb, end_bb)
        self.ctx.builder.position_at_end(body_bb)
        self.ctx.break_stack.append(end_bb)
        self.ctx.emit_block(stmt.body)
        self.ctx.break_stack.pop()
        if not self.ctx.builder.block.is_terminated:
            current = self.ctx.builder.load(idx_slot, name=safe_user_ident(stmt.index))
            next_value = self.ctx.builder.add(current, ir.Constant(idx_type, 1))
            self.ctx.builder.store(next_value, idx_slot)
            self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(end_bb)

    def emit_slice_for_in(self, stmt: ForIn):
        elem_type = parse_slice_type(stmt.iterable.type)
        if elem_type is None or stmt.value is None:
            raise NotImplementedError("LLVM backend only supports for i, item in slice")

        saved_vars = self.ctx.vars.copy()
        idx_type = ir.IntType(32)
        idx_slot = self.ctx.alloca_at_entry(safe_user_ident(stmt.index), idx_type)
        value_slot = self.ctx.alloca_at_entry(safe_user_ident(stmt.value), llvm_type(elem_type))
        self.ctx.vars[stmt.index] = (idx_slot, "i32")
        self.ctx.vars[stmt.value] = (value_slot, elem_type)
        self.ctx.root_slots_for_type(value_slot, elem_type)

        slice_value = self.ctx.emit_expr(stmt.iterable)
        ptr = self.ctx.builder.extract_value(slice_value, 0)
        length64 = self.ctx.builder.extract_value(slice_value, 1)
        length32 = self.ctx.builder.trunc(length64, idx_type)
        self.ctx.builder.store(ir.Constant(idx_type, 0), idx_slot)

        cond_bb = self.ctx.func.append_basic_block("for.slice.cond")
        body_bb = self.ctx.func.append_basic_block("for.slice.body")
        end_bb = self.ctx.func.append_basic_block("for.slice.end")
        self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(cond_bb)
        current = self.ctx.builder.load(idx_slot, name=safe_user_ident(stmt.index))
        self.ctx.builder.cbranch(self.ctx.builder.icmp_signed("<", current, length32), body_bb, end_bb)
        self.ctx.builder.position_at_end(body_bb)
        elem_ptr = self.ctx.builder.gep(ptr, [current], inbounds=True, name="for.slice.elem.ptr")
        self.ctx.builder.store(self.ctx.builder.load(elem_ptr), value_slot)
        self.ctx.break_stack.append(end_bb)
        self.ctx.emit_block(stmt.body)
        self.ctx.break_stack.pop()
        if not self.ctx.builder.block.is_terminated:
            current = self.ctx.builder.load(idx_slot, name=safe_user_ident(stmt.index))
            next_value = self.ctx.builder.add(current, ir.Constant(idx_type, 1))
            self.ctx.builder.store(next_value, idx_slot)
            self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(end_bb)
        self.ctx.vars = saved_vars

    def emit_map_for_in(self, stmt: ForIn):
        map_parts = parse_map_type(stmt.iterable.type)
        if map_parts is None or stmt.value is None:
            raise NotImplementedError("LLVM backend only supports for key, value in map")
        key_type, value_type = map_parts

        saved_vars = self.ctx.vars.copy()
        key_slot = self.ctx.alloca_at_entry(safe_user_ident(stmt.index), llvm_type(key_type))
        value_slot = self.ctx.alloca_at_entry(safe_user_ident(stmt.value), llvm_type(value_type))
        cursor_slot = self.ctx.alloca_at_entry("__nc_map_cursor", ir.IntType(64))
        found_slot = self.ctx.alloca_at_entry("__nc_map_found", ir.IntType(64))
        map_slot = self.ctx.alloca_at_entry("__nc_map_iter", MAP_TYPE)
        self.ctx.vars[stmt.index] = (key_slot, key_type)
        self.ctx.vars[stmt.value] = (value_slot, value_type)
        self.ctx.root_slots_for_type(key_slot, key_type)
        self.ctx.root_slots_for_type(value_slot, value_type)

        map_value = self.ctx.emit_expr(stmt.iterable)
        self.ctx.builder.store(map_value, map_slot)
        self.ctx.builder.store(ir.Constant(ir.IntType(64), 0), cursor_slot)

        cond_bb = self.ctx.func.append_basic_block("for.map.cond")
        body_bb = self.ctx.func.append_basic_block("for.map.body")
        end_bb = self.ctx.func.append_basic_block("for.map.end")
        self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(cond_bb)
        cursor = self.ctx.builder.load(cursor_slot, name="for.map.cursor")
        key_ptr = self.ctx.builder.bitcast(key_slot, I8PTR)
        value_ptr = self.ctx.builder.bitcast(value_slot, I8PTR)
        found = self.ctx.builder.call(self.ctx.map_next_fn, [map_slot, cursor, key_ptr, value_ptr], name="for.map.next")
        self.ctx.builder.store(found, found_slot)
        self.ctx.builder.cbranch(
            self.ctx.builder.icmp_signed(">=", found, ir.Constant(ir.IntType(64), 0)),
            body_bb,
            end_bb,
        )
        self.ctx.builder.position_at_end(body_bb)
        self.ctx.break_stack.append(end_bb)
        self.ctx.emit_block(stmt.body)
        self.ctx.break_stack.pop()
        if not self.ctx.builder.block.is_terminated:
            found = self.ctx.builder.load(found_slot, name="for.map.found")
            next_cursor = self.ctx.builder.add(found, ir.Constant(ir.IntType(64), 1))
            self.ctx.builder.store(next_cursor, cursor_slot)
            self.ctx.builder.branch(cond_bb)
        self.ctx.builder.position_at_end(end_bb)
        self.ctx.vars = saved_vars
