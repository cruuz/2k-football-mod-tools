from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_static_visual_proof",
    ROOT / "tools/apf_helmet_static_visual_proof.py",
)
assert SPEC and SPEC.loader
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


class ExactHelmetStaticVisualProofTest(unittest.TestCase):
    def test_triangle_strip_expansion_respects_parity_and_restart(self) -> None:
        self.assertEqual(
            proof.expand_triangle_strip([0, 1, 2, 3, 0xFFFF, 4, 5, 6]),
            [(0, 1, 2), (2, 1, 3), (4, 5, 6)],
        )
        self.assertEqual(proof.expand_triangle_strip([0, 0, 1, 2]), [(1, 0, 2)])

    def test_compact_mesh_preserves_source_identity_and_converts_v_only(self) -> None:
        positions = [(float(index), 0.0, 0.0) for index in range(6)]
        normals = [(0.0, 1.0, 0.0)] * 6
        uvs = {1: (-0.1, 0.2), 3: (0.5, 0.6), 5: (1.1, 1.2)}
        result = proof.compact_mesh(positions, normals, [(5, 1, 3)], uvs)
        self.assertEqual(result["source_vertex_indices"], [1, 3, 5])
        self.assertEqual(result["triangles"], [[2, 0, 1]])
        self.assertEqual(result["uv_d3d"], [[-0.1, 0.2], [0.5, 0.6], [1.1, 1.2]])
        expected = [[-0.1, 0.8], [0.5, 0.4], [1.1, -0.2]]
        for actual_row, expected_row in zip(result["uv_blender"], expected, strict=True):
            for actual, wanted in zip(actual_row, expected_row, strict=True):
                self.assertAlmostEqual(actual, wanted)

    def test_region_mask_colorization_is_exact_and_fail_closed(self) -> None:
        pixels = bytearray((0, 0, 0, 136)) * (512 * 512)
        pixels[0:4] = bytes((255, 0, 0, 136))
        pixels[4:8] = bytes((0, 255, 0, 136))
        output = proof.colorize_region_mask(bytes(pixels), 0xFFC0C0C0, 0xFFFFFFFF)
        self.assertEqual(output[0:12], bytes((192, 192, 192, 255, 255, 255, 255, 255, 0, 0, 0, 0)))
        pixels[8:12] = bytes((1, 0, 0, 136))
        with self.assertRaisesRegex(proof.ProofError, "flat black/red/green"):
            proof.colorize_region_mask(bytes(pixels), 0xFFC0C0C0, 0xFFFFFFFF)

    def test_weighted_region_mask_matches_shader_equation_and_fails_closed(self) -> None:
        pixels = bytearray((0, 0, 0, 136)) * (512 * 512)
        pixels[0:4] = bytes((255, 0, 0, 136))
        pixels[4:8] = bytes((0, 255, 0, 136))
        pixels[8:12] = bytes((68, 85, 0, 136))
        output = proof.colorize_weighted_region_mask(
            bytes(pixels), 0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF,
        )
        residual = 255 - 68 - 85
        mixed = tuple(
            (shell * residual + 192 * 68 + 255 * 85 + 127) // 255
            for shell in (0, 76, 84)
        )
        self.assertEqual(output[0:16], bytes(
            (192, 192, 192, 255, 255, 255, 255, 255, *mixed, 255,
             0, 76, 84, 255)
        ))

        invalid = bytearray(pixels)
        invalid[0:4] = bytes((1, 0, 0, 136))
        with self.assertRaisesRegex(proof.ProofError, "4-bit channel lattice"):
            proof.colorize_weighted_region_mask(
                bytes(invalid), 0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF,
            )
        invalid[0:4] = bytes((136, 136, 0, 136))
        with self.assertRaisesRegex(proof.ProofError, "coverage unit"):
            proof.colorize_weighted_region_mask(
                bytes(invalid), 0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF,
            )

    def test_source_is_headless_exact_and_has_explicit_claim_boundary(self) -> None:
        source = (ROOT / "tools/apf_helmet_static_visual_proof.py").read_text(encoding="utf-8")
        blender = (ROOT / "tools/apf_helmet_static_visual_proof_blender.py").read_text(encoding="utf-8")
        self.assertIn('environment.pop("DISPLAY", None)', source)
        self.assertIn('"--background", "--factory-startup"', source)
        self.assertIn("not Xenia, gameplay, original-hardware", source)
        self.assertIn('scene.render.engine = "BLENDER_EEVEE_NEXT"', blender)
        self.assertIn('scene.render.engine = "BLENDER_EEVEE"', blender)
        self.assertIn('helmet-v18-blender-error.log', blender)
        self.assertIn("preflight_outputs(root)", blender)
        self.assertIn("unlit_emission_exact_palette_no_lights_v1", source)
        self.assertIn("unlit_emission_exact_palette_no_lights_v1", blender)
        self.assertIn('nodes.new("ShaderNodeEmission")', blender)
        self.assertIn('nodes.new("ShaderNodeUVMap")', blender)
        self.assertIn('links.new(uv_map.outputs["UV"], image.inputs["Vector"])', blender)
        self.assertIn('image.extension = "CLIP"', blender)
        self.assertIn('split_carrier_sides(groups["helmet_hi_draw_02"])', blender)
        self.assertIn("signed_x_topology_islands_with_distinct_zero_seams_v2", source)
        self.assertIn("signed_x_topology_islands_with_distinct_zero_seams_v2", blender)
        self.assertIn("exact_v18_editor_build_static_asset_space_visualization", source)
        self.assertIn("exact_v18_editor_build_static_asset_space_visualization", blender)
        self.assertIn("EXPECTED_BUILD_MANIFEST_SHA256", source)
        self.assertIn("inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1", source)
        self.assertIn("inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1", blender)
        self.assertIn("CARRIER_VISUAL_NORMAL_BIAS_M = 0.0005", blender)
        self.assertIn("render-only coplanar shell depth separation", source)
        self.assertIn('result.blend_method = "OPAQUE"', blender)
        self.assertNotIn('result.blend_method = "BLEND"', blender)
        self.assertNotIn('nodes.new("ShaderNodeBsdfTransparent")', blender)
        self.assertIn("camera_data.lens = 55.0", blender)
        self.assertIn("lens55mm_side0.72m_crown_rear0.75m_v1", blender)
        self.assertIn('"side-right": ((0.72, 0.055, 0.018), math.radians(90.0))', blender)
        self.assertIn('"side-left": ((-0.72, 0.055, 0.018), math.radians(-90.0))', blender)
        self.assertIn("right_roll_plus_pi_over_2_left_minus_pi_over_2", blender)
        self.assertIn("margin >= 24", source)
        self.assertIn("debug-carrier-material", source)
        self.assertIn("debug-carrier-uv", blender)
        self.assertIn("debug-camera-axes", blender)
        self.assertIn("debug-carrier-material-roll90", blender)
        self.assertIn("screen_right_world", source)
        self.assertIn("side-right screen horizontal is not world Z", source)
        self.assertNotIn("add_area(", blender)
        self.assertNotIn("ShaderNodeBsdfPrincipled", blender)
        self.assertNotIn("xenia", blender.casefold())
        self.assertNotIn("apf_helmet_crest_carrier_uv_wrap", source)
        self.assertNotIn("apf_helmet_crest_carrier_expand", source)

    def test_atomic_destination_refuses_existing_or_symlink_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(proof.ProofError, "refusing to overwrite"):
                proof._atomic_destination(existing)
            target = root / "target"
            target.symlink_to(existing, target_is_directory=True)
            with self.assertRaisesRegex(proof.ProofError, "refusing to overwrite"):
                proof._atomic_destination(target)

    def test_private_v18_prepares_to_exact_golden_when_available(self) -> None:
        source = Path(
            "/media/noah/Storage/.codex-tmp/"
            "apf-eagles-editor-final-v18-headless-20260803/0A"
        )
        if not source.is_file():
            self.skipTest("private exact-v18 runtime root is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "proof"
            proof.prepare_exact(source, output)
            receipt = json.loads((output / "helmet-v18-proof.json").read_text())
            self.assertEqual(
                receipt["geometry"]["sha256"],
                "06574672ad913ef836300afabdd80e1d39be647e7763ea5cac5b11bc0407d567",
            )
            self.assertEqual(
                receipt["crest"]["raw_region_mask"]["png_sha256"],
                "bbebf7171a90ba2847b1a6c5647d78fa589ad7390c31380313ed431f6f8cf516",
            )
            self.assertEqual(
                receipt["crest"]["review_material"]["png_sha256"],
                "35e06e0f009c31cb1e27cab126f072d67e12d6b3efc9ff4032091075640573f8",
            )
            self.assertIn("palette[2]*green/255",
                          receipt["crest"]["review_material"]["mapping"])
            self.assertEqual(receipt["geometry"]["minimum_crest_absolute_x_cm"], 0.0)
            self.assertLess(receipt["geometry"]["minimum_crest_z_cm"], -9.4)
            components = receipt["geometry"]["coordinate_proof"]["carrier_components"]
            self.assertEqual(components["component_count"], 2)
            for side in ("left", "right"):
                self.assertEqual(components["sides"][side]["vertex_count"], 163)
                self.assertEqual(components["sides"][side]["triangle_count"], 268)
                self.assertEqual(components["sides"][side]["x_zero_seam_vertex_count"], 3)
            projection = receipt["geometry"]["coordinate_proof"]["side_right_projection"]
            self.assertGreater(projection["projected_width_pixels"], 350.0)
            self.assertGreater(projection["projected_height_pixels"], 180.0)

            completion = {
                "schema": "apf2k8_exact_helmet_blender_stage/v2",
                "source_claim": "exact_v18_editor_build_static_asset_space_visualization",
                "blender_version": "test-only",
                "shading_contract": "unlit_emission_exact_palette_no_lights_v1",
                "physical_light_count": 0,
                "visible_source_draws": [1, 2],
                "uv_binding": "explicit:Exact APF crest UV",
                "texture_extension": "CLIP",
                "carrier_material_background_contract": (
                    "inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1"
                ),
                "carrier_visual_normal_bias": {
                    "meters": 0.0005,
                    "purpose": "render-only coplanar shell depth separation",
                    "game_geometry_changed": False,
                },
                "carrier_component_contract": {
                    "split": "signed_x_topology_islands_with_distinct_zero_seams_v2",
                    "component_count": 2,
                    "left": {
                        "vertex_count": 163, "triangle_count": 268,
                        "x_zero_seam_vertex_count": 3,
                    },
                    "right": {
                        "vertex_count": 163, "triangle_count": 268,
                        "x_zero_seam_vertex_count": 3,
                    },
                    "main_visibility": ["left", "right"],
                    "side_diagnostic_visibility": ["right"],
                },
                "camera_contract": "lens55mm_side0.72m_crown_rear0.75m_v1",
                "camera_axis_contract": (
                    "right_roll_plus_pi_over_2_left_minus_pi_over_2_"
                    "crown_rear_zero_v2"
                ),
                "camera_bases": {
                    "side-right": {
                        "screen_right_world": [0.0, 0.0, -1.0],
                        "screen_up_world": [0.0, 1.0, 0.0],
                        "forward_world": [-1.0, 0.0, 0.0],
                    }
                },
                "views": {},
                "debug_views": {},
            }
            for view_index, view in enumerate((*proof.VIEW_NAMES, *proof.DEBUG_VIEW_NAMES)):
                image = Image.new("RGB", (768, 768), (8, 10, 12))
                draw = ImageDraw.Draw(image)
                for color in range(64):
                    x0 = 48 + color * 10
                    fill = ((color * 3) % 256, (color * 5) % 256, view_index * 32)
                    if color == 0:
                        fill = (0, 76, 84)
                    draw.rectangle(
                        (x0, 48, x0 + 9, 719),
                        fill=fill,
                    )
                path = output / f"helmet-v18-{view}.png"
                image.save(path)
                section = "views" if view in proof.VIEW_NAMES else "debug_views"
                completion[section][view] = {
                    "file": path.name,
                    "sha256": proof._sha256_file(path),
                }
            blend = output / "helmet-v18-proof.blend"
            blend.write_bytes(b"test-only blender scene")
            completion["blend_scene"] = {
                "file": blend.name,
                "sha256": proof._sha256_file(blend),
            }
            proof._write_json(output / "helmet-v18-blender-stage.json", completion)
            finalized = proof.finalize_exact(output)
            self.assertEqual(len(finalized["render"]["views"]), 4)
            self.assertEqual(len(finalized["render"]["debug_views"]), 4)
            self.assertTrue((output / "helmet-v18-contact-sheet.png").is_file())
            self.assertTrue((output / "helmet-v18-debug-contact-sheet.png").is_file())
            with self.assertRaisesRegex(proof.ProofError, "already been finalized"):
                proof.finalize_exact(output)


if __name__ == "__main__":
    unittest.main()
