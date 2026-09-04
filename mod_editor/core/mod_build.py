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
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
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
    # one EDGE / one LB / one interior pool across 4-3 and 3-4 (XBE pools + playbook recode + ROST
    # reclassification; needs a disc image; implies scheme_labels)
    position_pools: bool = False
    # 2026 season: real 2026 schedule template in pack 0 (17 games, 18 weeks, one bye; the real 3-game
    # preseason after it) + year/calendar/season-length/14-team-playoffs/preseason executable patches
    # (rookie birth years and the DOB line follow the year); needs a disc image
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
    # CREATED from the copy; costs one pool dword per season row (the game folds the oldest seasons a bit earlier)
    team_history: str = ""
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
    # community playbook packs (.2k5book recipes) installed into the copy's team books.
    # A recipe, not retail bytes: the same formation/play/link rows the designers stage, so
    # Build compiles them against the user's own disc.  Never in a preset -- a community book
    # is a user choice like commentary, and a curated official one belongs in EXPERIMENTAL first.
    playbook_packs: tuple[str, ...] = ()
    # text
    edge_rename: bool = False
    # presentation
    scorebug: bool = False
    commentary: list[CommentarySwap] = field(default_factory=list)
    # free-form description carried into receipts / packs
    name: str = ""
    author: str = ""
    notes: str = ""

    def wants_xbe_patch(self) -> bool:
        return (self.throw or self.catch_slider or self.accel_ramp or self.draft_ai or self.returner_fix
                or self.progression or self.scheme_labels or self.camera or self.kick_rules or self.kick_power or self.position_pools
                or self.season_2026 or self.widescreen or self.overtime or self.team_column or self.seven_on_seven
                or self.position_row or self.probowl_order or bool(self.penalties) or bool(self.uniform_choice)
                or self.kick_laces or self.franchise_practice or bool(self.prospect_names) or self.player_star)

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
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": False,
        "catch_slider": True, "accel_ramp": False, "draft_ai": True, "returner_fix": True, "progression": False,
        "edge_rename": False, "scorebug": False, "scheme_labels": False, "camera": False,
        "kick_rules": False, "kick_power": True, "kickoff_alignment": False,
        "position_pools": False, "season_2026": False, "widescreen": False, "overtime": False, "team_column": True, "seven_on_seven": False, "team_history": "", "position_row": True, "probowl_order": True, "penalties": "", "uniform_choice": "", "kick_laces": False, "franchise_practice": False, "prospect_names": "", "player_star": False,
    },
    # ADVANCED = basic + everything that modernises the game (Noah's tweaks and breakthroughs).
    "softdrink_advanced": {
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True,
        "edge_rename": True, "scorebug": True, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": False,
        "position_pools": True, "season_2026": True, "widescreen": False, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "choice", "kick_laces": False, "franchise_practice": True, "prospect_names": "modern", "player_star": True,
    },
    # EXPERIMENTAL = advanced + widescreen and anything still rough (dynamic-kickoff line-up).
    "softdrink_experimental": {
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True,
        "edge_rename": True, "scorebug": True, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": True,
        "position_pools": True, "season_2026": True, "widescreen": True, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "choice", "kick_laces": True, "franchise_practice": True, "prospect_names": "modern", "player_star": True,
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
        "returner_fix": _core_module("nfl2k5_returner_fix") is not None,
        "progression": _core_module("nfl2k5_progression") is not None,
        "scheme_labels": _core_module("nfl2k5_modern_positions") is not None,
        "camera": _core_module("nfl2k5_camera") is not None,
        "kick_rules": _core_module("nfl2k5_kick_rules") is not None,
        "kickoff_alignment": _tools_module("nfl2k5_kickoff_alignment") is not None,
        "widescreen": _core_module("nfl2k5_widescreen") is not None,
        "overtime": _core_module("nfl2k5_overtime") is not None,
        "team_history": (_core_module("nfl2k5_team_history") is not None
                         and (ROOT / "data" / "nfl2k5_retail_team_history.csv").exists()),
        "team_column": _core_module("nfl2k5_team_column") is not None,
        "position_row": _core_module("nfl2k5_position_row") is not None,
        "probowl_order": _core_module("nfl2k5_probowl_order") is not None,
        "penalties": _core_module("nfl2k5_penalties") is not None,
        "uniform_choice": _core_module("nfl2k5_uniform_choice") is not None,
        "kick_laces": _core_module("nfl2k5_kick_laces") is not None,
        "franchise_practice": _core_module("nfl2k5_franchise_practice") is not None,
        "prospect_names": (_core_module("nfl2k5_prospect_names") is not None
                           and (ROOT / "data" / "nfl2k5_modern_names.csv").exists()),
        "player_star": _core_module("nfl2k5_player_star") is not None,
        "player_tags": _core_module("nfl2k5_player_tags") is not None,
        "seven_on_seven": (SEVEN_ON_SEVEN_RELEASED
                           and _core_module("nfl2k5_seven_on_seven") is not None
                           and _core_module("nfl2k5_seven_on_seven_book") is not None),
        "season_2026": (_core_module("nfl2k5_season_length") is not None
                        and _tools_module("nfl2k5_franchise_schedule") is not None
                        and (ROOT / "data" / "nfl_2026_schedule.json").exists()),
        "position_pools": (_core_module("nfl2k5_position_pools") is not None
                           and _tools_module("nfl2k5_playbook_position_recode") is not None
                           and _tools_module("nfl2k5_roster_reclassify") is not None),
        "scorebug": (_tools_module("nfl2k5_scorebug_layout") is not None
                     and (ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn" / "shield_espn_modern.png").exists()
                     and (ROOT / "assets" / "intermediate" / "nfl2k5" / "models" / "0346_0078_score_bug.gltf").exists()),
        "edge_rename": _core_module("nfl2k5_edge_rename") is not None,
        "commentary": _tools_module("nfl2k5_commentary_swap") is not None,
        "playbook_packs": (_core_module("nfl2k5_playbook_pack") is not None
                           and _tools_module("nfl2k5_playbook_position_recode") is not None),
    }


def inspect(source: Path | str) -> dict[str, Any]:
    """Current state of every patch in ``source`` (a default.xbe or a disc image)."""

    source = Path(source)
    report = tt.read_any(source)
    out: dict[str, Any] = {
        "path": str(source), "container": report.get("container"),
        "throw": report["settings"], "catch_slider": report.get("catch_slider"),
        "accel_ramp": report.get("accel_ramp"), "draft_ai": report.get("draft_ai"),
        "returner_fix": report.get("returner_fix", "unknown"), "progression": report.get("progression", "unknown"),
        "scheme_labels": report.get("scheme_labels", "unknown"), "camera": report.get("camera", "unknown"),
        "kick_rules": report.get("kick_rules", "unknown"), "kick_power": report.get("kick_power", "unknown"), "widescreen": report.get("widescreen", "unknown"),
        "overtime": report.get("overtime", "unknown"), "team_column": report.get("team_column", "unknown"),
        "position_row": report.get("position_row", "unknown"), "probowl_order": report.get("probowl_order", "unknown"),
        "penalties": report.get("penalties", "unknown"),
        "uniform_choice": report.get("uniform_choice", "unknown"),
        "kick_laces": report.get("kick_laces", "unknown"),
        "franchise_practice": report.get("franchise_practice", "unknown"),
        # the executable half alone is never "applied": the name pool lives in pack 0 (both halves below for images)
        "prospect_names": ("partial" if report.get("prospect_names") == "applied" else report.get("prospect_names", "unknown")),
        "player_star": report.get("player_star", "unknown"), "player_tags": "n/a",
        "seven_on_seven": report.get("seven_on_seven", "unknown"), "seven_on_seven_book": "n/a", "team_history": "n/a",
        "position_pools": "n/a", "season_2026": "n/a", "kickoff_alignment": "n/a",
        "scorebug": "n/a", "edge_rename": "unknown", "commentary": "unknown",
        # a pack is a recipe compiled into the books; there is no single site to read back,
        # so the receipt (not inspect) is the record of which packs went in
        "playbook_packs": "n/a",
    }
    if report.get("container") == "xiso":
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
    if "edge_rename" in report:
        out["edge_rename"] = report.get("edge_rename")
        out["edge_rename_disc"] = report.get("edge_rename_disc")
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
            if length != len(payload):
                raise ValueError("default.xbe size changed")
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


def build(plan: BuildPlan, progress: ProgressSink | None = None) -> dict[str, Any]:
    """Apply the whole plan to a copy of ``plan.source`` at ``plan.target``; return the receipt."""

    progress = progress or (lambda *_a: None)
    source, target = Path(plan.source), Path(plan.target)
    if target.exists() and target.resolve() == source.resolve():
        raise ValueError("target must not be the source")
    if target.exists() and not plan.overwrite:
        raise FileExistsError(f"{target} exists")
    receipt: dict[str, Any] = {"plan": plan.to_recipe(), "steps": [], "source": str(source), "target": str(target)}
    is_image = tt.is_disc_image(source)
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
    if plan.prospect_names and not is_image:
        raise ValueError("modern prospect names need a disc image (the name pool lives in the roster template in pack 0)")
    if plan.player_tags and not is_image:
        raise ValueError("star tags need a disc image (the roster records live in pack 0)")
    if plan.playbook_packs and not is_image:
        raise ValueError("playbook packs need a disc image (the books live in the archive packs)")

    # 1. copy + executable and text patches through the proven writer (throw tables, caves, EDGE rename
    #    including its disc text spans when the source is an image)
    if plan.wants_xbe_patch() or plan.edge_rename:
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
                                  "kick_laces": plan.kick_laces, "franchise_practice": plan.franchise_practice,
                                  "prospect_names": plan.prospect_names,
                                  "player_star": plan.player_star}
        if settings is not None:
            kwargs["settings"] = settings
        step = tt.write_copy(source, target, **kwargs)
        receipt["steps"].append({"step": "xbe", **{k: step.get(k) for k in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "edge_rename_disc", "returner_fix", "progression", "scheme_labels", "camera", "kick_rules", "kick_power", "widescreen", "overtime", "team_column", "seven_on_seven", "position_row", "probowl_order", "penalties", "uniform_choice", "kick_laces", "franchise_practice", "prospect_names", "player_star", "changed_byte_count")}})
    else:
        progress("Copying the image", 0, 0)
        if target.exists():
            target.unlink()
        shutil.copyfile(source, target)
        receipt["steps"].append({"step": "copy"})

    # 3. presentation on the copy
    if plan.scorebug:
        sbl = _tools_module("nfl2k5_scorebug_layout")
        if sbl is None:
            raise RuntimeError("scorebug layout tool is not available in this build")
        progress("Re-laying the scorebug (mesh, placement, textures)", 0, 0)
        rec = sbl.apply_in_place(target)
        receipt["steps"].append({"step": "scorebug", **{k: rec.get(k) for k in ("filled_bytes", "padding_bytes", "wrapper_identical", "root", "textures", "text_colours", "persistent", "hud_layout", "layout")}})
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
    if plan.playbook_packs:
        # after every other playbook writer (the position recode rewrites defensive category
        # codes and the 7-on-7 writer owns the practice book; a pack only ever replaces
        # offensive formations/plays inside a team book, so the three do not overlap).
        packs = _core_module("nfl2k5_playbook_pack")
        if packs is None:
            raise RuntimeError("the playbook pack module is not available in this build")
        progress("Installing the community playbook packs", 0, 0)
        pack_receipt = packs.apply_packs_to_image(
            target, [Path(p) for p in plan.playbook_packs],
            progress=lambda msg: progress(msg, 0, 0),
        )
        receipt["steps"].append({"step": "playbook_packs", **pack_receipt})
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
                raise ValueError(f"pack-0 schedule template is {pstate.get('state')}: {pstate.get('reason', '')}")
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
    for swap in plan.commentary:
        cs = _tools_module("nfl2k5_commentary_swap")
        if cs is None:
            raise RuntimeError("commentary swap tool is not available in this build")
        progress(f"Replacing commentary stream {swap.stream}", 0, 0)
        rec = cs.replace_in_place(target, swap.stream, Path(swap.wav)) if hasattr(cs, "replace_in_place") else {"unsupported": True}
        receipt["steps"].append({"step": "commentary", "stream": swap.stream, "wav": swap.wav, **rec})

    receipt["result"] = inspect(target)
    return receipt


def save_receipt(receipt: dict[str, Any], path: Path | str) -> None:
    Path(path).write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8", newline="\n")


__all__ = ["BuildPlan", "CommentarySwap", "PRESETS", "PRESET_TITLES", "apply_preset", "availability", "build", "inspect", "save_receipt"]
