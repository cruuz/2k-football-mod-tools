from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_shell_prebuild_static_proof",
    ROOT / "tools/apf_helmet_shell_prebuild_static_proof.py",
)
assert SPEC and SPEC.loader
prebuild = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prebuild
SPEC.loader.exec_module(prebuild)


class HelmetShellPrebuildStaticProofTest(unittest.TestCase):
    def test_semantic_png_contract_is_exact_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "semantic.png"
            image = Image.new("RGBA", (512, 512), (0, 0, 0, 255))
            for y_value in range(120, 390):
                for x_value in range(30, 480):
                    if (x_value + y_value) % 17 == 0:
                        image.putpixel((x_value, y_value), (255, 0, 0, 255))
            image.save(path)
            rgba, receipt = prebuild.load_semantic_png(path)
            self.assertEqual(len(rgba), 512 * 512 * 4)
            self.assertEqual(len(receipt["file_sha256"]), 64)
            self.assertGreater(receipt["metrics"]["active_texel_count"], 1_000)

            image.putpixel((10, 10), (0, 0, 17, 255))
            image.save(path)
            with self.assertRaisesRegex(prebuild.PrebuildProofError, "blue channel"):
                prebuild.load_semantic_png(path)

    def test_exact_private_geometry_accepts_only_simulated_v24_fields(self) -> None:
        source = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
        if not source.is_file():
            self.skipTest("exact private APF source is unavailable")
        archive = prebuild.apf_outer.parse_archive(source)
        with prebuild.apf_inner.ArchiveReader(archive) as reader:
            system, _receipt = prebuild.core._read_helmet_system(archive, reader)
        routed, receipt = prebuild.simulate_v24_route(system)
        self.assertEqual(receipt["schema"], "apf2k8_helmet_shell_route_simulation/v24")
        self.assertNotEqual(receipt["source_system_sha256"], receipt["simulated_system_sha256"])
        self.assertGreater(receipt["changed_byte_count"], 1_000)
        geometries = [
            prebuild.core._decode_geometry(routed, spec)
            for spec in prebuild.core.LODS
        ]
        self.assertEqual([len(row.faces) for row in geometries], [2214, 432])
        self.assertEqual([row.overlay_triangle_count for row in geometries], [0, 0])

    def test_contract_is_headless_prebuild_only(self) -> None:
        source = (ROOT / "tools/apf_helmet_shell_prebuild_static_proof.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("headless_prebuild_static_asset_space", source)
        self.assertIn("v24_route_fields_simulated_only", source)
        self.assertIn('"no_copied_game_volume": True', source)
        self.assertIn('"no_emulator": True', source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("xenia", source.lower())


if __name__ == "__main__":
    unittest.main()
