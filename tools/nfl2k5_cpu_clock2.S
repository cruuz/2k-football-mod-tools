/* EXPERIMENTAL / UNWITNESSED. b780 b-clock, GNU as --32. Modern CPU clock management (nfl2k5_cpu_clock2).
 *
 * Every entry below is reached from one pinned retail site (see mod_editor/core/nfl2k5_cpu_clock2.py, SITES).
 * Native helpers used (all retail USA, unchanged):
 *   late_native  0x205FE0  late window: Q3/Q4 with at most 300 s left in the half (26 callers)
 *   late_time    0x205FEF  its tail: half seconds <= 300 -> 1, else 0
 *   half_time    0x205F80  ST0 = seconds left in the half (returns with ECX = that float's bits)
 *   margin_fn    0x205F40  EAX = score margin of the team in ECX (clobbers EDX)
 *   need_fn      0x205F50  ST0 = time-needed estimate of the team in ECX (stored before every snap)
 *   distance_fn  0x203370  ST0 = offense distance to the goal line, cm
 *   permit_fn    0x207270  EAX = 1 when the team in ECX may call a timeout at this dead ball
 *   timer_stop   0xAF4F0   stop the game timer in ECX (the clock tick's own stop when time runs out)
 * No writable data: every decision reads live game state only.
 */
.intel_syntax noprefix
.code32
.text
.global estimate_lw, urgency_lw, hurry_lw, onside_need, four_minute_route, four_minute, early_timeout, half_kneel
.global kneel_runoff
.global ot_window
.extern late_native, late_time, half_time, margin_fn, need_fn, distance_fn, permit_fn
.extern snap_back, snap_special, snap_normal, poll_back, poll_return, poll_take, kneel_back, lineup_back
.extern timer_stop

/* ---- Two scores down: Q4 with up to 10:00 left counts as late for the team that needs two or more scores.
 * Site 0x20A79B inside the time-needed estimate 0x20A4D0 (EDI = team). Returns EAX like 0x205FE0; ECX and EDX are
 * kept (the native routine may clobber ECX, so no caller relies on it); the x87 stack is balanced. */
estimate_lw:
    push ecx
    mov ecx, edi
    call two_scores_late
    pop ecx
    ret

/* Site 0x18C0E8 inside the CPU huddle-state routine 0x18C0B0 (ESI = team): the no-huddle hurry test. */
hurry_lw:
    push ecx
    mov ecx, esi
    call two_scores_late
    pop ecx
    ret

/* ECX = team. EAX = late window (native), or 1 for a team down 9+ in Q4 with at most 600 s left. The native late
 * window and 0x205F80 return with ECX holding the half-seconds float, so ECX is saved around the native call. */
two_scores_late:
    push ecx
    call late_native
    pop ecx
    test eax, eax
    jnz 1f
    cmp dword ptr [0xe602c4], 4
    jne 1f
    push edx
    call margin_fn                    /* EAX = margin of ECX, EDX clobbered */
    pop edx
    cmp eax, -9
    mov eax, 0
    jg 1f
    call half_time
    fcomp dword ptr [c600]
    fnstsw ax
    test ah, 0x41                     /* C0|C3: half <= 600 */
    mov eax, 0
    jz 1f
    mov eax, 1
1:  ret

/* Site 0x207A36 inside the urgency routine 0x2079B0, reached only with a positive estimate. In Q4 outside the
 * native late window only estimate_lw can have produced that estimate (a team down 9+, at most 600 s left), so
 * the urgency curve clamp(1.5 - t/E, 0, 1) is used for it. */
urgency_lw:
    call late_native
    test eax, eax
    jnz 1f
    cmp dword ptr [0xe602c4], 4
    jne 1f
    call half_time
    fcomp dword ptr [c600]
    fnstsw ax
    test ah, 0x41
    mov eax, 0
    jz 1f
    mov eax, 1
1:  ret

/* Site 0x206ED9 inside the onside-kick test 0x206EB0 (ECX = kicking team): the onside test keeps seeing the
 * native estimate, which is zero outside the late window, so the two-score extension never adds onside kicks. */
onside_need:
    push ecx
    call late_native                  /* returns with ECX clobbered (0x205F80 pops its local into ECX) */
    pop ecx
    test eax, eax
    jz 1f
    jmp need_fn                       /* tail call, ECX = kicking team */
1:  fldz
    ret

/* ---- Four-minute offense. Two sites in the CPU snap delay 0x2D3360 (ESI = the snapping team's selector, EDI = the
 * selected PLAY, [ESP+0x14] = offense urgency, clock running). Retail runs the play clock down (snap with 0.8 to
 * 2.2 s left) only for a kneel, the field-goal run-down, or a field goal or punt PLAY in the last 120 s of Q2 or
 * Q4 (Q4 only with urgency <= 0).
 * four_minute_route, site 0x2D33D8 (displaced: cmp edi,[esi+0x3c]; je; cmp edi,[esi+0x40]; jne): field goal and
 * punt PLAYs keep the native path; any other PLAY of a leading offense in Q4 now takes the same Q2/Q4 branch.
 * four_minute, site 0x2D340C (displaced: mov ecx,[0xe6028c]; fld [ecx+0x10]): in that Q4 branch a leading offense
 * compares the clock with 300 s instead of 120 s. Resumes at fnstsw 0x2D341B. */
four_minute_route:
    cmp edi, dword ptr [esi+0x3c]     /* field goal PLAY */
    je 1f
    cmp edi, dword ptr [esi+0x40]     /* punt PLAY */
    je 1f
    cmp dword ptr [0xe602c4], 4
    jne 2f
    push eax
    push edx
    push ecx
    mov ecx, dword ptr [0xe60280]
    call margin_fn
    pop ecx
    test eax, eax
    pop edx
    pop eax
    jle 2f
1:  jmp snap_special                  /* 0x2D33E2: Q2/Q4 run-the-clock branch */
2:  jmp snap_normal                   /* 0x2D3427 */

four_minute:
    mov ecx, dword ptr [0xe6028c]
    fld dword ptr [ecx+0x10]
    push eax
    push edx
    push ecx
    mov ecx, dword ptr [0xe60280]
    call margin_fn
    pop ecx
    test eax, eax
    pop edx
    pop eax                           /* pops keep the flags of test */
    jle 1f
    fcomp dword ptr [c300]
    jmp snap_back
1:  fcomp dword ptr [c120]
    jmp snap_back

/* ---- Early defensive timeouts. Site 0x188614 in the CPU timeout poll 0x1885F0 (ESI = CPU team or 0, EAX =
 * game clock, clock running). Retail: a timeout needs at most 120 s on the clock and the two-minute warning (the
 * poll), and the native predicate 0x207050 also stops above 120 s. A CPU defense that trails in Q4 with more than
 * 120 s left now gets the predicate's own defense rule without those gates: timeout permitted (0x207270), the late
 * window, and the defense needs the ball back with time (estimate > 0 and t < estimate: about 2:55 when down 1 to 8,
 * 5:00 when down 9 or more). Above 120 s the native 0x207310 (offense must stop the clock, t <= 60) is always 0, so
 * the native poll would take the timeout: this path enters its tail 0x188722 with EDI pushed as the poll does.
 * Displaced: fld [eax+0x10]; fcomp [120]. The retail path resumes at fnstsw 0x18861D. */
early_timeout:
    test esi, esi
    jz 4f
    cmp esi, dword ptr [0xe60284]
    jne 4f
    cmp dword ptr [0xe602c4], 4
    jne 4f
    push eax
    push edx
    push ecx
    mov ecx, esi
    call margin_fn
    pop ecx
    test eax, eax
    pop edx
    pop eax
    jge 4f                            /* not trailing: retail */
    push eax
    fld dword ptr [eax+0x10]
    fcomp dword ptr [c120]
    fnstsw ax
    test ah, 0x41                     /* clock <= 120: retail gates */
    pop eax
    jnz 4f
    mov ecx, esi
    call permit_fn
    test eax, eax
    jz 3f
    call late_native
    test eax, eax
    jz 3f
    mov ecx, esi
    call need_fn                      /* ST0 = the defense's estimate */
    fldz
    fcomp st(1)
    fnstsw ax
    test ah, 0x01                     /* 0 < estimate */
    jz 2f
    call half_time                    /* ST0 = t, ST1 = estimate */
    fcompp
    fnstsw ax
    test ah, 0x01                     /* t < estimate */
    jz 3f
    push edi
    jmp poll_take                     /* 0x188722: the native timeout request */
2:  fstp st(0)
3:  jmp poll_return                   /* 0x18873C */
4:  fld dword ptr [eax+0x10]
    fcomp dword ptr [c120]
    jmp poll_back

/* ---- End-of-half kneel. Site 0x206F10, entry of the CPU kneel test (called by the native caller 0x20B180 and the
 * VIP situation key 0xF7010). Q2: kneel when the offense is on its own side (50 to 92 yards out), down 1 to 3, at
 * most 60 s left, its native estimate asks for no time (it is not trying to score), and the native kneel formula
 * (4 - defense timeouts - down) x play clock + current play clock + 15 > t holds. Other quarters: native. */
half_kneel:
    cmp dword ptr [0xe602c4], 2
    je 1f
    sub esp, 0xc                      /* displaced */
    push esi
    mov esi, dword ptr [0xe60280]
    jmp kneel_back                    /* 0x206F1A */
1:  push ebx
    push esi
    push edi
    sub esp, 8                        /* [esp] = t, [esp+4] = scratch */
    mov esi, dword ptr [0xe60280]
    test esi, esi
    jz 8f
    mov edx, dword ptr [0xe602ec]
    mov ebx, dword ptr [edx+4]        /* down */
    cmp ebx, 1
    jl 8f
    cmp ebx, 3
    jg 8f
    call half_time
    fst dword ptr [esp]
    fcomp dword ptr [c60]
    fnstsw ax
    test ah, 0x41                     /* t <= 60 */
    jz 8f
    call distance_fn
    fcom dword ptr [c4572]
    fnstsw ax
    test ah, 0x01                     /* closer than 50 yards: not on its own side */
    jnz 7f
    fcomp dword ptr [c8412]
    fnstsw ax
    test ah, 0x41                     /* farther than 92 yards (inside its own 8): no kneel */
    jz 8f
    mov ecx, esi
    call need_fn
    fcomp dword ptr [c0]
    fnstsw ax
    test ah, 0x41                     /* estimate <= 0 */
    jz 8f
    mov eax, dword ptr [0xe60284]
    test eax, eax
    jz 8f
    mov eax, dword ptr [eax+8]
    test eax, eax
    jz 8f
    mov ecx, 4
    sub ecx, dword ptr [eax+4]        /* defense timeouts */
    sub ecx, ebx
    mov dword ptr [esp+4], ecx
    fild dword ptr [esp+4]
    fmul dword ptr [0xe602ac]         /* native play-clock reset */
    mov eax, dword ptr [0xe6028c]
    test byte ptr [eax+0x18], 6
    jnz 6f
    mov eax, dword ptr [0xe60294]
    fadd dword ptr [eax+0x10]         /* current play clock */
6:  fadd dword ptr [c15]
    fcomp dword ptr [esp]
    fnstsw ax
    test ah, 0x41                     /* formula <= t: no kneel */
    jnz 8f
    mov eax, 1
    jmp 9f
7:  fstp st(0)
8:  xor eax, eax
9:  add esp, 8
    pop edi
    pop esi
    pop ebx
    ret

/* ---- Kneel runoff. Site 0x189080, entry of the line-up step called from the native dead ball 0xA03DC (through
 * Decided clock or Era rules when they are installed) and 0x18DFF6. After a Take Knee play (PLAY header has the
 * knee bits 0x408000) in Q2 or Q4, with the clock running, when the downs left can kneel the whole clock out
 * ((4 - down - defense timeouts) x play clock >= clock), set the game timer to 0:00 and stop it, the state the clock
 * tick 0x157D40 leaves when time runs out during a play; its native dispatcher 0xA2970 then ends the half or the game.
 * Displaced: push ecx; mov eax,[0xe60280]. Resumes at 0x189086. */
kneel_runoff:
    pushfd
    pushad
    cmp dword ptr [0xa83a18], 3
    jne 9f
    cmp dword ptr [0xe602b4], 4
    jne 9f
    mov eax, dword ptr [0xe602b8]
    cmp eax, 18
    je 1f
    cmp eax, 12
    jne 9f
1:  mov eax, dword ptr [0xe602c4]
    cmp eax, 2
    je 2f
    cmp eax, 4
    jne 9f
2:  mov esi, dword ptr [0xe60280]
    test esi, esi
    jz 9f
    mov eax, dword ptr [esi+0xc]
    test eax, eax
    jz 9f
    mov eax, dword ptr [eax+0xc]      /* selected PLAY */
    test eax, eax
    jz 9f
    mov eax, dword ptr [eax+4]        /* PLAY header */
    and eax, 0x4081c0                 /* knee bits and the special-teams family */
    cmp eax, 0x408000
    jne 9f
    mov ecx, dword ptr [0xe6028c]
    test ecx, ecx
    jz 9f
    test byte ptr [ecx+0x18], 0xe     /* stopped, paused or counting up: no */
    jnz 9f
    mov eax, dword ptr [ecx+0x10]
    test eax, eax
    jle 9f                            /* positive finite seconds only */
    cmp eax, 0x7f800000
    jae 9f
    mov edx, dword ptr [0xe602ec]
    test edx, edx
    jz 9f
    mov ebx, 4
    sub ebx, dword ptr [edx+4]        /* downs left after this one */
    mov edi, dword ptr [0xe60284]
    test edi, edi
    jz 9f
    mov edi, dword ptr [edi+8]
    test edi, edi
    jz 9f
    sub ebx, dword ptr [edi+4]        /* each defense timeout saves one play clock */
    jle 9f
    push ebx
    fild dword ptr [esp]
    add esp, 4
    fmul dword ptr [0xe602ac]
    fcomp dword ptr [ecx+0x10]
    fnstsw ax
    test ah, 0x01                     /* burnable < clock: no */
    jnz 9f
    mov dword ptr [ecx+0x10], 0       /* time is up, exactly as when it runs out during a play: */
    call timer_stop                   /* stopped at 0:00, so no timeout path acts on it; the clock tick */
9:  popad                             /* 0x157D40 then ends the period through its native dispatcher */
    popfd
    push ecx                          /* displaced */
    mov eax, dword ptr [0xe60280]
    jmp lineup_back

/* ---- Overtime clock (separate build choice). Site 0x205FE0, entry of the late window. Q3/Q4: native. Overtime
 * counts as late only where the end of the period can end the game: franchise regular season (mode 7, period 5,
 * a tie), or a non-playoff mode while the scores differ (modern overtime). Playoffs (modes 5 and 6) play another
 * period, so their overtime clock decides nothing. Registers other than EAX are kept, as the native routine does. */
ot_window:
    mov eax, dword ptr [0xe602c4]
    cmp eax, 3
    je 4f
    cmp eax, 4
    je 4f
    jl 3f
    mov eax, dword ptr [0xe5ff80]
    cmp eax, 5
    je 3f
    cmp eax, 6
    je 3f
    cmp eax, 7
    jne 1f
    cmp dword ptr [0xe602c4], 5
    jne 3f
    jmp 4f
1:  push ecx
    mov ecx, dword ptr [0xe5fc28]     /* home score record */
    mov eax, dword ptr [0xe5fc68]     /* away score record */
    test ecx, ecx
    jz 2f
    test eax, eax
    jz 2f
    mov ecx, dword ptr [ecx]
    cmp ecx, dword ptr [eax]
    pop ecx
    je 3f
    jmp 4f
2:  pop ecx
3:  xor eax, eax
    ret
4:  jmp late_time

    .balign 4
c600:   .float 600.0
c300:   .float 300.0
c120:   .float 120.0
c60:    .float 60.0
c15:    .float 15.0
c0:     .float 0.0
c4572:  .float 4572.0
c8412:  .float 8412.48
