/* nfl2k5_show_block_guard (switch): as --32 -o switch.o switch.S && ld -m elf_i386 -Ttext=0x1F7DF0 --oformat binary -e _start -o switch.bin switch.o
 * The routine and its case table (kept at 0x1F7E80) cover the retail extent exactly (0xB8 bytes). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0x1F7DF0: presentation command 14 (CL = its case) */
    movzx eax, cl
    cmp eax, 9
    ja 9f
    jmp dword ptr [eax*4 + 0x1f7e80]
c0: jmp 0x9f8c0
c1: jmp 0x125cd0
c2: mov dword ptr [0xe602c8], 0x16
    and dword ptr [0xe602cc], 0         /* (re-encoded: was mov ..., 0) */
9:  ret
c3: mov dword ptr [0xe602c8], 0x18
    and dword ptr [0xe602cc], 0         /* (re-encoded) */
    ret
c4: push 1                              /* (re-encoded: was mov ecx, 1) */
    pop ecx
    jmp 0xa0320
c5: jmp 0xa1e90
c6: call 0x11bea0
    xor ecx, ecx
    call 0xa5580
    call 0x5ab60
    xor ecx, ecx
    call 0x5f460
    mov ecx, 0x83
    jmp 0x67df0
c7: jmp 0xa0090
c8: call 0x136d40
    mov ecx, eax
    jmp 0x117780
c9: cmp dword ptr [0xe602b8], 10        /* (added) the postgame show only when the game is over (state 10). The */
    jne 9b                              /* 2025 overtime rules play on after an overtime period end with different */
    push 1                              /* scores; retail's period-end presentation would load the postgame show */
    pop ecx                             /* there and keep it loaded into the extra period. */
    jmp 0xda4d0
    .org 0x90, 0x90                     /* the case table stays at 0x1F7E80 */
    .long c0, c1, c2, c3, c4, c5, c6, c7, c8, c9
