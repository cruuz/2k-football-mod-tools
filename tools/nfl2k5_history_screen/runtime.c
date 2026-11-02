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
   Game log (Player Card page 4, called by the champions owner's page cycle): one line per stored game of the card's
     player this season. */

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
#define S_LOG_SCROLL 8

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

static void cell(u32 row, float x, u32 align, const u16 *text, u32 colour) {
    text_at(text, x, TEXT_Y(row), 4, align, colour);
}

static void cell_ascii(u32 row, float x, u32 align, const char *text, u32 colour) {
    u16 buffer[48];
    put_ascii(buffer, text);
    cell(row, x, align, buffer, colour);
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

/* ---- the franchise extension footer (draft 2K5XTND1, nfl2k5_history_screen.FOOTER_DRAFT) ---------------------------- */
#define X_SEASONS 1
#define X_TOTALS 2
#define X_AWARDS 3
#define X_CLUB_RECORDS 4
#define X_LEADERS 5
#define X_HOF 6
#define X_BOX 7

static const u8 *x_body(void) {
    u32 body = hist_xtnd_ptr ? hist_xtnd_ptr[0] : 0;
    return body >= 0x10000 && body < 0x08000000 && !(body & 3) ? (const u8 *)body : 0;
}

static u32 x_total(void) {
    const u8 *f = x_body();
    if (!f)
        return 0;
    static const u8 magic[8] = {'2', 'K', '5', 'X', 'T', 'N', 'D', '1'};
    for (u32 i = 0; i < 8; i++)
        if (f[i] != magic[i])
            return 0;
    u32 total = *(const u32 *)(f + 12), count = *(const u16 *)(f + 10);
    return *(const u16 *)(f + 8) == 1 && count <= 16 && total >= 16 + 16 * count && total <= 0x20000 ? total : 0;
}

/* The block with this id (and at least this size), or 0. */
static const u8 *x_block(u32 id, u32 need) {
    u32 total = x_total();
    if (!total)
        return 0;
    const u8 *f = x_body();
    u32 count = *(const u16 *)(f + 10);
    for (u32 i = 0; i < count; i++) {
        const u8 *e = f + 16 + 16 * i;
        u32 off = *(const u32 *)(e + 4), size = *(const u32 *)(e + 8);
        if (*(const u16 *)e == id && size >= need && off >= 16 + 16 * count && off <= total && size <= total - off)
            return f + off;
    }
    return 0;
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

/* The champions block's 55-bit person (initial, nine letters, position): "T. BRADY"; 0 letters = empty. */
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
static u32 season_year(void) {
    return (u32)((i32)G(CARD_YEAR_IMM) - 11) + G(SEASONS);
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
#define CATS 12
static const char *const category_name[CATS] = {"PASS YARDS", "PASS TD", "RUSH YARDS", "RUSH TD", "RECEPTIONS",
                                                "REC. YARDS", "REC. TD", "SACKS", "INTERCEPTIONS", "TACKLES",
                                                "FIELD GOALS", "POINTS"};
static const char *const playoff_text[8] = {"", "LOST WILD CARD", "LOST DIVISIONAL", "LOST CONFERENCE",
                                            "LOST SUPER BOWL", "WON SUPER BOWL", "", ""};

static u16 *put_value(u16 *out, u32 category, u32 value) {
    return category == 7 ? put_halves(out, value) : put_thousands(out, value);
}

/* A list of lines, newest or best first: a page fills rows from it after the scroll. Each page computes its lines in a
   stable order with a "line k" function, so scrolling needs no table. */
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

/* ---- SEASONS: franchise seasons from the footer, newest first, then the seeded real seasons ---------------------- */
#define SEASON_SLOT 260u
#define SEASON_SLOTS 32u

/* The slots of a 32-season ring (year u16 at the start of each slot) ordered newest first; returns how many hold a season. */
static u32 ring_order(const u8 *b, u32 slot_size, u8 *order) {
    u32 count = 0;
    if (!b)
        return 0;
    for (u32 s = 0; s < SEASON_SLOTS; s++) {
        u32 year = *(const u16 *)(b + slot_size * s);
        if (year >= 1990 && year < 2200)
            order[count++] = (u8)s;
    }
    for (u32 i = 0; i + 1 < count; i++) {                   /* selection sort, year descending */
        u32 best = i;
        for (u32 j = i + 1; j < count; j++)
            if (*(const u16 *)(b + slot_size * order[j]) > *(const u16 *)(b + slot_size * order[best]))
                best = j;
        u8 t = order[i];
        order[i] = order[best];
        order[best] = t;
    }
    return count;
}

static void draw_season_line(u32 row, u32 year, u32 w, u32 l, u32 t, u32 place, u32 playoff, const u16 *coach,
                             u32 colour) {
    u16 text[40];
    put_uint(text, year);
    cell(row, 60.0f, 1, text, colour);
    put_record(text, w, l, t);
    cell(row, 190.0f, 2, text, colour);
    if (place >= 1 && place <= 8) {
        put_ordinal(text, place);
        cell(row, 210.0f, 1, text, colour);
    }
    cell_ascii(row, 265.0f, 1, playoff_text[playoff & 7], colour);
    if (coach)
        cell(row, 445.0f, 1, coach, colour);
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
    const u8 *ring = x_block(X_SEASONS, SEASON_SLOT * SEASON_SLOTS);
    u8 order[SEASON_SLOTS];
    u32 franchise = ring_order(ring, SEASON_SLOT, order);
    /* row 0: the franchise era record from the totals block */
    const u8 *totals = x_block(X_TOTALS, 384);
    out = put_ascii(text, "SINCE ");
    out = put_uint(out, (u32)((i32)G(CARD_YEAR_IMM) - 11));
    out = put_ascii(out, ": ");
    if (totals && *(const u16 *)(totals + 12 * index + 10)) {
        const u8 *c = totals + 12 * index;
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
    cell(0, 60.0f, 1, text, YELLOW);
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
        if (k < franchise) {
            const u8 *s = ring + SEASON_SLOT * order[k], *c = s + 4 + 8 * index;
            draw_season_line(l.top + r, *(const u16 *)s, c[0], c[1], c[2], c[3] & 15, c[3] >> 4, 0, YELLOW);
        } else {
            u32 at = RO_FIELD(RO_SEASONS) + 10 * (seed_first + k - franchise);
            u16 coach[28];
            coach[0] = 0;
            put_seed_name(coach, RO_U16(at + 6));
            draw_season_line(l.top + r, RO_U16(at), RO_U8(at + 2), RO_U8(at + 3), RO_U8(at + 4), RO_U8(at + 5) & 15,
                             RO_U8(at + 5) >> 4, coach, GREY);
        }
    }
}

/* ---- RECORDS and RECORD BOOK -------------------------------------------------------------------------------- */
/* Record entry, seed: {u8 category, u8 kind (0 game, 1 season, 2 career), u16 name, u32 value, u16 year, u8 club, u8 pos}.
   Footer club records: 12 categories x {game, season} x {person 7, u8 flags, u16 year, u16 value} per club. */
static const char *const kind_name[3] = {"GAME", "SEASON", "CAREER"};

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
        u32 at = entries + 12 * (first + i);
        if (at + 12 > RO_FIELD(RO_SIZE))
            return 0;
        if (RO_U8(at) == category && RO_U8(at + 1) == kind) {
            m->value = RO_U32(at + 4);
            m->year = RO_U16(at + 8);
            m->club = RO_U8(at + 10);
            m->pos = RO_U8(at + 11);
            m->fresh = 0;
            m->name[0] = 0;
            put_seed_name(m->name, RO_U16(at + 2));
            return 1;
        }
    }
    return 0;
}

static u32 x_club_record(u32 index, u32 category, u32 kind, Mark *m) {
    const u8 *b = x_block(X_CLUB_RECORDS, 32 * CATS * 2 * 12);
    if (!b || index >= 32 || kind > 1)
        return 0;
    const u8 *e = b + 12 * (2 * (CATS * index + category) + kind);
    if (person_empty(e) || !*(const u16 *)(e + 10))
        return 0;
    m->value = *(const u16 *)(e + 10);
    m->year = *(const u16 *)(e + 8);
    m->club = index;
    m->pos = person_pos(e);
    m->fresh = 1;
    put_person(m->name, e);
    return 1;
}

/* the better of the seeded club record and the franchise one */
static u32 club_record(u32 index, u32 category, u32 kind, Mark *m) {
    Mark x;
    u32 have = seed_club_record(seed_of(index), category, kind, m);
    if (x_club_record(index, category, kind, &x) && (!have || x.value > m->value)) {
        *m = x;
        have = 1;
    }
    return have;
}

static void draw_mark(u32 row, u32 category, u32 kind, const Mark *m, u32 with_club) {
    u16 text[40], *out;
    u32 colour = m->fresh ? YELLOW : GREY;
    cell_ascii(row, 60.0f, 1, category_name[category], GREY);
    cell_ascii(row, 200.0f, 1, kind_name[kind], DIM);
    put_value(text, category, m->value);
    cell(row, 335.0f, 2, text, colour);
    out = put_text(text, m->name, 20);
    if (with_club && m->club < 32) {
        out = put_ascii(out, " (");
        out = put_club_abbr(out, m->club);
        put_ascii(out, ")");
    }
    cell(row, 350.0f, 1, text, colour);
    if (m->year) {
        put_uint(text, m->year);
        cell(row, 600.0f, 2, text, colour);
    }
    if (m->fresh)
        cell_ascii(row, 545.0f, 2, "NEW", YELLOW);
}

static void page_records(u32 index) {
    cell_ascii(0, 60.0f, 1, "CLUB RECORDS", GREY);
    cell_ascii(0, 335.0f, 2, "VALUE", GREY);
    cell_ascii(0, 350.0f, 1, "HOLDER", GREY);
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

/* NFL record book: the seeded record, unless a club record made in this franchise beats it */
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
    if (*kind < 2) {
        Mark x;
        for (u32 i = 0; i < 32; i++)
            if (x_club_record(i, *category, *kind, &x) && x.value > m->value)
                *m = x;
    }
    return 1;
}

static void page_book(void) {
    cell_ascii(0, 60.0f, 1, "NFL RECORDS", GREY);
    cell_ascii(0, 335.0f, 2, "VALUE", GREY);
    cell_ascii(0, 350.0f, 1, "HOLDER", GREY);
    cell_ascii(0, 600.0f, 2, "YEAR", GREY);
    List l;
    list_start(&l, ro_ok() ? RO_FIELD(RO_BOOK_COUNT) : 0, 1);
    if (!l.count) {
        cell_ascii(1, 60.0f, 1, "NO RECORDS IN THIS BUILD", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < l.count; r++) {
        u32 category, kind;
        Mark m;
        if (book_entry(l.first + r, &category, &kind, &m))
            draw_mark(l.top + r, category, kind, &m, 1);
    }
}

/* ---- LEADERS: the club's all-time top three per category --------------------------------------------------- */
/* seed: per club {u16 first, u16 count} x 32, then entries {u8 category, u8 rank, u16 name, u32 value, u8 pos, u8 flags}
   (10 B); footer: 32 clubs x 10 categories x 3 x {person 7, u8 flags, u32 value}. The footer's entries, when present,
   are the live table (seeded at the franchise start and updated each season); otherwise the seed shows. */
#define LEADER_CATS 10

static u32 leader(u32 index, u32 k, Mark *m, u32 *category, u32 *rank) {
    *category = k / 3;
    *rank = k % 3;
    const u8 *b = x_block(X_LEADERS, 32 * LEADER_CATS * 3 * 12);
    if (b && index < 32) {
        const u8 *e = b + 12 * (3 * (LEADER_CATS * index + *category) + *rank);
        if (!person_empty(e) && *(const u32 *)(e + 8)) {
            m->value = *(const u32 *)(e + 8) & 0xFFFFFF;
            m->fresh = e[7] & 1;
            m->pos = person_pos(e);
            m->year = 0;
            m->club = index;
            put_person(m->name, e);
            return 1;
        }
    }
    u32 base = RO_FIELD(RO_LEADERS), seed = seed_of(index);
    if (!base || seed >= 32)
        return 0;
    u32 first = RO_U16(base + 4 * seed), count = RO_U16(base + 4 * seed + 2);
    for (u32 i = 0; i < count && i < LEADER_CATS * 3; i++) {
        u32 at = base + 128 + 10 * (first + i);
        if (at + 10 > RO_FIELD(RO_SIZE))
            return 0;
        if (RO_U8(at) == *category && RO_U8(at + 1) == *rank) {
            m->value = RO_U32(at + 4);
            m->fresh = 0;
            m->pos = RO_U8(at + 8);
            m->year = 0;
            m->club = index;
            m->name[0] = 0;
            put_seed_name(m->name, RO_U16(at + 2));
            return 1;
        }
    }
    return 0;
}

static void page_leaders(u32 index) {
    cell_ascii(0, 60.0f, 1, "ALL-TIME LEADERS", GREY);
    cell_ascii(0, 335.0f, 2, "TOTAL", GREY);
    cell_ascii(0, 350.0f, 1, "PLAYER", GREY);
    u32 have[LEADER_CATS * 3], count = 0, category, rank;
    Mark m;
    for (u32 k = 0; k < LEADER_CATS * 3; k++)
        if (leader(index, k, &m, &category, &rank))
            have[count++] = k;
    List l;
    list_start(&l, count, 1);
    if (!count) {
        cell_ascii(1, 60.0f, 1, "NO ALL-TIME LEADERS IN THIS BUILD YET", GREY);
        return;
    }
    for (u32 r = 0; r < l.rows && l.first + r < count; r++) {
        u16 text[40], *out;
        leader(index, have[l.first + r], &m, &category, &rank);
        u32 row = l.top + r, colour = m.fresh ? YELLOW : GREY;
        if (!rank || !r)
            cell_ascii(row, 60.0f, 1, category_name[category], GREY);
        out = put_uint(text, rank + 1);
        put_ascii(out, ".");
        cell(row, 215.0f, 2, text, DIM);
        put_value(text, category, m.value);
        cell(row, 335.0f, 2, text, colour);
        cell(row, 350.0f, 1, m.name, colour);
        if (m.fresh)
            cell_ascii(row, 600.0f, 2, "NEW", YELLOW);
    }
}

/* ---- AWARDS: one award (L/R), one line per season newest first: footer seasons, then the seeded ones ----------- */
#define AWARD_SLOT 66u

static void page_awards(u32 award) {
    const u8 *ring = x_block(X_AWARDS, AWARD_SLOT * SEASON_SLOTS);
    u8 order[SEASON_SLOTS];
    u32 franchise = ring_order(ring, AWARD_SLOT, order), seed_first = 0, seed_count = 0;
    if (ro_ok() && RO_FIELD(RO_AWARDS)) {
        seed_first = RO_U16(RO_FIELD(RO_AWARDS) + 4 * award);
        seed_count = RO_U16(RO_FIELD(RO_AWARDS) + 4 * award + 2);
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
            const u8 *s = ring + AWARD_SLOT * order[k], *e = s + 2 + 8 * award;
            year = *(const u16 *)s;
            pos = person_pos(e);
            team = e[7] ? e[7] - 1u : 0xFF;
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
        cell(row, 140.0f, 1, name, colour);
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
#define HOF_SLOTS 192u
#define HOF_ENTRY 12u

/* footer inductees {person 7, u8 club + 1, u16 class year, u16 score} passing the filter, newest class first (then by
   slot); returns how many */
static u32 hof_order(const u8 *b, u32 filter, u8 *order) {
    u32 count = 0;
    if (!b)
        return 0;
    for (u32 s = 0; s < HOF_SLOTS; s++) {
        const u8 *e = b + HOF_ENTRY * s;
        u32 year = *(const u16 *)(e + 8);
        if (year >= 1990 && year <= 2200 && !person_empty(e) && (!filter || e[7] == filter))
            order[count++] = (u8)s;
    }
    for (u32 i = 0; i + 1 < count; i++) {
        u32 best = i;
        for (u32 j = i + 1; j < count; j++)
            if (*(const u16 *)(b + HOF_ENTRY * order[j] + 8) > *(const u16 *)(b + HOF_ENTRY * order[best] + 8))
                best = j;
        u8 t = order[best];
        for (u32 j = best; j > i; j--)                  /* rotate, so equal years keep their slot order */
            order[j] = order[j - 1];
        order[i] = t;
    }
    return count;
}

static u32 seed_inductee(u32 k, u32 filter_seed, u32 *at_out) {
    u32 base = RO_FIELD(RO_HOF), count = RO_FIELD(RO_HOF_COUNT), n = 0;
    if (!base)
        return 0;
    for (u32 i = 0; i < count && i < 1024; i++) {
        u32 at = base + 6 * i;
        if (at + 6 > RO_FIELD(RO_SIZE))
            return 0;
        if (filter_seed != 0xFF && RO_U8(at + 5) != filter_seed)
            continue;
        if (n++ == k) {
            *at_out = at;
            return 1;
        }
    }
    return 0;
}

static void page_hof(u32 filter) {
    u32 franchise = 0, seed_count = 0, at, filter_seed = 0xFF, filter_byte = 0;
    if (filter) {
        filter_byte = filter;                          /* footer: club index + 1 */
        filter_seed = seed_of(filter - 1);
        if (filter_seed == 0xFF)
            filter_seed = 0xFE;                         /* a club without seed shows no seeded members */
    }
    const u8 *b = x_block(X_HOF, HOF_SLOTS * HOF_ENTRY);
    u8 order[HOF_SLOTS];
    franchise = hof_order(b, filter_byte, order);
    while (seed_count < 1024 && ro_ok() && seed_inductee(seed_count, filter_seed, &at))
        seed_count++;
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
            const u8 *e = b + HOF_ENTRY * order[k];
            year = *(const u16 *)(e + 8);
            pos = person_pos(e);
            team = e[7] ? e[7] - 1u : 0xFF;
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
        cell(row, 140.0f, 1, name, colour);
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

/* ---- box scores ------------------------------------------------------------------------------------------------ */
/* Footer box score (480 B): {u8 row, u8 slot, u8 home, u8 away, u8 user sides, u8 lines, u16 year,
   team stats 2 x 14 u16 (home, away), 18 lines x 22 B {person 7, u8 side << 7 | kind, u16 player link, 6 x u16}}. */
#define BOX_SIZE 480u
#define BOX_SLOTS 24u
#define BOX_LINES 18u
#define TEAM_STATS 14u
static const char *const team_stat_name[TEAM_STATS] = {"FIRST DOWNS", "TOTAL YARDS", "PASSING YARDS", "RUSHING YARDS",
                                                       "PASS ATT-COMP", "", "RUSHES", "TURNOVERS", "FUMBLES LOST",
                                                       "INTERCEPTIONS", "PENALTIES", "", "THIRD DOWNS", ""};
enum { K_PASS = 1, K_RUSH, K_REC, K_DEF, K_KICK, K_PUNT };
static const char *const kind_label[8] = {"", "PASSING", "RUSHING", "RECEIVING", "DEFENSE", "KICKING", "PUNTING", ""};

static u32 grid_ok(u32 row, u32 slot) {
    return row < 22 && slot < 17;
}

static const u8 *grid_cell(u32 row, u32 slot) {
    return (const u8 *)(GRID + 8 * (17 * row + slot));
}

static const u8 *x_box(u32 row, u32 slot) {
    const u8 *b = x_block(X_BOX, BOX_SIZE * BOX_SLOTS);
    u32 year = season_year();
    if (!b || !grid_ok(row, slot))
        return 0;
    const u8 *c = grid_cell(row, slot);
    for (u32 s = 0; s < BOX_SLOTS; s++) {
        const u8 *e = b + BOX_SIZE * s;
        if (e[0] == row && e[1] == slot && e[2] == c[1] && e[3] == c[2] && *(const u16 *)(e + 6) == year &&
            e[5] <= BOX_LINES)
            return e;
    }
    return 0;
}

/* one player line of a box score as text: "22/31 250 YDS 2 TD 1 INT" */
static u16 *put_line_stats(u16 *out, u32 kind, const u16 *v) {
    switch (kind) {
    case K_PASS:
        out = put_uint(out, v[0]);
        *out++ = '/';
        out = put_uint(out, v[1]);
        out = put_ascii(out, "  ");
        out = put_int(out, (i16)v[2]);
        out = put_ascii(out, " YDS  ");
        out = put_uint(out, v[3]);
        out = put_ascii(out, " TD  ");
        out = put_uint(out, v[4]);
        return put_ascii(out, " INT");
    case K_RUSH:
        out = put_uint(out, v[0]);
        out = put_ascii(out, " CAR  ");
        out = put_int(out, (i16)v[1]);
        out = put_ascii(out, " YDS  ");
        out = put_uint(out, v[2]);
        return put_ascii(out, " TD");
    case K_REC:
        out = put_uint(out, v[0]);
        out = put_ascii(out, " REC  ");
        out = put_int(out, (i16)v[1]);
        out = put_ascii(out, " YDS  ");
        out = put_uint(out, v[2]);
        return put_ascii(out, " TD");
    case K_DEF:
        out = put_uint(out, v[0]);
        out = put_ascii(out, " TKL  ");
        out = put_halves(out, v[1]);
        out = put_ascii(out, " SACK  ");
        out = put_uint(out, v[2]);
        return put_ascii(out, " INT");
    case K_KICK:
        out = put_ascii(out, "FG ");
        out = put_uint(out, v[0]);
        *out++ = '/';
        out = put_uint(out, v[1]);
        out = put_ascii(out, "  XP ");
        out = put_uint(out, v[2]);
        *out++ = '/';
        return put_uint(out, v[3]);
    case K_PUNT:
        out = put_uint(out, v[0]);
        out = put_ascii(out, " PUNTS  ");
        out = put_uint(out, v[1]);
        return put_ascii(out, " YDS");
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

static void line_score_row(u32 row, u32 index, const u8 *quarters, u32 total, u32 colour) {
    u16 text[24];
    put_club_abbr(text, index);
    cell(row, 60.0f, 1, text, colour);
    for (u32 q = 0; q < 5; q++) {
        if (q == 4 && !quarters[4])
            continue;
        put_uint(text, quarters[q]);
        cell(row, 260.0f + 50.0f * (float)q, 2, text, colour);
    }
    put_uint(text, total);
    cell(row, 560.0f, 2, text, colour);
}

static u32 week_label(u16 *out, u32 row) {
    u32 weeks = B(WEEKS_BYTE);
    static const char *const round[4] = {"WILD CARD", "DIVISIONAL", "CONFERENCE", "SUPER BOWL"};
    if (row < weeks) {
        out = put_ascii(out, "WEEK ");
        put_uint(out, row + 1);
    } else if (row - weeks < 4) {
        put_ascii(out, round[row - weeks]);
    } else {
        put_ascii(out, "PRO BOWL");
    }
    return 1;
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
    bars(2);
    /* sub-bar: "WEEK 3: GIANTS 24, EAGLES 17" */
    week_label(text, row);
    out = text;
    while (*out)
        out++;
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
    line_score_row(1, c[2], q + 5, (u32)away, away > home ? WHITE : GREY);
    /* the home line goes in row 2, the first row of the list below scrolls under it */
    line_score_row(2, c[1], q, (u32)home, home > away ? WHITE : GREY);
    const u8 *e = x_box(row, slot);
    u32 lines = 0, top = 3, first = hist_state[S_BOX_SCROLL];
    if (!e) {
        cell_ascii(4, 60.0f, 1, "FULL STATS ARE KEPT FOR YOUR TEAM'S GAMES", GREY);
        cell_ascii(5, 60.0f, 1, "(FROM THE FIRST GAME PLAYED WITH THIS FEATURE)", DIM);
        legend("B: BACK");
        return;
    }
    /* the list: team stats (one line per stat with a name), then the player lines */
    u32 stat_rows[TEAM_STATS], stats = 0;
    for (u32 s = 0; s < TEAM_STATS; s++)
        if (team_stat_name[s][0])
            stat_rows[stats++] = s;
    u32 count = stats + e[5];
    if (first + (ROWS - top) > count)
        first = count > ROWS - top ? count - (ROWS - top) : 0;
    hist_state[S_BOX_SCROLL] = first;
    const u16 *home_stats = (const u16 *)(e + 8), *away_stats = home_stats + TEAM_STATS;
    for (u32 r = 0; r < ROWS - top && first + r < count; r++, lines++) {
        u32 k = first + r, screen_row = top + r;
        if (k < stats) {
            u32 s = stat_rows[k];
            cell_ascii(screen_row, 60.0f, 1, team_stat_name[s], GREY);
            if (s == 4 || s == 12 || s == 10) {        /* pairs: att-comp, conversions-attempts, penalties-yards */
                put_uint(put_ascii(put_uint(text, away_stats[s]), "-"), away_stats[s + 1]);
                cell(screen_row, 420.0f, 2, text, GREY);
                put_uint(put_ascii(put_uint(text, home_stats[s]), "-"), home_stats[s + 1]);
                cell(screen_row, 560.0f, 2, text, GREY);
            } else {
                put_uint(text, away_stats[s]);
                cell(screen_row, 420.0f, 2, text, GREY);
                put_uint(text, home_stats[s]);
                cell(screen_row, 560.0f, 2, text, GREY);
            }
            continue;
        }
        const u8 *line = e + 64 + 22 * (k - stats);
        u32 kind = line[7] & 7, side = line[7] >> 7, colour = G(HUMAN + 4 * (side ? c[2] : c[1])) ? WHITE : GREY;
        put_club_abbr(text, side ? c[2] : c[1]);
        cell(screen_row, 60.0f, 1, text, DIM);
        cell_ascii(screen_row, 105.0f, 1, kind_label[kind], DIM);
        put_person(text, line);
        cell(screen_row, 230.0f, 1, text, colour);
        put_line_stats(text, kind, (const u16 *)(line + 10));
        cell(screen_row, 600.0f, 2, text, colour);
    }
    if (count > ROWS - top) {
        out = put_uint(text, first + 1);
        *out++ = '-';
        out = put_uint(out, first + lines);
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
#define LEGEND_X 8u                                  /* the |M_SECONDARY| slot of the menu legend */

static u32 schedule_game(u32 *row, u32 *slot) {
    u32 r = SEL_ROW(), s = SEL_SLOT();
    if (!grid_ok(r, s))
        return 0;
    *row = r;
    *slot = s;
    return grid_cell(r, s)[0] == 3 && club(grid_cell(r, s)[1]) && club(grid_cell(r, s)[2]);
}

/* From the Schedule input hook (0x24D2E5, once per port that may act this frame): the legend offers the box score while
   a played game is selected, and a fresh X press opens it. Returns nonzero when the box score screen was pushed. */
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

/* ---- Player Card page 4: the game log ------------------------------------------------------------------------ */
/* Lines of the card's player in this season's stored box scores, oldest first. The player is matched by his record
   (the line's link = his index in the roster's player array) and his packed name. */
#define ROSTER 0x00B72918u

static u32 player_link(u32 player) {
    u32 root = G(ROSTER);
    if (!root || !player)
        return 0xFFFF;
    u32 base = G(root + 4), count = G(root);
    if (player < base || (player - base) % 0x54 || (player - base) / 0x54 >= count)
        return 0xFFFF;
    return (player - base) / 0x54;
}

static u32 same_person(const u8 *p, u32 player) {
    const u16 *last = (const u16 *)G(player + 0x14);
    if (!last)
        return 0;
    for (u32 i = 0; i < 9; i++) {
        u32 c = sym_char(bits(p, 5 + 5 * i, 5)), l = last[i];
        if (l >= 'a' && l <= 'z')
            l -= 32;
        if (!c)
            return 1;
        if (c != l)
            return 0;
    }
    return 1;
}

/* k-th game-log line of the player (oldest week first): sets the box score and line, returns 1 */
static u32 log_line(u32 player, u32 k, const u8 **box, const u8 **line) {
    const u8 *b = x_block(X_BOX, BOX_SIZE * BOX_SLOTS);
    u32 link = player_link(player), year = season_year(), n = 0;
    if (!b || link == 0xFFFF)
        return 0;
    for (u32 row = 0; row < 22; row++)
        for (u32 s = 0; s < BOX_SLOTS; s++) {
            const u8 *e = b + BOX_SIZE * s;
            if (e[0] != row || *(const u16 *)(e + 6) != year || e[5] > BOX_LINES)
                continue;
            for (u32 i = 0; i < e[5]; i++) {
                const u8 *l = e + 64 + 22 * i;
                if (*(const u16 *)(l + 8) == link && same_person(l, player) && n++ == k) {
                    *box = e;
                    *line = l;
                    return 1;
                }
            }
        }
    return 0;
}

#define LOG_ROWS 6u

/* the card's stats table area (the champions page uses the same place; the honors owner hides the table) */
void FC hist_log_ratings(volatile u32 *card_state) {
    u32 player = G(CARD_PLAYER), count = 0, ctx[32];
    const u8 *box, *line;
    u16 text[80], *out;
    (void)ctx;
    while (count < 64 && log_line(player, count, &box, &line))
        count++;
    u32 first = card_state[1];
    if (first + LOG_ROWS > count)
        first = count > LOG_ROWS ? count - LOG_ROWS : 0;
    card_state[1] = first;
    if (!count) {
        put_ascii(text, "NO GAMES KEPT FOR THIS PLAYER THIS SEASON");
        text_at(text, 215.0f, 203.0f, 8, 1, BLACK);
        return;
    }
    for (u32 r = 0; r < LOG_ROWS && first + r < count; r++) {
        log_line(player, first + r, &box, &line);
        u32 side = line[7] >> 7, mine = side ? box[3] : box[2], theirs = side ? box[2] : box[3];
        i32 us = side ? AWAY_SCORE(box[0], box[1]) : HOME_SCORE(box[0], box[1]);
        i32 them = side ? HOME_SCORE(box[0], box[1]) : AWAY_SCORE(box[0], box[1]);
        (void)mine;
        out = put_ascii(text, box[0] < B(WEEKS_BYTE) ? "WK " : "PO ");
        out = put_uint(out, box[0] < B(WEEKS_BYTE) ? box[0] + 1u : box[0] + 1u - B(WEEKS_BYTE));
        *out++ = ' ';
        out = put_ascii(out, side ? "@" : "VS ");
        out = put_club_abbr(out, theirs);
        *out++ = ' ';
        out = put_ascii(out, us > them ? "W " : us < them ? "L " : "T ");
        out = put_int(out, us);
        *out++ = '-';
        out = put_int(out, them);
        out = put_ascii(out, "  ");
        put_line_stats(out, line[7] & 7, (const u16 *)(line + 10));
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

void FC hist_log_bio(void) {
    u16 text[48];
    put_ascii(text, "GAME LOG: THIS SEASON");
    text_at(text, 198.0f, 137.0f, 8, 1, BLACK);
    put_ascii(text, "YOUR TEAM'S GAMES ARE KEPT");
    text_at(text, 198.0f, 154.0f, 8, 1, DIM);
}
