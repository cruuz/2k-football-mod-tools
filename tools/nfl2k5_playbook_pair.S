/* All wrappers preserve the displaced ABI. No writable data in RX. */
.intel_syntax noprefix
.text
.global begin, queue, bind, cleanup, load_mode, vip
.extern state
begin:
    pushfd
    pushad
    cld
    call pair_begin
    popad
    popfd
    mov eax, [0xe60184]
    jmp begin_continue
queue:
    pushfd
    pushad
    cld
    call pair_queue
    popad
    popfd
    cmp dword ptr [0xe5ff80], 3
    jmp queue_continue
bind:
    pushfd
    pushad
    cld
    call pair_bind
    popad
    popfd
    sub esp, 8
    push esi
    call home_team_native
    jmp bind_continue
cleanup:
    pushfd
    pushad
    cld
    call pair_cleanup
    popad
    popfd
    mov ecx, 0xe61638
    jmp cleanup_continue
/* Stock matches normally recycle User A/B buffers. During this load phase
 * every PLAY uses the retail heap branch, independent of completion order.
 * The retail resource destructor frees these bodies; composites have their
 * own explicit free. User A/B sources are refused before entering this phase.
 */
load_mode:
    cmp dword ptr [state], 0
    je native_mode
    xor eax, eax
    ret
native_mode:
    jmp mode_native
/* Profile play numbers refer to the original book. Returning the retail
 * no-profile result avoids both replaying and recording mismatched indices.
 * Other sides, and all games with Same as offense, keep the native path.
 */
vip:
    pushfd
    cmp ecx, 0xe5fc20
    jne away_vip
    cmp dword ptr [state+28], 0
    jmp check_vip
away_vip:
    cmp dword ptr [state+92], 0
check_vip:
    jne no_vip
    popfd
    cmp ecx, 0xe5fc20
    jmp vip_continue
no_vip:
    popfd
    xor eax, eax
    ret
.section .note.GNU-stack,"",@progbits
