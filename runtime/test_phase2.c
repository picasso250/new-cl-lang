#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>

static nc_green_thread* g1;
static nc_green_thread* g2;

static void g1_entry(void* arg) {
    (void)arg;
    printf("G1: A\n");
    __nc_g_switch(g1, g2);
    printf("G1: C\n");
    // g1 done; trampoline will exit(0)
}

static void g2_entry(void* arg) {
    (void)arg;
    printf("G2: B\n");
    __nc_g_switch(g2, g1);
}

int main(void) {
    printf("=== Phase 2: Win64 context switch ===\n\n");

    g1 = __nc_g_alloc(g1_entry, NULL);
    g2 = __nc_g_alloc(g2_entry, NULL);
    if (!g1 || !g2) {
        fprintf(stderr, "FAIL: alloc\n");
        return 1;
    }

    __nc_g_init_stack(g1);
    __nc_g_init_stack(g2);

    printf("main: switching to G1\n");
    nc_green_thread dummy = {0};
    __nc_g_switch(&dummy, g1);

    // should never reach here in Phase 2
    fprintf(stderr, "FAIL: returned to main unexpectedly\n");
    return 1;
}
