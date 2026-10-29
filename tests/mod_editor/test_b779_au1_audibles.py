"""b779 au1: audibles at the line.

Ju3tin, 10/27: "When in game and your at the line looking through the audible plays you crash"; "It seems like the new
formations and plays, don't have working audibles". The PLAY body header table at 0x4C is ten (formation, menu slot)
pairs: entries 0-4 are the offense's No Huddle buttons (b778 pb7), entries 5-9 the defense's audibles at the line
(0xFEE70 opens a five-button panel for a non-special defensive formation; 0xFEFA0 -> 0xFF0B2 reads entry 5 + button).
Every retail entry 5-9 names a coverage. The SOFTDRINK defense packs rebuild the defensive menus, where fronts and
coverages interleave, but kept those bytes, so 16 v0.7 club books pointed a defensive audible at a front (TEN: Bear 46
menu slot 28, "Bear Pinch"). The defense pack compiler now re-seats such an entry on the nearest coverage of the same
formation, the compiler refuses a writer that breaks a sound audible, and the Build's final book gate refuses any
dangling audible on the image.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402

IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE",
                          "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
HAVE_RETAIL = IMAGE.is_file() and XBE.is_file()
BASE = 32 + packs.AUDIBLE_TABLE


def retail_books():
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(IMAGE) as image:
        return {name: image.read_entry(index) for name, index in BOOK_ENTRIES.items()}


def slot_play(raw, fi, slot):
    return struct.unpack_from("<H", raw, 32 + insp.FORMATION_AUX_BASE + fi * insp.FORMATION_AUX_SIZE + 2 * slot)[0] & 0x1FF


def component(raw, play):
    return lib.defense_component(lib.decoded_chains(raw[32:], play))


@unittest.skipUnless(HAVE_RETAIL, "Retail image / executable unavailable")
class AudibleTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.books = retail_books()

    def test_every_retail_book_is_sound(self):
        self.assertEqual(len(self.books), 37)
        for name, raw in self.books.items():
            with self.subTest(book=name):
                self.assertEqual(packs.audible_table_problems(raw, book_name=name), [])
        # The exemption is only for the two books retail ships with offense plays in the defensive half.
        self.assertTrue(packs.audible_table_problems(self.books["PRACTICE"]))
        self.assertTrue(packs.audible_table_problems(self.books["reference"]))

    def test_a_front_in_the_defensive_half_is_refused_and_repaired_to_the_nearest_coverage(self):
        raw = bytearray(self.books["TEN"])
        fi, slot = raw[BASE + 16], raw[BASE + 17]          # defensive audible 3 (button L): retail Bear, slot 28
        fronts = [s for s in range(36) if slot_play(raw, fi, s) != 0x1FF and component(raw, slot_play(raw, fi, s)) == "front"]
        self.assertTrue(fronts)
        raw[BASE + 17] = fronts[0]
        before = bytes(raw)
        problems = packs.audible_table_problems(before, book_name="TEN")
        self.assertEqual(len(problems), 1)
        self.assertIn("defense audible 3", problems[0])
        self.assertIn("front", problems[0])
        moves = packs.repair_defense_audibles(raw)
        self.assertEqual(len(moves), 1)
        new = raw[BASE + 17]
        self.assertEqual(component(raw, slot_play(raw, fi, new)), "coverage")
        coverage = [s for s in range(36) if slot_play(raw, fi, s) != 0x1FF
                    and component(raw, slot_play(raw, fi, s)) in ("coverage", "full")]
        self.assertEqual(abs(new - fronts[0]), min(abs(s - fronts[0]) for s in coverage))
        changed = [i for i, (a, b) in enumerate(zip(before, raw)) if a != b]
        self.assertEqual(changed, [BASE + 17])               # one byte: nothing else moves
        self.assertEqual(packs.audible_table_problems(bytes(raw), book_name="TEN"), [])
        self.assertEqual(packs.repair_defense_audibles(raw), [])  # idempotent

    def test_offense_half_and_sound_entries_are_never_touched(self):
        for name in ("TEN", "KC", "GEN"):
            raw = bytearray(self.books[name])
            self.assertEqual(packs.repair_defense_audibles(raw), [])
            self.assertEqual(bytes(raw), self.books[name])
        raw = bytearray(self.books["TEN"])
        raw[BASE + 16] = 0                                     # formation 0 is an offensive formation
        with self.assertRaises(packs.PlaybookPackError):
            packs.repair_defense_audibles(raw)


@unittest.skipUnless(HAVE_RETAIL, "Retail image / executable unavailable")
class ShippedBooks(unittest.TestCase):
    """The shipped SOFTDRINK offense + defense packs on retail TEN and ARZ through the Build's book tail."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("NFL2K5_SCORING_XBE", str(XBE))
        cls.books = retail_books()

    def packs_for(self, team):
        from pb.v2.build import pack_path
        return (packs.load_pack(pack_path(team)),
                packs.load_pack(ROOT / f"data/playbooks/softdrink_{team.lower()}_defense.2k5book"))

    def test_shipped_books_have_no_dangling_audible(self):
        from pb.v2 import compose
        expected = {"TEN": [(3, 25, 28, 26)], "ARZ": [(2, 26, 15, 14), (3, 27, 16, 15)]}
        for team, want in expected.items():
            with self.subTest(team=team):
                offense, defense = self.packs_for(team)
                final, _receipt, _a, b = compose.compose(team, self.books[team], offense, defense)
                self.assertEqual(packs.audible_table_problems(final, book_name=team), [])
                moves = b.report.get("defense_audibles")
                self.assertEqual([(m["audible"], m["formation"], m["old_slot"], m["slot"]) for m in moves], want)
                for m in moves:
                    self.assertEqual(component(final, m["play"]), "coverage")
                    self.assertEqual(component(final, m["old_play"]), "front")

    def test_without_the_repair_the_defense_compile_is_refused(self):
        """The v0.7 behaviour (the header kept while the menus moved) now fails the compile."""
        offense, defense = self.packs_for("TEN")
        after_offense = packs.apply_pack_to_resource(self.books["TEN"], offense, asset_id="book:TEN").replacement
        with mock.patch.object(packs, "_keep_defense_audibles", lambda compiled, source: compiled):
            with self.assertRaisesRegex(packs.PlaybookPackError, "audible"):
                packs.apply_pack_to_resource(after_offense, defense, asset_id="book:TEN")


class BuildGate(unittest.TestCase):
    """mod_build's final book gate reads every PLAY on the image and refuses a dangling audible."""

    def run_gate(self, books):
        from mod_editor.core import mod_build
        recode = packs._outer_image()

        class Archive:
            def __init__(self, _target):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def entries_with_head(self, head):
                return [type("E", (), {"index": index})() for index in books]

            def read_entry(self, index):
                return books[index]

        fake = type("Recode", (), {"OuterImage": Archive, "BOOK_ENTRIES": recode.BOOK_ENTRIES})
        inspector = mod_build._core_module("nfl2k5_playbook_inspector")
        with mock.patch.object(packs, "_outer_image", lambda: fake), \
                mock.patch.object(inspector, "playcall_ui_problems", lambda raw: []), \
                mock.patch.object(inspector, "category_menu_problems", lambda raw: []):
            return mod_build._check_playbook_menus(Path("image"), lambda *a: None)

    @unittest.skipUnless(HAVE_RETAIL, "Retail image / executable unavailable")
    def test_gate_refuses_a_front_audible_and_exempts_only_practice_and_reference(self):
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        retail = retail_books()
        self.assertEqual(self.run_gate({BOOK_ENTRIES[n]: retail[n] for n in ("TEN", "PRACTICE", "reference")}),
                         {"books": 3, "problems": 0})
        broken = bytearray(retail["TEN"])
        fi = broken[BASE + 16]
        broken[BASE + 17] = next(s for s in range(36) if slot_play(broken, fi, s) != 0x1FF
                                 and component(broken, slot_play(broken, fi, s)) == "front")
        with self.assertRaisesRegex(RuntimeError, "defense audible 3"):
            self.run_gate({BOOK_ENTRIES["TEN"]: bytes(broken)})
        # The PRACTICE exemption is by archive entry, not by content: the same bytes elsewhere are refused.
        with self.assertRaisesRegex(RuntimeError, "defense audible"):
            self.run_gate({4500: retail["PRACTICE"]})


if __name__ == "__main__":
    unittest.main()
