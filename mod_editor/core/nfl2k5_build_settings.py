"""Portable, typed Build choices saved beside project edits, never game state."""
from copy import deepcopy
from decimal import Decimal
import math

FEATURE_KEYS = (
    "momentum_collisions", "momentum_collision_level", "read_option_runtime",
    "franchise_2026_rules", "senior_bowl", "senior_bowl_settings", "senior_bowl_seed",
    "guardian_overlay", "guardian_everyone_practice", "guardian_players",
    "my_career", "my_career_setup", "franchise_autosave", "crib_reclaim", "trim_intro_videos", "screen_hooks", "coverage_trail", "coverage_hitch_brake", "franchise_edit_player", "cpu_money_downs", "accelerated_clock", "accelerated_clock_minimum_seconds", "weekly_prep", "weekly_prep_cpu", "weekly_prep_remember", "playbook_pair", "deep_zone_facing", "deep_zone_bail", "deep_zone_bail_calls", "modern_naming",
    "reserves_16", "created_teams_extra", "hires_families",
)
FEATURE_KEYS += (
    "throw", "max_deep_yards", "arc", "realistic_flight", "arc_by_distance", "catch_slider",
    "accel_ramp", "draft_ai", "returner_fix", "progression", "franchise_economy", "scheme_labels", "camera",
    "kick_rules", "kick_power", "kickoff_alignment", "xbe_space", "kickoff_relocated", "momentum",
    "momentum_contact", "defensive_try", "zone_drop_cap", "all_stadiums", "practice_squad_screen",
    "abilities", "abilities_off_week", "abilities_lock_right_stick", "abilities_lock_special_moves", "abilities_lock_speedster",
    "abilities_right_stick_stars_only", "abilities_button_moves_stars_only", "abilities_charge_stars_only", "abilities_star_access",
    "qb_spy", "calendar_engine", "coverage_slider",
    "scramble_tuning", "flatter_deep_ball", "chop_block_toggle", "dynamic_kickoff",
    "dynamic_kickoff_settings", "position_pools", "position_pools_keep_olb", "depth_chart_rows", "season_cap", "season_2026",
    "team_names_2026", "widescreen", "overtime", "team_column", "seven_on_seven", "team_history",
    "career_stats", "position_row", "probowl_order", "elbow_options", "the1wam_lineman_rating", "xemu_display_list_fix", "resource_load_guard", "loader_wakeup_fix", "rb_rename", "name_keyboard", "penalties", "uniform_choice", "team_sleeves", "helmet_finish", "kick_laces", "punter_holder",
    "franchise_practice", "practice_squad", "depth_locks", "prospect_names", "player_star",
    "player_tags", "roster_edits", "espn25_plan", "espn25_rosters", "playbook_packs", "screen_timing", "depth_roles", "edge_rename",
    "hires_pack", "hires_folder", "hires_scale", "hires_target", "guardian_cap", "scorebug",
    "scorebug_runtime", "scorebug_folder", "scorebug_watermark", "indicator_names_folder", "indicator_names_style", "music_policy", "music_unlock", "music_userlist",
    "music_project", "music_library", "commentary", "name", "author", "notes",
)
FEATURE_KEYS += ("weather_plan", "weather_haze", "coin_defer", "decided_clock",
                 "decided_clock_margin", "decided_clock_seconds", "cpu_scrambles", "modern_color",
                 "modern_color_settings", "modern_arrowhead", "modern_metlife")
FEATURE_KEYS += ("modern_metlife_model",)  # b76-u5: MetLife Stadium as a new model
FEATURE_KEYS += ("modern_helmets",)  # b76-hm: modern helmets and facemasks
FEATURE_KEYS += ("modern_sofi",)  # b76-u6: SoFi Stadium for the Rams and Chargers
FEATURE_KEYS += ("modern_highmark",)  # b76-st: the new Highmark Stadium for the Bills
FEATURE_KEYS += ("modern_att",)  # b76-st2: AT&T Stadium for the Cowboys
FEATURE_KEYS += ("modern_levis",)  # b76-st2: Levi's Stadium for the 49ers
FEATURE_KEYS += ("modern_allegiant",)  # b76-st2: Allegiant Stadium for the Raiders
FEATURE_KEYS += ("modern_mercedes_benz",)  # b76-st2: Mercedes-Benz Stadium for the Falcons
FEATURE_KEYS += ("modern_usbank",)  # b76-st3: U.S. Bank Stadium for the Vikings
FEATURE_KEYS += ("modern_lucas_oil",)  # b76-st3: Lucas Oil Stadium for the Colts
FEATURE_KEYS += ("modern_state_farm",)  # b76-st3: State Farm Stadium for the Cardinals
FEATURE_KEYS += ("modern_hard_rock",)  # b76-st4: Hard Rock Stadium for the Dolphins
FEATURE_KEYS += ("modern_gillette",)  # b76-st4: Gillette Stadium for the Patriots
FEATURE_KEYS += ("modern_lambeau",)  # b76-st4: Lambeau Field for the Packers
FEATURE_KEYS += ("modern_everbank",)  # b76-st4: EverBank Stadium for the Jaguars
FEATURE_KEYS += ("modern_everbank_construction",)  # b76-st4: its 2026 construction (on by default)
FEATURE_KEYS += ("modern_board_kit",)  # b76-st5: the modern stadium boards on the retail stadiums (tier 2)
FEATURE_KEYS += ("modern_practice_field",)  # b76-pf: a modern outdoor NFL practice facility (s32)
FEATURE_KEYS += ("modern_practice_field_team_logo",)  # b76-pf P1: the practicing team's logo at midfield
FEATURE_KEYS += ("modern_surfaces",)  # b76-tf: modern playing surfaces in every home field
FEATURE_KEYS += ("custom_intro",)  # b76-i1: movie path for the Custom intro video option, "" = off
FEATURE_KEYS += ("espn_marks_2026", "official_marks_pack")  # b76 p1: ESPN presentation marks (2026)
FEATURE_KEYS += ("number_kerning",)  # b76-k2: the jersey 1 kerned in two-digit numbers
FEATURE_KEYS += ("espn_wipes_boards_2026",)  # b76-p2: ESPN 2026 wipes and boards
FEATURE_KEYS += ("kick_meter_2026",)  # b76-km: the kick meter in the 2026 ESPN bar's look
FEATURE_KEYS += ("modern_goalposts",)  # b77-v1: the uprights 35 ft above the crossbar (NFL since 2014)
FEATURE_KEYS += ("modern_coaches",)  # b77-co1: the 2026 head coaches (sideline look, faces, DAL/WAS pictures)
FEATURE_KEYS += ("cpu_qb_zone_windows", "cpu_qb_recheck", "cpu_qb_tiers", "db_ball_play")  # b776-ai2: CPU AI late executable owners, off in every preset
FEATURE_KEYS += ("db_dive_window",)  # b780-cv3: defenders leap only for balls they can reach, the last late executable owner
FEATURE_KEYS += ("hair_styles",)  # b775-hs1: added hair models chosen per player (roster +0x0D), late executable owner
FEATURE_KEYS += ("helmet_side_numbers",)  # b81 helmet-sides: route 5 = helmet number set E (both sides), Chargers 24H0/24A0
FEATURE_KEYS += ("modern_numbers",)  # b81 modern numbers: None (follow season_2026), "modern" or "retail"
FEATURE_KEYS += ("classic_crowd",)  # b81-seamen: the classic Seamen's own crowd (12 files + one fixed allocator page)
FEATURE_KEYS += ("play_art_routes",)  # b776-pa2: play art routes at their real length, late executable owner
FEATURE_KEYS += ("run_blocking",)  # b777-ol1: run blocking, the last late executable owner
FEATURE_KEYS += ("pass_protection",)  # b778-pr1: pass protection, a late executable owner
FEATURE_KEYS += ("pass_rush_stats",)  # b779-st1: pressures / QB hits / allowed stats, a late executable owner (b779-int1: key was missing)
FEATURE_KEYS += ("history_screen",)  # b780-j4: franchise History screen, box scores and game log, a late executable owner
FEATURE_KEYS += ("cpu_passer_iq",)  # b780 a-passer: CPU quarterbacks throw on time and check down, a late executable owner
FEATURE_KEYS += ("cpu_clock2", "cpu_clock2_overtime")  # b780 b-clock: modern CPU clock management, a late executable owner
FEATURE_KEYS += ("intro_autoskip",)  # b780-mem1: the pregame intro skips itself when its director could not load
FEATURE_KEYS += ("protection_calls",)  # b780 p1-slide: the user's slide call at the line (L / R in the audible menu), late executable owner
FEATURE_KEYS += ("team_number_scale",)  # b776-ns1: per-kit jersey number size {kit: scale}, late executable owner
FEATURE_KEYS += ("qb_accuracy",)  # b777-qb3: accurate short and on-the-run throws by Pass Accuracy, late executable owner
FEATURE_KEYS += ("star_retention",)  # b778-fa1: CPU clubs keep their stars (veteran cap cut), late executable owner
FEATURE_KEYS += ("team_building",)  # b81: CPU clubs draft and sign to their weakest starters (shared need rule)
FEATURE_KEYS += ("practice_injuries",)  # b778-pi1: franchise practice keeps injuries, late executable owner
FEATURE_KEYS += ("cpu_ball_carriers",)  # b778-ai5: CPU ball carriers stay in bounds / QBs slide past the sticks
FEATURE_KEYS += ("cpu_runner_vision",)  # b780 cv2-runner: CPU ball carriers see where defenders go (needs cpu_ball_carriers)
FEATURE_KEYS += ("return_coverage",)  # b778-kr1: return coverage pursuit angles, late owner
FEATURE_KEYS += ("modern_force_out",)  # b778-fo1: modern sideline catches (no force-out from 2008), late executable owner
FEATURE_KEYS += ("crib_trophy_room",)  # b778-xs1: the Crib keeps only the Trophy Room side (shop cut), in place
FEATURE_KEYS += ("module_loader",)  # b778-xs1: on-demand Career Home (module loader prototype), late executable owner, off
FEATURE_KEYS += ("star_career",)  # b778-st2: rookie stars and stars earned/lost over a career, late executable owner
FEATURE_KEYS += ("rookie_faces",)  # b778-rh1: new draft headshots matched to skin tone, build and name (image only)
FEATURE_KEYS += ("alien_prospect",)  # b778-ee1: the once-in-a-century gray alien prospect (needs rookie faces)
FEATURE_KEYS += ("backfield_cards",)
FEATURE_KEYS += ("gadget_play",)  # beta 81 Q62: the SPECIAL GAD player on gadget plays
FEATURE_KEYS += ("sportscenter_lineup",)  # b778-sc2: featured-player identity lookup, no allocation
FEATURE_KEYS += ("franchise_draft_clock",)  # b778-dr1: broadcast-paced franchise draft, late executable owner
FEATURE_KEYS += ("weekly_progression",)  # b778-pg1: franchise weekly progression, late executable owner
FEATURE_KEYS += ("trophy_room",)  # b778-pg2: the Crib display name
FEATURE_KEYS += ("player_progress", "player_progress_visible")  # b778-pg2/pg3: Player Progress screen/row, late executable owner
FEATURE_KEYS += ("franchise_history",)  # b780 j23: franchise history and records footer, late executable owner
FEATURE_KEYS += ("contract_college_guard",)  # b778-cr1: Contracts null-college crash guard, late executable owner
FEATURE_KEYS += ("load_user_team_guard",)  # b780 mc1: Franchise load with no human club, in-place sites
FEATURE_KEYS += ("save_list_type_guard",)  # b780 mc1: boot save list with a NULL save type, in-place sites
FEATURE_KEYS += ("show_block_guard",)  # b81 ot-crash: the show and the replay share one block, in-place sites
FEATURE_KEYS += ("edition_save_notes",)  # beta 81 review M1: 64 MB save messages for a 128 MB save, in-place text
FEATURE_KEYS += ("coach_career_fix",)  # b780 c1 (wired at b780-int): coach Super Bowl trip counter fix, in-place site
FEATURE_KEYS += ("history_pool",)  # b780 hist1: career history pool (no wrapped totals, chunked collection), in-place sites
FEATURE_KEYS += ("sim_cb_tackles",)  # b778-cb1: cornerback tackle credit, late executable owner
FEATURE_KEYS += ("sim_rb_injuries",)  # b779-sim2: weekly RB injury roll and simulated-game carry guard
FEATURE_KEYS += ("sim_realism",)  # b779-sim2 r4: scheduled-sim season realism, late executable owner
FEATURE_KEYS += ("sim_qb_injuries", "sim_qb_injury_rate")
FEATURE_KEYS += ("sim_breakaway_stop",)  # b81 scoring: the simulated breakaway stop, yards to goal (default 68 since the combined calibration)
FEATURE_KEYS += ("qb_room",)  # b81 qb34: None follows sim_qb_injuries (DESIGN_CHANGES C1)
FEATURE_KEYS += ("coach_carousel",)  # b780-c6: the coaching carousel, late executable owner + roster pool
FEATURE_KEYS += ("standings_records",)  # b780-j1: Team Standings division / conference / home / road records, late executable owner
FEATURE_KEYS += ("catch_snap_limit",)  # b780-cv4: CPU defenders cannot slide to the ball for a pick, late executable owner
FEATURE_KEYS += ("speed_threshold",)  # b780-cv5: speed separation strength 0..100 on deep routes, late executable owner (0 = off)
FEATURE_KEYS += ("scramble_blocking",)  # b780-cv7: receivers block for a scrambling QB, late executable owner (test)
FEATURE_KEYS += ("injured_reserve_guard", "modern_injured_reserve")  # b780 IR1: the Pro Bowl IR guard (in place) and modern injured reserve (late executable owner)
FEATURE_KEYS += ("audible_legend",)  # b780-p3: audible panel button legend (late executable owner; the lift follows the bar)
FEATURE_KEYS += ("sim_stats",)  # b778-sim1: simulated franchise game pace (in place, no allocation)
FEATURE_KEYS += ("quick_long_release",)  # b780-c-release: quicker deep and rollout throws (constants only, in place, no allocation)
FEATURE_KEYS += ("option_defaults", "default_quarter_minutes", "default_sim_quarter_minutes")  # b779-df1: fresh-profile default options (in place, no allocation)
FEATURE_KEYS += ("modern_clock_led",)  # b778-sd4: LED play clock and score digits, late executable owner
FEATURE_KEYS += ("inbox_standings",)  # b778-pc3: inbox story 23 standings setup (pointer-only edit)
FEATURE_KEYS += ("modern_fans",)  # b77-fr1: the 2026 fans of the crowd-reaction cutaways
FEATURE_KEYS += ("modern_officials",)  # b77-rf1: the 2025-26 NFL officials' uniform
FEATURE_KEYS += ("modern_venues_2026",)  # b76-u4: folder of 2026 team venue art, "" = off
FEATURE_KEYS += ("historic_teams_quick_game",)  # b76-h1: historic teams in Quick Game Team Select
FEATURE_KEYS += ("historic_rosters_2026",)  # ht: held until all source/routing gaps are resolved
FEATURE_KEYS += ("classic_teams",)  # b775-ct1: Anniversary and classic team-seasons in Quick Game
FEATURE_KEYS += ("kickoff_return_blocking",)  # b76-vb3 E1: return blockers claim distinct men after the catch (test)
FEATURE_KEYS += ("espn25_more_moments", "historic_stock_books", "espn25_named_previews", "espn25_era_rules")  # b76-m1: 25 more ESPN 25th Anniversary moments
FEATURE_KEYS += ("k128_memory", "k128_roster_heap", "k128_early")  # b76-k1: 128 MB memory (K128), the roster heap, the early form
FEATURE_KEYS += ("letter_grades",)  # b77-f4: letter grades in Franchise (allocator owner, late)
FEATURE_KEYS += ("coach_ai",)  # preserved as an explicit editable Build setting
FEATURE_KEYS += ("honors_page", "honors_history")  # b77-f5: Player Card honors page (allocator owner, late) and its award history
FEATURE_KEYS += ("contract_college_guard",)  # b778-cr1: Player Contracts null-college screen guard (late owner)
FEATURE_KEYS += ("my_career_home",)  # ui1: MyCareer Career Home (default on with MyCareer)
FEATURE_KEYS += ("super_bowl_user_art",)  # b773-sb2: Super Bowl logos folder; "" = the bundled real logos (sb3)
FEATURE_KEYS += ("console_memory",)  # b780-m64b: 128 (default, absent in older projects) or 64 (experimental)
PROJECT_KEYS = ("softdrink_project", "include_softdrink_project")
FEATURE_KEYS += ("stock_age_policy",)
MUSIC_KEYS = ("music_shuffle", "music_shuffle_selection")


def defaults():
    from .mod_build import BuildPlan
    plan = BuildPlan("", "")
    return {key: deepcopy(getattr(plan, key)) for key in FEATURE_KEYS}

def validate_sim_qb_injuries(mode, rate):
    if mode not in (None, "retail", "realistic", "custom"):
        raise ValueError("Choose Retail, Realistic or Custom for simulated quarterback injuries.")
    if mode == "custom":
        if type(rate) not in (float, int) or not 0 <= rate <= 100:
            raise ValueError("Custom quarterback injury chance must be between 0.000 and 100.000 percent.")
        thousandths = Decimal(str(rate)) * 1000
        if thousandths != thousandths.to_integral_value():
            raise ValueError("Use increments of 0.001 percentage points for the custom quarterback injury chance.")


def validate_sim_breakaway_stop(value):
    if type(value) is not int or not 20 <= value <= 99:
        raise ValueError("The simulated breakaway stop is a whole number of yards to goal from 20 to 99.")
QB_ROOM_LEVELS = (None, "retail", "realistic")


def validate_qb_room(level):
    """b81 qb34: the quarterback room has no Custom level."""
    if level not in QB_ROOM_LEVELS:
        raise ValueError("Choose Retail or Realistic for the quarterback room rules.")


def qb_room_level(qb_room, sim_qb_injuries):
    """b81 qb34 (DESIGN_CHANGES C1): an explicit Retail or Realistic wins; otherwise the room follows the simulated
    quarterback injury option (Realistic or Custom -> Realistic, Retail -> Retail, keep the source -> keep). A followed
    Realistic is installed only where the room's needs are met (see qb_room_needs_met and mod_build)."""
    validate_qb_room(qb_room)
    if qb_room is not None:
        return qb_room
    return {"realistic": "realistic", "custom": "realistic", "retail": "retail"}.get(sim_qb_injuries)


def qb_room_needs_met(get):
    """b81 qb34: a plan (``get(field)``) that installs the room's needs: the 128 MB standard target with K128, depth
    chart locks and the SPECIAL depth chart rows (which carry the lineup roles). A missing console_memory is 128."""
    return (get("console_memory") in (None, 128) and bool(get("k128_memory")) and bool(get("depth_locks"))
            and bool(get("depth_chart_rows")))


def build_settings(value):
    from . import nfl2k5_music_playlist as music, nfl2k5_throw_tuning as tt
    from . import nfl2k5_senior_bowl as bowl, nfl2k5_hires_pack as hires
    tt._require(type(value) is dict and set(value) <= set(FEATURE_KEYS + MUSIC_KEYS + PROJECT_KEYS),
                "Unsupported Build settings")
    result = music.build_settings({key: value[key] for key in MUSIC_KEYS if key in value})
    for key, expected_type in zip(PROJECT_KEYS, (str, bool)):
        if key in value:
            tt._require(type(value[key]) is expected_type, f"Invalid league artwork setting: {key}")
            result[key] = value[key]
    expected = defaults()
    choices = {**expected, **deepcopy({key: value[key] for key in FEATURE_KEYS if key in value})}
    if choices["sim_qb_injuries"] != "custom":
        choices["sim_qb_injury_rate"] = expected["sim_qb_injury_rate"]
    validate_sim_qb_injuries(choices["sim_qb_injuries"], choices["sim_qb_injury_rate"])
    validate_sim_breakaway_stop(choices["sim_breakaway_stop"])
    validate_qb_room(choices["qb_room"])
    tt._require(choices["helmet_finish"] in ("glossy", "matte"), "Helmet finish must be glossy or matte")
    from . import nfl2k5_modern_color as colour
    colour.normalize_settings(choices["modern_color_settings"])
    from . import nfl2k5_team_number_scale as number_scale
    choices["team_number_scale"] = number_scale.normalize(choices["team_number_scale"])
    tt._require(choices["scorebug_watermark"] in ("auto", "mnf", "off"), "ESPN watermark must be auto, mnf or off")
    tt._require(choices["stock_age_policy"] in ("preserve_age", "keep_birthdates"), "Unknown stock roster age policy")
    for key in FEATURE_KEYS:
        item, default = choices[key], expected[key]
        if type(default) is bool:
            tt._require(type(item) is bool, f"{key} must be true or false")
        elif type(default) is int:
            tt._require(type(item) is int, f"{key} must be a whole number")
        elif type(default) is float:
            tt._require(type(item) in (int, float) and math.isfinite(item), f"{key} must be a finite number")
        elif type(default) is str:
            tt._require(type(item) is str, f"{key} must be text")
        elif type(default) in (list, tuple):
            tt._require(type(item) in (list, tuple), f"{key} must be a list")
            choices[key] = list(item)
        elif type(default) is dict:
            tt._require(type(item) is dict, f"{key} must be an object")
    for key in ("music_project", "music_library", "my_career_setup"):
        tt._require(choices[key] is None or type(choices[key]) is str, f"{key} must be a path or None")
    tt._require(choices["screen_timing"] in (None, "A", "B", "C", "D"), "Screen timing must be A, B, C, D or None")
    tt._require(0 <= choices["speed_threshold"] <= 100, "Speed separation must be a whole number from 0 to 100")  # b780-cv5
    tt._require(choices["console_memory"] in (128, 64), "Console memory must be 128 or 64 (MB)")  # b780-m64b
    week = choices["abilities_off_week"]
    tt._require(week is None or type(week) is int and 0 <= week <= 17, "Abilities off week must be 0..17 or None")
    for key in ("player_tags", "playbook_packs"):
        tt._require(all(type(item) is str for item in choices[key]), f"{key} entries must be text")
    tt._require(all(type(row) is dict and set(row) == {"stream", "wav"} and all(type(v) is str for v in row.values())
                    for row in choices["commentary"]), "Commentary entries must name a stream and WAV path")
    tt._validate_r62_options(**{key: choices[key] for key in tt.R62_RUNTIME_KEYS
                               if key in choices and key != "my_career_setup"})
    bowl.Settings.from_dict(choices["senior_bowl_settings"])
    bowl._integer(choices["senior_bowl_seed"], 0, 2147483647, "Senior Bowl seed")
    setup = choices["my_career_setup"]
    tt._require(setup is None or type(setup) is str, "MyCareer setup must be a path or None")
    players = choices["guardian_players"]
    tt._require(players is None or type(players) is list and all(
        type(row) is dict and set(row) == {"pool", "index", "record_sha256"}
        and type(row["pool"]) is str and type(row["index"]) is int and row["index"] >= 0
        and type(row["record_sha256"]) is str and len(row["record_sha256"]) == 64
        and all(c in "0123456789abcdef" for c in row["record_sha256"]) for row in players),
        "Guardian players require exact pool, index and record SHA-256 pins")
    families = choices["hires_families"]
    tt._require(type(families) in (list, tuple), "Hi-res families must be a list or tuple")
    tt._require(len(families) == len(set(families)) and set(families) <= set(hires.FAMILIES),
                "Unknown or duplicate hi-res families")
    choices["hires_families"] = list(families)
    for key in FEATURE_KEYS:
        if key in value:
            result[key] = choices[key]
    return deepcopy(result)


def from_plan(plan):
    """Store the effective plan without source, destination or overwrite permission."""
    return build_settings(plan.to_recipe())


def to_plan(state, source, target):
    """Reconstruct choices in a new build; never inherit overwrite permission."""
    from .mod_build import BuildPlan, CommentarySwap
    values = build_settings(state)
    for key in PROJECT_KEYS:
        values.pop(key, None)
    values["commentary"] = [CommentarySwap(**row) for row in values.get("commentary", [])]
    return BuildPlan(source, target, **values)

FEATURE_KEYS += ("team_ratings",)  # Dynamic modern team rating getters.


# b780 studio1 (Q60): every "this box needs that box" rule between the Build and Game Fixes boxes, in ONE table (moved here
# from mod_editor/gui/beta62_options.py by b780 m64prof, which the pages still import it through). Each child lists the
# parents it needs: ticking a child ticks its parents that can be ticked, unticking a parent unticks its children, and the
# build refuses a child whose parent is missing.
REQUIRES = {
    "coverage_hitch_brake": ("coverage_trail",),
    "weekly_prep_cpu": ("weekly_prep",),
    "weekly_prep_remember": ("weekly_prep",),
    "k128_roster_heap": ("k128_memory",),
    "k128_early": ("k128_memory",),
    "espn25_named_previews": ("espn25_more_moments",),
    "espn25_era_rules": ("espn25_more_moments", "dynamic_kickoff", "defensive_try", "overtime"),
    "historic_rosters_2026": ("historic_teams_quick_game",),
    "classic_teams": ("historic_teams_quick_game",),  # b775-ct1
    "cpu_clock2_overtime": ("cpu_clock2",),  # b780 b-clock: the overtime window extends the modern clock rules
    "cpu_runner_vision": ("cpu_ball_carriers",),  # b780 cv2-runner: its wider sideline limit is cpu_ball_carriers' taper
}
# b780 m64prof: values that mean something only with another option on; the build refuses them otherwise
# (nfl2k5_momentum._settings: "a collision level requires momentum_collisions", "contact requires a nonzero momentum level").
VALUE_REQUIRES = {
    "sim_qb_injuries": ("sim_realism", "k128_memory"),
    "momentum_collision_level": ("momentum_collisions",),
    "momentum_contact": ("momentum",),
}


def build_requires():
    """{option: the options it needs} for every dependency rule the build applies: REQUIRES and VALUE_REQUIRES."""
    return {**REQUIRES, **VALUE_REQUIRES}
