"""Exact stored-span geometry transport, using synthetic native SCNE bundles."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b765"))
import s1_geometry as geometry  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as builder  # noqa: E402


def native_bundle() -> bytes:
    record = bytearray(0x100)
    struct.pack_into("<I", record, 0x44, 2)
    struct.pack_into("<4f", record, 0x10, 0, 0, 0, 1)
    struct.pack_into("<I", record, 0x84, 0x32)
    struct.pack_into("<I", record, 0x88, 0x00080115)
    struct.pack_into("<I", record, 0x90, 0x140)
    struct.pack_into("<I", record, 0x9C, 0x00040121)
    struct.pack_into("<2H", record, 0xC4, 12, 10)
    template = builder.Shape(record, "template", [],
                             [builder.Submesh(bytearray(0x80), b"")], [None] * 8)
    positions = [(0, 0, 0), (0, 100, 0), (100, 0, 0), (100, 100, 0)]
    shape = builder.static_shape(template, "crowd_billboard", positions,
                                 [(101, 102, 103, 255)] * 4,
                                 [(0, 0), (0, 1), (1, 0), (1, 1)],
                                 [(0, builder.encode_words(builder.TRIANGLE_STRIP, [0, 1, 2, 3]))],
                                 uv_constant=(2, 2, 0, 0))
    reference = builder.static_shape(template, "seating_reference",
                                     [(x, y, z - 1) for x, y, z in positions],
                                     [(21, 22, 23, 255)] * 4,
                                     [(0, 0), (0, 1), (1, 0), (1, 1)],
                                     [(1, builder.encode_words(builder.TRIANGLE_STRIP, [0, 1, 2, 3]))])
    unreferenced = builder.static_shape(template, "unused_native_vertices", positions,
                                       [(11, 12, 13, 255)] * 4,
                                       [(0, 0), (0, 1), (1, 0), (1, 1)], [])
    identity = struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    nodes = [builder.Node(bytearray(0x60), s.name, s.name, identity, identity)
             for s in (shape, reference, unreferenced)]
    scene = builder.Scene("stadium", [],
                           [builder.Material(bytearray(0x80), "crowd", None),
                            builder.Material(bytearray(0x80), "seat01", None)],
                           nodes, [shape, reference, unreferenced], [])
    decoded, system, video = builder.serialize(scene)
    packed, _ = builder.compressed_chunk("SCNE", decoded, system, video,
                                         stream_tag=3, offset_bits=12, optimal=False)
    # Add a real fixed compression allocation with sufficient budget to allow
    # deliberate synthetic test movements without compression luck.
    head = list(struct.unpack_from("<4s7I", packed))
    stored = builder.align(len(decoded) + 128, 16)
    head[1] = stored
    padded = struct.pack("<4s7I", *head) + packed[32:] + bytes(stored - len(packed) + 32)
    allocated, _ = builder.fixed_span_chunk("SCNE", decoded, system, video, padded)
    prefix = struct.pack("<4s7I", b"TEST", 16, 16, 0, 0, 0, 0, 0) + bytes(range(16))
    suffix = struct.pack("<4s7I", b"TEST", 16, 16, 0, 0, 0, 0, 0) + bytes(range(16, 32))
    return prefix + allocated + suffix


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = native_bundle()
        self.export = self.root / "export"
        self.manifest = geometry.export_bundle(self.data, "s07dd.iff", self.export, outer_index=3143)
        self.path = self.export / "stadium.gltf"
        self.manifest_path = self.export / "manifest.json"

    def edit(self, attribute: str, vertex: int, values: tuple, *, shape: int = 0):
        document = json.loads(self.path.read_text())
        primitive = document["meshes"][shape]["primitives"][0]
        accessor = document["accessors"][primitive["attributes"][attribute]]
        view = document["bufferViews"][accessor["bufferView"]]
        widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
        width = widths[accessor["type"]]
        at = view.get("byteOffset", 0) + accessor.get("byteOffset", 0) + vertex * width * 4
        data = bytearray((self.export / "stadium.bin").read_bytes())
        struct.pack_into(f"<{width}f", data, at, *values)
        (self.export / "stadium.bin").write_bytes(data)

    def compile(self, data=None, **kwargs):
        return geometry.compile_bundle(data or self.data, self.manifest_path, self.path, **kwargs)

    def document_edit(self, callback):
        document = json.loads(self.path.read_text())
        callback(document)
        self.path.write_text(json.dumps(document))

    def test_unedited_roundtrip_is_entire_bundle_identical(self):
        output, receipt = self.compile()
        self.assertEqual(output, self.data)
        self.assertEqual(receipt["decoded_scope"]["changed_decoded_bytes"], 0)
        self.assertTrue(receipt["already_applied"])
        self.assertIn("shape_0001_seating_reference", (self.export / "stadium_reference.obj").read_text())
        self.assertIn("shape_0002_unused_native_vertices", (self.export / "stadium_reference.obj").read_text())

    def test_position_only_exact_span_readback_and_idempotency(self):
        self.edit("POSITION", 0, (1, 0, 0))
        output, receipt = self.compile(positions={0})
        offset, length = receipt["offset"], receipt["length"]
        self.assertNotEqual(output, self.data)
        self.assertEqual(output[:offset], self.data[:offset])
        self.assertEqual(output[offset + length:], self.data[offset + length:])
        self.assertEqual(receipt["decoded_scope"]["outside_sha256_before"],
                         receipt["decoded_scope"]["outside_sha256_after"])
        self.assertTrue(receipt["readback_exact"])
        repeated, repeated_receipt = self.compile(output, positions={0})
        self.assertEqual(repeated, output)
        self.assertTrue(repeated_receipt["already_applied"])
        self.assertEqual(repeated_receipt["decoded_scope"]["changed_decoded_bytes"], 0)

    def test_changed_other_chunk_composes_and_preserves_that_change(self):
        self.edit("POSITION", 0, (1, 0, 0))
        composed = bytearray(self.data)
        composed[40] ^= 0x80
        output, _ = self.compile(bytes(composed), positions={0})
        self.assertEqual(output[40], composed[40])

    def test_missing_explicit_position_scope_refuses(self):
        self.edit("POSITION", 0, (1, 0, 0))
        with self.assertRaisesRegex(geometry.GeometryError, "position edit has no explicit scope"):
            self.compile()

    def test_uv_scope_keeps_colours_selector_and_positions_exact(self):
        self.edit("TEXCOORD_0", 0, (0.25, 0.5))
        output, receipt = self.compile(uvs={0})
        _, old_scene, old = geometry.stadium(self.data)
        _, new_scene, new = geometry.stadium(output)
        lanes = geometry.models._shape_lanes(old_scene, old_scene["shapes"][0], old)
        self.assertEqual(geometry.models.read_positions(old, old_scene["shapes"][0], lanes),
                         geometry.models.read_positions(new, new_scene["shapes"][0], lanes))
        self.assertEqual({edit["lane"] for edit in receipt["edits"]}, {"uv"})
        self.assertEqual(receipt["decoded_scope"]["authorized_ranges"][0][1], 4)

    def test_uv_range_widening_requires_explicit_scope(self):
        self.edit("TEXCOORD_0", 0, (8, 0.5))
        with self.assertRaisesRegex(geometry.GeometryError, "rescale-uvs"):
            self.compile(uvs={0})
        output, receipt = self.compile(uvs={0}, rescale_uvs={0})
        self.assertNotEqual(output, self.data)
        self.assertIn("uv_constant", {edit["lane"] for edit in receipt["edits"]})

    def test_explicit_uv_constant_matches_compiler_and_preserves_other_lanes(self):
        constant = (0.5, 4.0, 0.5, 3.0)
        target = geometry.builder.static_shape(
            geometry.builder.parse(geometry.stadium(self.data)[2], geometry.stadium(self.data)[0].system_bytes).shapes[0],
            "target", [(0,0,0)] * 4, [(0,0,0,255)] * 4,
            [(0.2,-0.5),(0.3,2.0),(0.6,4.0),(0.8,6.0)], [], uv_constant=constant)
        expected = []
        for i in range(4):
            raw = struct.unpack_from('<2h', target.streams[1], i*10+4)
            expected.append(geometry.models.uv_to_gltf(*raw,constant[:2],constant[2:]))
            self.edit('TEXCOORD_0',i,expected[-1])
        with self.assertRaisesRegex(geometry.GeometryError, 'rescale-uvs scope'):
            self.compile(uvs={0},uv_constants={0:constant})
        output,receipt=self.compile(uvs={0},rescale_uvs={0},uv_constants={0:constant})
        chunk,_,decoded=geometry.stadium(output)
        actual=geometry.builder.parse(decoded,chunk.system_bytes).shapes[0]
        self.assertEqual(actual.record[0x30:0x40],target.record[0x30:0x40])
        self.assertEqual(b''.join(actual.streams[1][i*10+4:i*10+8] for i in range(4)),
                         b''.join(target.streams[1][i*10+4:i*10+8] for i in range(4)))
        repeated,_=self.compile(output,uvs={0},rescale_uvs={0},uv_constants={0:constant})
        self.assertEqual(repeated,output)
        self.assertTrue(receipt['decoded_scope']['outside_identical'])

    def test_invalid_explicit_uv_constant_refuses(self):
        for constant in ((0,1,0,0),(1,float('nan'),0,0),(1,2,3)):
            with self.assertRaisesRegex(geometry.GeometryError,'invalid explicit UV constant'):
                self.compile(uvs={0},rescale_uvs={0},uv_constants={0:constant})

    def test_new_outside_sphere_movement_requires_bounds_scope(self):
        self.edit("POSITION", 0, (-1000, 0, 0))
        with self.assertRaisesRegex(geometry.GeometryError, "culling sphere"):
            self.compile(positions={0})
        output, receipt = self.compile(positions={0}, bounds={0})
        self.assertNotEqual(output, self.data)
        self.assertIn("bounding_sphere", {edit["lane"] for edit in receipt["edits"]})

    def test_lost_vertex_id_refuses(self):
        self.document_edit(lambda doc: doc["meshes"][0]["primitives"][0]["attributes"].pop("_NFL_VERTEX_INDEX"))
        with self.assertRaisesRegex(geometry.GeometryError, "missing _NFL_VERTEX_INDEX"):
            self.compile()

    def test_duplicate_missing_or_fractional_vertex_id_refuses(self):
        for value in (0, 1.5, float("nan")):
            self.edit("_NFL_VERTEX_INDEX", 1, (value,))
            with self.assertRaises(geometry.GeometryError):
                self.compile()

    def test_colour_edit_refuses_even_with_position_scope(self):
        self.edit("_NFL_COLOR", 0, (1, 1, 1, 1))
        with self.assertRaisesRegex(geometry.GeometryError, "_NFL_COLOR changed"):
            self.compile(positions={0})

    def test_material_and_node_edit_refuse(self):
        self.document_edit(lambda doc: doc["materials"][0].update(alphaMode="BLEND"))
        with self.assertRaisesRegex(geometry.GeometryError, "materials changed"):
            self.compile()
        original = json.loads((self.export / "baseline.gltf").read_text())
        original["buffers"][0]["uri"] = "stadium.bin"
        original["nodes"][0]["translation"] = [0, 1, 0]
        self.path.write_text(json.dumps(original))
        with self.assertRaisesRegex(geometry.GeometryError, "nodes changed"):
            self.compile()

    def test_reversed_winding_refuses(self):
        document = json.loads(self.path.read_text())
        primitive = document["meshes"][0]["primitives"][0]
        accessor = document["accessors"][primitive["indices"]]
        view = document["bufferViews"][accessor["bufferView"]]
        at = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        data = bytearray((self.export / "stadium.bin").read_bytes())
        struct.pack_into("<4H", data, at, 1, 0, 2, 3)
        (self.export / "stadium.bin").write_bytes(data)
        with self.assertRaisesRegex(geometry.GeometryError, "topology changed"):
            self.compile()

    def test_vertex_reordering_with_exact_native_ids_is_byte_identical(self):
        document = json.loads(self.path.read_text())
        primitive = document["meshes"][0]["primitives"][0]
        payload = bytearray((self.export / "stadium.bin").read_bytes())
        order = [2, 0, 3, 1]
        for accessor_id in primitive["attributes"].values():
            accessor = document["accessors"][accessor_id]
            view = document["bufferViews"][accessor["bufferView"]]
            width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]] * 4
            begin = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            original = bytes(payload[begin:begin + width * 4])
            payload[begin:begin + width * 4] = b"".join(original[i * width:(i + 1) * width] for i in order)
        accessor = document["accessors"][primitive["indices"]]
        view = document["bufferViews"][accessor["bufferView"]]
        begin = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        struct.pack_into("<4H", payload, begin, *(order.index(i) for i in range(4)))
        (self.export / "stadium.bin").write_bytes(payload)
        output, receipt = self.compile()
        self.assertEqual(output, self.data)
        self.assertEqual(receipt["decoded_scope"]["changed_decoded_bytes"], 0)

    def test_native_strip_to_equivalent_triangles_is_byte_identical(self):
        document = json.loads(self.path.read_text())
        primitive = document["meshes"][0]["primitives"][0]
        payload = bytearray((self.export / "stadium.bin").read_bytes())
        # The exported file may triangulate; the native push words are never rewritten.
        begin = len(payload)
        payload.extend(struct.pack("<6H", 0, 1, 2, 2, 1, 3))
        document["bufferViews"].append({"buffer": 0, "byteOffset": begin, "byteLength": 12})
        document["accessors"].append({"bufferView": len(document["bufferViews"]) - 1,
                                        "componentType": 5123, "type": "SCALAR", "count": 6})
        primitive["mode"] = 4
        primitive["indices"] = len(document["accessors"]) - 1
        document["buffers"][0]["byteLength"] = len(payload)
        self.path.write_text(json.dumps(document))
        (self.export / "stadium.bin").write_bytes(payload)
        output, _ = self.compile()
        self.assertEqual(output, self.data)

    def test_unknown_input_stadium_hash_refuses(self):
        self.edit("POSITION", 0, (1, 0, 0))
        changed = bytearray(self.data)
        offset = self.manifest["chunk_offset"]
        # Wrapper scratch-word changes leave decode valid but invalidate the pin.
        changed[offset + 20] ^= 1
        with self.assertRaisesRegex(geometry.GeometryError, "unexpected input stadium hash"):
            self.compile(bytes(changed), positions={0})

    def test_corrupted_baseline_refuses(self):
        path = self.export / "baseline.bin"
        path.write_bytes(path.read_bytes() + b"bad")
        with self.assertRaisesRegex(geometry.GeometryError, "unexpected baseline.bin hash"):
            self.compile()

    def test_compression_budget_failure_does_not_write_any_file(self):
        self.edit("POSITION", 0, (1, 0, 0))
        with mock.patch.object(builder, "fixed_span_chunk", side_effect=builder.ScneBuildError("scene does not fit the stored span")):
            with self.assertRaisesRegex(ValueError, "does not fit"):
                self.compile(positions={0})
        self.assertEqual((self.export / "source.scne").read_bytes(),
                         geometry.span_bytes(self.data, geometry.stadium(self.data)[0]))

    def test_scope_proof_detects_one_byte_outside_authorized_ranges(self):
        with self.assertRaisesRegex(geometry.GeometryError, "outside authorized geometry lanes"):
            geometry.scope_proof(b"0123456789", b"0X23X56789", [(4, 5)])

    def test_write_atomic_reads_back_and_rejects_symlink(self):
        path = self.root / "fixed.iff"
        geometry.write_atomic(path, self.data)
        self.assertEqual(path.read_bytes(), self.data)
        link = self.root / "alias.iff"
        link.symlink_to(path)
        with self.assertRaisesRegex(geometry.GeometryError, "symlink"):
            geometry.write_atomic(link, b"bad")
        self.assertEqual(path.read_bytes(), self.data)

    def test_cli_receipt_collision_preserves_input_and_does_not_write_output(self):
        input_path = self.root / "s07dd.iff"
        input_path.write_bytes(self.data)
        output = self.root / "fixed" / "s07dd.iff"
        for receipt in (input_path, output, self.manifest_path, self.export / "stadium.bin"):
            with mock.patch("sys.stderr"):
                result = geometry.main(["import", "--input", str(input_path),
                                        "--manifest", str(self.manifest_path), "--edited", str(self.path),
                                        "--output", str(output), "--receipt", str(receipt)])
            self.assertEqual(result, 2)
            self.assertFalse(output.exists())
            self.assertEqual(input_path.read_bytes(), self.data)
            self.assertEqual(geometry.sha((self.export / "baseline.bin").read_bytes()),
                             self.manifest["baseline_bin_sha256"])

    def test_cli_output_cannot_clobber_pinned_source_or_edit_buffer(self):
        input_path = self.root / "s07dd.iff"
        input_path.write_bytes(self.data)
        for output in (self.export / "source.scne", self.export / "stadium.bin"):
            original = output.read_bytes()
            with mock.patch("sys.stderr"):
                result = geometry.main(["import", "--input", str(input_path),
                                        "--manifest", str(self.manifest_path), "--edited", str(self.path),
                                        "--output", str(output), "--receipt", str(self.root / "receipt.json")])
            self.assertEqual(result, 2)
            self.assertEqual(output.read_bytes(), original)
            self.assertFalse((self.root / "receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
