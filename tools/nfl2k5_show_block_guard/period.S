/* nfl2k5_show_block_guard (period start): as --32 -o period.o period.S && ld -m elf_i386 -Ttext=0x9F940 --oformat binary -e _start -o period.bin period.o
 * The bytes fill the retail extent exactly (mod_editor/core/nfl2k5_show_block_guard.py SITES). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0x9F940: start period ECX (0xB8B30 and the other period starts) */
    push esi
    mov esi, ecx
    call 0x8d340
    call 0x834f0
    cmp dword ptr [0xb72ed0], 0         /* a show still holds the block: the postgame show a continued overtime */
    je 1f                               /* period end loaded; play must not run with the block taken */
    call 0xda5a0                        /* the guarded release: unload, give the block back, clear 0xB72ED0 */
1:  mov ecx, esi
    call 0xb8910
    mov ecx, esi
    call 0x1ceed0
    mov ecx, esi
    call 0x89440
    mov ecx, esi
    call 0x1d3210
    dec esi                             /* retail: cmp esi, 1 (esi is restored next) */
    pop esi
    je 2f
    call 0x100780
2:  xor ecx, ecx
    mov ch, 1                           /* retail: mov ecx, 0x100 */
    call 0x1d1f80
    xor ecx, ecx
    jmp 0xcecd0
