/* MyCareer native adapters. EXPERIMENTAL / UNWITNESSED.
 * All mutable bytes are inside the existing 4096-byte state allocation.
 * Functions marked FC use the retail ECX/EDX fastcall convention.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FC __attribute__((fastcall))
#define NI __attribute__((noinline))
#define W(p,n) (*(u32 *)((u8 *)(p)+(n)))
#define B(p,n) (((u8 *)(p))[n])
#define G(n) (*(volatile u32 *)(n))
extern u8 state[4096];
extern u32 primary(void);
extern void resolve_team(void), settle(void);
extern void rebind(void);
#define S(n) W(state,n)
#define STAGED (state+1280)
#define ROOT ((u8 *)G(0xB72918))
extern const u8 menu_template[];
static NI void init_menus(void) {
    const u8 *p=menu_template; u8 *dst=state+256; u32 i;
    while(p[0] || p[1]) {
        for(i=0;i<4U*p[0];i++) *dst++=0;
        for(i=0;i<4U*p[1];i++) *dst++=p[2+i];
        p+=2+4U*p[1];
    }
}
static NI void move_bytes(u8 *out,const u8 *in,u32 n) { while(n--) *out++=*in++; }
static NI void zero(u8 *out,u32 n) { while(n--) *out++=0; }
static NI u32 fnv(const u8 *p,u32 n) {
    u32 v=0x811c9dc5; while(n--) v=(v^*p++)*0x1000193; return v;
}
u32 inline_active(void) {
    return S(0)==0x4251434d && S(4)==0x31303030 && G(0xE576A0)==2 &&
           S(2580)==2 && S(24)>=2 && S(24)<=6;
}
u32 FC inline_valid(const u8 *b,u32 arena) {
    u32 i,token=0;
    if(W(b,0)!=0x4c50434d || W(b,4)!=0x31303030 || W(b,8)!=0x800001 ||
       W(b,12)!=fnv(b+16,112) || W(b,32)>=4096 || B(b,36)<2 || B(b,36)>6 ||
       B(b,37)>=8 || B(b,38)>=2 || B(b,39)>=17 ||
       (W(b,40)>=32 && W(b,40)!=0xffffffff) ||
       W(b,60)&~0x0ffff000U || W(b,64)>1000000 || W(b,84)>1000000 ||
       W(b,68)>0x7f92b1 || B(b,72)>2 || B(b,73) ||
       (B(b,74)>=32 && B(b,74)!=255) || B(b,75) || W(b,76)>0x7f92b1 ||
       (!B(b,72) && (B(b,74)!=255 || W(b,76))) ||
       B(b,80)>1 || B(b,81)>1 || B(b,82) || B(b,83)) return 0;
    for(i=16;i<32;i++) token|=b[i];
    for(i=44;i<56;i+=4) if(W(b,i)<0x70 || W(b,i)>=arena) return 0;
    for(i=88;i<128;i++) if(b[i]) return 0;
    return token!=0;
}
void FC inline_encode(u8 *b) {
    zero(b,128);
    W(b,0)=0x4c50434d; W(b,4)=0x31303030; W(b,8)=0x800001;
    move_bytes(b+16,state+40,16); W(b,32)=S(28);
    B(b,36)=S(24); B(b,37)=S(32); B(b,38)=S(36); B(b,39)=state[149];
    W(b,40)=S(56); move_bytes(b+44,state+84,12);
    W(b,56)=S(100); W(b,60)=S(120)&0x0ffff000;
    move_bytes(b+64,state+64,8); move_bytes(b+72,state+188,8);
    B(b,80)=S(180); B(b,81)=S(184); W(b,84)=S(196);
    W(b,12)=fnv(b+16,112);
}
void inline_decode(void) {
    u8 *b=STAGED;
    zero(state,200); init_menus();
    S(4)=0x31303030; S(8)=1280;
    move_bytes(state+40,b+16,16); S(28)=W(b,32);
    S(24)=B(b,36); S(32)=B(b,37); S(36)=B(b,38); state[149]=B(b,39);
    S(56)=W(b,40); move_bytes(state+84,b+44,12);
    S(100)=W(b,56); S(120)=W(b,60);
    S(96)=W(b,44); S(112)=W(b,48); S(116)=W(b,52);
    move_bytes(state+64,b+64,8); move_bytes(state+188,b+72,8);
    S(180)=B(b,80); S(184)=B(b,81); S(196)=W(b,84);
    /* Enable only after the whole native deserialization has completed. */
    S(0)=0x4251434d; S(2580)=2;
    if(!primary()) { S(24)=6; S(2576)=7; }
    else resolve_team();
}
static NI u32 relative(const u8 *root,u32 arena,u32 field,u32 n) {
    u32 at=field+W(root,field)-1;
    return W(root,field) && at>=0x70 && at<arena && n<=arena-at?at:0;
}
/* Called ONLY after native signed read success, before any deserializer.
 * The complete metadata length is checked before following any file pointer.
 * +2660 is pending footer, +2664 records the SOURCE ROST extent for load.
 */
u32 FC inline_stage(const u8 *file,u32 size) {
    u32 base,growth,arena,pool,p,i,ref;
    const u8 *b,*r;
    S(2660)=0; S(2664)=0;
    if(size!=720044 && size!=724140 && size!=720172 && size!=724268) return 0;
    base=(size==720172 || size==724268)?size-128:size;
    growth=base-720044; arena=0x91000+growth;
    if(W(file,0x2e0)!=0x54534f52 || W(file,0x2e4)!=0x91020+growth ||
       W(file,0x30c)!=0x54534f52 || W(file,0x310)!=(growth!=0) ||
       W(file,0x314)!=13 || B(file,0x91320+growth)!=2 || G(0xB72808)<arena) return 0;
    S(2664)=0x91040+growth;
    if(base==size) return S(2580)==0;
    b=file+base; r=file+0x320;
    if(!inline_valid(b,arena) || W(r,0)>4096 || W(b,32)>=W(r,0) ||
       !(pool=relative(r,arena,4,84*W(r,0)))) return 0;
    p=pool+84*W(b,32);
    if(B(r,p+0x35)!=B(b,39) || W(r,p+4)!=W(b,56) ||
       (W(r,p+0x18)&0x0ffff000)!=W(b,60)) return 0;
    for(i=0;i<3;i++) {
        ref=relative(r,arena,p+(i?12+i*4:0),i?2:8);
        if(!ref || ref!=W(b,44+i*4)) return 0;
    }
    move_bytes(STAGED,b,128); S(2660)=1; return 1;
}
/* Metadata admission is independent of the currently loaded career. */
u32 FC inline_admit(u32 size) {
    u32 max=G(0xB72808);
    return size==720044 || size==720172 ||
           (max>=0x92000 && (size==724140 || size==724268));
}

/* Consumer-only play-call eligibility. The field unit and identity are
 * revalidated by the bounded binder, independently of menu/navigation club
 * ownership. Special teams, linemen and an absent MyPlayer use native CPU
 * calls. Supersim can query the same presence through mode_unit_present. */
u32 mode_unit_present(void) {
    if(!inline_active()) return 0;
    rebind();
    return S(24)==3?S(2568):0;
}
u32 FC mode_human(u8 *t) {
    u8 *p; u32 mask;
    if(!inline_active()) return t?W(t,0x30):0;
    p=(u8 *)mode_unit_present();
    if(!p || W(p,0x38)!=(u32)t || G(0xE602B4)!=4) return 0;
    mask=(u32)t==G(0xE60280)?0x389:((u32)t==G(0xE60284)?0x18c70:0);
    return (mask>>state[149])&1;
}

/* Owned entry and native CAP bridge. Menu/row bytes are immutable templates.
 * +2672 manager; +2676 uncommitted record; +2680 creation state (1 editing,
 * 2 choosing a team, 3 completion unwind); +2684 selected team.
 * +1408..1559 contains the original CAP slot and its two 34-byte name cells.
 */
#define N0(a) ((u32 (*)(void))(a))
#define N1(a) ((u32 (FC *)(u32))(a))
#define N2(a) ((u32 (FC *)(u32,u32))(a))
extern const u8 entry_menu[], apartment[], team_menu[], practice_menu[];
extern const u16 draft_notice[], refusal_notice[];
extern void FC native_new_player(u32 manager);
extern void FC mode_autosave(u32 manager,u32 descriptor);
static NI u32 owner(u32 manager) { return manager && S(2672)==manager && W((u8 *)manager,0x100)<32; }
static NI void notice(u32 manager,const u16 *text) { N2(0x14e520)(manager,(u32)text); }
static NI u8 *team(u32 index) {
    return ROOT && index<32 && W(ROOT,0x18)>=32?(u8 *)(W(ROOT,0x1c)+500*index):0;
}
static NI u32 player_bounds(u8 *p) {
    u32 off=(u32)p-W(ROOT,4);
    return p && W(ROOT,0)<=4096 && !(off%84) && off/84<W(ROOT,0);
}
static NI void rollback(void) {
    u8 *p=(u8 *)S(2676);
    if(p && ROOT && player_bounds(p)) {
        if(S(2680)==2) {
            N2(0x2425c0)((u32)ROOT+0x38,(u32)p);
            W((u8 *)W(ROOT,0x3c),4*W(ROOT,0x38))=S(1560);
        }
        move_bytes(p,state+1408,84);
        move_bytes((u8 *)W(p,16),state+1492,68);
    }
    S(2676)=S(2680)=0;
    G(0xCB8B14)=G(0xCB8B98)=G(0xCB8BA0)=G(0xCB8BA4)=0;
}
void FC mode_entry(u32 manager) {
    if(!manager || W((u8 *)manager,0x100)>=30 || S(2672)) return;
    S(0)=0; S(2580)=1; S(2672)=manager; S(2684)=0;
    init_menus();
    N2(0x6e390)(manager,(u32)entry_menu);
}
void FC mode_draft(u32 manager) { notice(manager,draft_notice); }
void FC mode_load(u32 manager) {
    if(owner(manager)) N2(0x6e390)(manager,0x508df0);
}
void FC mode_create(u32 manager) {
    u8 *p,*t; u32 i,j,n,first;
    if(!owner(manager) || S(2676)) return;
    if(!ROOT || W(ROOT,0x38)>=2500 || W(ROOT,0x18)>128) goto refuse;
    p=(u8 *)N0(0xbff50)();
    if(!p || !player_bounds(p) || p[0x28]==0xee) goto refuse;
    first=W(p,16)-(u32)ROOT;
    if(first<0x70 || first+68>G(0xB72808) || W(p,20)!=W(p,16)+34) goto refuse;
    /* Reject contradictory free/owned slots before the native initializer. */
    for(i=0;i<W(ROOT,0x18);i++) {
        t=(u8 *)(W(ROOT,0x1c)+i*500);
        if(t[0x19b]>1) goto refuse; /* Foreign/grown squad metadata needs its owner. */
        for(j=0;j<65;j++) if(W(t,j*4)==(u32)p) goto refuse;
    }
    for(i=0;i<W(ROOT,0x38);i++) if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)p) goto refuse;
    n=W(ROOT,0); t=(u8 *)W(ROOT,4);
    for(i=0;i<n;i++,t+=84) if(t!=p && (W(t,16)==W(p,16) || W(t,20)==W(p,20))) goto refuse;
    move_bytes(state+1408,p,84); move_bytes(state+1492,(u8 *)W(p,16),68);
    S(1560)=W((u8 *)W(ROOT,0x3c),4*W(ROOT,0x38));
    S(2676)=(u32)p; S(2680)=1;
    native_new_player(manager);
    return;
refuse: notice(manager,refusal_notice);
}
u32 FC mode_created(u32 manager) {
    u8 *p=(u8 *)S(2676); u32 i,count=0;
    if(!owner(manager) || S(2680)!=1 || (u32)p!=G(0xCB8B14) || !p || !(p[8]&4)) return 0;
    for(i=0;i<W(ROOT,0x38);i++) if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)p) count++;
    if(count!=1) return 0;
    S(2680)=3; return 1;
}
u32 mode_cap_ratings(void) {
    u8 *p=(u8 *)S(2676); u32 i;
    if(S(2680)!=1 || !p || (u32)p!=G(0xCB8B14) || p[0x35]<12) return 0;
    if(p[0x35]<17) for(i=0x36;i<=0x51;i++)
        if(i!=0x4b && i!=0x4d && i!=0x4f) p[i]=65;
    G(0xCB8B98)=0; return 1;
}
void FC mode_event(u32 manager,u32 event) {
    u32 top;
    if(!owner(manager)) return;
    top=W((u8 *)manager,8*W((u8 *)manager,0x100));
    if(event==3 && top==(u32)entry_menu && (S(2680)==1 || S(2680)==2)) rollback();
    if(event==3 && top==(u32)apartment) { resolve_team(); settle(); }
    if(event==6 && top==(u32)apartment) mode_autosave(manager,top);
}
u32 mode_team_left(void) { S(2684)=(S(2684)+31)%32; return 1; }
u32 mode_team_right(void) { S(2684)=(S(2684)+1)%32; return 1; }
u32 mode_team_get(void) { return S(2684); }
u32 mode_team_max(void) { return 31; }
u32 mode_team_name(void) { u8 *t=team(S(2684)); return t?W(t,0x104):0; }

static NI u32 on_stack(u32 manager,const u8 *descriptor) {
    u32 i,n=W((u8 *)manager,0x100);
    if(n>=32) return 0;
    for(i=0;i<=n;i++) if(W((u8 *)manager,8*i)==(u32)descriptor) return 1;
    return 0;
}
static NI u32 hub(u32 manager) { return owner(manager) && inline_active() && on_stack(manager,apartment); }
static NI void capture(u8 *p) {
    u32 i;
    zero(state,200); S(4)=0x31303030; S(8)=1280;
    S(24)=3; S(28)=((u32)p-W(ROOT,4))/84; S(56)=S(2684);
    /* Native RNG supplies a new per-career token. It is data, never identity
     * selected by name, a pre-generated player, or an executable recipe. */
    for(i=40;i<56;i+=4) S(i)=N1(0x48b50)(0xE5FCA0);
    S(40)|=1;
    S(84)=W(p,0)-(u32)ROOT; S(88)=W(p,16)-(u32)ROOT; S(92)=W(p,20)-(u32)ROOT;
    S(100)=W(p,4); S(120)=W(p,24); state[149]=p[0x35];
    state[190]=255; S(0)=0x4251434d; S(2580)=2;
    S(2676)=S(2680)=0; resolve_team();
}
void FC mode_sign(u32 manager) {
    u8 *p=(u8 *)S(2676),*t=team(S(2684)); u32 i,count=0;
    if(!owner(manager) || S(2680)!=2 || !t || !p || !player_bounds(p) || p[0x35]>=17) return;
    /* Match native acquisition's 54-player limit, including occupied tail
     * slots. Never displace a player or hide an invalid/full destination. */
    if(t[0x11c]>=54 || t[0x19b] || W(t,4*t[0x11c])) { notice(manager,refusal_notice); return; }
    for(i=0;i<W(ROOT,0x38);i++) if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)p) count++;
    if(count!=1 || !(p[8]&4)) { notice(manager,refusal_notice); return; }
    if(!N1(0x148ab0)(manager)) return; /* Native confirmation, before mutation. */
    N0(0x148c60)();
    G(0xE6011C)=0; /* Native Weekly Preparation off in player career. */
    N0(0x10ea10)();
    N0(0x13ee10)();
    N2(0x2425c0)((u32)ROOT+0x38,(u32)p);
    ((void (FC *)(u32,u32,u32,u32))0x3228a0)((u32)p,1,1,0);
    ((void (FC *)(u32,u32,u32))0x2bd260)((u32)p,(u32)t,1);
    N2(0xc3ee0)((u32)t,(u32)p); N1(0x243790)((u32)t); N1(0xc3f00)((u32)t);
    N1(0x13ec90)((u32)t);
    capture(p);
    N1(0x13f1b0)(manager);
}
void FC mode_play(u32 manager) {
    if(hub(manager) && primary()) N2(0x6e390)(manager,0x522828);
}
void FC mode_practice(u32 manager) {
    if(hub(manager) && primary()) N2(0x6e390)(manager,(u32)practice_menu);
}
void FC mode_practice_init(u32 manager) {
    u32 club=S(2588); (void)manager;
    N0(0x148ad0)();
    if(club) { N1(0x77ae0)(club); N1(0x77b20)(club); G(0xE601D4)=1; N0(0xe33f0)(); }
}
void FC mode_card(u32 manager) {
    u32 p;
    if(hub(manager) && (p=primary())) {
        ((void (FC *)(u32,u32,u32))0x320e90)(manager,p,S(2588));
    }
}
void FC mode_save_menu(u32 manager) {
    if(hub(manager)) N2(0x6e390)(manager,0x507ec8);
}
void FC mode_postgame(u32 manager) {
    /* Preserve the native postgame parent and its complete week processing.
     * It pops itself before committing; only then may Schedule return home. */
    N1(0xc74e0)(manager);
    if(hub(manager) && W((u8 *)manager,8*W((u8 *)manager,0x100))==0x522828)
        N2(0x6e450)(manager,(u32)apartment);
}
void FC mode_quit(u32 manager) {
    if(!owner(manager)) return;
    if(inline_active()) {
        N1(0xc8190)(manager);
        if(G(0xE576A0)==2) return; /* User cancelled the native exit dialog. */
    } else {
        rollback(); N2(0x6e450)(manager,0x515660);
    }
    S(0)=S(2580)=S(2672)=S(2560)=S(2564)=S(2568)=0;
}
u32 FC mode_route(u32 manager,u32 target) {
    if(!owner(manager) || !inline_active()) return target;
    if(target==0x522190) {
        if(on_stack(manager,entry_menu)) {
            N2(0x6e450)(manager,(u32)entry_menu);
            N2(0x6e2e0)(manager,(u32)apartment); return 0;
        }
        return (u32)apartment;
    }
    if(target==0x4e7ec0 && on_stack(manager,apartment)) N2(0x6e450)(manager,(u32)apartment);
    return target;
}
u32 FC mode_return(u32 manager,u32 target) {
    if(hub(manager) && G(0xE5FF80)<=2 &&
       on_stack(manager,practice_menu) &&
       W((u8 *)manager,8*W((u8 *)manager,0x100))==0x5275f8) return (u32)apartment;
    return target;
}
u32 FC mode_loaded(u32 manager,u32 target) {
    if(inline_active()) {
        S(2672)=manager;
        N1(0x13ec90)(S(2588));
        return (u32)apartment;
    }
    return target;
}
void mode_load_error(void) {
    extern const u16 load_notice[];
    if(S(2672)) notice(S(2672),load_notice);
}
