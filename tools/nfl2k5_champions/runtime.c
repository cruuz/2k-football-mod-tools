/* Super Bowl champion pop-up, champions history and modern award voting (job hn1, beta 79). EXPERIMENTAL / UNWITNESSED.

   Freestanding i386 code for the late allocator owner nfl2k5_champions, built by tools/nfl2k5_champions_build.py into
   mod_editor/core/nfl2k5_champions_code.py; no retail bytes live here. Game routines are called through their fixed
   retail addresses; the only relocations are this blob's own labels. The blob owns no writable memory: the champions
   history lives in the spare bytes at the end of the roster arena (see HISTORY below), the pop-up text on the stack.

   HISTORY. The roster arena ends with a 0x400-byte region: the 352-byte reserve block (magic "2K5RSV2") written by the
   practice-squad owner, 448 bytes that are zero in every arena the Studio builds, and the game's own 224-byte tail. The
   448 bytes are kept as one checked block (the arena is saved whole with every franchise, so the history costs no save
   size and an old save simply has no block):
     +0 magic "2K5CHMP\0", +8 version 1, +9 ring size (22), +12 Adler-32 of bytes 0..11 and 16..433,
     +16 22 entries of 19 bytes, entry n % 22 holding Super Bowl number n:
       [0] n, [1..3] champion + 1 (6 bits), runner-up + 1 (6), champion points (6), runner-up points (6),
       [4..10] Super Bowl MVP, [11..17] season MVP (each 55 bits: initial, nine letters, position code; five bits each),
       [18] the season MVP's club + 1.
   A block or entry that fails its checks reads as empty, so a foreign write can only lose history, never show a wrong
   champion; with no reserve block (an arena without the Studio's reserve schema) the history is simply off. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef short i16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))

/* the game's text context and helpers (as the Player Card honors page uses them) */
#define TEXT_INIT  ((void (FC *)(void *))0x00046920)
#define TEXT_FONT  ((void (FC *)(void *, u32))0x000469B0)
#define TEXT_ALIGN ((void (FC *)(void *, u32))0x00046A00)
#define TEXT_POS   ((void (FC *)(void *, float, float, float))0x00046A70)
#define TEXT_COLOR ((void (FC *)(void *, u32))0x00046B50)
#define TEXT_WIDTH ((i32 (FC *)(void *, const u16 *))0x00046C50)
#define TEXT_DRAW  ((void (FC *)(void *, const u16 *))0x000F1C70)
#define FONT_GET   ((u32 (FC *)(u32))0x000EF850)
#define NOTICE     ((void (FC *)(u32, const u16 *))0x0014E520)   /* modal one-button information dialog */
#define CLASS_SET  ((void (FC *)(u32))0x0014EDB0)
#define STAT       ((i32 (FC *)(u32, u32))0x0014EE40)             /* current season value of a history field */
#define HOME_SCORE ((i32 (FC *)(u32, u32))0x000C5110)
#define AWAY_SCORE ((i32 (FC *)(u32, u32))0x000C5150)
#define HOME_TEAM  ((u32 (FC *)(u32, u32))0x000C4E00)
#define AWAY_TEAM  ((u32 (FC *)(u32, u32))0x000C4E20)
#define TEAM_FIRST ((u32 (FC *)(u32))0x000C3E70)
#define TEAM_NEXT  ((u32 (FC *)(u32, u32))0x000C3E80)
#define TEAM_COUNT ((u32 (*)(void))0x000C6430)
#define TEAM_AT    ((u32 (FC *)(u32))0x000C4C50)
#define WINS       ((u32 (FC *)(u32))0x000C7720)
#define LOSSES     ((u32 (FC *)(u32))0x000C7750)
#define TIES       ((u32 (FC *)(u32))0x000C7780)

#define CARD_YEAR_IMM 0x003204ADu   /* the card's year base: mov ecx, base_year + 11 */
#define SB_ROW_IMM 0x00133A41u      /* the Super Bowl week row: 0x14 retail, 0x15 with the 18-week season */
#define SEASONS 0x00E576B8u
#define LEAGUE_MODE 0x00E576A0u
#define CLASS 0x00BD7F98u
#define ROSTER 0x00B72918u          /* the roster object (the arena root) */
#define ARENA_SIZE 0x00B72808u      /* the arena length */
#define AWARDS 0x00E5A2F0u
#define POS_NAMES 0x004F26D0u       /* 17 pointers to the position abbreviations */
#define BLACK 0xFF101010u

/* ---- small text helpers ------------------------------------------------------------------------------------ */
static u16 *put_text(u16 *out, const u16 *text) {
    if (text)
        while (*text)
            *out++ = *text++;
    return out;
}

static u16 *put_uint(u16 *out, u32 value) {
    u16 digits[10];
    u32 n = 0;
    do {
        digits[n++] = (u16)('0' + value % 10);
        value /= 10;
    } while (value && n < 10);
    while (n)
        *out++ = digits[--n];
    return out;
}

static u16 *put_roman(u16 *out, u32 n) {
    static const u16 value[9] = {100, 90, 50, 40, 10, 9, 5, 4, 1};
    static const char symbol[9][3] = {"C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"};
    for (u32 i = 0; i < 9; i++)
        while (n >= value[i]) {
            for (const char *s = symbol[i]; *s; s++)
                *out++ = (u16)*s;
            n -= value[i];
        }
    return out;
}

static u16 *put_ascii(u16 *out, const char *text) {
    while (*text)
        *out++ = (u16)(u8)*text++;
    return out;
}

/* ---- season identity ----------------------------------------------------------------------------------------- */
static u32 season_year(void) {
    return (u32)((i32)G(CARD_YEAR_IMM) - 11) + G(SEASONS);
}

/* Super Bowl number of the season: Super Bowl I closed the 1966 season. */
static u32 sb_number(void) {
    u32 year = season_year();
    return year > 1966 && year - 1965 < 256 ? year - 1965 : 0;
}

static u32 team_index(u32 team) {
    u32 base = TEAM_AT(0);
    return team >= base && (team - base) % 500 == 0 ? (team - base) / 500 : 0xFFFF;
}

/* ---- the history block ---------------------------------------------------------------------------------------- */
#define RING 22u
#define ENTRY 19u
#define ENTRIES_AT 16u
#define USED (ENTRIES_AT + RING * ENTRY)

/* the 448 spare bytes after the reserve block at the end of the arena, or 0 when this arena has none */
static u8 *gap(void) {
    u32 root = G(ROSTER), size = G(ARENA_SIZE);
    if (!root || size < 0x2000 || size > 0x400000)
        return 0;
    u32 block = root + size - 0x400;
    return G(block) == 0x52354B32 && G(block + 4) == 0x00325653 ? (u8 *)(block + 352) : 0;
}

static u32 adler(const u8 *p, u32 n, u32 a, u32 b) {
    for (u32 i = 0; i < n; i++) {
        a = (a + p[i]) % 65521;
        b = (b + a) % 65521;
    }
    return (b << 16) | a;
}

static u32 block_sum(const u8 *g) {
    u32 first = adler(g, 12, 1, 0);
    return adler(g + ENTRIES_AT, USED - ENTRIES_AT, first & 0xFFFF, first >> 16);
}

static const u8 magic[8] = {'2', 'K', '5', 'C', 'H', 'M', 'P', 0};

static u32 block_ok(const u8 *g) {
    for (u32 i = 0; i < 8; i++)
        if (g[i] != magic[i])
            return 0;
    return g[8] == 1 && g[9] == RING && block_sum(g) == (u32)g[12] + ((u32)g[13] << 8) + ((u32)g[14] << 16) + ((u32)g[15] << 24);
}

static void seal(u8 *g) {
    u32 sum = block_sum(g);
    g[12] = (u8)sum;
    g[13] = (u8)(sum >> 8);
    g[14] = (u8)(sum >> 16);
    g[15] = (u8)(sum >> 24);
}

/* Entry for Super Bowl n of a block that has already been checked (block_ok), or 0 when the entry itself is empty or
   not in its own ring slot. */
static const u8 *entry_at(const u8 *g, u32 n) {
    if (!n)
        return 0;
    const u8 *e = g + ENTRIES_AT + (n % RING) * ENTRY;
    u32 t = (u32)e[1] + ((u32)e[2] << 8) + ((u32)e[3] << 16), champion = t & 63, runner = t >> 6 & 63;
    return e[0] == n && champion >= 1 && champion <= 32 && runner >= 1 && runner <= 32 ? e : 0;
}

static u32 sym5(u32 c) {
    if (c >= 'a' && c <= 'z')
        c -= 32;
    if (c >= 'A' && c <= 'Z')
        return c - 'A' + 1;
    return c == '-' ? 27 : c == '.' ? 28 : c == '\'' ? 29 : c == ' ' ? 30 : 31;
}

static u32 chr5(u32 s) {
    if (s >= 1 && s <= 26)
        return 'A' + s - 1;
    return s == 27 ? '-' : s == 28 ? '.' : s == 29 ? '\'' : s == 30 ? ' ' : '?';
}

static void put_bits(u8 *out, u32 at, u32 value, u32 count) {
    for (u32 b = 0; b < count; b++)
        if (value >> b & 1)
            out[(at + b) >> 3] |= (u8)(1u << ((at + b) & 7));
}

static u32 get_bits(const u8 *in, u32 at, u32 count) {
    u32 value = 0;
    for (u32 b = 0; b < count; b++)
        if (in[(at + b) >> 3] >> ((at + b) & 7) & 1)
            value |= 1u << b;
    return value;
}

/* Length of a last name without a generational suffix ("Walker III" -> 6, "Harrison Jr." -> 8). */
static u32 name_length(const u16 *last) {
    u32 n = 0, space = 0;
    if (!last)
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

/* first initial + up to nine letters of the last name + the position code: 55 bits in 7 bytes */
static void pack_person(u8 *out, u32 player) {
    const u16 *first = (const u16 *)G(player + 0x10), *last = (const u16 *)G(player + 0x14);
    u32 at = 5, length = name_length(last);
    for (u32 i = 0; i < 7; i++)
        out[i] = 0;
    put_bits(out, 0, first && first[0] ? sym5(first[0]) : 0, 5);
    for (u32 i = 0; i < 9; i++, at += 5)
        put_bits(out, at, i < length ? sym5(last[i]) : 0, 5);
    put_bits(out, at, B(player + 0x35) & 31, 5);
}

/* "K. WALKER I, HB" */
static u16 *put_person(u16 *out, const u8 *in) {
    u32 first = get_bits(in, 0, 5), pos = get_bits(in, 50, 5);
    if (first) {
        *out++ = (u16)chr5(first);
        *out++ = '.';
        *out++ = ' ';
    }
    for (u32 i = 0; i < 9; i++) {
        u32 s = get_bits(in, 5 + 5 * i, 5);
        if (!s)
            break;
        *out++ = (u16)chr5(s);
    }
    if (pos < 17) {
        *out++ = ',';
        *out++ = ' ';
        out = put_text(out, (const u16 *)G(POS_NAMES + 4 * pos));
    }
    return out;
}

static u16 *put_full_name(u16 *out, u32 player) {
    out = put_text(out, (const u16 *)G(player + 0x10));
    *out++ = ' ';
    return put_text(out, (const u16 *)G(player + 0x14));
}

/* ---- recording ---------------------------------------------------------------------------------------------- */
static void record_season(u32 n, u32 champion, u32 runner_up, u32 champion_points, u32 runner_points, u32 sb_mvp,
                          u32 mvp, u32 mvp_team) {
    u8 *g = gap();
    if (!g)
        return;
    if (!block_ok(g)) {                                   /* a new or unreadable block starts empty */
        for (u32 i = 0; i < USED; i++)
            g[i] = 0;
        for (u32 i = 0; i < 8; i++)
            g[i] = magic[i];
        g[8] = 1;
        g[9] = RING;
    }
    u8 *e = g + ENTRIES_AT + (n % RING) * ENTRY;
    for (u32 i = 0; i < ENTRY; i++)
        e[i] = 0;
    champion_points = champion_points > 63 ? 63 : champion_points;
    runner_points = runner_points > 63 ? 63 : runner_points;
    u32 t = (champion + 1) | (runner_up + 1) << 6 | champion_points << 12 | runner_points << 18;
    e[0] = (u8)n;
    e[1] = (u8)t;
    e[2] = (u8)(t >> 8);
    e[3] = (u8)(t >> 16);
    if (sb_mvp)
        pack_person(e + 4, sb_mvp);
    if (mvp) {
        pack_person(e + 11, mvp);
        e[18] = (u8)(mvp_team < 32 ? mvp_team + 1 : 0);
    }
    seal(g);
}

/* Called from the stage-9 advance (0x2485FA) before the retail rollover: the Super Bowl row is still in the grid and the
   season object still holds the Super Bowl MVP and the season MVP. */
void FC champions_advance_notice(u32 menu) {
    u32 row = B(SB_ROW_IMM), n = sb_number();
    if (G(LEAGUE_MODE) != 2 || !n || row < 0x10 || row > 0x20)
        return;
    i32 home = HOME_SCORE(row, 0), away = AWAY_SCORE(row, 0);
    if (home == away)
        return;
    u32 winner = home > away ? HOME_TEAM(row, 0) : AWAY_TEAM(row, 0);
    u32 loser = home > away ? AWAY_TEAM(row, 0) : HOME_TEAM(row, 0);
    u32 w = team_index(winner), l = team_index(loser);
    if (w > 31 || l > 31 || w == l)
        return;
    u32 high = (u32)(home > away ? home : away), low = (u32)(home > away ? away : home);
    u32 sb_mvp = G(AWARDS + 0x5888), mvp = G(AWARDS + 0x5800), mvp_team = 0xFFFF;
    if (mvp) {
        u32 t = G(AWARDS + 0x5804);
        mvp_team = t < 32 ? t : team_index(t);
    }
    record_season(n, w, l, high, low, sb_mvp, mvp, mvp_team);
    u16 text[256], *out = text;
    out = put_text(out, (const u16 *)G(winner + 0x138));
    *out++ = ' ';
    out = put_text(out, (const u16 *)G(winner + 0x104));
    out = put_ascii(out, " won Super Bowl ");
    out = put_roman(out, n);
    out = put_ascii(out, ", ");
    out = put_uint(out, high);
    *out++ = '-';
    out = put_uint(out, low);
    out = put_ascii(out, " over the ");
    out = put_text(out, (const u16 *)G(loser + 0x138));
    *out++ = ' ';
    out = put_text(out, (const u16 *)G(loser + 0x104));
    out = put_ascii(out, ".");
    if (sb_mvp) {
        out = put_ascii(out, "\nSuper Bowl MVP: ");
        out = put_full_name(out, sb_mvp);
        out = put_ascii(out, ", ");
        out = put_text(out, (const u16 *)G(POS_NAMES + 4 * (B(sb_mvp + 0x35) < 17 ? B(sb_mvp + 0x35) : 0)));
    }
    if (mvp) {
        out = put_ascii(out, "\nSeason MVP: ");
        out = put_full_name(out, mvp);
        out = put_ascii(out, ", ");
        out = put_text(out, (const u16 *)G(POS_NAMES + 4 * (B(mvp + 0x35) < 17 ? B(mvp + 0x35) : 0)));
    }
    *out = 0;
    NOTICE(menu, text);
}

/* ---- Player Card page 3: the champions ------------------------------------------------------------------------ */
static const float slot_x[2] = {310.0f, 490.0f};
static const float slot_y[5] = {318.0f, 333.0f, 347.0f, 362.0f, 377.0f};
static const float line_y[3] = {137.0f, 154.0f, 171.0f};

static void text_start(u32 *ctx, u32 font, u32 align) {
    TEXT_INIT(ctx);
    TEXT_COLOR(ctx, BLACK);
    TEXT_FONT(ctx, FONT_GET(font));
    TEXT_ALIGN(ctx, align);
}

/* The checked block, or 0 when this arena has none or it is empty or damaged. */
static const u8 *history_block(void) {
    const u8 *g = gap();
    return g && block_ok(g) ? g : 0;
}

static u32 newest_season(const u8 *g) {
    u32 best = 0;
    for (u32 i = 0; g && i < RING; i++) {
        u32 n = g[ENTRIES_AT + i * ENTRY];
        if (n > best && entry_at(g, n))
            best = n;
    }
    return best;
}

static u16 *put_abbr(u16 *out, u32 index_plus_one) {
    u32 team = TEAM_AT(index_plus_one - 1);
    return team ? put_text(out, (const u16 *)G(team + 0x108)) : out;
}

static u32 entry_champion(const u8 *e) { return ((u32)e[1] + ((u32)e[2] << 8) + ((u32)e[3] << 16)) & 63; }
static u32 entry_runner_up(const u8 *e) { return (((u32)e[1] + ((u32)e[2] << 8) + ((u32)e[3] << 16)) >> 6) & 63; }
static u32 entry_champion_points(const u8 *e) { return (((u32)e[1] + ((u32)e[2] << 8) + ((u32)e[3] << 16)) >> 12) & 63; }
static u32 entry_runner_points(const u8 *e) { return (((u32)e[1] + ((u32)e[2] << 8) + ((u32)e[3] << 16)) >> 18) & 63; }

/* Rating panel: the ten newest seasons in the ring, "YEAR ABBR" right-aligned at x - 8 and "pts-pts ABBR" at x. */
void champions_ratings(void) {
    const u8 *g = history_block();
    u32 ctx[32], newest = newest_season(g), shown = 0;
    u16 label[24], value[24];
    for (u32 n = newest; n && n + RING > newest && shown < 10; n--) {
        const u8 *e = entry_at(g, n);
        u16 *out = label;
        if (!e)
            continue;
        float x = slot_x[shown / 5], y = slot_y[shown % 5];
        shown++;
        out = put_uint(out, n + 1965);
        *out++ = ' ';
        out = put_abbr(out, entry_champion(e));
        *out = 0;
        out = value;
        out = put_uint(out, entry_champion_points(e));
        *out++ = '-';
        out = put_uint(out, entry_runner_points(e));
        *out++ = ' ';
        out = put_abbr(out, entry_runner_up(e));
        *out = 0;
        text_start(ctx, 3, 2);
        TEXT_POS(ctx, x - 8.0f, y, 20.0f);
        TEXT_DRAW(ctx, label);
        TEXT_ALIGN(ctx, 1);
        TEXT_POS(ctx, x, y, 20.0f);
        TEXT_DRAW(ctx, value);
    }
}

/* Bio lines: the newest Super Bowl in words, its MVP and the season MVP. */
void champions_bio(void) {
    const u8 *g = history_block();
    u32 ctx[32], newest = newest_season(g);
    u16 text[96], *out;
    const u8 *e = newest ? entry_at(g, newest) : 0;
    u32 lines = 0;
    if (!e) {
        out = put_ascii(text, "CHAMPIONS: NONE YET");
        *out = 0;
        text_start(ctx, 8, 1);
        TEXT_POS(ctx, 198.0f, line_y[0], 20.0f);
        TEXT_DRAW(ctx, text);
        return;
    }
    out = put_ascii(text, "SUPER BOWL ");
    out = put_roman(out, newest);
    out = put_ascii(out, ": ");
    out = put_abbr(out, entry_champion(e));
    *out++ = ' ';
    out = put_uint(out, entry_champion_points(e));
    *out++ = '-';
    out = put_uint(out, entry_runner_points(e));
    *out++ = ' ';
    out = put_abbr(out, entry_runner_up(e));
    *out = 0;
    text_start(ctx, 8, 1);
    TEXT_POS(ctx, 198.0f, line_y[lines++], 20.0f);
    TEXT_DRAW(ctx, text);
    if (get_bits(e + 4, 0, 5) | get_bits(e + 4, 5, 5)) {
        out = put_ascii(text, "SB MVP: ");
        out = put_person(out, e + 4);
        *out = 0;
        text_start(ctx, 8, 1);
        TEXT_POS(ctx, 198.0f, line_y[lines++], 20.0f);
        TEXT_DRAW(ctx, text);
    }
    if (get_bits(e + 11, 0, 5) | get_bits(e + 11, 5, 5)) {
        out = put_ascii(text, "MVP: ");
        out = put_person(out, e + 11);
        if (e[18]) {
            out = put_ascii(out, " (");
            out = put_abbr(out, e[18]);
            *out++ = ')';
        }
        *out = 0;
        text_start(ctx, 8, 1);
        TEXT_POS(ctx, 198.0f, line_y[lines++], 20.0f);
        TEXT_DRAW(ctx, text);
    }
}

/* ---- modern award voting -------------------------------------------------------------------------------------- */
enum { P_QB, P_K, P_P, P_WR, P_CB, P_FS, P_SS, P_HB, P_FB, P_TE, P_OLB, P_ILB, P_C, P_G, P_T, P_DT, P_DE };
typedef struct {
    i32 pass_yds, pass_td, pass_int, rush_yds, rush_td, rec, rec_yds, rec_td, tackles, sacks2, def_int, ff;
} Line;

/* Production in hundredths of a point: 1 point per 25 passing yards, 4 per passing TD, -2 per interception, 1 per 10
   rushing or receiving yards, 6 per touchdown, half a point per catch; 2 per sack, 0.4 per tackle, 8 per interception,
   3 per forced fumble. */
static i32 offense_points(const Line *s) {
    i32 v = s->pass_yds * 4 + s->pass_td * 400 - s->pass_int * 200 + s->rush_yds * 10 + s->rush_td * 600 +
            s->rec_yds * 10 + s->rec * 50 + s->rec_td * 600;
    return v > 0 ? v : 0;
}

static i32 defense_points(const Line *s) {
    i32 v = s->sacks2 * 200 + s->tackles * 40 + s->def_int * 800 + s->ff * 300;
    return v > 0 ? v : 0;
}

/* percent weights by position code: MVP (offense and defense), offensive and defensive player of the year */
static const u8 mvp_weight[17] = {100, 0, 0, 58, 38, 36, 36, 60, 40, 48, 40, 40, 0, 0, 0, 44, 44};
static const u8 opoy_weight[17] = {72, 0, 0, 100, 0, 0, 0, 100, 55, 88, 0, 0, 0, 0, 0, 0, 0};
static const u8 dpoy_weight[17] = {0, 0, 0, 0, 108, 96, 96, 0, 0, 0, 100, 92, 0, 0, 0, 100, 100};

/* Otherworldly seasons, as a percentage of a mark nobody has reached in the NFL: a single one at 100 or more wins MVP. */
static u32 otherworldly(const Line *s) {
    u32 r = 0, v;
    v = (u32)(s->sacks2 > 0 ? s->sacks2 : 0) * 100 / 60;          /* 30 sacks (record 22.5) */
    r = v > r ? v : r;
    v = (u32)(s->tackles > 0 ? s->tackles : 0) * 100 / 300;       /* 300 tackles */
    r = v > r ? v : r;
    v = (u32)(s->rush_yds > 0 ? s->rush_yds : 0) * 100 / 2500;    /* 2,500 rushing yards (record 2,105) */
    r = v > r ? v : r;
    v = (u32)(s->rec_yds > 0 ? s->rec_yds : 0) * 100 / 2200;      /* 2,200 receiving yards (record 1,964) */
    r = v > r ? v : r;
    v = (u32)(s->pass_yds > 0 ? s->pass_yds : 0) * 100 / 6000;    /* 6,000 passing yards (record 5,477) */
    r = v > r ? v : r;
    v = (u32)(s->pass_td > 0 ? s->pass_td : 0) * 100 / 60;        /* 60 passing touchdowns (record 55) */
    r = v > r ? v : r;
    v = (u32)(s->def_int > 0 ? s->def_int : 0) * 100 / 15;        /* 15 interceptions (record 14) */
    r = v > r ? v : r;
    return r;
}

static void read_line(u32 p, Line *s) {
    s->pass_yds = STAT(p, 8);
    s->pass_td = STAT(p, 9);
    s->pass_int = STAT(p, 10);
    s->rush_yds = STAT(p, 2);
    s->rush_td = STAT(p, 3);
    s->rec = STAT(p, 12);
    s->rec_yds = STAT(p, 13);
    s->rec_td = STAT(p, 14);
    s->tackles = STAT(p, 18);
    s->sacks2 = STAT(p, 19);
    s->def_int = STAT(p, 20);
    s->ff = STAT(p, 21);
}

/* Team success factor in percent from the regular-season record: 35 at .400 or worse, 100 at .750 or better. */
static u32 team_factor(u32 team) {
    u32 w = WINS(team), l = LOSSES(team), t = TIES(team), g = w + l + t;
    u32 pct = g ? (2 * w + t) * 500 / g : 0;
    if (pct <= 400)
        return 35;
    return pct >= 750 ? 100 : 35 + (pct - 400) * 65 / 350;
}

typedef struct { u32 score, player, team; } Pick;

static void consider(Pick *pick, u32 score, u32 player, u32 team) {
    if (score > pick->score) {
        pick->score = score;
        pick->player = player;
        pick->team = team;
    }
}

static u32 offense_side(u32 pos) {
    return pos == P_QB || pos == P_HB || pos == P_FB || pos == P_WR || pos == P_TE;
}

/* After the retail award pass of the final regular week (hook at 0x116E55): replace MVP, OPOY, DPOY, OROY, DROY.
   Pass 0 picks the MVP (an otherworldly season first, else production x position weight x team success); pass 1 picks the
   other four, the MVP excluded from OPOY and DPOY, the rookies (second season slot) from production alone. */
void champions_modern_awards(void) {
    Pick mvp = {0, 0, 0}, wonder = {0, 0, 0}, opoy = {0, 0, 0}, dpoy = {0, 0, 0}, oroy = {0, 0, 0}, droy = {0, 0, 0};
    u32 saved = G(CLASS), teams = TEAM_COUNT(), exclude = 0;
    CLASS_SET(0);
    for (u32 pass = 0; pass < 2; pass++) {
        for (u32 i = 0; i < teams; i++) {
            u32 team = TEAM_AT(i);
            u32 factor = team ? team_factor(team) : 0;
            for (u32 p = team ? TEAM_FIRST(team) : 0; p; p = TEAM_NEXT(team, p)) {
                u32 pos = B(p + 0x35);
                if (pos > P_DE || pos == P_K || pos == P_P || pos == P_C || pos == P_G || pos == P_T)
                    continue;
                Line s;
                read_line(p, &s);
                u32 offense_side_player = offense_side(pos);
                u32 value = offense_side_player ? (u32)offense_points(&s) : (u32)defense_points(&s);
                if (pass == 0) {
                    u32 wild = otherworldly(&s);
                    consider(&wonder, wild >= 100 ? wild : 0, p, team);
                    consider(&mvp, value * mvp_weight[pos] * factor, p, team);
                    continue;
                }
                if (p != exclude) {
                    if (offense_side_player)
                        consider(&opoy, value * opoy_weight[pos], p, team);
                    else
                        consider(&dpoy, value * dpoy_weight[pos], p, team);
                }
                if (((G(p + 0x24) >> 8) & 31) == 1)
                    consider(offense_side_player ? &oroy : &droy, value, p, team);
            }
        }
        if (pass == 0) {
            if (wonder.player)
                mvp = wonder;
            exclude = mvp.player;
        }
    }
    CLASS_SET(saved);
    if (mvp.player) {
        G(AWARDS + 0x5800) = mvp.player;
        G(AWARDS + 0x5804) = mvp.team;
    }
    if (opoy.player) {
        G(AWARDS + 0x5810) = opoy.player;
        G(AWARDS + 0x5814) = opoy.team;
    }
    if (dpoy.player) {
        G(AWARDS + 0x5818) = dpoy.player;
        G(AWARDS + 0x581C) = dpoy.team;
    }
    if (oroy.player) {
        G(AWARDS + 0x5820) = oroy.player;
        G(AWARDS + 0x5824) = oroy.team;
    }
    if (droy.player) {
        G(AWARDS + 0x5828) = droy.player;
        G(AWARDS + 0x582C) = droy.team;
    }
}
