/* EXPERIMENTAL. GNU as --32. CPU money downs, Modern 2 variant b81f (beta 81): fake kicks at real NFL rates.
 *
 * Installed IN PLACE over the native fake lottery of the scrimmage dispatcher 0x20B180, the 98 bytes 0x20B258..0x20B2B9
 * (assembled for that address; the owner guards the whole dispatcher). Retail reached 0x20B258 after the field-goal, punt,
 * Hail Mary and kneel tests had all said no; with time to spare and the cached draw above 0.95 it returned the
 * field-goal or punt category on a fourth down the game had decided to go for, and the commit 0x20B670 re-ran the kick
 * test, read "no" and ran a fake (any distance, about 5% of those downs). That entry now answers the ordinary category,
 * as retail did for every other draw, and the fake decision moves to one place:
 *
 * fake_gate: called from 0x20B6F2 in the commit instead of "fake flag = (re-test said no)". EBX = the category record
 * (0x11 punt, 0x13 field goal). Downs 1 to 3: never a fake (a kick there is the native end-of-half or overtime kick).
 * Fourth down with 2 yards or less to go: a fake with the league's rate for that kick, drawn from the game's match RNG
 * (0x48B90 on 0xE5FCA0). Otherwise the real kick. Returns ESI = fake flag; clobbers EAX, ECX, EDX and flags (the commit
 * reloads them); the x87 stack is balanced.
 *
 * two_point_threshold: the try lottery in 0x209FE0 (0x20A01E "fcomp [0.95]") reads this value instead, so a two-point try
 * comes from the kick formation 1.76% of the time instead of 5%.
 *
 * Rates: nflverse play-by-play, regular season (docs in nfl2k5_cpu_money_downs.FAKE_RATES).
 */
.intel_syntax noprefix
.code32
.text
.global ordinary, fake_gate, short_cm, p_punt, p_fg, two_point_threshold, fakes_end
.extern native_category, rng_uniform

ordinary:
    add esp, 8                      /* the dispatcher's frame, as at 0x20B2CC */
    jmp native_category

fake_gate:
    xor esi, esi
    mov eax, [0xe602ec]
    test eax, eax
    jz fake_done
    cmp dword ptr [eax+4], 4
    jne fake_done                   /* downs 1 to 3: a real kick */
    fld dword ptr [eax+0x28]
    fsub dword ptr [eax+0x18]
    fabs
    fcomp dword ptr short_cm
    fnstsw ax
    test ah, 0x41
    jz fake_done                    /* more than 2 yards to go: a real kick */
    mov ecx, 0xe5fca0
    call rng_uniform                /* ST0 = uniform [0,1); preserves ECX, EBX, ESI, EDI */
    movzx eax, byte ptr [ebx+4]
    and eax, 2                      /* 0x11 punt -> p_punt, 0x13 field goal -> p_fg */
    fcomp dword ptr [p_punt+eax*2]
    fnstsw ax
    test ah, 1
    jz fake_done                    /* draw >= rate: a real kick */
    inc esi
fake_done:
    ret

.balign 4, 0xcc
short_cm: .float 182.89             /* 2 yards (182.88 cm) plus 0.01 cm */
p_punt: .float 0.037                /* 4th and 1-2: 45 fake punts in 1,210 punt-formation snaps, 2021-2025 */
p_fg: .float 0.0022                 /* 12 fake field goals in 5,364 field-goal-formation snaps, 2021-2025 */
two_point_threshold: .float 0.9824  /* 14 of 794 two-point tries from the kick formation, 2020-2025 */
fakes_end:
