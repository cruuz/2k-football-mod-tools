/* EXPERIMENTAL / UNWITNESSED. b778 ai6, GNU as --32. Late-game fourth down for a CPU team TRAILING in the last two
 * minutes of the fourth quarter (Noah 10/23): go for it at any distance; kick only when trailing by 1 to 3 and the
 * kicker is in range (range - 5 yards, as the late-lead rule); punt only when all three timeouts remain, more than
 * 1:30 is left, the opponent scored 7 or fewer in the second half (the game's own live quarter scoring at 250DD0,
 * category 7) and a 1-in-3 state hash (play count + drive index + clock bits) is zero. Otherwise go. Returns 0
 * retail (native Hail Mary), 1 go, 2 field goal, 3 punt, 4 not this situation. Every register, flag and the x87
 * stack are preserved.
 *
 * Called only after the caller has checked the CPU offense, phase, fourth down and the user-VIP delegation.
 */
.intel_syntax noprefix
.code32
.text
.global late_decision
.extern half_time, kicker_range, quarter_points, hail_mary, late_state

late_decision:
    pushfd
    pushad
    sub esp, 16
    mov eax, [0xe602c4]
    cmp eax, 4
    jne late_no                     /* fourth quarter only */
    mov eax, [0xe60280]             /* offense team */
    test eax, eax
    jz late_no
    mov [esp+8], eax
    mov edx, [eax+8]                /* score object: +0 score, +4 timeouts, +0xC direction record */
    test edx, edx
    jz late_no
    mov ecx, [edx]                  /* offense score */
    mov edx, [eax]                  /* opponent team */
    test edx, edx
    jz late_no
    mov edx, [edx+8]
    test edx, edx
    jz late_no
    sub ecx, [edx]                  /* margin, offense minus opponent */
    mov [esp+4], ecx
    test ecx, ecx
    jns late_no                     /* not trailing */
    mov ecx, [esp+8]
    call half_time                  /* seconds left in the half (the quarter clock in period 4) */
    fstp dword ptr [esp]
    mov eax, [esp]
    cmp eax, 0x42f00000
    ja late_no                      /* more than 2:00 left */
    mov ecx, [esp+8]
    mov edx, [ecx+8]
    mov edx, [edx+0xc]
    test edx, edx
    jz late_no
    mov eax, [edx+4]                /* native direction value: only its sign matters */
    mov edx, [0xe602ec]
    fld dword ptr [edx+0x18]        /* line of scrimmage */
    fdiv dword ptr yard
    test eax, eax
    js late_negative_direction
    fchs
late_negative_direction:
    fadd dword ptr fifty            /* yards to the opponent goal line */
    fstp dword ptr [esp+12]
    mov eax, [esp+4]
    cmp eax, -3
    jl late_punt                    /* trailing by 4 or more: never kick */
    mov ecx, [esp+8]
    call kicker_range
    fdiv dword ptr yard
    fsub dword ptr five
    fadd dword ptr eps              /* inclusive, the same 0.0001 yard tolerance as the late-lead rule */
    fcomp dword ptr [esp+12]
    fnstsw ax
    test ah, 5
    jnz late_punt
    mov eax, 2
    jmp late_set
late_punt:
    mov eax, [esp+8]
    mov eax, [eax+8]
    cmp dword ptr [eax+4], 3        /* all three timeouts */
    jne late_go
    cmp dword ptr [esp], 0x42b40000
    jbe late_go                     /* 1:30 or less: no punt */
    mov ecx, 1                      /* drive-ring side: 0 home, 1 away */
    cmp dword ptr [esp+8], 0xe5fc20
    je late_side
    xor ecx, ecx
late_side:
    mov edx, 7                      /* second-half points (live quarter scoring) */
    call quarter_points
    cmp eax, 7
    jg late_go                      /* the opponent moved the ball in the second half */
    /* An 8-byte state in the named late data owner: a counter and the last drive. The counter advances once per
     * drive (the CPU may enter the policy several times for one decision), so the punt cycle is 1 and 2 go, 3
     * punts, over decisions, not calls. The counter==0 and last==drive==0 at install is the first drive. */
    mov ecx, [0xe53800]
    cmp ecx, [late_state+4]
    jne late_advance
    cmp dword ptr [late_state], 0
    jne late_hash
late_advance:
    mov [late_state+4], ecx
    inc dword ptr [late_state]
late_hash:
    mov eax, [late_state]
    xor edx, edx
    mov ecx, 3
    div ecx
    test edx, edx
    jnz late_go
    xor eax, eax                    /* retail punts at long yardage; the native chart decides */
    jmp late_set
late_go:
    mov ecx, [esp+8]
    call hail_mary                  /* native 206DD0: the end-of-half Hail Mary call stays in charge */
    test eax, eax
    jnz late_no
    mov eax, 1
    jmp late_set
late_no:
    mov eax, 4
late_set:
    mov [esp+44], eax               /* EAX slot of the pushad frame */
    add esp, 16
    popad
    popfd
    ret

.balign 4, 0xcc
yard: .float 91.44
eps: .float 0.0001
fifty: .float 50
five: .float 5
third: .float 0.33333334
late_end:
