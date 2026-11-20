/* Preserve each club's quarterback order before its medical depth sort. When the starter has healed,
 * temporarily restore eligible ranks for the native match copy, then restore the franchise chart. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define B(p) (*(volatile u8 *)(p))
#define W(p) (*(volatile u16 *)(p))
#define D(p) (*(volatile u32 *)(p))
#define MASTER 0xb72918u
#define YEAR 0xe576b8u
#define WEEK 0xe576b4u
#define ACTIVE_STAGE 0xe576a4u
#define USER_FLAG 0xe5775cu
#define AUTO_DEPTH 0xe60140u
#define MODE 0xe5ff80u
#define QB_MAX 8
#define RANK_MASK (7u << 10)
#define INJURED 0x80000000u
#define WEEKS_MASK (255u << 22)

struct quarterback {
    u32 player;
    u8 chart_rank;
    u8 locks;
};
struct room {
    u32 club, root, year, week, count;
    struct quarterback order[QB_MAX]; /* index is the native rating/lock rank BEFORE its medical partition */
};
struct restoration {
    u32 p;
    u8 rank;
};
struct room captures[32];
struct restoration undo_entries[QB_MAX * 2];
u32 undo_count;
u32 capture_count, eligible_count, corrected_teams, corrected_rank_writes;

static u32 rank(u32 player) {
    return (W(player + 40) >> 10) & 7;
}

static void set_rank(u32 player, u32 desired) {
    W(player + 40) = (W(player + 40) & ~RANK_MASK) | (desired << 10);
}

static int fully_healthy(u32 player) {
    return !(D(player + 32) & (INJURED | WEEKS_MASK)) && !(D(player + 36) & 0x70000000u);
}

static int managed(u32 index) {
    return !D(USER_FLAG + 4 * index) || D(AUTO_DEPTH);
}

void before_partition(u32 index, u32 team) {
    if (index >= 32) return;
    struct room *room = &captures[index];
    room->count = 0;
    u32 root = D(MASTER);
    if (!root || team != D(root + 28) + 500 * index || !managed(index)) return;
    u32 slots = B(team + 0x11c), ranks = 0, count = 0;
    if (slots > 65) return;
    for (u32 i = 0; i < slots; i++) {
        u32 player = D(team + 4 * i);
        if (!player || B(player + 53) != 0) continue;
        u32 position = rank(player);
        if (ranks & (1u << position)) return;
        ranks |= 1u << position;
        count++;
        room->order[position].player = player;
    }
    if (count < 2 || count > QB_MAX || ranks != (1u << count) - 1) return;
    u32 starter = room->order[0].player, medical = D(starter + 32);
    if (!(medical & INJURED) || ((medical >> 22) & 255) != 1) return;
    /* Capture only the starter's last recovery week, with a healthy backup for every other rank. */
    for (u32 i = 1; i < count; i++) {
        if (!fully_healthy(room->order[i].player)) return;
    }
    room->club = team;
    room->root = root;
    room->year = D(YEAR);
    room->week = D(WEEK);
    room->count = count;
    capture_count++;
}

void after_partition(u32 index, u32 team) {
    if (index >= 32) return;
    struct room *room = &captures[index];
    if (!room->count || room->club != team) return;
    u32 mask = 0;
    for (u32 i = 0; i < room->count; i++) {
        struct quarterback *qb = &room->order[i];
        qb->chart_rank = rank(qb->player);
        qb->locks = B(qb->player + 82);
        mask |= 1u << qb->chart_rank;
    }
    if (!room->order[0].chart_rank || mask != (1u << room->count) - 1) {
        room->count = 0;
        return;
    }
    eligible_count++;
}

/* context.S calls this symbol directly with the club pointer in EAX. */
static __attribute__((noinline, regparm(1))) void prepare(u32 team) {
    u32 root = D(MASTER);
    if (!root) return;
    u32 base = D(root + 28);
    if (team < base || team - base >= 16000 || (team - base) % 500) return;
    u32 index = (team - base) / 500;
    struct room *room = &captures[index];
    if (!room->count || room->root != root || room->club != team ||
        room->year != D(YEAR) || room->week != D(WEEK) || !managed(index)) return;
    u32 slots = B(team + 0x11c), seen = 0;
    if (slots > 65) return;
    for (u32 i = 0; i < slots; i++) {
        u32 player = D(team + 4 * i);
        if (!player || B(player + 53) != 0) continue;
        u32 j = 0;
        for (; j < room->count; j++) {
            if (room->order[j].player == player) break;
        }
        if (j == room->count || (seen & (1u << j))) return;
        seen |= 1u << j;
        struct quarterback *qb = &room->order[j];
        if (!fully_healthy(player) || qb->chart_rank != rank(player) || qb->locks != B(player + 82)) return;
        if (qb->chart_rank != j && (qb->locks & 1)) return;
    }
    if (seen != (1u << room->count) - 1) return;
    for (u32 i = 0; i < room->count; i++) {
        struct quarterback *qb = &room->order[i];
        if (qb->chart_rank == i) continue;
        undo_entries[undo_count].p = qb->player;
        undo_entries[undo_count++].rank = qb->chart_rank;
        set_rank(qb->player, i);
        corrected_rank_writes++;
    }
    corrected_teams++;
}

void prepare_match(u32 home, u32 away, const u32 *sp) {
    undo_count = 0;
    /* Only a full fixture on the scheduled grid passes this call chain. Gamecast has its own entry in context.S. */
    if (sp[7] != 0x10b9e0 || sp[13] != 0xc7b58 || D(MODE) != 4) return;
    u32 stage = D(ACTIVE_STAGE);
    if (stage != 8 && stage != 9) return;
    if (home == away) return;
    prepare(home);
    prepare(away);
}

void restore_match(void) {
    while (undo_count) {
        struct restoration *entry = &undo_entries[--undo_count];
        set_rank(entry->p, entry->rank);
    }
}
