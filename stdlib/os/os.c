#ifdef _WIN32
#include <direct.h>
#else
#include <unistd.h>
#endif

char* __nc_os_getcwd(char* buf, int size) {
#ifdef _WIN32
    return _getcwd(buf, size);
#else
    return getcwd(buf, size);
#endif
}
