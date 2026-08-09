"""Fail-closed tests for the shared release staging helper."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "packaging/stage_release.py"
SPEC = importlib.util.spec_from_file_location("stage_release", HELPER)
assert SPEC is not None and SPEC.loader is not None
stage_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage_release)


class ReleaseStagingTests(unittest.TestCase):
    def test_stages_fresh_destination_and_preserves_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-stage-test-") as temporary:
            fixture = Path(temporary)
            root = fixture / "source"
            root.mkdir()
            (root / "data.txt").write_bytes(b"exact data\n")
            launcher = root / "bin/launch.sh"
            launcher.parent.mkdir()
            launcher.write_bytes(b"#!/bin/sh\nexit 0\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
            allowlist = fixture / "allowlist.txt"
            allowlist.write_text("data.txt\nbin/launch.sh\n", encoding="utf-8")
            destination = fixture / "stage"

            self.assertEqual(
                stage_release.stage(allowlist, destination, root), 2
            )
            self.assertEqual((destination / "data.txt").read_bytes(), b"exact data\n")
            staged_launcher = destination / "bin/launch.sh"
            self.assertEqual(staged_launcher.read_bytes(), launcher.read_bytes())
            if os.name != "nt":
                self.assertTrue(staged_launcher.stat().st_mode & stat.S_IXUSR)

    def test_refuses_existing_destination_without_touching_it(self) -> None:
        for kind in ("directory", "file", "dangling-symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix="release-stage-existing-"
            ) as temporary:
                fixture = Path(temporary)
                root = fixture / "source"
                root.mkdir()
                (root / "declared.txt").write_text("source\n", encoding="utf-8")
                allowlist = fixture / "allowlist.txt"
                allowlist.write_text("declared.txt\n", encoding="utf-8")
                destination = fixture / "stage"
                sentinel = destination / "sentinel.txt"
                if kind == "directory":
                    destination.mkdir()
                    sentinel.write_text("keep\n", encoding="utf-8")
                elif kind == "file":
                    destination.write_text("keep\n", encoding="utf-8")
                else:
                    destination.symlink_to(fixture / "missing-target")

                with self.assertRaisesRegex(
                    stage_release.StageError, "destination already exists"
                ):
                    stage_release.stage(allowlist, destination, root)
                self.assertTrue(os.path.lexists(destination))
                if kind == "directory":
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
                    self.assertFalse((destination / "declared.txt").exists())
                elif kind == "file":
                    self.assertEqual(destination.read_text(encoding="utf-8"), "keep\n")

    def test_refuses_destination_below_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-stage-dest-link-") as temporary:
            fixture = Path(temporary)
            root = fixture / "source"
            root.mkdir()
            (root / "declared.txt").write_text("source\n", encoding="utf-8")
            allowlist = fixture / "allowlist.txt"
            allowlist.write_text("declared.txt\n", encoding="utf-8")
            actual_parent = fixture / "actual-parent"
            actual_parent.mkdir()
            linked_parent = fixture / "linked-parent"
            linked_parent.symlink_to(actual_parent, target_is_directory=True)
            destination = linked_parent / "stage"

            with self.assertRaisesRegex(
                stage_release.StageError, "destination has a symlinked parent"
            ):
                stage_release.stage(allowlist, destination, root)
            self.assertFalse((actual_parent / "stage").exists())

    def test_refuses_missing_or_invalid_allowlist_before_creating_destination(self) -> None:
        for kind in ("missing", "directory", "symlink", "invalid-utf8"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix="release-stage-allowlist-"
            ) as temporary:
                fixture = Path(temporary)
                root = fixture / "source"
                root.mkdir()
                allowlist = fixture / "allowlist.txt"
                if kind == "directory":
                    allowlist.mkdir()
                elif kind == "symlink":
                    target = fixture / "real-allowlist.txt"
                    target.write_text("safe.txt\n", encoding="utf-8")
                    allowlist.symlink_to(target)
                elif kind == "invalid-utf8":
                    allowlist.write_bytes(b"safe.txt\n\xff")
                destination = fixture / "stage"

                with self.assertRaises(
                    (stage_release.StageError, UnicodeError)
                ):
                    stage_release.stage(allowlist, destination, root)
                self.assertFalse(os.path.lexists(destination))

    def test_refuses_noncanonical_or_escaping_allowlist_entries(self) -> None:
        bad_entries = (
            "/absolute.py",
            "../escape.py",
            "a/../../escape.py",
            "./safe.py",
            "safe.py\\other.py",
            "safe.py\nsafe.py",
        )
        for entry in bad_entries:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory(
                prefix="release-stage-path-"
            ) as temporary:
                fixture = Path(temporary)
                root = fixture / "source"
                root.mkdir()
                (root / "safe.py").write_text("safe = True\n", encoding="utf-8")
                allowlist = fixture / "allowlist.txt"
                allowlist.write_text(entry + "\n", encoding="utf-8")
                destination = fixture / "stage"

                with self.assertRaises(stage_release.StageError):
                    stage_release.stage(allowlist, destination, root)
                self.assertFalse(os.path.lexists(destination))

    def test_refuses_empty_or_comment_only_allowlist(self) -> None:
        for payload in ("", "\n", "# comment\n"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory(
                prefix="release-stage-empty-"
            ) as temporary:
                fixture = Path(temporary)
                root = fixture / "source"
                root.mkdir()
                allowlist = fixture / "allowlist.txt"
                allowlist.write_text(payload, encoding="utf-8")
                destination = fixture / "stage"

                with self.assertRaisesRegex(
                    stage_release.StageError, "no file entries"
                ):
                    stage_release.stage(allowlist, destination, root)
                self.assertFalse(os.path.lexists(destination))

    def test_refuses_absent_or_nonregular_inputs_atomically(self) -> None:
        for kind in ("missing", "directory", "symlink", "symlinked-parent"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix="release-stage-input-"
            ) as temporary:
                fixture = Path(temporary)
                root = fixture / "source"
                root.mkdir()
                (root / "first.txt").write_text("valid\n", encoding="utf-8")
                relative = "bad.txt"
                if kind == "directory":
                    (root / relative).mkdir()
                elif kind == "symlink":
                    target = root / "target.txt"
                    target.write_text("target\n", encoding="utf-8")
                    (root / relative).symlink_to(target)
                elif kind == "symlinked-parent":
                    outside = fixture / "outside"
                    outside.mkdir()
                    (outside / "bad.txt").write_text("outside\n", encoding="utf-8")
                    (root / "linked").symlink_to(outside, target_is_directory=True)
                    relative = "linked/bad.txt"
                allowlist = fixture / "allowlist.txt"
                allowlist.write_text(
                    f"first.txt\n{relative}\n", encoding="utf-8"
                )
                destination = fixture / "stage"

                with self.assertRaises(stage_release.StageError):
                    stage_release.stage(allowlist, destination, root)
                self.assertFalse(os.path.lexists(destination))

    def test_cli_without_required_inputs_is_usage_error(self) -> None:
        completed = subprocess.run(
            [sys.executable, os.fspath(HELPER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("usage:", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_cli_failure_is_nonzero_and_named(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-stage-cli-") as temporary:
            fixture = Path(temporary)
            root = fixture / "source"
            root.mkdir()
            allowlist = fixture / "allowlist.txt"
            allowlist.write_text("missing.txt\n", encoding="utf-8")
            destination = fixture / "stage"
            completed = subprocess.run(
                [
                    sys.executable,
                    os.fspath(HELPER),
                    os.fspath(allowlist),
                    os.fspath(destination),
                    os.fspath(root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("RELEASE_STAGE_REFUSED:", completed.stderr)
            self.assertFalse(os.path.lexists(destination))

    def test_ci_uses_the_same_hardened_helper_without_precreating_stages(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            'python3 packaging/stage_release.py packaging/release-allowlist.txt "$s" "$repo"',
            workflow,
        )
        self.assertIn(
            'python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt "$a" "$repo"',
            workflow,
        )
        self.assertNotIn("stage_release()", workflow)
        self.assertNotIn('mkdir -p "$s"', workflow)
        self.assertNotIn('mkdir -p "$a"', workflow)


if __name__ == "__main__":
    unittest.main()
