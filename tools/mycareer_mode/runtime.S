.intel_syntax noprefix
.code32
.text
.global mode_stage
mode_stage:
 call 0x61730
 pushfd
 pushad
 call mode_match_copy
 popad
 popfd
 ret
.global inline_size, inline_save, inline_load_begin, inline_admission
.global inline_read, inline_load_end, inline_roster_size
.global inline_active
inline_active:
 /* Share the binder's complete magic/Franchise/phase admission. */
 call enabled
 jz 1f
 cmp DWORD PTR [state+2580],2
 jne 1f
 cmp DWORD PTR [state+24],1
 je 1f
 push 1
 pop eax
 ret
1: xor eax,eax
 ret
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
 pushfd
 push eax
 xor eax,eax
 mov DWORD PTR [state],eax
 mov DWORD PTR [state+2560],eax
 mov DWORD PTR [state+2564],eax
 mov DWORD PTR [state+2568],eax
 mov DWORD PTR [state+2660],eax
 mov DWORD PTR [state+2664],eax
 mov DWORD PTR [state+2708],eax
 mov DWORD PTR [state+2716],eax
 mov DWORD PTR [state+2732],eax
 pop eax
 popfd
 jmp 0x16ab70

.global mode_ff_dialog
mode_ff_dialog:
 /* Any native modal restores ordinary speed/audio before its nested loop. */
 mov DWORD PTR [state+2716],0
 push ebp
 mov ebp,esp
 and esp,0xfffffff8
 sub esp,0x1c
 push 0x14e079
 ret
.global mode_ff_qb_snap, mode_ff_other_snap
.macro ff_snap_guard
 pushfd
 pushad
 call mode_ff_hold_snap
 test eax,eax
 popad
 jz 1f
 popfd
 xor eax,eax
 ret
1: popfd
.endm
mode_ff_qb_snap:
 ff_snap_guard
 push esi
 mov esi,ecx
 mov eax,DWORD PTR [esi+0xc]
 push 0x2d37e6
 ret
mode_ff_other_snap:
 ff_snap_guard
 sub esp,0xc
 push esi
 push edi
 push 0x2ed025
 ret
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
 push ecx
 call m3_creation_route
 pop ecx
 mov edx,eax
 jmp 0x6e390
1: jmp 0x6e450
mode_handler:
 push ecx
 push edx
 call mode_event
 pop edx
 pop ecx
 cmp edx,6
 je mode_frame
 cmp edx,7
 je mode_draw_frame
 jmp 0xf3e90
mode_draw_frame:
 push ecx
 call 0xf3e90
 pop ecx
 jmp mode_draw

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
.global mode_autosave
mode_autosave:
 /* The host validates Auto Save's complete template before admitting this
  * optional bridge. Its installed Desk callback locates the relocated owner.
  * The retail pointer means Auto Save was not selected for this build. */
 mov eax,DWORD PTR [0x521dcc]
 cmp eax,0x142dd0
 je 1f
 add eax,OFFSET FLAT:autosave_completion_delta
 jmp eax
1: ret
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
.global mode_art_input
.global mode_camera_focus
mode_camera_focus:
 /* Phase 7 is the pre-lineup presentation. Its descriptor and skeleton
  * focus already supply framing; keep that focus untouched.
  * Gameplay phases retain the existing MyPlayer camera hook verbatim. */
 pushfd
 cmp DWORD PTR [0xb616c0],7
 jne 1f
 popfd
 jmp 0x5f760
1: popfd
 jmp camera_focus
.global mode_camera_pick
mode_camera_pick:
 /* Native 89590's last camera-only choice; earlier play/task work is done.
  * A present MyPlayer follows the same branch as a retail human side. */
 pushad
 call mode_unit_present
 test eax,eax
 popad
 jnz 0x89722
 mov eax,DWORD PTR [0xe5fc50]
 test eax,eax
 jmp 0x89712
mode_art_input:
 /* Only the bound player's input decoder sees the temporary art-side mask.
  * Native play/task selection and controller assignment run outside it. */
 push ebx
 call mode_unit_present
 test eax,eax
 jz 1f
 mov edx,DWORD PTR [eax+0xc]
 cmp edx,DWORD PTR [esp+12]
 jne 1f
 mov ebx,DWORD PTR [eax+0x38]
 push DWORD PTR [ebx+0x24]
 mov DWORD PTR [ebx+0x24],1
 push DWORD PTR [esp+16]
 push DWORD PTR [esp+16]
 call 0x120a20
 pop DWORD PTR [ebx+0x24]
 pop ebx
 ret 8
1: pop ebx
 jmp 0x120a20
human_defense:
 /* JMP adapter for CMP [ESI+30],EBX; PUSH EBX; JNE. EBX is zero. */
 push eax
 call human_esi
 pop eax
 push ebx
 jnz 1f
 jmp 0xa3432
1: jmp 0xa3443

.global start_player
.global mode_row_text
mode_row_text:
 /* Native row text is already formatted. Tint the selected owned row,
  * retaining the scene's opacity and all native selection/scrolling. */
 call 0x30ab0
 pushfd
 push eax
 cmp edi,DWORD PTR [state+2672]
 jne row_done
 mov eax,DWORD PTR [edi+0x100]
 cmp esi,DWORD PTR [edi+eax*8+4]
 jne row_done
 mov eax,DWORD PTR [edi+eax*8]
 cmp DWORD PTR [eax+8],OFFSET FLAT:mode_handler
 jne row_done
 mov eax,DWORD PTR [esp+36]
 and DWORD PTR [eax+32],0xff000000
 or DWORD PTR [eax+32],0x00ffff00
row_done:
 pop eax
 popfd
 ret
start_player:
 /* resolve_team validates identity, membership and native/grown reserves.
  * Insert the created record before the old starter in both native chains.
  * Ranks below its former rank move down once; overflow row 7 stays 7. */
 pushad
 call resolve_team
 cmp DWORD PTR [state+24],3
 jne start_done
 mov edi,DWORD PTR [state+2560]
 mov esi,DWORD PTR [state+2588]
 movzx ebp,BYTE PTR [edi+41]
 shr ebp,2
 and ebp,7
 xor ebx,ebx
start_loop:
 movzx eax,BYTE PTR [esi+0x11c]
 cmp ebx,eax
 jae start_finish
 mov edx,DWORD PTR [esi+ebx*4]
 mov al,BYTE PTR [edi+53]
 cmp BYTE PTR [edx+53],al
 jne start_next
 movzx eax,BYTE PTR [edx+41]
 shr eax,2
 and eax,7
 cmp edx,edi
 jne start_other
 xor eax,eax
 jmp start_write
start_other:
 cmp eax,ebp
 jb start_shift
 mov ecx,eax
 or ecx,ebp
 jnz start_write
start_shift:
 inc eax
start_write:
 push eax
 movzx ecx,BYTE PTR [edi+53]
 mov eax,0x1ec18
 bt eax,ecx
 pop eax
 lea ecx,[eax+eax*8]
 lea ecx,[ecx*4]
 jnc start_bits
 cmp eax,3
 jae start_bits
 movzx ecx,BYTE PTR [start_sides+eax]
start_bits:
 and BYTE PTR [edx+41],3
 or BYTE PTR [edx+41],cl
start_next:
 inc ebx
 jmp start_loop
start_finish:
 or BYTE PTR [edi+82],3
 push 1
 pop eax
 mov DWORD PTR [state+180],eax
 mov DWORD PTR [state+184],eax
start_done:
 popad
 ret
start_sides:
 .byte 0x40,0x04,0x28

.section .note.GNU-stack,"",@progbits

 .text
.global mode_hud_frame
mode_hud_frame:
 /* Displaced target 89F50 is a pinned RET. Preserve the complete machine
  * state across text formatting, x87 stat returns and native glyph work. */
 pushfd
 pushad
 mov ebp,esp
 sub esp,528
 and esp,-16
 fxsave [esp]
 call mode_hud
 fxrstor [esp]
 mov esp,ebp
 popad
 popfd
 ret
