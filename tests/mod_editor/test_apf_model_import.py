"""Fail-closed tests for the stock helmet/player same-topology importer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from mod_editor.apf_studio import model_export, model_import


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


class ImportBoundaryTests(unittest.TestCase):
    def test_boundary_names_every_preserved_unsupported_lane(self) -> None:
        boundary = model_import.MODEL_IMPORT_BOUNDARY
        for value in (
            "POSITION-only",
            "Vertex count",
            "expanded triangles",
            "POSITION W",
            "normals",
            "blend indices/weights",
            "materials",
            "animation",
            "collision",
        ):
            self.assertIn(value, boundary)

    def test_accessor_cannot_read_past_its_declared_buffer_view(self) -> None:
        document = {
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 1,
                    "type": "VEC3",
                }
            ],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 4}],
        }
        with self.assertRaisesRegex(model_import.ModelImportError, "bufferView"):
            model_import._accessor_values(document, b"\0" * 12, 0, position=True)

    def test_publisher_copies_then_patches_a_tiny_new_volume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            source = root / "source-0A"
            original = bytes(range(64))
            source.write_bytes(original)
            output_dir = root / "new"
            output_dir.mkdir()
            output = output_dir / "0A"
            replacement = b"APF"
            patch = model_import.ModelPatch(
                model_export.target("player"),
                17,
                len(replacement),
                replacement,
                hashlib.sha256(original[17:20]).hexdigest(),
                hashlib.sha256(replacement).hexdigest(),
                1,
                3,
                0.001,
                False,
                {"schema": model_import.IMPORT_SCHEMA},
            )
            with mock.patch.object(
                model_import, "build_model_patch", return_value=patch
            ) as builder, mock.patch.object(
                model_import, "try_reflink", return_value=False
            ):
                receipt = model_import.import_model(
                    source, "player", root / "edited.gltf", output
                )

            builder.assert_called_once()
            expected = bytearray(original)
            expected[17:20] = replacement
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(output.read_bytes(), bytes(expected))
            self.assertEqual(receipt.output_0a, output)
            published = json.loads(receipt.receipt.read_text(encoding="utf-8"))
            self.assertEqual(published["published_output"]["size_bytes"], len(original))
            self.assertEqual(
                published["published_output"]["outer_entry_reread_sha256"],
                patch.output_entry_sha256,
            )


@unittest.skipUnless(PRIVATE_INDEX.is_file(), "private APF archive is not present")
class PrivateRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.gltf = cls.root / "player.gltf"
        cls.export = model_export.export_model(PRIVATE_INDEX, "player", cls.gltf)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _restore_export(self) -> None:
        # Export is exclusive, so rebuild the three private files in a clean
        # nested directory when a prior test intentionally changed the binary.
        nested = Path(
            tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.root)
        )
        self.gltf = nested / "player.gltf"
        self.export = model_export.export_model(PRIVATE_INDEX, "player", self.gltf)

    def test_unmodified_export_is_whole_entry_no_op(self) -> None:
        patch = model_import.build_model_patch(PRIVATE_INDEX, "player", self.gltf)
        self.assertTrue(patch.no_op)
        self.assertEqual(patch.changed_vertex_count, 0)
        self.assertEqual(patch.source_entry_sha256, patch.output_entry_sha256)
        self.assertTrue(patch.manifest["preservation"]["independent_reopen_exact"])

    def test_one_position_change_rebuilds_only_position_xyz(self) -> None:
        self._restore_export()
        document = json.loads(self.gltf.read_text(encoding="utf-8"))
        binary = self.gltf.parent / document["buffers"][0]["uri"]
        payload = bytearray(binary.read_bytes())
        original = struct.unpack_from("<f", payload, 0)[0]
        struct.pack_into("<f", payload, 0, original + 0.01)
        binary.write_bytes(payload)
        patch = model_import.build_model_patch(PRIVATE_INDEX, "player", self.gltf)
        self.assertFalse(patch.no_op)
        self.assertEqual(patch.changed_vertex_count, 1)
        self.assertGreater(patch.changed_position_component_bytes, 0)
        self.assertLess(patch.maximum_quantization_error, 0.01)
        self.assertEqual(len(patch.rebuilt_entry), patch.outer_size)
        preservation = patch.manifest["preservation"]
        self.assertTrue(preservation["expanded_triangle_lists_exact"])
        self.assertTrue(preservation["position_w_exact"])
        self.assertTrue(
            preservation["normal_tangent_uv_blend_skin_material_attachment_bytes_exact"]
        )

    def test_changed_topology_and_material_are_rejected(self) -> None:
        self._restore_export()
        document = json.loads(self.gltf.read_text(encoding="utf-8"))
        binary = self.gltf.parent / document["buffers"][0]["uri"]
        index_accessor = document["accessors"][1]
        index_view = document["bufferViews"][index_accessor["bufferView"]]
        offset = index_view.get("byteOffset", 0) + index_accessor.get("byteOffset", 0)
        payload = bytearray(binary.read_bytes())
        first = struct.unpack_from("<I", payload, offset)[0]
        struct.pack_into("<I", payload, offset, first + 1)
        binary.write_bytes(payload)
        with self.assertRaisesRegex(model_import.ModelImportError, "topology"):
            model_import.build_model_patch(PRIVATE_INDEX, "player", self.gltf)

        self._restore_export()
        document = json.loads(self.gltf.read_text(encoding="utf-8"))
        document["materials"] = [{"name": "unsupported"}]
        self.gltf.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(model_import.ModelImportError, "materials"):
            model_import.build_model_patch(PRIVATE_INDEX, "player", self.gltf)


if __name__ == "__main__":
    unittest.main()
