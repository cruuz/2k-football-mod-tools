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
#define G(n) (*(u32 *)(n))
extern u8 state[4096];
extern u32 primary(void);
extern void resolve_team(void), settle(void);
extern void rebind(void);
#define S(n) W(state,n)
#define STAGED (state+1280)
#define ROOT ((u8 *)G(0xB72918))
extern const u8 menu_template[];
extern const u8 text_template[], text_bytes[];
static NI void init_menus(void) {
    const u8 *p=menu_template,*q; u8 *dst=state+200; u32 i;
    for(i=0;i<(u32)text_bytes;i++) ((u16 *)(state+1408))[i]=text_template[i];
    while((i=*p++)) {
        q=p;
        if(i&128) { i=(i&127)+3; q=dst-*(const u16 *)p; p+=2; }
        else p+=i;
        while(i--) *dst++=*q++;
    }
}
static NI void move_bytes(u8 *out,const u8 *in,u32 n) { while(n--) *out++=*in++; }
static NI void zero(u8 *out,u32 n) { while(n--) *out++=0; }
static NI u32 fnv(const u8 *p,u32 n) {
    u32 v=0x811c9dc5; while(n--) v=(v^*p++)*0x1000193; return v;
}
u32 inline_active(void);
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
static const u8 save_words[]={7,0,14,21,22,23,25,30,16,17,47,48,0,49};
void FC inline_encode(u8 *b) {
    u32 i;
    zero(b,128);
    W(b,0)=0x4c50434d; W(b,4)=0x31303030; W(b,8)=0x800001;
    move_bytes(b+16,state+40,16);
    for(i=0;i<14;i++) if(save_words[i]) W(b,32+4*i)=S(4*save_words[i]);
    B(b,36)=S(24); B(b,37)=S(32); B(b,38)=S(36); B(b,39)=state[149];
    W(b,60)&=0x0ffff000;
    B(b,80)=S(180); B(b,81)=S(184);
    W(b,12)=fnv(b+16,112);
}
void inline_decode(void) {
    u8 *b=STAGED; u32 i;
    zero(state,200); init_menus();
    S(4)=0x31303030; S(8)=1280;
    move_bytes(state+40,b+16,16);
    for(i=0;i<14;i++) if(save_words[i]) S(4*save_words[i])=W(b,32+4*i);
    S(24)=B(b,36); S(32)=B(b,37); S(36)=B(b,38); state[149]=B(b,39);
    S(96)=W(b,44); S(112)=W(b,48); S(116)=W(b,52);
    S(180)=B(b,80); S(184)=B(b,81);
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
 * +3312..3467 contains the original CAP slot, its two 34-byte name cells,
 * and the unused free-agent tail word. Strings at +1408 are restored after
 * the creation-only club row overlay is popped; its title stays in RX.
 */

#define CALL2(a,x,y) ({ u32 cx_=(u32)(x),dx_=(u32)(y),ax_; \
 __asm__ volatile("call %c3" : "=a"(ax_), "+c"(cx_), "+d"(dx_) : "i"(a) \
 : "memory", "cc", "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"); ax_; })
#define CALL1(a,x) ({ u32 cx_=(u32)(x),ax_; __asm__ volatile("call %c2" : "=a"(ax_), "+c"(cx_) : "i"(a) : "edx", "memory", "cc", "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"); ax_; })
#define CALL0(a) ({ u32 ax_; __asm__ volatile("call %c1" : "=a"(ax_) : "i"(a) : "ecx", "edx", "memory", "cc", "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"); ax_; })

#define N0(a) ((u32 (*)(void))(a))
#define N1(a) ((u32 (FC *)(u32))(a))
#define N2(a) ((u32 (FC *)(u32,u32))(a))
extern const u8 entry_menu[], apartment[], team_menu[], practice_menu[], club_menu[];
extern const u16 watch_text[], fixture_text[];
u32 mode_next_fixture(void);
extern const u16 draft_notice[], refusal_notice[];
extern void FC native_new_player(u32 manager);
extern void FC mode_autosave(u32 manager,u32 descriptor);
static NI u32 owner(u32 manager) { return manager && S(2672)==manager && W((u8 *)manager,0x100)<32; }
static NI void notice(u32 manager,const u16 *text) { CALL2(0x14e520,manager,(u32)text); }
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
            CALL2(0x2425c0,(u32)ROOT+0x38,(u32)p);
            W((u8 *)W(ROOT,0x3c),4*W(ROOT,0x38))=S(3464);
        }
        move_bytes(p,state+3312,84);
        move_bytes((u8 *)W(p,16),state+3396,68);
    }
    S(2676)=S(2680)=0;
    G(0xCB8B14)=G(0xCB8B98)=G(0xCB8BA0)=G(0xCB8BA4)=0;
}
void FC mode_entry(u32 manager) {
    if(!manager || W((u8 *)manager,0x100)>=30 || S(2672)) return;
    S(0)=0; S(2580)=1; S(2672)=manager; S(2684)=0;
    init_menus();
    CALL2(0x6e390,manager,(u32)entry_menu);
}
void FC mode_draft(u32 manager) { notice(manager,draft_notice); }
void FC mode_load(u32 manager) {
    if(owner(manager)) CALL2(0x6e390,manager,0x508df0);
}
void FC mode_create(u32 manager) {
    u8 *p,*t; u32 i,j,n,first;
    if(!owner(manager) || S(2676)) return;
    if(!ROOT || W(ROOT,0x38)>=2500 || W(ROOT,0x18)>128) goto refuse;
    p=(u8 *)CALL0(0xbff50);
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
    move_bytes(state+3312,p,84); move_bytes(state+3396,(u8 *)W(p,16),68);
    S(3464)=W((u8 *)W(ROOT,0x3c),4*W(ROOT,0x38));
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
    if(event==3 && top!=(u32)club_menu) init_menus();
    if(event==3 && top==(u32)entry_menu && (S(2680)==1 || S(2680)==2)) rollback();
    if(event==3 && top==(u32)apartment) { resolve_team(); settle(); }
    if(event==6 && top==(u32)apartment) mode_autosave(manager,top);
}
void FC mode_team_confirm(u32 manager) {
    u32 row=W((u8 *)manager,8*W((u8 *)manager,0x100)+4);
    if(owner(manager) && S(2680)==2 && row<32) {
        S(2684)=row;
        CALL1(0x6e400,manager);
    }
}
void FC mode_team_open(u32 manager) {
    u32 i; u8 *r=state+432;
    if(!owner(manager) || S(2680)!=2) return;
    /* Creation-only overlay. CAP rollback is outside the bounded binder list.
     * Resume restores the parent templates before native reconstruction. */
    zero(r,33*52);
    for(i=0;i<32;i++,r+=52) {
        W(r,0)=9; W(r,4)=W(team(i),0x104); W(r,40)=(u32)mode_team_confirm;
    }
    W(r,0)=3;
    CALL2(0x6e390,manager,(u32)club_menu);
    W((u8 *)manager,8*W((u8 *)manager,0x100)+4)=S(2684);
}

/* Retail text context, font binding, opaque tint, alignment and draw path.
 * Unlike the animated list handler this does not need a named SCNE sheet. */
static NI void text(const u16 *s,u32 selected,float x,float y,u32 font) {
    ((void (FC *)(const u16 *,u32,float,float,float,float,u32,u32,u32,u32))0x6bc30)
        (s,0,x,y,20,240,0,0,G(0xa90ecc+4*font),selected?0xffffff00:0xffffffff);
}
static NI const u16 *footer(void) {
    u32 slot=mode_next_fixture(),args[3];
    const u8 *p=(const u8 *)(0xE57C40+8*slot);
    if(slot>=374) return watch_text;
    args[0]=W((u8 *)G(0xE5786C+4*p[2]),0x104);
    args[1]=W((u8 *)G(0xE5786C+4*p[1]),0x104); args[2]=(u32)watch_text;
    ((void (FC *)(u8 *,u32,const u16 *,u32 *))0x49f00)(state+3468,314,fixture_text,args);
    return (const u16 *)(state+3468);
}
void FC mode_draw(u32 manager) {
    const u8 *d=(const u8 *)W((u8 *)manager,8*W((u8 *)manager,0x100));
    /* Native navigation owns every title, row and selected-row highlight.
     * This pass supplies only the two extra pieces of career information. */
    if(d==apartment) text(footer(),0,320,432,0);
    if(d==team_menu) text((const u16 *)W(team(S(2684)),0x104),0,320,380,1);
}

void mode_visuals(void) {
    u8 *p=(u8 *)mode_unit_present(),*t=0; u32 old=0;
    if(p) { t=(u8 *)W(p,0x38); old=W(t,0x30); W(t,0x30)=1; }
    /* This flag is scoped to the unchanged native renderer. CPU selection,
     * control transfer and teammate AI never observe the temporary value. */
    CALL0(0x75d90);
    if(t) W(t,0x30)=old;
    /* Live substitutions and special-team waits have no modal prompt.
     * The Apartment explains CPU control without floating text over play. */
}
u32 mode_result(void) {
    u32 result=G(0xA83A18);
    /* Only the engine's completed-game signal may consume a career fixture.
     * Initial/running state 3 must never turn an abandoned match into stats. */
    return inline_active() && result!=2?0:result;
}

static NI u32 on_stack(u32 manager,const u8 *descriptor) {
    u32 i,n=W((u8 *)manager,0x100);
    if(n>=32) return 0;
    for(i=0;i<=n;i++) if(W((u8 *)manager,8*i)==(u32)descriptor) return 1;
    return 0;
}
static NI u32 hub(u32 manager) { return owner(manager) && inline_active() && on_stack(manager,apartment); }
extern void start_player(void);
void FC mode_start(u32 manager) {
    if(hub(manager)) start_player();
}
static NI void capture(u8 *p) {
    u32 i;
    zero(state,200); S(4)=0x31303030; S(8)=1280;
    S(24)=3; S(28)=((u32)p-W(ROOT,4))/84; S(56)=S(2684);
    /* Native RNG supplies a new per-career token. It is data, never identity
     * selected by name, a pre-generated player, or an executable recipe. */
    for(i=40;i<56;i+=4) S(i)=CALL1(0x48b50,0xE5FCA0);
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
    if(!CALL1(0x148ab0,manager)) return; /* Native confirmation, before mutation. */
    CALL0(0x148c60);
    G(0xE6011C)=0; /* Native Weekly Preparation off in player career. */
    CALL0(0x10ea10);
    CALL0(0x13ee10);
    CALL2(0x2425c0,(u32)ROOT+0x38,(u32)p);
    ((void (FC *)(u32,u32,u32,u32))0x3228a0)((u32)p,1,1,0);
    ((void (FC *)(u32,u32,u32))0x2bd260)((u32)p,(u32)t,1);
    CALL2(0xc3ee0,(u32)t,(u32)p); CALL1(0x243790,(u32)t); CALL1(0xc3f00,(u32)t);
    CALL1(0x13ec90,(u32)t);
    capture(p);
    start_player();
    CALL1(0x13f1b0,manager);
}
/* Return the first playable career fixture, never a selected Schedule card.
 * Retail rows have 17 eight-byte entries; 0/1 are the unplayed states.
 * Advance intervening league weeks natively, then continue the same action
 * into C79F0. The first own fixture is never included in that CPU advance. */
u32 mode_next_fixture(void) {
    u32 i; const u8 *p=(const u8 *)0xE57C40;
    if(G(0xE576A4)<7 || G(0xE576A4)>9 || S(56)>=32) return 374;
    for(i=0;i<374;i++,p+=8)
        if(p[0]<2 && (p[1]==S(56) || p[2]==S(56))) return i;
    return 374;
}
void FC mode_play(u32 manager) {
    u32 slot;
    extern const u16 advance_notice[];
    if(!hub(manager) || !primary()) return;
    start_player();
    if(S(56)>=32) return;
    slot=mode_next_fixture();
    if(slot<374 && slot/17<=G(0xE576B4)) {
        if(!((u32 (FC *)(u32,u32,u32))0xC79F0)(slot/17,slot%17,S(32))) {
            CALL2(0x6e390,manager,0x4F19E8);
            CALL2(0x6e390,manager,0x51B908);
        }
    } else {
        if(slot>=374) notice(manager,advance_notice);
        N1(G(0xE576B4)<G(0xE576B0)?0x247D40:0x2480B0)(manager);
        if(slot<374) mode_play(manager);
    }
}
void FC mode_practice(u32 manager) {
    if(hub(manager) && primary()) {
        start_player();
        CALL2(0x6e390,manager,(u32)practice_menu);
    }
}
void FC mode_practice_init(u32 manager) {
    u32 club=S(2588),other=(u32)team((S(56)+1)&31),swap; (void)manager;
    CALL0(0x148ad0);
    /* Free Practice starts with home offense. Keep the unique created
     * record on its position's side, instead of copying it to both teams. */
    if((0x18c70>>state[149])&1) { swap=club; club=other; other=swap; }
    if(club) { CALL1(0x77ae0,club); CALL1(0x77b20,other); G(0xE601D4)=1; CALL0(0xe33f0); }
}
void FC mode_card(u32 manager) {
    u32 p;
    if(hub(manager) && (p=primary())) {
        ((void (FC *)(u32,u32,u32))0x320e90)(manager,p,S(2588));
    }
}
void FC mode_save_menu(u32 manager) {
    if(hub(manager)) CALL2(0x6e390,manager,0x507ec8);
}
void FC mode_postgame(u32 manager) {
    /* Preserve the native postgame parent and its complete week processing.
     * It pops itself before committing; only then may Schedule return home. */
    CALL1(0xc74e0,manager);
    if(hub(manager) && W((u8 *)manager,8*W((u8 *)manager,0x100))==0x522828)
        CALL2(0x6e450,manager,(u32)apartment);
}
void FC mode_quit(u32 manager) {
    if(!owner(manager)) return;
    if(inline_active()) {
        CALL1(0xc8190,manager);
        if(G(0xE576A0)==2) return; /* User cancelled the native exit dialog. */
    } else {
        rollback(); CALL2(0x6e450,manager,0x515660);
    }
    S(0)=S(2580)=S(2672)=S(2560)=S(2564)=S(2568)=0;
}
u32 FC mode_route(u32 manager,u32 target) {
    if(!owner(manager) || !inline_active()) return target;
    if(target==0x522190) {
        if(on_stack(manager,entry_menu)) {
            CALL2(0x6e450,manager,(u32)entry_menu);
            CALL2(0x6e2e0,manager,(u32)apartment); return 0;
        }
        return (u32)apartment;
    }
    if(target==0x4e7ec0 && on_stack(manager,apartment)) CALL2(0x6e450,manager,(u32)apartment);
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
        CALL1(0x13ec90,S(2588));
        return (u32)apartment;
    }
    return target;
}
void mode_load_error(void) {
    extern const u16 load_notice[];
    if(S(2672)) notice(S(2672),load_notice);
}
