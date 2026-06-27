from llvmlite import ir

from compiler.ast import Block, ExpressionStatement, FunctionCall, FunctionDeclaration, FunctionExpr, GenericFunctionValue, Identifier, MethodCall
from compiler.llvm_context import CodegenContext
from compiler.llvm_layout import ERROR_TYPE, I8PTR, llvm_type
from compiler.names import abi_symbol, safe_user_ident
from compiler.source_location import location_for_node
from compiler.type_ref import parse_fn_type, parse_slice_type


class FunctionEmitter:
    def __init__(self, ctx: CodegenContext):
        self.ctx = ctx

    def register_closure_envs(self, closures: list[FunctionExpr]):
        self.ctx.closure_env_types.clear()
        for closure in closures:
            fields = [llvm_type(capture_type) for _name, capture_type in getattr(closure, "captures", [])]
            if not fields:
                fields = [ir.IntType(8)]
            self.ctx.closure_env_types[closure.closure_id] = ir.LiteralStructType(fields)

    def declare_function(self, fn: FunctionDeclaration):
        name = self.function_symbol(fn)
        is_fallible = bool(getattr(fn, "fallible", False)) and not getattr(fn, "is_extern", False) and fn.name != "main"
        ret = ir.IntType(1) if is_fallible else (
            ir.IntType(32) if fn.name == "main" and (fn.return_type or "void") == "void" else llvm_type(fn.return_type)
        )
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        args = [ir.IntType(32), I8PTR.as_pointer()] if fn.name == "main" else []
        if is_fallible:
            if (fn.return_type or "void") != "void":
                args.append(llvm_type(fn.return_type).as_pointer())
            args.append(ERROR_TYPE.as_pointer())
        for _n, t in all_params:
            slice_elem = parse_slice_type(t)
            if slice_elem is not None:
                ptr_type = llvm_type(slice_elem).as_pointer()
                args.append(ptr_type)
                args.append(ir.IntType(64))
                args.append(ir.IntType(64))
            else:
                args.append(llvm_type(t))
        fn_type = ir.FunctionType(ret, args)
        existing = self.ctx.module.globals.get(name)
        if existing is not None:
            if getattr(existing, "function_type", None) != fn_type:
                raise RuntimeError(f"extern symbol '{name}' declared with incompatible ABI")
        else:
            self.ctx.module.globals[name] = ir.Function(self.ctx.module, fn_type, name=name)
        llvm_fn_obj = self.ctx.module.globals[name]
        arg_idx = 0
        if llvm_fn_obj.name == "main":
            arg_idx += 2
        elif is_fallible:
            if (fn.return_type or "void") != "void":
                arg_idx += 1
            arg_idx += 1
        for _n, t in all_params:
            slice_elem = parse_slice_type(t)
            if slice_elem is not None:
                arg_idx += 3
            else:
                arg_idx += 1
        self.ctx.fn_decls[name] = fn
        if not fn.receiver_name:
            self.ctx.fn_decls[fn.name] = fn

    def function_symbol(self, fn: FunctionDeclaration):
        if getattr(fn, "is_extern", False):
            return getattr(fn, "extern_symbol", None) or fn.name
        if fn.name == "main" and not fn.receiver_name:
            return "main"
        module_name = getattr(getattr(fn, "source_file", None), "module_name", "<memory>")
        if fn.receiver_name:
            receiver_type = fn.receiver_type.lstrip("*").lstrip("?")
            signature = f"method\0{module_name}\0{receiver_type}\0{fn.name}\0{fn.return_type or 'void'}\0{fn.params}"
            return abi_symbol("M", module_name, f"{receiver_type}_{fn.name}", signature)
        signature = f"function\0{module_name}\0{fn.name}\0{fn.return_type or 'void'}\0{fn.params}"
        return abi_symbol("F", module_name, fn.name, signature)

    def frame_name(self, fn: FunctionDeclaration):
        if fn.receiver_name:
            receiver_type = fn.receiver_type.lstrip("*").lstrip("?")
            return f"{receiver_type}.{fn.name}"
        return fn.name

    def node_location(self, node):
        return location_for_node(node)

    def closure_symbol(self, closure: FunctionExpr):
        module_name = getattr(getattr(closure, "source_file", None), "module_name", "<memory>")
        signature = f"lambda\0{module_name}\0{closure.closure_id}\0{closure.return_type or 'void'}\0{closure.params}"
        return abi_symbol("L", module_name, f"lambda_{closure.closure_id}", signature)

    def declare_closure_function(self, closure: FunctionExpr):
        ret = llvm_type(closure.return_type or "void")
        args = [I8PTR] + [llvm_type(t) for _n, t in closure.params]
        fn = ir.Function(self.ctx.module, ir.FunctionType(ret, args), name=self.closure_symbol(closure))
        fn.linkage = "internal"

    def emit_closure_function(self, closure: FunctionExpr):
        llvm_fn = self.ctx.module.globals[self.closure_symbol(closure)]
        block = llvm_fn.append_basic_block("entry")
        saved_builder, saved_func, saved_vars = self.ctx.builder, self.ctx.func, self.ctx.vars
        saved_defer = (self.ctx.defer_sites, self.ctx.defer_stack_slot, self.ctx.defer_top_slot, self.ctx.emitting_defer)
        saved_gc = (self.ctx.current_gc_mark, self.ctx.current_return_slot, self.ctx.current_frame_name)
        self.ctx.builder = ir.IRBuilder(block)
        self.ctx.func = llvm_fn
        self.ctx.vars = {}
        self.ctx.current_frame_name = f"lambda {closure.closure_id}"
        self.ctx.init_defer_state()
        self.ctx.init_gc_frame(is_main=False)
        llvm_fn.args[0].name = "__nc_env"
        env_type = self.ctx.closure_env_types[closure.closure_id]
        env_ptr = self.ctx.builder.bitcast(llvm_fn.args[0], env_type.as_pointer(), name="closure.env.ptr")
        env_slot = self.ctx.alloca_at_entry("__nc_env_slot", I8PTR)
        self.ctx.builder.store(llvm_fn.args[0], env_slot)
        self.ctx.root_slots_for_type(env_slot, f"*__nc_env_{closure.closure_id}")
        for i, (capture_name, capture_type) in enumerate(getattr(closure, "captures", [])):
            field_ptr = self.ctx.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{safe_user_ident(capture_name)}.ptr",
            )
            self.ctx.vars[capture_name] = (field_ptr, capture_type)
        for arg, (param_name, param_type) in zip(llvm_fn.args[1:], closure.params):
            arg.name = safe_user_ident(param_name)
            slot = self.ctx.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
            self.ctx.builder.store(arg, slot)
            self.ctx.vars[param_name] = (slot, param_type)
            self.ctx.root_slots_for_type(slot, param_type)
        if (closure.return_type or "void") != "void":
            self.ctx.current_return_slot = self.ctx.alloca_at_entry("__nc_ret", llvm_type(closure.return_type))
            self.ctx.root_slots_for_type(self.ctx.current_return_slot, closure.return_type)
        self.emit_callable_body(closure.body, closure.return_type or "void", f"lambda {closure.closure_id}")
        self.ctx.builder, self.ctx.func, self.ctx.vars = saved_builder, saved_func, saved_vars
        self.ctx.defer_sites, self.ctx.defer_stack_slot, self.ctx.defer_top_slot, self.ctx.emitting_defer = saved_defer
        self.ctx.current_gc_mark, self.ctx.current_return_slot, self.ctx.current_frame_name = saved_gc

    def emit_function(self, fn: FunctionDeclaration):
        llvm_fn = self.ctx.module.globals[self.function_symbol(fn)]
        block = llvm_fn.append_basic_block("entry")
        saved_defer = (self.ctx.defer_sites, self.ctx.defer_stack_slot, self.ctx.defer_top_slot, self.ctx.emitting_defer)
        saved_gc = (
            self.ctx.current_gc_mark,
            self.ctx.current_return_slot,
            self.ctx.current_error_slot,
            self.ctx.current_is_fallible,
            self.ctx.current_frame_name,
        )
        self.ctx.builder = ir.IRBuilder(block)
        self.ctx.func = llvm_fn
        self.ctx.vars = {}
        self.ctx.init_defer_state()
        self.ctx.init_gc_frame(is_main=fn.name == "main")
        all_params = ([(fn.receiver_name, fn.receiver_type)] if fn.receiver_name else []) + fn.params
        llvm_args = list(llvm_fn.args)
        self.ctx.current_is_fallible = bool(getattr(fn, "fallible", False)) and fn.name != "main"
        self.ctx.current_frame_name = self.frame_name(fn)
        if fn.name == "main":
            llvm_args[0].name = "__nc_argc"
            llvm_args[1].name = "__nc_argv"
            self.ctx.init_os_args(llvm_args[0], llvm_args[1])
            llvm_args = llvm_args[2:]
        elif self.ctx.current_is_fallible:
            if (fn.return_type or "void") != "void":
                self.ctx.current_return_slot = llvm_args[0]
                self.ctx.root_slots_for_type(self.ctx.current_return_slot, fn.return_type)
                llvm_args = llvm_args[1:]
            self.ctx.current_error_slot = llvm_args[0]
            self.ctx.root_slots_for_type(self.ctx.current_error_slot, "error")
            llvm_args = llvm_args[1:]
        arg_idx = 0
        for param_name, param_type in all_params:
            slice_elem = parse_slice_type(param_type)
            if slice_elem is not None:
                ptr_arg = llvm_args[arg_idx]
                len_arg = llvm_args[arg_idx + 1]
                cap_arg = llvm_args[arg_idx + 2]
                arg_idx += 3
                ptr_arg.name = safe_user_ident(f"{param_name}.ptr")
                len_arg.name = safe_user_ident(f"{param_name}.len")
                cap_arg.name = safe_user_ident(f"{param_name}.cap")
                slot = self.ctx.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
                slice_val = ir.Constant(llvm_type(param_type), ir.Undefined)
                slice_val = self.ctx.builder.insert_value(slice_val, ptr_arg, [0], name=f"{safe_user_ident(param_name)}.ptr.ins")
                slice_val = self.ctx.builder.insert_value(slice_val, len_arg, [1], name=f"{safe_user_ident(param_name)}.len.ins")
                slice_val = self.ctx.builder.insert_value(slice_val, cap_arg, [2], name=f"{safe_user_ident(param_name)}.cap.ins")
                self.ctx.builder.store(slice_val, slot)
                self.ctx.vars[param_name] = (slot, param_type)
                self.ctx.root_slots_for_type(slot, param_type)
            else:
                arg = llvm_args[arg_idx]
                arg_idx += 1
                arg.name = safe_user_ident(param_name)
                slot = self.ctx.alloca_at_entry(safe_user_ident(param_name), llvm_type(param_type))
                self.ctx.builder.store(arg, slot)
                self.ctx.vars[param_name] = (slot, param_type)
                self.ctx.root_slots_for_type(slot, param_type)
        if (fn.return_type or "void") != "void" and self.ctx.current_return_slot is None:
            self.ctx.current_return_slot = self.ctx.alloca_at_entry("__nc_ret", llvm_type(fn.return_type))
            self.ctx.root_slots_for_type(self.ctx.current_return_slot, fn.return_type)

        self.emit_function_body(fn)
        self.ctx.defer_sites, self.ctx.defer_stack_slot, self.ctx.defer_top_slot, self.ctx.emitting_defer = saved_defer
        (
            self.ctx.current_gc_mark,
            self.ctx.current_return_slot,
            self.ctx.current_error_slot,
            self.ctx.current_is_fallible,
            self.ctx.current_frame_name,
        ) = saved_gc

    def emit_function_body(self, fn: FunctionDeclaration):
        if getattr(fn, "_is_erased_generic", False) and "lt" in set(getattr(fn, "_erased_ops", set())):
            self.emit_erased_ord_min_body(fn)
            return
        self.emit_callable_body(fn.body, fn.return_type or "void", f"function {fn.name}",
                                is_main=fn.name == "main", is_extern=getattr(fn, "is_extern", False))

    def emit_erased_ord_min_body(self, fn: FunctionDeclaration):
        prev_return_type, prev_is_main = self.ctx.current_return_type, self.ctx.current_is_main
        self.ctx.current_return_type = fn.return_type or "void"
        self.ctx.current_is_main = False
        desc_slot, _desc_type = self.ctx.vars["_desc"]
        left_slot, _left_type = self.ctx.vars[fn.params[1].name]
        right_slot, _right_type = self.ctx.vars[fn.params[2].name]
        desc = self.ctx.builder.load(desc_slot, name="erased.desc.value")
        left = self.ctx.builder.load(left_slot, name="erased.left.raw")
        right = self.ctx.builder.load(right_slot, name="erased.right.raw")
        void_raw_raw = ir.FunctionType(ir.VoidType(), [I8PTR, I8PTR, I8PTR]).as_pointer()
        void_raw_raw_unary = ir.FunctionType(ir.VoidType(), [I8PTR, I8PTR]).as_pointer()
        bool_raw_raw = ir.FunctionType(ir.IntType(1), [I8PTR, I8PTR, I8PTR]).as_pointer()
        hash_raw = ir.FunctionType(ir.IntType(64), [I8PTR, I8PTR]).as_pointer()
        desc_struct_ty = ir.LiteralStructType([
            ir.IntType(32),
            ir.IntType(32),
            void_raw_raw,
            void_raw_raw_unary,
            bool_raw_raw,
            bool_raw_raw,
            hash_raw,
            void_raw_raw_unary,
        ])
        desc_ptr = self.ctx.builder.bitcast(desc, desc_struct_ty.as_pointer(), name="erased.desc.ptr")
        lt_ptr = self.ctx.builder.gep(
            desc_ptr,
            [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 5)],
            inbounds=True,
            name="erased.desc.lt.ptr",
        )
        lt_fn = self.ctx.builder.load(lt_ptr, name="erased.desc.lt")
        cond = self.ctx.builder.call(lt_fn, [desc, left, right], name="erased.lt")
        selected = self.ctx.builder.select(cond, left, right, name="erased.min.raw")
        self.ctx.builder.store(selected, self.ctx.current_return_slot)
        self.emit_success_return()
        self.ctx.current_return_type, self.ctx.current_is_main = prev_return_type, prev_is_main

    def emit_callable_body(self, body: Block, return_type: str, name: str, is_main: bool = False,
                           is_extern: bool = False):
        prev_return_type, prev_is_main = self.ctx.current_return_type, self.ctx.current_is_main
        self.ctx.current_return_type = return_type
        self.ctx.current_is_main = is_main

        # Phase 8: cooperative time-slice yield at function entry
        if not is_extern:
            fn_yield_ty = ir.FunctionType(ir.VoidType(), [])
            fn_yield = self.ctx.module.globals.get("__nc_g_check_yield")
            if fn_yield is None:
                fn_yield = ir.Function(self.ctx.module, fn_yield_ty, "__nc_g_check_yield")
            self.ctx.builder.call(fn_yield, [])

        stmts = body.statements
        if return_type != "void" and stmts and isinstance(stmts[-1], ExpressionStatement):
            for stmt in stmts[:-1]:
                self.ctx.emit_stmt(stmt)
            if not self.ctx.builder.block.is_terminated:
                value = self.ctx.emit_coerced_expr(stmts[-1].expr, return_type)
                if self.ctx.current_return_slot is not None:
                    self.ctx.builder.store(value, self.ctx.current_return_slot)
                self.emit_success_return()
            self.ctx.current_return_type, self.ctx.current_is_main = prev_return_type, prev_is_main
            return
        self.ctx.emit_block(body)
        if not self.ctx.builder.block.is_terminated:
            self.ctx.emit_deferred()
            if is_main and return_type == "void":
                self.ctx.emit_gc_rewind()
                self.ctx.builder.ret(ir.Constant(ir.IntType(32), 0))
            elif return_type == "void":
                self.emit_success_return()
            else:
                raise RuntimeError(f"missing ret in {name}")
        self.ctx.current_return_type, self.ctx.current_is_main = prev_return_type, prev_is_main

    def emit_success_return(self):
        self.ctx.emit_deferred()
        if self.ctx.current_is_fallible:
            self.ctx.emit_gc_rewind()
            self.ctx.builder.ret(ir.Constant(ir.IntType(1), 0))
            return
        if self.ctx.current_is_main and self.ctx.current_return_type == "void":
            self.ctx.emit_gc_rewind()
            self.ctx.builder.ret(ir.Constant(ir.IntType(32), 0))
            return
        if self.ctx.current_return_type == "void":
            self.ctx.emit_gc_rewind()
            self.ctx.builder.ret_void()
            return
        value = self.ctx.builder.load(self.ctx.current_return_slot, name="ret.value")
        self.ctx.emit_gc_rewind()
        self.ctx.builder.ret(value)

    def emit_error_return_value(self, value, node=None, append_frame=True):
        if append_frame:
            path, line, col = self.node_location(node) if node is not None else ("<unknown>", 0, 0)
            value = self.ctx.emit_error_append_frame(value, self.ctx.current_frame_name, path, line, col)
        if self.ctx.current_error_slot is not None:
            self.ctx.builder.store(self.ctx.cast_to(value, "error"), self.ctx.current_error_slot)
        self.ctx.emit_deferred()
        if self.ctx.current_is_main:
            self.ctx.emit_print_error(value)
            self.ctx.emit_gc_rewind()
            self.ctx.builder.ret(ir.Constant(self.ctx.func.function_type.return_type, 1))
            return
        if not self.ctx.current_is_fallible:
            self.ctx.emit_print_error(value)
            self.ctx.emit_exit(1)
            self.ctx.builder.unreachable()
            return
        self.ctx.emit_gc_rewind()
        self.ctx.builder.ret(ir.Constant(ir.IntType(1), 1))

    def emit_fallible_op(self, node):
        status, value_slot, error_slot, success_type = self.emit_fallible_call_raw(node.expr)
        err_bb = self.ctx.func.append_basic_block("fallible.err")
        ok_bb = self.ctx.func.append_basic_block("fallible.ok")
        self.ctx.builder.cbranch(status, err_bb, ok_bb)
        self.ctx.builder.position_at_end(err_bb)
        err_value = self.ctx.builder.load(error_slot, name="fallible.err.value")
        if node.op == "??":
            path, line, col = self.node_location(node)
            err_value = self.ctx.emit_error_append_frame(err_value, self.ctx.current_frame_name, path, line, col)
            self.emit_error_return_value(err_value, append_frame=False)
        elif node.op == "!!":
            path, line, col = self.node_location(node)
            err_value = self.ctx.emit_error_append_frame(err_value, self.ctx.current_frame_name, path, line, col)
            self.ctx.emit_print_error(err_value)
            self.ctx.emit_exit(1)
            self.ctx.builder.unreachable()
        else:
            raise RuntimeError(f"unknown fallible operator {node.op}")
        self.ctx.builder.position_at_end(ok_bb)
        if success_type == "void":
            return ir.Constant(ir.IntType(1), 0)
        return self.ctx.builder.load(value_slot, name="fallible.ok.value")

    def emit_fallible_call_raw(self, call_node):
        if isinstance(call_node, FunctionCall):
            return self.emit_fallible_function_call_raw(call_node)
        if isinstance(call_node, MethodCall):
            return self.ctx.emit_fallible_method_call_raw(call_node)
        raise RuntimeError(f"fallible operator requires a fallible call, got {type(call_node).__name__}")

    def fallible_out_slots(self, success_type):
        value_slot = None
        if success_type != "void":
            value_slot = self.ctx.alloca_at_entry("__nc_fallible_value", llvm_type(success_type))
            self.ctx.root_slots_for_type(value_slot, success_type)
        error_slot = self.ctx.alloca_at_entry("__nc_fallible_error", ERROR_TYPE)
        self.ctx.root_slots_for_type(error_slot, "error")
        return value_slot, error_slot

    def emit_fallible_function_call_raw(self, node: FunctionCall):
        fn_decl = self.ctx.fn_decls[node.name]
        if not getattr(fn_decl, "fallible", False):
            raise RuntimeError(f"{node.name} is not fallible")
        fn = self.ctx.module.globals[self.function_symbol(fn_decl)]
        success_type = fn_decl.return_type or "void"
        value_slot, error_slot = self.fallible_out_slots(success_type)
        args = []
        if value_slot is not None:
            args.append(value_slot)
        args.append(error_slot)
        for arg, (_pname, ptype) in zip(node.args, fn_decl.params):
            slice_elem = parse_slice_type(ptype)
            if slice_elem is not None:
                slice_val = self.ctx.emit_coerced_expr(arg, ptype)
                args.append(self.ctx.builder.extract_value(slice_val, 0, name="fallible.call.slice.ptr"))
                args.append(self.ctx.builder.extract_value(slice_val, 1, name="fallible.call.slice.len"))
                args.append(self.ctx.builder.extract_value(slice_val, 2, name="fallible.call.slice.cap"))
            else:
                args.append(self.ctx.emit_coerced_expr(arg, ptype))
        status = self.ctx.builder.call(fn, args, name="fallible.status")
        return status, value_slot, error_slot, success_type

    def emit_function_expr(self, node: FunctionExpr):
        closure_type = llvm_type(node.type)
        fn = self.ctx.module.globals[self.closure_symbol(node)]
        env_ptr = self.emit_closure_env(node)
        value = ir.Constant(closure_type, ir.Undefined)
        value = self.ctx.builder.insert_value(value, fn.bitcast(closure_type.elements[0]), [0], name="closure.call")
        value = self.ctx.builder.insert_value(value, env_ptr, [1], name="closure.env")
        return value

    def emit_generic_function_value(self, node: GenericFunctionValue):
        closure_type = llvm_type(node.type)
        thunk = self.function_value_thunk(node.name, node.type)
        value = ir.Constant(closure_type, ir.Undefined)
        value = self.ctx.builder.insert_value(value, thunk.bitcast(closure_type.elements[0]), [0], name="fn.value.call")
        value = self.ctx.builder.insert_value(value, ir.Constant(I8PTR, None), [1], name="fn.value.env")
        return value

    def function_value_thunk(self, fn_name: str, fn_value_type: str):
        if fn_name in self.ctx.function_value_thunks:
            return self.ctx.function_value_thunks[fn_name]
        parsed = parse_fn_type(fn_value_type)
        if parsed is None:
            raise RuntimeError(f"{fn_name} is not a function value")
        param_types, ret_type = parsed
        module_name = getattr(getattr(self.ctx.fn_decls[fn_name], "source_file", None), "module_name", "<memory>")
        thunk_name = abi_symbol("FV", module_name, f"fnval_{fn_name}", f"fnval\0{module_name}\0{fn_name}\0{fn_value_type}")
        thunk_type = ir.FunctionType(llvm_type(ret_type), [I8PTR] + [llvm_type(t) for t in param_types])
        thunk = ir.Function(self.ctx.module, thunk_type, name=thunk_name)
        thunk.linkage = "internal"
        self.ctx.function_value_thunks[fn_name] = thunk

        block = thunk.append_basic_block("entry")
        saved_builder = self.ctx.builder
        self.ctx.builder = ir.IRBuilder(block)
        target = self.ctx.module.globals[self.function_symbol(self.ctx.fn_decls[fn_name])]
        target_args = []
        arg_idx = 1  # skip env ptr
        for param_type in param_types:
            slice_elem = parse_slice_type(param_type)
            if slice_elem is not None:
                slice_val = thunk.args[arg_idx]
                arg_idx += 1
                target_args.append(self.ctx.builder.extract_value(slice_val, 0, name="thunk.slice.ptr"))
                target_args.append(self.ctx.builder.extract_value(slice_val, 1, name="thunk.slice.len"))
                target_args.append(self.ctx.builder.extract_value(slice_val, 2, name="thunk.slice.cap"))
            else:
                target_args.append(thunk.args[arg_idx])
                arg_idx += 1
        result = self.ctx.builder.call(target, target_args)
        if ret_type == "void":
            self.ctx.builder.ret_void()
        else:
            self.ctx.builder.ret(result)
        self.ctx.builder = saved_builder
        return thunk

    def emit_closure_env(self, node: FunctionExpr):
        captures = getattr(node, "captures", [])
        if not captures:
            return ir.Constant(I8PTR, None)
        env_type = self.ctx.closure_env_types[node.closure_id]
        size = self.ctx.sizeof_fields([capture_type for _name, capture_type in captures])
        raw = self.ctx.malloc_bytes(ir.Constant(ir.IntType(64), max(size, 1)))
        env_ptr = self.ctx.builder.bitcast(raw, env_type.as_pointer(), name="closure.env.alloc")
        for i, (capture_name, capture_type) in enumerate(captures):
            source_ptr, _source_type = self.ctx.vars[capture_name]
            capture_value = self.ctx.builder.load(source_ptr, name=f"capture.{safe_user_ident(capture_name)}")
            field_ptr = self.ctx.builder.gep(
                env_ptr,
                [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), i)],
                inbounds=True,
                name=f"capture.{safe_user_ident(capture_name)}.store.ptr",
            )
            self.ctx.builder.store(self.ctx.cast_to(capture_value, capture_type), field_ptr)
        return self.ctx.builder.bitcast(env_ptr, I8PTR, name="closure.env.i8")

    def emit_closure_call(self, node: FunctionCall):
        closure = self.ctx.emit_expr(Identifier(node.name))
        call_ptr = self.ctx.builder.extract_value(closure, 0)
        env = self.ctx.builder.extract_value(closure, 1)
        param_types = getattr(node, "closure_param_types", [arg.type for arg in node.args])
        args = [env] + [self.ctx.emit_coerced_expr(arg, ptype) for arg, ptype in zip(node.args, param_types)]
        return self.ctx.builder.call(call_ptr, args)
