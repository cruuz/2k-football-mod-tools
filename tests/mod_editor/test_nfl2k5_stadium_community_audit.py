"""Proof-oracle tests and pinned reproductions of rejected community versions.

The KnownCommunityBehavior tests PASS when they reproduce the stated defect;
they are NOT a release safety approval. They skip without the private supplied
scripts. Set NFL2K5_COMMUNITY_ADDONS to their folder to run them elsewhere.
No bpy stub result is substituted for the separate real-Blender retail proof.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.nfl_stadium_community_proof import binary_delta, contract_details, float_rows, runs

ADDONS = Path(os.environ.get('NFL2K5_COMMUNITY_ADDONS', ROOT / '.scratch/community'))
EXPORTER = ADDONS / 'NFL_2K5_Stadium_RoundTrip_Exporter_v0_3_0.py'
# Bound these defect reproductions to the exact reviewed upstream source.
EXPORTER_SHA256 = 'd87fdff9bf1fb1135d8d65323d91261bfa5e33e9b9355d3dc4d866efe46a488a'


def fixture():
    return {
        'buffers': [{'uri': 'template.bin', 'byteLength': 64}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 4, 'byteLength': 28, 'byteStride': 16},
                        {'buffer': 0, 'byteOffset': 40, 'byteLength': 8}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'type': 'VEC3', 'count': 2,
                       'min': [0, 0, 0], 'max': [0, 0, 0]},
                      {'bufferView': 1, 'componentType': 5126, 'type': 'SCALAR', 'count': 2}],
        'meshes': [{'name': 'part', 'primitives': [{'attributes': {'POSITION': 0, '_NFL_VERTEX_INDEX': 1}}]}],
    }


def payload():
    data = bytearray(b'\xAA' * 64)
    struct.pack_into('<3f', data, 4, 1, 2, 3)
    struct.pack_into('<3f', data, 20, 4, 5, 6)
    struct.pack_into('<2f', data, 40, 0, 1)
    return data


class ProofOracleTests(unittest.TestCase):
    def test_ranges_are_lossless_and_inclusive(self):
        self.assertEqual(runs([]), [])
        self.assertEqual(runs([7, 3, 4, 4, 0]), [[0, 0], [3, 4], [7, 7]])

    def test_reader_uses_both_offsets_and_stride(self):
        doc = fixture()
        doc['bufferViews'][0]['byteOffset'] = 0
        doc['accessors'][0]['byteOffset'] = 4
        self.assertEqual(float_rows(doc, payload(), 0), [(1, 2, 3), (4, 5, 6)])

    def test_noop_has_zero_differences(self):
        result = binary_delta(fixture(), payload(), payload())
        self.assertEqual(result['changed_bytes'], 0)
        self.assertEqual(result['accessors'], [])

    def test_full_byte_accounting_including_unowned_bytes(self):
        old, new = payload(), payload()
        new[7] ^= 1
        new[22] ^= 1
        new[63] ^= 1
        doc = fixture()
        # Shared primitive accessors must not double-count the changed bytes.
        doc['meshes'][0]['primitives'] *= 2
        result = binary_delta(doc, old, new)
        self.assertEqual(result['changed_bytes'], 3)
        self.assertEqual(result['by_semantic'], {'POSITION': 2})
        self.assertEqual(result['unattributed_byte_ranges_inclusive'], [[63, 63]])
        self.assertEqual(result['accessors'][0]['row_ranges_inclusive'], [[0, 1]])
        self.assertEqual(result['accessors'][0]['byte_ranges_inclusive'], [[7, 7], [22, 22]])

    def test_size_change_is_not_silently_zipped(self):
        with self.assertRaisesRegex(ValueError, 'size changed'):
            binary_delta(fixture(), payload(), payload() + b'x')

    def test_blender_uv_float_roundtrip_loses_source_bits(self):
        def f32(value):
            return struct.unpack('<f', struct.pack('<f', value))[0]
        original = f32(0.0006206793477758765)
        back = f32(1 - f32(1 - original))
        self.assertNotEqual(struct.pack('<f', original), struct.pack('<f', back))

    def test_axis_diagnostic_separates_swizzle_from_rounding(self):
        doc = fixture()
        old, new = payload(), payload()
        struct.pack_into('<3f', new, 4, 1, -3, 2)
        out = copy.deepcopy(doc)
        out['accessors'][0].update(min=[1, -3, 2], max=[4, 5, 6])
        result = contract_details(doc, old, {'unchanged': (out, new)})
        self.assertEqual(result['axis_correction_only']['still_different_position_rows'], 0)
        self.assertTrue(result['unchanged_bounds_correct'])
        self.assertTrue(result['unchanged_document_matches_except_buffer_and_bounds'])

    def test_contract_diagnostic_detects_material_and_bounds_changes(self):
        doc = fixture()
        out = copy.deepcopy(doc)
        out['meshes'][0]['primitives'][0]['material'] = 99
        result = contract_details(doc, payload(), {'unchanged': (out, payload())})
        self.assertFalse(result['unchanged_bounds_correct'])
        self.assertFalse(result['unchanged_document_matches_except_buffer_and_bounds'])


class KnownCommunityBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXPORTER.is_file():
            raise unittest.SkipTest('Private community exporter absent; set NFL2K5_COMMUNITY_ADDONS')
        source = EXPORTER.read_bytes()
        if hashlib.sha256(source).hexdigest() != EXPORTER_SHA256:
            raise unittest.SkipTest('Community exporter differs from reviewed v0.3.0 SHA-256')
        tree = ast.parse(source)
        # Load the ORIGINAL functions, without executing Blender UI registration.
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name)
                                                        and t.id.startswith('_GLTF_') for t in node.targets)]
        cls.namespace = {'struct': struct, 'os': os, 'json': json}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(EXPORTER), 'exec'), cls.namespace)

    def setUp(self):
        self.api = dict(self.namespace)
        self.doc = fixture()
        self.binary = payload()

    def test_supported_strided_float_rows_preserve_padding(self):
        before = self.binary[:]
        self.api['_write_accessor_rows'](self.doc, self.binary, 0, {1: (7, 8, 9)})
        self.assertEqual(self.binary[:20], before[:20])
        self.assertEqual(self.binary[32:], before[32:])
        self.assertEqual(float_rows(self.doc, self.binary, 0)[1], (7, 8, 9))

    def test_minmax_includes_untouched_rows(self):
        self.api['_write_accessor_rows'](self.doc, self.binary, 0, {1: (-7, 8, 0)})
        self.api['_refresh_accessor_minmax'](self.doc, self.binary, 0)
        self.assertEqual(self.doc['accessors'][0]['min'], [-7, 2, 0])
        self.assertEqual(self.doc['accessors'][0]['max'], [1, 8, 3])

    def test_sparse_and_nonfloat_refuse_before_write(self):
        before = self.binary[:]
        self.doc['accessors'][0]['sparse'] = {'count': 1}
        with self.assertRaisesRegex(ValueError, 'Sparse'):
            self.api['_write_accessor_rows'](self.doc, self.binary, 0, {0: (7, 8, 9)})
        del self.doc['accessors'][0]['sparse']
        self.doc['accessors'][0]['componentType'] = 5123
        with self.assertRaisesRegex(ValueError, 'not FLOAT'):
            self.api['_write_accessor_rows'](self.doc, self.binary, 0, {0: (7, 8, 9)})
        self.assertEqual(self.binary, before)

    def test_known_view_overrun_writes_neighbor_bytes(self):
        self.doc['bufferViews'][0]['byteLength'] = 12
        self.assertEqual(self.api['_write_accessor_rows'](self.doc, self.binary, 0, {1: (7, 8, 9)}), 1)
        self.assertEqual(struct.unpack_from('<3f', self.binary, 20), (7, 8, 9))

    def test_known_nan_is_accepted(self):
        self.api['_write_accessor_rows'](self.doc, self.binary, 0, {0: (math.nan, 8, 9)})
        self.assertTrue(math.isnan(struct.unpack_from('<f', self.binary, 4)[0]))

    def test_known_invalid_rows_and_width_are_silently_skipped(self):
        before = self.binary[:]
        self.assertEqual(self.api['_write_accessor_rows'](self.doc, self.binary, 0,
                                                         {-1: (1, 2, 3), 2: (1, 2, 3), 0: (1, 2)}), 0)
        self.assertEqual(before, self.binary)

    def test_known_conflicting_uv_corners_choose_first(self):
        layer = SimpleNamespace(data=[SimpleNamespace(uv=SimpleNamespace(x=1, y=2)),
                                      SimpleNamespace(uv=SimpleNamespace(x=3, y=4))])
        layers = type('Layers', (list,), {'active': layer})([layer])
        mesh = SimpleNamespace(vertices=[object()], loops=[SimpleNamespace(vertex_index=0, index=i) for i in range(2)],
                               uv_layers=layers)
        self.assertEqual(self.api['_vertex_uv_values'](mesh), [(1, 2)])

    def fast_export(self, folder, output, edits=None):
        template = folder / 'template.gltf'
        template.write_text(json.dumps(self.doc), encoding='utf-8')
        (folder / 'template.bin').write_bytes(self.binary)
        # Functions retain their original namespace; restore these two hooks
        # after every test so only file loading and the scene collector are stubbed.
        originals = {name: self.namespace[name] for name in ('_resolve_template_gltf', '_collect_fast_edits')}
        self.namespace['_resolve_template_gltf'] = lambda *a: str(template)
        self.namespace['_collect_fast_edits'] = lambda *a: (edits or {'part': {0: {'POSITION': (9, 8, 7)}}}, 1, [], [])
        settings = SimpleNamespace(strict_validation=True, patch_positions=True, patch_uvs=True,
                                   patch_vertex_colors=True, patch_normals=True)
        try:
            # Upstream opens its BIN without a context manager. This test audits
            # that source unchanged; do not let the warning obscure the result.
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                return self.api['_fast_template_export'](None, None, str(output), settings)
        finally:
            self.namespace.update(originals)

    def test_known_export_overwrites_template_even_with_strict_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            ok, message, _ = self.fast_export(folder, folder / 'template.gltf')
            self.assertTrue(ok, message)
            self.assertNotEqual((folder / 'template.bin').read_bytes(), self.binary)

    def test_known_json_failure_leaves_written_bin(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            output = folder / 'out.gltf'
            output.mkdir()
            ok, _, _ = self.fast_export(folder, output)
            self.assertFalse(ok)
            self.assertTrue((folder / 'out.bin').is_file())

    def test_known_output_symlink_writes_outside_selected_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            chosen = folder / 'chosen'
            chosen.mkdir()
            victim = folder / 'unrelated.bin'
            victim.write_bytes(b'unchanged user file')
            try:
                (chosen / 'out.bin').symlink_to(victim)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f'Creating symlinks unavailable: {exc}')
            ok, message, _ = self.fast_export(folder, chosen / 'out.gltf')
            self.assertTrue(ok, message)
            self.assertNotEqual(victim.read_bytes(), b'unchanged user file')

    def test_known_unknown_source_id_silently_succeeds(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            ok, message, _ = self.fast_export(folder, folder / 'out.gltf', {'part': {999: {'POSITION': (9, 8, 7)}}})
            self.assertTrue(ok, message)
            self.assertEqual((folder / 'out.bin').read_bytes(), self.binary)

    def test_missing_normals_in_template_are_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            ok, message, _ = self.fast_export(folder, folder / 'out.gltf', {'part': {0: {'NORMAL': (0, 0, 1)}}})
            self.assertTrue(ok, message)
            self.assertEqual((folder / 'out.bin').read_bytes(), self.binary)
            doc = json.loads((folder / 'out.gltf').read_text())
            self.assertNotIn('NORMAL', doc['meshes'][0]['primitives'][0]['attributes'])

    def test_known_multiple_id_accessors_cross_patch_unrelated_rows(self):
        self.binary.extend(b'\xAA' * 64)
        self.doc['buffers'][0]['byteLength'] = len(self.binary)
        self.doc['bufferViews'].extend([{'buffer': 0, 'byteOffset': 64, 'byteLength': 24},
                                        {'buffer': 0, 'byteOffset': 88, 'byteLength': 8}])
        self.doc['accessors'].extend([{'bufferView': 2, 'componentType': 5126, 'type': 'VEC3', 'count': 2},
                                      {'bufferView': 3, 'componentType': 5126, 'type': 'SCALAR', 'count': 2}])
        self.doc['meshes'][0]['primitives'].append({'attributes': {'POSITION': 2, '_NFL_VERTEX_INDEX': 3}})
        struct.pack_into('<6f', self.binary, 64, 10, 20, 30, 40, 50, 60)
        struct.pack_into('<2f', self.binary, 88, 1, 0)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            ok, message, _ = self.fast_export(folder, folder / 'out.gltf')
            self.assertTrue(ok, message)
            after = (folder / 'out.bin').read_bytes()
            # Only ID 0 was edited. Both ID 1 rows have also been overwritten.
            self.assertEqual(float_rows(self.doc, after, 0), [(9, 8, 7)] * 2)
            self.assertEqual(float_rows(self.doc, after, 2), [(9, 8, 7)] * 2)


def scene_probe(output):
    """Exercise the supplied cleanup on disposable Blender datablocks only."""
    import bpy
    from tools.nfl_stadium_community_proof import IMPORTER, load_addon

    importer = load_addon(ADDONS / IMPORTER, 'community_cleanup_probe')
    root = bpy.data.objects.new('nfl2k5_units_centimetre_to_metre', None)
    bpy.context.scene.collection.objects.link(root)
    child = bpy.data.objects.new('UserAddedChild', None)
    bpy.context.scene.collection.objects.link(child)
    child.parent = root  # Untagged user object under a recognized root.
    shared_mesh = bpy.data.meshes.new('SharedUserMesh')
    stadium_part = bpy.data.objects.new('StadiumPart', shared_mesh)
    unrelated = bpy.data.objects.new('UnrelatedUserObject', shared_mesh)
    bpy.context.scene.collection.objects.link(stadium_part)
    bpy.context.scene.collection.objects.link(unrelated)
    stadium_part.parent = root
    bpy.context.view_layer.update()
    removed = importer.clear_previous_nfl2k5_import(bpy.context)
    receipt = {'removed': list(removed),
               'untagged_child_deleted': bpy.data.objects.get('UserAddedChild') is None,
               'unrelated_object_retained': bpy.data.objects.get('UnrelatedUserObject') is not None,
               'shared_mesh_retained': bpy.data.meshes.get('SharedUserMesh') is not None}
    Path(output).write_text(json.dumps(receipt), encoding='utf-8')
    importer.unregister()


class BlenderSceneSafetyTests(unittest.TestCase):
    def test_known_cleanup_deletes_untagged_descendants_but_keeps_shared_data(self):
        importer = ADDONS / 'NFL_2K5_Stadium_Importer_v0_11_1.py'
        if not importer.is_file():
            self.skipTest('Private community importer absent; set NFL2K5_COMMUNITY_ADDONS')
        if hashlib.sha256(importer.read_bytes()).hexdigest() != '0353398b0962137b101835f8c47874a1f41ba13b1222539a07471d27915f48fe':
            self.skipTest('Community importer differs from reviewed v0.11.1 SHA-256')
        blender = shutil.which('blender')
        if blender is None:
            self.skipTest('Blender is not installed; scene cleanup requires real bpy')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / 'scene.json'
            result = subprocess.run([blender, '-b', '-noaudio', '--factory-startup', '-t', '2',
                                     '--python-exit-code', '1', '--python', str(Path(__file__).resolve()),
                                     '--', '--scene-probe', str(output)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout)
            receipt = json.loads(output.read_text())
            self.assertTrue(receipt['untagged_child_deleted'])
            self.assertTrue(receipt['unrelated_object_retained'])
            self.assertTrue(receipt['shared_mesh_retained'])
            self.assertEqual(receipt['removed'][0], 3)


if __name__ == '__main__':
    if '--scene-probe' in sys.argv:
        scene_probe(sys.argv[sys.argv.index('--scene-probe') + 1])
    else:
        unittest.main()
