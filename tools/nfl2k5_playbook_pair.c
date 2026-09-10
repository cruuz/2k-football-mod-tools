/* USA Xbox. EXPERIMENTAL / UNWITNESSED. No libc or writable static storage.
 * Live PLAY bodies use absolute pointers; on-disc field-relative pointers are
 * converted by the retail loader before this code runs. Never publish a partial
 * merge. The caller owns and discards the private destination on any error.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FAST __attribute__((fastcall))
#define U(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define PTR(p,o) ((u8 *)U(p,o))
#define BODY 0x13390u
#define FORM 0x134u
#define AUX 0x245cu
#define PLAY 0x33fcu
#define CAT 0x993cu
#define NODE 0x9adcu
#define NAME 0x10840u
#define ENDNAME 0x13380u
#define NONE 0xffffu

static void copy(void *dst, const void *src, u32 n) {
    u8 *d=dst; const u8 *s=src;
    while (n--) *d++=*s++;
}
static void zero(void *dst, u32 n) { u8 *d=dst; while (n--) *d++=0; }
static int equal(const void *a, const void *b, u32 n) {
    const u8 *x=a, *y=b;
    while (n--) if (*x++ != *y++) return 0;
    return 1;
}
static int span(const u8 *base, const void *p, u32 n, u32 lo, u32 hi) {
    u32 off=(u32)p-(u32)base;
    return off>=lo && off<=hi && n<=hi-off;
}
static int name_length(const u8 *base, const u16 *s) {
    u32 i;
    for (i=0;i<=40;i++) {
        if (!span(base,s+i,2,NAME,ENDNAME)) return -1;
        if (!s[i]) return (int)i;
    }
    return -1;
}
static u32 put_name(u8 *out, const u8 *src, u32 pointer) {
    int n=name_length(src,(u16 *)pointer);
    u32 used=U(out,0x1083c), bytes;
    if (n<0) return 0;
    bytes=((u32)n+1)*2;
    if (used>(ENDNAME-NAME)/2 || bytes>ENDNAME-NAME-used*2) return 0;
    u8 *p=out+NAME+used*2;
    copy(p,(void *)pointer,bytes);
    U(out,0x1083c)=used+bytes/2;
    return (u32)p;
}
static int valid(const u8 *p) {
    return p && U(p,0xc)==0x59414c50 && U(p,0x34)>0 && U(p,0x34)<=50
        && U(p,0x38)>0 && U(p,0x38)<=270 && U(p,0x3c)>0 && U(p,0x3c)<=26
        && U(p,0x40)<=3500 && PTR(p,0x44)==p+FORM && PTR(p,0x48)==p+AUX
        && PTR(p,0x60)==p+PLAY && PTR(p,0x64)==p+CAT && PTR(p,0x68)==p+NODE;
}
static int defense_form(const u8 *p) { u32 t=(U(p,4)>>8)&63; return t>=4 && t<=7; }
static int defense_play(const u8 *p) { return ((U(p,4)>>6)&7)==1; }

/* Error 1: malformed source, 2: capacity, 3: cross-unit link/audible,
 * 4: unsupported substitution word. None of these publishes out.
 * Categories are shared only when their name AND complete 12-byte role/code
 * record match. Formation slot/mirror/shift bytes and all node operands survive.
 */
int pair_merge(u8 *out, const u8 *offense, const u8 *defense) {
    u16 fm[2][50], pm[2][270], cm[2][26];
    u32 side,i,j,k,n,fn=0,pn=0,cn=0,nn=0,subs=0;
    const u8 *src;
    if (!out || out==offense || out==defense || !valid(offense) || !valid(defense)) return 1;
    zero(out,BODY); copy(out,offense,0x30);
    /* This private body is never inserted into the resource manager's list. */
    U(out,0)=U(out,4)=U(out,0x18)=U(out,0x1c)=0;
    U(out,0x14)=(u32)out;
    U(out,0x44)=(u32)(out+FORM); U(out,0x48)=(u32)(out+AUX);
    U(out,0x60)=(u32)(out+PLAY); U(out,0x64)=(u32)(out+CAT); U(out,0x68)=(u32)(out+NODE);
    for (side=0;side<2;side++) {
        for (i=0;i<50;i++) fm[side][i]=NONE;
        for (i=0;i<270;i++) pm[side][i]=NONE;
        for (i=0;i<26;i++) cm[side][i]=NONE;
        src=side ? defense : offense;
        for (i=0;i<U(src,0x34);i++) {
            const u8 *f=src+FORM+i*180;
            if (((U(f,4)>>8)&63)>13) return 1;
            if (defense_form(f)!=(int)side) continue;
            if (fn==50) return 2;
            fm[side][i]=(u16)fn++;
        }
        for (i=0;i<U(src,0x38);i++) {
            if (defense_play(src+PLAY+i*96)!=(int)side) continue;
            if (pn==270) return 2;
            pm[side][i]=(u16)pn++;
        }
    }
    if (!fn || !pn) return 1;
    for (side=0;side<2;side++) {
        src=side ? defense : offense;
        /* Collect every category referenced by a retained formation. */
        for (i=0;i<U(src,0x34);i++) if (fm[side][i]!=NONE) {
            const u8 *a=src+AUX+i*80;
            u32 mask=U(a,0x4c), def=U(a,0x48)&63;
            if ((mask>>U(src,0x3c)) || (def>=U(src,0x3c) && def!=63)) return 1;
            if (def!=63) mask |= 1u<<def;
            for (j=0;j<U(src,0x3c);j++) if ((mask&(1u<<j)) && cm[side][j]==NONE) {
                const u8 *c=src+CAT+j*16;
                int len=name_length(src,(u16 *)U(c,0));
                if (len<0) return 1;
                for (k=0;k<cn;k++) {
                    u8 *d=out+CAT+k*16;
                    if (name_length(out,(u16 *)U(d,0))==len && equal(c+4,d+4,12)
                        && equal(PTR(c,0),PTR(d,0),((u32)len+1)*2)) break;
                }
                if (k==cn) {
                    if (cn==26) return 2;
                    u8 *d=out+CAT+cn++*16;
                    copy(d,c,16); U(d,0)=put_name(out,src,U(c,0));
                    if (!U(d,0)) return 2;
                }
                cm[side][j]=(u16)k;
            }
        }
        for (i=0;i<U(src,0x38);i++) if (pm[side][i]!=NONE) {
            const u8 *p=src+PLAY+i*96; u8 *d=out+PLAY+pm[side][i]*96;
            copy(d,p,96); U(d,0)=put_name(out,src,U(p,0));
            if (!U(d,0)) return 2;
            for (j=0;j<11;j++) {
                n=U(p,8+j*8)&15;
                const u8 *chain=PTR(p,12+j*8);
                if (!n) { U(d,12+j*8)=0; continue; }
                if (!span(src,chain,n*8,NODE,NODE+U(src,0x40)*8)
                    || (((u32)chain-(u32)src-NODE)&7)) return 1;
                /* Deduplicate exact bounded chains, including shared suffixes. */
                for (k=0;k+n<=nn;k++) if (equal(out+NODE+k*8,chain,n*8)) break;
                if (k+n>nn) {
                    k=nn;
                    if (n>3500-nn) return 2;
                    copy(out+NODE+nn*8,chain,n*8); nn+=n;
                }
                U(d,12+j*8)=(u32)(out+NODE+k*8);
            }
        }
        for (i=0;i<U(src,0x34);i++) if (fm[side][i]!=NONE) {
            const u8 *f=src+FORM+i*180, *a=src+AUX+i*80;
            u8 *d=out+FORM+fm[side][i]*180, *b=out+AUX+fm[side][i]*80;
            copy(d,f,180); U(d,0)=put_name(out,src,U(f,0));
            if (!U(d,0)) return 2;
            copy(b,a,80);
            for (j=0;j<36;j++) {
                u16 v=((u16 *)a)[j]; n=v&511;
                if (n==511) continue;
                if (n>=U(src,0x38) || pm[side][n]==NONE) return 3;
                ((u16 *)b)[j]=(v&~511u)|pm[side][n];
            }
            n=U(a,0x48)&63;
            U(b,0x48)=(U(a,0x48)&~63u)|(n==63 ? 63 : cm[side][n]);
            U(b,0x4c)=0;
            for (j=0;j<U(src,0x3c);j++) if (U(a,0x4c)&(1u<<j)) U(b,0x4c)|=1u<<cm[side][j];
        }
        /* Byte pairs are formation index + unchanged link slot, not play index. */
        for (i=0;i<5;i++) {
            u32 at=0x4c+side*10+i*2;
            n=src[at]; j=src[at+1];
            if (n>=U(src,0x34) || fm[side][n]==NONE || j>=36
                || ((((u16 *)(src+AUX+n*80))[j]&511)==511)) return 3;
            out[at]=(u8)fm[side][n]; out[at+1]=(u8)j;
        }
        for (i=0;i<50;i++) {
            u32 word=U(src,0x6c+i*4), type=(word>>18)&3, index=(word>>20)&1023;
            if (!word) continue;
            if (type==1) {
                if (index>=U(src,0x3c)) return 4;
                n=cm[side][index];
            } else if (type==2) {
                if (index>=U(src,0x34)) return 4;
                n=fm[side][index];
            } else return 4;
            if (n==NONE) continue;
            word=(word&~0x3ff00000u)|(n<<20);
            for (j=0;j<subs;j++) if (U(out,0x6c+j*4)==word) break;
            if (j==subs) {
                if (subs==50) return 2;
                U(out,0x6c+subs++*4)=word;
            }
        }
    }
    U(out,0x30)=put_name(out,offense,U(offense,0x30));
    if (!U(out,0x30)) return 2;
    U(out,0x34)=fn; U(out,0x38)=pn; U(out,0x3c)=cn; U(out,0x40)=nn;
    U(out,0x13380)=1;
    return 0;
}

/* All state is in the allocator's zero-initialized RW child. RO layout is
 * generated by the Python owner. Index 0 means Same as offense; 1..34 stock.
 */
struct side_state {
    u32 choice, team, original, extra, merged, queued, error;
    u8 request[36];
};
struct paired_root { u32 merged, offense, defense; };
struct workspace {
    u32 loading, started, warned;
    struct side_state side[2];
    u32 reserved[5];
    u32 read_root, spy_source; /* fixed offsets 160/164 in owned RW */
    struct paired_root roots[2];
};
extern struct workspace state;
extern const u32 ro[];
extern u32 FAST heap_native(void);
extern u32 FAST allocate_native(u32 heap, u32 size);
extern void FAST free_native(u32 ptr);
extern void FAST unload_native(u32 name);
extern void FAST notice_native(u32 context, u32 text);
extern u32 FAST queue_native(u32 name,u32 file,void *request,u32 heap,u32 callback,u32 user);
extern void load_callback_native(void);
extern void FAST home_loaded(u32 root);
extern void FAST away_loaded(u32 root);

/* Publication contains only complete private merges. The ordinal map is
 * owned by the same heap allocation, immediately after its fixed PLAY body.
 * Readers never search the resource manager or wait for a pending load. */
u32 FAST pair_read_root(u32 field) {
    for (u32 s=0;s<2;s++) {
        u32 base=state.roots[s].merged;
        if (base && field-base>=PLAY+8 && field-base<PLAY+270*96)
            return base;
    }
    return 0;
}
unsigned long long FAST pair_spy_source(u32 field) {
    for (u32 s=0;s<2;s++) {
        struct paired_root *r=&state.roots[s];
        u32 base=r->merged, offset=field-base-PLAY-8;
        if (!base || offset>=270*96-8) continue;
        u32 pi=offset/96, slot=(offset%96)/8;
        if ((offset&7) || slot>=11 || pi>=U(base,0x38)) return 0;
        u32 source=((u16 *)(base+BODY))[pi];
        u32 original=(source&0x8000) ? r->defense : r->offense;
        pi=source&0x7fff;
        if (!original || pi>=U(original,0x38)) return 0;
        u32 from=original+PLAY+pi*96+8+slot*8;
        /* A post-bind change to the live fallback must not borrow intent
         * from the original. Both scripts remain exact bounded two-node rows. */
        if (U(from,0)!=U(field,0) || (U(field,0)&15)!=2
            || !span((u8 *)base,PTR(field,4),16,NODE,NODE+U(base,0x40)*8)
            || !span((u8 *)original,PTR(from,4),16,NODE,NODE+U(original,0x40)*8)
            || !equal(PTR(from,4),PTR(field,4),16)) return 0;
        return ((unsigned long long)original<<32)|from;
    }
    return 0;
}

static u32 team(u32 s) { return *(u32 *)(0xe5fe68+s*4); }
static u32 *root(u32 s) { return (u32 *)(0xe5fe80+s*4); }
static void notice(u32 index) { notice_native(0,ro[index]); }
/* 77c50 initializes exhibition to 4. c73b0 selects 5 for Season and
 * 6/7 for Franchise schedule games. 0..3 are practice, 8 is a drill. */
static int ordinary_game(void) { return *(u32 *)0xe5ff80-4u <= 3u; }
static int stock(u32 s) {
    u32 entry=*(u32 *)(0xe5fe78+s*4);
    if (!entry) { if (!team(s)) return 0; entry=U(team(s),0x110); }
    if (!entry) return 0;
    const u16 *code=(u16 *)U(entry,4);
    if (!code) return 0;
    /* Stock codes are at most 3 ASCII characters; compare the filename prefix. */
    for (u32 i=0;i<34;i++) {
        const u16 *file=(u16 *)ro[35+i]; u32 j=0;
        while (j<3 && code[j] && code[j]==file[j]) j++;
        if (j && !code[j] && file[j]=='-') return 1;
    }
    return 0;
}
static u32 choice(u32 s) {
    struct side_state *v=&state.side[s];
    if (v->choice>34 || (v->choice && v->team!=team(s))) v->choice=0;
    return v->choice;
}
static void change(u32 s, int delta) {
    if (state.started) return;
    if (!ordinary_game()) { notice(73); return; }
    struct side_state *v=&state.side[s]; u32 c=choice(s);
    v->choice=(c+(delta<0 ? 34 : 1))%35; v->team=team(s);
    if (v->choice && !state.warned) { state.warned=1; notice(72); }
}
u32 get_home(void) { return choice(0); }
u32 get_away(void) { return choice(1); }
u32 text_home(void) { return ro[choice(0)]; }
u32 text_away(void) { return ro[choice(1)]; }
void next_home(void) { change(0,1); }
void prev_home(void) { change(0,-1); }
void next_away(void) { change(1,1); }
void prev_away(void) { change(1,-1); }
u32 visible(void) { return ordinary_game(); }
/* Native row callback ABI (2c01c0): ECX screen, EDX runtime row; +8 is
 * the hidden flag. The callback does not return a visibility boolean. */
void FAST visibility(u32 screen, u8 *row) {
    (void)screen;
    U(row,8)=!ordinary_game() || state.started;
}
u32 maximum(void) { return 34; }
u32 minimum(void) { return 0; }
u32 width(void) { return 160; }

void pair_begin(void) {
    if (state.started) return; /* never overwrite live request structs */
    if (!ordinary_game() || (!choice(0) && !choice(1))) return;
    if (!stock(0) || !stock(1)) {
        state.side[0].choice=state.side[1].choice=0; notice(74); return;
    }
    state.started=state.loading=1;
}
void FAST home_loaded(u32 r) { if (state.loading) state.side[0].extra=r; }
void FAST away_loaded(u32 r) { if (state.loading) state.side[1].extra=r; }
void pair_queue(void) {
    if (!state.loading) return;
    for (u32 s=0;s<2;s++) {
        struct side_state *v=&state.side[s];
        if (!v->choice || v->queued) continue;
        v->queued=1;
        if (!queue_native(ro[69+s],ro[34+v->choice],v->request,heap_native(),
                          (u32)load_callback_native,(u32)(s ? away_loaded : home_loaded))) v->error=5;
    }
}
void pair_bind(void) {
    if (!state.loading) return;
    for (u32 s=0;s<2;s++) {
        struct side_state *v=&state.side[s];
        if (!v->choice) continue;
        v->original=*root(s);
        if (!v->original || !v->extra || v->error) v->error=5;
        else {
            u32 dest=allocate_native(heap_native(),BODY+270*2);
            if (!dest) v->error=6;
            else {
                v->error=pair_merge((u8 *)dest,(u8 *)v->original,(u8 *)v->extra);
                if (v->error) free_native(dest);
                else {
                    u32 n=0;
                    for (u32 unit=0;unit<2;unit++) {
                        u32 src=unit ? v->extra : v->original;
                        for (u32 pi=0;pi<U(src,0x38);pi++)
                            if (defense_play((u8 *)(src+PLAY+pi*96))==(int)unit)
                                ((u16 *)(dest+BODY))[n++]=(u16)(pi|(unit<<15));
                    }
                    v->merged=dest; *root(s)=dest;
                    state.roots[s].offense=v->original;
                    state.roots[s].defense=v->extra;
                    state.roots[s].merged=dest;
                    state.read_root=(u32)pair_read_root;
                    state.spy_source=(u32)pair_spy_source;
                }
            }
        }
        if (v->error) notice(75+s);
    }
    state.loading=0;
}
void pair_cleanup(void) {
    state.read_root=state.spy_source=0; /* revoke before free or callbacks */
    if (!state.started) { zero(&state,sizeof(state)); return; }
    state.loading=0; /* callbacks during cancellation must not publish */
    for (u32 s=0;s<2;s++) {
        struct side_state *v=&state.side[s];
        if (v->merged) {
            if (*root(s)==v->merged) *root(s)=v->original;
            u32 *bound=(u32 *)(0xe5fc40+s*0x40);
            if (*bound==v->merged) *bound=v->original;
            free_native(v->merged); v->merged=0;
        }
        if (v->queued) unload_native(ro[69+s]);
    }
    zero(&state,sizeof(state));
}
