/* DESIGN: bounded replacement routines. Sources and assumptions are in
 * data/nfl2k5_franchise_economy.json. Units are game $1000, at 1:4 dollars.
 * PROVED OFFLINE: native ABIs are covered by the Unicorn tests.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FAST __attribute__((fastcall))
#define STD __attribute__((stdcall))
#define SECTION(s) __attribute__((section(s), used))
#include "generated_tables.h"

/* b778 fa2: retail routines called directly (addresses bound in assemble.py's
 * linker script), so each call is a 5-byte rel32 instead of mov/call reg. */
extern float FAST n_rating(u8 *p, unsigned boosted);              /* 0x246D80 */
extern void FAST n_recount(u8 *team);                              /* 0xC3F00 payroll and count */
extern unsigned FAST n_human(u8 *team);                            /* 0x13EC30 */
extern u8 *FAST n_team(unsigned index);                            /* 0xC4C50 */
extern unsigned n_teams(void);                                     /* 0xC4BE0 */
extern unsigned n_roster_limit(void);                              /* 0x247AF0: 65 offseason, 54 season */
extern unsigned FAST n_salary(u8 *p);                              /* 0xE6380 this season's base */
extern unsigned FAST n_base(unsigned value, unsigned kind, unsigned bonus, unsigned index, unsigned len); /* 0xE6040 */
extern unsigned FAST n_prorated(unsigned value, unsigned bonus, unsigned len);                         /* 0xE6020 */
extern float FAST n_frand(void *rng);                              /* 0x48B90 */
extern unsigned FAST n_rand(void *rng);                            /* 0x48B50 */
extern int STD n_trunc(float value);                               /* 0x322260 cvttss2si */
extern void FAST n_release(u8 *team, u8 *p, unsigned to_list, unsigned log); /* 0x2BD900 */
extern unsigned STD n_cpu_sign(u8 *team, unsigned pos, int budget, void *menu); /* 0x322BB0 */
extern void FAST n_cut_to(u8 *team, unsigned count);              /* 0x2BF9A0 */
extern void n_prune(void);                                          /* 0x2BB9A0: the trade board's pruner */
void FAST economy_release(u8 *team, u8 *p);
unsigned economy_points(u8 *p);
extern void FAST n_need_low(int *need, u8 *team);                  /* 0x2BD880 count - native minimum */
extern void FAST n_need_want(int *need, u8 *team);                 /* 0x2BD8C0 count - wanted depth */
extern unsigned FAST n_at_position(u8 *team, unsigned pos);        /* 0xC3CB0 */
extern unsigned FAST n_minimum_at(unsigned pos);                   /* 0x2BD410 native minimum table */
extern unsigned FAST n_wanted_at(unsigned pos);                    /* 0x2BD400 native wanted depth */
#define RNG ((void *)0xe5fca0)
#define FA_LIST ((u32 *)(*(u8 **)0xb72918 + 0x38))
#define FLOOR_PLAYERS 50            /* Noah 10/22: "They should never have less than 50." */
#define PROVE_IT 0.70f              /* "a high overall": about a top-30 player on most clubs */
#define CPU(t) (!n_human(t) || *(u32 *)0xe6013c == 1)
#define ROOM(t) (economy_cap(t, 1, 0) - *(int *)((t) + 0x124))
#define UNSIGNED_WEEKS(p) ((p)[0x25] >> 5)
#define PROVE_IT_FREE_AGENT(p) (!((p)[0x24] & 15) && UNSIGNED_WEEKS(p) >= 2)
int FAST economy_cap(u8 *team, unsigned with_penalty, unsigned year);
unsigned FAST economy_best_room(u8 *p, u8 **club);
/* b780 econ3 (revision 7): window roster_n (defined at the end). */
extern const u8 cut_rows[4][17];
unsigned FAST economy_full(u8 *team, unsigned pos);
unsigned FAST economy_offer_room(u8 *offer);
unsigned club_level(u8 *team, unsigned pos, float him, unsigned busy);
void economy_need(int *need, u8 *team, unsigned want);
int FAST economy_vet_short(u8 *team);
/* b81 economy revision 10 (defined at the end) */
unsigned FAST economy_years(u8 *p);
int FAST economy_reserve(u8 *team);
int FAST economy_usable_room(u8 *team);
int FAST economy_fill_budget(u8 *team);
void FAST economy_camp(u8 *team, void *menu);
void FAST economy_clear_cap(u8 *team);
u8 *economy_hole_first(u8 *p, unsigned ask, u8 *club);
u8 *economy_prove_club(u8 *p, unsigned ask);
u8 *FAST economy_vet_pick(u8 *team, u8 *proposed);

static unsigned maximum(unsigned a, unsigned b) { return a > b ? a : b; }
static unsigned minimum(unsigned a, unsigned b) { return a < b ? a : b; }

static unsigned economy_floor(unsigned pro);

/* b81 economy revision 10: the price is a rank on the real market curve (price_of, below), not a cube of the overall;
 * the surplus (trades), floor_apy and the 60,000 clamp are as before; a free agent asks economy_ask. The old body's
 * 540 bytes stay this routine's: the linker pads up to economy_floor, so economy_floor, economy_penalty and
 * economy_cap keep their addresses (the team-building owner calls economy_cap). */
unsigned floor_of(unsigned pro);
unsigned price_of(u8 *p, unsigned aging);
unsigned economy_ask(u8 *p, unsigned value, unsigned floor);
SECTION(".value") unsigned FAST economy_value(u8 *p, unsigned floor_apy,
                                              unsigned surplus, unsigned aging, unsigned years) {
    unsigned pos = p[0x35], pro = p[0x25] & 31;
    if (pos >= 17) return 0;
    unsigned floor = floor_of(pro), value = price_of(p, aging);
    if (value < floor) value = floor;
    if (surplus && (p[0x24] & 15) && (p[0x27] & 15)) {
        int salary = (int)n_salary(p) + *(u16 *)(p + 10) * (p[0x26] >> 4) / (p[0x27] & 15);
        int v = (int)value + ((int)value - salary) * (int)minimum(years, 4) / 2;
        value = v < 1 ? 1u : (unsigned)v;
    }
    if (floor_apy && (p[0x27] & 15)) {
        unsigned apy = *(u16 *)(p + 10) * 10u / (p[0x27] & 15);
        if (value < apy) value = apy;
    }
    /* Callers truncate to AX. Never wrap an expensive player to near zero. */
    if (value > 60000) value = 60000;
    if (!(p[0x24] & 15) && !(p[0x27] & 15)) value = economy_ask(p, value, floor);
    return value;
}

/* DESIGN: the CBA minimum salary for a player's years of service, grown with the season index. */
SECTION(".penalty") static unsigned economy_floor(unsigned pro) {
    return (minimums[minimum(pro, 7)] + minimum(*(u32 *)0xe576b8, 4) * 45 + 3) / 4;
}

SECTION(".contracts") void FAST economy_contract(u8 *p, unsigned low, unsigned high, unsigned floor_apy) {
    unsigned years = minimum(maximum(low, 1), 7);
    if (high >= years) years += n_rand(RNG) % (minimum(high, 7) - years + 1);
    /* b81 revision 10: the CPU's own ranges (renewals and extensions 2-6 at 0x322ECE, fills 2-4 / 5-6 at 0x322D98) take
     * the real length of his age and price (the draw above still runs: the RNG stream is unchanged); the user's screens
     * (1-4, 1-5) and MyCareer (1-1) keep theirs. */
    if (low >= 2 && high > low) years = economy_years(p);
    if (PROVE_IT_FREE_AGENT(p)) years = 1;   /* b778 fa2: a prove-it deal */
    unsigned salary = economy_value(p, floor_apy, 0, 1, years);
    unsigned value = (salary * years + 9) / 10;
    *(u16 *)(p + 10) = (u16)minimum(value, 65535);
    p[0x24] = (p[0x24] & 0xf0) | years;
    p[0x27] = (p[0x27] & 0xf0) | years;
    p[0x26] = 2; /* balanced, no fabricated signing bonus */
}

/* The native pick argument is a zero-based ordinal. The retail draft has
 * 224 regular picks; compensatory choices are outside this model.
 * The source table stores fitted four-year schedules at observed knots.
 */
SECTION(".rookie") void FAST economy_rookie(u8 *p, unsigned ordinal, unsigned randomize) {
    (void)randomize;
    unsigned pick = minimum(ordinal + 1, 224), i = 0;
    const struct rookie_row *table = (const struct rookie_row *)ROOKIE_TABLE_VA;
    while (i + 1 < ROOKIE_COUNT && table[i + 1].pick <= pick) ++i;
    unsigned value = table[i].value;
    if (i + 1 < ROOKIE_COUNT) {
        unsigned span = table[i + 1].pick - table[i].pick;
        int delta = (int)table[i + 1].value - value;
        value += delta * (int)(pick - table[i].pick) / (int)span;
    }
    /* DESIGN: the fitted 2026 rookie pool grows with the modeled cap. */
    float grown = value * (*(u32 *)0xe3c278 / 75300.0f);
    *(u16 *)(p + 10) = (u16)(grown > 65535.0f ? 65535 : (unsigned)(grown + 0.5f));
    p[0x24] = (p[0x24] & 0xf0) | 4;
    p[0x27] = (p[0x27] & 0xf0) | 4;
    p[0x26] = table[i].curve;
}

SECTION(".picks") unsigned STD economy_pick(const u16 *p) {
    unsigned round = *p & 63, slot = (*p >> 6) & 63;
    if (!round || round > 7 || slot > 31) return 0;
    unsigned stage = *(u32 *)0xe576a4;
    if (stage >= 7 || (*p & 0xf000)) slot = 15;
    unsigned index = (round - 1) * 32 + slot, value = 3000;
    if (index) {
        value = 2649;
        for (unsigned i = 1; i < index; ++i) value -= pick_deltas[i - 1];
    }
    value *= 2;
    if (*p & 0xf000) value = value * 3 / 4;
    return value;
}

/* DESIGN: retain the save's 16-bit dead-money ledger. Saturation is a blocked
 * cap, never wraparound that grants spending room. The accessor handles it.
 */
SECTION(".penalty") void FAST economy_penalty(u8 *team, u8 *player, unsigned year) {
    if (year > 6 || !((unsigned (FAST *)(u8 *))0x13ec30)(team)) return;
    unsigned amount = ((unsigned (FAST *)(u8 *))0x13ed00)(player);
    u16 *slot = (u16 *)(team + 0x19c + year * 2);
    *slot = (u16)minimum((unsigned)*slot + amount, 65535);
}

SECTION(".cap") int FAST economy_cap(u8 *team, unsigned with_penalty, unsigned year) {
    if (year > 6) return 0;
    unsigned used = 0;
    if (with_penalty && ((unsigned (FAST *)(u8 *))0x13ec30)(team))
        used = *(u16 *)(team + 0x19c + year * 2);
    unsigned cap = *(u32 *)0xe3c278;
    if (used == 65535 || used >= cap) return 0;
    cap -= used;
    while (year--) cap = (unsigned)(cap * *(float *)0x4fe7a0);
    return (int)cap;
}

/* DESIGN: one shared display boundary. Accounting stays in game $1000.
 * PROVED OFFLINE: every immediate call to the retail currency formatter is
 * enumerated by money_probe.py; native screen callbacks are exercised there.
 */
SECTION(".money") u16 *FAST economy_money(int game_thousands, u16 *out) {
    u16 *start = out;
    if (game_thousands < -536870911) game_thousands = -536870911;
    if (game_thousands > 536870911) game_thousands = 536870911;
    if (game_thousands < 0) { *out++ = '-'; game_thousands = -game_thousands; }
    unsigned real = (unsigned)game_thousands * 4, values[2];
    const u16 *format = (const u16 *)0xea2858;
    values[0] = real;
    if (real >= 1000) {
        values[0] = real / 1000; values[1] = real % 1000 / 10;
        format = (const u16 *)0xea2840;
    }
    ((void (FAST *)(u16 *, const u16 *, unsigned *))0x4a400)(out, format, values);
    return start;
}

/* DESIGN: the retail CPU fill loop uses an unlimited budget and can add
 * several players after its single roster check. Check each transaction.
 * Ten game thousands cover the generated contract's upward rounding.
 */
SECTION(".roster_d") unsigned FAST economy_fill_room(u8 *team, unsigned budget) {
    if (team[0x11c] >= 54) return 0;
    ((void (FAST *)(u8 *))0xc3f00)(team);
    int room = economy_cap(team, 1, 0) - *(u32 *)(team + 0x124) - 10;
    return room > 0 ? minimum(budget, (unsigned)room) : 0;
}

/* b780 hunt1 (revision 6): the gate's room rule refuses a club of 54 or more (written when the trim held every camp at
 * 54). With the native camp limit (revision 5) camps hold up to 65 from the draft to the season gate, so a club that
 * lost its only kicker or punter in the offseason (an expiring contract, a retirement) could not sign one again before
 * the gate's cut to 53, which cannot make one (v0.9 RC, seed 2602: Kansas City's kicker left in free agency and the club
 * opened year 4 with none). A K or P signing (the native signing's second argument is 1 or 2) now skips that count test
 * below the native 65 and keeps the cap-room rule: economy_fill_room + 9 is its body after the 9-byte count test
 * (cmp byte [ecx+0x11C], 53; ja), with ECX and EDX as the body expects them. The fills only ask for a K or P where the
 * club has none (the native minimum and wanted depth are 1). Every other signing keeps the gate as it was. */
SECTION(".fill_gate") __attribute__((naked)) void economy_fill_gate(void) {
    __asm__("mov 4(%esp), %ecx\nmov 12(%esp), %edx\nmov 8(%esp), %eax\ndec %eax\ncmp $1, %eax\nja 4f\n"
            "cmpb $64, 0x11c(%ecx)\nja 4f\ncall economy_fill_room+9\njmp 5f\n4: call economy_fill_room\n"
            "5: test %eax, %eax\njz 1f\n"
            "mov %eax, 12(%esp)\nsub $0x114, %esp\njmp 0x322bb6\n"
            "1: xor %eax, %eax\nret $16\n");
}

/* DESIGN: a timed CPU offer already passed native player consent. Check
 * its actual first-year charge and overwrite the previous deal's curve
 * and bonus before the untouched native commit writes its term and value.
 */
SECTION(".offer_room") unsigned FAST economy_offer_room(u8 *offer) {
    u8 *team = *(u8 **)(offer + 4), *p = *(u8 **)offer;
    unsigned years = offer[10], bonus = offer[8], kind = offer[11] >> 5;
    if (!years || years > 7 || bonus > 7 || team[0x11c] >= 54) return 0;
    unsigned value = *(u16 *)(offer + 12);
    unsigned charge = ((unsigned (FAST *)(unsigned, unsigned, unsigned, unsigned, unsigned))0xe6040)
                      (value, kind, bonus, 0, years);
    charge += ((unsigned (FAST *)(unsigned, unsigned, unsigned))0xe6020)(value, bonus, years);
    ((void (FAST *)(u8 *))0xc3f00)(team);
    if ((int)(*(u32 *)(team + 0x124) + charge) > economy_cap(team, 1, 0) - economy_reserve(team)) return 0;   /* b81 r10 */
    p[0x26] = kind | bonus << 4;
    return 1;
}

/* b779 vs1: the transaction list's "Signed ... (n/$...)" formats n from the live player
 * record +0x27. A signing that is later released has +0x27 cleared by 0x2BD900, so its old
 * transaction line reads "0 years". Use the live term while the player is under contract and
 * the term the transaction log recorded (packed >> 5 & 0xffff) once it was cleared. Caller
 * 0x369133 has ESI = log entry, ECX = player; the formatter's years slot is 0x10(%esp)
 * before the call, 0x14(%esp) inside this stub. */
SECTION(".txn_years") __attribute__((naked)) void economy_txn_years(void) {
    __asm__("movzbl 0x27(%ecx), %edx\nandl $15, %edx\njnz 1f\nmovl (%esi), %edx\nshrl $5, %edx\n"
            "1: movl %edx, 0x14(%esp)\nret\n");
}

/* b780 econ3 (revision 7, Q33): the gate asks economy_offer_both (roster_o): no bid from a computer club already at its
 * modern maximum at the player's position, then the room test as before. Same size, so no symbol moves. */
SECTION(".offer_gate") __attribute__((naked)) void economy_offer_gate(void) {
    __asm__("mov %edi, %ecx\ncall economy_offer_both\ntest %eax, %eax\n"
            "jz 0x323cbd\nmov 0xb72918, %ecx\njmp 0x323bb9\n");
}

/* DESIGN: automatic CPU renewals also bypass offer acceptance. Quote the
 * balanced generated deal against room excluding this player's old deal.
 * Restore the old record and payroll before deciding; rejection is read-only.
 */
SECTION(".roster_d") unsigned FAST economy_renew_room(u8 *p, u8 *team) {
    u8 remaining = p[0x24];
    p[0x24] &= 0xf0;
    ((void (FAST *)(u8 *))0xc3f00)(team);
    int room = economy_cap(team, 1, 0) - *(u32 *)(team + 0x124);
    p[0x24] = remaining;
    ((void (FAST *)(u8 *))0xc3f00)(team);
    if ((*(u16 *)(p + 0x28) >> 10) & 7) room -= economy_reserve(team);   /* b81 r10: a depth-chart starter may use it */
    return room >= (int)economy_value(p, !!(remaining & 15), 0, 1, 0) + 10;
}

SECTION(".roster_e") __attribute__((naked)) void economy_renew_gate(void) {
    __asm__("mov %esi, %ecx\nmov %edi, %edx\ncall economy_renew_room\n"
            "test %eax, %eax\njz 1f\npush %ebx\nmov 0x24(%esi), %ebx\n"
            "and $15, %bl\njmp 0x322eb7\n1: ret\n");
}

/* ---------------------------------------------------------------------------
 * b778 fa2 (revision 3): restructures, the 50-player floor, minimum-salary
 * depth and one-year prove-it deals. Noah 10/22: "allow contract restructures
 * ... hold teams to a minimum of 50 players ... lower level players usually
 * accept a veteran minimum ... take the best deal on the table after a week or
 * two of no one signing them ... a one-year deal".
 * Code space: the retail weekly CPU signing pass 0x323870 (rebuilt below) and
 * four unreferenced retail library functions (sha256-pinned windows; zero
 * byte-granular references to any address inside them anywhere in the image).
 * ------------------------------------------------------------------------- */

/* PROVED OFFLINE: one season's cap charge is the curve's base (0xE6040) plus the
 * prorated bonus (0xE6020), as the payroll routine 0xC3F00 adds them. */
SECTION(".roster_e") static unsigned charge(unsigned value, unsigned kind, unsigned bonus, unsigned index, unsigned len) {
    return n_base(value, kind, bonus, index, len) + n_prorated(value, bonus, len);
}

/* DESIGN: an NFL restructure converts this season's base salary into a signing
 * bonus prorated over the years left. The native contract stores one total, a
 * curve and a prorated bonus share, so the faithful equivalent re-papers the
 * money still owed (unchanged in total) over the years left as the back-loaded
 * curve 6 with a 20% prorated bonus: this season's charge falls, later seasons
 * rise, and a later release leaves the bonus as dead money. Returns the room it
 * makes this season. A second restructure in the same season gains nothing. */
SECTION(".roster_b") int FAST economy_restructure(u8 *p, unsigned apply) {
    unsigned left = p[0x24] & 15, len = p[0x27] & 15, value = *(u16 *)(p + 10);
    unsigned kind = p[0x26] & 15, bonus = p[0x26] >> 4, owed = 0;
    /* b81 r10: 3+ years left, and never a deal already restructured (curve 6, bonus 2): the money owed moves once */
    if (left < 3 || left > len || kind > 7 || bonus > 9 || p[0x26] == (6 | 2 << 4)) return 0;
    /* Never a contract the retail veteran cut calls overpaid (base > 2.1 x market value). */
    if (n_salary(p) * 10 > economy_value(p, 0, 0, 1, left) * 21) return 0;
    for (unsigned i = len - left; i < len; ++i) owed += charge(value, kind, bonus, i, len);
    owed = minimum(owed / 10, 65535);
    int saving = (int)charge(value, kind, bonus, len - left, len) - (int)charge(owed, 6, 2, 0, left);
    if (apply) {
        *(u16 *)(p + 10) = (u16)owed;
        p[0x26] = 6 | 2 << 4;
        p[0x27] = (p[0x27] & 0xf0) | left;
    }
    return saving;
}

/* Restructure the contract that makes the most room (b81 revision 10: moved to window .r10_rbest, where a club holding
 * three restructured deals restructures no more). */
unsigned economy_restructure_best(u8 *team);

unsigned FAST economy_camp_limit(void);   /* b780 b4-economy (D10): defined at the end of roster_m */
void FAST economy_cover(u8 *team, void *menu);   /* b780 hunt1: defined after roster_h's rodata (naked, fastcall ECX/EDX) */

/* DESIGN: replace the native CPU cap-cut routine with a bounded reconciliation
 * that also runs after the rollover returns IR players. Keep the native 54
 * player/cap gate intact; release through the real transaction and FA paths.
 * Preserve two QBs and at least one player in every other occupied position.
 * b778 fa2: a CPU club (a user club only with the native "CPU manages" flag)
 * restructures before any release. At or below the 50-player floor only a
 * player paid at least twice the minimum is released, so the release pays for
 * the minimum signing that refills the slot (the old floor was 42 players).
 * `force` releases one such player even under the cap (a club short of the
 * floor with no room left for minimum salaries). */
SECTION(".fill_room") static void trim(u8 *team, unsigned force) {
    for (unsigned attempt = 0; attempt < 80; ++attempt, force = 0) {
        n_recount(team);
        unsigned count = team[0x11c], least = economy_floor(0);
        int room = ROOM(team);
        if (count <= economy_camp_limit() && room >= 0 && !force) return;
        if (room < 0 && CPU(team) && economy_restructure_best(team)) continue;
        u8 *best = 0;
        float score = 2.0f;
        for (unsigned i = 0; i < count; ++i) {
            u8 *p = ((u8 **)team)[i];
            unsigned pos = p[0x35], same = 0;
            for (unsigned j = 0; j < count; ++j) same += ((u8 **)team)[j][0x35] == pos;
            if (same <= (pos == 0 ? 2u : 1u)) continue;
            unsigned salary = (p[0x24] & 15) ? n_salary(p) : 0;
            if ((room < 0 && !salary) || (count <= FLOOR_PLAYERS && salary < 2 * least)) continue;
            float rating = n_rating(p, 0);
            if (rating < score) { score = rating; best = p; }
        }
        if (!best) return;
        economy_penalty(team, best, 0);
        economy_release(team, best);
    }
}

SECTION(".reconcile") void FAST economy_reconcile(u8 *team) {
    trim(team, 0);
}

/* DESIGN: the retail weekly CPU fill (0x323870), rebuilt as one helper: every
 * position below the native minimum (or wanted depth) gets a 0x322BB0 signing
 * with chance `chance`. With `floor` set it fills a club to FLOOR_PLAYERS with
 * lower-level depth instead: the budget is twice the rookie minimum, doubling only
 * when nobody at the position is that cheap (to four times it until free agency
 * closes), so the best cheap player at a needed position signs at about the minimum. */
SECTION(".roster_a") static void fill(u8 *team, void *menu, float chance, unsigned want, unsigned floor) {
    int need[17];
    economy_need(need, team, want);   /* b780 econ3 (revision 7): the native need with the modern depth cells */
    for (unsigned pos = 0; pos < 17; ++pos)
        while (need[pos] < 0) {
            ++need[pos];
            int budget = n_human(team) ? ROOM(team) : economy_fill_budget(team);   /* b81 r10: the reserve */
            if (!floor) {
                if (n_frand(RNG) < chance) n_cpu_sign(team, pos, budget, menu);
                continue;
            }
            /* Lower-level players first, the cheapest tier first: twice the rookie minimum,
             * then four times it (about $3.7M real), within the room. Before free agency
             * (stages 1 and 2) the market above that is left to free agency and the clubs'
             * own offers; from the end of free agency on the tiers keep doubling to the room. */
            if (team[0x11c] >= FLOOR_PLAYERS) return;
            int room = ROOM(team) - 10;
            unsigned least = economy_floor(0);
            int top = *(u32 *)0xe576a4 >= 3 ? room : (int)(4 * least);
            for (budget = 2 * least; !n_cpu_sign(team, pos, minimum(budget, room), menu) && budget < room && budget < top; budget *= 2) {}
        }
}

/* Cap compliance (restructures before releases), then the 50-player floor; a
 * club still short without room for a minimum salary restructures, else releases
 * one well-paid player, then refills with minimum salaries. */
SECTION(".roster_a") static void upkeep(u8 *team, void *menu) {
    if (*(u32 *)0xe576a4 >= 8) economy_cover(team, menu);   /* b780 hunt1: in season a hurt K or P is covered */
    economy_clear_cap(team);    /* b81 r10: over the cap, restructure once, then release by value lost */
    economy_camp(team, menu);   /* b81 r10: kickers and punters compete in camp */
    for (unsigned attempt = 0; attempt < 12; ++attempt) {
        trim(team, 0);
        fill(team, menu, 1.0f, 0, 1);
        fill(team, menu, 1.0f, 1, 1);
        if (team[0x11c] >= FLOOR_PLAYERS || ROOM(team) >= (int)(2 * economy_floor(0)) + 10) return;
        if (!economy_restructure_best(team)) trim(team, 1);
    }
}

/* The best offer on the table for a free agent: the most cap room among CPU
 * clubs (less 10, and less a minimum salary for each slot a club still needs to
 * reach the floor), preferring clubs he would start for (fewer players at least
 * as good at his position than the native minimum there), then clubs he would
 * play for (fewer than the wanted depth). A club that already signed a free
 * agent unsigned for two weeks or more since this week's count (his count is
 * still on him until the next weekly pass clears rostered players) makes no
 * other offer that week, so the deals spread across clubs. */
SECTION(".roster_c") unsigned FAST economy_best_room(u8 *p, u8 **club) {
    unsigned pos = p[0x35], least = economy_floor(0), tier = 0;
    float him = n_rating(p, 1);
    int best = 0;
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        /* b780 b4-economy (D10): the club that signs him (club != 0, the prove-it pass) needs an open spot below 53,
         * so nobody is cut to make room (a full club reads busy); the ask (club == 0) still counts every club. Weeks 1-4
         * of a simulated v0.8 season: every CPU club cut a player for one every week. */
        unsigned count = team[0x11c], level;
        if (!CPU(team)) continue;
        /* b780 econ3 (revision 7): the start/play level and the club's busy and full tests (club_level, roster_n). */
        level = club_level(team, pos, him, club && count >= 53);
        int room = economy_usable_room(team);   /* b81 r10: never the club's reserve */
        if (count < FLOOR_PLAYERS) room -= (int)((FLOOR_PLAYERS - 1 - count) * least);
        if (level && room > 0 && (level > tier || (level == tier && room > best))) {
            tier = level; best = room;
            if (club) *club = team;
        }
    }
    return (unsigned)best;
}

/* DESIGN: once per weekly advance (the callers of 0x323870: stages 1, 2, 6-9).
 * 1. The retail weekly CPU fill, unchanged in effect.
 * 2. Every free agent counts the weeks he has gone unsigned (player +0x25 bits
 *    5-7, the retail offer-days field; new offers no longer seed from it).
 * 3. Each CPU club gets cap compliance and the 50-player floor.
 * 4. A free agent above PROVE_IT unsigned for two weeks takes the best offer on
 *    the table (economy_value now asks no more than it): the club with the most
 *    room that would start him signs him through 0x322BB0 to a one-year deal
 *    (economy_contract), one such deal per club a week. In season a full club
 *    first cuts one player (0x2BF9A0). */
SECTION(".week") void FAST economy_week(void *menu, unsigned unused, float low, float want) {
    (void)unused;
    for (unsigned pass = 0; pass < 2; ++pass) {
        float chance = pass ? want : low;
        if (chance > 0.0f)
            for (unsigned t = 0; t < n_teams(); ++t) {
                u8 *team = n_team(t);
                if ((!n_human(team) || *(u32 *)0xe6013c) && team[0x11c] < n_roster_limit())
                    fill(team, menu, chance, pass, 0);
            }
    }
    u32 *list = FA_LIST;
    for (unsigned i = 0; i < list[0]; ++i)
        if (((u8 **)list[1])[i][0x25] < 0xe0) ((u8 **)list[1])[i][0x25] += 0x20;
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        for (unsigned i = 0; i < team[0x11c]; ++i) ((u8 **)team)[i][0x25] &= 31;
        if (CPU(team)) upkeep(team, menu);
    }
    unsigned limit = *(u32 *)0xe576a4 >= 8 ? 53 : 64;
    for (unsigned i = list[0]; i-- > 0;) {
        u8 *p = ((u8 **)list[1])[i], *club = 0;
        if (!PROVE_IT_FREE_AGENT(p) || p[0x35] >= 17 || !(n_rating(p, 1) > PROVE_IT)) continue;
        unsigned ask = economy_value(p, 0, 0, 1, 1);
        if (!(club = economy_prove_club(p, ask))) continue;   /* b81 r10: best room, then a hole club first */
        /* b780 b4-economy (D10): economy_best_room no longer offers a full club, so this cut never runs now. */
        if (club[0x11c] >= limit) n_cut_to(club, limit - 1);
        n_cpu_sign(club, p[0x35], ask + 1, menu);
    }
}

/* DESIGN: after every stage action (the common tail at 0x248628 of 0x2480B0,
 * whose EBX is the menu) each CPU club gets the same upkeep, so expiring
 * contracts, free agency and the draft never leave a club short or over the
 * cap. Before the stage-6 veteran cut (jump-table entry 0x24809C), contracts are
 * restructured while the retail cut's own gate (payroll + 6000 >= cap) holds,
 * so room comes from restructures first. */
SECTION(".roster_d") void FAST economy_clubs(void *menu, unsigned vetcut) {
    /* After the regular season and the playoffs the stage action leaves injured
     * reserve with lapsed contracts until the rollover returns them (whose own
     * reconcile follows); the weekly passes cover those stages. */
    if (!vetcut && *(u32 *)0xe576a4 >= 8) return;
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        if (!CPU(team)) continue;
        if (!vetcut) { upkeep(team, menu); continue; }
        /* b780 econ3 (revision 7, Q45): restructure only while the club is short of the veteran cut's line (room for
         * two league-minimum signings; economy_vet_short), not within the retail gate's 6000 ($24M). */
        do n_recount(team);
        while (economy_vet_short(team) > 0 && economy_restructure_best(team));
    }
}

/* DESIGN: the re-signing stage (0x323720) releases every expiring contract the
 * club does not renew (0x322B60 at 0x3237AC). A CPU club already at or below the
 * floor re-signs the expiring player instead, through the economy's renewal gate
 * (0x322EB0, which refuses what the club cannot afford), so free agency does not
 * open with clubs below 50: the league's free-agent pool alone cannot refill them
 * before the draft. */
SECTION(".roster_e") void FAST economy_expire(u8 *team, u8 *p, void *menu) {
    if (CPU(team) && team[0x11c] <= FLOOR_PLAYERS) {
        __asm__ volatile("call 0x322eb0" : : "S"(p), "D"(team) : "eax", "ecx", "edx", "cc", "memory");
        if (p[0x24] & 15) return;
    }
    ((void (FAST *)(u8 *, u8 *, void *))0x322b60)(team, p, menu);
}

/* DESIGN: at the end of the playoffs the retail retirement pass (0x2BDB00) asks
 * 0x2BCF90 about every free agent, and that decision retires anyone whose contract
 * value is zero at once (0x2BCFAA), which every unsigned free agent is: the pool
 * emptied at each new league year (332 of 332 in a v0.6.1 franchise) and clubs that
 * lost players to retirement had nobody to sign. At the free-agent call (0x2BDB74)
 * a zero value is lent as one unit for the call only, so a free agent retires on
 * the same age and rating rule as a rostered player (32 of those 332 did). */
SECTION(".roster_e") __attribute__((naked)) void economy_fa_retire(void) {
    __asm__("mov 4(%esp), %eax\npush %esi\nmovzwl 10(%edi), %esi\ntest %esi, %esi\njnz 1f\n"
            "movw $1, 10(%edi)\n1: push %eax\ncall 0x2bcf90\nmov %si, 10(%edi)\npop %esi\nret $4\n");
}

SECTION(".week_tail") __attribute__((naked)) void economy_after(void) {
    __asm__("mov %ebx, %ecx\nxor %edx, %edx\ncall economy_clubs\njmp 0xc4bb0\n");
}

SECTION(".week_tail") __attribute__((naked)) void economy_stage6(void) {
    __asm__("xor %ecx, %ecx\nmov $1, %edx\ncall economy_clubs\njmp 0x247fd7\n");
}

/* ---------------------------------------------------------------------------
 * b779 rc1 (revision 4): the draft class keeps the create vacancies and the
 * first class's position mix. Window "roster_f" is the unreferenced retail
 * library function 0x382200..0x3822BF (tools/franchise_economy/dead_code.py).
 *
 * PROVED OFFLINE (Unicorn, released v0.7 XBE + disc ROST): with revision 3 the
 * league keeps its unsigned free agents, so the retirement pass 0x2BDB00 retires
 * only 236 and tops retirements up until free + retiring >= 380 counting the 144
 * create vacancies (flags & 5 == 1) as free. The class allocator 0x2BD390 then
 * takes the first 380 records with bit 2 clear, vacancies included, and each
 * prospect keeps the reused record's old position: the second class was 144 FB,
 * 4 QB, 0 K, 0 P, and no vacancy was left for Create Player, MyCareer or a
 * moment/historic import.
 * ------------------------------------------------------------------------- */

/* Not available to the class: a used record (bit 2) or a create vacancy (bit 0).
 * Replaces 0x2BD380 (bit 2 only) at the allocator 0x2BD3C0 and at the retirement
 * pass's free count 0x2BDCAE, so the top-up retires enough free agents for a full
 * class without the vacancies. ECX = record; EAX nonzero = skip; EDX preserved. */
SECTION(".roster_f") __attribute__((naked)) void economy_class_free(void) {
    __asm__("movzbl 8(%ecx), %eax\nand $5, %eax\nret\n");
}

/* b779 rc1 (Noah 10/28: "there should always be a ton of rookie prospects. Every draft, every position pool
 * should have undrafted players that nobody wants"): a generated class asks for CLASS_SIZE prospects (the
 * native loop asked for 380; the first class is still the disc's own 380-record window). The mix per 450 is
 * the CPU's average 224-pick draft per position over simulated v0.7 drafts 3-10, plus a target left over, for a
 * 355-player class (what the league frees in a normal year), scaled to 450, then moved toward T, DT and WR after
 * the smart cut-down (CPU clubs now keep their linemen). b779 ag1: with the 4,096-record arena every class is a
 * full 450, so the mix was retuned from the CPU's undrafted leftovers over ten simulated 450-player drafts (sim
 * fastX1: K and P all undrafted at 5, FS, C, G and DE down to 6, DT 22-34 left over), then C and DT up after the
 * second run (fastX4: C and DT once at 5): QB 21, K 9, P 9, WR 37, CB 44, FS 18, SS 14, HB 25, FB 9, TE 25, OLB 18,
 * ILB 18, C 30, G 28, T 44, DT 49, DE 52. Under the
 * one-pool scheme no rostered player carries OLB (10), and the class must conserve that
 * (nfl2k5_position_pools), so an OLB slot becomes LB (11).
 * b81 economy revision 10 (coordinator ruling 6, 11/25): K 9 -> 4 and P 9 -> 4. Every class added 18 specialists nobody
 * drafted while clubs keep one of each, so the free-agent pool grew by about 8 kickers and 8 punters a season (ten-season
 * panel 68001-68004: K 17 -> 72, P 12 -> 60; rated 80+ 1 -> 30 per league). Real: 7.3 kickers and 5.5 punters a season
 * play their first snap, 1.9 and 2.0 are drafted (nflverse 2014-2025, economy/real.txt R6). The ten slots go two each to
 * WR, CB, T, DT and DE (the premium positions): QB 21, K 4, P 4, WR 39, CB 46, FS 18, SS 14, HB 25, FB 9, TE 25, OLB 18,
 * ILB 18, C 30, G 28, T 46, DT 51, DE 54. */
#define CLASS_SIZE 450
SECTION(".roster_f_rodata") static const u8 class_counts[17] = {
    21, 4, 4, 39, 46, 18, 14, 25, 9, 25, 18, 18, 30, 28, 46, 51, 54};

SECTION(".roster_f") __attribute__((noinline)) unsigned league_has_olb(void) {
    u8 *root = *(u8 **)0xB72918;   /* the roster's own 32 club blocks, valid whenever a class is generated */
    for (unsigned t = 0; t < 32; ++t) {
        u8 *team = *(u8 **)(root + 0x1c) + 500 * t;
        for (unsigned i = 0; i < team[0x11c] && i < 65; ++i)
            if (((u8 **)team)[i][0x35] == 10) return 1;
    }
    return 0;
}

/* Prospect k of a class (the generator's countdown [0xE41CDC], CLASS_SIZE..1) takes slot (k - 1) x 151
 * mod 450 of the mix (151 is prime to 450, so a full class visits every slot once and has exactly the counts
 * above; a class cut short, such as the disc's 380-record first class, still samples every group). */
SECTION(".roster_f") unsigned FAST economy_class_position(void) {
    unsigned k = (*(unsigned *)0xE41CDC - 1) * 151 % CLASS_SIZE, pos = 0;
    while (pos < 16 && k >= class_counts[pos]) k -= class_counts[pos++];
    return pos == 10 && !league_has_olb() ? 11 : pos;
}

/* 0x2BE91D in the class loop 0x2BE900: was movzx edx, [eax+0x35]; mov ecx, eax. */
SECTION(".roster_f") __attribute__((naked)) void economy_class_slot(void) {
    __asm__("push %eax\ncall economy_class_position\nmov %eax, %edx\npop %eax\nmov %eax, %ecx\nret\n");
}

/* b779 rc1: the preseason -> regular season gate. The stage-7 advance (0x24821A)
 * asks 0x2BF950 for every user club (payroll <= cap and active players <= the
 * in-season limit, 53 with the practice squad) and, on a refusal, shows "You must
 * be under the salary cap and have a maximum of 53 players to enter the regular
 * season. The %s need attention." and returns; the Season screen's automatic
 * advance (0x2486F0) asks again at once, so the notice never went away (SWeaR
 * 10/27, Titans, Aug 28 2032). Before asking, cut a user club that is over the
 * limit to it with the native cut-down 0x2BF9A0, exactly what retail's Simulate
 * Preseason path (0x2BFD60) does for every user club. The limit is the gate's own
 * immediate (0x2BF978). An over-the-cap club still gets the notice. */
SECTION(".roster_g") __attribute__((naked)) void economy_preseason_gate(void) {
    __asm__("push %ecx\nmovzbl 0x2bf978, %edx\ncmpb %dl, 0x11c(%ecx)\njbe 1f\n"
            "call 0x2bf9a0\n1: pop %ecx\njmp 0x2bf950\n");
}

/* b779 rc1 (Noah 10/28: "I want players to retire at an appropriate age, not just retire because they're an
 * older free agent nobody signed ... guys should always be available"). The retirement pass (0x2BDB00) asks
 * for enough retirements that the next class gets its records (CLASS_SIZE, 0x2BDCC4/0x2BDCCB); the retail
 * top-up 0x2BD0E0 retired the lowest-rated free agents of any age. This top-up (0x2BDCD6) retires only free
 * agents who are past their position's age, oldest first, and then, only if still short, the lowest-rated
 * free agents within two years of it. Never a younger player: a class may come up short instead.
 * The position's age is the installed career length (0xACEDE0: years pro at which the native retirement
 * 0x2BCF90 starts, nfl2k5_progression's NFL career lengths from nflverse draft_picks 1994-2013) + 24, the age
 * at which a typical starter has retired (base + 2 years pro, a rookie being 1 at about 22): QB/K/P 38,
 * HB 30, FB/CB 31, WR/S/LB 32, TE/DT/DE 33, G/T 34, C 35. */
/* Noah 10/28: "some of the guys waiting for a shot might be willing to wait it out a few extra years". Each
 * player gets his own 0-6 extra years (most 0-3), fixed by his record index so it is the same after a reload:
 * 5 in 16 none, 4 one, 3 two, 2 three, 1 four, 1 six (mean 1.4). */
SECTION(".roster_g_rodata") static const u8 hold_years[16] = {0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 6};
SECTION(".roster_g") static int past_age(u8 *p) {
    u8 *root = *(u8 **)0xB72918;
    unsigned season = *(unsigned *)0x247AC7 + *(unsigned *)0xE576B8 + 1;
    unsigned index = ((unsigned)p - *(unsigned *)(root + 4)) / 84;
    int age = (int)((season - ((*(unsigned *)(p + 24) >> 21) & 127)) % 100);
    return age - (int)(*(unsigned *)(0xACEDE0 + 4 * p[0x35]) + 24) - hold_years[(index * 2654435761U) >> 28];
}

SECTION(".roster_g") static int eligible(u8 *p, int over) {
    return !(p[8] & 0x18) && p[0x35] < 17 && past_age(p) >= over;
}

/* A player the class generator made: his first-name pointer is one of the generated-name pool's entries
 * (ROST root +0x50 count, +0x54 entries of {first, last}); real and created players own their name storage. */
SECTION(".roster_j") static int generated(u8 *p) {
    u8 *root = *(u8 **)0xB72918;
    unsigned *entry = *(unsigned **)(root + 0x54), n = *(unsigned *)(root + 0x50);
    for (unsigned i = 0; i < n && i < 2048; ++i)
        if (entry[2 * i] == *(unsigned *)(p + 16)) return 1;
    return 0;
}

/* Protected floor candidates: a generated player with no career history (+0x2C); mode 1 also needs him to be at
 * least 27 and rated no higher than 0.60 (60 OVR); mode 2 (variant B) takes any age and rating. */
extern const unsigned char economy_floor_protected;
SECTION(".roster_j") static int protectable(u8 *p, float r) {
    unsigned mode = *(volatile const unsigned char *)&economy_floor_protected;
    unsigned season = *(unsigned *)0x247AC7 + *(unsigned *)0xE576B8 + 1;
    unsigned age = (season - ((*(unsigned *)(p + 24) >> 21) & 127)) % 100;
    union { float f; unsigned u; } v = { r };   /* r >= 0: compare the bits; 0x3F19999A = 0.60f, no float literal */
    return (mode == 2 || (age >= 27 && v.u <= 0x3F19999AU)) && !*(unsigned *)(p + 0x2C) && generated(p);
}

/* The lowest-rated candidate one at a time while more than `keep` are needed: mode 0 = within two years of his
 * position's age, mode 1 or 2 = a protected floor candidate of that kind. */
SECTION(".roster_i") __attribute__((noinline)) static int lowest(u8 **list, unsigned n, int need, int keep, int mode) {
    u8 *best;
    float low, r;
    while (need > keep) {
        best = 0; low = 0;
        for (unsigned i = 0; i < n; ++i)   /* no float literal: compiler constants land in the "value" window */
            if (eligible(list[i], mode ? -40 : -2) && ((r = n_rating(list[i], 1)) < low || !best) &&
                    (!mode || protectable(list[i], r))) { low = r; best = list[i]; }
        if (!best) break;
        best[8] |= 8; --need;
    }
    return need;
}

/* Oldest first: every free agent at least `lo` years past his position's age, while more than `keep` are needed. */
SECTION(".roster_m") __attribute__((noinline)) static int oldest(u8 **list, unsigned n, int need, int lo, int keep) {
    for (int over = 12; over >= lo && need > keep; --over)
        for (unsigned i = 0; i < n && need > keep; ++i)
            if (eligible(list[i], over)) { list[i][8] |= 8; --need; }
    return need;
}

/* b780 b4-economy (row D10; v0.8 known issue "CPU clubs still sign and cut fringe players in camp"): trim() held every
 * CPU club at 54 after every stage action all year, so right after the draft each club released about six players,
 * a third of them that day's picks (one simulated v0.8 offseason: 151 releases at the draft, 52 of them rookies).
 * Retail lets a club carry 65 until the regular season (0x247AF0) and cuts it once at the season gate (0x2BFAA0,
 * now the smart cut-down), so the camp limit is the native one before the season and 54 from the season on. */
SECTION(".roster_m") __attribute__((noinline)) unsigned FAST economy_camp_limit(void) {
    return maximum(n_roster_limit(), 54);
}

/* b780 hunt1 (revision 6): the retail stage-6 veteran cap cut (0x2BFAF0, run for every club at 0x247FF5) releases an
 * overpaid veteran whatever his position. With the native camp limit (revision 5) camp payrolls stay over the cap, so
 * the stage-6 fill that follows could not sign a replacement: a club whose only kicker or punter was that veteran
 * started the season without one (SOFTDRINK 2K28 v0.9 RC, seed 2602: CHI and KC with no K at kickoff while 30 kickers
 * were free agents; v0.8, trimmed to 54, signed one in the same stage). The cut's own release call (0x2BFBBD) comes
 * here: it never releases the club's last healthy K or P (the trim and the smart cut already keep one of every
 * position) and otherwise jumps to the native release with the same registers and arguments, so the release keeps the
 * cut's return address. In roster_m's spare bytes, after its own code: no other symbol moves.
 * b780 econ3 (revision 7, Q45): the stub now asks economy_vet_pick (roster_n) which player to release, if any (the K/P
 * guard moved there): ECX = team, EDX = the cut's candidate, the native release's two stack arguments untouched. */
SECTION(".roster_m") __attribute__((naked)) void economy_vet_release(void) {
    __asm__("push %ecx\ncall economy_vet_pick\npop %ecx\ntest %eax, %eax\njz 1f\nmov %eax, %edx\n"
            "push 8(%esp)\npush 8(%esp)\ncall 0x2bd900\ncall 0x2bb9a0\n1: ret $8\n");
}


/* (a) past the position's age, oldest first; (b) within two years of it, lowest-rated first; (c) only when the
 * class would still have fewer than MIN_CLASS records, the oldest remaining free agents. The roster file has a
 * fixed number of records, so a class can only be as deep as the league frees each year: the sims report how
 * often (b) and (c) fire and the ages (c) reaches. 350 kept every position with undrafted players after the
 * 224-pick draft on the 3,231-record arena (Noah 10/28: "never fewer than about 350"). b779 ag1: on the 4,096-record
 * arena the floor is the full class, so every draft has about 226 undrafted players (Noah 10/28: "a ton of rookie
 * prospects"); the variant-B floor below only retires generated players who never played. */
#define MIN_CLASS 450
#define DRAFT_FLOOR 256   /* 224 picks + 32: below this even the protected floor takes the oldest free agents */
/* Pass (c), the class floor. 0: the oldest remaining free agents. 1: only generated players with no career
 * history, 27 or older and rated 60 or less, lowest-rated first. 2 (variant B): only generated players with no
 * career history, any age and rating, lowest-rated first; real and created identities and anyone with history
 * are never taken by the floor. With 1 or 2 a class may stay under MIN_CLASS.
 * nfl2k5_franchise_economy.FLOOR_PROTECTED_VA is this byte. */
SECTION(".roster_h_rodata") const unsigned char economy_floor_protected = 2;
SECTION(".roster_h") int STD economy_class_topup(int need, unsigned retiring) {
    u8 *root = *(u8 **)0xB72918, **list = *(u8 ***)(root + 0x3c);
    unsigned n = *(unsigned *)(root + 0x38);
    (void)retiring;
    need = lowest(list, n, oldest(list, n, need, 0, 0), 0, 0);
    if (*(volatile const unsigned char *)&economy_floor_protected)   /* the draft must never run dry: 256 */
        return oldest(list, n, lowest(list, n, need, CLASS_SIZE - MIN_CLASS, 1), -40, CLASS_SIZE - DRAFT_FLOOR);
    return oldest(list, n, need, -40, CLASS_SIZE - MIN_CLASS);
}

/* b780 hunt1 (coordinator, 11/03: "if a K or P can get hurt in a played or simulated game, a 53-man club then has no
 * way to replace him in season. Make that signing work, for example by releasing the lowest-value player the way a
 * real club would"). A played game can hurt a kicker or a punter: the collision injury chain (0x137520 and 0x137680
 * -> 0x1373C0, the harder-hit of the two players -> 0x136B10) tests no position. The CPU fill never asked for a
 * replacement, because the native need (0x2BD880 over 0xC3CB0) counts injured players too, so the kick went to the
 * depth chart's next player. Each in-season weekly pass a CPU club with no healthy K (or P) now signs one; a club
 * at 53 first makes room with the smart cut (0x2BF9A0: the lowest-rated player at a position above its minimum; K
 * and P stay at their minimum of 1, so the hurt kicker stays). The signing goes through 0x322BB0 and the gate (cap
 * room) like every CPU fill. */
/* ECX = team, EDX = menu (fastcall); K (1), then P (2): no healthy one on the club (the injured bit, +0x23 bit 7, as
 * the trim, the gate and economy_vet_release read it) -> at 53 the smart cut 0x2BF9A0 to 52, then the CPU signing
 * 0x322BB0 (team, pos, 0xFFFF, menu), whose gate keeps the cap-room rule. The free-agent pool always held kickers and
 * punters in the offline seasons (29 to 78); with none the signing fails and the club waits at 52 until one is free. */
SECTION(".roster_h_tail") __attribute__((naked)) void FAST economy_cover(u8 *team __attribute__((unused)),
                                                             void *menu __attribute__((unused))) {
    __asm__("push %ebx\npush %esi\npush %ebp\nmov %ecx, %esi\nmov %edx, %ebp\nxor %ebx, %ebx\ninc %ebx\n"
            "1: movzbl 0x11c(%esi), %ecx\n"
            "2: dec %ecx\njs 3f\nmov (%esi,%ecx,4), %eax\ncmpb %bl, 0x35(%eax)\njne 2b\ntestb $0x80, 0x23(%eax)\njnz 2b\njmp 5f\n"
            "3: cmpb $53, 0x11c(%esi)\njb 4f\npush $52\npop %edx\nmov %esi, %ecx\ncall 0x2bf9a0\n"
            "4: push %ebp\npush $0xffff\npush %ebx\npush %esi\ncall 0x322bb0\n"
            "5: inc %ebx\ncmp $3, %ebx\njb 1b\npop %ebp\npop %esi\npop %ebx\nret\n");
}

/* b779 rc1 (Noah 10/28: "make it smart, so teams aren't cutting guys that they need at certain positions. They'll
 * prioritize the lowest overall at a position where they have more than they need, according to modern NFL
 * position keeping"). Replaces the native cut-down 0x2BF9A0 (fastcall team, target; every caller: the preseason
 * gate, retail's Simulate Preseason, the economy's trims, MyCareer's signing room). While the club has more than
 * `target` active players it releases (native 0x2BD900, as the native cut does) the lowest-rated player at a
 * position still above its minimum; only when no position is above its minimum, the lowest-rated player at a
 * position with two or more. Minimums: 2024 53-man rosters (atlantafalcons.com, 2024-08-28, all 32 teams:
 * QB 2.4, RB 3.6, WR 5.9, TE 3.3, OL 9.4, DL 7.9, LB 7.3, DB 10.3, K 1, P 1 on average), at or below the league
 * average: QB 2, K 1, P 1, WR 5, CB 5, FS 2, SS 2, HB 3, FB 0, TE 3, LB 5 (OLB 3 + ILB 2 when the league has
 * OLBs, else ILB 5 under the one-pool scheme), C 2, G 3, T 3 (OL 8), DT 3, DE 4 (DL 7). 44 in all.
 *
 * b780 econ3 (revision 7, Q33; HUNT6/HUNT1: QBs 2.7 to 3.7 a club over four offseasons, DT 5.25 to 3.44, TE 3.56 to
 * 3.00, 30 to 57 DTs released at each season gate). Raw overalls are not comparable across positions, so "the
 * lowest-rated player above his minimum" took the low-overall depth positions (DT, TE) down to their minimums every
 * year while a fourth or fifth QB stayed. The cut now works in tiers (roster_n's tables): first a position above its
 * modern maximum (QB 3, FB 2) loses its lowest-rated player; then a position above the keep target from the same
 * 2024 averages (QB 2, WR 6, CB 6, FS 2, SS 2, HB 3, FB 1, TE 3, LB 5, C 2, G 3, T 4, DT 4, DE 4: 49 with K and P);
 * then a position above its minimum (as before); then any position with two or more. K and P keep the old rule
 * (above their minimum of 1 only), so a club that covered a hurt kicker never loses the healthy one to a maximum. */

/* The lowest-rated active player at a position with more than mins[position] (floor 0), or more than one
 * (floor 1). */
SECTION(".roster_k") __attribute__((noinline)) static u8 *cut_pick(u8 *team, const u8 *mins, unsigned floor) {
    unsigned n = team[0x11c], i, pos;
    u8 *best = 0, *p;
    float low = 0, r;
    for (i = 0; i < n; ++i) {
        p = ((u8 **)team)[i]; pos = p[0x35];
        if (pos >= 17 || n_at_position(team, pos) <= (floor ? 1 : mins[pos])) continue;   /* native 0xC3CB0 */
        if ((r = n_rating(p, 1)) < low || !best) { low = r; best = p; }
    }
    return best;
}

SECTION(".roster_l") void FAST economy_smart_cut(u8 *team, unsigned target) {
    u8 rows[3][17], *best;
    unsigned k;
    for (k = 0; k < 51; ++k) (&rows[0][0])[k] = (&cut_rows[0][0])[k];
    if (!league_has_olb())          /* the one-pool scheme: OLB slots count as LB */
        for (k = 0; k < 3; ++k) { rows[k][11] += rows[k][10]; rows[k][10] = 0; }
    while (team[0x11c] > target) {
        for (k = 0; k < 3 && !(best = cut_pick(team, rows[k], 0)); ++k) {}
        if (k == 3 && !(best = cut_pick(team, rows[2], 1))) return;
        economy_release(team, best);
    }
}

/* ---- b780 econ3 (revision 7): two more unreferenced retail library functions (tools/franchise_economy/dead_code.py):
 * window roster_n at 0x3C0920 (537 bytes) and window roster_o at 0x264AC0 (295 bytes). ---- */
/* The smart cut's tiers (above a maximum, above the keep target, above the minimum) and the most a computer club signs or
 * bids for at a position (QB 3, K 1, P 1, FB 2); 30 = no limit. */
SECTION(".roster_n_rodata") __attribute__((aligned(1))) const u8 cut_rows[4][17] = {
    {3, 30, 30, 30, 30, 30, 30, 30, 2, 30, 30, 30, 30, 30, 30, 30, 30},     /* cut_max: above a modern maximum */
    {2, 30, 30, 6, 6, 2, 2, 3, 1, 3, 3, 2, 2, 3, 4, 4, 4},                 /* cut_keep: above the 2024 keep target */
    /* cut_min, as before (nfl2k5_roster_refresh.CUT_MINIMUMS mirrors it for the injured players' rejoin cut): */
    {2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 3, 2, 2, 3, 3, 3, 4},
    {3, 1, 1, 30, 30, 30, 30, 30, 2, 30, 30, 30, 30, 30, 30, 30, 30},     /* sign_max: the most a club signs or bids for */
};
/* The native depth tables (0x521C68 minimum, 0x521C20 wanted) with the modern cells: FS and SS minimum 2 (retail 1),
 * TE minimum 3 (retail 2), QB wanted 3 (retail 4). The tables themselves stay as they are (nfl2k5_position_pools owns
 * them and MyCareer's advisory reads them): the economy adds these steps where it reads them, and at the draft need's
 * minimum call (0x31E02D in 0x31DEA0), whose minimum + round table - count put FS and SS last every round (year 1 of
 * a v0.9 franchise: 3 of the class's 22 safeties drafted, 35 of its 44 tackles). */
SECTION(".roster_n_rodata") __attribute__((aligned(1))) const signed char depth_step[2][17] = {
    {0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0},
    {-1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0},
};

/* The draft need's minimum (0x31E02D: call 0x2BD410, ECX = position; EAX only, as the native table read). */
SECTION(".roster_o") unsigned FAST economy_draft_min(unsigned pos) {
    return n_minimum_at(pos) + depth_step[0][pos];
}

/* b780 econ3 (revision 7, Q45; coordinator 11/03: "Cut only when a club is over the cap, or can't fit two
 * league-minimum signings, so clubs keep room for in-season injury and IR replacements"). How far the club is past
 * that line, in game thousands (> 0: short of room for two minimum signings). The payroll is 0xC3F00's (+0x124), so
 * IR salaries count once modern injured reserve adds them to its result. */
SECTION(".roster_n") int FAST economy_vet_short(u8 *team) {
    n_recount(team);
    return *(int *)(team + 0x124) + (int)(2 * economy_floor(0)) - economy_cap(team, 1, 0);
}

/* The retail veteran cap cut (0x2BFAF0, stage 6, every club, years pro >= 10, 210%) proposed an overpaid veteran while
 * payroll + 6000 >= cap. Release nobody while the club is not short of the line above. Otherwise (coordinator 11/04: "A
 * club $0.52M short shouldn't lose Mark Andrews. Choose from every player above the position minimums, cheapest value
 * loss first, while still clearing the line, with charted starters last") the release comes from the whole club: every
 * player under contract at a position above its smart-cut minimum (cut_rows row 2, OLB slots as LB in the one-pool
 * scheme; never the club's last healthy K or P), valued by the cut's own value call at 0x2BFB67 (which star retention
 * may hook). Of those whose charge clears the shortfall, the least value lost, a depth-chart starter (+0x28 rank 0)
 * only when no backup clears it; when no single release clears it, the least value lost again, backups first (the cut
 * proposes again while the club is short). The proposal itself only says the club has an overpaid veteran. */
SECTION(".roster_n") u8 *FAST economy_vet_pick(u8 *team, u8 *proposed) {
    int over = (u32)proposed < 0x10000u ? (int)(u32)proposed : economy_vet_short(team);   /* b81 r10: trim's overage */
    unsigned (FAST *worth)(u8 *, unsigned, unsigned, unsigned, unsigned) =
        (unsigned (FAST *)(u8 *, unsigned, unsigned, unsigned, unsigned))(0x2BFB6C + *(int *)0x2BFB68);
    unsigned olb = league_has_olb(), least = 0;
    u8 *best = 0;
    if (over <= 0) return 0;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        u8 *q = ((u8 **)team)[i];
        unsigned pos = q[0x35], left = q[0x24] & 15, j, floor;
        if (pos >= 17 || !left) continue;
        floor = cut_rows[2][pos];
        if (!olb && pos - 10u < 2u) floor = pos == 10 ? 0 : cut_rows[2][10] + cut_rows[2][11];
        if (n_at_position(team, pos) <= floor) continue;
        if (pos - 1u < 2u) {                 /* K or P: another healthy one must stay */
            for (j = 0; j < team[0x11c]; ++j) {
                u8 *o = ((u8 **)team)[j];
                if (o != q && o[0x35] == pos && !(o[0x23] & 0x80)) break;
            }
            if (j == team[0x11c]) continue;
        }
        int charge = (int)(n_salary(q) + n_prorated(*(u16 *)(q + 10), q[0x26] >> 4, q[0x27] & 15));
        unsigned key = (worth(q, 0, 0, 1, left) & 0xffff) | !((*(u16 *)(q + 0x28) >> 10) & 7) << 16 | (charge < over) << 17;
        if (!best || key < least) { best = q; least = key; }
    }
    return best;
}

/* fill(): count minus the minimum (want 0) or the wanted depth (want 1), as 0x2BD880 / 0x2BD8C0 count (0xC3CB0, every
 * player at the position), with the modern cells. */
SECTION(".roster_c_tail") void economy_need(int *need, u8 *team, unsigned want) {
    for (unsigned pos = 0; pos < 17; ++pos)
        need[pos] = (int)n_at_position(team, pos) - (int)(want ? n_wanted_at(pos) : n_minimum_at(pos)) - depth_step[want][pos];
}

/* b780 econ3 (revision 7, Q33): a computer club already at its modern maximum at the player's position (QB 3, K 1, P 1,
 * FB 2) makes no bid (the free-agent wishes of nfl2k5_draft_ai signed 4 to 11 QBs each free agency); otherwise the
 * offer's room test (economy_offer_room) as before. */
SECTION(".roster_o") unsigned FAST economy_offer_both(u8 *offer) {
    return !economy_full(*(u8 **)(offer + 4), (*(u8 **)offer)[0x35]) && economy_offer_room(offer);
}

/* A computer-run club (not a human one; best_room's clubs are computer clubs already) at its modern maximum at the
 * position (row 3). */
SECTION(".roster_o") unsigned FAST economy_full(u8 *team, unsigned pos) {
    return pos < 17 && !n_human(team) && n_at_position(team, pos) >= cut_rows[3][pos];
}

/* economy_best_room's level for one club: 2 if he would start (fewer players at least as good as him than the minimum),
 * 1 if he would play (fewer than the wanted depth), 0 when the club is busy (signed a long-unsigned free agent since
 * this week's count, or full for the signing pass) or at its maximum at his position. Before revision 7 a club with
 * three worse QBs read 2 for a 70+ QB, so the prove-it pass gave it a fourth. */
SECTION(".roster_o") unsigned club_level(u8 *team, unsigned pos, float him, unsigned busy) {
    unsigned better = 0;
    for (unsigned j = 0; j < team[0x11c]; ++j) {
        u8 *q = ((u8 **)team)[j];
        busy |= q[0x25] >= 0x40;     /* signed a long-unsigned free agent since this week's count */
        if (q[0x35] == pos && !(n_rating(q, 1) < him)) ++better;
    }
    if (busy || economy_full(team, pos)) return 0;
    return better < n_minimum_at(pos) + depth_step[0][pos] ? 2 : better < n_wanted_at(pos) + depth_step[1][pos] ? 1 : 0;
}

/* ---------------------------------------------------------------------------------------------------------------------
 * b81 practice squads (revision 8, REMAINING R60; Noah 11/20: "this franchise mode's got to be like the most realistic
 * NFL simulator"; real clubs keep a full practice squad every season). In every recorded ten-season franchise no player
 * ever joined a practice squad: beta 76.5 retired the automatic demotion at final cuts and nothing else adds a reserve,
 * so the 128 shipped reserves only retired away (128 in 2026, 9 by 2035). In the stage-7 action, right after the
 * preseason -> regular season gate (0x2485DB: every club the CPU runs cut to the in-season limit, unchanged), its call of
 * the next class (0x2485E0) comes here (economy_squad_gate): every club no person manages tops its squad up to SQUAD
 * from the free-agent list, then the class is made as before. The fill goes in
 * rounds: one signing per club for each slot of a 12-slot position mix (squad_mix; no quarterback, coordinator 11/20:
 * the emergency and backup quarterback signings draw from the free agents), the clubs in an order whose start turns with
 * the slot and the season, so a scarce position runs out on a different club each time; a second round over the mix for
 * clubs still short; a third that also takes a K, P or FB. Each signing takes one healthy free agent at the slot's
 * position with at most two accrued seasons (years pro 3 or less, a rookie being 1), chosen by a hash of his record and
 * the club's record (squad_best), not the best-rated: review 11/20, signing the best-rated in club-index order gave clubs
 * 0-7 squads 8.6 overall better than clubs 24-31, and a hash pick in club-index order still sent clubs 24-31 to the
 * kickers and punters once the young receivers ran out. A club a person manages is never touched, whatever the auto
 * sign and cut setting.
 * The signing is the native one without its random contract and jersey draws: off the free-agent list (0x2425C0), onto
 * the active list (0xC3EE0, the squad's append), then the squad's own demotion ps_demote (its limit, single ownership,
 * record flags), then a one-year minimum deal (no cap charge while on the squad). No game RNG, no transaction row.
 * Without the practice-squad runtime (0xC3EE0 not its append) or with foreign reserve bytes the club is only cut. At the
 * rollover the squad's one-year deals expire (economy_squad_expire): the reserves of a club no person manages go back to the
 * free-agent list, so squads re-form every year from young players and camps keep their full offseason roster.
 * --------------------------------------------------------------------------------------------------------------------- */
#define SQUAD 12
extern unsigned FAST ps_append(u8 *team, u8 *p);                  /* nfl2k5_practice_squad SYMBOLS (bridged by the arena) */
extern unsigned FAST ps_demote(u8 *team, u8 *p);
extern unsigned FAST n_fa_remove(u32 *list, u8 *p);               /* 0x2425C0 */
extern unsigned FAST n_fa_add(u32 *list, u8 *p);                  /* 0x242560 (the squad runtime's ps_fa_add) */
extern unsigned FAST retail_fa_add(u32 *list, u8 *p);             /* 0x2952FC: the retail append, no ownership test */
extern unsigned FAST n_append(u8 *team, u8 *p);                   /* 0xC3EE0 */
extern unsigned FAST n_remove(u8 *team, u8 *p);                   /* 0xC3EB0 */
extern void n_ir_return(void);                                    /* 0x246F90 the rollover's return from injured reserve */
/* WR, CB, T, DE, HB, LB (OLB or ILB), C or G, DT, TE, S (FS or SS), WR, any lineman (C, G or T): position masks by the
 * +0x35 codes; no quarterback (coordinator 11/20). Three rounds written out: the mix, the mix again for clubs still
 * short, and the mix with a K, P or FB (bits 1, 2, 8) for clubs short after two. */
#define SQUAD_MIX 1u << 3, 1u << 4, 1u << 14, 1u << 16, 1u << 7, 3u << 10, 3u << 12, 1u << 15, 1u << 9, 3u << 5, 1u << 3, 7u << 12
#define SQUAD_MIX_KP (1u << 3) | 0x106, (1u << 4) | 0x106, (1u << 14) | 0x106, (1u << 16) | 0x106, (1u << 7) | 0x106, \
    (3u << 10) | 0x106, (3u << 12) | 0x106, (1u << 15) | 0x106, (1u << 9) | 0x106, (3u << 5) | 0x106, (1u << 3) | 0x106, \
    (7u << 12) | 0x106
SECTION(".roster_q_rodata") __attribute__((aligned(4))) const u32 squad_mix[3 * SQUAD] = {SQUAD_MIX, SQUAD_MIX, SQUAD_MIX_KP};

/* The eligible free agent at a position in `mask` with the lowest hash of (his record offset, the club's record offset):
 * a pseudo-random pick fixed by the league state (record offsets, not memory addresses, so a reloaded save picks the
 * same), with no game RNG drawn. Each club ranks the pool in its own order, the same every season, so a club tends to
 * sign back its own squad players who are still free and eligible. */
SECTION(".roster_p") __attribute__((noinline)) static u8 *FAST squad_best(u8 *team, u32 mask) {
    u8 *root = *(u8 **)0xB72918, *p, *best = 0;
    u32 *list = FA_LIST, seed = (u32)team - *(u32 *)(root + 0x1c), low = ~0u, h;
    for (u32 i = 0; i < list[0]; ++i) {
        p = ((u8 **)list[1])[i];
        if (p[0x35] >= 17 || !(mask >> p[0x35] & 1) || (p[0x25] & 31) > 3 || (p[8] & 0x1c) != 4 ||
            p[0x28] == 0xee || (p[0x23] & 0x80)) continue;
        h = (((u32)p - *(u32 *)(root + 4)) ^ seed) * 2654435761u;
        if (h <= low) { low = h; best = p; }
    }
    return best;
}

/* Sign one free agent for one slot to the squad: 1 = go on (signed, or nobody fits), 0 = stop the whole fill (refused).
 * Re-check R1 (11/21): the squad runtime refuses every player while any club's reserve storage is unreadable, and its
 * free-agent append refuses too, so a player taken off the list first ended in no list (446 on the kept image with one
 * damaged club). Now the squad's append is asked first, while he is still on the free-agent list, so that refusal
 * changes nothing; only then is he taken off the list (the retail remove-by-value). If the demotion is refused after it,
 * he goes back through the retail append with no ownership test (0x2952FC) and leaves the active list only once he is
 * back on the free-agent list: if he could not be put back he stays on the club's active list (54 players, which the
 * validator's I1 reports), never in no list. */
SECTION(".roster_r") __attribute__((noinline)) static u32 FAST squad_sign(u8 *team, u32 mask) {
    u32 *list = FA_LIST;
    u8 *p = squad_best(team, mask);
    if (!p) return 1;
    if (!n_append(team, p)) return 0;
    n_fa_remove(list, p);
    if (ps_demote(team, p)) {
        *(u16 *)(p + 10) = (u16)((economy_floor(0) + 9) / 10);    /* one year at the rookie minimum */
        p[0x24] = (p[0x24] & 0xf0) | 1;
        p[0x27] = (p[0x27] & 0xf0) | 1;
        p[0x26] = 2;
        return 1;
    }
    if (retail_fa_add(list, p)) n_remove(team, p);           /* 1 once he is on the list (0 only at 2,500) */
    return 0;
}

/* The squad's storage as the fill and the release may change it: the practice-squad runtime installed (0xC3EE0 is its
 * append), a club no person manages (coordinator 11/20: never a human club, whatever the auto sign and cut setting; the
 * gate's own cut still follows that setting), and its reserve bytes in the squad's own form (none yet, or the A5 marker
 * with at most SQUAD reserves), every reserve a player in the 65 physical slots (a null slot skips the club). */
SECTION(".roster_u") __attribute__((noinline)) static u32 FAST squad_ok(u8 *team) {
    u32 a = team[0x11c], r = team[0x1f2];
    if (n_human(team) || *(u8 *)0xC3EE0 != 0xE9 || *(int *)0xC3EE1 != (int)ps_append - 0xC3EE5 ||
        (team[0x1f3] == 0xa5 ? r > SQUAD || a + r > 65u : (team[0x19b] | r) != 0))
        return 0;
    while (r--) if (!((u8 **)team)[a + r]) return 0;
    return 1;
}

/* 0x247B79 in the rollover 0x247B40, after the retirements and before the injured players return (ECX/EDX unused): was
 * call 0x246F90 (the return from injured reserve). Real squad deals last one season: every club no person manages lets them
 * expire here, every reserve back on the free-agent list with no contract (as the native release leaves a player), so
 * camp has the full offseason roster again and the next gate forms a new squad. At this point a club holds its 53 and at
 * most SQUAD reserves, all in physical slots. Holding 12 reserves through the offseason caps a camp at 53 (65 physical
 * slots): the second ten-season panel then opened 7 seasons with a club that could not sign a kicker or punter in camp. */
SECTION(".roster_s") void FAST economy_squad_expire(void) {
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        if (squad_ok(team))
            while (team[0x1f2]) {
                u8 **slot = (u8 **)team + team[0x11c] + --team[0x1f2], *p = *slot;
                *slot = 0;                                    /* the squad's own form: the slots past the last are null */
                if (!n_fa_add(FA_LIST, p)) { *slot = p; ++team[0x1f2]; break; }
                *(u16 *)(p + 10) = 0;
                p[0x24] &= 0xf0;
                p[0x27] &= 0xf0;
            }
    }
    n_ir_return();
}

/* 0x2485E0 in the stage-7 action, right after the gate's call 0x2485DB (no register arguments): was call 0x2BF8B0, the
 * next draft class (0x2485DB itself lies in nfl2k5_progression's guarded "Preseason calls" span). Round r, slot j: the 32
 * clubs in turn from (7 x season + 11 x (12 r + j)) modulo 32 (the league's 32 clubs, as the gate's own loop); a club
 * full or managed by a person is passed over; a refused signing stops the fill. Then the class. */
extern void n_next_class(void);                                   /* 0x2BF8B0 */
SECTION(".roster_t") void FAST economy_squad_gate(void) {
    u32 turn = *(u32 *)0xE576B8 * 7;
    for (u32 j = 0; j < 3 * SQUAD; ++j, turn += 11)
        for (u32 k = 0; k < 32; ++k) {
            u8 *team = n_team((turn + k) & 31);
            if (team[0x1f2] < SQUAD && squad_ok(team) && !squad_sign(team, squad_mix[j]))
                goto done;                                    /* a refused signing stops the whole fill (re-check R1) */
        }
done:
    n_next_class();
}

/* ---------------------------------------------------------------------------------------------------------------------
 * b81 team building (revision 9; coordinator 11/25: one routine for the CPU free-agent signing's affordability, so the
 * economy lane's revision 10 changes only its body). The cap room a CPU club may spend on a free-agent signing: cap room
 * less 10 ($40,000 real), the margin the prove-it pass already keeps (economy_best_room). Called by the team-building
 * wishes (nfl2k5_team_building, tools/team_building/runtime.c tb_candidate) at this window's first byte (an ENTRY).
 * b81 economy revision 10: the room a club may spend leaves its reserve (economy_usable_room: cap room - 10 - reserve).
 * --------------------------------------------------------------------------------------------------------------------- */
SECTION(".roster_v") int FAST economy_room_for_signing(u8 *team) {
    return economy_usable_room(team);   /* b81 revision 10: and never the club's reserve (economy_reserve) */
}

/* ---------------------------------------------------------------------------------------------------------------------
 * b81 economy revision 10 (economy lane DESIGN.txt; coordinator rulings 2026-11-25). The ten-season panel 68001-68004
 * (8b180ed5): from 2031 every CPU club sat at 96-100% of the cap (real median room 2.9%, 7 of 32 clubs at 7.6%+), up to
 * 17 starter-grade free agents per league were unsigned at week 18, 5-6 year deals were 22% of the active book (real
 * 0.8%) and 30 kickers and punters rated 80+ sat unsigned. Causes (DESIGN.txt 2): the price followed absolute ratings
 * (the CPU rosters at economy_value cost 1.03 of the cap in 2026 and 1.38 in 2033); every signing path spent to the last
 * dollar; restructured deals were restructured again (3.3 -> 9.7 a club); no club ever cut an overpaid veteran to make
 * room; lengths ignored age and price; the in-season prove-it ask counted the room of full clubs no one could sign with.
 * Revision 10:
 * - price: a player's rank at his position group among every rostered man, on the real market curve (OverTheCap, the
 *   k-th best-paid active player's share of the cap) x the price scale (1.0 since the 11/25 retune), the aging rule by age, the minimum. Rating inflation moves
 *   no price (data/nfl2k5_franchise_economy.json revision_10.price);
 * - a free agent's ask falls with the weeks he goes unsigned; the prove-it clamp counts only clubs that could sign him;
 * - lengths: one draw from the real length mix of the player's age band and price tier, used by the CPU's offers, the
 *   player's own wish (0x322690, so the offer and his consent agree), renewals, extensions and fills;
 * - a cap reserve per CPU club drawn from the real in-season room; FA offers, non-starter renewals, native fills above
 *   four minimums and prove-it signings must leave it;
 * - before the re-signing stage a CPU club short of its reserve + 2% of the cap releases up to three overpaid 30+ (or
 *   past their position's decline age) veterans; a deal is restructured once, with 3+ years left, 3 a club at most; an
 *   over-the-cap trim releases by value lost (the veteran cut's own ranking) instead of the lowest-rated man;
 * - kickers and punters compete in camp.
 * A club a person owns is never touched by the new rules (ruling 7), whatever its "CPU manages" setting.
 * ------------------------------------------------------------------------------------------------------------------- */
#define STAGE (*(u32 *)0xE576A4)
#define SEASON (*(u32 *)0xE576B8)
#define CAP (*(u32 *)0xE3C278)
#define ROSTER_ROOT (*(u8 **)0xB72918)
#define TEAM_INDEX(t) ((u32)((t) - *(u8 **)(ROSTER_ROOT + 0x1c)) / 500u)
#define HEALTHY(p) (!((p)[0x23] & 0x80))      /* no injury bit, as the trim, the gate and economy_cover read it */
#define CHARGE(q) (n_salary(q) + n_prorated(*(u16 *)((q) + 10), (q)[0x26] >> 4, (q)[0x27] & 15))
#define CAMP_EDGE 0.01f                         /* one point of 0x246D80 (11/25: four kept turnover at 10%, two at 13-14%) */
/* Code space: economy_value's own 540 bytes (economy_value, price_of, share_e4), the retail routine 0x322690 (the
 * player's years wanted; economy_years) and unreferenced retail functions (assemble.py R10_WINDOWS, one or two routines
 * or tables each). A club a person owns never reaches the new rules (ruling 7: n_human, "CPU manages" or not). */

/* Twice his rank among every rostered man of his position group (club active lists; 0x246D80 unboosted):
 * 2 + 2 x (rated above him) + (level with him). */
SECTION(".r10_rank_club") unsigned rank_club(u8 *team, u8 *p, unsigned g, float him) {
    unsigned n2 = 0;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        u8 *q = ((u8 **)team)[i];
        if (q == p || q[0x35] >= 17 || price_group[q[0x35]] != g) continue;
        float s = n_rating(q, 0);
        n2 += s > him ? 2 : s == him;
    }
    return n2;
}

SECTION(".r10_rank") unsigned rank_twice(u8 *p) {
    unsigned g = price_group[p[0x35]], n2 = 2;
    float him = n_rating(p, 0);
    for (unsigned t = 0; t < n_teams(); ++t) n2 += rank_club(n_team(t), p, g, him);
    return n2;
}

/* b81 #45 (sim speed): economy_rank_any is rank_twice, or the same count on the team-building owner's pace page when
 * that owner has put its free-agency day on the stage action (the day call at 0x24849A reads `call 0x1535010`, the page's
 * day entry; only that owner writes it, after reserving the page). The page counts by rank_club's rule, from a memo of
 * each rating for the day and, inside a club's scoring, from lists of the rosters (tools/team_building/pace.c). */
#define PACE_SITE 0x24849Au
#define PACE_DAY 0x1535010u                    /* the page's day entry (the call's target) */
#define PACE_RANK 0x1535018u                   /* the page's rank entry: unsigned (u8 *p), as rank_twice */
#define PACE_CALL ((u32)(PACE_DAY - PACE_SITE - 5))
SECTION(".r10_rank_any") unsigned economy_rank_any(u8 *p) {
    unsigned (*count)(u8 *) = rank_twice;
    if (*(u32 *)PACE_SITE == (0xE8u | PACE_CALL << 8) && *(u8 *)(PACE_SITE + 4) == (u8)(PACE_CALL >> 24))
        count = (unsigned (*)(u8 *))PACE_RANK;
    return count(p);
}

/* Age in the season being played, as past_age reads it. */
SECTION(".r10_age") int age_of(u8 *p) {
    unsigned season = *(unsigned *)0x247AC7 + SEASON + 1;
    return (int)((season - ((*(unsigned *)(p + 24) >> 21) & 127)) % 100);
}

/* The CBA minimum for his years of service (economy_floor is static to its window). */
SECTION(".r10_age") unsigned floor_of(unsigned pro) {
    return (minimums[minimum(pro, 7)] + minimum(SEASON, 4) * 45 + 3) / 4;
}

/* The market curve at twice-rank `rank2`, in 1/10000 of the cap (knots in 0.1% units, linear between them). */
SECTION(".r10_value") unsigned share_e4(unsigned g, unsigned rank2) {
    const u8 *v = g < 5 ? price_curve_a + g * PRICE_KNOTS : g < 10 ? price_curve_b + (g - 5) * PRICE_KNOTS
                                                                  : price_curve_c + (g - 10) * PRICE_KNOTS;
    unsigned i = 0, r0, r1;
    while (i + 2 < PRICE_KNOTS && 2u * price_ranks[i + 1] < rank2) ++i;
    r0 = 2u * price_ranks[i]; r1 = 2u * price_ranks[i + 1];
    if (rank2 <= r0) return v[i] * 10u;
    if (rank2 >= r1) return v[i + 1] * 10u;
    return (v[i] * 10u * (r1 - rank2) + v[i + 1] * 10u * (rank2 - r0)) / (r1 - r0);
}

/* His price in game $1000 before the minimum: the curve x the cap, then 8% a year past his position's decline age
 * (never below a quarter) when `aging`. */
SECTION(".r10_value") unsigned price_of(u8 *p, unsigned aging) {
    unsigned pos = p[0x35], v = share_e4(price_group[pos], economy_rank_any(p)) * (CAP / 100) / 100 * PRICE_SCALE_PCT / 100;
    int over = age_of(p) - decline_age[pos];
    if (aging && over > 0) v = v * (over >= 10 ? 64u : 256u - 20u * (unsigned)over) >> 8;
    return v;
}

/* A free agent's ask before the prove-it clamp: his price falling with the weeks he has gone unsigned (+0x25 bits
 * 5-7), at most half of it from the camp stage on, a quarter of it in season, never below his minimum. */
SECTION(".r10_ask") unsigned ask_of(u8 *p, unsigned value, unsigned floor) {
    unsigned weeks = p[0x25] >> 5, ask = weeks ? value * ask_decay[weeks - 1] >> 8 : value;
    if (STAGE >= 8) ask = value >> 2;
    else if (STAGE >= 6 && ask > value >> 1) ask = value >> 1;
    return ask < floor ? floor : ask;
}

/* After two unsigned weeks a man rated over 70 asks no more than the most room a club that could sign him now has left
 * (the owner 10/22: "take the best deal on the table after a week or two of no one signing them"). economy_best_room with a
 * club pointer: a full club is busy, as in the signing pass itself (the old clamp counted full clubs too, so his ask
 * could exceed every open club's room and he never signed: 10-16 starter-grade men a league by 2033). */
SECTION(".r10_clamp") unsigned economy_ask(u8 *p, unsigned value, unsigned floor) {
    unsigned ask = ask_of(p, value, floor);
    if (PROVE_IT_FREE_AGENT(p) && n_rating(p, 1) > PROVE_IT) {
        u8 *club = 0;
        unsigned best = economy_best_room(p, &club);
        if (ask > best) ask = maximum(best, floor);
    }
    return ask;
}

/* His price tier: under 0.5, 1, 2, 5 or 10% of the cap, or more (0..5). */
SECTION(".r10_tier") unsigned years_tier(u8 *p) {
    unsigned v = price_of(p, 1), cap = CAP;
    return v * 200 < cap ? 0 : v * 100 < cap ? 1 : v * 50 < cap ? 2 : v * 20 < cap ? 3 : v * 10 < cap ? 4 : 5;
}

/* His age band and price tier's cumulative length draw (revision_10.lengths; 1 to 4 years, then 5). */
SECTION(".r10_cell") const u8 *years_cell(u8 *p) {
    int a = age_of(p);
    return years_cum + 4 * (6 * (a <= 25 ? 0 : a <= 29 ? 1 : a <= 32 ? 2 : 3) + years_tier(p));
}

/* Retail 0x322690 (the years a player wants, EDI = player; called by the CPU's offer 0x324180, by his consent 0x3232A0
 * twice and at 0x32368B) now answers here: a draw from the real length mix of his age and price, by a hash of his record
 * and the season (no RNG: his offer and his consent agree, as retail's index draw did). 1 to 5 years. */
SECTION(".years") __attribute__((naked)) void economy_years_entry(void) {
    __asm__("mov %edi, %ecx\njmp economy_years\n");
}

/* His draw, 0..254 (review S2: a cell's 255 is 100 per cent, so 255 must never be drawn): a hash of his record and the
 * season. */
SECTION(".r10_hash") unsigned years_hash(u8 *p) {
    u32 h = ((((u32)p - *(u32 *)(ROSTER_ROOT + 4)) ^ (SEASON * 0x9E3779B9u)) * 2654435761u) >> 24;
    return h - (h == 255);
}

SECTION(".r10_years") unsigned FAST economy_years(u8 *p) {
    if (!p) return (unsigned)-1;
    if (p[0x35] >= 17) return 1;
    const u8 *cum = years_cell(p);
    unsigned h = years_hash(p), years = 1;
    while (years < 5 && h >= cum[years - 1]) ++years;
    if (years == 1 && age_of(p) <= 25) years = 2 + (h & 1);   /* 11/25: a man 25 or under signs for 2-3 years */
    return years;
}

/* The room a CPU club keeps in hand this league year (ruling 4): a share of the cap drawn per club and season from the
 * real in-season room (revision_10.reserve), half of it in season (it is there for in-season signings); 0 for a club a
 * person owns. */
SECTION(".r10_reserve") int FAST economy_reserve(u8 *team) {
    if (n_human(team)) return 0;
    unsigned pm = reserve_pm[(TEAM_INDEX(team) * 0x9E3779B1u ^ SEASON * 0x85EBCA6Bu) >> 29];
    int r = (int)(CAP / 1000 * pm);
    return STAGE >= 8 ? r >> 1 : r;
}

SECTION(".r10_usable") int FAST economy_usable_room(u8 *team) {
    return ROOM(team) - 10 - economy_reserve(team);
}

/* A native fill's budget for a CPU club: its usable room, but always four minimums (a club fills its depth). */
SECTION(".r10_budget") int FAST economy_fill_budget(u8 *team) {
    int room = economy_usable_room(team), least = (int)(4 * floor_of(0));
    if (room > 0xFFFF) room = 0xFFFF;           /* review S1: the native signing compares the low word only */
    return room > least ? room : least;
}

/* Restructure the contract that makes the most room, at least $1M real (moved from roster_b, unchanged: economy_restructure
 * itself now refuses a deal already restructured or with fewer than 3 years left). */
/* The club's restructured deals (curve kind 6, bonus 2: economy_restructure's mark). */
SECTION(".r10_rcount") unsigned economy_restructured(u8 *team) {
    unsigned n = 0;
    for (unsigned i = 0; i < team[0x11c]; ++i) n += ((u8 **)team)[i][0x26] == (6 | 2 << 4);
    return n;
}

/* The contract whose restructure makes the most room, at least $1M real, or 0. */
SECTION(".r10_rscan") u8 *restructure_pick(u8 *team) {
    u8 *best = 0;
    int most = 250;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        int saving = economy_restructure(((u8 **)team)[i], 0);
        if (saving > most) { most = saving; best = ((u8 **)team)[i]; }
    }
    return best;
}

SECTION(".r10_rbest") unsigned economy_restructure_best(u8 *team) {
    u8 *best;
    if (economy_restructured(team) >= 3) return 0;      /* retune 11/25: three restructured deals a club at most */
    if ((best = restructure_pick(team))) economy_restructure(best, 1);
    return best != 0;
}

/* Over the cap, a CPU club restructures (once per deal), then releases by value lost with the veteran cut's own
 * ranking (economy_vet_pick given the overage: the least price lost among men whose charge clears it, depth-chart
 * starters last), not the lowest-rated man the trim would take. Called by upkeep and at the rollover before the trim. */
SECTION(".r10_clear") void FAST economy_clear_cap(u8 *team) {
    if (n_human(team)) return;
    for (unsigned k = 0; k < 8; ++k) {
        n_recount(team);
        int over = -ROOM(team);
        u8 *q;
        if (over <= 0) return;
        if (economy_restructure_best(team)) continue;
        if (!(q = economy_vet_pick(team, (u8 *)(u32)over))) return;
        economy_release(team, q);
    }
}

/* The rollover's reconcile (0x247BC6) comes here: the cap first, then the trim as before. */
SECTION(".r10_rollover") void FAST economy_rollover_reconcile(u8 *team) {
    economy_clear_cap(team);
    economy_reconcile(team);
}

/* Every release the economy makes (the trim, the smart cut, the cap clearing, the cap casualties, camp) goes through
 * here: the native release, then the trade board's own pruner 0x2BB9A0, which cancels (0x2BB660(rec, 0, 1, 1)) any
 * offer naming a man with no contract years -- the man just released. Without it a pending offer kept naming him after
 * another club took him onto its practice squad or IR (panel 74003, 2031: I8 "side B names a player his club does not
 * have" for eleven weeks; the ownership guard refused it each week, the pruner no longer saw zero years). */
SECTION(".r10_release") void FAST economy_release(u8 *team, u8 *p) {
    n_release(team, p, 1, 1);
    n_prune();
}

/* A veteran the club could cut for room (ruling 4): not a QB (the quarterback room's), K or P; under contract; above the
 * smart cut's minimum at his position (cut_rows row 2; LB with the OLB minimum, the product's one-pool scheme); 30 or older, or past
 * his position's decline age. */
SECTION(".r10_cuttable") unsigned cuttable(u8 *team, u8 *q) {
    unsigned pos = q[0x35], floor;
    int a;
    if (pos < 3 || pos >= 17 || !(q[0x24] & 15)) return 0;
    floor = cut_rows[2][pos] + (pos == 11 ? cut_rows[2][10] : 0);   /* the one-pool scheme: LB holds the OLB minimum */
    if (n_at_position(team, pos) <= floor) return 0;
    a = age_of(q);
    return a >= 30 || a > decline_age[pos];
}

/* How far a cuttable veteran is paid above his price, in game $1000: when this season's base salary (0xE6380, as the
 * restructure's and the veteran cut's overpaid tests read it) is at least 1.5 x his price + 0.5% of the cap, the salary
 * less the price; else 0. */
SECTION(".r10_overpay") int overpay(u8 *team, u8 *q) {
    if (!cuttable(team, q)) return 0;
    int salary = (int)n_salary(q), price = (int)economy_value(q, 0, 0, 1, q[0x24] & 15);
    return 2 * salary >= 3 * price + (int)(CAP / 100) ? salary - price : 0;
}

/* The club's most overpaid cuttable veteran, or 0. */
SECTION(".r10_most") u8 *most_overpaid(u8 *team) {
    u8 *best = 0;
    int most = 0;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        int over = overpay(team, ((u8 **)team)[i]);
        if (over > most) { most = over; best = ((u8 **)team)[i]; }
    }
    return best;
}

/* A CPU club short of its reserve + 2% of the cap releases its most overpaid veteran, up to three. */
SECTION(".r10_casualty") void casualties(u8 *team) {
    for (unsigned k = 0; k < 3; ++k) {
        u8 *q;
        n_recount(team);
        if (economy_usable_room(team) + 10 >= (int)(CAP / 50) || !(q = most_overpaid(team))) return;
        economy_release(team, q);
    }
}

/* The re-signing stage (0x248426: call 0x323720, ECX = the menu) comes here first. Ruling 4 (the owner: "clubs that make
 * moves to stay relevant"): real clubs cut before free agency. Then the native re-signing stage. */
SECTION(".r10_resign") void FAST economy_resign_stage(void *menu) {
    for (unsigned t = 0; t < n_teams(); ++t)
        if (!n_human(n_team(t))) casualties(n_team(t));
    ((void (FAST *)(void *))0x323720)(menu);
    n_prune();                                  /* the expiring men it released have no contract years now */
}

/* The best-rated healthy man at `pos` in a list of player pointers (a club's active list or the free-agent list). */
SECTION(".r10_best") u8 *best_at(u8 **list, unsigned n, unsigned pos) {
    u8 *best = 0;
    float top = 0;
    for (unsigned i = 0; i < n; ++i) {
        u8 *q = list[i];
        if (q[0x35] != pos || !HEALTHY(q)) continue;
        float r = n_rating(q, 0);
        if (!best || r > top) { best = q; top = r; }
    }
    return best;
}

/* Camp competition (stage 6, from upkeep): for K, then P, a CPU club whose best healthy one rates CAMP_EDGE (2 points)
 * below the best healthy free agent whose ask fits its fill budget signs (0x322BB0) and keeps the better man: the
 * incumbent goes only when the man signed is healthy and rates the edge above him; otherwise the man signed goes
 * (review M1: the native signing takes the best-rated affordable man at the position, hurt or not, who need not be the
 * one compared). Kickers and punters change clubs; none retires for it (the owner 10/28: no player retires because he
 * is an unsigned free agent). */
/* Healthy and CAMP_EDGE above `mine`. */
SECTION(".r10_camp_ahead") unsigned camp_ahead(u8 *q, u8 *mine) {
    return q && HEALTHY(q) && n_rating(q, 0) >= n_rating(mine, 0) + CAMP_EDGE;
}

/* The club's best healthy man at `pos` when the best healthy free agent there, asking no more than `budget` (the price
 * the native signing compares: 0x2BD440(p, 0; 0, 1, 0), low word), rates the edge above him, else 0. */
/* He asks no more than `budget`. */
SECTION(".r10_camp_fits") unsigned camp_fits(u8 *fa, int budget) {
    return (int)(economy_value(fa, 0, 0, 1, 0) & 0xFFFF) <= budget;
}

/* The best healthy free agent at `pos` asks no more than `budget` and rates the edge above `mine`. */
SECTION(".r10_camp_pick") unsigned camp_pick(u8 *mine, unsigned pos, int budget) {
    u32 *list = FA_LIST;
    u8 *fa = best_at((u8 **)list[1], list[0], pos);
    return fa && camp_fits(fa, budget) && camp_ahead(fa, mine);
}

/* After a signing: the man just appended (0xC3EE0) stays only if he is healthy and the edge above `mine`. */
SECTION(".r10_camp_keep") void FAST camp_keep(u8 *team, u8 *mine) {
    u8 *signed_man = ((u8 **)team)[team[0x11c] - 1];
    economy_release(team, camp_ahead(signed_man, mine) ? mine : signed_man);
}

/* Camp competition for `mine`, the club's best healthy man at `pos`: sign within the fill budget, keep the better. */
SECTION(".r10_camp_one") void FAST camp_swap(u8 *team, u8 *mine, unsigned pos, void *menu) {
    int budget = economy_fill_budget(team);
    if (team[0x11c] < 64 && camp_pick(mine, pos, budget) && n_cpu_sign(team, pos, budget, menu)) camp_keep(team, mine);
}

/* A full camp roster's cut for a missing specialist: no QB, K or P, depth row 2 or below (rows 0 and 1, +0x28 bits
 * 10-12, are seated starters), at a position above its smart-cut minimum (cut_rows row 2). */
SECTION(".r10_camp_ok") unsigned camp_cuttable(u8 *team, u8 *q) {
    unsigned pos = q[0x35];
    return pos >= 3 && pos < 17 && (*(u16 *)(q + 0x28) >> 10 & 7) >= 2 && n_at_position(team, pos) > cut_rows[2][pos];
}

/* The lowest-rated cuttable man (0x246D80 in whole points), or 0. */
SECTION(".r10_camp_cut") u8 *camp_cut(u8 *team) {
    u8 *best = 0;
    unsigned low = 256;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        u8 *q = ((u8 **)team)[i];
        unsigned r;
        if (camp_cuttable(team, q) && (r = economy_points(q)) < low) { low = r; best = q; }
    }
    return best;
}

/* Review G6 (panel 74003, 2035: a club opened the season with no punter; the in-season cover only signed one at week 1):
 * a CPU club with no healthy man at K or P in camp signs one (0x322BB0 with 0xFFFF, as the in-season cover does: its gate
 * keeps the cap rule), after cutting camp_cut's man if the roster is full. */
SECTION(".r10_camp_cover") void FAST camp_cover(u8 *team, unsigned pos, void *menu) {
    u8 *cut;
    if (team[0x11c] >= 64) {
        if (!(cut = camp_cut(team))) return;
        economy_release(team, cut);
    }
    n_cpu_sign(team, pos, 0xFFFF, menu);
}

/* One position in camp: cover a missing specialist, else compete. */
SECTION(".r10_camp_pos") void FAST camp_one(u8 *team, unsigned pos, void *menu) {
    u8 *mine = best_at((u8 **)team, team[0x11c], pos);
    if (mine) camp_swap(team, mine, pos, menu);
    else camp_cover(team, pos, menu);
}

SECTION(".r10_camp") void FAST economy_camp(u8 *team, void *menu) {
    if (STAGE != 6 || n_human(team)) return;
    camp_one(team, 1, menu);
    camp_one(team, 2, menu);
}

/* ---- b81 economy revision 10: prove-it hole priority (coordinator 11/25: the team-building lane's DESIGN 3.4, which it
 * could not build without the economy's windows). When the prove-it pass has found a club for a long-unsigned man,
 * a club with a hole at his position that can also sign him gets first call: the one of them with the most room.
 * A hole is the shared team-need rule (tools/common/team_need.h, coordinator ruling N1 and its 11/25 header ruling; each
 * owner compiles its own copy) exactly as team building's free-agency wish reads it (tb_new_score): a club's need seats
 * at the pool are its first TN_NEED_SEATS present men of the pool by depth row (ties: roster order), an empty seat
 * rating 0; ratings are 0x246D80(p, 0) in whole points (tn_points); he is HOLE_MARGIN points or more above the club's
 * weakest seat, and that seat's mid-rank on the league scale (every club's need seats, empties 0: tn_percentile) is
 * in the bottom quarter. The club's own seats first take an unseated present man HOLE_MARGIN above the weakest (review
 * S1, tb_bench: a signing appends a man without the depth sort, so a hole just filled would read as open again).
 * Quarterbacks (the quarterback room's), K, P and FB (no need seats) keep the old choice. A club a person owns never
 * gets the call. ---- */
#include "team_need.h"
#define HOLE_MARGIN 3u                          /* points: team building's MARGIN */
#define HOLE_LINE (TN_SCALE / 4u)               /* team building's HOLE: a mid-rank below it is the bottom quarter */
struct scale { unsigned v, below, equal, n; };
struct pick { u8 *club; int most; };

/* 0x246D80(p, 0) in whole points (team building's tb_points). */
SECTION(".r10_pts") unsigned economy_points(u8 *p) {
    union { float f; unsigned u; } v;
    v.f = n_rating(p, 0);
    return tn_points(v.u);
}

/* A present man of `pool`. */
SECTION(".r10_pool_man") unsigned pool_man(u8 *o, unsigned pool) {
    return o[0x35] < 17 && TN_POOL[o[0x35]] == pool && tn_present(o);
}

static inline unsigned row_or_none(u8 *p) { return p ? tn_row(p) : 8u; }

/* Seat o among m's first two present men by depth row, ties in roster order (team building's tb_seat). */
SECTION(".r10_seat_in") void seat_in(u8 **m, unsigned seats __attribute__((unused)), u8 *o) {
    unsigned r = tn_row(o);
    if (r < row_or_none(m[0])) m[1] = m[0], m[0] = o;
    else if (r < row_or_none(m[1])) m[1] = o;
}

/* f(m, the pool's need seats, o) for each present man o of `pool` on the club, in roster order. */
typedef void each_fn(u8 **m, unsigned seats, u8 *o);
SECTION(".r10_each") void each_man(u8 *team, unsigned pool, u8 **m, each_fn *f) {
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        u8 *o = ((u8 **)team)[i];
        if (pool_man(o, pool)) f(m, TN_NEED_SEATS[pool], o);
    }
}

/* A club's first two present men of `pool` (team building's tb_seats); the first TN_NEED_SEATS are its need seats. */
SECTION(".r10_club_seats") void club_seats(u8 *team, unsigned pool, u8 **m) {
    m[0] = m[1] = 0;
    each_man(team, pool, m, seat_in);
}

/* Need seat k in points, an empty seat 0. */
SECTION(".r10_seat_pts") unsigned seat_pts(u8 **m, unsigned k) {
    return m[k] ? economy_points(m[k]) : 0;
}

/* One club's need seats at `pool` counted against s->v: rated below it, equal to it, all. */
SECTION(".r10_count") void count_club(u8 *team, unsigned pool, struct scale *s) {
    u8 *m[2];
    club_seats(team, pool, m);
    for (unsigned k = 0; k < TN_NEED_SEATS[pool]; ++k) {
        unsigned r = seat_pts(m, k);
        s->below += r < s->v;
        s->equal += r == s->v;
        ++s->n;
    }
}

/* The mid-rank of `v` on the league scale at `pool` (every club's need seats, empties 0), in 256ths: the header's
 * tn_percentile, (below + equal / 2) / n. */
SECTION(".r10_league") unsigned economy_league_pct(unsigned pool, unsigned v) {
    struct scale s = {v, 0, 0, 0};
    for (unsigned t = 0; t < n_teams(); ++t) count_club(n_team(t), pool, &s);
    return s.n ? (2 * s.below + s.equal) * (TN_SCALE / 2u) / s.n : TN_SCALE;
}

/* The weakest of m's `seats` need seats in points; *w its index. */
SECTION(".r10_low") unsigned low_seat(u8 **m, unsigned seats, unsigned *w) {
    unsigned low = 256;
    for (unsigned k = 0; k < seats; ++k) {
        unsigned r = seat_pts(m, k);
        if (r < low) low = r, *w = k;
    }
    return low;
}

/* Review S1 for one man (team building's tb_bench_man): unseated and HOLE_MARGIN or more above the weakest seat, he
 * takes it. */
SECTION(".r10_bench") void bench_man(u8 **m, unsigned seats, u8 *o) {
    unsigned w = 0;
    if (o == m[0] || (seats > 1 && o == m[1])) return;
    if (economy_points(o) >= low_seat(m, seats, &w) + HOLE_MARGIN) m[w] = o;
}

/* The club's weakest need seat at `pool` in points, after review S1 over its present men in roster order. */
SECTION(".r10_weakest") unsigned economy_weakest(u8 *team, unsigned pool) {
    u8 *m[2];
    unsigned seats = TN_NEED_SEATS[pool], w;
    club_seats(team, pool, m);
    each_man(team, pool, m, bench_man);
    return low_seat(m, seats, &w);
}

/* The club has a hole at his pool that he fills: HOLE_MARGIN points above its weakest need seat, and that seat's mid-rank
 * on the league scale in the bottom quarter (tn_percentile: (below + equal / 2) / n in 256ths). */
SECTION(".r10_hole") unsigned economy_hole_p(u8 *team, u8 *p) {
    unsigned pool = TN_POOL[p[0x35]], weak = economy_weakest(team, pool);
    return economy_points(p) >= weak + HOLE_MARGIN && economy_league_pct(pool, weak) < HOLE_LINE;
}

/* `team`, if it can sign him now and pay `ask` with more usable room than k->most (not a person's club, not busy or full
 * this week, a level for him as economy_best_room reads it) and has a hole he fills, becomes the pick. */
SECTION(".r10_level") unsigned level_ok(u8 *team, u8 *p) {
    return club_level(team, p[0x35], n_rating(p, 1), team[0x11c] >= 53);
}

/* The room a hole club may spend on him: its usable room less its floor fills (a club under 50 keeps a minimum for each
 * man it still needs to 49, as economy_best_room does; review N1). */
SECTION(".r10_hole_room") int FAST hole_room(u8 *team) {
    int room = economy_usable_room(team), short_of = FLOOR_PLAYERS - 1 - team[0x11c];
    return short_of > 0 ? room - short_of * (int)economy_floor(0) : room;
}

SECTION(".r10_could") void hole_pick(u8 *team, u8 *p, unsigned ask, struct pick *k) {
    int room = hole_room(team);
    if (room >= (int)ask && room > k->most && !n_human(team) && level_ok(team, p) && economy_hole_p(team, p)) {
        k->most = room;
        k->club = team;
    }
}

/* Called by the prove-it pass with the club economy_best_room chose: the hole club with the most room, else that club. */
SECTION(".r10_holefirst") u8 *economy_hole_first(u8 *p, unsigned ask, u8 *club) {
    struct pick k = {club, -1};
    if (p[0x35] && TN_NEED_SEATS[TN_POOL[p[0x35]]])
        for (unsigned t = 0; t < n_teams(); ++t) hole_pick(n_team(t), p, ask, &k);
    return k.club;
}

/* The prove-it pass's club for him (economy_week): the club economy_best_room chose if it has room for his ask, then a
 * hole club first. Kept out of economy_week so the week window's stage stubs (economy_after, economy_stage6) stay at
 * their revision 3-9 addresses: the stage hook sites 0x248628 and 0x24809C keep their bytes, which the Player Progress
 * owner accepts inside its guarded span. */
SECTION(".r10_prove") u8 *economy_prove_club(u8 *p, unsigned ask) {
    u8 *club = 0;
    if (economy_best_room(p, &club) < ask || !club) return 0;
    return economy_hole_first(p, ask, club);
}
