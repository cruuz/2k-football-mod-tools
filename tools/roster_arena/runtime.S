/* Handwritten ABI adapters; originals displaced by entry hooks. */
.intel_syntax noprefix
.section .text.retail_fa_add,"ax",@progbits
.global retail_fa_add
retail_fa_add:
 mov eax, DWORD PTR [ecx]
 cmp eax, 0x9c4
 jmp 0x242567
.section .text.retail_clear,"ax",@progbits
.global retail_clear
retail_clear:
 push ebx
 push esi
 mov esi, ecx
 movzx ebx, BYTE PTR [esi+0x35]
 jmp 0xE64D8
.section .text.retail_rollover,"ax",@progbits
.global retail_rollover
retail_rollover:
 push ebx
 push ebp
 push esi
 push edi
 call 0xC4EB0
 jmp 0x247B49
.section .text.retire_player,"ax",@progbits
.global retire_player
retire_player:
 push edi
 mov edi, ecx
 push 0
 call 0x2BCF90
 pop edi
 ret
.section .text.size_adapter,"ax",@progbits
.global size_adapter
size_adapter:
 mov edx, DWORD PTR [esp+4]
 push esi
 push edi
 push ecx
 mov ecx, eax
 call arena_size
 ret 4
.section .note.GNU-stack,"",@progbits

.section .text.retail_export,"ax",@progbits
.global retail_export
retail_export:
 sub esp, 0x1c
 mov eax, ecx
 jmp 0xC0B95
.section .text.retail_import,"ax",@progbits
.global retail_import
retail_import:
 sub esp, 0x130
 jmp 0xC1036
.section .text.ir_restore,"ax",@progbits
.global ir_restore
ir_restore:
 call ps_ir_append
 test eax, eax
 jz 1f
 mov DWORD PTR [esi], 0
1:
 ret
.section .text.offer_limit,"ax",@progbits
.global offer_limit
offer_limit:
 mov ecx, DWORD PTR [esi+4]
 jmp ps_limit
.section .text.draft_limit,"ax",@progbits
.global draft_limit
draft_limit:
 mov eax, esi
 jmp capacity_flags
.section .text.capacity_flags,"ax",@progbits
.global capacity_flags
capacity_flags:
 push eax
 mov ecx, eax
 call ps_limit
 pop edx
 movzx ecx, BYTE PTR [edx+0x11c]
 cmp ecx, eax
 ret
.section .text.cpu_sign_guard,"ax",@progbits
.global cpu_sign_guard
cpu_sign_guard:
 pushad
 mov ecx, DWORD PTR [esp+36]
 call ps_room
 test eax, eax
 jz 1f
 popad
 sub esp, 0x114
 jmp 0x322BB6
1:
 popad
 xor eax, eax
 ret 16
.section .text.pending_sign_guard,"ax",@progbits
.global pending_sign_guard
pending_sign_guard:
 pushad
 mov ecx, DWORD PTR [eax+4]
 call ps_room
 test eax, eax
 jz 1f
 popad
 push ecx
 push edi
 mov edi, eax
 push 1
 jmp 0x323B36
1:
 popad
 ret
.section .text.draft_sign_guard,"ax",@progbits
.global draft_sign_guard
draft_sign_guard:
 pushad
 mov ecx, edx
 call ps_room
 test eax, eax
 jz 1f
 popad
 push esi
 push edi
 mov edi, edx
 mov edx, DWORD PTR [esp+12]
 jmp 0x325B58
1:
 popad
 ret 4
.section .text.trade_guard,"ax",@progbits
.global trade_guard
trade_guard:
 pushad
 call ps_trade_room
 test eax, eax
 jz 1f
 popad
 sub esp, 8
 mov eax, DWORD PTR [esp+12]
 jmp 0x2BC677
1:
 popad
 xor eax, eax
 ret 4

.section .text.count_adapter,"ax",@progbits
.global count_adapter
count_adapter:
 mov ecx, eax
 jmp arena_count
.section .text.remove_adapter,"ax",@progbits
.global remove_adapter
remove_adapter:
 mov edx, ecx
 mov ecx, eax
 jmp arena_remove
.section .text.retail_remove,"ax",@progbits
.global retail_remove
retail_remove:
 mov eax, ecx
 mov ecx, edx
 movzx edx, BYTE PTR [eax+0x11c]
 jmp 0xc3a97
.section .text.retail_load,"ax",@progbits
.global retail_load
retail_load:
 push esi
 mov esi, ecx
 test esi, esi
 jmp 0xc2045
.section .text.retail_save,"ax",@progbits
.global retail_save
retail_save:
 mov eax, DWORD PTR [0xb72918]
 jmp 0xc1f95
.section .text.created_adapter,"ax",@progbits
.global created_adapter
created_adapter:
 mov ecx, eax
 jmp arena_created

/* b778 fa6: capacity franchise save-list admission. The retail compare at 0x16ABCF only accepts
 * the exact capacity total size, so a pre-capacity 720,044-byte save reads as DAMAGED. Four real
 * sizes are admitted (720044/720172/724140/724268); 720044/724140 differ only in bit 8 from their
 * 128-byte MyCareer-footer forms, so one masked compare covers each pair. The handler's expected
 * size stays in EAX; the stack still carries 16AB70's pushed ESI. */
.section .text.capacity_admission,"ax",@progbits
.global capacity_admission
capacity_admission:
 cmp DWORD PTR [esi+0xbdc1cc], eax
 je 1f
 cmp DWORD PTR [esi+0xbdc1cc], 0xafcac
 je 1f
 cmp DWORD PTR [esi+0xbdc1cc], 0xafd2c
 je 1f
 mov eax, 1
 jmp 2f
1:
 xor eax, eax
2:
 pop esi
 ret
/* b778 fa6: the franchise load path asks BFE50 for the wrapper size after C2040. On a capacity
 * build BFE50 answers the capacity wrapper (0xB0040), but an old buffer still stores its season
 * and front-office blocks at the old offsets. Return the source wrapper size (declared + 0x20)
 * for an old ROST version 0/1 wrapper; a capacity wrapper falls through to BFE50 unchanged.
 * ESI is the file buffer and the wrapper starts at +0x2E0. */
.section .text.capacity_load_size,"ax",@progbits
.global capacity_load_size
capacity_load_size:
 mov eax, DWORD PTR [esi+0x2e0+4]
 cmp eax, 0x91020
 je 1f
 cmp eax, 0x92020
 je 2f
 jmp 0xbfe50
1:
 mov eax, 0x91040
 ret
2:
 mov eax, 0x92040
 ret
