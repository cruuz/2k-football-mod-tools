/* Quarterback trades (beta 81 stage 4b, the quarterback room's stage bit 16; owner nfl2k5_qb_trades, its own fixed page
   0x152C000, DESIGN_CHANGES C20): need-driven quarterback-for-pick trades between two CPU clubs (DESIGN.md 4.2 as
   changed by qb34/evidence/trades/RISKS.md and C20).

   When: inside the native trade pass. The stage-8 case of the weekly advance calls 0x2BC960 (prune 0x2BB9A0, the pending
   scan 0x2BC900 that executes or refuses every kind-2 record between CPU clubs, then three random proposers) at
   0x247E1E, only while the native trade window 0x247D10 is open and before the week's games. trade_call posts at most
   one record per buyer, calls 0x2BC960 exactly as the site would, and then cancels every record of ours still on the
   board (refused by the executor). So a record of ours exists only during that one native call: never at a point where
   the game can be saved, never in stage 7 or 9, never after the deadline.

   The settings are the quarterback room's (its page at 0x1529000: magic, mode, stage bit 16, shadow flag), and the rows
   and counters go to the room's ring and counters (fixed offsets of that page, resolved by tools/qb_trades/build.py from
   tools/qb_room/room.h and INTERFACE.md). This page keeps one link word: the IR owner's store (+0xF00), for E2's L.

   Buyer: not human (every user-managed club of a multi-user franchise is human here: the flag 0xE5775C), not named by a
   live record, 49 to 52 active, a healthy quarterback, at most 2 active quarterbacks (C22 addendum 1), W + L + T >= 2,
   W + 1 >= L, no emergency signing (E1, E2 or the floor, applied or, in shadow, would) logged in this or the previous
   week, its best healthy quarterback S' rated below 85 (C24 F4: a healthy 85+ starter is no need; the relative tests
   below still apply, the two together), and either its starter was benched by D3 in the previous advance's room pass
   (logged with this week), or a quarterback L on its IR 3+ better than S' (L rated with flag 0, C22 addendum 2) is out
   3+ weeks or for the season. Seller: not human, not named, not a buyer, 51 to 65 active, 3+ quarterbacks of whom 3+
   healthy (it keeps 2 healthy ones), and after the sale a healthy backup rated 60 or more besides its best man (C24 F3).
   Package: the best-rated Qs over every seller: fully healthy, not on row 0, rated below the seller's best healthy
   quarterback (C22 (a): a seller never gives up its best man), 4+ years pro, 1+ contract years, not named by a live
   record, ovr(Qs) - ovr(S') >= 3, buyer's cap room - Qs's charge after the trade > 10 (M1/N6: charge_after, the
   executor's contract rewrite applied to a copy of his record); and no free agent at least as good within the
   buyer's reach (C24 F5: E2's candidate F for the buyer, the best healthy free agent the picker 0x322BB0 takes within
   cap room - 10, exactly as moves.c chooses it; ovr(F) >= ovr(Qs) means no trade: E1/E2 sign him instead). Price
   (C24, ruled): the buyer's OWN pick of the coming draft, word round | buyer << 6 (year 0; round one-based, slot =
   original club in season; RISKS.md (b)): round 2 at 95+, 3 at 90-94, 4 at 82-89, 5 at 76-81, 6 at 70-75, 7 below;
   when the buyer does not own that round's pick, the round just before it (C24 N1: at most one round earlier), never
   a later one; neither: no trade.
   Only before the native deadline week (C22 (c): the week counter below the stage table's byte 0x5151C5, 9 with the
   deadline owner), whatever the Trade Deadline option says.
   Post with probability 0.35 (key: 8, buyer, year, W, L, T, Qs index, S' attempts and yards) if the native evaluator
   0x2BAE90 accepts the record as built, into the first kind-0 slot of 1 to 14, kind written last. Shadow (the room's
   flags bit 0, or this page's own flag word +0xF04 bit 0, which puts 4b alone in shadow while the room's other stages
   act): everything is computed, counted and logged; nothing is written to the board.

   Ring rows (decision 8): club = buyer, a = Qs, b = S' (0xFFFF none), d = L - W, g = games, rating10 = the pick word,
   gap = ovr(Qs) - ovr(S'), coach = seller, threshold = 35000. Decision bit 0x10: the need is a D3 benching; 0x40: a row
   written after the native pass. Results: before the pass 0 not posted (the counters say why), 1 posted, 2 would post
   (shadow), 4 refused by the evaluator; after it 1 executed, 7 refused by the executor and cancelled here, 0 gone (the
   game removed it without a trade: the pruner or the ownership guard). */
#include "../qb_room/room.h"

#undef B
#undef W
#undef D
#define B(a) (*(u8 *)(a))
#define W(a) (*(u16 *)(a))
#define D(a) (*(u32 *)(a))
extern struct counters qb_counters_plain;              /* the room's page + 0x2040 */
extern u32 qb_ring_cursor_plain;                       /* the room's page + 0x2E00 */
extern struct event qb_ring_plain[128];                /* the room's page + 0x2400 */
extern struct settings qb_settings_plain;              /* the room's page + 0x2000 */
extern u32 qb_trade_ir_store;                          /* this page + 0xF00: the IR owner's store, else 0 */
extern u32 qb_trade_flags;                             /* this page + 0xF04: bit 0 = 4b alone in shadow (panels) */
#define qb_counters qb_counters_plain

#define STAGE_TRADE 16u                                  /* the room's stage bit 16 (INTERFACE.md) */
#define TRADE_EVENT 8u
#define NEED_D3 0x10u
#define AFTER 0x40u
#define REFUSED 4u
#define CANCELLED 7u
#define BOARD 0x00E3C27Cu
#define RECORD 0x3Cu
#define PICKS 0x00E3C094u
#define CAP 0x00E3C278u
#define IR_MAGIC 0x52493236u
#define IR_CLUBS 0x40u
#define IR_CLUB_SIZE 0xA4u
#define IR_CAP 20u
#define F_SEASON 1u
#define POST_P 35000u
#define DEADLINE_WEEK 0x005151C5u                        /* stage_table[8].byte5: the window test's week (9 with the
                                                            deadline owner); C22 (c) posts only before it, always */

#define SALARY ((u32 (FC *)(u32))0x000E6380)            /* this season's base charge (fastcall ECX) */
#define TIMES10 ((u32 (FC *)(u32))0x000E5FF0)           /* value x 10 (arithmetic only) */
#define TENTHS ((u32 (FC *)(u32))0x000E6000)            /* signed / 10, toward zero (arithmetic only) */
#define OWED ((u32 (FC *)(u32))0x0013ED00)              /* bonus still owed: yearly bonus x years left, tenths */
#define VALUE ((u32 (FC *)(u32, u32, u32, u32, u32))0x002BD440)   /* the picker's value (moves.c): AX */
#define OFFERS 0x00E3C600u                               /* the offer table the picker scans after the list */
#define OFFER_COUNT 100u
#define STARTER_CAP 85                                   /* C24 F4: S' at or above it is no need */
#define BACKUP_MIN 60                                    /* C24 F3: the seller's backup after the sale */
#define CANCEL ((void (FC *)(u32, u32, u32, u32))0x002BB660)   /* (offer, new kind, clear A, clear B), ret 8 */
#define NATIVE_PASS ((void (FC *)(u32, u32))0x002BC960)        /* (proposers, menu) */

static u32 healthy(u32 p) {
    return !(D(p + 0x20) & (INJURED | WEEKS_MASK)) && !(D(p + 0x24) & 0x70000000u);
}

static i32 rating(u32 p, u32 flag) {                     /* room.c overall(): 0x246D80(p, flag) to whole points */
    union { float f; u32 u; } v;
    v.f = RATING(p, flag);
    u32 e = (v.u >> 23) & 255;
    if (v.u >> 31 || e < 119) return 0;
    if (e > 127) return 100;
    u32 s = 150 - e;
    return (i32)((((v.u & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s);
}

static i32 ovr(u32 p) {                                  /* flag 1, the page's rating for healthy men (gap, Qs, S') */
    return rating(p, 1);
}

static u32 index_of(u32 p) {
    return p ? (p - D(D(LEAGUE_ROOT) + 4)) / PLAYER_SIZE : 0xFFFFu;
}

/* Does a live record (kind != 0, slots 0 to 14) name v as a club or a player? */
static u32 named(u32 v) {
    for (u32 rec = BOARD; rec < BOARD + 15 * RECORD; rec += RECORD)
        for (u32 o = 8; D(rec) && o < 0x30; o += 4)
            if (o != 0x18 && o != 0x1C && D(rec + o) == v) return 1;
    return 0;
}

static u32 listed(u32 team, u32 p) {
    for (u32 i = 0; i < B(team + 0x11C) && i < SLOTS; i++)
        if (D(team + 4 * i) == p) return 1;
    return 0;
}

/* One row of the room's ring (INTERFACE.md layout): a, b player records (0: none). */
static void row(u32 club, u32 decision, u32 result, u32 a, u32 b, i32 d, u32 g, u32 word, i32 gap, u32 seller) {
    u32 n = qb_ring_cursor_plain;
    struct event *e = &qb_ring_plain[n % 128u];
    e->year = (u16)D(YEAR);
    e->week = (u8)D(WEEK);
    e->club = (u8)club;
    e->decision = (u8)decision;
    e->result = (u8)result;
    e->a = (u16)index_of(a);
    e->b = (u16)index_of(b);
    e->d = (i8)d;
    e->g = (u8)g;
    e->rating10 = (u16)word;
    e->gap = (i8)gap;
    e->coach = (u8)seller;
    e->threshold = POST_P;
    qb_ring_cursor_plain = n + 1;
    qb_counters.events_logged++;
}

/* E2's injured-reserve test (tools/qb_room/moves.c long_starter): a quarterback on this club's IR, 3+ better than S',
   out 3 weeks or more or for the season. */
static u32 lost_starter(u32 index, i32 best) {
    u32 store = qb_trade_ir_store;
    if (!store || D(store) != IR_MAGIC) {
        qb_counters.trade_ir_unlinked++;
        return 0;
    }
    u32 club = store + IR_CLUBS + IR_CLUB_SIZE * index, n = B(club);
    for (u32 i = 0; i < n && i < IR_CAP; i++) {
        u32 entry = club + 4 + 8 * i, p = D(entry);
        /* C22 addendum (2): L is hurt, and flag 1 discounts injured men (C21): his rating is flag 0's */
        if (p && B(p + 0x35) == 0 && rating(p, 0) - best >= 3 && ((B(entry + 6) & F_SEASON) || (D(p + 0x20) >> 22 & 255) >= 3))
            return 1;
    }
    return 0;
}

/* The native evaluator 0x2BAE90 (EAX = offer; stack: value A out, value B out, message 0; ret 0xC): Out status, both
   payrolls, both counts (A >= 50, B <= 53 in season). Reads only (no message buffer). */
static u32 evaluate(u32 *offer) {
    u32 out[2], ok;
    __asm__ volatile("pushl $0\n\tpushl %2\n\tpushl %1\n\tmovl $0x2BAE90, %%ecx\n\tcall *%%ecx"
                     : "=a"(ok) : "r"(&out[0]), "r"(&out[1]), "a"(offer) : "ecx", "edx", "memory", "cc");
    return ok;
}

/* C24 F5: E2's candidate F for a club with cap room `room` (tools/qb_room/moves.c pick_at and choose, the same scan):
   the man the picker 0x322BB0 takes at budget room - 10 (its scan order: the free-agent list [root + 0x38], then the
   counted entries of the offer table; the first strictly higher 0x246D80(p, 1) whose value is below the budget); if he
   is on the offer table or not fully healthy, ask again at his value. Returns F's rating, 0 when nobody. */
static i32 free_agent(i32 room) {
    if (room <= 10) return 0;
    u32 budget = room - 10 > 0xFFFF ? 0xFFFFu : (u32)(room - 10), root = D(LEAGUE_ROOT), count = D(root + 0x38);
    u32 list = D(root + 0x3C);
    for (;;) {
        u32 have = 0, best = 0, key = 0, value = 0, pool = 0;
        for (u32 i = 0; i < count + OFFER_COUNT; i++) {
            u32 offer = i >= count, entry = OFFERS + 16 * (i - count), p;
            if (offer && (!(B(entry + 0xB) & 3) || (D(entry + 8) & 0x1C000000u) != 0x0C000000u)) continue;
            p = offer ? D(entry) : D(list + 4 * i);
            if (!p || B(p + 0x35) != 0) continue;
            union { float f; u32 u; } v;
            v.f = RATING(p, 1);
            u32 k = v.u >> 31 ? 0 : v.u;
            if (have && k <= key) continue;
            u32 x = VALUE(p, 0, 0, 1, 0) & 0xFFFFu;
            if (x >= budget) continue;
            best = p, key = k, value = x, pool = offer, have = 1;
        }
        if (!have) return 0;
        if (!pool && healthy(best)) return ovr(best);
        budget = value;
    }
}

/* C24 F3: the seller's best healthy quarterback rating left besides its best man `starter` once `qs` is sold. */
static i32 backup_after(u32 t, u32 starter, u32 qs) {
    i32 top = 0;
    for (u32 j = 0; j < B(t + 0x11C); j++) {
        u32 p = D(t + 4 * j);
        i32 o;
        if (p && p != starter && p != qs && B(p + 0x35) == 0 && healthy(p) && (o = ovr(p)) > top) top = o;
    }
    return top;
}

/* M1/N6 (the trades review's 1.3): the buyer's charge for p once the trade is made. The executor rewrites every moved
   man's contract (0x2BB360, called at 0x2BC733: x = 0xE5FF0(value); x -= 0x13ED00(p); bonus bits 20..23 of +0x24
   cleared; value = 0xE6000(x)) and recounts both payrolls (0xC3F00: this season's charge plus the yearly bonus, which
   is then zero). The same rewrite on a copy of the record, then 0xE6380 of the copy: the game's record is not touched.
   0xE5FF0 and 0xE6000 are arithmetic on their argument; 0x13ED00 and 0xE6380 (with 0xE6020, 0xE6040 and 0xE3F10) read
   only +0xA and +0x24 of the record they are given, never its address, so a copy on the stack prices as the record. */
static u32 charge_after(u32 p) {
    u8 copy[PLAYER_SIZE] __attribute__((aligned(4)));
    u32 c = (u32)copy;
    for (u32 i = 0; i < PLAYER_SIZE; i += 4) D(c + i) = D(p + i);
    u32 x = TIMES10(W(p + 0xA)) - OWED(p);            /* 0x13ED00 with the original record, as the executor calls it */
    D(c + 0x24) &= 0xFF0FFFFFu;
    W(c + 0xA) = (u16)TENTHS(x);
    return SALARY(c);
}

struct club { u32 team, starter, w, l, t, flags; i32 best; };
#define OUT 1u                                           /* no club, human, or named by a live record */
#define SELLER 2u
#define BUYER 4u
#define USED 8u

struct posted { u32 rec, qs, buyer, seller, word; };

/* Decide and post; returns how many records were written (in `out`). */
static u32 post(struct posted *out) {
    u32 count = 0;
    /* The rows still in the room's ring from this and the previous week of this season: an emergency signing (E1, E2
       or the floor; applied, or in shadow would) and a D3 benching in the previous advance's room pass (logged with
       this week, after the previous advance's week increment). */
    u32 year = D(YEAR), week = D(WEEK), signed_mask = 0, benched = 0, n = qb_ring_cursor_plain;
    for (u32 k = 0; k < 128u && k < n; k++) {
        struct event *e = &qb_ring_plain[(n - 1 - k) % 128u];
        u32 decision = e->decision & 15, bit = 1u << (e->club & 31);
        if (e->year != year || e->week + 1u < week || (e->result != APPLIED && e->result != WOULD)) continue;
        if (decision >= 5 && decision <= 7) signed_mask |= bit;
        if (decision == D3 && e->week == week) benched |= bit;
    }
    struct club c[CLUBS];
    for (u32 i = 0; i < CLUBS; i++) {
        struct club *x = &c[i];
        u32 t = x->team = CLUB_AT(i), a = 0, h = 0, m;
        x->flags = OUT;
        x->starter = 0;
        x->best = 0;
        if (!t || D(USER_FLAG + 4 * i) || named(t) || (m = B(t + 0x11C)) > SLOTS) continue;
        for (u32 j = 0; j < m; j++) {
            u32 p = D(t + 4 * j);
            if (!p || B(p + 0x35) != 0) continue;
            a++;
            if (!healthy(p)) continue;
            h++;
            i32 o = ovr(p);
            if (!x->starter || o > x->best) {
                x->starter = p;
                x->best = o;
            }
        }
        x->w = WINS(t);
        x->l = LOSSES(t);
        x->t = TIES(t);
        x->flags = m >= 51 && a >= 3 && h >= 3 ? SELLER : 0;
        /* C22 addendum (1): at most 2 active quarterbacks before the trade, for either need (never 4 after) */
        if (m < 49 || m > 52 || !h || a > 2 || x->w + x->l + x->t < 2 || x->w + 1 < x->l || signed_mask >> i & 1
                || x->best >= STARTER_CAP)                              /* C24 F4 */
            continue;
        if (benched >> i & 1) x->flags = BUYER | NEED_D3;
        else if (lost_starter(i, x->best)) x->flags = BUYER;
    }
    u32 saved = D(STAT_CLASS);
    if (saved) D(STAT_CLASS) = 0;
    for (u32 b = 0; b < CLUBS; b++) {
        struct club *x = &c[b];
        if ((x->flags & (BUYER | USED)) != BUYER) continue;
        qb_counters.trade_buyers++;
        u32 qs = 0, seller = 0, word = 0, result = KEPT;
        i32 top = x->best + 2, room = (i32)(D(CAP) - D(x->team + 0x124));
        for (u32 i = 0; i < CLUBS; i++) {
            u32 t = c[i].team;
            if (c[i].flags != SELLER) continue;
            for (u32 j = 0; j < B(t + 0x11C); j++) {
                u32 p = D(t + 4 * j);
                i32 o;
                if (!p || B(p + 0x35) != 0 || !healthy(p) || !(W(p + 0x28) & ROW_MASK) || (B(p + 0x25) & 31) < 4
                        || !(B(p + 0x24) & 15) || (o = ovr(p)) <= top || o >= c[i].best   /* C22 (a) */
                        || room - (i32)charge_after(p) <= 10 || named(p)                 /* M1/N6 */
                        || backup_after(t, c[i].starter, p) < BACKUP_MIN)               /* C24 F3 */
                    continue;
                qs = p;
                top = o;
                seller = i;
            }
        }
        if (!qs) {
            qb_counters.trade_no_package++;
            continue;
        }
        if (free_agent(room) >= top) {                                  /* C24 F5: E1/E2 sign him instead */
            qb_counters.trade_free_agent++;
            goto log;
        }
        /* C24 price: 2nd at 95+, 3rd at 90-94, 4th 82-89, 5th 76-81, 6th 70-75, 7th below; not owned: the round just
           before it (C24 N1: at most one round earlier), never a later one; neither: no trade */
        u32 ruled = top >= 95 ? 2 : top >= 90 ? 3 : top >= 82 ? 4 : top >= 76 ? 5 : top >= 70 ? 6 : 7;
        for (u32 round = ruled; round >= 1 && round + 1 >= ruled && !word; round--)
            if (B(PICKS + 32 * round + b) == b) word = round | b << 6;
        if (!word) {
            qb_counters.trade_no_pick++;
            goto log;
        }
        u32 key[9] = {TRADE_EVENT, b, year, x->w, x->l, x->t, index_of(qs), (u32)SEASON_STAT(x->starter, 6),
                      (u32)SEASON_STAT(x->starter, 8)}, hash = 0x51425233u;
        for (u32 i = 0; i < 9; i++) {
            hash ^= key[i];
            hash ^= hash >> 16; hash *= 0x85EBCA6Bu; hash ^= hash >> 13; hash *= 0xC2B2AE35u; hash ^= hash >> 16;
        }
        if (hash % 100000u >= POST_P) {
            qb_counters.trade_kept++;
            goto log;
        }
        u32 offer[15];
        for (u32 i = 0; i < 15; i++) offer[i] = 0;
        offer[0] = 2;
        offer[2] = c[seller].team;
        offer[3] = qs;
        offer[8] = x->team;
        offer[12] = word;
        if (!evaluate(offer)) {
            qb_counters.trade_refused++;
            result = REFUSED;
            goto log;
        }
        u32 slot = 1;
        while (slot < 15 && D(BOARD + RECORD * slot)) slot++;
        if (slot == 15) {
            qb_counters.trade_no_slot++;
            goto log;
        }
        x->flags |= USED;
        c[seller].flags |= USED;
        result = WOULD;
        if ((qb_settings_plain.flags | qb_trade_flags) & FLAG_SHADOW) {
            qb_counters.trade_shadow++;
            goto log;
        }
        u32 rec = BOARD + RECORD * slot;
        for (u32 i = 1; i < 13; i++) D(rec + 4 * i) = offer[i];
        W(rec + 0x34) = 0;
        D(rec) = 2;                                      /* kind last */
        out[count].rec = rec;
        out[count].qs = qs;
        out[count].buyer = b;
        out[count].seller = seller;
        out[count++].word = word;
        qb_counters.trades_posted++;
        result = APPLIED;
log:
        row(b, TRADE_EVENT | (x->flags & NEED_D3), result, qs, x->starter, (i32)(x->l - x->w), x->w + x->l + x->t, word,
            top - x->best, seller);
    }
    if (saved) D(STAT_CLASS) = saved;
    return count;
}

/* The native trade pass with 4b around it (trade_entry, at 0x247E1E): post, run 0x2BC960 as the site would, then clear
   up: every record of ours still there (kind 2 with A's first player the man we named: a slot our executed record freed
   may hold a native record by now) is cancelled with 0x2BB660(rec, 0, 1, 1), as the game's own pre-sweep does. */
void __attribute__((noinline, cdecl)) trade_call(u32 proposers, u32 menu) {
    struct posted done[14];
    u32 count = 0;
    qb_counters.trade_calls++;
    if (qb_settings_plain.magic[0] == 0x4F524251u && qb_settings_plain.magic[1] == 0x31764D4Fu
            && qb_settings_plain.mode == 1 && (qb_settings_plain.stages & STAGE_TRADE) && D(LEAGUE_ROOT)) {
        if (D(STAGE) != 8) qb_counters.trade_inactive++;
        else if (D(WEEK) >= B(DEADLINE_WEEK)) qb_counters.trade_past_deadline++;     /* C22 (c) */
        else count = post(done);
    }
    NATIVE_PASS(proposers, menu);
    for (u32 i = 0; i < count; i++) {
        struct posted *x = &done[i];
        u32 result = 0;
        if (D(x->rec) == 2 && D(x->rec + 0xC) == x->qs) {
            CANCEL(x->rec, 0, 1, 1);
            qb_counters.trades_cancelled++;
            result = CANCELLED;
        } else if (listed(CLUB_AT(x->buyer), x->qs)) {
            qb_counters.trades_executed++;
            result = APPLIED;
        } else {
            qb_counters.trades_gone++;
        }
        row(x->buyer, TRADE_EVENT | AFTER, result, x->qs, 0, 0, 0, x->word, 0, x->seller);
    }
}
