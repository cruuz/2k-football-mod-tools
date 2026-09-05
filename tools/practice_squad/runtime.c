/* Original freestanding i386 implementation. Rebuild with build_runtime.py.
 * Reserve pointers occupy existing physical slots and use RETAIL relocation. No .text variable, new heap allocation, or save-size change.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed int i32;
#define FC __attribute__((fastcall))
#define NOINLINE __attribute__((noinline))
#define U32(p,o) (*(u32 *)((u8 *)(p)+(o)))
#define U16(p,o) (*(u16 *)((u8 *)(p)+(o)))
#define B(p,o) (*((u8 *)(p)+(o)))
#define ROOT (*(u8 **)0xB72918)
#define EMPTY 0xffffffffU
#define ACTIVE 0x11c
#define FN1(a) ((u32 (FC *)(u8 *))(a))
#define FN2(a) ((u32 (FC *)(u8 *,u8 *))(a))
#define COPY(a) ((void (FC *)(u8 *,u32 *,u32 *))(a))
extern u32 FC retail_fa_add(u8 *, u8 *);
extern void FC retail_clear(u8 *);
extern void FC retail_rollover(void);
extern u32 FC retire_player(u8 *);

static NOINLINE u32 length(const u16 *s) { u32 n=0; if(s) while(s[n]) ++n; return n; }
static NOINLINE u32 index_of(u8 *p) {
    u8 *r=ROOT; u32 n=(u32)p-U32(r,4);
    if(n%84 || n/84>=U32(r,0)) return EMPTY;
    return n/84;
}
/* Only three padding bytes are owned: +19B, +1F2, +1F3. Team +19C
 * is future cap accounting; +1AA..+1F1 is live team statistics. */
#define RSV_VERSION 0x19b
#define RSV_COUNT 0x1f2
#define RSV_MAGIC 0x1f3
static NOINLINE int reserve_count(u8 *t) {
    u32 i,n=B(t,ACTIVE),r=B(t,RSV_COUNT);
    if(n>65) return -1;
    if(!B(t,RSV_VERSION) && !r && !B(t,RSV_MAGIC)) r=0;
    else if(B(t,RSV_VERSION)!=1 || B(t,RSV_MAGIC)!=0xa5 || r>12) return -1;
    if(n+r>65) return -1;
    for(i=n+r;i<65;i++) if(U32(t,4*i)) return -1;
    for(i=n;i<n+r;i++) if(!U32(t,4*i)) return -1;
    return (int)r;
}
static NOINLINE void set_count(u8 *t,u32 n) {
    B(t,RSV_VERSION)=1; B(t,RSV_MAGIC)=0xa5; B(t,RSV_COUNT)=n;
}
static NOINLINE u8 *owner(u32 id) {
    u8 *r=ROOT,*t=(u8 *)U32(r,0x1c); u32 i,j; int n;
    if(!r || U32(r,0x18)>128) return (u8 *)1;
    for(i=0;i<U32(r,0x18);i++,t+=500) {
        n=reserve_count(t);
        if(n<0) return (u8 *)1;
        for(j=0;j<(u32)n;j++) if(index_of((u8 *)U32(t,4*(B(t,ACTIVE)+j)))==id) return t;
    }
    return 0;
}
static NOINLINE void erase(u8 *t,u32 at) {
    u32 n=(u32)reserve_count(t),i=at+B(t,ACTIVE),end=n+B(t,ACTIVE)-1;
    for(;i<end;i++) U32(t,4*i)=U32(t,4*(i+1));
    U32(t,4*end)=0; set_count(t,n-1);
}
/* Insertion is preflighted before the first store. Promotion rotates a player
 * already present in the physical array, so it also works at 65 total players.
 * Its caller decrements reserve ownership only after insertion returns success. */
static NOINLINE u32 insert(u8 *t,u8 *p,int promote) {
    int r=reserve_count(t); u32 a=B(t,ACTIVE),i;
    if(r<0 || a>=65) return 0;
    if(promote) {
        for(i=a;i<a+(u32)r;i++) if(U32(t,4*i)==(u32)p) break;
        if(i==a+(u32)r) return 0;
    } else { i=a+(u32)r; if(i>=65) return 0; }
    while(i>a) { U32(t,4*i)=U32(t,4*(i-1)); --i; }
    U32(t,4*a)=(u32)p; ++B(t,ACTIVE); return 1;
}
static NOINLINE int listed(u8 *p,u8 *except) {
    u8 *r=ROOT,*t=(u8 *)U32(r,0x1c); u32 i,j;
    /* All-star aliases are display teams, not franchise ownership. */
    for(i=0;i<U32(r,0x18);i++,t+=500) if(t!=except &&
        (i<32 || U32(t,0x128)==2 || U32(t,0x128)==4))
        for(j=0;j<B(t,ACTIVE);j++) if(U32(t,4*j)==(u32)p) return 1;
    for(i=0;i<U32(r,0x38);i++) if(((u32 *)U32(r,0x3c))[i]==(u32)p) return 1;
    /* Franchise IR remains a separate owner. */
    if(U32((u8 *)0xE576A0,0))
        for(i=0;i<160;i++) if(((u32 *)0xE421E0)[i]==(u32)p) return 1;
    return 0;
}

u32 FC ps_append(u8 *t,u8 *p) {
    if(!t || !p) return 0;
    if(U32((u8 *)0xE576A0,0) && U32((u8 *)0xE576A4,0)>=8 && B(t,ACTIVE)>=53) return 0;
    if(owner(index_of(p))) return 0;
    return insert(t,p,0);
}
u32 FC ps_fa_add(u8 *list,u8 *p) {
    if(owner(index_of(p))) return 0;
    return retail_fa_add(list,p);
}
/* Rollover returns IR to the off-season roster. Keep the IR owner if all
 * 65 physical slots are occupied; the retail caller otherwise drops it. */
u32 FC ps_ir_append(u8 *t,u8 *p) {
    if(!t || !p || owner(index_of(p))) return 0;
    return insert(t,p,0);
}
/* Preflight callers which remove an old owner before ignoring append's return.
 * The off-season limit includes hidden slots; regular season remains 53. */
u32 FC ps_limit(u8 *t) {
    int r=reserve_count(t); u32 limit;
    if(r<0) return 0;
    limit=65-(u32)r;
    if(U32((u8 *)0xE576A0,0) && U32((u8 *)0xE576A4,0)>=8 && limit>53) limit=53;
    return limit;
}
u32 FC ps_room(u8 *t) { return t && B(t,ACTIVE)<ps_limit(t); }
u32 FC ps_trade_room(u32 *offer) {
    u8 *a=(u8 *)offer[2],*b=(u8 *)offer[8];
    u32 i,na,nb,la,lb;
    if(!a || !b || a==b) return 0;
    na=B(a,ACTIVE); nb=B(b,ACTIVE); la=ps_limit(a); lb=ps_limit(b);
    for(i=0;i<3;i++) {
        if(offer[3+i]) { if(!na || ++nb>lb || owner(index_of((u8 *)offer[3+i]))) return 0; --na; }
        if(offer[9+i]) { if(!nb || ++na>la || owner(index_of((u8 *)offer[9+i]))) return 0; --nb; }
    }
    return 1;
}
u32 FC ps_demote(u8 *t,u8 *p) {
    u32 i,id=index_of(p),matches=0; int r=reserve_count(t);
    if(id==EMPTY || r<0 || r==12 || owner(id) || listed(p,t)) return 0;
    for(i=0;i<B(t,ACTIVE);i++) if(U32(t,4*i)==(u32)p) ++matches;
    if(matches!=1 || !FN2(0xC3EB0)(t,p)) return 0;
    U32(t,4*(B(t,ACTIVE)+r))=(u32)p; set_count(t,r+1);
    B(p,8)=(B(p,8)|4)&~0x10;
    FN1(0xC3F00)(t); return 1;
}
u32 FC ps_promote(u8 *t,u8 *p) {
    u32 id=index_of(p); int r=reserve_count(t);
    if(r<=0 || B(t,ACTIVE)>=53 || owner(id)!=t || listed(p,t)) return 0;
    if(!insert(t,p,1)) return 0;
    set_count(t,r-1); FN1(0xC3F00)(t); return 1;
}
void FC ps_cut(u8 *t,u8 *p,u32 fa,u32 contract) {
    if(U32((u8 *)0xE576A4,0)==7 && B(t,ACTIVE)>53 && ps_demote(t,p)) return;
    ((void (FC *)(u8 *,u8 *,u32,u32))0x2BD900)(t,p,fa,contract);
}
void FC ps_clear(u8 *p) {
    u32 id=index_of(p); u8 *t;
    while((t=owner(id)) && t!=(u8 *)1) {
        u32 i,n=(u32)reserve_count(t);
        for(i=0;i<n;i++) if(U32(t,4*(B(t,ACTIVE)+i))==(u32)p) break;
        erase(t,i);
    }
    retail_clear(p);
}
void FC ps_rollover(void) {
    u8 *r=ROOT,*t=(u8 *)U32(r,0x1c); u32 i,j; int n;
    for(i=0;i<U32(r,0x18);i++,t+=500) {
        n=reserve_count(t);
        for(j=0;n>0 && j<(u32)n;) {
            u8 *p=(u8 *)U32(t,4*(B(t,ACTIVE)+j));
            if((B(p,8)&8) || retire_player(p)) { B(p,8)|=8; erase(t,j); --n; }
            else ++j;
        }
    }
    retail_rollover();
}
static NOINLINE u32 count(u8 *t) {
    int r=reserve_count(t); return r<0?0:B(t,ACTIVE)+(u32)r;
}
static NOINLINE u8 *player(u8 *r,u8 *t,u32 i) {
    (void)r; return (u8 *)U32(t,4*i);
}
static NOINLINE void measure(u8 *p,u32 *fixed,u32 *strings,u32 kind) {
    static const u16 fields[]={0x104,0x108,0x10c,0x138,0x13c,0x10,0x14};
    u32 i,start=kind==500?0:5,end=kind==500?5:7;
    *fixed+=kind;
    for(i=start;i<end;i++) *strings+=2+2*length((u16 *)U32(p,fields[i]));
}
void FC ps_size(u8 *t,u8 *other,u8 *stadium,u32 *fixed,u32 *strings) {
    u32 i,j; u8 *teams[2]; teams[0]=t; teams[1]=other;
    *fixed=0x70; *strings=0;
    if(stadium) { u32 f,s; COPY(0x241F00)(stadium,&f,&s); *fixed+=f; *strings+=s; }
    for(j=0;j<2;j++) if(teams[j]) {
        u32 f,s; u8 *q=teams[j]; measure(q,fixed,strings,500);
        for(i=0;i<count(q);i++) measure(player(ROOT,q,i),fixed,strings,84);
        ((void (FC *)(u8 *,u32 *,u32 *))0x241690)((u8 *)U32(q,0x14c),&f,&s);
        *fixed+=f; *strings+=s;
        ((void (FC *)(u8 *,u32 *,u32 *))0x197020)((u8 *)U32(q,0x110),&f,&s);
        *fixed+=f; *strings+=s;
    }
}

/* Use the complete retail exporter/importer with temporary active views. All
 * changes to those views live on the stack and are restored before return.
 * The original 65-entry college arrays are sufficient for 53+12. */
extern u8 * FC retail_export(u8 *,u8 *,u8 *,u8 *);
extern u32 FC retail_import(u8 *,u8 *);
static NOINLINE void metadata(u8 *t,u8 *save,int restore) {
    if(restore) { B(t,RSV_VERSION)=save[0]; B(t,RSV_COUNT)=save[1]; B(t,RSV_MAGIC)=save[2]; }
    else { save[0]=B(t,RSV_VERSION); save[1]=B(t,RSV_COUNT); save[2]=B(t,RSV_MAGIC);
           B(t,RSV_VERSION)=B(t,RSV_COUNT)=B(t,RSV_MAGIC)=0; }
}
u8 * FC ps_export(u8 *t,u8 *other,u8 *stadium,u8 *out) {
    u8 saved[2][3],active[2],*teams[2],*result; int reserves[2]; u32 j,n=other?2:1;
    if(!t || !out || t==other) return 0;
    teams[0]=t; teams[1]=other;
    for(j=0;j<n;j++) if((reserves[j]=reserve_count(teams[j]))<0) return 0;
    for(j=0;j<n;j++) { active[j]=B(teams[j],ACTIVE); B(teams[j],ACTIVE)+=reserves[j]; metadata(teams[j],saved[j],0); }
    result=retail_export(t,other,stadium,out);
    for(j=0;j<n;j++) {
        B(teams[j],ACTIVE)=active[j]; metadata(teams[j],saved[j],1);
        if(result) { u8 *dest=(u8 *)(U32(result,0x1c)+500*j);
            B(dest,ACTIVE)=active[j]; metadata(dest,saved[j],1); }
    }
    return result;
}
u32 FC ps_import(u8 *src,u8 *dst) {
    u8 *r=ROOT,*team,*pool,meta[3]; u32 colleges[65],i,n=U32(src,0),available=0,result;
    u8 active; int reserves;
    if(n>65 || U32(src,0x18)!=1 || B(dst,ACTIVE) || reserve_count(dst)!=0) return 0;
    team=(u8 *)((u32)src+0x1c+U32(src,0x1c)-1);
    pool=(u8 *)((u32)src+4+U32(src,4)-1);
    active=B(team,ACTIVE); reserves=reserve_count(team);
    if(reserves<0 || active+(u32)reserves!=n) return 0;
    /* Serialized references are field-relative; verify the compact export's
     * ordered primary pool before retail's college-ID loop uses that order. */
    for(i=0;i<n;i++) {
        if((u32)team+4*i+U32(team,4*i)-1!=(u32)pool+84*i) return 0;
        colleges[i]=U32(pool,84*i);
    }
    for(i=0;i<U32(r,0);i++) {
        u8 *p=(u8 *)(U32(r,4)+84*i);
        if((B(p,8)&5)==1 && !owner(i) && !listed(p,0)) ++available;
    }
    if(available<n) return 0;
    B(team,ACTIVE)=n; metadata(team,meta,0);
    result=retail_import(src,dst);
    B(team,ACTIVE)=active; metadata(team,meta,1);
    if(result) { B(dst,ACTIVE)=active; metadata(dst,meta,1); }
    /* Retail leaves the input relocated; restore it, including raw college
     * IDs, so a failed operation may be inspected/retried without corruption. */
    FN1(0xC0730)(src);
    for(i=0;i<n;i++) U32(pool,84*i)=colleges[i];
    return result;
}
