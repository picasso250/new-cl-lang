// nc_gc.c — STW 三色标记-清除（精确根集，无栈扫描）

#include "nc_gc.h"
#include <stdlib.h>
#include <string.h>

static nc_record_t* _gc_registry = NULL;

// 精确根集
#define GC_MAX_ROOTS 256
static struct { void* ptr; int active; } _gc_roots[GC_MAX_ROOTS];
static size_t _gc_root_count = 0;

// 灰栈
#define GC_GRAY_MAX 4096
static nc_record_t* _gc_gray[GC_GRAY_MAX];
static size_t        _gc_gray_top = 0;

// ——— 查找记录 ———
static int _is_heap_ptr(void* c) {
    if (!c) return 0;
    uintptr_t a = (uintptr_t)c;
    for (nc_record_t* r = _gc_registry; r; r = r->next)
        if (a >= (uintptr_t)r->ptr && a < (uintptr_t)r->ptr + r->size) return 1;
    return 0;
}

static nc_record_t* _find_record(void* ptr) {
    for (nc_record_t* r = _gc_registry; r; r = r->next)
        if (ptr >= r->ptr && (uintptr_t)ptr < (uintptr_t)r->ptr + r->size) return r;
    return NULL;
}

static void _gc_mark_gray(void* ptr) {
    nc_record_t* rec = _find_record(ptr);
    if (rec && rec->marked == 0) {
        rec->marked = 1;
        if (_gc_gray_top < GC_GRAY_MAX)
            _gc_gray[_gc_gray_top++] = rec;
    }
}

// ——— 扫描对象：按指针宽度扫每个对齐字 ———
static void _gc_scan(nc_record_t* rec) {
    size_t n = rec->size / sizeof(void*);
    void** w = (void**)rec->ptr;
    for (size_t i = 0; i < n; i++)
        if (w[i]) _gc_mark_gray(w[i]);
}

// ——— API ———
void nc_gc_init(void) {
    _gc_registry = NULL;
    _gc_root_count = 0;
    _gc_gray_top = 0;
}

void* nc_gc_alloc(size_t size) {
    void* ptr = calloc(1, size);
    if (!ptr) return NULL;
    nc_record_t* rec = (nc_record_t*)malloc(sizeof(nc_record_t));
    rec->ptr = ptr;
    rec->size = size;
    rec->marked = 0;
    rec->next = _gc_registry;
    _gc_registry = rec;
    return ptr;
}

// ——— 精确根操作 ———
int nc_gc_push_root(void* ptr) {
    if (!ptr || !_is_heap_ptr(ptr)) return -1;
    if (_gc_root_count >= GC_MAX_ROOTS) return -1;
    _gc_roots[_gc_root_count].ptr = ptr;
    _gc_roots[_gc_root_count].active = 1;
    return (int)_gc_root_count++;
}

void nc_gc_pop_root(void) {
    if (_gc_root_count > 0) _gc_root_count--;
}

void nc_gc_drop_root(int handle) {
    if (handle >= 0 && handle < (int)_gc_root_count)
        _gc_roots[handle].active = 0;
}

// ——— 收集 ———
void nc_gc_collect(void) {
    // 标记：从活跃根出发
    for (size_t i = 0; i < _gc_root_count; i++) {
        if (_gc_roots[i].active)
            _gc_mark_gray(_gc_roots[i].ptr);
    }

    // BFS
    while (_gc_gray_top > 0) {
        nc_record_t* rec = _gc_gray[--_gc_gray_top];
        _gc_scan(rec);
        rec->marked = 2;
    }

    // 清除
    nc_record_t** prev = &_gc_registry;
    nc_record_t* curr = _gc_registry;
    while (curr) {
        if (curr->marked == 0) {
            *prev = curr->next;
            free(curr->ptr);
            nc_record_t* dead = curr;
            curr = curr->next;
            free(dead);
        } else {
            curr->marked = 0;
            prev = &curr->next;
            curr = curr->next;
        }
    }
    _gc_gray_top = 0;

    // 压缩根集（移除已失效的）
    size_t w = 0;
    for (size_t i = 0; i < _gc_root_count; i++) {
        if (_gc_roots[i].active)
            _gc_roots[w++] = _gc_roots[i];
    }
    _gc_root_count = w;
}

size_t nc_gc_live(void) {
    size_t n = 0;
    for (nc_record_t* r = _gc_registry; r; r = r->next) n++;
    return n;
}
