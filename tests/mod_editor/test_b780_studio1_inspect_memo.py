"""b780 studio1: reading a disc checks each executable's structure once, not once per status function.

``mod_build.inspect`` asks about 150 status functions the same 12 MB scale-out executable, and each re-ran the same
structure checks (``nfl2k5_xbe_space.validate_scale_structure`` / ``_validate`` / ``layout``, about 0.1 s apiece, thousands of
times): the released v0.8 disc took minutes to read, the Rosters page did it on the GUI thread, and the Build tab's 180
second limit ended before it finished.  ``studio_inspection.memoised_validation`` runs each check once per distinct
executable while a disc is being read.  These tests are synthetic: counting stand-ins for the checks.
"""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import studio_inspection as inspection  # noqa: E402


class _Counting:
    """Stands in for one check: counts its calls, returns fresh mutable results, refuses an image starting with b'BAD'."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        if payload[:3] == b"BAD":
            raise ValueError("foreign image")
        return (True, "applied", [{"owner": "x", "raw": len(payload)}])


class MemoisedValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.check = _Counting()
        patches = [mock.patch.object(space, name, self.check) for name in inspection._MEMOISED]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_equal_executables_are_checked_once_inside_the_block(self) -> None:
        first, second = bytes(range(256)) * 40, bytes(range(256)) * 40            # equal bytes, two objects
        self.assertIsNot(first, second)
        with inspection.memoised_validation():
            results = [space._validate(first), space._validate(second), space._validate(first)]
        self.assertEqual(self.check.calls, 1)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_a_different_executable_or_a_different_check_is_checked_again(self) -> None:
        with inspection.memoised_validation():
            space._validate(b"A" * 100)
            space._validate(b"B" * 100)
            space.layout(b"A" * 100)
            space.validate_scale_structure(b"A" * 100)
        self.assertEqual(self.check.calls, 4)

    def test_a_caller_that_changes_its_answer_does_not_change_the_next_one(self) -> None:
        payload = b"C" * 200
        with inspection.memoised_validation():
            first = space._validate(payload)
            first[2].append({"owner": "intruder"})
            first[2][0]["owner"] = "changed"
            again = space._validate(payload)
        self.assertEqual(again[2], [{"owner": "x", "raw": 200}])

    def test_a_refusal_is_never_remembered(self) -> None:
        bad = b"BAD" + b"\0" * 100
        with inspection.memoised_validation():
            for _ in range(3):
                with self.assertRaises(ValueError):
                    space._validate(bad)
        self.assertEqual(self.check.calls, 3)

    def test_only_bytes_with_no_other_arguments_are_remembered(self) -> None:
        with inspection.memoised_validation():
            space._validate(bytearray(b"D" * 50))
            space._validate(bytearray(b"D" * 50))
        self.assertEqual(self.check.calls, 2)

    def test_the_originals_come_back_and_the_memo_is_dropped_when_the_block_ends(self) -> None:
        with inspection.memoised_validation():
            self.assertIsNot(space._validate, self.check)
            space._validate(b"E" * 100)
        self.assertIs(space._validate, self.check)
        self.assertIs(space.layout, self.check)
        self.assertIs(space.validate_scale_structure, self.check)
        space._validate(b"E" * 100)                         # outside the block every call checks again
        space._validate(b"E" * 100)
        self.assertEqual(self.check.calls, 3)
        with inspection.memoised_validation():
            space._validate(b"E" * 100)
        self.assertEqual(self.check.calls, 4)               # a new block starts with an empty memo

    def test_blocks_nest_and_only_the_outermost_restores(self) -> None:
        with inspection.memoised_validation():
            with inspection.memoised_validation():
                space._validate(b"F" * 100)
            self.assertIsNot(space._validate, self.check)   # still inside the outer block
            space._validate(b"F" * 100)
        self.assertEqual(self.check.calls, 1)
        self.assertIs(space._validate, self.check)

    def test_a_block_that_raises_still_restores(self) -> None:
        with self.assertRaises(RuntimeError):
            with inspection.memoised_validation():
                raise RuntimeError("boom")
        self.assertIs(space._validate, self.check)

    def test_threads_may_enter_and_leave_in_any_order(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def hold() -> None:
            with inspection.memoised_validation():
                entered.set()
                release.wait(5)

        worker = threading.Thread(target=hold)
        worker.start()
        self.assertTrue(entered.wait(5))
        with inspection.memoised_validation():
            pass                                            # leaves first: the other thread's block must keep its memo
        self.assertIsNot(space._validate, self.check)
        release.set()
        worker.join(5)
        self.assertIs(space._validate, self.check)

    def test_the_disc_read_runs_inside_the_memo(self) -> None:
        from mod_editor.core import mod_build
        seen = []
        with mock.patch.object(mod_build, "_inspect", side_effect=lambda *a, **k: seen.append(space._validate) or {"ok": 1}):
            self.assertEqual(mod_build.inspect(Path("disc.iso")), {"ok": 1})
        self.assertEqual(len(seen), 1)
        self.assertIsNot(seen[0], self.check)               # the memo's wrapper was installed while the read ran
        self.assertIs(space._validate, self.check)          # and is gone afterwards


class DiscReadLimitTests(unittest.TestCase):
    def test_the_limit_is_long_enough_for_a_scale_out_disc_and_a_timeout_says_so_in_plain_words(self) -> None:
        import subprocess
        self.assertGreaterEqual(inspection.INSPECT_TIMEOUT_SECONDS, 600)
        expired = subprocess.TimeoutExpired(["python", "-c", "import sys; secret program"], 1)
        with mock.patch.object(inspection.subprocess, "run", side_effect=expired):
            with self.assertRaises(ValueError) as caught:
                inspection.inspect_source(Path("disc.iso"))
        text = str(caught.exception)
        self.assertIn("took longer than", text)
        self.assertNotIn("secret program", text)            # not the command line the player used to be shown
        self.assertNotIn("python", text)


if __name__ == "__main__":
    unittest.main()
