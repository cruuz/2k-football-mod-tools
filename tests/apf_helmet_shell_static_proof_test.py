from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_shell_static_proof",
    ROOT / "tools/apf_helmet_shell_static_proof.py",
)
assert SPEC and SPEC.loader
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class HelmetShellStaticProofTest(unittest.TestCase):
    def semantic_atlas(self) -> bytes:
        pixels = bytearray((0, 0, 0, 255)) * (512 * 512)
        for y_value in range(160, 352):
            for x_value in range(96, 416):
                offset = (y_value * 512 + x_value) * 4
                pixels[offset : offset + 4] = bytes((170, 68, 0, 255))
        return bytes(pixels)

    def test_triangle_strip_expansion_respects_restart_parity_and_degenerates(self) -> None:
        self.assertEqual(
            proof.expand_strip([0, 1, 2, 3, 0xFFFF, 4, 5, 6]),
            [(0, 1, 2), (2, 1, 3), (4, 5, 6)],
        )
        self.assertEqual(proof.expand_strip([7] * 20), [])

    def test_atlas_contract_and_integer_palette_equation(self) -> None:
        rgba = self.semantic_atlas()
        metrics = proof._validate_atlas(rgba)
        self.assertEqual(metrics["active_texel_count"], 320 * 192)
        material = proof.colorize_atlas(
            rgba, 0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF,
        )
        pixel = material[200, 200]
        residual = 255 - 170 - 68
        expected = [
            (shell * residual + silver * 170 + white * 68 + 127) // 255
            for shell, silver, white in zip(
                (0, 76, 84), (192, 192, 192), (255, 255, 255), strict=True,
            )
        ]
        self.assertEqual(pixel.tolist(), [*expected, 255])

        invalid = bytearray(rgba)
        invalid[2] = 17
        with self.assertRaisesRegex(proof.ProofError, "blue channel"):
            proof._validate_atlas(bytes(invalid))
        invalid = bytearray(rgba)
        invalid[0:4] = bytes((170, 102, 0, 136))
        with self.assertRaisesRegex(proof.ProofError, "coverage unit"):
            proof._validate_atlas(bytes(invalid))

    def test_software_raster_is_deterministic_and_reports_exact_identity(self) -> None:
        spec = proof.LodSpec(
            "synthetic", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 4, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 2, 2, 1,
        )
        positions = np.asarray((
            (1.0, -1.0, -1.0), (1.0, -1.0, 1.0),
            (1.0, 1.0, 1.0), (1.0, 1.0, -1.0),
        ), dtype=np.float64)
        faces = np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int32)
        geometry = proof.Geometry(
            spec=spec,
            positions=positions,
            normals=np.asarray(((1.0, 0.0, 0.0),) * 4),
            uvs=np.asarray(((0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0))),
            faces=faces,
            side_faces={"right": faces, "left": faces},
            material_before_route=2,
            overlay_triangle_count=0,
        )
        semantic = np.frombuffer(self.semantic_atlas(), dtype=np.uint8).reshape((512, 512, 4))
        material = proof.colorize_atlas(
            self.semantic_atlas(), 0xFF003366, 0xFFFFFF00, 0xFFFFFFFF,
        )
        frame = proof._frame("side-right", [geometry])
        first = proof.rasterize(geometry, faces, semantic, material, frame)
        second = proof.rasterize(geometry, faces, semantic, material, frame)
        self.assertTrue(np.array_equal(first.image, second.image))
        self.assertGreater(int(first.shell.sum()), 100_000)
        self.assertGreater(int(first.active.sum()), 20_000)
        metrics = proof.mask_metrics(first, second)
        self.assertEqual(metrics["shell_iou"], 1.0)
        self.assertEqual(metrics["active_art_iou"], 1.0)
        self.assertEqual(metrics["semantic_exact_fraction_on_shell_intersection"], 1.0)

    def test_exact_retail_geometry_decodes_after_only_v24_route_fields_are_simulated(self) -> None:
        source = Path(
            "/media/noah/Storage/for codex 1.0/extracted/"
            "All-Pro Football 2K8 (USA)/0A"
        )
        if not source.is_file():
            self.skipTest("exact private APF source is unavailable")
        archive = proof.apf_outer.parse_archive(source)
        with proof.apf_inner.ArchiveReader(archive) as reader:
            system, _receipt = proof._read_helmet_system(archive, reader)
        routed = bytearray(system)
        for spec in proof.LODS:
            material_offset = (
                spec.draw_record_offset
                + proof.SHELL_DRAW * proof.DRAW_RECORD_SIZE
                + 0x20
            )
            struct.pack_into(">I", routed, material_offset, proof.CREST_MATERIAL)
            start = spec.index_offset + spec.overlay_index_start * 2
            routed[start : start + spec.overlay_index_count * 2] = (
                struct.pack(">H", spec.overlay_vertex_start) * spec.overlay_index_count
            )
        geometries = [proof._decode_geometry(bytes(routed), spec) for spec in proof.LODS]
        self.assertEqual(
            [(len(item.faces), len(item.side_faces["right"])) for item in geometries],
            [(2214, 1107), (432, 216)],
        )
        self.assertEqual([item.overlay_triangle_count for item in geometries], [0, 0])

    def test_refuses_existing_destination_before_parsing_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "0A"
            source.write_bytes(b"placeholder")
            output = root / "proof"
            output.mkdir()
            with self.assertRaisesRegex(proof.ProofError, "refusing to overwrite"):
                proof.prepare(source, output)

    def test_explicit_argb_override_is_strict_and_all_or_nothing(self) -> None:
        self.assertEqual(proof._parse_argb("#FF003366"), 0xFF003366)
        self.assertEqual(proof._parse_argb("0xffaabbcc"), 0xFFAABBCC)
        self.assertEqual(proof._parse_argb(" 11223344 "), 0x11223344)
        for invalid in ("#123456", "GG003366", "0x123456789"):
            with self.assertRaises(proof.argparse.ArgumentTypeError):
                proof._parse_argb(invalid)

        errors = io.StringIO()
        with redirect_stderr(errors):
            status = proof.main([
                "--input-0a", "/does/not/matter",
                "--output", "/does/not/matter-either",
                "--shell-argb", "FF003366",
            ])
        self.assertEqual(status, 1)
        self.assertIn("must be supplied together", errors.getvalue())

    def test_explicit_palette_does_not_depend_on_custom_appearance_slot(self) -> None:
        source = Path(
            "/media/noah/Storage/for codex 1.0/extracted/"
            "All-Pro Football 2K8 (USA)/0A"
        )
        if not source.is_file():
            self.skipTest("exact private APF source is unavailable")
        selected_asset, selected_outer, colors, receipt = proof._resolve_target(
            source,
            asset_index=30,
            outer_entry=1133,
            appearance_slot=999_999,
            bank_name="home",
            palette_override=(0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF),
        )
        self.assertEqual((selected_asset, selected_outer), (30, 1133))
        self.assertEqual(colors, (0xFF004C54, 0xFFC0C0C0, 0xFFFFFFFF))
        self.assertEqual(receipt["palette_source"], "explicit_cli_argb_override")
        self.assertIsNone(receipt["appearance_slot"])

    def test_standalone_parse_view_uses_temporary_pristine_siblings(self) -> None:
        source = Path(
            "/media/noah/Storage/for codex 1.0/extracted/"
            "All-Pro Football 2K8 (USA)/0A"
        )
        if not source.is_file():
            self.skipTest("exact private APF source is unavailable")
        view_parent: Path | None = None
        with proof._standalone_parse_view(source, source) as (parse_0a, receipt):
            view_parent = parse_0a.parent
            self.assertNotEqual(parse_0a, source)
            self.assertTrue(receipt["used"])
            parsed = proof.apf_outer.parse_archive(parse_0a)
            self.assertEqual([pack.name for pack in parsed.packs], ["0A", "0B", "1A", "1B"])
        assert view_parent is not None
        self.assertFalse(view_parent.exists())

    def test_contract_is_headless_and_independent_of_v24_writer_verifier(self) -> None:
        source = (ROOT / "tools/apf_helmet_shell_static_proof.py").read_text(encoding="utf-8")
        self.assertIn("headless_static_asset_space_whole_shell_visualization_only", source)
        self.assertIn("proof_eligible_for_runtime_or_visual_quality_claim", source)
        self.assertIn("draw 1 is not routed to crest material 2", source)
        self.assertIn("legacy draw-2 overlay is not degenerate", source)
        self.assertIn("layer_binding_independent", source)
        self.assertIn("private temporary parse view", source)
        self.assertNotIn("import apf_helmet_crest_wrap_patch", source)
        self.assertNotIn("import apf_helmet_crest_wrap_verify", source)
        self.assertNotIn("subprocess", source)


if __name__ == "__main__":
    unittest.main()
