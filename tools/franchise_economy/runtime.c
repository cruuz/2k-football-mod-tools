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

static unsigned maximum(unsigned a, unsigned b) { return a > b ? a : b; }
static unsigned minimum(unsigned a, unsigned b) { return a < b ? a : b; }

SECTION(".value") unsigned FAST economy_value(u8 *p, unsigned floor_apy,
                                              unsigned surplus, unsigned aging, unsigned years) {
    unsigned pos = p[0x35], pro = p[0x25] & 31;
    if (pos >= 17) return 0;
    float ovr = ((float (FAST *)(u8 *, unsigned))0x246d80)(p, 0);
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
    unsigned year = minimum(*(u32 *)0xe576b8, 4);
    unsigned floor = (minimums[minimum(pro, 7)] + year * 45 + 3) / 4;
    if (value < floor) value = (float)floor;
    if (surplus && (p[0x24] & 15) && (p[0x27] & 15)) {
        unsigned salary = ((unsigned (FAST *)(u8 *))0xe6380)(p);
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
    return (unsigned)value;
}

SECTION(".contracts") void FAST economy_contract(u8 *p, unsigned low, unsigned high, unsigned floor_apy) {
    unsigned years = minimum(maximum(low, 1), 7);
    if (high >= years) years += ((unsigned (FAST *)(void *))0x48b50)((void *)0xe5fca0) %
                               (minimum(high, 7) - years + 1);
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

/* DESIGN: replace the native CPU cap-cut routine with a bounded reconciliation
 * that also runs after the rollover returns IR players. Keep the native 54
 * player/cap gate intact; release through the real transaction and FA paths.
 * Preserve two QBs and at least one player in every other occupied position.
 * The 42-player floor prevents a financial fix from emptying a legal roster.
 */
SECTION(".reconcile") void FAST economy_reconcile(u8 *team) {
    for (unsigned attempt = 0; attempt < 65; ++attempt) {
        ((void (FAST *)(u8 *))0xc3f00)(team);
        unsigned count = team[0x11c];
        unsigned cap = economy_cap(team, 1, 0), payroll = *(u32 *)(team + 0x124);
        if ((count <= 54 && payroll <= cap) || count <= 42) return;
        u8 *best = 0;
        float score = 2.0f;
        for (unsigned i = 0; i < count; ++i) {
            u8 *p = ((u8 **)team)[i];
            unsigned pos = p[0x35], same = 0;
            for (unsigned j = 0; j < count; ++j) same += ((u8 **)team)[j][0x35] == pos;
            if (same <= (pos == 0 ? 2u : 1u)) continue;
            unsigned salary = (p[0x24] & 15) ? ((unsigned (FAST *)(u8 *))0xe6380)(p) : 0;
            if (payroll > cap && !salary) continue;
            float rating = ((float (FAST *)(u8 *, unsigned))0x246d80)(p, 0);
            if (rating < score) { score = rating; best = p; }
        }
        if (!best) return;
        economy_penalty(team, best, 0);
        ((void (FAST *)(u8 *, u8 *, unsigned, unsigned))0x2bd900)(team, best, 1, 1);
    }
}

/* DESIGN: the retail CPU fill loop uses an unlimited budget and can add
 * several players after its single roster check. Check each transaction.
 * Ten game thousands cover the generated contract's upward rounding.
 */
SECTION(".fill_room") unsigned FAST economy_fill_room(u8 *team, unsigned budget) {
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
SECTION(".renew_room") unsigned FAST economy_renew_room(u8 *p, u8 *team) {
    u8 remaining = p[0x24];
    p[0x24] &= 0xf0;
    ((void (FAST *)(u8 *))0xc3f00)(team);
    int room = economy_cap(team, 1, 0) - *(u32 *)(team + 0x124);
    p[0x24] = remaining;
    ((void (FAST *)(u8 *))0xc3f00)(team);
    return room >= (int)economy_value(p, !!(remaining & 15), 0, 1, 0) + 10;
}

SECTION(".renew_gate") __attribute__((naked)) void economy_renew_gate(void) {
    __asm__("mov %esi, %ecx\nmov %edi, %edx\ncall economy_renew_room\n"
            "test %eax, %eax\njz 1f\npush %ebx\nmov 0x24(%esi), %ebx\n"
            "and $15, %bl\njmp 0x322eb7\n1: ret\n");
}
