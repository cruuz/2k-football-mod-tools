"""Tests for the Defensive End -> EDGE rename (executable + disc text)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_edge_rename as edge  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

IMAGE_BASE = edge.IMAGE_BASE
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
RETAIL_PACK_C = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/C")
RETAIL_PACK_0 = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")

# synthetic sections: (index, virtual address, raw size); raw data is appended behind the throw fixture
EDGE_SECTIONS = (
    (12, 0x004F2000, 0x00023000),   # .rdata window: pointer tables 0x4F26C8.. and slot records ..0x5147D8
    (13, 0x00A89000, 0x0003A000),   # .data window: legend table 0xA89938 .. franchise table 0xAC2698
    (14, 0x00E67000, 0x00056000),   # .string_ window: 0xE677E0 .. 0xEBBFD8
)


def _u16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    return raw + b"\0" * (slot - len(raw))


def build_edge_synthetic_xbe() -> bytes:
    """The throw-tuning fixture plus .rdata/.data/.string_ windows seeded with the retail EDGE sites."""

    buf = bytearray(_build_synthetic_xbe())
    table = struct.unpack_from("<I", buf, 0x120)[0] - IMAGE_BASE
    raw_cursor = len(buf)
    layout = {}
    for index, va, size in EDGE_SECTIONS:
        raw_cursor = (raw_cursor + 0xFFF) & ~0xFFF
        layout[index] = (va, raw_cursor, size)
        raw_cursor += size
    buf.extend(b"\0" * (raw_cursor - len(buf)))
    for index, (va, raw, size) in layout.items():
        header = table + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\0" * 20]
        fields[1], fields[3], fields[4] = va, raw, size
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)

    def off(target_va: int) -> int:
        if IMAGE_BASE <= target_va < IMAGE_BASE + 0xCC4:
            return target_va - IMAGE_BASE
        for va, raw, size in layout.values():
            if va <= target_va < va + size:
                return raw + (target_va - va)
        raise AssertionError(f"VA 0x{target_va:x} outside the synthetic windows")

    buf[0xC88: 0xC88 + len(edge.RETAIL_LOGO_C88)] = edge.RETAIL_LOGO_C88
    for _label, ptr_va, old, _new in edge.POINTER_SITES:
        struct.pack_into("<I", buf, off(ptr_va), old)
    for va in edge.SINGULAR_SITES:
        buf[off(va): off(va) + edge.SINGULAR_SLOT] = _u16("Defensive End", edge.SINGULAR_SLOT)
    for va in edge.PLURAL_SITES:
        buf[off(va): off(va) + edge.PLURAL_SLOT] = _u16("Defensive Ends", edge.PLURAL_SLOT)
    for _label, va, abbrev, old_long, _new_long in edge.SLOT_RECORDS:
        record = _u16(abbrev, 2 * edge.SLOT_ABBREV_WCHARS) + _u16(old_long, 2 * edge.SLOT_LONG_WCHARS)
        buf[off(va): off(va) + len(record)] = record
    # retired strings (the retail "DE" entries and the legend) so the windows look like the real pool
    retired = {0x00E69C4C: "DE", 0x00E6C290: "DE", 0x00E83D64: "DE", 0x00E87ED0: "DE", 0x00E677E0: "|CIRCLE|SWAP DE"}
    for va, text in retired.items():
        raw = _u16(text, (len(text.encode("utf-16le")) + 2 + 3) & ~3)
        buf[off(va): off(va) + len(raw)] = raw
    for index, (va, raw, size) in layout.items():
        header = table + index * strength.SECTION_HEADER_SIZE
        buf[header + 36: header + 56] = hashlib.sha1(  # nosec B324
            struct.pack("<I", size) + buf[raw: raw + size]).digest()
    return bytes(buf)


def _string_at(payload: bytes, va: int) -> str:
    off = edge._offset(payload, va)
    end = off
    while payload[end: end + 2] != b"\0\0":
        end += 2
    return payload[off: end].decode("utf-16le")


class LayoutInvariantTests(unittest.TestCase):
    def test_host_string_sits_after_the_draft_cave_inside_the_logo(self) -> None:
        self.assertGreaterEqual(edge.LEGEND_VA, draft.CAVE_VA + len(draft.cave_bytes()))
        self.assertLessEqual(edge.LEGEND_VA + len(edge.legend_bytes()), edge.LOGO_END_VA)
        self.assertEqual(edge.LEGEND_VA % 4, 0)

    def test_legend_tail_is_the_abbreviation(self) -> None:
        legend = edge.legend_bytes()
        self.assertEqual(legend[edge.EDGE_VA - edge.LEGEND_VA:].decode("utf-16le").rstrip("\0"), "EDGE")
        self.assertEqual(legend.decode("utf-16le").rstrip("\0"), "|CIRCLE|SWAP EDGE")
        self.assertEqual(len(legend), len(edge.RETAIL_LOGO_C88))

    def test_every_replacement_fits_its_slot(self) -> None:
        self.assertLessEqual(len("Edge Rusher".encode("utf-16le")) + 2, edge.SINGULAR_SLOT)
        self.assertLessEqual(len("Edge Rushers".encode("utf-16le")) + 2, edge.PLURAL_SLOT)
        self.assertLessEqual(len("EDGE".encode("utf-16le")) + 2, 2 * edge.SLOT_ABBREV_WCHARS)
        self.assertLessEqual(len("RIGHT EDGE RUSHER".encode("utf-16le")) + 2, 2 * edge.SLOT_LONG_WCHARS)
        self.assertEqual(len(edge.ROST_AFTER), edge.ROST_ALLOCATION)
        self.assertEqual(len(edge.ROST_BEFORE), edge.ROST_ALLOCATION)
        self.assertEqual(len(edge.ROST_LAST_NAME_OFFSETS), 247)
        self.assertEqual(len(set(edge.ROST_LAST_NAME_OFFSETS)), 247)
        for _label, _off, allocation, _sha, text in edge.TRIV_SITES:
            self.assertLessEqual(len(text.encode("utf-16le")) + 2, allocation)
            self.assertIn("Edge Rusher", text)
            self.assertNotIn("Defensive End", text)


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_edge_synthetic_xbe()

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(edge.status(self.payload), "retail")
        patched, receipt = edge.apply(self.payload)
        self.assertEqual(edge.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [12, 13, 14])
        self.assertEqual(len(receipt["edits"]), 1 + 6 + 4 + 14 + 4)
        self.assertEqual(receipt["changed_bytes"], 399)
        self.assertEqual(_string_at(patched, edge.EDGE_VA), "EDGE")
        self.assertEqual(_string_at(patched, edge.LEGEND_VA), "|CIRCLE|SWAP EDGE")
        for _label, ptr_va, _old, new in edge.POINTER_SITES:
            target = struct.unpack_from("<I", patched, edge._offset(patched, ptr_va))[0]
            self.assertEqual(target, new)
            self.assertEqual(_string_at(patched, target), "EDGE" if new == edge.EDGE_VA else "|CIRCLE|SWAP EDGE")
        for va in edge.SINGULAR_SITES:
            self.assertEqual(_string_at(patched, va), "Edge Rusher")
        for va in edge.PLURAL_SITES:
            self.assertEqual(_string_at(patched, va), "Edge Rushers")
        for _label, va, _abbrev, _old, new_long in edge.SLOT_RECORDS:
            self.assertEqual(_string_at(patched, va), "EDGE")
            self.assertEqual(_string_at(patched, va + 2 * edge.SLOT_ABBREV_WCHARS), new_long)
        with self.assertRaises(edge.EdgeRenameError):
            edge.apply(patched)

    def test_digests_are_repinned_for_every_touched_section(self) -> None:
        patched, _receipt = edge.apply(self.payload)
        for section in strength._sections(patched):
            if section.index in (12, 13, 14):
                self.assertEqual(section.stored_digest, strength.section_digest(patched, section))
        # untouched sections keep their digest bytes
        for before, after in zip(strength._sections(self.payload), strength._sections(patched)):
            if before.index not in (12, 13, 14):
                self.assertEqual(before.stored_digest, after.stored_digest)

    def test_only_the_listed_bytes_change(self) -> None:
        patched, receipt = edge.apply(self.payload)
        allowed = set()
        for item in receipt["edits"]:
            start = int(item["file_offset"], 16)
            allowed.update(range(start, start + len(bytes.fromhex(item["after"]))))
        for section in strength._sections(self.payload):
            if section.index in (12, 13, 14):
                allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= allowed)

    def test_foreign_bytes_are_refused(self) -> None:
        buf = bytearray(self.payload)
        buf[0xC88] ^= 0xFF
        self.assertEqual(edge.status(bytes(buf)), "foreign")
        with self.assertRaises(edge.EdgeRenameError):
            edge.apply(bytes(buf))
        buf = bytearray(self.payload)
        off = edge._offset(self.payload, edge.SINGULAR_SITES[2])
        buf[off + 4] ^= 0x20
        self.assertEqual(edge.status(bytes(buf)), "foreign")

    def test_write_copy_applies_the_rename_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(self.payload)
            target = Path(tmp) / "edge.xbe"
            receipt = tt.write_xbe_copy(source, target, edge_rename=True)
            self.assertEqual(receipt["edge_rename"], "applied")
            self.assertEqual(receipt["catch_slider"], "retail")
            self.assertEqual(receipt["edge_rename_patch"]["changed_bytes"], 399)
            report = tt.read_xbe(target)
            self.assertEqual(report["edge_rename"], "applied")
            self.assertEqual(edge.status(target.read_bytes()), "applied")
            with self.assertRaises(tt.ThrowTuningError):
                tt.write_xbe_copy(target, Path(tmp) / "again.xbe", edge_rename=True)
            both = Path(tmp) / "both.xbe"
            receipt = tt.write_xbe_copy(source, both, settings=tt.TuningSettings(80.0, 0.0, True),
                                        catch_slider=True, edge_rename=True)
            self.assertEqual(receipt["edge_rename"], "applied")
            self.assertEqual(receipt["catch_slider"], "applied")


class DiscSiteTests(unittest.TestCase):
    def test_site_states_and_summary(self) -> None:
        applied_triv = {label: edge._triv_after(text, allocation)
                        for label, _off, allocation, _sha, text in edge.TRIV_SITES}

        def read(pack: str, offset: int, size: int) -> bytes:
            if pack == edge.ROST_PACK:
                index = edge.ROST_LAST_NAME_OFFSETS.index(offset)
                return edge.ROST_BEFORE if index % 2 == 0 else edge.ROST_AFTER
            label = next(l for l, o, *_ in edge.TRIV_SITES if o == offset)
            return applied_triv[label] if label.endswith("494") else b"\0" * size

        states = edge.disc_site_states(read)
        summary = edge.summarize_disc(states)
        self.assertEqual(summary["rost"], {"retail": 124, "applied": 123, "foreign": 0})
        self.assertEqual(summary["triv"], {"retail": 0, "applied": 1, "foreign": 1})
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(edge.summarize_disc({"rost": [("a", 0, "retail")]})["status"], "retail")
        self.assertEqual(edge.summarize_disc({"rost": [("a", 0, "applied")]})["status"], "applied")
        self.assertEqual(edge.summarize_disc({"rost": [("a", 0, "foreign")]})["status"], "foreign")

    def test_apply_disc_rewrites_only_retail_sites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "fake.iso"
            rost_size = max(edge.ROST_LAST_NAME_OFFSETS) + 0x40
            triv_size = max(off + alloc for _l, off, alloc, _s, _t in edge.TRIV_SITES) + 0x40
            fd = os.open(image, os.O_RDWR | os.O_CREAT)
            try:
                os.truncate(fd, rost_size + triv_size)  # sparse: only the seeded spans hold data
                for index, off in enumerate(edge.ROST_LAST_NAME_OFFSETS):
                    os.pwrite(fd, edge.ROST_BEFORE if index != 5 else b"\x41" * 16, off)
                label, off, allocation, _sha, text = edge.TRIV_SITES[1]
                os.pwrite(fd, edge._triv_after(text, allocation), rost_size + off)   # already applied
                entries = {
                    edge.ROST_PACK: SimpleNamespace(byte_offset=0, size=rost_size),
                    edge.TRIV_PACK: SimpleNamespace(byte_offset=rost_size, size=triv_size),
                }
                before = edge.disc_status(fd, entries)
                self.assertEqual(before["rost"], {"retail": 246, "applied": 0, "foreign": 1})
                self.assertEqual(before["triv"], {"retail": 0, "applied": 1, "foreign": 1})
                receipt = edge.apply_disc(fd, entries, os.pwrite)
                self.assertEqual(len(receipt["written"]), 246)
                self.assertEqual(receipt["changed_bytes"], 246 * 16)
                self.assertEqual(receipt["after"]["rost"], {"retail": 0, "applied": 246, "foreign": 1})
                self.assertEqual(os.pread(fd, 16, edge.ROST_LAST_NAME_OFFSETS[5]), b"\x41" * 16)
                self.assertEqual(os.pread(fd, 16, edge.ROST_LAST_NAME_OFFSETS[0]).decode("utf-16le").rstrip("\0"), "Edge")
                again = edge.apply_disc(fd, entries, os.pwrite)
                self.assertEqual(again["written"], [])
            finally:
                os.close(fd)

    def test_missing_pack_is_refused(self) -> None:
        with self.assertRaises(edge.EdgeRenameError):
            edge.disc_status(0, {})


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not available")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_reads_as_retail_and_patches_cleanly(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(edge.status(payload), "retail")
        patched, receipt = edge.apply(payload)
        self.assertEqual(edge.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], 399)
        self.assertEqual(_string_at(patched, edge.EDGE_VA), "EDGE")
        # the .string_ section no longer carries the long name anywhere
        self.assertNotIn("Defensive End".encode("utf-16le"), patched)
        self.assertNotIn("DEF END".encode("utf-16le"), patched)
        # every abbreviation table entry resolves to EDGE; the retired "DE" strings are unreferenced
        for _label, ptr_va, old, _new in edge.POINTER_SITES:
            self.assertNotIn(struct.pack("<I", old), patched)
        for section in strength._sections(patched):
            self.assertEqual(section.stored_digest, strength.section_digest(patched, section),
                             f"section {section.index} digest")
        # the position-enum accessor still returns the other sixteen retail abbreviations
        table = edge._offset(patched, 0x004F26D0)
        names = [_string_at(patched, struct.unpack_from("<I", patched, table + 4 * i)[0]) for i in range(17)]
        self.assertEqual(names, ["QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB",
                                 "C", "G", "T", "DT", "EDGE"])

    @unittest.skipUnless(RETAIL_PACK_C.is_file() and RETAIL_PACK_0.is_file(), "retail packs not available")
    def test_retail_packs_hold_the_disc_sites(self) -> None:
        with open(RETAIL_PACK_0, "rb") as pack0, open(RETAIL_PACK_C, "rb") as pack_c:
            def read(pack: str, offset: int, size: int) -> bytes:
                handle = pack0 if pack == edge.ROST_PACK else pack_c
                handle.seek(offset)
                return handle.read(size)
            summary = edge.summarize_disc(edge.disc_site_states(read))
        self.assertEqual(summary["status"], "retail")
        self.assertEqual(summary["rost"]["retail"], 247)
        self.assertEqual(summary["triv"]["retail"], 2)


if __name__ == "__main__":
    unittest.main()
