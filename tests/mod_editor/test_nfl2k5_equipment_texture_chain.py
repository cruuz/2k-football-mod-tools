"""Bounded synthetic TSET proofs for independent glove/shoe mip imports."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core.nfl2k5_equipment_import_intent import (
    INTENT_CHUNK, OWN_TEXTURE, PALETTE_ONLY, import_mode, with_import_mode,
)
from nfl_txtr import HEADER, compress_vc_lz, decode_chunk, encode_rgba_png, parse_chunks, swizzle_2d


def digest(data):
    return hashlib.sha256(data).hexdigest()


def artwork(width, height):
    # Off-grid diagonal with invisible magenta: lower mips must retain coverage
    # without magenta bleeding into the visible white/teal design.
    return b"".join(bytes((255, 0, 255, 0) if x < 3 or y < 3 else
                         (240, 245, 250, 255) if x > y + 3 else (20, 180, 170, 255))
                    for y in range(height) for x in range(width))


class Fixture:
    def __init__(self, root, *, family=8, margin=2048, names=None):
        self.width, self.height, self.count = 32, (16 if family == 6 else 32), 3
        if names is not None and len(names) != self.count:
            raise ValueError("synthetic equipment fixture names must match its three references")
        self.levels = 2 if family == 6 else 3
        system = 512
        chains = []
        for level in range(self.levels):
            w, h = self.width >> level, self.height >> level
            linear = bytes((x + y + level) % 8 for y in range(h) for x in range(w))
            chains.append(swizzle_2d(linear, w, h, 1))
        shared = b"".join(chains)
        self.chain_size = len(shared)
        video = bytearray(shared)
        palette_offsets = []
        for reference in range(self.count):
            if reference:
                video.extend(bytes((-len(video)) % 128))
            palette_offsets.append(len(video))
            video.extend(b"".join(bytes((i // 2, (i + reference * 30) % 256, i, 255))
                                  for i in range(256)))
        video.extend(b"Z" * ((-len(video)) % 128))  # preserve an opaque unused tail
        decoded = bytearray(system) + video
        struct.pack_into("<II", decoded, 0, 13, self.count)
        rows = []
        for reference, palette_offset in enumerate(palette_offsets):
            name = ("glove" if family == 6 else "shoes") + f"{reference + 1:02d}"
            if names is not None:
                name = names[reference]
            base = 0x18 + reference * 0x24
            name_at, descriptor = 128 + reference * 32, 256 + reference * 32
            decoded[base:base + 4] = b"TXTR"
            for field, target in ((base + 4, name_at), (base + 8, descriptor)):
                struct.pack_into("<i", decoded, field, target - field + 1)
            encoded_name = (name + "\0").encode("utf-16le")
            decoded[name_at:name_at + len(encoded_name)] = encoded_name
            packed = 0xB29 | self.levels << 16 | 5 << 20 | (4 if family == 6 else 5) << 24
            struct.pack_into("<6I", decoded, descriptor, 0, 0, palette_offset, packed, 0, 0x80000000)
            rows.append(writer.EquipmentTarget(
                0, "SYNTHETIC", family, reference, name, self.width, self.height,
                0, palette_offset, packed, 0, 0x80000000, digest(chains[0]),
                digest(video[palette_offset:palette_offset + 1024]),
            ))
        self.rows = tuple(rows)
        self.decoded = bytes(decoded)
        encoded, _ = compress_vc_lz(self.decoded, stream_tag=1, offset_bits=12)
        stored = (len(encoded) + margin + 15) & ~15
        self.span = HEADER.pack(b"TSET", stored, system, len(video), 0xFEEDBEEF,
                                stored, 0, 0) + encoded + bytes(stored - len(encoded))
        self.chunk = replace(parse_chunks(self.span)[0], index=family)
        self.root = root
        self.pack = root / "synthetic-pack"
        self.pack.write_bytes(self.span)

    def png(self, reference=0, *, independent=True, rgba=None, scale=1):
        rgba = artwork(self.width, self.height) if rgba is None else rgba
        target = self.rows[reference]
        png = encode_rgba_png(self.width, self.height, rgba)
        png = with_import_mode(png, target.asset_id, rgba, independent=independent, scale=scale)
        path = self.root / f"art-{reference}.png"
        path.write_bytes(png)
        return target.asset_id, path

    def context(self):
        stack = ExitStack()
        segment = SimpleNamespace(pack_ordinal=0, pack_offset=128, size=len(self.span))
        archive = SimpleNamespace(entries=[SimpleNamespace(size=len(self.span), segments=[segment])],
                                  packs=[SimpleNamespace(name="pack", path=self.pack, size=len(self.span))])
        stack.enter_context(patch.object(writer, "load_targets", return_value=(
            {t.asset_id: t for t in self.rows}, {(0, self.chunk.index): self.rows})))
        stack.enter_context(patch.object(writer, "parse_archive", return_value=archive))
        stack.enter_context(patch.object(writer, "read_entry_bytes", side_effect=lambda *args: self.span))
        actual_parse = writer.parse_chunks
        stack.enter_context(patch.object(writer, "parse_chunks", side_effect=lambda data, **kw: (
            [self.chunk] if kw.get("allow_trailing") else actual_parse(data, **kw))))
        stack.enter_context(patch.object(writer, "_chain_pins", return_value={(0, self.chunk.index): digest(self.span)}))
        return stack

    def build(self, edits):
        with self.context():
            return writer.build_unified_uniform_equipment_imports(
                self.root / "0", edits, pack_hashes={"pack": digest(self.span)},
            )


class EquipmentChainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="equipment-chain-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_every_family_has_exact_new_shape_all_levels_and_unchanged_siblings(self):
        for family in (6, 8, 9):
            with self.subTest(family=family):
                f = Fixture(self.root, family=family)
                result, _previews, receipt, _selector, _target = f.build([f.png()])
                chunk = parse_chunks(result)[0]
                actual, _ = decode_chunk(result, chunk)
                self.assertEqual(len(result), len(f.span))
                self.assertGreater(chunk.video_bytes, f.chunk.video_bytes)
                textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
                desc = textures[0].descriptor_offset
                pixel = struct.unpack_from("<I", actual, desc + 4)[0]
                self.assertEqual(pixel % 128, 0)
                self.assertGreaterEqual(pixel, f.chunk.video_bytes)
                tex = replace(textures[0], pixel_offset=pixel)
                levels = writer.decode_equipment_levels(actual, chunk, tex)
                expected = make_digit_mips(artwork(f.width, f.height), f.width, f.height, f.levels)
                self.assertEqual(levels, [level.rgba for level in expected])
                self.assertTrue(any(0 < alpha < 255 for level in levels[1:] for alpha in level[3::4]))
                masked_before, masked_after = bytearray(f.decoded), bytearray(actual[:len(f.decoded)])
                for start, size in ((desc + 4, 4), (f.chunk.system_bytes + f.rows[0].palette_offset, 1024)):
                    masked_before[start:start + size] = bytes(size)
                    masked_after[start:start + size] = bytes(size)
                self.assertEqual(masked_before, masked_after)
                for sibling in (1, 2):
                    self.assertEqual(writer.decode_equipment_levels(f.decoded, f.chunk, textures[sibling]),
                                     writer.decode_equipment_levels(actual, chunk, textures[sibling]))
                self.assertTrue(receipt["compression"]["loader_in_place_alias_guard"])
                self.assertEqual([r["decoded_rgba_sha256"] for r in receipt["edits"][0]["levels"]],
                                 [digest(level.rgba) for level in expected])

    def test_plain_png_retains_the_default_palette_only_contract(self):
        f = Fixture(self.root)
        result, _, report, _, _ = f.build([f.png(independent=False)])
        actual, _ = decode_chunk(result, parse_chunks(result)[0])
        start = f.chunk.system_bytes + f.rows[0].palette_offset
        self.assertEqual(f.decoded[:start], actual[:start])
        self.assertEqual(f.decoded[start + 1024:], actual[start + 1024:])
        self.assertEqual(report["allocation"]["added_video_bytes"], 0)
        self.assertTrue(report["claims"]["selected_palette_allocations_only"])

    def test_final_build_receipt_distinguishes_chain_and_palette_edits(self):
        from types import SimpleNamespace
        from nfl2k5_visual_mod_project import claims_for

        for independent in (False, True):
            f = Fixture(self.root)
            _span, _previews, _report, _selector, target = f.build([f.png(independent=independent)])
            claims = claims_for([SimpleNamespace(kind="uniform_equipment_texture", target=target)])
            self.assertEqual(claims["uniform_equipment_selected_palettes_only"], not independent)
            self.assertEqual(claims["uniform_equipment_independent_chains_requested"], independent)
            self.assertEqual(claims["fixed_span_importers_reused_without_codec_changes"], not independent)
            self.assertTrue(claims["uniform_equipment_vc_lz_format_preserved"])
            self.assertFalse(claims["runtime_visibility_proved"])

    def test_explicit_smaller_image_rebuilds_packed_dimensions_and_every_level(self):
        f = Fixture(self.root)
        result, previews, receipt, _, _ = f.build([f.png(scale=2)])
        chunk = parse_chunks(result)[0]
        actual, _ = decode_chunk(result, chunk)
        textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
        texture = textures[0]
        pixel, _palette, packed = struct.unpack_from("<3I", actual, texture.descriptor_offset + 4)
        self.assertEqual(((packed >> 16) & 15, (packed >> 20) & 15, (packed >> 24) & 15), (2, 4, 4))
        decoded = writer.decode_equipment_levels(actual, chunk, replace(texture, pixel_offset=pixel,
                                                                         width=16, height=16, mip_levels=2))
        expected = make_digit_mips(artwork(32, 32), 32, 32, 3)[1:]
        self.assertEqual(decoded, [row.rgba for row in expected])
        self.assertEqual(receipt["edits"][0]["encoded_dimensions"], [16, 16])
        self.assertEqual(receipt["edits"][0]["size_reduction"], 2)
        from nfl_tset_png_import import decode_rgba_png
        self.assertEqual(decode_rgba_png(previews[0][1], (16, 16))[2], decoded[0])

    def test_optimal_lossless_fallback_preserves_exact_texture_bytes(self):
        from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
        source = b"aabaaaaabaaaaaababbaaba" * 80
        for bits in (10, 11, 12, 13):
            greedy, _ = compress_vc_lz(source, offset_bits=bits, stream_tag=1)
            best = compress_equipment_optimal(source, offset_bits=bits, stream_tag=1,
                                              max_encoded_size=len(greedy))
            self.assertLessEqual(len(best), len(greedy))
            from nfl_txtr import decompress_vc_lz
            self.assertEqual(decompress_vc_lz(best)[0], source)
        with self.assertRaisesRegex(writer.TxtrError, "search limit"):
            compress_equipment_optimal(source, offset_bits=12, stream_tag=1,
                                       max_encoded_size=4000, max_candidate_comparisons=1)

    def test_multiple_modes_and_independent_chains_compose_in_either_order(self):
        f = Fixture(self.root, margin=4096)
        edits = [f.png(), f.png(1, independent=False),
                 f.png(2, rgba=bytes((20, 40, 100, 255)) * (f.width * f.height))]
        a = f.build(edits)
        b = f.build(reversed(edits))
        self.assertEqual(a[0], b[0])
        offsets = [row["pixel_offset"] for row in a[2]["edits"]]
        self.assertEqual(offsets[1], 0)
        self.assertLess(offsets[0] + f.chain_size, offsets[2] + 1)
        self.assertNotEqual(offsets[0], offsets[2])
        self.assertEqual(a[2]["allocation"]["independent_variant_count"], 2)

    def test_refuses_overflow_without_writing_the_source(self):
        f = Fixture(self.root, margin=0)
        rng = random.Random(893)
        rgba = bytes(value for _ in range(f.width * f.height)
                     for value in (rng.randrange(256), rng.randrange(256), rng.randrange(256), 255))
        original = f.pack.read_bytes()
        with self.assertRaisesRegex(writer.UniformEquipmentWriterError, "cannot fit.*retail"):
            f.build([f.png(rgba=rgba)])
        self.assertEqual(f.pack.read_bytes(), original)

    def test_refuses_lower_mip_drift_even_with_unchanged_base_and_palettes(self):
        f = Fixture(self.root)
        edits = [f.png()]
        with f.context():
            changed = bytearray(f.decoded)
            changed[f.chunk.system_bytes + f.width * f.height] ^= 1
            # Keep the original complete source pin, emulate a foreign input.
            replacement, _ = writer.rebuild_compressed_chunk_fixed_span(f.span, bytes(changed))
            f.span = replacement
            with self.assertRaisesRegex(writer.UniformEquipmentWriterError, "complete retail source pin"):
                writer.build_unified_uniform_equipment_imports(self.root / "0", edits)

    def test_descriptor_and_base_palette_drift_refuse(self):
        for where in (256 + 4, 256 + 12, 512, 512 + 1344):
            f = Fixture(self.root)
            changed = bytearray(f.decoded)
            changed[where] ^= 1
            with self.assertRaises(writer.UniformEquipmentWriterError):
                writer._validate_layout(bytes(changed), f.chunk, f.rows)

    def test_replay_is_exact_and_mixed_or_foreign_bytes_refuse(self):
        f = Fixture(self.root)
        result = f.build([f.png()])
        after, receipt = writer.apply_equipment_span(f.span, result[0], result[2])
        self.assertTrue(receipt["changed"])
        replay, receipt = writer.apply_equipment_span(after, result[0], result[2])
        self.assertEqual(replay, after)
        self.assertFalse(receipt["changed"])
        changed = bytearray(after)
        changed[-1] ^= 1
        with self.assertRaisesRegex(writer.UniformEquipmentWriterError, "mixed or foreign"):
            writer.apply_equipment_span(bytes(changed), result[0], result[2])
        with self.assertRaisesRegex(writer.UniformEquipmentWriterError, "replacement or fixed span"):
            writer.apply_equipment_span(f.span, bytes(changed), result[2])

    def test_repeated_builds_have_identical_spans_and_receipts(self):
        f = Fixture(self.root)
        edits = [f.png()]
        self.assertEqual(f.build(edits), f.build(edits))

    def test_wrong_png_size_and_duplicate_edits_refuse(self):
        f = Fixture(self.root)
        target, path = f.png()
        with self.assertRaisesRegex(writer.UniformEquipmentWriterError, "repeats"):
            f.build([(target, path), (target, path)])
        path.write_bytes(encode_rgba_png(1, 1, bytes((0, 0, 0, 255))))
        with self.assertRaises(ValueError):
            f.build([(target, path)])

    def test_pin_catalog_covers_every_reviewed_glove_and_shoe_chunk(self):
        _by_id, groups = writer.load_targets()
        pins = writer._chain_pins()
        self.assertEqual(set(pins), {key for key in groups if key[1] in (6, 8, 9)})
        self.assertEqual(len(pins), 1902)


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.rgba = bytes((255, 255, 255, 255)) * 64
        self.png = encode_rgba_png(8, 8, self.rgba)
        self.asset_id = "tset:0:8:0:shoes01"

    def test_default_explicit_choice_reset_and_idempotent_tag(self):
        self.assertEqual(import_mode(self.png, self.asset_id, self.rgba), PALETTE_ONLY)
        tagged = with_import_mode(self.png, self.asset_id, self.rgba, independent=True)
        self.assertEqual(import_mode(tagged, self.asset_id, self.rgba), OWN_TEXTURE)
        self.assertEqual(with_import_mode(tagged, self.asset_id, self.rgba, independent=True), tagged)
        self.assertEqual(with_import_mode(tagged, self.asset_id, self.rgba, independent=False), self.png)

    def test_wrong_variant_changed_pixels_crc_and_unsupported_family_refuse(self):
        tagged = with_import_mode(self.png, self.asset_id, self.rgba, independent=True)
        for asset_id, rgba in (("tset:0:8:1:shoes02", self.rgba), (self.asset_id, bytes(len(self.rgba)))):
            with self.assertRaises(ValidationError):
                import_mode(tagged, asset_id, rgba)
        damaged = tagged.replace(OWN_TEXTURE.encode(), b"I" + OWN_TEXTURE.encode()[1:])
        with self.assertRaisesRegex(ValidationError, "checksum"):
            import_mode(damaged, self.asset_id, self.rgba)
        with self.assertRaisesRegex(ValidationError, "Only.*gloves and shoes"):
            with_import_mode(self.png, "tset:0:4:0:socks00", self.rgba, independent=True)

    def test_duplicate_mode_chunks_refuse(self):
        tagged = with_import_mode(self.png, self.asset_id, self.rgba, independent=True)
        start = tagged.index(INTENT_CHUNK) - 4
        end = start + struct.unpack_from(">I", tagged, start)[0] + 12
        doubled = tagged[:end] + tagged[start:end] + tagged[end:]
        with self.assertRaisesRegex(ValidationError, "repeats"):
            import_mode(doubled, self.asset_id, self.rgba)


if __name__ == "__main__":
    unittest.main()
