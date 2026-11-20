.intel_syntax noprefix
.code32
.section .text
.global supplement
# The three scheduled scrimmage handlers enter through the franchise fixture guard.
supplement:
    push eax
    mov eax, [0xa9719c]
    test eax, eax
    jz before_primary
    mov eax, [eax+8]
before_primary:
    xchg [esp], eax                     # saved pre-selection active QB
    push DWORD PTR [esp+16]
    push DWORD PTR [esp+16]
    push DWORD PTR [esp+16]
    call 0x1028b0                       # always execute original call with original arguments
    jmp qb_capture_flags
    .fill 5,1,0x90
continue_capture:
    and esp, -16
    fxsave [esp]
    mov [esp+512], ecx                 # preserved GPR frame above the aligned FX image
    cmp DWORD PTR [ecx+52], 0           # same restriction argument as the primary selector
    jne finished
    mov esi, [0xa9719c]
    test esi, esi
    jz finished
    cmp DWORD PTR [esi+0xdc], 0
    jne finished
    mov ebp, [esi+8]
    test ebp, ebp
    jz finished
    mov edx, [esp+512]
    cmp ebp, [edx+36]                   # block a second QB after a primary substitution
    jne finished
    cmp BYTE PTR [ebp+0x35], 0
    jne finished
    test BYTE PTR [ebp+0x23], 0x80
    jnz finished
    test BYTE PTR [ebp+0x27], 0x70
    jnz finished
    call 0x625a0                        # same injury master/mode/slider predicate
    test eax, eax
    jz finished
    mov edi, [0xa971a0]
    test edi, edi
    jz finished
    mov ecx, [0xb72918]
    test ecx, ecx
    jz finished
    mov ecx, [ecx+0x1c]                 # loaded franchise club table, 500 bytes per club
    mov eax, [esi]
    mov edx, [edi]
    sub eax, ecx
    sub edx, ecx
    cmp eax, 15500
    ja finished
    cmp edx, 15500
    ja finished
    cmp eax, edx
    je finished
    jb sorted_clubs
    xchg eax, edx
sorted_clubs:
    mov ecx, [0xe576b8]                 # season, week and sorted club offsets identify a game
    mov ebx, [0xe576b4]
    cmp eax, [club_a]
    jne new_game
    cmp edx, [club_b]
    jne new_game
    cmp ecx, [season_year]
    jne new_game
    cmp ebx, [season_week]
    je existing_game
new_game:
    mov [club_a], eax
    mov [club_b], edx
    mov [season_year], ecx
    mov [season_week], ebx
    rol eax, 16
    xor eax, edx
    xor eax, 0x51424931                   # "QBI1" private stream namespace
    call mix32
    xor eax, ecx
    rol ebx, 16
    xor eax, ebx
    call mix32
    xor eax, DWORD PTR [0xe5fca8]         # read two initialized match words, never draw or write
    call mix32
    xor eax, DWORD PTR [0xe5fcb0]
    call mix32
    mov [game_key], eax
    mov DWORD PTR [sequence_no], 0
existing_game:
    inc DWORD PTR [sequence_no]
    mov eax, [sequence_no]
    imul eax, 0x9e3779b9
    add eax, [game_key]
    call mix32
    mov ebx, eax                        # one counter value for this eligible play
    xor eax, 0x47415445                  # GATE
    call mix32
    and eax, 0x7fffffff
    mov [gate_sample], eax
    movzx ecx, BYTE PTR [ebp+0x3b]     # actual stored Durability
    mov edx, OFFSET ordinary_thresholds
    inc DWORD PTR [ordinary_opps]
    mov eax, [esp+512]
    cmp DWORD PTR [eax+40], 0x108a07    # return PC of credited sack/scramble handler
    jne evaluate_gate
    dec DWORD PTR [ordinary_opps]
    inc DWORD PTR [special_opps]
    mov edx, OFFSET special_thresholds
evaluate_gate:
    fld DWORD PTR [edx+ecx*4]           # thresholds in 31-bit units at slider 1.0
    fmul DWORD PTR [0xe60204]
    fild DWORD PTR [gate_sample]
    fcompp
    fnstsw ax
    test ah, 1                          # private roll < threshold (either 0.5 or 1.0 works)
    jz finished
    inc DWORD PTR [gate_hits]
    mov eax, ebx
    xor eax, 0x4c454e31                  # independent LEN1 uniform for duration acceptance
    call mix32
    shr eax, 1
    push eax
    mov eax, ebx
    xor eax, 0x4e415431                  # NAT1, private native diagnosis / duration seed
    call mix32
    mov edx, eax
    mov ecx, OFFSET private_rng
    call 0x48be0
    push 0                              # status scratch, following arg is the LEN1 draw
    call descriptor
finished:
    fxrstor [esp]
    mov esp, [esp+512]
    popad
    popfd
    lea esp, [esp+4]
    ret 12

# MurmurHash3 32-bit finalizer, bijective in the input, clobbers only EAX and EDX.
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

# The installer populates four routines from the exact compatible local game. No retail code is embedded.
descriptor:
    .zero 139
    mov edi, [esp+0x10]
    mov eax, [0xa9719c]
    mov [esp+0x14], eax
    mov DWORD PTR [esp+0x18], 0
duration:
    .zero 93
duration_accept:
    mov eax, ebx
    cmp eax, 255
    ja 0x10286e
    mov edx, DWORD PTR [esp+0x3c]
    cmp edx, [length_thresholds+eax*4]
    jae 0x10286e
    inc DWORD PTR [commits]
    jmp qb_duration_adjust                        # exact native health flags, status, substitution and observer
group:
    .zero 157
weeks:
    .zero 421

.balign 4
season_year: .long -1
season_week: .long -1
club_a: .long -1
club_b: .long -1
game_key: .long 0
sequence_no: .long 0
gate_sample: .long 0
ordinary_opps: .long 0
special_opps: .long 0
gate_hits: .long 0
commits: .long 0
private_rng: .zero 448
ordinary_thresholds: .zero 1024
special_thresholds: .zero 1024
length_thresholds: .zero 1024
