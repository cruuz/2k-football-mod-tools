/* Sprite presentation engine. No heap allocation, FONT lookup, or mutable RX data.
 * Resource tables contain all layout/UV/glyph metrics. Native formatters retain
 * the game's clock, quarter, down/distance and score semantics. Franchise team
 * records are counted once at setup with the retail per-week counters. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef short s16;
typedef unsigned char u8;
#define V(a) (*(volatile u32 *)(a))
#define MAGIC 0x35525053u
#define FAST __attribute__((fastcall))
#define NOINLINE __attribute__((noinline))
typedef void (FAST *Formatter)(u16 *);
typedef u32 (FAST *Lookup)(u32,u32,const u16 *);
typedef u32 (FAST *Count)(u32,u32);
typedef void (FAST *Printf)(u16 *,const u16 *,const u32 *);
struct Glyph {u16 token[4];int width,height,advance,rise;s16 uv[8];};
struct Field {u32 source,vertex,capacity,glyphs,count,color,flags,visibility;int x,y,z,width,align,alt;};
struct Static {u32 vertex,tint,material,brand;};
struct Brand {u32 mode;s16 uv[16];}; /* NFL then MNF, one existing quad */
struct Header {u32 magic,revision,fields,field_offset,statics,static_offset,size,quads;};
/* 120 of the owner's 128 RW bytes. record[0] is home ([0xE5FE68]), record[1] away ([0xE5FE6C]).
 * sb (2026-09-24): the last down seen, the interim-label and TIMEOUT-tab timers (IEEE single bits,
 * seconds left; no float constant is ever loaded, so nothing lands in .rodata), the packed timeouts
 * left (home bits 0..7, away 8..15), the tab's side (1 away at the anchor, 2 home at the alternate) and the red
 * play-clock flag the frame's fields read. */
struct State {u32 scene,active,home,away,home_wing,away_wing,home_plate,away_plate,home_rim,away_rim,kick_phase,kicker;u16 record[2][12];
 u32 down,interim,timeouts,tab,tab_side,red;};
typedef union {u32 u;float f;} Bits;
#define INTERIM_SECONDS 0x40e00000u /* 7.0: ESPN's median "3rd Down" (52 in the full Broncos-Chiefs game, p25 5, p75 10) */
#define TAB_SECONDS 0x40800000u     /* 4.0: ESPN's TIMEOUT popups ran 2, 4 and 5 s in the same game */
#define ESPN_PLATE 0xff181719u      /* x plate cell ~0.9 = the measured black plate (22,21,23) */
#define PLAY_CLOCK_RED 0xffdd0038u  /* x white cell 246 = the measured red cell (213,0,54) */
struct Accent {u32 code,kind,wing,rim,plate;};

NOINLINE void FAST sprite_blank(u16 *out) {out[0]=0;}
static u8 *base(void) {
 u32 p=V(0xa95528);
 if (!p || V(p-256+0x60)!=MAGIC || V(p-256+0x64)!=16512) return (u8*)0;
 return (u8*)(p-256);
}
static struct Header *header(u8 *b) {return (struct Header*)(b+16512);}
static u32 material(u8 *b,u32 k) {
 /* Callers use logical 3..10 -> native 2,4,3,9,7,10,6,8.
  * Event records already carry the pointers for logical 0..2.
  * Packed nibbles keep the event repair inside the existing RX reservation. */
 k=(0x86a79342u>>((k-3)*4))&15;
 return V(b+256+0x20)+k*128;
}
static void color(u8 *b,u32 first,u32 c) {
 for(u32 j=0;j<4;j++) V(b+0x2d20+(first+j)*10)=c;
}
static u32 monday_night(void) {
 if(V(0xe576a0)!=2 || V(0xe60184)!=2)return 0;
 u32 week=V(0xe576b4),slot=V(0xe576bc);
 if(week>=22 || slot>=17)return 0;
 u8 *record=(u8*)(0xe57c40+(week*17+slot)*8);
 if(record[3]<1 || record[3]>12 || record[4]<1 || record[4]>31)return 0;
 /* D22AC is the current-record weekday SITE. The calendar owner detours it.
  * Both implementations take record in ECX and add 3 for month/day/year.
  * Calling 1C18B0 directly would bypass the extended calendar. */
 return ((u32 (FAST *)(const u8 *))0xd22ac)(record)==0;
}
/* vb3 (2026-09-23): a historic team (category 4: the 25th Anniversary moments' teams and Quick Game's historic
 * teams) keeps its franchise's art code at +0x10C ("10" for Packers '66), so it takes that franchise's panel.
 * Only created teams (category 2) keep the neutral panel. */
static u32 logo(u32 context) {
 u16 name[8];
 V(name)=0x00620073;V(name+2)=0x002d002d;V(name+4)=0x00300068;V(name+6)=0;
 u32 p=V(context+0x10c),kind=V(context+0x128);
 if(p && kind!=2) {
  u16 *s=(u16*)p;u32 tens=s[0]-'0',ones=s[1]-'0',code=tens*10+ones;
  if(tens<=3 && ones<=9 && !s[2] && (code<=30 || code==37)){name[2]=s[0];name[3]=s[1];}
 }
 Lookup find=(Lookup)0x449e0;
 u32 found=find(0xe614b8,0x52545854,name);
 if(!found && name[2]!='-') {name[2]=name[3]='-';found=find(0xe614b8,0x52545854,name);}
 return found;
}

static void accents(u8 *b,u32 context,u32 *wing,u32 *rim,u32 *plate) {
 struct Header *h=header(b);
 if(h->revision!=2)return;
 *wing=*rim=*plate=0xff303030;
 u32 *tail=(u32*)((u8*)h+h->size-12);
 if(h->size<12 || h->size>16384 || tail[0]!=0x35544e54 || tail[1]>52 ||
    tail[2]<16512+sizeof(struct Header) || tail[2]+tail[1]*sizeof(struct Accent)!=16512+h->size-12)return;
 u16 *code=(u16*)V(context+0x10c);
 if(!code || !code[0] || !code[1] || code[2])return;
 u32 key=(u32)code[0]|((u32)code[1]<<16),kind=V(context+0x128);
 /* vb3: the accent table has no historic rows; a historic team wears its franchise's (the NFL row, kind 0). */
 if(kind==4)kind=0;
 struct Accent *rows=(struct Accent*)(b+tail[2]);
 for(u32 i=0;i<tail[1];i++)if(rows[i].code==key && rows[i].kind==kind){
  *wing=rows[i].wing;*rim=rows[i].rim;*plate=rows[i].plate;return;
 }
}

/* Entering W-L(-T) of the two teams of a Franchise game, regular season only.
 * [0xE5FE68]/[0xE5FE6C] are the league records the fixture start staged (home,
 * away). Rows 0..weeks-1 of the schedule grid are the regular season: the weeks
 * byte is the Season row of the .rdata stage table (17 retail, 18 with the 2026
 * season length), so played playoff rows never count. C75A0/C7620/C76A0 are the
 * retail wins/losses/ties of one week. A team with no decided game shows nothing
 * (ESPN shows no record in week 1). Setup only; the update copies the text. */
NOINLINE void FAST records(struct State *s) {
 u32 weeks=*(volatile u8 *)0x5151c4;
 if(weeks>22)weeks=22;
 for(u32 side=0;side<2;side++){
  u32 team=V(0xe5fe68+side*4),r[3];u16 *t=s->record[side];t[0]=0;
  if((V(0xe576a0)^2)|((V(0xe5ff80)-6)>>1)|((V(0xe576a4)-8)>>1)|!team)continue;
  for(u32 k=0;k<3;k++){r[k]=0;for(u32 w=0;w<weeks;w++)r[k]+=((Count)(0xc75a0+k*0x80))(team,w);}
  if(r[0]|r[1]|r[2])((Printf)0x4a400)(t,(const u16 *)(r[2]?0xe68c34:0xe68c28),r);
 }
}

/* The team the bar marks: 1 away, 2 home, 0 none. [0xE60280] is the team in
 * possession; the kickoff and safety-kick builders set it to the KICKING team
 * (phases 2 and 1), and the dead-ball pass swaps it after the return. ESPN marks
 * the receiving team during a kick, so the kicker is captured when a kick phase
 * begins and its opponent is marked until the phase ends. Phase 0 (pregame, the
 * coin toss, the half) marks no one. */
NOINLINE u32 FAST possessor(struct State *s) {
 u32 phase=V(0xe602b4),team=V(0xe60280);
 if(phase-1<2){if(s->kick_phase!=phase){s->kick_phase=phase;s->kicker=team;}team=s->kicker^(0xe5fc20^0xe5fc60);}
 else s->kick_phase=0;
 if(!phase || phase>4)return 0;
 return team==0xe5fc60?1:team==0xe5fc20?2:0;
}

static u32 FAST element_visible(u32 record);
NOINLINE static u32 espn_mode(void);
NOINLINE static u32 timeouts_now(void);

NOINLINE void sprite_setup(struct State *s) {
 u8 *b=base();s->active=0;if(!b)return;
 struct Header *h=header(b);
 if(h->magic!=MAGIC || (h->revision!=1 && h->revision!=2) || h->fields>16 || h->statics>24 || h->quads>71)return;
 s->scene=(u32)b+256;s->active=1;
 s->home=logo(0xb30864);s->away=logo(0xb30a58);
 s->home_wing=s->home?V(s->home-4):0xff4a4e58;
 s->away_wing=s->away?V(s->away-4):0xff4a4e58;
 s->home_plate=s->home?V(s->home-8):0xff3a3f48;
 s->away_plate=s->away?V(s->away-8):0xff3a3f48;
 s->home_rim=0xff000000|(((s->home_wing&0xfefefe)>>1)+0x7f7f7f);
 s->away_rim=0xff000000|(((s->away_wing&0xfefefe)>>1)+0x7f7f7f);
 accents(b,0xb30864,&s->home_wing,&s->home_rim,&s->home_plate);
 accents(b,0xb30a58,&s->away_wing,&s->away_rim,&s->away_plate);
 V(material(b,5)+0x30)=s->home;V(material(b,8)+0x30)=s->away;
 /* Keep retail descriptor/slot words. Empty callbacks submit no bar glyphs. */
 for(u32 i=0;i<5;i++)V(0xa95884+i*40)=(u32)sprite_blank;
 V(0xa95924)=(u32)sprite_blank;
 V(0xa9594c)=V(0xa95984)=(u32)sprite_blank;
 V(0xa9596c)=V(0xa959a4)=0;
 V(0xa959cc)=V(0xa95a3c)=(u32)sprite_blank;
 /* The spare event material holds native hang-time text. */
 V(0xa95aec)=material(b,10);
 s->kick_phase=0;
 records(s);
 /* sb: hang time, ball on and FUMBLE keep their retail timing but draw no retail text. */
 V(0xa95aac)=V(0xa95b8c)=V(0xa95bfc)=(u32)sprite_blank;
 s->down=s->interim=s->tab=s->tab_side=s->red=0;s->timeouts=timeouts_now();
}

NOINLINE static u32 text(struct State *s,struct Field *f,u16 *out) {
 out[0]=0;
 u32 source=f->source,p;
 if(source<2){p=V(source?0xe5fc68:0xe5fc28);if(!p || V(p)>999)return 0;((Formatter)(source?0xfc070:0xfc050))(out);}
 else if(source<4){p=V(source==2?0xe5fc28:0xe5fc68);if(!p)return 0;u32 n=V(p+4);if(n>3)return 0;V(out)='0'+n;}
 else if(source==4){((Formatter)0xfc090)(out);}
 /* Retail splits at ceil(seconds)==600. FC100 deliberately returns empty
  * above 599.0; FC150 handles that complementary range. Positive IEEE bits
  * preserve order after the finite, nonnegative range guard above. */
 else if(source==5){
  p=V(0xe6028c);if(!p || V(p+16)>0x45610000u)return 0;((Formatter)(V(p+16)<=0x4415c000u?0xfc100:0xfc150))(out);
  /* sb: ESPN drops the minute under one minute (":54"); FC100 prints "0:54". */
  if((f->flags&2) && out[0]=='0' && out[1]==':'){u16 *q=out;do q[0]=q[1];while(*q++);}
 }
 else if(source==6){p=V(0xe60294);if(!p || V(p+16)>0x42c60000u || (V(p+24)&6))return 0;((Formatter)0xfbe30)(out);}
 else if(source==7){
  if(espn_mode()){V(out)='E'|('S'<<16);V(out+2)='P'|('N'<<16);out[4]=0;return 1;}
  if(!V(0xe602ec) || !V(0xe60280))return 0;
  ((Formatter)0xfc7d0)(out);
  /* sb: after a play ESPN shows the new down alone ("3rd Down") before the distance. */
  if((int)s->interim>0 && out[3]==' '){V(out+4)='D'|('o'<<16);V(out+6)='w'|('n'<<16);out[8]=0;}
 }
 /* Records (8 home, 9 away) are the setup text; their tabs (10, 11) are one token
  * for the text length; the arrow (12) returns 2 when it belongs over the home score. */
 else if(source<12){u16 *r=s->record[source&1];u32 n=0;while((out[n]=r[n]))n++;if(source>9){if(!n)return 0;V(out)='0'+n;}}
 else if(source==12){V(out)='^';return possessor(s);}
 /* sb: the TIMEOUT tab over the calling team's wing (1 away, 2 home). */
 else if(source==13){if((int)s->tab<=0)return 0;V(out)='T';return s->tab_side;}
 else return 0;
 if((f->flags&1) && out[0]=='0' && out[1] && !out[2]){out[0]=out[1];out[1]=0;}
 return 1;
}

/* Record origin is the parent-index word (A959C8 + index * 0x70).
 * This is FC360's binding/current-slide decision, including unordered x87. */
static u32 FAST element_visible(u32 record) {
 return V(record+0x58) && !(*(volatile float*)(record+0x3c)<=*(volatile float*)(record+0x2c));
}

/* sb: the plate shows ESPN's black wordmark plate whenever it carries no down: the kick and
 * point-after phases, pregame, the half and the overtime toss (FC7D0 prints "Kickoff", "Point After",
 * "Pregame"... there), and while a retail event ESPN never draws would show: hang time (A95AA8),
 * ball on (A95B88) or FUMBLE (A95BF8). FLAG (A95B18) keeps its own yellow plate. */
NOINLINE static u32 espn_mode(void) {
 return V(0xe602b4)!=4 || element_visible(0xa95aa8) || element_visible(0xa95b88) || element_visible(0xa95bf8);
}
NOINLINE static u32 timeouts_now(void) {
 u32 t=0;
 for(u32 side=0;side<2;side++){u32 p=V(side?0xe5fc68:0xe5fc28);t|=(p?V(p+4)&255:255)<<(side*8);}
 return t;
}

NOINLINE static void field(u8 *b,struct State *s,struct Field *f) {
 struct Glyph *tokens[16];u16 buffer[96];u32 count=0;int total=0;
 for(u32 j=0;j<f->capacity;j++)color(b,f->vertex+j*4,0);
 if(f->capacity>16 || f->vertex+f->capacity*4>286 || f->count>128)return;
 if(f->visibility && !V(f->visibility))return;
 /* Requests describe the next update, not the draw. In the compact layout
  * the retail events occupy the same plate as down-and-distance; suppress
  * underlying glyphs only while those elements actually draw (the plates
  * have translucent pixels). No request word participates in this decision. */
 if(f->source==7) {
  /* FLAG draws its own plate. Any other retail event puts the bar in the ESPN-plate mode, whose
   * wordmark does not follow the down element's slide (sb). */
  if(element_visible(0xa95b18))return;
  if(!espn_mode() && !element_visible(0xa959c8))return;
 }
 u32 side=text(s,f,buffer);
 if(!side)return;
 u16 *at=buffer;
 while(*at && at<buffer+80) {
  struct Glyph *glyph=(struct Glyph*)(b+f->glyphs),*match=(struct Glyph*)0;u32 length=0;
  for(u32 i=0;i<f->count;i++){
   u32 n=0;while(n<4 && glyph[i].token[n] && glyph[i].token[n]==at[n])n++;
   if(n && (n==4 || !glyph[i].token[n])){match=glyph+i;length=n;break;}
  }
  if(!match || count==f->capacity)return;
  tokens[count++]=match;total+=match->advance;at+=length;
 }
 if(!count || *at)return;
 total-=tokens[count-1]->advance-tokens[count-1]->width;
 if(total<=0)return;
 int width=total<f->width?total:f->width;
 int left=(side==2?f->alt:f->x)-(f->align==1?width/2:f->align==2?width:0),advance=0;
 for(u32 i=0;i<count;i++) {
  struct Glyph *g=tokens[i];u32 first=f->vertex+i*4;
  int x0=left+advance*width/total,x1=left+(advance+g->width)*width/total;
  int y0=f->y+g->rise,y1=y0-g->height;
  for(u32 j=0;j<4;j++) {
   s16 *pos=(s16*)(b+0x2660+(first+j)*6),*uv=(s16*)(b+0x2d20+(first+j)*10+4);
   pos[0]=(j&1)?x1:x0;pos[1]=(j&2)?y1:y0;pos[2]=f->z;
   uv[0]=g->uv[j*2];uv[1]=g->uv[j*2+1];
  }
  if(g->width && g->height)color(b,first,f->source==6 && s->red?0xffffffff:f->color);
  advance+=g->advance;
 }
}

/* sb B1: play calling keeps the 2026 bar up and draws no retail play-call bar. The retail play-call bar's draws
 * (0x8C450, 0x8CA00) run only while [0xB641B4] and [0xB641B0] are set; the build turns both draws off and points
 * the per-frame hide at 0x8BEA0 here, so the bar stays while that mode is on and replays and menus still hide it. */
NOINLINE void sprite_playcall_hide(void) {
 if(V(0xb641b4) && V(0xb641b0))return;
 ((void (*)(void))0xfc6b0)();
}
static u32 playcall_keep(void) {
 /* The mode is on and the build's draw guard is in place (0x8C465 reads jmp): without the guard, retail. */
 return V(0xb641b4) && V(0xb641b0) && *(volatile u8 *)0x8c465==0xe9;
}

/* dt is the frame time FC9C0 receives (IEEE single bits, sb). */
NOINLINE void sprite_update(struct State *s,u32 dt) {
 u8 *b=base();if(!b || !s->active || s->scene!=(u32)b+256)return;
 if(dt-1>=0x3f7fffffu)dt=0;
 /* sb: the interim label starts when the down steps to 2nd, 3rd or 4th in the same series. */
 u32 p=V(0xe602ec);
 if(p){u32 d=V(p+4);if(d!=s->down){s->interim=d>1 && d==s->down+1?INTERIM_SECONDS:0;s->down=d;}}
 /* sb: a side whose timeouts drop gets the TIMEOUT tab. The half's reset only rises. */
 u32 t=timeouts_now();
 if(t!=s->timeouts){
  for(u32 side=0;side<2;side++)if(((t>>(side*8))&255)<((s->timeouts>>(side*8))&255)){s->tab=TAB_SECONDS;s->tab_side=side?1:2;}
  s->timeouts=t;
 }
 Bits a,d;d.u=dt;
 if((int)s->interim>0){a.u=s->interim;a.f-=d.f;s->interim=a.u;}
 /* sb (lab run 2): the tab's 4 s count only while the bar draws ([0xA95524]); the play-call screen hides the
  * bar, so a timeout called there still shows its tab when the bar comes back. */
 if((int)s->tab>0 && V(0xa95524)){a.u=s->tab;a.f-=d.f;s->tab=a.u;}
 /* sb B1: play calling's entry hide (0xACAC3) cleared the draw gate; the bar stays up through play calling. */
 if(playcall_keep())V(0xa95524)=1;
 if(!V(0xa95520))return;
 struct Header *h=header(b);
 for(u32 k=3;k<10;k++) {
  u32 m=material(b,k);
  V(m+8)=(V(m+8)&~1u)|((k==5&&!s->home)||(k==8&&!s->away));
  V(m+24)=0xffffffff;
 }
 /* Event plates are logical 10, 2, 1, 0, outside the bar reset above.
  * Recompute every plate from the same binding/current-slide gate as text.
  * A request can end while its slide is still closing. */
 for(u32 record=0xa95aa8;record<0xa95c68;record+=0x70) {
  u32 m=V(record+0x44);
  /* sb: only FLAG keeps a plate; ESPN draws no hang-time, ball-on or FUMBLE plate. */
  if(m)V(m+8)=(V(m+8)&~1u)|(record!=0xa95b18 || !element_visible(record));
 }
 /* The plate takes the colour of the team the arrow marks, or ESPN's black with no down (sb). */
 u32 side=possessor(s),tint=espn_mode()?ESPN_PLATE:side==2?s->home_plate:side==1?s->away_plate:0xff3a3f48;
 /* sb: the play clock cell turns ESPN red at 5 seconds and under (displayed 5..0), white digits. */
 p=V(0xe60294);
 u32 red=s->red=V(0xa95a70) && p && V(p+16)<=0x40a00000u && !(V(p+24)&6);
 struct Static *statics=(struct Static*)(b+h->static_offset);
 for(u32 i=0;i<h->statics;i++){
  u32 source=statics[i].tint;
  if(source) {
   u32 c=source==1?s->home_wing:source==2?s->away_wing:source==4?s->home_rim:source==5?s->away_rim:source==6?(red?PLAY_CLOCK_RED:0xffffffff):tint;
   color(b,statics[i].vertex,c);
  }
  if(statics[i].brand) {
   struct Brand *mark=(struct Brand*)(b+statics[i].brand);
   color(b,statics[i].vertex,mark->mode==2?0:0xffffffff);
   u32 variant=mark->mode==1 || (mark->mode==0 && monday_night());
   for(u32 j=0;j<4;j++) {
    s16 *uv=(s16*)(b+0x2d20+(statics[i].vertex+j)*10+4);
    uv[0]=mark->uv[variant*8+j*2];uv[1]=mark->uv[variant*8+j*2+1];
   }
  }
 }
 struct Field *fields=(struct Field*)(b+h->field_offset);
 for(u32 i=0;i<h->fields;i++)field(b,s,fields+i);
}
