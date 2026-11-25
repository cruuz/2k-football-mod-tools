/* CPU trades at every position (beta 81, owner nfl2k5_cpu_trades; the trades-all lane's design with the coordinator's
   rulings R1 to R7 and the design-review rulings M1-M3, S1-S10, N1-N8). Two fixed pages at 0x152E000
   (nfl2k5_xbe_space.CPU_TRADES_*). The need rule is the shared header tools/common/team_need.h.

   When: inside the native trade pass 0x2BC960, at its pending scan (entry.S trade_entry, site 0x2BC96C): this code posts
   its records, calls the pending scan 0x2BC900 (which executes or refuses every kind-2 record between CPU clubs through
   the native executor 0x2BC670), repairs the depth rows of both clubs of every executed trade at the traded pool (S9)
   and cancels every record of its own still on the board. When the board ran out of slots it runs once more (S8: at
   most two rounds a tick). A record of ours exists only during the native call: never at a save point. The quarterback
   trades of stage 4b (nfl2k5_qb_trades) post before 0x2BC960; this code never offers or buys a QB, K or P.
   A second entry (entry.S story_entry, site 0x2BB296 in the trade story writer 0x2BB200) posts the inbox story of every
   executed trade of ours whatever its asset value (S7); for any other trade it is the native `cmp eax, 1000`.

   Settings (page + 0x1C00, CPUTRDv1): stage bits 1 = the regular season (stage 8, only while the week counter is below
   the deadline byte 0x5151C5 whatever the Trade Deadline option says; R5), 2 = the preseason (stage 7, from the second
   franchise season: S10), 4 = losing clubs may sell veterans past their prime in season (R3, S2); flags bit 0 = shadow
   (everything is computed, counted and logged; nothing is written: no release, no record, no row); p8_ppm and p7_ppm
   = the posting chance per package in millionths (stage 8: times the week weight, halved; both times the pool weight).

   One round (post):
   - League scale per pool (header): every club's need-seat starters (32 x TN_NEED_SEATS values; an empty seat rates
     0), sorted; a club's need percentile at a pool is the mid-rank of its weakest need-seat starter there
     (tn_percentile); q25/q50/q75/q90 = the scale's values at n/4, n/2, 3n/4, 9n/10.
   - Buyer: no person manages it (0xE5775C), no pending offer names it (a native listing does not), fewer than 3 trade
     groups in the native ledger (R4), 2+ healthy quarterbacks, fewer than 3 of its own picks of the coming draft gone
     (S3), in stage 8 still in the race (W + 1 >= L). Its needs: up to three pools in its bottom quarter (percentile
     below 64/256), lowest first (S1); in stage 7 also a pool with no present backup (a depth deal, S10).
   - Package for a need: the best man over every seller: fully healthy, no status bits, 2+ years pro, 1+ contract
     years; in stage 7 not in the first year of his contract (from year index 1; N2: in stage 8 the ledger's signing
     rows say "just signed"); not star-tagged (+0x53 bit 0, MyCareer's man too); not on the board; not in a signing or
     trade row of the ledger; not his club's best player, not its best man at a premium pool, not at or above q90, not
     a development asset (S2, S4); not one of the seller's seated starters (header TN_SEATS) unless the seller is losing
     (bit 4) and he has 8+ years pro (R3, S2); the seller keeps its seats filled and its cut minimum; rated at least
     the buyer's weakest need-seat starter + 3 and q25 (a stage 7 depth need: q25 - 8). Cap (M1): the buyer's cap room
     after the trade, with the contract the executor writes (0x2BB360: the owed bonus folded into the value), stays at or
     above two minimum salaries (the economy's line, economy_vet_short).
   - Room (M3): a buyer at 53 in season (65 in the preseason) first releases one man by the economy's smart cut rule: a
     pool above its maximum, else above its keep target, else above its cut minimum (counting the man it buys); small
     deals first, then the lowest rating; never a QB, K or P, a seated starter or a man who just joined. Nobody: none.
   - Price: its own pick of the coming draft (year 0), round by the man's place on the pool's scale: q75+ a 3rd, q50+ a
     4th, q25+ a 5th, else a 6th; one round later with 9+ years pro, with one contract year left, and in the preseason;
     never past the 7th; not owned: one round earlier but never a 1st (N3); else no trade.
   - Draw (stateless, reload-stable): hash(9, buyer, pool, year, stage, week, man, W, L) % 1000000 below the chance;
     the first kind-0 slot of 1 to 14; the native evaluator 0x2BAE90 accepts the record (after the release); kind
     written last; at most MAX_POSTS records (or would-be records, in shadow) a round; one record per club.

   Ring rows (page + 0x1D00, 48 x 16 bytes, cursor + 0x1CE0): struct event; a package the draw keeps is only counted.
   Results before the pending scan: 1 posted, 2 would post (shadow), 3 no pick, 4 refused by the evaluator, 5 no slot, 6 per-round cap,
   8 nobody to release; rows after it (flag F_AFTER): 1 executed, 7 refused by the executor and cancelled here, 0 gone. */
#include "../common/team_need.h"

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define B(a) (*(volatile u8 *)(a))
#define W(a) (*(volatile u16 *)(a))
#define D(a) (*(volatile u32 *)(a))

#define CLUB_AT ((u32 (FC *)(u32))0x000C4C50)
#define WINS ((u32 (FC *)(u32))0x000C7720)
#define LOSSES ((u32 (FC *)(u32))0x000C7750)
#define TIES ((u32 (FC *)(u32))0x000C7780)
#define RATING ((float (FC *)(u32, u32))0x00246D80)
#define SALARY ((u32 (FC *)(u32))0x000E6380)            /* this season's base charge (fastcall ECX) */
#define TO_MONEY ((u32 (FC *)(u32))0x000E5FF0)          /* contract value (u16) -> money, as 0x2BB360 */
#define OWED ((u32 (FC *)(u32))0x0013ED00)              /* the bonus still owed (ECX = player), as 0x2BB360 */
#define TO_VALUE ((u32 (FC *)(u32))0x000E6000)          /* money -> contract value, as 0x2BB360 */
#define CANCEL ((void (FC *)(u32, u32, u32, u32))0x002BB660)   /* (offer, new kind, clear A, clear B), ret 8 */
#define RELEASE ((void (FC *)(u32, u32, u32, u32))0x002BD900)  /* (club, player, to the list, log), ret 8 */
#define PENDING ((void (__attribute__((stdcall)) *)(u32))0x002BC900)   /* the pending scan (menu), ret 4 */

#define LEAGUE_ROOT 0x00B72918u
#define STAGE 0x00E576A4u
#define WEEK 0x00E576B4u
#define YEAR 0x00E576B8u
#define USER_FLAG 0x00E5775Cu
#define DEADLINE_WEEK 0x005151C5u
#define BOARD 0x00E3C27Cu
#define RECORD 0x3Cu
#define PICKS 0x00E3C094u
#define CAP 0x00E3C278u
#define LEDGER 0x00E3F070u
#define LEDGER_CURSOR 0x00E3F06Cu
#define LEDGER_ROWS 600u
#define CLUBS 32u
#define SLOTS 65u
#define TEAM_SIZE 500u
#define PLAYER_SIZE 0x54u
#define RANK_LOCK 1u                                     /* player + 0x52 bit 0 */

#define ST_SEASON 1u
#define ST_PRESEASON 2u
#define ST_REBUILD 4u
#define FLAG_SHADOW 1u
#define MAX_POSTS 6u
#define LOAD_LIMIT 3u
#define PICKS_PAID_LIMIT 3u                              /* S3 */
#define RING_EVENTS 48u
#define QUARTER 64u                                      /* 0.25 in 256ths */
#define REBUILD_YEARS 8u                                 /* R3, S2: past his prime */
#define DECISION 9u
#define SMALL_DEAL 60u                                   /* contract value per year (nfl2k5_roster_refresh) */

#define KEPT 0u
#define POSTED 1u
#define WOULD 2u
#define NO_PICK 3u
#define REFUSED 4u
#define NO_SLOT 5u
#define CAPPED 6u
#define CANCELLED 7u
#define NO_RELEASE 8u
#define F_REBUILD 1u
#define F_RELEASE 2u
#define F_DEPTH 4u
#define F_ROUND2 8u
#define F_AFTER 0x40u

struct settings {
    u32 magic[2];
    u32 mode, stages, flags, p8_ppm, p7_ppm, reserved;
};

/* COUNTERS BEGIN (build.py reads these names in order; page + 0x1C20, u32 each, at most 48) */
struct counters {
    u32 calls;                   /* every entry at the pending scan, whatever the settings */
    u32 bad_settings;            /* magic or mode not CPUTRDv1 / 1: nothing posted */
    u32 inactive;                /* settings fine but this stage (or its bit) does not post */
    u32 past_deadline;           /* stage 8 at or past the deadline byte: nothing posted */
    u32 opening_preseason;       /* stage 7 of the first franchise season (S10): nothing posted */
    u32 rounds;                  /* rounds that looked for trades (at most two a tick) */
    u32 buyers;                  /* clubs that may buy, per round */
    u32 out_load;                /* clubs out: three trade groups in the ledger */
    u32 out_race;                /* buyers out: W + 1 < L (stage 8) */
    u32 out_picks;               /* buyers out: three own picks of the coming draft already paid (S3) */
    u32 out_quarterbacks;        /* buyers out: fewer than two healthy quarterbacks */
    u32 no_need;                 /* buyers with no pool in their bottom quarter (or thin, stage 7) */
    u32 no_package;              /* needs tried, no seller offers a man who fits */
    u32 rej_health;              /* candidate men refused: not fully healthy, rookie, no contract years */
    u32 rej_contract;            /* first contract year (stage 7, from year index 1) */
    u32 rej_protected;           /* star tag, club's best, best at a premium pool, q90, development asset */
    u32 rej_starter;             /* a seated starter of the seller (and not a rebuild sale) */
    u32 rej_depth;               /* the seller would lose a seat or its cut minimum */
    u32 rej_floor;               /* not good enough for the buyer */
    u32 rej_cap;                 /* the buyer's cap after the trade (M1) */
    u32 rej_ledger;              /* on the board, or just signed or traded (ledger) */
    u32 rebuild_packages;        /* packages from a losing seller's veteran starter (bit 4) */
    u32 depth_packages;          /* stage 7 depth deals */
    u32 no_release;              /* a buyer at the limit with nobody it may release */
    u32 releases;                /* make-room releases made (M3) */
    u32 no_pick;
    u32 kept;
    u32 capped;
    u32 refused;
    u32 no_slot;
    u32 shadow;
    u32 posted;
    u32 executed;
    u32 cancelled;
    u32 gone;
    u32 events_logged;
    u32 second_rounds;           /* S8: rounds run again because the board was full */
    u32 rows_repaired;           /* S9: clubs whose rows at the traded pool were repaired after a trade */
    u32 stories_forced;          /* S7: our trades whose inbox story the gate let through, whatever their value */
};
/* COUNTERS END */

struct event {                   /* 16 bytes */
    u16 year;
    u8 stage, week, buyer, seller, position, result;
    u16 player, word;
    u8 rating, pct, q25, flags;
} __attribute__((packed));

extern volatile struct settings ct_settings;          /* page + 0x1C00 */
extern volatile struct counters ct_counters;          /* page + 0x1C20 */
extern volatile u32 ct_ring_cursor;                   /* page + 0x1CE0 */
extern volatile u32 ct_current[MAX_POSTS];            /* page + 0x1CE4: our records during the pending scan (S7) */
extern volatile u32 ct_round_mask;                    /* page + 0x1CFC: clubs in a record of ours or a trade this call (S8) */
extern volatile struct event ct_ring[RING_EVENTS];    /* page + 0x1D00 */

/* The economy's smart cut tiers per position (cut_max, cut_keep; cut_min is the header's; one-pool LB). */
static const u8 CUT_MAX[TN_POSITIONS] = {3, 30, 30, 30, 30, 30, 30, 30, 2, 30, 0, 30, 30, 30, 30, 30, 30};
static const u8 CUT_KEEP[TN_POSITIONS] = {2, 30, 30, 6, 6, 2, 2, 3, 1, 3, 0, 5, 2, 3, 4, 4, 4};
/* Stage 8 week weights (stored week 0..8), halved when used: the real deadline rush. */
static const u8 WEEK_WEIGHT[9] = {1, 1, 1, 1, 2, 2, 2, 4, 8};
/* Pool weights in 16ths (S1: hold the position mix to the real one), regular season and preseason. */
static const u8 POOL_WEIGHT[2][TN_POSITIONS] = {
    {0, 0, 0, 16, 16, 16, 16, 16, 0, 10, 0, 16, 5, 5, 5, 16, 16},    /* season: OL about 7 percent, TE 4 */
    {0, 0, 0, 12, 16, 16, 16, 4, 0, 8, 0, 14, 12, 12, 12, 10, 10},   /* preseason: DB, OL, LB first; RB rare */
};

struct club {
    u32 team;
    u8 flags, load, active, best;
    u8 w, l, t, paid;
    u8 qbs, pad[3];
    u8 weak[TN_POSITIONS];       /* weakest need-seat starter's rating (0: a seat empty) */
    u8 other[TN_POSITIONS];      /* the other need-seat starter's rating at a two-seat pool (0: empty) */
    u8 pct[TN_POSITIONS];        /* its percentile on the league scale, 256ths */
    u8 present[TN_POSITIONS];    /* present men at the pool */
};
#define OUT 1u
#define BUYER 2u
#define SELLER 4u
#define REBUILD 8u
#define USED 16u

struct posted { u32 rec, qs, buyer, seller, word, pool; };

static u32 rating(u32 p) {
    union { float f; u32 u; } v;
    v.f = RATING(p, 0);
    return tn_points(v.u);
}

static u32 index_of(u32 p) {
    return p ? (p - D(D(LEAGUE_ROOT) + 4)) / PLAYER_SIZE : 0xFFFFu;
}

static u32 pool_of(u32 p) {
    u32 pos = B(p + 0x35);
    return pos < TN_POSITIONS ? TN_POOL[pos] : 0xFFu;
}

static u32 row_of(u32 p) {
    return tn_row((const u8 *)p);
}

/* Does a live record (kind != 0, slots 0 to 14) name player p (either side)? */
static u32 named(u32 p) {
    for (u32 rec = BOARD; rec < BOARD + 15 * RECORD; rec += RECORD)
        for (u32 o = 0xC; D(rec) && o < 0x30; o += 4)
            if ((o < 0x18 || o >= 0x24) && D(rec + o) == p) return 1;
    return 0;
}

/* Does a pending offer (kind 2 and above; a native listing is kind 1) name club t on either side? */
static u32 named_club(u32 t) {
    for (u32 rec = BOARD; rec < BOARD + 15 * RECORD; rec += RECORD)
        if (D(rec) > 1 && (D(rec + 8) == t || D(rec + 0x20) == t)) return 1;
    return 0;
}

static u32 listed(u32 team, u32 p) {
    for (u32 i = 0; i < B(team + 0x11C) && i < SLOTS; i++)
        if (D(team + 4 * i) == p) return 1;
    return 0;
}

/* A signing (kind 1) or trade (kind 7) row of the native ledger names p. */
static u32 in_ledger(u32 p) {
    for (u32 at = LEDGER; at < LEDGER + 12 * LEDGER_ROWS; at += 12) {
        u32 kind = D(at) & 31;
        if ((kind == 1 || kind == 7) && D(at + 4) == p) return 1;
    }
    return 0;
}

static u32 fmix(u32 h) {
    h ^= h >> 16; h *= 0x85EBCA6Bu; h ^= h >> 13; h *= 0xC2B2AE35u; h ^= h >> 16;
    return h;
}

static void row(u32 stage, u32 buyer, u32 seller, u32 pool, u32 result, u32 qs, u32 word, u32 rating10, u32 pct,
                u32 q25, u32 flags) {
    u32 n = ct_ring_cursor;
    volatile struct event *e = &ct_ring[n % RING_EVENTS];
    e->year = (u16)D(YEAR);
    e->stage = (u8)stage;
    e->week = (u8)D(WEEK);
    e->buyer = (u8)buyer;
    e->seller = (u8)seller;
    e->position = (u8)pool;
    e->result = (u8)result;
    e->player = (u16)index_of(qs);
    e->word = (u16)word;
    e->rating = (u8)rating10;
    e->pct = (u8)pct;
    e->q25 = (u8)q25;
    e->flags = (u8)flags;
    ct_ring_cursor = n + 1;
    ct_counters.events_logged++;
}

/* The native evaluator 0x2BAE90 (EAX = offer; stack: value A out, value B out, message 0; ret 0xC). Reads only. */
static u32 evaluate(u32 *offer) {
    u32 out[2], ok;
    __asm__ volatile("pushl $0\n\tpushl %2\n\tpushl %1\n\tmovl $0x2BAE90, %%ecx\n\tcall *%%ecx"
                     : "=a"(ok) : "r"(&out[0]), "r"(&out[1]), "a"(offer) : "ecx", "edx", "memory", "cc");
    return ok;
}

/* M1: the charge the buyer carries after the trade. The executor's 0x2BB360 folds the bonus still owed into the
   contract value and clears the bonus field; the charge is 0xE6380 on the record so rewritten. Computed on a copy. */
static u32 charge_after(u32 p) {
    u32 copy[PLAYER_SIZE / 4];
    for (u32 i = 0; i < PLAYER_SIZE / 4; i++) copy[i] = D(p + 4 * i);
    u32 money = TO_MONEY(W(p + 0xA)) - OWED(p);
    copy[0x24 / 4] &= 0xFF0FFFFFu;
    ((volatile u16 *)copy)[0xA / 2] = (u16)TO_VALUE(money);
    return SALARY((u32)copy);
}

/* Two league-minimum salaries of the season (the economy's line, economy_vet_short: (885 + 45 x min(year, 4) + 3) / 4
   each, the minimum for no years of service in data/nfl2k5_franchise_economy.json). */
static i32 cap_margin(void) {
    u32 year = D(YEAR) < 4 ? D(YEAR) : 4;
    return (i32)(2 * ((885 + 45 * year + 3) / 4));
}

/* Trade groups of the native ledger per club (each club named by an outgoing row of a group counts it once). */
static void ledger_load(struct club *c, u32 base) {
    u32 cursor = D(LEDGER_CURSOR), mask = 0;
    if (cursor >= LEDGER_ROWS) return;
    for (u32 k = 0; k < LEDGER_ROWS; k++) {
        u32 at = LEDGER + 12 * ((cursor + k) % LEDGER_ROWS), word = D(at), team = D(at + 8);
        if ((word & 31) != 7) {
            mask = 0;
            continue;
        }
        if (team >= base && (team - base) % TEAM_SIZE == 0 && (team - base) / TEAM_SIZE < CLUBS)
            mask |= 1u << ((team - base) / TEAM_SIZE);
        if (word & 0x80000000u) {
            for (u32 i = 0; i < CLUBS; i++)
                if (mask >> i & 1 && c[i].load < 255) c[i].load++;
            mask = 0;
        }
    }
}

/* Is p one of his club's seated starters: among the first TN_SEATS present men of his pool in row order (ties: the
   club's list order)? */
static u32 seated(u32 team, u32 p) {
    u32 pool = pool_of(p), before = 0, r = row_of(p), n = B(team + 0x11C), mine = SLOTS;
    if (pool == 0xFFu || !tn_present((const u8 *)p)) return 0;
    for (u32 j = 0; j < n && j < SLOTS; j++)
        if (D(team + 4 * j) == p) mine = j;
    for (u32 j = 0; j < n && j < SLOTS; j++) {
        u32 o = D(team + 4 * j), ro;
        if (!o || o == p || pool_of(o) != pool || !tn_present((const u8 *)o)) continue;
        ro = row_of(o);
        if (ro < r || (ro == r && j < mine)) before++;
    }
    return before < TN_SEATS[pool];
}

/* One club's roster: the weakest of its first TN_NEED_SEATS present men by row at each pool (0 if a seat is empty),
   present counts, its best player (any health) and its healthy quarterbacks. */
static void scan(struct club *x) {
    u8 rows[TN_POSITIONS][4], rate[TN_POSITIONS][4], n[TN_POSITIONS];
    x->best = x->qbs = 0;
    for (u32 p = 0; p < TN_POSITIONS; p++) n[p] = x->present[p] = 0;
    for (u32 j = 0; j < x->active; j++) {
        u32 o = D(x->team + 4 * j), pool, r, ro, k;
        if (!o || (pool = pool_of(o)) == 0xFFu) continue;
        r = rating(o);
        if (r > x->best) x->best = (u8)r;
        if (pool == 0 && tn_healthy((const u8 *)o)) x->qbs++;
        if (!tn_present((const u8 *)o)) continue;
        x->present[pool]++;
        ro = row_of(o);
        for (k = 0; k < n[pool] && rows[pool][k] <= ro; k++) {}
        if (k >= 4) continue;                                  /* keep the four lowest rows (ties: list order) */
        for (u32 m = (n[pool] < 4 ? n[pool] : 3); m > k; m--) {
            rows[pool][m] = rows[pool][m - 1];
            rate[pool][m] = rate[pool][m - 1];
        }
        rows[pool][k] = (u8)ro;
        rate[pool][k] = (u8)r;
        if (n[pool] < 4) n[pool]++;
    }
    for (u32 p = 0; p < TN_POSITIONS; p++) {
        u32 s0 = n[p] ? rate[p][0] : 0, s1 = n[p] > 1 ? rate[p][1] : 0;
        x->weak[p] = (u8)(TN_NEED_SEATS[p] > 1 && s1 < s0 ? s1 : s0);
        x->other[p] = (u8)(s1 < s0 ? s0 : s1);
    }
}

/* The man at pool `pool` the seller may sell (see the header comment); 0 if none. */
static u32 offer_of(struct club *s, u32 stage, u32 pool, u32 floor, u32 above, i32 room, const u8 *q, u32 *rebuild) {
    u32 t = s->team, count = 0, best = 0, best_r = above, top_at_pool = 0;
    for (u32 j = 0; j < s->active; j++) {
        u32 o = D(t + 4 * j), r;
        if (!o || pool_of(o) != pool) continue;
        count++;
        if ((r = rating(o)) > top_at_pool) top_at_pool = r;
    }
    if (count < (u32)TN_CUT_MIN[pool] + 1u || s->present[pool] < (u32)TN_SEATS[pool] + 1u) {
        ct_counters.rej_depth++;
        return 0;
    }
    for (u32 j = 0; j < s->active; j++) {
        u32 p = D(t + 4 * j), r, pro, left, sale_rebuild;
        if (!p || pool_of(p) != pool) continue;
        pro = B(p + 0x25) & 31;
        left = B(p + 0x24) & 15;
        if (!tn_healthy((const u8 *)p) || pro < 2 || !left) {
            ct_counters.rej_health++;
            continue;
        }
        if (stage == 7 && D(YEAR) && left == (B(p + 0x27) & 15u)) {
            ct_counters.rej_contract++;
            continue;
        }
        r = rating(p);
        if (B(p + 0x53) & 1 || r >= s->best || (TN_PREMIUM[pool] && r >= top_at_pool) || r >= q[3]
                || (pro <= TN_YOUNG_YEARS && r > q[1])) {
            ct_counters.rej_protected++;
            continue;
        }
        sale_rebuild = seated(t, p);
        if (sale_rebuild && (!(s->flags & REBUILD) || pro < REBUILD_YEARS)) {
            ct_counters.rej_starter++;
            continue;
        }
        if (r < floor || r <= best_r) {
            ct_counters.rej_floor++;
            continue;
        }
        if (room - (i32)charge_after(p) < cap_margin()) {
            ct_counters.rej_cap++;
            continue;
        }
        if (named(p) || in_ledger(p)) {
            ct_counters.rej_ledger++;
            continue;
        }
        best = p;
        best_r = r;
        *rebuild = sale_rebuild;
    }
    return best;
}

/* M3: the man a buyer at its limit releases (the economy's smart cut tiers, counting the man it buys at `pool`; small
   deals first, then the lowest rating 0x246D80(p, 1); never a QB, K or P, a seated starter or a man who just joined,
   never a man named on the board). 0: nobody. */
static u32 release_of(u32 team, u32 pool) {
    u32 n = B(team + 0x11C);
    for (u32 tier = 0; tier < 3; tier++) {
        u32 best = 0, best_small = 0;
        float low = 0;
        for (u32 j = 0; j < n && j < SLOTS; j++) {
            u32 p = D(team + 4 * j), at, count = 0, limit, small, length;
            float r;
            if (!p || (at = pool_of(p)) == 0xFFu || at <= 2) continue;
            for (u32 k = 0; k < n && k < SLOTS; k++) {
                u32 o = D(team + 4 * k);
                if (o && pool_of(o) == at) count++;
            }
            if (at == pool) count++;
            limit = tier == 0 ? CUT_MAX[at] : tier == 1 ? CUT_KEEP[at] : TN_CUT_MIN[at];
            if (count <= limit || seated(team, p) || named(p) || in_ledger(p)) continue;
            length = B(p + 0x27) & 15u;
            small = W(p + 0xA) <= SMALL_DEAL * (length ? length : 1u);
            r = RATING(p, 1);
            if (!best || (small && !best_small) || (small == best_small && r < low)) {
                best = p;
                best_small = small;
                low = r;
            }
        }
        if (best) return best;
    }
    return 0;
}

/* The price round (q75+ a 3rd, q50+ a 4th, q25+ a 5th, else a 6th; later for age, an expiring deal and the preseason). */
static u32 price(u32 p, u32 r, const u8 *q, u32 stage) {
    u32 round = r >= q[2] ? 3 : r >= q[1] ? 4 : r >= q[0] ? 5 : 6;
    if ((B(p + 0x25) & 31) >= 9) round++;
    if ((B(p + 0x24) & 15) == 1) round++;
    if (stage == 7) round++;
    return round > 7 ? 7 : round;
}

/* The buyer's own pick of the coming draft in this round, or the round before but never a 1st (N3). */
static u32 pick(u32 b, u32 ruled) {
    for (u32 round = ruled; round >= 2 && round + 1 >= ruled; round--)
        if (B(PICKS + 32 * round + b) == b) return round | b << 6;
    return 0;
}

/* S9: the native sort's row and side for a man (retail 0x2BDCF0: WR, CB, OLB, ILB, G, T, DT, DE carry a side:
   row 0 -> 0x4000, row 1 -> 0, row 2 -> 0x2000, row r >= 3 -> r << 13). */
static void set_row(u32 p, u32 r) {
    u32 pos = B(p + 0x35);
    u32 v = (W(p + 0x28) & ~0x1C00u) | (r > 7 ? 7 : r) << 10;
    if (pos == 3 || pos == 4 || pos == 10 || pos == 11 || pos == 13 || pos == 14 || pos == 15 || pos == 16)
        v = (v & 0x1FFFu) | (r == 0 ? 0x4000u : r == 1 ? 0 : r == 2 ? 0x2000u : (r > 7 ? 7 : r) << 13);
    W(p + 0x28) = (u16)v;
}

/* S9 after an executed trade, at the traded pool only (a league-wide re-sort would also undo the quarterback room's
   pre-game holds): the seller closes the row the man left; the buyer seats him by rating among its men (a rank-locked
   man keeps his place ahead of him). */
/* A man left `team` from `row` at `pool` (traded or released): the men behind him move up one row, and when that
   empties row 6 while men share the overflow row 7 (a camp roster), the best of them takes row 6. */
static void close_gap(u32 team, u32 pool, u32 row) {
    u32 n = B(team + 0x11C), six = 0, best = 0, top = 0;
    for (u32 j = 0; j < n && j < SLOTS; j++) {
        u32 o = D(team + 4 * j), ro, r;
        if (!o || pool_of(o) != pool) continue;
        ro = row_of(o);
        if (ro > row && ro < 7) set_row(o, --ro);
        if (ro == 6) six = 1;
        if (ro == 7 && (r = rating(o) + 1) > top) {
            top = r;
            best = o;
        }
    }
    if (row < 7 && !six && best) set_row(best, 6);
}

static void repair(u32 seller, u32 buyer, u32 qs, u32 old_row) {
    u32 pool = pool_of(qs), n, newrow = 0, r = rating(qs);
    close_gap(seller, pool, old_row);
    n = B(buyer + 0x11C);
    for (u32 j = 0; j < n && j < SLOTS; j++) {
        u32 o = D(buyer + 4 * j);
        if (o && o != qs && pool_of(o) == pool && (B(o + 0x52) & RANK_LOCK || rating(o) >= r)) newrow++;
    }
    if (newrow > 7) newrow = 7;
    for (u32 j = 0; j < n && j < SLOTS; j++) {
        u32 o = D(buyer + 4 * j), ro;
        if (o && o != qs && pool_of(o) == pool && (ro = row_of(o)) >= newrow && ro < 7) set_row(o, ro + 1);
    }
    set_row(qs, newrow);
    ct_counters.rows_repaired += 2;
}

static u32 post(struct posted *out, u32 stage, u32 round2, u32 *exhausted) {
    struct club c[CLUBS];
    u8 q[TN_POSITIONS][4];
    u32 root = D(LEAGUE_ROOT), count = 0, made = 0, year = D(YEAR), week = D(WEEK), base, start, threshold;
    u32 kind = stage == 7;
    if (!root) return 0;
    ct_counters.rounds++;
    base = D(root + 0x1C);
    for (u32 i = 0; i < CLUBS; i++) {
        struct club *x = &c[i];
        x->team = CLUB_AT(i);
        x->flags = x->load = x->active = x->best = x->w = x->l = x->t = x->paid = x->qbs = 0;
        for (u32 p = 0; p < TN_POSITIONS; p++) x->weak[p] = x->other[p] = x->present[p] = 0;
        if (!x->team || B(x->team + 0x11C) > SLOTS) {
            x->flags = OUT;
            continue;
        }
        x->active = B(x->team + 0x11C);
        scan(x);
        /* S8: a club in a record of ours in the first round sits out the second (one trade per club per call) */
        if (D(USER_FLAG + 4 * i) || named_club(x->team) || (round2 && ct_round_mask >> i & 1)) x->flags = OUT;
        for (u32 r = 1; r <= 7; r++)
            if (B(PICKS + 32 * r + i) != i) x->paid++;
    }
    ledger_load(c, base);
    /* The league scale of each pool and each club's percentile there. */
    for (u32 p = 0; p < TN_POSITIONS; p++) {
        u8 v[2 * CLUBS];
        u32 n = 0;
        for (u32 i = 0; i < CLUBS; i++) c[i].pct[p] = 0;
        q[p][0] = q[p][1] = q[p][2] = q[p][3] = 0;
        if (!TN_NEED_SEATS[p]) continue;
        /* the header's league scale: every club's need-seat starters (weak, and the other at a two-seat pool) */
        for (u32 j = 0; j < CLUBS * TN_NEED_SEATS[p]; j++) {
            u8 e = j < CLUBS ? c[j].weak[p] : c[j - CLUBS].other[p];
            u32 k = n++;
            while (k && v[k - 1] > e) {
                v[k] = v[k - 1];
                k--;
            }
            v[k] = e;
        }
        q[p][0] = v[n / 4];
        q[p][1] = v[n / 2];
        q[p][2] = v[3 * n / 4];
        q[p][3] = v[9 * n / 10];
        for (u32 i = 0; i < CLUBS; i++) c[i].pct[p] = (u8)tn_percentile(v, n, c[i].weak[p]);
    }
    for (u32 i = 0; i < CLUBS; i++) {
        struct club *x = &c[i];
        if (x->flags & OUT) continue;
        if (x->load >= LOAD_LIMIT) {
            ct_counters.out_load++;
            x->flags = OUT;
            continue;
        }
        if (stage == 8) {
            x->w = (u8)WINS(x->team);
            x->l = (u8)LOSSES(x->team);
            x->t = (u8)TIES(x->team);
        }
        if (x->active >= 51) {
            x->flags |= SELLER;
            if (stage == 8 && ct_settings.stages & ST_REBUILD && x->w + x->l + x->t >= 4 && x->l >= x->w + 3u)
                x->flags |= REBUILD;
        }
        if (stage == 8 && x->w + 1u < x->l) {
            ct_counters.out_race++;
            continue;
        }
        if (x->paid >= PICKS_PAID_LIMIT) {
            ct_counters.out_picks++;
            continue;
        }
        if (x->qbs < 2) {
            ct_counters.out_quarterbacks++;
            continue;
        }
        x->flags |= BUYER;
        ct_counters.buyers++;
    }
    threshold = stage == 8 ? ct_settings.p8_ppm / 2 * WEEK_WEIGHT[week < 9 ? week : 8] : ct_settings.p7_ppm;
    start = fmix(year * 131u + week * 7u + stage + round2 * 977u) % CLUBS;
    for (u32 k = 0; k < CLUBS; k++) {
        u32 b = (start + k) % CLUBS, qs = 0, seller = 0, rebuild = 0, r = 0, pool = 0xFFu, depth = 0, word, result;
        u32 hash, slot, flags = 0, victim = 0, chance, wanted = 0;
        struct club *x = &c[b];
        u8 tried[TN_POSITIONS];
        i32 room;
        if ((x->flags & (BUYER | USED)) != BUYER) continue;
        for (u32 p = 0; p < TN_POSITIONS; p++) tried[p] = 0;
        room = (i32)(D(CAP) - D(x->team + 0x124));
        /* S1: up to three needs, the lowest percentile first; stage 7 also a pool with no present backup (S10). */
        for (u32 choice = 0; choice < 3 && !qs; choice++) {
            u32 need = 0xFFu, low = 256, is_depth = 0, floor;
            for (u32 p = 1; p < TN_POSITIONS; p++) {
                u32 thin = kind && TN_NEED_SEATS[p] && x->present[p] < (u32)TN_SEATS[p] + 1u;
                if (!TN_NEED_SEATS[p] || tried[p] || !POOL_WEIGHT[kind][p]) continue;
                if ((x->pct[p] < QUARTER || thin) && x->pct[p] < low) {
                    low = x->pct[p];
                    need = p;
                    is_depth = x->pct[p] >= QUARTER;
                }
            }
            if (need == 0xFFu) break;
            tried[need] = 1;
            wanted = 1;
            floor = is_depth ? (q[need][0] > 8 ? q[need][0] - 8u : 0u)
                             : (x->weak[need] + 3u > q[need][0] ? x->weak[need] + 3u : q[need][0]);
            for (u32 i = 0; i < CLUBS; i++) {
                u32 sale = 0, p;
                if (i == b || (c[i].flags & (SELLER | USED | OUT)) != SELLER) continue;
                p = offer_of(&c[i], stage, need, floor, r, room, q[need], &sale);
                if (p) {
                    qs = p;
                    seller = i;
                    rebuild = sale;
                    r = rating(p);
                    pool = need;
                    depth = is_depth;
                }
            }
        }
        if (!wanted) {
            ct_counters.no_need++;
            continue;
        }
        if (!qs) {
            ct_counters.no_package++;
            continue;
        }
        if (rebuild) {
            ct_counters.rebuild_packages++;
            flags |= F_REBUILD;
        }
        if (depth) {
            ct_counters.depth_packages++;
            flags |= F_DEPTH;
        }
        if (round2) flags |= F_ROUND2;
        word = pick(b, price(qs, r, q[pool], stage));
        {
            u32 key[9] = {DECISION, b, pool, year, stage, week, index_of(qs), x->w, x->l};
            hash = 0x43505454u;
            for (u32 i = 0; i < 9; i++) hash = fmix(hash ^ key[i]);
            hash %= 1000000u;
        }
        chance = threshold / 16u * POOL_WEIGHT[kind][pool];
        if (x->active >= (stage == 8 ? 53u : 65u)) {
            victim = release_of(x->team, pool);
            flags |= F_RELEASE;
        }
        if (!word) {
            ct_counters.no_pick++;
            result = NO_PICK;
        } else if (hash >= chance) {
            ct_counters.kept++;
            result = KEPT;
        } else if (made >= MAX_POSTS) {
            ct_counters.capped++;
            result = CAPPED;
        } else if (flags & F_RELEASE && !victim) {
            ct_counters.no_release++;
            result = NO_RELEASE;
        } else {
            u32 offer[15];
            for (u32 i = 0; i < 15; i++) offer[i] = 0;
            offer[0] = 2;
            offer[2] = c[seller].team;
            offer[3] = qs;
            offer[8] = x->team;
            offer[12] = word;
            slot = 1;
            while (slot < 15 && D(BOARD + RECORD * slot)) slot++;
            if (slot == 15) {
                ct_counters.no_slot++;
                *exhausted = 1;
                result = NO_SLOT;
            } else if ((ct_settings.flags & FLAG_SHADOW) != 0) {
                x->flags |= USED;
                c[seller].flags |= USED;
                made++;
                ct_counters.shadow++;
                result = WOULD;
            } else {
                if (victim) {
                    u32 vpool = pool_of(victim), vrow = row_of(victim);
                    RELEASE(x->team, victim, 1, 1);
                    close_gap(x->team, vpool, vrow);              /* S9: the native release leaves his row empty */
                    ct_counters.releases++;
                }
                if (!evaluate(offer)) {
                    ct_counters.refused++;
                    result = REFUSED;
                } else {
                    u32 rec = BOARD + RECORD * slot;
                    x->flags |= USED;
                    c[seller].flags |= USED;
                    made++;
                    for (u32 i = 1; i < 13; i++) D(rec + 4 * i) = offer[i];
                    W(rec + 0x34) = 0;
                    D(rec) = 2;                                  /* kind last */
                    out[count].rec = rec;
                    out[count].qs = qs;
                    out[count].buyer = b;
                    out[count].seller = seller;
                    out[count].word = word;
                    out[count].pool = pool | row_of(qs) << 8;       /* and his row at the seller */
                    ct_current[count] = rec;
                    ct_round_mask |= 1u << b | 1u << seller;
                    count++;
                    ct_counters.posted++;
                    result = POSTED;
                }
            }
        }
        if (result != KEPT) row(stage, b, seller, pool, result, qs, word, r, x->pct[pool], q[pool][0], flags);
    }
    return count;
}

/* One round: post, the native pending scan, then for every record of ours: executed (rows repaired), still there
   (refused: cancelled) or gone. Returns whether the board ran out of slots. */
static u32 round_of(u32 menu, u32 stage, u32 round2) {
    struct posted done[MAX_POSTS];
    u32 exhausted = 0, count;
    u32 cursor = D(LEDGER_CURSOR), root = D(LEAGUE_ROOT);
    for (u32 i = 0; i < MAX_POSTS; i++) ct_current[i] = 0;
    count = post(done, stage, round2, &exhausted);
    PENDING(menu);
    for (u32 i = 0; i < MAX_POSTS; i++) ct_current[i] = 0;
    /* S8: a club in any trade this scan executed (a native swap too) sits out the second round */
    for (u32 n = 0; root && cursor < LEDGER_ROWS && cursor != D(LEDGER_CURSOR) && n < LEDGER_ROWS; n++) {
        u32 at = LEDGER + 12u * cursor, club = D(at + 8);
        if ((D(at) & 31u) == 7u && club >= D(root + 0x1C)) ct_round_mask |= 1u << (club - D(root + 0x1C)) / TEAM_SIZE % 32u;
        if (++cursor == LEDGER_ROWS) cursor = 0;
    }
    for (u32 i = 0; i < count; i++) {
        struct posted *x = &done[i];
        u32 result = 0;
        if (D(x->rec) == 2 && D(x->rec + 0xC) == x->qs) {
            CANCEL(x->rec, 0, 1, 1);
            ct_counters.cancelled++;
            result = CANCELLED;
        } else if (listed(CLUB_AT(x->buyer), x->qs)) {
            ct_counters.executed++;
            repair(CLUB_AT(x->seller), CLUB_AT(x->buyer), x->qs, x->pool >> 8);
            result = POSTED;
        } else {
            ct_counters.gone++;
        }
        row(stage, x->buyer, x->seller, x->pool & 0xFFu, result, x->qs, x->word, 0, 0, 0, F_AFTER);
    }
    return exhausted;
}

void __attribute__((noinline, cdecl)) trade_call(u32 menu) {
    u32 stage = D(STAGE), active = 0;
    ct_counters.calls++;
    if (ct_settings.magic[0] != 0x54555043u || ct_settings.magic[1] != 0x31764452u || ct_settings.mode != 1)
        ct_counters.bad_settings++;
    else if (stage == 8 && ct_settings.stages & ST_SEASON) {
        if (D(WEEK) >= B(DEADLINE_WEEK)) ct_counters.past_deadline++;
        else active = 1;
    } else if (stage == 7 && ct_settings.stages & ST_PRESEASON) {
        if (!D(YEAR)) ct_counters.opening_preseason++;          /* S10: the opening rosters stay the real ones */
        else active = 1;
    } else
        ct_counters.inactive++;
    if (!active) {
        PENDING(menu);
        return;
    }
    ct_round_mask = 0;
    if (round_of(menu, stage, 0) && !(ct_settings.flags & FLAG_SHADOW)) {
        ct_counters.second_rounds++;                            /* S8: once more after the scan freed slots */
        round_of(menu, stage, 1);
    }
}

/* S7: is `record` (the story writer's EBP) one of ours in this pending scan? Counts the stories it forces. */
u32 __attribute__((noinline, cdecl)) story_is_ours(u32 record) {
    for (u32 i = 0; i < MAX_POSTS; i++)
        if (ct_current[i] && ct_current[i] == record) {
            ct_counters.stories_forced++;
            return 1;
        }
    return 0;
}
