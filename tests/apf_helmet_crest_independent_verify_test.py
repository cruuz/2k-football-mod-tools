"""Hostile tests for the independent APF shell-atlas verifier."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import struct
import sys
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_helmet_crest_wrap_patch as writer  # noqa: E402
import apf_helmet_crest_wrap_verify as verifier  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
DESIGN = Path(
    "/media/noah/Storage/.codex-tmp/apf-eagles-clean-source-region-mask-v3.png"
)


def read_outer(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return os.pread(descriptor, writer.OUTER_SIZE, writer.OUTER_OFFSET)
    finally:
        os.close(descriptor)


class IndependenceTests(unittest.TestCase):
    def test_verifier_does_not_import_writer_numpy_or_private_artifact(self) -> None:
        source = inspect.getsource(verifier)
        self.assertNotIn("import apf_helmet_crest_wrap_patch", source)
        self.assertNotIn("import numpy", source)
        self.assertNotIn(".codex-tmp", source)
        self.assertNotIn("xenia", source.lower())

    def test_contract_is_v24_shell_atlas(self) -> None:
        self.assertEqual(verifier.PATCH_SCHEMA, writer.SCHEMA)
        self.assertEqual(
            verifier.VERIFY_SCHEMA,
            "apf2k8_helmet_shell_atlas_verify/v24",
        )
        self.assertEqual(verifier.OPERATION, writer.OPERATION)


@unittest.skipUnless(SOURCE.is_file() and DESIGN.is_file(), "retail/Eagles inputs absent")
class GoldenAndTamperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_outer = read_outer(SOURCE)
        with Image.open(DESIGN) as image:
            raw = image.convert("RGBA").tobytes()
        # Opaque-shell-body contract: the v24 design's uniform 0x88 transport
        # alpha is rejected; raise every texel to the opaque value while
        # keeping the exact RGB lattice.
        cls.design = bytes(
            value if index % 4 != 3 else 255
            for index, value in enumerate(raw)
        )
        cls.built = writer.build_patch(cls.source_outer, design_rgba=cls.design)
        cls.source_scne = writer._parse_outer(cls.source_outer, source=True).system
        cls.output_scne = writer._parse_outer(
            cls.built.rebuilt_entry,
            source=False,
            expected_output_sha256=writer.EXPECTED_OUTPUT_OUTER_SHA256,
            expected_system_sha256=writer.EXPECTED_OUTPUT_SYSTEM_SHA256,
        ).system

    def test_independent_outer_and_atlas_proof_passes(self) -> None:
        report = verifier.verify_outer(
            self.source_outer,
            self.built.rebuilt_entry,
            self.built.manifest,
            design_rgba=self.design,
            atlas_rgba=self.built.atlas_rgba,
        )
        self.assertTrue(report["verified"])
        self.assertTrue(report["proof"]["eagles_regression_hash_checked"])
        self.assertTrue(report["proof"]["fixed_semantic_bake_exact"])
        self.assertTrue(report["proof"]["shell_vertices_indices_and_uv_exact"])
        self.assertTrue(report["proof"]["old_overlay_zero_triangle_degenerate"])
        self.assertEqual(
            [row["faces_per_side"] for row in report["geometry"]], [1107, 216]
        )

    def test_shell_vertex_tamper_is_rejected(self) -> None:
        output = bytearray(self.output_scne)
        spec = verifier.LODS[0]
        output[spec.stream_start + 12] ^= 1
        with self.assertRaisesRegex(verifier.VerifyError, "vertex/UV stream changed"):
            verifier.verify_geometry(
                self.source_scne,
                bytes(output),
                design_rgba=self.design,
                atlas_rgba=self.built.atlas_rgba,
            )

    def test_accessory_draw_tamper_is_rejected(self) -> None:
        output = bytearray(self.output_scne)
        spec = verifier.LODS[1]
        output[spec.draw_record_offset + 3 * verifier.DRAW_RECORD_SIZE] ^= 1
        with self.assertRaisesRegex(verifier.VerifyError, "draw 3 record changed"):
            verifier.verify_geometry(
                self.source_scne,
                bytes(output),
                design_rgba=self.design,
                atlas_rgba=self.built.atlas_rgba,
            )

    def test_live_draw2_triangle_is_rejected(self) -> None:
        output = bytearray(self.output_scne)
        spec = verifier.LODS[1]
        start = spec.index_offset + spec.carrier_index_start * 2
        struct.pack_into(">3H", output, start, spec.carrier_vertex_start,
                         spec.carrier_vertex_start + 1,
                         spec.carrier_vertex_start + 2)
        with self.assertRaisesRegex(verifier.VerifyError, "not one degenerate index"):
            verifier.verify_geometry(
                self.source_scne,
                bytes(output),
                design_rgba=self.design,
                atlas_rgba=self.built.atlas_rgba,
            )

    def test_atlas_tamper_is_rejected_independently(self) -> None:
        atlas = bytearray(self.built.atlas_rgba)
        atlas[(200 * 512 + 200) * 4] ^= 17
        with self.assertRaisesRegex(verifier.VerifyError, "independent fixed-coordinate"):
            verifier.verify_geometry(
                self.source_scne,
                self.output_scne,
                design_rgba=self.design,
                atlas_rgba=bytes(atlas),
            )

    def test_receipt_atlas_hash_tamper_is_rejected(self) -> None:
        receipt = dict(self.built.manifest)
        receipt["result"] = dict(receipt["result"])
        receipt["result"]["shell_atlas_rgba_sha256"] = "0" * 64
        with self.assertRaisesRegex(verifier.VerifyError, "receipt atlas hash differs"):
            verifier.verify_outer(
                self.source_outer,
                self.built.rebuilt_entry,
                receipt,
                design_rgba=self.design,
                atlas_rgba=self.built.atlas_rgba,
            )


if __name__ == "__main__":
    unittest.main()
