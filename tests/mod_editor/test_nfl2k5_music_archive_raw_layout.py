"""The archive reader accepts a disc whose directories sit below the volume descriptor.

Ju3tin (#2k5-general, 2026-09-09) built from a raw dump whose root directory lives at
sector 30 and whose ``vc_53450030`` directory lives at sector 31, both below the volume
descriptor at sector 32.  Nothing overlaps, yet every build step that opens the disc
through ``nfl2k5_music_archive.Disc`` refused it with "overlapping disc file or
metadata: root directory", because the overlap sweep started past the descriptor
instead of at the partition start.  The xiso the studio pins puts its root at sector 33,
which is why the same options build there.  Real overlaps must still be refused.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_music_archive as archive  # noqa: E402
from tests.nfl2k5_xiso_fixture import SECTOR, SyntheticXiso, dir_node  # noqa: E402

# A redump-style raw dump (video partition in front, game partition at 0x18300000) whose
# directories sit at sectors 30 and 31.  Read-only retail input; never copied anywhere.
RAW_DUMP = Path("/home/noah/Downloads/ESPN NFL 2K5 (USA) 2.iso")
RAW_DUMP_PARTITION = 0x18300000
DESCRIPTOR_SECTOR = 32
PACK_SIZE = 0x2000
PACK_SECTORS = tuple(64 + 4 * index for index in range(16))
PACK_NAMES = "0123456789ABCDEF"


def sixteen_pack_image(directory: Path) -> bytearray:
    """The shared synthetic xiso with the sixteen packs the archive reader requires."""
    entries = [(0x1000 + index, bytes([index + 1]) * 2048) for index in range(8)]
    fixture = SyntheticXiso(directory, entries, pack_sizes=(PACK_SIZE,) * 16, pack_sectors=PACK_SECTORS)
    return bytearray(fixture.image)


def directories_at(image: bytearray, root_sector: int, sub_sector: int, *,
                   root_size: int | None = None, xbe_sector: int = 35) -> bytearray:
    """Move the fixture's directories (root at 33, vc_53450030 at 34) to the given sectors."""
    subdir = dir_node([(PACK_SECTORS[index], PACK_SIZE, 0x80, name) for index, name in enumerate(PACK_NAMES)])
    root = dir_node([(xbe_sector, 16, 0x80, "default.xbe"), (sub_sector, len(subdir), 0x10, "vc_53450030")])
    for sector in (33, 34):
        image[sector * SECTOR:(sector + 1) * SECTOR] = bytes(SECTOR)
    image[root_sector * SECTOR:root_sector * SECTOR + len(root)] = root
    image[sub_sector * SECTOR:sub_sector * SECTOR + len(subdir)] = subdir
    struct.pack_into("<II", image, 0x10014, root_sector, len(root) if root_size is None else root_size)
    return image


class DirectoriesBelowTheDescriptorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def _write(self, image: bytes, name: str = "disc.iso") -> Path:
        path = self.root / name
        path.write_bytes(bytes(image))
        return path

    def test_the_pinned_fixture_layout_still_opens(self) -> None:
        with archive.Disc(self._write(sixteen_pack_image(self.root)), descriptors=()) as disc:
            self.assertEqual(disc.partition, 0)
            self.assertEqual(tuple(disc.pack_extents), tuple(PACK_NAMES))

    def test_the_testers_layout_opens(self) -> None:
        # root directory at sector 30, vc_53450030 at sector 31, descriptor at 32: no overlap.
        image = directories_at(sixteen_pack_image(self.root), 30, 31)
        with archive.Disc(self._write(image), descriptors=()) as disc:
            self.assertEqual(disc.partition, 0)
            self.assertEqual(tuple(disc.pack_extents), tuple(PACK_NAMES))
            self.assertEqual(disc.entries["vc_53450030"].sector, 31)
            self.assertEqual(disc.nodes["0"][1:], (PACK_SECTORS[0], PACK_SIZE))

    def test_a_file_below_the_descriptor_opens_too(self) -> None:
        image = directories_at(sixteen_pack_image(self.root), 30, 31, xbe_sector=29)
        image[29 * SECTOR:29 * SECTOR + 16] = b"XBEH" + bytes(12)
        with archive.Disc(self._write(image), descriptors=()) as disc:
            self.assertEqual(disc.entries["default.xbe"].sector, 29)

    def test_the_testers_layout_opens_behind_a_video_partition(self) -> None:
        # The same directory placement inside a raw dump: the game partition starts later in the file.
        partition = 0x30000
        image = directories_at(sixteen_pack_image(self.root), 30, 31)
        with archive.Disc(self._write(bytes(partition) + bytes(image), "raw.iso"), descriptors=()) as disc:
            self.assertEqual(disc.partition, partition)
            self.assertEqual(disc.entries["vc_53450030"].byte_offset, partition + 31 * SECTOR)
            self.assertEqual(disc.pack_extents["0"].byte_offset, partition + PACK_SECTORS[0] * SECTOR)

    def test_a_root_directory_that_runs_into_the_next_directory_is_still_refused(self) -> None:
        # root at 30 declared two sectors long reaches into vc_53450030 at 31: a real overlap.
        image = directories_at(sixteen_pack_image(self.root), 30, 31, root_size=2 * SECTOR)
        with self.assertRaisesRegex(ValueError, "overlapping disc file or metadata: vc_53450030"):
            archive.Disc(self._write(image), descriptors=())

    def test_a_file_over_the_volume_descriptor_is_still_refused(self) -> None:
        image = directories_at(sixteen_pack_image(self.root), 30, 31, xbe_sector=DESCRIPTOR_SECTOR)
        with self.assertRaisesRegex(ValueError, "overlapping disc file or metadata"):
            archive.Disc(self._write(image), descriptors=())

    def test_a_directory_over_the_volume_descriptor_is_still_refused(self) -> None:
        # root at 31 declared two sectors long covers the descriptor sector.
        image = directories_at(sixteen_pack_image(self.root), 31, 30, root_size=2 * SECTOR)
        with self.assertRaisesRegex(ValueError, "overlapping disc file or metadata"):
            archive.Disc(self._write(image), descriptors=())


@unittest.skipUnless(RAW_DUMP.is_file(), f"raw dump is absent: {RAW_DUMP}")
class RawDumpTests(unittest.TestCase):
    """Read-only: opens the dump, never writes or copies it."""

    def test_the_raw_dump_opens_with_its_directories_below_the_descriptor(self) -> None:
        with archive.Disc(RAW_DUMP) as disc:
            self.assertEqual(disc.partition, RAW_DUMP_PARTITION)
            root_sector, root_size = struct.unpack("<II", disc.read(8, disc.partition + 0x10014))
            self.assertLess(root_sector, DESCRIPTOR_SECTOR)
            self.assertLess(disc.entries["vc_53450030"].sector, DESCRIPTOR_SECTOR)
            self.assertEqual(root_size, SECTOR)
            self.assertIn("default.xbe", disc.entries)
            self.assertEqual(tuple(disc.pack_extents), tuple(PACK_NAMES))
            self.assertTrue(disc.banks)


if __name__ == "__main__":
    unittest.main()
