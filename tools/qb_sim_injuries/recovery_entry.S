.intel_syntax noprefix
.code32
.section .text
.global depth_hook, match_hook
depth_hook:
    pushfd
    pushad
    push edi
    push esi
    call before_partition
    add esp,8
    popad
    popfd
    call qb_depth_helper
    pushfd
    pushad
    push edi
    push esi
    call after_partition
    add esp,8
    popad
    popfd
    ret
match_hook:
    pushfd
    pushad
    lea eax,[esp+36]
    push eax
    push edx
    push ecx
    call prepare_match
    add esp,12
    popad
    popfd
    mov dword ptr [esp], OFFSET match_initialized
    jmp 0x10b280
.global match_initialized
match_initialized:
    pushfd
    pushad
    call restore_match
    popad
    popfd
    jmp 0x10b95f
.section .note.GNU-stack,"",@progbits
