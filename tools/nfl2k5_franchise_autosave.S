/* Optional native Franchise save. EXPERIMENTAL / UNWITNESSED.
 * No container writer. Native serializer 16E3F0, overwrite preflight 16BE80,
 * transaction/signing 16C2F0 and its progress/error dialogs remain in charge.
 * RW: enabled 0, pending 4, active 8, valid slot 12, device 16, quiet tick 20,
 * save successes 24, attempted slot 28, UTF-16 slot name 32..65.
 */
.intel_syntax noprefix
.code32
.text
.extern state, strings
.extern desk_native, mark_played_native, mark_sim_native, copy_settings_native
.extern camera_size_native, league_native, mode_nonzero, mode_zero, load_continue
.extern dialog_native, notice_native, init_devices_native, select_device_native
.extern save_native, close_devices_native
.extern allocate_native

.global toggle, getter, value_text, played, simulated, desk
.global serialize, load_settings, load_slot, load_begin, mode_change
.global overwrite_dialog, success_dialog
.global allocate

toggle:
 xor dword ptr [state], 1
 mov dword ptr [state+4], 0
 mov dword ptr [state+20], 0
 mov eax, 1
 ret
getter:
 mov eax, dword ptr [state]
 ret
value_text:
 mov eax, dword ptr [state]
 and eax, 1
 mov eax, dword ptr [eax*4+0x4ed994]
 ret
/* Preserve all effects of each original callee, including flags. */
played:
 call mark_played_native
 pushfd
 pushad
 call mark
 popad
 popfd
 ret
simulated:
 call mark_sim_native
 pushfd
 pushad
 call mark
 popad
 popfd
 ret
mark:
 cmp dword ptr [0xe576a0], 2 /* native Franchise; 1 is Tournament */
 jne mark_done
 cmp dword ptr [state], 1
 jne mark_done
 mov dword ptr [state+4], 1
 mov dword ptr [state+20], 0
mark_done:
 ret

/* Retail silently returns on allocation failure after overwrite preflight.
 * Keep manual behavior; auto attempts report through the native notice UI. */
allocate:
 call allocate_native
 pushfd
 pushad
 test eax, eax
 jnz allocate_done
 cmp dword ptr [state+8], 1
 jne allocate_done
 mov ecx, dword ptr [0xbdbda4]
 mov edx, offset strings+384
 call notice_native
allocate_done:
 popad
 popfd
 ret

/* Only the on-disk Franchise serializer call is wrapped. Temporary native
 * settings snapshots and every FPF consumer retain the original live flag. */
serialize:
 push ecx
 call copy_settings_native
 pushfd
 pushad
 cmp dword ptr [0xe576a0], 2
 jne serialize_done
 mov edx, dword ptr [esp+36]
 mov eax, dword ptr [state]
 mov dword ptr [edx+0x64], eax
serialize_done:
 popad
 popfd
 lea esp, [esp+4]
 ret

/* This caller has completed its settings copy, including the camera owner.
 * Restore the reused disk word to our RW toggle, then remove it from FPF. */
load_settings:
 pushfd
 pushad
 cmp dword ptr [ebp+0xbdc1d4], 9
 jne load_settings_done
 xor eax, eax
 cmp dword ptr [0xe5ffe4], 1
 sete al
 mov dword ptr [state], eax
 mov dword ptr [0xe5ffe4], 0
load_settings_done:
 popad
 popfd
 jmp camera_size_native

/* A new load attempt invalidates the old slot even if that load fails. */
load_begin:
 mov dword ptr [state+4], 0
 mov dword ptr [state+12], 0
 mov dword ptr [state+20], 0
 sub esp, 0x14
 mov eax, dword ptr [0xbdbdb8]
 jmp load_continue

/* Reached after season AND front-office deserializers return. EBP is the
 * selected metadata byte offset, not a screen index. */
load_slot:
 pushfd
 pushad
 cmp dword ptr [ebp+0xbdc1d4], 9
 jne load_slot_done
 mov ecx, dword ptr [ebp+0xbdc1d0]
 call remember
load_slot_done:
 mov dword ptr [state+4], 0
 mov dword ptr [state+20], 0
 popad
 popfd
 jmp league_native

/* Every explicit native league selection ends the previous slot lease.
 * Native load writes its deserialized league directly and then captures anew. */
mode_change:
 mov dword ptr [state+4], 0
 mov dword ptr [state+12], 0
 mov dword ptr [state+20], 0
 cmp ecx, 2
 jne mode_replay
 mov dword ptr [0xe5ffe4], 0
mode_replay:
 mov eax, ecx
 test eax, eax
 jnz mode_nonzero
 jmp mode_zero

/* ECX = successful native slot name; invoked only within pushad. Names are
 * at most 16 UTF-16 code units in the native naming UI. No truncation. */
remember:
 mov dword ptr [state+12], 0
 test ecx, ecx
 jz remember_done
 cmp word ptr [ecx], 0
 je remember_done
 xor edx, edx
remember_scan:
 cmp word ptr [ecx+edx*2], 0
 je remember_copy
 inc edx
 cmp edx, 17
 jb remember_scan
 ret
remember_copy:
 mov esi, ecx
 mov edi, offset state+32
 inc edx
 mov ecx, edx
 cld
 rep movsw
 mov eax, dword ptr [0xbdbdb8]
 cmp eax, 9
 jae remember_done
 imul eax, eax, 0x34
 mov edx, dword ptr [0xbdbdbc]
 test edx, edx
 jz remember_done
 mov eax, dword ptr [edx+eax]
 test eax, eax
 jz remember_done
 mov dword ptr [state+16], eax
 mov dword ptr [state+12], 1
remember_done:
 ret

/* Exact overwrite-confirmation call, never a global dialog bypass. */
overwrite_dialog:
 cmp dword ptr [state+8], 1
 jne ordinary_dialog
 mov eax, 2
 ret 24
ordinary_dialog:
 jmp dialog_native

/* This call can only be reached after the native write, close, enumeration
 * and same-name/type/size readback checks succeed. EBP is native save frame. */
success_dialog:
 pushfd
 pushad
 cmp dword ptr [ebp+8], 9
 jne success_not_franchise
 mov ecx, dword ptr [ebp+12]
 call remember
 mov dword ptr [state+4], 0
 inc dword ptr [state+24]
success_not_franchise:
 popad
 popfd
 cmp dword ptr [state+8], 1
 jne ordinary_dialog
 xor eax, eax
 ret 24

/* Call the real Desk update first. A second quiet topmost Desk tick ensures
 * resume, scene restoration and transition work have completed. */
desk:
 push ecx
 call desk_native
 pushfd
 pushad
 mov ebp, dword ptr [esp+36]
 cmp dword ptr [state+8], 0
 jne desk_done
 cmp dword ptr [state], 1
 jne desk_cancel
 cmp dword ptr [0xe576a0], 2
 jne desk_cancel
 mov eax, dword ptr [ebp+0x100]
 cmp eax, 32
 jae desk_wait
 cmp dword ptr [ebp+eax*8], 0x522190
 jne desk_wait
 cmp dword ptr [0xa83a10], 0 /* game scene still alive */
 jne desk_wait
 cmp dword ptr [0xaa2408], 0 /* pending Desk destination */
 jne desk_wait
 mov edx, dword ptr [0xaa2140]
 test edx, edx
 jz desk_wait
 mov eax, dword ptr [edx+4] /* native nonnegative scene time */
 cmp eax, 0x7f800000
 jae desk_wait
 cmp eax, dword ptr [0xaa2400] /* return animation target */
 jb desk_wait
 cmp dword ptr [0xbdbdb0], 1 /* native I/O controller is idle */
 jne desk_wait
 mov eax, dword ptr [0xbdbda0]
 test eax, eax
 jz desk_state_ok
 cmp eax, 7
 je desk_state_ok
 cmp eax, 8
 jne desk_wait
desk_state_ok:
 cmp dword ptr [state+4], 0
 je desk_done
 cmp dword ptr [state+20], 0
 jne desk_attempt
 mov dword ptr [state+20], 1
 jmp desk_done
desk_wait:
 mov dword ptr [state+20], 0
 jmp desk_done
desk_cancel:
 mov dword ptr [state+4], 0
 jmp desk_wait
desk_attempt:
 mov dword ptr [state+4], 0
 mov dword ptr [state+20], 0
 mov dword ptr [state+8], 1
 cmp dword ptr [state+12], 1
 jne missing_slot
 /* Native discovery owns the device table and title-session lifetime. */
 push dword ptr [0xbdbda4]
 mov dword ptr [0xbdbda4], ebp
 cmp dword ptr [0xbdbdbc], 0
 je missing_device
 call init_devices_native
 xor edi, edi
 mov esi, dword ptr [0xbdbdbc]
 test esi, esi
 jz missing_device
device_loop:
 mov eax, dword ptr [state+16]
 cmp dword ptr [esi], eax
 je device_found
 add esi, 0x34
 inc edi
 cmp edi, 9
 jb device_loop
 jmp missing_device
device_found:
 push edi
 call select_device_native
 cmp dword ptr [esi+8], 0
 je missing_device
 mov ebx, dword ptr [esi+0x1c]
 cmp ebx, 256
 ja missing_device
 xor edi, edi
slot_loop:
 cmp edi, ebx
 jae missing_device
 imul eax, edi, 24
 cmp dword ptr [eax+0xbdc1d4], 9
 jne next_slot
 mov edx, dword ptr [eax+0xbdc1d0]
 test edx, edx
 jz next_slot
 xor ecx, ecx
name_loop:
 mov ax, word ptr [state+32+ecx*2]
 cmp ax, word ptr [edx+ecx*2]
 jne next_slot
 test ax, ax
 jz save_slot
 inc ecx
 cmp ecx, 17
 jb name_loop
next_slot:
 inc edi
 jmp slot_loop
save_slot:
 mov dword ptr [state+28], edi
 mov ecx, edi
 call save_native
 jmp close_device
missing_device:
 mov ecx, ebp
 mov edx, offset strings+256
 call notice_native
close_device:
 call close_devices_native
 pop dword ptr [0xbdbda4]
 jmp attempt_done
missing_slot:
 mov ecx, ebp
 mov edx, offset strings+128
 call notice_native
attempt_done:
 mov dword ptr [state+8], 0
desk_done:
 popad
 popfd
 lea esp, [esp+4]
 ret
