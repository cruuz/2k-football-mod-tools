"""Composed Never call and scheme/clone workflows on authored book bytes."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_formation_calling as calling
from tests.mod_editor import test_apf_b69_schemes as fixtures


class CloneRetirementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SchemeSessionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.addCleanup(self.fixture.doCleanups)
        self.facade = self.fixture.facade
        book = bytearray(self.fixture.backend.initial.books["O-ManBlock"])
        book[0x120:0x1D0] = book[0x70:0x120]
        word = struct.unpack_from(">I", book, 0x1C8)[0]
        struct.pack_into(">I", book, 0x1C8, word | (1 << 24))
        original = splb._compact_normalize(bytes(book))
        self.fixture.backend.initial.books["O-ManBlock"] = original
        self.masks = list(calling.membership_masks(original, 0))
        self.fixture.stage(dict(kind="never_call", book="O-ManBlock", formation=0,
                                never=True, restore_masks=self.masks))

    def test_scheme_clone_retains_restore_masks_across_save_reopen(self):
        self.fixture.stage(self.facade.playcalling_scheme_plan(0, "pro_spread"))
        saved = self.facade.session.save_project(self.fixture.root / "cloned.apf2k8mod")
        self.facade.undo()
        self.facade.session.load_project(saved)
        context = self.facade.playcalling_context()
        formation = next(row for row in context["formations"] if row["id"] == 0)
        self.assertTrue(formation["never_call"])
        self.assertEqual(formation["restore_masks"], self.masks)
        self.fixture.stage(dict(kind="never_call", book=context["book"], formation=0,
                                never=False, restore_masks=formation["restore_masks"]))
        state = self.facade.playcalling_context()["state"]
        self.assertEqual(calling.membership_masks(state.books[context["book"]], 0), tuple(self.masks))
        self.assertEqual(calling.membership_masks(state.books["O-ManBlock"], 0), (0,))
        self.facade.undo()
        self.assertTrue(next(row for row in self.facade.playcalling_context()["formations"]
                             if row["id"] == 0)["never_call"])

    def test_explicit_clone_uses_donor_state_at_copy_time(self):
        self.fixture.stage(self.facade.playcalling_plan("offense", 0, "O-ManBlock"))
        self.fixture.stage(dict(kind="never_call", book="O-ManBlock", formation=0,
                                never=False, restore_masks=self.masks))
        context = self.facade.playcalling_context()
        formation = next(row for row in context["formations"] if row["id"] == 0)
        self.assertTrue(formation["never_call"])
        self.assertEqual(formation["restore_masks"], self.masks)
        self.fixture.stage(dict(kind="never_call", book=context["book"], formation=0,
                                never=False, restore_masks=formation["restore_masks"]))
        state = self.facade.playcalling_context()["state"]
        for name in (context["book"], "O-ManBlock"):
            self.assertEqual(calling.membership_masks(state.books[name], 0), tuple(self.masks))


if __name__ == "__main__":
    unittest.main()
