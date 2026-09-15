"""Venue identification, exact banner writes and bounded native binding."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
from tools.b70_t2_stadium_probe import writer as w, RETAIL, CACHE, native_binding, native
from mod_editor.core.nfl2k5_stadium_studio import Nfl2k5StadiumStudio
from nfl_txtr import decode_chunk, parse_chunks, encode_rgba_png
XISO = Path(os.environ.get('NFL2K5_RETAIL_XISO', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))


class IdentityTests(unittest.TestCase):
    def test_crc_identity_and_unknown_refusal(self):
        for name, venue in (('s05dd.iff', 'Chicago Field'), ('s06nr.iff', 'Paul Brown Stadium')):
            identity = w.stadium_package_identity(hex(zlib.crc32(name.upper().encode('utf-16le'))))
            self.assertEqual(identity['filename'], name)
            self.assertEqual(identity['venue'], venue)
        self.assertEqual(w.stadium_package_identity('garbage'), {})
        self.assertEqual(w.stadium_package_identity('0xdeadbeef'), {})


@unittest.skipUnless(native.Uc and (RETAIL/'default.xbe').is_file() and
                     (CACHE/'indexes/nfl2k5_resource_chunks_v2.json').is_file(),
                     'Requires private retail files, inventory, Stadium cache and Unicorn')
class RetailBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = w._DynamicStadiumResolver(RETAIL/'vc_53450030/0', CACHE/'indexes/nfl2k5_resource_chunks_v2.json')

    def test_chicago_cincinnati_banner_write_reopen_native_material_binding(self):
        if not XISO.is_file():
            self.skipTest('Private source XISO is absent')
        from mod_editor.core.model import SourceRecord
        from mod_editor.core.nfl2k5_source_cache import SourceCache
        from mod_editor.studio.session import StudioSession
        source_record = SourceRecord(str(XISO), str(XISO), 'xiso', w.SOURCE_SHA256, XISO.stat().st_size,
                                     True, 'nfl2k5-usa-retail-xiso')
        cache = SourceCache(source_record, CACHE, RETAIL/'vc_53450030/0',
                            CACHE/'indexes/nfl2k5_resource_chunks_v2.json', CACHE/'originals',86882,4323,{})
        folder = CACHE/'derived/stadium-studio-v1'
        stadium_cache = SimpleNamespace(root=folder,texture_manifest=folder/'textures/manifest.json',
                                        texture_root=folder/'textures',private=True,shareable=False)
        product = w.Nfl2k5StadiumTextureWriter(cache,stadium_cache)
        results = []
        for selector, filename in (
            ('nfl2k5.stadium.o3141.c0006.scene1998.texture0042', 's05dd.iff'),
            ('nfl2k5.stadium.o3142.c0005.scene2003.texture0029', 's06dd.iff'),
        ):
            source = self.resolver.resolve(selector)
            c = source.contract
            rgba = b''.join(bytes((255,0,255,255) if (x//32)%2 else (250,250,250,255))
                            for y in range(c.height) for x in range(c.width))
            with tempfile.TemporaryDirectory(prefix='b70-banner-') as directory:
                path = Path(directory)/'authored.png'
                path.write_bytes(encode_rgba_png(c.width,c.height,rgba))
                session = StudioSession(cache,SimpleNamespace(),root=Path(directory)/'sessions')
                session.attach_stadium_texture(product,product.texture(w.TARGET_TEXTURE_ID))
                studio = Nfl2k5StadiumStudio(folder/'models/manifest.json',folder/'textures/manifest.json',
                                            folder/'textures',edit_delegate=session.stadium_delegate)
                texture = next(t for t in studio.scene_details(c.scene_id).textures if t.texture_id==selector)
                self.assertEqual(texture.access_status,'Editable')
                captured = []
                compile_many = product.compile_many
                def capture(*args,**kwargs):
                    rows = compile_many(*args,**kwargs)
                    captured.extend(rows)
                    return rows
                with patch.object(product,'compile_many',side_effect=capture):
                    staged = studio.replace_texture(selector,path)
                self.assertTrue(staged.modified)
                self.assertIn(selector,session._stadium_edits)
                self.assertEqual(len(captured),1)
                compiled = captured[0]
                self.assertEqual(compiled.public_metadata()['compiled_occurrences'][0]['selector'],selector)
                # Small disposable span, no pack/disc copy. Close/reopen before decode.
                stored = Path(directory)/'span.bin'
                stored.write_bytes(b'GUARD' + compiled.rebuilt_span + b'GUARD')
                readback = stored.read_bytes()
                self.assertEqual(readback[:5], b'GUARD')
                self.assertEqual(readback[-5:], b'GUARD')
                span = readback[5:-5]
                self.assertEqual(len(span), len(source.span))
                self.assertNotEqual(span, source.span)
                decoded, _ = decode_chunk(span, parse_chunks(span)[0])
                self.assertEqual(w._decode_dynamic_p8_mips(decoded,c)[0], rgba)
                # Entire SCNE parser and native texture/material binding retain identity.
                binding = native_binding(source, decoded)
                self.assertEqual(self.resolver.resolve(selector).span, source.span)
                metadata = c.target_metadata()
                self.assertEqual(metadata['stadium_package']['filename'], filename)
                results.append(dict(selector=selector, metadata=metadata,
                    stored_bytes=len(span), encoded_bytes=compiled.encoded_bytes,
                    decoded_changed_bytes=compiled.decoded_changed_byte_count,
                    editable_delegate_staged=True,reopened_base_rgba_exact=True, native=binding, in_game_outcome='UNWITNESSED'))
                self.assertTrue(studio.revert_texture(selector))
                self.assertNotIn(selector,session._stadium_edits)
        print(json.dumps(results,indent=2))

    def test_existing_scene_selector_identifies_and_searches_all_variants(self):
        cache = CACHE/'derived/stadium-studio-v1'
        if not (cache/'models/manifest.json').is_file():
            self.skipTest('Private Stadium Studio export cache is absent')
        studio = Nfl2k5StadiumStudio(cache/'models/manifest.json',cache/'textures/manifest.json',cache/'textures')
        for search, filename in (('Chicago Field', 's05dd.iff'), ('Paul Brown Stadium', 's06dd.iff')):
            rows = studio.list_scenes(search=search)
            self.assertEqual(len(rows),9)
            self.assertTrue(any(filename in r.label for r in rows))
        self.assertEqual(len({r.label for r in studio.list_scenes()}),477)


if __name__ == '__main__':
    unittest.main()
