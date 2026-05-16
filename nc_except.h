// nc_except.h — 异常运行时（setjmp/longjmp）
#ifndef NC_EXCEPT_H
#define NC_EXCEPT_H

#include <setjmp.h>
#include <stdio.h>

// 异常帧：try 块 push，退出/跳转时 pop
typedef struct __nc_ex_frame {
    jmp_buf             jb;
    struct __nc_ex_frame* prev;
    str                 ex_value;
} __nc_ex_frame_t;

static __nc_ex_frame_t* __nc_ex_top = NULL;

// throw：存值并跳到最近 catch
static void __nc_throw(str ex) {
    if (__nc_ex_top) {
        __nc_ex_top->ex_value = ex;
        longjmp(__nc_ex_top->jb, 1);
    }
    fprintf(stderr, "uncaught: %.*s\n", (int)ex._len, ex._ptr);
    exit(1);
}

#endif
