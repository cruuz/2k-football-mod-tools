/* Only the existing pocket escape lottery threshold changes: .25 -> .3125
 * times effective Scramble. Native coverage/pressure/timer gates are retained.
 */
.intel_syntax noprefix
.code32
.text
.global threshold
.extern factor
threshold:
    pushfd
    push eax
    cmp dword ptr [0xe602b8], 14
    jne retail
    cmp dword ptr [0xe602b4], 4
    jne retail
    mov eax, [edi+0xc]
    test eax, eax
    jz retail
    cmp dword ptr [eax], -1          /* native CPU steering sentinel */
    jne retail
    mov eax, [edi+0x3c]
    test eax, eax
    jz retail
    cmp byte ptr [eax+0x35], 0       /* roster QB */
    jne retail
    .ifndef BETA80
    mov eax, dword ptr [0xbe47c0]     /* smoothed pocket pressure, updated by 0x198860 */
    cmp eax, 0x7f800000
    jae retail                        /* unknown or negative input */
    cmp eax, 0x3f333333               /* 0.70, same pressure boundary as the passer owner */
    jae pressured
    mov eax, dword ptr [0xe6029c]     /* live clock, seconds since the snap */
    test eax, eax
    jz retail
    cmp dword ptr [eax+0x10], 0x40200000  /* clean pocket, at least 2.5 seconds */
    jae retail
    fstp st(0)                        /* stay on the reads in an early clean pocket */
    fldz
    jmp done
pressured:
    .endif
    fmul dword ptr [factor]
    jmp done
retail:
    fmul dword ptr [0x4e696c]
done:
    pop eax
    popfd
    ret
