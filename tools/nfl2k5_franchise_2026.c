/* Original freestanding i386 rule kernel. EXPERIMENTAL / UNWITNESSED.
 * No retail hooks call this code. Input ownership/identity is a caller contract;
 * see the report's hard gates before connecting a game or save callback.
 * All mutations preflight before stores. External dependencies: none.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define FC __attribute__((fastcall))
#define PACK __attribute__((packed))
#define EMPTY 65535
#define NPLAY 4096
#define ELIGIBLE 1
#define CHARGED 2
#define PRACTICE 4
#define EXPIRED 8
#define CUTDOWN 16
#define LEGACY 32
struct PACK Team {u16 last; u8 games,used,cut,qualified; u16 game,a,b,day,reserved;};
struct PACK IR {u16 player; u8 games,flags; u16 expiry,day;};
struct PACK State {u32 magic,version; u16 season,players; u32 epoch; u8 reserved[16];
 struct Team teams[32]; u8 history[2048]; struct IR ir[160]; u8 tail[224];};
struct Request {u32 op,team,player,day,key,flags,a,b,active,reserves;};
extern struct State workspace;
typedef char size_check[sizeof(struct State)==4096?1:-1];
static void zero(void *p,u32 n) {u8 *q=p; while(n--) *q++=0;}
static u32 hist(struct State *s,u32 p) {return (s->history[p/2]>>((p&1)*4))&15;}
static void put_hist(struct State *s,u32 p,u32 v) {
 u32 shift=(p&1)*4; s->history[p/2]=(s->history[p/2]&~(15<<shift))|(v<<shift);
}
static void init(struct State *s,u32 season,u32 players,u32 epoch) {
 u32 i; zero(s,sizeof(*s)); s->magic=0x4b363246; s->version=1;
 s->season=season; s->players=players; s->epoch=epoch;
 for(i=0;i<32;i++) s->teams[i].last=s->teams[i].game=s->teams[i].a=s->teams[i].b=EMPTY;
 for(i=0;i<160;i++) s->ir[i].player=EMPTY;
}
static int valid(struct State *s) {
 u32 i,j,p,empty,f,charged,cut; struct Team *t; struct IR *e;
 if(!s || s->magic!=0x4b363246 || s->version!=1 || s->season<2000 || s->season>2255 || !s->players || s->players>NPLAY) return 0;
 for(i=0;i<16;i++) if(s->reserved[i]) return 0;
 for(i=0;i<224;i++) if(s->tail[i]) return 0;
 for(i=0;i<NPLAY;i++) {p=hist(s,i); if((p>>2)>2 || (i>=s->players && p)) return 0;}
 for(i=0;i<32;i++) {
  t=s->teams+i;
  if(t->games>31 || t->qualified>1 || t->used>8+2*t->qualified || t->cut>2 || t->cut>t->used || t->day>511 || t->reserved) return 0;
  if((t->last==EMPTY)!=(t->games==0)) return 0;
  if(t->game!=EMPTY && t->last!=EMPTY && t->game<=t->last) return 0;
  if((t->game==EMPTY && (t->a!=EMPTY || t->b!=EMPTY)) || (t->a==EMPTY && t->b!=EMPTY)) return 0;
  for(j=0;j<2;j++) {
   p=j?t->b:t->a;
   if(p==EMPTY) continue;
   if(p>=s->players || (j && p==t->a)) return 0;
   for(f=0;f<i;f++) if(s->teams[f].a==p || s->teams[f].b==p) return 0;
  }
  empty=charged=cut=0;
  for(j=0;j<5;j++) {
   e=s->ir+i*5+j; f=e->flags;
   if(e->player==EMPTY) {if(e->games || f || e->expiry || e->day) return 0; empty=1; continue;}
   if(empty || e->player>=s->players || e->games>t->games || e->day>t->day || f>=64) return 0;
   if((f&(CHARGED|PRACTICE|CUTDOWN)) && !(f&ELIGIBLE)) return 0;
   if((f&PRACTICE) && (!(f&CHARGED) || (f&EXPIRED) || !e->expiry)) return 0;
   if((f&CUTDOWN) && !(f&CHARGED)) return 0;
   if((f&LEGACY) && f!=LEGACY) return 0;
   if(e->expiry>532 || (!(f&(PRACTICE|EXPIRED)) && e->expiry)) return 0;
   charged+=(f&CHARGED)!=0; cut+=(f&CUTDOWN)!=0;
   for(p=0;p<i*5+j;p++) if(s->ir[p].player==e->player) return 0;
   for(p=0;p<32;p++) if(s->teams[p].a==e->player || s->teams[p].b==e->player) return 0;
  }
  if(charged>t->used || cut>t->cut) return 0;
 }
 return 1;
}
static void expire(struct State *s,u32 team,u32 day) {
 u32 j; struct IR *e;
 for(j=team*5;j<team*5+5;j++) {e=s->ir+j;
  if((e->flags&PRACTICE) && day>=e->expiry) e->flags=(e->flags&~PRACTICE)|EXPIRED;
 }
 s->teams[team].day=day;
}
/* Returns 0 refused (no store), 1 changed, 2 exact replay. Request is 40 bytes.
 * op 0 init: player=pool count, flags=season, key=epoch; state need not exist yet.
 * op 1 IR: flags bits post-cutdown=1, cutdown=2, legacy=4.
 * op 2 complete: flags=phase 8/9. op 3 designate: flags=postseason 0/1.
 * op 4 activate: flags=medical clear 0/1, active/reserves=ownership counts.
 * op 5 accept: flags=postseason, a/b=PS ids or FFFF (packed).
 * op 6 qualify. op 7 rollover: flags=new season. op 8 calendar day advance.
 */
u32 FC franchise_kernel(struct State *s,const struct Request *r) {
 struct Team *t; struct IR *e=0,*row; u32 j,k,h,f,used,slot=5;
 if(s!=(struct State *)&workspace || !r || (u32)r>0xffffffffU-sizeof(*r)) return 0;
 if((u32)r<(u32)s+sizeof(*s) && (u32)r+sizeof(*r)>(u32)s) return 0;
 if(r->op==0) {
  if(!r->player || r->player>NPLAY || r->flags<2000 || r->flags>2255) return 0;
  init(s,r->flags,r->player,r->key); return 1;
 }
 if(!valid(s) || r->op>8) return 0;
 if(r->op==7) {
  if(r->flags==s->season) return 2;
  if(r->flags!=s->season+1U || r->flags>2255) return 0;
  for(j=0;j<32;j++) if(s->teams[j].game!=EMPTY) return 0;
  for(j=0;j<160;j++) if(s->ir[j].player!=EMPTY) return 0;
  init(s,r->flags,s->players,s->epoch); return 1;
 }
 if(r->team>=32 || r->day>511) return 0;
 t=s->teams+r->team; row=s->ir+r->team*5;
 if(r->op==6) {if(t->qualified) return 2; t->qualified=1; return 1;}
 if(r->op==8) {if(r->day<t->day) return 0; expire(s,r->team,r->day); return 1;}
 if(r->op==2) {
  if(r->key>=EMPTY || (r->flags!=8 && r->flags!=9)) return 0;
  if(t->last==r->key) return r->day==t->day?2:0;
  if((t->last!=EMPTY && r->key<=t->last) || t->games>=31 || r->day<t->day || (t->game!=EMPTY && t->game!=r->key) || (r->flags==9 && !t->qualified)) return 0;
  t->last=r->key; t->games++; t->game=t->a=t->b=EMPTY; expire(s,r->team,r->day); return 1;
 }
 if(r->op==5) {
  if(r->key>=EMPTY || r->flags>1 || r->a>EMPTY || r->b>EMPTY || (r->a==EMPTY && r->b!=EMPTY) || (r->a!=EMPTY && r->a==r->b)) return 0;
  if(t->game==r->key) return (t->a==r->a && t->b==r->b && t->day==r->day)?2:0;
  if(t->game!=EMPTY || (t->last!=EMPTY && r->key<=t->last) || r->day<t->day || (r->flags && !t->qualified)) return 0;
  for(j=0;j<2;j++) {
   k=j?r->b:r->a; if(k==EMPTY) continue;
   if(k>=s->players || (!r->flags && (hist(s,k)&3)>=3)) return 0;
   for(h=0;h<160;h++) if(s->ir[h].player==k) return 0;
   for(h=0;h<32;h++) if(s->teams[h].a==k || s->teams[h].b==k) return 0;
  }
  if(!r->flags) {
   if(r->a!=EMPTY) put_hist(s,r->a,hist(s,r->a)+1);
   if(r->b!=EMPTY) put_hist(s,r->b,hist(s,r->b)+1);
  }
  t->game=r->key; t->a=r->a; t->b=r->b; t->day=r->day; return 1;
 }
 if(r->player>=s->players || r->day<t->day) return 0;
 h=hist(s,r->player);
 for(j=0;j<5;j++) if(row[j].player==r->player) {e=row+j; slot=j; break;}
 if(r->op==1) {
  if(t->game!=EMPTY || r->flags>7 || ((r->flags&4) && (r->flags&2))) return 0;
  for(j=0;j<160;j++) if(s->ir[j].player==r->player) return 0;
  for(j=0;j<32;j++) if(s->teams[j].a==r->player || s->teams[j].b==r->player) return 0;
  for(j=0;j<5;j++) if(row[j].player==EMPTY) break;
  if(j==5) return 0;
  f=(r->flags&4)?LEGACY:(r->flags&3)?ELIGIBLE:0;
  if(r->flags&2) {
   if(t->cut>=2 || t->used>=8 || (h>>2)>=2) return 0;
   f|=CHARGED|CUTDOWN;
  }
  e=row+j; e->player=r->player; e->games=t->games; e->flags=f; e->day=r->day;
  if(r->flags&2) {t->used++; t->cut++;} t->day=r->day; return 1;
 }
 if(!e) return 0;
 if(r->op==3) {
  if(r->flags>1 || (r->flags && !t->qualified) || !(e->flags&ELIGIBLE) || (e->flags&(EXPIRED|LEGACY)) || t->games-e->games<4 || (h>>2)>=2) return 0;
  if(e->flags&PRACTICE) return r->day<e->expiry?2:0;
  used=t->used;
  if(!(e->flags&CHARGED)) {if(used>=(r->flags?10U:8U)) return 0; used++;}
  t->used=used; t->day=r->day; e->flags|=CHARGED|PRACTICE; e->expiry=r->day+21; return 1;
 }
 if(r->op==4) {
  if(t->game!=EMPTY || !(e->flags&PRACTICE) || r->day>=e->expiry || t->games-e->games<4 || r->flags!=1 || r->active>=53 || r->reserves>12 || r->active+r->reserves>=65 || (h>>2)>=2) return 0;
  put_hist(s,r->player,h+4);
  for(j=slot;j<4;j++) row[j]=row[j+1];
  zero(row+4,8); row[4].player=EMPTY; t->day=r->day; return 1;
 }
 return 0;
}

struct PACK Candidate {u16 id; u8 position,rank,rating,available,reserve,elevated;};
struct Selection {u32 count,previous_count,special_count; struct Candidate p[65]; u16 previous[48],special[6];};
struct Selected {u32 count,ol; u16 ids[48];};
static u32 ol(struct Candidate *p) {return p->position>=12 && p->position<=14;}
static int better(struct Candidate *a,struct Candidate *b) {
 if(a->rank!=b->rank) return a->rank<b->rank;
 if(a->rating!=b->rating) return a->rating>b->rating;
 return a->id<b->id;
}
static void take(u32 i,u8 *marked,u16 *selected,u32 *n,struct Selection *r) {
 if(!marked[i] && *n<48) {marked[i]=1; selected[(*n)++]=r->p[i].id;}
}
/* Independent deterministic R1 selection. Does not mutate source records.
 * Return 0 without output writes on refusal; 1 on success. */
u32 FC franchise_select(struct Selection *r,struct Selected *out) {
 u32 i,j,k,n=0,count=0,active=0,reserves=0,elevated=0,ols=0,limit,pos,want;
 u8 order[65],marked[65]; u16 selected[48]; struct Candidate *p;
 if(!r || !out || (u32)r>0xffffffffU-sizeof(*r) || (u32)out>0xffffffffU-sizeof(*out)) return 0;
 if((u32)r<(u32)out+sizeof(*out) && (u32)r+sizeof(*r)>(u32)out) return 0;
 if(r->count>65 || r->previous_count>48 || r->special_count>6) return 0;
 zero(marked,65);
 for(i=0;i<r->count;i++) {
  p=r->p+i;
  if(p->id>=NPLAY || p->position>16 || p->rank>7 || p->available>1 || p->reserve>1 || p->elevated>1 || (p->elevated && !p->reserve)) return 0;
  for(j=0;j<i;j++) if(r->p[j].id==p->id) return 0;
  if(p->reserve) reserves++; else active++;
  elevated+=p->elevated;
  if(p->available && (!p->reserve || p->elevated)) {
   j=count++;
   while(j && better(p,r->p+order[j-1])) {order[j]=order[j-1]; j--;}
   order[j]=i; ols+=ol(p);
  }
 }
 if(active>53 || reserves>12 || elevated>2 || count<11) return 0;
 limit=ols>=8?48:47;
 for(pos=0;pos<17;pos++) {
  want=pos==0?2:1;
  for(j=0;j<count && want;j++) if(r->p[order[j]].position==pos) {take(order[j],marked,selected,&n,r); want--;}
 }
 for(i=0;i<r->special_count;i++) for(j=0;j<count;j++) if(r->p[order[j]].id==r->special[i]) take(order[j],marked,selected,&n,r);
 want=8;
 for(j=0;j<count && want;j++) if(ol(r->p+order[j])) {take(order[j],marked,selected,&n,r); want--;}
 for(i=0;i<r->previous_count && n<limit;i++) for(j=0;j<count;j++) if(r->p[order[j]].id==r->previous[i]) take(order[j],marked,selected,&n,r);
 for(j=0;j<count && n<limit;j++) take(order[j],marked,selected,&n,r);
 ols=0;
 for(i=0;i<n;i++) for(k=0;k<r->count;k++) if(r->p[k].id==selected[i]) ols+=ol(r->p+k);
 out->count=n; out->ol=ols;
 for(i=0;i<48;i++) out->ids[i]=i<n?selected[i]:EMPTY;
 return 1;
}
/* Date YYYYMMDD in ECX. EDX bits: minute 0..15, deadline disabled bit16,
 * trade predicate bit17 (else cutdown). 0 invalid, 1 false, 2 true. */
u32 FC franchise_calendar(u32 date,u32 context) {
 u32 minute=context&65535,month=date/100%100,day=date%100,days;
 if(date/10000!=2026 || minute>=1440 || context>>18 || month<1 || month>12) return 0;
 days=month==2?28:(month==4 || month==6 || month==9 || month==11)?30:31;
 if(!day || day>days) return 0;
 if(context&(1<<17)) return (context&(1<<16)) || date<20261110 || (date==20261110 && minute<960)?2:1;
 return date>20260830 || (date==20260830 && minute>=1080)?2:1;
}
