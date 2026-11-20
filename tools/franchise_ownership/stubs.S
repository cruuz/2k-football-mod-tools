.intel_syntax noprefix
.text
.globl ownership_trade_stub, ownership_release_stub, ownership_contract_stub, ownership_store

/* Replaces the CALL to the validator in the common CPU and user trade executor. */
ownership_trade_stub:
    pushfd
    pushad
    call ownership_trade_valid
    test eax, eax
    jz invalid_trade
    popad
    popfd
    push 0x002BC380
    ret
invalid_trade:
    popad
    popfd
    xor eax, eax
    ret 8

/* 0x2BD900 takes ECX=club, EDX=player, [esp+4]=to free agency, [esp+8]=prorate.
 * Plain active removal is also used in IR placement, where the live IR owner was just added. */
ownership_release_stub:
    pushfd
    cmp DWORD PTR [esp+8], 0
    je original_remove
    pushad
    call ownership_prepare_release
    test eax, eax
    jz already_released
    popad
original_remove:
    popfd
    push esi
    push edi
    mov esi, edx
    mov edi, ecx
    push 0x002BD906
    ret
already_released:
    popad
    popfd
    xor eax, eax
    ret 8

/* Zero remaining contract years cannot be prorated. Preserve every byte of the player's
 * record and all caller state on this path. Other contracts take the original calculation. */
ownership_contract_stub:
    pushfd
    test BYTE PTR [esi+0x27], 0x0F
    jz zero_years
    popfd
    movzx ecx, WORD PTR [esi+0x0A]
    push offset converted
    push 0x000E5FF0
    ret
converted:
    push 0x002BCF69
    ret
zero_years:
    popfd
    ret

.balign 4
ownership_store:
    .long 0

.section .note.GNU-stack,"",@progbits
