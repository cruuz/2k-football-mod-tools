#!/usr/bin/env python3
"""Build the MyCareer apartment hub art (Fable, 2026-09-07).

Two kinds of output live here:

* Authored atlases, drawn by this script from scratch and committed:
  ``mycareer_panels.png`` (256x128), ``mycareer_calendar.png`` (128x128) and
  ``mycareer_focus.png`` (128x32).
* The backdrop ``mycareer_apartment.png`` (512x512), which is a real ESPN NFL
  2K5 texture, the skyline the Crib's windows look out on, recomposed for the
  hub slot from a recipe (``backdrop_recipe.json``). It is decoded from the
  user's own disc through the Studio's private source cache and the Crib
  catalog at build time, and it is never committed: this repository carries no
  retail pixels, only the recipe. The two hub mockups are composed on top of it
  and are equally local.

Run ``python3 docs/mycareer_art/build.py`` to render the atlases, compose the
backdrop and the mockups (when the source cache is present), and write
``manifest.json`` for ``tools/mycareer_art_check.py``. Pass ``--recipe`` to
compose an alternate recipe, ``--out`` to write elsewhere.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SEED = 20260907
DEFAULT_RECIPE = HERE / "backdrop_recipe.json"

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


class BuildError(ValueError):
    """A plain, actionable build problem."""


# ----------------------------------------------------------------------------- helpers
class Layer:
    """An RGBA layer drawn at 2x or 4x and reduced with a box filter."""

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
        self.d.rounded_rectangle(self.box(b), radius=r * self.s, fill=fill, outline=outline,
                                 width=max(1, int(round(width * self.s))))

    def ellipse(self, b, fill, outline=None, width=1):
        self.d.ellipse(self.box(b), fill=fill, outline=outline, width=max(1, int(round(width * self.s))))

    def poly(self, pts, fill, outline=None, width=1):
        self.d.polygon(self.p(pts), fill=fill, outline=outline,
                       width=max(1, int(round(width * self.s))) if outline else 0)

    def line(self, pts, fill, width=1):
        self.d.line(self.p(pts), fill=fill, width=max(1, int(width * self.s)))

    def reduced(self) -> Image.Image:
        w, h = self.im.size
        return self.im.resize((w // self.s, h // self.s), Image.Resampling.BOX)


# ----------------------------------------------------------------------------- source cache
def find_source_cache_root() -> Path | None:
    """The Studio's private cache for this user's disc, or None when absent."""
    from mod_editor.core.nfl2k5_source_cache import default_cache_root
    override = os.environ.get("NFL2K5_SOURCE_CACHE_ROOT")
    base = Path(override).expanduser() if override else default_cache_root()
    if (base / "cache.json").is_file():
        return base
    if not base.is_dir():
        return None
    roots = sorted(path for path in base.iterdir() if (path / "cache.json").is_file())
    return roots[0] if roots else None


def open_source_cache(root: Path):
    """Bind the existing cache without re-hashing the disc image.

    The Studio builds this record after inspecting the XISO; here the marker it
    wrote is enough, because every original the Crib IO hands back is verified
    against the catalog's pinned pixel hashes anyway.
    """
    from mod_editor.core.model import SourceRecord
    from mod_editor.core.nfl2k5_source_cache import (
        CACHE_SCHEMA, INVENTORY_RELATIVE, PACK_FOLDER, SourceCache)
    marker = json.loads((root / "cache.json").read_text(encoding="utf-8"))
    if marker.get("schema") != CACHE_SCHEMA:
        raise BuildError(f"{root / 'cache.json'} is not a {CACHE_SCHEMA} marker")
    source = marker.get("source") or {}
    record = SourceRecord(selected_path="", inspected_path="", kind="xiso",
                          sha256=str(source.get("sha256", "")), size=int(source.get("size", 0)),
                          recognized=True, fingerprint_id=None, detected_game="nfl2k5")
    summary = marker.get("summary", {})
    counts = summary.get("resource_kind_counts", {})
    originals = root / "originals"
    originals.mkdir(exist_ok=True)
    return SourceCache(source=record, root=root, pack0=root / PACK_FOLDER / "0",
                       inventory=root / INVENTORY_RELATIVE, originals=originals,
                       resource_count=int(summary.get("resource_chunk_count", 0)),
                       outer_entry_count=int(summary.get("outer_entry_count", 0)),
                       kind_counts={str(k): int(v) for k, v in counts.items()})


class CribAssets:
    """Decode catalogued Crib textures through the repo's own verified path."""

    def __init__(self, root: Path):
        from mod_editor.core.nfl2k5_crib import Nfl2k5CribIO, load_nfl2k5_crib_catalog
        self.catalog = load_nfl2k5_crib_catalog()
        self.io = Nfl2k5CribIO(open_source_cache(root), self.catalog)

    def rgba(self, selector: str, asset_id: str) -> np.ndarray:
        asset = self.catalog.by_selector(selector)
        if asset.asset_id != asset_id:
            raise BuildError(f"{selector} is {asset.asset_id} in the catalog, the recipe says {asset_id}")
        path = self.io.ensure_original(asset)
        with Image.open(path) as image:
            arr = np.asarray(image.convert("RGBA")).copy()
        if arr.shape[:2] != (asset.height, asset.width):
            raise BuildError(f"{selector} decoded as {arr.shape[1]}x{arr.shape[0]}, expected {asset.width}x{asset.height}")
        return arr


# ----------------------------------------------------------------------------- backdrop recipe
def load_recipe(path: Path) -> dict:
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if recipe.get("schema") != "mycareer_backdrop_recipe/v1":
        raise BuildError(f"{path} is not a mycareer_backdrop_recipe/v1 file")
    if tuple(recipe.get("canvas", ())) != (512, 512):
        raise BuildError("the backdrop recipe must target the 512x512 slot")
    if not recipe.get("layers"):
        raise BuildError("the backdrop recipe has no layers")
    return recipe


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def nine_slice(src: np.ndarray, size: tuple[int, int], inset: int, border_only: bool = False) -> np.ndarray:
    """Stretch a tile to size keeping its corners and edge bands; border_only leaves the centre clear."""
    src_im = Image.fromarray(src, "RGBA")
    w, h = src_im.size
    tw, th = size
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    xs = [(0, inset, 0, inset), (inset, w - inset, inset, tw - inset), (w - inset, w, tw - inset, tw)]
    ys = [(0, inset, 0, inset), (inset, h - inset, inset, th - inset), (h - inset, h, th - inset, th)]
    for ix, (sx0, sx1, dx0, dx1) in enumerate(xs):
        for iy, (sy0, sy1, dy0, dy1) in enumerate(ys):
            if border_only and ix == 1 and iy == 1:
                continue
            piece = src_im.crop((sx0, sy0, sx1, sy1))
            target = (max(1, dx1 - dx0), max(1, dy1 - dy0))
            if piece.size != target:
                piece = piece.resize(target, Image.Resampling.BILINEAR)
            out.paste(piece, (dx0, dy0))
    return np.asarray(out).copy()


def place_layer(canvas: np.ndarray, layer: dict, assets: CribAssets, rng: np.random.Generator) -> dict:
    """Composite one recipe layer; returns the provenance record for the manifest."""
    src = assets.rgba(layer["selector"], layer["asset_id"])
    x0, y0, x1, y1 = layer["rect"]
    w, h = x1 - x0, y1 - y0
    fit = layer.get("fit", "exact")
    if fit == "exact":
        if src.shape[1] != w or src.shape[0] != h:
            raise BuildError(f"{layer['selector']} is {src.shape[1]}x{src.shape[0]}; rect {layer['rect']} needs fit 'scale', 'tile' or 'nine_slice'")
        block = src
    elif fit == "scale":
        block = np.asarray(Image.fromarray(src, "RGBA").resize((w, h), Image.Resampling.LANCZOS)).copy()
    elif fit == "tile":
        reps = (h // src.shape[0] + 1, w // src.shape[1] + 1, 1)
        block = np.tile(src, reps)[:h, :w]
    elif fit == "nine_slice":
        block = nine_slice(src, (w, h), int(layer.get("inset", 16)), bool(layer.get("border_only", False)))
    else:
        raise BuildError(f"unknown layer fit {fit!r}")
    block = block.astype(np.float32)
    tint = layer.get("tint")
    if tint:
        block[..., :3] *= np.asarray(tint, np.float32)[None, None, :]
    if layer.get("crop_alpha_to_rect"):
        block[..., 3] = 255
    alpha = (block[..., 3:4] / 255.0) * float(layer.get("opacity", 1.0))
    region = canvas[y0:y1, x0:x1, :3]
    canvas[y0:y1, x0:x1, :3] = region * (1 - alpha) + np.clip(block[..., :3], 0, 255) * alpha
    extend = layer.get("extend")
    if extend:
        extend_rows(canvas, (x0, y0, x1, y1), extend, rng)
    return {"selector": layer["selector"], "asset_id": layer["asset_id"], "rect": [x0, y0, x1, y1], "fit": fit,
            "source_size": [int(src.shape[1]), int(src.shape[0])]}


def _edge_row(canvas: np.ndarray, rows: slice, x0: int, x1: int, blur: int) -> np.ndarray:
    """Mean of a few edge rows, smoothed along x so the continuation has no column streaks."""
    edge = canvas[rows, x0:x1, :3].mean(axis=0)
    if blur > 1:
        kernel = np.ones(blur, np.float32) / blur
        pad = blur // 2
        padded = np.pad(edge, ((pad, pad), (0, 0)), mode="edge")
        edge = np.stack([np.convolve(padded[:, c], kernel, mode="valid") for c in range(3)], axis=1)
    return edge[None, :, :]


def extend_rows(canvas: np.ndarray, rect, extend: dict, rng: np.random.Generator) -> None:
    """Continue an image above and below its rect: its smoothed edge rows, eased to a dark tone.

    The sky above keeps easing over the whole extension (it simply gets darker
    upward). Below, the city's edge is blurred along x and reaches the dark tone
    within `fade_rows`, so the band under the window reads as shadow, not smear.
    """
    x0, y0, x1, y1 = rect
    fade_to = np.asarray(extend.get("fade_to", [4, 4, 10]), np.float32)
    strength = float(extend.get("strength", 0.85))
    grain = float(extend.get("grain", 2.0))
    blur = int(extend.get("blur", 33))
    top, bottom = int(extend.get("top", 0)), int(extend.get("bottom", 0))
    if top:
        edge = _edge_row(canvas, slice(y0, y0 + 3), x0, x1, blur)
        t = smoothstep((np.arange(top)[::-1] + 1) / top)[:, None, None] * strength
        rows = edge * (1 - t) + fade_to[None, None, :] * t
        rows += rng.normal(0.0, grain, size=rows.shape)
        canvas[y0 - top:y0, x0:x1, :3] = np.clip(rows, 0, 255)
    if bottom:
        edge = _edge_row(canvas, slice(y1 - 3, y1), x0, x1, blur)
        fade_rows = min(bottom, int(extend.get("fade_rows", 40)))
        t = smoothstep((np.arange(bottom) + 1) / fade_rows)[:, None, None]
        rows = edge * (1 - t) + fade_to[None, None, :] * t
        rows += rng.normal(0.0, grain, size=rows.shape)
        canvas[y1:y1 + bottom, x0:x1, :3] = np.clip(rows, 0, 255)


def apply_shade(canvas: np.ndarray, shade: dict) -> None:
    """Hold the menu column in shadow: a horizontal ease from `min` at the left edge to 1 at `to_x`."""
    xx = np.arange(canvas.shape[1], dtype=np.float32)
    t = smoothstep((xx - float(shade.get("from_x", 0))) / max(1.0, float(shade["to_x"]) - float(shade.get("from_x", 0))))
    t = t ** float(shade.get("power", 1.0))
    factor = float(shade["min"]) + (1.0 - float(shade["min"])) * t
    canvas[..., :3] *= factor[None, :, None]
    top = shade.get("top")
    if top:
        yy = np.arange(canvas.shape[0], dtype=np.float32)
        tf = float(top["min"]) + (1.0 - float(top["min"])) * smoothstep(yy / float(top["to_y"]))
        canvas[..., :3] *= tf[:, None, None]


def compose_backdrop(recipe: dict, assets: CribAssets) -> tuple[Image.Image, dict]:
    rng = np.random.default_rng(int(recipe.get("seed", SEED)))
    w, h = recipe["canvas"]
    canvas = np.zeros((h, w, 4), np.float32)
    canvas[..., :3] = np.asarray(recipe.get("background", [6, 6, 12]), np.float32)[None, None, :]
    canvas[..., 3] = 255
    provenance = [place_layer(canvas, layer, assets, rng) for layer in recipe["layers"]]
    if recipe.get("shade"):
        apply_shade(canvas, recipe["shade"])
    grain = recipe.get("grain", {})
    if grain.get("sigma"):
        canvas[..., :3] += rng.normal(0.0, float(grain["sigma"]), size=(h, w, 1))
    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    canvas[..., 3] = 255
    return Image.fromarray(canvas, "RGBA"), {"recipe": recipe.get("name"), "layers": provenance,
                                             "shade": recipe.get("shade"), "grain": grain}


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
    band = np.exp(-((np.arange(h) - h / 2) / 7.0) ** 2)[:, None, None]
    fill = fill + band * np.array([30, 24, 16], np.float32)
    arr[..., :3] = fill
    arr[..., 3] = 255
    arr[: h // 3, :, :3] = np.clip(arr[: h // 3, :, :3] + 22, 0, 255)
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
    return Image.fromarray(nine_slice(np.asarray(tile.convert("RGBA")).copy(), size, inset), "RGBA")


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
    text(d, (44, 34), "MYCAREER", 30)
    text(d, (46, 70), "THE APARTMENT", 13, (255, 214, 80))
    d.rectangle((44, 92, 596, 93), fill=(214, 66, 30, 255))
    d.rectangle((44, 94, 596, 94), fill=(255, 255, 255, 90))
    text(d, (596, 70), "WEEK 3   PRESEASON", 13, (220, 220, 230), anchor="ra")
    mx0, my0, mx1, _ = UI["menu"]
    rh = UI["row_height"]
    ui.alpha_composite(focus.resize((mx1 - mx0, rh), Image.Resampling.BILINEAR), (mx0, my0))
    for i, label in enumerate(ROWS):
        y = my0 + i * rh
        colour = (255, 255, 255) if i == 0 else (222, 226, 236)
        text(d, (mx0 + 10, y + rh // 2), label, 15, colour, anchor="lm")
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


# ----------------------------------------------------------------------------- manifest + main
def manifest(recipe: dict, provenance: dict | None) -> dict:
    layers = recipe["layers"]
    objects = {f"layer_{i}_{layer['selector'].split(':')[-2]}": list(layer["rect"]) for i, layer in enumerate(layers)}
    core = [name for name, layer in zip(objects, layers) if layer.get("core", True)]
    return {
        "schema": "mycareer_art/v1",
        "seed": SEED,
        "ui": UI,
        "crop_43": list(CROP_43),
        "crop_wide": list(CROP_WIDE),
        "objects": objects,
        "core_objects": core,
        "smooth_rects": recipe.get("smooth_rects", {}),
        "backdrop": {
            "recipe": recipe.get("name"),
            "retail_pixels_committed": False,
            "provenance": provenance,
            "note": recipe.get("note", ""),
        },
        "panel_tiles": {name: {"rect": list(rect), "kind": kind, "nine_slice_inset": inset}
                        for name, (rect, kind, inset) in PANEL_TILES.items()},
        "calendar": {"cell": CAL_CELL, "icons": {name: list(cal_cell(i)) for i, name in enumerate(CAL_ICONS)}},
        "focus": {"stretch_columns": [12, 116], "rim_px": 2},
    }


def build(out: Path, recipe_path: Path = DEFAULT_RECIPE, *, require_backdrop: bool = False,
          mockup_prefix: str = "hub_mockup") -> list[Path]:
    """Render the atlases, compose the backdrop and mockups when the cache exists, write the manifest."""
    out.mkdir(parents=True, exist_ok=True)
    recipe = load_recipe(recipe_path)
    panels = render_panels()
    calendar = render_calendar()
    focus = render_focus()
    panels.save(out / "mycareer_panels.png", optimize=True)
    calendar.save(out / "mycareer_calendar.png", optimize=True)
    focus.save(out / "mycareer_focus.png", optimize=True)
    written = [out / "mycareer_panels.png", out / "mycareer_calendar.png", out / "mycareer_focus.png"]
    provenance = None
    root = find_source_cache_root()
    if root is None:
        message = ("no NFL 2K5 source cache on this machine: the backdrop and mockups are composed from "
                   "your own disc; open the XISO in Mod Studio once, or set NFL2K5_SOURCE_CACHE_ROOT")
        if require_backdrop:
            raise BuildError(message)
        print("note:", message)
    else:
        backdrop, provenance = compose_backdrop(recipe, CribAssets(root))
        backdrop.save(out / "mycareer_apartment.png", optimize=True)
        ui = ui_layer(panels, calendar, focus)
        mockup_43(backdrop, ui).save(out / f"{mockup_prefix}_640x480.png", optimize=True)
        mockup_wide(backdrop, ui).save(out / f"{mockup_prefix}_wide.png", optimize=True)
        written += [out / "mycareer_apartment.png", out / f"{mockup_prefix}_640x480.png", out / f"{mockup_prefix}_wide.png"]
    (out / "manifest.json").write_bytes((json.dumps(manifest(recipe, provenance), indent=2) + "\n").encode("utf-8"))
    return written + [out / "manifest.json"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the MyCareer apartment hub art.")
    parser.add_argument("--out", type=Path, default=HERE, help="output folder (default: this folder)")
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE, help="backdrop recipe JSON")
    parser.add_argument("--mockup-prefix", default="hub_mockup", help="file stem for the two mockups")
    parser.add_argument("--require-backdrop", action="store_true", help="fail when the source cache is absent")
    args = parser.parse_args(argv)
    try:
        written = build(args.out.expanduser().resolve(), args.recipe.expanduser().resolve(),
                        require_backdrop=args.require_backdrop, mockup_prefix=args.mockup_prefix)
    except BuildError as exc:
        print("error:", exc, file=sys.stderr)
        return 1
    print("wrote", ", ".join(p.name for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
