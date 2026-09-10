"""Synthetic codec/guard tests and read-only retail/PS3 endzone proofs."""
from __future__ import annotations

from dataclasses import replace
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import apf_field_art_patch as fa
import apf_field_art_verify as verify
import apf_inner
import apf_outer
import apf_xenos_bc1_mip_layout as mips
import apf_xenos_dxt5a as scalar

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A')
BUNDLE = Path('/home/noah/Downloads/NFL Logos Textures.zip')


def synthetic():
    contract = replace(fa._CONTRACTS[(78, 1)], width=128, height=128,
                       pitch_pixels=128, base_len=8192, mip_len=24576)
    metadata = dict(format=59, endianness=1, tiled=True, stacked=False,
                    dimension=1, mip_min_level=0, packed_mips=True,
                    width=128, height=128, pitch_pixels=128,
                    vc_base_data_length=8192, vc_mip_data_length=24576,
                    mip_max_level=3, mip_address_pages=2,
                    swizzle_components=[0, 0, 0, 5])
    return contract, metadata


class DXT5ASyntheticTests(unittest.TestCase):
    def test_scalar_endpoint_modes_and_exact_unchanged_blocks(self):
        contract, metadata = synthetic()
        loc = mips.derive_layout(metadata)[-1]
        # Both endpoint modes, including the explicit 0/255 mode.
        for endpoints in ((255, 0), (12, 180), (73, 73)):
            block = bytes(endpoints) + int('7654321076543210', 8).to_bytes(6, 'little')
            linear = block * loc.logical_block_count
            rgba = fa._decode_endzone_level('dxt5a', linear, loc)
            self.assertEqual(fa._encode_endzone_level('dxt5a', linear, rgba, loc), linear)
            pixels = scalar.decode_block(block)
            self.assertEqual(pixels[:8], scalar.alpha_palette(*endpoints))

    def test_changed_scalar_mips_swizzle_transport_and_padding(self):
        contract, metadata = synthetic()
        original = bytes([0xA5]) * (contract.base_len + contract.mip_len)
        wanted = Image.new('RGBA', (128, 128), (0, 0, 0, 255))
        wanted.paste((255, 255, 255, 255), (0, 0, 64, 128))
        output, levels = fa._encode_endzone_texture(contract, metadata, original, wanted.tobytes())
        self.assertEqual(len(output), len(original))
        self.assertEqual(fa.decode_field_art_base(metadata, output[:8192])[2], wanted.tobytes())
        self.assertEqual(mips.transport_roundtrip(output, mips.derive_layout(metadata)), output)
        self.assertEqual(len(levels), 4)
        self.assertTrue(all(r['decode_back_metrics']['maximum_absolute_error'] == 0 for r in levels))
        verify.verify_endzone_mips(contract, metadata, original, output, wanted.tobytes(), 1, levels)
        # Independent verifier rejects both changed active mip data and inactive padding.
        for offset in (mips.derive_layout(metadata)[1].data_offset, len(output) - 1):
            corrupt = bytearray(output); corrupt[offset] ^= 1
            with self.assertRaises(verify.VerifyError):
                verify.verify_endzone_mips(contract, metadata, original, bytes(corrupt), wanted.tobytes(), 1, levels)
        changed = copy.deepcopy(levels); changed[1]['wanted_rgba_sha256'] = '0' * 64
        with self.assertRaises(verify.VerifyError):
            verify.verify_endzone_mips(contract, metadata, original, output, wanted.tobytes(), 1, changed)

    def test_unrepresentable_color_and_alpha_refused(self):
        contract, metadata = synthetic()
        for color in ((255, 0, 0, 255), (80, 80, 80, 0)):
            with self.assertRaisesRegex(fa.PatchError, 'grayscale RGB and opaque alpha'):
                fa._encode_endzone_texture(contract, metadata, bytes(32768), Image.new('RGBA', (128, 128), color).tobytes())
        with self.assertRaisesRegex(fa.PatchError, 'grayscale'):
            fa.decode_field_art_base({**metadata, 'swizzle_components': [0, 1, 2, 3]}, bytes(8192))

    def test_descriptor_drift_and_aliases_refused(self):
        _, metadata = synthetic()
        for key, value in [('format', 20), ('endianness', 2), ('tiled', False),
                           ('vc_mip_data_length', 4096), ('mip_address_pages', 1), ('mip_max_level', 12)]:
            with self.subTest(key=key), self.assertRaises(mips.MipLayoutError):
                mips.derive_layout({**metadata, key: value})

    def test_quality_step_preserves_alpha_and_is_receipted(self):
        contract, metadata = synthetic()
        requested = Image.new('RGBA', (128, 128), (140, 140, 140, 255)).tobytes()
        effective = fa._endzone_image(requested, (128, 128), 2, True).tobytes()
        self.assertEqual(set(effective), {255})
        original = bytes(32768)
        output, levels = fa._encode_endzone_texture(contract, metadata, original, effective)
        verify.verify_endzone_mips(contract, metadata, original, output, requested, 2, levels, simplify=True)
        with self.assertRaises(verify.VerifyError):
            verify.verify_endzone_mips(contract, metadata, original, output, requested, 2, levels)
        rgba = bytes((120, 130, 255, 73)) * 64
        self.assertEqual(fa._endzone_image(rgba, (8, 8), 1, True).tobytes(), bytes((0, 255, 255, 73)) * 64)

    def test_safe_h7a_gate_and_greedy_parse_parity(self):
        rng = random.Random(59)
        data = bytes(4096) + bytes(rng.randrange(4) for _ in range(4096))
        def old_match(data, current, candidate, maximum):
            length = 0
            while length < maximum and data[current + length] == data[candidate + length]:
                length += 1
            return length
        for shift in (8, 9, 11):
            stream = fa.compress_h7a(data, shift)
            fa._validate_h7a_stream(stream, data, shift)
            with mock.patch.object(fa, '_match_length', old_match):
                self.assertEqual(stream, fa.compress_h7a(data, shift))
        # Literal A, then distance 1 / length 3: decoder accepts it; console gate refuses.
        unsafe = b'\x02A\x00\x01'
        self.assertEqual(apf_inner.decompress_h7a(unsafe, 4, 9), b'AAAA')
        with self.assertRaisesRegex(fa.PatchError, 'overlaps'):
            fa._validate_h7a_stream(unsafe, b'AAAA', 9)
        with self.assertRaises(fa.PatchError):
            fa._validate_h7a_stream(b'\x01', b'AAAA', 9)


@unittest.skipUnless(RETAIL.is_file(), f'Retail APF Xbox 360 0A absent at {RETAIL}')
class RetailDXT5ATests(unittest.TestCase):
    def test_all_39_retail_pins_and_mip_layouts(self):
        archive = apf_outer.parse_archive(RETAIL)
        contracts = [c for c in fa._CONTRACTS.values() if c.format == 59]
        self.assertEqual(len(contracts), 39)
        with apf_inner.ArchiveReader(archive) as reader:
            for c in contracts:
                with self.subTest(entry=c.entry_index):
                    entry = archive.entries[c.entry_index]
                    record = apf_inner.parse_iff(reader, entry)
                    blocks = [apf_inner.decode_block(reader, record, i, 1 << 25) for i in range(record.block_count)]
                    _, _, _, pixel, meta = fa._resolve_target(record, blocks, c)
                    fa._validate_descriptor(c, meta)
                    self.assertEqual(hashlib.sha256(reader.read(entry, 0, entry.size)).hexdigest(), c.entry_sha256)
                    self.assertEqual(hashlib.sha256(pixel[:c.base_len]).hexdigest(), c.base_sha256)
                    locations = mips.derive_layout(meta)
                    self.assertEqual(len(locations), 8)
                    self.assertEqual(mips.transport_roundtrip(pixel, locations), pixel)

    def test_retail_decode_encode_unchanged_exact(self):
        archive = apf_outer.parse_archive(RETAIL); entry = archive.entries[78]
        c = fa._CONTRACTS[(78, 1)]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            source = reader.read(entry, 0, entry.size)
            blocks = [apf_inner.decode_block(reader, record, i, 1 << 25) for i in range(record.block_count)]
        _, _, _, pixel, meta = fa._resolve_target(record, blocks, c)
        rgba = fa.decode_field_art_base(meta, pixel[:c.base_len])[2]
        base_loc = mips.derive_layout(meta)[0]
        linear = mips.extract_linear_bc1(pixel, base_loc)
        self.assertEqual(fa._encode_endzone_level('dxt5a', linear, rgba, base_loc), linear)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / 'retail.png'; Image.frombytes('RGBA', (2048, 512), rgba).save(png)
            result = fa.build_field_art_patch(RETAIL, png, 78, 1)
        self.assertEqual(result.entry_bytes, source)
        self.assertEqual(result.manifest['validation']['codec_maximum_absolute_error'], 0)
        # Separately invoke the scalar codec on every distinct retail block.
        maximum = 0
        for block in {linear[i:i + 8] for i in range(0, len(linear), 8)}:
            values = scalar.decode_block(block); encoded, error = scalar.encode_block(values)
            decoded = scalar.decode_block(encoded)
            maximum = max(maximum, max(abs(a - b) for a, b in zip(values, decoded)))
        self.assertEqual(maximum, 0)


@unittest.skipUnless(RETAIL.is_file() and BUNDLE.is_file(), f'Retail 0A and supplied NFL Logos ZIP required: {RETAIL}; {BUNDLE}')
class SuppliedPS3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.apf_studio.ps3_texture_bundle import read_bundle, destination_slots
        cls.bundle = read_bundle(BUNDLE); cls.slots = destination_slots(RETAIL)

    def test_all_eight_pairs_stage_idempotently_and_prepare_54(self):
        from mod_editor.apf_studio.ps3_texture_bundle import Assignment, build_plan, stage_plan
        from mod_editor.apf_studio.models import ApfSource
        from mod_editor.apf_studio.session import ApfSession
        names = {'Chicago Bears', 'Cleveland Browns', 'Green Bay Packers', 'Houston Oilers',
                 'Indianapolis Colts', 'Los Angeles Raiders', 'New York Giants', 'New York Jets'}
        assignments = []
        for p in self.bundle.pairs:
            if p.kind == 'endzone' and p.variant.endswith('Orginal'):
                continue
            slot = next(s for s in self.slots if s.kind == p.kind and s.entry_hash == p.entry_hash)
            assignments.append(Assignment(p.pair_id, slot.slot_id))
        plan = build_plan(self.bundle, self.slots, assignments)
        self.assertEqual(len(self.bundle.pairs), 55)
        self.assertEqual(len(plan.assignments), 54)
        self.assertEqual(sum(s.kind == 'endzone' and s.writable for s in self.slots), 117)
        selected = [a for a in assignments if a.pair_id.split('/')[0] in names and '/endzone/' in a.pair_id]
        self.assertEqual(len(selected), 8)
        selected_plan = build_plan(self.bundle, self.slots, selected)
        self.assertTrue(all(r['mips'] == 'regenerated' for r in selected_plan.receipt['assignments']))
        source = ApfSource(RETAIL.parent, RETAIL.parent, RETAIL, 'a' * 64, RETAIL.stat().st_size, 'b' * 64, 'retail gate')
        with tempfile.TemporaryDirectory() as tmp:
            session = ApfSession(source, mock.Mock(), cache_root=Path(tmp) / 'cache')
            try:
                self.assertEqual(len(stage_plan(session, selected_plan)), 16)
                stage_plan(session, selected_plan)
                self.assertEqual(len(session.modifications), 16)
            finally:
                session.close()

    @unittest.skipUnless(os.environ.get("APF_ENDZONE_SLOW") == "1", "set APF_ENDZONE_SLOW=1 for supplied-pair allocation builds (about 4 minutes)")
    def test_supplied_chicago_and_washington_build_and_reparse(self):
        for team in ('Chicago Bears', 'Washington Redskins'):
            with self.subTest(team=team), tempfile.TemporaryDirectory() as tmp:
                p = next(p for p in self.bundle.pairs if p.team == team and p.kind == 'endzone')
                slot = next(s for s in self.slots if s.kind == p.kind and s.entry_hash == p.entry_hash)
                targets = []
                for layer, ix in zip(p.layers, slot.inner_indices):
                    png = Path(tmp) / (layer.layer + '.png'); layer.image.save(png); targets.append((ix, png))
                result = fa.build_field_art_patch_many(RETAIL, slot.outer_index, targets)
                entry = apf_outer.parse_archive(RETAIL).entries[slot.outer_index]
                self.assertEqual(len(result.entry_bytes), entry.size)
                reader = fa.BytesReader(result.entry_bytes)
                record = apf_inner.parse_iff(reader, entry)
                blocks = [apf_inner.decode_block(reader, record, i, 1 << 25) for i in range(record.block_count)]
                self.assertTrue(result.manifest['validation']['endzone_mips_independently_verified'])
                self.assertTrue(result.manifest['validation']['h7a_no_overlapping_matches'])
                self.assertGreaterEqual(result.manifest['iff']['allocation_slack_after'], 0)
                for layer, ix, proof in zip(p.layers, slot.inner_indices, result.manifest['targets']):
                    c = fa._CONTRACTS[(slot.outer_index, ix)]
                    _, _, _, pixel, meta = fa._resolve_target(record, blocks, c)
                    fa._validate_descriptor(c, meta)
                    self.assertEqual(hashlib.sha256(pixel[:c.base_len]).hexdigest(), proof['base_sha256_after'])
                    self.assertEqual(len(proof['mip_levels']), 8)
                # Optional metadata-only receipt; no pixels/payloads leave the temp directory.
                receipt_dir = os.environ.get('APF_ENDZONE_RECEIPTS')
                if receipt_dir:
                    name = team.split()[0].lower() + '_endzone_writer.json'
                    Path(receipt_dir, name).write_text(json.dumps(result.manifest, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
