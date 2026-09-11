/* MyCareer native adapters. EXPERIMENTAL / UNWITNESSED.
 * Mutable bytes use the named 4096-byte base and 4096-byte M3 allocations.
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
extern u8 m3[4096];
#define M(n) W(m3,n)
extern const u8 m3_menu_template[],m3_menu_bytes[];
extern u8 settings_rows[];
extern const u16 m3_supersim_off_text[],m3_supersim_skip_text[],m3_supersim_fast_text[];
extern const u16 m3_star_off_text[],m3_star_on_text[],m3_settings_note[];
extern const u16 m3_fpf_off_text[],m3_fpf_on_text[];
extern const u16 m3_ff_format[],m3_ff_wait_text[];
extern const u8 m3_settings_menu[];
extern u32 primary(void);
extern void resolve_team(void), settle(void);
extern void rebind(void);
#define S(n) W(state,n)
#define STAGED (state+1280)
#define ROOT ((u8 *)G(0xB72918))
/* +2696 Supersim (0 skip, 1 off, 2 fast), +2700 star disabled, +2704 FPF.
 * The retail word E5FFE4 remains authoritative; only load reapplies it. */
static NI void settings_labels(void) {
    W(settings_rows,4)=(u32)(G(0xE5FFE4)?m3_fpf_on_text:m3_fpf_off_text);
    W(settings_rows,52+4)=(u32)(S(2696)==2?m3_supersim_fast_text:
                              S(2696)?m3_supersim_off_text:m3_supersim_skip_text);
    W(settings_rows,104+4)=(u32)(S(2700)?m3_star_off_text:m3_star_on_text);
}
static NI void player_star(u8 *p) { p[0x53]=(p[0x53]&0xfe)|!S(2700); }
extern const u8 menu_template[];
extern const u8 text_template[], text_bytes[];
static NI void init_menus(void) {
    const u8 *p=menu_template,*q; u8 *dst=state+200; u32 i;
    for(i=0;i<(u32)text_bytes;i++) ((u16 *)(state+1408))[i]=text_template[i];
    for(i=0;i<(u32)m3_menu_bytes;i++) m3[256+i]=m3_menu_template[i];
    while((i=*p++)) {
        q=p;
        if(i&128) { i=(i&127)+3; q=dst-*(const u16 *)p; p+=2; }
        else p+=i;
        while(i--) *dst++=*q++;
    }
    settings_labels();
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
       B(b,80)>1 || B(b,81)>1 || B(b,82)>15 ||
       (B(b,82)&10)==10 || B(b,83)) return 0;
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
    S(2704)=G(0xE5FFE4)!=0;
    B(b,82)=S(2704)|(S(2696)==2?8:S(2696)<<1)|(S(2700)<<2);
    W(b,12)=fnv(b+16,112);
}
void inline_decode(void) {
    u8 *b=STAGED; u32 i;
    zero(state,200);
    S(2696)=b[82]&8?2:(b[82]>>1)&1; S(2700)=(b[82]>>2)&1; S(2704)=b[82]&1;
    S(2712)=S(2716)=0;
    zero(m3,256); zero(m3+3600,496); init_menus();
    S(4)=0x31303030; S(8)=1280;
    move_bytes(state+40,b+16,16);
    for(i=0;i<14;i++) if(save_words[i]) S(4*save_words[i])=W(b,32+4*i);
    S(24)=B(b,36); S(32)=B(b,37); S(36)=B(b,38); state[149]=B(b,39);
    S(96)=W(b,44); S(112)=W(b,48); S(116)=W(b,52);
    S(180)=B(b,80); S(184)=B(b,81);
    /* Enable only after the whole native deserialization has completed. */
    S(0)=0x4251434d; S(2580)=2;
    if(!primary()) { S(24)=6; S(2576)=7; }
    else { G(0xE5FFE4)=S(2704); player_star((u8 *)primary()); resolve_team(); }
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
    if(!p || S(2712) || W(p,0x38)!=(u32)t || G(0xE602B4)!=4) return 0;
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

/* Stage 1: repeat the native presentation-skip request. Stage 2 uses the
 * same guarded path during accelerated updates. +2696 stores 0 skip,
 * 1 off, 2 fast (the new-career default).
 * The Settings footer preserves it on cold load. No simulation
 * delta, football clock, camera phase or native completion flag is written.
 * A2120 retains its replay/readiness/period guards and cleanup. */
static NI u32 mode_skip_ready(void) {
    if(S(2696)==1 || G(0xA83A18)!=3 || G(0xA83A14) ||
       !G(0xE60268) || !S(2564) || !inline_active()) return 0;
    if(mode_unit_present() || S(24)!=3) return 0;
    if(CALL2(0x70a10,S(32),0)&0x200) { S(2696)=1; S(2712)=S(2716)=0; return 0; }
    return 1;
}
void mode_skip_tick(void) {
    u32 phase=G(0xB616C0);
    /* This replaces 64D27's native no-op 89F40, before the normal update.
     * Never dismiss challenge decisions, tosses or arbitrary modal menus. */
    if((phase==20 || phase==23 || phase==24 || phase==25 || phase==27) &&
       mode_skip_ready()) CALL0(0xa2120);
}
u32 FC mode_skip_buttons(u32 port,u32 bank) {
    u32 buttons=CALL2(0x70a10,port,bank);
    /* Only the two automatic-replay screen consumers. Do not synthesize
     * controller input for gameplay, play calling, pause or modal dialogs. */
    if(port==S(32) && !bank && G(0xB616C0)==20 && mode_skip_ready()) buttons|=0x100;
    return buttons;
}

/* Stage 2 candidate. Main-frame event 6 is the complete native outer update;
 * hardware polling and render events remain outside this bounded loop.
 * +2712 waits for a settled appearance, +2716 gates audio/ticker. Both are
 * transient and cleared on load. Personnel membership still comes from the
 * native binder, including substitutions, K and P. */
static NI u32 mode_ff_settled(void) {
    u8 *p=(u8 *)G(0xE60268),*task; u32 n=128,count=0,i;
    if(G(0xE602B8)!=13 || !G(0xE60294) ||
       !(G(0xE602AC)>0 && G(0xE602AC)<=0x42700000)) return 0;
    while(p && n--) {
        if(!W(p,0x48)) {
            task=(u8 *)W(p,0x20);
            if(!task || W(task,0x3e4)!=13 ||
               !CALL1(0x1ff940,p)) return 0;
            /* Readiness alone remains true while a CPU snap is queued.
             * Event 28 and the post-request QB task must both be absent. */
            for(i=0;i<8;i++) if(W(task,0x320+24*i) &&
                                 W(task,0x334+24*i)==28) return 0;
            if(W(task,0x310) && G(W(task,0x310))==0x2d2ad0) return 0;
            count++;
        }
        p=(u8 *)W(p,0x30);
    }
    return !p && count==22;
}
u32 mode_ff_hold_snap(void) {
    /* Both native CPU snap decision entries stop before event 28 is posted.
     * This also covers a two-minute/no-huddle immediate-snap decision on
     * the very frame the personnel becomes ready. No task is rewritten. */
    return S(2716) && S(2712) && G(0xE602B8)==13 && mode_unit_present();
}
static NI u32 mode_ff_ready(u32 manager) {
    u32 depth,body,phase=G(0xE602B8),camera=G(0xB616C0);
    if(S(2696)!=2 || !inline_active() || G(0xA83A18)!=3 ||
       G(0xA83A14) || !S(2564) || !G(0xE60268) ||
       !manager || (depth=W((u8 *)manager,0x100))>=32 ||
       W((u8 *)manager,8*depth)!=0x4e7ec0) return 0;
    if(!CALL2(0x709b0,S(32),0) || (CALL2(0x70a10,S(32),0)&0x200)) {
        S(2696)=1; S(2712)=0; return 0;
    }
    /* Installed modal guards: initial/OT toss, challenge, tips and every
     * non-game manager descriptor run at 1x with native prompts intact. */
    if(!G(0xE602B4) || camera==26 || G(0xBB6CB4) ||
       phase<11 || phase>21) return 0;
    body=mode_unit_present();
    if(body) {
        if(!S(2712)) return 0;
        if(mode_ff_settled()) {
            S(2712)=0;
            S(2728)=1;
            W((u8 *)G(0xE60294),16)=G(0xE602AC);
            CALL1(0xaf510,G(0xE60294));
            rebind();
            return 0;
        }
        /* Unexpected mid-play membership never gives away a snap. Keep
         * normal speed until the native next pre-snap appearance settles. */
        if(phase!=11 && phase!=12 && phase!=13) return 0;
    } else S(2712)=1;
    return 1;
}
u32 FC mode_ff_frame(u32 manager,u32 unused,u32 delta) {
    u32 i=0,result; (void)unused;
    S(2728)=0;
    S(2716)=mode_ff_ready(manager);
    if(S(2728)) { S(2728)=0; return 1; }
    do {
        if(i) CALL1(0x48b50,0xE5FCA0);
        result=((u32 (FC *)(u32,u32,u32))0x6e6a0)(manager,0,delta);
        i++;
        if(!S(2716)) break;
        S(2716)=mode_ff_ready(manager);
    } while(S(2716) && i<8);
    S(2728)=0;
    return result;
}
void mode_ff_audio(void) {
    u32 i,gain=G(0xA70830);
    /* Retire native voices even while muted. Invalidate cached SetVolume
     * values in both device-buffer banks so entering/leaving mute is heard. */
    if(S(2716) || S(2724)) for(i=0;i<64;i++) {
        G(0xA70A90+i*0x68)=0xbf800000;
        G(0xA72490+i*0x68)=0xbf800000;
    }
    S(2724)=S(2716);
    if(S(2716)) G(0xA70830)=0;
    CALL0(0x3dbc0);
    G(0xA70830)=gain;
}

#define N0(a) ((u32 (*)(void))(a))
#define N1(a) ((u32 (FC *)(u32))(a))
#define N2(a) ((u32 (FC *)(u32,u32))(a))
extern const u8 entry_menu[], apartment[], team_menu[], practice_menu[], club_menu[];
extern const u8 m3_progress_menu[],m3_prep_menu[],m3_draft_menu[],m3_upgrade_menu[];
extern const u16 m3_progress_note[],m3_prep_note[],m3_draft_note[],m3_unsigned_text[];
extern const u16 m3_calendar_format[],m3_pick_format[];
void FC m3_boot_tick(u32 manager);
void FC m3_draft_tick(u32 manager);
void FC mode_create(u32 manager);
void FC m3_draw_upgrade(u32 manager);
u32 FC m3_creation_route(u32 manager);
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
    S(0)=0; S(2580)=1; S(2672)=manager; S(2684)=0; zero(m3,4096);
    init_menus();
    CALL2(0x6e390,manager,(u32)entry_menu);
}
void FC mode_draft(u32 manager) {
    if(!owner(manager) || S(2676) || inline_active()) return;
    /* Cancelling CAP preserves the already generated class for a retry. */
    if(M(0)==2 && G(0xE576A4)==4 && G(0xE576B8)==1) { mode_create(manager); return; }
    if(M(0)) return;
    if(!CALL1(0x148ab0,manager)) return;
    CALL0(0x148c60); G(0xE6011C)=0; G(0xE60120)=0;
    CALL0(0x10ea10); CALL0(0x13ee10);
    M(0)=1; M(4)=0;
    CALL2(0x6e390,manager,(u32)m3_progress_menu);
}
void FC mode_undrafted(u32 manager) {
    if(M(0)) notice(manager,draft_notice);
    else mode_create(manager);
}
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
    p[0x53]|=1; S(2680)=3; return 1;
}
u32 mode_cap_ratings(void) {
    u8 *p=(u8 *)S(2676);
    /* Retail has 51 templates, including OL/DT/DE. Let the native writer
     * use all of them, including the pools owner's EDGE rows. Only an
     * invalid position needs the bounds guard. */
    if(S(2680)!=1 || !p || (u32)p!=G(0xCB8B14) || p[0x35]<17) return 0;
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
void FC mode_frame(u32 manager) {
    u32 top=W((u8 *)manager,8*W((u8 *)manager,0x100));
    /* Save and Quit are handled before another league operation. A new
     * descriptor gets a visible frame before its first expensive update. */
    CALL2(0xf3e90,manager,6);
    if(!owner(manager) || top!=W((u8 *)manager,8*W((u8 *)manager,0x100))) return;
    if(top==(u32)m3_progress_menu) m3_boot_tick(manager);
    if(top==(u32)m3_draft_menu) m3_draft_tick(manager);
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
static NI void ticker_play(u16 *s) {
    u32 line=0,n,cut; u16 saved;
    while(*s && line<4) {
        n=0; while(s[n] && n<48) n++;
        cut=n;
        if(s[n]) { while(cut && s[cut]!=32) cut--; if(!cut) cut=n; }
        saved=s[cut]; s[cut]=0;
        /* Retail glyph widths, not a guessed average character width. */
        while(cut>1 && CALL2(0x49410,G(0xa90ecc),s)>540) {
            s[cut]=saved; saved=s[--cut]; s[cut]=0;
        }
        text(s,0,320,374+22*line,0);
        s[cut]=saved; s+=cut; while(*s==32) s++;
        line++;
    }
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
    if(d==m3_progress_menu) text(m3_progress_note,0,320,404,0);
    if(d==m3_prep_menu) text(m3_prep_note,0,320,404,0);
    if(d==m3_settings_menu) text(m3_settings_note,0,320,404,0);
    if(d==m3_draft_menu) {
        u32 args[2]={G(0xE3C0A8)+1,G(0xE3C0A4)+1};
        ((void (FC *)(u8 *,u32,const u16 *,u32 *))0x49f00)(m3+2700,400,m3_pick_format,args);
        text((const u16 *)(m3+2700),0,320,380,0);
        text(m3_draft_note,0,320,432,0);
    }
    if(d==m3_upgrade_menu) m3_draw_upgrade(manager);
    if(d==apartment) {
        u32 slot=mode_next_fixture(),args[6];
        const u8 *p=(const u8 *)(0xE57C40+8*slot);
        if(slot<374) {
            args[0]=slot/17+1; args[1]=p[3]; args[2]=p[4];
            args[3]=2000+(u32)p[5]; args[4]=p[6]; args[5]=p[7];
            ((void (FC *)(u8 *,u32,const u16 *,u32 *))0x49f00)(m3+2700,400,m3_calendar_format,args);
            text((const u16 *)(m3+2700),0,320,404,0);
        }
    }
}

void mode_visuals(void) {
    u8 *p=(u8 *)mode_unit_present(),*t=0; u32 old=0;
    if(p) { t=(u8 *)W(p,0x38); old=W(t,0x30); W(t,0x30)=1; }
    /* This flag is scoped to the unchanged native renderer. CPU selection,
     * control transfer and teammate AI never observe the temporary value. */
    CALL0(0x75d90);
    if(t) W(t,0x30)=old;
    if(S(2716) && G(0xE6028C) && G(0xE5FC28) && G(0xE5FC68)) {
        u16 header[128],last[512]; u32 seconds,args[5];
        float clock=*(float *)(G(0xE6028C)+16);
        seconds=clock>0 && clock<3600?(u32)(clock+.999f):0;
        args[0]=G(G(0xE5FC28)); args[1]=G(G(0xE5FC68));
        args[2]=G(0xE602C4); args[3]=seconds/60; args[4]=seconds%60;
        ((void (FC *)(u16 *,u32,const u16 *,u32 *))0x49f00)
            (header,sizeof(header),m3_ff_format,args);
        text(header,1,320,350,0);
        /* Same last-play formatter as the native visual simulator. The
         * event counter is monotonic; its formatter owns ring indexing. */
        if(G(0xE53804) && G(0xE53804)<0x80000000U) {
            CALL2(0x150620,last,G(0xE53804)-1);
            ticker_play(last);
        } else text(m3_ff_wait_text,0,320,374,0);
    }
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
void FC mode_settings_open(u32 manager) {
    if(hub(manager)) CALL2(0x6e390,manager,(u32)m3_settings_menu);
}
void FC mode_settings_toggle(u32 manager) {
    u32 row; u8 *p;
    if(hub(manager) && W((u8 *)manager,8*W((u8 *)manager,0x100))==(u32)m3_settings_menu) {
        row=W((u8 *)manager,8*W((u8 *)manager,0x100)+4);
        if(row==0) CALL0(0x147e60); /* Retail Franchise Settings toggle. */
        if(row==1) { S(2696)=S(2696)==2?1:S(2696)==1?0:2; S(2712)=S(2716)=0; }
        if(row==2 && (p=(u8 *)primary())) { S(2700)=!S(2700); player_star(p); }
        settings_labels();
        /* Native row construction caches each label pointer. Refresh that
         * cache while retaining the selected row; native scrolling resumes. */
        CALL1(0x14ff80,manager);
    }
}
extern void start_player(void);
void FC mode_start(u32 manager) {
    if(hub(manager)) start_player();
}
static NI void capture(u8 *p) {
    u32 i;
    zero(state,200); S(2696)=2; S(2712)=S(2716)=S(2700)=S(2704)=G(0xE5FFE4)=0;
    player_star(p); S(4)=0x31303030; S(8)=1280;
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
extern const u16 m3_sign_text[],m3_sign_cut_text[];
static NI u32 m3_sign_limit(u8 *t) {
    u32 n;
    if(B((u8 *)0xc3ee0,0)==0xe9) {
        /* The complete Practice Squad installation is validated offline.
         * Its stable ps_limit entry also dispatches arena-grown reserves. */
        n=CALL1(0x3ee10c,(u32)t);
        return n<54?n:54;
    }
    if(t[0x11c]>64 || t[0x19b] || t[0x1f2] || t[0x1f3] || W(t,4*t[0x11c])) return 0;
    return 54;
}
void FC mode_sign(u32 manager) {
    u32 continuing=inline_active() && S(24)==4;
    u8 *p=continuing?(u8 *)primary():(u8 *)S(2676),*t=team(S(2684)); u32 i,count=0,limit,old;
    if(!owner(manager) || S(2680)!=2 || !t || !p || !player_bounds(p) || p[0x35]>=17) return;
    /* Native preseason cuts leave all clubs at 54. An undrafted career can
     * ask the chosen club to make room using its native cut policy. Fresh
     * free-agent entry retains the existing 54-player admission rule. */
    limit=continuing?m3_sign_limit(t):54;
    if(!limit || (!continuing && (t[0x11c]>=54 || t[0x19b] || W(t,4*t[0x11c])))) {
        notice(manager,refusal_notice); return;
    }
    for(i=0;i<W(ROOT,0x38);i++) if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)p) count++;
    if(count!=1 || !(p[8]&4)) { notice(manager,refusal_notice); return; }
    if(continuing) {
        if(!CALL2(0x14e540,manager,(u32)(t[0x11c]>=limit?m3_sign_cut_text:m3_sign_text))) return;
        while(t[0x11c]>=limit) {
            old=t[0x11c]; CALL2(0x2bf9a0,(u32)t,limit-1);
            limit=m3_sign_limit(t);
            if(!limit || t[0x11c]>=old) { notice(manager,refusal_notice); return; }
        }
    } else if(!CALL1(0x148ab0,manager)) return;
    if(!continuing) {
        CALL0(0x148c60);
        G(0xE6011C)=0; /* Native Weekly Preparation off in player career. */
        CALL0(0x10ea10);
        CALL0(0x13ee10);
    }
    CALL2(0x2425c0,(u32)ROOT+0x38,(u32)p);
    ((void (FC *)(u32,u32,u32,u32))0x3228a0)((u32)p,1,1,0);
    ((void (FC *)(u32,u32,u32))0x2bd260)((u32)p,(u32)t,1);
    CALL2(0xc3ee0,(u32)t,(u32)p); CALL1(0x243790,(u32)t); CALL1(0xc3f00,(u32)t);
    CALL1(0x13ec90,(u32)t);
    if(continuing) { S(2680)=0; player_star(p); resolve_team(); }
    else capture(p);
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
void FC mode_sim_appearance(u32 manager) {
    if(!hub(manager) || !primary()) return;
    S(2696)=2;
    settings_labels();
    mode_play(manager);
    /* Arm only after the native fixture route reached Team Select. This
     * includes MyPlayer's first appearance when his unit starts the game. */
    if(W((u8 *)manager,8*W((u8 *)manager,0x100))==0x51b908)
        S(2712)=1;
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
    if(owner(manager) && inline_active() && (p=primary())) {
        ((void (FC *)(u32,u32,u32))0x320e90)(manager,p,S(2588));
    }
}
void FC mode_save_menu(u32 manager) {
    if(owner(manager) && inline_active()) CALL2(0x6e390,manager,0x507ec8);
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
    if(inline_active() || M(0)) {
        CALL1(0xc8190,manager);
        if(G(0xE576A0)==2) return; /* User cancelled the native exit dialog. */
    } else {
        rollback(); CALL2(0x6e450,manager,0x515660);
    }
    S(0)=S(2580)=S(2672)=S(2560)=S(2564)=S(2568)=M(0)=0;
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
        M(0)=0;
        if(S(2588)) CALL1(0x13ec90,S(2588));
        if(G(0xE576A4)==4 && S(24)==2) return (u32)m3_prep_menu;
        if(G(0xE576A4)==5) return (u32)m3_draft_menu;
        if(S(24)==4) { S(2680)=2; return (u32)team_menu; }
        return (u32)apartment;
    }
    return target;
}
void mode_load_error(void) {
    extern const u16 load_notice[];
    if(S(2672)) notice(S(2672),load_notice);
}

/* M3 draft entry. Native year/stage/round state is already serialized by
 * Franchise. The existing pointer-free career footer owns the prospect.
 * A zero-depth owned menu context is used only for native league processing;
 * the visible progress menu stays on the real manager's stack. No fabricated
 * standings, class generator, contract or pick is substituted. */
#define LEAGUE_MENU ((u32)(m3+3600))
void FC m3_boot_tick(u32 manager) {
    u32 stage=G(0xE576A4),week=G(0xE576B4),year=G(0xE576B8);
    if(!owner(manager) || M(0)!=1) return;
    if(stage==4 && year==1) {
        M(0)=2;
        CALL2(0x6e450,manager,(u32)entry_menu);
        mode_create(manager);
        return;
    }
    if(++M(4)>40 || year>1 || stage<1 || stage>9) goto failed;
    if(stage>=7 && week<G(0xE576B0)) CALL1(0x247d40,LEAGUE_MENU);
    else {
        if(stage==9) CALL2(0xc4d30,(u32)team(0),1);
        CALL1(0x2480b0,LEAGUE_MENU);
    }
    if(stage==G(0xE576A4) && week==G(0xE576B4) && year==G(0xE576B8)) goto failed;
    return;
failed:
    M(0)=3; notice(manager,draft_notice);
}

static const u8 m3_quotas[17]={3,1,1,6,5,2,2,3,2,3,4,3,2,4,4,4,4};
/* Include CAP as a 381st prospect, then exchange it with a same-position
 * selected record if needed. Both records and their original name/history
 * pointers survive. No generated prospect is removed or rerated, and no
 * shared name string is overwritten. Selection exactly matches the Senior
 * Bowl data tier's index rotation with seed 1. */
u32 FC m3_place(u32 manager) {
    u8 *p=(u8 *)S(2676),*q,*chosen=0,tmp[84];
    u32 counts[17]={0},i,j,pos,total=0,n,offset,k,one_pool;
    if(!owner(manager) || M(0)!=2 || S(2680)!=2 || !p || !player_bounds(p) ||
       G(0xE576A4)!=4 || G(0xE576B8)!=1 || G(0xE576B4)!=0 ||
       G(0xE576B0)!=1 || p[0x35]>=17 || (p[8]&0x34)!=4) return 0;
    n=W(ROOT,0); pos=p[0x35];
    /* The native CAP must have exactly one FA reference before conversion. */
    k=0;
    for(i=0;i<W(ROOT,0x38);i++) if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)p) k++;
    if(k!=1) return 0;
    counts[pos]=1;
    for(i=0,q=(u8 *)W(ROOT,4);i<n;i++,q+=84) if((q[8]&0x34)==0x14) {
        if(q[0x35]>=17) return 0;
        counts[q[0x35]]++; total++;
    }
    if(total<106 || total>=512) return 0;
    one_pool=counts[10]==0;
    for(i=0;i<17;i++) {
        k=m3_quotas[i];
        if(one_pool && i==10) k=0;
        if(one_pool && i==11) k+=m3_quotas[10];
        if(counts[i]<2*k) return 0;
    }
    offset=(1U^(pos*0x9e3779b9U))%counts[pos];
    for(i=0,j=0,q=(u8 *)W(ROOT,4);i<n;i++,q+=84)
        if(q[0x35]==pos && (q==p || (q[8]&0x34)==0x14) && j++==offset) { chosen=q; break; }
    if(!chosen) return 0;
    /* Scan membership before the two-record exchange, including all-star
     * aliases, reserve tails and the entire free-agent prefix. */
    for(i=0;i<W(ROOT,0x18);i++) {
        q=(u8 *)(W(ROOT,0x1c)+500*i);
        for(j=0;j<65;j++) if(W(q,j*4)==(u32)p || W(q,j*4)==(u32)chosen) return 0;
    }
    if(chosen!=p) for(i=0;i<W(ROOT,0x38);i++)
        if(W((u8 *)W(ROOT,0x3c),4*i)==(u32)chosen) return 0;
    CALL2(0x2425c0,(u32)ROOT+0x38,(u32)p);
    p[8]|=0x10;
    if(chosen!=p) {
        move_bytes(tmp,p,84); move_bytes(p,chosen,84); move_bytes(chosen,tmp,84);
    }
    capture(chosen); M(0)=0;
    return (u32)chosen;
}
u32 FC m3_creation_route(u32 manager) {
    S(2680)=2;
    if(M(0)==2) {
        if(m3_place(manager)) return (u32)m3_prep_menu;
        rollback(); notice(manager,draft_notice);
        return (u32)entry_menu;
    }
    return (u32)team_menu;
}
void FC m3_begin_draft(u32 manager) {
    if(!owner(manager) || !inline_active() || S(24)!=2 || !primary() || G(0xE576A4)!=4) return;
    CALL1(0x2480b0,LEAGUE_MENU);
    if(G(0xE576A4)==5) CALL2(0x6e2e0,manager,(u32)m3_draft_menu);
    else notice(manager,draft_notice);
}
void FC m3_draft_tick(u32 manager) {
    u32 option;
    if(!owner(manager) || !inline_active() || !primary() || G(0xE576A4)!=5) return;
    option=G(0xE60134); G(0xE60134)=1;
    if(!CALL0(0x325d00)) {
        CALL1(0x325b90,LEAGUE_MENU);
        CALL0(0x325a50);
    }
    if(CALL0(0x325d00)) {
        CALL1(0x2480b0,LEAGUE_MENU); /* full native cleanup, logs and stage 6 */
        if(G(0xE576A4)==6) CALL1(0x2480b0,LEAGUE_MENU);
        resolve_team();
        if(S(24)==3) {
            CALL1(0x13ec90,S(2588)); start_player();
            CALL2(0x6e2e0,manager,(u32)apartment);
        } else if(S(24)==4) {
            S(2680)=2; S(2684)=0;
            CALL2(0x6e2e0,manager,(u32)team_menu);
            notice(manager,m3_unsigned_text);
        }
    }
    G(0xE60134)=option;
}

/* M3 purchases. A quote captures the identity, value, balance and manager;
 * cancel, stale confirmation and replay consume it before any write. */
extern const u8 m3_fields[25],m3_caps[17][25];
extern const u16 *const m3_rating_names[25];
extern const u16 m3_upgrade_format[],m3_confirm_text[],m3_unavailable_text[];
static u32 m3_cost(u32 value) {
    return value<70?10:value<80?15:value<90?25:value<95?40:value<99?60:0;
}
static u32 m3_field_index(u32 field) {
    u32 i; for(i=0;i<25;i++) if(m3_fields[i]==field) return i;
    return 25;
}
u32 FC m3_upgrade_quote(u32 manager,u32 field) {
    u8 *p; u32 value,cost,i=m3_field_index(field);
    M(32)=0;
    if(!hub(manager) || S(24)!=3 || i>=25 || !(p=(u8 *)primary())) return 0;
    value=p[field]; cost=m3_cost(value);
    if(value>=m3_caps[state[149]][i] || !cost || S(64)<cost) return 0;
    M(36)=field; M(40)=value; M(44)=S(64); M(48)=S(28);
    move_bytes(m3+52,state+40,16); M(68)=manager; M(32)=(u32)p;
    return cost;
}
u32 FC m3_upgrade_commit(u32 manager,u32 answer) {
    u8 *p=(u8 *)M(32); u32 field=M(36),value=M(40),cost=m3_cost(value),i=m3_field_index(field);
    M(32)=0;
    if(answer!=1 || manager!=M(68) || !hub(manager) || S(24)!=3 || !p ||
       primary()!=(u32)p || S(28)!=M(48) || i>=25 || value>=m3_caps[state[149]][i] ||
       p[field]!=value || !cost || S(64)!=M(44) || S(64)<cost) return 0;
    for(i=0;i<16;i++) if(state[40+i]!=m3[52+i]) return 0;
    p[field]=(u8)(value+1); S(64)-=cost;
    return 1;
}
void FC m3_upgrade_open(u32 manager) {
    if(hub(manager) && primary()) { M(72)=0; M(32)=0; CALL2(0x6e390,manager,(u32)m3_upgrade_menu); }
}
void FC m3_upgrade_previous(u32 manager) { if(hub(manager)) { M(72)=(M(72)+24)%25; M(32)=0; } }
void FC m3_upgrade_next(u32 manager) { if(hub(manager)) { M(72)=(M(72)+1)%25; M(32)=0; } }
void FC m3_back(u32 manager) { if(hub(manager)) { M(32)=0; CALL1(0x6e400,manager); } }
void FC m3_upgrade_buy(u32 manager) {
    u32 answer;
    if(M(72)>=25 || !m3_upgrade_quote(manager,m3_fields[M(72)])) { notice(manager,m3_unavailable_text); return; }
    answer=CALL2(0x14e540,manager,(u32)m3_confirm_text);
    m3_upgrade_commit(manager,answer);
}
void FC m3_draw_upgrade(u32 manager) {
    u8 *p; u32 i=M(72),args[5],v;
    if(!hub(manager) || i>=25 || !(p=(u8 *)primary())) return;
    v=p[m3_fields[i]];
    args[0]=(u32)m3_rating_names[i]; args[1]=v; args[2]=m3_caps[state[149]][i];
    args[3]=v<args[2]?m3_cost(v):0; args[4]=S(64);
    ((void (FC *)(u8 *,u32,const u16 *,u32 *))0x49f00)(m3+2700,400,m3_upgrade_format,args);
    text((const u16 *)(m3+2700),0,320,380,0);
}
