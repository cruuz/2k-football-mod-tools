"""Install SOFTDRINK 2K28 refusals that name the fix (beta-79 ship, R3 review M6 and MINOR 12).

An extracted ("HDD ready") game folder is not an image file: the refusal says so and says how to make one. A target
folder that does not exist is a ModpackError with a plain sentence, not a raw FileNotFoundError from mkstemp.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from mod_editor.core import modpack as m, modpack_files as f


class FolderDumpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_an_extracted_folder_is_refused_with_the_xiso_hint(self) -> None:
        folder = self.root / "ESPN NFL 2K5 (USA) extracted"
        folder.mkdir()
        (folder / "default.xbe").write_bytes(b"XBEH")
        with self.assertRaises(m.ModpackError) as caught:
            f._source_path(folder)
        text = str(caught.exception)
        self.assertIn("Detected: a game folder, not an image file", text)
        self.assertIn("not an extracted game folder", text)
        self.assertIn("xiso first", text)
        self.assertIn("repacked", text)
        self.assertNotIn("—", text)
        self.assertNotIn("–", text)

    def test_an_image_file_is_accepted(self) -> None:
        image = self.root / "ESPN NFL 2K5 (USA).xiso.iso"
        image.write_bytes(b"\0" * 4096)
        self.assertEqual(os.path.samefile(f._source_path(image), image), True)

    def test_a_missing_file_keeps_the_general_refusal(self) -> None:
        with self.assertRaises(m.ModpackError) as caught:
            f._source_path(self.root / "missing.iso")
        self.assertIn("Detected: unreadable game image", str(caught.exception))
        self.assertNotIn("game folder", str(caught.exception))

    @unittest.skipIf(os.name == "nt", "creating symbolic links needs extra rights on Windows")
    def test_a_symbolic_link_to_a_folder_is_still_a_link_refusal(self) -> None:
        folder = self.root / "dump"
        folder.mkdir()
        link = self.root / "link to dump"
        link.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(m.ModpackError) as caught:
            f._source_path(link)
        self.assertIn("must not be a symbolic link", str(caught.exception))


class MissingTargetFolderTests(unittest.TestCase):
    def test_a_target_in_a_folder_that_does_not_exist_is_a_plain_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "no such dir" / "SOFTDRINK 2K28.xiso.iso"
            with self.assertRaises(m.ModpackError) as caught:
                with f._transaction(target):
                    self.fail("the transaction must not start")
            self.assertIn("The output folder does not exist", str(caught.exception))
            self.assertFalse(target.parent.exists())

    def test_an_existing_folder_still_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.iso"
            with f._transaction(target) as part:
                Path(part).write_bytes(b"ok")
            self.assertEqual(target.read_bytes(), b"ok")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["out.iso"])


if __name__ == "__main__":
    unittest.main()
