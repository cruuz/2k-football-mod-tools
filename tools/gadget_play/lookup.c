/* The native choice supplies the primary play, formation and category. The
 * game relocates their pointers. All offsets below are for the USA PLAY body. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
enum { FORM=0x134, AUX=0x245c, PLAY=0x33fc, CAT=0x993c,
       NODE=0x9adc, NAMES=0x10840, END_NAMES=0x13380, BODY=0x13390 };
struct book_rows { char name[12]; u16 first, count; };
struct link { u16 play, pair_play; u8 form, pair_form, slot, reserved; u32 program, codes; };
extern const struct book_rows book_rows[];
extern const struct link links[];
extern const u8 blobs[];
extern const u32 *const pair_info;
static u32 word(const void *p) { return *(const u32 *)p; }
static int equal(const u8 *a, const u8 *b, u32 n) {
    for (u32 i=0; i<n; ++i) if (a[i]!=b[i]) return 0;
    return 1;
}
static int index_at(const u8 *root, const u8 *p, u32 start, u32 stride, u32 count) {
    u32 delta=(u32)p-((u32)root+start);
    if (delta>=count*stride || delta%stride) return -1;
    return (int)(delta/stride);
}
static const struct book_rows *book_for(const u8 *root) {
    const u16 *name=(const u16 *)word(root+0x30);
    u32 offset=(u32)name-(u32)root;
    if (offset<NAMES || offset>END_NAMES-24 || offset&1) return 0;
    for (unsigned b=0;b<37;b++) {
        const struct book_rows *r=book_rows+b;
        for (unsigned i=0;i<12;i++) {
            if (name[i]!=(u8)r->name[i]) break;
            if (!name[i]) return r;
        }
    }
    return 0;
}
/* Compare the entire native script against the compiler's exact canonical
 * bytes. The in-place initializer may set bit 31 in the play flags (0x1a9a8c).
 * A pointer only gets read as a node chain after bounds and 8-byte alignment. */
static int same_program(const u8 *root, const u8 *play, const u8 *w, u32 nodes) {
    if ((word(play+4)&0x7fffffffu)!=word(w)) return 0;
    w+=4;
    for (unsigned slot=0;slot<11;slot++) {
        u32 descriptor=word(play+8+8*slot), count=descriptor&15;
        if (descriptor!=word(w)) return 0;
        w+=4;
        if (!count) continue;
        const u8 *chain=(const u8 *)word(play+12+8*slot);
        u32 off=(u32)chain-(u32)(root+NODE), length=count*8;
        if ((off&7) || off>nodes*8 || length>nodes*8-off || !equal(chain,w,length)) return 0;
        w+=length;
    }
    return 1;
}
int select_slot(const u8 *root, const u8 *const *choice, const u8 *category,
                const u8 *formation) {
    if ((u32)root<0x10000 || (u32)root>0x7fffffffu-BODY || (u32)root&3) return -1;
    if (choice[0]!=category || choice[1]!=formation || choice[2]!=choice[3]) return -1;
    if (word(root+12)!=0x59414c50 || word(root+0x44)!=(u32)(root+FORM) ||
        word(root+0x48)!=(u32)(root+AUX) || word(root+0x60)!=(u32)(root+PLAY) ||
        word(root+0x64)!=(u32)(root+CAT) || word(root+0x68)!=(u32)(root+NODE)) return -1;
    u32 nf=word(root+0x34), np=word(root+0x38), nc=word(root+0x3c), nn=word(root+0x40);
    if (!nf || nf>50 || !np || np>270 || !nc || nc>26 || nn>3500) return -1;
    int f=index_at(root,formation,FORM,180,nf), p=index_at(root,choice[2],PLAY,96,np);
    int c=index_at(root,category,CAT,16,nc);
    if (f<0 || p<0 || c<0) return -1;
    const u8 *aux=root+AUX+f*80;
    if ((word(aux+72)&63)!=(u32)c) return -1;  /* honor alternate personnel */
    const struct book_rows *b=book_for(root);
    if (!b) return -1;
    int paired=pair_info && (pair_info[2]==(u32)root || pair_info[5]==(u32)root);
    for (u32 i=0;i<b->count;i++) {
        const struct link *l=links+b->first+i;
        if ((paired ? l->pair_play : l->play)!=p || (paired ? l->pair_form : l->form)!=f) continue;
        if (!equal(category+4,blobs+l->codes,12)) return -1;
        for (unsigned k=0;k<36;k++) {
            if ((*(const u16 *)(aux+2*k)&511)==(u32)p)
                return same_program(root,choice[2],blobs+l->program,nn) ? l->slot : -1;
        }
        return -1;
    }
    return -1;
}
