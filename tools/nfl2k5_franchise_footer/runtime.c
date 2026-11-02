/* Franchise extension footer host (b780 J2, job j23-footer). EXPERIMENTAL.

   Freestanding i386 code for the late allocator owner nfl2k5_franchise_footer, built by
   tools/nfl2k5_franchise_footer_build.py into mod_editor/core/nfl2k5_franchise_footer_code.py. No retail bytes live
   here. Every address this code needs beyond its own labels is in the CONFIG table at the end of the blob, which the
   Studio fills when it installs the owner (nfl2k5_franchise_footer.code_for): the owner's writable state, the static
   body (builds without the 128 MB roster heap), the Player Progress footer it hosts, the call targets it displaced.

   The format is mod_editor/core/nfl2k5_franchise_extension.py (published contract; keep the two in step):
     native save | MyCareer 128 (optional) | body BODY_SIZE (optional) | Player Progress footer 34,320 (optional, last)
   Body: 64-byte header ("2K5XTND1", sizes, flags, save count, year/stage/week, Adler-32 of header+directory at +0x3C),
   16 directory slots of 16 bytes at +0x40 (slot n = block id n+1: id, version, flags, offset, size, Adler-32), the host
   info area at +0x140 (not checksummed), the blocks at fixed offsets from +0x200.

   Hooks (stubs.S): 0x16AA26 total size, 0x16E50D save (after the front office and the MyCareer block), 0x16E815 load
   (after every native deserializer and MyCareer's), 0x16ABB5 save-list admission of a franchise save, 0x13EF21 new
   franchise (inside FUN_0013EE10, which MyCareer also calls). Nothing here allocates except xt_body (once per boot).
*/

typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;

#define FC __attribute__((fastcall))
#define G(a) (*(volatile u32 *)(a))
#define B(a) (*(volatile u8 *)(a))

#define ALLOC ((u8 *(FC *)(u32, u32))0x00048700)      /* heap allocate: ecx = heap control, edx = bytes */
#define EXTRA_REGION 0x00B018B8u                      /* the >64 MB region the arena init took (K128) */
#define HEAP_MAGIC_AT 0x98u
#define HEAP_MAGIC 0x50414548u                         /* "HEAP", written by the game's heap init 0x48640 */
#define MAIN_HEAP 0x00B04E24u
#define ARENA_SIZE 0x00B72808u                         /* this build's roster arena length */
#define LEAGUE_MODE 0x00E576A0u
#define STAGE 0x00E576A4u
#define WEEK 0x00E576B4u
#define YEAR 0x00E576B8u

#define BODY_SIZE 98288u
#define PP_SIZE 34320u
#define CAREER 128u
#define RETAIL_SAVE 720044u
#define LEGACY_SAVE 847020u
#define NATIVE_FROM_DECLARED 0x1EC8Cu
#define DIR_AT 0x40u
#define SLOTS 16u
#define INFO_AT 0x140u
#define CHECKSUM_AT 0x3Cu
#define PP_RECORD_SIZE 34287u

/* CONFIG (filled by the Studio; read only at run time). Layout pinned by nfl2k5_franchise_footer.CONFIG_FIELDS. */
struct config {
    u32 magic;          /* "XTHC" */
    u32 version;        /* 1 */
    u32 state;          /* the owner's writable state (64 bytes) */
    u32 static_body;    /* the body in the executable's writable memory, or 0 (K128 builds: extra memory) */
    u32 pp_footer;      /* the Player Progress owner's RAM footer (its data + 16), or 0 when it is not hosted */
    u32 pp_baseline;    /* that owner's capture_baseline, or 0 */
    u32 chain_size;     /* the displaced call targets */
    u32 chain_save;
    u32 chain_load;
    u32 seeds;          /* a table of 16 seed image pointers (block id 1..16), or 0 */
    u32 flags;          /* bit 0: the main heap may hold the body when there is no extra region */
    u32 stamp;          /* host build stamp (written into the header) */
    u32 chain_franchise;/* the displaced new-franchise call target (0x13ED70 on retail bytes) */
    u8 admission[8];    /* the seven bytes the admission site held before this owner (+ one zero) */
    u32 reserved;
};
extern const struct config xt_config;

/* the blocks this host knows (the format's BLOCKS): id, version, offset, size */
static const u32 blocks[6][4] = {
    {1, 1, 0x0200, 18960}, {2, 1, 0x4C10, 528}, {3, 1, 0x4E20, 9520},
    {4, 1, 0x7350, 16176}, {5, 1, 0xB280, 4624}, {6, 1, 0xC490, 12304},
};
#define NBLOCKS 6u

/* state (64 bytes, zero at boot) */
#define S_MAGIC 0u
#define S_BODY 4u
#define S_FLAGS 8u        /* 1 no memory this boot, 2 dropped a loaded body (no memory) */
#define S_SOURCE 12u
#define S_LOADS 16u
#define S_SAVES 20u
#define S_RESULT 24u
#define S_ADMIT 28u

static u8 *state(void) { return (u8 *)xt_config.state; }
#define SW(off) (*(volatile u32 *)(state() + (off)))

static void copy(u8 *to, const u8 *from, u32 n) {
    for (u32 i = 0; i < n; i++)
        to[i] = from[i];
}

static void zero(u8 *to, u32 n) {
    for (u32 i = 0; i < n; i++)
        to[i] = 0;
}

static u32 rd(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24; }
static void wr(u8 *p, u32 v) { p[0] = (u8)v; p[1] = (u8)(v >> 8); p[2] = (u8)(v >> 16); p[3] = (u8)(v >> 24); }
static void wr16(u8 *p, u32 v) { p[0] = (u8)v; p[1] = (u8)(v >> 8); }
static u32 rd16(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8; }

/* zlib Adler-32, continuing (a, b) packed as b << 16 | a; the modulo every 5,552 bytes */
static u32 adler(const u8 *p, u32 n, u32 sum) {
    u32 a = sum & 0xFFFF, b = sum >> 16;
    while (n) {
        u32 k = n < 5552 ? n : 5552;
        n -= k;
        while (k--) {
            a += *p++;
            b += a;
        }
        a %= 65521;
        b %= 65521;
    }
    return b << 16 | a;
}

static const u8 magic[8] = {'2', 'K', '5', 'X', 'T', 'N', 'D', '1'};

static u32 header_sum(const u8 *b) {
    return adler(b + DIR_AT, SLOTS * 16, adler(b, CHECKSUM_AT, 1));
}

static void write_header(u8 *b, u32 flags) {
    for (u32 i = 0; i < 8; i++)
        b[i] = magic[i];
    wr16(b + 8, 1);
    wr16(b + 10, 64);
    wr(b + 12, BODY_SIZE);
    wr16(b + 16, DIR_AT);
    wr16(b + 18, SLOTS);
    wr16(b + 20, 16);
    wr16(b + 22, 0);
    wr(b + 24, flags);
}

static u32 header_ok(const u8 *b) {
    for (u32 i = 0; i < 8; i++)
        if (b[i] != magic[i])
            return 0;
    return rd16(b + 8) == 1 && rd16(b + 10) == 64 && rd(b + 12) == BODY_SIZE && rd16(b + 16) == DIR_AT
        && rd16(b + 18) == SLOTS && rd16(b + 20) == 16 && rd(b + CHECKSUM_AT) == header_sum(b);
}

static void write_entry(u8 *b, u32 k) {
    u8 *e = b + DIR_AT + (blocks[k][0] - 1) * 16;
    wr16(e, blocks[k][0]);
    e[2] = (u8)blocks[k][1];
    e[3] = 1;
    wr(e + 4, blocks[k][2]);
    wr(e + 8, blocks[k][3]);
    wr(e + 12, adler(b + blocks[k][2], blocks[k][3], 1));
}

static u32 entry_ok(const u8 *b, u32 k) {
    const u8 *e = b + DIR_AT + (blocks[k][0] - 1) * 16;
    return rd16(e) == blocks[k][0] && e[2] == blocks[k][1] && (e[3] & 1) && rd(e + 4) == blocks[k][2]
        && rd(e + 8) == blocks[k][3] && rd(e + 12) == adler(b + blocks[k][2], blocks[k][3], 1);
}

/* a block's seed image (or zeros) and its directory entry */
static void init_block(u8 *b, u32 k) {
    const u32 *seeds = (const u32 *)xt_config.seeds;
    const u8 *seed = seeds ? (const u8 *)seeds[blocks[k][0] - 1] : 0;
    if (seed)
        copy(b + blocks[k][2], seed, blocks[k][3]);
    else
        zero(b + blocks[k][2], blocks[k][3]);
    write_entry(b, k);
}

static void info_set(u8 *b, u32 at, u32 value) { wr(b + INFO_AT + at, value); }
static u32 info_get(const u8 *b, u32 at) { return rd(b + INFO_AT + at); }

/* a new, empty (seeded) body */
static void fresh(u8 *b, u32 reason) {
    zero(b, BODY_SIZE);
    write_header(b, xt_config.pp_footer ? 1 : 0);
    wr(b + 36, xt_config.stamp);
    for (u32 k = 0; k < NBLOCKS; k++)
        init_block(b, k);
    wr(b + CHECKSUM_AT, header_sum(b));
    info_set(b, 0x00, 0x4F464E49);                 /* "INFO" */
    info_set(b, 0x14, SW(S_SOURCE));
    info_set(b, 0x18, reason);
}

/* The body, allocated and made fresh the first time it is needed (allow != 0); 0 when there is no memory for it. */
u8 *FC xt_body(u32 allow) {
    u8 *b = (u8 *)SW(S_BODY);
    if (b || !allow || (SW(S_FLAGS) & 1))
        return b;
    u32 source = 0;
    if (xt_config.static_body) {
        b = (u8 *)xt_config.static_body;
        source = 1;
    } else {
        u32 region = G(EXTRA_REGION);
        if (region && G(region + HEAP_MAGIC_AT) == HEAP_MAGIC) {
            b = ALLOC(region, BODY_SIZE);
            source = 2;
        } else if (xt_config.flags & 1) {
            b = ALLOC(MAIN_HEAP, BODY_SIZE);
            source = 3;
        }
    }
    if (!b) {
        SW(S_FLAGS) |= 1;
        return 0;
    }
    SW(S_MAGIC) = 0x31485458;                       /* "XTH1" */
    SW(S_SOURCE) = source;
    fresh(b, 4);
    SW(S_BODY) = (u32)b;
    return b;
}

/* ---- total size (0x16AA26): what the footer adds to this franchise save ---------------------------------------- */
u32 FC xt_size_extra(void) {
    u8 *b = xt_body(G(LEAGUE_MODE) == 2);
    return (xt_config.pp_footer ? PP_SIZE : 0) + (b ? BODY_SIZE : 0);
}

/* ---- save (0x16E50D, after the front office and the MyCareer block): the body, then Player Progress ----------- */
void FC xt_save_footer(u8 *buffer, u32 total) {
    u32 pp = xt_config.pp_footer ? PP_SIZE : 0;
    u8 *b = (u8 *)SW(S_BODY);                         /* the size hook already decided; never allocate here */
    u32 need = pp + (b ? BODY_SIZE : 0);
    if (!buffer || total < RETAIL_SAVE + need)
        return;
    if (pp)
        copy(buffer + total - PP_SIZE, (const u8 *)xt_config.pp_footer, PP_SIZE);
    if (b) {
        u32 saves = rd(b + 28) + 1;
        write_header(b, pp ? 1 : 0);
        wr(b + 28, saves);
        wr16(b + 32, G(YEAR));
        b[34] = (u8)G(STAGE);
        b[35] = (u8)G(WEEK);
        wr(b + 36, xt_config.stamp);
        for (u32 k = 0; k < NBLOCKS; k++)
            write_entry(b, k);
        wr(b + CHECKSUM_AT, header_sum(b));
        info_set(b, 0x10, info_get(b, 0x10) + 1);
        copy(buffer + total - pp - BODY_SIZE, b, BODY_SIZE);
    }
    SW(S_SAVES) += 1;
}

/* ---- load (0x16E815, after every deserializer) ------------------------------------------------------------------ */
static u32 native_of(const u8 *file, u32 size) {
    u32 declared = rd(file + 0x2E4);
    u32 native = declared + NATIVE_FROM_DECLARED;
    if (rd(file + 0x2E0) != 0x54534F52 || size < native)  /* "ROST" */
        return 0;
    if (native != RETAIL_SAVE && native != RETAIL_SAVE + 0x1000 && native != LEGACY_SAVE
        && native != RETAIL_SAVE + G(ARENA_SIZE) - 0x91000)
        return 0;
    return native;
}

/* 0 none, 1 Player Progress only, 2 body only, 3 both; *career = 0 or 128 */
static u32 footer_kind(u32 rest, u32 *career) {
    static const u32 sizes[4] = {0, PP_SIZE, BODY_SIZE, BODY_SIZE + PP_SIZE};
    for (u32 c = 0; c <= CAREER; c += CAREER)
        for (u32 k = 0; k < 4; k++)
            if (rest == c + sizes[k]) {
                *career = c;
                return k;
            }
    *career = 0;
    return 0xFF;
}

static u32 pp_ok(const u8 *f) {
    return rd(f) == 0x46475050 && rd(f + 4) == 0x31303030 && rd16(f + 8) == 1 && rd16(f + 10) == 32
        && rd(f + 12) == PP_RECORD_SIZE;
}

/* check every known block of a loaded body; rebuild a bad one from its seed. 2 loaded, 3 bad header, 4 repaired */
static u32 repair(u8 *b) {
    if (!header_ok(b)) {
        fresh(b, 3);
        return 3;
    }
    u32 mask = 0;
    for (u32 k = 0; k < NBLOCKS; k++)
        if (!entry_ok(b, k)) {
            init_block(b, k);
            mask |= 1u << (blocks[k][0] - 1);
        }
    if (mask)
        wr(b + CHECKSUM_AT, header_sum(b));
    info_set(b, 0x08, mask);
    return mask ? 4 : 2;
}

void FC xt_load_footer(const u8 *file, u32 size) {
    u32 native = file ? native_of(file, size) : 0, career = 0, kind = 0xFF;
    if (native)
        kind = footer_kind(size - native, &career);
    if (kind == 0xFF)
        kind = 0;                                       /* not a known layout: treat it as a save without footers */
    SW(S_LOADS) += 1;
    if (xt_config.pp_footer) {                          /* the Player Progress owner's own old-save rule */
        u8 *pp = (u8 *)xt_config.pp_footer;
        if ((kind & 1) && pp_ok(file + size - PP_SIZE))
            copy(pp, file + size - PP_SIZE, PP_SIZE);
        else {
            zero(pp, PP_SIZE);
            if (xt_config.pp_baseline)
                ((void (*)(void))xt_config.pp_baseline)();
        }
    }
    u32 result;
    if (kind & 2) {
        u8 *b = xt_body(1);
        if (b) {
            copy(b, file + native + career, BODY_SIZE);
            result = repair(b);
            if (result == 3)
                info_set(b, 0x08, 0);
        } else {
            SW(S_FLAGS) |= 2;                            /* no memory: the history pauses (xemu at 64 MB) */
            result = 5;
        }
    } else {
        u8 *b = (u8 *)SW(S_BODY);
        if (b)
            fresh(b, 2);                                /* this franchise has no history yet */
        result = 1;
    }
    u8 *b = (u8 *)SW(S_BODY);
    if (b) {
        info_set(b, 0x04, result);
        info_set(b, 0x0C, info_get(b, 0x0C) + 1);
        info_set(b, 0x14, SW(S_SOURCE));
    }
    SW(S_RESULT) = result;
}

/* ---- save-list admission of a franchise save: the size family of nfl2k5_franchise_extension.admitted_sizes ----- */
u32 FC xt_admit(u32 size) {
    u32 arena = G(ARENA_SIZE), natives[3], career;
    natives[0] = RETAIL_SAVE;
    natives[1] = RETAIL_SAVE + arena - 0x91000;
    natives[2] = natives[1] > LEGACY_SAVE ? LEGACY_SAVE : 0;
    SW(S_ADMIT) = size;
    for (u32 i = 0; i < 3; i++)
        if (natives[i] && size >= natives[i] && footer_kind(size - natives[i], &career) != 0xFF)
            return 1;
    return 0;
}

/* ---- a new franchise (0x13EF21 inside FUN_0013EE10): its history starts empty ----------------------------------- */
void FC xt_new_franchise(void) {
    u8 *b = (u8 *)SW(S_BODY);
    if (b)
        fresh(b, 1);
}

/* The host's exported cell for other owners (the history engine, screens): the body pointer, 0 when absent. */
u8 *FC xt_body_now(void) { return (u8 *)SW(S_BODY); }
