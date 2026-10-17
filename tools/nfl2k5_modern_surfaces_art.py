"""Author the Modern playing surfaces art (data/nfl2k5_modern_surfaces/art/*.png).

Everything here is procedural and deterministic (fixed seeds, no photos, no image models, no logos):

* ``detail_<kind>.png``: the field's ``detail_normal`` texture for one surface kind, a palette PNG whose pixels are
  the six mip levels packed in one 512 x 384 atlas (mip 0 at (0, 0) 512 x 256; mip 1 at (0, 256); mip 2 at
  (256, 256); mip 3 at (384, 256); mip 4 at (448, 256); mip 5 at (480, 256)). tf-v3 (2026-09-27): the texture the
  game SHOWS is the palette alpha (in game the field's brightness follows it almost proportionally, and the retail
  map's visible grain goes with its alpha, while tf-v1's tilted normals under a constant alpha showed nothing even up
  close), so the 256 entries are one flat normal (128, 128, 255) with alpha = the entry's index, and the pixels carry
  short blades or fibres (2 to 3.5 texels, 2.5 to 4.5 cm at the game's 1.27 cm per texel) with dark gaps. tf-v4
  (gr2/gr3, Noah 2026-10-16): the levels are PREMIPPED. Each mip is the 2 x 2 box of the one above mixed with fresh
  per-level clump noise at that level's own texel scale (FRESH, CLUMP_SIGMA), so the grain survives to the mips the
  gameplay camera samples instead of averaging away, and the PNG holds them at FULL strength (candidate A's spreads,
  ``DETAIL_REL_FULL`` in the module) around the kind's alpha (the mean the in-game brightness was measured with). The
  module scales each level's spread down to the strength a build asks for (``DETAIL_STRENGTH``: turf 15 %, grass 20 %
  of the way from tf-v3.1's spreads to A's). Every structure stays within a texel or two of its own level because the
  game maps this texture per triangle with discontinuous UVs (592 of the 618 shared positions of E_detail): anything
  longer shows the triangle lattice.
* ``detail_<kind>_tile.png``: a tileable 64 x 64 version of the same kind (mips packed in a 64 x 96 atlas) for the
  venues whose detail normal is a compressed chunk (the Colts and Vikings sets s11, s15): repeated, it fits their
  fixed span.
* ``pattern_<look>.png``: an 8-bit grey atlas of luminance patterns (128 = the surface mean, 1 unit = 1/128):
  rows 0..63 the 128 x 64 colour map (one period: 10 yards along the field in u, 10 yards across in v), rows
  64..191 the 128 x 128 colour map for fields whose colour quad borrows the outside-grass texture, rows 192..319
  the 128 x 128 outside-grass pattern.

The build (mod_editor/core/nfl2k5_modern_surfaces.py) reads these files; it never regenerates them, so the shipped
bytes do not depend on the floating-point library of the machine that builds a disc.

    python3 tools/nfl2k5_modern_surfaces_art.py [--out DIR] [--masters DIR]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402  (the spreads and alphas the build uses)
OUT = ROOT / "data" / "nfl2k5_modern_surfaces" / "art"
MIP_ORIGINS = ((0, 0), (0, 256), (256, 256), (384, 256), (448, 256), (480, 256))
DETAIL_KINDS = ("fibre", "helix", "blade_bermuda", "blade_bluegrass")

# Look -> (pattern kind, parameters). Band contrast is +- the fraction of luminance per 5-yard band.
LOOK_PATTERNS = {
    # the colour map carries the bands and a smooth mottle only: the field span is a fixed VC-LZ allocation, and
    # per-texel noise would not fit; the fine texture lives in the detail normal (a raw chunk, any content fits)
    "synthetic_fieldturf": dict(pattern="bands", band=0.070, mottle=0.010, mottle_scale=40, speckle=0.0, seed=11),
    "synthetic_helix": dict(pattern="bands", band=0.095, mottle=0.012, mottle_scale=32, speckle=0.0, seed=12),
    "synthetic_vivid": dict(pattern="bands", band=0.060, mottle=0.008, mottle_scale=40, speckle=0.0, seed=13),
    "grass_bluegrass": dict(pattern="bands", band=0.050, mottle=0.035, mottle_scale=16, speckle=0.0, seed=14),
    "grass_bermuda": dict(pattern="bands", band=0.060, mottle=0.040, mottle_scale=14, speckle=0.0, seed=15),
    "grass_checker": dict(pattern="checker", band=0.050, mottle=0.035, mottle_scale=14, speckle=0.0, seed=16),
}


# ------------------------------------------------------------------ deterministic helpers
def rng(seed):
    return np.random.default_rng(seed)


def tile_noise(h, w, cells_y, cells_x, r):
    """Tileable smooth value noise in [-1, 1] on a (cells_y x cells_x) lattice."""
    g = r.uniform(-1, 1, (cells_y, cells_x))
    ys = np.arange(h) / h * cells_y
    xs = np.arange(w) / w * cells_x
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[y0 % cells_y][:, x0 % cells_x]
    b = g[y0 % cells_y][:, (x0 + 1) % cells_x]
    c = g[(y0 + 1) % cells_y][:, x0 % cells_x]
    d = g[(y0 + 1) % cells_y][:, (x0 + 1) % cells_x]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def fractal(h, w, base_cells, r, octaves=3):
    out = np.zeros((h, w))
    amp, tot, cells = 1.0, 0.0, base_cells
    for _ in range(octaves):
        out += amp * tile_noise(h, w, max(1, round(h / cells)), max(1, round(w / cells)), r)
        tot += amp
        amp *= 0.5
        cells = max(1, cells / 2)
    return out / tot


def square_wave(n, periods, supersample=16):
    """Area-averaged +1/-1 square wave over n texels with `periods` full periods (+1 first half)."""
    t = (np.arange(n * supersample) + 0.5) / (n * supersample) * periods
    return np.where((t % 1.0) < 0.5, 1.0, -1.0).reshape(n, supersample).mean(1)


# ------------------------------------------------------------------ colour map patterns
def pattern(look, h, w, *, outside=False):
    """Luminance multiplier (h, w) around 1.0 for one look. Columns run along the field (one period = two 5-yard
    bands); rows run across (one period = 10 yards, two 5-yard checker cells)."""
    p = LOOK_PATTERNS[look]
    r = rng(p["seed"] + (100 if outside else 0) + h)
    if outside:
        tone = np.zeros((h, w))
    elif p["pattern"] == "checker":
        tone = square_wave(w, 1)[None, :] * square_wave(h, 1)[:, None]
    else:
        tone = np.repeat(square_wave(w, 1)[None, :], h, 0)
    mottle = fractal(h, w, p["mottle_scale"] * (w / 128.0), r) * p["mottle"]
    speckle = r.uniform(-1, 1, (h, w)) * p["speckle"]
    return 1.0 + tone * p["band"] + mottle + speckle


def pattern_atlas(look):
    rows = [pattern(look, 64, 128), pattern(look, 128, 128), pattern(look, 128, 128, outside=True)]
    atlas = np.concatenate(rows, 0)
    return np.clip(np.round(atlas * 128.0), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ detail normals
def strokes(h, w, cx, cy, th, length, width, height, curl, steps=10):
    """Height field of short lying fibres or blades (tileable max-splat of tapered strokes)."""
    hf = np.zeros((h, w))
    for k in range(steps + 1):
        t = k / steps - 0.5
        ang = th + curl * t
        px = cx + np.cos(ang) * length * t
        py = cy + np.sin(ang) * length * t
        prof = height * (1 - abs(2 * t) ** 3)
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                xi = np.floor(px).astype(int) + ox
                yi = np.floor(py).astype(int) + oy
                wgt = np.clip(1 - np.hypot(px - (xi + 0.5), py - (yi + 0.5)) / width, 0, 1) * prof
                np.maximum.at(hf, (yi % h, xi % w), wgt)
    return hf


DETAIL_PARAMS = {
    # tf-v3: bright short blades or fibres lying every way, dark gaps (infill specks on synthetic turf), a per-texel
    # jitter. alpha = the kind's palette alpha since tf-v1 (163, 168, 143: the in-game brightness was measured with it,
    # the module's DETAIL_ALPHA). The spreads (standard deviation / mean of the alpha per mip level) live in the module:
    # DETAIL_REL_ANCHOR (tf-v3.1, the calm look Noah played on v0.6.1), DETAIL_REL_FULL (gr2 candidate A, what this
    # file stores) and DETAIL_STRENGTH (how far a build goes from the first toward the second). fresh_seed draws the
    # per-level clump noise (Bermuda 7 and fibre 8 are the draws of gr2's pick sheet).
    "fibre": dict(count=60000, length=(2.0, 3.5), width=0.5, curl=0.6, infill=0.14, jitter=0.30, alpha=163, seed=41,
                  fresh_seed=8, fresh=(0.0, 0.25, 0.45, 0.6, 0.7, 0.8)),
    # Matrix Helix: shorter, twisted fibres. Its long curls must not reach mips 2 and 3 through the box (gr2's lattice
    # warning sheet), so those levels take more fresh noise
    "helix": dict(count=66000, length=(1.6, 3.0), width=0.5, curl=2.2, infill=0.14, jitter=0.30, alpha=168, seed=42,
                  fresh_seed=10, fresh=(0.0, 0.25, 0.7, 0.7, 0.75, 0.8)),
    # Bermuda: dense short fine blades mown low
    "blade_bermuda": dict(count=70000, length=(1.8, 3.0), width=0.45, curl=0.4, infill=0.06, jitter=0.28, alpha=143,
                          seed=43, fresh_seed=7, fresh=(0.0, 0.25, 0.45, 0.6, 0.7, 0.8)),
    # Kentucky bluegrass: a little longer blades mown higher
    "blade_bluegrass": dict(count=62000, length=(2.2, 3.5), width=0.48, curl=0.4, infill=0.06, jitter=0.28, alpha=143,
                            seed=44, fresh_seed=9, fresh=(0.0, 0.25, 0.45, 0.6, 0.7, 0.8)),
}
#: tf-v4: the Gaussian sigma (texels of that level) of each level's fresh clump noise
CLUMP_SIGMA = (0.0, 0.6, 0.7, 0.8, 0.8, 0.8)
#: the one normal every palette entry carries (tf-v3): flat, as the in-game texture is the alpha
FLAT_NORMAL_RGB = (128, 128, 255)


def _stroke_set(p, h, w, r):
    n = p["count"] * h * w // (256 * 512)
    cx = r.uniform(0, w, n)
    cy = r.uniform(0, h, n)
    th = r.uniform(0, 2 * math.pi, n)
    length = r.uniform(*p["length"], n)
    height = r.uniform(0.55, 1.0, n)
    curl = r.uniform(-p["curl"], p["curl"], n)
    return cx, cy, th, length, height, curl


def blade_field(kind, h=256, w=512, scale=1):
    """Zero-mean, unit-spread blade field (h*scale x w*scale, tileable): bright short strokes, dark gaps, jitter."""
    p = DETAIL_PARAMS[kind]
    r = rng(p["seed"])
    cx, cy, th, length, height, curl = _stroke_set(p, h, w, r)
    hf = strokes(h * scale, w * scale, cx * scale, cy * scale, th, length * scale, p["width"] * scale, height, curl,
                 steps=10 * scale)
    v = hf - hf.mean()
    if p["infill"]:
        specks = r.random((h, w)) < p["infill"]
        if scale > 1:
            specks = np.kron(specks, np.ones((scale, scale), bool))
        v = np.where(specks & (hf < 0.35), -0.9, v)
    jit = rng(p["seed"] + 9).normal(0, 1, (h, w))
    v = v + p["jitter"] * (np.kron(jit, np.ones((scale, scale))) if scale > 1 else jit)
    return (v - v.mean()) / v.std()


def _box(a):
    return (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]) / 4


def _unit(a):
    a = a - a.mean()
    sd = float(a.std())
    return a / (sd if sd > 1e-9 else 1.0)


def alpha_levels(kind, h=256, w=512, levels=6, *, fresh_seed=None):
    """The alpha index levels (uint8, = palette index) of one kind at FULL strength (tf-v4, premipped): level k is the
    2 x 2 box of the level above (coherent blades) mixed with fresh per-level clump noise at that level's own texel
    scale (Gaussian, wrapped so a tile still tiles), rescaled to DETAIL_REL_FULL[k] x the kind's alpha around that
    alpha; every level's mean kept on the alpha. gr2's ``looks.detail_levels``, the generator of Noah's pick sheet."""
    from scipy.ndimage import gaussian_filter
    p = DETAIL_PARAMS[kind]
    m = float(p["alpha"])
    r = rng(p["fresh_seed"] if fresh_seed is None else fresh_seed)
    cur = _unit(blade_field(kind, h, w))
    out = []
    for k in range(levels):
        if k:
            cur = _unit(_box(cur))
            n = r.normal(0, 1, cur.shape)
            if CLUMP_SIGMA[k]:
                n = gaussian_filter(n, CLUMP_SIGMA[k], mode="wrap")
            f = p["fresh"][k]
            cur = _unit(math.sqrt(1 - f) * cur + math.sqrt(f) * _unit(n))
        a = m + ms.DETAIL_REL_FULL[k] * m * cur
        q = np.clip(np.round(a), 0, 255)
        q = np.clip(q + np.round(m - q.mean()), 0, 255)
        out.append(q.astype(np.uint8))
    return out


def _palette_image(atlas):
    img = Image.fromarray(atlas, "P")
    img.putpalette(list(FLAT_NORMAL_RGB) * 256)
    return img, bytes(range(256))


def detail_atlas(kind):
    """(P-mode PIL image 512 x 384: one flat normal, alpha = index; the tRNS bytes; the index levels)."""
    idx_levels = alpha_levels(kind)
    atlas = np.zeros((384, 512), np.uint8)
    for (ox, oy), idx in zip(MIP_ORIGINS, idx_levels):
        atlas[oy:oy + idx.shape[0], ox:ox + idx.shape[1]] = idx
    img, trns = _palette_image(atlas)
    return img, trns, idx_levels


TILE_ORIGINS = ((0, 0), (0, 64), (32, 64), (48, 64), (56, 64), (60, 64))


TILES = 3


def tile_atlas(kind):
    """Three tileable 64 x 64 versions side by side (each with its mips packed below it: a 192 x 96 atlas) for the
    venues whose detail normal is a compressed chunk (s11, s15). The library lays them over the texture in a fixed
    irregular grid (TILE_GRID) that repeats every third 64 x 64 block in the texture's swizzled order, so the chunk
    still compresses into its span while no single tile repeats as a lattice; the same blade density per texel and
    the same spreads as the full art."""
    atlas = np.zeros((96, 64 * TILES), np.uint8)
    base = DETAIL_PARAMS[kind]["seed"]
    for t in range(TILES):
        DETAIL_PARAMS[kind]["seed"] = base + 100 * (t + 1)
        try:
            levels = alpha_levels(kind, 64, 64, fresh_seed=DETAIL_PARAMS[kind]["fresh_seed"] + 100 * (t + 1))
        finally:
            DETAIL_PARAMS[kind]["seed"] = base
        for (ox, oy), idx in zip(TILE_ORIGINS, levels):
            atlas[oy:oy + idx.shape[0], 64 * t + ox:64 * t + ox + idx.shape[1]] = idx
    return _palette_image(atlas)


def masters_4x(kind, out_dir):
    """Edition 4x master (2048 x 1024 RGBA): the same blades rasterized at 4x, the flat normal, alpha = mip 0's at the
    build's default strength (the pack keys on the default detail video)."""
    p = DETAIL_PARAMS[kind]
    v = blade_field(kind, scale=4)
    rel0 = ms.detail_rel(kind)[0]
    a = np.clip(np.round(p["alpha"] + rel0 * p["alpha"] * v), 0, 255).astype(np.uint8)
    rgb = np.empty(a.shape + (3,), np.uint8)
    rgb[...] = FLAT_NORMAL_RGB
    Image.fromarray(np.concatenate([rgb, a[..., None]], -1), "RGBA").save(out_dir / f"detail_{kind}_4x.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--masters", default=None, help="also write the Edition 4x detail masters here (not shipped)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for kind in DETAIL_KINDS:
        img, trns, _levels = detail_atlas(kind)
        path = out / f"detail_{kind}.png"
        img.save(path, transparency=trns, optimize=False)
        manifest[path.name] = dict(kind="detail", detail=kind, size=[512, 384])
        img, trns = tile_atlas(kind)
        path = out / f"detail_{kind}_tile.png"
        img.save(path, transparency=trns, optimize=False)
        manifest[path.name] = dict(kind="detail_tile", detail=kind, size=[64 * TILES, 96])
    for look in LOOK_PATTERNS:
        path = out / f"pattern_{look}.png"
        Image.fromarray(pattern_atlas(look), "L").save(path, optimize=False)
        manifest[path.name] = dict(kind="pattern", look=look, size=[128, 320])
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_modern_surfaces_art/v1", files=manifest),
                                             indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.masters:
        m = Path(args.masters)
        m.mkdir(parents=True, exist_ok=True)
        for kind in DETAIL_KINDS:
            masters_4x(kind, m)
    print("wrote", len(manifest), "files to", out)


if __name__ == "__main__":
    main()
