/* MyCareer Career Home (job ui1). EXPERIMENTAL / UNWITNESSED.
 * Runs from its own preloaded section (nfl2k5_my_career_home). It changes no
 * MyCareer code: the Apartment descriptor's title, rows and handler point here
 * (MyCareer template data), every action except the two screen openers is an
 * existing MyCareer row action, and MyCareer's B/quit/autosave/route logic
 * still sees the same Apartment descriptor. Functions marked FC use the retail
 * ECX/EDX fastcall convention. All mutable state is on the stack.
 *
 * Drawing (event 7, after the native list draw), in HUD text space 640x448:
 *  - text: retail 6BC30 (centre x, baseline y), as every MyCareer screen;
 *  - panels: the retail immediate path the text itself uses (2D2A0 begin,
 *    2CBE0 colour, 2CB90 UV, 2CA70 vertex, 2CA00 end) with an aligned stack
 *    copy of a loaded font's material (the player star's method). A null
 *    texture gives flat or gradient colour; a texture found by name in the
 *    resident front-end collections gives full-colour art. Nothing is
 *    loaded or allocated; a missing font or texture skips that piece.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FC __attribute__((fastcall))
#define SC __attribute__((stdcall))
#define NI __attribute__((noinline))
#define W(p,n) (*(u32 *)((u8 *)(p)+(n)))
#define G(n) (*(u32 *)(n))
extern u8 state[4096];
#define S(n) W(state,n)
#define FONT(slot) G(0xa90ecc+4*(slot))

/* MyCareer (same build; resolved by name at install). */
extern u8 apartment[], hub_rows[];
extern u32 inline_active(void), primary(void), mode_next_fixture(void);
extern const u16 fixture_text[], watch_text[], m3_calendar_format[];
/* This owner's tables (built by nfl2k5_my_career_home.code_for). */
extern u8 home_classic[], home_options[], home_schedule[];
extern const u16 home_text_next[], home_text_season[], home_text_overall[], home_text_xp[];
extern const u16 home_text_starter[], home_text_backup[], home_text_none[];
extern const u16 home_text_options_note[], home_fmt_matchup[], home_tex_ghost[];
extern const u16 *const home_photo_names[17];
/* Schedule screen (job mcs). */
extern const u16 home_text_bye[], home_text_tbd[], home_text_nogame[], home_text_now[], home_text_pre[];
extern const u16 home_fmt_home[], home_fmt_away[], home_fmt_date[];

#define CALL1(a,x) ({ u32 cx_=(u32)(x),ax_; __asm__ volatile("call %c2" : "=a"(ax_), "+c"(cx_) : "i"(a) : "edx", "memory", "cc", "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"); ax_; })
#define CALL2(a,x,y) ({ u32 cx_=(u32)(x),dx_=(u32)(y),ax_; \
 __asm__ volatile("call %c3" : "=a"(ax_), "+c"(cx_), "+d"(dx_) : "i"(a) \
 : "memory", "cc", "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"); ax_; })

static NI u32 top(u32 manager) { return W(manager,8*W(manager,0x100)); }
/* MyCareer's hub(): the owning manager, a live career and the Apartment
 * (Career Home) somewhere on the stack. */
static NI u32 hub(u32 manager) {
    u32 i,n;
    if(!manager || S(2672)!=manager || (n=W(manager,0x100))>=32 || !inline_active()) return 0;
    for(i=0;i<=n;i++) if(W(manager,8*i)==(u32)apartment) return 1;
    return 0;
}
void FC home_options_open(u32 manager) {
    if(hub(manager) && top(manager)==(u32)apartment) CALL2(0x6e390,manager,(u32)home_options);
}
void FC home_classic_open(u32 manager) {
    if(hub(manager)) CALL2(0x6e390,manager,(u32)home_classic);
}

/* ---- text ---------------------------------------------------------------- */
/* Retail text: 6BC30(text, 0, x, y, z, 240, 0, 0, font, ARGB); x is the line
 * centre and y its baseline (alignment 3/2 inside 6BC30). */
static NI void text(const u16 *s,float x,float y,u32 font,u32 tint) {
    if(FONT(font)) ((void (FC *)(const u16 *,u32,float,float,float,float,u32,u32,u32,u32))0x6bc30)
        (s,0,x,y,20,240,0,0,FONT(font),tint);
}
/* The native width (0x49410: sum of glyph advances); 0 without the font. */
static NI float width(const u16 *s,u32 font) {
    return FONT(font)?(float)((u32 (FC *)(u32,const u16 *))0x49410)(FONT(font),s):0;
}
/* Integer HUD coordinates from here on (exact in float; the conversion happens once, inside). */
static NI void text_left(const u16 *s,int x,int y,u32 font,u32 tint) { text(s,(float)x+width(s,font)/2,(float)y,font,tint); }
static NI void text_right(const u16 *s,int x,int y,u32 font,u32 tint) { text(s,(float)x-width(s,font)/2,(float)y,font,tint); }
static NI u16 *put(u16 *out,const u16 *s,u32 n) { while(n-- && s && *s) *out++=*s++; *out=0; return out; }
static NI u16 *ascii(u16 *out,const char *s) { while(*s) *out++=(u8)*s++; *out=0; return out; }
static NI u16 *number(u16 *out,int value) {
    char d[12]; u32 n=0,v;
    if(value<0) { *out++='-'; v=0U-(u32)value; } else v=(u32)value;
    do { d[n++]=(char)('0'+v%10); v/=10; } while(v);
    while(n) *out++=(u16)d[--n];
    *out=0; return out;
}
static NI void format(u16 *out,u32 size,const u16 *f,u32 *args) {
    ((void (FC *)(u16 *,u32,const u16 *,u32 *))0x49f00)(out,size,f,args);
}

/* ---- quads --------------------------------------------------------------- */
typedef struct { float x,y,z,w; } vec4;
/* One textured or flat quad, corners TL TR BL BR (a 4-vertex strip). */
static NI void quad(int x0,int y0,int x1,int y1,u32 c0,u32 c1,u32 c2,u32 c3,u32 texture) {
    u8 material[128] __attribute__((aligned(16)));
    vec4 v; u32 i; const u8 *font=(const u8 *)FONT(0);
    if(!font) return;
    /* The loaded font's material: its registered draw key (+4), blend and
     * depth state. +0x30 is the texture (0 = untextured). */
    for(i=0;i<128;i++) material[i]=font[0x40+i];
    W(material,0x30)=texture;
    ((void (FC *)(u32,u32,u32,const u8 *,u32))0x2d2a0)(0,0,6,material,0);
    v.z=20; v.w=1;
    CALL1(0x2cbe0,c0); ((void (SC *)(float,float))0x2cb90)(0,0); v.x=x0; v.y=y0; CALL1(0x2ca70,&v);
    CALL1(0x2cbe0,c1); ((void (SC *)(float,float))0x2cb90)(1,0); v.x=x1; CALL1(0x2ca70,&v);
    CALL1(0x2cbe0,c2); ((void (SC *)(float,float))0x2cb90)(0,1); v.x=x0; v.y=y1; CALL1(0x2ca70,&v);
    CALL1(0x2cbe0,c3); ((void (SC *)(float,float))0x2cb90)(1,1); v.x=x1; CALL1(0x2ca70,&v);
    ((void (*)(void))0x2ca00)();
}
static NI void box(int x0,int y0,int x1,int y1,u32 c) { quad(x0,y0,x1,y1,c,c,c,c,0); }
/* A texture registered under this name in any loaded collection, else 0. */
static NI u32 texture(const u16 *name) {
    return name?((u32 (FC *)(u32,u32,const u16 *))0x449e0)(0,0x52545854,name):0;
}
static NI u32 alpha(u32 c,u32 a) { return (c&0xffffff)|(a<<24); }

static NI void classic_lines(void) {
    u16 line[160]; u32 slot=mode_next_fixture(),args[6];
    const u8 *p=(const u8 *)(0xE57C40+8*slot);
    if(slot>=374) { text(watch_text,320,432,0,0xffffffff); return; }
    args[0]=W(G(0xE5786C+4*p[2]),0x104);
    args[1]=W(G(0xE5786C+4*p[1]),0x104); args[2]=(u32)watch_text;
    format(line,314,fixture_text,args);
    text(line,320,432,0,0xffffffff);
    args[0]=slot/17+1; args[1]=p[3]; args[2]=p[4];
    args[3]=2000+(u32)p[5]; args[4]=p[6]; args[5]=p[7];
    format(line,314,m3_calendar_format,args);
    text(line,320,404,0,0xffffffff);
}

static NI int stat(u8 *p,u32 selector) {
    /* Bank 11: this season (season history plus a live game), the bank the
     * Player Card reads. CB240 returns the value on the x87 stack. */
    return (int)((float (FC *)(u8 *,u32,u32))0xCB240)(p,selector,11);
}

/* Panel geometry (HUD text space). Calibrated on Noah's 10/16 Apartment frame
 * (f_0166): native rows are left-aligned at x 41 with baselines 97 + 42k and a
 * selected label's cursor box can reach x ~280; the title bar ends at y ~72; the
 * grey bottom plate starts near y 368. The panel stays in x 290..620, y 88..306. */
#define L 290
#define R 620

static NI void stat_line(u16 *o,u8 *p,u32 pos) {
    if(pos==0) {
        o=number(o,stat(p,4)); *o++='/'; o=number(o,stat(p,35)); o=ascii(o,"  ");
        o=number(o,stat(p,76)); o=ascii(o," YDS  "); o=number(o,stat(p,64)); o=ascii(o," TD  ");
        o=number(o,stat(p,22)); ascii(o," INT");
    } else if(pos==7 || pos==8) {
        o=number(o,stat(p,3)); o=ascii(o," CAR  "); o=number(o,stat(p,80));
        o=ascii(o," YDS  "); o=number(o,stat(p,63)); ascii(o," TD");
    } else if(pos==3 || pos==9) {
        o=number(o,stat(p,46)); o=ascii(o," REC  "); o=number(o,stat(p,79));
        o=ascii(o," YDS  "); o=number(o,stat(p,62)); ascii(o," TD");
    } else if(pos==1) {
        int made=0,tried=0,i;
        for(i=0;i<4;i++) { made+=stat(p,173+i); tried+=stat(p,169+i); }
        o=ascii(o,"FG "); o=number(o,made); *o++='/'; o=number(o,tried);
        o=ascii(o,"  XP "); o=number(o,stat(p,88)); *o++='/'; number(o,stat(p,89));
    } else if(pos==2) {
        o=number(o,stat(p,43)); o=ascii(o," PUNTS  "); o=number(o,stat(p,78)); ascii(o," YDS");
    } else if(pos>=12 && pos<=14) {
        o=number(o,stat(p,99)); ascii(o," GAMES");
    } else {
        int sacks=stat(p,47);
        o=number(o,stat(p,50)); o=ascii(o," TKL  "); o=number(o,sacks/2);
        if(sacks&1) o=ascii(o,".5");
        o=ascii(o," SACK  "); o=number(o,stat(p,23)); ascii(o," INT");
    }
}
/* The larger font when the line fits, else the smaller one. */
static NI void fit_left(const u16 *s,int x,int y,int room,u32 big,u32 small,u32 tint) {
    text_left(s,x,y,width(s,big)>(float)room?small:big,tint);
}
static NI void chip(int x0,int x1,const u16 *value,const u16 *caption,u32 accent) {
    float x=((float)x0+(float)x1)/2;
    box(x0,156,x1,200,0xc0101820); box(x0,156,x0+3,200,accent);
    text(value,x,182,1,0xffffffff);
    text(caption,x,196,3,0xffc8c8c8);
}

void FC home_panel(u32 manager) {
    u16 line[96],value[16],*o; u8 *p,*t; u32 slot,args[6],pos,c1,c2,primary_c,second_c,tx,x,accent,caption;
    (void)manager;
    if(!(p=(u8 *)primary())) return;
    t=(u8 *)S(2588);
    pos=p[0x35];
    /* Team colours from the retail accessors (asset-code table at 4E7FE0);
     * the same fallbacks as retail when there is no club. */
    primary_c=t?CALL1(0x68d70,t):0xff0065e6;
    second_c=t?CALL1(0x68dc0,t):0xff00a0ff;
    accent=alpha(primary_c,0xff);
    caption=alpha(second_c|0x404040,0xff);

    /* Header card: team gradient, helmet watermark, position photo. */
    quad(L,88,R,146,alpha(primary_c,0xf0),alpha(second_c,0xf0),alpha(primary_c,0xf0),
         alpha(second_c,0xf0),0);
    box(L,146,R,149,alpha(second_c,0xff));
    if((tx=texture(home_tex_ghost))) quad(R-70,86,R-6,146,0x50ffffff,0x50ffffff,0x50ffffff,0x50ffffff,tx);
    x=L+8;
    if(pos<17 && (tx=texture(home_photo_names[pos]))) {
        quad(L+4,92,L+54,142,0xffffffff,0xffffffff,0xffffffff,0xffffffff,tx);
        x=L+62;
    }
    o=line;
    if(*(u16 *)W(p,16)) { *o++=*(u16 *)W(p,16); *o++='.'; *o++=' '; }
    put(o,(const u16 *)W(p,20),16);
    fit_left(line,(int)x,118,R-6-(int)x,1,0,0xffffffff);
    o=put(line,(const u16 *)G(0x4F26D0+4*pos),4);
    if(t) { o=ascii(o,"  "); o=put(o,(const u16 *)W(t,0x138),20); *o++=' '; put(o,(const u16 *)W(t,0x104),20); }
    fit_left(line,(int)x,138,R-6-(int)x,3,8,0xffffffff);

    /* Three chips: overall, XP, depth chart spot. Depth: the rank in the
     * first native chain (start_player's rule); a starter has rank 0 in
     * either chain. */
    number(value,(int)CALL2(0x246d90,p,0));
    chip(L,L+105,value,home_text_overall,accent);
    number(value,(int)S(64));
    chip(L+112,L+217,value,home_text_xp,accent);
    c1=(p[41]>>2)&7; c2=(p[41]>>5)&7;
    o=put(value,(const u16 *)G(0x4F26D0+4*pos),4);
    number(o,(int)c1+1);
    chip(L+224,R,value,(!c1 || !c2)?home_text_starter:home_text_backup,accent);

    /* Next game card. */
    box(L,206,R,260,0xc0101820); box(L,206,L+3,260,alpha(second_c,0xff));
    text_left(home_text_next,L+12,221,3,caption);
    slot=mode_next_fixture();
    if(slot<374) {
        const u8 *f=(const u8 *)(0xE57C40+8*slot);
        args[0]=W(G(0xE5786C+4*f[2]),0x104);
        args[1]=W(G(0xE5786C+4*f[1]),0x104);
        format(line,192,home_fmt_matchup,args);
        fit_left(line,L+12,240,R-L-18,0,3,0xffffffff);
        args[0]=slot/17+1; args[1]=f[3]; args[2]=f[4];
        args[3]=2000+(u32)f[5]; args[4]=f[6]; args[5]=f[7];
        format(line,192,m3_calendar_format,args);
        text_left(line,L+12,255,3,0xffc8c8c8);
    } else text_left(home_text_none,L+12,240,0,0xffffffff);

    /* This season. */
    box(L,266,R,306,0xc0101820); box(L,266,L+3,306,alpha(second_c,0xff));
    text_left(home_text_season,L+12,281,3,caption);
    stat_line(line,p,pos);
    fit_left(line,L+12,299,R-L-18,0,3,0xffffffff);
}

/* ---- schedule (job mcs, Noah 2026-10-18) ---------------------------------- */
/* The player's club's season straight from the league grid MyCareer already
 * plays from (0xE57C40: 22 rows of 17 eight-byte cells, [state][home][away]
 * [month][day][year-2000][hour][minute], state 3 played, 7 ends the row) and
 * the native cell scores (C5110 home, C5150 away: the quarter bytes summed).
 * The rows are the regular weeks of this image's stage table (Season row
 * byte +4: 17 retail, 18 with the 2026 season), then Wild Card, Divisional,
 * Conference and Super Bowl. The native list owns the week labels, the cursor
 * and the scrolling; the cards follow its first visible row (0xC8E1CC, the
 * value its row draw at 2C8730 used this frame). Read only. */
#define WEEKS (*(const u8 *)0x5151C4)
#define VISIBLE 7
static NI u32 schedule_rows(void) { u32 n=WEEKS+4u; return n>22?22:n; }
/* The row of the next career fixture, else the league week, in range. */
static NI u32 schedule_now(void) {
    u32 slot=mode_next_fixture(),last=schedule_rows()-1,row=slot<374?slot/17:G(0xE576B4);
    return row<last?row:last;
}
void FC home_schedule_open(u32 manager) {
    if(!hub(manager) || top(manager)!=(u32)apartment) return;
    CALL2(0x6e390,manager,(u32)home_schedule);
    /* The cursor starts on this week (the native list keeps it in view). */
    if(top(manager)==(u32)home_schedule) W(manager,8*W(manager,0x100)+4)=schedule_now();
}
/* A on a week: nothing (B goes back natively). */
void FC home_schedule_row(u32 manager) { (void)manager; }

static NI void schedule_draw(void) {
    u16 line[64],*o; u32 args[5],row,slot,k,club=S(56),rows=schedule_rows(),now=schedule_now();
    u32 first=G(0xC8E1CC),won=0,lost=0,tied=0,c1=0xff0065e6,c2=0xff00a0ff; u8 *t=(u8 *)S(2588);
    if(t) { c1=CALL1(0x68d70,t); c2=CALL1(0x68dc0,t); }
    if(first+VISIBLE>rows) first=rows>VISIBLE?rows-VISIBLE:0;
    for(row=0;row<rows;row++) {
        const u8 *f=0,*c=(const u8 *)(0xE57C40+136*row); u32 games=0,mine=0,theirs=0,played=0,accent;
        int y=72+42*(int)(row-first);
        for(slot=0;slot<17 && c[0]!=7;slot++,c+=8) {
            games++;
            if(club<32 && (c[1]==club || c[2]==club)) {
                f=c;
                if(c[0]==3) {
                    u32 home=CALL2(0xc5110,row,slot),away=CALL2(0xc5150,row,slot);
                    played=1; mine=c[1]==club?home:away; theirs=c[1]==club?away:home;
                    if(row<WEEKS) { if(mine>theirs) won++; else if(mine<theirs) lost++; else tied++; }
                }
            }
        }
        if(row<first || row>=first+VISIBLE) continue;
        /* This week's card: the club's primary colour, darkening to the right so the white, grey and yellow
         * text reads on every club (the native cursor marks the selected week). */
        if(row==now) quad(L,y,R-10,y+34,alpha(c1,0xf0),alpha(c1>>1&0x7f7f7f,0xf0),alpha(c1,0xf0),alpha(c1>>1&0x7f7f7f,0xf0),0);
        else box(L,y,R-10,y+34,0xc0101820);
        accent=!played?alpha(c2,0xff):mine>theirs?0xff30c050:mine<theirs?0xffe03838:0xffc8c8c8;
        box(L,y,L+3,y+34,accent);
        if(!f) {
            text_left(!games?home_text_tbd:row<WEEKS?home_text_bye:home_text_nogame,L+12,y+23,0,0xffc8c8c8);
            continue;
        }
        k=f[1]==club?f[2]:f[1];
        args[0]=W(G(0xE5786C+4*k),0x104);
        format(line,sizeof line,f[1]==club?home_fmt_home:home_fmt_away,args);
        fit_left(line,L+12,y+16,190,0,3,0xffffffff);
        if(played) {
            o=ascii(line,mine>theirs?"W ":mine<theirs?"L ":"T ");
            o=number(o,(int)mine); *o++='-'; number(o,(int)theirs);
            text_right(line,R-20,y+16,0,accent);
        } else if(row==now) text_right(home_text_now,R-20,y+16,3,0xffffff00);
        args[0]=f[3]; args[1]=f[4]; args[2]=2000+(u32)f[5]; args[3]=f[6]; args[4]=f[7];
        format(line,sizeof line,home_fmt_date,args);
        text_left(line,L+12,y+30,3,0xffc8c8c8);
        /* A preseason grid (stage 7) holds the preseason games in the first rows. */
        if(G(0xE576A4)==7) text_right(home_text_pre,R-20,y+30,3,0xffc8c8c8);
    }
    /* Scroll bar when the season does not fit. */
    if(rows>VISIBLE) {
        box(R-7,72,R-4,358,0x60ffffff);
        box(R-7,72+286*first/rows,R-4,72+286*(first+VISIBLE)/rows,0xffffffff);
    }
    /* Club and regular-season record, then the way back. */
    o=line;
    if(t) { o=put(o,(const u16 *)W(t,0x138),20); *o++=' '; o=put(o,(const u16 *)W(t,0x104),20); *o++=' '; *o++=' '; }
    o=number(o,(int)won); *o++='-'; o=number(o,(int)lost);
    if(tied) { *o++='-'; number(o,(int)tied); }
    text(line,320,404,0,0xffffffff);
    text(home_text_options_note,320,432,0,0xffffffff);
}

/* Event 7 (draw) for the four Career Home descriptors. MyCareer's row tint
 * hook (mode_row_text) tints the selected row only while the top descriptor's
 * handler is MyCareer's, so the native draw runs with that handler and this
 * one is restored before anything else can read it (home.S). */
void FC home_draw(u32 manager) {
    u32 d=top(manager);
    if(!hub(manager)) return;
    if(d==(u32)apartment) home_panel(manager);
    else if(d==(u32)home_classic) classic_lines();
    else if(d==(u32)home_options) text(home_text_options_note,320,404,0,0xffffffff);
    else if(d==(u32)home_schedule) schedule_draw();
}
