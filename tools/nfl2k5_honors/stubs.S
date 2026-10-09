/* Player Card honors page (job F5, beta 77): the seven retail patch sites enter here. EXPERIMENTAL / UNWITNESSED.
   Game routines are reached through absolute addresses in eax; honors_state is the owner's RW block. */
    .intel_syntax noprefix
    .text
    .globl honors_page_input, honors_page_enter, honors_page_ratings, honors_page_bio
    .globl honors_season_hook, honors_sb_hook, honors_fold_rule

/* 0x320D7B, in place of "test eax, 0x220" in the card's pad loop: eax = buttons pressed this frame. Black,
   White, L trigger (the game's L1) or R trigger (R1) flips the page with the menu cursor sound; the retail
   B/Back test is then repeated so the caller's jump sees its own flags. */
honors_page_input:
    test eax, 0xF000
    jz 1f
    push eax
    push ecx
    push edx
    xor dword ptr [honors_state], 1
    push 0
    push 0
    push 0
    push 0
    push 0
    push 0
    mov ecx, 0x00E8DA28
    mov eax, 0x00038650
    call eax
    xor edx, edx
    mov ecx, eax
    mov eax, 0x00089DA0
    call eax
    pop edx
    pop ecx
    pop eax
1:  test eax, 0x220
    ret

/* 0x320210, in place of "mov ecx, [0xC90248]" (6 bytes, call + nop) in the card's enter action: every card
   opens on the retail page. */
honors_page_enter:
    mov dword ptr [honors_state], 0
    mov ecx, dword ptr [0x00C90248]
    ret

/* 0x320B75 and 0x320B7A, the card's draw calls to the rating panel (0x320500) and the bio lines (0x320760). */
honors_page_ratings:
    cmp dword ptr [honors_state], 0
    jne honors_counts
    mov eax, 0x00320500
    jmp eax
honors_page_bio:
    cmp dword ptr [honors_state], 0
    jne honors_years
    mov eax, 0x00320760
    jmp eax

/* 0x116E5F, FUN_00116920's tail jump to the rushing title (reached only for week index 16, after the MVP,
   OPOY, DPOY, rookie and best-at-position awards): run the tail, then record the season's winners. */
honors_season_hook:
    mov eax, 0x001160C0
    call eax
    pushad
    call commit_season
    popad
    ret

/* 0x1356B4, FUN_00135310's last call (ecx, edx are its arguments) after the game's scores are in the grid. */
honors_sb_hook:
    mov eax, 0x001C1C80
    call eax
    pushad
    call commit_sb
    popad
    ret

/* 0x14F168, in place of "mov eax, [esi*4 + 0xAA26C0]" (7 bytes, call + 2 nops) in the history fold: honor
   fields always fold by sum, every other field keeps the retail lookup (including its reads past field 86). */
honors_fold_rule:
    lea eax, [esi - 96]
    cmp eax, 10
    jb 1f
    mov eax, dword ptr [esi*4 + 0x00AA26C0]
    ret
1:  mov eax, 1
    ret
