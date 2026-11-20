/* Quarterback room, stage 4a (beta 81 piece 4): emergency quarterback signings. DESIGN.md 4.1 is the contract.

   Entry: sign_after (entry.S, section .text.sign) after the game's own weekly signings 0x323870 return, once per
   weekly advance, with the menu that 0x248010 passed in ECX. Stage bit 8 gates the pass and E1; E2 needs bit 32 too.
   League stage 8 only. Linked after room.c's code and tables, so piece 3's bytes do not move.

   For each league club 0..31 that the game's CPU fill would serve (not human, or auto sign/cut [0xE6013C] = 1):
   A = quarterbacks on the active list, H = the healthy ones, S' = the best-rated healthy one.
   - E1: H <= 1 and A <= 2. Sign (probability 1).
   - E2: A <= 2, a quarterback L on this club's injured reserve (the IR owner's live store, linked at page + 0x2020)
     with ovr(L) - ovr(S') >= 3 and 3 or more weeks left or flagged out for the season, and the candidate F has
     ovr(F) - ovr(S') >= 2. Sign with probability 0.5 (key: 6, club, year, W, L, T, F index, S' attempts, yards).
   The candidate F: the best-rated healthy free-agent quarterback such that the native picker 0x322BB0, given
   budget = value(F) + 1, takes F and nobody else (simulated exactly over both of its pools, below), and cap room
   minus 10 (the economy gate's cap on the budget) is above value(F); else the next healthy one down; else nothing.
   Acts, only once F is known and not in shadow: at 53 the smart cut 0x2BF9A0(club, 52); the room re-checked after
   it; then 0x322BB0(club, 0, value(F) + 1, menu). One quarterback per club per pass; A <= 2 keeps the active list at
   3 or fewer.

   Game routines (retail and standard disassembly, see the test file):
   - 0x322BB0 n_cpu_sign(team, position, budget, menu): stdcall, ret 0x10, returns 0 when nobody is signed. It keeps
     the player with the strictly highest 0x246D80(p, 1) at the position whose value (AX of 0x2BD440) is below the
     budget's low 16 bits, scanning the free-agent list ([root + 0x38]: count, array) and then the offer table
     0xE3C600 (100 x 16 bytes; an entry counts when byte +0xB & 3 and bits 26..28 of dword +8 are 3; player at +0).
     No injury test. On standard its entry jumps to the practice-squad guard and the economy gate first.
   - 0x2BD440 value: ECX = player, EDX = 0, stack 0, 1, 0 (callee pops 12), value in AX.
   - 0x2BF9A0 cut-down (standard: the economy's smart cut): fastcall ECX = club, EDX = target, plain ret.
   - 0xC3F00 payroll recount: fastcall ECX = club (club + 0x124 = payroll). */
#include "room.h"

#define VALUE ((u32 (FC *)(u32, u32, u32, u32, u32))0x002BD440)
#define CUT_TO ((void (FC *)(u32, u32))0x002BF9A0)
#define SIGN ((u32 (__attribute__((stdcall)) *)(u32, u32, u32, u32))0x00322BB0)
#define RECOUNT ((void (FC *)(u32))0x000C3F00)

#define AUTO_SIGN 0x00E6013Cu        /* "CPU signs and cuts for my club" */
#define CAP 0x00E3C278u              /* the league cap, game thousands */
#define OFFERS 0x00E3C600u
#define OFFER_COUNT 100u
#define POOL_MAX 64u
#define E1 5u
#define E2 6u
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

static i32 overall_of(u32 key) {
    u32 e = (key >> 23) & 255;
    if (e < 119) return 0;
    if (e > 127) return 100;
    u32 s = 150 - e;
    return (i32)((((key & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s);
}

static u32 value_of(u32 p) {
    return VALUE(p, 0, 0, 1, 0) & 0xFFFFu;          /* exactly as 0x322BB0 calls it */
}

/* Cap room as economy_fill_room computes it after its recount: economy_cap(team, 1, 0) - payroll. */
static i32 room_of(u32 team, u32 index) {
    u32 cap = D(CAP), used = 0;
    if (D(USER_FLAG + 4 * index)) used = W(team + 0x19C);
    if (used == 0xFFFFu || used >= cap) cap = 0;
    else cap -= used;
    return (i32)cap - (i32)D(team + 0x124);
}

/* Every quarterback the native picker can see: the free-agent list, then the counted entries of the offer table. */
static u32 collect(struct pick *pool) {
    u32 n = 0, root = D(LEAGUE_ROOT);
    u32 count = D(root + 0x38), list = D(root + 0x3C);
    for (u32 i = 0; i < count; i++) {
        u32 p = D(list + 4 * i);
        if (!p || B(p + 0x35) != 0) continue;
        if (n == POOL_MAX) return POOL_MAX + 1;
        pool[n].p = p;
        pool[n].pool = 0;
        pool[n].key = rating_key(p);
        pool[n++].value = value_of(p);
    }
    for (u32 i = 0; i < OFFER_COUNT; i++) {
        u32 entry = OFFERS + 16 * i, p = D(entry);
        if (!(B(entry + 0xB) & 3) || (D(entry + 8) & 0x1C000000u) != 0x0C000000u || !p || B(p + 0x35) != 0) continue;
        if (n == POOL_MAX) return POOL_MAX + 1;
        pool[n].p = p;
        pool[n].pool = 1;
        pool[n].key = rating_key(p);
        pool[n++].value = value_of(p);
    }
    return n;
}

/* The player 0x322BB0 takes for `budget`: in scan order, a strictly higher rating with value below the budget. */
static u32 picker(const struct pick *pool, u32 n, u32 budget) {
    u32 chosen = 0, best = 0, have = 0;
    for (u32 i = 0; i < n; i++) {
        if ((have && pool[i].key <= best) || pool[i].value >= budget) continue;
        chosen = pool[i].p;
        best = pool[i].key;
        have = 1;
    }
    return chosen;
}

/* The candidate F of DESIGN 4.1, or 0. */
static const struct pick *candidate(const struct pick *pool, u32 n, i32 room) {
    const struct pick *f = 0;
    u32 tried = 0;
    for (;;) {
        /* the best-rated healthy free agent below the last one tried (ties: list order) */
        const struct pick *next = 0;
        for (u32 i = 0; i < n; i++) {
            const struct pick *q = &pool[i];
            if (q->pool || !fully_healthy(q->p)) continue;
            if (tried && (q->key > f->key || (q->key == f->key && q <= f))) continue;
            if (!next || q->key > next->key) next = q;
        }
        if (!next) return 0;
        f = next;
        tried = 1;
        if (f->value < 0xFFFFu && room - 10 > (i32)f->value && picker(pool, n, f->value + 1) == f->p) return f;
    }
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

static void log_sign(u32 index, u32 decision, u32 result, u32 starter, i32 starter_ovr, const struct pick *f, i32 d,
                     i32 g, u32 threshold) {
    u32 n = qb_ring_cursor, table = D(D(LEAGUE_ROOT) + 4);
    volatile struct event *e = &qb_ring[n % 128u];
    e->year = (u16)D(YEAR);
    e->week = (u8)D(WEEK);
    e->club = (u8)index;
    e->decision = (u8)decision;
    e->result = (u8)result;
    e->a = starter ? (u16)((starter - table) / PLAYER_SIZE) : 0xFFFFu;
    e->b = f ? (u16)((f->p - table) / PLAYER_SIZE) : 0xFFFFu;
    e->d = (i8)d;
    e->g = (u8)g;
    e->rating10 = 0;
    e->gap = (i8)(f ? overall_of(f->key) - starter_ovr : 0);
    e->coach = 0;
    e->threshold = threshold;
    qb_ring_cursor = n + 1;
    qb_counters.events_logged++;
}

static void club_signing(u32 index, u32 stages, u32 shadow, u32 menu) {
    u32 team = CLUB_AT(index);
    if (!team) return;
    if (D(USER_FLAG + 4 * index) && D(AUTO_SIGN) != 1) {
        qb_counters.sign_skip_human++;
        return;
    }
    u32 slots = B(team + 0x11C), a = 0, h = 0, starter = 0, best = 0;
    if (slots > SLOTS) return;
    for (u32 i = 0; i < slots; i++) {
        u32 p = D(team + 4 * i);
        if (!p || B(p + 0x35) != 0) continue;
        a++;
        if (!fully_healthy(p)) continue;
        h++;
        u32 key = rating_key(p);
        if (!starter || key > best) {
            starter = p;
            best = key;
        }
    }
    if (a > 2) return;
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
    struct pick pool[POOL_MAX];
    u32 n = collect(pool);
    if (n > POOL_MAX) {
        qb_counters.sign_pool_overflow++;
        return;
    }
    if (!shadow) RECOUNT(team);                     /* the gate recounts before its room test; so does this */
    const struct pick *f = candidate(pool, n, room_of(team, index));
    u32 w = WINS(team), l = LOSSES(team), t = TIES(team);
    i32 d = (i32)l - (i32)w, g = (i32)(w + l + t);
    if (decision == E2) {
        if (!f || overall_of(f->key) - starter_ovr < 2) return;      /* the market has nothing better: no need */
        qb_counters.e2_tried++;
        u32 saved = D(STAT_CLASS);
        if (saved) D(STAT_CLASS) = 0;
        u32 att = (u32)SEASON_STAT(starter, 6), yds = (u32)SEASON_STAT(starter, 8);
        if (saved) D(STAT_CLASS) = saved;
        u32 key[9] = {E2, index, D(YEAR), w, l, t, (f->p - D(D(LEAGUE_ROOT) + 4)) / PLAYER_SIZE, att, yds};
        qb_counters.e2_drawn++;
        if (draw(key, 9) >= 50000u) {
            qb_counters.e2_kept++;
            log_sign(index, E2, KEPT, starter, starter_ovr, f, d, g, 50000u);
            return;
        }
    } else {
        qb_counters.e1_tried++;
        if (!f) {
            qb_counters.sign_no_candidate++;
            log_sign(index, E1, KEPT, starter, starter_ovr, 0, d, g, 100000u);
            return;
        }
    }
    u32 threshold = decision == E1 ? 100000u : 50000u;
    if (shadow) {
        qb_counters.sign_shadow++;
        log_sign(index, decision, WOULD, starter, starter_ovr, f, d, g, threshold);
        return;
    }
    if (B(team + 0x11C) >= 53) {
        CUT_TO(team, 52);
        qb_counters.sign_cuts++;
        RECOUNT(team);
        if (room_of(team, index) - 10 <= (i32)f->value) {
            qb_counters.sign_room_lost++;
            log_sign(index, decision, KEPT, starter, starter_ovr, f, d, g, threshold);
            return;
        }
    }
    u32 signed_ = SIGN(team, 0, f->value + 1, menu);
    if (signed_) {
        if (decision == E1) qb_counters.e1_done++;
        else qb_counters.e2_done++;
    } else {
        qb_counters.sign_failed++;
    }
    log_sign(index, decision, signed_ ? APPLIED : KEPT, starter, starter_ovr, f, d, g, threshold);
}

void CDECL emergency_pass(u32 menu) {
    qb_counters.sign_passes++;
    if (qb_settings.magic[0] != 0x4F524251u || qb_settings.magic[1] != 0x31764D4Fu || qb_settings.mode != 1) {
        qb_counters.passes_bad_settings++;
        return;
    }
    u32 stages = qb_settings.stages;
    if (!(stages & STAGE_SIGN)) return;
    if (D(STAGE) != 8) {
        qb_counters.sign_inactive++;
        return;
    }
    if (!D(LEAGUE_ROOT)) return;
    u32 shadow = qb_settings.flags & FLAG_SHADOW;
    for (u32 index = 0; index < CLUBS; index++) club_signing(index, stages, shadow, menu);
}
