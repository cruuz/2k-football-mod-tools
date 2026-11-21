.intel_syntax noprefix
.code32
.section .text
.global fixture_start
# Original weekly-only entry retained at the established address. context.S handles both supported match callers.
fixture_start:
    pushfd
    pushad
    cmp dword ptr [esp+36],0x10b95f
    jne finish
    cmp dword ptr [esp+64],0x10b9e0
    jne finish
    cmp dword ptr [esp+88],0xc7b58
    jne finish
    cmp dword ptr [0xe5ff80],4
    jne finish
    mov eax,[0xe576a4]
    sub eax,7
    cmp eax,2
    ja finish
    mov eax,[0xe576b8]
    cmp eax,[CACHED_YEAR]
    jne finish
    mov eax,[0xe576b4]
    cmp eax,[CACHED_WEEK]
    jne finish
    mov eax,[0xb72918]
    test eax,eax
    jz finish
    mov eax,[eax+0x1c]
    sub ecx,eax
    sub edx,eax
    cmp ecx,15500
    ja finish
    cmp edx,15500
    ja finish
    cmp ecx,edx
    je finish
    jb ordered
    xchg ecx,edx
ordered:
    cmp ecx,[CACHED_CLUB_A]
    jne finish
    cmp edx,[CACHED_CLUB_B]
    jne finish
    mov dword ptr [CACHED_YEAR],-1
    mov dword ptr [POS_CACHED_YEAR],-1
finish:
    popad
    popfd
    jmp MATCH_INITIALIZER
.section .note.GNU-stack,"",@progbits
