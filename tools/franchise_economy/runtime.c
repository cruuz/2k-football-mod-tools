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

SECTION(".week") __attribute__((naked)) void economy_after(void) {
    __asm__("mov %ebx, %ecx\nxor %edx, %edx\ncall economy_clubs\njmp 0xc4bb0\n");
}

SECTION(".week") __attribute__((naked)) void economy_stage6(void) {
    __asm__("xor %ecx, %ecx\nmov $1, %edx\ncall economy_clubs\njmp 0x247fd7\n");
}
