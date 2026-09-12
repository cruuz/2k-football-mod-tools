/* MyCareer, original i386 code. EXPERIMENTAL / UNWITNESSED.
 * 0..1279: pointer-free checkpoint. 1280..2559: I/O staging.
 * 2560 primary ptr, 2564 match ptr, 2568 entity ptr, 2572 appearance key.
 * 2576 error, 2580 requested entry, 2588 club pointer. 2600..2631 journal path.
 * 2640 visited-controller count, 2800..3311 validated controller pointers.
 * Checkpoint 96..179 is the immutable 84-byte MyPlayer recipe; its position
 * byte (checkpoint 149) is the identity's position, so MyPlayer can be any
 * of the 17 retail position codes. Checkpoint 180 requests the starter lock;
 * 184 records that it was written once.
 * All state belongs to the allocator's 4096-byte RW request.
 */
.intel_syntax noprefix
.code32
.text
.global entry, mode_text, title_text, attach, copy, reset, assign, automatic, team_reset
.global manual, transfer, generation, draft, sim, navigation, cpu_management
.global camera, camera_focus, screen_dispatch, load_complete, save_read, save_write
.global front_office, gameplan, enabled, primary, resolve_team, rebind, inject
.global settle, hash_bytes, check_state, journal_name, overwrite_guard, code_end

/* ZF clear only while a validated checkpoint owns the current Franchise. */
enabled:
 cmp DWORD PTR [state], 0x4251434d
 jne disabled
 cmp DWORD PTR [state+4], 0x31303030
 jne disabled
 cmp DWORD PTR [0xe576a0], 2
 jne disabled
 cmp DWORD PTR [state+24], 1
 jb disabled
 cmp DWORD PTR [state+24], 6
 ja disabled
 push eax
 mov eax, 1
 test eax, eax
 pop eax
 ret
disabled:
 push eax
 xor eax, eax
 pop eax
 ret

/* Resolve the primary pool ordinal and immutable creation fingerprint.
 * EAX returns a live primary record, never a saved RAM pointer. */
primary:
 push ebx
 push ecx
 push edx
 xor eax, eax
 mov DWORD PTR [state+2560], eax
 call enabled
 jz primary_done
 cmp DWORD PTR [state+24], 6
 je primary_done
 mov ebx, DWORD PTR [0xb72918]
 test ebx, ebx
 jz primary_done
 mov ecx, DWORD PTR [ebx]
 test ecx, ecx
 jz primary_done
 cmp ecx, 4096
 ja primary_done
 mov edx, DWORD PTR [state+28]
 cmp edx, ecx
 jae primary_lost
 imul edx, edx, 84
 mov eax, DWORD PTR [ebx+4]
 test eax, eax
 jz primary_done
 add eax, edx
 /* The identity's position is the recipe's, not a fixed QB code. */
 mov cl, BYTE PTR [state+96+0x35]
 cmp BYTE PTR [eax+0x35], cl
 jne primary_lost
 cmp DWORD PTR [state+24], 1
 je primary_valid
.ifdef MYCAREER_INLINE
 mov ecx, DWORD PTR [eax]
 sub ecx, ebx
 cmp ecx, DWORD PTR [state+84]
 jne primary_lost
.endif
 mov ecx, DWORD PTR [eax+0x10]
 sub ecx, ebx
 cmp ecx, DWORD PTR [state+88]
 jne primary_lost
 mov ecx, DWORD PTR [eax+0x14]
 sub ecx, ebx
 cmp ecx, DWORD PTR [state+92]
 jne primary_lost
 mov ecx, DWORD PTR [eax+4]
 cmp ecx, DWORD PTR [state+100]
 jne primary_lost
 mov ecx, DWORD PTR [eax+0x18]
 xor ecx, DWORD PTR [state+120]
 test ecx, 0x0ffff000
 jnz primary_lost
primary_valid:
 mov DWORD PTR [state+2560], eax
 jmp primary_done
primary_lost:
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+2576], 1
 xor eax, eax
primary_done:
 pop edx
 pop ecx
 pop ebx
 ret

/* Refresh actual signing/trade/reserve destination through native team lists.
 * The team-control association stays available to navigation. c4d50 below
 * presents CPU ownership to front-office consumers. */
resolve_team:
 pushad
 mov DWORD PTR [state+56], -1
 mov DWORD PTR [state+2588], 0
 mov DWORD PTR [state+80], 0
 call primary
 test eax, eax
 jz resolve_done
 mov ebp, eax
 xor edi, edi
resolve_club:
 mov ebx, DWORD PTR [0xe5786c+edi*4]
 test ebx, ebx
 jz resolve_next
.ifdef MYCAREER_INLINE
 /* Grown reserves include five index slots outside the team record. The
  * shared validator requires the installed owner and its sealed arena. */
 cmp BYTE PTR [ebx+0x19b], 2
 jne resolve_inline_slots
 mov ecx, ebx
 mov edx, ebp
 call mode_grown_member
 cmp eax, 2
 ja resolve_bad
 test eax, eax
 jz resolve_next
 movzx esi, BYTE PTR [ebx+0x11c]
 xor edx, edx
 cmp eax, 1
 je resolve_found
 mov edx, esi
 jmp resolve_found
resolve_inline_slots:
.endif
 movzx ecx, BYTE PTR [ebx+0x11c]
 cmp ecx, 65
 ja resolve_bad
 mov esi, ecx
 cmp BYTE PTR [ebx+0x19b], 1
 jne resolve_slots_ready
 cmp BYTE PTR [ebx+0x1f3], 0xa5
 jne resolve_bad
 movzx edx, BYTE PTR [ebx+0x1f2]
 cmp edx, 12
 ja resolve_bad
 add ecx, edx
 cmp ecx, 65
 ja resolve_bad
resolve_slots_ready:
 xor edx, edx
resolve_slot:
 cmp edx, ecx
 jae resolve_reserve
 cmp ebp, DWORD PTR [ebx+edx*4]
 je resolve_found
 inc edx
 jmp resolve_slot
resolve_reserve:
 /* Practice Squad v1 uses existing team-owned tail slots and metadata. */
 jmp resolve_next
resolve_found:
 cmp DWORD PTR [state+56], -1
 jne resolve_bad
 mov DWORD PTR [state+56], edi
 mov DWORD PTR [state+2588], ebx
 cmp edx, esi
 jb resolve_next
 mov DWORD PTR [state+80], 1
resolve_next:
 inc edi
 cmp edi, 32
 jb resolve_club
 cmp DWORD PTR [state+24], 1
 je resolve_done
 test BYTE PTR [ebp+8], 0x10
 jnz resolve_prospect
 mov DWORD PTR [state+24], 4
 cmp DWORD PTR [state+56], -1
 je resolve_done
 mov DWORD PTR [state+24], 3
 cmp DWORD PTR [state+80], 0
 je resolve_starter
 mov DWORD PTR [state+24], 5
 jmp resolve_done
resolve_starter:
 /* Once, on the first active club: depth row 1 at MyPlayer's own position
  * plus the rank lock bit that nfl2k5_depth_locks keeps through the weekly
  * ratings sort. Without that owner the bit is inert and the row is only an
  * initial placement. HYPOTHESIS for the CPU depth chart; never rewritten. */
 cmp DWORD PTR [state+180], 1
 jne resolve_done
 cmp DWORD PTR [state+184], 0
 jne resolve_done
 mov DWORD PTR [state+184], 1
 and WORD PTR [ebp+0x28], 0xe3ff
 or BYTE PTR [ebp+0x52], 1
 jmp resolve_done
resolve_prospect:
 mov DWORD PTR [state+24], 2
 jmp resolve_done
resolve_bad:
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+2576], 2
resolve_done:
 call enabled
 jz resolve_return
 /* Keep one native navigation association. CPU consumers use our getter. */
 xor eax, eax
 mov edi, 0xe5775c
 mov ecx, 34
 cld
 rep stosd
 mov eax, DWORD PTR [state+56]
 cmp eax, 32
 jae resolve_return
 mov DWORD PTR [0xe5775c+eax*4], 1
resolve_return:
 popad
 ret

/* The final-generation hook and first actual draft pick share one guarded
 * injection. A generation after this transition never silently reinjects. */
.ifndef MYCAREER_INLINE
inject:
 pushfd
 pushad
 call primary
 test eax, eax
 jz inject_done
 cmp DWORD PTR [state+24], 1
 jne inject_done
 cmp DWORD PTR [0xe576a4], 5
 jne inject_done
 test BYTE PTR [eax+8], 0x10
 jz inject_lost
 call resolve_team
 cmp DWORD PTR [state+56], -1
 jne inject_lost
 mov edi, eax
 mov esi, OFFSET FLAT:state+96
 mov ecx, 21
 cld
 rep movsd
 mov ebx, DWORD PTR [0xb72918]
 add DWORD PTR [eax], ebx
 add DWORD PTR [eax+16], ebx
 add DWORD PTR [eax+20], ebx
 or BYTE PTR [eax+8], 0x10
 mov DWORD PTR [state+24], 2
 jmp inject_done
inject_lost:
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+2576], 3
inject_done:
 popad
 popfd
 ret

generation:
 mov eax, 0x2be900
 call eax
 call inject
 ret
.endif
overwrite_guard:
 pushfd
 pushad
 call enabled
 jz overwrite_done
 cmp DWORD PTR [state+24], 2
 jb overwrite_done
 mov eax, DWORD PTR [0xb72918]
 test eax, eax
 jz overwrite_done
 mov edx, DWORD PTR [state+28]
 cmp edx, DWORD PTR [eax]
 jae overwrite_done
 imul edx, edx, 84
 add edx, DWORD PTR [eax+4]
 cmp ecx, edx
 jne overwrite_done
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+2564], 0
overwrite_done:
 popad
 popfd
 push 0x2be6f0
 ret
.ifndef MYCAREER_INLINE
draft:
 call inject
 sub esp, 0x110
 push 0x325b96
 ret
load_complete:
 mov eax, 0x1349a0
 call eax
 call confirm_load
 call inject
 call resolve_team
 cmp DWORD PTR [state+2576], 7
 jne load_done
 push 0
 push -1
 push 0
 push OFFSET FLAT:missing_help
 push 0
 push 0x5042fc
 mov edx, OFFSET FLAT:title_text
 mov ecx, 0xe3c040
 mov eax, 0x14e440
 call eax
load_done:
 ret
confirm_load:
 push eax
 cmp DWORD PTR [state+2652], 1
 jne confirm_done
 mov eax, DWORD PTR [state+2648]
 mov DWORD PTR [state+24], eax
 mov DWORD PTR [state+2652], 0
confirm_done:
 pop eax
 ret
.endif

copy:
 pushfd
 pushad
 cmp edx, 0xb30c4c
 jne copy_second
 mov DWORD PTR [state+2564], 0
 mov DWORD PTR [state+2568], 0
copy_second:
 cmp edx, 0xb30c4c
 je copy_valid
 cmp edx, 0xb321a0
 jne copy_done
copy_valid:
 call primary
 test eax, eax
 jz copy_done
 movzx ebx, BYTE PTR [ecx+0x11c]
 cmp ebx, 65
 ja copy_done
 xor esi, esi
copy_find:
 cmp esi, ebx
 jae copy_done
 cmp eax, DWORD PTR [ecx+esi*4]
 je copy_found
 inc esi
 jmp copy_find
copy_found:
 imul esi, esi, 84
 add esi, edx
 mov DWORD PTR [state+2564], esi
 call resolve_team
copy_done:
 popad
 popfd
 mov al, BYTE PTR [ecx+0x11c]
 push 0xc3c66
 ret

/* Clear body input from every active body, then bind exactly one unique match
 * identity. 128 nodes bounds cycles; malformed lists detach, never guess.
 * CPU blocks retain their native callback and mode. Only changed ownership
 * clears the five transient input words, so a held QB button survives a frame. */
rebind:
 pushfd
 pushad
 mov DWORD PTR [state+2568], 0
 mov DWORD PTR [state+2640], 0
 call enabled
 jz bind_done
 call primary
 test eax, eax
 jz bind_clear
 mov ebp, DWORD PTR [state+2564]
 jmp bind_start
bind_clear:
 xor ebp, ebp
bind_start:
 mov esi, DWORD PTR [0xe60268]
 xor edi, edi
 mov ebx, 128
bind_loop:
 test esi, esi
 jz bind_complete
 dec ebx
 js bind_bad
 mov edx, DWORD PTR [esi+0xc]
 test edx, edx
 jnz bind_controller
 cmp DWORD PTR [esi+0x48], 0
 jne bind_next
bind_controller:
 cmp edx, 0xbd8210
 jb bind_bad
 cmp edx, 0xbd8210+128*36-36
 ja bind_bad
 mov eax, edx
 sub eax, 0xbd8210
 push edx
 xor edx, edx
 mov ecx, 36
 div ecx
 test edx, edx
 pop edx
 jnz bind_bad
 mov eax, DWORD PTR [state+2640]
 mov DWORD PTR [state+2800+eax*4], edx
 inc DWORD PTR [state+2640]
 cmp DWORD PTR [esi+0x48], 0
 jne bind_cpu
 test ebp, ebp
 jz bind_cpu
 cmp ebp, DWORD PTR [esi+0x3c]
 jne bind_cpu
 test edi, edi
 jnz bind_bad
 mov edi, esi
bind_cpu:
.ifdef MYCAREER_INLINE
 /* Supersim keeps native membership visible while delaying input ownership
  * until the complete settled pre-snap frame has finished. */
 cmp DWORD PTR [state+2708],0
 jne bind_detach
.endif
 cmp esi, DWORD PTR [state+2584]
 jne bind_detach
 cmp edi, esi
 jne bind_detach
 mov eax, DWORD PTR [state+32]
 cmp DWORD PTR [edx], eax
 je bind_next
bind_detach:
 cmp DWORD PTR [edx], -1
 je bind_next
 mov DWORD PTR [edx], -1
 mov DWORD PTR [esi+0x44], 0
 mov DWORD PTR [edx+0x10], 0
 mov DWORD PTR [edx+0x14], 0
 mov DWORD PTR [edx+0x18], 0
 mov DWORD PTR [edx+0x1c], 0
 mov DWORD PTR [edx+0x20], 0
bind_next:
 mov esi, DWORD PTR [esi+0x30]
 jmp bind_loop
bind_complete:
 mov DWORD PTR [state+2568], edi
.ifdef MYCAREER_INLINE
 cmp DWORD PTR [state+2708],0
 je 1f
 xor edi,edi
1:
.endif
 mov DWORD PTR [state+2584], edi
 mov eax, DWORD PTR [state+32]
 imul ecx, eax, 24
 mov DWORD PTR [0xbe4d60+ecx], edi
 mov DWORD PTR [0xbe4d64+ecx], edi
 mov DWORD PTR [0xbe4d68+ecx], edi
 mov DWORD PTR [0xbe4d6c+ecx], edi
 mov DWORD PTR [0xe5fc50], 0
.ifdef MYCAREER_INLINE
 mov DWORD PTR [0xe5fc90], 0
.else
 mov DWORD PTR [0xe5fc88], 0
.endif
 test edi, edi
 jz bind_done
 mov edx, DWORD PTR [edi+0xc]
 cmp DWORD PTR [edx], eax
 je bind_registered
 mov DWORD PTR [edx], eax
 /* Native assignment also refreshes this port's input-mode mapping. */
 mov ecx, edx
 mov edx, DWORD PTR [ecx+4]
 mov eax, 0x1565f0
 call eax
 mov ecx, edi
 mov eax, 0x7d550
 call eax
bind_registered:
 mov DWORD PTR [edi+0x44], 0x40000000
 /* Remember participation for this fixture, not a possession-team pointer. */
 call fixture_key
 mov DWORD PTR [state+2572], eax
 jmp bind_done
bind_bad:
 mov DWORD PTR [state+2576], 4
 mov DWORD PTR [state+2564], 0
 mov DWORD PTR [state+2584], 0
 /* Clear only controller blocks actually reached and validated above. */
 mov ecx, DWORD PTR [state+2640]
 test ecx, ecx
 jz bind_bad_done
bind_all_cpu:
 mov edx, DWORD PTR [state+2800+ecx*4-4]
 mov DWORD PTR [edx], -1
 loop bind_all_cpu
bind_bad_done:
 xor edi, edi
 jmp bind_complete
bind_done:
 popad
 popfd
 ret

attach:
 call rebind
 mov eax, ebp
 pop ebp
 ret 4
reset:
 call enabled
 jz reset_retail
 call rebind
 ret
reset_retail:
 push esi
 mov esi, ecx
 mov eax, 0x63810
 call eax
 push 0x156648
 ret
assign:
 call enabled
 jz assign_retail
 call rebind
 ret 4
assign_retail:
 mov eax, DWORD PTR [esp+4]
 sub esp, 8
 push 0x156877
 ret
automatic:
 call enabled
 jz automatic_retail
 call rebind
 ret
automatic_retail:
 push ebx
 mov ebx, ecx
 mov al, BYTE PTR [ebx+0x2c]
 push 0x1a7976
 ret
team_reset:
 call enabled
 jz team_reset_retail
 call rebind
 ret
team_reset_retail:
 push edi
 mov edi, DWORD PTR [ecx+4]
 test edi, edi
 push 0x1a77a6
 ret
manual:
 call enabled
 jz manual_retail
 call rebind
 ret
manual_retail:
 push esi
 push edi
 mov edi, ecx
 mov eax, DWORD PTR [edi+0xc]
 push 0x1a85e7
 ret
transfer:
 call enabled
 jz transfer_retail
 call rebind
 ret 12
transfer_retail:
 mov eax, DWORD PTR [esp+4]
 mov ecx, DWORD PTR [esp+8]
 push 0x1a70e8
 ret

/* ECX row, EDX slot. Return 1 for the current MyPlayer club's fixture. */
career_fixture:
 push ebx
 push ecx
 push edx
 xor eax, eax
 cmp ecx, 22
 jae fixture_done
 cmp edx, 17
 jae fixture_done
 mov ebx, DWORD PTR [state+56]
 cmp ebx, 32
 jae fixture_done
 imul ecx, ecx, 17
 add ecx, edx
 movzx edx, BYTE PTR [0xe57c41+ecx*8]
 cmp edx, ebx
 je fixture_yes
 movzx edx, BYTE PTR [0xe57c42+ecx*8]
 cmp edx, ebx
 jne fixture_done
fixture_yes:
 mov eax, 1
fixture_done:
 pop edx
 pop ecx
 pop ebx
 ret
navigation:
 call enabled
 jz navigation_retail
 call resolve_team
 call settle
 jmp career_fixture
navigation_retail:
 push esi
 push edi
 mov esi, edx
 mov edi, ecx
 push 0xc6d16
 ret
sim:
 call enabled
 jz sim_retail
 cmp DWORD PTR [state+24], 6
 je sim_refuse
 call resolve_team
 call settle
 call career_fixture
 test eax, eax
 jz sim_retail
sim_refuse:
 /* Never whole-game simulate a MyPlayer-team fixture, even while benched. */
 mov DWORD PTR [state+2576], 5
 xor eax, eax
 ret 4
sim_retail:
 sub esp, 0x110
 push 0xc7a26
 ret
cpu_management:
 call enabled
 jz cpu_retail
 /* Native game launch and the two menu team enumerators see the club.
  * Draft, signing, trade and weekly-management callers see CPU ownership. */
 cmp DWORD PTR [esp], 0xc73b0
 jb cpu_menu
 cmp DWORD PTR [esp], 0xc74db
 jb cpu_club
cpu_menu:
 cmp DWORD PTR [esp], 0x13ebe0
 jb cpu_no
 cmp DWORD PTR [esp], 0x13ec70
 jae cpu_no
cpu_club:
 xor eax, eax
 cmp ecx, DWORD PTR [state+2588]
 sete al
 ret
cpu_no:
 xor eax, eax
 ret
cpu_retail:
 mov eax, 0xc4ca0
 call eax
 push 0xc4d55
 ret

.macro gm_launcher name, resume
\name:
 call enabled
 jz \name\()_retail
 mov DWORD PTR [state+2576], 6
 xor eax, eax
 ret
\name\()_retail:
 push 0
 push 0
 push 0
 push \resume
 ret
.endm
.ifndef MYCAREER_INLINE
gm_launcher front_office, 0x142916
gm_launcher gameplan, 0x142956
.endif

.ifndef MYCAREER_INLINE
screen_dispatch:
 /* The adjacent ordinary Franchise row explicitly leaves MyCareer. */
 cmp edx, 0x500dc8
 jne screen_career
 mov DWORD PTR [state], 0
 mov DWORD PTR [state+2580], 0
 mov DWORD PTR [state+2564], 0
 mov DWORD PTR [state+2568], 0
 jmp screen_retail
screen_career:
 call enabled
 jz screen_retail
 cmp edx, 0x52533c
 je screen_refuse
 cmp edx, 0x503d6c
 je screen_refuse
 cmp edx, 0x555098
 je screen_refuse
 /* Includes the native Practice Squad clone and other editor-only clones. */
 cmp edx, 0x14ba000
 jae screen_refuse
 jmp screen_retail
screen_refuse:
 mov DWORD PTR [state+2576], 6
 xor eax, eax
 ret
screen_retail:
 push esi
 mov esi, ecx
 cmp DWORD PTR [esi+0x100], 0x20
 push 0x6e39a
 ret
.endif

camera:
 /* The camera owner (version 4, Standard default) no longer touches the
    fresh-profile default site; its constant spectator hook at A54C3 (retail
    jle 7e06, owned nop nop) identifies it. When selected, its session option
    also governs MyCareer; the native per-frame route keeps Options changes
    and its normal focus hook. */
 cmp WORD PTR [0xa54c3], 0x9090
 je camera_retail
 call enabled
 jz camera_retail
 push eax
 mov eax, DWORD PTR [state+36]
 cmp eax, 1
 ja camera_done
 cmp eax, DWORD PTR [0xb665f0]
 je camera_done
 mov DWORD PTR [0xb665f0], eax
 mov DWORD PTR [0xb665f4], 1
camera_done:
 pop eax
 ret
camera_retail:
 push ebx
 push esi
 push edi
 xor edi, edi
 push 0xa5495
 ret
camera_focus:
 pushfd
 push eax
 call enabled
 jz focus_done
 mov eax, DWORD PTR [state+2568]
 test eax, eax
 jz focus_done
 mov eax, DWORD PTR [eax+0x18]
 test eax, eax
 jz focus_done
 add eax, 0x30
 /* Two saved words + return + time: first focus-vector argument at +16. */
 mov DWORD PTR [esp+16], eax
focus_done:
 pop eax
 popfd
 push 0x5f760
 ret

/* Monotonic key uses actual year/stage/row/fixture, not a week increment. */
fixture_key:
 mov eax, DWORD PTR [0xe576b8]
 shl eax, 16
 mov ecx, DWORD PTR [0xe576a4]
 shl ecx, 12
 add eax, ecx
 mov ecx, DWORD PTR [0xe576b4]
 shl ecx, 5
 add eax, ecx
 add eax, DWORD PTR [0xe576bc]
 inc eax
 ret
settle:
 pushfd
 pushad
 call enabled
 jz settle_done
 cmp DWORD PTR [0xe576b8], 127
 ja settle_done
 mov eax, DWORD PTR [0xe576a4]
 cmp eax, 7
 jb settle_done
 cmp eax, 9
 ja settle_done
 call fixture_key
 mov ebp, eax
 mov ecx, DWORD PTR [0xe576b4]
 mov edx, DWORD PTR [0xe576bc]
 /* A completed appearance can be settled after native week navigation. */
 mov eax, DWORD PTR [state+2572]
 test eax, eax
 jz settle_fixture
 dec eax
 mov ebx, eax
 shr ebx, 16
 cmp ebx, DWORD PTR [0xe576b8]
 jne settle_fixture
 mov ebx, eax
 shr ebx, 12
 and ebx, 15
 cmp ebx, DWORD PTR [0xe576a4]
 jne settle_fixture
 mov ebp, DWORD PTR [state+2572]
 mov edx, eax
 and edx, 31
 shr eax, 5
 and eax, 127
 mov ecx, eax
settle_fixture:
 call career_fixture
 test eax, eax
 jz settle_done
 imul ecx, ecx, 17
 add ecx, edx
 cmp BYTE PTR [0xe57c40+ecx*8], 3
 jne settle_done
 mov eax, ebp
 cmp eax, DWORD PTR [state+68]
 jbe settle_done
 xor edx, edx
 xor ebx, ebx
 cmp DWORD PTR [state+24], 3
 jne settle_award
 cmp eax, DWORD PTR [state+2572]
 jne settle_award
 mov edx, 25
 mov ebx, 1
settle_award:
 mov DWORD PTR [state+68], eax
 add DWORD PTR [state+64], edx
 cmp DWORD PTR [state+64], 1000000
 jbe settle_store
 mov DWORD PTR [state+64], 1000000
settle_store:
.ifndef MYCAREER_INLINE
 mov edi, DWORD PTR [state+72]
 and edi, 63
 shl edi, 4
 add edi, OFFSET FLAT:state+256
 mov DWORD PTR [edi], eax
 mov DWORD PTR [edi+4], edx
 mov eax, DWORD PTR [state+64]
 mov DWORD PTR [edi+8], eax
 mov DWORD PTR [edi+12], ebx
 inc DWORD PTR [state+72]
 and DWORD PTR [state+72], 63
 cmp DWORD PTR [state+76], 64
 jae settle_done
 inc DWORD PTR [state+76]
.else
 add DWORD PTR [state+196], edx
 cmp DWORD PTR [state+196], 1000000
 jbe settle_done
 mov DWORD PTR [state+196], 1000000
.endif
settle_done:
 popad
 popfd
 ret

/* FNV-1a32: ESI bytes, ECX length, EAX seed. EDX clobbered. */
.ifndef MYCAREER_INLINE
hash_bytes:
 test ecx, ecx
 jz hash_done
hash_loop:
 movzx edx, BYTE PTR [esi]
 xor eax, edx
 imul eax, eax, 0x1000193
 inc esi
 dec ecx
 jnz hash_loop
hash_done:
 ret
/* ESI checkpoint; return EAX=1 for valid bounded pointer-free content. */
check_state:
 push ebx
 push ecx
 push edx
 push esi
 mov ebx, esi
 xor eax, eax
 cmp DWORD PTR [ebx], 0x4251434d
 jne check_done
 cmp DWORD PTR [ebx+4], 0x31303030
 jne check_done
 cmp DWORD PTR [ebx+8], 1280
 jne check_done
 cmp DWORD PTR [ebx+24], 1
 jb check_done
 cmp DWORD PTR [ebx+24], 6
 ja check_done
 cmp DWORD PTR [ebx+28], 4096
 jae check_done
 cmp DWORD PTR [ebx+32], 8
 jae check_done
 cmp DWORD PTR [ebx+36], 2
 jae check_done
 cmp DWORD PTR [ebx+60], 0
 jne check_done
 mov eax, DWORD PTR [ebx+96]
 cmp eax, DWORD PTR [ebx+84]
 jne check_invalid
 mov eax, DWORD PTR [ebx+112]
 cmp eax, DWORD PTR [ebx+88]
 jne check_invalid
 mov eax, DWORD PTR [ebx+116]
 cmp eax, DWORD PTR [ebx+92]
 jne check_invalid
 xor eax, eax
 cmp DWORD PTR [ebx+76], 64
 ja check_done
 cmp DWORD PTR [ebx+72], 64
 jae check_done
 cmp DWORD PTR [ebx+84], 0x91000
 jae check_done
 cmp DWORD PTR [ebx+88], 0x91000
 jae check_done
 cmp DWORD PTR [ebx+92], 0x91000
 jae check_done
 cmp DWORD PTR [ebx+64], 1000000
 ja check_done
 cmp BYTE PTR [ebx+96+0x35], 17
 jae check_done
 cmp DWORD PTR [ebx+180], 1
 ja check_done
 cmp DWORD PTR [ebx+184], 1
 ja check_done
 mov eax, DWORD PTR [ebx+40]
 or eax, DWORD PTR [ebx+44]
 or eax, DWORD PTR [ebx+48]
 or eax, DWORD PTR [ebx+52]
 jz check_done
 mov eax, 0x811c9dc5
 lea esi, [ebx+16]
 mov ecx, 1264
 call hash_bytes
 cmp eax, DWORD PTR [ebx+12]
 sete al
 movzx eax, al
 jmp check_done
check_invalid:
 xor eax, eax
check_done:
 pop esi
 pop edx
 pop ecx
 pop ebx
 ret

/* U: is title data. A 64-slot journal stays outside signed save folders.
 * Exact two-hash pairing refuses stale/colliding slot occupants. */
journal_name:
 pushad
 mov esi, OFFSET FLAT:journal_path
 mov edi, OFFSET FLAT:state+2600
 mov ecx, 18
 cld
 rep movsb
 mov eax, DWORD PTR [state+2592]
 and eax, 63
 mov edx, eax
 shr eax, 4
 and edx, 15
 mov al, BYTE PTR [hex_digits+eax]
 mov dl, BYTE PTR [hex_digits+edx]
 mov BYTE PTR [state+2611], al
 mov BYTE PTR [state+2612], dl
 popad
 ret

/* ESI complete FXG buffer. Compute a pair independent of process pointers. */
pair_save:
 push esi
 mov eax, 0x811c9dc5
 mov ecx, 720044
 call hash_bytes
 mov DWORD PTR [state+2592], eax
 pop esi
 mov eax, 0x9e3779b9
 mov ecx, 720044
 call hash_bytes
 mov DWORD PTR [state+2596], eax
 call journal_name
 ret

/* Calls use the retail stdcall API. All handles close before return.
 * A saved FXG remains retail-sized; journal failures never counterfeit a save
 * signature. The error is exposed in the MyCareer entry dialog. */
checkpoint_read:
 pushad
 call pair_save
 mov DWORD PTR [state], 0
 mov DWORD PTR [state+2560], 0
 mov DWORD PTR [state+2564], 0
 mov DWORD PTR [state+2568], 0
 mov DWORD PTR [state+2652], 0
 push 0
 push 0x80
 push 3
 push 0
 push 1
 push 0x80000000
 push OFFSET FLAT:state+2600
 mov eax, 0x1e336
 call eax
 cmp eax, -1
 je read_seed
 mov ebx, eax
 push 0
 push OFFSET FLAT:state+2620
 push 1280
 push OFFSET FLAT:state+1280
 push ebx
 call read_original
 mov edi, eax
 push ebx
 mov eax, 0x1a69f
 call eax
 test edi, edi
 jz read_seed
 cmp DWORD PTR [state+2620], 1280
 jne read_seed
 mov esi, OFFSET FLAT:state+1280
 call check_state
 test eax, eax
 jz read_seed
 mov eax, DWORD PTR [esi+16]
 cmp eax, DWORD PTR [state+2592]
 jne read_seed
 mov eax, DWORD PTR [esi+20]
 cmp eax, DWORD PTR [state+2596]
 je read_accept
read_seed:
 mov esi, OFFSET FLAT:seed
 call check_state
 test eax, eax
 jz read_missing
 mov eax, DWORD PTR [esi+16]
 cmp eax, DWORD PTR [state+2592]
 jne read_missing
 mov eax, DWORD PTR [esi+20]
 cmp eax, DWORD PTR [state+2596]
 jne read_missing
read_accept:
 mov edi, OFFSET FLAT:state
 mov ecx, 320
 cld
 rep movsd
 /* File bytes alone do not prove that native signature validation and load
  * succeeded. Hold input until the actual season deserializer completes. */
 mov eax, DWORD PTR [state+24]
 mov DWORD PTR [state+2648], eax
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+2652], 1
 mov DWORD PTR [state+2576], 0
 jmp read_done
read_missing:
 mov DWORD PTR [state+2576], 7
 cmp DWORD PTR [state+2580], 1
 jne read_done
 /* Requested MyCareer must not fall back to team control on a bad pairing. */
 mov esi, OFFSET FLAT:seed
 call check_state
 test eax, eax
 jz read_done
 mov edi, OFFSET FLAT:state
 mov ecx, 320
 cld
 rep movsd
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+56], -1
 mov DWORD PTR [state+2588], 0
read_done:
 popad
 ret
checkpoint_write:
 pushad
 cmp DWORD PTR [state+2652], 0
 jne write_done
 call settle
 call pair_save
 mov esi, OFFSET FLAT:state
 mov edi, OFFSET FLAT:state+1280
 mov ecx, 320
 cld
 rep movsd
 mov eax, DWORD PTR [state+2592]
 mov DWORD PTR [state+1296], eax
 mov eax, DWORD PTR [state+2596]
 mov DWORD PTR [state+1300], eax
 mov esi, OFFSET FLAT:state+1296
 mov ecx, 1264
 mov eax, 0x811c9dc5
 call hash_bytes
 mov DWORD PTR [state+1292], eax
 push 0
 push 0x80000080
 push 2
 push 0
 push 0
 push 0x40000000
 push OFFSET FLAT:state+2600
 mov eax, 0x1e336
 call eax
 cmp eax, -1
 je write_failed
 mov ebx, eax
 push 0
 push OFFSET FLAT:state+2620
 push 1280
 push OFFSET FLAT:state+1280
 push ebx
 call write_original
 mov edi, eax
 push ebx
 mov eax, 0x1a69f
 call eax
 test edi, edi
 jz write_failed
 cmp DWORD PTR [state+2620], 1280
 jne write_failed
 mov DWORD PTR [state+2576], 0
 jmp write_done
write_failed:
 mov DWORD PTR [state+2576], 8
write_done:
 popad
 ret

.macro io_hook name, original, callback, writing
\name:
 push ebp
 mov ebp, esp
 push DWORD PTR [ebp+24]
 push DWORD PTR [ebp+20]
 push DWORD PTR [ebp+16]
 push DWORD PTR [ebp+12]
 push DWORD PTR [ebp+8]
 call \original
 pushfd
 pushad
 test eax, eax
 jz \name\()_done
 cmp DWORD PTR [ebp+16], 720044
 jb \name\()_done
 cmp DWORD PTR [ebp+16], 720896
 ja \name\()_done
 mov ecx, DWORD PTR [ebp+20]
 test ecx, ecx
 jz \name\()_done
 cmp DWORD PTR [ecx], 720044
 jb \name\()_done
 mov edx, DWORD PTR [ebp+16]
 cmp DWORD PTR [ecx], edx
 ja \name\()_done
 mov esi, DWORD PTR [ebp+12]
 cmp DWORD PTR [esi+0x2e0], 0x54534f52
 jne \name\()_done
 cmp BYTE PTR [esi+0x91320], 2
 jne \name\()_done
.if \writing
 call enabled
 jz \name\()_done
.else
 cmp DWORD PTR [state+2580], 1
 jne \name\()_done
.endif
 call \callback
\name\()_done:
 popad
 popfd
 pop ebp
 ret 20
.endm
io_hook save_read, read_original, checkpoint_read, 0
io_hook save_write, write_original, checkpoint_write, 1
read_original:
 push ebp
 mov ebp, esp
 sub esp, 16
 push 0x1d8d8
 ret
write_original:
 push ebp
 mov ebp, esp
 sub esp, 16
 push 0x1d9c5
 ret

/* The Game Modes row action. The native list dispatcher (0x150020, row kind
 * 9 through the 0x15024C case table) calls [row+0x28] with ECX = the screen
 * stack object and EDX = its state entry, then pops EBX/EBP/ESI/EDI and
 * returns; pushad/popad and the retail dialog (0x14E070 saves EBX/ESI/EDI,
 * ret 0x28; wrapper 0x14E440 ret 0x18) keep that contract. A configured
 * build reuses native Load / Save rather than FPP's forced exhibition
 * settings; a build without a sealed setup only explains itself. */
entry:
 mov DWORD PTR [state+2652], 0
 pushad
 mov esi, OFFSET FLAT:seed
 call check_state
 test eax, eax
 jz entry_unconfigured
 mov edi, OFFSET FLAT:state
 mov ecx, 320
 cld
 rep movsd
 mov DWORD PTR [state+24], 6
 mov DWORD PTR [state+56], -1
 mov DWORD PTR [state+2576], 7
 mov DWORD PTR [state+2580], 1
 popad
 push ecx
 push 0
 push -1
 push 0
 push OFFSET FLAT:entry_help
 push 0
 push 0x5042fc
 mov edx, OFFSET FLAT:title_text
 mov ecx, 0xe3c040
 mov eax, 0x14e440
 call eax
 pop ecx
 mov edx, 0x508df0
 mov eax, 0x6e390
 jmp eax
entry_unconfigured:
 popad
 /* No setup is sealed in this executable: nothing can pair, so no Load /
  * Save screen is pushed and no MyCareer entry is requested. */
 mov DWORD PTR [state+2580], 0
 push ecx
 push 0
 push -1
 push 0
 push OFFSET FLAT:no_setup_help
 push 0
 push 0x5042fc
 mov edx, OFFSET FLAT:title_text
 mov ecx, 0xe3c040
 mov eax, 0x14e440
 call eax
 pop ecx
 ret
.balign 4, 0xcc
/* Both 20-byte labels equal nfl2k5_modern_naming.career_text("menu_row") and
 * career_text("screen_title"); test_nfl2k5_my_career pins that contract. */
mode_text:
 .short 77,121,67,97,114,101,101,114,0,0
title_text:
 .short 77,121,67,97,114,101,101,114,0,0
entry_help:
 .string16 "EXPERIMENTAL / UNWITNESSED. Load the Franchise draft save prepared on the MyCareer page in Studio. Keep the matching setup in Build."
no_setup_help:
 .string16 "This build has no MyCareer setup. Create MyPlayer on the MyCareer page in Studio, include MyCareer.json in Build, then load the paired save from this menu."
missing_help:
 .string16 "MyCareer checkpoint is missing or does not match this save. MyPlayer input is disabled. Reload a matching save and checkpoint, or choose the ordinary Franchise menu."
journal_path:
 .asciz "U:\\MyCareer00.dat"
hex_digits:
 .ascii "0123456789ABCDEF"
code_end:
.endif
.section .note.GNU-stack,"",@progbits
