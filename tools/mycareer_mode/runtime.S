.intel_syntax noprefix
.code32
.text
.global inline_size, inline_save, inline_load_begin, inline_admission
.global inline_read, inline_load_end, inline_roster_size
/* Only the Franchise total-size calculation gets the footer. */
inline_size:
 call inline_active
 test eax,eax
 mov eax,0x165b0
 jz 1f
 add eax,128
1: ret
/* Retail FO serializer runs before the appended footer and native signing. */
inline_save:
 push ecx
 call 0x2d0790
 pushfd
 pushad
 call inline_active
 test eax,eax
 jz 1f
 call settle
 mov ecx,DWORD PTR [esp+36]
 add ecx,0x165b0
 call inline_encode
1: popad
 popfd
 add esp,4
 ret
inline_load_begin:
 mov DWORD PTR [state],0
 mov DWORD PTR [state+2560],0
 mov DWORD PTR [state+2564],0
 mov DWORD PTR [state+2568],0
 mov DWORD PTR [state+2660],0
 mov DWORD PTR [state+2664],0
 jmp 0x16ab70
/* Replace just type-9's expected-size branch of the native admission table. */
inline_admission:
 mov ecx,DWORD PTR [esi+0xbdc1cc]
 call inline_admit
 xor eax,1
 pop esi
 ret
/* Native ReadFile transaction remains responsible for authentication/errors. */
inline_read:
 push ebp
 mov ebp,esp
 push DWORD PTR [ebp+16]
 push DWORD PTR [ebp+12]
 push DWORD PTR [ebp+8]
 call 0x16c880
 pushfd
 pushad
 test eax,eax
 jz 2f
 mov eax,DWORD PTR [ebp+8]
 mov ecx,DWORD PTR [ebp+12]
 add ecx,eax
 /* The caller preserves metadata offset EBP; our frame saves it at [EBP]. */
 mov eax,DWORD PTR [ebp]
 cmp DWORD PTR [eax+0xbdc1d4],9
 jne 1f
 mov edx,DWORD PTR [eax+0xbdc1cc]
 call inline_stage
 mov DWORD PTR [esp+28],eax
 test eax,eax
 jnz 2f
 mov DWORD PTR [state+2576],7
 jmp 3f
1: cmp DWORD PTR [state+2580],0
 je 2f
 mov DWORD PTR [esp+28],0
 mov DWORD PTR [state+2576],7
3: call mode_load_error
2: popad
 popfd
 pop ebp
 ret 12
inline_roster_size:
 mov eax,DWORD PTR [state+2664]
 test eax,eax
 jnz 1f
 jmp 0xbfe50
1: ret
/* After BOTH the roster/season and complete front-office deserializers. */
inline_load_end:
 pushfd
 pushad
 cmp DWORD PTR [state+2660],1
 jne 1f
 mov DWORD PTR [state+2660],0
 call inline_decode
1: popad
 popfd
 mov eax,0x165b0
 ret

.global native_new_player, mode_creation_done, mode_handler
native_new_player:
 /* Enter the native NEW branch, never the existing-player list selection. */
 push esi
 push edi
 mov esi,ecx
 xor edi,edi
 jmp 0x34621c
mode_creation_done:
 push ecx
 push edx
 call mode_created
 test eax,eax
 pop edx
 pop ecx
 jz 1f
 push ecx
 mov edx,OFFSET FLAT:entry_menu
 call 0x6e450
 pop ecx
 mov DWORD PTR [state+2680],2
 mov edx,OFFSET FLAT:team_menu
 jmp 0x6e390
1: jmp 0x6e450
mode_handler:
 push ecx
 push edx
 call mode_event
 pop edx
 pop ecx
 jmp 0xf3e90

.global mode_dispatch, mode_practice_return, mode_loaded_replace
.global mode_cap_template
mode_cap_template:
 call mode_cap_ratings
 test eax,eax
 jnz 1f
 mov edx,DWORD PTR [0xcb8b14]
 push 0x343466
 ret
1: ret
mode_dispatch:
 push ecx
 call mode_route
 pop ecx
 mov edx,eax
 test edx,edx
 jz 1f
 push esi
 mov esi,ecx
 cmp DWORD PTR [esi+0x100],0x20
 push 0x6e39a
 ret
1: ret
mode_practice_return:
 push ecx
 call mode_return
 pop ecx
 mov edx,eax
 jmp 0x6e450
mode_loaded_replace:
 push ecx
 call mode_loaded
 pop ecx
 mov edx,eax
 jmp 0x6e2e0

/* Exact five-byte MOV/TEST consumers; each preserves the original live
 * registers and returns flags from the substituted human predicate. */
.global human_ecx, human_esi, human_eax, human_defense, mode_stats_commit
mode_stats_commit:
 call 0x134140
 jmp settle
human_esi:
 push ecx
 mov ecx,esi
 call human_ecx
 pop ecx
 ret
human_ecx:
 push ecx
 push edx
 call mode_human
 pop edx
 pop ecx
 test eax,eax
 ret
human_eax:
 push eax
 mov ecx,eax
 call human_ecx
 mov ecx,eax
 pop eax
 test ecx,ecx
 ret
human_defense:
 /* JMP adapter for CMP [ESI+30],EBX; PUSH EBX; JNE. EBX is zero. */
 push eax
 call human_esi
 pop eax
 push ebx
 jnz 1f
 jmp 0xa3432
1: jmp 0xa3443

.section .note.GNU-stack,"",@progbits
