/* Season award vote (job b81-awards): the retail patch site enters here. EXPERIMENTAL /
   UNWITNESSED. The stub replays the retail bytes it replaced and returns to the next retail instruction with
   push/ret, so no register the retail code reads is changed. */
    .intel_syntax noprefix
    .text
    .globl awards_vote_entry

/* 0x116E5A, FUN_00116920's award block after the champions owner's call at 0x116E55: "pop esi; pop ebp; add esp, 0x1c"
   (5 bytes) before the rushing-title tail at 0x116E5F (the honors owner's jump when installed). */
awards_vote_entry:
    pop esi
    pop ebp
    add esp, 0x1c
    pushad
    call awards_vote
    popad
    push 0x00116E5F
    ret
