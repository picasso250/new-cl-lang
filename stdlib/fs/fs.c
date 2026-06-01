#include <stdio.h>

#ifdef _WIN32
#include <direct.h>
#include <io.h>
#else
#include <unistd.h>
#include <sys/stat.h>
#endif

int __nc_fs_exists(const char* path) {
#ifdef _WIN32
    return _access(path, 0) == 0;
#else
    return access(path, F_OK) == 0;
#endif
}

int __nc_fs_remove(const char* path) {
    if (remove(path) == 0) {
        return 0;
    }
#ifdef _WIN32
    return _rmdir(path);
#else
    return rmdir(path);
#endif
}

int __nc_fs_rename(const char* old_path, const char* new_path) {
    return rename(old_path, new_path);
}

int __nc_fs_mkdir(const char* path) {
#ifdef _WIN32
    return _mkdir(path);
#else
    return mkdir(path, 0777);
#endif
}
