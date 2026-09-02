"""Whatever a stranger picks, both editors must answer with a sentence.

These editors are about to be handed images by people whose dumps nobody here
has seen: the wrong game, a half-finished download, an archive somebody renamed
to .iso, a folder, a link, a path that no longer exists. Refusing any of those is
correct. Raising something the caller does not catch is not, because these run
from a desktop icon with no console and the user only sees the window disappear.

Every case below is something people really do, and every one has to come back as
``ValidationError`` or ``SourceError``, never a bare ``OSError``.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

_REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.apf_studio.source import SourceError, SourceManager  # noqa: E402
from mod_editor.core import sources  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
RETAIL_2K5 = _REPO_ROOT / "ESPN NFL 2K5 (USA).xiso.iso"


def _filesystem_without_an_executable(path: Path) -> Path:
    """A real XDVDFS whose only entry is not a game executable."""

    name = b"readme.txt"
    node = struct.pack("<HHII", 0, 0, 40, 12) + bytes([0x80, len(name)]) + name
    node += b"\0" * (-len(node) % 4)
    header = bytearray(SECTOR)
    header[:20] = MAGIC
    header[-20:] = MAGIC
    struct.pack_into("<II", header, 20, 33, len(node))
    blob = bytearray(33 * SECTOR)
    blob[0x10000:0x10000 + SECTOR] = header
    blob += node + bytes((-len(node)) % SECTOR)
    blob += bytes(8 * SECTOR)
    path.write_bytes(bytes(blob))
    return path


class HostileSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="hostile-source-"))
        self.inspector = sources.SourceInspector()
        self.apf = SourceManager()

    def _cases(self) -> list[tuple[str, Path]]:
        empty = self.root / "empty.iso"
        empty.write_bytes(b"")
        noise = self.root / "noise.iso"
        noise.write_bytes(os.urandom(256 * 1024))
        zeros = self.root / "zeros.iso"
        zeros.write_bytes(bytes(256 * 1024))
        archive = self.root / "renamed.iso"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("readme.txt", "this is a zip, not a disc")
        folder = self.root / "a-folder"
        folder.mkdir()
        return [
            ("an empty file", empty),
            ("random bytes", noise),
            ("all zeros", zeros),
            ("a zip renamed to .iso", archive),
            ("a filesystem with no executable",
             _filesystem_without_an_executable(self.root / "no-xbe.iso")),
            ("an empty folder", folder),
            ("a path that does not exist", self.root / "absent.iso"),
        ]

    def test_nothing_a_stranger_picks_escapes_as_an_unhandled_error(self) -> None:
        for label, path in self._cases():
            with self.subTest(case=label):
                # Identification answers "what is this?" and must never raise.
                sources.disc_title(path)
                sources.contained_identity(path)
                try:
                    self.inspector.inspect(path)
                except ValidationError:
                    pass
                try:
                    self.apf.resolve(path)
                except SourceError:
                    pass

    def test_a_path_that_is_gone_is_refused_in_words(self) -> None:
        """A recent-files entry or an unmounted drive is ordinary, not a crash."""

        absent = self.root / "absent.iso"
        for call in (lambda: self.inspector.inspect(absent),
                     lambda: self.apf.resolve(absent)):
            with self.assertRaises((ValidationError, SourceError)) as caught:
                call()
            self.assertIn("not there any more", str(caught.exception))

    def test_an_empty_folder_names_what_it_wanted_to_find(self) -> None:
        folder = self.root / "empty-folder"
        folder.mkdir()
        with self.assertRaises(ValidationError) as caught:
            self.inspector.inspect(folder)
        self.assertIn("default.xbe", str(caught.exception))


class SymlinkedDiscTests(unittest.TestCase):
    """A linked disc is an ordinary setup, not a suspicious one.

    Keeping the image on another drive and linking it into a working folder is
    normal. Opening the given path with O_NOFOLLOW reported that as "not an Xbox
    game" while the inspector recognised the very same file, so the editor
    contradicted itself. Resolving first keeps the guarantee that matters, which
    is that the file opened is the file examined.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="symlink-disc-"))

    @unittest.skipUnless(RETAIL_2K5.is_file(), "retail 2K5 image not present")
    def test_a_symlinked_disc_is_identified_like_the_file_it_points_at(self) -> None:
        link = self.root / "linked.iso"
        link.symlink_to(RETAIL_2K5)
        direct = sources.disc_title(RETAIL_2K5)
        through_link = sources.disc_title(link)
        self.assertIsNotNone(direct)
        self.assertEqual(through_link, direct)

    @unittest.skipUnless(RETAIL_2K5.is_file(), "retail 2K5 image not present")
    def test_identification_agrees_with_recognition(self) -> None:
        """The two answers must not contradict each other for one file."""

        link = self.root / "linked.iso"
        link.symlink_to(RETAIL_2K5)
        self.assertIsNotNone(sources.disc_title(link))
        self.assertTrue(sources.SourceInspector().inspect(link).recognized)

    def test_a_link_that_points_nowhere_is_refused_not_followed(self) -> None:
        broken = self.root / "broken.iso"
        broken.symlink_to(self.root / "nothing-here.iso")
        self.assertIsNone(sources.disc_title(broken))
        with self.assertRaises(ValidationError):
            sources.SourceInspector().inspect(broken)


if __name__ == "__main__":
    unittest.main()
