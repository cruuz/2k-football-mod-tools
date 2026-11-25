/* Season award vote and defensive credit (job b81-awards): the two retail patch sites enter here. EXPERIMENTAL /
   UNWITNESSED. Each stub replays the retail bytes it replaced and returns to the next retail instruction with
   push/ret, so no register the retail code reads is changed. */
    .intel_syntax noprefix
    .text
    .globl awards_vote_entry, awards_credit_entry

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

/* 0x134DF1, FUN_00134DD0 (one club's career merge): "mov ebx, eax; mov al, [edi+0x11c]" (8 bytes). eax = the club's
   first live record, edi = the live team, esi = the club record. */
awards_credit_entry:
    pushad
    push eax
    mov edx, esi
    mov ecx, edi
    call awards_credit
    popad
    mov ebx, eax
    mov al, byte ptr [edi + 0x11c]
    push 0x00134DF9
    ret
