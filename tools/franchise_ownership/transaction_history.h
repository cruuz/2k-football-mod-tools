/* The loader has resolved every player and club in the native 600-row ring at 0x2D0F3D,
 * before the post-IR load callback at 0x2D0F70. Serialized IDs cover only primary players. */
struct load_event { load_u32 packed; load_u8 *player, *club; };
#define LOAD_EVENTS ((const struct load_event *)0x00E3F070)
#define LOAD_EVENT_COUNT 600u
#define LOAD_LAST 0x80000000u

static load_u32 load_previous(load_u32 slot) { return slot ? slot - 1 : LOAD_EVENT_COUNT - 1; }

static __attribute__((noinline)) int load_traded_to(load_u8 *league, load_u8 *player, load_u8 *club,
                                                   load_u32 slot, load_u32 cursor) {
    /* 0x2BC818..0x2BC8BB writes up to three players and three picks on each side.
     * Each row names the outgoing club. Only the last row is marked. */
    load_u8 *outgoing = LOAD_EVENTS[slot].club;
    /* 0x2D04F0/0xC4C50 resolved this pointer to a native team or null. Exclude display clubs. */
    if (outgoing == club || (load_u32)outgoing - load_word(league, 0x1C) >= 32u * 500) return 0;
    int matched = 0, other_side = 0, seen_player = 0;
    load_u8 counts[2][2] = {{0}};
    for (load_u32 n = 1; !(LOAD_EVENTS[slot].packed & LOAD_LAST); ++n) {
        if (n >= 12) return 0;
        if (++slot == LOAD_EVENT_COUNT) slot = 0;
        if (slot == cursor || (LOAD_EVENTS[slot].packed & 31) != 7) return 0;
    }
    for (load_u32 n = 0; n < 12; ++n) {
        const struct load_event *event = &LOAD_EVENTS[slot];
        load_u32 args = (event->packed & ~LOAD_LAST) >> 5;
        if (event->player) {
            if (args) return 0; /* 0x2D0540 already resolved and bounded the primary player index. */
            seen_player = 1;
            if (event->player == player) {
                if (matched++) return 0;
            }
        } else if (seen_player || !(args & 63) || (args & ~0xF003Fu)) {
            /* The writer emits all picks after all players. A broken player reference is not a pick. */
            return 0;
        }
        if (event->club == club) other_side = 1;
        else if (event->club != outgoing) return 0;
        if (++counts[event->club == club][event->player == 0] > 3) return 0;
        if (slot == cursor) return 0; /* The ring may have overwritten the start of the exchange. */
        slot = load_previous(slot);
        load_u32 previous = LOAD_EVENTS[slot].packed;
        if ((previous & 31) != 7 || (previous & LOAD_LAST))
            return matched && other_side;
    }
    return 0;
}

static __attribute__((noinline)) int load_acquired_by(load_u8 *league, load_u8 *player, load_u8 *club) {
    load_u32 cursor = *(const load_u32 *)0x00E3F06C, slot = cursor;
    if (cursor >= LOAD_EVENT_COUNT) return 0;
    for (load_u32 n = 0; n < LOAD_EVENT_COUNT; ++n) {
        slot = load_previous(slot);
        const struct load_event *event = &LOAD_EVENTS[slot];
        if (event->player != player) continue;
        switch (event->packed & 31) {
            case 1: case 4: /* Signed or drafted by the club named in this single row. */
                return (event->packed & LOAD_LAST) && event->club == club;
            case 7:
                return load_traded_to(league, player, club, slot, cursor);
            case 3: case 5: case 6: case 10: case 11: case 12:
                break; /* These retail events do not move a player between clubs. */
            default:
                /* Retired, waived, released, or a cleared/unknown same-player event. Its old
                 * pointer cannot establish custody, and an earlier acquisition may be obsolete. */
                return 0;
        }
    }
    return 0;
}
