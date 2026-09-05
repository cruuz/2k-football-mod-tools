/* Original i386 callbacks. EXPERIMENTAL / UNWITNESSED.
 * Page bindings retain the native fastcall signatures, getter/activation ret 4.
 * Private state: captured team, manager, popup busy. Everything else is stack/UI heap.
 */
.intel_syntax noprefix
.code32
.text
.global row, enter, leave, context, selector, title, one
.global active_count, reserve_count, active_get, reserve_get, activate, code_end

/* EAX=validated current team, EDX=league selector; zero on refusal.
 * Never substitute the first human coach for the selected franchise context.
 */
context:
 push ebx
 push esi
 push edi
 cmp DWORD PTR [0xe576a0], 1
 jne context_bad
 mov ebx, DWORD PTR [0xb72918]
 test ebx, ebx
 jz context_bad
 mov ecx, DWORD PTR [ebx+0x18]
 dec ecx
 cmp ecx, 127
 ja context_bad
 mov esi, DWORD PTR [0xe3c0a0]
 test esi, esi
 jz context_bad
 mov edi, DWORD PTR [ebx+0x1c]
 test edi, edi
 jz context_bad
 mov eax, esi
 sub eax, edi
 jc context_bad
 xor edx, edx
 mov ecx, 500
 div ecx
 test edx, edx
 jnz context_bad
 cmp eax, DWORD PTR [ebx+0x18]
 jae context_bad
 cmp eax, 32
 jae context_bad
 mov eax, DWORD PTR [ebx]
 dec eax
 cmp eax, 4095
 ja context_bad
 cmp DWORD PTR [ebx+4], 0
 je context_bad
 cmp DWORD PTR [ebx+0x38], 4096
 ja context_bad
 cmp DWORD PTR [ebx+0x38], 0
 je context_league
 cmp DWORD PTR [ebx+0x3c], 0
 je context_bad
context_league:
 xor edi, edi
context_find:
 cmp esi, DWORD PTR [0xe5786c+edi*4]
 je context_found
 inc edi
 cmp edi, 34
 jb context_find
 jmp context_bad
context_found:
 cmp DWORD PTR [0xe5775c+edi*4], 0
 je context_bad
 mov eax, esi
 call ps_reserve_count
 test eax, eax
 js context_bad
 mov eax, esi
 mov edx, edi
 jmp context_done
context_bad:
 xor eax, eax
context_done:
 pop edi
 pop esi
 pop ebx
 ret

/* Captured identity is required once the screen is open. */
current:
 call context
 test eax, eax
 jz current_done
 cmp eax, DWORD PTR [state_data]
 je current_done
 xor eax, eax
current_done:
 ret
selector:
 call current
 test eax, eax
 jz selector_bad
 mov eax, edx
 ret
selector_bad:
 mov eax, -1
 ret
title:
 call current
 test eax, eax
 jz title_bad
 mov eax, DWORD PTR [eax+0x104]
 test eax, eax
 jnz title_done
title_bad:
 mov eax, OFFSET invalid_text
title_done:
 ret
one:
 mov eax, 1
 ret

row:
 push ecx
 call context
 test eax, eax
 jz row_bad
 push 0x41700000
 push 0x41500000
 call fade
 mov DWORD PTR [0xaa2408], OFFSET descriptor
 pop ecx
 ret
row_bad:
 pop ecx
 mov edx, OFFSET invalid_text
 jmp message
enter:
 push ecx
 call leave
 call context
 mov DWORD PTR [state_data], eax
 pop ecx
 mov DWORD PTR [state_data+4], ecx
 ret
leave:
 mov DWORD PTR [state_data], 0
 mov DWORD PTR [state_data+4], 0
 mov DWORD PTR [state_data+8], 0
 ret

/* EAX=player, ESI=team. Validate primary identity and exclusive ownership.
 * Scan bounded root teams, including reserve tails. Retail all-star active
 * aliases are excluded exactly as in ps.listed; reserves are never aliases.
 */
owned:
 push ebx
 push ecx
 push edx
 push edi
 push ebp
 mov ebp, eax
 test eax, eax
 jz owned_bad
 mov ebx, DWORD PTR [0xb72918]
 sub eax, DWORD PTR [ebx+4]
 jc owned_bad
 xor edx, edx
 mov ecx, 84
 div ecx
 test edx, edx
 jnz owned_bad
 cmp eax, DWORD PTR [ebx]
 jae owned_bad
 xor edi, edi
 xor ecx, ecx
 mov edx, DWORD PTR [ebx+0x1c]
owned_team:
 push ecx
 push edx
 mov eax, edx
 call ps_reserve_count
 pop edx
 pop ecx
 test eax, eax
 js owned_bad
 push ecx
 push edx
 movzx ecx, BYTE PTR [edx+0x11c]
 add eax, ecx
 mov ecx, DWORD PTR [esp+4]
 cmp ecx, 32
 jb owned_start
 cmp edx, esi
 je owned_start
 cmp DWORD PTR [edx+0x128], 2
 je owned_start
 cmp DWORD PTR [edx+0x128], 4
 je owned_start
 movzx ecx, BYTE PTR [edx+0x11c]
 jmp owned_slots
owned_start:
 xor ecx, ecx
owned_slots:
 cmp ecx, eax
 jae owned_next
 cmp DWORD PTR [edx+ecx*4], ebp
 jne owned_step
 cmp edx, esi
 jne owned_bad_pop
 inc edi
owned_step:
 inc ecx
 jmp owned_slots
owned_next:
 pop edx
 pop ecx
 inc ecx
 add edx, 500
 cmp ecx, DWORD PTR [ebx+0x18]
 jb owned_team
 cmp edi, 1
 jne owned_bad
 mov ecx, DWORD PTR [ebx+0x38]
 mov edi, DWORD PTR [ebx+0x3c]
 test ecx, ecx
 jz owned_ir
 mov eax, ebp
 repne scasd
 je owned_bad
owned_ir:
 mov ecx, 160
 mov edi, 0xe421e0
 mov eax, ebp
 repne scasd
 je owned_bad
 mov eax, ebp
 jmp owned_done
owned_bad_pop:
 add esp, 8
owned_bad:
 xor eax, eax
owned_done:
 pop ebp
 pop edi
 pop edx
 pop ecx
 pop ebx
 ret

active_count:
 xor eax, eax
 jmp count
reserve_count:
 mov eax, 1
count:
 push ebx
 push esi
 push edi
 mov ebx, eax
 mov edi, ecx
 cmp edx, 17
 jne count_bad
 call current
 test eax, eax
 jz count_bad
 cmp edi, edx
 jne count_bad
 mov esi, eax
 call ps_reserve_count
 test eax, eax
 js count_bad
 test ebx, ebx
 jnz count_ready
 movzx eax, BYTE PTR [esi+0x11c]
count_ready:
 /* Validate every exposed row before allocating a list of that count. */
 mov edi, eax
 xor ecx, ecx
 mov edx, esi
 test ebx, ebx
 jz count_loop
 movzx eax, BYTE PTR [esi+0x11c]
 lea edx, [esi+eax*4]
count_loop:
 cmp ecx, edi
 jae count_good
 mov eax, DWORD PTR [edx+ecx*4]
 call owned
 test eax, eax
 jz count_bad
 inc ecx
 jmp count_loop
count_good:
 mov eax, edi
 jmp count_done
count_bad:
 xor eax, eax
count_done:
 pop edi
 pop esi
 pop ebx
 ret
active_get:
 xor eax, eax
 jmp getter
reserve_get:
 mov eax, 1
getter:
 push ebx
 push esi
 push edi
 mov ebx, eax
 mov esi, edx
 mov edi, ecx
 cmp DWORD PTR [esp+16], 17
 jne get_bad
 test esi, esi
 js get_bad
 call current
 test eax, eax
 jz get_bad
 cmp edi, edx
 jne get_bad
 mov edi, esi
 mov esi, eax
 call ps_reserve_count
 test eax, eax
 js get_bad
 test ebx, ebx
 jnz get_reserve
 movzx eax, BYTE PTR [esi+0x11c]
 cmp edi, eax
 jae get_bad
 jmp get_slot
get_reserve:
 cmp edi, eax
 jae get_bad
 movzx eax, BYTE PTR [esi+0x11c]
 add edi, eax
get_slot:
 mov eax, DWORD PTR [esi+edi*4]
 call owned
 jmp get_done
get_bad:
 xor eax, eax
get_done:
 pop edi
 pop esi
 pop ebx
 ret 4

/* Native binding: ECX=manager, EDX=sheet, stack=row. Popup may pump
 * events: recheck captured context, page and ownership after it returns.
 */
activate:
 push ebx
 push esi
 push edi
 push ebp
 mov edi, ecx
 mov ebp, edx
 cmp DWORD PTR [state_data+8], 0
 jne action_done
 cmp edi, DWORD PTR [state_data+4]
 jne action_done
 test ebp, ebp
 jz action_done
 cmp DWORD PTR [ebp+0x58], OFFSET sheet
 jne action_done
 mov eax, DWORD PTR [esp+20]
 test eax, eax
 js action_done
 cmp DWORD PTR [ebp+0xa4], 65
 ja action_done
 cmp eax, DWORD PTR [ebp+0xa4]
 jae action_done
 mov edx, DWORD PTR [ebp+0x40]
 test edx, edx
 jz action_done
 mov ebx, DWORD PTR [edx+eax*4]
 call action_check
 test eax, eax
 jz action_refused
 mov DWORD PTR [state_data+8], 1
 mov eax, OFFSET demote_menu
 cmp DWORD PTR [ebp+0x5c], OFFSET reserve_binding
 jne action_popup
 mov eax, OFFSET promote_menu
action_popup:
 push 0
 push -1
 push 1
 push edi
 push 0
 push eax
 mov edx, OFFSET screen_text
 mov ecx, 0xe3c040
 call dialog
 cmp eax, 1
 jne action_unlock
 call action_check
 test eax, eax
 jz action_refused
 mov edx, ebx
 mov ecx, esi
 cmp DWORD PTR [ebp+0x5c], OFFSET reserve_binding
 je action_promote
 call ps_demote
 test eax, eax
 jz action_result
 /* Host transaction also clears the persistent depth/returner locks. */
 and BYTE PTR [ebx+0x52], 0xe0
 jmp action_result
action_promote:
 call ps_promote
action_result:
 test eax, eax
 jz action_refused
 mov ecx, ebp
 call rebuild
 /* Native rebuild clamps +BC; explicitly also discard stale scroll/row scratch. */
 mov ecx, ebp
 mov edx, DWORD PTR [ebp+0xbc]
 call clamp
 mov DWORD PTR [ebp+0xc8], 0
 mov DWORD PTR [ebp+0xb4], 0
 jmp action_unlock
action_refused:
 mov ecx, edi
 mov edx, OFFSET refused_text
 call message
action_unlock:
 mov DWORD PTR [state_data+8], 0
action_done:
 pop ebp
 pop edi
 pop esi
 pop ebx
 ret 4

/* Require selected player in the current tab, not just somewhere on team. */
action_check:
 cmp edi, DWORD PTR [state_data+4]
 jne check_bad
 cmp DWORD PTR [ebp+0x58], OFFSET sheet
 jne check_bad
 call current
 test eax, eax
 jz check_done
 mov esi, eax
 mov eax, ebx
 call owned
 test eax, eax
 jz check_done
 mov al, BYTE PTR [ebx+8]
 and al, 0x1c
 cmp al, 4
 jne check_bad
 cmp BYTE PTR [ebx+0x28], 0xee
 je check_bad
 movzx ecx, BYTE PTR [esi+0x11c]
 xor edx, edx
 cmp DWORD PTR [ebp+0x5c], OFFSET active_binding
 je check_slots
 cmp DWORD PTR [ebp+0x5c], OFFSET reserve_binding
 jne check_bad
 mov edx, ecx
 movzx eax, BYTE PTR [esi+0x1f2]
 add ecx, eax
check_slots:
 cmp edx, ecx
 jae check_bad
 cmp DWORD PTR [esi+edx*4], ebx
 je check_good
 inc edx
 jmp check_slots
check_good:
 mov eax, 1
 ret
check_bad:
 xor eax, eax
check_done:
 ret
message:
 push 0
 push -1
 push 0
 push ecx
 push 0
 push 0x5042fc
 mov ecx, 0xe3c040
 call dialog
 ret
code_end:
