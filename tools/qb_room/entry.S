/* Quarterback room (beta 81 piece 3): the two weekly-advance entries.

   Both sites are whole 5-byte calls inside the weekly advance 0x247D40 (retail disassembly, see
   tests/mod_editor/test_b81_qb_room_native.py): 0x247DCA `call 0x2BE020` (injured-reserve pass, after the first
   auto depth and before the week's games) and 0x24807A `call 0x27EB80` (after the second auto depth, the last call
   before the function returns). Only the call displacement changes. Each stub keeps every general register, EFLAGS
   and ESP exactly as the call left them, calls a cdecl C pass with no arguments, and jumps on to the original target
   with the original return address still on the stack, so the target runs as if it had been called directly.
   Neither target reads a register or a stack argument from its caller (0x2BE020 starts `push ecx` as a local slot
   that it overwrites before reading; 0x27EB80 starts `sub esp,8`), and neither caller passes one. */
.intel_syntax noprefix
.code32
.section .text
.global opening_entry, room_entry
opening_entry:
    pushfd
    pushad
    cld
    call opening_pass           /* void __attribute__((cdecl)) opening_pass(void) */
    popad
    popfd
    jmp 0x2be020
room_entry:
    pushfd
    pushad
    cld
    call room_pass              /* void __attribute__((cdecl)) room_pass(void) */
    popad
    popfd
    jmp 0x27eb80
/* Stage 4a (moves.c). 0x248010 `call 0x323870` (the game's weekly signings; on standard economy_week, fastcall
   ECX = menu with two float stack arguments, ret 8). sign_entry keeps the menu, puts sign_after in place of the return
   address and jumps on with every register, the flags and both stack arguments untouched; the routine's ret 8 lands
   in sign_after with ESP exactly where the unhooked call would leave it, and EBX/ESI/EDI/EBP as the routine left them
   (EBP is still the weekly advance's menu). sign_after keeps them, calls the cdecl pass with the menu, and jumps to
   0x248015 as the routine's own return would. Placed after room.c and moves.c (section .text.sign) so that piece 3's
   bytes do not move. */
.section .text.sign,"ax",@progbits
.global sign_entry, sign_after
sign_entry:
    mov dword ptr [qb_menu], ecx
    mov dword ptr [esp], OFFSET sign_after
    jmp 0x323870
sign_after:
    pushfd
    pushad
    cld
    push 0                      /* pregame = 0: the post-game call */
    push dword ptr [qb_menu]
    call emergency_pass         /* void __attribute__((cdecl)) emergency_pass(u32 menu, u32 pregame) */
    add esp, 8
    popad
    popfd
    jmp 0x248015
/* The floor (DESIGN addendum F3, F8): the pre-game call 0x247DCA points here. opening_pass runs as in opening_entry; with
   stage bit 64 clear the stub then jumps to 0x2BE020 exactly as opening_entry does. With it set it CALLS the IR pass
   0x2BE020 with the registers and flags the call site left, runs emergency_pass(menu, 1) with the weekly advance's menu (EBP,
   loaded at 0x247D50 and not written again before 0x247DCA), restores everything the IR pass left and returns to
   0x247DCF. (The over-cap entry sign_ungated is retired with the over-cap rung, floor review F1.) */
.section .text.floor,"ax",@progbits
.global pregame_entry
pregame_entry:
    pushfd
    pushad
    cld
    call opening_pass           /* void __attribute__((cdecl)) opening_pass(void) */
    test byte ptr [qb_settings + 12], 64
    jnz 1f
    popad
    popfd
    jmp 0x2be020
1:
    popad
    popfd
    call 0x2be020
    pushfd
    pushad
    cld
    push 1                      /* pregame = 1 */
    push ebp
    call emergency_pass         /* void __attribute__((cdecl)) emergency_pass(u32 menu, u32 pregame) */
    add esp, 8
    popad
    popfd
    ret
.section .note.GNU-stack,"",@progbits
