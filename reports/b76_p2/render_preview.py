#!/usr/bin/env python3
"""Beta 76 p2: draw docs/espn_wipes_boards/preview.png from the shipped PNGs only.

The shipped textures are drawn through the retail triangles (positions and UVs read from an extracted retail
``vc_53450030`` folder, geometry only; bind pose, orthographic, nearest texel) and laid out beside the textures
themselves. No retail pixel and no broadcast frame is drawn.

    python3 reports/b76_p2/render_preview.py --packs <extracted vc_53450030> [--output docs/espn_wipes_boards/preview.png]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for extra in (ROOT, ROOT / "tools", HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import author_wipes_boards as author  # noqa: E402

ART = ROOT / "data" / "nfl2k5_espn_wipes_boards"
# the replay wipe's material colours (material +0x18, RGB; numbers read from the retail scene, no pixels)
REPLAY_TINTS = {"b_yellow_streak01": (1.0, 0.239, 0.0), "cruve_rays": (0.933, 0.867, 0.396),
                "top_rays": (1.0, 0.518, 0.122), "crescent01": (0.965, 0.761, 0.11),
                "crescent02": (0.89, 0.388, 0.098), "crescent03": (1.0, 0.478, 0.129)}


def load(name: str) -> np.ndarray:
    return np.asarray(Image.open(ART / f"{name}.png").convert("RGBA")).astype(np.float64) / 255.0


def draw(tris: list[dict], textures: dict[int, np.ndarray], size: int, *, tints=None, background=(20, 20, 26),
         depth_first=True) -> Image.Image:
    pts = np.array([p[:2] for t in tris for p in t["pos"]])
    lo, hi = pts.min(0), pts.max(0)
    span = (hi - lo).max() * 1.04
    centre = (lo + hi) / 2
    img = np.zeros((size, size, 3))
    img[:] = np.array(background) / 255.0
    order = sorted(tris, key=lambda t: sum(p[2] for p in t["pos"]), reverse=not depth_first)
    for tri in order:
        xy = np.array([((p[0] - centre[0]) / span * size + size / 2, size / 2 - (p[1] - centre[1]) / span * size)
                       for p in tri["pos"]])
        x0, y0 = np.maximum(np.floor(xy.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(xy.max(0)).astype(int), size - 1)
        if x1 < x0 or y1 < y0 or tri["texture"] is None or tri["texture"] not in textures:
            continue
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        lam = author.barycentric(np.stack([xs + 0.5, ys + 0.5], -1), [tuple(v) for v in xy])
        inside = lam.min(-1) >= 0
        if not inside.any():
            continue
        tex = textures[tri["texture"]]
        th, tw = tex.shape[:2]
        u = sum(lam[..., i] * tri["uv"][i][0] for i in range(3))
        v = sum(lam[..., i] * tri["uv"][i][1] for i in range(3))
        sample = tex[np.mod(np.floor(v * th).astype(int), th), np.mod(np.floor(u * tw).astype(int), tw)]
        tint = np.array((tints or {}).get(tri["material"], (1.0, 1.0, 1.0)))
        alpha = sample[..., 3] * inside
        region = img[y0:y1 + 1, x0:x1 + 1]
        region[:] = region * (1 - alpha[..., None]) + sample[..., :3] * tint * alpha[..., None]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def checker(width: int, height: int, cell: int = 8) -> Image.Image:
    yy, xx = np.mgrid[0:height, 0:width]
    tone = np.where(((xx // cell) + (yy // cell)) % 2 == 0, 90, 130).astype(np.uint8)
    return Image.fromarray(np.stack([tone, tone, tone], -1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--packs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "espn_wipes_boards" / "preview.png")
    args = parser.parse_args()
    board = author.triangles(author.load_scene(args.packs, 347, 5))
    board_img = draw(board, {0: load("scoreboard_sign02"), 1: load("scoreboard_dot"), 2: load("scoreboard_sign01"),
                             3: load("scoreboard_backboard01")}, 640)
    flashy = [t for t in author.triangles(author.load_scene(args.packs, 3114, 4)) if t["material"] == "logo1"]
    flashy_img = draw(flashy, {0: load("redflashy_logo1")}, 320, background=(12, 11, 16))
    replay = author.triangles(author.load_scene(args.packs, 3114, 1))
    layers = [t for t in replay if t["texture"] is not None]
    replay_img = draw(layers, {0: load("replay_wipe_pattern_flash"), 1: load("replay_wipe_streaks"),
                               2: load("replay_wipe_logo_glow"), 3: load("replay_wipe_rays")}, 320, tints=REPLAY_TINTS)
    sheet = Image.new("RGB", (1280, 900), (16, 16, 20))
    sheet.paste(board_img, (0, 0))
    sheet.paste(flashy_img, (640, 0))
    sheet.paste(replay_img, (960, 0))
    names = [name for name, _o, _c, _i in author.TARGETS]
    x, y = 640, 330
    for name in names:
        tex = Image.open(ART / f"{name}.png").convert("RGBA")
        scale = min(150 / tex.width, 130 / tex.height)
        tile = tex.resize((max(1, int(tex.width * scale)), max(1, int(tex.height * scale))), Image.Resampling.NEAREST)
        back = checker(tile.width, tile.height).convert("RGBA")
        back.alpha_composite(tile)
        if x + 158 > 1280:
            y += 142
            x = 640 if y + 130 < 640 else 0
        sheet.paste(back.convert("RGB"), (x, y))
        x += 158
    d = ImageDraw.Draw(sheet)
    d.text((6, 6), "pause scoreboard (shipped textures through the retail triangles)", fill=(255, 220, 0))
    d.text((646, 6), "RedFlashy logo1 through its quads", fill=(255, 220, 0))
    d.text((966, 6), "replay wipe texture layers", fill=(255, 220, 0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
