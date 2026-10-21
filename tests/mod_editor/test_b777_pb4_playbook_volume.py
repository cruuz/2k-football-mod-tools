"""b777 pb4: more plays per book (menu links), the slot rule, role-preserving sharing, no duplicate plays.

PROVED OFFLINE on the shipped packs and catalogs (pb/v2/catalogs); the composed-book gate is pb/v2/rules_b777.py
(its receipt pb/v2/receipts/rules-b777.json is checked here when present).  Gameplay is unwitnessed.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import generator as gen  # noqa: E402

_CAP = json.loads((ROOT / "pb/v2/receipts/capacity-b777-before.json").read_text())["sets"]
RETAIL_LINKS = {t: r["offense_links"] for t, r in _CAP["books_retail"]["teams"].items()}
V3_LINKS = {t: r["offense_links"] for t, r in _CAP["books_v3"]["teams"].items()}      # pb1's b776 books


class SlotRuleTests(unittest.TestCase):
    def test_known_formations(self):
        self.assertEqual(gen.slot_rule_violations(oc.FORMATIONS["Gun Doubles"]), [])
        self.assertEqual(gen.slot_rule_violations(oc.FORMATIONS["Gun Spread"]), [])
        self.assertTrue(gen.slot_rule_violations(oc.FORMATIONS["Wing T"]))         # Z on the wing
        self.assertTrue(gen.slot_rule_violations(oc.FORMATIONS["Strong I Twins"]))  # Z inside X

    def test_alignment_classes(self):
        ctx = oc.FORMATIONS["Gun Doubles"].context()
        classes = Counter(gen._side_rank(ctx, p) for p in ctx.players if p.kind in (oc.WR, oc.TE, oc.HB))
        self.assertEqual(classes["outside"], 2)
        self.assertEqual(classes["back"], 1)


class ShippedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text())
        cls.version = manifest["version"]
        cls.packs = {r["team"]: packs.load_pack(ROOT / r["pack"]) for r in manifest["teams"]}
        cls.catalogs = {t: json.loads((ROOT / f"pb/v2/catalogs/{t}.json").read_text()) for t in cls.packs}

    def test_version_and_every_team(self):
        self.assertEqual(self.version, gen.VERSION)
        self.assertEqual(set(self.packs), set(packs.TEAM_BOOKS))

    def test_more_plays_than_retail_and_v3(self):
        total = 0
        for team, pk in self.packs.items():
            links = sum(len(m) for _f, m in pk.menus)
            total += links
            with self.subTest(team=team):
                self.assertGreater(links, RETAIL_LINKS[team])
                self.assertGreaterEqual(links, V3_LINKS[team])
        self.assertGreaterEqual(total, 1.7 * sum(RETAIL_LINKS.values()))

    def test_menus(self):
        for team, pk in self.packs.items():
            for fid, menu in pk.menus:
                with self.subTest(team=team, formation=fid):
                    self.assertEqual(len(menu) % 3, 0)
                    self.assertLessEqual(len(menu), insp.FORMATION_PLAY_LINKS)
                    self.assertEqual(len(set(menu)), len(menu))

    def test_slot_rule_is_rare(self):
        for team, cat in self.catalogs.items():
            bad = [f for f in cat["formations"] if gen.slot_rule_violations(oc.FORMATIONS[f["formation"]])]
            total = sum(len(f["menu"]) for f in cat["formations"])
            with self.subTest(team=team):
                self.assertLessEqual(len(bad), gen.SLOT_RULE_HARD_MAX, [f["formation"] for f in bad])
                self.assertLessEqual(sum(len(f["menu"]) for f in bad), 0.08 * total)

    def test_mesh_capped(self):
        for team, cat in self.catalogs.items():
            mesh = [r for r in cat["plays"] if "Mesh" in r["name"] or "Mesh" in (r.get("concept") or "")]
            with self.subTest(team=team):
                self.assertLessEqual(len(mesh), gen.MESH_RECORDS_MAX)
                self.assertTrue(all(len(r["formations"]) <= gen.LIMITED_SHARE for r in mesh))

    def test_composed_gate_receipt(self):
        path = ROOT / "pb/v2/receipts/rules-b777.json"
        if not path.exists():
            self.skipTest("composed-book gate receipt not written")
        doc = json.loads(path.read_text())
        self.assertEqual(doc["summary"]["failures"], [])
        for team, row in doc["teams"].items():
            with self.subTest(team=team):
                self.assertEqual(row["duplicate_plays"], 0)
                self.assertEqual(row["bad_menus"], [])


if __name__ == "__main__":
    unittest.main()
