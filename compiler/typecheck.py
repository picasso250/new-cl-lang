"""
类型推断 —— Pass 2：用符号表标注 AST 各节点的类型。
符号表已含嵌套作用域信息，遍历时同步进出作用域。
"""


class TypeCheckError(Exception):
    pass


def infer_types(program: "Program", symtab: "SymbolTable", source: str | None = None):
    """Pass 2: 标注 Program 中所有表达式和语句的类型。"""
    from compiler.ast import (
        Program, VariableDeclaration, ExpressionStatement,
        Assignment, Block, If, While, FunctionDeclaration, Return,
        StructDecl, StructLiteral, FieldAccess,
        EnumDecl, EnumRef, Switch, ForIn,
        IntegerLiteral, StringLiteral, BoolLiteral, BinaryOp, UnaryOp, FunctionCall, Identifier,
        ArrayLiteral, SliceLiteral, IndexAccess, SliceExpr, MethodCall, TryCatch, Throw, Defer, Break
    )

    current_return_type = "void"

    def line_col(pos: int) -> tuple[int, int]:
        if source is None:
            return 0, 0
        line = source.count("\n", 0, pos) + 1
        last_nl = source.rfind("\n", 0, pos)
        col = pos + 1 if last_nl < 0 else pos - last_nl
        return line, col

    def fail(message, node=None):
        span = getattr(node, "span", None)
        if span and source is not None:
            line, col = line_col(span[0])
            raise TypeCheckError(f"{line}:{col}: {message}")
        raise TypeCheckError(message)

    def require_type(actual, expected, context, node=None):
        if actual != expected:
            fail(f"{context}: expected {expected}, got {actual}", node)

    def require_arg_count(args, expected, context, node=None):
        if len(args) != expected:
            fail(f"{context}: expected {expected} args, got {len(args)}", node)

    def ends_with_return(stmts):
        return bool(stmts) and isinstance(stmts[-1], Return)

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
            # 内置函数
            if node.name == "print":
                require_arg_count(node.args, 1, "print", node)
                node.type = "void"
                return
            if node.name == "read_file":
                require_arg_count(node.args, 1, "read_file", node)
                require_type(node.args[0].type, "str", "read_file path", node)
                node.type = "str"
                return
            if node.name == "write_file":
                require_arg_count(node.args, 2, "write_file", node)
                require_type(node.args[0].type, "str", "write_file path", node)
                require_type(node.args[1].type, "str", "write_file content", node)
                node.type = "void"
                return
            if node.name == "append":
                require_arg_count(node.args, 2, "append", node)
                if not node.args[0].type.startswith("[]"):
                    fail(f"append: expected slice, got {node.args[0].type}", node)
                require_type(node.args[1].type, node.args[0].type[2:], "append element", node)
                node.type = node.args[0].type if node.args else "i32"
                return
            if node.name == "map_new":
                node.type = "nc_map"
                return
            if node.name == "map_set_s":
                node.type = "void"
                return
            if node.name == "map_get_s":
                node.type = "str"
                return
            if node.name == "map_has":
                node.type = "i32"
                return
            if node.name == "str":
                require_arg_count(node.args, 1, "str", node)
                node.type = "str"
                return
            if node.name == "i32":
                require_arg_count(node.args, 1, "i32", node)
                node.type = "i32"
                return
            if node.name == "gc_collect":
                node.type = "void"
                return
            if node.name == "gc_live":
                node.type = "i32"
                return
            if node.name == "len":
                require_arg_count(node.args, 1, "len", node)
                if not (node.args[0].type == "str" or node.args[0].type == "nc_map" or node.args[0].type.startswith("[]")):
                    fail(f"len: expected str, map, or slice, got {node.args[0].type}", node)
                node.type = "i32"
                return
            funcs = getattr(symtab, "_functions", {})
            if node.name not in funcs:
                fail(f"Function '{node.name}' not found", node)
            ret_type, params = funcs[node.name]
            require_arg_count(node.args, len(params), node.name, node)
            for arg, (pname, ptype) in zip(node.args, params):
                require_type(arg.type, ptype, f"argument {pname} to {node.name}", arg)
            node.type = ret_type
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
                require_arg_count(node.args, len(params), f"method {node.method}", node)
                for arg, (pname, ptype) in zip(node.args, params):
                    require_type(arg.type, ptype, f"argument {pname} to method {node.method}", arg)
                node.type = ret_type or "void"
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
        nonlocal current_return_type
        for stmt in stmts:
            if isinstance(stmt, VariableDeclaration):
                walk_expr(stmt.initializer)
                stmt.type = stmt.annotation or stmt.initializer.type
                require_type(stmt.initializer.type, stmt.type, f"let {stmt.name}", stmt)
                symtab.declare(stmt.name, stmt.type, stmt.mut)
            elif isinstance(stmt, ExpressionStatement):
                walk_expr(stmt.expr)
            elif isinstance(stmt, Assignment):
                walk_expr(stmt.target)
                walk_expr(stmt.expr)
                if isinstance(stmt.target, Identifier):
                    sym = symtab.lookup(stmt.target.name)
                    if not sym.is_mut:
                        fail(f"cannot assign to immutable variable {stmt.target.name}", stmt.target)
                require_type(stmt.expr.type, stmt.target.type, "assignment", stmt.expr)
            elif isinstance(stmt, If):
                walk_expr(stmt.condition)
                require_type(stmt.condition.type, "bool", "if condition", stmt.condition)
                symtab.push_scope()
                walk_stmts(stmt.then_block.statements)
                symtab.pop_scope()
                if stmt.else_block:
                    symtab.push_scope()
                    walk_stmts(stmt.else_block.statements)
                    symtab.pop_scope()
            elif isinstance(stmt, While):
                walk_expr(stmt.condition)
                require_type(stmt.condition.type, "bool", "while condition", stmt.condition)
                symtab.push_scope()
                walk_stmts(stmt.body.statements)
                symtab.pop_scope()
            elif isinstance(stmt, FunctionDeclaration):
                symtab.push_scope()
                prev_return_type = current_return_type
                current_return_type = stmt.return_type or "void"
                if stmt.receiver_name:
                    symtab.declare(stmt.receiver_name, stmt.receiver_type)
                for pname, _ptype in stmt.params:
                    symtab.declare(pname, _ptype)
                walk_stmts(stmt.body.statements)
                if current_return_type != "void" and not ends_with_return(stmt.body.statements):
                    fail(f"function {stmt.name}: missing return {current_return_type}", stmt)
                current_return_type = prev_return_type
                symtab.pop_scope()
            elif isinstance(stmt, Return):
                if stmt.expr:
                    walk_expr(stmt.expr)
                    require_type(stmt.expr.type, current_return_type, "return", stmt)
                elif current_return_type != "void":
                    fail(f"return: expected {current_return_type}, got void", stmt)
            elif isinstance(stmt, StructDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, EnumDecl):
                pass  # 已在 Pass 1 注册
            elif isinstance(stmt, Switch):
                walk_expr(stmt.scrutinee)
                for case_val, case_stmt in stmt.cases:
                    walk_expr(case_val)
                    require_type(case_val.type, stmt.scrutinee.type, "switch case", case_val)
                    walk_stmts([case_stmt])
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
                walk_stmts(stmt.body.statements)
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
                pass
            elif isinstance(stmt, Block):
                symtab.push_scope()
                walk_stmts(stmt.statements)
                symtab.pop_scope()

    walk_stmts(program.statements)
