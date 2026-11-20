.intel_syntax noprefix
.code32
.section .text
.global stability
# Long-franchise stability (beta 81): the contract is the addendum "Long-franchise stability" of pos3/DESIGN.md
# (A.2 the mechanism, A.6 the interim). From a franchise's third season on, each class's chance is multiplied by
# g = R / M, clamped to 0.5 to 1.25, where M is the league mean of max(0, K - Durability) over the class's starters and
# R the same statistic at the calibrated level (installer). In the first two seasons every g is exactly 1.0, and a
# multiply by exactly 1.0 changes no bit, so those seasons play as slice 3 does.
# Entered by CALL as the first instruction of the new-game blocks of clinical.S (quarterback) and positions.S, so it
# runs before the first use of a factor in every fixture and again after any load. It is a pure function of the
# loaded league: the season index, the club active lists, and each listed player's stored position, depth rank and
# Durability. It writes only stab_factor, stab_sum and stab_count in the bank (and the stack), preserves every general
# register (not the flags; neither caller needs them), uses one x87 slot and touches no game generator.
.set CLASS_COUNT, 13                    # slices 2 and 3's twelve classes in their order, then the quarterback
.set ONE, 0x3f800000
.set FLOOR, 0x3f000000                  # 0.5
.set CEILING, 0x3fa00000                # 1.25
.set MIN_STARTERS, 8
.set CLUBS, 32
.set CLUB_SIZE, 500
.set MAX_LISTED, 0x41                   # the active list's limit, as recovery.c checks it
stability:
    pushad
    mov ecx, CLASS_COUNT-1
defaults:
    mov DWORD PTR [stab_factor+ecx*4], ONE      # exactly 1.0 first, whatever an earlier fixture left
    dec ecx
    jns defaults
    movzx eax, BYTE PTR [stab_mode]     # 0 off, 1 year table (interim), 2 adaptive
    test eax, eax
    jz done
    mov ebx, [0xe576b8]                 # season index of the franchise, 0 in its first season
    cmp ebx, 2
    jb done                             # the first two seasons are never touched
    cmp eax, 1
    jne adaptive
    cmp ebx, 9
    jbe year_ready
    mov ebx, 9
year_ready:
    mov eax, [stab_year+ebx*4]          # interim: one factor for every class, by season index
    mov ecx, CLASS_COUNT-1
year_fill:
    mov [stab_factor+ecx*4], eax
    dec ecx
    jns year_fill
    jmp done
adaptive:
    mov eax, [0xb72918]
    test eax, eax
    jz done
    mov esi, [eax+0x1c]                 # club table, 500 bytes a club, active list pointers from +0, count at +0x11C
    test esi, esi
    jz done
    xor eax, eax
    mov ecx, CLASS_COUNT*2-1
clear:
    mov [stab_sum+ecx*4], eax           # stab_sum then stab_count, contiguous
    dec ecx
    jns clear
    mov ebp, CLUBS
club:
    movzx ecx, BYTE PTR [esi+0x11c]     # players on this club's active list
    cmp ecx, MAX_LISTED
    ja done                             # not a club record: leave every factor at 1.0
    xor ebx, ebx
player:
    cmp ebx, ecx
    jae next_club                       # only the listed players: IR and free agents are not on the list
    mov edi, [esi+ebx*4]
    inc ebx
    test edi, edi
    jz player
    movzx eax, BYTE PTR [edi+0x35]      # stored position, 0 to 16
    cmp eax, 16
    ja player
    movzx edx, BYTE PTR [stab_class+eax]
    cmp edx, 0xff
    je player                           # kickers, punters and switched-off classes
    push ecx
    movzx ecx, WORD PTR [edi+0x28]
    shr ecx, 10
    and ecx, 7                          # stored depth rank at his position, 0 first
    cmp cl, BYTE PTR [stab_starters+eax]
    pop ecx                             # POP leaves the flags
    jae player                          # starters only
    movzx eax, BYTE PTR [edi+0x3b]      # stored Durability
    push ecx
    movzx ecx, BYTE PTR [stab_zero+edx]
    sub ecx, eax                        # K - Durability
    jae counted
    xor ecx, ecx                        # above the zero point: no chance, counts as 0
counted:
    add [stab_sum+edx*4], ecx
    inc DWORD PTR [stab_count+edx*4]
    pop ecx
    jmp player
next_club:
    add esi, CLUB_SIZE
    dec ebp
    jnz club
    xor ecx, ecx
class:
    cmp DWORD PTR [stab_count+ecx*4], MIN_STARTERS
    jb keep                             # too few starters to mean anything: stay at 1.0
    cmp DWORD PTR [stab_sum+ecx*4], 0
    je keep                             # every starter at or above K: stay at 1.0, no division by zero
    fild DWORD PTR [stab_count+ecx*4]
    fmul DWORD PTR [stab_reference+ecx*4]   # count x R
    fidiv DWORD PTR [stab_sum+ecx*4]        # / sum = R / M
    fstp DWORD PTR [stab_factor+ecx*4]
    mov eax, [stab_factor+ecx*4]        # positive floats order like unsigned integers
    cmp eax, FLOOR
    jae floor_ok
    mov eax, FLOOR
floor_ok:
    cmp eax, CEILING
    jbe ceiling_ok
    mov eax, CEILING
ceiling_ok:
    mov [stab_factor+ecx*4], eax
keep:
    inc ecx
    cmp ecx, CLASS_COUNT
    jb class
done:
    popad
    ret

.balign 4
stab_factor: .rept CLASS_COUNT          # the factor per class; positions.S reads +class*4, clinical.S +48
    .long ONE
    .endr
stab_sum: .zero 4*CLASS_COUNT           # sum of max(0, K - Durability) over the class's starters
stab_count: .zero 4*CLASS_COUNT         # their number (must follow stab_sum: one loop clears both)
stab_reference: .zero 4*CLASS_COUNT     # floats R, installer
stab_year: .rept 10                     # floats by season index 0 to 9 (later seasons use 9), installer
    .long ONE
    .endr
# by stored position: QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE
stab_class:    .byte 12, 0xff, 0xff, 5, 10, 11, 11, 4, 7, 6, 9, 9, 2, 1, 0, 8, 3   # installer: 0xFF switches off
stab_starters: .byte 1, 0, 0, 3, 3, 1, 1, 2, 1, 1, 3, 3, 1, 2, 2, 2, 2   # ranks below this count as starters
stab_zero: .zero CLASS_COUNT            # bytes, installer: the zero point K per class (quarterback 100)
stab_mode: .byte 0                      # installer: 0 off, 1 year, 2 adaptive
.section .note.GNU-stack,"",@progbits
