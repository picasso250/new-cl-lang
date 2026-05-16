// nc_hashmap.c — 实现

#include "nc_hashmap.h"
#include <stdlib.h>
#include <string.h>

#define INIT_CAP  16
#define LOAD_MAX  0.70
#define FNV_BASIS 14695981039346656037ULL
#define FNV_PRIME 1099511628211ULL

// ——— str 相等比较 ———
static int _str_eq(str a, str b) {
    if (a._len != b._len) return 0;
    for (long long i = 0; i < a._len; i++) {
        if (a._ptr[i] != b._ptr[i]) return 0;
    }
    return 1;
}

// ——— 无分配：直接用输入指针做键（调用方保证生命周期） ———
// 如果键是栈上 str 则需拷贝，但符号表场景键全是字符串字面量或堆上切片，
// 为避免 str 拷贝开销，当前不 clone。

// ——— FNV-1a 哈希 ———
static long long _hash(str key, long long cap) {
    unsigned long long h = FNV_BASIS;
    for (long long i = 0; i < key._len; i++) {
        h ^= (unsigned char)key._ptr[i];
        h *= FNV_PRIME;
    }
    return (long long)(h % (unsigned long long)cap);
}

void nc_map_init(nc_map* m) {
    m->cap = INIT_CAP;
    m->len = 0;
    m->tombstones = 0;
    m->entries = (nc_entry*)calloc((size_t)m->cap, sizeof(nc_entry));
}

void nc_map_free(nc_map* m) {
    free(m->entries);
    m->entries = NULL;
    m->cap = 0;
    m->len = 0;
    m->tombstones = 0;
}

// ——— 重哈希 ———
static void _rehash(nc_map* m) {
    long long old_cap = m->cap;
    nc_entry* old = m->entries;
    m->cap *= 2;
    m->len = 0;
    m->tombstones = 0;
    m->entries = (nc_entry*)calloc((size_t)m->cap, sizeof(nc_entry));
    for (long long i = 0; i < old_cap; i++) {
        if (old[i].state == 1) {
            nc_map_put(m, old[i].key, old[i].value);
        }
    }
    free(old);
}

void nc_map_put(nc_map* m, str key, nc_val value) {
    // 检查负载
    if ((double)(m->len + m->tombstones) / (double)m->cap > LOAD_MAX) {
        _rehash(m);
    }

    long long idx = _hash(key, m->cap);
    long long tomb = -1;

    for (long long i = 0; i < m->cap; i++) {
        nc_entry* e = &m->entries[idx];
        if (e->state == 0) {
            // 空位 — 插入
            long long put_at = (tomb >= 0) ? tomb : idx;
            m->entries[put_at].key = key;
            m->entries[put_at].value = value;
            m->entries[put_at].state = 1;
            m->len++;
            if (tomb >= 0) m->tombstones--;
            return;
        }
        if (e->state == 2 && tomb < 0) {
            tomb = idx;
        }
        if (e->state == 1 && _str_eq(e->key, key)) {
            // 键已存在 — 覆盖值
            e->value = value;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}

int nc_map_get(const nc_map* m, str key, nc_val* out) {
    if (m->cap == 0) return 0;
    long long idx = _hash(key, m->cap);
    for (long long i = 0; i < m->cap; i++) {
        nc_entry* e = (nc_entry*)&m->entries[idx];
        if (e->state == 0) return 0;
        if (e->state == 1 && _str_eq(e->key, key)) {
            *out = e->value;
            return 1;
        }
        idx = (idx + 1) % m->cap;
    }
    return 0;
}

int nc_map_contains(const nc_map* m, str key) {
    nc_val v;
    return nc_map_get(m, key, &v);
}

void nc_map_remove(nc_map* m, str key) {
    if (m->cap == 0) return;
    long long idx = _hash(key, m->cap);
    for (long long i = 0; i < m->cap; i++) {
        nc_entry* e = &m->entries[idx];
        if (e->state == 0) return;
        if (e->state == 1 && _str_eq(e->key, key)) {
            e->state = 2;  // tombstone
            m->len--;
            m->tombstones++;
            return;
        }
        idx = (idx + 1) % m->cap;
    }
}
