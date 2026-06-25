# NC runtime — Win64 context switch
# Intel syntax, MinGW/GCC assembler
#
# void __nc_g_switch(nc_green_thread* current, nc_green_thread* next);
#   RCX = current, RDX = next
#
# Offsets in nc_green_thread:
#   rsp            24
#   rbx            48
#   rbp            56
#   rdi            64
#   rsi            72
#   r12            80
#   r13            88
#   r14            96
#   r15           104
#   xmm_save      112  (10 x 16 bytes = 160 bytes)
#   entry_fn      296
#   entry_arg     304

    .intel_syntax noprefix
    .globl  __nc_g_switch
    .globl  __nc_g_entry_trampoline

__nc_g_switch:
    # save callee-saved GPRs to current (RCX)
    mov     [rcx + 48],  rbx
    mov     [rcx + 56],  rbp
    mov     [rcx + 64],  rdi
    mov     [rcx + 72],  rsi
    mov     [rcx + 80],  r12
    mov     [rcx + 88],  r13
    mov     [rcx + 96],  r14
    mov     [rcx + 104], r15

    # save RSP
    mov     [rcx + 24],  rsp

    # save XMM6–XMM15 to current->xmm_save
    movaps  [rcx + 112],      xmm6
    movaps  [rcx + 112 + 16], xmm7
    movaps  [rcx + 112 + 32], xmm8
    movaps  [rcx + 112 + 48], xmm9
    movaps  [rcx + 112 + 64], xmm10
    movaps  [rcx + 112 + 80], xmm11
    movaps  [rcx + 112 + 96], xmm12
    movaps  [rcx + 112 + 112], xmm13
    movaps  [rcx + 112 + 128], xmm14
    movaps  [rcx + 112 + 144], xmm15

    # restore next (RDX)
    mov     rbx,  [rdx + 48]
    mov     rbp,  [rdx + 56]
    mov     rdi,  [rdx + 64]
    mov     rsi,  [rdx + 72]
    mov     r12,  [rdx + 80]
    mov     r13,  [rdx + 88]
    mov     r14,  [rdx + 96]
    mov     r15,  [rdx + 104]

    mov     rsp,  [rdx + 24]

    movaps  xmm6,  [rdx + 112]
    movaps  xmm7,  [rdx + 112 + 16]
    movaps  xmm8,  [rdx + 112 + 32]
    movaps  xmm9,  [rdx + 112 + 48]
    movaps  xmm10, [rdx + 112 + 64]
    movaps  xmm11, [rdx + 112 + 80]
    movaps  xmm12, [rdx + 112 + 96]
    movaps  xmm13, [rdx + 112 + 112]
    movaps  xmm14, [rdx + 112 + 128]
    movaps  xmm15, [rdx + 112 + 144]

    ret

# Entry trampoline for a new green thread.
# Entered via ret from __nc_g_switch into a newly-allocated G.
# Stack on entry:
#   [RSP + 0]  = G pointer
#   [RSP - 32] = call space (32 bytes)
# After pop rcx, RSP points to call space.
__nc_g_entry_trampoline:
    pop     rcx                     # RCX = G pointer
    mov     rax, [rcx + 296]        # G->entry_fn
    mov     rdx, [rcx + 304]        # G->entry_arg
    sub     rsp, 32                 # allocate shadow space
    call    rax                     # entry_fn(entry_arg)
    add     rsp, 32
    # Phase 3+: __nc_g_exit — for now, exit process
    mov     ecx, 0
    call    exit
