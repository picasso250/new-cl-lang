#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_align_errors = 0;
static int g_state_errors = 0;

static void dummy_entry(void* arg) {
    (void)arg;
}

int main(void) {
    printf("=== Phase 1: G struct + stack alloc ===\n");

    // 1. verify constants
    printf("G stack size  : %zu\n", (size_t)NC_G_STACK_SIZE);
    printf("G guard size  : %zu\n", (size_t)NC_G_GUARD_SIZE);
    printf("sizeof(G)     : %zu\n", sizeof(nc_green_thread));

    // 2. single alloc
    nc_green_thread* g = __nc_g_alloc(dummy_entry, NULL);
    if (!g) {
        fprintf(stderr, "FAIL: __nc_g_alloc returned NULL\n");
        return 1;
    }
    printf("PASS: single alloc\n");
    printf("  stack_region : %p\n", g->stack_region);
    printf("  stack_top    : %p\n", g->stack_top);
    printf("  rsp          : %p\n", g->rsp);
    printf("  state        : %d (expect G_RUNNABLE=%d)\n", g->state, G_RUNNABLE);

    // 3. alignment check
    uintptr_t top = (uintptr_t)g->stack_top;
    if (top % 16 != 0) {
        fprintf(stderr, "FAIL: stack_top not 16-byte aligned: %p\n", g->stack_top);
        g_align_errors++;
    } else {
        printf("PASS: stack_top 16-byte aligned\n");
    }
    __nc_g_free(g);

    // 4. bulk alloc
    #define BULK 1000
    nc_green_thread* bulk[BULK];
    for (int i = 0; i < BULK; i++) {
        bulk[i] = __nc_g_alloc(dummy_entry, NULL);
        if (!bulk[i]) {
            fprintf(stderr, "FAIL: bulk alloc[%d] returned NULL\n", i);
            return 1;
        }
        if (bulk[i]->state != G_RUNNABLE) {
            g_state_errors++;
        }
        uintptr_t t = (uintptr_t)bulk[i]->stack_top;
        if (t % 16 != 0) {
            g_align_errors++;
        }
        if (bulk[i]->entry_fn != dummy_entry) {
            g_state_errors++;
        }
    }
    printf("PASS: bulk alloc %d Gs\n", BULK);
    printf("  alignment errors: %d\n", g_align_errors);
    printf("  state errors    : %d\n", g_state_errors);

    // 5. verify stacks don't overlap
    for (int i = 0; i < BULK; i++) {
        uintptr_t base_i = (uintptr_t)bulk[i]->stack_region;
        uintptr_t size_i = NC_G_GUARD_SIZE + NC_G_STACK_SIZE;
        for (int j = i + 1; j < BULK; j++) {
            uintptr_t base_j = (uintptr_t)bulk[j]->stack_region;
            if (base_i + size_i > base_j && base_j + size_i > base_i) {
                fprintf(stderr, "FAIL: overlapping regions [%d] and [%d]\n", i, j);
                return 1;
            }
        }
    }
    printf("PASS: no overlapping stacks\n");

    // 6. free
    for (int i = 0; i < BULK; i++) {
        __nc_g_free(bulk[i]);
    }
    printf("PASS: all freed\n");

    int total_errors = g_align_errors + g_state_errors;
    printf("\n=== %s (%d errors) ===\n",
           total_errors == 0 ? "ALL PASS" : "SOME FAIL",
           total_errors);
    return total_errors;
}
