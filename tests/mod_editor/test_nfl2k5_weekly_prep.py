"""Standalone owner and signed native-save proofs. No disc image is loaded."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_weekly_prep as patch, nfl2k5_weekly_prep_save as prep
from mod_editor.core import nfl2k5_franchise_save as fs, nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_weekly_prep_fixture import retail_bytes, signed_save


def reseal(payload, va, value):
    result = bytearray(payload)
    at = XbeImage(payload).offset(va, len(value))
    result[at:at+len(value)] = value
    for s in _sections(result):
        result[s.header_offset+36:s.header_offset+56] = section_digest(result, s)
    return bytes(result)


class FormatTests(unittest.TestCase):
    def test_default_has_equal_rank_hours_and_two_rest_days(self):
        rows = prep.validate_plan(prep.default_plan())
        self.assertEqual(len(rows), 17)
        for activity in (93, 96, 99):
            self.assertEqual(sum(r["hours"] for r in rows if r["activity"] == activity), 10)
        self.assertEqual([(r["day"], r["activity"]) for r in rows[-2:]], [(5, 103), (6, 103)])
        self.assertTrue(all(r["repeat"] for r in rows))

    def test_malformed_rows_are_rejected_explicitly(self):
        for bad in (-1, 2**32, True, 0x010001FF, 0x0000005D, 0x0900005D, 0x7100005D):
            with self.subTest(word=bad), self.assertRaises(ValueError):
                prep.validate_plan([bad] + [prep.EMPTY] * 499)
        with self.assertRaises(ValueError):
            prep.validate_plan([])
        with self.assertRaises(ValueError):
            prep.encode(activity=173)

    def test_requests_match_committed_budget_and_no_runtime_storage(self):
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == patch.OWNER], list(patch.REQUESTS))
        self.assertLessEqual(len(patch.assembly.CODE), 1536)
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(patch.REQUESTS).issubset(set(REQUESTS)))


class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched, cls.receipt = patch.apply(cls.retail)

    def test_all_four_build_settings_are_recognized_and_replay(self):
        self.assertEqual(patch.status(self.retail), "retail")
        for cpu, remember in itertools.product((False, True), repeat=2):
            b, receipt = patch.apply(self.retail, cpu=cpu, remember=remember)
            self.assertEqual(patch.read_settings(b), dict(status="applied", cpu=cpu, remember=remember))
            self.assertEqual(patch.apply(b)[0], b)
            self.assertEqual(patch.apply(b, cpu=cpu, remember=remember)[1]["changed_bytes"], 0)
            self.assertEqual(receipt["save_growth"], 0)
            with self.assertRaisesRegex(ValueError, "clean base"):
                patch.apply(b, cpu=not cpu)

    def test_every_hook_and_owned_padding_refuse_mixed_bytes_before_mutation(self):
        for _, va, before, _ in patch.sites(patch.allocation(self.patched)["va"]):
            broken = reseal(self.patched, va, before)
            digest = hashlib.sha256(broken).digest()
            self.assertEqual(patch.status(broken), "foreign", hex(va))
            with self.assertRaises(ValueError):
                patch.apply(broken)
            self.assertEqual(hashlib.sha256(broken).digest(), digest)
        for va in (patch.allocation(self.patched)["va"] + patch.CODE_SIZE - 1, 0x51D358, 0x51E8F8, 0x2AB9B0):
            image = XbeImage(self.patched)
            broken = reseal(self.patched, va, bytes([image.read(va, 1)[0] ^ 1]))
            self.assertEqual(patch.status(broken), "foreign")
            with self.assertRaises(ValueError):
                patch.apply(broken)

    def test_undeclared_owner_and_invalid_options_refuse(self):
        allocated, _ = space.apply(self.retail, (("nfl2k5_camera", "code", 64, 16),), scaleout=True)
        with self.assertRaises(ValueError):
            patch.apply(allocated)
        for value in (1, "on", [], 0.0):
            with self.assertRaises(ValueError):
                patch.apply(self.retail, cpu=value)

    def test_173_drills_28_attributes_and_te_back_parity(self):
        audit = prep.audit_tables(self.retail)
        self.assertEqual(len(audit["activities"]), 173)
        self.assertEqual({a["field"] for a in audit["attributes"]}, set(rr.RATING_BYTE_ORDER))
        for offset in range(5):
            rows = [audit["activities"][base+offset] for base in (39, 44, 54)]
            for field in ("intensity", "injury_mask", "attribute_mask", "flags", "injury_flags"):
                self.assertEqual(len({r[field] for r in rows}), 1)
        self.assertEqual(audit["position_masks"]["TE"], audit["position_masks"]["HB"])
        self.assertEqual(audit["position_masks"]["FS"], audit["position_masks"]["CB"])

    def test_recorder_reserves_whole_hooks_and_owned_code(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        before, _ = space.apply(self.retail, patch.REQUESTS, scaleout=True)
        after, receipt = patch.apply(before)
        recorder = Recorder(self.retail)
        recorder.observe(space, "apply", self.retail, before, {})
        recorder.observe(patch, "apply", before, after, receipt)
        rows = recorder.finish(after)
        for _, va, pin, _ in patch.HOOKS:
            self.assertTrue(any(int(r["start"], 0) <= va and int(r["end"], 0) >= va + len(bytes.fromhex(pin))
                                and r["owner"] == patch.OWNER for r in rows), hex(va))


class SignedSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = signed_save()

    def test_authored_plan_is_fixed_span_and_signed_copy_reopens(self):
        original = self.source
        result, receipt = prep.replace_plan(original, 0, prep.default_plan())
        self.assertFalse(receipt["signed"])
        self.assertEqual(len(result), len(original))
        self.assertEqual(len(prep.read_plan(result, 0)["rows"]), 17)
        self.assertEqual(prep.replace_plan(result, 0, prep.default_plan())[0], result)
        doc = fs.FranchiseSave(original)
        allowed = set(range(doc.front_office_block+prep.PLAN_OFFSET, doc.front_office_block+prep.PLAN_OFFSET+2000))
        allowed.update(range(doc.front_office_block+prep.STATE_OFFSET, doc.front_office_block+prep.STATE_OFFSET+4))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(original, result)) if a != b))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "source"
            source.mkdir()
            (source / "SAVEGAME.DAT").write_bytes(original)
            (source / "EXTRA").write_bytes(rr.sign_save(original))
            container = rr.SaveContainer.load(source)
            receipt = container.write(root / "copy", result)
            self.assertTrue(receipt["signed"] and receipt["readback_verified"])
            self.assertEqual(rr.SaveContainer.load(root / "copy").savegame, result)
            self.assertEqual((source / "SAVEGAME.DAT").read_bytes(), original)

    def test_active_unknown_and_foreign_plans_refuse_without_mutation(self):
        doc = fs.FranchiseSave(self.source)
        for state in (2, 3, 0xFFFFFFFF):
            buf = bytearray(self.source)
            struct.pack_into("<I", buf, doc.front_office_block+prep.STATE_OFFSET, state)
            before = bytes(buf)
            with self.assertRaises(ValueError):
                prep.replace_plan(buf, 0, prep.default_plan())
            self.assertEqual(buf, before)
        bad = list(prep.default_plan())
        bad[0] = prep.encode(activity=1, target=32767)
        with self.assertRaises(ValueError):
            prep.replace_plan(self.source, 0, bad)

    def test_empty_plan_explicitly_clears_saved_plan_and_state(self):
        changed, _ = prep.replace_plan(self.source, 0, prep.default_plan())
        empty, _ = prep.replace_plan(changed, 0, (prep.EMPTY,) * 500)
        self.assertEqual(prep.read_plan(empty, 0)["rows"], [])
        self.assertEqual(prep.read_plan(empty, 0)["state"], 0)


if __name__ == "__main__":
    unittest.main()
