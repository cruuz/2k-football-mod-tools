"""b780 plays2 (Q18): every offense formation lists a run and a pass.

HUNT8 found 94 run-less and 28 pass-less formations in the 32 shipped offense packs; the native play lottery 0x2096A0
returned one fixed pass for a run-less formation at run share 1.0.  ``pb/v2/run_pass_floor.py`` fixed the packs, the
generator calls it on every pack it builds, and ``nfl2k5_playbook_lint`` fails FORMATION_NO_RUN / FORMATION_NO_PASS.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import run_pass_floor as floor  # noqa: E402

PACKS = sorted((ROOT / "data/playbooks").glob("softdrink_*_modern.2k5book"))
IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", ""))


def load(team_pack: Path):
    doc = json.loads(team_pack.read_text(encoding="utf-8"))
    cat = json.loads((ROOT / "pb/v2/catalogs" / f"{doc['book']['team']}.json").read_text(encoding="utf-8"))
    return doc, cat


class CoverageRuleTests(unittest.TestCase):
    def test_codes_are_errors_with_a_goal(self):
        for code in ("FORMATION_NO_RUN", "FORMATION_NO_PASS"):
            self.assertEqual(lint.SEVERITY[code], "error")
            self.assertEqual(lint.GOAL_IDS[code], "Q18")

    def test_a_menu_without_a_run_or_a_pass_is_flagged(self):
        found = lint.coverage_findings([(3, "Pistol Wing", 0, 12), (4, "Full House", 3, 0), (5, "Gun Doubles", 4, 8)])
        self.assertEqual([(f.code, f.formation_name) for f in found],
                         [("FORMATION_NO_RUN", "Pistol Wing"), ("FORMATION_NO_PASS", "Full House")])

    def test_retail_own_run_less_sets_are_exempt_and_nothing_is_exempt_from_a_pass(self):
        rows = [(0, "Hail Mary", 0, 3), (1, " Gun: Straight ", 0, 9), (2, "Gun: Straight Trips", 0, 9)]
        self.assertEqual(lint.coverage_findings(rows), [])
        self.assertEqual([f.code for f in lint.coverage_findings([(0, "Hail Mary", 0, 0)])], ["FORMATION_NO_PASS"])

    def test_pack_coverage_names_the_formation_that_lost_its_runs(self):
        doc, cat = load(next(p for p in PACKS if p.name == "softdrink_bal_modern.2k5book"))
        plays = {p["id"]: p for p in doc["plays"]}
        fid = next(f["id"] for f in doc["formations"] if f["custom_name"] == "Singleback Ace")
        passes = [p for p in doc["menus"][fid] if floor.kind_of(int(plays[p]["play_flags"])) == "pass"]
        self.assertGreaterEqual(len(passes), 3)
        doc["menus"][fid] = passes[: len(passes) // 3 * 3]
        found = lint.pack_coverage(packs.loads_pack(json.dumps(doc)))
        self.assertEqual([(f.code, f.formation_name) for f in found], [("FORMATION_NO_RUN", "Singleback Ace")])

    @unittest.skipUnless(IMAGE.is_file(), "needs the retail image")
    def test_retail_club_books_are_clean(self):
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES, OuterImage
        with OuterImage(IMAGE) as image:
            for team in ("BUF", "IND", "BAL"):          # BUF and IND carry retail's two run-less "Gun: Straight" sets
                self.assertEqual(lint.resource_coverage(image.read_entry(BOOK_ENTRIES[team])), [], team)

    def test_utility_books_are_skipped(self):
        self.assertIn("reference", lint.UTILITY_BOOKS)


class ShippedPacksTests(unittest.TestCase):
    def test_every_shipped_pack_has_a_run_and_a_pass_in_every_menu(self):
        self.assertEqual(len(PACKS), 32)
        for path in PACKS:
            pack = packs.load_pack(path)
            self.assertEqual(lint.pack_coverage(pack), [], path.name)

    def test_menus_keep_the_page_rule_and_the_format_limits(self):
        for path in PACKS:
            doc, _cat = load(path)
            names = {f["id"]: f["custom_name"] for f in doc["formations"]}
            for fid, menu in doc["menus"].items():
                self.assertEqual(len(menu) % 3, 0, (path.name, names[fid], len(menu)))
                self.assertTrue(3 <= len(menu) <= insp.FORMATION_PLAY_LINKS, (path.name, names[fid], len(menu)))
                self.assertEqual(len(menu), len(set(menu)))
            self.assertLessEqual(len(doc["plays"]), 270)
            self.assertEqual(floor.short_formations(doc), [], path.name)

    def test_the_floor_tool_has_nothing_left_to_do(self):
        self.assertEqual(floor.main(["--check"]), 0)
        for path in PACKS:
            doc, cat = load(path)
            before = copy.deepcopy(doc["menus"])
            self.assertEqual(floor.fix_doc(doc, cat), [], path.name)
            self.assertEqual(doc["menus"], before)

    def test_manifests_follow_the_packs(self):
        manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text(encoding="utf-8"))
        from pb.v2 import generator as gen
        for row in manifest["teams"]:
            pack = packs.load_pack(ROOT / row["pack"])
            self.assertEqual(row["links"], sum(len(m) for _f, m in pack.menus), row["team"])
            self.assertEqual(row["semantic_sha256"], gen.semantic_digest(packs.loads_pack(pack.dumps())), row["team"])

    def test_catalog_menus_name_the_pack_menus(self):
        for path in PACKS:
            doc, cat = load(path)
            plays = {p["id"]: p for p in doc["plays"]}
            rows = {r["formation"]: r for r in cat["formations"]}
            for form in doc["formations"]:
                self.assertEqual(rows[form["custom_name"]]["menu"],
                                 [plays[p]["custom_name"] for p in doc["menus"][form["id"]]], (path.name, form["custom_name"]))


class FloorToolTests(unittest.TestCase):
    def strip_runs(self, team_pack: str, formation: str):
        doc, cat = load(next(p for p in PACKS if p.name == team_pack))
        plays = {p["id"]: p for p in doc["plays"]}
        fid = next(f["id"] for f in doc["formations"] if f["custom_name"] == formation)
        passes = [p for p in doc["menus"][fid] if floor.kind_of(int(plays[p]["play_flags"])) == "pass"]
        doc["menus"][fid] = passes[: len(passes) // 3 * 3]
        self.assertEqual(floor.short_formations(doc), [(fid, "run")])
        return doc, cat, fid, plays

    def test_a_run_less_set_takes_a_page_of_sister_runs(self):
        doc, cat, fid, plays = self.strip_runs("softdrink_bal_modern.2k5book", "Singleback Ace")
        before = len(doc["menus"][fid])
        changes = floor.fix_doc(doc, cat)
        self.assertEqual([c["status"] for c in changes], ["ok"])
        menu = doc["menus"][fid]
        self.assertEqual(len(menu) % 3, 0)
        self.assertEqual(floor.short_formations(doc), [])
        added = [p for p in menu if floor.kind_of(int(plays[p]["play_flags"])) == "run"]
        self.assertTrue(added)
        forms = {f["id"]: f for f in doc["formations"]}
        for pid in added:                                  # a link, never a new record: another menu already lists it
            self.assertTrue(any(pid in m for g, m in doc["menus"].items() if g != fid), pid)
        self.assertEqual(len(doc["plays"]), len({p["id"] for p in doc["plays"]}))
        self.assertGreaterEqual(len(menu), before)
        # every link is lint clean as the Studio compiler writes it
        self.assertEqual(lint.lint_pack(packs.loads_pack(json.dumps(doc)), studio_rules=True).counts(), {})
        self.assertIn(forms[fid]["custom_name"], {f["formation"] for f in cat["formations"]})

    def test_a_pass_less_set_gets_a_pass_and_keeps_its_sneaks(self):
        doc, cat = load(next(p for p in PACKS if p.name == "softdrink_bal_modern.2k5book"))
        plays = {p["id"]: p for p in doc["plays"]}
        fid = next(f["id"] for f in doc["formations"] if f["custom_name"] == "Full House Sneak")
        runs = [p for p in doc["menus"][fid] if floor.kind_of(int(plays[p]["play_flags"])) == "run"]
        doc["menus"][fid] = runs
        self.assertEqual(floor.short_formations(doc), [(fid, "pass")])
        floor.fix_doc(doc, cat)
        self.assertEqual(floor.short_formations(doc), [])
        names = [plays[p]["custom_name"] for p in doc["menus"][fid]]
        self.assertIn("Tush Push", names)
        self.assertIn("QB Sneak", names)
        self.assertEqual(len(doc["menus"][fid]) % 3, 0)

    def test_no_huddle_links_survive(self):
        for path in PACKS:
            doc, _cat = load(path)
            for fid, pid in doc.get("no_huddle", []):
                self.assertIn(pid, doc["menus"][fid], path.name)

    def test_the_generator_runs_the_floor(self):
        source = (ROOT / "pb/v2/generator.py").read_text(encoding="utf-8")
        self.assertIn("floor.fix_doc(doc, catalog", source)
        self.assertIn("formations still without a run or a pass", source)


class CatalogConsistencyTests(unittest.TestCase):
    def test_converted_records_are_catalogued_as_designed_for_their_formation(self):
        converted = Counter()
        for path in PACKS:
            doc, cat = load(path)
            rows = {r["play"]: r for r in cat["plays"]}
            plays = {p["id"]: p for p in doc["plays"]}
            for row in cat["plays"]:
                if row.get("added_by") == "b780 plays2":
                    converted[path.name] += 1
                    p = plays[row["play"]]
                    self.assertEqual(row["name"], p["custom_name"])
                    self.assertEqual(row["play_type"], p["play_type"])
                    self.assertIn(row["home"], row["formations"])
                    self.assertEqual((p["play_flags"] & 0x1FF), (p["donor"]["flags"] & 0x1FF))
            self.assertEqual({r["play"] for r in cat["plays"]}, set(plays) - {"fgfake"}, path.name)
        self.assertTrue(converted)


if __name__ == "__main__":
    unittest.main()
