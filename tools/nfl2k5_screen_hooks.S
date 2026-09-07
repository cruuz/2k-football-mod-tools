/* EXPERIMENTAL / UNWITNESSED. GNU as --32.
 * Two stateless policies. No new RW allocation or borrowed task fields.
 * Block boundary: EBX actor, EDI actor state, ESI block task.
 * QB boundary: EDI actor, ESI pass task, [ESP+12] native float timer.
 * All classification is integer-only; only displaced instructions touch x87.
 */
.intel_syntax noprefix
.code32
.text
.global block, qb, code_end
.extern block_tail, block_wait, qb_tail
block:
    pushfd
    pushad
    test dword ptr [edi+0x420], 0x20000
    jnz block_original                 /* terminal action keeps native exit */
    mov eax, [esi+0x60]
    and eax, 0x7fffffff
    cmp eax, 0x7f800000
    jae block_original                 /* infinity / NaN never coerced */
    test eax, eax
    jz expired
    cmp dword ptr [esi+0x60], 0
    jge block_original                 /* positive native holds are unchanged */
expired:
    mov eax, [0xe6029c]
    test eax, eax
    jz block_original
    cmp dword ptr [0xe602b8], 14
    jne block_original
    cmp dword ptr [eax+0x10], 0x3f4ccccd /* unsigned: [0, .8); invalid bypass */
    jae block_original
    mov edx, ebx
    call screen
    test eax, eax
    jz block_original
    test esi, esi
    jz block_original
    lea edx, [ebp+esi*8]
    call line
    test eax, eax
    jz block_original
    cmp cl, [edi+0x450]                /* hold, not release or later block */
    jne block_original
    popad
    popfd
    fld dword ptr [esi+0x60]
    fcomp dword ptr [0x4e4180]
    jmp block_wait                     /* retain task timer and x87 comparison */
block_original:
    popad
    popfd
    fld dword ptr [esi+0x60]
    fcomp dword ptr [0x4e4180]
    jmp block_tail
qb:
    pushfd
    pushad
    mov edx, edi
    cmp byte ptr [edx+0x2e], 0
    jne qb_original
    call screen
    test eax, eax
    jz qb_original
    cmp byte ptr [edi+0x450], 3         /* live pass node, not lookahead */
    jne qb_original
    test dword ptr [eax+4], 0x03f00000
    jnz qb_original                    /* explicit delay always survives */
    inc esi
qb_line:
    lea edx, [ebp+esi*8]
    call line
    test eax, eax
    jnz qb_policy
    inc esi
    cmp esi, 5
    jbe qb_line
qb_original:
    popad
    popfd
    mov ecx, [esp+12]
    mov [esi+0x60], ecx
    jmp qb_tail
qb_policy:
    popad
    popfd
    mov ecx, 0x3f19999a                /* float .6; do not overwrite stack local */
    mov [esi+0x60], ecx
    jmp qb_tail

/* EDX actor. Return EAX pass node or zero, EBP QB descriptor, EBX PLAY
 * buffer, EDI state, ESI slot. Only native slots0..5 are candidates.
 * Match actual first-read slot6..10 with Start -> type9/10 route.
 * Narrow QB grammar: Start -> take snap -> mode0 drop -> terminal pass.
 */
screen:
    movzx esi, byte ptr [edx+0x2e]
    cmp esi, 5
    ja no
    mov edi, [edx+0x20]
    mov ebp, [edi+0x41c]
    lea eax, [esi*8]
    sub ebp, eax
    mov ebx, 0xb75a40
    mov eax, ebp
    sub eax, ebx
    cmp eax, 0x13390
    jb buffer
    add ebx, 0x13390
    sub eax, 0x13390
buffer:
    sub eax, 0x3404
    cmp eax, 270*96
    jae no
    xor edx, edx
    mov ecx, 96
    div ecx
    test edx, edx
    jnz no
    mov edx, ebp
    push 4
    pop ecx
    call chain
    test eax, eax
    jz no
    cmp word ptr [eax+8], 3
    jne no
    test byte ptr [eax+12], 15
    jnz no
    cmp word ptr [eax+16], 0x0404
    jne no
    test byte ptr [eax+20], 7
    jnz no
    add eax, 24
    cmp word ptr [eax], 0x0206
    jne no
    movzx edx, byte ptr [eax+4]
    shr edx, 4
    dec edx
    cmp edx, 4
    ja no
    lea edx, [ebp+edx*8+48]
    push eax
    push 2
    pop ecx
    call chain
    test eax, eax
    jz receiver_no
    movzx edx, word ptr [eax+8]
    and edx, 0xfbff
    cmp edx, 0x0212
    jne receiver_no
    mov dl, [eax+12]
    and dl, 15
    sub dl, 9
    cmp dl, 1
    ja receiver_no
    pop eax
    ret
receiver_no:
    pop eax
no:
    xor eax, eax
    ret

/* EDX descriptor; return EAX hold or zero, ECX hold index (1 or2).
 * Start [-> center snap] -> finite type0/1 hold -> mode0 release -> type3.
 * Reject terminal/conditional holds and releases; match group0 only.
 */
line:
    mov ecx, [edx]
    and ecx, 15
    lea eax, [ecx-4]
    cmp eax, 1
    ja no
    call chain
    test eax, eax
    jz no
    cmp ecx, 5
    jne hold
    cmp word ptr [eax+8], 0x0402
    jne no
    test byte ptr [eax+12], 15
    jnz no
hold:
    sub ecx, 3
    lea eax, [eax+ecx*8]
    mov edx, [eax]
    and edx, 0xfffffbff
    cmp edx, 0x11
    jne no
    mov dl, [eax+4]
    and dl, 31
    cmp dl, 1
    ja no
    test word ptr [eax+4], 0x0fc0
    jz no
    cmp dword ptr [eax+8], 0x18
    jne no
    test byte ptr [eax+13], 0xc0
    jnz no
    cmp word ptr [eax+16], 0x0211
    jne no
    mov dl, [eax+20]
    and dl, 31
    cmp dl, 3
    jne no
    ret

/* EDX descriptor inside validated play; ECX exact length. The complete
 * chain must be aligned and inside THIS buffer's fixed node pool. */
chain:
    mov eax, [edx]
    and eax, 15
    cmp eax, ecx
    jne no
    mov eax, [edx+4]
    sub eax, ebx
    sub eax, 0x9adc
    cmp eax, 3500*8
    jae no
    test al, 7
    jnz no
    lea edx, [eax+ecx*8]
    cmp edx, 3500*8
    ja no
    lea eax, [ebx+eax+0x9adc]
    cmp word ptr [eax], 1
    jne no
    ret
code_end:
