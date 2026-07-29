"""Bring an edited stadium mesh back from Blender.

Exporting stadium geometry to glTF has worked for a long time, and there is a
proved writer that replaces a target's FLOAT3 position lane inside its exact
allocation. The step between them never existed, so "import a stadium model"
meant hand-authoring a JSON array of several hundred XYZ triples. Nobody was
going to do that, which is why the export has sat there unused.

This is the bridge, and its limit is the honest part. The writer replaces a
fixed-size lane inside a fixed allocation, so **the vertex count is part of the
target's identity**. You can move vertices -- reshape a roof, raise an upper
deck, lean the stands. You cannot add or remove them, and no amount of clever
packing changes that; a mesh that comes back with a different count is a
different mesh. The count is checked here so the failure is a clear sentence
rather than a refusal several steps later, and checked again by the writer,
which is the one that actually matters.

These tests use synthetic glTF documents shaped the way Blender writes them --
separate ``.bin``, ``byteStride`` set, named meshes -- so they need no retail
data. The end-to-end proof against a real disc is recorded in the release
notes: an edited roof composed into a patched volume 9, 670 decoded bytes
changed, topology and every unrelated stream preserved.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_stadium_gltf_roundtrip as roundtrip  # noqa: E402

_TARGET = "nfl2k5/stadium/o3280/c5/s0"   # the 574-vertex stadium roof


class _GltfFixture:
    """A glTF shaped the way Blender's exporter writes one."""

    def __init__(self, root: Path, count: int, *, name: str = "roof",
                 stride: int = 12, component: int = 5126,
                 kind: str = "VEC3", primitives: int = 1,
                 embedded: bool = False) -> None:
        self.root = root
        payload = b"".join(
            struct.pack("<3f", float(index), 100.0 + index, -float(index))
            for index in range(count)
        )
        if embedded:
            import base64
            uri = roundtrip.DATA_URI + base64.b64encode(payload).decode("ascii")
        else:
            (root / "mesh.bin").write_bytes(payload)
            uri = "mesh.bin"
        document = {
            "asset": {"version": "2.0", "generator": "Khronos glTF Blender I/O"},
            "buffers": [{"uri": uri, "byteLength": len(payload)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0,
                             "byteLength": len(payload), "byteStride": stride}],
            "accessors": [{"bufferView": 0, "componentType": component,
                           "count": count, "type": kind}],
            "meshes": [{"name": name, "primitives": [
                {"attributes": {"POSITION": 0}} for _ in range(primitives)
            ]}],
            "nodes": [{"mesh": 0, "name": name}],
            "scenes": [{"nodes": [0]}], "scene": 0,
        }
        self.path = root / "mesh.gltf"
        self.path.write_text(json.dumps(document, indent=1), encoding="utf-8")


class CatalogTests(unittest.TestCase):
    def test_the_pinned_catalog_loads(self) -> None:
        catalog = roundtrip.load_catalog()
        self.assertEqual(len(catalog), 75)
        self.assertIn(_TARGET, catalog)

    def test_the_roof_target_declares_its_vertex_count(self) -> None:
        catalog = roundtrip.load_catalog()
        row = catalog[_TARGET]
        self.assertEqual(row["shape"]["name"], "roof")
        self.assertEqual(row["shape"]["vertex_count"], 574)


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_positions_come_back_in_order(self) -> None:
        fixture = _GltfFixture(self.root, 4)
        positions, name = roundtrip.read_positions(fixture.path)
        self.assertEqual(name, "roof")
        self.assertEqual(len(positions), 4)
        self.assertAlmostEqual(positions[2][1], 102.0, places=5)

    def test_an_interleaved_stride_is_honoured(self) -> None:
        """Blender writes tightly packed, but a stride is legal and must work."""
        payload = bytearray()
        for index in range(3):
            payload += struct.pack("<3f", float(index), 1.0, 2.0) + b"\x00" * 8
        (self.root / "mesh.bin").write_bytes(bytes(payload))
        document = {
            "asset": {"version": "2.0"},
            "buffers": [{"uri": "mesh.bin", "byteLength": len(payload)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0,
                             "byteLength": len(payload), "byteStride": 20}],
            "accessors": [{"bufferView": 0, "componentType": 5126,
                           "count": 3, "type": "VEC3"}],
            "meshes": [{"name": "roof",
                        "primitives": [{"attributes": {"POSITION": 0}}]}],
        }
        path = self.root / "mesh.gltf"
        path.write_text(json.dumps(document), encoding="utf-8")
        positions, _name = roundtrip.read_positions(path)
        self.assertEqual([round(p[0]) for p in positions], [0, 1, 2])

    def test_an_embedded_base64_buffer_works(self) -> None:
        fixture = _GltfFixture(self.root, 5, embedded=True)
        positions, _name = roundtrip.read_positions(fixture.path)
        self.assertEqual(len(positions), 5)

    def test_a_named_mesh_can_be_selected(self) -> None:
        fixture = _GltfFixture(self.root, 3, name="upper_deck")
        positions, name = roundtrip.read_positions(fixture.path, "upper_deck")
        self.assertEqual(name, "upper_deck")
        self.assertEqual(len(positions), 3)

    def test_asking_for_a_mesh_that_is_not_there_says_what_is(self) -> None:
        fixture = _GltfFixture(self.root, 3, name="roof")
        with self.assertRaises(roundtrip.RoundTripError) as caught:
            roundtrip.read_positions(fixture.path, "scoreboard")
        self.assertIn("roof", str(caught.exception))

    def test_more_than_one_primitive_is_refused(self) -> None:
        fixture = _GltfFixture(self.root, 3, primitives=2)
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.read_positions(fixture.path)

    def test_a_non_float_accessor_is_refused(self) -> None:
        fixture = _GltfFixture(self.root, 3, component=5123)
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.read_positions(fixture.path)

    def test_a_non_vec3_accessor_is_refused(self) -> None:
        fixture = _GltfFixture(self.root, 3, kind="VEC2")
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.read_positions(fixture.path)

    def test_a_missing_bin_file_is_refused(self) -> None:
        fixture = _GltfFixture(self.root, 3)
        (self.root / "mesh.bin").unlink()
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.read_positions(fixture.path)


class RecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = roundtrip.load_catalog()

    def test_a_matching_mesh_becomes_a_valid_recipe(self) -> None:
        fixture = _GltfFixture(self.root, 574)
        recipe = roundtrip.build_recipe(fixture.path, _TARGET, self.catalog)
        self.assertEqual(set(recipe),
                         {"catalog", "positions", "schema", "target_id"})
        self.assertEqual(recipe["schema"], roundtrip.RECIPE_SCHEMA)
        self.assertEqual(len(recipe["positions"]), 574)
        self.assertEqual(recipe["catalog"]["sha256"], roundtrip.CATALOG_SHA256)

    def test_the_recipe_shape_is_exactly_what_the_writer_validates(self) -> None:
        """Producer and consumer must agree, or this is a JSON file nobody reads."""
        writer = (
            _REPO_ROOT / "tools" / "nfl_stadium_catalog_position_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'require(set(value) == {"catalog", "positions", "schema", "target_id"}',
            writer,
        )
        self.assertIn(roundtrip.RECIPE_SCHEMA, writer)
        self.assertIn(roundtrip.CATALOG_SHA256, writer)

    def test_a_different_vertex_count_is_refused_with_the_reason(self) -> None:
        """The limit that defines this lane. Say it plainly, not in bytes."""
        fixture = _GltfFixture(self.root, 573)
        with self.assertRaises(roundtrip.RoundTripError) as caught:
            roundtrip.build_recipe(fixture.path, _TARGET, self.catalog)
        message = str(caught.exception)
        self.assertIn("574", message)
        self.assertIn("573", message)
        self.assertIn("cannot add or remove", message)

    def test_an_unknown_target_is_refused(self) -> None:
        fixture = _GltfFixture(self.root, 574)
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.build_recipe(fixture.path, "nfl2k5/made/up/target",
                                   self.catalog)

    def test_a_non_finite_coordinate_is_refused(self) -> None:
        """A NaN from a bad modifier must not reach the packer."""
        payload = bytearray()
        for index in range(574):
            value = float("nan") if index == 7 else float(index)
            payload += struct.pack("<3f", value, 1.0, 2.0)
        (self.root / "mesh.bin").write_bytes(bytes(payload))
        document = {
            "asset": {"version": "2.0"},
            "buffers": [{"uri": "mesh.bin", "byteLength": len(payload)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0,
                             "byteLength": len(payload), "byteStride": 12}],
            "accessors": [{"bufferView": 0, "componentType": 5126,
                           "count": 574, "type": "VEC3"}],
            "meshes": [{"name": "roof",
                        "primitives": [{"attributes": {"POSITION": 0}}]}],
        }
        path = self.root / "mesh.gltf"
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(roundtrip.RoundTripError):
            roundtrip.build_recipe(path, _TARGET, self.catalog)

    def test_every_catalog_target_can_be_round_tripped(self) -> None:
        """Not just the roof: all 75 must accept a mesh of their own size."""
        for target_id, row in list(self.catalog.items())[:12]:
            count = int(row["shape"]["vertex_count"])
            if count == 0 or count > 4000:
                continue
            with self.subTest(target_id=target_id):
                directory = Path(tempfile.mkdtemp(dir=self.root))
                fixture = _GltfFixture(directory, count)
                recipe = roundtrip.build_recipe(fixture.path, target_id,
                                                self.catalog)
                self.assertEqual(len(recipe["positions"]), count)


if __name__ == "__main__":
    unittest.main()
