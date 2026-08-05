"""Focused guards for the APF high/low helmet material-route witness."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_dual_lod_shell_material_route_patch as patch  # noqa: E402
import apf_helmet_dual_lod_shell_material_route_verify as verifier  # noqa: E402


PRIVATE_SOURCE = Path(
    "/media/noah/Storage/.codex-tmp/apf-eagles-editor-proof-v9-shell-v1/0A"
)


class DualLodMaterialWordBoundaryTests(unittest.TestCase):
    def test_big_endian_slot_changes_are_exactly_two_low_bytes(self) -> None:
        source = bytearray(0xCD000)
        for route in patch.LOD_ROUTES:
            struct.pack_into(">I", source, route.material_field_offset, 1)
        output = patch.replace_material_words(bytes(source))
        self.assertEqual(
            patch.base.difference_offsets(bytes(source), output),
            [0x9A13, 0xCCAD3],
        )
        for route in patch.LOD_ROUTES:
            self.assertEqual(
                struct.unpack_from(">I", output, route.material_field_offset)[0], 2
            )

    def test_either_source_word_drift_fails_closed_before_change(self) -> None:
        source = bytearray(0xCD000)
        struct.pack_into(">I", source, 0x9A10, 1)
        struct.pack_into(">I", source, 0xCCAD0, 2)
        with self.assertRaisesRegex(patch.base.PatchError, "helmet_lo.*source drift"):
            patch.replace_material_words(bytes(source))

    def test_route_constants_cover_high_and_low_nodes(self) -> None:
        self.assertEqual(
            [
                (route.node_index, route.node_name, route.material_field_offset)
                for route in patch.LOD_ROUTES
            ],
            [(0, "helmet_hi", 0x9A10), (32, "helmet_lo", 0xCCAD0)],
        )
        self.assertEqual(verifier.CHANGED_BYTE_OFFSETS, [0x9A13, 0xCCAD3])

    def test_verifier_does_not_import_the_dual_lod_writer(self) -> None:
        source = (
            ROOT / "tools/apf_helmet_dual_lod_shell_material_route_verify.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import apf_helmet_dual_lod_shell_material_route_patch", source)


@unittest.skipUnless(PRIVATE_SOURCE.is_file(), "private v9 APF witness is not present")
class PrivateSourceBuildTests(unittest.TestCase):
    def test_guarded_rebuild_has_pinned_two_byte_result(self) -> None:
        before = PRIVATE_SOURCE.stat()
        built = patch.build_patch(PRIVATE_SOURCE)
        after = PRIVATE_SOURCE.stat()
        self.assertEqual(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        )
        self.assertEqual(len(built.rebuilt_entry), patch.base.OUTER_SIZE)
        self.assertEqual(
            hashlib.sha256(built.rebuilt_entry).hexdigest(),
            patch.OUTPUT_OUTER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(built.output_system).hexdigest(),
            patch.OUTPUT_SYSTEM_SHA256,
        )
        self.assertEqual(
            patch.base.difference_offsets(built.source.system, built.output_system),
            [0x9A13, 0xCCAD3],
        )
        self.assertEqual(
            patch._validate_semantic_routes(built.output_system, 2), None
        )


if __name__ == "__main__":
    unittest.main()
