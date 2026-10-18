"""Classic teams in Quick Game (job ct1, Noah 2026-10-17). EXPERIMENTAL / UNWITNESSED: offline evidence only.

Data, helper code and Quick Game variant tests run anywhere. The native Team Select tests need the private retail
extraction (NFL2K5_RETAIL_EXTRACTION) and skip without it.
"""
from __future__ import annotations

import csv
import io
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core import nfl2k5_classic_teams as ct  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

NOAH = {"titans_2019", "giants_2016", "giants_2022", "browns_2020", "buccaneers_2020", "colts_2014", "chargers_2006",
        "eagles_2017", "lions_2008", "browns_2017"}


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ct.Data.load()

    def test_twenty_four_team_seasons_within_the_identity_and_list_ceilings(self):
        self.assertEqual(len(self.data.teams), 24)
        self.assertLessEqual(len(self.data.teams), ct.LAST_ID - ct.FIRST_ID + 1)
        self.assertLessEqual(len(self.data.teams), ct.MAX_ROWS)
        self.assertTrue(NOAH <= set(self.data.teams), "Noah's 10/17 picks")
        seasons = [self.data.teams[k]["season"] for k in self.data.order()]
        self.assertEqual(seasons, sorted(seasons))
        self.assertTrue(all(2005 <= s <= 2025 for s in seasons))

    def test_no_classic_team_duplicates_an_anniversary_team_season(self):
        moments = mm.Data.load()
        # The one deliberate exception: Noah asked for the 2017 Eagles with Wentz AND Foles (the season roster, week
        # 13); the Anniversary team is the Super Bowl LII game roster (Wentz on injured reserve). Distinct files.
        self.assertEqual(set(self.data.teams) & set(moments.teams), {"eagles_2017"})
        self.assertNotEqual(self.data.filename("eagles_2017"), mm.table_entries(moments)[
            [k for k, *_r in mm.table_entries(moments)].index("eagles_2017")][1])
        retail = {(d["selector"], d["year"]) for d in ct._descriptors(_main_roster())} if _main_roster() else set()
        self.assertFalse({(t["selector"], t["season"]) for t in self.data.teams.values()} & retail)

    def test_every_roster_is_53_with_starters_and_the_m1_contract_minimums(self):
        minimums = {"QB": 2, "K": 1, "P": 1, "WR": 4, "HB": 2, "FB": 1, "TE": 2, "T": 2, "G": 2, "C": 1, "DE": 2,
                    "DT": 2, "CB": 3, "FS": 1, "SS": 1}
        for key in self.data.order():
            rows = self.data.rosters[key]
            counts = {}
            for row in rows:
                counts[row["position"]] = counts.get(row["position"], 0) + 1
                self.assertTrue(1 <= int(row["jersey"]) <= 99)
                self.assertTrue(150 <= int(row["weight"]) <= 405)
            for position, need in minimums.items():
                self.assertGreaterEqual(counts.get(position, 0), need, f"{key} {position}")
            self.assertGreaterEqual(counts.get("OLB", 0) + counts.get("ILB", 0), 3, key)
            for position in counts:
                self.assertEqual(sorted(int(r["depth"]) for r in rows if r["position"] == position),
                                 list(range(1, counts[position] + 1)), f"{key} {position} depth")

    def test_noah_named_players_start(self):
        def starter(key, last, position):
            return any(r["last"] == last and r["position"] == position and int(r["depth"]) <= 3
                       for r in self.data.rosters[key])
        self.assertTrue(starter("titans_2019", "Tannehill", "QB") and starter("titans_2019", "Henry", "HB")
                        and starter("titans_2019", "Brown", "WR"))
        self.assertTrue(starter("browns_2020", "Mayfield", "QB") and starter("browns_2020", "Landry", "WR")
                        and starter("browns_2020", "Beckham Jr.", "WR"))
        self.assertTrue(starter("buccaneers_2020", "Brady", "QB"))
        self.assertTrue(starter("colts_2014", "Luck", "QB"))
        self.assertTrue(starter("chargers_2006", "Rivers", "QB"))
        qbs = [r["last"] for r in self.data.rosters["eagles_2017"] if r["position"] == "QB"]
        self.assertIn("Wentz", qbs)
        self.assertIn("Foles", qbs)

    def test_every_player_has_a_sourced_appearance_row(self):
        allowed = ("headshot_review", "headshot_2026", "retail_2004", "photo_review", "public_record",
                   "retail_historic_same_season", "v0.4 main roster", "none")
        for key in self.data.order():
            for look in self.data.appearance[key]:
                self.assertTrue(look["source"].startswith(allowed), look)
                if look["source"].startswith("none"):
                    self.assertIsNone(look["tone"])
                else:
                    self.assertIn(look["tone"], range(6))

    def test_kits_reuse_existing_styles_and_stadiums_are_franchise_rows(self):
        for key, row in self.data.presentation.items():
            self.assertIn(row["kit_quality"], ("match", "close", "stand-in"))
            if isinstance(row["kit"], dict):
                self.assertIn(row["kit"]["fallback"], ("retail", "modern"))
            self.assertEqual(row["stadium"], "franchise")


class HelperCodeTests(unittest.TestCase):
    def test_layout_and_list_length(self):
        code = ct.helper_code(0x1509E70, moment_table=0x14DE450, moment_count=50,
                              rows=[(2019, 8, 68), (2016, 8, 40)], default_fmt=ct.FMT_FILE)
        self.assertEqual(len(code), ct.RO_SIZE)
        self.assertEqual(code[0], 0xA1)                                    # total: mov eax,[root]
        self.assertEqual(struct.unpack_from("<I", code, 9)[0], 52)          # add eax, M + N
        self.assertEqual(code[ct.ROWS_OFFSET:ct.ROWS_OFFSET + 8], struct.pack("<HBBHBB", 2019, 8, 68, 2016, 8, 40))
        self.assertEqual(code[ct.ROWS_OFFSET + 8:], bytes(ct.RO_SIZE - ct.ROWS_OFFSET - 8))
        # every entry point the Quick Game variant calls holds code
        for entry in h1.CLASSIC_ENTRIES.values():
            self.assertNotEqual(code[entry], 0xCC)

    def test_quick_game_variant_changes_only_its_patterns(self):
        for seasons in (False, True):
            base = h1.code_for(0x14E0000, 0x14F0000, seasons=seasons)
            classic = h1.code_for(0x14E0000, 0x14F0000, seasons=seasons, classic_va=0x1509E70)
            self.assertEqual(len(base), len(classic))
            changed = [i for i in range(len(base)) if base[i] != classic[i]]
            self.assertTrue(changed)
            calls = [i for i in range(len(classic) - 5) if classic[i] == 0xE8 and base[i] != 0xE8]
            targets = {0x14E0000 + i + 5 + struct.unpack_from("<i", classic, i + 1)[0] for i in calls}
            self.assertEqual(targets, {0x1509E70 + v for v in h1.CLASSIC_ENTRIES.values()})
            self.assertLessEqual(len(changed), 70)

    def test_owner_is_a_late_read_only_owner_of_the_union(self):
        self.assertIn(ct.OWNER, space.LATE_OWNERS)
        # b775-int1: the last read-only late owner; only hs1's hair styles code owner (no read-only bytes) follows it
        self.assertEqual(space.LATE_OWNERS[-2:], (ct.OWNER, "nfl2k5_hair_styles"))
        self.assertIn(ct.REQUESTS[0], space.dormant_union())
        rows = [a for a in space._scale_allocations(space.dormant_union()) if a["owner"] == ct.OWNER]
        self.assertEqual(len(rows), 1)
        region = next(r for r in space._scale_regions(space.dormant_union())
                      if r["va"] <= rows[0]["va"] < r["va"] + r["size"])
        self.assertTrue(region["flags"] & 4, "the helper page must be executable")


def _main_roster():
    try:
        from tests.nfl2k5_supersim_draft_fixture import XBE
        from mod_editor.core import nfl2k5_roster_records as rr
        if not (XBE.parent / "vc_53450030/0").is_file():
            return None
        with rr._outer_image()(XBE.parent) as archive:
            return archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
    except Exception:  # noqa: BLE001
        return None


class NativeTests(unittest.TestCase):
    """The real Team Select handlers, the option's classic variant and the importer, on the retail extraction."""

    @classmethod
    def setUpClass(cls):
        if _main_roster() is None:
            raise unittest.SkipTest("private retail roster archive is absent")
        try:
            from nfl2k5_classic_teams_native import build
        except ImportError as exc:
            raise unittest.SkipTest(f"Unicorn unavailable: {exc}")
        from tests.nfl2k5_supersim_draft_fixture import XBE
        cls.retail_dir = XBE.parent
        cls.build = staticmethod(build)
        make, cls.data, cls.moment_files, cls.files, cls.receipt, cls.receipts = build(XBE.parent)
        cls.make = staticmethod(make)

    @property
    def cpu(self):
        if not hasattr(self, "_cpu"):
            self._cpu = self.make()
        return self._cpu

    def test_receipt(self):
        self.assertEqual(self.receipt["status"], "applied")
        self.assertEqual((self.receipt["moment_teams"], self.receipt["classic_rows"], self.receipt["list_length"]),
                         (50, 24, 149))

    def test_one_forward_lap_loads_retail_then_moments_then_classic_and_wraps(self):
        cpu = self.cpu
        user1, _user2 = cpu.spare_slots()[:2]
        start = cpu.pool()["used"]
        cpu.team_select(cpu.last_resident(), cpu.team(15))
        steps = [cpu.press("home", +1) for _ in range(150)]
        loaded = [s["loaded"][0] for s in steps[:149]]
        moment_names = [name for _key, name, *_rest in mm.table_entries(mm.Data.load())]
        classic_names = [name for name, _raw in self.files]
        self.assertEqual(loaded[75:125], moment_names)
        self.assertEqual(loaded[125:], classic_names)
        self.assertEqual(len(set(loaded)), 149)
        for step in steps[:149]:
            self.assertEqual(step["home"]["index"], cpu.index(user1))
            self.assertEqual((step["home"]["category"], step["home"]["players"]), (4, 53))
            self.assertEqual(step["pool"]["used"], start + 53)
        self.assertEqual((steps[149]["home"]["index"], steps[149]["loaded"]), (0, []))   # wraps to the 49ers
        self.assertEqual(steps[149]["pool"]["used"], start)

    def test_each_classic_team_imports_with_its_identity_home_row_and_kit(self):
        cpu = self.cpu
        user1, _ = cpu.spare_slots()[:2]
        cpu.team_select(cpu.team(0), cpu.team(15))
        receipts = list(self.receipts.values())
        for receipt in reversed(sorted(receipts, key=lambda r: r["identity"])):
            step = cpu.press("home", -1)
            self.assertEqual(step["loaded"], [receipt["file"]])
            self.assertEqual(step["home"]["identity"], receipt["identity"])
            self.assertEqual(cpu.stadium_id(user1), receipt["stadium_id"])
            self.assertEqual(cpu.style(user1), receipt["style"])

    def test_both_sides_hold_classic_teams_and_never_the_same_slot(self):
        cpu = self.cpu
        user1, user2 = cpu.spare_slots()[:2]
        cpu.team_select(cpu.team(0), cpu.team(0))
        home = cpu.press("home", -1)
        away = cpu.press("away", -1)
        self.assertEqual(home["home"]["index"], cpu.index(user1))
        self.assertEqual(away["away"]["index"], cpu.index(user2))
        self.assertEqual(home["loaded"], away["loaded"])                       # the same team-season, two copies
        self.assertEqual(cpu.pool()["used"], 106)                               # mo1's import floor is what it needs

    def test_new_files_never_reuse_a_disc_name_and_templates_stay_unchanged(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        with rr._outer_image()(self.retail_dir) as archive:
            ids = {e.name_id for e in archive.entries}
            by_id = {e.name_id: e for e in archive.entries}
            before = {k: archive.read(by_id[mm.name_id(self.data.teams[k]["template"])].virtual_offset,
                                      by_id[mm.name_id(self.data.teams[k]["template"])].size) for k in self.data.order()}
        for name, raw in self.files:
            self.assertNotIn(mm.name_id(name), ids)
            self.assertEqual(raw[:4], b"ROST")
        templates = dict(before)
        ct.compile_files(_main_roster(), templates, self.data, spares={}, has_kit=lambda c, s: True)
        self.assertEqual(templates, before)

    def test_executable_changes_stay_in_owned_spans(self):
        """Only the Quick Game code, the classic allocation, the allocator's own directory page and the section header
        digests change; every other byte of the executable stays."""
        from mod_editor.core import nfl2k5_espn25_rosters as e
        from mod_editor.core import nfl2k5_throw_tuning as tt
        payload, _ = tt._apply_all(e.read_xbe(self.retail_dir), None, False, scheme_labels=True, practice_squad=True,
                                   franchise_practice=True, depth_locks=True, xbe_space=True, zone_drop_cap=True,
                                   espn25_more_moments=True, historic_teams_quick_game=True)
        payload, _ = space.extend_scaleout(payload, (space.DIRECTORY_CODE_REQUEST,))
        after, _ = ct.apply_xbe(payload, ct.rows_for(_main_roster(), self.data))
        again, receipt = ct.apply_xbe(after, ct.rows_for(_main_roster(), self.data))
        self.assertEqual((again, receipt["status"]), (after, "already_applied"))
        code, _data = h1.allocations(after)
        owned = ct.allocation(after)
        directory = next(r for r in space.layout(after)["regions"] if r["kind"] == "read_only")
        spans = [(0, 0x1000), (code["raw"], code["raw"] + h1.CODE_SIZE), (owned["raw"], owned["raw"] + ct.RO_SIZE),
                 (directory["raw"], directory["raw"] + space.PAGE)]
        self.assertEqual(len(after), len(payload))
        for i in range(len(after)):
            if after[i] != payload[i]:
                self.assertTrue(any(lo <= i < hi for lo, hi in spans), hex(i))
        self.assertEqual(ct.xbe_status(after), "applied")
        self.assertEqual(h1.status(after), "applied")
        self.assertEqual(ct.xbe_status(payload), "retail")


class HonoursTests(unittest.TestCase):
    """Coordinator 10/17: every rating override follows a sourced season honour and a short list of floor rules."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((ROOT / "data/nfl2k5_classic_teams/honours.json").read_text(encoding="utf-8"))
        cls.data = ct.Data.load()
        cls.manifest = json.loads((ROOT / "data/nfl2k5_classic_teams/manifest.json").read_text(encoding="utf-8"))

    def test_rules_are_the_documented_floors(self):
        self.assertEqual(self.doc["rules"], {"MVP": 95, "OPOY": 93, "DPOY": 93, "AP1": 90, "LEADER": 90, "AP2": 87,
                                             "PB": 84})

    def test_every_honour_names_its_source_and_the_source_line_says_so(self):
        import re
        teams = json.loads((ROOT / "data/nfl2k5_classic_teams/teams.json").read_text(encoding="utf-8"))["teams"]
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_classic_teams_honours as hb
        for key, src in self.doc["sources"].items():
            self.assertRegex(src["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(src["url"].startswith(("https://en.wikipedia.org/w/index.php?title=",
                                                   "https://github.com/nflverse/")), key)
            if "wikipedia" in src["url"]:
                self.assertIn("oldid=", src["url"])          # a fixed revision
        for p in self.doc["players"]:
            team = teams[p["team"]]
            rows = [r for r in self.data.rosters[p["team"]] if f"{r['first']} {r['last']}" == p["name"]]
            self.assertEqual(len(rows), 1, p["name"])
            best = max(self.doc["rules"][h["honour"]] for h in p["honours"])
            self.assertEqual(p["floor"], best)
            for h in p["honours"]:
                self.assertIn(h["source"], self.doc["sources"])
                line = h["line"]
                if h["honour"] == "LEADER":
                    self.assertTrue(line.startswith("led the NFL in"), line)
                    self.assertEqual(h["source"], f"nflverse_stats_{team['season']}")
                    continue
                last = hb.fold(p["name"]).split()[-1] if not p["name"].endswith((" Jr.", " III", " II")) else \
                    hb.fold(p["name"]).split()[-2]
                self.assertIn(last.rstrip(".").lower(), hb.plain(line).lower(), (p["name"], line))
                if h["honour"] in ("AP1", "AP2", "PB"):
                    self.assertIn(hb.FULL_NAMES[team["selector"]].lower(), line.lower(), line)
                    self.assertTrue(h["source"].startswith("allpro_" if h["honour"] != "PB" else "probowl_"))
                    self.assertTrue(h["source"].endswith(str(team["season"])))
                if h["honour"] == "AP2":
                    self.assertIn("AP-2", line)
                if h["honour"] == "AP1":
                    self.assertRegex(hb.plain(line), r"\bAP\b(?!-)")
                if h["honour"] in ("MVP", "OPOY", "DPOY"):
                    self.assertEqual(h["source"], h["honour"].lower())

    def test_the_named_stars_carry_their_season_honours(self):
        named = {("titans_2019", "Derrick Henry"): {"LEADER", "PB"}, ("ravens_2019", "Lamar Jackson"): {"MVP"},
                 ("chiefs_2022", "Patrick Mahomes"): {"MVP"}, ("panthers_2015", "Cam Newton"): {"MVP"},
                 ("packers_2011", "Aaron Rodgers"): {"MVP"}, ("chargers_2006", "LaDainian Tomlinson"): {"MVP"},
                 ("bears_2006", "Devin Hester"): {"AP1"}, ("seahawks_2013", "Richard Sherman"): {"AP1"},
                 ("seahawks_2013", "Earl Thomas"): {"AP1"}, ("eagles_2017", "Carson Wentz"): {"AP2"},
                 ("colts_2014", "Andrew Luck"): {"PB"}, ("browns_2020", "Nick Chubb"): {"PB"},
                 ("eagles_2024", "Saquon Barkley"): {"OPOY"}}
        found = {(p["team"], p["name"]): {h["honour"] for h in p["honours"]} for p in self.doc["players"]}
        for key, want in named.items():
            self.assertTrue(want <= found.get(key, set()), key)

    def test_overrides_reach_their_floor_and_the_rows_meet_every_floor(self):
        for o in self.manifest["overrides"]:
            self.assertGreaterEqual(o["native_overall_after"], o["floor"], o["name"])
            self.assertIn(o["rule"], self.doc["rules"])
        if _main_roster() is None:
            self.skipTest("private retail roster archive is absent (native overall template)")
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_classic_teams_build as cb
        from tests.nfl2k5_supersim_draft_fixture import XBE
        template = cb.template_record(XBE.parent)
        for p in self.doc["players"]:
            row = next(r for r in self.data.rosters[p["team"]] if f"{r['first']} {r['last']}" == p["name"])
            self.assertGreaterEqual(cb.native_ovr(row, template), p["floor"], p["name"])

    def test_the_honours_rebuild_from_the_pinned_pages(self):
        cache = Path("/home/noah/2k-worktrees/.b77-scratch/f5/sources")
        inputs = Path("/home/noah/2k-worktrees/.b77-scratch/ct1/nflverse")
        if not (cache / "provenance.json").is_file() or not inputs.is_dir():
            self.skipTest("private source cache absent")
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_classic_teams_honours as hb
        self.assertEqual(hb.build(cache, inputs), self.doc)


if __name__ == "__main__":
    unittest.main()
