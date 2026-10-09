#!/usr/bin/env python3
"""Author a team's 2026 kit (uniforms, helmet, numbers, socks, LOD atlas) from its retail textures and a team spec.

Job u1 of the 2026 modernization program (pilot: the New York Giants, ``data/nfl2k5_teams_2026/NYG.json``).

Noah's rule for 2026 art (U_BRIEF, 2026-09-23): the disc carries the real look natively at the retail size, and a
texture pack only adds resolution. So every texture is authored ONCE at 4x (the master, for the 2K5 Edition xemu
packs) and area-downscaled to the retail size (the native disc texture). The retail texture is the layout template:
the player model's UV layout is shared by every team, so the pixel positions in the spec (collar V tip, sleeve
swoosh grid, pants stripe bands, pants hip marks) are the same for all 32 teams.

The NFL shield and the maker's swoosh are never drawn: ``author --uniform-marks`` names the official masters (a
``nfl2k5_uniform_marks/v1`` manifest; the files are pinned by SHA-256 and stay out of the repository), placed where
the 2026 uniforms carry them (job uw): the shield under the collar V, the swoosh on both sleeves below the shoulder
seam with its hook toward the front, and on the front of the left hip.

  python3 tools/nfl2k5_team_2026_art.py export --source-xiso RETAIL.iso --codes 18 --out DIR
  python3 tools/nfl2k5_team_2026_art.py author --spec data/nfl2k5_teams_2026/NYG.json --retail DIR/uniforms \
      --equipment DIR/equipment --marks MARKS --uniform-marks UNIFORM_MARKS/manifest.json --out ART
  python3 tools/nfl2k5_team_2026_art.py venue --spec ... --marks MARKS --retail-venue VENUE_EXPORT --out VENUE_ART
  python3 tools/nfl2k5_team_2026_art.py project --spec ... --art ART [--faces FACES/manifest.json] --out project.json
  python3 tools/nfl2k5_team_2026_art.py colours --manifest ART/manifest.json --out colours.json
  python3 tools/nfl2k5_team_2026_art.py pack --catalog DISC.catalog.tsv --art ART/manifest.json \
      [--faces FACES/manifest.json] --name "NYG 2026" --out PACK_SRC
  python3 tools/nfl2k5_team_2026_art.py merge-projects --project NYG.json --project DAL.json ... --out league.json

``export`` reads the user's own disc through the Studio's verified source cache; nothing retail is written to the
repository. ``author`` writes ``ART/master4x/<set>/<name>.png`` and ``ART/retail/<set>/<name>.png`` plus a manifest
with the SHA-256 of every file. ``project`` writes a ``nfl2k5_visual_mod_project/v1`` document for the Studio's
unified writer (``tools/nfl2k5_visual_mod_project.py``), which refits every edit inside its retail span. ``colours``
measures the dominant colours of every authored texture as hex, for the Jev palette check. ``pack`` writes a manifest
for the 2K5 Edition pack builder (job x2, ``tools/nfl2k5_texture_pack.py build``) that maps the 4x masters to texture
names in their archive files; the builder resolves the keys against the catalog of the disc that is played.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
MASTER = 4
SCHEMA = "nfl2k5_team_2026/v1"
ART_SCHEMA = "nfl2k5_team_2026_art/v1"

# Shared player-model UV positions, measured on the retail textures (retail pixels, x right, y down).
TORSO_V_TIP = (161.0, 70.0)            # front collar V tip (18H6/18A6 neck mask, rows 0..70)
TORSO_SLEEVE_MARKS = ((56, 4, 63, 23), (263, 4, 270, 23), (282, 10, 289, 29), (489, 10, 496, 29))  # retail maker marks
PANTS_STRIPE_BANDS = ((130, 155), (357, 382))  # the two outer-seam stripe bands (x ranges, full height)
PANTS_SHIELD_BOX = (92, 40, 104, 51)   # NFL shield on the right hip (kept)
PANTS_MAKER_BOX = (401, 41, 420, 48)   # retail maker mark on the left hip (becomes the swoosh)
NECK_GREY = (220, 220, 220)
# The two neck openings of the shared torso UV layout (retail px; one span [x0, x1) per row from the top edge): the
# near-grey opening that most of the 479 retail torsos share. The neck is this region, not a colour test, so the
# retail torsos' grey mesh dots, maker tags and grey NFL shield are never neck (job d2), and an opening painted a
# darker grey (TEN 28A0, PHI 21H0, MIN 15A0) is still whole.
TORSO_NECK_SPANS = (
    (  # front V, rows 0..70
       (139, 185), (139, 185), (138, 186), (138, 186), (138, 186), (138, 186), (138, 186), (138, 186), (137, 186),
       (137, 186), (137, 186), (137, 186), (137, 186), (137, 186), (137, 186), (138, 186), (138, 186), (138, 186),
       (138, 186), (138, 186), (138, 186), (138, 185), (138, 185), (138, 185), (138, 185), (138, 185), (138, 185),
       (138, 185), (138, 185), (138, 185), (138, 185), (138, 185), (138, 185), (138, 185), (138, 185), (139, 185),
       (139, 185), (139, 185), (139, 184), (139, 184), (139, 184), (139, 184), (140, 184), (140, 183), (140, 183),
       (140, 183), (141, 183), (141, 182), (141, 182), (142, 182), (142, 182), (142, 181), (143, 181), (143, 180),
       (144, 180), (144, 179), (145, 178), (146, 178), (147, 177), (147, 176), (150, 174), (151, 173), (152, 172),
       (153, 171), (154, 170), (155, 169), (157, 168), (158, 166), (159, 165), (160, 164), (160, 163),
    ),
    (  # back, rows 0..43
       (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415),
       (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415),
       (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 415), (366, 414), (366, 414), (366, 414),
       (366, 414), (366, 414), (366, 414), (367, 413), (367, 413), (368, 412), (368, 412), (369, 411), (370, 411),
       (370, 410), (372, 409), (373, 407), (374, 406), (376, 404), (378, 403), (380, 399), (387, 392),
    ),
)
RETAIL_NAVY_B = 101 / 255.0            # blue channel of the retail flat navy (4, 8, 101), the recolour reference
# The small player atlas ("splayer", 256x128, one per uniform set) shares one layout across all teams: pants
# (one leg, with its outer stripe), torso front, hands, helmet side, the two sock halves and a sleeve, painted with
# baked shading. Boxes are (x0, y0, x1, y1) in retail atlas pixels.
SPLAYER = {
    "pants": (0, 0, 128, 90), "pants_stripe": (46, 0, 66, 90), "pants_stripe_center": 56.0, "pants_scale": 0.48,
    "pants_maker": (69, 13, 85, 23), "torso": (128, 0, 256, 100), "hands": (0, 90, 37, 128),
    "helmet": (37, 90, 128, 128), "sock_low": (127, 100, 160, 128), "sock": (160, 100, 190, 128),
    "sleeve": (190, 100, 256, 128), "chest_mark": (180.0, 36.0), "chest_mark_width": 7.0,
}


# Named places on the shared layouts (retail pixels, x0 y0 x1 y1), for ``decorations`` items (``"at": name``) and for
# the guide images of ``layout``. Measured on the retail textures; the texture half a place sits in is stated, the
# player's left or right is not (check it in the lab or on the Team Select render).
LAYOUT = {
    "torso": {
        "collar_front_tip": (159, 68, 163, 72),      # the front V tip (TORSO_V_TIP)
        "chest_logo": (152, 86, 170, 99),            # under the collar, where the Giants' small ny sits
        "front_numbers": (98, 80, 224, 150),         # the front mesh panel (the game draws the numbers)
        "back_collar": (376, 44, 406, 58),           # below the back neck opening
        "back_numbers": (320, 95, 448, 175),         # the back mesh panel
        "shoulder_1": TORSO_SLEEVE_MARKS[0], "shoulder_2": TORSO_SLEEVE_MARKS[1],   # front half maker marks
        "shoulder_3": TORSO_SLEEVE_MARKS[2], "shoulder_4": TORSO_SLEEVE_MARKS[3],   # back half maker marks
    },
    "sleeve": {                                      # two sleeves in one texture, the stripe band near the cuff
        "sleeve_1_band": (10, 36, 122, 56), "sleeve_2_band": (10, 100, 122, 120),
        "sleeve_1_upper": (10, 6, 122, 32), "sleeve_2_upper": (10, 70, 122, 96),
    },
    "pants": {
        "stripe_1": (PANTS_STRIPE_BANDS[0][0], 0, PANTS_STRIPE_BANDS[0][1], 256),
        "stripe_2": (PANTS_STRIPE_BANDS[1][0], 0, PANTS_STRIPE_BANDS[1][1], 256),
        "hip_shield": PANTS_SHIELD_BOX, "hip_maker": PANTS_MAKER_BOX,
    },
    "helmet": {"decal_upper": (40, 44, 112, 108), "decal_lower": (40, 142, 112, 212),
               "stripe_band": (148, 0, 177, 232), "stripe_centre": (160, 0, 164, 232)},   # centre line x 162
}


def anchor_centre(part: str, name: str) -> tuple[float, float]:
    x0, y0, x1, y1 = LAYOUT[part][name]
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


# --------------------------------------------------------------------------------------------- colour and images
def rgb(value: str) -> np.ndarray:
    value = value.strip()
    if not (len(value) == 7 and value[0] == "#"):
        raise ValueError(f"colour must be #RRGGBB, got {value!r}")
    return np.array([int(value[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255.0


def load(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0


def save(array: np.ndarray, path: Path, *, digit_registration: str | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    options = {}
    if digit_registration is not None:
        if digit_registration not in {"retail", "as_authored"}:
            raise ValueError("unknown digit registration")
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("nfl2k5_digit_registration", digit_registration)
        options["pnginfo"] = metadata
    Image.fromarray(data, "RGBA").save(path, optimize=False, compress_level=9, **options)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upscale(array: np.ndarray, factor: int = MASTER, resample=Image.LANCZOS) -> np.ndarray:
    """Premultiplied Lanczos upscale (no colour fringes at alpha edges)."""
    h, w = array.shape[:2]
    pre = array.copy()
    pre[..., :3] *= pre[..., 3:4]
    out = np.stack([np.asarray(Image.fromarray(pre[..., c]).resize((w * factor, h * factor), resample), dtype=np.float32)
                    for c in range(4)], axis=-1)
    out = np.clip(out, 0.0, 1.0)
    alpha = out[..., 3:4]
    out[..., :3] = np.where(alpha > 1e-4, out[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    return np.clip(out, 0.0, 1.0)


def downscale(array: np.ndarray, factor: int = MASTER) -> np.ndarray:
    """Exact box (area) downscale on premultiplied RGBA: the native texture is the average of its master block."""
    h, w = array.shape[:2]
    if h % factor or w % factor:
        raise ValueError("master size must be a multiple of the factor")
    pre = array.copy()
    pre[..., :3] *= pre[..., 3:4]
    pre = pre.reshape(h // factor, factor, w // factor, factor, 4).mean(axis=(1, 3))
    alpha = pre[..., 3:4]
    pre[..., :3] = np.where(alpha > 1e-4, pre[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    return np.clip(pre, 0.0, 1.0)


def over(dst: np.ndarray, colour: np.ndarray, alpha: np.ndarray) -> None:
    """Paint ``colour`` with coverage ``alpha`` (HxW) onto an opaque-or-not RGBA array in place."""
    a = np.clip(alpha, 0.0, 1.0)[..., None]
    dst[..., :3] = dst[..., :3] * (1.0 - a) + colour[None, None, :3] * a
    dst[..., 3:4] = dst[..., 3:4] * (1.0 - a) + a


def rect_coverage(shape, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Exact fractional pixel coverage of an axis-aligned rectangle (pixel units of the array)."""
    h, w = shape
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    cx = np.clip(np.minimum(xs + 1, x1) - np.maximum(xs, x0), 0.0, 1.0)
    cy = np.clip(np.minimum(ys + 1, y1) - np.maximum(ys, y0), 0.0, 1.0)
    return cy[:, None] * cx[None, :]


def polygon_coverage(shape, points, supersample: int = 8) -> np.ndarray:
    """Anti-aliased polygon coverage by supersampled rasterisation."""
    h, w = shape
    # BOX reduction has no footprint outside a pixel's own supersampled block. An integer-aligned crop therefore
    # produces identical coverage and makes triangle-clipped art practical without allocating a full 16K canvas.
    x0 = max(0, math.floor(min(x for x, _y in points)) - 1)
    y0 = max(0, math.floor(min(y for _x, y in points)) - 1)
    x1 = min(w, math.ceil(max(x for x, _y in points)) + 1)
    y1 = min(h, math.ceil(max(y for _x, y in points)) + 1)
    result = np.zeros((h, w), dtype=np.float32)
    if x1 <= x0 or y1 <= y0:
        return result
    image = Image.new("L", ((x1-x0) * supersample, (y1-y0) * supersample), 0)
    ImageDraw.Draw(image).polygon([((x-x0) * supersample, (y-y0) * supersample) for x, y in points], fill=255)
    result[y0:y1, x0:x1] = np.asarray(image.resize((x1-x0, y1-y0), Image.BOX), dtype=np.float32) / 255.0
    return result


def mark_coverage(mask_png: Path, shape, center, width: float, rotate: float = 0.0, height: float | None = None,
                  mirror: bool = False) -> np.ndarray:
    """A high-resolution mark (white-on-transparent PNG) placed by centre and width, as coverage in ``shape``."""
    with Image.open(mask_png) as image:
        alpha = image.convert("RGBA").getchannel("A")
    box = alpha.getbbox()
    alpha = alpha.crop(box)
    if mirror:
        alpha = alpha.transpose(Image.FLIP_LEFT_RIGHT)
    if rotate:
        alpha = alpha.rotate(rotate, resample=Image.BICUBIC, expand=True)
        alpha = alpha.crop(alpha.getbbox())
    aw, ah = alpha.size
    if height is None:
        height = width * ah / aw
    h, w = shape
    ss = 4
    canvas = Image.new("L", (w * ss, h * ss), 0)
    tw, th = max(1, round(width * ss)), max(1, round(height * ss))
    scaled = alpha.resize((tw, th), Image.LANCZOS)
    canvas.paste(scaled, (round((center[0] - width / 2) * ss), round((center[1] - height / 2) * ss)))
    return np.asarray(canvas.resize((w, h), Image.BOX), dtype=np.float32) / 255.0


def shade_ratio(ratio: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Retail shading as a brightness ratio, compressed for light targets: a grey fold that reads well on grey
    fabric reads as a dirty stripe on white, so light colours keep half of the retail contrast."""
    ratio = np.clip(ratio, 0.0, 1.25)
    if float(np.asarray(target).mean()) > 0.8:
        ratio = 1.0 - (1.0 - ratio) * 0.45
    return ratio


def smooth_threshold(alpha: np.ndarray, lo: float = 0.3, hi: float = 0.7) -> np.ndarray:
    t = np.clip((alpha - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def glyph_master(retail_rgba: np.ndarray, factor: int = MASTER) -> np.ndarray:
    """Clean 4x glyph coverage from a retail anti-aliased glyph (digits, nameplate letters)."""
    alpha = retail_rgba[..., 3]
    h, w = alpha.shape
    up = np.asarray(Image.fromarray(alpha).resize((w * factor, h * factor), Image.BICUBIC), dtype=np.float32)
    return smooth_threshold(np.clip(up, 0.0, 1.0), 0.35, 0.65)


# --------------------------------------------------------------------------------------------- official marks
# The NFL shield and the maker's swoosh are never drawn here (job uw, 2026-09-29: the earlier polygons read as "a line
# or something" on the sleeves). They are the renders of the official vectors, loaded from the user's own files
# through a ``nfl2k5_uniform_marks/v1`` manifest (``author --uniform-marks``: {"schema", "marks": {name: {"file",
# "sha256"}}}, files relative to the manifest) and they must match these pins. Nothing of them ships in the repository.
UNIFORM_MARKS_SCHEMA = "nfl2k5_uniform_marks/v1"
UNIFORM_MARK_PINS = {
    # NFL.com's own shield SVG (the 2008 design), Inkscape render: tight crop centred on 2048 x 2048, 2 % margin
    "nfl_shield": "3f9209455841b8ed9e03afd1ebd254ec7c91d37898df67b9d24c62d2683df8fc",
    # nike.com's own swoosh vector (served inline by the site's header), rendered white the same way
    "nike_swoosh": "4fd63f149867893d289e8670c6640d159a76d493cfeceafe6a7b4a18039c4a9b",
}
_UNIFORM_MARKS: dict = {}


def use_uniform_marks(manifest: Path | str) -> dict:
    """Load the pinned official masters named by a uniform-marks manifest (every pin must be present and match)."""
    path = Path(manifest)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(doc, dict) and doc.get("schema") == UNIFORM_MARKS_SCHEMA):
        raise SystemExit(f"{path}: expected a {UNIFORM_MARKS_SCHEMA} manifest")
    rows = doc.get("marks") or {}
    loaded = {}
    for name, pin in UNIFORM_MARK_PINS.items():
        row = rows.get(name)
        if not row:
            raise SystemExit(f"{path}: the manifest names no {name}")
        file = (path.parent / row["file"]).resolve()
        data = file.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row.get("sha256") or digest != pin:
            raise SystemExit(f"{path}: {row['file']} is not the reviewed {name} master (sha256 {digest}, pinned {pin})")
        with Image.open(file) as image:
            rgba = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255.0
        ys, xs = np.nonzero(rgba[..., 3] > 0.0)
        loaded[name] = {"rgba": rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy(), "sha256": digest,
                        "file": str(file)}
    _UNIFORM_MARKS.clear()
    _UNIFORM_MARKS.update(loaded)
    return {name: row["sha256"] for name, row in loaded.items()}


def uniform_mark(name: str) -> np.ndarray:
    """The official master (RGBA, cropped to its alpha box), after ``use_uniform_marks``."""
    if name not in _UNIFORM_MARKS:
        raise SystemExit(f"the kit needs the official {name}: pass --uniform-marks (the tool never draws a mark)")
    return _UNIFORM_MARKS[name]["rgba"]


def _reduced(rgba: np.ndarray, width: float) -> np.ndarray:
    """The master box-reduced (premultiplied) toward ``width`` px across, so point samples of it do not alias."""
    k = max(1, int(rgba.shape[1] // max(width, 1.0)))
    if k == 1:
        return rgba
    h, w = rgba.shape[0] // k * k, rgba.shape[1] // k * k
    pre = rgba[:h, :w].copy()
    pre[..., :3] *= pre[..., 3:4]
    pre = pre.reshape(h // k, k, w // k, k, 4).mean(axis=(1, 3))
    a = pre[..., 3:4]
    pre[..., :3] = np.where(a > 1e-6, pre[..., :3] / np.maximum(a, 1e-6), 0.0)
    return pre


def _sample(rgba: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear premultiplied samples of an RGBA master at (u, v) in 0..1 (u across, v down); outside is empty."""
    h, w = rgba.shape[:2]
    pre = rgba.copy()
    pre[..., :3] *= pre[..., 3:4]
    x = u * w - 0.5
    y = v * h - 0.5
    inside = np.isfinite(x) & np.isfinite(y) & (x > -1.0) & (x < w) & (y > -1.0) & (y < h)
    x = np.where(inside, x, -2.0)
    y = np.where(inside, y, -2.0)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    out = np.zeros(x.shape + (4,), np.float32)
    for dy, wy in ((0, 1.0 - fy), (1, fy)):
        for dx, wx in ((0, 1.0 - fx), (1, fx)):
            xi, yi = x0 + dx, y0 + dy
            ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h) & inside
            vals = pre[np.clip(yi, 0, h - 1), np.clip(xi, 0, w - 1)]
            out += np.where(ok[..., None], vals, 0.0) * wx * wy
    return out


def _texture_light(out: np.ndarray, cov: np.ndarray, sigma_px: float = 3.0) -> np.ndarray:
    """The texture's own lighting under a mark: the surface luminance around it, blurred across it, relative to its
    median under the mark (cloth folds and baked shading carry into the mark; a flat texture gives 1)."""
    from scipy import ndimage
    luma = out[..., :3] @ LUMA
    keep = (cov < 0.02).astype(np.float32)
    sigma = float(sigma_px) * MASTER
    light = ndimage.gaussian_filter(luma * keep, sigma) / np.maximum(ndimage.gaussian_filter(keep, sigma), 1e-3)
    under = cov > 0.5
    ref = float(np.median(light[under])) if under.any() else float(np.median(light))
    return np.clip(light / max(ref, 1e-3), 0.8, 1.15)


def _paint_mark(out: np.ndarray, sample: np.ndarray, colour: np.ndarray | None, region) -> None:
    """Composite premultiplied mark samples (HxWx4 over ``region`` of ``out``) in one colour or in the mark's own
    colours, lit by the texture's own lighting."""
    y0, y1, x0, x1 = region
    cov = np.zeros(out.shape[:2], np.float32)
    cov[y0:y1, x0:x1] = sample[..., 3]
    light = _texture_light(out, cov)[y0:y1, x0:x1, None]
    a = sample[..., 3:4]
    if colour is not None:
        rgb = np.broadcast_to(colour[None, None, :3], a.shape[:2] + (3,))
    else:
        rgb = np.where(a > 1e-6, sample[..., :3] / np.maximum(a, 1e-6), 0.0)
    dst = out[y0:y1, x0:x1]
    dst[..., :3] = dst[..., :3] * (1.0 - a) + np.clip(rgb * light, 0.0, 1.0) * a
    dst[..., 3:4] = dst[..., 3:4] * (1.0 - a) + a


def place_mark(out: np.ndarray, name: str, centre, width: float, height: float, colour: np.ndarray | None = None,
               mirror: bool = False, rotate: float = 0.0, supersample: int = 4) -> None:
    """An official master placed flat in a texture: centre, width and height in the array's pixels (the box of the
    mark's alpha; unequal texel sizes along x and y are given as the box, so the mark keeps its true proportions on
    the model), turned by ``rotate`` degrees (counter-clockwise on the image), supersampled and lit like the
    texture."""
    rgba = _reduced(uniform_mark(name), max(width, height) * supersample)
    reach = 0.5 * math.hypot(width, height) + 2.0
    x0, x1 = max(int(math.floor(centre[0] - reach)), 0), min(int(math.ceil(centre[0] + reach)), out.shape[1])
    y0, y1 = max(int(math.floor(centre[1] - reach)), 0), min(int(math.ceil(centre[1] + reach)), out.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    offs = (np.arange(supersample, dtype=np.float64) + 0.5) / supersample
    xs = (np.arange(x0, x1)[:, None] + offs[None, :]).ravel()
    ys = (np.arange(y0, y1)[:, None] + offs[None, :]).ravel()
    X, Y = np.meshgrid(xs, ys)
    c, s = math.cos(math.radians(rotate)), math.sin(math.radians(rotate))
    dx, dy = X - centre[0], Y - centre[1]
    # image rotation (y down): a counter-clockwise turn on screen
    u = (dx * c - dy * s) / width + 0.5
    v = (dx * s + dy * c) / height + 0.5
    if mirror:
        u = 1.0 - u
    smp = _sample(rgba, u, v)
    smp = smp.reshape(y1 - y0, supersample, x1 - x0, supersample, 4).mean(axis=(1, 3))
    _paint_mark(out, smp, colour, (y0, y1, x0, x1))


# The jersey swoosh sits on each SLEEVE's outer face just below the shoulder seam, under the TV number, with its hook
# toward the front of the arm and its tip toward the back on both arms, so the right arm shows the mark mirrored and
# the left arm shows it as drawn (the 2026 broadcast frames, job uw). The game's UNIF_sleeve texture carries the
# player's right arm in rows 0-64 and the left arm in rows 64-128, the shoulder seam along each island's top. The
# placement was measured on the rest-pose hi_body (the swoosh box 6 cm across the arm, its centre 1.6 cm below
# the seam and 3 cm forward of the arm's side, the box along the arm's circumference) and is kept as a grid: decal
# coordinates (s along the swoosh from the hook end 0 to the tip end 1, t up the arm from the box bottom 0 to its top
# 1) to sleeve texels (retail px). The texture is area-mapped from the grid, so the UV layout's stretch near the
# shoulder is followed, not an affine guess.
SLEEVE_SWOOSH = {
    "s": (-0.15, -0.05, 0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.05, 1.15),
    "t": (-0.25, 0.00, 0.25, 0.50, 0.75, 1.00, 1.25),
    "R": {
        "x": (
            (84.19, 81.71, 79.43, 77.16, 74.89, 72.61, 70.34, 67.97, 65.52, 63.11, 60.98, 58.74, 56.51, 54.27),
            (85.02, 82.56, 80.10, 77.64, 75.18, 72.72, 70.26, 67.80, 65.54, 63.52, 61.42, 59.18, 56.94, 54.71),
            (84.85, 82.39, 79.93, 77.47, 75.01, 72.55, 70.09, 67.96, 65.94, 63.92, 61.85, 59.61, 57.38, 55.14),
            (84.67, 82.21, 79.75, 77.29, 74.83, 72.41, 70.38, 68.37, 66.35, 64.33, 62.29, 60.05, 57.81, 55.77),
            (84.49, 82.03, 79.57, 77.11, 74.83, 72.81, 70.79, 68.77, 66.75, 64.74, 62.71, 60.49, 58.38, 56.83),
            (84.32, 81.86, 79.40, 77.25, 75.23, 73.21, 71.20, 69.18, 67.16, 65.14, 63.12, 60.99, 59.44, 58.38),
            (84.14, 81.72, 79.68, 77.66, 75.64, 73.62, 71.60, 69.58, 67.12, 65.88, 63.12, 62.88, 61.88, 60.62),
        ),
        "y": (
            (18.85, 18.20, 17.69, 17.19, 16.68, 16.17, 15.67, 15.19, 14.75, 14.29, 13.63, 12.92, 12.21, 11.50),
            (16.35, 15.91, 15.47, 15.02, 14.58, 14.14, 13.70, 13.26, 12.75, 12.15, 11.51, 10.80, 10.09, 9.37),
            (14.42, 13.98, 13.54, 13.10, 12.65, 12.21, 11.77, 11.21, 10.62, 10.02, 9.39, 8.68, 7.96, 7.25),
            (12.49, 12.05, 11.61, 11.17, 10.73, 10.27, 9.67, 9.08, 8.48, 7.88, 7.27, 6.55, 5.84, 5.10),
            (10.56, 10.12, 9.68, 9.24, 8.73, 8.13, 7.54, 6.94, 6.34, 5.74, 5.14, 4.43, 3.70, 2.89),
            (8.63, 8.19, 7.75, 7.19, 6.60, 6.00, 5.40, 4.80, 4.20, 3.60, 3.00, 2.30, 1.49, 1.38),
            (6.70, 6.25, 5.65, 5.06, 4.46, 3.86, 3.26, 2.66, 2.12, 1.88, 1.38, 1.38, 1.38, 1.38),
        ),
    },
    "L": {
        "x": (
            (43.49, 45.83, 47.93, 50.02, 52.12, 54.21, 56.33, 58.62, 60.91, 63.16, 65.41, 67.90, 70.40, 72.89),
            (42.75, 45.04, 47.34, 49.63, 51.92, 54.22, 56.51, 58.81, 60.97, 63.02, 65.21, 67.70, 70.20, 72.69),
            (42.93, 45.23, 47.52, 49.82, 52.11, 54.41, 56.70, 58.79, 60.83, 62.88, 65.00, 67.50, 70.00, 72.49),
            (43.12, 45.42, 47.71, 50.01, 52.30, 54.56, 56.60, 58.65, 60.69, 62.74, 64.81, 67.30, 69.79, 71.99),
            (43.31, 45.61, 47.90, 50.20, 52.37, 54.42, 56.46, 58.51, 60.55, 62.60, 64.64, 67.10, 69.38, 70.93),
            (43.50, 45.79, 48.09, 50.19, 52.23, 54.28, 56.32, 58.37, 60.41, 62.45, 64.50, 66.77, 68.12, 69.38),
            (43.69, 45.96, 48.00, 50.05, 52.09, 54.14, 56.18, 57.88, 60.38, 61.88, 64.38, 64.88, 65.88, 66.88),
        ),
        "y": (
            (82.57, 81.93, 81.42, 80.91, 80.40, 79.89, 79.39, 78.95, 78.51, 78.03, 77.38, 76.67, 75.96, 75.25),
            (80.11, 79.67, 79.23, 78.79, 78.35, 77.90, 77.46, 77.02, 76.50, 75.90, 75.26, 74.55, 73.84, 73.13),
            (78.19, 77.74, 77.30, 76.86, 76.42, 75.98, 75.53, 74.96, 74.36, 73.76, 73.14, 72.43, 71.72, 71.01),
            (76.26, 75.82, 75.37, 74.93, 74.49, 74.03, 73.43, 72.82, 72.22, 71.62, 71.02, 70.31, 69.60, 68.86),
            (74.33, 73.89, 73.45, 73.00, 72.49, 71.89, 71.29, 70.69, 70.09, 69.49, 68.89, 68.19, 67.45, 66.65),
            (72.39, 71.96, 71.52, 70.95, 70.35, 69.75, 69.15, 68.55, 67.95, 67.35, 66.75, 66.05, 65.38, 65.38),
            (70.44, 70.01, 69.42, 68.82, 68.22, 67.62, 67.02, 66.62, 66.12, 65.88, 65.38, 65.38, 65.38, 65.38),
        ),
    },
}


def sleeve_swoosh(out: np.ndarray, colour: np.ndarray, arm: str, supersample: int = 4, offset=(0.0, 0.0)) -> None:
    """The official swoosh on one arm of a 4x sleeve master (``arm`` "R" or "L"). ``offset`` (retail px, down the
    island is +y) moves it for a kit whose jersey carries it lower (the Bengals: under the sleeve's tiger stripes)."""
    from scipy.interpolate import LinearNDInterpolator
    g = SLEEVE_SWOOSH
    S, T = np.meshgrid(np.asarray(g["s"], np.float64), np.asarray(g["t"], np.float64))
    gx = (np.asarray(g[arm]["x"], np.float64) + float(offset[0])) * MASTER
    gy = (np.asarray(g[arm]["y"], np.float64) + float(offset[1])) * MASTER
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    to_st = LinearNDInterpolator(pts, np.stack([S.ravel(), T.ravel()], axis=1))
    x0, x1 = max(int(math.floor(gx.min())) - 1, 0), min(int(math.ceil(gx.max())) + 1, out.shape[1])
    y0, y1 = max(int(math.floor(gy.min())) - 1, 0), min(int(math.ceil(gy.max())) + 1, out.shape[0])
    offs = (np.arange(supersample, dtype=np.float64) + 0.5) / supersample
    xs = (np.arange(x0, x1)[:, None] + offs[None, :]).ravel()
    ys = (np.arange(y0, y1)[:, None] + offs[None, :]).ravel()
    X, Y = np.meshgrid(xs, ys)
    st = to_st(np.stack([X.ravel(), Y.ravel()], axis=1)).reshape(X.shape + (2,))
    # s runs toward the back on both arms (the grid is measured in 3D), so the right arm's mark comes out mirrored
    # as seen from outside that arm, and the left arm's as drawn, with no flip here
    s, t = st[..., 0], st[..., 1]
    rgba = uniform_mark("nike_swoosh")
    across = (gx.max() - gx.min()) * supersample
    smp = _sample(_reduced(rgba, across), s, 1.0 - t)
    smp = smp.reshape(y1 - y0, supersample, x1 - x0, supersample, 4).mean(axis=(1, 3))
    _paint_mark(out, smp, colour, (y0, y1, x0, x1))


# The NFL shield under the collar V: its top just below the V's point (and below any collar trim there), centred on
# the V. Size from the 2026 jerseys (the shield about 3.2 cm tall; the torso texels near the V measure 0.355 cm
# across and 0.29 cm down on the rest-pose hi_body, so the box keeps the shield's true 0.727 proportions).
COLLAR_SHIELD = {"height_px": 11.0, "width_px": 6.6, "gap_px": 0.0}
# The pants (2026 Nike game pants): the swoosh on the front of the player's LEFT hip and the NFL shield on the front
# of the player's RIGHT hip, their tops level, a few inches below the top of the pants (bengals.com 2026 home photo
# cwlxihk5mouwztbxgcy7 at 8256 px, #30: shield 2.6 cm tall, swoosh about 4 cm across, scaled by the 8 in front
# numerals; the Bears' white pants in the ESPN clip of 2026-09-28: the swoosh's centre about 7.5 cm below the belt's
# top). In this layout the player's left hip is the retail 2004 shield's column (x +13.7 cm on the rest-pose body),
# the right hip the retail maker mark's column (x -14.3 cm); rows run 0.265 cm (texels 0.222 cm across, 0.293 cm
# down near the hips); the belt spans rows 2-12. The 2004 marks on both hips are filled from the fabric first.
PANTS_SWOOSH = {"centre": (98.0, 31.3), "width_px": 18.0, "height_px": 4.7}
PANTS_SHIELD = {"centre": (410.5, 33.4), "width_px": 8.6, "height_px": 8.9}


def _clear_old_mark(out: np.ndarray, box, grow: float = 3.0, tol: float = 0.07) -> np.ndarray:
    """Fill a 2004 mark on a 4x fabric texture from the fabric around it. The mark is every texel near ``box``
    (retail px, grown by ``grow``) that is not a shaded version of the fabric colour (the median of a ring around
    the box), grown by one retail pixel; the fill weights each neighbour by how much it looks like fabric."""
    from scipy import ndimage
    H, W = out.shape[:2]
    x0, y0, x1, y1 = box
    X0, Y0 = max(int((x0 - grow - 3) * MASTER), 0), max(int((y0 - grow - 3) * MASTER), 0)
    X1, Y1 = min(int((x1 + grow + 3) * MASTER), W), min(int((y1 + grow + 3) * MASTER), H)
    sub = out[Y0:Y1, X0:X1]
    yy, xx = np.mgrid[Y0:Y1, X0:X1] / float(MASTER)
    near = (xx >= x0 - grow) & (xx < x1 + grow) & (yy >= y0 - grow) & (yy < y1 + grow)
    ring = ~near
    fabric = np.median(sub[..., :3][ring], axis=0)
    luma = sub[..., :3] @ LUMA
    # the cloth's own shading is mild: a much darker or lighter texel is the old mark (a grey ring on white pants is
    # not "shaded white")
    k = np.clip(luma / max(float(fabric @ LUMA), 1e-3), 0.85, 1.12)
    dist = np.linalg.norm(sub[..., :3] - fabric[None, None, :] * k[..., None], axis=2)
    old = ndimage.binary_dilation((dist > tol) & near, iterations=MASTER)
    old |= (xx >= x0 - 1) & (xx < x1 + 1) & (yy >= y0 - 1) & (yy < y1 + 1)     # the box itself, always
    mask = np.zeros((H, W), np.float32)
    mask[Y0:Y1, X0:X1] = old
    weight = np.zeros((H, W), np.float32)
    weight[Y0:Y1, X0:X1] = np.exp(-(dist / 0.05) ** 2) * (~old)
    # a feathered edge (one retail pixel): the fill fades into the fabric, so no box outline shows in the 4x master
    soft = np.maximum(mask, np.clip(ndimage.gaussian_filter(mask, 0.75 * MASTER) * 2.0, 0.0, 1.0))
    return _inpaint_weighted(out, soft, weight, 1.5 * MASTER)


# --------------------------------------------------------------------------------------------- the spec
class Spec:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        if self.data.get("schema") != SCHEMA:
            raise ValueError(f"{path}: expected schema {SCHEMA}")
        self.albedo = {k: rgb(v) for k, v in self.data["albedo"].items()}

    def colour(self, name: str) -> np.ndarray:
        if name.startswith("#"):
            return rgb(name)
        return self.albedo[name]


# --------------------------------------------------------------------------------------------- authors
def decorate(out: np.ndarray, spec: Spec, items: list, marks: Path | None, part: str = "") -> np.ndarray:
    """Extra art on a kit part, in retail pixels of that part's texture: ``rect`` [x0, y0, x1, y1] and ``polygon``
    [[x, y], ...] bands in a colour, and ``mark`` (a marks key) at ``center`` with ``width``, optional ``rotate``
    (degrees) and ``mirror``, in one colour or, with no ``colour``, in the mark's own colours. A ``rect`` may name a
    place of the part (e.g. "stripe_band" on the helmet); ``"shade": true`` keeps the painted shading under a band.
    For the teams whose sleeves, shoulders, hips or helmets carry more than the Giants'."""
    shape = out.shape[:2]

    def paint(colour, cov, shade: bool, sigma_px: float = 3.0) -> None:
        if shade:
            # keep the surface's shading under the item (a helmet's gloss, cloth folds) without the old art under it:
            # the luminance around the item, blurred across it, gives the light (``shade_sigma``, retail px: a wider
            # blur for a large item, so the old art's own detail under it does not print through; job u7)
            from scipy import ndimage
            luma = out[..., :3] @ LUMA
            keep = (cov < 0.5).astype(np.float32)
            sigma = float(sigma_px) * MASTER
            light = ndimage.gaussian_filter(luma * keep, sigma) / np.maximum(ndimage.gaussian_filter(keep, sigma), 1e-3)
            ref = float(np.median(light[cov > 0.5])) if (cov > 0.5).any() else float(light.mean())
            k = np.clip(light / max(ref, 1e-3), 0.75, 1.2)[..., None]
            a = np.clip(cov, 0.0, 1.0)[..., None]
            out[..., :3] = out[..., :3] * (1 - a) + np.clip(colour[None, None, :] * k, 0, 1) * a
            out[..., 3:4] = out[..., 3:4] * (1 - a) + a
        else:
            over(out, colour, cov)

    for item in items or ():
        colour = spec.colour(item["colour"]) if item.get("colour") else None
        shade = bool(item.get("shade"))
        if "rect" in item and item.get("fill") == "sides":
            # the box refilled from its two sides, row by row (linear across x): old art such as a helmet's centre
            # lines goes and the surface's own shading runs through (job u7)
            box = LAYOUT[part][item["rect"]] if isinstance(item["rect"], str) else item["rect"]
            x0, y0, x1, y1 = [int(round(v * MASTER)) for v in box]
            x0, x1 = max(x0, 1), min(x1, shape[1] - 1)
            left, right = out[y0:y1, x0 - 1:x0].copy(), out[y0:y1, x1:x1 + 1].copy()
            t = np.linspace(0.0, 1.0, x1 - x0, dtype=np.float32)[None, :, None]
            out[y0:y1, x0:x1] = left * (1 - t) + right * t
        elif "rect" in item:
            box = LAYOUT[part][item["rect"]] if isinstance(item["rect"], str) else item["rect"]
            x0, y0, x1, y1 = box
            paint(colour, rect_coverage(shape, x0 * MASTER, y0 * MASTER, x1 * MASTER, y1 * MASTER), shade)
        elif "polygon" in item:
            paint(colour, polygon_coverage(shape, [(x * MASTER, y * MASTER) for x, y in item["polygon"]]), shade,
                  item.get("shade_sigma", 3.0))
        elif "bands" in item:
            # a partition of polygon bands painted in one pass (job b77 u1, the Patriots' yoke stripes): each band is
            # many non-overlapping pieces whose coverages add up exactly, and neighbouring bands blend into each
            # other, never through the jersey colour, so no seam or dark fringe shows between pieces or bands
            covs, colours = [], []
            for band in item["bands"]:
                cov = np.zeros(shape, np.float32)
                for points in band["polygons"]:
                    cov += polygon_coverage(shape, [(x * MASTER, y * MASTER) for x, y in points])
                covs.append(np.clip(cov, 0.0, 1.0))
                colours.append(spec.colour(band["colour"]))
            total = np.clip(sum(covs), 0.0, 1.0)
            weight = np.maximum(sum(covs), 1e-6)
            rgb = sum(c[..., None] * col[None, None, :3] for c, col in zip(covs, colours)) / weight[..., None]
            a = total[..., None]
            out[..., :3] = out[..., :3] * (1 - a) + rgb * a
            out[..., 3:4] = out[..., 3:4] * (1 - a) + a
        elif "mark" in item and item["mark"].startswith("@"):
            # an official league or maker mark ("@nfl_shield", "@nike_swoosh"): the pinned master, never a team file
            cx, cy = anchor_centre(part, item["at"]) if "at" in item else item["center"]
            dx, dy = item.get("offset", (0, 0))
            name = item["mark"][1:]
            if name not in UNIFORM_MARK_PINS:
                raise SystemExit(f"{spec.path}: unknown official mark {item['mark']}")
            rgba = uniform_mark(name)
            width = float(item["width"]) * MASTER
            height = float(item.get("height", item["width"] * rgba.shape[0] / rgba.shape[1])) * MASTER
            place_mark(out, name, ((cx + dx) * MASTER, (cy + dy) * MASTER), width, height, colour=colour,
                       mirror=bool(item.get("mirror")), rotate=float(item.get("rotate", 0.0)))
        elif "mark" in item:
            path = (marks or Path(".")) / spec.data["marks"][item["mark"]]
            cx, cy = anchor_centre(part, item["at"]) if "at" in item else item["center"]
            dx, dy = item.get("offset", (0, 0))
            centre = ((cx + dx) * MASTER, (cy + dy) * MASTER)
            if colour is not None:
                cov = mark_coverage(path, shape, centre, item["width"] * MASTER, float(item.get("rotate", 0.0)),
                                    mirror=bool(item.get("mirror")))
                over(out, colour, cov)
            else:
                with Image.open(path) as image:
                    logo = image.convert("RGBA")
                logo = logo.crop(logo.getbbox())
                if item.get("mirror"):
                    logo = logo.transpose(Image.FLIP_LEFT_RIGHT)
                if item.get("rotate"):
                    logo = logo.rotate(float(item["rotate"]), resample=Image.BICUBIC, expand=True)
                    logo = logo.crop(logo.getbbox())
                width = item["width"] * MASTER
                # ``height`` (retail px, optional): the box for textures whose texels are not square on the model
                height = float(item["height"]) * MASTER if item.get("height") else width * logo.height / logo.width
                _place_logo(out, logo, centre, width, height, rotate=False)
    return out


def torso_neck_mask(shape) -> np.ndarray:
    """The torso's neck openings (TORSO_NECK_SPANS) as a 0/1 mask of a retail-size torso."""
    mask = np.zeros(shape, np.float32)
    for spans in TORSO_NECK_SPANS:
        for y, (x0, x1) in enumerate(spans):
            mask[y, x0:x1] = 1.0
    return mask


def author_torso(spec: Spec, kit: dict, retail: Path, marks: Path) -> np.ndarray:
    t = kit["torso"]
    donor = load(retail / t["neck_donor"] / "torso.png")
    h, w = donor.shape[:2]
    H, W = h * MASTER, w * MASTER
    base = spec.colour(t["base_colour"])
    grey = np.array(NECK_GREY, dtype=np.float32) / 255.0
    neck = torso_neck_mask((h, w))
    neck_up = np.asarray(Image.fromarray(neck).resize((W, H), Image.BICUBIC), dtype=np.float32)
    # smooth the retail one-pixel staircase into a clean curve before thresholding
    from scipy import ndimage
    neck_up = smooth_threshold(ndimage.gaussian_filter(np.clip(neck_up, 0, 1), sigma=MASTER * 0.55), 0.42, 0.58)
    out = np.zeros((H, W, 4), dtype=np.float32)
    out[..., :3] = base
    out[..., 3] = 1.0
    # collar trims (``collar_trim``: a list of {"colour", "width"} in retail pixels, innermost first): bands that
    # follow the neck opening's own edge, for the kits with a contrasting collar; painted outermost first
    trims = t.get("collar_trim", [])
    if trims:
        outside = ndimage.distance_transform_edt(neck_up < 0.5)
        edges = np.cumsum([float(trim["width"]) * MASTER for trim in trims])
        for trim, edge in reversed(list(zip(trims, edges))):
            over(out, spec.colour(trim["colour"]), np.clip(edge - outside + 0.5, 0.0, 1.0) * (1.0 - neck_up))
    over(out, grey, neck_up)
    shape = (H, W)
    if t.get("collar_shield"):
        # the official NFL shield under the V (COLLAR_SHIELD), below the collar trim's point when the kit has one
        s = COLLAR_SHIELD
        trim = sum(float(trim["width"]) for trim in trims)
        top = TORSO_V_TIP[1] + trim + s["gap_px"]
        place_mark(out, "nfl_shield", (TORSO_V_TIP[0] * MASTER, (top + s["height_px"] / 2.0) * MASTER),
                   s["width_px"] * MASTER, s["height_px"] * MASTER)
    mark = t.get("chest_mark")
    if mark:
        path = marks / spec.data["marks"][mark["mark"]]
        # ``height`` (retail px, optional): the torso's chest texels are 0.275 cm across and 0.25 cm down, so a mark
        # may give its box to keep true proportions on the model (job b77 u1)
        cov = mark_coverage(path, shape, (mark["center"][0] * MASTER, mark["center"][1] * MASTER), mark["width"] * MASTER,
                            height=float(mark["height"]) * MASTER if mark.get("height") else None)
        over(out, spec.colour(mark["colour"]), cov)
    # ``sleeve_swooshes`` ({"colour"}): the maker's swoosh, drawn on the sleeves (author_sleeve), not on the retail
    # maker spots of the shoulder tops (TORSO_SLEEVE_MARKS), which stay the plain jersey
    return decorate(out, spec, t.get("decorations"), marks, "torso")


def author_sleeve(spec: Spec, kit: dict, retail: Path, marks: Path | None = None) -> np.ndarray:
    s = kit["sleeve"]
    selector = kit["selector"]
    ref = load(retail / selector / "sleeve.png")
    h, w = ref.shape[:2]
    out = np.zeros((h * MASTER, w * MASTER, 4), dtype=np.float32)
    out[..., :3] = spec.colour(s["base_colour"])
    out[..., 3] = 1.0
    if s.get("stripes_from"):
        donor = load(retail / s["stripes_from"] / "sleeve.png")
        # donor stripes: every pixel far from the donor's base colour (white) is stripe coverage
        base = np.median(donor[..., :3].reshape(-1, 3), axis=0)
        cov = np.clip(np.abs(donor[..., :3] - base).sum(axis=2) / 1.2, 0.0, 1.0)
        cov_up = smooth_threshold(np.asarray(Image.fromarray(cov).resize((w * MASTER, h * MASTER), Image.BICUBIC), dtype=np.float32), 0.35, 0.65)
        over(out, spec.colour(s["stripe_colour"]), cov_up)
    out = decorate(out, spec, s.get("decorations"), marks, "sleeve")
    if s.get("art_shift_rows"):
        # ``art_shift_rows`` (retail px): the sleeve's own art moved down each arm's island, the top refilled with
        # the base colour, so the swoosh sits above it as on the real jersey (job uw v57); art pushed past an
        # island's bottom would be cut, which the tool refuses
        out = shift_sleeve_islands(out, int(s["art_shift_rows"]), spec.colour(s["base_colour"]), kit["selector"])
    # the maker's swoosh on both arms (the kit's ``torso.sleeve_swooshes`` colour), over the sleeve art as on the
    # real jersey (SLEEVE_SWOOSH); a kit whose own design places it (``decorations`` with "@nike_swoosh") sets none;
    # ``sleeve_swooshes.offset`` [dx, dy] (retail px) moves it on both arms
    sw = kit["torso"].get("sleeve_swooshes")
    if sw:
        for arm in ("R", "L"):
            sleeve_swoosh(out, spec.colour(sw["colour"]), arm, offset=tuple(sw.get("offset", (0.0, 0.0))))
    return out


SLEEVE_ISLANDS = ((0, 64), (64, 128))    # retail rows of the right and left arm's islands, the seam at each top


def shift_sleeve_islands(out: np.ndarray, rows: int, base: np.ndarray, label: str = "") -> np.ndarray:
    """Move each arm island's art ``rows`` retail px down its island (toward the cuff); the vacated top rows take
    ``base``. Refuses a shift that would push art (texels away from ``base``) past an island's bottom."""
    k = rows * MASTER
    res = out.copy()
    for top, bot in SLEEVE_ISLANDS:
        t, b = top * MASTER, bot * MASTER
        lost = out[b - k:b, :, :3]
        if (np.abs(lost - base[None, None, :3]).sum(axis=2) > 0.15).any():
            raise SystemExit(f"{label}: art_shift_rows {rows} would cut the sleeve art at the island's bottom")
        res[t + k:b] = out[t:b - k]
        res[t:t + k, :, :3] = base[None, None, :3]
        res[t:t + k, :, 3] = 1.0
    return res


def author_pants(spec: Spec, kit: dict, retail: Path, marks: Path) -> np.ndarray:
    """The set's pants: the retail pant fabric recoloured with its shading, the 2026 stripe in both seam bands and
    the swoosh for the maker mark. ``base_from`` (another set of the same team) takes the retail texture (fabric,
    shading, belt, shield) from that set's pants instead: a white retail pant made dark keeps faint light blobs
    where its thigh pads are brighter than its base, so a dark 2026 pant is best made from a set whose retail pants
    were dark (job d8: SEA 26H0 from 26A0, ARI 00H0 from 00A0). Without a dark set, a white base made dark counts
    its brighter texels as fabric too, so the pads go dark with the rest."""
    p = kit["pants"]
    own = load(retail / kit["selector"] / "pants.png")
    ref = load(retail / p["base_from"] / "pants.png") if p.get("base_from") else own
    if ref.shape != own.shape:
        raise SystemExit(f"{kit['selector']} pants: base_from {p['base_from']} is {ref.shape[1]}x{ref.shape[0]}, "
                         f"the set's own pants are {own.shape[1]}x{own.shape[0]}")
    h, w = ref.shape[:2]
    H, W = h * MASTER, w * MASTER
    base_ref = np.median(ref[80:200, 180:330, :3].reshape(-1, 3), axis=0)
    up = upscale(ref)
    out = up.copy()
    target = spec.colour(p["base_colour"])
    # recolour the pant fabric (everything near the retail base colour) keeping its shading ratio
    diff = up[..., :3] - base_ref
    if (float(base_ref.mean()) > 0.8 and float(base_ref.max() - base_ref.min()) < 0.05
            and float(target.mean()) < float(base_ref.mean()) - 0.25):
        # a white base made dark: texels brighter than the base (thigh pads, highlights) are fabric as well, so
        # only a darker shade or a hue counts as distance (a light 2026 pant keeps the plain rule)
        lift = diff.mean(axis=2, keepdims=True)
        near = np.abs(diff - lift).sum(axis=2) + 3.0 * np.maximum(-lift[..., 0], 0.0)
    else:
        near = np.abs(diff).sum(axis=2)
    fabric = smooth_threshold(1.0 - np.clip(near / 0.35, 0.0, 1.0), 0.3, 0.8)
    luma_ref = float(base_ref.mean())
    ratio = shade_ratio(up[..., :3].mean(axis=2) / max(luma_ref, 1e-3), target)[..., None]
    shaded = np.clip(target[None, None, :] * ratio, 0.0, 1.0)
    out[..., :3] = out[..., :3] * (1 - fabric[..., None]) + shaded * fabric[..., None]
    shape = (H, W)
    # clear the retail stripe bands to the base colour, then draw the new stripe centred in each band
    widths = [int(n) for _, n in p["stripe"]]
    total = sum(widths)
    for band, (x0, x1) in enumerate(PANTS_STRIPE_BANDS):
        # two retail pixels of margin: the upscale rings a little past the retail band edges
        over(out, target, rect_coverage(shape, (x0 - 2) * MASTER, 0, (x1 + 2) * MASTER, H))
        start = (x0 + x1) / 2.0 - total / 2.0
        # the second band is the other leg's outer seam: an asymmetric stripe is drawn mirrored there (job d5)
        stripes = p["stripe"] if band == 0 or not p.get("mirror_band_2", True) else list(reversed(p["stripe"]))
        for name, n in stripes:
            over(out, spec.colour(name), rect_coverage(shape, start * MASTER, 0, (start + n) * MASTER, H))
            start += n
    # the 2004 hip marks (the NFL shield on the left hip, the maker's mark on the right) are filled from the fabric
    # around them, shading kept; the 2026 swoosh goes on the front of the left hip (PANTS_SWOOSH)
    for box in (PANTS_SHIELD_BOX, PANTS_MAKER_BOX):
        out = _clear_old_mark(out, box)
    ps = PANTS_SWOOSH
    place_mark(out, "nike_swoosh", (ps["centre"][0] * MASTER, ps["centre"][1] * MASTER), ps["width_px"] * MASTER,
               ps["height_px"] * MASTER, colour=spec.colour(p["swoosh_colour"]))
    if p.get("hip_shield", True):
        sh = PANTS_SHIELD
        place_mark(out, "nfl_shield", (sh["centre"][0] * MASTER, sh["centre"][1] * MASTER), sh["width_px"] * MASTER,
                   sh["height_px"] * MASTER)
    out = decorate(out, spec, p.get("decorations"), marks, "pants")
    out[..., 3] = 1.0
    return out


def author_socks(spec: Spec, kit: dict, retail: Path, equipment: Path) -> np.ndarray:
    """The socks (TSET socks00; the project and the pack make its mud twin from it with the retail darken rule, so
    stripes carry over to the muddy socks). ``socks.colour``: one solid colour with the retail fabric shading.
    ``socks.stripes`` [{"colour", "y", "height"}] adds horizontal bands (rows of the 64 px sock texture, top down)
    in the same shading. ``socks.transfer`` {"from": an outer index whose retail socks have the 2026 stripe layout
    (default the kit's own), "palette": [[retail colour, 2026 colour], ...]} instead re-mixes every texel of those
    retail socks from the matching 2026 colours (non-negative least squares per texel, summing to one), so stripe
    edges, anti-aliasing and shading carry over (job d2's socks_fix.py)."""
    socks = kit["socks"]
    outer = kit["outer_index"]
    if socks.get("transfer"):
        tr = socks["transfer"]
        ref = load(equipment / f"tset_{tr.get('from', outer)}_4_0_socks00.png")
        h, w = ref.shape[:2]
        up = np.asarray(Image.fromarray((ref[..., :3] * 255 + 0.5).astype(np.uint8)).resize((w * MASTER, h * MASTER),
                        Image.BICUBIC), dtype=np.float64) / 255.0          # the bands are horizontal: bicubic
        a = np.stack([spec.colour(p[0]) for p in tr["palette"]], axis=1).astype(np.float64)   # 3 x k
        b = np.stack([spec.colour(p[1]) for p in tr["palette"]], axis=1).astype(np.float64)
        x = up.reshape(-1, 3).T
        # a soft sum-to-one row keeps the mix weights barycentric
        weights, *_ = np.linalg.lstsq(np.vstack([a, np.full((1, a.shape[1]), 3.0)]),
                                      np.vstack([x, np.full((1, x.shape[1]), 3.0)]), rcond=None)
        weights = np.clip(weights, 0.0, None)
        weights /= np.maximum(weights.sum(axis=0, keepdims=True), 1e-6)
        out = np.ones((h * MASTER, w * MASTER, 4), dtype=np.float32)
        out[..., :3] = np.clip((b @ weights).T.reshape(h * MASTER, w * MASTER, 3), 0.0, 1.0)
        return out
    ref = load(equipment / f"tset_{outer}_4_0_socks00.png")
    h, w = ref.shape[:2]
    up = upscale(ref)
    colour = spec.colour(socks["colour"])
    luma = up[..., :3].mean(axis=2)
    # retail socks are a flat stirrup over a white lower half; 2026 socks are one solid colour: keep only the
    # fabric's relative shading (normalised by its own median), not the retail colour split
    ratio = np.clip(1.0 + (luma - np.median(luma, axis=1, keepdims=True)) * 0.6, 0.85, 1.1)[..., None]
    out = np.zeros_like(up)
    out[..., :3] = np.clip(colour[None, None, :] * ratio, 0.0, 1.0)
    out[..., 3] = 1.0
    shape = out.shape[:2]
    for band in socks.get("stripes", ()):
        cov = rect_coverage(shape, 0, float(band["y"]) * MASTER, shape[1], (float(band["y"]) + float(band["height"])) * MASTER)
        lit = np.clip(spec.colour(band["colour"])[None, None, :] * ratio, 0.0, 1.0)
        out[..., :3] = out[..., :3] * (1 - cov[..., None]) + lit * cov[..., None]
    return out


def _soft_band(dist: np.ndarray, edge: float) -> np.ndarray:
    """Anti-aliased 0..1 coverage of ``dist <= edge`` (one master pixel of ramp)."""
    return np.clip(edge - dist + 0.5, 0.0, 1.0)


def render_font_glyph(font_file: str, char: str, donor_cov: np.ndarray, outline_total_frac: float) -> np.ndarray:
    """A glyph from a font file, fitted to the donor glyph's box: the whole glyph with its outlines is as tall as the
    retail glyph and centred where it was, so the game's own placement (one glyph per texture, two for 10..99)
    keeps working. Returns the fill coverage at master size."""
    from PIL import ImageFont
    ys, xs = np.nonzero(donor_cov > 0.5)
    if len(ys) == 0:
        return np.zeros_like(donor_cov)
    box_h = float(ys.max() + 1 - ys.min())
    cx, cy = (xs.min() + xs.max() + 1) / 2.0, (ys.min() + ys.max() + 1) / 2.0
    big = 800
    font = ImageFont.truetype(font_file, big)
    canvas = Image.new("L", (big * 2, big * 2), 0)
    ImageDraw.Draw(canvas).text((big // 2, big // 4), char, font=font, fill=255)
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    gy, gx = np.nonzero(arr > 0.5)
    arr = arr[gy.min():gy.max() + 1, gx.min():gx.max() + 1]
    fill_h = box_h / (1.0 + 2.0 * outline_total_frac)
    scale = fill_h / arr.shape[0]
    w = max(1, int(round(arr.shape[1] * scale)))
    h = max(1, int(round(arr.shape[0] * scale)))
    glyph = np.asarray(Image.fromarray((arr * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS),
                       dtype=np.float32) / 255.0
    out = np.zeros_like(donor_cov)
    x0, y0 = int(round(cx - w / 2.0)), int(round(cy - h / 2.0))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dx1, dy1 = min(out.shape[1], x0 + w), min(out.shape[0], y0 + h)
    out[dy0:dy1, dx0:dx1] = glyph[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]
    return out


_NAME_METRICS: dict | None = None


def name_metrics(selector: str) -> list[dict]:
    """The name-atlas cells of a uniform set (the NAME metrics object beside the ``names`` strip): per character
    its x offset in the strip and its advance (the glyph occupies columns offset .. offset + advance - 1). From the
    Studio's audited nameplate report (all 634 sets); 628 sets share one offset pattern, the Cowboys' six alternates
    another."""
    global _NAME_METRICS
    if _NAME_METRICS is None:
        report = json.loads((ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json")
                            .read_text(encoding="utf-8"))
        _NAME_METRICS = {o["selector"]["logical_name"].upper(): o["metrics"] for o in report["name_objects"]}
    return _NAME_METRICS[f"{selector.upper()}.IFF"]


def render_font_box(font_file: str, char: str, width: int, height: int) -> np.ndarray:
    """A font glyph's ink stretched to exactly ``width`` x ``height`` pixels (the name-atlas cells are fixed boxes
    the game packs by advance, so the glyph fills its cell the way the retail letters do)."""
    from PIL import ImageFont
    big = 400
    font = ImageFont.truetype(font_file, big)
    canvas = Image.new("L", (big * 2, big * 2), 0)
    ImageDraw.Draw(canvas).text((big // 2, big // 4), char, font=font, fill=255)
    arr = np.asarray(canvas, dtype=np.uint8)
    ys, xs = np.nonzero(arr > 127)
    if len(ys) == 0 or width < 1 or height < 1:
        return np.zeros((max(height, 1), max(width, 1)), np.float32)
    ink = Image.fromarray(arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    return np.asarray(ink.resize((width, height), Image.LANCZOS), dtype=np.float32) / 255.0


def font_name_strip(font_file: str, selector: str, donor_cov: np.ndarray, inset: float) -> np.ndarray:
    """The ``names`` strip redrawn in a font: every mapped cell (apostrophe, hyphen, A..Z; lower case shares the
    upper-case cell) gets the font's glyph stretched into the retail glyph's box (the cell's advance less one
    column, the retail glyph's ink rows), inset by ``inset`` master pixels for outlines. The last cell (metric 28,
    unmapped by the name mapper) holds a small lower-case c in retail, drawn here in the font too. The NAME metrics
    are not changed, so the game spaces the new letters exactly as before."""
    out = np.zeros_like(donor_cov)
    for metric in name_metrics(selector):
        chars = metric["characters"]
        x0 = int(metric["atlas_offset_u16"]) * MASTER
        adv = int(metric["advance_metric_u16"]) * MASTER
        cell = donor_cov[:, x0:x0 + 32 * MASTER]
        if chars.startswith("PORTME"):
            char = "c"                  # the unmapped cell holds a small lower-case c (the retail art: Mc names)
        elif chars and (chars[0] in "'-" or chars[0].isalpha()):
            char = chars[0].upper()
        else:
            out[:, x0:x0 + cell.shape[1]] = cell
            continue
        rows = np.nonzero((cell > 0.5).any(axis=1))[0]
        if len(rows) == 0:
            continue
        y0, y1 = int(rows.min() + inset), int(rows.max() + 1 - inset)
        width = adv - MASTER if adv > 3 * MASTER else adv          # one clear column between letters
        side = min(inset, max(0.0, (width - 2 * MASTER) / 2.0))    # narrow letters (I) keep two retail columns
        bx0, bx1 = int(x0 + side), int(x0 + width - side)
        if bx1 - bx0 < 2 or y1 - y0 < 2:
            continue
        out[y0:y1, bx0:bx1] = render_font_box(font_file, char, bx1 - bx0, y1 - y0)
    return out


def inline_native(spec: Spec, g: dict, master: np.ndarray) -> np.ndarray:
    """The native digit for a glyph block with an ``inline``: the box-downscaled fill, then the inline drawn as a
    clean ring of whole texels (inside distance on the native coverage), so the Studio's two-tone digit import
    keeps one continuous line instead of a half-covered blend (job u7)."""
    from scipy import ndimage
    native = downscale(master)
    inset, width = [float(v) for v in g.get("inline_px", [1, 1])]
    solid = native[..., 3] > 0.5
    inside = ndimage.distance_transform_edt(solid)
    ring = solid & (inside > inset) & (inside <= inset + width)
    native[..., :3] = np.where(native[..., 3:4] > 1e-4, spec.colour(g["fill"])[None, None, :], native[..., :3])
    native[ring, :3] = spec.colour(g["inline"])
    return native


def render_polygon_glyph(shape: dict, canvas_shape, *, height: float, center) -> np.ndarray:
    """Rasterize a traced flat digit with explicit outer contours and holes.

    Coordinates use the shape's own units; ``height`` and ``center`` use master pixels. The same height/centre
    can be shared by all ten glyphs, so a new font never inherits ten different retail registration boxes.
    """
    width, units = float(shape["width"]), float(shape["height"])
    if not (0 < width <= units * 2 and units > 0 and height > 0):
        raise ValueError("invalid traced digit dimensions")
    contours = shape.get("contours", ())
    if not contours:
        raise ValueError("a traced digit needs an outer contour")
    ss = 4
    canvas = Image.new("L", (canvas_shape[1] * ss, canvas_shape[0] * ss))
    drawing = ImageDraw.Draw(canvas)
    scale = height / units
    origin = (float(center[0]) - width * scale / 2, float(center[1]) - height / 2)
    for paths, colour in ((contours, 255), (shape.get("holes", ()), 0)):
        for points in paths:
            if len(points) < 3 or any(len(p) != 2 or not all(math.isfinite(float(v)) for v in p) for p in points):
                raise ValueError("invalid traced digit contour")
            drawing.polygon([((origin[0] + float(x) * scale) * ss,
                              (origin[1] + float(y) * scale) * ss) for x, y in points], fill=colour)
    return np.asarray(canvas.resize(canvas_shape[::-1], Image.BOX), dtype=np.float32) / 255.0


def author_glyphs(spec: Spec, kit: dict, retail: Path, name: str, fill_key: str) -> np.ndarray:
    """Numbers and name letters. The glyph shapes come from the donor set's retail glyphs, or, for a team with a new
    number font, from a font file fitted to the retail glyph boxes (``font``). Optional outlines (``outline``,
    ``outline2``, widths as fractions of the glyph height: ``outline_frac``, ``outline2_frac``) are measured from
    the glyph edge: on retail shapes they are cut from inside the shape (the retail glyph already includes its
    outline), on font glyphs they grow outwards to the retail box. The Giants use a plain fill (no keys set)."""
    from scipy import ndimage
    g = kit[fill_key]
    donor = load(retail / g["glyph_donor"] / f"{name}.png")
    cov = glyph_master(donor)
    rows_with_ink = np.nonzero((cov > 0.5).any(axis=1))[0]
    glyph_h = float(rows_with_ink.max() + 1 - rows_with_ink.min()) if len(rows_with_ink) else 1.0
    o1 = float(g.get("outline_frac", 0.0)) if g.get("outline") else 0.0
    o2 = float(g.get("outline2_frac", 0.0)) if g.get("outline2") else 0.0
    font = g.get("font")
    shapes = g.get("glyph_shapes") if name.startswith("digit_") else None
    if shapes and font:
        raise ValueError("choose a font file or traced glyph shapes")
    if (font or shapes) and (name.startswith("digit_") or name == "nameplate"):
        if name == "nameplate":
            letter_h = 24.0 * MASTER                                  # the retail cap height (rows 4..27)
            fill = font_name_strip(font, g["glyph_donor"], cov, (o1 + o2) * letter_h)
            glyph_h = letter_h
        elif shapes:
            glyph_h = float(g["glyph_height"]) * MASTER
            center = [float(v) * MASTER for v in g["glyph_center"]]
            fill = render_polygon_glyph(shapes[name.rsplit("_", 1)[1]], cov.shape,
                                        height=glyph_h / (1 + 2 * (o1 + o2)), center=center)
        else:
            fill = render_font_glyph(font, name.rsplit("_", 1)[1], cov, o1 + o2)
        outside = ndimage.distance_transform_edt(fill < 0.5)
        layers = [(g.get("outline2"), np.maximum(fill, _soft_band(outside, (o1 + o2) * glyph_h))) if o2 else None,
                  (g.get("outline"), np.maximum(fill, _soft_band(outside, o1 * glyph_h))) if o1 else None,
                  (g["fill"], fill)]
    else:
        inside = ndimage.distance_transform_edt(cov > 0.5)
        layers = [(g.get("outline2"), cov) if o2 else None,
                  (g.get("outline"), cov * np.clip(inside - o2 * glyph_h + 0.5, 0.0, 1.0)) if o1 else None,
                  (g["fill"], cov * np.clip(inside - (o1 + o2) * glyph_h + 0.5, 0.0, 1.0) if (o1 or o2) else cov)]
    if g.get("inline") and name.startswith("digit_"):
        # a tone-on-tone inline inside the number's edge (the 2020+ Rams numbers, job u7): a band ``inline_px``
        # = [inset, width] in native texels (default one texel in from the edge, one texel wide), drawn on the fill
        inset, width = [float(v) * MASTER for v in g.get("inline_px", [1, 1])]
        body = layers[-1][1]
        inside = ndimage.distance_transform_edt(body > 0.5)
        band = np.clip(inside - inset + 0.5, 0.0, 1.0) * np.clip(inset + width - inside + 0.5, 0.0, 1.0)
        layers.append((g["inline"], band * body))
    # straight-alpha "over": the colour of a half-covered edge pixel is the glyph colour, not a darkened one
    premul = np.zeros(cov.shape + (3,), dtype=np.float32)
    alpha = np.zeros(cov.shape, dtype=np.float32)
    for layer in layers:
        if layer is None:
            continue
        colour, a = layer
        a = np.clip(a, 0.0, 1.0)
        premul = premul * (1 - a[..., None]) + spec.colour(colour)[None, None, :] * a[..., None]
        alpha = alpha * (1 - a) + a
    out = np.zeros(cov.shape + (4,), dtype=np.float32)
    out[..., :3] = np.where(alpha[..., None] > 1e-6, premul / np.maximum(alpha[..., None], 1e-6),
                            spec.colour(g["fill"])[None, None, :])
    out[..., 3] = alpha
    return out


# The two side decals sit at the same place on every team's helmet texture (shared helmet UVs): the lower one reads
# upright, the upper one is the same art turned 180 degrees. Boxes in retail pixels (x0, y0, x1, y1); the flag,
# the screws and the ear-hole slots lie outside them or are dropped as small or off-centre pieces.
HELMET_DECAL_BOXES = {"upper": (40, 44, 112, 108), "lower": (40, 142, 112, 212)}
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _recolour_family(rgbv: np.ndarray, src: np.ndarray, dst: np.ndarray, tol: float = 0.16):
    """Recolour every shaded version of ``src`` to ``dst``, keeping the shading (the pixel's luminance ratio)."""
    luma = rgbv @ LUMA
    k = np.clip(luma / max(float(src @ LUMA), 1e-3), 0.0, 2.5)
    distance = np.linalg.norm(rgbv - src[None, None, :] * k[..., None], axis=2)
    m = smooth_threshold(np.clip(1.0 - distance / tol, 0.0, 1.0), 0.3, 0.7)
    new = np.clip(dst[None, None, :] * k[..., None], 0.0, 1.0)
    return rgbv * (1 - m[..., None]) + new * m[..., None]


def _old_decals(ref: np.ndarray, boxes: dict, erase_box: bool = False) -> tuple[np.ndarray, dict]:
    """The retail side decals: in each box, the pixels that differ from the box's shell colour, kept when they
    belong to the largest piece or sit inside its (enlarged) bounds and are not specks (under 12 percent of the
    largest piece: the facemask screws). Returns the mask (retail pixels) and each decal's centre and size."""
    from scipy import ndimage
    mask = np.zeros(ref.shape[:2], dtype=bool)
    found = {}
    for name, (x0, y0, x1, y1) in boxes.items():
        box = ref[y0:y1, x0:x1, :3]
        border = np.concatenate([box[0], box[-1], box[:, 0], box[:, -1]])
        shell = np.median(border, axis=0)
        diff = np.linalg.norm(box - shell[None, None, :], axis=2) > 0.18
        if erase_box:
            # a many-coloured old decal (JAX's jaguar: spots, whiskers, tongue): every non-shell pixel in the box
            m = ndimage.binary_dilation(diff, iterations=1)
            ys, xs = np.nonzero(m)
            if len(ys):
                found[name] = ((xs.min() + xs.max() + 1) / 2.0 + x0, (ys.min() + ys.max() + 1) / 2.0 + y0,
                               float(xs.max() + 1 - xs.min()), float(ys.max() + 1 - ys.min()))
                mask[y0:y1, x0:x1] |= m
            continue
        lab, n = ndimage.label(diff)
        if n == 0:
            continue
        idx = np.arange(1, n + 1)
        sizes = ndimage.sum(diff, lab, idx)
        big = int(idx[int(np.argmax(sizes))])
        by, bx = np.nonzero(lab == big)
        ex, ey = 0.25 * (bx.max() + 1 - bx.min()), 0.25 * (by.max() + 1 - by.min())
        centres = ndimage.center_of_mass(diff, lab, idx)
        floor = max(40.0, 0.12 * float(sizes.max()))  # the facemask screws on helmet02 are about 7% of a decal
        keep = [int(i) for i, s, (cy, cx) in zip(idx, sizes, centres)
                if i == big or (s >= floor and bx.min() - ex <= cx <= bx.max() + ex and by.min() - ey <= cy <= by.max() + ey)]
        m = ndimage.binary_dilation(np.isin(lab, keep), iterations=1)
        ys, xs = np.nonzero(m)
        found[name] = ((xs.min() + xs.max() + 1) / 2.0 + x0, (ys.min() + ys.max() + 1) / 2.0 + y0,
                       float(xs.max() + 1 - xs.min()), float(ys.max() + 1 - ys.min()))
        mask[y0:y1, x0:x1] |= m
    return mask, found


def decal_flip(facing: str, mark_faces: str = "right") -> bool:
    """Whether the lower (left-side) decal is the mark flipped horizontally: the head must sit at the texture's left
    (the front: u grows toward the rear on both islands) for "front", at the right for "rear"."""
    return facing != "image" and ((facing == "front") != (mark_faces == "left"))


def _place_logo(canvas: np.ndarray, logo: Image.Image, centre, max_w: float, max_h: float, rotate: bool,
                flip_h: bool = False, flip_v: bool = False) -> None:
    """Composite an RGBA logo (straight alpha) into a master canvas, fitted inside max_w x max_h at ``centre``."""
    logo = logo.crop(logo.getbbox())
    if flip_h:
        logo = logo.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_v:
        logo = logo.transpose(Image.FLIP_TOP_BOTTOM)
    if rotate:
        logo = logo.rotate(180)
    s = min(max_w / logo.width, max_h / logo.height)
    w, h = max(1, int(round(logo.width * s))), max(1, int(round(logo.height * s)))
    arr = np.asarray(logo.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
    x0, y0 = int(round(centre[0] - w / 2.0)), int(round(centre[1] - h / 2.0))
    region = canvas[y0:y0 + h, x0:x0 + w]
    a = arr[: region.shape[0], : region.shape[1], 3:4]
    region[..., :3] = region[..., :3] * (1 - a) + arr[: region.shape[0], : region.shape[1], :3] * a


_HELMET_GEOMETRY: list = [None]
HELMET_WRAP_DIR = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_helmet_wraps"


def use_helmet_geometry(path: Path | str | None) -> None:
    """The head export (JSON with ``HI_HELMET_C``: pos, uv, tris) that ``helmet.side_logo`` projects its logos through.
    Read only; game-derived, so it comes from the user's own disc and never from the repository."""
    _HELMET_GEOMETRY[0] = None if path is None else Path(path)


def _apply_side_logo(out: np.ndarray, spec: Spec, side_logo: dict, marks: Path | None) -> np.ndarray:
    """``helmet.side_logo`` {"mark", "centre": [z, y], "width", "angle", "facing", "layout": {"right": {"box": ...},
    "left": {...}}, "wrap": name of a mask in data/nfl2k5_helmet_wraps} on the shell C art (``helmet02``): the old side
    logos (their ``layout`` boxes, native texels) are erased and the mark is painted where the real helmet wears it,
    seen from the side (tools/b77/sh1_helmet.py: the Seahawks' hawk faces the REAR on both sides)."""
    import importlib.util
    geometry = _HELMET_GEOMETRY[0]
    if geometry is None:
        raise SystemExit("helmet.side_logo needs the head export: pass --helmet-geometry (use_helmet_geometry)")
    name = "b77_sh1_helmet"
    if name not in sys.modules:
        module_spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "b77" / "sh1_helmet.py")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        module_spec.loader.exec_module(module)
    sh1 = sys.modules[name]
    pm = sh1.posmap(geometry, out.shape[0])
    mark = sh1.prepare_mark((marks or Path(".")) / spec.data["marks"][side_logo["mark"]])
    wrap = sh1.load_wrap(HELMET_WRAP_DIR / f"{side_logo['wrap']}.png") if side_logo.get("wrap") else None
    placement = {"centre": side_logo["centre"], "width": side_logo["width"], "angle": side_logo["angle"],
                 "facing": side_logo.get("facing", "rear")}
    sh1.apply_master(out, pm, mark, side_logo["layout"], placement, wrap=wrap)
    return out


def author_helmet(spec: Spec, kit: dict, retail: Path, family: str, marks: Path | None = None) -> np.ndarray:
    """The live helmet: shell and stripe recoloured with the retail shading kept, and (``decal``) the side logos
    redrawn from a full-colour mark. The Giants path (``shell`` and ``stripe`` on the retail navy and red) is
    unchanged; other teams name their retail colours: ``shell_from`` and ``recolour`` [{"from", "to", "tolerance",
    "box" (retail px) or "region" (a helmet place: stripe_band, ...)}]. ``decorations`` (as on the torso, with the
    helmet places) are painted on the shell before the decal. ``decal``: {"mark", "scale", "boxes", "erase": "box"
    (every non-shell pixel in each box is old decal), "centres"/"sizes" by decal name (retail px)}."""
    hs = kit["helmet"]
    ref = load(retail / kit["selector"] / f"helmet_{family}.png")
    up = upscale(ref)
    rgbv = up[..., :3]
    out = up.copy()
    if "shell_from" not in hs:
        r, g, b = rgbv[..., 0], rgbv[..., 1], rgbv[..., 2]
        # shell: the retail navy family (blue-dominant, low red and green), by ratio to the retail base (4, 8, 101)
        shell = smooth_threshold(np.clip((b - np.maximum(r, g) - 0.12) / 0.2, 0.0, 1.0), 0.2, 0.8) * (r < 0.35) * (g < 0.4)
        base = np.array([4, 8, 101], dtype=np.float32) / 255.0
        k = np.clip(b / base[2], 0.0, 2.2)[..., None]
        shell_new = np.clip(spec.colour(hs["shell"])[None, None, :] * k, 0.0, 1.0)
        out[..., :3] = rgbv * (1 - shell[..., None]) + shell_new * shell[..., None]
        # stripe: the retail red (207, 0, 54) family
        red = smooth_threshold(np.clip((r - np.maximum(g, b) - 0.25) / 0.2, 0.0, 1.0), 0.2, 0.8)
        kr = np.clip(r / (207 / 255.0), 0.0, 1.3)[..., None]
        red_new = np.clip(spec.colour(hs["stripe"])[None, None, :] * kr, 0.0, 1.0)
        out[..., :3] = out[..., :3] * (1 - red[..., None]) + red_new * red[..., None]
    else:
        out[..., :3] = _recolour_family(rgbv, spec.colour(hs["shell_from"]), spec.colour(hs["shell"]))
        for rule in hs.get("recolour", []):
            new = _recolour_family(out[..., :3], spec.colour(rule["from"]), spec.colour(rule["to"]),
                                   float(rule.get("tolerance", 0.16)))
            box = rule.get("box") or (LAYOUT["helmet"][rule["region"]] if rule.get("region") else None)
            if box:
                # a rule limited to a box (retail px or a helmet place): the stripe, not the ear holes and screws
                m = _box(up.shape[:2], box)[..., None]
                out[..., :3] = out[..., :3] * (1 - m) + new * m
            else:
                out[..., :3] = new
    if hs.get("decorations"):
        out = decorate(out, spec, hs["decorations"], marks, "helmet")   # on the shell, before the decal
    decal = hs.get("decal")
    if decal:
        boxes = {k: tuple(v) for k, v in decal.get("boxes", HELMET_DECAL_BOXES).items()}
        mask_r, found = _old_decals(ref, boxes, erase_box=decal.get("erase") == "box")
        for name in list(found):
            # sizes and centres set by eye (retail px) when the old decal's pieces mislead the automatic box
            cx, cy, w, h = found[name]
            if name in decal.get("centres", {}):
                cx, cy = decal["centres"][name]
            if name in decal.get("sizes", {}):
                w, h = decal["sizes"][name]
            found[name] = (cx, cy, w, h)
        mask = np.asarray(Image.fromarray(mask_r.astype(np.uint8) * 255).resize(up.shape[1::-1], Image.NEAREST),
                          dtype=np.float32) / 255.0
        # fill the old decal from the surrounding SHELL only (the ear-hole slots, screws and the flag must not smear
        # into it): the fill weights each neighbour by how close it is to a shaded version of the new shell colour
        shell_rgb = spec.colour(hs["shell"])
        luma = out[..., :3] @ LUMA
        k = np.clip(luma / max(float(shell_rgb @ LUMA), 1e-3), 0.0, 2.5)
        shellness = np.exp(-(np.linalg.norm(out[..., :3] - shell_rgb[None, None, :] * k[..., None], axis=2) / 0.08) ** 2)
        out = _inpaint_weighted(out, mask, shellness, 2.0 * MASTER)
        with Image.open((marks or Path(".")) / spec.data["marks"][decal["mark"]]) as image:
            logo = image.convert("RGBA")
        scale = float(decal.get("scale", 1.0))
        facing = decal.get("facing", "image")
        if facing not in ("image", "front", "rear"):
            raise SystemExit("helmet.decal.facing is image, front or rear")
        mark_faces = decal.get("mark_faces", "right")
        if mark_faces not in ("left", "right"):
            raise SystemExit("helmet.decal.mark_faces is left or right")
        # "image" (the default, text and unmirrored logos): the same picture on both sides, so a mark that faces right
        # points to the rear on the left side and to the front on the right side. "front"/"rear": the head points that
        # way on BOTH sides (u grows toward the rear on both islands; the upper island is the lower one flipped
        # vertically), which a team that mirrors its logo needs (job sh1)
        flip_h = decal_flip(facing, mark_faces)
        for name, (cx, cy, w, h) in found.items():
            if facing == "image":
                _place_logo(out, logo, (cx * MASTER, cy * MASTER), w * MASTER * scale, h * MASTER * scale,
                            rotate=(name == "upper"))
            else:
                _place_logo(out, logo, (cx * MASTER, cy * MASTER), w * MASTER * scale, h * MASTER * scale,
                            rotate=False, flip_h=flip_h, flip_v=(name == "upper"))
    if hs.get("atlas_decal"):
        import importlib.util
        name = "b77_uni_helmet"
        if name not in sys.modules:
            ms = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "b77" / "uni_helmet.py")
            module = importlib.util.module_from_spec(ms)
            sys.modules[name] = module
            ms.loader.exec_module(module)
        ad = hs["atlas_decal"]
        with Image.open((marks or Path(".")) / spec.data["marks"][ad["mark"]]) as image:
            logo = image.convert("RGBA")
        out = sys.modules[name].apply_decal(out, logo, ad, spec.colour(hs["shell"]), family)[0]
    elif hs.get("side_logo") and family == "helmet02":
        out = _apply_side_logo(out, spec, hs["side_logo"], marks)
    # keep the retail alpha exactly (decal cutouts, reflection weight)
    out[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize(up.shape[1::-1], Image.NEAREST), dtype=np.float32)
    return out


def _inpaint(img: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    """Fill ``mask`` (1 = replace) from its surroundings by normalised Gaussian blur."""
    from scipy import ndimage
    keep = 1.0 - np.clip(mask, 0.0, 1.0)
    num = np.stack([ndimage.gaussian_filter(img[..., c] * keep, sigma) for c in range(3)], axis=-1)
    den = ndimage.gaussian_filter(keep, sigma)[..., None]
    fill = num / np.maximum(den, 1e-4)
    out = img.copy()
    out[..., :3] = img[..., :3] * keep[..., None] + fill * (1.0 - keep[..., None])
    return out


def _inpaint_weighted(img: np.ndarray, mask: np.ndarray, weight: np.ndarray, sigma: float) -> np.ndarray:
    """Like ``_inpaint``, with every kept neighbour weighted by ``weight`` (0..1); where no weighted neighbour is
    near, the blur widens until one is."""
    from scipy import ndimage
    keep = (1.0 - np.clip(mask, 0.0, 1.0)) * np.clip(weight, 0.0, 1.0)
    out = img.copy()
    fill = np.zeros(img.shape[:2] + (3,), dtype=np.float32)
    done = np.zeros(img.shape[:2], dtype=bool)
    for s in (sigma, sigma * 2, sigma * 4, sigma * 8):
        num = np.stack([ndimage.gaussian_filter(img[..., c] * keep, s) for c in range(3)], axis=-1)
        den = ndimage.gaussian_filter(keep, s)
        ok = (den > 1e-3) & ~done
        fill[ok] = num[ok] / den[ok][:, None]
        done |= ok
    m = np.clip(mask, 0.0, 1.0)[..., None]
    out[..., :3] = img[..., :3] * (1 - m) + fill * m
    return out


def _box(shape_master, box):
    x0, y0, x1, y1 = box
    return rect_coverage(shape_master, x0 * MASTER, y0 * MASTER, x1 * MASTER, y1 * MASTER)


def _navy_ratio(rgbv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(membership, brightness ratio) of the retail navy family inside shaded art."""
    r, g, b = rgbv[..., 0], rgbv[..., 1], rgbv[..., 2]
    member = smooth_threshold(np.clip((b - np.maximum(r, g) - 0.08) / 0.15, 0.0, 1.0), 0.2, 0.8)
    return member, np.clip(b / RETAIL_NAVY_B, 0.0, 2.2)


def author_splayer(spec: Spec, kit: dict, equipment: Path, marks: Path) -> np.ndarray:
    """The small player atlas: the target set's own atlas, with the torso (and sleeve) regions transplanted from a
    plain retail donor set of the same franchise, then recoloured to 2026 and restriped. The Giants path recolours
    the retail navy family; any other team names its colours: ``splayer.recolour`` [{"from", "to", "region":
    torso|sleeve|helmet|pants|socks|all, "tolerance"}] (shading kept), and ``splayer.logo`` {"mark", "box",
    "scale", "centre", "size"} swaps the helmet-side logo."""
    sp = kit["splayer"]
    target = load(equipment / f"p8_{kit['outer_index']}_splayer.png")
    donor = load(equipment / f"p8_{sp['torso_donor_outer']}_splayer.png")
    h, w = target.shape[:2]
    H, W = h * MASTER, w * MASTER
    shape = (H, W)
    t_up, d_up = upscale(target), upscale(donor)
    out = t_up.copy()
    torso = _box(shape, SPLAYER["torso"])[..., None]
    out = out * (1 - torso) + d_up * torso
    if sp.get("sleeve_from_donor"):
        sleeve = _box(shape, SPLAYER["sleeve"])[..., None]
        out = out * (1 - sleeve) + d_up * sleeve
    rgbv = out[..., :3]
    member, ratio = _navy_ratio(rgbv)
    rules = sp.get("recolour")
    regions = {"torso": _box(shape, SPLAYER["torso"]), "sleeve": _box(shape, SPLAYER["sleeve"]),
               "helmet": _box(shape, SPLAYER["helmet"]), "pants": _box(shape, SPLAYER["pants"]),
               "socks": np.clip(_box(shape, SPLAYER["sock"]) + _box(shape, SPLAYER["sock_low"]), 0, 1),
               "all": np.ones(shape, np.float32)}
    if rules:
        # any team: named retail colour families move to 2026 colours per region, the painted shading kept
        for rule in rules:
            m = regions[rule.get("region", "all")][..., None]
            new = _recolour_family(rgbv, spec.colour(rule["from"]), spec.colour(rule["to"]),
                                   float(rule.get("tolerance", 0.16)))
            rgbv[:] = rgbv * (1 - m) + new * m
    # torso: donor navy -> jersey colour (a white donor has no navy and stays as shaded white)
    jersey = spec.colour(kit["torso"]["base_colour"])
    if not rules and float(jersey.mean()) < 0.9:
        m = member * _box(shape, SPLAYER["torso"])
        rgbv[:] = rgbv * (1 - m[..., None]) + np.clip(jersey[None, None, :] * ratio[..., None], 0, 1) * m[..., None]
    # sleeve
    sleeve_colour = spec.colour(kit["sleeve"]["base_colour"])
    if not rules and float(sleeve_colour.mean()) < 0.9:
        m = member * _box(shape, SPLAYER["sleeve"])
        rgbv[:] = rgbv * (1 - m[..., None]) + np.clip(sleeve_colour[None, None, :] * ratio[..., None], 0, 1) * m[..., None]
    if kit["sleeve"].get("stripe_colour"):
        r, g, b = rgbv[..., 0], rgbv[..., 1], rgbv[..., 2]
        redm = smooth_threshold(np.clip((r - np.maximum(g, b) - 0.25) / 0.2, 0.0, 1.0), 0.2, 0.8) * _box(shape, SPLAYER["sleeve"])
        kr = np.clip(r / (207 / 255.0), 0.0, 1.3)
        rgbv[:] = rgbv * (1 - redm[..., None]) + np.clip(spec.colour(kit["sleeve"]["stripe_colour"])[None, None, :] * kr[..., None], 0, 1) * redm[..., None]
    # helmet side: retail navy -> helmet shell colour, retail red -> stripe red (the logo stays)
    if not rules:
        m = member * _box(shape, SPLAYER["helmet"])
        rgbv[:] = rgbv * (1 - m[..., None]) + np.clip(spec.colour(kit["helmet"]["shell"])[None, None, :] * ratio[..., None], 0, 1) * m[..., None]
    # socks: both halves become the one 2026 sock colour, keeping the painted shading
    sock = spec.colour(kit["socks"]["colour"])
    socks = np.clip(_box(shape, SPLAYER["sock"]) + _box(shape, SPLAYER["sock_low"]), 0, 1)
    luma = rgbv.mean(axis=2)
    from scipy import ndimage
    local = ndimage.gaussian_filter(luma, MASTER * 3)
    shade = np.clip(1.0 + (luma - local) * 0.8, 0.8, 1.15)[..., None]
    rgbv[:] = rgbv * (1 - socks[..., None]) + np.clip(sock[None, None, :] * shade, 0, 1) * socks[..., None]
    # pants: retail grey fabric -> 2026 pant colour with its shading, then the 2026 stripe
    pants_box = _box(shape, SPLAYER["pants"])
    ref = np.median(target[10:80, 5:40, :3].reshape(-1, 3), axis=0)
    pant = spec.colour(kit["pants"]["base_colour"])
    # every neutral (low-saturation) pixel of the pant leg is fabric, whatever its shade; the belt strip on top stays
    sat = rgbv.max(axis=2) - rgbv.min(axis=2)
    fabric = smooth_threshold(1.0 - np.clip(sat / 0.25, 0.0, 1.0), 0.2, 0.7) * pants_box
    fabric *= 1.0 - _box(shape, (0, 0, 128, 6))
    kp = shade_ratio(rgbv.mean(axis=2) / max(float(ref.mean()), 1e-3), pant)[..., None]
    rgbv[:] = rgbv * (1 - fabric[..., None]) + np.clip(pant[None, None, :] * kp, 0, 1) * fabric[..., None]
    band = _box(shape, SPLAYER["pants_stripe"]) + _box(shape, SPLAYER["pants_maker"])
    out[..., :3] = rgbv
    out = _inpaint(out, np.clip(band, 0, 1) * pants_box, MASTER * 3)
    rgbv = out[..., :3]
    scale = SPLAYER["pants_scale"]
    total = sum(int(n) for _, n in kit["pants"]["stripe"]) * scale
    start = SPLAYER["pants_stripe_center"] - total / 2.0
    y0, y1 = SPLAYER["pants"][1], SPLAYER["pants"][3]
    for name, n in kit["pants"]["stripe"]:
        over(out, spec.colour(name), rect_coverage(shape, start * MASTER, y0 * MASTER, (start + n * scale) * MASTER, y1 * MASTER))
        start += n * scale
    # the torso's chest mark
    mark = kit["torso"].get("chest_mark")
    if mark:
        cx, cy = SPLAYER["chest_mark"]
        cov = mark_coverage(marks / spec.data["marks"][mark["mark"]], shape, (cx * MASTER, cy * MASTER),
                            SPLAYER["chest_mark_width"] * MASTER)
        over(out, spec.colour(mark["colour"]), cov)
    for box in sp.get("clear", ()):
        # small 2004 marks (maker specks) filled from their surroundings; atlas pixels
        m = np.zeros(shape, np.float32)
        bx0, by0, bx1, by1 = (int(round(v * MASTER)) for v in box)
        m[by0:by1, bx0:bx1] = 1.0
        out = _inpaint_weighted(out, m, (m < 0.5).astype(np.float32), 1.5 * MASTER)
    logo = sp.get("logo")
    if logo:
        # the helmet-side logo, swapped like the Team Select cards' (old logo found by shell colour and hue, filled
        # from the shell, the new mark lit like the shell); box, centre and size are atlas pixels
        with Image.open(marks / spec.data["marks"][logo["mark"]]) as image:
            new_mark = image.convert("RGBA")
        out = _card_logo(out, tuple(logo.get("box", SPLAYER["helmet"])), new_mark, float(logo.get("scale", 1.0)),
                         logo.get("centre"), logo.get("size"))
    out[..., 3] = 1.0
    return out


# Team Select cards are pre-rendered images (a jersey with a number, the pants at the right edge, the helmet in the
# lower left; or a helmet side view over the UI bar). They are recoloured by region and colour class, not redrawn.
CARD_UNIF = {"pants": (222, 84, 256, 256), "helmet": (0, 128, 168, 256), "collar_mark": (64, 70, 96, 92),
             "chest_mark": (80.0, 81.0), "chest_mark_width": 12.0}
# The pants leg on the unif card (card px) for the general card path: the thigh reaches x 175 at the bottom edge and
# the jersey hem bounds it above (measured on the shared pose: CHI 05H0, KC 13H0, PIT 22H0 and 22A0, SEA 26H0). The
# old box (CARD_UNIF["pants"], x 222 on) split the leg (job d6), and stays only in the Giants' own card path.
CARD_UNIF_PANTS = ((173, 256), (174, 202), (182, 138), (190, 121), (198, 113), (222, 95), (230, 92), (256, 91),
                   (256, 256))
# Where the helmet logo sits on the Team Select cards (the render pose is shared by every team; measured on the
# Giants' and Bears' cards, home and away, with a margin). Retail card pixels.
CARD_LOGO_BOXES = {("unif", 256, "H"): (20, 160, 112, 240), ("unif", 256, "A"): (20, 160, 112, 240),
                   ("helm", 256, "H"): (116, 18, 240, 132), ("helm", 256, "A"): (28, 16, 136, 132),
                   ("helm", 128, "H"): (57, 8, 121, 67), ("helm", 128, "A"): (8, 8, 70, 67)}


def _card_regions(shape, family: str, ref_shape) -> dict:
    """Soft region masks of a card at master size: the helmet, the jersey and the pants (unif card), or the helmet
    above the menu bar (helm cards)."""
    if family == "unif":
        pants = polygon_coverage(shape, [(x * MASTER, y * MASTER) for x, y in CARD_UNIF_PANTS])
        helmet = _box(shape, CARD_UNIF["helmet"])
        return {"helmet": helmet, "pants": pants, "jersey": np.clip(1.0 - pants - helmet, 0.0, 1.0),
                "all": np.ones(shape, np.float32)}
    top = _box(shape, (0, 0, ref_shape[1], ref_shape[0] * 0.62))
    return {"helmet": top, "all": top}


def _card_logo(up: np.ndarray, box, logo: Image.Image, scale: float = 1.0, centre=None, size=None) -> np.ndarray:
    """Replace the helmet logo on a card render. In the search box, the lit shell colour is the median of the box's
    rim; the old logo is the largest piece that is not shell (plus pieces inside its bounds, specks dropped). It is
    filled from the surrounding shell only, and the new mark is drawn in the old logo's box with the shell's
    lighting (luminance ratio) on it."""
    from scipy import ndimage
    x0, y0, x1, y1 = (int(v * MASTER) for v in box)
    opaque = up[..., 3] > 0.5
    sub = up[y0:y1, x0:x1, :3]
    rim = np.zeros(sub.shape[:2], bool)
    b = max(2, MASTER * 2)
    rim[:b], rim[-b:], rim[:, :b], rim[:, -b:] = True, True, True, True
    rim &= opaque[y0:y1, x0:x1]
    shell = np.median(sub[rim], axis=0) if rim.any() else np.median(sub.reshape(-1, 3), axis=0)
    luma = up[..., :3] @ LUMA
    k = np.clip(luma / max(float(shell @ LUMA), 1e-3), 0.0, 3.0)
    shellness = np.exp(-(np.linalg.norm(up[..., :3] - shell[None, None, :] * k[..., None], axis=2) / 0.12) ** 2)
    # a dark logo colour can pass for shaded shell by brightness alone, so the hue (chromaticity) counts too
    rgbs = up[..., :3] + 1e-3
    chroma = rgbs / rgbs.sum(axis=2, keepdims=True)
    shell_chroma = (shell + 1e-3) / float((shell + 1e-3).sum())
    hue_off = (np.linalg.norm(chroma - shell_chroma[None, None, :], axis=2) > 0.06) & (luma > 0.04)
    shellness = np.where(hue_off, np.minimum(shellness, 0.1), shellness)
    other = (shellness[y0:y1, x0:x1] < 0.35) & opaque[y0:y1, x0:x1]
    lab, n = ndimage.label(other)
    if n == 0:
        return up
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum(other, lab, idx)
    big = int(idx[int(np.argmax(sizes))])
    by, bx = np.nonzero(lab == big)
    ex, ey = 0.25 * (bx.max() + 1 - bx.min()), 0.25 * (by.max() + 1 - by.min())
    centres = ndimage.center_of_mass(other, lab, idx)
    floor = 0.02 * float(sizes.max())  # thin outline pieces of a logo (a star's outer ring) count
    keep = [int(i) for i, sz, (cy, cx) in zip(idx, sizes, centres)
            if i == big or (sz >= floor and bx.min() - ex <= cx <= bx.max() + ex and by.min() - ey <= cy <= by.max() + ey)]
    # erase the logo's whole convex outline (a star's thin rings and the shell between its points included)
    from scipy.spatial import ConvexHull
    py, px = np.nonzero(np.isin(lab, keep))
    pts = np.stack([px, py], axis=1)[:: max(1, len(px) // 4000)]
    hull = pts[ConvexHull(pts).vertices] if len(pts) >= 3 else pts
    canvas = Image.new("L", (other.shape[1], other.shape[0]), 0)
    ImageDraw.Draw(canvas).polygon([tuple(map(float, v)) for v in hull], fill=255)
    piece = ndimage.binary_dilation(np.asarray(canvas) > 0, iterations=MASTER)
    # the new mark takes the size of the old logo's main parts (pieces at least a quarter of the largest: both
    # letters of a monogram, a star's body), not of thin rings or highlights caught in the hull
    main = [i for i in keep if sizes[i - 1] >= 0.25 * float(sizes.max())]
    ys, xs = np.nonzero(np.isin(lab, main))
    lx0, ly0, lx1, ly1 = xs.min() + x0, ys.min() + y0, xs.max() + 1 + x0, ys.max() + 1 + y0
    if centre is not None or size is not None:
        # set by eye in the spec when the automatic box caught a highlight (card pixels)
        cxm = centre[0] * MASTER if centre is not None else (lx0 + lx1) / 2.0
        cym = centre[1] * MASTER if centre is not None else (ly0 + ly1) / 2.0
        wm = size[0] * MASTER if size is not None else float(lx1 - lx0)
        hm = size[1] * MASTER if size is not None else float(ly1 - ly0)
        lx0, lx1, ly0, ly1 = cxm - wm / 2.0, cxm + wm / 2.0, cym - hm / 2.0, cym + hm / 2.0
    mask = np.zeros(up.shape[:2], np.float32)
    mask[y0:y1, x0:x1] = piece
    out = _inpaint_weighted(up, mask, shellness * (mask < 0.5), 2.0 * MASTER)
    shade = np.clip(np.sqrt((out[..., :3] @ LUMA) / max(float(shell @ LUMA), 1e-3)), 0.8, 1.15)
    logo = logo.crop(logo.getbbox())
    s = min((lx1 - lx0) * scale / logo.width, (ly1 - ly0) * scale / logo.height)
    lw, lh = max(1, int(round(logo.width * s))), max(1, int(round(logo.height * s)))
    arr = np.asarray(logo.resize((lw, lh), Image.LANCZOS), dtype=np.float32) / 255.0
    ox, oy = int(round((lx0 + lx1 - lw) / 2.0)), int(round((ly0 + ly1 - lh) / 2.0))
    region = out[oy:oy + lh, ox:ox + lw]
    a = arr[: region.shape[0], : region.shape[1], 3:4] * (region[..., 3:4] > 0.5)
    lit = np.clip(arr[: region.shape[0], : region.shape[1], :3] * shade[oy:oy + lh, ox:ox + lw][..., None], 0.0, 1.0)
    region[..., :3] = region[..., :3] * (1 - a) + lit * a
    return out


def author_card_general(spec: Spec, kit: dict, retail: Path, name: str, marks: Path | None) -> np.ndarray:
    """Team Select cards for any team: ``card.recolour`` rules [{"from", "to", "region": helmet|jersey|pants|all or
    "box": [x0, y0, x1, y1] (card px), "tolerance", "cards"}] move the render's retail colour families (shading kept; a rule skips a card that lacks
    its region, so helm cards take only helmet and all rules; "cards" limits a rule to named cards), and ``card.logo`` {"mark", "scale"}
    replaces the helmet logo in the shared pose (CARD_LOGO_BOXES, or ``card.logo.boxes`` by card name). The new
    mark takes the old logo's box; when that box caught a highlight, set ``card.logo.centres`` and ``sizes`` by
    card name (unif_256, helm_256, helm_128; card pixels). Check every card by eye."""
    card = kit["card"]
    ref = load(retail / kit["selector"] / f"{name}.png")
    up = upscale(ref)
    family = "unif" if "unif" in name else "helm"
    res = int(name.rsplit("_", 1)[1])
    regions = _card_regions(up.shape[:2], family, ref.shape)
    rgbv = up[..., :3]
    card_name = name.replace("team-select_", "")
    for rule in card.get("recolour", []):
        region = rule.get("region", "all")
        if "box" not in rule and region not in regions:
            continue                      # a jersey or pants rule does not touch a helm card (it has no such part)
        if "cards" in rule and card_name not in rule["cards"]:
            continue                      # "cards": ["unif_256", "helm_256", "helm_128"] limits a rule to some cards
        # "box" [x0, y0, x1, y1] (card px) instead of a region, as on the helmet (limit it with "cards")
        m = (_box(up.shape[:2], rule["box"]) if "box" in rule else regions[region])[..., None]
        new = _recolour_family(rgbv, spec.colour(rule["from"]), spec.colour(rule["to"]), float(rule.get("tolerance", 0.16)))
        rgbv = rgbv * (1 - m) + new * m
    up[..., :3] = rgbv
    logo = card.get("logo")
    if logo:
        side = kit["selector"][-2]
        box = tuple(logo.get("boxes", {}).get(name.replace("team-select_", ""), CARD_LOGO_BOXES[(family, res, side)]))
        with Image.open((marks or Path(".")) / spec.data["marks"][logo["mark"]]) as image:
            mark = image.convert("RGBA")
        up = _card_logo(up, box, mark, float(logo.get("scale", 1.0)), logo.get("centres", {}).get(card_name),
                        logo.get("sizes", {}).get(card_name))
    if family == "unif":
        up = card_maker_swap(up, spec, kit)
    up[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize(up.shape[1::-1], Image.BICUBIC), dtype=np.float32).clip(0, 1)
    return up


def _classes(rgbv: np.ndarray):
    r, g, b = rgbv[..., 0], rgbv[..., 1], rgbv[..., 2]
    navy = smooth_threshold(np.clip((b - np.maximum(r, g) - 0.08) / 0.15, 0.0, 1.0), 0.2, 0.8)
    red = smooth_threshold(np.clip((r - np.maximum(g, b) - 0.22) / 0.2, 0.0, 1.0), 0.2, 0.8)
    sat = rgbv.max(axis=2) - rgbv.min(axis=2)
    neutral = smooth_threshold(1.0 - np.clip(sat / 0.18, 0.0, 1.0), 0.2, 0.8)
    return navy, red, neutral, np.clip(b / RETAIL_NAVY_B, 0.0, 2.6), np.clip(r / (207 / 255.0), 0.0, 1.3)


def _mix(rgbv, member, colour, ratio):
    ratio = np.broadcast_to(np.asarray(ratio, dtype=np.float32), member.shape)
    rgbv[:] = rgbv * (1 - member[..., None]) + np.clip(colour[None, None, :] * ratio[..., None], 0, 1) * member[..., None]


# Every retail unif card carries one 2004 maker mark on the pants hip, in the pose all teams share (job d2).
CARD_MAKER = {"rect": (236, 120, 252, 131), "box": (238.5, 122.5, 249.5, 128.5)}


def card_maker_swap(up: np.ndarray, spec: Spec, kit: dict) -> np.ndarray:
    """The unif card's 2004 maker mark becomes the 2026 swoosh: the mark's rect is filled from its surroundings,
    and the swoosh (the pants' swoosh colour) is drawn with the card's lighting. On by default; ``card_maker``:
    false turns it off, or {"rect", "box", "colour"} moves or recolours it (card pixels)."""
    from scipy import ndimage
    cfg = kit.get("card_maker", {})
    if cfg is False:
        return up
    cfg = cfg if isinstance(cfg, dict) else {}
    x0, y0, x1, y1 = (int(round(v * MASTER)) for v in cfg.get("rect", CARD_MAKER["rect"]))
    shape = up.shape[:2]
    mask = np.zeros(shape, np.float32)
    mask[y0:y1, x0:x1] = 1.0
    mask = np.clip(ndimage.gaussian_filter(mask, 1.0), 0.0, 1.0)
    weight = ((mask <= 0.01) & (up[..., 3] > 0.5)).astype(np.float32)
    out = _inpaint_weighted(up, mask, weight, 2.0 * MASTER)
    colour = spec.colour(cfg.get("colour", kit["pants"].get("swoosh_colour", "white")))
    bx0, by0, bx1, by1 = (v * MASTER for v in cfg.get("box", CARD_MAKER["box"]))
    # the official swoosh fitted to the box's width (its own proportions), lit by the card's render
    alpha = out[..., 3].copy()
    width = bx1 - bx0
    height = width * uniform_mark("nike_swoosh").shape[0] / uniform_mark("nike_swoosh").shape[1]
    place_mark(out, "nike_swoosh", ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0), width, height, colour=colour)
    out[..., 3] = alpha
    return out


def author_card_unif(spec: Spec, kit: dict, retail: Path, marks: Path) -> np.ndarray:
    ref = load(retail / kit["selector"] / "team-select_unif_256.png")
    up = upscale(ref)
    H, W = up.shape[:2]
    shape = (H, W)
    rgbv = up[..., :3]
    navy, red, neutral, kb, kr = _classes(rgbv)
    pants = _box(shape, CARD_UNIF["pants"])
    helmet = _box(shape, CARD_UNIF["helmet"])
    jersey = np.clip(1.0 - pants - helmet, 0.0, 1.0)
    jersey_colour = spec.colour(kit["torso"]["base_colour"])
    num_colour = spec.colour(kit["digits"]["fill"])
    _mix(rgbv, navy * helmet, spec.colour(kit["helmet"]["shell"]), kb)
    _mix(rgbv, red * helmet, spec.colour(kit["helmet"]["stripe"]), kr)
    if float(jersey_colour.mean()) > 0.8:
        # a white jersey: the retail navy trim and number outlines become the surrounding shaded white
        up = _inpaint(up, navy * jersey, MASTER * 2.5)
        rgbv = up[..., :3]
        _mix(rgbv, red * jersey, num_colour, kr)
    else:
        _mix(rgbv, navy * jersey, jersey_colour, kb)
    # the retail collar wordmark becomes the small team logo
    up = _inpaint(up, _box(shape, CARD_UNIF["collar_mark"]) * (up[..., 3] > 0.5), MASTER * 3)
    mark = kit["torso"].get("chest_mark")
    if mark:
        cov = mark_coverage(marks / spec.data["marks"][mark["mark"]], shape,
                            (CARD_UNIF["chest_mark"][0] * MASTER, CARD_UNIF["chest_mark"][1] * MASTER),
                            CARD_UNIF["chest_mark_width"] * MASTER)
        over(up, spec.colour(mark["colour"]), cov * (up[..., 3] > 0.5))
    rgbv = up[..., :3]
    # pants: neutral fabric -> 2026 pant colour; the retail stripe's outer and centre colours -> the 2026 ones
    pant = spec.colour(kit["pants"]["base_colour"])
    _, _, neutral, _, _ = _classes(rgbv)
    _mix(rgbv, neutral * pants, pant, shade_ratio(rgbv.mean(axis=2) / 0.70, pant))
    stripe = kit["pants"]["stripe"]
    navy2, red2, _, _, _ = _classes(rgbv)
    _mix(rgbv, navy2 * pants, spec.colour(stripe[0][0]), 1.0)
    _mix(rgbv, red2 * pants, spec.colour(stripe[len(stripe) // 2][0]), 1.0)
    up[..., :3] = rgbv
    up = card_maker_swap(up, spec, kit)
    up[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize((W, H), Image.BICUBIC), dtype=np.float32).clip(0, 1)
    return up


def author_card_helm(spec: Spec, kit: dict, retail: Path, name: str) -> np.ndarray:
    ref = load(retail / kit["selector"] / f"{name}.png")
    up = upscale(ref)
    rgbv = up[..., :3]
    navy, red, _, kb, kr = _classes(rgbv)
    top = _box(up.shape[:2], (0, 0, ref.shape[1], ref.shape[0] * 0.62))
    _mix(rgbv, navy * top, spec.colour(kit["helmet"]["shell"]), kb)
    _mix(rgbv, red * top, spec.colour(kit["helmet"]["stripe"]), kr)
    up[..., :3] = rgbv
    up[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize(up.shape[1::-1], Image.BICUBIC), dtype=np.float32).clip(0, 1)
    return up


# --------------------------------------------------------------------------------------------- commands
def cmd_author(args) -> int:
    spec = Spec(Path(args.spec))
    retail, marks, out = Path(args.retail), Path(args.marks), Path(args.out)
    manifest = {"schema": ART_SCHEMA, "team": spec.data["team"], "spec": str(args.spec),
                "spec_sha256": hashlib.sha256(Path(args.spec).read_bytes()).hexdigest(), "master_factor": MASTER, "items": []}
    if getattr(args, "uniform_marks", None):
        # the official NFL shield and swoosh masters (pinned), recorded with the art they went into
        manifest["uniform_marks"] = use_uniform_marks(args.uniform_marks)
    if getattr(args, "helmet_geometry", None):
        use_helmet_geometry(args.helmet_geometry)

    keep_retail: list[tuple[str, ...]] = [()]      # the current kit's ``keep_retail`` name prefixes
    file_masters: list[dict] = [{}]                # the current kit's ``files`` (texture name -> master PNG)
    kept: list[str] = []

    def emit(set_selector: str, name: str, master: np.ndarray, kind: str, native: np.ndarray | None = None, **extra):
        if keep_retail[0] and name.startswith(keep_retail[0]):
            kept.append(f"{set_selector} {name}")      # left out, so the project keeps this texture retail
            return
        if name in file_masters[0]:
            # ``files``: {texture name: 4x master PNG} art made outside this tool (job u7: the Team Select cards
            # re-rendered from the 2026 kit, the small player atlas); the native is its box downscale as usual
            path = Path(file_masters[0][name])
            given = load(path)
            if given.shape != master.shape:
                raise SystemExit(f"{set_selector} {name}: {path} is {given.shape[1]}x{given.shape[0]}, "
                                 f"the master must be {master.shape[1]}x{master.shape[0]}")
            master, native = given, None
            extra = dict(extra, source=str(path))
        native = downscale(master) if native is None else native
        if name in ("helmet_helmet00", "helmet_helmet02"):
            ref = load(retail / set_selector / f"{name}.png")
            native[..., 3] = ref[..., 3]
        m = out / "master4x" / set_selector / f"{name}.png"
        n = out / "retail" / set_selector / f"{name}.png"
        row = {"set": set_selector, "name": name, "kind": kind, "retail": str(n.relative_to(out)),
               "retail_size": [native.shape[1], native.shape[0]],
               "retail_sha256": save(native, n, digit_registration=extra.get("digit_registration")),
               "master": str(m.relative_to(out)), "master_size": [master.shape[1], master.shape[0]],
               "master_sha256": save(master, m)}
        row.update(extra)
        manifest["items"].append(row)
        print(f"  {set_selector} {name} {native.shape[1]}x{native.shape[0]}")

    for side, kit in spec.data["kits"].items():
        sel = kit["selector"]
        kit = dict(kit)
        kit.setdefault("outer_index", args.outer_home if side == "home" else args.outer_away)
        # ``keep_retail``: name prefixes (e.g. ["digit_", "nameplate"]) of textures this kit leaves retail (job d7)
        keep_retail[0] = tuple(kit.get("keep_retail", ()))
        file_masters[0] = dict(kit.get("files", {}))
        emit(sel, "torso", author_torso(spec, kit, retail, marks), "torso")
        emit(sel, "sleeve", author_sleeve(spec, kit, retail, marks), "sleeve")
        emit(sel, "pants", author_pants(spec, kit, retail, marks), "pants")
        for family in ("helmet00", "helmet02"):
            emit(sel, f"helmet_{family}", author_helmet(spec, kit, retail, family, marks), "live_helmet", family=family)
        # the glyph block of each digit family: the jersey numbers take ``digits``, the sleeve (TV) numbers
        # ``arm_digits`` (default ``digits``; "none" for a kit without sleeve numbers, e.g. the 2020+ Chargers), the
        # helmet numbers ``helmet_digits`` (default: the digits donor in white)
        arm = kit.get("arm_digits", kit["digits"])
        if not (arm == "none" or isinstance(arm, dict)):
            raise SystemExit(f"{sel}: arm_digits is \"none\" or a glyph block like digits, not {arm!r}")
        blocks = {"jersey": kit["digits"], "arm": arm,
                  "helmet": kit.get("helmet_digits", {"glyph_donor": kit["digits"]["glyph_donor"], "fill": "white"})}
        for fam in ("jersey", "arm", "helmet"):
            kit_f = dict(kit)
            kit_f["_glyphs"] = blocks[fam]
            for digit in range(10):
                name = f"digit_{fam}_{digit}"
                ref_size = load(retail / sel / f"{name}.png").shape[:2]
                if blocks[fam] == "none":
                    # no number: a fully transparent glyph (colour: the jersey's, so no edge can fringe)
                    blank = np.zeros((ref_size[0] * MASTER, ref_size[1] * MASTER, 4), np.float32)
                    blank[..., :3] = spec.colour(kit["torso"]["base_colour"])
                    emit(sel, name, blank, "live_number_nameplate", family=fam, digit=digit, blank=True)
                    continue
                donor = blocks[fam]["glyph_donor"]          # the size check uses the donor this family draws from
                donor_size = load(retail / donor / f"{name}.png").shape[:2]
                if donor_size != ref_size:
                    raise SystemExit(f"{sel} {name}: donor {donor} is {donor_size}, target is {ref_size}")
                master = author_glyphs(spec, kit_f, retail, name, "_glyphs")
                native = inline_native(spec, blocks[fam], master) if blocks[fam].get("inline") else None
                emit(sel, name, master, "live_number_nameplate", native=native, family=fam, digit=digit,
                     **({"digit_registration": blocks[fam]["registration"]} if blocks[fam].get("registration") else {}))
        emit(sel, "nameplate", author_glyphs(spec, kit, retail, "nameplate", "nameplate"), "live_number_nameplate",
             family="nameplate", digit=None)
        emit(sel, "team-select_unif_256", author_card_general(spec, kit, retail, "team-select_unif_256", marks)
             if "card" in kit else author_card_unif(spec, kit, retail, marks), "team_select", family="unif",
             resolution=256)
        for res in (256, 128):
            name = f"team-select_helm_{res}"
            emit(sel, name, author_card_general(spec, kit, retail, name, marks) if "card" in kit
                 else author_card_helm(spec, kit, retail, name),
                 "team_select", family="helm", resolution=res)
        if args.equipment:
            emit(sel, "socks00", author_socks(spec, kit, retail, Path(args.equipment)), "uniform_equipment_texture",
                 asset_id=f"tset:{kit['outer_index']}:4:0:socks00")
            if kit.get("splayer"):
                emit(sel, "splayer", author_splayer(spec, kit, Path(args.equipment), marks), "p8_texture",
                     asset_id=f"p8:{kit['outer_index']}:splayer")
            eq = kit.get("equipment")
            if eq:
                # ``equipment``: {"recolour": [{"from", "to", "tolerance"}], "items": [export stems such as
                # "6_3_glove04"]}: the set's retail gloves, pads, sleeves and shoes with a colour family moved to
                # 2026, shading kept; a mud twin (the next index, "<name>_mud") is made by the project step when
                # the set has one (job u7: the 2004 Rams navy on gloves, wristbands, pads, sleeves and shoes)
                edir = Path(args.equipment)
                for stem in eq["items"]:
                    src = edir / f"tset_{kit['outer_index']}_{stem}.png"
                    chunk, index, tname = stem.split("_", 2)
                    ref_eq = load(src)
                    up = upscale(ref_eq)
                    for rule in eq["recolour"]:
                        up[..., :3] = _recolour_family(up[..., :3], spec.colour(rule["from"]), spec.colour(rule["to"]),
                                                       float(rule.get("tolerance", 0.16)))
                    up[..., 3] = np.asarray(Image.fromarray(ref_eq[..., 3]).resize(up.shape[1::-1], Image.NEAREST),
                                            dtype=np.float32)
                    has_mud = (edir / f"tset_{kit['outer_index']}_{chunk}_{int(index) + 1}_{tname}_mud.png").exists()
                    emit(sel, tname, up, "uniform_equipment_texture",
                         asset_id=f"tset:{kit['outer_index']}:{chunk}:{index}:{tname}", mud=has_mud)
    if kept:
        manifest["kept_retail"] = kept
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"authored {len(manifest['items'])} textures into {out}" + (f" ({len(kept)} kept retail)" if kept else ""))
    return 0


# --------------------------------------------------------------------------------------------- venue art
# The home stadium's per-team art (the three end zone panels, the midfield mark and the two fan-banner sheets), in
# the layout the stadium writer consumes (u2's metlife_team_art/v1 contract for s18). The end zone strip is the three
# 256x128 panels side by side (768x128); the texture squeezes the 53.3 x 10 yard end zone horizontally by 5.33/6, so
# marks are drawn wider by ``stretch`` to read at their true proportions on the field.
FONT_CANDIDATES = ("/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(size_px: int):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size_px)
    return ImageFont.load_default()


def text_coverage(shape, text: str, center, height: float, max_width: float | None = None, lines: int = 1) -> np.ndarray:
    """Bold text as coverage, centred, fitted to a cap height (and a maximum width)."""
    h, w = shape
    ss = 4
    font = _font(int(height * ss * 1.35))
    probe = Image.new("L", (10, 10))
    box = ImageDraw.Draw(probe).multiline_textbbox((0, 0), text, font=font, align="center", spacing=int(height * ss * 0.25))
    tw, th = int(math.ceil(box[2] - box[0])), int(math.ceil(box[3] - box[1]))
    img = Image.new("L", (tw + 8, th + 8), 0)
    ImageDraw.Draw(img).multiline_text((4 - box[0], 4 - box[1]), text, fill=255, font=font, align="center",
                                       spacing=int(height * ss * 0.25))
    target_h = height * ss * lines
    scale = target_h / img.height
    if max_width is not None and img.width * scale > max_width * ss:
        scale = max_width * ss / img.width
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("L", (w * ss, h * ss), 0)
    canvas.paste(img, (round(center[0] * ss - img.width / 2), round(center[1] * ss - img.height / 2)))
    return np.asarray(canvas.resize((w, h), Image.BOX), dtype=np.float32) / 255.0


def framed_mark_coverage(mask_png: Path, frame, shape, center, width: float) -> np.ndarray:
    """A mark cropped to a given frame box of its canvas (not its own bbox), so layers drawn from one canvas (an
    outline and its fill) keep their registration; the frame is placed by centre and width."""
    with Image.open(mask_png) as image:
        alpha = image.convert("RGBA").getchannel("A").crop(frame)
    h, w = shape
    ss = 4
    fw, fh = frame[2] - frame[0], frame[3] - frame[1]
    tw, th = max(1, round(width * ss)), max(1, round(width * fh / fw * ss))
    canvas = Image.new("L", (w * ss, h * ss), 0)
    canvas.paste(alpha.resize((tw, th), Image.LANCZOS), (round(center[0] * ss - tw / 2), round(center[1] * ss - th / 2)))
    return np.asarray(canvas.resize((w, h), Image.BOX), dtype=np.float32) / 255.0


def stretched_mark(mask_png: Path, shape, center, height: float, stretch: float = 1.0) -> np.ndarray:
    with Image.open(mask_png) as image:
        x0, y0, x1, y1 = image.convert("RGBA").getchannel("A").getbbox()
    aw, ah = x1 - x0, y1 - y0                     # the mark's own width and height (not its bbox corner)
    return mark_coverage(mask_png, shape, center, height * aw / ah * stretch, height=height)


def author_endzone_strip(spec: Spec, venue: dict, marks: Path, key: str = "endzone") -> np.ndarray:
    ez = venue[key]
    H, W = 128 * MASTER, 768 * MASTER
    shape = (H, W)
    out = np.zeros((H, W, 4), dtype=np.float32)
    paint = spec.colour(ez["paint"])
    out[..., :3] = paint
    out[..., 3] = ez.get("paint_alpha", 0.92)
    for item in ez.get("marks", ()):
        c = [v * MASTER for v in item["center"]]
        cov = stretched_mark(marks / spec.data["marks"][item["mark"]], shape, c, item["height"] * MASTER, item.get("stretch", 1.0))
        a = cov * item.get("alpha", 0.96)
        out[..., :3] = out[..., :3] * (1 - a[..., None]) + spec.colour(item["colour"])[None, None, :] * a[..., None]
        out[..., 3] = np.maximum(out[..., 3], a)
    return out


def _center_logo_colour(spec: Spec, cl: dict, marks: Path, shape, width: float) -> np.ndarray:
    """The midfield logo in several colours (job d6): ``mark``, a marks PNG drawn in its own colours, or ``layers``,
    [{"mark", "colour"}, ...] single-colour masks of one canvas painted in order and registered in the first
    layer's frame. Either fits inside ``width_frac`` of the square, both ways. ``keyline`` {"colour", "width"
    (retail px)} rings the whole logo for contrast on the grass; ``alpha`` (0.95) lets the grass show a little."""
    from scipy import ndimage
    H, W = shape
    rgb_p = np.zeros((H, W, 3), dtype=np.float32)          # premultiplied colour
    alpha = np.zeros((H, W), dtype=np.float32)
    if cl.get("mark"):
        with Image.open(marks / spec.data["marks"][cl["mark"]]) as image:
            logo = image.convert("RGBA")
        logo = logo.crop(logo.getbbox())
        s = min(width / logo.width, width / logo.height)
        w, h = max(1, round(logo.width * s)), max(1, round(logo.height * s))
        # resampled premultiplied, so transparent texels' colour does not fringe the edges
        pre = np.asarray(logo.convert("RGBa").resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
        x0, y0 = (W - w) // 2, (H - h) // 2
        rgb_p[y0:y0 + h, x0:x0 + w] = np.clip(pre[..., :3], 0.0, 1.0)
        alpha[y0:y0 + h, x0:x0 + w] = np.clip(pre[..., 3], 0.0, 1.0)
    else:
        paths = [marks / spec.data["marks"][layer["mark"]] for layer in cl["layers"]]
        with Image.open(paths[0]) as first:
            canvas_size = first.size
            frame = first.convert("RGBA").getchannel("A").getbbox()
        fw, fh = frame[2] - frame[0], frame[3] - frame[1]
        fit = min(width, width * fw / fh)                   # the frame's width once fitted both ways
        for layer, path in zip(cl["layers"], paths):
            with Image.open(path) as image:
                if image.size != canvas_size:
                    raise SystemExit(f"center_logo layer {layer['mark']}: canvas {image.size}, first layer {canvas_size}")
            cov = framed_mark_coverage(path, frame, shape, (W / 2, H / 2), fit)
            colour = spec.colour(layer["colour"])
            rgb_p = rgb_p * (1 - cov[..., None]) + colour[None, None, :] * cov[..., None]
            alpha = alpha * (1 - cov) + cov
    if cl.get("keyline"):
        kl = cl["keyline"]
        ring = np.clip(float(kl["width"]) * MASTER - ndimage.distance_transform_edt(alpha < 0.5) + 0.5, 0.0, 1.0)
        # the ring goes under the logo: the logo over (ring colour, ring coverage)
        rgb_p = rgb_p + spec.colour(kl["colour"])[None, None, :] * (ring * (1 - alpha))[..., None]
        alpha = alpha + ring * (1 - alpha)
    straight = rgb_p / np.maximum(alpha[..., None], 1e-4)
    solid = alpha > 0.5
    if solid.any():
        # straight alpha: the colour under (nearly) transparent texels is the nearest solid texel's
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        straight = np.where((alpha > 0.02)[..., None], straight, straight[iy, ix])
    out = np.zeros((H, W, 4), dtype=np.float32)
    out[..., :3] = np.clip(straight, 0.0, 1.0)
    out[..., 3] = alpha * float(cl.get("alpha", 0.95))
    return out


def author_center_logo(spec: Spec, venue: dict, marks: Path) -> np.ndarray:
    """The midfield logo, a transparent 256 x 256 overlay: ``outline_mark`` and ``fill_mark`` (one colour each), or
    in several colours with ``mark`` or ``layers`` (see _center_logo_colour)."""
    cl = venue["center_logo"]
    H = W = 256 * MASTER
    shape = (H, W)
    out = np.zeros((H, W, 4), dtype=np.float32)
    width = cl.get("width_frac", 0.88) * W
    if cl.get("mark") or cl.get("layers"):
        return _center_logo_colour(spec, cl, marks, shape, width)
    # outline and fill are layers of one logo: place both in the outline's frame (same canvas) so they register,
    # instead of fitting each to the width on its own (which grew the fill over the outline)
    frame = None
    if cl.get("outline_mark") and cl.get("fill_mark"):
        with Image.open(marks / spec.data["marks"][cl["outline_mark"]]) as a, \
                Image.open(marks / spec.data["marks"][cl["fill_mark"]]) as b:
            if a.size == b.size:
                frame = a.convert("RGBA").getchannel("A").getbbox()
    for key, colour_key in (("outline_mark", "outline"), ("fill_mark", "fill")):
        if cl.get(key):
            path = marks / spec.data["marks"][cl[key]]
            if frame is not None:
                cov = framed_mark_coverage(path, frame, shape, (W / 2, H / 2), width) * cl.get("alpha", 0.95)
            else:
                cov = mark_coverage(path, shape, (W / 2, H / 2), width) * cl.get("alpha", 0.95)
            out[..., :3] = out[..., :3] * (1 - cov[..., None]) + spec.colour(cl[colour_key])[None, None, :] * cov[..., None]
            out[..., 3] = np.maximum(out[..., 3], cov)
    # straight alpha with meaningful colour under soft edges: extend the outline colour into the transparent area
    first = spec.colour(cl["outline"] if cl.get("outline_mark") else cl["fill"])
    empty = out[..., 3] <= 1e-4
    out[empty, :3] = first
    return out


def _banner_folds(ref: np.ndarray, slot) -> np.ndarray:
    """Cloth fold shading of one retail banner (its text inpainted away), as a brightness ratio."""
    x0, y0, x1, y1 = slot
    sub = ref[y0:y1, x0:x1]
    inside = sub[..., 3] > 0.5
    base = np.median(sub[..., :3][inside], axis=0)
    dev = np.abs(sub[..., :3] - base).sum(axis=2)
    from scipy import ndimage
    # the old letters and their anti-aliased edges are masked generously (grey blotches came from edge pixels
    # the tighter mask kept), then the cloth shading is the heavy-blurred luminance of what is left
    keep = (inside & ~ndimage.binary_dilation(dev > 0.12, iterations=2)).astype(np.float32)
    luma = sub[..., :3].mean(axis=2)
    smooth = ndimage.gaussian_filter(luma * keep, 5.0) / np.maximum(ndimage.gaussian_filter(keep, 5.0), 1e-3)
    ratio = np.clip(smooth / max(float(np.median(smooth[inside])), 1e-3), 0.9, 1.06)
    ratio[~inside] = 1.0
    return ratio


def author_banner_sheet(spec: Spec, sheet: dict, retail_png: Path, marks: Path) -> np.ndarray:
    ref = load(retail_png)
    h, w = ref.shape[:2]
    H, W = h * MASTER, w * MASTER
    shape = (H, W)
    out = np.zeros((H, W, 4), dtype=np.float32)
    folds = np.ones((h, w), dtype=np.float32)
    for banner in sheet["banners"]:
        x0, y0, x1, y1 = banner["slot"]
        # ``"folds": false`` (on the sheet or one banner): a flat surface such as a wall or a board, so no cloth
        # shading is carried over from the retail art (job d3: wall05 kept the old logos' fold shading)
        cloth = bool(banner.get("folds", sheet.get("folds", True)))
        f = _banner_folds(ref, banner["slot"]) if cloth else np.ones((y1 - y0, x1 - x0), np.float32)
        if cloth and float(spec.colour(banner["bg"]).mean()) > 0.8:
            f = 1.0 - (1.0 - f) * 0.45          # light cloth shows folds faintly (as the pants' fabric rule)
        folds[y0:y1, x0:x1] = f
        box = _box(shape, banner["slot"])
        out[..., :3] = out[..., :3] * (1 - box[..., None]) + spec.colour(banner["bg"])[None, None, :] * box[..., None]
        for item in banner["items"]:
            c = (item["center"][0] * MASTER, item["center"][1] * MASTER)
            if "mark" in item:
                cov = mark_coverage(marks / spec.data["marks"][item["mark"]], shape, c, item["width"] * MASTER)
            else:
                cov = text_coverage(shape, item["text"], c, item["height"] * MASTER,
                                    item.get("max_width", x1 - x0 - 12) * MASTER, lines=item["text"].count("\n") + 1)
            over(out, spec.colour(item["colour"]), cov * box)
    fold_up = np.asarray(Image.fromarray(folds).resize((W, H), Image.BICUBIC), dtype=np.float32)
    out[..., :3] = np.clip(out[..., :3] * fold_up[..., None], 0.0, 1.0)
    out[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize((W, H), Image.BICUBIC), dtype=np.float32).clip(0, 1)
    return out


def author_cutout_sheet(spec: Spec, sheet: dict, retail_png: Path, marks: Path) -> np.ndarray:
    """A cut-out target (letters or logos cut to their own alpha shape, ``"alpha": "items"``): the texture's alpha is
    the union of the items drawn in the slots, not the retail alpha, and there is no cloth backdrop. Colour under
    transparent pixels is the nearest item's colour, so filtering at the edges does not fringe."""
    from scipy import ndimage
    ref = load(retail_png)
    h, w = ref.shape[:2]
    H, W = h * MASTER, w * MASTER
    shape = (H, W)
    rgb = np.zeros((H, W, 3), dtype=np.float32)
    alpha = np.zeros((H, W), dtype=np.float32)
    for banner in sheet["banners"]:
        box = _box(shape, banner["slot"])
        x0, y0, x1, y1 = banner["slot"]
        for item in banner["items"]:
            c = (item["center"][0] * MASTER, item["center"][1] * MASTER)
            if "mark" in item:
                cov = mark_coverage(marks / spec.data["marks"][item["mark"]], shape, c, item["width"] * MASTER)
            else:
                cov = text_coverage(shape, item["text"], c, item["height"] * MASTER,
                                    item.get("max_width", x1 - x0 - 12) * MASTER, lines=item["text"].count("\n") + 1)
            cov = np.clip(cov * box, 0.0, 1.0)
            colour = spec.colour(item["colour"])
            rgb = rgb * (1 - cov[..., None]) + colour[None, None, :] * cov[..., None]
            alpha = alpha * (1 - cov) + cov
    solid = alpha > 0.5
    if solid.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        fill = rgb[iy, ix]
        rgb = np.where(alpha[..., None] > 1e-3, rgb / np.maximum(alpha[..., None], 1e-3), fill)
        rgb = np.where(solid[..., None], rgb, fill)
    out = np.zeros((H, W, 4), dtype=np.float32)
    out[..., :3] = np.clip(rgb, 0.0, 1.0)
    out[..., 3] = alpha
    return out


def cmd_venue(args) -> int:
    spec = Spec(Path(args.spec))
    venue = spec.data["venue"]
    marks, out, retail = Path(args.marks), Path(args.out), Path(args.retail_venue)
    items = []

    def emit(scene: str, material: str, master: np.ndarray, layer: str, bleed: bool = False):
        native = downscale(master)
        if bleed:
            # a cut-out: colour under transparent texels is the nearest opaque texel's, so filtering does not fringe
            from scipy import ndimage
            solid = native[..., 3] > 0.5
            if solid.any():
                _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
                clear = native[..., 3] <= 1e-3
                native[..., :3] = np.where(clear[..., None], native[iy, ix, :3], native[..., :3])
        m = out / "master4x" / scene / f"{material}.png"
        n = out / "retail" / scene / f"{material}.png"
        items.append({"scene": scene, "material": material, "size": [native.shape[1], native.shape[0]],
                      "file": str(n.relative_to(out)), "master": str(m.relative_to(out)), "layer": layer,
                      "sha256": save(native, n), "master_sha256": save(master, m)})
        print(f"  {scene}/{material} {native.shape[1]}x{native.shape[0]} ({layer})")

    strip = author_endzone_strip(spec, venue, marks)
    for i, part in enumerate(("L", "M", "R")):
        emit("field", f"endzone_N_{part}", strip[:, i * 256 * MASTER:(i + 1) * 256 * MASTER].copy(), "overlay")
    if venue.get("endzone_south"):
        # the eleven venues whose south end zone has its own textures (different words at the two ends)
        strip = author_endzone_strip(spec, venue, marks, "endzone_south")
        for i, part in enumerate(("L", "M", "R")):
            emit("field", f"endzone_S_{part}", strip[:, i * 256 * MASTER:(i + 1) * 256 * MASTER].copy(), "overlay")
    emit("field", "center_logo", author_center_logo(spec, venue, marks), "overlay")
    prefix = venue["prefix"]
    for material, sheet in venue["banners"].items():
        src = next(retail.glob(f"{prefix}dd_stadium_t*_{material}.png"))
        if sheet.get("alpha") == "items":
            emit("stadium", material, author_cutout_sheet(spec, sheet, src, marks), "full", bleed=True)
        else:
            emit("stadium", material, author_banner_sheet(spec, sheet, src, marks), "full")
    paint = {"endzone": venue["endzone"]["paint"]}
    if venue.get("endzone_south"):
        paint["endzone_south"] = venue["endzone_south"]["paint"]
    manifest = {"schema": "metlife_team_art/v1", "team": spec.data["team"], "venue_prefix": prefix,
                "colours": spec.data["palette"], "paint": paint,
                "sources": sorted(set(spec.data["sources"].values()) | set(venue.get("sources", []))),
                "notes": venue.get("notes", ""), "items": items}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"venue art: {len(items)} items into {out}")
    return 0


BODY_MUD_GAIN = 0.93  # W1: jersey, sleeve and pants mud twins (retail white jersey 0.936); equipment keeps 0.6


def darken_mud(path: Path, out: Path, gain: float = 0.6) -> str:
    """The retail ``darken_60`` rule for an equipment mud twin: 60 percent brightness, alpha kept. Body textures
    (jersey, sleeve, pants) pass BODY_MUD_GAIN: their mud twins are only loaded in rain and snow."""
    rgba = load(path)
    rgba[..., :3] *= gain
    return save(rgba, out)


def cmd_project(args) -> int:
    """A ``nfl2k5_visual_mod_project/v1`` document for the Studio's unified writer, from authored art manifests."""
    spec = Spec(Path(args.spec))
    code = spec.data["asset_code"]
    art = Path(args.art).resolve()
    manifest = json.loads((art / "manifest.json").read_text(encoding="utf-8"))
    edits = []
    for item in manifest["items"]:
        selector = item["set"]
        side_code = selector[len(code)]
        variant = int(selector[len(code) + 1:])
        png = str(art / item["retail"])
        kind = item["kind"]
        if kind in ("torso", "sleeve", "pants"):
            edits.append({"kind": kind, "asset_code": code, "side": side_code, "variant": variant,
                          "clean_png": png, "mud_png": None, "mud_mode": "wet_93"})  # W1: body mud twins are 0.93, not 0.6
        elif kind == "live_helmet":
            edits.append({"kind": kind, "asset_code": code, "side": side_code, "variant": variant,
                          "family": item["family"], "png": png})
        elif kind == "live_number_nameplate":
            edits.append({"kind": kind, "asset_code": code, "side": side_code, "variant": variant,
                          "family": item["family"], "digit": item["digit"], "png": png})
        elif kind == "team_select":
            edits.append({"kind": kind, "asset_code": code, "side": "home" if side_code == "H" else "away",
                          "style": variant, "family": item["family"], "resolution": item["resolution"], "png": png})
        elif kind == "uniform_equipment_texture":
            edits.append({"kind": kind, "asset_id": item["asset_id"], "png": png})
            if item.get("mud") is False:
                continue                     # gloves and wristbands have no mud twin (job u7)
            # the mud twin sits at the next index of the same TSET: tset:<outer>:4:0:socks00 -> ...:4:1:socks00_mud
            parts = item["asset_id"].split(":")
            mud_id = ":".join(parts[:3] + [str(int(parts[3]) + 1), parts[4] + "_mud"])
            mud_png = art / "retail" / selector / (Path(item["retail"]).stem + "_mud.png")
            darken_mud(Path(png), mud_png)
            edits.append({"kind": kind, "asset_id": mud_id, "png": str(mud_png)})
        elif kind == "p8_texture":
            edits.append({"kind": kind, "asset_id": item["asset_id"], "png": png})
    for faces in args.faces or ():
        fm = json.loads(Path(faces).read_text(encoding="utf-8"))
        base = Path(faces).resolve().parent
        for item in fm["items"]:
            png = str((base / item["retail"]).resolve())
            if item["kind"] == "live_face":
                edits.append({"kind": "live_face", "face_id": item["face_id"], "family": item["family"], "png": png})
            elif item["kind"] == "player_portrait":
                edits.append({"kind": "player_portrait", "portrait_id": item["portrait_id"], "png": png})
    for kit in spec.data["kits"].values():
        # ``unif_color`` {"facemask", "turtleneck" (optional: null keeps the retail word)}: the set's packed colour
        # words (facemask and faceshield, turtleneck); colours as #RRGGBB or AARRGGBB (job d7)
        uc = kit.get("unif_color")
        if uc:
            edits.append({"kind": "unif_color", "selector": kit["selector"], "facemask": uc["facemask"],
                          "turtleneck": uc.get("turtleneck")})
    project = {"edits": edits, "purpose": f"{spec.data['name']} {spec.data['season']} look (job u1 pilot)",
               "schema": "nfl2k5_visual_mod_project/v1"}
    out = Path(args.out)
    out.write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"project: {len(edits)} edits -> {out}")
    return 0


# --------------------------------------------------------------------------------------------- retail export
def cmd_export(args) -> int:
    """Export every uniform set of the given asset codes, plus the equipment TSETs and P8 textures of those sets'
    packages, from the user's own disc through the Studio's verified source cache. The output is the ``--retail`` and
    ``--equipment`` input of ``author``; it holds retail bytes, so it must stay outside the repository."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from mod_editor.core.nfl2k5_asset_io import Nfl2k5AssetIO
    from mod_editor.core.nfl2k5_extended_visual_catalog import load_nfl2k5_extended_visual_catalog
    from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO
    from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache
    from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog

    out = Path(args.out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit("export writes retail textures: choose a folder outside the repository")
    cache = Nfl2k5SourceCache().index(Path(args.source_xiso))
    ucat = load_nfl2k5_uniform_catalog()
    uio = Nfl2k5AssetIO(cache)
    sets = []
    for code in (c.strip() for c in args.codes.split(",") if c.strip()):
        for side in ("H", "A"):
            for variant in range(10):
                try:
                    sets.append(ucat.uniform_set_for(code, side, variant))
                except Exception:  # noqa: BLE001 - the catalog raises for a set the team does not have
                    continue
    rows, failures = [], []
    for us in sets:
        for a in ucat.assets_for_set(us.selector):
            dest = out / "uniforms" / us.selector / (a.asset_id.split(".", 3)[-1].replace(".", "_") + ".png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not dest.exists():
                    uio.export_original(a, dest)
            except Exception as exc:  # noqa: BLE001 - record and continue; author fails loudly on a missing input
                failures.append(f"{a.asset_id}: {type(exc).__name__}: {exc}")
                continue
            rows.append({"asset_id": a.asset_id, "set": us.selector, "kind": a.kind, "size": [a.width, a.height],
                         "png": str(dest.relative_to(out))})
    ecat = load_nfl2k5_extended_visual_catalog()
    eio = Nfl2k5ExtendedVisualIO(cache)
    selectors = {us.selector for us in sets}
    outers = {}
    equipment = list(ecat.assets_for_kind("uniform_equipment_texture"))
    for a in equipment:
        if a.search_terms and a.search_terms[0] in selectors and a.equipment_descriptor is not None:
            outers[a.search_terms[0]] = a.equipment_descriptor.outer_index
    wanted = {str(v) for v in outers.values()}
    for a in equipment + list(ecat.assets_for_kind("p8_texture")):
        if a.asset_id.split(":")[1] not in wanted:
            continue
        dest = out / "equipment" / (a.asset_id.replace(":", "_") + ".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not dest.exists():
                eio.export_original(a, dest)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{a.asset_id}: {type(exc).__name__}: {exc}")
            continue
        rows.append({"asset_id": a.asset_id, "kind": a.kind, "size": [a.width, a.height],
                     "png": str(dest.relative_to(out))})
    doc = {"source": str(Path(args.source_xiso)), "codes": args.codes, "set_outers": dict(sorted(outers.items())),
           "items": rows, "failures": failures}
    (out / "export.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"export: {len(sets)} uniform sets, {len(rows)} textures, {len(failures)} failures -> {out}")
    print("set packages (outer index): " + ", ".join(f"{k}={v}" for k, v in sorted(outers.items())))
    return 1 if failures else 0


# --------------------------------------------------------------------------------------------- texture pack
# The 2K5 Edition's packs (job x2) key a texture by its bytes on the disc that is played, so a pack manifest names
# its targets (texture name + archive file) and x2's ``nfl2k5_texture_pack.py build`` resolves them against the
# catalog of that disc. Names repeat across the 634 uniform files, so every target carries its file.
PACK_TSET = {"torso": "jersey00", "pants": "pants00", "sleeve": "sleeve00", "socks00": "socks00"}
PACK_DIGIT_PREFIX = {"jersey": "", "helmet": "hn", "arm": "an"}
PACK_NOT_PACKABLE = {
    "nameplate": "the name letters are a VC_P8_LINEAR (0x7F) strip that the CPU compositor 0x001C2140 reads to draw "
                 "each player's name into a generated texture; the strip is never uploaded, so a pack cannot key it "
                 "(native only)",
}


def _read_catalog(path: Path) -> list[dict]:
    import csv
    with path.open(encoding="utf-8") as stream:
        lines = [line for line in stream if not line.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def cmd_pack(args) -> int:
    """A texture-pack manifest for x2's pack builder: the authored 4x masters (and 4x mud twins, darkened like the
    native writer's ``darken_60``) mapped to catalog names in their archive files."""
    import os
    catalog = _read_catalog(Path(args.catalog))
    by_name: dict[str, list[dict]] = {}
    for row in catalog:
        by_name.setdefault(row["name"], []).append(row)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    entries, skipped, problems = [], [], []

    def target(name: str, file: str | None = None, size: tuple[int, int] | None = None) -> dict | None:
        rows = by_name.get(name, [])
        if file:
            rows = [r for r in rows if r["file"].casefold() == file.casefold()]
        if size:
            rows = [r for r in rows if (int(r["width"]), int(r["height"])) == size]
        files = sorted({r["file"] for r in rows})
        if len(files) != 1:
            problems.append(f"{name} {file or ''} {size or ''}: {len(files)} archive files in the catalog")
            return None
        return {"name": name, "file": files[0]}

    def add(image: Path, tgt: dict | None, group: str, label: str) -> None:
        if tgt is not None:
            entries.append({"image": os.path.relpath(image, out), "target": tgt, "group": group, "label": label})

    for manifest_path in args.art or ():
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        base = Path(manifest_path).resolve().parent
        for item in manifest["items"]:
            sel, name, kind = item["set"], item["name"], item["kind"]
            master = base / item["master"]
            file = f"{sel}.IFF"
            label = f"{sel} {name}"
            if name in PACK_NOT_PACKABLE:
                skipped.append({"texture": label, "why": PACK_NOT_PACKABLE[name]})
            elif kind in ("torso", "pants", "sleeve") or name == "socks00":
                texture = PACK_TSET[name if name == "socks00" else kind]
                clean = [n for n in by_name if n.endswith(f"/{texture}") and n.startswith(f"uniform {file} ")]
                if len(clean) != 1:
                    problems.append(f"{label}: {len(clean)} catalog names end in /{texture} in {file}")
                    continue
                add(master, target(clean[0], file), "uniforms", label)
                mud = out / "mud" / sel / f"{name}_mud.png"
                darken_mud(master, mud, BODY_MUD_GAIN if kind in ("torso", "pants", "sleeve") else 0.6)
                add(mud, target(clean[0] + "_mud", file), "uniforms", label + " (mud)")
            elif kind == "live_helmet":
                add(master, target(item["family"], file), "uniforms", label)
            elif kind == "live_number_nameplate":
                glyph = f"{PACK_DIGIT_PREFIX[item['family']]}{48 + int(item['digit'])}"
                add(master, target(glyph, file), "uniforms", label)
            elif kind == "p8_texture":
                add(master, target(item["asset_id"].split(":")[2], file), "uniforms", label)
            elif kind == "team_select":
                code, side = sel[:-2], sel[-2].lower()
                size = (item["resolution"], item["resolution"])
                add(master, target(f"{item['family']}_{side}{code}_{int(sel[-1])}", None, size), "team_select", label)
            else:
                skipped.append({"texture": label, "why": f"no pack rule for kind {kind}"})
    for manifest_path in args.faces or ():
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        base = Path(manifest_path).resolve().parent
        for item in manifest["items"]:
            master = base / item["master"]
            if item["kind"] == "live_face":
                add(master, target(f"{item['family']}{item['face_id']}"), "faces", f"{item['player']} {item['family']}")
            elif item["kind"] == "player_portrait":
                add(master, target(item["portrait_id"], None, (128, 128)), "portraits", f"{item['player']} portrait")
    doc = {"name": args.name, "priority": args.priority,
           "description": "4x masters of the native 2026 art (job u1 recipe); keys resolve against the played disc",
           "entries": entries}
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "not_packed.json").write_text(json.dumps({"skipped": skipped, "problems": problems}, indent=1) + "\n",
                                         encoding="utf-8", newline="\n")
    print(f"pack manifest: {len(entries)} entries, {len(skipped)} not packable, {len(problems)} problems -> {out}")
    for p in problems:
        print("  PROBLEM " + p)
    return 1 if problems else 0


def dominant_colours(path: Path, k: int = 4) -> list[dict]:
    """The k most common colours of a texture (alpha > 0.5 pixels), as hex with their share: deterministic
    k-means on RGB, seeded by quantised histogram peaks."""
    rgba = load(path)
    px = rgba[..., :3][rgba[..., 3] > 0.5].reshape(-1, 3)
    if len(px) == 0:
        return []
    q = np.round(px * 15).astype(int)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    order = np.argsort(-counts)[:k]
    centers = np.stack([(keys[order] // 256) / 15.0, ((keys[order] // 16) % 16) / 15.0, (keys[order] % 16) / 15.0], axis=1)
    for _ in range(8):
        d = ((px[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        label = d.argmin(axis=1)
        centers = np.stack([px[label == i].mean(axis=0) if (label == i).any() else centers[i] for i in range(len(centers))])
    share = np.bincount(label, minlength=len(centers)) / len(px)
    rows = [{"hex": "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in c), "share": round(float(sh), 3)}
            for c, sh in zip(centers, share)]
    return sorted(rows, key=lambda r: -r["share"])


def cmd_colours(args) -> int:
    rows = []
    for manifest_path in args.manifest:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        base = Path(manifest_path).resolve().parent
        for item in manifest["items"]:
            rel = item.get("retail") or item.get("file")
            name = item.get("name") or item.get("material") or Path(rel).stem
            rows.append({"texture": f"{item.get('set') or item.get('scene') or ''}/{name}", "kind": item.get("kind", item.get("layer", "")),
                         "file": rel, "dominant": dominant_colours(base / rel)})
    Path(args.out).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"colours: {len(rows)} textures -> {args.out}")
    return 0


def cmd_layout(args) -> int:
    """Guide images of the shared layouts: a set's retail torso, sleeve, pants and helmet at 3x with every LAYOUT
    place boxed and named, plus layout.json. The images hold retail pixels, so they go outside the repository."""
    retail, out = Path(args.retail) / args.set, Path(args.out)
    if ROOT in out.resolve().parents:
        raise SystemExit("the guide images hold retail pixels: choose a folder outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    files = {"torso": ["torso.png"], "sleeve": ["sleeve.png"], "pants": ["pants.png"],
             "helmet": ["helmet_helmet00.png", "helmet_helmet02.png"]}
    scale = 3
    for part, names in files.items():
        for name in names:
            with Image.open(retail / name) as image:
                im = image.convert("RGB")
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            draw = ImageDraw.Draw(im)
            for label, (x0, y0, x1, y1) in LAYOUT[part].items():
                draw.rectangle((x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1), outline=(255, 0, 255), width=2)
                draw.text((x0 * scale + 3, y0 * scale + 2), label, fill=(255, 0, 255))
            im.save(out / f"layout_{args.set}_{Path(name).stem}.png")
    doc = {"units": "retail pixels (x0, y0, x1, y1); decorations use {\"at\": name, \"offset\": [dx, dy]}",
           "places": {part: {k: list(v) for k, v in places.items()} for part, places in LAYOUT.items()}}
    (out / "layout.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"layout guide for {args.set}: {sum(len(v) for v in files.values())} images -> {out}")
    return 0


def _edit_target(edit: dict) -> tuple:
    """What a project edit writes, for the merge's no-overlap check."""
    kind = edit["kind"]
    if "asset_id" in edit:
        return (kind, edit["asset_id"])
    if "selector" in edit:
        return (kind, str(edit["selector"]).upper())   # unif_color and other edits addressed by a set selector
    if kind == "live_face":
        return (kind, edit["face_id"], edit["family"])
    if kind == "player_portrait":
        return (kind, edit["portrait_id"])
    return (kind, edit.get("asset_code"), edit.get("side"), edit.get("variant", edit.get("style")), edit.get("family"),
            edit.get("digit"), edit.get("resolution"))


def cmd_merge_projects(args) -> int:
    """One visual project for the league build from the per-team projects, refusing two edits of one target (two
    teams given the same face slot, or one set authored twice)."""
    edits, seen, clashes = [], {}, []
    for path in args.project:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        for edit in doc["edits"]:
            key = _edit_target(edit)
            if key in seen:
                clashes.append(f"{key} in {seen[key]} and {path}")
                continue
            seen[key] = path
            edits.append(edit)
    if clashes:
        print("\n".join("  CLASH " + c for c in clashes[:40]))
        raise SystemExit(f"{len(clashes)} targets are written by more than one project")
    project = {"edits": edits, "purpose": args.purpose, "schema": "nfl2k5_visual_mod_project/v1"}
    Path(args.out).write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"merged project: {len(edits)} edits from {len(args.project)} projects -> {args.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    ly = sub.add_parser("layout")
    ly.add_argument("--retail", required=True, help="exported retail uniform set folders (<set>/<name>.png)")
    ly.add_argument("--set", default="18A6", help="the set to draw the places on (18A6 has sleeve stripes)")
    ly.add_argument("--out", required=True)
    mp = sub.add_parser("merge-projects")
    mp.add_argument("--project", action="append", required=True)
    mp.add_argument("--purpose", default="2026 teams (job u1 recipe)")
    mp.add_argument("--out", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--source-xiso", required=True, help="the user's own retail disc")
    ex.add_argument("--codes", required=True, help="comma-separated asset codes, e.g. 18")
    ex.add_argument("--out", required=True, help="a folder outside the repository")
    pk = sub.add_parser("pack")
    pk.add_argument("--catalog", required=True, help="x2 texture catalog of any build (the names are stable)")
    pk.add_argument("--art", action="append", help="authored art manifest(s)")
    pk.add_argument("--faces", action="append", help="faces manifest(s)")
    pk.add_argument("--name", required=True)
    pk.add_argument("--priority", type=int, default=0)
    pk.add_argument("--out", required=True)
    co = sub.add_parser("colours")
    co.add_argument("--manifest", action="append", required=True)
    co.add_argument("--out", required=True)
    pj = sub.add_parser("project")
    pj.add_argument("--spec", required=True)
    pj.add_argument("--art", required=True)
    pj.add_argument("--faces", action="append", help="faces manifest(s) (live_face and player_portrait items)")
    pj.add_argument("--out", required=True)
    v = sub.add_parser("venue")
    v.add_argument("--spec", required=True)
    v.add_argument("--marks", required=True)
    v.add_argument("--retail-venue", required=True, help="exported retail stadium textures (<prefix>dd_<scene>_t<i>_..._<material>.png)")
    v.add_argument("--out", required=True)
    a = sub.add_parser("author")
    a.add_argument("--spec", required=True)
    a.add_argument("--retail", required=True, help="exported retail uniform set folders (<set>/<name>.png)")
    a.add_argument("--marks", required=True, help="folder of high-resolution mark masks named in the spec")
    a.add_argument("--uniform-marks", help="nfl2k5_uniform_marks/v1 manifest of the official NFL shield and swoosh "
                                           "masters (pinned; needed by collar_shield, sleeve_swooshes, the pants "
                                           "swoosh and @ marks)")
    a.add_argument("--equipment", help="exported equipment PNGs (tset_<outer>_<chunk>_<index>_<name>.png)")
    a.add_argument("--helmet-geometry", help="the head export JSON (HI_HELMET_C: pos, uv, tris) for helmet.side_logo recipes")
    a.add_argument("--outer-home", type=int, default=0)
    a.add_argument("--outer-away", type=int, default=0)
    a.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.command == "author":
        return cmd_author(args)
    if args.command == "venue":
        return cmd_venue(args)
    if args.command == "project":
        return cmd_project(args)
    if args.command == "colours":
        return cmd_colours(args)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "pack":
        return cmd_pack(args)
    if args.command == "merge-projects":
        return cmd_merge_projects(args)
    if args.command == "layout":
        return cmd_layout(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
