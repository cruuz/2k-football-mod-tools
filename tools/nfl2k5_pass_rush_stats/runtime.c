/* Pass rush stats (job b779 st1): pressures, QB hits, pressures / QB hits / sacks allowed. EXPERIMENTAL.

   Freestanding i386 code for the late allocator owner nfl2k5_pass_rush_stats. Built by
   tools/nfl2k5_pass_rush_stats_build.py into mod_editor/core/nfl2k5_pass_rush_stats_code.py. Every game routine is
   called through its fixed retail address; the only relocations are this blob's own labels and prs_state.

   Played games (the hooks in stubs.S):
     shed   0x23477A  the engaged-block tick 0x233040 returned 2 (a pass rusher beat his blocker): remember, per
                      rusher, the blocker he beat on this play (the play is the play-log count [0xE53804]).
     throw  0x2DB2CA  the release 0x2DAF10 is about to run for the passer (ESI): every defender within the hurry
                      radius gets a pressure, within the hit radius also a QB hit; the blocker each one beat on
                      this play gets a pressure allowed (and a QB hit allowed).
     sack   0xCE32A / 0xCE2A4  the play logger writes a sack entry: the sacker gets a pressure and a QB hit, the
                      blocker he beat gets a pressure, a QB hit and a sack allowed.
     reset  0xA78EF / 0x10B427  the play log is cleared for a new played or simulated game: counters cleared.
   Commit (played and simulated games): 0x134E1F, after FUN_00134DD0 merged one club's game into the career
   stream, adds this game's counts to the current season of every player who played. A game without any played
   event (a simulated or Game Cast game) draws the counts instead, from NFL per-game rates driven by the players'
   Pass Rush / Pass Blocking ratings and the game's own sacks.

   History words (player+0x2C stream): fields 106 pressures, 107 QB hits, 108 pressures allowed,
   109 QB hits allowed, 110 sacks allowed, value in the current season slot, the native class (regular/postseason).
   Values are written with read + set (0x14EE40 / 0x14F430), never through 0x14F450 (its sum/max rule table
   0xAA26C0 is unrelated data past field 86). */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define GB(a) (*(volatile u8 *)(a))
#define GF(a) (*(volatile float *)(a))

#define FIELD0 106
#define NSTAT 5
#define NCODE 136
enum { S_PRS, S_QBH, S_PA, S_HA, S_SA };

/* game routines */
#define LIVE_CODE  ((u32 (FC *)(u32))0x000BBAA0)          /* live 0x54 record -> play-log player code (al) */
#define LIVE_FIRST0 ((u32 (*)(void))0x00061B60)            /* side 0 live records (0xB30C4C) */
#define LIVE_FIRST1 ((u32 (*)(void))0x00061B70)            /* side 1 live records (0xB321A0) */
#define LIVE_NEXT  ((u32 (FC *)(u32))0x00061B90)
#define STAGE      ((u32 (*)(void))0x000C4BB0)
#define CLASS_SET  ((void (FC *)(u32))0x0014EDB0)
#define HIST_GET   ((i32 (FC *)(u32, u32))0x0014EE40)      /* current season slot value */
#define HIST_SET   ((void (FC *)(u32, u32, u32))0x0014F430)
#define HIST_AGO   ((i32 (FC *)(u32, u32, u32))0x0014EF20) /* value N seasons ago */
#define CLASS 0x00BD7F98u                                   /* history class: 0 regular season, 1 postseason */

#define PLAY_COUNT 0x00E53804u
#define OFFENSE 0x00E60280u
#define DEFENSE 0x00E60284u
#define CARD_PLAYER 0x00C90248u
#define CARD_BANKS 0x00C90254u
#define WEEK 0x00E576B4u
#define CELL 0x00E576BCu
#define SEASONS 0x00E576B8u

/* tunables, patched by the Python owner (labels) */
extern volatile float prs_hurry_mm2, prs_hit_mm2;

typedef struct {
    u32 live;          /* a played-game event happened since the last play-log reset */
    u32 throws, sacks, sheds, credits;   /* diagnostics (played events seen) */
    u32 last_defenders;                  /* defenders scanned at the last throw */
    u32 last_min_mm;                     /* nearest defender at the last throw, mm */
    u32 commits;                         /* players committed (diagnostic) */
    u32 rng;                             /* draw state while committing a simulated game */
    u8 cnt[NCODE][NSTAT];
    u8 beaten[NCODE];
    u16 tag[NCODE];
} State;

extern volatile State prs_state;

static void bump(u32 code, u32 stat) {
    if (code < NCODE && prs_state.cnt[code][stat] < 255)
        prs_state.cnt[code][stat]++;
}

static u32 actor_code(u32 actor) {
    if (!actor)
        return 0;
    u32 rec = G(actor + 0x3C);
    if (!rec)
        return 0;
    u32 code = LIVE_CODE(rec) & 0xFF;
    return code < NCODE ? code : 0;
}

/* the blocker this rusher beat on the current play, or 0 */
static u32 beaten_by(u32 rusher) {
    if (!rusher || rusher >= NCODE)
        return 0;
    u32 b = prs_state.beaten[rusher];
    if (!b || prs_state.tag[rusher] != (u16)G(PLAY_COUNT))
        return 0;
    return b;
}

/* 0x23477A: the block between ebx and esi was shed (0x233040 returned 2). The blocker is the one on offense. */
void FC prs_on_shed(u32 a, u32 b) {
    u32 offense = G(OFFENSE);
    u32 blocker = a, rusher = b;
    if (b && G(b + 0x38) == offense) {
        blocker = b;
        rusher = a;
    }
    if (!blocker || !rusher || G(blocker + 0x38) != offense)
        return;
    u32 rc = actor_code(rusher), bc = actor_code(blocker);
    if (!rc || !bc)
        return;
    prs_state.beaten[rc] = (u8)bc;
    prs_state.tag[rc] = (u16)G(PLAY_COUNT);
    prs_state.sheds++;
    prs_state.live = 1;
}

/* 0x2DB2CA: the passer (actor) releases the ball. */
void FC prs_on_throw(u32 passer) {
    prs_state.live = 1;
    prs_state.throws++;
    if (!passer)
        return;
    u32 t = G(passer + 0x18);
    u32 team = G(DEFENSE);
    if (!t || !team || G(passer + 0x38) == team)
        return;
    float qx = GF(t + 0x30), qz = GF(t + 0x38);
    u32 head = G(team);
    u32 d = head ? G(head + 4) : 0;
    u32 seen = 0;
    float best = 1.0e12f;
    for (u32 n = 0; d && n < 16; n++, d = G(d + 0x34)) {
        if (G(d + 0x48))
            continue;
        u32 dt = G(d + 0x18);
        if (!dt)
            continue;
        seen++;
        float dx = GF(dt + 0x30) - qx, dz = GF(dt + 0x38) - qz;
        float r2 = dx * dx + dz * dz;
        if (r2 < best)
            best = r2;
        if (r2 > prs_hurry_mm2)
            continue;
        u32 rc = actor_code(d);
        if (!rc)
            continue;
        u32 hit = r2 <= prs_hit_mm2;
        u32 bc = beaten_by(rc);
        bump(rc, S_PRS);
        if (hit)
            bump(rc, S_QBH);
        if (bc) {
            bump(bc, S_PA);
            if (hit)
                bump(bc, S_HA);
        }
        prs_state.credits++;
    }
    prs_state.last_defenders = seen;
    /* integer square root of the nearest squared distance, for the diagnostics */
    u32 v = best > 4.0e9f ? 0xFFFFFFFFu : (u32)best, root = 0, bit = 1u << 30;
    while (bit > v)
        bit >>= 2;
    while (bit) {
        if (v >= root + bit) {
            v -= root + bit;
            root = (root >> 1) + bit;
        } else {
            root >>= 1;
        }
        bit >>= 2;
    }
    prs_state.last_min_mm = root;
}

/* 0xCE32A / 0xCE2A4: a sack entry; rec = the sacker's live record. */
void FC prs_on_sack(u32 rec) {
    prs_state.live = 1;
    prs_state.sacks++;
    if (!rec)
        return;
    u32 rc = LIVE_CODE(rec) & 0xFF;
    if (!rc || rc >= NCODE)
        return;
    u32 bc = beaten_by(rc);
    bump(rc, S_PRS);
    bump(rc, S_QBH);
    if (bc) {
        bump(bc, S_PA);
        bump(bc, S_HA);
        bump(bc, S_SA);
    }
}

/* 0xA78EF / 0x10B427: a new game (played or simulated) clears the play log. */
void prs_on_reset(void) {
    volatile u8 *p = (volatile u8 *)&prs_state;
    for (u32 i = 0; i < sizeof(State); i++)
        p[i] = 0;
}

/* ---- simulated games: per-game draws ---------------------------------------------------------------- */

static u32 next(void) {
    u32 x = prs_state.rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    prs_state.rng = x;
    return x;
}
static u32 chance(float p) {             /* true with probability p (0..1) */
    if (p <= 0.0f)
        return 0;
    if (p >= 1.0f)
        return 1;
    return (next() >> 8) < (u32)(p * 16777216.0f);
}
static u32 binomial(u32 n, float mean) {
    float p = mean / (float)n;
    u32 k = 0;
    for (u32 i = 0; i < n; i++)
        k += chance(p);
    return k;
}

/* Expected pressures a game for a defender (NFL, PFR advanced defense 2021-2025 per game, starters with 8+
   starts: DE 1.54, OLB 1.42, DT 0.79, LB 0.56, S 0.18, CB 0.06; elite edges about 3.3 a game), as a curve of
   Pass Rush: base + scale * x^1.5 with x = (rating - 50) / 45 clamped to 0..1. Backups (depth rank 2 and
   deeper) play part of the snaps. Index by position code 0..16. */
static const float rush_base[17] = {0, 0, 0, 0, 0.02f, 0.05f, 0.06f, 0, 0, 0, 0.25f, 0.10f, 0, 0, 0, 0.15f, 0.25f};
static const float rush_scale[17] = {0, 0, 0, 0, 0.15f, 0.35f, 0.45f, 0, 0, 0, 3.05f, 1.10f, 0, 0, 0, 2.10f, 3.05f};
extern volatile float prs_rush_share, prs_hit_share, prs_ol_per_game, prs_ol_hit_share, prs_ol_sack_share;

static float rush_curve(u32 rating) {
    float x = ((float)rating - 50.0f) / 45.0f;
    if (x < 0.0f)
        x = 0.0f;
    if (x > 1.0f)
        x = 1.0f;
    /* x^1.5 without libm: x * sqrt(x), Newton steps */
    float s = x > 0.0f ? (x + 1.0f) * 0.5f : 0.0f;
    for (u32 i = 0; i < 6 && s > 0.0f; i++)
        s = 0.5f * (s + x / s);
    return x * s;
}

static u32 depth_rank(u32 player) {
    return (G(player + 0x28) >> 10) & 7;
}

/* the stats object of a live record ([[live+0x30]], the one FUN_001334B0 merges), or 0 */
static u32 stats_of(u32 live) {
    u32 p = live ? G(live + 0x30) : 0;
    return p ? G(p) : 0;
}
static u32 played(u32 live) {
    u32 s = stats_of(live);
    return s && G(s);
}
/* this game's sacks for a defender (half sacks, selector 47) and times sacked for a passer (selector 48) */
static u32 game_half_sacks(u32 live) {
    u32 s = stats_of(live);
    if (!s || GF(s + 0x24) == 0.0f || !G(s + 0x28))
        return 0;
    return GB(G(s + 0x28) + 4);
}
static u32 game_sacked(u32 live) {
    u32 s = stats_of(live);
    if (!s || GF(s + 4) == 0.0f || !G(s + 8))
        return 0;
    return GB(G(s + 8) + 0x23);
}

static void add(u32 player, u32 stat, u32 value) {
    if (!value)
        return;
    i32 cur = HIST_GET(player, FIELD0 + stat);
    i32 v = cur + (i32)value;
    if (v > 32767)
        v = 32767;
    HIST_SET(player, FIELD0 + stat, (u32)v);
}

#define MAXOL 16

/* 0x134E1F: FUN_00134DD0 merged club (club records, persistent) / team (in-game, +0x11C players) / side. */
void FC prs_on_commit(u32 team, u32 club, u32 side) {
    u32 n = GB(team + 0x11C);
    u32 first = side ? LIVE_FIRST1() : LIVE_FIRST0();
    u32 stage = STAGE();
    if (stage == 9 || stage == 7)
        CLASS_SET(1);
    u32 seed = 0x9E3779B9u ^ (G(WEEK) * 0x85EBCA6Bu) ^ (G(CELL) * 0xC2B2AE35u) ^ (G(SEASONS) << 20) ^ (side * 0x27D4EB2Fu)
          ^ club;
    prs_state.rng = seed ? seed : 1;
    u32 live = prs_state.live;
    u32 team_sacked = 0;
    u32 ol_player[MAXOL], ol_weight[MAXOL];
    u32 ol_n = 0, ol_total = 0, ol_pbk = 0, ol_starters = 0;
    u32 rec = first;
    for (u32 i = 0; i < n && rec; i++, rec = LIVE_NEXT(rec)) {
        u32 player = G(club + 4 * i);
        if (!player)
            continue;
        if (live) {
            u32 code = LIVE_CODE(rec) & 0xFF;
            if (code && code < NCODE) {
                for (u32 s = 0; s < NSTAT; s++) {
                    add(player, s, prs_state.cnt[code][s]);
                    prs_state.cnt[code][s] = 0;
                }
                prs_state.commits++;
            }
            continue;
        }
        if (!played(rec))
            continue;
        u32 pos = GB(player + 0x35);
        if (pos > 16)
            continue;
        team_sacked += game_sacked(rec);
        if (pos >= 12 && pos <= 14) {           /* C, G, T: share the line's charge below */
            if (ol_n < MAXOL) {
                u32 pbk = GB(player + 0x46);
                u32 w = pbk >= 115 ? 1 : 115 - pbk;
                w = w * w / 16 + 1;           /* (115 - pbk)^2 / 16: weaker blockers are charged more */
                u32 starter = depth_rank(player) <= 1;
                if (!starter)
                    w = w / 5 + 1;
                else {
                    ol_pbk += pbk;
                    ol_starters++;
                }
                ol_player[ol_n] = player;
                ol_weight[ol_n] = w;
                ol_total += w;
                ol_n++;
            }
            continue;
        }
        if (rush_scale[pos] == 0.0f)
            continue;
        float e = rush_base[pos] + rush_scale[pos] * rush_curve(GB(player + 0x48));
        if (depth_rank(player) >= 2)
            e *= 0.45f;
        u32 sacks = (game_half_sacks(rec) + 1) / 2;   /* whole sacks credited by the engine this game */
        u32 extra = binomial(12, e * prs_rush_share);
        u32 hits = 0;
        for (u32 k = 0; k < extra; k++)
            hits += chance(prs_hit_share);
        add(player, S_PRS, sacks + extra);
        add(player, S_QBH, sacks + hits);
        prs_state.commits++;
    }
    if (!live && ol_n && ol_total) {
        /* the line's charged pressures this game, scaled by the starters' average Pass Blocking */
        float f = 1.0f;
        if (ol_starters) {
            f = 1.0f + (70.0f - (float)(ol_pbk / ol_starters)) / 25.0f;
            if (f < 0.5f)
                f = 0.5f;
            if (f > 1.6f)
                f = 1.6f;
        }
        u32 pa[MAXOL], ha[MAXOL], sa[MAXOL];
        for (u32 i = 0; i < ol_n; i++)
            pa[i] = ha[i] = sa[i] = 0;
        u32 charged = binomial(16, prs_ol_per_game * f);
        u32 sacks_charged = 0;
        for (u32 k = 0; k < team_sacked && k < 16; k++)
            sacks_charged += chance(prs_ol_sack_share);
        for (u32 k = 0; k < charged + sacks_charged; k++) {
            u32 r = next() % ol_total, i = 0;
            while (i + 1 < ol_n && r >= ol_weight[i]) {
                r -= ol_weight[i];
                i++;
            }
            pa[i]++;
            if (k >= charged) {
                ha[i]++;
                sa[i]++;
            } else if (chance(prs_ol_hit_share)) {
                ha[i]++;
            }
        }
        for (u32 i = 0; i < ol_n; i++) {
            add(ol_player[i], S_PA, pa[i]);
            add(ol_player[i], S_HA, ha[i]);
            add(ol_player[i], S_SA, sa[i]);
        }
    }
    CLASS_SET(0);
    if (side)
        prs_on_reset();
}

/* ---- the Player Card: column getter (descriptor cookie 0x200B3: ecx = row, edx = stat id = history field) -- */
float FC prs_card_value(u32 row, u32 field) {
    u32 bank = G(CARD_BANKS + 4 * row);
    u32 player = G(CARD_PLAYER);
    i32 v = 0;
    if (!player || field < FIELD0 || field >= FIELD0 + NSTAT)
        return 0.0f;
    if (bank == 9) {
        /* career: every live word of this field in the current class (the native search 0x14E800's filter) */
        const volatile u32 *w = (const volatile u32 *)G(player + 0x2C);
        u32 cls = G(CLASS);
        for (u32 n = 0; w && n < 50000; n++, w++) {
            u32 word = *w;
            if (((word >> 16) & 0x7F) == field && ((word >> 29) & 1) == cls && !(word & 0x10000000))
                v += (i32)(short)(word & 0xFFFF);
            if (word & 0x80000000)
                break;
        }
    }
    else if (bank == 11)
        v = HIST_GET(player, field);
    else if (bank >= 12 && bank <= 26)
        v = HIST_AGO(player, field, bank - 11);
    return (float)v;
}
