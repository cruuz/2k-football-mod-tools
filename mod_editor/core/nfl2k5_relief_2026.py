"""The 2026 jersey relief: this season's construction in the bump maps of every SOFTDRINK 2026 kit (beta 81).

Job b81-uniforms (Noah 11/18 on the first modern relief: "The jersey looks overly sculpted tbh, should be less obvious
and more accurate to the real thing"; 11/19, of the three strengths drawn from this season's close-ups: "B. Keep new.")
replaces the ``bump_jersey``, ``bump_sleeve`` and ``bump_pants`` maps of the 178 SOFTDRINK 2026 kit packages
(A8R8G8B8 tangent-space normal maps, R = +u, G = up, B = out) with level B of ``tools/b81_uniforms/bump_true.py``:

* jersey: the 2004 sculpt's folds softened (gain 0.8) with every 2004 construction detail lifted out, hairline seams,
  a flat collar band, two small vents, sparse pin holes below the V, and the collar shield barely raised under the
  kit's own painted shield (and any maker's mark the kit paints on the torso shoulder caps);
* sleeve: the master sleeve's folds, one hem hairline, the painted swoosh barely raised;
* pants: the kit's own pants sculpt with the 2004 shield and Reebok embosses lifted out, the painted swoosh and shield
  barely raised.

Retail-free storage (job b81-retail-free-art, schema v2). Each map is two layers:

* the BASE, which is retail-derived and therefore never ships: the Studio derives it at build time from the user's own
  disc with the exact arithmetic the art was authored with (``jersey_base``, ``sleeve_base``, ``pants_base``: a numpy
  port of bump_true's scipy steps, bit for bit). Jersey and sleeve start from the retail 18H0 maps read from the
  user's retail disc (pinned by their span SHA-256); pants start from the kit's own pants map as the image holds it.
  The base is the 2004 folds softened, with the 2004 construction lifted out, and nothing new;
* the DIFFERENCE, which is the project's own work and is what ships (``data/nfl2k5_relief_2026_b81u/``): per texel
  and channel the authored map minus the base, modulo 256, where this season's seams, collar band, vents, pin holes
  and embosses sit, and zero everywhere else. One difference master for the jersey and one for the sleeve, small
  per-kit difference patches (alpha 255 takes the patch texel, alpha 0 keeps the master's), each distinct patch once.
  The jersey also ships two one-bit layout masks, the inputs of its base that are not read from the disc: its UV
  island coverage (``islands_jersey.png``, 1024 x 512: where the folds stop) and the collar openings the art was
  drawn for (``openings_jersey.png``, one 512 x 256 mask per distinct opening, stacked: where the folds soften
  toward the collar). They hold no texel value of any map.

A map is composed with numpy only, its mip chain is the Studio bump writer's box filter, it is swizzled and packed into
the kit's own fixed compressed span (the retail packer first, the tighter optimal parse only when a span needs it), each
DISTINCT map compressed once and its stream reused for every slot that takes it. The wrapper, its loader scratch word
and the span size never change; each written span is read back.

Every slot is pinned: ``before_sha256`` is the stored span as a v0.10 build holds it after the earlier steps,
``composed_sha256`` the composed level-0 map, ``after_sha256`` the span this step writes. A Studio build (not strict)
leaves a slot alone when it holds anything else (a user's own bump art), and leaves the step alone when the retail
maps it needs are not the pinned ones; a second run writes nothing. Strict refuses both.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from . import build_steps
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import (HEADER, COMPRESSED_SENTINEL, TxtrError, check_vc_lz_native, compress_vc_lz, decode_chunk,
                      minimum_vc_lz_overlap_scratch, parse_chunks, parse_texture, swizzle_2d, texture_to_rgba)
from nfl_vc_lz_fill import compress_optimal, fill_stream

SCHEMA = "nfl2k5_relief_2026/v2"
ROOT = Path(__file__).resolve().parents[2]
DATA_B81U = ROOT / "data/nfl2k5_relief_2026_b81u.json"
SLOTS = ("bump_jersey", "bump_sleeve", "bump_pants")
BASES = ("retail", "before")
S = 2                                                   # the art is drawn on twice the native grid
FOLD_GAIN, FOLD_BLUR = 0.80, 1.8                        # level B (bump_true.LEVELS["B"])
OLD_PANTS = ((86, 36, 110, 56), (398, 36, 426, 56))     # the 2004 shield and Reebok embosses on every pants map


def require(ok, message):
    if not ok:
        raise ValueError("2026 jersey relief: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def spec(path=None):
    document = json.loads(Path(path or DATA_B81U).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document["slots"]:
        key = (row["selector"], row["slot"])
        require(key not in seen, "duplicate slot entry " + repr(key))
        seen.add(key)
        require(row["slot"] in SLOTS and row["base"] in BASES, "unknown slot or base")
        require((row["base"] == "retail") == (row["slot"] != "bump_pants"), "jersey and sleeve start from retail")
        require(row["base"] != "retail" or row["slot"] in document["masters"], "slot without its difference master")
        require(row["patch"] is None or document["patches"][row["patch"]]["slot"] == row["slot"], "patch of another slot")
        require(row["slot"] != "bump_jersey" or 0 <= row["opening"] < document["bases"]["bump_jersey"]["openings"]["count"],
                "jersey row without its collar opening")
    for slot in document["masters"]:
        require(slot in document["bases"], "difference master without its retail base")
    return document


def relief_b81u():
    """The b81-uniforms relief document (level B on the 178 SOFTDRINK 2026 kit packages)."""
    return spec(DATA_B81U)


def art_folder(document):
    name = document.get("art")
    require(isinstance(name, str) and name == Path(name).name and name.startswith("nfl2k5_relief_2026"),
            "unexpected art folder")
    return ROOT / "data" / name


def selectors(document=None):
    return sorted({r["selector"] for r in (document or relief_b81u())["slots"]})


# -- the shipped layers -----------------------------------------------------------------------------------------------

def read_art(folder, entry):
    """One authored PNG of the document as an (h, w, 4) uint8 array, checked against its pin and size."""
    payload = (Path(folder) / entry["png"]).read_bytes()
    require(sha(payload) == entry["sha256"], entry["png"] + " differs from its pin")
    width, height, rgba = decode_rgba_png(payload, (entry["width"], entry["height"]))
    return np.frombuffer(rgba, np.uint8).reshape(height, width, 4)


def compose(base, patch=None, at=(0, 0)):
    """``base`` with ``patch`` laid over it at ``at`` (x, y): texels of alpha 255 replace, alpha 0 keep. Alpha is
    255 everywhere in the result (these maps do not use it)."""
    out = np.array(base, np.uint8, copy=True)
    if patch is not None:
        x, y = at
        h, w = patch.shape[:2]
        require(0 <= x and 0 <= y and x + w <= out.shape[1] and y + h <= out.shape[0], "patch outside its map")
        take = patch[..., 3] == 255
        require(bool(np.all(take | (patch[..., 3] == 0))), "patch alpha is neither 0 nor 255")
        region = out[y:y + h, x:x + w]
        region[take] = patch[take]
    out[..., 3] = 255
    return out


def add_difference(base, difference):
    """The authored map: ``base`` plus ``difference`` per colour channel, modulo 256; alpha 255."""
    require(base.shape == difference.shape, "difference and base differ in size")
    out = np.empty(base.shape, np.uint8)
    out[..., :3] = (base[..., :3].astype(np.uint16) + difference[..., :3]) & 0xFF
    out[..., 3] = 255
    return out


def difference_of(authored, base):
    """The shipped layer: ``authored`` minus ``base`` per colour channel, modulo 256 (alpha 255)."""
    out = np.empty(authored.shape, np.uint8)
    out[..., :3] = (authored[..., :3].astype(np.int16) - base[..., :3]) & 0xFF
    out[..., 3] = 255
    return out


def islands(document, folder=None):
    entry = document["bases"]["bump_jersey"]["islands"]
    mask = read_art(folder or art_folder(document), entry)[..., 0] > 127
    require(mask.shape == (256 * S, 512 * S), "island mask size")
    return mask


def openings(document, folder=None):
    """The collar openings the jersey art was drawn for: a list of native 256 x 512 masks."""
    entry = document["bases"]["bump_jersey"]["openings"]
    stack = read_art(folder or art_folder(document), entry)[..., 0] > 127
    require(stack.shape == (256 * entry["count"], 512), "collar opening masks size")
    return [stack[256 * i:256 * (i + 1)] for i in range(entry["count"])]


# -- the base: an exact numpy port of bump_true's level B on the retail maps -------------------------------------------
# Every step below reproduces tools/b81_uniforms/bump_true.py (scipy.ndimage) to the bit: the Gaussian weights are the
# document's stored float64 values, sums run in scipy's order (centre, then the farthest pair first), and the masks are
# integer morphology. tests/mod_editor/test_b81_relief.py compares them with scipy where scipy is installed.

def _up2_axis(a, axis):
    """Pillow's BILINEAR 2x enlargement along one axis (22-bit fixed point, edge texels kept)."""
    a = np.moveaxis(a.astype(np.int64), axis, 0)
    prev = np.concatenate([a[:1], a[:-1]], 0)
    nxt = np.concatenate([a[1:], a[-1:]], 0)
    even = (a * 3145728 + prev * 1048576 + (1 << 21)) >> 22
    odd = (a * 3145728 + nxt * 1048576 + (1 << 21)) >> 22
    even[0] = a[0]
    odd[-1] = a[-1]
    out = np.empty((2 * a.shape[0],) + a.shape[1:], np.int64)
    out[0::2], out[1::2] = even, odd
    return np.moveaxis(np.clip(out, 0, 255).astype(np.uint8), 0, axis)


def decode_map(rgba):
    """A stored normal map on the 2x grid as signed components (bump_nike.decode: RGB, bilinear, /127.5 - 1)."""
    rgb = np.asarray(rgba, np.uint8)[..., :3]
    return _up2_axis(_up2_axis(rgb, 1), 0).astype(np.float64) / 127.5 - 1.0


class Kernels:
    """scipy.ndimage.gaussian_filter (truncate 4, mode reflect) with the document's stored weights."""

    def __init__(self, table):
        self.table = {}
        for sigma, weights in table.items():
            w = np.array([float.fromhex(x) for x in weights], np.float64)
            require(len(w) % 2 == 1 and len(w) // 2 == int(4.0 * float(sigma) + 0.5) and np.array_equal(w, w[::-1]),
                    "Gaussian weights for sigma %s" % sigma)
            self.table[float(sigma)] = w

    def line(self, a, sigma, axis):
        w = self.table[float(sigma)]
        r = len(w) // 2
        a = np.moveaxis(a, axis, -1)
        n = a.shape[-1]
        p = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(r, r)], mode="symmetric")
        out = p[..., r:r + n] * w[r]
        for j in range(r, 0, -1):
            out = out + (p[..., r - j:r - j + n] + p[..., r + j:r + j + n]) * w[r - j]
        return np.moveaxis(out, -1, axis)

    def __call__(self, a, sigma):
        a = np.asarray(a, np.float64)
        for axis in range(a.ndim):
            a = self.line(a, sigma, axis)
        return a

    def pair(self, sl, sigma):
        return np.stack([self(sl[..., i], sigma * S) for i in range(2)], -1)


def kernel_table(sigmas):
    """The Gaussian weights the authoring run used (scipy's _gaussian_kernel1d), as float64 hex: written into the
    document by the generator, so no platform's exp() is involved at build time."""
    out = {}
    for sigma in sigmas:
        sd = float(sigma)
        radius = int(4.0 * sd + 0.5)
        x = np.arange(-radius, radius + 1)
        phi = np.exp(-0.5 / (sd * sd) * x ** 2)
        phi = phi / phi.sum()
        out[repr(sd)] = [float(v).hex() for v in phi]
    return out


SIGMAS = (0.8 * S, 1.5 * S, 1.6 * S, FOLD_BLUR * S, 2.0 * S, 2.3 * S, 3.0 * S, 4.5 * S, 5.0 * S)


def dilate(mask, n=1):
    m = np.asarray(mask, bool)
    for _ in range(n):
        o = m.copy()
        o[1:] |= m[:-1]
        o[:-1] |= m[1:]
        o[:, 1:] |= m[:, :-1]
        o[:, :-1] |= m[:, 1:]
        m = o
    return m


def erode(mask, n=1):
    m = np.asarray(mask, bool)
    for _ in range(n):
        o = m.copy()
        o[1:] &= m[:-1]
        o[0] = False
        o[:-1] &= m[1:]
        o[-1] = False
        o[:, 1:] &= m[:, :-1]
        o[:, 0] = False
        o[:, :-1] &= m[:, 1:]
        o[:, -1] = False
        m = o
    return m


def components(mask):
    """4-connected components of a 2-D mask: (labels, 0 = background; sizes by label)."""
    m = np.asarray(mask, bool)
    height, width = m.shape
    parent = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    previous, rows = [], []
    for y in range(height):
        edges = np.diff(np.concatenate([[0], m[y].view(np.int8), [0]]))
        runs, j = [], 0
        for start, end in zip(np.nonzero(edges == 1)[0].tolist(), np.nonzero(edges == -1)[0].tolist()):
            rid = len(parent)
            parent.append(rid)
            while j < len(previous) and previous[j][1] <= start:
                j += 1
            k = j
            while k < len(previous) and previous[k][0] < end:
                a, b = find(rid), find(previous[k][2])
                if a != b:
                    parent[max(a, b)] = min(a, b)
                k += 1
            runs.append((start, end, rid))
        rows.append(runs)
        previous = runs
    labels = np.zeros((height, width), np.int64)
    roots, sizes = {}, [0]
    for y, runs in enumerate(rows):
        for start, end, rid in runs:
            root = find(rid)
            label = roots.get(root)
            if label is None:
                label = roots[root] = len(sizes)
                sizes.append(0)
            labels[y, start:end] = label
            sizes[label] += end - start
    return labels, np.array(sizes, np.int64)


def fill_holes(mask):
    labels, _sizes = components(~np.asarray(mask, bool))
    edge = set(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]).tolist()) - {0}
    return ~np.isin(labels, sorted(edge))


def distance_within(feature, cap):
    """Euclidean distance (2x pixels) to the nearest texel of ``feature``: exact below ``cap``, at least ``cap``
    beyond (scipy's distance_transform_edt is sqrt of the integer squared offset, so these are the same floats)."""
    height, width = feature.shape
    far = cap * cap * 4 + 1
    up = np.empty((height, width), np.int64)
    last = np.full(width, -(1 << 30), np.int64)
    for y in range(height):
        last = np.where(feature[y], y, last)
        up[y] = y - last
    down = np.empty((height, width), np.int64)
    last = np.full(width, 1 << 30, np.int64)
    for y in range(height - 1, -1, -1):
        last = np.where(feature[y], y, last)
        down[y] = last - y
    vertical = np.minimum(up, down)
    g = np.where(vertical <= cap, vertical * vertical, far)
    d2 = g.copy()
    for dx in range(1, cap + 1):
        d2[:, dx:] = np.minimum(d2[:, dx:], g[:, :-dx] + dx * dx)
        d2[:, :-dx] = np.minimum(d2[:, :-dx], g[:, dx:] + dx * dx)
    return np.sqrt(np.minimum(d2, far).astype(np.float64))


def slopes(nxy):
    nz = np.sqrt(np.clip(1.0 - (nxy ** 2).sum(-1), 0.04, 1.0))
    return nxy / nz[..., None]


def encode(nx, ny):
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.stack([nx / length, ny / length, nz / length], -1)
    return np.clip(np.round(out * 127.5 + 127.5), 0, 255).astype(np.uint8)


def reduce(slope):
    """Slopes on the 2x grid -> the native A8R8G8B8 map (bump_nike.reduce)."""
    rgb = encode(slope[..., 0], slope[..., 1]).astype(np.float64)
    h, w = rgb.shape[0] // S, rgb.shape[1] // S
    v = rgb.reshape(h, S, w, S, 3).mean(axis=(1, 3)) / 127.5 - 1.0
    v /= np.sqrt((v ** 2).sum(-1, keepdims=True)) + 1e-9
    rgb = np.clip(np.round(v * 127.5 + 127.5), 0, 255).astype(np.uint8)
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


def old_construction(gauss, xy):
    """Where the 2004 map carries mesh, piping and collar ribs (bump_nike.old_construction)."""
    lo = np.stack([gauss(xy[..., i], 1.6 * S) for i in range(2)], -1)
    energy = gauss(((xy - lo) ** 2).sum(-1), 3.0 * S)
    mesh = dilate(erode(energy > 0.035, 2 * S), 2 * S)
    labels, sizes = components(mesh)
    big = np.nonzero(sizes > 2500 * S * S)[0]
    mesh = np.isin(labels, big[big > 0])
    return fill_holes(erode(dilate(mesh, 3 * S), 3 * S))


def jersey_base(gauss, retail_rgba, opening, island):
    """Level B folds of the retail jersey sculpt with the 2004 construction lifted out, flat outside the islands."""
    r = decode_map(retail_rgba)
    xy = r[..., :2]
    sl = slopes(xy)
    old = old_construction(gauss, xy)
    old_soft = gauss(dilate(old, 5 * S).astype(np.float64), 1.5 * S)
    hole = gauss(np.repeat(np.repeat(opening, S, 0), S, 1).astype(np.float64), 0.8 * S) > 0.5
    dhole = distance_within(hole, 14 * S) / S
    collar_zone = np.clip(1.0 - (dhole - 9.0) / 5.0, 0, 1)
    sculpt = sl * (1 - old_soft)[..., None] + gauss.pair(sl, 2.3) * old_soft[..., None]
    thin = dilate(old & ~dilate(erode(old, 7 * S), 7 * S), 4 * S)
    thin_soft = gauss(thin.astype(np.float64), 2.0 * S)[..., None]
    sculpt = sculpt * (1 - thin_soft) + gauss.pair(sl, 4.5) * thin_soft
    sculpt = sculpt * (1 - collar_zone)[..., None] + gauss.pair(sl, 5.0) * 0.6 * collar_zone[..., None]
    folds = gauss.pair(sculpt, FOLD_BLUR) * FOLD_GAIN
    folds[~island] = 0
    return reduce(folds)


def sleeve_base(gauss, retail_rgba):
    """The retail sleeve's folds softened, faded out above each island's hem."""
    r = decode_map(retail_rgba)
    sl = gauss.pair(slopes(r[..., :2]), max(FOLD_BLUR, 1.6)) * FOLD_GAIN
    size = 128 * S
    rows = np.arange(size)[:, None].repeat(size, 1)
    for top in (0, 64 * S):
        t = (rows - top) / S
        island = (t >= 0) & (t < 64)
        sl = sl * np.clip((59.0 - t) / 3.0, 0, 1)[..., None] * island[..., None] + sl * (~island)[..., None]
    return reduce(sl)


def _membrane(field, region, iterations=4000):
    ys, xs = np.nonzero(region)
    y0, y1, x0, x1 = ys.min() - 1, ys.max() + 2, xs.min() - 1, xs.max() + 2
    f = field[y0:y1, x0:x1].astype(np.float64).copy()
    inside = region[y0:y1, x0:x1]
    f[inside] = f[~inside].mean()
    for _ in range(iterations):
        avg = 0.25 * (np.roll(f, 1, 0) + np.roll(f, -1, 0) + np.roll(f, 1, 1) + np.roll(f, -1, 1))
        f[inside] = avg[inside]
    out = field.copy()
    out[y0:y1, x0:x1] = f
    return out


def pants_base(gauss, before_rgba, worked):
    """The kit's own pants map with the 2004 shield and Reebok embosses lifted out (the surrounding folds laid
    through), its own bytes kept outside the worked boxes."""
    height, width = 256 * S, 512 * S
    require(np.asarray(before_rgba).shape == (256, 512, 4), "pants map size")
    sl = slopes(decode_map(before_rgba)[..., :2])
    for x0, y0, x1, y1 in OLD_PANTS:
        soft = np.zeros((height, width))
        soft[y0 * S:y1 * S, x0 * S:x1 * S] = 1
        soft = gauss(soft, 1.5 * S)[..., None]
        region = np.zeros((height, width), bool)
        region[max(y0 - 3, 0) * S:(y1 + 3) * S, max(x0 - 3, 0) * S:(x1 + 3) * S] = True
        filled = np.stack([_membrane(sl[..., i], region) for i in range(2)], -1)
        sl = sl * (1 - soft) + filled * soft
    lifted = reduce(sl)
    out = np.array(before_rgba, np.uint8, copy=True)
    for x0, y0, x1, y1 in worked:
        box = (slice(max(y0 - 4, 0), y1 + 4), slice(max(x0 - 4, 0), x1 + 4))
        out[box] = lifted[box]
    out[..., 3] = 255
    return out


def _texture(span):
    chunk = parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    return np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)


def retail_maps(document, retail):
    """The retail maps the jersey and sleeve bases start from, read from the user's retail disc and checked against
    their pins; None when the disc does not hold them."""
    want = document["bases"]
    selector = {entry["selector"] for entry in want.values()}
    require(len(selector) == 1, "one retail package")
    (selector,) = selector
    try:
        with bump._Image.open(Path(retail), writable=False) as image:
            index = bump._parsed_index(image)
            found = [e for e in index.entries if bump.logical_name_for(e.name_id) == selector + ".IFF"]
            if len(found) != 1:
                return None
            raw = image.read_segments(index.sub_extents(found[0], 0, found[0].size))
    except (ValueError, OSError):
        return None
    out = {}
    for slot, entry in want.items():
        chunk = _chunk_for(raw, entry["chunk"])
        span = raw[chunk.offset:chunk.end_offset]
        if sha(span) != entry["span_sha256"]:
            return None
        out[slot] = _texture(span)
    return out


def _base_job(job):
    kind, table, payload = job
    gauss = Kernels(table)
    if kind == "bump_jersey":
        retail, opening, island = payload
        return jersey_base(gauss, retail, opening, island)
    if kind == "bump_sleeve":
        return sleeve_base(gauss, payload)
    before, worked = payload
    return pants_base(gauss, before, worked)


# -- packing into a fixed span ----------------------------------------------------------------------------------------

def mip_levels(rgba, levels):
    """The bump writer's box-filter chain (``generate_mips``: each texel the rounded mean of its four parents,
    ``(a + b + c + d + 2) // 4`` per channel), in numpy."""
    out = [np.ascontiguousarray(rgba, np.uint8)]
    for _ in range(1, levels):
        a = out[-1].astype(np.uint16)
        require(a.shape[0] % 2 == 0 and a.shape[1] % 2 == 0, "map cannot be halved exactly")
        s = a[0::2, 0::2] + a[0::2, 1::2] + a[1::2, 0::2] + a[1::2, 1::2]
        out.append(((s + 2) // 4).astype(np.uint8))
    return out


def body(system, rgba, levels):
    """The decoded TXTR body: the slot's own system buffer, then the swizzled B,G,R,A mip chain."""
    chain = []
    for level in mip_levels(rgba, levels):
        bgra = level[..., [2, 1, 0, 3]]
        chain.append(swizzle_2d(np.ascontiguousarray(bgra).tobytes(), level.shape[1], level.shape[0], 4))
    return bytes(system) + b"".join(chain)


def fit(template_span, decoded, compressed):
    """``nfl_vc_lz_fill.rebuild_fixed_span_filled`` for a stream compressed once for several slots, with the bump
    writer's fill slack: fill it to this slot's stored body inside the retail loader scratch allowance, keep the
    wrapper exactly, check it natively and by an independent decode."""
    raw_kind, stored_size, system_bytes, video_bytes, magic, scratch, _r0, _r1 = HEADER.unpack_from(template_span)
    require(magic == COMPRESSED_SENTINEL and len(decoded) == system_bytes + video_bytes, "not this slot's body")
    require(len(compressed) <= stored_size, "stream longer than the stored body")
    chunk = parse_chunks(template_span, allow_trailing=True)[0]
    # the bump writer's tail slack: all 16 bytes of the common retail allowance as slack can need 17 when the last
    # token crosses a flag group
    filled, _ = fill_stream(compressed, decoded, stored_size, slack=min(scratch, 8))
    padding = stored_size - len(filled)
    exact = minimum_vc_lz_overlap_scratch(filled, stored_size, len(decoded))
    require(padding <= scratch and exact <= scratch, "cannot keep the retail scratch word (stream %d, filled %d, stored "
            "%d, padding %d, needs %d, retail %d)" % (len(compressed), len(filled), stored_size, padding, exact, scratch))
    rebuilt = template_span[:HEADER.size] + filled + bytes(padding)
    try:
        check_vc_lz_native(rebuilt[HEADER.size:], stored_size, scratch, decoded)
    except TxtrError:
        require(scratch != 0, "native check failed with no scratch")
        filled, _ = fill_stream(compressed, decoded, stored_size - 1, slack=0)
        padding = stored_size - len(filled)
        exact = minimum_vc_lz_overlap_scratch(filled, stored_size, len(decoded))
        require(padding <= scratch and exact <= scratch, "native-safe fill cannot keep the retail scratch word")
        rebuilt = template_span[:HEADER.size] + filled + bytes(padding)
        check_vc_lz_native(rebuilt[HEADER.size:], stored_size, scratch, decoded)
    back, info = decode_chunk(rebuilt, chunk)
    require(back == decoded and len(rebuilt) == len(template_span) and info.consumed_bytes == len(filled),
            "filled span failed its independent decode")
    return rebuilt


def _stream_facts(span):
    chunk = parse_chunks(span, allow_trailing=True)[0]
    require(chunk.kind == "TXTR" and chunk.compressed and chunk.end_offset == len(span), "not one compressed TXTR span")
    stream = span[chunk.body_offset:chunk.end_offset]
    system = bump._decompress_prefix(stream, chunk.output_size, chunk.system_bytes)
    texture = parse_texture(system, chunk)
    return chunk, system, texture, int.from_bytes(stream[4:8], "little"), stream[8]


def _job(job):
    """One distinct map: build its body, compress it once, fit it into every slot that takes it.
    job = (composed sha256, (RGBA bytes, shape), [(key, before span), ...]) -> [(key, after span, detail), ...]"""
    composed_sha, (data, shape), slots = job
    facts = [_stream_facts(span) for _key, span in slots]
    chunk, system, texture = facts[0][:3]
    for other in facts[1:]:
        require(other[1] == system, "slots of one map differ in their system buffer")
    rgba = np.frombuffer(data, np.uint8).reshape(shape)
    require(rgba.shape == (texture.height, texture.width, 4), "map size differs from the slot")
    require(sha(rgba.tobytes()) == composed_sha, "composed map differs from its pin")
    decoded = body(system, rgba, texture.mip_levels)
    require(len(decoded) == chunk.output_size, "mip chain does not fill the slot's allocation")
    streams = {}
    out = []
    for (key, span), (slot_chunk, _s, _t, tag, offset_bits) in zip(slots, facts):
        stored = slot_chunk.stored_size
        greedy = streams.get(("greedy", tag, offset_bits))
        if greedy is None:
            greedy = streams[("greedy", tag, offset_bits)] = compress_vc_lz(
                decoded, stream_tag=tag, offset_bits=offset_bits, verify_roundtrip=True)[0]
        encoder, stream = "greedy", greedy
        if len(greedy) > stored:
            encoder, stream = "optimal", streams.get(("optimal", tag, offset_bits))
            if stream is None:
                stream = streams[("optimal", tag, offset_bits)] = compress_optimal(decoded, stream_tag=tag,
                                                                                   offset_bits=offset_bits)
            require(len(stream) <= stored, "map needs %d bytes, more than its %d-byte span" % (len(stream), stored))
        out.append((key, fit(span, decoded, stream), dict(encoder=encoder, packed_bytes=len(stream), stored_size=stored)))
    return out


def workers(count=None):
    return count or min(8, max(1, (os.cpu_count() or 2) - 1))


def _pool_map(function, jobs, count):
    if count > 1 and len(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=count) as pool:
            yield from pool.map(function, jobs, chunksize=1)
    else:
        yield from map(function, jobs)


def compose_maps(rows, spans, document, retail, *, count=None, progress=None):
    """{(selector, slot): before span} for the given rows and the retail maps (``retail_maps``) ->
    {(selector, slot): composed level-0 RGBA}: the base derived from the disc plus the shipped difference. Every
    composed map is checked against its pin."""
    folder = art_folder(document)
    table = document["gauss_kernels"]
    masters = {name: read_art(folder, entry) for name, entry in document["masters"].items()}
    jersey = any(r["slot"] == "bump_jersey" for r in rows)
    island = islands(document, folder) if jersey else None
    collars = openings(document, folder) if jersey else None
    keys, jobs, base_of = {}, [], {}
    for row in rows:
        key = (row["selector"], row["slot"])
        if row["slot"] == "bump_jersey":
            job_key = ("bump_jersey", row["opening"])
            payload = (retail["bump_jersey"], collars[row["opening"]], island)
        elif row["slot"] == "bump_sleeve":
            job_key, payload = ("bump_sleeve",), retail["bump_sleeve"]
        else:
            before = _texture(spans[key])
            worked = [tuple(b) for b in row["worked"]]
            job_key = ("bump_pants", sha(before.tobytes()), repr(worked))
            payload = (before, worked)
        base_of[key] = job_key
        if job_key not in keys:
            keys[job_key] = len(jobs)
            jobs.append((row["slot"], table, payload))
    say = progress or (lambda message, done, total: None)
    say("The 2026 jersey relief: deriving %d base maps from the disc" % len(jobs), 0, len(jobs))
    bases = []
    for index, base in enumerate(_pool_map(_base_job, jobs, workers(count))):
        bases.append(base)
        say("The 2026 jersey relief: %d of %d base maps derived" % (index + 1, len(jobs)), index + 1, len(jobs))
    patches = {}
    out = {}
    for row in rows:
        key = (row["selector"], row["slot"])
        base = bases[keys[base_of[key]]]
        if row["slot"] in masters:
            difference = masters[row["slot"]]
        else:
            difference = np.zeros(base.shape, np.uint8)
        if row["patch"] is not None:
            entry = document["patches"][row["patch"]]
            if row["patch"] not in patches:
                patches[row["patch"]] = read_art(folder, entry)
            difference = compose(difference, patches[row["patch"]], (entry["x"], entry["y"]))
        composed = add_difference(base, difference)
        require(sha(composed.tobytes()) == row["composed_sha256"],
                "%s %s: the base derived from this disc plus the shipped difference is not the authored map" % key)
        out[key] = composed
    return out


def authored_map(document, row, retail, before_rgba=None):
    """One slot's authored level-0 map outside a build (the Team Select card tools): the base derived from the retail
    maps (``retail_maps``) or, for pants, from ``before_rgba`` (the slot's input map), plus the shipped difference;
    checked against its pin."""
    gauss = Kernels(document["gauss_kernels"])
    folder = art_folder(document)
    if row["slot"] == "bump_jersey":
        base = jersey_base(gauss, retail["bump_jersey"], openings(document, folder)[row["opening"]], islands(document, folder))
    elif row["slot"] == "bump_sleeve":
        base = sleeve_base(gauss, retail["bump_sleeve"])
    else:
        base = pants_base(gauss, before_rgba, [tuple(b) for b in row["worked"]])
    if row["slot"] in document["masters"]:
        difference = read_art(folder, document["masters"][row["slot"]])
    else:
        difference = np.zeros(base.shape, np.uint8)
    if row["patch"] is not None:
        entry = document["patches"][row["patch"]]
        difference = compose(difference, read_art(folder, entry), (entry["x"], entry["y"]))
    composed = add_difference(base, difference)
    require(sha(composed.tobytes()) == row["composed_sha256"], "%s %s: composed map differs from its pin" %
            (row["selector"], row["slot"]))
    return composed


def compile_slots(rows, spans, document=None, *, retail=None, count=None, progress=None):
    """{(selector, slot): before span} for the given document rows -> {(selector, slot): (after span, detail)}.
    Rows that take the same composed map share one compressed stream."""
    document = document or relief_b81u()
    composed = compose_maps(rows, spans, document, retail, count=count, progress=progress)
    groups, maps = {}, {}
    for row in rows:
        key = (row["selector"], row["slot"])
        groups.setdefault(row["composed_sha256"], []).append((key, spans[key]))
        maps[row["composed_sha256"]] = composed[key]
    jobs = [(digest, (maps[digest].tobytes(), maps[digest].shape), slots) for digest, slots in groups.items()]
    jobs.sort(key=lambda job: -sum(len(span) for _k, span in job[2]))
    say = progress or (lambda message, done, total: None)
    results = {}
    say("The 2026 jersey relief: packing %d distinct maps into %d slots" % (len(jobs), len(rows)), 0, len(jobs))
    for index, out in enumerate(_pool_map(_job, jobs, workers(count))):
        for key, span, detail in out:
            results[key] = (span, detail)
        say("The 2026 jersey relief: %d of %d maps packed" % (index + 1, len(jobs)), index + 1, len(jobs))
    return results


# -- the image ------------------------------------------------------------------------------------------------------

def _chunk_for(raw, index):
    for chunk in parse_chunks(raw, allow_trailing=True):
        if chunk.index == index:
            return chunk
    raise ValueError("2026 jersey relief: chunk %d absent" % index)


def state_of(row, raw):
    """("before" | "after" | "other", chunk, span) of one pinned slot in its package bytes."""
    chunk = _chunk_for(raw, row["chunk"])
    span = raw[chunk.offset:chunk.end_offset]
    layout_ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
    digest = sha(span) if layout_ok else None
    state = "before" if digest == row["before_sha256"] else "after" if digest == row["after_sha256"] else "other"
    return state, chunk, span


def apply_to_image(path, retail=None, *, strict=False, document=None, count=None, progress=None):
    """Studio build step: the pinned bump spans only. ``retail`` is the user's retail disc (a path, or a callable
    returning one), read only when a slot is written. Not strict, a slot holding anything but its pinned input (or
    its finished output) is left alone, and so is the whole step when the retail disc does not hold the pinned maps;
    strict refuses both. Every write is read back."""
    document = document or relief_b81u()
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            names = {bump.logical_name_for(e.name_id) for e in index.entries}
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written_spans=0, written_bytes=0, skipped_slots=[], kits=[])
    wanted = selectors(document)
    if not strict and not all(s + ".IFF" in names for s in wanted):
        return dict(state="other_uniform", written_spans=0, written_bytes=0, skipped_slots=[], kits=[])
    by_selector = {}
    for row in document["slots"]:
        by_selector.setdefault(row["selector"], []).append(row)
    written, written_bytes, skipped, todo, spans, places, kits = 0, 0, [], [], {}, {}, {}
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        entries = {}
        for entry in index.entries:
            entries.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        # Preflight every slot before the first write, so a refusal leaves the image untouched.
        for selector in wanted:
            found = entries.get(selector + ".IFF", [])
            require(len(found) == 1, selector + " kit package absent or duplicated")
            entry = found[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            with build_steps.resource(selector + ".IFF"):
                for row in by_selector[selector]:
                    state, chunk, span = state_of(row, raw)
                    kits.setdefault(selector, dict(selector=selector, written=[], kept=[], skipped=[]))
                    if state == "after":
                        kits[selector]["kept"].append(row["slot"])
                        continue
                    if state == "other":
                        require(not strict, "%s %s: unknown input hash" % (selector, row["slot"]))
                        skipped.append("%s:%s" % (selector, row["slot"]))
                        kits[selector]["skipped"].append(row["slot"])
                        continue
                    key = (selector, row["slot"])
                    todo.append(row)
                    spans[key] = span
                    places[key] = (entry, chunk.offset)
        if todo:
            maps = None
            if any(r["base"] == "retail" for r in todo):
                source = retail() if callable(retail) else retail
                maps = retail_maps(document, source) if source is not None else None
                if maps is None:
                    require(not strict, "the retail disc does not hold the pinned 18H0 jersey and sleeve maps")
                    return dict(state="no_retail_base", written_spans=0, written_bytes=0,
                                skipped_slots=["%s:%s" % (r["selector"], r["slot"]) for r in todo], kits=[])
            results = compile_slots(todo, spans, document, retail=maps, count=count, progress=progress)
            for row in todo:
                key = (row["selector"], row["slot"])
                new, _detail = results[key]
                require(len(new) == len(spans[key]) and new[:HEADER.size] == spans[key][:HEADER.size],
                        "%s %s: wrapper or span size changed" % key)
                require(sha(new) == row["after_sha256"], "%s %s: Studio compile differs from its output pin" % key)
            for row in todo:
                key = (row["selector"], row["slot"])
                new = results[key][0]
                entry, offset = places[key]
                segments = index.sub_extents(entry, offset, len(new))
                image.write_segments(segments, new)
                require(image.read_segments(segments) == new, "written span read-back differs")
                written += 1
                written_bytes += len(new)
                kits[row["selector"]]["written"].append(row["slot"])
    nothing_known = skipped and not written and not any(k["kept"] for k in kits.values())
    return dict(state="other_uniform" if nothing_known else "applied", written_spans=written, written_bytes=written_bytes, skipped_slots=skipped,
                kits=list(kits.values()))


def apply_relief_b81u(path, retail=None, *, strict=False, progress=None):
    """Studio uniform finish pass for the b81-uniforms relief, after the uniform pass numbers: pinned spans only.
    ``retail``: the user's retail disc (path or callable), where the jersey and sleeve bases come from."""
    return apply_to_image(path, retail, strict=strict, document=relief_b81u(), progress=progress)
