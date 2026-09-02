"""Headless contract tests for the bounded APF stadium mesh hand-off."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from mod_editor.apf_studio import stadium_model_import as service


class StadiumModelImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.target = service.target_by_id("outer14.inner8.node13")
        self.assertEqual(self.target.vertex_count, 8)
        self.positions = tuple((float(index), 0.0, 0.0) for index in range(8))
        self.indices = (0, 1, 2, 2, 3, 0)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _gltf(
        self,
        name: str,
        *,
        positions: tuple[tuple[float, float, float], ...] | None = None,
        indices: tuple[int, ...] | None = None,
        attributes: dict[str, int] | None = None,
        material: bool = False,
        translation: list[float] | None = None,
    ) -> Path:
        positions = positions or self.positions
        indices = indices or self.indices
        position_bytes = b"".join(struct.pack("<3f", *value) for value in positions)
        index_offset = len(position_bytes)
        binary = position_bytes + b"".join(struct.pack("<I", value) for value in indices)
        binary_path = self.root / f"{name}.bin"
        binary_path.write_bytes(binary)
        primitive: dict[str, object] = {
            "attributes": attributes or {"POSITION": 0},
            "indices": 1,
            "mode": 4,
        }
        document: dict[str, object] = {
            "accessors": [
                {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"},
                {"bufferView": 1, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
            ],
            "asset": {"version": "2.0"},
            "bufferViews": [
                {"buffer": 0, "byteLength": len(position_bytes)},
                {"buffer": 0, "byteLength": len(indices) * 4, "byteOffset": index_offset},
            ],
            "buffers": [{"byteLength": len(binary), "uri": binary_path.name}],
            "meshes": [{
                "extras": {"apf2k8_target_id": self.target.target_id},
                "primitives": [primitive],
            }],
            "nodes": [{"mesh": 0}],
        }
        if material:
            primitive["material"] = 0
            document["materials"] = [{"name": "unsupported"}]
        if translation is not None:
            document["nodes"] = [{"mesh": 0, "translation": translation}]
        path = self.root / f"{name}.gltf"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_catalog_maps_only_the_proved_scene_and_77_nodes(self) -> None:
        self.assertEqual(len(service.targets()), 77)
        self.assertEqual(
            service.target_for_surface(14, 8, (13,)),
            self.target,
        )
        self.assertIsNone(service.target_for_surface(15, 8, (13,)))
        self.assertIsNone(service.target_for_surface(14, 8, (999,)))

    def test_parser_rejects_every_unproved_authoring_lane(self) -> None:
        with self.assertRaisesRegex(service.StadiumModelImportError, "UV, normal"):
            service._mesh_payload(
                self._gltf("normal", attributes={"POSITION": 0, "NORMAL": 0}),
                self.target,
            )
        with self.assertRaisesRegex(service.StadiumModelImportError, "materials"):
            service._mesh_payload(self._gltf("material", material=True), self.target)
        with self.assertRaisesRegex(service.StadiumModelImportError, "Apply every"):
            service._mesh_payload(
                self._gltf("transform", translation=[1.0, 0.0, 0.0]),
                self.target,
            )

    def test_import_builds_canonical_recipe_then_uses_independent_verifier(self) -> None:
        reference = self._gltf("reference")
        changed_positions = list(self.positions)
        changed_positions[0] = (0.25, 0.0, 0.0)
        edited = self._gltf("edited", positions=tuple(changed_positions))
        manifest = {
            "result": {"changed_decoded_block0_byte_count": 1},
            "mode": "changed",
        }
        verification = {"checks": {"manifest_every_field_independently_rederived": True}}

        def write_output(_game: Path, recipe_path: Path, artifact: Path) -> dict[str, object]:
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            self.assertEqual(recipe["target_id"], self.target.target_id)
            self.assertEqual(recipe["positions"][0], [0.25, 0.0, 0.0])
            artifact.mkdir()
            (artifact / "1A").write_bytes(b"copied-pack")
            (artifact / service.stadium_writer.MANIFEST_NAME).write_text("{}")
            return manifest

        expected_hash = service.stadium_writer.load_catalog()[1][self.target.target_id]["position0"]["retail_lane_sha256"]
        with mock.patch.object(service, "_source_position_hash", return_value=expected_hash), mock.patch.object(
            service.stadium_writer, "write_output", side_effect=write_output
        ) as writer, mock.patch.object(
            service.stadium_verifier, "verify", return_value=(verification, manifest)
        ) as verifier:
            receipt = service.import_edited_mesh(
                self.root / "game",
                reference,
                self.target.target_id,
                edited,
                self.root / "published",
            )

        writer.assert_called_once()
        verifier.assert_called_once()
        self.assertEqual(receipt.changed_byte_count, 1)
        self.assertFalse(receipt.no_op)
        self.assertEqual(receipt.output_pack.read_bytes(), b"copied-pack")

    def test_changed_topology_fails_before_writer_and_leaves_no_output(self) -> None:
        reference = self._gltf("reference-topology")
        edited = self._gltf("edited-topology", indices=(0, 2, 1, 2, 3, 0))
        expected_hash = service.stadium_writer.load_catalog()[1][self.target.target_id]["position0"]["retail_lane_sha256"]
        output = self.root / "must-not-exist"
        with mock.patch.object(service, "_source_position_hash", return_value=expected_hash), mock.patch.object(
            service.stadium_writer, "write_output"
        ) as writer, self.assertRaisesRegex(service.StadiumModelImportError, "topology differs"):
            service.import_edited_mesh(
                self.root / "game",
                reference,
                self.target.target_id,
                edited,
                output,
            )
        writer.assert_not_called()
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
