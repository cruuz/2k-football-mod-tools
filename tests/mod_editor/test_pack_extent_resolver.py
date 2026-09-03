"""Archive packs are found through the disc's directory, never at a remembered byte.

This exists because of a public bug report. Build & Share -> Advanced preset died with

    ValueError: pack-0 schedule template is foreign: ROST stored size is not retail

on a legal USA retail ``.iso`` whose executable-only Basic preset built fine. ``default.xbe``
was resolved through the XDVDFS directory, so the executable patches worked; the schedule
step read pack 0 from the hard-coded byte 1,631,188,992 -- where the maintainer's rip keeps
it -- and on an image laid out differently it read 193 MB of something else and called the
template "foreign". Other writers carried the same assumption as ``PACK_SECTOR`` /
``XISO_PACK_BYTE_OFFSET`` / ``ABSOLUTE_XISO_SPAN`` constants.

Everything here is synthetic: a minimal XDVDFS image built in memory with ``default.xbe``
and ``vc_53450030/0`` at deliberately non-retail sectors, behind a redump-style game-partition
base (0x0FD90000), on a file far too small for the retail constant to point anywhere at all.
The test proves the shared resolver finds both files, that the studio recognises such a file
as a disc image, and that ``mod_build``'s schedule step reads and writes pack 0 where the
directory says -- with the heavy patch modules stubbed, because the point is the address.
"""

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
from mod_editor.core import mod_build, nfl2k5_throw_tuning as tt  # noqa: E402

SECTOR = xiso.SECTOR_SIZE
REDUMP_BASE = 0x0FD90000                       # XGD2 raw dump: video partition in front of the game
RETAIL_PACK0_BYTE = 1_631_188_992              # the number every writer used to assume
XBE_SECTOR, XBE_SIZE = 1_000, 4_096            # retail: sector 1,170
DIR_SECTOR = 900
PACK0_SECTOR, PACK0_SIZE = 5_000, 0x8000       # retail: sector 796,479
PACK9_SECTOR, PACK9_SIZE = 7_000, 0x2000       # retail: sector 35,531


def _node(sector: int, size: int, attributes: int, name: str) -> bytes:
    raw = struct.pack("<HHIIBB", 0, 0, sector, size, attributes, len(name)) + name.encode("ascii")
    return raw + b"\0" * (-len(raw) % 4)


def _directory(rows: list[tuple[int, int, int, str]]) -> bytes:
    """A flat XDVDFS directory as a right-leaning AVL chain (legal, and what the readers walk)."""

    nodes = [_node(*row) for row in rows]
    out = bytearray(b"".join(nodes))
    cursor = 0
    for index, node in enumerate(nodes[:-1]):
        struct.pack_into("<H", out, cursor + 2, (cursor + len(node)) // 4)
        cursor += len(node)
    return bytes(out)


def build_relocated_image(path: Path, *, pack0: bytes, base: int = REDUMP_BASE) -> None:
    """default.xbe + vc_53450030/{0,9} at non-retail sectors behind a redump-style base."""

    assert len(pack0) == PACK0_SIZE
    subdir = _directory([(PACK0_SECTOR, PACK0_SIZE, 0x80, "0"), (PACK9_SECTOR, PACK9_SIZE, 0x80, "9")])
    root = _directory([(XBE_SECTOR, XBE_SIZE, 0x80, "default.xbe"), (DIR_SECTOR, len(subdir), 0x10, "vc_53450030")])
    root_sector = (xiso.XDVDFS_HEADER_OFFSET // SECTOR) + 1
    header = bytearray(SECTOR)
    header[:20] = xiso.XDVDFS_MAGIC
    struct.pack_into("<II", header, 20, root_sector, len(root))
    header[-20:] = xiso.XDVDFS_MAGIC
    with path.open("wb") as stream:
        for sector, payload in (
            (xiso.XDVDFS_HEADER_OFFSET // SECTOR, bytes(header)),
            (root_sector, root),
            (DIR_SECTOR, subdir),
            (XBE_SECTOR, b"XBEH" + bytes(range(256)) * 15 + bytes(XBE_SIZE - 4 - 256 * 15)),
            (PACK0_SECTOR, pack0),
            (PACK9_SECTOR, bytes(range(256)) * (PACK9_SIZE // 256)),
        ):
            stream.seek(base + sector * SECTOR)
            stream.write(payload)


class PackExtentResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pack-extent-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pack0 = bytes((index * 7 + 3) & 0xFF for index in range(PACK0_SIZE))
        self.image = self.tmp / "relocated.iso"
        build_relocated_image(self.image, pack0=self.pack0)

    def _open(self) -> tuple[int, int]:
        fd = os.open(self.image, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        self.addCleanup(os.close, fd)
        return fd, os.fstat(fd).st_size

    def test_resolver_finds_pack_and_xbe_where_the_directory_puts_them(self) -> None:
        fd, size = self._open()
        self.assertEqual(xiso.locate_xdvdfs_base(fd, size), REDUMP_BASE)
        expected_pack0 = (REDUMP_BASE + PACK0_SECTOR * SECTOR, PACK0_SIZE)
        for spelling in ("0", 0, "vc_53450030/0", "VC_53450030/0"):
            with self.subTest(spelling=spelling):
                self.assertEqual(xiso.pack_extent(fd, size, spelling), expected_pack0)
        self.assertEqual(xiso.pack_extent(fd, size, "9"), (REDUMP_BASE + PACK9_SECTOR * SECTOR, PACK9_SIZE))
        self.assertEqual(xiso.pack_extent(fd, size, 9), (REDUMP_BASE + PACK9_SECTOR * SECTOR, PACK9_SIZE))
        self.assertEqual(xiso.xbe_extent(fd, size), (REDUMP_BASE + XBE_SECTOR * SECTOR, XBE_SIZE))
        # the resolved offset really addresses the pack bytes, and the retail byte is not even in the file
        self.assertEqual(xiso.read_exact(fd, expected_pack0[0], PACK0_SIZE), self.pack0)
        self.assertGreater(RETAIL_PACK0_BYTE, size)
        # a directory parsed once can be handed back in
        entries, _ = xiso.parse_xdvdfs(fd, size)
        self.assertEqual(xiso.pack_extent(fd, size, "0", entries=entries), expected_pack0)

    def test_missing_pack_is_a_clear_error_naming_the_path(self) -> None:
        fd, size = self._open()
        with self.assertRaisesRegex(xiso.PatchError, r"vc_53450030/5"):
            xiso.pack_extent(fd, size, "5")
        with self.assertRaisesRegex(xiso.PatchError, r"vc_53450030/C"):
            xiso.pack_extent(fd, size, 12)
        with self.assertRaisesRegex(xiso.PatchError, r"is a directory"):
            xiso.file_extent(fd, size, "vc_53450030")
        for bad in (16, -1, "zz", "other/0", True):
            with self.subTest(bad=bad), self.assertRaises(xiso.PatchError):
                xiso.pack_path(bad)

    def test_retail_sectors_are_provenance_only(self) -> None:
        self.assertEqual(xiso.RETAIL_PACK_SECTORS["0"] * SECTOR, RETAIL_PACK0_BYTE)
        self.assertEqual(set(xiso.RETAIL_PACK_SECTORS), set(xiso.PACK_NAMES))

    def test_studio_recognises_a_redump_layout_as_a_disc_image(self) -> None:
        self.assertTrue(tt.is_disc_image(self.image))
        fd, size = self._open()
        with self.assertRaisesRegex(Exception, "default.xbe inside the image is 4096 bytes"):
            tt.image_xbe_extent(fd, size)          # found, then honestly refused: not retail-sized
        xbe = self.tmp / "default.xbe"
        xbe.write_bytes(b"XBEH" + bytes(64))
        self.assertFalse(tt.is_disc_image(xbe))
        junk = self.tmp / "junk.iso"
        junk.write_bytes(bytes(0x20000))
        self.assertFalse(tt.is_disc_image(junk))

    def test_mod_build_schedule_step_uses_the_directory_not_the_constant(self) -> None:
        template, preseason = b"T" * 8, b"P" * 8
        seen: list[bytes] = []

        class Season:
            @staticmethod
            def simple_status(_xbe: bytes) -> str:
                return "applied"

        class Schedule:
            @staticmethod
            def encode_schedule(_doc):
                return template, {"validation": {"weeks": 18}}

            @staticmethod
            def encode_preseason(_doc):
                return preseason, {"games": 3}

            def pack_status(self, pack: bytes) -> dict:
                seen.append(bytes(pack))
                if pack == self_pack0:
                    return {"state": "retail"}
                return {"state": "foreign", "reason": "ROST stored size is not retail"}

            @staticmethod
            def apply_pack(pack: bytes, template_bytes: bytes, preseason: bytes = b"") -> tuple[bytes, dict]:
                patched = bytearray(pack)
                patched[100:108] = template_bytes
                patched[200:208] = preseason
                return bytes(patched), {"records": 272, "placement": 100}

        self_pack0 = self.pack0
        real_core, real_tools = mod_build._core_module, mod_build._tools_module

        def core(name: str):
            return Season() if name == "nfl2k5_season_length" else real_core(name)

        def tools(name: str):
            return Schedule() if name == "nfl2k5_franchise_schedule" else real_tools(name)

        def write_copy(source, target, **_kwargs):
            shutil.copyfile(source, target)
            return {}

        target = self.tmp / "built.iso"
        plan = mod_build.BuildPlan(str(self.image), str(target), season_2026=True)
        with (
            mock.patch.object(mod_build, "_core_module", core),
            mock.patch.object(mod_build, "_tools_module", tools),
            mock.patch.object(mod_build, "_xbe_bytes", lambda _p: b"XBEH"),
            mock.patch.object(mod_build, "inspect", lambda _p: {"stubbed": True}),
            mock.patch.object(mod_build, "PACK0_SIZE", PACK0_SIZE),
            mock.patch.object(mod_build.tt, "write_copy", write_copy),
        ):
            receipt = mod_build.build(plan)

        step = next(s for s in receipt["steps"] if s["step"] == "season_2026")
        pack0_at = REDUMP_BASE + PACK0_SECTOR * SECTOR
        self.assertEqual(step["schedule"]["pack0_byte_offset"], pack0_at)
        self.assertEqual(step["schedule"]["written_bytes"], 16)
        self.assertEqual(seen, [self.pack0], "the schedule step must read exactly the directory's pack 0")
        built = target.read_bytes()
        self.assertEqual(built[pack0_at + 100:pack0_at + 108], template)
        self.assertEqual(built[pack0_at + 200:pack0_at + 208], preseason)
        untouched = bytearray(self.image.read_bytes())
        untouched[pack0_at + 100:pack0_at + 108] = template
        untouched[pack0_at + 200:pack0_at + 208] = preseason
        self.assertEqual(built, bytes(untouched), "nothing outside the two template writes may change")

    def test_mod_build_refuses_an_image_whose_pack0_is_not_retail_sized(self) -> None:
        fd = os.open(self.image, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            with self.assertRaisesRegex(ValueError, r"vc_53450030/0 in this image is 32768 bytes"):
                mod_build._pack0_extent(fd)
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
