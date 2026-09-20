"""Beta 74: the working-session root follows each platform's convention.

Before this, ``default_session_root`` returned ``~/.local/share`` on every
platform, so on Windows the Studio created and scanned
``C:\\Users\\<name>\\.local\\share\\2k5-mod-studio\\sessions`` -- a POSIX path
inside the user profile. Coach Edwards found exactly that folder on 2026-09-19,
and workspace_state.py already documents a Windows ``[Errno 13]`` on such a
``.local`` path. Sessions now use ``%LOCALAPPDATA%`` on Windows, matching the
Studio's state directory, and ``$XDG_DATA_HOME`` or ``~/.local/share`` on POSIX.

Synthetic environment only; no build, no game bytes.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from mod_editor.core import platform_compat
from mod_editor.studio import session as session_module


class SessionRootPlatformTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "LOCALAPPDATA")}

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_posix_default_is_local_share(self):
        os.environ.pop("XDG_DATA_HOME", None)
        with patch.object(platform_compat, "IS_WINDOWS", False):
            root = session_module.default_session_root()
        self.assertEqual(root, Path.home() / ".local" / "share" / "2k5-mod-studio" / "sessions")

    def test_xdg_data_home_is_honoured_on_posix(self):
        os.environ["XDG_DATA_HOME"] = "/opt/xdg"
        with patch.object(platform_compat, "IS_WINDOWS", False):
            root = session_module.default_session_root()
        self.assertEqual(root, Path("/opt/xdg") / "2k5-mod-studio" / "sessions")

    def test_windows_uses_localappdata_not_dot_local(self):
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ["LOCALAPPDATA"] = r"C:\Users\glenwood.edwards\AppData\Local"
        with patch.object(platform_compat, "IS_WINDOWS", True):
            root = session_module.default_session_root()
        text = str(root)
        self.assertIn("AppData", text)
        self.assertNotIn(".local", text)
        # It must live under the same private root the Studio's own resolver names.
        with patch.object(platform_compat, "IS_WINDOWS", True):
            self.assertTrue(
                platform_compat.is_within_user_private_root(root)
                or str(platform_compat.user_private_root()) in text
            )

    def test_xdg_wins_over_windows_localappdata(self):
        os.environ["XDG_DATA_HOME"] = "/opt/xdg"
        os.environ["LOCALAPPDATA"] = r"C:\Users\x\AppData\Local"
        with patch.object(platform_compat, "IS_WINDOWS", True):
            root = session_module.default_session_root()
        self.assertEqual(root, Path("/opt/xdg") / "2k5-mod-studio" / "sessions")


if __name__ == "__main__":
    unittest.main()
