"""Afternoon field shadows cast by the stadium the bundle really carries (Beta 77 st1).

What the game draws (PROVED OFFLINE from default.xbe and PROVED IN GAME in st1's xemu labs, 2026-10-12):

* Only the afternoon dry bundles (``sNNad.iff``; Time Of Day "Afternoon", or a franchise game at 4 or 5 PM) of the
  outdoor venues carry a TXTR named ``shadow`` (34 of the 42 retail venues; s07 and s37 also in their day bundle). It is
  256 x 256 P8, one mip, black with 16 alpha levels: alpha 254 is shadow, 0 is sunlit.
* ``FUN_0009c160`` binds it as the third texture of the detail layer (``E_detail``, the field and its border) and writes
  the float 0x38DE9A9E (1.0614585e-4 per cm) into the detail material; the renderer multiplies it by the shape's UV
  constant (0.501) into vertex-shader constant c[-89], so the shadow is a planar map of the world x and z: one texture
  is 188.04 m, 0.7345 m per texel, centred on the field (texel 128 at x = z = 0), u along +x and v along +z (st1 lab
  run05: 10-yard bands land on the painted yard lines and a marker at +x, -z lands at +x, -z).
* The detail pass's final combiner is ``r0 * r0.a * (1 - shadow.a)`` added to the field, so the shadow takes away the
  sunlit sheen; the field under it reads about 0.45 of the sunlit field.

Retail baked each venue's texture from its own 2004 stadium with one sun per venue (the retail Giants Stadium
texture is the shadow of that model's stands and light towers under a sun at azimuth 315 degrees, elevation 35
degrees: 98 percent of the field texels agree). A modern stadium model kept the retail texture, so its field showed
the old stadium's shadow. ``bundle_shadow`` casts the stadium scene the bundle carries under the same sun (the venue
table ``data/nfl2k5_stadium_shadow/venues.json``) and writes it in the retail format inside the chunk's fixed span.

Every value is plain IEEE arithmetic (no C library transcendental functions, no BLAS), so the bytes are the same on
every platform; the sun direction goes through ``exact_math``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import exact_math as math

OWNER = "nfl2k5_stadium_shadow"
LABEL = "EXPERIMENTAL"
ROOT = Path(__file__).resolve().parents[2]
VENUES_PATH = ROOT / "data" / "nfl2k5_stadium_shadow" / "venues.json"
VENUES_SCHEMA = "nfl2k5_stadium_shadow_venues/v1"
SHADOW_NAME = "shadow"
SIZE = 256
#: FUN_0009c160 writes this float into the detail material (+0x20, +0x24); the E_detail shape's UV constant (0.501)
#: scales it (FUN_00024160 builds c[-89] from both), so one texture spans 1 / (0.501 x 1.0614585e-4) cm
DETAIL_SCALE = struct.unpack("<f", struct.pack("<I", 0x38DE9A9E))[0]
SHAPE_UV_SCALE = 0.501
TEXTURE_M = 1.0 / (SHAPE_UV_SCALE * DETAIL_SCALE * 100.0)
TEXEL_M = TEXTURE_M / SIZE
CENTRE = 128
#: texels around the centre the detail layer can sample: E_detail spans x +-26.21 m and z +-56.69 m (35.7 and 77.2
#: texels); four texels of margin. Everything outside is shadow, as retail authors it.
WINDOW_U, WINDOW_V = 40, 82
#: the alpha levels of the retail textures (s13ad's sixteen; s18ad carries the same ramp)
LEVELS = (0, 24, 40, 56, 71, 87, 103, 119, 135, 151, 167, 183, 199, 215, 231, 254)
SUPERSAMPLE = 4
#: field-level props retail did not bake (benches, heaters, carts, the yard markers) and the environment backdrop
PROP_PREFIXES = ("sideline", "env_", "Bench", "Fan", "Heater", "towels", "Snow", "pylon", "lambert1_new", "yardfront",
                 "yardside")
#: a triangle wholly below this height (metres) lies on the ground and casts nothing
GROUND_M = 0.3

STRIP, QUADS, TRIANGLES, FAN, QUAD_STRIP = 6, 8, 5, 7, 9


class StadiumShadowError(ValueError):
    """A plain refusal before any mutation."""


def require(ok, message):
    if not ok:
        raise StadiumShadowError(message)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


_VENUES = None


def venues():
    """{prefix: row} of the venue table (the retail sun per venue and how it was found)."""
    global _VENUES
    if _VENUES is None:
        require(VENUES_PATH.is_file(), "the stadium shadow venue table is missing from this build")
        doc = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
        require(doc.get("schema") == VENUES_SCHEMA, "unsupported stadium shadow venue table")
        _VENUES = doc["venues"]
    return _VENUES


def sun_vector(azimuth_deg, elevation_deg):
    """Unit vector toward the sun: azimuth from +z toward +x, elevation above the field."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    ce = math.cos(e)
    return (ce * math.sin(a), math.sin(e), ce * math.cos(a))


def venue_sun(prefix):
    row = venues().get(prefix)
    require(row is not None and "sun" in row, f"{prefix}: no sun in the stadium shadow venue table")
    return sun_vector(row["sun"]["azimuth_deg"], row["sun"]["elevation_deg"])


# --- the stadium's triangles ------------------------------------------------------------------------------------

def _triangles(words):
    from . import nfl2k5_scne_builder as sb
    out = []
    for mode, ix in sb.decode_words(words):
        if mode == STRIP:
            out += [(ix[k], ix[k + 1], ix[k + 2]) for k in range(len(ix) - 2)]
        elif mode == TRIANGLES:
            out += [tuple(ix[k:k + 3]) for k in range(0, len(ix) - 2, 3)]
        elif mode == FAN:
            out += [(ix[0], ix[k], ix[k + 1]) for k in range(1, len(ix) - 1)]
        elif mode == QUADS:
            for k in range(0, len(ix) - 3, 4):
                a, b, c, d = ix[k:k + 4]
                out += [(a, b, c), (a, c, d)]
        elif mode == QUAD_STRIP:
            for k in range(0, len(ix) - 3, 2):
                a, b, c, d = ix[k:k + 4]
                out += [(a, b, d), (a, d, c)]
    return [t for t in out if len(set(t)) == 3]


def occluders(decoded, system_bytes, skip=()):
    """(N, 3, 3) float64 world triangles in metres of a decoded stadium scene that can cast onto the field; ``skip``
    names materials that let the sun through (a venue's translucent roof panels). Retail's bakes cast every other
    material, the alpha-tested ones included (its light towers' lattices read solid)."""
    import numpy as np
    from . import nfl2k5_scne_builder as sb
    scene = sb.parse(decoded, system_bytes)
    identity = struct.pack("<16f", *(1.0 if i % 5 == 0 else 0.0 for i in range(16)))
    drawn = {}
    for node in scene.nodes:
        require(node.matrix14 == identity, f"{scene.name}: node {node.name} is not at the origin")
        drawn[node.shape_name] = drawn.get(node.shape_name, 0) + 1
    tris = []
    for shape in scene.shapes:
        if not drawn.get(shape.name):
            continue
        pos = np.asarray(sb.shape_positions(shape), dtype=np.float64) / 100.0
        for sub in shape.submeshes:
            name = scene.materials[sub.material].name or ""
            if name.startswith(PROP_PREFIXES) or name in skip:
                continue
            idx = _triangles(sub.words)
            if idx:
                tris.append(pos[np.asarray(idx, dtype=np.int64)])
    require(tris, f"{scene.name}: no triangles")
    t = np.concatenate(tris)
    return t[(t[:, :, 1] > GROUND_M).any(axis=1)]


# --- the cast -----------------------------------------------------------------------------------------------------

def coverage(tris, sun):
    """{0..SUPERSAMPLE**2} shadow samples per texel (int array SIZE x SIZE) inside the window, the rest full."""
    import numpy as np
    s = SUPERSAMPLE
    lx, ly, lz = (float(v) for v in sun)
    require(ly > 0, "the sun is below the horizon")
    y = np.maximum(tris[:, :, 1], 0.0)
    gx = tris[:, :, 0] - (y / ly) * lx
    gz = tris[:, :, 2] - (y / ly) * lz
    u = CENTRE + gx / TEXEL_M
    v = CENTRE + gz / TEXEL_M
    u0, u1, v0, v1 = CENTRE - WINDOW_U, CENTRE + WINDOW_U, CENTRE - WINDOW_V, CENTRE + WINDOW_V
    mask = np.zeros(((v1 - v0) * s, (u1 - u0) * s), dtype=bool)
    offs = (np.arange(s, dtype=np.float64) + 0.5) / s
    for k in range(len(tris)):
        ax, bx, cx = u[k]
        ay, by, cy = v[k]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if area == 0.0:
            continue
        if area < 0.0:
            bx, cx, by, cy = cx, bx, cy, by
        iu0 = max(u0, int(np.floor(min(ax, bx, cx))))
        iu1 = min(u1, int(np.floor(max(ax, bx, cx))) + 1)
        iv0 = max(v0, int(np.floor(min(ay, by, cy))))
        iv1 = min(v1, int(np.floor(max(ay, by, cy))) + 1)
        if iu0 >= iu1 or iv0 >= iv1:
            continue
        px = (np.arange(iu0, iu1, dtype=np.float64)[:, None] + offs[None, :]).reshape(-1)[None, :]
        py = (np.arange(iv0, iv1, dtype=np.float64)[:, None] + offs[None, :]).reshape(-1)[:, None]
        inside = (((bx - ax) * (py - ay) - (by - ay) * (px - ax)) >= 0.0) \
            & (((cx - bx) * (py - by) - (cy - by) * (px - bx)) >= 0.0) \
            & (((ax - cx) * (py - cy) - (ay - cy) * (px - cx)) >= 0.0)
        mask[(iv0 - v0) * s:(iv1 - v0) * s, (iu0 - u0) * s:(iu1 - u0) * s] |= inside
    counts = np.full((SIZE, SIZE), s * s, dtype=np.int64)
    counts[v0:v1, u0:u1] = mask.reshape(v1 - v0, s, u1 - u0, s).sum(axis=(1, 3))
    return counts


def alpha_levels(counts):
    """The retail format: a light [1, 6, 1] softening across texels (retail edges are about a texel soft: 7.5 percent
    of the window's texels sit between the end levels, 3.9 unsoftened and 9.8 with this), then the nearest of the
    sixteen retail alpha levels, all in integers. Outside the window stays full shadow."""
    import numpy as np
    full = SUPERSAMPLE * SUPERSAMPLE
    c = np.asarray(counts, dtype=np.int64)
    p = np.pad(c, 1, mode="edge")
    h = p[:, :-2] + 6 * p[:, 1:-1] + p[:, 2:]
    b = h[:-2, :] + 6 * h[1:-1, :] + h[2:, :]                 # 0 .. 64 * full
    levels = np.asarray(LEVELS, dtype=np.int64)
    # nearest level to 254 * b / (64 * full): compare |254 * b - level * 64 * full| exactly (first level on a tie)
    err = np.abs(254 * b[..., None] - levels[None, None, :] * (64 * full))
    out = levels[err.argmin(axis=-1)].astype(np.uint8)
    u0, u1, v0, v1 = CENTRE - WINDOW_U, CENTRE + WINDOW_U, CENTRE - WINDOW_V, CENTRE + WINDOW_V
    keep = np.full((SIZE, SIZE), 254, dtype=np.uint8)
    keep[v0:v1, u0:u1] = out[v0:v1, u0:u1]
    return keep


def cast(decoded, system_bytes, sun, skip=()):
    """The shadow alpha (SIZE x SIZE uint8, row = v, column = u) of one decoded stadium scene under ``sun``."""
    return alpha_levels(coverage(occluders(decoded, system_bytes, skip), sun))


# --- the TXTR -------------------------------------------------------------------------------------------------------

def _tools():
    from . import nfl2k5_modern_metlife as ml
    return ml._tools()[0], ml


def shadow_chunk(bundle):
    """(chunk, decoded, texture info) of the bundle's ``shadow`` TXTR, or None."""
    tx, _ml = _tools()
    for chunk in tx.parse_chunks(bundle, allow_trailing=True):
        if chunk.kind != "TXTR":
            continue
        decoded, _ = tx.decode_chunk(bundle, chunk)
        info = tx.parse_texture(decoded, chunk)
        if info.name == SHADOW_NAME:
            return chunk, decoded, info
    return None


def read_alpha(bundle):
    """The shadow alpha of a bundle (row = v), or None when it has no shadow."""
    import numpy as np
    found = shadow_chunk(bundle)
    if found is None:
        return None
    chunk, decoded, info = found
    tx, _ml = _tools()
    rgba = np.frombuffer(tx.texture_to_rgba(decoded, chunk, info), dtype=np.uint8).reshape(info.height, info.width, 4)
    return rgba[..., 3].copy()


def encode(decoded, chunk, info, alpha):
    """The decoded TXTR with ``alpha`` as its one level: black entries carrying the levels, swizzled indices."""
    import numpy as np
    tx, _ml = _tools()
    require(info.format_name == "P8" and (info.width, info.height, info.mip_levels) == (SIZE, SIZE, 1),
            "the shadow is not the 256 x 256 one-level P8 texture")
    a = np.asarray(alpha, dtype=np.uint8)
    require(a.shape == (SIZE, SIZE) and set(np.unique(a).tolist()) <= set(LEVELS), "shadow alpha off the retail levels")
    palette = bytearray(1024)
    lut = np.zeros(256, dtype=np.uint8)
    for i, level in enumerate(LEVELS):
        palette[i * 4 + 3] = level
        lut[level] = i
    out = bytearray(decoded)
    at = chunk.system_bytes
    out[at + info.pixel_offset:at + info.pixel_offset + SIZE * SIZE] = tx.swizzle_2d(lut[a].tobytes(), SIZE, SIZE, 1)
    out[at + info.palette_offset:at + info.palette_offset + 1024] = palette
    return bytes(out)


def write_shadow(bundle, alpha):
    """(bundle of the same size with the shadow replaced inside its fixed span, receipt)."""
    tx, ml = _tools()
    found = shadow_chunk(bundle)
    require(found is not None, "the bundle has no shadow texture")
    chunk, decoded, info = found
    new = encode(decoded, chunk, info, alpha)
    span_end = chunk.offset + 32 + chunk.stored_size
    span = bytes(bundle[chunk.offset:span_end])
    if new == decoded:
        rebuilt = span
    else:
        try:
            rebuilt, _fit = tx.rebuild_compressed_chunk_fixed_span(span, new)
        except tx.TxtrError as exc:
            raise StadiumShadowError(f"the shadow does not fit its span: {exc}") from exc
    require(len(rebuilt) == len(span), "the shadow span changed size")
    out = bytes(bundle[:chunk.offset]) + rebuilt + bytes(bundle[span_end:])
    back = shadow_chunk(out)
    require(back is not None and back[1] == new, "shadow read-back differs")
    return out, dict(offset=chunk.offset, length=len(span), before_sha256=sha(span), after_sha256=sha(rebuilt),
                     decoded_sha256=sha(new))


def bundle_shadow(bundle, prefix, sun=None):
    """(bundle, receipt or None): the shadow of the stadium scene this bundle carries, under the venue's retail sun,
    in place of the bundle's shadow texture. A bundle without a shadow texture comes back unchanged with None."""
    if shadow_chunk(bundle) is None:
        return bytes(bundle), None
    import numpy as np
    tx, ml = _tools()
    chunk = ml.bundle_scenes(bundle)["stadium"]
    decoded, _ = tx.decode_chunk(bundle, chunk)
    row = venues().get(prefix, {})
    if row.get("roof") == "closed":
        # a roofed field is lit by the stadium's own lights: no sun shadow, as retail's domes have none
        sun = None
        alpha = np.full((SIZE, SIZE), 254, dtype=np.uint8)
        alpha[CENTRE - WINDOW_V:CENTRE + WINDOW_V, CENTRE - WINDOW_U:CENTRE + WINDOW_U] = 0
    else:
        sun = tuple(sun) if sun is not None else venue_sun(prefix)
        alpha = cast(decoded, chunk.system_bytes, sun, skip=tuple(row.get("translucent", ())))
    out, receipt = write_shadow(bundle, alpha)
    lit = int((alpha[CENTRE - 75:CENTRE + 75, CENTRE - 33:CENTRE + 33] == 0).sum())
    return out, dict(receipt, sun=None if sun is None else [round(v, 6) for v in sun], roof=row.get("roof", "open"),
                     stadium_sha256=sha(decoded), alpha_sha256=sha(alpha.tobytes()), field_lit_texels=lit)
