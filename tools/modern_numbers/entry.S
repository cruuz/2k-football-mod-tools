/* Modern jersey numbers (beta 81, owner nfl2k5_modern_numbers): the one entry.

   0x2BD260 is the entry of FUN_002BD260, the jersey routine every join calls (ECX = player, EDX = club, [esp+4] = keep;
   it pops 4). Its first 6 bytes (mov eax,[esp+4]; test eax,eax) become `jmp number_entry` + nop. number_entry builds
   the routine's own frame (push ebx, ebp, esi, edi; ebx = club, edi = player, exactly as 0x2BD266..0x2BD26D do) and asks
   the cdecl number_pick(player, club, frame) for a number, frame = the routine's entry ESP (the caller's return address,
   then keep, then the caller's own frame).
   - 0..99: write bits 3..9 of +0x20 (the bits the retail routine writes) and jump to 0x2BD33F, the retail tail: the
     play-by-play cue fix (a cue in 9000..9099 follows the new number), then pop edi, esi, ebp, ebx and ret 4.
   - negative (no legal number free on the club, or a record the rule does not cover): undo the frame and re-enter the
     retail body at 0x2BD266 with keep = 1 (eax = 1, the flags of `test eax,eax`), the retail walk and its own fallback.
   number_pick reads only; it writes nothing. */
.intel_syntax noprefix
.code32
.section .text
.global number_entry
number_entry:
    push ebx
    push ebp
    push esi
    push edi
    mov ebx, edx
    mov edi, ecx
    lea eax, [esp + 16]
    cld
    push eax
    push ebx
    push edi
    call number_pick            /* int __attribute__((cdecl)) number_pick(u8 *player, u8 *club, const u32 *frame) */
    add esp, 12
    test eax, eax
    js 1f
    mov edx, [edi + 0x20]
    and edx, 0xFFFFFC07
    shl eax, 3
    or edx, eax
    mov [edi + 0x20], edx
    jmp 0x2BD33F
1:
    mov ecx, edi
    mov edx, ebx
    pop edi
    pop esi
    pop ebp
    pop ebx
    mov eax, 1
    test eax, eax
    jmp 0x2BD266
.section .note.GNU-stack,"",@progbits
