"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


from compiler.builtins import NUMERIC_TYPES, SCALAR_TYPES, STRINGIFIABLE_TYPES, infer_builtin_call
from compiler.type_ref import (
    ArrayTypeRef, FunctionType, GenericType, NamedType, PointerType, SliceType,
    parse_fn_type, parse_map_type, parse_type_ref,
)


class TypeCheckError(Exception):
    pass


def infer_types(program: "Program", symtab: "SymbolTable", source: str | None = None):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Update, Block, ForCondition, FunctionDeclaration, Return, ImportDecl,
        StructDecl, IfaceDecl, StructLiteral, FieldAccess,
        EnumDecl, EnumRef, ForIn,
        IfExpr, BlockExpr, MatchExpr, IntegerLiteral, FloatLiteral, StringLiteral, InterpolatedString, RuneLiteral, BoolLiteral, NilLiteral, BinaryOp, UnaryOp, FunctionCall, SizeOfType, Identifier,
        ExternBlock, FunctionExpr,
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
        if not is_assignable_type(actual, expected):
            fail(f"{context}: expected {expected}, got {actual}", node)

    def require_arg_count(args, expected, context, node=None):
        if len(args) != expected:
            fail(f"{context}: expected {expected} args, got {len(args)}", node)

    def fn_type(params, ret_type):
        return f"fn({','.join(params)})->{ret_type}"

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
        if isinstance(expr, FunctionCall) and expr.name == "runtime.gc_live":
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
        narrowed = getattr(block, "_narrowed_vars", None)
        if narrowed:
            narrowed_read_stack.append(narrowed)
            narrowed_assign_forbidden.append(set(narrowed.keys()))
        has_tail = block_tail_expr(block)
        body = block.statements[:-1] if has_tail else block.statements
        walk_stmts(body)
        tail = block_tail_expr(block)
        if tail is None:
            if narrowed:
                narrowed_assign_forbidden.pop()
                narrowed_read_stack.pop()
            symtab.pop_scope()
            return "void"
        walk_expr(tail)
        tail_type = tail_expr_type(tail) or "void"
        if narrowed:
            narrowed_assign_forbidden.pop()
            narrowed_read_stack.pop()
        symtab.pop_scope()
        return tail_type

    def infer_if_value(stmt):
        then_type = infer_block_value(stmt.then_block, stmt)
        else_type = infer_block_value(stmt.else_block, stmt) if stmt.else_block is not None else "void"
        require_type(else_type, then_type, "if expression branches", stmt)
        return then_type

    def match_pattern_key(pattern):
        if isinstance(pattern, EnumRef):
            return ("enum", pattern.enum_name, pattern.variant)
        if isinstance(pattern, IntegerLiteral):
            return ("int", pattern.value)
        if isinstance(pattern, StringLiteral):
            return ("str", pattern.value)
        if isinstance(pattern, BoolLiteral):
            return ("bool", pattern.value)
        fail(f"match pattern: unsupported pattern {type(pattern).__name__}", pattern)

    def infer_match_value(node):
        walk_expr(node.scrutinee)
        if not node.arms:
            fail("match expression: expected at least one arm", node)

        scrut_type = node.scrutinee.type
        enum_variants = None
        try:
            if symtab.lookup(scrut_type).nc_type == "enum":
                enum_variants = symtab.lookup_enum(scrut_type)
        except NameError:
            enum_variants = None

        result_type = None
        seen_else = False
        seen_patterns = set()
        seen_enum_variants = set()

        for i, (pattern, body) in enumerate(node.arms):
            if seen_else:
                fail("match expression: else must be the last arm", pattern or body)
            if pattern is None:
                seen_else = True
                if i != len(node.arms) - 1:
                    fail("match expression: else must be the last arm", body)
            else:
                walk_expr(pattern)
                match_pattern_key(pattern)
                require_type(pattern.type, scrut_type, "match pattern", pattern)
                key = match_pattern_key(pattern)
                if key in seen_patterns:
                    fail("match expression: duplicate pattern", pattern)
                seen_patterns.add(key)
                if isinstance(pattern, EnumRef):
                    seen_enum_variants.add(pattern.variant)
            walk_expr(body)
            if result_type is None:
                result_type = body.type
            else:
                require_type(body.type, result_type, "match expression arms", body)

        if not seen_else:
            if enum_variants is None:
                fail("match expression: non-enum match requires else", node)
            missing = enum_variants - seen_enum_variants
            if missing:
                fail(f"match expression: missing enum variants {', '.join(sorted(missing))}", node)

        return result_type or "void"

    def require_assignable(target):
        if not isinstance(target, (Identifier, IndexAccess, FieldAccess)):
            fail(f"invalid assignment target: {type(target).__name__}", target)

    def is_pointer_type(t):
        return isinstance(t, str) and t.startswith("*")

    def is_nullable_pointer_type(t):
        return isinstance(t, str) and t.startswith("?*")

    def nonnullable_pointer_type(t):
        return "*" + t[2:] if is_nullable_pointer_type(t) else t

    def is_nil_type(t):
        return t == "__nil"

    def is_numeric_type(t):
        return t in NUMERIC_TYPES

    def validate_map_type(t, node=None):
        map_args = parse_map_type(t)
        if map_args is None:
            return None
        if len(map_args) != 2:
            fail(f"map: expected 2 type args, got {len(map_args)}", node)
        key_type, value_type = map_args
        if key_type not in SCALAR_TYPES:
            fail(f"map key type: expected scalar, got {key_type}", node)
        if value_type not in SCALAR_TYPES:
            fail(f"map value type: expected scalar, got {value_type}", node)
        return key_type, value_type

    def validate_sized_type(t, node=None, *, allow_void=False):
        if t == "void":
            if allow_void:
                return
            fail("size_of: void has no size", node)
        ref = parse_type_ref(t)

        def walk(r, *, allow_void_here=False):
            if isinstance(r, NamedType):
                name = r.name
                if name == "void":
                    if allow_void_here:
                        return
                    fail("size_of: void has no size", node)
                require_public_qualified(name, node)
                if name in NUMERIC_TYPES or name in {"bool", "str", "rune"}:
                    return
                if name == "map":
                    fail("size_of: map requires type arguments", node)
                try:
                    sym = symtab.lookup(name)
                except NameError:
                    fail(f"size_of: unknown type {name}", node)
                if sym.nc_type not in {"struct", "enum", "iface"}:
                    fail(f"size_of: unknown type {name}", node)
                return
            if isinstance(r, PointerType):
                walk(r.inner, allow_void_here=True)
                return
            if isinstance(r, SliceType):
                walk(r.elem)
                return
            if isinstance(r, ArrayTypeRef):
                walk(r.elem)
                return
            if isinstance(r, FunctionType):
                for p in r.params:
                    walk(p)
                walk(r.ret, allow_void_here=True)
                return
            if isinstance(r, GenericType):
                if not isinstance(r.base, NamedType):
                    fail(f"size_of: unsupported type {t}", node)
                base = r.base.name
                if base != "map":
                    fail(f"size_of: unknown type {base}", node)
                if len(r.args) != 2:
                    fail(f"map: expected 2 type args, got {len(r.args)}", node)
                for arg in r.args:
                    walk(arg)
                key_type, value_type = validate_map_type(t, node)
                return
            fail(f"size_of: unsupported type {t}", node)

        walk(ref, allow_void_here=allow_void)

    def is_rune_type(t):
        return t == "rune"

    def is_iface_type(t):
        return isinstance(t, str) and t in getattr(symtab, "_ifaces", {})

    def require_public_qualified(name, node=None):
        if isinstance(name, str) and "." in name and name.rsplit(".", 1)[1].startswith("_"):
            fail(f"symbol '{name}' is private", node)

    def is_integer_type(t):
        return t in {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"}

    def is_extern_abi_type(t):
        if t == "void":
            return True
        if t in {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64", "bool"}:
            return True
        if isinstance(t, str) and t.startswith("*"):
            return is_extern_abi_type(t[1:])
        if isinstance(t, str) and t.startswith("?*"):
            return is_extern_abi_type(t[2:])
        return False

    def validate_extern_function(fn):
        if fn.type_params:
            fail("generic extern functions are not supported", fn)
        ret = fn.return_type or "void"
        if not is_extern_abi_type(ret):
            fail(f"extern function {fn.name}: unsupported return type {ret}", fn)
        for pname, ptype in fn.params:
            if not is_extern_abi_type(ptype) or ptype == "void":
                fail(f"extern function {fn.name}: unsupported parameter {pname}: {ptype}", fn)

    def is_assignable_type(actual, expected):
        if actual == expected:
            return True
        if is_iface_type(expected):
            return pointer_implements_iface(actual, expected)
        if is_nil_type(actual):
            return is_nullable_pointer_type(expected)
        if is_pointer_type(actual) and is_nullable_pointer_type(expected):
            return actual[1:] == expected[2:]
        return False

    def iface_method_set(iface_name, stack=None):
        stack = stack or []
        if iface_name not in getattr(symtab, "_ifaces", {}):
            fail(f"iface {iface_name}: embedded iface not found")
        iface = symtab._ifaces[iface_name]
        if iface.get("method_set") is not None:
            return iface["method_set"]
        if iface_name in stack:
            fail(f"iface {iface_name}: embedded iface cycle")
        methods = {}
        order = []
        def add(name, params, ret):
            sig = ([ptype for _pname, ptype in params], ret or "void")
            if name in methods and methods[name] != sig:
                fail(f"iface {iface_name}: conflicting method {name}")
            if name not in methods:
                order.append(name)
            methods[name] = sig
        for embed in iface["embeds"]:
            if embed not in getattr(symtab, "_ifaces", {}):
                fail(f"iface {iface_name}: embedded iface {embed} not found")
            for mname, (param_types, ret) in iface_method_set(embed, stack + [iface_name]).items():
                add(mname, [(f"arg{i}", t) for i, t in enumerate(param_types)], ret)
        for mname, params, ret in iface["methods"]:
            add(mname, params, ret)
        iface["method_order"] = order
        iface["method_set"] = methods
        return methods

    def pointer_implements_iface(actual, iface_name):
        if not is_pointer_type(actual) or is_nullable_pointer_type(actual):
            return False
        type_name = actual[1:]
        methods = getattr(symtab, "_methods", {}).get(type_name, {})
        for mname, (param_types, ret_type) in iface_method_set(iface_name).items():
            if mname not in methods:
                return False
            actual_ret, actual_params = methods[mname]
            if actual_ret is None:
                actual_ret = resolve_method_return(type_name, mname)
            if (actual_ret or "void") != (ret_type or "void"):
                return False
            if [ptype for _pname, ptype in actual_params] != param_types:
                return False
        return True

    def maybe_narrow_condition(condition):
        if not isinstance(condition, BinaryOp) or condition.op != "!=":
            return None
        left_is_var = isinstance(condition.left, Identifier) and is_nil_type(getattr(condition.right, "type", None))
        right_is_var = isinstance(condition.right, Identifier) and is_nil_type(getattr(condition.left, "type", None))
        var = condition.left if left_is_var else condition.right if right_is_var else None
        if var is None:
            return None
        if not is_nullable_pointer_type(var.type):
            return None
        return var.name, nonnullable_pointer_type(var.type)

    narrowed_read_stack = []
    narrowed_assign_forbidden = []

    def lookup_narrowed(name):
        for narrowed in reversed(narrowed_read_stack):
            if name in narrowed:
                return narrowed[name]
        return None

    def is_assignment_forbidden(name):
        return any(name in scope for scope in narrowed_assign_forbidden)

    def walk_expr(node):
        if isinstance(node, IntegerLiteral):
            node.type = node.suffix_type or "i32"
        elif isinstance(node, FloatLiteral):
            node.type = node.suffix_type or "f64"
        elif isinstance(node, StringLiteral):
            node.type = "str"
        elif isinstance(node, RuneLiteral):
            node.type = "rune"
        elif isinstance(node, InterpolatedString):
            for part in node.parts:
                walk_expr(part)
                if part.type not in STRINGIFIABLE_TYPES:
                    fail(f"string interpolation: cannot convert {part.type} to str", part)
            node.type = "str"
        elif isinstance(node, BoolLiteral):
            node.type = "bool"
        elif isinstance(node, NilLiteral):
            node.type = "__nil"
        elif isinstance(node, Identifier):
            sym = symtab.lookup(node.name)
            node.type = lookup_narrowed(node.name) or sym.nc_type
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
            elif node.op == "~":
                if not is_integer_type(node.operand.type):
                    fail(f"unary operator ~: expected integer operand, got {node.operand.type}", node)
                node.type = node.operand.type
            elif node.op == "-":
                if not is_numeric_type(node.operand.type):
                    fail(f"unary operator -: expected numeric operand, got {node.operand.type}", node)
                node.type = node.operand.type
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
                if is_nil_type(node.left.type) or is_nil_type(node.right.type):
                    other_type = node.right.type if is_nil_type(node.left.type) else node.left.type
                    if not is_nullable_pointer_type(other_type):
                        fail(f"nil comparison requires nullable pointer, got {other_type}", node)
                    node.type = "bool"
                    return
                require_type(node.right.type, node.left.type, "comparison", node)
                if is_rune_type(node.left.type) and node.op not in ("==", "!="):
                    fail(f"rune type: operator {node.op} is not allowed", node)
                node.type = "bool"
                return
            if node.op in ("<", ">", "<=", ">="):
                if is_rune_type(node.left.type) or is_rune_type(node.right.type):
                    fail(f"rune type: operator {node.op} is not allowed", node)
                if (is_pointer_type(node.left.type) or is_pointer_type(node.right.type)
                        or is_nullable_pointer_type(node.left.type) or is_nullable_pointer_type(node.right.type)):
                    fail(f"pointer type {node.left.type}: operator {node.op} is not allowed", node)
                if not (is_numeric_type(node.left.type) and is_numeric_type(node.right.type)):
                    fail(f"comparison: expected numeric operands, got {node.left.type} and {node.right.type}", node)
                require_type(node.right.type, node.left.type, "comparison", node)
                node.type = "bool"
                return
            if (is_pointer_type(node.left.type) or is_pointer_type(node.right.type)
                    or is_nullable_pointer_type(node.left.type) or is_nullable_pointer_type(node.right.type)):
                fail(f"pointer type {node.left.type}: operator {node.op} is not allowed", node)
            if is_rune_type(node.left.type) or is_rune_type(node.right.type):
                fail(f"rune type: operator {node.op} is not allowed", node)
            if node.op in ("+", "-", "*", "/"):
                if not (is_numeric_type(node.left.type) and is_numeric_type(node.right.type)):
                    fail(f"binary operator {node.op}: expected numeric operands, got {node.left.type} and {node.right.type}", node)
            if node.op == "%":
                if not (is_integer_type(node.left.type) and is_integer_type(node.right.type)):
                    fail(f"binary operator %: expected integer operands, got {node.left.type} and {node.right.type}", node)
            if node.op in ("&", "|", "^", "<<", ">>"):
                if not (is_integer_type(node.left.type) and is_integer_type(node.right.type)):
                    fail(f"binary operator {node.op}: expected integer operands, got {node.left.type} and {node.right.type}", node)
            require_type(node.right.type, node.left.type, f"binary operator {node.op}", node)
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            require_public_qualified(node.name, node)
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
                try:
                    sym = symtab.lookup(node.name)
                except NameError:
                    fail(f"Function '{node.name}' not found", node)
                parsed = parse_fn_type(sym.nc_type)
                if parsed is None:
                    fail(f"Function '{node.name}' not found", node)
                param_types, ret_type = parsed
                require_arg_count(node.args, len(param_types), node.name, node)
                for i, (arg, ptype) in enumerate(zip(node.args, param_types)):
                    require_type(arg.type, ptype, f"argument {i + 1} to {node.name}", arg)
                node.type = ret_type
                node.is_closure_call = True
                node.closure_param_types = param_types
        elif isinstance(node, SizeOfType):
            validate_sized_type(node.type_name, node)
            node.type = "u64"
        elif isinstance(node, FunctionExpr):
            nonlocal current_return_type
            prev_return_type = current_return_type
            if not node.return_type_explicit:
                infer_function_expr_return(node)
            current_return_type = node.return_type or "void"
            symtab.push_scope()
            for pname, ptype in node.params:
                validate_map_type(ptype, node)
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
            narrowed = maybe_narrow_condition(node.condition)
            if narrowed is not None:
                node.then_block._narrowed_vars = {narrowed[0]: narrowed[1]}
            node.type = infer_if_value(node)
        elif isinstance(node, BlockExpr):
            node.type = infer_block_value(node.block, node)
        elif isinstance(node, MatchExpr):
            node.type = infer_match_value(node)
        elif isinstance(node, EnumRef):
            require_public_qualified(node.enum_name, node)
            # 验证 enum 类型存在
            symtab.lookup(node.enum_name)
            variants = symtab.lookup_enum(node.enum_name)
            if node.variant not in variants:
                fail(f"enum {node.enum_name}: unknown variant {node.variant}", node)
            node.type = node.enum_name
        elif isinstance(node, StructLiteral):
            require_public_qualified(node.name, node)
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
            if is_nullable_pointer_type(obj_type):
                fail(f"nullable pointer type {obj_type}: field access requires if p != nil narrowing", node)
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
            if is_nullable_pointer_type(obj_type):
                fail(f"nullable pointer type {obj_type}: method call requires if p != nil narrowing", node)
            if is_iface_type(obj_type):
                methods = iface_method_set(obj_type)
                if node.method not in methods:
                    fail(f"{obj_type}: method {node.method} not found", node)
                param_types, ret_type = methods[node.method]
                require_arg_count(node.args, len(param_types), f"method {node.method}", node)
                for i, (arg, ptype) in enumerate(zip(node.args, param_types)):
                    require_type(arg.type, ptype, f"argument {i + 1} to method {node.method}", arg)
                node.type = ret_type
                return
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
            elif parse_map_type(node.obj.type) is not None:
                key_type, value_type = validate_map_type(node.obj.type, node)
                require_type(node.index.type, key_type, "map key", node.index)
                node.type = value_type
            elif node.obj.type.startswith("[]"):
                require_type(node.index.type, "i32", "index", node.index)
                node.type = node.obj.type[2:]
            elif node.obj.type.startswith("["):
                require_type(node.index.type, "i32", "index", node.index)
                node.type = node.obj.type.split("]", 1)[1]
            elif is_pointer_type(node.obj.type) or is_nullable_pointer_type(node.obj.type):
                fail(f"pointer type {node.obj.type}: indexing is not allowed", node)
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
                if stmt.annotation:
                    require_public_qualified(stmt.annotation, stmt)
                    validate_map_type(stmt.annotation, stmt)
                walk_expr(stmt.initializer)
                stmt.type = stmt.annotation or stmt.initializer.type
                if stmt.type == "void" or stmt.type == "__nil":
                    fail(f"let {stmt.name}: cannot bind void value", stmt)
                require_type(stmt.initializer.type, stmt.type, f"let {stmt.name}", stmt)
                symtab.declare(stmt.name, stmt.type)
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.target)
                require_assignable(stmt.target)
                if isinstance(stmt.target, Identifier) and is_assignment_forbidden(stmt.target.name):
                    fail(f"cannot assign to narrowed nullable pointer '{stmt.target.name}' inside non-nil block", stmt.target)
                if isinstance(stmt.target, Identifier) and getattr(stmt.target, "is_capture", False):
                    fail(f"cannot assign to captured variable '{stmt.target.name}'", stmt.target)
                walk_expr(stmt.expr)
                if stmt.op == "=":
                    require_type(stmt.expr.type, stmt.target.type, "assignment", stmt.expr)
                else:
                    compound_op = stmt.op[:-1]
                    fake = BinaryOp(stmt.target, compound_op, stmt.expr)
                    fake.span = getattr(stmt, "span", None)
                    fake.left.type = stmt.target.type
                    fake.right.type = stmt.expr.type
                    if compound_op in ("&", "|", "^", "<<", ">>"):
                        if not (is_integer_type(stmt.target.type) and is_integer_type(stmt.expr.type)):
                            fail(f"binary operator {compound_op}: expected integer operands, got {stmt.target.type} and {stmt.expr.type}", stmt)
                    elif compound_op == "%":
                        if not (is_integer_type(stmt.target.type) and is_integer_type(stmt.expr.type)):
                            fail(f"binary operator %: expected integer operands, got {stmt.target.type} and {stmt.expr.type}", stmt)
                    elif compound_op == "+" and stmt.target.type == "str":
                        require_type(stmt.expr.type, "str", "string concatenation", stmt.expr)
                    elif compound_op in ("+", "-", "*", "/"):
                        if not (is_numeric_type(stmt.target.type) and is_numeric_type(stmt.expr.type)):
                            fail(f"binary operator {compound_op}: expected numeric operands, got {stmt.target.type} and {stmt.expr.type}", stmt)
                    else:
                        fail(f"unsupported assignment operator {stmt.op}", stmt)
                    require_type(stmt.expr.type, stmt.target.type, f"binary operator {compound_op}", stmt.expr)
            elif isinstance(stmt, Update):
                walk_expr(stmt.target)
                require_assignable(stmt.target)
                if isinstance(stmt.target, Identifier) and is_assignment_forbidden(stmt.target.name):
                    fail(f"cannot assign to narrowed nullable pointer '{stmt.target.name}' inside non-nil block", stmt.target)
                if isinstance(stmt.target, Identifier) and getattr(stmt.target, "is_capture", False):
                    fail(f"cannot assign to captured variable '{stmt.target.name}'", stmt.target)
                if is_rune_type(stmt.target.type):
                    fail(f"{stmt.op}: expected numeric lvalue, got rune", stmt)
                if not is_numeric_type(stmt.target.type) or is_pointer_type(stmt.target.type) or is_nullable_pointer_type(stmt.target.type):
                    fail(f"{stmt.op}: expected numeric lvalue, got {stmt.target.type}", stmt)
            elif isinstance(stmt, ForCondition):
                walk_expr(stmt.condition)
                require_type(stmt.condition.type, "bool", "for condition", stmt.condition)
                symtab.push_scope()
                break_depth += 1
                walk_stmts(stmt.body.statements)
                break_depth -= 1
                symtab.pop_scope()
            elif isinstance(stmt, FunctionDeclaration):
                if stmt.return_type:
                    require_public_qualified(stmt.return_type, stmt)
                    validate_map_type(stmt.return_type, stmt)
                if stmt.receiver_type:
                    require_public_qualified(stmt.receiver_type, stmt)
                    validate_map_type(stmt.receiver_type, stmt)
                for _pname, _ptype in stmt.params:
                    require_public_qualified(_ptype, stmt)
                    validate_map_type(_ptype, stmt)
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
                for _fname, _ftype in stmt.fields:
                    validate_map_type(_ftype, stmt)
            elif isinstance(stmt, IfaceDecl):
                iface_method_set(stmt.name)
            elif isinstance(stmt, EnumDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, ImportDecl):
                pass
            elif isinstance(stmt, ExternBlock):
                for fn in stmt.functions:
                    validate_extern_function(fn)
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
                    fail("break outside loop", stmt)
            elif isinstance(stmt, Block):
                symtab.push_scope()
                narrowed = getattr(stmt, "_narrowed_vars", None)
                if narrowed:
                    narrowed_read_stack.append(narrowed)
                    narrowed_assign_forbidden.append(set(narrowed.keys()))
                walk_stmts(stmt.statements)
                if narrowed:
                    narrowed_assign_forbidden.pop()
                    narrowed_read_stack.pop()
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
