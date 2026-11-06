/* Franchise History screen, box scores from the Schedule and the Player Card game log (job b780 j4-history, beta 80).
   EXPERIMENTAL / UNWITNESSED.

   Freestanding i386 code for the late allocator owner nfl2k5_history_screen, built by tools/nfl2k5_history_screen_build.py
   into mod_editor/core/nfl2k5_history_screen_code.py; no retail bytes live here. Game routines are called through their
   fixed retail addresses. Four link symbols: this blob's own labels, hist_state (16 RW words of the owner), hist_ro (the
   owner's read-only block: descriptors, the cloned ESPN.com rows, the seeded real history) and hist_xtnd_ptr (the footer
   owner's word holding the address of the franchise extension footer in RAM, or 0 when no footer owner is installed: the
   franchise-made parts then read as empty).

   Every read of the footer or the seed tables is bounds-checked against the sizes stored with them, and anything that
   fails a check reads as empty, so a damaged or foreign footer can only hide history, never show a wrong line or read
   past a table. Nothing here writes outside hist_state and the stack.

   Screen (descriptor in hist_ro, layout league_news_common like Team Standings, handler 0xF3DA0 so B goes back):
     pages SEASONS, RECORDS, LEADERS, RECORD BOOK, AWARDS, HALL OF FAME: Black/White change the page, L/R the club (the
     award on AWARDS, the club filter on HALL OF FAME), Up/Down scroll. Ten 25-pixel row bars at y 88 + 30k, x 40..604
     (the Team Standings geometry), text in the standings font (4) and colours.
   Box score (second descriptor, pushed from the Schedule with X on a played game): line score by quarter from the
     league grid for every game; for a game kept in the footer, the team stats of both clubs and the player lines.
   Game log (Player Card page 4: the champions owner's page cycle finds hist_card_flip / hist_card_rows / hist_card_bio through the
     extension record this owner keeps just before its ESPN.com rows, see build_ro): one line per stored game of the
     card's player this season.
   The footer layout is the j23-footer contract (nfl2k5_franchise_extension, envelope 1, blocks version 1). */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef short i16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))

/* the game's text context and helpers (as Team Standings and the Player Card pages use them) */
#define TEXT_INIT  ((void (FC *)(void *))0x00046920)
#define TEXT_FONT  ((void (FC *)(void *, u32))0x000469B0)
#define TEXT_ALIGN ((void (FC *)(void *, u32))0x00046A00)
#define TEXT_POS   ((void (FC *)(void *, float, float, float))0x00046A70)
#define TEXT_COLOR ((void (FC *)(void *, u32))0x00046B50)
#define TEXT_STYLE ((void (FC *)(void *, u32))0x00046B60)
#define TEXT_WIDTH ((i32 (FC *)(void *, const u16 *))0x00046C50)
#define TEXT_DRAW  ((void (FC *)(void *, const u16 *))0x000F1C70)
#define FONT_GET   ((u32 (FC *)(u32))0x000EF850)
#define RECT       ((void (FC *)(u32, u32, float, float, float, float, float))0x0006BBE0)
/* league */
#define TEAM_AT    ((u32 (FC *)(u32))0x000C4C50)
#define TEAM_INDEX ((u32 (FC *)(u32))0x000C4CA0)
#define TEAM_COUNT ((u32 (*)(void))0x000C6430)
#define HOME_SCORE ((i32 (FC *)(u32, u32))0x000C5110)
#define AWAY_SCORE ((i32 (FC *)(u32, u32))0x000C5150)
/* pads and menus */
#define PAD_ON      ((u32 (FC *)(u32, u32))0x000709B0)
#define PAD_PRESSED ((u32 (FC *)(u32, u32))0x00070A10)
#define PAD_REPEAT  ((u32 (FC *)(u32, u32))0x00070A30)
#define PAD_CONSUME ((void (FC *)(u32, u32, u32))0x00070A50)
#define CURSOR_SOUND ((void (*)(void))0x0014D390)
#define SCREEN_PUSH ((void (FC *)(u32, u32))0x0006E390)

#define CARD_YEAR_IMM 0x003204ADu   /* the card's year base: mov ecx, base_year + 11 */
#define SEASONS 0x00E576B8u         /* seasons elapsed in this franchise */
#define LEAGUE_MODE 0x00E576A0u     /* 2 = Franchise */
#define FOCUS_TEAM 0x00E3C0A0u      /* the club the franchise menus follow (0x13EC80) */
#define HUMAN 0x00E5775Cu           /* nonzero per club index: user controlled (0xC4D50) */
#define GRID 0x00E57C40u            /* 22 rows x 17 cells x 8 bytes: state, home, away, month, day, year-2000, h, m */
#define SCORES 0x00E587F0u          /* 10 bytes per cell: home Q1..Q4, OT, away Q1..Q4, OT */
#define WEEKS_BYTE 0x005151C4u      /* regular-season weeks of this image (17 retail, 18 with the 2026 season) */
#define POS_NAMES 0x004F26D0u       /* 17 pointers to the position abbreviations */
#define CARD_PLAYER 0x00C90248u     /* the Player Card's player record */

#define GREY 0xFFC0C0C0u
#define YELLOW 0xFFC0C000u
#define WHITE 0xFFFFFFFFu
#define DIM 0xFF909090u
#define BLACK 0xFF101010u
#define BAR 0x80000000u
#define HEAD_BAR 0xA0101830u

extern volatile u32 hist_state[16];
extern const u8 hist_ro[];
/* the footer owner's RW word that holds the address of the footer body in RAM (static RW on most builds, the K128 extra
   heap on others), or no symbol (0) when no footer owner is installed */
extern const volatile u32 hist_xtnd_ptr[] __attribute__((weak));

/* state words */
#define S_PAGE 0
#define S_CLUB 1        /* club index; on AWARDS the award, on HALL OF FAME the filter (0 = all, k = club k-1) */
#define S_SCROLL 2
#define S_AWARD 3
#define S_FILTER 4
#define S_BOX_ROW 5
#define S_BOX_SLOT 6
#define S_BOX_SCROLL 7

/* ---- small text helpers ------------------------------------------------------------------------------------ */
static u16 *put_text(u16 *out, const u16 *text, u32 limit) {
    if (text)
        while (*text && limit--)
            *out++ = *text++;
    *out = 0;
    return out;
}

static u16 *put_ascii(u16 *out, const char *text) {
    while (*text)
        *out++ = (u16)(u8)*text++;
    *out = 0;
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
    *out = 0;
    return out;
}

/* 5,477 */
static u16 *put_thousands(u16 *out, u32 value) {
    if (value >= 1000) {
        out = put_thousands(out, value / 1000);
        *out++ = ',';
        u32 rest = value % 1000;
        *out++ = (u16)('0' + rest / 100);
        *out++ = (u16)('0' + rest / 10 % 10);
        *out++ = (u16)('0' + rest % 10);
        *out = 0;
        return out;
    }
    return put_uint(out, value);
}

static u16 *put_int(u16 *out, i32 value) {
    if (value < 0) {
        *out++ = '-';
        return put_uint(out, 0u - (u32)value);
    }
    return put_uint(out, (u32)value);
}

/* half units (sacks are counted in halves): 12.5 */
static u16 *put_halves(u16 *out, u32 halves) {
    out = put_uint(out, halves / 2);
    if (halves & 1)
        out = put_ascii(out, ".5");
    return out;
}

static u16 *put_record(u16 *out, u32 w, u32 l, u32 t) {
    out = put_uint(out, w);
    *out++ = '-';
    out = put_uint(out, l);
    if (t) {
        *out++ = '-';
        out = put_uint(out, t);
    }
    *out = 0;
    return out;
}

static u16 *put_ordinal(u16 *out, u32 n) {
    out = put_uint(out, n);
    return put_ascii(out, n == 1 ? "ST" : n == 2 ? "ND" : n == 3 ? "RD" : "TH");
}

/* ---- drawing ------------------------------------------------------------------------------------------------ */
#define ROWS 10u
#define ROW_Y(r) (88.0f + 30.0f * (float)(r))
#define TEXT_Y(r) (ROW_Y(r) + 3.0f)

static void text_at(const u16 *text, float x, float y, u32 font, u32 align, u32 colour) {
    u32 ctx[32];
    if (!text || !*text)
        return;
    TEXT_INIT(ctx);
    TEXT_FONT(ctx, FONT_GET(font));
    TEXT_COLOR(ctx, colour);
    TEXT_ALIGN(ctx, align == 3 ? 1 : align);
    TEXT_STYLE(ctx, 1);
    if (align == 3)                                      /* centred: left-aligned at x minus half the width */
        x -= (float)(TEXT_WIDTH(ctx, text) / 2);
    TEXT_POS(ctx, x, y, 21.0f);
    TEXT_DRAW(ctx, text);
}

/* The largest of the game's menu fonts (the standings font 4, then 3, then 8) whose width (the game's own measure)
   fits `room` pixels; the narrowest when none does; font 4 when room is 0 (no limit). Absent fonts are skipped. */
static const u8 fit_fonts[3] = {4, 3, 8};

static u32 fit_font(const u16 *text, u32 room) {
    u32 ctx[32], best = 4;
    i32 narrow = 0x7FFFFFFF;
    if (!room)
        return 4;
    for (u32 k = 0; k < 3; k++) {
        u32 handle = FONT_GET(fit_fonts[k]);
        if (!handle)
            continue;
        TEXT_INIT(ctx);
        TEXT_FONT(ctx, handle);
        i32 w = TEXT_WIDTH(ctx, text);
        if (w <= (i32)room)
            return fit_fonts[k];
        if (w < narrow) {
            narrow = w;
            best = fit_fonts[k];
        }
    }
    return best;
}

/* one table cell in row r at x, at most `room` pixels wide (0 = no limit) */
static void cellw(u32 row, float x, u32 room, u32 align, const u16 *text, u32 colour) {
    if (text && *text)
        text_at(text, x, TEXT_Y(row), fit_font(text, room), align, colour);
}

static void cell(u32 row, float x, u32 align, const u16 *text, u32 colour) {
    cellw(row, x, 0, align, text, colour);
}

static void cellw_ascii(u32 row, float x, u32 room, u32 align, const char *text, u32 colour) {
    u16 buffer[48];
    put_ascii(buffer, text);
    cellw(row, x, room, align, buffer, colour);
}

static void cell_ascii(u32 row, float x, u32 align, const char *text, u32 colour) {
    cellw_ascii(row, x, 0, align, text, colour);
}

static void bars(u32 head) {
    for (u32 r = 0; r < ROWS; r++)
        RECT(r < head ? HEAD_BAR : BAR, 0, 40.0f, ROW_Y(r), 31.0f, 564.0f, 25.0f);
}

/* the sub-bar between the layout's L and R arrows (Team Standings draws its conference there) */
static void subtitle(const u16 *text) {
    text_at(text, 320.0f, 64.0f, 3, 3, BLACK);
}

static void legend(const char *line) {
    u16 buffer[96];
    put_ascii(buffer, line);
    text_at(buffer, 320.0f, 412.0f, 3, 3, GREY);
}

/* ---- the club table and names ----------------------------------------------------------------------------- */
static u32 team_count(void) {
    u32 n = TEAM_COUNT();
    return n > 32 ? 32 : n;
}

static u32 club(u32 index) {
    return index < 32 ? TEAM_AT(index) : 0;
}

static u16 *put_club_name(u16 *out, u32 index, u32 full) {
    u32 team = club(index);
    if (!team)
        return out;
    if (full) {
        out = put_text(out, (const u16 *)G(team + 0x138), 20);
        *out++ = ' ';
    }
    return put_text(out, (const u16 *)G(team + 0x104), 20);
}

static u16 *put_club_abbr(u16 *out, u32 index) {
    u32 team = club(index);
    return team ? put_text(out, (const u16 *)G(team + 0x108), 4) : out;
}

static u16 *put_position(u16 *out, u32 pos) {
    if (pos < 17)
        out = put_text(out, (const u16 *)G(POS_NAMES + 4 * pos), 5);
    return out;
}

/* ---- the read-only block (built by nfl2k5_history_screen.build_ro) -------------------------------------------- */
#define RO_U32(o) (*(const u32 *)(hist_ro + (o)))
#define RO_U16(o) (*(const u16 *)(hist_ro + (o)))
#define RO_U8(o) (hist_ro[(o)])
enum { RO_MAGIC, RO_SIZE, RO_CLUBS, RO_SEASONS, RO_SEASON_COUNT, RO_AWARDS, RO_HOF, RO_HOF_COUNT, RO_BOOK, RO_BOOK_COUNT,
       RO_CLUB_RECORDS, RO_LEADERS, RO_NAMES, RO_NAMES_SIZE, RO_SEED_LAST, RO_BOX_DESCRIPTOR, RO_BOX_LEGEND };
#define RO_FIELD(k) RO_U32(4 * (k))

static u32 ro_ok(void) {
    return RO_FIELD(RO_MAGIC) == 0x31525348u && RO_FIELD(RO_SIZE) >= 64 && RO_FIELD(RO_SIZE) < 0x40000;
}

/* an ASCII name of the pool ("T. BRADY"), or 0 when the offset is out of range */
static u16 *put_seed_name(u16 *out, u32 offset) {
    u32 pool = RO_FIELD(RO_NAMES), size = RO_FIELD(RO_NAMES_SIZE);
    if (offset >= size || offset == 0xFFFF)
        return out;
    for (u32 i = 0; offset + i < size && hist_ro[pool + offset + i] && i < 24; i++)
        *out++ = (u16)hist_ro[pool + offset + i];
    *out = 0;
    return out;
}

/* Seed club k (0..31): three aliases of 4 bytes, then first season line and count. The game's club is matched by its
   abbreviation, so the game's club order and relocations (STL, SD, OAK) do not matter. */
#define SEED_CLUB(k) (RO_FIELD(RO_CLUBS) + 16u * (k))

static u32 abbr_match(u32 team, u32 seed) {
    const u16 *abbr = (const u16 *)G(team + 0x108);
    if (!abbr)
        return 0;
    for (u32 a = 0; a < 3; a++) {
        u32 at = SEED_CLUB(seed) + 4 * a, i = 0;
        if (!RO_U8(at))
            continue;
        while (i < 4 && RO_U8(at + i) && abbr[i] == RO_U8(at + i))
            i++;
        if (i < 4 && !RO_U8(at + i) && !abbr[i])
            return 1;
    }
    return 0;
}

/* the seed club of a game club index, or 0xFF */
static u32 seed_of(u32 index) {
    u32 team = club(index);
    if (!team || !ro_ok())
        return 0xFF;
    for (u32 k = 0; k < 32; k++)
        if (abbr_match(team, k))
            return k;
    return 0xFF;
}

/* the game club index of a seed club, or 0xFF */
static u32 game_club_of_seed(u32 seed) {
    u32 n = team_count();
    for (u32 i = 0; seed < 32 && i < n; i++)
        if (abbr_match(club(i), seed))
            return i;
    return 0xFF;
}


/* ---- the franchise extension footer (2K5XTND1 envelope 1, nfl2k5_franchise_extension, job j23-footer) -------------- */
/* Body: +0 magic, +8 u16 envelope 1, +0xA u16 header size 64, +0xC u32 body size, +0x10 u16 directory offset 0x40,
   +0x12 u16 slots 16, +0x14 u16 slot size 16; slot n (id n + 1): u16 id, u8 version, u8 flags (bit 0 present),
   u32 offset, u32 size, u32 Adler-32. Blocks (version 1): 1 seasons, 2 totals, 3 records, 4 leaders, 5 hall,
   6 box scores. A block whose entry fails any check reads as absent. */
#define X_SEASONS 1
#define X_TOTALS 2
#define X_RECORDS 3
#define X_LEADERS 4
#define X_HALL 5
#define X_BOX 6

static const u8 *x_body(void) {
    u32 body = hist_xtnd_ptr ? hist_xtnd_ptr[0] : 0;
    return body >= 0x10000 && body < 0x08000000 && !(body & 3) ? (const u8 *)body : 0;
}

static u32 x_size(const u8 *f) {
    static const u8 magic[8] = {'2', 'K', '5', 'X', 'T', 'N', 'D', '1'};
    for (u32 i = 0; i < 8; i++)
        if (f[i] != magic[i])
            return 0;
    u32 size = *(const u32 *)(f + 12);
    return *(const u16 *)(f + 8) == 1 && *(const u16 *)(f + 10) == 64 && *(const u16 *)(f + 16) == 0x40 &&
           *(const u16 *)(f + 18) == 16 && *(const u16 *)(f + 20) == 16 && size >= 0x200 && size <= 0x20000 ? size : 0;
}

/* The block with this id, version 1 and at least `need` bytes, or 0. */
static const u8 *x_block(u32 id, u32 need) {
    const u8 *f = x_body();
    u32 size = f ? x_size(f) : 0;
    if (!size || id < 1 || id > 16)
        return 0;
    const u8 *e = f + 0x40 + 16 * (id - 1);
    u32 off = *(const u32 *)(e + 4), length = *(const u32 *)(e + 8);
    if (*(const u16 *)e != id || e[2] != 1 || !(e[3] & 1) || off < 0x200 || off > size || length > size - off ||
        length < need)
        return 0;
    return f + off;
}

static u32 sym_char(u32 s) {
    if (s >= 1 && s <= 26)
        return 'A' + s - 1;
    return s == 27 ? '-' : s == 28 ? '.' : s == 29 ? '\'' : s == 30 ? ' ' : 0;
}

static u32 bits(const u8 *in, u32 at, u32 count) {
    u32 value = 0;
    for (u32 b = 0; b < count; b++)
        if (in[(at + b) >> 3] >> ((at + b) & 7) & 1)
            value |= 1u << b;
    return value;
}

/* The 7-byte person (champions packing: initial, nine letters, position; 31 = coach / none): "T. BRADY". */
static u32 person_empty(const u8 *p) {
    return !bits(p, 5, 5);
}

static u16 *put_person(u16 *out, const u8 *p) {
    u32 first = bits(p, 0, 5);
    if (first && sym_char(first)) {
        *out++ = (u16)sym_char(first);
        *out++ = '.';
        *out++ = ' ';
    }
    for (u32 i = 0; i < 9; i++) {
        u32 c = sym_char(bits(p, 5 + 5 * i, 5));
        if (!c)
            break;
        *out++ = (u16)c;
    }
    *out = 0;
    return out;
}

static u32 person_pos(const u8 *p) {
    return bits(p, 50, 5);
}

/* ---- season year and the user's club ---------------------------------------------------------------------- */
static u32 base_year(void) {
    return (u32)((i32)G(CARD_YEAR_IMM) - 11);
}

static u32 season_year(void) {
    return base_year() + G(SEASONS);
}

/* The real history shown is the history before this franchise began. A build whose franchise starts before the seed
   ends (the retail 2004 calendar against a seed through 2025) shows only the seed's seasons, awards and Hall of Fame
   classes and its dated records from before that year, and none of its undated career totals. */
static u32 seed_whole(void) {
    return RO_FIELD(RO_SEED_LAST) < base_year();
}

static u32 user_club(void) {
    u32 focus = G(FOCUS_TEAM), n = team_count();
    if (focus) {
        u32 index = TEAM_INDEX(focus);
        if (index < n)
            return index;
    }
    for (u32 i = 0; i < n && i < 32; i++)
        if (G(HUMAN + 4 * i))
            return i;
    return 0;
}

/* ---- pages ---------------------------------------------------------------------------------------------------- */
enum { P_SEASONS, P_RECORDS, P_LEADERS, P_BOOK, P_AWARDS, P_HOF, PAGES };
static const char *const page_name[PAGES] = {"SEASONS", "RECORDS", "LEADERS", "RECORD BOOK", "AWARDS", "HALL OF FAME"};
#define AWARDS_N 8
static const char *const award_name[AWARDS_N] = {"MOST VALUABLE PLAYER", "OFFENSIVE PLAYER OF THE YEAR",
                                                 "DEFENSIVE PLAYER OF THE YEAR", "OFFENSIVE ROOKIE OF THE YEAR",
                                                 "DEFENSIVE ROOKIE OF THE YEAR", "COMEBACK PLAYER OF THE YEAR",
                                                 "COACH OF THE YEAR", "SUPER BOWL MVP"};
/* the footer's record categories (j23 RECORD_CATEGORIES); the leaders use the first ten without completions and
   forced fumbles (LEADER_CAT below maps them) */
#define CATS 12
static const char *const category_name[CATS] = {"PASS YARDS", "PASS TD", "COMPLETIONS", "RUSH YARDS", "RUSH TD",
                                                "RECEPTIONS", "REC. YARDS", "REC. TD", "SACKS", "INTERCEPTIONS",
                                                "TACKLES", "FORCED FUMBLES"};
#define C_SACKS 8
#define LEADER_CATS 10
static const u8 leader_category[LEADER_CATS] = {0, 1, 3, 4, 5, 6, 7, 8, 9, 10};
static const char *const playoff_text[8] = {"", "LOST WILD CARD", "LOST DIVISIONAL", "LOST CONFERENCE",
                                            "LOST SUPER BOWL", "WON SUPER BOWL", "", ""};

static u16 *put_value(u16 *out, u32 category, u32 value) {
    return category == C_SACKS ? put_halves(out, value) : put_thousands(out, value);
}

/* A list of lines, newest or best first: a page fills rows from it after the scroll. */
typedef struct {
    u32 count;          /* lines available */
    u32 first;          /* first line drawn (the scroll, clamped) */
    u32 rows;           /* rows the list may use */
    u32 top;            /* first screen row */
} List;

static void list_start(List *l, u32 count, u32 top) {
    l->count = count;
    l->top = top;
    l->rows = ROWS - top;
    u32 first = hist_state[S_SCROLL];
    if (first + l->rows > count)
        first = count > l->rows ? count - l->rows : 0;
    hist_state[S_SCROLL] = first;
    l->first = first;
}

/* ---- the footer's seasons (block 1): a ring of 32 season records of 592 bytes, newest = slot head - 1 ----------- */
#define SEASON_RECORD 592u
#define SEASON_RING 32u

/* The k-th newest stored season record, or 0. */
static const u8 *x_season(const u8 *b, u32 k) {
    if (!b)
        return 0;
    u32 count = b[0], head = b[1];
    if (count > SEASON_RING || head >= SEASON_RING || k >= count)
        return 0;
    const u8 *r = b + 16 + SEASON_RECORD * ((head + SEASON_RING - 1 - k) % SEASON_RING);
    u32 year = *(const u16 *)r;
    return year >= 1990 && year < 2200 ? r : 0;
}

static u32 x_season_count(const u8 *b) {
    u32 n = 0;
    while (n < SEASON_RING && x_season(b, n))
        n++;
    return n;
}

static void draw_season_line(u32 row, u32 year, u32 w, u32 l, u32 t, u32 place, u32 playoff, const u16 *coach,
                             u32 colour) {
    u16 text[40];
    put_uint(text, year);
    cell(row, 60.0f, 1, text, colour);
    put_record(text, w, l, t);
    cellw(row, 190.0f, 70, 2, text, colour);
    if (place >= 1 && place <= 8) {
        put_ordinal(text, place);
        cellw(row, 210.0f, 50, 1, text, colour);
    }
    cellw_ascii(row, 265.0f, 174, 1, playoff_text[playoff & 7], colour);
    if (coach && coach[0])
        cellw(row, 445.0f, 156, 1, coach, colour);
}

static void page_seasons(u32 index) {
    u16 text[64], *out;
    u32 seed = seed_of(index), seed_first = 0, seed_count = 0;
    if (seed < 32) {
        seed_first = RO_U16(SEED_CLUB(seed) + 12);
        seed_count = RO_U16(SEED_CLUB(seed) + 14);
        if (seed_first + seed_count > RO_FIELD(RO_SEASON_COUNT))
            seed_count = 0;
    }
    while (seed_count && RO_U16(RO_FIELD(RO_SEASONS) + 10 * seed_first) >= base_year()) {   /* newest first */
        seed_first++;
        seed_count--;
    }
    const u8 *ring = x_block(X_SEASONS, 16 + SEASON_RECORD * SEASON_RING);
    u32 franchise = x_season_count(ring);
    /* row 0: the franchise era from the totals block (+0 u16 first year, +16 + club*16 the club's line) */
    const u8 *totals = x_block(X_TOTALS, 16 + 16 * 32);
    u32 first_year = totals && *(const u16 *)totals ? *(const u16 *)totals : base_year();
    out = put_ascii(text, "SINCE ");
    out = put_uint(out, first_year);
    out = put_ascii(out, ": ");
    const u8 *c = totals ? totals + 16 + 16 * index : 0;
    if (c && c[10]) {
        out = put_record(out, *(const u16 *)c, *(const u16 *)(c + 2), *(const u16 *)(c + 4));
        out = put_ascii(out, "   PLAYOFFS ");
        out = put_uint(out, c[6]);
        out = put_ascii(out, "   DIVISION TITLES ");
        out = put_uint(out, c[7]);
        out = put_ascii(out, "   SUPER BOWLS ");
        put_uint(out, c[9]);
    } else {
        put_ascii(out, "NO SEASONS PLAYED YET");
    }
    cellw(0, 60.0f, 540, 1, text, YELLOW);
    cell_ascii(1, 60.0f, 1, "YEAR", GREY);
    cell_ascii(1, 190.0f, 2, "W-L-T", GREY);
    cell_ascii(1, 210.0f, 1, "DIV", GREY);
    cell_ascii(1, 265.0f, 1, "PLAYOFFS", GREY);
    cell_ascii(1, 445.0f, 1, "HEAD COACH", GREY);
    List l;
    list_start(&l, franchise + seed_count, 2);
    if (!l.count) {
        cell_ascii(2, 60.0f, 1, "NO SEASONS TO SHOW", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < l.count; r++) {
        u32 k = l.first + r;
        u16 coach[28];
        coach[0] = 0;
        if (k < franchise) {
            const u8 *s = x_season(ring, k), *line = s + 80 + 16 * index;
            u32 outcome = line[3];
            if (!(outcome & 0x80)) {                      /* no line for this club that season */
                put_uint(text, *(const u16 *)s);
                cell(l.top + r, 60.0f, 1, text, YELLOW);
                continue;
            }
            if (!person_empty(line + 8))
                put_person(coach, line + 8);
            draw_season_line(l.top + r, *(const u16 *)s, line[0], line[1], line[2], ((outcome >> 5) & 3) + 1,
                             outcome & 7, coach, YELLOW);
        } else {
            u32 at = RO_FIELD(RO_SEASONS) + 10 * (seed_first + k - franchise);
            put_seed_name(coach, RO_U16(at + 6));
            draw_season_line(l.top + r, RO_U16(at), RO_U8(at + 2), RO_U8(at + 3), RO_U8(at + 4), RO_U8(at + 5) & 15,
                             RO_U8(at + 5) >> 4, coach, GREY);
        }
    }
}

/* ---- RECORDS and RECORD BOOK -------------------------------------------------------------------------------- */
/* Book entry (RO): {u8 category, u8 kind (0 game, 1 season, 2 career), u16 name, u32 value, u16 year, u8 club, u8 pos};
   club record entry (RO, per club {u16 first, u16 count} x 32, then): {u8 category << 1 | kind, u8 pos, u16 name,
   u16 value, u16 year}.
   Footer records (block 3): club entry ((club*12 + category)*2 + kind) at +16 and league entry (category*2 + kind) at
   +9232, 12 B each: person (7), u8 club+1, u16 value, u8 year - 1900 (0 = empty), u8 week row + 1. */
static const char *const kind_name[3] = {"GAME", "SEASON", "CAREER"};
#define RECORDS_SIZE 9520u
#define LEAGUE_RECORDS_AT 9232u

typedef struct {
    u32 value, year, club, pos, fresh;   /* fresh: made in this franchise (NEW) */
    u16 name[28];
} Mark;

static u32 seed_club_record(u32 seed, u32 category, u32 kind, Mark *m) {
    u32 base = RO_FIELD(RO_CLUB_RECORDS);
    if (!base || seed >= 32)
        return 0;
    u32 first = RO_U16(base + 4 * seed), count = RO_U16(base + 4 * seed + 2), entries = base + 128;
    for (u32 i = 0; i < count && i < 64; i++) {
        u32 at = entries + 8 * (first + i);
        if (at + 8 > RO_FIELD(RO_SIZE))
            return 0;
        if (RO_U8(at) == (category << 1 | kind) && RO_U16(at + 6) < base_year()) {
            m->value = RO_U16(at + 4);
            m->year = RO_U16(at + 6);
            m->club = game_club_of_seed(seed);
            m->pos = RO_U8(at + 1);
            m->fresh = 0;
            m->name[0] = 0;
            put_seed_name(m->name, RO_U16(at + 2));
            return 1;
        }
    }
    return 0;
}

/* a footer record entry; entries dated before the franchise began are seeded real ones (not NEW) */
static u32 x_mark(const u8 *e, Mark *m) {
    if (person_empty(e) || !e[10])
        return 0;
    m->value = *(const u16 *)(e + 8);
    m->year = 1900u + e[10];
    m->club = e[7] && e[7] <= 32 ? e[7] - 1u : 0xFF;
    m->pos = person_pos(e);
    m->fresh = m->year >= base_year();
    put_person(m->name, e);
    return 1;
}

static u32 x_club_record(u32 index, u32 category, u32 kind, Mark *m) {
    const u8 *b = x_block(X_RECORDS, RECORDS_SIZE);
    if (!b || index >= 32 || kind > 1 || category >= CATS)
        return 0;
    return x_mark(b + 16 + 12 * ((index * CATS + category) * 2 + kind), m);
}

/* the better of the seeded club record and the footer's */
static u32 club_record(u32 index, u32 category, u32 kind, Mark *m) {
    Mark x;
    u32 have = seed_club_record(seed_of(index), category, kind, m);
    if (x_club_record(index, category, kind, &x) && (!have || x.value > m->value || (x.value == m->value && !x.fresh))) {
        *m = x;
        have = 1;
    }
    return have;
}

/* record row: CATEGORY (60) KIND (225) VALUE (right at 370) HOLDER (380) YEAR or "NEW 2028" (right at 600) */
static void draw_mark(u32 row, u32 category, u32 kind, const Mark *m, u32 with_club) {
    u16 text[40], *out;
    u32 colour = m->fresh ? YELLOW : GREY;
    cellw_ascii(row, 60.0f, 160, 1, category_name[category], GREY);
    cellw_ascii(row, 225.0f, 70, 1, kind_name[kind], DIM);
    put_value(text, category, m->value);
    cellw(row, 370.0f, 70, 2, text, colour);
    out = put_text(text, m->name, 20);
    if (with_club && m->club < 32) {
        out = put_ascii(out, " (");
        out = put_club_abbr(out, m->club);
        put_ascii(out, ")");
    }
    cellw(row, 380.0f, 146, 1, text, colour);
    out = text;
    if (m->fresh)
        out = put_ascii(out, m->year ? "NEW " : "NEW");
    if (m->year)
        put_uint(out, m->year);
    cellw(row, 600.0f, 70, 2, text, colour);
}

static void page_records(u32 index) {
    cell_ascii(0, 60.0f, 1, "CLUB RECORDS", GREY);
    cell_ascii(0, 370.0f, 2, "VALUE", GREY);
    cell_ascii(0, 380.0f, 1, "HOLDER", GREY);
    cell_ascii(0, 600.0f, 2, "YEAR", GREY);
    u32 have[CATS * 2], count = 0;
    Mark m;
    for (u32 k = 0; k < CATS * 2; k++)
        if (club_record(index, k / 2, 1 - k % 2, &m))
            have[count++] = k;
    List l;
    list_start(&l, count, 1);
    if (!count) {
        cell_ascii(1, 60.0f, 1, "NO CLUB RECORDS YET", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < count; r++) {
        u32 k = have[l.first + r];
        club_record(index, k / 2, 1 - k % 2, &m);
        draw_mark(l.top + r, k / 2, 1 - k % 2, &m, 0);
    }
}

/* NFL record book: the seeded record; a league record kept by the footer replaces it when it is better (career records:
   the league career leader of the leaders block) */
#define LEADERS_SIZE 16176u
#define LEAGUE_LEADERS_AT 15376u

static u32 x_career_leader(u32 category, Mark *m) {
    const u8 *b = x_block(X_LEADERS, LEADERS_SIZE);
    for (u32 c = 0; b && c < LEADER_CATS; c++)
        if (leader_category[c] == category) {
            const u8 *e = b + LEAGUE_LEADERS_AT + 16 * (c * 5);
            if (!(e[7] & 1) || person_empty(e))
                return 0;
            m->value = *(const u32 *)(e + 8);
            m->year = 0;
            m->club = 0xFF;
            m->pos = person_pos(e);
            m->fresh = (e[7] & 8) != 0;
            put_person(m->name, e);
            return 1;
        }
    return 0;
}

static u32 book_entry(u32 k, u32 *category, u32 *kind, Mark *m) {
    u32 base = RO_FIELD(RO_BOOK), count = RO_FIELD(RO_BOOK_COUNT);
    if (!base || k >= count || base + 12 * (k + 1) > RO_FIELD(RO_SIZE))
        return 0;
    u32 at = base + 12 * k;
    *category = RO_U8(at) < CATS ? RO_U8(at) : 0;
    *kind = RO_U8(at + 1) < 3 ? RO_U8(at + 1) : 0;
    m->value = RO_U32(at + 4);
    m->year = RO_U16(at + 8);
    m->club = RO_U8(at + 10) < 32 ? game_club_of_seed(RO_U8(at + 10)) : 0xFF;
    m->pos = RO_U8(at + 11);
    m->fresh = 0;
    m->name[0] = 0;
    put_seed_name(m->name, RO_U16(at + 2));
    if (*kind == 2 ? !seed_whole() : m->year >= base_year())
        m->value = 0;                                   /* set after this franchise began: not this franchise's past */
    Mark x;
    const u8 *b = x_block(X_RECORDS, RECORDS_SIZE);
    if (*kind < 2 && b && x_mark(b + LEAGUE_RECORDS_AT + 12 * (*category * 2 + *kind), &x) && x.value > m->value)
        *m = x;
    if (*kind == 2 && x_career_leader(*category, &x) && x.value > m->value)
        *m = x;
    return m->value != 0;
}

static void page_book(void) {
    cell_ascii(0, 60.0f, 1, "NFL RECORDS", GREY);
    cell_ascii(0, 370.0f, 2, "VALUE", GREY);
    cell_ascii(0, 380.0f, 1, "HOLDER", GREY);
    cell_ascii(0, 600.0f, 2, "YEAR", GREY);
    u8 have[64];
    u32 count = 0, category, kind;
    Mark m;
    for (u32 k = 0; ro_ok() && k < RO_FIELD(RO_BOOK_COUNT) && count < 64; k++)
        if (book_entry(k, &category, &kind, &m))
            have[count++] = (u8)k;
    List l;
    list_start(&l, count, 1);
    if (!count) {
        cell_ascii(1, 60.0f, 1, "NO RECORDS IN THIS BUILD", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < count; r++)
        if (book_entry(have[l.first + r], &category, &kind, &m))
            draw_mark(l.top + r, category, kind, &m, 1);
}

/* ---- LEADERS: the club's all-time top three per category --------------------------------------------------- */
/* Footer (block 4): club entry ((club*10 + category)*3 + rank) at +16, 16 B: person (7), u8 flags (1 valid, 2 real,
   4 linked, 8 franchise era), u32 value, u16 player, u16 check. Seed (RO): per club {u16 first, u16 count} x 32, then
   8-byte entries {u8 category (0..9) << 2 | rank, u8 pos, u16 name, u32 value}.
   A category whose footer table carries real (seeded) entries is the live one as it stands. Without them (a footer
   that was never seeded keeps franchise-era entries only) the footer's and the seed's lines are merged by value, a
   player in both counted once with his larger total, so the real all-time leaders stay on the page. */
static const u8 *x_leader(const u8 *b, u32 index, u32 category, u32 rank) {
    if (!b || index >= 32)
        return 0;
    const u8 *e = b + 16 + 16 * (3 * (LEADER_CATS * index + category) + rank);
    return (e[7] & 1) && !person_empty(e) ? e : 0;
}

/* candidate s of a category: 0..2 the footer's ranks, 3..5 the seed's (seed = the club's seed index, seed_of) */
static u32 leader_line(const u8 *b, u32 index, u32 seed, u32 category, u32 s, Mark *m) {
    m->year = 0;
    m->club = index;
    m->name[0] = 0;
    if (s < 3) {
        const u8 *e = x_leader(b, index, category, s);
        if (!e)
            return 0;
        m->value = *(const u32 *)(e + 8);
        m->fresh = (e[7] & 8) != 0;
        m->pos = person_pos(e);
        put_person(m->name, e);
        return 1;
    }
    u32 base = ro_ok() && seed_whole() ? RO_FIELD(RO_LEADERS) : 0;
    if (!base || seed >= 32)
        return 0;
    u32 first = RO_U16(base + 4 * seed), count = RO_U16(base + 4 * seed + 2);
    for (u32 i = 0; i < count && i < LEADER_CATS * 3; i++) {
        u32 at = base + 128 + 8 * (first + i);
        if (at + 8 > RO_FIELD(RO_SIZE))
            return 0;
        if (RO_U8(at) == (category << 2 | (s - 3))) {
            m->value = RO_U32(at + 4);
            m->fresh = 0;
            m->pos = RO_U8(at + 1);
            put_seed_name(m->name, RO_U16(at + 2));
            return 1;
        }
    }
    return 0;
}

/* a footer name ("R. GRONKOWSK", nine letters at most) against a seed name ("R. GRONKOWSKI", "O. BECKHAM JR.") */
static u32 same_name(const u16 *f, const u16 *s) {
    u32 i = 0;
    while (f[i] && f[i] == s[i])
        i++;
    return i && !f[i] && (!s[i] || s[i] == ' ' || i >= 12);
}

/* the category's top three as candidate numbers (see leader_line); returns how many */
static u32 leaders_of(const u8 *b, u32 index, u32 seed, u32 category, u8 *pick) {
    Mark a, c;
    u32 n = 0, real = 0, value[6];
    u8 cand[6];
    for (u32 r = 0; r < 3; r++) {
        const u8 *e = x_leader(b, index, category, r);
        if (e && (e[7] & 2))
            real = 1;
    }
    for (u32 s = 0; s < (real ? 3u : 6u); s++) {
        if (!leader_line(b, index, seed, category, s, &a))
            continue;
        u32 dup = 0;
        for (u32 i = 0; i < n && s >= 3 && !dup; i++)
            if (cand[i] < 3 && leader_line(b, index, seed, category, cand[i], &c) && same_name(c.name, a.name)) {
                dup = 1;
                if (a.value >= value[i]) {
                    cand[i] = (u8)s;
                    value[i] = a.value;
                }
            }
        if (!dup) {
            cand[n] = (u8)s;
            value[n++] = a.value;
        }
    }
    for (u32 i = 1; i < n; i++)                         /* larger first; equal values keep the seed's line first */
        for (u32 j = i; j > 0 && (value[j] > value[j - 1] || (value[j] == value[j - 1] && cand[j] >= 3 &&
                                                               cand[j - 1] < 3)); j--) {
            u32 v = value[j];
            u8 k = cand[j];
            value[j] = value[j - 1];
            cand[j] = cand[j - 1];
            value[j - 1] = v;
            cand[j - 1] = k;
        }
    if (n > 3)
        n = 3;
    for (u32 i = 0; i < n; i++)
        pick[i] = cand[i];
    return n;
}

static void page_leaders(u32 index) {
    cell_ascii(0, 60.0f, 1, "ALL-TIME LEADERS", GREY);
    cell_ascii(0, 370.0f, 2, "TOTAL", GREY);
    cell_ascii(0, 380.0f, 1, "PLAYER", GREY);
    const u8 *b = x_block(X_LEADERS, LEADERS_SIZE);
    u8 pick[LEADER_CATS * 3], line[LEADER_CATS * 3];
    u32 count = 0, seed = seed_of(index);
    for (u32 c = 0; c < LEADER_CATS; c++) {
        u32 n = leaders_of(b, index, seed, c, pick + count);
        for (u32 r = 0; r < n; r++)
            line[count + r] = (u8)(c << 2 | r);
        count += n;
    }
    List l;
    list_start(&l, count, 1);
    if (!count) {
        cell_ascii(1, 60.0f, 1, "NO ALL-TIME LEADERS IN THIS BUILD YET", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < count; r++) {
        u16 text[40], *out;
        Mark m;
        u32 k = l.first + r, category = line[k] >> 2, rank = line[k] & 3, row = l.top + r;
        if (!leader_line(b, index, seed, category, pick[k], &m))
            continue;
        u32 colour = m.fresh ? YELLOW : GREY;
        if (!rank || !r)
            cellw_ascii(row, 60.0f, 160, 1, category_name[leader_category[category]], GREY);
        out = put_uint(text, rank + 1);
        put_ascii(out, ".");
        cell(row, 245.0f, 2, text, DIM);
        put_value(text, leader_category[category], m.value);
        cellw(row, 370.0f, 100, 2, text, colour);
        cellw(row, 380.0f, 170, 1, m.name, colour);
        if (m.fresh)
            cell_ascii(row, 600.0f, 2, "NEW", YELLOW);
    }
}

/* ---- AWARDS: one award (L/R), one line per season newest first: the footer's seasons, then the seeded ones -------- */
static void page_awards(u32 award) {
    const u8 *ring = x_block(X_SEASONS, 16 + SEASON_RECORD * SEASON_RING);
    u32 franchise = x_season_count(ring), seed_first = 0, seed_count = 0;
    if (ro_ok() && RO_FIELD(RO_AWARDS)) {
        seed_first = RO_U16(RO_FIELD(RO_AWARDS) + 4 * award);
        seed_count = RO_U16(RO_FIELD(RO_AWARDS) + 4 * award + 2);
        while (seed_count && RO_U16(RO_FIELD(RO_AWARDS) + 32 + 6 * seed_first) >= base_year()) {
            seed_first++;
            seed_count--;
        }
    }
    cell_ascii(0, 60.0f, 1, "YEAR", GREY);
    cell_ascii(0, 140.0f, 1, award == 6 ? "COACH" : "PLAYER", GREY);
    cell_ascii(0, 420.0f, 1, award == 6 ? "" : "POS", GREY);
    cell_ascii(0, 500.0f, 1, "CLUB", GREY);
    List l;
    list_start(&l, franchise + seed_count, 1);
    if (!l.count) {
        cell_ascii(1, 60.0f, 1, "NO WINNERS YET", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < l.count; r++) {
        u32 k = l.first + r, row = l.top + r, year, pos, team, colour;
        u16 name[28], text[24];
        name[0] = 0;
        if (k < franchise) {
            const u8 *s = x_season(ring, k), *e = s + 16 + 8 * award;
            year = *(const u16 *)s;
            pos = person_empty(e) ? 0xFF : person_pos(e);
            team = e[7] && e[7] <= 32 ? e[7] - 1u : 0xFF;
            colour = YELLOW;
            if (person_empty(e))
                put_ascii(name, "-");
            else
                put_person(name, e);
        } else {
            u32 at = RO_FIELD(RO_AWARDS) + 32 + 6 * (seed_first + k - franchise);
            if (at + 6 > RO_FIELD(RO_SIZE))
                break;
            year = RO_U16(at);
            put_seed_name(name, RO_U16(at + 2));
            pos = RO_U8(at + 4);
            team = RO_U8(at + 5) < 32 ? game_club_of_seed(RO_U8(at + 5)) : 0xFF;
            colour = GREY;
        }
        put_uint(text, year);
        cell(row, 60.0f, 1, text, colour);
        cellw(row, 140.0f, 270, 1, name, colour);
        if (pos < 17 && award != 6) {
            put_position(text, pos);
            cell(row, 420.0f, 1, text, colour);
        }
        if (team < 32) {
            put_club_abbr(text, team);
            cell(row, 500.0f, 1, text, colour);
        }
    }
}

/* ---- HALL OF FAME: classes newest first, franchise inductees then the seeded members; L/R filters by club --------- */
/* Footer (block 5): +0 u8 inductees, +16 192 x 16 B in induction order: person (7), u8 club+1, u16 induction year,
   u16 retirement year, u8 flags (1 valid), u8 seasons, u16 score. A footer inductee of a class the seed already lists
   (induction year up to the seed's newest class) is the seed's own member and is not listed twice. */
#define HALL_SIZE 4624u
#define HALL_SLOTS 192u

static u32 seed_inductees(u32 filter_seed) {
    u32 base = RO_FIELD(RO_HOF), count = RO_FIELD(RO_HOF_COUNT), n = 0;
    for (u32 i = 0; base && i < count && i < 1024 && base + 6 * (i + 1) <= RO_FIELD(RO_SIZE); i++)
        if ((filter_seed == 0xFF || RO_U8(base + 6 * i + 5) == filter_seed) && RO_U16(base + 6 * i) <= base_year())
            n++;
    return n;
}

static u32 seed_inductee(u32 k, u32 filter_seed, u32 *at_out) {
    u32 base = RO_FIELD(RO_HOF), count = RO_FIELD(RO_HOF_COUNT), n = 0;
    if (!base)
        return 0;
    for (u32 i = 0; i < count && i < 1024; i++) {
        u32 at = base + 6 * i;
        if (at + 6 > RO_FIELD(RO_SIZE))
            return 0;
        if ((filter_seed != 0xFF && RO_U8(at + 5) != filter_seed) || RO_U16(at) > base_year())
            continue;
        if (n++ == k) {
            *at_out = at;
            return 1;
        }
    }
    return 0;
}

/* the footer inductees shown (newest first: the induction order reversed), filtered; returns how many */
static u32 hall_order(const u8 *b, u32 filter, u32 newest_seed_class, u8 *order) {
    u32 count = 0, n = b ? b[0] : 0;
    if (n > HALL_SLOTS)
        n = HALL_SLOTS;
    for (u32 i = n; i-- > 0;) {
        const u8 *e = b + 16 + 16 * i;
        u32 year = *(const u16 *)(e + 8);
        if (!(e[12] & 1) || person_empty(e) || year < 1990 || year > 2200 || year <= newest_seed_class ||
            (filter && e[7] != filter))
            continue;
        order[count++] = (u8)i;
    }
    return count;
}

static void page_hof(u32 filter) {
    u32 seed_count = 0, at, filter_seed = 0xFF, newest = 0;
    if (filter) {
        filter_seed = seed_of(filter - 1);
        if (filter_seed == 0xFF)
            filter_seed = 0xFE;                         /* a club without seed shows no seeded members */
    }
    if (ro_ok())
        seed_count = seed_inductees(filter_seed);
    if (ro_ok() && RO_FIELD(RO_HOF) && RO_FIELD(RO_HOF_COUNT))
        newest = RO_U16(RO_FIELD(RO_HOF));               /* the seed lists the newest class first */
    if (newest > base_year())
        newest = base_year();                            /* classes after the franchise began are the franchise's */
    const u8 *b = x_block(X_HALL, HALL_SIZE);
    u8 order[HALL_SLOTS];
    u32 franchise = hall_order(b, filter, newest, order);
    cell_ascii(0, 60.0f, 1, "CLASS", GREY);
    cell_ascii(0, 140.0f, 1, "MEMBER", GREY);
    cell_ascii(0, 420.0f, 1, "POS", GREY);
    cell_ascii(0, 500.0f, 1, "CLUB", GREY);
    List l;
    list_start(&l, franchise + seed_count, 1);
    if (!l.count) {
        cell_ascii(1, 60.0f, 1, "NO MEMBERS TO SHOW", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < l.count; r++) {
        u32 k = l.first + r, row = l.top + r, year, pos, team, colour;
        u16 name[28], text[24];
        name[0] = 0;
        if (k < franchise) {
            const u8 *e = b + 16 + 16 * order[k];
            year = *(const u16 *)(e + 8);
            pos = person_pos(e);
            team = e[7] && e[7] <= 32 ? e[7] - 1u : 0xFF;
            put_person(name, e);
            colour = YELLOW;
        } else {
            if (!seed_inductee(k - franchise, filter_seed, &at))
                break;
            year = RO_U16(at);
            put_seed_name(name, RO_U16(at + 2));
            pos = RO_U8(at + 4);
            team = RO_U8(at + 5) < 32 ? game_club_of_seed(RO_U8(at + 5)) : 0xFF;
            colour = GREY;
        }
        put_uint(text, year);
        cell(row, 60.0f, 1, text, colour);
        cellw(row, 140.0f, 270, 1, name, colour);
        if (pos < 17) {
            put_position(text, pos);
            cell(row, 420.0f, 1, text, colour);
        }
        if (team < 32) {
            put_club_abbr(text, team);
            cell(row, 500.0f, 1, text, colour);
        }
    }
}

/* ---- the History screen: enter, input, draw ----------------------------------------------------------------- */
void FC hist_enter(u32 manager) {
    (void)manager;
    hist_state[S_PAGE] = 0;
    hist_state[S_CLUB] = user_club();
    hist_state[S_SCROLL] = 0;
    hist_state[S_AWARD] = 0;
    hist_state[S_FILTER] = 0;
}

/* Black/White page, L/R club (award, filter), Up/Down scroll; returns nonzero when the cursor sound is due */
static u32 hist_buttons(u32 pressed, u32 repeat) {
    u32 page = hist_state[S_PAGE] % PAGES, teams = team_count(), turned = 0;
    if (pressed & 0x3000) {                            /* Black forward, White back */
        page = pressed & 0x1000 ? (page + 1) % PAGES : (page + PAGES - 1) % PAGES;
        hist_state[S_PAGE] = page;
        hist_state[S_SCROLL] = 0;
        turned = 1;
    }
    if (pressed & 0xC000) {                            /* R forward, L back */
        u32 forward = (pressed & 0x8000) != 0;
        if (page == P_AWARDS) {
            u32 a = hist_state[S_AWARD] % AWARDS_N;
            hist_state[S_AWARD] = forward ? (a + 1) % AWARDS_N : (a + AWARDS_N - 1) % AWARDS_N;
        } else if (page == P_HOF) {
            u32 f = hist_state[S_FILTER] % (teams + 1);
            hist_state[S_FILTER] = forward ? (f + 1) % (teams + 1) : (f + teams) % (teams + 1);
        } else if (page != P_BOOK && teams) {
            u32 c = hist_state[S_CLUB] % teams;
            hist_state[S_CLUB] = forward ? (c + 1) % teams : (c + teams - 1) % teams;
        }
        hist_state[S_SCROLL] = 0;
        turned = 1;
    }
    if (repeat & 0x1000000) {                          /* Up */
        if (hist_state[S_SCROLL])
            hist_state[S_SCROLL]--;
        turned = 1;
    }
    if (repeat & 0x2000000) {                          /* Down (the page clamps it) */
        if (hist_state[S_SCROLL] < 1024)
            hist_state[S_SCROLL]++;
        turned = 1;
    }
    return turned;
}

/* Pads like Team Standings' input (0x3551A0): every port the menu accepts (manager context +0x590). */
static u32 read_pads(u32 manager, u32 (*act)(u32, u32)) {
    u32 ctx = G(manager + 0x10C), sound = 0;
    for (u32 port = 0; port < 8; port++) {
        u32 filter = ctx ? G(ctx + 0x590) : 0;
        if (filter && !((u32 (FC *)(u32, u32, u32))filter)(manager, 0, port))
            continue;
        if (!PAD_ON(port, 0))
            continue;
        sound |= act(PAD_PRESSED(port, 0), PAD_REPEAT(port, 0));
    }
    return sound;
}

void FC hist_input(u32 manager) {
    if (read_pads(manager, hist_buttons))
        CURSOR_SOUND();
}

static void page_strip(void) {
    /* the page names in a row under the table, the current page in yellow */
    static const float x[PAGES] = {78.0f, 168.0f, 252.0f, 352.0f, 448.0f, 540.0f};
    u32 page = hist_state[S_PAGE] % PAGES;
    for (u32 p = 0; p < PAGES; p++) {
        u16 text[16];
        put_ascii(text, page_name[p]);
        text_at(text, x[p], 391.0f, 3, 3, p == page ? YELLOW : DIM);
    }
}

void FC hist_draw(u32 manager) {
    (void)manager;
    u32 page = hist_state[S_PAGE] % PAGES, teams = team_count();
    u16 text[64];
    if (!teams)
        return;
    u32 index = hist_state[S_CLUB] % teams;
    hist_state[S_CLUB] = index;
    bars(page == P_SEASONS ? 2 : 1);
    if (page == P_AWARDS) {
        put_ascii(text, award_name[hist_state[S_AWARD] % AWARDS_N]);
    } else if (page == P_HOF) {
        u32 f = hist_state[S_FILTER] % (teams + 1);
        if (f)
            put_club_name(text, f - 1, 1);
        else
            put_ascii(text, "ALL CLUBS");
    } else if (page == P_BOOK) {
        put_ascii(text, "NATIONAL FOOTBALL LEAGUE");
    } else {
        put_club_name(text, index, 1);
    }
    subtitle(text);
    if (page == P_SEASONS)
        page_seasons(index);
    else if (page == P_RECORDS)
        page_records(index);
    else if (page == P_LEADERS)
        page_leaders(index);
    else if (page == P_BOOK)
        page_book();
    else if (page == P_AWARDS)
        page_awards(hist_state[S_AWARD] % AWARDS_N);
    else
        page_hof(hist_state[S_FILTER] % (teams + 1));
    page_strip();
    legend(page == P_BOOK ? "BLACK/WHITE: PAGE    UP/DOWN: SCROLL    B: BACK"
                          : page == P_AWARDS ? "BLACK/WHITE: PAGE    L/R: AWARD    UP/DOWN: SCROLL    B: BACK"
                          : "BLACK/WHITE: PAGE    L/R: TEAM    UP/DOWN: SCROLL    B: BACK");
}

/* ---- box scores (footer block 6) ------------------------------------------------------------------------------- */
/* +0 u16 year, +2 u8 games, +3 u8 user club+1; game g at +16 + 512g: u8 row, slot, home, away, home points, away
   points, user side (0 home, 1 away), flags (1 valid, 2 played by the user, 4 simulated), user lines; +16 team stats
   home then away, 16 x u16 each; +80 opponent leaders 4 x 16 B {person 7, u8 kind 1..4, 4 x i16}; +144 user lines
   23 x 16 B {u16 player record index, u8 position, u8 kind 1..5, 6 x i16}. */
#define BOX_SIZE 12304u
#define BOX_ENTRY 512u
#define BOX_GAMES 24u
#define BOX_LINES 23u
enum { T_POINTS, T_FIRST, T_TOTAL, T_PASS, T_RUSH, T_PATT, T_COMP, T_RATT, T_TO, T_INT, T_FUM, T_SACKS, T_PEN, T_PENYDS,
       T_3RD, T_3RDATT, TEAM_STATS };
/* the team stat rows: (stat, second stat for a pair or 0xFF, separator) */
static const u8 stat_row[][3] = {{T_FIRST, 0xFF, 0}, {T_TOTAL, 0xFF, 0}, {T_PASS, 0xFF, 0}, {T_RUSH, 0xFF, 0},
                                 {T_COMP, T_PATT, '/'}, {T_RATT, 0xFF, 0}, {T_TO, 0xFF, 0}, {T_SACKS, 0xFF, 0},
                                 {T_PEN, T_PENYDS, '-'}, {T_3RD, T_3RDATT, '/'}};
static const char *const stat_name[] = {"FIRST DOWNS", "TOTAL YARDS", "PASSING YARDS", "RUSHING YARDS", "COMP/ATT",
                                        "RUSHES", "TURNOVERS", "SACKS ALLOWED", "PENALTIES", "THIRD DOWNS"};
#define STAT_ROWS (sizeof stat_row / sizeof stat_row[0])
enum { K_PASS = 1, K_RUSH, K_REC, K_DEF, K_KICK };
static const char *const kind_label[8] = {"", "PASSING", "RUSHING", "RECEIVING", "DEFENSE", "KICKING", "", ""};

static u32 grid_ok(u32 row, u32 slot) {
    return row < 22 && slot < 17;
}

static const u8 *grid_cell(u32 row, u32 slot) {
    return (const u8 *)(GRID + 8 * (17 * row + slot));
}

static const u8 *x_boxes(void) {
    const u8 *b = x_block(X_BOX, BOX_SIZE);
    return b && *(const u16 *)b == season_year() && b[2] <= BOX_GAMES ? b : 0;
}

static const u8 *x_box(u32 row, u32 slot) {
    const u8 *b = x_boxes();
    if (!b || !grid_ok(row, slot))
        return 0;
    const u8 *c = grid_cell(row, slot);
    for (u32 g = 0; g < b[2]; g++) {
        const u8 *e = b + 16 + BOX_ENTRY * g;
        if ((e[7] & 1) && e[0] == row && e[1] == slot && e[2] == c[1] && e[3] == c[2] && e[8] <= BOX_LINES)
            return e;
    }
    return 0;
}

/* one line's numbers as text: "22/31  250 YDS  2 TD  1 INT" (values in LINE_KINDS order) */
static u16 *put_line_stats(u16 *out, u32 kind, const i16 *v, u32 values) {
    switch (kind) {
    case K_PASS:
        out = put_int(out, v[0]);
        *out++ = '/';
        out = put_int(out, v[1]);
        out = put_ascii(out, "  ");
        out = put_int(out, v[2]);
        out = put_ascii(out, " YDS  ");
        out = put_int(out, v[3]);
        out = put_ascii(out, " TD");
        if (values > 4) {
            out = put_ascii(out, "  ");
            out = put_int(out, v[4]);
            out = put_ascii(out, " INT");
        }
        return out;
    case K_RUSH:
        out = put_int(out, v[0]);
        out = put_ascii(out, " CAR  ");
        out = put_int(out, v[1]);
        out = put_ascii(out, " YDS  ");
        out = put_int(out, v[2]);
        out = put_ascii(out, " TD");
        if (values > 4 && v[3] > 0) {
            out = put_ascii(out, "  ");
            out = put_int(out, v[3]);
            out = put_ascii(out, " REC ");
            out = put_int(out, v[4]);
            out = put_ascii(out, " YDS");
        }
        return out;
    case K_REC:
        out = put_int(out, v[0]);
        out = put_ascii(out, " REC  ");
        out = put_int(out, v[1]);
        out = put_ascii(out, " YDS  ");
        out = put_int(out, v[2]);
        return put_ascii(out, " TD");
    case K_DEF:
        out = put_int(out, v[0]);
        out = put_ascii(out, " TKL  ");
        out = put_halves(out, v[1] > 0 ? (u32)v[1] : 0);
        out = put_ascii(out, " SACK  ");
        out = put_int(out, v[2]);
        out = put_ascii(out, " INT");
        if (v[3] > 0) {
            out = put_ascii(out, "  ");
            out = put_int(out, v[3]);
            out = put_ascii(out, " FF");
        }
        return out;
    case K_KICK:
        out = put_ascii(out, "FG ");
        out = put_int(out, v[0]);
        *out++ = '/';
        out = put_int(out, v[1]);
        out = put_ascii(out, "  XP ");
        out = put_int(out, v[2]);
        *out++ = '/';
        return put_int(out, v[3]);
    }
    *out = 0;
    return out;
}

/* the player of a user line: "F. LASTNAME" from his roster record (the record index the capture kept) */
#define ROSTER 0x00B72918u

static u32 player_record(u32 link) {
    u32 root = G(ROSTER);
    if (!root || link >= 0xFFFF)
        return 0;
    u32 base = G(root + 4), count = G(root);
    return base && link < count && count < 0x10000 ? base + 0x54 * link : 0;
}

static u16 *put_player(u16 *out, u32 player) {
    const u16 *first = player ? (const u16 *)G(player + 0x10) : 0, *last = player ? (const u16 *)G(player + 0x14) : 0;
    if (first && first[0]) {
        u32 c = first[0];
        *out++ = (u16)(c >= 'a' && c <= 'z' ? c - 32 : c);
        *out++ = '.';
        *out++ = ' ';
    }
    for (u32 i = 0; last && last[i] && i < 16; i++) {
        u32 c = last[i];
        *out++ = (u16)(c >= 'a' && c <= 'z' ? c - 32 : c);
    }
    *out = 0;
    return out;
}

void FC box_enter(u32 manager) {
    (void)manager;
    hist_state[S_BOX_SCROLL] = 0;
}

static u32 box_buttons(u32 pressed, u32 repeat) {
    (void)pressed;
    u32 sound = 0;
    if ((repeat & 0x1000000) && hist_state[S_BOX_SCROLL]) {
        hist_state[S_BOX_SCROLL]--;
        sound = 1;
    }
    if ((repeat & 0x2000000) && hist_state[S_BOX_SCROLL] < 64) {
        hist_state[S_BOX_SCROLL]++;
        sound = 1;
    }
    return sound;
}

void FC box_input(u32 manager) {
    if (read_pads(manager, box_buttons))
        CURSOR_SOUND();
}

static void line_score_row(u32 row, u32 index, const u8 *quarters, u32 total, u32 colour, u32 ot) {
    u16 text[24];
    put_club_abbr(text, index);
    cell(row, 60.0f, 1, text, colour);
    for (u32 q = 0; q < 5; q++) {
        if (q == 4 && !ot)                              /* the OT column when either club scored in overtime */
            continue;
        put_uint(text, quarters[q]);
        cell(row, 260.0f + 50.0f * (float)q, 2, text, colour);
    }
    put_uint(text, total);
    cell(row, 560.0f, 2, text, colour);
}

static u16 *put_week(u16 *out, u32 row) {
    u32 weeks = B(WEEKS_BYTE);
    static const char *const round[4] = {"WILD CARD", "DIVISIONAL", "CONFERENCE", "SUPER BOWL"};
    if (row < weeks)
        return put_uint(put_ascii(out, "WEEK "), row + 1);
    return put_ascii(out, row - weeks < 4 ? round[row - weeks] : "PRO BOWL");
}

void FC box_draw(u32 manager) {
    (void)manager;
    u32 row = hist_state[S_BOX_ROW], slot = hist_state[S_BOX_SLOT];
    u16 text[64], *out;
    if (!grid_ok(row, slot))
        return;
    const u8 *c = grid_cell(row, slot);
    if (c[0] != 3 || !club(c[1]) || !club(c[2]))
        return;
    i32 home = HOME_SCORE(row, slot), away = AWAY_SCORE(row, slot);
    const u8 *q = (const u8 *)(SCORES + 10 * (17 * row + slot));
    bars(1);
    /* sub-bar: "WEEK 3: Eagles 17, Giants 24" (away first, the game's own order) */
    out = put_week(text, row);
    out = put_ascii(out, ": ");
    out = put_club_name(out, c[2], 0);
    *out++ = ' ';
    out = put_int(out, away);
    out = put_ascii(out, ", ");
    out = put_club_name(out, c[1], 0);
    *out++ = ' ';
    put_int(out, home);
    subtitle(text);
    cell_ascii(0, 60.0f, 1, "FINAL", GREY);
    for (u32 k = 0; k < 4; k++) {
        out = put_ascii(text, "Q");
        put_uint(out, k + 1);
        cell(0, 260.0f + 50.0f * (float)k, 2, text, GREY);
    }
    if (q[4] || q[9])
        cell_ascii(0, 460.0f, 2, "OT", GREY);
    cell_ascii(0, 560.0f, 2, "T", GREY);
    line_score_row(1, c[2], q + 5, (u32)away, away > home ? WHITE : GREY, q[4] || q[9]);
    line_score_row(2, c[1], q, (u32)home, home > away ? WHITE : GREY, q[4] || q[9]);
    const u8 *e = x_box(row, slot);
    u32 top = 3, first = hist_state[S_BOX_SCROLL];
    if (!e) {
        cellw_ascii(4, 60.0f, 540, 1, "FULL STATS ARE KEPT FOR YOUR TEAM'S GAMES", GREY);
        cellw_ascii(5, 60.0f, 540, 1, "(GAMES PLAYED WITH THE HISTORY SAVE DATA ON)", DIM);
        legend("B: BACK");
        return;
    }
    /* the list: a header, the team stat rows, the user club's player lines, then the opponent's leaders */
    u32 lines = e[8], leaders = 0, user = e[6] ? c[2] : c[1], them = e[6] ? c[1] : c[2];
    for (u32 k = 0; k < 4; k++)
        if (e[80 + 16 * k + 7] >= 1 && e[80 + 16 * k + 7] <= 4 && !person_empty(e + 80 + 16 * k))
            leaders++;
    u32 count = 1 + STAT_ROWS + lines + leaders, rows = ROWS - top, shown = 0;
    if (first + rows > count)
        first = count > rows ? count - rows : 0;
    hist_state[S_BOX_SCROLL] = first;
    const u16 *home_stats = (const u16 *)(e + 16), *away_stats = home_stats + TEAM_STATS;
    for (u32 r = 0; r < rows && first + r < count; r++, shown++) {
        u32 k = first + r, screen_row = top + r;
        if (k == 0) {                                   /* column heads: the clubs, away then home */
            cell_ascii(screen_row, 60.0f, 1, "TEAM STATS", DIM);
            put_club_abbr(text, c[2]);
            cell(screen_row, 420.0f, 2, text, DIM);
            put_club_abbr(text, c[1]);
            cell(screen_row, 560.0f, 2, text, DIM);
            continue;
        }
        if (k <= STAT_ROWS) {
            const u8 *s = stat_row[k - 1];
            cellw_ascii(screen_row, 60.0f, 300, 1, stat_name[k - 1], GREY);
            for (u32 side = 0; side < 2; side++) {
                const u16 *v = side ? home_stats : away_stats;
                out = put_uint(text, v[s[0]]);
                if (s[1] != 0xFF) {
                    *out++ = s[2];
                    put_uint(out, v[s[1]]);
                }
                cell(screen_row, side ? 560.0f : 420.0f, 2, text, GREY);
            }
            continue;
        }
        k -= 1 + STAT_ROWS;
        if (k < lines) {                                /* the user club's lines */
            const u8 *line = e + 144 + 16 * k;
            u32 kind = line[3] <= K_KICK ? line[3] : 0;
            put_club_abbr(text, user);
            cellw(screen_row, 60.0f, 42, 1, text, DIM);
            cellw_ascii(screen_row, 105.0f, 100, 1, kind_label[kind], DIM);
            put_player(text, player_record(*(const u16 *)line));
            cellw(screen_row, 210.0f, 140, 1, text, WHITE);
            put_line_stats(text, kind, (const i16 *)(line + 4), 6);
            cellw(screen_row, 600.0f, 240, 2, text, WHITE);
            continue;
        }
        k -= lines;
        for (u32 j = 0, seen = 0; j < 4; j++) {         /* the opponent's leaders */
            const u8 *ld = e + 80 + 16 * j;
            if (ld[7] < 1 || ld[7] > 4 || person_empty(ld) || seen++ != k)
                continue;
            put_club_abbr(text, them);
            cellw(screen_row, 60.0f, 42, 1, text, DIM);
            cellw_ascii(screen_row, 105.0f, 100, 1, kind_label[ld[7]], DIM);
            put_person(text, ld);
            cellw(screen_row, 210.0f, 140, 1, text, GREY);
            put_line_stats(text, ld[7], (const i16 *)(ld + 8), 4);
            cellw(screen_row, 600.0f, 240, 2, text, GREY);
            break;
        }
    }
    if (count > rows) {
        out = put_uint(text, first + 1);
        *out++ = '-';
        out = put_uint(out, first + shown);
        out = put_ascii(out, " OF ");
        put_uint(out, count);
        text_at(text, 320.0f, 391.0f, 3, 3, DIM);
    }
    legend("UP/DOWN: SCROLL    B: BACK");
}

/* ---- the Schedule: X on a played game opens its box score ----------------------------------------------------- */
/* The Schedule's own "selected game" accessors (used by its draw for the date line): 0x24B680 = grid row (the week shown
   in the weekly view, the list row in the team view), 0x24B6C0 = cell (the list row in the weekly view, the shown club's
   cell of that row in the team view, 0xFFFF on a bye). */
#define SEL_ROW ((u32 (*)(void))0x0024B680)
#define SEL_SLOT ((u32 (*)(void))0x0024B6C0)
#define LEGEND_SET ((void (FC *)(u32, u32, const u16 *))0x000F35A0)
#define LEGEND_X 1u    /* the menu legend's |M_HELP| slot: the X glyph (|M_SECONDARY| is Y: the desk maps it to 0x800) */

static u32 schedule_game(u32 *row, u32 *slot) {
    u32 r = SEL_ROW(), s = SEL_SLOT();
    if (!grid_ok(r, s))
        return 0;
    *row = r;
    *slot = s;
    return grid_cell(r, s)[0] == 3 && club(grid_cell(r, s)[1]) && club(grid_cell(r, s)[2]);
}

/* From the Schedule input hook (0x24D2E5, once per port that may act this frame): the legend offers the box score while
   a played game is selected, and a fresh X press opens it (and is consumed, so the menu's X help list does not open on
   top). Returns nonzero when the box score screen was pushed. */
u32 FC hist_schedule_x(u32 manager, u32 port) {
    u32 row = 0, slot = 0, played = G(LEAGUE_MODE) == 2 && schedule_game(&row, &slot);
    LEGEND_SET(manager, LEGEND_X, played ? (const u16 *)(hist_ro + RO_FIELD(RO_BOX_LEGEND)) : 0);
    if (!played || port >= 8 || !(PAD_PRESSED(port, 0) & 0x400))
        return 0;
    PAD_CONSUME(port, 0, 0x400);
    LEGEND_SET(manager, LEGEND_X, 0);
    hist_state[S_BOX_ROW] = row;
    hist_state[S_BOX_SLOT] = slot;
    hist_state[S_BOX_SCROLL] = 0;
    SCREEN_PUSH(manager, (u32)(hist_ro + RO_FIELD(RO_BOX_DESCRIPTOR)));
    CURSOR_SOUND();
    return 1;
}

/* ---- Player Card: the game log page ---------------------------------------------------------------------------- */
/* The card's player's lines in this season's stored games, oldest week first (matched by his record index). */
static u32 player_index(u32 player) {
    u32 root = G(ROSTER);
    if (!root || !player)
        return 0xFFFF;
    u32 base = G(root + 4), count = G(root);
    if (!base || player < base || (player - base) % 0x54 || (player - base) / 0x54 >= count)
        return 0xFFFF;
    return (player - base) / 0x54;
}

/* The player's lines in this season's kept games, oldest week first, in one pass: up to `max` (game, line) pairs. */
#define LOG_MAX 32u

static u32 log_lines(u32 player, const u8 **games, const u8 **lines, u32 max) {
    const u8 *b = x_boxes();
    u32 link = player_index(player), n = 0;
    if (!b || link == 0xFFFF)
        return 0;
    u8 order[BOX_GAMES];
    u32 count = 0;
    for (u32 g = 0; g < b[2] && g < BOX_GAMES; g++) {              /* the kept games by week (insertion sort) */
        const u8 *e = b + 16 + BOX_ENTRY * g;
        if (!(e[7] & 1) || e[8] > BOX_LINES)
            continue;
        u32 at = count++;
        while (at && b[16 + BOX_ENTRY * order[at - 1]] > e[0]) {
            order[at] = order[at - 1];
            at--;
        }
        order[at] = (u8)g;
    }
    for (u32 k = 0; k < count && n < max; k++) {
        const u8 *e = b + 16 + BOX_ENTRY * order[k];
        for (u32 i = 0; i < e[8] && n < max; i++) {
            const u8 *l = e + 144 + 16 * i;
            if (*(const u16 *)l == link) {
                games[n] = e;
                lines[n] = l;
                n++;
            }
        }
    }
    return n;
}

#define LOG_ROWS 6u
#define LOG 0x80000000u           /* state[1] of the card (the honors owner's state): the game log view of page 2 */
#define S_CARD_FRAME 8            /* the game log's rows were drawn this frame (its bio entry draws, then clears it) */

/* The card's stats table is the card screen's only element: hidden while a history page shows (the element count at
   context + 0x658 kept in state[3]), restored on every other page; the champions owner's champions_table, verbatim. */
static void card_table(volatile u32 *state, u32 hide) {
    u32 screen = state[2], ctx = screen ? G(screen + 0x10C) : 0;
    if (!ctx)
        return;
    if (hide) {
        if (G(ctx + 0x658)) {
            state[3] = G(ctx + 0x658);
            G(ctx + 0x658) = 0;
        }
    } else if (state[3] && !G(ctx + 0x658)) {
        G(ctx + 0x658) = state[3];
        state[3] = 0;
    }
}

/* The card's page turn while this owner is there (the champions owner calls it): card, honors, champions, game log;
   Black and R forward, White and L back; Up and Down scroll the champions list or the game log. Returns 1 when the
   cursor sound is due. b780 hist1 (Q5): the game log is a page only while there is a franchise footer to read (the
   option Franchise history and records, in a franchise); without one the card keeps its three pages, as it does
   without this owner, instead of a page that can only say NO GAMES KEPT. */
u32 FC hist_card_flip(u32 buttons, volatile u32 *state) {
    u32 page = state[0], log = state[1] & LOG;
    if (buttons & 0x3000000) {
        if (page != 2)
            return 0;
        u32 first = state[1] & ~LOG;
        if (buttons & 0x2000000) {
            if (first < 4096)
                first++;
        } else if (first) {
            first--;
        }
        state[1] = first | log;
        return 1;
    }
    if (!(buttons & 0xF000)) {
        if (buttons & 0x220)
            card_table(state, 0);         /* B or Back: the card closes, its table is whole again */
        return 0;
    }
    u32 pages = x_body() ? 4 : 3;
    u32 at = page >= 3 ? 0 : page == 2 && log ? 3 : page;
    if (at >= pages)
        at = pages - 1;
    at = buttons & 0x6000 ? (at + pages - 1) % pages : (at + 1) % pages;
    state[0] = at == 3 ? 2 : at;
    state[1] = at == 3 ? LOG : 0;
    hist_state[S_CARD_FRAME] = 0;
    if (state[0] != 2)
        card_table(state, 0);
    return 1;
}

/* The game log in the card's table area (state = the honors owner's state, the view's first row in state[1]). */
void FC hist_card_rows(volatile u32 *state) {
    const u8 *games[LOG_MAX], *lines[LOG_MAX];
    u16 text[96], *out;
    card_table(state, 1);
    hist_state[S_CARD_FRAME] = 1;
    u32 count = log_lines(G(CARD_PLAYER), games, lines, LOG_MAX);
    u32 first = state[1] & ~LOG;
    if (first + LOG_ROWS > count)
        first = count > LOG_ROWS ? count - LOG_ROWS : 0;
    state[1] = first | LOG;
    if (!count) {
        put_ascii(text, "NO GAMES KEPT FOR THIS PLAYER THIS SEASON");
        text_at(text, 215.0f, 203.0f, 8, 1, BLACK);
        return;
    }
    for (u32 r = 0; r < LOG_ROWS && first + r < count; r++) {
        const u8 *game = games[first + r], *line = lines[first + r];
        u32 side = game[6] & 1, theirs = side ? game[2] : game[3], weeks = B(WEEKS_BYTE);
        u32 us = side ? game[5] : game[4], them = side ? game[4] : game[5];
        out = put_ascii(text, game[0] < weeks ? "WK " : "PO ");
        out = put_uint(out, game[0] < weeks ? game[0] + 1u : game[0] + 1u - weeks);
        out = put_ascii(out, side ? " @" : " VS ");
        out = put_club_abbr(out, theirs);
        *out++ = ' ';
        out = put_ascii(out, us > them ? "W " : us < them ? "L " : "T ");
        out = put_uint(out, us);
        *out++ = '-';
        out = put_uint(out, them);
        out = put_ascii(out, "  ");
        put_line_stats(out, line[3] <= K_KICK ? line[3] : 0, (const i16 *)(line + 4), 6);
        text_at(text, 215.0f, 203.0f + 17.0f * (float)r, 8, 1, BLACK);
    }
    if (count > LOG_ROWS) {
        out = put_uint(text, first + 1);
        *out++ = '-';
        out = put_uint(out, first + LOG_ROWS < count ? first + LOG_ROWS : count);
        out = put_ascii(out, " OF ");
        out = put_uint(out, count);
        put_ascii(out, "  UP/DOWN");
        text_at(text, 215.0f, 330.0f, 8, 1, BLACK);
    }
}

/* The bio lines of the game log, only in a frame whose rows it drew (the champions page keeps its own). */
u32 hist_card_bio(void) {
    u16 text[48];
    if (!hist_state[S_CARD_FRAME])
        return 0;
    hist_state[S_CARD_FRAME] = 0;
    put_ascii(text, "GAME LOG: THIS SEASON");
    text_at(text, 198.0f, 137.0f, 8, 1, BLACK);
    put_ascii(text, "YOUR TEAM'S GAMES ARE KEPT");
    text_at(text, 198.0f, 154.0f, 8, 1, DIM);
    return 1;
}
