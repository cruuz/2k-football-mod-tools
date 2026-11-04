"""Main-heap budget at game setup for the 64 MB and 128 MB targets (b780-m64a). MODELLED, anchored on measurements.

Why (Noah, 2026-11-03): SOFTDRINK should also play on 64 MB machines: the original Xbox and hakuX on Android
(which reimplements the Xbox kernel instead of running the real one). The full 128 MB build stays the main product;
the Studio's 64 MB option uses this module to say what fits, what must be off and what to trim. Pure Python: no
disc reads, no native code; every number below was measured or derived offline and is pinned by
``tests/mod_editor/test_nfl2k5_memory_budget.py``.

What decides a game (read from the XBE code: MEM1, BK 2026-10-01, K1 2026-09-23)
-------------------------------------------------------------------------------
* The arena init (0x326E0) takes the largest contiguous block below 64 MiB less 2 MiB ([0xA6D324]) and builds the
  main heap over it (0x3908D). The executable's boot-loaded pages come out of the same 64 MiB first, so every
  resident page is one page less main heap. K128's late form adds the upper 64 MB only after this, so the main heap
  is the same at 64 MB and at 128 MB (retail 33,039,360 B; the v0.9 RC 32,662,400 B); only the early form grows it.
* The loading mode loads the stadium bundle and the two kit packages (and gamedata.iff) into the main heap; game
  setup's in-game block (0x84EB0) then takes the main heap's largest free block ("the room") less 0x20000 and carves
  at most 0x180000 of it: a 0x2E0 header, the match roster export (about 14 KB), heap A = min(0x148000, the rest) and
  heap B = what is left, where the pregame intro director DIR_INTRO needs 73,856 B. With K128's roster heap and the
  >64 MB region the block is capped at 0x180000 (the freed room stays free); at 64 MB it is not capped.
* Heap B too small: DIR_INTRO's load gets NULL (the resource load guard catches it) and the pregame stadium shots loop
  until A is pressed. Heap A short of 0x148000: the pregame and intro helmet loads fail too. So the verdict here asks
  for heap B >= 73,856 B plus a safety margin at the hardest matchup, which leaves heap A whole.

The model
---------
room(plan) = the v0.9 RC's measured room (EMU1 H1R2: 1,495,936 B, Texans at Ravens, M&T Bank afternoon clear, 128 MiB,
K128 late + roster heap), moved by what the plan does differently from that RC:
  + the executable's resident pages (page model of the allocator: the v3 scale-out runs, the v4 pool, the SPECIAL
    .XTLID storage), measured per owner on the RC's own default.xbe;
  + the disc resources the options add to the main heap (gamedata.iff, global.iff; disc inventory RC vs retail);
  - the roster block when it is in the main heap (always at 64 MB; 0xCA080 B with the capacity arena, 0x91080 retail);
  - the stadium bundle and the two kit packages of the matchup against the anchor's (every bundle of the RC disc);
  + K128's early form (128 MB only: the graphics arena grows 46.7 -> 61.6 MiB).
Measured numbers reproduce exactly (RC and v0.8 heaps at 128 MiB); the 64 MB numbers are MODELLED: no 64 MB run of
these builds exists yet. Known gap: retail at 64 MB (K1 lab, Patriots v Redskins) has about 386-401 KB more room
than this accounting explains from the RC's content; the model keeps that unattributed use (conservative), so a
plan far from the RC (a near-retail build) is predicted tighter than it may be. The U2 lab series (eight venues)
scatters about +-54 KB around the stadium term; the 64 KiB safety margin covers that.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import zlib
from dataclasses import fields as _dc_fields, is_dataclass

EVIDENCE = "MODELLED"
TARGETS = (64, 128)

# --- the engine (XBE code) ------------------------------------------------------------------------------------------
PAGE = 0x1000
UNIT = 128                       # the game's heap works in 128-byte units; an allocation costs align128(request + 128)
ARENA_RESERVE = 0x200000         # [0xA6D324], kept back by the arena init
INGAME_RESERVE = 0x20000         # 0x84EB0 leaves 128 KB of the largest free block
INGAME_CAP = 0x180000            # the most the in-game block ever carves (and K128's cap)
BLOCK_HEADER = 0x2E0
HEAP_A_SIZE = 0x148000
DIR_INTRO_BYTES = 73_856         # DIR_INTRO.IFF: 73,680 B of payload, 73,856 B charged in heap B (R4, BK)
EARLY_ARENA_GAIN = int((61.6 - 46.7) * 1024 * 1024) & ~0xFFF   # K128 early form, lab (K1, MEM1): 15,622,144 B
SAFETY_MARGIN = 65_536           # heap B bytes kept above DIR_INTRO at the hardest matchup
EXPORT_MARGIN = 512              # match exports measured 13,724..14,176 B; other matchups may be a little larger

# --- measurements ---------------------------------------------------------------------------------------------------
# EMU1 H1R2 (2026-11-03): the v0.9 RC disc 93c889e4 (default.xbe 1a476d94...), 128 MiB, K128 late + roster heap + the
# 128 MB stop, Texans at Ravens, M&T Bank Stadium (s02, afternoon clear), live reads of the running guest.
ANCHOR = {"room": 1_495_936, "block": 1_364_864, "left": 1_349_952, "export": 14_176, "heap_a": 1_343_360,
          "heap_b": 6_400, "dir_intro": "NULL", "venue": "s02ad", "home_kit": "02h0", "away_kit": "37a0",
          "main_heap": 32_662_400, "resident": 15_896_576, "source": "EMU1 H1R2, 2026-11-03"}
# EMU1 H1V8B: the v0.8 disc (default.xbe 5f987568...), same setup and matchup.
V08 = {"room": 1_555_456, "block": 1_424_384, "heap_b": 66_304, "resident": 15_835_136,
       "dir_intro": "NULL", "source": "EMU1 H1V8B, 2026-11-03"}
# K1 k1b (2026-09-23): retail plus K128's stub at 128 MiB with the roster in the main heap (the 64 MB layout),
# Patriots v Redskins: in-game block 2,115,456 B, export 13,968 B, heap B 214,656 B, 126,464 B free at the coin toss.
RETAIL = {"room": 2_115_456 + INGAME_RESERVE, "block": 2_115_456, "export": 13_968, "heap_b": 214_656,
          "main_heap": 33_039_360, "resident": 15_527_936, "venue": "s16", "home_kit": "16h0", "away_kit": "29a0",
          "source": "K1 k1b-retail-late-stub, 2026-09-23"}
UNATTRIBUTED_RC = (385_792, 401_024)   # RC main-heap use at setup this accounting does not explain (dd / ad variant)

# --- the executable's resident pages (the RC's own default.xbe, nfl2k5_xbe_space.layout) -------------------------------
RETAIL_RESIDENT = 15_527_936
XTLID_PRELOAD = 81_920           # SPECIAL depth-chart rows: .XTLID grown to 0xEE3CF0 and preloaded (20 pages)
LEGACY_SPACE = 3 * PAGE          # .AS0000 .. .AS0002
SCALEOUT_V3 = 0x18000 + 0x14000 + 0x5000   # .AS0003 .. .AS0005: 96 KiB RX, 80 KiB RW, 20 KiB RO (200,704 B)
POOL_DOC = PAGE                  # the v4 pool's directory document page
OUTER_TOP_GROWTH = 8_320         # the RC's main heap is 376,960 B below retail's: 368,640 B of pages and this
CODE_V3_CAP, RO_V3_CAP, DATA_V3_CAP = 106_852 + 64, 17_316 + 624, 86_016
# Without the scale-out the allocator keeps two legacy pages (+8,192 B; a third, code2, compresses the directory) and
# its header directory, a JSON document of the requests and the boot logo's, must fit 444 bytes: about seven small
# owners. Past that, or with any SCALEOUT_FIELDS option, it takes the scale-out (+212,992 B with the legacy pages).
# MEASURED offline (nfl2k5_xbe_space.apply on the retail XBE, 1 to 36 owners, 2026-11-03).
LEGACY_DIRECTORY_BYTES = 444     # HEADER_LOGO_OFFSET - DIRECTORY
LOGO_REQUEST = ("nfl2k5_boot_logo", "code", 690, 16)
LEGACY_REQUESTS = {"widescreen_menus": (("code", 128, 16),), "period_goalposts": (("code", 176, 16), ("read_only", 32, 4)), "team_logo_swap": (("read_only", 64, 4),), "abilities_runtime": (('code', 1344, 16),), "accelerated_clock": (('code', 1024, 16), ('data', 4, 4), ('read_only', 8, 4)), "audible_legend": (('code', 1280, 16),), "ball_carrier_ai": (('code', 176, 16),), "calendar": (('code', 1024, 16), ('read_only', 2048, 16)), "camera": (('code', 864, 16), ('read_only', 320, 16)), "catch_snap_limit": (('code', 224, 16),), "classic_teams": (('read_only', 288, 16),), "clock_led": (('code', 576, 16),), "coach_carousel": (('code', 4096, 16),), "coin_defer": (('code', 384, 16), ('data', 4, 4), ('read_only', 128, 4)), "contract_college_guard": (('code', 32, 16),), "coverage_slider": (('code', 16, 16),), "coverage_trail": (('code', 640, 16),), "cpu_clock2": (('code', 1152, 16),), "cpu_money_downs": (('code', 2048, 16),), "cpu_money_downs_late": (('code', 400, 16),), "cpu_money_downs_late_state": (('data', 8, 4),), "cpu_passer_iq": (('code', 256, 16), ('data', 16, 16)), "cpu_qb_reads": (('code', 1280, 16), ('data', 192, 16)), "cpu_scrambles": (('code', 128, 16), ('read_only', 4, 4)), "cpu_third_down": (('code', 192, 16),), "db_ball_play": (('code', 256, 16),), "decided_clock": (('code', 384, 16), ('read_only', 8, 4)), "deep_zone": (('code', 2048, 16), ('data', 256, 16)), "dive_window": (('code', 352, 16),), "draft_clock": (('code', 608, 16),), "dynamic_kickoff_relocated": (('code', 1939, 16), ('data', 10, 4)), "espn25_more_moments": (('code', 2560, 16), ('data', 16, 16)), "force_out": (('code', 96, 16),), "formation_art_spacing": (('code', 1024, 16),), "franchise_autosave": (('code', 1536, 16), ('data', 128, 16), ('read_only', 512, 16)), "franchise_edit_player": (('read_only', 704, 16),), "guardian_overlay": (('code', 496, 16),), "hair_styles": (('code', 768, 16),), "historic_teams_quick_game": (('code', 1280, 16), ('data', 16, 16)), "human_tap_burst_spill": (('code', 512, 16),), "k128": (('code', 1536, 16),), "letter_grades": (('code', 160, 16), ('read_only', 240, 16)), "letter_grades_progress": (('code', 16, 16),), "module_loader": (('code', 256, 16), ('data', 32, 16)), "moment_coaches": (('code', 512, 16), ('data', 512, 16)), "momentum": (('code', 1408, 16), ('data', 2064, 16)), "music_playlist": (('code', 2048, 16), ('data', 512, 16), ('read_only', 1024, 16)), "pass_protection": (('code', 352, 16),), "play_art_routes": (('code', 576, 16),), "practice_injuries": (('code', 48, 16),), "preseason_warning": (('data', 16, 16),), "protection_calls": (('code', 288, 16), ('data', 16, 16)), "qb_accuracy": (('code', 448, 16),), "qb_spy": (('code', 2048, 16), ('data', 768, 16), ('read_only', 512, 16)), "read_option_runtime": (('code', 2048, 16), ('data', 256, 16), ('read_only', 88, 16)), "return_coverage": (('code', 192, 16),), "roster_storage": (('code', 82, 16),), "run_blocking": (('code', 160, 16),), "runner_vision": (('code', 1664, 16),), "scramble_blocking": (('code', 816, 16), ('data', 16, 16)), "scramble_tuning": (('code', 160, 16),), "screen_hooks": (('code', 640, 16),), "sim_cb_tackles": (('code', 256, 16),), "sim_rb_injuries": (('code', 640, 16),), "sim_realism": (('code', 896, 16), ('data', 16, 4)), "standings_records": (('code', 2304, 16), ('data', 16, 16)), "star_retention": (('code', 64, 16),), "stock_books": (('code', 1536, 16),), "team_number_scale": (('code', 624, 16),), "weekly_prep": (('code', 1536, 16),), "weekly_progression": (('code', 608, 16),), "zone_drop": (('code', 80, 16),)}

# owner: (code in v3, code in the pool, read-only in v3, read-only in the pool, data), bytes in the RC
OWNER_BYTES = {
    "history_screen": (0, 18432, 0, 36864, 64), "player_progress_screen": (0, 4096, 0, 0, 34336),
    "my_career": (20480, 0, 0, 0, 4096), "roster_arena_growth": (8192, 0, 0, 0, 0),
    "pass_rush_stats": (0, 3328, 3584, 0, 1152), "star_career": (2080, 0, 0, 0, 4096),
    "defensive_try_stats": (2048, 0, 4096, 0, 0), "scorebug_runtime": (5920, 0, 0, 0, 128),
    "champions": (5632, 0, 0, 0, 0), "coach_ai": (5120, 0, 0, 0, 128), "xbe_space_directory": (0, 0, 1104, 0, 0),
    "practice_squad_screen": (4096, 0, 0, 0, 256), "anniversary_kickoff": (3584, 0, 0, 0, 736),
    "era_rules": (2048, 0, 2176, 0, 16), "my_career_m3": (0, 0, 0, 0, 4096), "music_playlist": (2048, 0, 1024, 0, 512),
    "momentum": (1408, 0, 0, 0, 2064), "qb_spy": (2048, 0, 512, 0, 768), "calendar": (1024, 0, 2048, 0, 0),
    "espn25_more_moments": (2560, 0, 0, 0, 16), "honors": (2560, 0, 0, 0, 16), "defensive_try": (1440, 0, 0, 0, 1040),
    "standings_records": (0, 2304, 0, 0, 16), "deep_zone": (2048, 0, 0, 0, 256), "moment_venues": (2304, 0, 0, 0, 0),
    "franchise_autosave": (1536, 0, 512, 0, 128), "cpu_money_downs": (2048, 0, 0, 0, 0), "stock_books": (1536, 0, 0, 0, 0),
    "weekly_prep": (1536, 0, 0, 0, 0), "k128": (1536, 0, 0, 0, 0), "cpu_qb_reads": (1280, 0, 0, 0, 192),
    "abilities_runtime": (1344, 0, 0, 0, 0), "historic_teams_quick_game": (1280, 0, 0, 0, 16),
    "audible_legend": (0, 1280, 0, 0, 0), "camera": (864, 0, 320, 0, 0), "cpu_clock2": (0, 1152, 0, 0, 0),
    "accelerated_clock": (1024, 0, 8, 0, 4), "moment_coaches": (512, 0, 0, 0, 512),
    "formation_art_spacing": (1024, 0, 0, 0, 0), "hback_spill": (1024, 0, 0, 0, 0), "sim_realism": (896, 0, 0, 0, 16),
    "team_ratings_spill": (448, 0, 464, 0, 0), "hair_styles": (768, 0, 0, 0, 0), "franchise_edit_player": (0, 0, 704, 0, 0),
    "boot_logo": (690, 0, 0, 0, 0), "coverage_trail": (640, 0, 0, 0, 0), "screen_hooks": (640, 0, 0, 0, 0),
    "sim_rb_injuries": (640, 0, 0, 0, 0), "team_number_scale": (624, 0, 0, 0, 0), "draft_clock": (608, 0, 0, 0, 0),
    "weekly_progression": (608, 0, 0, 0, 0), "play_art_routes": (576, 0, 0, 0, 0), "clock_led": (576, 0, 0, 0, 0),
    "draft_picks_spill": (544, 0, 0, 0, 0), "coin_defer": (384, 0, 128, 0, 4), "human_tap_burst_spill": (512, 0, 0, 0, 0),
    "qb_accuracy": (448, 0, 0, 0, 0), "letter_grades": (160, 0, 240, 0, 0), "cpu_money_downs_late": (400, 0, 0, 0, 0),
    "decided_clock": (384, 0, 8, 0, 0), "pass_protection": (352, 0, 0, 0, 0), "protection_calls": (0, 288, 0, 0, 16),
    "classic_teams": (0, 0, 288, 0, 0), "module_loader": (256, 0, 0, 0, 32), "cpu_passer_iq": (256, 0, 0, 0, 16),
    "db_ball_play": (256, 0, 0, 0, 0), "sim_cb_tackles": (256, 0, 0, 0, 0), "period_goalposts": (176, 0, 32, 0, 0),
    "cpu_third_down": (192, 0, 0, 0, 0), "return_coverage": (192, 0, 0, 0, 0), "ball_carrier_ai": (176, 0, 0, 0, 0),
    "scramble_tuning": (160, 0, 0, 0, 0), "run_blocking": (160, 0, 0, 0, 0), "cpu_scrambles": (128, 0, 4, 0, 0),
    "widescreen_menus": (128, 0, 0, 0, 0), "force_out": (96, 0, 0, 0, 0), "roster_storage": (82, 0, 0, 0, 0),
    "zone_drop": (80, 0, 0, 0, 0), "team_logo_swap": (0, 0, 64, 0, 0), "star_retention": (64, 0, 0, 0, 0),
    "practice_injuries": (48, 0, 0, 0, 0), "contract_college_guard": (32, 0, 0, 0, 0), "coverage_slider": (16, 0, 0, 0, 0),
    "letter_grades_progress": (16, 0, 0, 0, 0), "preseason_warning": (0, 0, 0, 0, 16), "moment_context": (0, 0, 0, 0, 16),
    "cpu_money_downs_late_state": (0, 0, 0, 0, 8),
    # not in the RC (their own REQUESTS; placed where the model puts them: v3 first, the pool for the overflow)
    "franchise_footer": (4096, 0, 0, 0, 64), "coach_carousel": (4096, 0, 0, 0, 0), "runner_vision": (1664, 0, 0, 0, 0),
    "dive_window": (352, 0, 0, 0, 0), "catch_snap_limit": (224, 0, 0, 0, 0), "speed_threshold": (1024, 0, 0, 0, 0),
    "scramble_blocking": (816, 0, 0, 0, 16), "read_option_runtime": (2048, 0, 88, 0, 256),
    "playbook_pair": (8192, 0, 4096, 0, 512), "senior_bowl": (4096, 0, 0, 0, 65536),
    "franchise_2026": (5120, 0, 0, 0, 4096), "dynamic_kickoff_relocated": (1939, 0, 0, 0, 10),
    "guardian_overlay": (496, 0, 0, 0, 0),
    "injured_reserve": (6144, 0, 0, 0, 5312),   # b780 IR1: the runtime and its 32 x 20 store (nfl2k5_injured_reserve.REQUESTS)
}
FRANCHISE_STATIC_BODY = 98_352 - 64    # without the 128 MB roster heap the franchise history body is XBE data
# the scale-out's own owners (counted only with the scale-out; the legacy layout carries the boot logo itself)
INFRASTRUCTURE = ("xbe_space_directory", "boot_logo", "moment_context")


def _modern(value):
    return value not in (None, False, "", "retail", 0)


# owner -> the plan fields that install it (any of them); INFRASTRUCTURE rides with any space owner
OWNER_FIELDS = {
    "history_screen": ("history_screen",), "player_progress_screen": ("player_progress",), "my_career": ("my_career",),
    "my_career_m3": ("my_career",), "roster_arena_growth": ("reserves_16", "created_teams_extra", "roster_capacity"),
    "pass_rush_stats": ("pass_rush_stats",), "star_career": ("star_career",), "defensive_try_stats": ("defensive_try",),
    "defensive_try": ("defensive_try",), "scorebug_runtime": ("scorebug_runtime",), "champions": ("honors_page",),
    "honors": ("honors_page",), "coach_ai": ("coach_ai",), "practice_squad_screen": ("practice_squad_screen", "reserves_16"),
    "anniversary_kickoff": ("dynamic_kickoff",), "era_rules": ("espn25_era_rules",), "music_playlist": ("music_shuffle",),
    "momentum": ("momentum", "momentum_contact", "momentum_collisions"), "qb_spy": ("qb_spy",),
    "calendar": ("calendar_engine",), "espn25_more_moments": ("espn25_more_moments",),
    "moment_coaches": ("espn25_more_moments",), "standings_records": ("standings_records",),
    "deep_zone": ("deep_zone_facing", "deep_zone_bail"), "moment_venues": ("espn25_named_previews",),
    "franchise_autosave": ("franchise_autosave",), "cpu_money_downs": ("cpu_money_downs", "coach_ai"),
    "cpu_third_down": ("cpu_money_downs", "coach_ai"), "cpu_money_downs_late": ("cpu_money_downs_modern2",),
    "cpu_money_downs_late_state": ("cpu_money_downs_modern2",), "stock_books": ("historic_stock_books",),
    "weekly_prep": ("weekly_prep", "weekly_prep_cpu", "weekly_prep_remember"), "k128": ("k128_memory",),
    "cpu_qb_reads": ("cpu_qb_zone_windows", "cpu_qb_recheck", "cpu_qb_tiers"), "abilities_runtime": ("abilities",),
    "historic_teams_quick_game": ("historic_teams_quick_game",), "audible_legend": ("audible_legend",),
    "camera": ("camera",), "cpu_clock2": ("cpu_clock2",), "accelerated_clock": ("accelerated_clock",),
    "formation_art_spacing": ("play_art_routes",), "play_art_routes": ("play_art_routes",),
    "sim_realism": ("sim_realism",), "hair_styles": ("hair_styles",),
    "franchise_edit_player": ("franchise_edit_player",), "coverage_trail": ("coverage_trail", "coverage_hitch_brake"),
    "screen_hooks": ("screen_hooks",), "sim_rb_injuries": ("sim_rb_injuries",), "team_number_scale": ("team_number_scale",),
    "draft_clock": ("franchise_draft_clock",), "weekly_progression": ("weekly_progression",),
    "clock_led": ("modern_clock_led",), "coin_defer": ("coin_defer",), "qb_accuracy": ("qb_accuracy",),
    "letter_grades": ("letter_grades",), "letter_grades_progress": ("letter_grades",),
    "decided_clock": ("decided_clock",), "pass_protection": ("pass_protection",), "protection_calls": ("protection_calls",),
    "classic_teams": ("classic_teams",), "module_loader": ("module_loader",), "cpu_passer_iq": ("cpu_passer_iq",),
    "db_ball_play": ("db_ball_play",), "sim_cb_tackles": ("sim_cb_tackles",), "return_coverage": ("return_coverage",),
    "ball_carrier_ai": ("cpu_ball_carriers",), "scramble_tuning": ("scramble_tuning",), "run_blocking": ("run_blocking",),
    "cpu_scrambles": ("cpu_scrambles",), "force_out": ("modern_force_out",), "roster_storage": ("all_stadiums",),
    "zone_drop": ("zone_drop_cap",), "star_retention": ("star_retention",), "practice_injuries": ("practice_injuries",),
    "contract_college_guard": ("contract_college_guard",), "coverage_slider": ("coverage_slider",),
    "franchise_footer": ("franchise_history",), "coach_carousel": ("coach_carousel",),
    "runner_vision": ("cpu_runner_vision",), "dive_window": ("db_dive_window",), "catch_snap_limit": ("catch_snap_limit",),
    "speed_threshold": ("speed_threshold",), "scramble_blocking": ("scramble_blocking",),
    "read_option_runtime": ("read_option_runtime",), "playbook_pair": ("playbook_pair",), "senior_bowl": ("senior_bowl",),
    "franchise_2026": ("franchise_2026_rules",), "dynamic_kickoff_relocated": ("kickoff_relocated",),
    "guardian_overlay": ("guardian_overlay",), "human_tap_burst_spill": ("abilities",),
    "injured_reserve": ("modern_injured_reserve",),   # b780 IR1 (the Pro Bowl guard alone is in place: no bytes)
    "team_ratings_spill": ("team_ratings",), "preseason_warning": ("franchise_economy",),
    # small owners the build adds from other options on a disc image (mod_build _widescreen_menus_wanted,
    # _period_goalposts_wanted, _team_logo_swap_wanted; the economy's preseason warning flag)
    "widescreen_menus": ("widescreen",), "period_goalposts": ("modern_goalposts",),
    "team_logo_swap": ("modern_practice_field_team_logo",),
    # the roster edits' own XBE steps: draft-pick ownership and H-back role labels install directory spills that
    # always take the scale-out (nfl2k5_draft_picks / nfl2k5_hback apply with scaleout=True)
    "draft_picks_spill": ("roster_draft_pick_ownership",), "hback_spill": ("roster_hback_roles",),
}
# the plan fields that need the scale-out sections (nfl2k5_throw_tuning._xbe_space_adapter)
SCALEOUT_FIELDS = ("camera", "franchise_autosave", "weekly_prep", "weekly_prep_cpu", "weekly_prep_remember", "coach_ai",
                   "playbook_pair", "deep_zone_facing", "deep_zone_bail", "momentum_collisions", "accelerated_clock",
                   "coin_defer", "decided_clock", "cpu_scrambles", "sim_rb_injuries", "sim_realism", "coach_carousel",
                   "standings_records", "history_screen", "franchise_history", "speed_threshold", "cpu_clock2",
                   "cpu_runner_vision", "catch_snap_limit", "scramble_blocking", "audible_legend", "team_ratings",
                   "roster_draft_pick_ownership", "roster_hback_roles", "modern_injured_reserve")

# --- disc resources the options add to the main heap (inventory of the RC disc against retail, decoded charges) ------
RESOURCE_BYTES = {
    "scorebug_runtime": 332_544,   # gamedata.iff: 34 appended TXTR and the grown HUD scene (BK: 331,264 + 1,280)
    "scorebug": 67_584,            # global.iff: five appended TXTR (the HUD fonts; attribution INFERRED)
    "hair_styles": 84_736,         # global.iff: hi_head +26,496, lo_body +9,856, nine 64x64 hair textures 48,384
    "kick_meter_2026": 6_784,      # gamedata.iff: the kick meter FONT
}

# --- the roster block ---------------------------------------------------------------------------------------------------
ROSTER_RETAIL = 0x91000 + 0x80       # 594,048 B in the main heap (BK, K1 lab)
ROSTER_GROWN = 0x92000 + 0x80        # 16 reserves or two extra created teams
ROSTER_CAPACITY = 0xCA000 + 0x80     # the capacity arena (4,096 records) the pack's roster edits ask for

# --- stadiums and kits (every bundle of the RC disc and of retail; largest of the nine time/weather variants) --------
# venue: (2026 name, RC charge, retail charge, the field that changes it in the RC)
VENUES = {
    "s00": ("State Farm Stadium", 2_695_552, 2_643_328, "modern_state_farm"),
    "s01": ("Mercedes-Benz Stadium", 2_437_760, 2_619_008, "modern_mercedes_benz"),
    "s02": ("M&T Bank Stadium", 2_806_016, 2_808_832, "modern_venues_2026"),
    "s03": ("Highmark Stadium", 2_530_816, 2_726_400, "modern_highmark"),
    "s04": ("Bank of America Stadium", 2_667_392, 2_676_224, "modern_venues_2026"),
    "s05": ("Soldier Field", 2_692_992, 2_692_992, "modern_venues_2026"),
    "s06": ("Paycor Stadium", 2_672_384, 2_681_600, "modern_venues_2026"),
    "s07": ("AT&T Stadium", 2_533_632, 2_533_888, "modern_att"),
    "s08": ("Empower Field at Mile High", 2_627_712, 2_551_552, "modern_venues_2026"),
    "s09": ("Ford Field", 2_787_968, 2_655_232, "modern_venues_2026"),
    "s10": ("Lambeau Field", 2_672_512, 2_672_512, "modern_lambeau"),
    "s11": ("Lucas Oil Stadium", 2_521_856, 2_535_680, "modern_lucas_oil"),
    "s12": ("EverBank Stadium", 2_435_584, 2_718_720, "modern_everbank"),
    "s13": ("GEHA Field at Arrowhead", 2_524_672, 2_536_064, "modern_venues_2026"),
    "s14": ("Hard Rock Stadium", 2_435_712, 2_705_792, "modern_hard_rock"),
    "s15": ("U.S. Bank Stadium", 2_580_352, 2_523_136, "modern_usbank"),
    "s16": ("Gillette Stadium", 2_151_552, 2_731_008, "modern_gillette"),
    "s17": ("Caesars Superdome", 2_743_680, 2_758_656, "modern_venues_2026"),
    "s18": ("MetLife Stadium (Giants)", 2_723_328, 2_735_232, "modern_metlife"),
    "s19": ("MetLife Stadium (Jets)", 2_697_600, 2_806_400, "modern_metlife_model"),
    "s20": ("Allegiant Stadium", 2_649_216, 2_701_952, "modern_allegiant"),
    "s21": ("Lincoln Financial Field", 2_743_168, 2_752_896, "modern_venues_2026"),
    "s22": ("Acrisure Stadium", 2_801_536, 2_726_400, "modern_venues_2026"),
    "s23": ("SoFi Stadium (Rams)", 2_580_352, 2_592_384, "modern_sofi"),
    "s24": ("SoFi Stadium (Chargers)", 2_580_480, 2_709_760, "modern_sofi"),
    "s25": ("Levi's Stadium", 2_490_496, 2_678_912, "modern_levis"),
    "s26": ("Lumen Field", 2_710_400, 2_720_640, "modern_venues_2026"),
    "s27": ("Raymond James Stadium", 2_724_480, 2_737_152, "modern_venues_2026"),
    "s28": ("Nissan Stadium", 2_680_576, 2_680_576, "modern_venues_2026"),
    "s29": ("Northwest Stadium", 2_686_208, 2_695_936, "modern_venues_2026"),
    "s30": ("Huntington Bank Field", 2_727_168, 2_594_688, "modern_venues_2026"),
    "s31": ("venue s31", 2_628_480, 2_628_480, "modern_venues_2026"),
    "s36": ("venue s36", 2_606_592, 2_606_592, None),
    "s37": ("NRG Stadium", 2_853_888, 2_727_936, "modern_venues_2026"),
    "s39": ("venue s39", 2_667_392, 2_667_392, "modern_venues_2026"),
    "s40": ("SoFi Stadium (event)", 2_373_760, 2_468_864, "modern_sofi"),
    "s41": ("venue s41", 2_481_152, 2_481_152, None), "s42": ("venue s42", 2_487_040, 2_487_040, None),
    "s43": ("venue s43", 2_532_480, 2_532_480, None), "s44": ("venue s44", 2_514_944, 2_514_944, None),
    "s45": ("venue s45", 2_534_528, 2_534_528, None),
}
PRACTICE_VENUE = ("s32", 1_855_488, 2_091_520, "modern_practice_field")   # practice only; no pregame intro
KIT = 2_729_728                  # every retail kit package, and the RC's primaries
# the RC's larger kit packages: BAL style 1 (a 2026 alternate) and the CHI, CLE and WAS sets; the CPU always wears
# style 0, a player can pick any offered style (nfl2k5_uniform_slots)
KITS_RETAIL = {"03h4": 2_770_688, "03a4": 2_770_688, "24h5": 2_770_688, "24a5": 2_770_688}
KITS_RC = {**KITS_RETAIL, "02h1": 2_859_648, "02a1": 2_859_648, "05h0": 2_740_736, "05a0": 2_740_736,
           "05h4": 2_740_736, "05a4": 2_740_736, "29a0": 2_740_736, "30h0": 2_740_736, "30a0": 2_740_736,
           "30h4": 2_740_736, "30a4": 2_740_736}
TEAMS = tuple(range(31)) + (37,)  # kit and venue numbers of the 32 clubs (s37 / 37: Houston)
ANCHOR_VENUE_CHARGE = 2_806_016  # s02ad in the RC (the anchor's own bundle)

# --- the SOFTDRINK 2K28 v0.9 pack plan the anchor was measured on (experimental preset + recipe_v09 overrides) ------
RC_ON = frozenset("""
abilities abilities_charge_stars_only abilities_lock_speedster abilities_right_stick_stars_only accelerated_clock
alien_prospect all_stadiums arc_by_distance audible_legend calendar_engine camera catch_slider chop_block_toggle
classic_teams coach_ai coach_career_fix coin_defer contract_college_guard coverage_hitch_brake coverage_slider
coverage_trail cpu_ball_carriers cpu_clock2 cpu_passer_iq cpu_qb_recheck cpu_qb_tiers cpu_qb_zone_windows crib_reclaim
crib_trophy_room db_ball_play decided_clock deep_zone_bail deep_zone_facing defensive_try depth_chart_rows depth_locks
depth_roles draft_ai dynamic_kickoff edge_rename elbow_options espn25_era_rules espn25_more_moments
espn25_named_previews espn25_rosters espn_marks_2026 espn_wipes_boards_2026 franchise_autosave franchise_draft_clock
franchise_economy franchise_edit_player franchise_practice hair_styles historic_rosters_2026 historic_stock_books
historic_teams_quick_game history_screen honors_page inbox_standings k128_memory k128_roster_heap kick_laces
kick_meter_2026 kick_rules kickoff_alignment letter_grades loader_wakeup_fix modern_allegiant modern_att
modern_board_kit modern_clock_led modern_coaches modern_color modern_everbank modern_everbank_construction modern_fans
modern_force_out modern_gillette modern_goalposts modern_hard_rock modern_helmets modern_highmark modern_levis
modern_lucas_oil modern_mercedes_benz modern_metlife modern_metlife_model modern_naming modern_officials
modern_practice_field modern_practice_field_team_logo modern_sofi modern_state_farm modern_surfaces modern_usbank
module_loader momentum_collisions momentum_contact music_shuffle music_unlock music_userlist my_career my_career_home
name_keyboard number_kerning option_defaults overtime pass_protection pass_rush_stats play_art_routes player_progress
player_progress_visible player_star position_pools position_row practice_injuries practice_squad practice_squad_screen
probowl_order progression protection_calls punter_holder qb_accuracy qb_spy quick_long_release rb_rename
realistic_flight resource_load_guard return_coverage returner_fix rookie_faces run_blocking scheme_labels scorebug
scorebug_runtime scramble_tuning screen_hooks season_2026 season_cap sim_cb_tackles sim_rb_injuries sim_realism
sim_stats sportscenter_lineup standings_records star_career star_retention team_column team_names_2026 team_ratings
team_sleeves the1wam_lineman_rating throw trophy_room weather_haze weekly_prep weekly_prep_cpu weekly_prep_remember
weekly_progression widescreen xemu_display_list_fix zone_drop_cap""".split())
RC_VALUES = {"momentum": 50, "momentum_collision_level": 50, "cpu_money_downs": "modern2", "cpu_scrambles": "modern",
             "team_number_scale": {"13A0": 1.1, "13H0": 1.1}, "modern_venues_2026": "2026 venue art",
             "roster_capacity": True, "roster_draft_pick_ownership": True, "roster_hback_roles": True}

# Options a 64 MB build cannot have. A plan field, except roster_capacity: roster edits whose document asks for the
# capacity arena (free_agent_capacity; see roster_capacity_records).
REQUIRES_128 = {
    "k128_memory": "It teaches the Xbox's 4627 kernel to use 128 MB at start-up. A 64 MB console has nothing to add, "
                   "hakuX has no real kernel to patch, and with the 128 MB start-up check the disc refuses to start "
                   "below 128 MB.",
    "k128_roster_heap": "It moves the roster into the memory above 64 MB, which a 64 MB machine does not have.",
    "k128_early": "It adds the upper 64 MB before the graphics memory is built: xemu at 128 MB only.",
    "roster_capacity": "These roster edits ask for the bigger roster (4,096 records, about 228 KB more), which the "
                       "build allows only with the 128 MB option. Use the retail-capacity roster edits.",
    "reserves_16": "The build pairs 16 reserves with the 128 MB start-up check: the lab's 64 MB bisect failed the "
                   "pregame intro with them.",
    "created_teams_extra": "The build pairs the extra created teams with the 128 MB start-up check: the lab's 64 MB "
                           "bisect failed the pregame intro with them.",
    "guardian_overlay": "Its main-heap cost needs the room the 128 MB roster heap frees; at 64 MB the pregame intro "
                        "failed in the lab.",
    "hires_pack": "2x textures cost 0.25 MB (one helmet) to 2.3 MB (both kits) per match; only K128's early form at "
                  "128 MB has that room.",
    "modern_injured_reserve": "Modern injured reserve keeps its code and its list of every club's injured players in "
                              "the extra executable sections (the scale-out), and the 64 MB profile is the legacy "
                              "layout, which has no room left for it. A 64 MB build keeps the 2004 injured reserve "
                              "(5 a club, season-ending) with the Pro Bowl guard.",
}

# A field and the sub-options that only matter with it; a suggestion turns the whole group off.
GROUPS = {"momentum": ("momentum_contact", "momentum_collisions"), "weekly_prep": ("weekly_prep_cpu", "weekly_prep_remember"),
          "deep_zone_facing": ("deep_zone_bail",), "cpu_qb_zone_windows": ("cpu_qb_recheck", "cpu_qb_tiers"),
          "coverage_trail": ("coverage_hitch_brake",), "my_career": ("my_career_home",),
          "player_progress": ("player_progress_visible",), "scorebug": ("scorebug_runtime",)}
OFF_VALUES = {"cpu_money_downs": "retail", "cpu_scrambles": "retail", "momentum": 0, "created_teams_extra": 0,
              "speed_threshold": 0, "modern_venues_2026": None, "team_number_scale": None}
# these never become suggestions: they cost room when off (the on-demand loader) or are required off already
NOT_SUGGESTED = frozenset(("module_loader", "resource_load_guard")) | frozenset(REQUIRES_128)


def rc_plan() -> dict:
    """The v0.9 pack's effective options (what the anchor measured), as a flat {field: value} dict."""
    return {**{f: True for f in RC_ON}, **RC_VALUES}


_ROSTER_CACHE: dict = {}


def roster_edits_summary(path) -> dict:
    """What a roster-edits document asks of memory: {"capacity_records": free_agent_capacity records (0: retail
    capacity, as mod_build reads it), "draft_pick_ownership": bool, "hback_roles": bool} (both XBE steps take the
    scale-out). Read once per file version."""
    empty = {"capacity_records": 0, "draft_pick_ownership": False, "hback_roles": False}
    if not path:
        return dict(empty)
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return dict(empty)
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _ROSTER_CACHE:
        got = dict(empty)
        try:
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
            if isinstance(document, dict):
                request = document.get("free_agent_capacity")
                value = request.get("records", 0) if isinstance(request, dict) else 0
                got["capacity_records"] = value if type(value) is int and value > 0 else 0
                got["draft_pick_ownership"] = document.get("draft_pick_ownership") is not None
                got["hback_roles"] = document.get("hback_roles") is not None
        except (OSError, ValueError):
            pass
        _ROSTER_CACHE[key] = got
    return dict(_ROSTER_CACHE[key])


def roster_capacity_records(path) -> int:
    """Records a roster-edits document's free_agent_capacity asks for (0: retail capacity), as mod_build reads it."""
    return roster_edits_summary(path)["capacity_records"]


def _preset(name) -> dict:
    if not name:
        return {}
    try:
        from . import mod_build
    except ImportError:
        return {}
    return dict(mod_build.PRESETS.get(name, {}))


def options(plan=None) -> dict:
    """A BuildPlan, a recipe ({"preset", "overrides"}) or a flat {field: value} dict as one flat dict; None: the pack."""
    if plan is None:
        return rc_plan()
    if is_dataclass(plan) and not isinstance(plan, type):
        out = {f.name: getattr(plan, f.name) for f in _dc_fields(plan)}
    elif isinstance(plan, dict):
        if isinstance(plan.get("overrides"), dict):
            out = _preset(plan.get("preset"))
            out.update(plan["overrides"])
        else:
            out = dict(plan)
    else:
        raise TypeError("plan must be a BuildPlan, a recipe dict or a {field: value} dict")
    if not {"roster_capacity", "roster_draft_pick_ownership", "roster_hback_roles"} <= set(out):
        summary = roster_edits_summary(out.get("roster_edits"))
        out.setdefault("roster_capacity", summary["capacity_records"] > 0)
        out.setdefault("roster_draft_pick_ownership", summary["draft_pick_ownership"])
        out.setdefault("roster_hback_roles", summary["hback_roles"])
    return out


def on(opts: dict, field: str) -> bool:
    value = opts.get(field)
    if field == "cpu_money_downs_modern2":
        return opts.get("cpu_money_downs") == "modern2"
    if field == "cpu_scrambles":
        return value == "modern"
    if field == "cpu_money_downs":
        return value not in (None, "", "retail")
    if field == "momentum":
        return type(value) in (int, float) and value > 0
    if field == "momentum_collisions":
        return bool(value) and bool(opts.get("momentum_collision_level"))
    return bool(value) and value != "retail"


def forced_off(plan=None, target_mb: int = 64) -> list:
    """The fields on in the plan that the target cannot have (REQUIRES_128 at 64 MB; nothing at 128 MB)."""
    _target(target_mb)
    opts = options(plan)
    return [f for f in REQUIRES_128 if target_mb == 64 and on(opts, f)]


def _target(target_mb):
    if target_mb not in TARGETS:
        raise ValueError("target_mb must be 64 or 128")


def _turn_off(opts: dict, fields) -> dict:
    out = dict(opts)
    for f in fields:
        out[f] = OFF_VALUES.get(f, False)
    return out


def _roster_heap(opts, target_mb) -> bool:
    return target_mb == 128 and on(opts, "k128_memory") and on(opts, "k128_roster_heap")


def owners(opts: dict) -> list:
    out = [o for o, fs in OWNER_FIELDS.items() if any(on(opts, f) for f in fs)]
    return out + list(INFRASTRUCTURE) if out else out


def xbe_resident(plan=None, target_mb: int = 64) -> int:
    """Boot-loaded bytes of the plan's executable (pages), by the allocator's layout rules."""
    opts = options(plan) if not isinstance(plan, dict) or "overrides" in plan else plan
    extra = XTLID_PRELOAD if on(opts, "depth_chart_rows") else 0
    if on(opts, "my_career") and on(opts, "my_career_home") and not on(opts, "module_loader"):
        extra += 3 * PAGE                      # Career Home's section is preloaded without the on-demand loader
    found = owners(opts)
    if not found:
        return RETAIL_RESIDENT + extra
    code = sum(OWNER_BYTES[o][0] + OWNER_BYTES[o][1] for o in found)
    read_only = sum(OWNER_BYTES[o][2] + OWNER_BYTES[o][3] for o in found)
    data = sum(OWNER_BYTES[o][4] for o in found)
    if "franchise_footer" in found and not _roster_heap(opts, target_mb):
        data += FRANCHISE_STATIC_BODY
    if not any(on(opts, f) for f in SCALEOUT_FIELDS):
        pages = _legacy_pages([o for o in found if o not in INFRASTRUCTURE])
        if pages:
            return RETAIL_RESIDENT + pages + extra
    overflow = max(0, code - CODE_V3_CAP) + max(0, read_only - RO_V3_CAP) + max(0, data - DATA_V3_CAP)
    pool = POOL_DOC + math.ceil(overflow / PAGE) * PAGE if overflow else 0
    return RETAIL_RESIDENT + LEGACY_SPACE + SCALEOUT_V3 + pool + extra


LEGACY_OWNERS = frozenset(("nfl2k5_boot_logo", "nfl2k5_dynamic_kickoff_relocated", "nfl2k5_scorebug_runtime",
                           "nfl2k5_defensive_try", "nfl2k5_momentum", "nfl2k5_zone_drop"))   # the beta-62 owners


def _legacy_pages(features) -> int:
    """Resident bytes of the legacy layout for these owners, or 0 when they need the scale-out: the allocator's own
    rules (nfl2k5_xbe_space _needs_scaleout, _legacy_allocations, _directory), replayed."""
    if any(o not in LEGACY_REQUESTS for o in features):
        return 0
    requests = sorted([LOGO_REQUEST] + [(f"nfl2k5_{o}", k, n, a) for o in features for k, n, a in LEGACY_REQUESTS[o]])
    names = {r[0] for r in requests}
    if names - LEGACY_OWNERS and names & (LEGACY_OWNERS - {LOGO_REQUEST[0]}):
        return 0                          # a beta-62 owner with a newer one: the scale-out
    if any(k == "read_only" for _o, k, _n, _a in requests):
        return 0                          # the legacy pages are code and data only
    cursors, extended = {"code": 0, "data": 0}, False
    new_owners = {"nfl2k5_defensive_try", "nfl2k5_momentum", "nfl2k5_zone_drop"}
    for _owner, kind, size, align in sorted(requests, key=lambda r: (r[0] in new_owners, r)):
        offset = (cursors[kind] + align - 1) & -align
        if offset // PAGE != (offset + size - 1) // PAGE:
            offset = (offset + PAGE - 1) & -PAGE       # a request never straddles a page
        if offset + size > PAGE * (2 if kind == "code" else 1):
            return 0
        extended |= kind == "code" and offset >= PAGE
        cursors[kind] = offset + size
    digest = hashlib.sha256(repr(requests).encode()).hexdigest()   # stands in for the code's SHA-256
    raw = json.dumps({"requests": requests, "code_sha256": digest}, sort_keys=True, separators=(",", ":")).encode()
    if extended:
        raw = zlib.compress(raw, 9)       # the code2 page: the directory is stored compressed
    if 12 + len(raw) > LEGACY_DIRECTORY_BYTES:
        return 0
    return 3 * PAGE if extended else 2 * PAGE


def roster_block(opts: dict, target_mb: int) -> int:
    """Main-heap bytes of the roster block (0 when K128's roster heap holds it at 128 MB)."""
    if _roster_heap(opts, target_mb):
        return 0
    if on(opts, "roster_capacity"):
        return ROSTER_CAPACITY
    if on(opts, "reserves_16") or on(opts, "created_teams_extra"):
        return ROSTER_GROWN
    return ROSTER_RETAIL


def venue_charge(opts: dict, venue: str) -> int:
    _name, rc, retail, field = VENUES[venue]
    return rc if field is None or on(opts, field) else retail


def _kit(code: str) -> int:
    return KITS_RC.get(code, KIT)


def _club_kit(team: int, side: str, uniforms: str):
    styles = (0,) if uniforms == "primary" else range(6)
    return max((_kit(f"{team:02d}{side}{s}"), -s, f"{team:02d}{side}{s}") for s in styles)[::2]   # ties: lowest style


_KIT_TABLES: dict = {}


def _kit_tables(uniforms: str):
    """(best home kit per club, away kits best first): the kits do not depend on the plan."""
    if uniforms not in _KIT_TABLES:
        home = {t: _club_kit(t, "h", uniforms) for t in TEAMS}
        away = sorted(((_club_kit(t, "a", uniforms), t) for t in TEAMS), key=lambda x: (-x[0][0], x[1]))
        _KIT_TABLES[uniforms] = (home, away)
    return _KIT_TABLES[uniforms]


def hardest_matchup(plan=None, uniforms: str = "any") -> dict:
    """The heaviest stadium plus kits of any game (uniforms "any": a player may pick any offered style; "primary":
    style 0, what the CPU wears). Delta: main-heap bytes beyond the anchor's M&T Bank, BAL home and HOU away."""
    if uniforms not in ("any", "primary"):
        raise ValueError('uniforms must be "any" or "primary"')
    opts = options(plan) if not isinstance(plan, dict) or "overrides" in plan else plan
    home_kits, away_kits = _kit_tables(uniforms)
    best = None
    for venue in VENUES:
        charge = venue_charge(opts, venue)
        number = int(venue[1:])
        for home in ((number,) if number in TEAMS else TEAMS):
            home_kit = home_kits[home]
            away_kit = next(kit for kit, team in away_kits if team != home)
            total = charge + home_kit[0] + away_kit[0]
            if best is None or total > best[0]:
                best = (total, venue, home_kit[1], away_kit[1])
    total, venue, home_kit, away_kit = best
    return {"venue": venue, "name": VENUES[venue][0], "home_kit": home_kit, "away_kit": away_kit,
            "venue_bytes": venue_charge(opts, venue), "kit_bytes": _kit(home_kit) + _kit(away_kit),
            "delta": total - (ANCHOR_VENUE_CHARGE + 2 * KIT)}


def heaps(room: int, export: int = ANCHOR["export"], *, capped: bool = False) -> dict:
    """0x84EB0 and 0x125700 for a main heap whose largest free block at setup is ``room``."""
    block = max(0, room - INGAME_RESERVE)
    if capped:
        block = min(block, INGAME_CAP)
    left = min(block, INGAME_CAP) - BLOCK_HEADER - export
    heap_a = max(0, min(HEAP_A_SIZE, left))
    rest = left - HEAP_A_SIZE
    heap_b = rest // UNIT * UNIT if rest >= UNIT else 0
    return {"room": room, "block": block, "left": left, "heap_a": heap_a, "heap_a_short": HEAP_A_SIZE - heap_a,
            "heap_b": heap_b, "dir_intro_fits": heap_b >= DIR_INTRO_BYTES}


def needed_room(export: int = ANCHOR["export"] + EXPORT_MARGIN, safety: int = SAFETY_MARGIN) -> int:
    """The smallest room at which heap B holds DIR_INTRO plus ``safety`` (no cap: 64 MB)."""
    return INGAME_RESERVE + BLOCK_HEADER + export + HEAP_A_SIZE + DIR_INTRO_BYTES + safety


def room(plan=None, target_mb: int = 64, matchup="hardest") -> tuple:
    """(room, matchup): the main heap's largest free block at game setup. matchup "hardest" (any uniform), "primary"
    (style 0 kits) or "anchor" (the measured Texans at Ravens, M&T Bank afternoon clear)."""
    _target(target_mb)
    opts = options(plan) if not isinstance(plan, dict) or "overrides" in plan else plan
    rc = rc_plan()
    value = ANCHOR["room"] + ANCHOR["resident"] - xbe_resident(opts, target_mb)
    for field, size in RESOURCE_BYTES.items():
        value += (int(on(rc, field)) - int(on(opts, field))) * size
    value -= roster_block(opts, target_mb)
    if target_mb == 128 and on(opts, "k128_memory") and on(opts, "k128_early"):
        value += EARLY_ARENA_GAIN
    if matchup == "anchor":
        game = {"venue": "s02", "name": VENUES["s02"][0], "home_kit": ANCHOR["home_kit"], "away_kit": ANCHOR["away_kit"],
                "venue_bytes": venue_charge(opts, "s02"), "kit_bytes": 2 * KIT,
                "delta": venue_charge(opts, "s02") - ANCHOR_VENUE_CHARGE}
    else:
        game = hardest_matchup(opts, "any" if matchup == "hardest" else matchup)
    return value - game["delta"], game


def _costed_fields(opts: dict) -> list:
    fields = {f for fs in OWNER_FIELDS.values() for f in fs} | set(RESOURCE_BYTES) | {"depth_chart_rows"}
    fields |= {v[3] for v in VENUES.values() if v[3]}
    fields.discard("cpu_money_downs_modern2")
    dependents = {d for ds in GROUPS.values() for d in ds}
    return sorted(f for f in fields - NOT_SUGGESTED - dependents if on(opts, f))


def option_costs(plan=None, target_mb: int = 64) -> dict:
    """{field: bytes}: the room at game setup each option on in the plan takes at the target, alone (turning it and
    its sub-options off, everything else kept; the hardest matchup is re-found each time). None: the v0.9 pack plan.
    Fields that cost nothing are left out. At 64 MB the plan's REQUIRES_128 fields are taken as off first."""
    _target(target_mb)
    opts = _turn_off(options(plan), forced_off(plan, target_mb))
    base, _ = room(opts, target_mb)
    out = {}
    for field in _costed_fields(opts):
        saved = room(_turn_off(opts, (field,) + GROUPS.get(field, ())), target_mb)[0] - base
        if saved > 0:
            out[field] = saved
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def predict(plan=None, target_mb: int = 64) -> dict:
    """Fits verdict for the plan at the target at its hardest matchup. Keys: fits, spare_bytes, over_bytes, hardest,
    suggestions [(field, bytes)], plus target_mb, room, block, heap_a, heap_b, dir_intro_bytes, margin, needed_room,
    primary_uniforms {...}, forced_off [fields], evidence, notes. At 64 MB the numbers are for the plan with its
    forced_off fields off (the build cannot have them); fits stays False while any of them is still on."""
    _target(target_mb)
    given = options(plan)
    forced = forced_off(given, target_mb)
    opts = _turn_off(given, forced)
    capped = _roster_heap(opts, target_mb)
    export = ANCHOR["export"] + EXPORT_MARGIN
    value, game = room(opts, target_mb, "hardest")
    got = heaps(value, export, capped=capped)
    need = needed_room(export)
    if capped:   # the block stops at 0x180000: heap B is at most what the cap leaves
        ok = got["heap_b"] - DIR_INTRO_BYTES >= SAFETY_MARGIN
        spare = max(0, got["heap_b"] - DIR_INTRO_BYTES - SAFETY_MARGIN)
        over = max(0, DIR_INTRO_BYTES + SAFETY_MARGIN - got["heap_b"])
    else:
        ok, spare, over = value >= need, max(0, value - need), max(0, need - value)
    suggestions, trial, left = [], dict(opts), over
    while left > 0:
        base = room(trial, target_mb)[0]
        best = None
        for field in _costed_fields(trial):
            group = (field,) + GROUPS.get(field, ())
            saved = room(_turn_off(trial, group), target_mb)[0] - base
            if saved > 0 and (best is None or saved > best[1]):
                best = (group, saved)
        if best is None:
            break
        group, saved = best
        suggestions.append((group[0], saved))
        suggestions.extend((g, 0) for g in group[1:] if on(trial, g))
        trial = _turn_off(trial, group)
        left -= saved
    primary_value, primary_game = room(opts, target_mb, "primary")
    primary = heaps(primary_value, export, capped=capped)
    notes = [f"MODELLED, anchored on EMU1's measured v0.9 RC heaps (Texans at Ravens, 128 MiB); no {target_mb} MB run "
             "of this plan exists.", f"Hardest game: {game['name']} ({game['venue']}), kits {game['home_kit']} "
             f"and {game['away_kit']}; the CPU's own uniforms (style 0) give heap B {primary['heap_b']:,} B."]
    if forced:
        notes.append("Off for this target first: " + ", ".join(forced) + ".")
    if target_mb == 64:
        notes.append("Unproven on a console and on hakuX; xemu at 128 MB is the recommended full experience.")
    return {"fits": bool(ok and not forced), "spare_bytes": spare, "over_bytes": over,
            "hardest": f"{game['name']} ({game['venue']})", "suggestions": suggestions,
            "target_mb": target_mb, "room": value, "block": got["block"], "heap_a": got["heap_a"],
            "heap_a_short": got["heap_a_short"], "heap_b": got["heap_b"], "dir_intro_bytes": DIR_INTRO_BYTES,
            "margin": got["heap_b"] - DIR_INTRO_BYTES, "needed_room": need, "safety_bytes": SAFETY_MARGIN,
            "matchup": game, "primary_uniforms": {"room": primary_value, "heap_b": primary["heap_b"],
                                                   "margin": primary["heap_b"] - DIR_INTRO_BYTES,
                                                   "hardest": f"{primary_game['name']} ({primary_game['venue']})"},
            "forced_off": forced, "evidence": EVIDENCE, "notes": notes}


# --- the recommended 64 MB profile ------------------------------------------------------------------------------------
# The allocator's legacy layout holds small code/data owners in two pages (+8,192 B), or three (+12,288 B) once the
# code spills into the third page, which also compresses its directory; anything more, any read-only request, a
# beta-62 owner mixed with newer ones or any SCALEOUT_FIELDS option takes the scale-out (+212,992 B). MEASURED:
# these 21 fields are 25 requests and +12,288 B (nfl2k5_xbe_space.apply on the retail XBE, 2026-11-03); one more
# owner (all_stadiums would fit instead of protection_calls, not with it) takes the scale-out.
PROFILE_64_PATCHES = ("contract_college_guard", "widescreen", "franchise_economy", "qb_accuracy", "pass_protection",
                      "run_blocking", "cpu_ball_carriers", "abilities", "cpu_qb_zone_windows", "cpu_qb_recheck",
                      "cpu_qb_tiers", "return_coverage", "practice_injuries", "star_retention", "modern_force_out",
                      "db_ball_play", "sim_cb_tackles", "cpu_passer_iq", "scramble_tuning", "weekly_progression",
                      "franchise_draft_clock", "coverage_slider", "protection_calls")
# trimmed beyond the space owners: the heavy disc resources and the SPECIAL rows' 80 KB .XTLID storage
PROFILE_64_TRIM = ("scorebug", "scorebug_runtime", "hair_styles", "kick_meter_2026", "depth_chart_rows",
                   "my_career_home", "module_loader")
# b780 hist1: in-place 2004 bug fixes the profile turns ON when a plan has them off (no allocation, no section: they
# cost nothing at 64 MB). The career history pool fix keeps a long franchise's totals whole and its pool collecting in
# 6,000-word chunks (nfl2k5_history_pool: six sites inside the history engine's own bytes).
# b780 mc1: the Franchise load user-team guard (three in-place sites, a retail crash path on a save with no human club).
PROFILE_64_ON = ("history_pool", "load_user_team_guard")
PSEUDO_FIELDS = frozenset(("roster_capacity", "roster_draft_pick_ownership", "roster_hback_roles",
                           "cpu_money_downs_modern2"))
PROFILE_64_ROSTER = ("roster edits at retail capacity without the draft_pick_ownership and hback_roles sections: "
                     "tools/nfl2k5_roster_retail_fit.py fit --drop-xbe-sections")


def recommended_64_profile(plan=None) -> dict:
    """{BuildPlan field: value} to set on the plan (None: the v0.9 pack) for the 64 MB profile: every REQUIRES_128
    field off, the heavy disc resources off, every space owner off except PROFILE_64_PATCHES, and the in-place 2004 fixes of
    PROFILE_64_ON on. In place features stay
    (2026 rosters, names, ratings, faces, coaches, uniforms, helmets, fans, officials, ESPN marks and wipes, the
    stadium models and the 2026 venue art, rules, sim and AI edits that need no allocation). The roster edits must be
    the retail-capacity file without the two XBE sections (PROFILE_64_ROSTER); that is a file, not a field."""
    opts = options(plan)
    keep = set(PROFILE_64_PATCHES)
    fields = set(REQUIRES_128) | {f for fs in OWNER_FIELDS.values() for f in fs} | set(SCALEOUT_FIELDS)
    fields |= set(PROFILE_64_TRIM) | {d for ds in GROUPS.values() for d in ds}
    out = {}
    for field in sorted(fields - keep - PSEUDO_FIELDS):
        if on(opts, field):
            out[field] = OFF_VALUES.get(field, False)
    for field in PROFILE_64_ON:
        if not on(opts, field):
            out[field] = True
    return out


def profile_64_plan(plan=None, *, roster_ready: bool = True) -> dict:
    """The plan with the 64 MB profile applied, as a flat dict; roster_ready: its roster edits are the retail-capacity
    file without the XBE sections (else the plan's own roster edits decide)."""
    out = {**options(plan), **recommended_64_profile(plan)}
    if roster_ready:
        out.update(roster_capacity=False, roster_draft_pick_ownership=False, roster_hback_roles=False)
    return out


def _main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SOFTDRINK 64 / 128 MB budget at game setup (MODELLED)")
    parser.add_argument("recipe", nargs="?", help="a recipe or {field: value} JSON (default: the v0.9 pack plan)")
    parser.add_argument("--target", type=int, default=64, choices=TARGETS)
    parser.add_argument("--profile", action="store_true", help="apply the recommended 64 MB profile first")
    args = parser.parse_args(argv)
    plan = json.loads(open(args.recipe, encoding="utf-8").read()) if args.recipe else None
    if args.profile:
        plan = profile_64_plan(plan)
    got = predict(plan, args.target)
    print(json.dumps({**got, "option_costs": option_costs(plan, args.target)}, indent=1, default=str))
    return 0 if got["fits"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
