#!/usr/bin/env python3
"""Author the MyCareer apartment hub art (Fable, 2026-09-07).

Every pixel written by this script is drawn here: procedural plaster, a dusk
skyline, and flat-shaded props. The Crib room materials (wall, window, framed
shirt, television, paintings) were looked at as *style* references only; no
retail pixel is read or copied. Running the script regenerates:

    mycareer_apartment.png   512x512 hub background (7 P8 mips in game)
    mycareer_panels.png      256x128 panel backing atlas (5 mips)
    mycareer_calendar.png    128x128 calendar icon atlas (5 mips)
    mycareer_focus.png       128x32 focus-row highlight (1 mip, provisional)
    hub_mockup_640x480.png   the composed hub at 4:3
    hub_mockup_wide.png      the composed hub at 16:9 (side art, unstretched UI)
    manifest.json            object / tile / icon rectangles for the checker

The renderer is deterministic (seeded grain), so the PNGs are reproducible.
Needs Pillow and numpy; the mockups also want Arial Bold as the retail-font
stand-in and fall back to DejaVu Sans Bold.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
SEED = 20260907

# Grain and gradient tuning. One 256-entry palette has to carry the whole room,
# so the wall grain (which widens the warm boxes median cut has to split) and
# the sky's hue span decide how finely the dusk gradient is represented.
# Measured with tools/mycareer_art_check.py: without sky grain the quantized
# dusk gradient steps in ~20-level bands; at sigma 6 the bands dissolve into a
# photographic grain like the Crib's own skybox, and the low-pass banding
# measure drops from 13 to 5 levels.
WALL_GRAIN = (6.0, 4.0, 2.5)      # plaster noise amplitude per octave (24, 8, 3 px cells)
FILM_GRAIN = 2.0                  # final per-pixel grain, whole image
SKY_GRAIN = 6.0                   # extra grain inside the window view
SKY_STOPS = [
    (0.00, (30, 26, 74)), (0.30, (78, 42, 100)), (0.55, (150, 72, 96)),
    (0.68, (206, 118, 78)), (0.76, (222, 152, 92)), (1.00, (120, 76, 66)),
]

# ----------------------------------------------------------------------------- layout
# Virtual 640x480 UI. The 4:3 hub shows the centred 512x384 crop of the 512x512
# texture (0.8 texture px per UI unit, texture row 64 = UI row 0). Wide shows the
# centred 512x288 crop scaled 1.6667x with the unstretched UI centred on it.
UI = {
    "content": (36, 28, 604, 452),
    "menu": (44, 142, 302, 376),       # nine 26 px rows from y 142
    "summary": (332, 142, 596, 376),
    "footer_y": 432,
    "row_height": 26,
    "rows": 9,
}
CROP_43 = (0, 64, 512, 448)
CROP_WIDE = (0, 112, 512, 400)
ROWS = [
    "PLAY NEXT GAME", "PRACTICE", "SCHEDULE", "MYPLAYER CARD",
    "TEAM AND DEPTH CHART", "REQUESTS", "UPGRADE", "SAVE", "QUIT TO MAIN MENU",
]


def ui_to_tex_43(x: float, y: float) -> tuple[float, float]:
    return x * 0.8, 64 + y * 0.8


# Texture-space rectangles of the composition (x0, y0, x1, y1), half open.
SCENE = {
    "ceiling_line": 76,
    "floor_line": 356,
    "window": (336, 116, 466, 276),
    "jersey": (250, 112, 310, 180),
    "painting": (474, 106, 510, 156),
    "lamp": (476, 160, 514, 374),
    "lamp_glow_center": (493, 196),
    "tv": (10, 246, 88, 356),
    "sofa": (262, 292, 430, 392),
    "side_table": (438, 268, 480, 356),
    "gear": (36, 352, 264, 400),
    "drape": (316, 98, 332, 302),
}
# Objects that must stay inside the wide crop (core art). The lamp pole may
# run past the wide crop's bottom edge and the painting may be clipped at the
# right edge of 4:3, so those are listed as "accent", not core.
CORE_OBJECTS = ("window", "jersey", "sofa", "tv", "gear", "side_table")


# ----------------------------------------------------------------------------- helpers
def value_noise(shape: tuple[int, int], cell: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth noise in [-1, 1]: a random grid upsampled bilinearly."""
    h, w = shape
    gh, gw = h // cell + 2, w // cell + 2
    grid = rng.random((gh, gw)).astype(np.float32)
    big = Image.fromarray((grid * 255).astype(np.uint8), "L").resize((gw * cell, gh * cell), Image.Resampling.BILINEAR)
    arr = np.asarray(big, dtype=np.float32)[:h, :w] / 255.0
    return arr * 2.0 - 1.0


def fractal(shape, cells, amps, rng):
    out = np.zeros(shape, np.float32)
    for cell, amp in zip(cells, amps):
        out += value_noise(shape, cell, rng) * amp
    return out


def lerp(a, b, t):
    return a + (b - a) * t


def vgrad(h, w, stops):
    """Vertical gradient. stops: list of (t in 0..1, (r,g,b))."""
    ts = np.array([s[0] for s in stops], np.float32)
    cols = np.array([s[1] for s in stops], np.float32)
    y = np.linspace(0, 1, h, dtype=np.float32)
    out = np.zeros((h, w, 3), np.float32)
    for c in range(3):
        out[:, :, c] = np.interp(y, ts, cols[:, c])[:, None]
    return out


def to_img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


class Layer:
    """An RGBA prop layer drawn at 2x and reduced with a box filter."""

    def __init__(self, size=(512, 512), scale=2):
        self.s = scale
        self.im = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def p(self, pts):
        return [(x * self.s, y * self.s) for x, y in pts]

    def box(self, b):
        return [b[0] * self.s, b[1] * self.s, b[2] * self.s - 1, b[3] * self.s - 1]

    def rect(self, b, fill):
        self.d.rectangle(self.box(b), fill=fill)

    def rrect(self, b, r, fill, outline=None, width=1):
        self.d.rounded_rectangle(self.box(b), radius=r * self.s, fill=fill, outline=outline, width=max(1, int(round(width * self.s))))

    def ellipse(self, b, fill, outline=None, width=1):
        self.d.ellipse(self.box(b), fill=fill, outline=outline, width=max(1, int(round(width * self.s))))

    def poly(self, pts, fill, outline=None, width=1):
        self.d.polygon(self.p(pts), fill=fill, outline=outline, width=max(1, int(round(width * self.s))) if outline else 0)

    def line(self, pts, fill, width=1):
        self.d.line(self.p(pts), fill=fill, width=max(1, int(width * self.s)))

    def reduced(self) -> Image.Image:
        w, h = self.im.size
        return self.im.resize((w // self.s, h // self.s), Image.Resampling.BOX)


# ----------------------------------------------------------------------------- apartment
def light_map(rng: np.random.Generator) -> np.ndarray:
    """Per-pixel RGB light multiplier: dim cool ambient, warm lamp, dusk window."""
    h = w = 512
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ambient = np.array([0.36, 0.35, 0.40], np.float32)
    lx, ly = SCENE["lamp_glow_center"]
    d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2)
    lamp = 1.0 / (1.0 + (d / 190.0) ** 2)
    lamp_tint = np.array([1.10, 0.84, 0.54], np.float32)
    wx0, wy0, wx1, wy1 = SCENE["window"]
    dx = np.maximum(np.maximum(wx0 - xx, xx - wx1), 0)
    dy = np.maximum(np.maximum(wy0 - yy, yy - wy1), 0)
    dw = np.sqrt(dx ** 2 + dy ** 2)
    window = np.exp(-dw / 120.0)
    window_tint = np.array([1.00, 0.62, 0.58], np.float32)
    light = ambient[None, None, :] + lamp[..., None] * 1.35 * lamp_tint[None, None, :] \
        + window[..., None] * 0.40 * window_tint[None, None, :]
    # Gentle vignette so the far corners and the footer band stay calm.
    cx, cy = 300, 250
    r = np.sqrt(((xx - cx) / 360.0) ** 2 + ((yy - cy) / 330.0) ** 2)
    light *= (1.0 - 0.28 * np.clip(r, 0, 1.4) ** 2)[..., None]
    # The left third is the menu column: hold it in shadow deliberately.
    shade = np.clip((260 - xx) / 260.0, 0, 1) ** 1.3
    light *= (1.0 - 0.42 * shade)[..., None]
    return light.astype(np.float32)


def base_room(rng: np.random.Generator) -> np.ndarray:
    """Wall, ceiling and floor albedo (before lighting)."""
    h = w = 512
    out = np.zeros((h, w, 3), np.float32)
    # Plaster wall, in the family of the Crib's grey wall but warmed toward dusk.
    plaster = np.array([198, 180, 156], np.float32)
    grain = fractal((h, w), (24, 8, 3), WALL_GRAIN, rng)
    wall = plaster[None, None, :] + grain[..., None] * np.array([1.0, 0.9, 0.8], np.float32)
    out[:] = wall
    # Ceiling above the crown line, darker and cooler.
    cl = SCENE["ceiling_line"]
    out[:cl] = np.array([104, 100, 98], np.float32) + grain[:cl, :, None] * 0.5
    out[cl - 3:cl] = np.array([170, 160, 148], np.float32)      # molding lit face
    out[cl:cl + 2] = np.array([110, 98, 88], np.float32)        # molding shadow
    # Floor: walnut planks running left to right, slightly larger toward the viewer.
    fl = SCENE["floor_line"]
    walnut = np.array([96, 60, 38], np.float32)
    floor = np.repeat(walnut[None, None, :], h - fl, axis=0).repeat(w, axis=1)
    y = fl
    k = 0
    plank_rng = np.random.default_rng(SEED + 7)
    while y < h:
        step = int(18 + 2.2 * k)
        tone = 1.0 + plank_rng.normal(0, 0.06)
        floor[y - fl:min(h, y + step) - fl] *= tone
        seam = min(h - 1, y + step - 1) - fl
        floor[seam:seam + 1] *= 0.72
        # staggered end joints
        joints = plank_rng.integers(0, w, size=3)
        for jx in joints:
            floor[y - fl:min(h, y + step) - fl, jx:jx + 1] *= 0.86
        y += step
        k += 1
    wood_grain = fractal((h - fl, w), (64, 6), (5.0, 3.0), rng)
    floor += wood_grain[..., None] * np.array([1.0, 0.8, 0.6], np.float32)
    # Faint warm reflection on the boards below the window, and a foreground fade.
    yy, xx = np.mgrid[fl:h, 0:w].astype(np.float32)
    wx0, _, wx1, _ = SCENE["window"]
    refl = np.exp(-((xx - (wx0 + wx1) / 2) / 90.0) ** 2) * np.exp(-(yy - fl) / 70.0)
    floor += refl[..., None] * np.array([70, 38, 18], np.float32)
    out[fl:] = floor
    # Baseboard.
    out[fl - 7:fl - 1] = np.array([70, 52, 40], np.float32)
    out[fl - 8:fl - 7] = np.array([120, 96, 76], np.float32)
    out[fl - 1:fl + 1] = np.array([40, 28, 20], np.float32)
    return out


def skyline_window(rng: np.random.Generator) -> Image.Image:
    """The view: dusk sky, city silhouettes with lit windows, a lit stadium."""
    x0, y0, x1, y1 = SCENE["window"]
    w, h = x1 - x0, y1 - y0
    horizon = int(h * 0.70)
    sky = vgrad(h, w, SKY_STOPS)
    if SKY_GRAIN:
        sky = sky + rng.normal(0.0, SKY_GRAIN, size=(h, w, 1)).astype(np.float32)
    # Thin cloud streaks.
    cl = Layer((w, h), 4)
    for cx, cy, cw, ch, tone in ((30, 28, 70, 5, (60, 40, 90, 150)), (70, 52, 60, 4, (110, 60, 90, 130)),
                                 (95, 20, 40, 3, (50, 34, 80, 140)), (20, 70, 80, 4, (200, 120, 90, 110))):
        cl.ellipse((cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2), tone)
    clouds = cl.reduced().filter(ImageFilter.GaussianBlur(0.8))
    img = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    img.alpha_composite(clouds)
    # Far towers (bluish), near towers (dark), and a stadium bowl with light towers.
    far = Layer((w, h), 2)
    x = -4
    while x < w + 4:
        bw = int(rng.integers(6, 16))
        bh = int(rng.integers(14, 46))
        far.rect((x, horizon - bh, x + bw, horizon + 6), (74, 52, 96, 255))
        x += bw + int(rng.integers(0, 3))
    img.alpha_composite(far.reduced())
    near = Layer((w, h), 2)
    buildings = []
    x = -6
    while x < w + 6:
        bw = int(rng.integers(8, 24))
        bh = int(rng.integers(22, 78))
        top = horizon + 4 - bh
        near.rect((x, top, x + bw, h), (18, 16, 34, 255))
        if rng.random() < 0.35:   # rooftop box / antenna
            near.rect((x + bw // 3, top - 4, x + bw // 3 + 3, top), (18, 16, 34, 255))
        buildings.append((x, top, bw, bh))
        x += bw + int(rng.integers(0, 3))
    # Stadium on the right horizon: a low bowl and four floodlight towers.
    sx = int(w * 0.62)
    near.ellipse((sx, horizon - 10, sx + 46, horizon + 8), (30, 24, 44, 255))
    near.rect((sx - 2, horizon - 1, sx + 48, h), (18, 16, 34, 255))
    for tx in (sx + 6, sx + 16, sx + 30, sx + 40):
        near.line([(tx, horizon - 8), (tx, horizon - 26)], (40, 36, 60, 255), 1)
        near.rect((tx - 2, horizon - 28, tx + 2, horizon - 25), (255, 246, 214, 255))
    img.alpha_composite(near.reduced())
    # Floodlight glow.
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((sx - 4, horizon - 40, sx + 50, horizon - 12), (255, 226, 170, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(4))
    img.alpha_composite(glow)
    # Lit windows on the near towers.
    arr = np.array(img)
    for (bx, top, bw, bh) in buildings:
        n = int(rng.integers(2, 8))
        for _ in range(n):
            wx = int(rng.integers(bx + 1, max(bx + 2, bx + bw - 1)))
            wy = int(rng.integers(top + 3, max(top + 4, top + bh - 4)))
            if 0 <= wx < w and 0 <= wy < h:
                warm = rng.random() < 0.7
                arr[wy, wx, :3] = (255, 214, 140) if warm else (190, 220, 255)
                arr[wy, wx, 3] = 255
    img = Image.fromarray(arr, "RGBA")
    # Glass: a soft diagonal reflection.
    gl = Layer((w, h), 2)
    gl.poly([(w * 0.55, 0), (w * 0.80, 0), (w * 0.35, h), (w * 0.10, h)], (255, 240, 230, 22))
    img.alpha_composite(gl.reduced())
    return img


def props(rng: np.random.Generator) -> Image.Image:
    """All furniture and gear on one RGBA layer, flat shaded."""
    L = Layer()
    fl = SCENE["floor_line"]

    # --- floor shadows first (soft, drawn at 1x later) -----------------------
    shadows = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadows)
    for (x0, y0, x1, y1) in (SCENE["sofa"], SCENE["tv"], SCENE["side_table"]):
        sd.ellipse((x0 - 6, y1 - 10, x1 + 6, y1 + 8), (0, 0, 0, 150))
    for b in ((36, 388, 106, 404), (108, 388, 162, 404), (174, 392, 226, 404)):
        sd.ellipse(b, (0, 0, 0, 140))
    shadows = shadows.filter(ImageFilter.GaussianBlur(4))

    # --- framed jersey (mahogany frame, black mat, plain navy shirt) ---------
    x0, y0, x1, y1 = SCENE["jersey"]
    L.rect((x0, y0, x1, y1), (112, 40, 28, 255))                          # mahogany
    L.poly([(x0, y0), (x1, y0), (x1 - 5, y0 + 5), (x0 + 5, y0 + 5)], (158, 70, 48, 255))
    L.poly([(x0, y0), (x0 + 5, y0 + 5), (x0 + 5, y1 - 5), (x0, y1)], (138, 58, 40, 255))
    L.poly([(x1, y1), (x0, y1), (x0 + 5, y1 - 5), (x1 - 5, y1 - 5)], (64, 22, 14, 255))
    L.poly([(x1, y0), (x1, y1), (x1 - 5, y1 - 5), (x1 - 5, y0 + 5)], (84, 30, 20, 255))
    L.rect((x0 + 5, y0 + 5, x1 - 5, y1 - 5), (12, 10, 10, 255))          # black mat
    L.rect((x0 + 5, y0 + 5, x1 - 5, y0 + 6), (40, 30, 30, 255))
    # A football jersey: wide shoulders, short sleeves, body ending above the mat.
    ix0, iy0, ix1, iy1 = x0 + 8, y0 + 11, x1 - 8, y1 - 11
    cx = (ix0 + ix1) / 2
    navy, dark = (30, 42, 92, 255), (20, 28, 64, 255)
    L.poly([(ix0 + 13, iy0), (cx - 6, iy0 + 3), (cx + 6, iy0 + 3), (ix1 - 13, iy0),
            (ix1 + 1, iy0 + 9), (ix1 - 3, iy0 + 26), (ix1 - 12, iy0 + 24), (ix1 - 12, iy1),
            (ix0 + 12, iy1), (ix0 + 12, iy0 + 24), (ix0 + 3, iy0 + 26), (ix0 - 1, iy0 + 9)], navy)
    L.poly([(cx - 7, iy0 + 2), (cx + 7, iy0 + 2), (cx + 4, iy0 + 9), (cx - 4, iy0 + 9)], (236, 236, 240, 255))
    L.poly([(cx - 4, iy0 + 9), (cx + 4, iy0 + 9), (cx, iy0 + 12)], navy)
    for sx0, sx1 in ((ix0 - 1, ix0 + 10), (ix1 - 10, ix1 + 1)):
        for sy in (iy0 + 14, iy0 + 19):
            L.poly([(sx0, sy + 1), (sx1, sy - 1), (sx1, sy + 2), (sx0, sy + 4)], (232, 232, 236, 255))
    L.line([(ix0 + 12, iy0 + 25), (ix0 + 12, iy1)], dark, 1)
    L.line([(ix1 - 12, iy0 + 25), (ix1 - 12, iy1)], dark, 1)
    L.line([(cx, iy0 + 28), (cx + 1, iy1 - 4)], dark, 1)

    # --- pop-art canvas on the right wall (flat posterised helmet) ----------
    x0, y0, x1, y1 = SCENE["painting"]
    L.rect((x0, y0, x1, y1), (222, 92, 36, 255))
    L.rect((x0 + 2, y0 + 2, x1 - 2, y1 - 2), (238, 116, 48, 255))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 3
    L.ellipse((cx - 13, cy - 13, cx + 13, cy + 11), (58, 32, 96, 255))
    L.rect((cx - 13, cy - 2, cx + 13, cy + 11), (58, 32, 96, 255))
    L.ellipse((cx - 9, cy - 9, cx + 5, cy - 1), (240, 196, 60, 255))
    for k in range(3):
        L.line([(cx + 2, cy + 3 + k * 4), (cx + 15, cy + 1 + k * 4)], (240, 196, 60, 255), 1.5)
    L.rect((x0 + 4, y1 - 9, x1 - 4, y1 - 5), (240, 196, 60, 255))

    # --- one deep red drape, pulled open to the left of the window -----------
    x0, y0, x1, y1 = SCENE["window"]
    dx0, dy0, dx1, dy1 = SCENE["drape"]
    L.rect((dx0, dy0, dx1, dy1), (96, 26, 30, 255))
    for fx in range(dx0 + 2, dx1 - 2, 5):
        L.rect((fx, dy0, fx + 2, dy1), (124, 38, 40, 255))
        L.rect((fx + 2, dy0, fx + 3, dy1), (66, 16, 20, 255))
    L.rect((dx0 - 4, dy0 - 3, x1 + 28, dy0 + 1), (74, 52, 40, 255))            # curtain rod
    L.ellipse((dx0 - 9, dy0 - 5, dx0 - 3, dy0 + 3), (110, 82, 58, 255))
    L.ellipse((x1 + 26, dy0 - 5, x1 + 32, dy0 + 3), (110, 82, 58, 255))

    # --- window frame (four bars around the glass), mullions, sill ----------
    frame = (58, 40, 30, 255)
    L.rect((x0 - 9, y0 - 9, x1 + 9, y0), frame)
    L.rect((x0 - 9, y1, x1 + 9, y1 + 3), frame)
    L.rect((x0 - 9, y0 - 9, x0, y1 + 3), frame)
    L.rect((x1, y0 - 9, x1 + 9, y1 + 3), frame)
    L.rect((x0 - 9, y0 - 9, x1 + 9, y0 - 6), (92, 66, 50, 255))
    L.rect((x0 - 9, y0 - 9, x0 - 6, y1 + 3), (78, 56, 42, 255))
    L.rect((x0 - 2, y0 - 2, x1 + 2, y0), (30, 20, 14, 255))          # inner shadow lip
    L.rect((x0 - 2, y0 - 2, x0, y1 + 2), (30, 20, 14, 255))
    mx, my = (x0 + x1) // 2, (y0 + y1) // 2
    L.rect((mx - 2, y0, mx + 2, y1), (48, 34, 26, 255))
    L.rect((x0, my - 2, x1, my + 2), (48, 34, 26, 255))
    L.rect((mx - 2, y0, mx - 1, y1), (96, 70, 52, 255))
    L.rect((x0, my - 2, x1, my - 1), (96, 70, 52, 255))
    L.rect((x0 - 14, y1 + 3, x1 + 14, y1 + 9), (128, 100, 76, 255))
    L.rect((x0 - 14, y1 + 9, x1 + 14, y1 + 14), (70, 50, 38, 255))

    # --- television on a low stand, in the dark corner ----------------------
    x0, y0, x1, y1 = SCENE["tv"]
    L.rect((x0 + 4, y0 + 62, x1 - 4, fl - 2), (36, 26, 20, 255))            # stand body
    L.rect((x0, y0 + 60, x1, y0 + 64), (66, 50, 38, 255))                   # stand top
    L.rect((x0 + 8, y0 + 82, x1 - 8, y0 + 96), (22, 16, 12, 255))           # shelf recess
    L.rrect((x0, y0, x1, y0 + 60), 5, (46, 46, 52, 255))                    # CRT body
    L.rrect((x0, y0, x1, y0 + 4), 2, (72, 72, 80, 255))                     # lit top edge
    L.rrect((x0 + 6, y0 + 5, x1 - 6, y0 + 49), 4, (10, 10, 12, 255))        # screen
    L.poly([(x0 + 12, y0 + 8), (x0 + 30, y0 + 8), (x0 + 22, y0 + 46), (x0 + 8, y0 + 46)], (34, 26, 26, 255))
    L.rect((x0 + 6, y0 + 51, x1 - 6, y0 + 56), (28, 28, 32, 255))           # control strip
    L.rect((x1 - 16, y0 + 52, x1 - 14, y0 + 54), (60, 200, 90, 255))        # standby LED

    # --- sofa: brown leather, two cushions, a football resting on it --------
    x0, y0, x1, y1 = SCENE["sofa"]
    leather, hi, lo = (94, 56, 36, 255), (138, 86, 56, 255), (56, 32, 20, 255)
    L.rrect((x0, y0 + 4, x1, y1 - 12), 6, leather)
    L.rrect((x0 + 2, y0, x1 - 2, y0 + 8), 4, hi)                            # back top
    L.rrect((x0 + 20, y0 + 42, x1 - 20, y0 + 80), 5, (104, 64, 42, 255))    # seat
    L.rect((x0 + 20, y0 + 42, x1 - 20, y0 + 46), hi)
    L.rect(((x0 + x1) // 2 - 1, y0 + 42, (x0 + x1) // 2 + 1, y0 + 80), lo)  # cushion seam
    for ax0, ax1 in ((x0, x0 + 22), (x1 - 22, x1)):
        L.rrect((ax0, y0 + 30, ax1, y1 - 12), 7, (110, 68, 44, 255))
        L.rrect((ax0 + 2, y0 + 30, ax1 - 2, y0 + 36), 3, hi)
    L.rect((x0 + 4, y1 - 12, x1 - 4, y1 - 4), lo)                           # base
    L.rect((x0 + 8, y1 - 4, x0 + 14, y1), (30, 18, 12, 255))
    L.rect((x1 - 14, y1 - 4, x1 - 8, y1), (30, 18, 12, 255))
    bx, by = x0 + 108, y0 + 44
    L.ellipse((bx, by, bx + 34, by + 18), (124, 62, 30, 255))
    L.line([(bx + 12, by + 9), (bx + 22, by + 9)], (240, 236, 224, 255), 1.5)
    L.line([(bx + 5, by + 5), (bx + 5, by + 13)], (240, 236, 224, 255), 1)
    L.line([(bx + 29, by + 5), (bx + 29, by + 13)], (240, 236, 224, 255), 1)

    # --- side table with a plant ---------------------------------------------
    x0, y0, x1, y1 = SCENE["side_table"]
    L.rect((x0 + 4, y1 - 36, x1 - 4, y1 - 32), (74, 48, 34, 255))          # table top
    L.rect((x0 + 8, y1 - 32, x0 + 11, y1), (44, 28, 20, 255))
    L.rect((x1 - 11, y1 - 32, x1 - 8, y1), (44, 28, 20, 255))
    px = (x0 + x1) // 2
    L.poly([(px - 9, y1 - 54), (px + 9, y1 - 54), (px + 7, y1 - 36), (px - 7, y1 - 36)], (146, 78, 52, 255))
    L.rect((px - 10, y1 - 56, px + 10, y1 - 52), (168, 92, 62, 255))
    for dx, top, tone in ((-6, 30, (52, 120, 66, 255)), (0, 38, (70, 150, 82, 255)),
                          (6, 32, (46, 108, 60, 255)), (-2, 26, (82, 160, 90, 255)), (4, 22, (60, 130, 70, 255))):
        L.poly([(px + dx - 3, y1 - 54), (px + dx + 3, y1 - 54), (px + dx + dx * 0.4, y1 - 54 - top)], tone)

    # --- floor lamp: the warm key light ---------------------------------------
    x0, y0, x1, y1 = SCENE["lamp"]
    cx = (x0 + x1) // 2
    L.ellipse((cx - 16, y1 - 8, cx + 16, y1 + 2), (40, 28, 18, 255))
    L.rect((cx - 1, y0 + 34, cx + 1, y1 - 4), (176, 138, 66, 255))
    L.poly([(cx - 14, y0), (cx + 14, y0), (cx + 18, y0 + 38), (cx - 18, y0 + 38)], (244, 214, 156, 255))
    L.poly([(cx - 10, y0 + 6), (cx + 10, y0 + 6), (cx + 12, y0 + 32), (cx - 12, y0 + 32)], (255, 240, 200, 255))
    L.rect((cx - 14, y0, cx + 14, y0 + 2), (214, 178, 120, 255))

    # --- gear on the floor: duffel, helmet, football, cleats -----------------
    L.rrect((36, 364, 104, 398), 10, (48, 62, 46, 255))                     # duffel
    L.rrect((36, 364, 104, 372), 5, (64, 82, 60, 255))
    L.rect((44, 362, 96, 365), (24, 30, 22, 255))                            # strap
    L.rect((56, 368, 84, 370), (24, 30, 22, 255))
    L.ellipse((110, 354, 158, 398), (30, 42, 92, 255))                       # helmet shell
    L.ellipse((116, 357, 146, 376), (58, 76, 130, 255))                      # highlight
    L.ellipse((118, 362, 140, 376), (30, 42, 92, 255))
    L.rect((130, 382, 162, 396), (30, 42, 92, 255))
    for k in range(3):
        L.line([(140, 380 + k * 5), (166, 378 + k * 5)], (150, 150, 156, 255), 1.5)
    L.line([(160, 376), (162, 394)], (150, 150, 156, 255), 1.5)
    L.ellipse((124, 380, 132, 388), (16, 22, 52, 255))                       # ear hole
    L.ellipse((176, 380, 222, 400), (124, 62, 30, 255))                      # football
    L.line([(190, 390), (208, 390)], (240, 236, 224, 255), 1.5)
    L.line([(183, 385), (183, 395)], (240, 236, 224, 255), 1)
    L.line([(215, 385), (215, 395)], (240, 236, 224, 255), 1)
    for sx in (232, 248):                                                    # cleats
        L.poly([(sx, 394), (sx + 4, 384), (sx + 12, 384), (sx + 14, 394)], (226, 226, 230, 255))
        L.rect((sx, 394, sx + 14, 398), (20, 20, 22, 255))

    layer = L.reduced()
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    out.alpha_composite(shadows)
    out.alpha_composite(layer)
    return out


def render_apartment() -> Image.Image:
    rng = np.random.default_rng(SEED)
    albedo = base_room(rng)
    light = light_map(rng)
    room = albedo * light
    # Window view (already a lit image): paste unlit, then a soft inner shadow.
    view = skyline_window(np.random.default_rng(SEED + 3))
    x0, y0, x1, y1 = SCENE["window"]
    room_img = to_img(room).convert("RGBA")
    room_img.paste(view, (x0, y0))
    pr = props(rng)
    pr_arr = np.asarray(pr).astype(np.float32)
    lit = pr_arr.copy()
    lit[..., :3] = np.clip(pr_arr[..., :3] * light * 1.05, 0, 255)
    # The lamp shade and the window keep their own emitted colour.
    lx0, ly0, lx1, ly1 = SCENE["lamp"]
    lit[ly0:ly0 + 40, lx0:lx1, :3] = pr_arr[ly0:ly0 + 40, lx0:lx1, :3]
    room_img.alpha_composite(Image.fromarray(lit.astype(np.uint8), "RGBA"))
    final = np.asarray(room_img).astype(np.float32)
    grain = rng.normal(0.0, FILM_GRAIN, size=(512, 512, 1)).astype(np.float32)
    final[..., :3] = np.clip(final[..., :3] + grain, 0, 255)
    final[..., 3] = 255
    return Image.fromarray(final.astype(np.uint8), "RGBA")


# ----------------------------------------------------------------------------- panels
PANEL_TILES = {
    # name: (rect, kind, 9-slice inset)
    "summary_opaque": ((4, 4, 132, 100), "opaque", 12),
    "opponent_translucent": ((140, 4, 252, 60), "translucent", 8),
    "balance_translucent": ((140, 68, 252, 116), "translucent", 8),
    "ribbon_translucent": ((4, 108, 132, 124), "translucent", 4),
}


def render_panels() -> Image.Image:
    L = Layer((256, 128), 2)
    x0, y0, x1, y1 = PANEL_TILES["summary_opaque"][0]
    L.rrect((x0, y0, x1, y1), 6, (12, 18, 44, 255))
    L.rrect((x0, y0, x1, y1), 6, None, outline=(58, 72, 120, 255), width=1)
    L.rect((x0 + 1, y0 + 1, x1 - 1, y0 + 3), (70, 86, 140, 255))
    L.rect((x0 + 1, y0 + 8, x0 + 5, y1 - 8), (200, 48, 30, 255))
    x0, y0, x1, y1 = PANEL_TILES["opponent_translucent"][0]
    L.rrect((x0, y0, x1, y1), 5, (8, 12, 28, 176))
    L.rrect((x0, y0, x1, y1), 5, None, outline=(90, 106, 154, 230), width=1)
    L.rect((x0 + 1, y0 + 1, x1 - 1, y0 + 3), (90, 106, 154, 220))
    x0, y0, x1, y1 = PANEL_TILES["balance_translucent"][0]
    L.rrect((x0, y0, x1, y1), 5, (26, 20, 8, 168))
    L.rrect((x0, y0, x1, y1), 5, None, outline=(150, 120, 60, 230), width=1)
    L.rect((x0 + 1, y1 - 4, x1 - 1, y1 - 1), (232, 188, 70, 240))
    x0, y0, x1, y1 = PANEL_TILES["ribbon_translucent"][0]
    L.rrect((x0, y0, x1, y1), 3, (0, 0, 0, 140))
    L.rect((x0 + 1, y0 + 1, x1 - 1, y0 + 2), (255, 255, 255, 60))
    img = L.reduced()
    arr = np.array(img)
    # Vertical sheen on the opaque tile so it reads as a card, not a flat block.
    x0, y0, x1, y1 = PANEL_TILES["summary_opaque"][0]
    t = np.linspace(1.0, 0.72, y1 - y0, dtype=np.float32)[:, None, None]
    region = arr[y0:y1, x0:x1, :3].astype(np.float32) * t
    mask = arr[y0:y1, x0:x1, 3:4] > 0
    arr[y0:y1, x0:x1, :3] = np.where(mask, np.clip(region, 0, 255), arr[y0:y1, x0:x1, :3]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ----------------------------------------------------------------------------- calendar
CAL_CELL = 32
CAL_ICONS = ["played", "upcoming", "bye", "practice", "request", "current", "milestone"]


def cal_cell(index: int) -> tuple[int, int, int, int]:
    cx, cy = (index % 4) * CAL_CELL, (index // 4) * CAL_CELL
    return cx, cy, cx + CAL_CELL, cy + CAL_CELL


def render_calendar() -> Image.Image:
    L = Layer((128, 128), 4)
    ink = (14, 16, 24, 255)

    def cell(i):
        x0, y0, x1, y1 = cal_cell(i)
        return x0 + 3, y0 + 3, x1 - 3, y1 - 3

    # played: filled circle with a check mark
    x0, y0, x1, y1 = cell(0)
    L.ellipse((x0, y0, x1, y1), (66, 170, 90, 255), outline=ink, width=1.5)
    L.line([(x0 + 6, y0 + 13), (x0 + 11, y0 + 18), (x1 - 6, y0 + 8)], (255, 255, 255, 255), 3)
    # upcoming: a football (pointed ellipse) tilted the classic way, with laces
    x0, y0, x1, y1 = cell(1)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ang = -np.pi / 5
    ca, sa = np.cos(ang), np.sin(ang)

    def rot(px, py):
        return (cx + px * ca - py * sa, cy + px * sa + py * ca)

    outline = []
    for k in range(40):
        t = 2 * np.pi * k / 40
        # a pointed ellipse: squash the ends with a cosine power
        px = 13.5 * np.cos(t)
        py = 7.0 * np.sin(t) * (abs(np.cos(t)) ** 0.15 if abs(np.cos(t)) > 0.001 else 1.0)
        outline.append(rot(px, py))
    L.poly(outline, (236, 236, 240, 255), outline=ink, width=1.5)
    L.line([rot(-5, 0), rot(5, 0)], ink, 1.5)
    for k in (-3.5, -1, 1.5, 4):
        L.line([rot(k, -2.5), rot(k, 2.5)], ink, 1.2)
    # bye: a bold rounded dash, nothing on the slate
    x0, y0, x1, y1 = cell(2)
    cy = (y0 + y1) / 2
    L.rrect((x0 + 1, cy - 4, x1 - 1, cy + 4), 4, (200, 204, 214, 255), outline=ink, width=1.5)
    # practice: a striped cone
    x0, y0, x1, y1 = cell(3)
    cx = (x0 + x1) / 2
    L.poly([(cx - 5, y0 + 1), (cx + 5, y0 + 1), (x1 - 2, y1 - 4), (x0 + 2, y1 - 4)], (240, 140, 40, 255), outline=ink, width=1.5)
    L.poly([(cx - 7, y0 + 9), (cx + 7, y0 + 9), (cx + 8, y0 + 13), (cx - 8, y0 + 13)], (255, 255, 255, 255))
    L.poly([(cx - 9, y0 + 17), (cx + 9, y0 + 17), (cx + 10, y0 + 21), (cx - 10, y0 + 21)], (255, 255, 255, 255))
    L.rect((x0, y1 - 5, x1, y1 - 1), (240, 140, 40, 255))
    L.rrect((x0, y1 - 5, x1, y1 - 1), 1, None, outline=ink, width=1.5)
    # request: an envelope
    x0, y0, x1, y1 = cell(4)
    L.rrect((x0, y0 + 4, x1, y1 - 4), 2, (90, 150, 230, 255), outline=ink, width=1.5)
    L.line([(x0 + 1, y0 + 5), ((x0 + x1) / 2, y0 + 15), (x1 - 1, y0 + 5)], ink, 1.5)
    L.line([(x0 + 1, y1 - 5), (x0 + 10, y0 + 12)], ink, 1.2)
    L.line([(x1 - 1, y1 - 5), (x1 - 10, y0 + 12)], ink, 1.2)
    # current week: a hollow ring marker
    x0, y0, x1, y1 = cell(5)
    L.ellipse((x0, y0, x1, y1), None, outline=(255, 214, 80, 255), width=3)
    L.ellipse((x0 + 1, y0 + 1, x1 - 1, y1 - 1), None, outline=ink, width=1)
    # milestone: a five point star
    x0, y0, x1, y1 = cell(6)
    cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2 + 1, (x1 - x0) / 2
    pts = []
    for k in range(10):
        ang = -np.pi / 2 + k * np.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * np.cos(ang), cy + rr * np.sin(ang)))
    L.poly(pts, (255, 214, 80, 255), outline=ink, width=1.5)
    return L.reduced()


# ----------------------------------------------------------------------------- focus
def render_focus() -> Image.Image:
    w, h = 128, 32
    arr = np.zeros((h, w, 4), np.float32)
    top, bot = np.array([214, 66, 30], np.float32), np.array([132, 28, 14], np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    fill = top[None, None, :] * (1 - t[..., None]) + bot[None, None, :] * t[..., None]
    # centre band: a lighter fill through the middle rows so the row reads as lit
    band = np.exp(-((np.arange(h) - h / 2) / 7.0) ** 2)[:, None, None]
    fill = fill + band * np.array([30, 24, 16], np.float32)
    arr[..., :3] = fill
    arr[..., 3] = 255
    # gloss on the upper third
    arr[: h // 3, :, :3] = np.clip(arr[: h // 3, :, :3] + 22, 0, 255)
    # clear edge: 2 px bright rim, then a 1 px dark keyline inside it
    rim = np.array([255, 190, 96], np.float32)
    arr[:2, :, :3] = rim
    arr[-2:, :, :3] = rim
    arr[:, :2, :3] = rim
    arr[:, -2:, :3] = rim
    key = np.array([92, 18, 8], np.float32)
    arr[2, 2:-2, :3] = key
    arr[-3, 2:-2, :3] = key
    arr[2:-2, 2, :3] = key
    arr[2:-2, -3, :3] = key
    # rounded ends: 4 px radius corners cut to transparent, 1 px anti-aliased
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    r = 5.0
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        corner = ((cx - r <= xx) if cx < w / 2 else (xx <= cx + r)) & ((cy - r <= yy) if cy < h / 2 else (yy <= cy + r))
        corner &= ((xx < cx) if cx < w / 2 else (xx > cx)) & ((yy < cy) if cy < h / 2 else (yy > cy))
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        cover = np.clip(r + 0.5 - d, 0, 1)
        arr[..., 3] = np.where(corner, arr[..., 3] * cover, arr[..., 3])
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ----------------------------------------------------------------------------- mockups
def font(px: int) -> ImageFont.FreeTypeFont:
    for path in ("/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf",
                 "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def stretch(tile: Image.Image, size: tuple[int, int], inset: int) -> Image.Image:
    """9-slice a tile to `size` so its corners and edges keep their pixels."""
    w, h = tile.size
    tw, th = size
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    xs = [(0, inset, 0, inset), (inset, w - inset, inset, tw - inset), (w - inset, w, tw - inset, tw)]
    ys = [(0, inset, 0, inset), (inset, h - inset, inset, th - inset), (h - inset, h, th - inset, th)]
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            piece = tile.crop((sx0, sy0, sx1, sy1))
            if (dx1 - dx0, dy1 - dy0) != piece.size:
                piece = piece.resize((max(1, dx1 - dx0), max(1, dy1 - dy0)), Image.Resampling.NEAREST)
            out.paste(piece, (dx0, dy0))
    return out


def text(d: ImageDraw.ImageDraw, xy, s, px, fill=(255, 255, 255), anchor="la", shadow=True):
    f = font(px)
    if shadow:
        d.text((xy[0] + 1, xy[1] + 1), s, font=f, fill=(0, 0, 0, 200), anchor=anchor)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def button(d: ImageDraw.ImageDraw, xy, letter, colour):
    x, y = xy
    d.ellipse((x, y, x + 14, y + 14), fill=colour, outline=(20, 20, 20))
    d.text((x + 7, y + 7), letter, font=font(10), fill=(0, 0, 0), anchor="mm")


def ui_layer(panels: Image.Image, calendar: Image.Image, focus: Image.Image) -> Image.Image:
    """The hub UI in virtual 640x480 space, transparent where the art shows."""
    ui = Image.new("RGBA", (640, 480), (0, 0, 0, 0))
    d = ImageDraw.Draw(ui)
    # header
    text(d, (44, 34), "MYCAREER", 30)
    text(d, (46, 70), "THE APARTMENT", 13, (255, 214, 80))
    d.rectangle((44, 92, 596, 93), fill=(214, 66, 30, 255))
    d.rectangle((44, 94, 596, 94), fill=(255, 255, 255, 90))
    text(d, (596, 70), "WEEK 3   PRESEASON", 13, (220, 220, 230), anchor="ra")
    # menu rows
    mx0, my0, mx1, _ = UI["menu"]
    rh = UI["row_height"]
    ui.alpha_composite(focus.resize((mx1 - mx0, rh), Image.Resampling.BILINEAR), (mx0, my0))
    for i, label in enumerate(ROWS):
        y = my0 + i * rh
        colour = (255, 255, 255) if i == 0 else (222, 226, 236)
        text(d, (mx0 + 10, y + rh // 2), label, 15, colour, anchor="lm")
    # summary column
    sx0, sy0, sx1, sy1 = UI["summary"]
    tile, kind, inset = PANEL_TILES["summary_opaque"]
    ui.alpha_composite(stretch(panels.crop(tile), (sx1 - sx0, 104), inset), (sx0, sy0))
    text(d, (sx0 + 14, sy0 + 10), "MARCUS REED", 17)
    text(d, (sx0 + 14, sy0 + 34), "QB   #12   SEATTLE", 12, (255, 214, 80))
    text(d, (sx0 + 14, sy0 + 56), "OVR  68      YEAR  1      AGE  22", 12, (222, 226, 236))
    text(d, (sx0 + 14, sy0 + 78), "RECORD  2 - 0      STARTER", 12, (222, 226, 236))
    tile, kind, inset = PANEL_TILES["opponent_translucent"]
    oy = sy0 + 112
    ui.alpha_composite(stretch(panels.crop(tile), (sx1 - sx0, 64), inset), (sx0, oy))
    text(d, (sx0 + 12, oy + 8), "NEXT   WEEK 3   AT DENVER", 12, (255, 255, 255))
    text(d, (sx0 + 12, oy + 26), "SUN 1:00 PM", 11, (222, 226, 236))
    icon_x = sx0 + 12
    strip = ["played", "played", "current", "upcoming", "bye", "practice", "request", "milestone"]
    for name in strip:
        idx = CAL_ICONS.index("upcoming" if name == "current" else name)
        icon = calendar.crop(cal_cell(idx)).resize((20, 20), Image.Resampling.LANCZOS)
        ui.alpha_composite(icon, (icon_x, oy + 40))
        if name == "current":
            ring = calendar.crop(cal_cell(CAL_ICONS.index("current"))).resize((24, 24), Image.Resampling.LANCZOS)
            ui.alpha_composite(ring, (icon_x - 2, oy + 38))
        icon_x += 26
    tile, kind, inset = PANEL_TILES["balance_translucent"]
    by = oy + 72
    ui.alpha_composite(stretch(panels.crop(tile), (sx1 - sx0, 50), inset), (sx0, by))
    text(d, (sx0 + 12, by + 8), "UPGRADE POINTS", 12, (255, 255, 255))
    text(d, (sx1 - 12, by + 8), "1,250", 15, (255, 214, 80), anchor="ra")
    d.rectangle((sx0 + 12, by + 32, sx1 - 12, by + 36), fill=(40, 30, 14, 255))
    d.rectangle((sx0 + 12, by + 32, sx0 + 12 + int((sx1 - sx0 - 24) * 0.42), by + 36), fill=(232, 188, 70, 255))
    # footer
    fy = UI["footer_y"]
    ribbon = stretch(panels.crop(PANEL_TILES["ribbon_translucent"][0]), (560, 18), 4)
    ui.alpha_composite(ribbon, (40, fy - 2))
    button(d, (48, fy), "A", (96, 200, 80))
    text(d, (68, fy + 7), "Select", 12, anchor="lm")
    button(d, (128, fy), "B", (220, 60, 50))
    text(d, (148, fy + 7), "Back", 12, anchor="lm")
    button(d, (200, fy), "Y", (240, 200, 60))
    text(d, (220, fy + 7), "Save", 12, anchor="lm")
    return ui


def mockup_43(apartment: Image.Image, ui: Image.Image) -> Image.Image:
    back = apartment.crop(CROP_43).resize((640, 480), Image.Resampling.BILINEAR)
    back.alpha_composite(ui)
    return back.convert("RGB")


def mockup_wide(apartment: Image.Image, ui: Image.Image) -> Image.Image:
    back = apartment.crop(CROP_WIDE).resize((854, 480), Image.Resampling.BILINEAR)
    back.alpha_composite(ui, ((854 - 640) // 2, 0))
    return back.convert("RGB")


# ----------------------------------------------------------------------------- main
def manifest() -> dict:
    return {
        "schema": "mycareer_art/v1",
        "seed": SEED,
        "ui": UI,
        "crop_43": list(CROP_43),
        "crop_wide": list(CROP_WIDE),
        "objects": {name: list(rect) for name, rect in SCENE.items() if isinstance(rect, tuple) and len(rect) == 4},
        "core_objects": list(CORE_OBJECTS),
        # Smooth regions the checker watches for quantization banding.
        "smooth_rects": {
            "sky": [SCENE["window"][0] + 2, SCENE["window"][1] + 2, SCENE["window"][2] - 2,
                    SCENE["window"][1] + int((SCENE["window"][3] - SCENE["window"][1]) * 0.55)],
            "wall": [100, 120, 240, 170],
            "floor": [60, 410, 240, 448],
        },
        "panel_tiles": {name: {"rect": list(rect), "kind": kind, "nine_slice_inset": inset}
                        for name, (rect, kind, inset) in PANEL_TILES.items()},
        "calendar": {"cell": CAL_CELL, "icons": {name: list(cal_cell(i)) for i, name in enumerate(CAL_ICONS)}},
        "focus": {"stretch_columns": [12, 116], "rim_px": 2},
    }


def build(out: Path) -> list[Path]:
    """Render every deliverable into ``out`` and return the written paths."""
    out.mkdir(parents=True, exist_ok=True)
    apartment = render_apartment()
    panels = render_panels()
    calendar = render_calendar()
    focus = render_focus()
    apartment.save(out / "mycareer_apartment.png", optimize=True)
    panels.save(out / "mycareer_panels.png", optimize=True)
    calendar.save(out / "mycareer_calendar.png", optimize=True)
    focus.save(out / "mycareer_focus.png", optimize=True)
    ui = ui_layer(panels, calendar, focus)
    mockup_43(apartment, ui).save(out / "hub_mockup_640x480.png", optimize=True)
    mockup_wide(apartment, ui).save(out / "hub_mockup_wide.png", optimize=True)
    (out / "manifest.json").write_bytes((json.dumps(manifest(), indent=2) + "\n").encode("utf-8"))
    return sorted(out.glob("*.png")) + [out / "manifest.json"]


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Render the MyCareer apartment hub art.")
    parser.add_argument("--out", type=Path, default=HERE, help="output folder (default: this folder)")
    args = parser.parse_args(argv)
    written = build(args.out.expanduser().resolve())
    print("wrote", ", ".join(p.name for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
