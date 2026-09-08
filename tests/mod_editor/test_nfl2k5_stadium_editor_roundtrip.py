"""Source-free SCNE round trips and transactional Blender session imports."""
from __future__ import annotations
from dataclasses import fields, replace
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT/'tools'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from mod_editor.core import nfl2k5_stadium_texture_writer as writer
from mod_editor.core.nfl2k5_stadium_studio import StadiumTexture
from mod_editor.studio.session import StudioSession
from tools.nfl_scne_gltf import append_stadium_texcoords
from nfl_scne_inventory import ScneError
from nfl_txtr import HEADER, encode_rgba_png, compress_vc_lz, decompress_vc_lz, swizzle_2d


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root):
    system = bytes((i*19) % 256 for i in range(256))
    palette = bytes(n for i in range(256) for n in (i, i//2, 255-i, 255))
    # The authored lower mip intentionally is NOT a box-filtered base mip.
    pixel = swizzle_2d(bytes(range(16)), 4, 4, 1) + swizzle_2d(bytes([99]*4), 2, 2, 1)
    decoded = system + (pixel + palette)*2
    encoded, _ = compress_vc_lz(decoded)
    tail = b'opaque-tail'
    span = HEADER.pack(b'SCNE', len(encoded)+len(tail), len(system), len(decoded)-len(system),
                       0xFEEDBEEF, 32, 0, 0) + encoded + tail
    contracts, paths, textures = [], [], []
    for index in range(2):
        values = {field.name: 0 for field in fields(writer.DynamicStadiumP8Contract)}
        identity = f'nfl2k5.stadium.o0042.c0003.scene0077.texture{index:04d}'
        values.update(texture_id=identity, scene_id=identity.rsplit('.texture',1)[0],
                      outer_index=42, outer_id='0x12345678', chunk_index=3, scene_index=77,
                      texture_index=index, width=4, height=4, mip_dimensions=((4,4),(2,2)),
                      format_name='P8', system_bytes=len(system), video_bytes=len(decoded)-len(system),
                      pixel_offset=index*(20+1024), palette_offset=index*(20+1024)+20,
                      mapped_material_names=(f'wall{index}',), mapped_material_count=1,
                      pack_name='8', pack_sha256=sha(b'pack'), decoded_sha256=sha(decoded),
                      source_span_sha256=sha(span), stored_size=len(span)-HEADER.size,
                      retail_consumed=len(encoded), retail_scratch=32,
                      opaque_tail_size=len(tail), opaque_tail_sha256=sha(tail), shared_ownership_note='shared')
        contract = writer.DynamicStadiumP8Contract(**values)
        rgba = writer._decode_dynamic_p8_mips(decoded, contract)[0]
        contract = replace(contract, rgba_sha256=sha(rgba))
        png = root/f'stock-{index}.png'
        png.write_bytes(encode_rgba_png(4,4,rgba))
        source = writer._ResolvedStadiumScene(contract, NS(), span, decoded, tail, ())
        contracts.append(source); paths.append(png)
        textures.append(StadiumTexture(identity, contract.scene_id, index, 4, 4, 'P8', sha(rgba),
                         sha(png.read_bytes()), png, contract.mapped_material_names, 1, 'Editable'))
    return contracts, paths, textures


class NativeRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.sources, self.paths, self.textures = fixture(self.root)

    def test_noop_preserves_all_mips_palette_wrapper_and_compressed_tokens(self):
        with patch.object(writer, '_rebuild_vc_lz_fixed_span', side_effect=AssertionError('no recompress')):
            result = writer._compile_resolved_scene(self.sources, self.paths)
        self.assertEqual(result.fixed.span, self.sources[0].span)
        self.assertEqual(result.decoded_changed_byte_count, 0)
        self.assertTrue(all(row.quantization['unchanged'] == 1 for row in result.textures))
        self.assertEqual(result.textures[0].mip_rgba_sha256,
                         tuple(sha(mip) for mip in writer._decode_dynamic_p8_mips(
                             self.sources[0].decoded, self.sources[0].contract)))

    def test_mixed_noop_and_edit_preserve_unselected_allocation(self):
        self.paths[1].write_bytes(encode_rgba_png(4,4,bytes((2,91,13,255))*16))
        result = writer._compile_resolved_scene(self.sources, self.paths)
        decoded, _ = decompress_vc_lz(result.fixed.span[HEADER.size:], len(self.sources[0].decoded))
        boundary = self.sources[1].contract.system_bytes + self.sources[1].contract.pixel_offset
        self.assertEqual(decoded[:boundary], self.sources[0].decoded[:boundary])
        self.assertGreater(result.decoded_changed_byte_count, 0)
        self.assertEqual(len(result.fixed.span), len(self.sources[0].span))
        self.assertTrue(result.fixed.span.endswith(self.sources[0].opaque_tail))

    def test_oversize_compression_refuses_without_mutating_source(self):
        self.paths[0].write_bytes(encode_rgba_png(4,4,bytes((1,2,3,255))*16))
        original = self.sources[0].span
        with patch.object(writer, '_rebuild_vc_lz_fixed_span', side_effect=writer.StadiumTextureWriterError('cannot fit')):
            with self.assertRaisesRegex(writer.StadiumTextureWriterError, 'cannot fit'):
                writer._compile_resolved_scene(self.sources, self.paths)
        self.assertEqual(self.sources[0].span, original)

    def test_short_stream_can_fill_span_without_excess_loader_scratch(self):
        decoded = bytes(range(64))*64
        header = HEADER.pack(b'SCNE', 2000, 2048, 2048, 0xFEEDBEEF, 32, 0, 0)
        result = writer._rebuild_vc_lz_fixed_span(decoded, header, b'', consumed_cap=2000, scratch_cap=64)
        actual, _ = decompress_vc_lz(result.span[HEADER.size:], len(decoded))
        self.assertEqual(actual, decoded)
        self.assertLessEqual(result.scratch_after, 64)
        self.assertGreaterEqual(result.encoded_bytes, 1984)


class UVTests(unittest.TestCase):
    def source(self):
        decoded = bytearray(512)
        struct.pack_into('<4f', decoded, 0x30, 2.5, 3.5, -0.25, 0.75)
        positions = struct.pack('<9f', *range(9))
        decoded[256:292] = positions
        for i, uv in enumerate(((-32768,32767),(0,-8192),(16384,8192))):
            struct.pack_into('<2h', decoded, 320 + i*8 + 2, *uv)
        shape = dict(index=7, name='wall', record_offset=0, vertex_count=3, transform_count=1,
                     submesh_count=1, morph_channel_count=0,
                     vertex_streams=[dict(stream_index=0, offset=256, stride=12),dict(stream_index=1, offset=320, stride=8)],
                     attribute_descriptors=[dict(register=0, format_name='FLOAT3', stream_index=0, byte_offset=0),
                                            dict(register=6, format_name='NORMSHORT2',stream_index=1,byte_offset=2)])
        document = {'buffers':[{'byteLength':36}], 'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36}],
                    'accessors':[{'bufferView':0,'componentType':5126,'type':'VEC3','count':3}],
                    'meshes':[{'extras':{'source_shape_index':7},'primitives':[{'attributes':{'POSITION':0}}]}]}
        return document, positions, bytes(decoded), {'shapes':[shape]}

    def test_tiling_signed_uvs_without_v_flip_and_prefix_unchanged(self):
        document, binary, decoded, source = self.source()
        result = append_stadium_texcoords(document,binary,decoded,source)
        self.assertEqual(result[:36],binary)
        self.assertEqual(struct.unpack_from('<2f',result,36),(-2.75,4.25))
        self.assertEqual(struct.unpack_from('<2f',result,44),(-0.25,-0.125))
        self.assertFalse(document['extras']['nfl2k5_texcoord_contract']['v_flipped'])
        self.assertEqual(document['meshes'][0]['primitives'][0]['attributes']['POSITION'],0)

    def test_stale_cached_position_and_unknown_source_shape_refuse(self):
        document, binary, decoded, source = self.source()
        with self.assertRaisesRegex(ScneError,'positions differ'):
            append_stadium_texcoords(document,bytes(36),decoded,source)
        document['meshes'][0]['extras']['source_shape_index']=8
        with self.assertRaisesRegex(ScneError,'unknown source shape'):
            append_stadium_texcoords(document,binary,decoded,source)


class SessionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        sources, paths, self.textures = fixture(self.root)
        self.writer = object.__new__(writer.Nfl2k5StadiumTextureWriter)
        self.writer._editable_textures = {row.texture_id: row for row in self.textures}
        self.writer._resolver = NS(resolve_many=lambda ids: tuple(sources[int(i[-4:])] for i in ids))
        self.session = object.__new__(StudioSession)
        self.session.stadium_writer = self.writer
        self.session._stadium_textures = dict(self.writer._editable_textures)
        self.session._stadium_edits = {}
        self.session._stadium_undo = []; self.session._undo_order = []; self.session._history_sequence=0
        self.session.replacements=self.root/'replacements'; self.session.replacements.mkdir()
        self.session.history=self.root/'history'; self.session.history.mkdir()
        self.session._write_manifest=lambda: None
        self.inputs=[]
        for i, texture in enumerate(self.textures):
            path=self.root/f'edit-{i}.png'; path.write_bytes(encode_rgba_png(4,4,bytes((31+i,72,19,255))*16))
            self.inputs.append((texture,path))

    def test_whole_scene_commits_as_one_undo_action(self):
        result=self.session.replace_stadium_textures(tuple(self.inputs))
        self.assertEqual(len(result),2)
        self.assertEqual(len(self.session._stadium_edits),2)
        self.assertEqual(len(self.session._stadium_undo),1)
        self.assertEqual(len(self.session._stadium_undo[0].items),2)

    def test_combined_fit_includes_prior_edit(self):
        self.session.replace_stadium_textures((self.inputs[0],))
        with patch.object(self.writer,'compile_many', wraps=self.writer.compile_many) as compile_many:
            self.session.replace_stadium_textures((self.inputs[1],))
        self.assertEqual({row[0].texture_id for row in compile_many.call_args.args[0]},
                         {row.texture_id for row in self.textures})

    def test_existing_position_recipe_participates_in_combined_fit(self):
        geometry = self.root/'geometry.json'
        self.session._stadium_geometry_edit = NS(scene_id=self.textures[0].scene_id, recipe_path=geometry)
        with patch.object(self.writer, 'compile_many', side_effect=ValueError('preflight')) as compile_many:
            with self.assertRaisesRegex(ValueError, 'preflight'):
                self.session.replace_stadium_textures((self.inputs[0],))
        self.assertEqual(compile_many.call_args.kwargs['geometry_recipe'], geometry)
        self.assertEqual(self.session._stadium_edits, {})

    def test_fit_failure_keeps_prior_edit_files_and_history(self):
        self.session.replace_stadium_textures((self.inputs[0],))
        previous=dict(self.session._stadium_edits)
        files={p:p.read_bytes() for p in self.session.replacements.iterdir()}
        with patch.object(self.writer,'compile_many',side_effect=ValueError('fit failed')):
            with self.assertRaisesRegex(ValueError,'fit failed'):
                self.session.replace_stadium_textures(tuple(self.inputs))
        self.assertEqual(self.session._stadium_edits,previous)
        self.assertEqual({p:p.read_bytes() for p in self.session.replacements.iterdir()},files)
        self.assertEqual(len(self.session._stadium_undo),1)

    def test_manifest_failure_rolls_back_staged_files_and_history(self):
        self.session.replace_stadium_textures((self.inputs[0],))
        before=dict(self.session._stadium_edits)
        files={p:p.read_bytes() for p in self.session.replacements.iterdir()}
        self.session._write_manifest=lambda: (_ for _ in ()).throw(OSError('disk full'))
        with self.assertRaisesRegex(OSError,'disk full'):
            self.session.replace_stadium_textures(tuple(self.inputs))
        self.assertEqual(self.session._stadium_edits,before)
        self.assertEqual({p:p.read_bytes() for p in self.session.replacements.iterdir()},files)
        self.assertEqual(list(self.session.history.iterdir()),[])
        self.assertEqual(len(self.session._stadium_undo),1)


class NativeOwnershipEvidenceTests(unittest.TestCase):
    def test_culling_consumers_replay_but_do_not_claim_part_ownership(self):
        import json
        import os
        from tools.xbe_info import Xbe
        from tools.nfl_scne_bounds_ownership import executable_evidence
        source = Path(os.environ.get('NFL2K5_RETAIL_XBE',
            '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))
        if not source.is_file():
            self.skipTest('Retail USA default.xbe is absent; set NFL2K5_RETAIL_XBE for the native ownership audit')
        expected = json.loads((ROOT/'docs/mod_editor/nfl2k5_stadium_part_ownership.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            header = Path(temporary).resolve()/'header.json'
            header.write_text(json.dumps(Xbe(source).report()))
            actual = executable_evidence(source, header)
        self.assertEqual(actual['function_ranges'], expected['function_ranges'])
        self.assertEqual(actual['proved_dataflow'], expected['proved_dataflow'])
        self.assertFalse(expected['runtime_independent_parts_proved'])
        self.assertFalse(expected['transforms_write_back'])


if __name__=='__main__':
    unittest.main()
