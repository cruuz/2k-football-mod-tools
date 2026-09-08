"""Inspect and preview the actual encoded number textures, without a display.

EXPERIMENTAL / UNWITNESSED. Decoding is exact. The flat, unlit preview assumes
straight-alpha bilinear filtering; the optional size view assumes trilinear
LOD = log2(base height / drawn cell height). Actual camera derivatives, UVs,
LOD bias, material blending and alpha testing require an in-game witness.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Iterable

from PIL import Image, ImageDraw

from .errors import ValidationError
from .nfl2k5_digit_sheet import DigitSheetPng, _targets

_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


@dataclass(frozen=True)
class DecodedDigitTexture:
    format_name: str
    packed_format: int
    alpha_bits: int
    palette: tuple[tuple[int, int, int, int], ...]
    levels: tuple[Any, ...]
    span_sha256: str


@dataclass(frozen=True)
class DigitSheetPreview:
    png: bytes
    details: str
    receipts: tuple[dict[str, Any], ...]


def decode_digit_texture(span: bytes) -> DecodedDigitTexture:
    """Read every swizzled index and the shared palette after decompression."""
    import nfl_live_numbers_nameplate_png_import as writer
    from nfl_txtr import decode_chunk, parse_chunks, parse_texture

    if not 32 <= len(span) <= 128 * 1024:
        raise ValidationError("The encoded digit texture has an invalid size.")
    chunks = parse_chunks(span)
    if (len(chunks) != 1 or chunks[0].kind != "TXTR"
            or chunks[0].system_bytes != 128 or not 1024 < chunks[0].video_bytes <= 8192):
        raise ValidationError("The encoded digit texture has an unsupported allocation.")
    chunk = chunks[0]
    decoded, _ = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    if (texture.format_name != "P8" or texture.width not in (32, 64)
            or texture.height != texture.width or not 1 <= texture.mip_levels <= 4):
        raise ValidationError("Preview requires a supported 32 or 64 pixel P8 digit.")
    return DecodedDigitTexture(
        texture.format_name, texture.packed_format, 8,
        tuple(writer.parse_palette(decoded[chunk.system_bytes:], texture.palette_offset)),
        tuple(writer.decode_levels(decoded, chunk, texture)),
        hashlib.sha256(span).hexdigest(),
    )


def _filtered_level(level: Any, size: tuple[int, int]) -> Image.Image:
    # Pixel-centre bilinear sampling with clamp-to-edge addressing. Pillow's
    # downscaling BILINEAR widens the footprint as an antialiasing filter, which
    # would conceal coarse edges when displaying a deliberately selected mip.
    def taps(source: int, destination: int):
        for i in range(destination):
            position = (i + 0.5) * source / destination - 0.5
            low = math.floor(position)
            yield max(0, min(source - 1, low)), max(0, min(source - 1, low + 1)), position - low

    columns, rows = tuple(taps(level.width, size[0])), tuple(taps(level.height, size[1]))
    pixels = level.rgba
    output = bytearray(size[0] * size[1] * 4)
    for y, (top, bottom, vertical) in enumerate(rows):
        for x, (left, right, horizontal) in enumerate(columns):
            offsets = tuple((row * level.width + column) * 4
                            for row, column in ((top, left), (top, right), (bottom, left), (bottom, right)))
            for channel in range(4):
                upper = pixels[offsets[0] + channel] * (1 - horizontal) + pixels[offsets[1] + channel] * horizontal
                lower = pixels[offsets[2] + channel] * (1 - horizontal) + pixels[offsets[3] + channel] * horizontal
                output[(y * size[0] + x) * 4 + channel] = round(upper * (1 - vertical) + lower * vertical)
    return Image.frombytes("RGBA", size, bytes(output))


def render_digit_sample(
    texture: DecodedDigitTexture, *, height: int = 24, level: int | None = None,
    background: tuple[int, int, int] = (20, 40, 60),
) -> Image.Image:
    """Render a selected mip, or an explicitly assumed LOD, at jersey size."""
    if type(height) is not int or not 1 <= height <= 512:
        raise ValidationError("Preview height must be from 1 through 512 pixels.")
    if level is not None and (type(level) is not int or not 0 <= level < len(texture.levels)):
        raise ValidationError("That mip level is absent from the encoded digit.")
    base = texture.levels[0]
    size = (max(1, round(height * base.width / base.height)), height)
    lod = (float(level) if level is not None else
           min(len(texture.levels) - 1, max(0., math.log2(base.height / height))))
    first, second = math.floor(lod), math.ceil(lod)
    sampled = _filtered_level(texture.levels[first], size)
    if first != second:
        sampled = Image.blend(sampled, _filtered_level(texture.levels[second], size), lod - first)
    canvas = Image.new("RGBA", size, (*background, 255))
    return Image.alpha_composite(canvas, sampled).convert("RGB")


def render_digit_sheet_preview(
    rows: Iterable[tuple[int, DecodedDigitTexture]],
) -> bytes:
    """Ten numbered rows, all encoded mips and two assumed camera sizes."""
    entries = tuple(rows)
    if len(entries) != 10 or sorted(d for d, _ in entries) != list(range(10)):
        raise ValidationError("Preview needs encoded digits 0 through 9 exactly once.")
    canvas = Image.new("RGB", (730, 70 + len(entries) * 78), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), "Encoded number preview: EXPERIMENTAL / UNWITNESSED", fill=(20, 20, 20))
    draw.text((12, 25), "Saved levels at 32px; small views estimate camera detail without jersey lighting.", fill=(20, 20, 20))
    for x, title in ((12, "Digit"), (75, "Level 0"), (190, "Level 1"), (305, "Level 2"),
                     (420, "Level 3"), (555, "24px"), (650, "12px")):
        draw.text((x, 45), title, fill=(20, 20, 20))
    for row, (digit, texture) in enumerate(sorted(entries, key=lambda item: item[0])):
        y = 70 + row * 78
        draw.text((16, y + 10), str(digit), fill=(20, 20, 20))
        for level, mip in enumerate(texture.levels):
            x = 75 + level * 115
            for dy, bg in ((0, (20, 40, 60)), (34, (235, 235, 235))):
                canvas.paste(render_digit_sample(texture, height=32, level=level, background=bg), (x, y + dy))
            draw.text((x + 35, y + 10), f"{mip.width}px", fill=(20, 20, 20))
        for x, size in ((555, 24), (650, 12)):
            canvas.paste(render_digit_sample(texture, height=size), (x, y))
            canvas.paste(render_digit_sample(texture, height=size, background=(235, 235, 235)), (x, y + 34))
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def preview_digit_sheet(
    index: Path, assets: Iterable[object], outputs: Iterable[DigitSheetPng],
    progress: Callable[[str, int, int], None] | None = None,
) -> DigitSheetPreview:
    """Run the build's pinned writer for every split PNG before staging edits.

    Only tiny temporary PNGs are written. No archive pack or disc is copied or
    modified. Returning no result on any failure lets the GUI refuse the whole
    sheet before its ordinary Team Kit transaction starts.
    """
    import nfl_live_numbers_nameplate_png_import as writer
    from nfl_live_numbers_nameplate_targets import DEFAULT_REPORT

    targets, images = _targets(assets), tuple(outputs)
    if len(images) != 10 or any(
        (output.digit, output.asset_id, output.width, output.height)
        != (digit, target.asset_id, target.width, target.height)
        for digit, (target, output) in enumerate(zip(targets, images))
    ):
        raise ValidationError("Preview images do not match the selected ten digit slots.")
    rows, receipts, notes = [], [], []
    with tempfile.TemporaryDirectory(prefix="2k5-digit-preview-") as temporary:
        root = Path(temporary).resolve(strict=True)
        for target, output in zip(targets, images):
            path = root / f"{output.digit}.png"
            path.write_bytes(output.png)
            if progress:
                progress(f"Encoding digit {output.digit} for preview", output.digit, 10)
            try:
                span, _, receipt = writer.build_import(
                    index, DEFAULT_REPORT, target.family, target.asset_code,
                    target.side_code, target.variant, output.digit, path,
                )
            except ValueError as exc:
                raise ValidationError(f"Digit {output.digit}: {exc} {output.mapping_note}") from exc
            texture = decode_digit_texture(span)
            rows.append((output.digit, texture))
            receipts.append(receipt)
            notes.append(output.mapping_note)
            notes.extend(output.warnings)
            fit = receipt.get("bounded_palette_fit", {})
            if len(fit.get("attempts", ())) > 1:
                notes.append(f"Digit {output.digit}: reduced to {receipt['quantization']['palette_entries']} palette colours "
                             "to fit the fixed texture slot; inspect the encoded preview.")
            if receipt["quantization"].get("approximated_opaque_colours", 0):
                notes.append(f"Digit {output.digit}: many solid colours; some were approximated.")
    notes.extend((
        "P8: one shared palette, 8-bit alpha; all stored mip levels regenerated.",
        "Use straight-alpha PNG. Already darkened (premultiplied) RGB is not automatically repaired.",
        "The game adds jersey material, lighting and camera-dependent sampling. Verify broadcast and close views.",
    ))
    return DigitSheetPreview(render_digit_sheet_preview(rows), "\n".join(dict.fromkeys(notes)), tuple(receipts))
