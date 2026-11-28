.intel_syntax noprefix
.code32
.section .text
.global adjust
# The existing scheduled red-zone path loaded its native yard argument into ST(0).
adjust:
    pushfd
    push eax
    push ecx
    sub esp, 4
    cmp dword ptr [0xe5ff80], 4
    jne scale
    mov eax, dword ptr [0xe576a4]
    sub eax, 7
    cmp eax, 2
    ja scale
    mov eax, dword ptr [0xa9719c]
    test eax,eax
    jz scale
    mov eax,dword ptr [eax+8]
    test eax,eax
    jz scale
    cmp byte ptr [eax+0x35],0
    jne scale
    test dword ptr [eax+0x20],0xbfc00000
    jnz scale
    test dword ptr [eax+0x24],0x70000000
    jnz scale
    fst dword ptr [esp]
    cmp dword ptr [esp],0
    jle scale
    movzx ecx,byte ptr [eax+0x42]
    mov eax,85
    sub eax,ecx
    jle scale
    cmp eax,23
    jbe bounded
    mov eax,23
bounded:
    mov dword ptr [esp],eax
    fild dword ptr [esp]
    fmul dword ptr [per_point]
    fsubr dword ptr [one]
    fmulp st(1),st(0)
scale:
    fmul dword ptr [RZ_ADDR]
    lea esp,[esp+4]
    pop ecx
    pop eax
    popfd
    ret
.balign 4,0xcc
one: .float 1.0
per_point: .float 0.018
.section .note.GNU-stack,"",@progbits
