/* Run blocking: blocks hold longer on running plays, rating against rating. EXPERIMENTAL. GNU as --32.
 *
 * Retail engaged-block tick 0x234640 asks 0x233040 each simulation tick whether the pair breaks up.
 * On a running play (blocker state +0x18C & 7 not 1/2) the defender sheds (return 2) as soon as his
 * wanted heading has pointed away from the blocker for more than 0.05 s (the immediate at 0x23317A),
 * and, once the run has declared for a controlled ball carrier (latch 0x2F3AC0(455.2)), on any tick where
 * rand < his Run Coverage (0x2331C5), which is almost every tick. The engagement start roll 0x230320 gives
 * the defender the win on rand < curve(Run Coverage) + 0.25 - curve(Run Blocking) + leverage terms.
 *
 * delay (call at 0x23317A, replacing "mov dword ptr [esp+0x18], 0.05", run plays only): the shed delay
 *   becomes clamp(k_base + k_slope * (Run Blocking(blocker) - Run Coverage(defender)), k_min, k_max)
 *   seconds; EDI = blocker (offense), ESI = defender, as 0x233040 arranges them.
 * shed_rand (call at 0x2331C5, replacing "call 0x48B90"): the same native random number times k_shed_inv,
 *   so the per-tick shed chance after the run declares is Run Coverage / k_shed_inv.
 * k_roll: the run branch of the start roll (fadd at 0x23034F) adds k_roll instead of 0.25.
 * GPRs, EFLAGS (delay), XMM0 and the x87 stack balance are preserved.
 */
.intel_syntax noprefix
.code32
.text
.global delay, shed_rand, k_roll, k_base, k_slope, k_min, k_max, k_shed_inv, code_end
.extern rating, rand

delay:
    pushfd
    pushad
    sub esp, 16
    movups xmmword ptr [esp], xmm0
    sub esp, 8
    mov ecx, [edi+0x3c]
    push 0
    mov edx, 0xf                             /* Run Blocking of the blocker */
    call rating
    fstp dword ptr [esp]
    mov ecx, [esi+0x3c]
    push 0
    mov edx, 0x13                            /* Run Coverage of the defender */
    call rating
    fstp dword ptr [esp+4]
    movss xmm0, dword ptr [esp]
    subss xmm0, dword ptr [esp+4]
    mulss xmm0, dword ptr [k_slope]
    addss xmm0, dword ptr [k_base]
    maxss xmm0, dword ptr [k_min]
    minss xmm0, dword ptr [k_max]
    movss dword ptr [esp+0x58], xmm0         /* the caller's [esp+0x18]: 8 + 16 + 32 + 4 + 4 + 0x18 */
    add esp, 8
    movups xmm0, xmmword ptr [esp]
    add esp, 16
    popad
    popfd
    ret

shed_rand:
    call rand
    fmul dword ptr [k_shed_inv]
    ret

    .balign 4
k_roll:     .float 0.15
k_base:     .float 0.30
k_slope:    .float 0.60
k_min:      .float 0.08
k_max:      .float 0.60
k_shed_inv: .float 25.0
code_end:
