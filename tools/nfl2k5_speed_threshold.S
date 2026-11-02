/* Optional vertical man-coverage speed differential. Offline proposal only.
 * FUN_238020 epilogue: ECX=player, [ESP]=native speed, [ESP+24]=command.
 * Return ABI and all registers/flags/x87 state match the stolen instructions.
 * Only the function-local result can change. No rating/steering/task writes.
 */
.intel_syntax noprefix
.code32
.text
.global entry, native, constants, code_end
.extern setting, native_tail
entry:
    pushfd
    pushad
    movzx ebx, byte ptr [setting]
    test ebx, ebx
    jz native
    cmp ebx, 100
    ja native
    cmp dword ptr [0xe602b8], 14
    jne native
    cmp dword ptr [ecx+0x1c], 1
    jne native
    mov eax, [0xe60284]
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
    cmp dword ptr [edx+0x1c], 0
    jne native
    mov esi, [ecx+0x10]
    test esi, esi
    jz native
    cmp dword ptr [esi+4], 0x50f4ec
    jne native
    test byte ptr [esi+0x28], 3
    jnz native
    /* Settled run only. First-step and acceleration command stay native. */
    cmp dword ptr [esi+0x54], 0x3f600000 /* .875 */
    jb native
    cmp dword ptr [esi+0x54], 0x3f800000
    ja native
    cmp dword ptr [esp+60], 0x3f600000 /* original command */
    jb native
    cmp dword ptr [esp+60], 0x3f800000
    ja native
    mov eax, [ecx+0x20]
    test eax, eax
    jz native
    mov eax, [eax+0x310]
    test eax, eax
    jz native
    cmp eax, -1
    je native
    cmp dword ptr [eax], 0x1a4830 /* established man task only */
    jne native
    mov edi, [eax+0x40]
    test edi, edi
    jz native
    cmp edi, -1
    je native
    cmp edi, ecx
    je native
    cmp dword ptr [edi+0x1c], 1
    jne native
    mov eax, [0xe60280]
    test eax, eax
    jz native
    cmp eax, [ecx+0x38]
    je native
    cmp [edi+0x38], eax
    jne native
    mov eax, [eax+8]
    test eax, eax
    jz native
    mov eax, [eax+12]
    test eax, eax
    jz native
    mov eax, [eax+4] /* attack direction, exactly +1 or -1 */
    mov edx, eax
    and edx, 0x7fffffff
    cmp edx, 0x3f800000
    jne native
    mov edx, eax
    shr edx, 16
    and edx, 0x8000
    /* Body AND requested headings within 22.5 degrees of downfield.
     * A newly requested cut exits before the body has begun turning. */
    push eax
    mov eax, [ecx+0x0c]
    mov eax, [eax+0x14]
    sub ax, dx
    add ax, 4096
    cmp ax, 8192
    ja pop_direction
    mov eax, [esi+0x0c]
    sub ax, dx
    add ax, 4096
    cmp ax, 8192
    ja pop_direction
    mov esi, [edi+0x10]
    test esi, esi
    jz pop_direction
    cmp dword ptr [esi+4], 0x50f4ec
    jne pop_direction
    test byte ptr [esi+0x28], 3
    jnz pop_direction
    mov eax, [esi+0x0c]
    sub ax, dx
    add ax, 4096
    cmp ax, 8192
    ja pop_direction
    mov eax, [edi+0x0c]
    test eax, eax
    jz pop_direction
    cmp eax, -1
    je pop_direction
    cmp dword ptr [eax+0x1c], 0
    jne pop_direction
    mov eax, [eax+0x14]
    sub ax, dx
    add ax, 4096
    cmp ax, 8192
    ja pop_direction
    mov eax, [ecx+0x3c]
    test eax, eax
    jz pop_direction
    cmp eax, -1
    je pop_direction
    movzx esi, byte ptr [eax+0x36]
    mov eax, [edi+0x3c]
    test eax, eax
    jz pop_direction
    cmp eax, -1
    je pop_direction
    movzx eax, byte ptr [eax+0x36]
    cmp eax, 127
    ja pop_direction
    sub eax, esi
    jle pop_direction
    cmp eax, 25 /* maximum additional reduction 25% */
    jbe gap
    mov eax, 25
gap:
    imul ebx, eax
    mov edi, [edi+0x18]
    test edi, edi
    jz pop_direction
    mov edx, [0xe602ec]
    test edx, edx
    jz pop_direction
    /* Reject nonfinite coordinates/velocity before arithmetic. */
    mov eax, [edi+0x38]
    and eax, 0x7fffffff
    cmp eax, 0x49742400 /* 1 million world units */
    jae pop_direction
    mov eax, [edx+0x18]
    and eax, 0x7fffffff
    cmp eax, 0x49742400
    jae pop_direction
    mov eax, [edi+0x48]
    mov esi, [esp]
    and esi, 0x80000000
    xor eax, esi
    test eax, eax
    js pop_direction
    and eax, 0x7fffffff
    cmp eax, 0x438928f6 /* moving downfield >= 3 yd/s */
    jb pop_direction
    cmp eax, 0x44bb8000 /* <=1500 world units/s */
    ja pop_direction
    mov eax, [esp+40] /* native result, positive and finite */
    test eax, eax
    jle pop_direction
    cmp eax, 0x44bb8000
    ja pop_direction
    mov ebp, esp
    sub esp, 120
    fnsave [esp] /* saves caller x87, initializes private arithmetic */
    mov [esp+108], ebx
    fld dword ptr [edi+0x38]
    fsub dword ptr [edx+0x18]
    fmul dword ptr [ebp]
    fsub dword ptr [constants] /* depth - 8 yd */
    fstp dword ptr [esp+112]
    mov eax, [esp+112]
    test eax, eax
    jle restore
    cmp eax, dword ptr [constants+4] /* ramp over next 4 yd */
    jbe ramp
    mov eax, [constants+4]
    mov [esp+112], eax
ramp:
    fild dword ptr [esp+108]
    fmul dword ptr [constants+8] /* setting*gap/10000 */
    fmul dword ptr [esp+112]
    fdiv dword ptr [constants+4]
    fsubr dword ptr [constants+12] /* 1 - reduction */
    fmul dword ptr [ebp+40]
    fstp dword ptr [ebp+40]
restore:
    frstor [esp]
    mov esp, ebp
pop_direction:
    add esp, 4
native:
    popad
    popfd
    fld dword ptr [esp]
    add esp, 20
    jmp native_tail
.balign 4, 0xcc
constants:
    .float 731.52, 365.76, 0.0001, 1.0
code_end:
