#ifndef _WIN32
#include <stdint.h>
#include <unistd.h>
#include <sys/syscall.h>

int32_t __nc_linux_getpid(void) {
    return (int32_t)syscall(SYS_getpid);
}

int64_t __nc_linux_write(int32_t fd, const void* data, uint64_t len) {
    return (int64_t)syscall(SYS_write, fd, data, len);
}
#endif
