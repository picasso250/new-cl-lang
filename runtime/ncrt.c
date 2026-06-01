#include "ncrt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#include <fcntl.h>
#include <io.h>
#define getcwd _getcwd
#else
#include <unistd.h>
#endif

struct nc_entry {
    nc_val key;
    nc_val value;
    int state;
};

typedef struct __nc_gc_block {
    struct __nc_gc_block* next;
    size_t size;
    int marked;
    unsigned char payload[];
} __nc_gc_block;

static __nc_gc_block* __nc_gc_blocks = NULL;
static size_t __nc_gc_live_count = 0;
static void*** __nc_gc_roots = NULL;
static size_t __nc_gc_root_count = 0;
static size_t __nc_gc_root_cap = 0;
__nc_ex_frame_t* __nc_ex_top = NULL;
static int __nc_saved_argc = 0;
static char** __nc_saved_argv = NULL;

static void __nc_abort_oom(void) {
    fprintf(stderr, "nc runtime: out of memory\n");
    abort();
}

void __nc_gc_init(void) {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    __nc_gc_block* b = __nc_gc_blocks;
    while (b) {
        __nc_gc_block* next = b->next;
        free(b);
        b = next;
    }
    __nc_gc_blocks = NULL;
    __nc_gc_live_count = 0;
    __nc_gc_root_count = 0;
    __nc_ex_top = NULL;
}

void* __nc_gc_alloc(size_t sz) {
    size_t payload_size = sz ? sz : 1;
    __nc_gc_block* b = (__nc_gc_block*)calloc(1, sizeof(__nc_gc_block) + payload_size);
    if (!b) __nc_abort_oom();
    b->size = payload_size;
    b->next = __nc_gc_blocks;
    __nc_gc_blocks = b;
    __nc_gc_live_count++;
    return b->payload;
}

static __nc_gc_block* __nc_gc_find_block(void* p) {
    if (!p) return NULL;
    uintptr_t addr = (uintptr_t)p;
    for (__nc_gc_block* b = __nc_gc_blocks; b; b = b->next) {
        uintptr_t start = (uintptr_t)b->payload;
        uintptr_t end = start + b->size;
        if (addr >= start && addr < end) return b;
    }
    return NULL;
}

static void __nc_gc_mark_ptr(void* p);

static void __nc_gc_scan_block(__nc_gc_block* b) {
    size_t words = b->size / sizeof(void*);
    void** values = (void**)b->payload;
    for (size_t i = 0; i < words; i++) {
        __nc_gc_mark_ptr(values[i]);
    }
}

static void __nc_gc_mark_ptr(void* p) {
    __nc_gc_block* b = __nc_gc_find_block(p);
    if (!b || b->marked) return;
    b->marked = 1;
    __nc_gc_scan_block(b);
}

void __nc_gc_collect(void) {
    for (size_t i = 0; i < __nc_gc_root_count; i++) {
        void** slot = __nc_gc_roots[i];
        if (slot) __nc_gc_mark_ptr(*slot);
    }

    __nc_gc_block** link = &__nc_gc_blocks;
    __nc_gc_live_count = 0;
    while (*link) {
        __nc_gc_block* b = *link;
        if (!b->marked) {
            *link = b->next;
            free(b);
            continue;
        }
        b->marked = 0;
        __nc_gc_live_count++;
        link = &b->next;
    }
}

size_t __nc_gc_live(void) {
    return __nc_gc_live_count;
}

int __nc_gc_push_root_slot(void* slot) {
    if (__nc_gc_root_count == __nc_gc_root_cap) {
        size_t next_cap = __nc_gc_root_cap ? __nc_gc_root_cap * 2 : 64;
        void*** next = (void***)realloc(__nc_gc_roots, next_cap * sizeof(void**));
        if (!next) __nc_abort_oom();
        __nc_gc_roots = next;
        __nc_gc_root_cap = next_cap;
    }
    __nc_gc_roots[__nc_gc_root_count] = (void**)slot;
    return (int)__nc_gc_root_count++;
}

void __nc_gc_set_root(int h, void* p) {
    if (h < 0 || (size_t)h >= __nc_gc_root_count || !__nc_gc_roots[h]) return;
    *__nc_gc_roots[h] = p;
}

void __nc_gc_pop_root(void) {
    if (__nc_gc_root_count) __nc_gc_root_count--;
}

void __nc_gc_drop_root(int h) {
    if (h >= 0 && (size_t)h < __nc_gc_root_count) {
        __nc_gc_roots[h] = NULL;
    }
}

size_t __nc_gc_root_mark(void) {
    return __nc_gc_root_count;
}

void __nc_gc_root_rewind(size_t mark) {
    if (mark <= __nc_gc_root_count) {
        __nc_gc_root_count = mark;
    }
}

void __nc_cstr_to_str_out(str* out, const char* cstr) {
    if (!cstr) {
        *out = (str){0, 0};
        return;
    }
    size_t len = strlen(cstr);
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(len + 1);
    if (len) memcpy(buf, cstr, len);
    buf[len] = 0;
    *out = (str){buf, (uint64_t)len};
}

void __nc_os_set_args(int argc, char** argv) {
    __nc_saved_argc = argc;
    __nc_saved_argv = argv;
}

int32_t __nc_argc(void) {
    return __nc_saved_argc;
}

char* __nc_argv(int32_t i) {
    if (i < 0 || i >= __nc_saved_argc || !__nc_saved_argv) return NULL;
    return __nc_saved_argv[i];
}

int __nc_str_eq(str a, str b) {
    if (a.len != b.len) return 0;
    if (a.len == 0) return 1;
    return memcmp(a.ptr, b.ptr, (size_t)a.len) == 0;
}

int __nc_str_eq_ptr(const str* a, const str* b) {
    return __nc_str_eq(*a, *b);
}

void __nc_slice_copy_raw(nc_slice_raw* out, const void* src, uint64_t len, uint64_t elem_size) {
    out->ptr = NULL;
    out->len = len;
    out->cap = len;
    if (len == 0) return;
    out->ptr = __nc_gc_alloc((size_t)len * (size_t)elem_size);
    memcpy(out->ptr, src, (size_t)len * (size_t)elem_size);
}

void __nc_slice_append_raw(nc_slice_raw* out, const nc_slice_raw* in, const void* elem, uint64_t elem_size) {
    *out = *in;
    if (out->len >= out->cap) {
        uint64_t nc = out->cap ? out->cap * 2 : 4;
        void* np = __nc_gc_alloc((size_t)nc * (size_t)elem_size);
        if (out->ptr && out->len) {
            memcpy(np, out->ptr, (size_t)out->len * (size_t)elem_size);
        }
        out->ptr = np;
        out->cap = nc;
    }
    memcpy((uint8_t*)out->ptr + ((size_t)out->len * (size_t)elem_size), elem, (size_t)elem_size);
    out->len++;
}

int32_t __nc_slice_copy_into_raw(nc_slice_raw* dst, const nc_slice_raw* src, uint64_t elem_size) {
    uint64_t n = dst->len < src->len ? dst->len : src->len;
    if (n && dst->ptr && src->ptr) {
        memmove(dst->ptr, src->ptr, (size_t)n * (size_t)elem_size);
    }
    return (int32_t)n;
}

void __nc_slice_clear_raw(nc_slice_raw* s, uint64_t elem_size) {
    if (s->ptr && s->len) {
        memset(s->ptr, 0, (size_t)s->len * (size_t)elem_size);
    }
}

str __nc_str_cat(str a, str b) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)(a.len + b.len + 1));
    if (a.len) memcpy(buf, a.ptr, (size_t)a.len);
    if (b.len) memcpy(buf + a.len, b.ptr, (size_t)b.len);
    buf[a.len + b.len] = 0;
    return (str){buf, a.len + b.len};
}

void __nc_str_alloc_out(str* out, uint64_t len) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)len + 1);
    buf[len] = 0;
    *out = (str){buf, len};
}

void __nc_str_cat_out(str* out, const str* a, const str* b) {
    *out = __nc_str_cat(*a, *b);
}

str __nc_str_slice_copy(str s, uint64_t start, uint64_t end) {
    uint64_t n = end - start;
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)n + 1);
    if (n) memcpy(buf, s.ptr + start, (size_t)n);
    buf[n] = 0;
    return (str){buf, n};
}

void __nc_str_slice_copy_out(str* out, const str* s, uint64_t start, uint64_t end) {
    *out = __nc_str_slice_copy(*s, start, end);
}

str __nc_i32_to_str(int n) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(24);
    int len = sprintf((char*)buf, "%d", n);
    return (str){buf, (uint64_t)len};
}

void __nc_i32_to_str_out(str* out, int n) {
    *out = __nc_i32_to_str(n);
}

void __nc_i64_to_str_out(str* out, int64_t n) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(32);
    int len = snprintf((char*)buf, 32, "%lld", (long long)n);
    if (len < 0) len = 0;
    *out = (str){buf, (uint64_t)len};
}

void __nc_u64_to_str_out(str* out, uint64_t n) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(32);
    int len = snprintf((char*)buf, 32, "%llu", (unsigned long long)n);
    if (len < 0) len = 0;
    *out = (str){buf, (uint64_t)len};
}

void __nc_f64_to_str_out(str* out, double n) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(64);
    int len = snprintf((char*)buf, 64, "%g", n);
    if (len < 0) len = 0;
    *out = (str){buf, (uint64_t)len};
}

void __nc_rune_to_str_out(str* out, uint32_t r) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc(5);
    uint64_t len = 0;
    if (r <= 0x7F) {
        buf[len++] = (uint8_t)r;
    } else if (r <= 0x7FF) {
        buf[len++] = (uint8_t)(0xC0 | (r >> 6));
        buf[len++] = (uint8_t)(0x80 | (r & 0x3F));
    } else if (r <= 0xFFFF && !(r >= 0xD800 && r <= 0xDFFF)) {
        buf[len++] = (uint8_t)(0xE0 | (r >> 12));
        buf[len++] = (uint8_t)(0x80 | ((r >> 6) & 0x3F));
        buf[len++] = (uint8_t)(0x80 | (r & 0x3F));
    } else if (r <= 0x10FFFF) {
        buf[len++] = (uint8_t)(0xF0 | (r >> 18));
        buf[len++] = (uint8_t)(0x80 | ((r >> 12) & 0x3F));
        buf[len++] = (uint8_t)(0x80 | ((r >> 6) & 0x3F));
        buf[len++] = (uint8_t)(0x80 | (r & 0x3F));
    } else {
        buf[len++] = 0xEF;
        buf[len++] = 0xBF;
        buf[len++] = 0xBD;
    }
    buf[len] = 0;
    *out = (str){buf, len};
}

int __nc_str_to_i32(str s) {
    return atoi((const char*)s.ptr);
}

int __nc_str_to_i32_ptr(const str* s) {
    return __nc_str_to_i32(*s);
}

static int __nc_str_bytes_eq(const uint8_t* a, const uint8_t* b, int64_t n) {
    return n == 0 || memcmp(a, b, (size_t)n) == 0;
}

static void __nc_hash_bytes(unsigned long long* h, const void* data, size_t len) {
    const unsigned char* p = (const unsigned char*)data;
    for (size_t i = 0; i < len; i++) {
        *h ^= p[i];
        *h *= 1099511628211ULL;
    }
}

static int64_t __nc_map_hash(const nc_val* key, int64_t cap) {
    unsigned long long h = 14695981039346656037ULL;
    __nc_hash_bytes(&h, &key->tag, sizeof(key->tag));
    if (key->tag == NC_VAL_STR) {
        __nc_hash_bytes(&h, (const void*)(uintptr_t)key->a, (size_t)key->b);
    } else {
        __nc_hash_bytes(&h, &key->a, sizeof(key->a));
        __nc_hash_bytes(&h, &key->b, sizeof(key->b));
    }
    return (int64_t)(h % (unsigned long long)cap);
}

static int __nc_val_eq(const nc_val* a, const nc_val* b) {
    if (a->tag != b->tag) return 0;
    if (a->tag == NC_VAL_STR) {
        if (a->b != b->b) return 0;
        return __nc_str_bytes_eq((const uint8_t*)(uintptr_t)a->a, (const uint8_t*)(uintptr_t)b->a, (int64_t)a->b);
    }
    return a->a == b->a && a->b == b->b;
}

void __nc_map_init(nc_map* m) {
    m->cap = 16;
    m->len = 0;
    m->tombstones = 0;
    m->entries = (nc_entry*)__nc_gc_alloc(16 * sizeof(nc_entry));
}

void __nc_map_free(nc_map* m) {
    m->entries = 0;
    m->cap = 0;
    m->len = 0;
    m->tombstones = 0;
}

static void __nc_map_rehash(nc_map* m) {
    int64_t old_cap = m->cap;
    nc_entry* old = m->entries;
    m->cap *= 2;
    m->len = 0;
    m->tombstones = 0;
    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * sizeof(nc_entry));
    for (int64_t i = 0; i < old_cap; i++) {
        if (old[i].state != 1) continue;
        int64_t idx = __nc_map_hash(&old[i].key, m->cap);
        for (;;) {
            if (m->entries[idx].state == 0) {
                m->entries[idx] = old[i];
                m->len++;
                break;
            }
            idx = (idx + 1) % m->cap;
        }
    }
}

static void __nc_map_put(nc_map* m, const nc_val* key, nc_val value) {
    if (!m->cap) __nc_map_init(m);
    if ((double)(m->len + m->tombstones) / (double)m->cap > 0.70) {
        __nc_map_rehash(m);
    }
    int64_t idx = __nc_map_hash(key, m->cap);
    int64_t tomb = -1;
    for (int64_t i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) {
            int64_t put_at = tomb >= 0 ? tomb : idx;
            m->entries[put_at].key = *key;
            m->entries[put_at].value = value;
            m->entries[put_at].state = 1;
            m->len++;
            if (tomb >= 0) m->tombstones--;
            return;
        }
        if (m->entries[idx].state == 2 && tomb < 0) tomb = idx;
        if (m->entries[idx].state == 1 && __nc_val_eq(key, &m->entries[idx].key)) {
            m->entries[idx].value = value;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

static int __nc_map_lookup(const nc_map* m, const nc_val* key, nc_val* out) {
    if (!m->cap) return 0;
    int64_t idx = __nc_map_hash(key, m->cap);
    for (int64_t i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) return 0;
        if (m->entries[idx].state == 1 && __nc_val_eq(key, &m->entries[idx].key)) {
            *out = m->entries[idx].value;
            return 1;
        }
        idx = (idx + 1) % m->cap;
    }
    return 0;
}

void __nc_map_set(nc_map* m, const nc_val* key, const nc_val* value) {
    __nc_map_put(m, key, *value);
}

void __nc_map_get(nc_val* out, nc_map* m, const nc_val* key, int32_t value_tag) {
    nc_val v;
    if (__nc_map_lookup(m, key, &v) && v.tag == value_tag) {
        *out = v;
        return;
    }
    out->tag = value_tag;
    out->a = 0;
    out->b = 0;
}

int __nc_map_has(nc_map* m, const nc_val* key) {
    nc_val v;
    return __nc_map_lookup(m, key, &v);
}

void __nc_map_delete(nc_map* m, const nc_val* key) {
    if (!m->cap) return;
    int64_t idx = __nc_map_hash(key, m->cap);
    for (int64_t i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) return;
        if (m->entries[idx].state == 1 && __nc_val_eq(key, &m->entries[idx].key)) {
            memset(&m->entries[idx].key, 0, sizeof(nc_val));
            memset(&m->entries[idx].value, 0, sizeof(nc_val));
            m->entries[idx].state = 2;
            m->len--;
            m->tombstones++;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

void __nc_map_clear(nc_map* m) {
    if (!m->cap) return;
    memset(m->entries, 0, (size_t)m->cap * sizeof(nc_entry));
    m->len = 0;
    m->tombstones = 0;
}

void __nc_throw(str ex) {
    if (__nc_ex_top) {
        __nc_ex_top->ex = ex;
        longjmp(__nc_ex_top->jb, 1);
    }
    fprintf(stderr, "uncaught: %.*s\n", (int)ex.len, ex.ptr);
    exit(1);
}
