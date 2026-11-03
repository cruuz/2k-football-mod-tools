"""Which build step a disc build is in, what it was doing, and a safe way to leave a cosmetic step out (b791-h3).

Coach Edwards' builds took 4 to 5 hours and twice ended with one line, "Couldn't make the disc. cannot keep the retail
scratch word:", from a cosmetic stadium texture. Nothing said which step, which stadium or why, and everything the build
had done was thrown away. This module gives every build three things:

* **Step context.** The build marks each step (``begin`` for the long sequence in ``mod_build._build``, ``scoped`` for
  the late-owner helpers, ``resource`` for a loop over files). An exception that leaves the build reads
  ``During <step> (<resource>): <original message>``, keeps the original exception as ``__cause__`` and as
  ``.original``, exposes ``.step``, ``.label`` and ``.resource``, and stays an instance of the original's family
  (a ValueError stays a ValueError), so every caller that catches by type behaves as before.
* **A record of the run.** ``track`` records every progress line (repeats of one counter collapse into one line per
  30 seconds), the steps with their times, notes, left-out steps and a few facts (options, colour values, source disc,
  project fingerprint). ``build_report`` turns that record into the build log, the errors.log entry and the zip.
* **Optional steps.** ``optional`` wraps a visual step whose failure can be undone without affecting what later steps
  need (the stadium writers, the presentation scenes, the kit and uniform repairs, ...; the list and the reasons are
  in ``mod_build``). While it runs, every write to the build's private disc copy is journaled: the original bytes of
  each 16 KiB block are saved the first time a write changes them, the image size is remembered, and the sidecar
  receipts beside the copy are copied. If the step raises, the copy is restored exactly (and read back), the receipt is
  rolled back, a plain note is added ("Modern playing surfaces was left out: <reason>. Your disc keeps the playing
  surfaces as they were.") and the build goes on. A cancel always stops the build. If the step wrote in a way the
  journal cannot undo (a buffered or memory-mapped writer, a rename over the copy, a worker process writing the copy),
  the build stops as before, with the step named.

Switches (environment): ``NFL2K5_BUILD_STRICT=1`` makes optional steps stop the build like any other step (release
gate builds); ``NFL2K5_BUILD_JOURNAL=0`` turns the journal off (a failed optional step is then left out only when it
had not opened the copy for writing yet).

Nothing here changes what a successful step writes: the journal only reads and remembers.
"""
from __future__ import annotations

import contextvars
from functools import wraps
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import traceback
from typing import Any, Callable, Iterable

STRICT_ENV = "NFL2K5_BUILD_STRICT"
JOURNAL_ENV = "NFL2K5_BUILD_JOURNAL"

#: The words that follow "During" (and that start "... was left out") for every step a build can stop in.
STEP_LABELS: dict[str, str] = {
    "build": "the build",
    "preflight": "the checks before the build",
    "artwork_recipe": "the check of your project's artwork recipe",
    "project_check": "the quick check of your project",
    "project": "your project's artwork (the texture compile)",
    "music_project_prepare": "the preparation of your Music project",
    "xbe": "the copy of your game disc and the default.xbe patches",
    "copy": "the copy of your game disc",
    "retire_seven_on_seven": "removing the unavailable 7-on-7 practice",
    "scorebug": "the ESPN scorebar layout",
    "playbook_packs": "the complete offensive playbooks",
    "option_playbook_packs": "the option playbook packs",
    "defense_playbook_packs": "the defense playbook packs",
    "position_pools": "the one-pool positions",
    "depth_chart_rows": "the SPECIAL depth-chart rows",
    "kickoff_alignment": "the dynamic kickoff alignment",
    "kickoff_returns": "the kickoff return blocking assignments",
    "seven_on_seven_book": "the 7-on-7 practice playbook",
    "community_playbook_packs": "the community playbook packs",
    "depth_roles": "the X / Z / SLOT and nickel / dime roles",
    "screen_timing": "the screen pass timing",
    "playbook_menus": "the playbook menu check",
    "season_2026": "the 2026 season",
    "sofi_super_bowl_route": "the SoFi Super Bowl route",
    "prospect_names": "the modern prospect names",
    "player_tags": "the star player tags",
    "roster_history": "the roster edits and their history",
    "team_names_2026": "the 2026 team names",
    "commentary": "the commentary replacements",
    "guardian_cap": "the Guardian caps",
    "music_project": "your Music project",
    "coach_ai_resources": "the automatic CPU coach profiles",
    "play_intents": "the final playbook pairing",
    "scorebug_runtime": "the team logos and scorebug effects",
    "guardian_overlay": "the Guardian cap overlay",
    "xbe_space": "the extra patch space and its owners",
    "music_library": "your music library",
    "helmet_finish": "the helmet finish",
    "weather_haze": "the dry-weather haze response",
    "number_kerning": "the jersey number kerning",
    "modern_color_xbe": "Modern colour and lighting (light rigs)",
    "verify_composed": "the check of the composed disc",
    "hires_pack": "the Hi-res pack",
    "modern_naming": "the modern mode names",
    "roster_arena_growth": "the roster growth (reserves and created teams)",
    "crib_trophy_room": "the Crib Trophy Room cut",
    "crib_reclaim": "the Crib movie cut",
    "position_pool_filters": "the Outside Linebackers rows",
    "rb_rename_scenes": "renaming HB to RB on the roster screens",
    "espn25_rosters": "the historic moment rosters",
    "espn25_more_moments": "the historic Anniversary moments",
    "historic_styles": "the historic teams' retail uniforms and logos",
    "historic_stock_books": "the stock books for historic teams",
    "historic_rosters_2026": "the 75 historic season rosters",
    "espn25_plan": "your ESPN Anniversary edits",
    "era_kits": "the Anniversary era kit pass",
    "unc_bowl_uniforms": "the Unc Bowl uniform repair",
    "nyg_shoulder_numbers": "the Giants shoulder number repair",
    "kit_fixes_2026": "the 2026 home and away kit repair",
    "kit_fixes_2026_alts": "the 2026 alternate and throwback kit repair",
    "kit_fixes_2026_uf3": "the 2026 kit finish repair",
    "kit_fixes_2026_sea1": "the 2026 Seattle helmet and digit repair",
    "kit_fixes_2026_ov1": "the 2026 kit overlap repair",
    "glyph_fixes_2026": "the 2026 nameplate letter repair",
    "menu_icon_uf3": "the 2026 Pittsburgh schedule picture fix",
    "menu_helmet_w2026": "the 2026 Washington helmet card fix",
    "menu_chiefs_2026": "the 2026 Chiefs menu card fix",
    "pants_hem_2026": "the 2026 pants hem",
    "kit_fixes_2026_ku1": "the 2026 Chiefs kit repair",
    "kit_fixes_2026_sw1": "the 2026 sleeve swoosh repair",
    "kit_fixes_2026_names": "the 2026 nameplate spacing repair",
    "sideline_2026": "the 2026 sideline uniform repair",
    "moment_kits": "the Anniversary moment kit pass",
    "nameplate_fixes_2026": "the 2026 nameplate fix",
    "team_sleeves": "Team-coloured sleeves",
    "qb_throw_power": "the quarterbacks' Throw Power",
    "roster_refresh": "the dated roster refresh",
    "draft_pick_ownership": "the draft pick ownership",
    "hback_roles": "the H-back roles",
    "team_ratings": "the modern team ratings",
    "classic_teams": "the classic teams",
    "moment_scans": "the retail face scans for the Anniversary and classic teams",
    "weather_plan": "your stadium climate edits",
    "modern_color_bundles": "Modern colour and lighting (stadium bundles)",
    "modern_arrowhead": "Modern Arrowhead",
    "modern_metlife": "Modern MetLife Stadium",
    "modern_venues_2026": "2026 venue art",
    "modern_metlife_model": "the Modern MetLife model",
    "modern_sofi": "SoFi Stadium",
    "modern_highmark": "Highmark Stadium",
    "modern_att": "AT&T Stadium",
    "modern_levis": "Levi's Stadium",
    "modern_allegiant": "Allegiant Stadium",
    "modern_mercedes_benz": "Mercedes-Benz Stadium",
    "modern_usbank": "U.S. Bank Stadium",
    "modern_lucas_oil": "Lucas Oil Stadium",
    "modern_state_farm": "State Farm Stadium",
    "modern_hard_rock": "Hard Rock Stadium",
    "modern_gillette": "Gillette Stadium",
    "modern_lambeau": "Lambeau Field",
    "modern_everbank": "EverBank Stadium",
    "modern_board_kit": "Modern stadium boards",
    "modern_practice_field": "the Modern practice facility",
    "stadium_shadows": "the stadium shadow pass",
    "modern_surfaces": "Modern playing surfaces",
    "missing_midfield": "the late 2026 midfield logo pass",
    "espn_marks_2026": "ESPN presentation marks (2026)",
    "espn_wipes_boards_2026": "ESPN 2026 wipes and boards",
    "kick_meter_2026": "the Kick meter (2026 ESPN style)",
    "modern_goalposts": "Modern goalposts",
    "modern_coaches": "2026 head coaches",
    "modern_fans": "2026 fans",
    "modern_officials": "2025-26 officials",
    "modern_helmets": "Modern helmets and facemasks",
    "hair_styles": "the hair styles",
    "cpu_ai": "the CPU QB and defender reads",
    "play_art_routes": "the full-length play art routes",
    "commentary_final": "the final commentary pass",
    "menu_icon_orientation": "the 2026 Denver schedule picture fix",
    "rookie_faces": "the rookie faces",
    "trim_intro_videos": "trimming the intro videos",
    "custom_intro": "your custom intro video",
    "moments_after_intro": "the check of the Anniversary moments after the intro video pass",
    "moment_coaches": "the historical Anniversary coaches",
    "moment_context": "the Super Bowl context and moment stats",
    "moment_booth": "the Super Bowl booth welcome",
    "espn25_fields": "the period Anniversary field pass",
    "era_ball": "the era ball",
    "broadcast_greens": "the Broadcast greens pass",
    "super_bowl_hosts": "the franchise Super Bowl host pass",
    "team_number_scale": "the per-kit jersey number sizes",
    "run_blocking": "Run blocking",
    "pass_protection": "Pass protection",
    "pass_rush_stats": "Pass rush stats",
    "qb_accuracy": "Accurate short throws and throws on the run",
    "formation_art_spacing": "the play art icon spacing",
    "force_out": "Modern sideline catches",
    "practice_injuries": "Franchise practice injuries",
    "sportscenter_lineup": "SportsCenter highlight lineups",
    "ball_carriers": "CPU ball carriers",
    "star_retention": "CPU clubs keep their stars",
    "star_career": "Rookie stars and career stars",
    "draft_clock": "the franchise draft clock",
    "weekly_progression": "Weekly player progression",
    "player_progress": "the Player Progress screen",
    "contract_college_guard": "the Player Contracts college guard",
    "coach_career_fix": "the coach career counter fix",
    "sim_cb_tackles": "Cornerback tackle credit",
    "sim_stats": "the franchise sim pace fix",
    "option_defaults": "the SOFTDRINK default options",
    "clock_led": "Modern clock digits",
    "inbox_standings": "Inbox standings",
    "module_loader": "On-demand Career Home",
    "return_coverage": "Return coverage pursuit angles",
    "preseason_warning": "the pre-season roster warning",
    "sim_rb_injuries": "Simulated RB short injuries",
    "sim_realism": "Simulated season realism",
    "indicator_names": "the player name label",
    "champions_history": "the champions history",
    "disc_compaction": "compacting the finished disc",
    "final_checks": "the final checks of the finished disc",
    "music_check": "the check of the music playlist",
    "hash": "the final check of the finished disc",
    "publish": "publishing the finished disc",
}

#: The second sentence of a "was left out" note: what the finished disc has instead.
KEPT: dict[str, str] = {
    "modern_color_bundles": "Your disc keeps the stadium textures as they were; the light rigs keep your colour settings.",
    "modern_arrowhead": "Your disc keeps Arrowhead Stadium as it was.",
    "modern_metlife": "Your disc keeps the Giants and Jets stadium as it was.",
    "modern_venues_2026": "Your disc keeps the home stadiums' field and wall art as they were.",
    "modern_metlife_model": "Your disc keeps the Giants and Jets stadium model as it was.",
    "modern_sofi": "Your disc keeps the Rams and Chargers stadiums as they were.",
    "modern_highmark": "Your disc keeps the Bills' stadium as it was.",
    "modern_att": "Your disc keeps the Cowboys' stadium as it was.",
    "modern_levis": "Your disc keeps the 49ers' stadium as it was.",
    "modern_allegiant": "Your disc keeps the Raiders' stadium as it was.",
    "modern_mercedes_benz": "Your disc keeps the Falcons' stadium as it was.",
    "modern_usbank": "Your disc keeps the Vikings' stadium as it was.",
    "modern_lucas_oil": "Your disc keeps the Colts' stadium as it was.",
    "modern_state_farm": "Your disc keeps the Cardinals' stadium as it was.",
    "modern_hard_rock": "Your disc keeps the Dolphins' stadium as it was.",
    "modern_gillette": "Your disc keeps the Patriots' stadium as it was.",
    "modern_lambeau": "Your disc keeps the Packers' stadium as it was.",
    "modern_everbank": "Your disc keeps the Jaguars' stadium as it was.",
    "modern_board_kit": "Your disc keeps the stadium boards as they were.",
    "modern_practice_field": "Your disc keeps the practice field as it was.",
    "stadium_shadows": "Your disc keeps the field shadows as they were.",
    "modern_surfaces": "Your disc keeps the playing surfaces as they were.",
    "missing_midfield": "Your disc keeps those midfield logos as they were.",
    "espn_marks_2026": "Your disc keeps the ESPN marks as they were.",
    "espn_wipes_boards_2026": "Your disc keeps the replay wipes and boards as they were.",
    "kick_meter_2026": "Your disc keeps the kick meter as it was.",
    "modern_goalposts": "Your disc keeps the goalposts as they were.",
    "modern_coaches": "Your disc keeps the coach models and pictures as they were.",
    "modern_fans": "Your disc keeps the crowds as they were.",
    "modern_officials": "Your disc keeps the officials as they were.",
    "modern_helmets": "Your disc keeps the helmets and facemasks as they were.",
    "menu_icon_orientation": "Your disc keeps that picture as it was.",
    "espn25_fields": "Your disc keeps the Anniversary moments on their current fields.",
    "era_ball": "Your disc keeps the ball as it was.",
    "broadcast_greens": "Your disc keeps the field colours as they were.",
    "super_bowl_hosts": "Your franchise Super Bowls keep their neutral stadium.",
    "moment_kits": "Your disc keeps the uniforms the Anniversary moments already had.",
    "team_sleeves": "Your disc keeps the long sleeves as they were.",
    **{step: "Your disc keeps those uniforms as they were." for step in (
        "era_kits", "unc_bowl_uniforms", "nyg_shoulder_numbers", "kit_fixes_2026", "kit_fixes_2026_alts",
        "kit_fixes_2026_uf3", "kit_fixes_2026_sea1", "kit_fixes_2026_ov1", "glyph_fixes_2026", "pants_hem_2026",
        "kit_fixes_2026_ku1", "kit_fixes_2026_sw1", "kit_fixes_2026_names", "sideline_2026", "nameplate_fixes_2026")},
    **{step: "Your disc keeps those menu pictures as they were." for step in (
        "menu_icon_uf3", "menu_helmet_w2026", "menu_chiefs_2026")},
}
DEFAULT_KEPT = "Your disc keeps that part as it was."

#: Writers that open the private copy through a buffered file object but write only through its descriptor
#: (``f.fileno()`` with ``pwrite``), so the journal sees every byte. ``test_b791_h3_build_steps`` parses each one
#: and fails if one starts writing through the file object itself.
DESCRIPTOR_ONLY_WRITERS = frozenset({
    ("nfl2k5_historic_styles", "rewrite_archive"),
    ("nfl2k5_super_bowl_hosts", "_append"),
    ("nfl2k5_anniversary_pack", "append_to_image"),
    ("nfl2k5_kick_meter_2026", "_transaction"),
    ("nfl2k5_modern_goalposts", "_write_xbe"),
})

_DIGITS = re.compile(r"\d+")
_CLASS_PREFIX = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_.]*)?(?:Error|Exception):\s*")
#: A repeated progress line (same text once digits are ignored) is kept once per this many seconds.
COLLAPSE_SECONDS = 30.0
#: Progress records kept in memory (the first and the most recent; a marker says how many were dropped between).
MAX_RECORDS = 20000
KEEP_FIRST = 2000


def label_of(step_id: str, label: str | None = None) -> str:
    return label or STEP_LABELS.get(step_id) or step_id.replace("_", " ")


def plain_reason(exc: BaseException, limit: int = 400) -> str:
    """The cause in plain words: no class names, first line only, no trailing full stop."""
    text = str(exc).strip()
    text = _CLASS_PREFIX.sub("", text).strip()
    first = text.splitlines()[0].strip() if text else ""
    if not first or first.endswith(":"):
        detail = first.rstrip(":").strip()
        first = (f"{detail} (the step gave no reason)" if detail else
                 f"the step stopped without saying why ({type(exc).__name__})")
    if len(first) > limit:
        first = first[: limit - 3].rstrip() + "..."
    return first.rstrip(". ")


# ------------------------------------------------------------------------------------------------------------------
# The wrapped exception
# ------------------------------------------------------------------------------------------------------------------

class StepFailure(Exception):
    """An error that left one build step. ``str()`` is the "During <step> (<resource>): <message>" sentence."""

    step: str = ""
    label: str = ""
    resource: str | None = None
    original: BaseException | None = None
    last_progress: str = ""
    undo: str = ""

    def __str__(self) -> str:  # noqa: D105
        return getattr(self, "message", "") or super().__str__()


#: The families a wrapped error keeps (most specific first), so ``except ValueError`` and friends behave as before.
_FAMILIES = (FileExistsError, FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError, TimeoutError,
             OSError, KeyError, IndexError, LookupError, ValueError, TypeError, AttributeError, NotImplementedError,
             RecursionError, RuntimeError, ZeroDivisionError, OverflowError, ArithmeticError, AssertionError,
             ImportError, MemoryError, EOFError)
_WRAPPERS: dict[type, type] = {}
for _base in _FAMILIES:
    _cls = type(f"Step{_base.__name__}", (StepFailure, _base), {"__module__": __name__,
                                                               "__doc__": f"A {_base.__name__} that left a build step."})
    _WRAPPERS[_base] = _cls
    globals()[_cls.__name__] = _cls
del _base, _cls


_DYNAMIC: dict[type, type] = {}


def _wrapper_for(exc: BaseException) -> type:
    """The wrapper class: a StepFailure that is also an instance of the original's own class.

    The standard families use the named classes above (StepValueError, ...). Any other class (the Studio's
    ValidationError, a module's KickMeterError, a test's sentinel) gets a subclass of its own, so ``except
    ThatError`` around a build still catches it."""
    cls = type(exc)
    if cls in _WRAPPERS:
        return _WRAPPERS[cls]
    cached = _DYNAMIC.get(cls)
    if cached is None:
        try:
            cached = type(f"Step{cls.__name__}", (StepFailure, cls),
                          {"__module__": __name__, "__doc__": f"A {cls.__name__} that left a build step."})
        except TypeError:  # pragma: no cover - a class that cannot be combined (layout conflict): nearest family
            cached = next((_WRAPPERS[base] for base in _FAMILIES if isinstance(exc, base)), StepFailure)
        _DYNAMIC[cls] = cached
    return cached


def is_cancel(exc: BaseException) -> bool:
    """A user's Cancel (``nfl2k5_project_fit.BuildCancelled``) is control flow: never wrapped, never left out."""
    return any(cls.__name__ == "BuildCancelled" for cls in type(exc).__mro__)


def _chain_attr(exc: BaseException, attribute: str) -> Any:
    """The first ``attribute`` along ``exc``'s cause/context chain: a step stamp survives an error that was reworded
    into a new exception on its way out (``raise ValueError(words) from exc``)."""
    seen, current = 0, exc
    while current is not None and seen < 12:
        value = getattr(current, attribute, None)
        if value is not None:
            return value
        current = current.__cause__ or current.__context__
        seen += 1
    return None


def stage_words(exc: BaseException, target: Path | None) -> str | None:
    """Plain words for an error about one of the build's own private files (its .studio-build-* folder), or None."""
    if not isinstance(exc, OSError) or target is None:
        return None
    try:
        from . import mod_build
    except Exception:  # noqa: BLE001  # pragma: no cover
        return None
    stage = Path(target).parent
    for name in (getattr(exc, "filename", None), getattr(exc, "filename2", None)):
        if not name:
            continue
        path = Path(str(name))
        role = mod_build._private_stage_role(path)
        try:
            inside = path.is_relative_to(stage) or path.resolve().is_relative_to(stage.resolve())
        except (OSError, ValueError):
            inside = False
        if role and inside:
            return (f"{role} could not be read ({exc.strerror or 'missing'}); this is a fault inside the Studio's own "
                    "build folder, not in the files you chose")
    return None


def _stamp(exc: BaseException, attribute: str, value: Any) -> None:
    if getattr(exc, attribute, None) is None:
        try:
            setattr(exc, attribute, value)
        except (AttributeError, TypeError):  # pragma: no cover - an exception type without a __dict__
            pass


def wrap(exc: BaseException, step: str, label: str, resource: str | None = None, *,
         last_progress: str = "", undo: str = "") -> StepFailure:
    """The "During ..." error for ``exc`` (not raised; the caller raises it ``from exc``)."""
    text = str(exc).strip()
    if text and label and text.casefold().startswith(label.casefold() + ":"):
        text = text[len(label) + 1:].strip()          # "During Modern Arrowhead: Modern Arrowhead: ..." reads twice
    if not text:
        text = f"the step stopped without saying why ({type(exc).__name__})"
    head = f"During {label}" + (f" ({resource})" if resource else "")
    cls = _wrapper_for(exc)
    try:
        # No call to the original class's own __init__ (it may need other arguments): the instance gets the
        # message as its args and keeps the original's attributes (a selector, a kit list, ...).
        wrapped = cls.__new__(cls, f"{head}: {text}")
        BaseException.__init__(wrapped, f"{head}: {text}")
        for key, value in getattr(exc, "__dict__", {}).items():
            if not key.startswith("_studio_"):
                setattr(wrapped, key, value)
    except Exception:  # pragma: no cover - an exception type that refuses all of that
        wrapped = StepFailure(f"{head}: {text}")
    wrapped.message = f"{head}: {text}"
    wrapped.step, wrapped.label, wrapped.resource = step, label, resource
    wrapped.original, wrapped.last_progress, wrapped.undo = exc, last_progress, undo
    if isinstance(exc, OSError) and isinstance(wrapped, OSError):
        for name in ("errno", "strerror", "filename", "filename2"):
            try:
                setattr(wrapped, name, getattr(exc, name, None))
            except (AttributeError, TypeError):  # pragma: no cover
                pass
    return wrapped


# ------------------------------------------------------------------------------------------------------------------
# The tracker
# ------------------------------------------------------------------------------------------------------------------

_ACTIVE: contextvars.ContextVar["Tracker | None"] = contextvars.ContextVar("studio_build_tracker", default=None)


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class Tracker:
    """One build's record: steps, progress lines, notes, left-out steps and facts."""

    def __init__(self) -> None:
        self.started_wall = time.time()
        self.started = time.monotonic()
        self.steps: list[dict[str, Any]] = []
        self.records: list[list[Any]] = []      # [first seconds, last seconds, text, done, total, repeats, kind]
        self.dropped = 0
        self.calls = 0
        self.left_out: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self.facts: dict[str, Any] = {}
        self.failure: dict[str, Any] | None = None
        self.result: str = "running"
        self.ended: float | None = None         # seconds from the start when the build itself finished or stopped
        self._sequential: dict[str, Any] | None = None
        self._stack: list[dict[str, Any]] = []
        self._last_key: str | None = None
        self._lock = threading.RLock()
        self.progress = self.recording(None)

    # -- time
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def duration(self) -> float:
        """How long the build ran: up to its finish or stop (a report written afterwards adds nothing)."""
        return self.ended if self.ended is not None else self.elapsed()

    # -- steps
    def _enter_step(self, step_id: str, label: str, kind: str) -> dict[str, Any]:
        now = self.elapsed()
        entry = {"id": step_id, "label": label, "kind": kind, "start": now, "end": None, "lines": 0,
                 "first_record": len(self.records)}
        with self._lock:
            self.steps.append(entry)
            self._add_record(now, f"-- {label} --", 0, 0, kind="step")
        return entry

    def begin(self, step_id: str, label: str | None = None) -> None:
        label = label_of(step_id, label)
        with self._lock:
            if self._sequential is not None:
                if (self._sequential["id"], self._sequential["label"]) == (step_id, label) and self._sequential["end"] is None:
                    return
                if self._sequential["end"] is None:
                    self._sequential["end"] = self.elapsed()
            self._sequential = self._enter_step(step_id, label, "step")

    def push(self, step_id: str, label: str | None = None, kind: str = "scoped") -> dict[str, Any]:
        entry = self._enter_step(step_id, label_of(step_id, label), kind)
        with self._lock:
            self._stack.append(entry)
        return entry

    def pop(self, entry: dict[str, Any]) -> None:
        with self._lock:
            entry["end"] = self.elapsed()
            if entry in self._stack:
                self._stack.remove(entry)
            # A late-owner helper whose option is off returns at once: keep the log readable.
            if (entry["kind"] == "scoped" and entry["lines"] == 0 and not entry.get("failed")
                    and entry["end"] - entry["start"] < 0.05):
                if self.steps and self.steps[-1] is entry:
                    self.steps.pop()
                    if self.records and self.records[-1][6] == "step" and self.records[-1][2] == f"-- {entry['label']} --":
                        self.records.pop()
                        self._last_key = None

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            return self._stack[-1] if self._stack else self._sequential

    def finish(self, result: str) -> None:
        with self._lock:
            now = self.elapsed()
            for entry in self.steps:
                if entry["end"] is None:
                    entry["end"] = now
            self.result = result
            if self.ended is None:
                self.ended = now

    # -- progress
    def _add_record(self, now: float, text: str, done: Any, total: Any, *, kind: str = "line") -> None:
        if len(self.records) >= MAX_RECORDS:
            del self.records[KEEP_FIRST:KEEP_FIRST + 1000]
            self.dropped += 1000
            for entry in self.steps:
                entry["first_record"] = max(KEEP_FIRST, entry["first_record"] - 1000)
        self.records.append([now, now, text, done, total, 1, kind])

    def record(self, message: Any, done: Any = 0, total: Any = 0) -> None:
        text = str(message)
        key = _DIGITS.sub("#", text)
        now = self.elapsed()
        with self._lock:
            self.calls += 1
            last = self.records[-1] if self.records else None
            if (last is not None and last[6] == "line" and key == self._last_key
                    and now - last[0] < COLLAPSE_SECONDS):
                last[1], last[2], last[3], last[4] = now, text, done, total
                last[5] += 1
            else:
                self._add_record(now, text, done, total)
                self._last_key = key
            step = self.current()
            if step is not None:
                step["lines"] += 1

    def recording(self, sink: Callable[..., Any] | None) -> Callable[..., Any]:
        """A progress callable that records every line, then passes it on (cancellation passes through)."""
        tracker = self

        class _Recorder:
            _studio_tracker = tracker

            def __call__(self, message, done=0, total=0):
                tracker.record(message, done, total)
                if sink is not None:
                    return sink(message, done, total)
                return None

            @property
            def cancelled(self):
                return getattr(sink, "cancelled", None)

            @property
            def stage(self):
                return getattr(sink, "stage", None)

        return _Recorder()

    def lines(self, limit: int | None = None) -> list[str]:
        """The recorded progress as text lines ("[01:02:03] message", repeats noted)."""
        with self._lock:
            rows = list(self.records)
            dropped = self.dropped
        out = []
        for index, (first, last, text, done, total, repeats, kind) in enumerate(rows):
            if index == KEEP_FIRST and dropped:
                out.append(f"... {dropped} older progress lines were dropped here to keep the log small ...")
            stamp = _clock(first) if repeats == 1 else f"{_clock(first)}-{_clock(last)}"
            count = ""
            if kind == "line" and isinstance(total, int) and total > 0:
                count = f" [{done}/{total}]"
            more = f" (and {repeats - 1} more like it)" if repeats > 1 else ""
            out.append(f"[{stamp}] {text}{count}{more}")
        return out[-limit:] if limit else out

    def step_lines(self, entry: dict[str, Any] | None) -> list[str]:
        if entry is None:
            return []
        with self._lock:
            rows = self.records[entry["first_record"]:]
        return [row[2] for row in rows if row[6] == "line"]

    def last_line(self) -> str:
        with self._lock:
            for row in reversed(self.records):
                if row[6] == "line":
                    return row[2]
        return ""

    # -- facts and notes
    def fact(self, key: str, value: Any) -> None:
        with self._lock:
            self.facts[key] = value

    def note(self, text: str) -> None:
        with self._lock:
            if text not in self.notes:
                self.notes.append(text)


def active() -> Tracker | None:
    return _ACTIVE.get()


class track:
    """``with build_steps.track(progress) as session:`` around a build entry point; use ``session.progress`` inside.

    The outermost ``track`` owns a new Tracker (``session.tracker``; entry points nested inside reuse it and keep the
    progress they were given) and, when an exception leaves its block, raises the "During ..." wrapper ``from`` it.
    The owner's ``session.progress`` records every line and passes it on to ``progress``.
    """

    def __init__(self, progress: Callable[..., Any] | None = None, *, tracker: Tracker | None = None) -> None:
        self._progress = progress
        self._given = tracker
        self.owner = False
        self.tracker: Tracker | None = None
        self.progress: Callable[..., Any] | None = progress
        self._token = None

    def __enter__(self) -> "track":
        current = _ACTIVE.get()
        if current is not None:
            self.tracker = current
            self.progress = self._progress if self._progress is not None else current.progress
            return self
        tracker = self._given or Tracker()
        if getattr(self._progress, "_studio_tracker", None) is not tracker:
            tracker.progress = tracker.recording(self._progress)
        self.tracker, self.owner, self.progress = tracker, True, tracker.progress
        self._token = _ACTIVE.set(tracker)
        tracker.begin("preflight")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.owner:
            return False
        tracker = self.tracker
        try:
            _ACTIVE.reset(self._token)
        except ValueError:  # pragma: no cover - reset from another context
            _ACTIVE.set(None)
        if exc is None:
            tracker.finish("ok")
            return False
        if not isinstance(exc, Exception) or is_cancel(exc):
            tracker.finish("cancelled" if is_cancel(exc) else "stopped")
            return False
        wrapped = contextualize(exc, tracker)
        tracker.finish("failed")
        if wrapped is exc:
            return False
        raise wrapped from exc


def contextualize(exc: BaseException, tracker: Tracker | None) -> BaseException:
    """``exc`` with its step: a new StepFailure (or ``exc`` itself when it already has one)."""
    if isinstance(exc, StepFailure):
        failure = exc
    else:
        stamped = _chain_attr(exc, "_studio_step")
        current = tracker.current() if tracker is not None else None
        if stamped is not None:
            step_id, label = stamped
        elif current is not None:
            step_id, label = current["id"], current["label"]
        else:
            step_id, label = "build", label_of("build")
        resource = _chain_attr(exc, "_studio_resource")
        entry = None
        if tracker is not None:
            entry = next((s for s in reversed(tracker.steps) if s["id"] == step_id), None)
        step_lines = tracker.step_lines(entry) if tracker is not None else []
        last = step_lines[-1] if step_lines else (tracker.last_line() if tracker is not None else "")
        failure = wrap(exc, step_id, label, resource, last_progress=last,
                       undo=_chain_attr(exc, "_studio_undo") or "")
    if tracker is not None and tracker.failure is None:
        original = getattr(failure, "original", None) or exc
        # The wrapper is not raised yet, so the traceback is the original's own chain (the wrapper adds one line).
        tracker.failure = {
            "step": failure.step, "label": failure.label, "resource": failure.resource,
            "message": str(failure), "reason": plain_reason(original), "type": type(original).__name__,
            "last_progress": failure.last_progress, "undo": failure.undo,
            "traceback": failure_traceback(original),
        }
    return failure


def failure_traceback(exc: BaseException) -> str:
    """The full chained traceback text of an exception (after it has been raised)."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


# ------------------------------------------------------------------------------------------------------------------
# Markers used by mod_build
# ------------------------------------------------------------------------------------------------------------------

def begin(step_id: str, label: str | None = None) -> None:
    """Mark the start of the next step of the build (no-op outside a tracked build)."""
    tracker = _ACTIVE.get()
    if tracker is not None:
        tracker.begin(step_id, label)


def fact(key: str, value: Any) -> None:
    tracker = _ACTIVE.get()
    if tracker is not None:
        tracker.fact(key, value)


def scoped(step_id: str, label: str | None = None):
    """Decorator: while the function runs, the build is in this step; an error leaving it carries the step."""
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            tracker = _ACTIVE.get()
            entry = tracker.push(step_id, label) if tracker is not None else None
            try:
                return function(*args, **kwargs)
            except BaseException as exc:
                _stamp(exc, "_studio_step", (step_id, label_of(step_id, label)))
                if entry is not None:
                    entry["failed"] = True
                raise
            finally:
                if entry is not None:
                    tracker.pop(entry)
        return run
    return decorate


def name_failure(exc: BaseException, name: Any) -> None:
    """Give ``exc`` the resource ``name`` unless it already has one (what :class:`resource` does on the way out).

    For hot loops such as the shared pool runners: ``except BaseException as exc: name_failure(exc, task[0]); raise``
    reaches this module only when a task fails, so a traced run that succeeds executes nothing here
    (nfl2k5_late_steps.STEP_CODE lists the code a step runs)."""
    _stamp(exc, "_studio_resource", str(name))


class resource:
    """``with build_steps.resource("s13ad.iff"):`` names what a step is working on; an error leaving it carries it."""

    def __init__(self, name: Any) -> None:
        self.name = str(name)

    def __enter__(self) -> "resource":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            _stamp(exc, "_studio_resource", self.name)
        return False


# ------------------------------------------------------------------------------------------------------------------
# The write journal for optional steps
# ------------------------------------------------------------------------------------------------------------------

BLOCK = 16 * 1024
MEMORY_BUDGET = 64 * 1024 * 1024
#: The spill file's free-space check runs every SPILL_CHECK bytes; it stops (and the step is then not undoable) when
#: less than SPILL_FLOOR would be left on the output drive.
SPILL_CHECK = 64 * 1024 * 1024
SPILL_FLOOR = 512 * 1024 * 1024
_READ_CHUNK = 8 * 1024 * 1024
_HOOK_LOCK = threading.RLock()
_JOURNALS: list["_Journal"] = []
_ORIGINALS: dict[str, Callable[..., Any]] = {}
#: The real functions, taken when this module is first imported. The journaled wrappers always call these: code that
#: was imported while a step was journaled (multiprocessing.connection binds ``os.write`` at import) keeps a wrapper
#: after the wrappers are taken off ``os``, and that wrapper must still write.
_REAL_WRITE = os.write
_REAL_PWRITE = getattr(os, "pwrite", None)
_AUDIT_INSTALLED = False
_STDLIB_OPENERS = frozenset({"pathlib", "io", "_pyio", "codecs", "os", "tempfile", "contextlib", "shutil", "gzip",
                             "zipfile", "builtins"})


class _CannotUndo(Exception):
    """The step changed the copy in a way the journal cannot restore exactly."""


def _pread_all(fd: int, count: int, offset: int) -> bytes:
    from . import platform_compat
    chunks, done = [], 0
    while done < count:
        part = platform_compat.pread(fd, min(_READ_CHUNK, count - done), offset + done)
        if not part:
            break
        chunks.append(part)
        done += len(part)
    return b"".join(chunks)


class _Journal:
    """The original bytes of every block a step changes in one file, the file's size, and what it cannot see."""

    def __init__(self, target: Path, *, capture: bool = True) -> None:
        self.path = Path(target)
        self.real = os.path.normcase(os.path.realpath(self.path))
        self.basename = os.path.normcase(self.path.name)
        self.capture = capture
        self.owner = os.getpid()
        self.token = secrets.token_hex(6)
        self.lock = threading.RLock()
        self.blocks: dict[int, Any] = {}      # block index -> bytes, or (spill offset, length)
        self.memory = 0
        self.spill_path: Path | None = None
        self._spill = None
        self.unjournaled: list[str] = []      # reasons the copy cannot be restored exactly
        self.opened_for_write = False
        self.ref: int | None = None
        stat = self.path.stat()
        self.identity = (stat.st_dev, stat.st_ino)
        self.size0 = stat.st_size
        if capture:
            self.ref = os.open(self.path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0))

    # -- matching
    def matches_fd(self, fd: int) -> bool:
        try:
            stat = os.fstat(fd)
        except OSError:
            return False
        return (stat.st_dev, stat.st_ino) == self.identity

    def matches_path(self, path: Any) -> bool:
        try:
            text = os.fsdecode(os.fspath(path))
        except TypeError:
            return False
        if os.path.normcase(os.path.basename(text)) != self.basename:
            return False
        try:
            return os.path.normcase(os.path.realpath(text)) == self.real
        except OSError:  # pragma: no cover
            return True

    def flag(self, reason: str) -> None:
        with self.lock:
            if reason not in self.unjournaled:
                self.unjournaled.append(reason)

    def child_wrote(self) -> None:
        """A forked worker process wrote the copy: its journal is not this one, so the parent must not undo."""
        try:
            marker = self.path.parent / f".studio-undo-{self.token}-child-{os.getpid()}"
            with open(marker, "wb"):
                pass
        except OSError:  # pragma: no cover
            pass

    # -- capture
    def _store(self, index: int, data: bytes) -> None:
        if self.memory + len(data) <= MEMORY_BUDGET:
            self.blocks[index] = data
            self.memory += len(data)
            return
        if self._spill is None:
            self.spill_path = self.path.parent / f".studio-undo-{self.token}.bin"
            self._spill = open(self.spill_path, "w+b")
        self._spill.seek(0, os.SEEK_END)
        at = self._spill.tell()
        if at // SPILL_CHECK != (at + len(data)) // SPILL_CHECK or at == 0:
            # The undo copy shares the output drive with the build's own working room: never let it take that room.
            import shutil
            if shutil.disk_usage(self.path.parent).free < SPILL_FLOOR + len(data):
                raise OSError("no room on the output drive to keep the undo copy")
        self._spill.write(data)
        self.blocks[index] = (at, len(data))

    def _saved(self, index: int) -> bytes:
        value = self.blocks[index]
        if isinstance(value, tuple):
            at, length = value
            self._spill.flush()
            self._spill.seek(at)
            return self._spill.read(length)
        return value

    def before_write(self, offset: int, data: Any) -> None:
        if not self.capture:
            self.flag("the journal is off")
            return
        if self.unjournaled:
            return                      # already not undoable: saving more would only cost memory
        view = memoryview(data).cast("B")
        count = view.nbytes
        if count == 0 or offset >= self.size0:
            return
        end = min(offset + count, self.size0)
        first, last = offset // BLOCK, (end - 1) // BLOCK
        wanted = [index for index in range(first, last + 1) if index not in self.blocks]
        if not wanted:
            return
        start = wanted[0] * BLOCK
        stop = min((wanted[-1] + 1) * BLOCK, self.size0)
        current = _pread_all(self.ref, stop - start, start)
        if len(current) != stop - start:
            self.flag("a block of the copy could not be read before it was written")
            return
        for index in wanted:
            bstart, bend = index * BLOCK, min((index + 1) * BLOCK, self.size0)
            lo, hi = max(bstart, offset), min(bend, offset + count)
            if current[lo - start:hi - start] != view[lo - offset:hi - offset]:
                self._store(index, current[bstart - start:bend - start])

    def before_truncate(self, length: int) -> None:
        if not self.capture:
            self.flag("the journal is off")
            return
        if self.unjournaled:
            return
        if length >= self.size0:
            return
        try:
            size_now = os.fstat(self.ref).st_size
        except OSError:  # pragma: no cover
            size_now = self.size0
        upto = min(size_now, self.size0)
        for index in range(length // BLOCK, (upto + BLOCK - 1) // BLOCK):
            if index in self.blocks:
                continue
            bstart, bend = index * BLOCK, min((index + 1) * BLOCK, self.size0)
            data = _pread_all(self.ref, bend - bstart, bstart)
            if len(data) != bend - bstart:
                self.flag("the copy was shortened past bytes the journal could not read")
                return
            self._store(index, data)

    # -- undo
    def children(self) -> list[Path]:
        try:
            return sorted(self.path.parent.glob(f".studio-undo-{self.token}-child-*"))
        except OSError:  # pragma: no cover
            return []

    def restore(self) -> dict[str, Any]:
        """Put every saved block back, restore the size, read it all back. Raises _CannotUndo."""
        children = self.children()
        if children:
            self.flag("a worker process wrote the copy (" + ", ".join(p.name.rsplit("-", 1)[-1] for p in children) + ")")
        if self.unjournaled:
            raise _CannotUndo("; ".join(self.unjournaled))
        if not self.blocks and self.path.stat().st_size == self.size0 and not self.opened_for_write:
            return {"blocks": 0, "bytes": 0, "size": self.size0, "changed": False}
        from . import platform_compat
        fd = os.open(self.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            if size < self.size0:
                missing = [i for i in range(size // BLOCK, (self.size0 + BLOCK - 1) // BLOCK) if i not in self.blocks]
                if missing:
                    raise _CannotUndo("the copy was shortened outside the journal")
            if size != self.size0:
                os.ftruncate(fd, self.size0)
            restored = 0
            for index in sorted(self.blocks):
                data = self._saved(index)
                at, view = index * BLOCK, memoryview(data)
                while view:
                    written = platform_compat.pwrite(fd, view, at)
                    if written <= 0:
                        raise _CannotUndo("a short write while restoring the copy")
                    view, at = view[written:], at + written
                restored += len(data)
            os.fsync(fd)
            for index in sorted(self.blocks):
                data = self._saved(index)
                if _pread_all(fd, len(data), index * BLOCK) != data:
                    raise _CannotUndo(f"block {index} did not read back after the restore")
            if os.fstat(fd).st_size != self.size0:
                raise _CannotUndo("the copy's size did not come back")
        except OSError as exc:
            raise _CannotUndo(f"the copy could not be restored: {exc}") from exc
        finally:
            os.close(fd)
        return {"blocks": len(self.blocks), "bytes": restored, "size": self.size0, "changed": True}

    def close(self) -> None:
        if self.ref is not None:
            try:
                os.close(self.ref)
            except OSError:  # pragma: no cover
                pass
            self.ref = None
        if self._spill is not None:
            try:
                self._spill.close()
            except OSError:  # pragma: no cover
                pass
            self._spill = None
        for path in [self.spill_path, *self.children()]:
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    pass
        self.blocks.clear()


def _journals_for_fd(fd: int) -> list[_Journal]:
    return [journal for journal in list(_JOURNALS) if journal.matches_fd(fd)]


def _capture(fd: int, offset: int | None, data: Any) -> None:
    try:
        for journal in _journals_for_fd(fd):
            if os.getpid() != journal.owner:
                journal.child_wrote()
                continue
            with journal.lock:
                journal.opened_for_write = True
                at = os.lseek(fd, 0, os.SEEK_CUR) if offset is None else offset
                try:
                    journal.before_write(at, data)
                except Exception as exc:  # noqa: BLE001 - the journal never breaks a write; it gives up instead
                    journal.flag(f"the journal could not save a block ({type(exc).__name__}: {exc})")
    except Exception:  # noqa: BLE001  # pragma: no cover
        pass


def _hooked_pwrite(fd, data, offset):
    if _JOURNALS:
        _capture(fd, offset, data)
    return _REAL_PWRITE(fd, data, offset)


def _hooked_write(fd, data):
    if _JOURNALS:
        _capture(fd, None, data)
    return _REAL_WRITE(fd, data)


def _flag_vector_write(name):
    original = _ORIGINALS[name]

    def hooked(fd, *args, **kwargs):
        if _JOURNALS:
            try:
                for journal in _journals_for_fd(fd):
                    journal.flag(f"os.{name} wrote the copy")
            except Exception:  # noqa: BLE001  # pragma: no cover
                pass
        return original(fd, *args, **kwargs)
    return hooked


def _flag_copy(name):
    original = _ORIGINALS[name]

    def hooked(*args, **kwargs):
        if _JOURNALS and args:
            try:
                out = args[1] if name == "copy_file_range" else args[0]
                for journal in _journals_for_fd(out):
                    journal.flag(f"os.{name} wrote the copy")
            except Exception:  # noqa: BLE001  # pragma: no cover
                pass
        return original(*args, **kwargs)
    return hooked


def _opener() -> tuple[str, str]:
    """(module, function) of the first frame outside the standard library that opened a file."""
    frame = sys._getframe(2)
    for _ in range(10):
        if frame is None:
            break
        module = str(frame.f_globals.get("__name__", ""))
        if module.split(".")[0] not in _STDLIB_OPENERS and module != __name__:
            return module.rsplit(".", 1)[-1], frame.f_code.co_name
        frame = frame.f_back
    return "", ""


def _audit(event: str, args: tuple) -> None:
    """Sees what the journal cannot: buffered or mapped writers, truncation, renames and removals of the copy."""
    if not _JOURNALS:
        return
    try:
        if event == "open":
            path, mode, flags = args
            if isinstance(path, int):
                journals = [j for j in list(_JOURNALS) if j.matches_fd(path)]
            else:
                journals = [j for j in list(_JOURNALS) if j.matches_path(path)]
            if not journals:
                return
            flags = flags if isinstance(flags, int) else 0
            writes = bool(flags & (os.O_WRONLY | os.O_RDWR)) or (isinstance(mode, str) and any(c in mode for c in "wax+"))
            if not writes:
                return
            for journal in journals:
                if os.getpid() != journal.owner:
                    journal.child_wrote()
                    continue
                journal.opened_for_write = True
                if flags & getattr(os, "O_TRUNC", 0) or (isinstance(mode, str) and "w" in mode):
                    journal.flag("the copy was reopened empty (truncated on open)")
                elif isinstance(mode, str):
                    where = _opener()
                    if where not in DESCRIPTOR_ONLY_WRITERS:
                        journal.flag("a buffered writer opened the copy ({}.{})".format(*where) if where[0]
                                     else "a buffered writer opened the copy")
        elif event == "os.truncate":
            target, length = args
            journals = [j for j in list(_JOURNALS)
                        if (j.matches_fd(target) if isinstance(target, int) else j.matches_path(target))]
            for journal in journals:
                if os.getpid() != journal.owner:
                    journal.child_wrote()
                    continue
                with journal.lock:
                    journal.opened_for_write = True
                    try:
                        journal.before_truncate(int(length))
                    except Exception as exc:  # noqa: BLE001
                        journal.flag(f"the journal could not save the shortened part ({exc})")
        elif event == "mmap.__new__":
            fileno, _length, access, _offset = args
            if isinstance(fileno, int) and fileno >= 0:
                import mmap
                if access in (getattr(mmap, "ACCESS_READ", 1),):
                    return
                for journal in [j for j in list(_JOURNALS) if j.matches_fd(fileno)]:
                    journal.flag("the copy was memory-mapped for writing")
        elif event == "os.rename":
            source, destination = args[0], args[1]
            for journal in list(_JOURNALS):
                if journal.matches_path(destination) or journal.matches_path(source):
                    journal.flag("the copy was replaced or renamed")
        elif event == "os.remove":
            for journal in list(_JOURNALS):
                if journal.matches_path(args[0]):
                    journal.flag("the copy was removed")
    except Exception:  # noqa: BLE001 - an audit hook must never raise (it would block the operation)
        pass


def _install_hooks() -> None:
    global _AUDIT_INSTALLED
    with _HOOK_LOCK:
        if not _AUDIT_INSTALLED:
            sys.addaudithook(_audit)
            _AUDIT_INSTALLED = True
        if _ORIGINALS:
            return
        if _REAL_PWRITE is not None:
            _ORIGINALS["pwrite"] = os.pwrite
            os.pwrite = _hooked_pwrite
        _ORIGINALS["write"] = os.write
        os.write = _hooked_write
        for name in ("writev", "pwritev"):
            if hasattr(os, name):
                _ORIGINALS[name] = getattr(os, name)
                setattr(os, name, _flag_vector_write(name))
        for name in ("sendfile", "copy_file_range"):
            if hasattr(os, name):
                _ORIGINALS[name] = getattr(os, name)
                setattr(os, name, _flag_copy(name))


def _uninstall_hooks() -> None:
    with _HOOK_LOCK:
        if _JOURNALS or not _ORIGINALS:
            return
        for name, original in _ORIGINALS.items():
            setattr(os, name, original)
        _ORIGINALS.clear()


def _activate(journal: _Journal) -> None:
    with _HOOK_LOCK:
        _install_hooks()
        _JOURNALS.append(journal)


def _deactivate(journal: _Journal) -> None:
    with _HOOK_LOCK:
        if journal in _JOURNALS:
            _JOURNALS.remove(journal)
        _uninstall_hooks()


def hooks_installed() -> bool:
    """For tests: True while the os write functions are journaled."""
    return bool(_ORIGINALS)


# ------------------------------------------------------------------------------------------------------------------
# Optional steps
# ------------------------------------------------------------------------------------------------------------------

def strict() -> bool:
    return os.environ.get(STRICT_ENV, "").strip() == "1"


def left_out(receipt: dict, step_id: str) -> bool:
    return any(row.get("step") == step_id for row in receipt.get("left_out", ()) or ())


class _Prerequisite(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


def _sidecars(target: Path) -> dict[str, bytes | None]:
    """The receipts a step keeps beside the copy (``<copy name>.<something>``): name -> bytes."""
    found: dict[str, bytes | None] = {}
    prefix = target.name + "."
    try:
        entries = list(os.scandir(target.parent))
    except OSError:
        return found
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        try:
            if entry.is_file(follow_symlinks=False) and entry.stat().st_size <= 64 * 1024 * 1024:
                found[entry.name] = Path(entry.path).read_bytes()
            else:
                found[entry.name] = None
        except OSError:
            found[entry.name] = None
    return found


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


class optional:
    """``with build_steps.optional(receipt, target, progress, "modern_surfaces"):`` around one optional step.

    On success nothing changes. When the step raises an ``Exception`` (not a cancel): the copy, its sidecar receipts and
    ``receipt`` are restored exactly, the step is recorded in ``receipt["left_out"]`` and as a step row with one plain
    ``user_notes`` line, the note goes to ``progress``, and the block's exception is swallowed so the build goes on.
    When the copy cannot be restored exactly, or ``NFL2K5_BUILD_STRICT=1``, the exception goes on (with the step).
    ``self.require("modern_metlife")`` as the block's first line leaves this step out (with its own note) when a step it
    builds on was left out earlier in this build.
    """

    def __init__(self, receipt: dict, target: Any, progress: Callable[..., Any] | None, step_id: str,
                 label: str | None = None, *, kept: str | None = None) -> None:
        self.receipt = receipt
        self.target = Path(target) if target is not None else None
        self.progress = progress or (lambda *_args: None)
        self.step_id = step_id
        self.label = label_of(step_id, label)
        self.kept = kept or KEPT.get(step_id, DEFAULT_KEPT)
        self.journal: _Journal | None = None
        self.journal_problem = ""
        self.entry = None
        self.outcome: str = "running"

    # -- prerequisites
    def require(self, *step_ids: str) -> None:
        missing = [label_of(s) for s in step_ids if left_out(self.receipt, s)]
        if missing:
            raise _Prerequisite(missing)

    def __enter__(self) -> "optional":
        tracker = _ACTIVE.get()
        self.entry = tracker.push(self.step_id, self.label, kind="optional") if tracker is not None else None
        self._receipt_before = {key: _copy(value) for key, value in self.receipt.items()}
        self._result_before = dict(self.receipt.get("result") or {}) if isinstance(self.receipt.get("result"), dict) else None
        self._sidecars_before = {}
        if self.target is not None and not strict():
            try:
                if self.target.is_file():
                    capture = os.environ.get(JOURNAL_ENV, "").strip() != "0"
                    self.journal = _Journal(self.target, capture=capture)
                    self._sidecars_before = _sidecars(self.target)
                    _activate(self.journal)
            except OSError as exc:
                self.journal_problem = f"the copy could not be watched ({exc})"
                self.journal = None
        return self

    def _finish_entry(self) -> None:
        tracker = _ACTIVE.get()
        if tracker is not None and self.entry is not None:
            self.entry["outcome"] = self.outcome
            tracker.pop(self.entry)

    def __exit__(self, exc_type, exc, tb) -> bool:
        journal = self.journal
        if journal is not None:
            _deactivate(journal)
        try:
            if exc is None:
                self.outcome = "ok"
                return False
            if isinstance(exc, _Prerequisite):
                self._left_out(f"it builds on {', '.join(exc.missing)}, which {'was' if len(exc.missing) == 1 else 'were'} "
                               "left out", None, restored=None)
                return True
            if not isinstance(exc, Exception) or is_cancel(exc):
                self.outcome = "cancelled" if is_cancel(exc) else "stopped"
                _stamp(exc, "_studio_step", (self.step_id, self.label))
                return False
            _stamp(exc, "_studio_step", (self.step_id, self.label))
            if strict():
                self.outcome = "failed"
                _stamp(exc, "_studio_undo", f"{STRICT_ENV}=1: optional steps stop the build")
                return False
            try:
                restored = self._undo()
            except _CannotUndo as why:
                self.outcome = "failed"
                _stamp(exc, "_studio_undo", f"it could not be left out safely: {why}")
                return False
            reason = stage_words(exc, self.target) or plain_reason(exc)
            where = getattr(exc, "_studio_resource", None)
            if where and where not in reason:
                reason = f"{where}: {reason}"
            self._left_out(reason, exc, restored=restored)
            return True
        finally:
            if journal is not None:
                journal.close()
            self._finish_entry()

    def _undo(self) -> dict[str, Any]:
        if self.journal is None:
            if self.target is None or not self.target.exists():
                return {"changed": False}
            raise _CannotUndo(self.journal_problem or "the step was not watched")
        restored = self.journal.restore()
        after = _sidecars(self.target)
        for name, data in after.items():
            if name not in self._sidecars_before:
                try:
                    (self.target.parent / name).unlink()
                except OSError as exc:
                    raise _CannotUndo(f"a new receipt beside the copy could not be removed ({exc})") from exc
        for name, data in self._sidecars_before.items():
            if data is None:
                if after.get(name, b"") is not None or name not in after:
                    raise _CannotUndo(f"a receipt beside the copy ({name}) is too large to restore")
                continue
            if after.get(name) != data:
                try:
                    (self.target.parent / name).write_bytes(data)
                except OSError as exc:
                    raise _CannotUndo(f"a receipt beside the copy could not be restored ({exc})") from exc
        if _sidecars(self.target) != self._sidecars_before:
            raise _CannotUndo("the receipts beside the copy did not come back")
        return restored

    def _left_out(self, reason: str, exc: BaseException | None, *, restored: dict | None) -> None:
        self.outcome = "left_out"
        receipt = self.receipt
        result_now = receipt.get("result")
        for key in list(receipt):
            if key not in self._receipt_before:
                del receipt[key]
        for key, value in self._receipt_before.items():
            if key == "result" and isinstance(result_now, dict) and self._result_before is not None:
                result_now.clear()
                result_now.update(self._result_before)
                receipt["result"] = result_now
            elif key in ("steps", "user_notes") and isinstance(receipt.get(key), list) and isinstance(value, list):
                receipt[key][:] = value
            else:
                receipt[key] = _copy(value)
        note = f"{self.label[0].upper()}{self.label[1:]} was left out: {reason}. {self.kept}"
        row = {"step": self.step_id, "label": self.label, "status": "left_out", "reason": reason,
               "user_notes": [note]}
        if exc is not None:
            row["error"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        if restored is not None:
            row["restored"] = restored
        receipt.setdefault("left_out", []).append(row)
        receipt.setdefault("steps", []).append(row)
        receipt.setdefault("user_notes", []).append(note)
        tracker = _ACTIVE.get()
        if tracker is not None:
            tracker.left_out.append({**row, "traceback": failure_traceback(exc) if exc is not None else ""})
            tracker.note(note)
        try:
            self.progress(note, 0, 0)
        except Exception as progress_exc:  # noqa: BLE001
            if is_cancel(progress_exc):
                raise


def left_out_rows(receipt: dict) -> list[dict]:
    return list(receipt.get("left_out", ()) or ())


__all__ = ["STEP_LABELS", "KEPT", "StepFailure", "Tracker", "track", "active", "begin", "fact", "scoped", "resource",
           "optional", "left_out", "left_out_rows", "wrap", "contextualize", "plain_reason", "is_cancel", "strict",
           "label_of", "failure_traceback", "DESCRIPTOR_ONLY_WRITERS"]
