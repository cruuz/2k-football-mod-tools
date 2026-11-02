"""25 more ESPN 25th Anniversary moments: the owner, its Build wiring, the compilers and a bounded native proof.

Retail-free classes check the generated code, the call sites, the allocator budget, the Build wiring and the data
rules. Retail-backed classes skip without the private USA disc folder; they compile situation.iff and team files
from retail bytes, install the owner (alone and in the practice squad union), and run the moment list callbacks,
the select handler with the option's search and loader call, 2D17B0, the import, the match export, the scenario
setup and the won-moment mark under Unicorn (tests/nfl2k5_espn25_more_moments_native.py). The retail-backed
dataset is a synthetic one read back from two retail historic files, so the tests do not depend on the moments
data that ships in data/. EXPERIMENTAL / UNWITNESSED.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools", ROOT / "tests/mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as saved  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_espn25_scenarios as sc  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

KEY = "espn25_more_moments"
RETAIL = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_TARGETS = {"search": None, "load_home": 0x2D17B0, "load_away": 0x2D17B0, "mark_set": None, "venue": 0x77460}
TEAMS = {"falcons_1998": dict(selector="falcons", season=1998, asset_code="01", nickname="Falcons", city="Atlanta",
                              abbreviation="ATL", template="h-01-1998-falcons-1.iff"),
         "vikings_1998": dict(selector="vikings", season=1998, asset_code="15", nickname="Vikings", city="Minnesota",
                              abbreviation="MIN", template="h-15-1998-vikings-0.iff"),
         # also a retail team-season: A YARD TOO SHORT (row 22) plays Titans '99 at home
         "titans_1999": dict(selector="titans", season=1999, asset_code="28", nickname="Titans", city="Tennessee",
                             abbreviation="TEN", template="h-28-1999-titans-0.iff")}
TITANS_ROW = 35                  # the synthetic row (index) whose home side is the new Titans '99
MOMENT = {"id": "the_miss", "title": "THE MISS", "date": "January 17, 1999",
          "history": ("Synthetic test text: the 15-1 Vikings led the NFC title game 27-20 late when their kicker, "
                      "perfect all season, missed from 38 yards with 2:07 left. The Falcons took over at their 29 and "
                      "drove to tie the game and force overtime."),
          "goal": "Drive the Falcons to the tying touchdown in the Metrodome.",
          "stadium_index": 15, "away": "falcons_1998", "home": "vikings_1998", "user_side": "away",
          "possession": "away", "score_now": {"away": 20, "home": 27}, "final_score": {"away": 30, "home": 27},
          "quarter": 4, "clock": "2:07", "down": 1, "distance": 10, "ball_on": "ATL 29",
          "timeouts": {"away": 3, "home": 3}, "weather": "clear", "time_of_day": "afternoon", "temperature": 72,
          "kits": {"away": {"era_year": 1998}, "home": 0}, "stadium": "Hubert H. Humphrey Metrodome"}


def retail_available():
    return (RETAIL / "vc_53450030/0").is_file()


def outer_image():
    from nfl2k5_playbook_position_recode import OuterImage
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(RETAIL)
    return OuterImage(RETAIL)


def rows_from(raw):
    """A team CSV's rows read back from a retail historic file (its 2K names, numbers, positions and ratings)."""
    doc = rr.RosterDocument(raw[32:])
    players = sorted(doc.players, key=lambda p: p.index)
    groups = {}
    for p in players:
        groups.setdefault(p.record.position_name, []).append(p)
    depth = {}
    for pos, group in groups.items():
        if pos in mm.PAIRED:
            order = sorted(group, key=lambda p: (min(p.record.values["depth_rank"], p.record.values["depth_side"]),
                                                 0 if p.record.values["depth_rank"] <= p.record.values["depth_side"] else 1,
                                                 p.index))
        else:
            order = sorted(group, key=lambda p: (p.record.values["depth_rank"], p.record.values["depth_side"], p.index))
        for d, p in enumerate(order, 1):
            depth[p.index] = d
    out = []
    for i, p in enumerate(players):
        v = p.record.values
        stored = v["birth_year_low"] | (v["birth_year_high"] << 3)
        year = 1900 + stored if stored > 54 else 2000 + stored
        row = {"pool": "primary", "index": str(i), "first": p.first, "last": p.last, "position": p.record.position_name,
               "jersey": str(v["jersey"]), "college": "", "depth": str(depth[p.index]), "height": str(v["height"]),
               "weight": str(v["weight_raw"] + 150),
               "birth_date": f"{year:04d}-{max(v['birth_month'], 1):02d}-{max(v['birth_day'], 1):02d}",
               "years_pro": str(v["years_pro"]), "hand": "Left" if v["hand"] == 0 else "Right"}
        row.update({k: str(v[k]) for k in rr.RATING_BYTE_ORDER})
        out.append(row)
    return out


def write_dataset(folder, copies=1):
    """A synthetic dataset in the contract's files: THE MISS from retail files, plus numbered copies of it."""
    folder = Path(folder)
    teams_dir = folder / "teams"
    teams_dir.mkdir(parents=True, exist_ok=True)
    with outer_image() as archive:
        by_id = {e.name_id: e for e in archive.entries}
        for key, team in TEAMS.items():
            entry = by_id[mm.name_id(team["template"])]
            rows = rows_from(archive.read(entry.virtual_offset, entry.size))
            with (teams_dir / f"{key}.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
    (teams_dir / "teams.json").write_text(json.dumps({"schema": 1, "teams": TEAMS}))
    moments = [MOMENT] + [dict(MOMENT, id=f"copy_{n}", title=f"TEST MOMENT {26 + n}") for n in range(1, copies)]
    if copies > TITANS_ROW - 25:
        moments[TITANS_ROW - 25] = dict(moments[TITANS_ROW - 25], home="titans_1999")
    if copies > 5:
        moments[5] = {k: v for k, v in moments[5].items() if k != "stadium"}   # row 31 keeps the stand-in's name
    (folder / "moments.json").write_text(json.dumps({"schema": 1, "moments": moments}))
    return mm.Data.load(folder / "moments.json", teams_dir)


class WiringTests(unittest.TestCase):
    """Retail-free."""

    def test_requests_are_in_every_owner_union_and_the_budget(self):
        self.assertEqual(mm.REQUESTS, ((mm.OWNER, "code", 2560, 16), (mm.OWNER, "data", 16, 16)))
        self.assertLessEqual(len(mm.assembly.CODE), mm.TABLE_OFFSET)
        self.assertLessEqual(mm.NAMES_OFFSET, mm.CODE_SIZE - 512)
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == mm.OWNER], list(mm.REQUESTS))
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(mm.REQUESTS) <= set(REQUESTS))
        self.assertTrue(set(mm.REQUESTS) <= set(space.dormant_union()))
        # fx1: without MyCareer the historical Anniversary coaches are reserved with the first space pass.
        from mod_editor.core import nfl2k5_moment_coaches as mc
        self.assertEqual(tt._selected_space_requests(espn25_more_moments=True), mm.REQUESTS + mc.REQUESTS)
        self.assertEqual(tt._selected_space_requests(espn25_more_moments=True, my_career=True),
                         tt._selected_space_requests(my_career=True) + mm.REQUESTS)
        self.assertEqual(tt._selected_space_requests(), ())

    def test_call_sites_and_relocations(self):
        for label, va, pin, entry, kind in mm.HOOKS:
            raw = bytes.fromhex(pin)
            self.assertIn(entry, mm.assembly.LABELS)
            if kind == "call":
                self.assertEqual(raw[0], 0xE8, label)
                self.assertEqual(va + 5 + struct.unpack("<i", raw[1:])[0], RETAIL_TARGETS[label], label)
        for label, va, before, after in mm.sites(0x1000000, 0x1100000, 50):
            self.assertEqual(len(before), len(after), label)
        names = {symbol for _offset, _kind, symbol, _value in mm.assembly.RELOCATIONS}
        self.assertEqual(names - set(mm.SYMBOLS), {"table", "team_count", "session", "venue_table", "venue_count"})
        self.assertEqual(mm.SYMBOLS["stadium_get"], 0x77460)
        self.assertEqual(mm.SYMBOLS["historic_load"], 0x2D17B0)
        self.assertEqual(mm.SYMBOLS["name_equal"], 0x30CF0)

    def test_count_test_and_announcer_bytes(self):
        sites = {label: (va, before, after) for label, va, before, after in mm.sites(0x1000000, 0x1100000, 50)}
        self.assertEqual(sites["count"][2], bytes.fromhex("b832000000c3"))
        test = sites["mark_test"][2]
        self.assertEqual(test[:3], bytes.fromhex("0fb689"))
        self.assertEqual(test[7:12], bytes.fromhex("83f9207307"))
        self.assertIn(struct.pack("<I", 0x1100000), test)
        self.assertEqual(len(sites["announcer"][2]), 31)

    def test_template_reproduces(self):
        gnu_elf32_as = __import__("importlib").import_module(("tests.mod_editor." if __package__ else "") + "_gnu_elf32_as").gnu_elf32_as  # script and module form (b779-int1)
        if not shutil.which("as") or not gnu_elf32_as():
            self.skipTest("GNU as with ELF32 output is required for template reproduction")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_espn25_more_moments_assemble.py"), "--check"],
                       cwd=ROOT, check=True, capture_output=True, text=True)

    def test_build_option_is_wired_like_the_other_allocator_rows(self):
        from mod_editor.gui import beta62_options as r62_ui
        self.assertIn(KEY, tt.R62_SPACE_KEYS)
        self.assertIn(KEY, tt.R62_RUNTIME_KEYS)
        self.assertIs(mod_build.BuildPlan("", "").espn25_more_moments, False)
        self.assertIn(KEY, saved.FEATURE_KEYS)
        self.assertIn(KEY, r62_ui.KEYS)
        self.assertTrue(mod_build.BuildPlan("", "", espn25_more_moments=True).wants_xbe_patch())
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset[KEY], False, name)
        self.assertIn(KEY, tt._deferred_r62_options({key: None for key in tt.R62_RUNTIME_KEYS}, True))

    def test_the_build_refuses_a_saved_anniversary_plan_before_any_output(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.iso"
            source.write_bytes(b"stand-in bytes; is_disc_image is patched below")
            target = Path(folder) / "copy.iso"
            plan = mod_build.BuildPlan(source=str(source), target=str(target), espn25_more_moments=True,
                                       espn25_plan=str(Path(folder) / "plan.json"))
            with patch.object(mod_build.tt, "is_disc_image", return_value=True):
                with self.assertRaisesRegex(ValueError, "expanded Anniversary collection or a saved ESPN Anniversary plan"):
                    mod_build.build(plan)
            self.assertFalse(target.exists())

    def test_probe_table_fills_the_owned_code_and_needs_no_data_files(self):
        data = mm.probe_data()
        entries = mm.table_entries(data)
        self.assertEqual((len(data.moments), len(entries)), (26, 50))
        self.assertEqual(mm.strings_bytes(data), mm.DISPLAY_OFFSET - mm.NAMES_OFFSET)   # the text allocation
        code = mm.code_for(0x14DA000, 0x14F2000, entries, mm.venues(data))
        self.assertEqual(len(code), mm.CODE_SIZE)
        self.assertEqual(code[mm.DISPLAY_OFFSET - 2:mm.DISPLAY_OFFSET], b"\0\0")
        self.assertEqual({e[1][-6:] for e in entries}, {"-9.iff"})
        last = struct.unpack_from("<I", code, mm.VENUE_OFFSET + 4 * 25)[0] - 0x14DA000
        self.assertEqual(sc.utf16(code, last), "Probe Row Fifty")
        longer = mm.Data([dict(m, stadium=m["stadium"] + "x") for m in data.moments], data.teams, {})
        self.assertGreater(mm.strings_bytes(longer), mm.DISPLAY_OFFSET - mm.NAMES_OFFSET)
        self.assertIs(mm.Probe.OWNER, mm.OWNER)

    def test_missing_data_refuses_by_name(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(mm.MoreMomentsError, "moments data is missing"):
                mm.Data.load(Path(folder) / "moments.json", Path(folder) / "teams")
            (Path(folder) / "teams").mkdir()
            (Path(folder) / "teams/teams.json").write_text(json.dumps({"schema": 1, "teams": TEAMS}))
            (Path(folder) / "moments.json").write_text(json.dumps({"schema": 1, "moments": [MOMENT]}))
            with self.assertRaisesRegex(mm.MoreMomentsError, "roster of falcons_1998 is missing"):
                mm.Data.load(Path(folder) / "moments.json", Path(folder) / "teams")

    def test_texts_and_registry(self):
        for text in (mm.HELP_TEXT, mm.UI_LABEL, mm.BUILD_CAPTION, mm.__doc__ or ""):
            self.assertNotIn("—", text)
        self.assertIn("EXPERIMENTAL / UNWITNESSED", mm.HELP_TEXT)
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        entry = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.espn25.more_moments")
        self.assertEqual(entry["backend"]["module"], "mod_editor/core/nfl2k5_espn25_more_moments.py")
        self.assertEqual(entry["selectors"]["fields"][0]["name"], KEY)
        self.assertEqual(entry["validation_command"], "python3 -m tests.mod_editor.test_nfl2k5_espn25_more_moments")


class DataRuleTests(unittest.TestCase):
    """Retail-free rules of the data contract."""

    def test_display_order_is_chronological_with_stable_physical_identities(self):
        data = mm.Data([MOMENT, dict(MOMENT, id="latest", date="October 16, 2025")], {}, {})
        order = mm.display_order(data)
        self.assertEqual(order.index(25), 21)  # 1999 falls between Super Bowl XXXII and A YARD TOO SHORT
        self.assertEqual(order[-1], 26)
        self.assertEqual(set(order), set(range(27)))
        inventory = mm.display_inventory(data)
        self.assertEqual(inventory[21], dict(display_row=22, physical_row=26,
                                             date="January 17, 1999", id="the_miss"))
        self.assertEqual(inventory[-1]["date"], "October 16, 2025")

    def test_display_mapping_is_bounded_and_permutations_are_required(self):
        data = mm.probe_data()
        code = mm.code_for(0x1400000, 0x1500000, mm.table_entries(data), mm.venues(data),
                           order=mm.display_order(data))
        self.assertEqual(list(code[mm.DISPLAY_MAP_OFFSET:mm.DISPLAY_MAP_OFFSET + 51]),
                         list(mm.display_order(data)))
        self.assertEqual(code[mm.DISPLAY_MAP_OFFSET + 51:], b"\xff" * 13)
        with self.assertRaisesRegex(mm.MoreMomentsError, "permutation"):
            mm.code_for(0x1400000, 0x1500000, [], order=[0, 0])

    def test_ball_on_follows_the_retail_convention(self):
        data = mm.Data([MOMENT], {k: dict(v, team_key=k) for k, v in TEAMS.items()}, {})
        self.assertEqual(data.ball_yards(MOMENT), 21.0)                     # away own 29: +21 (THE MISS)
        self.assertEqual(data.ball_yards(dict(MOMENT, ball_on="MIN 6")), -44.0)  # 6 from the home goal line
        self.assertEqual(data.ball_yards(dict(MOMENT, ball_on="50")), 0.0)
        with self.assertRaises(mm.MoreMomentsError):
            data.ball_yards(dict(MOMENT, ball_on="NYG 20"))

    def test_depth_chains_follow_the_retail_interleave(self):
        self.assertEqual([mm._paired_chain(d, 5) for d in range(1, 6)], [(0, 4), (4, 0), (1, 3), (3, 1), (2, 2)])
        self.assertEqual([mm._paired_chain(d, 2) for d in (1, 2)], [(0, 1), (1, 0)])

    def test_kit_index_by_era(self):
        uniforms = [(0, 0, 0), (1, 1998, 2003), (2, 1993, 1994), (10, 2004, 2004)]
        self.assertEqual(mm.kit_index(uniforms, {"era_year": 1998}), 1)
        self.assertEqual(mm.kit_index(uniforms, {"era_year": 2016}), 0)
        self.assertEqual(mm.kit_index(uniforms, 2), 2)
        with self.assertRaises(mm.MoreMomentsError):
            mm.kit_index(uniforms, 7)

    def test_clock_and_date_rules(self):
        self.assertEqual(mm._clock("2:07"), 127)
        self.assertEqual(mm._clock("15:00"), 900)
        for bad in ("0:00", "15:01", "2:7", "207"):
            with self.assertRaises(mm.MoreMomentsError):
                mm._clock(bad)
        mm._date_ok("February 3, 2008")
        with self.assertRaises(mm.MoreMomentsError):
            mm._date_ok("Feb 3, 2008")


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class RetailCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = write_dataset(cls.tmp.name, copies=25)
        with outer_image() as archive:
            cls.main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            cls.situ = archive.read(archive.entries[22].virtual_offset, archive.entries[22].size)
            by_id = {e.name_id: e for e in archive.entries}
            cls.templates = {k: archive.read(by_id[mm.name_id(t["template"])].virtual_offset,
                                             by_id[mm.name_id(t["template"])].size) for k, t in TEAMS.items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_retail_collection_is_pinned(self):
        self.assertEqual(mm.sha(self.situ), mm.RETAIL_SITU_SHA256)
        self.assertEqual(tuple(sc.u32(self.situ, 32 + sc.RECORDS + i * sc.STRIDE + 0x10)
                               for i in range(25)), mm.RETAIL_STADIUMS)

    def test_situ_recognizes_only_the_catalogs_dated_historical_venues(self):
        data = mm.Data.load()
        collection = mm.compile_situ(self.situ, data, self.main)
        self.assertEqual(mm.situ_rows(collection, data), "applied")
        alternative = mm._historical_stadiums(data)
        repaired = bytearray(collection)
        for row, stadium in alternative.items():
            struct.pack_into("<I", repaired, 32 + sc.RECORDS + row * sc.STRIDE + 0x10, stadium)
        self.assertEqual(mm.situ_rows(bytes(repaired), data), "applied")
        # A valid native index which belongs to neither known profile is refused in either row family.
        for row in (12, 47):
            foreign = bytearray(repaired)
            original = mm.RETAIL_STADIUMS[row] if row < 25 else data.moments[row - 25]["stadium_index"]
            bad = next(value for value in range(82) if value not in (original, alternative[row]))
            struct.pack_into("<I", foreign, 32 + sc.RECORDS + row * sc.STRIDE + 0x10, bad)
            self.assertEqual(mm.situ_rows(bytes(foreign), data), "foreign")
        # A catalog row for a different dated/title moment grants no alternative to synthetic scenarios.
        self.assertNotIn(47, mm._historical_stadiums(self.data))

    def test_situ_keeps_the_retail_rows_and_siblings(self):
        collection = mm.compile_situ(self.situ, self.data, self.main)
        self.assertEqual(sc.u32(collection, 8), 50)
        self.assertEqual(mm.situ_rows(collection, self.data), "applied")
        self.assertEqual(collection[32 + sc.u32(collection, 4):], self.situ[mm.FIRST_CHUNK:])
        old, new = self.situ[32:mm.FIRST_CHUNK], collection[32:]
        for i in range(25):
            for offset in range(0, sc.STRIDE, 4):
                at = sc.RECORDS + i * sc.STRIDE + offset
                if offset in sc.POINTERS:
                    self.assertEqual(sc.utf16(old, sc.rel(old, at)), sc.utf16(new, sc.rel(new, at)))
                else:
                    self.assertEqual(old[at:at + 4], new[at:at + 4])
        record = new[sc.RECORDS + 25 * sc.STRIDE:sc.RECORDS + 26 * sc.STRIDE]
        self.assertEqual(struct.unpack_from("<IIIIII", record, 0x10)[:1], (15,))
        self.assertEqual(struct.unpack_from("<ff", record, 0x40), (21.0, 10.0))
        self.assertEqual(struct.unpack_from("<f", record, 0x4C)[0], 127.0)
        self.assertEqual(struct.unpack_from("<II", record, 0x58), (1, 0))        # Falcons 1998-2003, Vikings current
        self.assertEqual(struct.unpack_from("<IIi", record, 0x60), (0, 1, 72))
        self.assertEqual(mm.situ_rows(self.situ, self.data), "foreign")
        # the historic styles step moves a retail row's kit 0 to a spare style; the rows still read back applied
        spare = bytearray(collection)
        struct.pack_into("<II", spare, 32 + sc.RECORDS + 20 * sc.STRIDE + 0x58, 7, 7)
        self.assertEqual(mm.situ_rows(bytes(spare), self.data), "applied")
        struct.pack_into("<I", spare, 32 + sc.RECORDS + 20 * sc.STRIDE + 0x4C, 0)          # a changed clock is not
        self.assertEqual(mm.situ_rows(bytes(spare), self.data), "foreign")

    def test_team_files_carry_the_rows_and_parse(self):
        colleges = rr.RosterDocument(self.main[32:]).colleges
        for key, filename, entry, selector, identity in mm.table_entries(self.data):
            raw = mm.compile_team(self.templates[key], self.data.teams[key], self.data.rosters[key], colleges, identity)
            season = TEAMS[key]["season"]
            self.assertEqual(filename, f"h-{TEAMS[key]['asset_code']}-{season}-{selector}-9.iff")
            doc = rr.RosterDocument(raw[32:])
            team = doc.teams[0]
            self.assertEqual((team.nickname, team.player_count), (f"{TEAMS[key]['nickname']} '{season % 100:02d}", 53))
            self.assertEqual(struct.unpack_from("<H", raw, 32 + team.offset + 0x118)[0], identity)
            for player, row in zip(sorted(doc.players, key=lambda p: p.index), self.data.rosters[key]):
                v = player.record.values
                self.assertEqual((player.first, player.last, player.record.position_name, v["jersey"]),
                                 (row["first"], row["last"], row["position"], int(row["jersey"])))
                self.assertEqual([v[r] for r in rr.RATING_BYTE_ORDER], [int(row[r]) for r in rr.RATING_BYTE_ORDER])
                stored = v["birth_year_low"] | (v["birth_year_high"] << 3)
                self.assertEqual(stored, (int(row["birth_date"][:4]) + 2004 - season) % 100)
            one_pool = mm._one_pool(raw)
            self.assertEqual(len(one_pool), len(raw))
            self.assertNotIn("OLB", {p.record.position_name for p in rr.RosterDocument(one_pool[32:]).players}
                             - {p.record.position_name for p in rr.RosterDocument(raw[32:]).players
                                if p.record.position_name != "OLB"})

    def test_moment_team_files_carry_the_franchise_style_table(self):
        """The SITU kit index is chosen against the main roster's franchise style pairs; the game resolves that index
        against the moment team file, so the compiled file must carry the same 14 pairs. The template's own pairs
        name a different era (e.g. the 2000 Ravens template says 1997-1999 for style 1, the era kit's label is
        2008-2025). The kit art is keyed by the style index and does not move."""
        colleges = rr.RosterDocument(self.main[32:]).colleges
        for key, filename, entry, selector, identity in mm.table_entries(self.data):
            pairs = mm.franchise_style_pairs(self.main, TEAMS[key]["asset_code"])
            raw = mm.compile_team(self.templates[key], self.data.teams[key], self.data.rosters[key], colleges,
                                  identity, uniform_pairs=pairs)
            doc = rr.RosterDocument(raw[32:])
            team = doc.teams[0]
            self.assertEqual(raw[32 + team.offset + 0x15A:32 + team.offset + 0x15A + 56], pairs, key)

    def test_special_teams_are_chosen_from_the_new_roster(self):
        """The six team-record special-teams bytes (slot indexes) point at this roster's own players."""
        colleges = rr.RosterDocument(self.main[32:]).colleges
        for key, filename, entry, selector, identity in mm.table_entries(self.data):
            rows = list(reversed(self.data.rosters[key]))          # a slot order unlike the template's
            raw = mm.compile_team(self.templates[key], self.data.teams[key], rows, colleges, identity)
            doc = rr.RosterDocument(raw[32:])
            team = doc.teams[0]
            by_offset = {p.offset: p for p in doc.players}
            role = {at: by_offset[team.slots[raw[32 + team.offset + at]]] for at in mm.SPECIAL_TEAMS}
            with self.subTest(team=key):
                self.assertEqual(role[mm.KICKER].record.position_name, "K")
                self.assertIn(role[mm.HOLDER].record.position_name, ("QB", "P"))
                self.assertIn(role[mm.KR1].record.position_name, mm.KR_POSITIONS)
                self.assertIn(role[mm.KR2].record.position_name, mm.KR_POSITIONS)
                self.assertIn(role[mm.PR].record.position_name, mm.PR_POSITIONS)
                self.assertNotEqual(role[mm.KR1].offset, role[mm.KR2].offset)
                order = [q.offset for q in sorted(doc.players, key=lambda q: q.index)]   # row k sits in record k
                kr1 = rows[order.index(role[mm.KR1].offset)]
                backups = [r for r in rows if r["position"] in mm.KR_POSITIONS and not mm._starter(r)]
                self.assertEqual(mm.returner_score(kr1), max(mm.returner_score(r) for r in backups))

    def test_the_last_file_ends_on_a_sector_inside_its_own_wrapper(self):
        files = mm.compile_files(self.main, self.templates, self.data)
        names = list(files)
        self.assertEqual(names, [f for _k, f, _e, _s, _i in mm.table_entries(self.data)])
        for name in names:
            raw = files[name]
            self.assertEqual(struct.unpack_from("<II", raw, 4), (len(raw) - 32, len(raw) - 32), name)
            doc = rr.RosterDocument(raw[32:])
            self.assertEqual((len(doc.players), doc.teams[0].player_count), (53, 53), name)
        self.assertEqual(len(files[names[-1]]) % 2048, 0)
        self.assertNotEqual(len(files[names[0]]) % 2048, 0)
        self.assertEqual(mm.pad_to_sector(files[names[-1]]), files[names[-1]])

    def test_code_table_names_and_entries(self):
        entries = mm.table_entries(self.data)
        code = mm.code_for(0x14DA000, 0x14F2000, entries, mm.venues(self.data))
        self.assertEqual(len(code), mm.CODE_SIZE)
        for k, (_key, _file, entry, selector, _identity) in enumerate(entries):
            row = code[mm.TABLE_OFFSET + 16 * k:mm.TABLE_OFFSET + 16 * (k + 1)]
            self.assertEqual(row[:12], entry[:12])
            pointer = struct.unpack_from("<I", row, 12)[0] - 0x14DA000
            self.assertEqual(sc.utf16(code, pointer), selector)
        cells = struct.unpack_from("<25I", code, mm.VENUE_OFFSET)
        self.assertEqual(sc.utf16(code, cells[0] - 0x14DA000), "Hubert H. Humphrey Metrodome")
        self.assertEqual(cells[5], 0)                                   # no venue text: the stand-in's own name
        self.assertEqual(len({c for c in cells if c}), 1)               # one shared text


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class RetailXbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_espn25_rosters as e
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = write_dataset(cls.tmp.name, copies=25)
        cls.retail = e.read_xbe(RETAIL)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_guards_are_retail(self):
        self.assertEqual(mm.guard_digests(self.retail), {va: mm.GUARD_SHA256[va] for va, _s, _w in mm.GUARDS})

    def test_install_status_replay_and_foreign(self):
        self.assertEqual(mm.status(self.retail, self.data), "retail")
        patched, receipt = mm.apply(self.retail, self.data)
        self.assertEqual((receipt["status"], receipt["rows"], receipt["team_seasons"]), ("applied", 50, 3))
        self.assertEqual(mm.status(patched, self.data), "applied")
        again, receipt = mm.apply(patched, self.data)
        self.assertEqual((again, receipt["status"]), (patched, "already_applied"))
        other = write_dataset(Path(self.tmp.name) / "other", copies=3)
        self.assertEqual(mm.status(patched, other), "foreign")

    def test_probe_owner_installs_and_replays_without_data_files(self):
        patched, receipt = mm.Probe.apply(self.retail)
        self.assertEqual((receipt["status"], receipt["rows"], receipt["team_seasons"]), ("applied", 51, 50))
        self.assertEqual(mm.Probe.status(patched), "applied")
        self.assertEqual(mm.Probe.apply(patched)[0], patched)
        self.assertEqual(mm.status(patched, self.data), "foreign")

    def test_exact_legacy_upgrade_preserves_all_other_owner_allocations(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        newer = write_dataset(Path(self.tmp.name) / "newer", copies=26)
        allocated, _ = space.apply(self.retail, mm.REQUESTS, scaleout=True)
        code, dat = mm.allocations(allocated)
        legacy_body = mm.code_for(code["va"], dat["va"], mm.table_entries(self.data),
                                  mm.venues(self.data), legacy=True)
        installed, _ = space.install_code(allocated, mm.OWNER, legacy_body)
        image, legacy = XbeImage(installed), bytearray(installed)
        for _label, va, _before, after in mm.sites(code["va"], dat["va"], 50, legacy=True):
            at = image.offset(va, len(after))
            legacy[at:at + len(after)] = after
        for section in _sections(legacy):
            legacy[section.header_offset + 36:section.header_offset + 56] = section_digest(legacy, section)
        legacy = bytes(legacy)
        self.assertEqual(mm.legacy_status(legacy, self.data), "applied")
        with self.assertRaises(mm.MoreMomentsError):
            mm.apply(legacy, newer)  # no silent reconfiguration of a differently authored owner
        patched, receipt = mm.apply(legacy, newer, legacy_data=self.data)
        self.assertEqual((receipt["status"], receipt["rows"]), ("upgraded", 51))
        self.assertEqual((mm.status(patched, newer), mm.row_hooks_status(patched, newer)), ("applied", "applied"))
        self.assertEqual(mm.apply(patched, newer)[0], patched)
        self.assertEqual(space.layout(legacy)["allocations"], space.layout(patched)["allocations"])
        for allocation in space.layout(legacy)["allocations"]:
            if allocation["owner"] not in (mm.OWNER, "nfl2k5_xbe_space_directory"):
                at, size = allocation["raw"], allocation["size"]
                self.assertEqual(legacy[at:at + size], patched[at:at + size])
        mixed = bytearray(legacy)
        mixed[image.offset(mm.COUNT_VA)] ^= 1
        for section in _sections(mixed):
            mixed[section.header_offset + 36:section.header_offset + 56] = section_digest(mixed, section)
        self.assertEqual(mm.legacy_status(bytes(mixed), self.data), "foreign")
        with self.assertRaises(mm.MoreMomentsError):
            mm.apply(bytes(mixed), newer, legacy_data=self.data)

    def test_row_hooks_are_the_four_record_reads_of_the_list_draw_callbacks(self):
        """Beta 77: retail has `call 2CFD40` at each ROW_HOOKS site; the install points all four at the display helper,
        which maps the list row and jumps to 2CFD40. Nothing else in 20C710..20C850 changes."""
        image = XbeImage(self.retail)
        self.assertEqual([va for _label, va, _retail in mm.ROW_HOOKS], [0x20C71E, 0x20C740, 0x20C79B, 0x20C813])
        for _label, va, retail in mm.ROW_HOOKS:
            raw = image.read(va, 5)
            self.assertEqual(raw.hex(), retail)
            self.assertEqual(raw[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack_from("<i", raw, 1)[0], 0x2CFD40)
        patched, receipt = mm.apply(self.retail, self.data)
        code, _dat = mm.allocations(patched)
        helper = code["va"] + mm.DISPLAY_OFFSET + mm.assembly.DISPLAY_LABELS[mm.ROW_HELPER]
        after = XbeImage(patched)
        for _label, va, _retail in mm.ROW_HOOKS:
            raw = after.read(va, 5)
            self.assertEqual((raw[0], va + 5 + struct.unpack_from("<i", raw, 1)[0]), (0xE8, helper))
        self.assertEqual({e["label"] for e in receipt["edits"]} & mm.ROW_LABELS, set(mm.ROW_LABELS))
        changed = [at for at in range(0x20C710, 0x20C850) if after.read(at, 1) != image.read(at, 1)]
        operands = {va + k for _l, va, _r in mm.ROW_HOOKS for k in range(1, 5)}     # the rel32 of each call
        self.assertTrue(changed and set(changed) <= operands, "only the four call operands in the callbacks change")
        self.assertEqual(mm.row_hooks_status(patched, self.data), "applied")
        self.assertEqual(mm.row_hooks_status(self.retail, self.data), "retail")

    def test_a_beta_765_install_is_completed_in_place_and_nothing_else_moves(self):
        """The shipped v0.5 executable has the owner and the three older display hooks but not the row hooks: it still
        reads applied, and apply() writes exactly the four call sites and the one section digest."""
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        current, _ = mm.apply(self.retail, self.data)
        code, dat = mm.allocations(current)
        image, previous = XbeImage(current), bytearray(current)
        for label, va, before, _after in mm.sites(code["va"], dat["va"], mm.RETAIL_COUNT + len(self.data.moments)):
            if label in mm.ROW_LABELS:
                previous[image.offset(va, len(before)):image.offset(va, len(before)) + len(before)] = before
        for section in _sections(previous):
            previous[section.header_offset + 36:section.header_offset + 56] = section_digest(previous, section)
        previous = bytes(previous)
        self.assertNotEqual(previous, current)
        self.assertEqual((mm.status(previous, self.data), mm.row_hooks_status(previous, self.data)),
                         ("applied", "previous"))
        upgraded, receipt = mm.apply(previous, self.data)
        self.assertEqual((receipt["status"], receipt["rows_completed"]), ("upgraded", True))
        self.assertEqual(upgraded, current)
        runs = [i for i, (a, b) in enumerate(zip(previous, upgraded)) if a != b]
        self.assertEqual(len(runs), receipt["changed_bytes"])
        self.assertLessEqual(len(runs), 16 + 20)          # the rel32 of four calls, and the .text section's SHA-1
        again, replay = mm.apply(upgraded, self.data)
        self.assertEqual((again, replay["status"]), (upgraded, "already_applied"))
        self.assertEqual(mm.row_hooks_status(upgraded, self.data), "applied")

    def test_a_changed_row_hook_or_draw_callback_is_foreign(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        patched, _ = mm.apply(self.retail, self.data)
        image = XbeImage(patched)
        for va in [va + 2 for _l, va, _r in mm.ROW_HOOKS] + [0x20C712, 0x20C7D0, 0x20C84F]:
            bad = bytearray(patched)
            bad[image.offset(va, 1)] ^= 1
            for section in _sections(bad):
                bad[section.header_offset + 36:section.header_offset + 56] = section_digest(bad, section)
            with self.subTest(va=hex(va)):
                self.assertEqual(mm.status(bytes(bad), self.data), "foreign")
                with self.assertRaises(mm.MoreMomentsError):
                    mm.apply(bytes(bad), self.data)
        mixed = bytearray(patched)
        first = mm.ROW_HOOKS[0]
        mixed[image.offset(first[1], 5):image.offset(first[1], 5) + 5] = bytes.fromhex(first[2])
        for section in _sections(mixed):
            mixed[section.header_offset + 36:section.header_offset + 56] = section_digest(mixed, section)
        self.assertEqual(mm.status(bytes(mixed), self.data), "foreign")       # one of four still retail

    def test_the_venue_callback_is_the_details_screens_alone(self):
        """2C5A70 is registered once, in the Anniversary details screen's text callbacks (the group that also
        holds the title, date, history, goal and score callbacks, all reading the moment record), so the venue
        text reaches nothing but that line."""
        image = XbeImage(self.retail)
        hits = []
        at = self.retail.find(struct.pack("<I", 0x2C5A70))
        while at >= 0:
            hits.append(image.va_for_offset(at))
            at = self.retail.find(struct.pack("<I", 0x2C5A70), at + 1)
        self.assertEqual(hits, [0xACFD40])
        group = struct.unpack_from("<I", image.read(0xACFD38, 4))[0]
        neighbours = {struct.unpack_from("<I", image.read(0xACFCF8 + 16 * i + 8, 4))[0] for i in range(16)}
        self.assertEqual(struct.unpack_from("<I", image.read(0xACFCF8, 4))[0], group)
        self.assertTrue({0x2C5920, 0x2C59E0, 0x2C5A10, 0x2C5A40, 0x2C5AA0, 0x2C5A70} <= neighbours)

    def test_union_with_the_practice_squad_and_historic_teams(self):
        from mod_editor.core import nfl2k5_historic_teams_quick_game as h1
        from mod_editor.core import nfl2k5_practice_squad as ps
        original = mm.Data.load
        mm.Data.load = classmethod(lambda cls, *a, **k: self.data)
        try:
            patched, receipt = tt._apply_all(self.retail, None, False, scheme_labels=True, practice_squad=True,
                                             franchise_practice=True, depth_locks=True, xbe_space=True,
                                             historic_teams_quick_game=True, espn25_more_moments=True)
        finally:
            mm.Data.load = original
        self.assertEqual((mm.status(patched, self.data), h1.status(patched), ps.status(patched)),
                         ("applied", "applied", "applied"))
        self.assertEqual(receipt["espn25_more_moments_patch"]["rows"], 50)


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class NativeMomentsTests(unittest.TestCase):
    """The game's own code: list callbacks, selection, imports, match, setup and marks."""

    @classmethod
    def setUpClass(cls):
        try:
            from nfl2k5_espn25_more_moments_native import FastMomentsCPU, MomentsCPU, evidence
        except ImportError as exc:
            raise unittest.SkipTest(f"Unicorn unavailable: {exc}")
        from mod_editor.core import nfl2k5_espn25_rosters as e
        from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: F401
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = write_dataset(cls.tmp.name, copies=26)
        with outer_image() as archive:
            main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            situ = archive.read(archive.entries[22].virtual_offset, archive.entries[22].size)
            by_id = {x.name_id: x for x in archive.entries}
            templates = {k: archive.read(by_id[mm.name_id(t["template"])].virtual_offset,
                                         by_id[mm.name_id(t["template"])].size) for k, t in TEAMS.items()}
        collection = mm.compile_situ(situ, cls.data, main)
        cls.files = files = mm.compile_files(main, templates, cls.data)
        base, _ = tt._apply_all(e.read_xbe(RETAIL), None, catch_slider=False, scheme_labels=True,
                                practice_squad=True, franchise_practice=True, depth_locks=True)
        payload = base
        original = mm.Data.load
        mm.Data.load = classmethod(lambda c, *a, **k: cls.data)
        try:
            payload, _ = tt._apply_all(e.read_xbe(RETAIL), None, False, scheme_labels=True, practice_squad=True,
                                       franchise_practice=True, depth_locks=True, xbe_space=True,
                                       espn25_more_moments=True)
        finally:
            mm.Data.load = original
        cls.session = next(a for a in space.layout(payload)["allocations"]
                           if a["owner"] == mm.OWNER and a["kind"] == "data")["va"]
        resources, context, ids = evidence(RETAIL)
        cls.cpu = MomentsCPU(payload, resources, context, ids,
                             situ_chunk=collection[:32 + sc.u32(collection, 4)], extra_files=files)
        # the same executable and data with hooks only at the named boundaries: 51 clicks in seconds
        cls.fast = FastMomentsCPU(payload, resources, context, ids,
                                  situ_chunk=collection[:32 + sc.u32(collection, 4)], extra_files=files)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_fifty_one_rows_and_captions(self):
        cpu = self.cpu
        self.assertEqual(cpu.run(0x20C340), 51)
        self.assertEqual(cpu.caption(0), "THE ICE BOWL | December 31, 1967")
        self.assertEqual(cpu.caption(mm.display_order(self.data).index(25)), "THE MISS | January 17, 1999")
        self.assertEqual(cpu.caption(mm.display_order(self.data).index(49)), "TEST MOMENT 50 | January 17, 1999")

    def test_every_list_row_draws_the_moment_a_click_opens(self):
        """Beta 77 (Noah 10/7: "click one and another wrong one opens"). The list draws each row with its own
        callbacks (title and date 20C800, mini helmets 20C710 and 20C790). For all 51 rows, run those callbacks
        natively and require that they read the SITU record the select handler opens: the display row's physical
        row, with the title, date and both helmet kits taken from that record."""
        cpu, order = self.fast, mm.display_order(self.data)
        self.assertEqual(sorted(order), list(range(51)))
        self.assertNotEqual(list(order), list(range(51)), "the test needs a real permutation")
        for display, physical in enumerate(order):
            with self.subTest(display_row=display + 1, physical_row=physical + 1):
                expected = cpu.run(0x2CFD40, ecx=physical)
                title, date = cpu.text(cpu.r(expected)), cpu.text(cpu.r(expected + 0xC))
                drawn = {kind: cpu.draw_row(kind, display) for kind in ("title", "home_helmet", "away_helmet")}
                self.assertEqual(drawn["title"]["asked"], [physical])
                self.assertEqual(drawn["title"]["records"], [expected])
                self.assertEqual(drawn["home_helmet"]["asked"], [physical, physical])
                self.assertEqual(drawn["home_helmet"]["records"], [expected, expected])
                self.assertEqual(drawn["away_helmet"]["asked"], [physical])
                self.assertEqual(drawn["away_helmet"]["records"], [expected])
                self.assertEqual((drawn["title"]["title"], drawn["title"]["date"]), (title, date))
                self.assertEqual(drawn["home_helmet"]["kit"], cpu.r(expected + 0x5C))
                self.assertEqual(drawn["away_helmet"]["kit"], cpu.r(expected + 0x58))
                cpu.events.clear()
                cpu.select(display)
                self.assertEqual(cpu.r(0xBF1858), physical)
                self.assertEqual(cpu.run(0x20C6F0), expected)          # what the details screen reads
                self.assertEqual(cpu.text(cpu.r(cpu.run(0x20C6F0))), title)
                cpu.run(0x20C3C0)

    def test_new_moments_load_their_own_files_and_set_up(self):
        cpu = self.cpu
        for index in (25, "exit", 0, "exit", 49, "exit", 14, "exit", 32):
            if index == "exit":
                cpu.run(0x20C3C0)
                continue
            before, loads = len(cpu.imports), len(cpu.extra_loads)
            cpu.select(mm.display_order(self.data).index(index))
            selected, match = cpu.selected(), cpu.match()
            with self.subTest(moment=index):
                self.assertEqual([i["result"] for i in cpu.imports[before:]], [1, 1])
                self.assertEqual((selected["away"]["active"], selected["home"]["active"]), (53, 53))
                self.assertEqual(match["export_players"], 106)
                self.assertTrue(all(side["kit_exists"] for side in match["sides"].values()))
                if index in (25, 49, 32):
                    self.assertEqual((selected["away"]["name"], selected["home"]["name"]), ("Falcons '98", "Vikings '98"))
                    self.assertEqual(sorted(cpu.extra_loads[loads:]),
                                     ["h-01-1998-falcons-9.iff", "h-15-1998-vikings-9.iff"])
                    self.assertEqual(match["scenario"], {"home_score": 27, "away_score": 20, "clock_seconds": 127.0,
                                                         "quarter": 4})
                    self.assertEqual((match["sides"]["away"]["kit"], match["sides"]["home"]["kit"]),
                                     ("01a1.iff", "15h0.iff"))
                else:
                    self.assertEqual(cpu.extra_loads[loads:], [])
        self.assertTrue(all(r["pointers_after"] == 0 for r in cpu.releases))

    def test_import_completes_every_record_byte_over_a_used_spare_record(self):
        """b780 (b3-moments, Ju3tin 10/31 and 11/01): the importer takes the first spare record (flags & 5 == 1) and
        its clone never writes +0x0D..+0x0F or the +0x52 word (the beta 76.3 tail copied only the star bit), so a moment
        player kept the hair style, depth locks, ability flags and tier of whoever used that record before. Fill every
        spare record with such bytes (the star bit too), open a new moment (Falcons '98 at Vikings '98) through the
        game's own select handler, 2D17B0 and C1030, and require each imported player to carry exactly his team file's
        bytes."""
        cpu = self.cpu
        root = cpu.r(0xB72918)
        count, array = cpu.r(root), cpu.r(root + 4)
        spare = [array + 84 * i for i in range(count) if cpu.read(array + 84 * i + 8, 1)[0] & 5 == 1]
        self.assertGreaterEqual(len(spare), 106)
        saved = {at: cpu.read(at, 84) for at in spare}
        stale = (0x07, 0x5A, 0xA5, 0xDFE3)                    # hair 7, two unknown bytes, X-Factor + every flag
        try:
            for at in spare:
                cpu.write(at + 0x0D, bytes(stale[:3]))
                cpu.write(at + 0x52, struct.pack("<H", stale[3]))
            cpu.select(mm.display_order(self.data).index(25))
            authored = {}
            for name in ("h-01-1998-falcons-9.iff", "h-15-1998-vikings-9.iff"):
                doc = rr.RosterDocument(self.files[name][32:])
                for p in doc.players:
                    raw = self.files[name][32 + p.offset:32 + p.offset + 84]
                    authored[(name[2:4], p.first, p.last, p.record.values["jersey"])] = raw
            checked = 0
            for side, info in cpu.selected().items():
                code = info["code"]
                for k in range(info["active"]):
                    pointer = cpu.r(info["team"] + 4 * k)
                    person = cpu.person(pointer)
                    raw = cpu.read(pointer, 84)
                    src = authored[(code, person["first"], person["last"], person["jersey"])]
                    with self.subTest(side=side, player=f"{person['first']} {person['last']}"):
                        self.assertIn(pointer, saved)              # it did land in a used spare record
                        self.assertEqual(raw[0x0C:0x10], src[0x0C:0x10])
                        self.assertEqual(raw[0x52:0x54], src[0x52:0x54])
                    checked += 1
            self.assertEqual(checked, 106)
            cpu.run(0x20C3C0)
        finally:
            for at, raw in saved.items():
                cpu.write(at, raw)

    def test_retail_rows_keep_the_retail_search(self):
        """A retail row whose team-season is also a new one (A YARD TOO SHORT, Titans '99 at home) loads the retail
        file; the new row with that team-season loads the new file."""
        cpu = self.cpu
        before, events = len(cpu.extra_loads), len(cpu.events)
        cpu.select(mm.display_order(self.data).index(21))
        self.assertEqual(cpu.extra_loads[before:], [])
        self.assertIn("h-28-1999-titans-0.iff", [e["filename"] for e in cpu.events[events:]])
        cpu.run(0x20C3C0)
        before = len(cpu.extra_loads)
        cpu.select(mm.display_order(self.data).index(TITANS_ROW))
        self.assertEqual(sorted(cpu.extra_loads[before:]), ["h-01-1998-falcons-9.iff", "h-28-1999-titans-9.iff"])
        cpu.run(0x20C3C0)

    def test_details_venue_is_display_only(self):
        """2C5A70 (the details screen's venue text) shows a new row's venue; the stadium the game uses is the
        stand-in record, whose own name and code stay retail."""
        cpu = self.cpu
        out = 0x2500000

        def venue(row):
            cpu.select(mm.display_order(self.data).index(row))
            cpu.w(out, 0)
            cpu.run(0x2C5A70, args=(out, 0, 0))
            record = cpu.run(0x77460)                    # the selected stadium, as every other reader sees it
            shown = cpu.text(out)
            name, code = cpu.text(cpu.r(record)), cpu.text(cpu.r(record + 0x0C))
            cpu.run(0x20C3C0)
            return shown, name, code

        self.assertEqual(venue(25), ("Hubert H. Humphrey Metrodome", "H. H. H. Metrodome", "s15"))
        self.assertEqual(venue(30), ("H. H. H. Metrodome", "H. H. H. Metrodome", "s15"))     # no venue text
        self.assertEqual(venue(14), ("Tampa Bay Stadium", "Tampa Bay Stadium", "s27"))       # WIDE RIGHT, retail

    def test_selected_physical_identity_and_returned_display_selection(self):
        cpu = self.cpu
        display = mm.display_order(self.data).index(25)
        cpu.select(display)
        self.assertEqual(cpu.r(0xBF1858), 25)
        self.assertEqual(cpu.r(self.session + 4), display)
        out = []
        cpu.stubs[0x1707C0] = lambda: (out.append(cpu.reg("edx")), cpu.ret(1))
        cpu.stubs[0xF31B0] = lambda: cpu.ret(0)
        try:
            cpu.run(0x20C2F0)
        finally:
            cpu.stubs.pop(0x1707C0)
            cpu.stubs.pop(0xF31B0)
            cpu.run(0x20C3C0)
        self.assertEqual(out, [display])

    def test_row_fifty_one_selects_its_own_situation_and_session_mark(self):
        cpu = self.cpu
        display = mm.display_order(self.data).index(50)
        self.assertEqual(cpu.caption(display), "TEST MOMENT 51 | January 17, 1999")
        before = len(cpu.extra_loads)
        cpu.select(display)
        self.assertEqual(cpu.r(0xBF1858), 50)
        self.assertEqual(sorted(cpu.extra_loads[before:]),
                         ["h-01-1998-falcons-9.iff", "h-15-1998-vikings-9.iff"])
        self.assertEqual(cpu.match()["scenario"], {"home_score": 27, "away_score": 20,
                                                   "clock_seconds": 127.0, "quarter": 4})
        cpu.w(0xBF18CC, 0)
        cpu.w(self.session, 0)
        cpu.win(50)
        self.assertEqual((cpu.r(0xBF18CC), cpu.r(self.session)), (0, 1 << 18))
        self.assertEqual([i for i in range(51) if cpu.completed(i)], [display])
        cpu.run(0x20C3C0)

    def test_marks_for_rows_33_to_50_stay_in_the_session(self):
        cpu = self.cpu
        cpu.w(0xBF18CC, 0)
        cpu.w(self.session, 0)
        cpu.win(40)
        self.assertEqual((cpu.r(0xBF18CC), cpu.r(self.session)), (0, 1 << 8))
        self.assertEqual([i for i in range(50) if cpu.completed(i)], [mm.display_order(self.data).index(40)])
        for row in (0, 28, 49):
            cpu.win(row)
        self.assertEqual((cpu.r(0xBF18CC), cpu.r(self.session)), ((1 << 0) | (1 << 28), (1 << 8) | (1 << 17)))
        self.assertEqual([i for i in range(50) if cpu.completed(i)], sorted(mm.display_order(self.data).index(k) for k in (0, 28, 40, 49)))


class AnniversaryQcTests(unittest.TestCase):
    """Beta 76.3 (Noah 10/2: post-play faces "totally wrong and random", "you made Chris hogan black", no star icons).
    Retail-free: the shipped appearance data and the star copy's semantics (Unicorn)."""

    def test_the_shipped_looks_follow_the_rosters_row_for_row(self):
        data = mm.Data.load()
        self.assertEqual(set(data.appearance), set(data.rosters))
        for key, rows in data.rosters.items():
            self.assertEqual([look["name"] for look in data.appearance[key]],
                             [f"{row['first']} {row['last']}" for row in rows], key)
        looks = {(key, look["name"]): look for key, team in data.appearance.items() for look in team}
        self.assertEqual(looks[("patriots_2016", "Chris Hogan")]["tone"], 0)
        brady = looks[("patriots_2007", "Tom Brady")]
        self.assertEqual((brady["tone"], brady["retail"]["photo"]), (0, 2712))
        # The new 2025 teams use explicitly unresearched fallback looks where no current roster art exists.
        # Retain the original appearance audit's bound without manufacturing tones for those new players.
        unknown = [name for (key, name), look in looks.items()
                   if look["tone"] is None and key not in ("steelers_2025", "bengals_2025")]
        self.assertLessEqual(len(unknown), 20)
        new_unknown = [look for (key, name), look in looks.items()
                       if look["tone"] is None and key in ("steelers_2025", "bengals_2025")]
        self.assertEqual(len(new_unknown), 32)
        self.assertTrue(all(look["source"] == "none; template generic appearance unverified"
                            for look in new_unknown))

    def test_a_look_that_names_someone_else_is_refused(self):
        data = mm.Data.load()
        doc = json.loads(mm.APPEARANCE_JSON.read_text(encoding="utf-8"))
        doc["teams"]["patriots_2016"][0]["name"] = "Somebody Else"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "appearance.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(mm.MoreMomentsError):
                mm._load_appearance(path, data.rosters)
            self.assertIsNone(mm._load_appearance(Path(folder) / "absent.json", data.rosters))

    def test_import_tail_completes_the_record_and_replays_the_retail_tail(self):
        """b780 (b3-moments): the C1030 site copies the dword +0x0C..+0x0F of the file record and the owned tail copies
        the whole +0x52 word, so an imported player keeps none of the spare record's earlier hair style, depth locks,
        ability flags, ability tier, star tag or Guardian flag. Run under Unicorn from the site to the resume point."""
        try:
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
            from unicorn import x86_const as x86
        except ImportError:
            self.skipTest("unicorn required")
        code_va = 0x14DA000
        stub = mm.star_code(code_va + mm.STAR_OFFSET)
        site = mm.import_site(code_va)
        self.assertEqual(len(stub), mm.TABLE_OFFSET - mm.STAR_OFFSET)
        self.assertEqual(len(site), len(bytes.fromhex(mm.STAR_RETAIL)))
        jump = stub.index(b"\xe9")
        resume = struct.unpack_from("<i", stub, jump + 1)[0] + code_va + mm.STAR_OFFSET + jump + 5
        self.assertEqual(resume, mm.STAR_RESUME)
        self.assertEqual(stub[jump + 5:], b"\xcc" * (len(stub) - jump - 5))
        for src_word in (0x0000, 0x0100, 0xDFE3, 0x2000, 0xC01F):
            for dst_word in (0x0000, 0xFFFF, 0xDDC3, 0x5A5A):
                uc = Uc(UC_ARCH_X86, UC_MODE_32)
                uc.mem_map(0xC1000, 0x1000)
                uc.mem_map(0x14DA000, 0x1000)
                uc.mem_map(0x200000, 0x10000)
                uc.mem_write(mm.STAR_VA, site)
                uc.mem_write(code_va + mm.STAR_OFFSET, stub)
                src, dst, esi, stack = 0x200000, 0x201000, 0x202000, 0x208000
                record = bytearray(range(0x54))
                struct.pack_into("<H", record, 0x52, src_word)
                target = bytearray(b"\xee" * 0x54)
                struct.pack_into("<H", target, 0x52, dst_word)
                target[0x0C] = record[0x0C]                      # the clone has written +0x0C before the site
                uc.mem_write(src, bytes(record))
                uc.mem_write(dst, bytes(target))
                uc.mem_write(esi + 0x11C, bytes([0x35]))
                uc.mem_write(stack + 0x10, struct.pack("<I", 0x1234))
                regs = {x86.UC_X86_REG_EBP: src, x86.UC_X86_REG_EDI: dst, x86.UC_X86_REG_ESI: esi,
                        x86.UC_X86_REG_ESP: stack, x86.UC_X86_REG_EBX: 0x11111111, x86.UC_X86_REG_EDX: 0x22222222,
                        x86.UC_X86_REG_EAX: 0xDEADBEEF, x86.UC_X86_REG_ECX: 0xCAFEBABE}
                for reg, value in regs.items():
                    uc.reg_write(reg, value)
                uc.emu_start(mm.STAR_VA, mm.STAR_RESUME)
                expected = bytearray(target)
                expected[0x0C:0x10] = record[0x0C:0x10]
                expected[0x52:0x54] = record[0x52:0x54]
                with self.subTest(src=hex(src_word), dst=hex(dst_word)):
                    self.assertEqual(uc.reg_read(x86.UC_X86_REG_EIP), mm.STAR_RESUME)
                    self.assertEqual(bytes(uc.mem_read(dst, 0x54)), bytes(expected))
                    self.assertEqual(bytes(uc.mem_read(src, 0x54)), bytes(record))
                    self.assertEqual(uc.reg_read(x86.UC_X86_REG_EAX), 0x1234)        # mov eax,[esp+0x10]
                    self.assertEqual(uc.reg_read(x86.UC_X86_REG_ECX), 0x35)          # movzx ecx,byte [esi+0x11c]
                    for reg in (x86.UC_X86_REG_EBP, x86.UC_X86_REG_EDI, x86.UC_X86_REG_ESI, x86.UC_X86_REG_ESP,
                                x86.UC_X86_REG_EBX, x86.UC_X86_REG_EDX):
                        self.assertEqual(uc.reg_read(reg), regs[reg])

    def test_season_codes_follow_the_moves(self):
        cases = {("23", 2021): "LAR", ("23", 1999): "STL", ("23", 1951): "LA", ("20", 2001): "OAK", ("20", 1983): "LA",
                 ("20", 2020): "LV", ("20", 1976): "OAK", ("24", 2006): "SD", ("24", 2017): "LAC", ("11", 2009): "IND",
                 ("11", 1970): "BAL", ("00", 2008): "ARI", ("00", 1975): "STL", ("00", 1990): "PHO",
                 ("28", 1999): "TEN", ("28", 1988): "HOU", ("16", 2016): "NE", ("14", 2006): "SEA"}
        base = {"23": "STL", "20": "OAK", "24": "SD", "11": "IND", "00": "ARZ", "28": "TEN", "16": "NE", "14": "SEA"}
        for (code, season), want in cases.items():
            with self.subTest(code=code, season=season):
                team = {"asset_code": code, "season": season, "abbreviation": base[code]}
                self.assertEqual(mm.display_abbreviation(team), want)
                self.assertLessEqual(len(want), mm.SLOT_TEXT_CAPACITY[mm.TEAM_CITY_ABBREVIATION])

    def test_previous_star_only_tail_still_moves_one_bit(self):
        """The beta 76.3 .. beta 79 body (kept for recognition) copies only the star bit."""
        try:
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
            from unicorn import x86_const as x86
        except ImportError:
            self.skipTest("unicorn required")
        code_va = 0x14DA000
        stub = mm.previous_star_code(code_va + mm.STAR_OFFSET)
        self.assertEqual(len(stub), mm.TABLE_OFFSET - mm.STAR_OFFSET)
        resume = struct.unpack_from("<i", stub, len(stub) - 4)[0] + code_va + mm.STAR_OFFSET + len(stub)
        self.assertEqual(resume, mm.STAR_RESUME)
        site = mm.previous_import_site(code_va)
        self.assertEqual(site[:5], b"\xe9" + struct.pack("<i", code_va + mm.STAR_OFFSET - mm.STAR_VA - 5))
        self.assertEqual(site[5:], b"\xcc" * 6)
        for src_tag in (0, 1, 0x5F, 0xA0):
            for dst_tag in (0x00, 0x01, 0xFE, 0xFF):
                uc = Uc(UC_ARCH_X86, UC_MODE_32)
                uc.mem_map(0x14DA000, 0x1000)
                uc.mem_map(0x200000, 0x10000)
                uc.mem_write(code_va + mm.STAR_OFFSET, stub)
                src, dst, esi, stack = 0x200000, 0x201000, 0x202000, 0x208000
                uc.mem_write(src, bytes(range(0x53)) + bytes([src_tag]))
                uc.mem_write(dst, bytes(0x53) + bytes([dst_tag]))
                uc.mem_write(esi + 0x11C, bytes([0x35]))
                uc.mem_write(stack + 0x10, struct.pack("<I", 0x1234))
                for reg, value in {x86.UC_X86_REG_EBP: src, x86.UC_X86_REG_EDI: dst, x86.UC_X86_REG_ESI: esi,
                                   x86.UC_X86_REG_ESP: stack}.items():
                    uc.reg_write(reg, value)
                uc.emu_start(code_va + mm.STAR_OFFSET, mm.STAR_RESUME)
                with self.subTest(src=src_tag, dst=dst_tag):
                    self.assertEqual(bytes(uc.mem_read(dst, 0x54)), bytes(0x53) + bytes([(dst_tag & 0xFE) | (src_tag & 1)]))

    def test_the_star_copy_sits_in_the_owned_code_before_the_table(self):
        entries = mm.table_entries(mm.Data.load())
        code = mm.code_for(0x14DA000, 0x14F2000, entries, mm.venues(mm.Data.load()))
        self.assertEqual(code[mm.STAR_OFFSET:mm.TABLE_OFFSET], mm.star_code(0x14DA000 + mm.STAR_OFFSET))
        site = [s for s in mm.sites(0x14DA000, 0x14F2000, 50) if s[0] == "star_copy"]
        self.assertEqual(len(site), 1)
        _label, va, before, after = site[0]
        self.assertEqual((va, before.hex()), (mm.STAR_VA, mm.STAR_RETAIL))
        self.assertEqual(after[:6], mm.IMPORT_SITE_HEAD)
        self.assertEqual(after[6:], b"\xe9" + struct.pack("<i", 0x14DA000 + mm.STAR_OFFSET - mm.STAR_VA - 11))


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class AnniversaryQcRetailTests(unittest.TestCase):
    """Retail-backed: the C1030 site, an earlier install without the star copy, own-or-no-photo portraits."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_espn25_rosters as e
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = write_dataset(cls.tmp.name, copies=25)
        cls.retail = e.read_xbe(RETAIL)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_branch_in_c1030_lands_inside_the_replaced_tail(self):
        import capstone
        image = XbeImage(self.retail)
        start, end = 0xC1030, 0xC1E2E
        self.assertEqual(image.read(mm.STAR_VA, 11).hex(), mm.STAR_RETAIL)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        targets = set()
        for ins in md.disasm(image.read(start, end - start), start):
            if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
                try:
                    targets.add(int(ins.op_str, 16))
                except ValueError:
                    pass
        self.assertIn(mm.STAR_VA, targets)                      # the jne over the contract fix lands on the site
        self.assertFalse(targets & set(range(mm.STAR_VA + 1, mm.STAR_VA + 11)))

    def test_an_install_without_the_star_copy_still_reads_applied(self):
        """Beta 76.0-76.2 installed the owned code with int3 where the star copy now sits and left C1030 retail."""
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        patched, _ = mm.apply(self.retail, self.data)
        allocated, _ = space.apply(self.retail, mm.REQUESTS)
        code, dat = mm.allocations(allocated)
        body = mm.code_for(code["va"], dat["va"], mm.table_entries(self.data), mm.venues(self.data), order=mm.display_order(self.data))
        body = body[:mm.STAR_OFFSET] + b"\xcc" * (mm.TABLE_OFFSET - mm.STAR_OFFSET) + body[mm.TABLE_OFFSET:]
        installed, _ = space.install_code(allocated, mm.OWNER, body)
        image = XbeImage(installed)
        earlier = bytearray(installed)
        for label, va, before, after in mm.sites(code["va"], dat["va"], mm.RETAIL_COUNT + len(self.data.moments)):
            if label != "star_copy":
                at = image.offset(va, len(before))
                earlier[at:at + len(before)] = after
        for s in _sections(earlier):
            earlier[s.header_offset + 36:s.header_offset + 56] = section_digest(earlier, s)
        earlier = bytes(earlier)
        site = image.offset(mm.STAR_VA, 11)
        self.assertEqual(mm.status(earlier, self.data), "applied")
        self.assertEqual(mm.apply(earlier, self.data)[1]["status"], "already_applied")
        half = bytearray(earlier)                               # the site without its code is mixed, not applied
        half[site:site + 11] = patched[site:site + 11]
        self.assertEqual(mm.status(bytes(half), self.data), "foreign")

    def test_a_star_only_install_reads_applied_and_upgrades(self):
        """b780: a disc built by beta 76.3 .. beta 79 carries the star-only import tail and its plain jump. It reads
        applied; apply() completes the import in place (the 28-byte tail and the 11-byte site, nothing else moves) and
        a replay of the result changes nothing. Either half of the new tail with the other half of the old is foreign."""
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        current, _ = mm.apply(self.retail, self.data)
        self.assertEqual(mm.import_status(current, self.data), "current")
        code, _dat = mm.allocations(current)
        image = XbeImage(current)
        tail_at = code["raw"] + mm.STAR_OFFSET
        tail_size = mm.TABLE_OFFSET - mm.STAR_OFFSET
        site_at = image.offset(mm.STAR_VA, 11)

        def build(tail, site):
            out = bytearray(current)
            out[tail_at:tail_at + tail_size] = tail
            out[site_at:site_at + 11] = site
            if space.is_scaleout(current):
                space._seal_scaleout(out, space._read_scale_directory(current))
            else:
                requests = space._read_directory(current)
                out[space.DIRECTORY:space._directory_end(requests)] = space._directory(
                    requests, space._code_bytes(out, requests))
            for sec in _sections(out):
                out[sec.header_offset + 36:sec.header_offset + 56] = section_digest(out, sec)
            return bytes(out)

        old_tail, old_site = mm.previous_star_code(code["va"] + mm.STAR_OFFSET), mm.previous_import_site(code["va"])
        previous = build(old_tail, old_site)
        self.assertEqual(mm.status(previous, self.data), "applied")
        self.assertEqual(mm.import_status(previous, self.data), "previous")
        upgraded, receipt = mm.apply(previous, self.data)
        self.assertEqual(receipt["status"], "upgraded")
        self.assertEqual(upgraded, current)
        self.assertEqual(mm.apply(upgraded, self.data)[1]["status"], "already_applied")
        for tail, site, why in ((old_tail, mm.import_site(code["va"]), "old tail, new site"),
                                (mm.star_code(code["va"] + mm.STAR_OFFSET), old_site, "new tail, old site")):
            with self.subTest(why):
                mixed = build(tail, site)
                self.assertEqual(mm.status(mixed, self.data), "foreign")
                self.assertEqual(mm.import_status(mixed, self.data), "foreign")

    def test_a_beta_765_install_gets_its_row_hooks_and_the_whole_import_in_one_pass(self):
        """b780: a real beta 76.5 disc has neither the beta 77 row hooks nor the b780 import tail (it carries the
        star-only tail and its plain jump). apply() completes both in one pass; the result equals a fresh install and
        the receipt counts every changed byte."""
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        current, _ = mm.apply(self.retail, self.data)
        code, dat = mm.allocations(current)
        image = XbeImage(current)
        out = bytearray(current)
        tail_at, site_at = code["raw"] + mm.STAR_OFFSET, image.offset(mm.STAR_VA, 11)
        out[tail_at:tail_at + mm.TABLE_OFFSET - mm.STAR_OFFSET] = mm.previous_star_code(code["va"] + mm.STAR_OFFSET)
        out[site_at:site_at + 11] = mm.previous_import_site(code["va"])
        for label, va, before, _after in mm.sites(code["va"], dat["va"], mm.RETAIL_COUNT + len(self.data.moments)):
            if label in mm.ROW_LABELS:
                out[image.offset(va, len(before)):image.offset(va, len(before)) + len(before)] = before
        if space.is_scaleout(current):
            space._seal_scaleout(out, space._read_scale_directory(current))
        else:
            requests = space._read_directory(current)
            out[space.DIRECTORY:space._directory_end(requests)] = space._directory(
                requests, space._code_bytes(out, requests))
        for sec in _sections(out):
            out[sec.header_offset + 36:sec.header_offset + 56] = section_digest(out, sec)
        beta765 = bytes(out)
        self.assertEqual((mm.status(beta765, self.data), mm.row_hooks_status(beta765, self.data),
                          mm.import_status(beta765, self.data)), ("applied", "previous", "previous"))
        upgraded, receipt = mm.apply(beta765, self.data)
        self.assertEqual((receipt["status"], receipt["rows_completed"]), ("upgraded", True))
        self.assertIn("star-only import tail", receipt["upgraded_from"])
        self.assertEqual(upgraded, current)
        self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(beta765, upgraded)))
        self.assertEqual(mm.apply(upgraded, self.data)[1]["status"], "already_applied")

    def test_a_player_gets_his_own_art_or_none_and_his_tone(self):
        with outer_image() as archive:
            main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            by_id = {e.name_id: e for e in archive.entries}
            template = archive.read(by_id[mm.name_id(TEAMS["falcons_1998"]["template"])].virtual_offset,
                                    by_id[mm.name_id(TEAMS["falcons_1998"]["template"])].size)
        doc = rr.RosterDocument(main[32:])
        rows = self.data.rosters["falcons_1998"]
        looks = [{"name": f"{r['first']} {r['last']}", "tone": None} for r in rows]
        looks[0] = dict(looks[0], tone=4)
        looks[1] = dict(looks[1], tone=1, retail={"photo": 4321, "skin": 16, "face": 9, "dreads": 1})
        looks[2] = dict(looks[2], tone=2, retail={"photo": 4321, "skin": 8, "face": 3, "dreads": 0})
        raw = mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200,
                              appearance=looks, main_photos=frozenset({999}))
        players = sorted(rr.RosterDocument(raw[32:]).players, key=lambda p: p.index)
        v = [p.record.values for p in players]
        self.assertEqual(players[0].record.skin & 7, 4)
        self.assertEqual((v[0]["photo_id"], v[3]["photo_id"]), (mm.NOPHOTO_BASE, mm.NOPHOTO_BASE + 3))
        self.assertEqual((v[1]["photo_id"], players[1].record.skin, v[1]["face"], v[1]["dreads"]), (4321, 17, 9, 1))
        blocked = mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200,
                                  appearance=looks, main_photos=frozenset({4321}))
        self.assertEqual(sorted(rr.RosterDocument(blocked[32:]).players, key=lambda p: p.index)[1].record.values["photo_id"],
                         mm.NOPHOTO_BASE + 1)                   # a current record uses that id: its art may be his no more
        from mod_editor.core import nfl2k5_my_career_prospects as prospects
        for p in players:
            self.assertEqual(p.record.values["star_tag"], int(prospects.native_overall(p.record) >= mm.STAR_MIN_OVERALL))
        self.assertTrue(any(p.record.values["star_tag"] for p in players))

    def test_a_scan_the_league_overwrote_lives_in_its_unused_id(self):
        """b776-fs1: retail id 4321 is a current record's now; the player's own copy is in id 777 (the scans table)."""
        with outer_image() as archive:
            main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            by_id = {e.name_id: e for e in archive.entries}
            template = archive.read(by_id[mm.name_id(TEAMS["falcons_1998"]["template"])].virtual_offset,
                                    by_id[mm.name_id(TEAMS["falcons_1998"]["template"])].size)
        doc = rr.RosterDocument(main[32:])
        rows = self.data.rosters["falcons_1998"]
        looks = [{"name": f"{r['first']} {r['last']}", "tone": None} for r in rows]
        looks[1] = dict(looks[1], tone=1, retail={"photo": 4321, "skin": 16, "face": 9, "dreads": 1})
        ids = lambda raw: [p.record.values["photo_id"] for p in sorted(rr.RosterDocument(raw[32:]).players, key=lambda p: p.index)]  # noqa: E731
        taken = mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200, appearance=looks,
                                main_photos=frozenset({4321}), scans={4321: 777})
        self.assertEqual(ids(taken)[1], 777)
        free = mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200, appearance=looks,
                               main_photos=frozenset(), scans={4321: 777})
        self.assertEqual(ids(free)[1], 4321)                     # nobody holds the retail id: his own head is still there
        none = mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200, appearance=looks,
                               main_photos=frozenset({4321}), scans={})
        self.assertEqual(ids(none)[1], mm.NOPHOTO_BASE + 1)
        with self.assertRaises(mm.MoreMomentsError):             # a main-roster record using the copy's id would show him
            mm.compile_team(template, self.data.teams["falcons_1998"], rows, doc.colleges, 200, appearance=looks,
                            main_photos=frozenset({4321, 777}), scans={4321: 777})


@unittest.skipUnless(retail_available(), "user-owned USA disc folder absent")
class ShippedMomentLooksRetailTests(unittest.TestCase):
    """b779-mo4 (Ju3tin 10/28-29: "disappearing" / "invisible players" in newer moments): every shipped moment team
    file, compiled from the retail templates exactly as the build does, keeps each player inside what a moment can
    draw. The headless bit (+0x0C bit 7) draws the model without a head; a hair_style other than 0 asks for the added
    hair models of the main-roster hair step; the game has facemasks 00..26 only (nfl2k5_modern_helmets); and a player
    without his own face falls back to the generic head f(9001 + 100 * tone + face), which exists only for tone 0..5
    and face 0..6 (nfl2k5_rookie_faces, retail FUN_000E6780). A moment team has 53 players; the live team holds 65.
    Static guard only: the emulator runs of b779-mo4 did not reproduce the report (reports/b779_mo4_REPORT.md)."""

    @classmethod
    def setUpClass(cls):
        cls.data = mm.Data.load()
        with outer_image() as archive:
            cls.main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
            by_id = {e.name_id: e for e in archive.entries}
            descriptors = mm._retail_descriptors(cls.main)
            cls.templates = {}
            for key in cls.data.team_order():
                d = mm.template_for(cls.data.teams[key], descriptors)
                cls.templates[key] = archive.read(by_id[d["id"]].virtual_offset, by_id[d["id"]].size)
        cls.files = mm.compile_files(cls.main, cls.templates, cls.data)

    def test_every_moment_player_stays_inside_what_a_moment_draws(self):
        self.assertEqual(len(self.files), len(self.data.team_order()))
        for filename, raw in self.files.items():
            doc = rr.RosterDocument(raw[32:])
            self.assertEqual((len(doc.players), doc.teams[0].player_count), (53, 53), filename)
            for p in doc.players:
                v = p.record.values
                who = f"{filename} {p.first} {p.last}"
                self.assertEqual(v["headless"], 0, who)
                self.assertEqual(v["hair_style"], 0, who)
                self.assertLessEqual(v["face_mask"], 26, who)
                self.assertLessEqual(p.record.skin & 7, 5, who)
                self.assertLessEqual(v["face"] & 7, 6, who)

    def test_every_moment_team_prints_its_own_seasons_code(self):
        """b780 (v0.8 known issue: "the 2021 Rams show STL in the Super Bowl LVI moment"): the screens print the team's
        city abbreviation (+0x13C; the details screen's NOW box reads it at 2C5D40 / 2C5D90). Every shipped moment
        team file carries the code its club used that season, not its retail template's (the 1999 St. Louis Rams,
        1983 Los Angeles Raiders, 1970 Baltimore Colts and 1975 St. Louis Cardinals templates), and every text the
        importer copies fits the spare team's buffer."""
        expected = {key: mm.display_abbreviation(team) for key, team in self.data.teams.items()}
        self.assertEqual(expected["rams_2021"], "LAR")
        self.assertEqual(expected["cardinals_2008"], "ARI")    # the 2026 Cardinals' code (retail and the data: ARZ)
        for key in ("raiders_2001", "colts_2009", "colts_2022"):
            self.assertEqual(expected[key], self.data.teams[key]["abbreviation"], key)
        by_file = {name: key for key, name, *_ in mm.table_entries(self.data)}
        seen = set()
        for filename, raw in self.files.items():
            body = raw[32:]
            t = rr.RosterDocument(body).teams[0].offset
            def text(field):
                at = t + field + struct.unpack_from("<i", body, t + field)[0] - 1
                end = at
                while body[end:end + 2] != b"\0\0":
                    end += 2
                return body[at:end].decode("utf-16le")
            key = by_file[filename]
            with self.subTest(team=key):
                self.assertEqual(text(mm.TEAM_CITY_ABBREVIATION), expected[key])
                for field, capacity in mm.SLOT_TEXT_CAPACITY.items():
                    self.assertLessEqual(len(text(field)), capacity)
            seen.add(key)
        self.assertEqual(seen, set(self.data.teams))
        rams = {name: key for name, key in by_file.items() if key == "rams_2021"}
        self.assertEqual(len(rams), 1)

    def test_the_templates_are_inside_the_same_envelope(self):
        """The compiled records keep the donors' gear (helmet shell, facemask, sleeves); the donors are retail
        historic records, so the envelope above is the retail one."""
        for key, raw in self.templates.items():
            for p in rr.RosterDocument(raw[32:]).players:
                v = p.record.values
                self.assertEqual((v["headless"], v["hair_style"]), (0, 0), key)
                self.assertLessEqual(v["face_mask"], 26, key)


if __name__ == "__main__":
    unittest.main()
