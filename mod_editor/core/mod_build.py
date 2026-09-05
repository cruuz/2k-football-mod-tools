"""One build plan → one patched copy → one receipt.

Every patch the studio can make today is a byte-level edit of a COPY of the user's disc image:
the throw curve tables, the executable caves (Catching/Interception sliders, acceleration ramp,
franchise draft AI), the DE→EDGE strings, the ESPN scorebug bar with its textures, commentary
line swaps.  Until now each lived behind its own panel and its own copy step.  ``build`` applies a
whole :class:`BuildPlan` to one copy in a fixed order, streams progress, and returns a receipt
that the mod-pack exporter can store as the pack's recipe.

The modules that are still being written by other work streams (EDGE rename, commentary swap)
are imported lazily and reported as "unavailable" when absent, so this file never breaks the
studio while they land.
"""

from __future__ import annotations

import importlib
import json
import os

from mod_editor.core import platform_compat
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from . import nfl2k5_throw_tuning as tt

ProgressSink = Callable[[str, int, int], None]
ROOT = Path(__file__).resolve().parents[2]
PACK0_SIZE = 193_710_080   # vc_53450030/0 (retail); the schedule template lives in its ROST resource


def _tools_module(name: str):
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 - optional module not present yet
        return None


def _core_module(name: str):
    try:
        return importlib.import_module(f"mod_editor.core.{name}")
    except Exception:  # noqa: BLE001
        return None


def _scorebug_art_available() -> bool:
    module = _core_module("nfl2k5_scorebug_source_art")
    if module is None:
        return False
    try:
        return bool(module.available())
    except Exception:  # noqa: BLE001
        return False


UNIFORM_CHOICE_MODES = ("", "rule", "choice")


def uniform_choice_mode(value: object) -> str:
    """``BuildPlan.uniform_choice`` normalised: a bare checkbox True means the in-game choice form."""

    if value is True:
        return "choice"
    if not value:
        return ""
    mode = str(value)
    if mode not in UNIFORM_CHOICE_MODES:
        raise ValueError(f"uniform_choice must be one of {UNIFORM_CHOICE_MODES}, not {value!r}")
    return mode


@dataclass
class CommentarySwap:
    stream: str            # bank/stream id as the commentary tool names it
    wav: str               # path to the replacement WAV


@dataclass
class BuildPlan:
    source: str
    target: str
    overwrite: bool = False
    # gameplay
    throw: bool = False
    max_deep_yards: float = 55.0
    arc: float = 0.0
    realistic_flight: bool = False
    arc_by_distance: bool = False   # 45-60 yd lobs hang high, 61+ stay flat
    catch_slider: bool = False
    accel_ramp: bool = False
    draft_ai: bool = False
    returner_fix: bool = False
    progression: bool = False
    scheme_labels: bool = False   # depth-chart slot labels by scheme: 4-3 SAM/MIKE/WILL, 3-4 EDGE/MIKE/WILL/NT
    camera: bool = False          # Standard camera preset -> the Far look (retail Far geometry + lens 28/24); Far untouched
    kick_rules: bool = False      # kickoff 35 / touchback 35 (2026) / PAT 15, FG ceiling ~70 yd for elite legs
    kick_power: bool = False      # FG ceiling ~70 yd for elite legs ONLY (retail kick spots) - the BASIC preset's kicking fix
    # dynamic-kickoff alignment (2024+ rule, PHASE 1 = data only): coverage on the receiving 40, return
    # setup zone 35-30 with two returners deep, 5-yd kicker run-up; rewrites the Kickoff / Kick Return
    # formations of the 36 kicking playbooks; needs a disc image; opt-in until witnessed
    kickoff_alignment: bool = False
    # the full 2024/2025 dynamic kickoff (executable, EXPERIMENTAL, unwitnessed): coverage and setup blockers hold until the
    # ball touches the ground or a player, first contact is latched, landing zone then end zone = the 20, direct touchback =
    # touchback_yard (35, or 30 for 2024), short / out = the 40, the CPU kicker aims for the landing zone and the CPU returner
    # takes the touchback with the given probabilities; implies kick_rules + kickoff_alignment (and never kick_power)
    xbe_space: bool = False  # opt-in witness disc only, experimental and unwitnessed
    kickoff_relocated: bool = False
    dynamic_kickoff: bool = False
    dynamic_kickoff_settings: dict[str, object] = field(default_factory=lambda: {
        "touchback_yard": 35, "cpu_landing_probability": 90, "cpu_target_yards": (5, 15), "cpu_touchback_probability": 90})
    # one EDGE / one LB / one interior pool across 4-3 and 3-4 (XBE pools + playbook recode + ROST
    # reclassification; needs a disc image; implies scheme_labels)
    position_pools: bool = False
    # SLOT / NICKEL CORNER / DIME CORNER rows and X / Z labels on the depth-chart screen (executable, stride 13;
    # EXPERIMENTAL, unwitnessed): needs the one-pool positions (their third-starter cave) and the X / Z / SLOT playbook
    # roles; the rows edit the existing receiver / corner lists, they are not independent assignments
    depth_chart_rows: bool = False
    # 2026 season: real 2026 schedule template in pack 0 (17 games, 18 weeks, one bye; the real 3-game
    # preseason after it) + year/calendar/season-length/14-team-playoffs/preseason executable patches
    # (rookie birth years and the DOB line follow the year); needs a disc image
    season_cap: bool = False  # 128-season gate only; experimental, calendar repair deferred
    season_2026: bool = False
    # hor+ 16:9: the 3D view widens, HUD/menus/scorebug stay 4:3-proportioned; needs xemu [display.ui]
    # aspect_ratio = '16x9'. Opt-in only (not in a preset) until witnessed in game.
    widescreen: bool = False
    overtime: bool = False        # 2025+ NFL overtime: both teams possess, 10-min regular season w/ ties, playoffs to a winner
    # TEAM column on the franchise Player Card's season-by-season stats (which team each season was played for;
    # a UI fix, no gameplay change; past seasons of an older franchise save read "--" until their next rollover)
    team_column: bool = False
    # 7-on-7 practice: a fifth Practice Type (Practice -> Scrimmage -> Practice Type -> 7-On-7) that plays as
    # Full Scrimmage with the practice book loaded for both teams, plus the 7-on-7 sets/plays written into
    # PRACTICE-pb.iff (linemen parked at the sideline, a 4-second timer rusher); needs a disc image; unwitnessed
    seven_on_seven: bool = False
    # real team history for the roster's past seasons on the Player Card: "retail" = the shipped nflverse CSV
    # (data/nfl2k5_retail_team_history.csv), a path = a user CSV, "" = off; disc images only; shows in franchises
    # CREATED from the copy; costs one pool dword per season row (the game folds the oldest seasons a bit earlier).
    # Seasons the CSV does not cover are filled with the player's own 2004 club (receipt: "seasons_inferred"), so
    # 5,746 of the 5,838 rows the card can show name a team; only the 2004 free agents still read "--".
    team_history: str = ""
    # real per-season career counters for the roster's past seasons (passing / rushing / receiving / defence /
    # kicking) from a user CSV (schema in docs/mod_editor/career_stats.md; export the roster's own counters first
    # with tools/nfl2k5_career_stats.py to get the identity pins); "" = off; disc images only; runs right after
    # the team history because both rebuild the stat pool; refuses to overrun the pool or invent counters
    career_stats: str = ""
    # Position row on the first page of Edit Player (roster mode and Franchise); the descriptor exists for
    # Create Player, the Edit Player lists just never listed it. Depth Chart -> Auto after a change.
    position_row: bool = False
    # Pro Bowl Votes tabs in football order, K and P last (one pointer list; nothing else reads it)
    probowl_order: bool = False
    # penalties at NFL rates + a working Chop Block toggle: "" = off, "nfl" = the ESTIMATED first-cut profile
    # (seven .rdata slider->factor curve tables re-knotted in place, incidental face mask 5 -> 15 yd, the dead
    # Chop Block toggle wired through a 10-byte stub); room for a user .json profile path later; unwitnessed
    penalties: str = ""
    # home/away jerseys at any stadium: "rule" = home always dark, visitor always white (no Cowboys exception);
    # "choice" = the retail default plus a per-side colour flip on the same up/down that picks the era on
    # Controller Assign / Team Select (past the last era: flip and restart); "" = retail. Unwitnessed.
    uniform_choice: str = ""
    # laces to the posts on FG/PAT holds: one 6-byte hook on the held-ball join point + a 143-byte cave in a
    # dead routine that rolls the ball 180 degrees about its long axis on live Field Goal formation plays
    # (the game's own quaternion product; kickoff tee, punts and carries untouched). Opt-in until witnessed.
    kick_laces: bool = False
    # Free Practice inside Franchise: a Practice row on the Coach's Desk (the freed hook-list slot at
    # 0x521eec) opening a cloned Scrimmage Settings screen whose enter stub puts the team you coach on
    # BOTH sides at Practice Type = Full Scrimmage, and whose START pops once so a rep returns to the
    # Coach's Desk. UI addition, no gameplay effect; ~350-byte cave, no retail instruction changed.
    franchise_practice: bool = False
    # practice squads: 53 active + up to 12 team-owned reserves (the CPU's 65 -> 53 season cut keeps them; zero cap cost;
    # they survive saves, imports and the rollover; no in-game reserve screen yet); EXPERIMENTAL, unwitnessed
    practice_squad: bool = False
    # depth-chart locks: a player moved on the depth chart (T/G rank or side) or confirmed as KR/PR keeps that spot
    # through the weekly auto-depth (per-player lock bits in the record); EXPERIMENTAL, unwitnessed
    depth_locks: bool = False
    # modern draft-prospect names: "" = off, "modern" = the shipped nflverse list (data/nfl2k5_modern_names.csv),
    # a path = a user CSV (first,last; 485 rows). Rewrites the generated-player name pool in pack 0's roster
    # template (433 recorded surnames keep their index and call-out, 52 + every first name go modern) and
    # hooks the generator so replacement surnames are announced by number; disc images only; new franchises
    prospect_names: str = ""
    # the retail controller star (``icon_controller_star``) under the players named in ``player_tags``:
    # an 80-byte in-place rewrite of the retail predicate FUN_00075d40 that keeps its answer and ORs in
    # "this player's roster record has byte +0x53 bit 0 set", clamped to the game's 9-entry star list.
    # Off in BASIC, on in ADVANCED/EXPERIMENTAL: with no tags it draws nothing.  Unwitnessed.
    player_star: bool = False
    # who gets one: primary-roster indices (17) or "last,first,birth_date" keys ("Vick,Michael,1980-06-28"),
    # written into the ROST resource; disc images only, and the tag reaches franchises CREATED from the copy
    player_tags: list[str] = field(default_factory=list)
    # ★ Rosters edits: "" = off, otherwise the path of a roster-edits JSON document
    # (``2k5_mod_studio_roster_edits/v1``, written by the ★ Rosters page).  Applied to the ROST
    # resource of the copy LAST, after every other roster pass: it writes named record fields
    # (ratings, appearance, equipment, contract, position, depth, names through the shared pool)
    # and leaves +0x2C, the season-stat pool, the generated-name pool and the +0x53 star bit alone,
    # so all four of their digest gates stay intact.  Disc images only.
    roster_edits: str = ""
    # community playbook packs (.2k5book recipes) installed into the copy's team books.
    # A recipe, not retail bytes: the same formation/play/link rows the designers stage, so
    # Build compiles them against the user's own disc.  Never in a preset -- a community book
    # is a user choice like commentary, and a curated official one belongs in EXPERIMENTAL first.
    playbook_packs: tuple[str, ...] = ()
    # X / Z / SLOT receivers and nickel / dime corners: the personnel-group ordinals of every PLAY book normalised so
    # the innermost receiver is WR ordinal 2 (the 3rd receiver on the depth chart) and the inside corners are CB
    # ordinals 2 / 3; twelve shared groups that disagree by > 2 yd are refused and reported; disc images only;
    # ADVANCED (it changes who lines up, not physics); no depth-chart rows (those are the Tier 2 executable patch)
    screen_timing: str | None = None  # PLAY resources only; experimental A/B/C/D
    depth_roles: bool = False
    # text
    edge_rename: bool = False
    # presentation
    guardian_cap: bool = False  # helmet C resource trial, experimental and unwitnessed
    scorebug: bool = False
    scorebug_runtime: bool = False
    music_policy: str = "retail"
    music_unlock: bool = False
    music_userlist: bool = False
    music_project: str | None = None
    music_library: str | None = None
    commentary: list[CommentarySwap] = field(default_factory=list)
    # free-form description carried into receipts / packs
    name: str = ""
    author: str = ""
    notes: str = ""

    def wants_xbe_patch(self) -> bool:
        return (self.throw or self.catch_slider or self.accel_ramp or self.draft_ai or self.returner_fix
                or self.progression or self.scheme_labels or self.camera or self.kick_rules or self.kick_power or self.position_pools or self.xbe_space or self.kickoff_relocated or self.dynamic_kickoff or self.depth_chart_rows or self.practice_squad or self.depth_locks
                or self.season_cap or self.season_2026 or self.widescreen or self.overtime or self.team_column or self.seven_on_seven
                or self.position_row or self.probowl_order or bool(self.penalties) or bool(self.uniform_choice)
                or self.kick_laces or self.franchise_practice or bool(self.prospect_names) or self.player_star
                or self.scorebug_runtime or self.music_policy != "retail" or self.music_unlock or self.music_userlist
                or bool(self.music_library and _music_library_document(self.music_library)["bank"] == "cribmusic"))

    def to_recipe(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("source"); d.pop("target"); d.pop("overwrite")
        return d


# ---------------------------------------------------------------------------------------------
# SOFTDRINK patch presets (Noah, 9/3): one click to start from a known-good set, then customise.
#   basic    = gameplay/logic fixes only, stock feel — what an official update would have shipped
#   advanced = basic + every modern tweak (presentation, feel, era)
# Each maps BuildPlan field -> value; fields not listed keep the plan's defaults.  Patches that do
# not exist yet in this build are simply absent (availability() says which are missing).
PRESETS: dict[str, dict[str, Any]] = {
    # BASIC keeps the game in 2004: only the fixes a 2K5 update would have shipped.
    "softdrink_basic": {
        "scorebug_runtime": False,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": False,
        "catch_slider": True, "accel_ramp": False, "draft_ai": True, "returner_fix": True, "progression": False,
        "edge_rename": False, "scorebug": False, "guardian_cap": False, "scheme_labels": False, "camera": False,
        "kick_rules": False, "kick_power": True, "kickoff_alignment": False, "dynamic_kickoff": False, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": False, "season_cap": False, "season_2026": False, "widescreen": False, "overtime": False, "team_column": True, "seven_on_seven": False, "team_history": "", "career_stats": "", "screen_timing": None, "depth_roles": False, "depth_chart_rows": False, "position_row": True, "probowl_order": True, "penalties": "", "uniform_choice": "", "kick_laces": False, "franchise_practice": False, "practice_squad": False, "depth_locks": False, "prospect_names": "", "player_star": False,
    },
    # ADVANCED = basic + everything that modernises the game (Noah's tweaks and breakthroughs).
    "softdrink_advanced": {
        "scorebug_runtime": False,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True,
        "edge_rename": True, "scorebug": False, "guardian_cap": False, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": False, "dynamic_kickoff": False, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": True, "season_cap": False, "season_2026": True, "widescreen": False, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "career_stats": "", "screen_timing": None, "depth_roles": True, "depth_chart_rows": False, "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "choice", "kick_laces": False, "franchise_practice": True, "practice_squad": False, "depth_locks": False, "prospect_names": "modern", "player_star": True,
    },
    # EXPERIMENTAL = advanced + widescreen and anything still rough (dynamic-kickoff line-up).
    "softdrink_experimental": {
        "scorebug_runtime": True,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "guardian_cap": True,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True,
        "edge_rename": True, "scorebug": True, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": True, "dynamic_kickoff": True, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": True, "season_cap": True, "season_2026": True, "widescreen": True, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "career_stats": "", "screen_timing": "D", "depth_roles": True, "depth_chart_rows": True, "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "choice", "kick_laces": True, "franchise_practice": True, "practice_squad": True, "depth_locks": True, "prospect_names": "modern", "player_star": True,
    },
}
PRESET_TITLES = {"softdrink_basic": "SOFTDRINK patch: basic (2004 game, just the 2K5 fixes)",
                 "softdrink_advanced": "SOFTDRINK patch: advanced (everything modern)",
                 "softdrink_experimental": "SOFTDRINK patch: experimental (advanced + widescreen + rough edges)"}


def apply_preset(plan: BuildPlan, name: str) -> BuildPlan:
    """Return a copy of ``plan`` with the named preset's toggles set (source/target/name kept)."""

    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    values = dict(asdict(plan))
    values["commentary"] = list(plan.commentary)
    values.update(PRESETS[name])
    if not values.get("name"):
        values["name"] = PRESET_TITLES[name]
    return BuildPlan(**values)


def availability() -> dict[str, bool]:
    """Which optional patch modules are present in this build."""

    return {
        "throw": True, "catch_slider": True, "accel_ramp": True, "draft_ai": True,
        "xbe_space": _core_module("nfl2k5_xbe_space") is not None,
        "kickoff_relocated": (_core_module("nfl2k5_dynamic_kickoff_relocated") is not None
                              and _core_module("nfl2k5_xbe_space") is not None
                              and _tools_module("nfl2k5_kickoff_alignment") is not None),
        "screen_timing": (all(_core_module(name) is not None for name in (
            "nfl2k5_screen_timing", "nfl2k5_formation_play_writer", "nfl2k5_playbook_pack"))
            and _tools_module("nfl2k5_playbook_position_recode") is not None),
        "guardian_cap": (all(_core_module(name) is not None for name in (
            "nfl2k5_guardian_cap", "nfl2k5_models", "nfl2k5_p8_texture_writer"))
            and all(_tools_module(name) is not None for name in (
                "nfl_outer", "nfl_scene_probe", "nfl_scne_inventory", "nfl_scne_gltf", "nfl_txtr",
                "nfl_vc_lz_fill", "nfl_live_helmet_txtr_png_import", "nfl_live_helmet_txtr_targets",
                "nfl_tset_png_import", "nfl_all_texture_xiso_workflow"))),
        "season_cap": _core_module("nfl2k5_season_cap") is not None,
        "returner_fix": _core_module("nfl2k5_returner_fix") is not None,
        "progression": _core_module("nfl2k5_progression") is not None,
        "scheme_labels": _core_module("nfl2k5_modern_positions") is not None,
        "camera": _core_module("nfl2k5_camera") is not None,
        "kick_rules": _core_module("nfl2k5_kick_rules") is not None,
        "kickoff_alignment": _tools_module("nfl2k5_kickoff_alignment") is not None,
        "dynamic_kickoff": (_core_module("nfl2k5_dynamic_kickoff") is not None and _core_module("nfl2k5_kick_rules") is not None
                            and _tools_module("nfl2k5_kickoff_alignment") is not None),
        "widescreen": _core_module("nfl2k5_widescreen") is not None,
        "overtime": _core_module("nfl2k5_overtime") is not None,
        "team_history": (_core_module("nfl2k5_team_history") is not None
                         and (ROOT / "data" / "nfl2k5_retail_team_history.csv").exists()),
        "career_stats": _core_module("nfl2k5_career_stats") is not None,
        "team_column": _core_module("nfl2k5_team_column") is not None,
        "position_row": _core_module("nfl2k5_position_row") is not None,
        "probowl_order": _core_module("nfl2k5_probowl_order") is not None,
        "penalties": _core_module("nfl2k5_penalties") is not None,
        "uniform_choice": _core_module("nfl2k5_uniform_choice") is not None,
        "kick_laces": _core_module("nfl2k5_kick_laces") is not None,
        "franchise_practice": _core_module("nfl2k5_franchise_practice") is not None,
        "practice_squad": _core_module("nfl2k5_practice_squad") is not None,
        "depth_locks": _core_module("nfl2k5_depth_locks") is not None,
        "prospect_names": (_core_module("nfl2k5_prospect_names") is not None
                           and (ROOT / "data" / "nfl2k5_modern_names.csv").exists()),
        "player_star": _core_module("nfl2k5_player_star") is not None,
        "player_tags": _core_module("nfl2k5_player_tags") is not None,
        "roster_edits": _core_module("nfl2k5_roster_records") is not None,
        "seven_on_seven": (SEVEN_ON_SEVEN_RELEASED
                           and _core_module("nfl2k5_seven_on_seven") is not None
                           and _core_module("nfl2k5_seven_on_seven_book") is not None),
        "season_2026": (_core_module("nfl2k5_season_length") is not None
                        and _tools_module("nfl2k5_franchise_schedule") is not None
                        and (ROOT / "data" / "nfl_2026_schedule.json").exists()),
        "position_pools": (_core_module("nfl2k5_position_pools") is not None
                           and _tools_module("nfl2k5_playbook_position_recode") is not None
                           and _tools_module("nfl2k5_roster_reclassify") is not None),
        # The scorebug used to be gated on two developer-only files (our repaint of the ESPN
        # mark, and an intermediate glTF that only the CLI mockup ever reads), so every install
        # but this workstation reported "Not available in this build" and the ADVANCED preset
        # skipped it silently.  Both retail-derived inputs and the derived art now come from
        # the user's own disc image at build time (nfl2k5_scorebug_source_art), so the step is
        # available whenever the writer and the generator are: the source is checked when the
        # build runs, where a non-image source is already refused with its own message.
        "scorebug_runtime": all(_core_module(name) is not None for name in (
            "nfl2k5_scorebug_runtime", "nfl2k5_scorebug_ingame", "nfl2k5_scorebug_resources", "nfl2k5_xbe_space")),
        **{key: _core_module("nfl2k5_music_policy") is not None for key in
           ("music_policy", "music_unlock", "music_userlist")},
        "music_project": all(_core_module(name) is not None for name in (
            "nfl2k5_music_build", "nfl2k5_music_catalog")),
        "music_library": _core_module("nfl2k5_music_banks") is not None,
        "scorebug": (_tools_module("nfl2k5_scorebug_layout") is not None
                     and _core_module("nfl2k5_scorebug_source_art") is not None
                     and _scorebug_art_available()),
        "edge_rename": _core_module("nfl2k5_edge_rename") is not None,
        "commentary": _tools_module("nfl2k5_commentary_swap") is not None,
        "playbook_packs": (_core_module("nfl2k5_playbook_pack") is not None
                           and _tools_module("nfl2k5_playbook_position_recode") is not None),
        "depth_roles": (_core_module("nfl2k5_depth_roles") is not None
                        and _tools_module("nfl2k5_playbook_position_recode") is not None),
        "depth_chart_rows": (_core_module("nfl2k5_depth_chart_rows") is not None and _core_module("nfl2k5_position_pools") is not None
                             and _core_module("nfl2k5_modern_positions") is not None and _core_module("nfl2k5_depth_roles") is not None
                             and _tools_module("nfl2k5_playbook_position_recode") is not None and _tools_module("nfl2k5_roster_reclassify") is not None),
    }


def inspect_screen_timing(source: Path | str, level: str = "D") -> dict[str, Any]:
    module = _core_module("nfl2k5_screen_timing")
    if module is None:
        return {"status": "unavailable", "level": level, "books": []}
    try:
        return module.inspect_image(Path(source), level=level)
    except Exception as exc:  # noqa: BLE001 - preserve the refusal for the source status display
        return {"status": "foreign", "level": level, "books": [], "reason": str(exc)}


def inspect(source: Path | str, *, screen_timing: str | None = None) -> dict[str, Any]:
    """Current state of every patch in ``source`` (a default.xbe or a disc image)."""

    source = Path(source)
    report = tt.read_any(source)
    out: dict[str, Any] = {
        "path": str(source), "container": report.get("container"),
        "throw": report["settings"], "catch_slider": report.get("catch_slider"),
        "accel_ramp": report.get("accel_ramp"), "draft_ai": report.get("draft_ai"),
        "returner_fix": report.get("returner_fix", "unknown"), "progression": report.get("progression", "unknown"),
        "scheme_labels": report.get("scheme_labels", "unknown"), "camera": report.get("camera", "unknown"),
        "kick_rules": report.get("kick_rules", "unknown"), "dynamic_kickoff": report.get("dynamic_kickoff", "unknown"), "dynamic_kickoff_settings": report.get("dynamic_kickoff_settings"), "playoff_picture": report.get("playoff_picture", "unknown"), "depth_chart_rows": report.get("depth_chart_rows", "unknown"), "kick_power": report.get("kick_power", "unknown"), "widescreen": report.get("widescreen", "unknown"),
        "overtime": report.get("overtime", "unknown"), "team_column": report.get("team_column", "unknown"),
        "position_row": report.get("position_row", "unknown"), "probowl_order": report.get("probowl_order", "unknown"),
        "penalties": report.get("penalties", "unknown"),
        "uniform_choice": report.get("uniform_choice", "unknown"),
        "kick_laces": report.get("kick_laces", "unknown"),
        "franchise_practice": report.get("franchise_practice", "unknown"),
        "practice_squad": report.get("practice_squad", "unknown"),
        "practice_reserves": report.get("practice_reserves", "unknown"),
        "depth_locks": report.get("depth_locks", "unknown"),
        "season_cap": report.get("season_cap", "unknown"),
        "xbe_space": report.get("xbe_space", "unknown"),
        "kickoff_relocated": report.get("kickoff_relocated", "unknown"),
        "kickoff_relocated_settings": report.get("kickoff_relocated_settings"),
        # the executable half alone is never "applied": the name pool lives in pack 0 (both halves below for images)
        "prospect_names": ("partial" if report.get("prospect_names") == "applied" else report.get("prospect_names", "unknown")),
        "player_star": report.get("player_star", "unknown"), "player_tags": "n/a", "roster_edits": "n/a",
        "seven_on_seven": report.get("seven_on_seven", "unknown"), "seven_on_seven_book": "n/a", "team_history": "n/a",
        "position_pools": "n/a", "season_2026": "n/a", "kickoff_alignment": "n/a",
        "guardian_cap": report.get("guardian_cap", "n/a"),
        "screen_timing": "n/a",
        **{key: report.get(key, "foreign") for key in (
            "scorebug_runtime", "scorebug_xbe", "music_policy", "music_unlock",
            "music_userlist", "music_state", "music_metadata_patch")},
        "scorebug_runtime_resources": "n/a", "music_project": "n/a", "music_library": "n/a",
        "scorebug": "n/a", "edge_rename": "unknown", "commentary": "unknown",
        # a pack is a recipe compiled into the books; there is no single site to read back,
        # so the receipt (not inspect) is the record of which packs went in
        "playbook_packs": "n/a",
        "depth_roles": "n/a",
    }
    if report.get("container") == "xiso":
        runtime = _core_module("nfl2k5_scorebug_ingame")
        if runtime is not None:
            out["scorebug_runtime_resources"] = runtime.runtime_image_status(source)
        try:
            archive = _core_module("nfl2k5_music_archive")
            with archive.Disc(source) as disc:
                out["music_library"] = "available"
                out["music_library_counts"] = {k: len(v.boundaries) - 1 for k, v in disc.banks.items()}
            music = _core_module("nfl2k5_music_build")
            with music._banks_module().DiscBanks(source) as disc:
                out["music_project"] = "available"
        except (ValueError, OSError):
            pass
        screen = inspect_screen_timing(source, screen_timing or "D")
        out["screen_timing"] = screen["status"]
        out["screen_timing_details"] = screen
        roles = _core_module("nfl2k5_depth_roles")
        if roles is not None:
            try:
                role_state = roles.status(source)
                out["depth_roles"] = role_state["status"]
                out["depth_roles_books"] = role_state["books"]
            except Exception:  # noqa: BLE001
                out["depth_roles"] = "foreign"
        align = _tools_module("nfl2k5_kickoff_alignment")
        if align is not None:
            try:
                out["kickoff_alignment"] = align.status(source)["status"]
            except Exception:  # noqa: BLE001
                out["kickoff_alignment"] = "foreign"
        pools = _core_module("nfl2k5_position_pools")
        if pools is not None:
            try:
                out["position_pools"] = pools.status(_xbe_bytes(source))
            except Exception:  # noqa: BLE001
                out["position_pools"] = "foreign"
        season = _core_module("nfl2k5_season_length")
        if season is not None:
            try:
                out["season_2026"] = season.simple_status(_xbe_bytes(source))
            except Exception:  # noqa: BLE001
                out["season_2026"] = "foreign"
        sbl = _tools_module("nfl2k5_scorebug_layout")
        if sbl is not None:
            try:
                out["scorebug"] = sbl.status(source)
            except Exception:  # noqa: BLE001
                out["scorebug"] = "foreign"
        book = _core_module("nfl2k5_seven_on_seven_book")
        if book is not None:
            try:
                out["seven_on_seven_book"] = book.status(source)
            except Exception:  # noqa: BLE001
                out["seven_on_seven_book"] = "foreign"
        history = _core_module("nfl2k5_team_history")
        if history is not None:
            try:
                out["team_history"] = history.status(source)
            except Exception:  # noqa: BLE001
                out["team_history"] = "foreign"
        names = _core_module("nfl2k5_prospect_names")
        if names is not None:
            try:
                out["prospect_names"] = names.image_status(source)
            except Exception:  # noqa: BLE001
                out["prospect_names"] = "foreign"
        tags = _core_module("nfl2k5_player_tags")
        if tags is not None:
            try:
                out["player_tags"] = tags.status(source)
            except Exception:  # noqa: BLE001
                out["player_tags"] = "foreign"
        records = _core_module("nfl2k5_roster_records")
        if records is not None:
            try:
                out["roster_edits"] = records.status(source)
            except Exception:  # noqa: BLE001
                out["roster_edits"] = "foreign"
    if "edge_rename" in report:
        out["edge_rename"] = report.get("edge_rename")
        out["edge_rename_disc"] = report.get("edge_rename_disc")
    # Which disc this is decides whether Build will work at all, so the panel can say it
    # before anyone presses the button rather than after a step has refused.
    if report.get("container") == "xiso":
        identity = disc_identity(source)
        out["disc_identity"] = identity.as_json() if identity is not None else None
        out["disc_identity_line"] = identity.line() if identity is not None else ""
        out["disc_identity_headline"] = identity.headline if identity is not None else ""
    else:
        out["disc_identity"] = None
        out["disc_identity_line"] = ""
        out["disc_identity_headline"] = ""
    return out


def _xbe_bytes(source: Path) -> bytes:
    if tt.is_disc_image(source):
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            off, length = tt.image_xbe_extent(fd, size)
            return platform_compat.pread(fd, length, off)
        finally:
            os.close(fd)
    return source.read_bytes()


def _pack0_extent(descriptor: int) -> tuple[int, int]:
    """(absolute byte offset, size) of vc_53450030/0 in the open image, from its XDVDFS directory."""

    xc = tt._xdvdfs_module()
    try:
        offset, size = xc.pack_extent(descriptor, os.fstat(descriptor).st_size, "0")
    except xc.PatchError as exc:
        raise ValueError(f"cannot locate the schedule template pack: {exc}") from exc
    if size != PACK0_SIZE:
        raise ValueError(f"vc_53450030/0 in this image is {size} bytes, not the retail {PACK0_SIZE}")
    return offset, size


def _write_xbe_bytes(target: Path, payload: bytes) -> None:
    if tt.is_disc_image(target):
        fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            off, length = tt.image_xbe_extent(fd, size)
            if len(payload) != tt.EXPECTED_XBE_SIZE:
                # The generalized writer validates growth and rolls back same-size replays too.
                from . import nfl2k5_depth_chart_storage as storage
                storage.write_image_xbe(fd, payload)
            else:
                platform_compat.pwrite(fd, payload, off)
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        target.write_bytes(payload)


#: The 7-on-7 practice mode is built and tested but not released yet (Noah's call, 2026-09-03: it is
#: witnessed through the Practice Type screen and the play-call, not yet through a snap). While False the
#: checkboxes are hidden, every preset leaves it off and Build reports it unavailable; the modules and their
#: tests stay so the branch that finishes it merges cleanly.
SEVEN_ON_SEVEN_RELEASED = False

IMAGE_SUFFIXES = (".iso", ".xiso", ".img")


def image_target_path(chosen: str) -> str:
    """A user-typed save name for a patched disc image, given the suffix xemu's file picker looks for.

    A Discord user built a disc, got "a file that wasn't a .iso", and could not load it: the save
    dialog accepted a bare name. Anything without a disc-image suffix gets ``.xiso.iso``."""

    text = chosen.strip()
    if not text:
        return text
    lowered = text.casefold()
    if any(lowered.endswith(suffix) for suffix in IMAGE_SUFFIXES):
        return text
    return text + ".xiso.iso"


def disc_identity(source: Path | str, *, pack0: bytes | None = None):
    """What kind of disc image ``source`` is, or None when it cannot be told."""

    module = _core_module("nfl2k5_disc_identity")
    if module is None:
        return None
    try:
        return module.identify(source, pack0=pack0)
    except Exception:  # noqa: BLE001 -- an identity is a courtesy, never a gate
        return None


def _identity_note(source: Path | str, *, pack0: bytes | None = None) -> str:
    identity = disc_identity(source, pack0=pack0)
    return f"This image is: {identity.line()}" if identity is not None else ""


def _with_identity(exc: ValueError, source: Path, is_image: bool) -> ValueError:
    """Name the disc in a refusal.

    "pack-0 schedule template is foreign: ROST stored size is not retail" is
    true and useless: it is the same sentence for a repacked image, a disc that
    already carries somebody's roster mod, and a dump of another game.  Which
    one it is decides whether the user re-dumps, rebuilds, or starts over, so
    every refusal on a disc image says which.
    """

    text = str(exc)
    if not is_image or "This image is:" in text:
        return exc
    note = _identity_note(source)
    if not note:
        return exc
    joiner = " " if text.rstrip().endswith((".", "!", "?", ":")) else ". "
    return ValueError(f"{text.rstrip()}{joiner}{note}")


def _music_library_document(path):
    return _core_module("nfl2k5_music_banks")._load(path)


def _prepare_music_project(source, project, directory, progress):
    from .nfl2k5_source_cache import Nfl2k5SourceCache
    from .nfl2k5_audio_catalog import Nfl2k5AudioCatalog, Nfl2k5AudioService
    from .nfl2k5_audio_origin_preparation import Nfl2k5AudioOriginPreparation
    from mod_editor.studio.session import StudioSession
    from mod_editor.studio.music_service import MusicService
    cache = Nfl2k5SourceCache(directory / "cache").index(source, progress)
    audio = Nfl2k5AudioService(cache, Nfl2k5AudioCatalog(cache))
    preparation = Nfl2k5AudioOriginPreparation()
    if not preparation.is_ready(cache):
        preparation.prepare(cache, progress)
    audio.load_private_origin_inventories()
    session = StudioSession(cache, object(), root=directory / "sessions")
    session.attach_audio_service(audio)
    service = MusicService(session)
    try:
        service.load_project(project, progress=progress)
        return service.encoded_edits(progress=progress)
    finally:
        service.invalidate()


def build(plan: BuildPlan, progress: ProgressSink | None = None) -> dict[str, Any]:
    """Apply the plan to a copy; archive rebuilds publish only a complete result."""
    try:
        source, target = Path(plan.source).resolve(), Path(plan.target).absolute()
        if source == target.resolve():
            raise ValueError("target must not be the source")
        if target.exists() and not plan.overwrite:
            raise FileExistsError(f"{target} exists")
        with tempfile.TemporaryDirectory(prefix=".studio-build-", dir=target.parent) as folder:
            directory = Path(folder)
            edits = None
            if plan.music_project:
                if not tt.is_disc_image(source):
                    raise ValueError("Music replacements need a disc image")
                edits = _prepare_music_project(source, plan.music_project, directory, progress or (lambda *_: None))
            receipt = _build(replace(plan, target=str(directory / target.name), overwrite=False), progress,
                             music_edits=edits)
            if progress:
                progress("Publishing verified disc", 0, 0)
            os.replace(directory / target.name, target)
            receipt["target"] = str(target)
            receipt["result"]["path"] = str(target)
            return receipt
    except ValueError as exc:
        source = Path(plan.source)
        raise _with_identity(exc, source, tt.is_disc_image(source)) from exc


def _build(plan: BuildPlan, progress: ProgressSink | None = None, *, music_edits=None) -> dict[str, Any]:
    progress = progress or (lambda *_a: None)
    if plan.screen_timing is not None and (
            not isinstance(plan.screen_timing, str) or plan.screen_timing not in ("A", "B", "C", "D")):
        raise ValueError("screen_timing must be None or A, B, C, D")
    if (plan.music_policy not in ("retail", "jukebox_menus") or type(plan.music_unlock) is not bool
            or type(plan.music_userlist) is not bool or (plan.music_userlist and plan.music_policy != "jukebox_menus")):
        raise ValueError("Music policies require retail or jukebox_menus, boolean switches, and jukebox menus for UserList")
    if plan.scorebug_runtime:
        plan = replace(plan, scorebug=True, xbe_space=True)
    if plan.kickoff_relocated:
        plan = replace(plan, xbe_space=True, dynamic_kickoff=True)
    if plan.dynamic_kickoff:
        # record the effective dependencies in the recipe: the modern spots, never the power-only variant, the line-up
        plan = replace(plan, kick_rules=True, kick_power=False, kickoff_alignment=True)
    source, target = Path(plan.source), Path(plan.target)
    if target.exists() and target.resolve() == source.resolve():
        raise ValueError("target must not be the source")
    if target.exists() and not plan.overwrite:
        raise FileExistsError(f"{target} exists")
    receipt: dict[str, Any] = {"plan": plan.to_recipe(), "steps": [], "source": str(source), "target": str(target)}
    is_image = tt.is_disc_image(source)
    if (plan.xbe_space or plan.kickoff_relocated) and not is_image:
        raise ValueError("experimental extra patch space needs a disc image")
    if plan.music_library:
        if not is_image:
            raise ValueError("Music libraries need a disc image")
        library = _core_module("nfl2k5_music_banks")
        library.plan(source, plan.music_library)  # refuse missing assets before any ordinary writes
    if plan.screen_timing is not None and not is_image:
        raise ValueError("screen timing needs a disc image (the timing lives in PLAY resources)")
    if plan.guardian_cap:
        cap = _core_module("nfl2k5_guardian_cap")
        if cap is None:
            raise RuntimeError("Guardian caps are not available in this build")
        if not is_image or cap.image_status(source) not in {"retail", "applied"}:
            raise ValueError("Guardian caps need a disc image with the original player models and Detroit away helmet, or this exact cap trial.")
    if plan.scorebug and not is_image:
        raise ValueError("the ESPN scorebug needs a disc image (the mesh lives in the field pack)")
    if plan.position_pools and not is_image:
        raise ValueError("one-pool positions need a disc image (playbooks and rosters live on the disc)")
    if plan.season_2026 and not is_image:
        raise ValueError("the 2026 season needs a disc image (the schedule template lives in pack 0)")
    if plan.kickoff_alignment and not is_image:
        raise ValueError("the dynamic-kickoff alignment needs a disc image (the formations live in the playbooks)")
    if plan.seven_on_seven and not is_image:
        raise ValueError("7-on-7 practice needs a disc image (the 7-on-7 sets live in the practice playbook)")
    if plan.team_history and not is_image:
        raise ValueError("the team history needs a disc image (the roster template lives in pack 0)")
    if plan.career_stats and not is_image:
        raise ValueError("career stats need a disc image (the roster template lives in pack 0)")
    if plan.prospect_names and not is_image:
        raise ValueError("modern prospect names need a disc image (the name pool lives in the roster template in pack 0)")
    if plan.player_tags and not is_image:
        raise ValueError("star tags need a disc image (the roster records live in pack 0)")
    if plan.roster_edits and not is_image:
        raise ValueError("roster edits need a disc image (the roster records live in pack 0)")
    if plan.playbook_packs and not is_image:
        raise ValueError("playbook packs need a disc image (the books live in the archive packs)")
    if plan.depth_chart_rows:
        if not is_image:
            raise ValueError("depth-chart rows need a disc image (they build on the one-pool positions and the playbook roles)")
        rows = _core_module("nfl2k5_depth_chart_rows")
        pools = _core_module("nfl2k5_position_pools")
        roles = _core_module("nfl2k5_depth_roles")
        if rows is None or pools is None or roles is None:
            raise RuntimeError("the depth-chart row dependencies are not available in this build")
        source_xbe = _xbe_bytes(source)
        if rows.status(source_xbe) == "foreign":
            raise ValueError("the depth-chart row sites are neither retail nor this patch; refusing")
        pool_state = pools.status(source_xbe)
        if pool_state not in ("retail", "applied"):
            raise ValueError("the position-pool sites are neither retail nor this patch; refusing")
        if pool_state != "applied" and not plan.position_pools:
            raise ValueError("depth-chart rows need the one-pool positions (tick them, or build on a disc that has them)")
        if not plan.depth_roles and roles.status(source)["status"] != "applied":
            raise ValueError("depth-chart rows need the X / Z / SLOT playbook roles (tick them, or build on a disc that has them)")
    if plan.depth_roles and not is_image:
        raise ValueError("depth roles need a disc image (the personnel groups live in the PLAY books)")
    if plan.depth_roles:
        roles = _core_module("nfl2k5_depth_roles")
        if roles is None:
            raise RuntimeError("the depth-role module is not available in this build")
        role_states = roles.status(source)["books"]
        if not role_states or any(state == "foreign" for state in role_states.values()):
            raise ValueError("the source disc's playbooks carry foreign personnel data; depth roles refuse to guess")

    # Defense v2 recipes require native personnel fingerprints before the pool recode.
    # Keep offense recipes in their original later position relative to other PLAY writers.
    defense_packs: list[Path] = []
    option_packs: list[Path] = []
    offense_packs: list[Path] = []
    if plan.playbook_packs:
        packs = _core_module("nfl2k5_playbook_pack")
        if packs is None:
            raise RuntimeError("the playbook pack module is not available in this build")
        for path in dict.fromkeys(Path(p) for p in plan.playbook_packs):
            pack = packs.load_pack(path)
            (option_packs if any(p.option_intent for p in pack.plays) else
             defense_packs if pack.schema == packs.DEFENSE_SCHEMA else offense_packs).append(path)

    if option_packs and offense_packs:
        for option_path in option_packs:
            option = packs.load_pack(option_path)
            protected_plays = {p.replace_index for p in option.plays}
            protected_formations = {p.link_formation for p in option.plays}
            for other_path in offense_packs:
                other = packs.load_pack(other_path)
                if option.book.team == other.book.team and (
                        protected_plays & {p.replace_index for p in other.plays}
                        or protected_formations & {f.replace_index for f in other.formations}):
                    raise ValueError("Option and Modern Gun Core replacements overlap in " + option.book.team +
                                     "; select one stock seed or author a reviewed combined pack")

    # 1. copy + executable and text patches through the proven writer (throw tables, caves, EDGE rename
    #    including its disc text spans when the source is an image)
    # the rows run after the pools step below (their cave and stride depend on it), so they never ride the first pass
    # the 2026 season step patches the executable itself, so a season-only plan is copy-first too
    if replace(plan, depth_chart_rows=False, season_2026=False, xbe_space=False, kickoff_relocated=False, scorebug_runtime=False, music_library=None).wants_xbe_patch() or plan.edge_rename:
        progress("Copying and patching default.xbe", 0, 0)
        settings = tt.TuningSettings(plan.max_deep_yards, plan.arc, plan.realistic_flight, plan.arc_by_distance) if plan.throw else None
        kwargs: dict[str, Any] = {"overwrite": plan.overwrite, "progress": progress,
                                  "catch_slider": plan.catch_slider, "accel_ramp": plan.accel_ramp,
                                  "draft_ai": plan.draft_ai, "edge_rename": plan.edge_rename,
                                  "returner_fix": plan.returner_fix, "progression": plan.progression,
                                  "scheme_labels": plan.scheme_labels or plan.position_pools,
                                  "camera": plan.camera, "kick_rules": plan.kick_rules, "kick_power": plan.kick_power, "widescreen": plan.widescreen,
                                  "overtime": plan.overtime, "team_column": plan.team_column, "seven_on_seven": plan.seven_on_seven,
                                  "position_row": plan.position_row, "probowl_order": plan.probowl_order,
                                  "penalties": plan.penalties, "uniform_choice": uniform_choice_mode(plan.uniform_choice),
                                  "kick_laces": plan.kick_laces, "franchise_practice": plan.franchise_practice, "practice_squad": plan.practice_squad,
                                  "depth_locks": plan.depth_locks, "season_cap": plan.season_cap,
                                  "music_policy": plan.music_policy, "music_unlock": plan.music_unlock, "music_userlist": plan.music_userlist,
                                  "prospect_names": plan.prospect_names,
                                  "player_star": plan.player_star,
                                  "dynamic_kickoff": plan.dynamic_kickoff, "dynamic_kickoff_settings": plan.dynamic_kickoff_settings}
        if settings is not None:
            kwargs["settings"] = settings
        step = tt.write_copy(source, target, **kwargs)
        receipt["steps"].append({"step": "xbe", **{k: step.get(k) for k in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "edge_rename_disc", "returner_fix", "progression", "scheme_labels", "camera", "kick_rules", "kick_power", "dynamic_kickoff", "dynamic_kickoff_settings", "dynamic_kickoff_patch", "depth_chart_rows", "practice_squad", "practice_reserves", "depth_locks", "season_cap", "season_cap_patch", "widescreen", "overtime", "team_column", "seven_on_seven", "position_row", "probowl_order", "penalties", "uniform_choice", "kick_laces", "franchise_practice", "prospect_names", "player_star", "music_policy", "music_unlock", "music_userlist", "music_state", "music_policy_patch", "scorebug_xbe", "changed_byte_count")}})
    else:
        progress("Copying the image", 0, 0)
        if target.exists():
            target.unlink()
        shutil.copyfile(source, target)
        receipt["steps"].append({"step": "copy"})

    # 3. presentation on the copy
    if plan.scorebug and not plan.scorebug_runtime:
        sbl = _tools_module("nfl2k5_scorebug_layout")
        if sbl is None:
            raise RuntimeError("scorebug layout tool is not available in this build")
        progress("Re-laying the scorebug (mesh, placement, textures)", 0, 0)
        try:
            rec = sbl.apply_in_place(target)
        except SystemExit as exc:
            # the layout writer reports refusals as SystemExit (it is also a CLI). A build runs on
            # a Qt worker thread whose runner catches Exception, so a SystemExit there would kill
            # the thread silently and leave the panel waiting for a result that never comes.
            raise RuntimeError(f"the ESPN scorebug could not be written: {exc}") from exc
        receipt["steps"].append({"step": "scorebug", **rec})
    if option_packs:
        progress("Installing experimental option playbook packs", 0, 0)
        rec = packs.apply_packs_to_image(target, option_packs, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "option_playbook_packs", **rec, "experimental": True, "witnessed": False})
    if defense_packs:
        progress("Installing experimental native defense playbook packs", 0, 0)
        pack_receipt = packs.apply_packs_to_image(
            target, defense_packs, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "defense_playbook_packs", **pack_receipt,
                                 "experimental": True, "witnessed": False})
    if plan.position_pools:
        pools = _core_module("nfl2k5_position_pools")
        recode = _tools_module("nfl2k5_playbook_position_recode")
        roster = _tools_module("nfl2k5_roster_reclassify")
        if pools is None or recode is None or roster is None:
            raise RuntimeError("one-pool position modules are not available in this build")
        progress("Merging the EDGE / LB / interior pools in the executable", 0, 0)
        xbe = _xbe_bytes(target)
        state = pools.status(xbe)
        if state == "retail":
            xbe, pools_receipt = pools.apply(xbe)
            _write_xbe_bytes(target, xbe)
        elif state == "applied":
            pools_receipt = {"already_applied": True}
        else:
            raise ValueError(f"position-pool sites are {state}; refusing")
        progress("Recoding the 37 playbooks' defensive categories", 0, 0)
        book_receipt = recode.apply(target, progress=lambda msg: progress(msg, 0, 0))
        progress("Reclassifying rosters into the merged pools", 0, 0)
        roster_receipt = roster.apply(target, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "position_pools", "xbe": pools_receipt,
                                 "playbooks": {k: v for k, v in book_receipt.items() if k not in ("books", "rows")},
                                 "rosters": {k: v for k, v in roster_receipt.items() if k not in ("moves", "teams")}})
    if plan.depth_chart_rows:
        # after the pools (the rows reuse their third-starter cave and their stride-aware table) and before the book
        # writers; the executable rows never touch a book
        progress("Adding the SLOT, nickel and dime depth-chart rows", 0, 0)
        xbe, row_step = tt._apply_all(_xbe_bytes(target), None, catch_slider=False, arc_table=False, depth_chart_rows=True)
        _write_xbe_bytes(target, xbe)
        rows = _core_module("nfl2k5_depth_chart_rows")
        if rows is None or rows.status(_xbe_bytes(target)) != "applied":
            raise ValueError("the depth-chart rows failed their read-back")
        receipt["steps"].append({"step": "depth_chart_rows", "status": "applied", "xbe": row_step.get("depth_chart_rows_patch"),
                                 "changed_byte_count": row_step.get("changed_byte_count")})
    if plan.kickoff_alignment:
        align = _tools_module("nfl2k5_kickoff_alignment")
        if align is None:
            raise RuntimeError("the kickoff alignment tool is not available in this build")
        progress("Lining up the dynamic kickoff (coverage on the 40, setup zone 35-30)", 0, 0)
        align_receipt = align.apply(target, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "kickoff_alignment",
                                 **{k: align_receipt[k] for k in ("status", "kicker_depth_yd", "changed_bytes", "books")}})
    if plan.seven_on_seven:
        book = _core_module("nfl2k5_seven_on_seven_book")
        if book is None:
            raise RuntimeError("the 7-on-7 practice book module is not available in this build")
        progress("Writing the 7-on-7 sets into the practice playbook", 0, 0)
        book_receipt = book.apply(target, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "seven_on_seven_book", **{k: v for k, v in book_receipt.items() if k != "formations"}})
    if offense_packs:
        # Offensive packs retain their order after the position recode and practice writers.
        packs = _core_module("nfl2k5_playbook_pack")
        if packs is None:
            raise RuntimeError("the playbook pack module is not available in this build")
        progress("Installing the community playbook packs", 0, 0)
        pack_receipt = packs.apply_packs_to_image(
            target, offense_packs,
            progress=lambda msg: progress(msg, 0, 0),
        )
        receipt["steps"].append({"step": "playbook_packs", **pack_receipt})
    if plan.depth_roles:
        # last of the playbook writers: a pack or the 7-on-7 / kickoff writers change formations and shared-group
        # usage, and the role pass must see the final books (it validates every play before and after)
        roles = _core_module("nfl2k5_depth_roles")
        if roles is None:
            raise RuntimeError("the depth-role module is not available in this build")
        progress("Assigning X / Z / SLOT receivers and nickel / dime corners in the playbooks", 0, 0)
        role_receipt = roles.apply(target, allow_custom=bool(plan.playbook_packs or plan.seven_on_seven or plan.kickoff_alignment),
                                   progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "depth_roles", **role_receipt})
    for level, module, key, label in (
        (plan.screen_timing, _core_module("nfl2k5_screen_timing"),
         "screen_timing", "Screen pass timing (experimental)"),
    ):
        if level is None:
            continue
        if module is None:
            raise RuntimeError("The screen timing module is not available in this build")
        progress(label, 0, 0)
        step = module.apply_to_image(target, level=level,
                                     progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": key, **step})
    if plan.season_2026:
        season = _core_module("nfl2k5_season_length")
        fs = _tools_module("nfl2k5_franchise_schedule")
        if season is None or fs is None:
            raise RuntimeError("2026 season modules are not available in this build")
        progress("Setting the franchise to 2026 (year, calendar, 18-week season)", 0, 0)
        xbe = _xbe_bytes(target)
        state = season.simple_status(xbe)
        if state == "retail":
            xbe, season_receipt = season.apply(xbe)
            _write_xbe_bytes(target, xbe)
        elif state == "applied":
            season_receipt = {"already_applied": True}
        else:
            raise ValueError(f"season-length sites are {state}; refusing")
        # the seven-seed presentation (Playoff Picture, Playoff Tree, SportsCenter previews) rides with the bracket:
        # a disc with the fourteen-team playoffs must never show the old six-seed picture
        picture = _core_module("nfl2k5_playoff_picture")
        if picture is None:
            raise RuntimeError("the playoff presentation module is not available in this build")
        pstate_xbe = picture.status(xbe)
        if pstate_xbe == "retail":
            progress("Showing the seven-seed playoff picture and previews", 0, 0)
            xbe, picture_receipt = picture.apply(xbe)
            _write_xbe_bytes(target, xbe)
            if picture.status(_xbe_bytes(target)) != "applied":
                raise ValueError("the seven-seed playoff presentation failed its read-back")
        elif pstate_xbe == "applied":
            picture_receipt = {"already_applied": True}
        else:
            # the executable has no recognisable presentation sites (e.g. a non-retail base); the
            # fourteen-team bracket the season patch just applied is the gate for these same bytes,
            # so record the skip rather than refuse the whole season build
            picture_receipt = {"skipped": pstate_xbe}
        season_receipt = {**season_receipt, "playoff_picture": {k: v for k, v in picture_receipt.items() if k != "edits"}}
        progress("Writing the real 2026 schedule into the franchise template", 0, 0)
        doc = json.loads((ROOT / "data" / "nfl_2026_schedule.json").read_text(encoding="utf-8"))
        template, info = fs.encode_schedule(doc)
        # the 3-game preseason block goes right after the regular-season records (read by the
        # rewritten generator of the season patch's ``preseason`` group)
        preseason_block, preseason_info = fs.encode_preseason(doc) if hasattr(fs, "encode_preseason") else (b"", {"games": 0})
        fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            # Pack 0 is found through the image's own XDVDFS directory, never at a remembered byte.
            # The first public report of the Advanced preset failing was a legal USA retail .iso whose
            # packs sit at other sectors than the rip this was developed on: the executable patches
            # worked (default.xbe was resolved) while this step read 193 MB from the wrong place and
            # reported the schedule template as "foreign".
            pack_offset, pack_size = _pack0_extent(fd)
            pack = platform_compat.pread(fd, pack_size, pack_offset)
            pstate = fs.pack_status(pack)
            if pstate["state"] == "retail":
                patched, pack_receipt = fs.apply_pack(pack, template, preseason=preseason_block)
                written = 0
                start = None
                for i in range(len(pack)):
                    if pack[i] != patched[i]:
                        if start is None:
                            start = i
                    elif start is not None:
                        platform_compat.pwrite(fd, patched[start:i], pack_offset + start)
                        written += i - start
                        start = None
                if start is not None:
                    platform_compat.pwrite(fd, patched[start:], pack_offset + start)
                    written += len(pack) - start
                os.fsync(fd)
                pack_receipt = {**{k: v for k, v in pack_receipt.items() if k != "records"}, "written_bytes": written,
                                "pack0_byte_offset": pack_offset}
            elif pstate.get("state") == "applied":
                pack_receipt = {"already_applied": True}
            else:
                note = _identity_note(target, pack0=pack)
                raise ValueError(f"pack-0 schedule template is {pstate.get('state')}: "
                                 f"{pstate.get('reason', '')}. {note}".rstrip())
        finally:
            os.close(fd)
        receipt["steps"].append({"step": "season_2026", "xbe": {k: v for k, v in season_receipt.items() if k != "edits"},
                                 "schedule": {"weeks": info["validation"]["weeks"], "games": len(template) // 8,
                                              "preseason_games": preseason_info.get("games", 0), **pack_receipt}})
    if plan.team_history:
        # after the position-pool reclassify and the 2026 schedule: both hash or write the roster header and
        # records this step changes (the pool used count and every +0x2C pointer), neither touches the pool
        history = _core_module("nfl2k5_team_history")
        if history is None:
            raise RuntimeError("the team history module is not available in this build")
        progress("Writing the real team history into the roster template", 0, 0)
        history_receipt = history.apply(target, plan.team_history, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "team_history", **{k: v for k, v in history_receipt.items() if k != "log"},
                                 "log_lines": len(history_receipt.get("log", []))})
    if plan.career_stats:
        # right after the team history: both rebuild the stat pool and the +0x2C pointers. This pass only
        # changes the counters a user CSV names (and inserts the season words it needs), decodes every
        # written value back, and refuses to grow past the pool; the later passes leave the pool alone.
        career = _core_module("nfl2k5_career_stats")
        if career is None:
            raise RuntimeError("the career stats module is not available in this build")
        progress("Importing the career stats CSV into the roster template", 0, 0)
        career_receipt = career.apply(target, plan.career_stats, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "career_stats", **career_receipt})
    if plan.prospect_names:
        # after every other roster pass: the name pool (entry array + string span) is outside what the
        # reclassify, schedule and team-history gates hash, and none of them writes it. The executable half
        # (the cave with the layout's boundary) went in with the XBE step above; both must agree.
        names = _core_module("nfl2k5_prospect_names")
        if names is None:
            raise RuntimeError("the prospect names module is not available in this build")
        progress("Writing the modern prospect names into the roster's name pool", 0, 0)
        names_receipt = names.apply(target, plan.prospect_names, progress=lambda msg: progress(msg, 0, 0))
        baked = names.xbe_boundary(_xbe_bytes(target))
        if baked != names_receipt["boundary"]:
            raise ValueError(f"the executable's prospect-names cave carries boundary {baked}, the name pool needs {names_receipt['boundary']}")
        receipt["steps"].append({"step": "prospect_names", **{k: v for k, v in names_receipt.items() if k != "log"},
                                 "log_lines": len(names_receipt.get("log", []))})
    if plan.player_tags:
        # last of the roster passes: the star bit is the record's trailing pad byte +0x53, which sits
        # outside everything the reclassify, schedule, team-history and prospect-name gates hash or
        # write, so running it here leaves all four of their digests intact.
        tags = _core_module("nfl2k5_player_tags")
        if tags is None:
            raise RuntimeError("the star tag module is not available in this build")
        progress("Tagging the star players in the roster", 0, 0)
        tags_receipt = tags.apply(target, plan.player_tags, progress=lambda msg: progress(msg, 0, 0))
        if not plan.player_star:
            tags_receipt = {**tags_receipt, "note": "player_star is off: the tags are written but nothing draws them"}
        receipt["steps"].append({"step": "player_tags", **{k: v for k, v in tags_receipt.items() if k != "log"},
                                 "log_lines": len(tags_receipt.get("log", []))})
    if plan.roster_edits:
        # after every other roster pass. The star tag is +0x53, the team history rebuilds the stat
        # pool and the +0x2C pointers, the prospect names own the generated-name pool and the
        # reclassify hashes position/order: this pass writes named record fields and shared name
        # strings, and preserves all four, so running it last leaves every earlier gate intact.
        records = _core_module("nfl2k5_roster_records")
        if records is None:
            raise RuntimeError("the roster records module is not available in this build")
        progress("Applying the roster edits", 0, 0)
        # the reclassify pass above retires the OLB code, so an edit authored on a retail roster
        # must not write it back: tell the writer which scheme the disc it is landing on is on
        edits_receipt = records.apply(target, Path(plan.roster_edits),
                                      progress=lambda msg: progress(msg, 0, 0),
                                      scheme="one_pool" if plan.position_pools else None)
        receipt["steps"].append({"step": "roster_edits", "source": plan.roster_edits,
                                 "scheme": "one_pool" if plan.position_pools else "auto",
                                 **{k: v for k, v in edits_receipt.items() if k != "log"},
                                 "log_lines": len(edits_receipt.get("log", []))})
    for swap in plan.commentary:
        cs = _tools_module("nfl2k5_commentary_swap")
        if cs is None:
            raise RuntimeError("commentary swap tool is not available in this build")
        progress(f"Replacing commentary stream {swap.stream}", 0, 0)
        rec = cs.replace_in_place(target, swap.stream, Path(swap.wav)) if hasattr(cs, "replace_in_place") else {"unsupported": True}
        receipt["steps"].append({"step": "commentary", "stream": swap.stream, "wav": swap.wav, **rec})

    if plan.guardian_cap:
        cap = _core_module("nfl2k5_guardian_cap")
        if cap is None:
            raise RuntimeError("Guardian caps are not available in this build")
        progress("Adding guardian caps to helmet C", 0, 0)
        cap_receipt = cap.apply_to_image(target)
        receipt["steps"].append({"step": "guardian_cap", **cap_receipt})

    if music_edits is not None:
        with tempfile.TemporaryDirectory(prefix=".music-fixed-", dir=target.parent) as folder:
            destination = Path(folder) / target.name
            rec = _core_module("nfl2k5_music_build").build_copy(target, destination, music_edits, progress=progress)
            os.replace(destination, target)
        receipt["steps"].append({"step": "music_project", "project": plan.music_project, **rec})

    if plan.scorebug_runtime:
        progress("Installing team logos and scorebug effects (unwitnessed)", 0, 0)
        rec = _core_module("nfl2k5_scorebug_ingame").runtime_apply_in_place(target, with_kickoff=plan.kickoff_relocated)
        receipt["steps"].append({"step": "scorebug_runtime", **rec})
    elif plan.xbe_space or plan.kickoff_relocated:
        progress("Adding experimental extra patch space", 0, 0)
        patched, space_receipt = tt._apply_all(
            _xbe_bytes(target), wanted=None, catch_slider=False, arc_table=False,
            xbe_space=plan.xbe_space, kickoff_relocated=plan.kickoff_relocated,
            dynamic_kickoff_settings=plan.dynamic_kickoff_settings)
        _write_xbe_bytes(target, patched)
        receipt["steps"].append({"step": "xbe_space", **space_receipt,
                                 "xbe_space": tt.xbe_space_patch.status(patched),
                                 "kickoff_relocated": tt.kickoff_relocated_patch.status(patched),
                                 "kickoff_relocated_settings": tt.kickoff_relocated_patch.read_settings(patched)})

    if plan.music_library:
        library = _core_module("nfl2k5_music_banks")
        progress("Planning your music library on the working image", 0, 0)
        preview = library.plan(target, plan.music_library)
        progress(f"Music output: {preview['layout']['image_size']:,} bytes; scratch: {preview['scratch_bytes']:,} bytes", 0, 0)
        with tempfile.TemporaryDirectory(prefix=".music-library-", dir=target.parent) as folder:
            destination = Path(folder) / target.name
            rec = library.rebuild(target, destination, plan.music_library, expected_plan=preview, progress=progress)
            os.replace(destination, target)
        receipt["steps"].append({"step": "music_library", "library": plan.music_library, **rec})

    receipt["result"] = inspect(target, screen_timing=plan.screen_timing)
    return receipt


def save_receipt(receipt: dict[str, Any], path: Path | str) -> None:
    Path(path).write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8", newline="\n")


__all__ = ["BuildPlan", "CommentarySwap", "PRESETS", "PRESET_TITLES", "apply_preset", "availability", "build", "inspect", "save_receipt"]
