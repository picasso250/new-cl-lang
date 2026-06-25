#ifndef NCRT_H
#define NCRT_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

// ── green thread ────────────────────────────────────────────

typedef enum {
    G_RUNNABLE,
    G_RUNNING,
    G_WAIT_MUTEX,
    G_WAIT_TIMER,
    G_DEAD,
} nc_g_state;

#define NC_G_STACK_SIZE   (64 * 1024)
#define NC_G_GUARD_PAGES  1

size_t __nc_page_size(void);

// Phase 2 will construct a call-ready initial frame replacing the
// placeholder rsp = stack_top set by __nc_g_alloc.

typedef struct nc_green_thread {
    nc_g_state  state;
    void*       stack_region;  // start of entire region (guard + usable)
    void*       stack_top;     // top of usable stack
    void*       rsp;           // Phase 1: placeholder = stack_top; Phase 2: initial call frame

    size_t      stack_size;
    size_t      guard_size;

    // win64 callee-saved
    void*       rbx;
    void*       rbp;
    void*       rdi;
    void*       rsi;
    void*       r12;
    void*       r13;
    void*       r14;
    void*       r15;

    // xmm save area: 16 bytes per register × 10 regs (must be 16-byte aligned for movaps)
#ifdef _MSC_VER
    __declspec(align(16))
#endif
    uint8_t     xmm_save[160]
#ifndef _MSC_VER
    __attribute__((aligned(16)))
#endif
    ;

    // gc root handle for closure env (-1 = none)
    int         gc_root_handle;

    // time-slice
    uint64_t    start_ticks;

    // scheduling
    struct nc_green_thread* run_next;   // global run queue
    struct nc_green_thread* wait_next;  // mutex / timer wait queue
    struct nc_green_thread* all_next;   // global all-G list (for GC stack scan)

    // entry
    void (*entry_fn)(void*);
    void*       entry_arg;
} nc_green_thread;

nc_green_thread* __nc_g_alloc(void (*fn)(void*), void* arg);
void             __nc_g_free(nc_green_thread* g);
void             __nc_g_init_stack(nc_green_thread* g);

void __nc_g_switch(nc_green_thread* current, nc_green_thread* next);
void __nc_g_entry_trampoline(void);

// ── scheduler ──────────────────────────────────────────────

void __nc_scheduler_submit(nc_green_thread* g);  // first enqueue (live_g_count++)
int  __nc_runq_empty(void);

void __nc_g_yield(void);
void __nc_g_exit(void);

void __nc_scheduler_init(int num_workers);
void __nc_scheduler_run(void);                    // Phase 3a compat: inline single-thread
void __nc_scheduler_shutdown(void);               // drain all Gs, join workers

void __nc_spawn(void (*fn)(void*), void* env);

// ── mutex ──────────────────────────────────────────────────

typedef struct nc_mutex {
    int         locked;           // 0 = unlocked, 1 = locked
    nc_green_thread* head;        // wait queue (FIFO)
    nc_green_thread* tail;
#ifdef _WIN32
    void*       cs;               // CRITICAL_SECTION (heap-allocated)
#else
    pthread_mutex_t mu;
#endif
} nc_mutex;

nc_mutex* __nc_mutex_alloc(void);
void      __nc_mutex_free(nc_mutex* m);
void      __nc_mutex_lock(nc_mutex* m);
void      __nc_mutex_unlock(nc_mutex* m);

// ── sleep / timer ──────────────────────────────────────────

void __nc_sleep(uint64_t ms);

// ── existing types ──────────────────────────────────────────

typedef struct {
    uint8_t* ptr;
    uint64_t len;
} str;

typedef struct nc_entry nc_entry;
typedef uint64_t (*nc_map_hash_fn)(const void* key);
typedef int32_t (*nc_map_eq_fn)(const void* a, const void* b);

typedef struct {
    int64_t key_size;
    int64_t value_size;
    int64_t entry_size;
    int64_t key_offset;
    int64_t value_offset;
    int64_t state_offset;
    nc_map_hash_fn hash;
    nc_map_eq_fn eq;
} nc_map_desc;

typedef struct {
    nc_map_desc* desc;
    nc_entry* entries;
    int64_t cap;
    int64_t len;
    int64_t tombstones;
} nc_map;

typedef struct {
    void* ptr;
    uint64_t len;
    uint64_t cap;
} nc_slice_raw;

typedef struct {
    str function;
    str path;
    int32_t line;
    int32_t col;
} nc_error_frame;

typedef struct {
    str message;
    nc_slice_raw frames;
} nc_error;

void __nc_gc_init(void);
void* __nc_gc_alloc(size_t sz);
void __nc_gc_collect(void);
size_t __nc_gc_live(void);
int __nc_gc_push_root_slot(void* slot);
void __nc_gc_set_root(int h, void* p);
void __nc_gc_pop_root(void);
void __nc_gc_drop_root(int h);
size_t __nc_gc_root_mark(void);
void __nc_gc_root_rewind(size_t mark);

int __nc_str_eq(str a, str b);
str __nc_str_cat(str a, str b);
str __nc_str_slice_copy(str s, uint64_t start, uint64_t end);
str __nc_i32_to_str(int n);
int __nc_str_to_i32(str s);
void __nc_str_alloc_out(str* out, uint64_t len);
void __nc_str_cat_out(str* out, const str* a, const str* b);
void __nc_str_slice_copy_out(str* out, const str* s, uint64_t start, uint64_t end);
void __nc_i32_to_str_out(str* out, int n);
void __nc_i64_to_str_out(str* out, int64_t n);
void __nc_u64_to_str_out(str* out, uint64_t n);
void __nc_f32_to_str_out(str* out, float n);
void __nc_f64_to_str_out(str* out, double n);
void __nc_rune_to_str_out(str* out, uint32_t r);
float __nc_strict_str_to_f32(const uint8_t* ptr, uint64_t len);
double __nc_strict_str_to_f64(const uint8_t* ptr, uint64_t len);
int __nc_str_to_i32_ptr(const str* s);
int __nc_str_eq_ptr(const str* a, const str* b);
int32_t __nc_str_cmp_ptr(const str* a, const str* b);
void __nc_cstr_to_str_out(str* out, const char* cstr);
void __nc_os_set_args(int argc, char** argv);
int32_t __nc_argc(void);
char* __nc_argv(int32_t i);
FILE* __nc_stderr(void);
void __nc_error_from_str_out(nc_error* out, const str* message);
void __nc_error_append_frame(nc_error* err, const str* function, const str* path, int32_t line, int32_t col);
void __nc_error_print(const nc_error* err);

void __nc_slice_copy_raw(nc_slice_raw* out, const void* src, uint64_t len, uint64_t elem_size);
void __nc_slice_append_raw(nc_slice_raw* out, const nc_slice_raw* in, const void* elem, uint64_t elem_size);
int32_t __nc_slice_copy_into_raw(nc_slice_raw* dst, const nc_slice_raw* src, uint64_t elem_size);
void __nc_slice_clear_raw(nc_slice_raw* s, uint64_t elem_size);

void __nc_map_init(nc_map* m, nc_map_desc* desc);
void __nc_map_free(nc_map* m);
void __nc_map_set(nc_map* m, nc_map_desc* desc, const void* key, const void* value);
void __nc_map_get(void* out, nc_map* m, nc_map_desc* desc, const void* key);
int __nc_map_has(nc_map* m, nc_map_desc* desc, const void* key);
void __nc_map_delete(nc_map* m, nc_map_desc* desc, const void* key);
void __nc_map_clear(nc_map* m);
int64_t __nc_map_next(nc_map* m, int64_t start, void* key_out, void* value_out);

#endif
