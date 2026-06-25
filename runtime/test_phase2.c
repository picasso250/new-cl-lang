#include "ncrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static nc_green_thread* g1;
static nc_green_thread* g2;

// ── basic switch test ──────────────────────────────────────

static void g1_entry(void* arg) {
    (void)arg;
    printf("G1: A\n");
    __nc_g_switch(g1, g2);
    printf("G1: C\n");
}

static void g2_entry(void* arg) {
    (void)arg;
    printf("G2: B\n");
    __nc_g_switch(g2, g1);
}

static int test_basic_switch(void) {
    g1 = __nc_g_alloc(g1_entry, NULL);
    g2 = __nc_g_alloc(g2_entry, NULL);
    if (!g1 || !g2) return 1;

    __nc_g_init_stack(g1);
    __nc_g_init_stack(g2);

    printf("main: switching to G1\n");
    nc_green_thread dummy = {0};
    __nc_g_switch(&dummy, g1);
    // trampoline calls exit(0) — never returns
    return 1;
}

// ── register pattern test ──────────────────────────────────
// Verifies RBX/R12/R15 survive a G1→G2→G1 round-trip.
// XMM6-15 are saved/restored by the assembly but not yet
// pattern-tested (future Phase).

static nc_green_thread* rg1;
static nc_green_thread* rg2;
static int reg_ok = 1;

#define PAT_GPR ((unsigned long long)0xDEADBEEFCAFE0001ULL)

static void rg1_entry(void* arg) {
    (void)arg;

    __asm__ volatile(
        "movq %0, %%rbx\n\t"
        "movq %0, %%r12\n\t"
        "movq %0, %%r15\n\t"
        :
        : "i"(PAT_GPR)
        : "rbx", "r12", "r15"
    );

    __nc_g_switch(rg1, rg2);

    unsigned long long v_rbx, v_r12, v_r15;
    __asm__ volatile(
        "movq %%rbx, %0\n\t"
        "movq %%r12, %1\n\t"
        "movq %%r15, %2\n\t"
        : "=r"(v_rbx), "=r"(v_r12), "=r"(v_r15)
        :
        : "rbx", "r12", "r15"
    );

    if (v_rbx != PAT_GPR) { printf("FAIL: RBX\n"); reg_ok = 0; }
    if (v_r12 != PAT_GPR) { printf("FAIL: R12\n"); reg_ok = 0; }
    if (v_r15 != PAT_GPR) { printf("FAIL: R15\n"); reg_ok = 0; }

    if (reg_ok) printf("PASS: RBX/R12/R15 preserved across switch\n");
}

static void rg2_entry(void* arg) {
    (void)arg;

    unsigned long long clob = 0xBAADF00DBAADF00DULL;
    __asm__ volatile(
        "movq %0, %%rbx\n\t"
        "movq %0, %%r12\n\t"
        "movq %0, %%r15\n\t"
        :
        : "r"(clob)
        : "rbx", "r12", "r15"
    );

    __nc_g_switch(rg2, rg1);
}

static int test_register_preservation(void) {
    rg1 = __nc_g_alloc(rg1_entry, NULL);
    rg2 = __nc_g_alloc(rg2_entry, NULL);
    if (!rg1 || !rg2) return 1;

    __nc_g_init_stack(rg1);
    __nc_g_init_stack(rg2);

    nc_green_thread dummy = {0};
    __nc_g_switch(&dummy, rg1);
    return reg_ok ? 0 : 1;
}

// ── main ───────────────────────────────────────────────────

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s basic|regs\n", argv[0]);
        return 2;
    }

    printf("=== Phase 2: Win64 context switch ===\n\n");

    if (strcmp(argv[1], "basic") == 0) {
        return test_basic_switch();
    }
    if (strcmp(argv[1], "regs") == 0) {
        return test_register_preservation();
    }

    fprintf(stderr, "unknown mode: %s\n", argv[1]);
    return 2;
}
