/* EXPERIMENTAL / UNWITNESSED. GNU as --32, Intel syntax.
 * Rebuild the checked-in Python byte template with tools/nfl2k5_momentum_assemble.py.
 * Runtime patching needs only Python, never an assembler.
 * Slot (64 bytes): entity, state, roster, tick, filtered, run frames, state age,
 * valid, sampled vx/vz, pair, bonus, resolver EBP, reserved[3].
 * state_data starts with 16 bytes (overflow counter, reserved), then 32 slots.
 */
.intel_syntax noprefix
.code32
.text
.global dispatch, contact_first, contact_later, config, code_end
.extern state_data
.extern retail_dispatch, retail_attribute

/* No dispatcher stack arguments. Preserve the original stack alignment at the
 * trampoline, then capture either the ordinary RET or its tail-call RET.
 * EBP locals: steer, raw throttle, raw heading, filtered, heading, slot.
 */
dispatch:
    /* 1CD5D0's retail/kickoff prologue has already saved ESI/EDI. Undo
     * those two pushes, then wrap the complete dispatcher from its entry ABI. */
    pop edi
    pop esi
    push ebp
    mov ebp, esp
    lea esp, [esp-24]
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov dword ptr [ebp-4], 0
    mov dword ptr [ebp-24], 0
    mov ebx, ecx
    call find_slot
    test edi, edi
    jz prepared
    mov [ebp-24], edi
    call eligible
    jnc invalidate
    mov [ebp-4], edx
    mov eax, [edx+0x10]
    mov [ebp-8], eax
    mov eax, [edx+0x14]
    mov [ebp-12], eax
    mov ecx, [0xb71d10]
    mov eax, [ebx+0x3c]
    cmp [edi+4], esi
    jne reset
    cmp [edi+8], eax
    jne reset
    mov eax, [esi+8]
    cmp eax, [edi+24]
    jb reset
    cmp dword ptr [edi+28], 1
    jne reset
    mov eax, ecx
    sub eax, [edi+12]
    cmp eax, 1
    ja reset
    test eax, eax
    jz substitute
    jmp sample
reset:
    mov [edi+4], esi
    mov eax, [ebx+0x3c]
    mov [edi+8], eax
    mov dword ptr [edi+20], 0
    mov dword ptr [edi+28], 1
sample:
    mov [edi+12], ecx
    mov eax, [esi+8]
    mov [edi+24], eax
    /* q is retail's prior effective command. No extra acceleration ramp. */
    fld dword ptr [esi+0x1b8]
    fmul dword ptr [config+8]
    fsubr dword ptr [config+4]
    fdivr dword ptr [0xb71d0c]
    fsubr dword ptr [esi+0x54]
    fld dword ptr [edx+0x10]
    fcomi st, st(1)
    fcmovb st, st(1)
    fstp dword ptr [edi+16]
    fstp st(0)
    /* Sample horizontal velocity once per simulation tick, before contact. */
    mov eax, [ebx+0x18]
    mov ecx, [eax+0x40]
    mov [edi+32], ecx
    mov ecx, [eax+0x48]
    mov [edi+36], ecx
    fld dword ptr [edi+32]
    fmul st, st(0)
    fld dword ptr [edi+36]
    fmul st, st(0)
    faddp st(1), st
    fcomp dword ptr [config+12]
    fnstsw ax
    test ah, 0x45
    jnz slow
    cmp dword ptr [edi+20], 21
    jae substitute
    inc dword ptr [edi+20]
    jmp substitute
slow:
    mov dword ptr [edi+20], 0
substitute:
    mov eax, [edi+16]
    cmp eax, [edx+0x10]
    jae throttle_ready
    mov eax, [edx+0x10]
throttle_ready:
    mov [edx+0x10], eax
    mov [ebp-16], eax
    mov eax, [ebp-12]
    cmp dword ptr [ebp-8], 0
    jne heading
    mov eax, [esi+0xc]
heading:
    mov [edx+0x14], eax
    mov [ebp-20], eax
    jmp prepared
invalidate:
    mov dword ptr [edi+28], 0
    mov dword ptr [edi+20], 0
prepared:
    frstor [esp]
    add esp, 108
    popad
    popfd
    call trampoline
after_dispatch:
    pushfd
    pushad
    mov edx, [ebp-4]
    test edx, edx
    jz restored
    /* Restore only our unchanged substitutions, never retail command writes. */
    mov eax, [ebp-16]
    cmp [edx+0x10], eax
    jne restore_heading
    mov eax, [ebp-8]
    mov [edx+0x10], eax
restore_heading:
    mov eax, [ebp-20]
    cmp [edx+0x14], eax
    jne restored
    mov eax, [ebp-12]
    mov [edx+0x14], eax
restored:
    /* Invalidate any transition, including one inside the tail callback. */
    mov edi, [ebp-24]
    test edi, edi
    jz finish
    mov ebx, [edi]
    call eligible
    jc finish
    mov dword ptr [edi+28], 0
    mov dword ptr [edi+20], 0
finish:
    popad
    popfd
    mov esp, ebp
    pop ebp
    ret
trampoline:
    push esi
    push edi
    mov edi, ecx
    mov eax, [edi+0xc]
    mov esi, [edi+0x10]
    mov ecx, [eax+0x1c]
    jmp retail_dispatch

/* Input EBX=P. Output ESI=S, EDX=T, CF=eligible. No controller-index gate.
 * Only current/requested command 0, ordinary descriptor, stable locomotion 1,
 * live phase 14, no alternate facing, and bounded finite q/throttle/Agility/dt.
 * Null/sentinel owned structure pointers fall back to retail.
 */
eligible:
    clc
    cmp dword ptr [0xe602b8], 14
    jne no
    cmp dword ptr [ebx+0x1c], 1
    jne no
    mov esi, [ebx+0x10]
    mov edx, [ebx+0xc]
    lea eax, [esi-1]
    cmp eax, -3
    jae no
    lea eax, [edx-1]
    cmp eax, -3
    jae no
    cmp dword ptr [esi], 0
    jne no
    cmp dword ptr [edx+0x1c], 0
    jne no
    cmp dword ptr [esi+4], 0x50f4ec
    jne no
    test byte ptr [esi+0x28], 3
    jnz no
    mov eax, [esi+0x1c]
    lea ecx, [eax-1]
    cmp ecx, -3
    jae no
    cmp dword ptr [eax], 1
    jne no
    cmp dword ptr [esi+0x54], 0x3f800000
    ja no
    cmp dword ptr [edx+0x10], 0x3f800000
    ja no
    cmp dword ptr [esi+0x1b8], 0x3f800000
    ja no
    mov eax, [0xb71d0c]
    dec eax
    cmp eax, 0x3dcccccc-1 /* 0 < dt <= .1 */
    ja no
    stc
    ret
no:
    clc
    ret

/* Full scan, no hash aliasing. Reuse only slots absent for >1 ticks.
 * Invalidated slots retain identity until stale so same-frame reentry is safe.
 */
find_slot:
    mov edi, offset state_data+16
    xor edx, edx
    mov ecx, 32
scan:
    cmp [edi], ebx
    je found
    cmp dword ptr [edi], 0
    je candidate
    mov eax, [0xb71d10]
    sub eax, [edi+12]
    cmp eax, 1
    jbe next
candidate:
    mov edx, edi
next:
    add edi, 64
    loop scan
    mov edi, edx
    test edi, edi
    jz overflow
    mov [edi], ebx
    mov dword ptr [edi+28], 0
found:
    ret
overflow:
    inc dword ptr [state_data]
    ret

/* Both attribute calls retain the original ret-4 convention and call the
 * retail accessor with its modifier unchanged. No SSE registers are touched.
 * Preserve the complete x87 environment while calculating the bonus, then
 * add just one bounded scalar to the accessor's single returned value.
 */
contact_first:
    lea esp, [esp-8]
    push dword ptr [esp+12]
    call retail_attribute
    lea esp, [esp+8]
    pushfd
    pushad
    sub esp, 112
    fnsave [esp]
    mov ebx, esi
    call find_slot
    test edi, edi
    jz contact_done
    mov dword ptr [edi+44], 0
    mov eax, [ebp+8]
    mov [edi+40], eax
    mov [edi+48], ebp
    call contact_valid
    jnc contact_done
    /* Run history is sampled once per tick. At this first resolver read,
     * sample current pre-resolution velocity and cache the bonus for both reads. */
    mov edx, [ebp+8]
    mov edx, [edx+0x18]
    mov eax, [ebx+0x18]
    fld dword ptr [edx]
    fsub dword ptr [eax]
    fld st(0)
    fmul st, st(0)
    fld dword ptr [edx+8]
    fsub dword ptr [eax+8]
    fld st(0)
    fmul st, st(0)
    faddp st(2), st
    fmul dword ptr [eax+0x48]
    fxch st(2)
    fmul dword ptr [eax+0x40]
    faddp st(2), st
    fsqrt
    fdivp st(1), st
    fsub dword ptr [config+16]
    fmul dword ptr [config+20]
    /* Store and integer-check: nonfinite, negative or zero => no bonus. */
    fstp dword ptr [esp+108]
    mov eax, [esp+108]
    test eax, eax
    jle contact_done
    cmp eax, 0x7f800000
    jae contact_done
    cmp eax, 0x3f800000
    jbe bounded
    mov dword ptr [esp+108], 0x3f800000
bounded:
    fld dword ptr [esp+108]
    fmul st, st(0)
    fimul dword ptr [edi+20]
    fmul dword ptr [config+24]
    fstp dword ptr [edi+44]
contact_done:
    frstor [esp]
    add esp, 112
    popad
    popfd
    jmp add_bonus
contact_later:
    lea esp, [esp-8]
    push dword ptr [esp+12]
    call retail_attribute
    lea esp, [esp+8]
add_bonus:
    pushfd
    pushad
    mov ebx, esi
    call find_slot
    test edi, edi
    jz bonus_end
    call contact_valid
    jnc bonus_end
    cmp [edi+48], ebp
    jne bonus_end
    mov eax, [ebp+8]
    cmp [edi+40], eax
    jne bonus_end
    fadd dword ptr [edi+44]
    fld1
    fcomi st, st(1)
    fcmovnbe st, st(1)
    fstp st(1)
bonus_end:
    popad
    popfd
    ret 4
contact_valid:
    call eligible
    jnc invalid_contact
    cmp dword ptr [edi+28], 1
    jne invalid_contact
    cmp [edi+4], esi
    jne invalid_contact
    mov eax, [ebx+0x3c]
    cmp [edi+8], eax
    jne invalid_contact
    mov eax, [0xb71d10]
    cmp [edi+12], eax
    jne invalid_contact
    /* Retail attached-player predicate from FUN_001ce280. */
    mov eax, [0xe5fc00]
    test eax, eax
    jz invalid_contact
    cmp [eax], ebx
    jne invalid_contact
    stc
    ret
invalid_contact:
    clc
    ret
.balign 4, 0xcc
config:
    .long 0 /* level 1..100, contact in bit 8 */
    .float 0.4, 0.12 /* m*.4, m*.12 => t_stop */
    .float 251410.0 /* (.55 * reference_speed)^2, replaced by builder */
    .float 501.411, 0.002437 /* .55*vref, 1/(.45*vref) */
    .float 0.0038095238 /* .08*m /21 */
code_end:
