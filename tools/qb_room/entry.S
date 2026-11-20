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
.section .note.GNU-stack,"",@progbits
