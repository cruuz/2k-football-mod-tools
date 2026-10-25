/* Pass protection: on pass plays a beaten blocker holds his rusher for a rating-based delay instead of 0 s.
 * Retail 0x233040 gives pass plays a zero threshold at 0x233162 (the jne at 0x233178 skips the 0.05 s run
 * constant at 0x23317A), so the first tick whose heading test passes ends the block. This owner replaces the
 * zero store with a call that computes clamp(k_base + k_slope * (Pass Blocking(blocker) - Pass Rush(defender)),
 * k_min, k_max) on pass plays and writes 0 on run plays (the retail/run-blocking path is untouched).
 * EDI = blocker (offense), ESI = defender, EAX = pass flag, as 0x233040 arranges them.
 * GPRs, EFLAGS and the caller's ST0 (the accumulated time) are preserved. */
.intel_syntax noprefix
.code32
.text
.global pass_delay, k_base, k_slope, k_min, k_max, code_end
.extern rating

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
    movss dword ptr [esp+0x60], xmm0         /* the caller's [esp+0x18]: 68 + 0x18 + 4 */
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

    .balign 4
k_base:  .float 0.45
k_slope: .float 0.65
k_min:   .float 0.10
k_max:   .float 0.80
code_end:
