"""Beta 74: a build into a folder OneDrive manages is refused before staging.

A build writes a 6 GB disc copy and its working files beside the output and
reads those files back after two child passes. A OneDrive folder uploads and
scans every one of them and can hold or replace a file in that window, none
of which the Studio controls. Windows signed in with a Microsoft account puts
Desktop, Documents and Pictures under OneDrive by default, which is exactly
where a first-timer builds. The refusal names the folder, the reason and the
fix, and nothing is staged or validated first.

Two signals, both Windows-only: the OneDrive environment variables that name
the sync roots, and the cloud-files reparse tag on a Files On-Demand folder.
A junction is also a reparse point and must not trip it. POSIX hosts stand
in for Windows by flipping ``IS_WINDOWS``; ``os.lstat`` is stubbed for the
reparse tags a Linux filesystem cannot produce.
"""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from mod_editor.core import nfl2k5_build_service as service
from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildService
from mod_editor.gui.ux_text import failure_body
import test_nfl2k5_build_service as build_fixtures

CLOUD_TAG = 0x9000101A      # IO_REPARSE_TAG_CLOUD_1, one of the Files On-Demand tags
JUNCTION_TAG = 0xA0000003   # IO_REPARSE_TAG_MOUNT_POINT


class _ReparseDirectory:
    """What ``os.lstat`` reports for a reparse-point directory on Windows."""

    def __init__(self, tag):
        self.st_mode = stat.S_IFDIR | 0o755
        self.st_file_attributes = stat.FILE_ATTRIBUTE_DIRECTORY | stat.FILE_ATTRIBUTE_REPARSE_POINT
        self.st_reparse_tag = tag


def _windows():
    return patch.object(platform_compat, "IS_WINDOWS", True)


class OneDriveOutputFolderTests(unittest.TestCase):
    def test_a_folder_under_the_onedrive_root_is_refused_with_the_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "OneDrive - Contoso"
            output = root / "Desktop" / "2K5 builds"
            output.mkdir(parents=True)
            resolved = output.resolve()
            with _windows():
                with self.assertRaises(ValidationError) as caught:
                    service._require_local_output_folder(resolved, {"OneDriveCommercial": str(root)})
            text = str(caught.exception)
            self.assertIn("inside OneDrive", text)
            self.assertIn("the OneDriveCommercial folder", text)
            self.assertIn(str(resolved), text)
            self.assertIn("build again", text)
            self.assertIn("Fix: choose a folder OneDrive does not sync", failure_body(text))

    def test_the_root_itself_and_another_case_match_but_a_sibling_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "OneDrive"
            root.mkdir()
            sibling = Path(folder) / "OneDriveX"
            sibling.mkdir()
            with _windows():
                for supplied in (str(root), str(root).upper()):
                    with self.assertRaises(ValidationError):
                        service._require_local_output_folder(root.resolve(), {"OneDrive": supplied})
                # A sibling whose name merely starts with the root's name is local.
                service._require_local_output_folder(sibling.resolve(), {"OneDrive": str(root)})
                # An empty or blank variable names nothing.
                service._require_local_output_folder(root.resolve(), {"OneDrive": "   "})
                service._require_local_output_folder(root.resolve(), {})

    def test_a_files_on_demand_folder_is_refused_and_a_junction_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            managed = (Path(folder) / "Documents").resolve()
            output = managed / "builds"
            output.mkdir(parents=True)
            real = os.lstat

            def tagged(tag):
                def lstat(path, *args, **kwargs):
                    if Path(path) == managed:
                        return _ReparseDirectory(tag)
                    return real(path, *args, **kwargs)
                return lstat

            with _windows():
                with patch.object(service.os, "lstat", tagged(CLOUD_TAG)):
                    with self.assertRaises(ValidationError) as caught:
                        service._require_local_output_folder(output, {})
                self.assertIn(str(managed), str(caught.exception))
                self.assertIn("Files On-Demand", str(caught.exception))
                with patch.object(service.os, "lstat", tagged(JUNCTION_TAG)):
                    service._require_local_output_folder(output, {})

    def test_posix_never_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(platform_compat, "IS_WINDOWS", False):
                service._require_local_output_folder(Path(folder).resolve(), {"OneDrive": folder})

    def test_the_build_refuses_before_anything_is_staged_or_validated(self):
        with tempfile.TemporaryDirectory(prefix="b74-onedrive-") as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            runner = build_fixtures.FakeBackendRunner()
            with _windows(), patch.dict(os.environ, {"OneDrive": str(fixture.output.parent)}):
                with self.assertRaisesRegex(ValidationError, "inside OneDrive"):
                    Nfl2k5BuildService(runner=runner).build(
                        fixture.cache, fixture.project, fixture.output)
            self.assertEqual(runner.calls, [])
            self.assertEqual(fixture.stage_paths(), [])
            self.assertFalse(fixture.output.exists())


if __name__ == "__main__":
    unittest.main()
