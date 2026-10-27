"""b778-tr2 (PB68/PB90): in-season trades reach the native Player Trade confirm.

The practice-squad trade guard used to reject every offer when the receiving
club was at the 53-man active limit, because the native apply appends before it
removes the outgoing player and needs a transient 54th slot. These tests pin
the corrected guard and the two redirected trade appends. The full-roster
execution test lives in test_nfl2k5_practice_squad (Unicorn fixture).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: E402

# The retail extraction is private; point NFL2K5_RETAIL_EXTRACTION at it to run the patch tests.
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "")) / "ESPN NFL 2K5 (USA)" / "default.xbe"


class ConstantsTests(unittest.TestCase):
    def test_trade_insert_symbol_and_native_call_sites(self) -> None:
        self.assertIn("trade_insert", ps.SYMBOLS)
        self.assertIn("ps_trade_room", ps.SYMBOLS)
        sites = {site.va: site for site in ps.sites()}
        for va, retail in ((0x2BC74B, bytes.fromhex("e89077e0ff")),
                           (0x2BC79A, bytes.fromhex("e84177e0ff"))):
            self.assertIn(va, sites)
            site = sites[va]
            self.assertEqual(site.retail, retail)
            self.assertEqual(site.patched[0], 0xE8)
            self.assertEqual(site.patched, bytes.fromhex("e8") + struct.pack(
                "<i", ps.SYMBOLS["trade_insert"] - va - 5))
        # The guard must keep its native trade entry hook.
        self.assertEqual(sites[0x2BC670].patched[0], 0xE9)


@unittest.skipUnless(RETAIL.is_file(), "private retail NFL 2K5 default.xbe absent")
class RetailPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("private XBE is not the pinned US retail executable")
        cls.patched, cls.receipt = ps.apply(cls.retail)

    def test_retail_apply_redirects_both_trade_appends(self) -> None:
        self.assertEqual(ps.status(self.retail), "retail")
        self.assertEqual(ps.status(self.patched), "applied")
        target = ps.SYMBOLS["trade_insert"]
        for va in (0x2BC74B, 0x2BC79A):
            off = ps._offset(self.patched, va, ps._sections(self.patched))
            raw = self.patched[off:off + 5]
            self.assertEqual(raw[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack_from("<i", raw, 1)[0], target)
        again, receipt = ps.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
