/* Franchise history capture (b780 J3, job j23-footer). EXPERIMENTAL.

   Freestanding i386 code for the late allocator owner nfl2k5_history, built by tools/nfl2k5_history_build.py into
   mod_editor/core/nfl2k5_history_code.py. No retail bytes live here. It writes the blocks of the franchise extension
   footer (mod_editor/core/nfl2k5_franchise_extension.py, the published format; keep the two in step). The body comes
   from the footer host (nfl2k5_franchise_footer: xt_body, allocated on first franchise use); this owner has no body
   of its own. Every address beyond its labels is in the CONFIG table (hst_config) the Studio fills.

   Two moments (stubs.S):
   * a finished game (the tails of FUN_001356C0, played, 0x1356C8, and FUN_001356D0, simulated, 0x1356FF, both right
     after the commit FUN_00135310 and before the game summary 0x73770): single-game records for every player of both
     clubs, and the box score of a game the user's club played. Preseason and the Pro Bowl are not recorded.
   * the season close (stage 9, 0x248601, after the Super Bowl notice and the retirement pass, before the contract
     ring shift 0x13ED70 and the rollover): the season line of every club (regular-season W-L-T, PF, PA, division
     place, playoff result, head coach), the season's awards, franchise totals, single-season records, all-time leaders
     and Hall of Fame candidates (retirees) and the class.
   It reads the game's state only (getters, the grid, the stat readers). It never calls the random number generator,
   allocates nothing and writes only inside the body. Every loop is bounded; every pointer it follows is checked first;
   a part that finds anything unexpected is skipped (its code goes to the host info area) and the retail call runs. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef short i16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))

/* game routines (all getters) */
#define TEAM_READ  ((float (FC *)(u32, u32, u32))0x000CB2D0)   /* live club object, club stat id, bank 0 */
#define PLAYER_READ ((float (FC *)(u32, u32, u32))0x000CB240)  /* live player node, player stat id, bank 0 */
#define ROSTER_OF  ((u32 (FC *)(u32))0x000CA810)              /* live player node -> roster player record */
#define STAT       ((i32 (FC *)(u32, u32))0x0014EE40)         /* current season value of a history field */
#define CLASS_SET  ((void (FC *)(u32))0x0014EDB0)
#define TEAM_FIRST ((u32 (FC *)(u32))0x000C3E70)
#define TEAM_NEXT  ((u32 (FC *)(u32, u32))0x000C3E80)
#define TEAM_COUNT ((u32 (*)(void))0x000C6430)
#define TEAM_AT    ((u32 (FC *)(u32))0x000C4C50)
#define COACHED    ((u32 (*)(void))0x000C4D70)                /* the user's (controller's) team record */

#define LEAGUE_MODE 0x00E576A0u
#define STAGE 0x00E576A4u
#define WEEK 0x00E576B4u
#define CELL 0x00E576BCu
#define SEASONS 0x00E576B8u
#define GRID 0x00E57C40u           /* 22 rows x 17 slots x 8 B: type (3 played), home, away, ... */
#define SCORES 0x00E587F0u         /* 10 B per cell: home Q1..OT, away Q1..OT */
#define DIVISIONS 0x00E576D4u      /* the division of each club (u32) */
#define AWARDS 0x00E5A2F0u         /* season object; award slots {player*, team*} at +0x5800.. */
#define CLASS 0x00BD7F98u
#define CARD_YEAR_IMM 0x003204ADu  /* the season year base: mov ecx, base_year + 11 */
#define WEEKS_VA 0x005151C4u       /* stage table, Season row +4: regular-season weeks (17, or 18) */
#define SB_ROW_IMM 0x00133A41u     /* the Super Bowl row (0x14, 0x15 with 18 weeks) */
#define CLUB0 0x00B30864u          /* live clubs of the game just finished: home, away */
#define CLUB1 0x00B30A58u
#define NODES0 0x00B30BF8u         /* live player nodes: base + k * 0x54, k = 1..count (club +0x11C) */
#define NODES1 0x00B3214Cu

/* format (nfl2k5_franchise_extension, envelope v1) */
#define INFO_AT 0x140u
#define SEASONS_AT 0x0200u
#define TOTALS_AT 0x4C10u
#define RECORDS_AT 0x4E20u
#define LEADERS_AT 0x7350u
#define HALL_AT 0xB280u
#define BOX_AT 0xC490u
#define SEASON_RECORD 592u
#define RING 32u
#define LEAGUE_RECORDS 9232u
#define LEAGUE_LEADERS 15376u
#define CANDIDATES_AT 3088u
#define BOX_ENTRY 512u
#define BOX_GAMES 24u
#define BOX_LINES 23u

struct config {
    u32 magic;          /* "HSTC" */
    u32 version;        /* 1 */
    u32 body_fn;        /* the footer host's xt_body (fastcall, ecx = allocate) */
    u32 chain_close;    /* the displaced season-close call target (0x13ED70 on retail bytes) */
    u32 hall_bar;       /* Hall of Fame: the score a candidate needs (j6 tunes it) */
    u32 hall_wait;      /* seasons after retirement before a candidate is eligible (5) */
    u32 hall_window;    /* seasons a candidate stays eligible (15) */
    u32 hall_class;     /* most inductees per class (5) */
    u32 flags;          /* bit 0 records, 1 box scores, 2 leaders, 3 hall of fame */
    u32 reserved[7];
};
extern const struct config hst_config;

static u8 *body(u32 allow) {
    if (!hst_config.body_fn)
        return 0;
    return ((u8 *(FC *)(u32))hst_config.body_fn)(allow);
}

/* ---- small helpers ---------------------------------------------------------------------------------------- */
static u32 rd16(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8; }
static void wr16(u8 *p, u32 v) { p[0] = (u8)v; p[1] = (u8)(v >> 8); }
static u32 rd32(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24; }
static void wr32(u8 *p, u32 v) { p[0] = (u8)v; p[1] = (u8)(v >> 8); p[2] = (u8)(v >> 16); p[3] = (u8)(v >> 24); }
static void zero(u8 *p, u32 n) { while (n--) *p++ = 0; }
static void copy(u8 *to, const u8 *from, u32 n) { while (n--) *to++ = *from++; }

static void info_add(u8 *b, u32 at) { wr32(b + INFO_AT + at, rd32(b + INFO_AT + at) + 1); }
static void info_error(u8 *b, u32 code) { wr32(b + INFO_AT + 0x24, code); }

static u32 season_year(void) { return (u32)((i32)G(CARD_YEAR_IMM) - 11) + G(SEASONS); }

static u32 team_index(u32 team) {
    u32 base = TEAM_AT(0);
    return team >= base && (team - base) % 500 == 0 && (team - base) / 500 < 32 ? (team - base) / 500 : 0xFF;
}

static i32 to_int(float f) { return (i32)f; }

/* ---- the 7-byte person (nfl2k5_champions_history packing: initial, nine letters, position code) -------------- */
static u32 sym5(u32 c) {
    if (c >= 'a' && c <= 'z')
        c -= 32;
    if (c >= 'A' && c <= 'Z')
        return c - 'A' + 1;
    return c == '-' ? 27 : c == '.' ? 28 : c == '\'' ? 29 : c == ' ' ? 30 : 31;
}

static void put_bits(u8 *out, u32 at, u32 value, u32 count) {
    for (u32 b = 0; b < count; b++)
        if (value >> b & 1)
            out[(at + b) >> 3] |= (u8)(1u << ((at + b) & 7));
}

static u32 good_text(const u16 *s) { return (u32)s >= 0x10000 && (u32)s < 0x08000000; }

/* last name length without a generational suffix ("Walker III" -> 6) */
static u32 name_length(const u16 *last) {
    u32 n = 0, space = 0;
    if (!good_text(last))
        return 0;
    while (last[n] && n < 40) {
        if (last[n] == ' ')
            space = n;
        n++;
    }
    if (space) {
        static const char *const suffix[8] = {"Jr", "Jr.", "Sr", "Sr.", "II", "III", "IV", "V"};
        for (u32 k = 0; k < 8; k++) {
            u32 j = 0;
            while (suffix[k][j] && last[space + 1 + j] == (u16)(u8)suffix[k][j])
                j++;
            if (!suffix[k][j] && !last[space + 1 + j])
                return space;
        }
    }
    return n;
}

static void pack_name(u8 *out, const u16 *first, const u16 *last, u32 position) {
    u32 at = 5, length = name_length(last);
    zero(out, 7);
    put_bits(out, 0, good_text(first) && first[0] ? sym5(first[0]) : 0, 5);
    for (u32 i = 0; i < 9; i++, at += 5)
        put_bits(out, at, i < length ? sym5(last[i]) : 0, 5);
    put_bits(out, at, position & 31, 5);
}

static u32 good_player(u32 p) { return p >= 0x10000 && p < 0x08000000 && !(p & 3); }

static void pack_player(u8 *out, u32 p) {
    if (!good_player(p)) {
        zero(out, 7);
        return;
    }
    pack_name(out, (const u16 *)G(p + 0x10), (const u16 *)G(p + 0x14), B(p + 0x35));
}

/* a team record's head coach (team +0x14C -> coach record: +0 first name, +4 last name) */
static void pack_coach(u8 *out, u32 team) {
    u32 coach = team ? G(team + 0x14C) : 0;
    if (!good_player(coach)) {
        zero(out, 7);
        return;
    }
    pack_name(out, (const u16 *)G(coach), (const u16 *)G(coach + 4), 31);
}

/* ---- records (block 3) ------------------------------------------------------------------------------------ */
/* player stat selectors (game lines, bank 0) and history field ids (season lines, STAT) of the 12 categories:
   passing yards, passing TD, completions, rushing yards, rushing TD, receptions, receiving yards, receiving TD,
   sacks (half sacks), interceptions, tackles, forced fumbles */
static const u8 game_sel[12] = {76, 64, 4, 80, 63, 46, 79, 62, 47, 23, 50, 17};
static const u8 season_field[12] = {8, 9, 7, 2, 3, 12, 13, 14, 19, 20, 18, 21};

static void record_entry(u8 *e, u32 p, u32 club, u32 value, u32 year, u32 row) {
    pack_player(e, p);
    e[7] = (u8)(club + 1);
    wr16(e + 8, value > 0xFFFF ? 0xFFFF : value);
    e[10] = (u8)(year - 1900);
    e[11] = (u8)row;
}

static void consider_record(u8 *b, u32 club, u32 cat, u32 kind, i32 value, u32 p, u32 year, u32 row) {
    if (value <= 0 || club >= 32)
        return;
    u8 *e = b + RECORDS_AT + 16 + ((club * 12 + cat) * 2 + kind) * 12;
    if (!e[10] || (u32)value > rd16(e + 8))
        record_entry(e, p, club, (u32)value, year, row);
    u8 *l = b + RECORDS_AT + LEAGUE_RECORDS + (cat * 2 + kind) * 12;
    if (!l[10] || (u32)value > rd16(l + 8))
        record_entry(l, p, club, (u32)value, year, row);
}

/* ---- a finished game -------------------------------------------------------------------------------------- */
/* club stat ids of the box score (nfl2k5_franchise_extension.TEAM_STATS, in order) */
static const u8 team_stat[16] = {91, 14, 208, 76, 80, 35, 4, 3, 66, 22, 16, 48, 36, 98, 83, 39};

static i32 clamp16(i32 v) { return v > 32767 ? 32767 : v < -32768 ? -32768 : v; }

/* one box score line (kind 1 passing, 2 rushing, 3 receiving, 4 defense, 5 kicking) from a live node, or 0 */
static u32 line_kind(u32 node, i32 *v) {
    i32 att = to_int(PLAYER_READ(node, 35, 0)), rush = to_int(PLAYER_READ(node, 3, 0));
    i32 rec = to_int(PLAYER_READ(node, 46, 0)), tackles = to_int(PLAYER_READ(node, 50, 0));
    i32 sacks = to_int(PLAYER_READ(node, 47, 0)), ints = to_int(PLAYER_READ(node, 23, 0));
    i32 ff = to_int(PLAYER_READ(node, 17, 0));
    if (att > 0) {
        v[0] = to_int(PLAYER_READ(node, 4, 0));
        v[1] = att;
        v[2] = to_int(PLAYER_READ(node, 76, 0));
        v[3] = to_int(PLAYER_READ(node, 64, 0));
        v[4] = to_int(PLAYER_READ(node, 22, 0));
        v[5] = to_int(PLAYER_READ(node, 80, 0));
        return 1;
    }
    if (rush > 0 && rush >= rec) {
        v[0] = rush;
        v[1] = to_int(PLAYER_READ(node, 80, 0));
        v[2] = to_int(PLAYER_READ(node, 63, 0));
        v[3] = rec;
        v[4] = to_int(PLAYER_READ(node, 79, 0));
        v[5] = to_int(PLAYER_READ(node, 62, 0));
        return 2;
    }
    if (rec > 0) {
        v[0] = rec;
        v[1] = to_int(PLAYER_READ(node, 79, 0));
        v[2] = to_int(PLAYER_READ(node, 62, 0));
        v[3] = rush;
        v[4] = to_int(PLAYER_READ(node, 80, 0));
        v[5] = to_int(PLAYER_READ(node, 63, 0));
        return 3;
    }
    if (tackles > 0 || sacks > 0 || ints > 0 || ff > 0) {
        v[0] = tackles;
        v[1] = sacks;
        v[2] = ints;
        v[3] = ff;
        v[4] = 0;
        v[5] = 0;
        return 4;
    }
    return 0;
}

static u32 player_index(u32 p) {
    /* the roster record's index in the primary pool (roster object +4 relative pointer is relocated at load) */
    u32 root = G(0x00B72918);
    if (!root || !good_player(p))
        return 0xFFFF;
    u32 pool = G(root + 4);
    if (pool < 0x10000 || p < pool || (p - pool) % 0x54 || (p - pool) / 0x54 >= 8192)
        return 0xFFFF;
    return (p - pool) / 0x54;
}

static void box_capture(u8 *b, u32 played, u32 row, u32 slot, u32 home, u32 away, u32 user_side, u32 year) {
    u8 *h = b + BOX_AT;
    if (rd16(h) != year) {                                     /* a new season: last season's games go */
        zero(h, 16 + BOX_GAMES * BOX_ENTRY);
        wr16(h, year);
    }
    u32 n = h[2];
    for (u32 i = 0; i < n && i < BOX_GAMES; i++) {             /* the same game again (a replay): rewrite it */
        u8 *g = h + 16 + i * BOX_ENTRY;
        if (g[0] == row && g[1] == slot) {
            n = i;
            break;
        }
    }
    if (n >= BOX_GAMES)
        return;
    u8 *g = h + 16 + n * BOX_ENTRY;
    zero(g, BOX_ENTRY);
    const u8 *score = (const u8 *)(SCORES + (row * 17 + slot) * 10);
    u32 hp = 0, ap = 0;
    for (u32 q = 0; q < 5; q++) {
        hp += score[q];
        ap += score[5 + q];
    }
    g[0] = (u8)row;
    g[1] = (u8)slot;
    g[2] = (u8)home;
    g[3] = (u8)away;
    g[4] = (u8)(hp > 255 ? 255 : hp);
    g[5] = (u8)(ap > 255 ? 255 : ap);
    g[6] = (u8)user_side;
    g[7] = (u8)(1 | (played ? 2 : 4));
    for (u32 side = 0; side < 2; side++)
        for (u32 s = 0; s < 16; s++)
            wr16(g + 16 + side * 32 + s * 2, (u32)clamp16(to_int(TEAM_READ(side ? CLUB1 : CLUB0, team_stat[s], 0))));
    /* the opponent's leaders and the user club's lines */
    u32 lines = 0;
    i32 best[4] = {0, 0, 0, 0};
    for (u32 side = 0; side < 2; side++) {
        u32 obj = side ? CLUB1 : CLUB0, base = side ? NODES1 : NODES0, count = B(obj + 0x11C);
        for (u32 k = 1; k <= count && k <= 70; k++) {
            u32 node = base + k * 0x54, p = ROSTER_OF(node);
            if (!good_player(p))
                continue;
            i32 v[6];
            u32 kind = line_kind(node, v);
            if (!kind)
                continue;
            if (side == user_side) {
                if (lines < BOX_LINES) {
                    u8 *l = g + 144 + lines * 16;
                    wr16(l, player_index(p));
                    l[2] = B(p + 0x35);
                    l[3] = (u8)kind;
                    for (u32 j = 0; j < 6; j++)
                        wr16(l + 4 + j * 2, (u32)clamp16(v[j]));
                    lines++;
                }
                continue;
            }
            /* opponent leaders: passing (yards), rushing (yards), receiving (yards), defense (tackles) */
            i32 key = kind == 1 ? v[2] : kind == 2 ? v[1] : kind == 3 ? v[1] : v[0] * 2 + v[1];
            u32 slotk = kind - 1;
            if (slotk < 4 && key > best[slotk]) {
                best[slotk] = key;
                u8 *l = g + 80 + slotk * 16;
                zero(l, 16);
                pack_player(l, p);
                l[7] = (u8)kind;
                for (u32 j = 0; j < 4; j++)
                    wr16(l + 8 + j * 2, (u32)clamp16(v[j]));
            }
        }
    }
    g[8] = (u8)lines;
    if (n == h[2])
        h[2] = (u8)(n + 1);
    h[3] = (u8)((user_side ? away : home) + 1);
}

/* kind: 2 played by a user, 4 simulated */
void FC history_game(u32 kind) {
    if (G(LEAGUE_MODE) != 2)
        return;
    u32 stage = G(STAGE), row = G(WEEK), slot = G(CELL);
    if ((stage != 8 && stage != 9) || row >= 22 || slot >= 17)
        return;
    u32 sb = B(SB_ROW_IMM);
    if (row > sb)                                              /* the Pro Bowl is not recorded */
        return;
    const u8 *cell = (const u8 *)(GRID + (row * 17 + slot) * 8);
    u32 home = cell[1], away = cell[2];
    if (cell[0] != 3 || home >= 32 || away >= 32 || home == away)
        return;
    u8 *b = body(1);
    if (!b)
        return;
    u32 year = season_year();
    if (hst_config.flags & 1)
        for (u32 side = 0; side < 2; side++) {
            u32 obj = side ? CLUB1 : CLUB0, base = side ? NODES1 : NODES0, count = B(obj + 0x11C);
            u32 club = side ? away : home;
            for (u32 k = 1; k <= count && k <= 70; k++) {
                u32 node = base + k * 0x54, p = ROSTER_OF(node);
                if (!good_player(p))
                    continue;
                for (u32 c = 0; c < 12; c++)
                    consider_record(b, club, c, 0, to_int(PLAYER_READ(node, game_sel[c], 0)), p, year, row + 1);
            }
        }
    if (hst_config.flags & 2) {
        u32 user = team_index(COACHED());
        if (user == home || user == away)
            box_capture(b, kind == 2, row, slot, home, away, user == away, year);
    }
    info_add(b, 0x1C);
}

/* ---- the season close ------------------------------------------------------------------------------------- */
typedef struct {
    u32 w, l, t, pf, pa, dw, dl, dt, result, bye, played_wc, games;
} Line;

static void tally_season(Line *lines, u32 weeks, u32 sb) {
    zero((u8 *)lines, sizeof(Line) * 32);
    for (u32 row = 0; row <= sb && row < 22; row++)
        for (u32 slot = 0; slot < 17; slot++) {
            const u8 *cell = (const u8 *)(GRID + (row * 17 + slot) * 8);
            u32 home = cell[1], away = cell[2];
            if (cell[0] != 3 || home >= 32 || away >= 32 || home == away)
                continue;
            const u8 *score = (const u8 *)(SCORES + (row * 17 + slot) * 10);
            u32 hp = 0, ap = 0;
            for (u32 q = 0; q < 5; q++) {
                hp += score[q];
                ap += score[5 + q];
            }
            if (row < weeks) {
                Line *H = &lines[home], *A = &lines[away];
                u32 same = (G(DIVISIONS + 4 * home) & 7) == (G(DIVISIONS + 4 * away) & 7);
                H->pf += hp; H->pa += ap; A->pf += ap; A->pa += hp;
                H->games++; A->games++;
                if (hp > ap) {
                    H->w++; A->l++;
                    if (same) { H->dw++; A->dl++; }
                } else if (ap > hp) {
                    A->w++; H->l++;
                    if (same) { A->dw++; H->dl++; }
                } else {
                    H->t++; A->t++;
                    if (same) { H->dt++; A->dt++; }
                }
                continue;
            }
            /* postseason: the round is the row (wild card = sb - 3 .. Super Bowl = sb) */
            u32 round = row + 4 - sb;                          /* 1 wild card, 2 divisional, 3 conference, 4 SB */
            if (round < 1 || round > 4)
                continue;
            u32 winner = hp > ap ? home : away, loser = hp > ap ? away : home;
            if (hp == ap)
                continue;
            if (round == 1) {
                lines[home].played_wc = lines[away].played_wc = 1;
            }
            if (round == 2) {                                  /* a divisional team that skipped the wild card */
                if (!lines[home].played_wc) lines[home].bye = 1;
                if (!lines[away].played_wc) lines[away].bye = 1;
            }
            if (lines[loser].result < round)
                lines[loser].result = round;                   /* lost in this round */
            if (round == 4 && lines[winner].result < 5)
                lines[winner].result = 5;                      /* won the Super Bowl */
            else if (lines[winner].result < round)
                lines[winner].result = round;                  /* reached the next round (raised if it loses there) */
        }
}

/* win percentage x 1000 (a tie counts half) */
static u32 pct(const Line *a) {
    u32 g = a->w + a->l + a->t;
    return g ? (2 * a->w + a->t) * 500 / g : 0;
}

static u32 ahead(const Line *a, u32 ia, const Line *b, u32 ib) {
    if (pct(a) != pct(b))
        return pct(a) > pct(b);
    u32 da = a->dw + a->dl + a->dt, db = b->dw + b->dl + b->dt;
    u32 pa = da ? (2 * a->dw + a->dt) * 500 / da : 0, pb = db ? (2 * b->dw + b->dt) * 500 / db : 0;
    if (pa != pb)
        return pa > pb;
    i32 na = (i32)a->pf - (i32)a->pa, nb = (i32)b->pf - (i32)b->pa;
    if (na != nb)
        return na > nb;
    return ia < ib;
}

static u32 place_of(const Line *lines, u32 club) {
    u32 division = G(DIVISIONS + 4 * club) & 7, place = 1;
    for (u32 o = 0; o < 32; o++)
        if (o != club && (G(DIVISIONS + 4 * o) & 7) == division && ahead(&lines[o], o, &lines[club], club))
            place++;
    return place > 4 ? 4 : place;
}

static void award(u8 *out, u32 at) {
    u32 p = G(AWARDS + at), team = G(AWARDS + at + 4);
    if (!good_player(p))
        return;
    pack_player(out, p);
    u32 club = team_index(team);
    out[7] = (u8)(club < 32 ? club + 1 : 0);
}

static void close_seasons(u8 *b, Line *lines, u32 year, u32 weeks, u32 sb) {
    u8 *s = b + SEASONS_AT;
    u32 count = s[0] > RING ? RING : s[0], head = s[1] % RING;
    if (count && rd16(s + 16 + ((head + RING - 1) % RING) * SEASON_RECORD) == year) {
        head = (head + RING - 1) % RING;                       /* this season was already closed: rewrite it */
        count--;
    }
    u8 *r = s + 16 + head * SEASON_RECORD;
    zero(r, SEASON_RECORD);
    wr16(r, year);
    r[3] = (u8)weeks;
    u32 champion = 0xFF, runner = 0xFF, games = 0;
    for (u32 c = 0; c < 32; c++) {
        Line *L = &lines[c];
        u8 *e = r + 80 + c * 16;
        u32 place = place_of(lines, c);
        e[0] = (u8)L->w;
        e[1] = (u8)L->l;
        e[2] = (u8)L->t;
        e[3] = (u8)(L->result | (place == 1 ? 8 : 0) | (L->bye ? 16 : 0) | (place - 1) << 5 | 0x80);
        wr16(e + 4, L->pf > 0xFFFF ? 0xFFFF : L->pf);
        wr16(e + 6, L->pa > 0xFFFF ? 0xFFFF : L->pa);
        pack_coach(e + 8, TEAM_AT(c));
        if (L->result == 5)
            champion = c;
        if (L->result == 4)
            runner = c;
        if (L->result)
            games++;
    }
    u32 flags = 1;
    if (champion < 32 && runner < 32) {
        const u8 *cell = (const u8 *)(GRID + sb * 17 * 8);
        const u8 *score = (const u8 *)(SCORES + sb * 17 * 10);
        u32 hp = 0, ap = 0;
        for (u32 q = 0; q < 5; q++) {
            hp += score[q];
            ap += score[5 + q];
        }
        r[4] = (u8)(champion + 1);
        r[5] = (u8)(runner + 1);
        r[6] = (u8)(cell[1] == champion ? hp : ap);
        r[7] = (u8)(cell[1] == champion ? ap : hp);
        flags |= 2;
    }
    u32 user = team_index(COACHED());
    if (user < 32) {
        r[8] = (u8)(user + 1);
        flags |= 4;
    }
    r[2] = (u8)flags;
    r[9] = (u8)games;
    /* awards: MVP, OPOY, DPOY, OROY, DROY, comeback (not voted yet), coach of the year, Super Bowl MVP */
    award(r + 16 + 0 * 8, 0x5800);
    award(r + 16 + 1 * 8, 0x5810);
    award(r + 16 + 2 * 8, 0x5818);
    award(r + 16 + 3 * 8, 0x5820);
    award(r + 16 + 4 * 8, 0x5828);
    {   /* coach of the year: the slot holds {coach record, team} */
        u32 team = G(AWARDS + 0x580C), club = team_index(team);
        if (club < 32) {
            pack_coach(r + 16 + 6 * 8, TEAM_AT(club));
            r[16 + 6 * 8 + 7] = (u8)(club + 1);
        }
    }
    award(r + 16 + 7 * 8, 0x5888);
    s[0] = (u8)(count + 1 > RING ? RING : count + 1);
    s[1] = (u8)((head + 1) % RING);
    wr16(s + 2, year);
    u32 oldest = rd16(s + 16 + ((head + RING + 1 - s[0]) % RING) * SEASON_RECORD);
    wr16(s + 4, oldest ? oldest : year);
    s[6] = RING;
}

static void close_totals(u8 *b, const Line *lines, u32 year) {
    u8 *t = b + TOTALS_AT;
    if (!rd16(t))
        wr16(t, year);
    wr16(t + 2, rd16(t + 2) + 1);
    for (u32 c = 0; c < 32; c++) {
        const Line *L = &lines[c];
        u8 *e = t + 16 + c * 16;
        wr16(e, rd16(e) + L->w);
        wr16(e + 2, rd16(e + 2) + L->l);
        wr16(e + 4, rd16(e + 4) + L->t);
        if (L->result) e[6]++;
        if (place_of(lines, c) == 1) e[7]++;
        if (L->result >= 4) e[8]++;
        if (L->result == 5) e[9]++;
        e[10]++;
        if (L->w > L->l) e[11]++;
        /* playoff games: a team that lost in round r won r - 1 (minus the bye), a champion won every round */
        u32 played = L->result == 5 ? 4 - L->bye : L->result ? L->result - L->bye : 0;
        u32 lost = L->result && L->result < 5 ? 1 : 0;
        wr16(e + 12, rd16(e + 12) + (played > lost ? played - lost : 0));
        wr16(e + 14, rd16(e + 14) + lost);
    }
}

/* ---- leaders and the Hall of Fame: one pass over a player's history stream -------------------------------- */
/* history fields of the 10 leader categories: passing yards, TD, rushing yards, TD, receptions, receiving yards,
   TD, sacks (half), interceptions, tackles */
static const u8 leader_field[10] = {8, 9, 2, 3, 12, 13, 14, 19, 20, 18};
#define FIELD_GAMES 0u
#define FIELD_CLUB 87u

typedef struct {
    i32 club_total[10];      /* seasons with this club (field 87 = club + 1, and the current season) */
    i32 career[10];          /* every live regular-season word, folded rows included */
    u32 seasons, honors, sb, main_club;
} Career;

static void read_career(u32 p, u32 club, Career *c) {
    zero((u8 *)c, sizeof(Career));
    const volatile u32 *w = (const volatile u32 *)G(p + 0x2C);
    if ((u32)w < 0x10000 || (u32)w >= 0x08000000)
        return;
    u32 current = (G(p + 0x24) >> 8) & 31, club_of[32], seen = 0;
    for (u32 s = 0; s < 32; s++)
        club_of[s] = 0;
    for (u32 n = 0; n < 4096; n++) {                           /* first: which club each season slot belongs to */
        u32 word = w[n];
        if (!(word & 0x30000000) && ((word >> 16) & 0x7F) == FIELD_CLUB)
            club_of[(word >> 23) & 31] = word & 0xFFFF;
        if (word & 0x80000000)
            break;
    }
    club_of[current] = club + 1;
    for (u32 n = 0; n < 4096; n++) {
        u32 word = w[n], field = (word >> 16) & 0x7F, slot = (word >> 23) & 31;
        i32 value = (i32)(i16)(word & 0xFFFF);
        if (!(word & 0x30000000)) {
            for (u32 k = 0; k < 10; k++)
                if (field == leader_field[k]) {
                    c->career[k] += value;
                    if (!(word & 0x40000000) && club_of[slot] == club + 1)
                        c->club_total[k] += value;
                }
            if (field == FIELD_GAMES && value > 0 && !(word & 0x40000000) && !(seen & (1u << slot))) {
                seen |= 1u << slot;
                c->seasons++;
            }
            if (field >= 96 && field <= 104 && field != 101 && value > 0)
                c->honors += (u32)value;                       /* MVP, POY, ROY, SB MVP, Pro Bowl, All-Pro */
            if (field == 101 && value > 0)
                c->sb += (u32)value;
        }
        if (word & 0x80000000)
            break;
    }
    u32 most = 0;                                              /* the club of the most recorded seasons */
    c->main_club = club;
    for (u32 k = 0; k < 32; k++) {
        u32 n = 0;
        for (u32 s = 0; s < 32; s++)
            n += club_of[s] == k + 1;
        if (n > most) {
            most = n;
            c->main_club = k;
        }
    }
}

/* insert (or update) a player in one top-N table, highest value first */
static void leader_insert(u8 *table, u32 depth, u32 p, u32 value, u32 index, u32 check, u32 new_flag) {
    if (!value)
        return;
    u32 at = depth;
    for (u32 r = 0; r < depth; r++) {                          /* already there (linked): drop the old entry */
        u8 *e = table + r * 16;
        if ((e[7] & 1) && rd16(e + 12) == index && rd16(e + 14) == check && index != 0xFFFF) {
            for (u32 j = r; j + 1 < depth; j++)
                copy(table + j * 16, table + (j + 1) * 16, 16);
            zero(table + (depth - 1) * 16, 16);
            break;
        }
    }
    for (u32 r = 0; r < depth; r++) {
        u8 *e = table + r * 16;
        if (!(e[7] & 1) || value > rd32(e + 8)) {
            at = r;
            break;
        }
    }
    if (at >= depth)
        return;
    for (u32 j = depth - 1; j > at; j--)
        copy(table + j * 16, table + (j - 1) * 16, 16);
    u8 *e = table + at * 16;
    zero(e, 16);
    pack_player(e, p);
    e[7] = (u8)(1 | 4 | new_flag);
    wr32(e + 8, value);
    wr16(e + 12, index);
    wr16(e + 14, check);
}

/* the entry this player is linked to (flags out: its real-history bit), or 0 */
static const u8 *linked(const u8 *table, u32 depth, u32 index, u32 check) {
    for (u32 r = 0; r < depth; r++) {
        const u8 *e = table + r * 16;
        if ((e[7] & 1) && rd16(e + 12) == index && rd16(e + 14) == check && index != 0xFFFF)
            return e;
    }
    return 0;
}

/* a linked entry adds this season to its own total; anyone else enters from the stream's total */
static void leader_update(u8 *table, u32 depth, u32 p, i32 computed, i32 season, u32 index, u32 check) {
    const u8 *e = linked(table, depth, index, check);
    u32 value = e ? rd32(e + 8) + (season > 0 ? (u32)season : 0) : (computed > 0 ? (u32)computed : 0);
    leader_insert(table, depth, p, value, index, check, e && (e[7] & 2) ? 2 : 8);
}

/* Hall of Fame score (j6 tunes the constants in nfl2k5_history.HALL_RULE; keep the two in step) */
static u32 hall_score(u32 position, const Career *c) {
    i32 v = (i32)c->honors * 40 + (i32)c->sb * 15 + (i32)c->seasons * 6;
    switch (position) {
    case 0:  v += c->career[1] / 2 + c->career[0] / 400; break;                     /* QB: TD, yards */
    case 7: case 8: v += c->career[2] / 120 + c->career[3] * 2; break;              /* HB, FB */
    case 3: case 9: v += c->career[4] / 10 + c->career[5] / 150 + c->career[6] * 2; break; /* WR, TE */
    case 10: case 11: case 15: case 16: v += c->career[7] / 2 + c->career[9] / 12 + c->career[8] * 3; break;
    case 4: case 5: case 6: v += c->career[8] * 5 + c->career[9] / 15; break;       /* CB, FS, SS */
    default: v += (i32)c->seasons * 6; break;                                        /* the line, kickers */
    }
    return v > 0 ? (u32)v : 0;
}

static void close_players(u8 *b, u32 year) {
    u32 saved = G(CLASS), teams = TEAM_COUNT();
    u8 *hall = b + HALL_AT;
    CLASS_SET(0);
    if (teams > 32)
        teams = 32;
    for (u32 i = 0; i < teams; i++) {
        u32 team = TEAM_AT(i), guard = 0;
        if (!team)
            continue;
        for (u32 p = TEAM_FIRST(team); p && guard < 128; p = TEAM_NEXT(team, p), guard++) {
            if (!good_player(p))
                continue;
            /* single-season records */
            if (hst_config.flags & 1)
                for (u32 c = 0; c < 12; c++)
                    consider_record(b, i, c, 1, STAT(p, season_field[c]), p, year, 0);
            u32 index = player_index(p), check = rd16((const u8 *)(p + 6));
            Career career;
            if ((hst_config.flags & 0x0C) == 0)
                continue;
            read_career(p, i, &career);
            if (hst_config.flags & 4)
                for (u32 k = 0; k < 10; k++) {
                    i32 season = STAT(p, leader_field[k]);
                    leader_update(b + LEADERS_AT + 16 + (i * 10 + k) * 3 * 16, 3, p, career.club_total[k], season,
                                  index, check);
                    leader_update(b + LEADERS_AT + LEAGUE_LEADERS + k * 5 * 16, 5, p, career.career[k], season,
                                  index, check);
                }
            /* a retiree becomes a Hall of Fame candidate */
            if ((hst_config.flags & 8) && (B(p + 8) & 8) && hall[1] < 64) {
                u32 score = hall_score(B(p + 0x35), &career);
                u8 *e = hall + CANDIDATES_AT + hall[1] * 24;
                u32 dup = 0;
                for (u32 k = 0; k < hall[1]; k++) {
                    u8 *o = hall + CANDIDATES_AT + k * 24;
                    u8 name[7];
                    pack_player(name, p);
                    u32 same = 1;
                    for (u32 j = 0; j < 7; j++)
                        same &= o[j] == name[j];
                    if (same && rd16(o + 8) + 1 >= year)
                        dup = 1;                               /* the same man retiring again this or last season */
                }
                if (!dup && score) {
                    zero(e, 24);
                    pack_player(e, p);
                    e[7] = (u8)(career.main_club + 1);
                    wr16(e + 8, year);
                    wr16(e + 10, score > 0xFFFF ? 0xFFFF : score);
                    e[12] = (u8)(career.seasons > 255 ? 255 : career.seasons);
                    e[13] = 1;
                    u32 pos = B(p + 0x35), k1 = 0, k2 = 0, k3 = 0;
                    if (pos == 0) { k1 = (u32)career.career[1]; k2 = (u32)career.career[0] / 1000; }
                    else if (pos == 7 || pos == 8) { k1 = (u32)career.career[2]; k2 = (u32)career.career[3]; k3 = (u32)career.career[4]; }
                    else if (pos == 3 || pos == 9) { k1 = (u32)career.career[4]; k2 = (u32)career.career[5]; k3 = (u32)career.career[6]; }
                    else { k1 = (u32)career.career[9]; k2 = (u32)career.career[7]; k3 = (u32)career.career[8]; }
                    wr16(e + 14, k1 > 0xFFFF ? 0xFFFF : k1);
                    wr16(e + 16, k2 > 0xFFFF ? 0xFFFF : k2);
                    wr16(e + 18, k3 > 0xFFFF ? 0xFFFF : k3);
                    e[20] = (u8)(career.honors > 255 ? 255 : career.honors);
                    e[21] = (u8)(career.sb > 255 ? 255 : career.sb);
                    hall[1]++;
                }
            }
        }
    }
    CLASS_SET(saved);
}

/* this year's class: eligible candidates (retired at least hall_wait seasons ago) at or over the bar, best first */
static void close_hall(u8 *b, u32 year) {
    u8 *hall = b + HALL_AT;
    u32 inducted = 0, wait = hst_config.hall_wait, window = hst_config.hall_window, bar = hst_config.hall_bar;
    u32 most = hst_config.hall_class;
    if (rd16(hall + 2) == year)
        return;                                                /* this year's class is already in */
    while (inducted < most && hall[0] < 192) {
        u32 pick = 0xFF, best = 0;
        for (u32 k = 0; k < hall[1] && k < 64; k++) {
            u8 *e = hall + CANDIDATES_AT + k * 24;
            u32 retired = rd16(e + 8), score = rd16(e + 10);
            if ((e[13] & 1) && retired + wait <= year && score >= bar && score > best) {
                best = score;
                pick = k;
            }
        }
        if (pick == 0xFF)
            break;
        u8 *e = hall + CANDIDATES_AT + pick * 24, *in = hall + 16 + hall[0] * 16;
        zero(in, 16);
        copy(in, e, 8);                                        /* person + main club */
        wr16(in + 8, year);
        wr16(in + 10, rd16(e + 8));
        in[12] = (u8)(1 | (e[13] & 2) | 4);
        in[13] = e[12];
        wr16(in + 14, rd16(e + 10));
        hall[0]++;
        e[13] = 0;                                              /* inducted: no longer a candidate */
        inducted++;
    }
    /* drop inducted candidates and those past their window; keep the list packed */
    u32 keep = 0;
    for (u32 k = 0; k < hall[1] && k < 64; k++) {
        u8 *e = hall + CANDIDATES_AT + k * 24;
        u32 retired = rd16(e + 8);
        if (!(e[13] & 1) || retired + wait + window < year)
            continue;
        if (keep != k)
            copy(hall + CANDIDATES_AT + keep * 24, e, 24);
        keep++;
    }
    for (u32 k = keep; k < hall[1] && k < 64; k++)
        zero(hall + CANDIDATES_AT + k * 24, 24);
    hall[1] = (u8)keep;
    wr16(hall + 2, year);
}

void FC history_season_close(void) {
    if (G(LEAGUE_MODE) != 2)
        return;
    u32 weeks = B(WEEKS_VA), sb = B(SB_ROW_IMM);
    if (weeks < 1 || weeks > 18 || sb < weeks || sb > 21)
        return;
    u8 *b = body(1);
    if (!b)
        return;
    u32 year = season_year();
    if (year < 1901 || year > 2155) {
        info_error(b, 1);
        return;
    }
    Line lines[32];
    tally_season(lines, weeks, sb);
    close_seasons(b, lines, year, weeks, sb);
    close_totals(b, lines, year);
    close_players(b, year);
    if (hst_config.flags & 8)
        close_hall(b, year);
    info_add(b, 0x20);
}
