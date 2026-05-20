"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


from compiler.builtins import infer_builtin_call


class TypeCheckError(Exception):
    pass


def infer_types(program: "Program", symtab: "SymbolTable", source: str | None = None):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, While, FunctionDeclaration, Return,
        StructDecl, StructLiteral, FieldAccess,
        EnumDecl, EnumRef, Switch, ForIn,
        IfExpr, BlockExpr, IntegerLiteral, StringLiteral, BoolLiteral, BinaryOp, UnaryOp, FunctionCall, Identifier,
        FunctionExpr,
        ArrayLiteral, SliceLiteral, IndexAccess, SliceExpr, MethodCall, TryCatch, Throw, Defer, Break
    )

    current_return_type = "void"
    break_depth = 0
    closure_stack = []
    inferred_return_values = []
    inferred_void_return = False
    function_decls = {}
    method_decls = {}
    resolving_returns = []

    def line_col(text: str | None, pos: int) -> tuple[int, int]:
        if text is None:
            return 0, 0
        line = text.count("\n", 0, pos) + 1
        last_nl = text.rfind("\n", 0, pos)
        col = pos + 1 if last_nl < 0 else pos - last_nl
        return line, col

    def fail(message, node=None):
        span = getattr(node, "span", None)
        source_file = getattr(node, "source_file", None)
        node_source = source_file.source if source_file is not None else source
        if span and node_source is not None:
            line, col = line_col(node_source, span[0])
            if source_file is not None and not source_file.path.startswith("<"):
                raise TypeCheckError(f"{source_file.path}:{line}:{col}: {message}")
            raise TypeCheckError(f"{line}:{col}: {message}")
        raise TypeCheckError(message)

    def require_type(actual, expected, context, node=None):
        if actual != expected:
            fail(f"{context}: expected {expected}, got {actual}", node)

    def require_arg_count(args, expected, context, node=None):
        if len(args) != expected:
            fail(f"{context}: expected {expected} args, got {len(args)}", node)

    def fn_type(params, ret_type):
        return f"fn({','.join(params)})->{ret_type}"

    def parse_fn_type(nc_type):
        if not isinstance(nc_type, str) or not nc_type.startswith("fn("):
            return None
        close = nc_type.find(")->")
        if close < 0:
            return None
        args_s = nc_type[3:close]
        args = [] if args_s == "" else args_s.split(",")
        return args, nc_type[close + 3:]

    def ends_with_return(stmts):
        return bool(stmts) and isinstance(stmts[-1], Return)

    def block_tail_expr(block):
        if not block.statements:
            return None
        last = block.statements[-1]
        if isinstance(last, ExpressionStatement):
            return last.expr
        return None

    def tail_expr_type(expr):
        if isinstance(expr, FunctionCall) and expr.name == "gc_live":
            return None
        if getattr(expr, "type", None) == "void":
            return None
        return expr.type

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration):
            if top_stmt.receiver_name:
                type_name = top_stmt.receiver_type.lstrip("*")
                method_decls[(type_name, top_stmt.name)] = top_stmt
            else:
                function_decls[top_stmt.name] = top_stmt

    def infer_block_value(block, context_node):
        symtab.push_scope()
        has_tail = block_tail_expr(block)
        body = block.statements[:-1] if has_tail else block.statements
        walk_stmts(body)
        tail = block_tail_expr(block)
        if tail is None:
            symtab.pop_scope()
            return "void"
        walk_expr(tail)
        tail_type = tail_expr_type(tail) or "void"
        symtab.pop_scope()
        return tail_type

    def infer_if_value(stmt):
        then_type = infer_block_value(stmt.then_block, stmt)
        else_type = infer_block_value(stmt.else_block, stmt) if stmt.else_block is not None else "void"
        require_type(else_type, then_type, "if expression branches", stmt)
        return then_type

    def require_assignable(target):
        if not isinstance(target, (Identifier, IndexAccess, FieldAccess)):
            fail(f"invalid assignment target: {type(target).__name__}", target)

    def walk_expr(node):
        if isinstance(node, IntegerLiteral):
            node.type = "i32"
        elif isinstance(node, StringLiteral):
            node.type = "str"
        elif isinstance(node, BoolLiteral):
            node.type = "bool"
        elif isinstance(node, Identifier):
            sym = symtab.lookup(node.name)
            node.type = sym.nc_type
            if closure_stack and sym.scope_level < closure_stack[-1]["level"] and sym.nc_type not in ("struct", "enum"):
                ctx = closure_stack[-1]
                if node.name not in ctx["captures"]:
                    ctx["captures"][node.name] = sym.nc_type
                node.is_capture = True
                node.capture_type = sym.nc_type
        elif isinstance(node, UnaryOp):
            walk_expr(node.operand)
            if node.op == "!":
                require_type(node.operand.type, "bool", "logical not", node)
                node.type = "bool"
            else:
                node.type = node.operand.type
        elif isinstance(node, BinaryOp):
            walk_expr(node.left)
            walk_expr(node.right)
            if node.op in ("&&", "||"):
                require_type(node.left.type, "bool", f"logical operator {node.op}", node)
                require_type(node.right.type, "bool", f"logical operator {node.op}", node)
                node.type = "bool"
                return
            if node.op == "+" and node.left.type == "str":
                require_type(node.right.type, "str", "string concatenation", node)
                node.type = "str"
                return
            if node.op in ("==", "!="):
                require_type(node.right.type, node.left.type, "comparison", node)
                node.type = "bool"
                return
            if node.op in ("<", ">", "<=", ">="):
                require_type(node.right.type, node.left.type, "comparison", node)
                node.type = "bool"
                return
            require_type(node.right.type, node.left.type, f"binary operator {node.op}", node)
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                walk_expr(arg)
            builtin_type = infer_builtin_call(node, require_arg_count, require_type, fail)
            if builtin_type is not None:
                node.type = builtin_type
                return
            funcs = getattr(symtab, "_functions", {})
            if node.name in funcs:
                ret_type, params = funcs[node.name]
                if ret_type is None:
                    ret_type = resolve_function_return(node.name, node)
                require_arg_count(node.args, len(params), node.name, node)
                for arg, (pname, ptype) in zip(node.args, params):
                    require_type(arg.type, ptype, f"argument {pname} to {node.name}", arg)
                node.type = ret_type
                node.is_closure_call = False
            else:
                sym = symtab.lookup(node.name)
                parsed = parse_fn_type(sym.nc_type)
                if parsed is None:
                    fail(f"Function '{node.name}' not found", node)
                param_types, ret_type = parsed
                require_arg_count(node.args, len(param_types), node.name, node)
                for i, (arg, ptype) in enumerate(zip(node.args, param_types)):
                    require_type(arg.type, ptype, f"argument {i + 1} to {node.name}", arg)
                node.type = ret_type
                node.is_closure_call = True
        elif isinstance(node, FunctionExpr):
            nonlocal current_return_type
            prev_return_type = current_return_type
            if not node.return_type_explicit:
                infer_function_expr_return(node)
            current_return_type = node.return_type or "void"
            symtab.push_scope()
            for pname, ptype in node.params:
                symtab.declare(pname, ptype)
            ctx = {"level": symtab._level, "captures": {}}
            closure_stack.append(ctx)
            walk_stmts(node.body.statements)
            closure_stack.pop()
            if current_return_type != "void" and not ends_with_return(node.body.statements):
                if node.body.statements and isinstance(node.body.statements[-1], ExpressionStatement):
                    require_type(node.body.statements[-1].expr.type, current_return_type, "function expression tail expression", node.body.statements[-1].expr)
                else:
                    fail(f"function expression: missing return {current_return_type}", node)
            node.captures = list(ctx["captures"].items())
            node.type = fn_type([ptype for _pname, ptype in node.params], current_return_type)
            current_return_type = prev_return_type
            symtab.pop_scope()
        elif isinstance(node, IfExpr):
            walk_expr(node.condition)
            require_type(node.condition.type, "bool", "if condition", node.condition)
            node.type = infer_if_value(node)
        elif isinstance(node, BlockExpr):
            node.type = infer_block_value(node.block, node)
        elif isinstance(node, EnumRef):
            # 验证 enum 类型存在
            symtab.lookup(node.enum_name)
            variants = symtab.lookup_enum(node.enum_name)
            if node.variant not in variants:
                fail(f"enum {node.enum_name}: unknown variant {node.variant}", node)
            node.type = node.enum_name
        elif isinstance(node, StructLiteral):
            if node.heap:
                node.type = "*" + node.name
            else:
                node.type = node.name
            for _fname, fval in node.fields:
                walk_expr(fval)
            fields = symtab.lookup_struct(node.name)
            seen = set()
            for fname, fval in node.fields:
                if fname in seen:
                    fail(f"struct {node.name}: duplicate field {fname}", node)
                seen.add(fname)
                if fname not in fields:
                    fail(f"struct {node.name}: unknown field {fname}", node)
                require_type(fval.type, fields[fname], f"struct {node.name}.{fname}", fval)
            for fname in fields:
                if fname not in seen:
                    fail(f"struct {node.name}: missing field {fname}", node)
        elif isinstance(node, FieldAccess):
            walk_expr(node.obj)
            obj_type = node.obj.type
            if obj_type.startswith("*"):
                obj_type = obj_type[1:]
            fields = symtab.lookup_struct(obj_type)
            if node.field not in fields:
                fail(f"{obj_type}: unknown field {node.field}", node)
            node.type = fields[node.field]
        elif isinstance(node, MethodCall):
            walk_expr(node.obj)
            for arg in node.args:
                walk_expr(arg)
            obj_type = node.obj.type
            if obj_type.startswith("*"):
                obj_type = obj_type[1:]
            methods = getattr(symtab, "_methods", {})
            if obj_type in methods and node.method in methods[obj_type]:
                ret_type, params = methods[obj_type][node.method]
                if ret_type is None:
                    ret_type = resolve_method_return(obj_type, node.method, node)
                require_arg_count(node.args, len(params), f"method {node.method}", node)
                for arg, (pname, ptype) in zip(node.args, params):
                    require_type(arg.type, ptype, f"argument {pname} to method {node.method}", arg)
                node.type = ret_type
            else:
                fail(f"{obj_type}: method {node.method} not found", node)
        elif isinstance(node, ArrayLiteral):
            if len(node.elements) != node.length:
                fail(f"array literal: expected {node.length} elements, got {len(node.elements)}", node)
            for elem in node.elements:
                walk_expr(elem)
                require_type(elem.type, node.elem_type, "array element", elem)
            node.type = f"[{node.length}]{node.elem_type}"
        elif isinstance(node, SliceLiteral):
            for elem in node.elements:
                walk_expr(elem)
                require_type(elem.type, node.elem_type, "slice element", elem)
            node.type = f"[]{node.elem_type}"
        elif isinstance(node, IndexAccess):
            walk_expr(node.obj)
            walk_expr(node.index)
            if node.obj.type == "str":
                require_type(node.index.type, "i32", "index", node.index)
                node.type = "i32"
            elif node.obj.type == "nc_map":
                require_type(node.index.type, "str", "map key", node.index)
                node.type = "str"
            elif node.obj.type.startswith("[]"):
                require_type(node.index.type, "i32", "index", node.index)
                node.type = node.obj.type[2:]
            elif node.obj.type.startswith("["):
                require_type(node.index.type, "i32", "index", node.index)
                node.type = node.obj.type.split("]", 1)[1]
            else:
                require_type(node.index.type, "i32", "index", node.index)
                node.type = node.obj.type
        elif isinstance(node, SliceExpr):
            walk_expr(node.array)
            if node.start:
                walk_expr(node.start)
                require_type(node.start.type, "i32", "slice start", node.start)
            if node.end:
                walk_expr(node.end)
                require_type(node.end.type, "i32", "slice end", node.end)
            if node.array.type == "str":
                node.type = "str"
            elif node.array.type.startswith("[]"):
                node.type = node.array.type
            elif node.array.type.startswith("["):
                node.type = "[]" + node.array.type.split("]", 1)[1]
            else:
                node.type = node.array.type

    def walk_stmts(stmts: list):
        nonlocal current_return_type, break_depth, inferred_void_return
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                walk_expr(stmt.initializer)
                stmt.type = stmt.annotation or stmt.initializer.type
                if stmt.type == "void":
                    fail(f"let {stmt.name}: cannot bind void value", stmt)
                require_type(stmt.initializer.type, stmt.type, f"let {stmt.name}", stmt)
                symtab.declare(stmt.name, stmt.type)
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.target)
                require_assignable(stmt.target)
                if isinstance(stmt.target, Identifier) and getattr(stmt.target, "is_capture", False):
                    fail(f"cannot assign to captured variable '{stmt.target.name}'", stmt.target)
                walk_expr(stmt.expr)
                require_type(stmt.expr.type, stmt.target.type, "assignment", stmt.expr)
            elif isinstance(stmt, While):
                walk_expr(stmt.condition)
                require_type(stmt.condition.type, "bool", "for condition", stmt.condition)
                symtab.push_scope()
                break_depth += 1
                walk_stmts(stmt.body.statements)
                break_depth -= 1
                symtab.pop_scope()
            elif isinstance(stmt, FunctionDeclaration):
                symtab.push_scope()
                prev_return_type = current_return_type
                if not stmt.return_type_explicit:
                    if stmt.receiver_name:
                        resolve_method_return(stmt.receiver_type.lstrip("*"), stmt.name, stmt)
                    else:
                        resolve_function_return(stmt.name, stmt)
                current_return_type = stmt.return_type or "void"
                if stmt.receiver_name:
                    symtab.declare(stmt.receiver_name, stmt.receiver_type)
                for pname, _ptype in stmt.params:
                    symtab.declare(pname, _ptype)
                walk_stmts(stmt.body.statements)
                if current_return_type != "void" and not ends_with_return(stmt.body.statements):
                    if stmt.body.statements and isinstance(stmt.body.statements[-1], ExpressionStatement):
                        require_type(stmt.body.statements[-1].expr.type, current_return_type, f"function {stmt.name} tail expression", stmt.body.statements[-1].expr)
                    else:
                        fail(f"function {stmt.name}: missing return {current_return_type}", stmt)
                current_return_type = prev_return_type
                symtab.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
                    if current_return_type is None:
                        inferred_return_values.append((stmt.expr.type, stmt))
                    else:
                        require_type(stmt.expr.type, current_return_type, "return", stmt)
                elif current_return_type != "void":
                    if current_return_type is None:
                        inferred_void_return = True
                    else:
                        fail(f"return: expected {current_return_type}, got void", stmt)
            elif isinstance(stmt, StructDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, EnumDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, Switch):
                walk_expr(stmt.scrutinee)
                break_depth += 1
                for case_val, case_stmt in stmt.cases:
                    walk_expr(case_val)
                    require_type(case_val.type, stmt.scrutinee.type, "switch case", case_val)
                    walk_stmts([case_stmt])
                break_depth -= 1
            elif isinstance(stmt, ForIn):
                if stmt.start is not None:
                    walk_expr(stmt.start)
                    walk_expr(stmt.end)
                    require_type(stmt.start.type, "i32", "for range start", stmt.start)
                    require_type(stmt.end.type, "i32", "for range end", stmt.end)
                else:
                    walk_expr(stmt.iterable)
                    if not stmt.iterable.type.startswith("[]"):
                        fail(f"for-in: expected slice, got {stmt.iterable.type}", stmt.iterable)
                symtab.push_scope()
                symtab.declare(stmt.index, "i32")
                if stmt.value:
                    symtab.declare(stmt.value, stmt.iterable.type[2:])
                break_depth += 1
                walk_stmts(stmt.body.statements)
                break_depth -= 1
                symtab.pop_scope()
            elif isinstance(stmt, TryCatch):
                walk_stmts(stmt.try_block.statements)
                symtab.push_scope()
                symtab.declare(stmt.error_name, "str")
                walk_stmts(stmt.catch_block.statements)
                symtab.pop_scope()
            elif isinstance(stmt, Throw):
                walk_expr(stmt.expr)
                require_type(stmt.expr.type, "str", "throw", stmt)
            elif isinstance(stmt, Defer):
                walk_stmts(stmt.body.statements)
            elif isinstance(stmt, Break):
                if break_depth <= 0:
                    fail("break outside loop or switch", stmt)
            elif isinstance(stmt, Block):
                symtab.push_scope()
                walk_stmts(stmt.statements)
                symtab.pop_scope()

    def infer_return_from_body(fn_node, display_name):
        nonlocal current_return_type, inferred_return_values, inferred_void_return
        prev_return_type = current_return_type
        prev_values = inferred_return_values
        prev_void = inferred_void_return
        current_return_type = None
        inferred_return_values = []
        inferred_void_return = False

        symtab.push_scope()
        if isinstance(fn_node, FunctionDeclaration) and fn_node.receiver_name:
            symtab.declare(fn_node.receiver_name, fn_node.receiver_type)
        for pname, ptype in fn_node.params:
            symtab.declare(pname, ptype)
        walk_stmts(fn_node.body.statements)

        tail = block_tail_expr(fn_node.body)
        if tail is not None:
            ret_type = tail_expr_type(tail)
            if ret_type is not None:
                inferred_return_values.append((ret_type, tail))

        values = inferred_return_values
        saw_void = inferred_void_return
        symtab.pop_scope()

        current_return_type = prev_return_type
        inferred_return_values = prev_values
        inferred_void_return = prev_void

        if values and saw_void:
            fail(f"{display_name}: cannot mix value return and void return", values[0][1])
        if not values:
            return "void"
        first_type = values[0][0]
        for ret_type, ret_node in values[1:]:
            require_type(ret_type, first_type, f"{display_name} return type", ret_node)
        return first_type

    def update_function_signature(name, ret_type):
        symtab._functions[name] = (ret_type, symtab._functions[name][1])
        symtab._scopes[0][name].nc_type = ret_type

    def update_method_signature(type_name, method_name, ret_type):
        params = symtab._methods[type_name][method_name][1]
        symtab._methods[type_name][method_name] = (ret_type, params)
        mangled = f"{type_name}_{method_name}"
        if mangled in symtab._scopes[0]:
            symtab._scopes[0][mangled].nc_type = ret_type

    def resolve_function_return(name, node=None):
        if name not in function_decls:
            fail(f"Function '{name}' not found", node)
        fn_node = function_decls[name]
        if fn_node.return_type_explicit:
            fn_node.return_type = fn_node.return_type or "void"
            update_function_signature(name, fn_node.return_type)
            return fn_node.return_type
        if fn_node.return_type is not None:
            return fn_node.return_type
        key = ("function", name)
        if key in resolving_returns:
            fail(f"function {name}: return type inference cycle; add explicit return type", node or fn_node)
        resolving_returns.append(key)
        ret_type = infer_return_from_body(fn_node, f"function {name}")
        resolving_returns.pop()
        fn_node.return_type = ret_type
        update_function_signature(name, ret_type)
        return ret_type

    def resolve_method_return(type_name, method_name, node=None):
        key_name = (type_name, method_name)
        if key_name not in method_decls:
            fail(f"{type_name}: method {method_name} not found", node)
        fn_node = method_decls[key_name]
        if fn_node.return_type_explicit:
            fn_node.return_type = fn_node.return_type or "void"
            update_method_signature(type_name, method_name, fn_node.return_type)
            return fn_node.return_type
        if fn_node.return_type is not None:
            return fn_node.return_type
        key = ("method", type_name, method_name)
        if key in resolving_returns:
            fail(f"function {method_name}: return type inference cycle; add explicit return type", node or fn_node)
        resolving_returns.append(key)
        ret_type = infer_return_from_body(fn_node, f"function {method_name}")
        resolving_returns.pop()
        fn_node.return_type = ret_type
        update_method_signature(type_name, method_name, ret_type)
        return ret_type

    def infer_function_expr_return(node):
        ret_type = infer_return_from_body(node, "function expression")
        node.return_type = ret_type
        return ret_type

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration):
            if top_stmt.receiver_name:
                resolve_method_return(top_stmt.receiver_type.lstrip("*"), top_stmt.name, top_stmt)
            else:
                resolve_function_return(top_stmt.name, top_stmt)

    walk_stmts(program.statements)
