/* Quarterback room (beta 81 piece 3, owner nfl2k5_qb_room). Skeleton: both passes only count themselves. */
typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char i8;

#define CDECL __attribute__((cdecl))

/* Page data (fixed page offsets, resolved by build.py; the template holds zeros there). */
struct settings {
    u8 magic[8];
    u32 mode, stages, flags, h0_ppm, d2_scale_milli, reserved;
};
extern volatile struct settings qb_settings;          /* page + 0x2000 */

/* COUNTERS BEGIN (build.py reads these names in order; page + 0x2040, u32 each) */
struct counters {
    u32 opening_passes;
    u32 room_passes;
};
/* COUNTERS END */
extern volatile struct counters qb_counters;          /* page + 0x2040 */

struct event {
    u16 year;
    u8 week, club, decision, result;
    u16 a, b;
    i8 d;
    u8 g;
    u16 rating10;
    i8 gap;
    u8 coach;
    u32 threshold;
} __attribute__((packed));
extern volatile struct event qb_ring[128];            /* page + 0x2400 */
extern volatile u32 qb_ring_cursor;                   /* page + 0x2E00 */

void CDECL opening_pass(void) {
    qb_counters.opening_passes++;
}

void CDECL room_pass(void) {
    qb_counters.room_passes++;
}
