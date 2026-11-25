/* CPU trades at every position (beta 81, owner nfl2k5_cpu_trades): the two entries.

   trade_entry, site 0x2BC96C: the native trade pass 0x2BC960's `call 0x2BC900` (the pending scan; retail and every
   b81 build: e88fffffff), right after the pruner 0x2BB9A0 and before the three random proposers. 0x2BC960 runs from
   the weekly advance in stages 1, 2 and 7, and in stage 8 while the trade window 0x247D10 is open (table 0x248088).
   The pending scan is stdcall-shaped: one stack argument (the menu, pushed by 0x2BC96B `push edi`), `ret 4`; it
   preserves EBX, ESI, EDI and EBP, and 0x2BC960 reads ESI right after it (0x2BC971 `test esi, esi`). Only the call
   displacement changes. trade_entry passes the menu to the cdecl trade_call, which posts, calls 0x2BC900 and clears up.

   story_entry, site 0x2BB296: the trade story writer 0x2BB200's `cmp eax, 0x3e8` (3de8030000, then `jle 0x2BB354`,
   which skips the inbox story when the assets' mean value is 1000 or less), replaced by a 5-byte call. EBP holds the
   record there. For a record of ours (story_is_ours) the flags read "greater", so the story is posted (S7); for any
   other record the native compare is made. EAX, ECX and EDX are kept; EAX is the value the native code compares. */
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
.global story_entry
story_entry:
    push eax
    push ecx
    push edx
    push ebp
    call story_is_ours          /* u32 __attribute__((cdecl)) story_is_ours(u32 record) */
    add esp, 4
    test eax, eax
    pop edx
    pop ecx
    pop eax
    jnz 1f
    cmp eax, 0x3e8
    ret
1:  cmp esp, 0x3e8              /* a stack address is far above 1000: "greater", so `jle` falls through */
    ret
.section .note.GNU-stack,"",@progbits
