#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

/* Phase 5: sync.Mutex test — two Gs increment a shared counter */
/* Uses single-threaded scheduler (Phase 3a compat) */

static nc_mutex* g_mu;
static volatile int g_counter;

static void inc_worker(void* _) {
    for (int i = 0; i < 1000; i++) {
        __nc_mutex_lock(g_mu);
        int v = g_counter;
        __nc_g_yield();  // force preemption inside critical section
        g_counter = v + 1;
        __nc_mutex_unlock(g_mu);
    }
}

int main(void) {
    __nc_gc_init();
    g_mu = __nc_mutex_alloc();
    g_counter = 0;

    nc_green_thread* g1 = __nc_g_alloc(inc_worker, NULL);
    nc_green_thread* g2 = __nc_g_alloc(inc_worker, NULL);
    __nc_g_init_stack(g1);
    __nc_g_init_stack(g2);

    __nc_scheduler_submit(g1);
    __nc_scheduler_submit(g2);

    __nc_scheduler_run();

    printf("counter = %d (expected 2000)\n", g_counter);
    assert(g_counter == 2000);

    __nc_mutex_free(g_mu);
    printf("=== PASS: mutex lock/unlock + yield inside CS ===\n");
    return 0;
}
