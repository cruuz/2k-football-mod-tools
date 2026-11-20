/* Cold-load reconciliation for franchise player ownership. Source order breaks ties between
 * equal owners. The 32 franchise clubs rank above free agency and injured reserve; display
 * teams legitimately alias the same players. Keep player records, depth locks and contracts intact. */
typedef unsigned char load_u8;
typedef unsigned int load_u32;

struct load_ir_entry { load_u8 *player; short base; load_u8 flags, how; };
struct load_ir_club { load_u8 count, returns, pad[2]; struct load_ir_entry entries[20]; };
struct load_ir_store { load_u32 header[16]; struct load_ir_club clubs[32]; };
struct load_window {
    load_u32 base, size;
    load_u32 seen[128]; /* 4,096 records per pass. Larger or secondary pools reuse the scratch. */
};

static inline load_u32 load_word(const void *base, load_u32 offset) {
    return *(const load_u32 *)((const load_u8 *)base + offset);
}

static load_u8 *load_club(load_u32 index) {
    return ((load_u8 *(__attribute__((fastcall)) *)(load_u32))0x000C4C50)(index);
}

static int load_already_owned(struct load_window *window, load_u8 *player) {
    load_u32 delta = (load_u32)player - window->base;
    if (delta >= window->size || delta % 84) return 0;
    load_u32 id = delta / 84;
    load_u32 mask = 1u << (id & 31);
    load_u32 *word = &window->seen[id >> 5];
    int claimed = (*word & mask) != 0;
    *word |= mask;
    return claimed;
}

#define ROSTER_RESERVE_CRC load_reserve_crc
#include "../roster_arena/reserve_crc.h"
#undef ROSTER_RESERVE_CRC

static load_u8 *load_reserve_block(load_u8 *league) {
    load_u32 len = *(volatile load_u32 *)0x00B72808;
    if (len != 0x92000 && len != 0xB0000 && len != 0xCA000) return 0;
    load_u8 *b = league + len - 0x400;
    if (load_word(b, 0) != 0x52354B32 || load_word(b, 4) != 0x00325653 ||
        load_word(b, 8) != 0x00200002 || load_word(b, 12) != 0x00020005 ||
        (load_word(b, 28) & ~0x102u) || load_word(b, 20) != load_reserve_crc(b)) return 0;
    return b;
}

struct load_slots {
    load_u8 *club, *pool;
    unsigned short *overflow;
    load_u32 active, reserve;
};

static load_u8 *load_slot(const struct load_slots *s, load_u32 i) {
    if (i < 65) return ((load_u8 **)s->club)[i];
    unsigned int id = s->overflow[i - 65];
    return id == 0xFFFF ? 0 : s->pool + 84u * id;
}

static void load_write_slot(struct load_slots *s, load_u32 i, load_u8 *player) {
    if (i < 65) ((load_u8 **)s->club)[i] = player;
    else s->overflow[i - 65] = player ? (unsigned short)(((load_u32)player - (load_u32)s->pool)/84u) : 0xFFFF;
}

static int load_open_slots(load_u8 *league, load_u8 *block, load_u8 *club, struct load_slots *s) {
    load_u32 n = club[0x11C], r = club[0x1F2], capacity = 65, limit = 12;
    s->club = club;
    s->pool = *(load_u8 **)(league + 4);
    s->overflow = 0;
    if (club[0x19B] == 2) {
        load_u32 d = (load_u32)club - load_word(league, 0x1C), ord = d / 500;
        if (!block || d % 500 || ord >= 32 || ord >= load_word(league, 0x18)) return 0;
        s->overflow = (unsigned short *)(block + 32 + ord * 10);
        if (load_word(block, 28) & 0x100) limit = 16 + ((load_word(block, 24) >> ord) & 1u);
        for (load_u32 i = 0; i < 5; ++i)
            if (s->overflow[i] != 0xFFFF && s->overflow[i] >= load_word(league, 0)) return 0;
        capacity = 70;
    }
    if (club[0x19B] || r || club[0x1F3]) {
        if ((club[0x19B] != 1 && club[0x19B] != 2) || club[0x1F3] != 0xA5) return 0;
    }
    if (n > 65 || r > limit || n+r > capacity) return 0;
    if (club[0x19B]) {
        for (load_u32 i = n; i < capacity; ++i)
            if ((load_slot(s, i) != 0) != (i < n + r)) return 0;
    }
    s->active = n; s->reserve = r;
    return 1;
}

/* Transaction preflight can distinguish an invalid protected block from an empty practice squad. */
static __attribute__((unused)) int load_reserve_holds(void *root, void *block, void *team, void *player) {
    load_u8 *league = root, *club = team;
    struct load_slots slots;
    if (!league || !club || !load_open_slots(league, block, club, &slots)) return -1;
    for (load_u32 i = slots.active; i < slots.active + slots.reserve; ++i)
        if (load_slot(&slots, i) == player) return 1;
    return 0;
}

static void load_remove_slot(struct load_slots *s, load_u32 at, load_u32 end, int reserve) {
    load_u8 *club = s->club;
    load_u8 **players = (load_u8 **)club;
    if (reserve) {
        --club[0x1F2];
    } else {
        load_u32 kept = 0;
        while (kept < at && players[kept] != players[at]) ++kept;
        for (load_u32 role = 0x194; role < 0x19A; ++role) {
            load_u32 slot = club[role];
            if (slot == at) club[role] = kept == at ? 0xFF : (load_u8)kept;
            else if (slot > at && slot < club[0x11C]) --club[role];
        }
        --club[0x11C];
    }
    for (; at + 1 < end; ++at) load_write_slot(s, at, load_slot(s, at+1));
    load_write_slot(s, at, 0);
}

static int load_rosters(struct load_window *window, load_u8 *league, load_u8 *block, int reserve) {
    int overflow_changed = 0;
    for (load_u32 club_id = 0; club_id < 32; ++club_id) {
        load_u8 *club = load_club(club_id);
        struct load_slots slots;
        if (!club || !load_open_slots(league, block, club, &slots)) continue;
        load_u32 active = slots.active, total = active + slots.reserve;
        load_u32 slot = reserve ? active : 0, end = reserve ? total : active;
        while (slot < end) {
            if (load_already_owned(window, load_slot(&slots, slot))) {
                if (total > 65) overflow_changed = 1;
                load_remove_slot(&slots, slot, total, reserve);
                --total;
                --end;
            } else {
                ++slot;
            }
        }
    }
    return overflow_changed;
}

static void load_free_agents(struct load_window *window, load_u8 *league) {
    load_u32 original = load_word(league, 0x38), count = 0;
    load_u8 **players = *(load_u8 ***)(league + 0x3C);
    if (!players || original > load_word(league, 0) + load_word(league, 8)) return;
    for (load_u32 i = 0; i < original; ++i)
        if (!load_already_owned(window, players[i])) players[count++] = players[i];
    *(load_u32 *)(league + 0x38) = count;
    for (; count < original; ++count) players[count] = 0;
}

static void load_injured_reserve(struct load_window *window, struct load_ir_store *ir) {
    load_u8 **legacy = (load_u8 **)0x00E421E0;
    for (load_u32 club_id = 0; club_id < 32; ++club_id) {
        struct load_ir_club *club = &ir->clubs[club_id];
        load_u32 original = club->count, n = 0;
        for (load_u32 i = 0; i < original; ++i) {
            if (!load_already_owned(window, club->entries[i].player)) {
                if (i != n) club->entries[n] = club->entries[i];
                ++n;
            }
        }
        if (n == original) continue;
        club->count = (load_u8)n;
        ir->header[15] += original - n; /* original IR owner's dropped counter */
        for (load_u32 i = n; i < original; ++i) club->entries[i] = (struct load_ir_entry){0};
        for (load_u32 i = 0; i < 5; ++i)
            legacy[club_id * 5 + i] = i < n ? club->entries[i].player : 0;
    }
}

/* Registered at ir_config+12. The original loader has decoded both formats, including IR
 * games and return budgets; its payroll recount still follows this callback. No save-format change. */
__attribute__((fastcall)) void ownership_repair_loaded(void *root, void *store) {
    load_u8 *league = root;
    if (!league || !store) return;
    load_u8 *block = load_reserve_block(league);
    int overflow_changed = 0;
    /* Preflight all tagged rosters before changing anything. A corrupt v2 checksum must
     * never make a valid overflow tail look empty or get re-signed by this repair. */
    for (load_u32 club_id = 0; club_id < 32; ++club_id) {
        load_u8 *club = load_club(club_id);
        struct load_slots slots;
        if (club && !load_open_slots(league, block, club, &slots)) return;
    }
    for (load_u32 pool = 0; pool <= 8; pool += 8) {
        load_u32 count = load_word(league, pool), base = load_word(league, pool + 4);
        if (!base || count > 0xFFFF) continue;
        for (load_u32 offset = 0; offset < count; offset += 4096u) {
            load_u32 length = count - offset;
            struct load_window window;
            window.base = base + offset * 84u;
            window.size = (length < 4096u ? length : 4096u) * 84u;
            for (load_u32 i = 0; i < 128; ++i) window.seen[i] = 0;
            overflow_changed |= load_rosters(&window, league, block, 0);
            overflow_changed |= load_rosters(&window, league, block, 1);
            load_free_agents(&window, league);
            load_injured_reserve(&window, store);
        }
    }
    if (overflow_changed) *(load_u32 *)(block+20) = load_reserve_crc(block);
}
