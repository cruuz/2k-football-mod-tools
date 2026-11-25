.intel_syntax noprefix
.code32
.section .text
.global positions
# Slices 2 and 3 (beta 81): one private injury check per simulated franchise scrimmage play for every walked lineup
# slot: tackles, guards, center, ends and the ball-carrying halfback (slice 2), receivers, tight end, fullback,
# defensive tackles, linebackers, cornerbacks and safeties (slice 3). The contract is pos2/DESIGN.md sections 2 and
# 4.1 and pos3/DESIGN.md sections 1 and 2. Entered by CALL from clinical.S `finished`, where the caller restores every general register, the flags and
# the FXSAVE image afterwards. Nothing here draws from or writes to a game generator.
#
# At entry [esp] is the return address, [esp+4] the 512-byte FXSAVE image and [esp+516] the saved frame F
# (clinical_return.S: pushfd; pushad; mov ecx,esp): F+28 the saved EAX, which is 1 when the game's own roll at
# 0x1028B0 fired and called its selector (0x1028F3) and 0 otherwise; F+40 the return address of the hooked call
# (0x1081E8 rush, 0x10904F pass, 0x108A07 sack or escape); F+44, F+48, F+52 the three original arguments, F+52 being
# the one 0x1028B0 passes to the selector as its restriction (0x1028E4).
.set FRAME, 516
.set RUSH_RETURN, 0x1081e8
.set SLOT_COUNT, 29
.set CLASS_COUNT, 14
.set STAB_CLASSES, 12                  # classes with a long-franchise factor; kicker and punter (12, 13) take none
positions:
    cmp BYTE PTR [pos_enabled], 0
    je done
    mov ebx, [esp+FRAME]
    cmp DWORD PTR [ebx+28], 0           # the game's own roll fired on this play
    jne done
    cmp DWORD PTR [ebx+52], 0           # the caller's restriction argument
    jne done
    call 0x625a0                        # the same injury master, mode and slider predicate
    test eax, eax
    jz done
    mov ebx, [esp+FRAME]
    mov esi, [0xa9719c]                 # offensive side
    test esi, esi
    jz done
    mov edi, [0xa971a0]                 # defensive side
    test edi, edi
    jz done
    mov ecx, [0xb72918]
    test ecx, ecx
    jz done
    mov ecx, [ecx+0x1c]                 # loaded franchise club table, 500 bytes per club
    test ecx, ecx
    jz done
    mov eax, [esi]
    mov edx, [edi]
    sub eax, ecx
    sub edx, ecx
    cmp eax, 15500
    ja done
    cmp edx, 15500
    ja done
    cmp eax, edx
    je done
    jb sorted_clubs
    xchg eax, edx
sorted_clubs:
    mov ecx, [0xe576b8]                 # season, week and the sorted club offsets identify a fixture
    mov ebp, [0xe576b4]
    cmp eax, [pos_club_a]
    jne new_game
    cmp edx, [pos_club_b]
    jne new_game
    cmp ecx, [pos_year]
    jne new_game
    cmp ebp, [pos_week]
    je existing_game
new_game:
    call STABILITY                      # long-franchise factors for this fixture (stability.S)
    mov [pos_club_a], eax
    mov [pos_club_b], edx
    mov [pos_year], ecx
    mov [pos_week], ebp
    rol eax, 16
    xor eax, edx
    xor eax, 0x32534f50                 # "POS2": slice 2's own stream namespace
    call mix32
    xor eax, ecx
    rol ebp, 16
    xor eax, ebp
    call mix32
    xor eax, DWORD PTR [0xe5fca8]       # read two initialized match words, never draw or write
    call mix32
    xor eax, DWORD PTR [0xe5fcb0]
    call mix32
    mov [pos_key], eax
    mov DWORD PTR [pos_seq], 0
existing_game:
    inc DWORD PTR [pos_seq]
    inc DWORD PTR [pos_plays]
    mov eax, [pos_seq]
    imul eax, 0x9e3779b9
    add eax, [pos_key]
    call mix32
    mov [pos_hash], eax                 # one counter value for this play
    xor eax, 0x32544750                 # "PGT2": the gate sample
    call mix32
    and eax, 0x7fffffff
    mov [pos_sample], eax
pos_sampled:                            # exported: the play's sample is stored (tests and the season harness)
    # E[class] = S[class] x Injury slider, as an unsigned integer on the 31-bit scale per point of 100 - Durability
    xor ecx, ecx
effective:
    fld DWORD PTR [pos_scale+ecx*4]
    fmul DWORD PTR [0xe60204]
    cmp ecx, STAB_CLASSES
    jae no_factor                       # b81 game outcomes: the kicker and punter classes have no stability factor
    fmul DWORD PTR [STAB_FACTOR+ecx*4]  # the class's factor, exactly 1.0 in seasons one and two
no_factor:
    fistp QWORD PTR [pos_wide]
    mov eax, [pos_wide]
    mov edx, [pos_wide+4]
    test edx, edx
    jz effective_store
    js effective_zero                   # negative or invalid: no chance
    mov eax, 0xffffffff                 # too large for 32 bits: saturates in the product below
    jmp effective_store
effective_zero:
    xor eax, eax
effective_store:
    mov [pos_effective+ecx*4], eax
    inc ecx
    cmp ecx, CLASS_COUNT
    jb effective
    xor ebp, ebp                        # entry index
walk:
    movzx eax, BYTE PTR [pos_slots+ebp*4+1]
    mov ecx, esi
    test eax, eax
    jz side_ready
    mov ecx, edi
side_ready:
    cmp DWORD PTR [ecx+0xdc], 0         # the native selector's own side guard
    jne next
    movzx eax, BYTE PTR [pos_slots+ebp*4+2]
    mov edx, [ecx+eax*4+8]              # the match copy in this lineup slot
    test edx, edx
    jz next
    test DWORD PTR [edx+0x20], 0xbfc00000   # injured bit or weeks remaining
    jnz next
    test BYTE PTR [edx+0x27], 0x70      # status
    jnz next
    movzx eax, BYTE PTR [pos_slots+ebp*4+3]
    and eax, 3                          # rule: 0 every scrimmage play, 1 rushing ball carrier, 2 rush play, 3 specialists
    jz exposed
    cmp eax, 3
    je specialists
    cmp DWORD PTR [ebx+40], RUSH_RETURN
    jne next
    dec eax
    jnz exposed                         # rule 2: any rush play of his offense
    cmp edx, [0xa971a4]                 # rule 1: he is the ball carrier
    jne next
    jmp exposed
specialists:
    # rule 3 (b81 game outcomes, coordinator R3 ruling): the kicker and punter rows count only while both specialist
    # slots of that side hold their own specialists (stored position 1 in slot 32, 2 in slot 14). While either is out,
    # the other covers both jobs unexposed, so a club never loses both and puts a position player in to kick or punt.
    mov eax, [ecx+32*4+8]
    test eax, eax
    jz next
    cmp BYTE PTR [eax+0x35], 1
    jne next
    mov eax, [ecx+14*4+8]
    test eax, eax
    jz next
    cmp BYTE PTR [eax+0x35], 2
    jne next
exposed:
    movzx eax, BYTE PTR [edx+0x3b]      # stored Durability (unsigned)
    push ecx
    movzx ecx, BYTE PTR [pos_slots+ebp*4]   # class
    mov edx, [pos_zero+ecx*4]           # the class's zero point K (installer)
    sub edx, eax                        # K - Durability
    jbe immune                          # at or above the zero point: no chance
    mov eax, edx
    mul DWORD PTR [pos_effective+ecx*4] # edx:eax = (K - Durability) x E[class]
    pop ecx
    test edx, edx
    jnz saturate
    cmp eax, 0x80000000
    jbe compare
saturate:
    mov eax, 0x80000000                 # a certain proposal, never an overflow
compare:
    movzx edx, BYTE PTR [pos_slots+ebp*4+3]
    shr edx, 4                          # exposure weight in sixteenths; 0 means full
    jz weighted
    mul edx                             # at most 0x80000000 x 15, fits 64 bits
    shrd eax, edx, 4
weighted:
    cmp [pos_sample], eax
    jb hit
    sub [pos_sample], eax               # exclusive events from the one sample
next:
    inc ebp
    cmp ebp, SLOT_COUNT
    jb walk
done:
    ret
immune:
    pop ecx
    jmp next
hit:
    mov [victim_side], ecx
    movzx eax, BYTE PTR [pos_slots+ebp*4+2]
    mov [victim_slot], eax
    movzx eax, BYTE PTR [pos_slots+ebp*4]
    mov [pos_class], eax
    inc DWORD PTR [pos_hits+eax*4]
    lea eax, [eax+eax*2]
    shl eax, 3                          # six dwords per class
    add eax, OFFSET pos_accept
    mov [accept_ptr], eax
    mov eax, [pos_hash]
    xor eax, 0x324e4c50                 # "PLN2": the acceptance draw
    call mix32
    shr eax, 1
    push eax
    mov eax, [pos_hash]
    xor eax, 0x32544e50                 # "PNT2": seed of the private diagnosis and duration generator
    call mix32
    mov edx, eax
    mov ecx, OFFSET QB_PRIVATE_RNG
    call 0x48be0
    push 0                              # status scratch; the next argument is the acceptance draw
    call pos_descriptor                 # returns through the game's own `ret 8`, kept or not
    ret

# MurmurHash3 32-bit finalizer (the same function as clinical.S), clobbers only EAX and EDX.
mix32:
    mov edx, eax
    shr edx, 16
    xor eax, edx
    imul eax, 0x85ebca6b
    mov edx, eax
    shr edx, 13
    xor eax, edx
    imul eax, 0xc2b2ae35
    mov edx, eax
    shr edx, 16
    xor eax, edx
    ret

# The installer fills both blocks from the user's own game (the same 139 and 93 native bytes slice 1 links).
pos_descriptor:
    .zero 139
    mov edi, [esp+0x10]
    mov eax, [victim_side]
    mov [esp+0x14], eax
    mov eax, [victim_slot]
    mov [esp+0x18], eax
pos_duration:
    .zero 93
pos_duration_accept:
    mov eax, ebx                        # assigned weeks
    cmp eax, 31
    jbe accept_index
    mov eax, 31
accept_index:
    movzx eax, BYTE PTR [pos_week_group+eax]   # weeks 0-1, 2, 3, 4-7, 8-15, 16-31: groups 0 to 5
    mov edx, DWORD PTR [esp+0x3c]       # the acceptance draw
    mov ecx, [accept_ptr]
    cmp edx, [ecx+eax*4]
    jae 0x10286e                        # not kept: the game's own no-injury exit
    mov eax, [pos_class]
    inc DWORD PTR [pos_commits+eax*4]
    jmp 0x1027e8                        # the game's own health write, status and lineup substitution

.balign 4
pos_year: .long -1
pos_week: .long -1
pos_club_a: .long -1
pos_club_b: .long -1
pos_key: .long 0
pos_seq: .long 0
pos_hash: .long 0
pos_sample: .long 0
pos_wide: .quad 0
pos_class: .long 0
victim_side: .long 0
victim_slot: .long 0
accept_ptr: .long 0
pos_plays: .long 0
pos_hits: .zero 4*CLASS_COUNT
pos_commits: .zero 4*CLASS_COUNT
pos_effective: .zero 4*CLASS_COUNT
pos_scale: .zero 4*CLASS_COUNT          # CLASS_COUNT floats, installer
pos_zero: .zero 4*CLASS_COUNT           # CLASS_COUNT dwords, installer: the zero point K per class
pos_accept: .zero 24*CLASS_COUNT        # CLASS_COUNT tables of six thresholds by week group, installer
pos_week_group: .byte 0,0,1,2,3,3,3,3,4,4,4,4,4,4,4,4,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5   # assigned weeks 0 to 31
# class, side (0 offense, 1 defense), lineup slot, flags: bits 0-1 the rule (0 every scrimmage play, 1 rushing ball
# carrier, 2 rush play), bits 4-7 the exposure weight in sixteenths (0 full, 0x40 a quarter). Walk order.
pos_slots:
    .byte 0, 0, 12, 0
    .byte 0, 0, 13, 0
    .byte 1, 0, 10, 0
    .byte 1, 0, 11, 0
    .byte 2, 0, 9, 0
    .byte 3, 1, 15, 0
    .byte 3, 1, 16, 0
    .byte 4, 0, 1, 1
    .byte 4, 0, 3, 1
    .byte 5, 0, 4, 0
    .byte 5, 0, 5, 0
    .byte 5, 0, 6, 0
    .byte 5, 0, 7, 0x40
    .byte 6, 0, 8, 0
    .byte 7, 0, 2, 0x02
    .byte 8, 1, 17, 0
    .byte 8, 1, 18, 0
    .byte 9, 1, 19, 0
    .byte 9, 1, 20, 0
    .byte 9, 1, 21, 0
    .byte 9, 1, 22, 0x40
    .byte 10, 1, 24, 0
    .byte 10, 1, 25, 0
    .byte 10, 1, 26, 0
    .byte 11, 1, 23, 0
    .byte 11, 1, 27, 0
    .byte 11, 1, 28, 0x40
    # b81 game outcomes (coordinator R2/R3): the kicker (lineup slot 32) and the punter (slot 14) of the offense, on every
    # scrimmage play of their offense while both slots hold their own specialists (rule 3), LAST in the walk so every
    # earlier entry's hit decision is unchanged.
    .byte 12, 0, 32, 3
    .byte 13, 0, 14, 3
pos_enabled: .byte 0
.section .note.GNU-stack,"",@progbits
