"""A refusal a modder cannot act on is the same as a broken feature.

Two modders reported the 2K5 side not working. One said the editor "doesn't have
an export function"; the other asked "were you able to get it to rebuild the xiso
file because i couldn't". Running the real app settled what was actually wrong.

The builder is fine. A real 6.3 GB retail XISO rebuilds and independently
verifies: `NFL2K5_VISUAL_MOD_BUILD_PASS edits=1 changed=12`, then
`NFL2K5_VISUAL_MOD_VERIFY_PASS` on the same sha256, and `extract-xiso -l` lists a
well-formed 19-file image. Nothing about the pipeline is broken.

What is broken is how it says no:

1. **Build Modded XISO is disabled until an edit exists**, which is correct, but
   its tooltip was a fixed sentence describing what Build does. Load a disc, press
   Build before editing anything, and *nothing happens* — no dialog, no status
   change — with the only clue a small edit-count chip several widgets away. That
   is indistinguishable from a broken button, and it is the likeliest thing the
   second modder hit.
2. **The backend's collide check** raised one message naming three conditions and
   identifying none: "output XISO, manifest, or artifact directory
   exists/collides". It fires easily, because ``--artifact-dir`` is a required
   argument that must NOT already exist, so the obvious reflex of creating the
   directory first triggers it — after the user has already loaded and edited a
   6.3 GB disc.
3. **The free-space check budgeted a hardcoded ``SOURCE_SIZE``** while
   ``_validate_cache`` had deliberately stopped pinning the source size, because a
   legal dump's container differs from this project's own rip. A larger dump was
   therefore under-budgeted and could fail part-way through staging on a full disk
   instead of refusing cleanly up front, which is the entire point of the check.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_build_service as build_service  # noqa: E402
from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildError  # noqa: E402
from mod_editor.gui.studio_qt import (  # noqa: E402
    BUILD_READY_MESSAGE,
    _build_blocker_message,
)


class BuildButtonExplainsItselfTests(unittest.TestCase):
    def test_no_loaded_disc_says_to_load_one(self) -> None:
        message = _build_blocker_message(ready=False, edit_count=0, busy=False)
        self.assertIn("Open your game disc", message)
        self.assertNotEqual(message, BUILD_READY_MESSAGE)

    def test_no_edits_says_to_make_one_and_how(self) -> None:
        """The case a modder actually hit: loaded, pressed Build, nothing."""

        message = _build_blocker_message(ready=True, edit_count=0, busy=False)
        self.assertIn("at least one project edit", message)
        # Naming a way to make an edit matters more than naming the rule.
        self.assertTrue(
            any(hint in message for hint in ("Replace a PNG", "edit a string")),
            f"the message should say how to make an edit: {message!r}",
        )

    def test_a_running_operation_says_to_wait(self) -> None:
        message = _build_blocker_message(ready=True, edit_count=4, busy=True)
        self.assertIn("Wait", message)

    def test_busy_outranks_the_other_blockers(self) -> None:
        """Report the blocker the user must clear first, not the first one found."""

        self.assertIn(
            "Wait", _build_blocker_message(ready=False, edit_count=0, busy=True)
        )

    def test_a_usable_button_describes_what_build_does(self) -> None:
        self.assertEqual(
            _build_blocker_message(ready=True, edit_count=1, busy=False),
            BUILD_READY_MESSAGE,
        )
        self.assertIn("never changed", BUILD_READY_MESSAGE)

    def test_every_state_yields_a_nonempty_distinct_sentence(self) -> None:
        seen = {
            _build_blocker_message(ready=r, edit_count=c, busy=b)
            for r in (True, False) for c in (0, 5) for b in (True, False)
        }
        self.assertEqual(len(seen), 4, f"expected four distinct messages: {seen}")
        for message in seen:
            self.assertTrue(message.strip())
            self.assertTrue(message.rstrip().endswith("."), message)

    def test_the_button_tooltip_is_refreshed_with_its_enabled_state(self) -> None:
        """A stale tooltip would explain the previous state, which is worse."""

        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        enable_at = source.index("self.build_button.setEnabled(")
        tooltip_at = source.index("self.build_button.setToolTip(", enable_at)
        between = source[enable_at:tooltip_at]
        self.assertNotIn(
            "def ", between,
            "the tooltip must be set in the same refresh as the enabled state",
        )
        self.assertIn("_build_blocker_message", source[tooltip_at:tooltip_at + 400])


class BuildSpaceUsesTheRealSourceTests(unittest.TestCase):
    def test_the_requirement_follows_the_supplied_source_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small = root / "small.iso"
            small.write_bytes(b"\0" * 4096)
            captured: list[int] = []

            class _Usage:
                # Enough for the small dump plus margin, nowhere near SOURCE_SIZE.
                free = build_service.BUILD_SPACE_MARGIN + 8192

            original = build_service.shutil.disk_usage
            build_service.shutil.disk_usage = lambda _p: _Usage()  # type: ignore[assignment]
            try:
                # Budgeting the hardcoded SOURCE_SIZE would refuse this outright.
                build_service._require_build_space(root, small)
            finally:
                build_service.shutil.disk_usage = original  # type: ignore[assignment]
            self.assertEqual(captured, [])

    def test_a_dump_larger_than_the_constant_is_still_refused(self) -> None:
        """The under-budgeting case: a bigger container must not sneak through."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            big = root / "big.iso"
            big.write_bytes(b"")
            # Claim a size larger than the project's own rip without writing it.
            real_stat = Path.stat

            def fake_stat(self, *args, **kwargs):
                result = real_stat(self, *args, **kwargs)
                if self == big:
                    class _S:
                        st_size = build_service.SOURCE_SIZE * 2
                    return _S()
                return result

            class _Usage:
                # Plenty for the constant, not for twice it.
                free = build_service.SOURCE_SIZE + build_service.BUILD_SPACE_MARGIN

            original_usage = build_service.shutil.disk_usage
            build_service.shutil.disk_usage = lambda _p: _Usage()  # type: ignore[assignment]
            Path.stat = fake_stat  # type: ignore[assignment]
            try:
                with self.assertRaises(Nfl2k5BuildError) as caught:
                    build_service._require_build_space(root, big)
            finally:
                Path.stat = real_stat  # type: ignore[assignment]
                build_service.shutil.disk_usage = original_usage  # type: ignore[assignment]
            self.assertIn("free space", str(caught.exception))

    def test_an_unreadable_source_falls_back_rather_than_skipping(self) -> None:
        """Failing to measure must not silently disable the check."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "not-there.iso"

            class _Usage:
                free = 0

            original = build_service.shutil.disk_usage
            build_service.shutil.disk_usage = lambda _p: _Usage()  # type: ignore[assignment]
            try:
                with self.assertRaises(Nfl2k5BuildError):
                    build_service._require_build_space(root, missing)
            finally:
                build_service.shutil.disk_usage = original  # type: ignore[assignment]

    def test_the_call_site_passes_the_source(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "core" / "nfl2k5_build_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_require_build_space(output.parent, source)", source)


class CollideRefusalNamesThePathTests(unittest.TestCase):
    """The backend must say which of the three paths is the problem."""

    def setUp(self) -> None:
        self.source = (
            _REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py"
        ).read_text(encoding="utf-8")

    def _assert_contains(self, needle: str) -> None:
        """assertIn without pasting a 4,000-line module into the failure."""

        self.assertTrue(
            needle in self.source,
            f"nfl2k5_visual_mod_project.py no longer contains {needle!r}",
        )

    def test_the_unattributable_message_is_gone(self) -> None:
        self.assertNotIn(
            "output XISO, manifest, or artifact directory exists/collides",
            self.source,
            "the single message naming three conditions and identifying none is back",
        )

    def test_the_three_paths_are_labelled_for_the_message(self) -> None:
        for label in ('"output XISO"', '"manifest"', '"artifact directory"'):
            self._assert_contains(label)

    def test_each_condition_reports_separately(self) -> None:
        # An existing path, an unusable name and a collision are three different
        # mistakes with three different fixes, so each needs its own sentence.
        self._assert_contains("already exists")
        self._assert_contains("Build never overwrites")
        self._assert_contains("no usable filename")
        self._assert_contains("must be three ")

    def test_the_offending_path_is_interpolated_into_the_message(self) -> None:
        """Naming the condition without the path still leaves the user guessing."""

        self._assert_contains("already exists: {_path}")


if __name__ == "__main__":
    unittest.main()
