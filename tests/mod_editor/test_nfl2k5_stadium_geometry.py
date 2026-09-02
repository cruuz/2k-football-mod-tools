"""Retail-free tests for bounded Stadium glTF position import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import tempfile
import unittest

from mod_editor.core.nfl2k5_stadium_studio import StadiumGeometryTarget
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    GEOMETRY_CATALOG_SCHEMA,
    TARGET_SCENE_ID,
    StadiumTextureWriterError,
    compile_stadium_geometry_recipe,
)


def _write_gltf(
    root: Path,
    name: str,
    positions: tuple[tuple[float, float, float], ...],
    indices: tuple[int, ...] = (0, 1, 2),
) -> Path:
    binary = b"".join(struct.pack("<3f", *row) for row in positions)
    index_offset = len(binary)
    binary += b"".join(struct.pack("<H", value) for value in indices)
    bin_path = root / f"{name}.bin"
    bin_path.write_bytes(binary)
    document = {
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(positions),
                "type": "VEC3",
            },
            {
                "bufferView": 1,
                "componentType": 5123,
                "count": len(indices),
                "type": "SCALAR",
            },
        ],
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary), "uri": bin_path.name}],
        "bufferViews": [
            {"buffer": 0, "byteLength": index_offset, "byteOffset": 0},
            {
                "buffer": 0,
                "byteLength": len(indices) * 2,
                "byteOffset": index_offset,
            },
        ],
        "meshes": [{
            "extras": {"source_shape_index": 7},
            "name": "roof",
            "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}],
        }],
    }
    path = root / f"{name}.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class StadiumGeometryRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="stadium-geometry-")
        self.root = Path(self.temporary.name)
        self.before = (
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        )
        self.source = _write_gltf(self.root, "source", self.before)
        target = StadiumGeometryTarget(
            "stadium-shape-7", 7, "roof", 3,
            "catalog-same-count-position-v2", False,
        )
        self.scene = SimpleNamespace(
            scene_id=TARGET_SCENE_ID,
            gltf_path=self.source,
            geometry_targets=(target,),
        )
        source_bytes = b"".join(struct.pack("<3f", *row) for row in self.before)
        catalog = {
            "schema": GEOMETRY_CATALOG_SCHEMA,
            "targets": [{
                "eligibility": {"mechanically_rigid_same_count_float3": True},
                "position": {
                    "contiguous_decoded_span": {
                        "offset": 0,
                        "size": len(source_bytes),
                        "end_offset": len(source_bytes),
                        "sha256": hashlib.sha256(source_bytes).hexdigest(),
                    },
                },
                "shape": {"index": 7, "name": "roof", "vertex_count": 3},
                "source_identity": {
                    "outer_index": 3280,
                    "chunk_index": 5,
                    "scene_index": 2648,
                },
                "target_id": "stadium-shape-7",
            }],
        }
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps(catalog), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_compiles_only_changed_positions_and_records_preservation(self) -> None:
        edited = _write_gltf(
            self.root,
            "edited",
            (self.before[0], (1.25, 0.0, 0.0), self.before[2]),
        )
        compiled = compile_stadium_geometry_recipe(
            self.scene,
            edited,
            catalog_path=self.catalog,
            enforce_catalog_pin=False,
        )
        self.assertEqual(compiled.changed_target_count, 1)
        self.assertEqual(compiled.changed_vertex_count, 1)
        self.assertEqual(compiled.preserved_triangle_count, 1)
        recipe = json.loads(compiled.recipe)
        self.assertEqual(recipe["preservation"], {
            "collision": "unchanged game bytes",
            "materials": "unchanged game bytes",
            "topology": "validated equivalent before import",
            "uvs": "unchanged game bytes",
        })
        self.assertEqual(recipe["edits"][0]["positions"][1], [1.25, 0.0, 0.0])

    def test_rejects_changed_faces_before_staging(self) -> None:
        edited = _write_gltf(
            self.root,
            "changed-topology",
            self.before,
            indices=(0, 1, 1),
        )
        with self.assertRaisesRegex(StadiumTextureWriterError, "topology changed"):
            compile_stadium_geometry_recipe(
                self.scene,
                edited,
                catalog_path=self.catalog,
                enforce_catalog_pin=False,
            )


if __name__ == "__main__":
    unittest.main()
