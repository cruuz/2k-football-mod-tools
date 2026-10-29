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

static unsigned maximum(unsigned a, unsigned b) { return a > b ? a : b; }
static unsigned minimum(unsigned a, unsigned b) { return a < b ? a : b; }

static unsigned economy_floor(unsigned pro);

SECTION(".value") unsigned FAST economy_value(u8 *p, unsigned floor_apy,
                                              unsigned surplus, unsigned aging, unsigned years) {
    unsigned pos = p[0x35], pro = p[0x25] & 31;
    if (pos >= 17) return 0;
    float ovr = n_rating(p, 0);
    float quality = (ovr - 0.45f) / 0.55f;
    if (!(quality > 0.0f)) quality = 0.0f;
    if (quality > 1.0f) quality = 1.0f;
    float value = market[pos] * quality * quality * quality;
    value *= *(u32 *)0xe3c278 / 75300.0f;
    if (aging && pro > decline_after[pos]) {
        float age = 1.0f - (pro - decline_after[pos]) * 0.08f;
        if (age < 0.25f) age = 0.25f;
        value *= age;
    }
    unsigned floor = economy_floor(pro);
    if (value < floor) value = (float)floor;
    if (surplus && (p[0x24] & 15) && (p[0x27] & 15)) {
        unsigned salary = n_salary(p);
        salary += *(u16 *)(p + 10) * (p[0x26] >> 4) / (p[0x27] & 15);
        value += (value - salary) * minimum(years, 4) * 0.5f;
        if (value < 1.0f) value = 1.0f;
    }
    if (floor_apy && (p[0x27] & 15)) {
        unsigned apy = *(u16 *)(p + 10) * 10u / (p[0x27] & 15);
        if (value < apy) value = (float)apy;
    }
    /* Callers truncate to AX. Never wrap an expensive player to near zero. */
    if (value > 60000.0f) value = 60000.0f;
    /* b778 fa2: after two unsigned weeks a high-overall free agent asks no more
     * than the best room on the table (never below his minimum). */
    if (PROVE_IT_FREE_AGENT(p) && n_rating(p, 1) > PROVE_IT) {
        unsigned best = economy_best_room(p, 0);
        if (value > best) value = (float)maximum(best, floor);
    }
    return (unsigned)value;
}

/* DESIGN: the CBA minimum salary for a player's years of service, grown with the season index. */
SECTION(".penalty") static unsigned economy_floor(unsigned pro) {
    return (minimums[minimum(pro, 7)] + minimum(*(u32 *)0xe576b8, 4) * 45 + 3) / 4;
}

SECTION(".contracts") void FAST economy_contract(u8 *p, unsigned low, unsigned high, unsigned floor_apy) {
    unsigned years = minimum(maximum(low, 1), 7);
    if (high >= years) years += n_rand(RNG) % (minimum(high, 7) - years + 1);
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

SECTION(".fill_gate") __attribute__((naked)) void economy_fill_gate(void) {
    __asm__("mov 4(%esp), %ecx\nmov 12(%esp), %edx\n"
            "call economy_fill_room\ntest %eax, %eax\njz 1f\n"
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
    if (*(u32 *)(team + 0x124) + charge > (unsigned)economy_cap(team, 1, 0)) return 0;
    p[0x26] = kind | bonus << 4;
    return 1;
}

SECTION(".offer_gate") __attribute__((naked)) void economy_offer_gate(void) {
    __asm__("mov %edi, %ecx\ncall economy_offer_room\ntest %eax, %eax\n"
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
    if (left < 2 || left > len || kind > 7 || bonus > 9) return 0;
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

/* Restructure the contract that makes the most room, at least $1M real. */
SECTION(".roster_b") static unsigned restructure_best(u8 *team) {
    u8 *best = 0;
    int most = 250;
    for (unsigned i = 0; i < team[0x11c]; ++i) {
        int saving = economy_restructure(((u8 **)team)[i], 0);
        if (saving > most) { most = saving; best = ((u8 **)team)[i]; }
    }
    if (best) economy_restructure(best, 1);
    return best != 0;
}

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
        if (count <= 54 && room >= 0 && !force) return;
        if (room < 0 && CPU(team) && restructure_best(team)) continue;
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
        n_release(team, best, 1, 1);
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
    (want ? n_need_want : n_need_low)(need, team);
    for (unsigned pos = 0; pos < 17; ++pos)
        while (need[pos] < 0) {
            ++need[pos];
            int budget = n_human(team) ? ROOM(team) : 0xffff;
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
    for (unsigned attempt = 0; attempt < 12; ++attempt) {
        trim(team, 0);
        fill(team, menu, 1.0f, 0, 1);
        fill(team, menu, 1.0f, 1, 1);
        if (team[0x11c] >= FLOOR_PLAYERS || ROOM(team) >= (int)(2 * economy_floor(0)) + 10) return;
        if (!restructure_best(team)) trim(team, 1);
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
        unsigned count = team[0x11c], better = 0, busy = 0, level;
        if (!CPU(team)) continue;
        for (unsigned j = 0; j < count; ++j) {
            u8 *q = ((u8 **)team)[j];
            busy |= q[0x25] >= 0x40;     /* signed a long-unsigned free agent since this week's count */
            if (q[0x35] == pos && !(n_rating(q, 1) < him)) ++better;
        }
        level = busy ? 0 : better < n_minimum_at(pos) ? 2 : better < n_wanted_at(pos) ? 1 : 0;
        int room = ROOM(team) - 10;
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
        if (economy_best_room(p, &club) < ask || !club) continue;
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
        do n_recount(team);
        while (*(int *)(team + 0x124) + 6000 >= economy_cap(team, 1, 0) && restructure_best(team));
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

SECTION(".week") __attribute__((naked)) void economy_after(void) {
    __asm__("mov %ebx, %ecx\nxor %edx, %edx\ncall economy_clubs\njmp 0xc4bb0\n");
}

SECTION(".week") __attribute__((naked)) void economy_stage6(void) {
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
 * (nfl2k5_position_pools), so an OLB slot becomes LB (11). */
#define CLASS_SIZE 450
SECTION(".roster_f_rodata") static const u8 class_counts[17] = {
    21, 9, 9, 37, 44, 18, 14, 25, 9, 25, 18, 18, 30, 28, 44, 49, 52};

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

/* b779 rc1 (Noah 10/28: "make it smart, so teams aren't cutting guys that they need at certain positions. They'll
 * prioritize the lowest overall at a position where they have more than they need, according to modern NFL
 * position keeping"). Replaces the native cut-down 0x2BF9A0 (fastcall team, target; every caller: the preseason
 * gate, retail's Simulate Preseason, the economy's trims, MyCareer's signing room). While the club has more than
 * `target` active players it releases (native 0x2BD900, as the native cut does) the lowest-rated player at a
 * position still above its minimum; only when no position is above its minimum, the lowest-rated player at a
 * position with two or more. Minimums: 2024 53-man rosters (atlantafalcons.com, 2024-08-28, all 32 teams:
 * QB 2.4, RB 3.6, WR 5.9, TE 3.3, OL 9.4, DL 7.9, LB 7.3, DB 10.3, K 1, P 1 on average), at or below the league
 * average: QB 2, K 1, P 1, WR 5, CB 5, FS 2, SS 2, HB 3, FB 0, TE 3, LB 5 (OLB 3 + ILB 2 when the league has
 * OLBs, else ILB 5 under the one-pool scheme), C 2, G 3, T 3 (OL 8), DT 3, DE 4 (DL 7). 44 in all. */
SECTION(".roster_l_rodata") static const u8 cut_min[17] = {2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 3, 2, 2, 3, 3, 3, 4};

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
    u8 mins[17], *best;
    for (unsigned i = 0; i < 17; ++i) mins[i] = cut_min[i];
    if (!league_has_olb()) { mins[10] = 0; mins[11] = 5; }
    while (team[0x11c] > target && ((best = cut_pick(team, mins, 0)) || (best = cut_pick(team, mins, 1))))
        n_release(team, best, 1, 1);
}
