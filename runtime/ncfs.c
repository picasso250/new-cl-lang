#include "ncrt.h"

#include <stdio.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#else
#include <unistd.h>
#endif

int __nc_fs_support_exists(const char* path) {
    struct stat st;
    return stat(path, &st) == 0 ? 1 : 0;
}

int __nc_fs_support_remove(const char* path) {
    if (remove(path) == 0) return 0;
#ifdef _WIN32
    return _rmdir(path) == 0 ? 0 : 1;
#else
    return rmdir(path) == 0 ? 0 : 1;
#endif
}

int __nc_fs_support_rename(const char* old_path, const char* new_path) {
    if (__nc_fs_support_exists(new_path)) return 1;
    return rename(old_path, new_path) == 0 ? 0 : 1;
}

int __nc_fs_support_mkdir(const char* path) {
#ifdef _WIN32
    return _mkdir(path) == 0 ? 0 : 1;
#else
    return mkdir(path, 0777) == 0 ? 0 : 1;
#endif
}
