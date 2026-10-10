#!/usr/bin/env python3
"""Beta 77 u3c: painted textures for the alternates that are a new design (the Rivalries sets), used by
``tools/b77/u3s_alternates.py author`` through a recipe's ``"paint"`` key.

``paint(name, stem, rgba, ctx)`` gets the texture the recipe's donor and colour rules produced (RGBA float 0..1,
native size) and returns the finished texture (or the same array when the set paints nothing on it). ``ctx`` holds the
kit selector ("12H6"), the side and the export folder. Every look below is described in its set's recipe sources
(``data/nfl2k5_uniform_alternates_2026.json``); sizes are native texture pixels of the shared player-model UV layout
(front collar V tip (161, 70), back neck (366..415, 0..43), pants stripe bands x 130..155 and 357..382).

Fonts come from the machine (Georgia, Z003 script); nothing retail is copied.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SS = 4                                        # supersampling for painted shapes

FONTS = {
    "serif_bold": ("/usr/share/fonts/truetype/msttcorefonts/Georgia_Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    "script": ("/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
               "/usr/share/fonts/truetype/freefont/FreeSerifBoldItalic.ttf"),
    "sans_bold": ("/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS[kind]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit(f"no font for {kind}")


def hexf(text: str) -> np.ndarray:
    text = text.lstrip("#")
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def over(dst: np.ndarray, colour: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Composite a solid colour with coverage ``cov`` (H x W, 0..1) over an RGBA float texture."""
    out = dst.copy()
    a = np.clip(cov, 0, 1)[..., None]
    out[..., :3] = dst[..., :3] * (1 - a) + colour[None, None, :3] * a
    out[..., 3] = np.maximum(dst[..., 3], np.clip(cov, 0, 1))
    return out


def box_down(arr: np.ndarray, factor: int) -> np.ndarray:
    h, w = arr.shape[:2]
    return arr.reshape(h // factor, factor, w // factor, factor, *arr.shape[2:]).mean(axis=(1, 3))


def text_cov(shape: tuple[int, int], text: str, kind: str, centre: tuple[float, float], height: float,
             slant: float = 0.0, tracking: float = 0.0) -> np.ndarray:
    """Coverage of ``text`` whose ink is ``height`` px tall, centred at ``centre`` (native px), supersampled.
    ``slant`` shears the ink to the right (fraction of height)."""
    h, w = shape
    f = font(kind, 400)
    probe = Image.new("L", (4000, 800), 0)
    d = ImageDraw.Draw(probe)
    d.text((100, 100), text, font=f, fill=255)
    arr = np.asarray(probe)
    ys, xs = np.nonzero(arr > 127)
    ink = Image.fromarray(arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    scale = height * SS / ink.height
    ink = ink.resize((max(1, int(round(ink.width * scale))), max(1, int(round(ink.height * scale)))), Image.LANCZOS)
    canvas = Image.new("L", (w * SS, h * SS), 0)
    x0 = int(round(centre[0] * SS - ink.width / 2))
    y0 = int(round(centre[1] * SS - ink.height / 2))
    canvas.paste(ink, (x0, y0))
    if slant:
        canvas = canvas.transform(canvas.size, Image.AFFINE, (1, slant, -slant * (y0 + ink.height / 2), 0, 1, 0),
                                  Image.BICUBIC)
    return box_down(np.asarray(canvas, np.float32) / 255.0, SS)


def dilate(cov: np.ndarray, radius: float) -> np.ndarray:
    from scipy import ndimage
    if radius <= 0:
        return cov
    r = int(np.ceil(radius))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    footprint = (yy * yy + xx * xx) <= radius * radius
    return ndimage.grey_dilation(cov, footprint=footprint)


def shift(cov: np.ndarray, dx: float, dy: float) -> np.ndarray:
    from scipy import ndimage
    return ndimage.shift(cov, (dy, dx), order=1, mode="constant")


def rect(shape: tuple[int, int], x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Anti-aliased axis-aligned rectangle coverage (native px, fractional edges allowed)."""
    h, w = shape
    xs = np.clip(np.minimum(np.arange(w) + 1, x1) - np.maximum(np.arange(w), x0), 0, 1)
    ys = np.clip(np.minimum(np.arange(h) + 1, y1) - np.maximum(np.arange(h), y0), 0, 1)
    return (ys[:, None] * xs[None, :]).astype(np.float32)


def leopard(shape: tuple[int, int], seed: int, scale: float = 9.0) -> np.ndarray:
    """A soft rosette field 0..1 (blotches ringed by a darker edge), for a printed-leopard pants fabric."""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    h, w = shape
    n = ndimage.gaussian_filter(rng.random((h, w)).astype(np.float32), scale * 0.45)
    n = (n - n.min()) / (n.max() - n.min() + 1e-6)
    ring = np.abs(n - 0.55)
    return np.clip(1.0 - ring * 7.0, 0.0, 1.0)


# ------------------------------------------------------------------------------------------------ Bold City

BC_CREAM = "#EDE6D0"
BC_TEAL = "#037C8C"
BC_GOLD = "#B59A55"
BC_BLACK = "#141414"
BC_SHELL_TEAL = "#139AAD"


def bold_city(stem: str, rgba: np.ndarray, ctx: dict) -> np.ndarray:
    cream, teal, gold, black = hexf(BC_CREAM), hexf(BC_TEAL), hexf(BC_GOLD), hexf(BC_BLACK)
    h, w = rgba.shape[:2]
    if stem == "torso":
        out = rgba.copy()
        # chest script (jaguars.com Rivalries gallery photo 06/08: black script with a gold edge, under the collar)
        script = text_cov((h, w), "Jaguars", "script", (161, 104), 17.0)
        edge = dilate(script, 1.0)
        out = over(out, gold, edge)
        out = over(out, black, script)
        # the back neckline carries "Bold City" in the same script (jaguars.com, ESPN Aug 25)
        tag = text_cov((h, w), "Bold City", "script", (390.5, 52), 9.0)
        out = over(out, black, tag)
        return out
    if stem == "pants":
        out = rgba.copy()
        luma = rgba[..., :3].mean(axis=2)
        white = np.clip((luma - 0.80) / 0.15, 0.0, 1.0)[..., None]          # the donor's white fabric, not its dashes
        fabric = hexf(BC_BLACK)[None, None, :] * 0.62
        rosette = leopard((h, w), 7)[..., None]
        fabric = fabric * (1 - 0.35 * rosette) + hexf("#2A2A30")[None, None, :] * 0.35 * rosette
        out[..., :3] = rgba[..., :3] * (1 - white) + fabric * white
        for x0 in (130, 357):
            out = over(out, teal, rect((h, w), x0 + 3, 14, x0 + 22, 238))
            for gx in (x0, x0 + 22):
                out = over(out, gold, rect((h, w), gx, 14, gx + 3, 238))
        return out
    if stem in ("helmet_helmet02", "helmet_helmet00"):
        out = shell_teal(rgba, np.s_[:, :186])
        if stem == "helmet_helmet02":                                          # the front bumper plate reads 904 (jaguars.com)
            plate = rect((h, w), 190, 60, 255, 107)
            out = over(out, hexf("#F2F2EE"), plate)
            out = over(out, hexf(BC_BLACK), text_cov((h, w), "904", "sans_bold", (222.5, 83.5), 21.0))
        return out
    if stem == "splayer":
        out = rgba.copy()
        x0, y0, x1, y1 = 128, 0, 256, 100                                    # torso box (art.SPLAYER)
        out[y0:y1, x0:x1, :3] = out[y0:y1, x0:x1, :3] * cream[None, None, :]
        px0, py0, px1, py1 = 0, 0, 128, 90                                    # pants box
        seg = out[py0:py1, px0:px1, :3]
        luma = seg.mean(axis=2, keepdims=True)
        dark = np.clip((luma - 0.55) / 0.35, 0.0, 1.0)
        seg[:] = seg * (1 - dark) + (luma * 0.16 + 0.03) * dark
        out[py0:py1, px0:px1, :3] = seg
        out = over(out, teal, rect((h, w), 49, 0, 63, 90))
        out = over(out, gold, rect((h, w), 47, 0, 49, 90))
        out = over(out, gold, rect((h, w), 63, 0, 65, 90))
        hx0, hy0, hx1, hy1 = 37, 90, 128, 128                                 # helmet box
        out[hy0:hy1, hx0:hx1] = shell_teal(out[hy0:hy1, hx0:hx1], np.s_[:, :])
        return out
    if stem.startswith("digit_jersey_"):
        return numeral(stem[-1], rgba, gold, black, teal)
    return rgba


def shell_teal(rgba: np.ndarray, region) -> np.ndarray:
    """The black helmet shell becomes glossy teal; black that is part of a logo (within 3 px of a coloured texel) stays."""
    from scipy import ndimage
    out = rgba.copy()
    peak = rgba[..., :3].max(axis=2)
    dark = peak < 0.16
    coloured = ~dark
    near = ndimage.binary_dilation(coloured, structure=np.ones((3, 3), bool), iterations=3)
    shell = np.zeros(dark.shape, bool)
    shell[region] = True
    sel = (dark & ~near & shell).astype(np.float32)
    sel = ndimage.gaussian_filter(sel, 0.6)
    shade = np.clip(0.9 + (rgba[..., :3].mean(axis=2) / 0.16) * 0.1, 0.9, 1.0)[..., None]
    teal = hexf(BC_SHELL_TEAL)[None, None, :] * shade
    out[..., :3] = rgba[..., :3] * (1 - sel[..., None]) + teal * sel[..., None]
    return out


def numeral(char: str, donor: np.ndarray, gold, black, teal) -> np.ndarray:
    """A Bold City numeral: serif black fill, thin gold edge, teal drop shadow to the lower right (photo 06). The glyph
    box follows the donor's (tall, stretched by the game's 4:2 number UV)."""
    h, w = donor.shape[:2]
    ys, xs = np.nonzero(donor[..., 3] > 0.3)
    cx, cy = (xs.min() + xs.max() + 1) / 2.0, (ys.min() + ys.max() + 1) / 2.0
    box_h = float(ys.max() + 1 - ys.min())
    box_w = float(xs.max() + 1 - xs.min())
    fill_h = box_h - 8.0
    fill_w = min(box_w - 7.0, fill_h * 0.62)
    f = font("serif_bold", 500)
    probe = Image.new("L", (900, 900), 0)
    ImageDraw.Draw(probe).text((100, 50), char, font=f, fill=255)
    arr = np.asarray(probe)
    gy, gx = np.nonzero(arr > 127)
    ink = Image.fromarray(arr[gy.min():gy.max() + 1, gx.min():gx.max() + 1])
    fw = fill_w if char != "1" else fill_w * 0.7
    ink = ink.resize((max(1, int(round(fw * SS))), max(1, int(round(fill_h * SS)))), Image.LANCZOS)
    canvas = Image.new("L", (w * SS, h * SS), 0)
    canvas.paste(ink, (int(round((cx - 2.0) * SS - ink.width / 2)), int(round((cy - 2.5) * SS - ink.height / 2))))
    fill = np.asarray(canvas, np.float32) / 255.0                              # supersampled coverage
    big = fill
    ring = dilate(big, 1.6 * SS)
    shadow = dilate(shift(big, 3.0 * SS, 3.5 * SS), 1.6 * SS)
    out = np.zeros((h, w, 4), np.float32)
    parts = [(hexf(BC_TEAL), shadow), (gold, ring), (black, big)]
    acc = np.zeros((h * SS, w * SS, 4), np.float32)
    for colour, cov in parts:
        a = cov[..., None]
        acc[..., :3] = acc[..., :3] * (1 - a) + colour[None, None, :] * a
        acc[..., 3] = np.maximum(acc[..., 3], cov)
    # premultiplied box filter so the edge colours do not bleed
    pre = acc.copy()
    pre[..., :3] *= pre[..., 3:4]
    pre = box_down(pre, SS)
    out[..., 3] = pre[..., 3]
    out[..., :3] = np.where(pre[..., 3:4] > 1e-4, pre[..., :3] / np.maximum(pre[..., 3:4], 1e-4), 0.0)
    return out


PAINTERS = {"bold_city": bold_city}


# ------------------------------------------------------------------------------------------------ Dolphins Rivalries

MIA_DARK = "#181B24"
MIA_ORANGE = "#E8761E"
MIA_AQUA = "#3F9CC0"


def neck_ring(shape: tuple[int, int], width: float) -> np.ndarray:
    """Coverage of a ring ``width`` px wide around the front V and the back neck openings of the shared torso UV."""
    import nfl2k5_team_2026_art as art
    h, w = shape
    mask = np.zeros((h, w), np.float32)
    for spans in art.TORSO_NECK_SPANS:
        for y, (x0, x1) in enumerate(spans):
            mask[y, x0:x1] = 1.0
    return np.clip(dilate(mask, width) - mask, 0.0, 1.0)


def rivalries_mia(stem: str, rgba: np.ndarray, ctx: dict) -> np.ndarray:
    dark, orange, aqua = hexf(MIA_DARK), hexf(MIA_ORANGE), hexf(MIA_AQUA)
    h, w = rgba.shape[:2]
    if stem == "torso":
        out = rgba.copy()
        ring = neck_ring((h, w), 2.2)
        out = over(out, orange, ring * (np.arange(h)[:, None] < 72))
        cover = rect((h, w), 128, 90, 196, 104)                              # the donor's tiny "Dolphins" script under the shield
        out = over(out, dark, cover)
        out = over(out, orange, text_cov((h, w), "MIAMI", "sans_bold", (161, 96), 7.5, tracking=0))
        return out
    if stem == "sleeve":
        out = rgba.copy()
        for x0, y0, x1, y1 in ((30, 19, 100, 52), (30, 80, 100, 115)):        # the donor's two dolphin logos (not its swooshes)
            out[y0:y1, x0:x1, :3] = dark[None, None, :]
        return out
    if stem == "helmet_helmet02":
        out = rgba.copy()
        out = over(out, hexf("#F2F2EE"), rect((h, w), 190, 60, 255, 107))
        out = over(out, hexf(BC_BLACK), text_cov((h, w), "305", "sans_bold", (222.5, 83.5), 21.0))
        return out
    return rgba


PAINTERS["rivalries_mia"] = rivalries_mia


# ------------------------------------------------------------------------------------------------ Raiders white throwback

def raiders_throwback(stem: str, rgba: np.ndarray, ctx: dict) -> np.ndarray:
    """Silver numerals with a black outline (the 1970 road look) on the 2026 road kit's glyph shapes. The slot's number
    textures are only 640 to 992 bytes: two-colour anti-aliased numerals do not fit, so the edge is hard (binary alpha)
    and the black outline is 2 px (u3c probe, 2026-10-08: 6 of 10 digits fail with the soft edge)."""
    from scipy import ndimage
    if not stem.startswith(("digit_jersey_", "digit_arm_")):
        return rgba
    silver = hexf("#CCC4C4")
    black = hexf("#040404")
    m = rgba[..., 3] > 0.5
    inner = ndimage.binary_erosion(m, structure=np.ones((3, 3), bool), iterations=2)
    out = np.zeros_like(rgba)
    out[m, :3] = black
    out[inner, :3] = silver
    out[..., 3] = m.astype(np.float32)
    return out


PAINTERS["raiders_throwback"] = raiders_throwback


def apply(name: str, stem: str, rgba: np.ndarray, ctx: dict) -> np.ndarray:
    return PAINTERS[name](stem, rgba, ctx)
