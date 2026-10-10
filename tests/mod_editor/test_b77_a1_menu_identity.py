"""b77 / a1: every ESPN 25th Anniversary menu entry draws and opens its own moment.

Noah (10/7, from a tester): "ESPN 25th anniversary mode now isn't playing the right scenario: click one and another
wrong one opens." Beta 76.5 sorted the 51 moments by date by mapping the list's display row to the physical SITU row,
but hooked the mapping at a caption function that retail never calls instead of the callbacks that draw the rows
(title and date 20C800, mini helmets 20C710 / 20C790): 27 of the 51 rows showed one moment and opened another.

These tests run the game's own list, select, setup and consumer code under Unicorn, for all 51 menu rows, and state
what every row must show and load from the authored data (tests/nfl2k5_b77_menu_native.py). They do not run a game.

  * CatalogOrderTests (retail free): the per-moment catalogs follow the physical row order.
  * StudioRouteMenuTests: the executable the Studio builds from the retail disc (moments, named venues, stock books).
  * V05DiscMenuTests: the shipped SOFTDRINK 2K28 v0.5 disc, before the repair (the bug, 27 rows) and after
    tools/b77/a1_repair.py (all 51 rows), with the repair's scope, idempotence and refusals.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

RETAIL_ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
V05_DISC = Path(os.environ.get("B77_V05_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"
try:
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except ImportError:
    HAVE_UNICORN = False
if HAVE_UNICORN:
    import nfl2k5_b77_menu_native as nat
    from nfl2k5_espn25_more_moments_native import FastMomentsCPU


def write_proof(name, entries, expected, order):
    """B77_A1_PROOF_DIR=<folder> keeps each run's per-entry table as evidence for the report."""
    folder = os.environ.get("B77_A1_PROOF_DIR")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / f"a1_menu_{name}.json").write_text(
            json.dumps(dict(runtime_witnessed=False, run=name, rows=nat.proof_table(entries, expected, order)),
                       indent=1) + "\n", encoding="utf-8", newline="\n")


def mismatched_rows(entries):
    """Display rows whose drawn title (and date) is not the moment the click opened."""
    bad = []
    for entry in entries:
        drawn = entry["shown"]["title"]
        if (drawn["title"], drawn["date"]) != (entry["opened"]["title"], entry["opened"]["date"]):
            bad.append(entry["display_row"])
    return bad


class CatalogOrderTests(unittest.TestCase):
    """Retail free: the data the physical-row consumers index is in physical order, and the menu order is by date."""

    def test_catalogs_follow_the_physical_rows(self):
        data = mm.Data.load()
        dates = list(mm.RETAIL_DATES) + [m["date"] for m in data.moments]
        self.assertEqual(len(dates), 51)
        fields = json.loads((ROOT / "data/nfl2k5_espn25_fields.json").read_text())["moments"]
        venues = json.loads((ROOT / "data/nfl2k5_moment_venues.json").read_text())["moments"]
        eras = json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]
        previews = json.loads((ROOT / "data/espn25_previews_2026.json").read_text())["moments"]
        for name, rows in (("fields", fields), ("venues", venues[:50]), ("era", eras), ("previews", previews)):
            self.assertEqual([r["row"] for r in rows], list(range(1, len(rows) + 1)), name)
        titles = {r["row"]: r["title"] for r in fields}
        for i, text in enumerate(dates):
            from nfl2k5_b77_menu_native import iso
            with self.subTest(physical_row=i + 1):
                day = iso(text)
                self.assertEqual(fields[i]["date"], day.isoformat())
                if i < 50:
                    self.assertEqual(venues[i]["date"], day.isoformat())
                    self.assertEqual(previews[i]["text"]["date"], text)
                    self.assertEqual(previews[i]["text"]["title"], titles[i + 1])
                season = day.year if day.month >= 8 else day.year - 1
                self.assertEqual(eras[i]["season"], season)
                if i >= 25:
                    self.assertEqual(data.moments[i - 25]["title"], titles[i + 1])

    def test_display_order_is_the_date_order_with_physical_ties(self):
        from nfl2k5_b77_menu_native import iso
        data = mm.Data.load()
        dates = list(mm.RETAIL_DATES) + [m["date"] for m in data.moments]
        order = sorted(range(51), key=lambda i: (iso(dates[i]), i))
        self.assertEqual(list(mm.display_order(data)), order)
        self.assertEqual(len([d for d, p in enumerate(order) if d != p]), 27 + 0, "27 rows move; the others stay")
        self.assertEqual([d + 1 for d, p in enumerate(order) if d != p][0], 22)
        inventory = mm.display_inventory(data)
        self.assertEqual([r["physical_row"] for r in inventory], [p + 1 for p in order])


def check_entries(test, entries, expected, order, *, named_venues, era, books):
    """The assertions: entries are resolve_entry results for display rows 0..50."""
    test.assertEqual(len(entries), 51)
    canonical = ("title", "date", "away", "home", "stadium", "user_side", "possession", "score_now", "final", "quarter",
                 "down", "timeouts", "weather", "time", "temp")
    for entry in entries:
        d = entry["display_row"] - 1
        physical = order[d]
        want = expected[physical - 1]
        shown, opened = entry["shown"], entry["opened"]
        with test.subTest(display_row=d + 1, physical_row=physical, title=want["title"]):
            # what the click opens is the display row's own moment
            test.assertEqual(entry["physical"], physical)
            for key in canonical:
                test.assertEqual(opened[key], want[key], key)
            for key in ("ball", "distance", "seconds"):
                test.assertAlmostEqual(opened[key], want[key], places=3, msg=key)
            # what the row shows is that same moment: title and date, both helmets (same record, same kits)
            test.assertEqual((shown["title"]["title"], shown["title"]["date"]), (want["title"], want["date"]))
            test.assertEqual(shown["title"]["asked"], [physical - 1])
            test.assertEqual(shown["home_helmet"]["asked"], [physical - 1, physical - 1])
            test.assertEqual(shown["away_helmet"]["asked"], [physical - 1])
            test.assertEqual({tuple(shown[k]["records"]) for k in shown}, {(entry["record"],), (entry["record"], entry["record"])})
            test.assertEqual(shown["away_helmet"]["kit"], opened["kits"][0])
            test.assertEqual(shown["home_helmet"]["kit"], opened["kits"][1])
            # both teams loaded, as the data names them, with 53 players each
            test.assertEqual(entry["teams"]["active"], (53, 53))
            test.assertEqual((entry["teams"]["away"], entry["teams"]["home"]), (want["team_names"]))
            test.assertEqual(entry["new_files"], want["new_files"])
            test.assertEqual(entry["export_players"], 106)
            test.assertTrue(all(entry["kit_exists"].values()), entry["kit_files"])
            test.assertEqual(entry["field_qbs"], want["qbs"])
            test.assertEqual([len(entry["rosters"]["away"]), len(entry["rosters"]["home"])], [53, 53])
            test.assertEqual(entry["rosters"], want["rosters"])         # all 53 players of each side, by name
            # the staged scenario
            test.assertEqual(entry["scenario"], dict(home_score=want["score_now"][1], away_score=want["score_now"][0],
                                                     clock_seconds=want["seconds"], quarter=want["quarter"]))
            # every consumer keyed on the physical row
            test.assertEqual((entry["stadium_record"]["index"], entry["stadium_record"]["aligned"]), (want["stadium"], True))
            if named_venues:
                test.assertEqual(entry["details_venue"], want["venue"])
            test.assertEqual(entry["field_bundle"], f"a{physical - 1:02d}ds.iff")
            if era:
                test.assertAlmostEqual(entry["era_kickoff"], (50 - want["era"]["kickoff_yard"]) * 91.44, places=2)
            if books:
                modern = {side: 2005 <= want[side][1] <= 2030 for side in ("away", "home")}
                test.assertEqual(entry["book_modern"], modern)


def with_team_facts(rows, data, resources, context):
    """Add the facts only the rosters give: the team names a load must show, the files it loads, the starting QBs."""
    descriptors = {(d["selector"], d["year"]): d for d in context["descriptors"]}
    out = []
    for row in rows:
        row = dict(row)
        names, qbs, new, rosters = [], [], [], []
        for side in ("away", "home"):
            selector, season = row[side]
            if "away_key" in row:                                     # an authored team-season: its own new file
                key = row[side + "_key"]
                team = data.teams[key]
                names.append(f"{team['nickname']} '{season % 100:02d}")
                starters = [r for r in data.rosters[key] if r["position"] == "QB" and int(r["depth"]) == 1]
                qbs.append(f"{starters[0]['first']} {starters[0]['last']}")
                new.append(f"h-{team['asset_code']}-{season}-{selector}-9.iff")
                rosters.append(sorted(f"{r['first']} {r['last']}" for r in data.rosters[key]))
            else:                                                     # a retail historic team-season
                descriptor = descriptors[(selector, season)]
                doc = rr.RosterDocument(resources[descriptor["outer"]][32:])
                names.append(doc.teams[0].nickname)
                qb = sorted((p for p in doc.players if p.record.position_name == "QB"),
                            key=lambda p: (p.record.values["depth_rank"], p.record.values["depth_side"], p.index))[0]
                qbs.append(f"{qb.first} {qb.last}")
                rosters.append(sorted(f"{p.first} {p.last}" for p in doc.players))
        row["team_names"] = tuple(names)
        row["qbs"] = dict(away=qbs[0], home=qbs[1])
        row["rosters"] = dict(away=rosters[0], home=rosters[1])
        row["new_files"] = sorted(new)
        out.append(row)
    return out


@unittest.skipUnless(HAVE_UNICORN and RETAIL_ISO.is_file(), "Unicorn and the private USA retail disc image required")
class StudioRouteMenuTests(unittest.TestCase):
    """The executable and data the Studio produces from the retail disc: moments, named venues and stock books."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_espn25_rosters as er
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_moment_venues as venues
        from mod_editor.core import nfl2k5_stock_books as books
        from mod_editor.core import nfl2k5_xbe_space as space
        from nfl2k5_historic_quick_game_native import disc_evidence
        cls.data = mm.Data.load()
        cls.resources, cls.context, cls.ids = disc_evidence(RETAIL_ISO)
        main, retail_situ = cls.resources[5], cls.resources[22]
        with hs.Source(RETAIL_ISO) as source:
            templates = {key: source.get(mm.template_for(cls.data.teams[key], mm._retail_descriptors(main))["filename"])
                         for key in cls.data.team_order()}
        cls.retail_situ = retail_situ
        from mod_editor.core import nfl2k5_espn25_fields as fields
        # the build's later field step moves eight rows to their dated stadium alternatives (stadium-index words only)
        cls.collection, _ = fields.repair_situ(mm.compile_situ(retail_situ, cls.data, main, named=True))
        cls.files = mm.compile_files(main, templates, cls.data)
        base, _ = er.apply_xbe(er.read_xbe(RETAIL_ISO))
        base, _ = space.apply(base, space.dormant_union())
        base, _ = mm.apply(base, cls.data)
        base, _ = venues.apply(base)
        cls.payload, _ = books.apply(base)
        cls.expected = with_team_facts(nat.expected_rows(retail_situ, cls.data), cls.data, cls.resources, cls.context)
        cls.order = nat.display_order_from(cls.expected)

    def cpu(self, payload=None):
        return FastMomentsCPU(payload or self.payload, self.resources, self.context, self.ids,
                              situ_chunk=self.collection[:32 + struct.unpack_from("<I", self.collection, 4)[0]],
                              extra_files=self.files)

    def test_the_built_executable_is_recognised(self):
        self.assertEqual((mm.status(self.payload, self.data), mm.row_hooks_status(self.payload, self.data)),
                         ("applied", "applied"))

    def test_all_51_entries_draw_and_open_their_own_moment(self):
        cpu = self.cpu()
        entries = [nat.resolve_entry(cpu, d, era=False) for d in range(51)]
        write_proof("studio_route", entries, self.expected, self.order)
        self.assertEqual(mismatched_rows(entries), [])
        check_entries(self, entries, self.expected, self.order, named_venues=True, era=False, books=True)


@unittest.skipUnless(HAVE_UNICORN and RETAIL_ISO.is_file() and V05_DISC.is_file(),
                     "Unicorn, the private USA retail disc image and the v0.5 disc image required")
class V05DiscMenuTests(unittest.TestCase):
    """The shipped SOFTDRINK 2K28 v0.5 disc: its own executable, situation.iff, rosters and team files."""

    @classmethod
    def setUpClass(cls):
        import hashlib
        from tools.b77 import a1_repair as repair
        cls.repair = repair
        cls.data = mm.Data.load()
        cls.tmp = tempfile.TemporaryDirectory()
        (cls.resources, cls.context, cls.ids, cls.situ_chunk, cls.extra, retail_situ) = nat.disc_inputs(
            V05_DISC, RETAIL_ISO, cls.data)
        cls.expected = with_team_facts(nat.expected_rows(retail_situ, cls.data), cls.data, cls.resources, cls.context)
        # This fixture applies only a1's XBE repair to the shipped v0.5 disc.
        # MVX's later SITU repair is absent, so keep the independently recorded
        # v0.5 selections. StudioRouteMenuTests and AnyDiscMenuTests still
        # require the current catalog's repaired selections.
        selections = json.loads((ROOT / "data/nfl2k5_moment_venue_selections.json").read_text())["selections"]
        before = {row["row"]: row["before"] for row in selections}
        for row in cls.expected:
            row["stadium"] = before[row["physical"]]
        cls.order = nat.display_order_from(cls.expected)
        from mod_editor.core import nfl2k5_espn25_rosters as er
        cls.v05 = er.read_xbe(V05_DISC)
        if hashlib.sha256(cls.v05).hexdigest() != repair.V05_XBE_SHA256:
            raise unittest.SkipTest("the v0.5 disc image has another executable than SOFTDRINK 2K28 v0.5")
        cls.fixed, cls.body = repair.repair(cls.v05)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cpu(self, payload):
        return FastMomentsCPU(payload, self.resources, self.context, self.ids, situ_chunk=self.situ_chunk,
                              extra_files=self.extra)

    def test_v05_as_shipped_shows_one_moment_and_opens_another_on_27_rows(self):
        """The bug, on the real disc: the clicks are right (every opened field is the display row's moment) but 27
        rows draw the title, date and helmets of a different moment, rows 22 to 48 of the chronological menu."""
        self.assertEqual((mm.status(self.v05, self.data), mm.row_hooks_status(self.v05, self.data)),
                         ("applied", "previous"))
        cpu = self.cpu(self.v05)
        entries = [nat.resolve_entry(cpu, d) for d in range(51)]
        write_proof("v05_as_shipped", entries, self.expected, self.order)
        bad = mismatched_rows(entries)
        self.assertEqual(bad, list(range(22, 49)))
        for entry in entries:
            want = self.expected[self.order[entry["display_row"] - 1] - 1]
            self.assertEqual(entry["opened"]["title"], want["title"])             # the click itself was right
            self.assertEqual(entry["physical"], want["physical"])
        drawn = {e["display_row"]: e["shown"]["title"]["title"] for e in entries}
        opened = {e["display_row"]: e["opened"]["title"] for e in entries}
        self.assertEqual((drawn[22], opened[22]), ("A YARD TOO SHORT", "THE MISS"))   # the example from the report
        self.assertEqual((drawn[26], opened[26]), ("THE MISS", "VINATIERI STRIKES AGAIN"))
        # the title cell asked the record getter for the raw display row
        self.assertEqual([e["shown"]["title"]["asked"] for e in entries[:3]], [[0], [1], [2]])
        self.assertEqual(entries[21]["shown"]["title"]["asked"], [21])
        self.assertEqual(entries[21]["physical"], 26)

    def test_repaired_v05_draws_and_opens_its_own_moment_on_all_51_rows(self):
        cpu = self.cpu(self.fixed)
        entries = [nat.resolve_entry(cpu, d) for d in range(51)]
        write_proof("v05_repaired", entries, self.expected, self.order)
        self.assertEqual(mismatched_rows(entries), [])
        check_entries(self, entries, self.expected, self.order, named_venues=True, era=True, books=True)

    def test_completion_marks_follow_their_moments_in_the_repaired_list(self):
        """The completed-moment test already mapped the row: a win on physical row p lights the display row of p, and
        that display row now draws p's title."""
        cpu = self.cpu(self.fixed)
        session = next(a for a in __import__("mod_editor.core.nfl2k5_xbe_space", fromlist=["x"]).layout(self.fixed)["allocations"]
                       if a["owner"] == mm.OWNER and a["kind"] == "data")["va"]
        for physical in (1, 26, 32, 50, 51):                    # retail row, saved-bit extras, session-bit extras
            cpu.w(0xBF18CC, 0)
            cpu.w(session, 0)
            cpu.win(physical - 1)
            lit = [d for d in range(51) if cpu.run(0x20C390, ecx=d)]
            self.assertEqual(lit, [self.order.index(physical)], physical)
            self.assertEqual(cpu.draw_row("title", lit[0])["title"], self.expected[physical - 1]["title"])

    def test_repair_changes_only_its_declared_bytes_and_is_idempotent(self):
        repair = self.repair
        self.assertEqual(repair.sha(self.fixed), repair.FIXED_XBE_SHA256)
        scope = self.body["scope"]
        self.assertEqual((scope["changed_bytes"], scope["declared_bytes"], scope["outside_scope_identical"]), (36, 36, True))
        self.assertEqual(len(self.fixed), len(self.v05))
        runs = [(r["raw_start"], r["raw_end"]) for r in scope["declared_ranges"]]
        for start, end in runs[:4]:
            self.assertEqual(end - start, 4)
        changed = [i for i, (a, b) in enumerate(zip(self.v05, self.fixed)) if a != b]
        self.assertTrue(all(any(start <= i < end for start, end in runs) for i in changed))
        again, replay = repair.repair(self.fixed)
        self.assertEqual((again, replay["status"]), (self.fixed, "already_repaired"))

    def test_repair_cli_refuses_foreign_input_and_never_replaces_output(self):
        repair = self.repair
        source, output = Path(self.tmp.name) / "in", Path(self.tmp.name) / "out"
        source.mkdir()
        (source / "default.xbe").write_bytes(self.v05[:-1] + bytes([self.v05[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "unexpected input hash"):
            repair.main(["--input-dir", str(source), "--output-dir", str(output)])
        self.assertFalse(output.exists())
        (source / "default.xbe").write_bytes(self.v05)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(repair.main(["--input-dir", str(source), "--output-dir", str(output)]), 0)
        self.assertEqual((output / "default.xbe").read_bytes(), self.fixed)
        receipt = json.loads((output / "a1_receipt.json").read_text())
        self.assertEqual((receipt["files"]["default.xbe"]["before_sha256"], receipt["files"]["default.xbe"]["after_sha256"]),
                         (repair.V05_XBE_SHA256, repair.FIXED_XBE_SHA256))
        self.assertEqual(receipt["touched_disc_files"], ["default.xbe"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(repair.main(["--input-dir", str(source), "--output-dir", str(output)]), 0)   # replay: same bytes
        (output / "default.xbe").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "refusing to replace"):
            repair.main(["--input-dir", str(source), "--output-dir", str(output)])
        with self.assertRaisesRegex(ValueError, "must differ"):
            repair.main(["--input-dir", str(source), "--output-dir", str(source)])

    def test_stacked_input_needs_an_explicit_hash_and_a_recognised_owner(self):
        repair = self.repair
        foreign = bytearray(self.v05)
        code, _dat = mm.allocations(self.v05)
        foreign[mm.XbeImage(self.v05).offset(code["va"] + mm.DISPLAY_MAP_OFFSET, 1)] ^= 1
        source, output = Path(self.tmp.name) / "stack_in", Path(self.tmp.name) / "stack_out"
        source.mkdir()
        (source / "default.xbe").write_bytes(bytes(foreign))
        manifest = Path(self.tmp.name) / "accepted.json"
        manifest.write_text(json.dumps({"default.xbe": repair.sha(bytes(foreign))}))
        with self.assertRaises(ValueError):          # an accepted hash does not make an unrecognised owner acceptable
            repair.main(["--input-dir", str(source), "--output-dir", str(output), "--accepted-input-hashes", str(manifest)])
        self.assertFalse(output.exists())


@unittest.skipUnless(HAVE_UNICORN and RETAIL_ISO.is_file() and os.environ.get("B77_MENU_DISC"),
                     "set B77_MENU_DISC to a SOFTDRINK 2K28 disc image (with the retail disc image present)")
class AnyDiscMenuTests(unittest.TestCase):
    """The release check: run the whole menu proof on a finished SOFTDRINK disc, e.g. the v0.6 build:
    B77_MENU_DISC=/path/to/disc.xiso.iso python3 -m unittest tests.mod_editor.test_b77_a1_menu_identity.AnyDiscMenuTests
    It expects the full SOFTDRINK build (moments, named venues, era rules, stock books)."""

    def test_all_51_entries_on_this_disc(self):
        from mod_editor.core import nfl2k5_espn25_rosters as er
        disc, data = Path(os.environ["B77_MENU_DISC"]), mm.Data.load()
        resources, context, ids, situ_chunk, extra, retail_situ = nat.disc_inputs(disc, RETAIL_ISO, data)
        expected = with_team_facts(nat.expected_rows(retail_situ, data), data, resources, context)
        order = nat.display_order_from(expected)
        payload = er.read_xbe(disc)
        self.assertEqual(mm.row_hooks_status(payload, data), "applied", "the executable lacks the row-draw hooks")
        cpu = FastMomentsCPU(payload, resources, context, ids, situ_chunk=situ_chunk, extra_files=extra)
        entries = [nat.resolve_entry(cpu, d) for d in range(51)]
        write_proof("disc_" + disc.stem[:40].replace(" ", "_"), entries, expected, order)
        self.assertEqual(mismatched_rows(entries), [])
        check_entries(self, entries, expected, order, named_venues=True, era=True, books=True)


if __name__ == "__main__":
    unittest.main()
