"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
"""

NC_TO_C = {
    "i32": "int", "i64": "long long",
    "u32": "unsigned int", "u64": "unsigned long long",
    "f32": "float", "f64": "double",
    "bool": "int", "void": "void",
}


def generate_c(program: "Program") -> str:
    lines = [
        '#include <stdio.h>',
        '#include <stdlib.h>',
        '',
        'int main(void) {',
    ]
    for stmt in program.statements:
        _gen_stmt(lines, stmt, indent=1)
    lines.append('    return 0;')
    lines.append('}')
    return '\n'.join(lines)


def _gen_stmt(lines: list, stmt, indent: int):
    from compiler.ast import (
        VariableDeclaration, ExpressionStatement, Assignment,
        Block, If,
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
        fmt = "%d" if getattr(arg, "type", "i32") in ("i32", "i64", "u32", "u64", "bool") else "%s"
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
