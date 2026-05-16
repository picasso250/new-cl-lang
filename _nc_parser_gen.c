#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

// === nc_gc.h inline ===
typedef struct _nc_record { void* ptr; size_t size; uint8_t marked; struct _nc_record* next; } nc_record_t;
static nc_record_t* __nc_gc_registry = NULL;
static struct { void* ptr; int active; } __nc_gc_roots[256];
static size_t __nc_gc_root_n = 0;
static nc_record_t* __nc_gc_gray[4096];
static size_t __nc_gc_gray_top = 0;
static int __nc_gc_is_heap(void* c) {
    if (!c) return 0;
    uintptr_t a = (uintptr_t)c;
    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)
        if (a >= (uintptr_t)r->ptr && a < (uintptr_t)r->ptr + r->size) return 1;
    return 0; }
static nc_record_t* __nc_gc_find(void* p) {
    for (nc_record_t* r = __nc_gc_registry; r; r = r->next)
        if (p >= r->ptr && (uintptr_t)p < (uintptr_t)r->ptr + r->size) return r;
    return NULL; }
static void __nc_gc_mark_gray(void* p) {
    nc_record_t* r = __nc_gc_find(p);
    if (r && r->marked == 0) { r->marked = 1; if (__nc_gc_gray_top < 4096) __nc_gc_gray[__nc_gc_gray_top++] = r; } }
static void __nc_gc_scan(nc_record_t* r) {
    size_t n = r->size / sizeof(void*); void** w = (void**)r->ptr;
    for (size_t i = 0; i < n; i++) if (w[i]) __nc_gc_mark_gray(w[i]); }
static void* __nc_gc_alloc(size_t sz) {
    void* p = calloc(1, sz); if (!p) return NULL;
    nc_record_t* rec = (nc_record_t*)malloc(sizeof(nc_record_t));
    rec->ptr = p; rec->size = sz; rec->marked = 0;
    rec->next = __nc_gc_registry; __nc_gc_registry = rec; return p; }
static int __nc_gc_push_root(void* p) {
    if (!p || !__nc_gc_is_heap(p)) return -1;
    if (__nc_gc_root_n >= 256) return -1;
    __nc_gc_roots[__nc_gc_root_n].ptr = p;
    __nc_gc_roots[__nc_gc_root_n].active = 1;
    return (int)__nc_gc_root_n++; }
static void __nc_gc_pop_root(void) { if (__nc_gc_root_n > 0) __nc_gc_root_n--; }
static void __nc_gc_drop_root(int h) { if (h>=0 && h<(int)__nc_gc_root_n) __nc_gc_roots[h].active=0; }
static void __nc_gc_collect(void) {
    for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_mark_gray(__nc_gc_roots[i].ptr);
    while (__nc_gc_gray_top > 0) { nc_record_t* r = __nc_gc_gray[--__nc_gc_gray_top]; __nc_gc_scan(r); r->marked = 2; }
    nc_record_t** prev = &__nc_gc_registry; nc_record_t* c = __nc_gc_registry;
    while (c) { if (c->marked == 0) { *prev = c->next; free(c->ptr); nc_record_t* d=c; c=c->next; free(d); }
        else { c->marked = 0; prev = &c->next; c = c->next; } }
    __nc_gc_gray_top = 0;
    size_t w = 0; for (size_t i = 0; i < __nc_gc_root_n; i++) if (__nc_gc_roots[i].active) __nc_gc_roots[w++] = __nc_gc_roots[i];
    __nc_gc_root_n = w; }

typedef struct { const char* _ptr; long long _len; } str;

static str __nc_read_file(const char* path) {
    FILE* fp = fopen(path, "rb");
    if (!fp) { str e = {NULL, 0}; return e; }
    fseek(fp, 0, SEEK_END);
    long long sz = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    char* buf = (char*)__nc_gc_alloc(sz + 1);
    fread(buf, 1, sz, fp);
    buf[sz] = 0;
    fclose(fp);
    str r = {(const char*)buf, sz};
    return r;
}

static void __nc_write_file(const char* path, str content) {
    FILE* fp = fopen(path, "w");
    if (!fp) return;
    fwrite(content._ptr, 1, content._len, fp);
    fclose(fp);
}

static int __nc_str_eq(str a, str b) {
    if (a._len != b._len) return 0;
    return strncmp(a._ptr, b._ptr, a._len) == 0;
}

static str __nc_str_cat(str a, str b) {
    char* buf = (char*)__nc_gc_alloc(a._len + b._len + 1);
    memcpy(buf, a._ptr, a._len);
    memcpy(buf + a._len, b._ptr, b._len);
    buf[a._len + b._len] = 0;
    str r = {(const char*)buf, a._len + b._len};
    return r;
}

typedef struct { int* _ptr; long long _len; long long _cap; } _slice_int;

static _slice_int __nc_append_int(_slice_int s, int elem) {
    if (s._len >= s._cap) {
        long long nc = s._cap ? s._cap * 2 : 4;
        int* np = (int*)__nc_gc_alloc(nc * sizeof(int));
        for (long long i = 0; i < s._len; i++) np[i] = s._ptr[i];
        s._ptr = np; s._cap = nc;
    }
    s._ptr[s._len++] = elem;
    return s;
}

typedef enum { NC_VAL_NIL = 0, NC_VAL_I32, NC_VAL_STR, NC_VAL_PTR } nc_val_tag;
typedef struct { nc_val_tag tag; union { long long i; str s; void* p; }; } nc_val;
typedef struct { str key; nc_val value; int state; } nc_entry;
typedef struct { nc_entry* entries; long long cap; long long len; long long tombstones; } nc_map;

static int __nc_str_bytes_eq(const char* a, const char* b, long long n) {
    for (long long i = 0; i < n; i++) if (a[i] != b[i]) return 0;
    return 1;
}

static long long __nc_map_hash(str key, long long cap) {
    unsigned long long h = 14695981039346656037ULL;
    for (long long i = 0; i < key._len; i++) {
        h ^= (unsigned char)key._ptr[i]; h *= 1099511628211ULL; }
    return (long long)(h % (unsigned long long)cap);
}

static void __nc_map_init(nc_map* m) {
    m->cap = 16; m->len = 0; m->tombstones = 0;
    m->entries = (nc_entry*)__nc_gc_alloc(16 * sizeof(nc_entry));
}

static void __nc_map_free(nc_map* m) {
    free(m->entries); m->entries = 0; m->cap = 0; m->len = 0; m->tombstones = 0;
}

static void __nc_map_rehash(nc_map* m) {
    long long oc = m->cap; nc_entry* old = m->entries;
    m->cap *= 2; m->len = 0; m->tombstones = 0;
    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * sizeof(nc_entry));
    for (long long i = 0; i < oc; i++) {
        if (old[i].state == 1) {
            long long idx = __nc_map_hash(old[i].key, m->cap);
            for (long long j = 0; j < m->cap; j++) {
                if (m->entries[idx].state == 0) { m->entries[idx] = old[i]; break; }
                idx = (idx + 1) % m->cap; } } }
    free(old);
}

static void __nc_map_put(nc_map* m, str key, nc_val value) {
    if (m->cap && (double)(m->len + m->tombstones) / (double)m->cap > 0.70) __nc_map_rehash(m);
    long long idx = __nc_map_hash(key, m->cap);
    long long tomb = -1;
    for (long long i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) {
            long long put_at = (tomb >= 0) ? tomb : idx;
            m->entries[put_at].key = key; m->entries[put_at].value = value;
            m->entries[put_at].state = 1; m->len++;
            if (tomb >= 0) m->tombstones--;
            return; }
        if (m->entries[idx].state == 2 && tomb < 0) tomb = idx;
        if (m->entries[idx].state == 1 && key._len == m->entries[idx].key._len && __nc_str_bytes_eq(key._ptr, m->entries[idx].key._ptr, key._len)) {
            m->entries[idx].value = value; return; }
        idx = (idx + 1) % m->cap; } }

static int __nc_map_get(const nc_map* m, str key, nc_val* out) {
    if (!m->cap) return 0;
    long long idx = __nc_map_hash(key, m->cap);
    for (long long i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) return 0;
        if (m->entries[idx].state == 1 && key._len == m->entries[idx].key._len && __nc_str_bytes_eq(key._ptr, m->entries[idx].key._ptr, key._len)) {
            *out = m->entries[idx].value; return 1; }
        idx = (idx + 1) % m->cap; }
    return 0; }

static void __nc_map_set_str(nc_map* m, str key, str value) {
    __nc_map_put(m, key, (nc_val){.tag = NC_VAL_STR, .s = value}); }

static str __nc_map_get_str(nc_map* m, str key) {
    nc_val v;
    if (__nc_map_get(m, key, &v) && v.tag == NC_VAL_STR) return v.s;
    return (str){0, 0}; }

static int __nc_map_has(nc_map* m, str key) {
    nc_val v; return __nc_map_get(m, key, &v); }

static str __nc_i32_to_str(int n) {
    char* buf = (char*)__nc_gc_alloc(24);
    int len = sprintf(buf, "%d", n);
    return (str){buf, len}; }

static int __nc_str_to_i32(str s) {
    return atoi(s._ptr); }

static void __nc_gc_init(void) {
    __nc_gc_registry = NULL; __nc_gc_root_n = 0; __nc_gc_gray_top = 0; }

static size_t __nc_gc_live(void) {
    size_t n = 0;
    for (nc_record_t* r = __nc_gc_registry; r; r = r->next) n++;
    return n; }

#include <setjmp.h>
typedef struct __nc_ex_frame { jmp_buf jb; struct __nc_ex_frame* prev; str ex; } __nc_ex_frame_t;
static __nc_ex_frame_t* __nc_ex_top = NULL;
static void __nc_throw(str ex) {
    if (__nc_ex_top) { __nc_ex_top->ex = ex; longjmp(__nc_ex_top->jb, 1); }
    fprintf(stderr, "uncaught: %.*s\n", (int)ex._len, ex._ptr); exit(1); }

typedef struct { str code; int pos; } ParseResult;

int skip_space(str src, int pos);
int is_digit(int ch);
int is_alpha(int ch);
ParseResult read_word(str src, int pos);
ParseResult read_number(str src, int pos);
ParseResult parse_primary(str src, int pos);
ParseResult parse_mul(str src, int pos);
ParseResult parse_add(str src, int pos);
ParseResult parse_cmp(str src, int pos);
ParseResult parse_expression(str src, int pos);
ParseResult parse_block(str src, int pos);
ParseResult parse_statement(str src, int pos);

int skip_space(str src, int pos) {
    while (((pos < (int)(src)._len) && (((((int)(unsigned char)((src)._ptr[pos]) == 32) || ((int)(unsigned char)((src)._ptr[pos]) == 10)) || ((int)(unsigned char)((src)._ptr[pos]) == 9)) || ((int)(unsigned char)((src)._ptr[pos]) == 13)))) {
        pos = (pos + 1);
    }
    return pos;
}
int is_digit(int ch) {
    return ((48 <= ch) && (ch <= 57));
}
int is_alpha(int ch) {
    return ((((65 <= ch) && (ch <= 90)) || ((97 <= ch) && (ch <= 122))) || (ch == 95));
}
ParseResult read_word(str src, int pos) {
    int start = pos;
    while (((pos < (int)(src)._len) && (is_alpha((int)(unsigned char)((src)._ptr[pos])) || is_digit((int)(unsigned char)((src)._ptr[pos]))))) {
        pos = (pos + 1);
    }
    return (ParseResult){(str){src._ptr + start, pos - start}, pos};
}
ParseResult read_number(str src, int pos) {
    int start = pos;
    while (((pos < (int)(src)._len) && is_digit((int)(unsigned char)((src)._ptr[pos])))) {
        pos = (pos + 1);
    }
    return (ParseResult){(str){src._ptr + start, pos - start}, pos};
}
ParseResult parse_primary(str src, int pos) {
    pos = skip_space(src, pos);
    if ((pos >= (int)(src)._len)) {
        return (ParseResult){(str){"", 0}, pos};
    }
    int ch = (int)(unsigned char)((src)._ptr[pos]);
    if (is_digit(ch)) {
        return read_number(src, pos);
    }
    if (is_alpha(ch)) {
        return read_word(src, pos);
    }
    return (ParseResult){(str){"", 0}, pos};
}
ParseResult parse_mul(str src, int pos) {
    ParseResult r = parse_primary(src, pos);
    str code = r.code;
    __nc_gc_push_root((void*)code._ptr);
    pos = r.pos;
    pos = skip_space(src, pos);
    while (((pos < (int)(src)._len) && (((int)(unsigned char)((src)._ptr[pos]) == 42) || ((int)(unsigned char)((src)._ptr[pos]) == 47)))) {
        int op = (int)(unsigned char)((src)._ptr[pos]);
        pos = (pos + 1);
        ParseResult r2 = parse_primary(src, pos);
        if ((op == 42)) {
            code = __nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"(", 1}, code), (str){" * ", 3}), r2.code), (str){")", 1});
            __nc_gc_push_root((void*)code._ptr);
        } else {
            code = __nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"(", 1}, code), (str){" / ", 3}), r2.code), (str){")", 1});
            __nc_gc_push_root((void*)code._ptr);
        }
        pos = r2.pos;
        pos = skip_space(src, pos);
    }
    return (ParseResult){code, pos};
    __nc_gc_pop_root();
}
ParseResult parse_add(str src, int pos) {
    ParseResult r = parse_mul(src, pos);
    str code = r.code;
    __nc_gc_push_root((void*)code._ptr);
    pos = r.pos;
    pos = skip_space(src, pos);
    while (((pos < (int)(src)._len) && (((int)(unsigned char)((src)._ptr[pos]) == 43) || ((int)(unsigned char)((src)._ptr[pos]) == 45)))) {
        int op = (int)(unsigned char)((src)._ptr[pos]);
        pos = (pos + 1);
        ParseResult r2 = parse_mul(src, pos);
        if ((op == 43)) {
            code = __nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"(", 1}, code), (str){" + ", 3}), r2.code), (str){")", 1});
            __nc_gc_push_root((void*)code._ptr);
        } else {
            code = __nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"(", 1}, code), (str){" - ", 3}), r2.code), (str){")", 1});
            __nc_gc_push_root((void*)code._ptr);
        }
        pos = r2.pos;
        pos = skip_space(src, pos);
    }
    return (ParseResult){code, pos};
    __nc_gc_pop_root();
}
ParseResult parse_cmp(str src, int pos) {
    ParseResult r = parse_add(src, pos);
    str code = r.code;
    __nc_gc_push_root((void*)code._ptr);
    pos = r.pos;
    pos = skip_space(src, pos);
    str op = (str){"", 0};
    __nc_gc_push_root((void*)op._ptr);
    if (((((pos + 1) < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 61)) && ((int)(unsigned char)((src)._ptr[(pos + 1)]) == 61))) {
        op = (str){"==", 2};
        __nc_gc_push_root((void*)op._ptr);
        pos = (pos + 2);
    } else {
        if (((((pos + 1) < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 33)) && ((int)(unsigned char)((src)._ptr[(pos + 1)]) == 61))) {
            op = (str){"!=", 2};
            __nc_gc_push_root((void*)op._ptr);
            pos = (pos + 2);
        } else {
            if (((((pos + 1) < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 60)) && ((int)(unsigned char)((src)._ptr[(pos + 1)]) == 61))) {
                op = (str){"<=", 2};
                __nc_gc_push_root((void*)op._ptr);
                pos = (pos + 2);
            } else {
                if (((((pos + 1) < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 62)) && ((int)(unsigned char)((src)._ptr[(pos + 1)]) == 61))) {
                    op = (str){">=", 2};
                    __nc_gc_push_root((void*)op._ptr);
                    pos = (pos + 2);
                } else {
                    if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 60))) {
                        op = (str){"<", 1};
                        __nc_gc_push_root((void*)op._ptr);
                        pos = (pos + 1);
                    } else {
                        if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 62))) {
                            op = (str){">", 1};
                            __nc_gc_push_root((void*)op._ptr);
                            pos = (pos + 1);
                        }
                    }
                }
            }
        }
    }
    if (!__nc_str_eq(op, (str){"", 0})) {
        pos = skip_space(src, pos);
        ParseResult r2 = parse_add(src, pos);
        code = __nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"(", 1}, code), (str){" ", 1}), op), (str){" ", 1}), r2.code), (str){")", 1});
        __nc_gc_push_root((void*)code._ptr);
        pos = r2.pos;
    }
    return (ParseResult){code, pos};
    __nc_gc_pop_root();
    __nc_gc_pop_root();
}
ParseResult parse_expression(str src, int pos) {
    return parse_cmp(src, pos);
}
ParseResult parse_block(str src, int pos) {
    pos = skip_space(src, pos);
    if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 123))) {
        pos = (pos + 1);
    }
    str code = (str){"{\n", 2};
    __nc_gc_push_root((void*)code._ptr);
    pos = skip_space(src, pos);
    while (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) != 125))) {
        ParseResult r = parse_statement(src, pos);
        code = __nc_str_cat(code, r.code);
        __nc_gc_push_root((void*)code._ptr);
        pos = r.pos;
        pos = skip_space(src, pos);
        if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 59))) {
            pos = (pos + 1);
        }
        pos = skip_space(src, pos);
    }
    if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 125))) {
        pos = (pos + 1);
    }
    code = __nc_str_cat(code, (str){"}\n", 2});
    __nc_gc_push_root((void*)code._ptr);
    return (ParseResult){code, pos};
    __nc_gc_pop_root();
}
ParseResult parse_statement(str src, int pos) {
    pos = skip_space(src, pos);
    if ((pos >= (int)(src)._len)) {
        return (ParseResult){(str){"", 0}, pos};
    }
    int ch = (int)(unsigned char)((src)._ptr[pos]);
    if ((ch == 125)) {
        return (ParseResult){(str){"", 0}, pos};
    }
    if ((ch == 59)) {
        return (ParseResult){(str){"", 0}, (pos + 1)};
    }
    if (is_alpha(ch)) {
        ParseResult r = read_word(src, pos);
        str word = r.code;
        __nc_gc_push_root((void*)word._ptr);
        pos = r.pos;
        if (__nc_str_eq(word, (str){"let", 3})) {
            pos = skip_space(src, pos);
            if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 109))) {
                ParseResult r2 = read_word(src, pos);
                if (__nc_str_eq(r2.code, (str){"mut", 3})) {
                    pos = r2.pos;
                    pos = skip_space(src, pos);
                }
            }
            ParseResult nr = read_word(src, pos);
            str vname = nr.code;
            __nc_gc_push_root((void*)vname._ptr);
            pos = nr.pos;
            pos = skip_space(src, pos);
            if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 61))) {
                pos = (pos + 1);
            }
            ParseResult er = parse_expression(src, pos);
            return (ParseResult){__nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"    int ", 8}, vname), (str){" = ", 3}), er.code), (str){";\n", 2}), er.pos};
        }
        if (__nc_str_eq(word, (str){"print", 5})) {
            pos = skip_space(src, pos);
            if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 40))) {
                pos = (pos + 1);
            }
            pos = skip_space(src, pos);
            ParseResult er = parse_expression(src, pos);
            pos = er.pos;
            pos = skip_space(src, pos);
            if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 41))) {
                pos = (pos + 1);
            }
            return (ParseResult){__nc_str_cat(__nc_str_cat((str){"    printf(\"%d\\n\", ", 19}, er.code), (str){");\n", 3}), pos};
        }
        if (__nc_str_eq(word, (str){"if", 2})) {
            pos = skip_space(src, pos);
            ParseResult cr = parse_expression(src, pos);
            pos = cr.pos;
            ParseResult block = parse_block(src, pos);
            str code = __nc_str_cat(__nc_str_cat(__nc_str_cat((str){"    if (", 8}, cr.code), (str){") ", 2}), block.code);
            __nc_gc_push_root((void*)code._ptr);
            pos = block.pos;
            pos = skip_space(src, pos);
            if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 101))) {
                ParseResult r2 = read_word(src, pos);
                if (__nc_str_eq(r2.code, (str){"else", 4})) {
                    pos = r2.pos;
                    ParseResult b2 = parse_block(src, pos);
                    code = __nc_str_cat(__nc_str_cat(code, (str){"    else ", 9}), b2.code);
                    __nc_gc_push_root((void*)code._ptr);
                    pos = b2.pos;
                }
            }
            return (ParseResult){code, pos};
        }
        if (__nc_str_eq(word, (str){"while", 5})) {
            pos = skip_space(src, pos);
            ParseResult cr = parse_expression(src, pos);
            pos = cr.pos;
            ParseResult block = parse_block(src, pos);
            return (ParseResult){__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"    while (", 11}, cr.code), (str){") ", 2}), block.code), block.pos};
        }
        pos = skip_space(src, pos);
        if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 61))) {
            pos = (pos + 1);
            pos = skip_space(src, pos);
            ParseResult er = parse_expression(src, pos);
            return (ParseResult){__nc_str_cat(__nc_str_cat(__nc_str_cat(__nc_str_cat((str){"    ", 4}, word), (str){" = ", 3}), er.code), (str){";\n", 2}), er.pos};
        }
        return (ParseResult){__nc_str_cat(__nc_str_cat((str){"    ", 4}, word), (str){";\n", 2}), pos};
    }
    ParseResult er = parse_expression(src, pos);
    return (ParseResult){__nc_str_cat(__nc_str_cat((str){"    ", 4}, er.code), (str){";\n", 2}), er.pos};
    __nc_gc_pop_root();
    __nc_gc_pop_root();
    __nc_gc_pop_root();
}
int main(void) {
    __nc_gc_init();
    str src = __nc_read_file("input.nc");
    __nc_gc_push_root((void*)src._ptr);
    int pos = 0;
    str out = (str){"#include <stdio.h>\nint main(void) {\n", 36};
    __nc_gc_push_root((void*)out._ptr);
    pos = skip_space(src, pos);
    while ((pos < (int)(src)._len)) {
        ParseResult r = parse_statement(src, pos);
        out = __nc_str_cat(out, r.code);
        __nc_gc_push_root((void*)out._ptr);
        pos = skip_space(src, r.pos);
        if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 59))) {
            pos = (pos + 1);
        }
        pos = skip_space(src, pos);
        if (((pos < (int)(src)._len) && ((int)(unsigned char)((src)._ptr[pos]) == 125))) {
            break;
        }
    }
    out = __nc_str_cat(out, (str){"    return 0;\n}\n", 16});
    __nc_gc_push_root((void*)out._ptr);
    __nc_write_file("out.c", out);
    __nc_gc_pop_root();
    __nc_gc_pop_root();
    return 0;
}