#!/usr/bin/env python3
"""Beta 77 sh1: digitize the Seahawks' back wrap from a photograph of the real helmet into a small mask.

The real helmet's hawks wrap around the back: a thin white V line from each head, and a grey band between two more
white lines meeting in a lower V. The art tool cannot invent that, so this tool classifies the white lines and the grey
band in a back photograph (Riddell's authentic SpeedFlex SEA-4), registers the photo to the shell with the fitted back
camera and writes a 2-bit mask in view-plane centimetres (``data/nfl2k5_helmet_wraps/sea_wrap.png``: 0 none, 1 white,
2 grey, plus ``sea_wrap.json``). The photograph stays in private scratch; only this classification (a design shape,
no photographic pixel) is committed. ``sh1_helmet.paint_wrap`` paints it on the shell, so a Studio build needs no photo.

View plane: ``u = -x`` (the player's right is +u), ``w = y cos(el) + z sin(el)`` (cm, rest-pose head, y up, +z forward,
+x the player's left): an orthographic camera behind and above the head at elevation ``el``.

  sh1_digitize_wrap.py --photo SEA_4.png --out data/nfl2k5_helmet_wraps/sea_wrap
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

#: Back camera fitted to the silhouette of SEA-4 against the shell C export (IoU 0.964 at 30 degrees; the silhouette is
#: nearly flat between 12 and 60 degrees, the elevation is chosen by the wrap lines: see the sh1 report). Pixel size
#: of the fit: 300 x 300; the photo is scaled by 4.
CAMERA = {"elevation": 30.0, "sx": 11.0, "sy": 10.8, "tx": 150.78, "ty": 615.78, "fit_size": 300}
RES = 0.05                          # cm per mask cell
U_RANGE = (-13.0, 13.0)
W_RANGE = (28.0, 56.0)
#: Photo regions (coordinates of a 600 x 600 view of the photo) that are not wrap: the crown glare, the flag and the NFL
#: shield decals, the bumper plate and its lettering, the heads at the far left and right (the side logo paints those).
EXCLUDE_BOXES = ((215, 0, 385, 250), (100, 415, 210, 515), (390, 435, 460, 515))
REGION = ((60, 120), (540, 120), (565, 330), (525, 515), (75, 515), (35, 330))
SEEDS = ((150, 390), (450, 390), (300, 450))        # inside the grey band


def classify(photo: Path):
    rgba = np.asarray(Image.open(photo).convert("RGBA")).astype(float) / 255.0
    rgb = rgba[..., :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    chroma = rgb.max(2) - rgb.min(2)
    inside = rgba[..., 3] > 0.9
    white = inside & (lum > 0.80) & (chroma < 0.10)
    return white, inside


def _clean(mask: np.ndarray, minpx: int) -> np.ndarray:
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= minpx])


def wrap_masks(photo: Path):
    """(white lines, grey band) boolean masks in photo pixels."""
    white, inside = classify(photo)
    H = white.shape[0]
    k = H // 600

    def poly(pts):
        im = Image.new("L", (H, H), 0)
        ImageDraw.Draw(im).polygon([(x * k, y * k) for x, y in pts], fill=255)
        return np.asarray(im) > 0

    def box(b):
        m = np.zeros((H, H), bool)
        m[b[1] * k:b[3] * k, b[0] * k:b[2] * k] = True
        return m

    region = poly(REGION)
    excl = np.zeros((H, H), bool)
    for b in EXCLUDE_BOXES:
        excl |= box(b)
    excl |= np.arange(H)[:, None] > 500 * k
    # the lines run into the heads at the far left and right; they must seal the flood below, but the heads themselves
    # (columns outside 72..528) are painted by the side logo, so they are cut from the result afterwards
    lines_full = _clean(ndimage.binary_closing(white, iterations=2) & region & ~excl, 500 * (k * k) // 4)
    side_cut = (np.arange(H)[None, :] < 72 * k) | (np.arange(H)[None, :] > 528 * k)
    lines = lines_full & ~side_cut
    # the grey band is the cell between the second and third white line: flood the complement of the lines from seeds
    comp = inside & ~ndimage.binary_dilation(lines_full, iterations=3)
    lab, _ = ndimage.label(comp)
    ids = {lab[y * k, x * k] for x, y in SEEDS} - {0}
    band = np.isin(lab, list(ids)) & region
    for b in EXCLUDE_BOXES[:1]:
        band &= ~box(b)
    ys = np.arange(H)[:, None]
    low = np.where(lines_full & (ys >= 400 * k) & (ys <= 520 * k), ys, -1).max(0).astype(float)
    cols = np.nonzero(low > 0)[0]
    env = np.interp(np.arange(H), cols, low[cols])
    band &= ys <= env[None, :] + 2
    band &= np.arange(H)[None, :] > 72 * k
    band &= np.arange(H)[None, :] < 528 * k
    band = _clean(band, 3000 * (k * k) // 4)
    return lines, band


def to_view_plane(lines: np.ndarray, band: np.ndarray, camera: dict = CAMERA) -> np.ndarray:
    """2-bit mask (0 none, 1 white, 2 grey) in view-plane centimetres."""
    cols = int(round((U_RANGE[1] - U_RANGE[0]) / RES))
    rows = int(round((W_RANGE[1] - W_RANGE[0]) / RES))
    u = U_RANGE[0] + (np.arange(cols) + 0.5) * RES
    w = W_RANGE[1] - (np.arange(rows) + 0.5) * RES
    scale = lines.shape[0] / float(camera["fit_size"])
    px = (u[None, :] * camera["sx"] + camera["tx"]) * scale
    py = (-w[:, None] * camera["sy"] + camera["ty"]) * scale
    px = np.broadcast_to(px, (rows, cols))
    py = np.broadcast_to(py, (rows, cols))
    out = np.zeros((rows, cols), np.uint8)
    for value, mask in ((2, band), (1, lines)):
        f = ndimage.gaussian_filter(mask.astype(np.float32), 1.2)
        s = ndimage.map_coordinates(f, [py, px], order=1, mode="constant", cval=0.0)
        out[s > 0.5] = value
    return out


def symmetrize(mask: np.ndarray) -> tuple[np.ndarray, float]:
    """The real design is symmetric about the helmet's centre line; a photograph is not (light, a slight turn). Find the
    mirror axis (the shift of the flipped mask that overlaps the mask best), move the mask so the axis is at u = 0, and
    mirror the half with more painted cells onto the other. Returns (mask, axis offset in cm before the move)."""
    fg = mask > 0
    best, shift = -1.0, 0
    for s_ in range(-40, 41):
        flip = np.roll(fg[:, ::-1], s_, axis=1)
        iou = (fg & flip).sum() / float(max(1, (fg | flip).sum()))
        if iou > best:
            best, shift = iou, s_
    cols = mask.shape[1]
    axis = (cols - 1 + shift) / 2.0
    move = int(round((cols - 1) / 2.0 - axis))
    moved = np.roll(mask, move, axis=1)
    half = cols // 2
    left, right = moved[:, :half], moved[:, cols - half:]
    keep_left = (left > 0).sum() >= (right > 0).sum()
    out = moved.copy()
    if keep_left:
        out[:, cols - half:] = left[:, ::-1]
    else:
        out[:, :half] = right[:, ::-1]
    if cols % 2:
        out[:, half] = moved[:, half]
    return out, (axis - (cols - 1) / 2.0) * RES


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True, help="path stem: writes <stem>.png and <stem>.json")
    a = p.parse_args(argv)
    lines, band = wrap_masks(a.photo)
    mask, axis_cm = symmetrize(to_view_plane(lines, band))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, "L").save(a.out.with_suffix(".png"), optimize=True)
    meta = {"schema": "nfl2k5_helmet_wrap/v1", "team": "SEA", "camera": CAMERA, "res_cm": RES, "u_range": U_RANGE,
            "w_range": W_RANGE, "values": {"0": "none", "1": "white", "2": "grey"},
            "view_plane": "u = -x, w = y cos(el) + z sin(el), cm, rest-pose head",
            "photo_axis_offset_cm": round(axis_cm, 3), "symmetrized": "the half with more painted cells, mirrored about the helmet centre line",
            "source": "classified from Riddell authentic SpeedFlex SEA-4 (back view); only the classification is kept"}
    a.out.with_suffix(".json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"white_cells": int((mask == 1).sum()), "grey_cells": int((mask == 2).sum()),
                      "size": list(mask.shape)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
