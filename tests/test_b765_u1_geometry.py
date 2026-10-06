"""Fail-closed geometry handoff tests; no game asset is mutated."""
from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("u1_geometry", ROOT / "tools/b765/u1_geometry.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)


class ScopeTests(unittest.TestCase):
    def test_scope_receipt_proves_unchanged_outside_bytes(self):
        receipt = u.scope_receipt(b"abcd", b"abXd", [(2, 1)])
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual(receipt["changed_bytes"], 1)

    def test_scope_refuses_outside_edit_and_size_change(self):
        for after in (b"Xbcd", b"abcde"):
            with self.assertRaises(u.Refusal):
                u.scope_receipt(b"abcd", after, [(2, 1)])

    def test_outer_application_composes_and_is_idempotent(self):
        manifest = {"outer_offset": 2, "span_size": 4, "span_sha256": u.sha(b"abcd")}
        after, receipt = u.apply_outer(b"__abcd++", b"ABCD", manifest)
        self.assertEqual(after, b"__ABCD++")
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual(u.apply_outer(after, b"ABCD", manifest)[0], after)

    def test_outer_refuses_foreign_span_and_overflow(self):
        manifest = {"outer_offset": 2, "span_size": 4, "span_sha256": u.sha(b"abcd")}
        for before, span in ((b"__xxxx++", b"ABCD"), (b"__abcd++", b"ABCDE"), (b"__a", b"ABCD")):
            with self.assertRaises(u.Refusal):
                u.apply_outer(before, span, manifest)

    def test_face_identity_allows_reordering_and_cyclic_rotation(self):
        self.assertEqual(u.face_counter([(1,2,3),(3,4,5)]), u.face_counter([(4,5,3),(2,3,1)]))
        self.assertNotEqual(u.face_counter([(1,2,3)]), u.face_counter([(1,3,2)]))


class OutputAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.inputs = {name: self.folder / (name + ".bin")
                       for name in ("span", "outer", "manifest", "edited", "document", "before", "after", "retail")}
        for name, path in self.inputs.items():
            path.write_bytes(("original " + name).encode())
        self.output, self.receipt = self.folder / "output.bin", self.folder / "receipt.json"

    def refused_cli(self, arguments, message="aliases"):
        before = {p: p.read_bytes() for p in self.inputs.values()}
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), mock.patch.object(u, "compile_import") as compile_import, \
             mock.patch.object(u, "apply_outer") as apply_outer, mock.patch.object(u, "update_mask_document") as update:
            self.assertEqual(u.main([str(x) for x in arguments]), 2)
            compile_import.assert_not_called()
            apply_outer.assert_not_called()
            update.assert_not_called()
        self.assertIn(message, errors.getvalue())
        self.assertEqual(before, {p: p.read_bytes() for p in self.inputs.values()})
        self.assertFalse(self.output.exists())
        self.assertFalse(self.receipt.exists())

    def test_direct_and_resolved_input_aliases_refused(self):
        source = self.inputs["span"]
        for output in (source, self.folder / "missing" / ".." / source.name):
            with self.assertRaisesRegex(u.Refusal, "aliases"):
                u.guard_write_paths([source], [output])

    def test_symlink_and_hardlink_input_aliases_refused(self):
        source = self.inputs["span"]
        symbolic, hard = self.folder / "symbolic.bin", self.folder / "hard.bin"
        symbolic.symlink_to(source)
        os.link(source, hard)
        for output in (symbolic, hard):
            with self.assertRaises(u.Refusal):
                u.guard_write_paths([source], [output])
        self.assertEqual(source.read_bytes(), b"original span")

    def test_output_parent_symlinks_and_output_aliases_refused(self):
        link = self.folder / "linked"
        link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaisesRegex(u.Refusal, "symlink"):
            u.guard_write_paths([], [link / "output.bin"])
        with self.assertRaisesRegex(u.Refusal, "each other"):
            u.guard_write_paths([], [self.output, self.output])
        self.output.write_bytes(b"keep")
        os.link(self.output, self.receipt)
        with self.assertRaises(u.Refusal):
            u.guard_write_paths([], [self.output, self.receipt])
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_import_primary_and_receipt_inputs_are_protected(self):
        for flag in ("--output", "--receipt"):
            for name in ("span", "manifest", "edited"):
                with self.subTest(flag=flag, name=name):
                    out = self.inputs[name] if flag == "--output" else self.output
                    receipt = self.inputs[name] if flag == "--receipt" else self.receipt
                    self.refused_cli(["import", "--span", self.inputs["span"], "--manifest", self.inputs["manifest"],
                                      "--edited", self.inputs["edited"], "--output", out, "--receipt", receipt])

    def test_import_external_gltf_buffer_is_protected(self):
        binary = self.folder / "geometry.bin"
        binary.write_bytes(b"buffer remains")
        self.inputs["edited"].write_text(json.dumps({"asset": {"version": "2.0"},
                                                   "buffers": [{"uri": binary.name, "byteLength": 14}]}))
        self.refused_cli(["import", "--span", self.inputs["span"], "--manifest", self.inputs["manifest"],
                          "--edited", self.inputs["edited"], "--output", self.output, "--receipt", binary])
        self.assertEqual(binary.read_bytes(), b"buffer remains")

    def test_outer_primary_and_receipt_inputs_are_protected(self):
        for flag in ("--output", "--receipt"):
            for name in ("outer", "span", "manifest"):
                with self.subTest(flag=flag, name=name):
                    out = self.inputs[name] if flag == "--output" else self.output
                    receipt = self.inputs[name] if flag == "--receipt" else self.receipt
                    self.refused_cli(["apply-outer", "--outer", self.inputs["outer"], "--span", self.inputs["span"],
                                      "--manifest", self.inputs["manifest"], "--output", out, "--receipt", receipt])

    def test_staged_document_and_pins_protect_every_source(self):
        for flag in ("--output", "--pins"):
            for name in ("document", "before", "after", "retail", "outer"):
                with self.subTest(flag=flag, name=name):
                    out = self.inputs[name] if flag == "--output" else self.output
                    pins = self.inputs[name] if flag == "--pins" else self.receipt
                    self.refused_cli(["update-mask-document", "--document", self.inputs["document"],
                                      "--before-span", self.inputs["before"], "--after-span", self.inputs["after"],
                                      "--retail-span", self.inputs["retail"], "--retail-outer", self.inputs["outer"],
                                      "--output", out, "--pins", pins])

    def test_export_buffer_cannot_overwrite_source_span(self):
        folder = self.folder / "export"
        folder.mkdir()
        source = folder / "geometry.bin"
        source.write_bytes(b"native source")
        self.refused_cli(["export", "--key", u.mh.HI, "--span", source, "--out", folder])
        self.assertEqual(source.read_bytes(), b"native source")
        self.assertEqual([p.name for p in folder.iterdir()], ["geometry.bin"])


SPAN_DIR = Path(os.environ.get("B765_U1_GEOMETRY_EVIDENCE", "/nonexistent"))
HAS_SPANS = all((SPAN_DIR / f"v04_{key}.span").is_file() for key in u.mh.KEYS)


@unittest.skipUnless(HAS_SPANS, "set B765_U1_GEOMETRY_EVIDENCE to the private exact extracted spans")
class NativeGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.key = u.mh.HI
        self.span = (SPAN_DIR / f"v04_{self.key}.span").read_bytes()
        self.manifest = u.export(self.key, self.span, self.folder, ["FACEMASK23"], 1192208)
        self.path = self.folder / "geometry.gltf"

    def rewrite_document(self, mutate):
        doc = json.loads(self.path.read_text())
        mutate(doc)
        self.path.write_text(json.dumps(doc))

    def rewrite_accessor(self, attribute, mutate):
        doc = json.loads(self.path.read_text())
        accessor = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"][attribute]]
        view = doc["bufferViews"][accessor["bufferView"]]
        data = bytearray((self.folder / "geometry.bin").read_bytes())
        mutate(data, view["byteOffset"])
        (self.folder / "geometry.bin").write_bytes(data)

    def current_authoring_scene(self):
        """Pair the current document with its own scene, retaining pinned retail input."""
        document = u.mh.load_geometry()
        retail = (SPAN_DIR / f"retail_{self.key}.span").read_bytes()
        span, _ = u.mh.compile_scene(self.key, retail, document, u.mh.load_pins())
        return document, retail, span

    def test_all_exported_lanes_reimport_byte_identically_both_lods(self):
        for key in u.mh.KEYS:
            span = (SPAN_DIR / f"v04_{key}.span").read_bytes()
            folder = self.folder / key
            manifest = u.export(key, span, folder)
            # Use serialized manifest, like the actual CLI does.
            manifest = json.loads((folder / "manifest.json").read_text())
            after, receipt = u.compile_import(span, manifest, folder / "geometry.gltf", ("position","normal","uv"))
            self.assertEqual(after, span)
            self.assertEqual(receipt["decoded_scope"]["changed_bytes"], 0)
            self.assertEqual(receipt["stored_scope"]["changed_bytes"], 0)

    def test_common_helmet_number_export_preserves_native_ids_and_noop_bytes(self):
        names = [f"NUMBER_helmet_C_{side}" for side in ("L", "R", "M")]
        for key in u.mh.KEYS:
            span = (SPAN_DIR / f"v04_{key}.span").read_bytes()
            folder = self.folder / ("numbers_" + key)
            manifest = u.export(key, span, folder, names)
            self.assertEqual({m["name"] for m in manifest["meshes"]}, set(names))
            self.assertTrue(all(len(m["ids"]) == 4 and len(m["faces"]) == 2 for m in manifest["meshes"]))
            after, receipt = u.compile_import(span, manifest, folder / "geometry.gltf", ("position", "normal", "uv"))
            self.assertEqual(after, span)
            self.assertEqual(receipt["decoded_scope"]["changed_bytes"], 0)

    def test_missing_id_is_refused(self):
        self.rewrite_document(lambda d:d["meshes"][0]["primitives"][0]["attributes"].pop(u.models.VERTEX_INDEX_ATTRIBUTE))
        with self.assertRaisesRegex(u.Refusal, "Missing native vertex ID"):
            u.compile_import(self.span, self.manifest, self.path)

    def test_changed_original_id_is_refused(self):
        self.rewrite_accessor(u.models.VERTEX_INDEX_ATTRIBUTE, lambda data,at:struct.pack_into("<I",data,at,0))
        with self.assertRaisesRegex(u.Refusal, "vertex IDs/topology"):
            u.compile_import(self.span, self.manifest, self.path)

    def test_reversed_face_is_refused(self):
        doc = json.loads(self.path.read_text())
        accessor = doc["accessors"][doc["meshes"][0]["primitives"][0]["indices"]]
        at = doc["bufferViews"][accessor["bufferView"]]["byteOffset"]
        data = bytearray((self.folder / "geometry.bin").read_bytes())
        a,b,c = struct.unpack_from("<3I",data,at)
        struct.pack_into("<3I",data,at,a,c,b)
        (self.folder / "geometry.bin").write_bytes(data)
        with self.assertRaisesRegex(u.Refusal, "faces/topology/winding"):
            u.compile_import(self.span, self.manifest, self.path)

    def test_node_transform_is_refused(self):
        self.rewrite_document(lambda d:d["nodes"][0].update(scale=[1,2,1]))
        with self.assertRaisesRegex(u.Refusal, "transforms"):
            u.compile_import(self.span, self.manifest, self.path)

    def test_unknown_input_hash_and_tampered_manifest_are_refused(self):
        for span,manifest in ((self.span[:-1]+bytes([self.span[-1]^1]),self.manifest),
                              (self.span,dict(self.manifest,decoded_size=5))):
            with self.assertRaises(u.Refusal):
                u.compile_import(span, manifest, self.path)

    def test_position_range_overflow_is_refused(self):
        self.rewrite_accessor("POSITION",lambda data,at:struct.pack_into("<f",data,at,999))
        with self.assertRaisesRegex(u.Refusal, "quantization range"):
            u.compile_import(self.span,self.manifest,self.path)

    def test_uv_range_overflow_is_refused(self):
        self.rewrite_accessor("TEXCOORD_0",lambda data,at:struct.pack_into("<f",data,at,999))
        with self.assertRaisesRegex(u.Refusal, "UV exceeds"):
            u.compile_import(self.span,self.manifest,self.path,("uv",))

    def test_nonfinite_lane_is_refused(self):
        self.rewrite_accessor("POSITION",lambda data,at:struct.pack_into("<f",data,at,float("nan")))
        with self.assertRaisesRegex(u.Refusal, "Nonfinite"):
            u.compile_import(self.span,self.manifest,self.path)

    def test_bounded_edit_readback_preserves_commands_and_other_lanes(self):
        # A temporary-file edit exercises reimport; shipped geometry is untouched.
        document, retail, self.span = self.current_authoring_scene()
        self.folder = self.folder / "current"
        self.manifest = u.export(self.key, self.span, self.folder, ["FACEMASK23"], 1192208)
        self.path = self.folder / "geometry.gltf"
        def move(data,at):
            x = struct.unpack_from("<f",data,at)[0]
            struct.pack_into("<f",data,at,x+0.0001)
        self.rewrite_accessor("POSITION",move)
        after,receipt = u.compile_import(self.span,self.manifest,self.path)
        self.assertNotEqual(after,self.span)
        self.assertEqual(len(after),len(self.span))
        self.assertEqual(after[:32],self.span[:32])
        self.assertTrue(receipt["decoded_scope"]["outside_scope_identical"])
        self.assertTrue(receipt["topology_identical"])
        self.assertTrue(receipt["native_decode_readback_identical"])
        document = u.update_mask_document(document,self.span,after,retail)
        self.assertEqual(u.mh.author(self.key,u.mh.decode_span_bytes(retail,retail),document)[0],
                         u.mh.decode_span_bytes(after,after))

    def test_noop_source_document_preserves_all_original_fields(self):
        document, retail, span = self.current_authoring_scene()
        self.assertEqual(u.update_mask_document(document,span,span,retail),document)

    def test_current_document_refuses_stale_v04_scene_without_mutating_it(self):
        document, retail, current = self.current_authoring_scene()
        self.assertNotEqual(current, self.span)
        unchanged = copy.deepcopy(document)
        with self.assertRaisesRegex(u.Refusal, "Baseline geometry document does not reproduce the before scene"):
            u.update_mask_document(document,self.span,self.span,retail)
        self.assertEqual(document, unchanged)


if __name__ == "__main__":
    unittest.main()
