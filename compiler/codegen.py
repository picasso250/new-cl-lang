"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct 定义提升到文件作用域，fun main() 映射为 int main(void)。
"""

NC_TO_C = {
    "i32": "int", "i64": "long long",
    "u32": "unsigned int", "u64": "unsigned long long",
    "f32": "float", "f64": "double",
    "bool": "int", "void": "void",
    "str": "const char*",
}


def _type_to_c(nc_type: str) -> str:
    """将 NC 类型映射为 C 类型。struct 名 → typedef 名。"""
    return NC_TO_C.get(nc_type, nc_type)


def generate_c(program: "Program") -> str:
    from compiler.ast import FunctionDeclaration, StructDecl, Block, If, While

    lines = [
        '#include <stdio.h>',
        '#include <stdlib.h>',
        '',
    ]

    # 收集 struct 定义（提升到文件作用域）
    structs = []
    other_funcs = []
    main_func = None
    top_stmts = []

    def collect(stmts):
        nonlocal main_func
        for s in stmts:
            if isinstance(s, StructDecl):
                structs.append(s)
            elif isinstance(s, FunctionDeclaration):
                if s.name == "main":
                    main_func = s
                else:
                    other_funcs.append(s)
                collect(s.body.statements)  # 钻入函数体找 struct
            elif isinstance(s, Block):
                collect(s.statements)
            elif isinstance(s, If):
                collect(s.then_block.statements)
                if s.else_block:
                    collect(s.else_block.statements)
            elif isinstance(s, While):
                collect(s.body.statements)

    collect(program.statements)

    # 剩余顶层非函数/非 struct 语句
    for stmt in program.statements:
        if not isinstance(stmt, (FunctionDeclaration, StructDecl)):
            top_stmts.append(stmt)

    # 输出 struct
    for s in structs:
        fields_c = '; '.join(f'{_type_to_c(t)} {n}' for n, t in s.fields) + ';'
        lines.append(f'typedef struct {{ {fields_c} }} {s.name};')
    if structs:
        lines.append('')

    # 输出非 main 函数
    for func in other_funcs:
        _gen_function(lines, func)

    # 生成 main
    if main_func:
        lines.append('int main(void) {')
        for stmt in main_func.body.statements:
            _gen_stmt(lines, stmt, indent=1)
        lines.append('    return 0;')
        lines.append('}')
        for stmt in top_stmts:
            _gen_stmt(lines, stmt, indent=0)
    elif top_stmts:
        lines.append('int main(void) {')
        for stmt in top_stmts:
            _gen_stmt(lines, stmt, indent=1)
        lines.append('    return 0;')
        lines.append('}')
    else:
        lines.append('int main(void) { return 0; }')

    return '\n'.join(lines)


def _gen_function(lines: list, func):
    from compiler.ast import FunctionDeclaration
    c_ret = _type_to_c(func.return_type or "void")
    params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in func.params)
    if not params_c:
        params_c = "void"
    lines.append(f'{c_ret} {func.name}({params_c}) {{')
    for stmt in func.body.statements:
        _gen_stmt(lines, stmt, indent=1)
    lines.append('}')


def _gen_stmt(lines: list, stmt, indent: int):
    from compiler.ast import (
        VariableDeclaration, ExpressionStatement, Assignment,
        Block, If, While, Return, StructDecl,
    )
    pad = '    ' * indent

    if isinstance(stmt, StructDecl):
        pass  # struct 已在文件作用域生成

    elif isinstance(stmt, VariableDeclaration):
        c_type = _type_to_c(stmt.type)
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
    from compiler.ast import (
        IntegerLiteral, StringLiteral, Identifier,
        BinaryOp, FunctionCall, StructLiteral, FieldAccess,
    )

    if isinstance(node, IntegerLiteral):
        return str(node.value)

    if isinstance(node, StringLiteral):
        return f'"{node.value}"'

    if isinstance(node, Identifier):
        return node.name

    if isinstance(node, BinaryOp):
        left = _gen_expr(node.left)
        right = _gen_expr(node.right)
        return f'({left} {node.op} {right})'

    if isinstance(node, FunctionCall):
        args = ', '.join(_gen_expr(a) for a in node.args)
        return f'{node.name}({args})'

    if isinstance(node, StructLiteral):
        vals = ', '.join(_gen_expr(v) for _n, v in node.fields)
        return f'({node.name}){{{vals}}}'

    if isinstance(node, FieldAccess):
        return f'{_gen_expr(node.obj)}.{node.field}'

    raise NotImplementedError(f"codegen expr for {type(node).__name__}")
