/* Original dormant i386 components. EXPERIMENTAL / UNWITNESSED.
 * No retail call site targets these routines. No native file I/O or sim bridge.
 * All exported functions use cdecl and preserve EBX/ESI/EDI/EBP and DF.
 * Caller buffers must be mapped and disjoint; lengths are bounded below.
 */
.intel_syntax noprefix
.code32
.text
.global sb_gate, sb_select, sb_crc, sb_check, sb_save, sb_load, sb_simulate
.global quota_table, code_end

/* uint32 crc(const void *data, uint32 length): standard reflected CRC-32. */
sb_crc:
 push ebx
 push esi
 mov esi, DWORD PTR [esp+12]
 mov ecx, DWORD PTR [esp+16]
 mov eax, -1
crc_byte:
 test ecx, ecx
 jz crc_done
 movzx ebx, BYTE PTR [esi]
 xor eax, ebx
 mov edx, 8
crc_bit:
 shr eax, 1
 jnc crc_next
 xor eax, 0xedb88320
crc_next:
 dec edx
 jnz crc_bit
 inc esi
 dec ecx
 jmp crc_byte
crc_done:
 not eax
 pop esi
 pop ebx
 ret

/* check(blob, bytes): envelope check ONLY. Host Event.from_bytes performs
 * the full semantic/canonical check; a future native load bridge must match it.
 */
sb_check:
 cmp DWORD PTR [esp+8], 16384
 jne check_bad
 mov edx, DWORD PTR [esp+4]
 test edx, edx
 jz check_bad
 cmp edx, 0xffffc000
 ja check_bad
 cmp DWORD PTR [edx], 0x314e4253
 jne check_bad
 cmp DWORD PTR [edx+4], 0x01000001
 jne check_bad
 cmp DWORD PTR [edx+8], 16384
 jne check_bad
 mov eax, DWORD PTR [edx+16]
 dec eax
 cmp eax, 3
 ja check_bad
 cmp DWORD PTR [edx+20], 127
 ja check_bad
 cmp DWORD PTR [edx+28], 2
 ja check_bad
 cmp WORD PTR [edx+80], 512
 ja check_bad
 movzx eax, WORD PTR [edx+82]
 cmp eax, 106
 je check_crc
 test eax, eax
 jnz check_bad
 cmp DWORD PTR [edx+16], 4
 jne check_bad
check_crc:
 push edx
 push 16368
 add edx, 16
 push edx
 call sb_crc
 add esp, 8
 pop edx
 cmp eax, DWORD PTR [edx+12]
 sete al
 movzx eax, al
 ret
check_bad:
 xor eax, eax
 ret

/* seal(ECX blob), private. */
seal:
 push ecx
 push 16368
 add ecx, 16
 push ecx
 call sb_crc
 add esp, 8
 pop ecx
 mov DWORD PTR [ecx+12], eax
 ret

/* gate(blob, year, stage, remaining_days, untouched_hours)
 * Returns 1=hold Combine, 0=continue, -1=invalid/stale. Does not call retail
 * week/day routines. Complete/skipped remains terminal for the whole year.
 */
sb_gate:
 push ebx
 mov ebx, DWORD PTR [esp+8]
 push 16384
 push ebx
 call sb_check
 add esp, 8
 test eax, eax
 jz gate_bad
 mov eax, DWORD PTR [esp+12]
 cmp eax, DWORD PTR [ebx+20]
 jne gate_bad
 mov edx, DWORD PTR [esp+16]
 lea eax, [edx-1]
 cmp eax, 8
 ja gate_bad
 cmp DWORD PTR [esp+20], 4
 ja gate_bad
 cmp DWORD PTR [esp+24], 1
 ja gate_bad
 cmp DWORD PTR [ebx+16], 3
 jae gate_pass
 cmp edx, 4
 ja gate_skip
 jb gate_recover
 cmp DWORD PTR [esp+20], 4
 jb gate_skip
 cmp DWORD PTR [esp+24], 0
 je gate_skip
gate_recover:
 cmp DWORD PTR [ebx+16], 2
 jne gate_result
 mov DWORD PTR [ebx+16], 1
 mov ecx, ebx
 call seal
gate_result:
 xor eax, eax
 cmp DWORD PTR [esp+16], 4
 sete al
 pop ebx
 ret
gate_skip:
 mov DWORD PTR [ebx+16], 4
 mov ecx, ebx
 call seal
gate_pass:
 xor eax, eax
 pop ebx
 ret
gate_bad:
 mov eax, -1
 pop ebx
 ret

/* select(rows, count, seed, scheme, scratch_event)
 * Input rows: u32 primary_index, u8 position, u8 flags, u8 owned, u8 zero.
 * Input must be strictly sorted and unique, at most 4096 rows. Scan the entire
 * supplied primary snapshot; accept allocated, undrafted, unowned prospects.
 * Writes only scratch_event+80..83 and +256..16383. Does NOT publish live state.
 * Returns eligible count, -1 malformed, -2 shortage. Host must validate identity
 * and ownership while producing the snapshot; this is not a live ROST getter.
 */
sb_select:
 push ebp
 mov ebp, esp
 push ebx
 push esi
 push edi
 pushfd
 sub esp, 128
 cld
 mov ebx, DWORD PTR [ebp+12]
 cmp ebx, 4096
 ja select_bad
 mov eax, DWORD PTR [ebp+20]
 cmp eax, 2
 ja select_bad
 mov DWORD PTR [ebp-24], eax
 mov eax, DWORD PTR [ebp+16]
 mov DWORD PTR [ebp-20], eax
 mov esi, DWORD PTR [ebp+8]
 test esi, esi
 jz select_bad
 mov edi, DWORD PTR [ebp+24]
 test edi, edi
 jz select_bad
 mov DWORD PTR [ebp-28], edi
 add edi, 256
 xor eax, eax
 mov ecx, 16128/4
 rep stosd
 lea edi, [ebp-144]
 mov ecx, 17
 rep stosd
 mov DWORD PTR [ebp-32], 0
 mov DWORD PTR [ebp-36], -1
select_scan:
 test ebx, ebx
 jz select_positions
 mov eax, DWORD PTR [esi]
 cmp eax, 4095
 ja select_bad
 cmp DWORD PTR [ebp-36], -1
 je select_first
 cmp eax, DWORD PTR [ebp-36]
 jbe select_bad
select_first:
 mov DWORD PTR [ebp-36], eax
 movzx edx, BYTE PTR [esi+4]
 cmp edx, 16
 ja select_bad
 cmp BYTE PTR [esi+6], 1
 ja select_bad
 cmp BYTE PTR [esi+7], 0
 jne select_bad
 movzx ecx, BYTE PTR [esi+5]
 and ecx, 0x34
 cmp ecx, 0x14
 jne select_next
 cmp BYTE PTR [esi+6], 0
 jne select_next
 cmp DWORD PTR [ebp-24], 2
 jne select_accept
 cmp edx, 10
 je select_bad
select_accept:
 mov ecx, DWORD PTR [ebp-32]
 cmp ecx, 512
 jae select_bad
 mov edi, DWORD PTR [ebp-28]
 lea edi, [edi+256+ecx*4]
 mov WORD PTR [edi], ax
 mov BYTE PTR [edi+2], dl
 inc DWORD PTR [ebp-144+edx*4]
 inc DWORD PTR [ebp-32]
select_next:
 add esi, 8
 dec ebx
 jmp select_scan
select_positions:
 mov DWORD PTR [ebp-40], 0
 mov DWORD PTR [ebp-44], 0
 mov DWORD PTR [ebp-48], 0
select_position:
 mov ebx, DWORD PTR [ebp-40]
 cmp ebx, 17
 jae select_done
 movzx eax, BYTE PTR [quota_table+ebx]
 cmp DWORD PTR [ebp-24], 2
 jne select_quota
 cmp ebx, 10
 jne select_lb
 xor eax, eax
select_lb:
 cmp ebx, 11
 jne select_quota
 mov eax, 7
select_quota:
 add eax, eax
 mov DWORD PTR [ebp-56], eax
 test eax, eax
 jz select_position_next
 mov ecx, DWORD PTR [ebp-144+ebx*4]
 cmp ecx, eax
 jb select_short
 mov DWORD PTR [ebp-60], ecx
 imul eax, ebx, 0x9e3779b9
 xor eax, DWORD PTR [ebp-20]
 xor edx, edx
 div ecx
 mov DWORD PTR [ebp-64], edx
 mov DWORD PTR [ebp-52], 0
select_pick:
 mov eax, DWORD PTR [ebp-52]
 cmp eax, DWORD PTR [ebp-56]
 jae select_position_next
 add eax, DWORD PTR [ebp-64]
 cmp eax, DWORD PTR [ebp-60]
 jb select_find_start
 sub eax, DWORD PTR [ebp-60]
select_find_start:
 mov esi, DWORD PTR [ebp-28]
 add esi, 256
 mov ecx, DWORD PTR [ebp-32]
select_find:
 test ecx, ecx
 jz select_bad
 cmp BYTE PTR [esi+2], bl
 jne select_find_next
 test eax, eax
 jz select_found
 dec eax
select_find_next:
 add esi, 4
 dec ecx
 jmp select_find
select_found:
 mov edx, DWORD PTR [ebp-20]
 xor edx, ebx
 xor edx, DWORD PTR [ebp-52]
 and edx, 1
 mov eax, DWORD PTR [ebp-44]
 test edx, edx
 jnz select_home
 inc DWORD PTR [ebp-44]
 jmp select_row
select_home:
 mov eax, DWORD PTR [ebp-48]
 inc DWORD PTR [ebp-48]
 add eax, 53
select_row:
 imul eax, eax, 80
 mov edi, DWORD PTR [ebp-28]
 lea edi, [edi+eax+2304]
 mov ax, WORD PTR [esi]
 mov WORD PTR [edi], ax
 mov BYTE PTR [edi+2], bl
 mov BYTE PTR [edi+3], dl
 inc DWORD PTR [ebp-52]
 jmp select_pick
select_position_next:
 inc DWORD PTR [ebp-40]
 jmp select_position
select_done:
 mov edi, DWORD PTR [ebp-28]
 mov eax, DWORD PTR [ebp-32]
 mov WORD PTR [edi+80], ax
 mov WORD PTR [edi+82], 106
 jmp select_exit
select_short:
 mov eax, -2
 jmp select_exit
select_bad:
 mov eax, -1
select_exit:
 add esp, 128
 popfd
 pop edi
 pop esi
 pop ebx
 pop ebp
 ret

/* disjoint external buffer check, EDX=buffer. Reject wrap and overlap with
 * the entire owned 64 KiB workspace. Buffer mapping is the caller's contract.
 */
external:
 test edx, edx
 jz external_bad
 cmp edx, 0xffffc000
 ja external_bad
 lea eax, [edx+16384]
 cmp eax, OFFSET state_data
 jbe external_good
 cmp edx, OFFSET state_data+65536
 jb external_bad
external_good:
 mov eax, 1
 ret
external_bad:
 xor eax, eax
 ret

/* save(buffer, bytes): component export, not a native save file operation. */
sb_save:
 cmp DWORD PTR [esp+8], 16384
 jne check_bad
 mov edx, DWORD PTR [esp+4]
 call external
 test eax, eax
 jz check_bad
 push 16384
 push OFFSET state_data
 call sb_check
 add esp, 8
 test eax, eax
 jz check_bad
 push esi
 push edi
 pushfd
 cld
 mov edi, DWORD PTR [esp+16]
 mov esi, OFFSET state_data
 mov ecx, 4096
 rep movsd
 popfd
 pop edi
 pop esi
 mov eax, 1
 ret

/* load(buffer, bytes, identity48, year): rejects mismatched franchise/class,
 * normalizes interrupted runs to pending, and publishes only after checks.
 * identity48 is franchise UUID followed by full class SHA-256. This is only
 * the envelope transport component, not the full semantic native load proof.
 */
sb_load:
 push ebx
 mov ebx, DWORD PTR [esp+8]
 mov edx, ebx
 call external
 test eax, eax
 jz load_bad
 push DWORD PTR [esp+12]
 push ebx
 call sb_check
 add esp, 8
 test eax, eax
 jz load_bad
 mov eax, DWORD PTR [esp+20]
 cmp eax, DWORD PTR [ebx+20]
 jne load_bad
 mov edx, DWORD PTR [esp+16]
 test edx, edx
 jz load_bad
 xor ecx, ecx
load_identity:
 mov eax, DWORD PTR [edx+ecx]
 cmp eax, DWORD PTR [ebx+ecx+32]
 jne load_bad
 add ecx, 4
 cmp ecx, 48
 jb load_identity
 push esi
 push edi
 pushfd
 cld
 mov esi, ebx
 mov edi, OFFSET state_data
 mov ecx, 4096
 rep movsd
 popfd
 pop edi
 pop esi
 cmp DWORD PTR [state_data+16], 2
 jne load_done
 mov DWORD PTR [state_data+16], 1
 mov ecx, OFFSET state_data
 call seal
load_done:
 mov eax, 1
 pop ebx
 ret
load_bad:
 xor eax, eax
 pop ebx
 ret

/* Deliberate refusal. There is no safe simulator bridge in this revision. */
sb_simulate:
 mov eax, -6
 ret

code_end:
quota_table:
 .byte 3,1,1,6,5,2,2,3,2,3,4,3,2,4,4,4,4
