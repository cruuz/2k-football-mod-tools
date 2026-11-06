/* Scramble blocking (b780 cv7): receivers and backs block for a quarterback who runs past the line.
 * EXPERIMENTAL. Off in every preset until Noah plays it.
 *
 * Retail: a quarterback who tucks the ball and runs never tells his teammates. The CPU passer task 0x198540
 * makes him a ball carrier a yard short of the line (0x2E36F0, no possession event); a human quarterback
 * keeps his passer task. The receivers' play script is still on its route legs, so they finish their routes.
 *
 * tick: entered by "call tick" at 0x214FC0, the AI tick's first instruction (mov eax, [0xE602B8]); it runs
 * once per simulation step before any player's task. While a play is live (state 14) on a down or a try
 * (phase 4 or 3), the ball is held (ball state 2) by a quarterback (field role 0, the retail slide test),
 * no forward pass has been thrown on the play ([[0xE602EC]+0x1B0] == 0, the thrower 0xB6700 stores) and he
 * is at least half a yard past the line of scrimmage in his team's direction (the 0x198170 rule), every
 * CPU-controlled tight end, wide receiver, halfback or fullback of his team who is not already in a block
 * task (the game's own test 0x23ABA0: task+0x90 == 5) and not engaged with another player (0x231EE0) gets
 * the game's drive block exactly the way the game converts a blocker mid-play (0x23A010 and 0x23B040):
 * clear the script wait bits 0x4000 / 0x40000 of AI+0x420, clear the block kind bits of L+0x18C, then
 * 0x23F450(player, type 0: drive, (0, 0, 1, 0, 182.88, team heading, +inf)). Each formation slot converts
 * at most once a play (state bit mask, cleared whenever the play is not live), so a block the game ends
 * itself (the runner passed him, 0x23AA40) is never re-armed.
 *
 * One blocker per man: after the install, and after every target refresh of these blocks, a target that
 * another teammate's block task already has (task+0x40) is replaced: by the previous target if it is still
 * free, else by the nearest free defender, else the game's choice stands. The refresh is per task: the
 * block manager 0x23DBE0 calls task+0xA0 (ECX = player), which these tasks point at "refresh" (the game's
 * refresh 0x23CD60 first). No other player's block changes.
 */
.intel_syntax noprefix
.code32
.text
.global tick, refresh, code_end
.extern state, installer, native_refresh, engaged

tick:
    pushad
    cmp dword ptr [0xe602b8], 14            /* the play is live */
    jne reset
    mov eax, dword ptr [0xe602b4]
    cmp eax, 4                              /* a down from scrimmage */
    je phase_ok
    cmp eax, 3                              /* a try after a touchdown */
    jne done
phase_ok:
    cmp dword ptr [0xe602c0], 2             /* a player holds the ball */
    jne done
    mov eax, dword ptr [0xe5fc00]
    test eax, eax
    jz done
    mov ebp, dword ptr [eax]                /* the holder */
    test ebp, ebp
    jz done
    cmp dword ptr [ebp+0x1c], 1             /* a player object */
    jne done
    cmp byte ptr [ebp+0x2c], 0              /* the quarterback */
    jne done
    mov ebx, dword ptr [0xe602ec]
    test ebx, ebx
    jz done
    cmp dword ptr [ebx+0x1b0], 0            /* no forward pass thrown on this play */
    jne done
    mov eax, dword ptr [ebp+0x18]
    fld dword ptr [eax+0x38]
    fsub dword ptr [ebx+0x18]               /* z - line of scrimmage */
    mov eax, dword ptr [ebp+0x38]
    mov eax, dword ptr [eax+8]
    mov eax, dword ptr [eax+0xc]
    fld dword ptr [eax+4]                   /* the team's direction */
    fcomp dword ptr [0x4e4180]
    fnstsw ax
    test ah, 0x41
    jz forward
    fchs                                    /* direction <= 0: the game's -1 */
forward:
    fcomp dword ptr [half_yard]
    fnstsw ax
    test ah, 0x01                           /* short of half a yard past, or NaN */
    jnz done
    mov edi, dword ptr [ebp+0x38]
    mov edi, dword ptr [edi+4]              /* his team's first player */
    mov esi, 22
mate:
    test edi, edi
    jz done
    cmp edi, ebp
    je mate_next
    cmp dword ptr [edi+0x48], 0             /* on the field */
    jne mate_next
    movzx eax, byte ptr [edi+0x2c]
    sub eax, 8                              /* 8 TE, 9 WR, 10 HB, 11 FB */
    cmp eax, 3
    ja mate_next
    mov eax, dword ptr [edi+0xc]
    test eax, eax
    jz mate_next
    cmp dword ptr [eax], -1                 /* CPU-controlled */
    jne mate_next
    movzx ecx, byte ptr [edi+0x2e]          /* formation slot */
    cmp ecx, 15
    ja mate_next
    bt dword ptr [state], ecx               /* already converted on this play */
    jc mate_next
    mov eax, dword ptr [edi+0x20]
    test eax, eax
    jz mate_next
    mov eax, dword ptr [eax+0x310]
    test eax, eax
    jz mate_next
    cmp dword ptr [eax+0x90], 5             /* already blocking */
    je mate_next
    mov ecx, dword ptr [edi+0x10]
    call engaged                            /* 0x231EE0: in an engaged pair */
    test eax, eax
    jnz mate_next
    movzx ecx, byte ptr [edi+0x2e]
    bts dword ptr [state], ecx
    call convert
mate_next:
    mov edi, dword ptr [edi+0x34]
    dec esi
    jnz mate
done:
    popad
    mov eax, dword ptr [0xe602b8]           /* the displaced instruction */
    ret
reset:
    mov dword ptr [state], 0
    jmp done

/* EDI = player. The game's mid-play drive conversion (0x23A010 / 0x23B040), then one blocker per man. */
convert:
    push ebx
    mov eax, dword ptr [edi+0x20]
    and dword ptr [eax+0x420], 0xfffbbfff
    mov eax, dword ptr [edi+0x10]
    and dword ptr [eax+0x18c], 0xfffffff8
    mov eax, dword ptr [edi+0x38]
    mov eax, dword ptr [eax+8]
    mov eax, dword ptr [eax+0xc]
    fld dword ptr [eax+4]
    fcomp dword ptr [0x4e4180]
    fnstsw ax
    xor edx, edx
    test ah, 0x41
    jz heading_up
    mov edx, 0x8000
heading_up:
    push 0x7f800000                         /* no time limit */
    push edx                                /* the team's upfield heading */
    push 0x4336e148                         /* 182.88: the zone point 2 yards upfield, as 0x23A010 */
    push 0
    push 1                                  /* from the player's own position */
    push 0                                  /* selector sub-mode 0 */
    push 0
    xor edx, edx                            /* block type 0: drive */
    mov ecx, edi
    call installer                          /* 0x23F450, ret 0x1C */
    mov eax, dword ptr [edi+0x20]
    mov eax, dword ptr [eax+0x310]
    cmp dword ptr [eax+0x90], 5
    jne convert_out
    mov dword ptr [eax+0xa0], offset refresh
    xor ebx, ebx                            /* no previous target */
    call dedupe
convert_out:
    pop ebx
    ret

/* Entered through task+0xA0 by the block manager 0x23DBE0: ECX = player. */
refresh:
    push ebx
    push edi
    mov edi, ecx
    mov eax, dword ptr [edi+0x20]
    mov eax, dword ptr [eax+0x310]
    mov ebx, dword ptr [eax+0x40]           /* the previous target */
    call native_refresh                     /* 0x23CD60, ECX = player */
    call dedupe
    pop edi
    pop ebx
    ret

/* EDI = player, EBX = previous target or 0. Keeps the game's target unless a teammate's block has him. */
dedupe:
    push eax
    push edx
    push esi
    mov esi, dword ptr [edi+0x20]
    mov esi, dword ptr [esi+0x310]
    mov edx, dword ptr [esi+0x40]
    test edx, edx
    jz dedupe_out                           /* no target: the game's fallback */
    call claimed
    test eax, eax
    jz dedupe_out
    mov edx, ebx
    test edx, edx
    jz dedupe_pick
    cmp dword ptr [edx+0x48], 0
    jne dedupe_pick
    call claimed
    test eax, eax
    jnz dedupe_pick
    mov dword ptr [esi+0x40], edx           /* the previous target is still free */
    jmp dedupe_out
dedupe_pick:
    call nearest
    test eax, eax
    jz dedupe_out                           /* nobody free: the game's choice */
    mov dword ptr [esi+0x40], eax
dedupe_out:
    pop esi
    pop edx
    pop eax
    ret

/* EDI = player, EDX = candidate: EAX = 1 when another teammate's block task targets him. */
claimed:
    push ecx
    push esi
    mov esi, dword ptr [edi+0x38]
    mov esi, dword ptr [esi+4]
    mov ecx, 22
claimed_loop:
    test esi, esi
    jz claimed_no
    cmp esi, edi
    je claimed_next
    cmp dword ptr [esi+0x48], 0
    jne claimed_next
    mov eax, dword ptr [esi+0x20]
    test eax, eax
    jz claimed_next
    mov eax, dword ptr [eax+0x310]
    test eax, eax
    jz claimed_next
    cmp dword ptr [eax+0x90], 5
    jne claimed_next
    cmp dword ptr [eax+0x40], edx
    je claimed_yes
claimed_next:
    mov esi, dword ptr [esi+0x34]
    dec ecx
    jnz claimed_loop
claimed_no:
    xor eax, eax
    pop esi
    pop ecx
    ret
claimed_yes:
    mov eax, 1
    pop esi
    pop ecx
    ret

/* EDI = player: EAX = the nearest defender on the field whom no teammate's block has, or 0. Like the game's
 * selector 0x2FAFF0, a defender more than 3 yards behind the ball (in the player's direction) is not a choice. */
nearest:
    push ebx
    push ecx
    push edx
    push esi
    push ebp
    sub esp, 8                              /* [esp] = direction sign, [esp+4] = depth limit */
    mov eax, dword ptr [edi+0x38]
    mov eax, dword ptr [eax+8]
    mov eax, dword ptr [eax+0xc]
    fld1
    fld dword ptr [eax+4]
    fcomp dword ptr [0x4e4180]
    fnstsw ax
    test ah, 0x41
    jz sign_up
    fchs
sign_up:
    fst dword ptr [esp]
    mov eax, dword ptr [0xe5fc00]
    mov eax, dword ptr [eax+0x14]
    fmul dword ptr [eax+8]                  /* ball z * sign */
    fsub dword ptr [three_yards]
    fstp dword ptr [esp+4]
    xor ebx, ebx
    mov ebp, dword ptr [edi+0x18]
    mov esi, dword ptr [edi+0x38]
    mov esi, dword ptr [esi]                /* the other team */
    mov esi, dword ptr [esi+4]
    fld dword ptr [infinity]
    mov ecx, 22
nearest_loop:
    test esi, esi
    jz nearest_end
    cmp dword ptr [esi+0x48], 0
    jne nearest_next
    mov eax, dword ptr [esi+0x18]
    fld dword ptr [eax+0x38]
    fmul dword ptr [esp]
    fcomp dword ptr [esp+4]
    fnstsw ax
    test ah, 0x01                           /* behind the limit, or NaN */
    jnz nearest_next
    mov edx, esi
    call claimed
    test eax, eax
    jnz nearest_next
    mov eax, dword ptr [esi+0x18]
    fld dword ptr [eax+0x30]
    fsub dword ptr [ebp+0x30]
    fmul st(0), st(0)
    fld dword ptr [eax+0x38]
    fsub dword ptr [ebp+0x38]
    fmul st(0), st(0)
    faddp st(1), st(0)
    fcom st(1)
    fnstsw ax
    and ah, 0x45
    cmp ah, 1                               /* strictly nearer and ordered */
    jne nearest_drop
    fstp st(1)
    mov ebx, esi
    jmp nearest_next
nearest_drop:
    fstp st(0)
nearest_next:
    mov esi, dword ptr [esi+0x34]
    dec ecx
    jnz nearest_loop
nearest_end:
    fstp st(0)
    mov eax, ebx
    add esp, 8
    pop ebp
    pop esi
    pop edx
    pop ecx
    pop ebx
    ret

    .balign 4
half_yard:
    .float 45.72
three_yards:
    .float 274.32
infinity:
    .long 0x7f800000
code_end:
