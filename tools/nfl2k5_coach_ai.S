/* Preserve the displaced native ABI, including flags and stdcall cleanup. */
.intel_syntax noprefix
.text
.global source, resource, setup, takeover, controller_commit, cleanup, matchup, viewer, setup_native, career_address
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
    call coach_defer_rebind
    popad
    popfd
    ret
controller_commit:
    /* Preserve the native stdcall team argument and its ret 4 cleanup. */
    push dword ptr [esp+4]
    call controller_native
    pushfd
    pushad
    cld
    call coach_rebind
    popad
    popfd
    ret 4
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

/* F6E60 has initialized the playback context. Only automatic bindings
 * suppress the virtual-controller flag; the native explicit VIP path stays. */
.global presentation, offense, defense
presentation:
    pushfd
    pushad
    cld
    mov ecx, edi
    call coach_presentation
    popad
    popfd
    jmp presentation_continue
offense:
    pushfd
    pushad
    sub esp, 16
    cld
    mov ecx, ebx
    mov edx, esp
    call coach_choose
    test eax, eax
    jz offense_miss
    mov eax, [esp]
    mov [esp+32], eax /* saved EBX: category */
    mov eax, [esp+4]
    mov [esp+16], eax /* saved EDI: formation */
    mov eax, [esp+8]
    mov [esp+20], eax /* saved ESI: play */
    add esp, 16
    popad
    popfd
    jmp offense_publish
offense_miss:
    add esp, 16
    popad
    popfd
    je offense_special
    jmp offense_continue
defense:
    pushfd
    pushad
    sub esp, 16
    cld
    mov ecx, ebx
    mov edx, esp
    call coach_choose
    test eax, eax
    jz defense_miss
    mov eax, [esp]
    mov [esp+16], eax /* saved EDI: category */
    mov eax, [esp+4]
    mov [esp+20], eax /* saved ESI: formation */
    mov eax, [esp+8]
    mov [esp+68], eax /* native frame +16: front */
    mov eax, [esp+12]
    mov [esp+24], eax /* saved EBP: coverage */
    add esp, 16
    popad
    popfd
    jmp defense_publish
defense_miss:
    add esp, 16
    popad
    popfd
    jne defense_ordinary
    jmp defense_continue
.section .note.GNU-stack,"",@progbits
