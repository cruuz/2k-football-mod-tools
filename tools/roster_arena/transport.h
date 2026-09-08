/* Full-arena compact team exports keep the same +91C00 overflow location.
 * Payloads are larger, but neither native 500-byte team nor 65-entry import
 * scratch arrays are widened. Two bounded retail import batches do the copy. */
void FC arena_size(u8 *t,u8 *other,u8 *stadium,u32 *fixed,u32 *strings) {
    (void)t; (void)other; (void)stadium; *fixed=ARENA_SIZE; *strings=0;
}
u8 * FC arena_export(u8 *t,u8 *other,u8 *stadium,u8 *out) {
    u8 *teams[2],*dest,*p,*b; u32 n=other?2:1,counts[2],i,j,k=0,at,text;
    u32 fixed,strings,needed=0;
    if(!t || !out || t==other || !integrity()) return 0;
    teams[0]=t; teams[1]=other;
    for(j=0;j<n;j++) {
        int r=reserve_count(teams[j]); if(r<0) return 0;
        counts[j]=B(teams[j],ACTIVE)+(u32)r;
    }
    ps_size(t,other,stadium,&fixed,&strings);
    needed=fixed+strings;
    if(needed>BLOCK_OFFSET || fixed>0x10000 || strings>BLOCK_OFFSET-0x10000) return 0;
    zero(out,ARENA_SIZE); at=(u32)out+0x70; text=(u32)out+0x10000;
    if(stadium) { U32(out,0x10)=1; U32(out,0x14)=at; COPY(0x241F50)(stadium,&at,&text); }
    U32(out,0x30)=n; U32(out,0x34)=at;
    for(j=0;j<n;j++) COPY(0x2416E0)((u8 *)U32(teams[j],0x14c),&at,&text);
    U32(out,0x18)=n; U32(out,0x1c)=at;
    for(j=0;j<n;j++) COPY(0x241BD0)(teams[j],&at,&text);
    U32(out,0)=counts[0]+(other?counts[1]:0); U32(out,4)=at;
    b=out+BLOCK_OFFSET; copy(b,block(),352);
    U32(b,16)=0; U32(b,24)=0; U32(b,28)=0x100;
    for(i=0;i<160;i++) U16(b,32+2*i)=0xffff;
    for(j=0;j<n;j++) {
        dest=(u8 *)(U32(out,0x1c)+500*j);
        B(dest,ACTIVE)=B(teams[j],ACTIVE); B(dest,RSV_VERSION)=2;
        B(dest,RSV_COUNT)=B(teams[j],RSV_COUNT); B(dest,RSV_MAGIC)=0xa5;
        if(reserve_limit(teams[j])==17) U32(b,24)|=1U<<j;
        U32(dest,0x14c)=U32(out,0x34)+168*j;
        if(stadium) U32(dest,0x114)=U32(out,0x14);
        for(i=0;i<counts[j];i++,k++) {
            p=(u8 *)slot(teams[j],i);
            if(i<65) U32(dest,4*i)=at;
            else U16(b,32+10*j+2*(i-65))=k;
            COPY(0xE5F20)(p,&at,&text);
        }
    }
    U32(out,0x48)=n; U32(out,0x4c)=at;
    for(j=0;j<n;j++) {
        dest=(u8 *)(U32(out,0x1c)+500*j); U32(dest,0x110)=at;
        COPY(0x197050)((u8 *)U32(teams[j],0x110),&at,&text);
    }
    U32(b,20)=crc(b); return out;
}
static NOINLINE u32 relative(u8 *field) { return U32(field,0)?(u32)field+U32(field,0)-1:0; }
u8 * FC arena_export_one(u8 *out,u8 *t) {
    u32 colleges[70],i,n,id; u8 *pool;
    if(!arena_export(t,0,(u8 *)U32(t,0x114),out)) return 0;
    n=U32(out,0); pool=(u8 *)U32(out,4);
    for(i=0;i<n;i++) {
        id=U32((u8 *)slot(t,i),0);
        if(!id || id<U32(ROOT,0x24) || (id-U32(ROOT,0x24))%8 ||
           (id-U32(ROOT,0x24))/8>=U32(ROOT,0x20)) id=0xffffffffU;
        else id=(id-U32(ROOT,0x24))/8;
        colleges[i]=id;
    }
    FN1(0xC0730)(out);
    for(i=0;i<n;i++) U32(pool,84*i)=colleges[i];
    return out;
}
u32 FC arena_import(u8 *src,u8 *dst) {
    u8 *team,*pool,*b; u8 saved[500],proxy[500];
    u32 n,a,reserves,i,j,available=0,first,result,old_pool,ids[70],college[70];
    if(!src || !dst || !integrity() || U32(src,0x18)!=1 || B(dst,ACTIVE) || reserve_count(dst)!=0) return 0;
    n=U32(src,0); if(!n || n>70) return 0;
    team=(u8 *)relative(src+0x1c); pool=(u8 *)relative(src+4);
    if(!team || !pool) return 0;
    if(B(team,RSV_VERSION)!=2) return ps_import(src,dst);
    a=B(team,ACTIVE); reserves=B(team,RSV_COUNT); b=src+BLOCK_OFFSET;
    if(a>65 || a+reserves!=n || reserves>reserve_limit(dst) || n>capacity(dst) ||
       B(team,RSV_MAGIC)!=0xa5 || U32(b,0)!=0x52354b32 || U32(b,4)!=0x00325653 ||
       U32(b,8)!=0x00200002 || U32(b,12)!=0x00020005 || crc(b)!=U32(b,20)) return 0;
    for(i=0;i<n;i++) {
        if(i<65) { if(relative(team+4*i)!=(u32)pool+84*i) return 0; }
        else if(U16(b,32+2*(i-65))!=i) return 0;
        college[i]=U32(pool,84*i);
    }
    for(i=n;i<70;i++) {
        if(i<65) { if(U32(team,4*i)) return 0; }
        else if(U16(b,32+2*(i-65))!=0xffff) return 0;
    }
    available=available_count();
    if(available<n) return 0;
    copy(saved,team,500); old_pool=U32(src,4); first=n<65?n:65;
    U32(src,0)=first; B(team,ACTIVE)=first;
    B(team,RSV_VERSION)=B(team,RSV_COUNT)=B(team,RSV_MAGIC)=0;
    result=ps_import(src,dst);
    if(result) {
        for(i=0;i<first;i++) ids[i]=U32(dst,4*i);
        if(n>first) {
            copy(proxy,dst,500); zero(proxy,260);
            B(proxy,ACTIVE)=B(proxy,RSV_VERSION)=B(proxy,RSV_COUNT)=B(proxy,RSV_MAGIC)=0;
            U32(src,0)=n-first; U32(src,4)=(u32)pool+first*84-(u32)(src+4)+1;
            zero(team,260); B(team,ACTIVE)=n-first;
            for(i=0;i<n-first;i++) U32(team,4*i)=(u32)pool+(first+i)*84-(u32)(team+4*i)+1;
            result=ps_import(src,proxy);
            if(result) for(i=first;i<n;i++) ids[i]=U32(proxy,4*(i-first));
        }
        if(result) {
            B(dst,ACTIVE)=a; set_count(dst,reserves);
            for(j=0;j<n;j++) put_slot(dst,j,ids[j]);
            for(j=n;j<capacity(dst);j++) put_slot(dst,j,0);
            seal(); FN1(0xC3F00)(dst);
        }
    }
    copy(team,saved,500); U32(src,0)=n; U32(src,4)=old_pool;
    for(i=0;i<n;i++) U32(pool,84*i)=college[i];
    return result;
}
