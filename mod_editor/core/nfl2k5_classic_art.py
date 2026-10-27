"""Authored classic-team menu cards: the Team Select logo, helmet and uniform cards (job b778-ss1).

The classic-teams stage installs its authored kit through the Anniversary kit compositor, which copies the donor's
nine aggregate card members under the new index. This module replaces those copies with PNG art: each member is a
raw P8 TXTR slot (one mip, 256x256 for the logo/helmet/uniform cards and 64x64 for the mini cards and flipchip), so
the PNG is quantized to a 256-entry palette and written into the same fixed video allocation. Nothing grows: the
system buffer, wrapper and stored size stay the donor's, and the slot is then renamed to the new member name.
"""
from __future__ import annotations

from pathlib import Path
import struct
import hashlib

ROOT = Path(__file__).resolve().parents[2]
CARDS = ROOT / "data/nfl2k5_classic_teams/cards"

CARD_ART = {
    "logo": "logo.png",
    "logo_s": "logo_s.png",
    "helm_h": "helm_h.png",
    "helm_a": "helm_a.png",
    "unif_h": "unif_h.png",
    "unif_a": "unif_a.png",
    "mini_h": "mini_h.png",
    "mini_a": "mini_a.png",
    "flipchip": "logo_s.png",
}


class ClassicArtError(ValueError):
    """A card target or PNG is not the proved raw P8 card layout."""


def require(ok, message):
    if not ok:
        raise ClassicArtError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rgba_png(path):
    import sys
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import nfl_tset_png_import as png
    payload = Path(path).read_bytes()
    return png, png.decode_rgba_png(payload, expected_dimensions=None)


def card_art(kit):
    """{new member name: (card key, art file)} for the cards this kit authors; empty for the Anniversary kits."""
    art = kit.get("card_art")
    if not art:
        return {}
    require(isinstance(art, dict), kit["id"] + ": card_art must be an object")
    require(set(art) <= set(CARD_ART), kit["id"] + ": unknown card art key")
    code, style = kit["code"], kit["style"]
    out = {}
    for key, filename in art.items():
        require(isinstance(filename, str) and Path(filename).name == filename
                and filename.lower().endswith(".png"), kit["id"] + ": unsafe card art filename")
        if key == "flipchip":
            out[f"{code}_flipchip_00_h{style}"] = (key, filename)
        elif key == "logo":
            out[f"logo_{code}_{style}"] = (key, filename)
        elif key == "logo_s":
            out[f"logo_s{code}_{style}"] = (key, filename)
        else:
            out[f"{key}{code}_{style}"] = (key, filename)
    return out


def authored_slot(slot, key, path, name, *, root=CARDS):
    """The donor P8 card slot with the PNG's pixels in its fixed video allocation, renamed to ``name``."""
    from . import nfl2k5_historic_styles as hs
    require(key in CARD_ART, "unknown card art key " + str(key))
    png, decoded_png = _rgba_png(Path(root) / path)
    require(isinstance(decoded_png, tuple) and len(decoded_png) == 3, "card PNG read-back")
    width, height, rgba = decoded_png
    require(width == height and width in (64, 128, 256), "card PNG must be square 64, 128 or 256")
    from nfl_txtr import parse_chunks, decode_chunk, parse_texture, texture_to_rgba
    chunks = parse_chunks(slot, allow_trailing=True)
    require(len(chunks) == 1, "a card slot holds one TXTR resource")
    chunk = chunks[0]
    require(chunk.kind == "TXTR" and not chunk.compressed and chunk.video_bytes == width * height + 1024,
            "card target is not a raw one-mip P8 TXTR")
    decoded, _info = decode_chunk(slot, chunk)
    texture = parse_texture(decoded, chunk)
    require(texture.format_name == "P8" and texture.mip_levels == 1
            and (texture.width, texture.height) == (width, height)
            and texture.palette_offset == width * height and texture.pixel_offset == 0,
            "card target descriptor differs")
    require(len(decoded) == chunk.system_bytes + chunk.video_bytes, "card decoded size differs")
    level = png.MipLevel(0, width, height, rgba)
    palette, index_levels, _quantization = png.quantize_levels([level])
    require(len(index_levels) == 1 and len(index_levels[0]) == width * height, "card index count differs")
    swizzled = png.swizzle_2d(index_levels[0], width, height, 1)
    palette_bgra = png.palette_bytes(palette)
    require(len(swizzled) + len(palette_bgra) == chunk.video_bytes, "card video allocation differs")
    rebuilt = decoded[:chunk.system_bytes] + swizzled + palette_bgra
    require(len(rebuilt) == len(decoded), "card decoded size changed")
    span = slot[:chunk.end_offset]
    new_span = span[:32] + rebuilt
    out = new_span + slot[chunk.end_offset:]
    require(len(out) == len(slot) and out[:32] == slot[:32] and out[32:32 + chunk.system_bytes] == decoded[:chunk.system_bytes],
            "card wrapper/system bytes changed")
    out = hs.rename_slot(out, name)
    check_chunks = parse_chunks(out, allow_trailing=True)
    check_decoded, _ = decode_chunk(out, check_chunks[0])
    check_texture = parse_texture(check_decoded, check_chunks[0])
    expected = png.rgba_from_indices(index_levels[0], palette)
    actual = texture_to_rgba(check_decoded, check_chunks[0], check_texture)
    require(actual == expected, "card PNG round trip differs")
    require(hs.slot_name(out) == name, "card member rename differs")
    require(check_texture.width == width and check_texture.height == height, "card size read-back differs")
    return out, dict(member=name, art=path, size=[width, height], palette_entries=len(palette),
                     sha256=_sha(out))
