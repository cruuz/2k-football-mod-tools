/* Franchise trades are accepted from a persistent offer board. Recheck player ownership at
 * execution, before the pool, cap, draft picks and news can move. The load hook supplies the
 * same one-owner invariant for existing signed saves. */
#include "load.h"

typedef unsigned int u32;
typedef unsigned char u8;
#define FC __attribute__((fastcall))
#define LEAGUE (*(u8 * volatile *)0x00B72918)
#define MODE (*(volatile u32 *)0x00E576A0)
#define IR_MIRROR ((u8 **)0x00E421E0)
#define RECOUNT ((void (FC *)(u8 *))0x000C3F00)
#define NATIVE_REMOVE ((u32 (FC *)(u8 *, u8 *))0x000C3EB0)

extern struct load_ir_store *const ownership_store;

static u32 count_pointer(u8 **list, u32 length, u8 *player) {
    u32 matches = 0;
    for (u32 i = 0; i < length; ++i) if (list[i] == player) ++matches;
    return matches;
}

static int club_id(const u8 *team) {
    if (!team || !LEAGUE) return -1;
    u32 delta = (u32)team - load_word(LEAGUE, 0x1C);
    return delta % 500 == 0 && delta / 500 < 32 && delta / 500 < load_word(LEAGUE,0x18)
        ? (int)(delta / 500) : -1;
}

static u32 free_count(u8 *p) {
    u32 count = load_word(LEAGUE,0x38);
    return count_pointer(*(u8 ***)(LEAGUE+0x3C), count, p);
}

static int exclusive_outgoing(u8 *source, u8 *p, u8 *block) {
    if (source[0x11C]>65 || count_pointer((u8 **)source, source[0x11C], p) != 1 || free_count(p)) return 0;
    for (u32 i=0; i<32; ++i) {
        u8 *team=load_club(i);
        if (!team) continue;
        if (team!=source && team[0x11C]<=65 && count_pointer((u8 **)team,team[0x11C],p)) return 0;
        if (load_reserve_holds(LEAGUE,block,team,p)>0) return 0;
        struct load_ir_club *ir=&ownership_store->clubs[i];
        if (ir->count>20) continue;
        for (u32 j=0; j<ir->count; ++j) if (ir->entries[j].player==p) return 0;
    }
    return 1;
}

u32 FC ownership_trade_valid(u32 *offer) {
    if (MODE!=2 || !LEAGUE) return 1;
    if (!offer) return 0;
    u8 *seen[6];
    u8 *block=load_reserve_block(LEAGUE);
    u32 entries=0;
    for (u32 side=2; side<=8; side+=6) {
        u8 *source=(u8 *)offer[side];
        if (club_id(source)<0 || offer[2]==offer[8]) return 0;
        for (u32 slot=1; slot<=3; ++slot) {
            u8 *p=(u8 *)offer[side+slot];
            if (!p) continue; /* A pick-only side is valid. */
            if (count_pointer(seen,entries,p) || !exclusive_outgoing(source,p,block)) return 0;
            seen[entries++]=p;
        }
    }
    return 1;
}

void FC ownership_decline(u32 *offer, u32 interactive, void *menu) {
    /* The weekly processor and trade menu share 15 persistent 60-byte offer slots.
     * A private proposal elsewhere may need a message, but only posted offers are cleared. */
    u32 offset=(u32)offer-0x00E3C27C;
    if (offset<0x384 && offset%60==0 && offer[0]==2)
        ((void (FC *)(u32 *,u32,u32,u32))0x002BB660)(offer,0,1,1);
    if (interactive && menu)
        ((void (FC *)(void *,const unsigned short *))0x0014E520)(menu,u"Trade canceled. A player is no longer available.");
}

/* Explicit free-agent releases can originate on IR. Preserve its remaining players' clocks,
 * flags and order and leave the owner's mirror ready for the native payroll recalculation. */
static int withdraw_ir(u32 id, u8 *player) {
    struct load_ir_club *club=&ownership_store->clubs[id];
    u32 n=0, old=club->count;
    if (old>20) return 0;
    for (u32 i=0; i<old; ++i) {
        if (club->entries[i].player==player) continue;
        if (n!=i) club->entries[n]=club->entries[i];
        ++n;
    }
    if (n==old) return 0;
    club->count=(u8)n;
    for (u32 j=n; j<old; ++j) club->entries[j]=(struct load_ir_entry){0};
    for (u32 j=0; j<5; ++j) IR_MIRROR[id*5+j]=j<n?club->entries[j].player:0;
    return 1;
}

u32 FC ownership_prepare_release(u8 *source, u8 *p) {
    if (MODE!=2 || !LEAGUE) return 1;
    int from=club_id(source);
    if (from<0) return 1; /* Display rosters use the original routine. */
    if (!p) return 0;
    u8 *block=load_reserve_block(LEAGUE);
    struct load_slots source_slots;
    u32 active_count=source[0x11C];
    /* Retail owns an invalid primary roster. Its preseason loop requires each real cut to make progress. */
    if (active_count>65) return 1;
    u32 active=count_pointer((u8 **)source,active_count,p);
    if (!load_open_slots(LEAGUE,block,source,&source_slots)) {
        /* The fixed active pointers are independent of the optional practice-squad footer. */
        source_slots.active=active_count;
        source_slots.reserve=0;
    }
    int held_elsewhere=0;
    for (u32 i=0; i<32; ++i) {
        u8 *club=load_club(i);
        if (!club || club==source) continue;
        int reserve=load_reserve_holds(LEAGUE,block,club,p);
        if (reserve>0 || (club[0x11C]<=65 && count_pointer((u8 **)club,club[0x11C],p))) held_elsewhere=1;
    }
    int detached=withdraw_ir((u32)from,p);
    u32 total=source_slots.active+source_slots.reserve;
    for (u32 i=source_slots.active; i<total;) {
        if (load_slot(&source_slots,i)!=p) { ++i; continue; }
        load_remove_slot(&source_slots,i,total,1);
        if (total>65) *(u32 *)(block+20)=load_reserve_crc(block);
        --total;
        detached=1;
    }
    if (!active && !detached) return 0; /* Already cut or no longer belongs to this club. */
    if (held_elsewhere) {
        /* An active or reserve owner at a different club keeps the player's original contract. */
        while (active) { NATIVE_REMOVE(source,p); --active; }
        RECOUNT(source);
        return 0;
    }
    while (active>1) { NATIVE_REMOVE(source,p); --active; }
    for (u32 i=0; i<32; ++i)
        if ((int)i!=from && withdraw_ir(i,p)) RECOUNT(load_club(i));
    /* Recover an old FA alias before retail adds the player and publishes his release once. */
    u32 length=load_word(LEAGUE,0x38), kept=0;
    u8 **list=*(u8 ***)(LEAGUE+0x3C);
    for (u32 i=0; i<length; ++i) if (list[i]!=p) {
        if (kept!=i) list[kept]=list[i];
        ++kept;
    }
    if (kept!=length) {
        *(u32 *)(LEAGUE+0x38)=kept;
        for (; kept<length; ++kept) list[kept]=0;
    }
    return 1;
}
