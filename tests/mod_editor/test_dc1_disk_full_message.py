"""Opening a disc on a full profile drive names the drive instead of saying only "out of space".

Discord, 10/12 (tinpanalley): "it starts extracting ... then eventually says out of space and
I have 1.5 TB left on the drive". The Studio's private game copy (about 6 GiB) lives in the
user's profile, which on Windows is usually the small C: drive, not beside the disc image.
"""

from __future__ import annotations

import errno
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.gui.ux_text import failure_body, fix_hint  # noqa: E402
from mod_editor.studio import facade as facade_module  # noqa: E402
from mod_editor.studio.facade import Nfl2k5StudioFacade  # noqa: E402


class _Cache:
    def __init__(self, error: BaseException, root: Path | None):
        self.error = error
        if root is not None:
            self.cache_root = root

    def index(self, source, progress=None):
        raise self.error


class _WinDiskFull(OSError):
    winerror = 112


def _load(error: BaseException, root: Path | None):
    facade = Nfl2k5StudioFacade(source_cache=_Cache(error, root), xemu_command=())
    return facade.load_source(Path("disc.iso"), lambda *args: None)


class DiskFullMessage(unittest.TestCase):
    def test_posix_enospc_names_the_cache_folder_its_free_space_and_the_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "profile" / "2k5-mod-studio" / "cache"
            original = OSError(errno.ENOSPC, "No space left on device")
            with self.assertRaises(ValidationError) as caught:
                _load(original, root)
            text = str(caught.exception)
            self.assertIn("Not enough free space to open this disc", text)
            self.assertIn(str(root), text)
            self.assertIn("GiB free", text)
            self.assertIn(f"about {facade_module._GAME_INDEX_GIB} GiB", text)
            self.assertIn("beside your disc image does not help", text)
            self.assertIs(caught.exception.__cause__, original)

    def test_windows_disk_full_without_an_errno_is_recognised(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidationError) as caught:
                _load(_WinDiskFull("The disk is full"), Path(tmp))
            self.assertIn("Not enough free space", str(caught.exception))

    def test_a_cache_without_a_known_root_still_gets_the_plain_message(self):
        with self.assertRaises(ValidationError) as caught:
            _load(OSError(errno.ENOSPC, "No space left on device"), None)
        text = str(caught.exception)
        self.assertIn("Not enough free space to open this disc", text)
        self.assertNotIn(" in None", text)

    def test_other_os_errors_are_not_rewritten(self):
        original = PermissionError(errno.EACCES, "Permission denied")
        with self.assertRaises(PermissionError) as caught:
            _load(original, None)
        self.assertIs(caught.exception, original)

    def test_hints_cover_the_raw_operating_system_wording(self):
        self.assertIn("drive is full", fix_hint("[Errno 28] No space left on device: 'x'") or "")
        self.assertIn("drive is full", fix_hint("[WinError 112] There is not enough space on the disk") or "")
        message = facade_module._disk_full_message(None)
        self.assertEqual(fix_hint(message),
                         "Fix: free up room on the drive named above, then open the disc again.")
        body = failure_body(message)
        self.assertEqual(body.count("Fix:"), 1)
        # the older generic sentence for build-time shortages is unchanged
        self.assertIn("choose another folder", fix_hint("There is not enough free space to save this project safely.") or "")


if __name__ == "__main__":
    unittest.main()
