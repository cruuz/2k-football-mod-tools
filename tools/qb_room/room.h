/* Quarterback room: declarations shared by room.c (piece 3) and moves.c (piece 4a). Declarations only, so moving
   them here left room.c's compiled bytes unchanged (pinned in tests/mod_editor/test_b81_qb_room_native.py). */
#ifndef QB_ROOM_H
#define QB_ROOM_H
typedef unsigned int u32;
typedef int i32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char i8;

#define CDECL __attribute__((cdecl))
#define FC __attribute__((fastcall))
#define B(a) (*(volatile u8 *)(a))
#define W(a) (*(volatile u16 *)(a))
#define D(a) (*(volatile u32 *)(a))

#define CLUB_AT ((u32 (FC *)(u32))0x000C4C50)
#define WINS ((u32 (FC *)(u32))0x000C7720)
#define LOSSES ((u32 (FC *)(u32))0x000C7750)
#define TIES ((u32 (FC *)(u32))0x000C7780)
#define SEASON_STAT ((i32 (FC *)(u32, u32))0x0014EE40)
#define RATING ((float (FC *)(u32, u32))0x00246D80)

#define LEAGUE_ROOT 0x00B72918u      /* [root + 4] = player table, 0x54 bytes per player */
#define STAT_CLASS 0x00BD7F98u
#define STAGE 0x00E576A4u            /* 7 preseason, 8 season, 9 playoffs */
#define WEEK 0x00E576B4u
#define YEAR 0x00E576B8u
#define USER_FLAG 0x00E5775Cu        /* u32 per league club: human (0x13EC30 -> 0xC4D50 reads this table) */
#define CPU_DEPTH 0x00E60140u        /* "CPU manages my depth chart" */
#define GENERATOR_A 0x00E5FCA8u      /* two words of the game's shared generator, read only (as slice 1) */
#define GENERATOR_B 0x00E5FCB0u

#define CLUBS 32u                    /* league clubs; 32 and 33 are the all-star sides */
#define SLOTS 65u
#define QB_MAX 7u
#define PLAYER_SIZE 0x54u
#define ROW_MASK (7u << 10)          /* player + 0x28 bits 10..12: depth row */
#define INJURED 0x80000000u
#define WEEKS_MASK (255u << 22)

#define STAGE_D1 1u
#define STAGE_D2D3 2u
#define STAGE_D4 4u
#define STAGE_SIGN 8u                /* stage 4a: the signing pass and E1 */
#define STAGE_E2 32u                 /* E2 as well (only with STAGE_SIGN) */
#define STAGE_FLOOR 64u              /* the floor (DESIGN addendum F3) */
#define STAGE_OVER_CAP 128u          /* the floor's last rung: sign past the gates, over the cap */
#define FLAG_SHADOW 1u
#define LIMIT_PPM 1000000u

#define D1 1u
#define D2 2u
#define D3 3u
#define D4 4u
#define HOT 0x10u
#define PRESEASON 0x20u
#define B_AHEAD 0x40u
#define KEPT 0u
#define APPLIED 1u
#define WOULD 2u
#define LOCK_ONLY 3u

/* Page data (fixed page offsets, resolved by build.py; the template holds zeros there). */
struct settings {
    u32 magic[2];
    u32 mode, stages, flags, h0_ppm, d2_scale_milli, reserved;
};
extern volatile struct settings qb_settings;          /* page + 0x2000 */

/* COUNTERS BEGIN (build.py reads these names in order; page + 0x2040, u32 each) */
struct counters {
    u32 opening_passes;          /* every entry, whatever the settings */
    u32 room_passes;
    u32 passes_bad_settings;     /* magic or mode not QBROOMv1 / 1: nothing done */
    u32 passes_inactive;         /* a stage bit is on but the league stage is not 7, 8 or 9 */
    u32 clubs_visited;
    u32 skip_no_club;
    u32 skip_unmanaged;          /* human club with manual depth */
    u32 skip_room_shape;         /* not 2..7 quarterbacks on rows exactly 0..n-1 */
    u32 skip_row0_unhealthy;
    u32 skip_opening_injured;    /* opening pass: some quarterback not fully healthy */
    u32 coach_missing;           /* club + 0x14C was 0: leadership 83 used */
    u32 newcomers;               /* unlocked healthy quarterbacks judged */
    u32 newcomer_locked;         /* case (c): locked where he is */
    u32 newcomer_stage_off;      /* branch (a) or (b) whose stage bit is clear: left alone */
    u32 d1_evaluated;
    u32 d1_no_veteran;           /* no healthy non-rookie: rookie locked where he is */
    u32 d1_drawn;
    u32 d1_veteran_first;
    u32 d1_rookie_first;
    u32 d1_exchanged;            /* rows exchanged (or would be, in shadow) */
    u32 d2_evaluated;
    u32 d2_drawn;
    u32 d2_fired;
    u32 d2_kept;
    u32 d3_evaluated;
    u32 d3_drawn;
    u32 d3_fired;
    u32 d3_kept;
    u32 d3_exposure_lo;          /* sum over D3 evaluations of form*record*week*gapf*coach in millionths, */
    u32 d3_exposure_hi;          /* the same integer steps with H0 = 1; 64-bit (lo, hi) */
    u32 d4_evaluated;
    u32 d4_hot;
    u32 d4_lock_only;            /* gap >= 3 or <= -3: no draw */
    u32 d4_drawn;
    u32 d4_fired;
    u32 d4_kept;
    u32 exchanges_written;       /* row exchanges written to the game */
    u32 locks_written;           /* rank-lock bits set in the game */
    u32 shadow_exchanges;        /* exchanges decided in shadow (not written) */
    u32 events_logged;
    u32 e1_tried;                /* reserved for stage 4a / 4b (not built) */
    u32 e1_done;
    u32 e2_tried;
    u32 e2_done;
    u32 trades_posted;
    u32 trades_cancelled;
    u32 sign_passes;             /* stage 4a (moves.c): every entry through sign_after, whatever the settings */
    u32 sign_inactive;           /* stage bit 8 on, league stage not 8 */
    u32 sign_skip_human;         /* human club without auto sign/cut */
    u32 sign_no_candidate;       /* a need, but no healthy free agent the native picker would take within cap room */
    u32 sign_pool_overflow;      /* more quarterbacks in the picker's two pools than this pass can hold: skipped */
    u32 sign_ir_unlinked;        /* E2 asked for, but the IR store link is 0 or not the IR owner's store */
    u32 e2_drawn;
    u32 e2_kept;
    u32 sign_shadow;             /* signings decided in shadow (no cut, no signing) */
    u32 sign_cuts;               /* smart cuts 0x2BF9A0(club, 52) made first */
    u32 sign_room_lost;          /* cap room after the cut no longer above value(F): no signing */
    u32 sign_failed;             /* 0x322BB0 returned 0 */
    u32 floor_pregame_passes;    /* the floor (bit 64): every pre-game call, whatever the settings */
    u32 floor_runs;              /* a club the CPU signs for with H = 0 */
    u32 floor_post_deferred;     /* post-game call, A >= 3: left for the pre-game call */
    u32 floor_no_free_agent;     /* step 1 */
    u32 floor_pool_overflow;
    u32 floor_shadow;
    u32 floor_swaps;             /* step 2 releases of an injured quarterback */
    u32 floor_swap_stuck;
    u32 floor_cuts;              /* step 3 */
    u32 floor_candidate;         /* step 4 */
    u32 floor_no_target;         /* step 5 found nobody the picker would take */
    u32 floor_restructures;      /* step 6 */
    u32 floor_releases;          /* step 7 */
    u32 floor_gated;             /* step 8, through the gates after rungs 6 and 7 */
    u32 floor_over_cap;          /* step 8, past the gates (result code 5) */
    u32 floor_no_room;           /* step 8 impossible (over-cap rung off, or 53 active) */
    u32 floor_sign_failed;
    u32 floor_seated;            /* step 9 */
    u32 floor_failed;            /* step 10: still H = 0 */
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
extern volatile u32 qb_link_ir_store;                 /* page + 0x2020: the IR owner's store (stage 4a) */
extern volatile u32 qb_menu;                          /* page + 0x2E04: menu saved by sign_entry (RAM only) */

#endif
