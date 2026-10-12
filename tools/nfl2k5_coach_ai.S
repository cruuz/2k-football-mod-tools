/* Preserve the displaced native ABI, including flags and stdcall cleanup. */
.intel_syntax noprefix
.text
.global source, resource, setup, takeover, cleanup, matchup, viewer, setup_native, career_address
source:
    pushfd
    pushad
    cld
    call coach_validate_source
    popad
    popfd
    push ebx
    push esi
    push edi
    mov edi, edx
    mov esi, ecx
    jmp source_continue
resource:
    pushfd
    pushad
    cld
    call coach_validate_source
    popad
    popfd
    push ebx
    push ebp
    push esi
    mov esi, ecx
    jmp resource_continue
setup:
    pushfd
    pushad
    cld
    mov ecx, edi
    mov edx, [esp+64]
    push dword ptr [esp+60]
    call coach_prepare
    test eax, eax
    jz 1f
    mov dword ptr [esp+4], 4
1:
    popad
    popfd
    mov ecx, [esp+28]
    mov eax, [ecx*4+0xba04b0]
    jmp setup_continue
takeover:
    call takeover_native
    pushfd
    pushad
    cld
    call coach_rebind
    popad
    popfd
    ret
cleanup:
    pushfd
    pushad
    cld
    call coach_cleanup
    popad
    popfd
    mov ecx, 0xe6162c
    jmp cleanup_continue
setup_native:
    push edi
    mov edi, ecx
    mov eax, ecx
    push edx
    push dword ptr [esp+12]
    lea ecx, [edx+1]
    push ecx
    call setup_original
    mov ecx, edi
    call stats_bind_native
    pop edi
    ret 4
matchup:
    cmp edx, 2
    jae matchup_original
    pushfd
    pushad
    cld
    imul edx, edx, 0x58
    cmp dword ptr [edx+0xcc2478], 0
    jne matchup_miss
    mov ecx, [edx+0xcc2470]
    mov edx, 0xeb958c
    call coach_portrait
    test eax, eax
    jz matchup_miss
    mov [esp+28], eax
    popad
    popfd
    sub esp, 0x84
    jmp matchup_finish
matchup_miss:
    popad
    popfd
matchup_original:
    imul edx, edx, 0x58
    mov edx, [edx+0xcc2478]
    jmp matchup_continue
viewer:
    pushfd
    pushad
    cld
    mov ecx, [0xcb9208]
    cmp ecx, 4
    jae viewer_miss
    imul ecx, ecx, 0x1278
    add ecx, 0xbdfcf0
    mov edx, 0xeafb64
    call coach_portrait
    test eax, eax
    jz viewer_miss
    mov [esp+28], eax
    popad
    popfd
    jmp viewer_finish
viewer_miss:
    popad
    popfd
    cmp dword ptr [0xcb9208], -1
    jmp viewer_continue
.balign 4
career_address:
    .long career_state
.section .note.GNU-stack,"",@progbits
