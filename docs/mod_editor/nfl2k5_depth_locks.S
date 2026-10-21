.intel_syntax noprefix
.code32
# The executable module embeds the linked bytes; tests reproduce them with
# GNU as/ld/objcopy without requiring an assembler in the shipped application.
# All sections below replace their original functions/blocks in place.
# Common frame: pushad + 0x6c bytes. [0..64] snapshot sort keys; +44 mode;
# +4c shift (10/13); +50 lock bit; +54 count; +58 reserved-row bitset;
# +5c next free row; +60 priority; +64 ordinal; +68 pending bench lock.
# Saved ESI/EAX/EDX and caller return are at +70/+88/+80/+8c respectively.
# EBP=team, EDI=position enum, EBX=roster index, ESI=record.
.section .depth_compact,"ax"
.global compact
compact:
 xor edx,edx
 jmp common
weekly:
 push 1
 pop edx
common:
 pushad
 sub esp,0x6c
 mov ebp,ecx
 # Only successful bench promotions call from these three return addresses.
 # ESI is the selected record. Clear its old chain lock for compaction and
 # re-lock its final row on exit. Both layouts keep unit stride 11.
 # Retail calls at 0x244452 (side) / 0x244471 (rank); final SPECIAL calls
 # at 0x24445f and preserves EAX=encoded chain (0..4). Its return pin is
 # still 0x244464 after relocating the 46-record table to 0xee3000.
 and dword ptr [esp+0x68],0
 mov eax,[esp+0x8c]
 push 2
 pop edx
 cmp eax,0x244457
 je bench
 dec edx
 cmp eax,0x244476
 je bench
 cmp eax,0x244464
 jne no_bench
 mov edx,[esp+0x88]
 and edx,1
 inc edx
bench:
 mov [esp+0x68],edx
 mov esi,[esp+0x70]
 not edx
 and [esi+0x52],dl
no_bench:
 mov edx,[esp+0x80]
 mov [esp+0x44],edx
 movzx eax,byte ptr [ebp+0x11c]
 cmp eax,65
 ja done
 mov [esp+0x54],eax
 xor edi,edi
position:
 push 10
 pop dword ptr [esp+0x4c]
 push 1
 pop dword ptr [esp+0x50]
field:
 # b777 (mc5): +60 counts this chain's locks, +64 its players; close_holes
 # rebuilds the reserved rows (+58) from the seats.
 xor eax,eax
 mov [esp+0x60],eax
 mov [esp+0x64],eax
 xor ebx,ebx
snapshot:
 cmp ebx,[esp+0x54]
 jae allocate
 mov byte ptr [esp+ebx],255
 mov esi,[ebp+ebx*4]
 mov eax,edi
 cmp byte ptr [esi+0x35],al
 jne next_snapshot
 mov ecx,[esp+0x4c]
 movzx eax,word ptr [esi+0x28]
 shr eax,cl
 and eax,7
 mov edx,[esp+0x50]
 test byte ptr [esi+0x52],dl
 jz unlocked
 # b777 (mc5): tag the lock with its row; close_holes seats it.
 or al,0x40
seat_as_lock:
 mov [esp+ebx],al
 inc dword ptr [esp+0x60]
 jmp next_ordinal
unlocked:
 # EAX is this chain's stored row (the screen's priority).
 cmp dword ptr [esp+0x44],0
 je save_priority
 cmp ecx,13
 jne rank_ordinal
 # Retail only seeds the side chain for paired position enums.
 mov edx,0x1ec98
 bt edx,edi
 jnc save_priority
 # b777 (dl3): retail maps the sorted ordinal 0/1/2 to side rows 2/0/1, so
 # the rank-chain starter (ordinal 0) is never a side starter. With locks the
 # rank starter need not be ordinal 0 (a better locked player can sit at rank
 # 3), and an unlocked rank-0 player took side row 0 too (Noah's save: BUF
 # Rousseau, BAL Wagner, ...: one player in two unit slots, which the exit
 # check 0x243B50 refuses). Map the rank row this pass just assigned
 # instead; identical to retail when ranks equal ordinals (no locks).
 # Revision 4 (b777 dl4): rank rows 1/2 take side priorities 0/1 and rows
 # 3..7 keep their number, as before. The unlocked rank starter (row 0) is
 # no longer an unlocked priority 2: priorities only order the unlocked
 # players, so a side row 0/1 a lock left behind could still go to him
 # (reviewer ur1: a signing at rank 0 and side 0 when he was the only
 # unlocked player, or the only one below a released starter). He is now
 # seated like a side lock at retail's row 2 (tag 0x42): close_holes counts
 # him out of the unlocked rows, keeps row 2 for him when the rows above are
 # filled and otherwise seats him last (should_defer), so with 3+ players he
 # never takes side row 0 or 1 and no row is left blank. Without locks this
 # gives revision 3's rows (his retail-mapped side row 2, or row 1/0 when the
 # position has only 2/1 players).
 mov eax,[esi+0x28]
 shr eax,10
 and eax,7
 jz side_starter
 cmp al,3
 jae save_priority
 dec eax
 jmp save_priority
side_starter:
 mov al,0x42
 jmp seat_as_lock
rank_ordinal:
 mov eax,[esp+0x64]
cap:
 cmp eax,7
 jbe save_priority
 # EAX is below 256 here (an ordinal or row): the byte store is enough.
 mov al,7
save_priority:
 mov [esp+ebx],al
next_ordinal:
 inc dword ptr [esp+0x64]
next_snapshot:
 inc ebx
 jmp snapshot
allocate:
 # b777 (mc5): locked rows no longer leave permanent holes; see close_holes.
 call close_holes
priority:
 xor ebx,ebx
candidate:
 cmp ebx,[esp+0x54]
 jae next_priority
 mov eax,[esp+0x60]
 cmp [esp+ebx],al
 jne next_candidate
 mov eax,[esp+0x5c]
free_row:
 cmp eax,7
 jb test_row
 mov al,7
 jmp assign
test_row:
 bt [esp+0x58],eax
 jnc assign
 inc eax
 jmp free_row
assign:
 mov [esp+0x5c],eax
 inc dword ptr [esp+0x5c]
 mov esi,[ebp+ebx*4]
 mov ecx,[esp+0x4c]
 shl eax,cl
 mov edx,7
 shl edx,cl
 xor ax,[esi+0x28]
 and eax,edx
 xor [esi+0x28],ax
next_candidate:
 inc ebx
 jmp candidate
next_priority:
 inc dword ptr [esp+0x60]
 cmp dword ptr [esp+0x60],8
 jb priority
 cmp dword ptr [esp+0x4c],13
 je next_position
 mov byte ptr [esp+0x4c],13
 mov byte ptr [esp+0x50],2
 jmp field
next_position:
 inc edi
 cmp edi,17
 jb position
 cmp dword ptr [esp+0x44],0
 jne done
 mov esi,ebp
 xor eax,eax
 mov ecx,254
 call fallback
 mov [esi+0x195],al
 push 1
 pop eax
 mov ecx,254
 call fallback
 mov [esi+0x196],al
 xor eax,eax
 mov ecx,253
 call fallback
 mov [esi+0x199],al
 mov ebx,[esp+0x54]
restore:
 dec ebx
 js done
 mov esi,[ebp+ebx*4]
 mov al,[esi+0x52]
 test al,4
 jz kr2
 mov [ebp+0x195],bl
kr2:
 test al,8
 jz pr
 mov [ebp+0x196],bl
pr:
 test al,16
 jz restore
 mov [ebp+0x199],bl
 jmp restore
done:
 mov eax,[esp+0x68]
 test eax,eax
 jz epilogue
 mov esi,[esp+0x70]
 or [esi+0x52],al
epilogue:
 add esp,0x6c
 popad
 ret

# b777 (mc5), called by close_holes as a lock is about to take row EDX of the
# side chain: CF=1 when that player also starts the rank chain (rank 0) and
# the row is a side-chain starter (0 or 1). He is then seated last (row tag 7)
# so one player never fills two starting slots (the screen's exit check
# 0x243B50 refuses that; Discord 10/18: Luvu SAM+MIKE, Highsmith both EDGEs).
# Revision 4 (dl4): the deferred player is seated in an extra pass (row tag 8)
# after every lock of row 7, not among them in roster order (a two-player
# position with the other lock at row 7 gave him side row 0 again).
should_defer:
 cmp edx,2
 jae keep_seat
 cmp esi,8
 je keep_seat
 cmp byte ptr [edi+0x4c],13
 jne keep_seat
 mov eax,[ebp+ebx*4]
 test byte ptr [eax+0x29],0x1c
 jnz keep_seat
 stc
 ret
keep_seat:
 clc
 ret
fallback=0x242bb0


# Revision 3 (b777, job dl3; Noah 10/20: "Do new players with high overalls
# that are signed in free agency become starters if they're the best overall?").
# The 2026 roster refresh rank+side locks almost every club player, so the
# weekly rank stage kept a locked incumbent in his row even when a much better
# unlocked teammate (a free agent signing, trade or draft pick) joined. This
# replaces the native weekly pointer sort of CPU-run clubs (0x2BDD31..0x2BDDE0)
# with the same exchange sort (same compares, same 0xC3D70 stores, same order;
# the last index's self-compare is new and never swaps) plus a release rule:
# when an index is final it is the best remaining player of its position under
# the native sort rating 0x246D80 (edx=1), so the first unlocked player of a
# position seen is that position's best unlocked player. A rank-locked player
# whose rating plus 0.03 (3 overall points) is not above that best unlocked
# rating loses his rank and side locks (bits 0..1, kept cleared), and the rank
# stage that follows seats him and the better player by the native order.
# Returner locks (bits 2..4) stay. User clubs never reach this code (the
# native user-club skip above it). The table of 17 best ratings and a scratch
# float live in 19 pushed dwords (the outer index too); the native frame
# slots are not used by this sort.
.section .depth_sort,"ax"
.global sort
sort:
 # [esp] scratch rating, [esp+4+4*pos] best unlocked rating of pos (0 = none
 # yet), [esp+0x48] outer index; all start at zero. EBX inner index, EBP its
 # record, ESI the outer record, EDI the team.
 push 19
 pop ecx
sort_zero:
 push 0
 loop sort_zero
 xor ebx,ebx
sort_inner:
 cmp [edi+0x11c],bl
 jbe sort_settle
 mov eax,[esp+0x48]
 mov esi,[edi+eax*4]
 mov ebp,[edi+ebx*4]
 mov al,[esi+0x35]
 cmp al,[ebp+0x35]
 jne sort_next
 mov ecx,esi
 call sort_rate
 fstp dword ptr [esp]
 mov ecx,ebp
 call sort_rate
 fcomp dword ptr [esp]
 fnstsw ax
 sahf
 jbe sort_next
 mov ecx,edi
 push ebx
 mov edx,esi
 call 0xc3d70
 push dword ptr [esp+0x48]
 mov edx,ebp
 call 0xc3d70
sort_next:
 inc ebx
 jmp sort_inner
sort_settle:
 # The inner index reached the count: the outer index did too when equal.
 mov eax,[esp+0x48]
 cmp eax,ebx
 je sort_done
 # roster[outer] is now final: the best remaining player of his position.
 mov esi,[edi+eax*4]
 movzx eax,byte ptr [esi+0x35]
 cmp al,16
 ja sort_step
 lea ebp,[esp+eax*4+4]
 mov ecx,esi
 call sort_rate
 test byte ptr [esi+0x52],1
 jnz sort_locked
 cmp dword ptr [ebp],0
 jne sort_drop
 fst dword ptr [ebp]
sort_drop:
 fstp st(0)
 jmp sort_step
sort_locked:
 # 0x4F0F48 is the retail constant 0.03f (3 overall points).
 fadd dword ptr [0x4f0f48]
 fcomp dword ptr [ebp]
 fnstsw ax
 sahf
 ja sort_step
 and byte ptr [esi+0x52],0xfc
sort_step:
 inc dword ptr [esp+0x48]
 mov ebx,[esp+0x48]
 jmp sort_inner
sort_rate:
 push 1
 pop edx
 jmp 0x246d80
sort_done:
 add esp,0x4c

# Replaces the whole ratings-to-rank stage, after the native pointer sort.
.section .depth_weekly,"ax"
.global rank_stage
rank_stage:
 mov ecx,edi
 call weekly
 jmp 0x2bde70

# b777 (mc5, Noah 10/20: blank TEN RB1 in MyCareer, then a freeze). Every club
# player on the 2026 roster is rank+side locked, so when a locked starter left
# (contract, trade, release) his row stayed reserved by nobody and the depth
# chart showed a blank starter. The snapshot now tags each locked player of
# this position with 0x40|row instead of reserving the row. Here, in row
# order (then roster order), each locked player keeps his row while unlocked
# players can still fill the rows above it, otherwise he moves up; the
# reserved-row set is rebuilt from the seats. Unchanged when no hole exists;
# duplicate locks get distinct rows. Also zeroes the allocator's priority and
# next-row words (the two stores this call replaced). Frame F = EDI = ESP+0x24
# after PUSHAD: F+i tags (0..7 unlocked priority, 0x40|row locked, 0xFE seated,
# 0xFF other position), F+4c shift, F+54 roster count, F+58 reserved rows,
# F+5c next row, F+60 the snapshot's lock count, F+64 its player count and
# then the unlocked rows left. On the side chain, a lock that also starts the
# rank chain is not seated in side row 0 or 1 (should_defer, compactor tail).
close_holes:
 pushad
 lea edi,[esp+0x24]
 mov eax,[edi+0x64]
 sub eax,[edi+0x60]
 mov [edi+0x64],eax
 xor eax,eax
 mov [edi+0x5c],eax
 mov [edi+0x58],eax
 xor esi,esi
row_pass:
 xor ebx,ebx
locked_scan:
 cmp ebx,[edi+0x54]
 jae next_row
 lea edx,[esi+0x40]
 cmp [edi+ebx],dl
 jne next_locked
keep_room:
 mov edx,[edi+0x5c]
 cmp esi,edx
 jbe seat
 cmp dword ptr [edi+0x64],0
 je seat
 dec dword ptr [edi+0x64]
 inc dword ptr [edi+0x5c]
 jmp keep_room
seat:
 call should_defer
 jnc seat_cap
 mov byte ptr [edi+ebx],0x48
 jmp next_locked
seat_cap:
 cmp edx,7
 jbe seat_row
 mov dl,7
seat_row:
 bts [edi+0x58],edx
 inc dword ptr [edi+0x5c]
 mov byte ptr [edi+ebx],0xfe
 mov eax,[ebp+ebx*4]
 # Revision 4 (dl4): write the seat into the chain's 3-bit field directly
 # (rotate it to bits 0..2, replace, rotate back). The seated player's field
 # need not equal his tag row: a deferred player, or the unlocked rank
 # starter seated as a side lock at row 2.
 mov ecx,[edi+0x4c]
 ror word ptr [eax+0x28],cl
 and byte ptr [eax+0x28],0xf8
 or [eax+0x28],dl
 rol word ptr [eax+0x28],cl
next_locked:
 inc ebx
 jmp locked_scan
next_row:
 inc esi
 cmp esi,9
 jb row_pass
 xor eax,eax
 mov [edi+0x5c],eax
 mov [edi+0x60],eax
 popad
 ret

# The first five bytes retain the rows module's chain-bit patch location.
# The packer uses TEST EAX,EAX for retail, TEST AL,1 for SPECIAL (stride 11).
.section .depth_swap,"ax"
.global swap
swap:
 push edi
 xor edi,edi
 test al,1
 mov edx,0x1c00
 mov eax,1
 jz swap_fields
 mov edx,0xe000
 mov eax,2
swap_fields:
 or [ecx+0x52],al
 or [esi+0x52],al
 movzx edi,word ptr [ecx+0x28]
 xor di,[esi+0x28]
 and edi,edx
 xor [esi+0x28],di
 xor [ecx+0x28],di
 pop edi
 ret 4

# b777 (mc5): the detail list's ratings bars (FUN_00242E00) divide 10000 by
# the top row's three ratings, stored only when the top row has a player.
# With an empty top row the first divisor was 0 and the next row raised #DE
# (STATUS_INTEGER_DIVIDE_BY_ZERO at 0x242E53): Noah's frozen depth chart.
# An empty top row now stores 1s (the native floor) before returning.
panel_empty:
 test esi,esi
 jnz panel_done
 push 1
 pop eax
 mov [0xc174c4],eax
 mov [0xc174c8],eax
 mov [0xc174cc],eax
panel_done:
 jmp 0x242f10

# b777 (mc5): the weekly auto-depth skips user-controlled clubs (unless CPU
# management is on). A MyCareer club is one, but the league still moves its
# players (contracts, trades, cuts). Give such a club the screen compactor's
# pass (order kept, holes closed) instead of nothing, then skip it as before.
human_compact:
 mov ecx,edi
 call compact
 jmp 0x2bdfd4

# The weekly auto-depth's user-club skip (retail 0F84 to 0x2BDFD4).
.section .depth_human,"ax"
.global human_branch
human_branch:
 je human_compact

# The ratings panel's empty-row branch (retail 0F84 to 0x242F10).
.section .depth_panel,"ax"
.global panel_branch
panel_branch:
 je panel_empty

# Only the confirmed KR selection arm; EDI=team, ESI=selected player.
# Clear previous KR claims, transfer previous KR1 to KR2 and mark new KR1.
.section .depth_kr,"ax"
.global set_kr
set_kr:
 pushad
 movzx edx,byte ptr [edi+0x195]
 mov [edi+0x196],dl
 xor eax,eax
kr_loop:
 cmp al,[edi+0x11c]
 jae kr_done
 mov ebx,[edi+eax*4]
 and byte ptr [ebx+0x52],0xf3
 cmp eax,edx
 jne kr_selected
 or byte ptr [ebx+0x52],8
kr_selected:
 cmp ebx,esi
 jne kr_next
 mov [edi+0x195],al
 or byte ptr [ebx+0x52],4
kr_next:
 inc eax
 jmp kr_loop
kr_done:
 popad
 jmp 0x244499

.section .depth_pr,"ax"
.global set_pr
set_pr:
 pushad
 xor eax,eax
pr_loop:
 cmp al,[edi+0x11c]
 jae pr_done
 mov edx,[edi+eax*4]
 and byte ptr [edx+0x52],0xef
 cmp edx,esi
 jne pr_next
 mov [edi+0x199],al
 or byte ptr [edx+0x52],16
pr_next:
 inc eax
 jmp pr_loop
pr_done:
 popad
 jmp 0x244499

# Native roster removal, after its successful index guard. Release/trade/IR
# membership changes discard assignments that belong to the old roster.
# Preserve unowned high pad bits and the original contract-bit clear.
.section .depth_remove,"ax"
.global remove_locks
remove_locks:
 mov edx,[eax+ecx*4]
 push esi
 and byte ptr [edx+0x25],0x1f
 and byte ptr [edx+0x52],0xe0
 dec byte ptr [eax+0x11c]
 movzx edx,byte ptr [eax+0x11c]
