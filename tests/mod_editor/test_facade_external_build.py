"""A Build & Share copy registered with the facade is what Launch Latest Build starts."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.studio.facade import ExternalBuild, Nfl2k5StudioFacade, ValidationError  # noqa: E402


class ExternalBuildTests(unittest.TestCase):
    def test_a_regular_file_becomes_the_latest_build(self) -> None:
        facade = Nfl2k5StudioFacade()
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "modded.xiso.iso"
            image.write_bytes(b"\0" * 32)
            facade.register_external_build(image)
            self.assertEqual(facade._last_build, ExternalBuild(output_xiso=image))
            self.assertNotIn("Build a modded XISO first", facade.xemu_blocker)

    def test_missing_or_linked_files_are_refused(self) -> None:
        facade = Nfl2k5StudioFacade()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidationError):
                facade.register_external_build(Path(tmp) / "missing.iso")
            real = Path(tmp) / "real.iso"
            real.write_bytes(b"\0")
            link = Path(tmp) / "link.iso"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValidationError):
                facade.register_external_build(link)
            self.assertIsNone(facade._last_build)


if __name__ == "__main__":
    unittest.main()
