"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct/enum 定义提升到文件作用域，fun main() 映射为 int main(void)。
str 是胖指针 {ptr, len}，打印用 %.*s。
所有生成函数内闭于 generate_c。
"""

from compiler.c_abi import slice_append_name, slice_copy_name, type_to_c
from compiler.runtime import emit_runtime


_type_to_c = type_to_c
_slice_append_name = slice_append_name
_slice_copy_name = slice_copy_name


def generate_c(program: "Program") -> str:
    from compiler.ast import (
        FunctionDeclaration, StructDecl, EnumDecl, Switch, ForIn, Block, If, While,
        VariableDeclaration, ExpressionStatement, Assignment,
        Return, SliceExpr, ArrayLiteral, SliceLiteral, FunctionCall,
        IfExpr, BlockExpr, IntegerLiteral, StringLiteral, BoolLiteral, Identifier, BinaryOp, UnaryOp,
        EnumRef, StructLiteral, FieldAccess, IndexAccess, SliceExpr, MethodCall,
        TryCatch, Throw, Defer, Break
    )

    _lines = []
    _slice_types = set()
    _gc_vars = {}  # 变量名 → 类型 (str/nc_map) 用于 GC 根追踪
    _tmp_id = [0]
    _expr_indent = [1]
    _return_label = [None]
    _return_var = [None]
    _return_type = ["void"]
    _defer_stack = []
    _emitting_defer = [False]

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
            elif isinstance(s, ForIn):
                collect(s.body.statements)
                if s.start is not None:
                    pass  # range expressions don't contain inner decls
                else:
                    pass
            elif isinstance(s, TryCatch):
                collect(s.try_block.statements)
                collect(s.catch_block.statements)
            elif isinstance(s, Defer):
                collect(s.body.statements)

    collect(program.statements)

    top_stmts = [s for s in program.statements
                 if not isinstance(s, (FunctionDeclaration, StructDecl, EnumDecl))]

    def collect_slice_type(nc_type):
        if isinstance(nc_type, str) and nc_type.startswith("[]"):
            _slice_types.add(nc_type[2:])

    def collect_expr_types(node):
        collect_slice_type(getattr(node, "type", None))
        if isinstance(node, (ArrayLiteral, SliceLiteral)):
            if isinstance(node, SliceLiteral):
                _slice_types.add(node.elem_type)
            for elem in node.elements:
                collect_expr_types(elem)
        elif isinstance(node, SliceExpr):
            collect_expr_types(node.array)
            if node.start:
                collect_expr_types(node.start)
            if node.end:
                collect_expr_types(node.end)
        elif isinstance(node, IndexAccess):
            collect_expr_types(node.obj)
            collect_expr_types(node.index)
        elif isinstance(node, BinaryOp):
            collect_expr_types(node.left)
            collect_expr_types(node.right)
        elif isinstance(node, UnaryOp):
            collect_expr_types(node.operand)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                collect_expr_types(arg)
        elif isinstance(node, IfExpr):
            collect_expr_types(node.condition)
            for s in node.then_block.statements:
                collect_stmt_types(s)
            for s in node.else_block.statements:
                collect_stmt_types(s)
        elif isinstance(node, BlockExpr):
            for s in node.block.statements:
                collect_stmt_types(s)
        elif isinstance(node, StructLiteral):
            for _n, val in node.fields:
                collect_expr_types(val)
        elif isinstance(node, FieldAccess):
            collect_expr_types(node.obj)
        elif isinstance(node, MethodCall):
            collect_expr_types(node.obj)
            for arg in node.args:
                collect_expr_types(arg)

    def collect_stmt_types(stmt):
        collect_slice_type(getattr(stmt, "type", None))
        if isinstance(stmt, VariableDeclaration):
            collect_expr_types(stmt.initializer)
        elif isinstance(stmt, Assignment):
            collect_expr_types(stmt.target)
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, ExpressionStatement):
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, If):
            collect_expr_types(stmt.condition)
            for s in stmt.then_block.statements:
                collect_stmt_types(s)
            if stmt.else_block:
                for s in stmt.else_block.statements:
                    collect_stmt_types(s)
        elif isinstance(stmt, While):
            collect_expr_types(stmt.condition)
            for s in stmt.body.statements:
                collect_stmt_types(s)
        elif isinstance(stmt, ForIn):
            if stmt.start is not None:
                collect_expr_types(stmt.start)
                collect_expr_types(stmt.end)
            else:
                collect_expr_types(stmt.iterable)
            for s in stmt.body.statements:
                collect_stmt_types(s)
        elif isinstance(stmt, Switch):
            collect_expr_types(stmt.scrutinee)
            for case_val, case_stmt in stmt.cases:
                collect_expr_types(case_val)
                collect_stmt_types(case_stmt)
        elif isinstance(stmt, FunctionDeclaration):
            collect_slice_type(stmt.return_type)
            for _n, ptype in stmt.params:
                collect_slice_type(ptype)
            for s in stmt.body.statements:
                collect_stmt_types(s)
        elif isinstance(stmt, Return) and stmt.expr:
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, TryCatch):
            for s in stmt.try_block.statements + stmt.catch_block.statements:
                collect_stmt_types(s)
        elif isinstance(stmt, Throw):
            collect_expr_types(stmt.expr)
        elif isinstance(stmt, Defer):
            for s in stmt.body.statements:
                collect_stmt_types(s)
        elif isinstance(stmt, Block):
            for s in stmt.statements:
                collect_stmt_types(s)

    for stmt in program.statements:
        collect_stmt_types(stmt)

    # ——— 输出头部 + runtime 类型定义 ———
    _lines.extend(emit_runtime(_slice_types))

    for e in enums:
        vs = ', '.join(f'{e.name.upper()}_{v.upper()}' for v in e.variants)
        _lines.append(f'typedef enum {{ {vs} }} {e.name};')
    if enums:
        _lines.append('')

    for s in structs:
        fields_c = '; '.join(f'{_type_to_c(t)} {n}' for n, t in s.fields) + ';'
        _lines.append(f'typedef struct {{ {fields_c} }} {s.name};')
    if structs:
        _lines.append('')

    # ——— 代码生成内部函数 ———
    def next_tmp(prefix="__nc_tmp"):
        name = f'{prefix}_{_tmp_id[0]}'
        _tmp_id[0] += 1
        return name

    def root_expr_temp(name, nc_type, indent):
        pad = '    ' * indent
        if nc_type == "nc_map":
            _gc_vars[name] = nc_type
            _lines.append(f'{pad}__nc_gc_push_root((void*){name}.entries);')
        elif nc_type == "str":
            _gc_vars[name] = nc_type
            _lines.append(f'{pad}__nc_gc_push_root((void*){name}.ptr);')
        elif isinstance(nc_type, str) and nc_type.startswith("[]"):
            _gc_vars[name] = nc_type
            _lines.append(f'{pad}__nc_gc_push_root((void*){name}.ptr);')
        elif isinstance(nc_type, str) and nc_type.startswith("*"):
            _gc_vars[name] = nc_type
            _lines.append(f'{pad}__nc_gc_push_root((void*){name});')

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
        if not _defer_stack:
            return
        old = _emitting_defer[0]
        _emitting_defer[0] = True
        for body in reversed(_defer_stack):
            for s in body.statements:
                gen_stmt(s, indent)
        _emitting_defer[0] = old

    def gen_expr(node) -> str:
        if isinstance(node, IntegerLiteral):
            return str(node.value)
        if isinstance(node, BoolLiteral):
            return '1' if node.value else '0'
        if isinstance(node, StringLiteral):
            esc = node.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'(str){{(uint8_t*)"{esc}", {len(node.value)}}}'
        if isinstance(node, Identifier):
            return node.name
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
            return f'{node.enum_name.upper()}_{node.variant.upper()}'
        if isinstance(node, FunctionCall):
            if node.name == "read_file":
                arg = node.args[0]
                if isinstance(arg, StringLiteral):
                    return f'__nc_read_file("{arg.value}")'
                arg_c = gen_expr(arg)
                return f'__nc_read_file({arg_c}.ptr)'
            if node.name == "append":
                slice_c = gen_expr(node.args[0])
                elem_c = gen_expr(node.args[1])
                slice_t = getattr(node.args[0], "type", "[]i32")
                elem_t = slice_t[2:] if slice_t.startswith("[]") else "i32"
                return f'{_slice_append_name(elem_t)}({slice_c}, {elem_c})'
            if node.name == "map_set_s":
                m_c = gen_expr(node.args[0])
                k_c = gen_expr(node.args[1])
                v_c = gen_expr(node.args[2])
                return f'__nc_map_set_str(&{m_c}, {k_c}, {v_c})'
            if node.name == "map_get_s":
                m_c = gen_expr(node.args[0])
                k_c = gen_expr(node.args[1])
                return f'__nc_map_get_str(&{m_c}, {k_c})'
            if node.name == "map_has":
                m_c = gen_expr(node.args[0])
                k_c = gen_expr(node.args[1])
                return f'__nc_map_has(&{m_c}, {k_c})'
            if node.name == "len":
                arg_c = gen_expr(node.args[0])
                arg_t = getattr(node.args[0], "type", "str")
                if arg_t == "str":
                    return f'(int)({arg_c}).len'
                if arg_t == "nc_map":
                    return f'(int)({arg_c}).len'
                return f'(int)({arg_c}).len'
            if node.name == "str":
                arg_c = gen_expr(node.args[0])
                arg_t = getattr(node.args[0], "type", "i32")
                if arg_t == "i32":
                    return f'__nc_i32_to_str({arg_c})'
                return arg_c
            if node.name == "i32":
                arg_c = gen_expr(node.args[0])
                arg_t = getattr(node.args[0], "type", "str")
                if arg_t == "str":
                    return f'__nc_str_to_i32({arg_c})'
                return arg_c
            args = ', '.join(gen_expr(a) for a in node.args)
            return f'{node.name}({args})'
        if isinstance(node, IfExpr):
            tmp = next_tmp("__nc_if")
            pad = '    ' * _expr_indent[0]
            _lines.append(f'{pad}{_type_to_c(node.type)} {tmp};')
            gen_ifexpr_assign(node, tmp, _expr_indent[0])
            root_expr_temp(tmp, node.type, _expr_indent[0])
            return tmp
        if isinstance(node, BlockExpr):
            tmp = next_tmp("__nc_block")
            pad = '    ' * _expr_indent[0]
            _lines.append(f'{pad}{_type_to_c(node.type)} {tmp};')
            gen_block_value_assign(node.block, tmp, _expr_indent[0])
            root_expr_temp(tmp, node.type, _expr_indent[0])
            return tmp
        if isinstance(node, StructLiteral):
            vals = ', '.join(gen_expr(v) for _n, v in node.fields)
            return f'({node.name}){{{vals}}}'
        if isinstance(node, FieldAccess):
            obj_c = gen_expr(node.obj)
            obj_type = getattr(node.obj, "type", "")
            if obj_type.startswith("*"):
                return f'{obj_c}->{node.field}'
            return f'{obj_c}.{node.field}'
        if isinstance(node, MethodCall):
            obj = node.obj
            obj_type = obj.type if hasattr(obj, 'type') else ""
            if obj_type.startswith("*"):
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
        old_indent = _expr_indent[0]
        _expr_indent[0] = indent
        pad = '    ' * indent
        if isinstance(expr, FunctionCall) and expr.name == "gc_collect":
            _lines.append(f'{pad}__nc_gc_collect();')
            _expr_indent[0] = old_indent
            return
        if isinstance(expr, FunctionCall) and expr.name == "gc_live":
            _lines.append(f'{pad}printf("%d\\n", (int)__nc_gc_live());')
            _expr_indent[0] = old_indent
            return
        if isinstance(expr, FunctionCall) and expr.name == "write_file":
            path = expr.args[0]
            content = expr.args[1]
            path_c = f'"{path.value}"' if isinstance(path, StringLiteral) else f'{gen_expr(path)}.ptr'
            _lines.append(f'{pad}__nc_write_file({path_c}, {gen_expr(content)});')
            _expr_indent[0] = old_indent
            return
        if isinstance(expr, FunctionCall) and expr.name == "print":
            arg = expr.args[0]
            arg_type = getattr(arg, "type", "i32")
            if arg_type == "str":
                arg_c = gen_expr(arg)
                _lines.append(f'{pad}printf("%.*s\\n", (int)({arg_c}).len, ({arg_c}).ptr);')
            elif arg_type == "bool":
                _lines.append(f'{pad}printf("%d\\n", {gen_expr(arg)});')
            else:
                _lines.append(f'{pad}printf("%d\\n", {gen_expr(arg)});')
        else:
            _lines.append(f'{pad}{gen_expr(expr)};')
        _expr_indent[0] = old_indent

    def block_tail_expr(block):
        if not block.statements:
            return None
        last = block.statements[-1]
        if isinstance(last, ExpressionStatement):
            return last.expr
        return None

    def block_tail_if(block):
        if not block.statements:
            return None
        last = block.statements[-1]
        if isinstance(last, If):
            return last
        return None

    def gen_block_value_assign(block, target, indent):
        tail = block_tail_expr(block)
        tail_if = block_tail_if(block)
        body = block.statements[:-1] if (tail or tail_if) else block.statements
        for s in body:
            gen_stmt(s, indent)
        if tail_if is not None:
            gen_if_tail_assign(tail_if, target, indent)
            return
        if isinstance(tail, IfExpr):
            gen_ifexpr_assign(tail, target, indent)
            return
        _lines.append(f'{"    " * indent}{target} = {gen_expr(tail)};')

    def gen_block_value_return(block, indent):
        tail = block_tail_expr(block)
        tail_if = block_tail_if(block)
        body = block.statements[:-1] if (tail or tail_if) else block.statements
        for s in body:
            gen_stmt(s, indent)
        if tail_if is not None:
            gen_if_tail_return(tail_if, indent)
            return
        if isinstance(tail, IfExpr):
            gen_ifexpr_return(tail, indent)
            return
        emit_return_expr(tail, indent)

    def gen_ifexpr_assign(expr, target, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(expr.condition)}) {{')
        gen_block_value_assign(expr.then_block, target, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_assign(expr.else_block, target, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_if_tail_assign(stmt, target, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(stmt.condition)}) {{')
        gen_block_value_assign(stmt.then_block, target, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_assign(stmt.else_block, target, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_ifexpr_return(expr, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(expr.condition)}) {{')
        gen_block_value_return(expr.then_block, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_return(expr.else_block, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_if_tail_return(stmt, indent):
        pad = '    ' * indent
        _lines.append(f'{pad}if ({gen_expr(stmt.condition)}) {{')
        gen_block_value_return(stmt.then_block, indent + 1)
        _lines.append(f'{pad}}} else {{')
        gen_block_value_return(stmt.else_block, indent + 1)
        _lines.append(f'{pad}}}')

    def gen_stmt(stmt, indent=1):
        old_indent = _expr_indent[0]
        _expr_indent[0] = indent
        pad = '    ' * indent

        if isinstance(stmt, (StructDecl, EnumDecl)):
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, VariableDeclaration):
            if isinstance(stmt.initializer, ArrayLiteral):
                arr = stmt.initializer
                c_et = _type_to_c(arr.elem_type)
                elems = ', '.join(gen_expr(e) for e in arr.elements)
                _lines.append(f'{pad}{c_et} {stmt.name}[{arr.length}] = {{{elems}}};')
            elif isinstance(stmt.initializer, SliceLiteral):
                sl = stmt.initializer
                c_t = _type_to_c(stmt.type)
                elem_c = _type_to_c(sl.elem_type)
                n = len(sl.elements)
                _lines.append(f'{pad}{c_t} {stmt.name} = {{0, 0, 0}};')
                if n:
                    _lines.append(f'{pad}{stmt.name}.ptr = ({elem_c}*)__nc_gc_alloc({n} * sizeof({elem_c}));')
                    _lines.append(f'{pad}{stmt.name}.len = {n}; {stmt.name}.cap = {n};')
                    for i, elem in enumerate(sl.elements):
                        _lines.append(f'{pad}{stmt.name}.ptr[{i}] = {gen_expr(elem)};')
                    _gc_vars[stmt.name] = stmt.type
                    _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
            elif isinstance(stmt.initializer, SliceExpr):
                c_t = _type_to_c(stmt.type)
                _lines.append(f'{pad}{c_t} {stmt.name} = {gen_expr(stmt.initializer)};')
                _gc_vars[stmt.name] = stmt.type
                _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
            elif isinstance(stmt.initializer, IfExpr):
                c_t = _type_to_c(stmt.type)
                _lines.append(f'{pad}{c_t} {stmt.name};')
                gen_ifexpr_assign(stmt.initializer, stmt.name, indent)
                if stmt.type == "str":
                    _gc_vars[stmt.name] = "str"
                    _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
                elif isinstance(stmt.type, str) and stmt.type.startswith("[]"):
                    _gc_vars[stmt.name] = stmt.type
                    _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
            else:
                c_t = _type_to_c(stmt.type)
                # 堆分配: let s = new Struct{...}
                if isinstance(stmt.initializer, StructLiteral) and stmt.initializer.heap:
                    sname = stmt.initializer.name
                    _lines.append(f'{pad}{c_t} {stmt.name} = ({sname}*)__nc_gc_alloc(sizeof({sname}));')
                    for fname, fval in stmt.initializer.fields:
                        _lines.append(f'{pad}{stmt.name}->{fname} = {gen_expr(fval)};')
                    _gc_vars[stmt.name] = stmt.name  # 指针自身即根
                    _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name});')
                else:
                    init_c = gen_expr(stmt.initializer)
                    if stmt.type == "nc_map":
                        _lines.append(f'{pad}{c_t} {stmt.name}; __nc_map_init(&{stmt.name});')
                        _gc_vars[stmt.name] = "nc_map"
                    else:
                        _lines.append(f'{pad}{c_t} {stmt.name} = {init_c};')
                        if stmt.type == "str":
                            _gc_vars[stmt.name] = "str"
                        elif isinstance(stmt.type, str) and stmt.type.startswith("[]"):
                            _gc_vars[stmt.name] = stmt.type
                    # GC 根追踪（str/nc_map/slice）
                    if stmt.type == "nc_map":
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.entries);')
                    elif stmt.type == "str":
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
                    elif isinstance(stmt.type, str) and stmt.type.startswith("[]"):
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.name}.ptr);')
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, Identifier):
                _lines.append(f'{pad}{stmt.target.name} = {gen_expr(stmt.expr)};')
                # GC 根刷新
                if stmt.target.name in _gc_vars:
                    var_t = _gc_vars[stmt.target.name]
                    if var_t == "nc_map":
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.target.name}.entries);')
                    elif var_t == "str":
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.target.name}.ptr);')
                    elif isinstance(var_t, str) and var_t.startswith("[]"):
                        _lines.append(f'{pad}__nc_gc_push_root((void*){stmt.target.name}.ptr);')
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
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, ExpressionStatement):
            gen_expr_stmt(stmt.expr, indent)
            _expr_indent[0] = old_indent
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
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, While):
            cond_c = gen_expr(stmt.condition)
            _lines.append(f'{pad}while ({cond_c}) {{')
            for s in stmt.body.statements:
                gen_stmt(s, indent + 1)
            _lines.append(f'{pad}}}')
            _expr_indent[0] = old_indent
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
            _expr_indent[0] = old_indent
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
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Return):
            if stmt.expr:
                emit_return_expr(stmt.expr, indent)
            else:
                emit_return_void(indent)
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Block):
            for s in stmt.statements:
                gen_stmt(s, indent)
            _expr_indent[0] = old_indent
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
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Throw):
            pad = '    ' * indent
            ex_c = gen_expr(stmt.expr)
            emit_deferred(indent)
            _lines.append(f'{pad}__nc_throw({ex_c});')
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Defer):
            if _emitting_defer[0]:
                for s in stmt.body.statements:
                    gen_stmt(s, indent)
            else:
                _defer_stack.append(stmt.body)
            _expr_indent[0] = old_indent
            return
        if isinstance(stmt, Break):
            pad = '    ' * indent
            _lines.append(f'{pad}break;')
            _expr_indent[0] = old_indent
            return
        raise NotImplementedError(f"gen_stmt: {type(stmt).__name__}")

    # ——— 前向声明（支持互递归） ———
    for func in other_funcs:
        c_ret = _type_to_c(func.return_type or "void")
        if func.receiver_name:
            rtype = func.receiver_type.lstrip("*")
            fname = f"{rtype}_{func.name}"
            all_params = [(func.receiver_name, func.receiver_type)] + func.params
        else:
            fname = func.name
            all_params = func.params
        params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in all_params) or "void"
        _lines.append(f'{c_ret} {fname}({params_c});')
    if other_funcs:
        _lines.append('')

    # ——— 输出函数 ———
    for func in other_funcs:
        _gc_vars.clear()  # 每函数独立的 GC 变量
        _defer_stack.clear()
        c_ret = _type_to_c(func.return_type or "void")
        _return_type[0] = c_ret
        _return_label[0] = "__nc_return"
        _return_var[0] = "__nc_ret"
        if func.receiver_name:
            rtype = func.receiver_type.lstrip("*")
            fname = f"{rtype}_{func.name}"
            all_params = [(func.receiver_name, func.receiver_type)] + func.params
        else:
            fname = func.name
            all_params = func.params
        params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in all_params) or "void"
        _lines.append(f'{c_ret} {fname}({params_c}) {{')
        _lines.append('    size_t __nc_gc_mark = __nc_gc_root_mark();')
        if c_ret != "void":
            _lines.append(f'    {c_ret} __nc_ret;')
        for i, s in enumerate(func.body.statements):
            if i == len(func.body.statements) - 1 and (func.return_type or "void") != "void":
                if isinstance(s, ExpressionStatement):
                    emit_return_expr(s.expr, 1)
                    continue
                if isinstance(s, If):
                    gen_if_tail_return(s, 1)
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
        _gc_vars.clear()
        _defer_stack.clear()
        _return_type[0] = "int"
        _return_label[0] = "__nc_main_return"
        _return_var[0] = "__nc_ret"
        _lines.append('int main(void) {')
        _lines.append('    __nc_gc_init();')
        _lines.append('    size_t __nc_gc_mark = __nc_gc_root_mark();')
        _lines.append('    int __nc_ret = 0;')
        for i, s in enumerate(main_func.body.statements):
            if i == len(main_func.body.statements) - 1 and (main_func.return_type or "void") != "void":
                if isinstance(s, ExpressionStatement):
                    emit_return_expr(s.expr, 1)
                    continue
                if isinstance(s, If):
                    gen_if_tail_return(s, 1)
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

