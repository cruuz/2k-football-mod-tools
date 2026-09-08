/* Close pursuit turn recovery. EXPERIMENTAL / UNWITNESSED, opt-in.
 * Hook: 2FC9F0, ECX=player, [ESP+4]=positive turn units/second; ret 4.
 * The native integrator still chooses the shortest signed angle and updates
 * body, animation quaternion and transform together. We never change its
 * requested heading, task, lapse command, RNG or persistent owner state.
 * CPU ordinary locomotion only, active defense, a known man/pursuit task,
 * a live opposing target within three yards, requested turn >=90 degrees.
 * Authorize the existing turn for this tick. This is a deliberately explicit
 * fast pivot; rendered appearance and the reported man bug need Noah's test.
 */
.intel_syntax noprefix
.section .text
.global entry, restore, native, constants, code_end
.extern native_tail
entry:
    pushfd
    pushad
    test ecx, ecx
    jz native
    cmp ecx, -1
    je native
    cmp dword ptr [0xE602B8], 14
    jne native
    cmp dword ptr [ecx+0x1c], 1
    jne native
    mov eax, [0xE60284]
    test eax, eax
    jz native
    cmp [ecx+0x38], eax
    jne native
    mov edx, [ecx+0x0c]
    test edx, edx
    jz native
    cmp edx, -1
    je native
    cmp dword ptr [edx], -1
    jne native
    mov esi, [ecx+0x10]
    test esi, esi
    jz native
    cmp dword ptr [esi+4], 0x50F4EC
    jne native
    test dword ptr [esi+0x28], 3
    jnz native
    /* A queued special command must run with the original turn allowance. */
    cmp dword ptr [edx+0x1c], 0
    jne native
    mov eax, [edx+0x14]
    sub ax, word ptr [esi+0x0c]
    movsx eax, ax
    cdq
    xor eax, edx
    sub eax, edx
    cmp eax, 16384
    jb native
    mov eax, [ecx+0x20]
    test eax, eax
    jz native
    mov eax, [eax+0x310]
    test eax, eax
    jz native
    mov edx, [eax]
    cmp edx, 0x1A4830
    je target
    cmp edx, 0x1A4CF0
    je target
    cmp edx, 0x1A4DD0
    je target
    cmp edx, 0x1F4360
    je target
    cmp edx, 0x1F48F0
    je target
    cmp edx, 0x2EAB60
    je target
    cmp edx, 0x2EB300
    jne native
target:
    mov edi, [eax+0x40]
    test edi, edi
    jz native
    cmp edi, -1
    je native
    cmp edi, ecx
    je native
    cmp dword ptr [edi+0x1c], 1
    jne native
    mov eax, [0xE60280]
    test eax, eax
    jz native
    cmp eax, [ecx+0x38]
    je native
    cmp [edi+0x38], eax
    jne native
    mov edi, [edi+0x18]
    mov esi, [ecx+0x18]
    test edi, edi
    jz native
    test esi, esi
    jz native
    mov eax, [0xB71D0C]
    test eax, eax
    jle native
    cmp eax, 0x3dcccccd /* finite 0 < dt <= .1 s */
    ja native
    mov eax, [esp+40]
    test eax, eax
    js native
    cmp eax, 0x7f800000
    jae native
    mov ebp, esp
    sub esp, 112
    fnsave [esp]
    fld dword ptr [esi+0x30]
    fsub dword ptr [edi+0x30]
    fmul st(0), st(0)
    fld dword ptr [esi+0x38]
    fsub dword ptr [edi+0x38]
    fmul st(0), st(0)
    faddp st(1), st(0)
    fstp dword ptr [esp+108]
    mov eax, [esp+108]
    cmp eax, dword ptr [constants]
    ja restore /* also refuses unordered/infinite distance */
    /* Reuse the native navigation arrival distance (32.004 world units).
     * A stationary opponent already reached must not become an endless
     * sequence of half-turns. Only the native steer command is cleared;
     * the next planner tick remains free to request movement again.
     */
    cmp eax, dword ptr [constants+4]
    ja pivot
    mov eax, [edi+0x40]
    shl eax, 1 /* either signed zero is stationary */
    jnz pivot
    mov eax, [edi+0x48]
    shl eax, 1
    jnz pivot
    mov eax, [ecx+0x0c]
    mov dword ptr [eax+0x10], 0
    jmp restore
pivot:
    mov dword ptr [esp+108], 32768
    fild dword ptr [esp+108]
    fdiv dword ptr [0xB71D0C]
    fstp dword ptr [esp+108]
    mov eax, [esp+108]
    cmp eax, [ebp+40]
    jbe restore
    mov [ebp+40], eax
restore:
    frstor [esp]
    add esp, 112
native:
    popad
    popfd
    mov edx, [ecx+0x0c]
    fld dword ptr [edx+0x10]
    jmp native_tail
.balign 4, 0xcc
constants:
    .float 75251.4624 /* (3 * 91.44)^2; immutable, owned RX */
    .float 1024.256016 /* 32.004^2; native ordinary arrival distance */
code_end:
