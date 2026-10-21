"""The Build tab says what the gameplay presets leave out (Discord 10/16).

A newcomer built a disc with the Modern preset and reported that no mods were installed.
The presets are gameplay and franchise options; the SOFTDRINK 2K28 pack comes from Share.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.gui import build_panel_qt  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402

APP = QApplication.instance() or QApplication([])


class PresetScopeNote(unittest.TestCase):
    def test_note_is_visible_text_beside_the_preset_buttons(self):
        panel = BuildPanel(None)
        self.addCleanup(panel.close)
        text = panel.preset_scope_note.text()
        self.assertIn("do not add the SOFTDRINK 2K28 pack", text)
        self.assertIn("Install SOFTDRINK 2K28", text)
        self.assertTrue(panel.preset_scope_note.wordWrap())
        self.assertIs(panel.preset_scope_note.parent().__class__.__name__ == "QGroupBox", True)

    def test_the_claim_matches_what_the_presets_actually_contain(self):
        # The note says the presets carry no edited rosters, uniforms, stadium art or moments (Experimental does add coach, fan and official looks).
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            preset = mod_build.PRESETS[name]
            with self.subTest(preset=name):
                self.assertFalse(preset.get("espn25_rosters"))
                self.assertFalse(preset.get("modern_helmets"))
                self.assertFalse(preset.get("modern_board_kit"))
                self.assertFalse(preset.get("roster_edits"))

    def test_note_survives_choosing_a_preset(self):
        panel = BuildPanel(None)
        self.addCleanup(panel.close)
        before = panel.preset_scope_note.text()
        self.assertEqual(before, build_panel_qt.PRESET_SCOPE_NOTE)
        self.assertNotIn("\u2014", before)  # house style: no em dashes in copy


if __name__ == "__main__":
    unittest.main()
