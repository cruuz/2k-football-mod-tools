"""b780-b13: the Crib "Trophy Room only" cut is a visible, working and plainly worded Studio toggle.

Noah 10/22: "The only thing I want in the crib is the trophy room that shows your awards." Noah 10/28: "Crib stays trophy
room (toggle later)". All three SOFTDRINK presets tick the cut, so a person who builds their own disc has to be able to
find the one check box that undoes it, understand what it does, and trust that unticking it really leaves the Crib whole.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication, QGroupBox  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402
from mod_editor.core import nfl2k5_crib_trophy_room as crib  # noqa: E402
from mod_editor.gui import build_panel_qt  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE  # noqa: E402

PRESETS = ("softdrink_basic", "softdrink_advanced", "softdrink_experimental")
EM_DASH = "—"


def _disc_state(**overrides):
    """What the Build tab learns from a plain retail disc image, for the one option under test."""
    state = {"container": "xiso", "path": "retail.xiso.iso", "crib_trophy_room": "retail"}
    state.update(overrides)
    return state


def _group_title(widget):
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QGroupBox):
            return parent.title()
        parent = parent.parentWidget()
    return None


class CribToggleInTheBuildTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = BuildPanel()
        self.addCleanup(self.panel.deleteLater)

    def test_the_cut_is_a_real_check_box_in_the_gameplay_group(self):
        box = self.panel.crib_trophy_room_check
        self.assertEqual(box.text(), crib.BUILD_CAPTION)
        self.assertEqual(_group_title(box), "Gameplay")
        self.assertIn("crib_trophy_room", build_panel_qt.BUILD_KEYS)
        # the Crib name is its own option, in the Franchise group (the preset note and the FAQ say so)
        self.assertEqual(_group_title(self.panel.trophy_room_check), "Franchise")
        self.assertNotEqual(self.panel.trophy_room_check.text(), box.text())

    def test_every_preset_ticks_it_and_the_note_next_to_the_presets_says_so(self):
        self.panel.apply_state(_disc_state())
        self.assertTrue(self.panel.crib_trophy_room_check.isEnabled())
        for name in PRESETS:
            with self.subTest(preset=name):
                self.assertTrue(mod_build.PRESETS[name]["crib_trophy_room"])
                self.panel.crib_trophy_room_check.setChecked(False)
                self.panel.apply_preset(name)
                self.assertTrue(self.panel.crib_trophy_room_check.isChecked())
                self.assertTrue(self.panel.plan().crib_trophy_room)
                self.assertIn(crib.BUILD_CAPTION, self.panel.selected_labels())
        note = self.panel.preset_crib_note
        self.assertIs(note.parentWidget().__class__.__name__ == "QGroupBox", True)
        self.assertTrue(note.wordWrap())
        self.assertEqual(note.text(), build_panel_qt.PRESET_CRIB_NOTE)
        self.assertIn(crib.BUILD_CAPTION, note.text())      # the exact words of the box that undoes it
        self.assertIn("Gameplay", note.text())              # where that box is
        self.assertIn("All three presets", note.text())
        self.assertNotIn(EM_DASH, note.text())

    def test_unticking_after_a_preset_turns_the_cut_off_in_the_plan_the_labels_and_the_saved_project(self):
        self.panel.apply_state(_disc_state())
        self.panel.apply_preset("softdrink_basic")
        self.assertIs(self.panel.project_build_settings()["crib_trophy_room"], True)
        self.panel.crib_trophy_room_check.setChecked(False)
        plan = self.panel.plan()
        self.assertIs(plan.crib_trophy_room, False)
        self.assertNotIn(crib.BUILD_CAPTION, self.panel.selected_labels())
        saved = self.panel.project_build_settings()
        self.assertIs(saved["crib_trophy_room"], False)
        # the choice survives a save and a reopen, in both directions
        self.panel.crib_trophy_room_check.setChecked(True)
        self.panel.restore_project_build_settings(saved)
        self.assertIs(self.panel.plan().crib_trophy_room, False)
        self.assertIs(build_settings.build_settings(saved)["crib_trophy_room"], False)
        self.panel.restore_project_build_settings({**saved, "crib_trophy_room": True})
        self.assertIs(self.panel.plan().crib_trophy_room, True)

    def test_a_disc_that_already_has_the_cut_says_so_instead_of_offering_it_again(self):
        self.panel.apply_state(_disc_state(crib_trophy_room="applied"))
        box = self.panel.crib_trophy_room_check
        self.assertFalse(box.isEnabled())
        self.assertFalse(box.isChecked())
        self.assertEqual(self.panel._badges["crib_trophy_room"].text(), "Already installed")

    def test_a_bare_executable_cannot_take_it_because_the_cut_needs_the_whole_disc(self):
        self.panel.apply_state({"container": "xbe", "path": "default.xbe", "crib_trophy_room": "retail"})
        self.assertFalse(self.panel.crib_trophy_room_check.isEnabled())
        self.assertEqual(self.panel._badges["crib_trophy_room"].text(), "Full disc required")


class CribOptionWords(unittest.TestCase):
    def test_caption_and_help_say_what_it_removes_that_presets_tick_it_and_how_to_undo_it(self):
        text = crib.HELP_TEXT
        for needle in ("only the room, your trophies, User Card and Milestone Info", "Catalogs and Crib Items",
                       "Your save is not changed", "All three presets tick this", "Untick it to keep the whole Crib",
                       "The Crib is now the Trophy Room"):
            self.assertIn(needle, text)
        for words in (crib.BUILD_CAPTION, text, build_panel_qt.PRESET_CRIB_NOTE):
            self.assertNotIn(EM_DASH, words)
            self.assertNotIn("–", words)
        self.assertLessEqual(len(crib.BUILD_CAPTION), 70)   # a check box label, not a paragraph

    def test_the_caption_is_unique_so_the_note_and_the_faq_name_exactly_one_box(self):
        captions = [row[1] for row in build_panel_qt.BUILD_OPTIONS]
        self.assertEqual(captions.count(crib.BUILD_CAPTION), 1)


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class UntickingReallyKeepsTheCrib(unittest.TestCase):
    """Through the real build entry point: the flag decides, and nothing else does."""

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()

    def _build(self, flag):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            shutil.copyfile(XBE, source)
            target = Path(tmp) / f"out-{flag}.xbe"
            plan = mod_build.BuildPlan(str(source), str(target), crib_trophy_room=flag)
            receipt = mod_build.build(plan, progress=lambda *args, **kwargs: None)
            return target.read_bytes(), receipt

    def test_off_leaves_the_whole_crib_and_on_cuts_it_with_the_same_plan_otherwise(self):
        off, off_receipt = self._build(False)
        self.assertEqual(off, self.retail)                                  # every Crib byte is retail
        self.assertEqual(crib.status(off), "retail")
        self.assertEqual(off_receipt["result"]["crib_trophy_room"], "retail")
        self.assertNotIn("crib_trophy_room", [step["step"] for step in off_receipt["steps"]])
        on, on_receipt = self._build(True)
        self.assertEqual(crib.status(on), "applied")
        self.assertEqual(on_receipt["result"]["crib_trophy_room"], "applied")
        self.assertIn("crib_trophy_room", [step["step"] for step in on_receipt["steps"]])
        self.assertNotEqual(on, self.retail)

    def test_the_cut_keeps_the_unlockables_check_and_the_size_of_the_executable(self):
        # What the cut changes byte by byte is pinned in test_nfl2k5_crib_trophy_room; the help text promises that
        # teams, stadiums and cheats bought earlier stay unlocked, which is the one call this option never touches.
        on, _receipt = self._build(True)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        retail, cut = XbeImage(self.retail), XbeImage(on)
        self.assertEqual(cut.read(0x10E912, 5), retail.read(0x10E912, 5))
        self.assertEqual(len(on), len(self.retail))


if __name__ == "__main__":
    unittest.main()
