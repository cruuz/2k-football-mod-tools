"""Two .rdata patches: the Position row on Edit Player page 1 and the Pro Bowl Votes tab order."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_position_row as row  # noqa: E402
from mod_editor.core import nfl2k5_probowl_order as pb  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"


class ShapeTests(unittest.TestCase):
    def test_the_position_row_lands_after_last_name_and_keeps_the_terminator(self) -> None:
        words = struct.unpack("<7I", row.PATCHED_LIST)
        self.assertEqual(words[:2], struct.unpack("<2I", row.RETAIL_LIST[:8]))
        self.assertEqual(words[2], row.POSITION_DESCRIPTOR_VA)
        self.assertEqual(words[3:6], struct.unpack("<3I", row.RETAIL_LIST[8:20]))
        self.assertEqual(words[6], 0)

    def test_the_probowl_order_is_a_permutation_with_kickers_last(self) -> None:
        self.assertEqual(sorted(pb.PATCHED_TABS), sorted(pb.RETAIL_TABS))
        self.assertEqual(pb.PATCHED_TABS[-2:], pb.KICKING_TABS)
        self.assertEqual(pb.PATCHED_NAMES, ("QB", "HB", "FB", "WR", "TE", "C", "G", "T", "DT", "DE", "OLB", "ILB", "CB", "SS", "FS", "K", "P"))
        self.assertEqual(pb.PATCHED_LIST[-4:], b"\0\0\0\0")

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(row.status(b"XBEH" + b"\0" * 0x200), "foreign")
        self.assertEqual(pb.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(rdata.RdataSiteError):
            rdata.offset_of(b"XBEH" + b"\0" * 0x200, 0x54A254)


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()

    def test_status_apply_idempotent_and_foreign(self) -> None:
        for module in (row, pb):
            self.assertEqual(module.status(self.retail), "retail")
            patched, receipt = module.apply(self.retail)
            self.assertEqual(module.status(patched), "applied")
            self.assertGreater(receipt["changed_bytes"], 0)
            again, receipt2 = module.apply(patched)
            self.assertEqual(again, patched)
            self.assertTrue(receipt2.get("already_applied"))
            tampered = bytearray(patched)
            off = rdata.offset_of(patched, module.sites()[0][1])
            tampered[off] ^= 0x01
            self.assertEqual(module.status(bytes(tampered)), "foreign")

    def test_both_lists_gain_position_and_the_next_struct_is_untouched(self) -> None:
        patched, _r = row.apply(self.retail)
        for va in (row.LIST_CREATED_FACE_VA, row.LIST_REAL_FACE_VA):
            off = rdata.offset_of(patched, va)
            words = struct.unpack_from("<8I", patched, off)
            self.assertEqual(words[2], row.POSITION_DESCRIPTOR_VA)
            self.assertEqual(words[6], 0)
            self.assertEqual(patched[off + 28: off + 36], self.retail[off + 28: off + 36])

    def test_section_digests_are_recomputed(self) -> None:
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        patched, _r = pb.apply(self.retail)
        for section in _sections(patched):
            d = section.header_offset + 36
            self.assertEqual(patched[d: d + 20], section_digest(patched, section), section.index)

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        a, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, team_column=True, position_row=True, probowl_order=True)
        b1, _ = pb.apply(self.retail)
        b2, _ = row.apply(b1)
        b, _ = tt._apply_all(b2, None, catch_slider=False, returner_fix=True, team_column=True, position_row=True, probowl_order=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
