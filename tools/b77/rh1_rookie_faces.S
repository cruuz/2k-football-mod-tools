# rookie faces: replaces the class generator's skin/face draw (0xE67EA) and portrait pick (0xE7019) in FUN_000e6780
# Linked at 0xE67EA. Region A = 0xE67EA..0xE686E (130 bytes), region B = 0xE7019..0xE7117 (254 bytes).
.intel_syntax noprefix
.set D, 0x4F4F40          # tables (retail generic-portrait range table, 0x4F4F40..0x4F5138, 504 bytes)
.set ROSTER, 0xB72918     # -> live roster object
.set RNG, 0xE5FCA0
.set RAND, 0x48B50        # u32 rand(ecx = RNG)
.set RESUME, 0xE686E      # retail weight code after the skin/face draw
.set POS, D+0x00
.set FIRSTBAND, D+0x14
.set LASTCODE, D+0x34
.set SIG, D+0x38
.set TCB, D+0x58
.set TCO, D+0x5C
.set LEANMAX, D+0x60
.set HEAVYMIN, D+0x61
.set NICK0, D+0x62
.set NICKMASK, D+0x64
.set BUCKETS, D+0x68
.set LASTBITS, D+0xB0

.text
.globl _start
_start:
regionA:
    jmp RESUME                      # the retail skin/face draw is skipped (both are set in region B)
rnd:                                # eax = rand(); clobbers ecx, edx
    mov ecx, RNG
    jmp RAND
findname:                           # in: eax = name pointer, ebx = &entries[0].field, ecx = count; out: edi = index (count if absent)
    xor edi, edi
1:  cmp edi, ecx
    jae 2f
    cmp [ebx+edi*8], eax
    je 2f
    inc edi
    jmp 1b
2:  ret
inuse:                              # in: ax = portrait id; out: ZF=1 when some roster player already has it; keeps eax
    push esi
    push ecx
    mov ecx, [ebp]                  # primary count
    mov esi, [ebp+4]                # primary table
3:  test ecx, ecx
    jz 4f
    cmp [esi+6], ax
    je 5f
    add esi, 0x54
    dec ecx
    jmp 3b
4:  or ecx, 1                       # ZF=0: free
5:  pop ecx
    pop esi
    ret
tone_pick:                          # in: al = random byte, edx = threshold table, ecx = threshold count, ebx = first tone; out: ebx
6:  cmp al, [edx]
    jb 7f
    inc ebx
    inc edx
    dec ecx
    jnz 6b
7:  ret
regionA_end:
    .fill 0xE686E - 0xE67EA - (regionA_end - regionA), 1, 0xCC

    .fill 0xE7019 - 0xE686E, 1, 0
regionB:
    mov [esi], eax                  # college (retail store)
    mov ebp, [ROSTER]
    mov ebx, [ebp+0x54]             # name pool entries
    mov ecx, [ebp+0x50]             # count
    mov eax, [esi+0x10]             # first-name pointer
    call findname
    movzx eax, word ptr [NICK0]     # nickname first names sit at the end of the pool: keep 1 in (NICKMASK+1)
    cmp edi, eax
    jb 10f
    cmp edi, ecx
    jae 10f
    call rnd
    test al, [NICKMASK]
    jz 10f
    call rnd
    xor edx, edx
    movzx ecx, word ptr [NICK0]
    div ecx
    mov edi, edx
    mov eax, [ebx+edi*8]
    mov [esi+0x10], eax
10: xor edx, edx                    # logit accumulator in [esp+0x10]
    mov eax, [ebx]                  # canary: an older save carries its own pool; its first names are not ordered
    mov ax, [eax]                   # by these bands, so its name term stays neutral
    cmp ax, [D+0x12A]
    jne 11f
    mov eax, edi
    shl eax, 5
    movzx ecx, word ptr [NICK0]
    div ecx                         # band = index*32/NICK0 (>= 32 for nicknames or an absent name: neutral)
    mov ecx, [ebp+0x50]
    xor edx, edx
    cmp eax, 31
    ja 11f
    movsx edx, byte ptr [FIRSTBAND+eax]
11: mov [esp+0x10], edx
    add ebx, 4
    mov eax, [esi+0x14]             # surname pointer
    call findname
    cmp edi, ecx
    jae 12f
    mov eax, edi
    shr eax, 2
    movzx eax, byte ptr [LASTBITS+eax]
    mov ecx, edi
    and ecx, 3
    shl ecx, 1
    shr eax, cl
    and eax, 3
    movsx eax, byte ptr [LASTCODE+eax]
    add [esp+0x10], eax
12: movzx eax, byte ptr [esi+0x35]  # position
    cmp eax, 16
    ja 13f
    movsx eax, byte ptr [POS+eax]
    add [esp+0x10], eax
13: mov eax, [esp+0x10]             # sigmoid index = (logit + 128) >> 3, clamped 0..31
    add eax, 128
    sar eax, 3
    jns 14f
    xor eax, eax
14: cmp eax, 31
    jbe 15f
    mov eax, 31
15: movzx edi, byte ptr [SIG+eax]   # P(Black) * 256
    call rnd
    movzx eax, al
    cmp eax, edi                    # CF = Black
    sbb edi, edi                    # edi = -1 Black, 0 other
    jmp regionD
regionB_end:
    .fill 0xE7117 - 0xE7019 - (regionB_end - regionB), 1, 0xCC
    .fill D + 0x12C - 0xE7117, 1, 0
regionD:
    call rnd
    mov edx, OFFSET TCO
    xor ecx, ecx
    inc ecx
    xor ebx, ebx
    test edi, edi
    jz 16f
    mov edx, OFFSET TCB
    mov cl, 4
    inc ebx
16: call tone_pick                  # ebx = tone 0..5
    movzx eax, byte ptr [esi+0x2a]  # weight - 150
    lea ebx, [ebx+ebx*2]
    cmp al, [LEANMAX]
    jbe 17f
    inc ebx
    cmp al, [HEAVYMIN]
    jb 17f
    inc ebx
17: lea edi, [BUCKETS+ebx*4]        # bucket = tone*3 + build
    mov ebx, 8                      # tries
18: call rnd
    xor edx, edx
    movzx ecx, byte ptr [edi+2]
    div ecx
    mov [esp+0x14], edx             # index in bucket
    movzx eax, word ptr [edi]
    add eax, edx
    mov word ptr [esi+6], 0xFFFF
    call inuse
    jnz 19f
    dec ebx
    jnz 18b
19: mov [esi+6], ax                 # portrait
    mov ecx, [esi+0x18]             # skin bits 7-9 = tone, Dreads bit 0 = hanging locs or braids
    and ecx, 0xFFFFFC7E
    mov eax, edi
    sub eax, OFFSET BUCKETS
    shr eax, 2
    mov bl, 3
    div bl                          # al = tone
    movzx eax, al
    shl eax, 7
    or ecx, eax
    mov eax, [esp+0x14]
    cmp al, [edi+3]
    jae 20f
    or ecx, 1
20: mov [esi+0x18], ecx
    call rnd                        # generic head shape 0..6 (f9001 + 100*tone + face exists for all of them)
    xor edx, edx
    mov ecx, 7
    div ecx
    shl edx, 17
    mov eax, [esi+0x20]
    and eax, 0xFFF1FFFF
    or eax, edx
    mov [esi+0x20], eax
    pop edi
    pop esi
    pop ebp
    pop ebx
    add esp, 8
    ret 4
regionD_end:
    .fill D + 0x1F8 - D - 0x12C - (regionD_end - regionD), 1, 0xCC
