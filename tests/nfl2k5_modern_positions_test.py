"""Tests for the modern-era defensive depth-chart labels (SAM/MIKE/WILL, NT, 3-4 EDGE)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_edge_rename as edge  # noqa: E402
from mod_editor.core import nfl2k5_modern_positions as modern  # noqa: E402
from nfl2k5_edge_rename_test import build_edge_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")

# retail (position, chain) of every record in the two defensive units, from the retail .rdata dump
RETAIL_43 = [(0x10, 0), (0xF, 0), (0xF, 1), (0x10, 1), (0xA, 1), (0xB, 0), (0xA, 0), (4, 1), (4, 0), (6, 0), (5, 0)]
RETAIL_34 = [(0x10, 0), (0xF, 0), (0x10, 1), (0xB, 1), (0xB, 0), (0xA, 1), (0xA, 0), (4, 1), (4, 0), (6, 0), (5, 0)]
RETAIL_43_TEXT = [("LDE", "LEFT DEF END"), ("LDT", "LEFT DEF TACKLE"), ("RDT", "RIGHT DEF TACKLE"),
                  ("RDE", "RIGHT DEF END"), ("ROLB", "RIGHT OUTSIDE LINE BACKER"), ("ILB", "INSIDE LINE BACKER"),
                  ("LOLB", "LEFT OUTSIDE LINE BACKER"), ("RCB", "RIGHT CORNERBACK"), ("LCB", "LEFT CORNERBACK"),
                  ("SS", "STRONG SAFETY"), ("FS", "FREE SAFETY")]
RETAIL_34_TEXT = [("LDE", "LEFT DEF END"), ("DT", "DEF TACKLE"), ("RDE", "RIGHT DEF TACKLE"),
                  ("RILB", "RIGHT INSIDE LINE BACKER"), ("LILB", "LEFT INSIDE LINE BACKER"),
                  ("ROLB", "RIGHT OUTSIDE LINE BACKER"), ("LOLB", "LEFT OUTSIDE LINE BACKER"),
                  ("RCB", "RIGHT CORNERBACK"), ("LCB", "LEFT CORNERBACK"), ("SS", "STRONG SAFETY"),
                  ("FS", "FREE SAFETY")]


def build_synthetic_xbe() -> bytes:
    """The EDGE fixture (which already carries the four end records) plus every other record of
    the two defensive units, seeded with the retail text and pool fields."""

    buf = bytearray(build_edge_synthetic_xbe())
    for unit, texts, pools in ((modern.UNIT_43, RETAIL_43_TEXT, RETAIL_43), (modern.UNIT_34, RETAIL_34_TEXT, RETAIL_34)):
        for slot in range(modern.SLOTS_PER_UNIT):
            off = modern._offset(bytes(buf), modern.record_va(unit, slot))
            buf[off: off + modern.SLOT_TEXT_BYTES] = modern.slot_text(*texts[slot])
            struct.pack_into("<II", buf, off + modern.SLOT_TEXT_BYTES, *pools[slot])
    # re-pin the .rdata digest the way the fixture builder does
    table = struct.unpack_from("<I", buf, 0x120)[0] - modern.IMAGE_BASE
    for section in strength._sections(bytes(buf)):
        header = table + section.index * strength.SECTION_HEADER_SIZE
        if section.raw_size:
            buf[header + 36: header + 56] = hashlib.sha1(  # nosec B324
                struct.pack("<I", section.raw_size) + buf[section.raw_offset: section.raw_offset + section.raw_size]).digest()
    return bytes(buf)


def _labels(payload: bytes, unit: int) -> list[tuple[str, str]]:
    return [(r["abbreviation"], r["long_name"]) for r in
            (modern.read_record(payload, unit, s) for s in range(modern.SLOTS_PER_UNIT))]


def _pools(payload: bytes, unit: int) -> list[tuple[int, int]]:
    return [(r["position"], r["chain"]) for r in
            (modern.read_record(payload, unit, s) for s in range(modern.SLOTS_PER_UNIT))]


class LayoutInvariantTests(unittest.TestCase):
    def test_every_label_fits_its_field(self) -> None:
        for site in modern.SITES:
            abbrev, long_name = site.after
            self.assertLessEqual(len(abbrev), modern.SLOT_ABBREV_WCHARS - 1, site.label)
            self.assertLessEqual(len(long_name), modern.SLOT_LONG_WCHARS - 1, site.label)
            self.assertEqual(len(modern.slot_text(abbrev, long_name)), modern.SLOT_TEXT_BYTES)
            for before in site.before:
                self.assertEqual(len(modern.slot_text(*before)), modern.SLOT_TEXT_BYTES)

    def test_sites_are_distinct_records_inside_the_defensive_units(self) -> None:
        vas = [site.va for site in modern.SITES]
        self.assertEqual(len(vas), len(set(vas)))
        for site in modern.SITES:
            self.assertIn(site.unit, (modern.UNIT_43, modern.UNIT_34))
            self.assertEqual((site.va - modern.SLOT_TABLE_VA) % modern.SLOT_RECORD_STRIDE, 0)
            self.assertIn(site.label, modern.EXPECTED_POOLS)

    def test_optional_sites_are_exactly_the_edge_renames_end_records(self) -> None:
        optional = {site.va for site in modern.SITES if site.optional}
        edge_unit2 = {va for label, va, *_ in edge.SLOT_RECORDS if label.startswith("slot_unit2")}
        self.assertEqual(optional, edge_unit2)
        # and the default profile never touches a record the EDGE rename writes
        default = {site.va for site in modern.selected_sites(False)}
        self.assertFalse(default & {va for _l, va, *_ in edge.SLOT_RECORDS})

    def test_the_43_and_34_labels_read_as_the_owner_asked(self) -> None:
        by_label = {site.label: site.after for site in modern.SITES}
        self.assertEqual(by_label["43_sam"][0], "SAM")
        self.assertEqual(by_label["43_mike"][0], "MIKE")
        self.assertEqual(by_label["43_will"][0], "WILL")
        self.assertEqual(by_label["34_edge_left"][0], "EDGE")
        self.assertEqual(by_label["34_edge_right"][0], "EDGE")
        self.assertEqual(by_label["34_nt"], ("NT", "NOSE TACKLE"))


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_synthetic_xbe()

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(modern.status(self.payload), "retail")
        patched, receipt = modern.apply(self.payload)
        self.assertEqual(modern.status(patched), "applied")
        self.assertEqual(modern.status(self.payload), "retail")
        self.assertEqual(receipt["sections_repinned"], [12])
        self.assertEqual(len(receipt["edits"]), 8)
        self.assertEqual(_labels(patched, modern.UNIT_43),
                         [("LDE", "LEFT DEF END"), ("LDT", "LEFT DEF TACKLE"), ("RDT", "RIGHT DEF TACKLE"),
                          ("RDE", "RIGHT DEF END"), ("SAM", "STRONGSIDE LINEBACKER"), ("MIKE", "MIDDLE LINEBACKER"),
                          ("WILL", "WEAKSIDE LINEBACKER"), ("RCB", "RIGHT CORNERBACK"), ("LCB", "LEFT CORNERBACK"),
                          ("SS", "STRONG SAFETY"), ("FS", "FREE SAFETY")])
        self.assertEqual(_labels(patched, modern.UNIT_34),
                         [("LDE", "LEFT DEF END"), ("NT", "NOSE TACKLE"), ("RDE", "RIGHT DEF TACKLE"),
                          ("WILL", "WEAKSIDE LINEBACKER"), ("MIKE", "MIDDLE LINEBACKER"),
                          ("EDGE", "RIGHT EDGE RUSHER"), ("EDGE", "LEFT EDGE RUSHER"),
                          ("RCB", "RIGHT CORNERBACK"), ("LCB", "LEFT CORNERBACK"), ("SS", "STRONG SAFETY"),
                          ("FS", "FREE SAFETY")])
        # pools untouched: same players fill every slot
        self.assertEqual(_pools(patched, modern.UNIT_43), RETAIL_43)
        self.assertEqual(_pools(patched, modern.UNIT_34), RETAIL_34)

    def test_only_the_eight_text_fields_and_the_digest_change(self) -> None:
        patched, receipt = modern.apply(self.payload)
        allowed: set[int] = set()
        for site in modern.selected_sites(False):
            off = modern._offset(self.payload, site.va)
            allowed.update(range(off, off + modern.SLOT_TEXT_BYTES))
        table = struct.unpack_from("<I", self.payload, 0x120)[0] - modern.IMAGE_BASE
        header = table + 12 * strength.SECTION_HEADER_SIZE
        allowed.update(range(header + 36, header + 56))
        diff = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(diff <= allowed, sorted(diff - allowed)[:10])
        self.assertEqual(receipt["changed_bytes"], len(diff))
        section = next(s for s in strength._sections(patched) if s.index == 12)
        self.assertEqual(section.stored_digest, strength.section_digest(patched, section))

    def test_apply_refuses_applied_and_foreign(self) -> None:
        patched, _ = modern.apply(self.payload)
        with self.assertRaises(modern.ModernPositionsError):
            modern.apply(patched)
        foreign = bytearray(self.payload)
        off = modern._offset(self.payload, modern.record_va(modern.UNIT_43, 5))
        foreign[off: off + 4] = "MLB".encode("utf-16le")[:4]
        self.assertEqual(modern.status(bytes(foreign)), "foreign")
        with self.assertRaises(modern.ModernPositionsError):
            modern.apply(bytes(foreign))

    def test_a_changed_pool_field_makes_the_site_foreign(self) -> None:
        moved = bytearray(self.payload)
        off = modern._offset(self.payload, modern.record_va(modern.UNIT_34, 5)) + modern.SLOT_TEXT_BYTES
        struct.pack_into("<I", moved, off, 0x10)      # 3-4 ROLB slot pointed at the DE pool
        self.assertEqual(modern.status(bytes(moved)), "foreign")

    def test_optional_three_four_line_after_edge_rename(self) -> None:
        edged, _ = edge.apply(self.payload)
        self.assertEqual(modern.status(edged), "retail")
        self.assertEqual(modern.status(edged, three_four_line=True), "retail")
        patched, receipt = modern.apply(edged, three_four_line=True)
        self.assertEqual(len(receipt["edits"]), 10)
        self.assertEqual(modern.status(patched, three_four_line=True), "applied")
        self.assertEqual(_labels(patched, modern.UNIT_34)[:3],
                         [("DE", "LEFT DEFENSIVE END"), ("NT", "NOSE TACKLE"), ("DE", "RIGHT DEFENSIVE END")])
        self.assertEqual(_labels(patched, modern.UNIT_43)[:4],
                         [("EDGE", "LEFT EDGE RUSHER"), ("LDT", "LEFT DEF TACKLE"), ("RDT", "RIGHT DEF TACKLE"),
                          ("EDGE", "RIGHT EDGE RUSHER")])
        self.assertEqual(_pools(patched, modern.UNIT_34), RETAIL_34)
        # the EDGE rename accepts the DE text on its two 3-4 records, so its status stays applied
        self.assertEqual(edge.status(patched), "applied")
        self.assertEqual(modern.pool_profile(patched), "retail")
        # ... but the default profile composes cleanly with it
        default, _ = modern.apply(edged)
        self.assertEqual(edge.status(default), "applied")
        self.assertEqual(modern.status(default), "applied")

    def test_optional_three_four_line_from_retail(self) -> None:
        patched, receipt = modern.apply(self.payload, three_four_line=True)
        self.assertEqual(modern.status(patched, three_four_line=True), "applied")
        self.assertEqual(_labels(patched, modern.UNIT_34)[0], ("DE", "LEFT DEFENSIVE END"))
        self.assertEqual(len(receipt["edits"]), 10)


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_reads_retail_and_applies(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(modern.status(payload), "retail")
        self.assertEqual(modern.status(payload, three_four_line=True), "retail")
        self.assertEqual(_labels(payload, modern.UNIT_43), RETAIL_43_TEXT)
        self.assertEqual(_labels(payload, modern.UNIT_34), RETAIL_34_TEXT)
        self.assertEqual(_pools(payload, modern.UNIT_43), RETAIL_43)
        self.assertEqual(_pools(payload, modern.UNIT_34), RETAIL_34)
        patched, receipt = modern.apply(payload)
        self.assertEqual(modern.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [12])
        self.assertEqual(edge.status(patched), "retail")           # composes with the EDGE rename
        both, _ = edge.apply(patched)
        self.assertEqual(modern.status(both), "applied")
        self.assertEqual(edge.status(both), "applied")
        for section in strength._sections(both):
            if section.index == 12:
                self.assertEqual(section.stored_digest, strength.section_digest(both, section))


if __name__ == "__main__":
    unittest.main()
