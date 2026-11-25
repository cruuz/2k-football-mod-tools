/* Shared team-need definitions for computer clubs (beta 81): one rule for the CPU trades at every position
   (tools/cpu_trades), the season validator (tools/franchise_invariants.py), the trades lane's season observer and the
   team-building lane's draft and free-agency need. Coordinator ruling N1 on the trades lane's design review.
   Declarations, tables and small static functions only (freestanding i386 C; no writable data). The Python mirror is
   mod_editor/core/nfl2k5_team_need.py; tests/mod_editor/test_b81_team_need.py fails if the two tables differ.

   Positions (player + 0x35): QB 0, K 1, P 2, WR 3, CB 4, FS 5, SS 6, HB 7, FB 8, TE 9, OLB 10, ILB 11, C 12, G 13, T 14,
   DT 15, DE 16. The product's pools (nfl2k5_position_pools): no OLB (code 10 is an alias that no roster carries; every
   off-ball linebacker is at 11, "LB"), every edge rusher at 16 ("EDGE"), every interior lineman at 15 ("DT"). A code 10
   man, if one ever appears, belongs to the LB pool (TN_POOL).

   Starters are the seats each club actually uses, read from its depth chart: the first TN_SEATS[pool] PRESENT men of
   the pool in depth-row order (+0x28 bits 10..12; row 7 is the shared overflow). Present = no status bits and out 2
   weeks or less (+0x20 bits 22..29); a man out 3 weeks or more, or on IR (off the active list), is not a starter, and
   the next man in row order takes his seat. Measured against the simulator's own seats (the team-building lane's
   rows-vs-seats.txt, week 18; the trades lane's header_vs_seats.txt, season seat starters): depth rows 0 and 1 name
   seated men in 81 to 97 percent of CPU club-seasons at week 18 (row 0: 88 to 96 percent of season seat starters), the
   full row set only 64 to 93 percent (the third and fourth seats at WR, CB and LB move
   with injuries and the side chain). So two tables:
   - TN_NEED_SEATS: the seats a NEED is judged on (rows 0 and 1 at the multi-seat pools): the weakest present man of
     them against the league.
   - TN_SEATS: every seat a club uses (WR 3, CB 3, LB 4, T 2, G 2, DT 2, EDGE 2, others 1): a man in one of these is
     a starter, never surplus, and a seller keeps all of them present after a sale.

   Rating: 0x246D80(p, 0) (the native sort rating; flag 0 does not discount injuries, presence is judged separately)
   in whole points 0..100 (tn_points, the quarterback room's conversion).
   League scale of a pool: the ratings of every club's TN_NEED_SEATS present starters (32 x seats values), sorted;
   a man's percentile is the share of that list rated strictly below him, in 256ths (tn_percentile).
   Development asset (S4): 3 or fewer years pro and rated above the pool's median starter: never surplus. */
#ifndef TEAM_NEED_H
#define TEAM_NEED_H

#define TN_POSITIONS 17u
#define TN_LB 11u
#define TN_FB 8u
#define TN_PRESENT_WEEKS 2u             /* out this many weeks or fewer still counts as present */
#define TN_YOUNG_YEARS 3u               /* years pro 1..3: a development asset when above the pool median */
#define TN_SCALE 256u                   /* percentiles in 256ths */

/* Pool of a position code: OLB (10) counts as LB (11); every other code is its own pool. */
static const unsigned char TN_POOL[17] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 11, 12, 13, 14, 15, 16};
/* Seats a club uses per pool (starters): QB K P WR CB FS SS HB FB TE OLB LB C G T DT EDGE. */
static const unsigned char TN_SEATS[17] = {1, 1, 1, 3, 3, 1, 1, 1, 1, 1, 0, 4, 1, 2, 2, 2, 2};
/* Seats a need is judged on (rows 0 and 1 at most): the weakest present man of them. FB, K and P never make a need
   here (a club may carry no fullback: the economy's cut minimum is 0); QB is the quarterback system's. */
static const unsigned char TN_NEED_SEATS[17] = {1, 0, 0, 2, 2, 1, 1, 1, 0, 1, 0, 2, 1, 2, 2, 2, 2};
/* Premium pools (the owner's list for holes and star protection): QB, WR, CB, T, DT, EDGE. */
static const unsigned char TN_PREMIUM[17] = {1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1};
/* The economy's cut minimum per position (tools/franchise_economy cut_rows row 2 in the one-pool scheme: LB 5). */
static const unsigned char TN_CUT_MIN[17] = {2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4};

/* Present: no status bits (+0x24 bits 28..30) and out TN_PRESENT_WEEKS or fewer. */
static inline unsigned tn_present(const unsigned char *p) {
    unsigned medical = *(const unsigned *)(p + 0x20), contract = *(const unsigned *)(p + 0x24);
    return !(contract & 0x70000000u) && (medical >> 22 & 255u) <= TN_PRESENT_WEEKS;
}

/* Fully healthy (the trade rule for the man who moves): no injury bit, no weeks out, no status bits. */
static inline unsigned tn_healthy(const unsigned char *p) {
    return !(*(const unsigned *)(p + 0x20) & 0xBFC00000u) && !(*(const unsigned *)(p + 0x24) & 0x70000000u);
}

static inline unsigned tn_row(const unsigned char *p) {
    return *(const unsigned short *)(p + 0x28) >> 10 & 7u;
}

/* The float 0x246D80 returns, as whole points 0..100 (rounded; the quarterback room's overall()). */
static inline unsigned tn_points(unsigned bits) {
    unsigned e = bits >> 23 & 255u, s;
    if (bits >> 31 || e < 119) return 0;
    if (e > 127) return 100;
    s = 150 - e;
    return (((bits & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s;
}

/* Share of a sorted scale (n values, ascending) rated strictly below r, in 256ths. */
static inline unsigned tn_percentile(const unsigned char *scale, unsigned n, unsigned r) {
    unsigned below = 0;
    while (below < n && scale[below] < r) below++;
    return n ? below * TN_SCALE / n : 0;
}

#endif
