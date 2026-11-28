/* Modern franchise injured reserve (b780 IR1): the sites that are not plain jumps to a C entry. EXPERIMENTAL.
   ir_config is the Studio-filled table at the end of the blob (nfl2k5_injured_reserve.CONFIG_FIELDS). */
    .intel_syntax noprefix
    .text
    .globl ir_save_stub, ir_load_stub, ir_config

/* 0x2D09FD in the franchise front-office writer, right after its injured reserve loop: "mov esi, 0xE3CC40", 5 bytes,
   replaced by "call ir_save_stub". ebp is the front-office buffer. */
ir_save_stub:
    pushfd
    pushad
    push ebp
    call ir_save_ext
    add esp, 4
    popad
    popfd
    mov esi, 0x00E3CC40
    ret

/* 0x2D0F70 in the front-office loader, right after its injured reserve loop: "mov dword ptr [esp + 0x10], 0", 8 bytes,
   replaced by "call ir_load_stub" and three nops. ebp is the front-office buffer. */
ir_load_stub:
    pushfd
    pushad
    push ebp
    call ir_load_ext
    add esp, 4
    popad
    popfd
    mov DWORD PTR [esp + 0x14], 0
    ret

    .balign 16
ir_config:
    .long 0x434D5249                    /* +0  "IRMC" */
    .long 1                             /* +4  version */
    .long 0                             /* +8  the store (owned writable data) */
    .long 0                             /* +12 flags */
    .long 0, 0, 0, 0                    /* +16 reserved */

/* The cap forecast uses EAX=club and ECX=slot. Its native scratch frame includes our return address. */
    .text
    .globl ir_display_count_stub, ir_display_player_stub, ir_unknown_status
ir_display_count_stub:
    push ecx
    push eax
    mov ecx, eax
    call ir_display_count
    mov edx, eax
    pop eax
    pop ecx
    ret
ir_display_player_stub:
    push ecx
    push eax
    mov edx, ecx
    mov ecx, eax
    call ir_display_player
    mov esi, eax
    pop eax
    pop ecx
    cmp esi, [esp+0x40]
    ret

/* Native 0x13E190 has no diagnosis row for unspecified real-world injuries. Keep these players
   Out while their injury clock runs, including after the weekly status recalculation. */
ir_unknown_status:
    xor eax, eax
    test word ptr [edi+0x28], 0x3ff
    jnz 1f
    cmp byte ptr [edi+0x23], 0
    jns 1f
    test dword ptr [edi+0x20], 0x3fc00000
    jz 1f
    mov al, 4
1:
    pop edi
    pop ecx
    ret
