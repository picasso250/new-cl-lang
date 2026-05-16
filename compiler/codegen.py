"""代码生成 —— AST → C 源码。"""

from compiler.ast import *


def generate_c(program: Program) -> str:
    lines = []
    lines.append('#include <stdio.h>')
    lines.append('#include <stdlib.h>')
    lines.append('')
    lines.append('int main(void) {')

    # 收集所有 let 声明的变量名/类型（用于代码生成时的符号表）
    vartypes = {}  # name → c_type
    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration):
            # 目前所有变量推断为 int
            vartypes[stmt.name] = "int"
            init_c = _generate_expr(stmt.initializer)
            lines.append(f'    int {stmt.name} = {init_c};')
            if stmt.mut:
                pass  # C 中所有变量默认可变，无需特殊处理

    # 生成语句体（跳过声明，已在上方处理）
    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration):
            continue  # 已处理
        elif isinstance(stmt, ExpressionStatement):
            _gen_expr_stmt(lines, stmt.expr)
        elif isinstance(stmt, Assignment):
            lines.append(f'    {stmt.name} = {_generate_expr(stmt.expr)};')

    lines.append('    return 0;')
    lines.append('}')
    return '\n'.join(lines)


def _gen_expr_stmt(lines: list, expr):
    """生成表达式语句的 C 代码。"""
    if isinstance(expr, FunctionCall) and expr.name == "print":
        arg = expr.args[0]
        # 判断参数类型：整数用 %d，字符串用 %s
        arg_c = _generate_expr(arg)
        lines.append(f'    printf("%d\\n", {arg_c});')
    else:
        lines.append(f'    {_generate_expr(expr)};')


def _generate_expr(node: Node) -> str:
    if isinstance(node, IntegerLiteral):
        return str(node.value)

    if isinstance(node, Identifier):
        return node.name

    if isinstance(node, BinaryOp):
        left = _generate_expr(node.left)
        right = _generate_expr(node.right)
        return f'({left} {node.op} {right})'

    if isinstance(node, FunctionCall):
        args = ', '.join(_generate_expr(a) for a in node.args)
        return f'{node.name}({args})'

    raise NotImplementedError(f"Codegen not implemented for {type(node).__name__}")
