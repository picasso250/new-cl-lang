#ifndef NCRT_H
#define NCRT_H

#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t* ptr;
    uint64_t len;
} str;

typedef enum {
    NC_VAL_NIL = 0,
    NC_VAL_I8,
    NC_VAL_I16,
    NC_VAL_I32,
    NC_VAL_I64,
    NC_VAL_U8,
    NC_VAL_U16,
    NC_VAL_U32,
    NC_VAL_U64,
    NC_VAL_F32,
    NC_VAL_F64,
    NC_VAL_BOOL,
    NC_VAL_RUNE,
    NC_VAL_STR
} nc_val_tag;

typedef struct {
    int32_t tag;
    uint64_t a;
    uint64_t b;
} nc_val;

typedef struct nc_entry nc_entry;

typedef struct {
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

typedef struct __nc_ex_frame {
    jmp_buf jb;
    struct __nc_ex_frame* prev;
    str ex;
} __nc_ex_frame_t;

extern __nc_ex_frame_t* __nc_ex_top;

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

str __nc_read_file(const char* path);
void __nc_write_file(const char* path, str content);
int __nc_str_eq(str a, str b);
str __nc_str_cat(str a, str b);
str __nc_str_slice_copy(str s, uint64_t start, uint64_t end);
str __nc_i32_to_str(int n);
int __nc_str_to_i32(str s);
void __nc_str_cat_out(str* out, const str* a, const str* b);
void __nc_str_slice_copy_out(str* out, const str* s, uint64_t start, uint64_t end);
void __nc_i32_to_str_out(str* out, int n);
void __nc_i64_to_str_out(str* out, int64_t n);
void __nc_u64_to_str_out(str* out, uint64_t n);
void __nc_f64_to_str_out(str* out, double n);
void __nc_rune_to_str_out(str* out, uint32_t r);
int __nc_str_to_i32_ptr(const str* s);
void __nc_read_file_out(str* out, const char* path);
void __nc_write_file_ptr(const char* path, const str* content);
int __nc_read_file_status(str* out, const char* path);
int __nc_write_file_status(const char* path, const str* content);
int __nc_str_eq_ptr(const str* a, const str* b);

void __nc_slice_copy_raw(nc_slice_raw* out, const void* src, uint64_t len, uint64_t elem_size);
void __nc_slice_append_raw(nc_slice_raw* out, const nc_slice_raw* in, const void* elem, uint64_t elem_size);

void __nc_map_init(nc_map* m);
void __nc_map_free(nc_map* m);
void __nc_map_set(nc_map* m, const nc_val* key, const nc_val* value);
void __nc_map_get(nc_val* out, nc_map* m, const nc_val* key, int32_t value_tag);
int __nc_map_has(nc_map* m, const nc_val* key);

void __nc_throw(str ex);

#endif
