/* Season award vote and a 24-man All-Pro team (job b81-awards). EXPERIMENTAL /
   UNWITNESSED.

   Freestanding i386 code for the fixed-page owner nfl2k5_awards, built by tools/nfl2k5_awards_build.py into
   mod_editor/core/nfl2k5_awards_code.py; no retail bytes live here and the owner keeps no writable memory. Game routines
   are called through their fixed retail addresses; the only relocations are this blob's own labels. The plain-Python
   twin of every rule is mod_editor/core/nfl2k5_awards.py (choose_awards, all_pro).

   THE VOTE (site 0x116E5A, after the retail award pass and the champions owner's vote, before the honors owner records
   the slots). Replaces the five player awards and the best-at-position slots:
     MVP   quarterbacks: offence points x team factor x fatigue. Backs, receivers and tight ends only with a historic season
           (2,000 rushing yards, 2,400 scrimmage yards, 26 touchdowns or 1,950 receiving yards); defenders only past a
           record (24 sacks or 14 interceptions), worth 280 offence points x the larger fraction of the record. Team factor
           40% at .500 or worse to 100% at .750, +10 for one of the league's two best records. Fatigue: -15% for last
           season's MVP and -8% for each other MVP in the four seasons before (cap -30%), from the man's own MVP honors
           (history field 96).
     OPOY / OROY  offence points against each position's award season (tables), x 80-100% for the club's record.
     DPOY / DROY  10 a sack, 2 a QB hit (field 107), 20 an interception, 6 a forced fumble, 0.3 a tackle, x a position
           weight. The MVP is barred from OPOY and DPOY.
     ALL-PRO  QB 1, HB 1, FB 1, WR 3, TE 1, T 2, G 2, C 1, DE 2, DT 2, LB 2, CB 2, S 2, K 1, P 1 (24). The first of each
           retail category goes into the ten best-at-position slots (+0x5830..; the return-man slot is cleared) so the
           honors owner records them; the other fifteen get history field 104 here (Franchise only, regular class).

   The defensive credit (design R1) is not part of beta 81: simulated games keep no per-player defensive counters in
   the live records it re-drew (see mod_editor/core/nfl2k5_awards.py). */

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define GB(a) (*(volatile u8 *)(a))

/* game routines */
#define STAT       ((i32 (FC *)(u32, u32))0x0014EE40)        /* current season value of a history field */
#define HIST_AGO   ((i32 (FC *)(u32, u32, u32))0x0014EF20)   /* value N seasons ago */
#define HIST_SET   ((void (FC *)(u32, u32, u32))0x0014F430)
#define CLASS_SET  ((void (FC *)(u32))0x0014EDB0)
#define TEAM_FIRST ((u32 (FC *)(u32))0x000C3E70)
#define TEAM_NEXT  ((u32 (FC *)(u32, u32))0x000C3E80)
#define TEAM_COUNT ((u32 (*)(void))0x000C6430)
#define TEAM_AT    ((u32 (FC *)(u32))0x000C4C50)
#define CLUB_INDEX ((u32 (FC *)(u32))0x000C4CA0)
#define IR_COUNT   ((u32 (FC *)(u32))0x00246E50)
#define IR_GET     ((u32 (FC *)(u32, u32))0x00246EC0)
#define WINS       ((u32 (FC *)(u32))0x000C7720)
#define LOSSES     ((u32 (FC *)(u32))0x000C7750)
#define TIES       ((u32 (FC *)(u32))0x000C7780)
#define OVERALL    ((float (FC *)(u32, u32))0x00246D80)       /* the position overall, 0..1 */

#define AWARDS 0x00E5A2F0u          /* season object; slots {player*, team*} */
#define CLASS 0x00BD7F98u
#define LEAGUE_MODE 0x00E576A0u

enum { P_QB, P_K, P_P, P_WR, P_CB, P_FS, P_SS, P_HB, P_FB, P_TE, P_OLB, P_ILB, P_C, P_G, P_T, P_DT, P_DE };

typedef struct {
    i32 pass_yds, pass_td, pass_int, rush_yds, rush_td, rec, rec_yds, rec_td, tackles, sacks2, def_int, ff, qbh,
        punts, punt_yds, fgm, fga, sacks_allowed;
} Line;

static void read_line(u32 p, Line *s) {
    static const u8 fields[] = {8, 9, 10, 2, 3, 12, 13, 14, 18, 19, 20, 21, 107, 32, 33};
    i32 *out = &s->pass_yds;
    for (u32 i = 0; i < sizeof(fields); i++)
        out[i] = STAT(p, fields[i]);
    i32 m = 0, a = 0;
    for (u32 f = 61; f <= 68; f += 2) {
        m += STAT(p, f);
        a += STAT(p, f + 1);
    }
    s->fgm = m;
    s->fga = a;
    s->sacks_allowed = STAT(p, 110);
}

static u32 pos0(i32 v) {
    return v > 0 ? (u32)v : 0;
}

static u32 offense_points(const Line *s) {
    i32 v = s->pass_yds * 4 + s->pass_td * 400 - s->pass_int * 200 + s->rush_yds * 10 + s->rush_td * 600 +
            s->rec_yds * 10 + s->rec * 50 + s->rec_td * 600;
    return pos0(v);
}

static u32 defense_points(const Line *s) {
    return pos0(s->sacks2 * 50 + s->qbh * 20 + s->def_int * 200 + s->ff * 60 + s->tackles * 3);
}

static u32 is_offense(u32 pos) {
    return pos == P_QB || pos == P_HB || pos == P_FB || pos == P_WR || pos == P_TE;
}

static u32 is_defense(u32 pos) {
    return pos == P_CB || pos == P_FS || pos == P_SS || pos == P_OLB || pos == P_ILB || pos == P_DT || pos == P_DE;
}

static u32 win_pct1000(u32 team) {
    u32 w = WINS(team), l = LOSSES(team), t = TIES(team), g = w + l + t;
    return g ? (2 * w + t) * 500 / g : 0;
}

/* tables by position code (QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE) */
static const u16 opoy_ref[17] = {460, 0, 0, 315, 0, 0, 0, 355, 0, 310, 0, 0, 0, 0, 0, 0, 0};   /* points */
static const u16 oroy_ref[17] = {250, 0, 0, 300, 0, 0, 0, 355, 0, 300, 0, 0, 0, 0, 0, 0, 0};
static const u8 role_weight[17] = {0, 0, 0, 0, 130, 120, 120, 0, 0, 0, 80, 80, 0, 0, 0, 120, 100};
/* All-Pro: category of each position and how many men it names */
enum { A_QB, A_HB, A_FB, A_WR, A_TE, A_T, A_G, A_C, A_DE, A_DT, A_LB, A_CB, A_S, A_K, A_P, A_N };
static const u8 ap_cat[17] = {A_QB, A_K, A_P, A_WR, A_CB, A_S, A_S, A_HB, A_FB, A_TE, A_LB, A_LB, A_C, A_G, A_T, A_DT, A_DE};
static const u8 ap_size[A_N] = {1, 1, 1, 3, 1, 2, 2, 1, 2, 2, 2, 2, 2, 1, 1};
/* the retail best-at-position slots (+0x5830 + 8 * i): QB, RB/FB, WR, TE, OL, DL, LB, DB, K -> our category */
static const u8 slot_cat[9] = {A_QB, A_HB, A_WR, A_TE, A_T, A_DE, A_LB, A_CB, A_K};

typedef struct { u32 score, player, team; } Pick;
typedef struct { Pick mvp, opoy, dpoy, oroy, droy; Pick ap[A_N][3]; u32 second; } Vote;

static void consider(Pick *pick, u32 score, u32 player, u32 team) {
    if (score > pick->score) {
        pick->score = score;
        pick->player = player;
        pick->team = team;
    }
}

static void ap_insert(Pick *row, u32 n, u32 score, u32 player, u32 team) {
    for (u32 i = 0; i < n; i++) {
        if (row[i].player == player)
            return;
        if (score > row[i].score) {
            for (u32 j = n - 1; j > i; j--)
                row[j] = row[j - 1];
            row[i].score = score;
            row[i].player = player;
            row[i].team = team;
            return;
        }
    }
}

static u32 historic_offense(const Line *s) {
    return s->rush_yds >= 2000 || s->rush_yds + s->rec_yds >= 2400 || s->rush_td + s->rec_td >= 26 || s->rec_yds >= 1950;
}

static u32 mvp_base(u32 pos, const Line *s) {
    if (pos == P_QB)
        return offense_points(s);
    if (is_offense(pos))
        return historic_offense(s) ? offense_points(s) : 0;
    if (s->sacks2 < 48 && s->def_int < 14)
        return 0;
    u32 a = pos0(s->sacks2) * 1000 / 46, b = pos0(s->def_int) * 1000 / 14;
    return 28000 * (a > b ? a : b) / 1000;
}

static u32 fatigue(u32 p) {
    u32 cut = HIST_AGO(p, 96, 1) > 0 ? 15 : 0;
    for (u32 n = 2; n <= 5; n++)
        if (HIST_AGO(p, 96, n) > 0)
            cut += 8;
    return 100 - (cut > 30 ? 30 : cut);
}

static u32 offense_award(const Line *s, u32 ref, u32 pct) {
    u32 tf = pct >= 750 ? 100 : pct <= 500 ? 80 : 80 + (pct - 500) * 20 / 250;
    return ref ? offense_points(s) * 10 / ref * tf / 100 : 0;
}

/* the All-Pro score of a man at his category */
static u32 all_pro_score(u32 p, u32 pos, const Line *s, u32 pct) {
    u32 c = ap_cat[pos];
    if (c == A_QB)
        return offense_points(s);
    if (c == A_HB || c == A_WR || c == A_TE)
        return offense_award(s, opoy_ref[pos], pct);
    if (c == A_FB)
        return offense_points(s) + 1;
    if (c == A_T || c == A_G || c == A_C) {
        if (STAT(p, 0) < 12)
            return 0;
        i32 v = (i32)(OVERALL(p, 1) * 1000.0f) - 10 * s->sacks_allowed;
        return pos0(v);
    }
    if (c == A_K)
        return s->fga >= 10 ? pos0(s->fgm) * 1000 / (u32)s->fga * (u32)s->fgm : 0;
    if (c == A_P)
        return s->punts >= 40 ? pos0(s->punt_yds) * 100 / (u32)s->punts : 0;
    return defense_points(s) * role_weight[pos] / 100;
}

static void set_slot(u32 off, const Pick *p) {
    G(AWARDS + off) = p->player;
    G(AWARDS + off + 4) = p->team;
}

/* Visit every man of every club (active list, then injured reserve) for pass 0 or 1. */
static void walk(Vote *v, u32 pass, u32 mvp) {
    u32 teams = TEAM_COUNT();
    for (u32 i = 0; i < teams; i++) {
        u32 team = TEAM_AT(i);
        if (!team)
            continue;
        u32 pct = win_pct1000(team);
        u32 ir_count = i < 32 && CLUB_INDEX(team) < 32 ? IR_COUNT(team) : 0;
        for (u32 active = TEAM_FIRST(team), j = 0; active || j < ir_count;
             active ? (active = TEAM_NEXT(team, active)) : j++) {
            u32 p = active ? active : IR_GET(team, j);
            if (!p)
                continue;
            u32 pos = GB(p + 0x35);
            if (pos > P_DE)
                continue;
            if (pass == 0 && (pos == P_K || pos == P_P || pos == P_C || pos == P_G || pos == P_T))
                continue;
            Line s;
            read_line(p, &s);
            if (pass == 0) {
                u32 base = mvp_base(pos, &s);
                if (!base)
                    continue;
                u32 tf = pct <= 500 ? 40 : pct >= 750 ? 100 : 40 + (pct - 500) * 60 / 250;
                if (pct >= v->second)
                    tf += 10;
                consider(&v->mvp, base * tf * fatigue(p) / 10000, p, team);
                continue;
            }
            if (i < 32)
                ap_insert(v->ap[ap_cat[pos]], ap_size[ap_cat[pos]], all_pro_score(p, pos, &s, pct), p, team);
            u32 rookie = ((G(p + 0x24) >> 8) & 31) == 1;
            if (is_offense(pos)) {
                if (p != mvp)
                    consider(&v->opoy, offense_award(&s, opoy_ref[pos], pct), p, team);
                if (rookie)
                    consider(&v->oroy, offense_award(&s, oroy_ref[pos], pct), p, team);
            } else if (is_defense(pos)) {
                u32 d = defense_points(&s) * role_weight[pos] / 100;
                if (p != mvp)
                    consider(&v->dpoy, d, p, team);
                if (rookie)
                    consider(&v->droy, d, p, team);
            }
        }
    }
}

void awards_vote(void) {
    Vote v;
    u8 *z = (u8 *)&v;
    for (u32 i = 0; i < sizeof(v); i++)
        z[i] = 0;
    u32 saved = G(CLASS), teams = TEAM_COUNT(), best = 0, second = 0;
    CLASS_SET(0);
    for (u32 i = 0; i < teams && i < 32; i++) {               /* the second-best record: the two #1 seeds' stand-in */
        u32 team = TEAM_AT(i);
        if (!team)
            continue;
        u32 pct = win_pct1000(team);
        if (pct > best) {
            second = best;
            best = pct;
        } else if (pct > second)
            second = pct;
    }
    v.second = second ? second : 1;
    walk(&v, 0, 0);
    walk(&v, 1, v.mvp.player);
    CLASS_SET(saved);
    if (v.mvp.player)
        set_slot(0x5800, &v.mvp);
    if (v.opoy.player)
        set_slot(0x5810, &v.opoy);
    if (v.dpoy.player)
        set_slot(0x5818, &v.dpoy);
    if (v.oroy.player)
        set_slot(0x5820, &v.oroy);
    if (v.droy.player)
        set_slot(0x5828, &v.droy);
    for (u32 i = 0; i < 9; i++)
        set_slot(0x5830 + 8 * i, &v.ap[slot_cat[i]][0]);
    G(AWARDS + 0x5878) = 0;                                   /* the return man is not on this team */
    G(AWARDS + 0x587C) = 0;
    if (G(LEAGUE_MODE) != 2)
        return;
    CLASS_SET(0);
    for (u32 c = 0; c < A_N; c++)
        for (u32 k = 0; k < ap_size[c]; k++) {
            u32 in_slot = 0;
            for (u32 i = 0; i < 9; i++)
                in_slot |= k == 0 && slot_cat[i] == c;
            if (v.ap[c][k].player && !in_slot)
                HIST_SET(v.ap[c][k].player, 104, 1);
        }
    CLASS_SET(saved);
}
