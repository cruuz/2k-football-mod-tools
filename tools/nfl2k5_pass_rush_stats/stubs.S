/* Pass rush stats (job b779 st1): the retail sites enter here. EXPERIMENTAL.
   Every hook saves the flags, the integer registers and the x87 state (fnsave also gives the C code a clean
   FPU), runs the C handler, restores everything and continues with the displaced retail work. Absolute
   continuations use push imm32 / ret so no register is needed. prs_state is the owner's RW block. */
    .intel_syntax noprefix
    .text
    .globl prs_shed, prs_throw, prs_sack1, prs_sack2, prs_commit, prs_reset1, prs_reset2, prs_card_def
    .globl prs_card_wr, prs_card_rb, prs_list_rb, prs_list_wr
    .globl prs_hurry_mm2, prs_hit_mm2, prs_rush_share, prs_hit_share, prs_ol_per_game, prs_ol_hit_share
    .globl prs_ol_sack_share, prs_list_def, prs_list_ol

/* 0x23477A (jmp, 7 bytes "push 0; push 0; push 3; push esi") in the caller of the engaged-block tick, on the
   shed result (0x233040 returned 2): ebx and esi are the two engaged players. */
prs_shed:
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov ecx, ebx
    mov edx, esi
    call prs_on_shed
    frstor [esp]
    add esp, 108
    popad
    popfd
    push 0
    push 0
    push 3
    push esi
    push 0x00234781
    ret

/* 0x2DB2CA (call, in place of "call 0x2DAF10"): esi = the passer, the release runs next. */
prs_throw:
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov ecx, esi
    call prs_on_throw
    frstor [esp]
    add esp, 108
    popad
    popfd
    push 0x002DAF10
    ret

/* 0xCE32A (call, in place of "call 0xCC160"): ecx = the play result, eax = the log index. The sacker is the
   play's role-5 entry +0x24 (0xD2C20, the same getter the log writer uses). */
prs_sack1:
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov eax, 0x000D2C20
    call eax
    mov ecx, eax
    call prs_on_sack
    frstor [esp]
    add esp, 108
    popad
    popfd
    push 0x000CC160
    ret

/* 0xCE2A4 (call, in place of "call 0xCC1F0"): edi = the play's sack entry ([edi+0x20] passer, [edi+0x24]
   sacker live records). */
prs_sack2:
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov ecx, dword ptr [edi + 0x24]
    call prs_on_sack
    frstor [esp]
    add esp, 108
    popad
    popfd
    push 0x000CC1F0
    ret

/* 0x134E1F (jmp, 7 bytes "push 0; mov edx, 0x4C"): FUN_00134DD0 finished its per-player merge loop; edi = the
   in-game team, esi = the club, [esp+0x14] = the side argument. */
prs_commit:
    pushfd
    pushad
    sub esp, 108
    fnsave [esp]
    mov eax, dword ptr [esp + 108 + 36 + 0x14]
    push eax
    mov ecx, edi
    mov edx, esi
    call prs_on_commit
    frstor [esp]
    add esp, 108
    popad
    popfd
    push 0
    mov edx, 0x4C
    push 0x00134E26
    ret

/* 0xA78EF and 0x10B427 (calls, in place of "call 0xCCE00"): the play log is cleared for a new game. */
prs_reset1:
prs_reset2:
    pushad
    call prs_on_reset
    popad
    push 0x000CCE00
    ret

/* Entries 3, 4 and 5 of the Player Card's screen jump table (0x320C34 / 0x320C38 / 0x320C3C; retail 0x320BD2
   WR/TE, 0x320BE3 defense, 0x320BC1 HB/FB). C, G and T are routed to entry 4 too (0x320C50..0x320C52 = 4). Each
   stub points its sheet's own writable column-list field at this owner's list (after any card-prepare hook at
   the selector's entry has written its own), then runs the retail screen call. The defensive entry shows the
   offensive-line list for C, G and T. */
prs_card_wr:
    mov eax, dword ptr [prs_list_wr]
    mov dword ptr [0x0053592C], eax
    mov edx, 0x00536340
    jmp 2f
prs_card_rb:
    mov eax, dword ptr [prs_list_rb]
    mov dword ptr [0x0053582C], eax
    mov edx, 0x005360D8
    jmp 2f
prs_card_def:
    mov eax, dword ptr [0x00C90248]
    movzx eax, byte ptr [eax + 0x35]
    sub eax, 12
    cmp eax, 2
    mov eax, dword ptr [prs_list_def]
    ja 1f
    mov eax, dword ptr [prs_list_ol]
1:  mov dword ptr [0x00535A2C], eax
    mov edx, 0x005365A8
2:  mov ecx, dword ptr [esp + 4]
    mov eax, 0x0006E390
    call eax
    ret 4

    .balign 4
prs_hurry_mm2:     .float 33445.09       /* (182.88 cm = 2 yd)^2: a defender this close at the release hurried */
prs_hit_mm2:       .float 8361.27        /* (91.44 cm = 1 yd)^2: this close at the release hit the passer */
prs_rush_share:    .float 0.71           /* simulated: hurries + knockdowns per pressure (PFR: sacks 0.29) */
prs_hit_share:     .float 0.53           /* simulated: knockdowns per non-sack pressure (PFR 0.37 / 0.70) */
prs_ol_per_game:   .float 4.3            /* simulated: non-sack pressures charged to the line a game */
prs_ol_hit_share:  .float 0.45           /* simulated: share of those that are QB hits */
prs_ol_sack_share: .float 0.70           /* simulated: share of the team's sacks charged to a lineman */
prs_list_rb:       .long 0               /* the column lists (filled by the owner): HB/FB */
prs_list_wr:       .long 0               /* WR/TE */
prs_list_def:      .long 0               /* defense */
prs_list_ol:       .long 0               /* offensive line */
