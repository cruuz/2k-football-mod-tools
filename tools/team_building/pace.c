/* b81 #45 (sim speed): the team-building owner's pace page (nfl2k5_xbe_space.TEAM_BUILDING_PACE_VA, 0x1535000), built
 * with runtime.c by tools/team_building/assemble.py. Freestanding i386 C; its own translation unit. The page is in the
 * scale-out pool (RWX): its first word, pace_day, is the only writable word; the day itself lives in the stack frame of
 * pace_day_entry.
 *
 * Why: the offseason's free-agency stage (stage 3 -> 4) runs 0x324600 once a day from the stage action (0x24849A; 45
 * days a season): the day's signings (0x324060), the CPU wishes (0x3242C0, where this owner prices every free agent who
 * would start for a club through economy_value), the offers and their aging. The economy's revision-10 price ranks a
 * player among every rostered man of his position group (rank_twice), which rated the whole group again for every price:
 * 8.5 million native ratings (0x246D80, about 1,050 instructions each) in one stage on seed 2501, 9.6 times the v0.9
 * control's instructions for that advance.
 *
 * What, with no decision changed:
 * - pace_day_entry replaces the day's call at 0x24849A (`call 0x324600` -> `call 0x1535010`). Its frame holds the day:
 *   a memo of 0x246D80(p, 0) by player record, empty at the start of each day, and the rank lists. pace_day points at it
 *   while the day runs and is 0 otherwise. No code run inside a day writes a rating's inputs (player bytes 0x2A, 0x2B
 *   and 0x35..0x50, read by 0x246D80 through its attribute table; its own write of 0x2A for linemen, 0x1D2400, is undone
 *   before it returns), so a memoized rating is the value the native routine returns: the memo holds the native float
 *   itself (every return path of 0x246D80 loads a float from memory).
 * - pace_rate(p, flag) is 0x246D80(p, flag) (same ABI): flag 0 inside a day reads the memo, everything else calls the
 *   native routine. The team-building owner rates with it.
 * - pace_lists(1), called by the team-building owner when a club's scoring starts (its view and per-position search
 *   write nothing), lists every rostered man of each price group from the live rosters; pace_lists(0) drops them before
 *   the club's offers (0x324180 may change a roster). Nothing else builds or drops them.
 * - pace_rank_twice is the economy's rank_twice (runtime.c: 2 + 2 x others of his price group rated above him + others
 *   level with him, over every club's active list, a man at position 17 or above in no group, the man himself left
 *   out): counted on the lists while they stand, otherwise over the active lists as rank_club does, every rating through
 *   pace_rate. The economy's price reaches it through rank_any (runtime.c) only when 0x24849A calls this page.
 * Outside a day (any other stage, or a day run from a free-agency screen) every rating is the native one, as before.
 *
 * Fixed layout (the economy's rank_any and the 0x24849A site name these addresses): +0x00 pace_day, +0x04 "PACE",
 * +0x10 jmp pace_day_entry, +0x18 jmp pace_rank_twice, +0x20 jmp pace_rate, +0x28 jmp pace_lists.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FAST __attribute__((fastcall))
#define SECTION(s) __attribute__((section(s), used))
#define ROSTER_ROOT (*(u8 **)0xB72918)
#define PACE_PLAYERS 4096u                  /* the roster arena's player records (an index fits 12 bits) */
#define PACE_MEN 2112u                      /* 32 clubs x 66: with more rostered men the lists stay off */
#define PACE_GROUPS 15u                     /* economy price groups (a group fits 4 bits; assemble.py checks) */
extern float FAST n_rating(u8 *p, unsigned flag);                 /* 0x246D80 */
extern u8 *FAST n_team(unsigned index);                            /* 0xC4C50 */
extern unsigned n_teams(void);                                     /* 0xC4BE0 */
extern void FAST n_fa_day(void *menu);                             /* 0x324600: one free-agency day (ECX = menu) */
extern const u8 price_group[17];                                   /* the economy's position -> price group table */

struct pace {
    u32 lists;                              /* the lists below are the live rosters' */
    u16 end[PACE_GROUPS];                   /* group g's men: men[g ? end[g - 1] : 0 .. end[g]) */
    u16 men[PACE_MEN];                      /* player record indices */
    u32 known[PACE_PLAYERS / 32];           /* rate[i] holds 0x246D80(record i, 0) */
    float rate[PACE_PLAYERS];
};
extern struct pace *volatile pace_day;
unsigned pace_rank_twice(u8 *p);
float FAST pace_rate(u8 *p, unsigned flag);
void FAST pace_lists(unsigned on);
void FAST pace_day_entry(void *menu);

__attribute__((section(".pace_head"), used, naked)) void pace_head(void) {
    __asm__(".globl pace_day\npace_day: .long 0\n.ascii \"PACE\"\n.long 0, 0\n"
            "jmp pace_day_entry\n.p2align 3, 0xcc\njmp pace_rank_twice\n.p2align 3, 0xcc\n"
            "jmp pace_rate\n.p2align 3, 0xcc\njmp pace_lists\n.p2align 3, 0xcc\n");
}

/* The player record index of p (records of 84 bytes from the roster root's array), or PACE_PLAYERS when p is none:
   off / 84 is (off / 4) times 0x3CF3CF3D, the inverse of 21 modulo 2^32: below the record count only when off is a
   multiple of 84. */
__attribute__((always_inline)) static inline u32 pace_index(u8 *p) {
    u8 *root = ROSTER_ROOT;
    u32 off = (u32)(p - *(u8 **)(root + 4)), i = (off >> 2) * 0x3CF3CF3Du;
    return !(off & 3) && i < *(u32 *)root && i < PACE_PLAYERS ? i : PACE_PLAYERS;
}

/* The memo's first read of record i: the native rating, kept (out of line: the lookups below stay short). */
SECTION(".pace") __attribute__((noinline)) static void pace_fill(struct pace *d, u32 i) {
    d->rate[i] = n_rating(*(u8 **)(ROSTER_ROOT + 4) + 84 * i, 0);
    d->known[i >> 5] |= 1u << (i & 31);
}

__attribute__((always_inline)) static inline float pace_rated(struct pace *d, u32 i) {
    if (!(d->known[i >> 5] >> (i & 31) & 1)) pace_fill(d, i);
    return d->rate[i];
}

SECTION(".pace") float FAST pace_rate(u8 *p, unsigned flag) {
    struct pace *d = pace_day;
    u32 i;
    if (!d || flag || (i = pace_index(p)) >= PACE_PLAYERS) return n_rating(p, flag);
    return pace_rated(d, i);
}

SECTION(".pace") void FAST pace_day_entry(void *menu) {
    struct pace d;
    struct pace *before = pace_day;
    d.lists = 0;
    for (u32 k = 0; k < PACE_PLAYERS / 32; ++k) d.known[k] = 0;
    pace_day = &d;
    n_fa_day(menu);
    pace_day = before;
}

SECTION(".pace") void FAST pace_lists(unsigned on) {
    struct pace *d = pace_day;
    u32 n[PACE_GROUPS], next[PACE_GROUPS], total = 0;
    if (!d) return;
    d->lists = 0;
    if (!on) return;
    for (u32 g = 0; g < PACE_GROUPS; ++g) n[g] = 0;
    /* one walk of every club's active list: each man's price group and record index, packed g << 12 | i */
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        for (unsigned k = 0; k < team[0x11c]; ++k) {
            u8 *q = ((u8 **)team)[k];
            u32 i, g;
            if (q[0x35] >= 17) continue;
            if ((i = pace_index(q)) >= PACE_PLAYERS || (g = price_group[q[0x35]]) >= PACE_GROUPS || total >= PACE_MEN)
                return;
            d->men[total++] = (u16)(g << 12 | i);
            n[g]++;
        }
    }
    for (u32 g = 0, end = 0; g < PACE_GROUPS; ++g) next[g] = end, end += n[g], d->end[g] = (u16)end;
    /* in place by group (each slot goes to its group's next free slot), then the group bits off */
    for (u32 g = 0; g < PACE_GROUPS; ++g)
        while (next[g] < d->end[g]) {
            u16 e = d->men[next[g]];
            u32 h = e >> 12;
            if (h == g) {
                next[g]++;
            } else {
                d->men[next[g]] = d->men[next[h]];
                d->men[next[h]++] = e;
            }
        }
    for (u32 k = 0; k < total; ++k) d->men[k] &= 0xFFF;
    d->lists = 1;
}

SECTION(".pace") unsigned pace_rank_twice(u8 *p) {
    unsigned g = price_group[p[0x35]], n2 = 2;
    float him = pace_rate(p, 0);
    struct pace *d = pace_day;
    if (d && d->lists && g < PACE_GROUPS) {
        u32 self = pace_index(p);
        for (u32 k = g ? d->end[g - 1] : 0; k < d->end[g]; ++k) {
            u32 i = d->men[k];
            float s = pace_rated(d, i);
            n2 += s > him ? 2 : s == him && i != self;
        }
        return n2;
    }
    for (unsigned t = 0; t < n_teams(); ++t) {
        u8 *team = n_team(t);
        for (unsigned k = 0; k < team[0x11c]; ++k) {
            u8 *q = ((u8 **)team)[k];
            if (q == p || q[0x35] >= 17 || price_group[q[0x35]] != g) continue;
            float s = pace_rate(q, 0);
            n2 += s > him ? 2 : s == him;
        }
    }
    return n2;
}
