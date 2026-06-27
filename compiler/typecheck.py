"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


import copy

from compiler.builtins import NUMERIC_TYPES, SCALAR_TYPES, STRINGIFIABLE_TYPES, infer_builtin_call
from compiler.type_ref import TypeRefBase, FunctionType, PointerType, format_type_ref, is_fallible_fn_type, parse_fn_type, parse_map_type, parse_slice_type, parse_type_ref
from compiler.type_rules import TypeRules


class TypeCheckError(Exception):
    pass


def infer_types(program: "Program", symtab: "SymbolTable", source: str | None = None):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Update, Block, ForCondition, FunctionDeclaration, Return, ErrReturn, ImportDecl,
        StructDecl, IfaceDecl, StructLiteral, FieldAccess, TryStatement,
        EnumDecl, EnumRef, ForIn,
        IfExpr, BlockExpr, MatchExpr, IntegerLiteral, FloatLiteral, StringLiteral, InterpolatedString, RuneLiteral, BoolLiteral, NilLiteral, MagicConst, BinaryOp, UnaryOp, FunctionCall, SizeOfType, Identifier,
        ExternBlock, FunctionExpr, GenericFunctionValue,
        ArrayLiteral, SliceLiteral, MapLiteral, IndexAccess, SliceExpr, MethodCall, Defer, SpawnStmt, Break, FallibleOp,
        ErrorHandlerExpr, ErrorMatchExpr
    )

    NEVER = "__never"
    current_return_type = "void"
    break_depth = 0
    closure_stack = []
    inferred_return_values = []
    inferred_void_return = False
    function_decls = {}
    method_decls = {}
    resolving_returns = []
    current_callable = None
    fallible_op_depth = 0
    defer_depth = 0
    OPERATOR_METHODS = {
        "+": "__add__",
        "-": "__sub__",
        "*": "__mul__",
        "/": "__div__",
        "%": "__mod__",
        "<": "__lt__",
        "<=": "__le__",
        ">": "__gt__",
        ">=": "__ge__",
    }
    ORDER_OPERATOR_METHODS = {"__lt__", "__le__", "__gt__", "__ge__"}
    DERIVED_ORDER_FROM_LT = {
        "<=": ("right", True),
        ">": ("right", False),
        ">=": ("left", True),
    }

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

    def require_error_type(actual, context, node=None):
        if actual not in {"error", "str"}:
            fail(f"{context}: expected error, got {actual}", node)

    def require_public_qualified(name, node=None):
        if getattr(node, "_default_arg_expr", False):
            return
        name_s = format_type_ref(name)
        if isinstance(name_s, str) and "." in name_s and name_s.rsplit(".", 1)[1].startswith("_"):
            owner_name = getattr(node, "name", None)
            if isinstance(node, (StructDecl, IfaceDecl, FunctionDeclaration)) and isinstance(owner_name, str) and "." in owner_name:
                if owner_name.rsplit(".", 1)[0] == name_s.rsplit(".", 1)[0].lstrip("*?[]"):
                    return
            callable_name = getattr(current_callable, "name", None)
            if isinstance(callable_name, str) and "." in callable_name:
                if callable_name.rsplit(".", 1)[0] == name_s.rsplit(".", 1)[0].lstrip("*?[]"):
                    return
            fail(f"symbol '{name_s}' is private", node)

    type_rules = TypeRules(symtab, fail, require_public_qualified)

    def embedded_structs(type_name: str):
        return getattr(symtab, "_struct_embeds", {}).get(type_name, {})

    def pointer_base_name(t):
        ref = parse_type_ref(t)
        if isinstance(ref, PointerType):
            return format_type_ref(ref.inner)
        return format_type_ref(ref)

    def promoted_field(type_name: str, field: str, seen=None):
        seen = seen or set()
        if type_name in seen:
            return None
        seen.add(type_name)
        matches = []
        for embed_name, embed_type in embedded_structs(type_name).items():
            embed_base = pointer_base_name(embed_type)
            try:
                fields = symtab.lookup_struct(embed_base)
            except NameError:
                continue
            if field in fields:
                matches.append(([embed_name], fields[field]))
            nested = promoted_field(embed_base, field, seen.copy())
            if nested is not None:
                path, ftype = nested
                matches.append(([embed_name] + path, ftype))
        if len(matches) > 1:
            fail(f"{type_name}: ambiguous promoted field {field}")
        return matches[0] if matches else None

    def build_promoted_access(obj, path: list[str]):
        current = obj
        current_type = obj.type
        for field in path:
            access = FieldAccess(current, field)
            base = pointer_base_name(current_type)
            ftype = symtab.lookup_struct(base)[field]
            access.type = ftype
            current = access
            current_type = ftype
        return current

    def promoted_method(type_name: str, method: str, seen=None):
        seen = seen or set()
        if type_name in seen:
            return None
        seen.add(type_name)
        matches = []
        methods = getattr(symtab, "_methods", {})
        for embed_name, embed_type in embedded_structs(type_name).items():
            embed_base = pointer_base_name(embed_type)
            if embed_base in methods and method in methods[embed_base]:
                matches.append(([embed_name], embed_base, methods[embed_base][method]))
            nested = promoted_method(embed_base, method, seen.copy())
            if nested is not None:
                path, receiver_base, sig = nested
                matches.append(([embed_name] + path, receiver_base, sig))
        if len(matches) > 1:
            fail(f"{type_name}: ambiguous promoted method {method}")
        return matches[0] if matches else None

    def resolve_method_call(node, obj_type, method_name):
        methods = getattr(symtab, "_methods", {})
        if obj_type in methods and method_name in methods[obj_type]:
            return [], obj_type, methods[obj_type][method_name]
        promoted = promoted_method(obj_type, method_name)
        if promoted is not None:
            return promoted
        return None

    def validate_operator_method(type_name: str, method_name: str, node):
        resolved = resolve_method_call(node, type_name, method_name)
        if resolved is None:
            return None
        path, receiver_base, (ret_type, params) = resolved
        if len(params) != 1:
            fail(f"operator method {receiver_base}.{method_name}: expected one parameter", node)
        _pname, ptype = params[0]
        require_type(ptype, type_name, f"operator method {receiver_base}.{method_name} parameter", node)
        expected_ret = "bool" if method_name in ORDER_OPERATOR_METHODS else type_name
        if ret_type is None:
            ret_type = resolve_method_return(receiver_base, method_name, node)
        require_type(ret_type, expected_ret, f"operator method {receiver_base}.{method_name} return", node)
        return path, receiver_base, ret_type

    def validate_unary_operator_method(type_name: str, method_name: str, node):
        resolved = resolve_method_call(node, type_name, method_name)
        if resolved is None:
            return None
        path, receiver_base, (ret_type, params) = resolved
        if len(params) != 0:
            fail(f"operator method {receiver_base}.{method_name}: expected no parameters", node)
        expected_ret = type_name
        if ret_type is None:
            ret_type = resolve_method_return(receiver_base, method_name, node)
        require_type(ret_type, expected_ret, f"operator method {receiver_base}.{method_name} return", node)
        return path, receiver_base, ret_type

    def validate_struct_embedding(stmt):
        fields = stmt.fields
        seen_fields = set()
        for fname, _ftype in fields:
            if fname in seen_fields:
                fail(f"struct {stmt.name}: duplicate field {fname}", stmt)
            seen_fields.add(fname)
        direct_fields = {fname for fname, _ftype in fields if fname not in getattr(stmt, "embedded_fields", set())}
        promoted_fields = {}
        promoted_methods = {}
        for embed_name, embed_type in getattr(symtab, "_struct_embeds", {}).get(stmt.name, {}).items():
            embed_base = embed_type[1:] if embed_type.startswith("*") else embed_type
            try:
                embed_fields = symtab.lookup_struct(embed_base)
            except NameError:
                fail(f"struct {stmt.name}: embedded struct {embed_type} not found", stmt)
            for fname in embed_fields:
                if fname in direct_fields:
                    fail(f"struct {stmt.name}: promoted field {fname} conflicts with direct field", stmt)
                if fname in promoted_fields:
                    fail(f"struct {stmt.name}: promoted field {fname} conflicts with embedded field {promoted_fields[fname]}", stmt)
                promoted_fields[fname] = embed_name
            for mname in getattr(symtab, "_methods", {}).get(embed_base, {}):
                if stmt.name in getattr(symtab, "_methods", {}) and mname in symtab._methods[stmt.name]:
                    fail(f"struct {stmt.name}: promoted method {mname} conflicts with direct method", stmt)
                if mname in promoted_methods:
                    fail(f"struct {stmt.name}: promoted method {mname} conflicts with embedded method {promoted_methods[mname]}", stmt)
                promoted_methods[mname] = embed_name

    def mark_current_fallible(node=None):
        if current_callable is None:
            fail("err is only allowed inside functions", node)
        if isinstance(current_callable, FunctionExpr):
            fail("function expressions cannot be fallible in v1", node)
        current_callable.fallible = True

    def walk_expr_outside_fallible_op(expr):
        nonlocal fallible_op_depth
        prev = fallible_op_depth
        try:
            fallible_op_depth = 0
            walk_expr(expr)
        finally:
            fallible_op_depth = prev

    def walk_fallible_call_for_try(call):
        nonlocal fallible_op_depth
        if not isinstance(call, (FunctionCall, MethodCall)):
            fail(f"try requires a fallible function or method call, got {type(call).__name__}", call)
        fallible_op_depth += 1
        walk_expr(call)
        fallible_op_depth -= 1
        if not getattr(call, "fallible", False):
            fail("try requires a fallible call", call)
        return call.type

    def walk_fallible_expr(expr, context):
        nonlocal fallible_op_depth
        fallible_op_depth += 1
        walk_expr(expr)
        fallible_op_depth -= 1
        if not getattr(expr, "fallible", False):
            fail(f"{context} requires a fallible call", expr)
        return expr.type

    def require_arg_count(args, expected, context, node=None):
        if len(args) != expected:
            fail(f"{context}: expected {expected} args, got {len(args)}", node)

    def require_concrete_param_type(param, context, node=None):
        if param.type is None:
            fail(f"{context}: parameter {param.name} requires a type or default value", node or param)
        if is_fallible_fn_type(param.type):
            fail("fallible function values are not supported in v1", node or param)
        return param.type

    def required_param_count(params):
        count = 0
        for param in params:
            if param.default is None:
                count += 1
        return count

    def require_default_param_shape(params, context, node=None):
        seen_default = False
        for param in params:
            if param.default is not None:
                seen_default = True
            elif seen_default:
                fail(f"{context}: required parameter {param.name} cannot follow default parameter", node)

    def is_allowed_default_call(node):
        return node.name in (NUMERIC_TYPES | {"str", "rune"})

    def validate_default_expr_shape(expr, param_name):
        if isinstance(expr, FunctionExpr):
            return
        if isinstance(expr, FunctionCall):
            if not is_allowed_default_call(expr):
                fail(f"default parameter {param_name}: function calls are not allowed", expr)
        elif isinstance(expr, MethodCall):
            fail(f"default parameter {param_name}: method calls are not allowed", expr)
        elif isinstance(expr, FallibleOp):
            fail(f"default parameter {param_name}: fallible operations are not allowed", expr)
        if isinstance(expr, TypeRefBase) or not hasattr(expr, "__dict__"):
            return
        for key, value in expr.__dict__.items():
            if key in {"source_file", "type", "fallible", "is_closure_call", "closure_param_types"}:
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, tuple):
                        for part in item:
                            validate_default_expr_value(part, param_name)
                    else:
                        validate_default_expr_value(item, param_name)
            elif isinstance(value, tuple):
                for item in value:
                    validate_default_expr_value(item, param_name)
            else:
                validate_default_expr_value(value, param_name)

    def validate_default_expr_value(value, param_name):
        if not isinstance(value, TypeRefBase) and hasattr(value, "__dict__"):
            validate_default_expr_shape(value, param_name)

    def infer_default_param_type(param):
        if param.type is not None:
            return param.type
        if param.default is None:
            fail(f"parameter {param.name} requires a type or default value", param)
        if param.default.type in (None, "void", "__nil"):
            fail(f"default parameter {param.name}: cannot infer type from {param.default.type}", param.default)
        param.type = param.default.type
        return param.type

    def clone_default_expr(expr, replacements):
        cloned = copy.deepcopy(expr)

        def walk(n, repl):
            if isinstance(n, Identifier) and n.name in repl:
                return copy.deepcopy(repl[n.name])
            if isinstance(n, TypeRefBase) or not hasattr(n, "__dict__"):
                return n
            if isinstance(n, FunctionExpr):
                shadowed = {p.name for p in n.params}
                repl = {k: v for k, v in repl.items() if k not in shadowed}
            for key, value in list(n.__dict__.items()):
                if key == "source_file":
                    continue
                setattr(n, key, rewrite_value(value, repl))
            return n

        def rewrite_value(value, repl):
            if isinstance(value, list):
                out = []
                for item in value:
                    if isinstance(item, tuple):
                        out.append(tuple(walk(part, repl) if not isinstance(part, TypeRefBase) and hasattr(part, "__dict__") else part for part in item))
                    elif not isinstance(item, TypeRefBase) and hasattr(item, "__dict__"):
                        out.append(walk(item, repl))
                    else:
                        out.append(item)
                return out
            if isinstance(value, tuple):
                return tuple(walk(item, repl) if not isinstance(item, TypeRefBase) and hasattr(item, "__dict__") else item for item in value)
            if not isinstance(value, TypeRefBase) and hasattr(value, "__dict__"):
                return walk(value, repl)
            return value

        return walk(cloned, replacements)

    def apply_default_args(args, params, context, node=None):
        required = required_param_count(params)
        total = len(params)
        if len(args) < required or len(args) > total:
            fail(f"{context}: expected {required} to {total} args, got {len(args)}", node)
        replacements = {param.name: arg for param, arg in zip(params, args)}
        for param in params[len(args):]:
            if param.default is None:
                fail(f"{context}: missing argument {param.name}", node)
            default_expr = clone_default_expr(param.default, replacements)
            validate_default_expr_shape(default_expr, param.name)
            mark_default_arg_expr(default_expr)
            walk_expr(default_expr)
            if param.type is None:
                if default_expr.type in (None, "void", "__nil"):
                    fail(f"default parameter {param.name}: cannot infer type from {default_expr.type}", default_expr)
                param.type = default_expr.type
            require_concrete_param_type(param, context, node)
            require_type(default_expr.type, param.type, f"default argument {param.name} to {context}", default_expr)
            args.append(default_expr)
            replacements[param.name] = default_expr

    def mark_default_arg_expr(expr):
        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if isinstance(value, tuple):
                for item in value:
                    walk(item)
                return
            if isinstance(value, TypeRefBase) or not hasattr(value, "__dict__") or value.__class__.__name__ == "SourceFile":
                return
            value._default_arg_expr = True
            for child in value.__dict__.values():
                walk(child)
        walk(expr)

    def fn_type(params, ret_type):
        return FunctionType(tuple(parse_type_ref(p) for p in params), parse_type_ref(ret_type))

    def ends_with_return(stmts):
        return bool(stmts) and isinstance(stmts[-1], (Return, ErrReturn))

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

    def is_never(t):
        return t == NEVER

    def merge_value_types(left, right, context, node):
        if is_never(left) and is_never(right):
            return NEVER
        if is_never(left):
            return right
        if is_never(right):
            return left
        require_type(right, left, context, node)
        return left

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration):
            if top_stmt.receiver_name:
                type_name = top_stmt.receiver_type.lstrip("*")
                if (type_name, top_stmt.name) in method_decls:
                    fail(f"{type_name}: duplicate method {top_stmt.name}", top_stmt)
                method_decls[(type_name, top_stmt.name)] = top_stmt
            else:
                function_decls[top_stmt.name] = top_stmt

    def validate_function_defaults(fn):
        require_default_param_shape(fn.params, f"function {fn.name}", fn)
        symtab.push_scope()
        if fn.receiver_name:
            symtab.declare(fn.receiver_name, fn.receiver_type)
        for param in fn.params:
            if param.default is not None and (not getattr(fn, "_generic_origin_kind", None) or param.type is None):
                validate_default_expr_shape(param.default, param.name)
                walk_expr(param.default)
                infer_default_param_type(param)
                require_type(param.default.type, param.type, f"default parameter {param.name}", param.default)
            else:
                require_concrete_param_type(param, f"function {fn.name}", fn)
            symtab.declare(param.name, param.type)
        symtab.pop_scope()

    def infer_block_value(block, context_node):
        symtab.push_scope()
        narrowed = getattr(block, "_narrowed_vars", None)
        if narrowed:
            narrowed_read_stack.append(narrowed)
            narrowed_assign_forbidden.append(set(narrowed.keys()))
        has_tail = block_tail_expr(block)
        if not has_tail and block.statements and isinstance(block.statements[-1], (Return, ErrReturn)):
            walk_stmts(block.statements)
            if narrowed:
                narrowed_assign_forbidden.pop()
                narrowed_read_stack.pop()
            symtab.pop_scope()
            return NEVER
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
        return merge_value_types(then_type, else_type, "if expression branches", stmt)

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
        is_error_match = scrut_type == "error"
        enum_variants = None
        if not is_error_match:
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
                if is_error_match:
                    if not isinstance(pattern, StringLiteral):
                        fail(f"match error pattern: expected str literal, got {pattern.type}", pattern)
                    require_type(pattern.type, "str", "match error pattern", pattern)
                else:
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
                result_type = merge_value_types(result_type, body.type, "match expression arms", body)

        if not seen_else:
            if is_error_match:
                fail("match expression: error match requires else", node)
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
        return type_rules.is_pointer_type(t)

    def is_nullable_pointer_type(t):
        return type_rules.is_nullable_pointer_type(t)

    def nonnullable_pointer_type(t):
        return type_rules.nonnullable_pointer_type(t)

    def is_nil_type(t):
        return type_rules.is_nil_type(t)

    def is_numeric_type(t):
        return type_rules.is_numeric_type(t)

    def validate_map_type(t, node=None):
        return type_rules.validate_map_type(t, node)

    def validate_sized_type(t, node=None, *, allow_void=False):
        return type_rules.validate_sized_type(t, node, allow_void=allow_void)

    def is_rune_type(t):
        return type_rules.is_rune_type(t)

    def is_iface_type(t):
        return type_rules.is_iface_type(t)

    def require_comparable(t, node=None):
        return type_rules.require_comparable(t, node)

    def validate_generic_constraints(stmt):
        return type_rules.validate_generic_constraints(stmt)

    def is_integer_type(t):
        return type_rules.is_integer_type(t)

    def is_extern_abi_type(t):
        return type_rules.is_extern_abi_type(t)

    def validate_extern_function(fn):
        if fn.type_params:
            fail("generic extern functions are not supported", fn)
        for param in fn.params:
            if param.default is not None:
                fail("extern functions cannot have default parameters", param)
            if param.type is None:
                fail(f"extern function {fn.name}: parameter {param.name} requires a type", param)
        if getattr(fn, "trusted_stdlib", False):
            return
        ret = fn.return_type or "void"
        if not is_extern_abi_type(ret):
            fail(f"extern function {fn.name}: unsupported ret type {ret}", fn)
        for pname, ptype in fn.params:
            if not is_extern_abi_type(ptype) or ptype == "void":
                fail(f"extern function {fn.name}: unsupported parameter {pname}: {ptype}", fn)

    for top_stmt in program.statements:
        if isinstance(top_stmt, (FunctionDeclaration, StructDecl)):
            validate_generic_constraints(top_stmt)

    def is_assignable_type(actual, expected):
        if actual == expected:
            return True
        if actual == "str" and expected == "error":
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
        for method in iface["methods"]:
            mname, params, ret = method[:3]
            if len(method) > 3 and method[3]:
                fail(f"iface {iface_name}: fallible methods are not supported in v1")
            add(mname, params, ret)
        iface["method_order"] = order
        iface["method_set"] = methods
        return methods

    def pointer_implements_iface(actual, iface_name):
        if not is_pointer_type(actual) or is_nullable_pointer_type(actual):
            return False
        type_name = actual[1:]
        for mname, (param_types, ret_type) in iface_method_set(iface_name).items():
            resolved = resolve_method_call(None, type_name, mname)
            if resolved is None:
                return False
            _path, receiver_base, (actual_ret, actual_params) = resolved
            if actual_ret is None:
                actual_ret = resolve_method_return(receiver_base, mname)
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

    def is_upper_const_name(name: str) -> bool:
        has_letter = False
        for ch in name:
            if "A" <= ch <= "Z":
                has_letter = True
                continue
            if "0" <= ch <= "9" or ch == "_":
                continue
            return False
        return has_letter

    def require_mutable_binding(target):
        if isinstance(target, Identifier):
            try:
                sym = symtab.lookup(target.name)
            except NameError:
                return
            if getattr(sym, "immutable", False):
                fail(f"cannot assign to const binding '{target.name}'", target)

    def walk_expr(node):
        nonlocal current_return_type, current_callable, fallible_op_depth, inferred_void_return
        if isinstance(node, Return):
            if node.expr:
                walk_expr(node.expr)
                if current_return_type is None:
                    inferred_return_values.append((node.expr.type, node))
                else:
                    require_type(node.expr.type, current_return_type, "ret", node)
            elif current_return_type != "void":
                if current_return_type is None:
                    inferred_void_return = True
                else:
                    fail(f"ret: expected {current_return_type}, got void", node)
            node.type = NEVER
        elif isinstance(node, ErrReturn):
            if defer_depth > 0:
                fail("defer cannot return errors", node)
            walk_expr(node.expr)
            require_error_type(node.expr.type, "err", node)
            mark_current_fallible(node)
            node.type = NEVER
        elif isinstance(node, IntegerLiteral):
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
        elif isinstance(node, MagicConst):
            if node.name in {"__FILE__", "__FUNC__", "__MODULE__"}:
                if node.name == "__FUNC__" and current_callable is None:
                    fail("__FUNC__ is only available inside functions", node)
                node.type = "str"
            elif node.name in {"__LINE__", "__COL__"}:
                node.type = "i32"
            else:
                fail(f"unknown magic constant {node.name}", node)
        elif isinstance(node, Identifier):
            sym = symtab.lookup(node.name)
            funcs = getattr(symtab, "_functions", {})
            if sym.scope_level == 0 and node.name in funcs:
                fn_node = function_decls.get(node.name)
                if fn_node is None:
                    fail(f"function value {node.name}: extern functions cannot be used as function values", node)
                if getattr(fn_node, "type_params", []):
                    fail(f"function value {node.name}: generic functions require explicit type arguments", node)
                ret_type, params = funcs[node.name]
                if ret_type is None:
                    ret_type = resolve_function_return(node.name, node)
                if bool(getattr(fn_node, "fallible", False)):
                    fail(f"function value {node.name}: fallible functions cannot be used as function values", node)
                node.type = fn_type([ptype for _pname, ptype in params], ret_type or "void")
                node.is_function_value = True
                node.fallible = False
                return
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
                if node.operand.type in getattr(symtab, "_structs", {}):
                    overload = validate_unary_operator_method(node.operand.type, "__neg__", node)
                    if overload is not None:
                        path, receiver_base, ret_type = overload
                        node.overload_method = "__neg__"
                        node.overload_receiver_path = path
                        node.overload_receiver_base = receiver_base
                        node.type = ret_type
                        return
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
                require_comparable(node.left.type, node)
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
                if node.left.type == "str" or node.right.type == "str":
                    require_type(node.right.type, node.left.type, "comparison", node)
                    node.type = "bool"
                    return
                if not (is_numeric_type(node.left.type) and is_numeric_type(node.right.type)):
                    if node.left.type in getattr(symtab, "_structs", {}) and node.right.type == node.left.type:
                        method_name = OPERATOR_METHODS[node.op]
                        overload = validate_operator_method(node.left.type, method_name, node)
                        if overload is not None:
                            path, receiver_base, _ret_type = overload
                            node.overload_method = method_name
                            node.overload_receiver_path = path
                            node.overload_receiver_base = receiver_base
                            node.type = "bool"
                            return
                        if node.op in DERIVED_ORDER_FROM_LT:
                            overload = validate_operator_method(node.left.type, "__lt__", node)
                            if overload is not None:
                                path, receiver_base, _ret_type = overload
                                receiver_side, negate = DERIVED_ORDER_FROM_LT[node.op]
                                node.overload_method = "__lt__"
                                node.overload_receiver_path = path
                                node.overload_receiver_base = receiver_base
                                node.overload_receiver_side = receiver_side
                                node.overload_negate = negate
                                node.type = "bool"
                                return
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
                    if node.left.type in getattr(symtab, "_structs", {}) and node.right.type == node.left.type:
                        method_name = OPERATOR_METHODS[node.op]
                        overload = validate_operator_method(node.left.type, method_name, node)
                        if overload is not None:
                            path, receiver_base, ret_type = overload
                            node.overload_method = method_name
                            node.overload_receiver_path = path
                            node.overload_receiver_base = receiver_base
                            node.type = ret_type
                            return
                    fail(f"binary operator {node.op}: expected numeric operands, got {node.left.type} and {node.right.type}", node)
            if node.op == "%":
                if not (is_integer_type(node.left.type) and is_integer_type(node.right.type)):
                    if node.left.type in getattr(symtab, "_structs", {}) and node.right.type == node.left.type:
                        method_name = OPERATOR_METHODS[node.op]
                        overload = validate_operator_method(node.left.type, method_name, node)
                        if overload is not None:
                            path, receiver_base, ret_type = overload
                            node.overload_method = method_name
                            node.overload_receiver_path = path
                            node.overload_receiver_base = receiver_base
                            node.type = ret_type
                            return
                    fail(f"binary operator %: expected integer operands, got {node.left.type} and {node.right.type}", node)
            if node.op in ("&", "|", "^", "<<", ">>"):
                if not (is_integer_type(node.left.type) and is_integer_type(node.right.type)):
                    fail(f"binary operator {node.op}: expected integer operands, got {node.left.type} and {node.right.type}", node)
            require_type(node.right.type, node.left.type, f"binary operator {node.op}", node)
            node.type = node.left.type
        elif isinstance(node, FunctionCall):
            require_public_qualified(node.name, node)
            for arg in node.args:
                walk_expr_outside_fallible_op(arg)
            if node.name == "__nc_bytes_alloc" and not getattr(getattr(node, "source_file", None), "trusted_stdlib", False):
                fail("__nc_bytes_alloc is only available to trusted stdlib", node)
            builtin_type = infer_builtin_call(node, require_arg_count, require_type, fail)
            if builtin_type is not None:
                node.type = builtin_type
                return
            funcs = getattr(symtab, "_functions", {})
            if node.name in funcs:
                ret_type, params = funcs[node.name]
                if ret_type is None:
                    ret_type = resolve_function_return(node.name, node)
                if getattr(node, "_erased_call", False) and params and getattr(params[0], "type", None) == "raw":
                    params = params[1:]
                apply_default_args(node.args, params, node.name, node)
                for arg, (pname, ptype) in zip(node.args, params):
                    if getattr(node, "_erased_call", False) and ptype == "raw":
                        continue  # raw is compatible with any type for erased calls
                    require_type(arg.type, ptype, f"argument {pname} to {node.name}", arg)
                node.type = ret_type
                # For erased calls, substitute type args to get concrete return type
                if getattr(node, "_erased_call", False):
                    type_args = getattr(node, "_erased_type_args", [])
                    if type_args and ret_type == "raw":
                        fn_node = function_decls.get(node.name)
                        if fn_node and hasattr(fn_node, "_erased_template"):
                            tmpl = fn_node._erased_template
                            if tmpl.type_params and tmpl.return_type in tmpl.type_params:
                                idx = tmpl.type_params.index(tmpl.return_type)
                                if idx < len(type_args):
                                    node.type = type_args[idx]
                node.is_closure_call = False
                fn_node = function_decls.get(node.name)
                node.fallible = bool(getattr(fn_node, "fallible", False))
                if node.fallible and fallible_op_depth <= 0:
                    fail(f"fallible call {node.name} must be handled with ??, !!, err?, match?, or try", node)
            else:
                try:
                    sym = symtab.lookup(node.name)
                except NameError:
                    fail(f"Function '{node.name}' not found", node)
                parsed = parse_fn_type(sym.nc_type)
                if parsed is None:
                    fail(f"Function '{node.name}' not found", node)
                if is_fallible_fn_type(sym.nc_type):
                    fail("fallible function values are not supported in v1", node)
                param_types, ret_type = parsed
                require_arg_count(node.args, len(param_types), node.name, node)
                for i, (arg, ptype) in enumerate(zip(node.args, param_types)):
                    require_type(arg.type, ptype, f"argument {i + 1} to {node.name}", arg)
                node.type = ret_type
                node.is_closure_call = True
                node.closure_param_types = param_types
                node.fallible = False
        elif isinstance(node, FallibleOp):
            if node.op == "??" and defer_depth > 0:
                fail("defer cannot propagate fallible calls with ??", node)
            fallible_op_depth += 1
            walk_expr(node.expr)
            fallible_op_depth -= 1
            if not getattr(node.expr, "fallible", False):
                fail(f"{node.op} requires a fallible call", node)
            if node.op == "??":
                mark_current_fallible(node)
                node.type = node.expr.type
            elif node.op == "!!":
                node.type = node.expr.type
            else:
                fail(f"unknown fallible operator {node.op}", node)
        elif isinstance(node, ErrorHandlerExpr):
            success_type = walk_fallible_expr(node.expr, "err?")
            node.success_type = success_type
            symtab.push_scope()
            symtab.declare(node.error_name, "error")
            handler_type = infer_block_value(node.handler_block, node)
            symtab.pop_scope()
            node.type = merge_value_types(success_type, handler_type, "err? handler", node.handler_block)
        elif isinstance(node, ErrorMatchExpr):
            success_type = walk_fallible_expr(node.expr, "match?")
            node.success_type = success_type
            if not node.arms:
                fail("match? expression: expected at least one arm", node)
            symtab.push_scope()
            symtab.declare(node.error_name, "error")
            result_type = success_type
            seen_else = False
            seen_patterns = set()
            for i, (pattern, body) in enumerate(node.arms):
                if seen_else:
                    fail("match? expression: else must be the last arm", pattern or body)
                if pattern is None:
                    seen_else = True
                    if i != len(node.arms) - 1:
                        fail("match? expression: else must be the last arm", body)
                else:
                    walk_expr(pattern)
                    if not isinstance(pattern, StringLiteral):
                        fail(f"match? pattern: expected str literal, got {pattern.type}", pattern)
                    require_type(pattern.type, "str", "match? pattern", pattern)
                    key = match_pattern_key(pattern)
                    if key in seen_patterns:
                        fail("match? expression: duplicate pattern", pattern)
                    seen_patterns.add(key)
                walk_expr(body)
                result_type = merge_value_types(result_type, body.type, "match? arms", body)
            symtab.pop_scope()
            if not seen_else:
                fail("match? expression requires else", node)
            node.type = result_type
        elif isinstance(node, SizeOfType):
            validate_sized_type(node.type_name, node)
            node.type = "u64"
        elif isinstance(node, FunctionExpr):
            if getattr(node, "fallible_explicit", False):
                fail("function expressions cannot be marked err in v1", node)
            require_default_param_shape(node.params, "function expression", node)
            for param in node.params:
                if param.default is not None:
                    fail("function expressions cannot have default parameters", param)
                require_concrete_param_type(param, "function expression", node)
            prev_return_type = current_return_type
            prev_callable = current_callable
            if not node.return_type_explicit:
                infer_function_expr_return(node)
            current_return_type = node.return_type or "void"
            current_callable = node
            symtab.push_scope()
            for pname, ptype in node.params:
                if ptype is None:
                    fail(f"function expression: parameter {pname} requires a type", node)
                validate_map_type(ptype, node)
                symtab.declare(pname, ptype)
            ctx = {"level": symtab._level, "captures": {}}
            closure_stack.append(ctx)
            walk_stmts(node.body.statements)
            closure_stack.pop()
            if current_return_type != "void" and not ends_with_return(node.body.statements):
                if node.body.statements and isinstance(node.body.statements[-1], ExpressionStatement):
                    if node.body.statements[-1].expr.type != NEVER:
                        require_type(node.body.statements[-1].expr.type, current_return_type, "function expression tail expression", node.body.statements[-1].expr)
                else:
                    fail(f"function expression: missing ret {current_return_type}", node)
            node.captures = list(ctx["captures"].items())
            node.type = fn_type([ptype for _pname, ptype in node.params], current_return_type)
            current_return_type = prev_return_type
            current_callable = prev_callable
            symtab.pop_scope()
        elif isinstance(node, GenericFunctionValue):
            require_public_qualified(node.name, node)
            funcs = getattr(symtab, "_functions", {})
            if node.name not in funcs:
                fail(f"generic function value {node.name}: function not found", node)
            ret_type, params = funcs[node.name]
            if ret_type is None:
                ret_type = resolve_function_return(node.name, node)
            fn_node = function_decls.get(node.name)
            if bool(getattr(fn_node, "fallible", False)):
                fail(f"generic function value {node.name}: fallible functions cannot be used as function values", node)
            node.type = fn_type([ptype for _pname, ptype in params], ret_type)
            node.fallible = False
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
            if obj_type == "str":
                if getattr(getattr(node, "source_file", None), "trusted_stdlib", False):
                    if node.field == "ptr":
                        node.type = "?*i8"
                        return
                    if node.field == "len":
                        node.type = "u64"
                        return
                fail(f"str: unknown field {node.field}", node)
            if obj_type.startswith("[]") and getattr(getattr(node, "source_file", None), "trusted_stdlib", False):
                elem_type = obj_type[2:]
                if node.field == "ptr":
                    node.type = f"?*{elem_type}"
                    return
                if node.field in {"len", "cap"}:
                    node.type = "u64"
                    return
                fail(f"{obj_type}: unknown field {node.field}", node)
            if obj_type.startswith("*"):
                obj_type = obj_type[1:]
            fields = symtab.lookup_struct(obj_type)
            if node.field not in fields:
                promoted = promoted_field(obj_type, node.field)
                if promoted is None:
                    fail(f"{obj_type}: unknown field {node.field}", node)
                path, ftype = promoted
                original_field = node.field
                node.obj = build_promoted_access(node.obj, path)
                node.field = original_field
                node.type = ftype
                return
            node.type = fields[node.field]
        elif isinstance(node, MethodCall):
            walk_expr_outside_fallible_op(node.obj)
            for arg in node.args:
                walk_expr_outside_fallible_op(arg)
            obj_type = node.obj.type
            if obj_type == "str" and node.method == "c_str":
                require_arg_count(node.args, 0, "method c_str", node)
                node.type = "*i8"
                return
            map_args = parse_map_type(obj_type)
            if map_args is not None:
                if node.method != "has":
                    fail(f"{obj_type}: method {node.method} not found", node)
                require_arg_count(node.args, 1, "method has", node)
                key_type, _value_type = map_args
                require_type(node.args[0].type, key_type, "argument 1 to method has", node.args[0])
                node.type = "i32"
                return
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
            resolved = resolve_method_call(node, obj_type, node.method)
            if resolved is not None:
                path, receiver_base, (ret_type, params) = resolved
                if path:
                    node.obj = build_promoted_access(node.obj, path)
                    node.promoted_receiver_base = receiver_base
                if ret_type is None:
                    ret_type = resolve_method_return(receiver_base, node.method, node)
                apply_default_args(node.args, params, f"method {node.method}", node)
                for arg, (pname, ptype) in zip(node.args, params):
                    require_type(arg.type, ptype, f"argument {pname} to method {node.method}", arg)
                node.type = ret_type
                fn_node = method_decls.get((receiver_base, node.method))
                node.fallible = bool(getattr(fn_node, "fallible", False))
                if node.fallible and fallible_op_depth <= 0:
                    fail(f"fallible call {receiver_base}.{node.method} must be handled with ??, !!, err?, match?, or try", node)
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
            if node.elem_type is None:
                if not node.elements:
                    fail("slice literal: cannot infer element type from empty literal", node)
                walk_expr(node.elements[0])
                if node.elements[0].type in (None, "void", "__nil"):
                    fail(f"slice literal: cannot infer element type from {node.elements[0].type}", node.elements[0])
                node.elem_type = node.elements[0].type
                rest = node.elements[1:]
            else:
                rest = node.elements
            for elem in rest:
                walk_expr(elem)
                require_type(elem.type, node.elem_type, "slice element", elem)
            node.type = f"[]{node.elem_type}"
        elif isinstance(node, MapLiteral):
            if node.map_type is None:
                if not node.entries:
                    fail("map literal: cannot infer key/value types from empty literal", node)
                first_key, first_value = node.entries[0]
                walk_expr(first_key)
                walk_expr(first_value)
                node.map_type = f"map[{first_key.type},{first_value.type}]"
                key_type, value_type = validate_map_type(node.map_type, node)
                rest = node.entries[1:]
            else:
                key_type, value_type = validate_map_type(node.map_type, node)
                rest = node.entries
            for key, value in rest:
                walk_expr(key)
                require_type(key.type, key_type, "map literal key", key)
                walk_expr(value)
                require_type(value.type, value_type, "map literal value", value)
            node.type = node.map_type
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
        nonlocal current_return_type, break_depth, inferred_void_return, current_callable, defer_depth
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                if stmt.annotation:
                    require_public_qualified(stmt.annotation, stmt)
                    if is_fallible_fn_type(stmt.annotation):
                        fail("fallible function values are not supported in v1", stmt)
                    validate_map_type(stmt.annotation, stmt)
                walk_expr(stmt.initializer)
                stmt.type = stmt.annotation or stmt.initializer.type
                if stmt.type == "void" or stmt.type == "__nil":
                    fail(f"let {stmt.name}: cannot bind void value", stmt)
                if stmt.type == NEVER:
                    fail(f"let {stmt.name}: cannot bind never value", stmt)
                require_type(stmt.initializer.type, stmt.type, f"let {stmt.name}", stmt)
                symtab.declare(stmt.name, stmt.type, immutable=is_upper_const_name(stmt.name))
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.target)
                require_assignable(stmt.target)
                require_mutable_binding(stmt.target)
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
                            if stmt.target.type in getattr(symtab, "_structs", {}) and stmt.expr.type == stmt.target.type:
                                method_name = OPERATOR_METHODS[compound_op]
                                overload = validate_operator_method(stmt.target.type, method_name, stmt)
                                if overload is not None:
                                    path, receiver_base, ret_type = overload
                                    stmt.overload_method = method_name
                                    stmt.overload_receiver_path = path
                                    stmt.overload_receiver_base = receiver_base
                                    require_type(ret_type, stmt.target.type, f"binary operator {compound_op}", stmt)
                                    continue
                            fail(f"binary operator %: expected integer operands, got {stmt.target.type} and {stmt.expr.type}", stmt)
                    elif compound_op == "+" and stmt.target.type == "str":
                        require_type(stmt.expr.type, "str", "string concatenation", stmt.expr)
                    elif compound_op in ("+", "-", "*", "/"):
                        if not (is_numeric_type(stmt.target.type) and is_numeric_type(stmt.expr.type)):
                            if stmt.target.type in getattr(symtab, "_structs", {}) and stmt.expr.type == stmt.target.type:
                                method_name = OPERATOR_METHODS[compound_op]
                                overload = validate_operator_method(stmt.target.type, method_name, stmt)
                                if overload is not None:
                                    path, receiver_base, ret_type = overload
                                    stmt.overload_method = method_name
                                    stmt.overload_receiver_path = path
                                    stmt.overload_receiver_base = receiver_base
                                    require_type(ret_type, stmt.target.type, f"binary operator {compound_op}", stmt)
                                    continue
                            fail(f"binary operator {compound_op}: expected numeric operands, got {stmt.target.type} and {stmt.expr.type}", stmt)
                    else:
                        fail(f"unsupported assignment operator {stmt.op}", stmt)
                    require_type(stmt.expr.type, stmt.target.type, f"binary operator {compound_op}", stmt.expr)
            elif isinstance(stmt, Update):
                walk_expr(stmt.target)
                require_assignable(stmt.target)
                require_mutable_binding(stmt.target)
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
                require_default_param_shape(stmt.params, f"function {stmt.name}", stmt)
                if stmt.return_type:
                    require_public_qualified(stmt.return_type, stmt)
                    if is_fallible_fn_type(stmt.return_type):
                        fail("fallible function values are not supported in v1", stmt)
                    validate_map_type(stmt.return_type, stmt)
                if stmt.receiver_type:
                    require_public_qualified(stmt.receiver_type, stmt)
                    validate_map_type(stmt.receiver_type, stmt)
                for _pname, _ptype in stmt.params:
                    if _ptype is None:
                        continue
                    require_public_qualified(_ptype, stmt)
                    validate_map_type(_ptype, stmt)
                symtab.push_scope()
                prev_return_type = current_return_type
                prev_callable = current_callable
                if not stmt.return_type_explicit:
                    if stmt.receiver_name:
                        resolve_method_return(stmt.receiver_type.lstrip("*"), stmt.name, stmt)
                    else:
                        resolve_function_return(stmt.name, stmt)
                current_return_type = stmt.return_type or "void"
                current_callable = stmt
                if stmt.receiver_name:
                    symtab.declare(stmt.receiver_name, stmt.receiver_type)
                for param in stmt.params:
                    if param.default is not None and (not getattr(stmt, "_generic_origin_kind", None) or param.type is None):
                        validate_default_expr_shape(param.default, param.name)
                        walk_expr(param.default)
                        infer_default_param_type(param)
                        require_type(param.default.type, param.type, f"default parameter {param.name}", param.default)
                    elif param.default is None:
                        require_concrete_param_type(param, f"function {stmt.name}", stmt)
                    symtab.declare(param.name, param.type)
                walk_stmts(stmt.body.statements)
                if current_return_type != "void" and not ends_with_return(stmt.body.statements):
                    if stmt.body.statements and isinstance(stmt.body.statements[-1], ExpressionStatement):
                        if stmt.body.statements[-1].expr.type != NEVER:
                            require_type(stmt.body.statements[-1].expr.type, current_return_type, f"function {stmt.name} tail expression", stmt.body.statements[-1].expr)
                    else:
                        fail(f"function {stmt.name}: missing ret {current_return_type}", stmt)
                current_return_type = prev_return_type
                current_callable = prev_callable
                symtab.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
                    if current_return_type is None:
                        inferred_return_values.append((stmt.expr.type, stmt))
                    else:
                        require_type(stmt.expr.type, current_return_type, "ret", stmt)
                elif current_return_type != "void":
                    if current_return_type is None:
                        inferred_void_return = True
                    else:
                        fail(f"ret: expected {current_return_type}, got void", stmt)
                stmt.type = NEVER
            elif isinstance(stmt, ErrReturn):
                if defer_depth > 0:
                    fail("defer cannot return errors", stmt)
                walk_expr(stmt.expr)
                require_error_type(stmt.expr.type, "err", stmt)
                mark_current_fallible(stmt)
                stmt.type = NEVER
            elif isinstance(stmt, TryStatement):
                success_type = walk_fallible_call_for_try(stmt.call)
                if success_type == "void":
                    if stmt.success_name is not None:
                        fail("try: void fallible call cannot bind a success value", stmt)
                elif stmt.success_name is None:
                    fail(f"try: fallible call returning {success_type} requires a success binding", stmt)
                symtab.push_scope()
                if stmt.success_name is not None:
                    symtab.declare(stmt.success_name, success_type)
                walk_stmts(stmt.success_block.statements)
                symtab.pop_scope()
                if stmt.error_block is not None:
                    symtab.push_scope()
                    symtab.declare(stmt.error_name, "error")
                    walk_stmts(stmt.error_block.statements)
                    symtab.pop_scope()
            elif isinstance(stmt, StructDecl):
                validate_struct_embedding(stmt)
                for _fname, _ftype in stmt.fields:
                    require_public_qualified(_ftype, stmt)
                    validate_map_type(_ftype, stmt)
                for embed_name in getattr(stmt, "embedded_fields", set()):
                    embed_type = dict(stmt.fields)[embed_name]
                    if embed_type not in getattr(symtab, "_structs", {}):
                        fail(f"struct {stmt.name}: embedded struct {embed_type} not found", stmt)
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
                    if parse_slice_type(stmt.iterable.type) is None and parse_map_type(stmt.iterable.type) is None:
                        fail(f"for-in: expected slice or map, got {stmt.iterable.type}", stmt.iterable)
                symtab.push_scope()
                if stmt.start is not None:
                    symtab.declare(stmt.index, "i32")
                else:
                    slice_elem_type = parse_slice_type(stmt.iterable.type)
                    map_parts = parse_map_type(stmt.iterable.type)
                    if map_parts is not None:
                        if stmt.value is None:
                            fail("for-in: map requires key, value variables", stmt)
                        symtab.declare(stmt.index, map_parts[0])
                        symtab.declare(stmt.value, map_parts[1])
                    else:
                        symtab.declare(stmt.index, "i32")
                        if stmt.value:
                            symtab.declare(stmt.value, slice_elem_type)
                break_depth += 1
                walk_stmts(stmt.body.statements)
                break_depth -= 1
                symtab.pop_scope()
            elif isinstance(stmt, Defer):
                defer_depth += 1
                walk_stmts(stmt.body.statements)
                defer_depth -= 1
            elif isinstance(stmt, SpawnStmt):
                func = stmt.func_expr
                if not isinstance(func, FunctionExpr):
                    fail("spawn must be followed by a function expression", stmt)
                # typecheck the closure
                walk_expr(func)
                # verify zero params, void return
                if func.params:
                    fail("spawn function must take no parameters", stmt)
                ft = getattr(func, 'type', None)
                if ft and isinstance(ft, str) and not ft.startswith("fun()"):
                    fail(f"spawn function must return void, got {ft}", stmt)
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
        nonlocal current_return_type, inferred_return_values, inferred_void_return, current_callable
        prev_return_type = current_return_type
        prev_values = inferred_return_values
        prev_void = inferred_void_return
        prev_callable = current_callable
        current_return_type = None
        inferred_return_values = []
        inferred_void_return = False
        current_callable = fn_node

        symtab.push_scope()
        if isinstance(fn_node, FunctionDeclaration) and fn_node.receiver_name:
            symtab.declare(fn_node.receiver_name, fn_node.receiver_type)
        for param in fn_node.params:
            if getattr(param, "default", None) is not None and (not getattr(fn_node, "_generic_origin_kind", None) or param.type is None):
                validate_default_expr_shape(param.default, param.name)
                walk_expr(param.default)
                infer_default_param_type(param)
                require_type(param.default.type, param.type, f"default parameter {param.name}", param.default)
            elif getattr(param, "default", None) is None:
                require_concrete_param_type(param, display_name, fn_node)
            symtab.declare(param.name, param.type)
        walk_stmts(fn_node.body.statements)

        tail = block_tail_expr(fn_node.body)
        if tail is not None:
            ret_type = tail_expr_type(tail)
            if ret_type is not None and ret_type != NEVER:
                inferred_return_values.append((ret_type, tail))

        values = [(t, n) for t, n in inferred_return_values if t != NEVER]
        saw_void = inferred_void_return
        symtab.pop_scope()

        current_return_type = prev_return_type
        inferred_return_values = prev_values
        inferred_void_return = prev_void
        current_callable = prev_callable

        if values and saw_void:
            fail(f"{display_name}: cannot mix value ret and void ret", values[0][1])
        if not values:
            return "void"
        first_type = values[0][0]
        for ret_type, ret_node in values[1:]:
            require_type(ret_type, first_type, f"{display_name} ret type", ret_node)
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
            fail(f"function {name}: ret type inference cycle; add explicit ret type", node or fn_node)
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
            fail(f"function {method_name}: ret type inference cycle; add explicit ret type", node or fn_node)
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
            validate_function_defaults(top_stmt)

    def mark_direct_fallible(node):
        if isinstance(node, ErrReturn):
            return True
        if isinstance(node, FallibleOp):
            return node.op == "??" or mark_direct_fallible(node.expr)
        if isinstance(node, ErrorHandlerExpr):
            return mark_direct_fallible(node.handler_block)
        if isinstance(node, ErrorMatchExpr):
            return any(mark_direct_fallible(body) for _pattern, body in node.arms)
        if isinstance(node, FunctionExpr):
            return False
        if isinstance(node, Block):
            return any(mark_direct_fallible(stmt) for stmt in node.statements)
        if isinstance(node, FunctionDeclaration):
            return mark_direct_fallible(node.body)
        if isinstance(node, (ForCondition, ForIn, Defer)):
            return mark_direct_fallible(node.body)
        if isinstance(node, ExpressionStatement):
            return mark_direct_fallible(node.expr)
        if isinstance(node, VariableDeclaration):
            return mark_direct_fallible(node.initializer)
        if isinstance(node, Assignment):
            return mark_direct_fallible(node.target) or mark_direct_fallible(node.expr)
        if isinstance(node, Update):
            return mark_direct_fallible(node.target)
        if isinstance(node, Return):
            return bool(node.expr and mark_direct_fallible(node.expr))
        if isinstance(node, TryStatement):
            return mark_direct_fallible(node.success_block) or bool(node.error_block and mark_direct_fallible(node.error_block))
        if isinstance(node, IfExpr):
            return (mark_direct_fallible(node.condition)
                    or mark_direct_fallible(node.then_block)
                    or bool(node.else_block and mark_direct_fallible(node.else_block)))
        if isinstance(node, BlockExpr):
            return mark_direct_fallible(node.block)
        if isinstance(node, MatchExpr):
            return (mark_direct_fallible(node.scrutinee)
                    or any((p is not None and mark_direct_fallible(p)) or mark_direct_fallible(b) for p, b in node.arms))
        if isinstance(node, BinaryOp):
            return mark_direct_fallible(node.left) or mark_direct_fallible(node.right)
        if isinstance(node, UnaryOp):
            return mark_direct_fallible(node.operand)
        if isinstance(node, FunctionCall):
            return any(mark_direct_fallible(arg) for arg in node.args)
        if isinstance(node, GenericFunctionValue):
            return False
        if isinstance(node, MethodCall):
            return mark_direct_fallible(node.obj) or any(mark_direct_fallible(arg) for arg in node.args)
        if isinstance(node, (ArrayLiteral, SliceLiteral)):
            return any(mark_direct_fallible(elem) for elem in node.elements)
        if isinstance(node, MapLiteral):
            return any(mark_direct_fallible(k) or mark_direct_fallible(v) for k, v in node.entries)
        if isinstance(node, IndexAccess):
            return mark_direct_fallible(node.obj) or mark_direct_fallible(node.index)
        if isinstance(node, SliceExpr):
            return (mark_direct_fallible(node.array)
                    or bool(node.start and mark_direct_fallible(node.start))
                    or bool(node.end and mark_direct_fallible(node.end)))
        if isinstance(node, FieldAccess):
            return mark_direct_fallible(node.obj)
        if isinstance(node, StructLiteral):
            return any(mark_direct_fallible(v) for _n, v in node.fields)
        return False

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration) and mark_direct_fallible(top_stmt):
            top_stmt.fallible = True

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration) and getattr(top_stmt, "fallible_explicit", False):
            if getattr(top_stmt, "is_extern", False):
                fail("extern functions cannot be marked err", top_stmt)
            if not getattr(top_stmt, "fallible", False):
                fail(f"function {top_stmt.name}: err marker requires a fallible body", top_stmt)

    for top_stmt in program.statements:
        if isinstance(top_stmt, FunctionDeclaration):
            if top_stmt.receiver_name:
                resolve_method_return(top_stmt.receiver_type.lstrip("*"), top_stmt.name, top_stmt)
            else:
                resolve_function_return(top_stmt.name, top_stmt)

    walk_stmts(program.statements)
