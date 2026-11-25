/* b81 team building (lane team-building; coordinator rulings 1-11 of 2026-11-25): CPU clubs draft and sign to their
 * weakest starters, judged by the shared team-need rule (tools/common/team_need.h, the trades lane's header).
 *
 * Two entries, both reached only from draft-AI sites that the owner nfl2k5_team_building retargets:
 *   tb_order   the draft pick head's need call (draft_ai _prefix_bytes, `call 0x31DEA0` at 0x31E121): same ABI as
 *              FUN_0031DEA0 (fastcall ecx = team, edx = round, [esp] = pick, [esp+4] = int need[17]; ret 8). It runs
 *              the retail need first, then, for a club the CPU runs, moves the club's HOLES to the front: positions
 *              whose weakest need-seat starter rates in the league's bottom quarter (percentile < 64/256), read one
 *              season ahead with the economy's aging line (decline_after: 1 point a year past it, at most 4), premium
 *              positions weighted 3:2, ordered by that key; then every other position in the retail order. A position
 *              where the club already took a man in this draft (one year pro on its roster), or, in rounds 1 and 2,
 *              holds a development asset (header TN_YOUNG_YEARS or fewer years pro and above the pool's median
 *              starter), is not a hole. QB is in (ruling 3). FB, K and P have no need seats; OLB is LB's alias.
 *   tb_wish_entry   the free-agent wish body's jump (draft_ai body_patch at 0x324414): replaces the draft-AI scored
 *              selection. QB, K, P and FB keep the draft AI's own score (ruling 3: quarterback signings stay with the
 *              quarterback system's rules). Every other position: the best present free agent the club can pay there
 *              (his economy_value ask within
 *              economy_room_for_signing, the economy's revision-9 routine: cap room less 10), wished for when he is 3 points better than the
 *              club's weakest need-seat starter; a hole scores first (100000 + its depth, premium 3:2), a count deficit
 *              next (50000 + 1200 a man), an upgrade last (points gained x VALUE + 0..6 points of jitter); no wish
 *              otherwise. Then the draft AI's selection: the best four above 0 through 0x324180.
 * No writable data. Compiled by tools/team_building/assemble.py into proven-unreferenced retail functions
 * (tools/team_building/dead_code.py), one input section per window. */
#include "../common/team_need.h"

typedef unsigned char u8;
typedef unsigned int u32;
typedef int i32;
#define FAST __attribute__((fastcall))
#define SECTION(s) __attribute__((section(s), used, noinline))

extern float FAST n_rating(u8 *p, unsigned flag);                          /* 0x246D80 */
extern unsigned FAST n_human(u8 *team);                                     /* 0x13EC30 */
extern u8 *FAST n_team(unsigned index);                                     /* 0xC4C50 */
extern unsigned n_teams(void);                                              /* 0xC4BE0 */
extern unsigned FAST n_at_position(u8 *team, unsigned pos);                 /* 0xC3CB0 */
extern unsigned FAST n_minimum_at(unsigned pos);                            /* 0x2BD410 */
extern unsigned FAST n_maximum_at(unsigned pos);                            /* 0x2BD400 */
extern unsigned n_game_rand(void);                                          /* 0x48BC0 (the wish routine's RNG) */
extern void FAST n_need(u8 *team, unsigned round, unsigned pick, int *need); /* 0x31DEA0 */
extern unsigned FAST economy_value(u8 *p, unsigned floor_apy, unsigned surplus, unsigned aging, unsigned years);
extern int FAST economy_room_for_signing(u8 *team);                         /* 0x2D82F0, economy revision 9 */

#define FA_LIST ((u32 *)(*(u8 **)0xB72918 + 0x38))
#define DRAFT_VALUE ((const float *)0x10AF0)   /* draft_ai VALUE[17], then DEFICIT_BONUS, JITTER/256, THRESHOLD */
#define HOLE (TN_SCALE / 4u)                   /* percentile below this = the league's bottom quarter */
#define MARGIN 3u                              /* the depth-lock release margin: a signing must start */
#define SCALE_MAX 64u                          /* 32 clubs x 2 need seats */
#define NONE 255u

struct view {
    u8 weak[TN_POSITIONS];       /* this club: weakest need-seat present man's points (0: a seat empty) */
    u8 wpro[TN_POSITIONS];       /* his years pro */
    u8 young[TN_POSITIONS];      /* best points of a present man with 1..TN_YOUNG_YEARS years pro */
    u8 drafted[TN_POSITIONS];    /* a man with exactly one year pro (taken in this draft) */
    u8 n[TN_POSITIONS];          /* league scale sizes */
    u8 scale[TN_POSITIONS][SCALE_MAX];
};

extern const u8 tb_decline_after[TN_POSITIONS];
extern const u8 tb_value[TN_POSITIONS];

SECTION(".tb_a") u32 tb_points(u8 *p) {
    union { float f; u32 u; } v;
    v.f = n_rating(p, 0);
    return tn_points(v.u);
}

SECTION(".tb_a") void tb_zero(void *p, u32 n) {
    while (n--) ((u8 *)p)[n] = 0;
}

static inline u32 row_or_none(const u8 *p) { return p ? tn_row(p) : 8u; }

/* Seat o among a pool's first two present men by row (ties: list order). */
SECTION(".tb_w") void tb_seat(u8 **m, u8 *o) {
    u32 r = tn_row(o);
    if (r < row_or_none(m[0])) m[1] = m[0], m[0] = o;
    else if (r < row_or_none(m[1])) m[1] = o;
}

/* One club: its first two present men of each pool in row order; men[pool * 2 + k]. */
SECTION(".tb_b") void tb_seats(u8 *team, u8 **men) {
    u32 n = team[0x11C];
    tb_zero(men, TN_POSITIONS * 2 * sizeof *men);
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        if (o[0x35] < TN_POSITIONS && tn_present(o)) tb_seat(men + 2 * TN_POOL[o[0x35]], o);
    }
}

/* Insert v into an ascending scale of *n values. */
SECTION(".tb_c") void tb_insert(u8 *scale, u8 *n, u32 v) {
    u32 k = *n;
    if (k >= SCALE_MAX) return;
    while (k && scale[k - 1] > v) scale[k] = scale[k - 1], k--;
    scale[k] = (u8)v;
    (*n)++;
}

/* One pool of one club: its need seats into the league scale (an empty need seat rates 0 there too, header
   1fbb90087); for the own club the weakest. */
SECTION(".tb_r") void tb_pool(struct view *x, u8 **m, u32 pool, u32 own) {
    u32 seats = TN_NEED_SEATS[pool], weak = 255, wpro = 0;
    for (u32 k = 0; k < seats; k++) {
        u32 r = m[k] ? tb_points(m[k]) : 0;
        tb_insert(x->scale[pool], &x->n[pool], r);
        if (r < weak) weak = r, wpro = m[k] ? m[k][0x25] & 31 : 0;
    }
    if (own && seats) x->weak[pool] = (u8)weak, x->wpro[pool] = (u8)wpro;
}

/* One club into the league scales; for the own club also its weakest need-seat men. */
SECTION(".tb_d") void tb_club(struct view *x, u8 *team, u32 own) {
    u8 *men[TN_POSITIONS * 2];
    tb_seats(team, men);
    for (u32 pool = 0; pool < TN_POSITIONS; pool++) tb_pool(x, men + 2 * pool, pool, own);
}

/* Development assets and this draft's picks of the own club. */
SECTION(".tb_e") void tb_young(struct view *x, u8 *team) {
    u32 n = team[0x11C];
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        u32 pos = o[0x35], pro = o[0x25] & 31, pool, r;
        if (pos >= TN_POSITIONS || !pro || pro > TN_YOUNG_YEARS) continue;
        pool = TN_POOL[pos];
        if (pro == 1) x->drafted[pool] = 1;
        if (tn_present(o) && (r = tb_points(o)) > x->young[pool]) x->young[pool] = (u8)r;
    }
}

/* The league and the club `team`. */
SECTION(".tb_f") void tb_view(struct view *x, u8 *team) {
    u32 clubs = n_teams();
    tb_zero(x, sizeof *x);
    for (u32 i = 0; i < clubs; i++) {
        u8 *t = n_team(i);
        if (t) tb_club(x, t, t == team);
    }
    tb_young(x, team);
}

/* A rating's percentile on a pool's league scale (the header's tn_percentile: mid-rank, the men rated below plus half
   of those tied, in 256ths; coordinator ruling 11/25, header 1fbb90087). */
SECTION(".tb_s") u32 tb_pct(struct view *x, u32 pool, u32 r) {
    return tn_percentile(x->scale[pool], x->n[pool], r);
}

/* The weakest need-seat man of a pool, one season ahead (the economy's decline_after line, at most 4 points). */
SECTION(".tb_sa") u32 tb_ahead(struct view *x, u32 pool) {
    u32 weak = x->weak[pool], over = x->wpro[pool] + 1u, line = tb_decline_after[pool], drop;
    drop = over > line ? over - line : 0;
    if (drop > 4) drop = 4;
    return weak > drop ? weak - drop : 0;
}

/* A development asset at the pool: a young present man above the pool's median starter. */
SECTION(".tb_z") u32 tb_asset(struct view *x, u32 pool) {
    return x->young[pool] > x->scale[pool][x->n[pool] / 2];
}

/* A pool's hole key for the draft (lower = needier; NONE = no hole). */
SECTION(".tb_g") u32 tb_key(struct view *x, u32 pool, u32 round) {
    u32 pct;
    if (!TN_NEED_SEATS[pool] || x->drafted[pool]) return NONE;
    pct = tb_pct(x, pool, tb_ahead(x, pool));
    if (pct >= HOLE || (round < 2 && tb_asset(x, pool))) return NONE;
    return TN_PREMIUM[pool] ? pct * 171u >> 8 : pct;                 /* premium 3:2 */
}

/* Holes (ascending key, ties in retail order) first, then the retail order for the rest. */
SECTION(".tb_h") void tb_reorder(int *need, const u8 *key) {
    int out[TN_POSITIONS];
    u32 n = 0;
    for (u32 k = 0; k <= NONE; k++)
        for (u32 i = 0; i < TN_POSITIONS; i++)
            if (key[need[i]] == k) out[n++] = need[i];
    for (u32 i = 0; i < TN_POSITIONS; i++) need[i] = out[i];
}

SECTION(".tb_i") void FAST tb_order(u8 *team, unsigned round, unsigned pick, int *need) {
    struct view x;
    u8 key[TN_POSITIONS];
    n_need(team, round, pick, need);
    if (n_human(team)) return;                                 /* a person's club: the retail order */
    tb_view(&x, team);
    for (u32 p = 0; p < TN_POSITIONS; p++) key[p] = (u8)(p == 10 ? NONE : tb_key(&x, TN_POOL[p], round));
    tb_reorder(need, key);
}

/* ---- free agency ---------------------------------------------------------------------------------------------- */

SECTION(".tb_u") i32 tb_deficit(u8 *team, u32 pos) {
    return (i32)n_minimum_at(pos) - (i32)n_at_position(team, pos);
}

/* His points if he is a present free agent at `pos` rated above `floor` whose ask fits `room`, else 0. */
SECTION(".tb_x") u32 tb_fits(u8 *o, u32 pos, u32 floor, i32 room) {
    u32 r;
    if (o[0x35] != pos || !tn_present(o) || (r = tb_points(o)) <= floor) return 0;
    return (i32)economy_value(o, 0, 0, 1, 1) <= room ? r : 0;
}

/* The best present free agent at `pos` rated above `floor` (the club's weakest starter + 2: only a man who would start
   counts) whose ask fits `room`; *points gets his points (0: none). The ask (economy_value) is asked only of a man
   who beats the best so far, so a scan costs one rating per free agent at the position and a few asks. */
SECTION(".tb_j") u8 *tb_candidate(u32 pos, i32 room, u32 *points, u32 floor) {
    u32 *list = FA_LIST, r;
    u8 *best = 0;
    for (u32 i = 0; i < list[0]; i++)
        if ((r = tb_fits(((u8 **)list[1])[i], pos, floor, room)) != 0) best = ((u8 **)list[1])[i], floor = r;
    *points = best ? floor : 0;
    return best;
}

/* The mean 0x246D80(p, 1) of the club's men at a position (0 when it has none): the draft AI's average. */
SECTION(".tb_v") float tb_mean(u8 *team, u32 pos) {
    u32 n = team[0x11C], count = 0;
    float sum = 0.0f;
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        if (o[0x35] == pos) sum += n_rating(o, 1), count++;
    }
    return count ? sum / (float)count : 0.0f;
}

/* x 100 to an integer (round to nearest, the FPU's default). */
SECTION(".tb_y") i32 tb_int100(float v) {
    i32 out;
    v *= 100.0f;
    __asm__("fistpl %0" : "=m"(out) : "t"(v) : "st");
    return out;
}

/* The draft AI's own score (nfl2k5_draft_ai _wish_cave_bytes), x 100 as an integer: QB, K, P and FB. */
SECTION(".tb_k") i32 tb_old_score(u8 *team, u32 pos, u8 *best) {
    float score = (n_rating(best, 1) - tb_mean(team, pos)) * 100.0f * DRAFT_VALUE[pos];
    i32 deficit = tb_deficit(team, pos);
    if (deficit > 0) score += (float)deficit * DRAFT_VALUE[17];
    return tb_int100(score + (float)(n_game_rand() & 255) * DRAFT_VALUE[18]);
}

/* Weakness first (x 100) at a position with need seats. */
SECTION(".tb_l") i32 tb_new_score(struct view *x, u8 *team, u32 pos, u32 cand) {
    u32 pool = TN_POOL[pos], weak = x->weak[pool], pct = tb_pct(x, pool, weak), up = cand >= weak + MARGIN;
    i32 deficit = tb_deficit(team, pos);
    if (up && pct < HOLE) return 100000 + (i32)((HOLE - pct) * (2u + TN_PREMIUM[pool]));
    if (deficit > 0) return 50000 + 1200 * deficit;
    if (up) return (i32)((cand - weak) * tb_value[pos] + (n_game_rand() & 255) * 600u / 256u);
    return -1;
}

/* The native wish (0x324180: EAX = player, [esp] = team, callee pops). */
SECTION(".tb_m") u32 tb_wish(u8 *p, u8 *team) {
    u32 r;
    __asm__ volatile("push %2\n\tcall 0x324180" : "=a"(r) : "a"(p), "r"(team) : "ecx", "edx", "memory", "cc");
    return r;
}

/* The draft AI's selection: the best four above 0, each position once. */
SECTION(".tb_n") u32 tb_select(u8 *team, u8 **target, i32 *score, u32 wishes) {
    while (wishes < 4) {
        u32 best = NONE;
        i32 top = 0;
        for (u32 p = 0; p < TN_POSITIONS; p++)
            if (target[p] && score[p] > top) top = score[p], best = p;
        if (best == NONE) break;
        if (tb_wish(target[best], team)) wishes++;
        target[best] = 0;
    }
    return wishes;
}

/* One position's wish target and score (x 100; 0 or less: no wish). */
SECTION(".tb_t") i32 tb_score(struct view *x, u8 *team, u32 p, u8 *best, i32 room, u8 **target) {
    u32 cand;
    *target = 0;
    if (!best || n_at_position(team, p) >= n_maximum_at(p)) return 0;
    *target = best;
    if (!TN_NEED_SEATS[TN_POOL[p]] || p == TN_FB) return tb_old_score(team, p, best);
    if ((*target = tb_candidate(p, room, &cand, x->weak[TN_POOL[p]] + MARGIN - 1)) == 0) *target = best;
    return tb_new_score(x, team, p, cand);
}

SECTION(".tb_o") u32 FAST tb_wishes(u8 *team, u8 **best, u32 wishes) {
    struct view x;
    u8 *target[TN_POSITIONS];
    i32 score[TN_POSITIONS];
    i32 room = economy_room_for_signing(team);
    tb_view(&x, team);
    for (u32 p = 0; p < TN_POSITIONS; p++) score[p] = tb_score(&x, team, p, best[p], room, &target[p]);
    return tb_select(team, target, score, wishes);
}

/* 0x324414 jumps here (the draft AI's frame: best[17] at [esp+0x20], the wish count at [esp+0x10], team in ESI). */
__attribute__((section(".tb_p"), used, naked)) void tb_wish_entry(void) {
    __asm__("lea 0x20(%esp), %edx\n\tmov %esi, %ecx\n\tpush %ebx\n\tcall tb_wishes\n\t"
            "mov %eax, %ebx\n\tmov %eax, 0x10(%esp)\n\tjmp 0x324545\n");
}

/* decline_after_years_pro of data/nfl2k5_franchise_economy.json; nfl2k5_draft_ai.VALUE x 100 (tests pin both). */
__attribute__((section(".tb_q"), used)) const u8 tb_decline_after[TN_POSITIONS] = TB_DECLINE_AFTER;
__attribute__((section(".tb_q"), used)) const u8 tb_value[TN_POSITIONS] = TB_VALUE;
