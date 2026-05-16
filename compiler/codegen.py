"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct/enum 定义提升到文件作用域，fun main() 映射为 int main(void)。
str 是胖指针 {_ptr, _len}，打印用 %.*s。
所有生成函数内闭于 generate_c。
"""

NC_TO_C = {
    "i32": "int", "i64": "long long",
    "u32": "unsigned int", "u64": "unsigned long long",
    "f32": "float", "f64": "double",
    "bool": "int", "void": "void",
    "str": "str",  # 指 typedef str，非 const char*
}


def _type_to_c(nc_type: str) -> str:
    return NC_TO_C.get(nc_type, nc_type)


def generate_c(program: "Program") -> str:
    from compiler.ast import (
        FunctionDeclaration, StructDecl, EnumDecl, Switch, ForIn, Block, If, While,
        VariableDeclaration, ExpressionStatement, Assignment,
        Return, SliceExpr, ArrayLiteral, FunctionCall,
        IntegerLiteral, StringLiteral, Identifier, BinaryOp, UnaryOp,
        EnumRef, StructLiteral, FieldAccess, IndexAccess, SliceExpr,
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
            elif isinstance(s, ForIn):
                collect(s.body.statements)

    collect(program.statements)

    top_stmts = [s for s in program.statements
                 if not isinstance(s, (FunctionDeclaration, StructDecl, EnumDecl))]

    # ——— 输出头部 + 类型定义 ———
    _lines.append('#include <stdio.h>')
    _lines.append('#include <stdlib.h>')
    _lines.append('#include <string.h>')
    _lines.append('')
    _lines.append('typedef struct { const char* _ptr; long long _len; } str;')
    _lines.append('')
    _lines.append('static str __nc_read_file(const char* path) {')
    _lines.append('    FILE* fp = fopen(path, "rb");')
    _lines.append('    if (!fp) { str e = {NULL, 0}; return e; }')
    _lines.append('    fseek(fp, 0, SEEK_END);')
    _lines.append('    long long sz = ftell(fp);')
    _lines.append('    fseek(fp, 0, SEEK_SET);')
    _lines.append('    char* buf = (char*)malloc(sz + 1);')
    _lines.append('    fread(buf, 1, sz, fp);')
    _lines.append('    buf[sz] = 0;')
    _lines.append('    fclose(fp);')
    _lines.append('    str r = {(const char*)buf, sz};')
    _lines.append('    return r;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_write_file(const char* path, str content) {')
    _lines.append('    FILE* fp = fopen(path, "w");')
    _lines.append('    if (!fp) return;')
    _lines.append('    fwrite(content._ptr, 1, content._len, fp);')
    _lines.append('    fclose(fp);')
    _lines.append('}')
    _lines.append('')
    _lines.append('static int __nc_str_eq(str a, str b) {')
    _lines.append('    if (a._len != b._len) return 0;')
    _lines.append('    return strncmp(a._ptr, b._ptr, a._len) == 0;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static str __nc_str_cat(str a, str b) {')
    _lines.append('    char* buf = (char*)malloc(a._len + b._len + 1);')
    _lines.append('    memcpy(buf, a._ptr, a._len);')
    _lines.append('    memcpy(buf + a._len, b._ptr, b._len);')
    _lines.append('    buf[a._len + b._len] = 0;')
    _lines.append('    str r = {(const char*)buf, a._len + b._len};')
    _lines.append('    return r;')
    _lines.append('}')
    _lines.append('')
    _lines.append('typedef struct { int* _ptr; long long _len; long long _cap; } _slice_int;')
    _lines.append('')
    _lines.append('static _slice_int __nc_append_int(_slice_int s, int elem) {')
    _lines.append('    if (s._len >= s._cap) {')
    _lines.append('        long long nc = s._cap ? s._cap * 2 : 4;')
    _lines.append('        int* np = (int*)malloc(nc * sizeof(int));')
    _lines.append('        for (long long i = 0; i < s._len; i++) np[i] = s._ptr[i];')
    _lines.append('        s._ptr = np; s._cap = nc;')
    _lines.append('    }')
    _lines.append('    s._ptr[s._len++] = elem;')
    _lines.append('    return s;')
    _lines.append('}')
    _lines.append('')

    # ——— nc_map 哈希表（内联自 nc_hashmap.c） ———
    _lines.append('typedef enum { NC_VAL_NIL = 0, NC_VAL_I32, NC_VAL_STR, NC_VAL_PTR } nc_val_tag;')
    _lines.append('typedef struct { nc_val_tag tag; union { long long i; str s; void* p; }; } nc_val;')
    _lines.append('typedef struct { str key; nc_val value; int state; } nc_entry;')
    _lines.append('typedef struct { nc_entry* entries; long long cap; long long len; long long tombstones; } nc_map;')
    _lines.append('')
    _lines.append('static int __nc_str_bytes_eq(const char* a, const char* b, long long n) {')
    _lines.append('    for (long long i = 0; i < n; i++) if (a[i] != b[i]) return 0;')
    _lines.append('    return 1;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static long long __nc_map_hash(str key, long long cap) {')
    _lines.append('    unsigned long long h = 14695981039346656037ULL;')
    _lines.append('    for (long long i = 0; i < key._len; i++) {')
    _lines.append('        h ^= (unsigned char)key._ptr[i]; h *= 1099511628211ULL; }')
    _lines.append('    return (long long)(h % (unsigned long long)cap);')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_init(nc_map* m) {')
    _lines.append('    m->cap = 16; m->len = 0; m->tombstones = 0;')
    _lines.append('    m->entries = (nc_entry*)calloc(16, sizeof(nc_entry));')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_free(nc_map* m) {')
    _lines.append('    free(m->entries); m->entries = 0; m->cap = 0; m->len = 0; m->tombstones = 0;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_rehash(nc_map* m) {')
    _lines.append('    long long oc = m->cap; nc_entry* old = m->entries;')
    _lines.append('    m->cap *= 2; m->len = 0; m->tombstones = 0;')
    _lines.append('    m->entries = (nc_entry*)calloc((size_t)m->cap, sizeof(nc_entry));')
    _lines.append('    for (long long i = 0; i < oc; i++) {')
    _lines.append('        if (old[i].state == 1) {')
    _lines.append('            long long idx = __nc_map_hash(old[i].key, m->cap);')
    _lines.append('            for (long long j = 0; j < m->cap; j++) {')
    _lines.append('                if (m->entries[idx].state == 0) { m->entries[idx] = old[i]; break; }')
    _lines.append('                idx = (idx + 1) % m->cap; } } }')
    _lines.append('    free(old);')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_put(nc_map* m, str key, nc_val value) {')
    _lines.append('    if (m->cap && (double)(m->len + m->tombstones) / (double)m->cap > 0.70) __nc_map_rehash(m);')
    _lines.append('    long long idx = __nc_map_hash(key, m->cap);')
    _lines.append('    long long tomb = -1;')
    _lines.append('    for (long long i = 0; i < m->cap; i++) {')
    _lines.append('        if (m->entries[idx].state == 0) {')
    _lines.append('            long long put_at = (tomb >= 0) ? tomb : idx;')
    _lines.append('            m->entries[put_at].key = key; m->entries[put_at].value = value;')
    _lines.append('            m->entries[put_at].state = 1; m->len++;')
    _lines.append('            if (tomb >= 0) m->tombstones--;')
    _lines.append('            return; }')
    _lines.append('        if (m->entries[idx].state == 2 && tomb < 0) tomb = idx;')
    _lines.append('        if (m->entries[idx].state == 1 && key._len == m->entries[idx].key._len && __nc_str_bytes_eq(key._ptr, m->entries[idx].key._ptr, key._len)) {')
    _lines.append('            m->entries[idx].value = value; return; }')
    _lines.append('        idx = (idx + 1) % m->cap; } }')
    _lines.append('')
    _lines.append('static int __nc_map_get(const nc_map* m, str key, nc_val* out) {')
    _lines.append('    if (!m->cap) return 0;')
    _lines.append('    long long idx = __nc_map_hash(key, m->cap);')
    _lines.append('    for (long long i = 0; i < m->cap; i++) {')
    _lines.append('        if (m->entries[idx].state == 0) return 0;')
    _lines.append('        if (m->entries[idx].state == 1 && key._len == m->entries[idx].key._len && __nc_str_bytes_eq(key._ptr, m->entries[idx].key._ptr, key._len)) {')
    _lines.append('            *out = m->entries[idx].value; return 1; }')
    _lines.append('        idx = (idx + 1) % m->cap; }')
    _lines.append('    return 0; }')
    _lines.append('')
    _lines.append('static void __nc_map_set_str(nc_map* m, str key, str value) {')
    _lines.append('    __nc_map_put(m, key, (nc_val){.tag = NC_VAL_STR, .s = value}); }')
    _lines.append('')
    _lines.append('static str __nc_map_get_str(nc_map* m, str key) {')
    _lines.append('    nc_val v;')
    _lines.append('    if (__nc_map_get(m, key, &v) && v.tag == NC_VAL_STR) return v.s;')
    _lines.append('    return (str){0, 0}; }')
    _lines.append('')
    _lines.append('static int __nc_map_has(nc_map* m, str key) {')
    _lines.append('    nc_val v; return __nc_map_get(m, key, &v); }')
    _lines.append('')
    _lines.append('static str __nc_i32_to_str(int n) {')
    _lines.append('    char* buf = (char*)malloc(24);')
    _lines.append('    int len = sprintf(buf, "%d", n);')
    _lines.append('    return (str){buf, len}; }')
    _lines.append('')
    _lines.append('static int __nc_str_to_i32(str s) {')
    _lines.append('    return atoi(s._ptr); }')
    _lines.append('')

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
    def gen_expr(node) -> str:
        if isinstance(node, IntegerLiteral):
            return str(node.value)
        if isinstance(node, StringLiteral):
            esc = node.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'(str){{"{esc}", {len(node.value)}}}'
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
                return f'__nc_read_file({arg_c}._ptr)'
            if node.name == "append":
                slice_c = gen_expr(node.args[0])
                elem_c = gen_expr(node.args[1])
                return f'__nc_append_int({slice_c}, {elem_c})'
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
        if isinstance(node, StructLiteral):
            vals = ', '.join(gen_expr(v) for _n, v in node.fields)
            return f'({node.name}){{{vals}}}'
        if isinstance(node, FieldAccess):
            return f'{gen_expr(node.obj)}.{node.field}'
        if isinstance(node, IndexAccess):
            obj_c = gen_expr(node.obj)
            idx_c = gen_expr(node.index)
            obj_type = getattr(node.obj, "type", "")
            if obj_type == "nc_map":
                return f'__nc_map_get_str(&{obj_c}, {idx_c})'
            if isinstance(node.obj, Identifier) and node.obj.name in _slice_vars:
                return f'{obj_c}._ptr[{idx_c}]'
            if obj_type == "str":
                return f'(int)(unsigned char)(({obj_c})._ptr[{idx_c}])'
            return f'{obj_c}[{idx_c}]'

        if isinstance(node, SliceExpr):
            arr_c = gen_expr(node.array)
            start_c = gen_expr(node.start) if node.start else '0'
            end_c = gen_expr(node.end) if node.end else f'{arr_c}._len'
            if getattr(node.array, "type", "") == "str":
                return f'(str){{{arr_c}._ptr + {start_c}, {end_c} - {start_c}}}'
            return f'({arr_c} + {start_c})'
        raise NotImplementedError(f"gen_expr: {type(node).__name__}")

    def gen_expr_stmt(expr, indent=0):
        pad = '    ' * indent
        if isinstance(expr, FunctionCall) and expr.name == "write_file":
            path = expr.args[0]
            content = expr.args[1]
            path_c = f'"{path.value}"' if isinstance(path, StringLiteral) else f'{gen_expr(path)}._ptr'
            _lines.append(f'{pad}__nc_write_file({path_c}, {gen_expr(content)});')
            return
        if isinstance(expr, FunctionCall) and expr.name == "print":
            arg = expr.args[0]
            arg_type = getattr(arg, "type", "i32")
            if arg_type == "str":
                arg_c = gen_expr(arg)
                _lines.append(f'{pad}printf("%.*s\\n", (int)({arg_c})._len, ({arg_c})._ptr);')
            else:
                _lines.append(f'{pad}printf("%d\\n", {gen_expr(arg)});')
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
                # str 切片 → str struct
                if getattr(se.array, "type", "") == "str":
                    arr_c = gen_expr(se.array)
                    start_c = gen_expr(se.start) if se.start else '0'
                    end_c = gen_expr(se.end) if se.end else f'{arr_c}._len'
                    _lines.append(f'{pad}str {stmt.name} = (str){{{arr_c}._ptr + {start_c}, {end_c} - {start_c}}};')
                    _slice_vars[stmt.name] = True
                else:
                    c_et = _type_to_c(stmt.type)
                    arr_c = gen_expr(se.array)
                    start_c = gen_expr(se.start) if se.start else '0'
                    end_c = gen_expr(se.end) if se.end else '0'
                    _lines.append(f'{pad}_slice_int {stmt.name} = {{{arr_c} + {start_c}, {end_c} - {start_c}, {end_c} - {start_c}}};')
                    _slice_vars[stmt.name] = True
            else:
                c_t = _type_to_c(stmt.type)
                init_c = gen_expr(stmt.initializer)
                if stmt.type == "nc_map":
                    _lines.append(f'{pad}{c_t} {stmt.name}; __nc_map_init(&{stmt.name});')
                else:
                    _lines.append(f'{pad}{c_t} {stmt.name} = {init_c};')
            return
        if isinstance(stmt, Assignment):
            if isinstance(stmt.target, Identifier):
                _lines.append(f'{pad}{stmt.target.name} = {gen_expr(stmt.expr)};')
            elif isinstance(stmt.target, IndexAccess):
                obj_c = gen_expr(stmt.target.obj)
                idx_c = gen_expr(stmt.target.index)
                obj_type = getattr(stmt.target.obj, "type", "")
                if obj_type == "nc_map":
                    _lines.append(f'{pad}__nc_map_set_str(&{obj_c}, {idx_c}, {gen_expr(stmt.expr)});')
                else:
                    _lines.append(f'{pad}{obj_c}[{idx_c}] = {gen_expr(stmt.expr)};')
            else:
                _lines.append(f'{pad}{gen_expr(stmt.target)} = {gen_expr(stmt.expr)};')
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
        if isinstance(stmt, ForIn):
            iter_c = gen_expr(stmt.iterable)
            _lines.append(f'{pad}for (int {stmt.index} = 0; {stmt.index} < {iter_c}._len; {stmt.index}++) {{')
            _lines.append(f'{pad}    int {stmt.value} = {iter_c}._ptr[{stmt.index}];')
            for s in stmt.body.statements:
                gen_stmt(s, indent + 1)
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

    # ——— 前向声明（支持互递归） ———
    for func in other_funcs:
        c_ret = _type_to_c(func.return_type or "void")
        params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in func.params) or "void"
        _lines.append(f'{c_ret} {func.name}({params_c});')
    if other_funcs:
        _lines.append('')

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
