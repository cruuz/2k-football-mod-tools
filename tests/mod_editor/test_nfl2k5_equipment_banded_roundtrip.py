"""Banded PNGs require pixel indices, not just a replacement retail palette."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
from test_nfl2k5_equipment_texture_chain import Fixture
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from mod_editor.core.nfl2k5_equipment_lz import uncapped_optimal_fit
from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks
from nfl_tset_png_import import decode_rgba_png

INDEX = Path(os.environ.get('NFL2K5_RETAIL_INDEX',
    '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))


def bands(width, height, case):
    rng = random.Random(77)
    pixels = []
    for y in range(height):
        for x in range(width):
            first = height // 4 <= y < 3 * height // 8
            second = 5 * height // 8 <= y < 3 * height // 4
            color = (245, 245, 245, 255)
            if first or (case != 'one' and second):
                color = (64, 32, 16, 255)
            if case == 'posterised':
                if second:
                    color = (224, 96, 16, 255)
                elif y >= 7 * height // 8:
                    color = (192, 192, 192, 255)
            if case == 'noise' and (first or second) and x % 16 == 0:
                color = (64 + rng.randrange(4), 32, 16, 255)
            pixels.append(bytes(color))
    return b''.join(pixels)


def quantized_levels(rgba, target, maximum, scale=1):
    levels = make_digit_mips(rgba, target.width, target.height, target.mip_levels)
    levels[0] = replace(levels[0], rgba=rgba)
    levels = levels[scale.bit_length() - 1:]
    palette, indices, _ = writer._quantize_art(levels, maximum)
    return [b''.join(bytes(palette[i]) for i in row) for row in indices]


def decode_result(result, target, original_texture):
    span, previews, receipt, _, _ = result
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    row = next(row for row in receipt['edits'] if row['asset_id'] == target.asset_id)
    # Read the actual descriptor, independently of the preview and receipt.
    import struct
    pixel, _, packed = struct.unpack_from('<III', decoded, original_texture.descriptor_offset + 4)
    texture = replace(original_texture, pixel_offset=pixel, packed_format=packed,
                      width=1 << ((packed >> 20) & 15), height=1 << ((packed >> 24) & 15),
                      mip_levels=(packed >> 16) & 15)
    actual = writer.decode_equipment_levels(decoded, chunk, texture)
    preview = next(png for name, png in previews if name == row['preview_file'])
    assert decode_rgba_png(preview, (texture.width, texture.height))[2] == actual[0]
    return actual, row, decoded


class BandedTests(unittest.TestCase):
    def test_ordinary_bands_use_own_chain_and_roundtrip_every_mip(self):
        for case in ('one', 'two', 'posterised', 'noise'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory), family=4, width=64, count=2,
                            names=('socks00', 'socks00_mud'), margin=20000)
                target = f.rows[0]
                rgba = bands(target.width, target.height, case)
                path = f.root / 'ordinary.png'
                path.write_bytes(encode_rgba_png(target.width, target.height, rgba))
                result = f.build([(target.asset_id, path)])
                self.assertEqual(result[2]['input_pngs'][0]['sha256'],
                                 hashlib.sha256(path.read_bytes()).hexdigest())
                textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
                actual, row, decoded = decode_result(result, target, textures[0])
                maximum = next(a['maximum_palette_entries'] for a in result[2]['bounded_palette_fit']['attempts'] if a['result'] == 'fit')
                self.assertEqual(actual, quantized_levels(rgba, target, maximum))
                self.assertEqual(row['import_mode'], 'independent-mip-chain')
                after_chunk = parse_chunks(result[0])[0]
                self.assertEqual(writer.decode_equipment_levels(decoded, after_chunk, textures[1]),
                                 writer.decode_equipment_levels(f.decoded, f.chunk, textures[1]))

    def test_explicit_shared_palette_choice_stays_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), family=4, width=64, count=2,
                        names=('socks00', 'socks00_mud'))
            result = f.build([f.png(independent=False, rgba=bands(64, 64, 'two'))])
            self.assertEqual(result[2]['edits'][0]['import_mode'], 'palette-only')
            self.assertEqual(result[2]['allocation']['added_video_bytes'], 0)

    def test_exact_retail_and_rounding_projection_are_noops(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), family=4, width=64, count=2,
                        names=('socks00', 'socks00_mud'))
            textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
            retail = writer.decode_equipment_levels(f.decoded, f.chunk, textures[0])[0]
            # Retail uses indices 0..7. Make a tiny minority of pixels differ
            # by one channel so their per-index mode remains the retail colour.
            rounded = bytearray(retail)
            rounded[0] += 1
            for rgba in (retail, bytes(rounded)):
                result = f.build([f.png(independent=False, rgba=rgba)])
                self.assertEqual(result[0], f.span)

    def test_automatic_bands_refit_as_own_texture(self):
        from mod_editor.core.nfl2k5_equipment_import_intent import import_settings
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), family=4, width=64, count=2,
                        names=('socks00', 'socks00_mud'))
            rgba = bands(64, 64, 'two')
            png = encode_rgba_png(64, 64, rgba)
            settings = []
            for candidate in writer.refit_candidates(f.rows[0], png, rgba):
                decoded = decode_rgba_png(candidate, (64, 64))[2]
                settings.append(import_settings(candidate, f.rows[0].asset_id, decoded))
            self.assertTrue(all(mode == 'independent-mip-chain' for mode, _ in settings))
            self.assertEqual({scale for _, scale in settings}, {1, 2, 4})

    def test_tight_span_retries_distance_level_without_shrinking_explicit_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Fixture(Path(directory), family=4, width=64, count=2,
                        names=('socks00', 'socks00_mud'), margin=0)
            rgba = bytearray(bands(64, 64, 'two'))
            rng = random.Random(77)
            for i in range(0, len(rgba), 4):
                for channel in range(3):
                    rgba[i + channel] = min(255, rgba[i + channel] + rng.randrange(4))
            rgba = bytes(rgba)
            path = f.root / 'automatic.png'
            path.write_bytes(encode_rgba_png(64, 64, rgba))
            result = f.build([(f.rows[0].asset_id, path)])
            textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
            actual, row, _ = decode_result(result, f.rows[0], textures[0])
            self.assertEqual(row['encoded_dimensions'], [32, 32])
            maximum = next(a['maximum_palette_entries'] for a in
                           result[2]['bounded_palette_fit']['attempts'] if a['result'] == 'fit')
            self.assertEqual(actual, quantized_levels(rgba, f.rows[0], maximum, scale=2))
            # Identical pixels with an explicit full-size choice must not reuse
            # the automatic retry's cached half-size result.
            with self.assertRaises(writer.EquipmentFitError):
                f.build([f.png(independent=True, rgba=rgba)])


@unittest.skipUnless(INDEX.is_file(), 'Private retail pack index is absent')
class RetailBandedTests(unittest.TestCase):
    def test_real_sock_slot_bands(self):
        from nfl_outer import parse_archive, read_entry_bytes
        target = next(t for t in writer.load_targets()[0].values()
                      if t.set_selector == '30A4' and t.name == 'socks00')
        package = read_entry_bytes(parse_archive(INDEX), parse_archive(INDEX).entries[target.outer_index])
        chunk = next(c for c in parse_chunks(package, allow_trailing=True) if c.index == target.chunk_index)
        decoded, _ = decode_chunk(package, chunk)
        rows = writer.load_targets()[1][target.outer_index, target.chunk_index]
        textures, _ = writer._validate_layout(decoded, chunk, rows)
        with tempfile.TemporaryDirectory() as directory, uncapped_optimal_fit():
            hashes = {}
            for case in ('one', 'two', 'posterised', 'noise'):
                with self.subTest(case=case):
                    rgba = bands(target.width, target.height, case)
                    path = Path(directory) / (case + '.png')
                    path.write_bytes(encode_rgba_png(target.width, target.height, rgba))
                    result = writer.build_unified_uniform_equipment_imports(
                        INDEX, [(target.asset_id, path)], suggest_fit=False, pack_hashes=hashes)
                    actual, row, _ = decode_result(result, target, textures[target.reference_index])
                    maximum = next(a['maximum_palette_entries'] for a in result[2]['bounded_palette_fit']['attempts'] if a['result'] == 'fit')
                    expected = quantized_levels(rgba, target, maximum)
                    differing = sum(a[i:i+4] != b[i:i+4] for a, b in zip(actual, expected)
                                    for i in range(0, len(a), 4))
                    print(f'{case}: quantized RGBA differing pixels across all mips = {differing}', flush=True)
                    self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
