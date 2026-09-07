"""Portable, typed Build choices saved beside project edits, never game state."""
from copy import deepcopy

FEATURE_KEYS = (
    "momentum_collisions", "momentum_collision_level", "read_option_runtime",
    "franchise_2026_rules", "senior_bowl", "senior_bowl_settings", "senior_bowl_seed",
    "guardian_overlay", "guardian_everyone_practice", "guardian_players",
    "my_career", "my_career_setup", "crib_reclaim", "screen_hooks", "modern_naming",
    "reserves_16", "created_teams_extra", "hires_families",
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
