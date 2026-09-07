"""Standalone bounded family compiler, memory refusal and archive tests."""
from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'tests/mod_editor')]
from PIL import Image
from nfl2k5_xiso_fixture import SyntheticXiso
from mod_editor.core import nfl2k5_hires_texture as texture
from mod_editor.core import nfl2k5_hires_layouts as layouts
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_hires_budget as budget
from mod_editor.core import nfl2k5_music_archive as archive


def encode(data, asset, video):
    compressed, _ = texture.txtr.compress_vc_lz(data, stream_tag=asset.stream_tag, offset_bits=asset.offset_bits)
    stored = (len(compressed)+15) & ~15
    scratch = (max(stored-len(compressed), stored-len(data),
                   texture.txtr.minimum_vc_lz_overlap_scratch(compressed, stored, len(data)))+15) & ~15
    return texture.txtr.HEADER.pack(asset.kind.encode(), stored, asset.system_size, video,
                                   texture.txtr.COMPRESSED_SENTINEL, scratch, 0, 0)+compressed+bytes(stored-len(compressed))


def resources():
    from test_nfl2k5_hires_pack import fixtures
    ordinary, spans = fixtures()
    # Retain one ordinary resource plus a paired jersey and a scene logo.
    first = replace(ordinary[0], key='scorebug', family='scorebug', chunk=0)
    assets = [first]
    result = {first.key: spans['scorebug']}
    for i, kind in enumerate(('TSET', 'SCNE'), 1):
        a = replace(first, key='jersey_fixture' if kind == 'TSET' else 'field_fixture',
                    name='jersey00' if kind == 'TSET' else 'center_logo', outer=i, name_id=100+i,
                    native=16, native_height=8, levels=3, descriptor=64, second_descriptor=88 if kind == 'TSET' else 0,
                    family='jerseys' if kind == 'TSET' else 'stock_fields', kind=kind, system_size=256,
                    original_video=1536 if kind == 'SCNE' else 0,
                    original_pixels=128 if kind == 'SCNE' else 0,
                    original_palette=296 if kind == 'SCNE' else 0)
        system = bytearray(256)
        chain = a.video_size(1)-1024*a.palette_count
        descriptors = (64, 88) if kind == 'TSET' else (64,)
        for p, at in enumerate(descriptors):
            struct.pack_into('<6I', system, at, 0, a.original_pixels,
                             a.original_palette if kind == 'SCNE' else chain+p*1024,
                             a.format_word(1), 0, 0x80000000)
        video = a.original_video or a.video_size(1)
        baseline = bytes(system)+bytes(video)
        a = replace(a, system_sha256=texture.sha(system),
                    baseline_sha256=texture.sha(baseline) if kind == 'SCNE' else '')
        raw = encode(baseline, a, video)
        a = replace(a, retail_sha256=texture.sha(raw))
        texture.inspect_span(raw, a)
        assets.append(a)
        result[a.key] = raw
    return tuple(assets), result


def artwork(path, asset, mud=False):
    image = Image.new('RGBA', (asset.native*2, asset.height*2))
    image.putdata([((x//8%2)*128, (y//8%2)*128, 40 if mud else 240, 255)
                   for y in range(asset.height*2) for x in range(asset.native*2)])
    image.save(path)


class FamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root/'art'
        self.folder.mkdir()
        self.assets, self.raw = resources()
        for obj, key, value in ((texture, 'ASSETS', self.assets), (pack, 'ASSETS', self.assets),
                                (texture, 'BY_KEY', {a.key: a for a in self.assets}),
                                (texture, 'PILOT_ASSETS', self.assets)):
            context = patch.object(obj, key, value)
            context.start()
            self.addCleanup(context.stop)
        for a in self.assets:
            artwork(self.folder/(a.key+'.png'), a)
            if a.kind == 'TSET':
                artwork(self.folder/(a.key+'.mud.png'), a, True)

    def test_all_layouts_replay_native_reupgrade_and_rectangular_mips(self):
        enlarged, receipt = pack.apply(self.raw, self.folder)
        self.assertEqual(pack.apply(enlarged, self.folder)[0], enlarged)
        native, _ = pack.apply(enlarged, self.folder, scale=1)
        self.assertEqual(pack.apply(native, self.folder)[0], enlarged)
        self.assertFalse(receipt['memory']['whole_game_fit_proved'])
        self.assertIsNone(receipt['memory']['headroom_bytes'])
        for a in self.assets[1:]:
            info, baseline = texture.inspect_span(enlarged[a.key], a)
            self.assertEqual([(m['width'], m['height']) for m in info['mips'][:3]], [(32,16), (16,8), (8,4)])
            if a.kind == 'SCNE':
                self.assertEqual(texture.sha(baseline), a.baseline_sha256)
                self.assertEqual(info['video_bytes'], 1536+a.video_size(2))
            else:
                self.assertEqual(len(info['mips']), 6)
                for clean, mud in zip(info['mips'][:3], info['mips'][3:]):
                    self.assertEqual(clean['index_sha256'], mud['index_sha256'])
                    self.assertNotEqual(clean['rgba_sha256'], mud['rgba_sha256'])

    def test_scene_preserves_all_original_bytes_except_selected_descriptor(self):
        a = self.assets[2]
        _, baseline = texture.inspect_span(self.raw[a.key], a)
        rgba = pack.load_folder(self.folder)[a.key][0]
        raw, _ = texture.compile_texture(baseline, rgba, a, 2)
        decoded, _ = texture.txtr.decode_chunk(raw, texture.txtr.parse_chunks(raw)[0])
        self.assertEqual(decoded[:a.descriptor+4], baseline[:a.descriptor+4])
        self.assertEqual(decoded[a.descriptor+16:len(baseline)], baseline[a.descriptor+16:])
        changed = bytearray(decoded)
        changed[-1] ^= 1
        foreign = encode(bytes(changed), a, len(changed)-a.system_size)
        with self.assertRaisesRegex(ValueError, 'foreign artwork'):
            pack.apply({**self.raw, a.key: foreign}, self.folder)
        changed[300] ^= 1
        foreign = encode(bytes(changed), a, len(changed)-a.system_size)
        with self.assertRaisesRegex(ValueError, 'scene baseline'):
            texture.inspect_span(foreign, a)

    def test_foreign_shared_descriptor_and_scratch_refuse_before_encoding(self):
        a = self.assets[1]
        _, baseline = texture.inspect_span(self.raw[a.key], a)
        wrong = bytearray(baseline)
        struct.pack_into('<I', wrong, a.second_descriptor+4, 128)
        bad = encode(bytes(wrong)+bytes(a.video_size(1)), a, a.video_size(1))
        with patch.object(texture, 'compile_texture') as compiler:
            with self.assertRaisesRegex(ValueError, 'descriptor'):
                pack.apply({**self.raw, a.key: bad}, self.folder)
            compiler.assert_not_called()
        for a in self.assets[1:]:
            for offset, value in ((8, 0xffffffff), (12, 0xffffffff), (20, 0), (24, 1)):
                bad = bytearray(self.raw[a.key])
                struct.pack_into('<I', bad, offset, value)
                with self.subTest(kind=a.kind, offset=offset), self.assertRaises(ValueError):
                    texture.inspect_span(bytes(bad), a)

    def test_family_filters_unknown_inputs_pairs_and_input_races(self):
        selected = pack.load_folder(self.folder, families=['jerseys'])
        self.assertEqual(list(selected), ['jersey_fixture'])
        self.assertEqual(len(selected.input_details()), 2)
        (self.folder/'jersey_fixture.mud.png').unlink()
        with self.assertRaisesRegex(ValueError, 'both clean'):
            pack.load_folder(self.folder)
        self.assertEqual(list(pack.load_folder(self.folder, families=['scorebug'])), ['scorebug'])
        (self.folder/'names.png').write_bytes(b'not accepted')
        with self.assertRaisesRegex(ValueError, 'Unknown Hi-res artwork'):
            pack.load_folder(self.folder, families=['scorebug'])
        (self.folder/'names.png').unlink()
        selected = pack.load_folder(self.folder, families=['scorebug'])
        Image.new('RGBA', (32,32), 'red').save(self.folder/'scorebug.png')
        with self.assertRaisesRegex(ValueError, 'changed after preflight'):
            selected['scorebug']
        for families in ([], ['unknown'], ['scorebug','scorebug'], 'scorebug'):
            with self.subTest(families=families), self.assertRaises(ValueError):
                pack.load_folder(self.folder, families=families)

    def test_memory_alignment_boundaries_and_refusal_before_encode(self):
        self.assertEqual([budget.allocation(n) for n in (0, 1, 127, 128, 129)], [128, 256, 256, 256, 384])
        for invalid in (-1, True, 1.5):
            with self.assertRaises(ValueError): budget.allocation(invalid)
        measured = pack.preflight_budget(self.folder)
        needed = measured['modeled_output_bytes']
        with patch.object(budget, 'ARENA_CEILING', needed):
            self.assertEqual(pack.preflight_budget(self.folder)['over_budget_bytes'], 0)
        with patch.object(budget, 'ARENA_CEILING', needed-1), patch.object(texture, 'compile_texture') as compiler:
            with self.assertRaisesRegex(ValueError, r'over by 1 bytes'):
                pack.apply(self.raw, self.folder)
            compiler.assert_not_called()
        with self.assertRaisesRegex(ValueError, '128 MiB target unavailable'):
            pack.preflight_budget(self.folder, target='xemu-128')

    def test_archive_multiple_chunks_per_outer_growth_shrink_and_mud_race(self):
        # Two selected resources share one outer. No selected chunk may vanish.
        assets = (self.assets[0], replace(self.assets[1], outer=0, chunk=1, name_id=100), self.assets[2])
        with patch.object(pack, 'ASSETS', assets), patch.object(texture, 'ASSETS', assets), \
             patch.object(texture, 'BY_KEY', {a.key: a for a in assets}), \
             patch.object(pack, '_consumer_check', return_value={'synthetic': True}):
            entries = [(100, self.raw[assets[0].key]+self.raw[assets[1].key]),
                       (999, b'unselected'), (102, self.raw[assets[2].key]), (998, b'last')]
            fixture = SyntheticXiso(self.root, entries, pack_sizes=(2048,)*16, pack_sectors=tuple(range(64,80)))
            target = self.root/'output.iso'
            rec = pack.build_image(fixture.path, target, self.folder)
            self.assertEqual(rec['verification']['unchanged_outers'], 2)
            self.assertEqual(pack.inspect_image(target, self.folder)['status'], 'applied')
            control = self.root/'native.iso'
            pack.build_image(target, control, self.folder, scale=1)
            self.assertEqual(pack.inspect_image(control, self.folder, scale=1)['status'], 'applied')
            before = archive.file_hash(target)
            def mutate(stage, *_):
                if stage == 'archive':
                    (self.folder/'jersey_fixture.mud.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'authored input changed'):
                pack.build_image(fixture.path, target, self.folder, overwrite=True, progress=mutate)
            self.assertEqual(archive.file_hash(target), before)
            self.assertFalse(list(self.root.glob('.archive-*')))

    def test_shared_palette_quantization_reports_both_raster_errors(self):
        # More than 256 paired colors requires genuine shared-index reduction.
        clean = bytes(v for i in range(512) for v in (i%256, i//256, 1, 255))
        mud = bytes(v for i in range(512) for v in (i//256, i%256, 8, 200))
        level = texture.palettes.MipLevel
        palettes, indices, quality = layouts.paired_palette([level(0,32,16,clean)], [level(0,32,16,mud)])
        self.assertEqual(len(palettes), 2)
        self.assertEqual(len(indices[0]), 512)
        self.assertLessEqual(len(palettes[0]), 256)
        self.assertGreater(quality['maximum_channel_error'], 0)


if __name__ == '__main__':
    unittest.main()
