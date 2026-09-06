"""The open-disc hook (UX E2): one disc open fills every page that has its own source field.

The header said "Disc: …" while eleven pages still asked for a disc.  The shell now feeds
the disc it just opened to each page through that page's own load / inspect path, off the
UI thread, without opening a chooser, writing a file or resetting a roster the user edited.
These tests drive the hook with a synthetic default.xbe (the only source that inspects
without retail data) and check the contracts the review pinned:

* Build, Game Fixes and Position names receive one inspection and switch their captions to
  the executable wording; no target is invented for a bare executable.
* Getting Started's "Start SOFTDRINK Basic →" waits for the inspection and only ticks a
  fresh selection.
* Share's install source follows the open disc only while it has not been chosen by hand;
  a finished build's export pair is never replaced.
* ★ Rosters keeps an edited roster; the shell never reloads it on navigation.
* A suggested copy name never reuses an existing file.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from mod_editor.gui.share_panel_qt import SharePanel  # noqa: E402
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow  # noqa: E402
from mod_editor.gui.ux_text import suggest_copy_name  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402
from test_roster_editor_panel_qt import synthetic_body  # noqa: E402


def _open_source(facade: BrowseOnlyFacade, path: Path) -> None:
    """Make a browse-only facade report one open source (a synthetic default.xbe).

    Set after the window is built: a browse-only facade that claims a source during
    construction sends the embedded panels after data it cannot serve."""

    facade.source_ready = True
    facade.source_path = path
    facade.source_display_name = path.name


class OpenDiscHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # Windows: a lane's inspection worker can still hold the synthetic image when the
        # directory goes; the temp dir tolerates that (the OS frees it) rather than failing the test.
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.xbe = Path(self.tmp.name) / "default.xbe"
        self.xbe.write_bytes(_build_synthetic_xbe())
        self.window = StudioMainWindow(facade=BrowseOnlyFacade(), offer_recovery=False)
        self.app.processEvents()
        _open_source(self.window.facade, self.xbe)

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def _wait_for_inspection(self, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        while self.window._source_inspect_pending and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertFalse(self.window._source_inspect_pending, "the inspection never finished")

    def test_one_open_fills_the_build_and_patch_pages_with_the_right_captions(self) -> None:
        build = self.window._build_panel
        self.assertEqual(build.source_field.text(), "")
        self.window._prefill_panels_from_source(self.xbe)
        self.assertTrue(self.window._source_inspect_pending)
        self.assertEqual(build.source_status.text(), "Reading disc…")
        self.assertFalse(build.build_button.isEnabled())
        self._wait_for_inspection()
        for panel in (build, self.window._gameplay_patches_panel, self.window._edge_panel):
            self.assertEqual(Path(panel.source_field.text()).resolve(), self.xbe.resolve())
            self.assertEqual(panel.source_caption.text(), "Game executable (default.xbe)")
            self.assertEqual(panel.target_caption.text(), "Save executable copy as")
            # a bare executable gets no invented copy name: only disc copies are suggested
            self.assertEqual(panel.target_field.text(), "")
        self.assertTrue(build.catch_check.isEnabled())
        self.assertEqual(self.window.welcome_ready.text(), f"Disc open: {self.xbe.name}")
        # the throw page read the same file through its own reader
        deadline = time.time() + 60
        throw = self.window._throw_tuning_panel
        while not throw.source_field.text() and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertEqual(Path(throw.source_field.text()).resolve(), self.xbe.resolve())

    def test_start_softdrink_basic_waits_for_the_inspection_and_only_ticks_a_fresh_selection(self) -> None:
        build = self.window._build_panel
        self.window._prefill_panels_from_source(self.xbe)
        self.window._go_to_build_share("softdrink_basic")
        self.assertEqual(self.window.page_title.text(), "Build & Share")
        self.assertEqual(build.pending_preset, "softdrink_basic")
        self.assertFalse(build.throw_check.isChecked())
        self._wait_for_inspection()
        self.assertIsNone(build.pending_preset)
        self.assertTrue(build.throw_check.isChecked() and build.catch_check.isChecked())
        self.assertIn("selected; review changes below", build.preset_note.text())
        # customised choices are kept on a second visit
        build.catch_check.setChecked(False)
        self.window._go_to_build_share("softdrink_basic")
        self.assertFalse(build.catch_check.isChecked())
        self.assertIn("kept", build.preset_note.text())

    def test_a_second_open_supersedes_the_first_inspection(self) -> None:
        build = self.window._build_panel
        self.window._prefill_panels_from_source(self.xbe)
        first = self.window._source_generation
        other = Path(self.tmp.name) / "other.xbe"
        other.write_bytes(_build_synthetic_xbe())
        self.window.facade.source_path = other
        self.window.facade.source_display_name = other.name
        self.window._prefill_panels_from_source(other)
        self.assertGreater(self.window._source_generation, first)
        self._wait_for_inspection()
        self.assertEqual(Path(build.source_field.text()).resolve(), other.resolve())

    def test_the_roster_page_follows_the_disc_lazily_and_never_resets_an_edited_roster(self) -> None:
        panel = self.window._roster_editor_panel
        panel.load_document(rr.load_body(synthetic_body()), label="my edits")
        panel.auto_filled = True
        first = panel.selected_player() or panel.document.players[0]
        panel._dirty.add((first.pool, first.index))
        self.assertTrue(panel.is_dirty())
        self.window._prefill_panels_from_source(self.xbe)
        self.assertTrue(self.window._roster_prefill_pending)
        rosters_row = next(i for i in range(self.window.navigation.count())
                           if self.window.navigation.item(i).data(Qt.UserRole) == "rosters")
        self.window.navigation.setCurrentRow(rosters_row)
        self.app.processEvents()
        self.assertFalse(self.window._roster_prefill_pending)
        self.assertEqual(panel.source_label.text(), "my edits")
        self.assertIn("stays loaded", panel.status_label.text())
        self._wait_for_inspection()


class ShareFollowsTheOpenDiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_install_source_follows_only_while_not_chosen_by_hand(self) -> None:
        panel = SharePanel()
        panel.follow_source("/discs/a.iso")
        self.assertEqual(panel.base_field.text(), "/discs/a.iso")
        self.assertEqual(panel.source_field.text(), "/discs/a.iso")
        panel.follow_source("/discs/b.iso")
        self.assertEqual(panel.source_field.text(), "/discs/b.iso", "still following the open disc")
        panel.source_field.setText("/discs/mine.iso")           # chosen by hand
        panel.follow_source("/discs/c.iso")
        self.assertEqual(panel.source_field.text(), "/discs/mine.iso")
        panel.deleteLater()

    def test_a_finished_build_owns_the_export_pair(self) -> None:
        panel = SharePanel()
        panel.prefill_from_build({"source": "/discs/base.iso", "target": "/discs/base (modded).xiso.iso", "plan": {}})
        panel.base_field.setText("")
        panel.follow_source("/discs/other.iso")
        self.assertEqual(panel.base_field.text(), "", "the open disc must not replace a build's base")
        panel.deleteLater()


class CopyNameTests(unittest.TestCase):
    def test_suggested_names_sit_beside_the_source_and_never_collide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "ESPN NFL 2K5 (USA).xiso.iso"
            source.write_bytes(b"\0")
            first = suggest_copy_name(source)
            self.assertEqual(Path(first).resolve().parent, source.resolve().parent)
            self.assertEqual(Path(first).name, "ESPN NFL 2K5 (USA) (modded).xiso.iso")
            Path(first).write_bytes(b"\0")
            self.assertEqual(Path(suggest_copy_name(source)).name, "ESPN NFL 2K5 (USA) (modded 2).xiso.iso")
            self.assertEqual(Path(suggest_copy_name(source, suffix="sounds")).name,
                             "ESPN NFL 2K5 (USA) (sounds).xiso.iso")
            self.assertEqual(suggest_copy_name(""), "")


if __name__ == "__main__":
    unittest.main()
