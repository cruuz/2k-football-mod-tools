/* V5. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 * No runtime writes to executable/immutable tables. A paired native condition
 * enters GIVE when the snap reaches QB; its native event completes the handoff.
 * The scheduler accepts cancellation only while this QB still owns the ball.
 * RW: actor0, descriptor4, roster8, row12, clock16, samples20, controller24,
 * decision28 (-1 pending,0 keep,1 give,2 pass,3 pitch,4 stopped), back32,
 * receiver36, edge40, deadline44, snap48, resource index52, native index56,
 * book60, A released64, confidence68, crash72, started76, lane80/depth84,
 * held88/pressed92, eleven actor/roster/descriptor snap records96..227.
 */
.intel_syntax noprefix
.code32
.text
.global tick, schedule, snap, reset, hud, pass_init, exchange, config, code_end
.extern state_data, intent_table, lookup_actor, receiver_ready
.extern original_tail, result_tail, schedule_tail, schedule_mesh, snap_tail, reset_tail
.extern hud_native, hud_tail, draw_text, pass_tail, exchange_tail
.extern animation_change, set_node, decode_node, transition, give_init, pass_native, carry_init, release_task

/* A branch result is not a commitment: native GIVE/TAKE run while RW is pend. */
tick:
    pushfd
    push eax
    mov eax, offset state_data
    cmp esi, [eax]
    jne tick_retail
    cmp dword ptr [eax+12], 0
    je tick_retail
    cmp dword ptr [eax+28], -1
    jne tick_retail
    mov ebx, [eax+76]
    test ebx, ebx
    jnz tick_result
    dec ebx                          /* await snap reception; no condition movement */
tick_result:
    pop eax
    popfd
    jmp result_tail
tick_retail:
    pop eax
    popfd
    fld dword ptr [esp+0x1c]
    fcomp dword ptr [0x50a50c]
    jmp original_tail

schedule:
    pushfd
    pushad
    mov esi, ebp
    mov ebp, esp
    and esp, -16
    sub esp, 512
    fxsave [esp]
    push ebp
    fninit
    mov ebp, offset state_data
    cmp esi, [ebp]
    jne schedule_original
    cmp dword ptr [ebp+12], 0
    je schedule_original
    cmp dword ptr [ebp+28], 1
    jg schedule_original
check_life:
    cmp dword ptr [0xe602b8], 14
    jne stopped
    mov eax, [esi+0x20]
    mov edx, [eax+0x41c]
    cmp edx, [ebp+4]
    jne stopped
    mov ecx, [ebp+12]
    movzx ecx, byte ptr [ecx+20]
    lea edx, [edx+ecx*8]
    mov eax, [ebp+32]
    mov eax, [eax+0x20]
    cmp [eax+0x41c], edx
    jne stopped
    mov edx, [esi+0x3c]
    cmp edx, [ebp+8]
    jne stopped
    mov edx, [esi+0xc]
    mov ecx, [edx]
    cmp ecx, [ebp+24]
    jne stopped
    mov edi, [esi+0x20]
    movzx ebx, byte ptr [edi+0x450]
    cmp ebx, 1
    jbe force_task                    /* align/receive; snap still on center or in flight */
    mov eax, [0xe5fc00]
    test eax, eax
    jz before_receive
    cmp [eax], esi
    je has_ball
    mov eax, [eax]
    cmp eax, [ebp+32]
    jne before_receive
    push 1
    pop dword ptr [ebp+28]
    jmp schedule_original
before_receive:
    cmp byte ptr [ebp+76], 0
    je force_task
stopped:
    push 4
    pop dword ptr [ebp+28]
    jmp schedule_original
has_ball:
    cmp dword ptr [ebp+28], 0
    je kept
    cmp dword ptr [ebp+28], 1
    je force_task
    mov eax, [0xe6029c]
    test eax, eax
    jz force_task
    mov eax, [eax+0x10]
    cmp eax, 0x7f800000                /* finite, nonnegative snap clock */
    jae stopped
    cmp eax, [ebp+16]
    jb stopped
    jne new_clock
    cmp dword ptr [ebp+20], 0
    jne force_task
new_clock:
    mov [ebp+16], eax
    cmp ebx, 2
    je start_mesh
    cmp ebx, 4
    jne stopped
    jmp mesh
start_mesh:
    cmp dword ptr [ebp+76], 0
    jne mesh
    inc dword ptr [ebp+76]
    mov edi, [edi+0x310]
    mov eax, [edi+0x20]
    mov [ebp+80], eax
    mov eax, [edi+0x28]
    mov [ebp+84], eax
    fld dword ptr [ebp+16]
    fld1
    faddp st(1)
    fstp dword ptr [ebp+44]
mesh:
    inc dword ptr [ebp+20]
    mov ecx, [ebp+24]
    cmp ecx, -1
    je cpu
    cmp ecx, 3
    ja give
    imul ecx, ecx, 44
    mov eax, [ecx+0xa9b95c]
.ifdef READ_DIAGNOSTIC
    mov [ebp+88], eax
.endif
    test eax, 0x100
    jnz held_a
    mov byte ptr [ebp+64], 1
held_a:
    mov eax, [ecx+0xa9b954]
.ifdef READ_DIAGNOSTIC
    mov [ebp+92], eax
.endif
    test eax, 0x1000                   /* Xbox Black, explicit pitch */
    jnz pitch
    mov ebx, [ebp+12]
    cmp byte ptr [ebx+22], 0
    je check_keep
    test eax, 0x400                    /* Xbox X, pull/pass to named receiver */
    jnz pass
    movzx edx, byte ptr [ebx+22]
    movzx edx, byte ptr [edx*2+0xbdfcd0]
    cmp edx, 4
    ja check_keep
    mov edx, [edx*4+0x4faac0]          /* native receiver mask, slot6 = A */
    test eax, edx
    jnz pass
check_keep:
    cmp byte ptr [ebp+64], 0
    je force_task
    test eax, 0x100
    jnz keep
    jmp force_task
cpu:
    mov eax, [ebp+16]
    cmp eax, [ebp+44]
    jae give
    mov ebx, [ebp+12]
    call resolve_edge
    cmp eax, [ebp+40]
    je same_edge
    mov [ebp+40], eax
    and dword ptr [ebp+68], 0
same_edge:
    call sample
    test eax, eax
    jnz crash_sample
    cmp dword ptr [ebp+68], 0
    je force_task
    dec dword ptr [ebp+68]
    jmp force_task
crash_sample:
    inc dword ptr [ebp+68]
    cmp dword ptr [ebp+68], 3
    jb force_task
    mov ebx, [ebp+12]
    cmp byte ptr [ebx+22], 0
    jne pass
    /* Close crash: lateral; otherwise pull and keep. */
    mov eax, [ebp+40]
    mov eax, [eax+0x18]
    mov edx, [esi+0x18]
    fld dword ptr [eax+0x30]
    fsub dword ptr [edx+0x30]
    fabs
    fcomp dword ptr [intent_table+64]
    fnstsw ax
    test ah, 0x45
    jnz pitch
keep:
    xor eax, eax
    jmp cancel
pitch:
    push 3
    pop eax
    jmp cancel
pass:
    mov ebx, [ebp+12]
    movzx edx, byte ptr [ebx+22]
    test edx, edx
    jz force_task
    mov ecx, [esi+0x38]
    call lookup_actor
    test eax, eax
    jz force_task
    mov [ebp+36], eax
    push esi
    mov esi, eax
    call receiver_ready
    pop esi
    test eax, eax
    jz force_task
    push 2
    pop eax
cancel:
    mov [ebp+28], eax                  /* latch BEFORE native callbacks */
    /* Native animation transition invokes both participants' destructors.
     * The exchange hook rejects an already queued, canceled give event. */
    mov ecx, [ebp+32]
    push ecx
    call cancel_animation
    pop esi
    push 2                            /* back's native release/fake branch */
    pop edx
    cmp dword ptr [ebp+28], 3
    jne back_node
    inc edx                           /* pitch back stays in native TAKE */
back_node:
    call select_node
    mov eax, [edi]
    mov eax, [eax+4]
    movzx edx, byte ptr [edi+0x34]
    movzx eax, byte ptr [eax+edx*8]
    mov ecx, [eax*4+0xbe5110]
    mov edx, esi
    call transition
    mov esi, [ebp]
    mov ecx, esi
    call cancel_animation
    cmp dword ptr [ebp+28], 0
    je carry
    push 3
    pop edx
    cmp dword ptr [ebp+28], 2
    je qb_node
    inc edx
qb_node:
    call select_node
    cmp dword ptr [ebp+28], 3
    jne throwing
    /* Native opcode19 decoded kind = 1. This actor's operand cache, not PLAY. */
    mov dword ptr [edi+0x18], 0x3f800000
    mov ecx, offset give_init
    jmp enter
throwing:
    mov ecx, offset pass_native
    jmp enter
carry:
    mov edi, [esi+0x20]
    or dword ptr [edi+0x420], 0x820000
    mov ecx, offset carry_init
enter:
    mov edx, esi
    call transition
    cmp dword ptr [ebp+28], 0
    jne schedule_original
kept:
    cmp dword ptr [ebp+24], -1
    je schedule_original
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    mov dword ptr [esp+0x14], 0
    jmp schedule_human
/* ESI actor, EDX node; native pointer/decode operations preserve shared PLAY. */
select_node:
    mov edi, [esi+0x20]
    add edi, 0x41c
    and dword ptr [edi+4], 0xfffc7fc0
    mov ecx, edi
    call set_node
    mov eax, edi
    call decode_node
    ret
cancel_animation:
    mov eax, [ecx+0xc]
    and dword ptr [eax+0x10], 0
    mov edx, 0x50f4ec
    jmp animation_change
give:
    push 1
    pop dword ptr [ebp+28]
force_task:
    mov edx, [esi+0xc]
    and dword ptr [edx+0x10], 0
    and dword ptr [edx+0x1c], 0
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    mov dword ptr [esp+0x14], 1
    jmp schedule_mesh
schedule_original:
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
    mov eax, [esp+0x30]
    xor esi, esi
    jmp schedule_tail

/* Snap establishes exact identity once, independent of the current node. */
snap:
    pushfd
    pushad
    call clear_state
    mov ebp, offset state_data
.ifdef READ_DIAGNOSTIC
    inc dword ptr [ebp+48]
.endif
    or dword ptr [ebp+28], -1
.ifdef READ_DIAGNOSTIC
    or dword ptr [ebp+52], -1
    or dword ptr [ebp+56], -1
.endif
    mov ecx, [0xe60280]
    test ecx, ecx
    jz snap_done
    xor edx, edx
    call lookup_actor
    test eax, eax
    jz snap_done
    mov esi, eax
    mov [ebp], esi
    mov eax, [esi+0x20]
    test eax, eax
    jz snap_done
    mov eax, [eax+0x41c]
    mov [ebp+4], eax
    mov eax, [esi+0x3c]
    mov [ebp+8], eax
    mov eax, [esi+0xc]
    mov eax, [eax]
    mov [ebp+24], eax
    call lookup
    mov [ebp+12], eax
    test eax, eax
    jz snap_done
    movzx edx, byte ptr [eax+20]
    mov ecx, [esi+0x38]
    call lookup_actor
    mov [ebp+32], eax
    test eax, eax
    jnz snapshot
    and dword ptr [ebp+12], 0
    jmp snap_done
snapshot:
    lea edi, [ebp+96]
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
    mov eax, [eax+0x41c]
    mov [edi+8], eax
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

/* Native pass initializer consumes the receiver once, before human priority. */
pass_init:
    mov dword ptr [esi], 0x19bb60
    pushfd
    pushad
    mov ebp, offset state_data
    cmp dword ptr [ebp+28], 2
    jne pass_done
    mov ecx, [ebp]
    mov eax, [ecx+0x20]
    cmp [eax+0x310], esi
    jne pass_done
    mov eax, [ebp+36]
    test eax, eax
    jz pass_done
    and dword ptr [ebp+36], 0
    mov [esi+0x40], eax
    mov dword ptr [esi], 0x19bae0
    call dword ptr [esi]
pass_done:
    popad
    popfd
    jmp pass_tail

/* This callback's native arguments are (event, actor), stdcall ret8. */
exchange:
    pushfd
    push eax
    push ecx
    mov eax, offset state_data
    mov ecx, [esp+20]
    cmp ecx, [eax]
    jne exchange_native
    cmp dword ptr [eax+12], 0
    je exchange_native
    cmp dword ptr [eax+28], -1
    jne exchange_decided
    push 1
    pop dword ptr [eax+28]
exchange_decided:
    cmp dword ptr [eax+28], 1
    je exchange_native
    cmp dword ptr [eax+28], 4          /* scope ended: leave retail alone */
    jae exchange_native
    pop ecx
    pop eax
    popfd
    ret 8
exchange_native:
    pop ecx
    pop eax
    popfd
    push ebp
    mov ebp, esp
    and esp, -16
    jmp exchange_tail

/* Actual team's loaded book, not the custom-playbook editor's fixed buffers.
 * Offset is used only to report the source index after all four hashes match;
 * header-bounded descriptor identity tolerates native record reordering. */
lookup:
    mov edi, offset paired_contract
    test edi, edi
    jz lookup_native
    cmp dword ptr [edi], 0
    je lookup_native
    mov ecx, [ebp+4]
    call dword ptr [edi]
    test eax, eax
    jz lookup_native
    mov edi, eax
    jmp lookup_root
lookup_native:
    mov edi, [esi+0x38]
    mov edi, [edi+0x20]
lookup_root:
.ifdef READ_DIAGNOSTIC
    mov [ebp+60], edi
.endif
    test edi, edi
    jz no
    mov edx, [ebp+4]
    mov eax, edx
    sub eax, [edi+0x60]
    sub eax, 8
    cmp eax, 270*96
    jae no
    push edx
    xor edx, edx
    push 96
    pop ecx
    div ecx
    test edx, edx
    pop edx
    jne no
    cmp eax, [edi+0x38]
    jae no
.ifdef READ_DIAGNOSTIC
    mov [ebp+56], eax
.endif
    push esi
    mov ebx, offset intent_table+16
    mov ecx, [intent_table+8]
row:
    jecxz not_found
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
.ifdef READ_DIAGNOSTIC
    mov eax, [ebx+4]
    sub eax, 0x3404
    xor edx, edx
    push 96
    pop ecx
    div ecx
    mov [ebp+52], eax
.endif
    mov eax, ebx
    pop esi
    ret
mismatch:
    pop edx
    pop ecx
    add ebx, 24
    dec ecx
    jmp row
not_found:
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
    sub eax, [edi+0x68]
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

.ifndef READ_DIAGNOSTIC
sample:
    test eax, eax
    jz not_crash
    mov edx, [eax+0x18]
    test edx, edx
    jz not_crash
    /* Reject nonfinite/unbounded position and velocity before arithmetic. */
    push 8
    pop ecx
finite:
    mov eax, [edx+ecx*4+0x2c]
    and eax, 0x7fffffff
    cmp eax, 0x49742400
    jae not_crash
    loop finite
    /* Predict lateral separation .2s forward, normalized by the actual
     * decoded mesh destination. Inward AND within 2.5 yards means crash. */
    mov eax, [0xe602ec]
    fld dword ptr [ebp+80]
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
    fld dword ptr [ebp+84]
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
    mov ebp, offset state_data+96
    push 11
    pop edi
edge_loop:
    mov eax, [ebp]
    test eax, eax
    jz edge_skip
    cmp dword ptr [eax+0x48], 0
    jne edge_skip
    mov edx, [esi+0x38]
    mov edx, [edx]
    cmp [eax+0x38], edx
    jne edge_skip
    mov edx, [edx+4]
    push 11
    pop ecx
member:
    test edx, edx
    jz edge_skip
    cmp edx, eax
    je member_ok
    mov edx, [edx+0x34]
    loop member
edge_skip:
    jmp edge_next
member_ok:
    mov edx, [eax+0x3c]
    cmp edx, [ebp+4]
    jne edge_skip
    test edx, edx
    jz edge_skip
    movzx ecx, byte ptr [edx+0x35]
    cmp ecx, 16                       /* roster DE, not PLAY personnel12 */
    je role
    cmp ecx, 10                       /* roster OLB */
    jne edge_skip
role:
    mov edx, [eax+0x20]
    mov edx, [edx+0x41c]
    cmp edx, [ebp+8]
    jne edge_skip
    /* Snapshot identity plus bounds in this defender's actual loaded book. */
    mov ecx, [eax+0x38]
    mov ecx, [ecx+0x20]
    test ecx, ecx
    jz edge_skip
    push eax
    mov eax, [edx+4]
    sub eax, [ecx+0x68]
    cmp eax, 3500*8-120
    pop eax
    jae edge_skip
    mov ecx, [edx]
    and ecx, 15
    mov edx, [edx+4]

rush_node:
    test ecx, ecx
    jz edge_skip
    cmp byte ptr [edx], 11
    je rush
    add edx, 8
    loop rush_node
    jmp edge_skip
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
    fld dword ptr [state_data+80]
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
.else
resolve_edge:
sample:
    xor eax, eax
    ret
.endif
hud:
.ifdef READ_DIAGNOSTIC
    pushfd
    pushad
    mov ebp, esp
    and esp, -16
    sub esp, 512
    fxsave [esp]
    push ebp
    mov ebp, offset state_data
    cmp dword ptr [ebp+48], 0
    je hud_done
    sub esp, 224                       /* native FONT clone + 48 UTF-16 units */
    mov edi, esp
    mov esi, 0xa95040
    push 32
    pop ecx
    cld
    rep movsd
    mov eax, 0x44414552                /* READ */
    call emit_word
    mov eax, [ebp+52]
    cmp dword ptr [ebp+12], 0
    jne number
    mov eax, 0x7373696d
    call emit_word
    mov eax, [ebp+56]
number:
    cmp eax, -1
    jne decimal
    mov eax, 0x203f3f3f
    call emit_word
    jmp draw
decimal:
    push 10
    pop ebx
    xor ecx, ecx
digit:
    xor edx, edx
    div ebx
    push edx
    inc ecx
    test eax, eax
    jnz digit
pop_digit:
    pop eax
    add ax, '0'
    stosw
    loop pop_digit
    mov ax, ' '
    stosw
    cmp dword ptr [ebp+12], 0
    je draw
    mov eax, 0x70616e73                /* snap */
    cmp dword ptr [ebp+76], 0
    je phase
    mov eax, 0x646e6570                /* pend */
    mov ecx, [ebp+28]
    inc ecx
    jz phase
    mov eax, 0x7065656b                /* keep */
    dec ecx
    jz phase
    mov eax, 0x65766967                /* give */
    dec ecx
    jz phase
    mov eax, 0x73736170                /* pass */
    dec ecx
    jz phase
    mov eax, 0x63746970                /* pitc + h */
    dec ecx
    jz phase
    mov eax, 0x706f7473                /* stop */
phase:
    push eax
    call emit_word
    pop eax
    cmp eax, 0x63746970
    jne draw
    mov word ptr [edi-2], 'h'
draw:
    xor eax, eax
    stosw
    mov ecx, esp
    mov dword ptr [ecx+16], 0x42000000
    mov dword ptr [ecx+20], 0x42800000
    and dword ptr [ecx+24], 0
    and dword ptr [ecx+100], 0
    and dword ptr [ecx+104], 0
    or dword ptr [ecx+32], -1
    lea edx, [ecx+128]
    cmp dword ptr [ecx], 0
    je no_font
    call draw_text
no_font:
    add esp, 224
hud_done:
    pop ebp
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
.endif
    call hud_native
    jmp hud_tail
.ifdef READ_DIAGNOSTIC
emit_word:
    push 4
    pop ecx
letter:
    movzx edx, al
    mov [edi], dx
    add edi, 2
    shr eax, 8
    loop letter
    mov ax, ' '
    stosw
    ret
.endif
.balign 4, 0xcc
config:
code_end:
