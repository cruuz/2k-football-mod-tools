/* CPU trades at every position (beta 81, owner nfl2k5_cpu_trades; the trades-all lane's design with
   the coordinator's rulings RULINGS.md R1 to R7). Two fixed pages at 0x152E000 (nfl2k5_xbe_space.CPU_TRADES_*).

   When: inside the native trade pass 0x2BC960, at its pending scan (entry.S, site 0x2BC96C): this code posts its
   records, calls the pending scan 0x2BC900 (which executes or refuses every kind-2 record between CPU clubs through the
   native executor 0x2BC670), then cancels every record of its own still on the board. A record of ours therefore exists
   only during that one native call: never at a save point. The quarterback trades of stage 4b (nfl2k5_qb_trades) post
   before 0x2BC960 and are left to that page; this code never offers or buys a QB, K or P.

   Settings record (page + 0x1200, CPUTRDv1): stage bits 1 = the regular season (league stage 8, only while the week
   counter is below the deadline byte 0x5151C5 whatever the Trade Deadline option says; RULINGS R5), 2 = the preseason
   (stage 7), 4 = losing clubs may sell veterans in season (R3); flags bit 0 = shadow (everything is computed, counted
   and logged; nothing is written to the board); p8_ppm and p7_ppm = the posting chance per buyer and tick in millionths
   (stage 8: times the week weight below, halved). Nothing runs in stages 1 to 6 or 9 (R2: the pre-draft market and
   pick-only swaps are not built).

   One tick (post):
   - League scale per position: eff(c, p) = the k(p)-th best fully healthy man at p on club c (rating 0x246D80(p, 0),
     whole points; 0 with fewer healthy men; k = STARTERS[p]); q25, q50, q75, q90 of the 32 clubs' eff.
   - Buyer: a club no person manages (0xE5775C) that no pending offer names (a native listing does not count), in fewer than LOAD_LIMIT trade groups of
     the native ledger (0xE3F070, 600 rows; native, 4b and ours count; R4), with room for one more player (stage 8: 52
     or fewer active, stage 7: 64 or fewer; it never cuts), in stage 8 still in the race (W + 1 >= L). Its need is the
     position with eff below q25 that is furthest below it.
   - Package: the best-rated man Qs at that position over every seller: fully healthy, no status bits, 2+ years pro,
     1+ contract years and, from the second franchise season (year index 1), not in the first year of his contract
     (years left +0x24 & 15 != length +0x27 & 15; the starting roster has length = years left for everyone), not
     star-tagged (+0x53 bit 0; MyCareer's player carries it), not the seller's best player, not a young cornerstone
     (q90 or better with 6 or fewer years pro), named by no board record (listings included) and by no signing (kind 1) or trade (kind 7)
     row of the native ledger, rated at least eff(buyer) + 3 and at least q25; the buyer's cap room minus his charge
     above 10. Seller: no person manages it, not named, under LOAD_LIMIT, 51 or more active; it sells a man below its
     own weakest healthy starter at that position, or (bit 4, stage 8, L >= W + 3 after 4 or more games) a veteran with
     6+ years pro; either way it keeps k healthy men at the position and the economy's cut minimum (CUT_MIN).
   - Price: the buyer's pick of the coming draft (any slot it owns, its own first), round by Qs against the position's
     league scale: q90+ a 2nd, q75+ a 3rd, q50+ a 4th, q25+ a 5th, else a 6th; one round later with 9+ years pro and
     again with one contract year left (never past the 7th); not owned: one round earlier, else no trade.
   - Draw (stateless, reload-stable): hash(9, buyer, position, year, stage, week, Qs, W, L) % 1000000 below the stage's
     chance; the native evaluator 0x2BAE90 must accept the record as built; the first kind-0 slot of 1 to 14, kind
     written last; at most MAX_POSTS records (or would-be records, in shadow) a tick; one record per club.

   Ring rows (page + 0x1400, 128 x 24 bytes, cursor + 0x1340): see struct event. Results before the pending scan:
   0 kept by the draw, 1 posted, 2 would post (shadow), 3 no pick, 4 refused by the evaluator, 5 no slot, 6 per-tick cap;
   rows after it (flag AFTER): 1 executed, 7 refused by the executor and cancelled here, 0 gone (the game removed it
   without a trade). */

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
#define CANCEL ((void (FC *)(u32, u32, u32, u32))0x002BB660)   /* (offer, new kind, clear A, clear B), ret 8 */
#define PENDING ((void (__attribute__((stdcall)) *)(u32))0x002BC900)   /* the pending scan (menu), ret 4 */

#define LEAGUE_ROOT 0x00B72918u      /* [root + 4] players (0x54 bytes each), [root + 0x1C] clubs (500 bytes each) */
#define STAGE 0x00E576A4u            /* 7 preseason, 8 season, 9 playoffs */
#define WEEK 0x00E576B4u
#define YEAR 0x00E576B8u
#define USER_FLAG 0x00E5775Cu        /* u32 per league club: a person manages it */
#define DEADLINE_WEEK 0x005151C5u    /* stage_table[8].byte5: the trade window's week (9 with the deadline owner) */
#define BOARD 0x00E3C27Cu            /* 15 records of 0x3C; slot 0 is the user's work slot */
#define RECORD 0x3Cu
#define PICKS 0x00E3C094u            /* owner byte of (year 0) round r, slot s: PICKS + 32 * r + s */
#define CAP 0x00E3C278u
#define LEDGER 0x00E3F070u           /* 600 rows of 12 bytes: kind word (bit 31 = last row of a group), player, club */
#define LEDGER_CURSOR 0x00E3F06Cu
#define LEDGER_ROWS 600u
#define CLUBS 32u
#define SLOTS 65u
#define TEAM_SIZE 500u
#define PLAYER_SIZE 0x54u
#define POSITIONS 17u
#define INJURED 0x80000000u
#define WEEKS_MASK (255u << 22)

#define ST_SEASON 1u
#define ST_PRESEASON 2u
#define ST_REBUILD 4u
#define FLAG_SHADOW 1u
#define MAX_POSTS 6u
#define LOAD_LIMIT 3u                /* R4: three trade groups per club per ledger window */
#define DECISION 9u

#define KEPT 0u
#define POSTED 1u
#define WOULD 2u
#define NO_PICK 3u
#define REFUSED 4u
#define NO_SLOT 5u
#define CAPPED 6u
#define CANCELLED 7u
#define F_REBUILD 1u
#define F_OWN_PICK 2u
#define F_AFTER 0x40u

struct settings {
    u32 magic[2];
    u32 mode, stages, flags, p8_ppm, p7_ppm, reserved;
};

/* COUNTERS BEGIN (build.py reads these names in order; page + 0x1240, u32 each) */
struct counters {
    u32 calls;                   /* every entry at the pending scan, whatever the settings */
    u32 bad_settings;            /* magic or mode not CPUTRDv1 / 1: nothing posted */
    u32 inactive;                /* settings fine but this stage (or its bit) does not post */
    u32 past_deadline;           /* stage 8 at or past the deadline byte: nothing posted */
    u32 ticks;                   /* ticks that looked for trades */
    u32 needs;                   /* buyers with a need (each tick, each buyer once) */
    u32 load_out;                /* clubs left out for LOAD_LIMIT trade groups in the ledger */
    u32 no_package;              /* a need, but no seller offers a man who fits */
    u32 rebuild_packages;        /* packages from a losing seller's starter (bit 4) */
    u32 no_pick;                 /* a package, but the buyer owns no pick of the round or the one before */
    u32 kept;                    /* the draw kept it off the board this tick */
    u32 capped;                  /* MAX_POSTS reached this tick */
    u32 refused;                 /* the native evaluator refused the record as built */
    u32 no_slot;                 /* slots 1 to 14 all in use */
    u32 shadow;                  /* records that would be posted, in shadow */
    u32 posted;
    u32 executed;                /* after the pending scan: Qs on the buyer's list */
    u32 cancelled;               /* refused by the executor (record still there): cancelled here */
    u32 gone;                    /* removed by the game without a trade (pruner or ownership guard) */
    u32 events_logged;
};
/* COUNTERS END */

struct event {                   /* 24 bytes */
    u16 year;
    u8 stage, week, buyer, seller, position, result;
    u16 player, word;
    u8 rating, eff, q25, flags;
    u32 draw, threshold;
} __attribute__((packed));

extern volatile struct settings ct_settings;          /* page + 0x1200 */
extern volatile struct counters ct_counters;          /* page + 0x1240 */
extern volatile u32 ct_ring_cursor;                   /* page + 0x1340 */
extern volatile struct event ct_ring[128];            /* page + 0x1400 */

/* Starters per position (QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE); 0 = never traded here (QB is 4b's). */
static const u8 STARTERS[POSITIONS] = {0, 0, 0, 3, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 2, 2, 2};
/* The economy's cut minimum (tools/qb_room/moves.c floor_min; OLB and ILB one pool, counted under ILB). */
static const u8 CUT_MIN[POSITIONS] = {2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4};
/* Stage 8 week weights (stored week 0..8), halved when used: the deadline rush of the real league. */
static const u8 WEEK_WEIGHT[9] = {1, 1, 1, 1, 2, 2, 2, 4, 8};

struct club {
    u32 team;
    u8 flags, load, active, best;
    u8 w, l, t, need;
    u8 eff[POSITIONS];
    u8 pad[3];
};
#define OUT 1u                       /* no club, a person manages it, or named by a live record */
#define BUYER 2u
#define SELLER 4u
#define REBUILD 8u
#define USED 16u

struct posted { u32 rec, qs, buyer, seller, word, position; };

static u32 healthy(u32 p) {
    return !(D(p + 0x20) & (INJURED | WEEKS_MASK)) && !(D(p + 0x24) & 0x70000000u);
}

static u32 rating(u32 p) {                               /* 0x246D80(p, 0) to whole points (room.c overall()) */
    union { float f; u32 u; } v;
    v.f = RATING(p, 0);
    u32 e = (v.u >> 23) & 255;
    if (v.u >> 31 || e < 119) return 0;
    if (e > 127) return 100;
    u32 s = 150 - e;
    return (((v.u & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s;
}

static u32 index_of(u32 p) {
    return p ? (p - D(D(LEAGUE_ROOT) + 4)) / PLAYER_SIZE : 0xFFFFu;
}

/* Does a live record (kind != 0, slots 0 to 14) name player p (either side)? */
static u32 named(u32 p) {
    for (u32 rec = BOARD; rec < BOARD + 15 * RECORD; rec += RECORD)
        for (u32 o = 0xC; D(rec) && o < 0x30; o += 4)
            if ((o < 0x18 || o >= 0x24) && D(rec + o) == p) return 1;
    return 0;
}

/* Does a pending offer (any kind but 0 and 1, the native listings) name club t on either side? A listing only names
   its player (named above), so a club with a listing can still trade here. */
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
    for (u32 row = LEDGER; row < LEDGER + 12 * LEDGER_ROWS; row += 12) {
        u32 kind = D(row) & 31;
        if ((kind == 1 || kind == 7) && D(row + 4) == p) return 1;
    }
    return 0;
}

static u32 fmix(u32 h) {
    h ^= h >> 16; h *= 0x85EBCA6Bu; h ^= h >> 13; h *= 0xC2B2AE35u; h ^= h >> 16;
    return h;
}

static void row(u32 stage, u32 buyer, u32 seller, u32 position, u32 result, u32 qs, u32 word, u32 rating10, u32 eff,
                u32 q25, u32 flags, u32 draw, u32 threshold) {
    u32 n = ct_ring_cursor;
    volatile struct event *e = &ct_ring[n % 128u];
    e->year = (u16)D(YEAR);
    e->stage = (u8)stage;
    e->week = (u8)D(WEEK);
    e->buyer = (u8)buyer;
    e->seller = (u8)seller;
    e->position = (u8)position;
    e->result = (u8)result;
    e->player = (u16)index_of(qs);
    e->word = (u16)word;
    e->rating = (u8)rating10;
    e->eff = (u8)eff;
    e->q25 = (u8)q25;
    e->flags = (u8)flags;
    e->draw = draw;
    e->threshold = threshold;
    ct_ring_cursor = n + 1;
    ct_counters.events_logged++;
}

/* The native evaluator 0x2BAE90 (EAX = offer; stack: value A out, value B out, message 0; ret 0xC): Out status, both
   payrolls (not in stage 7), both counts. Reads only (no message buffer). */
static u32 evaluate(u32 *offer) {
    u32 out[2], ok;
    __asm__ volatile("pushl $0\n\tpushl %2\n\tpushl %1\n\tmovl $0x2BAE90, %%ecx\n\tcall *%%ecx"
                     : "=a"(ok) : "r"(&out[0]), "r"(&out[1]), "a"(offer) : "ecx", "edx", "memory", "cc");
    return ok;
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

/* One club's roster: eff per position (the k-th best healthy rating) and its best player (any health). */
static void scan(struct club *x) {
    u8 top[POSITIONS][3];
    for (u32 p = 0; p < POSITIONS; p++) top[p][0] = top[p][1] = top[p][2] = 0;
    x->best = 0;
    for (u32 j = 0; j < x->active; j++) {
        u32 p = D(x->team + 4 * j), pos, r;
        if (!p || (pos = B(p + 0x35)) >= POSITIONS) continue;
        r = rating(p);
        if (r > x->best) x->best = (u8)r;
        if (!healthy(p)) continue;
        for (u32 k = 0; k < 3; k++)
            if (r > top[pos][k]) {
                for (u32 m = 2; m > k; m--) top[pos][m] = top[pos][m - 1];
                top[pos][k] = (u8)r;
                break;
            }
    }
    for (u32 p = 0; p < POSITIONS; p++) x->eff[p] = STARTERS[p] ? top[p][STARTERS[p] - 1] : 0;
}

/* The man at position `pos` the seller may sell to a buyer needing `floor` or better; 0 if none. */
static u32 offer_of(struct club *s, u32 pos, u32 floor, u32 above, i32 room, const u8 *q, u32 *rebuild) {
    u32 t = s->team, lb = pos == 10 || pos == 11, healthy_at = 0, count = 0, best = 0, best_r = above;
    for (u32 j = 0; j < s->active; j++) {
        u32 p = D(t + 4 * j), at;
        if (!p) continue;
        at = B(p + 0x35);
        if (at == pos || (lb && (at == 10 || at == 11))) count++;
        if (at == pos && healthy(p)) healthy_at++;
    }
    /* After the sale: k healthy men and the cut minimum at the position (OLB and ILB together under ILB's minimum). */
    if (healthy_at < STARTERS[pos] + 1u || count < CUT_MIN[lb ? 11 : pos] + 1u) return 0;
    for (u32 j = 0; j < s->active; j++) {
        u32 p = D(t + 4 * j), r, pro, left, sale_rebuild;
        if (!p || B(p + 0x35) != pos || !healthy(p)) continue;
        pro = B(p + 0x25) & 31;
        left = B(p + 0x24) & 15;
        /* first contract year (just signed or re-signed) from the second franchise season: the roster a franchise
           starts from carries length = years left for every man, so in year index 0 the ledger rule alone applies */
        if (pro < 2 || !left || (D(YEAR) && left == (B(p + 0x27) & 15u)) || B(p + 0x53) & 1) continue;
        r = rating(p);
        if (r < floor || r <= best_r || r >= s->best || (r >= q[3] && pro <= 6)) continue;
        sale_rebuild = r >= s->eff[pos];
        if (sale_rebuild && (!(s->flags & REBUILD) || pro < 6)) continue;
        if (room - (i32)SALARY(p) <= 10 || named(p) || in_ledger(p)) continue;
        best = p;
        best_r = r;
        *rebuild = sale_rebuild;
    }
    return best;
}

static u32 price(u32 p, u32 r, const u8 *q) {
    u32 round = r >= q[3] ? 2 : r >= q[2] ? 3 : r >= q[1] ? 4 : r >= q[0] ? 5 : 6;
    if ((B(p + 0x25) & 31) >= 9) round++;
    if ((B(p + 0x24) & 15) == 1) round++;
    return round > 7 ? 7 : round;
}

/* The buyer's pick of the coming draft in this round or the one before: its own slot first, else any it owns. */
static u32 pick(u32 b, u32 ruled, u32 *own) {
    for (u32 round = ruled; round >= 1 && round + 1 >= ruled; round--) {
        if (B(PICKS + 32 * round + b) == b) {
            *own = 1;
            return round | b << 6;
        }
        for (u32 s = 0; s < CLUBS; s++)
            if (B(PICKS + 32 * round + s) == b) {
                *own = 0;
                return round | s << 6;
            }
    }
    return 0;
}

static u32 post(struct posted *out, u32 stage) {
    struct club c[CLUBS];
    u8 q[POSITIONS][4];
    u32 root = D(LEAGUE_ROOT), count = 0, made = 0, year = D(YEAR), week = D(WEEK), base, start, threshold;
    if (!root) return 0;
    ct_counters.ticks++;
    base = D(root + 0x1C);
    for (u32 i = 0; i < CLUBS; i++) {
        struct club *x = &c[i];
        x->team = CLUB_AT(i);
        x->flags = x->load = x->active = x->best = x->w = x->l = x->t = 0;
        x->need = 0xFF;
        for (u32 p = 0; p < POSITIONS; p++) x->eff[p] = 0;
        if (!x->team || B(x->team + 0x11C) > SLOTS) {
            x->flags = OUT;
            continue;
        }
        x->active = B(x->team + 0x11C);
        scan(x);
        if (D(USER_FLAG + 4 * i) || named_club(x->team)) x->flags = OUT;
    }
    ledger_load(c, base);
    /* The league scale of each position: the 32 clubs' eff, sorted. */
    for (u32 p = 0; p < POSITIONS; p++) {
        u8 v[CLUBS];
        for (u32 i = 0; i < CLUBS; i++) {
            u8 e = c[i].eff[p];
            u32 k = i;
            while (k && v[k - 1] > e) {
                v[k] = v[k - 1];
                k--;
            }
            v[k] = e;
        }
        q[p][0] = v[8];
        q[p][1] = v[16];
        q[p][2] = v[24];
        q[p][3] = v[28];
    }
    for (u32 i = 0; i < CLUBS; i++) {
        struct club *x = &c[i];
        u32 deficit = 0;
        if (x->flags & OUT) continue;
        if (x->load >= LOAD_LIMIT) {
            ct_counters.load_out++;
            continue;
        }
        if (stage == 8) {
            x->w = (u8)WINS(x->team);
            x->l = (u8)LOSSES(x->team);
            x->t = (u8)TIES(x->team);
        }
        if (x->active >= 51) {
            x->flags |= SELLER;
            if (stage == 8 && ct_settings.stages & ST_REBUILD && x->w + x->l + x->t >= 4 && x->l >= x->w + 3)
                x->flags |= REBUILD;
        }
        if (x->active > (stage == 8 ? 52 : 64) || (stage == 8 && x->w + 1 < x->l)) continue;
        for (u32 p = 0; p < POSITIONS; p++)
            if (STARTERS[p] && x->eff[p] < q[p][0] && (u32)(q[p][0] - x->eff[p]) > deficit) {
                deficit = q[p][0] - x->eff[p];
                x->need = (u8)p;
            }
        if (x->need != 0xFF) {
            x->flags |= BUYER;
            ct_counters.needs++;
        }
    }
    threshold = stage == 8 ? ct_settings.p8_ppm / 2 * WEEK_WEIGHT[week < 9 ? week : 8] : ct_settings.p7_ppm;
    start = fmix(year * 131u + week * 7u + stage) % CLUBS;
    for (u32 k = 0; k < CLUBS; k++) {
        u32 b = (start + k) % CLUBS, pos, qs = 0, seller = 0, rebuild = 0, r = 0, word, own = 0, result, hash, slot;
        struct club *x = &c[b];
        if ((x->flags & (BUYER | USED)) != BUYER) continue;
        pos = x->need;
        u32 floor = x->eff[pos] + 3u > q[pos][0] ? x->eff[pos] + 3u : q[pos][0];
        i32 room = (i32)(D(CAP) - D(x->team + 0x124));
        for (u32 i = 0; i < CLUBS; i++) {
            u32 sale = 0, p;
            if (i == b || (c[i].flags & (SELLER | USED)) != SELLER) continue;
            p = offer_of(&c[i], pos, floor, r, room, q[pos], &sale);
            if (p) {
                qs = p;
                seller = i;
                rebuild = sale;
                r = rating(p);
            }
        }
        if (!qs) {
            ct_counters.no_package++;
            continue;
        }
        if (rebuild) ct_counters.rebuild_packages++;
        word = pick(b, price(qs, r, q[pos]), &own);
        {
            u32 key[9] = {DECISION, b, pos, year, stage, week, index_of(qs), x->w, x->l};
            hash = 0x43505454u;
            for (u32 i = 0; i < 9; i++) hash = fmix(hash ^ key[i]);
            hash %= 1000000u;
        }
        if (!word) {
            ct_counters.no_pick++;
            result = NO_PICK;
        } else if (hash >= threshold) {
            ct_counters.kept++;
            result = KEPT;
        } else if (made >= MAX_POSTS) {
            ct_counters.capped++;
            result = CAPPED;
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
            if (!evaluate(offer)) {
                ct_counters.refused++;
                result = REFUSED;
            } else if (slot == 15) {
                ct_counters.no_slot++;
                result = NO_SLOT;
            } else {
                x->flags |= USED;
                c[seller].flags |= USED;
                made++;
                if ((ct_settings.flags & FLAG_SHADOW) != 0) {
                    ct_counters.shadow++;
                    result = WOULD;
                } else {
                    u32 rec = BOARD + RECORD * slot;
                    for (u32 i = 1; i < 13; i++) D(rec + 4 * i) = offer[i];
                    W(rec + 0x34) = 0;
                    D(rec) = 2;                                  /* kind last */
                    out[count].rec = rec;
                    out[count].qs = qs;
                    out[count].buyer = b;
                    out[count].seller = seller;
                    out[count].word = word;
                    out[count].position = pos;
                    count++;
                    ct_counters.posted++;
                    result = POSTED;
                }
            }
        }
        row(stage, b, seller, pos, result, qs, word, r, x->eff[pos], q[pos][0],
            (rebuild ? F_REBUILD : 0) | (own ? F_OWN_PICK : 0), hash, threshold);
    }
    return count;
}

/* The pending scan with this page around it (trade_entry at 0x2BC96C): post, run 0x2BC900 as the site would, then
   clear up: every record of ours still there (kind 2 with A's first player the man we named: a slot our executed
   record freed may hold a native record by now) is cancelled with 0x2BB660(rec, 0, 1, 1), as the game's pre-sweep does. */
void __attribute__((noinline, cdecl)) trade_call(u32 menu) {
    struct posted done[MAX_POSTS];
    u32 count = 0, stage = D(STAGE);
    ct_counters.calls++;
    if (ct_settings.magic[0] != 0x54555043u || ct_settings.magic[1] != 0x31764452u || ct_settings.mode != 1)
        ct_counters.bad_settings++;
    else if (stage == 8 && ct_settings.stages & ST_SEASON) {
        if (D(WEEK) >= B(DEADLINE_WEEK)) ct_counters.past_deadline++;
        else count = post(done, 8);
    } else if (stage == 7 && ct_settings.stages & ST_PRESEASON)
        count = post(done, 7);
    else
        ct_counters.inactive++;
    PENDING(menu);
    for (u32 i = 0; i < count; i++) {
        struct posted *x = &done[i];
        u32 result = 0;
        if (D(x->rec) == 2 && D(x->rec + 0xC) == x->qs) {
            CANCEL(x->rec, 0, 1, 1);
            ct_counters.cancelled++;
            result = CANCELLED;
        } else if (listed(CLUB_AT(x->buyer), x->qs)) {
            ct_counters.executed++;
            result = POSTED;
        } else {
            ct_counters.gone++;
        }
        row(stage, x->buyer, x->seller, x->position, result, x->qs, x->word, 0, 0, 0, F_AFTER, 0, 0);
    }
}
