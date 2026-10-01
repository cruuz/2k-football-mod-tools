#!/usr/bin/env python3
"""Render docs/espn_marks/marks_preview.png from the shipped mark PNGs only (no retail or broadcast pixels).

Top: shield_espn as the retail consumers show it, reassembled through the two wrap triangles pinned in
``nfl2k5_espn_marks.SHIELD_ESPN_WRAP`` (over a dark plate and over grass). Below: the four textures as
stored, at 4x on a checkerboard.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn_marks as marks  # noqa: E402


def reassemble(texture: Image.Image, scale: float, background: tuple[int, int, int]) -> Image.Image:
    tex = np.asarray(texture.convert("RGBA")).astype(np.float64) / 255.0
    th, tw = tex.shape[:2]
    xs = [p[0] for t in marks.SHIELD_ESPN_WRAP for p in t["pos"]]
    ys = [p[1] for t in marks.SHIELD_ESPN_WRAP for p in t["pos"]]
    x0, x1, y0, y1 = min(xs) - 3, max(xs) + 3, min(ys) - 3, max(ys) + 3
    w, h = int((x1 - x0) * scale), int((y1 - y0) * scale)
    gy, gx = np.mgrid[0:h, 0:w]
    px, py = x0 + (gx + 0.5) / scale, y1 - (gy + 0.5) / scale
    out = np.zeros((h, w, 4))
    for tri in marks.SHIELD_ESPN_WRAP:
        (ax, ay), (bx, by), (cx, cy) = tri["pos"]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        l0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
        l1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
        l2 = 1 - l0 - l1
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        u = sum(l * (uv[0] + 1) / 2 * tw for l, uv in zip((l0, l1, l2), tri["uv"])) - 0.5
        v = sum(l * (uv[1] + 1) / 2 * th for l, uv in zip((l0, l1, l2), tri["uv"])) - 0.5
        ui = np.clip(np.round(u).astype(int), 0, tw - 1)
        vi = np.clip(np.round(v).astype(int), 0, th - 1)
        out[inside] = tex[vi[inside], ui[inside]]
    base = np.ones((h, w, 3)) * np.array(background) / 255.0
    rgb = base * (1 - out[..., 3:4]) + out[..., :3] * out[..., 3:4]
    return Image.fromarray((rgb * 255).round().astype(np.uint8), "RGB")


def checker(size: tuple[int, int]) -> Image.Image:
    im = Image.new("RGB", size, (96, 96, 96))
    draw = ImageDraw.Draw(im)
    for y in range(0, size[1], 16):
        for x in range(0, size[0], 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill=(128, 128, 128))
    return im


def main() -> int:
    shield = Image.open(marks.ART_DIR / "shield_espn.png")
    tiles = [reassemble(shield, 4.0, (22, 22, 28)), reassemble(shield, 4.0, (44, 92, 44))]
    stored = []
    for name, zoom in (("shield_espn", 4), ("nfl_chiclet", 4), ("z_ESPN_bug", 4), ("espnLogo1", 1)):
        art = Image.open(marks.ART_DIR / f"{name}.png").convert("RGBA")
        art = art.resize((art.width * zoom, art.height * zoom), Image.Resampling.NEAREST)
        panel = checker(art.size)
        panel.paste(art, (0, 0), art)
        stored.append(panel)
    width = max(sum(t.width for t in tiles) + 16, sum(p.width for p in stored) + 16 * (len(stored) - 1))
    height = max(t.height for t in tiles) + 16 + max(p.height for p in stored)
    sheet = Image.new("RGB", (width, height), (16, 16, 16))
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width + 16
    x, y = 0, max(t.height for t in tiles) + 16
    for panel in stored:
        sheet.paste(panel, (x, y))
        x += panel.width + 16
    out = ROOT / "docs" / "espn_marks" / "marks_preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
