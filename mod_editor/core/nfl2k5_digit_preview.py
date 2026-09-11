"""Inspect and preview the actual encoded number textures, without a display.

EXPERIMENTAL / UNWITNESSED. Decoding is exact. The flat, unlit preview assumes
straight-alpha bilinear filtering; the optional size view assumes trilinear
LOD = log2(base height / drawn cell height). Actual camera derivatives, UVs,
LOD bias, material blending and alpha testing require an in-game witness.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
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

    @property
    def kept_retail_count(self) -> int:
        return sum(bool(row.get("kept_retail")) for row in self.receipts)

    @property
    def import_count(self) -> int:
        return len(self.receipts) - self.kept_retail_count

    @property
    def import_button_text(self) -> str:
        return f"Import {self.import_count} digits, {self.kept_retail_count} kept retail"


def jersey_preview_colour(path: Path) -> tuple[int, int, int]:
    """Dominant opaque base shade from the current jersey, without its lighting."""
    with Image.open(path) as opened:
        if opened.width * opened.height > 16_000_000:
            raise ValidationError("The jersey preview image is too large.")
        colours = Counter(c[:3] for c in opened.convert("RGBA").getdata() if c[3] >= 240)
    if not colours:
        raise ValidationError("The jersey preview has no opaque base colour.")
    buckets = Counter()
    for colour, count in colours.items():
        buckets[tuple(c//16 for c in colour)] += count
    bucket = max(buckets, key=lambda b: (buckets[b], b))
    kept = [(colour, count) for colour, count in colours.items() if tuple(c//16 for c in colour) == bucket]
    weight = sum(count for _, count in kept)
    return tuple(round(sum(colour[k]*count for colour,count in kept)/weight) for k in range(3))


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


def _filtered_level(level: Any, size: tuple[int, int], *, uv_bounds=(0., 0., 1., 1.)) -> Image.Image:
    # Pixel-centre bilinear sampling with clamp-to-edge addressing. Pillow's
    # downscaling BILINEAR widens the footprint as an antialiasing filter, which
    # would conceal coarse edges when displaying a deliberately selected mip.
    def taps(source: int, destination: int, low_uv: float, high_uv: float):
        for i in range(destination):
            position = (low_uv + (i + 0.5) * (high_uv-low_uv) / destination) * source - 0.5
            low = math.floor(position)
            yield max(0, min(source - 1, low)), max(0, min(source - 1, low + 1)), position - low

    columns = tuple(taps(level.width, size[0], uv_bounds[0], uv_bounds[2]))
    rows = tuple(taps(level.height, size[1], uv_bounds[1], uv_bounds[3]))
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
    *, retail_rows: Iterable[tuple[int, DecodedDigitTexture]] | None = None,
    kept_retail: Iterable[int] = (),
    background: tuple[int, int, int] = (20, 40, 60),
) -> bytes:
    """Ten numbered rows, all encoded mips and two assumed camera sizes."""
    entries = tuple(rows)
    originals = dict(retail_rows) if retail_rows is not None else {}
    kept = set(kept_retail)
    if len(entries) != 10 or sorted(d for d, _ in entries) != list(range(10)):
        raise ValidationError("Preview needs encoded digits 0 through 9 exactly once.")
    canvas = Image.new("RGB", (730, 70 + len(entries) * 78), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), "Saved digits. In-game appearance UNWITNESSED.", fill=(20, 20, 20))
    draw.text((12, 25), "Top: build result. Bottom: retail. Sizes estimate camera detail.", fill=(20, 20, 20))
    if originals:
        for x, textures, label in ((520, dict(entries), "57 build"), (630, originals, "57 retail")):
            for n, digit in enumerate((5, 7)):
                canvas.paste(render_digit_sample(textures[digit], height=24, background=background), (x+n*24, 3))
            draw.text((x, 28), label, fill=(20, 20, 20))
    for x, title in ((12, "Digit"), (75, "Level 0"), (190, "Level 1"), (305, "Level 2"),
                     (420, "Level 3"), (555, "24px"), (650, "12px")):
        draw.text((x, 45), title, fill=(20, 20, 20))
    for row, (digit, texture) in enumerate(sorted(entries, key=lambda item: item[0])):
        y = 70 + row * 78
        draw.text((16, y + 10), str(digit), fill=(20, 20, 20))
        if digit in kept:
            draw.rectangle((3, y+32, 69, y+61), fill=(255, 215, 128))
            draw.text((6, y+33), "KEPT", fill=(65, 35, 0))
            draw.text((6, y+46), "RETAIL", fill=(65, 35, 0))
        for level, mip in enumerate(texture.levels):
            x = 75 + level * 115
            for dy, sample in ((0, texture), (34, originals.get(digit, texture))):
                canvas.paste(render_digit_sample(sample, height=32, level=level, background=background), (x, y + dy))
            draw.text((x + 35, y + 10), f"{mip.width}px", fill=(20, 20, 20))
        for x, size in ((555, 24), (650, 12)):
            canvas.paste(render_digit_sample(texture, height=size, background=background), (x, y))
            canvas.paste(render_digit_sample(originals.get(digit, texture), height=size, background=background), (x, y + 34))
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def preview_digit_sheet(
    index: Path, assets: Iterable[object], outputs: Iterable[DigitSheetPng],
    progress: Callable[[str, int, int], None] | None = None,
    *, background: tuple[int, int, int] = (20, 40, 60),
) -> DigitSheetPreview:
    """Run the build's pinned writer for every split PNG before staging edits.

    Only tiny temporary PNGs are written. No archive pack or disc is copied or
    modified. A digit that cannot fit its slot at the quality floor is shown
    as the RETAIL texture with a ``kept_retail`` receipt and a note, which is
    exactly what the build does with it; any other failure returns no result
    so the GUI refuses the whole sheet before its Team Kit transaction starts.
    """
    import nfl_live_numbers_nameplate_png_import as writer
    from nfl_live_numbers_nameplate_targets import DEFAULT_REPORT, select_target
    from nfl_tset_png_import import QualityBudgetError
    from .nfl2k5_digit_art import kept_retail_reason

    targets, images = _targets(assets), tuple(outputs)
    if len(images) != 10 or any(
        (output.digit, output.asset_id, output.width, output.height)
        != (digit, target.asset_id, target.width, target.height)
        for digit, (target, output) in enumerate(zip(targets, images))
    ):
        raise ValidationError("Preview images do not match the selected ten digit slots.")
    rows, retail_rows, receipts, notes = [], [], [], []
    archive = None
    with tempfile.TemporaryDirectory(prefix="2k5-digit-preview-") as temporary:
        root = Path(temporary).resolve(strict=True)
        for target, output in zip(targets, images):
            path = root / f"{output.digit}.png"
            path.write_bytes(output.png)
            if progress:
                progress(f"Encoding digit {output.digit} for preview", output.digit, 10)
            _, _, slot = select_target(target.family, target.asset_code, target.side_code,
                                       target.variant, output.digit, DEFAULT_REPORT)
            if archive is None:
                archive = writer.parse_archive(index)
            retail_span = writer.read_entry_range(archive, archive.entries[slot.outer_index],
                                                   slot.chunk_offset, slot.span_size)
            writer.validate_template(retail_span, slot)
            retail_rows.append((output.digit, decode_digit_texture(retail_span)))
            try:
                span, _, receipt = writer.build_import(
                    index, DEFAULT_REPORT, target.family, target.asset_code,
                    target.side_code, target.variant, output.digit, path,
                )
            except QualityBudgetError as exc:
                # The build keeps the RETAIL digit for a slot whose art cannot
                # fit at the quality floor (beta-63.1), so the preview shows
                # that same outcome: the retail texture in this row, and a
                # note that names the slot and its allocation.
                span = retail_span
                reason = kept_retail_reason(slot.stored_size)
                receipt = {
                    "kept_retail": True,
                    "target": {"selector": slot.selector, "stored_size": slot.stored_size},
                    "reason": reason,
                    "digit_preparation": getattr(exc, "preparation", None),
                    "fit_attempts": list(getattr(exc, "attempts", ())),
                    "replacement": {"span_sha256": hashlib.sha256(span).hexdigest()},
                    "quantization": {},
                }
                notes.append(f"Digit {output.digit}: {reason}")
            except ValueError as exc:
                raise ValidationError(f"Digit {output.digit}: {exc} {output.mapping_note}") from exc
            texture = decode_digit_texture(span)
            rows.append((output.digit, texture))
            receipts.append(receipt)
            notes.append(output.mapping_note)
            if receipt.get("digit_outcome"):
                notes.append(f"Digit {output.digit}: {receipt['digit_outcome']}")
                registration = receipt["digit_preparation"]["registration"]
                notes.append(f"Box {registration['destination_box']}, scale {registration['scale']:.4f}; "
                             "alpha bound, near colours merged, one texel soft edge, edge colours extended.")
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
    return DigitSheetPreview(render_digit_sheet_preview(
        rows, retail_rows=retail_rows,
        kept_retail=(i for i, r in enumerate(receipts) if r.get("kept_retail")), background=background),
        "\n".join(dict.fromkeys(notes)), tuple(receipts))
