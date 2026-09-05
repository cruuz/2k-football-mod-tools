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
 # re-lock its final row on exit. The expanded row arm preserves EAX=chain.
 mov dword ptr [esp+0x68],0
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
 mov dword ptr [esp+0x4c],10
 mov dword ptr [esp+0x50],1
field:
 mov dword ptr [esp+0x58],0
 mov dword ptr [esp+0x64],0
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
 bts [esp+0x58],eax
 jmp next_ordinal
unlocked:
 cmp dword ptr [esp+0x44],0
 je save_priority
 mov eax,[esp+0x64]
 cmp ecx,13
 jne cap
 # Retail only seeds the side chain for paired position enums.
 mov edx,0x1ec18
 bt edx,edi
 jc paired_side
 movzx eax,word ptr [esi+0x28]
 shr eax,cl
 and eax,7
 jmp save_priority
paired_side:
 cmp eax,3
 jae cap
 add eax,2
 cmp eax,3
 jb cap
 sub eax,3
cap:
 cmp eax,7
 jbe save_priority
 push 7
 pop eax
save_priority:
 mov [esp+ebx],al
next_ordinal:
 inc dword ptr [esp+0x64]
next_snapshot:
 inc ebx
 jmp snapshot
allocate:
 mov dword ptr [esp+0x60],0
 mov dword ptr [esp+0x5c],0
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
 push 7
 pop eax
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
 mov dword ptr [esp+0x4c],13
 mov dword ptr [esp+0x50],2
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
 mov eax,1
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
fallback=0x242bb0


# Replaces the whole ratings-to-rank stage, after the native pointer sort.
.section .depth_weekly,"ax"
.global rank_stage
rank_stage:
 mov ecx,edi
 call weekly
 jmp 0x2bde70

# The first five bytes retain the rows module's chain-bit patch location.
# The packer uses TEST EAX,EAX for stride 11, TEST AL,1 for stride 13.
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
