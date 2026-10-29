/* Super Bowl champion pop-up, champions history and modern award voting (job hn1, beta 79): the two retail patch sites
   enter here. EXPERIMENTAL / UNWITNESSED. Game routines are reached through absolute addresses in eax. */
    .intel_syntax noprefix
    .text
    .globl champions_advance, champions_awards

/* 0x2485FA, FUN_002480B0's stage-9 action: "call 0x2BDB00" (the retail retirement pass that starts the rollover), 5 bytes.
   ebx is the league menu object of the caller. Show the champion notice (ecx = menu), then run the retail pass; it
   returns to the instruction after the site. */
champions_advance:
    pushad
    mov ecx, ebx
    call champions_advance_notice
    popad
    mov eax, 0x002BDB00
    jmp eax

/* 0x116E55, FUN_00116920's last award call "call 0x115FB0", 5 bytes: run it, then replace the five player awards. */
champions_awards:
    mov eax, 0x00115FB0
    call eax
    pushad
    call champions_modern_awards
    popad
    ret

