"""No emulator: byte pins, section digests, signed-imm8 arithmetic and composition."""
from pathlib import Path
import hashlib
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_season_cap as cap
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest, SECTION_COUNT

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"


def fixture():
    """Non-linear raw/VA mapping catches accidental VA-minus-base addressing."""
    buf = bytearray(0x1800)
    buf[:4] = b"XBEH"
    struct.pack_into("<I", buf, 0x104, 0x10000)
    struct.pack_into("<II", buf, 0x11C, SECTION_COUNT, 0x10200)
    struct.pack_into("<5I", buf, 0x200, 6, cap.CONTEXT_VA - 0x20, 0x100, 0x1000, 0x100)
    buf[0x1020:0x1020 + len(cap.RETAIL_CONTEXT)] = cap.RETAIL_CONTEXT
    section = _sections(buf)[0]
    buf[0x224:0x238] = section_digest(buf, section)
    return bytes(buf)


class GateTests(unittest.TestCase):
    def test_exact_one_byte_edit_receipt_digest_and_idempotence(self):
        source = fixture()
        result, receipt = cap.apply(source)
        self.assertEqual(cap.status(source), "retail")
        self.assertEqual(cap.status(result), "applied")
        off = 0x1027
        self.assertEqual(receipt["edits"], [{"label": "franchise_completion_limit", "va": "0x2480cd",
                                           "file_offset": hex(off), "bytes": 1, "before": "1e", "after": "7f"}])
        changes = {i for i, (a, b) in enumerate(zip(source, result)) if a != b}
        self.assertEqual(changes - set(range(0x224, 0x238)), {off})
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[0x224:0x238], section_digest(result, _sections(result)[0]))
        self.assertEqual(receipt["changed_bytes"], len(changes))
        again, noop = cap.apply(result)
        self.assertEqual(again, result)
        self.assertTrue(noop["already_applied"])
        self.assertEqual((noop["edits"], noop["changed_bytes"], noop["sections_repinned"]), ([], 0, []))
        self.assertFalse(receipt["witnessed"])
        self.assertFalse(receipt["calendar_repaired"])

    def test_every_foreign_immediate_refused_before_mutation_including_ff(self):
        for value in range(256):
            if value in (0x1E, 0x7F):
                continue
            with self.subTest(value=value):
                source = bytearray(fixture())
                source[0x1027] = value
                before = bytes(source)
                self.assertEqual(cap.status(source), "foreign")
                with self.assertRaises(cap.SeasonCapError):
                    cap.apply(source)
                self.assertEqual(source, before)

    def test_foreign_context_is_refused_even_with_applied_immediate(self):
        for patched in (False, True):
            for i in range(len(cap.RETAIL_CONTEXT)):
                if i == 7:
                    continue
                source = bytearray(cap.apply(fixture())[0] if patched else fixture())
                source[0x1020 + i] ^= 1
                before = bytes(source)
                with self.subTest(patched=patched, byte=i):
                    self.assertEqual(cap.status(source), "foreign")
                    with self.assertRaises(cap.SeasonCapError):
                        cap.apply(source)
                    self.assertEqual(source, before)

    def test_truncated_and_foreign_headers(self):
        for source in (b"", b"XBEH", fixture()[:0x1050], b"NOPE" + fixture()[4:]):
            self.assertEqual(cap.status(source), "foreign")
            with self.assertRaises(cap.SeasonCapError):
                cap.apply(source)

    def test_signed_immediate_endpoint_model(self):
        # This models the inspected cmp/jle plus stage test, not execution or gameplay.
        patched, _ = cap.apply(fixture())
        limit = struct.unpack("<b", patched[0x1027:0x1028])[0]
        self.assertEqual(limit, 127)
        for index in (0, 29, 30, 31, 49, 99, 100, 127, 128, 255):
            for stage in range(10):
                self.assertEqual(index <= limit or stage != 1, index < 128 or stage != 1)
        self.assertEqual(struct.unpack("<b", b"\xff")[0], -1)


@unittest.skipUnless(XBE.is_file(), f"retail default.xbe absent: {XBE}")
class RetailTests(unittest.TestCase):
    def test_special_depth_lock_context_keeps_the_pinned_bench_call_abi(self):
        from mod_editor.core import nfl2k5_depth_chart_rows as rows, nfl2k5_depth_locks as locks
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_modern_positions as modern, nfl2k5_edge_rename as edge
        source = XBE.read_bytes()
        prepared, _ = modern.apply(edge.apply(source)[0])
        special, _ = rows.apply(pools.apply(prepared)[0])
        self.assertEqual(locks.read_any(special)["stride"], 11)
        self.assertEqual(locks.read_any(special)["layout"], "special")
        # The current bench code still returns to the literal recognized by
        # PATCHED_COMPACT, carrying the encoded chain in EAX after pop eax.
        call_va, return_va = 0x24445F, 0x244464
        bench = rows.bench_bytes()
        self.assertEqual(bench[call_va - rows.BENCH_VA:return_va - rows.BENCH_VA],
                         b"\xe8" + struct.pack("<i", locks.COMPACT_VA - return_va))
        self.assertIn(b"\x3d" + struct.pack("<I", return_va), locks.PATCHED_COMPACT)
        patched, _ = locks.apply(special)
        self.assertEqual(locks.status(patched), "applied")
        self.assertEqual(rows.status(patched), "applied")
        self.assertEqual(locks.apply(patched)[0], patched)
        for original in (special, patched):
            broken = bytearray(original)
            broken[call_va - 0x10000 + 1] ^= 1
            self.assertEqual(locks.status(broken), "foreign")
            with self.assertRaises(locks.DepthLockError):
                locks.apply(broken)

    def test_retail_pin_and_all_calendar_owner_groups_commute(self):
        from mod_editor.core import nfl2k5_season_length as season
        source = XBE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9")
        direct, receipt = cap.apply(source)
        self.assertEqual(receipt["edits"][0]["file_offset"], "0x2380cd")
        calendar, _ = season.apply(source, groups=season.GROUPS)
        left, _ = cap.apply(calendar)
        right, _ = season.apply(direct, groups=season.GROUPS)
        self.assertEqual(left, right)
        self.assertEqual(cap.status(left), "applied")
        for section in _sections(left):
            self.assertEqual(left[section.header_offset + 36:section.header_offset + 56],
                             section_digest(left, section), section.index)


if __name__ == "__main__":
    unittest.main()
