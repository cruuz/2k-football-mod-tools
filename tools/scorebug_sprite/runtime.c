/* Sprite presentation engine. No heap allocation, FONT lookup, or mutable RX data.
 * Resource tables contain all layout/UV/glyph metrics. Native formatters retain
 * the game's clock, quarter, down/distance and score semantics. */
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
struct Glyph {u16 token[4];int width,height,advance,rise;s16 uv[8];};
struct Field {u32 source,vertex,capacity,glyphs,count,color,flags,visibility;int x,y,z,width,align,unused;};
struct Static {u32 vertex,tint,material,brand;};
struct Brand {u32 mode;s16 uv[16];}; /* NFL then MNF, one existing quad */
struct Header {u32 magic,revision,fields,field_offset,statics,static_offset,size,quads;};
struct State {u32 scene,active,home,away,home_wing,away_wing,home_plate,away_plate,home_rim,away_rim;};
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
static u32 logo(u32 context) {
 u16 name[8];
 V(name)=0x00620073;V(name+2)=0x002d002d;V(name+4)=0x00300068;V(name+6)=0;
 u32 p=V(context+0x10c),kind=V(context+0x128);
 if(p && kind!=2 && kind!=4) {
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
 struct Accent *rows=(struct Accent*)(b+tail[2]);
 for(u32 i=0;i<tail[1];i++)if(rows[i].code==key && rows[i].kind==kind){
  *wing=rows[i].wing;*rim=rows[i].rim;*plate=rows[i].plate;return;
 }
}

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
}

static u32 text(struct Field *f,u16 *out) {
 out[0]=0;
 u32 source=f->source,p;
 if(source<2){p=V(source?0xe5fc68:0xe5fc28);if(!p || V(p)>999)return 0;((Formatter)(source?0xfc070:0xfc050))(out);}
 else if(source<4){p=V(source==2?0xe5fc28:0xe5fc68);if(!p)return 0;u32 n=V(p+4);if(n>3)return 0;for(u32 j=0;j<n;j++)out[j]='~';out[n]=0;}
 else if(source==4){((Formatter)0xfc090)(out);}
 else if(source==5){p=V(0xe6028c);if(!p || V(p+16)>0x45610000u)return 0;((Formatter)0xfc100)(out);}
 else if(source==6){p=V(0xe60294);if(!p || V(p+16)>0x42c60000u || (V(p+24)&6))return 0;((Formatter)0xfbe30)(out);}
 else if(source==7){if(!V(0xe602ec) || !V(0xe60280))return 0;((Formatter)0xfc7d0)(out);}
 else return 0;
 if((f->flags&1) && out[0]=='0' && out[1] && !out[2]){out[0]=out[1];out[1]=0;}
 return 1;
}

/* Record origin is the parent-index word (A959C8 + index * 0x70).
 * This is FC360's binding/current-slide decision, including unordered x87. */
static u32 FAST element_visible(u32 record) {
 return V(record+0x58) && !(*(volatile float*)(record+0x3c)<=*(volatile float*)(record+0x2c));
}

static void field(u8 *b,struct Field *f) {
 struct Glyph *tokens[16];u16 buffer[96];u32 count=0;int total=0;
 for(u32 j=0;j<f->capacity;j++)color(b,f->vertex+j*4,0);
 if(f->capacity>16 || f->vertex+f->capacity*4>286 || f->count>128)return;
 if(f->visibility && !V(f->visibility))return;
 /* Requests describe the next update, not the draw. In the compact layout
  * the retail events occupy the same plate as down-and-distance; suppress
  * underlying glyphs only while those elements actually draw (the plates
  * have translucent pixels). No request word participates in this decision. */
 if(f->source==7) {
  if(!element_visible(0xa959c8))return;
  for(u32 record=0xa95aa8;record<0xa95c68;record+=0x70)
   if(element_visible(record))return;
 }
 if(!text(f,buffer))return;
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
 int left=f->x-(f->align==1?width/2:f->align==2?width:0),advance=0;
 for(u32 i=0;i<count;i++) {
  struct Glyph *g=tokens[i];u32 first=f->vertex+i*4;
  int x0=left+advance*width/total,x1=left+(advance+g->width)*width/total;
  int y0=f->y+g->rise,y1=y0-g->height;
  for(u32 j=0;j<4;j++) {
   s16 *pos=(s16*)(b+0x2660+(first+j)*6),*uv=(s16*)(b+0x2d20+(first+j)*10+4);
   pos[0]=(j&1)?x1:x0;pos[1]=(j&2)?y1:y0;pos[2]=f->z;
   uv[0]=g->uv[j*2];uv[1]=g->uv[j*2+1];
  }
  if(g->width && g->height)color(b,first,f->color);
  advance+=g->advance;
 }
}

NOINLINE void sprite_update(struct State *s) {
 u8 *b=base();if(!b || !s->active || s->scene!=(u32)b+256 || !V(0xa95520))return;
 struct Header *h=header(b);
 for(u32 k=3;k<10;k++){u32 m=material(b,k);V(m+8)&=~1u;V(m+24)=0xffffffff;}
 /* Event plates are logical 10, 2, 1, 0, outside the bar reset above.
  * Recompute every plate from the same binding/current-slide gate as text.
  * A request can end while its slide is still closing. */
 for(u32 record=0xa95aa8;record<0xa95c68;record+=0x70) {
  u32 m=V(record+0x44);
  V(m+8)=(V(m+8)&~1u)|!element_visible(record);
 }
 if(!s->home)V(material(b,5)+8)|=1;
 if(!s->away)V(material(b,8)+8)|=1;
 u32 p=V(0xe60280),tint=0xff3a3f48;
 if(p==0xe5fc20 || p==V(0xe5fc28))tint=s->home_plate;
 if(p==0xe5fc60 || p==V(0xe5fc68))tint=s->away_plate;
 struct Static *statics=(struct Static*)(b+h->static_offset);
 for(u32 i=0;i<h->statics;i++){
  u32 source=statics[i].tint;
  if(source) {
   u32 c=source==1?s->home_wing:source==2?s->away_wing:source==4?s->home_rim:source==5?s->away_rim:tint;
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
 for(u32 i=0;i<h->fields;i++)field(b,fields+i);
}
