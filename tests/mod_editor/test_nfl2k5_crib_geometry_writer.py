"""Bounded Crib position-only model export/import tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from mod_editor.core.nfl2k5_crib_geometry_writer import (
    CATALOG_PATH,
    CribGeometryWriterError,
    build_unified_crib_geometry_import,
    compile_crib_geometry_recipe,
    export_crib_scene_gltf,
    list_editable_scenes,
)


ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "assets/intermediate/nfl2k5/models"
PRIVATE_ROOT = Path(
    "/home/noah/.cache/2k5-mod-studio/"
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
PHONE_SCENE = "nfl2k5.crib.o4248.c0105.scene4218"


def _edited_copy(
    source: Path,
    root: Path,
    *,
    change_topology: bool = False,
    duplicate_second_position: bool = False,
    flatten_positions: bool = False,
) -> Path:
    document = json.loads(source.read_text(encoding="utf-8"))
    uri = document["buffers"][0]["uri"]
    source_bin = source.parent / uri
    output = root / source.name
    output_bin = root / uri
    root.mkdir(parents=True, exist_ok=True)
    payload = bytearray(source_bin.read_bytes())
    phone = next(
        mesh for mesh in document["meshes"]
        if mesh.get("extras", {}).get("source_shape_index") == 0
    )
    primitive = phone["primitives"][0]
    if change_topology:
        accessor = document["accessors"][primitive["indices"]]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        component = int(accessor["componentType"])
        code = {5121: "B", 5123: "H", 5125: "I"}[component]
        first = struct.unpack_from("<" + code, payload, offset)[0]
        struct.pack_into("<" + code, payload, offset, first + 1)
    else:
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        if flatten_positions:
            count = int(accessor["count"])
            first = bytes(payload[offset:offset + 12])
            for vertex in range(1, count):
                payload[offset + vertex * 12:offset + (vertex + 1) * 12] = first
        elif duplicate_second_position:
            payload[offset:offset + 12] = payload[offset + 12:offset + 24]
        else:
            x = struct.unpack_from("<f", payload, offset)[0]
            struct.pack_into("<f", payload, offset, x + 0.01)
    output.write_text(json.dumps(document), encoding="utf-8")
    output_bin.write_bytes(payload)
    return output


class CribGeometryCatalogTests(unittest.TestCase):
    def test_ten_owned_meshes_cover_seven_scenes_and_two_proved_formats(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(catalog["targets"]), 10)
        self.assertEqual(len(list_editable_scenes()), 7)
        self.assertEqual(
            {row["decode"]["format"] for row in catalog["targets"]},
            {"FLOAT3", "NORMSHORT3"},
        )
        self.assertTrue(catalog["claims"]["source_topology_uv_material_collision_preserved"])
        self.assertFalse(catalog["claims"]["contains_retail_bytes"])

    def test_recipe_retains_only_changed_vertices_not_stock_model_bytes(self) -> None:
        source = MODELS / "4248_0105_phone.gltf"
        with tempfile.TemporaryDirectory(prefix="crib-geometry-recipe-") as raw:
            edited = _edited_copy(source, Path(raw))
            compiled = compile_crib_geometry_recipe(PHONE_SCENE, source, edited)
        self.assertEqual(compiled.changed_target_count, 1)
        self.assertEqual(compiled.changed_vertex_count, 1)
        recipe = json.loads(compiled.recipe)
        self.assertEqual(len(recipe["edits"][0]["changes"]), 1)
        self.assertNotIn("positions", recipe["edits"][0])
        self.assertEqual(
            recipe["preservation"]["normals_and_other_vertex_registers"],
            "unchanged game bytes",
        )

    def test_changed_topology_is_refused_before_staging(self) -> None:
        source = MODELS / "4248_0105_phone.gltf"
        with tempfile.TemporaryDirectory(prefix="crib-geometry-topology-") as raw:
            edited = _edited_copy(source, Path(raw), change_topology=True)
            with self.assertRaisesRegex(CribGeometryWriterError, "topology changed"):
                compile_crib_geometry_recipe(PHONE_SCENE, source, edited)


class CribGeometryPrivateSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = PRIVATE_ROOT / "indexes/nfl2k5_resource_chunks_v2.json"
        cls.packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))

    def setUp(self) -> None:
        if not self.inventory.is_file() or len(self.packs) != 1:
            self.skipTest("private indexed NFL 2K5 source is unavailable")

    def test_private_export_compile_and_fixed_span_rebuild(self) -> None:
        with tempfile.TemporaryDirectory(prefix="crib-geometry-private-") as raw:
            root = Path(raw)
            source_dir = root / "source"
            source_dir.mkdir()
            source, binary = export_crib_scene_gltf(
                self.packs[0], self.inventory, PHONE_SCENE, source_dir / "phone.gltf"
            )
            self.assertTrue(source.is_file())
            self.assertTrue(binary.is_file())
            exported = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(
                exported["extras"]["nfl2k5_unit_contract"]["scale"], 0.01
            )
            # Reusing an adjacent source value is intentionally friendly to
            # the scene's extremely tight fixed lossless-compression budget.
            edited = _edited_copy(source, root / "edited", flatten_positions=True)
            compiled = compile_crib_geometry_recipe(PHONE_SCENE, source, edited)
            recipe = root / "phone.geometry.json"
            recipe.write_bytes(compiled.recipe)
            replacement, previews, report, selector, target = (
                build_unified_crib_geometry_import(
                    self.packs[0], self.inventory, recipe
                )
            )
        self.assertFalse(previews)
        self.assertEqual(len(replacement), target["span_size"])
        self.assertEqual(selector, f"{PHONE_SCENE}.geometry")
        self.assertGreater(report["replacement"]["changed_vertex_count"], 1)
        self.assertTrue(report["claims"]["same_count_position_components_only"])
        self.assertFalse(report["claims"]["arbitrary_model_replacement"])


if __name__ == "__main__":
    unittest.main()
