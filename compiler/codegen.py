"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
`fun main()` 映射为 C 的 `int main(void)`，其他函数正常生成。
无 `fun main()` 时退化为隐式 main 包裹顶层语句。
"""

NC_TO_C = {
    "i32": "int", "i64": "long long",
    "u32": "unsigned int", "u64": "unsigned long long",
    "f32": "float", "f64": "double",
    "bool": "int", "void": "void",
}


def generate_c(program: "Program") -> str:
    from compiler.ast import FunctionDeclaration

    lines = [
        '#include <stdio.h>',
        '#include <stdlib.h>',
        '',
    ]

    # 分离 main 函数、其他函数、顶层语句
    main_func = None
    other_funcs = []
    top_stmts = []

    for stmt in program.statements:
        if isinstance(stmt, FunctionDeclaration):
            if stmt.name == "main":
                main_func = stmt
            else:
                other_funcs.append(stmt)
        else:
            top_stmts.append(stmt)

    # 先输出其他函数
    for func in other_funcs:
        _gen_function(lines, func)

    # 生成 main
    if main_func:
        # 使用 NC 的 fun main() 作为入口
        lines.append('int main(void) {')
        for stmt in main_func.body.statements:
            _gen_stmt(lines, stmt, indent=1)
        lines.append('    return 0;')
        lines.append('}')

        # main 之外的顶层语句？放 main 之前（不太寻常但合法）
        for stmt in top_stmts:
            lines.append(f'# warning: top-level statement outside main')
    elif top_stmts:
        # 无 main，隐式包裹顶层语句
        lines.append('int main(void) {')
        for stmt in top_stmts:
            _gen_stmt(lines, stmt, indent=1)
        lines.append('    return 0;')
        lines.append('}')
    else:
        # 无入口点
        lines.append('int main(void) { return 0; }')

    return '\n'.join(lines)


def _gen_function(lines: list, func):
    from compiler.ast import FunctionDeclaration
    c_ret = NC_TO_C.get(func.return_type, "void")
    params_c = ', '.join(f'{NC_TO_C.get(t, "int")} {n}' for n, t in func.params)
    if not params_c:
        params_c = "void"
    lines.append(f'{c_ret} {func.name}({params_c}) {{')
    for stmt in func.body.statements:
        _gen_stmt(lines, stmt, indent=1)
    lines.append('}')


def _gen_stmt(lines: list, stmt, indent: int):
    from compiler.ast import (
        VariableDeclaration, ExpressionStatement, Assignment,
        Block, If, While, Return,
    )
    pad = '    ' * indent

    if isinstance(stmt, VariableDeclaration):
        c_type = NC_TO_C.get(stmt.type, "int")
        init_c = _gen_expr(stmt.initializer)
        lines.append(f'{pad}{c_type} {stmt.name} = {init_c};')

    elif isinstance(stmt, Assignment):
        lines.append(f'{pad}{stmt.name} = {_gen_expr(stmt.expr)};')

    elif isinstance(stmt, ExpressionStatement):
        _gen_expr_stmt(lines, stmt.expr, indent)

    elif isinstance(stmt, If):
        cond_c = _gen_expr(stmt.condition)
        lines.append(f'{pad}if ({cond_c}) {{')
        for s in stmt.then_block.statements:
            _gen_stmt(lines, s, indent + 1)
        if stmt.else_block:
            lines.append(f'{pad}}} else {{')
            for s in stmt.else_block.statements:
                _gen_stmt(lines, s, indent + 1)
        lines.append(f'{pad}}}')

    elif isinstance(stmt, While):
        cond_c = _gen_expr(stmt.condition)
        lines.append(f'{pad}while ({cond_c}) {{')
        for s in stmt.body.statements:
            _gen_stmt(lines, s, indent + 1)
        lines.append(f'{pad}}}')

    elif isinstance(stmt, Return):
        if stmt.expr:
            lines.append(f'{pad}return {_gen_expr(stmt.expr)};')
        else:
            lines.append(f'{pad}return;')

    elif isinstance(stmt, Block):
        for s in stmt.statements:
            _gen_stmt(lines, s, indent)

    else:
        raise NotImplementedError(f"codegen for {type(stmt).__name__}")


def _gen_expr_stmt(lines: list, expr, indent: int):
    from compiler.ast import FunctionCall
    pad = '    ' * indent

    if isinstance(expr, FunctionCall) and expr.name == "print":
        arg = expr.args[0]
        arg_type = getattr(arg, "type", "i32")
        fmt = "%s" if arg_type == "str" else "%d"
        lines.append(f'{pad}printf("{fmt}\\n", {_gen_expr(arg)});')
    else:
        lines.append(f'{pad}{_gen_expr(expr)};')


def _gen_expr(node) -> str:
    from compiler.ast import IntegerLiteral, Identifier, BinaryOp, FunctionCall

    if isinstance(node, IntegerLiteral):
        return str(node.value)

    if isinstance(node, Identifier):
        return node.name

    if isinstance(node, BinaryOp):
        left = _gen_expr(node.left)
        right = _gen_expr(node.right)
        return f'({left} {node.op} {right})'

    if isinstance(node, FunctionCall):
        args = ', '.join(_gen_expr(a) for a in node.args)
        return f'{node.name}({args})'

    raise NotImplementedError(f"codegen expr for {type(node).__name__}")
