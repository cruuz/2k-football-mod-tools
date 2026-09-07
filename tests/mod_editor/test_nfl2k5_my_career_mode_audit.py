"""Evidence refusals; no disc/archive allocation or production mutation."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import nfl2k5_my_career_mode_audit as audit
from tests.nfl2k5_my_career_fixture import XBE


class EvidenceRefusalTests(unittest.TestCase):
    def test_foreign_and_oversized_inputs_make_no_claim(self):
        for payload in (b"", b"XBEH" + bytes(2044), bytes(audit.MAX_XBE_BYTES + 1)):
            with self.assertRaises(ValueError):
                audit.audit(payload)

    @unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe evidence absent")
    def test_pinned_receipt_and_single_byte_damage(self):
        if XBE.stat().st_size > audit.MAX_XBE_BYTES:
            self.skipTest("retail evidence exceeds 16 MiB")
        payload = XBE.read_bytes()
        if hashlib.sha256(payload).hexdigest() != audit.RETAIL_SHA256:
            self.skipTest("USA retail XBE evidence pin differs")
        receipt = audit.audit(payload)
        self.assertFalse(receipt["runtime_witnessed"])
        self.assertFalse(receipt["save_candidate"]["production_allocation_authorized_by_evidence"])
        self.assertEqual(receipt["descriptor_words"]["created_player_list_target"]["value"], "0x56e9c4")
        damaged = bytearray(payload)
        damaged[0x3461F0 - 0x10000] ^= 1
        with self.assertRaisesRegex(ValueError, "pin differs"):
            audit.audit(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
