from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_static_visual_calibration",
    ROOT / "tools/apf_helmet_static_visual_calibration.py",
)
assert SPEC and SPEC.loader
calibration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibration)


class HelmetStaticVisualCalibrationTest(unittest.TestCase):
    def test_xy_fit_is_exact_nearest_and_preserves_flat_palette_alpha(self) -> None:
        source = bytearray((0, 0, 0, 136)) * (512 * 512)
        for y in range(143, 369):
            for x in range(512):
                offset = (y * 512 + x) * 4
                source[offset : offset + 4] = (
                    bytes((255, 0, 0, 136)) if (x + y) % 2
                    else bytes((0, 255, 0, 136))
                )
        output, transform = calibration.fit_active_xy_nearest(bytes(source))
        self.assertEqual(calibration.active_rgb_bbox(output), (0, 0, 511, 511))
        self.assertEqual(transform["input_active_size"], [512, 226])
        self.assertEqual(transform["x_scale"], 1.0)
        self.assertAlmostEqual(transform["y_scale"], 512 / 226)
        self.assertEqual(
            {tuple(output[index : index + 4]) for index in range(0, len(output), 4)},
            {(255, 0, 0, 136), (0, 255, 0, 136)},
        )

    def test_wrong_active_bbox_fails_closed(self) -> None:
        source = bytearray((0, 0, 0, 136)) * (512 * 512)
        source[0:4] = bytes((255, 0, 0, 136))
        with self.assertRaisesRegex(calibration.CalibrationError, "active bbox differs"):
            calibration.fit_active_xy_nearest(bytes(source))

    def test_private_v17_receipt_is_nonproof_when_available(self) -> None:
        source = ROOT / ".codex-tmp/apf-eagles-carrier-v17-runtime-game/0A"
        if not source.is_file():
            self.skipTest("private exact-v17 runtime root is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "calibration"
            receipt = calibration.prepare(source, output)
            reopened = json.loads((output / "helmet-v17-proof.json").read_text())
            self.assertEqual(receipt["claim"], calibration.CLAIM)
            self.assertEqual(reopened["schema"], calibration.SCHEMA)
            self.assertFalse(reopened["proof_eligible"])
            self.assertFalse(reopened["package_bound"])
            self.assertFalse(reopened["calibration"]["game_bytes_changed"])
            self.assertEqual(
                reopened["calibration"]["transform"]["input_active_bbox_inclusive"],
                [0, 143, 511, 368],
            )
            self.assertEqual(
                reopened["calibration"]["transform"]["output_canvas"], [512, 512]
            )

    def test_separate_blender_entry_is_strictly_calibration_labeled(self) -> None:
        source = (ROOT / "tools/apf_helmet_static_visual_calibration_blender.py").read_text()
        self.assertIn("apf2k8_helmet_static_visual_calibration/v1", source)
        self.assertIn("calibration_not_package_bound", source)
        self.assertNotIn("exact_v17_static_asset_space_visualization", source)


if __name__ == "__main__":
    unittest.main()
