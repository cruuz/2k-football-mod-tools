/* Modern jersey numbers (beta 81, owner nfl2k5_modern_numbers): the number a joining player wears.

   Called by number_entry (entry.S) from the entry of the jersey routine FUN_002BD260, which numbers almost every
   player who joins a club: the draft (FUN_00325B50), every CPU and user free-agent signing, both sides of the trade
   executor, the offseason free-agency paths and MyCareer. Retail knows only the 2004 ranges (tables 0x521B90 /
   0x521BD8: WR and TE 80-89, every back and DB 20-49, ...), so no rookie outside QB, K and P ever wore a single digit,
   and it looks only at the club's active list, so a joiner could take the number of a club-mate on the practice squad
   or on injured reserve, who then shared it with him when he came back.

   The rule (modern-numbers/DESIGN.txt 3.1 and 3.2, as built):
   * Legal numbers by position (today's NFL rule): QB 0-19; K, P 0-49 and 90-99; WR, TE, HB, FB 0-49 and 80-89; CB, FS,
     SS 0-49; OLB, ILB 0-59 and 90-99; DT 50-79 and 90-99; C, G, T 50-79; DE (the game's edge player) 0-79 and 90-99,
     an edge rusher's linebacker numbers and a defensive lineman's (every 2004-range number stays legal, so a veteran
     keeps his number exactly where retail kept it). Whole decades, one bit each (legal[]).
   * Taken = the number of any other player of the club: the active list, the practice-squad reserves after it (and
     their overflow rows) and the club's injured reserve (0x246E50 / 0x246EC0, retail or the modern IR owner's store).
   * A drafted rookie (the call comes from FUN_00325B50, whose caller is one of the game's three draft paths), and any
     rookie (years pro 0 or 1) joining before the regular season (stage [0xE576A4] below 8), gets a fresh draw.
     Anyone else keeps his own number when it is legal and not taken, and otherwise gets a fresh draw.
   * Fresh draw over the club's free legal numbers, weighted by the real 2026 shares of his position group:
     u1 < single[group][tier] percent and a single digit free -> one of the free single digits (u2); otherwise a
     decade by weight[group] (0-9 left out), renormalised over the decades with a free legal number (u2), then a free
     number in it (u3); no weighted decade free -> any free legal number (u3). Tier: the draft round (A = round 1,
     B = 2, C = 3, D = 4-7); an undrafted rookie E; anyone else by his rating against his position's thresholds
     (top 10 percent of the 2026 roster A, next 15 B, next 15 C, the rest D).
   * u1..u3 are a hash of (player index, club index, season [0xE576B8], stage, k): no game RNG is drawn and a reload
     gives the same number.
   * A call from outside the retail .text (an owner's page: MyCareer's signing of the user's own created player, modern
     IR renumbering a club-mate) keeps the player's own number whenever no club-mate wears it, even a rookie before the
     season or a retired or legacy number: the user chose it. Draws still follow every rule below.
   * A club's retired numbers (the owner's data file, from the public retired-numbers list) count as taken: never given
     automatically, not even as a joiner's own number. The exception list lets a club give one to a first-round rookie
     at QB, HB, FB, WR or TE where it really has (NYG 1, Nabers; TEN 1, Ward). A legacy number (DAL 88: a WR) is taken for
     every other position and left out of every draw; a fresh-draw joiner at its position of tier A or B gets it, when
     free, ahead of the draw. A user's own choice (Create Player, Assign Jersey Number, the Studio) never comes here.
   * Nothing legal free at a league club: a number from the nearest decade(s) nobody on the club wears or holds, not
     retired and not another position's legacy number. Nothing free at all, a club outside the league, a position code
     outside 0..16 or no league: return -1, and the entry runs the retail routine with keep = 1.
   Nothing here writes game memory; the entry writes the joiner's +0x20 bits 3..9 and the retail tail his cue. */
#include "tables.h"

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define D(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))
#define W(a) (*(volatile u16 *)(a))

#define ROOT 0x00B72918u               /* -> the league roster object: +0 players, +4 player table, +0x1C clubs */
#define ARENA_SIZE 0x00B72808u         /* the roster arena's length (the practice squad's overflow rows at its tail) */
#define LEAGUE_MODE 0x00E576A0u        /* 2 = franchise */
#define STAGE 0x00E576A4u              /* 8 = regular season, 9 = postseason, below 8 = offseason and preseason */
#define SEASON 0x00E576B8u             /* seasons since 2026 */
#define CLUB_INDEX ((u32 (FC *)(u32))0x000C4CA0)          /* club -> league index (0xFFFF when none) */
#define IR_COUNT ((u32 (FC *)(u32))0x00246E50)            /* club -> players on injured reserve (franchise only) */
#define IR_GET ((u32 (FC *)(u32, u32))0x00246EC0)         /* club, k -> his k-th IR player */
#define RATING ((float (FC *)(u32, u32))0x00246D80)       /* player, 1 -> the native sort rating, 0..1 in ST0 */

#define DRAFT_JOIN_RET 0x00325B6Cu     /* FUN_00325B50's call of the jersey routine returns here */
#define TEXT_START 0x00011000u         /* the retail .text: every game path that numbers a joiner calls from here */
#define TEXT_END 0x00420114u
#define PLAYER_SIZE 84
#define ACTIVE 0x11C
#define PS_COUNT 0x1F2
#define PS_MARKER 0x1F3
#define PS_MARK 0xA5
#define SLOTS 65
#define RESERVE_TAIL 0x400             /* the overflow block: root + arena size - 0x400, "2K5RSV2\0", rows at +32 */
#define RESERVE_ROWS 5

/* ---- the draw (fmix32 chain, as the quarterback room's) ------------------------------------------------------ */
static u32 fmix32(u32 h) { h ^= h >> 16; h *= 0x85EBCA6Bu; h ^= h >> 13; h *= 0xC2B2AE35u; h ^= h >> 16; return h; }

struct pick {
    u32 taken[4];          /* 100 bits: numbers worn by another player of the club */
    u32 key[5];            /* player index, club index, season, stage, then k */
    u32 legal;             /* decades */
};

static u32 draw(struct pick *s, u32 k) {
    u32 h = 0x4D4E554Du;   /* "MNUM" */
    s->key[4] = k;
    for (u32 i = 0; i < 5; i++) h = fmix32(h ^ s->key[i]);
    return h;
}

static int is_taken(const struct pick *s, u32 n) { return s->taken[n >> 5] >> (n & 31) & 1; }

static void take(struct pick *s, u32 p, u32 self) {
    if (!p || p == self) return;
    u32 n = (D(p + 0x20) >> 3) & 0x7F;
    if (n < 100) s->taken[n >> 5] |= 1u << (n & 31);
}

/* free legal numbers in decade d */
static u32 free_in(const struct pick *s, u32 d) {
    u32 c = 0;
    if (s->legal >> d & 1)
        for (u32 n = 10 * d; n < 10 * d + 10; n++) c += !is_taken(s, n);
    return c;
}

/* the k-th (0-based) free legal number of decade d */
static i32 nth_in(const struct pick *s, u32 d, u32 k) {
    for (u32 n = 10 * d; n < 10 * d + 10; n++)
        if (!is_taken(s, n) && !k--) return (i32)n;
    return -1;
}

/* ovr = (int)(v * 100 + 0.5) for the float v of 0x246D80(player, 1), exactly on the float's bits (room.c's overall) */
static u32 overall(u32 p) {
    union { float f; u32 u; } v;
    v.f = RATING(p, 1);
    u32 e = (v.u >> 23) & 255;
    if (v.u >> 31 || e < 119) return 0;
    if (e > 127) return 100;
    u32 s = 150 - e;
    return (((v.u & 0x7FFFFFu) | 0x800000u) * 100u + (1u << (s - 1))) >> s;
}

/* the club's other players: active list, practice-squad reserves (and their overflow rows), injured reserve */
static void club_numbers(struct pick *s, u32 club, u32 index, u32 self) {
    u32 root = D(ROOT), n = B(club + ACTIVE), i;
    if (n > SLOTS) n = SLOTS;
    for (i = 0; i < n; i++) take(s, D(club + 4 * i), self);
    if (B(club + PS_MARKER) == PS_MARK) {
        u32 end = n + B(club + PS_COUNT), block = root + D(ARENA_SIZE) - RESERVE_TAIL;
        if (end > SLOTS + RESERVE_ROWS) end = SLOTS + RESERVE_ROWS;
        int rows = index < 32 && D(block) == 0x52354B32u && D(block + 4) == 0x00325653u;   /* "2K5RSV2\0" */
        for (i = n; i < end; i++) {
            if (i < SLOTS) take(s, D(club + 4 * i), self);
            else if (rows) {
                u32 k = W(block + 32 + 10 * index + 2 * (i - SLOTS));
                if (k < D(root)) take(s, D(root + 4) + PLAYER_SIZE * k, self);
            }
        }
    }
    if (D(LEAGUE_MODE) == 2 && index < 32) {
        u32 count = IR_COUNT(club);
        for (i = 0; i < count && i < 64; i++) take(s, IR_GET(club, i), self);
    }
}

static int is_draft(const u32 *frame) {
    if (frame[0] != DRAFT_JOIN_RET) return 0;
    for (u32 i = 0; i < DRAFT_CALLERS; i++)       /* FUN_00325B50's own return address: one of the three draft paths */
        if (frame[4] == draft_callers[i]) return 1;
    return 0;
}

static void mark(struct pick *s, u32 n) { s->taken[n >> 5] |= 1u << (n & 31); }

i32 __attribute__((cdecl)) number_pick(u32 p, u32 club, const u32 *frame) {
    struct pick s;
    u32 root = D(ROOT), pos = B(p + 0x35), own = (D(p + 0x20) >> 3) & 0x7F;
    u32 rookie = (B(p + 0x25) & 31) <= 1, draft = is_draft(frame), tier, group, i, total, d, index, round = 31;
    u32 owner_call = frame[0] < TEXT_START || frame[0] >= TEXT_END, mates[4];
    i32 legacy_number = -1;
    if (!root || !club || pos >= 17) return -1;
    for (i = 0; i < 4; i++) s.taken[i] = 0;
    s.legal = legal_decades[pos];
    s.key[0] = (p - D(root + 4)) / PLAYER_SIZE;
    s.key[1] = index = CLUB_INDEX(club);
    s.key[2] = D(SEASON);
    s.key[3] = D(STAGE);
    if (draft) round = (frame[5] >> 5) & 31;               /* FUN_00325B50's pick word: round << 5 | slot */
    club_numbers(&s, club, index, p);
    for (i = 0; i < 4; i++) mates[i] = s.taken[i];         /* numbers club-mates wear, before the club's own rules */
    if (owner_call && own < 100 && (s.legal >> (own / 10) & 1) && !(mates[own >> 5] >> (own & 31) & 1))
        return (i32)own;                                   /* a page's call: the player's own number while it is free */
    if (index < 32) {
        u32 open[4] = {0, 0, 0, 0};                        /* retired numbers this joiner may have (the exceptions) */
        if (round == 0 && (SKILL >> pos & 1))
            for (i = 0; i < EXCEPTIONS; i++)
                if (exceptions[i][0] == index) open[exceptions[i][1] >> 5] |= 1u << (exceptions[i][1] & 31);
        for (i = 0; i < 100; i++)
            if ((retired[index][i >> 3] >> (i & 7) & 1) && !(open[i >> 5] >> (i & 31) & 1)) mark(&s, i);
        for (i = 0; i < LEGACY; i++)
            if (legacy[i][0] == index) {
                if (legacy[i][2] == pos) legacy_number = legacy[i][1];
                else mark(&s, legacy[i][1]);               /* another position's legacy number */
            }
    }
    if (!draft && !(rookie && s.key[3] < 8) && own < 100 && (s.legal >> (own / 10) & 1) && !is_taken(&s, own))
        return (i32)own;                                   /* he keeps his own number */
    group = group_of[pos];
    if (draft) {
        tier = round < 3 ? round : 3;
    } else if (rookie && s.key[3] < 8) {
        tier = 4;                                          /* undrafted rookie */
    } else {
        u32 ovr = overall(p);
        tier = ovr >= thresholds[pos][0] ? 0 : ovr >= thresholds[pos][1] ? 1 : ovr >= thresholds[pos][2] ? 2 : 3;
    }
    if (legacy_number >= 0 && !is_taken(&s, (u32)legacy_number) && (s.legal >> (legacy_number / 10) & 1)) {
        if (tier <= 1) return legacy_number;               /* the position's legacy number, ahead of the draw */
        mark(&s, (u32)legacy_number);                      /* otherwise it stays for a better newcomer */
    }
    if (draw(&s, 1) % 100 < single_digit[group][tier]) {
        u32 c = free_in(&s, 0);
        if (c) return nth_in(&s, 0, draw(&s, 2) % c);
    }
    for (total = 0, d = 1; d < 10; d++) total += free_in(&s, d) ? weight[group][d] : 0;
    if (total) {
        u32 r = draw(&s, 3) % total;
        for (d = 1; d < 10; d++) {
            u32 w = free_in(&s, d) ? weight[group][d] : 0;
            if (r < w) return nth_in(&s, d, draw(&s, 4) % free_in(&s, d));
            r -= w;
        }
    }
    for (total = 0, d = 0; d < 10; d++) total += free_in(&s, d);
    if (!total && index < 32) {
        /* No legal number free at a league club: the nearest decade(s) holding a number nobody on the club wears or holds
           (IR, practice squad), not retired and not another position's legacy number. The retail routine reads the
           active list only and would hand out an IR or squad man's number or a retired one (the owner's rules). */
        u32 legal = s.legal, dist, near;
        for (dist = 1; !total && dist < 10; dist++) {
            for (near = 0, d = 0; d < 10; d++)
                if ((d >= dist && (legal >> (d - dist) & 1)) || (d + dist < 10 && (legal >> (d + dist) & 1)))
                    near |= 1u << d;
            s.legal = near & ~legal;
            for (d = 0; d < 10; d++) total += free_in(&s, d);
        }
    }
    if (!total) return -1;                                 /* nothing free: the retail routine */
    total = draw(&s, 5) % total;
    for (d = 0; d < 10; d++) {
        u32 c = free_in(&s, d);
        if (total < c) return nth_in(&s, d, total);
        total -= c;
    }
    return -1;
}
