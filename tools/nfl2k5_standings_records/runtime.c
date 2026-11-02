/* Team Standings division / conference records and home / road / streak view (job b780 j1-standings).
   EXPERIMENTAL / UNWITNESSED.

   Freestanding i386 code for the late allocator owner nfl2k5_standings_records. Built by
   tools/nfl2k5_standings_records_build.py into mod_editor/core/nfl2k5_standings_records_code.py; no retail bytes live
   here. Every game routine is called through its fixed retail address (no relocation); the only relocations are this
   blob's own labels and the owner's 16-byte state block.

   ESPN.com > Team Standings is drawn by FUN_003554B0 (cells: three "call 0x4A400" that format the retail W, L and T
   counts into a stack buffer; labels: three "mov edx, imm32" that name the W, L and T header strings; legend: four
   "mov edx, imm32" in FUN_00355CD0) and read by FUN_003551A0. The same code also draws the realignment screen, which
   the stubs in stubs.S leave alone ([0xAE9EE8] is 1 only for the standings). White and Black turn the columns:

       view 0  W  L  T        the retail screen, byte for byte (every stub falls through to the retail routine)
       view 1  DIV  CONF      this season's division and conference records, regular season only
       view 2  HOME ROAD STRK the game's own home and road record strings and its current streak

   DIV and CONF come from the schedule grid the game already keeps for the season (0xE57C40: 22 rows of 17 cells, 8
   bytes each: status 3 = played, home club, away club; quarter scores 0xE587F0: 10 bytes a cell). Only the rows
   before the playoffs count (the byte at 0x5151C4: 17 retail, 18 with the 18-week season), and a division game is
   also a conference game, as in the NFL. Nothing is stored: the numbers are recomputed from the grid every frame. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define G8(a) (*(volatile u8 *)(a))

/* the owner's RW block: [0] = the view (0 retail W L T, 1 DIV CONF, 2 HOME ROAD STRK) */
extern volatile u32 sr_state[4];

/* the game's text context and its retail helpers (the same ones the Player Card pages use) */
#define TEXT_FONT  ((void (FC *)(void *, u32))0x000469B0)
#define TEXT_POS   ((void (FC *)(void *, float, float, float))0x00046A70)
#define TEXT_WIDTH ((i32 (FC *)(void *, const u16 *))0x00046C50)
#define FONT_GET   ((u32 (FC *)(u32))0x000EF850)
#define PLAY_SOUND ((void (FC *)(const u16 *))0x0014D390)
/* league: club record -> league index (0xFFFF when unknown), home / road record text, current streaks */
#define CLUB_INDEX  ((u32 (FC *)(u32))0x000C4CA0)
#define HOME_RECORD ((const u16 *(FC *)(u32))0x000C6B70)
#define ROAD_RECORD ((const u16 *(FC *)(u32))0x000C6C30)
#define WIN_STREAK  ((i32 (FC *)(u32))0x000C78D0)
#define LOSS_STREAK ((i32 (FC *)(u32))0x000C7960)

#define GRID    0x00E57C40u   /* 22 rows x 17 cells x 8 bytes: [0] status (3 = played), [1] home club, [2] away club */
#define SCORES  0x00E587F0u   /* 10 bytes a cell: home quarters 1-4 and overtime, then away */
#define DIVS    0x00E576D4u   /* u32 per league club index: its division */
#define CONFS   0x004F0FE0u   /* u32 per division: its conference */
#define WEEKS   0x005151C4u   /* regular-season rows: 17 retail, 18 with the season-length patch */
#define MENU_MOVE 0x00EB3C54u /* the retail conference switch's cursor sound name */
#define CLUBS 32u
#define DIVISIONS 8u
#define ROWS 22u
#define SLOTS 17u
#define VIEWS 2u

#define BLACK_BUTTON 0x1000u
#define WHITE_BUTTON 0x2000u

typedef struct { u32 w, l, t; } Rec;

/* ---- text ------------------------------------------------------------------------------------------------------ */

/* UTF-16 strings (packed: no padding between them), the legend lines in the retail legend's "x - words" style */
#define TEXT(name, ...) static const u16 name[] __attribute__((aligned(2))) = {__VA_ARGS__}
TEXT(s_blank, ' ', 0);
TEXT(s_div, 'D', 'I', 'V', 0);
TEXT(s_conf, 'C', 'O', 'N', 'F', 0);
TEXT(s_home, 'H', 'O', 'M', 'E', 0);
TEXT(s_road, 'R', 'O', 'A', 'D', 0);
TEXT(s_strk, 'S', 'T', 'R', 'K', 0);
TEXT(l_div, 'D', 'I', 'V', ' ', '-', ' ', 'd', 'i', 'v', 'i', 's', 'i', 'o', 'n', ' ', 'r', 'e', 'c', 'o', 'r', 'd', 0);
TEXT(l_conf, 'C', 'O', 'N', 'F', ' ', '-', ' ', 'c', 'o', 'n', 'f', 'e', 'r', 'e', 'n', 'c', 'e', ' ', 'r', 'e', 'c', 'o', 'r', 'd', 0);
TEXT(l_regular, 'R', 'e', 'g', 'u', 'l', 'a', 'r', ' ', 's', 'e', 'a', 's', 'o', 'n', ' ', 'g', 'a', 'm', 'e', 's', ' ', 'o', 'n', 'l', 'y', 0);
TEXT(l_keys, 'W', 'h', 'i', 't', 'e', '/', 'B', 'l', 'a', 'c', 'k', ' ', '-', ' ', 'c', 'h', 'a', 'n', 'g', 'e', ' ', 'c', 'o', 'l', 'u', 'm', 'n', 's', 0);
TEXT(l_home, 'H', 'O', 'M', 'E', ' ', '-', ' ', 'r', 'e', 'c', 'o', 'r', 'd', ' ', 'a', 't', ' ', 'h', 'o', 'm', 'e', 0);
TEXT(l_road, 'R', 'O', 'A', 'D', ' ', '-', ' ', 'r', 'e', 'c', 'o', 'r', 'd', ' ', 'o', 'n', ' ', 't', 'h', 'e', ' ', 'r', 'o', 'a', 'd', 0);
TEXT(l_strk, 'S', 'T', 'R', 'K', ' ', '-', ' ', 'c', 'u', 'r', 'r', 'e', 'n', 't', ' ', 's', 't', 'r', 'e', 'a', 'k', 0);

/* [view - 1][column]: the header labels (the unused middle column of view 1 holds a blank) */
static const u16 *const header_text[VIEWS][3] = {{s_div, s_blank, s_conf}, {s_home, s_road, s_strk}};
/* [view - 1][legend line]: the retail legend has two lines in each of two columns, drawn in this order */
static const u16 *const legend_text[VIEWS][4] = {{l_div, l_conf, l_regular, l_keys}, {l_home, l_road, l_strk, l_keys}};
/* the retail legend strings (clinch letters), the retail W / L / T header strings, the retail column x positions */
static const u32 retail_legend[4] = {0x00EB3C9Cu, 0x00EB3CD4u, 0x00EB3D0Cu, 0x00EB3D48u};
static const float header_x[3] = {210.0f, 250.0f, 280.0f};     /* the retail header labels (left aligned) */
static const float value_x[3] = {220.0f, 250.0f, 280.0f};      /* the retail number columns (centered) */
/* where each view's column is centered, as a shift from the retail column; DIV and CONF take the outer columns */
static const float shift[VIEWS][3] = {{-5.0f, 0.0f, 5.0f}, {-18.0f, 1.0f, 20.0f}};

/* ---- records ---------------------------------------------------------------------------------------------------- */

static void add(Rec *r, u32 mine, u32 theirs) {
    if (mine > theirs)
        r->w++;
    else if (mine < theirs)
        r->l++;
    else
        r->t++;
}

/* A club's division and conference records over the regular-season rows of this season's grid. */
static void records(u32 team, Rec *div, Rec *conf) {
    div->w = div->l = div->t = conf->w = conf->l = conf->t = 0;
    u32 me = CLUB_INDEX(team);
    if (me >= CLUBS)
        return;
    u32 my_div = G(DIVS + 4 * me);
    if (my_div >= DIVISIONS)
        return;
    u32 my_conf = G(CONFS + 4 * my_div);
    u32 weeks = G8(WEEKS);
    if (weeks > ROWS)
        weeks = ROWS;
    for (u32 row = 0; row < weeks; row++) {
        for (u32 slot = 0; slot < SLOTS; slot++) {
            u32 cell = row * SLOTS + slot;
            u32 g = GRID + 8 * cell;
            if (G8(g) != 3)                                  /* the game's own "played" status */
                continue;
            u32 home = G8(g + 1), away = G8(g + 2);
            if (home != me && away != me)
                continue;
            u32 opponent = home == me ? away : home;
            if (opponent >= CLUBS)
                continue;
            u32 s = SCORES + 10 * cell;
            u32 home_points = G8(s) + G8(s + 1) + G8(s + 2) + G8(s + 3) + G8(s + 4);
            u32 away_points = G8(s + 5) + G8(s + 6) + G8(s + 7) + G8(s + 8) + G8(s + 9);
            u32 mine = home == me ? home_points : away_points;
            u32 theirs = home == me ? away_points : home_points;
            u32 other_div = G(DIVS + 4 * opponent);
            if (other_div == my_div)
                add(div, mine, theirs);
            if (other_div < DIVISIONS && G(CONFS + 4 * other_div) == my_conf)
                add(conf, mine, theirs);
        }
    }
}

static u16 *put_uint(u16 *p, u32 v) {
    u16 digits[10];
    u32 n = 0;
    do {
        digits[n++] = (u16)('0' + v % 10);
        v /= 10;
    } while (v && n < 10);
    while (n)
        *p++ = digits[--n];
    return p;
}

/* "W-L", or "W-L-T" when a game was tied (the game's own home / road record format) */
static void put_record(u16 *p, const Rec *r) {
    p = put_uint(p, r->w);
    *p++ = '-';
    p = put_uint(p, r->l);
    if (r->t) {
        *p++ = '-';
        p = put_uint(p, r->t);
    }
    *p = 0;
}

static void put_text(u16 *p, const u16 *s) {
    for (u32 i = 0; i < 12 && s[i]; i++)
        *p++ = s[i];
    *p = 0;
}

/* "W3" after a win streak, "L2" after a loss streak, "--" like the game's own streak text when there is none */
static void put_streak(u16 *p, u32 team) {
    i32 wins = WIN_STREAK(team), losses = LOSS_STREAK(team);
    if (wins > 0) {
        *p++ = 'W';
        p = put_uint(p, (u32)wins);
    } else if (losses > 0) {
        *p++ = 'L';
        p = put_uint(p, (u32)losses);
    } else {
        *p++ = '-';
        *p++ = '-';
    }
    *p = 0;
}

/* ---- entries (stubs.S calls these; every one answers "retail" when the view is 0 or damaged) ---------------------- */

/* White (Black is the retail pad bit 0x1000) turns the columns back, Black forward; the cursor sound plays. */
void FC sr_buttons(u32 pressed) {
    u32 v = sr_state[0];
    if (v > VIEWS)
        v = 0;
    v = (pressed & BLACK_BUTTON) ? (v + 1) % (VIEWS + 1) : (v + VIEWS) % (VIEWS + 1);
    sr_state[0] = v;
    PLAY_SOUND((const u16 *)MENU_MOVE);
}

/* The header label of column col (the retail "mov edx, W/L/T"): retail pointer in view 0, else the view's label
   re-centered over its column (pos = the caller's x, y, z; ctx = its text context). */
const u16 *FC sr_header(u32 col, float *pos, void *ctx) {
    u32 v = sr_state[0];
    if (v == 0 || v > VIEWS || col > 2)
        return (const u16 *)(0x00EB3C88u + 4 * (col > 2 ? 0 : col));
    const u16 *text = header_text[v - 1][col];
    TEXT_FONT(ctx, FONT_GET(0));
    i32 width = TEXT_WIDTH(ctx, text);
    float block = pos[0] - header_x[col];                   /* 0 for the left division block, 280 for the right one */
    TEXT_POS(ctx, block + value_x[col] + shift[v - 1][col] - (float)(width / 2), pos[1], pos[2]);
    return text;
}

/* The number of column col for the club in edi (the retail "call 0x4A400" that formats one count into buf): 1 when
   handled here (the text is in buf, the caller's x is moved), 0 for the retail routine. */
u32 FC sr_cell_text(u32 col, u16 *buf, float *pos, u32 team) {
    u32 v = sr_state[0];
    if (v == 0 || v > VIEWS || col > 2)
        return 0;
    pos[0] += shift[v - 1][col];
    buf[0] = 0;
    if (v == 1) {
        if (col != 1) {
            Rec div, conf;
            records(team, &div, &conf);
            put_record(buf, col == 0 ? &div : &conf);
        }
    } else if (col == 0) {
        put_text(buf, HOME_RECORD(team));
    } else if (col == 1) {
        put_text(buf, ROAD_RECORD(team));
    } else {
        put_streak(buf, team);
    }
    return 1;
}

/* The legend line (the retail "mov edx, clinch string"). */
const u16 *FC sr_legend(u32 line) {
    u32 v = sr_state[0];
    if (line > 3)
        line = 0;
    if (v == 0 || v > VIEWS)
        return (const u16 *)retail_legend[line];
    return legend_text[v - 1][line];
}
