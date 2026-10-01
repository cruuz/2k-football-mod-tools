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
from types import SimpleNamespace
import unittest

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

import conftest  # noqa: E402


class GameDataDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="conftest-skip-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
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

    def report_for(self, error, failure_exception=AssertionError):
        report = SimpleNamespace(outcome="failed", longrepr="original failure")
        item = SimpleNamespace(
            fspath="test_example.py", location=("test_example.py", 7, "test_example"),
            _testcase=SimpleNamespace(failureException=failure_exception),
        )
        call = SimpleNamespace(excinfo=SimpleNamespace(value=error))
        hook = conftest.pytest_runtest_makereport(item, call)
        next(hook)
        with self.assertRaises(StopIteration):
            hook.send(SimpleNamespace(get_result=lambda: report))
        return report

    def test_assertion_naming_research_remains_a_failure(self):
        conftest.GITIGNORED_TREES += (self.root / "research",)
        report = self.report_for(AssertionError("missing docs/research/apf_audio.md"))
        self.assertEqual(report.outcome, "failed")
        self.assertEqual(report.longrepr, "original failure")

    def test_missing_file_report_becomes_a_skip(self):
        report = self.report_for(FileNotFoundError(2, "absent", str(self.absent / "x.json")))
        self.assertEqual(report.outcome, "skipped")
        self.assertIn("game data not present: reports/assets/x.json", report.longrepr[2])

    def test_wrapped_missing_file_report_becomes_a_skip(self):
        error = RuntimeError("tool could not read input")
        error.__cause__ = FileNotFoundError(2, "absent", str(self.absent / "x.json"))
        self.assertEqual(self.report_for(error).outcome, "skipped")

    def test_present_tree_report_remains_a_failure(self):
        for error in (
            FileNotFoundError(2, "absent", str(self.present / "x.json")),
            FileNotFoundError(2, "absent", bytes(self.present / "x.json")),
            FileNotFoundError(2, "absent", str(self.present / "output.iso")),
            FileNotFoundError(2, "absent", str(self.present / "output.qcow2")),
            ValueError(f"source report is missing: {self.present}/x.json"),
        ):
            with self.subTest(error=error):
                self.assertEqual(self.report_for(error).outcome, "failed")

    def test_assertion_with_missing_file_cause_or_context_remains_a_failure(self):
        for link in ("__cause__", "__context__"):
            error = AssertionError("the operation should have succeeded")
            setattr(error, link, FileNotFoundError(2, "absent", str(self.absent / "x.json")))
            with self.subTest(link=link):
                self.assertEqual(self.report_for(error).outcome, "failed")

    def test_assertion_inside_tool_error_chain_remains_a_failure(self):
        class FalseVerdict(AssertionError):
            def __bool__(self):
                return False

        for verdict in (AssertionError, FalseVerdict):
            with self.subTest(verdict=verdict.__name__):
                error = ValueError(f"missing input: {self.absent}/x.json")
                error.__cause__ = verdict("wrong output")
                self.assertEqual(self.report_for(error).outcome, "failed")

    def test_custom_unittest_failure_exception_remains_a_failure(self):
        class Verdict(ValueError):
            pass

        error = Verdict(f"missing input: {self.absent}/x.json")
        error.__cause__ = FileNotFoundError(2, "absent", str(self.absent / "x.json"))
        self.assertEqual(self.report_for(error, Verdict).outcome, "failed")

    def test_pytest_fail_remains_a_failure(self):
        if not hasattr(conftest.pytest, "fail"):
            self.skipTest("pytest is not installed")
        error = conftest.pytest.fail.Exception(f"missing input: {self.absent}/x.json")
        error.__cause__ = FileNotFoundError(2, "absent", str(self.absent / "x.json"))
        self.assertEqual(self.report_for(error).outcome, "failed")

    def test_tool_path_mention_without_absence_is_a_failure(self):
        for message in (f"invalid format in {self.absent}/x.json",
                        f"missing checksum in {self.absent}/x.json"):
            with self.subTest(message=message):
                self.assertEqual(self.report_for(ValueError(message)).outcome, "failed")

    def test_tool_explicit_absence_becomes_a_skip(self):
        for message in (
            "source report is missing or symlinked: reports/assets/x.json",
            "missing local file reports/assets/x.json",
            "reports/assets/x.json does not exist",
            "required input is missing: reports/assets/x.json",
        ):
            with self.subTest(message=message):
                self.assertEqual(self.report_for(ValueError(message)).outcome, "skipped")

    def test_nested_present_tree_is_not_confused_with_absent_root_tree(self):
        nested = self.root / "docs" / "research"
        nested.mkdir(parents=True)
        conftest.GITIGNORED_TREES += (self.root / "research", nested)
        error = ValueError("missing local file docs/research/x.md")
        self.assertEqual(self.report_for(error).outcome, "failed")

    def test_oserror_family_and_second_filename(self):
        for filename in (str(self.absent / "x.json"), bytes(self.absent / "x.json")):
            with self.subTest(filename=filename):
                error = OSError(5, "cannot read")
                error.filename2 = filename
                self.assertEqual(self.report_for(error).outcome, "skipped")

    def test_cyclic_cause_chain_terminates(self):
        error = ValueError("invalid input")
        error.__cause__ = error
        self.assertEqual(self.report_for(error).outcome, "failed")


if __name__ == "__main__":
    unittest.main()
