"""Offline APF composer guards, scope proofs and reproducible artifacts.

The small composition fixtures are synthetic and use an independent strict
hash gate. Canonical patch parsing exercises the production generators.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.b765 import d3_repair as repair
from mod_editor.core.errors import ValidationError


class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.baseline = bytearray(range(64))
        self.baseline[:2] = b"MZ"
        self.baseline = bytes(self.baseline)
        self.profile = repair.PROFILES[0]
        self.plans = (self.make_plan("charge", 8, (0x48001234, 0)),
                      self.make_plan("situations", 24, (0x12345678, 0xFEDCBA98)))
        self.gate = patch.object(repair, "check_image", self.pin)
        self.gate.start()
        self.addCleanup(self.gate.stop)
        self.verifier = patch.object(repair, "_verify_baseline")
        self.verify = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def make_plan(self, kind, offset, values):
        addresses = tuple(repair.IMAGE_BASE + offset + i*4 for i in range(len(values)))
        originals = tuple((address, struct.unpack_from(">I", self.baseline, address-repair.IMAGE_BASE)[0])
                          for address in addresses)
        document = SimpleNamespace(profile=self.profile, revision=4, version=4)
        return repair.PatchPlan(kind, document, (kind+"\n").encode(), kind+".toml",
                                tuple(zip(addresses, values)), originals)

    def pin(self, image):
        if hashlib.sha256(image).digest() != hashlib.sha256(self.baseline).digest():
            raise ValidationError("Synthetic fixture hash differs")
        return self.profile

    def installed(self, plans=None):
        image = bytearray(self.baseline)
        for plan in self.plans if plans is None else plans:
            for address, value in plan.words:
                struct.pack_into(">I", image, address-repair.IMAGE_BASE, value)
        return bytes(image)

    def test_composition_preserves_every_byte_outside_exact_word_scope(self):
        output, receipt = repair.compose_image(self.baseline, self.plans)
        self.assertEqual(output, self.installed())
        allowed = {address-repair.IMAGE_BASE+i for plan in self.plans for address, _ in plan.words for i in range(4)}
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(self.baseline, output)) if i not in allowed))
        self.assertEqual(receipt["scope_spans"], [
            {"file_offset": start, "bytes": 8, "input_sha256": repair.sha256(self.baseline[start:start+8]),
             "output_sha256": repair.sha256(output[start:start+8])} for start in (8, 24)])
        self.assertEqual(receipt["outside_scope_input_sha256"], receipt["outside_scope_output_sha256"])
        self.assertEqual(receipt["input_sha256"], repair.sha256(self.baseline))
        self.assertEqual(receipt["output_sha256"], repair.sha256(output))
        self.assertEqual(receipt["game_files_touched"], [])
        self.assertEqual(self.verify.call_count, 2)

    def test_idempotence_and_independently_installed_owners(self):
        for source, expected in ((self.installed(), {"charge": "already_installed", "situations": "already_installed"}),
                                 (self.installed(self.plans[:1]), {"charge": "already_installed", "situations": "retail"})):
            output, receipt = repair.compose_image(source, self.plans)
            self.assertEqual(output, self.installed())
            self.assertEqual(receipt["input_owners"], expected)
            if source == self.installed():
                self.assertEqual(receipt["changed_byte_count"], 0)

    def test_partial_stale_or_foreign_patch_refuses(self):
        for offset in (8, 12, 24, 28):
            source = bytearray(self.installed())
            source[offset] ^= 1
            with self.assertRaisesRegex(ValidationError, "partial, stale or foreign"):
                repair.compose_image(bytes(source), self.plans)

    def test_foreign_outside_scope_refuses_before_validation(self):
        for source in (self.baseline, self.installed()):
            changed = bytearray(source)
            changed[50] ^= 1
            with self.assertRaisesRegex(ValidationError, "hash differs"):
                repair.compose_image(bytes(changed), self.plans)
        self.verify.assert_not_called()

    def test_owner_overlap_profile_and_word_bounds_refuse(self):
        duplicate = replace(self.plans[1], words=self.plans[0].words, originals=self.plans[0].originals)
        with self.assertRaisesRegex(ValidationError, "overlap"):
            repair.compose_image(self.baseline, (self.plans[0], duplicate))
        mismatch = replace(self.plans[1], document=SimpleNamespace(profile=repair.PROFILES[1]))
        with self.assertRaisesRegex(ValidationError, "same executable profile"):
            repair.compose_image(self.baseline, (self.plans[0], mismatch))
        for address in (repair.IMAGE_BASE-4, repair.IMAGE_BASE+64, repair.IMAGE_BASE+1):
            bad = replace(self.plans[0], words=((address, 0),), originals=((address, 0),))
            with self.assertRaisesRegex(ValidationError, "outside the flat image"):
                repair.compose_image(self.baseline, (bad,))

    def test_missing_requests_and_duplicate_words_refuse(self):
        with self.assertRaisesRegex(ValidationError, "Choose charge"):
            repair.compose_image(self.baseline, ())
        bad = replace(self.plans[0], words=self.plans[0].words*2)
        with self.assertRaisesRegex(ValidationError, "incomplete or duplicated"):
            repair.compose_image(self.baseline, (bad,))

    def test_file_repair_is_reproducible_and_never_clobbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.pe"
            source.write_bytes(self.baseline)
            output, receipt = repair.compose_image(self.baseline, self.plans)
            with patch.object(repair, "prepare_repair", return_value=(output, receipt, self.plans)):
                repair.repair(source, root / "first", use_charge=True)
                repair.repair(source, root / "second", use_charge=True)
                first = {p.name: p.read_bytes() for p in (root/"first").iterdir()}
                second = {p.name: p.read_bytes() for p in (root/"second").iterdir()}
                self.assertEqual(first, second)
                saved = json.loads(first["scope-receipt.json"])
                self.assertTrue(saved["reapplying_same_patches_identical"])
                with self.assertRaisesRegex(ValidationError, "new output directory"):
                    repair.repair(source, root / "first", use_charge=True)
                self.assertEqual(first, {p.name: p.read_bytes() for p in (root/"first").iterdir()})
                self.assertEqual(source.read_bytes(), self.baseline)

    def test_xex_input_refuses_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"default.xex"
            source.write_bytes(b"XEX2synthetic")
            with self.assertRaisesRegex(ValidationError, "decoded flat PE"):
                repair.repair(source, root/"output", use_charge=True)
            self.assertFalse((root/"output").exists())


class CanonicalPlanTests(unittest.TestCase):
    def test_current_charge_originals_cover_every_word_for_both_profiles(self):
        for profile in repair.PROFILES:
            plan = repair.charge_plan(profile)
            self.assertEqual(repair.charge.parse_payload(plan.payload), plan.document)
            self.assertEqual(plan.document.revision, repair.charge.CURRENT_REVISION)
            self.assertEqual(set(dict(plan.originals)), set(dict(plan.words)))
            for address, original in plan.document.original_words:
                if address in dict(plan.words):
                    self.assertEqual(dict(plan.originals)[address], original)

    def test_current_situation_document_and_new_component_hook_roundtrip(self):
        weights = {"O-ManBlock": [{} for _ in range(13)]}
        weights["O-ManBlock"][2] = {"14": 4.}
        for profile in repair.PROFILES:
            document = repair.situation.SituationPatch(profile, repair.situation.encode_data({}, {}, weights))
            plan = repair.situation_plan(document.as_toml().encode())
            self.assertEqual(plan.document, document)
            self.assertGreaterEqual(document.version, 4)
            self.assertEqual(dict(plan.originals)[repair.situation.COMPONENT_HOOKS[profile.name]],
                             repair.situation.COMPONENT_ORIGINAL)
            self.assertFalse(set(dict(plan.words)) & set(dict(repair.charge_plan(profile).words)))

    def test_disabled_or_tampered_situation_toml_refuses(self):
        document = repair.situation.SituationPatch(repair.PROFILES[0], repair.situation.encode_data({}, {}, {}))
        payload = document.as_toml().encode()
        with self.assertRaisesRegex(ValidationError, "enabled situation patch"):
            repair.situation_plan(payload.replace(b"is_enabled = true", b"is_enabled = false"))
        with self.assertRaises(ValidationError):
            repair.situation_plan(payload.replace(b"All-Pro Football 2K8", b"Foreign game"))


class OwnedProfileComposerTests(unittest.TestCase):
    """Optional real-image proof; user-owned executable bytes stay private."""
    @classmethod
    def setUpClass(cls):
        names = ("APF_D3_BASE_PE", "APF_D3_TU_PE")
        if not all(os.environ.get(name) for name in names):
            raise unittest.SkipTest("Set APF_D3_BASE_PE and APF_D3_TU_PE for both owned flat-profile proofs")
        cls.paths = tuple(Path(os.environ[name]) for name in names)
        if not all(path.is_file() for path in cls.paths):
            raise AssertionError("Configured APF D3 owned flat-image fixture is absent")

    def test_current_owners_compose_and_reapply_on_both_pinned_profiles(self):
        proofs = []
        weights = {"O-ManBlock": [{} for _ in range(13)]}
        weights["O-ManBlock"][2] = {"2": .25, "14": 4.}
        for path, expected in zip(self.paths, repair.PROFILES):
            baseline = path.read_bytes()
            self.assertEqual(repair.check_image(baseline), expected)
            document = repair.situation.SituationPatch(expected, repair.situation.encode_data({}, {}, weights))
            output, receipt, plans = repair.prepare_repair(baseline, use_charge=True,
                                                         situation_payload=document.as_toml().encode())
            reapplied, repeated = repair.compose_image(output, plans)
            self.assertEqual(output, reapplied)
            self.assertEqual(repeated["changed_byte_count"], 0)
            self.assertEqual(receipt["normalized_retail_sha256"], expected.sha256)
            self.assertEqual(receipt["outside_scope_input_sha256"], receipt["outside_scope_output_sha256"])
            self.assertGreater(receipt["changed_byte_count"], 0)
            legacy = repair.situation.SituationPatch(expected, repair.situation.encode_data({}, {}, weights, version=3))
            with self.assertRaisesRegex(ValidationError, "fresh current situation patch"):
                repair.prepare_repair(baseline, use_charge=True, situation_payload=legacy.as_toml().encode())
            for offset in (2, plans[0].words[0][0]-repair.IMAGE_BASE):
                changed = bytearray(output)
                changed[offset] ^= 1
                with self.assertRaises(ValidationError):
                    repair.compose_image(bytes(changed), plans)
            proofs.append(receipt)
        target = os.environ.get("APF_D3_REPAIR_PROOF")
        if target:
            Path(target).write_text(json.dumps(proofs, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    unittest.main()
