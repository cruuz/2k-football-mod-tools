/* Defenders dive only for balls they can reach. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * The ball-play decision 0x1F52C0 (only caller: the behavior-37 reaction task 0x2E7240, i.e. a defender reacting to
 * the throw) returns 2, "play the ball" (action 0x61, a leap or swat), whenever the ball passes within 3 yards
 * (0x4EDD28) of where he stands now, 0.3 to 0.6 s ahead and below his reach. It never asks whether he is moving
 * toward that point or whether the receiver gets the ball first.
 *
 * window (call at 0x1F56FF, replacing "fld [esp+0x18]; fcomp [0x4EDD28]; fnstsw ax; test ah,5; jp 0x1F55CF",
 * followed there by "test eax, eax; jz 0x1F55CF" and NOPs; EAX is dead at the site) returns EAX = 1 to keep the
 * native result 2 or 0 for result 0 (he keeps running and the decision runs again next tick):
 *   - retail when the ball is not inside 3 yd (0) or is within a yard (1: the catch try lost its roll), when the
 *     defender is not CPU controlled ([[ESI+0x0C]] != -1), or when the ball's path is degenerate;
 *   - receiver first: 0 when the closest point is more than BEYOND x 0.3 s of flight past the stored catch point
 *     (0xBF0DF0, valid 0xBF0E08 == 1, intended receiver [0xE3C000] != 0, and still within a yard of the ball's line,
 *     so a tipped ball is not judged by a stale point), i.e. the ball reaches the receiver first;
 *   - reach: beyond REACH he must close the rest before the ball gets there: 1 only when
 *     dist x (dist - REACH) < (his velocity . (Q - D)) x t, where t is the ball's time to the closest point Q.
 * Frame of 0x1F52C0 (F = ESP + 4 at entry): F+0x18 dist, F+0x20 Q (ball at the closest time), F+0x30 D (him, y =
 * reach height), F+0x40 the ball 0.3 s ahead, F+0x50 the ball 0.6 s ahead. Only EAX and EFLAGS change (EAX is
 * dead at the site; the "test eax, eax" after the call sets the flags); the x87 stack is left as it was.
 */
.intel_syntax noprefix
.code32
.text
.global window, code_end, k_reach, k_beyond, k_line2

.set F, 20                                   /* sub esp 16: the frame is at ESP + F */

window:
    sub esp, 16                              /* [esp] ux, [esp+4] uz, [esp+8] uu, [esp+12] t */
    fld dword ptr [esp+F+0x18]
    fcomp dword ptr [0x4edd28]               /* 3 yd, retail */
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    jne refuse                               /* not inside 3 yd, or unordered: retail result 0 */
    fld dword ptr [esp+F+0x18]
    fcomp dword ptr [0x4e72b8]               /* 1 yd */
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    je allow                                 /* within a yard: retail */
    mov eax, [esi+0xc]
    cmp dword ptr [eax], -1
    jne allow                                /* not CPU controlled: retail */
    fld dword ptr [esp+F+0x50]
    fsub dword ptr [esp+F+0x40]
    fst dword ptr [esp]                      /* ux: the ball's horizontal travel over 0.3 s */
    fmul st(0), st(0)
    fld dword ptr [esp+F+0x58]
    fsub dword ptr [esp+F+0x48]
    fst dword ptr [esp+4]                    /* uz */
    fmul st(0), st(0)
    faddp st(1), st(0)
    fst dword ptr [esp+8]                    /* uu */
    fcomp dword ptr [0x4e4180]
    fnstsw ax
    test ah, 0x45
    jnz allow                                /* uu <= 0 or unordered: retail */
    cmp dword ptr [0xbf0e08], 1
    jne reach
    cmp dword ptr [0xe3c000], 0
    je reach
    fld dword ptr [0xbf0df0]
    fsub dword ptr [esp+F+0x40]
    fmul dword ptr [esp+4]                   /* (catch x - A x) uz */
    fld dword ptr [0xbf0df8]
    fsub dword ptr [esp+F+0x48]
    fmul dword ptr [esp]                     /* (catch z - A z) ux */
    fsubp st(1), st(0)                       /* cross = (catch - A) x u; its sign does not matter */
    fmul st(0), st(0)                        /* cross^2 = (off-line distance)^2 x uu */
    fld dword ptr [esp+8]
    fmul dword ptr [k_line2]                 /* uu x (1 yd)^2, cross^2 */
    fcompp
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    je reach                                 /* catch point off the ball's line (a tipped ball): skip */
    fld dword ptr [esp+F+0x20]
    fsub dword ptr [0xbf0df0]
    fmul dword ptr [esp]
    fld dword ptr [esp+F+0x28]
    fsub dword ptr [0xbf0df8]
    fmul dword ptr [esp+4]
    faddp st(1), st(0)                       /* s = (Q - catch point) . u */
    fld dword ptr [esp+8]
    fmul dword ptr [k_beyond]                /* uu x BEYOND, s */
    fcompp
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    je refuse                                /* uu x BEYOND < s: the receiver gets the ball first */
reach:
    fld dword ptr [esp+F+0x18]
    fcomp dword ptr [k_reach]
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    je allow                                 /* inside REACH: retail */
    fld dword ptr [esp+F+0x20]
    fsub dword ptr [esp+F+0x40]
    fmul dword ptr [esp]
    fld dword ptr [esp+F+0x28]
    fsub dword ptr [esp+F+0x48]
    fmul dword ptr [esp+4]
    faddp st(1), st(0)                       /* (Q - A) . u */
    fdiv dword ptr [esp+8]                   /* fraction of the 0.3-0.6 s stretch */
    fadd dword ptr [k_one]
    fmul dword ptr [0x4efe0c]                /* t = 0.3 x (1 + fraction) */
    fstp dword ptr [esp+12]
    mov eax, [esi+0x18]
    fld dword ptr [esp+F+0x20]
    fsub dword ptr [esp+F+0x30]
    fmul dword ptr [eax+0x40]
    fld dword ptr [esp+F+0x28]
    fsub dword ptr [esp+F+0x38]
    fmul dword ptr [eax+0x48]
    faddp st(1), st(0)                       /* v . (Q - D) */
    fmul dword ptr [esp+12]                  /* rhs = v . (Q - D) x t */
    fld dword ptr [esp+F+0x18]
    fld st(0)
    fsub dword ptr [k_reach]
    fmulp st(1), st(0)                       /* lhs = dist x (dist - REACH), rhs */
    fcompp
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    je allow                                 /* lhs < rhs: he gets there in time */
    cmp ah, 0x45
    je allow                                 /* unordered: retail */
refuse:
    xor eax, eax
    jmp done
allow:
    mov eax, 1
done:
    add esp, 16
    ret

.balign 4
k_reach: .float 137.16                       /* REACH = 1.5 yd */
k_beyond: .float 0.1                         /* BEYOND = 0.03 s of flight past the catch point (0.03 / 0.3) */
k_line2: .float 8361.2736                    /* (1 yd = 91.44 cm)^2: the catch point must lie on the ball's line */
k_one: .float 1.0
code_end:
