"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct/enum 定义提升到文件作用域，fun main() 映射为 int main(void)。
所有生成函数内闭于 generate_c，共享 _lines 和 _slice_vars。
"""

NC_TO_C = {
    "i32": "int", "i64": "long long",
    "u32": "unsigned int", "u64": "unsigned long long",
    "f32": "float", "f64": "double",
    "bool": "int", "void": "void",
    "str": "const char*",
}


def _type_to_c(nc_type: str) -> str:
    return NC_TO_C.get(nc_type, nc_type)


def generate_c(program: "Program") -> str:
    from compiler.ast import (
        FunctionDeclaration, StructDecl, EnumDecl, Switch, Block, If, While,
        VariableDeclaration, ExpressionStatement, Assignment,
        Return, SliceExpr, ArrayLiteral, FunctionCall,
        IntegerLiteral, StringLiteral, Identifier, BinaryOp, UnaryOp,
        EnumRef, StructLiteral, FieldAccess, IndexAccess,
    )

    _lines = []
    _slice_vars = {}

    # ——— 收集类型定义 ———
    structs = []
    enums = []
    other_funcs = []
    main_func = None

    def collect(stmts):
        nonlocal main_func
        for s in stmts:
            if isinstance(s, StructDecl):
                structs.append(s)
            elif isinstance(s, EnumDecl):
                enums.append(s)
            elif isinstance(s, FunctionDeclaration):
                if s.name == "main":
                    main_func = s
                else:
                    other_funcs.append(s)
                collect(s.body.statements)
            elif isinstance(s, Block):
                collect(s.statements)
            elif isinstance(s, If):
                collect(s.then_block.statements)
                if s.else_block:
                    collect(s.else_block.statements)
            elif isinstance(s, While):
                collect(s.body.statements)
            elif isinstance(s, Switch):
                for _cv, cs in s.cases:
                    collect([cs])

    collect(program.statements)

    top_stmts = [s for s in program.statements
                 if not isinstance(s, (FunctionDeclaration, StructDecl, EnumDecl))]

    # ——— 输出头部 + 类型定义 ———
    _lines.append('#include <stdio.h>')
    _lines.append('#include <stdlib.h>')
    _lines.append('')

    for s in structs:
        fields_c = '; '.join(f'{_type_to_c(t)} {n}' for n, t in s.fields) + ';'
        _lines.append(f'typedef struct {{ {fields_c} }} {s.name};')
    if structs:
        _lines.append('')

    for e in enums:
        vs = ', '.join(f'{e.name.upper()}_{v.upper()}' for v in e.variants)
        _lines.append(f'typedef enum {{ {vs} }} {e.name};')
    if enums:
        _lines.append('')

    # ——— 代码生成内部函数 ———
    def gen_expr(node) -> str:
        if isinstance(node, IntegerLiteral):
            return str(node.value)
        if isinstance(node, StringLiteral):
            return f'"{node.value}"'
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, BinaryOp):
            return f'({gen_expr(node.left)} {node.op} {gen_expr(node.right)})'
        if isinstance(node, UnaryOp):
            return f'({node.op}{gen_expr(node.operand)})'
        if isinstance(node, EnumRef):
            return f'{node.enum_name.upper()}_{node.variant.upper()}'
        if isinstance(node, FunctionCall):
            args = ', '.join(gen_expr(a) for a in node.args)
            return f'{node.name}({args})'
        if isinstance(node, StructLiteral):
            vals = ', '.join(gen_expr(v) for _n, v in node.fields)
            return f'({node.name}){{{vals}}}'
        if isinstance(node, FieldAccess):
            return f'{gen_expr(node.obj)}.{node.field}'
        if isinstance(node, IndexAccess):
            obj_c = gen_expr(node.obj)
            idx_c = gen_expr(node.index)
            if isinstance(node.obj, Identifier) and node.obj.name in _slice_vars:
                return f'{obj_c}._ptr[{idx_c}]'
            return f'{obj_c}[{idx_c}]'
        raise NotImplementedError(f"gen_expr: {type(node).__name__}")

    def gen_expr_stmt(expr, indent=0):
        pad = '    ' * indent
        if isinstance(expr, FunctionCall) and expr.name == "print":
            arg = expr.args[0]
            arg_type = getattr(arg, "type", "i32")
            fmt = "%s" if arg_type == "str" else "%d"
            _lines.append(f'{pad}printf("{fmt}\\n", {gen_expr(arg)});')
        else:
            _lines.append(f'{pad}{gen_expr(expr)};')

    def gen_stmt(stmt, indent=1):
        pad = '    ' * indent

        if isinstance(stmt, (StructDecl, EnumDecl)):
            return
        if isinstance(stmt, VariableDeclaration):
            if isinstance(stmt.initializer, ArrayLiteral):
                arr = stmt.initializer
                c_et = _type_to_c(arr.elem_type)
                elems = ', '.join(gen_expr(e) for e in arr.elements)
                _lines.append(f'{pad}{c_et} {stmt.name}[{arr.length}] = {{{elems}}};')
            elif isinstance(stmt.initializer, SliceExpr):
                se = stmt.initializer
                c_et = _type_to_c(stmt.type)
                arr_c = gen_expr(se.array)
                start_c = gen_expr(se.start) if se.start else '0'
                end_c = gen_expr(se.end) if se.end else '0'
                _lines.append(f'{pad}struct {{ {c_et}* _ptr; long long _len; }} {stmt.name} = {{{arr_c} + {start_c}, {end_c} - {start_c}}};')
                _slice_vars[stmt.name] = True
            else:
                c_t = _type_to_c(stmt.type)
                init_c = gen_expr(stmt.initializer)
                _lines.append(f'{pad}{c_t} {stmt.name} = {init_c};')
            return
        if isinstance(stmt, Assignment):
            _lines.append(f'{pad}{stmt.name} = {gen_expr(stmt.expr)};')
            return
        if isinstance(stmt, ExpressionStatement):
            gen_expr_stmt(stmt.expr, indent)
            return
        if isinstance(stmt, If):
            cond_c = gen_expr(stmt.condition)
            _lines.append(f'{pad}if ({cond_c}) {{')
            for s in stmt.then_block.statements:
                gen_stmt(s, indent + 1)
            if stmt.else_block:
                _lines.append(f'{pad}}} else {{')
                for s in stmt.else_block.statements:
                    gen_stmt(s, indent + 1)
            _lines.append(f'{pad}}}')
            return
        if isinstance(stmt, While):
            cond_c = gen_expr(stmt.condition)
            _lines.append(f'{pad}while ({cond_c}) {{')
            for s in stmt.body.statements:
                gen_stmt(s, indent + 1)
            _lines.append(f'{pad}}}')
            return
        if isinstance(stmt, Switch):
            scrut_c = gen_expr(stmt.scrutinee)
            _lines.append(f'{pad}switch ({scrut_c}) {{')
            for case_val, case_stmt in stmt.cases:
                val_c = gen_expr(case_val)
                _lines.append(f'{pad}    case {val_c}:')
                gen_stmt(case_stmt, indent + 2)
                _lines.append(f'{pad}        break;')
            _lines.append(f'{pad}}}')
            return
        if isinstance(stmt, Return):
            if stmt.expr:
                _lines.append(f'{pad}return {gen_expr(stmt.expr)};')
            else:
                _lines.append(f'{pad}return;')
            return
        if isinstance(stmt, Block):
            for s in stmt.statements:
                gen_stmt(s, indent)
            return
        raise NotImplementedError(f"gen_stmt: {type(stmt).__name__}")

    # ——— 输出函数 ———
    for func in other_funcs:
        c_ret = _type_to_c(func.return_type or "void")
        params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in func.params) or "void"
        _lines.append(f'{c_ret} {func.name}({params_c}) {{')
        for s in func.body.statements:
            gen_stmt(s)
        _lines.append('}')

    if main_func:
        _lines.append('int main(void) {')
        for s in main_func.body.statements:
            gen_stmt(s)
        _lines.append('    return 0;')
        _lines.append('}')
        for s in top_stmts:
            gen_stmt(s, indent=0)
    elif top_stmts:
        _lines.append('int main(void) {')
        for s in top_stmts:
            gen_stmt(s)
        _lines.append('    return 0;')
        _lines.append('}')
    else:
        _lines.append('int main(void) { return 0; }')

    return '\n'.join(_lines)
