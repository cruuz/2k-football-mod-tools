"""Beta 72.1: renaming a finished disc must not cost the next build.

A Windows 11 tester built a disc, renamed the copy, and pressed Build again:

    Couldn't make the disc.
    [WinError 2] The system cannot find the file specified:
    'C:\\Users\\...\\Desktop\\2K5 MOD Studio (Program Files)\\ESPN NFL 2K5 (USA) (modded).xiso.iso'

He had not chosen that path for the build that failed. The Build page hands
each finished copy to the next build (``_done``: "Build source is now: ..."),
so the copy he renamed was the source of the next one, and the first read of it
raised the platform's own file-not-found from inside the copy step. ``build()``
turns ValueError into a sentence, not OSError, so nothing named the file or
said what to do, and on Windows even the "No such file" fix hint did not match
the platform's wording.

Nothing about the new disc needed the old one, so:

* the build refuses by name, before the staging directory, the preflights and
  every write, when the file to build from is gone;
* the page goes back to the file the chain started from and says so, and
  names the missing file plainly when there is nothing to go back to;
* a build to a fresh target never reads, requires or writes the earlier one.

Real failures still refuse: a target that is the source, an existing target
without overwrite, and a folder chosen as the source. Synthetic discs only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.gui import ux_text  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from test_mod_build_performance import synthetic_disc  # noqa: E402

MODDED = "ESPN NFL 2K5 (USA) (modded).xiso.iso"
RENAMED = "NFL 2K5 Modded 3.xiso.iso"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Immediate:
    """Run the Build page's worker on this thread, so _done/_failed are ordered."""

    def start(self, task) -> None:
        task.run()


class RenamedBuildOutputTests(unittest.TestCase):
    """The build backend, given a source that is no longer there."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "ESPN NFL 2K5 (USA).xiso.iso"
        synthetic_disc(self.source)
        self.retail = digest(self.source)

    def build(self, source: Path, target: Path) -> dict:
        return mod_build.build(mod_build.BuildPlan(str(source), str(target)))

    def assertNothingStaged(self) -> None:
        self.assertEqual([], sorted(self.root.glob(".studio-build-*")),
                         "a refused build left a staging directory behind")

    def test_renaming_the_copy_refuses_by_name_and_never_touches_the_new_target(self) -> None:
        first = self.root / MODDED
        self.build(self.source, first)
        renamed = self.root / RENAMED
        first.rename(renamed)
        kept = digest(renamed)
        second = self.root / "ESPN NFL 2K5 (USA) (modded 2).xiso.iso"

        with self.assertRaises(ValueError) as caught:
            self.build(first, second)

        message = str(caught.exception)
        self.assertIn(str(first), message, "the refusal must name the file that is gone")
        self.assertIn("no longer on this computer", message)
        self.assertNotIsInstance(caught.exception, OSError,
                                 "a renamed copy is a sentence, not the platform's file-not-found")
        self.assertNotIn("Traceback", message)
        self.assertFalse(second.exists(), "nothing may be written for a refused build")
        self.assertFalse(first.exists(), "the old path must never be recreated")
        self.assertEqual(kept, digest(renamed), "the renamed copy is not touched")
        self.assertNothingStaged()

    def test_deleting_the_copy_refuses_the_same_way(self) -> None:
        first = self.root / MODDED
        self.build(self.source, first)
        first.unlink()
        second = self.root / "again.xiso.iso"

        with self.assertRaises(ValueError) as caught:
            self.build(first, second)

        self.assertIn(str(first), str(caught.exception))
        self.assertIn("no longer on this computer", str(caught.exception))
        self.assertFalse(second.exists())
        self.assertNothingStaged()

    def test_a_fresh_target_beside_the_old_copy_needs_nothing_from_it(self) -> None:
        first = self.root / MODDED
        self.build(self.source, first)
        before = digest(first)
        stat_before = first.stat()

        second = self.root / "ESPN NFL 2K5 (USA) (modded 2).xiso.iso"
        receipt = self.build(self.source, second)

        self.assertEqual(str(second), receipt["target"])
        self.assertEqual(before, digest(second), "the same source and plan make the same disc")
        self.assertEqual(before, digest(first), "the earlier copy is not rewritten")
        self.assertEqual((stat_before.st_size, stat_before.st_mtime_ns),
                         (first.stat().st_size, first.stat().st_mtime_ns))
        self.assertEqual(self.retail, digest(self.source), "the game disc is never changed")
        self.assertNothingStaged()

    def test_a_fresh_target_builds_with_the_old_copy_already_gone(self) -> None:
        """The whole point: the earlier target is not an input to the next build."""

        first = self.root / MODDED
        self.build(self.source, first)
        first.rename(self.root / RENAMED)

        second = self.root / "ESPN NFL 2K5 (USA) (modded 2).xiso.iso"
        receipt = self.build(self.source, second)
        self.assertEqual(str(second), receipt["target"])
        self.assertTrue(second.is_file())
        self.assertFalse(first.exists())

    def test_real_refusals_still_refuse_with_their_own_words(self) -> None:
        target = self.root / MODDED
        self.build(self.source, target)

        with self.assertRaises(FileExistsError):
            self.build(self.source, target)

        with self.assertRaisesRegex(ValueError, "target must not be the source"):
            self.build(self.source, self.source)

        folder = self.root / "a folder.xiso.iso"
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, "is a folder, not a game file"):
            self.build(folder, self.root / "from-a-folder.iso")
        self.assertNothingStaged()

    def test_the_refusal_carries_a_next_step_on_both_platforms(self) -> None:
        gone = self.root / MODDED
        with self.assertRaises(ValueError) as caught:
            self.build(gone, self.root / "out.iso")
        body = ux_text.failure_body(str(caught.exception))
        self.assertIn("Fix: open the file you want to build from, then build again.", body)
        self.assertIn(str(gone), body)
        # Windows words it its own way; the POSIX needle never matched there, so
        # the tester's dialog offered no next step at all.
        self.assertEqual("Fix: check that the file is still where it was.",
                         ux_text.fix_hint(f"[WinError 2] The system cannot find the file specified: '{gone}'"))
        self.assertEqual("Fix: check that the file is still where it was.",
                         ux_text.fix_hint(f"[Errno 2] No such file or directory: '{gone}'"))


class BuildPageRenamedCopyTests(unittest.TestCase):
    """The Build page, after the copy it handed to the next build disappears."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "ESPN NFL 2K5 (USA).xiso.iso"
        synthetic_disc(self.source)
        self.panel = BuildPanel()
        self.addCleanup(self.panel.deleteLater)
        self.panel._pool = _Immediate()
        self.panel.begin_reading(self.source)
        self.panel.apply_state(mod_build.inspect(self.source))

    def run_build(self, target: Path) -> None:
        self.panel.target_field.setText(str(target))
        self.panel._target_generated = False
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Ok), \
             mock.patch.object(QMessageBox, "information"):
            self.panel._build()
        self.assertTrue(target.is_file(), self.panel.status_label.text())

    def test_the_page_builds_again_from_the_disc_the_chain_started_from(self) -> None:
        first = self.root / MODDED
        self.run_build(first)
        # The page hands the finished copy to the next build; that is the chain.
        self.assertEqual(str(first), self.panel.source_field.text())
        self.assertTrue(self.panel._source_is_last_build)

        first.rename(self.root / RENAMED)

        self.assertEqual("", self.panel.blocker(), self.panel.blocker())
        self.assertEqual(str(self.source), self.panel.source_field.text(),
                         "a vanished copy sends the page back to the disc it started from")
        # The page names the copy it lost, which is all it knows; where the
        # modder put it is their business.
        self.assertIn("no longer at", self.panel.source_status.text())
        self.assertIn(MODDED, self.panel.source_status.text())
        self.assertIn(self.source.name, self.panel.source_status.text())
        self.assertFalse(self.panel._source_is_last_build)
        suggested = Path(self.panel.target_field.text())
        self.assertFalse(suggested.exists(), "the suggested output never overwrites a file")
        self.assertEqual(self.source.parent, suggested.parent)

        second = self.root / "ESPN NFL 2K5 (USA) (modded 2).xiso.iso"
        self.run_build(second)
        self.assertTrue(second.is_file())

    def test_build_pressed_straight_after_the_rename_still_makes_a_disc(self) -> None:
        """No refresh in between: renamed in Explorer, then Build clicked."""

        first = self.root / MODDED
        self.run_build(first)
        renamed = self.root / RENAMED
        first.rename(renamed)
        kept = digest(renamed)

        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Ok), \
             mock.patch.object(QMessageBox, "information"):
            self.panel._build()

        self.assertEqual(str(self.source), self.panel._source_before_build,
                         "the build that ran started from the disc, not the copy that left")
        self.assertTrue(Path(self.panel.target_field.text()).parent.samefile(self.root))
        self.assertEqual(kept, digest(renamed), "the renamed copy is left exactly as it was")
        self.assertNotIn("Couldn't", self.panel.status_label.text())

    def test_a_deleted_copy_is_recovered_from_the_same_memory(self) -> None:
        first = self.root / MODDED
        self.run_build(first)
        first.unlink()
        self.assertEqual("", self.panel.blocker())
        self.assertEqual(str(self.source), self.panel.source_field.text())
        self.assertTrue(self.panel.build_button.isEnabled())

    def test_a_vanished_chosen_disc_is_named_plainly_and_blocks(self) -> None:
        """Nothing to go back to: the page says which file, not what Windows said."""

        self.source.rename(self.root / "moved away.xiso.iso")
        self.panel._refresh()
        reason = self.panel.blocker()
        self.assertIn(str(self.source), reason)
        self.assertIn("renamed, moved or deleted", reason)
        self.assertNotIn("WinError", reason)
        self.assertNotIn("Errno", reason)
        self.assertFalse(self.panel.build_button.isEnabled())
        self.assertEqual(reason, self.panel.build_button.toolTip())

    def test_a_fresh_target_while_the_old_copy_is_still_there(self) -> None:
        first = self.root / MODDED
        self.run_build(first)
        kept = digest(first)
        second = self.root / "ESPN NFL 2K5 (USA) (modded 2).xiso.iso"
        self.run_build(second)
        self.assertTrue(second.is_file())
        self.assertEqual(kept, digest(first), "the earlier copy is left exactly as it was")

    def test_an_open_project_keeps_its_own_disc_as_the_next_build_source(self) -> None:
        """The project's build must start from the project's disc, always."""

        facade = types.SimpleNamespace(
            _lock=threading.Lock(), _cache=object(), _session=object(),
            modified_count=3, source_path=str(self.source),
            build_service=None, source_ready=False)
        self.panel._facade = facade
        first = self.root / MODDED
        receipt = {"target": str(first), "steps": [], "result": mod_build.inspect(self.source),
                   "outcome": {"message": "built"}}
        self.panel._source_before_build = str(self.source)
        self.panel._state_before_build = dict(self.panel._state)
        with mock.patch.object(QMessageBox, "information"):
            self.panel._done(dict(receipt, _build_panel_state=mod_build.inspect(self.source)))

        self.assertEqual(str(self.source), self.panel.source_field.text(),
                         "handing the project build the copy refuses the next one")
        self.assertFalse(self.panel._source_is_last_build)
        self.assertIn("with this project's edits", self.panel.source_status.text())
        self.assertNotEqual(str(self.source), self.panel.target_field.text(),
                            "the suggested output is never the source")

    def test_the_project_build_names_a_missing_file_instead_of_the_platform(self) -> None:
        """The session path resolved both files strictly and raised OSError."""

        facade = types.SimpleNamespace(
            _lock=threading.Lock(), _cache=object(), _session=object(),
            modified_count=1, source_path=str(self.source),
            build_service=None, source_ready=False)
        self.panel._facade = facade
        gone = self.root / MODDED
        plan = mod_build.BuildPlan(str(gone), str(self.root / "out.iso"))

        with self.assertRaises(ValueError) as caught:
            self.panel._build_operation(plan, lambda *args: None, include_session=True)
        self.assertIn(str(gone), str(caught.exception))
        self.assertIn("The file to build from is no longer on this computer", str(caught.exception))
        self.assertNotIsInstance(caught.exception, OSError)

        facade.source_path = str(self.root / "no-such-project-disc.iso")
        with self.assertRaises(ValueError) as caught:
            self.panel._build_operation(mod_build.BuildPlan(str(self.source), str(self.root / "out.iso")),
                                        lambda *args: None, include_session=True)
        self.assertIn("The open project's game disc is no longer on this computer",
                      str(caught.exception))

        # A real mismatch still refuses in its own words.
        other = self.root / "other.xiso.iso"
        synthetic_disc(other)
        facade.source_path = str(other)
        with self.assertRaisesRegex(ValueError, "Choose the open project's source disc"):
            self.panel._build_operation(mod_build.BuildPlan(str(self.source), str(self.root / "out.iso")),
                                        lambda *args: None, include_session=True)


if __name__ == "__main__":
    unittest.main()
