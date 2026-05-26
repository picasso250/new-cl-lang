"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct/enum 定义提升到文件作用域，fun main() 映射为 int main(void)。
str 是胖指针 {ptr, len}，打印用 %.*s。
所有生成函数内闭于 generate_c。
"""

from compiler.builtins import lower_builtin_expr, lower_builtin_stmt
from compiler.c_abi import c_user_ident, slice_append_name, slice_copy_name, type_to_c
from compiler.codegen_collect import collect_codegen_inputs, parse_fn_type
from compiler.codegen_context import CodegenContext
from compiler.runtime import emit_runtime


_type_to_c = type_to_c
_slice_append_name = slice_append_name
_slice_copy_name = slice_copy_name


def generate_c(program: "Program") -> str:
    from compiler.ast import (
        FunctionDeclaration, StructDecl, EnumDecl, ImportDecl, ForIn, Block, While,
        VariableDeclaration, ExpressionStatement, Assignment,
        Return, SliceExpr, ArrayLiteral, SliceLiteral, FunctionCall,
        IfExpr, BlockExpr, MatchExpr, IntegerLiteral, FloatLiteral, StringLiteral, BoolLiteral, NilLiteral, Identifier, BinaryOp, UnaryOp,
        FunctionExpr,
        EnumRef, StructLiteral, FieldAccess, IndexAccess, SliceExpr, MethodCall,
        TryCatch, Throw, Defer, Break
    )

    collected = collect_codegen_inputs(program)
    ctx = CodegenContext()
    _lines = []
    _slice_types = collected.slice_types
    _return_label = [None]
    _return_var = [None]
    _return_type = ["void"]
    _defer_sites = []
    _emitting_defer = [False]
    _closure_env_stack = []
    _closures = collected.closures
    structs = collected.structs
    enums = collected.enums
    other_funcs = collected.other_funcs
    main_func = collected.main_func
    top_stmts = collected.top_stmts
    _fn_types = collected.fn_types

    # ——— 输出头部 + runtime 类型定义 ———
    _lines.extend(emit_runtime(_slice_types))

    def enum_variant_c(enum_name, variant):
        return f'{c_user_ident(enum_name).upper()}_{variant.upper()}'

    for e in enums:
        vs = ', '.join(enum_variant_c(e.name, v) for v in e.variants)
        _lines.append(f'typedef enum {{ {vs} }} {_type_to_c(e.name)};')
    if enums:
        _lines.append('')

    for s in structs:
        fields_c = '; '.join(f'{_type_to_c(t)} {n}' for n, t in s.fields) + ';'
        _lines.append(f'typedef struct {{ {fields_c} }} {_type_to_c(s.name)};')
    if structs:
        _lines.append('')

    for fn_t in sorted(_fn_types):
        parsed = parse_fn_type(fn_t)
        if parsed is None:
            continue
        arg_types, ret_type = parsed
        c_name = _type_to_c(fn_t)
        c_ret = _type_to_c(ret_type)
        fn_args = ['void* env'] + [f'{_type_to_c(t)} a{i}' for i, t in enumerate(arg_types)]
        _lines.append(f'typedef struct {{ {c_ret} (*call)({", ".join(fn_args)}); void* env; }} {c_name};')
    if _fn_types:
        _lines.append('')

    for closure in _closures:
        cid = closure.closure_id
        fields = getattr(closure, "captures", [])
        if fields:
            fields_c = '; '.join(f'{_type_to_c(t)} {c_user_ident(n)}' for n, t in fields) + ';'
        else:
            fields_c = 'char _unused;'
        _lines.append(f'typedef struct {{ {fields_c} }} __nc_env_{cid};')
    if _closures:
        _lines.append('')

    # ——— 代码生成内部函数 ———
    def root_expr_temp(name, nc_type, indent):
        pad = '    ' * indent
        line = ctx.tracked_root_expr(name, nc_type)
        if line is not None:
            _lines.append(f'{pad}{line}')

    def emit_root_push(c_name, nc_type, indent):
        line = ctx.root_push_for_type(c_name, nc_type)
        if line is not None:
            _lines.append(f'{"    " * indent}{line}')

    def emit_return_expr(expr, indent):
        pad = '    ' * indent
        if _return_type[0] == "void":
            _lines.append(f'{pad}goto {_return_label[0]};')
            return
        _lines.append(f'{pad}{_return_var[0]} = {gen_expr(expr)};')
        _lines.append(f'{pad}goto {_return_label[0]};')

    def emit_return_void(indent):
        pad = '    ' * indent
        _lines.append(f'{pad}goto {_return_label[0]};')

    def emit_deferred(indent):
        if not _defer_sites:
            return
        old = _emitting_defer[0]
        _emitting_defer[0] = True
        pad = '    ' * indent
        _lines.append(f'{pad}while (__nc_defer_top > 0) {{')
        _lines.append(f'{pad}    switch (__nc_defer_stack[--__nc_defer_top]) {{')
        for site_id, body in _defer_sites:
            _lines.append(f'{pad}        case {site_id}:')
            for s in body.statements:
                gen_stmt(s, indent + 3)
            _lines.append(f'{pad}            break;')
        _lines.append(f'{pad}    }}')
        _lines.append(f'{pad}}}')
        _emitting_defer[0] = old

    def defer_site_id(stmt):
        site_id = getattr(stmt, "_defer_site_id", None)
        if site_id is None:
            site_id = len(_defer_sites)
            stmt._defer_site_id = site_id
            _defer_sites.append((site_id, stmt.body))
        return site_id

    def gen_expr(node) -> str:
        if isinstance(node, IntegerLiteral):
            return str(node.value)
        if isinstance(node, FloatLiteral):
            if getattr(node, "type", None) == "f32":
                return f'((float)({node.value}))'
            return node.value
        if isinstance(node, BoolLiteral):
            return '1' if node.value else '0'
        if isinstance(node, NilLiteral):
            return 'NULL'
        if isinstance(node, StringLiteral):
            esc = node.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'(str){{(uint8_t*)"{esc}", {len(node.value)}}}'
        if isinstance(node, Identifier):
            if getattr(node, "is_capture", False) and _closure_env_stack:
                return f'{_closure_env_stack[-1]}->{c_user_ident(node.name)}'
            return c_user_ident(node.name)
        if isinstance(node, BinaryOp):
            left_c = gen_expr(node.left)
            right_c = gen_expr(node.right)
            if node.op in ("==", "!=") and getattr(node.left, "type", "") == "str":
                if node.op == "==":
                    return f'__nc_str_eq({left_c}, {right_c})'
                return f'!__nc_str_eq({left_c}, {right_c})'
            if node.op == "+" and getattr(node.left, "type", "") == "str":
                return f'__nc_str_cat({left_c}, {right_c})'
            return f'({left_c} {node.op} {right_c})'
        if isinstance(node, UnaryOp):
            return f'({node.op}{gen_expr(node.operand)})'
        if isinstance(node, EnumRef):
            return enum_variant_c(node.enum_name, node.variant)
        if isinstance(node, FunctionCall):
            builtin_c = lower_builtin_expr(node, gen_expr, _slice_append_name)
            if builtin_c is not None:
                return builtin_c
            args = ', '.join(gen_expr(a) for a in node.args)
            if getattr(node, "is_closure_call", False):
                call_name = c_user_ident(node.name)
                prefix = f'{call_name}.env'
                if args:
                    return f'{call_name}.call({prefix}, {args})'
                return f'{call_name}.call({prefix})'
            return f'{c_user_ident(node.name)}({args})'
        if isinstance(node, FunctionExpr):
            cid = node.closure_id
            tmp = ctx.next_tmp("__nc_closure")
            env = ctx.next_tmp("__nc_env")
            pad = '    ' * ctx.expr_indent
            c_t = _type_to_c(node.type)
            _lines.append(f'{pad}__nc_env_{cid}* {env} = (__nc_env_{cid}*)__nc_gc_alloc(sizeof(__nc_env_{cid}));')
            for cname, _ctype in getattr(node, "captures", []):
                _lines.append(f'{pad}{env}->{c_user_ident(cname)} = {c_user_ident(cname)};')
            _lines.append(f'{pad}{c_t} {tmp} = {{ __nc_lambda_{cid}, {env} }};')
            root_expr_temp(tmp, node.type, ctx.expr_indent)
            return tmp
        if isinstance(node, IfExpr):
            if getattr(node, "type", None) == "void":
                raise NotImplementedError("void if expression has no C value")
            tmp = ctx.next_tmp("__nc_if")
            pad = '    ' * ctx.expr_indent
            _lines.append(f'{pad}{_type_to_c(node.type)} {tmp};')
            gen_ifexpr_assign(node, tmp, ctx.expr_indent)
            root_expr_temp(tmp, node.type, ctx.expr_indent)
            return tmp
        if isinstance(node, MatchExpr):
            if getattr(node, "type", None) == "void":
                raise NotImplementedError("void match expression has no C value")
            tmp = ctx.next_tmp("__nc_match")
            pad = '    ' * ctx.expr_indent
            _lines.append(f'{pad}{_type_to_c(node.type)} {tmp};')
            gen_matchexpr_assign(node, tmp, ctx.expr_indent)
            root_expr_temp(tmp, node.type, ctx.expr_indent)
            return tmp
        if isinstance(node, BlockExpr):
            tmp = ctx.next_tmp("__nc_block")
            pad = '    ' * ctx.expr_indent
            _lines.append(f'{pad}{_type_to_c(node.type)} {tmp};')
            gen_block_value_assign(node.block, tmp, ctx.expr_indent)
            root_expr_temp(tmp, node.type, ctx.expr_indent)
            return tmp
        if isinstance(node, StructLiteral):
            vals = ', '.join(gen_expr(v) for _n, v in node.fields)
            return f'({_type_to_c(node.name)}){{{vals}}}'
        if isinstance(node, FieldAccess):
            obj_c = gen_expr(node.obj)
            obj_type = getattr(node.obj, "type", "")
            if obj_type.startswith("*") or obj_type.startswith("?*"):
                return f'{obj_c}->{node.field}'
            return f'{obj_c}.{node.field}'
        if isinstance(node, MethodCall):
            obj = node.obj
            obj_type = obj.type if hasattr(obj, 'type') else ""
            if obj_type.startswith("?*"):
                obj_type = obj_type[2:]
            elif obj_type.startswith("*"):
                obj_type = obj_type[1:]
            obj_c = gen_expr(obj)
            if node.args:
                args_c = ', ' + ', '.join(gen_expr(a) for a in node.args)
            else:
                args_c = ''
            return f'{obj_type}_{node.method}({obj_c}{args_c})'
        if isinstance(node, IndexAccess):
            obj_c = gen_expr(node.obj)
            idx_c = gen_expr(node.index)
            obj_type = getattr(node.obj, "type", "")
            if obj_type == "nc_map":
                return f'__nc_map_get_str(&{obj_c}, {idx_c})'
            if obj_type.startswith("[]"):
                return f'{obj_c}.ptr[{idx_c}]'
            if obj_type == "str":
                return f'(int)(unsigned char)(({obj_c}).ptr[{idx_c}])'
            return f'{obj_c}[{idx_c}]'

        if isinstance(node, SliceExpr):
            arr_c = gen_expr(node.array)
            start_c = gen_expr(node.start) if node.start else '0'
            arr_t = getattr(node.array, "type", "")
            if arr_t == "str":
                end_c = gen_expr(node.end) if node.end else f'{arr_c}.len'
                return f'__nc_str_slice_copy({arr_c}, {start_c}, {end_c})'
            if arr_t.startswith("[]"):
                end_c = gen_expr(node.end) if node.end else f'{arr_c}.len'
                elem_t = arr_t[2:]
                return f'{_slice_copy_name(elem_t)}({arr_c}.ptr + {start_c}, {end_c} - {start_c})'
            if arr_t.startswith("["):
                end_c = gen_expr(node.end) if node.end else arr_t[1:].split("]", 1)[0]
                elem_t = arr_t.split("]", 1)[1]
                return f'{_slice_copy_name(elem_t)}({arr_c} + {start_c}, {end_c} - {start_c})'
            return f'({arr_c} + {start_c})'
        raise NotImplementedError(f"gen_expr: {type(node).__name__}")

    def gen_expr_stmt(expr, indent=0):
        old_indent = ctx.expr_indent
        ctx.expr_indent = indent
        pad = '    ' * indent
        if isinstance(expr, IfExpr):
            gen_ifexpr_stmt(expr, indent)
        elif isinstance(expr, MatchExpr):
            gen_matchexpr_stmt(expr, indent)
        elif isinstance(expr, FunctionCall) and lower_builtin_stmt(expr, gen_expr, _lines.append, pad):
            pass
        else:
            _lines.append(f'{pad}{gen_expr(expr)};')
        ctx.expr_indent = old_indent

    def block_tail_expr(block):
        if not block.statements:
            return None
        last = block.statements[-1]
        if isinstance(last, ExpressionStatement):
            return last.expr
        return None

    def gen_block_value_assign(block, target, indent):
        tail = block_tail_expr(block)
        body = block.statements[:-1] if tail else block.statements
        for s in body:
            gen_stmt(s, indent)
        if isinstance(tail, IfExpr):
            gen_ifexpr_assign(tail, target, indent)
            return
        if isinstance(tail, MatchExpr):
            gen_matchexpr_assign(tail, target, indent)
            return
        _lines.append(f'{"    " * indent}{target} = {gen_expr(tail)};')

    def gen_block_value_return(block, indent):
        tail = block_tail_expr(block)
        body = block.statements[:-1] if tail else block.statements
        for s in body:
            gen_stmt(s, indent)
        if isinstance(tail, IfExpr):
            gen_ifexpr_return(tail, indent)
            return
        if isinstance(tail, MatchExpr):
            gen_matchexpr_return(tail, indent)
            return
        emit_return_expr(tail, indent)

    def gen_ifexpr_assign(expr, target, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(expr.condition)}) {{')
        gen_block_value_assign(expr.then_block, target, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_assign(expr.else_block, target, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_ifexpr_stmt(expr, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(expr.condition)}) {{')
        for s in expr.then_block.statements:
            gen_stmt(s, indent + 1)
        if expr.else_block:
            _lines.append(f'{pad}}} else {{')
            for s in expr.else_block.statements:
                gen_stmt(s, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_ifexpr_return(expr, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(expr.condition)}) {{')
        gen_block_value_return(expr.then_block, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_return(expr.else_block, indent + 1)
        _lines.append(f'{pad}}}')

    def emit_match_chain(expr, indent, emit_arm):
        pad = '    ' * indent
        scrut_tmp = ctx.next_tmp("__nc_match_scrut")
        _lines.append(f'{pad}{_type_to_c(expr.scrutinee.type)} {scrut_tmp} = {gen_expr(expr.scrutinee)};')
        root_expr_temp(scrut_tmp, expr.scrutinee.type, indent)
        emitted_cond = False
        for pattern, body in expr.arms:
            if pattern is None:
                if emitted_cond:
                    _lines.append(f'{pad}}} else {{')
                else:
                    _lines.append(f'{pad}{{')
            else:
                cond = match_condition(scrut_tmp, expr.scrutinee.type, pattern)
                if emitted_cond:
                    _lines.append(f'{pad}}} else if ({cond}) {{')
                else:
                    _lines.append(f'{pad}if ({cond}) {{')
                emitted_cond = True
            emit_arm(body, indent + 1)
        _lines.append(f'{pad}}}')

    def match_condition(scrut_tmp, scrut_type, pattern):
        pat_c = gen_expr(pattern)
        if scrut_type == "str":
            return f'__nc_str_eq({scrut_tmp}, {pat_c})'
        return f'{scrut_tmp} == {pat_c}'

    def gen_expr_value_assign(expr, target, indent):
        if isinstance(expr, IfExpr):
            gen_ifexpr_assign(expr, target, indent)
            return
        if isinstance(expr, MatchExpr):
            gen_matchexpr_assign(expr, target, indent)
            return
        if isinstance(expr, BlockExpr):
            gen_block_value_assign(expr.block, target, indent)
            return
        _lines.append(f'{"    " * indent}{target} = {gen_expr(expr)};')

    def gen_expr_value_return(expr, indent):
        if isinstance(expr, IfExpr):
            gen_ifexpr_return(expr, indent)
            return
        if isinstance(expr, MatchExpr):
            gen_matchexpr_return(expr, indent)
            return
        if isinstance(expr, BlockExpr):
            gen_block_value_return(expr.block, indent)
            return
        emit_return_expr(expr, indent)

    def gen_matchexpr_assign(expr, target, indent):
        emit_match_chain(expr, indent, lambda body, body_indent: gen_expr_value_assign(body, target, body_indent))

    def gen_matchexpr_stmt(expr, indent):
        emit_match_chain(expr, indent, lambda body, body_indent: gen_expr_stmt(body, body_indent))

    def gen_matchexpr_return(expr, indent):
        emit_match_chain(expr, indent, gen_expr_value_return)

    def gen_stmt(stmt, indent=1):
        old_indent = ctx.expr_indent
        ctx.expr_indent = indent
        pad = '    ' * indent

        if isinstance(stmt, (StructDecl, EnumDecl, ImportDecl)):
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, VariableDeclaration):
            c_name = c_user_ident(stmt.name)
            if isinstance(stmt.initializer, ArrayLiteral):
                arr = stmt.initializer
                c_et = _type_to_c(arr.elem_type)
                elems = ', '.join(gen_expr(e) for e in arr.elements)
                _lines.append(f'{pad}{c_et} {c_name}[{arr.length}] = {{{elems}}};')
            elif isinstance(stmt.initializer, SliceLiteral):
                sl = stmt.initializer
                c_t = _type_to_c(stmt.type)
                elem_c = _type_to_c(sl.elem_type)
                n = len(sl.elements)
                _lines.append(f'{pad}{c_t} {c_name} = {{0, 0, 0}};')
                if n:
                    _lines.append(f'{pad}{c_name}.ptr = ({elem_c}*)__nc_gc_alloc({n} * sizeof({elem_c}));')
                    _lines.append(f'{pad}{c_name}.len = {n}; {c_name}.cap = {n};')
                    for i, elem in enumerate(sl.elements):
                        _lines.append(f'{pad}{c_name}.ptr[{i}] = {gen_expr(elem)};')
                    ctx.track_var(stmt.name, stmt.name)
                    emit_root_push(c_name, stmt.type, indent)
            elif isinstance(stmt.initializer, SliceExpr):
                c_t = _type_to_c(stmt.type)
                _lines.append(f'{pad}{c_t} {c_name} = {gen_expr(stmt.initializer)};')
                ctx.track_var(stmt.name, stmt.type)
                emit_root_push(c_name, stmt.type, indent)
            elif isinstance(stmt.initializer, IfExpr):
                c_t = _type_to_c(stmt.type)
                _lines.append(f'{pad}{c_t} {c_name};')
                gen_ifexpr_assign(stmt.initializer, c_name, indent)
                line = ctx.tracked_root_expr(stmt.name, stmt.type)
                if line is not None:
                    emit_root_push(c_name, stmt.type, indent)
            else:
                c_t = _type_to_c(stmt.type)
                # 堆分配: let s = new Struct{...}
                if isinstance(stmt.initializer, StructLiteral) and stmt.initializer.heap:
                    sname = stmt.initializer.name
                    sname_c = _type_to_c(sname)
                    _lines.append(f'{pad}{c_t} {c_name} = ({sname_c}*)__nc_gc_alloc(sizeof({sname_c}));')
                    for fname, fval in stmt.initializer.fields:
                        _lines.append(f'{pad}{c_name}->{fname} = {gen_expr(fval)};')
                    ctx.track_var(stmt.name, stmt.type)
                    emit_root_push(c_name, stmt.type, indent)
                else:
                    init_c = gen_expr(stmt.initializer)
                    if stmt.type == "nc_map":
                        _lines.append(f'{pad}{c_t} {c_name}; __nc_map_init(&{c_name});')
                    else:
                        _lines.append(f'{pad}{c_t} {c_name} = {init_c};')
                    line = ctx.tracked_root_expr(stmt.name, stmt.type)
                    if line is not None:
                        emit_root_push(c_name, stmt.type, indent)
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, Identifier):
                target_name = c_user_ident(stmt.target.name)
                _lines.append(f'{pad}{target_name} = {gen_expr(stmt.expr)};')
                # GC 根刷新
                if stmt.target.name in ctx.gc_vars:
                    var_t = ctx.gc_vars[stmt.target.name]
                    emit_root_push(target_name, var_t, indent)
            elif isinstance(stmt.target, IndexAccess):
                obj_c = gen_expr(stmt.target.obj)
                idx_c = gen_expr(stmt.target.index)
                obj_type = getattr(stmt.target.obj, "type", "")
                if obj_type == "nc_map":
                    _lines.append(f'{pad}__nc_map_set_str(&{obj_c}, {idx_c}, {gen_expr(stmt.expr)});')
                elif obj_type.startswith("[]"):
                    _lines.append(f'{pad}{obj_c}.ptr[{idx_c}] = {gen_expr(stmt.expr)};')
                else:
                    _lines.append(f'{pad}{obj_c}[{idx_c}] = {gen_expr(stmt.expr)};')
            elif isinstance(stmt.target, FieldAccess):
                _lines.append(f'{pad}{gen_expr(stmt.target)} = {gen_expr(stmt.expr)};')
            else:
                _lines.append(f'{pad}{gen_expr(stmt.target)} = {gen_expr(stmt.expr)};')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, ExpressionStatement):
            gen_expr_stmt(stmt.expr, indent)
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, While):
            cond_c = gen_expr(stmt.condition)
            _lines.append(f'{pad}while ({cond_c}) {{')
            for s in stmt.body.statements:
                gen_stmt(s, indent + 1)
            _lines.append(f'{pad}}}')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, ForIn):
            if stmt.start is not None:
                start_c = gen_expr(stmt.start)
                end_c = gen_expr(stmt.end)
                _lines.append(f'{pad}for (int {stmt.index} = {start_c}; {stmt.index} < {end_c}; {stmt.index}++) {{')
            else:
                iter_c = gen_expr(stmt.iterable)
                _lines.append(f'{pad}for (int {stmt.index} = 0; {stmt.index} < {iter_c}.len; {stmt.index}++) {{')
                elem_t = getattr(stmt.iterable, "type", "[]i32")
                elem_c = _type_to_c(elem_t[2:] if elem_t.startswith("[]") else "i32")
                _lines.append(f'{pad}    {elem_c} {stmt.value} = {iter_c}.ptr[{stmt.index}];')
            for s in stmt.body.statements:
                gen_stmt(s, indent + 1)
            _lines.append(f'{pad}}}')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Return):
            if stmt.expr:
                emit_return_expr(stmt.expr, indent)
            else:
                emit_return_void(indent)
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Block):
            for s in stmt.statements:
                gen_stmt(s, indent)
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, TryCatch):
            pad = '    ' * indent
            _lines.append(f'{pad}{{')
            _lines.append(f'{pad}    __nc_ex_frame_t __nc_f;')
            _lines.append(f'{pad}    __nc_f.prev = __nc_ex_top; __nc_ex_top = &__nc_f;')
            _lines.append(f'{pad}    if (setjmp(__nc_f.jb) == 0) {{')
            for s in stmt.try_block.statements:
                gen_stmt(s, indent + 2)
            _lines.append(f'{pad}        __nc_ex_top = __nc_f.prev;')
            _lines.append(f'{pad}    }} else {{')
            _lines.append(f'{pad}        __nc_ex_top = __nc_f.prev;')
            _lines.append(f'{pad}        str {stmt.error_name} = __nc_f.ex;')
            for s in stmt.catch_block.statements:
                gen_stmt(s, indent + 2)
            _lines.append(f'{pad}    }}')
            _lines.append(f'{pad}}}')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Throw):
            pad = '    ' * indent
            ex_c = gen_expr(stmt.expr)
            emit_deferred(indent)
            _lines.append(f'{pad}__nc_throw({ex_c});')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Defer):
            if _emitting_defer[0]:
                for s in stmt.body.statements:
                    gen_stmt(s, indent)
            else:
                site_id = defer_site_id(stmt)
                _lines.append(f'{pad}__nc_defer_stack[__nc_defer_top++] = {site_id};')
            ctx.expr_indent = old_indent
            return
        if isinstance(stmt, Break):
            pad = '    ' * indent
            _lines.append(f'{pad}break;')
            ctx.expr_indent = old_indent
            return
        raise NotImplementedError(f"gen_stmt: {type(stmt).__name__}")

    # ——— 闭包 trampoline ———
    for closure in _closures:
        ctx.reset_function_state()
        _defer_sites.clear()
        cid = closure.closure_id
        c_ret = _type_to_c(closure.return_type or "void")
        _return_type[0] = c_ret
        _return_label[0] = f"__nc_lambda_{cid}_return"
        _return_var[0] = "__nc_ret"
        params_c = ', '.join([f'{_type_to_c(t)} {c_user_ident(n)}' for n, t in closure.params])
        full_params = 'void* __nc_env_raw'
        if params_c:
            full_params += ', ' + params_c
        _lines.append(f'static {c_ret} __nc_lambda_{cid}({full_params}) {{')
        _lines.append('    size_t __nc_gc_mark = __nc_gc_root_mark();')
        _lines.append('    int __nc_defer_stack[1024];')
        _lines.append('    int __nc_defer_top = 0;')
        _lines.append(f'    __nc_env_{cid}* __env = (__nc_env_{cid}*)__nc_env_raw;')
        if c_ret != "void":
            _lines.append(f'    {c_ret} __nc_ret;')
        _closure_env_stack.append("__env")
        for i, s in enumerate(closure.body.statements):
            if i == len(closure.body.statements) - 1 and (closure.return_type or "void") != "void":
                if isinstance(s, ExpressionStatement):
                    emit_return_expr(s.expr, 1)
                    continue
            gen_stmt(s)
        _closure_env_stack.pop()
        _lines.append(f'{_return_label[0]}:')
        emit_deferred(1)
        _lines.append('    __nc_gc_root_rewind(__nc_gc_mark);')
        if c_ret != "void":
            _lines.append(f'    return {_return_var[0]};')
        else:
            _lines.append('    return;')
        _lines.append('}')
    if _closures:
        _lines.append('')

    # ——— 前向声明（支持互递归） ———
    for func in other_funcs:
        c_ret = _type_to_c(func.return_type or "void")
        if func.receiver_name:
            rtype = func.receiver_type.lstrip("*")
            fname = c_user_ident(f"{rtype}_{func.name}")
            all_params = [(func.receiver_name, func.receiver_type)] + func.params
        else:
            fname = c_user_ident(func.name)
            all_params = func.params
        params_c = ', '.join(f'{_type_to_c(t)} {c_user_ident(n)}' for n, t in all_params) or "void"
        _lines.append(f'{c_ret} {fname}({params_c});')
    if other_funcs:
        _lines.append('')

    # ——— 输出函数 ———
    for func in other_funcs:
        ctx.reset_function_state()
        _defer_sites.clear()
        c_ret = _type_to_c(func.return_type or "void")
        _return_type[0] = c_ret
        _return_label[0] = "__nc_return"
        _return_var[0] = "__nc_ret"
        if func.receiver_name:
            rtype = func.receiver_type.lstrip("*")
            fname = c_user_ident(f"{rtype}_{func.name}")
            all_params = [(func.receiver_name, func.receiver_type)] + func.params
        else:
            fname = c_user_ident(func.name)
            all_params = func.params
        params_c = ', '.join(f'{_type_to_c(t)} {c_user_ident(n)}' for n, t in all_params) or "void"
        _lines.append(f'{c_ret} {fname}({params_c}) {{')
        _lines.append('    size_t __nc_gc_mark = __nc_gc_root_mark();')
        _lines.append('    int __nc_defer_stack[1024];')
        _lines.append('    int __nc_defer_top = 0;')
        if c_ret != "void":
            _lines.append(f'    {c_ret} __nc_ret;')
        for i, s in enumerate(func.body.statements):
            if i == len(func.body.statements) - 1 and (func.return_type or "void") != "void":
                if isinstance(s, ExpressionStatement):
                    emit_return_expr(s.expr, 1)
                    continue
            gen_stmt(s)
        _lines.append(f'{_return_label[0]}:')
        emit_deferred(1)
        _lines.append('    __nc_gc_root_rewind(__nc_gc_mark);')
        if c_ret != "void":
            _lines.append(f'    return {_return_var[0]};')
        else:
            _lines.append('    return;')
        _lines.append('}')

    if main_func:
        ctx.reset_function_state()
        _defer_sites.clear()
        _return_type[0] = "int"
        _return_label[0] = "__nc_main_return"
        _return_var[0] = "__nc_ret"
        _lines.append('int main(void) {')
        _lines.append('    __nc_gc_init();')
        _lines.append('    size_t __nc_gc_mark = __nc_gc_root_mark();')
        _lines.append('    int __nc_defer_stack[1024];')
        _lines.append('    int __nc_defer_top = 0;')
        _lines.append('    int __nc_ret = 0;')
        for i, s in enumerate(main_func.body.statements):
            if i == len(main_func.body.statements) - 1 and (main_func.return_type or "void") != "void":
                if isinstance(s, ExpressionStatement):
                    emit_return_expr(s.expr, 1)
                    continue
            gen_stmt(s)
        _lines.append(f'{_return_label[0]}:')
        emit_deferred(1)
        _lines.append('    __nc_gc_root_rewind(__nc_gc_mark);')
        _lines.append('    return __nc_ret;')
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

