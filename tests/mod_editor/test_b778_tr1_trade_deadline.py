"""b778-tr1: the in-season trade deadline through the native gate (NFL Week 9).

Retail hides the Front Office TRADES/TRADING BLOCK rows from displayed Week 7 and the Player
Trade screen refuses from displayed Week 8. The fix changes only the two week boundaries:
the stage-table byte behind ``FUN_00247d10`` and the ``cmp eax,6`` immediate in the native
screen guard. The synthetic XBE carries the exact retail bytes at both virtual addresses, so
apply/status/idempotence and every refusal run without a disc. A retail-XBE smoke test runs
when the private extraction is present.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_trade_deadline as td  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

IMAGE_BASE = 0x10000
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA, TEXT_RAW, TEXT_SIZE = 0x11000, 0x1000, 0x3F0000
DATA_VA, DATA_RAW, DATA_SIZE = 0x4E3AE0, 0x431000, 0x70000
SECTIONS = {0: (TEXT_VA, TEXT_RAW, TEXT_SIZE), 12: (DATA_VA, DATA_RAW, DATA_SIZE)}
RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))


def _raw_offset(va: int) -> int:
    for sva, raw, size in SECTIONS.values():
        if sva <= va < sva + size:
            return raw + (va - sva)
    raise AssertionError(f"fixture has no section for {va:#x}")


def _digest(payload: bytes, raw: int, size: int) -> bytes:
    return hashlib.sha1(struct.pack("<I", size) + payload[raw:raw + size]).digest()  # nosec B324


def build_synthetic_xbe(*, weeks: int = 0x12, deadline: int = td.RETAIL_PREDICATE_WEEK,
                        screen: int = td.RETAIL_SCREEN_WEEK) -> bytes:
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
    guard = bytearray(td.SCREEN_GUARD_RETAIL)
    guard[td.SCREEN_VA - td.SCREEN_GUARD_VA] = screen
    off = _raw_offset(td.SCREEN_GUARD_VA)
    buf[off:off + len(guard)] = guard
    row = td.STAGE_GUARD_HEAD + bytes([weeks, deadline]) + td.STAGE_GUARD_TAIL
    off = _raw_offset(td.STAGE_GUARD_VA)
    buf[off:off + len(row)] = row
    for index, (_va, raw, size) in SECTIONS.items():
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        buf[header + 36:header + 56] = _digest(bytes(buf), raw, size)
    return bytes(buf)


class ConstantsTests(unittest.TestCase):
    def test_sites_are_the_two_native_boundaries(self) -> None:
        sites = td.sites()
        self.assertEqual([site.label for site in sites], ["trade_screen_week_limit", "stage_table_season_deadline"])
        self.assertEqual([(site.va, site.retail, site.patched) for site in sites],
                         [(0x002B8BC5, b"\x06", b"\x08"), (0x005151C5, b"\x06", b"\x09")])
        self.assertEqual((td.RETAIL_SCREEN_WEEK, td.SCREEN_WEEK_LIMIT), (6, 8))
        self.assertEqual((td.RETAIL_PREDICATE_WEEK, td.PREDICATE_WEEK_LIMIT), (6, 9))
        self.assertEqual(td.DEADLINE_WEEK, 9)

    def test_week_arithmetic_is_displayed_week_nine(self) -> None:
        # The save stores week zero for the first regular-season week, so displayed Week 9
        # is stored week 8: ``cmp eax,8; jg`` and ``week < 9`` both allow 0..8 and block 9.
        self.assertEqual(td.SCREEN_WEEK_LIMIT, td.DEADLINE_WEEK - 1)
        self.assertEqual(td.SCREEN_WEEK_LIMIT + 1, td.PREDICATE_WEEK_LIMIT)
        self.assertTrue(all(week <= td.SCREEN_WEEK_LIMIT for week in range(td.DEADLINE_WEEK)))
        self.assertGreater(td.DEADLINE_WEEK, td.SCREEN_WEEK_LIMIT)

    def test_screen_guard_calls_the_stage_and_week_accessors(self) -> None:
        guard = td.SCREEN_GUARD_RETAIL
        self.assertEqual(len(guard), 29)
        self.assertEqual(guard[:5], bytes.fromhex("a12401e600"))   # mov eax,[0xe60124] Trade Deadline option
        for call_off, target in ((9, 0xC4BB0), (19, 0xC4E70)):
            self.assertEqual(guard[call_off], 0xE8)
            relative = struct.unpack_from("<i", guard, call_off + 1)[0]
            self.assertEqual(td.SCREEN_GUARD_VA + call_off + 5 + relative, target)
        # the guard is the retail instruction stream with only the compared immediate changed
        self.assertEqual(td.SCREEN_GUARD_RETAIL[td.SCREEN_VA - td.SCREEN_GUARD_VA], 6)
        self.assertEqual(guard[td.SCREEN_VA - td.SCREEN_GUARD_VA + 1:td.SCREEN_VA - td.SCREEN_GUARD_VA + 3], b"\x7f\x0a")


class ApplyTests(unittest.TestCase):
    def test_retail_status_apply_and_idempotence(self) -> None:
        retail = build_synthetic_xbe()
        self.assertEqual(td.status(retail), "retail")
        applied, receipt = td.apply(retail)
        self.assertEqual(td.status(applied), "applied")
        self.assertEqual((receipt["status"], receipt["deadline_week"]), ("applied", 9))
        self.assertEqual(receipt["changed_bytes"], 42)
        self.assertEqual(receipt["sections_repinned"], [0, 12])
        self.assertEqual(receipt["file_growth"], 0)
        self.assertEqual(applied[_raw_offset(td.SCREEN_VA):_raw_offset(td.SCREEN_VA) + 1], b"\x08")
        self.assertEqual(applied[_raw_offset(td.STAGE_VA):_raw_offset(td.STAGE_VA) + 1], b"\x09")
        again, again_receipt = td.apply(applied)
        self.assertEqual(again, applied)
        self.assertEqual((again_receipt["status"], again_receipt["changed_bytes"], again_receipt["file_growth"]),
                         ("already_applied", 0, 0))

    def test_seventeen_week_season_is_accepted(self) -> None:
        retail = build_synthetic_xbe(weeks=0x11)
        applied, receipt = td.apply(retail)
        self.assertEqual(td.status(applied), "applied")
        self.assertEqual(receipt["deadline_week"], 9)
        self.assertEqual(applied[_raw_offset(td.STAGE_VA - 1):_raw_offset(td.STAGE_VA) + 1], bytes([0x11, 0x09]))

    def test_mixed_or_foreign_images_refuse(self) -> None:
        screen_only = build_synthetic_xbe(screen=td.SCREEN_WEEK_LIMIT)
        stage_only = build_synthetic_xbe(deadline=td.PREDICATE_WEEK_LIMIT)
        for payload in (screen_only, stage_only):
            self.assertEqual(td.status(payload), "foreign")
            with self.assertRaises(td.TradeDeadlineError):
                td.apply(payload)
        self.assertEqual(td.status(build_synthetic_xbe(deadline=7)), "foreign")
        self.assertEqual(td.status(build_synthetic_xbe(weeks=0x13)), "foreign")
        self.assertEqual(td.status(build_synthetic_xbe()[:0x200]), "foreign")
        self.assertEqual(td.status(b"not an xbe"), "foreign")
        with self.assertRaises(td.TradeDeadlineError):
            td.apply(b"not an xbe")

    def test_applied_screen_guard_keeps_every_other_retail_byte(self) -> None:
        applied = td.apply(build_synthetic_xbe())[0]
        guard = applied[_raw_offset(td.SCREEN_GUARD_VA):_raw_offset(td.SCREEN_GUARD_VA) + len(td.SCREEN_GUARD_RETAIL)]
        expected = bytearray(td.SCREEN_GUARD_RETAIL)
        expected[td.SCREEN_VA - td.SCREEN_GUARD_VA] = td.SCREEN_WEEK_LIMIT
        self.assertEqual(guard, bytes(expected))


class IntegrationTests(unittest.TestCase):
    def test_module_is_in_the_pinned_closure_and_the_2026_build_step(self) -> None:
        self.assertIs(tt.trade_deadline_patch, td)
        self.assertTrue(mod_build.availability()["season_2026"])
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertTrue(plan.season_2026)
        basic = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_basic")
        self.assertFalse(basic.season_2026)
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertIn('_core_module("nfl2k5_trade_deadline")', text)
        self.assertIn("Keeping in-season trades open through NFL Week 9", text)

    def test_module_and_test_are_in_the_release_allowlist(self) -> None:
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        self.assertIn("mod_editor/core/nfl2k5_trade_deadline.py", allow)
        self.assertIn("tests/mod_editor/test_b778_tr1_trade_deadline.py", allow)

    def test_module_has_no_dev_paths_or_em_dashes(self) -> None:
        text = (ROOT / "mod_editor/core/nfl2k5_trade_deadline.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("\u2014", text)


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail extraction is not present")
class RetailXbeTests(unittest.TestCase):
    def test_retail_bytes_apply_and_verify(self) -> None:
        retail = RETAIL_XBE.read_bytes()
        self.assertEqual(td.status(retail), "retail")
        image = XbeImage(retail)
        self.assertEqual(image.read(td.SCREEN_GUARD_VA, len(td.SCREEN_GUARD_RETAIL)), td.SCREEN_GUARD_RETAIL)
        self.assertEqual(image.read(td.SCREEN_VA, 1), b"\x06")
        self.assertEqual(image.read(td.STAGE_GUARD_VA, 6), td.STAGE_GUARD_HEAD + b"\x11\x06")
        applied, receipt = td.apply(retail)
        self.assertEqual(td.status(applied), "applied")
        self.assertEqual(XbeImage(applied).read(td.SCREEN_VA, 1), b"\x08")
        self.assertEqual(XbeImage(applied).read(td.STAGE_VA, 1), b"\x09")
        self.assertEqual(receipt["changed_bytes"], 42)


if __name__ == "__main__":
    unittest.main()
