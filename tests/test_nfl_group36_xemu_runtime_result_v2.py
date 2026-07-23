#!/usr/bin/env python3
"""Tests for the pinned positive NFL group36 xemu diagnostic result."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
import sys

sys.path.insert(0, str(TOOLS))
import nfl_group36_xemu_runtime_result_v2 as result  # noqa: E402


REPORT = ROOT / "reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json"
SCHEMA = ROOT / "reports/specs/nfl2k5_group36_xemu_runtime_result.v2.schema.json"

V1_PINS = {
    "docs/research/nfl_group36_xemu_runtime_result.md": (
        5_577,
        "df3f85b774959fc2a134fe8617b5d4cc106d6204f309bc05d739b10492e11368",
    ),
    "reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json": (
        4_353,
        "a606e8ef4a1030d1e2dca5202204e401eace7cc0a5b9ce0ff3443198e634bc6d",
    ),
    "reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json": (
        6_934,
        "ca553ac95199813fec740a6eca305f4860daf21f062303ce2d98c689af3854b1",
    ),
    "tests/test_nfl_group36_xemu_runtime_result.py": (
        9_842,
        "e449e3da9d525e59e6601df1f4f1ac53f9ed6e1b6f24169eebe23066466ab444",
    ),
    "tools/nfl_group36_xemu_runtime_result.py": (
        22_386,
        "3d1d6bff68f000f86f72f52db83613cef06053d0daf9d3b1e7df449843129f1f",
    ),
    "tools/validate_nfl_group36_xemu_runtime_result.sh": (
        5_007,
        "94f5b0213959ae7a8b725ee8490af50bdc11520a7082c7e607971b3e4f815227",
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeResultV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(REPORT.read_bytes())

    def test_checked_positive_result_is_narrow_and_derived(self) -> None:
        claims = result.validate_document(self.document)
        self.assertTrue(claims["control_target_outer_loaded_proved"])
        self.assertTrue(claims["expanded_target_outer_loaded_proved"])
        self.assertTrue(claims["target_outer_loaded_proved"])
        self.assertTrue(claims["geometry_visibility_proved"])
        self.assertTrue(claims["geometry_visibility_scope_pinned_xemu_diagnostic_only"])
        self.assertTrue(claims["same_camera_sequence_proved"])
        self.assertTrue(claims["xemu_clean_shutdown_pair_observed"])
        for key in (
            "changed_count_mesh_writeback_proved",
            "distribution_ready",
            "general_static_mesh_runtime_writeback_proved",
            "original_xbox_hardware_proved",
            "pixel_aligned_matched_pair_proved",
            "production_ready",
            "public_editor_exposed",
            "retail_signed_executable_chain_preserved",
            "runtime_gpu_trace_proved",
            "strict_v1_exact_frame_branch_satisfied",
        ):
            self.assertFalse(claims[key], key)

    def test_camera_sequence_is_exact_but_frames_are_not_pixel_aligned(self) -> None:
        camera = self.document["pair"]["camera_protocol"]
        self.assertEqual(camera["steps"], [
            {
                "duration_seconds": "4.00",
                "gap_seconds": None,
                "input": "left_stick_down",
                "press_seconds": None,
                "tap_count": None,
            },
            {
                "duration_seconds": None,
                "gap_seconds": "0.05",
                "input": "dpad_up",
                "press_seconds": "0.06",
                "tap_count": 15,
            },
            {
                "duration_seconds": None,
                "gap_seconds": "0.04",
                "input": "button_b_zoom_out",
                "press_seconds": "0.05",
                "tap_count": 30,
            },
        ])
        self.assertTrue(camera["same_sequence"])
        self.assertTrue(camera["end_zone_facing"])
        self.assertFalse(camera["pixel_aligned"])
        self.assertFalse(camera["same_play_state"])
        self.assertFalse(camera["same_team_state"])

    def test_geometry_claim_falls_when_the_unique_wall_observation_is_removed(self) -> None:
        document = copy.deepcopy(self.document)
        document["runs"]["expanded_wall"]["runtime"]["authored_wall_visible"] = False
        claims = result.derive_claims(document)
        self.assertFalse(claims["geometry_visibility_proved"])
        self.assertTrue(claims["target_outer_loaded_proved"])
        document["claims"] = claims
        document["status"] = result.derive_status(claims)
        with self.assertRaisesRegex(result.ResultError, "runtime observation differs"):
            result.validate_document(document)

    def test_target_claim_falls_when_the_loader_asset_route_is_removed(self) -> None:
        document = copy.deepcopy(self.document)
        document["runs"]["control"]["runtime"]["selection"]["actual_asset_code"] = "s18"
        claims = result.derive_claims(document)
        self.assertFalse(claims["control_target_outer_loaded_proved"])
        self.assertFalse(claims["target_outer_loaded_proved"])
        self.assertFalse(claims["geometry_visibility_proved"])
        document["claims"] = claims
        document["status"] = result.derive_status(claims)
        with self.assertRaisesRegex(result.ResultError, "runtime observation differs"):
            result.validate_document(document)

    def test_artifact_or_screenshot_identity_drift_is_refused(self) -> None:
        document = copy.deepcopy(self.document)
        document["runs"]["control"]["artifacts"]["xiso"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(result.ResultError, "identity differs"):
            result.validate_document(document)

        document = copy.deepcopy(self.document)
        screenshots = document["runs"]["expanded_wall"]["artifacts"]["screenshots"]
        screenshots.reverse()
        with self.assertRaisesRegex(result.ResultError, "canonical-role ordered"):
            result.validate_document(document)

    def test_forbidden_claims_cannot_be_self_promoted(self) -> None:
        for key in (
            "distribution_ready",
            "original_xbox_hardware_proved",
            "production_ready",
            "public_editor_exposed",
            "retail_signed_executable_chain_preserved",
        ):
            document = copy.deepcopy(self.document)
            document["claims"][key] = True
            with self.assertRaisesRegex(result.ResultError, "independently derived"):
                result.validate_document(document)

    def test_schema_const_enforces_every_publication_safety_boundary(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        self.assertEqual(schema["$id"], result.SCHEMA_URI)
        claims = schema["properties"]["claims"]["properties"]
        for key in (
            "distribution_ready",
            "original_xbox_hardware_proved",
            "production_ready",
            "public_editor_exposed",
            "retail_signed_executable_chain_preserved",
        ):
            self.assertEqual(claims[key], {"const": False})
        self.assertEqual(claims["geometry_visibility_proved"], {"const": True})
        self.assertEqual(claims["strict_v1_exact_frame_branch_satisfied"], {"const": False})

    def test_v1_negative_chain_is_immutable_and_separate(self) -> None:
        self.assertEqual(self.document["schema"], result.SCHEMA_ID)
        self.assertNotIn("selector_skip_negative", json.dumps(self.document))
        for relative, (size, sha256) in V1_PINS.items():
            path = ROOT / relative
            self.assertEqual(path.stat().st_size, size, relative)
            self.assertEqual(digest(path), sha256, relative)

    def test_file_verifier_refuses_size_hash_and_symlink_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "evidence.bin"
            source.write_bytes(b"runtime evidence")
            row = {
                "path": source.name,
                "sha256": digest(source),
                "size": source.stat().st_size,
            }
            result._verify_file(root, row, "fixture")
            with self.assertRaisesRegex(result.ResultError, "size differs"):
                result._verify_file(root, dict(row, size=row["size"] + 1), "fixture")
            link = root / "evidence-link.bin"
            link.symlink_to(source)
            with self.assertRaisesRegex(result.ResultError, "non-symlink"):
                result._verify_file(root, dict(row, path=link.name), "fixture")

    def test_png_header_check_is_dimension_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frame.png"
            prefix = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            path.write_bytes(prefix + struct.pack(">II", 1280, 720))
            result._verify_png(path, "fixture")
            path.write_bytes(prefix + struct.pack(">II", 640, 480))
            with self.assertRaisesRegex(result.ResultError, "dimensions differ"):
                result._verify_png(path, "fixture")

    def test_frozen_offline_and_workflow_semantics_are_consistent(self) -> None:
        result._verify_offline_semantics(ROOT)
        for name in result.RUN_NAMES:
            result._verify_workflow_semantics(ROOT, name)
            result._verify_config_semantics(ROOT, name)

    def test_validator_has_no_emulator_launch_or_pixel_classification_path(self) -> None:
        source = (ROOT / "tools/nfl_group36_xemu_runtime_result_v2.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("flatpak run", source)
        self.assertNotIn("x11_window", source)
        self.assertNotIn("PIL", source)
        self.assertNotIn("cv2", source)


if __name__ == "__main__":
    unittest.main()
