from llvmlite import ir

from compiler.ast import IfaceDecl
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import (
    I8PTR, IFACE_METHODS, IFACE_TYPES, STRUCT_EMBEDS, STRUCT_FIELDS,
    STRUCT_FIELD_INDEX, llvm_type,
)
from compiler.names import safe_user_ident


class IfaceEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def register_ifaces(self, program):
        IFACE_METHODS.clear()
        IFACE_TYPES.clear()
        raw = {}
        for stmt in program.statements:
            if isinstance(stmt, IfaceDecl):
                raw[stmt.name] = stmt

        def resolve(name, stack=None):
            stack = stack or []
            if name in IFACE_METHODS:
                return IFACE_METHODS[name]
            if name in stack:
                raise RuntimeError(f"iface {name}: embedded iface cycle")
            stmt = raw[name]
            methods = {}
            order = []

            def add(mname, params, ret):
                sig = ([ptype for _pname, ptype in params], ret or "void")
                if mname not in methods:
                    order.append(mname)
                methods[mname] = sig

            for embed in stmt.embeds:
                for mname, param_types, ret in resolve(embed, stack + [name]):
                    add(mname, [(f"arg{i}", t) for i, t in enumerate(param_types)], ret)
            for method in stmt.methods:
                mname, params, ret = method[:3]
                add(mname, params, ret)
            IFACE_METHODS[name] = [(mname, methods[mname][0], methods[mname][1]) for mname in order]
            IFACE_TYPES[name] = ir.LiteralStructType([I8PTR, I8PTR])
            return IFACE_METHODS[name]

        for name in list(raw):
            resolve(name)

    def emit_iface_method_call(self, node):
        obj_type = node.obj.type
        iface_value = self.ctx.emit_expr(node.obj)
        method_index = next(i for i, (name, _params, _ret) in enumerate(IFACE_METHODS[obj_type]) if name == node.method)
        _mname, param_types, ret_type = IFACE_METHODS[obj_type][method_index]
        vt_i8 = self.ctx.builder.extract_value(iface_value, 0, name="iface.vtable")
        data = self.ctx.builder.extract_value(iface_value, 1, name="iface.data")
        fn_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types]).as_pointer()
        vt_type = ir.LiteralStructType(self.iface_vtable_function_ptr_types(obj_type)).as_pointer()
        vt_ptr = self.ctx.builder.bitcast(vt_i8, vt_type, name="iface.vtable.ptr")
        fn_ptr_ptr = self.ctx.builder.gep(
            vt_ptr,
            [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), method_index)],
            inbounds=True,
            name="iface.method.ptr.ptr",
        )
        fn_ptr = self.ctx.builder.load(fn_ptr_ptr, name="iface.method.ptr")
        fn_ptr = self.ctx.builder.bitcast(fn_ptr, fn_type, name="iface.method.cast")
        args = [data] + [self.ctx.emit_coerced_expr(arg, ptype) for arg, ptype in zip(node.args, param_types)]
        return self.ctx.builder.call(fn_ptr, args)

    def iface_vtable_function_ptr_types(self, iface_name):
        return [
            ir.FunctionType(llvm_type(ret), [I8PTR] + [llvm_type(t) for t in params]).as_pointer()
            for _name, params, ret in IFACE_METHODS[iface_name]
        ]

    def box_iface(self, value, source_type, iface_name):
        if not isinstance(source_type, str) or not source_type.startswith("*") or source_type.startswith("?*"):
            raise RuntimeError(f"cannot box {source_type} as iface {iface_name}")
        concrete = source_type[1:]
        vtable = self.get_iface_vtable(iface_name, concrete)
        iface_type = llvm_type(iface_name)
        boxed = ir.Constant(iface_type, ir.Undefined)
        boxed = self.ctx.builder.insert_value(boxed, self.ctx.builder.bitcast(vtable, I8PTR), [0], name="iface.vtable.ins")
        boxed = self.ctx.builder.insert_value(boxed, self.ctx.builder.bitcast(value, I8PTR), [1], name="iface.data.ins")
        return boxed

    def get_iface_vtable(self, iface_name, concrete):
        key = (iface_name, concrete)
        if key in self.ctx.iface_vtables:
            return self.ctx.iface_vtables[key]
        field_types = self.iface_vtable_function_ptr_types(iface_name)
        vt_type = ir.LiteralStructType(field_types)
        values = []
        for mname, param_types, ret_type in IFACE_METHODS[iface_name]:
            thunk = self.get_iface_thunk(iface_name, concrete, mname, param_types, ret_type)
            values.append(thunk.bitcast(field_types[len(values)]))
        glob = ir.GlobalVariable(self.ctx.module, vt_type, name=safe_user_ident(f"__nc_iface_{iface_name}_{concrete}_vtable"))
        glob.linkage = "internal"
        glob.global_constant = True
        glob.initializer = ir.Constant.literal_struct(values)
        self.ctx.iface_vtables[key] = glob
        return glob

    def get_iface_thunk(self, iface_name, concrete, method_name, param_types, ret_type):
        key = (iface_name, concrete, method_name)
        if key in self.ctx.iface_thunks:
            return self.ctx.iface_thunks[key]
        fn_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types])
        name = safe_user_ident(f"__nc_iface_{iface_name}_{concrete}_{method_name}_thunk")
        thunk = ir.Function(self.ctx.module, fn_type, name=name)
        self.ctx.iface_thunks[key] = thunk
        block = thunk.append_basic_block("entry")
        saved_builder, saved_func = self.ctx.builder, self.ctx.func
        self.ctx.builder, self.ctx.func = ir.IRBuilder(block), thunk
        receiver_base, path = self.resolve_concrete_method(concrete, method_name)
        method_sym = safe_user_ident(f"{receiver_base}_{method_name}")
        method_fn = self.ctx.module.globals[method_sym]
        receiver = self.ctx.builder.bitcast(thunk.args[0], llvm_type(f"*{concrete}"), name="iface.receiver")
        current_type = concrete
        for field_name in path:
            field_index = STRUCT_FIELD_INDEX[current_type][field_name]
            zero = ir.Constant(ir.IntType(32), 0)
            receiver = self.ctx.builder.gep(
                receiver,
                [zero, ir.Constant(ir.IntType(32), field_index)],
                inbounds=True,
                name="iface.embed.receiver",
            )
            current_type = STRUCT_FIELDS[current_type][field_index][1]
        receiver = self.ctx.builder.bitcast(receiver, llvm_type(f"*{receiver_base}"), name="iface.receiver.cast")
        args = [receiver] + list(thunk.args[1:])
        result = self.ctx.builder.call(method_fn, args)
        if ret_type == "void":
            self.ctx.builder.ret_void()
        else:
            self.ctx.builder.ret(result)
        self.ctx.builder, self.ctx.func = saved_builder, saved_func
        return thunk

    def resolve_concrete_method(self, concrete, method_name):
        if safe_user_ident(f"{concrete}_{method_name}") in self.ctx.module.globals:
            return concrete, []
        for field_name, field_type in STRUCT_EMBEDS.get(concrete, {}).items():
            embed_base = field_type[1:] if field_type.startswith("*") else field_type
            if safe_user_ident(f"{embed_base}_{method_name}") in self.ctx.module.globals:
                return embed_base, [field_name]
            try:
                nested_base, nested_path = self.resolve_concrete_method(embed_base, method_name)
                return nested_base, [field_name] + nested_path
            except KeyError:
                pass
        raise KeyError(safe_user_ident(f"{concrete}_{method_name}"))
