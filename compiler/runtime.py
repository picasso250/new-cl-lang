"""Runtime C fragments emitted inline into generated C."""

from compiler.c_abi import slice_append_name, slice_copy_name, slice_type_name, type_to_c


def emit_prelude() -> list[str]:
    return [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "#include <stdint.h>",
        "",
    ]


def emit_gc() -> list[str]:
    return [
        "// === nc_gc.h inline ===",
        "typedef struct _nc_record { void* ptr; size_t size; uint8_t marked; struct _nc_record* next; } nc_record_t;",
        "static nc_record_t* __nc_gc_registry = NULL;",
        "static struct { void* ptr; int active; } __nc_gc_roots[256];",
        "static size_t __nc_gc_root_n = 0;",
        "static nc_record_t* __nc_gc_gray[4096];",
        "static size_t __nc_gc_gray_top = 0;",
        "static int __nc_gc_is_heap(void* c) {",
        "    if (!c) return 0;",
        "    uintptr_t a = (uintptr_t)c;",
        "    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)",
        "        if (a >= (uintptr_t)r->ptr && a < (uintptr_t)r->ptr + r->size) return 1;",
        "    return 0; }",
        "static nc_record_t* __nc_gc_find(void* p) {",
        "    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)",
        "        if (p >= r->ptr && (uintptr_t)p < (uintptr_t)r->ptr + r->size) return r;",
        "    return NULL; }",
        "static void __nc_gc_mark_gray(void* p) {",
        "    nc_record_t* r = __nc_gc_find(p);",
        "    if (r && r->marked == 0) { r->marked = 1; if (__nc_gc_gray_top < 4096) __nc_gc_gray[__nc_gc_gray_top++] = r; } }",
        "static void __nc_gc_scan(nc_record_t* r) {",
        "    size_t n = r->size / sizeof(void*); void** w = (void**)r->ptr;",
        "    for (size_t i = 0; i < n; i++) if (w[i]) __nc_gc_mark_gray(w[i]); }",
        "static void* __nc_gc_alloc(size_t sz) {",
        "    void* p = calloc(1, sz); if (!p) return NULL;",
        "    nc_record_t* rec = (nc_record_t*)malloc(sizeof(nc_record_t));",
        "    rec->ptr = p; rec->size = sz; rec->marked = 0;",
        "    rec->next = __nc_gc_registry; __nc_gc_registry = rec; return p; }",
        "static int __nc_gc_push_root(void* p) {",
        "    if (!p || !__nc_gc_is_heap(p)) return -1;",
        "    if (__nc_gc_root_n >= 256) return -1;",
        "    __nc_gc_roots[__nc_gc_root_n].ptr = p;",
        "    __nc_gc_roots[__nc_gc_root_n].active = 1;",
        "    return (int)__nc_gc_root_n++; }",
        "static void __nc_gc_pop_root(void) { if (__nc_gc_root_n > 0) __nc_gc_root_n--; }",
        "static void __nc_gc_drop_root(int h) { if (h>=0 && h<(int)__nc_gc_root_n) __nc_gc_roots[h].active=0; }",
        "static size_t __nc_gc_root_mark(void) { return __nc_gc_root_n; }",
        "static void __nc_gc_root_rewind(size_t mark) {",
        "    if (mark <= __nc_gc_root_n) __nc_gc_root_n = mark; }",
        "static void __nc_gc_collect(void) {",
        "    for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_mark_gray(__nc_gc_roots[i].ptr);",
        "    while (__nc_gc_gray_top > 0) { nc_record_t* r = __nc_gc_gray[--__nc_gc_gray_top]; __nc_gc_scan(r); r->marked = 2; }",
        "    nc_record_t** prev = &__nc_gc_registry; nc_record_t* c = __nc_gc_registry;",
        "    while (c) { if (c->marked == 0) { *prev = c->next; free(c->ptr); nc_record_t* d=c; c=c->next; free(d); }",
        "        else { c->marked = 0; prev = &c->next; c = c->next; } }",
        "    __nc_gc_gray_top = 0;",
        "    size_t w = 0; for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_roots[w++] = __nc_gc_roots[i];",
        "    __nc_gc_root_n = w; }",
        "",
    ]


def emit_str() -> list[str]:
    return [
        "typedef struct { uint8_t* ptr; uint64_t len; } str;",
        "",
        "static str __nc_read_file(const char* path) {",
        '    FILE* fp = fopen(path, "rb");',
        "    if (!fp) { str e = {NULL, 0}; return e; }",
        "    fseek(fp, 0, SEEK_END);",
        "    long long sz = ftell(fp);",
        "    fseek(fp, 0, SEEK_SET);",
        "    uint8_t* buf = (uint8_t*)__nc_gc_alloc(sz + 1);",
        "    fread(buf, 1, sz, fp);",
        "    buf[sz] = 0;",
        "    fclose(fp);",
        "    str r = {buf, (uint64_t)sz};",
        "    return r;",
        "}",
        "",
        "static void __nc_write_file(const char* path, str content) {",
        '    FILE* fp = fopen(path, "w");',
        "    if (!fp) return;",
        "    fwrite(content.ptr, 1, content.len, fp);",
        "    fclose(fp);",
        "}",
        "",
        "static int __nc_str_eq(str a, str b) {",
        "    if (a.len != b.len) return 0;",
        "    return memcmp(a.ptr, b.ptr, a.len) == 0;",
        "}",
        "",
        "static str __nc_str_cat(str a, str b) {",
        "    uint8_t* buf = (uint8_t*)__nc_gc_alloc(a.len + b.len + 1);",
        "    memcpy(buf, a.ptr, a.len);",
        "    memcpy(buf + a.len, b.ptr, b.len);",
        "    buf[a.len + b.len] = 0;",
        "    str r = {buf, a.len + b.len};",
        "    return r;",
        "}",
        "",
        "static str __nc_str_slice_copy(str s, uint64_t start, uint64_t end) {",
        "    uint64_t n = end - start;",
        "    uint8_t* buf = (uint8_t*)__nc_gc_alloc(n + 1);",
        "    if (n) memcpy(buf, s.ptr + start, n);",
        "    buf[n] = 0;",
        "    str r = {buf, n};",
        "    return r;",
        "}",
        "",
    ]


def emit_slice(slice_types: set[str]) -> list[str]:
    lines = []
    for elem_type in sorted(slice_types):
        slice_name = slice_type_name(elem_type)
        elem_c = type_to_c(elem_type)
        append_name = slice_append_name(elem_type)
        copy_name = slice_copy_name(elem_type)
        lines.extend([
            f"typedef struct {{ {elem_c}* ptr; uint64_t len; uint64_t cap; }} {slice_name};",
            "",
            f"static {slice_name} {copy_name}({elem_c}* src, uint64_t len) {{",
            f"    {slice_name} s = {{0, 0, 0}};",
            "    if (len) {",
            f"        s.ptr = ({elem_c}*)__nc_gc_alloc(len * sizeof({elem_c}));",
            "        memcpy(s.ptr, src, len * sizeof(*s.ptr));",
            "    }",
            "    s.len = len; s.cap = len;",
            "    return s;",
            "}",
            "",
            f"static {slice_name} {append_name}({slice_name} s, {elem_c} elem) {{",
            "    if (s.len >= s.cap) {",
            "        uint64_t nc = s.cap ? s.cap * 2 : 4;",
            f"        {elem_c}* np = ({elem_c}*)__nc_gc_alloc(nc * sizeof({elem_c}));",
            "        if (s.ptr) memcpy(np, s.ptr, s.len * sizeof(*np));",
            "        s.ptr = np; s.cap = nc;",
            "    }",
            "    s.ptr[s.len++] = elem;",
            "    return s;",
            "}",
            "",
        ])
    return lines


def emit_map() -> list[str]:
    return [
        "typedef enum { NC_VAL_NIL = 0, NC_VAL_I32, NC_VAL_STR, NC_VAL_PTR } nc_val_tag;",
        "typedef struct { nc_val_tag tag; union { long long i; str s; void* p; }; } nc_val;",
        "typedef struct { str key; nc_val value; int state; } nc_entry;",
        "typedef struct { nc_entry* entries; long long cap; long long len; long long tombstones; } nc_map;",
        "",
        "static int __nc_str_bytes_eq(const char* a, const char* b, long long n) {",
        "    for (long long i = 0; i < n; i++) if (a[i] != b[i]) return 0;",
        "    return 1;",
        "}",
        "",
        "static long long __nc_map_hash(str key, long long cap) {",
        "    unsigned long long h = 14695981039346656037ULL;",
        "    for (long long i = 0; i < key.len; i++) {",
        "        h ^= (unsigned char)key.ptr[i]; h *= 1099511628211ULL; }",
        "    return (long long)(h % (unsigned long long)cap);",
        "}",
        "",
        "static void __nc_map_init(nc_map* m) {",
        "    m->cap = 16; m->len = 0; m->tombstones = 0;",
        "    m->entries = (nc_entry*)__nc_gc_alloc(16 * sizeof(nc_entry));",
        "}",
        "",
        "static void __nc_map_free(nc_map* m) {",
        "    free(m->entries); m->entries = 0; m->cap = 0; m->len = 0; m->tombstones = 0;",
        "}",
        "",
        "static void __nc_map_rehash(nc_map* m) {",
        "    long long oc = m->cap; nc_entry* old = m->entries;",
        "    m->cap *= 2; m->len = 0; m->tombstones = 0;",
        "    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * sizeof(nc_entry));",
        "    for (long long i = 0; i < oc; i++) {",
        "        if (old[i].state == 1) {",
        "            long long idx = __nc_map_hash(old[i].key, m->cap);",
        "            for (long long j = 0; j < m->cap; j++) {",
        "                if (m->entries[idx].state == 0) { m->entries[idx] = old[i]; break; }",
        "                idx = (idx + 1) % m->cap; } } }",
        "    free(old);",
        "}",
        "",
        "static void __nc_map_put(nc_map* m, str key, nc_val value) {",
        "    if (m->cap && (double)(m->len + m->tombstones) / (double)m->cap > 0.70) __nc_map_rehash(m);",
        "    long long idx = __nc_map_hash(key, m->cap);",
        "    long long tomb = -1;",
        "    for (long long i = 0; i < m->cap; i++) {",
        "        if (m->entries[idx].state == 0) {",
        "            long long put_at = (tomb >= 0) ? tomb : idx;",
        "            m->entries[put_at].key = key; m->entries[put_at].value = value;",
        "            m->entries[put_at].state = 1; m->len++;",
        "            if (tomb >= 0) m->tombstones--;",
        "            return; }",
        "        if (m->entries[idx].state == 2 && tomb < 0) tomb = idx;",
        "        if (m->entries[idx].state == 1 && key.len == m->entries[idx].key.len && __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, key.len)) {",
        "            m->entries[idx].value = value; return; }",
        "        idx = (idx + 1) % m->cap; } }",
        "",
        "static int __nc_map_get(const nc_map* m, str key, nc_val* out) {",
        "    if (!m->cap) return 0;",
        "    long long idx = __nc_map_hash(key, m->cap);",
        "    for (long long i = 0; i < m->cap; i++) {",
        "        if (m->entries[idx].state == 0) return 0;",
        "        if (m->entries[idx].state == 1 && key.len == m->entries[idx].key.len && __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, key.len)) {",
        "            *out = m->entries[idx].value; return 1; }",
        "        idx = (idx + 1) % m->cap; }",
        "    return 0; }",
        "",
        "static void __nc_map_set_str(nc_map* m, str key, str value) {",
        "    __nc_map_put(m, key, (nc_val){.tag = NC_VAL_STR, .s = value}); }",
        "",
        "static str __nc_map_get_str(nc_map* m, str key) {",
        "    nc_val v;",
        "    if (__nc_map_get(m, key, &v) && v.tag == NC_VAL_STR) return v.s;",
        "    return (str){0, 0}; }",
        "",
        "static int __nc_map_has(nc_map* m, str key) {",
        "    nc_val v; return __nc_map_get(m, key, &v); }",
        "",
    ]


def emit_cast() -> list[str]:
    return [
        "static str __nc_i32_to_str(int n) {",
        "    uint8_t* buf = (uint8_t*)__nc_gc_alloc(24);",
        '    int len = sprintf(buf, "%d", n);',
        "    return (str){buf, len}; }",
        "",
        "static int __nc_str_to_i32(str s) {",
        "    return atoi((const char*)s.ptr); }",
        "",
    ]


def emit_gc_helpers() -> list[str]:
    return [
        "static void __nc_gc_init(void) {",
        "    __nc_gc_registry = NULL; __nc_gc_root_n = 0; __nc_gc_gray_top = 0; }",
        "",
        "static size_t __nc_gc_live(void) {",
        "    size_t n = 0;",
        "    for (nc_record_t* r = __nc_gc_registry; r; r = r->next) n++;",
        "    return n; }",
        "",
    ]


def emit_exception() -> list[str]:
    return [
        "#include <setjmp.h>",
        "typedef struct __nc_ex_frame { jmp_buf jb; struct __nc_ex_frame* prev; str ex; } __nc_ex_frame_t;",
        "static __nc_ex_frame_t* __nc_ex_top = NULL;",
        "static void __nc_throw(str ex) {",
        '    if (__nc_ex_top) { __nc_ex_top->ex = ex; longjmp(__nc_ex_top->jb, 1); }',
        '    fprintf(stderr, "uncaught: %.*s\\n", (int)ex.len, ex.ptr); exit(1); }',
        "",
    ]


def emit_runtime(slice_types: set[str]) -> list[str]:
    lines = []
    lines.extend(emit_prelude())
    lines.extend(emit_gc())
    lines.extend(emit_str())
    lines.extend(emit_slice(slice_types))
    lines.extend(emit_map())
    lines.extend(emit_cast())
    lines.extend(emit_gc_helpers())
    lines.extend(emit_exception())
    return lines
