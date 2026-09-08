/* EXPERIMENTAL / UNWITNESSED. GNU as --32.
 * ECX = actor, no stack arguments, EAX = callback result.
 * All added work preserves flags, general registers and complete x87/SSE state.
 * State: 0x40 header (snap QB, snap x, reserved), 22 records of 0x20 bytes:
 * actor, player state, assignment, QB, baseline x, mode, roster, reserved.
 * mode: 0 free, 1 shadow, 2 pursuit (latched), 3 ended until assignment reset.
 */
.intel_syntax noprefix
.code32
.text
.global zone_first, zone_later, reset_assignment, reset_command, snap, config, code_end
.extern state_data, intent_table
.extern resume_first, resume_later, resume_assignment, resume_command, resume_snap
.extern steer, pursue, transition
.extern init_rush_native, init_lane_native, init_man_native
.extern resume_rush, resume_delay, resume_lane, resume_man, resume_press, resume_release, resume_exchange

zone_first:
    push offset first_original
    jmp dispatch
zone_later:
    push offset later_original
dispatch:
    push ebp
    mov ebp, esp
    lea esp, [esp-48] /* save incoming flags before any arithmetic */
    pushfd
    pushad
    and esp, -16
    sub esp, 512
    fxsave [esp]
    fninit
    mov ebx, ecx
    mov dword ptr [ebp-4], 0 /* handled */
    mov esi, [ebx+0x20]
    mov dword ptr [ebp-36], 0
    test esi, esi
    jz finish
    /* Man/rush keeps native callback identities for peer exchange comparisons.
     * Borrow its target fields only during the spy movement call. On fallback
     * its native receiver/blocker targets must still be valid. */
    cmp dword ptr [ebp+4], offset ext_originals
    jb targets_saved
    mov eax, [esi+0x310]
    test eax, eax
    jz finish
    mov [ebp-36], eax
    mov edx, [eax]
    mov [ebp-40], edx
    mov edx, [eax+0x40]
    mov [ebp-44], edx
    mov edx, [eax+0x48]
    mov [ebp-48], edx
targets_saved:
    mov edi, offset state_data+0x40
    xor edx, edx
    mov ecx, 22
find_record:
    cmp [edi], ebx
    je found
    cmp dword ptr [edi], 0
    jne occupied
    mov edx, edi
occupied:
    add edi, 32
    loop find_record
    mov edi, edx
    test edi, edi
    jz finish /* all 22 in use: ordinary coverage */
found:
    mov eax, [esi+0x41c]
    cmp [edi+4], esi
    jne fresh
    cmp [edi+8], eax
    jne fresh
    mov ecx, [ebx+0x3c]
    cmp [edi+24], ecx
    je identity_ok
fresh:
    mov [edi], ebx
    mov [edi+4], esi
    mov [edi+8], eax
    mov eax, [ebx+0x3c]
    mov [edi+24], eax
    mov dword ptr [edi+20], 0
identity_ok:
    cmp dword ptr [edi+20], 3
    je finish
    test dword ptr [esi+0x420], 0x20000000
    jnz requested
    call lookup_intent
    test eax, eax
    jz end_spy
requested:
    cmp dword ptr [0xe602b8], 14
    jne end_spy
    mov eax, [ebx+0x38]
    cmp eax, [0xe60284]
    jne end_spy
    /* Explicit user takeover: same controller/player-lock guards as kickoff. */
    mov eax, [ebx+0xc]
    test eax, eax
    jz end_spy
    cmp dword ptr [eax], -1
    jne end_spy
    test byte ptr [esi+0x584], 0x20
    jnz end_spy
    mov eax, [0xe602ec]
    test eax, eax
    jz end_spy
    mov ecx, [eax+0x18]
    and ecx, 0x7fffffff
    cmp ecx, 0x49742400
    jae end_spy
    cmp dword ptr [eax+0x1c4], 0
    jne end_spy
    cmp dword ptr [eax+0x1c8], 0
    jne end_spy
    mov eax, [0xe5fc00]
    test eax, eax
    jz end_spy
    mov edx, [eax] /* owner, NOT the ball object's type field */
    test edx, edx
    jz end_spy
    cmp dword ptr [edx+0x1c], 1
    jne end_spy /* flight or free ball */
    cmp edx, [0xbe4f8c]
    jne carrier_exit
    mov eax, [edx+0x3c]
    test eax, eax
    jz end_spy
    cmp byte ptr [eax+0x35], 0
    jne end_spy /* cache fallback to another role is not a QB */
    mov eax, [edx+0x38]
    cmp eax, [0xe60280]
    jne carrier_exit
    mov eax, [edx+0x18]
    test eax, eax
    jz end_spy
    /* Bounded finite coordinates/speeds before any x87 comparisons. */
    push edx
    lea ecx, [eax+0x30]
    mov edx, 8
finite_loop:
    mov eax, [ecx]
    and eax, 0x7fffffff
    cmp eax, 0x49742400 /* abs < 1,000,000 cm */
    jae nonfinite
    add ecx, 4
    dec edx
    jnz finite_loop
    pop edx
    mov eax, [edx+0x18]
    cmp dword ptr [edi+20], 0
    jne retained
    cmp edx, [state_data]
    jne end_spy
    mov [edi+12], edx
    mov ecx, [state_data+4]
    mov [edi+16], ecx
    mov dword ptr [edi+20], 1
retained:
    cmp [edi+12], edx
    jne carrier_exit
    mov [ebp-8], edx
    /* Native signed field direction, +1/-1, and line coordinate. */
    mov ecx, [0xe60280]
    mov ecx, [ecx+8]
    mov ecx, [ecx+0xc]
    mov eax, [ecx+4]
    and eax, 0x7fffffff
    cmp eax, 0x7f800000
    jae end_spy
    fld dword ptr [ecx+4]
    ftst
    fnstsw ax
    fstp st(0)
    mov dword ptr [ebp-12], 1
    test ah, 0x41
    jz direction_ok
    mov dword ptr [ebp-12], -1
direction_ok:
    mov eax, [edx+0x18]
    cmp dword ptr [edi+20], 2
    je chase
    fld dword ptr [eax+0x30]
    fsub dword ptr [edi+16]
    fabs
    fcomp dword ptr [config+8]
    fnstsw ax
    test ah, 0x45
    jz latch /* strictly more than 3 yards */
    mov eax, [edx+0x18]
    fld dword ptr [eax+0x38]
    mov ecx, [0xe602ec]
    fsub dword ptr [ecx+0x18]
    fild dword ptr [ebp-12]
    fmulp st(1), st
    fcomp dword ptr [config+4]
    fnstsw ax
    test ah, 0x5
    jnz shadow /* >= -1 yard */
    mov eax, [edx+0x18]
    fld dword ptr [eax+0x48]
    fild dword ptr [ebp-12]
    fmulp st(1), st
    ftst
    fnstsw ax
    fstp st(0)
    test ah, 0x45
    jnz shadow
latch:
    mov dword ptr [edi+20], 2
chase:
    mov eax, [edx+0x18]
    mov ecx, [eax+0x30]
    mov [ebp-32], ecx
    mov ecx, [eax+0x38]
    mov [ebp-24], ecx
    jmp goal_ready
shadow:
    mov eax, [edx+0x18]
    fld dword ptr [eax+0x40]
    fmul dword ptr [config+12]
    fadd dword ptr [eax+0x30]
    /* Stay within retail field width. */
    fld dword ptr [config+16]
    fcomi st, st(1)
    fcmovnbe st, st(1)
    fstp st(1)
    fld dword ptr [config+20]
    fcomi st, st(1)
    fcmovb st, st(1)
    fstp st(1)
    fstp dword ptr [ebp-32]
    fild dword ptr [ebp-12]
    fmul dword ptr [config]
    mov ecx, [0xe602ec]
    fadd dword ptr [ecx+0x18]
    fstp dword ptr [ebp-24]
goal_ready:
    mov eax, [esi+0x310]
    mov [eax+0x40], edx
    mov dword ptr [eax+0x48], 0
    mov dword ptr [ebp-28], 0
    mov dword ptr [ebp-20], 0
    mov ecx, ebx
    lea edx, [ebp-32]
    cmp dword ptr [edi+20], 2
    je move_pursuit
    push 0
    push 0x3f800000
    push 0
    push edx
    xor edx, edx
    call steer /* native ret 16 */
    jmp handled
move_pursuit:
    push 0
    push 0x3f19999a
    push 0
    push 0x3eb851ec
    push 0x3f747ae1
    push 0
    push 1
    xor eax, eax
    cmp dword ptr [ebp-12], 1
    jne pursuit_heading
    mov eax, 0x8000 /* defender faces opposite offense */
pursuit_heading:
    push eax
    call pursue /* native ret 32, callback remains zone for lifecycle check */
handled:
    mov dword ptr [ebp-4], 1
    jmp finish
nonfinite:
    pop edx
    jmp end_spy
carrier_exit:
    cmp dword ptr [edi+20], 0
    je finish
    call retire
    mov edx, ebx
    mov ecx, 0x2eb330
    call transition /* native ball-carrier pursuit initializer */
    jmp handled
end_spy:
    cmp dword ptr [edi+20], 0
    je finish
    call retire
finish:
    mov eax, [ebp-36]
    test eax, eax
    jz targets_restored
    cmp [esi+0x310], eax
    jne targets_restored
    mov edx, [ebp-40]
    cmp [eax], edx
    jne targets_restored /* a native transition owns the new state */
    mov edx, [ebp-44]
    mov [eax+0x40], edx
    mov edx, [ebp-48]
    mov [eax+0x48], edx
targets_restored:
    fxrstor [esp]
    cmp dword ptr [ebp-4], 0
    lea esp, [ebp-84]
    popad
    jne return_spy
    popfd
    mov esp, ebp
    pop ebp
    ret /* returns to displaced prologue on the original stack */
return_spy:
    popfd
    mov esp, ebp
    pop ebp
    lea esp, [esp+4]
    xor eax, eax
    ret
retire:
    mov dword ptr [edi+20], 3
    and dword ptr [esi+0x420], 0xdfffffff
    mov eax, [esi+0x310]
    mov dword ptr [eax+0x40], 0
    mov dword ptr [eax+0x48], 0
    ret
first_original:
    push ebp
    mov ebp, esp
    and esp, -16
    jmp resume_first
later_original:
    push ebp
    mov ebp, esp
    and esp, -16
    jmp resume_later

/* Exact identity only in the two bounded native relocated PLAY buffers.
 * Lookup result EAX, all other registers unchanged. No arbitrary dereference.
 */
lookup_intent:
    pushad
    mov edi, [esi+0x41c]
    mov ebx, 0xb75a40
    mov eax, edi
    sub eax, ebx
    cmp eax, 0x13390
    jb buffer_found
    add ebx, 0x13390
    mov eax, edi
    sub eax, ebx
    cmp eax, 0x13390
    jae lookup_no
buffer_found:
    sub eax, 0x3404
    cmp eax, 270*96-8
    jae lookup_no
    xor edx, edx
    mov ecx, 96
    div ecx
    test edx, 7
    jnz lookup_no
    shr edx, 3
    cmp edx, 11
    jae lookup_no
    shl edx, 16
    or eax, edx
    or eax, 0x01000000
    mov [ebp-16], eax /* packed play/slot/version */
    mov esi, [ebx+0x30]
    call name_hash
    jc lookup_no
    mov [ebp-8], eax
    mov eax, [ebp-16]
    movzx eax, ax
    imul eax, 96
    mov esi, [ebx+eax+0x33fc]
    call name_hash
    jc lookup_no
    mov [ebp-12], eax
    /* FNV descriptor + exact two encoded nodes. */
    /* Descriptor has other bits: test low nibble separately. */
    mov eax, [edi]
    and eax, 15
    cmp eax, 2
    jne lookup_no
    mov esi, edi
    mov ecx, 4
    mov eax, 0x811c9dc5
    call hash_bytes
    mov esi, [edi+4]
    mov edx, esi
    sub edx, ebx
    sub edx, 0x9adc
    cmp edx, 3500*8-16
    ja lookup_no
    mov ecx, 16
    call hash_bytes
    mov esi, offset intent_table+16
    mov ecx, [intent_table+8]
lookup_row:
    test ecx, ecx
    jz lookup_no
    cmp [esi+8], eax
    jne next_row
    mov edx, [ebp-16]
    cmp [esi+4], edx
    jne next_row
    mov edx, [ebp-8]
    cmp [esi], edx
    jne next_row
    mov edx, [ebp-12]
    cmp [esi+12], edx
    je lookup_yes
next_row:
    add esi, 16
    loop lookup_row
lookup_no:
    popad
    xor eax, eax
    ret
lookup_yes:
    popad
    mov eax, 1
    ret
name_hash:
    mov edx, esi
    sub edx, ebx
    cmp edx, 0x10840
    jb name_bad
    cmp edx, 0x13390-128
    ja name_bad
    mov eax, 0x811c9dc5
    mov ecx, 64
name_loop:
    cmp word ptr [esi], 0
    je name_done
    push ecx
    mov ecx, 2
    call hash_bytes
    pop ecx
    loop name_loop
name_bad:
    stc
    ret
name_done:
    clc
    ret
hash_bytes:
    movzx edx, byte ptr [esi]
    xor eax, edx
    imul eax, eax, 0x01000193
    inc esi
    loop hash_bytes
    ret

/* The actual 13 -> 14 phase store marks the snap. Clear all per-play slots
 * and retain the cached QB and his lateral coordinate before further ticks.
 * Preserve CMP flags used by the retail branch after the displaced MOV. */
snap:
    pushfd
    pushad
    cld
    mov edi, offset state_data
    xor eax, eax
    mov ecx, 768/4
    rep stosd
    mov eax, [0xbe4f8c]
    test eax, eax
    jz snap_done
    mov edx, [eax+0x18]
    test edx, edx
    jz snap_done
    mov edx, [edx+0x30]
    mov ecx, edx
    and ecx, 0x7fffffff
    cmp ecx, 0x49742400
    jae snap_done
    mov [state_data], eax
    mov [state_data+4], edx
snap_done:
    popad
    popfd
    mov dword ptr [0xe602b8], 14
    jmp resume_snap

/* Retail state reset clears a slot before replaying all 7 displaced bytes. */
reset_assignment:
    pushfd
    pushad
    mov edx, ecx
    sub edx, 0x41c
    call clear_state
    popad
    popfd
    xor eax, eax
    cmp edx, eax
    mov [ecx+4], eax
    jmp resume_assignment
reset_command:
    pushfd
    pushad
    mov edx, [ecx+0x20]
    and dword ptr [edx+0x420], 0xdfffffff
    call clear_state
    popad
    popfd
    movsx eax, byte ptr [ecx+0x2e]
    mov ebx, [esi+0xc]
    jmp resume_command
clear_state:
    mov edi, offset state_data+0x40
    mov ecx, 22
clear_loop:
    cmp [edi+4], edx
    jne clear_next
    mov dword ptr [edi], 0
    mov dword ptr [edi+4], 0
    mov dword ptr [edi+20], 0
clear_next:
    add edi, 32
    loop clear_loop
    ret

/* Dispatch-table wrappers. ECX actor, no stack arguments, native return ABI.
 * Execute each original initializer once, including its early transition.
 * Clear the old per-assignment latch AFTER initialization, preserving its
 * return registers, flags and FP state. Never replace a man/rush initializer
 * with a zone initializer or overwrite its chosen callback. */
init_rush:
    push offset init_rush_native
    jmp initialize
init_lane:
    push offset init_lane_native
    jmp initialize
init_man:
    push offset init_man_native
initialize:
    push ecx
    call dword ptr [esp+4]
    pushfd
    pushad
    mov eax, [esp+36]
    mov edx, [eax+0x20]
    call clear_state
    popad
    popfd
    lea esp, [esp+8]
    ret

/* Intercept each supported native callback entry, including internal tail
 * calls and peer rewrites. Pointer equality in man exchange stays retail.
 * The exact same dispatcher, intent table and snap records serve every path. */
.macro extension name
\name:
    push offset \name\()_original
    jmp dispatch
.endm
extension rush_main
extension rush_delay
extension rush_lane
extension man_main
extension man_press
extension man_release
extension man_exchange

ext_originals:
rush_main_original:
    push ebp
    mov ebp, esp
    and esp, -16
    jmp resume_rush
rush_delay_original:
    push esi
    mov esi, ecx
    mov eax, [esi+0x20]
    jmp resume_delay
rush_lane_original:
    sub esp, 0x18
    push ebx
    push ebp
    jmp resume_lane
man_main_original:
    push ebp
    mov ebp, esp
    and esp, -16
    jmp resume_man
man_press_original:
    mov eax, [ecx+0x20]
    mov edx, [eax+0x310]
    jmp resume_press
man_release_original:
    mov eax, [ecx+0x10]
    mov eax, [eax+4]
    jmp resume_release
man_exchange_original:
    push ebp
    mov ebp, esp
    and esp, -16
    jmp resume_exchange
.balign 4, 0xcc
config:
    .float 365.76, -91.44, 274.32, 0.5, 2164.08, -2164.08
code_end:
