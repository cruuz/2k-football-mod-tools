/* CPU trades at every position (beta 81, owner nfl2k5_cpu_trades): the one entry.

   0x2BC96C is the native trade pass 0x2BC960's `call 0x2BC900` (the pending scan; retail and every b81 build:
   e88fffffff), right after the pruner 0x2BB9A0 and before the three random proposers. 0x2BC960 runs from the weekly
   advance in stages 1, 2 and 7, and in stage 8 while the trade window 0x247D10 is open (table 0x248088). The pending
   scan is stdcall-shaped: one stack argument (the menu, pushed by 0x2BC96B `push edi`), `ret 4`; it preserves EBX, ESI,
   EDI and EBP, and 0x2BC960 reads ESI right after it (0x2BC971 `test esi, esi`). Only the call displacement changes.
   trade_entry passes the menu to the cdecl trade_call, which posts, calls 0x2BC900 with it, and clears up. */
.intel_syntax noprefix
.code32
.section .text
.global trade_entry
trade_entry:
    cld
    push dword ptr [esp+4]
    call trade_call             /* void __attribute__((cdecl)) trade_call(u32 menu) */
    add esp, 4
    ret 4
.section .note.GNU-stack,"",@progbits
