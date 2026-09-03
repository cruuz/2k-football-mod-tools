"""The season-year / calendar / 18-week patch must stay pattern-driven, fail-closed and copy-only.

Synthetic fixture: a minimal XBE with a valid 22-section table whose three sections carry the retail
bytes of every site at their retail virtual addresses plus correct section digests.  A retail-XBE
smoke test (site bytes pinned against the real default.xbe) runs only when the private copy exists.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA, TEXT_RAW, TEXT_SIZE = 0x11000, 0x1000, 0x3F0000
RDATA_VA, RDATA_RAW, RDATA_SIZE = 0x4E3AE0, 0x3F1000, 0x40000
DATA_VA, DATA_RAW, DATA_SIZE = 0xA69980, 0x431000, 0x70000
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(struct.pack("<I", raw_size) + payload[raw: raw + raw_size]).digest()  # nosec B324


SECTIONS = {0: (TEXT_VA, TEXT_RAW, TEXT_SIZE), 12: (RDATA_VA, RDATA_RAW, RDATA_SIZE), 13: (DATA_VA, DATA_RAW, DATA_SIZE)}


def _raw_offset(va: int) -> int:
    for _index, (sva, raw, size) in SECTIONS.items():
        if sva <= va < sva + size:
            return raw + (va - sva)
    raise AssertionError(f"fixture has no section for {va:#x}")


def build_synthetic_xbe() -> bytes:
    buf = bytearray(DATA_RAW + DATA_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index in SECTIONS:
            fields[1], fields[3], fields[4] = SECTIONS[index]
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    for group in season.GROUPS:
        for site in season.group_sites(group):
            off = _raw_offset(site.va)
            buf[off: off + site.size] = site.retail
    for index, (_va, raw, size) in SECTIONS.items():
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        buf[header + 36: header + 56] = _section_digest(bytes(buf), raw, size)
    return bytes(buf)


class SiteTableTests(unittest.TestCase):
    def test_sites_do_not_overlap_and_keep_their_size(self) -> None:
        spans = []
        for group in season.GROUPS:
            for site in season.group_sites(group):
                self.assertEqual(len(site.retail), len(site.patched), site.label)
                self.assertNotEqual(site.retail, site.patched, site.label)
                spans.append((site.va, site.va + site.size, site.label))
        spans.sort()
        for (a0, a1, la), (b0, _b1, lb) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, f"{la} overlaps {lb}")
        self.assertEqual(len(season.WEEK_SITES), 143)          # 49 from the first sweep + 94 missed row literals
        self.assertEqual(len(season.year_sites(2026)), 8)      # 4 imm32 + 1 imm8 + rookie birth base/top + DOB line
        self.assertEqual(len(season.calendar_sites()), 2)
        self.assertEqual(len(season.group_sites("playoffs_14")), 13)
        self.assertEqual(len(season.group_sites("preseason")), 3)

    def test_year_sites_encode_the_requested_year(self) -> None:
        by_label = {site.label: site for site in season.year_sites(2026)}
        for site in season.year_sites(2026):
            if site.size == 4:
                self.assertEqual(struct.unpack("<I", site.patched)[0], 2026)
                self.assertEqual(struct.unpack("<I", site.retail)[0], 2004)
        self.assertEqual((by_label["regular_season_generator_year"].retail, by_label["regular_season_generator_year"].patched),
                         (b"\x04", b"\x1a"))
        self.assertNotIn("preseason_generator_year", by_label)     # inside the rewritten preseason generator now
        # rookies: retail (season + 80..82) % 100 = born 1980-82 in 2004; 2026 -> (season + 102..104) % 100 = 2002-04
        self.assertEqual((by_label["rookie_birth_base"].retail, by_label["rookie_birth_base"].patched), (b"\x50", b"\x66"))
        self.assertEqual((by_label["rookie_birth_top"].retail, by_label["rookie_birth_top"].patched), (b"\x52", b"\x68"))
        self.assertEqual(season.rookie_birth_base(2004), 0x50)
        self.assertEqual(season.dob_pivot(2026), 30)
        self.assertEqual(season.dob_pivot(2004), 8)
        dob = by_label["dob_four_digit_year"]
        self.assertEqual((dob.va, dob.size), (0x145D20, 0x70))
        self.assertEqual(dob.retail[:3], b"\x83\xec\x0c")
        self.assertEqual(dob.patched[:3], b"\x83\xec\x0c")
        self.assertIn(b"\x83\xf8\x1e\x8d\x88\x6c\x07\x00\x00\x77\x03\x83\xc1\x64", dob.patched)   # cmp 30; lea 1900; ja; +100
        self.assertIn(struct.pack("<I", season.DOB_FORMAT_STRING_VA), dob.patched)
        self.assertTrue(dob.patched.endswith(b"\x90\x90\x90"))
        with self.assertRaises(season.SeasonLengthError):
            season.year_sites(2099)
        with self.assertRaises(season.SeasonLengthError):
            season.year_sites(2052)                              # rookie base no longer fits an imm8

    def test_dob_formatter_calls_land_where_retail_did(self) -> None:
        code = season.dob_formatter_bytes(2026)
        first = 3                                                          # after sub esp,0xc
        second = code.index(b"\xa1" + struct.pack("<I", season.DOB_LINE_BUFFER_INDEX_VA)) - 5
        self.assertEqual(code[first], 0xE8)
        self.assertEqual(code[second], 0xE8)
        targets = {season.DOB_FORMATTER_VA + i + 5 + struct.unpack_from("<i", code, i + 1)[0] for i in (first, second)}
        self.assertEqual(targets, {season.DOB_LINE_NEXT_FN, season.DOB_LINE_FORMAT_FN})
        self.assertNotEqual(season.dob_formatter_bytes(2004), code)

    def test_calendar_records_are_well_formed(self) -> None:
        table = season.postseason_table(season.CALENDAR_2026)
        self.assertEqual(len(table), 96)
        self.assertEqual(table[:8], bytes([0, 0, 0, 1, 16, 0, 4, 30]))
        self.assertEqual(table[80:88], bytes([0, 0, 0, 2, 14, 0, 6, 30]))       # Super Bowl LXI
        self.assertEqual(season.postseason_table(season.RETAIL_POSTSEASON)[:8], bytes([0, 0, 0, 1, 8, 0, 0, 30]))
        self.assertEqual(season.postseason_record(1, 1, 12, 0)[6], 0)          # 12 encodes as 0

    def test_grid_row_bounds(self) -> None:
        self.assertEqual(season.ROW17_END_VA, 0xE58548)
        self.assertEqual(season.ROW18_END_VA, 0xE585D0)
        self.assertEqual(season.GRID_VA + season.GRID_ROWS * season.GRID_ROW_BYTES, 0xE587F0)
        skip = next(s for s in season.WEEK_SITES if s.label == "pro_bowl_record_skip")
        self.assertEqual(skip.patched[:2], b"\xeb\x22")                          # jmp 0x2a82b0+0x22 = 0x2a82d2
        bound = next(s for s in season.WEEK_SITES if s.label == "pro_bowl_row_bound")
        self.assertEqual(bound.va, 0x2A82AE + 2 + 0x22)


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_synthetic_xbe()

    def test_retail_status(self) -> None:
        report = season.status(self.payload)
        self.assertEqual((report["year"], report["calendar"], report["season_length"]), ("retail",) * 3)
        self.assertEqual(report["playoffs_14"], "retail")
        self.assertEqual(report["preseason"], "retail")
        self.assertEqual(report["regular_weeks"], 17)
        self.assertEqual(report["playoff_teams"], 12)
        self.assertEqual(report["preseason_games"], 4)
        self.assertEqual(season.read_year(self.payload), 2004)

    def test_full_apply_round_trip(self) -> None:
        patched, receipt = season.apply(self.payload)
        report = season.status(patched)
        self.assertEqual((report["year"], report["calendar"], report["season_length"]), ("applied",) * 3)
        self.assertEqual(report["playoffs_14"], "applied")
        self.assertEqual(report["preseason"], "applied")
        self.assertEqual(report["regular_weeks"], 18)
        self.assertEqual(report["playoff_teams"], 14)
        self.assertEqual(report["preseason_games"], 3)
        self.assertEqual(receipt["preseason_weeks"], 4)
        self.assertEqual(season.read_year(patched), 2026)
        self.assertEqual(receipt["sections_repinned"], [0, 12, 13])
        self.assertEqual(len(receipt["edits"]), 8 + 2 + 143 + 13 + 3)
        self.assertFalse(receipt["runtime_verified"])
        for index, (_va, raw, size) in SECTIONS.items():
            header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
            self.assertEqual(patched[header + 36: header + 56], _section_digest(patched, raw, size))
        # only the sites and the three digests changed
        expected = set()
        for group in season.GROUPS:
            for site in season.group_sites(group):
                off = _raw_offset(site.va)
                expected.update(off + i for i, (a, b) in enumerate(zip(site.retail, site.patched)) if a != b)
        for index in SECTIONS:
            header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
            expected.update(range(header + 36, header + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= expected)
        self.assertEqual(receipt["changed_bytes"], len(changed))
        with self.assertRaises(season.SeasonLengthError):
            season.apply(patched)

    def test_year_only_apply(self) -> None:
        patched, receipt = season.apply(self.payload, groups=("year",), year=2027)
        report = season.status(patched)
        self.assertEqual(report["year"], "applied:2027")
        self.assertEqual(report["season_length"], "retail")
        self.assertEqual(report["regular_weeks"], 17)
        self.assertEqual(receipt["regular_weeks"], 17)
        self.assertEqual(receipt["playoff_teams"], 12)
        self.assertEqual(season.read_year(patched), 2027)
        self.assertEqual(season.group_status(patched, "year", year=2027), "applied")
        self.assertEqual(season.group_status(patched, "year"), "foreign")   # not the 2026 preset

    def test_foreign_bytes_are_refused(self) -> None:
        buf = bytearray(self.payload)
        buf[_raw_offset(season.SEASON_WEEKS_VA)] = 0x13
        report = season.status(bytes(buf))
        self.assertEqual(report["season_length"], "foreign")
        self.assertEqual(report["year"], "retail")
        with self.assertRaises(season.SeasonLengthError):
            season.apply(bytes(buf))
        patched, _ = season.apply(bytes(buf), groups=("year", "calendar"))
        self.assertEqual(season.status(patched)["season_length"], "foreign")


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_every_site_is_retail_on_the_real_executable(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        report = season.status(payload)
        self.assertEqual((report["year"], report["calendar"], report["season_length"]), ("retail",) * 3)
        self.assertEqual(report["playoffs_14"], "retail")
        self.assertEqual(report["preseason"], "retail")
        patched, receipt = season.apply(payload)
        self.assertEqual(season.status(patched)["regular_weeks"], 18)
        self.assertEqual(season.status(patched)["playoff_teams"], 14)
        self.assertEqual(season.status(patched)["preseason_games"], 3)
        self.assertEqual(receipt["sections_repinned"], [0, 12, 13])
        sections = strength._sections(patched)
        for section in sections:
            if section.index in receipt["sections_repinned"]:
                self.assertEqual(strength.section_digest(patched, section), section.stored_digest)


if __name__ == "__main__":
    unittest.main()
