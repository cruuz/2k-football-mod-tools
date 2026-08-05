"""Discs that are legal but unusual must not abort the whole listing.

The reader is used to identify and browse a user's own disc image, and three
shapes it rejected are not corruption at all:

* an **empty directory**, which is legal and simply carries no extent. The
  reader demanded every directory have one, so a disc containing one empty
  folder failed to parse at all.
* a **non-ASCII filename**, where one accented character aborted every other
  entry on the disc along with it.
* a **deeply nested tree**, which recursed until the interpreter stack gave out
  and raised ``RecursionError`` -- a type that escapes every caller's
  ``except PatchError`` and surfaces as a crash rather than a refusal.

None of these relax a safety property. Extents are still bounds-checked against
the image, cycles are still refused, and the node budget still applies.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402

SECTOR = xiso.SECTOR_SIZE


def _entry(name: bytes, sector: int, size: int, attributes: int) -> tuple:
    """One directory record, described; offsets are filled in when linked."""

    return (name, sector, size, attributes)


def _pack(name: bytes, sector: int, size: int, attributes: int,
          left: int, right: int) -> bytes:
    record = struct.pack("<HHII", left, right, sector, size) + bytes(
        [attributes, len(name)]
    ) + name
    while len(record) % 4:
        record += b"\x00"
    return record


def _link(records: list[tuple]) -> bytes:
    """Lay records out as a right-leaning AVL chain.

    Entries are not a flat list: each carries left/right offsets in 4-byte
    units, and a reader only sees what the tree reaches. Chaining to the right
    is the simplest shape that reaches every record.
    """

    sizes = []
    for name, _sector, _size, _attributes in records:
        length = 14 + len(name)
        sizes.append(length + (-length % 4))

    offsets = []
    running = 0
    for length in sizes:
        offsets.append(running)
        running += length

    out = b""
    for index, (name, sector, size, attributes) in enumerate(records):
        right = offsets[index + 1] // 4 if index + 1 < len(records) else 0
        out += _pack(name, sector, size, attributes, 0, right)
    return out


class _Image:
    """A minimal XDVDFS image built in memory, one directory per sector."""

    def __init__(self) -> None:
        self.sectors: dict[int, bytes] = {}
        self.next_sector = 40

    def add_directory(self, records) -> tuple[int, int]:
        payload = _link(records) if records and isinstance(records[0], tuple) \
            else b"".join(records)
        sector = self.next_sector
        self.next_sector += max(1, (len(payload) + SECTOR - 1) // SECTOR)
        self.sectors[sector] = payload
        return sector, len(payload)

    def write(self, path: Path, root_sector: int, root_size: int) -> Path:
        header = bytearray(0x800)
        header[0:20] = xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, root_sector, root_size)
        header[-20:] = xiso.XDVDFS_MAGIC

        total = (self.next_sector + 8) * SECTOR
        blob = bytearray(total)
        blob[xiso.XDVDFS_HEADER_OFFSET:xiso.XDVDFS_HEADER_OFFSET + 0x800] = header
        for sector, payload in self.sectors.items():
            start = sector * SECTOR
            blob[start:start + len(payload)] = payload
        path.write_bytes(bytes(blob))
        return path


def _parse(path: Path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return xiso.parse_xdvdfs(descriptor, os.fstat(descriptor).st_size, 0)
    finally:
        os.close(descriptor)


class EmptyDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="xdvdfs-empty-"))

    def test_an_empty_directory_does_not_abort_the_listing(self) -> None:
        image = _Image()
        # A file whose bytes exist, plus a directory declaring no extent.
        data_sector, _ = image.add_directory([b"\x00" * 16])
        root_sector, root_size = image.add_directory([
            _entry(b"default.xbe", data_sector, 16, 0x80),
            _entry(b"emptydir", 0, 0, 0x10),
        ])
        path = image.write(self.root / "disc.iso", root_sector, root_size)

        entries, _meta = _parse(path)
        self.assertIn("default.xbe", entries)
        self.assertIn("emptydir", entries)
        self.assertTrue(entries["emptydir"].attributes & 0x10)

    def test_the_empty_directory_is_listed_rather_than_descended(self) -> None:
        image = _Image()
        root_sector, root_size = image.add_directory([
            _entry(b"emptydir", 0, 0, 0x10),
        ])
        path = image.write(self.root / "disc.iso", root_sector, root_size)
        entries, meta = _parse(path)
        self.assertEqual(set(entries), {"emptydir"})
        self.assertEqual(meta["directory_extents"], 1)


class FilenameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="xdvdfs-name-"))

    def test_a_non_ascii_name_no_longer_kills_the_disc(self) -> None:
        image = _Image()
        data_sector, _ = image.add_directory([b"\x00" * 16])
        root_sector, root_size = image.add_directory([
            _entry(b"caf\xe9.bin", data_sector, 16, 0x80),
            _entry(b"default.xbe", data_sector, 16, 0x80),
        ])
        path = image.write(self.root / "disc.iso", root_sector, root_size)

        entries, _meta = _parse(path)
        # The point is that the ordinary file survived the odd one.
        self.assertIn("default.xbe", entries)
        self.assertEqual(len(entries), 2)

    def test_the_odd_name_is_byte_reversible(self) -> None:
        """latin-1 maps every byte one-to-one, so nothing is guessed at."""

        image = _Image()
        data_sector, _ = image.add_directory([b"\x00" * 16])
        root_sector, root_size = image.add_directory([
            _entry(b"caf\xe9.bin", data_sector, 16, 0x80),
        ])
        path = image.write(self.root / "disc.iso", root_sector, root_size)
        entries, _meta = _parse(path)
        name = next(iter(entries.values())).path
        self.assertEqual(name.encode("latin-1"), b"caf\xe9.bin")

    def test_separators_and_nulls_are_still_refused(self) -> None:
        """Leniency about encoding is not leniency about path traversal."""

        for bad in (b"a/b.bin", b"a\\b.bin", b"a\x00b.bin"):
            with self.subTest(name=bad):
                image = _Image()
                data_sector, _ = image.add_directory([b"\x00" * 16])
                root_sector, root_size = image.add_directory([
                    _entry(bad, data_sector, 16, 0x80),
                ])
                path = image.write(self.root / f"disc{len(bad)}.iso",
                                   root_sector, root_size)
                with self.assertRaises(xiso.PatchError):
                    _parse(path)


class DepthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="xdvdfs-depth-"))

    def test_a_too_deep_tree_is_refused_as_a_patch_error(self) -> None:
        """Not RecursionError, which callers do not catch."""

        image = _Image()
        # Build downward: each level is a directory holding the next. The
        # innermost must be a real directory or the walk stops on bad bytes
        # before it ever reaches the depth bound.
        data_sector, _ = image.add_directory([b"\x00" * 16])
        sector, size = image.add_directory([
            _entry(b"leaf.bin", data_sector, 16, 0x80),
        ])
        for level in range(xiso.MAX_DIRECTORY_DEPTH + 8):
            sector, size = image.add_directory([
                _entry(f"d{level}".encode("ascii"), sector, size, 0x10),
            ])
        path = image.write(self.root / "deep.iso", sector, size)

        with self.assertRaises(xiso.PatchError) as caught:
            _parse(path)
        self.assertIn("too deep", str(caught.exception))

    def test_ordinary_nesting_still_parses(self) -> None:
        image = _Image()
        data_sector, _ = image.add_directory([b"\x00" * 16])
        sector, size = image.add_directory([
            _entry(b"leaf.bin", data_sector, 16, 0x80),
        ])
        for level in range(6):
            sector, size = image.add_directory([
                _entry(f"d{level}".encode("ascii"), sector, size, 0x10),
            ])
        path = image.write(self.root / "shallow.iso", sector, size)
        entries, _meta = _parse(path)
        self.assertEqual(len(entries), 7)  # six directories plus the leaf


def _link_balanced(records: list[tuple]) -> bytes:
    """Lay records out as a balanced tree, the shape a real mastering tool writes.

    ``_link`` chains every record to the right, which is the worst case for a
    recursive reader. A genuine disc stores a balanced AVL tree, so this is what
    the depth bound has to keep accepting.
    """

    lengths = {14 + len(name) + (-(14 + len(name)) % 4) for name, *_rest in records}
    if len(lengths) != 1:
        raise ValueError("balanced layout needs equal-length names")
    stride = lengths.pop()

    # A child pointer of 0 means "no child", so offset 0 cannot belong to any
    # node that is somebody's child. Placing records in pre-order puts the tree
    # root there, which is where a reader starts anyway.
    slot: dict[int, int] = {}
    children: dict[int, tuple[int | None, int | None]] = {}

    def build(low: int, high: int) -> int | None:
        if low >= high:
            return None
        middle = (low + high) // 2
        slot[middle] = len(slot)
        children[middle] = (build(low, middle), build(middle + 1, high))
        return middle

    build(0, len(records))

    def pointer(index: int | None) -> int:
        return 0 if index is None else slot[index] * stride // 4

    packed = [b""] * len(records)
    for index, (name, sector, size, attributes) in enumerate(records):
        left, right = children[index]
        packed[slot[index]] = _pack(
            name, sector, size, attributes, pointer(left), pointer(right)
        )
    return b"".join(packed)


def _many(count: int) -> list[tuple]:
    return [_entry(f"f{index:05d}".encode("ascii"), 0, 0, 0x80)
            for index in range(count)]


class UnbalancedTreeTests(unittest.TestCase):
    """A long chain must be refused, not crash the interpreter.

    The reader bounds directory *nesting* and total node count, but those are
    not the same thing as the interpreter stack: the AVL walk inside a single
    directory recurses per node, so a directory holding one long chain reaches
    thousands of frames while nested zero levels deep and well inside the node
    budget. A truncated or badly mastered image produces exactly that shape.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="xdvdfs-chain-"))

    def test_a_long_chain_is_refused_rather_than_overflowing_the_stack(self) -> None:
        image = _Image()
        # Comfortably past CPython's default 1000-frame limit, and still far
        # inside MAX_DIRECTORY_NODES, so this isolates the recursion bound.
        sector, size = image.add_directory(_many(1200))
        path = image.write(self.root / "chain.iso", sector, size)
        with self.assertRaises(xiso.PatchError):
            _parse(path)

    def test_a_balanced_directory_of_the_same_size_still_parses(self) -> None:
        """The bound must reject the degenerate shape, not large directories."""

        image = _Image()
        records = _many(1200)
        sector, size = image.add_directory([_link_balanced(records)])
        path = image.write(self.root / "balanced.iso", sector, size)
        entries, _meta = _parse(path)
        self.assertEqual(len(entries), 1200)


class RealDiscTests(unittest.TestCase):
    """The changes must not alter what a genuine disc produces."""

    SOURCE = _REPO_ROOT / "ESPN NFL 2K5 (USA).xiso.iso"

    @unittest.skipUnless(SOURCE.is_file(), "retail 2K5 image not present")
    def test_the_retail_listing_is_unchanged(self) -> None:
        descriptor = os.open(self.SOURCE, os.O_RDONLY)
        try:
            entries, meta = xiso.parse_xdvdfs(
                descriptor, os.fstat(descriptor).st_size
            )
        finally:
            os.close(descriptor)
        self.assertEqual(len(entries), 20)
        self.assertEqual(meta["directory_nodes"], 20)
        self.assertIn("default.xbe", entries)


if __name__ == "__main__":
    unittest.main()
