# rookie faces (b778-rh1, extended by b778-rh2 and b779-rf3): replaces the class generator's skin/face draw and its
# weight/height draw (0xE67EA..0xE6923) and portrait pick (0xE7019..0xE7120, incl. 9 bytes of padding) in FUN_000e6780,
# tables + code in the retail range table at 0x4F4F40.
# b779-rf3: region A also replaces the retail weight/height roll (0xE686E..0xE6923: each uniform and independent between
# the position's two template records) with a per-position table (nflverse combine, see BODY in nfl2k5_rookie_faces.py):
# value = lo + (c * S) >> 10, S = the sum of three random bytes (a bell from -3 to +3 sd); weight and height share one of
# their three bytes (correlation 1/3); weight only: 1 prospect in 64 adds 384 to S (a heavy outlier, centred on +3 sd).
# The generic head-shape draw moved here from region D, which now down-weights each row's last 5/16 (the review's
# plainest/ugliest faces): a first draw that lands there is redrawn once.
# Linked at 0xE67EA: as --32; ld -m elf_i386 -Ttext=0xE67EA; objcopy -O binary.
.intel_syntax noprefix
.set D, 0x4F4F40
.set ROSTER, 0xB72918
.set RNG, 0xE5FCA0
.set RAND, 0x48B50
.set RESUME, 0xE6923       # first retail instruction after the weight/height roll
.set POS, D+0x00
.set FIRSTBAND, D+0x14
.set LASTCODE, D+0x34
.set SIG, D+0x38
.set TCB, D+0x58
.set TCO, D+0x5C
.set RFIRST0, D+0x5D      # u16: pool index of the rare first names (4 per rare surname; = count when none)
.set NICK0, D+0x60
.set NICKMASK, D+0x62
.set RS0, D+0x63          # u16: pool index of the 3 rare surnames (2 East, then 1 South); 0x8000 = off
.set CANARY, D+0x65
.set BUCKETS, D+0x68      # 24 rows: tone 0..5 x build, then East x build, South x build: u16 start, u16 count | hanging << 9
.set LASTBITS, D+0xC8
.set TABLE_END, D+0x142
.set TONES, D+0x11        # tone of the East (0x11) / South (0x12) rows
.set LEANMAX, 74          # weight - 150 <= 74: lean (< 225 lb)
.set HEAVYMIN, 125        # weight - 150 >= 125: heavy (>= 275 lb)
.set TRIES, 24
.set OUTK, 4            # heavy outlier: 4 in 256 prospects (1.6 %)
.set OUTADD, 384
.set BLUEK, 10           # blue-chip prospects: 10 in 256 (3.9 %)
.set FRAND, 0x48B90       # float rand [0, 1) (ecx = generator)
.set FTOI, 0xE3F10        # float (stack) -> int, ret 4
.set GETTAB, 0x4F4CB4     # rating getter/setter table (stride 0x14, setter at -4)
.set GETEND, 0x4F4EF8
.set HALF, 0x4E4184       # .rdata 0.5f         # +3 sd on S (sd of S = 128, the table's c = 8 sd)

.text
.globl _start
_start:
regionA:
    jmp body
rndmod:                             # ecx = n -> edx = rand() % n (clobbers eax, ecx)
    push ecx
    call rnd
    pop ecx
    xor edx, edx
    div ecx
    ret
rnd:
    mov ecx, RNG
    jmp RAND
findname:                           # eax = name pointer, ebx = &entries[0].field, ecx = count -> edi = index (count if absent)
    xor edi, edi
1:  cmp edi, ecx
    jae 2f
    cmp [ebx+edi*8], eax
    je 2f
    inc edi
    jmp 1b
2:  ret
inuse:                              # ax = portrait id -> ZF=1 when a roster player already has it; keeps eax
    mov ecx, [ebp]
    mov edx, [ebp+4]
3:  test ecx, ecx
    jz 4f
    cmp [edx+6], ax
    je 5f
    add edx, 0x54
    dec ecx
    jmp 3b
4:  or ecx, 1
5:  ret
nickfix:                            # edi = first-name index, ecx = count. nickname run [NICK0, RFIRST0): keep 1 in NICKMASK+1;
    movzx eax, word ptr [NICK0]     # rare first names [RFIRST0, count): never from an ordinary draw. Redraw from [0, NICK0).
    cmp edi, eax
    jb 7f
    cmp edi, ecx
    jae 7f
    cmp di, [RFIRST0]
    jae 6f
    call rnd
    test al, [NICKMASK]
    jz 7f
6:  movzx ecx, word ptr [NICK0]
    call rndmod
    mov edi, edx
    mov eax, [ebx+edi*8]
    mov [esi+0x10], eax
7:  ret
draw:                               # eax = 4 random bytes x0..x3, cl = lo, ch = c -> eax = lo + (c * S) >> 10,
    push eax                        # S = x0 + x1 + x2, + 384 when x3 < OUTK (the height call forces x3 = 0xFF)
    movzx edx, ah
    movzx eax, al
    add eax, edx
    movzx edx, byte ptr [esp+2]
    add eax, edx
    cmp byte ptr [esp+3], OUTK
    jae 27f
    add eax, OUTADD
27: pop edx
    movzx edx, ch
    imul eax, edx
    shr eax, 10
    movzx ecx, cl
    add eax, ecx
    ret
bodytab:                            # per position 0..16: weight lo (lb - 150), weight c, height lo (in), height c
    .byte  40,  80, 70, 14    #  0 QB
    .byte   0, 122, 66, 18    #  1 K
    .byte  22, 108, 69, 16    #  2 P
    .byte   9, 111, 67, 17    #  3 WR
    .byte  18,  65, 68, 12    #  4 CB
    .byte  29,  68, 68, 13    #  5 FS
    .byte  29,  68, 68, 13    #  6 SS
    .byte  26,  95, 66, 13    #  7 HB
    .byte  64,  81, 69, 11    #  8 FB
    .byte  77,  61, 73, 11    #  9 TE
    .byte  55,  74, 69, 13    # 10 OLB
    .byte  57,  73, 69, 13    # 11 ILB
    .byte 136,  52, 73,  9    # 12 C
    .byte 135,  81, 74,  8    # 13 G
    .byte 130,  93, 75,  9    # 14 T
    .byte 113, 119, 72, 10    # 15 DT
    .byte  75,  78, 72, 11    # 16 DE
body:                               # esi = prospect (his template's position at +0x35), ebx/ebp = templates (kept)
    movzx edi, byte ptr [esi+0x35]
    lea edi, [bodytab+edi*4]
    call rnd
    push eax                        # x0..x2 = weight, x3 = the outlier coin
    mov cx, [edi]
    call draw
    mov [esi+0x2a], al              # weight - 150
    call rnd
    pop edx
    shl eax, 8
    mov al, dl                      # height bytes: the weight's x0 (shared), two new ones
    or eax, 0xFF000000              # no height outlier
    mov cx, [edi+2]
    call draw
    mov [esi+0x2b], al              # height, inches
    push 7                          # generic head shape 0..6 (was at the end of region D)
    pop ecx
    call rndmod
    add edx, edx
    and byte ptr [esi+0x22], 0xF1
    or [esi+0x22], dl
    jmp 28f
regionA_end:
    .fill 0xE6923 - 0xE67EA - (regionA_end - regionA), 1, 0xCC
28:
    .fill 0xE6D51 - 0xE6923, 1, 0
regionC:                            # b779-rf3: the rating loop (29 getter/setter pairs at 0x4F4CB4, retail semantics:
    call qsetup                     # value = b + r * (a - b) between the two templates) with r from qrand, then the
40: mov ecx, ebx                    # three capped rolls (consistency, aggressiveness, composure) as one small loop
    call [edi]
    mov [esp+0x1c], eax
    fild dword ptr [esp+0x1c]
    fstp dword ptr [esp+0x10]       # a (template A)
    mov ecx, ebp
    call [edi]
    mov [esp+0x1c], eax
    fild dword ptr [esp+0x1c]
    fstp dword ptr [esp+0x1c]       # b (template B)
    mov ecx, RNG
    call qrand
    fld dword ptr [esp+0x10]
    fsub dword ptr [esp+0x1c]
    push ecx
    fmulp st(1), st
    fadd dword ptr [esp+0x20]
    fstp dword ptr [esp]
    call FTOI
    mov dl, al
    mov ecx, esi
    call [edi-4]
    add edi, 0x14
    cmp edi, GETEND
    jl 40b
    push 2                          # consistency +0x50, aggressiveness +0x51, composure +0x4E:
    pop edi                         # b + (a - b) * r16 >> 16, a and b capped at 100 (retail: the same in x87)
41: movzx edx, byte ptr [cofs+edi]
    push edx
    movsx eax, byte ptr [ebx+edx]
    cmp eax, 100
    jl 42f
    push 100
    pop eax
42: movsx ecx, byte ptr [ebp+edx]
    cmp ecx, 100
    jl 43f
    push 100
    pop ecx
43: sub eax, ecx
    push ecx
    push eax
    call rnd
    movzx eax, ax
    pop edx
    imul eax, edx
    sar eax, 16
    pop ecx
    add eax, ecx
    pop edx
    mov [esi+edx], al
    dec edi
    jns 41b
    mov ecx, RNG                    # the next retail instruction draws with it
    jmp 29f
qsetup:                             # one byte per prospect: a blue-chip (BLUEK in 256) rolls every rating in the upper
    call rnd                        # half of his template range; the flag lives in the frame's free slot [esp+0x14]
    cmp al, BLUEK
    sbb eax, eax
    mov [esp+4+0x14], eax
    mov edi, GETTAB
    ret
qrand:                              # st0 = r, or (r + 1) / 2 for a blue-chip
    call FRAND
    test byte ptr [esp+4+0x14], 1
    jz 44f
    fld1
    faddp st(1), st
    fmul dword ptr [HALF]
44: ret
cofs:
    .byte 0x4E, 0x51, 0x50
regionC_end:
    .fill 0xE6F56 - 0xE6D51 - (regionC_end - regionC), 1, 0xCC
29:
    .fill 0xE7019 - 0xE6F56, 1, 0
regionB:
    mov [esi], eax                  # college (retail store)
    mov ebp, [ROSTER]
    mov ebx, [ebp+0x54]
    mov ecx, [ebp+0x50]
    add ebx, 4                      # surnames first: code term, and the index for the rare check
    mov eax, [esi+0x14]
    call findname
    mov [esp+0x14], edi
    xor edx, edx
    cmp edi, ecx
    jae 12f
    mov eax, edi
    shr eax, 2
    movzx eax, byte ptr [LASTBITS+eax]
    mov ecx, edi
    and ecx, 3
    add ecx, ecx
    shr eax, cl
    and eax, 3
    movsx edx, byte ptr [LASTCODE+eax]
    mov ecx, [ebp+0x50]
12: mov [esp+0x10], edx
    sub ebx, 4
    mov eax, [esi+0x10]
    call findname
    call nickfix
    mov eax, [ebx]                  # canary: an older save carries its own pool (no first-name term, no rare groups)
    mov ax, [eax]
    cmp ax, [CANARY]
    jne 9f
    mov eax, edi
    shl eax, 5
    movzx ecx, word ptr [NICK0]
    xor edx, edx
    div ecx
    cmp eax, 31
    ja 13f
    movsx edx, byte ptr [FIRSTBAND+eax]
    add [esp+0x10], edx
    jmp 13f
9:  or dword ptr [esp+0x14], -1
13: movzx eax, byte ptr [esi+0x35]  # position
    cmp eax, 16
    ja 14f
    movsx eax, byte ptr [POS+eax]
    add [esp+0x10], eax
14: mov eax, [esp+0x10]
    add eax, 128
    sar eax, 3
    jns 15f
    xor eax, eax
15: cmp eax, 31
    jbe 16f
    mov al, 31
16: movzx edi, byte ptr [SIG+eax]
    call rnd
    movzx eax, al
    cmp eax, edi
    sbb edi, edi                    # -1 Black, 0 other
    call rnd                        # tone: Black 1..5 by TCB, other 0..1 by TCO
    mov edx, OFFSET TCO
    xor ecx, ecx
    inc ecx
    xor ebx, ebx
    test edi, edi
    jz 17f
    mov edx, OFFSET TCB
    mov cl, 4
    inc ebx
17: cmp al, [edx]
    jb 18f
    inc ebx
    inc edx
    dec ecx
    jnz 17b
18: movzx eax, byte ptr [esi+0x2a]  # build from his weight
    xor edx, edx
    cmp al, LEANMAX
    jbe 19f
    inc edx
    cmp al, HEAVYMIN
    jb 19f
    inc edx
19: jmp regionD
regionB_end:
    .fill 0xE7120 - 0xE7019 - (regionB_end - regionB), 1, 0xCC
    .fill TABLE_END - 0xE7120, 1, 0
regionD:                            # ebx = tone, edx = build
    mov [esp+0x10], ebx             # the tone written to the skin bits
    mov eax, [esp+0x14]             # a rare surname? (-1 on an older pool)
    sub ax, [RS0]
    cmp eax, 3
    jae 20f
    xor ecx, ecx                    # group: East for the first two, South for the third
    cmp al, 2
    setae cl
    mov bl, [TONES+ecx]
    mov [esp+0x10], ebx
    lea ebx, [ecx+6]                # rows 18..23
    mov ecx, [esi]                  # first name: pool[RFIRST0 + 4 * rare + (college & 3)]
    and ecx, 3
    lea eax, [ecx+eax*4]
    add ax, [RFIRST0]
    mov ecx, [ebp+0x54]
    mov ecx, [ecx+eax*8]
    mov [esi+0x10], ecx
20: lea edi, [ebx+ebx*2]
    add edi, edx
    lea edi, [BUCKETS+edi*4]
    push TRIES
    pop ebx
22: movzx ecx, word ptr [edi+2]
    and ch, 1                       # count (9 bits)
    call rndmod                     # edx = index, ecx = count
    cmp bl, TRIES                   # first draw in the row's last 5/16 (the plainest faces): draw again
    jne 25f
    lea eax, [ecx+ecx*4]
    shr eax, 4
    sub ecx, eax
    cmp edx, ecx
    jae 26f
25: mov [esp+0x14], edx
    movzx eax, word ptr [edi]
    add eax, edx
    call inuse
    jnz 23f
26: dec ebx
    jnz 22b
23: mov [esi+6], ax
    mov ecx, [esi+0x18]             # skin bits 7-9 = tone, Dreads = hanging face
    and ecx, 0xFFFFFC7E
    mov eax, [esp+0x10]
    shl eax, 7
    or ecx, eax
    movzx eax, byte ptr [edi+3]
    shr eax, 1
    cmp [esp+0x14], eax
    jae 24f
    inc ecx
24: mov [esi+0x18], ecx
    pop edi
    pop esi
    pop ebp
    pop ebx
    add esp, 8
    ret 4
regionD_end:
    .fill D + 0x1F8 - TABLE_END - (regionD_end - regionD), 1, 0xCC
