from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from mod_editor.core.nfl2k5_stadium_studio import StadiumTexture
from mod_editor.core.nfl2k5_stadium_texture_delegate import (
    Nfl2k5Cement01TextureDelegate,
)
from mod_editor.core.nfl2k5_stadium_texture_verify import _ledger
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    CompiledStadiumTextureEdit,
    FIXED_ALLOCATION_ERROR,
    Nfl2k5StadiumTextureWriter,
    STOCK_PNG_SHA256,
    STOCK_RGBA_SHA256,
    TARGET_SCENE_ID,
    TARGET_TEXTURE_ID,
    StadiumTextureWriterError,
    _decode_p8_mips,
    _generate_dynamic_mips,
    _generate_mips,
    _mip_dimensions,
    _rebuild_vc_lz_fixed_span,
)

from nfl_tset_png_import import palette_bytes, quantize_levels, rgba_from_indices
from nfl_txtr import HEADER, decompress_vc_lz, encode_rgba_png, swizzle_2d


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def target_texture(stock_png: Path) -> StadiumTexture:
    return StadiumTexture(
        texture_id=TARGET_TEXTURE_ID,
        scene_id=TARGET_SCENE_ID,
        texture_index=2,
        width=64,
        height=64,
        format_name="P8",
        rgba_sha256=STOCK_RGBA_SHA256,
        png_sha256=STOCK_PNG_SHA256,
        png_path=stock_png,
        mapped_material_names=("cement01",),
        mapped_material_count=1,
        access_status="Preview/Export-only",
    )


class FakeWriter:
    def __init__(self, root: Path, preview: bytes) -> None:
        self.cache = SimpleNamespace(root=root)
        self.preview = preview
        self.fail = False

    def supports(self, texture: StadiumTexture) -> bool:
        return texture.texture_id == TARGET_TEXTURE_ID

    def compile(
        self, texture: StadiumTexture, supplied_png: Path
    ) -> CompiledStadiumTextureEdit:
        if self.fail:
            raise StadiumTextureWriterError(FIXED_ALLOCATION_ERROR)
        payload = supplied_png.read_bytes()
        return CompiledStadiumTextureEdit(
            texture_id=texture.texture_id,
            replacement_png_sha256=digest(payload),
            replacement_rgba_sha256=digest(b"authored-rgba"),
            quantized_preview_png_sha256=digest(self.preview),
            quantized_base_rgba_sha256=digest(b"quantized-rgba"),
            mip_rgba_sha256=tuple(digest(bytes((index,))) for index in range(4)),
            quantization={"palette_entries": 2, "total_pixel_count": 5_440},
            palette_entries=2,
            decoded_after_sha256=digest(b"decoded"),
            decoded_changed_byte_count=42,
            encoded_sha256=digest(b"encoded"),
            encoded_bytes=123,
            zero_gap_bytes=7,
            minimum_alias_scratch_bytes=8,
            scratch_after=16,
            source_span_sha256=digest(b"synthetic-source"),
            rebuilt_span_sha256=digest(b"synthetic-span"),
            quantized_preview_png=self.preview,
            rebuilt_span=b"synthetic-span",
        )


class StadiumTextureWriterUnitTests(unittest.TestCase):
    def test_rectangular_dynamic_mip_chain_halves_each_axis(self) -> None:
        self.assertEqual(
            _mip_dimensions(128, 64, 4),
            ((128, 64), (64, 32), (32, 16), (16, 8)),
        )
        dimensions = _mip_dimensions(128, 64, 4)
        rgba = bytes((17, 34, 51, 255)) * (128 * 64)
        levels = _generate_dynamic_mips(rgba, dimensions)
        self.assertEqual(
            [(row.width, row.height, len(row.rgba)) for row in levels],
            [
                (128, 64, 128 * 64 * 4),
                (64, 32, 64 * 32 * 4),
                (32, 16, 32 * 16 * 4),
                (16, 8, 16 * 8 * 4),
            ],
        )
        self.assertTrue(all(level.rgba == bytes((17, 34, 51, 255)) *
                            (level.width * level.height) for level in levels))

    def test_generic_four_level_mips_and_p8_roundtrip(self) -> None:
        rgba = bytearray()
        for y in range(64):
            for x in range(64):
                rgba.extend((x * 4, y * 4, (x ^ y) * 4, 255))
        levels = _generate_mips(bytes(rgba))
        self.assertEqual(
            [(row.width, row.height) for row in levels],
            [(64, 64), (32, 32), (16, 16), (8, 8)],
        )
        palette, indices, _stats = quantize_levels(levels)
        swizzled = b"".join(
            swizzle_2d(values, level.width, level.height, 1)
            for level, values in zip(levels, indices)
        )
        decoded = bytearray(577_792 + 947_072)
        pixel = 577_792 + 0x17300
        palette_start = 577_792 + 0x18840
        decoded[pixel:pixel + len(swizzled)] = swizzled
        decoded[palette_start:palette_start + 1_024] = palette_bytes(palette)
        actual = _decode_p8_mips(bytes(decoded))
        expected = tuple(rgba_from_indices(values, palette) for values in indices)
        self.assertEqual(actual, expected)
        self.assertEqual(len(swizzled), 5_440)

    def test_fixed_span_preserves_tail_and_losslessly_decodes(self) -> None:
        decoded = bytes((index // 16) % 8 for index in range(2_048))
        tail = b"synthetic-tail!!"
        consumed_cap = 512
        stored = consumed_cap + len(tail)
        header = HEADER.pack(b"SCNE", stored, 1_024, 1_024, 0xFEEDBEEF, 0, 0, 0)
        result = _rebuild_vc_lz_fixed_span(
            decoded,
            header,
            tail,
            consumed_cap=consumed_cap,
            scratch_cap=4_096,
        )
        self.assertEqual(len(result.span), HEADER.size + stored)
        self.assertTrue(result.span.endswith(tail))
        decoded_back, info = decompress_vc_lz(
            result.span[HEADER.size:HEADER.size + consumed_cap], len(decoded)
        )
        self.assertEqual(decoded_back, decoded)
        self.assertEqual(info.consumed_bytes, result.encoded_bytes)
        self.assertEqual(
            result.span[HEADER.size + result.encoded_bytes:HEADER.size + consumed_cap],
            bytes(result.zero_gap_bytes),
        )

    def test_fixed_span_fails_closed_when_allocation_is_too_small(self) -> None:
        decoded = bytes(range(256)) * 4
        tail = b"0123456789abcdef"
        header = HEADER.pack(b"SCNE", 48, 512, 512, 0xFEEDBEEF, 0, 0, 0)
        with self.assertRaisesRegex(StadiumTextureWriterError, "fixed SCNE allocation"):
            _rebuild_vc_lz_fixed_span(
                decoded,
                header,
                tail,
                consumed_cap=32,
                scratch_cap=4_096,
            )

    def test_writer_support_is_exact_not_format_wide(self) -> None:
        writer = object.__new__(Nfl2k5StadiumTextureWriter)
        texture = target_texture(Path("stock.png"))
        self.assertTrue(writer.supports(texture))
        self.assertFalse(writer.supports(replace(texture, texture_index=3)))
        self.assertFalse(writer.supports(replace(texture, width=128)))
        self.assertFalse(writer.supports(replace(texture, mapped_material_names=("roof01",))))

    def test_dynamic_catalog_support_is_occurrence_exact(self) -> None:
        writer = object.__new__(Nfl2k5StadiumTextureWriter)
        first = target_texture(Path("first.png"))
        second = replace(
            first,
            texture_id="nfl2k5.stadium.o3280.c0005.scene2648.texture0004",
            texture_index=4,
            rgba_sha256="1" * 64,
            png_sha256="2" * 64,
            png_path=Path("second.png"),
            mapped_material_names=("ibeam01",),
        )
        writer._editable_textures = {  # type: ignore[attr-defined]
            first.texture_id: first,
            second.texture_id: second,
        }
        self.assertEqual(writer.editable_count, 2)
        self.assertTrue(writer.supports(first))
        self.assertTrue(writer.supports(second))
        self.assertIs(writer.texture(second.texture_id), second)
        self.assertFalse(writer.supports(replace(second, texture_index=5)))
        self.assertFalse(writer.supports(replace(second, png_path=Path("alias.png"))))
        with self.assertRaisesRegex(StadiumTextureWriterError, "private editable P8"):
            writer.texture("nfl2k5.stadium.o3280.c0005.scene2648.texture9999")

    def test_difference_ledger_is_deterministic(self) -> None:
        before = bytes(32 + 908_880)
        after = bytearray(before)
        after[10:13] = b"abc"
        after[-1] = 1
        first = _ledger(before, bytes(after))
        second = _ledger(before, bytes(after))
        self.assertEqual(first, second)
        self.assertEqual(first["changed_byte_count"], 4)
        self.assertEqual(first["changed_run_count"], 2)


class StadiumTextureDelegateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stock = self.root / "stock.png"
        self.stock.write_bytes(b"synthetic-stock-preview")
        self.authored = self.root / "replacement.png"
        self.authored_payload = encode_rgba_png(64, 64, bytes((255, 0, 255, 255)) * 4096)
        self.authored.write_bytes(self.authored_payload)
        self.preview = encode_rgba_png(64, 64, bytes((248, 0, 248, 255)) * 4096)
        self.writer = FakeWriter(self.root, self.preview)
        self.delegate = Nfl2k5Cement01TextureDelegate(self.writer)  # type: ignore[arg-type]
        self.texture = target_texture(self.stock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_replace_publishes_only_authored_and_derived_bytes_then_reverts(self) -> None:
        self.assertEqual(self.delegate.current_png(self.texture), self.stock)
        result = self.delegate.replace(self.texture, self.authored)
        self.assertEqual(result.preview_png.read_bytes(), self.preview)
        self.assertEqual(result.authored_png.read_bytes(), self.authored_payload)
        self.assertEqual(self.delegate.current_png(self.texture), result.preview_png)
        compiled = self.delegate.compiled_edit(self.texture)
        self.assertIsNotNone(compiled)
        document = json.loads((result.authored_png.parent / "metadata.json").read_text())
        self.assertFalse(document["contains_retail_bytes"])
        self.assertNotIn("rebuilt_span", document["compiled_metadata"])
        self.assertNotIn("quantized_preview_png", document["compiled_metadata"])
        self.assertTrue(self.delegate.revert(self.texture))
        self.assertEqual(self.delegate.current_png(self.texture), self.stock)
        self.assertFalse(result.authored_png.parent.exists())
        self.assertFalse(self.delegate.revert(self.texture))

    def test_failed_compile_leaves_previous_generation_active(self) -> None:
        first = self.delegate.replace(self.texture, self.authored)
        self.writer.fail = True
        with self.assertRaises(StadiumTextureWriterError):
            self.delegate.replace(self.texture, self.authored)
        self.assertEqual(self.delegate.current_png(self.texture), first.preview_png)
        self.assertTrue(first.preview_png.exists())


if __name__ == "__main__":
    unittest.main()
