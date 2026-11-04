/* Modern franchise injured reserve (b780 IR1). EXPERIMENTAL / UNWITNESSED in game.

   Freestanding i386 code for the late allocator owner nfl2k5_injured_reserve, built by
   tools/nfl2k5_injured_reserve_build.py into mod_editor/core/nfl2k5_injured_reserve_code.py. No retail bytes live here.
   Every address beyond the game's fixed routines and globals is in ir_config (stubs.S), filled by the Studio when it
   installs the owner: the owner's writable store and the club append routine this build uses.

   Rules (Noah, 2026-11-03: "Do the full modern IR now"):
   * a player on injured reserve stays with his club, off the 53, so the club can fill the spot; up to 20 per club;
   * he must miss at least 4 of his club's games (played cells of the schedule grid, so a bye is not a game);
   * each club brings back at most 8 players a season; past that a player stays on injured reserve for the season;
   * CPU clubs (and the user's when "CPU manages my depth chart" is on, as retail) put a player with 4 or more weeks
     out on injured reserve and bring back a healthy one who served the minimum; at 53 the game's own cut-down
     (0x2BF9A0, surplus position first, lowest value) makes the room; after 6 returns only a player at least as
     valuable as the club's average comes back;
   * IR salaries stay in the cap: the retail payroll 0xC3F00 adds 0x246F20, which reads this store;
   * the season rollover brings every IR player back to his club (as retail) and resets the returns;
   * league slots 32 and 33 (the Pro Bowl teams) never touch the store (Q66).

   Store: the owner's writable data (struct store). The retail table 0xE421E0 (32 x 5 player pointers) is kept as a
   mirror of each club's first five entries, so every other reader of it (the practice squad and arena owners'
   "listed" checks, the native franchise save writer) keeps working unchanged.

   Save: the retail IR block of the franchise front office (+0x4FD0, 32 x 5 x {u16 index, u16}). The native writer
   puts the mirror's indices in the low halves and zero in the high halves; ir_save_ext then fills the high halves with
   the extension (layout in mod_editor/core/nfl2k5_injured_reserve_save.py; keep the two in step). The native loader
   reads only the low halves, so an older build loads the first five per club as its own season-ending IR. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef short i16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))

/* ---- game routines (retail addresses; callers' conventions read from the retail code) ------------------------- */
#define CLUB_AT ((u8 *(FC *)(u32))0x000C4C50)                    /* league index -> club */
#define CLUB_INDEX ((u32 (FC *)(u8 *))0x000C4CA0)                 /* club -> league index */
#define CLUB_COUNT ((u32 (*)(void))0x000C4BE0)                    /* league clubs (34 in the postseason) */
#define MODE_GET ((u32 (*)(void))0x000C4B80)                      /* 2 = franchise */
#define STAGE_GET ((u32 (*)(void))0x000C4BB0)                     /* [0xE576A4] */
#define HUMAN ((u32 (FC *)(u8 *))0x0013EC30)                      /* the club's human flag */
#define REMOVE ((void (FC *)(u8 *, u8 *, u32, u32))0x002BD900)    /* club, player, 0, 0: off the club, not to FA */
#define LOG_TXN ((void (FC *)(u32, u8 *, u8 *, u32, u32, u32))0x002BFDF0)   /* kind 0xC: placed on injured reserve */
#define RECOUNT ((void (FC *)(u8 *))0x000C3F00)                   /* club count and payroll (+0x124) */
#define VALUE ((float (FC *)(u8 *, u32))0x00246D80)               /* the cut-down's player value (kind 1) */
#define CUT_DOWN ((void (FC *)(u8 *, u32))0x002BF9A0)             /* club, limit: the CPU cut-down */
#define SALARY_A ((u32 (FC *)(u8 *))0x000E6380)
#define SALARY_B ((u32 (FC *)(u32, u32, u32))0x000E6020)
#define ASK ((u32 (FC *)(u8 *, const u16 *))0x0014E540)           /* yes/no dialog: 1 = yes */
#define TELL ((void (FC *)(u8 *, const u16 *))0x0014E520)         /* information dialog */
#define SELECTED ((u8 *(FC *)(u8 *))0x000F3250)                   /* the screen's selected player */
#define SCREEN ((u8 *(FC *)(u8 *))0x000F31B0)
#define REFRESH ((void (FC *)(u8 *))0x00174C70)
#define PLAYER_CLUB ((u8 *(FC *)(u8 *))0x00321530)                /* the club a player is on */
#define USER_CLUB ((u8 *(*)(void))0x0013EC80)                     /* [0xE3C0A0] */
#define STAGE_UI ((u32 (*)(void))0x00247AA0)
#define START_NEXT ((void (FC *)(u32))0x000C4EA0)                 /* displaced by the franchise-start site */

#define LEAGUE_ROOT 0x00B72918u
#define CPU_DEPTH 0x00E60140u                                     /* "CPU manages my depth chart" */
#define LEGACY_TABLE 0x00E421E0u
#define GRID 0x00E57C40u
#define GRID_CELLS 374u
#define PLAYED 3u

#define CLUBS 32u
#define CAP 20u
#define LEGACY 5u
#define EXT_CAP 102u
#define MIN_GAMES 4
#define RETURNS 8u
#define LONG_WEEKS 4u
#define SPARE_RETURNS 2u
#define ACTIVE 53u
#define SLOTS 65u
#define TEAM_COUNT 0x11Cu
#define INJURED 0x80000000u

#define F_SEASON 1u                                               /* stays on injured reserve for the season */
#define CARRY (-100)                                              /* rollover leftover: eligible at once */

struct entry { u8 *p; i16 base; u8 flags; u8 how; };
struct club { u8 n; u8 returns; u8 pad[2]; struct entry e[CAP]; };
struct store {
    u32 magic, version;
    u32 placed_cpu, placed_user, placed_start, back_cpu, back_user, season_ending, refused, rollover_back,
        rollover_kept, loads_extended, loads_legacy, saves, weeks, dropped;
    struct club c[CLUBS];
};

struct config { u32 magic, version; struct store *store; u32 flags; };
extern const struct config ir_config;
#define S (ir_config.store)

/* The club append: the practice squad owner's (0x3EE0D0, it checks the club's room and the reserves) when its rollover
   site 0x246FB6 calls its IR restore 0x2952B0, else the retail append 0xC3EE0. Read at run time, so the order the two
   owners are installed in does not matter. */
#define PS_RESTORE_SITE 0x00246FB6u
#define PS_RESTORE 0x002952B0u
static u32 ps_on(void) {
    const u8 *s = (const u8 *)PS_RESTORE_SITE;
    return s[0] == 0xE8 && PS_RESTORE_SITE + 5 + *(const u32 *)(s + 1) == PS_RESTORE;
}
static u32 APPEND(u8 *club, u8 *p) {
    if (ps_on()) return ((u32 (FC *)(u8 *, u8 *))0x003EE0D0)(club, p);
    ((void (FC *)(u8 *, u8 *))0x000C3EE0)(club, p);
    return 1;
}

enum { HOW_GAME = 0, HOW_CPU = 1, HOW_USER = 2, HOW_START = 3, HOW_LOAD = 4 };

static u8 *root(void) { return (u8 *)G(LEAGUE_ROOT); }
static u32 injured(const u8 *p) { return *(const u32 *)(p + 0x20) & INJURED; }
static u32 weeks_out(const u8 *p) { return (*(const u32 *)(p + 0x20) >> 22) & 0xFF; }
static u32 count_of(const u8 *club) { return club[TEAM_COUNT]; }

static i32 played(u32 c) {
    const u8 *cell = (const u8 *)GRID;
    i32 n = 0;
    for (u32 i = 0; i < GRID_CELLS; i++, cell += 8)
        if (cell[0] == PLAYED && (cell[1] == c || cell[2] == c)) n++;
    return n;
}

static i32 games(const struct entry *e, i32 now) {
    i32 g = now - e->base;
    return g < 0 ? 0 : g;
}

static u32 ext_total(void) {
    u32 t = 0;
    for (u32 c = 0; c < CLUBS; c++) if (S->c[c].n > LEGACY) t += S->c[c].n - LEGACY;
    return t;
}

static void mirror(u32 c) {
    u8 **slot = (u8 **)(LEGACY_TABLE + 20 * c);
    for (u32 i = 0; i < LEGACY; i++) slot[i] = i < S->c[c].n ? S->c[c].e[i].p : 0;
}

static i32 locate(const u8 *p, u32 *slot) {
    for (u32 c = 0; c < CLUBS; c++)
        for (u32 i = 0; i < S->c[c].n; i++)
            if (S->c[c].e[i].p == p) { if (slot) *slot = i; return (i32)c; }
    return -1;
}

static u32 on_list(const u8 *club, const u8 *p) {
    u8 *const *list = (u8 *const *)club;
    u32 n = count_of(club);
    for (u32 i = 0; i < n && i < SLOTS; i++) if (list[i] == p) return 1;
    return 0;
}

static void drop(u32 c, u32 i) {
    struct club *k = &S->c[c];
    for (u32 j = i; j + 1 < k->n; j++) k->e[j] = k->e[j + 1];
    k->n--;
    k->e[k->n].p = 0;
    mirror(c);
}

/* ---- the retail entry points, retargeted ------------------------------------------------------------------- */

FC u32 ir_count(u8 *club) {
    u32 c = CLUB_INDEX(club);
    return c < CLUBS ? S->c[c].n : 0;
}

FC u8 *ir_get(u8 *club, u32 i) {
    u32 c = CLUB_INDEX(club);
    return c < CLUBS && i < S->c[c].n ? S->c[c].e[i].p : 0;
}

void ir_clear(void) {
    u8 *a = (u8 *)&S->c[0];
    for (u32 i = 0; i < sizeof(S->c); i++) a[i] = 0;
    u32 *t = (u32 *)LEGACY_TABLE;
    for (u32 i = 0; i < CLUBS * LEGACY; i++) t[i] = 0;
    S->magic = 0x52493236u;  /* "62IR" */
    S->version = 1;
}

FC u32 ir_payroll(u8 *club) {
    if (MODE_GET() != 2) return 0;
    u32 c = CLUB_INDEX(club), total = 0;
    if (c >= CLUBS) return 0;
    for (u32 i = 0; i < S->c[c].n; i++) {
        u8 *p = S->c[c].e[i].p;
        u32 w = *(u32 *)(p + 0x24);
        total += SALARY_A(p);
        total += SALARY_B(*(u16 *)(p + 0x0A), (w >> 20) & 0xF, (w >> 24) & 0xF);
    }
    return total;
}

static u32 place(u8 *p, u8 *club, u32 how) {
    u32 c = CLUB_INDEX(club);
    if (c >= CLUBS || !p) return 0;                                   /* Q66: no Pro Bowl club, no write past */
    struct club *k = &S->c[c];
    u8 *r = root();
    u32 index = (u32)(p - *(u8 **)(r + 4)) / 0x54;
    if (k->n >= CAP || (k->n >= LEGACY && (ext_total() >= EXT_CAP || index > 0xFFF))) { S->refused++; return 0; }
    if (!on_list(club, p) || locate(p, 0) >= 0) return 0;
    k->e[k->n].p = p;
    k->e[k->n].base = (i16)played(c);
    k->e[k->n].flags = 0;
    k->e[k->n].how = (u8)how;
    k->n++;
    mirror(c);
    REMOVE(club, p, 0, 0);
    LOG_TXN(0xC, p, club, 0, 0, 1);
    RECOUNT(club);
    if (how == HOW_CPU) S->placed_cpu++;
    else if (how == HOW_START) S->placed_start++;
    else S->placed_user++;
    return 1;
}

FC u32 ir_place(u8 *p, u8 *club) { return place(p, club, HOW_GAME); }

FC u32 ir_find(u8 *p, u8 **club_out) {
    i32 c = locate(p, 0);
    if (c < 0) return 0;
    if (club_out) *club_out = CLUB_AT((u32)c);
    return 1;
}

static u32 append_room(u8 *club) {
    return ps_on() ? 1 : count_of(club) < SLOTS;                  /* the practice squad's append checks itself */
}

void ir_rollover(void) {
    for (u32 c = 0; c < CLUBS; c++) {
        u8 *club = CLUB_AT(c);
        struct club *k = &S->c[c];
        struct entry was[CAP];
        u32 n = k->n, kept = 0;
        for (u32 i = 0; i < n; i++) was[i] = k->e[i];
        k->n = 0;                      /* off the store (and the mirror) first: the append's own "owned" checks */
        mirror(c);
        for (u32 i = 0; i < n; i++) {
            struct entry e = was[i];
            if (club && append_room(club) && APPEND(club, e.p)) { S->rollover_back++; continue; }
            e.base = CARRY;                                           /* no room: stays, eligible at once */
            e.flags = 0;
            k->e[kept++] = e;
            S->rollover_kept++;
        }
        for (u32 i = kept; i < CAP; i++) k->e[i].p = 0;
        k->n = (u8)kept;
        k->returns = 0;
        mirror(c);
        if (club) RECOUNT(club);
    }
}

/* ---- returns ------------------------------------------------------------------------------------------------ */

enum { OK = 0, NOT_ON_IR, TOO_SOON, STILL_HURT, SEASON_OUT, NO_RETURNS, ROSTER_FULL, NOT_ADDED };

static u32 why_not(u32 c, u32 i, i32 now) {
    const struct entry *e = &S->c[c].e[i];
    if (e->flags & F_SEASON) return SEASON_OUT;
    if (games(e, now) < MIN_GAMES) return TOO_SOON;
    if (injured(e->p)) return STILL_HURT;
    if (S->c[c].returns >= RETURNS) return NO_RETURNS;
    return OK;
}

static u32 activate(u32 c, u32 i, u8 *club, u32 how) {
    struct club *k = &S->c[c];
    u8 *p = k->e[i].p;
    u32 limit = STAGE_GET() >= 8 ? ACTIVE : SLOTS;
    if (count_of(club) >= limit || !append_room(club)) return ROSTER_FULL;
    struct entry keep = k->e[i];
    drop(c, i);
    if (!APPEND(club, p)) {                                           /* refused: he stays where he was */
        for (u32 j = k->n; j > i; j--) k->e[j] = k->e[j - 1];
        k->e[i] = keep;
        k->n++;
        mirror(c);
        return NOT_ADDED;
    }
    k->returns++;
    RECOUNT(club);
    if (how == HOW_CPU) S->back_cpu++; else S->back_user++;
    return OK;
}

static float average_value(u8 *club) {
    u8 **list = (u8 **)club;
    u32 n = count_of(club);
    float sum = 0;
    for (u32 i = 0; i < n; i++) sum += VALUE(list[i], 1);
    return n ? sum / (float)n : 0;
}

/* human: the user's club when "CPU manages my depth chart" is on. Its injured players go on IR as retail's pass did,
   but nobody of his is released to make room: a return then waits for an open roster spot. */
static void cpu_week(u32 c, u8 *club, u32 human) {
    u8 *snap[SLOTS];
    u32 n = count_of(club);
    if (n > SLOTS) n = SLOTS;
    for (u32 i = 0; i < n; i++) snap[i] = ((u8 **)club)[i];
    for (u32 i = 0; i < n; i++)
        if (snap[i] && injured(snap[i]) && weeks_out(snap[i]) >= LONG_WEEKS) place(snap[i], club, HOW_CPU);
    i32 now = played(c);
    struct club *k = &S->c[c];
    for (u32 i = 0; i < k->n;) {
        u32 why = why_not(c, i, now);
        if (why == NO_RETURNS) { k->e[i].flags |= F_SEASON; S->season_ending++; i++; continue; }
        if (why != OK) { i++; continue; }
        if (k->returns >= RETURNS - SPARE_RETURNS && VALUE(k->e[i].p, 1) < average_value(club)) { i++; continue; }
        if (count_of(club) >= ACTIVE && !human) CUT_DOWN(club, ACTIVE - 1);
        if (activate(c, i, club, HOW_CPU) != OK) i++;
    }
}

void ir_weekly(void) {
    u32 stage = STAGE_GET();
    if (stage != 8 && stage != 9) return;
    S->weeks++;
    u32 n = CLUB_COUNT();
    if (n > CLUBS) n = CLUBS;                                          /* Q66: the Pro Bowl clubs are not walked */
    for (u32 c = 0; c < n; c++) {
        u8 *club = CLUB_AT(c);
        if (!club) continue;
        u32 human = HUMAN(club);
        if (human && !G(CPU_DEPTH)) continue;
        cpu_week(c, club, human);
    }
}

/* The franchise start (after the club loop of 0x13EE10): a roster's real IR players (injured, 4 or more weeks out)
   start on injured reserve, every club. */
void ir_start(void) {
    for (u32 c = 0; c < CLUBS; c++) {
        u8 *club = CLUB_AT(c);
        if (!club) continue;
        u8 *snap[SLOTS];
        u32 n = count_of(club);
        if (n > SLOTS) n = SLOTS;
        for (u32 i = 0; i < n; i++) snap[i] = ((u8 **)club)[i];
        for (u32 i = 0; i < n; i++)
            if (snap[i] && injured(snap[i]) && weeks_out(snap[i]) >= LONG_WEEKS) place(snap[i], club, HOW_START);
    }
}

FC void ir_start_hook(u32 ecx) {
    START_NEXT(ecx);
    ir_start();
}

/* ---- the user's IR action (both retail screens' button 1, the retail 0x247070) ----------------------------------- */

static const u16 T_PLACE[] = u"Placing a player on injured reserve takes him off your 53-man roster. He must miss at least "
                             u"4 games, and your club can bring back up to 8 players from injured reserve each season. "
                             u"Do you want to continue?";
static const u16 T_PLACE2[] = u"Place this player on the Injured Reserve list?";
static const u16 T_FULL[] = u"Your injured reserve list is full.";
static const u16 T_HEALTHY[] = u"Only an injured player can go on injured reserve.";
static const u16 T_BACK[] = u"Bring this player back from injured reserve? This uses one of your club's 8 returns for "
                            u"the season.";
static const u16 T_SOON[] = u"This player must miss at least 4 games on injured reserve before he can return.";
static const u16 T_HURT[] = u"This player is still injured. He can return once he is healthy.";
static const u16 T_SEASON[] = u"Your club has used all 8 returns from injured reserve this season. This player stays "
                              u"on injured reserve until the season ends.";
static const u16 T_ROOM[] = u"Your roster is full. Release a player before bringing this player back from injured "
                            u"reserve.";

FC void ir_user_action(u8 *ctx) {
    if (MODE_GET() != 2) return;
    u8 *p = SELECTED(ctx);
    if (!p) return;
    u32 stage = STAGE_UI();
    if (stage != 7 && stage != 8 && stage != 9) return;
    u8 *user = USER_CLUB();
    u32 slot;
    i32 c = locate(p, &slot);
    if (c >= 0) {
        u8 *club = CLUB_AT((u32)c);
        if (club != user) return;
        u32 why = why_not((u32)c, slot, played((u32)c));
        if (why == NO_RETURNS) { TELL(ctx, T_SEASON); return; }
        if (why == SEASON_OUT) { TELL(ctx, T_SEASON); return; }
        if (why == TOO_SOON) { TELL(ctx, T_SOON); return; }
        if (why == STILL_HURT) { TELL(ctx, T_HURT); return; }
        if (count_of(club) >= (stage >= 8 ? ACTIVE : SLOTS)) { TELL(ctx, T_ROOM); return; }
        if (!ASK(ctx, T_BACK)) return;
        why = activate((u32)c, slot, club, HOW_USER);
        if (why != OK) { TELL(ctx, T_ROOM); return; }
        REFRESH(SCREEN(ctx));
        return;
    }
    u8 *club = PLAYER_CLUB(p);
    if (!club || club != user) return;
    if (!injured(p)) { TELL(ctx, T_HEALTHY); return; }
    if (!ASK(ctx, T_PLACE) || !ASK(ctx, T_PLACE2)) return;
    if (!place(p, club, HOW_USER)) { TELL(ctx, T_FULL); return; }
    REFRESH(SCREEN(ctx));
}

/* ---- the save extension (front office +0x4FD0) ------------------------------------------------------------------ */

#define OFF_IR 0x4FD0u
#define CELLS 160u
#define W_MAGIC 0u
#define W_SUM 1u
#define W_RETURNS 2u
#define W_COUNTS 10u
#define W_STATES 18u
#define W_EXT 58u
#define MAGIC 0x5249u

static u16 *lo(u8 *office, u32 k) { return (u16 *)(office + OFF_IR + 4 * k); }
static u16 *hi(u8 *office, u32 k) { return (u16 *)(office + OFF_IR + 4 * k + 2); }
static u32 nib(u8 *office, u32 w, u32 i) { return (*hi(office, w + i / 4) >> (4 * (i % 4))) & 15; }
static void set_nib(u8 *office, u32 w, u32 i, u32 v) {
    u16 *h = hi(office, w + i / 4);
    *h = (u16)((*h & ~(15u << (4 * (i % 4)))) | ((v & 15) << (4 * (i % 4))));
}

static u16 checksum(u8 *office) {
    u32 a = 1, b = 0;
    for (u32 k = 0; k < CELLS; k++) { a = (a + *lo(office, k)) % 65521u; b = (b + a) % 65521u; }
    for (u32 k = W_RETURNS; k < CELLS; k++) { a = (a + *hi(office, k)) % 65521u; b = (b + a) % 65521u; }
    return (u16)(a ^ (b << 1) ^ (b >> 15));
}

static u32 state_of(const struct entry *e, i32 now) {
    i32 g = games(e, now);
    return (u32)(g > 7 ? 7 : g) | ((e->flags & F_SEASON) ? 8u : 0u);
}

/* After the native writer filled the 160 cells (low = mirror index or 0xFFFF, high = 0). */
void ir_save_ext(u8 *office) {
    u8 *r = root();
    u8 *table = *(u8 **)(r + 4);
    u32 w = W_EXT;
    for (u32 k = W_RETURNS; k < CELLS; k++) *hi(office, k) = 0;
    for (u32 c = 0; c < CLUBS; c++) {
        struct club *k = &S->c[c];
        i32 now = played(c);
        set_nib(office, W_RETURNS, c, k->returns);
        u32 extra = k->n > LEGACY ? k->n - LEGACY : 0;
        set_nib(office, W_COUNTS, c, extra);
        for (u32 i = 0; i < k->n && i < LEGACY; i++) set_nib(office, W_STATES, c * LEGACY + i, state_of(&k->e[i], now));
        for (u32 i = LEGACY; i < k->n && w < CELLS; i++, w++) {
            u32 index = (u32)(k->e[i].p - table) / 0x54;
            *hi(office, w) = (u16)((index & 0xFFF) | (state_of(&k->e[i], now) << 12));
        }
    }
    *hi(office, W_MAGIC) = MAGIC;
    *hi(office, W_SUM) = checksum(office);
    S->saves++;
}

static u32 listed_anywhere(const u8 *p) {
    for (u32 c = 0; c < CLUBS; c++) { u8 *club = CLUB_AT(c); if (club && on_list(club, p)) return 1; }
    return 0;
}

/* After the native loader put each low half's player into the retail table (mirror). */
void ir_load_ext(u8 *office) {
    u8 *r = root();
    u8 *table = *(u8 **)(r + 4);
    u32 players = *(u32 *)r;
    u32 ext = *hi(office, W_MAGIC) == MAGIC && *hi(office, W_SUM) == checksum(office);
    u8 **legacy = (u8 **)LEGACY_TABLE;
    u8 *a = (u8 *)&S->c[0];
    for (u32 i = 0; i < sizeof(S->c); i++) a[i] = 0;
    u32 w = W_EXT;
    for (u32 c = 0; c < CLUBS; c++) {
        struct club *k = &S->c[c];
        i32 now = played(c);
        for (u32 i = 0; i < LEGACY; i++) {
            u8 *p = legacy[c * LEGACY + i];
            if (!p || locate(p, 0) >= 0) continue;
            u32 st = ext ? nib(office, W_STATES, c * LEGACY + i) : 0;
            k->e[k->n].p = p;
            k->e[k->n].base = (i16)(now - (i32)(st & 7));
            k->e[k->n].flags = (st & 8) ? F_SEASON : 0;
            k->e[k->n].how = HOW_LOAD;
            k->n++;
        }
        if (ext) {
            k->returns = (u8)nib(office, W_RETURNS, c);
            for (u32 j = nib(office, W_COUNTS, c); j && w < CELLS; j--, w++) {
                u32 v = *hi(office, w), index = v & 0xFFF, st = v >> 12;
                u8 *p = table + 0x54 * index;
                if (index >= players || k->n >= CAP || locate(p, 0) >= 0 || listed_anywhere(p)) { S->dropped++; continue; }
                k->e[k->n].p = p;
                k->e[k->n].base = (i16)(now - (i32)(st & 7));
                k->e[k->n].flags = (st & 8) ? F_SEASON : 0;
                k->e[k->n].how = HOW_LOAD;
                k->n++;
            }
        }
        mirror(c);
    }
    if (ext) S->loads_extended++; else S->loads_legacy++;
    S->magic = 0x52493236u;
    S->version = 1;
}
