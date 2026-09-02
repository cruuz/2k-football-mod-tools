"""Focused guards for the private APF UV-driven crest-carrier witness."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_carrier_uv_wrap_patch as patch  # noqa: E402
import apf_helmet_crest_carrier_uv_wrap_verify as verifier  # noqa: E402


SOURCE = Path("/media/noah/Storage/.codex-tmp/apf-eagles-editor-proof-v8-accurate-wrap/0A")
OUTPUT = Path("/media/noah/Storage/.codex-tmp/apf-eagles-editor-proof-v16-uv-wrap/0A")
RECEIPT = OUTPUT.with_name(OUTPUT.name + patch.RECEIPT_SUFFIX)


class UvWrapBoundaryTests(unittest.TestCase):
    def test_mapping_contract_is_front_seam_to_rear_with_small_bias(self) -> None:
        self.assertGreater(patch.FRONT_Z, 12.0)
        self.assertLess(patch.REAR_Z, -10.0)
        self.assertEqual(patch.OUTWARD_BIAS, 0.045)
        self.assertLess(patch.FRONT_RAMP_START, patch.FRONT_RAMP_END)
        self.assertGreater(patch.REAR_TAPER_START, patch.FRONT_RAMP_END)

    def test_smoothstep_is_bounded_and_deterministic(self) -> None:
        self.assertEqual(patch._smoothstep(-1.0), 0.0)
        self.assertEqual(patch._smoothstep(0.0), 0.0)
        self.assertEqual(patch._smoothstep(0.5), 0.5)
        self.assertEqual(patch._smoothstep(1.0), 1.0)
        self.assertEqual(patch._smoothstep(2.0), 1.0)

    def test_writer_uses_both_fixed_carriers_without_uv_edits(self) -> None:
        self.assertEqual(
            [
                (row.node_name, row.carrier_vertex_start, row.carrier_vertex_count)
                for row in patch.previous.LODS
            ],
            [("helmet_hi", 2739, 326), ("helmet_lo", 476, 128)],
        )
        allowed, preserved = verifier.prior._authorized_and_preserved()
        self.assertTrue(allowed.isdisjoint(preserved))

    def test_source_identity_drift_fails_before_mapping(self) -> None:
        drifted = bytes(patch.previous.base.SYSTEM_LENGTH)
        with self.assertRaisesRegex(patch.PatchError, "pinned retail source"):
            patch.previous.expand_system(
                drifted, geometry_builder=patch._uv_wrap_geometry,
            )

    def test_verifier_does_not_import_uv_wrap_writer(self) -> None:
        source = (
            ROOT / "tools/apf_helmet_crest_carrier_uv_wrap_verify.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import apf_helmet_crest_carrier_uv_wrap_patch", source)


@unittest.skipUnless(
    SOURCE.is_file() and OUTPUT.is_file() and RECEIPT.is_file(),
    "private UV-wrap witness is absent",
)
class PrivateUvWrapCandidateTests(unittest.TestCase):
    def test_independent_full_volume_and_mapping_verification(self) -> None:
        report = verifier.verify(SOURCE, OUTPUT, RECEIPT)
        self.assertTrue(report["verified"])
        self.assertEqual(report["proof"]["changed_scne_byte_count"], 7765)
        self.assertTrue(report["proof"]["front_crown_seam_to_rear_outer_shell"])
        self.assertTrue(report["proof"]["quantized_outward_bias"])
        self.assertLess(report["mapping"][0]["minimum_absolute_x"], 0.001)
        self.assertTrue(all(row["minimum_z"] < -9.0 for row in report["mapping"]))
        self.assertTrue(all(row["u_to_z_correlation"] < -0.98 for row in report["mapping"]))


if __name__ == "__main__":
    unittest.main()
