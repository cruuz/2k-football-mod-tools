/* EXPERIMENTAL / UNWITNESSED. GNU as --32.
 * Live conditional-update boundary, BEFORE native movement, BEFORE its timer
 * and threat gates. ESI actor, EDI task, ECX interpreter. No stack arguments.
 * task+44 is the conditional argument (initialized to float 13 by retail),
 * not padding: this tagged callback owns it as pending/committed decision.
 * 0 keep, 1 give, 2 pass; -1 released, -2 throw requested; float13 untouched.
 * Native cache retains its actual purpose: 0 release back, 1 take, -1 wait.
 */
.intel_syntax noprefix
.code32
.text
.global tick, hud, pass_init, snap, reset, schedule, config, code_end
.extern intent_table, state_data, original_tail, result_tail, lookup_actor, held_command, receiver_ready
.extern hud_native, draw_icon, hud_tail, pass_tail, snap_tail, reset_tail, schedule_tail, schedule_mesh
/* Private RW: actor/task/descriptor/roster, last clock, frame, confidence,
 * controller, queued receiver, crash latch, selected EDGE, deadline; 11 snap
 * records at +64, each actor/roster/assignment. One offense owns the ball. */
tick:
    pushfd
    pushad
    mov ebp, esp
    and esp, -16
    sub esp, 512
    fxsave [esp]
    push ebp
    mov ebp, offset state_data
    fninit
    call lookup
    test eax, eax
    jz original
    mov ebx, eax                       /* immutable row */
    mov edx, [esi+0xc]
    xor eax, eax
    mov [edx+0x10], eax                /* no native run or stick throttle */
    mov [edx+0x1c], eax                /* raw held/rising state stays intact */
    mov eax, [edi+0x44]
    cmp eax, 2
    jbe decided
    cmp eax, 0x41500000                /* fresh native condition argument13 */
    jne active
    mov [ebp], esi
    mov [ebp+4], edi
    mov edx, [esi+0x20]
    mov edx, [edx+0x41c]
    mov [ebp+8], edx
    mov edx, [esi+0x3c]
    mov [ebp+12], edx
    push edi
    lea edi, [ebp+20]
    xor eax, eax
    push 6
    pop ecx
    cld
    rep stosd
    pop edi
    dec eax
    mov [ebp+16], eax
    mov dword ptr [edi+0x44], 0x41500001
active:
    cmp [ebp], esi
    jne invalid_active
    cmp [ebp+4], edi
    jne invalid_active
    mov edx, [esi+0x3c]
    cmp [ebp+12], edx
    jne invalid_active
    cmp dword ptr [0xe602b8], 14
    jne invalid_active
    mov eax, [0xe5fc00]
    test eax, eax
    jz invalid_active
    cmp [eax], esi
    jne invalid_active
    mov eax, [0xe6029c]
    test eax, eax
    jz pending
    mov eax, [eax+0x10]
    cmp eax, 0x40a00000                /* negative/NaN/stale: no exchange */
    jae invalid_active
    cmp [ebp+16], eax
    je pending                        /* at most once per simulation tick */
    cmp dword ptr [ebp+16], -1
    je frame_step
    cmp eax, [ebp+16]
    jb invalid_active
    jmp frame_step
invalid_active:
    jmp abandon
frame_step:
    cmp dword ptr [ebp+20], 0
    jne timed
    push eax
    fld dword ptr [esp]
    fld1
    faddp st(1)
    fstp dword ptr [ebp+44]
    pop eax
timed:
    mov [ebp+16], eax
    inc dword ptr [ebp+20]
    cmp eax, [ebp+44]
    jae clock_gate                    /* input at/after expiry cannot latch */
    mov edx, [esi+0xc]
    mov ecx, [edx]
    mov [ebp+28], ecx
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
    or dword ptr [edi+0x44], -1
clock_gate:
    call resolve_edge
    cmp [ebp+40], eax
    je same_edge
    mov [ebp+40], eax
    xor edx, edx
    mov [ebp+24], edx
    mov [ebp+36], edx
same_edge:
    mov [edi+0x40], eax
    mov edx, [esi+0xc]
    cmp dword ptr [edx], -1
    jne boundary
    call sample
    test eax, eax
    jz wide_sample
    cmp dword ptr [ebp+24], 3
    je boundary
    inc dword ptr [ebp+24]
    cmp dword ptr [ebp+24], 3
    jne boundary
    mov [ebp+36], eax
    jmp boundary
wide_sample:
    cmp dword ptr [ebp+24], 0
    je boundary
    dec dword ptr [ebp+24]
    jne boundary
    mov [ebp+36], eax
boundary:
    mov eax, [ebp+16]
    cmp eax, [ebp+44]
    jb pending
    cmp dword ptr [edi+0x44], -1
    je give
    cmp dword ptr [edi+0x44], -2
    je pass
    mov eax, [esi+0xc]
    cmp dword ptr [eax], -1
    jne keep
    cmp dword ptr [ebp+36], 0
    je give
    cmp byte ptr [ebx+22], 0
    je keep
    jmp pass
sample:
    test eax, eax
    jz not_crash
    mov edx, [eax+0x18]
    test edx, edx
    jz not_crash
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
    jae not_crash
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
    jnz not_crash
project:
    mov eax, [esi+0x18]
    fld dword ptr [edx+0x40]
    fmul dword ptr [intent_table+80]
    fadd dword ptr [edx+0x30]
    fsub dword ptr [eax+0x30]
    fabs
    fcomp dword ptr [intent_table+84]
    fnstsw ax
    test ah, 4
    jnz not_crash                           /* unordered comparison cannot keep */
    test ah, 0x45
    jz not_crash
    push 1
    pop eax
    ret
not_crash:
    xor eax, eax
    ret
pass:
    mov ecx, [esi+0x38]
    movzx edx, byte ptr [ebx+22]
    test edx, edx
    jz give
    call lookup_actor
    test eax, eax
    jz give
    mov [ebp+32], eax
    push esi
    mov esi, eax
    call receiver_ready               /* actual retail receiver gate */
    pop esi
    test eax, eax
    jz give
    push 2
    pop eax
    jmp commit
give:
    push 1
    pop eax
    jmp commit
abandon:
keep:
    xor eax, eax
commit:
    cmp eax, 2
    je store_commit
    and dword ptr [ebp+32], 0
store_commit:
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
    mov edx, [esp]
    mov [edx+16], eax                  /* saved EBX = native result */
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    jmp result_tail
pending:
    or eax, -1
    jmp result
original:
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    fld dword ptr [esp+0x1c]
    fcomp dword ptr [0x50a50c]
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
    pop ebx
    ret
clear:
    clc
    pop ebx
    ret

/* Resolve only actors present in the actual snap assignment snapshot.
 * Prefer the authored slot when valid, else the outermost play-side DE/OLB
 * executing a rush assignment. Snapshot identity prevents recycled actors.
 * Eleven candidates, fifteen script nodes, eleven blockers are hard caps. */
resolve_edge:
    push ebx
    push edi
    push ebp
    sub esp, 8
    xor eax, eax
    mov [esp], eax
    mov [esp+4], eax
    mov ebp, offset state_data+64
    push 11
    pop edi
edge_loop:
    mov eax, [ebp]
    test eax, eax
    jz edge_next
    cmp dword ptr [eax+0x48], 0
    jne edge_next
    mov edx, [esi+0x38]
    mov edx, [edx]
    cmp [eax+0x38], edx
    jne edge_next
    mov edx, [edx+4]
    push 11
    pop ecx
member:
    test edx, edx
    jz edge_next
    cmp edx, eax
    je member_ok
    mov edx, [edx+0x34]
    loop member
    jmp edge_next
member_ok:
    mov edx, [eax+0x3c]
    cmp edx, [ebp+4]
    jne edge_next
    test edx, edx
    jz edge_next
    movzx ecx, byte ptr [edx+0x35]
    cmp ecx, 16                       /* roster DE, not PLAY personnel12 */
    je role
    cmp ecx, 10                       /* roster OLB */
    jne edge_next
role:
    mov edx, [eax+0x20]
    mov edx, [edx+0x41c]
    cmp edx, [ebp+8]
    jne edge_next
    /* Descriptor and script must be in either native relocated PLAY pool. */
    mov ecx, edx
    sub ecx, 0xb75a40+0x3404
    cmp ecx, 270*96
    jb descriptor_ok
    sub ecx, 0x13390
    cmp ecx, 270*96
    jae edge_next
descriptor_ok:
    test cl, 7
    jnz edge_next
    mov ecx, [edx]
    and ecx, 15
    mov edx, [edx+4]
    push eax
    mov eax, edx
    sub eax, 0xb75a40+0x9adc
    cmp eax, 3500*8-120
    jb script_ok
    sub eax, 0x13390
    cmp eax, 3500*8-120
script_ok:
    pop eax
    jae edge_next
rush_node:
    test ecx, ecx
    jz edge_next
    cmp byte ptr [edx], 11
    je rush
    add edx, 8
    loop rush_node
    jmp edge_next
rush:
    call unblocked
    jc edge_next
    mov edx, [eax+0x18]
    test edx, edx
    jz edge_next
    mov ecx, [0xe602ec]
    fld dword ptr [intent_table+84]
    fld dword ptr [edx+0x38]
    fsub dword ptr [ecx+0x18]
    fabs
    fcomip st, st(1)
    fstp st(0)
    ja edge_next
    jp edge_next
    mov ecx, [0xe602ec]
    fld dword ptr [edx+0x30]
    fsub dword ptr [ecx+0x10]
    mov edx, [state_data+4]
    fld dword ptr [edx+0x20]
    fsub dword ptr [ecx+0x10]
    fmulp st(1)
    ftst
    push eax
    fnstsw ax
    test ah, 0x45
    pop eax
    jnz pop_next
    movzx ecx, byte ptr [eax+0x2e]
    cmp cl, [ebx+21]
    je select_authored
    fcom dword ptr [esp+4]
    push eax
    fnstsw ax
    test ah, 0x45
    pop eax
    jnz pop_next
    fstp dword ptr [esp+4]
    mov [esp], eax
    jmp edge_next
select_authored:
    fstp st(0)
    mov [esp], eax
    jmp resolved
pop_next:
    fstp st(0)
edge_next:
    add ebp, 12
    dec edi
    jnz edge_loop
resolved:
    pop eax
    add esp, 4
    pop ebp
    pop edi
    pop ebx
    ret

/* Before human priority at21516A. EBP is actor, stack locals are native.
 * Lookup is integer-only. Restrict the override to the paired live condition;
 * after native advancement the next frame uses ordinary human control. */
schedule:
    pushfd
    pushad
    mov esi, ebp
    cmp dword ptr [0xe602b8], 14
    jne schedule_original
    mov eax, [0xe5fc00]
    test eax, eax
    jz schedule_original
    cmp [eax], esi
    jne schedule_original
    mov eax, [esi+0x20]
    mov eax, [eax+0x310]
    cmp dword ptr [eax], 0x1aef80
    jne schedule_original
    call lookup
    test eax, eax
    jz schedule_original
    popad
    popfd
    mov dword ptr [esp+0x14], 1       /* native task path, not user priority */
    jmp schedule_mesh
schedule_original:
    popad
    popfd
    mov eax, [esp+0x30]
    xor esi, esi
    jmp schedule_tail

/* Disjoint from Spy's B6FB3 snap hook. Snapshot actual live assignments. */
snap:
    pushfd
    pushad
    call clear_state
    mov edi, offset state_data+64
    mov esi, [0xe60284]
    test esi, esi
    jz snap_done
    mov esi, [esi+4]
    push 11
    pop ecx
snap_actor:
    test esi, esi
    jz snap_done
    mov [edi], esi
    mov eax, [esi+0x3c]
    mov [edi+4], eax
    mov eax, [esi+0x20]
    test eax, eax
    jz snap_next
    mov eax, [eax+0x41c]
    mov [edi+8], eax
snap_next:
    add edi, 12
    mov esi, [esi+0x34]
    loop snap_actor
snap_done:
    popad
    popfd
    mov [0xe602c8], esi
    jmp snap_tail
reset:
    pushfd
    pushad
    call clear_state
    popad
    popfd
    push 0x5a
    pop ecx
    jmp reset_tail
clear_state:
    cld
    xor eax, eax
    mov edi, offset state_data
    push 64
    pop ecx
    rep stosd
    ret

/* The native world-marker queue is ready at646A1. Mark only the selected
 * EDGE row; native projection and icon0's passicons atlas supply the glyph. */
hud:
    pushfd
    pushad
    call live_state
    jc hud_done
    cmp eax, [state_data+16]
    jne hud_done
    cmp byte ptr [edx+0x450], 2
    jne hud_done
    cmp [state_data+4], edi
    jne hud_done
    cmp dword ptr [edi+0x44], 2
    jbe hud_done
    mov eax, [esi+0xc]
    mov eax, [eax]
    cmp eax, 3
    ja hud_done
    cmp [state_data+28], eax
    jne hud_done
    mov eax, [state_data+40]
    test eax, eax
    jz hud_done
    mov eax, [eax+0x3c]
    mov ecx, [0xa94ea4]
    cmp ecx, 25
    ja hud_done
    mov edx, 0xa94eac
cue_row:
    jecxz hud_done
    cmp [edx], eax
    je cue_edge
    add edx, 16
    loop cue_row
    jmp hud_done
cue_edge:
    and dword ptr [edx+12], 0xff1fffff /* icon0 at native projected EDGE head */
    or dword ptr [edx+12], 0x80       /* large native glyph */
hud_done:
    popad
    popfd
    call hud_native
    jmp hud_tail

/* Pending RPO crosses the actual pass initializer, which otherwise clears
 * the receiver. Hand the ready target to the native throw-request callback. */
pass_init:
    mov dword ptr [esi], 0x19bb60
    pushfd
    pushad
    mov ebp, esi
    call live_state
    jc pass_done
    cmp edi, ebp
    jne pass_done
    cmp byte ptr [edx+0x450], 3
    jne pass_done
    mov eax, [state_data+32]
    test eax, eax
    jz pass_done
    and dword ptr [state_data+32], 0  /* one initializer consumes one latch */
    push eax
    mov esi, eax
    call receiver_ready
    test eax, eax
    pop eax
    jz pass_done
    mov [ebp+0x40], eax
    mov dword ptr [ebp], 0x19bae0
    mov ecx, [state_data]
    call dword ptr [ebp]             /* emit native request before human priority resumes */
pass_done:
    popad
    popfd
    jmp pass_tail

/* Shared invalidation gates, returns actor ESI/state EDX/task EDI, CF. */
live_state:
    cmp dword ptr [0xe602b8], 14
    jne invalid_state
    mov esi, [state_data]
    test esi, esi
    jz invalid_state
    cmp esi, [0xbe4f8c]
    jne invalid_state
    mov eax, [0xe5fc00]
    test eax, eax
    jz invalid_state
    cmp [eax], esi
    jne invalid_state
    mov eax, [0xe6029c]
    test eax, eax
    jz invalid_state
    mov eax, [eax+0x10]
    cmp eax, 0x40a00000
    jae invalid_state
    cmp eax, [state_data+16]
    jb invalid_state
    mov ecx, [esi+0x3c]
    cmp ecx, [state_data+12]
    jne invalid_state
    mov ecx, [esi+0xc]
    mov ecx, [ecx]
    cmp ecx, [state_data+28]
    jne invalid_state
    mov edx, [esi+0x20]
    mov ecx, [edx+0x41c]
    cmp ecx, [state_data+8]
    jne invalid_state
    mov edi, [edx+0x310]
    clc
    ret
invalid_state:
    stc
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
    push 96
    pop ecx
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
code_end:
