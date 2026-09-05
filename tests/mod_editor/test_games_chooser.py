"""The "Select other games…" chooser: model without Qt, dialog offscreen.

One row per game -- the studio it opens -- sorted by console, game and year.
A refused module degrades to an explanatory row that cannot be opened, a
factory that raises becomes a sentence in the detail pane, and the real PS2
adapter is listed as "PS2 NFL 2K5 Studio" and opens its studio window.  The
dialog tests are skipped where PyQt5 is absent.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import chooser, contract  # noqa: E402

try:
    from PyQt5.QtWidgets import QApplication, QDialog

    from mod_editor.games.chooser_qt import COLUMNS, GameChooserDialog
except ImportError:  # PyQt5 is not installed here
    QApplication = None  # type: ignore[assignment]

from games_fakes import cli_command, write_fake_root  # noqa: E402


def _fake_root() -> Path:
    return write_fake_root(Path(tempfile.mkdtemp(prefix="chooser-root-")))


class ChooserModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fake_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.report = games.discover(self.root)
        self.rows = chooser.chooser_rows(self.report)

    def _row(self, game_id: str):
        return {row.game_id: row for row in self.rows}[game_id]

    def test_rows_are_one_studio_per_module_sorted_by_console_game_year(self) -> None:
        self.assertEqual([row.game_id for row in self.rows], ["crashgame", "okgame", "oldgame"],
                         [row.detail for row in self.rows])
        self.assertEqual([row.studio_label for row in self.rows],
                         ["TC Crash 1 Studio", "TC OK 1 Studio", "TC Old 1 Studio"])
        ok, old, crash = self._row("okgame"), self._row("oldgame"), self._row("crashgame")
        self.assertTrue(ok.loadable)
        self.assertEqual((ok.title, ok.platform, ok.version, ok.contract),
                         ("OK Game", "Test Console", "2.3.4", "vc_game_module/v1"))
        self.assertEqual(ok.studio_window, "main", "Open opens the module's own studio window")
        self.assertEqual(ok.detail, "OK Game — Test Console · module 2.3.4 · vc_game_module/v1 · 0 lane(s)")
        self.assertFalse(old.loadable)
        self.assertEqual(old.status_text, "Cannot load")
        self.assertEqual(old.studio_window, "", "a refused module opens nothing")
        self.assertIn("vc_game_module/v9", old.detail)
        self.assertEqual(old.version, "2.3.4", "a refused module still shows its declared version")
        self.assertEqual(old.studio_label, "TC Old 1 Studio",
                         "a refused module is still recognisable by the label it would have had")
        self.assertIn("a_dependency_nobody_has", crash.detail)
        self.assertEqual(chooser.chooser_headline(self.rows), "1 game module ready · 2 cannot be loaded (select one to see why)")
        self.assertEqual(chooser.chooser_headline(()), "No game modules are installed.")

    def test_a_module_whose_manifest_cannot_be_read_falls_back_to_its_title(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="chooser-unreadable-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        (root / "brokenmanifest").mkdir(parents=True)
        (root / "brokenmanifest" / "__init__.py").write_text("GAME = None\n", encoding="utf-8", newline="\n")
        (root / "brokenmanifest" / "game.json").write_text("{not json", encoding="utf-8", newline="\n")
        [row] = chooser.chooser_rows(games.discover(root))
        self.assertFalse(row.loadable)
        self.assertEqual(row.studio_label, "brokenmanifest")

    def test_windows_needing_the_studio_are_withheld_without_a_session(self) -> None:
        """The Windows menu still asks this, even though the chooser no longer lists windows."""

        ok = self._row("okgame")
        self.assertTrue(ok.loadable, [row.detail for row in self.rows])
        self.assertEqual([w.window_id for w in chooser.openable_windows(ok, has_studio_session=False)], ["main", "broken"])
        self.assertEqual([w.window_id for w in chooser.openable_windows(ok, has_studio_session=True)], ["main", "broken", "session"])
        self.assertEqual(chooser.openable_windows(self._row("oldgame"), has_studio_session=True), ())

    def test_open_studio_opens_the_window_the_module_named(self) -> None:
        opened = chooser.open_studio(self.report, "okgame")
        self.assertTrue(opened)
        with self.assertRaisesRegex(contract.Refusal, "No hosted game"):
            chooser.open_studio(self.report, "oldgame")

    def test_open_window_turns_every_failure_into_a_refusal(self) -> None:
        opened = chooser.open_window(self.report, "okgame", "main", context={"extra": 1})
        self.assertTrue(opened)
        with self.assertRaisesRegex(contract.Refusal, "could not open .*the window exploded"):
            chooser.open_window(self.report, "okgame", "broken")
        with self.assertRaisesRegex(contract.Refusal, "needs the studio's session"):
            chooser.open_window(self.report, "okgame", "session")
        self.assertTrue(chooser.open_window(self.report, "okgame", "session", context={"facade": object()}))
        with self.assertRaisesRegex(contract.Refusal, "has no window"):
            chooser.open_window(self.report, "okgame", "absent")
        with self.assertRaisesRegex(contract.Refusal, "No hosted game"):
            chooser.open_window(self.report, "oldgame", "main")

    def test_the_command_line_lists_and_describes(self) -> None:
        def run(*verbs):
            return subprocess.run(cli_command("--games-root", str(self.root), *verbs),
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=300)

        listing = run()
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("1 game module ready", listing.stdout, listing.stdout + listing.stderr)
        self.assertIn("oldgame", listing.stdout)
        self.assertIn("TC OK 1 Studio", listing.stdout, "the listing shows studio labels")
        self.assertEqual(run("list").stdout, listing.stdout)
        described = run("show", "okgame")
        self.assertEqual(described.returncode, 0, described.stderr)
        self.assertIn("TC OK 1 Studio", described.stdout)
        self.assertIn("--window main", described.stdout)
        self.assertIn("[studio]", described.stdout, "show marks which window is the studio")
        refused = run("show", "oldgame")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("cannot be loaded", refused.stderr)
        absent = run("show", "nothing")
        self.assertEqual(absent.returncode, 2)


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class ChooserDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.root = _fake_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.report = games.discover(self.root)

    def test_dialog_lists_studios_and_gates_open_on_load_status(self) -> None:
        dialog = GameChooserDialog(self.report, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(COLUMNS, ("Studio", "Status", "Detail"))
        self.assertEqual(dialog.table.columnCount(), len(COLUMNS))
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertEqual([dialog.table.item(row, 0).text() for row in range(3)],
                         ["TC Crash 1 Studio", "TC OK 1 Studio", "TC Old 1 Studio"])
        self.assertEqual(dialog.table.item(1, 1).text(), "Ready")
        self.assertEqual(dialog.table.item(2, 1).text(), "Cannot load")
        self.assertIn("1 game module ready", dialog.headline.text())
        self.assertTrue(dialog.select_game("oldgame"))
        self.assertFalse(dialog.open_button.isEnabled())
        self.assertIn("vc_game_module/v9", dialog.detail.text())
        self.assertFalse(dialog.open_selected(), "a refused row cannot open anything")
        self.assertTrue(dialog.select_game("okgame"))
        self.assertTrue(dialog.open_button.isEnabled())
        for control in (dialog.table, dialog.open_button, dialog.detail, dialog.headline):
            self.assertTrue(control.accessibleName())

    def test_opening_goes_through_the_module_and_failures_are_sentences(self) -> None:
        dialog = GameChooserDialog(self.report, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        dialog.select_game("okgame")
        self.assertTrue(dialog.open_selected(), "Open opens the studio, with no window to pick")
        self.assertIsInstance(dialog.last_opened, QDialog)
        self.assertEqual(dialog.last_opened.windowTitle(), "Fake window")
        self.assertIn("opened main", dialog.detail.text())
        self.assertFalse(dialog.open_selected("broken"))
        self.assertIn("the window exploded", dialog.detail.text())
        self.assertFalse(dialog.open_selected("session"), "no facade in this context")
        self.assertIn("needs the studio's session", dialog.detail.text())

    def test_a_session_context_still_reaches_a_window_that_needs_it(self) -> None:
        dialog = GameChooserDialog(self.report, context={"facade": object()}, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        dialog.select_game("okgame")
        self.assertTrue(dialog.open_selected("session"))

    def test_the_real_ps2_adapter_is_a_studio_row_and_opens_its_studio(self) -> None:
        dialog = GameChooserDialog(games.discover(), modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog.select_game("nfl2k5_ps2"))
        row = dialog.selected_row()
        self.assertEqual(row.studio_label, "PS2 NFL 2K5 Studio")
        self.assertEqual(row.studio_window, "studio")
        self.assertEqual([dialog.table.item(index, 0).text() for index in range(dialog.table.rowCount())],
                         ["PS2 NFL 2K5 Studio"])
        # The studio window's own menu_label is what it is called from inside
        # itself; every row that offers it from outside reads the composed one.
        studio_row = [window for window in row.windows if window.window_id == row.studio_window]
        self.assertEqual([window.menu_label for window in studio_row], ["PS2 NFL 2K5 Studio\u2026"])
        self.assertTrue(dialog.open_selected())
        self.assertIn("PS2 NFL 2K5 Studio: opened studio", dialog.detail.text())
        dialog.last_opened.close()
        dialog.last_opened.deleteLater()


if __name__ == "__main__":
    unittest.main()
