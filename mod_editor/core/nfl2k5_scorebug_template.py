"""Bounded, lossless PNG-layer compiler for the experimental static scorebar.

Only authored pixels come from this folder. Native SCNE/TXTR structure comes
from the user's pinned game. A template cannot add cells, hooks or live fonts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path

SCHEMA = "nfl2k5_scorebug_template/v1"
DEFAULT_FOLDER = Path(__file__).resolve().parents[2] / "docs" / "scorebug_template"
MAX_FILE_BYTES = 512 * 1024
ATLAS_WRAPPER_SHA256 = "c66d9295ba01d8599ffaa2a489b5a78e1f5cadf0a79bb9f6239a052433921781"
ATLAS_SYSTEM_SHA256 = "7c4a0f68f81db5db40ebf33a3084e95f4b85f019774f6663302aa9ba85ceb170"
RAILS = [84, 381, 560, 429]
# Half-open atlas rectangles. Score layers replace part of their team block.
LAYERS = {
    "frame": ([0, 0, 64, 8], [84, 381, 560, 429]),
    "left_mark": ([0, 8, 64, 24], [88, 393, 156, 417]),
    "away_block": ([0, 24, 32, 40], [160, 383, 274, 427]),
    "home_block": ([32, 24, 64, 40], [438, 383, 558, 427]),
    "away_score": ([20, 24, 32, 40], [231, 383, 274, 427]),
    "home_score": ([32, 24, 44, 40], [438, 383, 483, 427]),
    "clock_quarter": ([0, 40, 64, 52], [278, 405, 434, 427]),
    "down": ([0, 52, 64, 64], [278, 383, 434, 404]),
}
REGIONS = {"frame": (0, 0, 64, 8), "mark": (0, 8, 64, 24),
           "away": (0, 24, 32, 40), "home": (32, 24, 64, 40),
           "strip": (0, 40, 64, 52), "down": (0, 52, 64, 64)}
ANCHORS = {"away_city": (-158, 10, -64), "home_city": (165, 10, -64),
           "away_score": (-68, -2, -59), "home_score": (138, -2, -59),
           "quarter": (-21, 0, -4), "clock_a": (72, 0, -4), "clock_b": (72, 0, -4),
           "drop_down": (36, 22, -4), "drop_clock": (95, 0, -4),
           "drop_yellow": (36, 22, -4), "drop_red": (36, 22, -4),
           "drop_ball_on": (36, 20, -4), "drop_hangtime": (36, 22, -4)}


class TemplateError(ValueError):
    """A plain, actionable authoring error, raised before image mutation."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as exc:
        raise TemplateError(f"Cannot read {path.name}: {exc.strerror or exc}") from exc
    if len(data) > limit:
        raise TemplateError(f"{path.name} is too large; keep each source file under {limit // 1024} KB.")
    return data


def _png(path: Path, size: tuple[int, int]):
    from PIL import Image, UnidentifiedImageError
    raw = _read(path)
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format != "PNG" or source.size != size:
                raise TemplateError(f"{path.name} must be a {size[0]} x {size[1]} PNG; do not resize its canvas.")
            if getattr(source, "n_frames", 1) != 1:
                raise TemplateError(f"{path.name} must be a single PNG image, without animation.")
            image = source.convert("RGBA")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise TemplateError(f"{path.name} is not a readable PNG.") from exc
    if len(set(image.getdata())) > 256:
        raise TemplateError(f"{path.name} has more than 256 colours. Export it with a smaller palette.")
    return image, sha(raw)


@dataclass
class CompiledTemplate:
    image: object
    receipt: dict


def compile_folder(folder: Path | str | None = None) -> CompiledTemplate:
    """Validate all selected layers and pack them, without reading any game art.

    PNGs at source_scale 1 or 2 are authoritative. 2x uses nearest-neighbour
    reduction so the compiler never introduces interpolated colours.
    SVGs, team variants and the proposed glyph sheet are authoring sources.
    """
    from PIL import Image
    root = Path(folder).expanduser().resolve() if folder else DEFAULT_FOLDER
    raw = _read(root / "layout.json")
    try:
        spec = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise TemplateError("layout.json must contain valid JSON.") from exc
    if not isinstance(spec, dict) or spec.get("schema") != SCHEMA:
        raise TemplateError("This folder is not a supported scorebar template. Start with the supplied layout.json.")
    scale = spec.get("source_scale")
    if type(scale) is not int or scale not in (1, 2):
        raise TemplateError("source_scale in layout.json must be 1 or 2.")
    expected = {name: {"atlas_rect": atlas, "hud_rect": hud} for name, (atlas, hud) in LAYERS.items()}
    if (spec.get("layers") != expected or spec.get("rails") != RAILS
            or spec.get("atlas_size") != [64, 64]
            or spec.get("live_text_anchors") != {key: list(value) for key, value in ANCHORS.items()}):
        raise TemplateError("The cell layout or live text anchors changed. Repaint the layers; this compiler keeps the supplied cell positions.")
    if spec.get("live_timeouts") is not False:
        raise TemplateError("Live timeout marks need the runtime owner. Keep live_timeouts false in this static template.")
    atlas = Image.new("RGBA", (64, 64))
    rows, colours = [], set()
    for name, (rect, hud) in LAYERS.items():
        x, y, right, bottom = rect
        size = (right - x, bottom - y)
        path = root / f"{scale}x" / f"{name}.png"
        image, digest = _png(path, (size[0] * scale, size[1] * scale))
        colours.update(image.getdata())
        if len(colours) > 256:
            raise TemplateError("The scorebar layers use more than 256 colours together. Export them with one shared palette.")
        if scale == 2:
            image = image.resize(size, Image.Resampling.NEAREST)
        # Replacement, including alpha, is deliberate: score-cell layers are
        # independently repaintable and do not inherit a hidden team gradient.
        atlas.paste(image, (x, y))
        rows.append({"layer": name, "path": f"{scale}x/{name}.png", "sha256": digest,
                     "atlas_rect": rect, "hud_rect": hud})
    pixels = atlas.tobytes()
    return CompiledTemplate(atlas, {"schema": SCHEMA, "layout_sha256": sha(raw),
        "source_scale": scale, "layers": rows, "rgba_sha256": sha(pixels),
        "colours": len(set(atlas.getdata())), "source_colours": len(colours),
        "palette_policy": "exact RGBA; at most 256 colours; no lossy fallback",
        "retail_art_used": False, "live_fonts": ["font1", "font2", "font5"],
        "custom_glyphs_installed": False, "runtime_team_selection": False,
        "live_timeouts": False, "experimental": True, "witnessed": False})


def encode_span(template: bytes, compiled: CompiledTemplate) -> tuple[bytes, dict]:
    """Keep native P8 system bytes and the complete fixed-span VC-LZ wrapper."""
    from . import nfl2k5_scorebug_ingame as r
    import nfl_tset_png_import as palettes
    if len(template) != 2432 or sha(template[:32]) != ATLAS_WRAPPER_SHA256:
        raise TemplateError("The scorebar's game allocation or wrapper changed. Rebuild from a supported clean base.")
    chunk, decoded, _ = r.decode(template)
    if sha(decoded[:128]) != ATLAS_SYSTEM_SHA256:
        raise TemplateError("The scorebar's game texture header changed. Rebuild from a supported clean base.")
    texture = r.tx.parse_texture(decoded, chunk)
    if (texture.width, texture.height, len(template)) != (64, 64, 2432):
        raise TemplateError("The scorebar atlas is not the supported 64 x 64 game resource.")
    if compiled.image.size != (64, 64):
        raise TemplateError("The packed scorebar must be a 64 x 64 image.")
    pixels = list(compiled.image.getdata())
    palette = sorted(set(pixels))
    if len(palette) > 256:
        raise TemplateError("The packed scorebar exceeds 256 colours. Use a shared palette.")
    indices = {color: index for index, color in enumerate(palette)}
    linear = bytes(indices[color] for color in pixels)
    rebuilt = decoded[:128] + r.tx.swizzle_2d(linear, 64, 64, 1) + palettes.palette_bytes(palette)
    attempts = []
    for encoder in ("greedy", "optimal"):
        try:
            result, info = r.fill.rebuild_fixed_span_filled(template, rebuilt, encoder=encoder)
            break
        except r.tx.TxtrError as exc:
            attempts.append(str(exc))
    else:
        raise TemplateError("The artwork is too detailed for the game's scorebar slot. Simplify gradients or use fewer colours; the game allocation cannot grow.")
    if result[:32] != template[:32] or len(result) != len(template) or r.decode(result)[1] != rebuilt:
        raise TemplateError("The scorebar failed its exact game-resource readback check.")
    return result, {"template": compiled.receipt, "encoder": encoder,
                   "palette_colors": len(palette), "filled_bytes": info.filled_bytes,
                   "wrapper_identical": True, "fit_attempts": attempts}


def stage_team_variant(team: str, *, side: str, folder=None) -> CompiledTemplate:
    """Pack one future 64x64 team atlas, without binding or installing it.

    The runtime owner may pass this result to encode_span, then register and
    select it on the independent side's material. The static installer never
    calls this function. No retail team logos are decoded.
    """
    from PIL import Image
    root = Path(folder).expanduser().resolve() if folder else DEFAULT_FOLDER
    teams = json.loads(_read(root / "teams.json"))
    if not isinstance(teams, list) or len(teams) != 32:
        raise TemplateError("teams.json must contain the supplied 32 team records.")
    identities = {row.get("abbr") for row in teams if isinstance(row, dict)}
    if len(identities) != 32 or any(not isinstance(value, str) or not value.isascii()
                                  or not value.isalpha() or not 2 <= len(value) <= 3 for value in identities):
        raise TemplateError("Use the supplied two- or three-letter team identifiers in teams.json.")
    if team not in identities or side not in ("away", "home"):
        raise TemplateError("Choose a team from teams.json and side away or home.")
    base = compile_folder(root)
    scale = base.receipt["source_scale"]
    block, block_sha = _png(root / "teams" / f"{scale}x" / f"{team}.png", (32*scale, 16*scale))
    if scale == 2:
        block = block.resize((32, 16), Image.Resampling.NEAREST)
    if side == "home":
        block = block.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    image = base.image.copy()
    region = REGIONS[side]
    image.paste(block, region[:2])
    score_rect = LAYERS[side + "_score"][0]
    image.paste(base.image.crop(score_rect), score_rect[:2])
    count = len(set(image.getdata()))
    if count > 256:
        raise TemplateError("The team block and scorebar together exceed 256 colours. Use a shared palette.")
    return CompiledTemplate(image, {**base.receipt, "rgba_sha256": sha(image.tobytes()),
        "colours": count, "staged_team": team, "staged_side": side,
        "team_source_sha256": block_sha, "installed": False, "runtime_team_selection": False})


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Check or install an experimental scorebar template.")
    parser.add_argument("command", choices=("validate", "apply"))
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--image", type=Path, help="An existing disposable output disc copy, for apply")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        compiled = compile_folder(args.folder)
        receipt = compiled.receipt
        if args.command == "apply":
            if args.image is None:
                parser.error("apply needs --image pointing to an output copy")
            from .nfl2k5_scorebug_ingame import apply_in_place
            receipt = apply_in_place(args.image, scorebug_folder=args.folder)
        encoded = json.dumps(receipt, indent=2) + "\n"
        if args.receipt:
            args.receipt.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Scorebar: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
