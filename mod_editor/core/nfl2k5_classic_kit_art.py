"""Authored finishing for the classic teams' kit packages (job b778 ss2).

The shared kit composer (``nfl2k5_moment_kits.compose_side``) builds a package from donor chunks, palette maps and
painted texture rows. Two things it could not express are done here, both optional per kit side in the kit document:

* ``atlas.ops``: operations on the far-player atlas (``splayer``, 256x128 A8R8G8B8, five mips) after its donor
  rectangles are mixed. The atlas is the texture the game draws on every player past the near cameras, so it must
  carry the same colours, anchor and trim as the near textures. ``remap`` moves a whole colour scheme with the shades
  and blends kept (``nfl2k5_kit_fixes_2026.remap_colours``); the other operations are the kit painter's (``poly``,
  ``multipoly``, ``copy``...). Changed regions are re-filtered into the lower mips; untouched texels keep the
  donor's mips.
* ``unif_colours``: the Unif chunk's facemask and turtleneck words (RGB hex), written as the game stores them
  (B, G, R, 255).
"""
from __future__ import annotations

import struct

import numpy as np

from nfl_txtr import parse_chunks, parse_texture, swizzle_2d, unswizzle_2d

UNIF_COLOURS = 0x50


class ClassicKitArtError(ValueError):
    """An atlas operation or colour word is not usable."""


def require(ok, message):
    if not ok:
        raise ClassicKitArtError("classic kit art: " + message)


def _hex(text):
    require(isinstance(text, str) and len(text) == 7 and text[0] == "#", "colour must be #RRGGBB")
    return tuple(int(text[k:k + 2], 16) for k in (1, 3, 5))


def unif_words(unif_colours):
    """The 8 bytes of the facemask and turtleneck words for ``unif_colours`` = ["#RRGGBB", "#RRGGBB"]."""
    require(isinstance(unif_colours, (list, tuple)) and len(unif_colours) == 2, "unif_colours needs two colours")
    out = bytearray()
    for colour in unif_colours:
        r, g, b = _hex(colour)
        out += bytes((b, g, r, 255))
    return bytes(out)


def _levels(width, height, count):
    return [(max(1, width >> i), max(1, height >> i)) for i in range(count)]


def _read(mixed, system, levels):
    arrays, cursor = [], system
    for w, h in levels:
        raw = unswizzle_2d(mixed[cursor:cursor + w * h * 4], w, h, 4)
        bgra = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
        arrays.append(bgra[..., [2, 1, 0, 3]].copy())
        cursor += w * h * 4
    return arrays


def _write(arrays, levels):
    out = []
    for rgba, (w, h) in zip(arrays, levels):
        bgra = np.ascontiguousarray(rgba[..., [2, 1, 0, 3]], np.uint8).tobytes()
        out.append(swizzle_2d(bgra, w, h, 4))
    return b"".join(out)


def atlas_edit(mixed, chunk, ops, *, width=256, height=128, mips=5):
    """``mixed`` (the converted atlas: system bytes then every mip as swizzled A8R8G8B8) with ``ops`` applied to level 0."""
    from . import nfl2k5_kit_fixes_2026 as fixes
    system = chunk.system_bytes
    levels = _levels(width, height, mips)
    require(len(mixed) == system + sum(w * h * 4 for w, h in levels), "atlas allocation differs")
    arrays = _read(mixed, system, levels)
    base = arrays[0].copy()
    work = base.copy()
    for op in ops:
        if op["op"] == "remap":
            x0, y0, x1, y1 = (int(v) for v in op.get("box", (0, 0, width, height)))
            pairs = [(a, b) for a, b in op["pairs"]]
            region = work[y0:y1, x0:x1, :3]
            moved, hit = fixes.remap_colours(region.reshape(-1, 3), pairs, int(op.get("tolerance", 12)))
            region[...] = np.where(hit.reshape(region.shape[:2])[..., None], moved.reshape(region.shape), region)
        else:
            work, _scope = fixes.paint(work, [op])
    changed = np.any(work != base, axis=2)
    require(changed.any(), "the atlas operations changed nothing")
    arrays[0] = work
    for level in range(1, mips):
        h, w = arrays[level].shape[:2]
        child = arrays[level - 1].astype(np.int64)
        box = (child.reshape(h, 2, w, 2, 4).sum(axis=(1, 3)) + 2) // 4
        changed = changed.reshape(h, 2, w, 2).any(axis=(1, 3))
        arrays[level] = np.where(changed[..., None], box, arrays[level]).astype(np.uint8)
    return mixed[:system] + _write(arrays, levels)


def anchor_ops(polys, colours, *, alpha=None):
    """Kit painter operations for the Seamen anchor: ``polys`` = {"ink": [...], "fill": [...], "islands": [...]} in
    texel coordinates (``ss2_art.anchor_polys``); ``colours`` = {"ink": "#RRGGBB", "fill": "#RRGGBB"}."""
    ops = []
    for key, colour in (("ink", colours["ink"]), ("fill", colours["fill"]), ("islands", colours["ink"])):
        if not polys[key]:
            continue
        op = {"op": "multipoly", "color": colour,
              "polys": [[[round(x, 2), round(y, 2)] for x, y in poly] for poly in polys[key]]}
        if alpha is not None:
            op["alpha"] = alpha
        ops.append(op)
    return ops
