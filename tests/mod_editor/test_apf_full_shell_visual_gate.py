"""Pin the exact APF 2K8 v24 static visual proof without runtime overclaim."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/mod_editor/apf2k8_full_shell_visual_gate.json"


class ApfFullShellVisualGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_gate_is_pinned_to_the_exact_candidate_and_contact_sheets(self) -> None:
        self.assertEqual(
            self.receipt["schema"], "apf2k8_full_shell_visual_gate/v1"
        )
        self.assertEqual(
            self.receipt["candidate"]["output_0a_sha256"],
            "0e9630348bf367032120f46d149cda7b8c3b490eaedb609fb67c0a12acf02122",
        )
        self.assertEqual(
            self.receipt["independent_catalog_gate"]["receipt_sha256"],
            "13429d6e3fa1998d86210308ca2d434f9391a6b3bf7a3773792bbd489795b716",
        )
        self.assertEqual(
            self.receipt["static_renderer_gate"]["receipt_sha256"],
            "4826c15d5fd95500ab1cdf5254e1073931974d6e0de3fe1ec83df270fc5d6d60",
        )
        self.assertEqual(
            self.receipt["static_renderer_gate"]["contact_sheet_sha256"],
            {
                "helmet_hi": "294eb885b8add058c99d81ce3e5723116b85f47d723dcec34a6e8ccf3d6df409",
                "helmet_lo": "ea1dbc569efd7405bb84a4cd31291f3b873ac3efb17998c38b4378ef1a5b363e",
            },
        )

    def test_every_headless_and_visual_gate_passed(self) -> None:
        self.assertEqual(
            self.receipt["independent_catalog_gate"]["package_layer_count"], 236
        )
        self.assertEqual(self.receipt["static_renderer_gate"]["view_count"], 10)
        self.assertTrue(self.receipt["independent_catalog_gate"]["passed"])
        self.assertTrue(self.receipt["static_renderer_gate"]["passed"])
        self.assertTrue(self.receipt["spark_visual_review"]["passed"])
        self.assertTrue(
            self.receipt["claim_boundary"][
                "static_asset_space_eagles_visual_match_proved"
            ]
        )

    def test_receipt_keeps_runtime_and_distribution_boundaries_closed(self) -> None:
        boundary = self.receipt["claim_boundary"]
        for key in (
            "runtime_consumption_proved",
            "gameplay_visibility_proved",
            "package_versus_cache_runtime_ownership_proved",
            "xbox_360_hardware_proved",
            "emulator_used",
            "xenia_patch_created",
            "default_xex_edited",
        ):
            self.assertFalse(boundary[key])
        self.assertFalse(
            self.receipt["distribution"]["contains_private_game_data"]
        )
        self.assertFalse(
            self.receipt["distribution"]["contains_decoded_texture_pixels"]
        )
        self.assertFalse(
            self.receipt["distribution"]["contains_absolute_local_paths"]
        )


if __name__ == "__main__":
    unittest.main()
