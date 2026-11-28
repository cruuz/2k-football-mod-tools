.intel_syntax noprefix
.code32
.section .text
.global passing_scale
passing_scale:
    pushfd
    push eax
    push 0
    cmp dword ptr [0xe5ff80], 4
    jne original
    mov eax, dword ptr [0xe576a4]
    sub eax, 7
    cmp eax, 2
    ja original
    mov eax, dword ptr [0xa9719c]
    test eax, eax
    jz original
    mov eax, dword ptr [eax+8]
    test eax, eax
    jz original
    cmp byte ptr [eax+0x35], 0
    jne original
    test dword ptr [eax+0x20], 0xbfc00000
    jnz original
    test dword ptr [eax+0x24], 0x70000000
    jnz original
    fst dword ptr [esp]
    cmp dword ptr [esp], 0
    jle original
    movzx eax, byte ptr [eax+0x42]
    cmp eax, 100
    ja original
    fmul dword ptr [RATING_TABLE+4*eax]
    jmp finish
original:
    fmul dword ptr [BASE_MULTIPLIER]
finish:
    lea esp, [esp+4]
    pop eax
    popfd
    ret
.section .note.GNU-stack,"",@progbits
