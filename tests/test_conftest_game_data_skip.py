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

    def test_an_english_word_is_not_a_path(self) -> None:
        """The reason this hook has to match path-shaped text.

        Six of the gitignored trees are bare words -- build, assets, research,
        extracted, artifacts, docs/updates. A substring test turns any failure
        whose message happens to contain one of them into a skip, which hides
        real red. This is the case that actually happened: a genuine
        AssertionError reading "... decided at build time" was reported as
        "Skipped: game data not present: build".
        """

        for word in ("build", "assets", "research", "extracted", "artifacts"):
            with self.subTest(word=word):
                self.assertFalse(
                    conftest._names_a_path(f"... decided at {word} time", word)
                )
                self.assertTrue(
                    conftest._names_a_path(f"wrote {word}/manifest.json", word)
                )

    def test_a_nested_gitignored_tree_still_counts(self) -> None:
        # The gitignore pattern "research/" also matches "docs/research/", so a
        # preceding separator must stay allowed.
        self.assertTrue(conftest._names_a_path(
            "missing local file docs/research/apf_audio.md", "research"
        ))

    def test_a_directory_named_at_the_end_of_a_path_still_counts(self) -> None:
        # A tree named as the final segment has no trailing separator, so
        # requiring one would unmask a genuine missing-game-data failure. This
        # is the exact case that appears in the stadium writer's symlink test.
        self.assertTrue(conftest._names_a_path(
            "[Errno 2] No such file or directory: "
            "'/home/x/tmpabc/ancestor_link/All-Pro Football 2K8 (USA)'",
            "All-Pro Football 2K8 (USA)",
        ))

    def test_a_longer_word_with_the_same_prefix_is_not_a_match(self) -> None:
        self.assertFalse(conftest._names_a_path("builds/output.log", "build"))

    def test_a_multi_segment_tree_matches_at_a_word_boundary(self) -> None:
        self.assertTrue(conftest._names_a_path(
            "reports/assets/inventory.json is missing", "reports/assets"
        ))
        self.assertFalse(conftest._names_a_path(
            "reports/assets-backup/inventory.json", "reports/assets"
        ))

    def test_a_plain_assertion_mentioning_a_word_still_fails(self) -> None:
        # End to end through the real entry point, not just the helper.
        self.assertIsNone(conftest._missing_game_data(
            AssertionError("expected the build to finish, got a timeout")
        ))

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
