"""A dump of an Xbox disc is not one canonical file, and we must accept them all.

This exists because users with perfectly legal copies were told their game was
"not the USA version". The editor pinned the whole-file SHA-256 and the exact
byte size of ONE rip of ONE disc, and it read the filesystem header at a fixed
offset that only an extracted ``.xiso`` puts it at. Three separate assumptions,
each of which rejects a legitimate dump:

* a raw disc read keeps the video partition, so the game partition starts at
  ``0x18300000`` rather than ``0`` and the header magic is not where we looked;
* different rippers keep or trim trailing padding, changing the file size;
* any of the above changes the whole-file hash without changing one game byte.

Everything here is synthetic. Real XDVDFS images are built in memory from
scratch, so this runs on a bare CI runner with no game data, which is precisely
why it can be trusted to keep running -- the tests that would have caught this
originally are all gated on retail data no runner has.

What is deliberately NOT relaxed: the archive packs extracted from an image are
still verified against their pinned hashes before anything is published, and
every writer still verifies the exact extents it touches. This file asserts that
the container may vary, not that the contents may.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
HEADER_OFFSET = 0x10000


def build_xdvdfs(
    files: dict[str, bytes], base_offset: int = 0, tail_pad: int = 0
) -> bytes:
    """A real, minimal XDVDFS image with its game partition at *base_offset*.

    Flat root only -- enough to exercise header discovery and extent maths,
    which is what varies between dumps. The directory is a right-leaning chain
    of 4-byte-aligned AVL nodes, which is a legal degenerate tree.
    """
    names = sorted(files)
    root_sector = (HEADER_OFFSET // SECTOR) + 1
    layout: dict[str, tuple[int, int]] = {}
    cursor = root_sector + 1
    for name in names:
        layout[name] = (cursor, len(files[name]))
        cursor += max(1, (len(files[name]) + SECTOR - 1) // SECTOR)

    nodes = bytearray()
    offsets: list[int] = []
    for name in names:
        offsets.append(len(nodes))
        sector, size = layout[name]
        nodes += struct.pack("<HHII", 0, 0, sector, size)
        nodes += bytes([0x20, len(name)])
        nodes += name.encode("ascii")
        while len(nodes) % 4:
            nodes += b"\0"
    for index, offset in enumerate(offsets[:-1]):
        struct.pack_into("<H", nodes, offset + 2, offsets[index + 1] // 4)

    header = bytearray(SECTOR)
    header[0:20] = MAGIC
    struct.pack_into("<II", header, 20, root_sector, len(nodes))
    header[SECTOR - 20:SECTOR] = MAGIC

    partition = bytearray((cursor + 1) * SECTOR)
    partition[HEADER_OFFSET:HEADER_OFFSET + SECTOR] = header
    partition[root_sector * SECTOR:root_sector * SECTOR + len(nodes)] = nodes
    for name in names:
        sector, size = layout[name]
        partition[sector * SECTOR:sector * SECTOR + size] = files[name]
    return bytes(base_offset) + bytes(partition) + bytes(tail_pad)


class XisoLayoutToleranceTests(unittest.TestCase):
    PAYLOAD = {
        "default.xbe": b"XBEH" + bytes(range(256)) * 24,
        "readme.txt": b"not the executable",
    }

    def _written(self, blob: bytes) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".iso", delete=False)
        self.addCleanup(lambda p=handle.name: os.path.exists(p) and os.unlink(p))
        handle.write(blob)
        handle.close()
        return Path(handle.name)

    def _parse(self, path: Path):
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        self.addCleanup(lambda fd=descriptor: os.close(fd))
        size = os.fstat(descriptor).st_size
        base = xiso.locate_xdvdfs_base(descriptor, size)
        entries, _ = xiso.parse_xdvdfs(descriptor, size, base)
        return descriptor, base, entries

    def test_every_known_dump_layout_is_read_identically(self) -> None:
        """The four partition bases, plus padding, must all yield the same files."""
        cases = {
            "extracted .xiso": (0x00000000, 0),
            "raw XGD1 dump": (0x18300000, 0),
            "raw XGD2 dump": (0x0FD90000, 0),
            "raw XGD3 dump": (0x02080000, 0),
            "trailing padding kept": (0x00000000, 3 * SECTOR),
        }
        for label, (base_offset, tail) in cases.items():
            with self.subTest(layout=label):
                path = self._written(
                    build_xdvdfs(self.PAYLOAD, base_offset, tail)
                )
                descriptor, base, entries = self._parse(path)
                self.assertEqual(base, base_offset, f"{label}: wrong partition base")
                self.assertEqual(set(entries), {"default.xbe", "readme.txt"})
                for name, expected in self.PAYLOAD.items():
                    entry = entries[name]
                    self.assertEqual(entry.size, len(expected))
                    self.assertEqual(
                        xiso.read_exact(descriptor, entry.byte_offset, entry.size),
                        expected,
                        f"{label}: {name} did not read back byte-identically",
                    )

    def test_the_two_geometries_users_actually_reported(self) -> None:
        """The exact shapes of the two dumps the editor turned away.

        Both were refused by the size gate before anything was even hashed, and
        the byte counts in the two screenshots identify them precisely:

        * ``7,825,162,240`` -- a full XGD1 disc read (3,820,880 x 2,048). The
          video partition is still in front, so the game partition starts at
          ``0x18300000`` and the header was not where the reader looked.
        * ``6,300,958,720`` -- the same layout as the project's own copy but
          224 sectors longer, i.e. an identical game repacked by a different
          tool. Only the padding differs.

        Sizes are asserted literally so that a future change reintroducing a
        size expectation fails here with the number a real user saw.
        """
        for label, total, base in (
            ("full XGD1 disc read", 7_825_162_240, 0x18300000),
            ("repacked, 224 extra sectors", 6_300_958_720, 0x00000000),
        ):
            with self.subTest(dump=label):
                body = build_xdvdfs(self.PAYLOAD, base)
                self.assertLess(len(body), total, "fixture larger than the reported dump")
                handle = tempfile.NamedTemporaryFile(suffix=".iso", delete=False)
                self.addCleanup(
                    lambda p=handle.name: os.path.exists(p) and os.unlink(p)
                )
                handle.truncate(total)          # sparse: the padding costs nothing
                handle.seek(base)
                handle.write(body[base:])
                handle.close()
                path = Path(handle.name)
                self.assertEqual(path.stat().st_size, total)

                descriptor, found, entries = self._parse(path)
                self.assertEqual(found, base)
                self.assertEqual(
                    xiso.read_exact(
                        descriptor,
                        entries["default.xbe"].byte_offset,
                        entries["default.xbe"].size,
                    ),
                    self.PAYLOAD["default.xbe"],
                )

    def test_byte_offset_accounts_for_the_partition_base(self) -> None:
        """The regression itself: sector maths that ignores the base reads garbage."""
        base_offset = 0x18300000
        path = self._written(build_xdvdfs(self.PAYLOAD, base_offset))
        _, base, entries = self._parse(path)
        entry = entries["default.xbe"]
        self.assertEqual(base, base_offset)
        self.assertEqual(entry.byte_offset, base_offset + entry.sector * SECTOR)
        self.assertNotEqual(
            entry.byte_offset,
            entry.sector * SECTOR,
            "byte_offset ignored the partition base, which is the original bug",
        )

    def test_a_non_disc_image_is_still_refused(self) -> None:
        """Tolerating layouts must not become tolerating anything at all."""
        for label, blob in {
            "empty": b"",
            "short": b"not an iso",
            "right size, no magic": bytes(HEADER_OFFSET + 4 * SECTOR),
        }.items():
            with self.subTest(image=label):
                path = self._written(blob)
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                self.addCleanup(lambda fd=descriptor: os.close(fd))
                size = os.fstat(descriptor).st_size
                with self.assertRaises(xiso.PatchError):
                    xiso.locate_xdvdfs_base(descriptor, size)

    def test_the_probe_lists_the_offsets_it_tried(self) -> None:
        """A refusal has to tell a user what was looked for, not just say no."""
        path = self._written(bytes(HEADER_OFFSET + 4 * SECTOR))
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        self.addCleanup(lambda fd=descriptor: os.close(fd))
        with self.assertRaises(xiso.PatchError) as caught:
            xiso.locate_xdvdfs_base(descriptor, os.fstat(descriptor).st_size)
        message = str(caught.exception)
        self.assertIn("0x18300000", message)
        self.assertIn("Xbox disc image", message)


class ContainedIdentityTests(unittest.TestCase):
    """Recognition must follow the executable inside, not the container."""

    def test_a_relaid_image_is_recognized_by_its_executable(self) -> None:
        from mod_editor.core import sources

        payload = b"XBEH" + bytes(range(256)) * 40
        import hashlib

        fingerprint = sources.ContainedFingerprint(
            "synthetic-test-title",
            sources.GameId.NFL2K5,
            "xiso",
            "default.xbe",
            hashlib.sha256(payload).hexdigest(),
            len(payload),
            "Synthetic fingerprint for layout-tolerance tests only.",
        )
        original = sources.CONTAINED_FINGERPRINTS
        sources.CONTAINED_FINGERPRINTS = (fingerprint,)
        self.addCleanup(setattr, sources, "CONTAINED_FINGERPRINTS", original)

        seen: list[tuple[str, int]] = []
        for base_offset in (0x00000000, 0x18300000, 0x02080000):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "dump.iso"
                path.write_bytes(
                    build_xdvdfs({"default.xbe": payload}, base_offset)
                )
                row = sources.contained_identity(path)
                self.assertIsNotNone(
                    row, f"base 0x{base_offset:X} was not recognized"
                )
                self.assertEqual(row.fingerprint_id, "synthetic-test-title")
                seen.append((row.fingerprint_id, path.stat().st_size))
        # Same game recognized across containers of very different sizes.
        self.assertEqual(len({size for _, size in seen}), len(seen))

    def test_a_wrong_executable_is_not_recognized(self) -> None:
        """The relaxation is about layout only; the wrong game still fails."""
        from mod_editor.core import sources

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "other.iso"
            path.write_bytes(build_xdvdfs({"default.xbe": b"some other game"}))
            self.assertIsNone(sources.contained_identity(path))

    def test_a_file_that_is_not_a_disc_image_is_not_recognized(self) -> None:
        from mod_editor.core import sources

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.txt"
            path.write_bytes(b"plainly not a disc image")
            self.assertIsNone(sources.contained_identity(path))


if __name__ == "__main__":
    unittest.main()
