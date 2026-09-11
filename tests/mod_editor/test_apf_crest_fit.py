"""Synthetic 512x512 crest allocation, safe compression and receipt contracts."""
from dataclasses import replace
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from PIL import Image
import apf_inner as inner
import apf_outer as outer
import apf_logo_patch as writer
import apf_field_art_patch as field


def synthetic_package(budget=500000):
    """Hand-authored headers and flat pixels; no game or reporter bytes."""
    names = ('logo_l0', 'logo_l1')
    dram = bytearray(2 * writer.DRAM_PART_LEN)
    for i in range(2):
        start = i * writer.DRAM_PART_LEN
        struct.pack_into('>HH', dram, start + 0x60, 512, 512)
        struct.pack_into('>II', dram, start + 0x70, writer.BASE_LEN, writer.MIP_LEN)
        swizzle = sum(value << (3 * channel) for channel, value in enumerate((2, 1, 0, 3)))
        struct.pack_into('>6I', dram, start + 0x94, 2 | (16 << 22) | (1 << 31),
                         15 | (1 << 6), 511 | (511 << 13), swizzle << 1, 9 << 6,
                         (1 << 9) | (1 << 11))
    metas = [inner.parse_txtr_metadata(dram[i * writer.DRAM_PART_LEN:(i + 1) * writer.DRAM_PART_LEN]) for i in range(2)]
    rgba = [Image.new('RGBA', (512, 512), (0, 0, 0, alpha)).tobytes() for alpha in (255, 136)]
    vram = b''.join(writer.encode_4444_base(meta, art) + writer.rebuild_mip_tail(meta, art, bytes(writer.MIP_LEN))
                    for meta, art in zip(metas, rgba))
    stream = writer._compressed(vram, 8)
    stored = struct.pack('>5I', inner.H7A_MAGIC, len(vram), 20 + len(stream), 0, 8) + stream
    payload = bytearray(32)
    struct.pack_into('<II', payload, 0, 2, 5)
    for i, name in enumerate(names):
        descriptor, pointer = 16 + 8 * i, 8 + 4 * i
        struct.pack_into('<I', payload, pointer, descriptor - pointer + 1)
        name_start = len(payload)
        payload.extend(name.encode('utf-16le') + b'\0\0')
        type_start = len(payload)
        payload.extend('TXTR'.encode('utf-16le') + b'\0\0')
        struct.pack_into('<II', payload, descriptor, name_start - descriptor + 1,
                         type_start - descriptor - 4 + 1)
    footer = struct.pack('>I', inner.NAME_FOOTER_MAGIC) + struct.pack('<I', len(payload)) + payload
    header = bytearray(144)
    length = len(header) + len(dram) + len(stored)
    struct.pack_into('>8I', header, 0, inner.IFF_MAGIC, len(header), length, 0, 2, 13, 2, 69)
    for i, (data, uncompressed, start) in enumerate(((dram, len(dram), len(header)),
                                                   (stored, len(vram), len(header) + len(dram)))):
        struct.pack_into('>8I', header, 32 + 32 * i, 0, 0, 0, uncompressed, 0, start, len(data), 0)
    for i, name in enumerate(names):
        descriptor, pointer = 104 + 20 * i, 96 + 4 * i
        struct.pack_into('>I', header, pointer, descriptor - pointer + 1)
        struct.pack_into('>5I', header, descriptor, zlib.crc32(name.encode()), zlib.crc32(b'TXTR'),
                         2, i * writer.DRAM_PART_LEN, i * writer.PAYLOAD_LEN)
    allocation = len(header) + len(dram) + 20 + len(footer) + budget
    entry = outer.Entry(621, zlib.crc32(b'UNIFORM_LOGO_92.IFF'), 0, 0, 0, allocation,
                        'ff3bef94', (outer.Segment(0, '0A', 0, allocation),))
    raw = bytes(header) + bytes(dram) + stored + bytes(footer)
    if len(raw) > allocation:
        raise ValueError('synthetic source itself exceeds requested budget')
    raw += bytes(allocation - len(raw))
    record = inner.parse_iff(writer.BytesReader(raw), entry)
    blocks, original_stored = [bytes(dram), vram], [bytes(dram), stored]
    layers = tuple(writer._extract_layer(record, blocks, i, name, None) for i, name in enumerate(names))
    return entry, record, raw, blocks, original_stored, layers


def synthetic_art():
    rng = random.Random(661)
    image = Image.new('RGBA', (128, 128))
    image.putdata([((4 + rng.randrange(8)) * 17, (4 + rng.randrange(8)) * 17,
                    (4 + rng.randrange(8)) * 17, 255) for x in range(128 * 128)])
    l0 = image.resize((512, 512), Image.Resampling.NEAREST).tobytes()
    # Distinct detail masks exercise all six regions, with independent alpha.
    l1 = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).resize((512, 512), Image.Resampling.NEAREST).tobytes()
    return l0, l1


class CrestFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = synthetic_package()
        cls.art = synthetic_art()
        entry, record, raw, blocks, stored, layers = cls.source
        cls.candidates = {}
        for shades in (16, 8, 4, 2):
            block = writer._layer_blocks(blocks, tuple(zip(layers, cls.art)), shades, True)[1]
            cls.candidates[shades] = (block, writer._compressed(block, 8), writer._compressed(block, 8, True))

    def build(self, budget, *, allow=True, art=None):
        entry, record, raw, blocks, stored, layers = self.source
        size = entry.size + budget - writer.compressed_art_budget(entry, record)
        entry = replace(entry, size=size, segments=(replace(entry.segments[0], size=size),))
        raw = raw[:size]
        record = inner.parse_iff(writer.BytesReader(raw), entry)
        opened = (None, entry, record, raw, blocks, stored)
        with patch.object(writer, '_open_entry', return_value=opened), patch.object(writer, 'crest_package_budgets', return_value=()):
            return entry, writer.build_patch_rgba(Path('synthetic-0A'), *(art or self.art),
                        entry_index=621, allow_simplification=allow)

    def test_first_fit_greedy_and_each_shade_step_reparse(self):
        for shades in (16, 8, 4, 2):
            with self.subTest(shades=shades):
                block, greedy, optimal = self.candidates[shades]
                if shades < 16:
                    self.assertLess(len(greedy), len(self.candidates[shades * 2][2]))
                entry, result = self.build(len(greedy))
                fit = result.manifest['fit']
                self.assertEqual(fit['shades_per_region'], shades)
                self.assertEqual(fit['compressed_art_bytes'], len(greedy))
                self.assertEqual(fit['encoder'], 'greedy H7A')
                self.assertEqual(len(result.entry_bytes), entry.size)
                self.assertTrue(result.manifest['validation']['rebuilt_iff_reparsed'])
                self.assertEqual(result.manifest['source']['png_rgba_sha256']['logo_l0'], writer.sha256_bytes(self.art[0]))
                reader = writer.BytesReader(result.entry_bytes)
                record = inner.parse_iff(reader, entry)
                decoded = inner.decode_block(reader, record, 1, 1 << 30)
                self.assertEqual(decoded, block)
                for layer, original in zip(self.source[-1], self.art):
                    base = decoded[layer.vram_offset:layer.vram_offset + writer.BASE_LEN]
                    pixels = writer.decode_4444_base(layer.metadata, base)
                    self.assertEqual(pixels[3::4], original[3::4])
                    expected = original if shades == 16 else writer.simplify_regions(original, shades)
                    self.assertEqual(pixels, expected)
                if shades < 16:
                    self.assertIn(f'16 shades reduced to {shades} per region', fit['status'])
                for attempt in fit['attempts'][:-1]:
                    self.assertFalse(attempt['fits'])

    def test_optimal_before_any_reduction(self):
        if field._optimal_binary() is None:
            self.skipTest('reviewed optimal encoder unavailable on this platform')
        block, greedy, optimal = self.candidates[16]
        self.assertLess(len(optimal), len(greedy))
        _, result = self.build(len(optimal))
        self.assertEqual(result.manifest['fit']['shades_per_region'], 16)
        self.assertEqual(result.manifest['fit']['encoder'], 'safe optimal H7A')
        writer.verify_h7a_stream(optimal, block, 8)

    def test_refusal_and_disabled_reduction(self):
        needed = len(self.candidates[2][2])
        with self.assertRaisesRegex(writer.PatchError, f'needs {needed:,} at 2 shades.*Choose a package with room.*flatten the art'):
            self.build(needed - 1)
        with self.assertRaisesRegex(writer.PatchError, 'simplification disabled'):
            self.build(len(self.candidates[8][1]), allow=False)
        self.assertEqual(writer.fit_refusal(48609, 67758, 2, [{'slot': 23}, {'slot': 85}, {'slot': 78}]),
            'This crest package holds 48,609 bytes of compressed art; this logo needs 67,758 at 2 shades. '
            'Choose a package with room (for example Logo slot 23, 85, 78) or flatten the art.')

    def test_single_layer_preserves_sibling_and_hashes(self):
        entry, record, raw, blocks, stored, layers = self.source
        new_blocks = writer._layer_blocks(blocks, [(layers[0], self.art[0])], 4, True)
        budget = len(writer._compressed(new_blocks[1], 8))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'l0.png'
            Image.frombytes('RGBA', (512, 512), self.art[0]).save(path)
            size = entry.size + budget - writer.compressed_art_budget(entry, record)
            entry = replace(entry, size=size)
            raw = raw[:size]
            record = inner.parse_iff(writer.BytesReader(raw), entry)
            with patch.object(writer, '_open_entry', return_value=(None, entry, record, raw, blocks, stored)):
                result = writer.build_patch(Path('synthetic'), path, entry_index=621, allow_simplification=True)
        self.assertEqual(result.manifest['fit']['changed_layers'], ['logo_l0'])
        self.assertEqual(result.manifest['fit']['shades_per_region'], 4)
        self.assertTrue(result.manifest['validation']['other_level_l1_preserved'])
        self.assertEqual(result.manifest['source']['png_rgba_sha256'], writer.sha256_bytes(self.art[0]))

    def test_batch_propagates_fit_policy_and_keeps_receipts(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        entry, record, raw, blocks, stored, layers = self.source
        budget = len(self.candidates[4][1])
        size = entry.size + budget - writer.compressed_art_budget(entry, record)
        entry = replace(entry, size=size)
        raw = raw[:size]
        archive = SimpleNamespace(entries=[None] * 621 + [entry])
        with patch.object(outer, 'parse_archive', return_value=archive), \
             patch.object(inner, 'ArchiveReader', return_value=nullcontext(writer.BytesReader(raw))):
            result = writer.build_patch_rgba_batch(Path('synthetic'), (621,), lambda *_: self.art,
                                                   allow_simplification=True)[621]
        self.assertEqual(result.manifest['fit']['shades_per_region'], 4)
        self.assertEqual(result.manifest['source']['png_rgba_sha256']['logo_l1'], writer.sha256_bytes(self.art[1]))
        self.assertEqual(len(result.entry_bytes), size)

    def test_reparse_gate_still_refuses_wrong_decoded_blocks(self):
        with patch.object(inner, 'decode_block', return_value=b'wrong'):
            with self.assertRaisesRegex(writer.PatchError, 'does not decode as intended'):
                self.build(len(self.candidates[4][1]))

    def test_measurement_cache_keys_pixels_and_preserved_layout(self):
        layers = self.source[-1]
        template = writer.LogoMeasurementTemplate(8, bytes(2 * writer.PAYLOAD_LEN), layers)
        writer._MEASUREMENT_CACHE.clear()
        rows = writer.measure_logo_pair(*self.art, template, minimum_budget=1)
        with patch.object(writer, '_layer_blocks', side_effect=AssertionError('cache miss')):
            self.assertEqual(writer.measure_logo_pair(*self.art, template, minimum_budget=1), rows)
            with self.assertRaises(AssertionError):
                writer.measure_logo_pair(self.art[1], self.art[0], template, minimum_budget=1)
        self.assertEqual([r['compressed_art_bytes'] for r in rows[::2]],
                         [len(self.candidates[n][1]) for n in (16, 8, 4, 2)])


class SafetyTests(unittest.TestCase):
    def test_all_rgb_nibbles_snap_independently_and_alpha_is_untouched(self):
        art = bytes(range(256)) * (512 * 512 * 4 // 256)
        for shades in (8, 4, 2):
            result = writer.simplify_regions(art, shades)
            self.assertEqual(result[3::4], art[3::4])
            for channel in range(3):
                self.assertEqual(len(set(result[channel::4])), shades)
                self.assertTrue(all(value % 17 == 0 for value in result[channel::4]))

    def test_roundtripping_overlap_is_still_refused(self):
        # Three literal bytes then length 6 at distance 3: decodes correctly,
        # but is explicitly outside the reviewed console encoder contract.
        stream = b'\x08abc' + ((3 << 8) | 3).to_bytes(2, 'big')
        self.assertEqual(inner.decompress_h7a(stream, 9, 8), b'abcabcabc')
        with self.assertRaisesRegex(writer.PatchError, 'unsafe H7A'):
            writer.verify_h7a_stream(stream, b'abcabcabc', 8)

    def test_best_reuses_reviewed_binary_predicate_and_rejects_overlap(self):
        data = b'abcabcabc'
        greedy = writer.compress_h7a(data, 8)
        with patch.object(field, 'compress_h7a_best', return_value=b'\x08abc' + ((3 << 8) | 3).to_bytes(2, 'big')):
            self.assertEqual(writer.compress_h7a_best(data, 8, greedy=greedy), greedy)
        with patch.object(field, '_optimal_binary', return_value=None):
            self.assertEqual(writer.compress_h7a_best(data, 8, greedy=greedy), greedy)


if __name__ == '__main__':
    unittest.main()
