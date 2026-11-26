/* nfl2k5_show_block_guard (task): as --32 -o task.o task.S && ld -m elf_i386 -Ttext=0xDA5D0 --oformat binary -e _start -o task.bin task.o
 * The bytes are padded with 0x90 to the retail extent (mod_editor/core/nfl2k5_show_block_guard.py SITES). */
.intel_syntax noprefix
.text
.globl _start
_start:                                 /* 0xDA5D0: the show task's update (1 = keep running, 0 = done) */
    cmp dword ptr [0xb72ed0], 0         /* (added) no show block held: no show was loaded, so the task is done, */
    jne 0f
    mov dword ptr [0xb72c30], 1         /* and so is the halftime presentation (the flag the halftime show sets at */
    xor eax, eax                        /* its end, 0xCED30; state 9 waits on it at 0x158D33; cleared at the next */
    ret                                 /* game's setup, 0xCE820) */
0:  mov eax, dword ptr [0xb73af0]
    push esi
    xor esi, esi
    cmp eax, 2
    mov dword ptr [0xb72ee4], esi
    je 7f
    cmp dword ptr [0xb73b04], 2
    jne 6f
    sub eax, esi
    je 5f
    dec eax
    jne 4f
    xor ecx, ecx
    call 0x70950
    test eax, eax
    je 4f
    push 0xe68d88
    mov edx, 0x534b524d
    xor ecx, ecx
    push 2                              /* (re-encoded through EAX, which 0x449E0 does not take: was mov [x], 2 */
    pop eax                             /*  and mov [y], 1) */
    mov dword ptr [0xb73af0], eax
    dec eax
    mov dword ptr [0xb72e84], eax
    call 0x449e0
    cmp eax, esi
    mov dword ptr [0xb73ad0], eax
    je 1f
    mov ecx, eax
    call 0x151530
    mov ecx, eax
    call 0x2ec20
    push ecx
    mov ecx, dword ptr [0xb73ad0]
    fstp dword ptr [esp]
    call 0x151530
    mov ecx, eax
    call 0x2f010
1:  push 0xe68db4
    mov edx, 0x534b524d
    xor ecx, ecx
    call 0x449e0
    cmp eax, esi
    mov dword ptr [0xb73b08], eax
    je 2f
    mov ecx, eax
    call 0x151530
    or dword ptr [eax+8], 1
    mov ecx, dword ptr [0xb73b08]
    call 0x151530
    mov ecx, eax
    call 0x2ec20
    push ecx
    mov ecx, dword ptr [0xb73b08]
    fstp dword ptr [esp]
    call 0x151530
    mov ecx, eax
    call 0x2f010
2:  call 0x25bea0
    push 0xb73afc
    push 0xb73af8
    mov eax, 0xb73b00
    call 0xd9be0
    mov ecx, 4
    call 0x657b0
4:  mov eax, 1
    pop esi
    ret
5:  xor ecx, ecx                        /* EAX is 0 here (state 0) */
    inc eax                             /* (re-encoded: was mov [x], 1) */
    mov dword ptr [0xb73af0], eax
    call 0x70920
    mov dword ptr [0xb73ad0], esi
    mov dword ptr [0xb73b08], esi
    jmp 4b                              /* (shared exit; retail repeats "mov eax, 1 / pop esi / ret") */
6:  mov dword ptr [0xb73ad0], esi
    jmp 4b                              /* (shared exit) */
7:  call 0x5a930
    push ecx
    mov ecx, dword ptr [0xb73ad0]
    fstp dword ptr [esp]
    call 0x151530
    mov ecx, eax
    call 0x2f030
    test eax, eax
    jne 4b
    pop esi
    ret
