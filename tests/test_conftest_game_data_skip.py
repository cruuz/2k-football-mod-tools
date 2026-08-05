"""The game-data skip must never hide a real failure.

``tests/conftest.py`` turns "this machine has no disc image" into a skip so a
clean checkout does not report 343 broken tests. That is only safe while it is
impossible to fire on a machine that *does* have the data, because there the
same missing file means something went wrong. These tests pin that boundary.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import conftest  # noqa: E402


class GameDataDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="conftest-skip-"))
        self.absent = self.root / "reports" / "assets"
        self.present = self.root / "extracted"
        self.present.mkdir(parents=True)
        self._saved = (conftest.ROOT, conftest.GITIGNORED_TREES,
                       conftest.GITIGNORED_FILES)
        conftest.ROOT = self.root
        conftest.GITIGNORED_TREES = (self.absent, self.present)
        conftest.GITIGNORED_FILES = (self.root / "game.xiso.iso",)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        (conftest.ROOT, conftest.GITIGNORED_TREES,
         conftest.GITIGNORED_FILES) = self._saved

    def test_a_file_under_an_absent_tree_is_missing_game_data(self) -> None:
        error = FileNotFoundError(2, "No such file or directory")
        error.filename = str(self.absent / "inventory.json")
        self.assertIsNotNone(conftest._missing_game_data(error))

    def test_a_file_under_a_tree_that_exists_is_a_real_failure(self) -> None:
        """The step that should have written it did not. That is not a skip."""

        error = FileNotFoundError(2, "No such file or directory")
        error.filename = str(self.present / "never_written.json")
        self.assertIsNone(conftest._missing_game_data(error))

    def test_a_message_naming_an_absent_tree_counts(self) -> None:
        """Most tools raise their own type with the path only in the text."""

        class SpecError(ValueError):
            pass

        error = SpecError("source report is missing or symlinked: reports/assets/x.json")
        self.assertIsNotNone(conftest._missing_game_data(error))

    def test_a_message_naming_a_tree_that_exists_does_not_count(self) -> None:
        error = ValueError("extracted content did not match the expected layout")
        self.assertIsNone(conftest._missing_game_data(error))

    def test_an_ordinary_assertion_is_never_converted(self) -> None:
        self.assertIsNone(conftest._missing_game_data(AssertionError("3 != 4")))

    def test_a_wrapped_cause_is_still_found(self) -> None:
        """Refusals are usually re-raised as the tool's own error type."""

        inner = FileNotFoundError(2, "No such file or directory")
        inner.filename = str(self.absent / "inventory.json")
        outer = RuntimeError("could not build the report")
        outer.__cause__ = inner
        self.assertIsNotNone(conftest._missing_game_data(outer))

    def test_a_missing_disc_image_counts_but_a_present_one_does_not(self) -> None:
        disc = conftest.GITIGNORED_FILES[0]
        error = FileNotFoundError(2, "No such file or directory")
        error.filename = str(disc)
        self.assertIsNotNone(conftest._missing_game_data(error))
        disc.write_bytes(b"a dump that is present")
        self.assertIsNone(conftest._missing_game_data(error))


if __name__ == "__main__":
    unittest.main()
