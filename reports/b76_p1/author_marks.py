#!/usr/bin/env python3
"""Beta 76 p1: author the two re-graded ESPN presentation marks from 2026 broadcast stills.

Maintainer evidence script, not shipped. It reproduces ``data/nfl2k5_espn_marks/shield_espn.png``
and ``data/nfl2k5_espn_marks/nfl_chiclet.png`` byte for byte on the machine that made them, from
two private inputs that never enter the repository:

  --frames   the folder holding ``mnf/frames/frame_NNNNNN.png`` (the 2026 Giants at Rams highlights,
             every 30th frame) and ``obs/frames/frame_NNNNNN.png`` (the off-air recording, 2 fps)
  --pack0    an extracted retail ``vc_53450030/0`` (its sibling packs beside it), read for geometry
             only: the score_bug scene's ESPN mark triangles and the retail logo's display ellipse

Sources. The 2026 replay transition is the ESPN MNF shield stinger (red ESPN wordmark on black, a
silver MNF band, a flat NFL shield). It is at full size in five stills: mnf 87 and obs 327, 681,
2350, 2538. Each obs frame is registered onto mnf 87 (template match on the NFL shield over scales
0.70 to 1.50, then an ECC affine refinement over the shield body) and the five are median-combined.

shield_espn (128x64). The retail texture is a two-row wrap: every consumer (the score_bug bar, the
replay overlay chunks 64 and 65, the voice_of and weather_3row overlays) draws it with the same two
slanted triangles, so a picture painted straight across the texture tears. The red wordmark is
segmented from the median (redness = R - max(G, B), silhouette at half the letter level after an 8x
Lanczos upsample), placed at the centre of the retail logo's display ellipse at 94 percent of the
largest width that fits inside it, and every texel is inverse-mapped through the triangle that owns
its UV (4x4 supersampling). Colour: the median letter red. Alpha: 32 levels.

nfl_chiclet (64x64). The flat NFL shield is segmented from the stinger's black plate (flood fill of
the dark border, holes filled), area-resampled onto the retail shield footprint (9,2)-(55,63) and
composited on eight radial bands of the shield's own navy (the beta 72 plate rule); 48 colours.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
try:  # maintainer-only evidence tools; the studio runtime never imports this script
    import cv2
    from scipy import ndimage
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"author_marks.py needs opencv-python and scipy: {exc}")

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

STINGER = (("mnf", 87), ("obs", 327), ("obs", 681), ("obs", 2350), ("obs", 2538))
NFL_TEMPLATE = (890, 635, 140, 185)          # x, y, w, h of the NFL shield in mnf frame_000087
ECC_REGION = (700, 240, 1220, 820)           # shield body in mnf frame_000087 coordinates
ESPN_REGION = (760, 250, 1170, 370)          # the red wordmark
NFL_REGION = (875, 620, 1045, 835)           # the NFL shield
CHICLET_FOOTPRINT = (9, 2, 55, 63)
SS = 8


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def register(frames: Path) -> tuple[np.ndarray, dict]:
    ref = cv2.imread(str(frames / "mnf/frames/frame_000087.png"))
    if ref is None:
        raise SystemExit("mnf/frames/frame_000087.png is missing under --frames")
    refg = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
    x, y, w, h = NFL_TEMPLATE
    tpl = ref[y:y + h, x:x + w]
    x0, y0, x1, y1 = ECC_REGION
    mask = np.zeros(refg.shape, np.uint8)
    mask[y0:y1, x0:x1] = 1
    warped, report = [], {}
    for source, index in STINGER:
        name = f"{source}/frames/frame_{index:06d}.png"
        image = cv2.imread(str(frames / name))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        best = None
        for scale in np.linspace(0.7, 1.5, 81):
            t = cv2.resize(tpl, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
            _, peak, _, loc = cv2.minMaxLoc(cv2.matchTemplate(image, t, cv2.TM_CCOEFF_NORMED))
            if best is None or peak > best[0]:
                best = (peak, scale, loc)
        peak, scale, (lx, ly) = best
        warp = np.array([[scale, 0, lx - scale * x], [0, scale, ly - scale * y]], np.float32)
        cc, warp = cv2.findTransformECC(refg, gray, warp, cv2.MOTION_AFFINE,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), mask, 5)
        warped.append(cv2.warpAffine(image, warp, (ref.shape[1], ref.shape[0]),
                                     flags=cv2.INTER_CUBIC + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE))
        report[name] = dict(match=round(float(peak), 4), scale=round(float(scale), 4), ecc=round(float(cc), 4),
                            warp=[[round(float(v), 5) for v in row] for row in warp])
    median = np.median(np.stack(warped).astype(np.float32), axis=0).astype(np.uint8)
    return cv2.cvtColor(median, cv2.COLOR_BGR2RGB), report


def wrap_geometry(pack0: Path) -> tuple[list[dict], dict]:
    """The score_bug white-layer mark triangles and the retail logo's display ellipse (geometry only)."""

    import nfl2k5_scorebug_layout as layout
    from nfl_outer import parse_archive, read_entry_bytes
    from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
    archive = parse_archive(pack0)
    data = read_entry_bytes(archive, archive.entries[346])
    chunks = parse_chunks(data, allow_trailing=True)
    scene, _ = decode_chunk(data, chunks[78])
    mesh = layout.Mesh(scene)
    tris = []
    for k, indices in layout.strips(scene):
        if layout.SUBMESHES[k][2] != "zz_ESPN_bug":
            continue
        for i in range(len(indices) - 2):
            a, b, c = indices[i:i + 3]
            if len({a, b, c}) == 3 and a >= 268:            # the white layer (the shadow layer is 262..267)
                tris.append(dict(v=[a, b, c], pos=[mesh.pos[v][:2] for v in (a, b, c)],
                                 uv=[mesh.uv[v] for v in (a, b, c)]))
    decoded, _ = decode_chunk(data, chunks[26])
    info = parse_texture(decoded, chunks[26])
    alpha = np.frombuffer(texture_to_rgba(decoded, chunks[26], info), np.uint8).reshape(info.height, info.width, 4)
    alpha = alpha[..., 3].astype(np.float64) / 255.0
    scale = 8.0
    xs = [p[0] for t in tris for p in t["pos"]]
    ys = [p[1] for t in tris for p in t["pos"]]
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = int(np.ceil((X1 - X0) * scale)), int(np.ceil((Y1 - Y0) * scale))
    gy, gx = np.mgrid[0:H, 0:W]
    px, py = X0 + (gx + 0.5) / scale, Y1 - (gy + 0.5) / scale
    shown = np.zeros((H, W))
    for t in tris:
        uv = [((u + 1) / 2 * info.width, (v + 1) / 2 * info.height) for u, v in t["uv"]]
        M = affine(t["pos"], uv)
        inside = barycentric(np.stack([px, py], -1), t["pos"]).min(-1) >= 0
        u = px * M[0, 0] + py * M[1, 0] + M[2, 0]
        v = px * M[0, 1] + py * M[1, 1] + M[2, 1]
        ui = np.clip(np.floor(u).astype(int), 0, info.width - 1)
        vi = np.clip(np.floor(v).astype(int), 0, info.height - 1)
        shown[inside] = alpha[vi[inside], ui[inside]]
    yy, xx = np.nonzero(shown > 0.5)
    ux, uy = X0 + (xx + 0.5) / scale, Y1 - (yy + 0.5) / scale
    cx, cy = ux.mean(), uy.mean()
    evals, _ = np.linalg.eigh(np.cov(np.stack([ux - cx, uy - cy])))
    ellipse = dict(centre=[round(float(cx), 3), round(float(cy), 3)],
                   semi_axes=[round(float(2 * np.sqrt(evals[1])), 3), round(float(2 * np.sqrt(evals[0])), 3)],
                   bbox=[round(float(ux.min()), 2), round(float(uy.min()), 2),
                         round(float(ux.max()), 2), round(float(uy.max()), 2)])
    return tris, ellipse


def affine(src, dst) -> np.ndarray:
    A = np.array([[p[0], p[1], 1.0] for p in src])
    return np.linalg.solve(A, np.array(dst, dtype=np.float64))


def barycentric(points: np.ndarray, tri) -> np.ndarray:
    (x0, y0), (x1, y1), (x2, y2) = tri
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    l0 = ((y1 - y2) * (points[..., 0] - x2) + (x2 - x1) * (points[..., 1] - y2)) / d
    l1 = ((y2 - y0) * (points[..., 0] - x2) + (x0 - x2) * (points[..., 1] - y2)) / d
    return np.stack([l0, l1, 1 - l0 - l1], -1)


def bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x0 = np.clip(np.floor(x).astype(int), 0, img.shape[1] - 1)
    y0 = np.clip(np.floor(y).astype(int), 0, img.shape[0] - 1)
    x1, y1 = np.clip(x0 + 1, 0, img.shape[1] - 1), np.clip(y0 + 1, 0, img.shape[0] - 1)
    fx, fy = np.clip(x - x0, 0, 1), np.clip(y - y0, 0, 1)
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def author_shield_espn(median: np.ndarray, tris: list[dict], ellipse: dict) -> tuple[np.ndarray, dict]:
    x0, y0, x1, y1 = ESPN_REGION
    rgb = median[y0:y1, x0:x1].astype(np.float64)
    red = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
    core = red > 0.5 * np.percentile(red, 99)
    level = float(np.median(red[core]))
    hi = np.asarray(Image.fromarray(np.clip(red / level * 255, 0, 255).astype(np.uint8)).resize(
        (red.shape[1] * SS, red.shape[0] * SS), Image.Resampling.LANCZOS)).astype(np.float64) / 255.0
    mark = hi > 0.5
    ys, xs = np.nonzero(mark)
    mark = mark[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    aspect = mark.shape[1] / mark.shape[0]
    colour = np.median(rgb[core], axis=0)
    cx, cy = ellipse["centre"]
    ea, eb = ellipse["semi_axes"]
    my, mx = np.nonzero(mark[::4, ::4])

    def fits(width: float) -> bool:
        height = width / aspect
        px = cx - width / 2 + (mx * 4 + 2) / mark.shape[1] * width
        py = cy + height / 2 - (my * 4 + 2) / mark.shape[0] * height
        return bool((((px - cx) / ea) ** 2 + ((py - cy) / eb) ** 2 <= 1.0).all())
    lo, hi_w = 10.0, 2 * ea
    for _ in range(40):
        mid = (lo + hi_w) / 2
        lo, hi_w = (mid, hi_w) if fits(mid) else (lo, mid)
    width = lo * 0.94
    height = width / aspect
    S = 16.0
    xs_all = [p[0] for t in tris for p in t["pos"]]
    ys_all = [p[1] for t in tris for p in t["pos"]]
    X0, X1, Y0, Y1 = min(xs_all), max(xs_all), min(ys_all), max(ys_all)
    DW, DH = int(np.ceil((X1 - X0) * S)), int(np.ceil((Y1 - Y0) * S))
    left, top = int(round((cx - width / 2 - X0) * S)), int(round((Y1 - (cy + height / 2)) * S))
    mw, mh = int(round(width * S)), int(round(height * S))
    cover = np.asarray(Image.fromarray((mark * 255).astype(np.uint8)).resize((mw * 4, mh * 4), Image.Resampling.NEAREST)
                       .resize((mw, mh), Image.Resampling.BOX)).astype(np.float64) / 255.0
    shown = np.zeros((DH, DW))
    shown[top:top + mh, left:left + mw] = cover
    TW, TH, N = 128, 64, 4
    uvpix = [[((u + 1) / 2 * TW, (v + 1) / 2 * TH) for u, v in t["uv"]] for t in tris]
    maps = [affine(uvpix[i], tris[i]["pos"]) for i in range(len(tris))]
    sy, sx = np.mgrid[0:TH * N, 0:TW * N]
    P = np.stack([(sx + 0.5) / N, (sy + 0.5) / N], -1)
    score = np.stack([barycentric(P, uvpix[i]).min(-1) for i in range(len(tris))], 0)
    owner = score.argmax(0)
    screen_x, screen_y = np.zeros(P.shape[:2]), np.zeros(P.shape[:2])
    for i, M in enumerate(maps):
        sel = owner == i
        screen_x[sel] = P[sel][:, 0] * M[0, 0] + P[sel][:, 1] * M[1, 0] + M[2, 0]
        screen_y[sel] = P[sel][:, 0] * M[0, 1] + P[sel][:, 1] * M[1, 1] + M[2, 1]
    dx, dy = (screen_x - X0) * S - 0.5, (Y1 - screen_y) * S - 0.5
    outside = (dx < 0) | (dy < 0) | (dx > DW - 1) | (dy > DH - 1)
    samples = np.where(outside, 0.0, bilinear(shown, dx, dy))
    alpha = samples.reshape(TH, N, TW, N).mean(axis=(1, 3))
    levels = 32
    out = np.zeros((TH, TW, 4), np.uint8)
    out[..., :3] = np.round(colour).astype(np.uint8)
    out[..., 3] = np.round(np.round(np.clip(alpha, 0, 1) * (levels - 1)) / (levels - 1) * 255).astype(np.uint8)
    # forward check: the stored texture reassembled through the same triangles against the intended mark
    gy, gx = np.mgrid[0:DH, 0:DW]
    px, py = X0 + (gx + 0.5) / S, Y1 - (gy + 0.5) / S
    back, covered = np.zeros((DH, DW)), np.zeros((DH, DW), bool)
    stored = out[..., 3].astype(np.float64) / 255.0
    for i, t in enumerate(tris):
        M = affine(t["pos"], uvpix[i])
        inside = barycentric(np.stack([px, py], -1), t["pos"]).min(-1) >= 0
        u = px * M[0, 0] + py * M[1, 0] + M[2, 0] - 0.5
        v = px * M[0, 1] + py * M[1, 1] + M[2, 1] - 0.5
        back[inside] = bilinear(stored, u, v)[inside]
        covered |= inside
    iou = float(((back > 0.5) & (shown > 0.5)).sum() / max(1, ((back > 0.5) | (shown > 0.5)).sum()))
    return out, dict(silhouette_aspect=round(aspect, 4), letter_redness_level=round(level, 2),
                     colour_rgb=[int(v) for v in np.round(colour)], alpha_levels=levels,
                     display_width_units=round(width, 3), display_height_units=round(height, 3),
                     display_width_max_units=round(lo, 3), margin=0.94,
                     forward_check=dict(iou_at_half_coverage=round(iou, 4),
                                        mean_abs_alpha_error=round(float(np.abs(back - shown)[shown > 0.02].mean()), 4),
                                        intended_coverage_outside_triangles=round(float((shown * ~covered).sum() / shown.sum()), 6)))


def author_chiclet(median: np.ndarray) -> tuple[np.ndarray, dict]:
    x0, y0, x1, y1 = NFL_REGION
    rgb = median[y0:y1, x0:x1].astype(np.float64)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    labels, _count = ndimage.label(lum < 70)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    background = np.isin(labels, list(border))
    shield = ndimage.binary_opening(ndimage.binary_fill_holes(~background), iterations=1)
    parts, n = ndimage.label(shield)
    shield = parts == (1 + int(np.argmax(ndimage.sum(shield, parts, range(1, n + 1)))))
    ys, xs = np.nonzero(shield)
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    band = ndimage.binary_dilation(shield, iterations=2) & ~ndimage.binary_erosion(shield, iterations=2)
    rim = float(np.median(lum[ndimage.binary_erosion(shield, iterations=1) & ~ndimage.binary_erosion(shield, iterations=4)]))
    back = float(np.median(lum[background]))
    size = (lum.shape[1] * SS, lum.shape[0] * SS)
    hi = np.asarray(Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).resize(size, Image.Resampling.LANCZOS)).astype(np.float64)
    core_hi = np.asarray(Image.fromarray((shield * 255).astype(np.uint8)).resize(size, Image.Resampling.NEAREST)) > 127
    band_hi = np.asarray(Image.fromarray((band * 255).astype(np.uint8)).resize(size, Image.Resampling.NEAREST)) > 127
    fill = ndimage.binary_fill_holes(np.where(band_hi, hi > (back + rim) / 2, core_hi))
    cover = fill.reshape(lum.shape[0], SS, lum.shape[1], SS).mean(axis=(1, 3))
    bx0, by0, bx1, by1 = box
    crop_rgb, crop_a = rgb[by0:by1 + 1, bx0:bx1 + 1], cover[by0:by1 + 1, bx0:bx1 + 1]
    fx0, fy0, fx1, fy1 = CHICLET_FOOTPRINT
    tw, th = fx1 - fx0 + 1, fy1 - fy0 + 1
    prem = cv2.resize(crop_rgb * crop_a[..., None], (tw, th), interpolation=cv2.INTER_AREA)
    a = cv2.resize(crop_a, (tw, th), interpolation=cv2.INTER_AREA)
    col = np.where(a[..., None] > 1e-6, prem / np.maximum(a[..., None], 1e-6), 0)
    inner = rgb[ndimage.binary_erosion(shield, iterations=3)]
    navy = np.median(inner[(inner[:, 2] > inner[:, 0] + 40) & (inner[:, 0] < 90)], axis=0)
    yy, xx = np.mgrid[0:64, 0:64]
    step = np.round(np.clip(np.hypot(xx - 32, yy - 32) / 45.0, 0, 1) * 7) / 7.0
    out = np.clip(navy[None, None, :] * (1.22 - 0.80 * step)[..., None], 0, 255)
    region = out[fy0:fy1 + 1, fx0:fx1 + 1]
    out[fy0:fy1 + 1, fx0:fx1 + 1] = region * (1 - a[..., None]) + col * a[..., None]
    arr = np.zeros((64, 64, 4), np.uint8)
    arr[..., :3] = np.round(np.clip(out, 0, 255))
    arr[..., 3] = 255
    arr[..., :3] = np.asarray(Image.fromarray(arr[..., :3], "RGB").quantize(
        colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB"))
    return arr, dict(shield_box_px=box, shield_size_px=[bx1 - bx0 + 1, by1 - by0 + 1],
                     footprint=list(CHICLET_FOOTPRINT), downsample=round((bx1 - bx0 + 1) / tw, 3),
                     plate_navy=[int(round(v)) for v in navy], rim_luma=round(rim, 1),
                     background_luma=round(back, 1), palette_colours=48)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--pack0", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    median, registration = register(args.frames)
    tris, ellipse = wrap_geometry(args.pack0)
    shield, shield_report = author_shield_espn(median, tris, ellipse)
    chiclet, chiclet_report = author_chiclet(median)
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(registration=registration, stinger_frames=[f"{s}/frame_{i:06d}" for s, i in STINGER],
                  regions=dict(espn=list(ESPN_REGION), nfl=list(NFL_REGION), ecc=list(ECC_REGION)),
                  wrap=dict(triangles=[dict(pos=[[round(c, 3) for c in p] for p in t["pos"]],
                                            uv=[[round(c, 4) for c in p] for p in t["uv"]]) for t in tris],
                            ellipse=ellipse),
                  shield_espn=shield_report, nfl_chiclet=chiclet_report)
    for name, rgba in (("shield_espn", shield), ("nfl_chiclet", chiclet)):
        path = args.output / f"{name}.png"
        Image.fromarray(rgba, "RGBA").save(path, optimize=True)
        report[name]["png_sha256"] = sha(path.read_bytes())
        report[name]["unique_rgba"] = int(len({tuple(p) for p in rgba.reshape(-1, 4)}))
    (args.output / "author_marks_report.json").write_text(json.dumps(report, indent=1) + "\n",
                                                          encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k].get("png_sha256") for k in ("shield_espn", "nfl_chiclet")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
