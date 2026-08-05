"""A modder must be able to pick which team's helmet they are changing.

The crest writers take an outer archive entry index, and for a long time the
editor passed only one: outer 36, the Assassins.  Every other team on the disc
was unreachable from the product, so "put the Eagles wing on the Philadelphia
team" was not a thing the tool could do no matter what art you gave it.

These tests pin the fix at both ends -- the table that maps a team to its crest
package, and the build actually sending that team's indices to both writers.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import apf_team_crests  # noqa: E402
from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.gui import ApfTeamLogoPanel  # noqa: E402

from test_apf_team_logo_gui import (  # noqa: E402
    DECLARED_SIBLINGS, _CompletedProcess, _Facade, _RecordingRunner,
    _fake_game, _value_after, _write_png,
)


class CrestTableTests(unittest.TestCase):
    def test_every_built_in_team_is_offered(self) -> None:
        self.assertEqual(len(apf_team_crests.TEAM_CRESTS), 24)

    def test_no_two_teams_share_a_crest_package(self) -> None:
        """A shared package would silently repaint somebody else's helmet."""
        outers = [c.outer_entry_index for c in apf_team_crests.TEAM_CRESTS]
        assets = [c.asset_index for c in apf_team_crests.TEAM_CRESTS]
        self.assertEqual(len(set(outers)), len(outers))
        self.assertEqual(len(set(assets)), len(assets))

    def test_the_philadelphia_team_is_the_americans(self) -> None:
        """The row this whole exercise turned on."""
        crest = apf_team_crests.by_team("Americans")
        self.assertEqual(crest.abbreviation, "PHI")
        self.assertEqual(crest.outer_entry_index, 1133)
        self.assertEqual(crest.package_name, "uniform_logo_30.iff")

    def test_the_new_york_team_is_the_knights(self) -> None:
        crest = apf_team_crests.by_team("Knights")
        self.assertEqual(crest.abbreviation, "NY")
        self.assertEqual(crest.outer_entry_index, 112)

    def test_the_default_is_still_the_target_the_writers_always_used(self) -> None:
        """Existing callers that pass nothing must not silently move."""
        import apf_logo_patch

        self.assertEqual(
            apf_team_crests.default_crest().outer_entry_index,
            apf_logo_patch.ENTRY_INDEX,
        )

    def test_lookups_refuse_rather_than_guess(self) -> None:
        with self.assertRaises(KeyError):
            apf_team_crests.by_team("Philadelphia Eagles")
        with self.assertRaises(KeyError):
            apf_team_crests.by_outer_entry(999999)


class PanelSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, index_0a: str):
        recorder = _RecordingRunner()
        panel = ApfTeamLogoPanel(_Facade(index_0a=index_0a), recorder)
        return panel, recorder

    def test_the_picker_lists_every_team(self) -> None:
        panel, _ = self._panel("/nonexistent/0A")
        self.assertEqual(panel.slot.count(), len(apf_team_crests.TEAM_CRESTS))
        labels = [panel.slot.itemText(i) for i in range(panel.slot.count())]
        self.assertTrue(any("Americans" in text for text in labels))
        self.assertTrue(any("Knights" in text for text in labels))

    def test_it_opens_on_the_historical_default(self) -> None:
        panel, _ = self._panel("/nonexistent/0A")
        self.assertEqual(panel.selected_crest(), apf_team_crests.default_crest())

    def test_the_chosen_team_reaches_both_writers(self) -> None:
        """The whole point: pick Americans, and outer 1133 is what gets written."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = _fake_game(root)
            panel, runner = self._panel(str(index))
            staged = _write_png(root / "crest.png", panel._WIDTH, panel._HEIGHT)
            panel._stage_path(staged)
            self.app.processEvents()

            americans = apf_team_crests.by_team("Americans")
            panel.slot.setCurrentIndex(panel.slot.findData(americans))

            out_volume = root / "out" / "0A"
            with mock.patch.object(
                gui.QFileDialog, "getSaveFileName",
                return_value=(str(out_volume), ""),
            ), mock.patch.object(
                gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
            ):
                panel._build_copied_volume()

            operation = runner.operation_for("Building copied 0A")
            with mock.patch.object(
                gui.ApfTeamLogoPanel, "_declared_sibling_packs",
                return_value=DECLARED_SIBLINGS,
            ), mock.patch("subprocess.run",
                          side_effect=lambda *a, **k: _CompletedProcess(0)) as run:
                operation(lambda *_args: None)

            package_argv = run.call_args_list[0].args[0]
            cache_argv = run.call_args_list[1].args[0]
            self.assertEqual(
                _value_after(package_argv, "--entry-index"),
                str(americans.outer_entry_index),
            )
            self.assertEqual(
                _value_after(cache_argv, "--catalog-index"),
                str(americans.asset_index),
            )


if __name__ == "__main__":
    unittest.main()
