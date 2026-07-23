#!/usr/bin/env python3
"""Focused tests for the fixed two-byte APF helmet-selector witness."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_assassins_helmet_selector_patch as patch  # noqa: E402
import apf_assassins_helmet_selector_verify as verify  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
RUNTIME = Path(
    "/media/noah/Storage/.codex-tmp/apf-assassins-helmet-only-20260716"
)


class APFAssassinsHelmetSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = patch.build_patch(SOURCE)
        cls.source = patch.transport._validate_source(SOURCE)

    def test_exact_two_byte_target_and_fixed_compression(self) -> None:
        manifest = self.result.manifest
        self.assertEqual(manifest["target"], {
            "bank_selector_decoded_offsets": [0x1E10B0, 0x1E1040],
            "bank_selector_record_indices": [465, 451],
            "expected_retail_asset_index": 1,
            "family": "helmet",
            "replacement_asset_index": 2,
            "selector_slot": 3,
            "team_index": 1,
            "team_name": "Assassins",
        })
        self.assertEqual(manifest["preservation"]["decoded_changed_byte_count"], 2)
        self.assertEqual(manifest["compression"]["payload_size_after"], 435_226)
        self.assertEqual(
            manifest["compression"]["payload_sha256_after"],
            "ce086fc74fc53c8844ddad4c6fccfef83fc28756a4e6c5627ae5f3901d7aaca8",
        )
        self.assertEqual(
            manifest["result"]["outer_entry_sha256"],
            "8b3b00f16f994602a07f7f49c4c9ed6db69e099a781cad16d168e43f4025ed29",
        )

    def test_every_other_decoded_byte_and_opaque_byte_is_exact(self) -> None:
        file_length = self.result.manifest["result"]["file_length_after"]
        output = patch.transport.apf_inner.decompress_h7a(
            self.result.entry[104:file_length],
            patch.transport.DECODED_SIZE,
            patch.transport.H7A_SHIFT,
        )
        source = self.source[5]
        differences = [
            offset
            for offset, pair in enumerate(zip(source, output))
            if pair[0] != pair[1]
        ]
        self.assertEqual(differences, [0x1E1040, 0x1E10B0])
        for offset in differences:
            self.assertEqual(source[offset], 1)
            self.assertEqual(output[offset], 2)
            self.assertEqual(output[offset + 1 : offset + 8], source[offset + 1 : offset + 8])

    def test_all_pointer_targets_and_nonhelmet_families_are_exact(self) -> None:
        allocation, _raw, _capacity, _capacity_raw = patch.core.load_authorities()
        source_decoded = self.source[5]
        file_length = self.result.manifest["result"]["file_length_after"]
        output_decoded = patch.transport.apf_inner.decompress_h7a(
            self.result.entry[104:file_length],
            patch.transport.DECODED_SIZE,
            patch.transport.H7A_SHIFT,
        )
        before = patch.core.derive_selector_layout(
            source_decoded, allocation, require_retail_vectors=True
        )
        after = patch.core.derive_selector_layout(
            output_decoded, allocation, require_retail_vectors=False
        )
        self.assertEqual(after.all_pointer_targets, before.all_pointer_targets)
        for name, family in before.families.items():
            self.assertEqual(after.families[name].offsets, family.offsets)
            self.assertEqual(after.families[name].record_indices, family.record_indices)
            expected = list(family.assets)
            if name == "helmet":
                expected[1] = 2
            self.assertEqual(after.families[name].assets, tuple(expected))

    def test_verifier_imports_no_writer_or_allocation_planner(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/apf_assassins_helmet_selector_verify.py").read_text(
                encoding="utf-8"
            )
        )
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        self.assertNotIn("apf_assassins_helmet_selector_patch", modules)
        self.assertNotIn("apf_uniform_selector_patch", modules)
        self.assertNotIn("apf_uniform_selector_allocation", modules)

    def test_wrapper_rejects_colliding_new_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            collision = Path(temporary) / "same"
            with self.assertRaisesRegex(Exception, "colliding output paths"):
                patch.write_output(SOURCE, collision, collision)
            self.assertFalse(collision.exists())

    @unittest.skipUnless(
        (RUNTIME / "output-0A").is_file()
        and (RUNTIME / "manifest.json").is_file(),
        "generated fixed witness is not present",
    )
    def test_independent_complete_volume_verifier(self) -> None:
        report = verify.verify(
            SOURCE,
            RUNTIME / "output-0A",
            RUNTIME / "manifest.json",
        )
        self.assertEqual(report["decoded_changed_byte_count"], 2)
        self.assertEqual(
            report["output_volume_sha256"],
            "939f5d9bbe546b041b04ae2a76e55c01eaf3063d933ecccb72d90fa3e87be7a8",
        )
        self.assertFalse(report["claims"]["emulator_runtime_visibility_proved"])

    @unittest.skipUnless(
        (RUNTIME / "output-0A").is_file()
        and (RUNTIME / "manifest.json").is_file(),
        "generated fixed witness is not present",
    )
    def test_manifest_claim_tampering_fails_closed(self) -> None:
        document = json.loads((RUNTIME / "manifest.json").read_text(encoding="utf-8"))
        document["claim_flags"]["emulator_runtime_visibility_proved"] = True
        with tempfile.TemporaryDirectory() as temporary:
            tampered = Path(temporary) / "manifest.json"
            tampered.write_bytes(patch.transport.canonical_json_bytes(document))
            with self.assertRaisesRegex(
                verify.VerifyError, "manifest differs"
            ):
                verify.verify(SOURCE, RUNTIME / "output-0A", tampered)


if __name__ == "__main__":
    unittest.main()
