#!/usr/bin/env python3
"""Regression tests for the bounded cross-title model compatibility audit."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import blender_cross_title_model_compare as blender_compare  # noqa: E402
import cross_title_model_compatibility as compatibility  # noqa: E402


class CrossTitleModelCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report, cls.matrix, cls.bones = compatibility.generate()

    def test_representative_geometry_metrics(self) -> None:
        expected = {
            "nfl_stadium": (143, 562, 17_819, 27_066, 9_514),
            "apf_stadium": (115, 115, 156_501, 288_240, 96_080),
            "nfl_player": (1, 86, 7_396, 18_721, 10_006),
            "apf_player": (1, 1, 351, 918, 306),
        }
        for role, counts in expected.items():
            asset = self.report["assets"][role]
            self.assertEqual(
                (
                    asset["mesh_count"],
                    asset["primitive_count"],
                    asset["unique_vertex_count"],
                    asset["index_reference_count"],
                    asset["nondegenerate_triangle_count"],
                ),
                counts,
            )
            self.assertEqual(asset["materials"], 0)
            self.assertEqual(asset["images"], 0)

    def test_player_skin_mismatch_remains_explicit(self) -> None:
        nfl = self.report["assets"]["nfl_player"]
        apf = self.report["assets"]["apf_player"]
        self.assertEqual(nfl["joint_count"], 62)
        self.assertEqual(apf["joint_count"], 21)
        self.assertEqual(
            nfl["influence_count_distribution"],
            {"1": 5_356, "2": 1_921, "3": 119},
        )
        self.assertEqual(apf["influence_count_distribution"], {"1": 351})
        self.assertEqual(apf["source_position_formats"], ["snorm16x4"])
        self.assertIn("NORMAL", apf["attributes"][0])
        self.assertIn("TEXCOORD_0", apf["attributes"][0])
        self.assertNotIn("NORMAL", nfl["attributes"][0])
        self.assertNotIn("TEXCOORD_0", nfl["attributes"][0])

    def test_matrix_has_no_installable_import_claim(self) -> None:
        expected = {
            "coordinate_basis": "authoring-compatible",
            "units": "partial",
            "positions": "authoring-compatible",
            "topology": "intermediate-only",
            "normals_uv": "blocked",
            "skeleton": "retarget-required",
            "weights": "retarget-required",
            "inverse_bind": "authoring-compatible",
            "materials_shaders": "incompatible",
            "textures": "conversion-required",
            "lod": "unknown",
            "collision": "unknown",
            "container_endian": "incompatible",
            "allocation_writeback": "blocked",
            "runtime_routing": "blocked",
        }
        self.assertEqual(
            {row["surface"]: row["status"] for row in self.matrix},
            expected,
        )
        self.assertEqual(len(self.matrix), 15)

    def test_bone_candidates_are_authoring_only(self) -> None:
        self.assertEqual(len(self.bones), 124)
        summaries = self.report["bone_candidates"]["summaries"]
        self.assertEqual(
            summaries["apf_player_shadow_21"],
            {
                "target_joint_count": 21,
                "nfl_joint_count": 62,
                "name_and_parent": 7,
                "name_only": 6,
                "unmatched": 49,
                "ambiguous": 0,
                "direct_index_copy_safe": False,
            },
        )
        self.assertEqual(
            summaries["apf_player_hires_92"],
            {
                "target_joint_count": 92,
                "nfl_joint_count": 62,
                "name_and_parent": 3,
                "name_only": 11,
                "unmatched": 48,
                "ambiguous": 0,
                "direct_index_copy_safe": False,
            },
        )
        self.assertTrue(all(
            row["claim"] ==
            "authoring retarget candidate only; not an engine bone-index map"
            for row in self.bones
        ))

    def test_fail_closed_claims(self) -> None:
        claims = self.report["claims"]
        self.assertTrue(claims["standard_gltf_blender_comparison_possible"])
        self.assertTrue(claims["selected_player_coordinate_basis_compatible"])
        self.assertTrue(claims["partial_name_based_retarget_candidates_emitted"])
        false_claims = {
            "direct_joint_index_copy_safe",
            "direct_serialized_mesh_copy_safe",
            "nfl_stadium_direct_apf_import_possible",
            "nfl_player_direct_apf_import_possible",
            "edited_gltf_to_apf_scne_writer_available",
            "apf_model_archive_writeback_available",
            "runtime_visibility_tested",
            "emulator_started",
            "retail_original_modified",
        }
        for name in false_claims:
            self.assertIs(claims[name], False, name)

    def test_name_normalization_is_not_an_engine_map(self) -> None:
        self.assertEqual(compatibility.normalized_bone_name("HI_res:31:lhumerus"), "lhumerus")
        self.assertEqual(compatibility.normalized_bone_name("def_l_hand"), "lhand")
        root = next(
            row for row in self.bones
            if row["target_skeleton"] == "apf_player_shadow_21" and row["nfl_index"] == 0
        )
        self.assertEqual(root["status"], "name_and_parent")
        self.assertFalse(summaries_direct_copy(self.report))

    def test_blender_manifest_is_hash_checked_reference_only(self) -> None:
        report, checked = blender_compare.load_report(blender_compare.DEFAULT_REPORT)
        self.assertEqual(report["schema"], compatibility.SCHEMA)
        self.assertEqual(len(checked), 4)
        self.assertEqual([item["role"] for item, _ in checked],
                         ["nfl_stadium", "apf_stadium", "nfl_player", "apf_player"])
        self.assertFalse(report["claims"]["apf_model_archive_writeback_available"])


def summaries_direct_copy(report: dict) -> bool:
    """Return true only if every emitted target summary authorizes index copy."""

    return all(
        summary["direct_index_copy_safe"]
        for summary in report["bone_candidates"]["summaries"].values()
    )


if __name__ == "__main__":
    unittest.main()
