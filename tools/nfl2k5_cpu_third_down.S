/* EXPERIMENTAL / UNWITNESSED. b778 ai8, GNU as --32. Third-down run preference.
 *
 * Hooked at 0x209803 (inside the native offensive play selector 0x2096A0, after the shared scorer
 * 0x208820, before the retail score multiplier). ST0 carries the candidate score and ESI the
 * candidate PLAY. On third down with seven or more yards to go, a run candidate keeps 5 percent of
 * its score, so the native caller chooses a pass unless every candidate is a run. A third and 20+
 * in the fourth quarter, inside five minutes, with the offense leading is left alone: running there
 * is the measured NFL behavior. Every register, flag and the x87 register carrying the score survive.
 *
 * The displaced bytes (fmul [ebp-0x2c]; mov [ebp+edi*4-0x120],esi) are re-executed, then control
 * returns to the ordinary 0x20980D publication tail (which may be the Modern 2 play hook or the
 * retail store). The code needs no writable data and no runtime context.
 */
.intel_syntax noprefix
.code32
.text
.global third_down_play
third_down_play:
    sub esp, 128
    pushfd
    pushad
    mov ebx, dword ptr [0xe602ec]
    test ebx, ebx
    jz done
    cmp dword ptr [ebx+4], 3
    jne done
    fld dword ptr [ebx+0x28]
    fsub dword ptr [ebx+0x18]
    fabs
    sub esp, 4
    fstp dword ptr [esp]
    mov eax, dword ptr [esp]
    add esp, 4
    cmp eax, 0x4420051f              /* 7 * 91.44 cm */
    jb done
    cmp eax, 0x44e4999a              /* 20 * 91.44 cm */
    jb check_play
    cmp dword ptr [0xe602c4], 4      /* fourth quarter */
    jne check_play
    mov ecx, dword ptr [0xe6028c]
    test ecx, ecx
    jz check_play
    mov ecx, dword ptr [ecx+0x10]
    cmp ecx, 0x43960000              /* 300 s */
    ja check_play
    mov ecx, dword ptr [0xe60280]    /* offense team */
    test ecx, ecx
    jz check_play
    mov edx, dword ptr [ecx+8]       /* offense score record */
    test edx, edx
    jz check_play
    mov eax, dword ptr [edx]
    mov ecx, dword ptr [ecx]         /* opponent team */
    test ecx, ecx
    jz check_play
    mov ecx, dword ptr [ecx+8]
    test ecx, ecx
    jz check_play
    sub eax, dword ptr [ecx]
    jle check_play
    jmp done                         /* 3rd and 20+ late with a lead: the run may stand */
check_play:
    mov eax, dword ptr [esi+4]
    test eax, 0x8000                 /* PLAY header run bit (the generator's run classes) */
    jz done
    sub esp, 4
    mov dword ptr [esp], 0x3d4ccccd  /* 0.05 */
    fmul dword ptr [esp]
    add esp, 4
done:
    popad
    popfd
    add esp, 128
    fmul dword ptr [ebp-0x2c]
    mov dword ptr [ebp+edi*4-0x120], esi
    jmp 0x20980d
third_end:
.balign 4, 0xcc
