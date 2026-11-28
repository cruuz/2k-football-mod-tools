/* Quarterback trades (beta 81 stage 4b, owner nfl2k5_qb_trades): the one entry.

   0x247E1E is the stage-8 case's `call 0x2BC960` inside the weekly advance 0x247D40 (retail and every b81 build:
   e83d4b0700), reached only when the native trade window 0x247D10 is open (0x247E15 skips it otherwise), before the
   week's games. The site sets ECX = 3 (proposers) and EDX = the menu (EBP) for 0x2BC960, which is fastcall-shaped:
   it reads ECX and EDX, preserves EBX, ESI, EDI and EBP, and ends in a plain ret; the code after the site reloads EAX
   and sets the flags itself (0x247E23 `mov eax,[0xE60124]; test eax,eax`). Only the call displacement changes.
   trade_entry passes ECX and EDX to the cdecl trade_call, which posts, calls 0x2BC960 with them, and clears up. */
.intel_syntax noprefix
.code32
.section .text
.global trade_entry
trade_entry:
    cld
    push edx
    push ecx
    call trade_call             /* void __attribute__((cdecl)) trade_call(u32 proposers, u32 menu) */
    add esp, 8
    ret
.section .note.GNU-stack,"",@progbits
