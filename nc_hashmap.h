// nc_hashmap.h — 开放地址法 + FNV-1a，键为 str
// 单头文件，零依赖

#ifndef NC_HASHMAP_H
#define NC_HASHMAP_H

#include <stddef.h>

typedef struct {
    const char* _ptr;
    long long _len;
} str;

// ——— 值类型 ———
typedef enum {
    NC_VAL_NIL = 0,
    NC_VAL_I32,
    NC_VAL_STR,
    NC_VAL_PTR,
} nc_val_tag;

typedef struct {
    nc_val_tag tag;
    union {
        long long i;
        str s;
        void* p;
    };
} nc_val;

// ——— 条目 ———
typedef struct {
    str         key;
    nc_val      value;
    int         state;  // 0=empty, 1=occupied, 2=tombstone
} nc_entry;

// ——— 哈希表 ———
typedef struct {
    nc_entry*   entries;
    long long   cap;
    long long   len;
    long long   tombstones;
} nc_map;

// ——— API ———
void nc_map_init(nc_map* m);
void nc_map_free(nc_map* m);
void nc_map_put(nc_map* m, str key, nc_val value);
int  nc_map_get(const nc_map* m, str key, nc_val* out);
int  nc_map_contains(const nc_map* m, str key);
void nc_map_remove(nc_map* m, str key);

// 遍历: for (long long _i = 0; _i < m.cap; _i++) if (m.entries[_i].state == 1) ...
#define NC_MAP_FOR(key_var, val_var, m)                                  \
    for (long long _i = 0; _i < (m).cap; _i++)                           \
        if ((m).entries[_i].state == 1 &&                                \
            ((key_var) = (m).entries[_i].key,                            \
             (val_var) = (m).entries[_i].value, 1))

#endif
