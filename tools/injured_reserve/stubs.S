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
