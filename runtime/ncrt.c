#include "ncrt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

struct nc_entry {
    str key;
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

static void __nc_abort_oom(void) {
    fprintf(stderr, "nc runtime: out of memory\n");
    abort();
}

void __nc_gc_init(void) {
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

str __nc_read_file(const char* path) {
    FILE* fp = fopen(path, "rb");
    if (!fp) return (str){0, 0};
    fseek(fp, 0, SEEK_END);
    long sz = ftell(fp);
    if (sz < 0) {
        fclose(fp);
        return (str){0, 0};
    }
    fseek(fp, 0, SEEK_SET);
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)sz + 1);
    size_t n = fread(buf, 1, (size_t)sz, fp);
    fclose(fp);
    buf[n] = 0;
    return (str){buf, (uint64_t)n};
}

void __nc_write_file(const char* path, str content) {
    FILE* fp = fopen(path, "wb");
    if (!fp) return;
    fwrite(content.ptr, 1, content.len, fp);
    fclose(fp);
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

str __nc_str_cat(str a, str b) {
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)(a.len + b.len + 1));
    if (a.len) memcpy(buf, a.ptr, (size_t)a.len);
    if (b.len) memcpy(buf + a.len, b.ptr, (size_t)b.len);
    buf[a.len + b.len] = 0;
    return (str){buf, a.len + b.len};
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

int __nc_str_to_i32(str s) {
    return atoi((const char*)s.ptr);
}

int __nc_str_to_i32_ptr(const str* s) {
    return __nc_str_to_i32(*s);
}

void __nc_read_file_out(str* out, const char* path) {
    *out = __nc_read_file(path);
}

void __nc_write_file_ptr(const char* path, const str* content) {
    __nc_write_file(path, *content);
}

static int __nc_str_bytes_eq(const uint8_t* a, const uint8_t* b, int64_t n) {
    return n == 0 || memcmp(a, b, (size_t)n) == 0;
}

static int64_t __nc_map_hash(str key, int64_t cap) {
    unsigned long long h = 14695981039346656037ULL;
    for (uint64_t i = 0; i < key.len; i++) {
        h ^= (unsigned char)key.ptr[i];
        h *= 1099511628211ULL;
    }
    return (int64_t)(h % (unsigned long long)cap);
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
        int64_t idx = __nc_map_hash(old[i].key, m->cap);
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

static void __nc_map_put(nc_map* m, str key, nc_val value) {
    if (!m->cap) __nc_map_init(m);
    if ((double)(m->len + m->tombstones) / (double)m->cap > 0.70) {
        __nc_map_rehash(m);
    }
    int64_t idx = __nc_map_hash(key, m->cap);
    int64_t tomb = -1;
    for (int64_t i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) {
            int64_t put_at = tomb >= 0 ? tomb : idx;
            m->entries[put_at].key = key;
            m->entries[put_at].value = value;
            m->entries[put_at].state = 1;
            m->len++;
            if (tomb >= 0) m->tombstones--;
            return;
        }
        if (m->entries[idx].state == 2 && tomb < 0) tomb = idx;
        if (m->entries[idx].state == 1 &&
            key.len == m->entries[idx].key.len &&
            __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, (int64_t)key.len)) {
            m->entries[idx].value = value;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

static int __nc_map_get(const nc_map* m, str key, nc_val* out) {
    if (!m->cap) return 0;
    int64_t idx = __nc_map_hash(key, m->cap);
    for (int64_t i = 0; i < m->cap; i++) {
        if (m->entries[idx].state == 0) return 0;
        if (m->entries[idx].state == 1 &&
            key.len == m->entries[idx].key.len &&
            __nc_str_bytes_eq(key.ptr, m->entries[idx].key.ptr, (int64_t)key.len)) {
            *out = m->entries[idx].value;
            return 1;
        }
        idx = (idx + 1) % m->cap;
    }
    return 0;
}

void __nc_map_set_str(nc_map* m, str key, str value) {
    nc_val v;
    v.tag = NC_VAL_STR;
    v.s = value;
    __nc_map_put(m, key, v);
}

void __nc_map_set_str_ptr(nc_map* m, const str* key, const str* value) {
    __nc_map_set_str(m, *key, *value);
}

str __nc_map_get_str(nc_map* m, str key) {
    nc_val v;
    if (__nc_map_get(m, key, &v) && v.tag == NC_VAL_STR) return v.s;
    return (str){0, 0};
}

void __nc_map_get_str_out(str* out, nc_map* m, const str* key) {
    *out = __nc_map_get_str(m, *key);
}

int __nc_map_has(nc_map* m, str key) {
    nc_val v;
    return __nc_map_get(m, key, &v);
}

int __nc_map_has_ptr(nc_map* m, const str* key) {
    return __nc_map_has(m, *key);
}

void __nc_throw(str ex) {
    if (__nc_ex_top) {
        __nc_ex_top->ex = ex;
        longjmp(__nc_ex_top->jb, 1);
    }
    fprintf(stderr, "uncaught: %.*s\n", (int)ex.len, ex.ptr);
    exit(1);
}
