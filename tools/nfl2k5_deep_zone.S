/* EXPERIMENTAL / UNWITNESSED. Three native wrappers, no shared detours.
 * init: ECX=P after the complete native zone initializer, before 23A8C0.
 * tick: ECX=P before native directional row update 305870.
 * RW: eleven 21-byte records indexed by verified native zone record:
 * P, S, assignment script, QB, original throttle, byte flags. 0 absent, 1 armed, 2 ended,
 * bit 4 press bail, bit 8 heading correction in progress. Padding stays zero.
 * Retail planners retain their callback, target, landmark and event ownership.
 */
.intel_syntax noprefix
.code32
.text
.global init, tick, planner, config, code_end
.extern state_data, native_init_tail, native_rows, bearing, effective_facing, native_planner_tail

/* All wrappers save every incoming GPR, flag and x87/SSE register. */
.macro SAVE
    pushfd
    pushad
    mov ebp, esp
    and esp, -16
    sub esp, 544
    fxsave [esp]
    fninit
    mov ebx, ecx
.endm
.macro RESTORE
    fxrstor [esp]
    mov esp, ebp
    popad
    popfd
.endm

init:
    SAVE
    call eligible
    test eax, eax
    jz init_done
    mov [edi], ebx
    mov [edi+4], esi
    mov eax, [esi+0x41c]
    mov [edi+8], eax
    mov eax, [0xbe4f8c]
    mov [edi+12], eax
    mov eax, [esi+0x310]
    mov eax, [eax+0x34]
    mov [edi+16], eax
    mov byte ptr [edi+20], 2
    cmp dword ptr [0xe602b8], 14
    jne init_done
    cmp dword ptr [config], 0
    je init_bail
    mov byte ptr [edi+20], 1
init_bail:
    cmp dword ptr [config+4], 0
    je init_done
    /* Exactly three native deep records; modes 9/10 alone are insufficient. */
    mov edx, [0xbe4d40]
    and edx, 0x3ff
    mov eax, 0xbe4b6c
    xor ecx, ecx
count_deep:
    test byte ptr [eax], 8
    jz next_deep
    inc ecx
next_deep:
    add eax, 16
    dec edx
    jnz count_deep
    cmp ecx, 3
    jne init_done
    call direction
    test eax, eax
    jz init_done
    mov edx, [ebx+0x18]
    fld dword ptr [edx+0x38]
    mov ecx, [0xe602ec]
    test ecx, ecx
    jz init_pop
    fsub dword ptr [ecx+0x18]
    fmul dword ptr [esp+512]
    fstp dword ptr [esp+516]
    mov eax, [esp+516]
    test eax, eax
    js init_done
    cmp eax, dword ptr [config+8] /* actual depth <= 2 yd, finite */
    ja init_done
    mov byte ptr [edi+20], 5
    jmp init_done
init_pop:
    fstp st(0)
init_done:
    RESTORE
    jmp native_init_tail

planner:
    SAVE
    mov dword ptr [esp+536], 1
    jmp policy
tick:
    SAVE
    mov dword ptr [esp+536], 0
policy:
    call eligible
    test eax, eax
    jz retire_identity
    cmp [edi], ebx
    jne tick_done
    cmp [edi+4], esi
    jne tick_done
    mov eax, [esi+0x41c]
    cmp [edi+8], eax
    jne end_policy
    test byte ptr [edi+20], 1
    jz tick_done
    cmp dword ptr [0xe602b8], 14
    jne end_policy
    mov eax, [0xe602ec]
    test eax, eax
    jz end_policy
    /* These are distinct native event identities, not owner-change guesses. */
    cmp dword ptr [eax+0x1c8], 0 /* 35AF40 -> A0B90 -> B7430, passer */
    jne pass_event
    cmp dword ptr [eax+0x1c4], 0 /* kick */
    jne end_policy
    cmp dword ptr [eax+0x1d0], 0 /* lateral/punt family */
    jne end_policy
    mov eax, [esi+0x310]
    mov ecx, [eax]
    cmp ecx, 0x1a5790
    je zone_task
    cmp ecx, 0x1a5090
    jne end_policy
zone_task:
    test dword ptr [esi+0x420], 0x20000000 /* native Spy command wins */
    jnz end_policy
    test byte ptr [esi+0x584], 0x20 /* player lock */
    jnz end_policy
    mov ecx, [ebx+0x0c]
    cmp dword ptr [ecx], -1
    jne end_policy
    cmp dword ptr [ecx+0x1c], 0 /* queued special action */
    jne end_policy
    mov edx, [ebx+0x10]
    cmp dword ptr [edx+4], 0x50f4ec
    jne end_policy
    cmp dword ptr [edx+0x14], 0x511070 /* ordinary DB movement bank */
    jne end_policy
    test byte ptr [edx+0x28], 1
    jnz end_policy
    /* dt and throttle must be finite and bounded before floating point work. */
    mov eax, [0xb71d0c]
    test eax, eax
    jle tick_done
    cmp eax, 0x3dcccccd
    ja end_policy
    mov eax, [ecx+0x10]
    test eax, eax
    js end_policy
    cmp eax, 0x3f800000
    ja end_policy
    mov edx, [edi+12]
    test edx, edx
    jz end_policy
    cmp edx, -1
    je end_policy
    cmp edx, [0xbe4f8c]
    jne end_policy
    cmp dword ptr [edx+0x1c], 1
    jne end_policy
    mov eax, [edx+0x38]
    cmp eax, [0xe60280]
    jne end_policy
    mov eax, [edx+0x3c]
    test eax, eax
    jz end_policy
    cmp byte ptr [eax+0x35], 0 /* exact roster QB */
    jne end_policy
    mov eax, [0xe5fc00]
    test eax, eax
    jz end_policy
    cmp [eax], edx /* handoff/free ball/turnover ends, without calling it a pass */
    jne end_policy
    mov edx, [edx+0x18]
    test edx, edx
    jz end_policy
    mov [esp+520], edx
    call direction
    test eax, eax
    jz end_policy
    /* Finite, plausible actor/QB x/z and LOS; never compare NaN as an angle. */
    mov edx, [ebx+0x18]
    call finite_xz
    test eax, eax
    jz end_policy
    mov edx, [esp+520]
    call finite_xz
    test eax, eax
    jz end_policy
    mov eax, [0xe602ec]
    mov eax, [eax+0x18]
    and eax, 0x7fffffff
    cmp eax, 0x49742400
    jae end_policy
    /* QB crossing the line into a run releases the preference. */
    mov edx, [esp+520]
    fld dword ptr [edx+0x38]
    mov eax, [0xe602ec]
    fsub dword ptr [eax+0x18]
    fmul dword ptr [esp+512]
    fstp dword ptr [esp+516]
    mov eax, [esp+516]
    test eax, eax
    jns end_policy
    /* Bail alone returns to retail after recovering seven yards of depth. */
    cmp dword ptr [config], 0
    jne receiver
    mov edx, [ebx+0x18]
    fld dword ptr [edx+0x38]
    mov eax, [0xe602ec]
    fsub dword ptr [eax+0x18]
    fmul dword ptr [esp+512]
    fstp dword ptr [esp+516]
    mov eax, [esp+516]
    test eax, eax
    js end_policy
    cmp eax, dword ptr [config+12]
    jae bail_release
receiver:
    /* Native A+40 is retained, never replace receiver identity with the QB. */
    mov eax, [esi+0x310]
    mov edx, [eax+0x40]
    test edx, edx
    jz face
    cmp edx, -1
    je end_policy
    cmp dword ptr [edx+0x1c], 1
    jne end_policy
    mov eax, [edx+0x38]
    cmp eax, [0xe60280]
    jne end_policy
    mov edx, [edx+0x18]
    call finite_xz
    test eax, eax
    jz end_policy
    fld dword ptr [edx+0x38]
    mov eax, [ebx+0x18]
    fsub dword ptr [eax+0x38]
    fmul dword ptr [esp+512]
    fstp dword ptr [esp+516]
    mov eax, [esp+516]
    test eax, eax
    js face
    cmp eax, dword ptr [config+16] /* one yard beyond: latch until initializer */
    jae end_policy
face:
    cmp dword ptr [esp+536], 0
    jne planner_cap
    mov edx, [esp+520]
    mov eax, [ebx+0x18]
    fld dword ptr [edx+0x38]
    fsub dword ptr [eax+0x38]
    fstp dword ptr [esp+516]
    fld dword ptr [edx+0x30]
    fsub dword ptr [eax+0x30]
    fstp dword ptr [esp+524]
    push dword ptr [esp+516] /* z */
    push dword ptr [esp+528] /* x, prior push moved local offset */
    call bearing
    mov [esp+524], eax
    mov ecx, ebx
    call effective_facing
    mov edx, [ebx+0x10]
    test byte ptr [edx+0x28], 2
    jz reference_ready
    mov eax, [edx+0x10]
reference_ready:
    mov ecx, [esp+524]
    sub cx, ax
    movsx ecx, cx
    mov [esp+528], eax
    mov eax, ecx
    cdq
    xor eax, edx
    sub eax, edx
    cmp eax, 910 /* 5 degrees: stop correction */
    ja outside_inner
    and byte ptr [edi+20], -9
    jmp cap
outside_inner:
    test byte ptr [edi+20], 8
    jnz turn
    cmp eax, 1820 /* 10 degrees: begin correction */
    jb cap
    or byte ptr [edi+20], 8
turn:
    fld dword ptr [0xb71d0c]
    fmul dword ptr [config+24] /* 180 degrees/s */
    fistp dword ptr [esp+532]
    mov eax, [esp+532]
    cmp ecx, eax
    jle lower_turn
    mov ecx, eax
lower_turn:
    neg eax
    cmp ecx, eax
    jge apply_turn
    mov ecx, eax
apply_turn:
    add [esp+528], ecx
cap:
    mov edx, [ebx+0x10]
    mov eax, [esp+528]
    and eax, 0xffff
    mov [edx+0x10], eax
    or dword ptr [edx+0x28], 2
    and dword ptr [esi+0x584], 0xfffbffff /* clear inherited fast latch, CPU zone only */
    mov edx, [ebx+0xc]
    mov eax, [config+20]
    cmp [edx+0x10], eax
    jbe tick_done
    mov [edx+0x10], eax
    jmp tick_done
planner_cap:
    /* EBP is the saved PUSHAD base; original arg3 is EBP+48.
     * Cap BEFORE retail 1A4170 chooses the fast-latch branch. This retains
     * the real local aiming vector, interception and avoidance steering. */
    mov eax, [ebp+48]
    test eax, eax
    js end_policy
    cmp eax, 0x3f800000
    ja end_policy
    cmp eax, [config+20]
    jbe planner_clear
    mov eax, [config+20]
    mov [ebp+48], eax
planner_clear:
    and dword ptr [esi+0x584], 0xfffbffff
    jmp tick_done
pass_event:
    mov ecx, [edi+12]
    cmp [eax+0x1c8], ecx
    jne end_policy
    /* Retain a distinct diagnostic reason for a pass from the armed QB. */
    mov byte ptr [edi+20], 0x12
    jmp tick_done
bail_release:
    /* Restore the pre-cap native task throttle when this short tier ends.
     * An installed initial-drop cap stays authoritative (.84 in its receipt). */
    mov eax, [edi+16]
    mov edx, [esi+0x310]
    mov [edx+0x34], eax
end_policy:
    mov byte ptr [edi+20], 2
    jmp tick_done
retire_identity:
    /* Invalid mode/index/role cannot temporarily hide an armed record. */
    mov edi, offset state_data
    mov ecx, 11
retire_next:
    cmp [edi], ebx
    jne retire_skip
    mov byte ptr [edi+20], 2
retire_skip:
    add edi, 21
    dec ecx
    jnz retire_next
    jmp tick_done
tick_done:
    cmp dword ptr [esp+536], 0
    jne planner_done
    RESTORE
    jmp native_rows
planner_done:
    RESTORE
    push ebp
    mov ebp, esp
    and esp, -16
    jmp native_planner_tail

/* EBX=P -> ESI=S, EDI=our record, EAX=1 iff exact live defensive CB/deep record.
 * Never dereference an arbitrary index or steal an unreserved address. */
eligible:
    xor eax, eax
    cmp byte ptr [ebx+0x2c], 18
    jne eligible_done
    cmp dword ptr [ebx+0x1c], 1
    jne eligible_done
    mov edx, [0xe60284]
    test edx, edx
    jz eligible_done
    cmp [ebx+0x38], edx
    jne eligible_done
    mov esi, [ebx+0x20]
    test esi, esi
    jz eligible_done
    mov edx, [esi+0x310]
    test edx, edx
    jz eligible_done
    mov ecx, [edx+0xa4]
    cmp ecx, 11
    jae eligible_done
    mov edx, [0xbe4d40]
    and edx, 0x3ff
    cmp edx, 11
    ja eligible_done
    cmp ecx, edx
    jae eligible_done
    mov edx, ecx
    shl edx, 4
    cmp [edx+0xbe4b60], ebx
    jne eligible_done
    mov dl, [edx+0xbe4b6c]
    and dl, 12
    cmp dl, 8
    jne eligible_done
    imul edi, ecx, 21
    add edi, offset state_data
    inc eax
eligible_done:
    ret
/* Sign must be exactly +1 or -1, stored in the wrapper's scratch slot. */
direction:
    xor eax, eax
    mov edx, [0xe60280]
    test edx, edx
    jz direction_done
    mov edx, [edx+8]
    test edx, edx
    jz direction_done
    mov edx, [edx+12]
    test edx, edx
    jz direction_done
    mov edx, [edx+4]
    mov ecx, edx
    and ecx, 0x7fffffff
    cmp ecx, 0x3f800000
    jne direction_done
    mov [esp+516], edx /* helper return occupies four bytes */
    inc eax
direction_done:
    ret
finite_xz:
    xor eax, eax
    test edx, edx
    jz finite_done
    mov ecx, [edx+0x30]
    and ecx, 0x7fffffff
    cmp ecx, 0x49742400
    jae finite_done
    mov ecx, [edx+0x38]
    and ecx, 0x7fffffff
    cmp ecx, 0x49742400
    jae finite_done
    inc eax
finite_done:
    ret
.balign 4, 0xcc
config:
    .long 1, 1 /* default apply is both tiers; all product presets stay off */
    .float 182.88, 640.08, 91.44, 0.84, 32768
code_end:
