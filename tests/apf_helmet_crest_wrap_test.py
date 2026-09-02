"""Focused gates for the production APF whole-shell atlas writer."""

from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
import sys
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as patch  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
DESIGN = Path(
    "/media/noah/Storage/.codex-tmp/apf-eagles-clean-source-region-mask-v3.png"
)


def read_outer(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return os.pread(descriptor, patch.OUTER_SIZE, patch.OUTER_OFFSET)
    finally:
        os.close(descriptor)


def read_rgba(path: Path) -> bytes:
    with Image.open(path) as image:
        return image.convert("RGBA").tobytes()


class PublicBoundaryTests(unittest.TestCase):
    def test_public_signature_uses_only_semantic_rgba(self) -> None:
        signature = inspect.signature(patch.build_patch)
        self.assertEqual(tuple(signature.parameters), ("source_outer", "design_rgba"))
        self.assertEqual(
            signature.parameters["design_rgba"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def test_contract_and_regression_hashes_are_pinned(self) -> None:
        self.assertEqual(patch.SCHEMA, "apf2k8_helmet_shell_atlas_patch/v24")
        self.assertEqual(
            patch.OPERATION,
            "route_shell_draw_to_crest_atlas_and_neutralize_overlay",
        )
        self.assertEqual(
            patch.EXPECTED_OUTPUT_SYSTEM_SHA256,
            "bd49f04cb2bf58fc91f024af6a76405f3cefab3f63d2d98f445a413b67ef5ca7",
        )
        self.assertEqual(
            patch.EXPECTED_OUTPUT_OUTER_SHA256,
            "ae51ccdea7124bc9615fe39fda6632363e9bf4270e0b623b0707635fcd701323",
        )

    def test_writer_has_no_emulator_numpy_or_private_dependency(self) -> None:
        source = inspect.getsource(patch)
        self.assertNotIn("import numpy", source)
        self.assertNotIn("/.codex-tmp/", source)
        self.assertNotIn("xenia", source.lower())

    def test_source_identity_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(patch.PatchError, "pinned source allocation"):
            patch.build_patch(
                b"not retail outer 1310",
                design_rgba=bytes(patch.RGBA_LENGTH),
            )

    def test_new_semantic_design_rejects_blue(self) -> None:
        design = bytearray(bytes((0, 0, 0, 255)) * (512 * 512))
        design[(200 * 512 + 200) * 4 : (200 * 512 + 200) * 4 + 4] = bytes(
            (0, 0, 17, 255)
        )
        with self.assertRaisesRegex(patch.PatchError, "blue zero"):
            patch._validate_design_mask(bytes(design))

    def test_translucent_shell_body_background_is_rejected(self) -> None:
        # The v24 production design carried the retail bounded-crest 8/15
        # transport sentinel (0x88) as its shell-body alpha; in the routed
        # full-shell lane that rendered the helmet see-through and flat.
        design = bytearray(bytes((0, 0, 0, 136)) * (512 * 512))
        design[(200 * 512 + 200) * 4 : (200 * 512 + 200) * 4 + 4] = bytes(
            (255, 0, 0, 136)
        )
        with self.assertRaisesRegex(patch.PatchError, "opaque"):
            patch._validate_design_mask(bytes(design))

    def test_translucent_black_shell_texel_is_rejected(self) -> None:
        design = bytearray(bytes((0, 0, 0, 255)) * (512 * 512))
        design[(200 * 512 + 200) * 4 : (200 * 512 + 200) * 4 + 4] = bytes(
            (255, 0, 0, 255)
        )
        design[(201 * 512 + 200) * 4 : (201 * 512 + 200) * 4 + 4] = bytes(
            (0, 0, 0, 136)
        )
        with self.assertRaisesRegex(patch.PatchError, "opaque"):
            patch._validate_design_mask(bytes(design))

    def test_opaque_background_with_lattice_aa_edges_is_accepted(self) -> None:
        design = bytearray(bytes((0, 0, 0, 255)) * (512 * 512))
        design[(200 * 512 + 200) * 4 : (200 * 512 + 200) * 4 + 4] = bytes(
            (255, 0, 0, 255)
        )
        # 17-step lattice AA edge texels keep per-texel 4-bit alpha fidelity.
        design[(200 * 512 + 201) * 4 : (200 * 512 + 201) * 4 + 4] = bytes(
            (119, 0, 0, 136)
        )
        design[(200 * 512 + 202) * 4 : (200 * 512 + 202) * 4 + 4] = bytes(
            (51, 0, 0, 85)
        )
        background, active = patch._validate_design_mask(bytes(design))
        self.assertEqual(background, bytes((0, 0, 0, 255)))
        self.assertEqual(active, 3)

    def test_fixed_canvas_axes_map_to_physical_shell_axes(self) -> None:
        top_front = (0.0, patch.SEMANTIC_TOP_Y, patch.SEMANTIC_FRONT_Z)
        bottom_rear = (0.0, patch.SEMANTIC_BOTTOM_Y, patch.SEMANTIC_REAR_Z)
        self.assertEqual(patch._semantic_coordinate(top_front), (0.0, 0.0))
        self.assertEqual(patch._semantic_coordinate(bottom_rear), (1.0, 1.0))
        # Moving right on the design moves rearward (lower shell Z); moving
        # down moves lower (lower shell Y). Neither axis is bbox-normalized.
        x_left = patch.SEMANTIC_FRONT_Z - 0.25 * (
            patch.SEMANTIC_FRONT_Z - patch.SEMANTIC_REAR_Z
        )
        x_right = patch.SEMANTIC_FRONT_Z - 0.75 * (
            patch.SEMANTIC_FRONT_Z - patch.SEMANTIC_REAR_Z
        )
        y_top = patch.SEMANTIC_TOP_Y - 0.25 * (
            patch.SEMANTIC_TOP_Y - patch.SEMANTIC_BOTTOM_Y
        )
        y_bottom = patch.SEMANTIC_TOP_Y - 0.75 * (
            patch.SEMANTIC_TOP_Y - patch.SEMANTIC_BOTTOM_Y
        )
        self.assertGreater(x_left, x_right)
        self.assertGreater(y_top, y_bottom)

    def test_cli_no_longer_accepts_a_guarded_transport_input(self) -> None:
        signature = inspect.signature(patch.publish_outer)
        self.assertNotIn("guarded_png", signature.parameters)


def opaque_design(rgba: bytes) -> bytes:
    """Raise the v24 transport-sentinel alpha to the opaque shell contract."""

    return bytes(
        value if index % 4 != 3 else 255 for index, value in enumerate(rgba)
    )


@unittest.skipUnless(SOURCE.is_file() and DESIGN.is_file(), "retail/Eagles inputs absent")
class EaglesGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_outer = read_outer(SOURCE)
        cls.raw_v24_design = read_rgba(DESIGN)
        cls.design = opaque_design(cls.raw_v24_design)
        cls.result = patch.build_patch(cls.source_outer, design_rgba=cls.design)
        cls.source = patch._parse_outer(cls.source_outer, source=True)
        cls.output = patch._parse_outer(
            cls.result.rebuilt_entry,
            source=False,
            expected_output_sha256=patch.EXPECTED_OUTPUT_OUTER_SHA256,
            expected_system_sha256=patch.EXPECTED_OUTPUT_SYSTEM_SHA256,
        )

    def test_v24_translucent_design_is_rejected_by_the_contract(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.raw_v24_design).hexdigest(),
            "c9a915df7f66dae85a5f620ad4907aadc2cf3f4941fcfc86a074c68a34362d6c",
        )
        with self.assertRaisesRegex(patch.PatchError, "opaque"):
            patch.build_patch(
                self.source_outer, design_rgba=self.raw_v24_design
            )

    def test_exact_scne_outer_and_atlas_regression(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.result.rebuilt_entry).hexdigest(),
            patch.EXPECTED_OUTPUT_OUTER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(self.output.system).hexdigest(),
            patch.EXPECTED_OUTPUT_SYSTEM_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(self.result.atlas_rgba).hexdigest(),
            "5dfeaeb7402abe37c3fddcff0ede91fd09b26d7600bdddd75791b0e54236bf39",
        )
        self.assertEqual(
            self.result.manifest["metrics"]["atlas_bake"]["background_rgba_hex"],
            "000000ff",
        )
        self.assertTrue(
            self.result.manifest["metrics"]["atlas_bake"][
                "opaque_shell_body_contract"
            ]
        )
        self.assertEqual(self.result.manifest["metrics"]["changed_byte_count"], 2283)
        self.assertFalse(
            self.result.manifest["claim_flags"]["visual_eagles_match_proved"]
        )

    def test_only_route_words_and_draw2_indices_change(self) -> None:
        allowed: set[int] = set()
        for spec in patch.LODS:
            allowed.update(range(patch.MATERIAL_FIELD_OFFSETS[spec.node_name],
                                 patch.MATERIAL_FIELD_OFFSETS[spec.node_name] + 4))
            start = spec.index_offset + spec.carrier_index_start * 2
            allowed.update(range(start, start + spec.carrier_index_count * 2))
            stream_end = spec.stream_start + spec.vertex_count * patch.STRIDE
            self.assertEqual(
                self.source.system[spec.stream_start:stream_end],
                self.output.system[spec.stream_start:stream_end],
            )
            neutral = patch._indices(self.output.system, spec)[
                spec.carrier_index_start:
                spec.carrier_index_start + spec.carrier_index_count
            ]
            self.assertEqual(len(set(neutral)), 1)
            self.assertEqual(patch._triangles(neutral), [])
        changed = {
            index for index, pair in enumerate(zip(self.source.system, self.output.system))
            if pair[0] != pair[1]
        }
        self.assertTrue(changed <= allowed)

    def test_stock_shell_atlas_is_bilateral_unmixed_and_nonoverlapping(self) -> None:
        rows = self.result.manifest["metrics"]["atlas_bake"]["lods"]
        self.assertEqual([row["faces_per_side"] for row in rows], [1107, 216])
        self.assertTrue(all(row["bilateral_same_semantic_canvas"] for row in rows))
        self.assertTrue(all(not row["mixed_uv_orientation"] for row in rows))
        self.assertTrue(all(row["projected_overlap_count"] == 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
