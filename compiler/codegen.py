"""
代码生成 —— Pass 3：按序遍历 Typed AST，就地生成 C 代码。
struct/enum 定义提升到文件作用域，fun main() 映射为 int main(void)。
str 是胖指针 {ptr, len}，打印用 %.*s。
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
    if nc_type.startswith("[]"):
        return _slice_type_name(nc_type[2:])
    if nc_type.startswith("*"):
        return _type_to_c(nc_type[1:]) + "*"
    return NC_TO_C.get(nc_type, nc_type)


def _c_ident(name: str) -> str:
    return name.replace("*", "ptr_").replace("[]", "slice_").replace("[", "arr_").replace("]", "_")


def _slice_type_name(elem_type: str) -> str:
    return f'nc_slice_{_c_ident(elem_type)}'


def _slice_append_name(elem_type: str) -> str:
    return f'__nc_append_{_c_ident(elem_type)}'


def _slice_copy_name(elem_type: str) -> str:
    return f'__nc_slice_copy_{_c_ident(elem_type)}'


def generate_c(program: "Program") -> str:
    from compiler.ast import (
        FunctionDeclaration, StructDecl, EnumDecl, Switch, ForIn, Block, If, While,
        VariableDeclaration, ExpressionStatement, Assignment,
        Return, SliceExpr, ArrayLiteral, SliceLiteral, FunctionCall,
        IntegerLiteral, StringLiteral, BoolLiteral, Identifier, BinaryOp, UnaryOp,
        EnumRef, StructLiteral, FieldAccess, IndexAccess, SliceExpr, MethodCall,
        TryCatch, Throw, Defer, Break
    )

    _lines = []
    _slice_types = set()
    _gc_vars = {}  # 变量名 → 类型 (str/nc_map) 用于 GC 根追踪

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

    # ——— 输出头部 + 类型定义 ———
    _lines.append('#include <stdio.h>')
    _lines.append('#include <stdlib.h>')
    _lines.append('#include <string.h>')
    _lines.append('#include <stdint.h>')
    _lines.append('')
    _lines.append('// === nc_gc.h inline ===')
    _lines.append('typedef struct _nc_record { void* ptr; size_t size; uint8_t marked; struct _nc_record* next; } nc_record_t;')
    _lines.append('static nc_record_t* __nc_gc_registry = NULL;')
    _lines.append('static struct { void* ptr; int active; } __nc_gc_roots[256];')
    _lines.append('static size_t __nc_gc_root_n = 0;')
    _lines.append('static nc_record_t* __nc_gc_gray[4096];')
    _lines.append('static size_t __nc_gc_gray_top = 0;')
    _lines.append('static int __nc_gc_is_heap(void* c) {')
    _lines.append('    if (!c) return 0;')
    _lines.append('    uintptr_t a = (uintptr_t)c;')
    _lines.append('    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)')
    _lines.append('        if (a >= (uintptr_t)r->ptr && a < (uintptr_t)r->ptr + r->size) return 1;')
    _lines.append('    return 0; }')
    _lines.append('static nc_record_t* __nc_gc_find(void* p) {')
    _lines.append('    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)')
    _lines.append('        if (p >= r->ptr && (uintptr_t)p < (uintptr_t)r->ptr + r->size) return r;')
    _lines.append('    return NULL; }')
    _lines.append('static void __nc_gc_mark_gray(void* p) {')
    _lines.append('    nc_record_t* r = __nc_gc_find(p);')
    _lines.append('    if (r && r->marked == 0) { r->marked = 1; if (__nc_gc_gray_top < 4096) __nc_gc_gray[__nc_gc_gray_top++] = r; } }')
    _lines.append('static void __nc_gc_scan(nc_record_t* r) {')
    _lines.append('    size_t n = r->size / sizeof(void*); void** w = (void**)r->ptr;')
    _lines.append('    for (size_t i = 0; i < n; i++) if (w[i]) __nc_gc_mark_gray(w[i]); }')
    _lines.append('static void* __nc_gc_alloc(size_t sz) {')
    _lines.append('    void* p = calloc(1, sz); if (!p) return NULL;')
    _lines.append('    nc_record_t* rec = (nc_record_t*)malloc(sizeof(nc_record_t));')
    _lines.append('    rec->ptr = p; rec->size = sz; rec->marked = 0;')
    _lines.append('    rec->next = __nc_gc_registry; __nc_gc_registry = rec; return p; }')
    _lines.append('static int __nc_gc_push_root(void* p) {')
    _lines.append('    if (!p || !__nc_gc_is_heap(p)) return -1;')
    _lines.append('    if (__nc_gc_root_n >= 256) return -1;')
    _lines.append('    __nc_gc_roots[__nc_gc_root_n].ptr = p;')
    _lines.append('    __nc_gc_roots[__nc_gc_root_n].active = 1;')
    _lines.append('    return (int)__nc_gc_root_n++; }')
    _lines.append('static void __nc_gc_pop_root(void) { if (__nc_gc_root_n > 0) __nc_gc_root_n--; }')
    _lines.append('static void __nc_gc_drop_root(int h) { if (h>=0 && h<(int)__nc_gc_root_n) __nc_gc_roots[h].active=0; }')
    _lines.append('static void __nc_gc_collect(void) {')
    _lines.append('    for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_mark_gray(__nc_gc_roots[i].ptr);')
    _lines.append('    while (__nc_gc_gray_top > 0) { nc_record_t* r = __nc_gc_gray[--__nc_gc_gray_top]; __nc_gc_scan(r); r->marked = 2; }')
    _lines.append('    nc_record_t** prev = &__nc_gc_registry; nc_record_t* c = __nc_gc_registry;')
    _lines.append('    while (c) { if (c->marked == 0) { *prev = c->next; free(c->ptr); nc_record_t* d=c; c=c->next; free(d); }')
    _lines.append('        else { c->marked = 0; prev = &c->next; c = c->next; } }')
    _lines.append('    __nc_gc_gray_top = 0;')
    _lines.append('    size_t w = 0; for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_roots[w++] = __nc_gc_roots[i];')
    _lines.append('    __nc_gc_root_n = w; }')
    _lines.append('')
    _lines.append('typedef struct { uint8_t* ptr; uint64_t len; } str;')
    _lines.append('')
    _lines.append('static str __nc_read_file(const char* path) {')
    _lines.append('    FILE* fp = fopen(path, "rb");')
    _lines.append('    if (!fp) { str e = {NULL, 0}; return e; }')
    _lines.append('    fseek(fp, 0, SEEK_END);')
    _lines.append('    long long sz = ftell(fp);')
    _lines.append('    fseek(fp, 0, SEEK_SET);')
    _lines.append('    uint8_t* buf = (uint8_t*)__nc_gc_alloc(sz + 1);')
    _lines.append('    fread(buf, 1, sz, fp);')
    _lines.append('    buf[sz] = 0;')
    _lines.append('    fclose(fp);')
    _lines.append('    str r = {buf, (uint64_t)sz};')
    _lines.append('    return r;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_write_file(const char* path, str content) {')
    _lines.append('    FILE* fp = fopen(path, "w");')
    _lines.append('    if (!fp) return;')
    _lines.append('    fwrite(content.ptr, 1, content.len, fp);')
    _lines.append('    fclose(fp);')
    _lines.append('}')
    _lines.append('')
    _lines.append('static int __nc_str_eq(str a, str b) {')
    _lines.append('    if (a.len != b.len) return 0;')
    _lines.append('    return memcmp(a.ptr, b.ptr, a.len) == 0;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static str __nc_str_cat(str a, str b) {')
    _lines.append('    uint8_t* buf = (uint8_t*)__nc_gc_alloc(a.len + b.len + 1);')
    _lines.append('    memcpy(buf, a.ptr, a.len);')
    _lines.append('    memcpy(buf + a.len, b.ptr, b.len);')
    _lines.append('    buf[a.len + b.len] = 0;')
    _lines.append('    str r = {buf, a.len + b.len};')
    _lines.append('    return r;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static str __nc_str_slice_copy(str s, uint64_t start, uint64_t end) {')
    _lines.append('    uint64_t n = end - start;')
    _lines.append('    uint8_t* buf = (uint8_t*)__nc_gc_alloc(n + 1);')
    _lines.append('    if (n) memcpy(buf, s.ptr + start, n);')
    _lines.append('    buf[n] = 0;')
    _lines.append('    str r = {buf, n};')
    _lines.append('    return r;')
    _lines.append('}')
    _lines.append('')
    for elem_type in sorted(_slice_types):
        slice_name = _slice_type_name(elem_type)
        elem_c = _type_to_c(elem_type)
        append_name = _slice_append_name(elem_type)
        copy_name = _slice_copy_name(elem_type)
        _lines.append(f'typedef struct {{ {elem_c}* ptr; uint64_t len; uint64_t cap; }} {slice_name};')
        _lines.append('')
        _lines.append(f'static {slice_name} {copy_name}({elem_c}* src, uint64_t len) {{')
        _lines.append(f'    {slice_name} s = {{0, 0, 0}};')
        _lines.append('    if (len) {')
        _lines.append(f'        s.ptr = ({elem_c}*)__nc_gc_alloc(len * sizeof({elem_c}));')
        _lines.append('        memcpy(s.ptr, src, len * sizeof(*s.ptr));')
        _lines.append('    }')
        _lines.append('    s.len = len; s.cap = len;')
        _lines.append('    return s;')
        _lines.append('}')
        _lines.append('')
        _lines.append(f'static {slice_name} {append_name}({slice_name} s, {elem_c} elem) {{')
        _lines.append('    if (s.len >= s.cap) {')
        _lines.append('        uint64_t nc = s.cap ? s.cap * 2 : 4;')
        _lines.append(f'        {elem_c}* np = ({elem_c}*)__nc_gc_alloc(nc * sizeof({elem_c}));')
        _lines.append('        if (s.ptr) memcpy(np, s.ptr, s.len * sizeof(*np));')
        _lines.append('        s.ptr = np; s.cap = nc;')
        _lines.append('    }')
        _lines.append('    s.ptr[s.len++] = elem;')
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
    _lines.append('    for (long long i = 0; i < key.len; i++) {')
    _lines.append('        h ^= (unsigned char)key.ptr[i]; h *= 1099511628211ULL; }')
    _lines.append('    return (long long)(h % (unsigned long long)cap);')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_init(nc_map* m) {')
    _lines.append('    m->cap = 16; m->len = 0; m->tombstones = 0;')
    _lines.append('    m->entries = (nc_entry*)__nc_gc_alloc(16 * sizeof(nc_entry));')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_free(nc_map* m) {')
    _lines.append('    free(m->entries); m->entries = 0; m->cap = 0; m->len = 0; m->tombstones = 0;')
    _lines.append('}')
    _lines.append('')
    _lines.append('static void __nc_map_rehash(nc_map* m) {')
    _lines.append('    long long oc = m->cap; nc_entry* old = m->entries;')
    _lines.append('    m->cap *= 2; m->len = 0; m->tombstones = 0;')
    _lines.append('    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * sizeof(nc_entry));')
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
    _lines.append('        if (m->entries[idx].state == 1 && key.len == m->entries[idx].key.len && __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, key.len)) {')
    _lines.append('            m->entries[idx].value = value; return; }')
    _lines.append('        idx = (idx + 1) % m->cap; } }')
    _lines.append('')
    _lines.append('static int __nc_map_get(const nc_map* m, str key, nc_val* out) {')
    _lines.append('    if (!m->cap) return 0;')
    _lines.append('    long long idx = __nc_map_hash(key, m->cap);')
    _lines.append('    for (long long i = 0; i < m->cap; i++) {')
    _lines.append('        if (m->entries[idx].state == 0) return 0;')
    _lines.append('        if (m->entries[idx].state == 1 && key.len == m->entries[idx].key.len && __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, key.len)) {')
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
    _lines.append('    uint8_t* buf = (uint8_t*)__nc_gc_alloc(24);')
    _lines.append('    int len = sprintf(buf, "%d", n);')
    _lines.append('    return (str){buf, len}; }')
    _lines.append('')
    _lines.append('static int __nc_str_to_i32(str s) {')
    _lines.append('    return atoi((const char*)s.ptr); }')
    _lines.append('')

    _lines.append('static void __nc_gc_init(void) {')
    _lines.append('    __nc_gc_registry = NULL; __nc_gc_root_n = 0; __nc_gc_gray_top = 0; }')
    _lines.append('')
    _lines.append('static size_t __nc_gc_live(void) {')
    _lines.append('    size_t n = 0;')
    _lines.append('    for (nc_record_t* r = __nc_gc_registry; r; r = r->next) n++;')
    _lines.append('    return n; }')
    _lines.append('')
    _lines.append('#include <setjmp.h>')
    _lines.append('typedef struct __nc_ex_frame { jmp_buf jb; struct __nc_ex_frame* prev; str ex; } __nc_ex_frame_t;')
    _lines.append('static __nc_ex_frame_t* __nc_ex_top = NULL;')
    _lines.append('static void __nc_throw(str ex) {')
    _lines.append('    if (__nc_ex_top) { __nc_ex_top->ex = ex; longjmp(__nc_ex_top->jb, 1); }')
    _lines.append('    fprintf(stderr, "uncaught: %.*s\\n", (int)ex.len, ex.ptr); exit(1); }')
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
        pad = '    ' * indent
        if isinstance(expr, FunctionCall) and expr.name == "gc_collect":
            _lines.append(f'{pad}__nc_gc_collect();')
            return
        if isinstance(expr, FunctionCall) and expr.name == "gc_live":
            _lines.append(f'{pad}printf("%d\n", (int)__nc_gc_live());')
            return
        if isinstance(expr, FunctionCall) and expr.name == "write_file":
            path = expr.args[0]
            content = expr.args[1]
            path_c = f'"{path.value}"' if isinstance(path, StringLiteral) else f'{gen_expr(path)}.ptr'
            _lines.append(f'{pad}__nc_write_file({path_c}, {gen_expr(content)});')
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
            return
        if isinstance(stmt, Throw):
            pad = '    ' * indent
            ex_c = gen_expr(stmt.expr)
            _lines.append(f'{pad}__nc_throw({ex_c});')
            return
        if isinstance(stmt, Defer):
            for s in stmt.body.statements:
                gen_stmt(s, indent)
            return
        if isinstance(stmt, Break):
            pad = '    ' * indent
            _lines.append(f'{pad}break;')
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
        c_ret = _type_to_c(func.return_type or "void")
        if func.receiver_name:
            rtype = func.receiver_type.lstrip("*")
            fname = f"{rtype}_{func.name}"
            all_params = [(func.receiver_name, func.receiver_type)] + func.params
        else:
            fname = func.name
            all_params = func.params
        params_c = ', '.join(f'{_type_to_c(t)} {n}' for n, t in all_params) or "void"
        _lines.append(f'{c_ret} {fname}({params_c}) {{')
        for s in func.body.statements:
            gen_stmt(s)
        # 函数退出：弹出所有 GC 根
        for _ in _gc_vars:
            _lines.append('    __nc_gc_pop_root();')
        _lines.append('}')

    if main_func:
        _gc_vars.clear()
        _lines.append('int main(void) {')
        _lines.append('    __nc_gc_init();')
        for s in main_func.body.statements:
            gen_stmt(s)
        for _ in _gc_vars:
            _lines.append('    __nc_gc_pop_root();')
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

