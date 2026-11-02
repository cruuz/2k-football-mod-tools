/* Coaching carousel (job c6-carousel, beta 80). EXPERIMENTAL.

   Freestanding i386 code for the late allocator owner nfl2k5_coach_carousel, built by
   tools/nfl2k5_coach_carousel_build.py into mod_editor/core/nfl2k5_coach_carousel_code.py; no retail bytes live here.
   Game routines are called through their fixed retail addresses; the only relocations are this blob's own labels. The
   blob owns no writable memory: everything it keeps lives on the stack for one Advance to offseason.

   WHEN. Advance to offseason (stage 9 of FUN_002480B0) ends with "call 0x247B40", the season rollover; the patch site
   at 0x248632 enters carousel_run instead (stubs.S), which
     1. reads every club's season from the league grid (regular season, playoffs, Super Bowl) while it is still there,
     2. runs the retail rollover (so the owners hooked inside it still run: practice squad, economy, team column),
     3. decides which CPU clubs change head coach and whom they hire, rewrites those clubs' coach records, and shows
        one "COACHING CHANGES" notice for every three changes.
   Owner Firing (0xE60144, saved with the franchise) is the switch: 0 Off (nothing here runs except the rollover),
   1 CPU Teams, 2 All Teams (the retail owner check may also end the user's time; see carousel_user_gate). A club a
   user controls never changes coach here.

   DECISION. Hazard by regular-season winning share, with three curves for the coach's seasons with the club (1, 2,
   3 or more: the rollover's count +0x1C), a flat rate for a playoff club, times the club's owner factor (in 1/32).
   One league random draw per eligible club, in club order (the top 16 bits of the native generator); at most
   max_changes per offseason (the highest hazards win when more come up). Parameters: the 176-byte block at carousel_params (layout PARAMS in the Python module).

   HIRING. Vacancies are filled worst record first. Each first reserves a candidate from the hiring pool (a checked
   block the Studio writes into the coach string region of the roster, so it travels with every franchise save; magic
   "2K5CPOOL", layout POOL in the Python module): a weighted random pick among entries no club employs (employed =
   some club's coach record points at the entry's last-name string). A vacancy that gets no candidate is cancelled
   (that club keeps its coach). Then, with rehire_percent, a vacancy hires instead the most successful coach another
   club let go this offseason. The record is rewritten in place (the club keeps pointing at its own record):
     pool hire: names point at the pool strings; career, picture, ratings and personality come from the entry;
                tendencies, body (sideline model) and +0x14/+0x16 stay with the club;
     rehire:    the whole record of the coach who left (read after the rollover), except the body;
     both:      seasons with the club, this season and the streak start at 0; flag 0x02 (generic announcer line) set,
                flag 0x01 (free record) clear.
   On any doubt nothing changes: no pool, a foreign coach pointer, a club with no games, a bad parameter block. */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define H(a) (*(volatile u16 *)(a))
#define B(a) (*(volatile u8 *)(a))

#define ROLLOVER   ((void (*)(void))0x00247B40)
#define NOTICE     ((void (FC *)(u32, const u16 *))0x0014E520)  /* modal one-button information dialog */
#define TEAM_COUNT ((u32 (*)(void))0x000C4BE0)
#define TEAM_AT    ((u32 (FC *)(u32))0x000C4C50)
#define IS_HUMAN   ((u32 (FC *)(u32))0x000C4D50)
#define WIN_ROW    ((u32 (FC *)(u32, u32))0x000C75A0)
#define LOSS_ROW   ((u32 (FC *)(u32, u32))0x000C7620)
#define TIE_ROW    ((u32 (FC *)(u32, u32))0x000C76A0)
#define RAND       ((u32 (*)(void))0x00048BC0)               /* the league random number generator */

#define OWNER_FIRING 0x00E60144u
#define LEAGUE_MODE  0x00E576A0u
#define SB_ROW_IMM   0x00133A41u    /* the Super Bowl week row: 0x14 retail, 0x15 with the 18-week season */
#define ROSTER       0x00B72918u    /* the roster object (the arena root) */
#define ARENA_SIZE   0x00B72808u    /* the arena length */

#define CLUBS 32u
#define MAXC 12u                    /* hard cap of changes per offseason (the parameter block may ask for fewer) */
#define REC 0xA8u                   /* coach record */
#define ENTRY 64u                   /* pool entry */
#define MAX_POOL 48u

/* parameter block (176 bytes) */
#define P_VERSION 4
#define P_MAXC 5
#define P_REHIRE 6
#define P_PLAYOFF 8
#define P_CURVES 12                 /* u16[3][21]: tenure 1, 2, 3+; winning share 0, .05, .. 1.0 */
#define P_OWNER 138                 /* u8[32] in 1/32 */

extern const u8 carousel_params[];

struct Club {
    u32 team, coach;
    u8 w, l, t, playoffs;
    u8 pw, pl, title, human;
    u16 pct;                        /* regular-season winning share in 1/1000, ties count half */
    u8 eligible, index;
};

struct Move {
    u32 hazard;
    u8 club;                        /* index into clubs[] */
    u8 kind;                        /* 1 pool, 2 rehire */
    u8 entry;                       /* pool entry (kind 1) */
    u8 from;                        /* move index of the coach rehired (kind 2) */
    u8 taken;                       /* this move's departed coach was rehired elsewhere */
    u8 pad[3];
};

static u32 p16(const u8 *p, u32 at) { return (u32)p[at] | ((u32)p[at + 1] << 8); }

static u32 params_ok(void) {
    const u8 *p = carousel_params;
    return p[0] == 'C' && p[1] == '6' && p[2] == 'M' && p[3] == '1' && p[P_VERSION] == 1 && p[P_MAXC]
           && p[P_REHIRE] <= 100;
}

/* ---- the hiring pool ------------------------------------------------------------------------------------------ */
static u32 adler(const u8 *p, u32 n) {
    u32 a = 1, b = 0;
    for (u32 i = 0; i < n; i++) {
        a = (a + p[i]) % 65521;
        b = (b + a) % 65521;
    }
    return (b << 16) | a;
}

static u32 text_ok(const u8 *pool, u32 size, u32 at) {
    if (at & 1 || at >= size)
        return 0;
    for (u32 i = at; i + 1 < size; i += 2)
        if (!pool[i] && !pool[i + 1])
            return i - at <= 2 * 24;                     /* at most 24 characters */
    return 0;
}

/* The checked pool block, or 0. It sits somewhere in the arena (the Studio puts it in the free tail of the coach string
   region): found by its magic on a 4-byte step, then checked whole. */
static const u8 *find_pool(void) {
    u32 root = G(ROSTER), size = G(ARENA_SIZE);
    if (!root || root & 3 || size < 0x2000 || size > 0x400000)
        return 0;
    for (u32 a = root; a + 16 <= root + size; a += 4) {
        if (G(a) != 0x43354B32u || G(a + 4) != 0x4C4F4F50u)   /* "2K5C" "POOL" */
            continue;
        const u8 *p = (const u8 *)a;
        u32 count = p[9], bytes = p16(p, 10);
        if (p[8] != 1 || !count || count > MAX_POOL || bytes < 16 + ENTRY * count || bytes > 0x1000 || bytes & 3
            || a + bytes > root + size)
            continue;
        if (adler(p + 16, bytes - 16) != G(a + 12))
            continue;
        u32 good = 1;
        for (u32 k = 0; k < count && good; k++) {
            const u8 *e = p + 16 + ENTRY * k;
            for (u32 f = 0; f < 10; f += 2)
                if (p16(e, f) < 16 + ENTRY * count || !text_ok(p, bytes, p16(e, f)))
                    good = 0;
        }
        if (good)
            return p;
    }
    return 0;
}

/* ---- records -------------------------------------------------------------------------------------------------- */
/* The club's coach record when it is one of the roster's coach records, else 0. */
static u32 coach_of(u32 team) {
    u32 root = G(ROSTER);
    if (!team || !root)
        return 0;
    u32 coach = G(team + 0x14C), table = G(root + 0x34), count = G(root + 0x30);
    if (!coach || !table || count > 64 || coach < table || coach >= table + count * REC || (coach - table) % REC)
        return 0;
    return coach;
}

static void copy_bytes(u8 *to, const u8 *from, u32 n) {
    for (u32 i = 0; i < n; i++)
        to[i] = from[i];
}

static u32 employed(const struct Club *clubs, u32 n, u32 last_name) {
    for (u32 i = 0; i < n; i++)
        if (clubs[i].coach && G(clubs[i].coach + 4) == last_name)
            return 1;
    return 0;
}

static void fresh(u32 rec) {
    H(rec + 0x1C) = 0;                               /* seasons with the club */
    H(rec + 0x26) = 0;                               /* this season W L T */
    H(rec + 0x28) = 0;
    H(rec + 0x2A) = 0;
    H(rec + 0x2C) = 0;                               /* streak kind and length */
    H(rec + 0x2E) = 0;
    B(rec + 0x1A) = (u8)((B(rec + 0x1A) | 0x02) & ~0x01);
}

static void hire_pool(u32 rec, const u8 *pool, u32 entry) {
    const u8 *e = pool + 16 + ENTRY * entry;
    for (u32 f = 0; f < 5; f++)
        G(rec + 4 * f) = (u32)pool + p16(e, 2 * f);
    H(rec + 0x40) = (u16)p16(e, 10);                 /* picture */
    H(rec + 0x3E) = e[14];                           /* personality (sideline reactions) */
    static const u8 career[10] = {0x1E, 0x20, 0x22, 0x24, 0x30, 0x32, 0x34, 0x36, 0x38, 0x3A};
    for (u32 k = 0; k < 10; k++)
        H(rec + career[k]) = (u16)p16(e, 16 + 2 * k);
    H(rec + 0x3C) = 0;                               /* longest winning streak */
    copy_bytes((u8 *)(rec + 0x42), e + 36, 23);      /* ratings */
    fresh(rec);
}

static void hire_back(u32 rec, const u8 *saved) {
    u16 body = H(rec + 0x18);
    copy_bytes((u8 *)rec, saved, REC);
    H(rec + 0x18) = body;                            /* the club's sideline model stays */
    fresh(rec);
}

/* ---- the decision ------------------------------------------------------------------------------------------------ */
static u32 hazard(const struct Club *c) {
    const u8 *p = carousel_params;
    u32 base;
    if (c->playoffs) {
        base = p16(p, P_PLAYOFF);
    } else {
        u32 tenure = H(c->coach + 0x1C);
        u32 row = tenure <= 1 ? 0 : tenure == 2 ? 1 : 2;
        u32 k = c->pct / 50, f = c->pct % 50;
        const u8 *curve = p + P_CURVES + 42 * row;
        i32 a = (i32)p16(curve, 2 * k), b = k < 20 ? (i32)p16(curve, 2 * k + 2) : a;
        base = (u32)(a + (b - a) * (i32)f / 50);
    }
    base = base * p[P_OWNER + c->index] / 32;
    return base > 65535 ? 65535 : base;
}

/* career success of a departed coach (for the rehire pick): wins - losses + 4 x playoff wins + 12 x titles */
static i32 standing(const u8 *saved) {
    return (i32)(saved[0x20] | saved[0x21] << 8) - (i32)(saved[0x22] | saved[0x23] << 8)
           + 4 * (i32)(saved[0x34] | saved[0x35] << 8) + 12 * (i32)(saved[0x38] | saved[0x39] << 8);
}

/* ---- text ------------------------------------------------------------------------------------------------------ */
static u16 *put_ascii(u16 *out, const char *text) {
    while (*text)
        *out++ = (u16)(u8)*text++;
    return out;
}

static u16 *put_text(u16 *out, const u16 *text, u32 limit) {
    for (u32 i = 0; text && text[i] && i < limit; i++)
        *out++ = text[i];
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

static u16 *put_name(u16 *out, const u8 *rec) {
    out = put_text(out, (const u16 *)(*(const u32 *)rec), 24);
    *out++ = ' ';
    return put_text(out, (const u16 *)(*(const u32 *)(rec + 4)), 24);
}

/* "Raiders: Klint Kubiak out (3-14), Vic Fangio in" */
static u16 *put_change(u16 *out, const struct Club *c, const u8 *before, u32 rec) {
    *out++ = '\n';
    out = put_text(out, (const u16 *)G(c->team + 0x104), 20);
    out = put_ascii(out, ": ");
    out = put_name(out, before);
    out = put_ascii(out, " out (");
    out = put_uint(out, c->w);
    *out++ = '-';
    out = put_uint(out, c->l);
    if (c->t) {
        *out++ = '-';
        out = put_uint(out, c->t);
    }
    out = put_ascii(out, "), ");
    out = put_name(out, (const u8 *)rec);
    return put_ascii(out, " in");
}

/* ---- the advance ----------------------------------------------------------------------------------------------- */
void FC carousel_run(u32 menu) {
    u32 mode = G(OWNER_FIRING), row_sb = B(SB_ROW_IMM);
    if (G(LEAGUE_MODE) != 2 || mode < 1 || mode > 2 || !params_ok() || row_sb < 0x10 || row_sb > 0x20) {
        ROLLOVER();
        return;
    }
    struct Club clubs[CLUBS];
    u32 n = TEAM_COUNT();
    n = n > CLUBS ? CLUBS : n;
    u32 regular = row_sb - 3;                        /* wild card, divisional and conference rows come before it */
    for (u32 i = 0; i < n; i++) {
        struct Club *c = &clubs[i];
        u32 team = TEAM_AT(i), w = 0, l = 0, t = 0, pw = 0, pl = 0, title = 0;
        c->team = team;
        c->coach = coach_of(team);
        c->index = (u8)i;
        c->human = (u8)(team && IS_HUMAN(team) ? 1 : 0);
        if (team && c->coach)
            for (u32 r = 0; r <= row_sb; r++) {
                u32 a = WIN_ROW(team, r), b = LOSS_ROW(team, r);
                if (r < regular) {
                    w += a;
                    l += b;
                    t += TIE_ROW(team, r);
                } else {
                    pw += a;
                    pl += b;
                    if (r == row_sb)
                        title = a;
                }
            }
        c->w = (u8)(w > 255 ? 255 : w);
        c->l = (u8)(l > 255 ? 255 : l);
        c->t = (u8)(t > 255 ? 255 : t);
        c->pw = (u8)(pw > 15 ? 15 : pw);
        c->pl = (u8)(pl > 15 ? 15 : pl);
        c->playoffs = (u8)(pw + pl ? 1 : 0);
        c->title = (u8)(title ? 1 : 0);
        u32 games = w + l + t;
        c->pct = (u16)(games ? (2 * w + t) * 500 / games : 0);
        c->eligible = (u8)(team && c->coach && games && !c->human);
    }

    ROLLOVER();

    const u8 *pool = find_pool();
    if (!pool)
        return;
    u32 count = pool[9];
    struct Move moves[MAXC];
    u32 nm = 0, cap = carousel_params[P_MAXC] > MAXC ? MAXC : carousel_params[P_MAXC];
    /* fire: one draw per eligible club, in club order; keep the highest hazards when more than the cap come up */
    for (u32 i = 0; i < n; i++) {
        if (!clubs[i].eligible)
            continue;
        u32 h = hazard(&clubs[i]), roll = RAND() >> 16;
        if (roll >= h)
            continue;
        u32 at = nm;
        if (nm == cap) {
            u32 low = 0;
            for (u32 k = 1; k < nm; k++)
                if (moves[k].hazard < moves[low].hazard)
                    low = k;
            if (moves[low].hazard >= h)
                continue;
            at = low;
        } else {
            nm++;
        }
        moves[at].hazard = h;
        moves[at].club = (u8)i;
        moves[at].kind = 0;
        moves[at].taken = 0;
    }
    if (!nm)
        return;
    /* worst regular-season record first (then club order) */
    for (u32 a = 1; a < nm; a++)
        for (u32 b = a; b > 0; b--) {
            struct Club *x = &clubs[moves[b - 1].club], *y = &clubs[moves[b].club];
            if (x->pct < y->pct || (x->pct == y->pct && x->index < y->index))
                break;
            struct Move m = moves[b - 1];
            moves[b - 1] = moves[b];
            moves[b] = m;
        }
    /* the departed coaches as the rollover left them */
    u8 saved[MAXC][REC];
    for (u32 k = 0; k < nm; k++)
        copy_bytes(saved[k], (const u8 *)clubs[moves[k].club].coach, REC);
    /* reserve a pool candidate for every vacancy; none left = that club keeps its coach */
    u8 reserved[MAX_POOL];
    for (u32 e = 0; e < count; e++)
        reserved[e] = (u8)employed(clubs, n, (u32)pool + p16(pool + 16 + ENTRY * e, 2));
    for (u32 k = 0; k < nm; k++) {
        u32 total = 0;
        for (u32 e = 0; e < count; e++)
            if (!reserved[e])
                total += pool[16 + ENTRY * e + 12];
        if (!total)
            continue;
        u32 pick = (RAND() >> 16) % total, e = 0;
        for (; e < count; e++) {
            if (reserved[e])
                continue;
            u32 wgt = pool[16 + ENTRY * e + 12];
            if (pick < wgt)
                break;
            pick -= wgt;
        }
        if (e == count)
            continue;
        reserved[e] = 1;
        moves[k].kind = 1;
        moves[k].entry = (u8)e;
    }
    /* rehire: a vacancy may take instead the most successful coach another club let go */
    for (u32 k = 0; k < nm; k++) {
        if (moves[k].kind != 1 || (RAND() >> 16) % 100 >= carousel_params[P_REHIRE])
            continue;
        i32 best = -0x7FFFFFFF;
        u32 pick = MAXC;
        for (u32 j = 0; j < nm; j++)
            if (j != k && moves[j].kind && !moves[j].taken && standing(saved[j]) > best) {
                best = standing(saved[j]);
                pick = j;
            }
        if (pick == MAXC)
            continue;
        reserved[moves[k].entry] = 0;
        moves[k].kind = 2;
        moves[k].from = (u8)pick;
        moves[pick].taken = 1;
    }
    /* write the records, then tell the user, three changes a notice */
    u32 done = 0;
    for (u32 k = 0; k < nm; k++) {
        u32 rec = clubs[moves[k].club].coach;
        if (moves[k].kind == 1)
            hire_pool(rec, pool, moves[k].entry);
        else if (moves[k].kind == 2)
            hire_back(rec, saved[moves[k].from]);
        else
            continue;
        done++;
    }
    if (!done)
        return;
    u16 text[300], *out = text;
    u32 shown = 0;
    for (u32 k = 0; k < nm; k++) {
        if (!moves[k].kind)
            continue;
        if (shown % 3 == 0) {
            out = text;
            out = put_ascii(out, "COACHING CHANGES");
        }
        out = put_change(out, &clubs[moves[k].club], saved[k], clubs[moves[k].club].coach);
        shown++;
        if (shown % 3 == 0 || shown == done) {
            *out = 0;
            NOTICE(menu, text);
        }
    }
}
