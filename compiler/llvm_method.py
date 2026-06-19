from llvmlite import ir

from compiler.ast import FieldAccess, Identifier, IndexAccess
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import I8PTR, IFACE_METHODS, llvm_type
from compiler.names import safe_user_ident
from compiler.type_ref import parse_map_type


class MethodEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def emit_receiver_arg(self, obj, receiver_base: str):
        obj_type = obj.type
        if obj_type == f"*{receiver_base}":
            return self.ctx.emit_expr(obj)
        if obj_type == receiver_base:
            if isinstance(obj, (Identifier, FieldAccess, IndexAccess)):
                ptr, _typ = self.ctx.emit_lvalue(obj)
                return ptr
            value = self.ctx.emit_expr(obj)
            slot = self.ctx.alloca_at_entry("__nc_receiver_tmp", llvm_type(receiver_base))
            self.ctx.builder.store(value, slot)
            return slot
        value = self.ctx.emit_expr(obj)
        slot = self.ctx.alloca_at_entry("__nc_receiver_tmp", llvm_type(receiver_base))
        self.ctx.builder.store(value, slot)
        return slot

    def emit_operator_method_call(self, receiver_expr, method_name: str, rhs, receiver_base: str):
        name = safe_user_ident(f"{receiver_base}_{method_name}")
        fn = self.ctx.module.globals[name]
        args = [self.emit_receiver_arg(receiver_expr, receiver_base), self.ctx.emit_coerced_expr(rhs, receiver_base)]
        return self.ctx.builder.call(fn, args)

    def emit_operator_method_value(self, value, value_type: str, method_name: str, rhs, receiver_base: str):
        name = safe_user_ident(f"{receiver_base}_{method_name}")
        fn = self.ctx.module.globals[name]
        slot = self.ctx.alloca_at_entry("__nc_operator_receiver", llvm_type(value_type))
        self.ctx.builder.store(value, slot)
        args = [slot, self.ctx.emit_coerced_expr(rhs, value_type)]
        return self.ctx.builder.call(fn, args)

    def emit_method_call(self, node):
        obj_type = node.obj.type
        if obj_type == "str" and node.method == "c_str":
            value = self.ctx.emit_expr(node.obj)
            ptr = self.ctx.builder.extract_value(value, 0)
            is_null = self.ctx.builder.icmp_unsigned("==", ptr, ir.Constant(I8PTR, None), name="str.c_str.is_null")
            return self.ctx.builder.select(is_null, self.ctx.empty_string_ptr(), ptr, name="str.c_str")
        if parse_map_type(obj_type) is not None and node.method == "has":
            if len(node.args) != 1:
                raise RuntimeError("method has expects one argument")
            return self.ctx.emit_map_has(node.obj, node.args[0])
        if obj_type in IFACE_METHODS:
            return self.ctx.emit_iface_method_call(node)
        receiver_base = self.receiver_base(obj_type)
        name = safe_user_ident(f"{receiver_base}_{node.method}")
        if name not in self.ctx.module.globals:
            raise NotImplementedError(f"LLVM backend cannot call method {receiver_base}.{node.method}")
        fn = self.ctx.module.globals[name]
        fn_decl = self.ctx.fn_decls[name]
        if getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"fallible method call {receiver_base}.{node.method} must be lowered through a fallible operator")
        args = [self.emit_receiver_arg(node.obj, receiver_base)] + [
            self.ctx.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ]
        return self.ctx.builder.call(fn, args)

    def emit_fallible_method_call_raw(self, node):
        receiver_base = self.receiver_base(node.obj.type)
        name = safe_user_ident(f"{receiver_base}_{node.method}")
        if name not in self.ctx.module.globals:
            raise RuntimeError(f"method {receiver_base}.{node.method} is not fallible")
        fn_decl = self.ctx.fn_decls[name]
        if not getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"method {receiver_base}.{node.method} is not fallible")
        fn = self.ctx.module.globals[name]
        success_type = fn_decl.return_type or "void"
        value_slot, error_slot = self.ctx.fallible_out_slots(success_type)
        args = []
        if value_slot is not None:
            args.append(value_slot)
        args.append(error_slot)
        args.append(self.emit_receiver_arg(node.obj, receiver_base))
        args.extend([
            self.ctx.emit_coerced_expr(arg, ptype)
            for arg, (_pname, ptype) in zip(node.args, fn_decl.params)
        ])
        status = self.ctx.builder.call(fn, args, name="fallible.method.status")
        return status, value_slot, error_slot, success_type

    def receiver_base(self, obj_type: str):
        if obj_type.startswith("?*"):
            return obj_type[2:]
        if obj_type.startswith("*"):
            return obj_type[1:]
        return obj_type
