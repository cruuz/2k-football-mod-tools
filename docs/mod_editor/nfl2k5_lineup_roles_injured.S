# nfl2k5_lineup_roles rule 4 (b780 sub1; MC1's finding, coordinator 11/04): the weekly CPU auto-depth 0x2BDCF0 ranks
# by rating and never tests the injury bit (player +0x20 bit 31), so CPU depth charts listed injured starters. This
# block replaces the game's three calls of 0x2BDCF0 (0x247D5C, 0x248075, 0x24853D). It runs the pass, then for every
# league club the pass sorts (team +0x128 kind 0: never an all-star, Pro Bowl or historic side, which share players
# with the clubs; not a user club unless "CPU manages my depth chart",
# [0xE60140], is on: the pass's own test 0x13EC30) it lists each position's healthy players ahead of its injured ones
# in the rank chain (+0x28 bits 10..12) and, for paired positions, the side chain (bits 13..15), keeping each group's
# order. An injured player moved down loses his rank and side locks (+0x52 bits 0..1; returner locks stay), so when he
# is healthy the pass seats him by rating again (and depth locks' release rule frees a clearly worse locked backup).
# When a paired position changed and has three or more healthy players, its healthy rank starter is kept out of side
# rows 0 and 1 (depth locks revision 4's rule: one player never fills two starting slots). Position independent:
# game functions are called through registers. Assemble: as --32 -o x.o; objcopy -O binary -j .text x.o x.bin.
.intel_syntax noprefix
.code32
.text
.global inj_weekly
inj_weekly:
weekly_entry:                   # local alias: a call to a global symbol would leave a relocation
 mov eax, 0x2bdcf0
 call eax
 pushad
 mov eax, 0xc4be0                # league team count
 call eax
 mov ebp, eax
 xor esi, esi
team_loop:
 cmp esi, ebp
 jge team_done
 mov ecx, esi
 mov eax, 0xc4c50                # team at index
 call eax
 mov edi, eax
 test edi, edi
 jz team_next
 cmp dword ptr [edi+0x128], 0       # league clubs only (all-star kind 1, Pro Bowl slots, historic sides)
 jne team_next
 mov ecx, edi
 mov eax, 0x13ec30               # the pass's user-club test
 call eax
 test eax, eax
 jz team_fix
 cmp dword ptr ds:[0xe60140], 0
 je team_next
team_fix:
 call fix_team
team_next:
 inc esi
 jmp team_loop
team_done:
 popad
 ret

# EDI = the team. Frame: [ebp+0..0x103] list (65 players), 0x104 position, 0x108 chain shift, 0x10c changed,
# 0x110 pass, 0x114 next row.
fix_team:
 push ebp
 push esi
 push ebx
 sub esp, 0x118
 mov ebp, esp
 mov dword ptr [ebp+0x104], 0
pos_loop:
 mov dword ptr [ebp+0x10c], 0
 mov dword ptr [ebp+0x108], 10
 call partition
 mov eax, 0x1ec98                # paired positions 3 4 7 10 11 13 14 15 16
 mov ecx, [ebp+0x104]
 bt eax, ecx
 jnc pos_next
 mov dword ptr [ebp+0x108], 13
 call partition
 cmp dword ptr [ebp+0x10c], 0
 je pos_next
 call keep_out
pos_next:
 inc dword ptr [ebp+0x104]
 cmp dword ptr [ebp+0x104], 17
 jb pos_loop
 # An empty long snapper slot (team +0x198, 0xFF) takes the SPECIAL LS: the second center in the rank order. Nothing
 # in the game refills it after the offseason empties it (MC1's season-2 audit: 29 clubs).
 cmp byte ptr [edi+0x198], 0xff
 jne ls_done
 mov dword ptr [ebp+0x104], 12
 mov dword ptr [ebp+0x108], 10
 call build
 cmp ebx, 2
 jb ls_done
 mov edx, [ebp+4]
 xor esi, esi
ls_find:
 movzx eax, byte ptr [edi+0x11c]
 cmp esi, eax
 jae ls_done
 cmp [edi+esi*4], edx
 je ls_set
 inc esi
 jmp ls_find
ls_set:
 mov eax, esi
 mov [edi+0x198], al
ls_done:
 add esp, 0x118
 pop ebx
 pop esi
 pop ebp
 ret

# The players of the position in chain order (value, then roster slot): EBX = count.
build:
 xor ebx, ebx
 xor ecx, ecx
build_v:
 xor esi, esi
build_s:
 movzx eax, byte ptr [edi+0x11c]
 cmp esi, eax
 jae build_vnext
 mov edx, [edi+esi*4]
 test edx, edx
 jz build_snext
 movzx eax, byte ptr [edx+0x35]
 cmp eax, [ebp+0x104]
 jne build_snext
 movzx eax, word ptr [edx+0x28]
 push ecx
 mov ecx, [ebp+0x108]
 shr eax, cl
 pop ecx
 and eax, 7
 cmp eax, ecx
 jne build_snext
 cmp ebx, 65
 jae build_snext
 mov [ebp+ebx*4], edx
 inc ebx
build_snext:
 inc esi
 jmp build_s
build_vnext:
 inc ecx
 cmp ecx, 8
 jb build_v
 ret

# Healthy players ahead of injured ones in the chain [ebp+0x108]; sets [ebp+0x10c] when it moves anyone.
partition:
 call build
 xor esi, esi
 xor ecx, ecx
need_loop:
 cmp esi, ebx
 jae need_none
 mov edx, [ebp+esi*4]
 test byte ptr [edx+0x23], 0x80
 jz need_healthy
 mov cl, 1
 jmp need_next
need_healthy:
 test cl, cl
 jnz need_yes
need_next:
 inc esi
 jmp need_loop
need_none:
 ret
need_yes:
 mov dword ptr [ebp+0x10c], 1
 mov dword ptr [ebp+0x114], 0
 mov dword ptr [ebp+0x110], 0
pass_loop:
 xor esi, esi
seat_loop:
 cmp esi, ebx
 jae pass_next
 mov edx, [ebp+esi*4]
 movzx eax, byte ptr [edx+0x23]
 shr eax, 7
 cmp eax, [ebp+0x110]
 jne seat_next
 test eax, eax
 jz seat_row
 and byte ptr [edx+0x52], 0xfc     # an injured player moved down: rank and side locks off
seat_row:
 mov eax, [ebp+0x114]
 call write_chain
 inc dword ptr [ebp+0x114]
seat_next:
 inc esi
 jmp seat_loop
pass_next:
 inc dword ptr [ebp+0x110]
 cmp dword ptr [ebp+0x110], 2
 jb pass_loop
 ret

# EDX = player, EAX = row (capped at 7), chain [ebp+0x108].
write_chain:
 cmp eax, 7
 jbe write_ok
 mov eax, 7
write_ok:
 push ecx
 push ebx
 mov ecx, [ebp+0x108]
 mov ebx, 7
 shl ebx, cl
 not ebx
 and word ptr [edx+0x28], bx
 shl eax, cl
 or word ptr [edx+0x28], ax
 pop ebx
 pop ecx
 ret

# A paired position that changed: with three or more healthy players its healthy rank starter takes side row 2 when
# he is in side row 0 or 1.
keep_out:
 mov dword ptr [ebp+0x108], 10
 call build
 test ebx, ebx
 jz keep_done
 mov edx, [ebp]
 test byte ptr [edx+0x23], 0x80
 jnz keep_done
 xor ecx, ecx
 xor esi, esi
keep_count:
 cmp esi, ebx
 jae keep_counted
 mov eax, [ebp+esi*4]
 test byte ptr [eax+0x23], 0x80
 jnz keep_count_next
 inc ecx
keep_count_next:
 inc esi
 jmp keep_count
keep_counted:
 cmp ecx, 3
 jb keep_done
 push edx
 mov dword ptr [ebp+0x108], 13
 call build
 pop edx
 xor esi, esi
keep_find:
 cmp esi, 2
 jae keep_done
 cmp [ebp+esi*4], edx
 je keep_move
 inc esi
 jmp keep_find
keep_move:
 mov eax, [ebp+esi*4+4]
 mov [ebp+esi*4], eax
 inc esi
 cmp esi, 2
 jb keep_move
 mov [ebp+8], edx
 xor esi, esi
keep_write:
 cmp esi, ebx
 jae keep_done
 mov edx, [ebp+esi*4]
 mov eax, esi
 call write_chain
 inc esi
 jmp keep_write
keep_done:
 ret

# b780 sub1 (MC1's season-2 finding): entering the regular season of every season after the first, depth charts were
# stale league-wide (54 empty KR1/KR2/PR/K slots, MyCareer holes). The stage advance's last roster change comes from its
# common tail: 0x27EDF0 (0x248687) calls 0x27EB80 on entering stage 8, after the stage-6 case's pass (0x248075) and
# the preseason weeks' passes, and the week sim runs the pass again only after week 1's games. The tail's next call,
# 0x2BFDD0 (0x24868C, the call the week sim makes just before its own pass), now comes here: 0x2BFDD0, then, when the
# advance has reached the regular season (stage [0xE576A4] == 8), the pass with this rule on the final 53. Season 1's
# career starts at stage 8 with no stage advance before week 1, so it is unchanged.
season_tail:
 mov eax, 0x2bfdd0
 call eax
 cmp dword ptr ds:[0xe576a4], 8
 jne season_done
 call weekly_entry
season_done:
 ret
