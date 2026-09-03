"""Synthetic NFL 2K5 XISO builder shared by the audio swap tests.

Builds a ~160 KiB image with a real XDVDFS root, a ``vc_53450030`` folder
holding three packs, and an outer-archive index whose entries are supplied by
the test.  The packs are also written loose under ``retail/vc_53450030`` so the
``--retail-packs`` gate can be exercised.  No game data is involved.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for candidate in (TOOLS, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_SLOT_COUNT, align_up  # noqa: E402

SECTOR = 2048
DEFAULT_PACK_SIZES = (0x4000, 0x2000, 0x2000)
DEFAULT_PACK_SECTORS = (64, 72, 76)


def dir_node(rows: list[tuple[int, int, int, str]]) -> bytes:
    """Serialise a flat XDVDFS directory (right-chained, 4-byte aligned nodes)."""

    nodes: list[bytes] = []
    positions: list[int] = []
    cursor = 0
    for sector, size, attributes, name in rows:
        raw = struct.pack("<HHIIBB", 0, 0, sector, size, attributes, len(name)) + name.encode("ascii")
        raw += b"\0" * (-len(raw) % 4)
        positions.append(cursor)
        nodes.append(raw)
        cursor += len(raw)
    out = bytearray(b"".join(nodes))
    for index in range(len(nodes) - 1):
        struct.pack_into("<H", out, positions[index] + 2, positions[index + 1] // 4)
    return bytes(out)


class SyntheticXiso:
    """The fixture image plus where every outer entry landed."""

    def __init__(self, directory: Path, entries: list[tuple[int, bytes]], *,
                 pack_sizes: tuple[int, ...] = DEFAULT_PACK_SIZES,
                 pack_sectors: tuple[int, ...] = DEFAULT_PACK_SECTORS) -> None:
        directory = Path(directory)
        self.path = directory / "fixture.xiso.iso"
        self.retail_packs = directory / "retail" / "vc_53450030"
        self.retail_packs.mkdir(parents=True, exist_ok=True)
        self.pack_sizes = tuple(pack_sizes)
        self.pack_sectors = tuple(pack_sectors)
        total = sum(self.pack_sizes)

        table_end = HEADER_SIZE + 12 * len(entries)
        cursor = align_up(table_end)
        self.entry_offsets: list[int] = []
        placed: list[tuple[int, int, bytes]] = []
        for index, (name_id, payload) in enumerate(entries):
            payload = bytes(payload)
            if index == len(entries) - 1 and cursor + len(payload) < total:
                payload = payload + bytes(total - cursor - len(payload))    # last entry reaches the end
            assert cursor + len(payload) <= total, "fixture entries exceed the packs"
            placed.append((name_id, cursor, payload))
            self.entry_offsets.append(cursor)
            cursor = align_up(cursor + len(payload))

        virtual = bytearray(total)
        header = struct.pack("<III", len(entries), 0, len(self.pack_sizes))
        header += struct.pack(f"<{PACK_SLOT_COUNT}I", *([size // ALIGNMENT for size in self.pack_sizes]
                                                       + [0] * (PACK_SLOT_COUNT - len(self.pack_sizes))))
        assert len(header) == HEADER_SIZE
        table = b"".join(struct.pack("<III", name_id, len(payload), offset // ALIGNMENT)
                         for name_id, offset, payload in placed)
        virtual[:len(header)] = header
        virtual[len(header):len(header) + len(table)] = table
        for _name_id, offset, payload in placed:
            virtual[offset:offset + len(payload)] = payload

        packs: list[bytes] = []
        at = 0
        for size in self.pack_sizes:
            packs.append(bytes(virtual[at:at + size]))
            at += size
        self.pack_names = "0123456789ABCDEF"[:len(packs)]
        for name, payload in zip(self.pack_names, packs):
            (self.retail_packs / name).write_bytes(payload)

        subdir = dir_node([(self.pack_sectors[index], self.pack_sizes[index], 0x80, name)
                           for index, name in enumerate(self.pack_names)])
        root = dir_node([(35, 16, 0x80, "default.xbe"), (34, len(subdir), 0x10, "vc_53450030")])
        image = bytearray(max(0x28000, (self.pack_sectors[-1] * SECTOR + self.pack_sizes[-1] + 0x800)))
        head = bytearray(0x800)
        head[:20] = xiso.XDVDFS_MAGIC
        struct.pack_into("<II", head, 20, 33, len(root))
        head[-20:] = xiso.XDVDFS_MAGIC
        image[0x10000:0x10800] = head
        image[33 * SECTOR:33 * SECTOR + len(root)] = root
        image[34 * SECTOR:34 * SECTOR + len(subdir)] = subdir
        image[35 * SECTOR:35 * SECTOR + 16] = b"XBEH" + bytes(12)
        for sector, payload in zip(self.pack_sectors, packs):
            image[sector * SECTOR:sector * SECTOR + len(payload)] = payload
        self.path.write_bytes(bytes(image))
        self.image = bytes(image)

    def pack_extent(self, name: str) -> int:
        """Absolute image offset of a pack."""

        return self.pack_sectors[self.pack_names.index(name)] * SECTOR

    def virtual_to_image(self, virtual_offset: int) -> int:
        """Absolute image offset of a virtual archive offset (must not cross a seam)."""

        at = 0
        for name, size in zip(self.pack_names, self.pack_sizes):
            if at <= virtual_offset < at + size:
                return self.pack_extent(name) + (virtual_offset - at)
            at += size
        raise AssertionError("virtual offset outside the packs")
