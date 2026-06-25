#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>

static int g_step = 0;

// ── test 1: interleaved yield ──────────────────────────────

static void g1_fn(void* arg) {
    (void)arg;
    printf("G1: A\n"); g_step++;
    __nc_g_yield();
    printf("G1: C\n"); g_step++;
}

static void g2_fn(void* arg) {
    (void)arg;
    printf("G2: B\n"); g_step++;
    __nc_g_yield();
    printf("G2: D\n"); g_step++;
}

static int test_interleaved(void) {
    g_step = 0;

    nc_green_thread* a = __nc_g_alloc(g1_fn, NULL);
    nc_green_thread* b = __nc_g_alloc(g2_fn, NULL);
    __nc_g_init_stack(a);
    __nc_g_init_stack(b);
    __nc_scheduler_submit(a);
    __nc_scheduler_submit(b);

    printf("scheduler start\n");
    __nc_scheduler_run();
    printf("scheduler done\n");

    if (g_step != 4) {
        fprintf(stderr, "FAIL: g_step=%d, expected 4\n", g_step);
        return 1;
    }
    if (!__nc_runq_empty()) {
        fprintf(stderr, "FAIL: run queue not empty\n");
        return 1;
    }
    return 0;
}

// ── test 2: many yields ────────────────────────────────────

static int g_count[3];

static void many_fn_0(void* arg) { (void)arg; for (int i = 0; i < 3; i++) { g_count[0]++; __nc_g_yield(); } }
static void many_fn_1(void* arg) { (void)arg; for (int i = 0; i < 3; i++) { g_count[1]++; __nc_g_yield(); } }
static void many_fn_2(void* arg) { (void)arg; for (int i = 0; i < 3; i++) { g_count[2]++; __nc_g_yield(); } }

static int test_many_yields(void) {
    g_count[0] = g_count[1] = g_count[2] = 0;

    nc_green_thread* gs[3];
    void (*fns[])(void*) = { many_fn_0, many_fn_1, many_fn_2 };
    for (int i = 0; i < 3; i++) {
        gs[i] = __nc_g_alloc(fns[i], NULL);
        __nc_g_init_stack(gs[i]);
        __nc_scheduler_submit(gs[i]);
    }

    __nc_scheduler_run();

    if (g_count[0] != 3 || g_count[1] != 3 || g_count[2] != 3) {
        fprintf(stderr, "FAIL: counts=%d/%d/%d, expected 3/3/3\n",
                g_count[0], g_count[1], g_count[2]);
        return 1;
    }
    if (!__nc_runq_empty()) {
        fprintf(stderr, "FAIL: run queue not empty after many yields\n");
        return 1;
    }
    return 0;
}

// ── main ───────────────────────────────────────────────────

int main(void) {
    printf("=== Phase 3a: single-threaded scheduler ===\n\n");

    int fail = 0;

    printf("--- test 1: interleaved yield ---\n");
    if (test_interleaved()) fail = 1;

    printf("\n--- test 2: many yields ---\n");
    if (test_many_yields()) fail = 1;

    printf("\n=== %s ===\n", fail ? "SOME FAIL" : "ALL PASS");
    return fail;
}
