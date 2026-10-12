/* Automatic current-NFL CPU playback. No libc, writable RX, or save changes. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FAST __attribute__((fastcall))
#define U(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define H(p,o) (*(u16 *)((u8 *)(p)+(o)))
#define PTR(p,o) ((u8 *)U(p,o))
#define TAG 0x13000u
#define CONTEXT 0x21a0u
#define VALID 0x314b4f43u
struct Portrait { u32 identity, legacy; u16 book, asset, photo, alternate, name[13]; };
#include "coach_ai_portraits.h"
struct State {
    u8 *context[2], *book[2], *explicit_choice[2];
    u32 fingerprint[2], attachments[2], reason[2], active[2];
};
extern struct State state;
extern const u32 career_address;
extern u8 *FAST heap_native(void);
extern u8 *FAST allocate_native(u8 *, u32);
extern void FAST free_native(u8 *);
extern void FAST stats_native(u8 *, u8 *);
extern u32 FAST portrait_native(u8 *, u8 *);
extern void FAST setup_native(u8 *, u32, u8 *);

static void zero(u8 *p, u32 n) { while (n--) *p++=0; }
static void copy(u8 *d, const u8 *s, u32 n) { while (n--) *d++=*s++; }
static int equal(const u8 *a, const u8 *b, u32 n) {
    while (n--) if (*a++!=*b++) return 0;
    return 1;
}
static u32 hash(const u8 *p, u32 n) {
    u32 h=2166136261u;
    while (n--) h=(h^*p++)*16777619u;
    return h;
}
static u32 tag_hash(const u8 *p) {
    u32 h=2166136261u,i;
    for (i=0;i<896;i++) h=(h^((i>=20 && i<24)||(i>=28 && i<32)?0:p[i]))*16777619u;
    return h;
}
static int magic(const u8 *p) { return U(p,0)==0x43414f43u && U(p,4)==0x31494148u; }
static const struct Portrait *directory(const u8 *tag) {
    u32 index=H(tag,10);
    const struct Portrait *r;
    if (H(tag,8)!=1 || index>=32) return 0;
    r=portraits+index;
    return H(tag,12)==r->asset && H(tag,14)==r->photo && U(tag,24)==r->identity
        && equal(tag+64,(const u8 *)r->name,26) ? r : 0;
}
static int same_photo(const struct Portrait *r, u32 photo) {
    return photo==r->photo || (r->alternate && photo==r->alternate);
}
/* Co1 assigns DAL/WAS to formerly unused slots. Follow the current roster
 * only for documented identities, so an int2 base never shows unused art. */
static u32 current_photo(const struct Portrait *r) {
    u8 *root=PTR(0xb72918,0), *team, *coach;
    if (root && U(root,0x18)<=128 && r->book<U(root,0x18) && PTR(root,0x1c)) {
        team=PTR(root,0x1c)+r->book*500;
        coach=PTR(team,0x14c);
        if (U(team,0x128)==0 && H(team,0x118)==r->asset && coach
            && same_photo(r,H(coach,0x40))) return H(coach,0x40);
    }
    return r->photo;
}
/* Called before native E0D90 relocates a disc PLAY resource in place, and
 * before 161E30 copies/relocates a raw saved book. The marker exists only
 * in RAM, never on disc. Hash every meaningful raw body byte before the tag;
 * the resource-manager linkage/header prefix is deliberately excluded. */
void FAST coach_validate_source(u8 *book) {
    u8 *tag=book+TAG;
    if (!magic(tag)) return;
    U(tag,28)=0;
    if (U(book,12)!=0x59414c50u || U(book,0x1083c)>(TAG-0x10840)/2
        || !directory(tag) || U(tag,20)!=tag_hash(tag)
        || U(tag,16)!=hash(book+0x30,TAG-0x30)) return;
    U(tag,28)=VALID;
}
static int career(void) {
    u8 *p=(u8 *)career_address;
    return p && U(p,0)==0x4251434du && U(p,4)==0x31303030u
        && U(0xe576a0,0)==2 && U(p,24)>=1 && U(p,24)<=6;
}
static int records(const u8 *book, const u8 *p) {
    u32 i,forms=U(book,0x34),plays=U(book,0x38);
    if (!forms || forms>50 || !plays || plays>270) return 0;
    for (i=0;i<160;i++,p+=3) if (p[0]>1 || p[1]>=forms || p[2]>=plays) return 0;
    for (i=0;i<60;i++,p+=3) if (p[0]>=forms || p[1]>=plays || p[2]>=plays) return 0;
    return H(p,2)<=H(p,0) && H(p,6)<=H(p,4) && H(p,106)<=H(p,104);
}
static void expand(u8 *out, const u8 *tag, u8 *coach) {
    u32 i,j;
    const u8 *p=tag+128;
    zero(out,CONTEXT);
    stats_native(out+0x20b8,coach);
    U(out,0x34)=H(tag,10);
    for (i=0;i<20;i++) {
        u8 *r=out+0x3c+i*128;
        *r=1;
        for (j=1;j<=8;j++,p+=3) {
            r[2+j*14]=p[0]; r[2+j*14+7]=p[1]; r[2+j*14+8]=p[2];
        }
    }
    for (i=0;i<15;i++) {
        u8 *r=out+0xa3c+i*62;
        *r=1;
        for (j=1;j<=4;j++,p+=3) copy(r+2+j*12+3,p,3);
    }
    U(out,0xdf6)=U(out,0xdfa)=1;
    copy(out+0xe90,p,8);
    copy(out+0x20b8,p+8,96);
    copy(out+0x2186,p+104,4);
}
/* Return 1 only for an eligible CPU binding. Original F6E60 then performs
 * playback initialization and book matching; no selector or RNG is replaced.
 * Diagnostic reason: 1 human, 2 mode/special, 3 team/coach, 4 book/profile,
 * 5 heap failure, 6 explicit VIP, 7 automatic. */
u32 FAST coach_prepare(u8 *team, u32 side, u8 *label) {
    u8 *book,*tag,*front,*coach,*root;
    u8 **slot=(u8 **)(0xba04b0+side*4);
    const struct Portrait *r;
    u32 mode=U(0xe5ff80,0);
    if (side>1) return 0;
    state.active[side]=0;
    if (*slot==state.context[side]) *slot=0;
    state.reason[side]=1;
    if (U(team,0x30)) return 0;
    state.reason[side]=2;
    if (mode<4 || mode>7 || U(0xe601fc,0) || career()) return 0;
    front=(u8 *)(side ? 0xb30a58 : 0xb30864);
    state.reason[side]=3;
    /* Extending CPU VIP playback beyond mode 4 is current-NFL only.
     * Special teams retain the original mode-specific explicit-VIP rules. */
    if (U(front,0x128)!=0 || (H(front,0x118)>30 && H(front,0x118)!=37)) return 0;
    if (*slot) {
        state.explicit_choice[side]=*slot;
        state.reason[side]=6;
        return 1;
    }
    state.explicit_choice[side]=0;
    coach=PTR(front,0x14c);
    state.reason[side]=3;
    if (!coach) return 0;
    book=PTR(team,0x20);
    state.reason[side]=4;
    if (!book) return 0;
    tag=book+TAG;
    if (!magic(tag) || U(tag,28)!=VALID || !(r=directory(tag))) return 0;
    state.reason[side]=3;
    if (H(front,0x118)!=r->asset || !same_photo(r,H(coach,0x40))) return 0;
    state.reason[side]=4;
    root=PTR(0xb72918,0);
    if (!root || r->book>=U(root,0x48) || label!=PTR(root,0x4c)+r->book*8
        || !records(book,tag+128)) return 0;
    if (!state.context[side]) state.context[side]=allocate_native(heap_native(),CONTEXT);
    state.reason[side]=5;
    if (!state.context[side]) return 0;
    if (state.book[side]!=book || state.fingerprint[side]!=U(tag,20)) {
        expand(state.context[side],tag,coach);
        state.book[side]=book;
        state.fingerprint[side]=U(tag,20);
    }
    *slot=state.context[side];
    state.attachments[side]++;
    state.reason[side]=7;
    state.active[side]=r->book+1;
    return 1;
}
/* Native controller reassignment has already cleared both sides and reset
 * their statistics. Keep the human native path; rebind only CPU sides. */
void coach_rebind(void) {
    u32 side;
    for (side=0;side<2;side++) {
        u8 *team=(u8 *)(0xe5fc20+side*64),*p=state.explicit_choice[side];
        state.active[side]=0;
        if (U(team,0x30)) { state.reason[side]=1; continue; }
        /* Never take a VIP now being learned by a human on the other side. */
        if (p && !(U(p,0x38)==1 && PTR(0xba04b0,(side^1)*4)==p)) U(0xba04b0,side*4)=(u32)p;
        setup_native(team,side,PTR(0xe5fe78,side*4));
    }
}
void coach_cleanup(void) {
    u32 side;
    for (side=0;side<2;side++) if (state.context[side]) {
        u8 *team=(u8 *)(0xe5fc20+side*64),*stats=PTR(team,12);
        if (PTR(0xba04b0,side*4)==state.context[side]) {
            U(0xba04b0,side*4)=0;
            U(team,0x38)=0;
        }
        /* F7A90 also publishes an interior pointer. Revoke it before free,
         * retaining an explicit VIP's newer binding if it replaced ours. */
        if (stats && PTR(stats,0)==state.context[side]+0x20b8)
            U(stats,0)=0xba04b8+side*0xd8;
        free_native(state.context[side]);
    }
    zero((u8 *)&state,sizeof state);
}
/* Only authored identities AND exact names use a coach portrait. Unknown
 * personal VIPs and ordinary NFL-coach rendering retain the native path. */
u32 FAST coach_portrait(u8 *primary, u8 *group) {
    u32 i,id;
    u8 coach[68];
    if (!primary) return 0;
    id=U(primary,0);
    for (i=0;i<32;i++) {
        const struct Portrait *r=portraits+i;
        if ((id==r->identity || id==r->legacy) && equal(primary+4,(const u8 *)r->name,26)) {
            zero(coach,sizeof coach); H(coach,0x40)=current_photo(r);
            return portrait_native(group,coach);
        }
    }
    return 0;
}
