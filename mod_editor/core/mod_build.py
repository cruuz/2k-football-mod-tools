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
import struct

from mod_editor.core import platform_compat
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from . import nfl2k5_throw_tuning as tt
from . import nfl2k5_official_marks as official

ProgressSink = Callable[[str, int, int], None]
ROOT = Path(__file__).resolve().parents[2]
PACK0_SIZE = 193_710_080   # vc_53450030/0 (retail); the schedule template lives in its ROST resource


def softdrink_book_paths(teams: Iterable[str]) -> list[Path]:
    """Bundled modern pairs in retail team order, offenses before defenses.

    Keys are the game's abbreviations (ARZ, OAK, SD, STL). Duplicates
    are ignored; unknown keys are refused rather than silently omitted.
    """
    from .nfl2k5_playbook_pack import TEAM_BOOKS

    selected = set()
    for team in teams:
        if not isinstance(team, str) or team not in TEAM_BOOKS:
            raise ValueError(f"Unknown SOFTDRINK team key: {team!r}")
        selected.add(team)
    ordered = [team for team in TEAM_BOOKS if team in selected]
    folder = ROOT / "data" / "playbooks"
    return [folder / f"softdrink_{'giants' if team == 'NYG' else team.lower()}_modern.2k5book"
            for team in ordered] + [folder / f"softdrink_{team.lower()}_defense.2k5book"
                                    for team in ordered]


def plan_playbook_packs(
    paths: Iterable[Path | str],
) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    """Partition packs and refuse offensive overlaps before any build writes.

    Returns complete offenses, options, defenses, then community offenses.
    """
    # Defense v2 recipes require native personnel fingerprints before the pool recode.
    # Keep offense recipes in their original later position relative to other PLAY writers.
    defense_packs: list[Path] = []
    option_packs: list[Path] = []
    offense_packs: list[Path] = []
    complete_offense_packs: list[Path] = []
    if paths:
        packs = _core_module("nfl2k5_playbook_pack")
        if packs is None:
            raise RuntimeError("the playbook pack module is not available in this build")
        for path in dict.fromkeys(Path(p) for p in paths):
            pack = packs.load_pack(path)
            (complete_offense_packs if pack.schema == packs.OFFENSE_SCHEMA else
             option_packs if any(p.option_intent for p in pack.plays) else
             defense_packs if pack.schema == packs.DEFENSE_SCHEMA else offense_packs).append(path)

    for complete_path in complete_offense_packs:
        complete = packs.load_pack(complete_path)
        for other_path in (*complete_offense_packs, *option_packs, *offense_packs):
            if other_path == complete_path:
                continue
            other = packs.load_pack(other_path)
            overlap = set(complete.book.resolved_targets()) & set(other.book.resolved_targets())
            if overlap:
                raise ValueError("A complete offense owns every ordinary offensive play for "
                                 + ", ".join(sorted(overlap))
                                 + "; select one offensive pack for each of those teams")

    if option_packs and (offense_packs or complete_offense_packs):
        for option_path in option_packs:
            option = packs.load_pack(option_path)
            protected_plays = {p.replace_index for p in option.plays}
            protected_formations = {p.link_formation for p in option.plays}
            for other_path in (*complete_offense_packs, *offense_packs):
                other = packs.load_pack(other_path)
                if option.book.team == other.book.team and (
                        protected_plays & {p.replace_index for p in other.plays}
                        or protected_formations & {f.replace_index for f in other.formations}):
                    raise ValueError("Option and Modern Gun Core replacements overlap in " + option.book.team +
                                     "; select one stock seed or author a reviewed combined pack")

    return complete_offense_packs, option_packs, defense_packs, offense_packs


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
    arc_by_distance: bool = False   # retail through 40 yd, realistic deep flight with extra touch
    catch_slider: bool = False
    accel_ramp: bool = False
    draft_ai: bool = False
    returner_fix: bool = False
    progression: bool = False
    franchise_economy: bool = False  # DESIGN: requires the matching 1:4 contract fragment
    scheme_labels: bool = False   # depth-chart slot labels by scheme: 4-3 SAM/MIKE/WILL, 3-4 EDGE/MIKE/WILL/NT
    camera: bool = False          # Standard default, Far and Broadcast session choices; experimental
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
    momentum: int = 0  # experimental and unwitnessed; 0 is Retail
    momentum_contact: bool = False
    momentum_collisions: bool = False
    momentum_collision_level: int = 0
    read_option_runtime: bool = False
    franchise_2026_rules: bool = False
    senior_bowl: bool = False
    senior_bowl_settings: dict[str, object] = field(default_factory=lambda: {
        "scheme": "retail", "away": {"bank": 50, "side": "A", "era": 0},
        "home": {"bank": 51, "side": "H", "era": 0}})
    senior_bowl_seed: int = 1
    guardian_overlay: bool = False
    guardian_everyone_practice: bool = True
    guardian_players: list[dict] | None = None
    my_career: bool = False
    my_career_setup: str | None = None
    franchise_autosave: bool = False
    trim_intro_videos: bool = False  # output-only boot movie cut; off in every preset
    # b76-i1: path of a Sofdec movie made by tools/nfl2k5_intro_encode.py that replaces the boot
    # intro (outer 4296); "" = off.  Output-only, in no preset, EXPERIMENTAL / UNWITNESSED.
    custom_intro: str = ""
    crib_reclaim: bool = False
    screen_hooks: bool = False
    coverage_trail: bool = False
    weekly_prep: bool = False             # Weekly Preparation: safeties in DB drills; owner for the two suboptions; experimental, off in every preset
    weekly_prep_cpu: bool = False         # CPU teams run weekly prep before their games (needs weekly_prep)
    weekly_prep_remember: bool = False    # keep and reapply the human plan (needs weekly_prep)
    deep_zone_facing: bool = False        # deep-zone corners keep facing the QB on a slower drop; experimental, off in every preset
    deep_zone_bail: bool = False          # three-deep press start with a directional bail (ends at seven yards alone); experimental, off in every preset
    deep_zone_bail_calls: tuple = ()      # staged press-bail authoring calls (asset selector + formation/front/coverage indices); staging is not wired yet, must stay empty
    coach_ai: bool = False  # bare plans stay neutral; the SOFTDRINK release preset enables this
    playbook_pair: bool = False           # separate offensive and defensive playbooks (pregame Options rows); composes with read option / QB spy since beta 66 (paired-root contract); experimental, off in every preset
    cpu_money_downs: str = "retail"      # CPU fourth downs, two-point tries and overtime: retail / modern / aggressive / modern2; experimental; Basic is retail, Advanced and Experimental use modern2 (b77 p9)
    coin_defer: bool = False
    decided_clock: bool = False
    decided_clock_margin: int = 17
    decided_clock_seconds: int = 60
    cpu_scrambles: str = "retail"
    historic_teams_quick_game: bool = False  # b76-h1: Quick Game Team Select steps on into the 75 historic teams; experimental
    classic_teams: bool = False  # b775-ct1: with historic teams in Quick Game, the list runs on into every Anniversary team-season and 25 classic teams; experimental
    kickoff_return_blocking: bool = False  # b76-vb3 E1: return blockers claim distinct men after the catch (Noah's feel test)
    espn25_era_rules: bool = False  # e2: season-specific live rules for each moment
    historic_stock_books: bool = False  # e2: isolated retail bank and per-side resolver
    espn25_named_previews: bool = False  # named previews, period field aliases and historic venue profile
    # b773-sb2: optional folder of the user's own Super Bowl logos (super_bowl/<NUMERALS>.png, brands/<name>.png,
    # teams/<CODE>.png) placed in the Super Bowl walls' slots; "" keeps the authored marks. Never in a preset.
    super_bowl_user_art: str = ""
    espn25_more_moments: bool = False  # Anniversary collection with its own team-seasons; experimental, needs an image
    # b76-k1: 128 MB memory on stock xemu (K128, R1's late form: a 226-byte startup patch that teaches xemu's
    # Xbox kernel to manage 128 MB after the game built its arena; asleep at 64 MB and on any other kernel; needs
    # xemu System memory 128 MB) and, with it, the roster block in the game's >64 MB extra heap. Experimental.
    k128_memory: bool = False
    k128_roster_heap: bool = False
    k128_early: bool = False              # b76-k1: the early form (pages at the entry: the graphics memory grows by 14.9 MB)
    # b77-f4: letter grades in Franchise (Noah's 2K scale: 95+ A+ ... 0-49 F-) for the player overall and the team
    # offense / defense / overall; display only, lists still sort on the number, attributes stay numbers.
    # An allocator owner (late, after K128). Off in Basic (2004 numbers), on in Modern and Experimental.
    letter_grades: bool = False
    # Modern displayed unit ratings; native simulation and AI formulas stay intact.
    team_ratings: bool = False
    # b77-f5: Player Card honors page: the bumpers (Black/White) and triggers flip a Franchise Player Card to the award
    # history (MVP, OPOY, DPOY, ROY, Super Bowls, SB MVP, Pro Bowls, All-Pro, rushing titles, with years); the game adds
    # each season's winners itself. An allocator owner (late, after the letter grades). Off in Basic.
    honors_page: bool = False
    # ui1 (Noah 10/17 test menu): with MyCareer, its Apartment becomes Career Home (five sections and Quit, a live
    # MyPlayer panel in club colours; the old Apartment stays as "Classic Apartment"). On by default for the test disc;
    # off keeps the Apartment exactly as before. It takes the extra section slot, so not with a jukebox music library.
    my_career_home: bool = True
    # b77-f5: real award history for the players on the roster: "" = none, "builtin" = data/nfl2k5_honors_2026.json
    # (the 2026 rosters; every honor cited), or a path to an edited honors JSON or CSV. Disc images only; written into the
    # career-stat history after the career and TEAM history.
    honors_history: str = ""
    accelerated_clock: bool = False      # Madden-style accelerated clock; ADVANCED classification, off in every preset until witnessed
    accelerated_clock_minimum_seconds: int = 20   # minimum play clock after the huddle break: 25 / 20 / 15 / 10 / 5
    franchise_edit_player: bool = False   # Edit Player on Franchise Player Contracts (needs Position row + allocator); experimental, off in every preset
    reserves_16: bool = False
    created_teams_extra: int = 0
    defensive_try: bool = False
    zone_drop_cap: bool = False
    all_stadiums: bool = False
    music_shuffle: bool = False  # shared playlist shuffle (experimental, unwitnessed); the Music page's choices ride along
    music_shuffle_selection: dict | None = None  # MusicPanel.playlist_options() document, schema 1, or None = 66 core songs
    practice_squad_screen: bool = False  # native Coach's Desk Practice Squad screen (experimental, unwitnessed)
    abilities: bool = False  # player abilities rules v1 (experimental, unwitnessed)
    abilities_off_week: int | None = None  # zero-based regular-season row 0..17 with abilities off, or None
    abilities_lock_right_stick: bool = False   # opt-in restriction; base moves stay available by default
    abilities_lock_special_moves: bool = False # opt-in restriction; abilities normally add bonuses only
    abilities_lock_speedster: bool = True      # rules v2: Speed above 99 needs Speedster
    abilities_right_stick_stars_only: bool = False   # b77-g2: right-stick moves (the stick flicks and the click hurdle) only for players with the roster star tag; CPU carriers follow the same rule
    abilities_charge_stars_only: bool = False   # b77-g2: the charge-up meter of live ball carriers needs the star's charge-up access (non-carriers keep retail charge)
    abilities_star_access: tuple[str, ...] = ("flicks_charge", "stick_charge", "full", "full")  # b77-g2: access level of a starred player with no ability tier / Star / Superstar / X-Factor tier
    abilities_button_moves_stars_only: bool = False  # b77-g2: spin, truck, stiff-arm and button jukes only for starred players (a separate switch, off everywhere)
    qb_spy: bool = False  # zone, man and rush QB spy runtime (experimental, unwitnessed)
    calendar_engine: bool = False  # the complete 128-season calendar (implementation half of the 128-season option)
    coverage_slider: bool = False
    scramble_tuning: bool = False
    flatter_deep_ball: bool = False
    chop_block_toggle: bool = False
    dynamic_kickoff: bool = False
    dynamic_kickoff_settings: dict[str, object] = field(default_factory=lambda: {
        "touchback_yard": 35, "cpu_landing_probability": 90, "cpu_target_yards": (5, 15), "cpu_touchback_probability": 90})
    # one EDGE / one LB / one interior pool across 4-3 and 3-4 (XBE pools + playbook recode + ROST
    # reclassification; needs a disc image; implies scheme_labels)
    position_pools: bool = False
    # compatibility: keep the empty Outside Linebackers filter row for existing or custom saves
    position_pools_keep_olb: bool = False
    # Thirteen SPECIAL rows, with eleven on offense/defense and unit * 11 + slot indexing.
    # Experimental/unwitnessed; needs one-pool positions and X / Z / SLWR playbook roles.
    depth_chart_rows: bool = False
    # 2026 season: real 2026 schedule template in pack 0 (17 games, 18 weeks, one bye; the real 3-game
    # preseason after it) + year/calendar/season-length/14-team-playoffs/preseason executable patches
    # (draft/CAP birth years, CAP limits and the DOB line follow the year); needs a disc image
    season_cap: bool = False  # combined 128-season franchise option; experimental/unwitnessed
    season_2026: bool = False
    team_names_2026: bool = False
    modern_naming: bool = False
    # hor+ 16:9: the 3D view widens, HUD/menus/scorebug stay 4:3-proportioned; needs xemu [display.ui]
    # aspect_ratio = '16x9'. Experimental preset only; unwitnessed in game.
    widescreen: bool = False
    overtime: bool = False        # 2025+ NFL overtime: both teams possess, 10-min regular season w/ ties, playoffs to a winner
    # TEAM column on the franchise Player Card's season-by-season stats (which team each season was played for;
    # a UI fix, no gameplay change; past seasons of an older franchise save read "--" until their next rollover)
    team_column: bool = False
    # 7-on-7 practice: a fifth Practice Type (Practice -> Scrimmage -> Practice Type -> 7-On-7) that plays as
    # Full Scrimmage with the practice book loaded for both teams, plus the 7-on-7 sets/plays written into
    # PRACTICE-pb.iff (linemen parked at the sideline, a 4-second timer rusher); needs a disc image; unwitnessed
    seven_on_seven: bool = False  # held until repaired; old opt-ins are ignored while the release gate is off
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
    # the game's own Edit Player cycles all sixteen elbow pads, not the first ten (four .text spans,
    # eight bytes: the two cycle caps and the two backward wraps). Unwitnessed in game.
    elbow_options: bool = False
    # the1wam's lineman rating adjustment: while the game computes a C/G/T overall, 326 lb and up
    # counts as 294 lb and 325 lb and down as 317 lb (one retargeted call plus a 47-byte cave).
    # The stored weight and every gameplay reader of it are untouched. Unwitnessed in game.
    the1wam_lineman_rating: bool = False
    # b76-z2 xemu display-list stability fix: the frame display list's release callback (a NOP 7
    # software method) is raised from the D3D ring right after the list returns, not from the end
    # of the list, so xemu's pusher never waits inside a buffer the game is already rewriting
    # (the pregame-intro "Reserved pb command" abort, retail included). Same GPU methods in the
    # same order; two pinned .text spans, 94 changed bytes with the section digest, no growth.
    xemu_display_list_fix: bool = False
    resource_load_guard: bool = False
    loader_wakeup_fix: bool = False
    # b777-rb2: Halfback/HB display text reads Running Back/RB (in-place UTF-16 strings, no codes or caves).
    rb_rename: bool = False
    # b778-pg2: "The Crib" reads "Trophy Room" (in-place UTF-16 strings, no codes or caves).
    trophy_room: bool = False
    # b77-k1: First/Last Name keyboards also accept space, period, apostrophe and hyphen (data only, no code).
    name_keyboard: bool = False
    # penalties at NFL rates + a working Chop Block toggle: "" = off, "nfl" = the ESTIMATED first-cut profile
    # (seven .rdata slider->factor curve tables re-knotted in place, incidental face mask 5 -> 15 yd, the dead
    # Chop Block toggle wired through a 10-byte stub); room for a user .json profile path later; unwitnessed
    penalties: str = ""
    # home/away jerseys at any stadium: "rule" = home always dark, visitor always white (no Cowboys exception);
    # "choice" = the retail default plus a per-side colour flip on the same up/down that picks the era on
    # Controller Assign / Team Select (past the last era: flip and restart); "" = retail. Unwitnessed.
    uniform_choice: str = ""
    # b778-sl1 (Noah 10/22: "Team colored sleeves would be sick"): the black undershirt sleeve
    # style is rebound to each side's own uniform package and recoloured per kit. Data-only XBE
    # table flip plus package palettes; needs a disc image; on in every SOFTDRINK preset.
    team_sleeves: bool = False
    helmet_finish: str = "glossy"  # ADVANCED (beta 66, maumau78): "matte" zeroes both helmet LODs' shell reflection weight; off in every preset
    # laces to the posts on FG/PAT holds: one 6-byte hook on the held-ball join point + a 143-byte cave in a
    # dead routine that rolls the ball 180 degrees about its long axis on live Field Goal formation plays
    # (the game's own quaternion product; kickoff tee, punts and carries untouched). Opt-in until witnessed.
    kick_laces: bool = False
    punter_holder: bool = False
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
    # ESPN 25th Anniversary setup and shared historic roster edits: "" = off, otherwise the path of a
    # saved ``nfl2k5.espn25.plan.v1`` JSON plan written by Rosters > ESPN Anniversary.  A fixed-span
    # resource plan (SITU outer 22 + the shared historic ROSTs), no executable owner; it is applied
    # LAST on the disposable copy, after every relocation and roster pass, and resolved through the
    # copy's own XDVDFS/outer tables.  Never enabled by a preset.  EXPERIMENTAL / UNWITNESSED.
    espn25_plan: str = ""
    weather_plan: str = ""  # Saved nfl2k5.weather.edits.v1 JSON; EXPERIMENTAL, OFF
    weather_haze: bool = False  # Existing dry-weather coefficient; EXPERIMENTAL, OFF
    # b76-k2: a jersey 1 inside a two-digit number moves toward the other digit (the number binder rewritten in
    # place); EXPERIMENTAL / UNWITNESSED, off in every preset
    number_kerning: bool = False
    modern_color: bool = False  # Broadcast light rigs and grass re-grade; EXPERIMENTAL, OFF
    modern_color_settings: dict = field(default_factory=dict)  # Project recipe; {} means v2.1
    modern_arrowhead: bool = False  # Kansas City home packages toward the 2026 look; EXPERIMENTAL, OFF
    modern_metlife: bool = False  # Giants/Jets packages become MetLife Stadium; EXPERIMENTAL, OFF
    # b76-u4: folder of 2026 team venue art (<team>/venue/manifest.json, metlife_team_art/v1, plus _league marks)
    # written into every team's home stadium packages; "" = off. EXPERIMENTAL / UNWITNESSED, off in every preset
    modern_venues_2026: str = ""
    modern_metlife_model: bool = False  # b76-u5: MetLife Stadium as a new model (needs the skin); EXPERIMENTAL, OFF
    # b76-hm: modern helmets and facemasks (the Revolution helmet C with the modern Riddell details, 15 modern Riddell
    # masks in slots 12-26; the Standard shell and masks 0-11 stay retail for the classic scenarios). EXPERIMENTAL, OFF
    # in every preset
    modern_helmets: bool = False
    modern_sofi: bool = False  # b76-u6: SoFi Stadium for the Rams (s23) and Chargers (s24); EXPERIMENTAL, OFF
    modern_highmark: bool = False  # b76-st: the new Highmark Stadium for the Bills (s03); EXPERIMENTAL, OFF
    modern_att: bool = False  # b76-st2: AT&T Stadium for the Cowboys (s07); EXPERIMENTAL, OFF
    modern_levis: bool = False  # b76-st2: Levi's Stadium for the 49ers (s25); EXPERIMENTAL, OFF
    modern_allegiant: bool = False  # b76-st2: Allegiant Stadium for the Raiders (s20); EXPERIMENTAL, OFF
    modern_mercedes_benz: bool = False  # b76-st2: Mercedes-Benz Stadium for the Falcons (s01); EXPERIMENTAL, OFF
    modern_usbank: bool = False  # b76-st3: U.S. Bank Stadium for the Vikings (s15); EXPERIMENTAL, OFF
    modern_lucas_oil: bool = False  # b76-st3: Lucas Oil Stadium for the Colts (s11); EXPERIMENTAL, OFF
    modern_state_farm: bool = False  # b76-st3: State Farm Stadium for the Cardinals (s00); EXPERIMENTAL, OFF
    modern_hard_rock: bool = False  # b76-st4: Hard Rock Stadium for the Dolphins (s14); EXPERIMENTAL, OFF
    modern_gillette: bool = False  # b76-st4: Gillette Stadium for the Patriots (s16); EXPERIMENTAL, OFF
    modern_lambeau: bool = False  # b76-st4: Lambeau Field for the Packers (s10); EXPERIMENTAL, OFF
    modern_everbank: bool = False  # b76-st4: EverBank Stadium for the Jaguars (s12); EXPERIMENTAL, OFF
    #: b76-st4: its 2026 construction (on by default: the season as it stands; off: the 2025 stadium); only read
    #: when modern_everbank is on
    modern_everbank_construction: bool = True
    #: b76-st5: the modern stadium boards (the tier 2 board kit) on the retail stadiums the teams still play in
    #: (Superdome, NRG, Huntington Bank Field, Empower Field); EXPERIMENTAL, OFF
    modern_board_kit: bool = False
    # b76-pf: a modern outdoor NFL practice facility in the practice field every practice mode loads (s32); EXPERIMENTAL,
    # OFF in every preset
    modern_practice_field: bool = False
    # b76-pf P1: with the practice facility, the practicing team's logo at midfield (the field's midfield material named
    # teamlogo and the executable's field swap given an eighth pair, an allocator owner); EXPERIMENTAL, OFF in every
    # preset
    modern_practice_field_team_logo: bool = False
    # b76-tf: every home field gets its 2026 surface (modern synthetic turf or natural grass), repainted after every
    # stadium writer; the turf word stays retail. EXPERIMENTAL / UNWITNESSED, off in every preset
    modern_surfaces: bool = False
    # four standalone GAMEDATA marks (shield_espn, nfl_chiclet, espnLogo1, z_ESPN_bug) redrawn from the 2026
    # MNF broadcast stills and refit in their retail spans; EXPERIMENTAL / UNWITNESSED, off in every preset
    official_marks_pack: str = ""
    espn_marks_2026: bool = False
    # b76-p2: the replay transition, two wipes, the pause scoreboard, the helmet bumper monitor and the player card
    # shield repainted to the 2026 MNF package in their retail allocations; EXPERIMENTAL / UNWITNESSED, off in every preset
    espn_wipes_boards_2026: bool = False
    # b76-km: the kick meter, its aim arrow and the wind arrow redrawn in the 2026 ESPN bar's look (data only, three
    # gamedata.iff scenes refit in their retail spans); EXPERIMENTAL / UNWITNESSED, off in every preset
    kick_meter_2026: bool = False
    # b77-v1: the shared goalpost (every venue) with its uprights 35 ft above the crossbar (NFL since 2014): two
    # gamedata.iff scenes refit in their retail spans plus three in-place executable operands (the upright lines and
    # the ball/upright collision top); scoring unchanged. EXPERIMENTAL / UNWITNESSED, off in every preset
    modern_goalposts: bool = False
    # b77-co1: the 2026 head coaches: every club's coach model (cNN.iff chunk 0) refit in its retail span with his 2026
    # sideline look (club colours, 2026 chest logo, unbranded headset) and his face from his official headshot, plus
    # Dallas and Washington's Coach Matchup pictures (two free portrait slots and two coach-record photo ids).
    # EXPERIMENTAL / UNWITNESSED: on only in the experimental preset (the SOFTDRINK 2K28 recipe's preset)
    modern_coaches: bool = False
    # b775-hs1: hair styles: seven new hair models (long locs, short twists, long flowing hair, afro puff, braids, bun,
    # mullet) and nine hair textures ADDED to the player models next to the retail dreads, plus a late executable owner
    # that shows the one a player's roster hair style (record +0x0D, Studio field hair_style) asks for. Style 0 keeps
    # every player exactly as retail. EXPERIMENTAL / UNWITNESSED: on only in the experimental preset
    hair_styles: bool = False
    # b776-ai2: CPU AI, two late executable owners installed after every other executable writer.
    # nfl2k5_cpu_qb_reads: cpu_qb_zone_windows (the covered-window curve 0x50C51C: a defender who reaches the catch
    # point with or before the ball now closes the window) and cpu_qb_recheck (the CPU QB only weighs receivers he read
    # recently, stays on the one he picked and pulls the throw, at most twice a play, when that window closed).
    # nfl2k5_db_ball_play: db_ball_play (a defender reacting to the throw runs at full speed to the stored catch point).
    # EXPERIMENTAL / UNWITNESSED: off in every preset; a test recipe turns them on.
    cpu_qb_zone_windows: bool = False
    cpu_qb_recheck: bool = False
    db_ball_play: bool = False
    # b777-qb3: nfl2k5_qb_accuracy, a late executable owner hooked where the pass accuracy routine stores the miss
    # distance: a miss on a throw under 40 yd shrinks with the passer's Pass Accuracy and falls behind the receiver as
    # often as ahead (short drags/outs/slants/digs on the run were always overthrown and ignored the rating).
    # EXPERIMENTAL / UNWITNESSED: on only in the experimental preset (the SOFTDRINK 2K28 recipe's preset)
    qb_accuracy: bool = False
    # b776-pa2: play art routes at their real length: the play-art filter no longer cuts a chain's last route segment
    # (go, drag, flat, out, post/corner break) to 10 ft; it is drawn at its authored length, kept inside the play-call
    # panel. Only how the art is drawn changes. A late executable owner. EXPERIMENTAL / UNWITNESSED in game
    play_art_routes: bool = False
    # b777-ol1: run blocking: on running plays a defender sheds a block after a rating-based delay (Run Blocking of the
    # blocker against Run Coverage of the defender, 0.08-0.60 s instead of retail's 0.05 s for everyone), sheds far less
    # often once a controlled carrier's run has declared, and wins the first contact a little less often. Pass
    # protection keeps every retail byte. The last late executable owner (nfl2k5_run_blocking). EXPERIMENTAL: on in
    # the Advanced and Experimental presets (Noah 10/20: "my offensive line just does not block very well").
    run_blocking: bool = False
    # b778-fo1: modern sideline catches: no force-out credit. Retail rules a receiver carried out of bounds by a
    # defender (contact state) a catch without his feet down, the pre-2008 force-out rule; from the 2008 season a
    # receiver must get both feet down in bounds. A late executable owner (nfl2k5_force_out) hooks the credit read at
    # 0x15799B; Anniversary moments of seasons before 2008 keep the credit. EXPERIMENTAL: on in the Advanced and
    # Experimental presets (the SOFTDRINK 2K28 recipe builds from Experimental); Basic keeps the 2004 rule.
    modern_force_out: bool = False
    # b778-xs1: on-demand modules prototype: Career Home is not read at boot; the module loader (a late allocator
    # owner, nfl2k5_module_loader) reads its section with the kernel's XeLoadSection when a MyCareer screen opens.
    # EXPERIMENTAL and OFF in every preset until Noah's witnessed MyCareer session (docs/mod_editor/overlay_modules.md).
    module_loader: bool = False
    # b778-xs1: the Crib keeps only the Trophy Room side (Noah 10/22): the catalog popup and the Catalogs / Crib Items
    # shops are cut (nfl2k5_crib_trophy_room, three in-place edits). On in the SOFTDRINK presets.
    crib_trophy_room: bool = False
    # b778-pc3: retail inbox story 23 omits its single-row standings setup.
    inbox_standings: bool = False
    # b778-fa1: CPU clubs keep their stars. The retail stage-6 veteran cap cut (0x2BFAF0) releases 10+ year
    # veterans on cap savings alone (Noah's MyNFL3 lost Mahomes, Kittle and Stanley before the 2027 preseason). A late
    # executable owner (nfl2k5_star_retention) hooks its value call at 0x2BFB67 so a player rated over 85, or a QB
    # over 75, is never its target. EXPERIMENTAL: on in the Advanced and Experimental presets (the SOFTDRINK 2K28
    # recipe builds from Experimental); Basic keeps the retail rule.
    star_retention: bool = False
    # b778-pi1: Franchise practice: injured players sit out. Retail heals every match copy for practice (0x61540: keeps
    # injuries only in league games, modes 5..7), so a starter who is out for weeks lines up in the Coach's Desk
    # Practice. A late executable owner (nfl2k5_practice_injuries) hooks 0x61550 so practice (modes 0..2) with a
    # season or franchise loaded keeps the copies' injuries; the native lineup check then benches them, as on game day.
    # On in the Advanced and Experimental presets (the ones with the Coach's Desk Practice row).
    practice_injuries: bool = False
    # b778-ai5: CPU ball carriers stay in bounds and CPU quarterbacks slide only past the sticks (or when a defender
    # reaches them first). A late executable owner (nfl2k5_ball_carrier_ai) hooks the carrier's sideline filter at
    # 0x2E29E6 and the slide decision at 0x2E340E; human carriers and late-half clock urgency keep retail. EXPERIMENTAL:
    # on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds from Experimental).
    cpu_ball_carriers: bool = False

    # b778-st2: rookie stars and stars earned or lost over a career. The draft-class generator's 3..5 best prospects
    # (the draft-AI key) and 1..2 later-round gems (a top development archetype) get the Star tier; every offseason,
    # before the Preseason aging, players gain a star for a top-tier overall/production season or lose it after a down
    # year (an 85..89 hysteresis band and pg1's veteran-QB rule keep the league total near today's). Right-stick moves
    # stay star-only. A late executable owner (nfl2k5_star_career). EXPERIMENTAL: on in the Advanced and Experimental
    # presets (the SOFTDRINK 2K28 recipe builds from Experimental); Basic keeps retail draft classes and tags.
    star_career: bool = False
    # b778-rh1: rookie faces: a bank of new fictional draft headshots for generated prospects, chosen by the prospect's
    # skin tone (from his position and name odds), build (his weight) and never a face an active player wears; his
    # skin, generic head and Dreads bit follow the face. New Portrai2.iff / portrai2.cdf outers (every existing portrait
    # plus the bank) and the class generator's skin/portrait code rewritten in place (nfl2k5_rookie_faces). Images
    # only. EXPERIMENTAL: on in the Experimental preset (the SOFTDRINK 2K28 recipe builds from it).
    rookie_faces: bool = False
    # b778-ee1/ee2: the once-in-a-century gray alien prospect: one draft class in 150 (never the first, never again in
    # that franchise once he appeared) makes one prospect a 7'11", 150 lb gray alien: portrait 1947, a new live face
    # (igface2.iff / .cdf, pf1947.iff), gray arms/hands/neck/far-face/sideline-skin textures in outer 3, the class
    # generator's coin blocks compacted in place to hold the roll and five texture lookups (nfl2k5_alien_prospect).
    # Needs rookie_faces. Images only. EXPERIMENTAL: on in the Experimental preset (the SOFTDRINK 2K28 recipe builds
    # from it).
    alien_prospect: bool = False
    # b778-sc2: in-place SportsCenter featured-player lookup; no cave request.
    sportscenter_lineup: bool = False
    # b778-dr1: franchise draft on a broadcast clock. Retail makes every CPU pick before the user's in one frame ("it
    # goes super fast straight to your pick", Noah 10/22). A late executable owner (nfl2k5_draft_clock) hooks the draft
    # screen's step (call at 0x326DBC): each CPU club is on the game's own draft clock for 60 s; Y = Advance to Next
    # Pick / Simulate My Pick (on the user's clock), X = Advance to Next User Pick. No state bytes. On in
    # the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds from Experimental).
    franchise_draft_clock: bool = False
    # b778-pg1: franchise in-season weekly progression: after each franchise regular-season game a young player with a
    # good game gains a point on his key ratings every other good game, an older player who sat out or played poorly
    # loses a point of speed one week in four. A late executable owner (nfl2k5_weekly_progression) wraps the
    # per-player stat merge at 0x134E05 (after the game's weekly-prep cleanup). EXPERIMENTAL: off in every preset until
    # the second scale-out (job xs1) gives the combined build its 608 code bytes.
    weekly_progression: bool = False
    # b778-pg2: the Front Office Player Progress screen stays available every week of the regular season and
    # playoffs, compares each rating with the season-opening baseline, and a toggle shows last week's change.
    # The snapshot record is a 5,232-byte PPG2 table in the roster arena tail (no save growth). A late executable
    # owner (nfl2k5_player_progress_screen) that needs the growable pool from b778-xs1. EXPERIMENTAL: on in the
    # Advanced and Experimental presets; Basic keeps the retail offseason-only screen.
    player_progress: bool = False
    # b778-pg3: the safe visibility-only half of the Player Progress screen. The Front Office row is
    # available in every regular-season and playoff week (retail showed it only in the offseason); no
    # snapshot, no save growth and no roster-arena tail. This can ship without nfl2k5_player_progress.
    player_progress_visible: bool = False
    # b778-cr1: the Player Contracts panel reads the player's college word without a null check (0x6E11F). One late
    # executable owner (nfl2k5_contract_college_guard) hooks it and uses the panel's own N/A fallback, so an existing
    # franchise with a null college opens without a roster repair. On in every SOFTDRINK preset (a crash fix).
    contract_college_guard: bool = False
    # b778-cb1: cornerback tackle credit in the post-game merge. A late executable owner draws a starting corner's
    # tackle line from the NFL per-game distribution through the game's own RNG, with lower nickel and dime
    # distributions, so simulated RCBs stop reading as low-tackle/high-INT outliers. Played games use the same
    # record. EXPERIMENTAL: on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds from
    # Experimental).
    sim_cb_tackles: bool = False
    # b778-sim1: the simulated franchise game's clock pace. The simulator's per-event clock decrement came from
    # sqrt(300 / (Sim. Quarter Length * 60)) * 0.03, so a 15-minute setting produced about 1.7x the plays, points and
    # yards of a 5-minute setting. One in-place patch at 0x10B89C fixes the decrement (nfl2k5_sim_stats), so a
    # simulated game lands on NFL totals at every Sim. Quarter Length. Played games, the overtime sim clock and the
    # CB tackle / weekly progression owners are untouched. On in the Advanced and Experimental presets (the
    # SOFTDRINK 2K28 recipe builds from Experimental); Basic keeps the retail pace.
    sim_stats: bool = False
    # b778-sd4: modern clock digits: the stadium loader's generated 6x7 bulb font for the play clock, game clock and
    # scores is rewritten in place as a solid warm-white LED matrix. A late executable owner (nfl2k5_clock_led) hooks
    # the end of the clock-font lookup loop at 0x9999A. Every stadium and weather variant uses the same atlas.
    # EXPERIMENTAL: on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds from Experimental).
    modern_clock_led: bool = False
    # b776-ns1: per-kit jersey number size: {"13H0": 1.1, ...} (kit = team code, H or A, variant) -> the chest and back
    # numbers of that uniform package draw S times larger (a late executable owner hooked after the jersey-number
    # selector; every other kit, helmet and shoulder number binds as retail). {} = off, the executable keeps its bytes.
    # EXPERIMENTAL / UNWITNESSED; set per recipe (Noah 10/19: the Chiefs only)
    team_number_scale: dict = field(default_factory=dict)
    # b77-fr1: the 2026 fans of the crowd-reaction cutaways: every club's crowd texture sets (four archive families)
    # refit in their retail spans with 2025-26 fan wear, the 2026 logos and new signs. EXPERIMENTAL / UNWITNESSED: on
    # only in the experimental preset (the SOFTDRINK 2K28 recipe's preset)
    modern_fans: bool = False
    # b77-rf1: the 2025-26 NFL officials: the referee scene (shirt, pants, a UV-only plan that retires the 2004
    # front-chest number patch and moves the collar off the back-number swatch), the caps TSET and the seven number
    # textures of gamedata.iff (HL drawn as DJ), refit in their retail spans. EXPERIMENTAL / UNWITNESSED: on only in
    # the experimental preset (the SOFTDRINK 2K28 recipe's preset)
    modern_officials: bool = False
    # opt-in data patch: real historic players in the 35 shared historic roster files of the 25 moments
    espn25_rosters: bool = False
    historic_rosters_2026: bool = False  # source-gated season roster work; incomplete data must refuse
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
    hires_pack: bool = False
    hires_folder: str = ""
    hires_scale: int = 2
    hires_target: str = "xemu-64"
    hires_families: tuple[str, ...] = ("helmets", "field_logos", "stock_fields", "scorebug", "numbers", "jerseys")
    guardian_cap: bool = False  # helmet C resource trial, experimental and unwitnessed
    scorebug: bool = False
    scorebug_runtime: bool = False
    scorebug_watermark: str = "auto"  # NFL, switching to MNF only for franchise Monday night; mnf / off overrides
    scorebug_folder: str = ""      # optional repaintable ESPN scorebar artwork folder (docs/scorebug_template layout); blank = shipped art
    indicator_names_folder: str = ""  # optional private indicator atlas; empty preserves the native FONT
    # nl1: controlled-player name label: "retail" (default, the old indicator), "retail_persistent" (old look,
    # stays on) or "scorebug" (nm1's label from indicator_names_folder). See nfl2k5_indicator_names.STYLES.
    indicator_names_style: str = "retail"
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
                or self.progression or self.franchise_economy or self.scheme_labels or self.camera or self.kick_rules or self.kick_power or self.position_pools or self.xbe_space or self.kickoff_relocated or self.dynamic_kickoff or self.depth_chart_rows or self.practice_squad or self.depth_locks
                or self.season_cap or self.season_2026 or self.widescreen or self.overtime or self.team_column or self.seven_on_seven
                or self.position_row or self.probowl_order or self.elbow_options or self.the1wam_lineman_rating or self.xemu_display_list_fix or self.resource_load_guard or self.loader_wakeup_fix or self.rb_rename or self.name_keyboard or bool(self.penalties) or bool(self.uniform_choice) or self.team_sleeves or self.helmet_finish == "matte"
                or self.position_row or self.probowl_order or self.elbow_options or self.the1wam_lineman_rating or self.xemu_display_list_fix or self.resource_load_guard or self.loader_wakeup_fix or self.rb_rename or self.trophy_room or self.name_keyboard or bool(self.penalties) or bool(self.uniform_choice) or self.helmet_finish == "matte"
                or self.kick_laces or self.punter_holder or self.franchise_practice or bool(self.prospect_names) or self.player_star
                or self.position_row or self.probowl_order or self.elbow_options or self.the1wam_lineman_rating or self.xemu_display_list_fix or self.resource_load_guard or self.loader_wakeup_fix or self.rb_rename or self.name_keyboard or bool(self.penalties) or bool(self.uniform_choice) or self.helmet_finish == "matte"
                or self.kick_laces or self.punter_holder or self.franchise_practice or bool(self.prospect_names) or self.player_star or self.star_career
                or self.modern_naming or self.crib_reclaim or self.read_option_runtime or self.franchise_2026_rules or self.senior_bowl
                or self.guardian_overlay or self.my_career or self.screen_hooks or self.coverage_trail or self.franchise_edit_player or self.cpu_money_downs != "retail" or self.accelerated_clock or self.coin_defer or self.decided_clock or self.cpu_scrambles == "modern" or self.weather_haze or self.number_kerning or self.modern_color or self.weekly_prep or self.weekly_prep_cpu or self.weekly_prep_remember or self.coach_ai or self.playbook_pair or self.deep_zone_facing or self.deep_zone_bail or self.reserves_16 or bool(self.created_teams_extra) or self.franchise_autosave or self.historic_teams_quick_game or self.espn25_more_moments or self.historic_stock_books or self.espn25_era_rules or self.k128_memory or self.team_ratings or self.play_art_routes or self.letter_grades or self.honors_page
                or self.sportscenter_lineup or self.momentum_collisions or self.scorebug_runtime or self.indicator_names_style != "retail" or self.momentum > 0 or self.momentum_contact or self.defensive_try or self.zone_drop_cap or self.all_stadiums or self.music_shuffle or self.practice_squad_screen or self.abilities or self.qb_spy or self.calendar_engine or self.coverage_slider or self.scramble_tuning or self.flatter_deep_ball or self.chop_block_toggle or self.music_policy != "retail" or self.music_unlock or self.music_userlist
                or self.guardian_overlay or self.my_career or self.screen_hooks or self.coverage_trail or self.franchise_edit_player or self.cpu_money_downs != "retail" or self.accelerated_clock or self.coin_defer or self.decided_clock or self.cpu_scrambles == "modern" or self.weather_haze or self.number_kerning or self.modern_color or self.weekly_prep or self.weekly_prep_cpu or self.weekly_prep_remember or self.coach_ai or self.playbook_pair or self.deep_zone_facing or self.deep_zone_bail or self.reserves_16 or bool(self.created_teams_extra) or self.franchise_autosave or self.historic_teams_quick_game or self.espn25_more_moments or self.historic_stock_books or self.espn25_era_rules or self.k128_memory or self.team_ratings or self.play_art_routes or self.letter_grades or self.honors_page or self.contract_college_guard
                or self.guardian_overlay or self.my_career or self.screen_hooks or self.coverage_trail or self.franchise_edit_player or self.cpu_money_downs != "retail" or self.accelerated_clock or self.coin_defer or self.decided_clock or self.cpu_scrambles == "modern" or self.weather_haze or self.number_kerning or self.modern_color or self.weekly_prep or self.weekly_prep_cpu or self.weekly_prep_remember or self.coach_ai or self.playbook_pair or self.deep_zone_facing or self.deep_zone_bail or self.reserves_16 or bool(self.created_teams_extra) or self.franchise_autosave or self.historic_teams_quick_game or self.espn25_more_moments or self.historic_stock_books or self.espn25_era_rules or self.k128_memory or self.team_ratings or self.play_art_routes or self.letter_grades or self.honors_page or self.sim_cb_tackles or self.sim_stats
                or self.momentum_collisions or self.scorebug_runtime or self.indicator_names_style != "retail" or self.momentum > 0 or self.momentum_contact or self.defensive_try or self.zone_drop_cap or self.all_stadiums or self.music_shuffle or self.practice_squad_screen or self.abilities or self.qb_spy or self.calendar_engine or self.coverage_slider or self.scramble_tuning or self.flatter_deep_ball or self.chop_block_toggle or self.music_policy != "retail" or self.music_unlock or self.music_userlist
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
        "scorebug_runtime": False, "scorebug_watermark": "auto",
        "momentum": 0, "momentum_contact": False, "momentum_collisions": False, "momentum_collision_level": 0,
        "read_option_runtime": False, "franchise_2026_rules": False, "senior_bowl": False,
        "guardian_overlay": False, "my_career": False, "my_career_setup": None, "crib_reclaim": False, "trim_intro_videos": False, "franchise_autosave": False,
        "screen_hooks": False, "coverage_trail": False, "franchise_edit_player": False, "cpu_money_downs": "retail", "accelerated_clock": False, "accelerated_clock_minimum_seconds": 20, "weekly_prep": False, "weekly_prep_cpu": False, "weekly_prep_remember": False, "coach_ai": False, "playbook_pair": False, "deep_zone_facing": False, "deep_zone_bail": False, "deep_zone_bail_calls": (), "reserves_16": False, "created_teams_extra": 0, "modern_naming": False, "defensive_try": False, "zone_drop_cap": False, "all_stadiums": False,
        "music_shuffle": False, "music_shuffle_selection": None, "practice_squad_screen": False,
        "abilities": False, "abilities_off_week": None, "abilities_lock_right_stick": False, "abilities_lock_special_moves": False, "abilities_lock_speedster": True, "abilities_right_stick_stars_only": False, "abilities_charge_stars_only": False, "abilities_button_moves_stars_only": False, "abilities_star_access": ("flicks_charge", "stick_charge", "full", "full"), "qb_spy": False, "calendar_engine": False, "coverage_slider": False, "scramble_tuning": False, "flatter_deep_ball": False, "chop_block_toggle": False, "team_names_2026": False, "hires_pack": False,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": False,
        "catch_slider": True, "accel_ramp": False, "draft_ai": True, "returner_fix": True, "progression": False, "franchise_economy": False,
        "edge_rename": False, "scorebug": False, "guardian_cap": False, "scheme_labels": False, "camera": False,
        "kick_rules": False, "kick_power": True, "kickoff_alignment": False, "dynamic_kickoff": False, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": False, "position_pools_keep_olb": False, "season_cap": False, "season_2026": False, "widescreen": False, "overtime": False, "team_column": True, "seven_on_seven": False, "team_history": "", "career_stats": "", "screen_timing": None, "depth_roles": False, "depth_chart_rows": False, "position_row": True, "probowl_order": True, "penalties": "", "uniform_choice": "", "team_sleeves": True, "helmet_finish": "glossy", "kick_laces": False, "punter_holder": False, "franchise_practice": False, "practice_squad": False, "depth_locks": False, "prospect_names": "", "player_star": False,
        "espn25_plan": "", "espn25_rosters": False,
        "weather_plan": "", "weather_haze": False, "modern_color": False, "modern_arrowhead": False, "modern_metlife": False, "modern_metlife_model": False, "modern_sofi": False, "modern_highmark": False, "modern_att": False, "modern_levis": False, "modern_allegiant": False, "modern_mercedes_benz": False, "modern_surfaces": False, "modern_helmets": False, "modern_usbank": False, "modern_lucas_oil": False, "modern_state_farm": False, "modern_hard_rock": False, "modern_gillette": False, "modern_lambeau": False, "modern_everbank": False, "modern_everbank_construction": True, "modern_board_kit": False, "modern_practice_field": False, "modern_practice_field_team_logo": False,
        "coin_defer": False, "decided_clock": False,
        "decided_clock_margin": 17, "decided_clock_seconds": 60,
        "cpu_scrambles": "retail",
    },
    # ADVANCED = basic + everything that modernises the game (Noah's tweaks and breakthroughs).
    "softdrink_advanced": {
        "scorebug_runtime": False, "scorebug_watermark": "auto",
        "momentum": 0, "momentum_contact": False, "momentum_collisions": False, "momentum_collision_level": 0,
        "read_option_runtime": False, "franchise_2026_rules": False, "senior_bowl": False,
        "guardian_overlay": False, "my_career": False, "my_career_setup": None, "crib_reclaim": False, "trim_intro_videos": False, "franchise_autosave": True,
        "screen_hooks": False, "coverage_trail": True, "franchise_edit_player": True, "cpu_money_downs": "retail", "accelerated_clock": False, "accelerated_clock_minimum_seconds": 20, "weekly_prep": False, "weekly_prep_cpu": False, "weekly_prep_remember": False, "coach_ai": False, "playbook_pair": False, "deep_zone_facing": False, "deep_zone_bail": False, "deep_zone_bail_calls": (), "reserves_16": False, "created_teams_extra": 0, "modern_naming": False, "defensive_try": False, "zone_drop_cap": False, "all_stadiums": False,
        "music_shuffle": False, "music_shuffle_selection": None, "practice_squad_screen": False,
        "abilities": False, "abilities_off_week": None, "abilities_lock_right_stick": False, "abilities_lock_special_moves": False, "abilities_lock_speedster": True, "abilities_right_stick_stars_only": True, "abilities_charge_stars_only": True, "abilities_button_moves_stars_only": False, "abilities_star_access": ("flicks_charge", "stick_charge", "full", "full"), "qb_spy": False, "calendar_engine": False, "coverage_slider": False, "scramble_tuning": False, "flatter_deep_ball": False, "chop_block_toggle": False, "team_names_2026": False, "hires_pack": False,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True, "franchise_economy": False,
        "edge_rename": True, "scorebug": False, "guardian_cap": False, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": False, "dynamic_kickoff": False, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": True, "position_pools_keep_olb": False, "season_cap": False, "season_2026": True, "widescreen": False, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "career_stats": "", "screen_timing": None, "depth_roles": True, "depth_chart_rows": False, "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "", "team_sleeves": True, "helmet_finish": "glossy", "kick_laces": False, "punter_holder": True, "franchise_practice": True, "practice_squad": False, "depth_locks": False, "prospect_names": "modern", "player_star": True,
        "espn25_plan": "", "espn25_rosters": False,
        "weather_plan": "", "weather_haze": False, "modern_color": False, "modern_arrowhead": False, "modern_metlife": False, "modern_metlife_model": False, "modern_sofi": False, "modern_highmark": False, "modern_att": False, "modern_levis": False, "modern_allegiant": False, "modern_mercedes_benz": False, "modern_surfaces": False, "modern_helmets": False, "modern_usbank": False, "modern_lucas_oil": False, "modern_state_farm": False, "modern_hard_rock": False, "modern_gillette": False, "modern_lambeau": False, "modern_everbank": False, "modern_everbank_construction": True, "modern_board_kit": False, "modern_practice_field": False, "modern_practice_field_team_logo": False,
        "coin_defer": False, "decided_clock": False,
        "decided_clock_margin": 17, "decided_clock_seconds": 60,
        "cpu_scrambles": "retail",
    },
    # EXPERIMENTAL = advanced + widescreen and anything still rough (dynamic-kickoff line-up).
    "softdrink_experimental": {
        "scorebug_runtime": False, "scorebug_watermark": "auto",
        "momentum": 0, "momentum_contact": False, "momentum_collisions": False, "momentum_collision_level": 0,
        "read_option_runtime": False, "franchise_2026_rules": False, "senior_bowl": False,
        "guardian_overlay": False, "my_career": False, "my_career_setup": None, "crib_reclaim": False, "trim_intro_videos": False, "franchise_autosave": True,
        "screen_hooks": False, "coverage_trail": True, "franchise_edit_player": True, "cpu_money_downs": "retail", "accelerated_clock": False, "accelerated_clock_minimum_seconds": 20, "weekly_prep": False, "weekly_prep_cpu": False, "weekly_prep_remember": False, "coach_ai": False, "playbook_pair": False, "deep_zone_facing": False, "deep_zone_bail": False, "deep_zone_bail_calls": (), "reserves_16": False, "created_teams_extra": 0, "modern_naming": False, "defensive_try": False, "zone_drop_cap": False, "all_stadiums": False,
        "music_shuffle": False, "music_shuffle_selection": None, "practice_squad_screen": False,
        "abilities": False, "abilities_off_week": None, "abilities_lock_right_stick": False, "abilities_lock_special_moves": False, "abilities_lock_speedster": True, "abilities_right_stick_stars_only": True, "abilities_charge_stars_only": True, "abilities_button_moves_stars_only": False, "abilities_star_access": ("flicks_charge", "stick_charge", "full", "full"), "qb_spy": False, "calendar_engine": True, "coverage_slider": False, "scramble_tuning": False, "flatter_deep_ball": False, "chop_block_toggle": False, "team_names_2026": False, "hires_pack": False,
        "music_policy": "retail", "music_unlock": False, "music_userlist": False,
        "guardian_cap": True,
        "throw": True, "max_deep_yards": 80.0, "arc": 0.0, "realistic_flight": True, "arc_by_distance": True,
        "catch_slider": True, "accel_ramp": True, "draft_ai": True, "returner_fix": True, "progression": True, "franchise_economy": False,
        "edge_rename": True, "scorebug": True, "scheme_labels": True, "camera": True,
        "kick_rules": True, "kick_power": False, "kickoff_alignment": True, "dynamic_kickoff": True, "xbe_space": False, "kickoff_relocated": False,
        "position_pools": True, "position_pools_keep_olb": False, "season_cap": True, "season_2026": True, "widescreen": True, "overtime": True, "team_column": True, "seven_on_seven": False, "team_history": "retail", "career_stats": "", "screen_timing": "D", "depth_roles": True, "depth_chart_rows": True, "position_row": True, "probowl_order": True, "penalties": "nfl", "uniform_choice": "", "team_sleeves": True, "helmet_finish": "glossy", "kick_laces": True, "punter_holder": True, "franchise_practice": True, "practice_squad": True, "depth_locks": True, "prospect_names": "modern", "player_star": True,
        "espn25_plan": "", "espn25_rosters": False,
        "weather_plan": "", "weather_haze": False, "modern_color": False, "modern_arrowhead": False, "modern_metlife": False, "modern_metlife_model": False, "modern_sofi": False, "modern_highmark": False, "modern_att": False, "modern_levis": False, "modern_allegiant": False, "modern_mercedes_benz": False, "modern_surfaces": False, "modern_helmets": False, "modern_usbank": False, "modern_lucas_oil": False, "modern_state_farm": False, "modern_hard_rock": False, "modern_gillette": False, "modern_lambeau": False, "modern_everbank": False, "modern_everbank_construction": True, "modern_board_kit": False, "modern_practice_field": False, "modern_practice_field_team_logo": False,
        "coin_defer": False, "decided_clock": False,
        "decided_clock_margin": 17, "decided_clock_seconds": 60,
        "cpu_scrambles": "retail",
    },
}
PRESETS["softdrink_experimental"]["modern_naming"] = tt.modern_naming_patch.preset_enabled("experimental")
# b76 p1: ESPN presentation marks (2026) are experimental and unwitnessed: off in every preset.
for _preset in PRESETS.values():
    _preset["espn_marks_2026"] = False
del _preset
# b76-p2: ESPN 2026 wipes and boards are experimental and unwitnessed: off in every preset.
for _preset in PRESETS.values():
    _preset["espn_wipes_boards_2026"] = False
# b76-km: the 2026 kick meter is experimental and unwitnessed: off in every preset.
for _preset in PRESETS.values():
    _preset["kick_meter_2026"] = False
del _preset
# b77-v1: modern goalposts are experimental and unwitnessed: off in every preset.
for _preset in PRESETS.values():
    _preset["modern_goalposts"] = False
del _preset
# b77-co1: the 2026 head coaches are experimental and unwitnessed: on only in the experimental preset, the one the
# SOFTDRINK 2K28 recipe builds from (job's choice, recorded in the co1 report; Noah asked for them in the shortcut build).
for _preset in PRESETS.values():
    _preset["modern_coaches"] = False
PRESETS["softdrink_experimental"]["modern_coaches"] = True
del _preset
# b775-hs1: hair styles are experimental and unwitnessed: on only in the experimental preset, the one the SOFTDRINK
# 2K28 recipe builds from (Noah 10/17: "Hairstyles ... This goes in his next test disc").
for _preset in PRESETS.values():
    _preset["hair_styles"] = False
PRESETS["softdrink_experimental"]["hair_styles"] = True
del _preset
# b776-ai2: the CPU AI options are off in every preset (retail bytes); only a test recipe turns them on.
for _preset in PRESETS.values():
    _preset["cpu_qb_zone_windows"] = False
    _preset["cpu_qb_recheck"] = False
    _preset["db_ball_play"] = False
# b777-qb3: QB accuracy is experimental and unwitnessed: on only in the experimental preset, the one the SOFTDRINK 2K28
# recipe builds from (Noah 10/20 asked for it in the next build).
for _preset in PRESETS.values():
    _preset["qb_accuracy"] = False
PRESETS["softdrink_experimental"]["qb_accuracy"] = True
# b776-pa2: full-length play art routes: on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds
# from Experimental; Noah 10/18: "drags ... all the way across the screen ... go routes ... 20 plus yards").
for _preset in PRESETS.values():
    _preset["play_art_routes"] = False
PRESETS["softdrink_advanced"]["play_art_routes"] = True
PRESETS["softdrink_experimental"]["play_art_routes"] = True
del _preset
# b777-ol1: run blocking: on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds from
# Experimental; Noah 10/20 asked for better run blocking and more chunk runs); Basic keeps the retail bytes.
for _preset in PRESETS.values():
    _preset["run_blocking"] = False
PRESETS["softdrink_advanced"]["run_blocking"] = True
PRESETS["softdrink_experimental"]["run_blocking"] = True
del _preset
# b778-fo1: modern sideline catches (no force-out from 2008): a modern rule like overtime and the kick rules, so on in
# the Advanced and Experimental presets; Basic keeps the game in 2004 (the force-out catch of its time).
for _preset in PRESETS.values():
    _preset["modern_force_out"] = False
PRESETS["softdrink_advanced"]["modern_force_out"] = True
PRESETS["softdrink_experimental"]["modern_force_out"] = True
for _preset in PRESETS.values():  # b778-pg1: weekly progression is off until the combined layout has room (xs1)
    _preset["weekly_progression"] = False
del _preset
# b778-xs1: the Crib, Trophy Room only (Noah 10/22: "The only thing I want in the crib is the trophy room"): on in
# every SOFTDRINK preset; retail-style builds keep the Crib whole.
for _preset in PRESETS.values():
    _preset["crib_trophy_room"] = False
for _name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
    PRESETS[_name]["crib_trophy_room"] = True
del _preset, _name
# b778-pc3: the last-undefeated inbox story's standings setup.
for _name, _preset in PRESETS.items():
    _preset["inbox_standings"] = _name.startswith("softdrink_")
del _name, _preset
# b778-st2: rookie stars and career stars: a modern NFL feature like progression, so on in the Advanced and
# Experimental presets (the SOFTDRINK 2K28 recipe builds from Experimental); Basic keeps retail draft classes.
for _preset in PRESETS.values():
    _preset["star_career"] = False
PRESETS["softdrink_advanced"]["star_career"] = True
PRESETS["softdrink_experimental"]["star_career"] = True
del _preset
# b778-rh1: rookie faces are experimental: on only in the Experimental preset (the SOFTDRINK 2K28 recipe builds from it).
for _preset in PRESETS.values():
    _preset["rookie_faces"] = False
PRESETS["softdrink_experimental"]["rookie_faces"] = True
del _preset
# b778-fa1: CPU clubs keep their stars when clearing cap room (franchise AI), on in Advanced and Experimental.
for _preset in PRESETS.values():
    _preset["star_retention"] = False
PRESETS["softdrink_advanced"]["star_retention"] = True
PRESETS["softdrink_experimental"]["star_retention"] = True
# b778-pi1: franchise practice keeps injuries: on wherever the Coach's Desk Practice row (franchise_practice) is on.
for _preset in PRESETS.values():
    _preset["practice_injuries"] = bool(_preset.get("franchise_practice"))
del _preset
# b778-ai5: CPU ball carriers stay in bounds / QBs slide past the sticks (gameplay AI, like run blocking).
for _preset in PRESETS.values():
    _preset["cpu_ball_carriers"] = False
PRESETS["softdrink_advanced"]["cpu_ball_carriers"] = True
PRESETS["softdrink_experimental"]["cpu_ball_carriers"] = True
del _preset
# b778-ee1: the alien prospect rides on rookie faces: the same preset.
for _preset in PRESETS.values():
    _preset["alien_prospect"] = False
PRESETS["softdrink_experimental"]["alien_prospect"] = True
# b778-sc2: repair featured-player identity lookup in every SOFTDRINK preset.
for _preset in PRESETS.values():
    _preset["sportscenter_lineup"] = True
# b778-dr1: the broadcast-paced franchise draft, on with the other SOFTDRINK franchise features (Advanced, Experimental).
for _preset in PRESETS.values():
    _preset["franchise_draft_clock"] = False
PRESETS["softdrink_advanced"]["franchise_draft_clock"] = True
PRESETS["softdrink_experimental"]["franchise_draft_clock"] = True
del _preset
# b778-pg2: the Player Progress screen is OFF in every preset. The native screen and weekly capture work, but the
# provisional save host (roster arena tail 0x8FCF4) is used by the running Front Office: the emulator froze the Front
# Office after the record was written (the same save decodes correctly offline and stays 720,044 bytes). A versioned
# franchise footer or an owned arena reserve is required before this can ship. The option stays available for tests.
for _preset in PRESETS.values():
    _preset["player_progress"] = False
# b778-pg3: the visibility-only half is safe (it is the pg2 control run): on in Advanced and
# Experimental, off in Basic. The snapshot half stays off until its footer has emulator proof.
for _preset in PRESETS.values():
    _preset["player_progress_visible"] = False
PRESETS["softdrink_advanced"]["player_progress_visible"] = True
PRESETS["softdrink_experimental"]["player_progress_visible"] = True
del _preset
# b778-cr1: the Player Contracts null-college crash guard is a safety fix, not a taste option: on in every preset.
for _preset in PRESETS.values():
    _preset["contract_college_guard"] = True
del _preset
# b778-cb1: cornerback tackle credit: on in the Advanced and Experimental presets (the SOFTDRINK 2K28 recipe builds
# from Experimental); Basic keeps the retail merge byte for byte.
for _preset in PRESETS.values():
    _preset["sim_cb_tackles"] = False
PRESETS["softdrink_advanced"]["sim_cb_tackles"] = True
PRESETS["softdrink_experimental"]["sim_cb_tackles"] = True
del _preset
# b778-sim1: the simulated-game pace fix is a stat correction, not a taste option: on in the Advanced and Experimental
# presets (the SOFTDRINK 2K28 recipe builds from Experimental). Basic keeps retail for purists.
for _preset in PRESETS.values():
    _preset["sim_stats"] = False
PRESETS["softdrink_advanced"]["sim_stats"] = True
PRESETS["softdrink_experimental"]["sim_stats"] = True
del _preset
# b778-sd4: modern LED clock digits are a presentation fix like the modern goalposts and the 2026 boards, so on in the
# Advanced and Experimental presets; Basic keeps the retail bulbs.
for _preset in PRESETS.values():
    _preset["modern_clock_led"] = False
PRESETS["softdrink_advanced"]["modern_clock_led"] = True
PRESETS["softdrink_experimental"]["modern_clock_led"] = True
del _preset
# b77-fr1: the 2026 fans are experimental and unwitnessed: on only in the experimental preset, the one the SOFTDRINK
# 2K28 recipe builds from (job's choice, recorded in the fr1 report; Noah asked for them on 2026-10-12).
for _preset in PRESETS.values():
    _preset["modern_fans"] = False
PRESETS["softdrink_experimental"]["modern_fans"] = True
del _preset
# b77-rf1: the 2025-26 officials are experimental and unwitnessed: on only in the experimental preset, the one the
# SOFTDRINK 2K28 recipe builds from (job's choice, recorded in the rf1 report; Noah: "the refs need updated").
for _preset in PRESETS.values():
    _preset["modern_officials"] = False
PRESETS["softdrink_experimental"]["modern_officials"] = True
del _preset
# b76-h1: historic teams in Quick Game are off in basic and advanced (a 2004 game keeps its menus).
for _preset in PRESETS.values():
    _preset["historic_teams_quick_game"] = False
    _preset["historic_rosters_2026"] = False
del _preset
# b775-ct1: classic teams (Noah 10/17: "add a few more classic teams ... with their proper stadium, uniforms, rosters,
# depth charts", for his next test disc): on in the experimental preset, the one the SOFTDRINK 2K28 recipe builds from.
# They only act where historic teams in Quick Game is on (the recipe turns that on).
for _preset in PRESETS.values():
    _preset["classic_teams"] = False
PRESETS["softdrink_experimental"]["classic_teams"] = True
del _preset
# b76-vb3 E1: the return blocking rule is Noah's feel test; off in every preset.
for _preset in PRESETS.values():
    _preset["kickoff_return_blocking"] = False
del _preset
# b76-m1: 25 more Anniversary moments are off in every preset until witnessed (the ultimate recipe turns them on).
for _preset in PRESETS.values():
    _preset["espn25_more_moments"] = False
    _preset["historic_stock_books"] = False
    _preset["espn25_named_previews"] = False
    _preset["espn25_era_rules"] = False
del _preset
# b76-k2: the jersey number kerning is experimental and unwitnessed: off in every preset.
for _preset in PRESETS.values():
    _preset["number_kerning"] = False
del _preset
# b76-k1: 128 MB memory (K128) and the roster block in the extra heap are experimental: off in every preset.
for _preset in PRESETS.values():
    _preset["k128_memory"] = False
    _preset["k128_roster_heap"] = False
    _preset["k128_early"] = False
del _preset
# b77-f4: letter grades in Franchise (Noah, 2026-10-07): Basic keeps the 2004 numbers; Modern and Experimental grade.
for _preset in PRESETS:
    PRESETS[_preset]["team_ratings"] = _preset in ("softdrink_advanced", "softdrink_experimental")

PRESETS["softdrink_basic"]["letter_grades"] = False
PRESETS["softdrink_advanced"]["letter_grades"] = True
PRESETS["softdrink_experimental"]["letter_grades"] = True
# b77 p9: the modern presets use the CPU decisions level Modern 2 (sourced fourth-down table, overtime branch, two-point chart,
# defensive coverage variety); Basic stays retail. Experimental and unwitnessed.
for _preset in (PRESETS["softdrink_advanced"], PRESETS["softdrink_experimental"]):
    _preset["cpu_money_downs"] = "modern2"
del _preset
# b77-f5: the Player Card honors page and the sourced award history: on in the modern presets (Modern and
# Experimental) like the other b77 Franchise features (the f4 and p9 briefs); Basic stays retail. F5's own brief
# names no preset, so this is the job's choice, not a recorded Noah decision.
PRESETS["softdrink_basic"]["honors_page"] = False
PRESETS["softdrink_advanced"]["honors_page"] = True
PRESETS["softdrink_experimental"]["honors_page"] = True
PRESETS["softdrink_basic"]["honors_history"] = ""
PRESETS["softdrink_advanced"]["honors_history"] = "builtin"
PRESETS["softdrink_experimental"]["honors_history"] = "builtin"
# vt1: the SOFTDRINK release includes the 2026 coach profiles; the Build toggle remains editable.
PRESETS["softdrink_experimental"]["coach_ai"] = True
# i4: hu1 authored the alphabet consumed by nm1; resolve it inside each installed bundle.
for _preset_values in PRESETS.values():
    _preset_values["indicator_names_folder"] = ""
    # nl1 (Noah, 2026-10-17: "let's go back to the old player name indicator"): every preset keeps the
    # retail label. The nm1 label stays available as indicator_names_style "scorebug" (add, don't replace).
    _preset_values["indicator_names_style"] = "retail"
# b776-sm1 (Noah, 2026-10-18, after the b775 video: "R1 last names: go back to retail"): every preset, advanced and
# experimental included, keeps the retail label. b775-int1 had put the SOFTDRINK presets on "retail_persistent", whose
# CONTROL edit at 0x7604A labels only human-controlled players, so R1's show-names stopped drawing everyone else.
# "retail_persistent" and "scorebug" stay selectable styles (add, don't replace).
# (The loop above already sets "retail" for every preset; nothing below overrides it.)
PRESETS["softdrink_experimental"]["indicator_names_folder"] = str(ROOT / "data/nfl2k5_indicator_names")
# The private FONT occupies the appended sprite scene, which the runtime pass creates.
PRESETS["softdrink_experimental"]["scorebug_runtime"] = True
PRESET_TITLES = {"softdrink_basic": "SOFTDRINK patch: basic (2004 game, just the 2K5 fixes)",
                 "softdrink_advanced": "SOFTDRINK patch: advanced (everything modern)",
                 "softdrink_experimental": "SOFTDRINK patch: experimental (advanced + widescreen + rough edges)"}


# b76-i1: Custom intro video is in no preset; choosing a preset clears a chosen movie.
for _preset_values in PRESETS.values():
    _preset_values.setdefault("custom_intro", "")
# b76-u4: the 2026 venue art is in no preset; choosing a preset clears a chosen art folder.
for _preset_values in PRESETS.values():
    _preset_values.setdefault("modern_venues_2026", "")
# b773-sb2: the user's Super Bowl logos folder is in no preset either.
for _preset_values in PRESETS.values():
    _preset_values.setdefault("super_bowl_user_art", "")

# b76-z2: the xemu display-list stability fix is on in all three presets. It changes no gameplay
# and no picture: the GPU receives the same methods in the same order, only the place where
# xemu's pusher waits for the list-release callback moves into the ring. It fits "basic" (the
# fixes a 2K5 update would have shipped) as a crash fix for the runtime most players use.
for _preset_values in PRESETS.values():
    _preset_values["xemu_display_list_fix"] = True
    # b76-dn: allocation failure is a skipped resource, not an asynchronous read into NULL.
    _preset_values["resource_load_guard"] = True
    # b777-st1: the retail disc loader thread could suspend itself just after a read was posted and never wake
    # (endless LOADING card). Its idle now waits 1 ms and re-checks instead; same states, same reads.
    _preset_values["loader_wakeup_fix"] = True
    # b777-rb2 (Noah 10/20: "rename halfback to running back (RB) everywhere"): display text only.
    _preset_values["rb_rename"] = True
    # b778-pg2 (Noah 10/22: "the crib in my NFL should be renamed to Trophy Room"): display text only.
    _preset_values["trophy_room"] = True
    # b77-k1: typing space, period, apostrophe and hyphen in player names changes no gameplay; it is a Create/Edit Player
    # fix that every build should carry (real rosters already hold all four).
    _preset_values["name_keyboard"] = True


def apply_preset(plan: BuildPlan, name: str) -> BuildPlan:
    """Return a copy of ``plan`` with the named preset's toggles set (source/target/name kept)."""

    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    values = dict(asdict(plan))
    values["commentary"] = list(plan.commentary)
    values.update(PRESETS[name])
    values["modern_naming"] = tt.modern_naming_patch.preset_enabled(name.removeprefix("softdrink_"))
    if not values.get("name"):
        values["name"] = PRESET_TITLES[name]
    return BuildPlan(**values)


def _espn25_rosters_available() -> bool:
    module = _core_module("nfl2k5_espn25_rosters")
    if module is None:
        return False
    try:
        module.dataset()  # a missing or changed manifest/CSV disables the row
    except Exception:  # noqa: BLE001
        return False
    return True


def _team_names_available() -> bool:
    module = _core_module("nfl2k5_team_names_2026")
    try:
        return module is not None and bool(module.manifest()["teams"])
    except (OSError, ValueError):
        return False


def _espn_marks_available(marks_pack=None) -> bool:
    module = _core_module("nfl2k5_espn_marks")
    return module is not None and module.available(marks_pack)  # the pins and the shipped art must agree


def _espn_wipes_boards_available(marks_pack=None) -> bool:  # b76-p2
    module = _core_module("nfl2k5_espn_wipes_boards")
    return module is not None and module.available(marks_pack)  # the pins and the shipped art must agree


def _kick_meter_available() -> bool:  # b76-km
    module = _core_module("nfl2k5_kick_meter_2026")
    return module is not None and module.available()  # the pins, the art and the geometry must agree


def _cpu_ai_preflight(plan: "BuildPlan", source: Path, progress) -> None:
    """b776-ai2: refuse a source whose CPU AI sites are foreign or carry a different selection, before any write."""
    reads, ball = _core_module("nfl2k5_cpu_qb_reads"), _core_module("nfl2k5_db_ball_play")
    if (plan.cpu_qb_zone_windows or plan.cpu_qb_recheck) and reads is None or plan.db_ball_play and ball is None:
        raise ValueError("The CPU AI options are not available in this installation.")
    progress("Checking the CPU passing and coverage code for the CPU AI options", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The CPU AI options cannot read default.xbe: {exc}") from exc
    if plan.cpu_qb_zone_windows or plan.cpu_qb_recheck:
        settings = reads.read_settings(payload)
        wanted = (plan.cpu_qb_zone_windows, plan.cpu_qb_recheck)
        if settings["status"] == "foreign" or (settings["status"] == "applied"
                                               and (settings["zone_windows"], settings["recheck"]) != wanted):
            raise ValueError("The CPU quarterback code in this source is not retail or this selection of the CPU QB "
                             "options. Turn them off or rebuild from a supported USA source.")
    if plan.db_ball_play and ball.status(payload) == "foreign":
        raise ValueError("The pass-reaction code in this source is not retail or Defenders break on the thrown ball. "
                         "Turn it off or rebuild from a supported USA source.")


def _apply_cpu_ai(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b776-ai2: install the selected CPU AI owners on the built default.xbe and read them back."""
    reads, ball = _core_module("nfl2k5_cpu_qb_reads"), _core_module("nfl2k5_db_ball_play")
    progress("CPU AI: quarterback reads and defenders playing the ball", 0, 0)
    payload = _xbe_bytes(target)
    if plan.cpu_qb_zone_windows or plan.cpu_qb_recheck:
        payload, qb_receipt = reads.apply(payload, zone_windows=plan.cpu_qb_zone_windows, recheck=plan.cpu_qb_recheck)
        receipt["steps"].append({"step": "cpu_qb_reads", **{k: v for k, v in qb_receipt.items() if k != "reservations"}})
    if plan.db_ball_play:
        payload, ball_receipt = ball.apply(payload)
        receipt["steps"].append({"step": "db_ball_play", **{k: v for k, v in ball_receipt.items() if k != "reservations"}})
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload:
        raise RuntimeError("CPU AI: the written default.xbe does not read back")
    if plan.cpu_qb_zone_windows or plan.cpu_qb_recheck:
        settings = reads.read_settings(final)
        if (settings["status"], settings.get("zone_windows"), settings.get("recheck")) != (
                "applied", plan.cpu_qb_zone_windows, plan.cpu_qb_recheck):
            raise RuntimeError("CPU QB reads: the output does not read back as the selected options")
        receipt["result"]["cpu_qb_zone_windows"] = "applied" if plan.cpu_qb_zone_windows else "retail"
        receipt["result"]["cpu_qb_recheck"] = "applied" if plan.cpu_qb_recheck else "retail"
    if plan.db_ball_play:
        if ball.status(final) != "applied":
            raise RuntimeError("Defenders break on the thrown ball: the output does not read back as applied")
        receipt["result"]["db_ball_play"] = "applied"


def _qb_accuracy_preflight(source: Path, progress) -> None:
    """b777-qb3: refuse a source whose pass accuracy routine is foreign, before any write."""
    accuracy = _core_module("nfl2k5_qb_accuracy")
    if accuracy is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Accurate short throws is not available in this installation.")
    progress("Checking the pass accuracy code for accurate short throws", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Accurate short throws cannot read default.xbe: {exc}") from exc
    if accuracy.status(payload) == "foreign":
        raise ValueError("The pass accuracy code in this source is not retail or Accurate short throws. Turn it off or "
                         "rebuild from a supported USA source.")


def _run_blocking_preflight(source: Path, progress) -> None:
    """fx1 (review pr68 nit): refuse a source whose run-blocking sites are foreign, before any write (as qb3 does)."""
    module = _core_module("nfl2k5_run_blocking")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Run blocking is not available in this installation.")
    progress("Checking the blocking code for run blocking", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Run blocking cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The blocking code in this source is not retail or Run blocking. Turn it off or "
                         "build from your unmodified retail dump.")


def _force_out_preflight(source: Path, progress) -> None:
    """b778-fo1: refuse a source whose sideline catch ruling is foreign, before any write (as qb3 does)."""
    module = _core_module("nfl2k5_force_out")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Modern sideline catches is not available in this installation.")
    progress("Checking the sideline catch ruling for modern sideline catches", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Modern sideline catches cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The sideline catch code in this source is not retail or Modern sideline catches. Turn it off "
                         "or build from your unmodified retail dump.")


def _practice_injuries_preflight(source: Path, progress) -> None:
    """b778-pi1: refuse a source whose practice injury handling is foreign, before any write (as fo1 does)."""
    module = _core_module("nfl2k5_practice_injuries")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Franchise practice injuries is not available in this installation.")
    progress("Checking the practice injury handling", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Franchise practice injuries cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The practice injury code in this source is not retail or Franchise practice injuries. Turn "
                         "it off or build from your unmodified retail dump.")
def _draft_clock_preflight(source: Path, progress) -> None:
    """b778-dr1: refuse a source whose franchise draft step is foreign, before any write (as fo1 does)."""
    module = _core_module("nfl2k5_draft_clock")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("The franchise draft clock is not available in this installation.")
    progress("Checking the franchise draft screen for the draft clock", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The franchise draft clock cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The franchise draft code in this source is not retail or the draft clock. Turn it off or "
                         "build from your unmodified retail dump.")


# fx1: plan options that append a late allocator owner (nfl2k5_xbe_space.LATE_OWNERS) to an installed executable.
_LATE_OWNER_OPTIONS = (
    ("nfl2k5_letter_grades", "Letter grades", lambda p: p.letter_grades),
    ("nfl2k5_letter_grades_progress", "Letter grades", lambda p: p.letter_grades),
    ("nfl2k5_honors", "Honors page", lambda p: p.honors_page),
    ("nfl2k5_coach_ai", "Automatic coach AI", lambda p: p.coach_ai),
    ("nfl2k5_moment_coaches", "25 more Anniversary moments", lambda p: p.espn25_more_moments),
    ("nfl2k5_moment_context", "25 more Anniversary moments", lambda p: p.espn25_more_moments),
    ("nfl2k5_team_ratings", "Modern team ratings", lambda p: p.team_ratings),
    ("nfl2k5_classic_teams", "Classic teams", lambda p: p.classic_teams and p.historic_teams_quick_game),
    ("nfl2k5_hair_styles", "Hair styles", lambda p: p.hair_styles),
    ("nfl2k5_cpu_qb_reads", "CPU QB reads", lambda p: p.cpu_qb_zone_windows or p.cpu_qb_recheck),
    ("nfl2k5_db_ball_play", "Defender ball play", lambda p: p.db_ball_play),
    ("nfl2k5_play_art_routes", "Play art: full-length routes", lambda p: p.play_art_routes),
    ("nfl2k5_team_number_scale", "Jersey number sizes", lambda p: bool(p.team_number_scale)),
    ("nfl2k5_run_blocking", "Run blocking", lambda p: p.run_blocking),
    ("nfl2k5_qb_accuracy", "Accurate short throws", lambda p: p.qb_accuracy),
    ("nfl2k5_formation_art_spacing", "Play art: icon spacing", lambda p: p.play_art_routes),  # b777-tp1
    ("nfl2k5_force_out", "Modern sideline catches", lambda p: p.modern_force_out),  # b778-fo1
    ("nfl2k5_module_loader", "On-demand Career Home", lambda p: p.module_loader),  # b778-xs1
    ("nfl2k5_practice_injuries", "Franchise practice injuries", lambda p: p.practice_injuries),  # b778-pi1
    ("nfl2k5_ball_carrier_ai", "CPU ball carriers", lambda p: p.cpu_ball_carriers),  # b778-ai5
    ("nfl2k5_star_retention", "CPU clubs keep their stars", lambda p: p.star_retention),  # b778-fa1
    ("nfl2k5_star_career", "Rookie and career stars", lambda p: p.star_career),  # b778-st2
    ("nfl2k5_draft_clock", "Franchise draft clock", lambda p: p.franchise_draft_clock),  # b778-dr1
    ("nfl2k5_weekly_progression", "Weekly player progression", lambda p: p.weekly_progression),  # b778-pg1
    ("nfl2k5_player_progress_screen", "Player Progress screen", lambda p: p.player_progress or p.player_progress_visible),  # b778-pg2/pg3
    ("nfl2k5_sim_cb_tackles", "Cornerback tackle credit", lambda p: p.sim_cb_tackles),  # b778-cb1
    ("nfl2k5_clock_led", "Modern clock digits", lambda p: p.modern_clock_led),  # b778-sd4
)
_REBUILD_HINT = " Build from your unmodified retail dump instead."



def _star_career_preflight(source: Path, progress) -> None:
    """b778-st2: refuse a source whose class generator, aging loop or overall/stat code is foreign, before any write."""
    module = _core_module("nfl2k5_star_career")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Rookie and career stars is not available in this installation.")
    progress("Checking the draft class generator and offseason code for stars", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Rookie and career stars cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The draft class generator, the Preseason aging loop or the overall/stat code in this source "
                         "is not retail or Rookie and career stars. Turn it off or rebuild from a supported USA source.")


def _ball_carrier_preflight(source: Path, progress) -> None:
    """b778-ai5: refuse a source whose ball-carrier AI code is foreign, before any write."""
    module = _core_module("nfl2k5_ball_carrier_ai")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("CPU ball carriers is not available in this installation.")
    progress("Checking the ball-carrier AI for CPU ball carriers", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"CPU ball carriers cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The ball-carrier AI code in this source is not retail or CPU ball carriers. Turn it off "
                         "or build from your unmodified retail dump.")



def _star_retention_preflight(source: Path, progress) -> None:
    """b778-fa1: refuse a source whose veteran cap cut is foreign, before any write (as fo1 does)."""
    module = _core_module("nfl2k5_star_retention")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("CPU clubs keep their stars is not available in this installation.")
    progress("Checking the CPU veteran cap cut for CPU clubs keep their stars", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"CPU clubs keep their stars cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The CPU veteran cap cut in this source is not retail or CPU clubs keep their stars. Turn it "
                         "off or build from your unmodified retail dump.")





def _alien_prospect_preflight(plan, source: Path, is_image: bool, progress) -> None:
    """b778-ee1: the alien prospect needs rookie faces (his portrait joins its record), a disc image, the art and the
    retail generator, builder and face-record bytes."""
    if not plan.rookie_faces:
        raise ValueError("The alien prospect needs Rookie faces (his draft headshot joins its portrait record). Turn on "
                         "Rookie faces or turn off the alien prospect.")
    if not is_image:
        raise ValueError("The alien prospect adds face files to the disc archive: build from a disc image (.iso).")
    if not _alien_prospect_available():
        raise ValueError("The alien prospect is not available in this installation (its art is missing).")
    module = _core_module("nfl2k5_alien_prospect")
    progress("Checking the draft class generator for the alien prospect", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The alien prospect cannot read default.xbe: {exc}") from exc
    if module.xbe_status(payload) != "retail":
        raise ValueError("The draft class generator or the player builder in this source is not retail (an earlier "
                         "build added the alien prospect or something else changed it)." + _REBUILD_HINT)


def _rookie_faces_preflight(source: Path, is_image: bool, progress) -> None:
    """b778-rh1: rookie faces need a disc image, the bank data and the retail class-generator bytes."""
    if not is_image:
        raise ValueError("Rookie faces adds portrait files to the disc archive: build from a disc image (.iso).")
    if not _rookie_faces_available():
        raise ValueError("Rookie faces is not available in this installation (its face bank is missing).")
    module = _core_module("nfl2k5_rookie_faces")
    progress("Checking the draft class generator for rookie faces", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Rookie faces cannot read default.xbe: {exc}") from exc
    if module.xbe_status(payload) != "retail":
        raise ValueError("The draft class generator in this source is not retail (an earlier build added rookie faces "
                         "or something else changed it)." + _REBUILD_HINT)




def _rebuild_refusals(plan: "BuildPlan", source: Path, is_image: bool, progress) -> None:
    """fx1 (reviews pr67 #4, pr68 #1-#3, #5): refuse, before any write, a source that an earlier Studio build made
    when this release would only refuse it after every step had run. A retail dump never reaches a check: its
    executable is not a sealed scale-out image."""
    space = _core_module("nfl2k5_xbe_space")
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError):
        return
    if space is None or not space.is_scaleout(payload):
        return
    progress("Checking what an earlier build left on this disc", 0, 0)
    if plan.letter_grades:
        grades, attributes = _core_module("nfl2k5_letter_grades"), _core_module("nfl2k5_letter_grades_attributes")
        if (grades is not None and attributes is not None and grades.status(payload) == "applied"
                and attributes.status(payload) == "foreign"):
            raise ValueError("This disc carries an older Letter grades revision (rating screens graded) that this "
                             "release cannot update in place." + _REBUILD_HINT)
    if plan.espn25_named_previews:
        venues = _core_module("nfl2k5_moment_venues")
        if venues is not None and venues.status(payload) in ("previous", "legacy"):
            raise ValueError("This disc carries an older Historical Anniversary venue names revision." + _REBUILD_HINT)
        ball = _core_module("nfl2k5_era_ball")
        if is_image and ball is not None and not ball.enabled() and ball.image_status(source) != "retail":
            raise ValueError("This disc was built with the era ball, which this release no longer installs and "
                             "cannot take out again." + _REBUILD_HINT)
    try:
        _grown, _special, current = space._validate(payload)
        taken = {(owner, kind) for owner, kind, _size, _align in current}
        new, names = [], []
        for owner, label, wanted in _LATE_OWNER_OPTIONS:
            module = _core_module(owner)
            if not wanted(plan) or module is None:
                continue
            rows = [r for r in getattr(module, "REQUESTS", ()) if r[0] == owner and (r[0], r[1]) not in taken]
            if rows:
                new.extend(rows)
                taken.update((r[0], r[1]) for r in rows)
                names.append(label)
        if not new:
            return
        before = space._scale_allocations(current)
        after = space._scale_allocations(space._requests(list(current) + new))
    except (ValueError, KeyError, TypeError, AttributeError):
        return  # the owners' own checks report anything else, as before
    moved = sorted({row["owner"] for row in before if row not in after and row["owner"] != space.DIRECTORY_OWNER})
    if moved:
        raise ValueError(f"This disc was built earlier without {', '.join(dict.fromkeys(names))}; adding it now "
                         f"would move code an earlier build placed ({', '.join(moved)})." + _REBUILD_HINT)


def _apply_qb_accuracy(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b777-qb3: install the QB accuracy owner, the last late allocator owner, and read it back."""
    if not plan.qb_accuracy:
        return
    accuracy = _core_module("nfl2k5_qb_accuracy")
    if accuracy is None:
        raise RuntimeError("Accurate short throws needs nfl2k5_qb_accuracy.")
    progress("Passing: accurate short throws and throws on the run", 0, 0)
    payload, accuracy_receipt = accuracy.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or accuracy.status(final) != "applied":
        raise RuntimeError("Accurate short throws: the output does not read back as applied")
    receipt["steps"].append({"step": "qb_accuracy", **{k: v for k, v in accuracy_receipt.items() if k != "reservations"}})
    receipt["result"]["qb_accuracy"] = "applied"


def _apply_formation_art_spacing(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b777-tp1: the play-call formation art icon spacing owner (part of the play art option), the last late
    allocator owner; only how the diagrams draw the icons changes."""
    if not plan.play_art_routes:
        return
    module = _core_module("nfl2k5_formation_art_spacing")
    if module is None:
        raise RuntimeError("Play art icon spacing needs nfl2k5_formation_art_spacing.")
    progress("Play art: spacing the formation icons", 0, 0)
    payload, spacing_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Play art icon spacing: the output does not read back as applied")
    receipt["steps"].append({"step": "formation_art_spacing", **{k: v for k, v in spacing_receipt.items()
                                                                 if k not in ("reservations", "edits")}})
    receipt["result"]["formation_art_spacing"] = "applied"


def _apply_inbox_standings(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    if not plan.inbox_standings:
        return
    module = _core_module("nfl2k5_inbox_standings")
    if module is None:
        raise RuntimeError("Inbox standings needs nfl2k5_inbox_standings.")
    progress("Repairing the inbox standings table", 0, 0)
    patched, detail = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, patched)
    if module.status(_xbe_bytes(target)) != "applied":
        raise RuntimeError("Inbox standings did not read back as applied")
    receipt["steps"].append({"step": "inbox_standings", **detail})
    receipt["result"]["inbox_standings"] = "applied"


def _apply_force_out(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-fo1: the modern sideline catch owner (no force-out from 2008), a late allocator owner."""
    if not plan.modern_force_out:
        return
    module = _core_module("nfl2k5_force_out")
    if module is None:
        raise RuntimeError("Modern sideline catches needs nfl2k5_force_out.")
    progress("Rules: modern sideline catches (no force-out)", 0, 0)
    payload, force_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Modern sideline catches: the output does not read back as applied")
    receipt["steps"].append({"step": "modern_force_out", **{k: v for k, v in force_receipt.items() if k != "reservations"}})
    receipt["result"]["modern_force_out"] = "applied"


def _apply_practice_injuries(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-pi1: franchise practice keeps injuries, the last late allocator owner."""
    if not plan.practice_injuries:
        return
    module = _core_module("nfl2k5_practice_injuries")
    if module is None:
        raise RuntimeError("Franchise practice injuries needs nfl2k5_practice_injuries.")
    progress("Franchise: injured players sit out of practice", 0, 0)
    payload, injury_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Franchise practice injuries: the output does not read back as applied")
    receipt["steps"].append({"step": "practice_injuries", **{k: v for k, v in injury_receipt.items() if k != "reservations"}})
    receipt["result"]["practice_injuries"] = "applied"


def _apply_ball_carriers(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-ai5: CPU ball carriers stay in bounds / QBs slide past the sticks, the last late allocator owner."""
    if not plan.cpu_ball_carriers:
        return
    module = _core_module("nfl2k5_ball_carrier_ai")
    if module is None:
        raise RuntimeError("CPU ball carriers needs nfl2k5_ball_carrier_ai.")
    progress("CPU AI: ball carriers stay in bounds, QBs slide past the sticks", 0, 0)
    payload, carrier_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("CPU ball carriers: the output does not read back as applied")
    receipt["steps"].append({"step": "cpu_ball_carriers", **{k: v for k, v in carrier_receipt.items() if k != "reservations"}})
    receipt["result"]["cpu_ball_carriers"] = "applied"



def _apply_star_retention(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-fa1: CPU clubs keep their stars (veteran cap cut), the last late allocator owner."""
    if not plan.star_retention:
        return
    module = _core_module("nfl2k5_star_retention")
    if module is None:
        raise RuntimeError("CPU clubs keep their stars needs nfl2k5_star_retention.")
    progress("Franchise: CPU clubs keep their stars", 0, 0)
    payload, star_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("CPU clubs keep their stars: the output does not read back as applied")
    receipt["steps"].append({"step": "star_retention", **{k: v for k, v in star_receipt.items() if k != "reservations"}})
    receipt["result"]["star_retention"] = "applied"


def _apply_star_career(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-st2: the rookie/career star owner, after the last b778 late owner (nfl2k5_star_career)."""
    if not plan.star_career:
        return
    module = _core_module("nfl2k5_star_career")
    if module is None:
        raise RuntimeError("Rookie and career stars needs nfl2k5_star_career.")
    progress("Stars: rookie classes and career gains and losses", 0, 0)
    payload, star_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Rookie and career stars: the output does not read back as applied")
    receipt["steps"].append({"step": "star_career", **{k: v for k, v in star_receipt.items() if k != "reservations"}})
    receipt["result"]["star_career"] = "applied"


def _apply_crib_trophy_room(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-xs1: the Crib keeps the Trophy Room side; its shop is cut (in-place edits, no allocation)."""
    if not plan.crib_trophy_room:
        return
    module = _core_module("nfl2k5_crib_trophy_room")
    if module is None:
        raise RuntimeError("The Crib Trophy Room cut needs nfl2k5_crib_trophy_room.")
    progress("The Crib: Trophy Room only", 0, 0)
    payload, crib_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("The Crib Trophy Room cut: the output does not read back as applied")
    receipt["steps"].append({"step": "crib_trophy_room", **crib_receipt})
    receipt["result"]["crib_trophy_room"] = "applied"


def _apply_module_loader(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-xs1: the on-demand Career Home prototype, after Career Home and every other late allocator owner."""
    if not plan.module_loader:
        return
    module = _core_module("nfl2k5_module_loader")
    if module is None:
        raise RuntimeError("On-demand Career Home needs nfl2k5_module_loader.")
    progress("MyCareer: Career Home loaded on demand (experimental)", 0, 0)
    payload, loader_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("On-demand Career Home: the output does not read back as applied")
    receipt["steps"].append({"step": "module_loader", **loader_receipt})
    receipt["result"]["module_loader"] = "applied"
def _sportscenter_lineup_preflight(source: Path, progress) -> None:
    module = _core_module("nfl2k5_sportscenter_lineup")
    if module is None:
        raise ValueError("SportsCenter highlight lineups is unavailable in this installation.")
    progress("Checking SportsCenter highlight lineups", 0, 0)
    if module.status(_xbe_bytes(source)) == "foreign":
        raise ValueError("Foreign SportsCenter lineup code. Turn this option off or use an unmodified USA source.")


def _apply_sportscenter_lineup(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    if not plan.sportscenter_lineup:
        return
    module = _core_module("nfl2k5_sportscenter_lineup")
    if module is None:
        raise RuntimeError("SportsCenter highlight lineups needs nfl2k5_sportscenter_lineup.")
    progress("Repairing SportsCenter highlight lineups", 0, 0)
    payload, step = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    if _xbe_bytes(target) != payload or module.status(payload) != "applied":
        raise RuntimeError("SportsCenter highlight lineup output failed verification")
    receipt["steps"].append({"step": "sportscenter_lineup", **step})
    receipt["result"]["sportscenter_lineup"] = "applied"
def _apply_draft_clock(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-dr1: the broadcast-paced franchise draft, the last late allocator owner."""
    if not plan.franchise_draft_clock:
        return
    module = _core_module("nfl2k5_draft_clock")
    if module is None:
        raise RuntimeError("The franchise draft clock needs nfl2k5_draft_clock.")
    progress("Franchise: draft on a broadcast clock", 0, 0)
    payload, clock_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("The franchise draft clock: the output does not read back as applied")
    receipt["steps"].append({"step": "franchise_draft_clock", **{k: v for k, v in clock_receipt.items() if k != "reservations"}})
    receipt["result"]["franchise_draft_clock"] = "applied"
def _weekly_progression_preflight(source: Path, progress) -> None:
    """b778-pg1: refuse a source whose post-game merge call is foreign, before any write (as fo1 does)."""
    module = _core_module("nfl2k5_weekly_progression")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Weekly player progression is not available in this installation.")
    progress("Checking the post-game stat merge for weekly progression", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Weekly player progression cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The post-game stat merge in this source is not retail or Weekly player progression. Turn it "
                         "off or build from your unmodified retail dump.")


def _apply_weekly_progression(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-pg1: franchise in-season weekly progression, the last late allocator owner."""
    if not plan.weekly_progression:
        return
    module = _core_module("nfl2k5_weekly_progression")
    if module is None:
        raise RuntimeError("Weekly player progression needs nfl2k5_weekly_progression.")
    progress("Franchise: weekly player progression", 0, 0)
    payload, weekly_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Weekly player progression: the output does not read back as applied")
    receipt["steps"].append({"step": "weekly_progression", **{k: v for k, v in weekly_receipt.items() if k != "reservations"}})
    receipt["result"]["weekly_progression"] = "applied"
def _player_progress_preflight(source: Path, progress) -> None:
    """b778-pg2: refuse a source whose Player Progress bytes are foreign, before any write."""
    module = _core_module("nfl2k5_player_progress_screen")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("The Player Progress screen is not available in this installation.")
    progress("Checking the Player Progress screen bytes", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The Player Progress screen cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The Player Progress screen bytes in this source are not retail or this owner. Turn it off "
                         "or build from your unmodified retail dump.")


def _apply_player_progress(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-pg2/pg3: install the Player Progress owner (full snapshot or visibility-only)."""
    if not (plan.player_progress or plan.player_progress_visible):
        return
    module = _core_module("nfl2k5_player_progress_screen")
    if module is None:
        raise RuntimeError("The Player Progress screen needs nfl2k5_player_progress_screen.")
    visible_only = not plan.player_progress
    progress("Franchise: Player Progress row" if visible_only else "Franchise: Player Progress screen", 0, 0)
    payload, progress_receipt = module.apply(_xbe_bytes(target), visible_only=visible_only)
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    expected = "visible" if visible_only else "applied"
    if final != payload or module.status(final) != expected:
        raise RuntimeError(f"The Player Progress screen: the output does not read back as {expected}")
    receipt["steps"].append({"step": "player_progress", **{k: v for k, v in progress_receipt.items()
                                                            if k not in ("reservations", "edits")}})
    receipt["result"]["player_progress"] = expected
def _apply_contract_college_guard(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-cr1: the Player Contracts null-college screen guard, after every other late owner."""
    if not plan.contract_college_guard:
        return
    module = _core_module("nfl2k5_contract_college_guard")
    if module is None:
        raise RuntimeError("The Player Contracts college guard needs nfl2k5_contract_college_guard.")
    progress("Screens: Player Contracts null-college guard", 0, 0)
    payload, guard_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("The Player Contracts college guard: the output does not read back as applied")
    receipt["steps"].append({"step": "contract_college_guard", **{k: v for k, v in guard_receipt.items() if k != "reservations"}})
    receipt["result"]["contract_college_guard"] = "applied"
def _apply_sim_cb_tackles(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-cb1: the cornerback tackle credit owner, the last late allocator owner."""
    if not plan.sim_cb_tackles:
        return
    module = _core_module("nfl2k5_sim_cb_tackles")
    if module is None:
        raise RuntimeError("Cornerback tackle credit needs nfl2k5_sim_cb_tackles.")
    progress("Stats: cornerback tackle credit", 0, 0)
    payload, cb_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Cornerback tackle credit: the output does not read back as applied")
    receipt["steps"].append({"step": "sim_cb_tackles", **{k: v for k, v in cb_receipt.items() if k != "reservations"}})
    receipt["result"]["sim_cb_tackles"] = "applied"
def _sim_stats_preflight(source: Path, progress) -> None:
    """b778-sim1: refuse a source whose simulator initializer is foreign, before any write."""
    module = _core_module("nfl2k5_sim_stats")
    if module is None:
        raise ValueError("The franchise sim pace fix is not available in this installation.")
    progress("Checking the franchise simulator for the NFL pace fix", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"The franchise sim pace fix cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The franchise simulator in this source is not retail or the NFL pace fix. Turn it off or "
                         "rebuild from a supported USA source.")
def _apply_sim_stats(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-sim1: normalise the simulated game's clock pace (in place, no allocator request)."""
    if not plan.sim_stats:
        return
    module = _core_module("nfl2k5_sim_stats")
    if module is None:
        raise RuntimeError("The franchise sim pace fix needs nfl2k5_sim_stats.")
    progress("Stats: franchise simulated-game pace", 0, 0)
    payload, sim_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("The franchise sim pace fix: the output does not read back as applied")
    receipt["steps"].append({"step": "sim_stats", **{k: v for k, v in sim_receipt.items()
                                                    if k not in ("reservations", "edits")},
                             "edits": sim_receipt.get("edits", [])})
    receipt["result"]["sim_stats"] = "applied"
def _clock_led_preflight(source: Path, progress) -> None:
    """b778-sd4: refuse a source whose stadium-loader clock-font loop is foreign, before any write."""
    module = _core_module("nfl2k5_clock_led")
    if module is None or _core_module("nfl2k5_xbe_space") is None:
        raise ValueError("Modern clock digits are not available in this installation.")
    progress("Checking the clock-font loader for modern clock digits", 0, 0)
    try:
        payload = _xbe_bytes(source)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Modern clock digits cannot read default.xbe: {exc}") from exc
    if module.status(payload) == "foreign":
        raise ValueError("The clock-font loader in this source is not retail or Modern clock digits. Turn it off "
                         "or build from your unmodified retail dump.")


def _apply_clock_led(plan: "BuildPlan", target: Path, receipt: dict, progress) -> None:
    """b778-sd4: the modern LED clock digits owner, after modern sideline catches in the late-owner order."""
    if not plan.modern_clock_led:
        return
    module = _core_module("nfl2k5_clock_led")
    if module is None:
        raise RuntimeError("Modern clock digits need nfl2k5_clock_led.")
    progress("Presentation: modern LED clock digits", 0, 0)
    payload, led_receipt = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, payload)
    final = _xbe_bytes(target)
    if final != payload or module.status(final) != "applied":
        raise RuntimeError("Modern clock digits: the output does not read back as applied")
    receipt["steps"].append({"step": "modern_clock_led", **{k: v for k, v in led_receipt.items() if k != "reservations"}})
    receipt["result"]["modern_clock_led"] = "applied"


def _hair_styles_available() -> bool:  # b775-hs1
    module = _core_module("nfl2k5_hair_styles")
    return module is not None and module.available()  # the geometry, art, pointer census and pins must agree


def _rookie_faces_available() -> bool:  # b778-rh1
    module = _core_module("nfl2k5_rookie_faces")
    return (module is not None and module.BANK_JSON.is_file() and module.NAMES_JSON.is_file()
            and _core_module("nfl2k5_historic_styles") is not None)


def _alien_prospect_available() -> bool:  # b778-ee1
    module = _core_module("nfl2k5_alien_prospect")
    return module is not None and module.available() and _rookie_faces_available()


def _modern_coaches_available() -> bool:  # b77-co1
    module = _core_module("nfl2k5_modern_coaches")
    return module is not None and module.available()  # the pins and the shipped art must agree


def _modern_fans_available() -> bool:  # b77-fr1
    module = _core_module("nfl2k5_modern_fans")
    return module is not None and module.available()  # the pins and the shipped art must agree


def _modern_officials_available() -> bool:  # b77-rf1
    module = _core_module("nfl2k5_modern_officials")
    return module is not None and module.available()  # the pins and the shipped art must agree


def _modern_goalposts_available() -> bool:  # b77-v1
    module = _core_module("nfl2k5_modern_goalposts")
    return module is not None and module.available()  # the shipped pins must load


def availability(official_marks_pack=None) -> dict[str, bool]:
    """Which optional patch modules are present in this build."""

    return {
        "throw": True, "catch_slider": True, "accel_ramp": True, "draft_ai": True,
        "helmet_finish": _core_module("nfl2k5_helmet_finish") is not None,
        "weather_plan": _core_module("nfl2k5_weather") is not None,
        "weather_haze": _core_module("nfl2k5_weather_haze") is not None,
        "number_kerning": _core_module("nfl2k5_number_kerning") is not None,  # b76-k2
        "modern_color": _core_module("nfl2k5_modern_color") is not None,
        "modern_arrowhead": _core_module("nfl2k5_modern_arrowhead") is not None,
        "modern_metlife": _core_module("nfl2k5_modern_metlife") is not None,
        "modern_venues_2026": _core_module("nfl2k5_modern_venues_2026") is not None,  # b76-u4
        "modern_metlife_model": _core_module("nfl2k5_metlife_model") is not None,
        "modern_helmets": _core_module("nfl2k5_modern_helmets") is not None,  # b76-hm
        "modern_sofi": _core_module("nfl2k5_sofi_model") is not None,  # b76-u6
        "modern_highmark": _core_module("nfl2k5_highmark_model") is not None,  # b76-st
        "modern_att": _core_module("nfl2k5_att_model") is not None,  # b76-st2
        "modern_levis": _core_module("nfl2k5_levis_model") is not None,  # b76-st2
        "modern_allegiant": _core_module("nfl2k5_allegiant_model") is not None,  # b76-st2
        "modern_mercedes_benz": _core_module("nfl2k5_mercedes_benz_model") is not None,  # b76-st2
        "modern_usbank": _core_module("nfl2k5_usbank_model") is not None,  # b76-st3
        "modern_lucas_oil": _core_module("nfl2k5_lucas_oil_model") is not None,  # b76-st3
        "modern_state_farm": _core_module("nfl2k5_state_farm_model") is not None,  # b76-st3
        "modern_hard_rock": _core_module("nfl2k5_hard_rock_model") is not None,  # b76-st4
        "modern_gillette": _core_module("nfl2k5_gillette_model") is not None,  # b76-st4
        "modern_lambeau": _core_module("nfl2k5_lambeau_model") is not None,  # b76-st4
        "modern_everbank": _core_module("nfl2k5_everbank_model") is not None,  # b76-st4
        "modern_everbank_construction": _core_module("nfl2k5_everbank_model") is not None,  # b76-st4
        "modern_board_kit": _core_module("nfl2k5_board_kit") is not None,  # b76-st5
        "modern_practice_field": _core_module("nfl2k5_practice_field_model") is not None,  # b76-pf
        "modern_practice_field_team_logo": (_core_module("nfl2k5_practice_field_model") is not None
                                            and _core_module("nfl2k5_team_logo_swap") is not None),  # b76-pf P1
        "modern_surfaces": _core_module("nfl2k5_modern_surfaces") is not None,  # b76-tf
        "espn_marks_2026": _espn_marks_available(official_marks_pack),
        "espn_wipes_boards_2026": _espn_wipes_boards_available(official_marks_pack),  # b76-p2
        "kick_meter_2026": _kick_meter_available(),  # b76-km
        "modern_goalposts": _modern_goalposts_available(),  # b77-v1
        "modern_coaches": _modern_coaches_available(),  # b77-co1
        "rookie_faces": _rookie_faces_available(),  # b778-rh1
        "alien_prospect": _alien_prospect_available(),  # b778-ee1
        "hair_styles": _hair_styles_available(),  # b775-hs1
        # b776-ai2: the CPU AI owners need only their modules and the allocator
        **{key: _core_module(module) is not None and _core_module("nfl2k5_xbe_space") is not None
           for key, module in (("cpu_qb_zone_windows", "nfl2k5_cpu_qb_reads"), ("cpu_qb_recheck", "nfl2k5_cpu_qb_reads"),
                               ("db_ball_play", "nfl2k5_db_ball_play"), ("qb_accuracy", "nfl2k5_qb_accuracy"))},
        "team_number_scale": _core_module("nfl2k5_team_number_scale") is not None
                             and _core_module("nfl2k5_xbe_space") is not None,  # b776-ns1
        "modern_fans": _modern_fans_available(),  # b77-fr1
        "modern_officials": _modern_officials_available(),  # b77-rf1
        **{key: _core_module(module) is not None and _core_module("nfl2k5_xbe_space") is not None
           for key, module in (("momentum", "nfl2k5_momentum"), ("momentum_contact", "nfl2k5_momentum"),
                               ("momentum_collisions", "nfl2k5_momentum"),
                               ("read_option_runtime", "nfl2k5_read_option_runtime"),
                               ("guardian_overlay", "nfl2k5_guardian_resources"),
                               ("my_career", "nfl2k5_my_career"),
                               ("my_career_home", "nfl2k5_my_career_home"),
                               ("franchise_autosave", "nfl2k5_franchise_autosave"),
                               ("screen_hooks", "nfl2k5_screen_hooks"),
                               ("coverage_trail", "nfl2k5_coverage_trail"),
                               ("franchise_edit_player", "nfl2k5_franchise_edit_player"),
                               ("cpu_money_downs", "nfl2k5_cpu_money_downs"),
                               ("accelerated_clock", "nfl2k5_accelerated_clock"),
                               ("coin_defer", "nfl2k5_coin_defer"),
                               ("decided_clock", "nfl2k5_decided_clock"),
                               ("cpu_scrambles", "nfl2k5_cpu_scrambles"),
                               ("historic_teams_quick_game", "nfl2k5_historic_teams_quick_game"),
                               ("kickoff_return_blocking", "nfl2k5_kickoff_blocking"),
                               ("espn25_more_moments", "nfl2k5_espn25_more_moments"),
                               ("historic_stock_books", "nfl2k5_stock_books"),
                               ("espn25_era_rules", "nfl2k5_era_rules"),
                               ("k128_memory", "nfl2k5_k128"), ("k128_roster_heap", "nfl2k5_k128"), ("k128_early", "nfl2k5_k128"),
                               ("team_ratings", "nfl2k5_team_ratings"),
                               ("play_art_routes", "nfl2k5_play_art_routes"),  # b776-pa2
                               ("run_blocking", "nfl2k5_run_blocking"),  # b777-ol1
                               ("modern_force_out", "nfl2k5_force_out"),  # b778-fo1
                               ("module_loader", "nfl2k5_module_loader"),  # b778-xs1
                               ("crib_trophy_room", "nfl2k5_crib_trophy_room"),  # b778-xs1
                               ("inbox_standings", "nfl2k5_inbox_standings"),  # b778-pc3; no allocation
                               ("star_retention", "nfl2k5_star_retention"),  # b778-fa1
                               ("practice_injuries", "nfl2k5_practice_injuries"),  # b778-pi1
                               ("cpu_ball_carriers", "nfl2k5_ball_carrier_ai"),  # b778-ai5
                               ("sportscenter_lineup", "nfl2k5_sportscenter_lineup"),
                               ("franchise_draft_clock", "nfl2k5_draft_clock"),  # b778-dr1
                               ("weekly_progression", "nfl2k5_weekly_progression"),  # b778-pg1
                               ("player_progress", "nfl2k5_player_progress_screen"),  # b778-pg2
                               ("contract_college_guard", "nfl2k5_contract_college_guard"),  # b778-cr1
                               ("sim_cb_tackles", "nfl2k5_sim_cb_tackles"),  # b778-cb1
                               ("modern_clock_led", "nfl2k5_clock_led"),  # b778-sd4
                               ("letter_grades", "nfl2k5_letter_grades"),
                               ("honors_page", "nfl2k5_honors"), ("honors_history", "nfl2k5_honors_history"),
                               ("weekly_prep", "nfl2k5_weekly_prep"), ("weekly_prep_cpu", "nfl2k5_weekly_prep"), ("weekly_prep_remember", "nfl2k5_weekly_prep"),
                               ("coach_ai", "nfl2k5_coach_ai"),
                               ("playbook_pair", "nfl2k5_playbook_pair"),
                               ("deep_zone_facing", "nfl2k5_deep_zone"), ("deep_zone_bail", "nfl2k5_deep_zone"),
                               ("reserves_16", "nfl2k5_roster_arena_image"),
                               ("created_teams_extra", "nfl2k5_roster_arena_image"),
                               ("defensive_try", "nfl2k5_defensive_try"), ("zone_drop_cap", "nfl2k5_zone_drop"), ("all_stadiums", "nfl2k5_roster_storage"),
                               ("coverage_slider", "nfl2k5_coverage_slider"), ("scramble_tuning", "nfl2k5_scramble_tuning"),
                               ("music_shuffle", "nfl2k5_music_playlist"), ("practice_squad_screen", "nfl2k5_practice_squad_screen"),
                               ("abilities", "nfl2k5_abilities_runtime"), ("qb_spy", "nfl2k5_qb_spy_runtime"),
                               ("calendar_engine", "nfl2k5_calendar_engine"))},
        "sim_stats": _core_module("nfl2k5_sim_stats") is not None,  # b778-sim1; in place, no allocator
        "franchise_2026_rules": bool(tt.franchise_2026_patch.RUNTIME_READY),
        "senior_bowl": bool(tt.senior_bowl_patch.NATIVE_EVENT_AVAILABLE),
        "trim_intro_videos": _core_module("nfl2k5_intro_videos") is not None,
        "custom_intro": (_core_module("nfl2k5_custom_intro") is not None
                         and _core_module("nfl2k5_sofdec") is not None),
        "crib_reclaim": _core_module("nfl2k5_crib_reclaim") is not None,
        "modern_naming": tt.modern_naming_patch.all_strings_fit(),
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
        "flatter_deep_ball": _core_module("nfl2k5_throw_arc") is not None,
        "chop_block_toggle": _core_module("nfl2k5_penalties") is not None,
        "hires_pack": all(_core_module(name) is not None for name in (
            "nfl2k5_hires_pack", "nfl2k5_hires_texture", "nfl2k5_music_archive", "nfl2k5_music_banks",
            "nfl2k5_hires_layouts", "nfl2k5_hires_catalog", "nfl2k5_hires_budget", "nfl2k5_hires_evidence")),
        "team_names_2026": _team_names_available(),
        "season_cap": all(_core_module(name) is not None for name in ("nfl2k5_season_cap", "nfl2k5_calendar_engine", "nfl2k5_xbe_space")),
        "returner_fix": _core_module("nfl2k5_returner_fix") is not None,
        "progression": _core_module("nfl2k5_progression") is not None,
        "franchise_economy": _core_module("nfl2k5_franchise_economy") is not None,
        "scheme_labels": _core_module("nfl2k5_modern_positions") is not None,
        "camera": _core_module("nfl2k5_camera") is not None,
        "kick_rules": _core_module("nfl2k5_kick_rules") is not None,
        "kickoff_alignment": _tools_module("nfl2k5_kickoff_alignment") is not None,
        "dynamic_kickoff": (_core_module("nfl2k5_dynamic_kickoff") is not None and _core_module("nfl2k5_kick_rules") is not None
                            and _tools_module("nfl2k5_kickoff_alignment") is not None
                            and _tools_module("nfl2k5_kickoff_returns") is not None),
        "widescreen": _core_module("nfl2k5_widescreen") is not None,
        "overtime": _core_module("nfl2k5_overtime") is not None,
        "team_history": (_core_module("nfl2k5_team_history") is not None
                         and (ROOT / "data" / "nfl2k5_retail_team_history.csv").exists()),
        "career_stats": _core_module("nfl2k5_career_stats") is not None,
        "team_column": _core_module("nfl2k5_team_column") is not None,
        "position_row": _core_module("nfl2k5_position_row") is not None,
        "probowl_order": _core_module("nfl2k5_probowl_order") is not None,
        "elbow_options": _core_module("nfl2k5_elbow_options") is not None,
        "the1wam_lineman_rating": _core_module("nfl2k5_lineman_rating") is not None,
        "xemu_display_list_fix": _core_module("nfl2k5_display_list_stability") is not None,
        "resource_load_guard": _core_module("nfl2k5_resource_load_guard") is not None,
        "loader_wakeup_fix": _core_module("nfl2k5_loader_wakeup") is not None,
        "rb_rename": _core_module("nfl2k5_rb_rename") is not None,
        "trophy_room": _core_module("nfl2k5_trophy_room") is not None,
        "name_keyboard": _core_module("nfl2k5_name_keyboard") is not None,
        "penalties": _core_module("nfl2k5_penalties") is not None,
        "uniform_choice": _core_module("nfl2k5_uniform_choice") is not None,
        "team_sleeves": _core_module("nfl2k5_team_sleeves") is not None,
        "kick_laces": _core_module("nfl2k5_kick_laces") is not None,
        "punter_holder": _core_module("nfl2k5_punter_holder") is not None,
        "franchise_practice": _core_module("nfl2k5_franchise_practice") is not None,
        "practice_squad": _core_module("nfl2k5_practice_squad") is not None,
        "depth_locks": _core_module("nfl2k5_depth_locks") is not None,
        "prospect_names": (_core_module("nfl2k5_prospect_names") is not None
                           and (ROOT / "data" / "nfl2k5_modern_names.csv").exists()),
        "player_star": _core_module("nfl2k5_player_star") is not None,
        "player_tags": _core_module("nfl2k5_player_tags") is not None,
        "star_career": _core_module("nfl2k5_star_career") is not None,  # b778-st2
        "roster_edits": _core_module("nfl2k5_roster_records") is not None,
        # the plan-dependent status function is never called without a selected plan; Build probes
        # the image with Catalog.load and reports available / foreign (a bare XBE: requires image)
        "espn25_plan": _core_module("nfl2k5_espn25_scenarios") is not None,
        "espn25_rosters": _espn25_rosters_available(),
        "historic_rosters_2026": _core_module("nfl2k5_historic_rosters") is not None,
        "classic_teams": _core_module("nfl2k5_classic_teams") is not None,  # b775-ct1
        "seven_on_seven": (SEVEN_ON_SEVEN_RELEASED
                           and _core_module("nfl2k5_seven_on_seven") is not None
                           and _core_module("nfl2k5_seven_on_seven_book") is not None),
        "season_2026": (_core_module("nfl2k5_season_length") is not None
                        and _core_module("nfl2k5_trade_deadline") is not None
                        and _tools_module("nfl2k5_franchise_schedule") is not None
                        and (ROOT / "data" / "nfl_2026_schedule.json").exists()),
        "position_pools": (_core_module("nfl2k5_position_pools") is not None
                           and _tools_module("nfl2k5_playbook_position_recode") is not None
                           and _tools_module("nfl2k5_roster_reclassify") is not None
                           and callable(getattr(_tools_module("nfl2k5_roster_reclassify"), "olb_filter_policy", None))),
        "position_pools_keep_olb": (_core_module("nfl2k5_position_pools") is not None
                                    and callable(getattr(_tools_module("nfl2k5_roster_reclassify"), "olb_filter_policy", None))),
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
                     and _core_module("nfl2k5_scorebar_v3") is not None
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
        "franchise_economy": report.get("franchise_economy", "unknown"),
        "scheme_labels": report.get("scheme_labels", "unknown"), "camera": report.get("camera", "unknown"),
        "kick_rules": report.get("kick_rules", "unknown"), "dynamic_kickoff": report.get("dynamic_kickoff", "unknown"), "dynamic_kickoff_settings": report.get("dynamic_kickoff_settings"), "playoff_picture": report.get("playoff_picture", "unknown"), "depth_chart_rows": report.get("depth_chart_rows", "unknown"), "kick_power": report.get("kick_power", "unknown"), "widescreen": report.get("widescreen", "unknown"),
        "overtime": report.get("overtime", "unknown"), "team_column": report.get("team_column", "unknown"),
        "position_row": report.get("position_row", "unknown"), "probowl_order": report.get("probowl_order", "unknown"),
        "elbow_options": report.get("elbow_options", "unknown"),
        "the1wam_lineman_rating": report.get("the1wam_lineman_rating", "unknown"),
        "xemu_display_list_fix": report.get("xemu_display_list_fix", "unknown"),
        "resource_load_guard": report.get("resource_load_guard", "unknown"),
        "loader_wakeup_fix": report.get("loader_wakeup_fix", "unknown"),
        "rb_rename": report.get("rb_rename", "unknown"),
        "trophy_room": report.get("trophy_room", "unknown"),
        "name_keyboard": report.get("name_keyboard", "unknown"),
        "penalties": report.get("penalties", "unknown"),
        "uniform_choice": report.get("uniform_choice", "unknown"),
        "uniform_choice_mode": report.get("uniform_choice_mode"),
        "kick_laces": report.get("kick_laces", "unknown"),
        "punter_holder": report.get("punter_holder", "unknown"),
        "franchise_practice": report.get("franchise_practice", "unknown"),
        "practice_squad": report.get("practice_squad", "unknown"),
        "practice_reserves": report.get("practice_reserves", "unknown"),
        "depth_locks": report.get("depth_locks", "unknown"),
        "season_cap": report.get("season_cap", "unknown"),
        "modern_practice_field_team_logo": report.get("team_logo_swap", "unknown"),  # b76-pf P1: the executable's table
        **{key: report.get(key, "unknown") for key in
           ("momentum", "momentum_contact", "momentum_collisions", "momentum_settings",
            "read_option_runtime", "read_option_runtime_settings", "screen_hooks", "screen_hooks_settings", "coverage_trail", "franchise_edit_player", "cpu_money_downs", "cpu_money_downs_settings", "accelerated_clock", "accelerated_clock_settings", "coin_defer", "coin_defer_settings", "decided_clock", "decided_clock_settings", "cpu_scrambles", "cpu_scrambles_settings", "weekly_prep", "weekly_prep_cpu", "weekly_prep_remember", "weekly_prep_settings", "coach_ai", "playbook_pair", "deep_zone_facing", "deep_zone_bail", "deep_zone_settings",
            "guardian_overlay", "guardian_overlay_settings", "guardian_overlay_resources",
            "franchise_2026_rules", "franchise_2026_kernel", "franchise_2026_runtime_enforced",
            "senior_bowl", "senior_bowl_native_available", "my_career", "crib_reclaim", "franchise_autosave",
            "historic_teams_quick_game", "kickoff_return_blocking", "espn25_more_moments", "historic_stock_books", "espn25_named_previews", "espn25_era_rules", "k128_memory", "k128_roster_heap", "k128_early", "k128_settings", "letter_grades", "letter_grades_settings", "honors_page", "honors_page_settings", "my_career_home",
            "reserves_16", "created_teams_extra", "roster_arena_growth", "roster_arena_settings", "roster_arena_resource", "defensive_try", "zone_drop_cap", "zone_drop_settings", "all_stadiums", "coverage_slider", "scramble_tuning",
            "flatter_deep_ball", "chop_block_toggle", "chop_block_evidence",
            "music_shuffle", "music_shuffle_state", "practice_squad_screen", "abilities", "abilities_settings", "qb_spy", "calendar_engine")},
        "xbe_space": report.get("xbe_space", "unknown"),
        "kickoff_relocated": report.get("kickoff_relocated", "unknown"),
        "kickoff_relocated_settings": report.get("kickoff_relocated_settings"),
        # the executable half alone is never "applied": the name pool lives in pack 0 (both halves below for images)
        "prospect_names": ("partial" if report.get("prospect_names") == "applied" else report.get("prospect_names", "unknown")),
        "player_star": report.get("player_star", "unknown"), "player_tags": "n/a", "roster_edits": "n/a",
        "weather_plan": "requires image",
        "espn25_plan": "requires image", "espn25_rosters": "requires image",
        "seven_on_seven": report.get("seven_on_seven", "unknown"), "seven_on_seven_book": "n/a", "team_history": "n/a",
        "position_pools": "n/a", "position_pool_filters": "n/a", "season_2026": "n/a",
        "trade_deadline": report.get("trade_deadline", "unknown"), "kickoff_alignment": "n/a",
        "guardian_cap": report.get("guardian_cap", "n/a"),
        "screen_timing": "n/a", "modern_naming": "requires image", "team_names_2026": "n/a", "hires_pack": "requires image",
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
    ratings = _core_module("nfl2k5_team_ratings")
    out["team_ratings"] = ratings.status(_xbe_bytes(source)) if ratings is not None else "unavailable"
    play_art = _core_module("nfl2k5_play_art_routes")  # b776-pa2
    out["play_art_routes"] = play_art.status(_xbe_bytes(source)) if play_art is not None else "unavailable"
    spacing = _core_module("nfl2k5_formation_art_spacing")  # b777-tp1
    out["formation_art_spacing"] = spacing.status(_xbe_bytes(source)) if spacing is not None else "unavailable"
    run_blocking = _core_module("nfl2k5_run_blocking")  # b777-ol1
    out["run_blocking"] = run_blocking.status(_xbe_bytes(source)) if run_blocking is not None else "unavailable"
    force_out = _core_module("nfl2k5_force_out")  # b778-fo1
    out["modern_force_out"] = force_out.status(_xbe_bytes(source)) if force_out is not None else "unavailable"
    inbox = _core_module("nfl2k5_inbox_standings")
    out["inbox_standings"] = inbox.status(_xbe_bytes(source)) if inbox is not None else "unavailable"
    rookie_faces = _core_module("nfl2k5_rookie_faces")  # b778-rh1
    out["rookie_faces"] = rookie_faces.xbe_status(_xbe_bytes(source)) if rookie_faces is not None else "unavailable"
    alien = _core_module("nfl2k5_alien_prospect")  # b778-ee1
    out["alien_prospect"] = alien.xbe_status(_xbe_bytes(source)) if alien is not None else "unavailable"
    team_sleeves = _core_module("nfl2k5_team_sleeves")  # b778-sl1
    out["team_sleeves"] = team_sleeves.status(_xbe_bytes(source)) if team_sleeves is not None else "unavailable"
    star_retention = _core_module("nfl2k5_star_retention")  # b778-fa1
    out["star_retention"] = star_retention.status(_xbe_bytes(source)) if star_retention is not None else "unavailable"
    practice_injuries = _core_module("nfl2k5_practice_injuries")  # b778-pi1
    out["practice_injuries"] = (practice_injuries.status(_xbe_bytes(source)) if practice_injuries is not None
                                else "unavailable")
    ball_carriers = _core_module("nfl2k5_ball_carrier_ai")  # b778-ai5
    out["cpu_ball_carriers"] = ball_carriers.status(_xbe_bytes(source)) if ball_carriers is not None else "unavailable"
    sportscenter = _core_module("nfl2k5_sportscenter_lineup")
    out["sportscenter_lineup"] = sportscenter.status(_xbe_bytes(source)) if sportscenter is not None else "unavailable"
    draft_clock = _core_module("nfl2k5_draft_clock")  # b778-dr1
    out["franchise_draft_clock"] = draft_clock.status(_xbe_bytes(source)) if draft_clock is not None else "unavailable"
    weekly = _core_module("nfl2k5_weekly_progression")  # b778-pg1
    out["weekly_progression"] = weekly.status(_xbe_bytes(source)) if weekly is not None else "unavailable"
    player_progress = _core_module("nfl2k5_player_progress_screen")  # b778-pg2/pg3
    out["player_progress"] = player_progress.status(_xbe_bytes(source)) if player_progress is not None else "unavailable"
    out["player_progress_visible"] = out["player_progress"]
    college_guard = _core_module("nfl2k5_contract_college_guard")  # b778-cr1
    out["contract_college_guard"] = college_guard.status(_xbe_bytes(source)) if college_guard is not None else "unavailable"
    cb_tackles = _core_module("nfl2k5_sim_cb_tackles")  # b778-cb1
    out["sim_cb_tackles"] = cb_tackles.status(_xbe_bytes(source)) if cb_tackles is not None else "unavailable"
    sim_stats = _core_module("nfl2k5_sim_stats")  # b778-sim1
    out["sim_stats"] = sim_stats.status(_xbe_bytes(source)) if sim_stats is not None else "unavailable"
    clock_led = _core_module("nfl2k5_clock_led")  # b778-sd4
    out["modern_clock_led"] = clock_led.status(_xbe_bytes(source)) if clock_led is not None else "unavailable"
    # b778-bd2: these three are in the Modern preset but were missing from this report, so the
    # Build page disabled them and silently left them out of every UI build of that preset.
    crib_trophy = _core_module("nfl2k5_crib_trophy_room")
    out["crib_trophy_room"] = (crib_trophy.status(_xbe_bytes(source))
                               if crib_trophy is not None else "unavailable")
    star_career = _core_module("nfl2k5_star_career")
    out["star_career"] = star_career.status(_xbe_bytes(source)) if star_career is not None else "unavailable"
    module_loader = _core_module("nfl2k5_module_loader")
    out["module_loader"] = (module_loader.status(_xbe_bytes(source))
                            if module_loader is not None else "unavailable")
    # The award history is a roster-pool write with no executable site to read back; its
    # own writer skips honors already present, so a disc image can always take it.
    out["honors_history"] = "retail" if report.get("container") == "xiso" else "n/a"
    if report.get("container") == "xiso":
        moments = _core_module("nfl2k5_espn25_more_moments")
        stock = _core_module("nfl2k5_stock_books")
        try:
            out["espn25_named_previews"] = moments.named_image_status(source)
            if out["espn25_named_previews"] != report.get("espn25_named_previews"):
                out["espn25_named_previews"] = "foreign"
            bank_state = stock.image_status(source)
            if bank_state != out["historic_stock_books"]:
                out["historic_stock_books"] = "foreign"
        except (OSError, ValueError):
            out["espn25_named_previews"] = "foreign"
            out["historic_stock_books"] = "foreign"
        out["modern_naming"] = tt.modern_naming_patch.image_status(source)
        try:
            out["modern_naming_details"] = tt.modern_naming_patch.image_preview(source)
        except (OSError, ValueError) as exc:
            out["modern_naming_details"] = {"reason": str(exc)}
        hires = _core_module("nfl2k5_hires_pack")
        if hires is not None:
            try:
                out["hires_pack_details"] = hires.inspect_image(source)
                out["hires_pack"] = out["hires_pack_details"]["status"]
            except Exception as exc:  # preserve malformed resource evidence for display
                out["hires_pack"] = "foreign"
                out["hires_pack_details"] = {"status": "foreign", "reason": str(exc)}
        names_2026 = _core_module("nfl2k5_team_names_2026")
        if names_2026 is not None:
            try:
                rost_state = names_2026.image_status(source)
                xbe_state = names_2026.xbe_status(_xbe_bytes(source))
                # u3: the names (ROST) and their engine key paths (XBE) are one option: both or neither
                out["team_names_2026"] = rost_state if rost_state == xbe_state else "foreign"
                out["team_names_2026_xbe"] = xbe_state
                manifest = names_2026.manifest()
                out["team_names_2026_details"] = {"teams": manifest["teams"], "strg_audit": manifest["strg_audit"]}
            except (OSError, ValueError):
                out["team_names_2026"] = "foreign"
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
        returns = _tools_module("nfl2k5_kickoff_returns")
        if returns is not None:
            try:
                out["kickoff_returns"] = returns.status(source)["status"]
            except Exception:  # noqa: BLE001
                out["kickoff_returns"] = "foreign"
        pools = _core_module("nfl2k5_position_pools")
        if pools is not None:
            try:
                pools_xbe = _xbe_bytes(source)
                out["position_pools"] = pools.status(pools_xbe)
                out["position_pool_lineup"] = pools.lineup_status(pools_xbe)
                out["position_pool_filters"] = pools.filter_list_status(pools_xbe)
            except Exception:  # noqa: BLE001
                out["position_pools"] = "foreign"
                out["position_pool_filters"] = "foreign"
        season = _core_module("nfl2k5_season_length")
        if season is not None:
            try:
                out["season_2026"] = season.simple_status(_xbe_bytes(source))
            except Exception:  # noqa: BLE001
                out["season_2026"] = "foreign"
        deadline = _core_module("nfl2k5_trade_deadline")
        if deadline is not None:
            try:
                out["trade_deadline"] = deadline.status(_xbe_bytes(source))
            except Exception:  # noqa: BLE001
                out["trade_deadline"] = "foreign"
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
        espn = _core_module("nfl2k5_espn25_scenarios")
        if espn is not None:
            # the fixed SITU / historic ROST layout of a USA disc: available, else foreign (never a
            # plan status: that needs the selected plan, which inspect does not have)
            try:
                espn.Catalog.load(source)
                out["espn25_plan"] = "available"
            except Exception:  # noqa: BLE001
                out["espn25_plan"] = "foreign"
        weather = _core_module("nfl2k5_weather")
        if weather is None:
            out["weather_plan"] = "unavailable"
        else:
            try:
                weather.load_resource(source)  # Parses bounded ROST + resolved 82-row table.
                out["weather_plan"] = "available"
            except (OSError, ValueError):
                out["weather_plan"] = "foreign"
        rosters = _core_module("nfl2k5_espn25_rosters")
        if rosters is not None:
            try:
                out["espn25_rosters"] = rosters.image_status(source)
            except Exception:  # noqa: BLE001
                out["espn25_rosters"] = "foreign"
        seasons = _core_module("nfl2k5_historic_rosters")
        if seasons is not None:
            out["historic_rosters_2026"] = seasons.image_status(source)
        classic = _core_module("nfl2k5_classic_teams")  # b775-ct1: the executable half (the files need the retail source)
        if classic is not None:
            try:
                out["classic_teams"] = classic.xbe_status(rosters.read_xbe(source)) if rosters is not None else "foreign"
            except Exception:  # noqa: BLE001
                out["classic_teams"] = "foreign"
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
    haze = _core_module("nfl2k5_weather_haze")
    if haze is None:
        out["weather_haze"] = "unavailable"
    else:
        try:
            out["weather_haze"] = haze.status(_xbe_bytes(source))
        except (OSError, ValueError):
            out["weather_haze"] = "unknown"
    kerning = _core_module("nfl2k5_number_kerning")  # b76-k2
    if kerning is None:
        out["number_kerning"] = "unavailable"
    else:
        try:
            out["number_kerning"] = kerning.status(_xbe_bytes(source))
        except (OSError, ValueError):
            out["number_kerning"] = "unknown"
    modern = _core_module("nfl2k5_modern_color")
    if modern is None:
        out["modern_color"] = "unavailable"
    else:
        try:
            colour_receipt = modern.read_image_receipt(source)
            colour_settings = colour_receipt["settings"] if colour_receipt else None
            out["modern_color"] = modern.xbe_status(_xbe_bytes(source), colour_settings)
            if colour_receipt is not None:
                bundles = modern.image_status(source, receipt=colour_receipt)
                if bundles != out["modern_color"]:
                    out["modern_color"] = "foreign"
                else:
                    out["modern_color_settings"] = colour_settings
        except (OSError, ValueError):
            out["modern_color"] = "unknown"
    arrowhead = _core_module("nfl2k5_modern_arrowhead")
    if arrowhead is None:
        out["modern_arrowhead"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_arrowhead"] = "needs_image"
    else:
        try:
            out["modern_arrowhead"] = arrowhead.image_status(source)
        except (OSError, ValueError):
            out["modern_arrowhead"] = "unknown"
    metlife = _core_module("nfl2k5_modern_metlife")
    if metlife is None:
        out["modern_metlife"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_metlife"] = "needs_image"
    else:
        try:
            out["modern_metlife"] = metlife.image_status(source)
        except (OSError, ValueError):
            out["modern_metlife"] = "unknown"
    venues26 = _core_module("nfl2k5_modern_venues_2026")  # b76-u4
    if venues26 is None:
        out["modern_venues_2026"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_venues_2026"] = "needs_image"
    else:
        try:
            out["modern_venues_2026"] = venues26.image_status(source)
        except (OSError, ValueError):
            out["modern_venues_2026"] = "unknown"
    helmets = _core_module("nfl2k5_modern_helmets")  # b76-hm
    if helmets is None:
        out["modern_helmets"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_helmets"] = "needs_image"
    else:
        try:
            out["modern_helmets"] = helmets.image_status(source)
        except (OSError, ValueError):
            out["modern_helmets"] = "unknown"
    metlife_model = _core_module("nfl2k5_metlife_model")
    if metlife_model is None:
        out["modern_metlife_model"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_metlife_model"] = "needs_image"
    else:
        try:
            out["modern_metlife_model"] = metlife_model.image_status(source)
        except (OSError, ValueError):
            out["modern_metlife_model"] = "unknown"
    sofi = _core_module("nfl2k5_sofi_model")  # b76-u6
    if sofi is None:
        out["modern_sofi"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_sofi"] = "needs_image"
    else:
        try:
            out["modern_sofi"] = sofi.image_status(source)
        except (OSError, ValueError):
            out["modern_sofi"] = "unknown"
    highmark = _core_module("nfl2k5_highmark_model")  # b76-st
    if highmark is None:
        out["modern_highmark"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_highmark"] = "needs_image"
    else:
        try:
            out["modern_highmark"] = highmark.image_status(source)
        except (OSError, ValueError):
            out["modern_highmark"] = "unknown"
    att = _core_module("nfl2k5_att_model")  # b76-st2
    if att is None:
        out["modern_att"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_att"] = "needs_image"
    else:
        try:
            out["modern_att"] = att.image_status(source)
        except (OSError, ValueError):
            out["modern_att"] = "unknown"
    levis = _core_module("nfl2k5_levis_model")  # b76-st2
    if levis is None:
        out["modern_levis"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_levis"] = "needs_image"
    else:
        try:
            out["modern_levis"] = levis.image_status(source)
        except (OSError, ValueError):
            out["modern_levis"] = "unknown"
    allegiant = _core_module("nfl2k5_allegiant_model")  # b76-st2
    if allegiant is None:
        out["modern_allegiant"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_allegiant"] = "needs_image"
    else:
        try:
            out["modern_allegiant"] = allegiant.image_status(source)
        except (OSError, ValueError):
            out["modern_allegiant"] = "unknown"
    mercedes_benz = _core_module("nfl2k5_mercedes_benz_model")  # b76-st2
    if mercedes_benz is None:
        out["modern_mercedes_benz"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_mercedes_benz"] = "needs_image"
    else:
        try:
            out["modern_mercedes_benz"] = mercedes_benz.image_status(source)
        except (OSError, ValueError):
            out["modern_mercedes_benz"] = "unknown"
    usbank = _core_module("nfl2k5_usbank_model")  # b76-st3
    if usbank is None:
        out["modern_usbank"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_usbank"] = "needs_image"
    else:
        try:
            out["modern_usbank"] = usbank.image_status(source)
        except (OSError, ValueError):
            out["modern_usbank"] = "unknown"
    lucas_oil = _core_module("nfl2k5_lucas_oil_model")  # b76-st3
    if lucas_oil is None:
        out["modern_lucas_oil"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_lucas_oil"] = "needs_image"
    else:
        try:
            out["modern_lucas_oil"] = lucas_oil.image_status(source)
        except (OSError, ValueError):
            out["modern_lucas_oil"] = "unknown"
    state_farm = _core_module("nfl2k5_state_farm_model")  # b76-st3
    if state_farm is None:
        out["modern_state_farm"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_state_farm"] = "needs_image"
    else:
        try:
            out["modern_state_farm"] = state_farm.image_status(source)
        except (OSError, ValueError):
            out["modern_state_farm"] = "unknown"
    hard_rock = _core_module("nfl2k5_hard_rock_model")  # b76-st4
    if hard_rock is None:
        out["modern_hard_rock"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_hard_rock"] = "needs_image"
    else:
        try:
            out["modern_hard_rock"] = hard_rock.image_status(source)
        except (OSError, ValueError):
            out["modern_hard_rock"] = "unknown"
    gillette = _core_module("nfl2k5_gillette_model")  # b76-st4
    if gillette is None:
        out["modern_gillette"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_gillette"] = "needs_image"
    else:
        try:
            out["modern_gillette"] = gillette.image_status(source)
        except (OSError, ValueError):
            out["modern_gillette"] = "unknown"
    lambeau = _core_module("nfl2k5_lambeau_model")  # b76-st4
    if lambeau is None:
        out["modern_lambeau"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_lambeau"] = "needs_image"
    else:
        try:
            out["modern_lambeau"] = lambeau.image_status(source)
        except (OSError, ValueError):
            out["modern_lambeau"] = "unknown"
    everbank = _core_module("nfl2k5_everbank_model")  # b76-st4
    if everbank is None:
        out["modern_everbank"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_everbank"] = "needs_image"
    else:
        try:
            out["modern_everbank"] = everbank.image_status(source)
        except (OSError, ValueError):
            out["modern_everbank"] = "unknown"
    if everbank is None:  # b76-st4: the construction sub-option: retail (still to choose), on, off, mixed or foreign
        out["modern_everbank_construction"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_everbank_construction"] = "needs_image"
    else:
        try:
            out["modern_everbank_construction"] = everbank.construction_status(source)
        except (OSError, ValueError):
            out["modern_everbank_construction"] = "unknown"
    board_kit = _core_module("nfl2k5_board_kit")  # b76-st5
    if board_kit is None:
        out["modern_board_kit"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_board_kit"] = "needs_image"
    else:
        try:
            report = board_kit.image_report(source, brief=True)  # one reading: the state and the stadiums that stay as they are
            out["modern_board_kit"] = report["state"]
            if report["skipped"]:
                out["modern_board_kit_skips"] = [row["stadium"] for row in report["skipped"]]
        except (OSError, ValueError):
            out["modern_board_kit"] = "unknown"
    practice = _core_module("nfl2k5_practice_field_model")  # b76-pf
    if practice is None:
        out["modern_practice_field"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_practice_field"] = "needs_image"
    else:
        try:
            out["modern_practice_field"] = practice.image_status(source)
        except (OSError, ValueError):
            out["modern_practice_field"] = "unknown"
    surfaces = _core_module("nfl2k5_modern_surfaces")  # b76-tf
    if surfaces is None:
        out["modern_surfaces"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_surfaces"] = "needs_image"
    else:
        try:
            out["modern_surfaces"] = surfaces.image_status(source)
        except (OSError, ValueError):
            out["modern_surfaces"] = "unknown"
    marks = _core_module("nfl2k5_espn_marks")
    if marks is None:
        out["espn_marks_2026"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["espn_marks_2026"] = "needs_image"
    else:
        try:
            out["espn_marks_2026"] = marks.image_status(source)
        except (OSError, ValueError):
            out["espn_marks_2026"] = "unknown"
    # b76-p2: ESPN 2026 wipes and boards (six scene resources in wipe.cdf and the menu and bumper scenes)
    wipes = _core_module("nfl2k5_espn_wipes_boards")
    if wipes is None:
        out["espn_wipes_boards_2026"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["espn_wipes_boards_2026"] = "needs_image"
    else:
        try:
            out["espn_wipes_boards_2026"] = wipes.image_status(source)
        except (OSError, ValueError):
            out["espn_wipes_boards_2026"] = "unknown"
    # b76-km: the 2026 kick meter (KickArrow, KickMeter and windmeter in gamedata.iff)
    kick_meter = _core_module("nfl2k5_kick_meter_2026")
    if kick_meter is None:
        out["kick_meter_2026"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["kick_meter_2026"] = "needs_image"
    else:
        try:
            out["kick_meter_2026"] = kick_meter.image_status(source)
        except (OSError, ValueError):
            out["kick_meter_2026"] = "unknown"
    # b77-v1: modern goalposts (the two shared goalpost scenes in gamedata.iff and three executable operands)
    goalposts = _core_module("nfl2k5_modern_goalposts")
    if goalposts is None:
        out["modern_goalposts"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_goalposts"] = "needs_image"
    else:
        try:
            out["modern_goalposts"] = goalposts.image_status(source)
        except (OSError, ValueError):
            out["modern_goalposts"] = "unknown"
    # b775-hs1: hair styles (the two player scenes, nine hair textures in outer 3 and the executable owner)
    hair = _core_module("nfl2k5_hair_styles")
    if hair is None:
        out["hair_styles"] = "unavailable"
    elif not tt.is_disc_image(source):
        out["hair_styles"] = "needs_image"
    else:
        try:
            out["hair_styles"] = hair.image_status(source)
        except (OSError, ValueError):
            out["hair_styles"] = "unknown"
    # b776-ai2: the CPU AI owners (executable only, so a bare default.xbe reads too)
    reads, ball = _core_module("nfl2k5_cpu_qb_reads"), _core_module("nfl2k5_db_ball_play")
    try:
        xbe = _xbe_bytes(source) if reads is not None or ball is not None else b""
    except (OSError, ValueError):
        xbe = None
    for key, module, read in (("cpu_qb_zone_windows", reads, lambda m, x: m.component_status(x, "zone_windows")),
                              ("cpu_qb_recheck", reads, lambda m, x: m.component_status(x, "recheck")),
                              ("db_ball_play", ball, lambda m, x: m.status(x))):
        out[key] = "unavailable" if module is None else "unknown" if xbe is None else read(module, xbe)
    accuracy = _core_module("nfl2k5_qb_accuracy")  # b777-qb3
    if accuracy is None:
        out["qb_accuracy"] = "unavailable"
    else:
        try:
            out["qb_accuracy"] = accuracy.status(_xbe_bytes(source))
        except (OSError, ValueError):
            out["qb_accuracy"] = "unknown"
    # b776-ns1: the per-kit jersey number size (the executable's table)
    number_scale = _core_module("nfl2k5_team_number_scale")
    if number_scale is None:
        out["team_number_scale"] = "unavailable"
    else:
        try:
            out["team_number_scale"] = number_scale.status(_xbe_bytes(source))
        except (OSError, ValueError):
            out["team_number_scale"] = "unknown"
    # b77-co1: the 2026 head coaches (32 coach models, two portrait slots, two coach-record photo ids)
    coaches = _core_module("nfl2k5_modern_coaches")
    if coaches is None:
        out["modern_coaches"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_coaches"] = "needs_image"
    else:
        try:
            out["modern_coaches"] = coaches.image_status(source)
        except (OSError, ValueError):
            out["modern_coaches"] = "unknown"
    # b77-fr1: the 2026 fans (the 32 clubs' crowd texture sets of the crowd-reaction cutaways)
    fans = _core_module("nfl2k5_modern_fans")
    if fans is None:
        out["modern_fans"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_fans"] = "needs_image"
    else:
        try:
            out["modern_fans"] = fans.image_status(source)
        except (OSError, ValueError):
            out["modern_fans"] = "unknown"
    # b77-rf1: the 2025-26 officials (the referee scene, the caps and the number textures of gamedata.iff)
    officials = _core_module("nfl2k5_modern_officials")
    if officials is None:
        out["modern_officials"] = "unavailable"
    elif not (source.is_dir() or tt.is_disc_image(source)):
        out["modern_officials"] = "needs_image"
    else:
        try:
            out["modern_officials"] = officials.image_status(source)
        except (OSError, ValueError):
            out["modern_officials"] = "unknown"
    finish = _core_module("nfl2k5_helmet_finish")
    if finish is None:
        out["helmet_finish"] = "unavailable"
    else:
        try:
            out["helmet_finish"] = finish.status(_xbe_bytes(source))
        except (OSError, ValueError):  # a synthetic or foreign image without a readable executable
            out["helmet_finish"] = "unknown"
    intro = _core_module("nfl2k5_intro_videos")
    out["trim_intro_videos"] = (intro.image_status(source) if intro is not None and report.get("container") == "xiso"
                                else "requires image")
    custom_intro = _core_module("nfl2k5_custom_intro")
    out["custom_intro"] = (custom_intro.image_status(source)
                           if custom_intro is not None and report.get("container") == "xiso" else "requires image")
    return out


def _check_playbook_menus(target: Path, progress: Callable[..., Any]) -> dict[str, Any] | None:
    """Refuse unsafe labels or formation menus in every PLAY book on the image.

    Includes the native label slot and no-argument printf contract, duplicate
    links that hang the list, selection groups and unreachable/out-of-range
    links. Returns None when the modules are not part of this build.
    """
    inspector = _core_module("nfl2k5_playbook_inspector")
    packs = _core_module("nfl2k5_playbook_pack")
    if inspector is None or packs is None or not hasattr(inspector, "playcall_ui_problems"):
        return None
    progress("Checking every playbook's names and play menus", 0, 0)
    books, problems = 0, []
    with packs._outer_image().OuterImage(target) as archive:
        for entry in archive.entries_with_head(b"PLAY"):
            books += 1
            raw = archive.read_entry(entry.index)
            issues = inspector.playcall_ui_problems(raw)
            if not issues:
                issues = inspector.category_menu_problems(raw)
            problems += [f"book {entry.index}: {problem}"
                         for problem in issues]
    if problems:
        raise RuntimeError("A playbook on this build has unsafe play-call names or menus: " + "; ".join(problems[:4])
                           + (f"; and {len(problems) - 4} more" if len(problems) > 4 else ""))
    return {"books": books, "problems": 0}


def _xbe_bytes(source: Path) -> bytes:
    source = Path(source)  # fx1 (review pr67): BuildPlan.source is a str; a bare default.xbe raised AttributeError
    if tt.is_disc_image(source):
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            off, length = tt.image_xbe_extent(fd, size)
            return platform_compat.pread(fd, length, off)
        finally:
            os.close(fd)
    return source.read_bytes()


def _check_playbook_scoring(target: Path, progress: Callable[..., Any]) -> dict[str, Any]:
    """Fail closed on every final PLAY, after all book writers, before publication."""
    from . import nfl2k5_play_scoring as scoring
    packs = _core_module("nfl2k5_playbook_pack")
    if packs is None:
        raise RuntimeError("Native PLAY scoring requires the playbook archive reader")
    payload = _xbe_bytes(target)
    with packs._outer_image().OuterImage(target) as archive:
        books = [(entry.index, archive.read_entry(entry.index)) for entry in archive.entries_with_head(b"PLAY")]
    # The books are scored in worker processes and consumed in book order (nfl2k5_play_scoring.require_safe_many).
    rows = scoring.require_safe_many(
        books, payload, progress=lambda index, done, total: progress(
            f"Checking native play scoring: book {index}", done, 37))
    if not rows:
        raise RuntimeError("Native PLAY scoring found no books in the build")
    return {"status": "applied", "schema": scoring.SCHEMA, "books": len(rows), "faults": 0, "results": rows}


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


#: Held after the practice playtest: keep the implementation for future repair.
#: Old recipes cannot opt in, and builds retire an already installed menu entry.
SEVEN_ON_SEVEN_RELEASED = False


def retire_seven_on_seven(target: Path) -> dict[str, Any]:
    """Studio's fixed-size retirement pass, also usable on an extracted XBE."""
    before = _xbe_bytes(target)
    patched, removal = tt.seven_on_seven_patch.remove(before)
    if patched != before:
        _write_xbe_bytes(target, patched)
    return {"step": "seven_on_seven_removed", **removal}


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
    """Name the disc in a refusal, when the disc is the reason.

    "pack-0 schedule template is foreign: ROST stored size is not retail" is
    true and useless: it is the same sentence for a repacked image, a disc that
    already carries somebody's roster mod, and a dump of another game.  Which
    one it is decides whether the user re-dumps, rebuilds, or starts over, so
    every refusal on a disc image says which -- unless the image's game files
    are retail, in which case the disc is not the reason and naming it only
    misleads (beta 63: "outer 5: ROST preamble ... Build & Share works" sent a
    tester to repack a dump that was never the problem).
    """

    text = str(exc)
    if not is_image or "This image is:" in text:
        return exc
    identity = disc_identity(source)
    if identity is None or identity.can_build:
        return exc
    note = f"This image is: {identity.line()}"
    joiner = " " if text.rstrip().endswith((".", "!", "?", ":")) else ". "
    return ValueError(f"{text.rstrip()}{joiner}{note}")


def _music_library_document(path):
    return _core_module("nfl2k5_music_banks")._load(path)


def _prepare_music_project(source, project, directory, progress, *, library_result=None):
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
        if service.library_recipe_path() is not None:
            if library_result is None:
                raise ValueError("This Music project includes added songs; use the complete music build path.")
            library_result.append(service.library_recipe_path())
        return service.encoded_edits(progress=progress)
    finally:
        service.invalidate()


PLAYBOOK_OPTION_LABELS = {
    "coach_ai": "Automatic 2026 CPU coach profiles (experimental)",
    "playbook_pair": "Separate offensive and defensive playbooks (experimental)",
    "read_option_runtime": "Read option mesh controls (experimental)",
    "qb_spy": "QB spy for zone, man and rush (experimental)",
}


def validate_plan(plan: BuildPlan) -> list[str]:
    """Report incompatible choices before reading game inputs or copying a disc."""
    if type(plan.official_marks_pack) is not str:
        return ["official_marks_pack must be a folder path (text)"]
    if plan.historic_rosters_2026:
        from . import nfl2k5_historic_rosters
        try:
            nfl2k5_historic_rosters.require_build_ready()
        except nfl2k5_historic_rosters.HistoricRostersError as exc:
            return [str(exc)]
    # b76-f2: the Crib movie cut composes with Trim intro videos and with the Custom
    # intro video: a shrink larger than the movie archive's final pack spills into
    # the packs before it (nfl2k5_music_archive.pack_sizes).
    if plan.custom_intro and plan.trim_intro_videos:
        return ["Choose Custom intro video or Trim intro videos. The trim skips every startup movie, "
                "so the custom intro would never play."]
    # b76-u3: both rewrite the jersey colour rule at 0x6160F (when the Cowboys wear white).
    if plan.team_names_2026 and plan.uniform_choice:
        return ["Choose 2026 team names or Uniform choice. Both rewrite the game's jersey colour rule "
                "(when the Cowboys wear white), so one would undo the other."]
    # b76-pf P1: the eighth field swap pair only reaches the practice facility's field (its midfield named teamlogo).
    if plan.modern_practice_field_team_logo is True and plan.modern_practice_field is not True:
        return ["The practicing team's logo at midfield needs the Modern practice facility: turn it on too."]
    return []


def require_build_source(source: Path | str) -> Path:
    """Name a vanished build source in words, before any build work starts.

    A beta 72.1 tester built a disc, renamed the copy, and built again. The
    Build page hands each finished copy to the next build, so the plan still
    named the old name, and the first read of it raised the platform's own
    file-not-found from inside the copy step: "[WinError 2] The system cannot
    find the file specified: ...(modded).xiso.iso", a path he had not chosen in
    that build and an error this module never turned into a sentence (the
    refusal wrapper below catches ValueError, not OSError).

    Nothing about the new output was wrong, so the refusal says which file is
    gone and stops before the temporary directory, the preflights, the project
    compile and any write. The earlier copy is never required or written to; a
    build to a fresh target reads only the source named here.
    """

    source = platform_compat.io_path(source)
    try:
        found = source.is_file()
    except OSError:  # an unreadable parent, a dead network share
        found = False
    if found:
        return source
    if source.is_dir():
        raise ValueError(f"The file to build from is a folder, not a game file: {source}")
    raise ValueError(
        f"The file to build from is no longer on this computer: {source}. "
        "It was renamed, moved or deleted after it was chosen."
    )


#: The prefix of the private folder ``build`` makes beside the chosen output.
STAGE_PREFIX = ".studio-build-"
#: Working room a disc-image build needs beyond the copy itself (b778-bd2).
STAGE_SPACE_MARGIN = 512 * 1024 * 1024


def output_space_problem(source: Path | str, target: Path | str) -> str:
    """Why this disc copy cannot be written safely, in one actionable sentence, or "".

    The build stages a complete copy in the output folder before publishing it. A full drive
    therefore fails after the copy has already run for a long time, and Windows reports only
    the platform's raw "not enough space" sentence. Checking the same figure the build needs
    first turns that into an instruction before any work starts (b778-bd2, tinpanalley's
    build that ran over an hour and failed). Only disc images are measured: an executable
    copy is tiny.
    """

    if not tt.is_disc_image(source):
        return ""
    try:
        source_size = Path(source).stat().st_size
    except OSError:
        return ""  # require_build_source names a vanished source in its own words
    folder = platform_compat.io_path(target).parent
    required = source_size + STAGE_SPACE_MARGIN
    try:
        free = platform_compat.available_bytes(folder)
    except OSError as exc:
        return (f"The output folder cannot be checked for free space: {folder} ({exc}). "
                "Choose another folder, then make the disc again. Nothing was written.")
    if free >= required:
        return ""
    shortfall = required - free
    return (f"The output folder does not have enough free space for the build: {folder} has "
            f"{free / 1024**3:.2f} GiB free; writing the disc copy needs at least "
            f"{required / 1024**3:.2f} GiB (the {source_size / 1024**3:.2f} GiB source plus "
            f"{STAGE_SPACE_MARGIN // 1024**2} MiB of working room). Free another "
            f"{shortfall / 1024**3:.2f} GiB or choose another folder. Nothing was written.")


def local_output_problem(target: Path | str) -> str:
    """Why writing beside ``target`` is unsafe on this computer, or "".

    OneDrive uploads and scans every byte written to a synced folder. A 6 GB disc copy
    there can crawl for over an hour and then fail when the sync client holds one of the
    build's files, so the Build tab and the core build both refuse it up front with the
    folder and a plain replacement (b778-bd2; the texture-project builder has refused the
    same folder since beta 74).
    """

    if not platform_compat.IS_WINDOWS:
        return ""
    from .nfl2k5_build_service import _cloud_synced_root
    folder = platform_compat.io_path(target).parent
    found = _cloud_synced_root(folder)
    if found is None:
        return ""
    root, how = found
    return (f"The disc copy would be written inside OneDrive ({how}, {root}): {folder}. "
            "OneDrive uploads and scans the whole 6 GB disc while it is written, which can make a "
            "build crawl or fail. Choose a plain folder such as C:\\2K5 (Choose…), then make the disc "
            "again. Nothing was written.")


def _private_stage_role(path: Path) -> str | None:
    """What a file inside the Studio's own build folder is for, or None.

    ``.studio-build-aqijzioj`` is a random name that exists only while a build
    runs, so printing it tells the user nothing and reads like a folder they
    were supposed to know about ("a directory I never set", Smuzz 2026-09-21).
    The role is the part that means something.
    """

    for parent in path.parents:
        if parent.name.startswith(STAGE_PREFIX):
            if path.parent.name == "project":
                return "the project build's private copy of the disc"
            return "the build's private copy of the disc"
    return None


def require_step_source(source: Path | str, step: str) -> Path:
    """Name the step and the file's role when a step's input disc is gone.

    Steps that read the source after the copy pass must say which step wanted
    the file and what the file was, not hand the platform's own sentence about
    a temporary path to the user.
    """

    source = Path(source)
    try:
        if source.is_file():
            return source
    except OSError:  # an unreadable parent, a dead network share
        pass
    role = _private_stage_role(source)
    if role is None:
        raise ValueError(f"{step} could not read the file to build from: {source} is no longer on this "
                         "computer. Nothing was written to your chosen output.")
    raise ValueError(f"{step} could not read {role}: it is no longer there. "
                     "Nothing was written to your chosen output.")


def _private_stage_refusal(exc: OSError, stage: Path | None, step: str) -> ValueError | None:
    """Words for a build that lost one of its own private files, or None.

    Only files inside this build's own ``.studio-build-*`` folder are reworded.
    A refusal about the user's own file, the output folder or the disk keeps
    the platform's sentence, which is the useful one there.
    """

    if stage is None:
        return None
    try:
        roots = {stage, stage.resolve()}
    except OSError:  # pragma: no cover - the folder is already gone
        roots = {stage}
    named = [Path(str(name)) for name in (getattr(exc, "filename", None), getattr(exc, "filename2", None)) if name]
    for path in named:
        role = _private_stage_role(path)
        try:
            inside = any(path.is_relative_to(root) for root in roots)
        except (OSError, ValueError):  # pragma: no cover - a malformed name
            inside = False
        if role is None or not inside:
            continue
        what = step if step and step != "preflight" else "The build"
        reason = exc.strerror or str(exc)
        return ValueError(f"{what}: {role} could not be read ({reason}). This is a fault inside the "
                          "Studio's own build folder, not in the files you chose. Nothing was published.")
    return None


def build(plan: BuildPlan, progress: ProgressSink | None = None, *, _project_builder=None,
          require_change: bool = False) -> dict[str, Any]:
    """Apply the plan to a copy; archive rebuilds publish only a complete result.

    ``require_change`` is the Build & Share contract (b778-bd2): a disc whose selected
    changes are all already installed, or were all skipped, must not be published as a
    successful "retail copy". The page raises a clear refusal instead, so Play latest
    can never start the unchanged source by accident. Other callers keep the historical
    verified-copy behaviour.
    """
    from .build_io import StageProgress
    progress = StageProgress(progress)
    stage: Path | None = None
    try:
        blockers = validate_plan(plan)
        if blockers:
            raise ValueError("\n".join(blockers))
        platform_compat.validate_output_path(plan.target)
        require_build_source(plan.source)
        source, target = (platform_compat.io_path(platform_compat.absolute_path(p)) for p in (plan.source, plan.target))
        if platform_compat.paths_alias(source, target):
            raise ValueError("target must not be the source")
        # b778-bd2: refuse a folder the long build cannot finish in, before it starts.
        problem = local_output_problem(target)
        if problem:
            raise ValueError(problem)
        problem = output_space_problem(source, target)
        if problem:
            raise ValueError(problem)
        plan, coach_ai_skip = _coach_ai_decision(plan, progress)
        preflight_board_source(plan, progress)
        r62 = _validated_r62_plan_options(plan)
        from .image_use import check_image_destination, publish_image
        previous_target = check_image_destination(target, overwrite=plan.overwrite)
        with tempfile.TemporaryDirectory(prefix=STAGE_PREFIX, dir=target.parent) as folder:
            directory = Path(folder)
            stage = directory
            edits = None
            project_result = None
            effective_source = source
            if _project_builder is not None or plan.music_project:
                preflight_plan(plan, progress)
            if _project_builder is not None:
                # All plan refusals run before materializing project textures or
                # creating the first disc copy. Revalidate against the staged
                # resources below before consuming that private intermediate.
                project_directory = directory / "project"
                project_directory.mkdir()
                effective_source = project_directory / "source.iso"
                project_result = _project_builder(effective_source)
                if effective_source.is_symlink() or effective_source.stat().st_nlink != 1:
                    raise ValueError("Project builder did not produce a private image")
                from . import nfl2k5_modern_color as colour
                original_colour_receipt = colour.read_image_receipt(source)
                if original_colour_receipt is not None:
                    colour._save_image_receipt(effective_source, original_colour_receipt)
            if plan.music_project:
                if not tt.is_disc_image(source):
                    raise ValueError("Music replacements need a disc image")
                project_library = []
                edits = _prepare_music_project(effective_source, plan.music_project, directory,
                    progress or (lambda *_: None), library_result=project_library)
                if project_library:
                    if plan.music_library:
                        raise ValueError("Choose the Music project or the separate music library, then build again.")
                    plan = replace(plan, music_library=project_library[0])
            receipt = _build(replace(plan, source=str(effective_source), target=str(directory / target.name), overwrite=False), progress,
                             music_edits=edits, r62_options=r62, _consume_source=project_result is not None,
                             _retail_source=source)
            if project_result is not None:
                receipt["steps"].insert(0, {"step": "shared_project", **asdict(project_result)})
                receipt["source"] = str(source)
            if coach_ai_skip is not None:
                receipt["steps"].append(coach_ai_skip)
                receipt["coach_ai_skipped"] = coach_ai_skip["user_notes"][0]
            if plan.music_shuffle or plan.music_library:
                library = _core_module("nfl2k5_music_banks")
                expected = (plan.music_shuffle_selection or tt.music_playlist_patch.default_options()) if plan.music_shuffle else None
                checked = library.revalidate_playlist(directory / target.name, expected=expected)
                receipt["music_shuffle_validation"] = checked
                for step in receipt["steps"]:
                    preflight = step.get("music_shuffle_preflight")
                    if preflight is not None:
                        preflight.update(checked)
            progress("Hashing the verified disc", 0, 0)
            from .build_feedback import measure, compare, _digest
            # One read of the output. The source's hash comes from the pass
            # that copied it (the project builder's receipt, or this build's
            # own copy); beta 73 read the 6 GB source again here to get it.
            source_sha256 = (project_result.source_sha256
                             if project_result is not None and getattr(project_result, "source_sha256", "")
                             else receipt.get("source_sha256"))
            if source_sha256:
                receipt["outcome"] = compare(
                    {"sha256": source_sha256, "size": source.stat().st_size},
                    _digest(directory / target.name))
            else:
                receipt["outcome"] = measure(source, directory / target.name)
            if require_change and receipt["outcome"].get("status") == "unchanged":
                # b778-bd2: the step writers ran but every selected change was already on
                # the source (or kept as it was). Publishing this would hand the user a
                # disc indistinguishable from what they started with; say why instead.
                raise ValueError(
                    "Nothing was written: every selected change is already installed on this disc or was "
                    "left as it is, so the finished copy would be identical to the source. Choose your "
                    "unmodified retail disc as the source, or select different changes, then make the disc "
                    "again. Nothing was written to your chosen output.")
            # The public digest describes the final compact image, including when
            # an earlier resource pass recorded its own intermediate digest.
            if "disc_compaction" in receipt:
                receipt["result"].update(image_size=receipt["outcome"]["output"]["size"],
                                        image_sha256=receipt["outcome"]["output"]["sha256"])
            if progress:
                progress(receipt["outcome"]["message"], 0, 0)
            progress("Publishing the verified disc", 0, 0)
            from . import nfl2k5_modern_color as colour
            colour_receipt = colour.read_image_receipt(directory / target.name)
            venues26 = _core_module("nfl2k5_modern_venues_2026")  # b76-u4
            venues_receipt = venues26.read_receipt(directory / target.name) if venues26 is not None else None
            # b76-tf: the Modern surfaces receipt travels with the disc too (its status reads it)
            surfaces = _core_module("nfl2k5_modern_surfaces")
            surfaces_receipt = surfaces.read_receipt(directory / target.name) if surfaces is not None else None
            greens = _core_module("nfl2k5_broadcast_greens")
            greens_path = greens.receipt_path(directory / target.name) if greens is not None else None
            greens_receipt = json.loads(greens_path.read_text()) if greens_path is not None and greens_path.exists() else None
            publish_image(directory / target.name, target, previous_target)
            if colour_receipt is not None:
                colour._save_image_receipt(target, colour_receipt)
            else:
                colour.receipt_path(target).unlink(missing_ok=True)
            if venues26 is not None:
                if venues_receipt is not None:
                    venues26._save_receipt(target, venues_receipt)
                else:
                    venues26.receipt_path(target).unlink(missing_ok=True)
            if surfaces is not None:
                if surfaces_receipt is not None:
                    surfaces.save_receipt(target, surfaces_receipt)
                else:
                    surfaces.receipt_path(target).unlink(missing_ok=True)
            if greens is not None:
                if greens_receipt is not None:
                    greens.save(greens.receipt_path(target), greens_receipt)
                else:
                    greens.receipt_path(target).unlink(missing_ok=True)
            receipt["stage_seconds"] = progress.finish()
            receipt["target"] = str(target)
            receipt["result"]["path"] = str(target)
            return receipt
    except ValueError as exc:
        source = Path(plan.source)
        raise _with_identity(exc, source, tt.is_disc_image(source)) from exc
    except OSError as exc:
        # The user never chose anything inside the private build folder, so the
        # platform's own sentence about a file in it is unreadable as a report
        # and unusable as an instruction. Everything else keeps its own words.
        worded = _private_stage_refusal(exc, stage, progress.stage)
        if worded is None:
            raise
        raise worded from exc


def preflight_plan(plan: BuildPlan, progress: ProgressSink | None = None):
    """Run configuration and source preflights without creating a disc output (beta 66, job B)."""
    plan, coach_ai_skip = _coach_ai_decision(plan, progress)
    receipt = _build(plan, progress, _preflight_only=True)
    if coach_ai_skip is not None and isinstance(receipt, dict):
        receipt.setdefault("steps", []).append(coach_ai_skip)
        receipt["coach_ai_skipped"] = coach_ai_skip["user_notes"][0]
    return receipt


def _coach_ai_decision(plan, progress=None):
    """b77 co3: decide, before any write, whether the automatic coach AI can run on the rosters this build ends with.

    Its profiles need the 32 2026 head coaches (team, portrait and name; ``nfl2k5_coach_ai.plan_profiles``), which only
    a disc or a roster-edits document that carries them has (the SOFTDRINK 2K28 pack does; a plain retail dump does
    not). Without them the whole option is skipped, executable kernel and profiles alike (as if it were off; nothing
    partial), and one plain line says so in the build log, the receipt's user notes and the Build summary. Returns
    (plan, the receipt step for the skip or None)."""
    if not plan.coach_ai or not tt.is_disc_image(plan.source):
        return plan, None
    readiness = tt.coach_ai_patch.roster_readiness(plan.source, roster_edits=plan.roster_edits or None)
    if readiness["ready"]:
        return plan, None
    message = tt.coach_ai_patch.SKIP_MESSAGE
    if progress is not None:
        progress(message, 0, 0)
    step = {"step": "coach_ai_resources", "status": "skipped", "requested": True, "applied": False,
            "decided": "before any write", "checked": readiness["checked"],
            "mismatches": readiness["mismatches"], "user_notes": [message]}
    return replace(plan, coach_ai=False), step


def _board_kit_options(plan):
    """What the modern stadium boards must know about the rest of the plan: the stadiums another selected option
    writes in this very build. Modern Arrowhead rewrites all nine Kansas City bundles, so the boards leave that one
    stadium to it (before b77 e4 the build failed there, after hours of work, with "foreign" stadium scenes)."""
    return {"owned": {"s13": "Modern Arrowhead"}} if plan.modern_arrowhead else {}


def _announce_board_skips(result, progress):
    """Say, before the long work starts, which stadiums the boards will leave as they are."""
    skipped = (result or {}).get("skipped") if isinstance(result, dict) else None
    if skipped:
        names = ", ".join(str(row.get("stadium") or row.get("venue")) for row in skipped)
        progress(f"Modern stadium boards: {names} will be left as {'it is' if len(skipped) == 1 else 'they are'}", 0, 0)


def preflight_board_source(plan, progress=None):
    """Check the selected scene bytes before texture compilation or other preflights."""
    if not plan.modern_board_kit:
        return
    boards = _core_module("nfl2k5_board_kit")
    if boards is None or not tt.is_disc_image(plan.source):
        raise ValueError("Modern stadium boards need a disc image. Choose your unmodified USA retail image.")
    progress = progress or (lambda *_: None)
    progress("Checking Modern stadium boards source scenes", 0, 0)
    try:
        result = boards.check_request(Path(plan.source), **_board_kit_options(plan))
    except (OSError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    _announce_board_skips(result, progress)


def preflight_project_options(plan, document):
    """Reject known scene/board conflicts while the project is still only a recipe."""
    if not plan.modern_board_kit:
        return
    import re
    boards = _core_module("nfl2k5_board_kit")
    if boards is None:
        raise ValueError("Modern stadium boards are unavailable. Update Studio and try again.")
    bundles = {int(pin["outer"]): pin["name"]
               for venue in boards.pinned_venues()
               for pin in boards._venue_pins(venue).values()}
    conflicts = []
    for edit in document["edits"]:
        if edit["kind"] not in {"stadium_texture", "stadium_geometry"}:
            continue
        target = str(edit.get("target", ""))
        match = re.match(r"nfl2k5\.stadium\.o(\d+)\.", target)
        if match and int(match[1]) in bundles:
            conflicts.append(bundles[int(match[1])])
    if conflicts:
        raise ValueError("Modern stadium boards conflict with this project's stadium scene edits: "
                         + ", ".join(sorted(set(conflicts))[:6]) + ". "
                         "Turn off Modern stadium boards to keep your artwork, or remove these "
                         "stadium edits and build the boards from an unmodified retail image.")


def build_with_project(plan, service, cache, session, progress=None, *, require_change=False):
    """One private project copy, then gameplay, then one final publication."""
    from .nfl2k5_model_project import plan_rows, validate_build_plan
    preflight = getattr(service, "preflight_project", None)
    if callable(preflight):
        (progress or (lambda *_: None))("Checking the artwork recipe", 0, 0)
        document = preflight(session)
        preflight_project_options(plan, document)
        if not document["edits"]:
            return build(plan, progress, require_change=require_change)
    validate_build_plan(plan, session)
    models = plan_rows(session)
    report = progress or (lambda *_: None)
    def project_progress(event):
        report(event.message, event.completed, event.total)
    project_progress.cancelled = getattr(progress, 'cancelled', None)
    receipt = build(plan, progress, _project_builder=lambda output: service.build(
        cache, session, output, project_progress), require_change=require_change)
    if models:
        receipt["project_models"] = models
    return receipt


def _preview_play_intents(source, paths, progress=None):
    """Install ``paths`` in order onto an in-memory copy of ``source``'s books; ``progress`` hears each team.

    Compiling every team's complete offense takes minutes; without a message per team the status line sat on
    the last source check for the whole preview and the build looked hung."""
    if not paths:
        return []
    packs = _core_module("nfl2k5_playbook_pack")
    recode = packs._outer_image()
    pairs = []
    with recode.OuterImage(source) as archive:
        class PreviewArchive:
            entries = archive.entries
            pending = {}

            def read_entry(self, index):
                return self.pending[index] if index in self.pending else archive.read_entry(index)

            def write(self, offset, payload):
                index = next(i for i, entry in enumerate(self.entries) if entry.virtual_offset == offset)
                self.pending[index] = bytes(payload)
                return len(payload)

        packs.apply_packs_to_archive(PreviewArchive(), [(str(path), packs.load_pack(path)) for path in paths],
                                     (lambda message: progress(message, 0, 0)) if progress else None,
                                     book_entries=recode.BOOK_ENTRIES, collector=pairs, xbe=_xbe_bytes(source))
    return pairs


def check_playbook_pack_fit(source, pack_paths, progress=None):
    """Install ONE team's complete offense and defense pack on ``source`` in memory, before any long work.

    A custom defense pack records the SHA-256 of the book it was authored on: that team's retail book with its
    complete offense already compiled. When this Studio compiles the offense differently from the release the pack
    came from (beta 76.5's deep-back flat repair did), every such pack is refused. Without this check the refusal
    comes only when the packs are installed: minutes into the preview, or, when no preview runs, after the whole
    project build has finished. The 32 packs of a set come out of one compile, so one team is a faithful canary.
    Returns the team that was checked, or None when no team has both packs. Nothing is written."""

    packs = _core_module("nfl2k5_playbook_pack")
    if packs is None:
        return None
    offense_by_team: dict[str, Path] = {}
    defenses: list[tuple[Path, Any]] = []
    for path in dict.fromkeys(Path(p) for p in pack_paths):
        pack = packs.load_pack(path)
        if pack.schema == packs.OFFENSE_SCHEMA:
            offense_by_team.setdefault(pack.book.team, path)
        elif pack.schema == packs.DEFENSE_SCHEMA and not any(p.option_intent or p.preset_recipe for p in pack.plays):
            # a built-in preset recipe is regenerated for whatever book it meets, so it cannot be out of date
            defenses.append((path, pack))
    for path, defense in defenses:
        offense = offense_by_team.get(defense.book.team)
        if offense is None:
            continue
        (progress or (lambda *_: None))(f"Checking that {defense.book.team}'s defense pack fits its offense book", 0, 0)
        try:
            _preview_play_intents(source, [offense, path], progress=progress)
        except packs.PlaybookPackError as exc:
            if not str(exc).startswith(("Custom defense source changed", "Defense source fingerprint changed")):
                raise ValueError(str(exc)) from exc
            raise ValueError(
                f"The playbook packs in this build do not fit each other: {defense.book.team}'s defense pack "
                f"{defense.book.name!r} was written for a different compile of that team's complete offense "
                "than this Studio makes. This happens when the packs come from an older Studio or an older "
                "SOFTDRINK pack. Use the SOFTDRINK pack released with this Studio version, or remove the "
                "packs from the Playbook packs list on the Build tab, then build again. "
                f"Nothing was written. (Detail: {exc})") from exc
        return defense.book.team
    return None


def _verify_play_intents(source, pairs):
    """Reject a later PLAY pass that invalidates a retained compiler report."""
    if not pairs:
        return
    packs = _core_module("nfl2k5_playbook_pack")
    recode = packs._outer_image()
    with recode.OuterImage(source) as archive:
        for resource, report in pairs:
            if not (report.get("spy_intent", {}).get("records") or report.get("option_intent", {}).get("records")):
                continue
            asset_id = report.get("asset_id", "")
            team = asset_id.removeprefix("book:")
            if team not in recode.BOOK_ENTRIES or archive.read_entry(recode.BOOK_ENTRIES[team]) != resource:
                raise ValueError("Paired PLAY resource changed after compilation; recompile the authored intents against the final book")


def _r62_plan_options(plan, frozen_setup=None):
    # b76-vb3: the 25th Anniversary gate is decided per build (it rides with the dynamic kickoff on disc images).
    derived = {"read_option_intent_table", "anniversary_kickoff", "anniversary_kickoff_tables", "widescreen_menus",
               "team_logo_swap", "period_goalposts"}
    options = {key: (None if key in derived else frozen_setup if key == "my_career_setup"
                     else False if key == "roster_capacity" else getattr(plan, key))
               for key in tt.R62_RUNTIME_KEYS}
    # ui1: Career Home and a jukebox music library (installed after this stack) need the same extra section slot;
    # the music library wins and MyCareer keeps its Classic Apartment.
    options["my_career_home"] = bool(plan.my_career_home and not plan.music_library)
    return options


def _commentary_final_wanted(plan, loaded_espn25_plan):
    """b77-c2: builds that write rosters end with the final commentary pass (nfl2k5_commentary_final)."""
    return bool(plan.roster_edits or plan.prospect_names or plan.espn25_rosters or plan.espn25_more_moments
                or plan.historic_rosters_2026 or loaded_espn25_plan is not None)


def _anniversary_kickoff_wanted(plan, is_image):
    """b76-vb3: the ESPN 25th Anniversary moments keep the retail kickoff whenever the 2026 kickoff is built into a
    disc image (the gate is an allocator owner and reads the disc's retail special-teams data)."""
    return bool(plan.dynamic_kickoff and is_image and _core_module("nfl2k5_anniversary_kickoff") is not None)


def _widescreen_menus_wanted(plan, is_image):
    """b76-vb3 D2: widescreen builds keep 4:3 menus whenever the disc image can carry the small allocator owner."""
    return bool(plan.widescreen and is_image and _core_module("nfl2k5_widescreen_menus") is not None)


def _period_goalposts_wanted(plan, is_image):
    """b77-v1b: the 30 ft uprights of the pre-2014 Anniversary moments ride with the modern goalposts on disc images (a small
    allocator owner: the cave that picks the height when a stadium loads)."""
    return bool(plan.modern_goalposts and is_image and _core_module("nfl2k5_period_goalposts") is not None)


def _team_logo_swap_wanted(plan, is_image):
    """b76-pf P1: the field swap's eighth pair rides with the practice facility's team-logo sub-option on disc images."""
    return bool(plan.modern_practice_field and plan.modern_practice_field_team_logo and is_image
                and _core_module("nfl2k5_team_logo_swap") is not None)


def _validated_r62_plan_options(plan):
    r62 = _r62_plan_options(plan)
    tt._validate_r62_options(**r62)
    if plan.coach_ai:
        r62["cpu_money_downs"] = "modern2"
    tt._validate_lever_flags(plan.season_cap)
    tt.senior_bowl_patch.Settings.from_dict(plan.senior_bowl_settings)
    if type(plan.senior_bowl_seed) is not int or not 0 <= plan.senior_bowl_seed <= 2147483647:
        raise ValueError("Senior Bowl seed must be an integer from 0 to 2147483647")
    if plan.guardian_overlay and plan.guardian_cap:
        raise ValueError("Choose Guardian overlay or the helmet C trial, not both")
    if plan.guardian_players is not None and not plan.guardian_overlay:
        raise ValueError("Guardian player selections need guardian_overlay")
    if plan.my_career:
        # No setup selects the generic in-game creation format (MyPlayer is created in the game, careers save
        # inline); an explicit MyCareer.json keeps the legacy prepared-save route.
        if plan.my_career_setup:
            r62["my_career_setup"] = tt.my_career_patch.read_setup(plan.my_career_setup)
            tier = int.from_bytes(r62["my_career_setup"][212:216], "little")
            if plan.the1wam_lineman_rating and tier:
                # The Studio rates a prepared prospect tier against the retail overall. the1wam's lineman
                # rating changes a C/G/T overall, so a prepared lineman could miss its floor in the game.
                from . import nfl2k5_my_career_prospects as prospects
                goal = prospects.TIERS[tier][1]
                shown = prospects.prepared_overall(r62["my_career_setup"], lineman=True)
                if shown != goal:
                    raise ValueError(f"The prepared MyCareer prospect was rated to overall {goal} "
                                     f"({prospects.TIERS[tier][0]}) without the1wam's lineman rating; with it he "
                                     f"reads {shown}. Create MyPlayer in the game (leave the MyCareer setup empty), "
                                     "or build without the lineman rating.")
        else:
            r62["my_career_setup"] = None
    elif plan.my_career_setup is not None:
        raise ValueError("MyCareer setup needs my_career")
    return r62


def _apply_roster_history(plan, target, receipt, progress):
    """Apply identities, counters, then TEAM, with one history owner."""
    epoch = 2026 if plan.season_2026 else 2004
    modern_history = None
    if plan.roster_edits:
        # Replacement identities and their owned history precede optional history imports.
        records = _core_module("nfl2k5_roster_records")
        if records is None:
            raise RuntimeError("the roster records module is not available in this build")
        edits_document = records.read_edits(Path(plan.roster_edits))
        # Dated refreshes own final membership and depth. Defer them until all
        # historic imports, player tags and QB rating adjustments have run.
        refresh_follows = "roster_refresh" in edits_document
        if refresh_follows:
            edits_document = {k: v for k, v in edits_document.items() if k != "roster_refresh"}
        modern_history = edits_document.get("franchise_history")
        from . import nfl2k5_free_agents
        if plan.season_2026 and plan.position_pools and nfl2k5_free_agents.is_pack_input(edits_document):
            edits_document = dict(edits_document, modern_free_agents="2026-10-05")
        if edits_document.get("modern_free_agents"):
            edits_document = dict(edits_document, restore_historic_spare_capacity=True)
        if modern_history:
            if modern_history.get("base_year") != epoch:
                raise ValueError("franchise history epoch differs from the build season")
            if plan.career_stats:
                raise ValueError("embedded franchise history and a career CSV have conflicting ownership")
        progress("Applying the roster edits", 0, 0)
        # the reclassify pass above retires the OLB code, so an edit authored on a retail roster
        # must not write it back: tell the writer which scheme the disc it is landing on is on
        edits_receipt = records.apply(target, edits_document,
                                      progress=lambda msg: progress(msg, 0, 0),
                                      scheme="one_pool" if plan.position_pools else None,
                                      refresh_follows=refresh_follows)
        receipt["steps"].append({"step": "roster_edits", "source": plan.roster_edits,
                                 "scheme": "one_pool" if plan.position_pools else "auto",
                                 **{k: v for k, v in edits_receipt.items() if k != "log"},
                                 "log_lines": len(edits_receipt.get("log", []))})
    if plan.career_stats:
        if modern_history:
            raise ValueError("embedded franchise history and a career CSV have conflicting ownership")
        career = _core_module("nfl2k5_career_stats")
        career_receipt = career.apply(target, plan.career_stats, base_year=epoch,
                                      progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "career_stats", **career_receipt})
    if plan.team_history and not modern_history:
        history = _core_module("nfl2k5_team_history")
        history_receipt = history.apply(target, plan.team_history, base_year=epoch,
                                        progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "team_history", **{k: v for k, v in history_receipt.items() if k != "log"},
                                 "log_lines": len(history_receipt.get("log", []))})
    elif modern_history:
        receipt["steps"].append({"step": "team_history", "status": "owned_by_franchise_history",
                                 "base_year": epoch, "retail_fallback": False})
    if plan.honors_history:
        # b77-f5: sourced award history (the honors page reads it); last, after every history owner has written.
        honors_history = _core_module("nfl2k5_honors_history")
        if honors_history is None:
            raise RuntimeError("the honors history module is not available in this build")
        honors_receipt = honors_history.apply(target, plan.honors_history, base_year=epoch,
                                              progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "honors_history", **honors_receipt})


def _apply_draft_pick_ownership(plan, target, receipt, progress):
    if not plan.roster_edits:
        return
    document = _core_module("nfl2k5_roster_records").read_edits(Path(plan.roster_edits))
    pick_plan = document.get("draft_pick_ownership")
    if pick_plan is not None:
        progress("Setting draft picks for new franchises", 0, 0)
        pick_module = _core_module("nfl2k5_draft_picks")
        xbe, pick_receipt = pick_module.apply(_xbe_bytes(target), pick_plan)
        _write_xbe_bytes(target, xbe)
        receipt["steps"].append({"step": "draft_pick_ownership", **pick_receipt})


def _apply_hback_roles(plan, target, receipt, progress):
    if not plan.roster_edits:
        return
    document = _core_module("nfl2k5_roster_records").read_edits(Path(plan.roster_edits))
    roles = document.get("hback_roles")
    if roles is not None:
        progress("Setting team backfield role labels", 0, 0)
        xbe, result = _core_module("nfl2k5_hback").apply(_xbe_bytes(target), roles)
        _write_xbe_bytes(target, xbe)
        receipt["steps"].append({"step": "hback_roles", **result})


def _apply_team_ratings(plan, target, receipt, progress):
    if not plan.team_ratings:
        return
    module = _core_module("nfl2k5_team_ratings")
    if module is None:
        raise RuntimeError("The team ratings module is not available in this build")
    progress("Recalculating dynamic modern team ratings", 0, 0)
    xbe, result = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, xbe)
    receipt["steps"].append({"step": "team_ratings", **result})


def _apply_play_art_routes(plan, target, receipt, progress):
    """b776-pa2: the late play-art owner, after every other allocator owner (hair styles included)."""
    if not plan.play_art_routes:
        return
    module = _core_module("nfl2k5_play_art_routes")
    if module is None:
        raise RuntimeError("The play art routes module is not available in this build")
    progress("Drawing play art routes at their real length", 0, 0)
    xbe, result = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, xbe)
    if module.status(_xbe_bytes(target)) != "applied":
        raise RuntimeError("Play art routes: the executable does not read back as applied")
    receipt["steps"].append({"step": "play_art_routes", **{k: v for k, v in result.items() if k != "edits"}})
    receipt["result"]["play_art_routes"] = "applied"


def _apply_run_blocking(plan, target, receipt, progress):
    """b777-ol1: the run-blocking owner, the last allocator owner (after the per-kit jersey number size)."""
    if not plan.run_blocking:
        return
    module = _core_module("nfl2k5_run_blocking")
    if module is None:
        raise RuntimeError("The run blocking module is not available in this build")
    progress("Run blocking: blocks hold longer on running plays", 0, 0)
    xbe, result = module.apply(_xbe_bytes(target))
    _write_xbe_bytes(target, xbe)
    if module.status(_xbe_bytes(target)) != "applied":
        raise RuntimeError("Run blocking: the executable does not read back as applied")
    receipt["steps"].append({"step": "run_blocking", **{k: v for k, v in result.items() if k not in ("edits", "reservations")},
                             "edits": result.get("edits", [])})
    receipt["result"]["run_blocking"] = "applied"


def _roster_capacity_records(plan):
    """b778 fa4: records the paired arena writer must reserve for the dated free-agent plan."""
    if not plan.roster_edits:
        return 0
    records = _core_module("nfl2k5_roster_records")
    if records is None:
        return 0
    try:
        document = records.read_edits(Path(plan.roster_edits))
    except (OSError, ValueError):
        return 0
    request = document.get("free_agent_capacity")
    if not isinstance(request, dict):
        return 0
    value = request.get("records", 0)
    return value if type(value) is int and value > 0 else 0


def _apply_roster_refresh(plan, target, receipt, progress):
    if not plan.roster_edits:
        return
    records = _core_module("nfl2k5_roster_records")
    document = records.read_edits(Path(plan.roster_edits))
    if "roster_refresh" not in document:
        return
    if not plan.position_pools:
        raise ValueError("Dated roster refresh requires modern position pools")
    progress("Applying the dated roster refresh", 0, 0)
    directive = {"schema": records.EDITS_SCHEMA, "edits": [], "roster_refresh": document["roster_refresh"]}
    if plan.espn25_more_moments or plan.historic_teams_quick_game:
        # b775 (Noah 10/17: both sides of a moment were the home team): the refresh's new players use vacant
        # records; keep the two-team import floor, as the historic spare capacity does for the dated free agents.
        directive["restore_import_floor"] = True
    result = records.apply(target, directive, scheme="one_pool", progress=lambda msg: progress(msg, 0, 0))
    receipt["steps"].append({"step": "roster_refresh", **result})


@official.build_scope
def _build(plan: BuildPlan, progress: ProgressSink | None = None, *, music_edits=None, r62_options=None, _consume_source=False, _preflight_only=False, _retail_source=None) -> dict[str, Any]:
    progress = progress or (lambda *_a: None)
    seven_held = bool(plan.seven_on_seven and not SEVEN_ON_SEVEN_RELEASED)
    if seven_held:
        progress("7-on-7 practice is unavailable until repaired; ignoring the saved opt-in", 0, 0)
        plan = replace(plan, seven_on_seven=False)
    blockers = validate_plan(plan)
    if blockers:
        raise ValueError("\n".join(blockers))
    if plan.helmet_finish not in ("glossy", "matte"):
        raise ValueError("Helmet finish must be glossy or matte")
    if plan.helmet_finish == "matte" and _core_module("nfl2k5_helmet_finish") is None:
        raise RuntimeError("Helmet finish writer is not available in this build")
    if plan.screen_timing is not None and (
            not isinstance(plan.screen_timing, str) or plan.screen_timing not in ("A", "B", "C", "D")):
        raise ValueError("screen_timing must be None or A, B, C, D")
    if (plan.music_policy not in ("retail", "jukebox_menus") or type(plan.music_unlock) is not bool
            or type(plan.music_userlist) is not bool or (plan.music_userlist and plan.music_policy != "jukebox_menus")):
        raise ValueError("Music policies require retail or jukebox_menus, boolean switches, and jukebox menus for UserList")
    r62 = _validated_r62_plan_options(plan) if r62_options is None else dict(r62_options)
    capacity_records = _roster_capacity_records(plan)
    if capacity_records and (plan.reserves_16 or plan.created_teams_extra):
        raise ValueError("Capacity growth composes with neither 16 reserves nor extra created teams")
    if capacity_records and not plan.k128_memory:
        raise ValueError("Capacity growth needs the 128 MB memory option (K128)")
    if capacity_records:
        r62["roster_capacity"] = True
    if plan.reserves_16 or plan.created_teams_extra or capacity_records:
        plan = replace(plan, xbe_space=True, practice_squad=True, franchise_practice=True,
                       practice_squad_screen=plan.practice_squad_screen or plan.reserves_16)
    tt.momentum_patch._settings(plan.momentum, plan.momentum_contact, plan.momentum_collisions, plan.momentum_collision_level)
    momentum_on = plan.momentum > 0 or (plan.momentum_collisions and plan.momentum_collision_level > 0)
    if type(plan.defensive_try) is not bool or type(plan.zone_drop_cap) is not bool or type(plan.all_stadiums) is not bool:
        raise ValueError("experimental switches must be boolean")
    tt._validate_lever_flags(plan.music_shuffle, plan.practice_squad_screen, plan.abilities, plan.qb_spy, plan.calendar_engine, plan.season_cap)
    tt.abilities_patch._week(plan.abilities_off_week)
    tt.abilities_patch._locks(lock_right_stick=plan.abilities_lock_right_stick, lock_special_moves=plan.abilities_lock_special_moves,
                              lock_speedster=plan.abilities_lock_speedster)
    tt.abilities_patch._stars(right_stick_stars_only=plan.abilities_right_stick_stars_only,
                              button_moves_stars_only=plan.abilities_button_moves_stars_only,
                              charge_stars_only=plan.abilities_charge_stars_only, star_access=plan.abilities_star_access)
    if plan.abilities_charge_stars_only and (plan.abilities_lock_right_stick or plan.abilities_lock_special_moves):
        raise ValueError("Charge-ups: stars only replaces the charge policy of the two move locks: turn both locks off")
    if plan.abilities_off_week is not None and not plan.abilities:
        raise ValueError("abilities_off_week needs abilities")
    if plan.music_shuffle_selection is not None and not isinstance(plan.music_shuffle_selection, dict):
        raise ValueError("music_shuffle_selection must be the Music page's playlist document or None")
    if plan.music_shuffle_selection is not None:
        tt.music_playlist_patch.from_options(plan.music_shuffle_selection)  # refuse a stale or foreign document early
    if plan.practice_squad_screen:
        plan = replace(plan, practice_squad=True, franchise_practice=True, xbe_space=True)
    if plan.season_cap or plan.calendar_engine:
        # the public 128-season option is the complete repair: cap gate + calendar + 2026 templates on the allocator
        plan = replace(plan, season_cap=True, calendar_engine=True, season_2026=True, xbe_space=True)
    if type(plan.position_pools_keep_olb) is not bool:
        raise ValueError("position_pools_keep_olb must be boolean")
    if plan.position_pools_keep_olb:
        raise ValueError("The EDGE-only pools build requires reclassified rosters; rebuild an old compatibility "
                         "project with Keep Outside Linebackers off")
    if type(plan.team_names_2026) is not bool:
        raise ValueError("team_names_2026 must be boolean")
    if type(plan.weather_plan) is not str:
        raise ValueError("Choose a saved weather plan JSON file, or leave climate edits off.")
    if type(plan.weather_haze) is not bool:
        raise ValueError("Existing dry-weather haze response must be Off or On.")
    if type(plan.modern_color) is not bool:
        raise ValueError("Modern colour and lighting must be Off or On.")
    from . import nfl2k5_modern_color as colour
    colour.normalize_settings(plan.modern_color_settings)
    if type(plan.trim_intro_videos) is not bool:
        raise ValueError("Trim intro videos must be Off or On.")
    if type(plan.custom_intro) is not str:
        raise ValueError("Custom intro video must be the path of a movie file, or empty.")
    plan = replace(plan, custom_intro=plan.custom_intro.strip())
    if type(plan.modern_arrowhead) is not bool:
        raise ValueError("Modern Arrowhead must be Off or On.")
    if type(plan.modern_metlife) is not bool:
        raise ValueError("Modern MetLife Stadium must be Off or On.")
    if type(plan.modern_venues_2026) is not str:
        raise ValueError("2026 venue art must be the folder of team venue art, or empty.")
    plan = replace(plan, modern_venues_2026=plan.modern_venues_2026.strip())
    if type(plan.super_bowl_user_art) is not str:
        raise ValueError("Your Super Bowl logos must be a folder, or empty.")
    plan = replace(plan, super_bowl_user_art=plan.super_bowl_user_art.strip())
    if type(plan.modern_metlife_model) is not bool:
        raise ValueError("Modern MetLife model must be Off or On.")
    if type(plan.modern_helmets) is not bool:
        raise ValueError("Modern helmets must be Off or On.")
    if plan.modern_helmets and plan.guardian_cap:
        raise ValueError("Modern helmets add details to helmet C; turn the Guardian helmet C trial off (the Guardian "
                         "overlay works with Modern helmets).")
    if type(plan.modern_sofi) is not bool:
        raise ValueError("SoFi Stadium must be Off or On.")
    if type(plan.modern_highmark) is not bool:
        raise ValueError("Highmark Stadium must be Off or On.")
    if type(plan.modern_att) is not bool:
        raise ValueError("AT&T Stadium must be Off or On.")
    if type(plan.modern_levis) is not bool:
        raise ValueError("Levi's Stadium must be Off or On.")
    if type(plan.modern_allegiant) is not bool:
        raise ValueError("Allegiant Stadium must be Off or On.")
    if type(plan.modern_mercedes_benz) is not bool:
        raise ValueError("Mercedes-Benz Stadium must be Off or On.")
    if type(plan.modern_usbank) is not bool:
        raise ValueError("U.S. Bank Stadium must be Off or On.")
    if type(plan.modern_lucas_oil) is not bool:
        raise ValueError("Lucas Oil Stadium must be Off or On.")
    if type(plan.modern_state_farm) is not bool:
        raise ValueError("State Farm Stadium must be Off or On.")
    if type(plan.modern_hard_rock) is not bool:
        raise ValueError("Hard Rock Stadium must be Off or On.")
    if type(plan.modern_gillette) is not bool:
        raise ValueError("Gillette Stadium must be Off or On.")
    if type(plan.modern_lambeau) is not bool:
        raise ValueError("Lambeau Field must be Off or On.")
    if type(plan.modern_everbank) is not bool:
        raise ValueError("EverBank Stadium must be Off or On.")
    if type(plan.modern_everbank_construction) is not bool:
        raise ValueError("EverBank Stadium's 2026 construction must be Off or On.")
    if type(plan.modern_board_kit) is not bool:
        raise ValueError("Modern stadium boards must be Off or On.")
    if type(plan.modern_practice_field) is not bool:
        raise ValueError("Modern practice facility must be Off or On.")
    if type(plan.modern_practice_field_team_logo) is not bool:
        raise ValueError("The practicing team's logo at midfield must be Off or On.")
    if plan.modern_practice_field_team_logo and not plan.modern_practice_field:
        raise ValueError("The practicing team's logo at midfield needs the Modern practice facility.")
    if type(plan.modern_surfaces) is not bool:
        raise ValueError("Modern playing surfaces must be Off or On.")
    if type(plan.espn_marks_2026) is not bool:
        raise ValueError("ESPN presentation marks (2026) must be Off or On.")
    if (plan.espn_marks_2026 and plan.hires_pack and isinstance(plan.hires_families, (tuple, list))
            and "scorebug" in plan.hires_families):
        # b76 c1: still a real conflict. The family rewrites shield_espn (one of the four marks) and score_buga
        # (chunk 53); the Hi-res writer re-lays gamedata.iff around the new score_buga, which moves z_ESPN_bug
        # (chunk 57) and changes the outer's size even at 1x, while the marks are pinned to the retail layout.
        raise ValueError("ESPN presentation marks (2026) and the Hi-res scorebug family cannot be combined: both "
                         "rewrite shield_espn, and the Hi-res scorebug re-lays GAMEDATA, which moves the marks off "
                         "their retail positions. Select one.")
    if type(plan.espn_wipes_boards_2026) is not bool:  # b76-p2
        raise ValueError("ESPN 2026 wipes and boards must be Off or On.")
    if type(plan.kick_meter_2026) is not bool:  # b76-km
        raise ValueError("Kick meter (2026 ESPN style) must be Off or On.")
    if type(plan.indicator_names_folder) is not str:
        raise ValueError("Indicator names folder must be a path or empty.")
    if plan.indicator_names_style not in ("retail", "retail_persistent", "scorebug"):
        raise ValueError("Player name label must be retail, retail_persistent or scorebug.")
    if plan.indicator_names_style != "retail":
        if not tt.is_disc_image(plan.source):
            raise ValueError("The player name label styles need a disc image.")
    if plan.indicator_names_style == "scorebug":
        if not plan.indicator_names_folder:
            raise ValueError("The scorebug player name label needs its indicator atlas folder.")
        from . import nfl2k5_indicator_names as indicator_names
        indicator_names.compile_font(plan.indicator_names_folder)
    if type(plan.modern_goalposts) is not bool:  # b77-v1
        raise ValueError("Modern goalposts must be Off or On.")
    if type(plan.modern_coaches) is not bool:  # b77-co1
        raise ValueError("2026 head coaches must be Off or On.")
    if type(plan.hair_styles) is not bool:  # b775-hs1
        raise ValueError("Hair styles must be Off or On.")
    if type(plan.play_art_routes) is not bool:  # b776-pa2
        raise ValueError("Full-length play art routes must be Off or On.")
    if type(plan.run_blocking) is not bool:  # b777-ol1
        raise ValueError("Run blocking must be Off or On.")
    if type(plan.weekly_progression) is not bool:  # b778-pg1
        raise ValueError("Weekly player progression must be Off or On.")
    if type(plan.modern_force_out) is not bool:  # b778-fo1
        raise ValueError("Modern sideline catches must be Off or On.")
    if type(plan.crib_trophy_room) is not bool:  # b778-xs1
        raise ValueError("The Crib Trophy Room cut must be Off or On.")
    if type(plan.module_loader) is not bool:  # b778-xs1
        raise ValueError("On-demand Career Home must be Off or On.")
    if plan.module_loader and not (plan.my_career and plan.my_career_home and not plan.music_library):  # b778-xs1
        raise ValueError("On-demand Career Home needs MyCareer with Career Home (and no jukebox music library).")
    if type(plan.inbox_standings) is not bool:
        raise ValueError("Inbox standings must be Off or On.")
    if type(plan.rookie_faces) is not bool:  # b778-rh1
        raise ValueError("Rookie faces must be Off or On.")
    if type(plan.alien_prospect) is not bool:  # b778-ee1
        raise ValueError("The alien prospect must be Off or On.")
    if type(plan.star_retention) is not bool:  # b778-fa1
        raise ValueError("CPU clubs keep their stars must be Off or On.")
    if type(plan.practice_injuries) is not bool:  # b778-pi1
        raise ValueError("Franchise practice injuries must be Off or On.")
    if type(plan.cpu_ball_carriers) is not bool:  # b778-ai5
        raise ValueError("CPU ball carriers must be Off or On.")
    if type(plan.sportscenter_lineup) is not bool:
        raise ValueError("SportsCenter highlight lineups must be Off or On.")
    if type(plan.franchise_draft_clock) is not bool:  # b778-dr1
        raise ValueError("The franchise draft clock must be Off or On.")
    if type(plan.player_progress) is not bool:  # b778-pg2
        raise ValueError("The Player Progress screen must be Off or On.")
    if type(plan.player_progress_visible) is not bool:  # b778-pg3
        raise ValueError("The Player Progress row must be Off or On.")
    if type(plan.contract_college_guard) is not bool:  # b778-cr1
        raise ValueError("The Player Contracts college guard must be Off or On.")
    if type(plan.sim_cb_tackles) is not bool:  # b778-cb1
        raise ValueError("Cornerback tackle credit must be Off or On.")
    if type(plan.sim_stats) is not bool:  # b778-sim1
        raise ValueError("The franchise sim pace fix must be Off or On.")
    if type(plan.modern_clock_led) is not bool:  # b778-sd4
        raise ValueError("Modern clock digits must be Off or On.")
    if plan.hair_styles and plan.guardian_overlay:  # b775-hs1
        raise ValueError("Hair styles and the Guardian cap overlay cannot be combined yet: both grow the player models "
                         "and the overlay pins their retail positions. Turn one of them off.")
    for key, label in (("cpu_qb_zone_windows", "CPU QB respects zone defenders"),  # b776-ai2
                       ("cpu_qb_recheck", "CPU QB re-checks his read before throwing"),
                       ("db_ball_play", "Defenders break on the thrown ball"),
                       ("qb_accuracy", "Accurate short throws and throws on the run")):  # b777-qb3
        if type(getattr(plan, key)) is not bool:
            raise ValueError(f"{label} must be Off or On.")
    if type(plan.modern_fans) is not bool:  # b77-fr1
        raise ValueError("2026 fans must be Off or On.")
    if plan.team_number_scale:  # b776-ns1
        number_scale = _core_module("nfl2k5_team_number_scale")
        if number_scale is None:
            raise ValueError("The per-kit jersey number size needs nfl2k5_team_number_scale.")
        plan.team_number_scale = number_scale.normalize(plan.team_number_scale)
    elif not isinstance(plan.team_number_scale, dict):
        raise ValueError("Jersey number sizes must be an object of kit: scale.")
    if type(plan.modern_officials) is not bool:  # b77-rf1
        raise ValueError("2025-26 officials must be Off or On.")
    if (plan.kick_meter_2026 and plan.hires_pack and isinstance(plan.hires_families, (tuple, list))
            and "scorebug" in plan.hires_families):
        # The Hi-res scorebug family re-lays gamedata.iff around a larger score_buga (chunk 53), which moves the
        # three kick meter scenes (chunks 75 to 77) off the retail positions their pins name.
        raise ValueError("Kick meter (2026 ESPN style) and the Hi-res scorebug family cannot be combined: the Hi-res "
                         "scorebug re-lays GAMEDATA, which moves the kick meter scenes off their retail positions. "
                         "Select one.")
    plan = replace(plan, weather_plan=plan.weather_plan.strip())
    if type(plan.espn25_plan) is not str:
        raise ValueError("espn25_plan must be text: the path of a saved ESPN Anniversary plan, or empty")
    plan = replace(plan, espn25_plan=plan.espn25_plan.strip())
    if type(plan.espn25_rosters) is not bool:
        raise ValueError("espn25_rosters must be boolean")
    if type(plan.historic_rosters_2026) is not bool:
        raise ValueError("historic_rosters_2026 must be boolean")
    if plan.historic_rosters_2026:
        from . import nfl2k5_historic_rosters
        nfl2k5_historic_rosters.require_build_ready()
        if not plan.historic_teams_quick_game:
            raise ValueError('Historic season rosters require historic local Team Select')
    if plan.espn25_rosters and plan.espn25_plan:
        raise ValueError("Choose Historic moment rosters or a saved ESPN Anniversary plan, not both")
    if type(plan.espn25_era_rules) is not bool:
        raise ValueError("espn25_era_rules must be boolean")
    if type(plan.team_ratings) is not bool:
        raise ValueError("team_ratings must be boolean")
    if plan.team_ratings and not plan.position_pools:
        pools = _core_module("nfl2k5_position_pools")
        if pools is None or pools.status(_xbe_bytes(plan.source)) != "applied":
            raise ValueError("Modern team ratings require modern position pools")
    if type(plan.coach_ai) is not bool:
        raise ValueError("coach_ai must be boolean")
    if plan.coach_ai and not tt.is_disc_image(plan.source):
        raise ValueError("Automatic coach AI needs a disc image so profiles can match the final playbooks")
    if plan.historic_stock_books and plan.playbook_pair:
        raise ValueError("Stock historical books cannot be combined with separate offensive and defensive book selections")
    if plan.espn25_era_rules and not (plan.espn25_more_moments and plan.dynamic_kickoff and plan.defensive_try and plan.overtime):
        raise ValueError("Era rules require the expanded Anniversary collection, dynamic kickoff, defensive tries and modern overtime as the base")
    if type(plan.historic_stock_books) is not bool or type(plan.espn25_named_previews) is not bool:
        raise ValueError("historical book and preview options must be boolean")
    if plan.espn25_named_previews and not plan.espn25_more_moments:
        raise ValueError("Named Anniversary previews require the expanded Anniversary collection")
    if type(plan.espn25_more_moments) is not bool:
        raise ValueError("espn25_more_moments must be boolean")
    if plan.espn25_more_moments and plan.espn25_plan:
        raise ValueError("Choose the expanded Anniversary collection or a saved ESPN Anniversary plan, not both")
    tt._validate_lever_flags(plan.coverage_slider, plan.scramble_tuning, plan.flatter_deep_ball, plan.chop_block_toggle)
    if plan.flatter_deep_ball:
        if plan.arc or plan.realistic_flight or plan.arc_by_distance:
            raise ValueError("Flatter flight must be selected on its own; choose one flight option")
        plan = replace(plan, throw=True, max_deep_yards=plan.max_deep_yards if plan.throw else 80.0)
    if plan.throw:
        tt.TuningSettings(plan.max_deep_yards, plan.arc,
                          plan.realistic_flight, plan.arc_by_distance).validated()
    uniform_choice_mode(plan.uniform_choice)
    if type(plan.team_sleeves) is not bool:
        raise ValueError("team_sleeves must be boolean")
    if plan.team_sleeves and not tt.is_disc_image(plan.source):
        raise ValueError("Team-coloured sleeves need a disc image (the sleeve textures live in the uniform packages)")
    if plan.team_sleeves and _core_module("nfl2k5_team_sleeves") is None:
        raise ValueError("The team-coloured sleeves writer is not available in this installation")
    if type(plan.hires_pack) is not bool:
        raise ValueError("hires_pack must be boolean")
    if type(plan.hires_scale) is not int or plan.hires_scale not in (1, 2):
        raise ValueError("hires_scale must be the integer 1 or 2")
    if not isinstance(plan.hires_folder, str) or not isinstance(plan.hires_target, str):
        raise ValueError("Hi-res folder and target must be text")
    if plan.scorebug_watermark not in ("auto", "mnf", "off"):
        raise ValueError("ESPN watermark must be auto, mnf or off")
    if not isinstance(plan.scorebug_folder, str):
        raise ValueError("The scorebar artwork folder must be text")
    plan = replace(plan, scorebug_folder=plan.scorebug_folder.strip())
    if plan.scorebug or plan.scorebug_runtime:
        from .runtime_dependencies import require_numpy
        require_numpy("Scorebug build")
    if plan.scorebug_folder:
        if not plan.scorebug:
            raise ValueError("A scorebar artwork folder needs the ESPN scorebar option")
        if plan.scorebug_runtime:
            sprite = _core_module("nfl2k5_scorebug_sprite")
            if sprite is None:
                raise ValueError("The sprite scorebug compiler is missing; update this installation")
            sprite.compile_folder(plan.scorebug_folder,watermark=plan.scorebug_watermark)
        if not tt.is_disc_image(plan.source):
            raise ValueError("A scorebar artwork folder needs a disc image source")
    if not isinstance(plan.hires_families, (tuple, list)) or any(type(x) is not str for x in plan.hires_families):
        raise ValueError("Hi-res families must be a list of family names")
    families = tuple(plan.hires_families)
    hires_module = _core_module("nfl2k5_hires_pack")
    known_families = set(hires_module.FAMILIES) if hires_module is not None else set(families)
    if len(set(families)) != len(families) or set(families) - known_families:
        raise ValueError("Unknown or duplicate Hi-res family selection")
    if plan.hires_pack and hires_module is None:
        raise ValueError("The Hi-res pack is not available in this installation")
    if plan.team_sleeves and plan.hires_pack and "jerseys" in families:
        # The Hi-res jerseys family pins the complete 768-byte player texture binding table; row 36's
        # context-first word is exactly what the sleeve change edits, so the two cannot both be checked.
        raise ValueError("Team-coloured sleeves change the player texture binding table that the Hi-res "
                         "jerseys family pins; turn one of the two options off")
    if plan.hires_pack and not families:
        raise ValueError("Select at least one Hi-res family")
    plan = replace(plan, hires_families=families)
    if plan.coach_ai:
        plan = replace(plan, cpu_money_downs="modern2", xbe_space=True)
    legacy_disabled = momentum_on and plan.accel_ramp
    if momentum_on:
        plan = replace(plan, accel_ramp=False)
    if (momentum_on or plan.read_option_runtime or plan.guardian_overlay or plan.my_career or plan.screen_hooks or plan.coverage_trail or plan.franchise_edit_player or plan.cpu_money_downs != "retail" or plan.accelerated_clock or plan.coin_defer or plan.decided_clock or plan.cpu_scrambles == "modern" or plan.weekly_prep or plan.weekly_prep_cpu or plan.weekly_prep_remember or plan.coach_ai or plan.playbook_pair or plan.deep_zone_facing or plan.deep_zone_bail or plan.reserves_16 or plan.created_teams_extra or plan.defensive_try or plan.zone_drop_cap or plan.all_stadiums or plan.coverage_slider or plan.scramble_tuning
            or plan.music_shuffle or plan.practice_squad_screen or plan.abilities or plan.qb_spy or plan.calendar_engine or plan.franchise_autosave
            or plan.historic_teams_quick_game or plan.espn25_more_moments or plan.historic_stock_books or plan.espn25_era_rules or plan.k128_memory or plan.letter_grades or plan.honors_page):
        plan = replace(plan, xbe_space=True)
    if plan.franchise_edit_player:
        plan = replace(plan, position_row=True, xbe_space=True)
    if plan.weekly_prep_cpu or plan.weekly_prep_remember:
        plan = replace(plan, weekly_prep=True, xbe_space=True)
    if plan.my_career and plan.my_career_setup is None:
        plan = replace(plan, draft_ai=True, depth_locks=True)  # generic MyCareer (M3 draft) reuses the draft-AI implementation
    if plan.my_career and plan.my_career_setup:
        # Tiered prepared careers carry initial rank/side locks. Keep those
        # locks through native depth sorting; ordinary creation is unchanged.
        if struct.unpack_from("<I", r62["my_career_setup"], 212)[0]:
            plan = replace(plan, depth_locks=True)
    if type(plan.deep_zone_bail_calls) not in (tuple, list) or plan.deep_zone_bail_calls:
        raise ValueError("Press corner bail authoring calls are not staged by this build; leave deep_zone_bail_calls empty "
                         "(the runtime bail option serves an already authored press call)")
    if plan.deep_zone_facing or plan.deep_zone_bail:
        plan = replace(plan, xbe_space=True)
    if plan.scorebug_runtime:
        plan = replace(plan, scorebug=True, xbe_space=True)
    if plan.kickoff_relocated:
        plan = replace(plan, xbe_space=True, dynamic_kickoff=True)
    if plan.dynamic_kickoff:
        # record the effective dependencies in the recipe: the modern spots, never the power-only variant, the line-up
        plan = replace(plan, kick_rules=True, kick_power=False, kickoff_alignment=True)
    source, target = require_build_source(plan.source), platform_compat.io_path(plan.target)
    if platform_compat.paths_alias(target, source):
        raise ValueError("target must not be the source")
    if target.exists() and not plan.overwrite:
        raise FileExistsError(f"{target} exists")
    receipt: dict[str, Any] = {"plan": plan.to_recipe(), "steps": [], "source": str(source), "target": str(target)}
    receipt["seven_on_seven_opt_in_ignored"] = seven_held
    receipt["legacy_accel_ramp_disabled_by_momentum_profile"] = bool(legacy_disabled)
    is_image = tt.is_disc_image(source)
    if plan.playbook_packs and is_image:
        # First, while it costs seconds: the checks below run for minutes before the packs are installed.
        check_playbook_pack_fit(source, plan.playbook_packs, progress)
    try:
        installed_xbe = _xbe_bytes(source)
    except (OSError, ValueError):
        # The selected writer owns malformed/missing executable refusal.
        installed_xbe = None
    retire_seven = False
    if not SEVEN_ON_SEVEN_RELEASED and installed_xbe is not None:
        seven = tt.seven_on_seven_patch
        # Recognize any installed span, then demand a complete, digest-valid
        # installation before copying. This also refuses mixed old installs.
        try:
            retire_seven = any(installed_xbe[off:off + len(after)] == after
                               for _label, off, _before, after in seven._located(installed_xbe))
        except (ValueError, struct.error):
            # As above, malformed executable refusal belongs to the selected
            # writer; retirement must not mask unrelated plan preflight errors.
            retire_seven = False
        if retire_seven:
            seven.remove(installed_xbe)
    if r62.get("anniversary_kickoff") is None:
        r62["anniversary_kickoff"] = _anniversary_kickoff_wanted(plan, is_image)
    if r62["anniversary_kickoff"]:
        if not (plan.dynamic_kickoff and is_image):
            raise ValueError("The 25th Anniversary retail kickoff gate needs the dynamic kickoff and a disc image")
        gate = tt.anniversary_kickoff_patch
        try:
            # A source whose executable already carries the gate keeps its tables (a rebuild over a built disc);
            # otherwise the retail Kickoff/Kick Return records and return chains are read once from the source
            # (never distributed).
            tables = gate.installed_tables(installed_xbe) if installed_xbe is not None else None
            r62["anniversary_kickoff_tables"] = tables if tables is not None else gate.disc_tables(source)
        except Exception as exc:  # noqa: BLE001 - a source without retail special-teams data builds as before
            # e.g. a built disc as the source (its return plays already carry the 2026 chains): the 25th Anniversary
            # then keeps the 2026 kickoff, exactly as before this gate existed, and the receipt says why.
            r62["anniversary_kickoff"], r62["anniversary_kickoff_tables"] = False, None
            receipt["anniversary_kickoff"] = {"status": "skipped", "reason": f"{type(exc).__name__}: {exc}"}
            progress(f"25th Anniversary retail kickoff not installed: {exc}", 0, 0)
    if r62.get("widescreen_menus") is None:
        r62["widescreen_menus"] = _widescreen_menus_wanted(plan, is_image)
    if r62.get("team_logo_swap") is None:
        r62["team_logo_swap"] = _team_logo_swap_wanted(plan, is_image)
    if r62.get("period_goalposts") is None:
        r62["period_goalposts"] = _period_goalposts_wanted(plan, is_image)
    if plan.modern_practice_field_team_logo and not r62["team_logo_swap"]:
        raise ValueError("The practicing team's logo at midfield needs the Modern practice facility on a disc image.")
    if plan.kickoff_return_blocking and not r62.get("anniversary_kickoff"):
        # E1 lives in the 25th Anniversary gate's allocation: the dynamic kickoff on a disc image from a retail source.
        raise ValueError("Return blockers claiming distinct men need the dynamic kickoff on a disc image built from "
                         "the retail disc (the rule rides with the 25th Anniversary kickoff gate)")
    if installed_xbe is not None:
        tt._check_installed_runtime_settings(installed_xbe, r62)
    if (plan.xbe_space or plan.kickoff_relocated) and not is_image:
        raise ValueError("experimental extra patch space needs a disc image")
    naming_digest = None
    if plan.modern_naming and not is_image:
        raise ValueError("Modern mode names need a disc image")
    if is_image:
        naming_digest = tt._naming_source_preflight(source, plan.modern_naming)
    if plan.trim_intro_videos:
        if not is_image:
            raise ValueError("Trim intro videos needs a disc image")
        intro = _core_module("nfl2k5_intro_videos")
        if intro is None:
            raise RuntimeError("Trim intro videos is unavailable in this build")
        intro.plan(source)
    if plan.crib_reclaim:
        if not is_image:
            raise ValueError("Crib movie cut needs a disc image")
        tt.crib_reclaim_patch.plan(source)
    if plan.custom_intro:
        if not is_image:
            raise ValueError("Custom intro video needs a disc image")
        custom_intro = _core_module("nfl2k5_custom_intro")
        if custom_intro is None:
            raise RuntimeError("Custom intro video is unavailable in this build")
        custom_intro.preflight(source, plan.custom_intro)
    if plan.hires_pack:
        if plan.hires_target != "xemu-64":
            raise ValueError("128 MiB support has not been proved")
        if not is_image:
            raise ValueError("Hi-res packs need a disc image")
        hires = _core_module("nfl2k5_hires_pack")
        if hires is None:
            raise RuntimeError("Hi-res packs are unavailable in this build")
        receipt["hires_budget"] = hires.preflight_budget(plan.hires_folder, scale=plan.hires_scale,
                                                       target=plan.hires_target, families=plan.hires_families)
        preview = hires.inspect_image(source, plan.hires_folder, scale=plan.hires_scale, target=plan.hires_target,
                                      families=plan.hires_families)
        if any(row["family"] == "scorebug" for row in preview["assets"]) and (plan.scorebug or plan.scorebug_runtime):
            raise ValueError("The Hi-res scorebug conflicts with the ESPN scorebar or scorebug effects; select one")
        receipt["hires_preflight"] = preview
    if plan.scorebug and not plan.scorebug_runtime and tt.is_disc_image(source):
        # beta 62: check every template PNG, its palette, the fixed-span fit and the source identity
        # before a multi-gigabyte copy; the output-side transaction preflights again on the composed bytes.
        # Plan-level refusals such as the Hi-res scorebug conflict come first; this one parses the image.
        scorebar = _core_module("nfl2k5_scorebug_ingame")
        if scorebar is not None and hasattr(scorebar, "image_plan"):
            with open(source, "rb") as stream:
                scorebar.image_plan(stream.fileno(), os.fstat(stream.fileno()).st_size,
                                    scorebug_folder=plan.scorebug_folder or None)

    if plan.espn25_rosters:
        if not is_image:
            raise ValueError("Historic moment rosters need a disc image")
        # e1 (2026-09-23): One-pool positions no longer conflict. The pools step reclassifies the historic ROSTs
        # before the final roster pass, and that pass compiles onto the reclassified layout (pinned per resource).
        module = _core_module("nfl2k5_espn25_rosters")
        if module is None:
            raise RuntimeError("Historic moment rosters are unavailable in this build")
        module.require_build_ready()
        _, roster_preview = module.apply(module.read_resources(source))
        receipt["espn25_rosters_preflight"] = roster_preview
    if is_image and (plan.espn25_rosters or plan.espn25_more_moments or (plan.classic_teams and plan.historic_teams_quick_game)):
        # b776-fs1: every moment face scan must read from this retail source and fit its unused head id.
        scans_module = _core_module("nfl2k5_moment_scans")
        if scans_module is None:
            raise RuntimeError("The moment face scans module is unavailable in this build")
        # b776-disc2: in a project build `source` is the project-built image (2026 faces already written), so read the
        # user's retail game here, as the moment_scans step does.
        scans_retail = source if _retail_source is None else _retail_source
        planned = scans_module.plan(scans_retail, scans_retail, photos=frozenset())
        receipt["moment_scans_preflight"] = {"spans": len(planned), "pairs": len(scans_module.load())}
    if plan.team_names_2026:
        names = _core_module("nfl2k5_team_names_2026")
        if names is None:
            raise RuntimeError("The 2026 team-name module is unavailable")
        if not is_image:
            raise ValueError("2026 team names need a disc image; existing saves keep their names")
        if names.image_status(source) not in ("retail", "applied"):
            raise ValueError("2026 team names need the original names or this exact grouped patch")
        if names.xbe_status(_xbe_bytes(source)) not in ("retail", "applied"):
            raise ValueError("2026 team names need the original team lookups in default.xbe or this exact patch")
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
    if plan.honors_history and not is_image:
        raise ValueError("the award history needs a disc image (the roster template lives in pack 0)")
    if plan.prospect_names and not is_image:
        raise ValueError("modern prospect names need a disc image (the name pool lives in the roster template in pack 0)")
    if plan.player_tags and not is_image:
        raise ValueError("star tags need a disc image (the roster records live in pack 0)")
    if plan.roster_edits and not is_image:
        raise ValueError("roster edits need a disc image (the roster records live in pack 0)")
    if plan.roster_edits and not plan.position_pools:
        # fx1 (review pr67 #3): this refusal was only reached after every image writer had run
        records = _core_module("nfl2k5_roster_records")
        if records is not None and "roster_refresh" in records.read_edits(Path(plan.roster_edits)):
            raise ValueError("Dated roster refresh requires modern position pools")
    loaded_espn25_plan = None
    if plan.espn25_plan:
        espn = _core_module("nfl2k5_espn25_scenarios")
        if espn is None:
            raise RuntimeError("the ESPN Anniversary module is not available in this build")
        if not is_image:
            raise ValueError("ESPN Anniversary edits need a disc image (the scenarios and historic rosters live in pack 0)")
        if plan.reserves_16 or plan.created_teams_extra:
            # the plan pins the current (retail) main-roster wrapper geometry; the version-18 arena
            # growth rewrites it, so the two are refused together rather than resolved by guesswork
            raise ValueError("ESPN Anniversary edits cannot be combined with the roster arena growth "
                             "(16 reserves or extra created teams): the plan pins the current main roster geometry")
        if plan.position_pools:
            # the pool reclassify recodes every historic ROST too; this editor reads historic positions
            # as retail only, so a conflicting recode is refused instead of reinterpreted
            raise ValueError("ESPN Anniversary edits cannot be combined with the merged position pools: "
                             "the reclassify recodes the shared historic rosters this plan pins")
        espn_path = Path(plan.espn25_plan)
        if not espn_path.is_file():
            raise ValueError(f"the ESPN Anniversary plan is missing: {espn_path}")
        try:
            # loaded exactly once (bounded, duplicate-key-rejecting reader); the detached value is
            # kept for the final pass, and the plan is resolved against the source before any copy
            loaded_espn25_plan = espn.read_json(espn_path)
            progress("Checking the ESPN Anniversary plan against the source", 0, 0)
            espn.resolve_plan(espn.Catalog.load(source), loaded_espn25_plan)
        except ValueError as exc:
            raise ValueError(f"ESPN Anniversary plan refused: {exc}. Re-author the plan in Rosters > ESPN "
                             "Anniversary against this source (its scenario text and historic rosters must "
                             "match the plan)") from exc
    loaded_weather_plan = None
    if plan.weather_plan:
        weather = _core_module("nfl2k5_weather")
        if weather is None:
            raise ValueError("Climate editing is not included in this release. Turn it off or install a complete release.")
        if not is_image:
            raise ValueError("Climate edits need a full game disc. Choose your disc instead of default.xbe.")
        if plan.reserves_16 or plan.created_teams_extra:
            raise ValueError("Climate edits support the version-17 roster table. Turn off 16 reserves and extra created teams, then build again.")
        try:
            loaded_weather_plan = weather.read_json(Path(plan.weather_plan))
            if not isinstance(loaded_weather_plan, dict) or not loaded_weather_plan.get("changes"):
                raise ValueError("The saved plan has no climate changes")
            progress("Checking saved climate edits against the source", 0, 0)
            weather.apply(weather.load_resource(source), loaded_weather_plan)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Climate edits cannot be used: {exc}. Open Weather editor on this source and save the edits again.") from exc
    if plan.weather_haze:
        haze = _core_module("nfl2k5_weather_haze")
        if haze is None or haze.status(_xbe_bytes(source)) not in ("retail", "applied"):
            raise ValueError("The dry-weather haze reader is not recognized. Turn this option off or rebuild from a supported USA source.")
    if plan.number_kerning:  # b76-k2
        kerning = _core_module("nfl2k5_number_kerning")
        if kerning is None or kerning.status(_xbe_bytes(source)) not in ("retail", "applied"):
            raise ValueError("The jersey number binder is not recognized. Turn number kerning off or rebuild from a supported USA source.")
    if plan.modern_color:
        modern = _core_module("nfl2k5_modern_color")
        if modern is None or not is_image:
            raise ValueError("Modern colour and lighting needs a disc image (the stadium bundles live in the archive packs).")
        previous_colour = modern.read_image_receipt(source)
        previous_settings = previous_colour["settings"] if previous_colour else None
        if modern.xbe_status(_xbe_bytes(source), previous_settings) not in ("retail", "applied", "applied (custom)"):
            raise ValueError("The light rigs are not recognized. Choose the original retail source.")
        progress("Checking the stadium bundles for Colour & lighting", 0, 0)
        modern.check_image_request(source, plan.modern_color_settings, receipt=previous_colour)
    elif is_image:
        modern = _core_module("nfl2k5_modern_color")
        if modern is not None:
            previous_colour = modern.read_image_receipt(source)
            previous_settings = previous_colour["settings"] if previous_colour else None
            try:
                source_colour_state = modern.xbe_status(_xbe_bytes(source), previous_settings)
            except (OSError, ValueError):
                source_colour_state = "unknown"
            if previous_colour is not None or source_colour_state == "applied":
                raise ValueError("This disc already has a colour grade. Choose the original retail disc as the source to turn it off or reset it.")
    if plan.modern_arrowhead:
        arrowhead = _core_module("nfl2k5_modern_arrowhead")
        if arrowhead is None or not is_image:
            raise ValueError("Modern Arrowhead needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Arrowhead packages", 0, 0)
        try:
            arrowhead_state = arrowhead.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern Arrowhead cannot read the stadium packages: {exc}") from exc
        if arrowhead_state not in ("retail", "applied"):
            raise ValueError("The Arrowhead packages are not the supported retail or already-modern set. Turn Modern Arrowhead off or rebuild from a supported USA source.")
    if plan.modern_metlife:
        metlife = _core_module("nfl2k5_modern_metlife")
        if metlife is None or not is_image:
            raise ValueError("Modern MetLife Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Giants Stadium and Jets Stadium packages", 0, 0)
        try:
            metlife_state = metlife.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern MetLife Stadium cannot read the stadium packages: {exc}") from exc
        if metlife_state not in ("retail", "applied"):
            raise ValueError("The Giants Stadium and Jets Stadium packages are not the supported retail or already-MetLife set. Turn Modern MetLife Stadium off or rebuild from a supported USA source.")
    if plan.modern_venues_2026:
        venues26 = _core_module("nfl2k5_modern_venues_2026")
        if venues26 is None or not is_image:
            raise ValueError("2026 venue art needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the 2026 venue art and the home stadium packages", 0, 0)
        try:
            venues26.check_request(source, plan.modern_venues_2026, modern_arrowhead=plan.modern_arrowhead,
                                   sofi=plan.modern_sofi, highmark=plan.modern_highmark, att=plan.modern_att,
                                   levis=plan.modern_levis, allegiant=plan.modern_allegiant,
                                   mercedes_benz=plan.modern_mercedes_benz,
                                   usbank=plan.modern_usbank,
                                   lucas_oil=plan.modern_lucas_oil, state_farm=plan.modern_state_farm,
                                   hard_rock=plan.modern_hard_rock, gillette=plan.modern_gillette,
                                   lambeau=plan.modern_lambeau, everbank=plan.modern_everbank)
        except (OSError, ValueError) as exc:
            raise ValueError(f"2026 venue art: {exc}") from exc
    if plan.modern_metlife_model:
        # b76-u5: the model is written over the skin's stadium scene, so the skin runs first in the same build
        # (or the source already carries it).
        metlife_model = _core_module("nfl2k5_metlife_model")
        if metlife_model is None or not is_image:
            raise ValueError("Modern MetLife model needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the MetLife model's packages", 0, 0)
        try:
            model_state = metlife_model.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern MetLife model cannot read the stadium packages: {exc}") from exc
        if model_state == "retail" and not plan.modern_metlife:
            raise ValueError("Modern MetLife model needs Modern MetLife Stadium in the same build.")
        if model_state not in ("retail", "skin", "applied"):
            raise ValueError("The Giants and Jets packages are not a supported retail, MetLife or MetLife model set. Turn Modern MetLife model off or rebuild from a supported USA source.")
    if plan.modern_helmets:
        # b76-hm: same-size writes in the common player group (outer 3) and the historic team files; the Guardian
        # overlay may be on the source already or come in the same build (the two edits commute).
        helmets = _core_module("nfl2k5_modern_helmets")
        if helmets is None or not is_image:
            raise ValueError("Modern helmets needs a disc image (the player models live in the archive packs).")
        progress("Checking the player models for Modern helmets", 0, 0)
        helmets_state = helmets.image_status(source)
        if helmets_state not in ("retail", "applied"):
            raise ValueError("The player models are not a supported retail, Modern helmets or Guardian overlay set. "
                             "Turn Modern helmets off or rebuild from a supported USA source.")
    if plan.modern_sofi:
        # b76-u6: SoFi Stadium writes the Rams and Chargers packages whole (field, stadium, cameras) and their two
        # stadium rows; the 2026 venue art leaves those two venues to it.
        sofi = _core_module("nfl2k5_sofi_model")
        if sofi is None or not is_image:
            raise ValueError("SoFi Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Rams and Chargers stadium packages", 0, 0)
        try:
            sofi.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"SoFi Stadium: {exc}") from exc
    if plan.modern_highmark:
        # b76-st: Highmark Stadium writes the Bills' nine packages whole (field, stadium, cameras, cityscape) and the
        # s03 stadium row; the 2026 venue art leaves s03 to it and lends it the Bills' field art from its folder.
        highmark = _core_module("nfl2k5_highmark_model")
        if highmark is None or not is_image:
            raise ValueError("Highmark Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Bills' stadium packages", 0, 0)
        try:
            highmark.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Highmark Stadium: {exc}") from exc
    if plan.modern_att:
        # b76-st2: AT&T Stadium writes the Cowboys' nine packages whole (field, stadium, cameras) and the s07 stadium
        # row; the 2026 venue art leaves s07 to it and lends it the Cowboys' field art from its folder.
        att = _core_module("nfl2k5_att_model")
        if att is None or not is_image:
            raise ValueError("AT&T Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Cowboys' stadium packages", 0, 0)
        try:
            att.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"AT&T Stadium: {exc}") from exc
    if plan.modern_levis:
        # b76-st2: Levi's Stadium writes the 49ers' nine packages whole (field, collapsed cityscape, stadium, cameras)
        # and the s25 stadium row; the 2026 venue art leaves s25 to it and lends it the 49ers' field art from its folder.
        levis = _core_module("nfl2k5_levis_model")
        if levis is None or not is_image:
            raise ValueError("Levi's Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the 49ers' stadium packages", 0, 0)
        try:
            levis.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Levi's Stadium: {exc}") from exc
    if plan.modern_allegiant:
        # b76-st2: Allegiant Stadium writes the Raiders' nine packages whole (field, collapsed cityscape, stadium, cameras)
        # and the s20 stadium row; the 2026 venue art leaves s20 to it and lends it the Raiders' field art.
        allegiant = _core_module("nfl2k5_allegiant_model")
        if allegiant is None or not is_image:
            raise ValueError("Allegiant Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Raiders' stadium packages", 0, 0)
        try:
            allegiant.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Allegiant Stadium: {exc}") from exc
    if plan.modern_mercedes_benz:
        # b76-st2: Mercedes-Benz Stadium writes the Falcons' nine packages whole (field, stadium, cameras)
        # and the s01 stadium row; the 2026 venue art leaves s01 to it and lends it the Falcons' field art.
        mercedes_benz = _core_module("nfl2k5_mercedes_benz_model")
        if mercedes_benz is None or not is_image:
            raise ValueError("Mercedes-Benz Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Falcons' stadium packages", 0, 0)
        try:
            mercedes_benz.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Mercedes-Benz Stadium: {exc}") from exc
    if plan.modern_usbank:
        # b76-st3: U.S. Bank Stadium writes the Vikings' nine packages whole (field, stadium, cameras) and the s15
        # stadium row; the 2026 venue art leaves s15 to it and lends it the Vikings' field art from its folder.
        usbank = _core_module("nfl2k5_usbank_model")
        if usbank is None or not is_image:
            raise ValueError("U.S. Bank Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Vikings' stadium packages", 0, 0)
        try:
            usbank.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"U.S. Bank Stadium: {exc}") from exc
    if plan.modern_lucas_oil:
        # b76-st3: Lucas Oil Stadium writes the Colts' nine packages whole (field, stadium, cameras) and the s11 stadium
        # row; the 2026 venue art leaves s11 to it and lends it the Colts' field art from its folder.
        lucas_oil = _core_module("nfl2k5_lucas_oil_model")
        if lucas_oil is None or not is_image:
            raise ValueError("Lucas Oil Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Colts' stadium packages", 0, 0)
        try:
            lucas_oil.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Lucas Oil Stadium: {exc}") from exc
    if plan.modern_state_farm:
        # b76-st3: State Farm Stadium writes the Cardinals' nine packages whole (field, collapsed cityscape, stadium,
        # cameras) and the s00 stadium row; the 2026 venue art leaves s00 to it and lends it the Cardinals' field art.
        state_farm = _core_module("nfl2k5_state_farm_model")
        if state_farm is None or not is_image:
            raise ValueError("State Farm Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Cardinals' stadium packages", 0, 0)
        try:
            state_farm.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"State Farm Stadium: {exc}") from exc
    if plan.modern_hard_rock:
        # b76-st4: Hard Rock Stadium writes the Dolphins' nine packages whole (field, collapsed cityscape, stadium,
        # cameras) and the s14 stadium row; the 2026 venue art leaves s14 to it and lends it the Dolphins' field art.
        hard_rock = _core_module("nfl2k5_hard_rock_model")
        if hard_rock is None or not is_image:
            raise ValueError("Hard Rock Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Dolphins' stadium packages", 0, 0)
        try:
            hard_rock.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Hard Rock Stadium: {exc}") from exc
    if plan.modern_gillette:
        # b76-st4: Gillette Stadium writes the Patriots' nine packages whole (field, collapsed cityscape, stadium,
        # cameras) and the s16 stadium row; the 2026 venue art leaves s16 to it and lends it the Patriots' field art.
        gillette = _core_module("nfl2k5_gillette_model")
        if gillette is None or not is_image:
            raise ValueError("Gillette Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Patriots' stadium packages", 0, 0)
        try:
            gillette.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Gillette Stadium: {exc}") from exc
    if plan.modern_lambeau:
        # b76-st4: Lambeau Field writes the Packers' nine packages whole (field, collapsed cityscape, stadium,
        # cameras) and the s10 stadium row; the 2026 venue art leaves s10 to it and lends it the Packers' field art.
        lambeau = _core_module("nfl2k5_lambeau_model")
        if lambeau is None or not is_image:
            raise ValueError("Lambeau Field needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Packers' stadium packages", 0, 0)
        try:
            lambeau.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Lambeau Field: {exc}") from exc
    if plan.modern_everbank:
        # b76-st4: EverBank Stadium writes the Jaguars' nine packages whole (field, collapsed cityscape, stadium,
        # cameras) and the s12 stadium row; the 2026 venue art leaves s12 to it and lends it the Jaguars' field art.
        everbank = _core_module("nfl2k5_everbank_model")
        if everbank is None or not is_image:
            raise ValueError("EverBank Stadium needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the Jaguars' stadium packages", 0, 0)
        try:
            everbank.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"EverBank Stadium: {exc}") from exc
    if plan.modern_board_kit:
        # b76-st5: the modern stadium boards renovate the stadium scenes of the teams still in their 2004 buildings
        board_kit = _core_module("nfl2k5_board_kit")
        if board_kit is None or not is_image:
            raise ValueError("Modern stadium boards need a disc image (the stadium packages live in the archive packs).")
        progress("Checking the renovated stadiums' packages", 0, 0)
        try:
            board_kit.check_request(source, **_board_kit_options(plan))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern stadium boards: {exc}") from exc
    if plan.modern_practice_field:
        # b76-pf: the practice facility writes the nine practice field packages (s32): the field, the detail normal and
        # divots, the collapsed cityscape, the stadium and camera stretch; the row stays retail.
        practice = _core_module("nfl2k5_practice_field_model")
        if practice is None or not is_image:
            raise ValueError("Modern practice facility needs a disc image (the stadium packages live in the archive packs).")
        progress("Checking the practice field packages", 0, 0)
        try:
            practice.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern practice facility: {exc}") from exc
    if plan.modern_surfaces:
        # b76-tf: repaints the playing surface of all 288 home-venue packages after every stadium writer
        surfaces = _core_module("nfl2k5_modern_surfaces")
        if surfaces is None or not is_image:
            raise ValueError("Modern playing surfaces need a disc image (the stadium packages live in the archive packs).")
        progress("Checking the home-venue field packages", 0, 0)
        try:
            surfaces.check_request(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern playing surfaces: {exc}") from exc
    if plan.espn_marks_2026:
        marks = _core_module("nfl2k5_espn_marks")
        if marks is None or not is_image:
            raise ValueError("ESPN presentation marks (2026) need a disc image (the marks live in the archive packs).")
        progress("Checking the ESPN presentation marks", 0, 0)
        try:
            marks.validate_art(plan.official_marks_pack)
            # b76 c1: a source that already carries the sprite scorebug reads through its appended resources
            marks_state = marks.image_status(source, sprite_folder=(plan.scorebug_folder or None) if plan.scorebug_runtime else None)
        except (OSError, ValueError) as exc:
            raise ValueError(f"ESPN presentation marks (2026) cannot read the GAMEDATA marks: {exc}") from exc
        if marks_state not in ("retail", "applied"):
            raise ValueError("The four GAMEDATA marks are not the supported retail or already-2026 set, or GAMEDATA carries resources other than the sprite scorebug's. Turn ESPN presentation marks (2026) off or rebuild from a supported USA source.")
    if plan.espn_wipes_boards_2026:  # b76-p2
        wipes = _core_module("nfl2k5_espn_wipes_boards")
        if wipes is None or not is_image:
            raise ValueError("ESPN 2026 wipes and boards need a disc image (the wipes and boards live in the archive packs).")
        progress("Checking the ESPN wipes and boards", 0, 0)
        try:
            wipes.validate_art(plan.official_marks_pack)
            wipes_state = wipes.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"ESPN 2026 wipes and boards cannot read the presentation scenes: {exc}") from exc
        if wipes_state not in ("retail", "applied"):
            raise ValueError("The replay wipe, the pause scoreboard and the other four scenes are not the supported retail or already-2026 set. Turn ESPN 2026 wipes and boards off or rebuild from a supported USA source.")
    if plan.kick_meter_2026:  # b76-km
        kick_meter = _core_module("nfl2k5_kick_meter_2026")
        if kick_meter is None or not is_image:
            raise ValueError("Kick meter (2026 ESPN style) needs a disc image (the kick meter lives in the archive packs).")
        progress("Checking the kick meter scenes", 0, 0)
        try:
            # a source that already carries the sprite scorebug reads through its appended resources
            kick_state = kick_meter.image_status(source, sprite_folder=(plan.scorebug_folder or None) if plan.scorebug_runtime else None)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Kick meter (2026 ESPN style) cannot read the kick meter scenes: {exc}") from exc
        if kick_state not in ("retail", "applied"):
            raise ValueError("The kick meter, its aim arrow and the wind arrow are not the supported retail or already-2026 set, or GAMEDATA carries resources other than the sprite scorebug's. Turn Kick meter (2026 ESPN style) off or rebuild from a supported USA source.")
    if plan.modern_goalposts:  # b77-v1
        goalposts = _core_module("nfl2k5_modern_goalposts")
        if goalposts is None or not is_image:
            raise ValueError("Modern goalposts need a disc image (the goalpost lives in the archive packs).")
        progress("Checking the goalpost scenes", 0, 0)
        try:
            goal_state = goalposts.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Modern goalposts cannot read the goalpost scenes: {exc}") from exc
        if goal_state not in ("retail", "applied"):
            raise ValueError("The goalpost, its shadow and the executable's goalpost sites are not the supported retail or already-modern set. Turn Modern goalposts off or rebuild from a supported USA source.")
    if plan.team_number_scale:  # b776-ns1: the source executable's jersey-number block must be retail
        number_scale = _core_module("nfl2k5_team_number_scale")
        try:
            number_state = number_scale.status(_xbe_bytes(source))
        except (OSError, ValueError) as exc:
            raise ValueError(f"The per-kit jersey number size cannot read the executable: {exc}") from exc
        if number_state != "retail":
            raise ValueError("The executable's jersey-number block is not the supported retail code (or already carries "
                             "a number-size table). Clear the jersey number sizes or rebuild from a supported USA source.")
    if plan.hair_styles:  # b775-hs1
        hair = _core_module("nfl2k5_hair_styles")
        if hair is None or not is_image:
            raise ValueError("Hair styles need a disc image (the player models live in the archive packs).")
        progress("Checking the player models for hair styles", 0, 0)
        try:
            hair_state = hair.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Hair styles cannot read the player models: {exc}") from exc
        if hair_state not in ("retail", "applied"):
            raise ValueError("The player models, hair textures or the executable's hair hook are not the supported "
                             "retail or already-styled set. Turn Hair styles off or rebuild from a supported USA source.")
    if plan.cpu_qb_zone_windows or plan.cpu_qb_recheck or plan.db_ball_play:  # b776-ai2
        _cpu_ai_preflight(plan, source, progress)
    if plan.qb_accuracy:  # b777-qb3: the pass accuracy routine must be retail or this owner, before any write
        _qb_accuracy_preflight(source, progress)
    if plan.run_blocking:  # fx1: like qb3, before any write
        _run_blocking_preflight(source, progress)
    if plan.modern_force_out:  # b778-fo1: like qb3, before any write
        _force_out_preflight(source, progress)
    if plan.inbox_standings:
        inbox = _core_module("nfl2k5_inbox_standings")
        if inbox is None or inbox.status(_xbe_bytes(source)) == "foreign":
            raise ValueError("Inbox standings needs a supported last-undefeated story and its retail callbacks.")
    if plan.star_career:  # b778-st2: like qb3, before any write
        _star_career_preflight(source, progress)
    if plan.rookie_faces:  # b778-rh1: before any write
        _rookie_faces_preflight(source, is_image, progress)
    if plan.alien_prospect:  # b778-ee1: before any write
        _alien_prospect_preflight(plan, source, is_image, progress)
    if plan.star_retention:  # b778-fa1: like fo1, before any write
        _star_retention_preflight(source, progress)
    if plan.practice_injuries:  # b778-pi1: like fo1, before any write
        _practice_injuries_preflight(source, progress)
    if plan.cpu_ball_carriers:  # b778-ai5: before any write
        _ball_carrier_preflight(source, progress)
    if plan.sportscenter_lineup:
        _sportscenter_lineup_preflight(source, progress)
    if plan.franchise_draft_clock:  # b778-dr1: like fo1, before any write
        _draft_clock_preflight(source, progress)
    if plan.weekly_progression:  # b778-pg1: like fo1, before any write
        _weekly_progression_preflight(source, progress)
    if plan.player_progress or plan.player_progress_visible:  # b778-pg2/pg3: like qb3, before any write
        _player_progress_preflight(source, progress)
    if plan.sim_stats:  # b778-sim1: like qb3, before any write
        _sim_stats_preflight(source, progress)
    if plan.modern_clock_led:  # b778-sd4: like qb3, before any write
        _clock_led_preflight(source, progress)
    _rebuild_refusals(plan, source, is_image, progress)  # fx1: late refusals of earlier-built discs, before any write
    if is_image and plan.espn25_plan:  # b778-bd1: the Unc Bowl kits are pinned; a foreign source stops here, not hours in
        unc = _core_module("nfl2k5_unc_bowl_uniforms")
        if unc is not None:
            progress("Checking the Unc Bowl kits on the source disc", 0, 0)
            try:
                unc.preflight_source(source if _retail_source is None else _retail_source)
            except (OSError, KeyError, IndexError):
                pass  # an image this check cannot read is judged by the owners' own checks, as before
    if plan.modern_coaches:  # b77-co1
        coaches = _core_module("nfl2k5_modern_coaches")
        if coaches is None or not is_image:
            raise ValueError("2026 head coaches need a disc image (the coach models live in the archive packs).")
        progress("Checking the coach models", 0, 0)
        try:
            coach_state = coaches.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"2026 head coaches cannot read the coach models: {exc}") from exc
        if coach_state not in ("retail", "applied", "mixed"):
            raise ValueError("A coach model or coach picture is not the supported retail or already-2026 bytes. Turn 2026 head coaches off or rebuild from a supported USA source.")
    if plan.modern_fans:  # b77-fr1
        fans = _core_module("nfl2k5_modern_fans")
        if fans is None or not is_image:
            raise ValueError("2026 fans need a disc image (the crowd texture sets live in the archive packs).")
        progress("Checking the crowd texture sets", 0, 0)
        try:
            fan_state = fans.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"2026 fans cannot read the crowd texture sets: {exc}") from exc
        if fan_state not in ("retail", "applied", "mixed"):
            raise ValueError("A crowd texture is not the supported retail or already-2026 bytes. Turn 2026 fans off or rebuild from a supported USA source.")
    if plan.modern_officials:  # b77-rf1
        officials = _core_module("nfl2k5_modern_officials")
        if officials is None or not is_image:
            raise ValueError("2025-26 officials need a disc image (the referee model lives in the archive packs).")
        progress("Checking the officials", 0, 0)
        try:
            official_state = officials.image_status(source)
        except (OSError, ValueError) as exc:
            raise ValueError(f"2025-26 officials cannot read the referee model: {exc}") from exc
        if official_state not in ("retail", "applied", "mixed"):
            raise ValueError("The referee model, the caps or a number texture is not the supported retail or already-2025-26 bytes. Turn 2025-26 officials off or rebuild from a supported USA source.")
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
        if pool_state not in ("retail", "applied", "needs_fix"):
            raise ValueError("the position-pool sites are neither retail nor this patch; refusing")
        if pool_state != "applied" and not plan.position_pools:
            raise ValueError("depth-chart rows need the one-pool positions (tick them, or build on a disc that has them)")
        if not plan.depth_roles and roles.status(source)["status"] != "applied":
            raise ValueError("depth-chart rows need the X / Z / SLWR playbook roles (tick them, or build on a disc that has them)")
    if plan.depth_roles and not is_image:
        raise ValueError("depth roles need a disc image (the personnel groups live in the PLAY books)")
    if plan.depth_roles:
        roles = _core_module("nfl2k5_depth_roles")
        if roles is None:
            raise RuntimeError("the depth-role module is not available in this build")
        role_states = roles.status(source)["books"]
        if not role_states or any(state == "foreign" for state in role_states.values()):
            raise ValueError("the source disc's playbooks carry foreign personnel data; depth roles refuse to guess")

    stock_bank, stock_receipt = None, None
    if plan.historic_stock_books:
        retail = require_step_source(source if _retail_source is None else _retail_source, "Stock historical books")
        stock_bank, stock_receipt = _core_module("nfl2k5_stock_books").preserve(retail, one_pool=plan.position_pools)

    complete_offense_packs, option_packs, defense_packs, offense_packs = (
        plan_playbook_packs(plan.playbook_packs)
    )
    if plan.playbook_packs:
        packs = _core_module("nfl2k5_playbook_pack")

    if plan.read_option_runtime or plan.qb_spy:
        progress("Checking every playbook pack together, team by team (several minutes)", 0, 0)
        preview_pairs = _preview_play_intents(source, [*complete_offense_packs, *option_packs, *defense_packs, *offense_packs],
                                              progress=progress)
        if plan.read_option_runtime:
            _, read_preview = tt.read_option_patch.compile_intent_table(preview_pairs)
            if not read_preview["count"]:
                raise ValueError("Read option mesh controls need at least one paired authored read recipe")
            receipt["read_option_preflight"] = read_preview
        if plan.qb_spy:
            tt.qb_spy_patch.compile_intent_table(preview_pairs)

    # Availability is a plan refusal, not a reason to discard a copied disc.
    for enabled, module, tool in (
        (plan.scorebug and not plan.scorebug_runtime, "nfl2k5_scorebug_layout", True),
        (plan.position_pools, "nfl2k5_position_pools", False),
        (plan.position_pools, "nfl2k5_playbook_position_recode", True),
        (plan.position_pools, "nfl2k5_roster_reclassify", True),
        (plan.kickoff_alignment, "nfl2k5_kickoff_alignment", True),
        (plan.dynamic_kickoff, "nfl2k5_kickoff_returns", True),
        (plan.seven_on_seven, "nfl2k5_seven_on_seven_book", False),
        (plan.screen_timing is not None, "nfl2k5_screen_timing", False),
        (plan.team_history, "nfl2k5_team_history", False),
        (plan.career_stats, "nfl2k5_career_stats", False),
        (plan.honors_history, "nfl2k5_honors_history", False),
        (plan.prospect_names, "nfl2k5_prospect_names", False),
        (plan.player_tags, "nfl2k5_player_tags", False),
        (plan.roster_edits, "nfl2k5_roster_records", False),
        (plan.season_2026, "nfl2k5_season_length", False),
        (plan.season_2026, "nfl2k5_franchise_schedule", True),
        (plan.season_2026, "nfl2k5_playoff_picture", False),
        (plan.commentary, "nfl2k5_commentary_swap", True),
        (plan.guardian_cap, "nfl2k5_guardian_cap", False),
        (plan.read_option_runtime or plan.qb_spy, "nfl2k5_play_intents", False),
    ):
        if enabled and (_tools_module(module) if tool else _core_module(module)) is None:
            raise RuntimeError(f"{module} is not available in this build")
    # Parse user-authored documents before any expensive project preparation or
    # image copy. The later writers still resolve them against composed bytes.
    for document, module in ((plan.team_history, "nfl2k5_team_history"),
                             (plan.career_stats, "nfl2k5_career_stats"),
                             (plan.prospect_names, "nfl2k5_prospect_names")):
        if document:
            _core_module(module).load_rows(document)
    if plan.roster_edits:
        _core_module("nfl2k5_roster_records").read_edits(plan.roster_edits)
    if plan.honors_history and plan.honors_history.strip() != "builtin":
        _core_module("nfl2k5_honors_history").resolve(plan.honors_history, 2026 if plan.season_2026 else 2004)
    if plan.music_project and not Path(plan.music_project).is_file():
        raise ValueError(f"The Music project is missing: {plan.music_project}")
    if _preflight_only:
        return receipt

    # 1. copy + executable and text patches through the proven writer (throw tables, caves, EDGE rename
    #    including its disc text spans when the source is an image)
    # the rows run after the pools step below (their cave and stride depend on it), so they never ride the first pass
    # the 2026 season step patches the executable itself, so a season-only plan is copy-first too
    if replace(plan, helmet_finish="glossy", weather_haze=False, depth_chart_rows=False, season_2026=False, xbe_space=False, kickoff_relocated=False, scorebug_runtime=False, indicator_names_folder="", indicator_names_style="retail", momentum=0, momentum_contact=False, defensive_try=False, zone_drop_cap=False, all_stadiums=False, coverage_slider=False, scramble_tuning=False, music_library=None,
               music_shuffle=False, music_shuffle_selection=None, practice_squad_screen=False, abilities=False, abilities_off_week=None, qb_spy=False, calendar_engine=False,
               momentum_collisions=False, momentum_collision_level=0, read_option_runtime=False,
               franchise_2026_rules=False, senior_bowl=False, guardian_overlay=False, my_career=False,
               my_career_setup=None, screen_hooks=False, coverage_trail=False, franchise_edit_player=False, cpu_money_downs="retail", accelerated_clock=False, coin_defer=False, decided_clock=False, cpu_scrambles="retail", weekly_prep=False, weekly_prep_cpu=False, weekly_prep_remember=False, coach_ai=False, playbook_pair=False, deep_zone_facing=False, deep_zone_bail=False, reserves_16=False, created_teams_extra=0, camera=False, franchise_autosave=False, historic_teams_quick_game=False, espn25_more_moments=False, historic_stock_books=False, espn25_era_rules=False, k128_memory=False, k128_roster_heap=False, k128_early=False, letter_grades=False, honors_page=False, sportscenter_lineup=False).wants_xbe_patch() or plan.edge_rename or complete_offense_packs or plan.contract_college_guard:
        progress("Copying and patching default.xbe", 0, 0)
        settings = tt.TuningSettings(plan.max_deep_yards, plan.arc, plan.realistic_flight, plan.arc_by_distance) if plan.throw else None
        kwargs: dict[str, Any] = {"overwrite": plan.overwrite, "progress": progress,
                                  "catch_slider": plan.catch_slider, "accel_ramp": plan.accel_ramp,
                                  "forward_pass_ruling": bool(complete_offense_packs),
                                  "draft_ai": plan.draft_ai, "edge_rename": plan.edge_rename,
                                  "returner_fix": plan.returner_fix, "progression": plan.progression, "franchise_economy": plan.franchise_economy,
                                  "scheme_labels": plan.scheme_labels or plan.position_pools,
                                  "camera": plan.camera if not tt.is_disc_image(source) else False, "kick_rules": plan.kick_rules, "kick_power": plan.kick_power, "widescreen": plan.widescreen,
                                  "overtime": plan.overtime, "team_column": plan.team_column, "seven_on_seven": plan.seven_on_seven,
                                  "position_row": plan.position_row, "probowl_order": plan.probowl_order,
                                  "elbow_options": plan.elbow_options,
                                  "the1wam_lineman_rating": plan.the1wam_lineman_rating,
                                  "xemu_display_list_fix": plan.xemu_display_list_fix,
                                  "resource_load_guard": plan.resource_load_guard, "loader_wakeup_fix": plan.loader_wakeup_fix, "rb_rename": plan.rb_rename,
                                  "trophy_room": plan.trophy_room,
                                  "name_keyboard": plan.name_keyboard,
                                  "flatter_deep_ball": plan.flatter_deep_ball, "chop_block_toggle": plan.chop_block_toggle,
                                  "penalties": plan.penalties, "uniform_choice": uniform_choice_mode(plan.uniform_choice),
                                  "kick_laces": plan.kick_laces, "punter_holder": plan.punter_holder, "franchise_practice": plan.franchise_practice, "practice_squad": plan.practice_squad,
                                  "depth_locks": plan.depth_locks, "season_cap": plan.season_cap,
                                  "music_policy": plan.music_policy, "music_unlock": plan.music_unlock, "music_userlist": plan.music_userlist,
                                  "prospect_names": plan.prospect_names,
                                  "player_star": plan.player_star, "modern_naming": plan.modern_naming, "crib_reclaim": plan.crib_reclaim, "_defer_image_resources": True,
                                  "dynamic_kickoff": plan.dynamic_kickoff, "dynamic_kickoff_settings": plan.dynamic_kickoff_settings}
        if settings is not None:
            kwargs["settings"] = settings
        if _consume_source:
            kwargs["_consume_source"] = True
        step = tt.write_copy(source, target, **kwargs)
        receipt["source_sha256"] = step.get("source_sha256")
        receipt["steps"].append({"step": "xbe", **{k: step.get(k) for k in ("forward_pass_ruling_patch", "modern_naming_patch", "crib_reclaim_patch", "catch_slider", "accel_ramp", "draft_ai", "edge_rename", "edge_rename_disc", "returner_fix", "progression", "franchise_economy", "franchise_economy_patch", "scheme_labels", "camera", "kick_rules", "kick_power", "dynamic_kickoff", "dynamic_kickoff_settings", "dynamic_kickoff_patch", "depth_chart_rows", "practice_squad", "practice_reserves", "depth_locks", "season_cap", "season_cap_patch", "widescreen", "widescreen_patch", "overtime", "team_column", "seven_on_seven", "position_row", "probowl_order", "elbow_options", "the1wam_lineman_rating", "xemu_display_list_fix", "resource_load_guard", "resource_load_guard_patch", "loader_wakeup_fix", "loader_wakeup_fix_patch", "rb_rename", "rb_rename_patch", "trophy_room", "trophy_room_patch", "name_keyboard_patch", "penalties", "flatter_deep_ball", "flatter_deep_ball_patch", "chop_block_toggle", "chop_block_toggle_patch", "chop_block_evidence", "uniform_choice", "kick_laces", "punter_holder", "franchise_practice", "prospect_names", "player_star", "music_policy", "music_unlock", "music_userlist", "music_state", "music_policy_patch", "scorebug_xbe", "changed_byte_count")}})
    else:
        progress("Copying the image", 0, 0)
        if target.exists():
            target.unlink()
        if _consume_source:
            os.replace(source, target)
        else:
            from .build_io import copy_image
            import hashlib
            # Hashed as it is copied; the measured outcome never reads the
            # source again (beta 74).
            source_hasher = hashlib.sha256()
            copy_image(source, target, progress, source_hasher)
            receipt["source_sha256"] = source_hasher.hexdigest()
        receipt["steps"].append({"step": "copy"})

    if retire_seven:
        progress("Removing unavailable 7-on-7 practice from the menu", 0, 0)
        receipt["steps"].append(retire_seven_on_seven(target))

    # 3. presentation on the copy
    if plan.scorebug and not plan.scorebug_runtime:
        sbl = _tools_module("nfl2k5_scorebug_layout")
        if sbl is None:
            raise RuntimeError("scorebug layout tool is not available in this build")
        progress("Re-laying the scorebug (mesh, placement, textures)", 0, 0)
        try:
            rec = sbl.apply_in_place(target, scorebug_folder=plan.scorebug_folder or None)
        except SystemExit as exc:
            # the layout writer reports refusals as SystemExit (it is also a CLI). A build runs on
            # a Qt worker thread whose runner catches Exception, so a SystemExit there would kill
            # the thread silently and leave the panel waiting for a result that never comes.
            raise RuntimeError(f"the ESPN scorebug could not be written: {exc}") from exc
        receipt["steps"].append({"step": "scorebug", **rec})
    spy_pairs: list = []  # (exact PLAY replacement, compiler report) pairs for the QB spy lookup
    if complete_offense_packs:
        # PROVED OFFLINE: v4 pins the original full resource. Install before
        # defensive personnel/kickoff writers; those compose on its stable IDs.
        progress("Installing complete offensive playbooks", 0, 0)
        rec = packs.apply_packs_to_image(target, complete_offense_packs,
                                        progress=lambda msg: progress(msg, 0, 0), collector=spy_pairs)
        receipt["steps"].append({"step": "playbook_packs", **rec})
    if option_packs:
        progress("Installing experimental option playbook packs", 0, 0)
        rec = packs.apply_packs_to_image(target, option_packs, progress=lambda msg: progress(msg, 0, 0), collector=spy_pairs)
        receipt["steps"].append({"step": "option_playbook_packs", **rec, "experimental": True, "witnessed": False})
    if defense_packs:
        progress("Installing experimental native defense playbook packs", 0, 0)
        pack_receipt = packs.apply_packs_to_image(
            target, defense_packs, progress=lambda msg: progress(msg, 0, 0), collector=spy_pairs)
        receipt["steps"].append({"step": "defense_playbook_packs", **pack_receipt,
                                 "experimental": True, "witnessed": False})
    if plan.position_pools:
        pools = _core_module("nfl2k5_position_pools")
        recode = _tools_module("nfl2k5_playbook_position_recode")
        roster = _tools_module("nfl2k5_roster_reclassify")
        if pools is None or recode is None or roster is None:
            raise RuntimeError("one-pool position modules are not available in this build")
        progress("Merging the EDGE / LB / interior pools in the executable", 0, 0)
        # The early pass always keeps the Outside Linebackers rows (retained profile); the final pass below
        # decides the removal after the last roster writer has run. apply() replays and refuses foreign bytes.
        xbe, pools_receipt = pools.apply(_xbe_bytes(target), roster_has_olb=True)
        _write_xbe_bytes(target, xbe)
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
        progress("Adding the 13 SPECIAL depth-chart rows", 0, 0)
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
    if plan.dynamic_kickoff:
        # beta 62: the three normal return plays get close blocking assignments (drive blocks for the
        # setup zone, lead blocks for the deep non-carrier) in every book; planned and validated for
        # all 36 resources before the first write, idempotent on replay.
        returns = _tools_module("nfl2k5_kickoff_returns")
        if returns is None:
            raise RuntimeError("the kickoff returns tool is not available in this build")
        progress("Giving the kickoff return blockers close assignments", 0, 0)
        returns_receipt = returns.apply(target, progress=lambda msg: progress(msg, 0, 0))
        receipt["steps"].append({"step": "kickoff_returns", **returns_receipt})
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
            collector=spy_pairs,
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
    if (complete_offense_packs or option_packs or defense_packs or offense_packs or plan.position_pools or plan.kickoff_alignment
            or plan.dynamic_kickoff or plan.seven_on_seven or plan.depth_roles or plan.screen_timing is not None):
        # After the last playbook writer: every book's formation play menus must be ones the play call can walk to
        # the end. A play listed twice in one formation hangs the game when that formation is picked (vb2,
        # 2026-09-23, Noah's Practice hang on the modern_gun_core book); no writer may ship one.
        menus = _check_playbook_menus(target, progress)
        if menus is not None:
            receipt["playbook_menus"] = menus
    if plan.season_2026:
        season = _core_module("nfl2k5_season_length")
        fs = _tools_module("nfl2k5_franchise_schedule")
        if season is None or fs is None:
            raise RuntimeError("2026 season modules are not available in this build")
        progress("Setting the franchise to 2026 (year, calendar, 18-week season)", 0, 0)
        xbe = _xbe_bytes(target)
        state = season.simple_status(xbe)
        if state == "retail":
            xbe, season_receipt = season.apply(
                xbe, super_bowl_venue=season.SOFI_SB_VENUE if plan.modern_sofi else "s44_los_angeles")
            _write_xbe_bytes(target, xbe)
        elif state == "applied":
            # Upgrade v0.6's missed annual-awards comparison even though its
            # existing calendar and 18-week installation already validate.
            xbe, awards_receipt = season.repair_awards_timing(xbe)
            season_receipt = {"already_applied": True, "awards_timing": awards_receipt}
            if not awards_receipt["already_applied"]:
                _write_xbe_bytes(target, xbe)
        else:
            raise ValueError(f"season-length sites are {state}; refusing")
        # b778-tr1: retail hides the Front Office trade rows from displayed Week 7 and the
        # Player Trade screen blocks from Week 8. Keep the native gate, wording and menu; move
        # the boundary to the modern NFL deadline, displayed Week 9.
        deadline = _core_module("nfl2k5_trade_deadline")
        if deadline is None:
            raise RuntimeError("the trade-deadline module is not available in this build")
        deadline_state = deadline.status(xbe)
        if deadline_state == "retail":
            progress("Keeping in-season trades open through NFL Week 9", 0, 0)
            xbe, deadline_receipt = deadline.apply(xbe)
            _write_xbe_bytes(target, xbe)
        elif deadline_state == "applied":
            deadline_receipt = {"already_applied": True}
        else:
            raise ValueError(f"trade-deadline sites are {deadline_state}; refusing")
        season_receipt = {**season_receipt,
                          "trade_deadline": {k: v for k, v in deadline_receipt.items() if k != "edits"}}
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
    if plan.modern_sofi:
        # u6's neutral LXI model lives in s40. Also repair the older s44 calendar when reusing a build.
        season = _core_module("nfl2k5_season_length")
        xbe, route_receipt = season.route_sofi_super_bowl(_xbe_bytes(target))
        if not route_receipt["already_applied"]:
            _write_xbe_bytes(target, xbe)
        receipt["steps"].append({"step": "sofi_super_bowl_route", **route_receipt})
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
    _apply_roster_history(plan, target, receipt, progress)
    if plan.team_names_2026:
        module = _core_module("nfl2k5_team_names_2026")
        if module is None:
            raise RuntimeError("The 2026 team-name module is unavailable")
        names_receipt = module.apply_to_image(target, progress=lambda message: progress(message, 0, 0))
        # u3: the renamed abbreviation and nickname keep working as keys through the in-place XBE key paths
        # (schedule, Thanksgiving hosts, saved playbooks, ESPN25 moments); old saves use the same paths.
        progress("Team lookups for the 2026 names", 0, 0)
        # The 2026 menu colour rows go in with them; the scorebug's guard on the team colour table (scorebar v3
        # reads it) recognizes these rows, so the scorebug runtime installs over them in either order.
        keyed, keys_receipt = module.apply_xbe(_xbe_bytes(target))
        _write_xbe_bytes(target, keyed)
        if module.xbe_status(_xbe_bytes(target)) != "applied":
            raise RuntimeError("2026 team-name key paths did not read back")
        receipt["steps"].append({"step": "team_names_2026", **names_receipt, "xbe": keys_receipt})
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

    if plan.coach_ai:
        progress("Compiling automatic CPU coach profiles for the final playbooks", 0, 0)
        coach_receipt = tt.coach_ai_patch.apply_profiles_to_image(
            target, progress=lambda message: progress(message, 0, 0))
        receipt["steps"].append({"step": "coach_ai_resources", **coach_receipt})

    all_requests = tt._selected_space_requests(
        with_kickoff=plan.kickoff_relocated, runtime=plan.scorebug_runtime, momentum=plan.momentum,
        defensive_try=plan.defensive_try, zone_drop_cap=plan.zone_drop_cap, all_stadiums=plan.all_stadiums,
        coverage_slider=plan.coverage_slider, scramble_tuning=plan.scramble_tuning,
        music_shuffle=plan.music_shuffle, practice_squad_screen=plan.practice_squad_screen,
        abilities=plan.abilities, qb_spy=plan.qb_spy, calendar_engine=plan.calendar_engine,
        **tt._r62_space_options(r62), camera=plan.camera,
        hair_styles=plan.hair_styles, cpu_qb_reads=bool(plan.cpu_qb_zone_windows or plan.cpu_qb_recheck),
        db_ball_play=plan.db_ball_play, play_art_routes=plan.play_art_routes,
        team_number_scale=bool(plan.team_number_scale), run_blocking=plan.run_blocking,
        qb_accuracy=plan.qb_accuracy, modern_force_out=plan.modern_force_out,
        practice_injuries=plan.practice_injuries, cpu_ball_carriers=plan.cpu_ball_carriers,
        star_retention=plan.star_retention, star_career=plan.star_career,
        franchise_draft_clock=plan.franchise_draft_clock, weekly_progression=plan.weekly_progression,
        player_progress=bool(plan.player_progress or plan.player_progress_visible), contract_college_guard=plan.contract_college_guard,
        sim_cb_tackles=plan.sim_cb_tackles, modern_clock_led=plan.modern_clock_led,
        module_loader=plan.module_loader, classic_teams=plan.classic_teams)
    if plan.read_option_runtime or plan.qb_spy:
        resolver = _core_module("nfl2k5_play_intents")
        if resolver is None:
            raise RuntimeError("The final playbook pairing module is not available in this build")
        spy_pairs = resolver.resolve_final_pairs(
            target, spy_pairs, progress=lambda msg: progress(msg, 0, 0))
    read_table, read_receipt = (tt.read_option_patch.compile_intent_table(spy_pairs)
                                if plan.read_option_runtime else (None, None))
    spy_table, spy_table_receipt = (tt.qb_spy_patch.compile_intent_table(spy_pairs)
                                    if plan.qb_spy else (None, None))
    if plan.read_option_runtime and not read_receipt["count"]:
        raise ValueError("Read option mesh controls need at least one paired authored read recipe")
    if plan.read_option_runtime or plan.qb_spy:
        _verify_play_intents(target, spy_pairs)
        receipt["play_intents_final"] = {
            **resolver.resolution_receipt(spy_pairs),
            "read_option_count": read_receipt["count"] if read_receipt else 0,
            "qb_spy_count": spy_table_receipt["count"] if spy_table_receipt else 0,
        }
        counts = receipt["play_intents_final"]
        receipt["play_intents_summary"] = (
            f"Final playbooks paired: {counts['read_option_count']} read option plays, "
            f"{counts['qb_spy_count']} QB spy assignments. EXPERIMENTAL / UNWITNESSED.")
    if plan.scorebug_runtime:
        progress("Installing team logos and scorebug effects (unwitnessed)", 0, 0)
        rec = _core_module("nfl2k5_scorebug_ingame").runtime_apply_in_place(target, with_kickoff=plan.kickoff_relocated, scorebug_folder=plan.scorebug_folder or None,
            widescreen=bool(plan.widescreen), watermark=plan.scorebug_watermark,
            extra_requests=tuple(row for row in all_requests if row[0] not in {
                tt.scorebug_runtime_patch.OWNER, tt.kickoff_relocated_patch.OWNER}))
        receipt["steps"].append({"step": "scorebug_runtime", **rec})
    if plan.guardian_overlay:
        rec = tt.guardian_resources.apply_to_image(
            target, guardian_everyone_practice=plan.guardian_everyone_practice, guardian_players=plan.guardian_players,
            extra_requests=tuple(row for row in all_requests if row[0] != tt.guardian_overlay_patch.OWNER))
        receipt["steps"].append({"step": "guardian_overlay", **rec})
    if ((plan.xbe_space or plan.kickoff_relocated) and not plan.scorebug_runtime
            or momentum_on or plan.read_option_runtime or plan.guardian_overlay or plan.my_career or plan.screen_hooks or plan.coverage_trail or plan.franchise_edit_player or plan.cpu_money_downs != "retail" or plan.accelerated_clock or plan.coin_defer or plan.decided_clock or plan.cpu_scrambles == "modern" or plan.weekly_prep or plan.weekly_prep_cpu or plan.weekly_prep_remember or plan.coach_ai or plan.playbook_pair or plan.deep_zone_facing or plan.deep_zone_bail
            or plan.reserves_16 or plan.created_teams_extra or plan.defensive_try or plan.zone_drop_cap or plan.all_stadiums or plan.coverage_slider or plan.scramble_tuning
            or plan.music_shuffle or plan.practice_squad_screen or plan.abilities or plan.qb_spy or plan.calendar_engine or plan.camera or plan.franchise_autosave
            or plan.historic_teams_quick_game or plan.espn25_more_moments or plan.historic_stock_books or plan.espn25_era_rules or r62.get("anniversary_kickoff") or r62.get("widescreen_menus") or r62.get("team_logo_swap") or r62.get("period_goalposts") or plan.k128_memory or plan.letter_grades or plan.honors_page):
        progress("Adding experimental extra patch space", 0, 0)
        playlist_selection, playlist_preflight = None, None
        if plan.music_shuffle:
            playlist = tt.music_playlist_patch
            playlist_selection = playlist.from_options(plan.music_shuffle_selection) if plan.music_shuffle_selection else playlist.Selection()
            library = _core_module("nfl2k5_music_banks")
            preview = library.plan(target, plan.music_library) if plan.music_library else None
            playlist_selection, playlist_preflight = library.playlist_preflight(
                target, plan.music_shuffle_selection, library_plan=preview)
        patched, space_receipt = tt._apply_all(
            _xbe_bytes(target), wanted=None, catch_slider=False, arc_table=False,
            xbe_space=plan.xbe_space, kickoff_relocated=plan.kickoff_relocated,
            scorebug_runtime=plan.scorebug_runtime, momentum=plan.momentum, momentum_contact=plan.momentum_contact,
            defensive_try=plan.defensive_try, zone_drop_cap=plan.zone_drop_cap, all_stadiums=plan.all_stadiums, coverage_slider=plan.coverage_slider, scramble_tuning=plan.scramble_tuning,
            music_shuffle=plan.music_shuffle, music_shuffle_selection=playlist_selection, practice_squad_screen=plan.practice_squad_screen,
            abilities=plan.abilities, abilities_off_week=plan.abilities_off_week, abilities_lock_right_stick=plan.abilities_lock_right_stick,
            abilities_lock_special_moves=plan.abilities_lock_special_moves, abilities_lock_speedster=plan.abilities_lock_speedster,
            abilities_right_stick_stars_only=plan.abilities_right_stick_stars_only,
            abilities_button_moves_stars_only=plan.abilities_button_moves_stars_only,
            abilities_charge_stars_only=plan.abilities_charge_stars_only, abilities_star_access=plan.abilities_star_access,
            qb_spy=plan.qb_spy, qb_spy_intent_table=spy_table,
            calendar_engine=plan.calendar_engine, camera=plan.camera, season_cap=plan.season_cap, practice_squad=plan.practice_squad, franchise_practice=plan.franchise_practice,
            dynamic_kickoff_settings=plan.dynamic_kickoff_settings,
            hair_styles=plan.hair_styles, cpu_qb_reads=bool(plan.cpu_qb_zone_windows or plan.cpu_qb_recheck),
            db_ball_play=plan.db_ball_play, play_art_routes=plan.play_art_routes,
            team_number_scale=bool(plan.team_number_scale), run_blocking=plan.run_blocking,
            qb_accuracy=plan.qb_accuracy, modern_force_out=plan.modern_force_out,
            practice_injuries=plan.practice_injuries, cpu_ball_carriers=plan.cpu_ball_carriers,
            star_retention=plan.star_retention, star_career=plan.star_career,
            franchise_draft_clock=plan.franchise_draft_clock, weekly_progression=plan.weekly_progression,
            player_progress=bool(plan.player_progress or plan.player_progress_visible), contract_college_guard=plan.contract_college_guard,
            sim_cb_tackles=plan.sim_cb_tackles, modern_clock_led=plan.modern_clock_led,
            module_loader=plan.module_loader, classic_teams=plan.classic_teams,
            **{**r62, "read_option_intent_table": read_table, "modern_naming": False, "crib_reclaim": False})
        _write_xbe_bytes(target, patched)
        receipt["steps"].append({"step": "xbe_space", **space_receipt,
                                 **tt._grown_status_fields(patched),
                                 "read_option_intent_table": read_receipt, "qb_spy_intent_table": spy_table_receipt, "music_shuffle_preflight": playlist_preflight,
                                 "play_intents_final": receipt.get("play_intents_final"),
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

    # beta 66 (maumau78): the helmet finish is the final executable pass, after every allocator owner and a
    # possible music image rebuild, so Matte survives them and Glossy restores an already-Matte input.
    finish = _core_module("nfl2k5_helmet_finish")
    if finish is not None:
        try:
            current = _xbe_bytes(target)
        except (OSError, ValueError):
            # a synthetic or foreign image without a readable executable: nothing to restore; Matte still needs one
            if plan.helmet_finish == "matte":
                raise
            current = None
        if current is not None and (plan.helmet_finish == "matte" or finish.status(current) == "applied"):
            progress(f"Helmet finish: {plan.helmet_finish}", 0, 0)
            patched, finish_receipt = finish.apply(current, finish=plan.helmet_finish)
            _write_xbe_bytes(target, patched)
            finish.verify(_xbe_bytes(target), finish=plan.helmet_finish)
            receipt["steps"].append({"step": "helmet_finish", **finish_receipt})

    haze = _core_module("nfl2k5_weather_haze")
    if haze is not None:
        try:
            current = _xbe_bytes(target)
        except (OSError, ValueError):
            if plan.weather_haze:
                raise
            current = None
        if current is not None and (plan.weather_haze or haze.status(current) == "applied"):
            progress("Applying existing dry-weather haze response", 0, 0)
            patched, haze_receipt = haze.apply(current, enabled=plan.weather_haze)
            _write_xbe_bytes(target, patched)
            haze.verify(_xbe_bytes(target), enabled=plan.weather_haze)
            receipt["steps"].append({"step": "weather_haze", **haze_receipt})
    # b76-k2: the number binder rewritten in place (no allocation), after the other executable owners
    kerning = _core_module("nfl2k5_number_kerning")
    if kerning is not None:
        try:
            current = _xbe_bytes(target)
        except (OSError, ValueError):
            if plan.number_kerning:
                raise
            current = None
        # Off leaves an already-kerned source as it is (the retail routine is not stored).
        if current is not None and plan.number_kerning:
            progress("Jersey numbers: kerning the 1 in two-digit numbers", 0, 0)
            patched, kerning_receipt = kerning.apply(current, enabled=True)
            _write_xbe_bytes(target, patched)
            kerning.verify(_xbe_bytes(target), enabled=True)
            receipt["steps"].append({"step": "number_kerning", **kerning_receipt})
    modern = _core_module("nfl2k5_modern_color")
    if modern is not None:
        try:
            current = _xbe_bytes(target)
        except (OSError, ValueError):
            if plan.modern_color:
                raise
            current = None
        previous_colour = modern.read_image_receipt(source)
        previous_settings = previous_colour["settings"] if previous_colour else None
        if current is not None and (plan.modern_color or modern.xbe_status(current, previous_settings) in ("applied", "applied (custom)")):
            progress("Modern colour and lighting: light rigs", 0, 0)
            patched, modern_receipt = modern.apply(current, enabled=plan.modern_color, settings=plan.modern_color_settings, previous_settings=previous_settings)
            _write_xbe_bytes(target, patched)
            modern.verify(_xbe_bytes(target), enabled=plan.modern_color, settings=plan.modern_color_settings)
            receipt["steps"].append({"step": "modern_color_xbe", **modern_receipt})
    progress("Verifying the composed disc", 0, 0)
    inspection = inspect(target, screen_timing=plan.screen_timing)
    if plan.hires_pack:
        # Retain fixed-offset inspector results only with their pre-remap scope.
        receipt["pre_remap_inspection"] = inspection
        hires = _core_module("nfl2k5_hires_pack")
        with tempfile.TemporaryDirectory(prefix=".hires-", dir=target.parent) as folder:
            destination = Path(folder).resolve() / "image.iso"
            rec = hires.build_image(target, destination, plan.hires_folder,
                                    scale=plan.hires_scale, target=plan.hires_target, families=plan.hires_families, progress=progress)
            os.replace(destination, target)
        receipt["steps"].append({"step": "hires_pack", **rec})
        receipt["result"] = {"path": str(target), "container": "xiso",
                             "hires_pack": rec["verification"]["status"], "hires_pack_details": rec,
                             "image_size": target.stat().st_size,
                             "image_sha256": rec["verification"]["output_sha256"],
                             "inspection_scope": "Final archive and XBE verified by identity; earlier patch states are in pre_remap_inspection"}
    else:
        receipt["result"] = inspection
    if plan.modern_naming:
        rec = tt._finish_naming_image(target, naming_digest, progress)
        receipt["steps"].append({"step": "modern_naming", **rec})
    if plan.reserves_16 or plan.created_teams_extra or capacity_records:
        rec = tt._finish_roster_arena_image(target, plan.reserves_16, plan.created_teams_extra, progress,
                                            capacity_records=capacity_records)
        receipt["steps"].append({"step": "roster_arena_growth", **rec})
    # b778-xs1: the Crib Trophy Room cut goes in before the Crib rebuild, which then also drops the four arcade game
    # files (nothing can open them any more); in place, no allocation.
    _apply_crib_trophy_room(plan, target, receipt, progress)
    if plan.crib_reclaim:
        rec = tt._finish_crib_image(target, progress)
        receipt["steps"].append({"step": "crib_reclaim", **rec})
    # Outside Linebackers filter rows: decided after the LAST roster mutation (team names, imports, historic edits,
    # prospect names, user roster edits, arena growth) from a complete scan of every disc roster.
    olb_filtered = False
    pools_final = _core_module("nfl2k5_position_pools")
    run_olb_filter = bool(plan.position_pools) and pools_final is not None and is_image
    if not run_olb_filter and pools_final is not None and is_image:
        # A source that already carries the pools gets the same final decision; an executable that
        # cannot be read here was never patched by this build, so the rows are left alone.
        try:
            run_olb_filter = pools_final.status(_xbe_bytes(target)) == "applied"
        except Exception:  # noqa: BLE001
            run_olb_filter = False
    if run_olb_filter:
        roster_scan = _tools_module("nfl2k5_roster_reclassify")
        if roster_scan is None or not callable(getattr(roster_scan, "olb_filter_policy", None)):
            raise RuntimeError("the roster scan for the Outside Linebackers rows is not available in this build")
        progress("Scanning every disc roster for outside linebackers", 0, 0)
        scan = roster_scan.olb_filter_policy(target)
        # Only the literal False from a complete scan certifies absence. Beta 65 ships the EDGE-only
        # product profile: an uncertified roster refuses the build instead of keeping OLB rows.
        if scan["roster_has_olb"] is not False:
            raise ValueError("The EDGE-only position build still contains enum-10 players or an incomplete "
                             "roster scan; reclassify every selectable roster before building")
        xbe, filter_receipt = pools_final.apply(_xbe_bytes(target), roster_has_olb=False)
        _write_xbe_bytes(target, xbe)
        overview_receipt = pools_final.apply_team_needs_image(target)
        receipt["steps"].append({"step": "position_pool_filters", "scan": scan,
                                 "compatibility_override": plan.position_pools_keep_olb,
                                 "xbe": filter_receipt, "team_needs_overview": overview_receipt,
                                 "experimental": True, "witnessed": False})
        olb_filtered = True
    if plan.rb_rename and is_image:
        # b777-rb2: the two screen scenes that keep their own HB label (Roster Breakdown, TRAINING RESULTS),
        # same length in place, after the Team Needs overview rewrite above.
        progress("Renaming HB to RB on the roster and training screens", 0, 0)
        receipt["steps"].append({"step": "rb_rename_scenes", **_core_module("nfl2k5_rb_rename").apply_image(target)})
    if plan.modern_naming or plan.reserves_16 or plan.created_teams_extra or plan.crib_reclaim or olb_filtered:
        if plan.hires_pack:
            # Preserve the archive verifier's final scope; do not rerun fixed-offset inspectors.
            receipt["result"].update(tt._grown_status_fields(_xbe_bytes(target)))
            receipt["result"]["image_size"] = target.stat().st_size
            receipt["result"]["image_sha256"] = _core_module("nfl2k5_music_archive").file_hash(target)
        else:
            receipt["result"] = inspect(target, screen_timing=plan.screen_timing)
    if plan.espn25_rosters:
        # Historic resource pass plus the guarded native reload repair, on the copy after relocations.
        progress("Applying historic moment rosters", 0, 0)
        module = _core_module("nfl2k5_espn25_rosters")
        historic_receipt = module.apply_to_image(target)
        receipt["steps"].append({"step": "espn25_rosters", **historic_receipt})
        if historic_receipt.get("moment_scan_ids_in_use"):
            # fx1 (review pr69 #2): this used to be a receipt key only. Say it in the build log and the receipt's
            # user notes; the data is unchanged (a hard refusal would stop every non-2026 main roster).
            note = ("Historic moment rosters: the main roster already uses head ids "
                    + ", ".join(map(str, historic_receipt["moment_scan_ids_in_use"]))
                    + ", so four moment players wear those players' heads. The SOFTDRINK 2026 roster leaves them free.")
            progress(note, 0, 0)
            receipt.setdefault("user_notes", []).append(note)
        receipt["result"]["espn25_rosters"] = module.image_status(target)
        if receipt["result"]["espn25_rosters"] != "applied":
            raise ValueError("the historic moment rosters failed their read-back on the copy")
    if plan.espn25_more_moments:
        # b765-a1: rows 26 to 51 and their team-season files, after every relocating pass; the executable half was
        # installed with the allocator owners. On a One-pool positions build the new files get the same historic
        # 4-3 reclassification the pools option gave the retail 75.
        progress("Adding historic Anniversary moments", 0, 0)
        module = _core_module("nfl2k5_espn25_more_moments")
        pools_now = _core_module("nfl2k5_position_pools")
        one_pool = bool(pools_now is not None and pools_now.status(_xbe_bytes(target)) == "applied")
        moments_receipt = module.apply_to_image(target, one_pool=one_pool, named=plan.espn25_named_previews)
        receipt["steps"].append({"step": "espn25_more_moments", **moments_receipt})
        receipt["result"]["espn25_more_moments"] = module.image_status(target)
        if receipt["result"]["espn25_more_moments"] != "applied" or module.status(_xbe_bytes(target)) != "applied":
            raise ValueError("the historic Anniversary moments failed their read-back on the copy")
        if plan.espn25_named_previews:
            receipt["result"]["espn25_named_previews"] = module.named_image_status(target)
            if (receipt["result"]["espn25_named_previews"] != "applied"
                    or _core_module("nfl2k5_moment_venues").status(_xbe_bytes(target)) != "applied"):
                raise ValueError("the named Anniversary previews failed their read-back")
            receipt["steps"].append({"step": "espn25_named_previews", "status": "applied", "rows": 51})
        # b76-m1: historic and moment teams on style 0 move to a spare style holding the RETAIL style-0 art, so the
        # 2026 art a project writes to style 0 (the project copy runs before these steps) shows on the current teams
        # only. The copies come from the retail source, never from the copy.
        progress("Keeping the historic teams' retail uniforms and logos", 0, 0)
        styles = _core_module("nfl2k5_historic_styles")
        retail = require_step_source(source if _retail_source is None else _retail_source, "Historic team styles")
        styles_receipt = styles.apply_to_image(target, retail)
        receipt["steps"].append({"step": "historic_styles", **styles_receipt})
        receipt["result"]["historic_styles"] = styles.image_status(target, retail)
        if receipt["result"]["historic_styles"] != "applied":
            raise ValueError("the historic team styles failed their read-back on the copy")
    if stock_bank is not None:
        progress("Preserving stock books for historic teams", 0, 0)
        module = _core_module("nfl2k5_stock_books")
        bank_receipt = module.apply_to_image(target, stock_bank)
        receipt["steps"].append({"step": "historic_stock_books", **stock_receipt, **bank_receipt})
        receipt["result"]["historic_stock_books"] = module.image_status(target, stock_bank)
        if module.status(_xbe_bytes(target)) != "applied":
            raise ValueError("stock book resolver failed its read-back")
    if plan.historic_rosters_2026:
        seasons = _core_module("nfl2k5_historic_rosters")
        progress("Writing the 75 historic season rosters", 0, 0)
        season_receipt = seasons.apply_to_image(target)
        receipt["steps"].append({"step": "historic_rosters_2026", **season_receipt})
        receipt["result"]["historic_rosters_2026"] = seasons.image_status(target)
    if loaded_espn25_plan is not None:
        # last of all: the music, hi-res, naming, arena and crib passes above may have relocated packs,
        # so the plan resolves SITU and the historic ROSTs through the copy's own XDVDFS/outer tables
        # here, after final resource relocation and before build() publishes the disposable output
        espn = _core_module("nfl2k5_espn25_scenarios")
        progress("Applying ESPN Anniversary edits", 0, 0)
        espn_receipt = espn.apply_to_image(target, loaded_espn25_plan)
        receipt["steps"].append({"step": "espn25_plan", **espn_receipt})
        receipt["result"]["espn25_plan"] = espn.status(target, loaded_espn25_plan)
        if receipt["result"]["espn25_plan"] != "applied":
            raise ValueError("the ESPN Anniversary edits failed their read-back on the copy")
    if is_image:
        # b773-i4: the five Anniversary era kits (a5k trades NE 11, PHI 14, NO 6, BAL 1, PIT 4) composed from their
        # donor kits as the v0.6 native repair did, after the roster labels and the historic spares (donors) exist.
        # The Unc Bowl finish below starts from the composed PIT 22A4; a Studio build used to leave it retail.
        era_kits = _core_module("nfl2k5_era_kits")
        if era_kits is not None:
            progress("Composing the Anniversary era kits", 0, 0)
            era_receipt = era_kits.apply_to_image(target, lambda: require_step_source(
                source if _retail_source is None else _retail_source, "Anniversary era kits"))
            if era_receipt["state"] == "applied":
                receipt["steps"].append({"step": "era_kits", **era_receipt})
        uniforms = _core_module("nfl2k5_unc_bowl_uniforms")
        if uniforms is None:
            raise RuntimeError("the Unc Bowl uniform repair module is not available in this build")
        uniforms_receipt = uniforms.apply_to_image(target)
        receipt["steps"].append({"step": "unc_bowl_uniforms", **uniforms_receipt})
        for note in uniforms_receipt.get("user_notes", ()):  # b778-bd1: a kit left as it is is said, not a late failure
            progress(note, 0, 0)
            receipt.setdefault("user_notes", []).append(note)
        # b772-ny1: finish the known NYG home art after the project's uniform
        # layers. The native shoulder anNN textures use the plain jersey mips.
        numbers = _core_module("nfl2k5_nyg_numbers")
        if numbers is None:
            raise RuntimeError("the Giants shoulder-number repair module is not available in this build")
        number_receipt = numbers.apply_to_image(target)
        if number_receipt["state"] == "applied":
            receipt["steps"].append({"step": "nyg_shoulder_numbers", **number_receipt})
        # b772-uf1: the 2026 home/away kit art the in-game uniform review found wrong (sleeve stacks, chest bands,
        # pants stripes, patches, helmet marks, Giants style 7 shoulder digits), pinned to the known kit spans.
        kit_fixes = _core_module("nfl2k5_kit_fixes_2026")
        if kit_fixes is None:
            raise RuntimeError("the 2026 kit art repair module is not available in this build")
        kit_receipt = kit_fixes.apply_to_image(target)
        if kit_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026", **{k: v for k, v in kit_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"} for kit in kit_receipt["kits"]]})
        # b772-uf2: the 2026 alternate, throwback and Rivalries kit art the same review found wrong (second data file,
        # same compiler), pinned to the known kit spans after the home/away pass.
        alt_receipt = kit_fixes.apply_alternates(target)
        if alt_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_alts",
                                     **{k: v for k, v in alt_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"} for kit in alt_receipt["kits"]]})
        # b773-uf3: the uniform elements judged against the 2026 game highlights (the Washington helmet W, the Unc
        # Bowl Steelers nameplates and arm numbers, ...), a third pinned layer after the alternates.
        uf3_receipt = kit_fixes.apply_finish(target)
        if uf3_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_uf3",
                                     **{k: v for k, v in uf3_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"} for kit in uf3_receipt["kits"]]})
        # b773-sea1: the Seattle helmet (logo fragment off the crown stripe, the helmet back's lines whole) and the
        # wolf-grey shoulder digits, a fourth pinned layer after uf3.
        sea1_receipt = kit_fixes.apply_seattle(target)
        if sea1_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_sea1",
                                     **{k: v for k, v in sea1_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"} for kit in sea1_receipt["kits"]]})
        overlap_receipt = kit_fixes.apply_overlaps(target)
        if overlap_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_ov1",
                                     **{k: v for k, v in overlap_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                              for kit in overlap_receipt["kits"]]})
        # b776-fn2: the 2026 Bears and Chiefs nameplate letters (retail letter structure read from the source disc, in
        # the kit colours: the I, the W/M/N counters and the small c come back) and the redrawn 2026 Titans 7.
        # The runtime package check lists the module, so a release cannot ship without it (as pants_hem below).
        glyph_fixes = _core_module("nfl2k5_glyph_fixes_2026")
        if glyph_fixes is not None:
            glyph_receipt = glyph_fixes.apply_to_image(target, lambda: require_step_source(
                source if _retail_source is None else _retail_source, "2026 nameplate letters"))
            if glyph_receipt["state"] == "applied":
                receipt["steps"].append({"step": "glyph_fixes_2026",
                                         **{k: v for k, v in glyph_receipt.items() if k != "kits"},
                                         "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                                  for kit in glyph_receipt["kits"]]})
        # b773-uf3: the 2026 Pittsburgh road miniature (schedule screens) with its Steelmark the right way up; only the
        # exact known art changes, retail and user art are left alone.
        uf3_icon = _core_module("nfl2k5_menu_icon_uf3")
        if uf3_icon is not None:
            icon_receipt = uf3_icon.apply_to_image(target)
            if icon_receipt["state"] == "applied":
                receipt["steps"].append({"step": "menu_icon_uf3", **icon_receipt})
        # b773-hu1: Washington's Team Select helmet cards and schedule miniatures carry the 2026 helmet W uf3 drew in
        # game; only the exact known card art changes, retail and user art are left alone.
        helmet_w = _core_module("nfl2k5_menu_helmet_w2026")
        if helmet_w is not None:
            helmet_receipt = helmet_w.apply_to_image(target)
            if helmet_receipt["written"] or helmet_receipt["state"] == "applied":
                receipt["steps"].append({"step": "menu_helmet_w2026", **helmet_receipt})
        # b776-ku1: the Chiefs Team Select cards and schedule miniatures in the 2026 red (palette only, pinned slots).
        chiefs_menu = _core_module("nfl2k5_menu_chiefs_2026")
        if chiefs_menu is not None:
            menu_receipt = chiefs_menu.apply_to_image(target)
            if menu_receipt["written"] or menu_receipt["state"] == "applied":
                receipt["steps"].append({"step": "menu_chiefs_2026", **menu_receipt})
        # b773-pa1: the modern above-the-knee pants hem on every current-season kit (texture only: the pants, their
        # bump map and the sideline player), compiled after the uf3 finish; throwbacks keep their era hem.
        pants_hem = _core_module("nfl2k5_pants_hem_2026")
        if pants_hem is not None:
            hem_receipt = pants_hem.apply_to_image(target)
            if hem_receipt["state"] == "applied":
                receipt["steps"].append({"step": "pants_hem_2026",
                                         **{k: v for k, v in hem_receipt.items() if k != "kits"},
                                         "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                                  for kit in hem_receipt["kits"]]})
        # b776-ku1 (Noah 10/18): the 2026 Chiefs home and road kits redone to the current look (red that reads as
        # Chiefs red through the in-game colour pipeline, Nike-era sleeve bands, socks, pants stripes, AFL patch,
        # arm numbers on the shoulder tops); after the pants hem, the last writer of 13H0/13A0. Pinned spans only.
        chiefs_receipt = kit_fixes.apply_chiefs(target)
        if chiefs_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_ku1",
                                     **{k: v for k, v in chiefs_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                              for kit in chiefs_receipt["kits"]]})
        # b777-sw1 (Noah 10/20): the sleeve swoosh centred on the sleeve on every 2026 kit, over the arm number where
        # the number sits on the sleeve, clear of numbers, stripes and logos; the last kit writer. Pinned spans only.
        swoosh_receipt = kit_fixes.apply_swooshes(target)
        if swoosh_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_sw1",
                                     **{k: v for k, v in swoosh_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                              for kit in swoosh_receipt["kits"]]})
        # b778-uf1 (SWeaR 10/21: Dallas Alternate 1 last names glitched): a nameplate takes the glyph metrics of the
        # letter atlas it carries (07H7/07A7 wear 07A0's letters), only when its measured atlas has that layout.
        names_fix_receipt = kit_fixes.apply_nameplates(target)
        if names_fix_receipt["state"] == "applied":
            receipt["steps"].append({"step": "kit_fixes_2026_names",
                                     **{k: v for k, v in names_fix_receipt.items() if k != "kits"},
                                     "kits": [{k: v for k, v in kit.items() if k != "parts"}
                                              for kit in names_fix_receipt["kits"]]})
        if plan.espn25_more_moments:
            # b775-ek1 (Noah 10/17): every Anniversary side wears the uniform of its game. Missing looks become NEW
            # style indexes composed from kits already on the copy (read after every uniform writer above), labelled
            # only in the moments' team files so modern Team Select never offers them; then the 51 rows' selections.
            moment_kits = _core_module("nfl2k5_moment_kits")
            if moment_kits is None:
                raise RuntimeError("the Anniversary moment kits module is not available in this build")
            progress("Dressing the Anniversary teams in their game uniforms", 0, 0)
            kits_receipt = moment_kits.apply_to_image(target)
            receipt["steps"].append({"step": "moment_kits", **kits_receipt})
            receipt["result"]["moment_kits"] = moment_kits.image_status(target)
            if receipt["result"]["moment_kits"] != "applied":
                raise ValueError("the Anniversary moment kits failed their read-back on the copy")
        # b778-uf2 (Noah 10/22): the 2026 Jaguars nameplates on the retail letter structure (white letters with the
        # black outline on the teal home kit, black letters with their counters on the road and Bold City kits), then
        # every kit's nameplate hyphen solid; after the Anniversary moment kits, which copy kit packages.
        nameplate_fixes = _core_module("nfl2k5_nameplate_fixes_2026")
        if nameplate_fixes is None:
            raise RuntimeError("the 2026 nameplate fixes module is not available in this build")
        nameplate_receipt = nameplate_fixes.apply_to_image(
            target, lambda: require_step_source(source if _retail_source is None else _retail_source,
                                                "Jaguars nameplates"))
        receipt["steps"].append({"step": "nameplate_fixes_2026", **nameplate_receipt})
    if is_image and plan.team_sleeves:
        # b778-sl1: after every uniform writer (the last is the Anniversary moment kits above), so the
        # Team palette a package carries is the final art. Data only: one .rdata flag and package palettes.
        sleeves = _core_module("nfl2k5_team_sleeves")
        if sleeves is None:
            raise RuntimeError("the team-coloured sleeves module is not available in this build")
        progress("Making the long sleeves team-coloured", 0, 0)
        xbe, xbe_receipt = sleeves.apply(_xbe_bytes(target))
        _write_xbe_bytes(target, xbe)
        sleeves.verify(_xbe_bytes(target))
        sleeve_receipt = sleeves.apply_to_image(target)
        receipt["steps"].append({"step": "team_sleeves", "xbe": xbe_receipt, **sleeve_receipt})
        receipt["result"]["team_sleeves"] = "applied"
        if sleeve_receipt.get("skipped"):
            note = (f"Team-coloured sleeves: left {len(sleeve_receipt['skipped'])} uniform package(s) "
                    "with their own long-sleeve artwork.")
            progress(note, 0, 0)
            receipt.setdefault("user_notes", []).append(note)
    if plan.roster_edits:
        # b77 q1: a roster-edits document may carry a qb_throw_power directive (the amount is its "add"). It runs after
        # every other roster writer (free agents, Anniversary imports, ESPN25 plans) so no later step overwrites a QB.
        qb_module = _core_module("nfl2k5_qb_throw_power")
        if qb_module is None:
            raise RuntimeError("the QB Throw Power module is not available in this build")
        qb_directive = qb_module.directive_of(_core_module("nfl2k5_roster_records").read_edits(Path(plan.roster_edits)))
        if qb_directive is not None:
            progress("Raising every quarterback's Throw Power", 0, 0)
            qb_receipt = qb_module.apply_image(target, qb_directive, progress=lambda message: progress(message, 0, 0))
            receipt["steps"].append({"step": "qb_throw_power", **qb_receipt})
    _apply_roster_refresh(plan, target, receipt, progress)
    _apply_draft_pick_ownership(plan, target, receipt, progress)
    _apply_hback_roles(plan, target, receipt, progress)
    _apply_team_ratings(plan, target, receipt, progress)
    if plan.classic_teams and plan.historic_teams_quick_game and is_image:
        # b775-ct1: last of the executable and roster writers: it reads the season route, the historic styles' spares,
        # the moment table, the final main roster (own faces, colleges) and appends its files after theirs.
        classic = _core_module("nfl2k5_classic_teams")
        if classic is None:
            raise RuntimeError("the classic teams module is not available in this build")
        progress("Adding the classic teams to Quick Game", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Classic teams")
        classic_receipt = classic.apply_to_image(target, retail)
        receipt["steps"].append({"step": "classic_teams", **classic_receipt})
        receipt["result"]["classic_teams"] = classic.image_status(target, retail)
        if receipt["result"]["classic_teams"] != "applied":
            raise ValueError("the classic teams failed their read-back on the copy")
    if is_image and (plan.espn25_rosters or plan.espn25_more_moments or (plan.classic_teams and plan.historic_teams_quick_game)):
        # b776-fs1 (Noah 10/18): after every roster writer, the retail face scans the 2026 league overwrote are copied
        # into unused head ids; the Anniversary and classic rosters above already point at them.
        scans = _core_module("nfl2k5_moment_scans")
        if scans is None:
            raise RuntimeError("the moment face scans module is not available in this build")
        progress("Copying retail face scans for the Anniversary and classic teams", 0, 0)
        scans_source = require_step_source(source if _retail_source is None else _retail_source, "Moment face scans")
        scans_receipt = scans.apply_to_image(target, scans_source)
        receipt["steps"].append({"step": "moment_scans", **scans_receipt})
        receipt["result"]["moment_scans"] = scans.image_status(target, scans_source)
        if receipt["result"]["moment_scans"] != "applied":
            raise ValueError("the moment face scans failed their read-back on the copy")
    if loaded_weather_plan is not None:
        weather = _core_module("nfl2k5_weather")
        progress("Applying saved stadium climate edits", 0, 0)
        climate_receipt = weather.apply_to_image(target, loaded_weather_plan)
        weather.verify(weather.load_resource(target), loaded_weather_plan)
        receipt["steps"].append({"step": "weather_plan", **climate_receipt})
        receipt["result"]["weather_plan"] = "applied"
    if plan.modern_color:
        modern = _core_module("nfl2k5_modern_color")
        progress("Modern colour and lighting: stadium bundles", 0, 0)
        bundle_receipt = modern.apply_to_image(target, progress=progress, settings=plan.modern_color_settings, source_receipt=modern.read_image_receipt(source))
        receipt["steps"].append({"step": "modern_color_bundles", **{k: v for k, v in bundle_receipt.items() if k != "edits"}})
        receipt["result"]["modern_color"] = bundle_receipt["state"]
        receipt["result"]["modern_color_settings"] = bundle_receipt["settings"]
    if plan.modern_arrowhead:
        arrowhead = _core_module("nfl2k5_modern_arrowhead")
        progress("Modern Arrowhead: stadium packages", 0, 0)
        # On a colour build this reads the RETAIL stadium bundles again, to
        # compose the arrowhead art with the graded field before writing. Those
        # bytes belong to the disc the user chose, never to ``plan.source``: on
        # a project build that is the project's private copy, which the copy
        # step above consumed (beta 74 moves it onto the output rather than
        # copying it 6 GB at a time), and the retail bundles in it may carry
        # the project's own texture edits besides. Reported by Smuzz on
        # 2026-09-21 as "[Errno 2] No such file or directory:
        # ...\.studio-build-aqijzioj\project\source.iso".
        retail = require_step_source(source if _retail_source is None else _retail_source, "Modern Arrowhead")
        arrowhead_receipt = arrowhead.apply_to_image(target, progress=progress, retail_source=retail)
        receipt["steps"].append({"step": "modern_arrowhead", **{k: v for k, v in arrowhead_receipt.items() if k != "edits"}})
        receipt["result"]["modern_arrowhead"] = "applied"
    if plan.modern_metlife:
        # Same source rule as Arrowhead: a colour build composes the MetLife field art with the retail field
        # read from the disc the user chose. The venue name is written into the copy's own main ROST after
        # every roster owner above.
        metlife = _core_module("nfl2k5_modern_metlife")
        progress("Modern MetLife Stadium: Giants and Jets packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Modern MetLife Stadium")
        metlife_receipt = metlife.apply_to_image(target, progress=progress, retail_source=retail)
        receipt["steps"].append({"step": "modern_metlife", **{k: v for k, v in metlife_receipt.items() if k != "edits"}})
        receipt["result"]["modern_metlife"] = "applied"
    if plan.modern_venues_2026:
        # b76-u4: every team's 2026 field and wall art in its home stadium. Same source rule as Arrowhead and
        # MetLife: on a colour build the field art is composed with the retail field read from the disc the user
        # chose; the Giants and Jets packages stay MetLife's, and Kansas City needs Modern Arrowhead off.
        venues26 = _core_module("nfl2k5_modern_venues_2026")
        progress("2026 venue art: home stadium packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "2026 venue art")
        venues_receipt = venues26.apply_to_image(target, plan.modern_venues_2026, progress=progress, retail_source=retail,
                                                 modern_arrowhead=plan.modern_arrowhead, sofi=plan.modern_sofi,
                                                 highmark=plan.modern_highmark, att=plan.modern_att,
                                                 levis=plan.modern_levis, allegiant=plan.modern_allegiant,
                                                 mercedes_benz=plan.modern_mercedes_benz,
                                                 usbank=plan.modern_usbank,
                                                 lucas_oil=plan.modern_lucas_oil, state_farm=plan.modern_state_farm,
                                                 hard_rock=plan.modern_hard_rock, gillette=plan.modern_gillette,
                                                 lambeau=plan.modern_lambeau, everbank=plan.modern_everbank)
        receipt["steps"].append({"step": "modern_venues_2026", **venues_receipt})
        receipt["result"]["modern_venues_2026"] = "applied"
    if plan.modern_metlife_model:
        # b76-u5: after the skin: the model stretch (stadium and intro cameras) of the eighteen bundles and the
        # 2026 superfans, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        metlife_model = _core_module("nfl2k5_metlife_model")
        progress("Modern MetLife model: Giants and Jets packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Modern MetLife model")
        model_receipt = metlife_model.apply_to_image(target, progress=progress, retail_source=retail)
        receipt["steps"].append({"step": "modern_metlife_model", **{k: v for k, v in model_receipt.items()
                                                                    if k not in ("bundles", "crowd")}})
        receipt["result"]["modern_metlife_model"] = "applied"
    if plan.modern_sofi:
        # b76-u6: after Modern colour and the 2026 venue art: the eighteen Rams and Chargers packages (the field art
        # composed before the colour grade, the stadium, cameras and cityscape stretch) and the two stadium rows,
        # same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        sofi = _core_module("nfl2k5_sofi_model")
        progress("SoFi Stadium: Rams and Chargers packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "SoFi Stadium")
        sofi_receipt = sofi.apply_to_image(target, progress=progress, retail_source=retail,
                                             art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_sofi", **sofi_receipt})
        receipt["result"]["modern_sofi"] = "applied"
    if plan.modern_highmark:
        # b76-st: after Modern colour and the 2026 venue art: the nine Bills packages (the field composed before the
        # colour grade with the venue art folder's Bills end zones and midfield, the stadium, cameras and cityscape
        # stretch) and the s03 row, same-size writes compiled from the retail disc the user chose (the Arrowhead source
        # rule).
        highmark = _core_module("nfl2k5_highmark_model")
        progress("Highmark Stadium: Bills packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Highmark Stadium")
        highmark_receipt = highmark.apply_to_image(target, progress=progress, retail_source=retail,
                                                   art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_highmark", **highmark_receipt})
        receipt["result"]["modern_highmark"] = "applied"
    if plan.modern_att:
        # b76-st2: after Modern colour and the 2026 venue art: the nine Cowboys packages (the field composed before the
        # colour grade with the venue art folder's Cowboys end zones and midfield, the stadium and camera stretch) and the
        # s07 row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        att = _core_module("nfl2k5_att_model")
        progress("AT&T Stadium: Cowboys packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "AT&T Stadium")
        att_receipt = att.apply_to_image(target, progress=progress, retail_source=retail,
                                         art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_att", **att_receipt})
        receipt["result"]["modern_att"] = "applied"
    if plan.modern_levis:
        # b76-st2: after Modern colour and the 2026 venue art: the nine 49ers packages (the field composed before the
        # colour grade with the venue art folder's 49ers end zones and midfield, the collapsed cityscape, the stadium and
        # camera stretch) and the s25 row, same-size writes compiled from the retail disc the user chose.
        levis = _core_module("nfl2k5_levis_model")
        progress("Levi's Stadium: 49ers packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Levi's Stadium")
        levis_receipt = levis.apply_to_image(target, progress=progress, retail_source=retail,
                                             art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_levis", **levis_receipt})
        receipt["result"]["modern_levis"] = "applied"
    if plan.modern_allegiant:
        # b76-st2: after Modern colour and the 2026 venue art: the nine Raiders packages (the field composed before the
        # colour grade with the venue art folder's Raiders end zones and midfield, the stadium and camera stretch) and
        # the s20 row, same-size writes compiled from the retail disc the user chose.
        allegiant = _core_module("nfl2k5_allegiant_model")
        progress("Allegiant Stadium: Raiders packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Allegiant Stadium")
        allegiant_receipt = allegiant.apply_to_image(target, progress=progress, retail_source=retail,
                                                     art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_allegiant", **allegiant_receipt})
        receipt["result"]["modern_allegiant"] = "applied"
    if plan.modern_mercedes_benz:
        # b76-st2: after Modern colour and the 2026 venue art: the nine Falcons packages (the field composed before the
        # colour grade with the venue art folder's Falcons end zones and midfield, the stadium and camera stretch) and
        # the s01 row, same-size writes compiled from the retail disc the user chose.
        mercedes_benz = _core_module("nfl2k5_mercedes_benz_model")
        progress("Mercedes-Benz Stadium: Falcons packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Mercedes-Benz Stadium")
        mercedes_benz_receipt = mercedes_benz.apply_to_image(target, progress=progress, retail_source=retail,
                                                             art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_mercedes_benz", **mercedes_benz_receipt})
        receipt["result"]["modern_mercedes_benz"] = "applied"
    if plan.modern_usbank:
        # b76-st3: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Vikings packages (the
        # field composed before the colour grade with the venue art folder's Vikings end zones and midfield head, its
        # turf and apron on the Modern surfaces palette; the stadium and camera stretch) and the s15 row, same-size
        # writes compiled from the retail disc the user chose (the Arrowhead source rule).
        usbank = _core_module("nfl2k5_usbank_model")
        progress("U.S. Bank Stadium: Vikings packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "U.S. Bank Stadium")
        usbank_receipt = usbank.apply_to_image(target, progress=progress, retail_source=retail,
                                               art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_usbank", **usbank_receipt})
        receipt["result"]["modern_usbank"] = "applied"
    if plan.modern_lucas_oil:
        # b76-st3: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Colts packages (the field
        # composed before the colour grade with the venue art folder's Colts end zones and midfield, its turf and apron on
        # the Modern surfaces palette; the stadium and camera stretch) and the s11 row, same-size writes compiled from the
        # retail disc the user chose (the Arrowhead source rule).
        lucas_oil = _core_module("nfl2k5_lucas_oil_model")
        progress("Lucas Oil Stadium: Colts packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Lucas Oil Stadium")
        lucas_oil_receipt = lucas_oil.apply_to_image(target, progress=progress, retail_source=retail,
                                                     art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_lucas_oil", **lucas_oil_receipt})
        receipt["result"]["modern_lucas_oil"] = "applied"
    if plan.modern_state_farm:
        # b76-st3: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Cardinals packages (the
        # field composed before the colour grade with the venue art folder's Cardinals end zones and midfield, its grass
        # and apron on the Modern surfaces palette; the collapsed cityscape, the stadium and camera stretch) and the s00
        # row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        state_farm = _core_module("nfl2k5_state_farm_model")
        progress("State Farm Stadium: Cardinals packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "State Farm Stadium")
        state_farm_receipt = state_farm.apply_to_image(target, progress=progress, retail_source=retail,
                                                       art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_state_farm", **state_farm_receipt})
        receipt["result"]["modern_state_farm"] = "applied"
    if plan.modern_hard_rock:
        # b76-st4: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Dolphins packages (the
        # field composed before the colour grade with the venue art folder's Dolphins end zones and midfield, its grass
        # and apron on the Modern surfaces palette; the collapsed cityscape, the stadium and camera stretch) and the s14
        # row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        hard_rock = _core_module("nfl2k5_hard_rock_model")
        progress("Hard Rock Stadium: Dolphins packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Hard Rock Stadium")
        hard_rock_receipt = hard_rock.apply_to_image(target, progress=progress, retail_source=retail,
                                                     art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_hard_rock", **hard_rock_receipt})
        receipt["result"]["modern_hard_rock"] = "applied"
    if plan.modern_gillette:
        # b76-st4: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Patriots packages (the
        # field composed before the colour grade with the venue art folder's Patriots end zones and midfield, its grass
        # and apron on the Modern surfaces palette; the collapsed cityscape, the stadium and camera stretch) and the s16
        # row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        gillette = _core_module("nfl2k5_gillette_model")
        progress("Gillette Stadium: Patriots packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Gillette Stadium")
        gillette_receipt = gillette.apply_to_image(target, progress=progress, retail_source=retail,
                                                   art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_gillette", **gillette_receipt})
        receipt["result"]["modern_gillette"] = "applied"
    if plan.modern_lambeau:
        # b76-st4: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Packers packages (the
        # field composed before the colour grade with the venue art folder's Packers end zones and midfield, its grass
        # and apron on the Modern surfaces palette; the collapsed cityscape, the stadium and camera stretch) and the s10
        # row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule).
        lambeau = _core_module("nfl2k5_lambeau_model")
        progress("Lambeau Field: Packers packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Lambeau Field")
        lambeau_receipt = lambeau.apply_to_image(target, progress=progress, retail_source=retail,
                                                 art_root=plan.modern_venues_2026 or None)
        receipt["steps"].append({"step": "modern_lambeau", **lambeau_receipt})
        receipt["result"]["modern_lambeau"] = "applied"
    if plan.modern_everbank:
        # b76-st4: after Modern colour and the 2026 venue art, before Modern surfaces: the nine Jaguars packages (the
        # field composed before the colour grade with the venue art folder's Jaguars end zones and midfield, its grass
        # and apron on the Modern surfaces palette; the collapsed cityscape, the stadium and camera stretch) and the s12
        # row, same-size writes compiled from the retail disc the user chose (the Arrowhead source rule); the 2026
        # construction (modern_everbank_construction, on by default) or the 2025 stadium.
        everbank = _core_module("nfl2k5_everbank_model")
        progress("EverBank Stadium: Jaguars packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "EverBank Stadium")
        everbank_receipt = everbank.apply_to_image(target, progress=progress, retail_source=retail,
                                                   art_root=plan.modern_venues_2026 or None,
                                                   construction=plan.modern_everbank_construction)
        receipt["steps"].append({"step": "modern_everbank", **everbank_receipt})
        receipt["result"]["modern_everbank"] = "applied"
        # The construction sub-option is read back from the copy now: the build's inspection ran before this step, on
        # the retail Jaguars packages, so the receipt (and the summary) said "retail" for a disc built with the 2026
        # construction on (candidate E, 2026-09-28; the disc itself reads on).
        receipt["result"]["modern_everbank_construction"] = everbank.construction_status(target)
    if plan.modern_board_kit:
        # b76-st5: after Modern colour and the 2026 venue art (which may repaint these stadium scenes' textures): the
        # stadium scenes of the kit's venues renovated in place (geometry only; every texture keeps its index and
        # bytes), and both options' receipts take the new bundle hashes
        board_kit = _core_module("nfl2k5_board_kit")
        progress("Modern stadium boards", 0, 0)
        board_receipt = board_kit.apply_to_image(target, progress=progress, **_board_kit_options(plan))
        receipt["steps"].append({"step": "modern_board_kit", **board_receipt})
        receipt["result"]["modern_board_kit"] = "applied"
        if board_receipt.get("skipped"):  # the Build page names the stadiums that stayed as they were
            receipt["result"]["modern_board_kit_skips"] = [row["stadium"] for row in board_receipt["skipped"]]
    if plan.modern_practice_field:
        # b76-pf: after Modern colour and before Modern playing surfaces (which leaves s32 alone): the nine practice
        # field packages (s32): the stadium, cityscape and camera stretch compiled from the retail disc the user chose,
        # the practice field composed on the retail field (its art, then Modern colour's grade, then job tf's G-A surface
        # with tf's detail normal and divots), the 2026 venue art folder's current NFL shield at midfield when that
        # folder is given (league marks never ship), the colour receipt kept reading applied. Same-size writes; the row
        # is not written.
        practice = _core_module("nfl2k5_practice_field_model")
        progress("Modern practice facility: practice field packages", 0, 0)
        retail = require_step_source(source if _retail_source is None else _retail_source, "Modern practice facility")
        practice_receipt = practice.apply_to_image(target, progress=progress, retail_source=retail,
                                                   art_root=plan.modern_venues_2026 or None,
                                                   team_logo=plan.modern_practice_field_team_logo)
        receipt["steps"].append({"step": "modern_practice_field", **practice_receipt})
        receipt["result"]["modern_practice_field"] = "applied"
    stadium_shadow = _core_module("nfl2k5_stadium_shadow")
    shadow_venues = sorted({p for key, venues in (stadium_shadow.OPTION_VENUES.items() if stadium_shadow else ())
                            if getattr(plan, key, False) is True for p in venues})
    if shadow_venues:
        # b77 st1: after every stadium writer and before Modern playing surfaces: each modern stadium's afternoon field
        # shadow is cast from the stadium its bundle now carries, under the retail venue's sun (a closed roof casts
        # none, as retail's domes); the shadow texture's fixed span only, and Modern colour's and the 2026 venue art's
        # receipts take the new bundle hashes.
        progress("Stadium shadows", 0, 0)
        shadow_receipt = stadium_shadow.apply_to_image(target, shadow_venues, progress=progress)
        receipt["steps"].append({"step": "stadium_shadows", **shadow_receipt})
        receipt["result"]["stadium_shadows"] = shadow_receipt["state"]
    if plan.modern_surfaces:
        # b76-tf: LAST of the stadium writers (after Modern colour, Arrowhead, MetLife and its model, the 2026 venue art,
        # SoFi and Highmark): repaints each home field's surface over whatever they left, refits every field in its
        # fixed span and keeps their receipts reading applied. Same-size writes on the copy; no retail source needed.
        surfaces = _core_module("nfl2k5_modern_surfaces")
        progress("Modern playing surfaces: home-venue fields", 0, 0)
        surface_options = {}
        if plan.modern_venues_2026:
            venues = _core_module("nfl2k5_modern_venues_2026")
            full_normals = venues.field_prefix_loan_prefixes(plan.modern_venues_2026)
            if full_normals:
                surface_options["preserve_full_normal_prefixes"] = full_normals
            normal_loans = venues.field_normal_loan_prefixes(plan.modern_venues_2026)
            if normal_loans:
                surface_options["field_normal_loan_prefixes"] = normal_loans
            # gr3: PIT's late midfield compresses the surfaced normal for its loan, so it takes the tiled art
            midfield_loans = venues.midfield_normal_loan_prefixes(plan.modern_venues_2026)
            if midfield_loans:
                surface_options["tiled_normal_prefixes"] = midfield_loans
        surfaces_receipt = surfaces.apply_to_image(target, progress=progress, **surface_options)
        receipt["steps"].append({"step": "modern_surfaces", **surfaces_receipt})
        receipt["result"]["modern_surfaces"] = surfaces_receipt["state"]
    if plan.modern_venues_2026:
        # s2: PIT borrows losslessly from the completed field detail-normal map.
        # Keep this after surfaces so its full-resolution normal art is retained.
        midfield = _core_module("nfl2k5_midfield_art")
        midfield_receipt = midfield.apply_late_to_image(target, plan.modern_venues_2026, progress=progress)
        if midfield_receipt is not None:
            receipt["steps"].append({"step": "missing_midfield", **midfield_receipt})
    if plan.espn_marks_2026:
        # Four fixed-span GAMEDATA resources, compiled from the copy's own retail spans and resolved through
        # its own XDVDFS and outer tables, so a relocating pass above cannot misplace them.
        # b76 c1: with the sprite scorebug (installed above) the marks accept its appended resources and it accepts
        # the marks; the layout folder lets the marks recognize a scorebug built from the user's own layout.
        marks = _core_module("nfl2k5_espn_marks")
        progress("ESPN presentation marks (2026)", 0, 0)
        marks_receipt = marks.apply_to_image(target, progress=progress, marks_pack=plan.official_marks_pack,
                                             sprite_folder=(plan.scorebug_folder or None) if plan.scorebug_runtime else None)
        receipt["steps"].append({"step": "espn_marks_2026", **marks_receipt})
        receipt["result"]["espn_marks_2026"] = marks_receipt["state"]
    if plan.espn_wipes_boards_2026:  # b76-p2
        # Six fixed-span scene resources (three raw MRKS wipes, three VC-LZ scenes), compiled from the copy's own
        # retail spans and resolved through its own XDVDFS and outer tables after every relocating pass above.
        wipes = _core_module("nfl2k5_espn_wipes_boards")
        progress("ESPN 2026 wipes and boards", 0, 0)
        wipes_receipt = wipes.apply_to_image(target, progress=progress, marks_pack=plan.official_marks_pack)
        receipt["steps"].append({"step": "espn_wipes_boards_2026", **wipes_receipt})
        receipt["result"]["espn_wipes_boards_2026"] = wipes_receipt["state"]
    if plan.kick_meter_2026:  # b76-km
        # Three fixed-span gamedata.iff scenes (KickArrow, KickMeter, windmeter), compiled from the copy's own retail
        # spans and resolved through its own XDVDFS and outer tables after every relocating pass above. With the
        # sprite scorebug (installed above) they accept its appended resources and it accepts them.
        kick_meter = _core_module("nfl2k5_kick_meter_2026")
        progress("Kick meter (2026 ESPN style)", 0, 0)
        kick_receipt = kick_meter.apply_to_image(target, progress=progress,
                                                 sprite_folder=(plan.scorebug_folder or None) if plan.scorebug_runtime else None)
        receipt["steps"].append({"step": "kick_meter_2026", **kick_receipt})
        receipt["result"]["kick_meter_2026"] = kick_receipt["state"]
    if plan.modern_goalposts:  # b77-v1
        # Two fixed-span gamedata.iff scenes (goalpost_shadow, goalpost), found through the copy's own XDVDFS, outer and
        # chunk tables after every relocating pass above and compiled from their own retail spans, then three in-place
        # executable operands with the .text digest re-sealed (after every executable writer above). Composes with the
        # sprite scorebug, the ESPN presentation marks and the kick meter (their gamedata.iff rule accepts these spans).
        goalposts = _core_module("nfl2k5_modern_goalposts")
        progress("Modern goalposts", 0, 0)
        goal_receipt = goalposts.apply_to_image(target, progress=progress)
        receipt["steps"].append({"step": "modern_goalposts", **goal_receipt})
        receipt["result"]["modern_goalposts"] = goal_receipt["state"]
    if plan.modern_coaches:  # b77-co1
        # 32 fixed-span coach scenes (cNN.iff chunk 0), two raw portrait spans in Portrait.iff and two 16-bit coach-record
        # photo ids in the main roster, found through the copy's own outer table after every relocating pass and every
        # roster writer above (a roster whose Dallas or Washington coach names another picture keeps it).
        coaches = _core_module("nfl2k5_modern_coaches")
        progress("2026 head coaches", 0, 0)
        coach_receipt = coaches.apply_to_image(target, progress=progress)
        receipt["steps"].append({"step": "modern_coaches", **coach_receipt})
        receipt["result"]["modern_coaches"] = coach_receipt["state"]
    if plan.modern_fans:  # b77-fr1
        # the 32 clubs' crowd texture sets (four families of 85 outers, standalone TXTR chunks), fixed spans found
        # through the copy's own outer and chunk tables after every relocating pass
        fans = _core_module("nfl2k5_modern_fans")
        progress("2026 fans", 0, 0)
        fan_receipt = fans.apply_to_image(target, progress=progress)
        receipt["steps"].append({"step": "modern_fans", **fan_receipt})
        receipt["result"]["modern_fans"] = fan_receipt["state"]
    if plan.modern_officials:  # b77-rf1
        # the referee scene, the caps TSET and the seven number TXTR chunks of gamedata.iff: fixed spans found by kind
        # and name through the copy's own outer and chunk tables after every pass that re-lays gamedata.iff
        officials = _core_module("nfl2k5_modern_officials")
        progress("2025-26 officials", 0, 0)
        official_receipt = officials.apply_to_image(target, progress=progress)
        receipt["steps"].append({"step": "modern_officials", **official_receipt})
        receipt["result"]["modern_officials"] = official_receipt["state"]
    if plan.modern_helmets:
        # b76-hm: after every relocating pass, the historic rosters, One-pool positions and the Guardian overlay (the
        # historic fix is field level, the player scenes commute with the overlay's shell B).
        helmets = _core_module("nfl2k5_modern_helmets")
        progress("Modern helmets and facemasks", 0, 0)
        helmets_receipt = helmets.apply_to_image(target, progress=progress)
        receipt["steps"].append({"step": "modern_helmets", **helmets_receipt})
        receipt["result"]["modern_helmets"] = helmets_receipt["status"]
    if plan.hair_styles:
        # b775-hs1: after Modern helmets (its in-place scene writes are judged under the hair growth) and after every
        # executable writer: the two player scenes grow, nine hair textures are appended to outer 3 (pack 0 is
        # rewritten at the end of the copy), then the late allocator owner and its hook go into default.xbe.
        hair = _core_module("nfl2k5_hair_styles")
        progress("Hair styles: player models and hair textures", 0, 0)
        hair_receipt = hair.apply_to_image(target, progress=progress)
        hair_xbe, hair_xbe_receipt = hair.apply(_xbe_bytes(target))
        _write_xbe_bytes(target, hair_xbe)
        # the 2026 assignments (data/nfl2k5_hair_styles_2026_roster_edits.json, sourced per player) go into the main
        # roster here, after every roster writer, and only when it is the 2026 league roster they were made on
        hair_roster = hair.apply_assignments(target)
        if hair.image_status(target) != "applied":
            raise RuntimeError("Hair styles: the output image does not read back as applied")
        receipt["steps"].append({"step": "hair_styles", **{k: v for k, v in hair_receipt.items() if k != "scenes"},
                                 "scenes": [{k: v for k, v in r.items() if k in ("key", "growth", "added_vertices")}
                                            for r in hair_receipt.get("scenes", [])],
                                 "xbe": {k: v for k, v in hair_xbe_receipt.items() if k != "edits"},
                                 "roster": hair_roster})
        receipt["result"]["hair_styles"] = "applied"
    if plan.cpu_qb_zone_windows or plan.cpu_qb_recheck or plan.db_ball_play:
        # b776-ai2: the CPU AI owners are the last executable writers. Their allocations are late owners placed after
        # hair_styles (nfl2k5_xbe_space.LATE_OWNERS), so this step must follow it and nothing else moves.
        _apply_cpu_ai(plan, target, receipt, progress)
    _apply_play_art_routes(plan, target, receipt, progress)  # b776-pa2: the last allocator owner
    if _commentary_final_wanted(plan, loaded_espn25_plan):
        # b77-c2: the last roster writer has run (main roster, historic and Anniversary files, the user's Anniversary
        # edits, the historic helmets). The final commentary pass gives every other ROST resource the play-by-play
        # ids the main roster's final pass gives its own, and retires the recorded "double zero" cue that older
        # saves and highlights still carry. Only pbp_id words and one cue-table byte change; see
        # nfl2k5_commentary_final.
        final = _core_module("nfl2k5_commentary_final")
        if final is not None:
            progress("Final commentary pass: historic rosters and the double-zero cue", 0, 0)
            final_receipt = final.apply(target, progress=lambda message: progress(message, 0, 0))
            receipt["steps"].append({"step": "commentary_final", **final_receipt})
    # Repair only the byte-pinned 2026 Denver miniature after project imports.
    # Retail and custom art do not match the pin and remain untouched.
    if is_image:
        icons = _core_module("nfl2k5_menu_icon_orientation")
        icon_receipt = icons.apply_to_image(target)
        receipt["steps"].append({"step": "menu_icon_orientation", **icon_receipt})
    if plan.rookie_faces and is_image:
        # b778-rh1: after every portrait and roster writer above (project art, coaches, moment scans, classic teams,
        # the final commentary pass): the new aggregate copies every portrait as it now stands, and the bank ids are
        # checked against every roster on the copy.
        faces = _core_module("nfl2k5_rookie_faces")
        progress("Rookie faces: new draft headshots", 0, 0)
        alien = _core_module("nfl2k5_alien_prospect") if plan.alien_prospect else None  # b778-ee1
        extras = {} if alien is None else dict(extra_faces=[alien.portrait_face()], extra_appended=alien.appended(target))
        faces_receipt = faces.apply_to_image(target, _xbe_bytes, _write_xbe_bytes,
                                             progress=lambda message: progress(message, 0, 0), **extras)
        receipt["steps"].append({"step": "rookie_faces", **faces_receipt})
        receipt["result"]["rookie_faces"] = faces_receipt["state"]
        if alien is not None:
            # b778-ee1: his portrait and face outers rode the rookie-faces rewrite above; now the gray skin textures
            # (outer 3, before any hair-style textures) and the executable (in place, zero allocator bytes).
            progress("Alien prospect", 0, 0)
            alien_receipt = alien.apply_to_image(target, _xbe_bytes, _write_xbe_bytes,
                                                 progress=lambda message: progress(message, 0, 0))
            receipt["steps"].append({"step": "alien_prospect", **alien_receipt})
            receipt["result"]["alien_prospect"] = alien_receipt["state"]
    # Last resource pass, still inside build()'s disposable output transaction.
    if plan.trim_intro_videos:
        intro = _core_module("nfl2k5_intro_videos")
        progress("Trimming intro videos", 0, 0)
        cut = intro.finish_output(target, progress)
        receipt["steps"].append({"step": "trim_intro_videos", **cut})
        receipt["intro_video_disc_bytes_freed"] = cut["plan"]["disc_bytes_reclaimed"]
        receipt["intro_video_payload_bytes_freed"] = cut["plan"]["archive_bytes_reclaimed"]
        receipt["intro_video_gamedata_memory_credit"] = 0
        receipt["result"].update(trim_intro_videos="applied",
            image_size=cut["verification"]["output_bytes"],
            image_sha256=cut["verification"]["output_sha256"])
    if plan.custom_intro:
        custom_intro = _core_module("nfl2k5_custom_intro")
        progress("Writing the custom intro video", 0, 0)
        intro = custom_intro.finish_output(target, plan.custom_intro, progress)
        planned = {k: v for k, v in intro["plan"].items() if k != "layout"}
        planned["layout_packs"] = intro["plan"]["layout"]["packs"]
        receipt["steps"].append({"step": "custom_intro", **{k: v for k, v in intro.items() if k != "plan"},
                                 "plan": planned})
        receipt["custom_intro_before"] = intro["plan"]["before"]
        receipt["custom_intro_after"] = intro["plan"]["after"]
        receipt["custom_intro_archive_delta_bytes"] = intro["plan"]["archive_delta_bytes"]
        receipt["result"].update(custom_intro="applied",
            image_size=intro["verification"]["output_bytes"],
            image_sha256=intro["verification"]["output_sha256"])
    if plan.espn25_more_moments and (plan.trim_intro_videos or plan.custom_intro):
        # b76-m1: the intro passes lay the outer archive out again after the moments step (the new team files are
        # outer entries in the last pack), so read the moments back once more on the finished copy.
        if _core_module("nfl2k5_espn25_more_moments").image_status(target) != "applied":
            raise ValueError("the extra Anniversary moments did not survive the intro video pass on the copy")
        retail = require_step_source(source if _retail_source is None else _retail_source, "Historic team styles")
        if _core_module("nfl2k5_historic_styles").image_status(target, retail) != "applied":
            raise ValueError("the historic team styles did not survive the intro video pass on the copy")
        if _core_module("nfl2k5_moment_kits").image_status(target) != "applied":
            raise ValueError("the Anniversary moment kits did not survive the intro video pass on the copy")
    if plan.espn25_more_moments:
        progress("Restoring historical Anniversary coaches", 0, 51)
        historical_coaches = _core_module("nfl2k5_moment_coaches")
        coach_source = require_step_source(_retail_source or source, "Historical Anniversary coaches")
        coach_receipt = historical_coaches.apply_to_image(target, coach_source)
        receipt["steps"].append({"step": "moment_coaches", **coach_receipt})
        receipt["result"]["moment_coaches"] = "applied"
        # b775 mo2: the Super Bowl game type and the moment stats readers (the stats blocks rode in the coach SITU).
        progress("Adding Super Bowl context and historical moment stats", 0, 0)
        moment_context = _core_module("nfl2k5_moment_context")
        context_receipt = moment_context.apply_to_image(target)
        receipt["steps"].append({"step": "moment_context", **context_receipt})
        receipt["result"]["moment_context"] = "applied"
        # b776 sbc: the 17 Super Bowl moments open with the booth's "welcome to the Super Bowl" line.
        progress("Adding the Super Bowl booth welcome to the Super Bowl moments", 0, 0)
        moment_booth = _core_module("nfl2k5_moment_booth")
        booth_receipt = moment_booth.apply_to_image(target)
        receipt["steps"].append({"step": "moment_booth", **booth_receipt})
        receipt["result"]["moment_booth"] = "applied"
    # Use the completed venue models and edited SITU, after all other resource passes.
    if plan.espn25_named_previews:
        progress("Building period Anniversary fields", 0, 51)
        field_pack = _core_module("nfl2k5_anniversary_pack")
        if field_pack is None:
            raise ValueError("the Anniversary field compiler is unavailable")
        field_receipt = field_pack.apply_fields_to_image(
            target, retail, progress=lambda i, n, name: progress("Building period Anniversary fields: " + name, i, n),
            user_art=plan.super_bowl_user_art or None, log=lambda line: progress(line, 0, 0))
        receipt["steps"].append({"step": "espn25_fields", **field_receipt})
        receipt["result"]["espn25_fields"] = "applied"
        # b773-me1: the second ball palette the moment-venue selector picks for moments before 2006. b777 ar1: the
        # era ball is switched off in data/nfl2k5_era_ball/manifest.json (Noah: the football looks as it did before),
        # so the ball scene stays the user's own and no selector is installed; the step runs again when it is on.
        era_ball = _core_module("nfl2k5_era_ball")
        if era_ball is None:
            raise ValueError("the era ball compiler is unavailable")
        if era_ball.enabled():
            progress("Giving modern games the modern ball", 0, 0)
            ball_receipt = era_ball.apply_to_image(target)
            receipt["steps"].append({"step": "era_ball", **ball_receipt})
            receipt["result"]["era_ball"] = ball_receipt["state"]
        else:
            receipt["steps"].append({"step": "era_ball", "state": "off", "reason": "switched off in the era ball manifest"})
            receipt["result"]["era_ball"] = "off"
    if plan.modern_surfaces:
        # gr1: every field writer, including the period aliases, has finished.
        # Palette RGB only, preserving painted assets and st1's lighting.
        greens = _core_module("nfl2k5_broadcast_greens")
        if greens is None:
            raise ValueError("the Broadcast greens compiler is unavailable")
        greens_receipt = greens.apply_to_image(
            target, progress=progress, anniversary_receipt=field_receipt if plan.espn25_named_previews else None)
        receipt["steps"].append({"step": "broadcast_greens", **greens_receipt})
        receipt["result"]["broadcast_greens"] = greens_receipt["state"]
    if plan.season_2026 and tt.is_disc_image(target):
        # sb1: the announced Super Bowl hosts (LXII Atlanta, LXIII Las Vegas, LXIV Nashville) for franchise seasons 1
        # to 3: new bundles copied from the finished host bundles after every field and colour pass, with Super Bowl
        # fields; the neutral rows and the executable's season codes point at them.
        hosts = _core_module("nfl2k5_super_bowl_hosts")
        if hosts is None:
            raise ValueError("the Super Bowl hosts step is unavailable")
        progress("Super Bowl hosts for the franchise", 0, 0)
        hosts_receipt = hosts.apply_to_image(target, user_art=plan.super_bowl_user_art or None, progress=progress,
                                             xbe=_xbe_bytes(target))
        executable = hosts_receipt.pop("executable", None)
        if executable is not None:
            _write_xbe_bytes(target, executable)
        for line in hosts_receipt.get("log", ()):
            progress(line, 0, 0)
        receipt["steps"].append({"step": "super_bowl_hosts", **hosts_receipt})
        receipt["result"]["super_bowl_hosts"] = hosts_receipt["state"]
    if plan.team_number_scale:
        # b776-ns1: after every executable writer (the hair styles' late owner and the Super Bowl hosts' season codes): a late
        # allocator owner and its hook after the jersey-number selector call (0x8F580).
        number_scale = _core_module("nfl2k5_team_number_scale")
        progress("Jersey numbers: per-kit size", 0, 0)
        scaled_xbe, number_receipt = number_scale.apply(_xbe_bytes(target), plan.team_number_scale)
        _write_xbe_bytes(target, scaled_xbe)
        if number_scale.read_settings(_xbe_bytes(target)) != {"status": "applied", "scales": plan.team_number_scale}:
            raise RuntimeError("Jersey number sizes: the output executable does not read back as applied")
        receipt["steps"].append({"step": "team_number_scale", **{k: v for k, v in number_receipt.items()
                                                                 if k not in ("edits", "code_install")},
                                 "edits": number_receipt.get("edits", [])})
        receipt["result"]["team_number_scale"] = number_receipt["scales"]
    # b777 (int7 order, nfl2k5_xbe_space.LATE_OWNERS): after the per-kit jersey number size come ol1's run blocking,
    # then qb3's QB accuracy, the last late allocator owner, so nothing else moves.
    _apply_run_blocking(plan, target, receipt, progress)
    _apply_qb_accuracy(plan, target, receipt, progress)
    # b777-tp1: the formation art icon spacing (with play_art_routes) is the last late allocator owner
    _apply_formation_art_spacing(plan, target, receipt, progress)
    # b778-fo1: modern sideline catches (nfl2k5_xbe_space.LATE_OWNERS order)
    _apply_force_out(plan, target, receipt, progress)
    # b778-pi1: franchise practice injuries, after force-out (LATE_OWNERS order)
    _apply_practice_injuries(plan, target, receipt, progress)
    # No cave or allocator request. Integration must keep this after pi1's
    # nfl2k5_practice_injuries writer, which is not on this job's base.
    _apply_sportscenter_lineup(plan, target, receipt, progress)
    # b778-ai5: CPU ball carriers, after the practice injuries owner (LATE_OWNERS order)
    _apply_ball_carriers(plan, target, receipt, progress)
    # b778-fa1: CPU clubs keep their stars, after the other late allocator owners (LATE_OWNERS order)
    _apply_star_retention(plan, target, receipt, progress)
    # b778-st2: rookie stars and career stars, after the last b778 late owner
    _apply_star_career(plan, target, receipt, progress)
    # b778-dr1: the franchise draft clock, the last late allocator owner (nfl2k5_xbe_space.LATE_OWNERS order)
    _apply_draft_clock(plan, target, receipt, progress)
    # b778-pg1: franchise weekly progression, the last late allocator owner (nfl2k5_xbe_space.LATE_OWNERS order)
    _apply_weekly_progression(plan, target, receipt, progress)
    # b778-pg2: the Player Progress screen, after weekly progression (LATE_OWNERS order)
    _apply_player_progress(plan, target, receipt, progress)
    # b778-cr1: the Contracts null-college guard, after the other non-allocating writers
    _apply_contract_college_guard(plan, target, receipt, progress)  # b778-cr1: after the other late owners
    # b778-cb1: cornerback tackle credit, after the Contracts guard (LATE_OWNERS order)
    _apply_sim_cb_tackles(plan, target, receipt, progress)
    # b778-sim1: the simulated-game pace fix is in place and touches no allocator owner
    _apply_sim_stats(plan, target, receipt, progress)
    # b778-sd4: the LED clock, after the cornerback tackle owner (LATE_OWNERS order)
    _apply_clock_led(plan, target, receipt, progress)
    # b778-pc3: pointer-only final executable edit; integration places this after
    # pi1's nfl2k5_practice_injuries. No allocator owner or cave is required.
    _apply_inbox_standings(plan, target, receipt, progress)
    # b778-xs1: the on-demand Career Home gate, after every other late allocator owner (it is last in LATE_OWNERS)
    _apply_module_loader(plan, target, receipt, progress)
    # b778-pg2: the Player Progress screen and weekly snapshot (a late allocator owner after force_out)
    # b778-cb1: cornerback tackle credit, after force_out
    # b778-sd4: modern clock digits, after modern sideline catches
    if plan.indicator_names_style != "retail":
        # Final HUD writer: compresses the existing sprite scene losslessly and
        # fits its private FONT in that same span, after all other HUD owners.
        # retail_persistent writes only the two collector sites (native FONT).
        from . import nfl2k5_indicator_names as indicator_names
        progress("Installing the player name label", 0, 0)
        names_receipt = indicator_names.apply_to_image(target, folder=plan.indicator_names_folder or None,
                                                       style=plan.indicator_names_style)
        receipt["steps"].append({"step": "indicator_names", **names_receipt})
        receipt["result"]["indicator_names"] = names_receipt["state"]
    if tt.is_disc_image(target):
        # DESIGN: all growth writers have finished. Compact only this disposable
        # build copy, then run the publication gates through its new directory.
        from .xdvdfs_compact import finish_private
        compacted = finish_private(target, original=_retail_source or source, progress=progress)
        receipt["disc_compaction"] = compacted
        receipt["result"]["image_size"] = compacted["output_bytes"]
        if plan.trim_intro_videos:
            # The final 64 KiB alignment can consume some staged trim savings.
            # Keep the step plan intact, but report the finished disc reduction.
            receipt["intro_video_disc_bytes_freed"] = cut["plan"]["source_bytes"] - compacted["output_bytes"]
        # build() records the final image digest in its existing single hash pass.
        receipt["result"].pop("image_sha256", None)
    # Publication gate: inspect the actual finished archive and executable,
    # including full archive rewrites and the last paired owner updates.
    if stock_bank is not None:
        receipt["result"]["historic_stock_books"] = _core_module("nfl2k5_stock_books").image_status(target, stock_bank)
        if receipt["result"]["historic_stock_books"] != "applied":
            raise ValueError("stock books did not survive the final resource passes")
    if plan.team_number_scale and _core_module("nfl2k5_team_number_scale").read_settings(_xbe_bytes(target)) != {
            "status": "applied", "scales": plan.team_number_scale}:  # b776-ns1
        raise ValueError("the jersey number sizes did not survive the final passes")
    if plan.run_blocking and _core_module("nfl2k5_run_blocking").status(_xbe_bytes(target)) != "applied":  # b777-ol1
        raise ValueError("run blocking did not survive the final passes")
    if plan.qb_accuracy and _core_module("nfl2k5_qb_accuracy").status(_xbe_bytes(target)) != "applied":  # b777-qb3
        raise ValueError("accurate short throws did not survive the final passes")
    if plan.play_art_routes and _core_module("nfl2k5_formation_art_spacing").status(_xbe_bytes(target)) != "applied":
        raise ValueError("the play art icon spacing did not survive the final passes")  # b777-tp1
    if plan.modern_force_out and _core_module("nfl2k5_force_out").status(_xbe_bytes(target)) != "applied":  # b778-fo1
        raise ValueError("modern sideline catches did not survive the final passes")
    if plan.crib_trophy_room and _core_module("nfl2k5_crib_trophy_room").status(_xbe_bytes(target)) != "applied":  # b778-xs1
        raise ValueError("the Crib Trophy Room cut did not survive the final passes")
    if plan.module_loader and _core_module("nfl2k5_module_loader").status(_xbe_bytes(target)) != "applied":  # b778-xs1
        raise ValueError("the on-demand Career Home gate did not survive the final passes")
    if plan.inbox_standings and _core_module("nfl2k5_inbox_standings").status(_xbe_bytes(target)) != "applied":
        raise ValueError("inbox standings did not survive the final passes")
    if plan.star_retention and _core_module("nfl2k5_star_retention").status(_xbe_bytes(target)) != "applied":  # b778-fa1
        raise ValueError("CPU clubs keep their stars did not survive the final passes")
    if plan.practice_injuries and _core_module("nfl2k5_practice_injuries").status(_xbe_bytes(target)) != "applied":
        raise ValueError("franchise practice injuries did not survive the final passes")  # b778-pi1
    if plan.cpu_ball_carriers and _core_module("nfl2k5_ball_carrier_ai").status(_xbe_bytes(target)) != "applied":  # b778-ai5
        raise ValueError("CPU ball carriers did not survive the final passes")
    if plan.rookie_faces and is_image and _core_module("nfl2k5_rookie_faces").image_status(
            target, _xbe_bytes) != "applied":  # b778-rh1
        raise ValueError("rookie faces did not survive the final passes")
    if plan.alien_prospect and is_image and _core_module("nfl2k5_alien_prospect").image_status(
            target, _xbe_bytes) != "applied":  # b778-ee1
        raise ValueError("the alien prospect did not survive the final passes")
    if plan.sportscenter_lineup and _core_module("nfl2k5_sportscenter_lineup").status(_xbe_bytes(target)) != "applied":
        raise ValueError("SportsCenter highlight lineups did not survive the final passes")
    if plan.franchise_draft_clock and _core_module("nfl2k5_draft_clock").status(_xbe_bytes(target)) != "applied":
        raise ValueError("the franchise draft clock did not survive the final passes")  # b778-dr1
    if plan.weekly_progression and _core_module("nfl2k5_weekly_progression").status(_xbe_bytes(target)) != "applied":
        raise ValueError("weekly player progression did not survive the final passes")  # b778-pg1
    if plan.player_progress and _core_module("nfl2k5_player_progress_screen").status(_xbe_bytes(target)) != "applied":  # b778-pg2
        raise ValueError("the Player Progress screen did not survive the final passes")
    if plan.contract_college_guard and _core_module("nfl2k5_contract_college_guard").status(_xbe_bytes(target)) != "applied":
        raise ValueError("the Player Contracts college guard did not survive the final passes")  # b778-cr1
    if plan.sim_cb_tackles and _core_module("nfl2k5_sim_cb_tackles").status(_xbe_bytes(target)) != "applied":  # b778-cb1
        raise ValueError("cornerback tackle credit did not survive the final passes")
    if plan.sim_stats and _core_module("nfl2k5_sim_stats").status(_xbe_bytes(target)) != "applied":  # b778-sim1
        raise ValueError("the franchise sim pace fix did not survive the final passes")
    if plan.modern_clock_led and _core_module("nfl2k5_clock_led").status(_xbe_bytes(target)) != "applied":  # b778-sd4
        raise ValueError("modern clock digits did not survive the final passes")
    if plan.hair_styles and is_image:  # b778-hr3: scenes, textures, owner + hook and the 2026 roster bytes
        hair_step = next((s for s in receipt["steps"] if s.get("step") == "hair_styles"), {})
        receipt["result"]["hair_styles_final"] = _core_module("nfl2k5_hair_styles").verify_final(
            target, hair_step.get("roster"))
    if plan.espn25_named_previews:
        receipt["result"]["espn25_fields"] = field_pack.verify_fields_on_image(target, field_receipt)["status"]
        receipt["result"]["espn25_named_previews"] = _core_module("nfl2k5_espn25_more_moments").named_image_status(target)
        if (receipt["result"]["espn25_named_previews"] != "applied"
                    or _core_module("nfl2k5_moment_venues").status(_xbe_bytes(target)) != "applied"):
            raise ValueError("named previews did not survive the final resource passes")
        _ball = _core_module("nfl2k5_era_ball")
        receipt["result"]["era_ball"] = _ball.image_status(target) if _ball.enabled() else "off"
        if receipt["result"]["era_ball"] != ("applied" if _ball.enabled() else "off"):
            raise ValueError("the era ball did not survive the final resource passes")
        if not _ball.enabled() and _ball.image_status(target) != "retail":
            raise ValueError("the era ball is off but the ball scene is not the user's own")
    if is_image:
        from .nfl2k5_disc_extents import validate_image
        receipt["disc_extents"] = validate_image(target)
        receipt["playbook_scoring"] = _check_playbook_scoring(target, progress)
    return receipt


def save_receipt(receipt: dict[str, Any], path: Path | str) -> None:
    Path(path).write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8", newline="\n")


__all__ = ["validate_plan", "PLAYBOOK_OPTION_LABELS", "BuildPlan", "CommentarySwap", "PRESETS", "PRESET_TITLES", "apply_preset", "availability", "build", "inspect", "save_receipt"]
