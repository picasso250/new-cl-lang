#include "ncrt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#include <fcntl.h>
#include <io.h>
#define getcwd _getcwd
#else
#include <unistd.h>
#endif

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
static int __nc_saved_argc = 0;
static char** __nc_saved_argv = NULL;

static size_t __nc_gc_alloc_since_collect = 0;

static void __nc_abort_oom(void) {
    fprintf(stderr, "nc runtime: out of memory\n");
    abort();
}

FILE* __nc_stderr(void) {
    return stderr;
}

void __nc_error_from_str_out(nc_error* out, const str* message) {
    out->message = *message;
    out->frames.ptr = NULL;
    out->frames.len = 0;
    out->frames.cap = 0;
}

void __nc_error_append_frame(nc_error* err, const str* function, const str* path, int32_t line, int32_t col) {
    if (err->frames.len == err->frames.cap) {
        uint64_t next_cap = err->frames.cap ? err->frames.cap * 2 : 4;
        nc_error_frame* next = (nc_error_frame*)realloc(err->frames.ptr, (size_t)next_cap * sizeof(nc_error_frame));
        if (!next) __nc_abort_oom();
        err->frames.ptr = next;
        err->frames.cap = next_cap;
    }
    nc_error_frame* frames = (nc_error_frame*)err->frames.ptr;
    nc_error_frame* frame = &frames[err->frames.len++];
    frame->function = *function;
    frame->path = *path;
    frame->line = line;
    frame->col = col;
}

void __nc_error_print(const nc_error* err) {
    FILE* stream = __nc_stderr();
    fprintf(stream, "error: %.*s\n", (int)err->message.len, err->message.ptr);
    fprintf(stream, "stack:\n");
    nc_error_frame* frames = (nc_error_frame*)err->frames.ptr;
    for (uint64_t i = 0; i < err->frames.len; i++) {
        nc_error_frame* frame = &frames[i];
        fprintf(
            stream,
            "  at %.*s (%.*s:%d:%d)\n",
            (int)frame->function.len,
            frame->function.ptr,
            (int)frame->path.len,
            frame->path.ptr,
            frame->line,
            frame->col
        );
    }
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
}

void* __nc_gc_alloc(size_t sz) {
    size_t payload_size = sz ? sz : 1;
    __nc_gc_block* b = (__nc_gc_block*)calloc(1, sizeof(__nc_gc_block) + payload_size);
    if (!b) __nc_abort_oom();
    b->size = payload_size;
    b->next = __nc_gc_blocks;
    __nc_gc_blocks = b;
    __nc_gc_live_count++;
    __nc_gc_alloc_since_collect += sz;
    if (__nc_gc_alloc_since_collect >= 65536) {
        __nc_gc_collect();
        __nc_gc_alloc_since_collect = 0;
    }
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
    __nc_gc_alloc_since_collect = 0;
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

int32_t __nc_str_cmp_ptr(const str* a, const str* b) {
    uint64_t n = a->len < b->len ? a->len : b->len;
    if (n != 0) {
        int cmp = memcmp(a->ptr, b->ptr, (size_t)n);
        if (cmp < 0) return -1;
        if (cmp > 0) return 1;
    }
    if (a->len < b->len) return -1;
    if (a->len > b->len) return 1;
    return 0;
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

static void __nc_float_text_out(str* out, const char* text, int len) {
    if (len < 0) len = 0;
    uint8_t* buf = (uint8_t*)__nc_gc_alloc((size_t)len + 1);
    if (len) memcpy(buf, text, (size_t)len);
    buf[len] = 0;
    *out = (str){buf, (uint64_t)len};
}

static int __nc_same_f32(float a, float b) {
    return memcmp(&a, &b, sizeof(float)) == 0;
}

static int __nc_same_f64(double a, double b) {
    return memcmp(&a, &b, sizeof(double)) == 0;
}

void __nc_f32_to_str_out(str* out, float n) {
    char best[64];
    int best_len = snprintf(best, sizeof(best), "%.9g", (double)n);
    if (isfinite((double)n)) {
        for (int precision = 1; precision <= 9; precision++) {
            char candidate[64];
            int len = snprintf(candidate, sizeof(candidate), "%.*g", precision, (double)n);
            if (len < 0 || (size_t)len >= sizeof(candidate)) continue;
            float reparsed = strtof(candidate, NULL);
            if (__nc_same_f32(n, reparsed)) {
                memcpy(best, candidate, (size_t)len + 1);
                best_len = len;
                break;
            }
        }
    }
    __nc_float_text_out(out, best, best_len);
}

void __nc_f64_to_str_out(str* out, double n) {
    char best[64];
    int best_len = snprintf(best, sizeof(best), "%.17g", n);
    if (isfinite(n)) {
        for (int precision = 1; precision <= 17; precision++) {
            char candidate[64];
            int len = snprintf(candidate, sizeof(candidate), "%.*g", precision, n);
            if (len < 0 || (size_t)len >= sizeof(candidate)) continue;
            double reparsed = strtod(candidate, NULL);
            if (__nc_same_f64(n, reparsed)) {
                memcpy(best, candidate, (size_t)len + 1);
                best_len = len;
                break;
            }
        }
    }
    __nc_float_text_out(out, best, best_len);
}

float __nc_strict_str_to_f32(const uint8_t* ptr, uint64_t len) {
    if (!ptr && len != 0) return 0.0f;
    char* buf = (char*)malloc((size_t)len + 1);
    if (!buf) __nc_abort_oom();
    if (len) memcpy(buf, ptr, (size_t)len);
    buf[len] = 0;
    float value = strtof(buf, NULL);
    free(buf);
    return value;
}

double __nc_strict_str_to_f64(const uint8_t* ptr, uint64_t len) {
    if (!ptr && len != 0) return 0.0;
    char* buf = (char*)malloc((size_t)len + 1);
    if (!buf) __nc_abort_oom();
    if (len) memcpy(buf, ptr, (size_t)len);
    buf[len] = 0;
    double value = strtod(buf, NULL);
    free(buf);
    return value;
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

static unsigned char* __nc_map_entry_at(const nc_map* m, int64_t idx) {
    return ((unsigned char*)m->entries) + (size_t)idx * (size_t)m->desc->entry_size;
}

static int* __nc_map_state_ptr(const nc_map* m, unsigned char* entry) {
    return (int*)(void*)(entry + m->desc->state_offset);
}

static void* __nc_map_key_ptr(const nc_map* m, unsigned char* entry) {
    return entry + m->desc->key_offset;
}

static void* __nc_map_value_ptr(const nc_map* m, unsigned char* entry) {
    return entry + m->desc->value_offset;
}

static int64_t __nc_map_hash(nc_map_desc* desc, const void* key, int64_t cap) {
    return (int64_t)(desc->hash(key) % (uint64_t)cap);
}

void __nc_map_init(nc_map* m, nc_map_desc* desc) {
    m->desc = desc;
    m->cap = 16;
    m->len = 0;
    m->tombstones = 0;
    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * (size_t)desc->entry_size);
}

void __nc_map_free(nc_map* m) {
    m->desc = 0;
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
    m->entries = (nc_entry*)__nc_gc_alloc((size_t)m->cap * (size_t)m->desc->entry_size);
    for (int64_t i = 0; i < old_cap; i++) {
        unsigned char* old_entry = ((unsigned char*)old) + (size_t)i * (size_t)m->desc->entry_size;
        int old_state = *(int*)(void*)(old_entry + m->desc->state_offset);
        if (old_state != 1) continue;
        void* old_key = old_entry + m->desc->key_offset;
        int64_t idx = __nc_map_hash(m->desc, old_key, m->cap);
        for (;;) {
            unsigned char* entry = __nc_map_entry_at(m, idx);
            if (*__nc_map_state_ptr(m, entry) == 0) {
                memcpy(entry, old_entry, (size_t)m->desc->entry_size);
                m->len++;
                break;
            }
            idx = (idx + 1) % m->cap;
        }
    }
}

static void __nc_map_put(nc_map* m, nc_map_desc* desc, const void* key, const void* value) {
    if (!m->cap) __nc_map_init(m, desc);
    if ((double)(m->len + m->tombstones) / (double)m->cap > 0.70) {
        __nc_map_rehash(m);
    }
    int64_t idx = __nc_map_hash(m->desc, key, m->cap);
    int64_t tomb = -1;
    for (int64_t i = 0; i < m->cap; i++) {
        unsigned char* entry = __nc_map_entry_at(m, idx);
        int state = *__nc_map_state_ptr(m, entry);
        if (state == 0) {
            int64_t put_at = tomb >= 0 ? tomb : idx;
            unsigned char* put_entry = __nc_map_entry_at(m, put_at);
            memset(put_entry, 0, (size_t)m->desc->entry_size);
            memcpy(__nc_map_key_ptr(m, put_entry), key, (size_t)m->desc->key_size);
            memcpy(__nc_map_value_ptr(m, put_entry), value, (size_t)m->desc->value_size);
            *__nc_map_state_ptr(m, put_entry) = 1;
            m->len++;
            if (tomb >= 0) m->tombstones--;
            return;
        }
        if (state == 2 && tomb < 0) tomb = idx;
        if (state == 1 && m->desc->eq(key, __nc_map_key_ptr(m, entry))) {
            memcpy(__nc_map_value_ptr(m, entry), value, (size_t)m->desc->value_size);
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

static int __nc_map_lookup(nc_map* m, nc_map_desc* desc, const void* key, void* out) {
    if (!m->cap) return 0;
    if (!m->desc) m->desc = desc;
    int64_t idx = __nc_map_hash(m->desc, key, m->cap);
    for (int64_t i = 0; i < m->cap; i++) {
        unsigned char* entry = __nc_map_entry_at(m, idx);
        int state = *__nc_map_state_ptr(m, entry);
        if (state == 0) return 0;
        if (state == 1 && m->desc->eq(key, __nc_map_key_ptr(m, entry))) {
            if (out) memcpy(out, __nc_map_value_ptr(m, entry), (size_t)m->desc->value_size);
            return 1;
        }
        idx = (idx + 1) % m->cap;
    }
    return 0;
}

void __nc_map_set(nc_map* m, nc_map_desc* desc, const void* key, const void* value) {
    __nc_map_put(m, desc, key, value);
}

void __nc_map_get(void* out, nc_map* m, nc_map_desc* desc, const void* key) {
    if (__nc_map_lookup(m, desc, key, out)) {
        return;
    }
    memset(out, 0, (size_t)desc->value_size);
}

int __nc_map_has(nc_map* m, nc_map_desc* desc, const void* key) {
    return __nc_map_lookup(m, desc, key, NULL);
}

void __nc_map_delete(nc_map* m, nc_map_desc* desc, const void* key) {
    if (!m->cap) return;
    if (!m->desc) m->desc = desc;
    int64_t idx = __nc_map_hash(m->desc, key, m->cap);
    for (int64_t i = 0; i < m->cap; i++) {
        unsigned char* entry = __nc_map_entry_at(m, idx);
        int* state = __nc_map_state_ptr(m, entry);
        if (*state == 0) return;
        if (*state == 1 && m->desc->eq(key, __nc_map_key_ptr(m, entry))) {
            memset(entry, 0, (size_t)m->desc->entry_size);
            *state = 2;
            m->len--;
            m->tombstones++;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

void __nc_map_clear(nc_map* m) {
    if (!m->cap) return;
    memset(m->entries, 0, (size_t)m->cap * (size_t)m->desc->entry_size);
    m->len = 0;
    m->tombstones = 0;
}

int64_t __nc_map_next(nc_map* m, int64_t start, void* key_out, void* value_out) {
    if (!m->cap || !m->desc || start < 0) return -1;
    for (int64_t idx = start; idx < m->cap; idx++) {
        unsigned char* entry = __nc_map_entry_at(m, idx);
        if (*__nc_map_state_ptr(m, entry) == 1) {
            memcpy(key_out, __nc_map_key_ptr(m, entry), (size_t)m->desc->key_size);
            memcpy(value_out, __nc_map_value_ptr(m, entry), (size_t)m->desc->value_size);
            return idx;
        }
    }
    return -1;
}
