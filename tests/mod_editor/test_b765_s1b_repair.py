"""Crowd-only repair guards and exact full-mesh Studio UV compiler equality."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402
from tests.mod_editor.test_b765_s1_geometry import native_bundle  # noqa: E402
from tools.b765 import s1_geometry as g, s1b_repair as repair  # noqa: E402


def fixture():
    """Non-crowd vertices deliberately control the full mesh's UV range."""
    original = native_bundle()
    chunk, _, decoded = g.stadium(original)
    scene = sb.parse(decoded, chunk.system_bytes)
    mesh = SimpleNamespace(
        name="test_bowl",
        P=[(-2, -2, 0), (2, 2, 0), (0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0)],
        UV=[(-8, -70), (12, 120), (.2425, 3.25), (.0075, 3.25),
            (.2425, 4.5), (.0075, 4.5)],
        groups={"crowd": [[2, 3, 4, 5]], "seat01": [[0, 1, 2]]},
    )
    model = SimpleNamespace(meshes={mesh.name: mesh})
    ids = [2, 3, 4, 5]
    full = sb.static_shape(scene.shapes[0], mesh.name, np.asarray(mesh.P) * 100,
                           [(0, 0, 0, 255)] * len(mesh.P), mesh.UV, [])
    constant = struct.unpack_from("<4f", full.record, 0x30)
    crowd = sb.static_shape(
        scene.shapes[0], mesh.name + "_crowd_fix", np.asarray(mesh.P)[ids] * 100,
        [(101, 102, 103, 255)] * 4, [(0, 0), (0, 1), (1, 0), (1, 1)],
        [(0, sb.encode_words(sb.TRIANGLE_STRIP, [0, 1, 2, 3]))],
        uv_constant=(2, 2, 0, 0),
    )
    scene.shapes[0] = crowd
    scene.nodes[0].name = crowd.name
    scene.nodes[0].shape_name = crowd.name
    decoded, system, video = sb.serialize(scene)
    packed, _ = sb.compressed_chunk("SCNE", decoded, system, video,
                                    stream_tag=3, offset_bits=12, optimal=False)
    header = list(struct.unpack_from("<4s7I", packed))
    header[1] = sb.align(len(decoded) + 256, 16)
    padded = (struct.pack("<4s7I", *header) + packed[32:]
              + bytes(header[1] - len(packed) + 32))
    span, _ = sb.fixed_span_chunk("SCNE", decoded, system, video, padded)
    data = original[:chunk.offset] + span + original[chunk.end_offset:]
    return data, model, full, constant


class CrowdRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.model, self.full, self.constant = fixture()
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        (self.inputs / "s07dd.iff").write_bytes(self.data)
        self.export = self.root / "export"
        g.export_bundle(self.data, "s07dd.iff", self.export)
        self.targets = repair.studio_targets(self.scene(self.data), self.model)
        self.entry = dict(name="s07dd.iff", manifest="export/manifest.json",
                          edited="export/stadium.gltf", uvs=[0], rescale_uvs=[0],
                          uv_constants={"0": list(self.constant)})
        self.plan = self.root / "plan.json"
        self.output = self.root / "output"
        self.receipt = self.root / "receipt.json"

    @staticmethod
    def scene(data):
        chunk, _, decoded = g.stadium(data)
        return sb.parse(decoded, chunk.system_bytes)

    def write_plan(self):
        self.plan.write_text(json.dumps(dict(schema="b765_s1_repair_plan/v1",
                                              entries=[self.entry])))

    def apply(self, inputs=None, output=None, receipt=None):
        self.write_plan()
        module = SimpleNamespace(build=lambda code: self.model)
        real_import = repair.importlib.import_module

        def import_model(name, *args, **kwargs):
            if name == "mod_editor.core.nfl2k5_att_model":
                return module
            return real_import(name, *args, **kwargs)

        with mock.patch.object(repair.importlib, "import_module", side_effect=import_model):
            repair.apply(inputs or self.inputs, output or self.output, self.plan,
                         receipt or self.receipt)

    def edit_reference_uv(self):
        doc = json.loads((self.export / "stadium.gltf").read_text())
        primitive = doc["meshes"][1]["primitives"][0]
        accessor = doc["accessors"][primitive["attributes"]["TEXCOORD_0"]]
        view = doc["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        payload = bytearray((self.export / "stadium.bin").read_bytes())
        struct.pack_into("<2f", payload, offset, .25, .5)
        (self.export / "stadium.bin").write_bytes(payload)

    def assert_refused_before_write(self):
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual((self.inputs / "s07dd.iff").read_bytes(), self.data)

    def test_targets_use_full_mesh_range_then_native_crowd_order(self):
        target = self.targets[0]
        self.assertEqual(target["ids"], [2, 3, 4, 5])
        self.assertEqual(target["constant"], self.constant)
        packed = np.frombuffer(self.full.streams[1],
                               np.dtype([("c", "u1", 4), ("uv", "<i2", 2),
                                         ("s", "<i2")]))["uv"]
        self.assertTrue(np.array_equal(target["raw"], packed[[2, 3, 4, 5]]))
        compact = sb.static_shape(self.scene(self.data).shapes[0], "compact",
                                  np.asarray(self.model.meshes["test_bowl"].P)[2:] * 100,
                                  [(0, 0, 0, 255)] * 4,
                                  self.model.meshes["test_bowl"].UV[2:], [])
        self.assertNotEqual(compact.record[0x30:0x40], self.full.record[0x30:0x40])

    def test_native_position_order_mismatch_refuses_instead_of_remapping(self):
        scene = self.scene(self.data)
        original = scene.shapes[0].streams[0]
        scene.shapes[0].streams[0] = original[12:24] + original[:12] + original[24:]
        with self.assertRaisesRegex(ValueError, "native vertex order/positions differ"):
            repair.studio_targets(scene, self.model)

    def test_cached_compiler_checks_native_vertex_order_on_every_resource(self):
        compiled_meshes = {}
        repair.studio_targets(self.scene(self.data), self.model, compiled_meshes=compiled_meshes)
        scene = self.scene(self.data)
        original = scene.shapes[0].streams[0]
        scene.shapes[0].streams[0] = original[12:24] + original[:12] + original[24:]
        # Reusing the compiled target must retain the per-resource native
        # ordering guard, even when every vertex declaration byte is unchanged.
        with mock.patch.object(repair.sb, "static_shape") as compile_shape:
            with self.assertRaisesRegex(ValueError, "native vertex order/positions differ"):
                repair.studio_targets(scene, self.model, compiled_meshes=compiled_meshes)
            compile_shape.assert_not_called()

    def test_crowd_shape_with_non_crowd_submesh_refuses(self):
        scene = self.scene(self.data)
        reference = scene.shapes[1].submeshes[0]
        scene.shapes[0].submeshes.append(sb.Submesh(bytearray(reference.record), reference.words))
        with self.assertRaisesRegex(ValueError, "non-crowd draw"):
            repair.studio_targets(scene, self.model)

    def test_non_crowd_uv_scope_refuses_before_any_output(self):
        repair.edit_uvs(self.export, self.targets)
        self.edit_reference_uv()
        self.entry["uvs"] = [0, 1]
        self.assert_refused_before_write()

    def test_position_and_bounds_scope_refuse_before_any_output(self):
        repair.edit_uvs(self.export, self.targets)
        self.entry.update(positions=[0], bounds=[0])
        self.assert_refused_before_write()

    def test_texture_plan_refuses_before_any_output(self):
        self.entry = dict(name="s07dd.iff", manifest="export/manifest.json", textures=[])
        self.assert_refused_before_write()

    def test_wrong_crowd_uvs_refuse_before_any_output(self):
        # An authorized UV shape/constant scope is insufficient: the resulting
        # packed UVs must also equal Studio's compiled full-mesh crowd vertices.
        self.assert_refused_before_write()

    def test_apply_matches_compiler_preserves_other_lanes_and_is_idempotent(self):
        repair.edit_uvs(self.export, self.targets)
        composed = bytearray(self.data)
        composed[40] ^= 0x80  # Independent non-stadium allocation stands for another writer.
        (self.inputs / "s07dd.iff").write_bytes(composed)
        self.apply()
        output = (self.output / "s07dd.iff").read_bytes()
        self.assertEqual(output[40], composed[40])
        before, after = self.scene(self.data), self.scene(output)
        self.assertEqual(before.shapes[0].streams[0], after.shapes[0].streams[0])
        for i in range(4):
            self.assertEqual(before.shapes[0].streams[1][i * 10:i * 10 + 4],
                             after.shapes[0].streams[1][i * 10:i * 10 + 4])
            self.assertEqual(before.shapes[0].streams[1][i * 10 + 8:i * 10 + 10],
                             after.shapes[0].streams[1][i * 10 + 8:i * 10 + 10])
        self.assertEqual(before.shapes[1].streams, after.shapes[1].streams)
        self.assertEqual(after.shapes[0].record[0x30:0x40], self.full.record[0x30:0x40])
        equality = repair.verify(output, "s07", self.model)
        self.assertTrue(equality[0]["packed_uv_and_constants_equal_studio"])
        receipt = json.loads(self.receipt.read_text())
        self.assertTrue(receipt["entries"][0]["decoded_scope"]["outside_identical"])
        again = self.root / "again"
        self.apply(inputs=self.output, output=again, receipt=self.root / "again.json")
        self.assertEqual((again / "s07dd.iff").read_bytes(), output)
        self.assertTrue(json.loads((self.root / "again.json").read_text())["entries"][0]["already_applied"])


if __name__ == "__main__":
    unittest.main()
