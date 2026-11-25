/* b81 team building (lane team-building; coordinator rulings 1-11 of 2026-11-25, the review fixes of the same day): CPU
 * clubs draft and sign to their weakest starters, judged by the shared team-need rule (tools/common/team_need.h, the
 * trades lane's header).
 *
 * Two entries, both reached only from draft-AI sites that the owner nfl2k5_team_building retargets:
 *   tb_order   the draft pick head's need call (draft_ai _prefix_bytes, `call 0x31DEA0` at 0x31E121): same ABI as
 *              FUN_0031DEA0 (fastcall ecx = team, edx = round, [esp] = pick, [esp+4] = int need[17]; ret 8). It runs
 *              the retail need first, then, for a club the CPU runs, moves the club's HOLES to the front: positions
 *              whose weakest need-seat starter rates in the league's bottom quarter (percentile < 64/256), read one
 *              season ahead with the economy's aging line (decline_after: 1 point a year past it, at most 4), premium
 *              positions weighted 3:2, ordered by that key; then every other position in the retail order. The club's
 *              seats are read as the next depth sort will set them (an unseated man 3 points better takes a seat). A
 *              position where the club already took a man in this draft (one year pro on its roster), or, in rounds
 *              1 and 2, holds an unseated development asset (header TN_YOUNG_YEARS or fewer years pro and above the
 *              pool's median starter), is not a hole. QB is in (ruling 3). FB, K and P have no need seats; OLB is LB's
 *              alias, or, when some rostered man carries OLB (the two-pool scheme), keyed with the LB pool.
 *   tb_wish_entry   the free-agent wish body's jump (draft_ai body_patch at 0x324414): for a club a person runs it goes
 *              on to the draft AI's own cave (0x10B40), unchanged. Otherwise it replaces the draft-AI scored selection.
 *              QB, K, P and FB keep the draft AI's own score (ruling 3: quarterback signings stay with the quarterback
 *              system's rules); one of them short of its roster minimum ranks with the count deficits, a K or P the
 *              club has none of above the holes. Every other position: the best present free agent the club can pay
 *              there (his economy_value ask within economy_room_for_signing, the economy's affordability routine: cap
 *              room less 10), wished for when he is 3 points better than the club's weakest need-seat starter; a hole
 *              scores first (100000 + its depth, premium 3:2), a count deficit next (50000 + 1200 a man), an upgrade
 *              last (points gained x VALUE + 0..6 points of jitter); no wish otherwise. Then the draft AI's
 *              selection, the best four above 0 through 0x324180, with one wish a position pool.
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
    u8 weak[TN_POSITIONS];       /* this club: weakest need-seat man's points after the bench check (0: a seat empty) */
    u8 wpro[TN_POSITIONS];       /* his years pro */
    u8 young[TN_POSITIONS];      /* best points of an unseated present man with 1..TN_YOUNG_YEARS years pro */
    u8 drafted[TN_POSITIONS];    /* a man with exactly one year pro (taken in this draft) */
    u8 n[TN_POSITIONS];          /* league scale sizes */
    u8 scale[TN_POSITIONS][SCALE_MAX];
    u8 olb;                      /* some rostered man carries OLB (10): the two-pool scheme (review S6) */
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

/* One club: its first two present men of each pool in row order; men[pool * 2 + k]. Nonzero when one of its men
   carries OLB (10), the economy's league_has_olb test: then OLB is a position of its own, not the alias. */
SECTION(".tb_b") u32 tb_seats(u8 *team, u8 **men) {
    u32 n = team[0x11C], olb = 0;
    tb_zero(men, TN_POSITIONS * 2 * sizeof *men);
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        olb |= o[0x35] == 10;
        if (o[0x35] < TN_POSITIONS && tn_present(o)) tb_seat(men + 2 * TN_POOL[o[0x35]], o);
    }
    return olb;
}

/* Is o in one of a pool's `seats` need seats (m = men + 2 * pool)? */
SECTION(".tb_ss") u32 tb_seated(u8 **m, u32 seats, u8 *o) {
    for (u32 k = 0; k < seats; k++)
        if (m[k] == o) return 1;
    return 0;
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
   1fbb90087). */
SECTION(".tb_r") void tb_pool(struct view *x, u8 **m, u32 pool) {
    for (u32 k = 0; k < TN_NEED_SEATS[pool]; k++) tb_insert(x->scale[pool], &x->n[pool], m[k] ? tb_points(m[k]) : 0);
}

/* One pool of the own club: its weakest need-seat man's points and years pro. */
SECTION(".tb_rw") void tb_weak(struct view *x, u8 **m, u32 pool) {
    u32 seats = TN_NEED_SEATS[pool], weak = 255, wpro = 0;
    for (u32 k = 0; k < seats; k++) {
        u32 r = m[k] ? tb_points(m[k]) : 0;
        if (r < weak) weak = r, wpro = m[k] ? m[k][0x25] & 31 : 0;
    }
    if (seats) x->weak[pool] = (u8)weak, x->wpro[pool] = (u8)wpro;
}

/* The own club's need seats as the next depth sort will set them (review S1): an unseated present man rated MARGIN or
   more above a seat's man (the weakest seat first) takes it, in roster order. A CPU signing appends the man without
   sorting the depth chart (0x323D80), so a newcomer keeps his old club's row until the weekly sort; without this a
   hole just filled in free agency still reads as a hole and the club bids there again. */
SECTION(".tb_bm") void tb_bench_man(u8 **m, u32 seats, u8 *o) {
    u32 w = 0, low = 256;
    if (!seats || tb_seated(m, seats, o)) return;
    for (u32 k = 0; k < seats; k++) {
        u32 r = m[k] ? tb_points(m[k]) : 0;
        if (r < low) low = r, w = k;
    }
    if (tb_points(o) >= low + MARGIN) m[w] = o;
}

SECTION(".tb_bb") void tb_bench(u8 *team, u8 **men) {
    u32 n = team[0x11C];
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        u32 pos = o[0x35];
        if (pos < TN_POSITIONS && tn_present(o)) tb_bench_man(men + 2 * TN_POOL[pos], TN_NEED_SEATS[TN_POOL[pos]], o);
    }
}

/* Development assets (unseated: review S3, the club's own need-seat man is not one) and this draft's picks of the own
   club. */
SECTION(".tb_ea") void tb_asset_man(u8 *young, u8 **m, u32 seats, u8 *o) {
    u32 r;
    if (tn_present(o) && !tb_seated(m, seats, o) && (r = tb_points(o)) > *young) *young = (u8)r;
}

SECTION(".tb_e") void tb_young(struct view *x, u8 *team, u8 **men) {
    u32 n = team[0x11C];
    for (u32 j = 0; j < n; j++) {
        u8 *o = ((u8 **)team)[j];
        u32 pos = o[0x35], pro = o[0x25] & 31, pool;
        if (pos >= TN_POSITIONS || !pro || pro > TN_YOUNG_YEARS) continue;
        pool = TN_POOL[pos];
        if (pro == 1) x->drafted[pool] = 1;
        tb_asset_man(&x->young[pool], men + 2 * pool, TN_NEED_SEATS[pool], o);
    }
}

/* The own club: the bench check, its development assets and its weakest need-seat men. */
SECTION(".tb_do") void tb_own(struct view *x, u8 *team, u8 **men) {
    tb_bench(team, men);
    tb_young(x, team, men);
    for (u32 pool = 0; pool < TN_POSITIONS; pool++) tb_weak(x, men + 2 * pool, pool);
}

/* One club into the league scales (its depth-row need seats, the header's rule); the own club also through tb_own. */
SECTION(".tb_d") void tb_club(struct view *x, u8 *team, u32 own) {
    u8 *men[TN_POSITIONS * 2];
    x->olb |= (u8)tb_seats(team, men);
    for (u32 pool = 0; pool < TN_POSITIONS; pool++) tb_pool(x, men + 2 * pool, pool);
    if (own) tb_own(x, team, men);
}

/* The league and the club `team`. */
SECTION(".tb_f") void tb_view(struct view *x, u8 *team) {
    u32 clubs = n_teams();
    tb_zero(x, sizeof *x);
    for (u32 i = 0; i < clubs; i++) {
        u8 *t = n_team(i);
        if (t) tb_club(x, t, t == team);
    }
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
    for (u32 p = 0; p < TN_POSITIONS; p++)                    /* OLB: LB's alias, or its own position (S6) */
        key[p] = (u8)(p == 10 && !x.olb ? NONE : tb_key(&x, TN_POOL[p], round));
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

/* A kept position (QB, K, P, FB: the draft AI's own score, ruling 3). Whether it wishes is the draft AI's decision;
   a wish short of the roster minimum ranks with the count deficits, a K or P the club has none of above the holes
   (review S2: four hole bids must not crowd out an empty specialist slot); the draft AI's score orders within. */
SECTION(".tb_kk") i32 FAST tb_kept(u8 *team, u32 pos, u8 *best) {
    i32 s = tb_old_score(team, pos, best), d = tb_deficit(team, pos);
    if (s <= 0 || d <= 0) return s;
    return s / 16 + (pos - 1u < 2u && !n_at_position(team, pos) ? 200000 : 50000 + 1200 * d);
}

/* Weakness first (x 100) at a position with need seats. */
SECTION(".tb_l") i32 FAST tb_new_score(struct view *x, u8 *team, u32 pos, u32 cand) {
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
        if (tb_wish(target[best], team)) {
            wishes++;
            if (TN_POOL[best] == TN_LB) target[10] = target[TN_LB] = 0;   /* one wish a pool (OLB, LB: two-pool) */
        }
        target[best] = 0;
    }
    return wishes;
}

/* A need-seat position's wish: the best affordable man who would start; failing him, at a count deficit the best
   affordable man (review N5); failing that the draft AI's best (the offer gate then decides). */
SECTION(".tb_ta") i32 FAST tb_seek(struct view *x, u8 *team, u32 p, u8 *best, i32 room, u8 **target) {
    u32 cand, any;
    u8 *t = tb_candidate(p, room, &cand, x->weak[TN_POOL[p]] + MARGIN - 1);
    if (!t && tb_deficit(team, p) > 0) t = tb_candidate(p, room, &any, 0);
    *target = t ? t : best;
    return tb_new_score(x, team, p, cand);
}

/* One position's wish target and score (x 100; 0 or less: no wish). QB (0) and the positions without need seats (K,
   P, FB) are kept (tb_kept). */
SECTION(".tb_t") i32 tb_score(struct view *x, u8 *team, u32 p, u8 *best, i32 room, u8 **target) {
    *target = 0;
    if (!best || n_at_position(team, p) >= n_maximum_at(p)) return 0;
    *target = best;
    if (!TN_NEED_SEATS[TN_POOL[p]] || p == 0) return tb_kept(team, p, best);
    return tb_seek(x, team, p, best, room, target);
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

/* 0x324414 jumps here (the draft AI's frame: best[17] at [esp+0x20], the wish count at [esp+0x10], team in ESI). A
   club a person runs (wishes reach it when "CPU signs and cuts for me" is on, 0xE6013C) goes on to the draft AI's own
   cave at 0x10B40, exactly where the draft AI alone sends it: the Studio's promise "Your own club is never changed"
   (review M3). n_human keeps ESI, EBX and the frame; the cave reads nothing else at entry. */
__attribute__((section(".tb_p"), used, naked)) void tb_wish_entry(void) {
    __asm__("mov %esi, %ecx\n\tcall n_human\n\ttest %eax, %eax\n\tjnz 0x10B40\n\t"
            "lea 0x20(%esp), %edx\n\tmov %esi, %ecx\n\tpush %ebx\n\tcall tb_wishes\n\t"
            "mov %eax, %ebx\n\tmov %eax, 0x10(%esp)\n\tjmp 0x324545\n");
}

/* decline_after_years_pro of data/nfl2k5_franchise_economy.json; nfl2k5_draft_ai.VALUE x 100 (tests pin both). */
__attribute__((section(".tb_q"), used)) const u8 tb_decline_after[TN_POSITIONS] = TB_DECLINE_AFTER;
__attribute__((section(".tb_q"), used)) const u8 tb_value[TN_POSITIONS] = TB_VALUE;
