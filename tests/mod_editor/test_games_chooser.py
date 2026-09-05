"""The "Select other games…" chooser: model without Qt, dialog offscreen.

A refused module degrades to an explanatory row, a window that needs the Xbox
session is withheld when there is none, a factory that raises becomes a
sentence in the detail pane, and the real PS2 adapter's read-only window opens
through the chooser.  The dialog tests are skipped where PyQt5 is absent.
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

from games_fakes import write_fake_root  # noqa: E402


def _fake_root() -> Path:
    return write_fake_root(Path(tempfile.mkdtemp(prefix="chooser-root-")))


class ChooserModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _fake_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.report = games.discover(self.root)
        self.rows = chooser.chooser_rows(self.report)

    def test_rows_show_loadable_first_and_refusals_with_reasons(self) -> None:
        self.assertEqual([row.game_id for row in self.rows], ["okgame", "crashgame", "oldgame"],
                         [row.detail for row in self.rows])
        ok, crash, old = self.rows
        self.assertTrue(ok.loadable)
        self.assertEqual((ok.title, ok.platform, ok.version, ok.contract), ("OK Game", "Test Console", "2.3.4", "vc_game_module/v1"))
        self.assertEqual([w.window_id for w in ok.windows], ["main", "broken", "session"])
        self.assertFalse(old.loadable)
        self.assertEqual(old.status_text, "Cannot load")
        self.assertIn("vc_game_module/v9", old.detail)
        self.assertEqual(old.version, "2.3.4", "a refused module still shows its declared version")
        self.assertIn("a_dependency_nobody_has", crash.detail)
        self.assertEqual(chooser.chooser_headline(self.rows), "1 game module ready · 2 cannot be loaded (select one to see why)")
        self.assertEqual(chooser.chooser_headline(()), "No game modules are installed.")

    def test_windows_needing_the_studio_are_withheld_without_a_session(self) -> None:
        ok = self.rows[0]
        self.assertTrue(ok.loadable, [row.detail for row in self.rows])
        self.assertEqual([w.window_id for w in chooser.openable_windows(ok, has_studio_session=False)], ["main", "broken"])
        self.assertEqual([w.window_id for w in chooser.openable_windows(ok, has_studio_session=True)], ["main", "broken", "session"])
        self.assertEqual(chooser.openable_windows(self.rows[2], has_studio_session=True), ())

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
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        def run(*verbs):
            return subprocess.run([sys.executable, "-m", "mod_editor.games", "--games-root", str(self.root), *verbs],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=300, env=env)

        listing = run()
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("1 game module ready", listing.stdout, listing.stdout + listing.stderr)
        self.assertIn("oldgame", listing.stdout)
        self.assertEqual(run("list").stdout, listing.stdout)
        described = run("show", "okgame")
        self.assertEqual(described.returncode, 0, described.stderr)
        self.assertIn("--window main", described.stdout)
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

    def test_dialog_lists_rows_and_gates_open_on_load_status(self) -> None:
        dialog = GameChooserDialog(self.report, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.table.columnCount(), len(COLUMNS))
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertEqual(dialog.table.item(0, 4).text(), "Ready")
        self.assertEqual(dialog.table.item(2, 4).text(), "Cannot load")
        self.assertIn("1 game module ready", dialog.headline.text())
        self.assertTrue(dialog.select_game("oldgame"))
        self.assertFalse(dialog.open_button.isEnabled())
        self.assertIn("vc_game_module/v9", dialog.detail.text())
        self.assertFalse(dialog.open_selected(), "a refused row cannot open anything")
        self.assertTrue(dialog.select_game("okgame"))
        self.assertTrue(dialog.open_button.isEnabled())
        labels = [dialog.windows.item(i).text() for i in range(dialog.windows.count())]
        self.assertEqual(labels, ["OK Game window…", "Broken window…", "Needs session… (needs the studio's open project)"])
        self.assertFalse(dialog.windows.item(2).flags() & 0x20, "withheld window is disabled")  # Qt.ItemIsEnabled
        for control in (dialog.table, dialog.windows, dialog.open_button, dialog.detail, dialog.headline):
            self.assertTrue(control.accessibleName())

    def test_opening_goes_through_the_module_and_failures_are_sentences(self) -> None:
        dialog = GameChooserDialog(self.report, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        dialog.select_game("okgame")
        self.assertTrue(dialog.open_selected("main"))
        self.assertIsInstance(dialog.last_opened, QDialog)
        self.assertEqual(dialog.last_opened.windowTitle(), "Fake window")
        self.assertIn("opened main", dialog.detail.text())
        self.assertFalse(dialog.open_selected("broken"))
        self.assertIn("the window exploded", dialog.detail.text())
        self.assertFalse(dialog.open_selected("session"), "no facade in this context")
        self.assertIn("needs the studio's session", dialog.detail.text())

    def test_a_session_context_offers_the_session_window(self) -> None:
        dialog = GameChooserDialog(self.report, context={"facade": object()}, modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        dialog.select_game("okgame")
        labels = [dialog.windows.item(i).text() for i in range(dialog.windows.count())]
        self.assertEqual(labels, ["OK Game window…", "Broken window…", "Needs session…"])
        self.assertTrue(dialog.open_selected("session"))

    def test_the_real_ps2_adapter_opens_its_read_only_window_through_the_chooser(self) -> None:
        dialog = GameChooserDialog(games.discover(), modal_windows=False)
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog.select_game("nfl2k5_ps2"))
        labels = [dialog.windows.item(i).text() for i in range(dialog.windows.count())]
        self.assertEqual(labels, ["PS2 Save Editor…", "PS2 Disc Inventory…",
                                  "Export PS2 replacement pack… (needs the studio's open project)"])
        self.assertTrue(dialog.open_selected("disc-inventory"))
        self.assertEqual(dialog.last_opened.windowTitle(), "PS2 Disc Inventory")
        dialog.last_opened.close()
        dialog.last_opened.deleteLater()


if __name__ == "__main__":
    unittest.main()
