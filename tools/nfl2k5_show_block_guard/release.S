/* nfl2k5_show_block_guard (release): as --32 -o release.o release.S && ld -m elf_i386 -Ttext=0xDA5A0 --oformat binary -e _start -o release.bin release.o
 * The bytes are padded with 0x90 to the retail extent (mod_editor/core/nfl2k5_show_block_guard.py SITES). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0xDA5A0: the show release */
    xor eax, eax
    mov dword ptr [0xb72e80], eax       /* (moved up) the show is over */
    xchg eax, dword ptr [0xb72ed0]      /* the block this show held; cleared so a second release gives nothing back */
    test eax, eax
    je 1f
    mov ecx, 0xe68d6c
    call 0x432f0
    mov ecx, 0xe68d20
    call 0x432f0
    call 0xf60a0
1:  call 0x84260
    ret
