"""Retail-free tests for the dependency-free Stadium Studio glTF parser."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.gui.stadium_viewer import GltfWireframeModel, _view_coordinates


class StadiumViewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="stadium-viewer-")
        self.root = Path(self.temporary.name)
        positions = (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
        )
        payload = b"".join(struct.pack("<3f", *row) for row in positions)
        payload += struct.pack("<4H", 0, 1, 2, 3)
        self.binary = self.root / "scene.bin"
        self.binary.write_bytes(payload)
        self.gltf = self.root / "scene.gltf"
        self.gltf.write_text(json.dumps({
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(payload), "uri": "scene.bin"}],
            "bufferViews": [
                {"buffer": 0, "byteLength": 48, "byteOffset": 0},
                {"buffer": 0, "byteLength": 8, "byteOffset": 48},
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "byteOffset": 0,
                    "componentType": 5126,
                    "count": 4,
                    "type": "VEC3",
                },
                {
                    "bufferView": 1,
                    "byteOffset": 0,
                    "componentType": 5123,
                    "count": 4,
                    "type": "SCALAR",
                },
            ],
            "meshes": [{
                "name": "Stands / mesh 4",
                "extras": {
                    "apf_scene_node_index": 7,
                    "apf_source_mesh_index": 4,
                },
                "primitives": [{
                    "attributes": {"POSITION": 0},
                    "indices": 1,
                    "mode": 5,
                }],
            }],
            "nodes": [{
                "mesh": 0,
                "name": "Stands",
                "translation": [10, 20, 30],
                "extras": {"apf_scene_node_index": 7},
            }],
            "scene": 0,
            "scenes": [{"nodes": [0]}],
        }, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_triangle_strip_transform_bounds_and_surface_identity(self) -> None:
        model = GltfWireframeModel.load(self.gltf, self.binary)
        self.assertEqual(model.source_triangle_count, 2)
        self.assertEqual(len(model.triangles), 2)
        self.assertEqual(model.mesh_count, 1)
        self.assertEqual(model.center, (10.5, 20.5, 30.0))
        self.assertEqual(model.radius, 0.5)
        self.assertEqual(
            {(row.mesh_index, row.primitive_index) for row in model.triangles},
            {(0, 0)},
        )
        identity = model.surface_identity(0, 0)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.mesh_name, "Stands / mesh 4")
        self.assertEqual(identity.gltf_node_indices, (0,))
        self.assertEqual(identity.node_names, ("Stands",))
        self.assertEqual(identity.apf_scene_node_indices, (7,))
        self.assertEqual(identity.apf_source_mesh_index, 4)
        self.assertIsNone(identity.material_index)
        self.assertIsNone(model.surface_identity(9, 9))

    def test_binary_identity_and_preview_limit_fail_closed(self) -> None:
        changed = json.loads(self.gltf.read_text(encoding="utf-8"))
        changed["buffers"][0]["byteLength"] += 1
        self.gltf.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "binary identity"):
            GltfWireframeModel.load(self.gltf, self.binary)
        with self.assertRaisesRegex(ValidationError, "triangle limit"):
            GltfWireframeModel.load(
                self.gltf, self.binary, maximum_triangles=99
            )

    def test_camera_orbit_preserves_y_up_stadium_axis(self) -> None:
        center = (10.0, 20.0, 30.0)
        radius = 10.0
        # With no orbit, field-plane X/Z stay horizontal/depth and source Y is
        # the vertical screen axis.  This guards the axis mix-up that made a
        # real stadium appear as a tiny fragmented knot.
        self.assertEqual(
            _view_coordinates((20.0, 30.0, 40.0), center, radius, 0.0, 0.0),
            (1.0, 1.0, 1.0),
        )
        rotated = _view_coordinates(
            (20.0, 30.0, 40.0), center, radius, 3.141592653589793 / 2, 0.0
        )
        self.assertAlmostEqual(rotated[0], -1.0)
        self.assertAlmostEqual(rotated[1], 1.0)
        self.assertAlmostEqual(rotated[2], 1.0)


if __name__ == "__main__":
    unittest.main()
