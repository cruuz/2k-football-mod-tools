extern u32 FC retail_remove(u8 *,u32);
extern void FC retail_load(u8 *);
extern void FC retail_save(u8 *);
static NOINLINE void copy(u8 *d,const u8 *s,u32 n) { while(n--) *d++=*s++; }
static NOINLINE void zero(u8 *d,u32 n) { while(n--) *d++=0; }
static NOINLINE u32 available_count(void) {
    u8 used[1000],*r=ROOT,*t,*p; u32 i,j,id,total=0; int n;
    if(!r || U32(r,0)>8000 || U32(r,0x18)>128 || U32(r,0x38)>8000) return 0;
    zero(used,1000); t=(u8 *)U32(r,0x1c);
    for(i=0;i<U32(r,0x18);i++,t+=500) {
        n=reserve_count(t); if(n<0) return 0;
        j=(i<32 || U32(t,0x128)==2 || U32(t,0x128)==4)?0:B(t,ACTIVE);
        for(;j<B(t,ACTIVE)+(u32)n;j++) {
            id=index_of((u8 *)slot(t,j)); if(id==EMPTY) return 0;
            used[id/8]|=1U<<(id%8);
        }
    }
    for(i=0;i<U32(r,0x38);i++) {
        id=index_of((u8 *)U32((u8 *)U32(r,0x3c),4*i)); if(id==EMPTY) return 0;
        used[id/8]|=1U<<(id%8);
    }
    if(U32((u8 *)0xE576A0,0)) for(i=0;i<160;i++) {
        p=(u8 *)U32((u8 *)0xE421E0,4*i); if(!p) continue;
        id=index_of(p); if(id==EMPTY) return 0; used[id/8]|=1U<<(id%8);
    }
    for(i=0;i<U32(r,0);i++) if((B((u8 *)(U32(r,4)+84*i),8)&5)==1) {
        /* Retail BFF50 selects by these bits. Refuse contradictory owned/free
         * records before it can choose an identity excluded by our bitmap. */
        if(used[i/8]&(1U<<(i%8))) return 0;
        ++total;
    }
    return total;
}

/* C3A90 has EAX=team, ECX=slot. Its adapter preserves the native slot repair
 * and every later owner hook, then fills the native tail from the overflow. */
u32 FC arena_remove(u8 *t,u32 at) {
    u32 saved[17],i,a=B(t,ACTIVE),result; int n=reserve_count(t);
    if(n<0 || at>=a || !integrity()) return 0;
    for(i=0;i<(u32)n;i++) saved[i]=slot(t,a+i);
    result=retail_remove(t,at);
    if(result) {
        a=B(t,ACTIVE);
        for(i=0;i<(u32)n;i++) put_slot(t,a+i,saved[i]);
        for(i=a+(u32)n;i<capacity(t);i++) put_slot(t,i,0);
        seal();
    }
    return result;
}

/* Legacy save migration is done before publication. No old in-memory index
 * can be mistaken for a reused player after E64D0 clears its ownership. */
static NOINLINE void initialize(u8 *r) {
    u8 *b=r+BLOCK_OFFSET,*t=(u8 *)U32(r,0x1c); u32 i;
    zero(b,352);
    U32(b,0)=0x52354b32; U32(b,4)=0x00325653;
    U32(b,8)=0x00200002; U32(b,12)=0x00020005;
    U32(b,28)=arena_options&0x100;
    for(i=0;i<160;i++) U16(b,32+2*i)=0xffff;
    for(i=0;i<32 && i<U32(r,0x18);i++,t+=500) {
        B(t,RSV_VERSION)=2; B(t,RSV_MAGIC)=0xa5;
    }
    seal();
}
void FC arena_load(u8 *w) {
    u32 ver,declared,aux,word8,old_size; u8 *root,*b;
    if(!w || U32(w,0)!=0x54534f52 || U32(w,44)!=0x54534f52) return;
    ver=U32(w,48); declared=U32(w,4); word8=U32(w,8);
    aux=(ver==17 || ver==18)?0:word8;
    if(aux>ARENA_SIZE-BLOCK_OFFSET-352) return;
    root=w+52+U32(w,52)-1;
    if(ver==1 || ver==18) {
        if(root!=w+(ver==1?64:96) || declared!=(ver==1?0x92020:0x92040)) return;
        b=root+BLOCK_OFFSET;
        if(U32(b,0)!=0x52354b32 || U32(b,4)!=0x00325653 ||
           U32(b,8)!=0x00200002 || U32(b,12)!=0x00020005 ||
           (U32(b,28)&~0x102U) || crc(b)!=U32(b,20)) return;
    } else if(ver==0) {
        if(root!=w+64 || declared!=0x91020) return;
    } else if(ver!=17 || root!=w+96 || declared!=0x90f60) return;
    old_size=declared+32-((u32)root-(u32)w);
    U32(w,8)=aux;
    retail_load(w);
    U32(w,8)=word8;
    root=ROOT;
    if(!root || root!=(u8 *)U32((u8 *)0xB72804,0)) return;
    if(ver==0 || ver==17) {
        copy(root+ARENA_SIZE-aux,root+old_size-aux,aux);
        zero(root+old_size,ARENA_SIZE-old_size-aux);
        initialize(root);
    }
    U32((u8 *)0xB7280C,0)=ARENA_SIZE-aux;
    if(aux) U32((u8 *)0xBDB758,0)=(u32)root+ARENA_SIZE-aux;
}
void FC arena_save(u8 *w) {
    if(!w || !integrity()) return;
    retail_save(w);
    U32(w,48)=1;
}

/* Reserves get priority in the disposable 65-player practice projection.
 * Source active lists never change. Competitive modes copy active only. */
void FC arena_stage(u8 *away,u8 *home) {
    u8 *src[2],*t,*p,*d; u32 side,i,a,n,take,r,idx;
    src[0]=away; src[1]=home;
    for(side=0;side<2;side++) {
        t=(u8 *)(0xB30864+500*side); p=(u8 *)(0xB30C4C+5460*side);
        copy(t,src[side],500); a=B(t,ACTIVE); n=a; r=0;
        if(U32((u8 *)0xE576A0,0)==1 && U32((u8 *)0xE5FF80,0)<=2 && integrity()) {
            int reserves=reserve_count(src[side]);
            if(reserves>0) { r=(u32)reserves; n=a+r; if(n>65) n=65; }
        }
        take=n-r;
        for(i=0;i<n;i++,p+=84) {
            idx=i<take?i:a+i-take;
            d=(u8 *)slot(src[side],idx); copy(p,d,84);
            U32(t,4*i)=(u32)p; B(p,0x34)=side+1;
        }
        for(i=n;i<65;i++) U32(t,4*i)=0;
        B(t,ACTIVE)=n; B(t,RSV_VERSION)=B(t,RSV_COUNT)=B(t,RSV_MAGIC)=0;
    }
}
u32 FC arena_created(u8 *t) {
    u32 id=U16(t,0x118); u8 *b=block(),*r=ROOT;
    if(id==90 || id==91) return 0;
    if(b && (U32(b,28)&255)==2 && U32(r,0x18)==54 &&
       ((id==100 && (u32)t==U32(r,0x1c)+52*500) ||
        (id==101 && (u32)t==U32(r,0x1c)+53*500))) return 0;
    return 1;
}
