/* Franchise History screen (job b780 j4-history, beta 80): the retail patch site that enters here. EXPERIMENTAL /
   UNWITNESSED. Game routines are reached through absolute addresses in eax. */
    .intel_syntax noprefix
    .text
    .globl hist_schedule_hook

/* 0x24D2E5, in FUN_0024d1b0's port loop (the Schedule input): "test ebx, 0x220" (6 bytes) becomes call + nop.
   edi = the menu manager, esi = the port, ebx = the port's buttons. hist_schedule_x keeps the legend's X entry and opens
   the box score on a fresh X press over a played game; then FUN_0024d1b0 ends the way its own screen push does (0x24D348:
   refresh the list if it is due, return 0). Otherwise the retail B/Back test is repeated for the caller's jump. */
hist_schedule_hook:
    pushad
    mov ecx, edi
    mov edx, esi
    call hist_schedule_x
    test eax, eax
    popad
    jnz 1f
    test ebx, 0x220
    ret
1:  add esp, 4
    mov eax, 0x0024D348
    jmp eax

    .section .note.GNU-stack,"",@progbits
