"""hu1 (b773): Washington's menu helmets carry the 2026 helmet W instead of the club's outlined W.

uf3 drew the 2026 decal (four solid gold strokes split by thin burgundy lines, no outline) on the in-game helmets,
but the Team Select cards (``helm_h29_0``/``helm_a29_0`` at 256 and 128, the helmet on ``unif_h29_0``/``unif_a29_0``)
and the schedule miniatures (``mini_h29_0``/``mini_a29_0``) still showed the outlined W. This pass re-renders the W on
those eight P8 slots from one vector model (``data/nfl2k5_menu_helmet_w2026.json``): the club W's four strokes in
logo space, each overlapped by the next, placed on every card by a fitted projective transform. For each slot:

1. the old W's gold outline (and its antialiased fringe) is filled from the surrounding lit shell, texel by texel
   from the outside in, so the helmet's shading continues under it;
2. the four strokes are rasterised with exact fixed-point coverage; each back stroke stops ``gap`` texels short of
   the stroke in front of it, which leaves the thin burgundy split;
3. the gold takes the shell's lighting (square root of the luma ratio, as the card renders light their marks), so
   highlights and the falloff toward the rim carry across the W;
4. the chin strap and facemask stay in front: on the cards the grey strap, any gold that is not the W (facemask,
   jersey trim) and texels where the card fades out are never painted;
5. the slot is re-quantised whole with the Studio's Team Select card quantiser (integer median cut), since the old
   palettes have almost no free entries for the new gold.

All arithmetic is integer, so the result is byte-identical on every platform; each slot is pinned before and after.
Only the exact known art changes (``before_sha256``); retail, older or user art is left alone.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from . import nfl2k5_historic_styles as hs

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_menu_helmet_w2026.json"
SCHEMA = "nfl2k5_menu_helmet_w2026/v1"
UNIT = 64                      # fixed-point units per texel for the transformed outline
SUPER = 8                      # samples per texel along each axis
SAMPLES = SUPER * SUPER
SHADE_LIMITS = (800, 1150)     # gold lighting relative to the shell, per mille
OPAQUE = 224                   # texels at or above this alpha are helmet surface (the card edge fades below it)
AGGREGATES = {
    "logos": dict(record=0x89ACDBBE, cdf=0x823E3053),
    "logos128": dict(record=0x3E59669F, cdf=0x35CB8D72),
    "mini": dict(record=0x436A7B61, cdf=0x48F8908C),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec(path=None) -> dict:
    with open(path or DATA, "rb") as stream:
        doc = json.loads(stream.read().decode("utf-8"))
    hs.require(doc.get("schema") == SCHEMA, "unknown menu helmet W document")
    return doc


# ----------------------------------------------------------------------------------------------- slot access
def read_slot(span: bytes):
    from tools import nfl_txtr as tx
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    hs.require(not chunk.compressed and texture.format_code == 0x0B and texture.mip_levels == 1,
               "menu helmet slot is not a single-level P8 texture")
    w, h = texture.width, texture.height
    base = 32 + chunk.system_bytes + texture.pixel_offset
    pal_at = 32 + chunk.system_bytes + texture.palette_offset
    indices = np.frombuffer(tx.unswizzle_2d(span[base:base + w * h], w, h, 1), np.uint8).reshape(h, w).copy()
    palette = np.frombuffer(span[pal_at:pal_at + 1024], np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]].astype(np.int64)
    return indices, palette, base


def project(transform, x, y):
    a, b, c, d, e, f, g, h = (list(transform) + [0.0, 0.0])[:8]
    w = g * x + h * y + 1.0
    return (a * x + b * y + c) / w, (d * x + e * y + f) / w


def placed(model, transform):
    """The strokes in fixed-point texel units of the slot."""
    return [[(int(round(px * UNIT)), int(round(py * UNIT))) for px, py in (project(transform, x, y) for x, y in s)]
            for s in model["strokes"]]


def _inside(poly, X, Y):
    inside = np.zeros(X.shape, bool)
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if ay == by:
            continue
        crosses = (ay > Y) != (by > Y)
        dy = by - ay
        lhs = (X - ax) * dy
        rhs = (Y - ay) * (bx - ax)
        inside ^= crosses & ((lhs < rhs) if dy > 0 else (lhs > rhs))
    return inside


def _clear_of(poly, X, Y, gap):
    """Samples at least ``gap`` (fixed units) from every edge of ``poly`` (exact: squared distances in int64)."""
    g2 = gap * gap
    clear = np.ones(X.shape, bool)
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        ex, ey = bx - ax, by - ay
        length = ex * ex + ey * ey
        if length == 0:
            continue
        px, py = X - ax, Y - ay
        t = px * ex + py * ey
        before = t <= 0
        after = t >= length
        d_a = px * px + py * py
        qx, qy = X - bx, Y - by
        d_b = qx * qx + qy * qy
        cross = px * ey - py * ex
        mid = cross * cross >= g2 * length
        clear &= np.where(before, d_a >= g2, np.where(after, d_b >= g2, mid))
    return clear


def coverage(model, transform, gap, box):
    """Covered samples (0..SAMPLES) per texel of ``box``: stroke k minus every stroke in front of it grown by gap."""
    x0, y0, x1, y1 = box
    step = UNIT // SUPER
    sub = np.arange(SUPER, dtype=np.int64) * step + step // 2
    sx = (np.arange(x0, x1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    sy = (np.arange(y0, y1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    X, Y = np.meshgrid(sx, sy)
    strokes = placed(model, transform)
    g = int(round(gap * UNIT))
    ink = np.zeros(X.shape, bool)
    for k, poly in enumerate(strokes):
        mine = _inside(poly, X, Y)
        for front in strokes[k + 1:]:
            mine &= ~_inside(front, X, Y) & _clear_of(front, X, Y, g)
        ink |= mine
    return ink.reshape(y1 - y0, SUPER, x1 - x0, SUPER).sum(axis=(1, 3)).astype(np.int64)


# ----------------------------------------------------------------------------------------------- paint
def _neighbours(mask):
    """8-neighbour views of a padded array: (dy, dx) shifted copies, same shape."""
    h, w = mask.shape[:2]
    pad = np.pad(mask, [(1, 1), (1, 1)] + [(0, 0)] * (mask.ndim - 2))
    return [pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def _dilate(mask):
    out = mask.copy()
    for view in _neighbours(mask):
        out |= view
    return out


def components(mask):
    """8-connected component labels of a small mask (0 = background), in scan order."""
    h, w = mask.shape
    labels = np.zeros((h, w), np.int64)
    current = 0
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or labels[y, x]:
                continue
            current += 1
            labels[y, x] = current
            stack = [(y, x)]
            while stack:
                cy, cx = stack.pop()
                for ny in (cy - 1, cy, cy + 1):
                    for nx in (cx - 1, cx, cx + 1):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                            labels[ny, nx] = current
                            stack.append((ny, nx))
    return labels, current


def classify(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gold = (r > 110) & (g > 55) & (b < 90) & (g > b + 30)
    grey = (rgb.max(axis=2) - rgb.min(axis=2) < 18) & ((r + g + b) > 180)
    return gold, grey


def fill(rgb, unknown, known):
    """Fill ``unknown`` texels from the outside in: each takes the integer mean of its known 8-neighbours."""
    out = rgb.copy()
    known = known.copy()
    todo = unknown & ~known
    while todo.any():
        total = np.zeros(out.shape, np.int64)
        count = np.zeros(out.shape[:2], np.int64)
        for colour, ok in zip(_neighbours(np.where(known[..., None], out, 0)), _neighbours(known)):
            total += colour
            count += ok
        ready = todo & (count > 0)
        if not ready.any():
            # texels cut off from the shell (only strap or card edge around them) take the shell's median colour
            hs.require(known.any(), "menu helmet W: no shell to fill the outline from")
            out[todo] = np.sort(out[known], axis=0)[int(known.sum()) // 2]
            break
        out[ready] = total[ready] // count[ready][:, None]
        known |= ready
        todo &= ~ready
    for _ in range(2):
        total = out.copy()
        count = np.ones(out.shape[:2], np.int64)
        for colour, ok in zip(_neighbours(out), _neighbours(np.ones(out.shape[:2], bool))):
            total += colour
            count += ok
        out = np.where(unknown[..., None], total // count[..., None], out)
    return out


def luma(rgb):
    return rgb[..., 0] * 299 + rgb[..., 1] * 587 + rgb[..., 2] * 114


def _isqrt(values):
    flat = [int(v) for v in values.ravel()]
    import math
    return np.array([math.isqrt(v) for v in flat], np.int64).reshape(values.shape)


def paint(span: bytes, model: dict, target: dict) -> tuple[bytes, dict]:
    indices, palette, base = read_slot(span)
    h, w = indices.shape
    x0, y0, x1, y1 = target["box"]
    hs.require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, "menu helmet box outside the slot")
    rgba = palette[indices]
    region = rgba[y0:y1, x0:x1]
    rgb, alpha = region[..., :3].copy(), region[..., 3]
    gold, grey = classify(rgb)
    if not target["strap"]:
        grey = np.zeros_like(grey)           # miniatures: no strap crosses the W; their grey is the shell's sheen
    cover = coverage(model, target["transform"], float(target["gap"]), (x0, y0, x1, y1))
    footprint = _dilate(_dilate(coverage(model, target["transform"], 0.0, (x0, y0, x1, y1)) > 0))
    labels, count = components(gold)
    mark = np.zeros(gold.shape, bool)
    for label in range(1, count + 1):
        piece = labels == label
        if 2 * int((piece & footprint).sum()) >= int(piece.sum()):
            mark |= piece                    # the old W's outline: mostly inside the new W's footprint
    other = gold & ~mark                     # facemask, jersey trim: kept, and never painted over
    opaque = alpha >= OPAQUE         # the shell carries alpha 242..255; only RGB is painted, alpha stays
    paintable = opaque & ~_dilate(grey) & ~_dilate(other)
    outline = _dilate(mark) & paintable
    shell = paintable & ~outline
    hs.require(mark.sum() >= 20 and shell.sum() >= 50, "menu helmet W not found in its box")
    filled = fill(rgb, outline, shell)
    cover = np.where(paintable, cover, 0)
    y_fill = luma(filled)
    y_ref = int(np.sort(y_fill[shell])[shell.sum() // 2])
    shade = np.clip(_isqrt(y_fill * 1_000_000 // max(y_ref, 1)), *SHADE_LIMITS)
    colour = model["gold"].lstrip("#")
    gold_unlit = np.array([int(colour[i:i + 2], 16) for i in (0, 2, 4)], np.int64) * int(model["exposure"]) // 1000
    lit = np.clip(gold_unlit[None, None, :] * shade[..., None] // 1000, 0, 255)
    out = (filled * (SAMPLES - cover[..., None]) + lit * cover[..., None] + SAMPLES // 2) // SAMPLES
    out = np.where(paintable[..., None], out, rgb)
    image = rgba.copy()
    image[y0:y1, x0:x1, :3] = out
    after = requantise(span, image, base)
    receipt = dict(member=target["member"], repainted_texels=int((out != rgb).any(axis=2).sum()),
                   covered_texels=int((cover > 0).sum()), gold_unlit="#%02X%02X%02X" % tuple(int(v) for v in gold_unlit))
    return after, receipt


def requantise(span: bytes, image: np.ndarray, base: int) -> bytes:
    """The whole slot re-quantised from RGBA with the Studio's Team Select card quantiser (median cut, integer)."""
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import nfl_tset_png_import as palette_tools
    from tools import nfl_txtr as tx
    h, w = image.shape[:2]
    level = palette_tools.MipLevel(0, w, h, image.astype(np.uint8).tobytes())
    palette, levels, _ = palette_tools.quantize_levels([level])
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    pal_at = 32 + chunk.system_bytes + texture.palette_offset
    out = bytearray(span)
    out[base:base + w * h] = tx.swizzle_2d(levels[0], w, h, 1)
    out[pal_at:pal_at + 1024] = palette_tools.palette_bytes(palette).ljust(1024, b"\0")
    hs.require(len(out) == len(span), "menu helmet slot length changed")
    return bytes(out)


# ----------------------------------------------------------------------------------------------- disc
def locate(archive, aggregate: str, name: str):
    entries = {e.name_id: e for e in archive.entries}
    ids = AGGREGATES[aggregate]
    record, cdf = entries[ids["record"]], entries[ids["cdf"]]
    count, size, hashes = hs.parse_record(archive.read(record.virtual_offset, record.size))
    hs.require(count * size == cdf.size, "menu aggregate size differs from its CACR record")
    offset = cdf.virtual_offset + hashes.index(hs.member_hash(name)) * size
    span = archive.read(offset, size)
    hs.require(hs.slot_name(span) == name, "menu aggregate hash/name mismatch")
    return offset, span


def plan_archive(archive, doc=None):
    doc = doc or spec()
    plan, rows = [], []
    for target in doc["targets"]:
        try:
            at, before = locate(archive, target["aggregate"], target["member"])
        except (ValueError, KeyError, hs.HistoricStylesError):
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="not_applicable"))
            continue
        digest = sha(before)
        if digest == target["after_sha256"]:
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="applied", written=0))
            continue
        if digest != target["before_sha256"]:
            rows.append(dict(member=target["member"], aggregate=target["aggregate"], state="not_applicable",
                             target_sha256=digest))
            continue
        after, receipt = paint(before, doc["model"], target)
        hs.require(sha(after) == target["after_sha256"], f"{target['member']} differs from its pin")
        plan.append((at, before, after))
        rows.append(dict(aggregate=target["aggregate"], state="applied", written=1, virtual_offset=at,
                         size=len(before), before_sha256=digest, after_sha256=sha(after),
                         changed_bytes=sum(a != b for a, b in zip(before, after)), **receipt))
    states = {r["state"] for r in rows}
    state = "applied" if states == {"applied"} else ("not_applicable" if "applied" not in states else "partial")
    return plan, dict(state=state, written=len(plan), slots=rows)


def apply_to_image(image, *, strict=False) -> dict:
    from tools.nfl2k5_playbook_position_recode import OuterImage
    try:
        archive_cm = OuterImage(Path(image), writable=True)
        archive = archive_cm.__enter__()
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written=0)
    try:
        plan, receipt = plan_archive(archive)
        hs.require(not strict or receipt["state"] == "applied", "the Washington menu helmets are not the known art")
        attempted = []
        try:
            for at, before, after in plan:
                hs.require(archive.read(at, len(before)) == before, "Washington menu helmet changed after preflight")
                attempted.append((at, before))
                hs.require(archive.write(at, after) == len(after), "short Washington menu helmet write")
                hs.require(archive.read(at, len(after)) == after, "Washington menu helmet read-back differs")
            replay, _ = plan_archive(archive)
            hs.require(not replay, "Washington menu helmet correction did not survive read-back")
        except BaseException:
            for at, before in reversed(attempted):
                archive.write(at, before)
            raise
    finally:
        archive_cm.__exit__(None, None, None)
    return receipt
