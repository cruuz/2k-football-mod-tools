/* nfl2k5_show_block_guard (loader): as --32 -o loader.o loader.S && ld -m elf_i386 -Ttext=0xDA4D0 --oformat binary -e _start -o loader.bin loader.o
 * The bytes are padded with 0x90 to the retail extent (mod_editor/core/nfl2k5_show_block_guard.py SITES). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0xDA4D0: the halftime/postgame show loader (ecx: 0 halftime, 1 postgame) */
    push edi
    xor edi, edi
    cmp ecx, edi
    mov dword ptr [0xb73af0], edi
    mov dword ptr [0xb72ee8], edi
    mov dword ptr [0xb73aec], ecx
    mov dword ptr [0xb73af4], edi
    mov dword ptr [0xb73bb0], edi
    mov dword ptr [0xb72e80], 1         /* (moved up from the end) a show is under way, loaded or skipped: the
                                           presentation's "wait until a show is active" task (script command 35,
                                           0xDAD20) goes on either way; the release clears it */
    jne 1f
    call 0x116340
    call 0x834f0
    call 0x83a20
1:  push esi
    call 0xf6060
    mov esi, eax
    call 0xf6070                        /* the 0x148000-byte show block, or 0 when it is missing or taken */
    test eax, eax
    je 2f
    mov dword ptr [0xb72ed0], eax       /* (moved up) the block this show holds (only a show that got it records it) */
    lea ecx, [eax+3]
    and ecx, -4
    lea edx, [ecx+0x9c]
    sub eax, edx
    add eax, esi
    push eax
    mov dword ptr [0xb72ed4], ecx
    call 0x48640
    cmp dword ptr [0xb73aec], edi
    mov dword ptr [0xb73b04], edi
    pop esi
    mov edx, 0xe68d34
    jne 3f
    mov edx, 0xe68d50
3:  mov eax, dword ptr [0xb72ed4]
    push edi
    push 0xd9c40
    push eax
    push 0xb72e88
    mov ecx, 0xe68d20
    call 0x43f50
    mov ecx, dword ptr [0xb72ed4]
    mov edx, dword ptr [0xa8be74]
    push edi
    push 0xd9c40
    push ecx
    push 0xb72eac
    mov ecx, 0xe68d6c
    call 0x43f50
    pop edi
    ret
2:  pop esi                             /* no block: nothing is loaded; 0xB72ED0 keeps saying whether a show holds it */
    pop edi
    ret
