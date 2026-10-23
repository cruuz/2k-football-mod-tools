/* QB accuracy on short and on-the-run throws. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * The pass accuracy routine 0x2D9700 adds an error E to every throw (pressure, throwing on the run, out of
 * range, lob touch) and turns it into a miss distance D = curve 0x50BE20(radius + E'), where radius is the
 * QB-to-target distance and E' = E scaled by the Pass Accuracy factor ONLY when E > 0. It then moves the
 * target D along an error heading: the receiver's lead direction (lateral routes), the QB-to-target line
 * (downfield routes) or, on the run, the QB's running direction, each with a random spread that keeps 90% of
 * misses within 90 degrees of that heading. Result, measured natively (b777 qb3): a set QB in the pocket is
 * exact to about 35 yd whatever his rating, but a QB on the move misses drags, outs, slants and digs by
 * 0.5-2.3 yd, always AHEAD of the receiver or out toward the sideline (the "always overthrown" ball), and the
 * miss does not depend on his Pass Accuracy at all (E is negative for human QBs on the run, so the rating
 * factor is never applied). CPU QBs on the run also throw knee-high (the height error that rides with D).
 *
 * place (jmp at 0x2D9F18, replacing "fstp [esp+0x14]; mov ebx,[ebp+8]"): performs both retail
 * instructions, then, only when D > 0:
 *   w    = clamp((40 yd - radius) / 20 yd, 0, 1)    full effect to 20 yd, retail from 40 yd (deep game kept)
 *   K    = curve k_acc(Pass Accuracy)                the QB's own rating ([esp+0x30], read by the routine)
 *   Keff = 1 + w * (K - 1)
 *   D *= Keff; the height error [esp+0x18] *= Keff
 *   with probability k_flip * w the error heading (ESI) turns 180 degrees, so misses fall behind the
 *   receiver as often as ahead of him (the native clamp at 0x2D9F99 still applies after this).
 * The native RNG (0x48B90) is drawn once per throw that has a miss. GPRs (except the ESI flip), EFLAGS and
 * the x87 stack are preserved; everything else the routine computes is retail.
 *
 * lead (b777 qb4; jmp at 0x2DAD97, replacing the 36-byte retail "add the placement offset" tail of the lead solver
 * 0x2DA8E0): when a moving receiver runs within 45 degrees of the throw line (quick outs, flats, bubbles, fades), the
 * solver moves the target 137.16 cm (1.5 yd, constant 0x4F0F74) sideways off his path toward the QB side, so on a
 * quick out or a flat the ball arrives 1.5 yd underneath him. None of the 68 side-catch (bucket 1) normal catch
 * records reaches 1.5 yd sideways (66 reach 1 yd), so he cannot take it in stride. Here the offset is scaled by
 *   w = clamp((depth - 8 yd) / 2 yd, 0, 1),  depth = (target z - line of scrimmage) x field direction
 * (the solver's own int +1/-1 at [esp+0x40]): no offset up to 8 yd past the line (and behind it), retail from 10 yd.
 * At w = 1 the arithmetic is the retail sequence (x 1.0 is exact), so intermediate and deep leads are byte-for-byte
 * retail. Only EAX (reloaded at 0x2DADBB), EFLAGS (dead there) and the two target floats change; x87 stack empty on
 * entry and exit, as in retail.
 *
 * back (b778 qa1; jmp at 0x2DAE12, replacing "mov [esp+0x1c], 91.44; jmp 0x2DAE5C" in the solver's second placement
 * block): for a target at or behind the line of scrimmage retail adds 1 yd downfield (along the offense direction) to a
 * moving receiver's target, so a back on a swing or flat is thrown a yard upfield of his path and reaches back for it.
 * When the receiver is a backfield player (field role byte [player+0x2C] = 10 halfback or 11 fullback) the offset is
 * 0; every other receiver, and every target past the line, keeps retail's 91.44 cm. The receiver is read from the
 * release frame: both solver calls in the release 0x2DAF10 pass it at the same slot, [ebp+0x34] inside the solver
 * (guarded span). Only EAX (reloaded at 0x2DAE5C) and EFLAGS change.
 *
 * screen (b778 qa1; the "je" at 0x226837 for route kind 9 in the route predictor 0x2266A0 now jumps here): retail
 * sends kind 9 (screen) and 10 (stem block) to a shortcut that aims at the receiver's spot when he stands and leaves
 * a moving receiver to the target routine's velocity lead. A screen back thrown to while he drifts back toward the QB
 * (b776 HB screen: "he starts running backwards") is then led further back. Here a MOVING kind-9 receiver whose
 * downfield velocity is below -0.5 yd/s takes the predictor's ordinary route path (his screen spot) instead; every
 * other case goes to the retail shortcut. EAX, ECX, EDX, EBX and the x87 stack are preserved.
 */
.intel_syntax noprefix
.code32
.text
.global place, lead, back, screen, code_end
.extern resume, curve, rng, lead_resume, back_resume, screen_route, screen_shortcut

place:
    fstp dword ptr [esp+0x14]                /* retail: D */
    pushfd
    pushad
    sub esp, 16                              /* [esp] = w; routine locals at esp+52 */
    fld dword ptr [esp+52+0x14]
    fcomp dword ptr ds:0x4e4180
    fnstsw ax
    test ah, 0x45
    jnz place_done                           /* no miss (D <= 0) or unordered: retail */
    fld dword ptr [k_far]
    fsub dword ptr [ebp+0x0c]                /* 40 yd - radius */
    fmul dword ptr [k_band_inv]
    fcom dword ptr ds:0x4e4180
    fnstsw ax
    test ah, 0x45
    jnz place_pop                            /* deep (w <= 0) or unordered: retail */
    fcom dword ptr ds:0x4e419c
    fnstsw ax
    test ah, 0x01
    jnz place_w
    fstp st(0)
    fld1
place_w:
    fstp dword ptr [esp]
    push dword ptr [esp+52+0x30]             /* Pass Accuracy, effective attribute 5 */
    mov ecx, offset k_acc_points
    mov edx, 6
    call curve                               /* 0x1B0AE0, ret 4: ST0 = K */
    fsub dword ptr ds:0x4e419c
    fmul dword ptr [esp]
    fadd dword ptr ds:0x4e419c                   /* Keff */
    fld st(0)
    fmul dword ptr [esp+52+0x14]
    fstp dword ptr [esp+52+0x14]             /* D * Keff */
    fmul dword ptr [esp+52+0x18]
    fstp dword ptr [esp+52+0x18]             /* height error * Keff */
    mov ecx, 0xe5fca0
    call rng                                 /* 0x48B90: ST0 = r in [0, 1) */
    fld dword ptr [esp]
    fmul dword ptr [k_flip]                  /* ST0 = p, ST1 = r */
    fcomp st(1)
    fnstsw ax
    fstp st(0)
    test ah, 0x45
    jnz place_done                           /* p <= r: keep the heading */
    add dword ptr [esp+16+4], 0x8000         /* the saved ESI: error heading + 180 degrees */
    jmp place_done
place_pop:
    fstp st(0)
place_done:
    add esp, 16
    popad
    popfd
    mov ebx, dword ptr [ebp+8]               /* retail */
    jmp resume                               /* 0x2D9F1F */

lead:                                        /* jmp at 0x2DAD97; EDI (lead flag) != 0, x87 stack empty */
    mov eax, dword ptr ds:0xe602ec           /* play context; EAX is reloaded at 0x2DADBB */
    fld dword ptr [esp+0x58]                 /* target z before the offset */
    fsub dword ptr [eax+0x18]                /* - line of scrimmage */
    fimul dword ptr [esp+0x40]               /* x field direction (+1/-1): depth past the line, cm */
    fsub dword ptr [k_lead_near]             /* - 8 yd */
    fmul dword ptr [k_lead_band_inv]         /* / 2 yd */
    ftst
    fnstsw ax
    test ah, 0x45
    jz lead_upper                            /* > 0 */
    fstp st(0)                               /* <= 8 yd, behind the line, or unordered: w = 0 */
    fldz
    jmp lead_apply
lead_upper:
    fcom dword ptr ds:0x4e419c
    fnstsw ax
    test ah, 0x01
    jnz lead_apply                           /* < 1 */
    fstp st(0)
    fld1                                     /* >= 10 yd: w = 1, retail */
lead_apply:                                  /* ST0 = w */
    fld dword ptr [esp+0x34]                 /* retail: sin(perpendicular heading) */
    fmul st(0), st(1)
    fmul dword ptr ds:0x4f0f74               /* retail: x 137.16 cm */
    fadd dword ptr [esp+0x50]
    fstp dword ptr [esp+0x50]
    fld dword ptr [esp+0x30]                 /* retail: cos(perpendicular heading) */
    fmul st(0), st(1)
    fmul dword ptr ds:0x4f0f74
    fadd dword ptr [esp+0x58]
    fstp dword ptr [esp+0x58]
    fstp st(0)
    jmp lead_resume                          /* 0x2DADBB */

back:                                        /* jmp at 0x2DAE12: target at/behind the line, ESI = offense heading */
    mov eax, dword ptr [ebp+0x34]            /* the receiver (release frame) */
    mov al, byte ptr [eax+0x2c]              /* field role */
    and al, 0xfe
    cmp al, 10                               /* 10 halfback, 11 fullback */
    mov eax, 0x42b6e148                      /* retail: 91.44 cm downfield */
    jne back_store
    xor eax, eax                             /* a back: no downfield offset, the ball meets him on his path */
back_store:
    mov dword ptr [esp+0x1c], eax
    jmp back_resume                          /* 0x2DAE5C */

screen:                                      /* je at 0x226837: route kind 9; EDI = receiver */
    push eax
    mov eax, dword ptr [edi+0x14]
    test byte ptr [eax], 0x38
    jz screen_retail                         /* standing: retail shortcut (his spot) */
    mov eax, dword ptr [edi+0x38]            /* his team: offense direction +1/-1 */
    mov eax, dword ptr [eax+8]
    mov eax, dword ptr [eax+0xc]
    fld dword ptr [eax+4]
    mov eax, dword ptr [edi+0x18]
    fmul dword ptr [eax+0x48]                /* downfield velocity, cm/s */
    fcomp dword ptr [k_back]
    fnstsw ax
    sahf
    jp screen_retail                         /* unordered: retail */
    jae screen_retail                        /* not drifting back: retail velocity lead */
    pop eax
    jmp screen_route                         /* 0x22683D: the ordinary route path, his screen spot */
screen_retail:
    pop eax
    jmp screen_shortcut                      /* 0x226A62 */

.balign 4
k_back: .float -45.72                        /* -0.5 yd/s */
k_far: .float 3657.6                         /* 40 yd */
k_band_inv: .float 0.000546806649            /* 1 / 20 yd */
k_flip: .float 0.5
k_lead_near: .float 731.52                      /* 8 yd */
k_lead_band_inv: .float 0.005468066492      /* 1 / 2 yd */
k_acc_points:                                /* (Pass Accuracy, miss scale) */
    .float 0.0, 1.0
    .float 0.55, 0.9
    .float 0.7, 0.62
    .float 0.8, 0.45
    .float 0.9, 0.3
    .float 1.0, 0.18
code_end:
