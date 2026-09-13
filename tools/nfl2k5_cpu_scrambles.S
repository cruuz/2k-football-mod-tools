/* Only the existing pocket escape lottery threshold changes: .25 -> .50
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
    fmul dword ptr [factor]
    jmp done
retail:
    fmul dword ptr [0x4e696c]
done:
    pop eax
    popfd
    ret
