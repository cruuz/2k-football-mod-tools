"""Standalone optional retail family census and independent compiler checks."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests')]
from PIL import Image
from nfl2k5_xiso_fixture import SyntheticXiso
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_hires_texture as texture
from mod_editor.core import nfl2k5_hires_budget as budget
from mod_editor.core import nfl2k5_music_archive as archive
from tools.nfl2k5_hires_acceptance import artwork

SOURCE = Path(os.environ.get('NFL2K5_HIRES_TEST_IMAGE',
    '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))


class RetailFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest('Retail NFL 2K5 XISO absent; set NFL2K5_HIRES_TEST_IMAGE to the retail evidence copy')

    def test_complete_catalog_pins_and_unique_resource_identities(self):
        self.assertEqual(Counter(pack.asset_family(a) for a in texture.ASSETS),
                         dict(scorebug=2, helmets=64, jerseys=64, numbers=1920, field_logos=126, stock_fields=348))
        self.assertEqual(len({(a.outer, a.chunk) for a in texture.ASSETS}), len(texture.ASSETS))
        self.assertEqual(len(texture.BY_KEY), 2524)
        kits = {a.kit for a in texture.ASSETS if a.family == 'jerseys'}
        self.assertEqual(kits, {f'{i:02d}{side}0' for i in range(32) for side in 'ha'})
        self.assertEqual(sum(a.kind == 'SCNE' and a.native != a.height for a in texture.ASSETS), 9)
        wanted = {(a.outer,a.chunk): a for a in texture.ASSETS}
        seen = set()
        with archive.Disc(SOURCE, descriptors=()) as disc:
            for outer in sorted({a.outer for a in texture.ASSETS}):
                e = disc.archive_entries[outer]
                self.assertLess(e.size, 32*archive.BLOCK)
                for chunk, _, raw in archive.chunks(disc.read_entry_range(e,0,e.size)):
                    a = wanted.get((outer,chunk))
                    if a:
                        self.assertEqual(e.name_id, a.name_id)
                        self.assertEqual(texture.sha(raw), a.retail_sha256, a.key)
                        seen.add((outer,chunk))
        self.assertEqual(seen, set(wanted))

    def test_real_layout_native_2x_roundtrip_and_exact_budget(self):
        # Every layout/size class, including the rectangular stock midfield art.
        selected = {}
        for a in texture.ASSETS:
            selected.setdefault((pack.asset_family(a), a.native, a.height, a.levels), a)
        with archive.Disc(SOURCE, descriptors=()) as disc:
            raw, _ = pack._read(disc, [a.key for a in selected.values()])
        for a in selected.values():
            with self.subTest(key=a.key):
                before, base = texture.inspect_span(raw[a.key], a)
                rgba = artwork(a.native*2, a.height*2)
                if a.kind == 'TSET':
                    rgba = (rgba, artwork(a.native*2, a.height*2, True))
                outputs = {}
                for scale in (1,2):
                    output, rec = texture.compile_texture(base,rgba,a,scale)
                    after, restored = texture.inspect_span(output,a)
                    self.assertEqual(restored, base)
                    self.assertEqual(after, rec['decoded'])
                    self.assertEqual(after['scale'], scale)
                    self.assertEqual(len(after['mips']), a.levels*a.palette_count)
                    self.assertEqual(rec['quality']['maximum_channel_error'], 0)
                    outputs[scale] = output
                restored = texture.inspect_span(outputs[1],a)[1]
                self.assertEqual(texture.compile_texture(restored,rgba,a,2)[0],outputs[2])
        report = budget.model(texture.ASSETS)
        self.assertEqual(report['budget_status'], 'unproved')
        self.assertIsNone(report['headroom_bytes'])
        self.assertFalse(report['whole_game_fit_proved'])
        self.assertLess(report['modeled_output_bytes'], report['arena_upper_bound_bytes'])

    def test_22_name_surfaces_remain_native_and_source_hashes_match(self):
        report = json.loads((ROOT/'reports/hires_player_names.v2.json').read_text())
        self.assertEqual(len(report['assets']), 22)
        with archive.Disc(SOURCE, descriptors=()) as disc:
            e = disc.archive_entries[3]
            self.assertLess(e.size, 32*archive.BLOCK)
            chunks = {c:raw for c,_,raw in archive.chunks(disc.read_entry_range(e,0,e.size))}
            total = 0
            for row in report['assets']:
                raw = chunks[row['chunk']]
                self.assertEqual(texture.sha(raw), row['span_sha256'])
                h = texture.txtr.HEADER.unpack_from(raw)
                self.assertEqual((h[2], h[3], h[5]), (128,11776,16))
                total += budget.allocation(h[2]+h[3]+h[5])
            self.assertEqual(total, budget.PLAYER_NAMES)

    def test_real_outer_contents_through_bounded_archive_transaction(self):
        # Real resource bytes inside a small synthetic disc. Retain complete
        # outers so untouched chunks are independently verified by the writer.
        keys = ['helmet', 'jersey_00h0', 'number_00h0_jersey_7', 'scorebug', 'scorebug_espn']
        keys.append(next(a.key for a in texture.ASSETS if a.kind == 'SCNE' and a.native != a.height))
        selected = [texture.BY_KEY[k] for k in keys]
        outers = sorted({a.outer for a in selected})
        with archive.Disc(SOURCE, descriptors=()) as disc:
            consumers = pack._consumer_check(disc, keys)
            containers = [(disc.archive_entries[o].name_id, disc.read_entry_range(
                disc.archive_entries[o], 0, disc.archive_entries[o].size)) for o in outers]
        self.assertLess(sum(len(raw) for _, raw in containers), 15*archive.BLOCK)
        assets = tuple(replace(a, outer=outers.index(a.outer)) for a in selected)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            folder = root/'art'
            folder.mkdir()
            for a in assets:
                for mud in ((False, True) if a.kind == 'TSET' else (False,)):
                    Image.frombytes('RGBA', (a.native*2,a.height*2),
                                    artwork(a.native*2,a.height*2,mud)).save(
                        folder/(a.key+('.mud' if mud else '')+'.png'))
            fixture = SyntheticXiso(root, containers+[(0x1234,b'unselected')],
                                    pack_sizes=(archive.BLOCK,)*16,
                                    pack_sectors=tuple(64+512*i for i in range(16)))
            original = archive.file_hash(fixture.path)
            with patch.object(pack,'ASSETS',assets), patch.object(texture,'ASSETS',assets), \
                 patch.object(texture,'BY_KEY',{a.key:a for a in assets}), \
                 patch.object(pack,'_consumer_check',return_value=consumers):
                output = root/'authored.iso'
                result = pack.build_image(fixture.path,output,folder)
                self.assertEqual(result['verification']['status'],'verified')
                self.assertEqual(result['verification']['unchanged_outers'],1)
                self.assertEqual(len(result['verification']['decoded']),len(assets))
                self.assertEqual(archive.file_hash(fixture.path),original)
                with archive.Disc(fixture.path,descriptors=()) as old, archive.Disc(output,descriptors=()) as new:
                    for outer in range(len(outers)):
                        before = list(archive.chunks(old.read_entry_range(old.archive_entries[outer],0,old.archive_entries[outer].size)))
                        after = list(archive.chunks(new.read_entry_range(new.archive_entries[outer],0,new.archive_entries[outer].size)))
                        self.assertEqual(len(before),len(after))
                        owned = {a.chunk for a in assets if a.outer == outer}
                        for (chunk,_,raw), (index,_,changed) in zip(before,after):
                            self.assertEqual(chunk,index)
                            if chunk not in owned: self.assertEqual(raw,changed)

    def test_consumer_pins_compose_and_scorebug_conflict_refuses_both_orders(self):
        from tests.mod_editor import test_xbe_patch_memory_writes as gate
        from mod_editor.core import nfl2k5_scorebug_ingame as reference
        if not gate.XBE.is_file() or gate.Cs is None:
            self.skipTest('Retail extracted XBE or capstone absent for complete-owner composition')
        # Reuse the exact existing gate setup, including the v3 scale-out union
        # and all preceding/following executable owners, without adding an owner.
        for cls in (gate.ScaleoutOwnerTests, gate.ScaleoutReverseOwnerTests):
            with self.subTest(order=cls.__name__):
                cls.setUpClass()
                keys = tuple(a.key for a in texture.ASSETS if pack.asset_family(a) != 'scorebug')
                result = pack.validate_consumer_xbe(cls.patched, keys)
                self.assertGreater(len(result['ranges']),30)
                self.assertFalse(result['runtime_witnessed'])
                self.assertEqual(reference.xbe_status(cls.patched),'applied')
                # The reference scorebug deliberately changes this binding
                # table. A different consumer recipe must not pass as retail.
                with self.assertRaisesRegex(ValueError,'Foreign scorebug consumer at 0x00a95c60'):
                    pack.validate_consumer_xbe(cls.patched, tuple(texture.BY_KEY))


if __name__ == '__main__':
    unittest.main()
