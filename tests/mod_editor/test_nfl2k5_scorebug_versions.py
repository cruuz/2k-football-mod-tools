"""Both complete scene identities, independent pins and cross-version refusal."""
from __future__ import annotations

import itertools
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as r
from mod_editor.core import nfl2k5_scorebug_template as t

EXTRACTION = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'


@unittest.skipUnless((EXTRACTION / 'default.xbe').is_file() and
                     (EXTRACTION / 'vc_53450030/0').is_file(),
                     'pinned USA default.xbe and pack 0 required')
class VersionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = (EXTRACTION / 'default.xbe').read_bytes()
        cls.spans = {}
        with (EXTRACTION / 'vc_53450030/0').open('rb') as f:
            for name in ('score_bug', 'score_buga'):
                rec = r.RESOURCES[name]
                f.seek(rec['pack_offset'])
                cls.spans[name] = f.read(rec['span_size'])
        cls.folders = (None, t.DEFAULT_FOLDER)
        cls.pairs = [(r.apply_xbe(cls.xbe, scorebug_folder=folder)[0],
                      {name: r.apply(span, name, scorebug_folder=folder)[0]
                       for name, span in cls.spans.items()}) for folder in cls.folders]

    def test_template_has_the_independent_landed_xbe_and_resource_hashes(self):
        xbe, spans = self.pairs[1]
        self.assertEqual(r.digest(xbe), '0d0eee5163c1d5edbc41a8a0a522f3c55d74e9c5699f078aab37bd9e01b8d23f')
        self.assertEqual(r.digest(spans['score_bug']), '8bf58e95bdc4ddbfe627ee705165f7a639d5ba033dc3d6c9732f622ef3e364f2')
        self.assertEqual(r.digest(spans['score_buga']), 'a208b56329eec1dc285dfc8f04dcf66883b62d502c549ed70583d2fb7b0b1609')
        staged, receipt = r.stage_binding_scene(self.spans['score_bug'], scorebug_folder=t.DEFAULT_FOLDER)
        self.assertEqual(staged, spans['score_bug'])
        self.assertEqual(receipt['version'], r.TEMPLATE_VERSION)

    def test_xbe_readers_recognize_both_but_writers_refuse_cross_version_replay(self):
        for i, (xbe, spans) in enumerate(self.pairs):
            self.assertEqual(r.xbe_version(xbe), (r.VERSION, r.TEMPLATE_VERSION)[i])
            self.assertEqual(r.xbe_status(xbe), 'applied')
            self.assertEqual(r.apply_xbe(xbe, scorebug_folder=self.folders[i])[0], xbe)
            with self.assertRaises(r.ScorebugError):
                r.apply_xbe(xbe, scorebug_folder=self.folders[1-i])
            for name, span in spans.items():
                self.assertEqual(r.status(span, name), 'applied')
                self.assertEqual(r.apply(span, name, scorebug_folder=self.folders[i])[0], span)
                with self.assertRaises(r.ScorebugError):
                    r.apply(span, name, scorebug_folder=self.folders[1-i])

    def test_each_foreign_version_field_refuses_including_other_versions_extra_fields(self):
        exact = {va: new for va, _, new, _ in r.xbe_specs()}
        template = {va: new for va, _, new, _ in r.xbe_specs(scorebug_folder=t.DEFAULT_FOLDER)}
        old = {va: before for va, before, _, _ in r.xbe_specs()}
        for i, (xbe, _) in enumerate(self.pairs):
            own, other = (exact, template) if i == 0 else (template, exact)
            for va in exact.keys() | template.keys():
                value = other.get(va, old[va])
                if value == own.get(va, old[va]):
                    continue
                changed = bytearray(xbe)
                off = r.layout.sbpos.va_to_off(xbe, va)
                changed[off:off+len(value)] = value
                self.assertEqual(r.xbe_status(bytes(changed)), 'foreign', hex(va))

    def test_all_resource_xbe_combinations_and_preview_select_the_same_scene(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        base, xoff = 4096, 4096 + r.PACK_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / 'sparse.iso'
            with (mock.patch.object(r.layout.xc, 'pack_extent', return_value=(base, r.PACK_SIZE)),
                  mock.patch.object(tt, 'image_xbe_extent', return_value=(xoff, len(self.xbe)))):
                for indices in itertools.product(range(2), repeat=3):
                    with path.open('wb') as f:
                        for n, index in zip(('score_bug', 'score_buga'), indices[:2]):
                            f.seek(base + r.RESOURCES[n]['pack_offset'])
                            f.write(self.pairs[index][1][n])
                        f.seek(xoff); f.write(self.pairs[indices[2]][0])
                    coherent = len(set(indices)) == 1
                    self.assertEqual(r.image_status(path), 'applied' if coherent else 'foreign', indices)
                    for i, folder in enumerate(self.folders):
                        with path.open('rb') as f:
                            if coherent and indices[0] == i:
                                jobs, receipt = r.image_plan(f.fileno(), path.stat().st_size, scorebug_folder=folder)
                                self.assertTrue(all(before == after for _, before, after in jobs))
                                self.assertEqual(receipt['layout'], (r.VERSION, r.TEMPLATE_VERSION)[i])
                            else:
                                with self.assertRaisesRegex(r.ScorebugError, 'mixed or foreign'):
                                    r.image_plan(f.fileno(), path.stat().st_size, scorebug_folder=folder)
                    if coherent:
                        mesh, atlas = r.preview_data(path, scorebug_folder=self.folders[indices[0]])
                        anchor = (r.ANCHORS, r.V10['ANCHORS'])[indices[0]]['drop_down']
                        self.assertEqual(tuple(mesh.world[r.layout.T['drop_down']]),
                                         struct.unpack('<3f', struct.pack('<3f', *anchor)))
                        for n in ('score_bug', 'score_buga'):
                            self.assertEqual(struct.unpack_from('<I', self.pairs[indices[0]][1][n], 20)[0], 16)


if __name__ == '__main__':
    unittest.main()
