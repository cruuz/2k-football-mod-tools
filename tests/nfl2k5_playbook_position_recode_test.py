"""Tests for the one-pool playbook category recode (rule, image access, apply on a synthetic XISO)."""

from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "tools", ROOT, ROOT / "tests"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_playbook_position_recode as pr  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

RETAIL_PACKS = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030")
DE, DT, ILB, OLB, CB, FS, SS, K, P = 12, 13, 14, 15, 18, 16, 17, 2, 1


def code(kind: int, variant: int = 0) -> int:
    return kind | (variant << 5)


def codes(text: str) -> list[int]:
    names = {n: i for i, n in enumerate(pr.KIND_NAMES)}
    out = []
    for token in text.split():
        name, variant = token.rstrip("0123456789"), int(token[len(token.rstrip("0123456789")):])
        out.append(code(names[name], variant))
    return out


def labels(values: list[int], pooled: bool = True) -> str:
    return " ".join(pr.code_label(c, pooled=pooled) for c in values)


# ---------------------------------------------------------------------------------------------
# synthetic playbook resources
# ---------------------------------------------------------------------------------------------

def build_book(name: str, categories: list[tuple[str, int, list[int]]]) -> bytes:
    """A minimal PLAY resource: 0x20 wrapper + 0x13390 body with the header fields the parser checks,
    a name pool at 0x10840 and the category table at 0x993C."""

    body = bytearray(pr.BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    body[0x20:0x28] = b"p\0l\0b\0\0\0"
    pool = 0x10840

    def put_string(text: str) -> int:
        nonlocal pool
        raw = text.encode("utf-16le") + b"\0\0"
        body[pool: pool + len(raw)] = raw
        at = pool
        pool += (len(raw) + 3) & ~3
        return at

    def rel(field_offset: int, target: int) -> None:
        struct.pack_into("<i", body, field_offset, target - field_offset + 1)

    rel(0x30, put_string(name))
    struct.pack_into("<I", body, 0x3C, len(categories))
    for field_offset, target in ((0x44, pr.CATEGORY_BASE - 0x9808), (0x48, 0x245C), (0x60, 0x33FC), (0x64, pr.CATEGORY_BASE), (0x68, 0x9ADC)):
        rel(field_offset, target)
    for index, (cname, formation_type, slot_codes) in enumerate(categories):
        off = pr.CATEGORY_BASE + index * pr.CATEGORY_SIZE
        rel(off, put_string(cname))
        body[off + 4] = formation_type
        body[off + 5: off + 16] = bytes(slot_codes)
    header = struct.pack("<4s7I", b"PLAY", pr.BODY_SIZE, pr.BODY_SIZE, 0, 0, 0, 0, 0)
    return header + bytes(body)


FOUR_THREE_BOOK = [
    ("Pro", 0x04, codes("QB0 T0 T1 C0 G0 G1 TE0 WR1 WR0 FB0 HB0")),
    ("Goalline", 0x0B, codes("DE1 DE0 DT1 DT0 DT2 OLB0 ILB0 OLB1 FS0 CB1 CB0")),
    ("4-3", 0x0D, codes("DE1 DE0 DT1 DT0 OLB1 ILB0 OLB0 FS0 SS0 CB1 CB0")),
    ("Nickel", 0x0E, codes("DE1 DE0 DT1 DT0 OLB0 ILB0 CB2 FS0 SS0 CB1 CB0")),
    ("Prevent", 0x10, codes("OLB0 DE1 DE0 DT0 SS1 CB2 FS1 FS0 SS0 CB1 CB0")),
    ("Kickoff", 0x15, codes("K0 ILB2 ILB1 OLB2 FS1 SS1 SS2 FS2 CB3 CB2 OLB3")),
]
THREE_FOUR_BOOK = [
    ("Pro", 0x04, codes("QB0 T0 T1 C0 G0 G1 TE0 WR1 WR0 FB0 HB0")),
    ("3-4", 0x0D, codes("OLB1 DE1 DE0 DT0 ILB1 ILB0 OLB0 FS0 SS0 CB1 CB0")),
    ("Nickel", 0x0E, codes("OLB1 DE1 DE0 DT1 ILB0 OLB0 CB2 FS0 SS0 CB1 CB0")),
    ("Bear", 0x0D, codes("DE1 DE0 DT1 DT0 OLB0 ILB1 ILB0 FS0 SS0 CB1 CB0")),
]
FIVE_TWO_BOOK = [
    ("5-2", 0x0C, codes("DE1 DE0 DE2 DT1 DT0 OLB0 ILB0 FS0 SS0 CB1 CB0")),
    ("4-3", 0x0D, codes("DE1 DE0 DT1 DT0 OLB1 ILB0 OLB0 FS0 SS0 CB1 CB0")),
]
TEST_BOOKS = ("ARZ", "ATL", "BAL")      # outer entries 307, 308, 309


def build_fixture(directory: Path, books: dict[str, list[tuple[str, int, list[int]]]] | None = None) -> SyntheticXiso:
    books = books or {"ARZ": FOUR_THREE_BOOK, "ATL": THREE_FOUR_BOOK, "BAL": FIVE_TWO_BOOK}
    entries: list[tuple[int, bytes]] = []
    for index in range(pr.FIRST_BOOK_ENTRY):
        entries.append((0x1000 + index, bytes([index & 0xFF]) * 0x10))
    for name in TEST_BOOKS:
        entries.append((0x2000 + len(entries), build_book(name, books[name])))
    entries.append((0x3000, b"tail"))                       # the fixture pads the last entry to the pack end
    return SyntheticXiso(directory, entries, pack_sizes=(0x100000, 0x2000, 0x2000), pack_sectors=(64, 576, 580))


def fixture_digests(path: Path) -> dict[str, dict[str, str]]:
    return pr.digests(path, TEST_BOOKS)


class RuleTests(unittest.TestCase):
    def check(self, before: str, after: str, rule: str, formation_type: int = 0x0D, **kw: object) -> None:
        new, got_rule = pr.recode_codes(codes(before), formation_type, **kw)
        self.assertEqual(got_rule, rule, before)
        self.assertEqual(labels(new), after, before)
        self.assertEqual(len(set(new)), 11, f"duplicate codes in {after}")

    def test_even_front_4_3(self) -> None:
        self.check("DE1 DE0 DT1 DT0 OLB1 ILB0 OLB0 FS0 SS0 CB1 CB0", "EDGE1 EDGE0 DT1 DT0 LB2 LB0 LB1 FS0 SS0 CB1 CB0", "even")

    def test_even_front_keeps_de_dt_bytes(self) -> None:
        before = codes("DE1 DE0 DT1 DT0 OLB1 ILB0 OLB0 FS0 SS0 CB1 CB0")
        new, _ = pr.recode_codes(before, 0x0D)
        self.assertEqual(new[:4], before[:4])
        self.assertEqual(new[7:], before[7:])

    def test_odd_front_3_4(self) -> None:
        self.check("OLB1 DE1 DE0 DT0 ILB1 ILB0 OLB0 FS0 SS0 CB1 CB0", "EDGE1 DT2 DT1 DT0 LB1 LB0 EDGE0 FS0 SS0 CB1 CB0", "odd")

    def test_odd_front_with_dt1_nose(self) -> None:
        self.check("OLB1 DE1 DE0 DT1 ILB0 OLB0 CB2 FS0 SS0 CB1 CB0", "EDGE1 DT2 DT1 DT0 LB0 EDGE0 CB2 FS0 SS0 CB1 CB0", "odd", 0x0E)

    def test_five_two(self) -> None:
        self.check("DE1 DE0 DE2 DT1 DT0 OLB0 ILB0 FS0 SS0 CB1 CB0", "EDGE1 EDGE0 DT2 DT1 DT0 LB1 LB0 FS0 SS0 CB1 CB0", "five_two", 0x0C)

    def test_bear_bumps_the_olb_past_both_ilbs(self) -> None:
        self.check("DE1 DE0 DT1 DT0 OLB0 ILB1 ILB0 FS0 SS0 CB1 CB0", "EDGE1 EDGE0 DT1 DT0 LB2 LB1 LB0 FS0 SS0 CB1 CB0", "even")

    def test_kickoff_and_punt_backups(self) -> None:
        self.check("K0 ILB2 ILB1 OLB2 FS1 SS1 SS2 FS2 CB3 CB2 OLB3", "K0 LB2 LB1 LB3 FS1 SS1 SS2 FS2 CB3 CB2 LB4", "even", 0x15)
        self.check("P0 ILB1 DE2 C1 OLB1 OLB2 HB1 FB1 FS1 SS1 CB2", "P0 LB1 EDGE2 C1 LB2 LB3 HB1 FB1 FS1 SS1 CB2", "even", 0x11)

    def test_goalline_variants(self) -> None:
        self.check("DE1 DE2 DT2 DT0 DT1 DE0 ILB0 OLB0 FS0 CB1 CB0", "EDGE1 EDGE2 DT2 DT0 DT1 EDGE0 LB0 LB1 FS0 CB1 CB0", "even", 0x0B)
        self.check("DE1 DE0 DT1 DT3 DT0 OLB1 ILB1 OLB0 FS1 CB1 CB0", "EDGE1 EDGE0 DT1 DT3 DT0 LB3 LB1 LB2 FS1 CB1 CB0", "even", 0x0B)

    def test_prevent_default_and_two_edges(self) -> None:
        self.check("OLB0 DE1 DE0 DT0 SS1 CB2 FS1 FS0 SS0 CB1 CB0", "EDGE0 DT2 DT1 DT0 SS1 CB2 FS1 FS0 SS0 CB1 CB0", "odd", 0x10)
        self.check("OLB0 DE1 DE0 DT0 SS1 CB2 FS1 FS0 SS0 CB1 CB0", "EDGE0 EDGE1 DT1 DT0 SS1 CB2 FS1 FS0 SS0 CB1 CB0", "odd", 0x10,
                   prevent_two_edges=True)
        # the option only touches Prevent
        self.check("OLB1 DE1 DE0 DT0 ILB1 ILB0 OLB0 FS0 SS0 CB1 CB0", "EDGE1 DT2 DT1 DT0 LB1 LB0 EDGE0 FS0 SS0 CB1 CB0", "odd", 0x0D,
                   prevent_two_edges=True)

    def test_offense_untouched(self) -> None:
        before = codes("QB0 T0 T1 C0 G0 G1 TE0 WR1 WR0 FB0 HB0")
        new, rule = pr.recode_codes(before, 0x04)
        self.assertEqual((new, rule), (before, "untouched"))

    def test_no_olb_kind_survives_and_variants_fit(self) -> None:
        for _name, ftype, before in FOUR_THREE_BOOK + THREE_FOUR_BOOK + FIVE_TWO_BOOK:
            new, _ = pr.recode_codes(before, ftype)
            self.assertFalse(any((c & 0x1F) == pr.KIND_OLB for c in new))
            self.assertTrue(all(c >> 5 <= pr.MAX_VARIANT for c in new))


class SyntheticImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = build_fixture(Path(self.tmp.name))
        self.digests = fixture_digests(self.fixture.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_invalid_archive_table_closes_image_even_with_retained_traceback(self) -> None:
        invalid = bytearray(self.fixture.image)
        struct.pack_into("<I", invalid, self.fixture.pack_extent("0") + 4, 1)  # reserved header word
        self.fixture.path.write_bytes(invalid)
        real_open = os.open
        for writable in (False, True):
            with self.subTest(writable=writable):
                opened = []

                def track_open(*args, **kwargs):
                    fd = real_open(*args, **kwargs)
                    opened.append(fd)
                    return fd

                try:
                    with patch.object(os, "open", side_effect=track_open):
                        try:
                            with pr.OuterImage(self.fixture.path, writable=writable):
                                self.fail("invalid archive was accepted")
                        except pr.RecodeError as exc:
                            failure = exc  # keep the failed constructor alive like an error reporter
                    self.assertIn("implausible outer archive header", str(failure))
                    self.assertIsNotNone(failure.__traceback__)
                    self.assertEqual(len(opened), 1)
                    with self.assertRaises(OSError) as closed:
                        os.fstat(opened[0])
                    self.assertEqual(closed.exception.errno, errno.EBADF)
                    self.assertEqual(self.fixture.path.read_bytes(), invalid)
                finally:
                    for fd in opened:
                        try:
                            os.close(fd)  # release a leaked fd if the regression fails
                        except OSError:
                            pass

    def test_books_are_found_inside_the_image_and_the_loose_folder(self) -> None:
        for path in (self.fixture.path, self.fixture.retail_packs):
            with pr.OuterImage(path) as archive:
                books = pr.load_books(archive, TEST_BOOKS)
            self.assertEqual([b.book_name for b in books], list(TEST_BOOKS))
            self.assertEqual([len(b.categories) for b in books], [6, 4, 2])
            self.assertEqual(books[0].categories[2].name, "4-3")
            self.assertEqual(labels(books[1].categories[1].codes, pooled=False), "OLB1 DE1 DE0 DT0 ILB1 ILB0 OLB0 FS0 SS0 CB1 CB0")

    def test_status_apply_and_readback(self) -> None:
        retail, applied = self.digests["retail"], self.digests["applied"]
        self.assertEqual(pr.status(self.fixture.path, TEST_BOOKS, retail=retail, applied=applied)["status"], "retail")
        image_before = self.fixture.path.read_bytes()
        receipt = pr.apply(self.fixture.path, names=TEST_BOOKS, retail=retail, applied=applied)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(pr.status(self.fixture.path, TEST_BOOKS, retail=retail, applied=applied)["status"], "applied")
        image_after = self.fixture.path.read_bytes()
        self.assertEqual(len(image_before), len(image_after))
        diff = {i for i, (a, b) in enumerate(zip(image_before, image_after)) if a != b}
        # only slot-code bytes inside the three category tables change
        allowed: set[int] = set()
        with pr.OuterImage(self.fixture.path) as archive:
            for book in pr.load_books(archive, TEST_BOOKS):
                base = archive.image_offset(book.table_offset)
                for cat in book.categories:
                    allowed.update(range(base + cat.index * 16 + 5, base + cat.index * 16 + 16))
        self.assertTrue(diff <= allowed, sorted(diff - allowed)[:8])
        self.assertEqual(receipt["changed_bytes"], len(diff))
        with pr.OuterImage(self.fixture.path) as archive:
            books = {b.name: b for b in pr.load_books(archive, TEST_BOOKS)}
        self.assertEqual(labels(books["ARZ"].categories[2].codes), "EDGE1 EDGE0 DT1 DT0 LB2 LB0 LB1 FS0 SS0 CB1 CB0")
        self.assertEqual(labels(books["ATL"].categories[1].codes), "EDGE1 DT2 DT1 DT0 LB1 LB0 EDGE0 FS0 SS0 CB1 CB0")
        self.assertEqual(labels(books["BAL"].categories[0].codes), "EDGE1 EDGE0 DT2 DT1 DT0 LB1 LB0 FS0 SS0 CB1 CB0")
        self.assertEqual(books["ARZ"].categories[0].codes, FOUR_THREE_BOOK[0][2])     # offense untouched
        self.assertEqual(sorted(receipt["books"][0]["categories_changed"]), ["4-3", "Goalline", "Kickoff", "Nickel", "Prevent"])

    def test_apply_refuses_applied_and_foreign_books(self) -> None:
        retail, applied = self.digests["retail"], self.digests["applied"]
        pr.apply(self.fixture.path, names=TEST_BOOKS, retail=retail, applied=applied)
        with self.assertRaises(pr.RecodeError):
            pr.apply(self.fixture.path, names=TEST_BOOKS, retail=retail, applied=applied)
        # a foreign defensive category in one book refuses the whole run before any write
        foreign = build_fixture(Path(self.tmp.name) / "foreign",
                                {"ARZ": FOUR_THREE_BOOK, "ATL": THREE_FOUR_BOOK,
                                 "BAL": [("5-2", 0x0C, codes("DE1 DE0 DE2 DT1 DT0 OLB0 ILB0 FS0 SS0 CB1 CB0")),
                                         ("4-3", 0x0D, codes("DE1 DE0 DT1 DT0 OLB1 ILB1 OLB0 FS0 SS0 CB1 CB0"))]})
        before = foreign.path.read_bytes()
        st = pr.status(foreign.path, TEST_BOOKS, retail=retail, applied=applied)
        self.assertEqual(st["books"]["BAL"], "foreign")
        self.assertEqual(st["status"], "partial")
        with self.assertRaises(pr.RecodeError):
            pr.apply(foreign.path, names=TEST_BOOKS, retail=retail, applied=applied)
        self.assertEqual(foreign.path.read_bytes(), before)

    def test_custom_offense_category_does_not_break_the_retail_check(self) -> None:
        # a Create-a-Play author rewrote an offensive category: the defensive digest still reads retail
        retail, applied = self.digests["retail"], self.digests["applied"]
        custom = list(FOUR_THREE_BOOK)
        custom[0] = ("Jacks", 0x00, codes("QB0 T0 T1 C0 G0 G1 TE0 WR1 WR0 HB1 HB0"))
        edited = build_fixture(Path(self.tmp.name) / "custom", {"ARZ": custom, "ATL": THREE_FOUR_BOOK, "BAL": FIVE_TWO_BOOK})
        self.assertEqual(pr.status(edited.path, TEST_BOOKS, retail=retail, applied=applied)["status"], "retail")
        receipt = pr.apply(edited.path, names=TEST_BOOKS, retail=retail, applied=applied)
        self.assertEqual(receipt["status"], "applied")
        with pr.OuterImage(edited.path) as archive:
            arz = pr.load_books(archive, ["ARZ"])[0]
        self.assertEqual(arz.categories[0].codes, custom[0][2])

    def test_prevent_two_edges_reads_applied_custom(self) -> None:
        retail, applied = self.digests["retail"], self.digests["applied"]
        receipt = pr.apply(self.fixture.path, names=TEST_BOOKS, prevent_two_edges=True, retail=retail, applied=applied)
        self.assertEqual(receipt["after"]["ARZ"], "applied-custom")
        self.assertEqual(receipt["after"]["BAL"], "applied")          # no Prevent in that book
        self.assertEqual(receipt["status"], "applied-custom")

    def test_inspect_lists_every_defensive_category(self) -> None:
        with pr.OuterImage(self.fixture.path) as archive:
            rows = pr.inspect_rows(pr.load_books(archive, TEST_BOOKS))
        self.assertEqual(len(rows), 5 + 3 + 2)
        text = pr.format_inspect(rows)
        self.assertIn("== ARZ", text)
        self.assertIn("EDGE1 DT2 DT1 DT0 LB1 LB0 EDGE0", text)


@unittest.skipUnless(RETAIL_PACKS.is_dir(), "retail packs not present")
class RetailPackSmokeTests(unittest.TestCase):
    def test_retail_packs_read_retail_and_every_book_recodes_cleanly(self) -> None:
        st = pr.status(RETAIL_PACKS)
        self.assertEqual(st["status"], "retail")
        self.assertEqual(len(st["books"]), 37)
        with pr.OuterImage(RETAIL_PACKS) as archive:
            books = pr.load_books(archive)
        for book in books:
            table, changes = pr.recoded_table(book)
            self.assertEqual(hashlib.sha256(book.defensive_records(table)).hexdigest(), pr.APPLIED_TABLE_SHA256[book.name])
            for cat, new, rule in changes:
                if rule != "untouched":
                    self.assertEqual(len(set(new)), 11, f"{book.name} {cat.name}")
                    self.assertFalse(any((c & 0x1F) == pr.KIND_OLB for c in new), f"{book.name} {cat.name}")
        by_name = {b.name: b for b in books}
        self.assertEqual(labels(pr.recode_codes(by_name["BAL"].categories[10].codes, 0x0D)[0]),
                         "EDGE1 DT2 DT1 DT0 LB1 LB0 EDGE0 FS0 SS0 CB1 CB0")


if __name__ == "__main__":
    unittest.main()
