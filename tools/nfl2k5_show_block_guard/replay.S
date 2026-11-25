/* nfl2k5_show_block_guard (replay): as --32 -o replay.o replay.S && ld -m elf_i386 -Ttext=0x83F10 --oformat binary -e _start -o replay.bin replay.o
 * The bytes are padded with 0x90 to the retail extent (mod_editor/core/nfl2k5_show_block_guard.py SITES). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0x83F10: the replay system takes the show block for its two zones */
    test byte ptr [0xb608f0], 1
    jne 2f
    push esi
    call 0xf6060
    mov esi, eax
    xor cl, cl
    sar esi, 1
    call 0x834a0
    and dword ptr [0xb607f0], -2
    call 0xf6070
    test eax, eax
    je 1f                               /* no block (a show holds it): no replay zones, and no release later */
    mov dword ptr [0xb60a90], 1         /* (moved down) the replay holds the block */
    push esi
    mov edx, eax
    xor cl, cl
    mov dword ptr [0xb607b8], eax
    call 0x83330
    mov eax, dword ptr [0xb607b8]
    lea edx, [eax+esi]
    push esi
    mov cl, 1
    mov dword ptr [0xb607bc], edx
    call 0x83330
1:  pop esi
2:  ret
