#include "ncrt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
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
    if (__nc_gc_alloc_since_collect + payload_size >= 65536) {
        __nc_gc_collect();
    }
    __nc_gc_block* b = (__nc_gc_block*)calloc(1, sizeof(__nc_gc_block) + payload_size);
    if (!b) __nc_abort_oom();
    b->size = payload_size;
    b->next = __nc_gc_blocks;
    __nc_gc_blocks = b;
    __nc_gc_live_count++;
    __nc_gc_alloc_since_collect += payload_size;
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

// ── green thread stack ─────────────────────────────────────

// Assembly offset guard — must stay in sync with ncrt_switch_win64.S
// These are verified at compile time.
_Static_assert(offsetof(nc_green_thread, rsp)       == 24,  "rsp offset");
_Static_assert(offsetof(nc_green_thread, rbx)       == 48,  "rbx offset");
_Static_assert(offsetof(nc_green_thread, rbp)       == 56,  "rbp offset");
_Static_assert(offsetof(nc_green_thread, rdi)       == 64,  "rdi offset");
_Static_assert(offsetof(nc_green_thread, rsi)       == 72,  "rsi offset");
_Static_assert(offsetof(nc_green_thread, r12)       == 80,  "r12 offset");
_Static_assert(offsetof(nc_green_thread, r13)       == 88,  "r13 offset");
_Static_assert(offsetof(nc_green_thread, r14)       == 96,  "r14 offset");
_Static_assert(offsetof(nc_green_thread, r15)       == 104, "r15 offset");
_Static_assert(offsetof(nc_green_thread, xmm_save)  == 112, "xmm_save offset");
_Static_assert(offsetof(nc_green_thread, entry_fn)  == 304, "entry_fn offset");
_Static_assert(offsetof(nc_green_thread, entry_arg) == 312, "entry_arg offset");

#ifdef _WIN32
#include <windows.h>
#endif

size_t __nc_page_size(void) {
#ifdef _WIN32
    SYSTEM_INFO info;
    GetSystemInfo(&info);
    return info.dwPageSize;
#else
    long sz = sysconf(_SC_PAGESIZE);
    return sz > 0 ? (size_t)sz : 4096;
#endif
}

#ifdef _WIN32

nc_green_thread* __nc_g_alloc(void (*fn)(void*), void* arg) {
    nc_green_thread* g = (nc_green_thread*)malloc(sizeof(nc_green_thread));
    if (!g) return NULL;

    size_t page_size  = __nc_page_size();
    size_t guard_size = page_size * NC_G_GUARD_PAGES;
    size_t total      = guard_size + NC_G_STACK_SIZE;

    void* region = VirtualAlloc(NULL, total, MEM_RESERVE, PAGE_NOACCESS);
    if (!region) {
        free(g);
        return NULL;
    }

    // commit usable stack
    void* usable = (char*)region + guard_size;
    if (!VirtualAlloc(usable, NC_G_STACK_SIZE, MEM_COMMIT, PAGE_READWRITE)) {
        VirtualFree(region, 0, MEM_RELEASE);
        free(g);
        return NULL;
    }

    memset(g, 0, sizeof(nc_green_thread));
    g->state        = G_RUNNABLE;
    g->stack_region = region;
    g->stack_top    = (char*)usable + NC_G_STACK_SIZE;
    g->rsp          = g->stack_top;   // Phase 1 placeholder; Phase 2 constructs call frame
    g->stack_size   = NC_G_STACK_SIZE;
    g->guard_size   = guard_size;
    g->gc_root_handle = -1;
    g->entry_fn     = fn;
    g->entry_arg    = arg;

    return g;
}

void __nc_g_free(nc_green_thread* g) {
    if (!g) return;
    if (g->stack_region) {
        VirtualFree(g->stack_region, 0, MEM_RELEASE);
    }
    free(g);
}

#else  // Linux / SysV

#include <sys/mman.h>
#include <unistd.h>

nc_green_thread* __nc_g_alloc(void (*fn)(void*), void* arg) {
    nc_green_thread* g = (nc_green_thread*)malloc(sizeof(nc_green_thread));
    if (!g) return NULL;

    size_t page_size  = __nc_page_size();
    size_t guard_size = page_size * NC_G_GUARD_PAGES;
    size_t total      = guard_size + NC_G_STACK_SIZE;

    void* region = mmap(NULL, total, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (region == MAP_FAILED) {
        free(g);
        return NULL;
    }

    // guard page(s)
    if (mprotect(region, guard_size, PROT_NONE) != 0) {
        munmap(region, total);
        free(g);
        return NULL;
    }

    memset(g, 0, sizeof(nc_green_thread));
    g->state        = G_RUNNABLE;
    g->stack_region = region;
    g->stack_top    = (char*)region + total;
    g->rsp          = g->stack_top;   // Phase 1 placeholder; Phase 2 constructs call frame
    g->stack_size   = NC_G_STACK_SIZE;
    g->guard_size   = guard_size;
    g->gc_root_handle = -1;
    g->entry_fn     = fn;
    g->entry_arg    = arg;

    return g;
}

void __nc_g_free(nc_green_thread* g) {
    if (!g) return;
    if (g->stack_region) {
        munmap(g->stack_region, g->guard_size + g->stack_size);
    }
    free(g);
}

#endif

// ── common (platform-independent) ──────────────────────────

void __nc_g_init_stack(nc_green_thread* g) {
    // Build initial stack frame so that __nc_g_switch rets into the trampoline.
    //
    // Layout (stack grows downward from stack_top):
    //   [stack_top - 48]  return address → __nc_g_entry_trampoline
    //   [stack_top - 40]  G pointer (trampoline will pop into first arg reg)
    //   [stack_top - 8]   top of 32-byte reserved area (padding for alignment;
    //                     the trampoline allocates its own shadow space before
    //                     calling entry_fn)

    char* sp = (char*)g->stack_top;

    // reserved area (32 bytes — not entry_fn shadow; trampoline handles that)
    sp -= 32;
    memset(sp, 0, 32);

    // G pointer
    sp -= 8;
    *(void**)sp = g;

    // return address
    sp -= 8;
    *(void**)sp = (void*)__nc_g_entry_trampoline;

    g->rsp = sp;
}

// ── scheduler ─────────────────────────────────────────────

#ifdef _WIN32
#include <windows.h>
#include <process.h>

typedef struct {
    CRITICAL_SECTION cs;
    CONDITION_VARIABLE cv;
    int accepting;            // 1 = accept new Gs, 0 = draining
    int live_workers;
    long long live_g_count;   // Gs not yet DEAD
    HANDLE* handles;
} nc_sched;

static nc_sched sched = {{0}};
static int sched_inited = 0;

static void sched_ensure_init(void) {
    if (sched_inited) return;
    sched_inited = 1;
#ifdef _WIN32
    InitializeCriticalSection(&sched.cs);
    InitializeConditionVariable(&sched.cv);
#endif
}

#define SCHED_LOCK()       EnterCriticalSection(&sched.cs)
#define SCHED_UNLOCK()     LeaveCriticalSection(&sched.cs)
#define SCHED_WAIT()       SleepConditionVariableCS(&sched.cv, &sched.cs, INFINITE)
#define SCHED_SIGNAL()     WakeConditionVariable(&sched.cv)
#define SCHED_BROADCAST()  WakeAllConditionVariable(&sched.cv)

#else
#include <pthread.h>

typedef struct {
    pthread_mutex_t mu;
    pthread_cond_t  cv;
    int accepting;
    int live_workers;
    long long live_g_count;
    pthread_t* handles;
} nc_sched;

static nc_sched sched = {PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0, 0, 0, NULL};

#define SCHED_LOCK()       pthread_mutex_lock(&sched.mu)
#define SCHED_UNLOCK()     pthread_mutex_unlock(&sched.mu)
#define SCHED_WAIT()       pthread_cond_wait(&sched.cv, &sched.mu)
#define SCHED_SIGNAL()     pthread_cond_signal(&sched.cv)
#define SCHED_BROADCAST()  pthread_cond_broadcast(&sched.cv)

#endif

typedef struct nc_worker {
    nc_green_thread sched_g;   // worker's scheduler context (on stack)
    nc_green_thread* current_g;
    int id;
} nc_worker;

static __thread nc_worker* current_worker = NULL;

static nc_green_thread* run_head = NULL;
static nc_green_thread* run_tail = NULL;

// internal: yield re-enqueue (no live_g_count change)
static void runq_push_existing(nc_green_thread* g) {
    g->run_next = NULL;
    // caller holds SCHED_LOCK
    if (run_tail) {
        run_tail->run_next = g;
    } else {
        run_head = g;
    }
    run_tail = g;
}

static nc_green_thread* runq_pop_locked(void) {
    // caller holds SCHED_LOCK
    nc_green_thread* g = run_head;
    if (g) {
        run_head = g->run_next;
        if (!run_head) run_tail = NULL;
        g->run_next = NULL;
    }
    return g;
}

static int runq_empty_locked(void) {
    return run_head == NULL;
}

// public: first enqueue of a new G (live_g_count++)
void __nc_scheduler_submit(nc_green_thread* g) {
    g->run_next = NULL;
    sched_ensure_init();
    SCHED_LOCK();
    if (run_tail) {
        run_tail->run_next = g;
    } else {
        run_head = g;
    }
    run_tail = g;
    sched.live_g_count++;
    SCHED_SIGNAL();
    SCHED_UNLOCK();
}

int __nc_runq_empty(void) {
    sched_ensure_init();
    SCHED_LOCK();
    int e = runq_empty_locked();
    SCHED_UNLOCK();
    return e;
}

void __nc_g_yield(void) {
    if (!current_worker || !current_worker->current_g) {
        fprintf(stderr, "__nc_g_yield: called outside scheduler\n");
        abort();
    }
    nc_worker* w = current_worker;
    nc_green_thread* g = w->current_g;
    g->state = G_RUNNABLE;
    SCHED_LOCK();
    runq_push_existing(g);
    SCHED_SIGNAL();
    SCHED_UNLOCK();
    __nc_g_switch(g, &w->sched_g);
}

static void g_finish_dead(nc_green_thread* g) {
    SCHED_LOCK();
    if (sched.live_g_count <= 0) abort();
    sched.live_g_count--;
    if (sched.live_g_count == 0) {
        SCHED_BROADCAST();
    }
    SCHED_UNLOCK();
    if (g->gc_root_handle >= 0) {
        __nc_gc_drop_root(g->gc_root_handle);
        g->gc_root_handle = -1;
    }
}

void __nc_g_exit(void) {
    if (!current_worker || !current_worker->current_g) {
        exit(0);
    }
    nc_worker* w = current_worker;
    nc_green_thread* g = w->current_g;
    g->state = G_DEAD;
    __nc_g_switch(g, &w->sched_g);
    abort();
}

void __nc_spawn(void (*fn)(void*), void* env) {
    nc_green_thread* g = __nc_g_alloc(fn, env);
    if (!g) abort();
    __nc_g_init_stack(g);
    g->gc_root_handle = -1;
    if (env) {
        g->gc_root_handle = __nc_gc_push_root_slot(&g->entry_arg);
    }
    __nc_scheduler_submit(g);
}

// Phase 5 forward declarations
static void wake_expired_timers(void);
static uint64_t timer_next_deadline_ms(void);
static int  timer_has_pending(void);

static void worker_loop(void* arg) {
    nc_worker* w = (nc_worker*)arg;
    current_worker = w;

    while (1) {
        SCHED_LOCK();

        wake_expired_timers();

        uint64_t timeout_ms = timer_next_deadline_ms();
        while (runq_empty_locked() && (sched.accepting || timer_has_pending())) {
#ifdef _WIN32
            if (timeout_ms > 0) {
                DWORD dw = (DWORD)(timeout_ms < 0x7FFFFFFF ? timeout_ms : 0x7FFFFFFF);
                SleepConditionVariableCS(&sched.cv, &sched.cs, dw);
            } else {
                SCHED_WAIT();
            }
#else
            if (timeout_ms > 0) {
                struct timespec ts;
                clock_gettime(CLOCK_REALTIME, &ts);
                ts.tv_sec += timeout_ms / 1000;
                ts.tv_nsec += (timeout_ms % 1000) * 1000000;
                if (ts.tv_nsec >= 1000000000) {
                    ts.tv_sec++;
                    ts.tv_nsec -= 1000000000;
                }
                pthread_cond_timedwait(&sched.cv, &sched.mu, &ts);
            } else {
                SCHED_WAIT();
            }
#endif
            wake_expired_timers();
            timeout_ms = timer_next_deadline_ms();
        }

        nc_green_thread* g = runq_pop_locked();
        if (g) {
            SCHED_UNLOCK();
            w->current_g = g;
            g->state = G_RUNNING;
            __nc_g_switch(&w->sched_g, g);
            w->current_g = NULL;

            if (g->state == G_DEAD) {
                g_finish_dead(g);
                __nc_g_free(g);
            }
            continue;
        }

        // run queue empty: check if we can exit
        // cannot exit if there are pending timers
        if (!sched.accepting && !timer_has_pending()) {
            sched.live_workers--;
            SCHED_UNLOCK();
            current_worker = NULL;
            free(w);
            return;
        }
    }
}

#ifdef _WIN32
static unsigned __stdcall worker_thread(void* arg) {
    worker_loop(arg);
    return 0;
}
#else
static void* worker_thread(void* arg) {
    worker_loop(arg);
    return NULL;
}
#endif

void __nc_scheduler_init(int num_workers) {
    sched_ensure_init();
    SCHED_LOCK();
    sched.accepting = 1;
    sched.live_workers = num_workers;
    SCHED_UNLOCK();

#ifdef _WIN32
    sched.handles = (HANDLE*)malloc((size_t)num_workers * sizeof(HANDLE));
#else
    sched.handles = (pthread_t*)malloc((size_t)num_workers * sizeof(pthread_t));
#endif
    if (!sched.handles) abort();

    for (int i = 0; i < num_workers; i++) {
        nc_worker* w = (nc_worker*)malloc(sizeof(nc_worker));
        if (!w) abort();
        memset(w, 0, sizeof(*w));
        w->id = i;

#ifdef _WIN32
        HANDLE h = (HANDLE)_beginthreadex(NULL, 0, worker_thread, w, 0, NULL);
        if (!h) abort();
        sched.handles[i] = h;
#else
        pthread_t t;
        if (pthread_create(&t, NULL, worker_thread, w) != 0) abort();
        sched.handles[i] = t;
#endif
    }
}

void __nc_scheduler_run(void) {
    // Phase 3a compatibility: single-threaded inline scheduler
    sched_ensure_init();
    nc_worker w = {0};
    current_worker = &w;
    sched.accepting = 1;

    while (1) {
        SCHED_LOCK();
        wake_expired_timers();
        nc_green_thread* g = runq_pop_locked();
        SCHED_UNLOCK();
        if (!g) {
            // check once more: anything pending?
            SCHED_LOCK();
            if (timer_has_pending()) {
                // wait a bit for timers to expire
                SCHED_UNLOCK();
                Sleep(1);
                continue;
            }
            SCHED_UNLOCK();
            break;
        }

        w.current_g = g;
        g->state = G_RUNNING;
        __nc_g_switch(&w.sched_g, g);
        w.current_g = NULL;

        if (g->state == G_DEAD) {
            g_finish_dead(g);
            __nc_g_free(g);
        }
    }

    current_worker = NULL;
    sched.accepting = 0;
}

void __nc_scheduler_shutdown(void) {
    SCHED_LOCK();
    sched.accepting = 0;

    // drain: wait until all live Gs complete
    while (sched.live_g_count > 0) {
        SCHED_BROADCAST();
        SCHED_WAIT();
    }

    // stop workers
    SCHED_BROADCAST();
    int n = sched.live_workers;
    SCHED_UNLOCK();

    // join all workers
    for (int i = 0; i < n; i++) {
#ifdef _WIN32
        WaitForSingleObject(sched.handles[i], INFINITE);
        CloseHandle(sched.handles[i]);
#else
        pthread_join(sched.handles[i], NULL);
#endif
    }
    free(sched.handles);
    sched.handles = NULL;
}

/* ═══════════════════════════════════════════════════════════
 * Phase 5: Mutex + Sleep/Timer
 * ═══════════════════════════════════════════════════════════ */

// ── monotonic wall clock (milliseconds) ────────────────────

static uint64_t nc_tick_ms(void) {
#ifdef _WIN32
    return GetTickCount64();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
#endif
}

// ── mutex internal lock ────────────────────────────────────

static void mutex_lock_internal(nc_mutex* m) {
#ifdef _WIN32
    EnterCriticalSection((CRITICAL_SECTION*)m->cs);
#else
    pthread_mutex_lock(&m->mu);
#endif
}

static void mutex_unlock_internal(nc_mutex* m) {
#ifdef _WIN32
    LeaveCriticalSection((CRITICAL_SECTION*)m->cs);
#else
    pthread_mutex_unlock(&m->mu);
#endif
}

// ── mutex alloc / free ─────────────────────────────────────

nc_mutex* __nc_mutex_alloc(void) {
    nc_mutex* m = (nc_mutex*)calloc(1, sizeof(nc_mutex));
    if (!m) __nc_abort_oom();
#ifdef _WIN32
    CRITICAL_SECTION* cs = (CRITICAL_SECTION*)malloc(sizeof(CRITICAL_SECTION));
    if (!cs) __nc_abort_oom();
    InitializeCriticalSection(cs);
    m->cs = cs;
#else
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr);
    pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_NORMAL);
    pthread_mutex_init(&m->mu, &attr);
    pthread_mutexattr_destroy(&attr);
#endif
    return m;
}

void __nc_mutex_free(nc_mutex* m) {
    if (!m) return;
#ifdef _WIN32
    if (m->cs) {
        DeleteCriticalSection((CRITICAL_SECTION*)m->cs);
        free(m->cs);
    }
#else
    pthread_mutex_destroy(&m->mu);
#endif
    free(m);
}

// ── mutex park: atomically park G + release internal lock ──

static void nc_mutex_park_and_unlock(nc_mutex* m) {
    nc_worker* w = current_worker;
    nc_green_thread* g = w->current_g;

    // Append to mutex wait queue
    if (m->tail) {
        m->tail->wait_next = g;
    } else {
        m->head = g;
    }
    m->tail = g;
    g->wait_next = NULL;
    g->state = G_WAIT_MUTEX;

    // Release internal lock BEFORE switching to scheduler
    mutex_unlock_internal(m);

    // Switch to scheduler; resumes when this G is dequeued by unlock
    __nc_g_switch(g, &w->sched_g);
}

// ── mutex lock / unlock ────────────────────────────────────

void __nc_mutex_lock(nc_mutex* m) {
    mutex_lock_internal(m);
    if (m->locked == 0) {
        m->locked = 1;
        mutex_unlock_internal(m);
        return;
    }
    // Lock held — park this G and wait for handoff
    nc_mutex_park_and_unlock(m);
    // Resumed here via handoff: we now own the lock (locked still == 1)
}

void __nc_mutex_unlock(nc_mutex* m) {
    mutex_lock_internal(m);
    if (m->head) {
        // Handoff: dequeue first waiter, keep locked=1
        nc_green_thread* g = m->head;
        m->head = g->wait_next;
        if (!m->head) m->tail = NULL;
        g->wait_next = NULL;
        g->state = G_RUNNABLE;
        SCHED_LOCK();
        runq_push_existing(g);
        SCHED_SIGNAL();
        SCHED_UNLOCK();
        // locked stays 1 (handoff to g)
    } else {
        m->locked = 0;
    }
    mutex_unlock_internal(m);
}

// ── timer / sleep ──────────────────────────────────────────

typedef struct nc_timer {
    uint64_t           deadline;
    nc_green_thread*   g;
    struct nc_timer*   next;
} nc_timer;

static nc_timer* timer_head;

static int timer_has_pending(void) {
    return timer_head != NULL;
}

static uint64_t timer_next_deadline_ms(void) {
    // caller holds SCHED_LOCK; returns ms until next deadline, or 0
    if (!timer_head) return 0;
    uint64_t now = nc_tick_ms();
    if (timer_head->deadline <= now) return 0;
    return timer_head->deadline - now;
}

static void wake_expired_timers(void) {
    // caller holds SCHED_LOCK
    uint64_t now = nc_tick_ms();
    while (timer_head && timer_head->deadline <= now) {
        nc_timer* t = timer_head;
        timer_head = t->next;
        t->g->state = G_RUNNABLE;
        runq_push_existing(t->g);
        free(t);
    }
}

void __nc_sleep(uint64_t ms) {
    if (!current_worker || !current_worker->current_g) {
        fprintf(stderr, "__nc_sleep: called outside scheduler\n");
        abort();
    }
    nc_worker* w = current_worker;
    nc_green_thread* g = w->current_g;

    uint64_t deadline = nc_tick_ms() + ms;

    nc_timer* t = (nc_timer*)malloc(sizeof(nc_timer));
    if (!t) __nc_abort_oom();
    t->deadline = deadline;
    t->g = g;

    SCHED_LOCK();

    // Insert sorted by deadline (ascending)
    nc_timer** link = &timer_head;
    while (*link && (*link)->deadline <= deadline) {
        link = &(*link)->next;
    }
    t->next = *link;
    *link = t;

    // If we inserted at head, signal a sleeping worker
    if (timer_head == t) {
        SCHED_SIGNAL();
    }

    g->state = G_WAIT_TIMER;
    SCHED_UNLOCK();

    // Switch to scheduler (no lock held)
    __nc_g_switch(g, &w->sched_g);
    // Resumed after timer expired and G was re-enqueued
}
