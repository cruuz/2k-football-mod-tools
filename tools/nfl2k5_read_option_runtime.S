/* EXPERIMENTAL / UNWITNESSED. GNU as --32.
 * Live conditional-update boundary, AFTER native movement, BEFORE its timer
 * and threat gates. ESI actor, EDI task, ECX interpreter. No stack arguments.
 * task+44 is the conditional argument (initialized to float 13 by retail),
 * not padding: this tagged callback owns it as pending/committed decision.
 * 0 keep, 1 give, 2 pass; -1 released, -2 throw requested; float13 untouched.
 * Native cache retains its actual purpose: 0 release back, 1 take, -1 wait.
 */
.intel_syntax noprefix
.code32
.text
.global tick, config, code_end
.extern intent_table, original_tail, result_tail, lookup_actor, held_command, receiver_ready
tick:
    pushfd
    pushad
    mov ebp, esp
    and esp, -16
    sub esp, 512
    fxsave [esp]
    fninit
    call lookup
    test eax, eax
    jz original
    mov ebx, eax                       /* immutable row */
    mov eax, [edi+0x44]
    cmp eax, 2
    jbe decided
    cmp eax, 0x41500000                /* fresh native condition argument13 */
    jne active
    mov ecx, [esi+0x38]
    mov ecx, [ecx]
    movzx edx, byte ptr [ebx+21]
    call lookup_actor
    mov [edi+0x40], eax                /* retain selected defender in task */
    mov dword ptr [edi+0x44], 0x41500001
active:
    cmp dword ptr [0xe602b8], 14
    jne pending
    mov eax, [0xe5fc00]
    test eax, eax
    jz abandon
    cmp [eax], esi
    jne abandon                       /* never initiate a lost-ball exchange */
    mov edx, [esi+0xc]
    mov ecx, [edx]
    cmp ecx, -1
    je clock_gate
    cmp ecx, 3
    ja release
    imul eax, ecx, 44
    mov eax, [eax+0xa9b960]
    cmp eax, 8
    je human
    cmp eax, 10
    jne release
human:
    /* Same physical column as command3 in presnap contexts3/4. Query its
     * live running command through the retail held-command table reader. */
    push ecx
    imul ecx, ecx, 28
    mov ecx, [ecx+0xe5fe90]
    cmp ecx, 2
    ja invalid_layout
    imul ecx, ecx, 21
    add eax, ecx
    imul eax, eax, 108
    mov edx, [eax+0xa99ec0]
    pop ecx
    call held_command
    test eax, eax
    jz release
    cmp dword ptr [edi+0x44], -1
    je clock_gate
    movzx eax, byte ptr [ebx+22]        /* intended pass slot, 0 when zone */
    sub eax, 6
    cmp eax, 2
    ja clock_gate
    mov edx, [eax*4+0x4faac0]
    mov eax, [esi+0xc]
    imul eax, [eax], 44
    test [eax+0xa9b954], edx            /* rising edge, never held throw */
    jz clock_gate
    mov dword ptr [edi+0x44], -2
    jmp clock_gate
invalid_layout:
    pop ecx
release:
    cmp dword ptr [edi+0x44], -2
    je clock_gate
    mov dword ptr [edi+0x44], -1
clock_gate:
    mov eax, [0xe6029c]
    test eax, eax
    jz pending
    mov eax, [eax+0x10]
    cmp eax, 0x3eb33333                /* mesh: float .35 since snap */
    jb pending
    cmp eax, 0x40a00000                /* invalid/stale time: no transfer */
    jae abandon
    cmp dword ptr [edi+0x44], -1
    je give
    cmp dword ptr [edi+0x44], -2
    je pass
    mov eax, [esi+0xc]
    cmp dword ptr [eax], -1
    jne keep
    mov eax, [edi+0x40]
    test eax, eax
    jz give
    call unblocked
    jc give
    mov edx, [eax+0x18]
    test edx, edx
    jz give
    /* Reject nonfinite/unbounded position and velocity before arithmetic. */
    lea ecx, [edx+0x30]
    push 8
    pop eax
finite:
    push eax
    mov eax, [ecx]
    and eax, 0x7fffffff
    cmp eax, 0x49742400
    pop eax
    jae give
    add ecx, 4
    dec eax
    jnz finite
    /* Predict lateral separation .2s forward, normalized by the actual
     * decoded mesh destination. Inward AND within 2.5 yards means crash. */
    mov eax, [0xe602ec]
    fld dword ptr [edi+0x20]
    fsub dword ptr [eax+0x10]           /* signed authored lane, not moving QB */
    fld dword ptr [edx+0x40]
    fmul st, st(1)
    ftst
    fnstsw ax
    fstp st(0)
    fstp st(0)
    test ah, 1
    jnz project
    mov eax, [0xe602ec]
    fld dword ptr [edi+0x28]
    fsub dword ptr [eax+0x18]
    fmul dword ptr [edx+0x48]
    ftst
    fnstsw ax
    fstp st(0)
    test ah, 0x45
    jnz give
project:
    mov eax, [esi+0x18]
    fld dword ptr [edx+0x40]
    fmul dword ptr [config]
    fadd dword ptr [edx+0x30]
    fsub dword ptr [eax+0x30]
    fabs
    fcomp dword ptr [config+4]
    fnstsw ax
    test ah, 4
    jnz give                           /* unordered comparison cannot keep */
    test ah, 0x45
    jz give
    cmp byte ptr [ebx+22], 0
    je keep
pass:
    mov ecx, [esi+0x38]
    movzx edx, byte ptr [ebx+22]
    test edx, edx
    jz give
    call lookup_actor
    test eax, eax
    jz give
    push esi
    mov esi, eax
    call receiver_ready               /* actual retail receiver gate */
    pop esi
    test eax, eax
    jz give
    mov eax, 2
    jmp commit
give:
    mov eax, 1
    jmp commit
abandon:
keep:
    xor eax, eax
commit:
    mov [edi+0x44], eax                /* sole commitment before native exit */
decided:
    cmp eax, 1
    je result
    test eax, eax
    jnz pass_result
    cmp byte ptr [ebx+22], 0
    je result
    mov edx, [esi+0x20]
    or dword ptr [edx+0x420], 0x20000   /* native terminal -> carrying exit */
pass_result:
    xor eax, eax                      /* back releases on keep OR pass */
result:
    mov [ebp+16], eax                  /* saved EBX = native result */
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    jmp result_tail
pending:
    or eax, -1
    jmp result
original:
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    fld dword ptr [edi+0x60]
    fcomp dword ptr [0x4e4180]
    jmp original_tail

/* Conservative live blocker check: an offensive assignment targeting the
 * selected edge disqualifies that CPU read. Never alter a block or defender.
 * EAX target, CF blocked/invalid. QB's own read target is deliberately ignored.
 */
unblocked:
    push ebx
    mov ecx, [esi+0x38]
    mov ecx, [ecx+4]
    push 11
    pop ebx
blocker:
    test ecx, ecx
    jz clear
    cmp ecx, esi
    je next_blocker
    mov edx, [ecx+0x20]
    test edx, edx
    jz blocked
    mov edx, [edx+0x310]
    test edx, edx
    jz blocked
    cmp [edx+0x40], eax
    je blocked
next_blocker:
    mov ecx, [ecx+0x34]
    dec ebx
    jnz blocker
    test ecx, ecx
    jz clear
blocked:
    stc
clear:
    pop ebx
    ret

/* Exact identity in either bounded relocated PLAY buffer. Hash book/name,
 * both participant scripts, and require QB slot0 / condition node2. */
lookup:
    cmp byte ptr [esi+0x2e], 0
    jne no
    mov edx, [esi+0x20]
    cmp byte ptr [edx+0x450], 2
    jne no
    mov edx, [edx+0x41c]
    mov ecx, 0xb75a40
    mov eax, edx
    sub eax, ecx
    cmp eax, 0x13390
    jb buffer
    add ecx, 0x13390
    sub eax, 0x13390
buffer:
    sub eax, 0x3404
    cmp eax, 270*96
    jae no
    push edx
    xor edx, edx
    push ecx
    mov ecx, 96
    div ecx
    pop ecx
    test edx, edx
    pop edx
    jne no
    push esi
    push edi
    mov edi, ecx                      /* PLAY base */
    mov ebx, offset intent_table+16
    mov ecx, [intent_table+8]
row:
    jecxz not_found
    mov eax, edx
    sub eax, edi
    cmp [ebx+4], eax
    jne next
    push ecx
    push edx
    mov esi, [edi+0x30]
    call name_hash
    cmp eax, [ebx]
    jne mismatch
    mov edx, [esp]
    mov esi, [edx-8]
    call name_hash
    cmp eax, [ebx+16]
    jne mismatch
    mov edx, [esp]
    call script_hash
    cmp eax, [ebx+8]
    jne mismatch
    movzx edx, byte ptr [ebx+20]
    lea edx, [edx*8]
    add edx, [esp]
    call script_hash
    cmp eax, [ebx+12]
    jne mismatch
    pop edx
    pop ecx
    mov eax, ebx
    pop edi
    pop esi
    ret
mismatch:
    pop edx
    pop ecx
next:
    add ebx, 24
    dec ecx
    jmp row
not_found:
    pop edi
    pop esi
no:
    xor eax, eax
    ret
script_hash:
    mov eax, [edx]
    and eax, 15
    cmp eax, 5
    jne no
    mov esi, [edx+4]
    mov eax, esi
    sub eax, edi
    sub eax, 0x9adc
    cmp eax, 3500*8-40
    ja no
    push 40
    pop ecx
    jmp hash
name_hash:
    mov eax, esi
    sub eax, edi
    sub eax, 0x10840
    cmp eax, 0x2b50-128
    ja no
    xor ecx, ecx
name_scan:
    cmp word ptr [esi+ecx], 0
    je hash
    add ecx, 2
    cmp ecx, 126
    jb name_scan
    jmp no
hash:
    mov eax, 0x811c9dc5
    jecxz hash_done
hash_byte:
    movzx edx, byte ptr [esi]
    xor eax, edx
    imul eax, eax, 0x01000193
    inc esi
    loop hash_byte
hash_done:
    ret
.balign 4, 0xcc
config:
    .float .2, 228.6
code_end:
