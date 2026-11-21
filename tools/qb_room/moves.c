/* Quarterback room, stage 4a (beta 81 piece 4): emergency quarterback signings (DESIGN.md 4.1), and the floor
   (DESIGN addendum F1 to F8, stage bit 64): a club with no healthy quarterback gets one before every game week.

   Entry: sign_after (entry.S, section .text.sign) after the game's own weekly signings 0x323870 return, once per
   weekly advance, with the menu that 0x248010 passed in ECX. Stage bit 8 gates the pass and E1; E2 needs bit 32 too.
   League stage 8 only. Linked after room.c's code and tables, so piece 3's bytes do not move.

   For each league club 0..31 that is not a user's (C21 rule 5; the floor below still serves a user's club with auto
   sign/cut [0xE6013C] = 1, F4):
   A = quarterbacks on the active list, H = the healthy ones, S' = the best-rated healthy one.
   - E1: H <= 1 and A <= 2. Sign (probability 1).
   - E2: A <= 2, a quarterback L on this club's injured reserve (the IR owner's live store, linked at page + 0x2020)
     with ovr(L) - ovr(S') >= 3 and 3 or more weeks left or flagged out for the season, and the candidate F has
     ovr(F) - ovr(S') >= 2. Sign with probability 0.5 (key: 6, club, year, W, L, T, F index, S' attempts, yards).
   The candidate F: the best-rated healthy free-agent quarterback such that the native picker 0x322BB0, given
   budget = value(F) + 1, takes F and nobody else (simulated exactly over both of its pools, below), and cap room
   minus 10 (the economy gate's cap on the budget) is above value(F); else the next healthy one down; else nothing.
   Acts, only once F is known and not in shadow: at exactly 53 (stage 8 only, so 53 is the most it can be) one
   protected release (C21: protected_release below; never a star, a row 0 man, a QB, K or P, or a man his position
   needs; nobody eligible: no signing this week, sign_skip_protected), then the recount, the pool collected again and
   F chosen again (C11: the release reprices the market, below; nobody: sign_room_lost); then 0x322BB0(club, 0,
   value(F) + 1, menu). One quarterback per club per pass; A <= 2 keeps the active list at 3 or fewer.

   Game routines (retail and standard disassembly, see the test file):
   - 0x322BB0 n_cpu_sign(team, position, budget, menu): stdcall, ret 0x10, returns 0 when nobody is signed. It keeps
     the player with the strictly highest 0x246D80(p, 1) at the position whose value (AX of 0x2BD440) is below the
     budget's low 16 bits, scanning the free-agent list ([root + 0x38]: count, array) and then the offer table
     0xE3C600 (100 x 16 bytes; an entry counts when byte +0xB & 3 and bits 26..28 of dword +8 are 3; player at +0).
     No injury test. On standard its entry jumps to the practice-squad guard and the economy gate first.
   - 0x2BD440 value: ECX = player, EDX = 0, stack 0, 1, 0 (callee pops 12), value in AX. On 9f435b38 it is a market
     price: for an unsigned prove-it man (no contract years, +0x25 > 0x3F) min(base, the best bidder's room - 10),
     the best bidder found by 0x3D2890 over every CPU club (need at the position, economy cap - payroll - 10). A
     club's own cut, restructure or release changes its room and so the price: every choice here is made on a pool
     collected after the last such step (C11; P2a 2502/2027).
   - 0x2BF9A0 cut-down (standard: the economy's smart cut): fastcall ECX = club, EDX = target, plain ret. Called by
     E1/E2 until C21 (it released a 95-rated guard for a backup quarterback in P5-r3); no longer called here.
   - 0xC3F00 payroll recount: fastcall ECX = club (club + 0x124 = payroll). */
#include "room.h"

/* moves.c is the only writer of its counters and ring rows and nothing runs concurrently with a pass, so plain
   (non-volatile) accesses are exact here; every call into the game is a compiler barrier for memory, so values are
   reloaded after it. This keeps stage 4a and the floor inside the code region (room.c keeps its volatile accesses). */
#undef B
#undef W
#undef D
#define B(a) (*(u8 *)(a))
#define W(a) (*(u16 *)(a))
#define D(a) (*(u32 *)(a))
extern struct counters qb_counters_plain;              /* page + 0x2040 as well (build.py): plain accesses */
extern u32 qb_ring_cursor_plain;                       /* page + 0x2E00 as well */
#define qb_counters qb_counters_plain
#define qb_ring_cursor qb_ring_cursor_plain
extern u32 qb_seen_healthy;                            /* page + 0x2E08 (RAM only): clubs with H >= 1 this advance */

#define VALUE ((u32 (FC *)(u32, u32, u32, u32, u32))0x002BD440)
#define SIGN ((u32 (__attribute__((stdcall)) *)(u32, u32, u32, u32))0x00322BB0)
#define RECOUNT ((void (FC *)(u32))0x000C3F00)
#define RELEASE ((void (FC *)(u32, u32, u32, u32))0x002BD900)      /* club, player, to the list, log: ret 8 */
#define SALARY ((u32 (FC *)(u32))0x000E6380)                         /* this season's base charge (fastcall ECX) */
#define RESTRUCTURE ((i32 (FC *)(u32, u32))0x003B9F60)             /* economy_restructure(player, apply) */

#define AUTO_SIGN 0x00E6013Cu        /* "CPU signs and cuts for my club" */
#define CAP 0x00E3C278u              /* the league cap, game thousands */
#define OFFERS 0x00E3C600u
#define OFFER_COUNT 100u
#define E1 5u
#define E2 6u
#define FLOOR_EVENT 7u
#define NO_FIT 6u                    /* ring result: no free agent fits after every restructure and release */
#define LOST_SINCE 0x10u             /* floor ring decision bit: the club had a healthy QB earlier in this advance */
#define IR_MAGIC 0x52493236u         /* "62IR", struct store in tools/injured_reserve/runtime.c */
#define IR_CLUBS 0x40u               /* offset of store.c[] */
#define IR_CLUB_SIZE 0xA4u           /* u8 n, u8 returns, u8 pad[2], 20 x {player, i16 base, u8 flags, u8 how} */
#define IR_CAP 20u
#define F_SEASON 1u

struct pick { u32 p, key, value, pool; };

static u32 fmix32(u32 h) { h ^= h >> 16; h *= 0x85EBCA6Bu; h ^= h >> 13; h *= 0xC2B2AE35u; h ^= h >> 16; return h; }
static u32 draw(const u32 *w, u32 n) { u32 h = 0x51425233u; for (u32 i = 0; i < n; i++) h = fmix32(h ^ w[i]); return h % 100000u; }

static int fully_healthy(u32 p) {
    return !(D(p + 0x20) & (INJURED | WEEKS_MASK)) && !(D(p + 0x24) & 0x70000000u);
}

/* The rating as the picker compares it (a float in 0..1 compared on its bits: for non-negative floats the order of
   the bits is the order of the values; -0.0 equals 0.0), and the whole-point overall of room.c. */
static u32 rating_key(u32 p) {
    union { float f; u32 u; } v;
    v.f = RATING(p, 1);
    return v.u >> 31 ? 0 : v.u;
}

static __attribute__((section(".text.mid"))) i32 overall_of(u32 key) {   /* C21: moved to the middle piece */
    u32 e = (key >> 23) & 255;
    if (e < 119) return 0;
    if (e > 127) return 100;
    u32 s = 150 - e;
    return (i32)((((key & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s);
}

/* Cap room as economy_fill_room computes it after its recount: economy_cap(team, 1, 0) - payroll. */
static i32 room_of(u32 team, u32 index) {
    u32 cap = D(CAP), used = 0;
    if (D(USER_FLAG + 4 * index)) used = W(team + 0x19C);
    if (used == 0xFFFFu || used >= cap) cap = 0;
    else cap -= used;
    return (i32)cap - (i32)D(team + 0x124);
}

/* A (quarterbacks on the active list), H (the healthy ones) and S' (the best-rated healthy one, with its key). */
static u32 scan(u32 team, u32 *healthy, u32 *starter, u32 *best) {
    u32 a = 0, h = 0, s = 0, k = 0;
    for (u32 i = 0; i < B(team + 0x11C); i++) {
        u32 p = D(team + 4 * i);
        if (!p || B(p + 0x35) != 0) continue;
        a++;
        if (!fully_healthy(p)) continue;
        h++;
        u32 key = rating_key(p);
        if (!s || key > k) {
            s = p;
            k = key;
        }
    }
    *healthy = h;
    *starter = s;
    *best = k;
    return a;
}

static __attribute__((noinline)) int listed(u32 team, u32 p) {
    for (u32 i = 0; i < B(team + 0x11C); i++)
        if (D(team + 4 * i) == p) return 1;
    return 0;
}

/* The man 0x322BB0 takes for `budget`, asked as the picker asks it, in one pass and with nothing stored (P5: from
   2029/2030 the free-agent list holds more quarterbacks than 66d8a7e1b's 64-entry pool, and every act gave up): in its
   scan order (the free-agent list [root + 0x38]: count, array; then the counted entries of the offer table 0xE3C600),
   the first quarterback with a strictly higher rating than the best so far whose value (AX of 0x2BD440, called exactly
   as the picker calls it and only when the rating is higher, as the picker does) is below the budget. 0 when nobody. */
static __attribute__((noinline)) u32 pick_at(struct pick *out, u32 budget) {
    u32 have = 0, root = D(LEAGUE_ROOT), count = D(root + 0x38), list = D(root + 0x3C);
    for (u32 i = 0; i < count + OFFER_COUNT; i++) {
        u32 offer = i >= count, entry = OFFERS + 16 * (i - count), p;
        if (offer && (!(B(entry + 0xB) & 3) || (D(entry + 8) & 0x1C000000u) != 0x0C000000u)) continue;
        p = offer ? D(entry) : D(list + 4 * i);
        if (!p || B(p + 0x35) != 0) continue;
        u32 key = rating_key(p);
        if (have && key <= out->key) continue;
        u32 value = VALUE(p, 0, 0, 1, 0) & 0xFFFFu;
        if (value >= budget) continue;
        out->p = p;
        out->key = key;
        out->value = value;
        out->pool = offer;
        have = 1;
    }
    return have;
}

/* The candidate (DESIGN 4.1, F3 step 4): the best-rated healthy free agent on the list whom the picker takes at his
   value + 1 and nobody else, valued below room minus 10. The picker's own man at budget room - 10 is the best such
   man unless he is hurt or on the offer table; any other must be valued below him (else the picker would prefer him),
   so ask again at his value. The budget falls strictly, so the asks end. Exactly what choosing over the whole pool
   gave, for a list of any length. */
static __attribute__((noinline)) u32 choose(struct pick *out, i32 room) {
    if (room <= 10) return 0;
    u32 budget = room - 10 > 0xFFFF ? 0xFFFFu : (u32)(room - 10);
    while (pick_at(out, budget)) {
        if (!out->pool && fully_healthy(out->p)) return 1;
        budget = out->value;
    }
    return 0;
}

/* Is any free agent on the list a healthy quarterback (F3 step 1)? */
static __attribute__((noinline)) u32 any_healthy_free_agent(void) {
    u32 root = D(LEAGUE_ROOT), count = D(root + 0x38), list = D(root + 0x3C);
    for (u32 i = 0; i < count; i++) {
        u32 p = D(list + 4 * i);
        if (p && B(p + 0x35) == 0 && fully_healthy(p)) return 1;
    }
    return 0;
}

/* E2's injured-reserve test: a quarterback on this club's IR, 3 or more better than S', out 3 weeks or more or for
   the season. -1 when the store is not linked. */
static i32 long_starter(u32 index, i32 best) {
    u32 store = qb_link_ir_store;
    if (!store || D(store) != IR_MAGIC) return -1;
    u32 club = store + IR_CLUBS + IR_CLUB_SIZE * index, n = B(club);
    if (n > IR_CAP) n = IR_CAP;
    for (u32 i = 0; i < n; i++) {
        u32 entry = club + 4 + 8 * i, p = D(entry);
        if (!p || B(p + 0x35) != 0 || overall_of(rating_key(p)) - best < 3) continue;
        if ((B(entry + 6) & F_SEASON) || ((D(p + 0x20) >> 22) & 255) >= 3) return 1;
    }
    return 0;
}

/* One ring row (INTERFACE.md). a and b are player records (0: none); r10 is clamped to 0..65535. In the tail piece
   (page + 0x2E10, build.py). */
static __attribute__((noinline, section(".text.tail"))) void put(u32 index, u32 decision, u32 result, u32 a, u32 b, u32 d, u32 g, i32 r10, u32 gap, u32 coach,
                u32 threshold) {
    u32 n = qb_ring_cursor, table = D(D(LEAGUE_ROOT) + 4);
    union { struct event e; u32 w[5]; } row;
    row.e.year = (u16)D(YEAR);
    row.e.week = (u8)D(WEEK);
    row.e.club = (u8)index;
    row.e.decision = (u8)decision;
    row.e.result = (u8)result;
    row.e.a = a ? (u16)((a - table) / PLAYER_SIZE) : 0xFFFFu;
    row.e.b = b ? (u16)((b - table) / PLAYER_SIZE) : 0xFFFFu;
    row.e.d = (i8)d;
    row.e.g = (u8)g;
    row.e.rating10 = (u16)(r10 < 0 ? 0 : r10 > 65535 ? 65535 : r10);
    row.e.gap = (i8)gap;
    row.e.coach = (u8)coach;
    row.e.threshold = threshold;
    u32 *to = (u32 *)&qb_ring[n % 128u];
    for (u32 k = 0; k < 5; k++) to[k] = row.w[k];
    qb_ring_cursor = n + 1;
    qb_counters.events_logged++;
}

/* The fewest a club keeps at each position (the economy's cut_min, 2024 53-man rosters): QB 2, K 1, P 1, WR 5,
   CB 5, FS 2, SS 2, HB 3, FB 0, TE 3, OLB and ILB 5 together (either scheme), C 2, G 3, T 3, DT 3, DE 4. */
static const u8 floor_min[17] = {2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4};

/* C21 (coordinator's ruling, 11/20): E1's and E2's make-room release. The man released must be, all at once, (a) one
   of the club's ten lowest-rated players leaving out QB, K and P (fewer than ten of them rate strictly lower), (b)
   not first (row 0) at his position, and (c) a man whose position keeps at least its minimum of healthy players
   without him (floor_min, OLB and ILB as one pool). Injured or healthy makes no difference, so the rating is the
   game's 0x246D80 with flag 0: with flag 1 (the page's other ratings) an injured man is discounted (a hurt 90 CB
   rates 63), and the hurt stars the smart cut released (every 90+ cut in P5-r3 and P5-E2) would rate low here. The
   lowest-rated man meeting (b) and (c) is the only one that can meet (a) as well; he goes by the native release
   0x2BD900. Nobody: 0, and E1/E2 sign nobody this week. The floor's release_one is untouched. */
static __attribute__((noinline)) u32 unhurt_key(u32 p) {
    union { float f; u32 u; } v;
    v.f = RATING(p, 0);                             /* flag 0: no injury discount (healthy men: equal to flag 1) */
    return v.u >> 31 ? 0 : v.u;
}

static __attribute__((noinline)) u32 protected_release(u32 team) {
    u8 fit[17] = {0};
    u32 n = B(team + 0x11C), best = 0, best_key = 0, lower = 0;
    for (u32 i = 0; i < n; i++) {
        u32 p = D(team + 4 * i), pos = B(p + 0x35);
        if (pos > 16) continue;
        if (pos == 10) pos = 11;
        fit[pos] += fully_healthy(p);
    }
    for (u32 i = 0; i < n; i++) {                  /* the lowest-rated man meeting (b) and (c) */
        u32 p = D(team + 4 * i), pos = B(p + 0x35), key;
        if (pos < 3 || pos > 16 || !(W(p + 0x28) & ROW_MASK)) continue;
        if (pos == 10) pos = 11;
        if (fit[pos] - fully_healthy(p) < floor_min[pos]) continue;
        key = unhurt_key(p);
        if (!best || key < best_key) {
            best = p;
            best_key = key;
        }
    }
    if (!best) return 0;
    for (u32 i = 0; i < n; i++) {                  /* (a): any other man meeting (b) and (c) rates at least as high */
        u32 p = D(team + 4 * i);
        if (B(p + 0x35) >= 3 && B(p + 0x35) <= 16) lower += unhurt_key(p) < best_key;
    }
    if (lower >= 10) return 0;
    RELEASE(team, best, 1, 1);
    return !listed(team, best);
}

/* ---- E1 and E2 (DESIGN 4.1) ---------------------------------------------------------------------------------- */
static void club_signing(u32 menu, u32 shadow, u32 index, u32 stages) {
    u32 team = CLUB_AT(index), h, starter, best;
    if (!team) return;
    if (D(USER_FLAG + 4 * index)) {                /* C21 rule 5: never a user's club (the floor keeps F4) */
        qb_counters.sign_skip_human++;
        return;
    }
    if (B(team + 0x11C) > SLOTS || scan(team, &h, &starter, &best) > 2) return;
    i32 starter_ovr = starter ? overall_of(best) : 0;
    u32 decision = 0;
    if (h <= 1) {
        decision = E1;
    } else if (stages & STAGE_E2) {
        i32 ir = long_starter(index, starter_ovr);
        if (ir < 0) qb_counters.sign_ir_unlinked++;
        if (ir > 0) decision = E2;
    }
    if (!decision) return;
    struct pick fp;
    if (!shadow) RECOUNT(team);                     /* the gate recounts before its room test; so does this */
    const struct pick *f = choose(&fp, room_of(team, index)) ? &fp : 0;
    u32 w = WINS(team), l = LOSSES(team), t = TIES(team), threshold = decision == E1 ? 100000u : 50000u;
    u32 d = l - w, g = w + l + t, gap = f ? (u32)(overall_of(f->key) - starter_ovr) : 0, result = KEPT;
    if (decision == E2) {
        if (!f || (i32)gap < 2) return;             /* the market has nothing better: no need */
        qb_counters.e2_tried++;
        u32 saved = D(STAT_CLASS);
        if (saved) D(STAT_CLASS) = 0;
        u32 att = (u32)SEASON_STAT(starter, 6), yds = (u32)SEASON_STAT(starter, 8);
        if (saved) D(STAT_CLASS) = saved;
        u32 key[9] = {E2, index, D(YEAR), w, l, t, (f->p - D(D(LEAGUE_ROOT) + 4)) / PLAYER_SIZE, att, yds};
        qb_counters.e2_drawn++;
        if (draw(key, 9) >= 50000u) {
            qb_counters.e2_kept++;
            goto log;
        }
    } else {
        qb_counters.e1_tried++;
        if (!f) {
            qb_counters.sign_no_candidate++;
            goto log;
        }
    }
    if (shadow) {
        qb_counters.sign_shadow++;
        result = WOULD;
        goto log;
    }
    if (B(team + 0x11C) == 53) {
        if (!protected_release(team)) {            /* C21 rule 3: nobody may go: no signing this week */
            qb_counters.sign_skip_protected++;
            goto log;
        }
        qb_counters.sign_cuts++;
        RECOUNT(team);                              /* C11: the cut reprices the market; choose again */
        if (!choose(&fp, room_of(team, index))) {
            f = 0;
            qb_counters.sign_room_lost++;
            goto log;
        }
    }
    if (SIGN(team, 0, f->value + 1, menu)) {
        result = APPLIED;
        if (decision == E1) qb_counters.e1_done++;
        else qb_counters.e2_done++;
    } else {
        qb_counters.sign_failed++;
    }
log:
    put(index, decision, result, starter, f ? f->p : 0, d, g, 0, gap, 0, threshold);
}

/* ---- The floor (DESIGN addendum F1 to F8, stage bit 64): a club the CPU signs for with no healthy quarterback on its
   active list (H = 0) gets one. Pre-game (pregame_entry, after the IR pass 0x2BE020 returns, stages 7 to 9, every club)
   and post-game (this pass, after E1, when A <= 2). F3's steps, in order:
    1 no healthy free-agent quarterback in the picker's pools: stop, count, sign nobody;
    2 pre-game only, while A >= 3: release the lowest-rated (injured) quarterback with the native release
      0x2BD900(club, p, 1, 1); if he is still listed, stop: never a fourth;
    3 at exactly 53 active: the smart cut 0x2BF9A0(club, 52), one player;
    4 the candidate rule of E1 (best healthy man the picker takes within room minus 10): the gated signing;
    5 else the target T: the cheapest healthy prove-it free agent (no contract years, 2+ unsigned weeks; ties to the
      higher rating), else the cheapest healthy one, that the picker takes at value(T) + 1;
    6 while room minus 10 is not above value(T), up to 3: restructure the contract with the largest dry-run saving
      above 250 (economy_restructure 0x3B9F60, as restructure_best) and recount;
    7 while still short and 51+ active, up to 2: 0x2BF9A0(club, count - 1) and recount;
    8 (C11) recount, collect again, step 4's rule on the fresh pool: the gated signing of that man (rung 2); else
      the target chosen again on the fresh pool and, with 52 or fewer active and bit 128 set, the native signing
      entered past its gates (sign_ungated: sub esp,0x114; jmp 0x322BB6), result code 5 "signed over the cap".
      Steps 4 and 5 also run on a pool collected after step 3's cut;
    9 pre-game only: seat him (floor_seat);
   10 H >= 1, else floor_failed.
   Stage 7 (camp; the coordinator's rule, 2026-11-20): steps 1, 4, 9 and 10 only. No release of any kind (no swap, no
   cut, no release rung), no restructure, no over-cap signing; with no candidate within room minus 10, floor_no_room
   and stop. The gates decide the plain signing (the economy gate refuses at 54+ active, the practice-squad guard at
   65 minus the reserves); the native cut to 53 then runs and the first stage 8 pre-game call does the full floor.
   P2a 2502/2027: 61472f79c cut at >= 53, so a camp roster went down to 52 in one call and the signing still failed.
   Ring row: decision 7, a = the injured man released (step 2), b = the man signed (or T), d = restructures,
   g = releases, rating10 = room at the start (clamped 0..65535), gap = rung (1 candidate, 2 gated after 6-7,
   3 over the cap), coach = swaps, threshold = value(F or T). */
static u32 restructure_once(u32 team) {
    u32 best = 0;
    i32 most = 250;
    for (u32 i = 0; i < B(team + 0x11C); i++) {
        u32 p = D(team + 4 * i);
        i32 saving = p ? RESTRUCTURE(p, 0) : 0;
        if (saving > most) {
            most = saving;
            best = p;
        }
    }
    if (best) RESTRUCTURE(best, 1);
    return best;
}

/* F3 step 9: the new man on row 0, the others one row down in their old order, rank and side locks (bits 0 and 1 of
   +0x52) cleared on each injured man moved down; no lock on the new man. Exported for TF7. */
void __attribute__((noinline, cdecl)) floor_seat(u32 team, u32 newman) {
    u32 slots = B(team + 0x11C), order[8], n = 0;
    for (u32 row = 0; row < 8; row++)                  /* the old order first, then the new rows */
        for (u32 i = 0; i < slots && n < 8; i++) {
            u32 p = D(team + 4 * i);
            if (p && p != newman && B(p + 0x35) == 0 && ((W(p + 0x28) >> 10) & 7) == row) order[n++] = p;
        }
    for (u32 k = 0; k < n; k++) {
        u32 p = order[k];
        W(p + 0x28) = (W(p + 0x28) & ~ROW_MASK) | (k < 6 ? k + 1 : 7) << 10;
        if (!fully_healthy(p)) B(p + 0x52) &= ~3u;
    }
    W(newman + 0x28) &= ~ROW_MASK;
    qb_counters.floor_seated++;
}

/* Make room by one release (floor review F1(b), F5): the lowest-valued healthy player at a position that keeps at
   least its minimum of healthy players without him; an injured one (at a position above its minimum) only when no
   such healthy man exists. A quarterback is never taken while he is the club's only healthy one (the floor acts at
   H = 0 after the swap leaves one hurt quarterback, below the minimum of 2, so none is eligible). With `room` set (the
   make-room releases, not the cut at 53) a player the recount charges nothing is skipped: no contract years left, or
   a zero base charge 0xE6380 (the economy's trim skips them the same way; re-check R-F1). Returns 0 when nobody is
   eligible or the release did not take: the bound on releases per act is the club's players above the minimums. */
static __attribute__((noinline)) u32 release_one(u32 team, u32 room) {
    u8 all[17] = {0}, fit[17] = {0};
    u32 n = B(team + 0x11C), best = 0, best_key = 0;
    for (u32 i = 0; i < n; i++) {
        u32 p = D(team + 4 * i), pos = B(p + 0x35);
        if (pos > 16) continue;
        if (pos == 10) pos = 11;                       /* OLB and ILB as one pool */
        all[pos]++;
        fit[pos] += fully_healthy(p);
    }
    for (u32 i = 0; i < n; i++) {
        u32 p = D(team + 4 * i), pos = B(p + 0x35);
        if (pos > 16) continue;
        if (pos == 10) pos = 11;
        u32 healthy = fully_healthy(p);
        if (healthy ? fit[pos] <= floor_min[pos] : all[pos] <= floor_min[pos]) continue;
        if (room && (!(B(p + 0x24) & 15) || !SALARY(p))) continue;            /* frees no cap room */
        u32 key = (healthy ? 0 : 0x10000u) | (VALUE(p, 0, 0, 1, 0) & 0xFFFFu);  /* healthy first, then the value */
        if (!best || key < best_key) {
            best = p;
            best_key = key;
        }
    }
    if (!best) return 0;
    RELEASE(team, best, 1, 1);
    return !listed(team, best);
}

/* Floor review F6: does the club have a next game? The validator's rule (tools/franchise_invariants.py,
   next_game_state), so the floor and I11 agree: an unplayed schedule cell (0xE57C40, 22 x 17 cells of 8 bytes: kind 0,
   not all of home, away and month 0) naming the club on a known side: a regular-season row in stage 8 (row below the
   stage's week count [0xE576B0]), or a side whose flag byte is set (0xE57954, u16 a cell: low byte home, high byte
   away; the playoff bracket's unknown sides carry team 0 and flag 0). In stage 8 with every regular-season cell played
   the bracket is not built yet (it appears at the 8 -> 9 stage advance), so every club counts. A club on its bye
   has one. */
static __attribute__((noinline)) u32 next_game(u32 index) {
    u32 stage = D(STAGE), weeks = D(0x00E576B0u), regular_left = 0;
    for (u32 i = 0; i < 22u * 17u; i++) {
        u32 cell = 0x00E57C40u + 8 * i, side = W(0x00E57954u + 2 * i);
        if (B(cell) || !(B(cell + 1) | B(cell + 2) | B(cell + 3))) continue;
        u32 regular = stage == 8 && i / 17u < weeks;
        regular_left |= regular;
        if ((B(cell + 1) == index && (regular || (side & 0xFFu))) || (B(cell + 2) == index && (regular || side >> 8)))
            return 1;
    }
    return stage == 8 && !regular_left;
}

/* The floor (DESIGN addendum F3, floor review F1 to F6). One act per club per point (0 post-game, 1 pre-game, 2 the end
   of the weekly advance, 3 the end of the stage advance). `stages` is 0 in camp. */
static void floor_club(u32 shadow, u32 stages, u32 index, u32 point, u32 menu) {
    u32 team = CLUB_AT(index), h, s, k, bit = 1u << index;
    if (!team || B(team + 0x11C) > SLOTS || (D(USER_FLAG + 4 * index) && D(AUTO_SIGN) != 1)) return;
    u32 a = scan(team, &h, &s, &k);
    if (h) {
        qb_seen_healthy |= bit;                        /* (6): it had one at this point of this advance */
        return;
    }
    if (stages && !next_game(index)) {                 /* F6: eliminated, or the season over (stages 8 and 9) */
        qb_counters.floor_no_game++;
        return;
    }
    u32 lost = qb_seen_healthy & bit ? LOST_SINCE : 0;
    qb_counters.floor_runs++;
    if (lost) qb_counters.floor_lost_since++;
    struct pick fp;
    const struct pick *f = 0;
    u32 out = 0, swaps = 0, restructures = 0, releases = 0, result = KEPT;
    i32 room = room_of(team, index);
    if (!any_healthy_free_agent()) {                                  /* 1 */
        qb_counters.floor_no_free_agent++;
        goto done;
    }
    if (shadow) {
        qb_counters.floor_shadow++;
        result = WOULD;
        goto log;
    }
    while (stages && a >= 2) {          /* 2 (F1(c)): the new man is one of two, which the economy's trim keeps */
        u32 worst = 0, low = 0;
        for (u32 i = 0; i < B(team + 0x11C); i++) {
            u32 p = D(team + 4 * i);
            if (!p || B(p + 0x35) != 0) continue;
            u32 key = rating_key(p);
            if (!worst || key <= low) {
                worst = p;
                low = key;
            }
        }
        RELEASE(team, worst, 1, 1);
        if (listed(team, worst)) {
            qb_counters.floor_swap_stuck++;
            goto done;
        }
        out = worst;
        swaps++;
        qb_counters.floor_swaps++;
        a--;
    }
    if (stages && B(team + 0x11C) == 53 && release_one(team, 0)) qb_counters.floor_cuts++;       /* 3 */
    for (;;) {                          /* C11 and F1(b): choose on the pool as it stands; make room until he fits */
        RECOUNT(team);
        if (choose(&fp, room_of(team, index))) {                     /* 4: the gated signing fits */
            f = &fp;
            break;
        }
        if (!stages) {                                                /* camp: rung 1 only */
            qb_counters.floor_no_room++;
            goto done;
        }
        if (restructures < 3 && restructure_once(team)) {             /* 6 */
            restructures++;
            qb_counters.floor_restructures++;
        } else if (release_one(team, 1)) {                            /* 7, bounded by the minimums */
            if (releases++) qb_counters.floor_extra_releases++;
            qb_counters.floor_releases++;
        } else {
            qb_counters.floor_no_fit++;                               /* (2): the named failure, nothing further */
            result = NO_FIT;
            goto done;
        }
    }
    if (restructures || releases) qb_counters.floor_gated++;
    else qb_counters.floor_candidate++;
    if (SIGN(team, 0, f->value + 1, menu) && listed(team, f->p)) {
        u32 p = f->p;                                                 /* F3: the one-year prove-it contract */
        W(p + 0xA) = (u16)((f->value + 9u) / 10u);
        B(p + 0x24) = (B(p + 0x24) & 0xF0u) | 1u;
        B(p + 0x27) = (B(p + 0x27) & 0xF0u) | 1u;
        B(p + 0x26) = 2;
        RECOUNT(team);
        result = APPLIED;
        if (room_of(team, index) < 0) qb_counters.floor_over_cap++;  /* never expected: the gate checked the room */
        if (point && (!D(USER_FLAG + 4 * index) || D(CPU_DEPTH))) floor_seat(team, p);     /* 9, F4 */
        else if (point) qb_counters.floor_unseated++;
    } else {
        qb_counters.floor_sign_failed++;
    }
done:
    scan(team, &h, &s, &k);                                           /* 10 */
    if (!h) qb_counters.floor_failed++;
log:
    put(index, FLOOR_EVENT | (stages ? 0 : PRESEASON) | lost, result, out, f ? f->p : 0, restructures, releases,
        room, restructures || releases ? 2 : 1, swaps, f ? f->value : 0);
}

/* Four points (floor review F2). Pre-game (pregame_entry, after the IR pass 0x2BE020, point 1): the floor for every
   club; it also keeps the weekly advance's menu (EBP there) in the page's menu slot, since EBP is gone by the end.
   Post-game (sign_after, after the game's own weekly signings 0x323870, point 0): E1 and E2 (bit 8, stage 8), then the
   floor. The end of the weekly advance (end_entry at 0x24807A, after room_pass and the news 0x27EB80, point 2) and
   the end of the stage advance (stage_entry at 0x248687, after both camp cuts to 53 and every stage change, point 3):
   the floor alone, with the kept menu. The floor runs in stages 7 to 9 (bit 64). */
void CDECL emergency_pass(u32 menu, u32 point) {
    if (point == 1) {
        qb_counters.floor_pregame_passes++;
        qb_menu = menu;
    } else if (!point) {
        qb_counters.sign_passes++;
    } else {
        qb_counters.floor_end_passes++;
    }
    if (qb_settings.magic[0] != 0x4F524251u || qb_settings.magic[1] != 0x31764D4Fu || qb_settings.mode != 1) {
        if (!point) qb_counters.passes_bad_settings++;
        return;
    }
    u32 stages = qb_settings.stages, stage = D(STAGE);
    u32 sign = !point && (stages & STAGE_SIGN) && stage == 8;
    u32 floor = (stages & STAGE_FLOOR) && stage >= 7 && stage <= 9;
    if (!point && (stages & STAGE_SIGN) && stage != 8) qb_counters.sign_inactive++;
    if ((!sign && !floor) || !D(LEAGUE_ROOT)) return;
    u32 shadow = qb_settings.flags & FLAG_SHADOW;
    if (point == 1) qb_seen_healthy = 0;              /* the pre-game call opens a weekly advance's points */
    if (stage == 7) stages = 0;                       /* camp: the floor tries rung 1 only, releases nobody */
    for (u32 index = 0; index < CLUBS; index++) {
        if (sign) club_signing(menu, shadow, index, stages);
        if (floor) floor_club(shadow, stages, index, point, menu);
    }
}
