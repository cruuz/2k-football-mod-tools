"""Original-index errors and historical equipment records, through real builds."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
import b661_build_fixture as fixture
from test_b68_t1_build import backend
from mod_editor.core import nfl2k5_build_service as service
from nfl_txtr import encode_rgba_png, decode_chunk, parse_chunks


def legacy_png(asset_id, rgba, *, independent=True):
    # adb037c0 (beta 62), unchanged through beta 65: npTC/v1, scale=1;
    # 93e1f6a7 (RC49): ordinary PNG, with no intent record or stored mip bytes.
    png = encode_rgba_png(32, 32, rgba)
    if not independent:
        return png
    record = json.dumps(dict(schema='nfl2k5_equipment_import_intent/v1',
        asset_id=asset_id, mode='independent-mip-chain',
        rgba_sha256=hashlib.sha256(rgba).hexdigest(), scale=1),
        sort_keys=True, separators=(',', ':')).encode()
    chunk = struct.pack('>I4s', len(record), b'npTC') + record
    chunk += struct.pack('>I', zlib.crc32(b'npTC' + record) & 0xffffffff)
    return png[:-12] + chunk + png[-12:]


class BuildDiagnosticsTests(unittest.TestCase):
    def test_refusing_edit_reaches_service_without_progress_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            equipment, _ = fixture.create(root)
            tool = backend()
            fixture.configure(tool, root)
            bad = root / 'orange-shoes.png'
            bad.write_bytes(encode_rgba_png(16, 16, bytes((255, 90, 0, 255))*256))
            project = root / 'project.json'
            project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA, purpose='refusal proof',
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND,
                            asset_id=equipment.rows[0].asset_id, png=str(bad))])))
            class Runner:
                def run(self, argv, cwd):
                    command = [sys.executable, str(Path(fixture.__file__)), str(root), *argv[2:]]
                    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=30)
                    return service.CommandResult(tuple(command), result.returncode, result.stdout, result.stderr)
            cache = SimpleNamespace(pack0=root/'0', inventory=root/'inventory.json')
            builder = service.Nfl2k5BuildService(runner=Runner())
            with patch.object(builder, '_validate_cache', return_value=root/'source.iso'), \
                 patch.object(service, '_require_build_space'), \
                 self.assertRaises(service.Nfl2k5BuildError) as caught:
                builder.build(cache, project, root/'out.iso')
            message = str(caught.exception)
            for text in ('compiling project edits', 'Project edit index 0', 'Equipment / Shoes',
                         'SYNTHETIC', 'shoes01', '32'):
                self.assertIn(text, message)
            self.assertNotIn('NFL2K5_', message)
            self.assertFalse((root/'out.iso').exists())
            print(message)

    def test_legacy_palette_and_own_texture_records_load_build_and_verify(self):
        for independent in (False, True):
            with self.subTest(independent=independent), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                equipment, _ = fixture.create(root)
                tool = backend(); fixture.configure(tool, root)
                rgba = bytes((250, 190, 10, 255))*(32*32)
                png = root/'legacy.png'; asset = equipment.rows[0].asset_id
                png.write_bytes(legacy_png(asset, rgba, independent=independent))
                project = root/'project.json'
                project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA, purpose='legacy',
                    edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
                self.assertEqual(tool.read_project(project, equipment_index=root/'0').value['edits'][0]['asset_id'], asset)
                with contextlib.redirect_stdout(io.StringIO()):
                    result = tool.build(project, root/'source.iso', root/'out.iso', root/'receipt.json',
                        root/'artifacts', root/'0', root/'inventory.json')
                verified = tool.verify_written(project, root/'source.iso', root/'out.iso',
                    root/'receipt.json', root/'artifacts', tool.file_digest(root/'receipt.json'))
                self.assertTrue(verified['written_spans_verified'])
                self.assertEqual(result['project']['includes'][0]['project_edit_index'], 0)
                span = result['edits'][0]
                start = span['target']['absolute_span_offset']
                data = (root/'out.iso').read_bytes()[start:start+span['replacement']['span_size']]
                chunk = parse_chunks(data)[0]
                self.assertEqual(chunk.video_bytes > equipment.chunk.video_bytes, independent)

    def test_invalid_legacy_own_art_is_refused_during_project_load(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            equipment, _ = fixture.create(root)
            tool = backend(); fixture.configure(tool, root)
            asset = equipment.rows[0].asset_id
            rgba = bytes((255, 120, 0, 255))*(32*32)
            png = root/'legacy.png'
            # A real old record with a digest belonging to different pixels.
            payload = legacy_png(asset, rgba)
            digest = hashlib.sha256(rgba).hexdigest().encode()
            payload = payload.replace(digest, b'0'*64)
            # Recompute the ancillary chunk CRC, as an old record writer did.
            cursor = payload.index(b'npTC')
            length = struct.unpack_from('>I', payload, cursor-4)[0]
            payload = bytearray(payload)
            struct.pack_into('>I', payload, cursor+4+length,
                zlib.crc32(payload[cursor:cursor+4+length]) & 0xffffffff)
            png.write_bytes(payload)
            project = root/'project.json'
            project.write_bytes(tool.canonical_json(dict(schema=tool.SCHEMA, purpose='invalid legacy',
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
            with patch.object(tool, 'validate_source', side_effect=AssertionError('started disc validation')), \
                 self.assertRaisesRegex(ValueError, 'Cannot load equipment edits:.*shoes01.*no longer matches'):
                tool.read_project(project, equipment_index=root/'0')
            self.assertFalse((root/'out.iso').exists())

    def test_stderr_precedes_stdout_and_long_reason_is_not_cut(self):
        reason = 'While writing project edits: Project edit index 401: ' + 'x'*700 + ' choose another image'
        result = service.CommandResult((), 1, 'NFL2K5_BUILD_PHASE copy seconds=1.2\n', 'error: '+reason+'\n')
        self.assertEqual(service._last_message(result), reason)
        self.assertNotIn('NFL2K5_', service._last_message(service.CommandResult((), 1,
            'NFL2K5_BUILD_PHASE compile seconds=1\n', '')))


if __name__ == '__main__':
    unittest.main()
