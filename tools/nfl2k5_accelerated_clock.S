/* Build-time Madden-style accelerated clock. No retail timer flags changed.
 * RX instructions, RO two-word options, RW per-snap latch; no .text state.
 * Preserve native GPRs/EFLAGS, x87, XMM0..3 and MXCSR at completion.
 */
.intel_syntax noprefix
.code32
.text
.global complete, stop_clock, period_reset, no_huddle, code_end
.extern options, latch, native_restart, stop_tail, period_tail, no_huddle_tail

complete:
    call native_restart
    pushfd
    cmp dword ptr [options], 1
    jne complete_flags
    pushad
    cmp dword ptr [latch], 0
    jne complete_regs
    mov dword ptr [latch], 1
    cmp dword ptr [0xe602b8], 12
    jne complete_regs
    mov eax, [0xe602b4]
    sub eax, 3
    cmp eax, 1
    ja complete_regs                 /* kickoffs/toss/safety kicks excluded */
    mov edi, [0xe602c4]
    test edi, edi
    jle complete_regs
    mov ebx, [0xe60294]
    mov esi, [0xe6028c]
    test ebx, ebx
    jz complete_regs
    test esi, esi
    jz complete_regs
    test byte ptr [ebx+24], 12       /* paused or count-up play clock */
    jnz complete_regs
    mov eax, [ebx+16]
    cmp eax, 0x42200000              /* reject negative/nonfinite/>40 */
    ja complete_regs
    mov eax, [esi+16]
    cmp eax, 0x461c4000              /* reject negative/nonfinite/>10000 */
    ja complete_regs
    mov edx, [options+4]
    cmp edx, 5
    jb complete_regs
    cmp edx, 25
    ja complete_regs
    sub esp, 68
    movups [esp], xmm0
    movups [esp+16], xmm1
    movups [esp+32], xmm2
    movups [esp+48], xmm3
    stmxcsr [esp+64]
    cvtsi2ss xmm3, edx               /* exact integer minimum */
    movss xmm0, [ebx+16]
    ucomiss xmm0, xmm3
    jbe complete_simd               /* never extend a short clock */
    subss xmm0, xmm3                 /* positive runoff amount */
    movss xmm1, [esi+16]
    movaps xmm2, xmm1
    cmp edi, 1
    je half_add
    cmp edi, 3
    jne half_ready
half_add:
    mov eax, [0xe602b0]
    cmp eax, 0x461c4000
    ja complete_simd
    addss xmm2, [0xe602b0]
half_ready:
    mov eax, 120
    cvtsi2ss xmm1, eax
    ucomiss xmm2, xmm1
    jbe complete_simd               /* final two minutes, including all OT */
    test byte ptr [esi+24], 14       /* stopped/paused/count-up: play only */
    jnz play_only
    cmp dword ptr [0xe602b4], 4
    jne play_only
    mov eax, [0xe60280]
    test eax, eax
    jz complete_simd
    mov eax, [eax+12]
    test eax, eax
    jz complete_simd
    mov eax, [eax+12]
    test eax, eax
    jz complete_simd
    test dword ptr [eax+4], 0x4001c0 /* native specials and knee/spike */
    jnz play_only
    /* The <=120 guard also protects the last snap of a half. A Q1/Q3
       runoff may reach zero; the native dispatcher owns period ending. */
    movss xmm1, [esi+16]
    subss xmm1, xmm0
    xorps xmm2, xmm2
    maxss xmm1, xmm2                 /* Q1/Q3 clamp; native period end owns 0 */
    movss [esi+16], xmm1
play_only:
    movss [ebx+16], xmm3             /* exact scorebug value, one store */
complete_simd:
    ldmxcsr [esp+64]
    movups xmm0, [esp]
    movups xmm1, [esp+16]
    movups xmm2, [esp+32]
    movups xmm3, [esp+48]
    add esp, 68
complete_regs:
    popad
complete_flags:
    popfd
    ret

stop_clock:
    pushfd
    cmp dword ptr [options], 1
    jne stop_original
    cmp dword ptr [esp+4], 0xb7015  /* only successful B6F30 snap */
    jne stop_original
    mov dword ptr [latch], 0
stop_original:
    popfd
    mov ecx, [0xe60294]
    jmp stop_tail

period_reset:
    pushfd
    cmp dword ptr [options], 1
    jne period_original
    mov dword ptr [latch], 1         /* first snap of quarter never shortened */
period_original:
    popfd
    mov eax, [0xe602b0]
    jmp period_tail

no_huddle:
    pushfd
    cmp dword ptr [options], 1
    jne no_huddle_original
    mov dword ptr [latch], 1         /* also covers later native re-lineup */
no_huddle_original:
    popfd
    push ebx
    mov ebx, [0xe60284]
    jmp no_huddle_tail
code_end:
