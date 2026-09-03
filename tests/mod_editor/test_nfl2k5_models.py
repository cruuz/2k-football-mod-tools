"""Models export/import core: codecs, glTF reading, fitting, and (when the private extraction exists) real scenes."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mod_editor.core import nfl2k5_models as M  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
PACK0 = EXTRACTION / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"
INVENTORY = REPO / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
HAVE_DISC = PACK0.is_file() and INVENTORY.is_file()


class CodecTests(unittest.TestCase):
    def test_normshort_round_trips_every_value(self) -> None:
        for value in (-32768, -32767, -1, 0, 1, 12345, 32767):
            self.assertEqual(M.encode_normshort(M.normshort(value)), value)

    def test_normpacked3_round_trips_unit_vectors(self) -> None:
        for vector in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.577, 0.577, -0.577), (-0.3, 0.9, 0.31)):
            word = M.encode_normpacked3(*vector)
            back = M.decode_normpacked3(word)
            for a in range(3):
                self.assertAlmostEqual(back[a], vector[a], delta=2.5e-3)
            self.assertEqual(M.encode_normpacked3(*back), word)

    def test_uv_mapping_is_its_own_inverse(self) -> None:
        for raw in ((0, 0), (32767, 32767), (-32768, -32768), (1234, -4321)):
            u, v = M.uv_to_gltf(*raw)
            self.assertTrue(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0)
            back = M.uv_from_gltf(u, v)
            self.assertEqual(back, raw)

    def test_prefix_decoder_agrees_with_the_full_decoder(self) -> None:
        import nfl_txtr as t
        payload = (b"SCNE" * 40 + bytes(range(256)) * 3 + b"the name lives early" * 10)
        stream, _info = t.compress_vc_lz(payload, stream_tag=3, offset_bits=12)
        for limit in (1, 17, 200, 512, len(payload), len(payload) + 100):
            self.assertEqual(M.decode_vc_lz_prefix(stream, limit), payload[:limit])


class CatalogTests(unittest.TestCase):
    def test_keys_round_trip(self) -> None:
        self.assertEqual(M.parse_model_key(M.model_key(3, 114)), (3, 114))
        with self.assertRaises(M.ModelsError):
            M.parse_model_key("stadium")

    def test_group_rules_name_the_obvious_models(self) -> None:
        self.assertEqual(M.group_for_name("hi_body"), "players")
        self.assertEqual(M.group_for_name("fullsize_helmet"), "helmets")
        self.assertEqual(M.group_for_name("referee"), "officials")
        self.assertEqual(M.group_for_name("cheerleader"), "crowd")
        self.assertEqual(M.group_for_name("stadium"), "stadiums")
        self.assertEqual(M.group_for_name("HI_TOM_BRADY"), "trophies")
        self.assertEqual(M.group_for_name("jukebox"), "crib")
        self.assertEqual(M.group_for_name("main_menu"), "menus")
        self.assertEqual(M.group_for_name("glowball"), "other")
        for group in M.GROUP_ORDER:
            self.assertIn(group, M.GROUP_LABELS)


def _tiny_gltf(directory: Path, *, glb: bool, skinned: bool, positions_metres: list[tuple[float, float, float]],
               indices_lane: bool = True) -> Path:
    """A minimal glTF/GLB with one triangle mesh under a 0.01-scaled root (the export layout)."""
    binary = bytearray()
    views = []
    accessors = []

    def add(payload: bytes, count: int, kind: str, component: int, target: int | None) -> int:
        while len(binary) % 4:
            binary.append(0)
        view = {"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        binary.extend(payload)
        views.append(view)
        accessors.append({"bufferView": len(views) - 1, "componentType": component, "count": count, "type": kind})
        return len(accessors) - 1

    flat = [c for p in positions_metres for c in p]
    attributes = {"POSITION": add(struct.pack(f"<{len(flat)}f", *flat), len(positions_metres), "VEC3", 5126, 34962)}
    if indices_lane:
        attributes[M.VERTEX_INDEX_ATTRIBUTE] = add(struct.pack(f"<{len(positions_metres)}f", *range(len(positions_metres))),
                                                   len(positions_metres), "SCALAR", 5126, 34962)
    if skinned:
        attributes["JOINTS_0"] = add(struct.pack("<" + "4H" * len(positions_metres), *([0, 0, 0, 0] * len(positions_metres))),
                                     len(positions_metres), "VEC4", 5123, 34962)
        attributes["WEIGHTS_0"] = add(struct.pack("<" + "4f" * len(positions_metres), *([1, 0, 0, 0] * len(positions_metres))),
                                      len(positions_metres), "VEC4", 5126, 34962)
    tri = add(struct.pack("<3H", 0, 1, 2), 3, "SCALAR", 5123, 34963)
    nodes = [{"name": "tri_mesh", "mesh": 0}]
    document = {"asset": {"version": "2.0"}, "scene": 0, "meshes": [{"name": "tri", "primitives": [{"attributes": attributes, "indices": tri, "mode": 4}]}],
                "accessors": accessors, "bufferViews": views}
    if skinned:
        ibm = add(struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -0.5, -0.25, 0, 1), 1, "MAT4", 5126, None)
        nodes.append({"name": "joint", "translation": [0.5, 0.25, 0.0]})
        nodes[0]["skin"] = 0
        document["skins"] = [{"joints": [1], "inverseBindMatrices": ibm, "skeleton": 1}]
        root_children = [0, 1]
    else:
        root_children = [0]
    nodes.append({"name": "root", "scale": [0.01, 0.01, 0.01], "children": root_children})
    document["nodes"] = nodes
    document["scenes"] = [{"nodes": [len(nodes) - 1]}]
    if glb:
        payload = json.dumps(document).encode("utf-8")
        payload += b" " * (-len(payload) % 4)
        bin_chunk = bytes(binary) + bytes(-len(binary) % 4)
        document["buffers"] = [{"byteLength": len(binary)}]
        payload = json.dumps(document).encode("utf-8"); payload += b" " * (-len(payload) % 4)
        total = 12 + 8 + len(payload) + 8 + len(bin_chunk)
        blob = struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(payload), 0x4E4F534A) + payload \
            + struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
        path = directory / "tiny.glb"
        path.write_bytes(blob)
        return path
    document["buffers"] = [{"uri": "tiny.bin", "byteLength": len(binary)}]
    (directory / "tiny.bin").write_bytes(bytes(binary))
    path = directory / "tiny.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class GltfReadingTests(unittest.TestCase):
    def test_gltf_and_glb_positions_come_back_in_centimetres(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for glb in (False, True):
                path = _tiny_gltf(Path(tmp), glb=glb, skinned=False,
                                  positions_metres=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)])
                meshes = M.read_edited_meshes(M.GltfFile(path))
                self.assertEqual(len(meshes), 1)
                # node-local metres x root 0.01 = world metres; / 0.01 = the game's centimetres
                self.assertEqual([tuple(round(c, 6) for c in p) for p in meshes[0].positions],
                                 [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)])
                self.assertEqual(meshes[0].source_indices, [0, 1, 2])

    def test_skinned_mesh_ignores_its_node_and_uses_bind_space(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _tiny_gltf(Path(tmp), glb=True, skinned=True,
                              positions_metres=[(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.2, 0.0)])
            meshes = M.read_edited_meshes(M.GltfFile(path))
            # joint world = root(0.01) * T(0.5, 0.25, 0); inverse bind = T(-0.5, -0.25, 0):
            # world = 0.01 * (p + (0.5,0.25,0) - (0.5,0.25,0)) = 0.01 p  ->  /0.01 = p in "metres" = game cm numbers
            got = [tuple(round(c, 5) for c in p) for p in meshes[0].positions]
            self.assertEqual(got, [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.2, 0.0)])

    def test_nearest_map_finds_the_closest_target(self) -> None:
        targets = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (100.0, 100.0, 100.0)]
        sources = [(0.4, 0.1, 0.0), (9.0, 0.5, 0.0), (0.0, 12.0, 1.0), (99.0, 101.0, 100.0)]
        self.assertEqual(M._nearest_map(sources, targets), [0, 1, 2, 3])


@unittest.skipUnless(HAVE_DISC, "private retail extraction is absent")
class RealSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = M.ModelSource(PACK0, INVENTORY)

    def test_catalog_names_every_scene(self) -> None:
        entries = self.source.catalog()
        self.assertEqual(len(entries), 4616)
        names = {e.name for e in entries}
        for expected in ("hi_body", "hi_head", "referee", "fullsize_helmet", "stadium", "cheerleader"):
            self.assertIn(expected, names)
        self.assertFalse(any(e.name.startswith("scene_") for e in entries))

    def test_export_referee_has_skin_uvs_normals_textures_and_index_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = M.export_model(self.source, "o346c109", Path(tmp) / "referee.gltf")
            document = json.loads(result.gltf_path.read_text(encoding="utf-8"))
            self.assertEqual(len(document["skins"]), 2)
            self.assertEqual(len(document["skins"][0]["joints"]), 25)
            attributes = document["meshes"][0]["primitives"][0]["attributes"]
            for key in ("POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0", M.VERTEX_INDEX_ATTRIBUTE):
                self.assertIn(key, attributes)
            self.assertEqual(len(document["images"]), 2)
            self.assertTrue(result.readme_path.is_file())
            accessor = document["accessors"][attributes["TEXCOORD_0"]]
            self.assertEqual(accessor["count"], 1451)

    def test_import_round_trip_moves_only_what_moved_and_fits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = M.export_model(self.source, "o346c109", Path(tmp) / "referee.gltf")
            document = json.loads(result.gltf_path.read_text(encoding="utf-8"))
            blob = bytearray(result.bin_path.read_bytes())
            accessor = document["accessors"][document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
            view = document["bufferViews"][accessor["bufferView"]]
            moved = 0
            for i in range(accessor["count"]):
                at = view["byteOffset"] + i * 12
                x, y, z = struct.unpack_from("<3f", blob, at)
                if y > 60.0:
                    struct.pack_into("<3f", blob, at, x, y + 2.0, z)
                    moved += 1
            result.bin_path.write_bytes(bytes(blob))
            compiled = M.compile_import(self.source, "o346c109", result.gltf_path)
            self.assertEqual(compiled.shapes[0].positions_changed, moved)
            self.assertEqual(compiled.shapes[1].positions_changed, 0)
            self.assertIn("vertex index lane", compiled.shapes[0].matched_by)
            self.assertAlmostEqual(compiled.shapes[0].max_move_cm, 2.0, places=2)
            self.assertEqual(len(compiled.rebuilt_span), len(self.source.span(self.source.resource("o346c109"))))
            self.assertEqual(compiled.rebuilt_span[:0x20], self.source.span(self.source.resource("o346c109"))[:0x20])

    def test_an_unchanged_export_is_refused_rather_than_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = M.export_model(self.source, "o4248c94", Path(tmp) / "case.gltf")
            with self.assertRaisesRegex(M.ModelsError, "does not change"):
                M.compile_import(self.source, "o4248c94", result.gltf_path)


if __name__ == "__main__":
    unittest.main()
