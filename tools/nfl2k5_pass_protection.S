/* Pass protection: on pass plays a beaten blocker holds his rusher for a rating-based delay instead of 0 s.
 * Retail 0x233040 gives pass plays a zero threshold at 0x233162 (the jne at 0x233178 skips the 0.05 s run
 * constant at 0x23317A), so the first tick whose heading test passes ends the block.  This owner replaces the
 * zero store with a call that computes, on pass plays,
 *
 *     mean  = clamp(k_base + k_slope * (PassBlocking(blocker) - PassRush(defender)), k_min, k_max)
 *     delay = mean * (k_floor + k_scale * u)          u = 0..65535 from a hash of (blocker, defender, play count)
 *
 * and writes 0 on run plays (the retail/run-blocking path is untouched).  The hash is the same for every tick of
 * one engagement (the play count only moves when a play ends), so the delay is a per-engagement draw, not a
 * per-tick one; it differs between plays, so the same two players do not repeat the same result (b779-pr1).
 * EDI = blocker (offense), ESI = defender, EAX = pass flag, as 0x233040 arranges them.
 * GPRs, EFLAGS, XMM0 and the caller's ST0 (the accumulated time) are preserved. */
.intel_syntax noprefix
.code32
.text
.global pass_delay, sack_draw, sack_norm, k_base, k_slope, k_min, k_max, k_floor, k_scale, k_taper, k_start_i, k_one, code_end
.extern rating
.extern season

pass_delay:
    pushfd
    pushad
    sub esp, 32
    movups xmmword ptr [esp], xmm0           /* save XMM0 */
    fstp dword ptr [esp+16]                  /* save and pop the caller's ST0 (accumulated time) */
    mov eax, dword ptr [esp+0x3c]            /* saved EAX: 1 = pass state, 0 = run state */
    test eax, eax
    je 1f
    mov ebx, dword ptr [esp+0x20]            /* saved EDI = blocker */
    mov esi, dword ptr [esp+0x24]            /* saved ESI = defender */
    mov ecx, dword ptr [ebx+0x3c]
    push 0
    mov edx, 0x10                            /* Pass Blocking of the blocker */
    call rating
    fstp dword ptr [esp+20]
    mov ecx, dword ptr [esi+0x3c]
    push 0
    mov edx, 0x12                            /* Pass Rush of the defender */
    call rating
    fstp dword ptr [esp+24]
    movss xmm0, dword ptr [esp+20]
    subss xmm0, dword ptr [esp+24]
    mulss xmm0, dword ptr [k_slope]
    addss xmm0, dword ptr [k_base]
    maxss xmm0, dword ptr [k_min]
    minss xmm0, dword ptr [k_max]
    imul eax, ebx, 0x9E3779B1                /* hash(blocker, defender, play count) -> 16 bits */
    imul edx, esi, 0x85EBCA6B
    xor eax, edx
    imul edx, dword ptr [0xE53804], 0xC2B2AE35
    xor eax, edx
    mov edx, eax
    shr edx, 16
    xor eax, edx
    and eax, 0xFFFF
    mov dword ptr [esp+28], eax
    fild dword ptr [esp+28]                  /* u = 0..65535 */
    fmul dword ptr [k_scale]
    fadd dword ptr [k_floor]
    fstp dword ptr [esp+28]
    mulss xmm0, dword ptr [esp+28]
    movss dword ptr [esp+0x60], xmm0         /* the caller's [esp+0x18]: 32 + 36 + 4 + 0x18 */
    jmp 2f
1:
    mov dword ptr [esp+0x60], 0
2:
    movups xmm0, xmmword ptr [esp]
    fld dword ptr [esp+16]
    add esp, 32
    popad
    popfd
    ret

/* Simulated sacker draw (b779-pr1): the weight c^3 of a front-seven candidate is multiplied by
 * 1 / (1 + k_taper * max(0, season half-sacks - k_start)), so a season leader gets fewer of the next sacks and the
 * normaliser (which uses the same factor) hands them to the rest of the line.  ST0 = c on entry, c^3 * g on exit.
 * Called from 0x1037E0 (the draw, EDX = candidate) and 0x10404D (the normaliser loop, candidate = [EBX + EDI*4 + 4]).
 * Every GPR, EFLAGS and XMM0 are preserved; the x87 stack gains nothing. */
sack_draw:
    mov ecx, edx
    jmp scale_cube
sack_norm:
    mov ecx, dword ptr [ebx+edi*4+4]
scale_cube:
    pushfd
    pushad
    sub esp, 32
    movups xmmword ptr [esp], xmm0
    mov edx, 19                              /* season history field 19 = defensive sacks, in half-sacks */
    call season
    sub eax, dword ptr [k_start_i]
    jg 1f
    xor eax, eax
1:
    cvtsi2ss xmm0, eax
    mulss xmm0, dword ptr [k_taper]
    addss xmm0, dword ptr [k_one]
    movss dword ptr [esp+16], xmm0
    movss xmm0, dword ptr [k_one]
    divss xmm0, dword ptr [esp+16]
    movss dword ptr [esp+16], xmm0
    movups xmm0, xmmword ptr [esp]
    fld st(0)
    fmul st, st(1)
    fmulp st(1), st
    fmul dword ptr [esp+16]
    add esp, 32
    popad
    popfd
    ret

    .balign 4
k_base:  .float 0.60
k_slope: .float 1.40
k_min:   .float 0.10
k_max:   .float 1.80
k_floor: .float 0.55
k_scale: .float 0.0000137330
k_taper: .float 0.055
k_one:   .float 1.0
k_start_i: .long 8
code_end:
