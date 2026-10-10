/* Player Card honors page and live award history (job F5, beta 77). EXPERIMENTAL / UNWITNESSED.

   Freestanding i386 code for the late allocator owner nfl2k5_honors. Built by tools/nfl2k5_honors_build.py into
   mod_editor/core/nfl2k5_honors_code.py; no retail bytes live here. Every game routine is called through its
   fixed retail address (no relocation); the only relocations are this blob's own labels and honors_state.

   History words (player+0x2C stream, the game's career-stat pool): value 0..15, field 16..22, season slot 23..27,
   deleted 28, postseason 29, folded 30, last 31. One field per honor, value 1 in the season it was won. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef short i16;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define HONORS 10
#define FIELD0 96

/* the game's text context (0x80 bytes) and its retail helpers */
#define TEXT_INIT  ((void (FC *)(void *))0x00046920)
#define TEXT_FONT  ((void (FC *)(void *, u32))0x000469B0)
#define TEXT_ALIGN ((void (FC *)(void *, u32))0x00046A00)
#define TEXT_POS   ((void (FC *)(void *, float, float, float))0x00046A70)
#define TEXT_COLOR ((void (FC *)(void *, u32))0x00046B50)
#define TEXT_WIDTH ((i32 (FC *)(void *, const u16 *))0x00046C50)
#define TEXT_DRAW  ((void (FC *)(void *, const u16 *))0x000F1C70)
#define FONT_GET   ((u32 (FC *)(u32))0x000EF850)
/* history pool: set class (0 regular, 1 postseason), set a field in the player's current season slot */
#define CLASS_SET  ((void (FC *)(u32))0x0014EDB0)
#define HIST_SET   ((void (FC *)(u32, u32, u32))0x0014F430)
/* league: Super Bowl predicate, cell scores and teams, team player iterator */
#define IS_SUPER_BOWL ((u32 (*)(void))0x00133A30)
#define HOME_SCORE ((i32 (FC *)(u32, u32))0x000C5110)
#define AWAY_SCORE ((i32 (FC *)(u32, u32))0x000C5150)
#define HOME_TEAM  ((u32 (FC *)(u32, u32))0x000C4E00)
#define AWAY_TEAM  ((u32 (FC *)(u32, u32))0x000C4E20)
#define TEAM_FIRST ((u32 (FC *)(u32))0x000C3E70)
#define TEAM_NEXT  ((u32 (FC *)(u32, u32))0x000C3E80)

#define CARD_PLAYER 0x00C90248u     /* the Player Card's player record */
#define CARD_YEAR_IMM 0x003204ADu   /* the card's own Yr base: mov ecx, base_year + 11 */
#define SEASONS 0x00E576B8u         /* seasons elapsed in this franchise */
#define LEAGUE_MODE 0x00E576A0u     /* 2 = Franchise */
#define WEEK 0x00E576B4u
#define CELL 0x00E576BCu
#define CLASS 0x00BD7F98u
#define AWARDS 0x00E5A2F0u          /* season object (FUN_000C5C00); award slots {player*, team*} */
#define BLACK 0xFF101010u

enum { H_MVP, H_OPOY, H_DPOY, H_OROY, H_DROY, H_SB, H_SBMVP, H_PB, H_AP, H_RUSH };

extern volatile u32 honors_state[4];  /* [0] page (0 = retail card, 1 = honors) */

typedef struct { u32 count[HONORS]; u32 years[HONORS]; u32 earlier[HONORS]; i32 earlier_slot[HONORS]; } Tally;

/* fixed-width UTF-16 labels: the ten rating slots, then the year-line labels */
static const u16 slot_label[HONORS][12] = {
    {'M','V','P',0}, {'O','F','F','.',' ','P','O','Y',0}, {'D','E','F','.',' ','P','O','Y',0},
    {'O','F','F','.',' ','R','O','O','K','I','E',0}, {'D','E','F','.',' ','R','O','O','K','I','E',0},
    {'S','U','P','E','R',' ','B','O','W','L','S',0}, {'S','B',' ','M','V','P',0},
    {'P','R','O',' ','B','O','W','L','S',0}, {'A','L','L','-','P','R','O',0},
    {'R','U','S','H',' ','T','I','T','L','E','S',0},
};
/* rating slot i shows honor slot_honor[i]: left column MVP OPOY DPOY OROY DROY, right SB SBMVP PB AP RUSH */
static const unsigned char slot_honor[HONORS] = {H_MVP, H_OPOY, H_DPOY, H_OROY, H_DROY, H_SB, H_SBMVP, H_PB, H_AP, H_RUSH};
static const float slot_x[2] = {310.0f, 490.0f};
static const float slot_y[5] = {318.0f, 333.0f, 347.0f, 362.0f, 377.0f};
/* year lines: honors in importance order, their labels */
static const unsigned char line_honor[HONORS] = {H_MVP, H_SB, H_SBMVP, H_OPOY, H_DPOY, H_OROY, H_DROY, H_AP, H_PB, H_RUSH};
static const u16 line_label[HONORS][12] = {
    {'M','V','P',':',0}, {'O','F','F','.',' ','P','O','Y',':',0}, {'D','E','F','.',' ','P','O','Y',':',0},
    {'O','F','F','.',' ','R','O','Y',':',0}, {'D','E','F','.',' ','R','O','Y',':',0},
    {'S','U','P','E','R',' ','B','O','W','L',':',0}, {'S','B',' ','M','V','P',':',0},
    {'P','R','O',' ','B','O','W','L',':',0}, {'A','L','L','-','P','R','O',':',0},
    {'R','U','S','H',' ','T','I','T','L','E',':',0},
};
static const u16 none_label[] = {'H','O','N','O','R','S',':',0};
static const u16 none_value[] = {'N','O','N','E',' ','Y','E','T',0};
static const u16 pre_text[] = {'p','r','e',' ',0};
static const float line_y[3] = {137.0f, 154.0f, 171.0f};

/* One pass over the card player's stream: per honor, total, the slots won (bit mask) and folded totals. */
static void tally(u32 player, Tally *t) {
    for (u32 h = 0; h < HONORS; h++) {
        t->count[h] = 0;
        t->years[h] = 0;
        t->earlier[h] = 0;
        t->earlier_slot[h] = -1;
    }
    if (!player)
        return;
    const volatile u32 *w = (const volatile u32 *)G(player + 0x2C);
    if (!w)
        return;
    for (u32 n = 0; n < 4096; n++, w++) {
        u32 word = *w;
        u32 h = ((word >> 16) & 0x7F) - FIELD0;
        if (h < HONORS && !(word & 0x30000000)) {          /* live, regular-season class */
            u32 value = (u32)(i32)(i16)(word & 0xFFFF);
            if ((i32)value > 0) {
                t->count[h] += value;
                if (word & 0x40000000) {                     /* folded: seasons up to this slot */
                    t->earlier[h] += value;
                    t->earlier_slot[h] = (i32)((word >> 23) & 31);
                } else {
                    t->years[h] |= 1u << ((word >> 23) & 31);
                }
            }
        }
        if (word & 0x80000000)
            break;
    }
}

/* Append decimal text; returns the new end. */
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

static u16 *put_text(u16 *out, const u16 *text) {
    while (*text)
        *out++ = *text++;
    return out;
}

/* The card's own year for a season slot: base + seasons elapsed - (years pro - slot). */
static i32 slot_year(u32 player, u32 slot) {
    i32 base = (i32)G(CARD_YEAR_IMM) - 11;
    i32 count = (i32)((G(player + 0x24) >> 8) & 31);
    return base + (i32)G(SEASONS) - count + (i32)slot;
}

/* Years text, e.g. "2018 2022", "pre 2019 (2) 2021-24": runs of three or more seasons collapse. */
static void years_text(u32 player, const Tally *t, u32 h, u16 *out, const u16 *end) {
    const u16 *start = out;
    if (t->earlier[h]) {
        out = put_text(out, pre_text);
        out = put_uint(out, (u32)slot_year(player, (u32)t->earlier_slot[h]));
        if (t->earlier[h] > 1) {
            *out++ = ' ';
            *out++ = '(';
            out = put_uint(out, t->earlier[h]);
            *out++ = ')';
        }
    }
    u32 mask = t->years[h];
    for (u32 s = 0; s < 32 && out + 16 < end; s++) {
        if (!(mask & (1u << s)))
            continue;
        u32 last = s;
        while (last + 1 < 32 && (mask & (1u << (last + 1))))
            last++;
        if (out != start)
            *out++ = ' ';
        out = put_uint(out, (u32)slot_year(player, s));
        if (last >= s + 2) {
            *out++ = '-';
            u32 y = (u32)slot_year(player, last) % 100;
            *out++ = (u16)('0' + y / 10);
            *out++ = (u16)('0' + y % 10);
            s = last;
        }
    }
    *out = 0;
}

static void text_start(u32 *ctx, u32 font, u32 align) {
    TEXT_INIT(ctx);
    TEXT_COLOR(ctx, BLACK);
    TEXT_FONT(ctx, FONT_GET(font));
    TEXT_ALIGN(ctx, align);
}

/* Page 2, rating panel: label right-aligned at x - 8, count left-aligned at x (the retail rating layout). */
void honors_counts(void) {
    Tally t;
    u32 ctx[32];
    u16 value[12];
    u32 player = G(CARD_PLAYER);
    tally(player, &t);
    for (u32 i = 0; i < HONORS; i++) {
        float x = slot_x[i / 5], y = slot_y[i % 5];
        text_start(ctx, 3, 2);
        TEXT_POS(ctx, x - 8.0f, y, 20.0f);
        TEXT_DRAW(ctx, slot_label[i]);
        *put_uint(value, t.count[slot_honor[i]]) = 0;
        TEXT_ALIGN(ctx, 1);
        TEXT_POS(ctx, x, y, 20.0f);
        TEXT_DRAW(ctx, value);
    }
}

/* Page 2, bio panel: up to three "LABEL: years" lines (the retail bio font and first column). */
void honors_years(void) {
    Tally t;
    u32 ctx[32];
    u16 text[96];
    u32 player = G(CARD_PLAYER);
    u32 line = 0;
    tally(player, &t);
    for (u32 k = 0; k < HONORS && line < 3; k++) {
        u32 h = line_honor[k];
        if (!t.count[h])
            continue;
        years_text(player, &t, h, text, text + 96);
        text_start(ctx, 8, 1);
        TEXT_POS(ctx, 198.0f, line_y[line], 20.0f);
        TEXT_DRAW(ctx, line_label[h]);
        i32 width = TEXT_WIDTH(ctx, line_label[h]);
        TEXT_POS(ctx, 198.0f + (float)(width + 8), line_y[line], 20.0f);
        TEXT_DRAW(ctx, text);
        line++;
    }
    if (!line) {
        text_start(ctx, 8, 1);
        TEXT_POS(ctx, 198.0f, line_y[0], 20.0f);
        TEXT_DRAW(ctx, none_label);
        i32 width = TEXT_WIDTH(ctx, none_label);
        TEXT_POS(ctx, 198.0f + (float)(width + 8), line_y[0], 20.0f);
        TEXT_DRAW(ctx, none_value);
    }
}

/* Set an honor (value 1) in the player's current season slot, always in the regular-season class so the
   rollover's postseason wipe keeps it. Setting is idempotent: an existing entry is overwritten with 1. */
static void set_honor(u32 player, u32 h) {
    if (!player)
        return;
    u32 saved = G(CLASS);
    CLASS_SET(0);
    HIST_SET(player, FIELD0 + h, 1);
    CLASS_SET(saved);
}

/* After the game's season awards (week index 16, FUN_00116920 and its rushing-title tail). */
void commit_season(void) {
    if (G(LEAGUE_MODE) != 2)
        return;
    set_honor(G(AWARDS + 0x5800), H_MVP);
    set_honor(G(AWARDS + 0x5810), H_OPOY);
    set_honor(G(AWARDS + 0x5818), H_DPOY);
    set_honor(G(AWARDS + 0x5820), H_OROY);
    set_honor(G(AWARDS + 0x5828), H_DROY);
    for (u32 off = 0x5830; off <= 0x5878; off += 8)       /* the game's best player per position group */
        set_honor(G(AWARDS + off), H_AP);
    set_honor(G(AWARDS + 0x5880), H_RUSH);
}

/* After a game commit (FUN_00135310): for the Super Bowl, every player of the winner and the SB MVP. */
void commit_sb(void) {
    if (G(LEAGUE_MODE) != 2 || !IS_SUPER_BOWL())
        return;
    u32 week = G(WEEK), cell = G(CELL);
    i32 home = HOME_SCORE(week, cell), away = AWAY_SCORE(week, cell);
    if (home != away) {
        u32 team = home > away ? HOME_TEAM(week, cell) : AWAY_TEAM(week, cell);
        if (team)
            for (u32 p = TEAM_FIRST(team); p; p = TEAM_NEXT(team, p))
                set_honor(p, H_SB);
    }
    set_honor(G(AWARDS + 0x5888), H_SBMVP);
}
