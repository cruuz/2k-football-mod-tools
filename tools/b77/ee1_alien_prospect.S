# ee1/ee2 alien prospect: everything lives in the 935 bytes of FUN_000E6780's seventeen "copy a field from the low or
# the high template on a coin" blocks (0xE696E..0xE6D15), which the first part rewrites as one table-driven loop that
# makes the same 17 calls of the float rand 0x48B90 in the same order with the same compares (bit-for-bit the same
# prospect). ee2 adds the 7'11" 150 lb record fields, the far-face sf lookup and the sideline-skin lookup.
# Linked at 0xE696E.   as --32 -o x.o x.S && ld -m elf_i386 -Ttext=0xE696E --oformat binary -o x.bin x.o
.intel_syntax noprefix
.set RESUME, 0xE6D15        # retail code after the last coin block
.set FRAND, 0x48B90         # float rand(ecx = generator) -> st0 in [0,1)
.set RAND, 0x48B50          # u32 rand(ecx = generator)
.set RNG, 0xE5FCA0
.set THR_A, 0x4E696C        # the retail 0.5 compare constant (16 blocks)
.set THR_B, 0x4E6D5C        # the other one (the +0x18 bit 1 block)
.set ROSTER, 0xB72918       # -> live roster object
.set YEAR, 0xE576B8         # franchise year (0 in the first season)
.set CLASSLEFT, 0xE41CDC    # prospects still to make in this class (0x17C at the first)
.set FIND, 0x449E0          # resource by name: ecx = container (0 = every resident one), edx = type, [esp+4] = name
.set ALIEN_ID, 1947
.set FLAG, 0xB7             # template record 2 (+0xA8) byte +0x0F, bit 0: "this franchise has had him"
.set THRESH, 75657          # per prospect: 1 - (149/150)^(1/380) of 2^32, so a 380-prospect class has him 1 time in 150

.text
.globl _start
_start:
coin:                               # esi = new record, ebp / ebx = the low / high template (retail registers)
    mov edi, OFFSET table
1:  mov ecx, RNG
    call FRAND
    test byte ptr [edi+5], 1
    jnz 2f
    fcomp dword ptr [THR_A]
    jmp 3f
2:  fcomp dword ptr [THR_B]
3:  fnstsw ax
    test ah, 5
    mov ecx, ebp                    # rand < threshold (or unordered): the low template, as retail's JP falls through
    jnp 4f
    mov ecx, ebx
4:  movzx edx, byte ptr [edi+4]     # field offset
    mov eax, [ecx+edx]
    and eax, [edi]                  # source bits
    mov ecx, [edi]
    test byte ptr [edi+5], 2
    jz 5f
    or cl, 1                        # the last block also clears bit 0 (retail: and 0xFFFFFFFA)
5:  not ecx
    and ecx, [esi+edx]
    or eax, ecx
    mov [esi+edx], eax
    add edi, 6
    cmp edi, OFFSET table_end
    jb 1b
    jmp RESUME

table:                              # u32 mask, u8 offset, u8 flags (1 = THR_B, 2 = also clear bit 0)
    .long 0x00300000
    .byte 0x20, 0
    .long 0x00000007
    .byte 0x20, 0
    .long 0x00000002
    .byte 0x18, 1
    .long 0x000003C0
    .byte 0x1C, 0
    .long 0x00003C00
    .byte 0x1C, 0
    .long 0x00000007
    .byte 0x0C, 0
    .long 0x00000038
    .byte 0x0C, 0
    .long 0x0003C000
    .byte 0x1C, 0
    .long 0x003C0000
    .byte 0x1C, 0
    .long 0x03C00000
    .byte 0x1C, 0
    .long 0x3C000000
    .byte 0x1C, 0
    .long 0x00000003
    .byte 0x1C, 0
    .long 0x00007C00
    .byte 0x20, 0
    .long 0x00018000
    .byte 0x20, 0
    .long 0x00000020
    .byte 0x1C, 0
    .long 0x00000060
    .byte 0x18, 0
    .long 0x00000004
    .byte 0x18, 2
table_end:

wrap:                               # FUN_002BE6F0's call of FUN_000E6780 (0x2BE7CE): the generator, then the roll
    push esi
    mov esi, ecx
    push dword ptr [esp+8]          # the generator's stack argument
    call 0xE6780
    call alien
    pop esi
    ret 4

alien:                              # esi = the prospect just made; keeps every register
    push eax
    push ecx
    push edx
    mov eax, [ROSTER]
    cmp dword ptr [eax+8], 3        # the draft template table must hold record 2
    jb 9f
    mov eax, [eax+0xC]
    cmp dword ptr [YEAR], 0
    jne 7f
    cmp dword ptr [CLASSLEFT], 0x17C
    jne first_season                # (patched to fall through for the test build)
    and byte ptr [eax+FLAG], 0xFE   # a new franchise starts without him (its roster may be a reused RAM copy)
first_season:
    jmp 9f                          # the first class of a franchise (and MyCareer's own creation) never rolls
                                    # (test build: 2 NOPs, so the forced roll happens in a new franchise)
7:  test byte ptr [eax+FLAG], 1
    jnz 9f
    push eax
    mov ecx, RNG
    call RAND
    cmp eax, THRESH                 # (test build: 0xFFFFFFFF)
    pop eax
    jae 9f
    or byte ptr [eax+FLAG], 1       # once in this franchise, never again
    mov word ptr [esi+6], ALIEN_ID  # his own portrait and face package (portrait 1947, f/h/n/s1947)
    and dword ptr [esi+0x18], 0xFFFFF062   # no Dreads, no eye black, skin 0, body type 0 (profile 0: the thinnest)
    and dword ptr [esi+0x1C], 0xFFFFC01F   # bare hands (gloves 0) and no mouthpiece
    and dword ptr [esi+0x20], 0xFFF07FFF   # no visor (his eyes show through the face mask); generic face shape 0
                                           # (skin 0, face 0: s9001, the shape his close-up package carries)
    mov al, [esi+0x0D]
    and al, 0xF0
    or al, 13                       # hair style 13: no hair model
    mov [esi+0x0D], al
    mov byte ptr [esi+0x2B], 95     # 7'11": the record's height byte, any value 0-255; the card divides by 12
    mov byte ptr [esi+0x2A], 0      # 150 lb: weight_raw is pounds - 150 unsigned, so this is the lightest the game
                                    # reads and shows (0x2A + 150); the weight profile clamps it at 150 (profile 0)
9:  pop edx
    pop ecx
    pop eax
    ret

gray:                               # eax = retail texture, ecx = record, edx = UTF-16 name -> eax; clobbers ecx, edx
    cmp word ptr [ecx+6], ALIEN_ID
    jne 1f
    push eax
    push edx
    mov edx, 0x52545854             # 'TXTR'
    xor ecx, ecx                    # every resident container (outer 3, global.iff)
    call FIND
    pop ecx
    test eax, eax
    jnz 1f
    mov eax, ecx                    # no gray texture on this disc: keep the retail one
1:  ret

hand:                               # 0x8ED1F in the hand helper (glove in esi; the record pushed at [ebp-8])
    mov eax, [edx*4+0xB65428]
    test esi, esi                   # gloves 1-9 keep their own textures
    jnz 1f
    push ecx
    mov ecx, [ebp-8]
    mov edx, OFFSET n_hand
    call gray
    pop ecx
1:  ret

arm:                                # 0x8EDDE in the arm helper (bare arms; the record pushed at [ebp-4])
    mov eax, [ecx*4+0xB65428]
    mov ecx, [ebp-4]
    mov edx, OFFSET n_arm
    jmp gray

neck:                               # 0x8F2FC in the player builder (record in ebx)
    mov eax, [edx*4+0xB65520]
    push ecx
    mov ecx, ebx
    mov edx, OFFSET n_neck
    call gray
    pop ecx
    ret

sf:                                 # 0x8F152 in the player builder: the far-LOD placeholder face is
                                    # [eax*4+0xB65508] (sf0..sf5 by LOD pass and skin; record in ebx) -> ecx
    cmp word ptr [ebx+6], ALIEN_ID
    jne 1f
    push eax
    push OFFSET n_sf
    mov edx, 0x52545854             # 'TXTR'
    xor ecx, ecx                    # every resident container
    call FIND
    pop ecx                         # the sf slot index
    test eax, eax
    jz 2f
    mov ecx, eax                    # the alien's own far face
    ret
2:  mov ecx, [ecx*4+0xB65508]       # no alien_sf on this disc: retail
    ret
1:  mov ecx, [eax*4+0xB65508]
    ret

side:                               # 0x119B35 in the sideline-person builder: the bench body is
                                    # [eax*4+0xBA8280] (sideline_skin_00..05 by skin; record in edi) -> eax
    cmp word ptr [edi+6], ALIEN_ID
    jne 1f
    push eax
    push OFFSET n_side
    mov edx, 0x52545854             # 'TXTR'
    xor ecx, ecx
    call FIND
    pop edx                         # the skin slot index
    test eax, eax
    jz 2f
    ret                             # the alien's own gray sideline skin
2:  mov eax, [edx*4+0xBA8280]       # no alien_sideline on this disc: retail
    ret
1:  mov eax, [eax*4+0xBA8280]
    ret

    .balign 2
n_arm:
    .short 'a','l','i','e','n','_','a','r','m',0
n_hand:
    .short 'a','l','i','e','n','_','h','a','n','d',0
n_neck:
    .short 'a','l','i','e','n','_','n','e','c','k',0
n_sf:
    .short 'a','l','i','e','n','_','s','f',0
n_side:
    .short 'a','l','i','e','n','_','s','i','d','e','l','i','n','e',0
end:

# ee2 follow-up: lanky long limbs and a thinner body for photo 1947, on the player matrix postprocessor (0x93850).
# The engine has no limb-length table: height is one uniform root scale (0x918B0) and the four weight profiles only
# scale each bone's girth perpendicular to its SKEL axis. The postprocessor does receive the 25 low and 62 high
# current bone matrices, so this hook scales each arm about its shoulder (true segment length) and lowers the whole
# upper body (thorax and everything above it) on the waist by SPINE_DROP, so the torso is shorter and the legs read
# proportionally longer. Only translation lanes change; joint rotations, animations and attachments stay intact.
.set POST_VA, 0x93850
.set POST_RESUME, 0x93856
.set GIRTH_VA, 0x93859
.set GIRTH_RESUME, 0x9385E
.set GIRTH_NOP, 0x938BD
.set SCHED, 0x4EF898           # u8[62]: high current matrix -> low source channel

skel:                               # 0x93850 entry: ecx = player context, edx = mask, [esp+4] = low current
    cmp word ptr [ecx+6], ALIEN_ID  # photo id (the roster record, as in every ee1/ee2 lookup)
    jne 90f
    mov esi, [esp+4]                # low_current, high_current at +0x640
    pushad
    # lower the upper body by SPINE_DROP (low 10..24 thorax..shoulderpads, high 27..59); the feet and hips stay
    movss xmm6, dword ptr [spine_drop]
    lea ebx, [esi+0x280]                    # low[10] thorax
    mov ebp, 15
    call spine
    lea ebx, [esi+0xD00]                    # high[27] thorax
    mov ebp, 33
    call spine
    # arms: each distal joint is scaled about its shoulder, so the whole arm chain gets longer
    mov ebx, esi                            # low[0]
    xor edi, edi
    mov ebp, 25
1:  movzx eax, byte ptr [edi+chains]
    test eax, eax
    jz 2f
    call limb
2:  add ebx, 64
    inc edi
    dec ebp
    jnz 1b
    lea ebx, [esi+0x640]                    # high[0]
    xor edi, edi
    mov ebp, 62
3:  movzx eax, byte ptr [edi+SCHED]
    movzx eax, byte ptr [eax+chains]
    test eax, eax
    jz 4f
    call limb
4:  add ebx, 64
    inc edi
    dec ebp
    jnz 3b
    popad
90: push ebp
    mov ebp, esp
    and esp, 0xfffffff0
    jmp POST_RESUME

spine:                              # ebx first matrix, ebp count, xmm6 drop -> y -= drop
    movss xmm0, dword ptr [ebx+0x34]
    subss xmm0, xmm6
    movss dword ptr [ebx+0x34], xmm0
    add ebx, 64
    dec ebp
    jnz spine
    ret

limb:                               # eax chain, ebx matrix, esi low base
    movzx edx, byte ptr [eax+pivots-1]
    movss xmm3, dword ptr [eax*4+factors-4]
    mov ecx, edx
    shl ecx, 6
    add ecx, esi
    movups xmm0, xmmword ptr [ecx+0x30]
    movups xmm1, xmmword ptr [ebx+0x30]
    subps xmm1, xmm0
    shufps xmm3, xmm3, 0
    mulps xmm1, xmm3
    addps xmm1, xmm0
    movups xmmword ptr [ebx+0x30], xmm1
    ret

weight:                             # 0x93859: eax = weight pounds for the profile, before the retail clamp
    movzx eax, byte ptr [ecx+0x2a]
    add eax, 150
    cmp word ptr [ecx+6], ALIEN_ID
    jne 1f
    mov eax, 100                    # the visual body profile: his record says 150 (the save floor), the mesh uses 100
1:  ret

.balign 2
factors:                            # chain 1 left arm, 2 right arm
    .float 1.16, 1.16
pivots:
    .byte 14, 19                    # lhumerus, rhumerus
chains:                             # low index / schedule channel -> chain (0 = torso, root, legs or pad)
    .byte 0,0,0,0,0, 0,0,0,0, 0,0,0,0, 0,1,1,1,1, 0,2,2,2,2, 0,0
spine_drop: .float 4.0
