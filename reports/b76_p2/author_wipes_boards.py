#!/usr/bin/env python3
"""Beta 76 p2: author the ESPN 2026 wipes and boards textures from 2026 broadcast stills.

Maintainer evidence script, not shipped. It rebuilds every PNG in ``data/nfl2k5_espn_wipes_boards/`` byte for
byte on the machine that made them, from private inputs that never enter the repository:

  --frames  the folder holding ``mnf/frames/frame_NNNNNN.png`` (the 2026 Giants at Rams MNF highlights, every
            30th frame) and ``obs/frames/frame_NNNNNN.png`` (the off-air recording of the same game, 2 fps)
  --packs   an extracted retail ``vc_53450030`` folder, read for geometry and layout only: the UV triangles of
            the scenes, the retail glow box, arc radius and alpha falloffs the new layers are fitted to

Every colour and every mark comes from the 2026 frames; nothing is copied from a retail texture. The frames used
and every measured number are written to ``author_wipes_boards_report.json`` beside the PNGs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
try:  # maintainer-only evidence tools; the studio runtime never imports this script
    import cv2
    from scipy import ndimage
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"author_wipes_boards.py needs opencv-python and scipy: {exc}")

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools", ROOT / "reports" / "b76_p1"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

STINGER_STILLS = (("mnf", 87), ("obs", 327), ("obs", 681), ("obs", 2350), ("obs", 2538))
ESPN_BOX = (760, 250, 1170, 370)        # the red wordmark in mnf frame_000087 coordinates (p1)
BAND_BOX = (671, 411, 1250, 607)        # the silver MNF band
NFL_BOX = (875, 620, 1045, 835)         # the flat NFL shield (p1)
EMBLEM_BOX = (640, 220, 1280, 840)      # the whole emblem in mnf frame_000087 coordinates (its red rims)
BUMPER_STILL = ("obs", 830)             # the 2026 MNF bumper: red wall, chrome outline letters
RIBBON_STILL = ("obs", 3102)            # the 2026 ESPN NFL open: red ribbons with white glints
EMBLEM_CLOSEUP = ("obs", 1848)          # the emblem close-up going to break: steel band, black plates
BAR_STILLS = tuple(range(290, 300))     # normal 2026 bar frames (the bar's top rim at x 1150-1230, y 946-956)
BOARD_STILL = ("obs", 1866)             # the 2026 corner score box (charcoal, white numerals)
BOARD_BOX_1080 = (1560, 850, 1840, 1060)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def still(frames: Path, source: str, index: int) -> np.ndarray:
    image = cv2.imread(str(frames / source / "frames" / f"frame_{index:06d}.png"))
    if image is None:
        raise SystemExit(f"{source}/frames/frame_{index:06d}.png is missing under --frames")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


# --- 2026 evidence: the emblem median and its parts ------------------------------------------------------

def emblem(frames: Path) -> tuple[np.ndarray, dict]:
    """The five full-size stinger stills registered onto mnf 87 and median-combined (p1's registration)."""

    import author_marks as p1
    median, report = p1.register(frames)
    return median.astype(np.float64), report


def wordmark(median: np.ndarray) -> dict:
    """The 2026 red ESPN wordmark: silhouette (redness at half the letter level) and its own shading."""

    x0, y0, x1, y1 = ESPN_BOX
    rgb = median[y0:y1, x0:x1]
    red = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
    core = red > 0.5 * np.percentile(red, 99)
    level = float(np.median(red[core]))
    coverage = np.clip((red - 0.25 * level) / (0.5 * level), 0, 1)
    mask = red > 0.5 * level
    ys, xs = np.nonzero(mask)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    crop = (slice(box[1], box[3]), slice(box[0], box[2]))
    shading = rgb[crop].copy()
    fill = np.median(rgb[core], axis=0)
    shading[~mask[crop]] = fill
    return dict(coverage=coverage[crop], rgb=shading, fill=fill, level=level,
                box=[box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0])


def colour_stats(pixels: np.ndarray) -> dict:
    return dict(median=[int(v) for v in np.median(pixels, 0)], p10=[int(v) for v in np.percentile(pixels, 10, 0)],
                p90=[int(v) for v in np.percentile(pixels, 90, 0)], count=int(len(pixels)))


def palette(median: np.ndarray, frames: Path) -> dict:
    """Named 2026 colours, each with the pixels it was measured from."""

    x0, y0, x1, y1 = BAND_BOX
    band = median[y0:y1, x0:x1].reshape(-1, 3)
    lum, sat = band.mean(1), band.max(1) - band.min(1)
    light, letters = band[(lum > 150) & (sat < 40)], band[(lum < 110) & (sat < 60)]
    ex0, ey0, ex1, ey1 = EMBLEM_BOX
    emblem_rgb = median[ey0:ey1, ex0:ex1]
    hsv = cv2.cvtColor(np.clip(emblem_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(int)
    red = ((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 140) & (hsv[..., 2] > 70)
    yy, xx = np.mgrid[ey0:ey1, ex0:ex1]
    wx0, wy0, wx1, wy1 = ESPN_BOX
    red &= ~((xx >= wx0) & (xx < wx1) & (yy >= wy0) & (yy < wy1))      # the rims, not the wordmark
    rim = emblem_rgb[red]
    plate = median[640:700, 820:1100].reshape(-1, 3)
    plate = plate[plate.max(1) < 40]
    word = wordmark(median)
    bumper = still(frames, *BUMPER_STILL).reshape(-1, 3).astype(np.float64)
    bumper_red = bumper[(bumper[:, 0] > bumper[:, 1] + 40)]
    bumper_hot = bumper[(bumper.min(1) > 200)]
    ribbon = still(frames, *RIBBON_STILL).reshape(-1, 3).astype(np.float64)
    ribbon_red = ribbon[(ribbon[:, 0] > 150) & (ribbon[:, 0] > ribbon[:, 1] + 80)]
    bar = np.concatenate([still(frames, "mnf", index)[946:956, 1150:1230].reshape(-1, 3).astype(np.float64)
                          for index in BAR_STILLS])
    box = still(frames, *BOARD_STILL)[BOARD_BOX_1080[1]:BOARD_BOX_1080[3], BOARD_BOX_1080[0]:BOARD_BOX_1080[2]]
    box = box.reshape(-1, 3).astype(np.float64)
    blum, bsat = box.mean(1), box.max(1) - box.min(1)
    return dict(
        bar_rim=colour_stats(bar), board_charcoal=colour_stats(box[(blum > 18) & (blum < 50) & (bsat < 20)]),
        board_white=colour_stats(box[(blum > 220) & (bsat < 30)]),
        band_silver=colour_stats(light), band_letters=colour_stats(letters), rim_red=colour_stats(rim),
        plate_black=colour_stats(plate), wordmark_red=dict(median=[int(v) for v in word["fill"]]),
        bumper_red=colour_stats(bumper_red), bumper_hot_white=colour_stats(bumper_hot),
        ribbon_red=colour_stats(ribbon_red),
        sources=dict(emblem=[f"{s}/frame_{i:06d}" for s, i in STINGER_STILLS],
                     bar=[f"mnf/frame_{i:06d}" for i in BAR_STILLS],
                     board=f"{BOARD_STILL[0]}/frame_{BOARD_STILL[1]:06d}",
                     bumper=f"{BUMPER_STILL[0]}/frame_{BUMPER_STILL[1]:06d}",
                     ribbon=f"{RIBBON_STILL[0]}/frame_{RIBBON_STILL[1]:06d}"))


def rgba_png(path: Path, rgba: np.ndarray) -> str:
    Image.fromarray(np.ascontiguousarray(rgba.astype(np.uint8)), "RGBA").save(path, optimize=True)
    return sha(path.read_bytes())


def limit_colours(rgba: np.ndarray, colours: int) -> np.ndarray:
    """Deterministic median-cut to at most ``colours`` RGBA entries (so the game quantiser keeps them exactly)."""

    image = Image.fromarray(np.ascontiguousarray(rgba.astype(np.uint8)), "RGBA")
    if len(set(image.getdata())) <= colours:
        return np.asarray(image).copy()
    quantised = image.quantize(colors=colours, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    return np.asarray(quantised.convert("RGBA")).copy()


# --- retail geometry and layout (read only; never copied into a texture) ------------------------------------

WIPE_SLOT = 124_160                     # wipe.cdf (outer 3114) holds six raw MRKS slots of this size


def load_scene(packs: Path, outer: int, chunk: int):
    """One retail scene resource from the extracted packs, parsed by the shipped backend (geometry only)."""

    import nfl2k5_playbook_position_recode as recode
    from nfl_txtr import parse_chunks
    from mod_editor.core import nfl2k5_presentation_scenes as scenes
    with recode.OuterImage(packs) as archive:
        entry = archive.entries[outer]
        body = archive.read(entry.virtual_offset, entry.size)
    if outer == 3114:
        offset = chunk * WIPE_SLOT
        span_chunk = parse_chunks(body[offset:offset + WIPE_SLOT], allow_trailing=True)[0]
        span = body[offset:offset + span_chunk.end_offset]
    else:
        found = parse_chunks(body, allow_trailing=True)[chunk]
        offset, span = found.offset, body[found.offset:found.end_offset]
    return scenes.open_resource(span, outer_index=outer, outer_id=f"0x{entry.name_id:08x}", outer_size=entry.size,
                                chunk_index=chunk, chunk_offset=offset)


def triangles(resource) -> list[dict]:
    """Every submesh triangle of a scene: shape, material, texture index, and per-vertex display xyz and UV."""

    from mod_editor.core import nfl2k5_models as models
    from mod_editor.core import nfl2k5_presentation_scenes as scenes
    import nfl_scne_gltf as gltf
    view = scenes.scene_view(resource.decoded, resource.kind)
    scene = resource.scene
    out = []
    for shape in scene["shapes"]:
        lanes = models._shape_lanes(scene, shape, view)
        pos = models.read_positions(view, shape, lanes)
        uvs = None
        if lanes.texcoord is not None:
            pairs = models.read_lane_2h(view, shape, lanes.texcoord, lanes.vertex_count)
            uvs = [models.uv_to_gltf(u, v, lanes.uv_scale, lanes.uv_offset) for u, v in pairs]
        for sub in (s for s in scene["submeshes"] if s["shape_index"] == shape["index"]):
            if not sub.get("command_offset"):
                continue
            tris = []
            for mode, raw in gltf.decode_batches(view, sub["command_offset"], sub["primary_command_word_count"]):
                if mode == 5:          # NV2A triangles
                    tris += [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]
                elif mode == 6:        # triangle strip
                    tris += [(raw[i], raw[i + 1], raw[i + 2]) if i % 2 == 0 else (raw[i + 1], raw[i], raw[i + 2])
                             for i in range(len(raw) - 2) if len({raw[i], raw[i + 1], raw[i + 2]}) == 3]
                elif mode in (7, 10):  # fan, polygon
                    tris += [(raw[0], raw[i], raw[i + 1]) for i in range(1, len(raw) - 1)]
                elif mode == 8:        # quads
                    for i in range(0, len(raw) - 3, 4):
                        q = raw[i:i + 4]
                        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
                elif mode == 9:        # quad strip
                    for i in range(0, len(raw) - 3, 2):
                        q = raw[i:i + 4]
                        tris += [(q[0], q[1], q[3]), (q[0], q[3], q[2])]
                else:
                    raise SystemExit(f"unhandled NV2A primitive mode {mode}")
            material = scene["materials"][sub["material_index"]]
            for tri in tris:
                out.append(dict(shape=shape["name"], material=material["name"], texture=material["texture_index"],
                                pos=[list(pos[v]) for v in tri], uv=[list(uvs[v]) if uvs else None for v in tri]))
    return out


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


def inverse_map(tris: list[dict], size: tuple[int, int], design, *, plane=(0, 1), supersample: int = 4,
                margin: float = 2.0):
    """Author in display space, store in texture space: every texel is sampled from ``design`` at the display
    point its owning UV triangle maps it to. Returns (rgba float, owned share, worst conflict per texel).

    ``design(x, y)`` returns RGBA floats (0..255) for arrays of display coordinates. UVs outside 0..1 wrap (the
    game samples with wrap addressing). A texel owned by several triangles keeps the first owner in ``tris``
    order; the conflict map records how far the other owners' display samples disagree. Texels within
    ``margin`` texels outside every triangle take their nearest triangle's extrapolated display sample, so
    bilinear filtering at a triangle edge (a wrap seam) reads the design and not an empty texel.
    """

    width, height = size
    n = supersample
    sy, sx = np.mgrid[0:height * n, 0:width * n]
    P = np.stack([(sx + 0.5) / n, (sy + 0.5) / n], -1)
    out = np.zeros((height * n, width * n, 4))
    owned = np.zeros((height * n, width * n), int)
    conflict = np.zeros((height * n, width * n))
    reach = np.full((height * n, width * n), -np.inf)
    a, b = plane
    maps = []
    for tri in tris:
        uv = [(u * width, v * height) for u, v in tri["uv"]]
        area = (uv[1][0] - uv[0][0]) * (uv[2][1] - uv[0][1]) - (uv[2][0] - uv[0][0]) * (uv[1][1] - uv[0][1])
        if abs(area) < 1e-9:
            continue
        M = affine(uv, [(p[a], p[b]) for p in tri["pos"]])
        us, vs = [p[0] for p in uv], [p[1] for p in uv]
        for kx in range(int(np.floor(min(us) / width)), int(np.floor(max(us) / width)) + 1):
            for ky in range(int(np.floor(min(vs) / height)), int(np.floor(max(vs) / height)) + 1):
                shifted = [(u - kx * width, v - ky * height) for u, v in uv]
                maps.append((shifted, affine(shifted, [(p[a], p[b]) for p in tri["pos"]])))
    for uv, M in maps:
        inside = barycentric(P, uv).min(-1) >= -1e-9
        if not inside.any():
            continue
        px = P[inside][:, 0] * M[0, 0] + P[inside][:, 1] * M[1, 0] + M[2, 0]
        py = P[inside][:, 0] * M[0, 1] + P[inside][:, 1] * M[1, 1] + M[2, 1]
        value = design(px, py)
        first = owned[inside] == 0
        cur = out[inside]
        diff = np.abs(cur - value).max(-1)
        conflict[inside] = np.where(first, conflict[inside], np.maximum(conflict[inside], diff))
        cur[first] = value[first]
        out[inside] = cur
        owned[inside] += 1
    if margin > 0:
        for uv, M in maps:
            lam = barycentric(P, uv)
            area2 = abs((uv[1][0] - uv[0][0]) * (uv[2][1] - uv[0][1]) - (uv[2][0] - uv[0][0]) * (uv[1][1] - uv[0][1]))
            alt = [area2 / max(1e-9, np.hypot(uv[(i + 2) % 3][0] - uv[(i + 1) % 3][0],
                                               uv[(i + 2) % 3][1] - uv[(i + 1) % 3][1])) for i in range(3)]
            outside = np.max(np.stack([-lam[..., i] * alt[i] for i in range(3)], -1), -1)
            near = (owned == 0) & (outside <= margin) & (-outside > reach)
            if not near.any():
                continue
            px = P[near][:, 0] * M[0, 0] + P[near][:, 1] * M[1, 0] + M[2, 0]
            py = P[near][:, 0] * M[0, 1] + P[near][:, 1] * M[1, 1] + M[2, 1]
            out[near] = design(px, py)
            reach[near] = -outside[near]
    texel = out.reshape(height, n, width, n, 4).mean(axis=(1, 3))
    share = (owned > 0).reshape(height, n, width, n).mean(axis=(1, 3))
    touched = np.isfinite(reach).reshape(height, n, width, n).any(axis=(1, 3)) | (share > 0)
    worst = conflict.reshape(height, n, width, n).max(axis=(1, 3))
    return texel, share, worst, touched


def forward_render(tris: list[dict], texture: np.ndarray, *, plane=(0, 1), scale: float = 2.0, box=None):
    """Draw the texture through the triangles into display space (nearest texel), for checks and previews."""

    a, b = plane
    pts = np.array([[p[a], p[b]] for t in tris for p in t["pos"]])
    x0, y0 = pts.min(0) if box is None else box[:2]
    x1, y1 = pts.max(0) if box is None else box[2:]
    W, H = int(np.ceil((x1 - x0) * scale)), int(np.ceil((y1 - y0) * scale))
    gy, gx = np.mgrid[0:H, 0:W]
    px, py = x0 + (gx + 0.5) / scale, y1 - (gy + 0.5) / scale
    shown = np.zeros((H, W, 4))
    th, tw = texture.shape[:2]
    for tri in tris:
        xy = [(p[a], p[b]) for p in tri["pos"]]
        inside = barycentric(np.stack([px, py], -1), xy).min(-1) >= 0
        if not inside.any():
            continue
        M = affine(xy, [(u * tw, v * th) for u, v in tri["uv"]])
        u = px[inside] * M[0, 0] + py[inside] * M[1, 0] + M[2, 0]
        v = py[inside] * M[1, 1] + px[inside] * M[0, 1] + M[2, 1]
        ui = np.mod(np.floor(u).astype(int), tw)
        vi = np.mod(np.floor(v).astype(int), th)
        shown[inside] = texture[vi, ui]
    return shown, (x0, y0, x1, y1)


# --- the replay transition (replay_wipe, wipe.cdf slot 1) ---------------------------------------------------

def radial(size: int, reach: float) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx + 0.5 - size / 2, yy + 0.5 - size / 2)
    return np.clip(1.0 - d / reach, 0.0, 1.0), d


def replay_pattern_flash(pal: dict) -> tuple[np.ndarray, dict]:
    """32x32 flash: the fly-through ends on the silver MNF band, so the flash is that silver, brightest inside."""

    alpha, d = radial(32, 17.0)
    hi, lo = np.array(pal["band_silver"]["p90"], float), np.array(pal["band_silver"]["p10"], float)
    t = np.clip(d / 16.0, 0, 1)[..., None]
    rgb = hi * (1 - t) + lo * t
    out = np.concatenate([rgb, alpha[..., None] * 255], -1)
    return np.round(out), dict(colour_centre=hi.tolist(), colour_edge=lo.tolist(), reach_texels=17.0,
                               source="band_silver p90 to p10 (the MNF band the transition flies through)")


def replay_streaks(pal: dict) -> tuple[np.ndarray, dict]:
    """8x8 streak: a glossy rim line, white-hot core in 2026 rim red (the echo rims of the fly-in)."""

    hot = np.array(pal["bumper_hot_white"]["median"], float)
    body = np.array(pal["rim_red"]["p90"], float)
    edge = np.array(pal["rim_red"]["median"], float)
    rows = [(edge, 0), (edge, 110), (body, 200), (hot, 255), (hot, 255), (body, 200), (edge, 110), (edge, 0)]
    out = np.zeros((8, 8, 4))
    for y, (colour, alpha) in enumerate(rows):
        out[y, :, :3] = colour
        out[y, :, 3] = alpha
    return np.round(out), dict(rows=[[int(c) for c in colour] + [alpha] for colour, alpha in rows],
                               source="rim_red median/p90 and the bumper's white-hot outline core")


def replay_logo_glow(word: dict, box=(2, 15, 126, 48)) -> tuple[np.ndarray, dict]:
    """128x64 glow behind the ESPN logo: the 2026 red wordmark with its own shading, softened like a glow.

    ``box`` is where the retail glow's letters sit (layout only), so the glow stays behind the wipe's 3D logo.
    """

    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cov, rgb = word["coverage"], word["rgb"]
    aspect = cov.shape[1] / cov.shape[0]
    w = bw
    h = w / aspect
    if h > bh:
        h, w = bh, bh * aspect
    W, H = int(round(w)), int(round(h))
    ox, oy = x0 + (bw - W) // 2, y0 + (bh - H) // 2
    S = 8
    cov_hi = cv2.resize(cov, (W * S, H * S), interpolation=cv2.INTER_LINEAR)
    cov_t = cv2.resize(cov_hi, (W, H), interpolation=cv2.INTER_AREA)
    rgb_t = cv2.resize(rgb, (W, H), interpolation=cv2.INTER_AREA)
    alpha = np.zeros((64, 128))
    alpha[oy:oy + H, ox:ox + W] = cov_t
    glow = cv2.GaussianBlur(alpha, (0, 0), 1.3)
    alpha = np.maximum(alpha, np.clip(glow * 1.15, 0, 1))
    colour = np.zeros((64, 128, 3))
    colour[:] = word["fill"]
    colour[oy:oy + H, ox:ox + W] = np.where(cov_t[..., None] > 0.05, rgb_t, word["fill"])
    out = np.concatenate([colour, alpha[..., None] * 255], -1)
    return np.round(np.clip(out, 0, 255)), dict(placed=[ox, oy, W, H], retail_letters_box=list(box),
                                                  wordmark_aspect=round(aspect, 4), glow_sigma_texels=1.3,
                                                  source="the 2026 wordmark silhouette and shading (emblem median)")


def replay_rays(pal: dict, centre=(146.5, 148.1), radius=110.0) -> tuple[np.ndarray, dict]:
    """256x128 crescents and rays: a glossy 2026 rim along the retail arc (centre and radius are layout only).

    Cross-section from the inside out: dark rim edge, stacked echo ridges (the rims the emblem trails as it
    flies in), a bright top edge, then a soft red glow where the retail arc had its long outer falloff.
    """

    cx, cy = centre
    yy, xx = np.mgrid[0:128, 0:256]
    d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) - radius
    dark = np.array(pal["rim_red"]["p10"], float)
    mid = np.array(pal["rim_red"]["median"], float)
    bright = np.array(pal["rim_red"]["p90"], float)
    hot = np.array(pal["bumper_hot_white"]["median"], float)
    colour = np.zeros((128, 256, 3))
    alpha = np.zeros((128, 256))
    inner = (d >= -14) & (d < -8)
    colour[inner] = dark
    alpha[inner] = np.clip((d[inner] + 14) / 6, 0, 1) * 230
    body = (d >= -8) & (d < 4)
    ridge = (np.floor((d + 8) / 3) % 2 == 0)
    colour[body & ridge] = bright
    colour[body & ~ridge] = mid
    alpha[body] = 255
    edge = (d >= 4) & (d < 7)
    colour[edge] = bright * 0.4 + hot * 0.6
    alpha[edge] = 255
    outer = (d >= 7) & (d < 30)
    colour[outer] = mid
    alpha[outer] = np.clip(1 - (d[outer] - 7) / 23, 0, 1) ** 1.5 * 170
    out = np.concatenate([colour, alpha[..., None]], -1)
    return np.round(out), dict(centre=list(centre), radius=radius, bands=dict(inner=[-14, -8], ridges=[-8, 4],
                               top_edge=[4, 7], glow=[7, 30]), ridge_period_texels=3,
                               source="rim_red p10/median/p90 across the emblem's left rim, bumper white-hot")


# --- RedFlashy (wipe.cdf slot 4): logo1 is a two-row wrap ------------------------------------------------------

def redflashy_logo1(word: dict, tris: list[dict], retail_alpha: np.ndarray) -> tuple[np.ndarray, dict]:
    """256x256 logo1: the 2026 red wordmark laid into the retail two-row wrap (ES over PN, slanted seam).

    The retail wordmark's display box is measured by drawing the retail alpha through the quads (layout only);
    the 2026 wordmark is fitted into that box at its own aspect and every texel is inverse-mapped through the
    quad that owns it, so the two halves meet at the seam as one wordmark.
    """

    logo = [t for t in tris if t["material"] == "logo1"]
    retail_rgba = np.zeros(retail_alpha.shape + (4,))
    retail_rgba[..., 3] = retail_alpha
    shown, box = forward_render(logo, retail_rgba, scale=1.0)
    ys, xs = np.nonzero(shown[..., 3] > 0.5)
    X0, Y0, X1, Y1 = box
    rx0, rx1 = X0 + xs.min(), X0 + xs.max() + 1
    ry1, ry0 = Y1 - ys.min(), Y1 - ys.max() - 1
    cov, rgb = word["coverage"], word["rgb"]
    aspect = cov.shape[1] / cov.shape[0]
    bw, bh = rx1 - rx0, ry1 - ry0
    w = min(bw, bh * aspect)
    h = w / aspect
    cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    left, top = cx - w / 2, cy + h / 2
    ch, cw = cov.shape

    def design(px, py):
        u = (px - left) / w * cw - 0.5
        v = (top - py) / h * ch - 0.5
        inside = (u >= -0.5) & (v >= -0.5) & (u <= cw - 0.5) & (v <= ch - 0.5)
        a = np.where(inside, bilinear(cov, u, v), 0.0)
        c = np.where(inside[..., None], bilinear(rgb, u, v), word["fill"])
        return np.concatenate([c, a[..., None] * 255], -1)

    texel, owned, worst, _touched = inverse_map(logo, (256, 256), design, supersample=4)
    # forward check: the stored texture through the same quads against the intended placement
    back, _ = forward_render(logo, texel / 255.0, scale=1.0, box=box)
    gy, gx = np.mgrid[0:back.shape[0], 0:back.shape[1]]
    want = design(X0 + gx + 0.5, Y1 - gy - 0.5)[..., 3] / 255.0
    iou = float(((back[..., 3] > 0.5) & (want > 0.5)).sum() / max(1, ((back[..., 3] > 0.5) | (want > 0.5)).sum()))
    return np.round(np.clip(texel, 0, 255)), dict(
        retail_wordmark_display_box=[round(float(v), 2) for v in (rx0, ry0, rx1, ry1)],
        placed_display_box=[round(float(v), 2) for v in (left, top - h, left + w, top)], wordmark_aspect=round(aspect, 4),
        texels_owned=int((owned > 0).sum()), forward_iou=round(iou, 4),
        source="the 2026 wordmark silhouette and shading (emblem median), inverse-mapped through the retail quads")


# --- Electricity (wipe.cdf slot 3) ------------------------------------------------------------------------------

def electricity_background(pal: dict) -> tuple[np.ndarray, dict]:
    """64x64 back plate: the 2026 MNF bumper's red wall over the emblem's black plate (top half, bottom half)."""

    top = np.array(pal["bumper_red"]["median"], float)
    low = np.array(pal["bumper_red"]["p10"], float)
    black = np.array(pal["plate_black"]["median"], float)
    out = np.zeros((64, 64, 4))
    for y in range(64):
        t = y / 63.0
        colour = top * (1 - t) + low * t if y < 32 else low * (1 - (t - 0.5) * 2 * 0.6) + black * ((t - 0.5) * 2 * 0.6)
        out[y, :, :3] = colour
    out[..., 3] = 255
    return np.round(out), dict(top=top.tolist(), middle=low.tolist(), bottom_mix_black=black.tolist(),
                               source="bumper_red median and p10 (obs 830), plate_black (emblem median)")


def bolt_path(rng: np.random.Generator, x: float, y0: float, y1: float, spread: float, step: float = 3.0):
    points, y = [(x, y0)], y0
    while y < y1:
        y = min(y1, y + step * rng.uniform(0.7, 1.4))
        x = x + rng.normal(0, spread)
        points.append((x, y))
    return points


def electricity_lightning(pal: dict) -> tuple[np.ndarray, dict]:
    """128x128 bolts in the retail column layout (plates u 1-44 v 0-90; bolts u 41-81, 80-110, 108-126).

    Each column gets its own jagged line drawn as the 2026 bumper's glowing outline: a white-hot core in a red
    glow. The paths are generated here (seeded), not traced from the retail bolts.
    """

    rng = np.random.default_rng(2026)
    hot = np.array(pal["bumper_hot_white"]["median"], float)
    glow = np.array(pal["bumper_red"]["p90"], float)
    S = 4
    core = Image.new("L", (128 * S, 128 * S), 0)
    halo = Image.new("L", (128 * S, 128 * S), 0)
    columns = [(22.0, 14.0, 88.0, 1.6), (61.0, 3.0, 78.0, 1.5), (95.0, 3.0, 107.0, 1.3), (117.0, 3.0, 125.0, 0.9)]
    paths = []
    for x, y0, y1, spread in columns:
        for branch in range(2 if x < 40 else 1):
            path = bolt_path(rng, x + (branch * 6 - 3 if x < 40 else 0), y0, y1, spread)
            paths.append(path)
            scaled = [(px * S, py * S) for px, py in path]
            ImageDraw.Draw(core).line(scaled, fill=255, width=S * (2 if branch == 0 else 1))
            ImageDraw.Draw(halo).line(scaled, fill=255, width=S * 5)
    core_a = np.asarray(core.resize((128, 128), Image.Resampling.BOX)).astype(float) / 255
    halo_a = np.asarray(halo.filter(ImageFilter.GaussianBlur(S * 2.5)).resize((128, 128), Image.Resampling.BOX)).astype(float) / 255
    # the plates' flare at the top of the big column (retail layout: v 0-14 of u 1-44)
    yy, xx = np.mgrid[0:128, 0:128]
    flare = np.clip(1 - np.hypot((xx - 22) / 14, (yy - 8) / 9), 0, 1) ** 1.2
    core_a = np.maximum(core_a, flare * 0.9)
    alpha = np.clip(np.maximum(core_a, halo_a * 0.85), 0, 1)
    mix = np.clip(core_a / np.maximum(alpha, 1e-6), 0, 1)[..., None]
    colour = hot * mix + glow * (1 - mix)
    out = np.concatenate([colour, alpha[..., None] * 255], -1)
    return np.round(out), dict(columns=[list(c) for c in columns], seed=2026,
                               source="bumper white-hot outline core and bumper_red p90 glow (obs 830)")


# --- the helmet bumper set (outer 18 chunk 11): monitor and monitorcolors -------------------------------------

MONITOR_LAYOUT = dict(screen=(23, 19, 238, 216), lines=(60, 189), diagonal=((165.5, 61.0), (101.5, 189.0)),
                      slits=(5.5, 88.5, 172.5), stand=216)


def glow_line(size, segments, width_core: float, width_glow: float, S: int = 4):
    core = Image.new("L", (size[0] * S, size[1] * S), 0)
    halo = Image.new("L", (size[0] * S, size[1] * S), 0)
    for (x0, y0), (x1, y1) in segments:
        ImageDraw.Draw(core).line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=255, width=int(width_core * S))
        ImageDraw.Draw(halo).line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=255, width=int(width_glow * S))
    c = np.asarray(core.resize(size, Image.Resampling.BOX)).astype(float) / 255
    h = np.asarray(halo.filter(ImageFilter.GaussianBlur(S * 1.2)).resize(size, Image.Resampling.BOX)).astype(float) / 255
    return c, h


def helmet_monitor(pal: dict, layout: dict = MONITOR_LAYOUT) -> tuple[np.ndarray, dict]:
    """256x256 set monitor: the emblem's black plate and red rim as the bezel, the 2026 MNF bumper wall as the
    screen (red, horizontal panel lines), the retail line layout drawn as the bumper's white-hot outlines.

    The line and slit positions are the retail layout (so the monitorcolors bands still meet them); every
    colour is measured from the 2026 frames.
    """

    black = np.array(pal["plate_black"]["median"], float)
    black_hi = np.array(pal["plate_black"]["p90"], float)
    rim = np.array(pal["rim_red"]["median"], float)
    rim_hi = np.array(pal["rim_red"]["p90"], float)
    wall = np.array(pal["bumper_red"]["median"], float)
    wall_dark = np.array(pal["bumper_red"]["p10"], float)
    wall_light = np.array(pal["ribbon_red"]["p10"], float)
    hot = np.array(pal["bumper_hot_white"]["median"], float)
    out = np.zeros((256, 256, 3))
    yy, xx = np.mgrid[0:256, 0:256]
    shade = 0.75 + 0.25 * (1 - yy / 255.0)
    out[:] = black * shade[..., None] + black_hi * (1 - shade[..., None]) * 0.5
    sx0, sy0, sx1, sy1 = layout["screen"]
    top, bottom = layout["lines"]
    screen = (xx >= sx0) & (xx < sx1) & (yy >= sy0) & (yy < sy1)
    band = np.where(yy < top, 0, np.where(yy <= bottom, 1, 2))
    t = np.clip((yy - sy0) / max(1, sy1 - sy0), 0, 1)
    colours = [wall_dark * (1 - t[..., None]) + wall * t[..., None],
               wall * (1 - 0.35 * t[..., None]) + wall_dark * 0.35 * t[..., None],
               wall_light * (1 - 0.3 * t[..., None]) + wall * 0.3 * t[..., None]]
    for index, colour in enumerate(colours):
        sel = screen & (band == index)
        out[sel] = colour[sel]
    panel = screen & ((yy - sy0) % 12 == 0)
    out[panel] = out[panel] * 0.82 + wall_light * 0.18
    # a red rim around the screen, the emblem's plate edge
    frame = (xx >= sx0 - 3) & (xx < sx1 + 3) & (yy >= sy0 - 3) & (yy < sy1 + 3) & ~screen
    out[frame] = rim
    frame_hi = frame & ((yy == sy0 - 3) | (xx == sx0 - 3))
    out[frame_hi] = rim_hi
    for x in layout["slits"]:
        slit = (np.abs(xx + 0.5 - x) <= 1.0) & (yy >= layout["stand"] + 8) & (yy < 250)
        out[slit] = rim
    (dx0, dy0), (dx1, dy1) = layout["diagonal"]
    core, halo = glow_line((256, 256), [((sx0, top), (sx1, top)), ((sx0, bottom), (sx1, bottom)),
                                        ((dx0, dy0), (dx1, dy1))], 1.5, 5.0)
    glow = np.clip(halo - core, 0, 1)[..., None] * screen[..., None]
    out = out * (1 - glow * 0.8) + rim_hi * glow * 0.8
    out = out * (1 - core[..., None]) + hot * core[..., None]
    rgba = np.concatenate([np.clip(out, 0, 255), np.full((256, 256, 1), 255.0)], -1)
    return np.round(rgba), dict(layout=layout, screen="bumper_red p10, median; ribbon_red p10 lower band",
                                bezel="plate_black, rim_red", lines="bumper white-hot core, rim_red p90 glow",
                                source="obs 830 (MNF bumper wall), obs 1848 (emblem plate and rim), obs 3102 (ribbon)")


def helmet_monitorcolors(pal: dict) -> tuple[np.ndarray, dict]:
    """256x128 scrolling colours: horizontal red ribbon bands with white glints (the 2026 ESPN NFL open).

    Every row is one colour: the texture scrolls sideways across the set's bands, and row-constant bands keep
    the regenerated mip chain to a few dozen colours, so the resource's palette ends in zero entries the stream
    packs as matches (the in-place decode then needs no more than the retail scratch word).
    """

    rng = np.random.default_rng(76)
    lo = np.array(pal["ribbon_red"]["p10"], float)
    mid = np.array(pal["ribbon_red"]["median"], float)
    hi = np.array(pal["ribbon_red"]["p90"], float)
    hot = np.array(pal["bumper_hot_white"]["median"], float)
    tones = [lo, lo * 0.5 + mid * 0.5, mid, mid * 0.5 + hi * 0.5, hi]
    rows = np.zeros((128, 3))
    y = 0
    while y < 128:
        height = int(rng.integers(4, 13))
        rows[y:y + height] = tones[int(rng.integers(0, len(tones)))]
        y += height
    glints = sorted(int(v) for v in rng.choice(np.arange(6, 122), 4, replace=False))
    for g in glints:
        rows[g] = hot
    out = np.zeros((128, 256, 4))
    out[..., :3] = np.round(rows)[:, None, :]
    out[..., 3] = 255
    return out, dict(seed=76, glint_rows=glints, tones=[[int(round(c)) for c in t] for t in tones],
                     source="ribbon_red p10/median/p90 and white-hot glints (obs 3102, obs 830)")


# --- more emblem parts: the MNF letters, the band, the NFL shield ----------------------------------------------

def mnf_letters(median: np.ndarray) -> dict:
    """The MNF band of the emblem: its silver RGB and the dark letter silhouette (coverage 0..1)."""

    x0, y0, x1, y1 = BAND_BOX
    rgb = median[y0:y1, x0:x1]
    lum = rgb.mean(-1)
    sat = rgb.max(-1) - rgb.min(-1)
    band = (lum > 140) & (sat < 45)
    rows = np.nonzero(band.mean(1) > 0.5)[0]
    top, bottom = int(rows.min()), int(rows.max()) + 1
    inner = rgb[top:bottom]
    ilum = inner.mean(-1)
    silver = float(np.median(ilum[ilum > 140]))
    dark = float(np.median(ilum[ilum < 90]))
    coverage = np.clip((silver - ilum) / max(1.0, silver - dark), 0, 1)
    letters = coverage > 0.5
    labels, count = ndimage.label(letters)
    sizes = ndimage.sum(letters, labels, range(1, count + 1))
    keep = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s > 0.02 * letters.sum()])
    ys, xs = np.nonzero(keep)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    cov = coverage[box[1]:box[3], box[0]:box[2]] * ndimage.binary_dilation(keep, iterations=2)[box[1]:box[3], box[0]:box[2]]
    return dict(band_rgb=inner, band_rows=[top + y0, bottom + y0], coverage=cov,
                box=[box[0] + x0, box[1] + y0 + top, box[2] + x0, box[3] + y0 + top])


def nfl_shield(median: np.ndarray) -> dict:
    """The flat NFL shield of the emblem as RGBA (p1's segmentation: flood the dark plate, fill the shield)."""

    x0, y0, x1, y1 = NFL_BOX
    rgb = median[y0:y1, x0:x1]
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    labels, _count = ndimage.label(lum < 70)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    background = np.isin(labels, list(border))
    shield = ndimage.binary_opening(ndimage.binary_fill_holes(~background), iterations=1)
    parts, n = ndimage.label(shield)
    shield = parts == (1 + int(np.argmax(ndimage.sum(shield, parts, range(1, n + 1)))))
    ys, xs = np.nonzero(shield)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    soft = ndimage.gaussian_filter(shield.astype(float), 0.7)
    crop = (slice(box[1], box[3]), slice(box[0], box[2]))
    return dict(rgb=rgb[crop], alpha=np.clip(soft[crop] * 1.4 - 0.2, 0, 1),
                box=[box[0] + x0, box[1] + y0, box[2] + x0, box[3] + y0])


# --- the pause scoreboard (outer 347 chunk 5): a display-space design, stored through the retail UVs -------

SCOREBOARD_FONT = Path("/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf")
SCOREBOARD_FONT_ITALIC = Path("/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-BoldItalic.ttf")
# The retail LED panel is a 49 x 50 lattice of dots in display space; its labels (layout only) start at these
# lattice cells: (text, top row, first column of each letter). Letters are 10 rows tall.
LED_LABELS = (("VISITOR", 3, (3, 10, 15, 22, 27, 34, 41)), ("HOME", 15, (3, 10, 17, 25)),
              ("DOWN", 37, (3, 10, 17, 25)))
LED_MARKER_CELL = (40, 34)      # the possession marker after DOWN: top row, first column
# The 2026 lettering on that lattice (drawn here, 2-dot strokes like the 2026 bold condensed type). W is M turned
# upside down because the retail triangles draw DOWN's W from the M's dots.
LED_GLYPHS = {
    "V": ("##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####.", ".####.", "..##..", "..##.."),
    "I": ("####", "####", ".##.", ".##.", ".##.", ".##.", ".##.", ".##.", "####", "####"),
    "S": (".#####", "######", "##....", "##....", "#####.", ".#####", "....##", "....##", "######", "#####."),
    "T": ("######", "######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."),
    "O": (".####.", "######", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "######", ".####."),
    "R": ("#####.", "######", "##..##", "##..##", "######", "#####.", "##.##.", "##..##", "##..##", "##..##"),
    "H": ("##..##", "##..##", "##..##", "##..##", "######", "######", "##..##", "##..##", "##..##", "##..##"),
    "M": ("##...##", "###.###", "#######", "##.#.##", "##...##", "##...##", "##...##", "##...##", "##...##",
          "##...##"),
    "E": ("######", "######", "##....", "##....", "#####.", "#####.", "##....", "##....", "######", "######"),
    "D": ("#####.", "######", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "######", "#####."),
    "N": ("##..##", "###.##", "###.##", "######", "######", "##.###", "##.###", "##..##", "##..##", "##..##"),
}
LED_GLYPHS["W"] = tuple(reversed(LED_GLYPHS["M"]))
LED_MARKER_GLYPH = (".####.", "######", "######", ".####.")


class Canvas:
    """A display-space RGBA canvas (PIL, ``scale`` pixels per display unit, y up)."""

    def __init__(self, box, scale: float, fill):
        self.x0, self.y0, self.x1, self.y1 = box
        self.s = scale
        self.w = int(np.ceil((self.x1 - self.x0) * scale))
        self.h = int(np.ceil((self.y1 - self.y0) * scale))
        self.image = Image.new("RGBA", (self.w, self.h), tuple(int(v) for v in fill))
        self.draw = ImageDraw.Draw(self.image)

    def px(self, x, y):
        return ((x - self.x0) * self.s, (self.y1 - y) * self.s)

    def rect(self, box):
        x0, y0, x1, y1 = box
        a, b = self.px(x0, y1)
        c, d = self.px(x1, y0)
        return int(round(a)), int(round(b)), int(round(c)), int(round(d))

    def fill(self, box, colour):
        self.draw.rectangle(self.rect(box), fill=tuple(int(v) for v in colour))

    def paste(self, box, rgba: np.ndarray, *, keep_aspect=True, align="centre", composite=True):
        """Fit an RGBA array (0..255) into a display box."""

        x0, y0, x1, y1 = self.rect(box)
        bw, bh = x1 - x0, y1 - y0
        h, w = rgba.shape[:2]
        if keep_aspect:
            k = min(bw / w, bh / h)
            nw, nh = max(1, int(round(w * k))), max(1, int(round(h * k)))
        else:
            nw, nh = bw, bh
        tile = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA").resize((nw, nh), Image.Resampling.LANCZOS)
        ox = x0 + (bw - nw) // 2 if align == "centre" else x0
        oy = y0 + (bh - nh) // 2
        if composite:
            self.image.alpha_composite(tile, (ox, oy))
        else:
            self.image.paste(tile, (ox, oy))

    def text(self, box, words: str, font: Path, colour, *, height_share=0.72):
        from PIL import ImageFont
        x0, y0, x1, y1 = self.rect(box)
        size = int((y1 - y0) * height_share * 1.35)
        face = ImageFont.truetype(str(font), size)
        while size > 4:
            l, t, r, b = self.draw.textbbox((0, 0), words, font=face)
            if r - l <= (x1 - x0) and b - t <= (y1 - y0) * height_share:
                break
            size -= 1
            face = ImageFont.truetype(str(font), size)
        l, t, r, b = self.draw.textbbox((0, 0), words, font=face)
        self.draw.text((x0 + (x1 - x0 - (r - l)) / 2 - l, y0 + (y1 - y0 - (b - t)) / 2 - t), words,
                       font=face, fill=tuple(int(v) for v in colour))

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        if getattr(self, "_cache_of", None) is not self.image:
            self._cache = np.asarray(self.image).astype(np.float32)
            self._cache_of = self.image
        return bilinear(self._cache, (np.asarray(x) - self.x0) * self.s - 0.5,
                        (self.y1 - np.asarray(y)) * self.s - 0.5).astype(np.float64)


def tinted(mask: np.ndarray, colour) -> np.ndarray:
    out = np.zeros(mask.shape + (4,))
    out[..., :3] = colour
    out[..., 3] = np.clip(mask, 0, 1) * 255
    return out


def rotate90(rgba: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.rot90(rgba, 1))


BOARD_BOX = (-311.5, -228.5, 285.0, 208.0)
FRAME_PATCH = (12, 0, 31, 4)            # sign02 texels every silver border samples (uv 0.115-0.219, 0.008-0.023)
LED_DOTS = (42, 21)                     # sign01 top half: 2x2 LED dots on a 3-texel pitch, gaps on x, y = 3k


def board_regions() -> dict:
    """Display boxes (x0, y0, x1, y1) of the scoreboard's visible parts, from the retail triangles (layout only)."""

    return dict(
        top_sign=(-252.8, 136.2, 133.4, 182.4), right_sign=(154.4, 18.7, 284.5, 115.2),
        left_upper=(-311.0, -2.5, -273.7, 115.2), left_lower=(-311.0, -136.6, -273.7, -19.1),
        nfl_panel=(-310.9, -227.6, -181.4, -170.3), lockup_panel=(61.8, -227.6, 242.4, -170.3),
        espn_piece=(-113.0, -160.0, -55.6, -146.1), vision_pieces=(-49.2, -160.0, -7.7, -150.2),
        led_frame=(-156.3, -227.8, 36.9, -166.1), main_screen=(-252.8, -136.7, 133.4, 115.2),
        led_panel=(154.4, -136.7, 284.5, -2.4), led_small=(-135.3, -227.6, 15.9, -178.7))


def board_canvas(pal: dict, median: np.ndarray, word: dict, band: dict, shield: dict) -> tuple[Canvas, dict]:
    charcoal = np.array(pal["board_charcoal"]["median"], float)
    black = np.array(pal["plate_black"]["median"], float)
    white = np.array(pal["board_white"]["median"], float)
    rim = np.array(pal["rim_red"]["median"], float)
    rim_hi = np.array(pal["rim_red"]["p90"], float)
    regions = board_regions()
    canvas = Canvas(BOARD_BOX, 6.0, tuple(charcoal) + (255,))
    wm = word["coverage"]
    red_word = np.concatenate([word["rgb"], wm[..., None] * 255], -1)
    white_word = tinted(wm, white)
    mnf = tinted(band["coverage"], white)
    # the marquee: red wordmark and the 2026 lettering on the board charcoal
    x0, y0, x1, y1 = regions["top_sign"]
    canvas.fill(regions["top_sign"], charcoal)
    canvas.paste((x0 + 6, y0 + 7, x0 + 118, y1 - 7), red_word)
    canvas.text((x0 + 124, y0 + 5, x1 - 6, y1 - 5), "MONDAY NIGHT FOOTBALL", SCOREBOARD_FONT_ITALIC, white,
                height_share=0.62)
    # the right sign: the emblem's upper half as the stinger shows it (median of five stills)
    canvas.fill(regions["right_sign"], black)
    top = int(word["box"][1]) - 22
    bottom = int(band["band_rows"][1]) + 6
    emblem_rgb = median[top:bottom, 680:1240]
    canvas.paste(regions["right_sign"], np.concatenate([emblem_rgb, np.full(emblem_rgb.shape[:2] + (1,), 255.0)], -1))
    # the left banners: the red wordmark reading upward on the emblem's black plate
    for name in ("left_upper", "left_lower"):
        bx0, by0, bx1, by1 = regions[name]
        canvas.fill(regions[name], black)
        canvas.paste((bx0 + 5, by0 + 8, bx1 - 5, by1 - 8), rotate90(red_word))
    # the NFL panel: the emblem's shield on its black plate
    canvas.fill(regions["nfl_panel"], black)
    nx0, ny0, nx1, ny1 = regions["nfl_panel"]
    canvas.paste((nx0, ny0 + 4, nx1, ny1 - 4), np.concatenate([shield["rgb"], shield["alpha"][..., None] * 255], -1))
    # the lockup panel: white ESPN wordmark and MNF letters (the 2026 corner watermark)
    canvas.fill(regions["lockup_panel"], charcoal)
    lx0, ly0, lx1, ly1 = regions["lockup_panel"]
    mid = lx0 + (lx1 - lx0) * 0.55
    canvas.paste((lx0 + 10, ly0 + 14, mid - 4, ly1 - 14), white_word)
    canvas.paste((mid + 4, ly0 + 13, lx1 - 10, ly1 - 13), mnf)
    # the small sign under the screen: the white wordmark alone on a transparent ground
    for name in ("espn_piece", "vision_pieces"):
        canvas.fill(regions[name], (0, 0, 0, 0))
    ex0, ey0, ex1, ey1 = regions["espn_piece"]
    canvas.paste((ex0 + 1, ey0 + 1, ex1 - 1, ey1 - 1), white_word, composite=False)
    # the small LED panel's frame: a red rim with rounded corners, transparent inside and out
    fx0, fy0, fx1, fy1 = regions["led_frame"]
    ring = Image.new("L", (canvas.w, canvas.h), 0)
    d = ImageDraw.Draw(ring)
    d.rounded_rectangle(canvas.rect(regions["led_frame"]), radius=int(12 * canvas.s), fill=255)
    d.rounded_rectangle(canvas.rect((fx0 + 6, fy0 + 6, fx1 - 6, fy1 - 6)), radius=int(7 * canvas.s), fill=0)
    ring_a = np.asarray(ring).astype(float) / 255
    arr = np.asarray(canvas.image).astype(float)
    box = canvas.rect(regions["led_frame"])
    sub = (slice(max(0, box[1] - 2), box[3] + 2), slice(max(0, box[0] - 2), box[2] + 2))
    yy = np.linspace(0, 1, arr[sub].shape[0])[:, None, None]
    ring_colour = rim_hi * (1 - yy) + rim * yy
    arr[sub][..., :3] = np.where(ring_a[sub][..., None] > 0, ring_colour, arr[sub][..., :3])
    arr[sub][..., 3] = ring_a[sub] * 255
    canvas.image = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    canvas.draw = ImageDraw.Draw(canvas.image)
    return canvas, dict(regions={k: list(v) for k, v in regions.items()},
                        lettering=dict(font=SCOREBOARD_FONT_ITALIC.name, text="MONDAY NIGHT FOOTBALL",
                                       font_sha256=sha(SCOREBOARD_FONT_ITALIC.read_bytes())))


def led_lattice(tris: list[dict], width: int = 128, height: int = 128):
    """The LED texture dots, where each one shows up on the display, and the display lattice of the big panel.

    Returns (per-dot list of display points, lattice column centres, lattice row centres top first)."""

    maps = []
    for tri in tris:
        if tri["texture"] != 2 or min(v for _u, v in tri["uv"]) >= 0.5 - 1e-6 and max(v for _u, v in tri["uv"]) <= 1.0 + 1e-6:
            continue
        uv = [(u * width, v * height) for u, v in tri["uv"]]
        us, vs = [p[0] for p in uv], [p[1] for p in uv]
        for kx in range(int(np.floor(min(us) / width)), int(np.floor(max(us) / width)) + 1):
            for ky in range(int(np.floor(min(vs) / height)), int(np.floor(max(vs) / height)) + 1):
                shifted = [(u - kx * width, v - ky * height) for u, v in uv]
                area = ((shifted[1][0] - shifted[0][0]) * (shifted[2][1] - shifted[0][1])
                        - (shifted[2][0] - shifted[0][0]) * (shifted[1][1] - shifted[0][1]))
                if abs(area) > 1e-9:
                    maps.append((shifted, affine(shifted, [(p[0], p[1]) for p in tri["pos"]])))
    cols, rows = LED_DOTS
    points = {}
    for j in range(rows):
        for i in range(cols):
            c = np.array([3 * i + 2.0, 3 * j + 2.0])
            points[(i, j)] = [(c[0] * M[0, 0] + c[1] * M[1, 0] + M[2, 0], c[0] * M[0, 1] + c[1] * M[1, 1] + M[2, 1])
                              for uv, M in maps if barycentric(c, uv).min() >= -1e-6]
    main = sorted(p for pts in points.values() for p in pts if p[0] > 150)

    def centres(values):
        values = np.sort(np.array(values))
        groups = [[values[0]]]
        for a, b in zip(values, values[1:]):
            (groups.append([b]) if b - a > 0.9 else groups[-1].append(b))
        return np.array([np.mean(g) for g in groups])
    return points, centres([p[0] for p in main]), centres([p[1] for p in main])[::-1]


def led_labels(tris: list[dict], pal: dict) -> tuple[np.ndarray, dict]:
    """sign01 rows 0-63: the LED board. The labels VISITOR, HOME and DOWN and the possession marker keep their
    retail lattice cells (layout) and are lettered with the 2026 glyphs above: white lit dots on dim bar blue.
    A dot the triangles reuse in several places is lit by the majority of the places it shows up in."""

    white = np.array(pal["board_white"]["median"], float)
    unlit = np.array(pal["bar_rim"]["median"], float) * 0.6 + np.array(pal["board_charcoal"]["median"], float) * 0.4
    gap = np.array(pal["plate_black"]["p10"], float)
    points, cx, cy = led_lattice(tris)
    lattice = np.zeros((len(cy), len(cx)), bool)
    for word, top, starts in LED_LABELS:
        for letter, left in zip(word, starts):
            for r, line in enumerate(LED_GLYPHS[letter]):
                for c, mark in enumerate(line):
                    lattice[top + r, left + c] |= mark == "#"
    top, left = LED_MARKER_CELL
    for r, line in enumerate(LED_MARKER_GLYPH):
        for c, mark in enumerate(line):
            lattice[top + r, left + c] |= mark == "#"
    cols, rows = LED_DOTS
    lit = np.zeros((rows, cols), bool)
    reused = split = 0
    for (i, j), pts in points.items():
        votes = []
        for x, y in pts:
            if x > 150:
                votes.append(bool(lattice[int(np.argmin(np.abs(cy - y))), int(np.argmin(np.abs(cx - x)))]))
            else:
                votes.append(False)       # the small panel under the screen is a blank board
        reused += len(votes) > 1
        split += 0 < sum(votes) < len(votes)
        lit[j, i] = sum(votes) * 2 > len(votes)
    out = np.zeros((64, 128, 4))
    out[..., :3] = gap
    out[..., 3] = 255
    for j in range(rows):
        for i in range(cols):
            y, x = 3 * j + 1, 3 * i + 1
            top_colour, low_colour = (white, white * 0.9) if lit[j, i] else (unlit * 1.1, unlit)
            out[y, x:x + 2, :3] = top_colour
            out[y + 1, x:x + 2, :3] = low_colour
    return np.round(np.clip(out, 0, 255)), dict(lattice=[int(len(cx)), int(len(cy))], lit_dots=int(lit.sum()),
                                                reused_dots=int(reused), split_votes=int(split),
                                                labels=[w for w, _t, _s in LED_LABELS])


def board_tiles(pal: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """The two tiled textures: the screen's LED wall (1-texel dots, 2-texel pitch, gaps transparent) in the
    2026 bar's rim blue, and the backboard in the board charcoal with vertical brushed grain (seeded)."""

    rng = np.random.default_rng(347)
    dot = np.zeros((64, 64, 4))
    dot[0::2, 0::2, :3] = pal["bar_rim"]["median"]
    dot[0::2, 0::2, 3] = 255
    base = np.array(pal["board_charcoal"]["median"], float)
    dark = np.array(pal["board_charcoal"]["p10"], float)
    grain = np.convolve(rng.normal(0, 1, 80), np.ones(5) / 5, mode="same")[8:72]
    grain = (grain - grain.min()) / max(1e-6, grain.max() - grain.min())
    back = np.zeros((64, 64, 4))
    for x in range(64):
        back[:, x, :3] = dark * (1 - grain[x]) + base * grain[x]
    back[..., 3] = 255
    return np.round(dot), np.round(back), dict(dot_colour=list(pal["bar_rim"]["median"]), dot_pitch_texels=2,
                                               backboard=[list(dark), list(base)], seed=347)


# --- the player card's league shield (outer 3 chunk 57, znfl_shield) --------------------------------------------

def playercard_nfl_shield(shield: dict, retail_alpha: np.ndarray) -> tuple[np.ndarray, dict]:
    """64x64 znfl_shield: the emblem's flat 2026 NFL shield in the footprint the retail shield occupies (the
    footprint is layout; the pixels are the five-still median), transparent around it."""

    ys, xs = np.nonzero(retail_alpha > 0.5)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgb, alpha = shield["rgb"], shield["alpha"]
    h, w = alpha.shape
    k = min((x1 - x0) / w, (y1 - y0) / h)
    nw, nh = max(1, int(round(w * k))), max(1, int(round(h * k)))
    prem = cv2.resize(rgb * alpha[..., None], (nw, nh), interpolation=cv2.INTER_AREA)
    a = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_AREA)
    colour = np.where(a[..., None] > 1e-6, prem / np.maximum(a[..., None], 1e-6), 0)
    out = np.zeros((64, 64, 4))
    ox, oy = x0 + (x1 - x0 - nw) // 2, y0 + (y1 - y0 - nh) // 2
    out[oy:oy + nh, ox:ox + nw, :3] = colour
    out[oy:oy + nh, ox:ox + nw, 3] = np.clip(a, 0, 1) * 255
    fill = np.median(rgb[alpha > 0.9], axis=0)
    out[out[..., 3] == 0, :3] = fill
    return np.round(np.clip(out, 0, 255)), dict(retail_footprint=[x0, y0, x1, y1], placed=[ox, oy, nw, nh],
                                                 source="the flat NFL shield of the emblem median (five stills)")


# --- the whole set --------------------------------------------------------------------------------------------

TARGETS = (  # PNG name -> (outer, chunk, texture index); the build option pins the same list
    ("replay_wipe_pattern_flash", 3114, 1, 0), ("replay_wipe_streaks", 3114, 1, 1),
    ("replay_wipe_logo_glow", 3114, 1, 2), ("replay_wipe_rays", 3114, 1, 3),
    ("electricity_background1", 3114, 3, 0), ("electricity_lightning", 3114, 3, 1),
    ("redflashy_logo1", 3114, 4, 0),
    ("scoreboard_sign02", 347, 5, 0), ("scoreboard_dot", 347, 5, 1), ("scoreboard_sign01", 347, 5, 2),
    ("scoreboard_backboard01", 347, 5, 3),
    ("helmetbumper_monitor", 18, 11, 0), ("helmetbumper_monitorcolors", 18, 11, 1),
    ("playercard_znfl_shield", 3, 57, 1),
)


def author_all(frames: Path, packs: Path) -> tuple[dict[str, np.ndarray], dict]:
    median, registration = emblem(frames)
    word, band, shield = wordmark(median), mnf_letters(median), nfl_shield(median)
    pal = palette(median, frames)
    report: dict = dict(registration=registration, palette=pal,
                        wordmark=dict(box=word["box"], level=round(word["level"], 2),
                                      fill=[int(v) for v in word["fill"]]),
                        mnf_band=dict(box=band["box"], band_rows=band["band_rows"]), nfl_shield=dict(box=shield["box"]))
    out: dict[str, np.ndarray] = {}
    for name, fn in (("replay_wipe_pattern_flash", lambda: replay_pattern_flash(pal)),
                     ("replay_wipe_streaks", lambda: replay_streaks(pal)),
                     ("replay_wipe_logo_glow", lambda: replay_logo_glow(word)),
                     ("replay_wipe_rays", lambda: replay_rays(pal)),
                     ("electricity_background1", lambda: electricity_background(pal)),
                     ("electricity_lightning", lambda: electricity_lightning(pal)),
                     ("helmetbumper_monitor", lambda: helmet_monitor(pal)),
                     ("helmetbumper_monitorcolors", lambda: helmet_monitorcolors(pal))):
        out[name], report[name] = fn()
    from mod_editor.core import nfl2k5_presentation_scenes as scenes
    flashy = load_scene(packs, 3114, 4)
    w, h, rgba = scenes.texture_rgba(flashy, 0)
    retail_alpha = np.frombuffer(rgba, np.uint8).reshape(h, w, 4)[..., 3].astype(np.float64) / 255.0
    out["redflashy_logo1"], report["redflashy_logo1"] = redflashy_logo1(word, triangles(flashy), retail_alpha)
    card = load_scene(packs, 3, 57)
    w, h, rgba = scenes.texture_rgba(card, 1)
    card_alpha = np.frombuffer(rgba, np.uint8).reshape(h, w, 4)[..., 3].astype(np.float64) / 255.0
    out["playercard_znfl_shield"], report["playercard_znfl_shield"] = playercard_nfl_shield(shield, card_alpha)
    board = load_scene(packs, 347, 5)
    tris = triangles(board)
    canvas, report["scoreboard_design"] = board_canvas(pal, median, word, band, shield)
    design = canvas.sample
    charcoal = np.array(pal["board_charcoal"]["median"], float)
    sign02, share, worst, touched = inverse_map([t for t in tris if t["texture"] == 0], (128, 128), design)
    x0, y0, x1, y1 = FRAME_PATCH
    sign02[y0:y1, x0:x1, :3] = pal["band_silver"]["median"]
    sign02[y0:y1, x0:x1, 3] = 255
    blank = ~touched
    blank[y0:y1, x0:x1] = False
    sign02[blank, :3] = charcoal
    sign02[blank, 3] = 255
    report["scoreboard_sign02"] = dict(texels_owned=int((share > 0).sum()), texels_blank=int(blank.sum()),
                                       reused_texels_disagreeing=int((worst > 40).sum()), frame_patch=list(FRAME_PATCH),
                                       frame_colour="band_silver median")
    marquee = [t for t in tris if t["texture"] == 2 and min(v for _u, v in t["uv"]) >= 0.5 - 1e-6
               and max(v for _u, v in t["uv"]) <= 1.0 + 1e-6]
    sign01, share1, _worst1, touched1 = inverse_map(marquee, (128, 128), design)
    led, report["scoreboard_led"] = led_labels(tris, pal)
    sign01[:64] = led
    lower = sign01[64:]
    lower[~touched1[64:], :3] = charcoal
    lower[~touched1[64:], 3] = 255
    report["scoreboard_sign01"] = dict(marquee_texels_owned=int((share1[64:] > 0).sum()), led_rows="0-63")
    dot, back, report["scoreboard_tiles"] = board_tiles(pal)
    out.update(scoreboard_sign02=sign02, scoreboard_sign01=sign01, scoreboard_dot=dot, scoreboard_backboard01=back)
    for name in out:
        out[name] = limit_colours(np.round(np.clip(out[name], 0, 255)), 256)
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--packs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    images, report = author_all(args.frames, args.packs)
    args.output.mkdir(parents=True, exist_ok=True)
    report["png"] = {}
    for name, _outer, _chunk, _index in TARGETS:
        path = args.output / f"{name}.png"
        report["png"][name] = dict(sha256=rgba_png(path, images[name]), size=list(images[name].shape[1::-1]),
                                   unique_rgba=int(len({tuple(p) for p in images[name].reshape(-1, 4)})))
    report["targets"] = [dict(png=f"{n}.png", outer=o, chunk=c, texture=i) for n, o, c, i in TARGETS]
    (args.output / "author_wipes_boards_report.json").write_text(
        json.dumps(report, indent=1, default=lambda v: v.tolist() if hasattr(v, "tolist") else str(v)) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({k: v["sha256"][:16] for k, v in report["png"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
