/* Quarterback room (beta 81 piece 3, owner nfl2k5_qb_room): who starts at quarterback for a CPU-managed club.

   The contract is .b77-scratch/b81/qb34/DESIGN.md section 2 (2.1 to 2.8); the byte interface is INTERFACE.md.
   Freestanding i386 code; no writable data of its own. Everything it keeps is in the page's settings record,
   counters and event ring (page + 0x2000 / 0x2040 / 0x2400 / 0x2E00), which build.py resolves.

   Entries (entry.S): opening_pass() before the week's games (0x247DCA) does D1 only, for clubs with no injured
   quarterback; room_pass() after the games, signings, cuts and the second depth sort (0x24807A) does the newcomer
   step (D1, D4, plain lock) and then D3 and D2. At most one exchange per club per pass.

   Stage bits of the settings record: 1 = D1, 2 = D2 and D3, 4 = D4. The newcomer step runs when D1 or D4 is set;
   a newcomer whose branch (a: D1, b: D4) is switched off is left exactly as he is (no lock, no event), so a stage
   that is off behaves like the old game for that player. Shadow (flags bit 0): every decision is computed, drawn,
   counted and logged, and the local copy of the room is updated as if it had been written (so the control flow is
   the acting one), but nothing is written to the game.

   Game routines, conventions read from the retail executable (tests/mod_editor/test_b81_qb_room_native.py):
   - 0xC4C50 club at league index: ECX = index -> EAX club (0 if none); reads only.
   - 0xC7720 / 0xC7750 / 0xC7780 wins / losses / ties: ECX = club -> EAX; walk the schedule grid, read only;
     EBX, ESI, EDI, EBP preserved.
   - 0x14EE40 season stat: ECX = player, EDX = field -> EAX (signed 16-bit value, sign-extended); the stat class it
     matches is [0xBD7F98] (0 = regular season), which this code sets to 0 around its reads and restores.
   - 0x246D80 native sort rating: ECX = player, EDX = 1 -> float 0..1 in ST0 (one x87 value; nothing else left).
   All four are fastcall-shaped (ECX, EDX in; EAX, ECX, EDX clobbered) and are declared fastcall below. */
#include "room.h"

struct qb {
    u32 p, index;
    i32 ovr, apps, att, cmp, yds, td, ints;
    u32 row, rookie, healthy, locked;
};

struct room {
    u32 index, stage, stages, shadow, opening, n;
    u32 w, l, t, coach1000, h0, d2_scale;
    i32 d, g;
    struct qb q[QB_MAX];     /* by depth row */
};

/* ---- the private draw (DESIGN 2.8, copied exactly) ---------------------------------------------------------- */
static u32 fmix32(u32 h) { h ^= h >> 16; h *= 0x85EBCA6Bu; h ^= h >> 13; h *= 0xC2B2AE35u; h ^= h >> 16; return h; }
static u32 draw(const u32 *w, u32 n) { u32 h = 0x51425233u; for (u32 i = 0; i < n; i++) h = fmix32(h ^ w[i]); return h % 100000u; }

/* ---- inputs ------------------------------------------------------------------------------------------------ */
static int fully_healthy(u32 p) {
    return !(D(p + 0x20) & (INJURED | WEEKS_MASK)) && !(D(p + 0x24) & 0x70000000u);
}

/* ovr = (int)(v * 100 + 0.5) for the float v of 0x246D80(player, 1), evaluated exactly on the float's bits, so the
   answer does not depend on the x87 precision the game left in the control word (nothing touches the control
   word). v is a float in 0..1 (the getter clamps); m * 100 + 2^(s-1) < 2^32 for s = 23..31. */
static i32 overall(u32 p) {
    union { float f; u32 u; } v;
    v.f = RATING(p, 1);
    u32 e = (v.u >> 23) & 255;
    if (v.u >> 31 || e < 119) return 0;                 /* negative, zero or below 2^-8: rounds to 0 */
    if (e > 127) return 100;                            /* 1.0 or more */
    u32 s = 150 - e;
    return (i32)((((v.u & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s);
}

/* Season passer rating times 10, the NFL formula with its clamps (DESIGN 2.2 as corrected by DESIGN_CHANGES C4:
   each component in thousandths with one truncating divide, the sum rounded); 0 without attempts. The stat getter
   returns signed 16-bit values, so the largest product is 32768 * 25000 = 8.2e8 < 2^31 (likewise 5000, 250 and
   20000), and the sum is at most 4 * 2375 + 3. */
static i32 clamp2375(i32 v) { return v < 0 ? 0 : v > 2375 ? 2375 : v; }
static i32 rating10(const struct qb *q) {
    if (q->att <= 0) return 0;
    i32 a = clamp2375(q->cmp * 5000 / q->att - 1500);
    i32 b = clamp2375(q->yds * 250 / q->att - 750);
    i32 c = clamp2375(q->td * 20000 / q->att);
    i32 e = clamp2375(2375 - q->ints * 25000 / q->att);
    return (a + b + c + e + 3) / 6;
}

static int starter_usage(const struct qb *q) {
    return q->apps >= 1 && q->att >= 15 * q->apps;
}

/* floor(v * f / k) without overflow for every value this file passes (v <= 5.6e6, f <= 1350, k <= 1000). */
static u32 scale(u32 v, u32 f, u32 k) {
    return v / k * f + v % k * f / k;
}

/* ---- writes ------------------------------------------------------------------------------------------------ */
static void lock(struct room *r, struct qb *x) {
    if (x->locked) return;
    x->locked = 1;
    if (r->shadow) return;
    B(x->p + 0x52) |= 1;
    qb_counters.locks_written++;
}

/* The standard build's depth swap 0x242CA0 with chain 0: exchange the 3-bit rows at +0x28, set bit 0 of +0x52 on
   both. The local copy is exchanged too; callers stop the club after it. */
static void exchange(struct room *r, struct qb *x, struct qb *y) {
    u32 row = x->row;
    x->row = y->row;
    y->row = row;
    lock(r, x);
    lock(r, y);
    if (r->shadow) {
        qb_counters.shadow_exchanges++;
        return;
    }
    u16 bits = (W(x->p + 0x28) ^ W(y->p + 0x28)) & ROW_MASK;
    W(y->p + 0x28) ^= bits;
    W(x->p + 0x28) ^= bits;
    qb_counters.exchanges_written++;
}

static void log_event(const struct room *r, u32 decision, u32 result, const struct qb *a, const struct qb *b,
                      u32 threshold) {
    u32 n = qb_ring_cursor;
    volatile struct event *e = &qb_ring[n % 128u];
    e->year = (u16)D(YEAR);
    e->week = (u8)D(WEEK);
    e->club = (u8)r->index;
    e->decision = (u8)(decision | (r->stage == 7 ? PRESEASON : 0));
    e->result = (u8)result;
    e->a = (u16)a->index;
    e->b = (u16)b->index;
    e->d = (i8)r->d;
    e->g = (u8)r->g;
    e->rating10 = (u16)rating10(&r->q[0]);
    e->gap = (i8)(b->ovr - a->ovr);
    e->coach = (u8)(r->coach1000 / 10);
    e->threshold = threshold;
    qb_ring_cursor = n + 1;
    qb_counters.events_logged++;
}

static u32 outcome(const struct room *r, u32 exchanged, u32 drawn) {
    return exchanged ? (r->shadow ? WOULD : APPLIED) : drawn ? KEPT : LOCK_ONLY;
}

/* ---- D1 after review (DESIGN addendum 2, R1 to R4), in the middle code piece (page + 0x2200, build.py). ----------
   Recomputed in every pass from a key that does not change during the season: draw(D1, club, year, V index, U index)
   against today's gap x = ovr(U) - ovr(V). V is the incumbent: the first healthy non-rookie in row order. The veteran
   is wanted when x <= -1, or x is 0 to 5 and the draw is below 0.85 - 0.05 x (always the rookie at x >= 6).
   - Veteran wanted, rookie ahead: a hold, rows only: V takes U's row, U and everyone between move down one. No lock;
     the next native sort may undo it and the next pass writes it again (the pre-game pass is the last word).
   - Rookie wanted, V ahead, x 0 to 5, before the club's first game (stage 7, or stage 8 with W + L + T = 0): a
     promotion by choice: U takes V's row, V and everyone between move down one, and the two are locked (the one lock
     D1 may write). After the first game D1 never moves a rookie ahead; the native 3-point rule, D2 and D3 do that.
   - Otherwise nothing is written. Ring row: on every write, and on the pre-game pass also when nothing is written.
   threshold = the chance the veteran starts, in hundred-thousandths. Returns 1 when rows were written. */
#define MID __attribute__((noinline, section(".text.mid")))
#define TAIL __attribute__((noinline, section(".text.tail")))

/* Man m to row `to` (above his own), everyone from `to` down to m's old row moves down one; rows only. In the tail
   piece (page + 0x2E10) with moves.c's put(): decide_d1 alone fills most of the middle one. */
static TAIL void lift(struct room *r, struct qb *m, u32 to) {
    for (u32 i = 0; i < r->n; i++) {
        struct qb *q = &r->q[i];
        u32 row = q == m ? to : q->row >= to && q->row < m->row ? q->row + 1 : q->row;
        if (row == q->row) continue;
        if (!r->shadow) W(q->p + 0x28) = (u16)((W(q->p + 0x28) & ~ROW_MASK) | row << 10);
        q->row = row;
    }
    if (r->shadow) qb_counters.shadow_exchanges++;
    else qb_counters.exchanges_written++;
}

static MID u32 decide_d1(struct room *r, struct qb *u) {
    struct qb *v = 0;
    for (u32 i = 0; i < r->n; i++) {
        struct qb *q = &r->q[i];
        if (q->healthy && !q->rookie && (!v || q->row < v->row)) v = q;
    }
    qb_counters.d1_evaluated++;
    if (!v) {
        qb_counters.d1_no_veteran++;
        return 0;
    }
    i32 x = u->ovr - v->ovr;
    u32 p, veteran, result = KEPT;
    if (x <= -1) {
        p = 100000u;
        veteran = 1;
    } else if (x >= 6) {
        p = 0;
        veteran = 0;
    } else {
        p = (u32)(85 - 5 * x) * 1000u;
        u32 key[5] = {D1, r->index, D(YEAR), v->index, u->index};
        veteran = draw(key, 5) < p;
        qb_counters.d1_drawn++;
    }
    if (veteran) qb_counters.d1_veteran_first++;
    else qb_counters.d1_rookie_first++;
    if (veteran && u->row < v->row) {
        lift(r, v, u->row);
        qb_counters.d1_held++;
        result = r->shadow ? WOULD : APPLIED;
    } else if (!veteran && v->row < u->row && x <= 5 && (r->stage == 7 || r->g == 0)) {
        lift(r, u, v->row);
        lock(r, u);
        lock(r, v);
        qb_counters.d1_promoted++;
        result = r->shadow ? WOULD : APPLIED;
    }
    if (result != KEPT) qb_counters.d1_exchanged++;
    if (result != KEPT || r->opening) log_event(r, D1 | (veteran ? 0 : B_AHEAD), result, v, u, p);
    return result != KEPT;
}

/* R1's season reset (stage 3b, bit 256): at the first pre-game pass of a season with year index 1 or more (stage 8,
   week 0), a healthy quarterback who leads the healthy row 0 man by 6 or more takes row 0 (rows only; the best-rated
   such man, ties to the upper row). Year index 0 is exempt, so the real opening chart stands. */
static u32 season_reset(struct room *r) {
    struct qb *top = 0, *first = 0;
    for (u32 i = 0; i < r->n; i++) {
        struct qb *q = &r->q[i];
        if (!q->row) first = q;
        if (q->healthy && (!top || q->ovr > top->ovr || (q->ovr == top->ovr && q->row < top->row))) top = q;
    }
    if (!first || !first->healthy || top->ovr - first->ovr < 6) return 0;
    lift(r, top, 0);
    qb_counters.season_resets++;
    return 1;
}

/* ---- D4: the returning starter (DESIGN 2.6; addendum 2, R1). U is not on row 0; S = row 0. ----------------------
   Recomputed in every room pass from draw(D4, club, year, U index, S index) against today's gap and today's "hot"
   test; U takes the job (an exchange: rows and both locks) in the week the draw falls below the table's chance.
   Until then nothing is written. threshold = the chance U takes the job. */
static u32 decide_d4(struct room *r, struct qb *u) {
    struct qb *s = 0;
    for (u32 i = 0; i < r->n; i++)
        if (!r->q[i].row) s = &r->q[i];
    i32 x = u->ovr - s->ovr;
    u32 hot = s->att >= 90 && rating10(s) >= 900 && r->w >= r->l;
    u32 flags = D4 | (hot ? HOT : 0);
    qb_counters.d4_evaluated++;
    if (hot) qb_counters.d4_hot++;
    if (x >= 3 || x <= -3) {
        qb_counters.d4_lock_only++;
        return 0;
    }
    u32 p = x >= 0 ? (hot ? 30000u : 80000u) : (hot ? 10000u : 35000u);
    u32 key[5] = {D4, r->index, D(YEAR), u->index, s->index};
    u32 fire = draw(key, 5) < p;
    qb_counters.d4_drawn++;
    if (fire) {
        qb_counters.d4_fired++;
        exchange(r, u, s);
    } else {
        qb_counters.d4_kept++;
    }
    log_event(r, flags | (fire ? B_AHEAD : 0), outcome(r, fire, 1), s, u, p);
    return fire;
}

/* Key of D2 and D3: decision, club, year, W, L, T, S index, S attempts, completions, yards, TD, INT. */
static u32 season_draw(const struct room *r, u32 decision) {
    const struct qb *s = &r->q[0];
    u32 key[12] = {decision, r->index, D(YEAR), r->w, r->l, r->t, s->index, (u32)s->att, (u32)s->cmp, (u32)s->yds,
                   (u32)s->td, (u32)s->ints};
    return draw(key, 12);
}

/* ---- D3: benched for poor play (DESIGN 2.5). S = row 0 with 60+ attempts, C = row 1 healthy. --------------------
   p = H0 * form * record * week * gapf * coach, in this order: H0 in millionths; form, record, week and gapf in
   hundredths, each multiply followed by its divide by 100; coach in thousandths, divided by 1000; the last step
   divides by 10 to hundred-thousandths. Worst case before a divide: H0 1,000,000 (the clamp) times 1.6, 1.7, 1.0
   and 1.5 is 4,080,000 ppm, times coach 1350 is 5.5e9, so every step uses scale() (exact floor, no overflow). */
static u32 d3_factors(const struct room *r, u32 v) {
    const struct qb *s = &r->q[0];
    i32 rating = rating10(s), gap = s->ovr - r->q[1].ovr;
    u32 form = rating < 650 ? 160 : rating < 750 ? 130 : rating < 850 ? 100 : rating < 950 ? 45 : 12;
    u32 record = r->d <= -1 ? 10 : r->d == 0 ? 50 : r->d <= 4 ? 100 : 170;
    u32 week = r->g <= 3 ? 60 : 100;
    u32 gapf = gap <= 5 ? 150 : gap <= 10 ? 100 : gap <= 15 ? 50 : 15;
    v = scale(v, form, 100);
    v = scale(v, record, 100);
    v = scale(v, week, 100);
    v = scale(v, gapf, 100);
    return scale(v, r->coach1000, 1000);
}

static u32 decide_d3(struct room *r) {
    struct qb *s = &r->q[0], *c = &r->q[1];
    if (s->att < 60 || !c->healthy) return 0;
    qb_counters.d3_evaluated++;
    u32 exposure = d3_factors(r, LIMIT_PPM);
    u32 lo = qb_counters.d3_exposure_lo + exposure;
    if (lo < exposure) qb_counters.d3_exposure_hi++;
    qb_counters.d3_exposure_lo = lo;
    u32 p = d3_factors(r, r->h0) / 10;
    u32 fire = season_draw(r, D3) < p;
    qb_counters.d3_drawn++;
    if (fire) {
        qb_counters.d3_fired++;
        exchange(r, c, s);
    } else {
        qb_counters.d3_kept++;
        lock(r, s);
        lock(r, c);
    }
    log_event(r, D3 | (fire ? B_AHEAD : 0), outcome(r, fire, 1), s, c, p);
    return fire;
}

/* ---- D2: the kid's turn (DESIGN 2.4). S = row 0 healthy non-rookie, K = best healthy rookie, gap(K, S) >= -5. ----
   p = base(d) * scale * week(g) * coach: base in millionths times d2_scale_milli / 1000, week in hundredths / 100,
   coach in thousandths / 1000, then / 10. Worst case: 160,000 * 1,000,000 / 1000 = 1.6e8, times 1.0, times 1350
   = 2.2e11 before the divide, so scale() again (exact floor). */
static u32 decide_d2(struct room *r) {
    struct qb *s = &r->q[0], *k = 0;
    if (s->rookie) return 0;
    for (u32 i = 1; i < r->n; i++) {
        struct qb *q = &r->q[i];
        if (q->healthy && q->rookie && (!k || q->ovr > k->ovr)) k = q;
    }
    if (!k || k->ovr - s->ovr < -5) return 0;
    qb_counters.d2_evaluated++;
    u32 base = r->d <= -1 ? 4000 : r->d == 0 ? 12000 : r->d == 1 ? 35000 : r->d == 2 ? 70000 :
               r->d == 3 ? 100000 : r->d == 4 ? 130000 : 160000;
    u32 week = r->g == 1 ? 50 : r->g <= 7 ? 100 : 30;
    u32 p = scale(base, r->d2_scale, 1000);
    p = scale(p, week, 100);
    p = scale(p, r->coach1000, 1000) / 10;
    u32 fire = season_draw(r, D2) < p;
    qb_counters.d2_drawn++;
    if (fire) {
        qb_counters.d2_fired++;
        exchange(r, k, s);
    } else {
        qb_counters.d2_kept++;
        lock(r, s);
        lock(r, k);
    }
    log_event(r, D2 | (fire ? B_AHEAD : 0), outcome(r, fire, 1), s, k, p);
    return fire;
}

/* ---- one club ---------------------------------------------------------------------------------------------- */
static void club_pass(struct room *r) {
    qb_counters.clubs_visited++;
    u32 team = CLUB_AT(r->index);
    if (!team) {
        qb_counters.skip_no_club++;
        return;
    }
    if (D(USER_FLAG + 4 * r->index) && !D(CPU_DEPTH)) {
        qb_counters.skip_unmanaged++;
        return;
    }
    /* Collect: position byte +0x35 = 0, 2..7 of them, rows exactly 0..n-1 (recovery.c's sanity test). */
    u32 slots = B(team + 0x11C), rows = 0, n = 0;
    if (slots > SLOTS) slots = 0;
    for (u32 i = 0; i < slots; i++) {
        u32 p = D(team + 4 * i);
        if (!p || B(p + 0x35) != 0) continue;
        u32 row = (W(p + 0x28) >> 10) & 7;
        if (n == QB_MAX || rows & (1u << row)) {
            n = 0;
            break;
        }
        rows |= 1u << row;
        n++;
        r->q[row].p = p;
    }
    if (n < 2 || rows != (1u << n) - 1) {
        qb_counters.skip_room_shape++;
        return;
    }
    r->n = n;
    for (u32 i = 0; i < n; i++) {
        struct qb *q = &r->q[i];
        q->row = i;
        q->healthy = fully_healthy(q->p);
    }
    if (!r->q[0].healthy) {
        qb_counters.skip_row0_unhealthy++;
        return;
    }
    u32 table = D(D(LEAGUE_ROOT) + 4);
    for (u32 i = 0; i < n; i++) {
        struct qb *q = &r->q[i];
        q->index = (q->p - table) / PLAYER_SIZE;
        q->rookie = (B(q->p + 0x25) & 31) == 1;
        q->locked = B(q->p + 0x52) & 1;
        q->ovr = overall(q->p);
        q->apps = SEASON_STAT(q->p, 0);
        q->att = SEASON_STAT(q->p, 6);
        q->cmp = SEASON_STAT(q->p, 7);
        q->yds = SEASON_STAT(q->p, 8);
        q->td = SEASON_STAT(q->p, 9);
        q->ints = SEASON_STAT(q->p, 10);
    }
    r->w = WINS(team);
    r->l = LOSSES(team);
    r->t = TIES(team);
    r->g = (i32)(r->w + r->l + r->t);
    r->d = (i32)r->l - (i32)r->w;
    u32 coach = D(team + 0x14C), leadership = 83;
    if (coach) leadership = B(coach + 0x56);
    else qb_counters.coach_missing++;
    if (leadership < 61) leadership = 61;
    if (leadership > 99) leadership = 99;
    r->coach1000 = 1350 - 600 * (leadership - 61) / 38;

    /* 0. The season reset (addendum 2, R1; bit 256): the first pre-game pass of a season from year index 1. */
    if (r->opening && (r->stages & STAGE_D3) && r->stage == 8 && !D(WEEK) && D(YEAR) && season_reset(r)) return;
    /* 1. Newcomers: healthy, rank lock clear, best-rated first (ties: the upper row first). */
    if (r->stages & (STAGE_D1 | STAGE_D4)) {
        u32 order[QB_MAX], count = 0;
        for (u32 i = 0; i < n; i++) {
            if (!r->q[i].healthy || r->q[i].locked) continue;
            u32 at = count++;
            while (at && r->q[order[at - 1]].ovr < r->q[i].ovr) {
                order[at] = order[at - 1];
                at--;
            }
            order[at] = i;
        }
        for (u32 k = 0; k < count; k++) {
            struct qb *u = &r->q[order[k]];
            if (u->locked) continue;                    /* locked as the other man of an earlier decision */
            u32 a = u->rookie && !starter_usage(u) && (r->stage == 7 || r->stage == 8);
            u32 b = !a && u->row != 0 && !u->rookie && starter_usage(u) && r->stage >= 8;
            if (r->opening && !a) continue;             /* the opening pass does D1 only */
            if ((a && !(r->stages & STAGE_D1)) || (b && !(r->stages & STAGE_D4))) {
                qb_counters.newcomer_stage_off++;
                continue;
            }
            qb_counters.newcomers++;
            if (a) {
                if (decide_d1(r, u)) return;
            } else if (b) {
                if (decide_d4(r, u)) return;
            } else {
                qb_counters.newcomer_locked++;          /* case (c): nothing written (addendum 2, R1) */
            }
        }
    }
    /* 2. D3 then D2 (each on its own bit, R5): stage 8, after games 1 to 16, only if step 1 wrote nothing. */
    if (r->opening || r->stage != 8 || !(r->stages & (STAGE_D2 | STAGE_D3)) || r->g < 1 || r->g > 16) return;
    if ((r->stages & STAGE_D3) && decide_d3(r)) return;
    if (r->stages & STAGE_D2) decide_d2(r);
}

static void pass(u32 opening) {
    if (qb_settings.magic[0] != 0x4F524251u || qb_settings.magic[1] != 0x31764D4Fu || qb_settings.mode != 1) {
        qb_counters.passes_bad_settings++;
        return;
    }
    struct room r;
    r.stages = qb_settings.stages;
    r.opening = opening;
    if (!(r.stages & (opening ? STAGE_D1 | STAGE_D3 : STAGE_D1 | STAGE_D2 | STAGE_D3 | STAGE_D4))) return;
    r.stage = D(STAGE);
    if (r.stage < 7 || r.stage > 9) {
        qb_counters.passes_inactive++;
        return;
    }
    if (!D(LEAGUE_ROOT)) return;
    r.shadow = qb_settings.flags & FLAG_SHADOW;
    r.h0 = qb_settings.h0_ppm;
    r.d2_scale = qb_settings.d2_scale_milli;
    if (r.h0 > LIMIT_PPM) r.h0 = LIMIT_PPM;
    if (r.d2_scale > LIMIT_PPM) r.d2_scale = LIMIT_PPM;
    u32 saved = D(STAT_CLASS);
    if (saved) D(STAT_CLASS) = 0;
    for (r.index = 0; r.index < CLUBS; r.index++) club_pass(&r);
    if (saved) D(STAT_CLASS) = saved;
}

void CDECL opening_pass(void) {
    qb_counters.opening_passes++;
    pass(1);
}

void CDECL room_pass(void) {
    qb_counters.room_passes++;
    pass(0);
}
