#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>

/* Phase 6: deadlock detection
 * G1: locks muA, yields, tries muB → blocks
 * G2: locks muB, tries muA → blocks
 * classic deadlock → __nc_scheduler_run detects immediately
 */

static nc_mutex* muA;
static nc_mutex* muB;

static void g1_fn(void* _) {
    __nc_mutex_lock(muA);
    __nc_g_yield();
    __nc_mutex_lock(muB);
    __nc_mutex_unlock(muB);
    __nc_mutex_unlock(muA);
}

static void g2_fn(void* _) {
    __nc_mutex_lock(muB);
    __nc_mutex_lock(muA);
    __nc_mutex_unlock(muA);
    __nc_mutex_unlock(muB);
}

int main(void) {
    __nc_gc_init();
    muA = __nc_mutex_alloc();
    muB = __nc_mutex_alloc();

    nc_green_thread* g1 = __nc_g_alloc(g1_fn, NULL);
    nc_green_thread* g2 = __nc_g_alloc(g2_fn, NULL);
    __nc_g_init_stack(g1);
    __nc_g_init_stack(g2);

    __nc_scheduler_submit(g1);
    __nc_scheduler_submit(g2);

    __nc_scheduler_run();

    printf("UNEXPECTED: no deadlock detected\n");
    return 1;
}
