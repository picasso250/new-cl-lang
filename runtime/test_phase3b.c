#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>

#ifdef _WIN32
#include <windows.h>
#define ATOMIC_INC(p) InterlockedIncrement((LONG volatile*)(p))
#define ATOMIC_READ(p) (*(volatile LONG*)(p))
#else
#define ATOMIC_INC(p) __sync_fetch_and_add((p), 1)
#define ATOMIC_READ(p) __sync_fetch_and_add((p), 0)
#endif

static volatile LONG g_counter = 0;
static volatile int  g_n = 2;
static volatile int  g_yields = 100;

static void worker_g(void* arg) {
    int id = (int)(intptr_t)arg;
    for (int i = 0; i < g_yields; i++) {
        ATOMIC_INC(&g_counter);
        if (i % 10 == 9) __nc_g_yield();
    }
    (void)id;
}

static int test_multi_worker(void) {
    g_counter = 0;

    for (int i = 0; i < g_n; i++) {
        nc_green_thread* g = __nc_g_alloc(worker_g, (void*)(intptr_t)i);
        __nc_g_init_stack(g);
        __nc_runq_push(g);
    }

    __nc_scheduler_init(4);  // 4 OS workers
    __nc_scheduler_shutdown();

    int expected = g_n * g_yields;
    int actual = ATOMIC_READ(&g_counter);
    if (actual != expected) {
        fprintf(stderr, "FAIL: counter=%d, expected %d\n", actual, expected);
        return 1;
    }
    printf("PASS: %d Gs × %d yields = %d (4 workers)\n", g_n, g_yields, actual);
    return 0;
}

int main(void) {
    printf("=== Phase 3b: multi-worker scheduler ===\n\n");

    int fail = 0;
    if (test_multi_worker()) fail = 1;

    printf("\n=== %s ===\n", fail ? "SOME FAIL" : "ALL PASS");
    return fail;
}
