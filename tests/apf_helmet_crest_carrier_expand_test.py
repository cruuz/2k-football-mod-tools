"""Focused guards for the private APF crest-carrier expansion diagnostic."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_carrier_expand_patch as patch  # noqa: E402
import apf_helmet_crest_carrier_expand_verify as verifier  # noqa: E402


SOURCE = Path("/media/noah/Storage/.codex-tmp/apf-eagles-editor-proof-v8-accurate-wrap/0A")
OUTPUT = Path("/media/noah/Storage/.codex-tmp/apf-eagles-editor-proof-v15-carrier-expand/0A")
RECEIPT = OUTPUT.with_name(OUTPUT.name + patch.RECEIPT_SUFFIX)


class CarrierBoundaryTests(unittest.TestCase):
    def test_fixed_windows_cover_both_crest_carriers(self) -> None:
        self.assertEqual(
            [(row.node_name, row.carrier_vertex_start, row.carrier_vertex_count) for row in patch.LODS],
            [("helmet_hi", 2739, 326), ("helmet_lo", 476, 128)],
        )
        allowed, preserved = verifier._authorized_and_preserved()
        self.assertEqual(len(allowed), (326 + 128) * 18)
        self.assertTrue(allowed.isdisjoint(preserved))

    def test_triangle_strip_restart_and_winding_are_deterministic(self) -> None:
        indices = [4, 5, 6, 7, 0xFFFF, 8, 9, 10]
        self.assertEqual(
            patch._triangles(indices),
            [(4, 5, 6), (6, 5, 7), (8, 9, 10)],
        )
        self.assertEqual(patch._triangles(indices), verifier._triangles(indices))

    def test_closest_point_returns_surface_barycentrics(self) -> None:
        point, barycentric = patch._closest_point(
            (0.25, 0.25, 1.0), (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        )
        self.assertEqual(point, (0.25, 0.25, 0.0))
        self.assertAlmostEqual(sum(barycentric), 1.0)
        self.assertTrue(all(value >= 0.0 for value in barycentric))

    def test_source_identity_drift_fails_before_geometry(self) -> None:
        drifted = bytearray(patch.base.SYSTEM_LENGTH)
        with self.assertRaisesRegex(patch.PatchError, "pinned retail source"):
            patch.expand_system(bytes(drifted))

    def test_verifier_does_not_import_writer(self) -> None:
        source = (ROOT / "tools/apf_helmet_crest_carrier_expand_verify.py").read_text(encoding="utf-8")
        self.assertNotIn("import apf_helmet_crest_carrier_expand_patch", source)


@unittest.skipUnless(SOURCE.is_file() and OUTPUT.is_file() and RECEIPT.is_file(), "private carrier witness is absent")
class PrivateCandidateTests(unittest.TestCase):
    def test_independent_full_volume_verification(self) -> None:
        report = verifier.verify(SOURCE, OUTPUT, RECEIPT)
        self.assertTrue(report["verified"])
        self.assertEqual(report["proof"]["changed_scne_byte_count"], 7296)
        self.assertTrue(all(row["zero_flipped_triangles"] for row in report["geometry"]))
        self.assertTrue(all(row["zero_degenerate_triangles"] for row in report["geometry"]))


if __name__ == "__main__":
    unittest.main()
