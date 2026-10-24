"""b778 ai7: a CPU QB Sneak / tush push is only a short-yardage call.

The native play scorer weights a one-yard QB run by *distance only* (2.4% of the plays in its formation at 1 yd,
0.48% at 2, 0.12% at 3), not by down or field position. The generator therefore keeps both plays in one
22-personnel under-centre formation, "Full House Sneak": the native 1st/2nd target is 23/13 personnel, so the
22 group is the heavy group it asks for least often, while the 3rd/4th target still reaches it on short yardage.
The 23/13 goal-line and short sets keep no sneak at all.

These tests hold on the engine alone; the generator and native-selector tests need the retail image/XBE and skip
without them. The full 500-draw CPU commit evidence is in the job report (scratch, not a unit test: the native
formation lottery can still draw the 22 group on 1st-and-1, so a small unit sample cannot prove a zero rate).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_vip as vip  # noqa: E402
from pb.v2 import generator as gen  # noqa: E402

IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE",
                          "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
HAVE_RETAIL = IMAGE.is_file() and XBE.is_file()


class EngineRuleTests(unittest.TestCase):
    def test_only_the_full_house_sneak_set_may_carry_a_sneak(self):
        self.assertIn("Full House Sneak", oc.FORMATIONS)
        spec = oc.FORMATIONS["Full House Sneak"]
        self.assertEqual((spec.personnel, spec.align), ("22", "uc"))
        self.assertTrue(gen._sneak_formation("Full House Sneak"))
        for name in ("Goal Line Sneak", "Goal Line", "I-Form Tight", "Full House", "Ace Jumbo", "Heavy Wing",
                     "Gun Doubles", "Pistol Full House", "Strong Jumbo"):
            self.assertFalse(gen._sneak_formation(name), name)

    def test_the_stack_reaches_the_backs(self):
        spec = oc.FORMATIONS["Full House Sneak"]
        design = om.tush_push(spec.context(), spec.codes())
        self.assertEqual(design.play_type, "sneak")
        self.assertEqual(len([c for c in design.chains if c]), 11)
        sneak = oc.CONCEPTS["QB Sneak"].build(spec.context())
        self.assertEqual(sneak.play_type, "sneak")

    def test_generator_must_list_has_the_sneak_set(self):
        self.assertIn("Full House Sneak", gen.MUST_FORMATIONS)

    def test_native_pool_map_matches_the_ring_rule(self):
        # Proven against the native ring reader 0x17F1D0 (see the job report): 1st/2nd -> pools 0-5, 3rd/4th
        # short -> 6-11, 3rd/4th long -> 12-17. The ring filter must allow a one-yard QB run only in 6-11.
        from mod_editor.core import nfl2k5_coach_tendencies as tend
        cases = {(1, 1): 0, (1, 2): 0, (2, 1): 0, (3, 1): 1, (3, 2): 1, (3, 3): 2, (4, 1): 1, (4, 2): 1}
        for (down, distance), distance_bin in cases.items():
            pool = tend.projected_pool(dict(down=down, ydstogo=distance, yardline_100=60,
                                            score_differential=0, qtr=2, half_seconds_remaining=300))
            self.assertIn(pool, _sneak_pools(distance_bin), (down, distance, pool))
        self.assertEqual(vip.SNEAK_POOLS, tuple(range(6, 12)))

    def test_ring_filter_replaces_a_sneak_outside_the_short_pools(self):
        choices = (
            vip.Choice(0, 1, False, False, "I-Form Tight", "QB Sneak"),
            vip.Choice(0, 2, False, False, "I-Form Tight", "RB Dive"),
            vip.Choice(0, 3, False, False, "I-Form Tight", "RB Iso"),
            vip.Choice(0, 4, False, False, "I-Form Tight", "Tush Push"),
        )
        bad = [dict(index=0, choices=[vars(c) for c in choices[:1] + choices[1:2] + choices[1:2] + choices[1:2]
                                       + choices[1:2] + choices[1:2] + choices[1:2] + choices[1:2]])]
        changes = vip.restrict_sneak_pools(bad, choices)
        self.assertTrue(changes)
        names = [c["play_name"] for c in bad[0]["choices"]]
        self.assertNotIn("QB Sneak", names)
        good = [dict(index=11, choices=[vars(c) for c in choices[:1] + choices[1:2] + choices[1:2] + choices[1:2]
                                        + choices[1:2] + choices[1:2] + choices[1:2] + choices[1:2]])]
        self.assertEqual(vip.restrict_sneak_pools(good, choices), [])


def _sneak_pools(distance_bin):
    return {0: (0, 1, 2), 1: vip.SNEAK_POOLS, 2: (12, 13, 14, 15, 16, 17)}[distance_bin]


@unittest.skipUnless(HAVE_RETAIL, "retail image and XBE are required for the generator check")
class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        gen.build_league(IMAGE, ["TEN"], xbe=XBE, out_dir=cls.out, fit_iters=0, progress=lambda *_: None)
        cls.doc = json.loads((cls.out / "softdrink_ten_modern.2k5book").read_text(encoding="utf-8"))
        cls.names = {p["id"]: p["custom_name"] for p in cls.doc["plays"]}
        cls.forms = {f["id"]: f for f in cls.doc["formations"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_sneak_link_is_in_the_full_house_sneak(self):
        hits = []
        for fid, menu in self.doc["menus"].items():
            for pid in menu:
                if self.names[pid] in ("QB Sneak", "Tush Push"):
                    hits.append((self.forms[fid]["custom_name"], self.names[pid]))
        self.assertTrue(hits, "the generated book lost both one-yard QB runs")
        self.assertEqual({name for name, _play in hits}, {"Full House Sneak"}, hits)
        for fid, form in self.forms.items():
            if form["custom_name"] == "Full House Sneak":
                self.assertIn("Tush Push", [self.names[p] for p in self.doc["menus"][fid]])
                self.assertIn("QB Sneak", [self.names[p] for p in self.doc["menus"][fid]])

    def test_old_sets_have_no_sneak(self):
        for form in self.doc["formations"]:
            if form["custom_name"] in ("Goal Line Sneak", "Goal Line", "I-Form Tight", "Full House", "Ace Jumbo"):
                menu = [self.names[p] for p in self.doc["menus"][form["id"]]]
                self.assertNotIn("QB Sneak", menu, form["custom_name"])
                self.assertNotIn("Tush Push", menu, form["custom_name"])


@unittest.skipUnless(HAVE_RETAIL, "retail image and XBE are required for the native check")
class NativeRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Unicorn is required for the native play selector")
        from mod_editor.core import nfl2k5_playbook_pack as packs
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        gen.build_league(IMAGE, ["TEN"], xbe=XBE, out_dir=out, fit_iters=0, progress=lambda *_: None)
        retail = None
        with OuterImage(IMAGE) as image:
            retail = image.read_entry(BOOK_ENTRIES["TEN"])
        pack = packs.load_pack(out / "softdrink_ten_modern.2k5book")
        cls.book = packs.apply_pack_to_resource(retail, pack, asset_id="book:TEN", xbe=XBE.read_bytes()).replacement

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def machine(self):
        from pb.scoring_selectors import World
        from mod_editor.core import nfl2k5_play_scoring as scoring
        from mod_editor.core import nfl2k5_playbook_inspector as insp
        w = World(XBE.read_bytes())
        w.load(self.book)
        for team in (scoring.TEAM, w.defense):
            record = w.get(team + 0xC)
            w.m.mem_write(record + 0x2C, bytes(0x30))
            w.call(0x204C80, eax=team)
        book = insp.parse_playbook_resource(self.book)
        name = {p.index: p.name.strip() for p in book.plays}
        form = next(f.index for f in book.formations if f.name.strip() == "Full House Sneak")
        body = self.book[insp.RESOURCE_HEADER_SIZE:]
        category = next(c.index for c in book.categories
                        if body[insp.CATEGORY_BASE + c.index * insp.CATEGORY_SIZE + 4] & 0x3F == 2)
        return w, name, form, category

    def test_one_yard_sneaks_only_at_one_yard(self):
        from mod_editor.core import nfl2k5_play_scoring as scoring
        from mod_editor.core import nfl2k5_playbook_inspector as insp
        w, name, form, category = self.machine()
        fv = scoring.BOOK + insp.FORMATION_BASE + form * insp.FORMATION_SIZE
        cv = scoring.BOOK + insp.CATEGORY_BASE + category * insp.CATEGORY_SIZE

        def sample(down, distance, draws=4000):
            got = 0
            for i in range(draws):
                w.configure(down=down, distance=distance, yard=40)
                w.fput(0xBF16F8, .5)
                ret = w.call(0x2096A0, ecx=scoring.TEAM, edx=8, args=(fv, cv, 0))
                pi = (ret - scoring.BOOK - insp.PLAY_BASE) // 96 if ret else None
                if name.get(pi, "").casefold() in ("qb sneak", "tush push"):
                    got += 1
            return got

        self.assertGreater(sample(3, 1), 0, "the allowed 3rd-and-1 sneak disappeared")
        self.assertGreater(sample(4, 1), 0, "the allowed 4th-and-1 sneak disappeared")
        self.assertEqual(sample(3, 3), 0, "a 3rd-and-3 sneak is possible")
        self.assertEqual(sample(3, 2), 0, "a 3rd-and-2 sneak is possible")


if __name__ == "__main__":
    unittest.main()
