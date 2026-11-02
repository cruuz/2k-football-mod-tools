"""Job b780 j1-standings: Team Standings division / conference records and the home / road / streak view.
EXPERIMENTAL / UNWITNESSED in game.

Static checks run everywhere (template, relocations, sites, guards, model, wiring). The install and native classes map
the retail USA ``default.xbe`` with the owner installed and run the game's own code under Unicorn:

* the real Team Standings draw (FUN_003554B0) on a synthetic franchise league: a full season of regular-season rows
  plus playoff rows in the schedule grid, the division table, club records; every text call is captured (text, font,
  alignment, colour, position). View 0 must be identical to the retail image's calls; views 1 and 2 must show, for all 32
  clubs, exactly the Python model's DIV and CONF records (regular season only, ties, overtime, bye weeks, 17 and 18 week
  seasons) and the game's own HOME, ROAD and STRK values;
* the real input function (FUN_003551A0): White and Black turn the views with the cursor sound, L and R still switch
  AFC and NFC, the realignment screen that shares the code never reacts;
* the real enter callback and the legend function;
* every stub on its own: registers, stack and the retail fall-through.

Substituted leaves are named where used: the text routines (captured), the 3D quad primitives the screen draws behind its
text, the club name lookup 0xC41C0 (a fixed "T##" name), 0xEFB20 and the standings sort 0x2A7C40. Everything else is the
game's code. Nothing here is an in-game result. The native classes skip without the pinned USA XBE or Unicorn.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import random
import re
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_standings_records as sr  # noqa: E402
from mod_editor.core import nfl2k5_standings_records_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None

GRID, SCORES, DIVISIONS, LEAGUE_TEAMS = 0xE57C40, 0xE587F0, 0xE576D4, 0xE5786C
LEAGUE_MODE, LEAGUE_COUNT, USER_CLUB, PADS, SOUND_READY = 0xE576A0, 0xE576AC, 0xE3C0A0, 0xB37A70, 0xAA26B4
SCREEN_MODE, SCREEN_VIEW_CONF, SCREEN_WLT, SCREEN_SORT, SCREEN_CURSOR = 0xAE9ECC, 0xAE9EE4, 0xAE9EE8, 0xAE9EEC, 0xAE9EC8
WEEKS_BYTE = 0x5151C4
DRAW, INPUT, ENTER_RETAIL, LEGEND = 0x3554B0, 0x3551A0, 0x3550F0, 0x355CD0
ENTER_POINTER = 0x54CDB4
TEXT = {"init": 0x46920, "font_get": 0xEF850, "font": 0x469B0, "align": 0x46A00, "colour": 0x46B50, "pos": 0x46A70,
        "posvec": 0x46AC0, "shadow": 0x46B60, "width": 0x46C50, "draw": 0xF1C70}

# A real league (job r4-records, the v0.8 executable under Unicorn, week 1 of a new franchise): the league club index of
# each abbreviation, the division of each league index (0-3 NFC West, North, South, East; 4-7 AFC West, North, South,
# East; the last two are the Pro Bowl squads) and the 16 scores of that week as (away, away points, home, home points).
ABBR = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG", "JAX",
        "NYJ", "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")
REAL_DIVISIONS = (0, 1, 5, 7, 4, 5, 2, 0, 4, 4, 6, 3, 7, 3, 2, 3, 6, 7, 1, 1, 2, 7, 4, 0, 5, 3, 2, 0, 5, 6, 6, 1, 0, 0)
REAL_WEEK_1 = (("SF", 16, "LAR", 23), ("TB", 22, "CIN", 25), ("BAL", 31, "IND", 10), ("CLE", 10, "JAX", 13),
               ("NO", 13, "DET", 20), ("CHI", 20, "CAR", 34), ("ATL", 10, "PIT", 17), ("BUF", 28, "HOU", 31),
               ("NYJ", 27, "TEN", 14), ("ARI", 17, "LAC", 28), ("WAS", 38, "PHI", 24), ("MIA", 12, "LV", 28),
               ("GB", 20, "MIN", 10), ("DAL", 24, "NYG", 7), ("DEN", 27, "KC", 17), ("NE", 23, "SEA", 20))


def _retail() -> bytes | None:
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


_PATCHED = {}


def _patched() -> bytes | None:
    if "p" not in _PATCHED:
        data = _retail()
        _PATCHED["p"] = sr.apply(data)[0] if data else None
    return _PATCHED["p"]


# ---- synthetic seasons -----------------------------------------------------------------------------------------------


def reseal(buf):
    """Recompute every section digest (what the kernel checks), so a tampered image is judged by the owner's own pins."""
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    return bytes(buf)


def blank_tables():
    grid, scores = bytearray(sr.GRID_ROWS * sr.GRID_SLOTS * 8), bytearray(sr.GRID_ROWS * sr.GRID_SLOTS * 10)
    for cell in range(sr.GRID_ROWS * sr.GRID_SLOTS):
        grid[8 * cell] = 7                      # an unused slot, as the game leaves them
    return grid, scores


def put_game(grid, scores, row, slot, home, away, home_points, away_points, *, played=True, overtime=0):
    cell = row * sr.GRID_SLOTS + slot
    grid[8 * cell:8 * cell + 8] = bytes([3 if played else 0, home, away, 0, 0, 0, 0, 0])
    if not played:
        return

    def quarters(total):
        first = min(total, 7)
        rest = total - first - overtime
        parts = [first, max(rest, 0) // 3, max(rest, 0) // 3, max(rest, 0) - 2 * (max(rest, 0) // 3), overtime]
        parts[0] += total - sum(parts)
        return bytes(parts)
    scores[10 * cell:10 * cell + 5] = quarters(home_points)
    scores[10 * cell + 5:10 * cell + 10] = quarters(away_points)


def season(seed, *, weeks=17, playoff_rows=4, played_weeks=None, divisions=REAL_DIVISIONS):
    """A random season: every regular-season week pairs the 32 clubs (some on a bye, some weeks all inside divisions), a
    few ties and overtime games, then playoff rows. ``played_weeks`` leaves the later weeks scheduled but unplayed."""

    rng = random.Random(seed)
    grid, scores = blank_tables()
    division_weeks = set(rng.sample(range(weeks), 6))
    for row in range(weeks + playoff_rows):
        clubs = list(range(32))
        rng.shuffle(clubs)
        if row in division_weeks:
            pairs = []
            for d in range(8):
                members = [c for c in range(32) if divisions[c] == d]
                rng.shuffle(members)
                pairs += [(members[0], members[1]), (members[2], members[3])]
            rng.shuffle(pairs)
        elif row < weeks:
            byes = 2 * rng.randrange(0, 3)
            pairs = [(clubs[i], clubs[i + 1]) for i in range(0, 32 - byes, 2)]
        else:
            count = (6, 4, 2, 1)[row - weeks] if row - weeks < 4 else 1
            pairs = [(clubs[2 * i], clubs[2 * i + 1]) for i in range(count)]
        for slot, (a, b) in enumerate(pairs):
            home, away = (a, b) if rng.random() < .5 else (b, a)
            kind = rng.random()
            hp, ap = rng.randrange(0, 45), rng.randrange(0, 45)
            ot = 0
            if kind < .07:
                ap = hp                                  # a tie
            elif kind < .14:
                ot, ap = rng.randrange(1, 4), hp + rng.choice((-3, 3, 6))      # overtime decided it
                hp = max(hp, ot)
                ap = max(ap, ot)
            played = played_weeks is None or row < played_weeks or row >= weeks and played_weeks >= weeks
            put_game(grid, scores, row, slot, home, away, hp, ap, played=played, overtime=min(ot, hp, ap))
    return bytes(grid), bytes(scores)


def real_week_one():
    grid, scores = blank_tables()
    for slot, (away, ap, home, hp) in enumerate(REAL_WEEK_1):
        put_game(grid, scores, 0, slot, ABBR.index(home), ABBR.index(away), hp, ap)
    return bytes(grid), bytes(scores)


# ---- static tests ----------------------------------------------------------------------------------------------------


class StaticTests(unittest.TestCase):
    """Runs everywhere."""

    def test_template_fits_and_relocations_are_owned(self):
        self.assertLessEqual(len(runtime.CODE), sr.CODE_SIZE)
        self.assertEqual(sr.REQUESTS, (("nfl2k5_standings_records", "code", 2048, 16), ("nfl2k5_standings_records", "data", 16, 16)))
        for offset, kind, symbol, value in runtime.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertIn(symbol, ("code", "state"))
            self.assertLessEqual(offset + 4, len(runtime.CODE))
            if symbol == "code":
                self.assertLessEqual(value, len(runtime.CODE))
        for entry in ("sr_input", "sr_hdr0", "sr_hdr1", "sr_hdr2", "sr_cell0", "sr_cell1", "sr_cell2", "sr_leg0", "sr_leg1",
                      "sr_leg2", "sr_leg3", "sr_enter", "sr_buttons", "sr_header", "sr_cell_text", "sr_legend"):
            self.assertIn(entry, runtime.LABELS)

    def test_code_for_relocates_against_both_blocks(self):
        a = sr.code_for(0x14DA000, 0x14F2000)
        b = sr.code_for(0x14DB000, 0x14F2010)
        self.assertEqual(len(a), sr.CODE_SIZE)
        self.assertTrue(a.endswith(b"\xcc" * (sr.CODE_SIZE - len(runtime.CODE))))
        differ = {i for i in range(len(a)) if a[i] != b[i]}
        state_fields = {off for off, _k, sym, _v in runtime.RELOCATIONS if sym == "state"}
        code_abs = {off for off, kind, sym, _v in runtime.RELOCATIONS if sym == "code" and kind == 1}
        allowed = {off + k for off in state_fields | code_abs for k in range(4)}
        self.assertTrue(differ)
        self.assertTrue(differ <= allowed)       # PC-relative calls inside the blob do not change with its address
        for off in state_fields:
            self.assertEqual(struct.unpack_from("<I", a, off)[0], 0x14F2000)
            self.assertEqual(struct.unpack_from("<I", b, off)[0], 0x14F2010)
        for off in code_abs:                      # the pointer tables (headers, legends) point into the blob
            self.assertTrue(0x14DA000 <= struct.unpack_from("<I", a, off)[0] < 0x14DA000 + sr.CODE_SIZE)

    def test_sites_are_whole_instructions_calling_the_entries(self):
        code_va = 0x14DA000
        at = sr.labels(code_va)
        rows = sr.sites(code_va)
        self.assertEqual([r[0] for r in rows], ["input", "header_w", "header_l", "header_t", "cell_w", "cell_l", "cell_t",
                                                "legend_1", "legend_2", "legend_3", "legend_4"])
        spans = []
        for (label, va, before, after), (_l, _v, _b, entry, _k) in zip(rows, sr.SITE_TABLE):
            self.assertEqual(len(before), len(after), label)
            self.assertEqual(after[0], 0xE8, label)
            self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], at[entry], label)
            self.assertEqual(after[5:], b"\x90" * (len(before) - 5), label)
            spans.append((va, va + len(before)))
        self.assertEqual(sr.SITE_TABLE[0][2].hex(), "8b442414f6c4c0")         # the pressed mask and the L/R test
        self.assertEqual(len(sr.SITE_TABLE[0][2]), 7)
        spans.sort()
        for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0)                                       # no two sites overlap
        label, va, before, after = sr.data_edits(code_va)[0]
        self.assertEqual((label, va), ("enter_pointer", 0x54CDB4))
        self.assertEqual(before, struct.pack("<I", ENTER_RETAIL))
        self.assertEqual(struct.unpack("<I", after)[0], at["sr_enter"])

    def test_guards_are_pinned(self):
        self.assertEqual([name for name, _va, _size in sr.GUARDS], list(sr.GUARD_SHA256_PINNED))
        for digest in sr.GUARD_SHA256_PINNED.values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(len(set(sr.GUARD_SHA256_PINNED.values())), len(sr.GUARD_SHA256_PINNED))

    def test_caption_and_help_are_plain_words(self):
        self.assertLessEqual(len(sr.BUILD_CAPTION), 60)
        for text in (sr.BUILD_CAPTION, sr.HELP_TEXT):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
            text.encode("ascii")
        for word in ("White", "Black", "DIV", "CONF", "HOME", "ROAD", "STRK", "EXPERIMENTAL"):
            self.assertIn(word, sr.HELP_TEXT)

    def test_runtime_source_is_ascii(self):
        folder = ROOT / "tools" / "nfl2k5_standings_records"
        if not folder.is_dir():
            self.skipTest("tool sources are not in this tree")
        for name in ("runtime.c", "stubs.S"):
            (folder / name).read_text(encoding="ascii")

    def test_late_owner_is_last(self):
        self.assertEqual(space.LATE_OWNERS[-1], sr.OWNER)
        self.assertEqual(space.LATE_OWNERS[-3:], ("nfl2k5_sim_realism", "nfl2k5_sim_realism_state", sr.OWNER))
        self.assertEqual(space.LATE_OWNERS.count(sr.OWNER), 1)

    def test_allocates_in_the_complete_owner_union_without_moving_any_owner(self):
        union = list(space.dormant_union())
        before = {(r["owner"], r["kind"]): (r["va"], r["size"]) for r in space._scale_allocations(union)}
        after_rows = space._scale_allocations(union + list(sr.REQUESTS))
        after = {(r["owner"], r["kind"]): (r["va"], r["size"]) for r in after_rows}
        self.assertEqual({k: v for k, v in after.items() if k in before}, before)           # nothing moved
        mine = {k: v for k, v in after.items() if k[0] == sr.OWNER}
        self.assertEqual({k[1]: v[1] for k, v in mine.items()}, {"code": sr.CODE_SIZE, "data": sr.DATA_SIZE})
        self.assertTrue(all(va % 16 == 0 for va, _size in mine.values()))
        plan = space.plan(union + list(sr.REQUESTS), scaleout=True)                       # the allocator accepts the set
        self.assertGreater(plan["capacity"]["pool"]["max_pages"], plan["capacity"]["pool"]["pages"])

    def test_template_is_fresh_when_the_pinned_toolchain_is_here(self):
        import shutil
        import subprocess
        tool = ROOT / "tools" / "nfl2k5_standings_records_build.py"
        if not tool.is_file() or not shutil.which("gcc") or not shutil.which("as") or not shutil.which("ld"):
            self.skipTest("the build tool or the toolchain is not here")
        gcc = subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout
        binutils = subprocess.run(["as", "--version"], capture_output=True, text=True).stdout
        if "13.3" not in gcc.splitlines()[0] or "2.42" not in binutils.splitlines()[0]:
            self.skipTest("the template was generated with gcc 13.3 and binutils 2.42")
        spec = importlib.util.spec_from_file_location("sr_build", tool)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        target = ROOT / "mod_editor" / "core" / "nfl2k5_standings_records_code.py"
        self.assertEqual(target.read_text(encoding="utf-8"), build.generate(), "run tools/nfl2k5_standings_records_build.py")


class ModelTests(unittest.TestCase):
    """The Python model of what the screen must show."""

    def test_conference_table_matches_the_game(self):
        self.assertEqual(sr.CONFERENCE_OF_DIVISION, (1, 1, 1, 1, 0, 0, 0, 0))
        self.assertEqual(len(REAL_DIVISIONS), 34)
        for d in range(8):
            self.assertEqual(sum(1 for c in range(32) if REAL_DIVISIONS[c] == d), 4)

    def test_real_week_one(self):
        grid, scores = real_week_one()
        rec = sr.division_conference_records(grid, scores, REAL_DIVISIONS)
        club = ABBR.index
        # SF 16 at LAR 23: both NFC West, so a division and a conference game (the research report's own example)
        self.assertEqual(rec[club("LAR")], {"div": [1, 0, 0], "conf": [1, 0, 0]})
        self.assertEqual(rec[club("SF")], {"div": [0, 1, 0], "conf": [0, 1, 0]})
        # NE 23 at SEA 20: an AFC club at an NFC club: neither
        self.assertEqual(rec[club("SEA")], {"div": [0, 0, 0], "conf": [0, 0, 0]})
        # GB 20 at MIN 10: NFC North
        self.assertEqual(rec[club("GB")], {"div": [1, 0, 0], "conf": [1, 0, 0]})
        # CHI 20 at CAR 34: NFC, different divisions: conference only
        self.assertEqual(rec[club("CAR")], {"div": [0, 0, 0], "conf": [1, 0, 0]})
        self.assertEqual(rec[club("CHI")], {"div": [0, 0, 0], "conf": [0, 1, 0]})
        # BUF 28 at HOU 31: AFC East at AFC South
        self.assertEqual(rec[club("HOU")], {"div": [0, 0, 0], "conf": [1, 0, 0]})
        # ARI 17 at LAC 28: NFC West at AFC West: nothing counts
        self.assertEqual(rec[club("LAC")], {"div": [0, 0, 0], "conf": [0, 0, 0]})

    def test_every_game_counts_for_both_clubs_once(self):
        grid, scores = season(5)
        rec = sr.division_conference_records(grid, scores, REAL_DIVISIONS)
        games = list(sr._cell_games(grid, scores, 17))
        same_div = sum(1 for _r, _s, h, a, _hp, _ap in games if REAL_DIVISIONS[h] == REAL_DIVISIONS[a])
        same_conf = sum(1 for _r, _s, h, a, _hp, _ap in games
                        if sr.CONFERENCE_OF_DIVISION[REAL_DIVISIONS[h]] == sr.CONFERENCE_OF_DIVISION[REAL_DIVISIONS[a]])
        self.assertGreater(same_div, 20)
        self.assertEqual(sum(sum(r["div"]) for r in rec), 2 * same_div)
        self.assertEqual(sum(sum(r["conf"]) for r in rec), 2 * same_conf)
        for r in rec:                                  # a division game is also a conference game
            self.assertLessEqual(sum(r["div"]), sum(r["conf"]))
            self.assertLessEqual(sum(r["conf"]), 17)   # at most one game a week

    def test_wins_and_losses_mirror_between_the_two_clubs(self):
        grid, scores = season(11)
        rec = sr.division_conference_records(grid, scores, REAL_DIVISIONS)
        for key in ("div", "conf"):
            self.assertEqual(sum(r[key][0] for r in rec), sum(r[key][1] for r in rec))     # every win is a loss elsewhere
            self.assertEqual(sum(r[key][2] for r in rec) % 2, 0)                           # a tie is two clubs' tie

    def test_playoff_rows_and_unplayed_cells_are_excluded(self):
        grid, scores = season(7, weeks=17, playoff_rows=4)
        with_playoffs = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=21)
        regular = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=17)
        self.assertNotEqual(with_playoffs, regular)                 # the playoff rows do hold games
        self.assertEqual(regular, sr.division_conference_records(*season(7, weeks=17, playoff_rows=0), REAL_DIVISIONS, weeks=17))
        partial = season(7, weeks=17, playoff_rows=0, played_weeks=9)
        self.assertEqual(sr.division_conference_records(*partial, REAL_DIVISIONS, weeks=17),
                         sr.division_conference_records(*partial, REAL_DIVISIONS, weeks=9))

    def test_eighteen_week_season_counts_the_extra_row(self):
        grid, scores = season(3, weeks=18, playoff_rows=4)
        seventeen = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=17)
        eighteen = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=18)
        self.assertNotEqual(seventeen, eighteen)
        self.assertEqual(sum(sum(r["conf"]) for r in eighteen) - sum(sum(r["conf"]) for r in seventeen),
                         2 * sum(1 for _r, _s, h, a, _x, _y in sr._cell_games(grid, scores, 18)
                                 if _r == 17 and sr.CONFERENCE_OF_DIVISION[REAL_DIVISIONS[h]] == sr.CONFERENCE_OF_DIVISION[REAL_DIVISIONS[a]]))

    def test_ties_and_overtime(self):
        grid, scores = blank_tables()
        a, b = ABBR.index("DAL"), ABBR.index("PHI")                  # NFC East rivals
        put_game(grid, scores, 0, 0, a, b, 20, 20)                   # a tie
        put_game(grid, scores, 1, 0, a, b, 23, 20, overtime=3)       # a field goal in overtime
        put_game(grid, scores, 2, 0, b, a, 17, 14)                   # the other club at home
        rec = sr.division_conference_records(bytes(grid), bytes(scores), REAL_DIVISIONS)
        self.assertEqual(rec[a]["div"], [1, 1, 1])
        self.assertEqual(rec[b]["div"], [1, 1, 1])
        self.assertEqual(sr.format_record(rec[a]["div"]), "1-1-1")
        self.assertEqual(sr.format_record([4, 2, 0]), "4-2")

    def test_format_and_streak(self):
        self.assertEqual(sr.format_record([10, 5, 1]), "10-5-1")
        self.assertEqual(sr.format_streak(3, 0), "W3")
        self.assertEqual(sr.format_streak(0, 2), "L2")
        self.assertEqual(sr.format_streak(0, 0), "--")

    def test_home_road_and_streaks_follow_the_game_rules(self):
        grid, scores = blank_tables()
        a, b, c = ABBR.index("DAL"), ABBR.index("PHI"), ABBR.index("NYG")
        put_game(grid, scores, 0, 0, a, b, 20, 10)       # DAL wins at home
        put_game(grid, scores, 1, 0, c, a, 10, 17)       # DAL wins on the road
        put_game(grid, scores, 2, 0, a, c, 14, 14)       # a tie clears both streaks
        put_game(grid, scores, 3, 0, b, a, 30, 7)        # DAL loses on the road
        put_game(grid, scores, 4, 0, a, b, 3, 9)         # DAL loses at home
        grid, scores = bytes(grid), bytes(scores)
        hr = sr.home_road_records(grid, scores)
        self.assertEqual((hr[a]["home"], hr[a]["road"]), ([1, 1, 1], [1, 1, 0]))
        self.assertEqual(sr.streaks(grid, scores)[a], (0, 2))
        self.assertEqual(sr.streaks(grid, scores)[b], (2, 0))


class WiringTests(unittest.TestCase):
    """The option is wired the way the other late-owner options are."""

    def test_build_plan_and_presets(self):
        from mod_editor.core import mod_build
        plan = mod_build.BuildPlan(Path("source.iso"), Path("target.iso"))
        self.assertIs(plan.standings_records, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["standings_records"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertTrue(plan.__class__(Path("s.iso"), Path("t.iso"), standings_records=True).wants_xbe_patch())

    def test_settings_key_and_panel_row(self):
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("standings_records", settings.FEATURE_KEYS)
        text = (ROOT / "mod_editor" / "gui" / "build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("standings_records", _standings_records.BUILD_CAPTION, _standings_records.HELP_TEXT)', text)

    def test_allocation_request_joins_the_union_only_when_selected(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        on = tt._selected_space_requests(standings_records=True)
        off = tt._selected_space_requests()
        self.assertEqual([r for r in on if r[0] == sr.OWNER], list(sr.REQUESTS))
        self.assertEqual([r for r in off if r[0] == sr.OWNER], [])
        self.assertEqual(sorted(set(on) - set(off)), sorted(sr.REQUESTS))
        adapter = tt._xbe_space_adapter(standings_records=True)
        self.assertTrue(adapter.scaleout)
        self.assertEqual([r for r in adapter.requests if r[0] == sr.OWNER], list(sr.REQUESTS))

    def test_late_owner_option_row_and_packaging(self):
        from mod_editor.core import mod_build
        rows = [row for row in mod_build._LATE_OWNER_OPTIONS if row[0] == sr.OWNER]
        self.assertEqual(len(rows), 1)
        plan = mod_build.BuildPlan(Path("s.iso"), Path("t.iso"))
        self.assertFalse(rows[0][2](plan))
        self.assertTrue(rows[0][2](mod_build.BuildPlan(Path("s.iso"), Path("t.iso"), standings_records=True)))
        allow = ROOT / "packaging" / "release-allowlist.txt"
        if allow.is_file():
            lines = set(allow.read_text(encoding="utf-8").splitlines())
            for path in ("mod_editor/core/nfl2k5_standings_records.py", "mod_editor/core/nfl2k5_standings_records_code.py",
                         "tests/mod_editor/test_nfl2k5_standings_records.py"):
                self.assertIn(path, lines)
        providers = (ROOT / "mod_editor" / "core" / "providers.py").read_text(encoding="utf-8")
        for path in ("mod_editor/core/nfl2k5_standings_records.py", "mod_editor/core/nfl2k5_standings_records_code.py"):
            self.assertIn(f'"{path}": "', providers)

    def test_capability_registry_entry(self):
        import json
        data = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        rows = [c for c in data["capabilities"] if c["id"] == "nfl2k5.franchise.standings_records"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["game"], "nfl2k5_xbox")
        self.assertEqual(row["backend"]["module"], "mod_editor/core/nfl2k5_standings_records.py")
        self.assertEqual([f["name"] for f in row["selectors"]["fields"]], ["standings_records"])
        self.assertIs(row["gui"]["default_enabled"], False)
        self.assertEqual(row["runtime"]["status"], "not-tested")


# ---- Unicorn: the game's own code with the owner installed -------------------------------------------------------------


class Machine:
    """The image mapped section by section, a heap, ranged call hooks (a hook costs nothing outside its address)."""

    HEAP, STACK, STOP = 0x3000000, 0x4000000, 0x5000000
    SP = STACK + 0xF000

    def __init__(self, payload: bytes):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = {}
        for s in image.sections:
            for page in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096):
                pages[page] = True
        regions = []
        for page in sorted(pages):
            if regions and regions[-1][1] == page:
                regions[-1][1] += 4096
            else:
                regions.append([page, page + 4096])
        for start, end in regions:
            self.uc.mem_map(start, end - start)
        for s in image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for va, size in ((self.HEAP, 0x100000), (self.STACK, 0x10000), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        self.calls = []

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)
        return value

    def wide(self, va, limit=120):
        raw = bytes(self.uc.mem_read(va, limit * 2))
        end = next((i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0"), len(raw))
        return raw[:end].decode("utf-16le")

    def float_at(self, va):
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    def hook(self, va, fn, pop=0):
        """Replace the function at ``va``: fn(machine) -> eax or None; ``pop`` = stack bytes the callee removes."""

        def callback(_uc, _address, _size, _data):
            result = fn(self)
            sp = self.reg("ESP")
            ret = self.get(sp)
            if result is not None:
                self.reg("EAX", result)
            self.reg("ESP", sp + 4 + pop)
            self.reg("EIP", ret)
        self.uc.hook_add(self.u.UC_HOOK_CODE, callback, begin=va, end=va)

    def call(self, va, ecx=0, edx=0, stack=(), regs=None, budget=200_000_000):
        sp = self.SP
        for value in reversed(list(stack)):
            sp -= 4
            self.put(sp, value)
        sp -= 4
        self.put(sp, self.STOP)
        self.reg("ESP", sp)
        self.reg("ECX", ecx)
        self.reg("EDX", edx)
        for name in ("EBX", "ESI", "EDI", "EBP"):
            self.reg(name, 0x0BADF00D)
        for name, value in (regs or {}).items():
            self.reg(name, value)
        self.uc.emu_start(va, self.STOP, count=budget)
        if self.reg("EIP") != self.STOP:
            raise AssertionError(f"instruction budget exhausted at {self.reg('EIP'):#x}, entry {va:#x}")
        return self.reg("EAX")


class Standings(Machine):
    """A synthetic franchise league the Team Standings code can run on."""

    CLUBS_AT = Machine.HEAP + 0x4000        # 34 club records, stride 0x1F4
    NAMES_AT = Machine.HEAP + 0x40000       # a wide "T##" name per club
    SCREEN = Machine.HEAP + 0x60000

    def __init__(self, payload, grid, scores, *, view=0, conference=0, standings=True, weeks=17, user=0,
                 divisions=REAL_DIVISIONS, state_va=None, retail_counts=True, state=None):
        super().__init__(payload)
        self.state_va = state_va
        self.text, self.contexts, self.sound = [], {}, []
        for index in range(34):
            record = self.CLUBS_AT + index * 0x1F4
            self.uc.mem_write(record, bytes(0x1F4))
            self.put(LEAGUE_TEAMS + 4 * index, record)
            self.put(record + 0x130, divisions[index])               # the club's own division word
            self.put(DIVISIONS + 4 * index, divisions[index])
            self.uc.mem_write(self.NAMES_AT + 0x20 * index, f"T{index:02d}".encode("utf-16le") + b"\0\0")
        self.put(LEAGUE_MODE, 2)
        self.put(LEAGUE_COUNT, 34)
        self.put(USER_CLUB, self.club(user))
        self.uc.mem_write(GRID, grid)
        self.uc.mem_write(SCORES, scores)
        self.uc.mem_write(WEEKS_BYTE, bytes([weeks]))
        self.put(SCREEN_MODE, 0)
        self.put(SCREEN_VIEW_CONF, conference)
        self.put(SCREEN_WLT, 1 if standings else 0)
        self.put(SCREEN_SORT, 1)
        self.put(SCREEN_CURSOR, 0)
        self.put(SOUND_READY, 1)
        if state_va is not None:
            self.put(state_va, view if state is None else state)
        self._capture_text()
        for va, pop in ((0x6BBE0, 0x14), (0x6BC30, 0x1C), (0x6A970, 0x1C)):     # quads drawn behind the text
            self.hook(va, lambda m: None, pop)
        for va, value in ((0x69260, 0x1111), (0x69E70, 0x2222), (0x68E10, 0x3333), (0x49410, 18)):
            self.hook(va, lambda m, value=value: value)
        self.hook(0xC41C0, lambda m: self.NAMES_AT + 0x20 * ((m.reg("ECX") - self.CLUBS_AT) // 0x1F4))
        self.hook(0xEFB20, lambda m: m.reg("EDX"), pop=4)                            # the name, clipped to a width
        self.hook(0x2A7C40, lambda m: None)                                          # the standings sort
        self.hook(0x38650, lambda m: 0x1234)                                         # the sound lookup and play
        self.hook(0x89DA0, lambda m: self.sound.append(m.reg("ECX")), pop=0x18)
        if not retail_counts:                                                        # a faster draw: the W L T counts are not read
            for va in (0xC7720, 0xC7750, 0xC7780):
                self.hook(va, lambda m: 0)

    def club(self, index):
        return self.CLUBS_AT + index * 0x1F4

    def _capture_text(self):
        ctx = self.contexts

        def entry(m):
            return ctx.setdefault(m.reg("ECX"), {"font": None, "align": None, "colour": None, "pos": None})

        def pos(m):
            sp = m.reg("ESP")
            entry(m)["pos"] = (m.float_at(sp + 4), m.float_at(sp + 8), m.float_at(sp + 12))

        def posvec(m):
            entry(m)["pos"] = struct.unpack("<3f", bytes(m.uc.mem_read(m.reg("EDX"), 12)))

        def draw(m):
            d = dict(ctx.get(m.reg("ECX"), {}))
            self.text.append((m.wide(m.reg("EDX")), d.get("font"), d.get("align"), d.get("colour"), d.get("pos")))
        self.hook(TEXT["init"], lambda m: ctx.__setitem__(m.reg("ECX"), {"font": None, "align": None, "colour": None, "pos": None}))
        self.hook(TEXT["font_get"], lambda m: 0x7000 + m.reg("ECX"))
        self.hook(TEXT["font"], lambda m: entry(m).__setitem__("font", m.reg("EDX") - 0x7000))
        self.hook(TEXT["align"], lambda m: entry(m).__setitem__("align", m.reg("EDX")))
        self.hook(TEXT["colour"], lambda m: entry(m).__setitem__("colour", m.reg("EDX")))
        self.hook(TEXT["shadow"], lambda m: None)
        self.hook(TEXT["pos"], pos, pop=12)
        self.hook(TEXT["posvec"], posvec)
        self.hook(TEXT["width"], lambda m: 9 * len(m.wide(m.reg("EDX"))))        # nine units a character
        self.hook(TEXT["draw"], draw)

    # ---- running the screen ----
    def draw(self):
        self.text.clear()
        self.call(DRAW)
        return list(self.text)

    def legend(self):
        self.text.clear()
        self.call(LEGEND)
        return list(self.text)

    def pad_frame(self, pressed, *, repeat=0, view=None):
        if view is not None:
            self.put(self.state_va, view)
        self.put(PADS + 0x00, 1)                       # controller 0 present
        self.put(PADS + 0x08, pressed)                 # pressed this frame
        self.put(PADS + 0x0C, repeat)
        for port in range(1, 8):
            self.put(PADS + port * 0x244, 0)
        self.put(self.SCREEN + 0x10C, self.SCREEN + 0x200)     # screen param -> instance
        self.put(self.SCREEN + 0x200 + 0x590, 0)               # no pad filter
        self.sound.clear()
        self.call(INPUT, ecx=self.SCREEN)
        return self.get(self.state_va) if self.state_va is not None else None


def parse(text):
    """The captured draw as {club: [cell, cell, cell]} plus the header labels of each division block."""

    blocks, clubs, current = [], {}, None
    i = 0
    while i < len(text):
        label = text[i][0]
        match = re.fullmatch(r"T(\d\d)", label)
        if match and text[i][3] is not None:
            clubs[int(match.group(1))] = [(t[0], t[4]) for t in text[i + 1:i + 4]]
            i += 4
            continue
        if text[i][1] == 4 and label not in ("W", "L", "T"):          # a division name, drawn in the big font
            current = {"name": label, "labels": [(t[0], t[4]) for t in text[i + 1:i + 4]]}
            blocks.append(current)
            i += 4
            continue
        i += 1
    return blocks, clubs


def conference_clubs(conference, divisions=REAL_DIVISIONS):
    conf_id = 1 if conference == 0 else 0           # screen conference 0 is the NFC (conference id 1)
    return [c for c in range(32) if sr.CONFERENCE_OF_DIVISION[divisions[c]] == conf_id]


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched = _patched()

    def test_retail_is_retail_and_patched_is_applied(self):
        self.assertEqual(sr.status(self.retail), "retail")
        self.assertEqual(sr.status(self.patched), "applied")
        self.assertEqual(space.status(self.patched), "applied")
        settings = sr.read_settings(self.patched)
        self.assertTrue(settings["standings_records"])
        self.assertEqual(settings["views"], sr.VIEWS)
        self.assertFalse(sr.read_settings(self.retail)["standings_records"])

    def test_apply_is_idempotent_and_edits_only_its_sites(self):
        again, receipt = sr.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        found = sr.allocations(self.patched)
        self.assertEqual((found["code"]["size"], found["code"]["align"]), (sr.CODE_SIZE, 16))
        self.assertEqual((found["data"]["size"], found["data"]["align"]), (sr.DATA_SIZE, 16))
        code_va = found["code"]["va"]
        edited = {va + i for _l, va, before, _a in sr.sites(code_va) + sr.data_edits(code_va) for i in range(len(before))}
        self.assertEqual(len(edited), 7 + 10 * 5 + 4)
        # in the game's own sections nothing but the eleven call sites and the enter pointer changed
        changed = set()
        for section in XbeImage(self.retail).sections:
            before = self.retail[section.raw:section.raw + section.raw_size]
            after = self.patched[section.raw:section.raw + section.raw_size]
            changed |= {section.start + i for i in range(len(before)) if before[i] != after[i]}
        self.assertEqual(sorted(changed - edited), [])
        self.assertGreater(len(changed), 50)

    def test_a_single_foreign_site_is_refused(self):
        code_va = sr.allocations(self.patched)["code"]["va"]
        for label, va, before, _after in sr.sites(code_va) + sr.data_edits(code_va):
            with self.subTest(site=label):
                buf = bytearray(self.patched)
                off = rdata.offset_of(self.patched, va)
                buf[off:off + len(before)] = before
                self.assertEqual(sr.status(reseal(buf)), "foreign")        # a half install, with a valid section digest

    def test_a_changed_dependency_is_refused(self):
        # the section digests are recomputed, so only this owner's own pins can refuse these images
        for name, va, _size in sr.GUARDS:
            if name == "standings screen":
                va = 0x355500                                               # inside the draw function
            elif name == "standings descriptors":
                va = 0x54CC70                                               # a handler descriptor, not the enter pointer
            with self.subTest(dependency=name):
                buf = bytearray(self.retail)
                buf[rdata.offset_of(self.retail, va)] ^= 0xFF
                tampered = reseal(buf)
                self.assertEqual(space.status(tampered), "retail")
                self.assertEqual(sr.status(tampered), "foreign")
                with self.assertRaises(sr.StandingsRecordsError):
                    sr.apply(tampered)

    def test_build_step_installs_reads_back_and_is_skipped_when_off(self):
        import tempfile
        from mod_editor.core import mod_build
        progress = lambda *args: None  # noqa: E731
        self.assertTrue(mod_build.availability()["standings_records"])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "default.xbe"
            target.write_bytes(self.retail)
            self.assertEqual(mod_build.inspect(target)["standings_records"], "retail")
            receipt = {"steps": [], "result": {}}
            mod_build._apply_standings_records(mod_build.BuildPlan(Path("source.xbe"), target), target, receipt, progress)
            self.assertEqual(target.read_bytes(), self.retail)                       # off: nothing is written
            self.assertEqual(receipt["steps"], [])
            plan = mod_build.BuildPlan(Path("source.xbe"), target, standings_records=True)
            mod_build._standings_records_preflight(target, progress)                 # a retail source passes
            mod_build._apply_standings_records(plan, target, receipt, progress)
            self.assertEqual(sr.status(target.read_bytes()), "applied")
            self.assertEqual(mod_build.inspect(target)["standings_records"], "applied")
            self.assertEqual(receipt["result"]["standings_records"], "applied")
            self.assertEqual([step["step"] for step in receipt["steps"]], ["standings_records"])
            self.assertNotIn("reservations", receipt["steps"][0])
            mod_build._standings_records_preflight(target, progress)                 # an installed one passes too
            buf = bytearray(self.retail)
            buf[rdata.offset_of(self.retail, 0xC6B70)] ^= 0xFF                       # the game's home record routine, changed
            target.write_bytes(reseal(buf))
            with self.assertRaises(ValueError):
                mod_build._standings_records_preflight(target, progress)             # refused before any write
            self.assertEqual(mod_build.inspect(target)["standings_records"], "foreign")

    def test_the_regular_season_row_count_must_be_17_or_18(self):
        def with_weeks(value):
            buf = bytearray(self.retail)
            buf[rdata.offset_of(self.retail, WEEKS_BYTE)] = value
            return reseal(buf)
        self.assertEqual(sr.status(with_weeks(18)), "retail")
        self.assertEqual(sr.status(sr.apply(with_weeks(18))[0]), "applied")
        self.assertEqual(sr.status(with_weeks(19)), "foreign")
        self.assertEqual(sr.status(with_weeks(16)), "foreign")

    def test_state_must_start_zero_and_code_must_match(self):
        found = sr.allocations(self.patched)
        buf = bytearray(self.patched)
        buf[XbeImage(self.patched).offset(found["data"]["va"], 1)] = 2
        self.assertEqual(sr.status(reseal(buf)), "foreign")
        buf = bytearray(self.patched)
        buf[XbeImage(self.patched).offset(found["code"]["va"] + 0x20, 1)] ^= 0x55
        self.assertEqual(sr.status(reseal(buf)), "foreign")

    def test_composes_with_the_other_late_owners_and_moves_nothing(self):
        """The build applies late owners in LATE_OWNERS order and this one is last: appended to an image that already
        carries another owner it moves nothing and leaves that owner applied. The reverse (an earlier owner appended
        after this one) is refused by the allocator, not silently moved."""
        from mod_editor.core import nfl2k5_honors as honors, nfl2k5_pass_rush_stats as prs, nfl2k5_sim_realism as realism
        for name, module in (("honors", honors), ("pass rush stats", prs), ("sim realism", realism)):
            with self.subTest(owner=name):
                theirs, _ = module.apply(self.retail)
                mine, _ = sr.apply(theirs)
                self.assertEqual((sr.status(mine), module.status(mine)), ("applied", "applied"))
                before = {(r["owner"], r["kind"]): r["va"] for r in space.layout(theirs)["allocations"]}
                after = {(r["owner"], r["kind"]): r["va"] for r in space.layout(mine)["allocations"]}
                self.assertEqual({k: v for k, v in after.items() if k in before}, before)     # nothing moved
                self.assertEqual({k for k in after if k not in before},
                                 {(sr.OWNER, "code"), (sr.OWNER, "data")})
                first, _ = sr.apply(self.retail)
                with self.assertRaises(ValueError):
                    module.apply(first)


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched = _patched()
        found = sr.allocations(cls.patched)
        cls.code_va, cls.state = found["code"]["va"], found["data"]["va"]
        cls.at = sr.labels(cls.code_va)
        cls.grid, cls.scores = season(1)

    def game(self, grid=None, scores=None, *, patched=True, **kwargs):
        grid = self.grid if grid is None else grid
        scores = self.scores if scores is None else scores
        if patched:
            return Standings(self.patched, grid, scores, state_va=self.state, **kwargs)
        return Standings(self.retail, grid, scores, **kwargs)

    # --- the screen as the player sees it --------------------------------------------------------------------------
    def test_view_zero_is_the_retail_screen_call_for_call(self):
        for conference in (0, 1):
            for standings in (True, False):
                with self.subTest(conference=conference, standings=standings):
                    retail = self.game(patched=False, conference=conference, standings=standings).draw()
                    patched = self.game(view=0, conference=conference, standings=standings).draw()
                    self.assertGreater(len(retail), 70 if standings else 15)       # 80 texts on the standings, 20 names on the other
                    self.assertEqual(patched, retail)
        legend_retail = self.game(patched=False).legend()
        self.assertEqual(self.game(view=0).legend(), legend_retail)
        self.assertEqual([t[0] for t in legend_retail], ["x - clinched playoff berth", "y - clinched division title",
                                                         "z - clinched first round bye", "* - clinched home field adv."])

    def test_the_realignment_screen_never_changes(self):
        retail = self.game(patched=False, standings=False).draw()
        for view in (1, 2):
            with self.subTest(view=view):
                self.assertEqual(self.game(view=view, standings=False).draw(), retail)

    def test_division_and_conference_records_on_screen_equal_the_model(self):
        for seed in (1, 2, 3, 4, 5, 6):
            grid, scores = season(seed, weeks=17)
            model = sr.division_conference_records(grid, scores, REAL_DIVISIONS)
            for conference in (0, 1):
                with self.subTest(seed=seed, conference=conference):
                    text = self.game(grid, scores, view=1, conference=conference, retail_counts=False).draw()
                    blocks, clubs = parse(text)
                    self.assertEqual(sorted(clubs), conference_clubs(conference))
                    self.assertEqual(len(blocks), 4)
                    for club, cells in clubs.items():
                        self.assertEqual(cells[0][0], sr.format_record(model[club]["div"]), f"DIV of club {club}")
                        self.assertEqual(cells[1][0], "")
                        self.assertEqual(cells[2][0], sr.format_record(model[club]["conf"]), f"CONF of club {club}")
                    for block in blocks:
                        self.assertEqual([label for label, _pos in block["labels"]], ["DIV", " ", "CONF"])

    def test_played_week_one_matches_the_researched_numbers(self):
        grid, scores = real_week_one()
        for conference, expected in ((0, {"LAR": ("1-0", "1-0"), "SF": ("0-1", "0-1"), "SEA": ("0-0", "0-0"),
                                          "CAR": ("0-0", "1-0"), "CHI": ("0-0", "0-1"), "GB": ("1-0", "1-0")}),
                                     (1, {"HOU": ("0-0", "1-0"), "BUF": ("0-0", "0-1"), "LAC": ("0-0", "0-0")})):
            blocks, clubs = parse(self.game(grid, scores, view=1, conference=conference).draw())
            for abbr, (div, conf) in expected.items():
                self.assertEqual((clubs[ABBR.index(abbr)][0][0], clubs[ABBR.index(abbr)][2][0]), (div, conf), abbr)

    def test_regular_season_only_and_the_week_count(self):
        grid, scores = season(9, weeks=18, playoff_rows=4)
        for weeks in (17, 18):
            model = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=weeks)
            blocks, clubs = parse(self.game(grid, scores, view=1, conference=0, weeks=weeks, retail_counts=False).draw())
            for club, cells in clubs.items():
                with self.subTest(weeks=weeks, club=club):
                    self.assertEqual((cells[0][0], cells[2][0]),
                                     (sr.format_record(model[club]["div"]), sr.format_record(model[club]["conf"])))
        # the retail W L T count every row, playoff games included; DIV and CONF never do
        retail_w = parse(self.game(grid, scores, view=0, conference=0).draw())[1]
        everything = {c: sum(1 for _r, _s, h, a, hp, ap in sr._cell_games(grid, scores, 22)
                             if (h == c and hp > ap) or (a == c and ap > hp)) for c in retail_w}
        self.assertEqual({c: int(cells[0][0]) for c, cells in retail_w.items()}, everything)

    def test_home_road_and_streak_are_the_games_own_values(self):
        for seed in (2, 8):
            grid, scores = season(seed)
            home_road = sr.home_road_records(grid, scores)
            streak = sr.streaks(grid, scores)
            for conference in (0, 1):
                with self.subTest(seed=seed, conference=conference):
                    blocks, clubs = parse(self.game(grid, scores, view=2, conference=conference, retail_counts=False).draw())
                    self.assertEqual(sorted(clubs), conference_clubs(conference))
                    for club, cells in clubs.items():
                        self.assertEqual(cells[0][0], sr.format_record(home_road[club]["home"]), f"HOME of club {club}")
                        self.assertEqual(cells[1][0], sr.format_record(home_road[club]["road"]), f"ROAD of club {club}")
                        self.assertEqual(cells[2][0], sr.format_streak(*streak[club]), f"STRK of club {club}")
                    for block in blocks:
                        self.assertEqual([label for label, _pos in block["labels"]], ["HOME", "ROAD", "STRK"])

    def test_cells_keep_their_rows_and_stay_inside_their_blocks(self):
        grid, scores = season(4)
        base_blocks, base_clubs = parse(self.game(grid, scores, view=0, conference=1).draw())
        for view, shifts in ((1, (-5, 0, 5)), (2, (-18, 1, 20))):
            blocks, clubs = parse(self.game(grid, scores, view=view, conference=1, retail_counts=False).draw())
            self.assertEqual(sorted(clubs), sorted(base_clubs))
            for club, cells in clubs.items():
                for column in range(3):
                    pos, base = cells[column][1], base_clubs[club][column][1]
                    self.assertEqual(pos, (base[0] + shifts[column], base[1], base[2]))     # same row and depth, shifted
                    block = 280 if base[0] > 400 else 0                                    # the left or the right division block
                    self.assertTrue(170 + block <= pos[0] <= 322 + block, (view, club, pos))
            self.assertEqual([b["name"] for b in blocks], [b["name"] for b in base_blocks])
            for block, base in zip(blocks, base_blocks):
                self.assertEqual([pos[1:] for _t, pos in block["labels"]], [pos[1:] for _t, pos in base["labels"]])

    def test_header_labels_are_centered_over_their_columns(self):
        grid, scores = season(4)
        for view, texts, shifts in ((1, ("DIV", " ", "CONF"), (-5, 0, 5)), (2, ("HOME", "ROAD", "STRK"), (-18, 1, 20))):
            blocks, _clubs = parse(self.game(grid, scores, view=view, conference=0, retail_counts=False).draw())
            for block_index, block in enumerate(blocks):
                offset = 280 if block["labels"][0][1][0] > 400 else 0
                for (label, pos), text, column, shift in zip(block["labels"], texts, (220, 250, 280), shifts):
                    self.assertEqual(label, text)
                    width = 9 * len(text)                                          # the test's text width: nine units a character
                    self.assertEqual(pos[0], offset + column + shift - width // 2, (view, block_index, label))
                self.assertIn(block["name"], ("NORTH", "SOUTH", "EAST", "WEST"))

    def test_legend_follows_the_view(self):
        retail = self.game(patched=False).legend()
        views = {1: ["DIV - division record", "CONF - conference record", "Regular season games only",
                     "White/Black - change columns"],
                 2: ["HOME - record at home", "ROAD - record on the road", "STRK - current streak",
                     "White/Black - change columns"]}
        for view, lines in views.items():
            text = self.game(view=view).legend()
            self.assertEqual([t[0] for t in text], lines)
            self.assertEqual([t[1:] for t in text], [t[1:] for t in retail])          # same font, alignment, colour, positions
        for line in sum(views.values(), []):
            self.assertLessEqual(len(line), 30)
            line.encode("ascii")
        self.assertEqual(self.game(view=7).legend(), retail)                           # a damaged view reads as retail

    def test_a_damaged_view_draws_the_retail_screen(self):
        retail = self.game(patched=False, conference=0).draw()
        for damaged in (3, 4, 0x80000000, 0xFFFFFFFF):
            with self.subTest(view=damaged):
                self.assertEqual(self.game(view=damaged, conference=0).draw(), retail)

    def test_the_draw_reads_the_season_and_writes_nothing_of_it(self):
        grid, scores = season(10)
        game = self.game(grid, scores, view=1, retail_counts=False)
        watched = ((GRID, len(grid)), (SCORES, len(scores)), (DIVISIONS, 34 * 4), (0x5151C4, 4))
        writes = []

        def on_write(_uc, _access, address, size, _value, _data):
            writes.append((address, size))
        for start, length in watched:
            game.uc.hook_add(game.u.UC_HOOK_MEM_WRITE, on_write, begin=start, end=start + length - 1)
        game.draw()
        game.pad_frame(0x1000, view=2)
        game.draw()
        self.assertEqual(writes, [])
        self.assertEqual(bytes(game.uc.mem_read(GRID, len(grid))), grid)
        self.assertEqual(bytes(game.uc.mem_read(SCORES, len(scores))), scores)

    # --- the buttons -----------------------------------------------------------------------------------------------
    def test_black_goes_forward_and_white_goes_back_with_the_cursor_sound(self):
        game = self.game()
        for pressed, name, order in ((0x1000, "Black", (0, 1, 2, 0)), (0x2000, "White", (0, 2, 1, 0))):
            view = 0
            for expected in order[1:]:
                with self.subTest(button=name, to=expected):
                    self.assertEqual(game.pad_frame(pressed, view=view), expected)
                    self.assertEqual(len(game.sound), 1)                     # one cursor sound, the retail one
                    view = expected
        self.assertEqual(game.pad_frame(0x1000 | 0x2000, view=0), 1)         # both at once: Black wins
        self.assertEqual(game.pad_frame(0x1000, view=9), 1)                  # a damaged view starts over
        self.assertEqual(game.pad_frame(0x2000, view=9), 2)

    def test_other_buttons_do_nothing_and_l_r_still_switch_the_conference(self):
        game = self.game()
        for pressed in (0x100, 0x200, 0x400, 0x800, 0x10, 0x20, 0x40, 0x80, 0x100000):
            with self.subTest(pressed=hex(pressed)):
                self.assertEqual(game.pad_frame(pressed, view=1), 1)
                self.assertEqual(game.get(SCREEN_VIEW_CONF), 0)
                self.assertEqual(game.sound, [])
        for pressed in (0x4000, 0x8000, 0xC000):                              # the triggers: retail's AFC / NFC switch
            game.put(SCREEN_VIEW_CONF, 0)
            self.assertEqual(game.pad_frame(pressed, view=2), 2)              # the view stays
            self.assertEqual(game.get(SCREEN_VIEW_CONF), 1)
            self.assertEqual(len(game.sound), 1)
        game.put(SCREEN_VIEW_CONF, 1)
        game.pad_frame(0x8000, view=0)
        self.assertEqual(game.get(SCREEN_VIEW_CONF), 0)
        # White with a trigger: the view turns and the conference switches, two sounds
        game.put(SCREEN_VIEW_CONF, 0)
        self.assertEqual(game.pad_frame(0x2000 | 0x4000, view=0), 2)
        self.assertEqual((game.get(SCREEN_VIEW_CONF), len(game.sound)), (1, 2))

    def test_the_realignment_screen_ignores_white_and_black(self):
        game = self.game(standings=False)
        game.put(SCREEN_MODE, 1)
        for pressed in (0x1000, 0x2000):
            self.assertEqual(game.pad_frame(pressed, view=0), 0)
            self.assertEqual(game.sound, [])
        game.put(SCREEN_MODE, 0)
        self.assertEqual(game.pad_frame(0x1000, view=0), 0)

    def test_the_retail_input_function_ignores_white_and_black(self):
        game = self.game(patched=False)
        game.put(PADS, 1)
        game.put(PADS + 8, 0x3000)
        game.put(game.SCREEN + 0x10C, game.SCREEN + 0x200)
        game.put(game.SCREEN + 0x200 + 0x590, 0)
        game.call(INPUT, ecx=game.SCREEN)
        self.assertEqual(game.sound, [])

    def test_every_visit_opens_on_the_retail_columns(self):
        pointer = self.patched[rdata.offset_of(self.patched, ENTER_POINTER):][:4]
        self.assertEqual(struct.unpack("<I", pointer)[0], self.at["sr_enter"])
        for club, wlt_conf in ((ABBR.index("NYG"), 0), (ABBR.index("NE"), 1)):
            game = self.game(user=club, standings=False)
            for view in (0, 1, 2):
                game.put(self.state, view)
                game.call(self.at["sr_enter"], ecx=game.SCREEN)
                self.assertEqual(game.get(self.state), 0)
                self.assertEqual((game.get(SCREEN_MODE), game.get(SCREEN_WLT), game.get(SCREEN_SORT)), (0, 1, 1))
                self.assertEqual(game.get(SCREEN_VIEW_CONF), wlt_conf)           # the user's own conference first
            retail = self.game(patched=False, user=club, standings=False)
            retail.call(ENTER_RETAIL, ecx=retail.SCREEN)
            self.assertEqual(retail.get(SCREEN_VIEW_CONF), wlt_conf)

    # --- the stubs one at a time -----------------------------------------------------------------------------------
    def stub_frame(self, game, *, pos=(220.0, 118.0, 21.0), view=1):
        """A fake caller frame above the stub's return address: the position vector at [esp_s + 0x28]."""
        game.put(self.state, view)
        base = game.SP - 4                       # esp at the stub's entry once `call` has pushed the return address
        return base

    def test_cell_stub_handles_a_cell_and_leaves_the_registers_alone(self):
        grid, scores = real_week_one()
        sf = ABBR.index("SF")                              # lost at LAR in week 1: DIV 0-1, CONF 0-1, no home game, ROAD 0-1
        for view, col, expected, shift in ((1, 0, "0-1", -5), (1, 2, "0-1", 5), (1, 1, "", 0), (2, 0, "0-0", -18),
                                           (2, 1, "0-1", 1), (2, 2, "L1", 20)):
            with self.subTest(view=view, column=col):
                game = self.game(grid, scores, view=view)
                buf = game.HEAP + 0x70000
                game.uc.mem_write(buf, b"\xaa" * 64)
                esp_entry = game.SP - 4 - 4                # the return address and the retail formatter's one stack argument
                pos_va = esp_entry + 0x28                  # the caller's text position vector, [esp+0x20] of its frame
                game.uc.mem_write(pos_va, struct.pack("<3f", 220.0, 118.0, 21.0))
                regs = {"EDI": game.club(sf), "EBX": 0x11111111, "ESI": 0x22222222, "EBP": 0x33333333}
                game.call(self.at["sr_cell%d" % col], ecx=buf, edx=0x1234, stack=(game.HEAP + 0x71000,), regs=regs)
                for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EBP", 0x33333333), ("EDI", game.club(sf))):
                    self.assertEqual(game.reg(name), value, name)
                self.assertEqual(game.wide(buf), expected)
                self.assertEqual(struct.unpack("<3f", bytes(game.uc.mem_read(pos_va, 12))), (220.0 + shift, 118.0, 21.0))
                self.assertEqual(game.reg("ESP"), game.SP)  # "ret 4": past the return address and the argument, as the formatter

    def test_cell_stub_in_view_zero_jumps_to_the_retail_formatter_unchanged(self):
        game = self.game(view=0)
        seen = []
        game.hook(0x4A400, lambda m: seen.append((m.reg("ECX"), m.reg("EDX"), m.get(m.reg("ESP") + 4))), pop=4)
        pos_va = game.SP - 8 + 0x28
        game.uc.mem_write(pos_va, struct.pack("<3f", 220.0, 118.0, 21.0))
        for col in range(3):
            game.call(self.at["sr_cell%d" % col], ecx=0x9000 + col, edx=0xEB3C94, stack=(0x7000 + col,), regs={"EDI": 0x5555})
        self.assertEqual(seen, [(0x9000, 0xEB3C94, 0x7000), (0x9001, 0xEB3C94, 0x7001), (0x9002, 0xEB3C94, 0x7002)])
        self.assertEqual(struct.unpack("<3f", bytes(game.uc.mem_read(pos_va, 12))), (220.0, 118.0, 21.0))

    def test_header_stub_returns_the_label_and_keeps_the_registers(self):
        for view, col, label in ((0, 0, 0xEB3C88), (0, 1, 0xEB3C8C), (0, 2, 0xEB3C90)):
            game = self.game(view=view)
            game.call(self.at["sr_hdr%d" % col], regs={"EBX": 0x11111111, "ESI": 0x22222222, "EDI": 0x33333333, "EBP": 0x44444444})
            self.assertEqual(game.reg("EDX"), label)
            for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
                self.assertEqual(game.reg(name), value, name)
        for view, col, text in ((1, 0, "DIV"), (1, 2, "CONF"), (2, 1, "ROAD")):
            game = self.game(view=view)
            game.call(self.at["sr_hdr%d" % col], regs={"EBX": 0x11111111, "ESI": 0x22222222, "EDI": 0x33333333, "EBP": 0x44444444})
            self.assertEqual(game.wide(game.reg("EDX")), text)
            self.assertEqual(game.reg("ESP"), game.SP - 4 + 4)
            for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
                self.assertEqual(game.reg(name), value, name)

    def test_input_stub_sets_the_flags_the_callers_branch_reads(self):
        for pressed, zero in ((0x0000, True), (0x4000, False), (0x8000, False), (0xC000, False), (0x3000, True), (0x1000, True)):
            game = self.game(view=0)
            game.put(SCREEN_WLT, 0)                    # the realignment case: only the retail test runs
            esp_entry = game.SP - 4
            game.put(esp_entry + 0x18, pressed)
            game.call(self.at["sr_input"])
            self.assertEqual(bool(game.reg("EFLAGS") & 0x40), zero, hex(pressed))       # ZF from "test ah, 0xC0"
            self.assertEqual(game.reg("EAX") & 0xFFFF, pressed & 0xFFFF)

    # --- fuzz: the real draw against the model on many random seasons ------------------------------------------------
    def test_random_seasons_all_32_clubs(self):
        for seed in range(100, 108):
            weeks = 17 if seed % 2 == 0 else 18
            grid, scores = season(seed, weeks=weeks, played_weeks=None if seed % 3 else weeks - 5)
            model = sr.division_conference_records(grid, scores, REAL_DIVISIONS, weeks=weeks)
            shown = {}
            for conference in (0, 1):
                _blocks, clubs = parse(self.game(grid, scores, view=1, conference=conference, weeks=weeks,
                                                 retail_counts=False).draw())
                shown.update({c: (cells[0][0], cells[2][0]) for c, cells in clubs.items()})
            self.assertEqual(sorted(shown), list(range(32)))
            for club in range(32):
                self.assertEqual(shown[club], (sr.format_record(model[club]["div"]), sr.format_record(model[club]["conf"])),
                                 f"seed {seed} club {club} ({ABBR[club]})")


if __name__ == "__main__":
    unittest.main()
