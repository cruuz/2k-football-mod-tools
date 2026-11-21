.intel_syntax noprefix
.code32
.section .text
.global fit
fit:
    pushfd
    push eax
    push ecx
    sub esp, 8
    cmp dword ptr [0xe5ff80], 4
    jne finish
    mov eax, dword ptr [0xe576a4]
    sub eax, 7
    cmp eax, 2
    ja finish
    mov eax, dword ptr [0xa9719c]
    test eax, eax
    jz finish
    cmp ebp, dword ptr [eax+8]
    jne finish
    cmp byte ptr [ebp+0x35], 0
    jne finish
    test dword ptr [ebp+0x20], 0xbfc00000
    jnz finish
    test dword ptr [ebp+0x24], 0x70000000
    jnz finish
    # ST(0) contains the game's just-computed thrower score from native descriptor 6.
    fst dword ptr [esp]
    mov ecx, dword ptr [esp]
    test ecx, ecx
    js finish
    cmp ecx, dword ptr [anchor]
    jae finish
    fld dword ptr [anchor]
    fsub st(0), st(1)
    mov ecx, dword ptr [0xa97200]
    cmp ecx, 0x41a00000
    jle normal_field
    cmp ecx, 0x42c80000
    jg normal_field
    fmul dword ptr [open_factor]
    mov eax, dword ptr [open_ceiling]
    jmp clip_score
normal_field:
    fmul dword ptr [factor]
    mov eax, dword ptr [ceiling]
clip_score:
    fst dword ptr [esp+4]
    mov ecx, dword ptr [esp+4]
    cmp ecx, eax
    jbe add_to_score
    fstp st(0)
    mov dword ptr [esp+4],eax
    fld dword ptr [esp+4]
add_to_score:
    faddp st(1), st(0)
finish:
    lea esp, [esp+8]
    pop ecx
    pop eax
    popfd
    mov edx, dword ptr [0xa971a0]
    ret
.balign 4,0xcc
anchor: .float .82
factor: .float .4
ceiling: .float .08
open_factor: .float .75
open_ceiling: .float .14
.section .note.GNU-stack,"",@progbits
