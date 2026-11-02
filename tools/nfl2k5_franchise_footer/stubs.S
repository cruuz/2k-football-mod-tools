/* Franchise extension footer host (b780 J2): the five retail sites enter here. EXPERIMENTAL.
   Game routines and the displaced call targets are reached through absolute addresses in eax (no relocation leaves the
   blob). xt_config is the Studio-filled table at the end of the blob (nfl2k5_franchise_footer.CONFIG_FIELDS). */
    .intel_syntax noprefix
    .text
    .globl xt_size_hook, xt_save_hook, xt_load_hook, xt_admission, xt_franchise_hook, xt_config

/* 0x16AA26 in FUN_0016AA10 (the franchise total size): "call <front office size>", 5 bytes. The caller adds eax to
   esi (its running total) and returns. eax = the displaced target's size (front office, + the MyCareer block) + the
   footer this save carries. Only eax, ecx, edx change. */
xt_size_hook:
    mov eax, DWORD PTR [xt_config + 24]
    call eax
    push eax
    call xt_size_extra
    pop ecx
    add eax, ecx
    ret

/* 0x16E50D in FUN_0016E3F0 (the save): "call <front office writer>" with ecx = buffer + offset, 5 bytes. esi is the
   save buffer and ebx its total size (FUN_0016AA10's answer, footers included). The displaced writer runs first (the
   front office, then MyCareer's block), then the body and the Player Progress footer go at the end of the buffer. */
xt_save_hook:
    push ecx
    mov eax, DWORD PTR [xt_config + 28]
    call eax
    add esp, 4
    pushfd
    pushad
    mov ecx, DWORD PTR [esp + 4]        /* saved esi: the buffer */
    mov edx, DWORD PTR [esp + 16]       /* saved ebx: the total size */
    call xt_save_footer
    popad
    popfd
    ret

/* 0x16E815 in FUN_0016E540 (the load): "call <front office size>" after the front office deserializer, 5 bytes. esi is
   the file buffer and ebp the save slot's metadata offset ([ebp + 0xBDC1CC] = the file size). The displaced target runs
   first (MyCareer decodes its block there); its eax is returned unchanged. */
xt_load_hook:
    mov eax, DWORD PTR [xt_config + 32]
    call eax
    pushfd
    pushad
    mov ecx, DWORD PTR [esp + 4]        /* saved esi: the file buffer */
    mov eax, DWORD PTR [esp + 8]        /* saved ebp: the metadata offset */
    mov edx, DWORD PTR [eax + 0xBDC1CC] /* the file size */
    call xt_load_footer
    popad
    popfd
    ret

/* 0x16ABB5 in FUN_0016AB70 (save-list admission), the franchise branch "call 0x16AA10; jmp 0x16ABCF", 7 bytes, entered
   with esi = the slot's metadata offset and esi's old value on the stack. eax = 0 admitted, 1 damaged. */
xt_admission:
    mov ecx, DWORD PTR [esi + 0xBDC1CC]
    call xt_admit
    xor eax, 1
    pop esi
    ret

/* 0x13EF21 in FUN_0013EE10 (a new franchise, also called by MyCareer): "call 0x13ED70", 5 bytes, ecx = 1. The
   displaced target (0x13ED70) runs as a tail call with every register as the site left it. */
xt_franchise_hook:
    pushfd
    pushad
    call xt_new_franchise
    popad
    popfd
    mov eax, DWORD PTR [xt_config + 48]
    jmp eax

    .balign 16
xt_config:
    .long 0x43485458                    /* +0  "XTHC" */
    .long 1                             /* +4  version */
    .long 0, 0, 0, 0                    /* +8  state, static body, Player Progress footer, its baseline routine */
    .long 0, 0, 0                       /* +24 chain size, chain save, chain load */
    .long 0, 0, 0                       /* +36 seeds, flags, stamp */
    .long 0                             /* +48 chain new franchise */
    .long 0, 0                          /* +52 the displaced admission bytes (7 + 1) */
    .long 0                             /* +60 reserved */
