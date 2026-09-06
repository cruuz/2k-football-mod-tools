/* Persistent index storage. ROOT is the installed writable ROST allocation. */
#define ARENA_SIZE 0x92000U
#define BLOCK_OFFSET 0x91c00U
extern const u32 arena_options;
static NOINLINE u32 available_count(void);
static NOINLINE u32 crc(const u8 *b) {
    u32 c=0xffffffffU,i,j;
    for(i=0;i<352;i++) {
        c^=(i>=20 && i<24)?0:b[i];
        for(j=0;j<8;j++) c=(c>>1)^((0U-(c&1))&0xedb88320U);
    }
    return c^0xffffffffU;
}
static NOINLINE u8 *block(void) {
    u8 *r=ROOT,*b;
    if(!r || U32((u8 *)0xB72808,0)!=ARENA_SIZE) return 0;
    b=r+BLOCK_OFFSET;
    if(U32(b,0)!=0x52354b32 || U32(b,4)!=0x00325653 ||
       U32(b,8)!=0x00200002 || U32(b,12)!=0x00020005 ||
       (U32(b,28)&~0x102U)) return 0;
    return b;
}
static NOINLINE int integrity(void) {
    u8 *b=block();
    return b && crc(b)==U32(b,20);
}
static NOINLINE void seal(void) {
    u8 *b=block(); if(b) U32(b,20)=crc(b);
}
static NOINLINE int ordinal(u8 *t) {
    u8 *r=ROOT; u32 d;
    if(!r || !t || !U32(r,0x1c)) return -1;
    d=(u32)t-U32(r,0x1c);
    if(d%500 || d/500>=32 || d/500>=U32(r,0x18)) return -1;
    return (int)(d/500);
}
static NOINLINE u32 capacity(u8 *t) {
    return B(t,RSV_VERSION)==2 && ordinal(t)>=0 && block()?70:65;
}
static NOINLINE u32 reserve_limit(u8 *t) {
    int team=ordinal(t); u8 *b=block();
    if(!b || team<0 || !(U32(b,28)&0x100)) return 12;
    return 16+((U32(b,24)>>(u32)team)&1);
}
static NOINLINE u32 slot(u8 *t,u32 i) {
    int team; u8 *b; u32 id;
    if(i<65) return U32(t,4*i);
    if(i>=70 || (team=ordinal(t))<0 || !(b=block())) return 0;
    id=U16(b,32+(u32)team*10+(i-65)*2);
    return id==0xffff || id>=U32(ROOT,0)?0:U32(ROOT,4)+84*id;
}
static NOINLINE void put_slot(u8 *t,u32 i,u32 p) {
    if(i<65) U32(t,4*i)=p;
    else { u8 *b=block(); int team=ordinal(t);
        if(b && team>=0 && i<70) U16(b,32+(u32)team*10+(i-65)*2)=p?index_of((u8 *)p):0xffff;
    }
}
static NOINLINE int reserve_count(u8 *t) {
    u32 i,n,r,end,cap;
    if(!t) return -1;
    n=B(t,ACTIVE); r=B(t,RSV_COUNT); cap=capacity(t);
    if(n>65) return -1;
    if(!B(t,RSV_VERSION) && !r && !B(t,RSV_MAGIC)) r=0;
    else if((B(t,RSV_VERSION)!=1 && !(B(t,RSV_VERSION)==2 && cap==70)) ||
            B(t,RSV_MAGIC)!=0xa5 || r>reserve_limit(t)) return -1;
    end=n+r; if(end>cap) return -1;
    for(i=end;i<cap;i++) if(slot(t,i)) return -1;
    for(i=n;i<end;i++) if(!slot(t,i)) return -1;
    return (int)r;
}
static NOINLINE void set_count(u8 *t,u32 n) {
    B(t,RSV_VERSION)=ordinal(t)>=0 && block()?2:1;
    B(t,RSV_MAGIC)=0xa5; B(t,RSV_COUNT)=n;
}
