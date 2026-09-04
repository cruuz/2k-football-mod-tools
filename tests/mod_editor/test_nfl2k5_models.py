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

    # Per-shape UV constants seen on the disc: the unit case, the referee, a 12x tiled seat row.
    UV_CONSTANTS = (((0.501, 0.501), (0.5, 0.5)), ((0.808, 1.241), (0.549, 0.175)),
                    ((12.04, 1.63), (0.5, -1.1255)), ((15.03, 10.02), (0.5, 0.5)))

    def test_uv_mapping_is_its_own_inverse_under_every_shape_constant(self) -> None:
        for scale, offset in self.UV_CONSTANTS:
            for raw in ((0, 0), (32767, 32767), (-32768, -32768), (1234, -4321), (-32702, 32702)):
                u, v = M.uv_to_gltf(*raw, scale, offset)
                self.assertEqual(M.uv_from_gltf(u, v, scale, offset), raw, (scale, offset, raw))
            # and through a binary32 file, as the exporter writes it
            for raw in ((32767, -32768), (-1, 1), (12345, -12345)):
                u, v = struct.unpack("<2f", struct.pack("<2f", *M.uv_to_gltf(*raw, scale, offset)))
                self.assertEqual(M.uv_from_gltf(u, v, scale, offset), raw)

    def test_uv_transform_follows_the_shader_rule_with_no_v_flip(self) -> None:
        # oT0.xy = v6.xy * c[-89].xy + c[-89].zw; c[-89] = (Su, Sv, Ou, Ov) at shape +0x30
        self.assertEqual(M.uv_to_gltf(32767, -32768, (2.0, 3.0), (0.5, -1.0)), (2.5, -4.0))
        self.assertEqual(M.uv_to_gltf(0, 0, (12.04, 1.63), (0.5, -1.1255)), (0.5, -1.1255))
        low = M.uv_to_gltf(0, -16384, (1.0, 1.0), (0.0, 0.0))
        high = M.uv_to_gltf(0, 16384, (1.0, 1.0), (0.0, 0.0))
        self.assertLess(low[1], high[1])                 # a larger lane value is a larger v: no flip
        self.assertEqual(M.uv_from_gltf(99.0, -99.0, (1.0, 1.0), (0.0, 0.0)), (32767, -32768))   # clamped
        self.assertEqual(M.uv_from_gltf(0.5, 0.5, (0.0, 0.0), (0.5, 0.5)), (0, 0))               # degenerate S
        self.assertTrue(M.uv_in_range(1.0 + 0.4 / 32767.0, 1.0, 0.0))
        self.assertFalse(M.uv_in_range(1.0 + 0.6 / 32767.0, 1.0, 0.0))

    def test_fit_uv_range_widens_only_the_axis_that_needs_it(self) -> None:
        scale, offset = (0.808, 1.241), (0.549, 0.175)
        inside = [(offset[0] + scale[0] * n, offset[1] + scale[1] * m) for n, m in ((-1.0, 1.0), (0.0, 0.0), (0.998, -0.998))]
        self.assertEqual(M.fit_uv_range(inside, scale, offset), (scale, offset, (False, False)))
        edited = inside + [(offset[0] + 1.5 * scale[0], 0.0)]         # u leaves the range, v does not
        new_scale, new_offset, widened = M.fit_uv_range(edited, scale, offset)
        self.assertEqual(widened, (True, False))
        self.assertEqual((new_scale[1], new_offset[1]), (scale[1], offset[1]))   # V constant byte-identical
        us = [uv[0] for uv in edited]
        self.assertAlmostEqual(new_offset[0], (min(us) + max(us)) / 2.0, places=5)
        self.assertAlmostEqual(new_scale[0], (max(us) - min(us)) / 2.0 * 1.001, places=5)
        for uv in edited:
            self.assertTrue(M.uv_in_range(uv[0], new_scale[0], new_offset[0]))
            back = M.uv_to_gltf(*M.uv_from_gltf(uv[0], uv[1], new_scale, new_offset), new_scale, new_offset)
            self.assertAlmostEqual(back[0], uv[0], delta=new_scale[0] / 32767.0)
        # binary32, as the record stores it
        self.assertEqual(struct.unpack("<f", struct.pack("<f", new_scale[0]))[0], new_scale[0])
        # both axes at once, including a degenerate (single-valued) one
        _s, _o, both = M.fit_uv_range([(50.0, 50.0), (60.0, 50.0)], (1.0, 1.0), (0.0, 0.0))
        self.assertEqual(both, (True, True))
        self.assertGreater(_s[1], 0.0)

    def test_d3dcolor_round_trips(self) -> None:
        for word in (0x00000000, 0xFFFFFFFF, 0xFF102030, 0x80FF0000, 0x0000FF00, 0x000000FF):
            self.assertEqual(M.rgba_to_d3dcolor(*M.d3dcolor_to_rgba(word)), word)
        self.assertEqual(M.d3dcolor_to_rgba(0xAABBCCDD), (0xBB, 0xCC, 0xDD, 0xAA))
        self.assertEqual(M.rgba_to_d3dcolor(255.0, 0.0, 0.0, 255.0), 0xFFFF0000)
        self.assertEqual(M.rgba_to_d3dcolor(300, -5, 127.5, 255), 0xFFFF0080)   # clamped and rounded

    def test_stadium_studio_contract_ids(self) -> None:
        scene_id = M.scene_contract_id("stadium", 3610, 4, 4175)
        self.assertEqual(scene_id, "nfl2k5.stadium.o3610.c0004.scene4175")
        self.assertEqual(M.texture_contract_id(scene_id, 2), "nfl2k5.stadium.o3610.c0004.scene4175.texture0002")
        self.assertEqual(M.scene_contract_id("referee", 346, 109, 99), "nfl2k5.referee.o0346.c0109.scene0099")
        self.assertEqual(M.scene_contract_id("odd name/here", 1, 2, 3), "nfl2k5.odd_name_here.o0001.c0002.scene0003")
        self.assertEqual(M.GLTF_TEXTURE_ID_KEY, "nfl2k5_texture_id")
        from mod_editor.core import nfl2k5_stadium_studio as studio
        self.assertIs(studio.GLTF_TEXTURE_ID_KEY, M.GLTF_TEXTURE_ID_KEY)
        self.assertEqual(studio._scene_id(3610, 4, 4175), scene_id)
        self.assertEqual(studio._texture_id(scene_id, 2), M.texture_contract_id(scene_id, 2))

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
               indices_lane: bool = True, colours: list[tuple[float, float, float, float]] | None = None) -> Path:
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
    if colours is not None:
        flat_c = [c for rgba in colours for c in rgba]
        attributes[M.COLOUR_ATTRIBUTE] = add(struct.pack(f"<{len(flat_c)}f", *flat_c), len(colours), "VEC4", 5126, 34962)
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

    def test_the_colour_lane_is_read_from_nfl_color_only(self) -> None:
        colours = [(1.0, 0.0, 0.0, 1.0), (0.0, 0.5, 0.0, 1.0), (0.25, 0.5, 0.75, 0.125)]   # binary32-exact
        with tempfile.TemporaryDirectory() as tmp:
            path = _tiny_gltf(Path(tmp), glb=False, skinned=False,
                              positions_metres=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)], colours=colours)
            mesh = M.read_edited_meshes(M.GltfFile(path))[0]
            self.assertEqual(mesh.colours, colours)
            path = _tiny_gltf(Path(tmp), glb=True, skinned=False, positions_metres=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0)])
            self.assertIsNone(M.read_edited_meshes(M.GltfFile(path))[0].colours)

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

    # -- the per-shape UV rule and the Stadium Studio contract ---------------------------------
    STADIUM = "o3611c4"            # the smallest stadium scene: 67 shapes, 16,104 vertices, 44 textures
    REFEREE = "o346c109"

    def _inventory_scene_index(self, resource: object) -> int:
        """The Stadiums page's scene_index, computed the way its cache worker does: enumerate the SCNE resources."""
        import nfl_scene_probe as probe
        _document, resources = probe.parse_inventory(INVENTORY)
        scne = [r for r in resources if r.kind == "SCNE"]
        return next(i for i, r in enumerate(scne) if (r.outer_index, r.chunk_index) == (resource.outer_index, resource.chunk_index))

    def test_export_uvs_follow_each_shapes_constant_and_carry_the_contract(self) -> None:
        for key, scene_name in ((self.STADIUM, "stadium"), (self.REFEREE, "referee")):
            with tempfile.TemporaryDirectory() as tmp:
                result = M.export_model(self.source, key, Path(tmp) / f"{key}.gltf")
                document = json.loads(result.gltf_path.read_text(encoding="utf-8"))
                blob = result.bin_path.read_bytes()
                resource, decoded, scene = self.source.parse(key)
                shapes = {int(s["index"]): s for s in scene["shapes"]}
                self.assertEqual(str(scene["name"]), scene_name)
                scene_id = (f"nfl2k5.{scene_name}.o{resource.outer_index:04d}.c{resource.chunk_index:04d}."
                            f"scene{self._inventory_scene_index(resource):04d}")
                # -- file-level contract
                self.assertEqual(document["extras"]["nfl2k5_scene_id"], scene_id)
                self.assertEqual(document["asset"]["extras"]["schema"], "nfl2k5_model_export/v2")
                self.assertEqual(document["nodes"][-1]["name"], "nfl2k5_units_centimetre_to_metre")
                self.assertEqual(document["scenes"][0]["nodes"], [len(document["nodes"]) - 1])
                self.assertIs(document["extras"]["nfl2k5_unit_contract"]["buffer_rewritten"], False)
                self.assertIs(document["extras"]["nfl2k5_texcoord_contract"]["v_flip"], False)
                self.assertIs(document["extras"]["nfl2k5_vertex_colour_contract"]["color0_written"], False)
                self.assertEqual(document["extras"]["nfl2k5_texture_contract"]["embedded_image_count"], len(document["images"]))
                # -- materials / textures / images: nfl2k5_texture_id everywhere, images named by material
                names_by_texture: dict[int, list[str]] = {}
                for material in scene["materials"]:
                    if material.get("texture_index") is not None:
                        names_by_texture.setdefault(int(material["texture_index"]), []).append(str(material["name"]))
                self.assertEqual(len(document["materials"]), len(scene["materials"]))
                for index, material in enumerate(document["materials"]):
                    extras = material["extras"]
                    self.assertEqual(extras["nfl2k5_material_index"], index)
                    self.assertIn("nfl2k5_texture_id", extras)
                    binding = material["pbrMetallicRoughness"].get("baseColorTexture")
                    if binding is None:
                        self.assertIn(extras["nfl2k5_mapping_status"], ("unmapped", "mapped_embedded_texture"))
                    else:
                        self.assertEqual(extras["nfl2k5_mapping_status"], "mapped_embedded_texture")
                        self.assertEqual(binding["texCoord"], 0)
                        texture = document["textures"][binding["index"]]
                        self.assertEqual(extras["nfl2k5_texture_id"], texture["extras"]["nfl2k5_texture_id"])
                        self.assertEqual(document["images"][texture["source"]]["extras"]["nfl2k5_texture_id"],
                                         texture["extras"]["nfl2k5_texture_id"])
                self.assertEqual(len(document["images"]), len(document["textures"]))
                for image, texture in zip(document["images"], document["textures"]):
                    texture_index = image["extras"]["nfl2k5_texture_index"]
                    texture_id = f"{scene_id}.texture{texture_index:04d}"
                    self.assertEqual(image["extras"]["nfl2k5_texture_id"], texture_id)
                    self.assertEqual(image["extras"]["nfl2k5_scene_id"], scene_id)
                    self.assertEqual(texture["extras"]["nfl2k5_texture_id"], texture_id)
                    self.assertEqual(image["name"], names_by_texture[texture_index][0])
                    self.assertEqual(texture["name"], image["name"])
                    self.assertEqual(len(image["extras"]["rgba_sha256"]), 64)
                    self.assertEqual(image["extras"]["format_name"], "P8")
                    self.assertEqual(image["mimeType"], "image/png")
                if key == self.STADIUM:
                    self.assertEqual(len(document["images"]), 44)
                    self.assertIn("roof01", [image["name"] for image in document["images"]])
                # -- meshes: source_* aliases, the UV constant, TEXCOORD_0 == n * S + O, no COLOR_0
                checked = tiled = 0
                for mesh in document["meshes"]:
                    shape = shapes[mesh["extras"]["nfl2k5_shape_index"]]
                    extras = mesh["extras"]
                    self.assertEqual(extras["source_shape_index"], int(shape["index"]))
                    self.assertEqual(extras["source_record_offset"], int(shape["record_offset"]))
                    self.assertEqual(extras["vertex_attribute_descriptors"], shape["attribute_descriptors"])
                    self.assertEqual(extras["position_format"], extras["nfl2k5_position_format"])
                    for primitive in mesh["primitives"]:
                        if "indices" not in primitive:
                            continue
                        p_extras = primitive["extras"]
                        self.assertEqual(p_extras["source_material_index"], p_extras["nfl2k5_material_index"])
                        self.assertEqual(p_extras["source_submesh_index"], p_extras["nfl2k5_submesh_index"])
                        self.assertEqual(p_extras["source_material_name"], scene["materials"][p_extras["source_material_index"]]["name"])
                        self.assertNotIn("COLOR_0", primitive["attributes"])
                    attributes = mesh["primitives"][0]["attributes"]
                    lanes = M._shape_lanes(scene, shape)                  # layout only; the constant is read raw below
                    self.assertEqual(M.COLOUR_ATTRIBUTE in attributes, lanes.colour is not None)
                    if lanes.texcoord is None:
                        self.assertNotIn("TEXCOORD_0", attributes)
                        continue
                    su, sv, ou, ov = struct.unpack_from("<4f", decoded, int(shape["record_offset"]) + 0x30)
                    self.assertEqual(extras["nfl2k5_uv_scale"], [su, sv])
                    self.assertEqual(extras["nfl2k5_uv_offset"], [ou, ov])
                    self.assertEqual(extras["texcoord_decode"]["serialized_fields"], ["+0x30", "+0x34", "+0x38", "+0x3C"])
                    self.assertGreater(sv, 0.0)                                          # no V flip anywhere
                    if abs(su) > 0.6 or abs(sv) > 0.6:
                        tiled += 1
                    raw = M.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
                    accessor = document["accessors"][attributes["TEXCOORD_0"]]
                    view = document["bufferViews"][accessor["bufferView"]]
                    self.assertEqual(accessor["count"], lanes.vertex_count)
                    for i in range(0, lanes.vertex_count, max(1, lanes.vertex_count // 60)):
                        u, v = struct.unpack_from("<2f", blob, view["byteOffset"] + 8 * i)
                        self.assertAlmostEqual(u, M.normshort(raw[i][0]) * su + ou, delta=2e-5, msg=(key, lanes.name, i))
                        self.assertAlmostEqual(v, M.normshort(raw[i][1]) * sv + ov, delta=2e-5, msg=(key, lanes.name, i))
                        checked += 1
                    if lanes.colour is not None:
                        words = M.read_lane_u32(decoded, shape, lanes.colour, lanes.vertex_count)
                        accessor = document["accessors"][attributes[M.COLOUR_ATTRIBUTE]]
                        self.assertEqual((accessor["type"], accessor["componentType"]), ("VEC4", 5126))
                        view = document["bufferViews"][accessor["bufferView"]]
                        for i in range(0, lanes.vertex_count, max(1, lanes.vertex_count // 10)):
                            floats = struct.unpack_from("<4f", blob, view["byteOffset"] + 16 * i)
                            self.assertEqual(tuple(round(c * 255.0) for c in floats), M.d3dcolor_to_rgba(words[i]))
                    if lanes.name == "ref_high":
                        for got, want in zip((su, sv, ou, ov), (0.808, 1.241, 0.549, 0.175)):
                            self.assertAlmostEqual(got, want, places=3)
                self.assertGreater(checked, 100)
                if key == self.STADIUM:
                    self.assertGreaterEqual(tiled, 50)                  # 54 of the 67 shapes tile (S up to 12)
                    self.assertGreater(max(abs(m["extras"]["nfl2k5_uv_scale"][0]) for m in document["meshes"]), 5.0)
                # -- an unchanged export imports back to the original quantised lanes: nothing to write
                with self.assertRaisesRegex(M.ModelsError, "does not change"):
                    M.compile_import(self.source, key, result.gltf_path, write_uvs=True, write_colours=True)

    def test_a_uv_edit_outside_the_range_widens_only_that_axis_of_the_shape_constant(self) -> None:
        resource, decoded, scene = self.source.parse(self.REFEREE)
        shape = scene["shapes"][0]
        lanes = M._shape_lanes(scene, shape, decoded)
        self.assertEqual(lanes.name, "ref_high")
        with tempfile.TemporaryDirectory() as tmp:
            result = M.export_model(self.source, self.REFEREE, Path(tmp) / "referee.gltf")
            document = json.loads(result.gltf_path.read_text(encoding="utf-8"))
            blob = bytearray(result.bin_path.read_bytes())
            accessor = document["accessors"][document["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]]
            at = document["bufferViews"][accessor["bufferView"]]["byteOffset"]
            _u0, v0 = struct.unpack_from("<2f", blob, at)
            wanted_u = lanes.uv_offset[0] + 1.5 * lanes.uv_scale[0]           # half a texture past the encodable edge
            struct.pack_into("<2f", blob, at, wanted_u, v0)
            result.bin_path.write_bytes(bytes(blob))
            with self.assertRaisesRegex(M.ModelsError, "range widening is off"):
                M.compile_import(self.source, self.REFEREE, result.gltf_path, write_uvs=True, allow_rescale=False)
            compiled = M.compile_import(self.source, self.REFEREE, result.gltf_path, write_uvs=True)
        report = compiled.shapes[0]
        self.assertTrue(report.uv_rescaled)
        self.assertFalse(report.rescaled)                                         # positions untouched
        self.assertEqual(report.positions_changed, 0)
        self.assertTrue(any("UV range widened on U:" in note for note in report.notes))
        self.assertIn("UV range widened", compiled.summary())
        rebuilt = self.source.decode_span(compiled.rebuilt_span, resource)
        (su, sv), (ou, ov) = M.read_uv_constant(rebuilt, lanes.record_offset)
        self.assertEqual((sv, ov), (lanes.uv_scale[1], lanes.uv_offset[1]))          # V constant byte-identical
        self.assertGreater(su, lanes.uv_scale[0])
        self.assertNotEqual(ou, lanes.uv_offset[0])
        before = M.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
        after = M.read_lane_2h(rebuilt, shape, lanes.texcoord, lanes.vertex_count)
        self.assertEqual([v for _u, v in before], [v for _u, v in after])            # V lane untouched
        step = su / 32767.0
        self.assertAlmostEqual(M.normshort(after[0][0]) * su + ou, wanted_u, delta=step)
        for i in range(1, lanes.vertex_count):                                        # every other u re-quantised within half a step
            self.assertAlmostEqual(M.normshort(after[i][0]) * su + ou,
                                   M.normshort(before[i][0]) * lanes.uv_scale[0] + lanes.uv_offset[0], delta=step / 2.0 + 1e-6)
        self.assertEqual(len(compiled.rebuilt_span), len(self.source.span(resource)))

    def test_color0_only_on_request_and_a_painted_nfl_color_comes_back(self) -> None:
        resource, decoded, scene = self.source.parse(self.STADIUM)
        shape = scene["shapes"][0]
        lanes = M._shape_lanes(scene, shape, decoded)
        self.assertIsNotNone(lanes.colour)
        with tempfile.TemporaryDirectory() as tmp:
            baked = M.export_model(self.source, self.STADIUM, Path(tmp) / "baked.gltf", include_vertex_colors_as_color0=True)
            document = json.loads(baked.gltf_path.read_text(encoding="utf-8"))
            attributes = document["meshes"][0]["primitives"][0]["attributes"]
            self.assertIn("COLOR_0", attributes)
            self.assertIn(M.COLOUR_ATTRIBUTE, attributes)
            self.assertIs(document["extras"]["nfl2k5_vertex_colour_contract"]["color0_written"], True)
            self.assertTrue(document["accessors"][attributes["COLOR_0"]]["normalized"])
            self.assertIn("COLOR_0 IS included", baked.readme_path.read_text(encoding="utf-8"))
            plain = M.export_model(self.source, self.STADIUM, Path(tmp) / "plain.gltf")
            self.assertIn("COLOR_0 is NOT included", plain.readme_path.read_text(encoding="utf-8"))
            document = json.loads(plain.gltf_path.read_text(encoding="utf-8"))
            blob = bytearray(plain.bin_path.read_bytes())
            accessor = document["accessors"][document["meshes"][0]["primitives"][0]["attributes"][M.COLOUR_ATTRIBUTE]]
            at = document["bufferViews"][accessor["bufferView"]]["byteOffset"]
            struct.pack_into("<4f", blob, at, 1.0, 0.0, 0.0, 1.0)                      # vertex 0 painted pure red
            plain.bin_path.write_bytes(bytes(blob))
            compiled = M.compile_import(self.source, self.STADIUM, plain.gltf_path)
        self.assertEqual(compiled.shapes[0].colours_changed, 1)
        self.assertEqual(sum(s.colours_changed for s in compiled.shapes), 1)
        self.assertEqual(sum(s.positions_changed for s in compiled.shapes), 0)
        self.assertIn("1 vertex colours", compiled.summary())
        rebuilt = self.source.decode_span(compiled.rebuilt_span, resource)
        self.assertEqual(M.read_lane_u32(rebuilt, shape, lanes.colour, 1)[0], 0xFFFF0000)


if __name__ == "__main__":
    unittest.main()
