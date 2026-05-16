// nc_gc.h — STW 三色标记-清除 GC（精确根集）
#ifndef NC_GC_H
#define NC_GC_H

#include <stddef.h>
#include <stdint.h>

typedef struct _nc_record {
    void*              ptr;
    size_t             size;
    uint8_t            marked;
    struct _nc_record* next;
} nc_record_t;

void  nc_gc_init(void);
void* nc_gc_alloc(size_t size);
void  nc_gc_collect(void);
int   nc_gc_push_root(void* ptr);   // 返回句柄
void  nc_gc_pop_root(void);
void  nc_gc_drop_root(int handle);
size_t nc_gc_live(void);

#define NC_GC_NEW(T)  ((T*)nc_gc_alloc(sizeof(T)))

#endif
