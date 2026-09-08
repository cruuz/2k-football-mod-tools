"""Evidence refusals; no disc/archive allocation or production mutation."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import nfl2k5_my_career_mode_audit as audit
from tests.nfl2k5_my_career_fixture import XBE, draft_save
from tests.mod_editor.test_nfl2k5_franchise_save import FRANCHISE1


class EvidenceRefusalTests(unittest.TestCase):
    def test_zero_sample_never_authorizes_tail_allocation(self):
        payload = draft_save()
        receipt = audit.audit_save(payload)
        self.assertEqual(receipt["nonzero_bytes"], 0)
        self.assertFalse(receipt["allocation_allowed"])
        self.assertFalse(receipt["signature_checked"])
        self.assertFalse(receipt["modified"])

    def test_occupied_tail_is_reported_at_exact_offsets_without_mutation(self):
        payload = bytearray(draft_save())
        start = audit.SAVE_TAIL_START
        payload[start:start + 4] = b"\xff\xff\xff\x3f"
        payload[start + 127] = 7
        original = bytes(payload)
        receipt = audit.audit_save(original)
        self.assertEqual(receipt["nonzero_bytes"], 5)
        self.assertEqual(receipt["occupied_words"], [
            {"relative_offset": "0x0", "value": "0x3fffffff"},
            {"relative_offset": "0x7c", "value": "0x7000000"}])
        self.assertEqual(bytes(payload), original)
        self.assertFalse(receipt["allocation_allowed"])

    def test_save_size_and_framing_refusals(self):
        good = draft_save()
        for payload in (good[:-1], good + b"\0", bytes(len(good)),
                        good[:0x91320] + b"\x01" + good[0x91321:]):
            with self.assertRaises(ValueError):
                audit.audit_save(payload)

    @unittest.skipUnless(FRANCHISE1.is_file(), "private year-7 Franchise1 evidence absent")
    def test_real_year_seven_save_defeats_the_empty_tail_assumption(self):
        with FRANCHISE1.open("rb") as source:
            payload = source.read(audit.franchise.FRANCHISE_SAVE_SIZE + 1)
        expected = "063baa6954477e544ee04ae3b390055e247ce3e4c56328667aff7f72ffa791dd"
        tail = payload[audit.SAVE_TAIL_START:audit.SAVE_TAIL_START + audit.SAVE_TAIL_SIZE]
        save_pin = "0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7"
        if hashlib.sha256(payload).hexdigest() != save_pin or hashlib.sha256(tail).hexdigest() != expected:
            self.skipTest("private occupied-tail evidence pin differs")
        receipt = audit.audit_save(payload)
        self.assertEqual(receipt["year_field"], 7)
        self.assertEqual(receipt["nonzero_bytes"], 12)
        self.assertEqual([row["value"] for row in receipt["occupied_words"]],
                         ["0x3fffffff", "0x9bffffff", "0x119307f"])
        self.assertFalse(receipt["allocation_allowed"])

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
