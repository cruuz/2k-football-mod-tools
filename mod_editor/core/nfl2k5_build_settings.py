"""Portable, typed Build choices saved beside project edits, never game state."""
from copy import deepcopy
import math

FEATURE_KEYS = (
    "momentum_collisions", "momentum_collision_level", "read_option_runtime",
    "franchise_2026_rules", "senior_bowl", "senior_bowl_settings", "senior_bowl_seed",
    "guardian_overlay", "guardian_everyone_practice", "guardian_players",
    "my_career", "my_career_setup", "franchise_autosave", "crib_reclaim", "screen_hooks", "coverage_trail", "franchise_edit_player", "cpu_money_downs", "weekly_prep", "weekly_prep_cpu", "weekly_prep_remember", "modern_naming",
    "reserves_16", "created_teams_extra", "hires_families",
)
FEATURE_KEYS += (
    "throw", "max_deep_yards", "arc", "realistic_flight", "arc_by_distance", "catch_slider",
    "accel_ramp", "draft_ai", "returner_fix", "progression", "scheme_labels", "camera",
    "kick_rules", "kick_power", "kickoff_alignment", "xbe_space", "kickoff_relocated", "momentum",
    "momentum_contact", "defensive_try", "zone_drop_cap", "all_stadiums", "practice_squad_screen",
    "abilities", "abilities_off_week", "qb_spy", "calendar_engine", "coverage_slider",
    "scramble_tuning", "flatter_deep_ball", "chop_block_toggle", "dynamic_kickoff",
    "dynamic_kickoff_settings", "position_pools", "position_pools_keep_olb", "depth_chart_rows", "season_cap", "season_2026",
    "team_names_2026", "widescreen", "overtime", "team_column", "seven_on_seven", "team_history",
    "career_stats", "position_row", "probowl_order", "penalties", "uniform_choice", "kick_laces",
    "franchise_practice", "practice_squad", "depth_locks", "prospect_names", "player_star",
    "player_tags", "roster_edits", "espn25_plan", "espn25_rosters", "playbook_packs", "screen_timing", "depth_roles", "edge_rename",
    "hires_pack", "hires_folder", "hires_scale", "hires_target", "guardian_cap", "scorebug",
    "scorebug_runtime", "scorebug_folder", "music_policy", "music_unlock", "music_userlist",
    "music_project", "music_library", "commentary", "name", "author", "notes",
)
MUSIC_KEYS = ("music_shuffle", "music_shuffle_selection")


def defaults():
    from .mod_build import BuildPlan
    plan = BuildPlan("", "")
    return {key: deepcopy(getattr(plan, key)) for key in FEATURE_KEYS}


def build_settings(value):
    from . import nfl2k5_music_playlist as music, nfl2k5_throw_tuning as tt
    from . import nfl2k5_senior_bowl as bowl, nfl2k5_hires_pack as hires
    tt._require(type(value) is dict and set(value) <= set(FEATURE_KEYS + MUSIC_KEYS),
                "Unsupported Build settings")
    result = music.build_settings({key: value[key] for key in MUSIC_KEYS if key in value})
    choices = {**defaults(), **deepcopy({key: value[key] for key in FEATURE_KEYS if key in value})}
    expected = defaults()
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
    values["commentary"] = [CommentarySwap(**row) for row in values.get("commentary", [])]
    return BuildPlan(source, target, **values)
