"""Modern MetLife (experimental): Giants Stadium (s18) and Jets Stadium (s19) reworked into MetLife Stadium.

The retail game has two venue records for the stadium the Giants and Jets shared: ``s18`` "Giants Stadium"
(Giants home games) and ``s19`` "Jets Stadium" (Jets home games), nine archive bundles each
(``s18{d,a,n}{d,r,s}.iff``: day, afternoon, night; dry, rain, snow). Every bundle carries a field scene, a
stadium scene, a cityscape scene and the flyover camera paths. MetLife sits beside where Giants Stadium stood
and has a similar three-tier bowl, so this option keeps the Giants Stadium bowl and reworks it:

* palette rules recolour structure in place (the retail indices and mips stay, only the 256-entry palette of
  each named texture changes): charcoal MetLife seats, neutral silver steel and concrete;
* authored patches replace the signage: the team wall pads, the LED fascia ribbons, the end-zone video
  boards and the field-level sponsor and fan banners; each patch is written into the
  texture of every variant, and the rain and snow looks are carried over from the user's own retail variant
  pair (a per-channel affine fit of retail dry to retail rain or snow, plus the snow drift mask);
* the field marks (the end zones and the midfield logo, Giants and Jets 2026) are composited over each
  variant's own retail turf before the modern colour grade, exactly like Modern Arrowhead;
* geometry MetLife does not have collapses: the rooftop press box and every light tower and lamp bank (each
  vertex to its shape's retail bounding-sphere centre, same counts, spheres retail, nothing drawn), and the
  fourteen light-glow and four lens-flare markers that sat on the lamps move onto the roof rim on their own
  bearings;
* the ROST stadium records s18 and s19 are renamed "MetLife Stadium" (display name and name fields only;
  the asset code the engine uses as a file-name key stays ``s18``/``s19``).

Every SCNE is refit inside its fixed VC-LZ span with the retail wrapper, including the loader scratch word,
unchanged. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path

OWNER = "nfl2k5_modern_metlife"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Modern MetLife Stadium (experimental)"
HELP_TEXT = (
    "Giants Stadium becomes MetLife Stadium for Giants and Jets home games (day, afternoon, night; dry, rain, "
    "snow): charcoal seats, silver steel, team wall pads, LED ribbon boards and video boards, the 2026 end zones "
    "and midfield logos, no rooftop press box and no light towers (the light glows sit on the roof rim), and the "
    "venue name MetLife Stadium. "
    "Every scene is refit inside its fixed span. Off in every preset; needs a disc image. Appearance in game is "
    "unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_metlife"
RULES_PATH = DATA_DIR / "rules.json"
PINS_PATH = DATA_DIR / "pins.json"
RULES_SCHEMA = "nfl2k5_modern_metlife_rules/v1"
PINS_SCHEMA = "nfl2k5_modern_metlife_pins/v1"
VENUES = ("s18", "s19")
TEAM_OF_VENUE = {"s18": "giants", "s19": "jets"}
TIMES, WEATHERS = "dan", "drs"
VARIANTS = tuple(f"{venue}{tod}{weather}.iff" for venue in VENUES for tod in TIMES for weather in WEATHERS)
SCENES = ("field", "stadium", "cityscape")
VENUE_NAME = "MetLife Stadium"
ROST_OUTER_INDEX = 5
ROST_STADIUM_SIZE = 0x80
# (field offset, name) of the stadium record's string pointers; +0x0C is the engine's file-name key.
ROST_STRING_FIELDS = ((0x00, "name"), (0x08, "location"), (0x0C, "asset_code"), (0x10, "display_name"),
                      (0x14, "secondary_label"))
RENAMED_FIELDS = ("name", "display_name")
RETAIL_ROST_STRINGS = {
    "s18": {"name": "Giants Stadium", "location": "East Rutherford, NJ", "asset_code": "s18",
            "display_name": "Giants Stadium", "secondary_label": ""},
    "s19": {"name": "Jets Stadium", "location": "East Rutherford, NJ", "asset_code": "s19",
            "display_name": "Giants Stadium", "secondary_label": ""},
}


class ModernMetLifeError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ModernMetLifeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def name_id(filename):
    """The engine's archive name id: CRC-32 of the upper-case UTF-16LE filename."""
    return zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF


def variant_parts(filename):
    """('s18', 'd', 'r') for 's18dr.iff'."""
    require(filename in VARIANTS, f"{filename} is not a MetLife bundle")
    return filename[:3], filename[3], filename[4]


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_txtr as tx  # noqa: E402
    import nfl_scne_inventory as inv  # noqa: E402
    from nfl_scene_probe import ResourceRecord, HEADER  # noqa: E402
    from . import nfl2k5_stadium_texture_writer as stw
    return tx, inv, ResourceRecord, HEADER, stw


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


# --- rules and art ---------------------------------------------------------------------------------

_RULES = None


def rules():
    """The checked-in rule document (palette rules, patches, overlays, geometry, venue names)."""
    global _RULES
    if _RULES is None:
        require(RULES_PATH.is_file(), "Modern MetLife rules are missing from this build")
        _RULES = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        require(_RULES.get("schema") == RULES_SCHEMA, "unsupported Modern MetLife rules schema")
    return _RULES


def art_files():
    return sorted(set((DATA_DIR / "art").rglob("*.png")) |
                  {ROOT / p for p, row in official.CATALOG.items()
                   if row["feature"] == "modern_metlife"})


def art_pins():
    return {p.relative_to(DATA_DIR).as_posix(): sha(official.resolve_path(p).read_bytes()) for p in art_files()}


_ART = {}


def art_rgba(relative, width, height):
    """Exact-size RGBA8 numpy array (height, width, 4) of one authored PNG."""
    import numpy as np
    path = official.resolve_path(DATA_DIR / relative)
    key = (str(path), sha(path.read_bytes()), width, height)
    if key not in _ART:
        from PIL import Image
        require(path.is_file(), f"Modern MetLife art is missing: {relative}")
        with Image.open(path) as image:
            require(image.size == (width, height),
                    f"{relative} is {image.size[0]}x{image.size[1]}, the texture needs {width}x{height}")
            _ART[key] = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    return _ART[key]


def _venue_items(kind, venue, scene):
    out = []
    for item in rules().get(kind, ()):
        if scene != item["scene"]:
            continue
        if venue not in item.get("venues", VENUES):
            continue
        out.append(item)
    return out


# --- P8 texture access --------------------------------------------------------------------------------

def _scene(data, chunk):
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    record = ResourceRecord(outer_index=0, outer_id="", outer_size=len(data), chunk_index=chunk.index,
                            chunk_offset=chunk.offset, kind=chunk.kind, stored_size=chunk.stored_size,
                            word_08=chunk.system_bytes, word_0c=chunk.video_bytes, word_10=chunk.compression_magic,
                            word_14=chunk.overlap_scratch_bytes)
    decoded, _ = tx.decode_chunk(data, chunk)
    rec, _names, _maps, _sample = inv.parse_scene(chunk.index, record, decoded, {})
    return rec, decoded


def texture_rows(rec):
    """{material name: texture row} for the P8 textures of one parsed scene."""
    rows = {int(r["index"]): r for r in rec.get("embedded_textures", ())}
    out = {}
    for material in rec.get("materials", ()):
        index = material.get("texture_index")
        if index is None or int(index) not in rows:
            continue
        row = rows[int(index)]
        if row.get("format_name") == "P8" and row.get("conversion_status") == "base_level_supported":
            out[material["name"]] = row
    return out


def read_p8(decoded, system, row):
    """(RGBA array (h, w, 4), palette bytes) of the base level of one P8 texture."""
    import numpy as np
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    width, height = int(row["width"]), int(row["height"])
    pixel = system + int(row["pixel_offset"])
    palette_at = system + int(row["palette_offset"])
    raw = bytes(decoded[palette_at:palette_at + 1024])
    palette = np.frombuffer(raw, dtype=np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    linear = np.frombuffer(tx.unswizzle_2d(bytes(decoded[pixel:pixel + width * height]), width, height, 1),
                           dtype=np.uint8).reshape(height, width)
    return palette[linear].copy(), raw


def write_p8(edited, system, row, rgba, maximum=256):
    """Quantize an RGBA array (full mip chain, one shared palette) into one P8 allocation in place."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    import numpy as np
    width, height, levels = int(row["width"]), int(row["height"]), int(row["mip_levels"])
    require(rgba.shape == (height, width, 4), "authored texture has the wrong size")
    dims = stw._mip_dimensions(width, height, levels)
    mips = stw._generate_dynamic_mips(np.ascontiguousarray(rgba, dtype=np.uint8).tobytes(), dims)
    palette, linear, _quality = stw.quantize_levels(mips, maximum)
    swizzled = b"".join(stw.swizzle_2d(indices, level.width, level.height, 1) for level, indices in zip(mips, linear))
    payload = stw.palette_bytes(palette)
    pixel = system + int(row["pixel_offset"])
    palette_at = system + int(row["palette_offset"])
    require(len(swizzled) == sum(w * h for w, h in dims) and len(payload) == stw.PALETTE_BYTES
            and palette_at == pixel + len(swizzled) and palette_at + stw.PALETTE_BYTES <= len(edited),
            f"{row.get('mapped_material_names')}: P8 allocation mismatch")
    edited[pixel:pixel + len(swizzled)] = swizzled
    edited[palette_at:palette_at + stw.PALETTE_BYTES] = payload
    return len(palette)


def write_palette(edited, system, row, palette_rgba):
    """Replace only the 256-entry palette (indices and mips keep their retail bytes)."""
    import numpy as np
    palette_at = system + int(row["palette_offset"])
    bgra = np.asarray(palette_rgba, dtype=np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    edited[palette_at:palette_at + 1024] = bgra.tobytes()


# --- colour rules -------------------------------------------------------------------------------------

def _hsv(rgb):
    import numpy as np
    rgb = rgb.astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-9), 0.0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(mx)
    safe = np.maximum(delta, 1e-9)
    hue = np.where(mx == r, ((g - b) / safe) % 6, hue)
    hue = np.where(mx == g, (b - r) / safe + 2, hue)
    hue = np.where(mx == b, (r - g) / safe + 4, hue)
    hue = np.where(delta > 0, hue * 60.0, 0.0)
    return hue, sat, mx


def _luma(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def palette_rule(palette_rgba, rule):
    """New 256x4 palette for one named rule; alpha always stays retail."""
    import numpy as np
    pal = np.asarray(palette_rgba, dtype=np.float64).copy()
    rgb = pal[:, :3]
    hue, sat, val = _hsv(rgb)
    y = _luma(rgb)
    kind = rule["kind"]
    if kind == "grey_ramp":
        # Warm/red seat colours become a cool charcoal at a scaled luminance; neutral entries (aisles,
        # concrete) are only neutralized. Parameters: scale, tint (r, g, b multipliers), hue window.
        lo, hi = rule.get("hue", [-30, 60])
        huew = ((hue - lo) % 360) <= ((hi - lo) % 360)
        coloured = (sat >= rule.get("min_sat", 0.12)) & huew
        tint = np.asarray(rule.get("tint", [0.97, 1.0, 1.04]))
        grey = np.clip(y * rule.get("scale", 1.45), 0, rule.get("max", 235))[:, None] * tint[None, :]
        neutral = np.clip(y * rule.get("neutral_scale", 1.0), 0, 255)[:, None] * tint[None, :]
        out = np.where(coloured[:, None], grey, np.where((sat < rule.get("min_sat", 0.12))[:, None],
                                                          rgb * (1 - rule.get("neutralize", 0.6))
                                                          + neutral * rule.get("neutralize", 0.6), rgb))
        pal[:, :3] = out
    elif kind == "neutral":
        # Desaturate toward a slightly cool grey at a luminance gain (steel, concrete, frames).
        amount = rule.get("amount", 0.7)
        tint = np.asarray(rule.get("tint", [0.98, 1.0, 1.03]))
        grey = np.clip(y * rule.get("gain", 1.0) + rule.get("lift", 0.0), 0, 255)[:, None] * tint[None, :]
        pal[:, :3] = rgb * (1 - amount) + grey * amount
    elif kind == "hue_map":
        # Entries inside a hue window take a new hue/saturation at their own value (team colour swaps).
        lo, hi = rule["hue"]
        inside = (((hue - lo) % 360) <= ((hi - lo) % 360)) & (sat >= rule.get("min_sat", 0.2))
        import colorsys
        target_h, target_s = rule["to_hue"] / 360.0, rule["to_sat"]
        for i in np.nonzero(inside)[0]:
            v = min(1.0, val[i] * rule.get("gain", 1.0))
            pal[i, :3] = np.array(colorsys.hsv_to_rgb(target_h, target_s, v)) * 255.0
    else:
        raise ModernMetLifeError(f"unknown palette rule {kind}")
    return np.clip(np.rint(pal), 0, 255).astype(np.uint8)


def _box_blur(mask, radius):
    import numpy as np
    if radius <= 0:
        return mask
    k = 2 * radius + 1
    padded = np.pad(mask, radius, mode="wrap")
    cs = padded.cumsum(axis=0).cumsum(axis=1)
    cs = np.pad(cs, ((1, 0), (1, 0)))
    h, w = mask.shape
    total = cs[k:k + h, k:k + w] - cs[0:h, k:k + w] - cs[k:k + h, 0:w] + cs[0:h, 0:w]
    return total / (k * k)


# The prior variance (20 levels squared) of the ridge gain in weather_transfer: a channel whose retail spread
# is well above it keeps its own least-squares gain; a flat one takes the joint gain of the three channels.
WEATHER_RIDGE = 400.0


def weather_transfer(dry_retail, variant_retail, authored, *, region=None, snow=False):
    """Carry the retail dry -> variant look onto authored dry art.

    A per-channel affine fit of the retail pair over ``region`` (y0, y1, x0, x1) maps the authored pixels.
    Each channel's gain is a ridge estimate pulled toward the joint gain of all three channels (one gain, one
    offset, fitted over the stacked channels): a channel the retail art barely varies in (a flat pad) cannot
    say how bright new art in it should become, so it takes the joint gain instead of a near-zero or
    runaway one; a channel with real spread keeps its own. For snow, the part of the retail variant the fit
    cannot explain and that is brighter than the fit (the drifts) becomes a mask that blends the snow colour
    over the result. Alpha stays authored.
    """
    import numpy as np
    d = dry_retail.astype(np.float64)
    v = variant_retail.astype(np.float64)
    a = authored.astype(np.float64)
    if np.array_equal(dry_retail, variant_retail):
        return authored.copy(), None
    y0, y1, x0, x1 = region or (0, d.shape[0], 0, d.shape[1])
    ds, vs = d[y0:y1, x0:x1], v[y0:y1, x0:x1]
    solid = ds[..., 3] > 128
    out = a.copy()
    fits = []
    stack_x = np.concatenate([ds[..., c][solid] for c in range(3)])
    stack_y = np.concatenate([vs[..., c][solid] for c in range(3)])
    joint = float(np.polyfit(stack_x, stack_y, 1)[0]) if stack_x.size >= 8 and np.ptp(stack_x) >= 1.0 else 1.0
    for c in range(3):
        xs = ds[..., c][solid]
        ys = vs[..., c][solid]
        if xs.size < 8:
            gain, bias = 1.0, float(ys.mean() - xs.mean()) if xs.size else 0.0
        else:
            mx, my = float(xs.mean()), float(ys.mean())
            sxx = float(((xs - mx) ** 2).mean())
            sxy = float(((xs - mx) * (ys - my)).mean())
            gain = (sxy + WEATHER_RIDGE * joint) / (sxx + WEATHER_RIDGE)
            bias = my - gain * mx
        fits.append((float(gain), float(bias)))
        out[y0:y1, x0:x1, c] = a[y0:y1, x0:x1, c] * gain + bias
    if snow:
        pred = np.stack([ds[..., c] * fits[c][0] + fits[c][1] for c in range(3)], axis=-1)
        excess = (vs[..., :3] - pred).mean(axis=-1)
        # drifts are broad and nearly white; blur before and after the threshold so the edges of
        # printed retail art (a non-affine difference too) never become snow shapes
        bright = (vs[..., :3].mean(axis=-1) > 170) & (vs[..., :3].max(axis=-1) - vs[..., :3].min(axis=-1) < 40)
        drift = np.clip(_box_blur(excess, 2) / 70.0, 0.0, 1.0) * solid * bright
        drift = np.clip(_box_blur(drift, 2) * 1.3, 0.0, 1.0)
        if drift.max() > 0.05:
            snow_rgb = np.percentile(vs[..., :3][drift > 0.5], 80, axis=0) if (drift > 0.5).any() \
                else np.array([236.0, 238.0, 242.0])
            region_rgb = out[y0:y1, x0:x1, :3]
            out[y0:y1, x0:x1, :3] = region_rgb * (1 - drift[..., None]) + snow_rgb[None, None, :] * drift[..., None]
    out[..., 3] = a[..., 3]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), fits


def composite_over(base, over):
    """Straight-alpha 'over' of an authored overlay onto a retail texture; the result keeps base alpha."""
    import numpy as np
    b = base.astype(np.float64)
    o = over.astype(np.float64)
    alpha = o[..., 3:4] / 255.0
    out = b.copy()
    out[..., :3] = o[..., :3] * alpha + b[..., :3] * (1 - alpha)
    # An overlay painted onto an alpha-cut texture (the midfield logo) also carries its own coverage.
    out[..., 3] = np.maximum(b[..., 3], o[..., 3])
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


# --- geometry ----------------------------------------------------------------------------------------

def _shape_positions(rec, shape, decoded):
    from . import nfl2k5_models as models
    lanes = models._shape_lanes(rec, shape, decoded)
    require(lanes.position_format == "FLOAT3", f"{shape['name']}: only FLOAT3 positions are edited")
    return lanes, models.read_positions(decoded, shape, lanes)


def geometry_edits(edited, rec, venue):
    """Collapse the shapes MetLife does not have (rules['geometry'], mode "collapse").

    Every vertex of a named shape moves to the centre of the shape's retail bounding sphere (shape +0x00,
    radius +0x48, the sphere the frustum test reads). The vertex count, the topology, the materials and the
    sphere stay retail; every triangle becomes zero-area, so nothing of the shape is drawn, and every vertex
    is inside the sphere (distance 0). Only FLOAT3 position lanes are written.
    """
    receipt = []
    shapes = {s["name"]: s for s in rec.get("shapes", ())}
    for item in rules().get("geometry", ()):
        if venue not in item.get("venues", VENUES) or item.get("scene", "stadium") != rec.get("name"):
            continue
        require(item.get("mode") == "collapse", f"geometry rule {item.get('shape')}: only collapse is admitted in the stadium")
        shape = shapes.get(item["shape"])
        require(shape is not None, f"geometry rule names a missing shape {item['shape']}")
        lanes, positions = _shape_positions(rec, shape, edited)
        record = int(shape["record_offset"])
        cx, cy, cz, cw = struct.unpack_from("<4f", edited, record)
        radius = struct.unpack_from("<f", edited, record + 0x48)[0]
        require(cw == 1.0 and math.isfinite(radius) and radius > 0, f"{shape['name']}: no bounding sphere")
        from . import nfl2k5_models as models
        stream_base = models._stream_base({}, shape, lanes.position_stream)
        moved = 0
        for index, position in enumerate(positions):
            if tuple(position) == (cx, cy, cz):
                continue
            struct.pack_into("<3f", edited, stream_base + index * lanes.position_stride + lanes.position_offset,
                             cx, cy, cz)
            moved += 1
        receipt.append(dict(shape=shape["name"], mode="collapse", vertices=len(positions), moved=moved,
                            sphere_radius_m=round(radius / 100.0, 3)))
    return receipt


def quad_edits(edited, rec, venue):
    """Resize the field quads the rules name (rules['geometry'], mode "quad"): same vertices, same UVs.

    b76-u5b: the Giants paint their midfield helmet about 16 x 14 yards, the retail center_logo quad is 10 x 9.26
    yards. A rule names the material of a four-vertex quad, its retail half extents (x across, z along; every
    corner must sit there, y = 0) and the new half extents; each corner keeps its signs, so the texture mapping is
    unchanged. The shape's bounding sphere (the frustum test) must still contain every moved corner.
    """
    from . import nfl2k5_models as models
    from . import nfl2k5_scne_builder as sb
    receipt = []
    for item in rules().get("geometry", ()):
        if (item.get("mode") != "quad" or venue not in item.get("venues", VENUES)
                or item.get("scene", "stadium") != rec.get("name")):
            continue
        subs = [m for m in rec.get("submeshes", ()) if m.get("material_name") == item["material"]]
        require(len(subs) == 1, f"quad rule {item['material']}: {len(subs)} submeshes")
        sm = subs[0]
        require(int(sm.get("secondary_command_word_count", 0)) == 0, f"{item['material']}: secondary words")
        shape = next(s for s in rec["shapes"] if s["name"] == sm["shape_name"])
        lanes, positions = _shape_positions(rec, shape, edited)
        words = bytes(edited[int(sm["command_offset"]):int(sm["command_offset"]) + 4 * int(sm["word_count"])])
        indices = sorted({i for _mode, ix in sb.decode_words(words) for i in ix})
        require(len(indices) == 4, f"{item['material']}: not a four-vertex quad")
        hx, hz = (float(v) * 100.0 for v in item["retail_half_extent_m"])
        nx, nz = (float(v) * 100.0 for v in item["half_extent_m"])
        base = models._stream_base({}, shape, lanes.position_stream)
        record = int(shape["record_offset"])
        cx, cy, cz, cw = struct.unpack_from("<4f", edited, record)
        radius = struct.unpack_from("<f", edited, record + 0x48)[0]
        corners = []
        for index in indices:
            x, y, z = positions[index]
            require(abs(abs(x) - hx) < 0.5 and abs(abs(z) - hz) < 0.5 and y == 0.0,
                    f"{item['material']}: vertex {index} is not at the retail corner")
            new = (math.copysign(nx, x), 0.0, math.copysign(nz, z))
            require(math.dist(new, (cx, cy, cz)) <= radius, f"{item['material']}: a corner leaves the shape sphere")
            struct.pack_into("<3f", edited, base + index * lanes.position_stride + lanes.position_offset, *new)
            corners.append([round(v / 100.0, 3) for v in new])
        receipt.append(dict(shape=shape["name"], material=item["material"], mode="quad", corners_m=corners))
    return receipt


MARKER_POSITION = 0x10  # a scene marker record is 0x40 bytes: +0x00 name pointer, +0x10 x, y, z, w


def marker_edits(edited, rec, venue):
    """Move the named scene markers (rules['markers']) to authored positions, same bytes, same records.

    The executable registers a light glow at every stadium marker whose name holds "light" and a lens flare
    at every one whose name holds "flare" (0x0007F210 -> 0x0007EB00 / 0x0007EB50, position read from marker
    +0x10); 0x00097B80 also copies the "marker_flare" positions as the player-shadow lights of shadow mode 2.
    A rule names one marker, the SHA-256 of its retail 16 position bytes (the write refuses anything else)
    and the new position in metres; w stays.
    """
    receipt = []
    markers = {m["name"]: m for m in rec.get("markers", ())}
    for item in rules().get("markers", ()):
        if venue not in item.get("venues", VENUES) or item.get("scene", "stadium") != rec.get("name"):
            continue
        marker = markers.get(item["marker"])
        require(marker is not None, f"marker rule names a missing marker {item['marker']}")
        at = int(marker["record_offset"]) + MARKER_POSITION
        before = bytes(edited[at:at + 16])
        require(sha(before) in item["retail_sha256"], f"{item['marker']}: the position is not retail")
        require(struct.unpack_from("<f", before, 12)[0] == 1.0, f"{item['marker']}: w is not 1")
        struct.pack_into("<3f", edited, at, *(float(v) * 100.0 for v in item["position_m"]))
        receipt.append(dict(marker=item["marker"], position_m=list(item["position_m"])))
    return receipt


# --- one scene ------------------------------------------------------------------------------------------

def _item_materials(item, rows):
    names = [item["material"]] + list(item.get("aliases", ()))
    return [n for n in names if n in rows]


def paint_scene(decoded, rec, venue, weather, dry=None, palette_cap=256):
    """Author one decoded scene in place; ``dry`` is {material: RGBA} of the same venue/time dry variant.

    Returns (edited bytes, receipt). The caller owns compression and wrappers.
    """
    import numpy as np
    scene = rec.get("name")
    edited = bytearray(decoded)
    system = int(rec["system_bytes"])
    rows = texture_rows(rec)
    receipt = dict(scene=scene, palettes=[], patches=[], overlays=[], geometry=[], markers=[], palette_cap=palette_cap)
    done = set()
    for item in _venue_items("palette_rules", venue, scene):
        for material in _item_materials(item, rows):
            row = rows[material]
            key = int(row["index"])
            if key in done:
                continue
            done.add(key)
            _rgba, raw = read_p8(edited, system, row)
            palette = np.frombuffer(raw, dtype=np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
            new = palette_rule(palette, rules()["palette_kinds"][item["rule"]])
            write_palette(edited, system, row, new)
            receipt["palettes"].append(dict(material=material, texture=key, rule=item["rule"]))
    for kind in ("patches", "overlays"):
        for item in _venue_items(kind, venue, scene):
            for material in _item_materials(item, rows):
                row = rows[material]
                key = int(row["index"])
                if key in done:
                    continue
                done.add(key)
                width, height = int(row["width"]), int(row["height"])
                art = art_rgba(item["art"], width, height)
                current, _raw = read_p8(edited, system, row)
                base_dry = (dry or {}).get(material)
                if base_dry is None:
                    base_dry = current
                require(base_dry.shape == current.shape, f"{material}: dry and variant textures differ in size")
                if kind == "overlays":
                    authored = composite_over(base_dry, art)
                    result, fits = weather_transfer(base_dry, current, authored, snow=False)
                    rects = None
                else:
                    rects = item.get("rects") or [[0, 0, width, height]]
                    result = current.copy()
                    fits = []
                    for x0, y0, x1, y1 in rects:
                        region = (y0, y1, x0, x1)
                        piece, fit = weather_transfer(base_dry, current, art, region=region,
                                                      snow=weather == "s" and bool(item.get("snow_drift")))
                        result[y0:y1, x0:x1] = piece[y0:y1, x0:x1]
                        fits.append(fit)
                colours = write_p8(edited, system, row, result, palette_cap)
                receipt[kind].append(dict(material=material, texture=key, art=item["art"], rects=rects,
                                          palette_entries=colours, weather_fit=fits))
    receipt["geometry"] = geometry_edits(edited, rec, venue) if scene == "stadium" else quad_edits(edited, rec, venue)
    receipt["markers"] = marker_edits(edited, rec, venue) if scene == "stadium" else []
    return bytes(edited), receipt


def retail_textures(decoded, rec):
    """{material: RGBA} of every P8 texture of one decoded scene (the dry reference)."""
    system = int(rec["system_bytes"])
    return {material: read_p8(decoded, system, row)[0] for material, row in texture_rows(rec).items()}


def _stream_peak(stream, stored):
    """(alias, token index) of the in-place decode constraint's maximum (see nfl_txtr)."""
    output_size = struct.unpack_from("<I", stream, 0)[0]
    bits = stream[8]
    length_mask = (1 << (16 - bits)) - 1
    source, flags, mask, dest, best, best_token, token = 10, stream[9], 1, 0, 0, -1, 0
    while dest < output_size:
        if flags & mask:
            code = struct.unpack_from("<H", stream, source)[0]
            source += 2
            dest += ((code >> bits) & length_mask) + 3
        else:
            source += 1
            dest += 1
        if dest < output_size:
            value = stored - output_size + dest - source
            if value > best:
                best, best_token = value, token
        token += 1
        mask = (mask << 1) & 0xFF
        if mask == 0 and dest < output_size:
            flags = stream[source]
            source += 1
            mask = 1
    return best, best_token


def _peak_aware_fit(span, decoded):
    """Keep the retail wrapper when the only miss is the in-place scratch at the stream's tail.

    The in-place decode constraint (nfl_txtr.minimum_vc_lz_overlap_scratch) at output position p is
    stored - decoded + dest(p) - source(p). Filling the stream with literals raises source(p) for every
    later p, and a constraint that peaks in the last kilobytes is lowered by exactly the bytes filled
    before it. The colour option's fills stop up to 16 bytes short of the stored body (padding); here the
    same trailing fill runs to the last byte (padding 0), which lowers a tail peak by that padding. The
    wrapper, scratch word included, stays byte-identical; the result is decoded and checked.
    """
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_vc_lz_fill as fill  # noqa: E402
    fields = HEADER.unpack_from(span)
    stored, scratch = fields[1], fields[5]
    prefix = span[HEADER.size:HEADER.size + 9]
    declared, tag = struct.unpack_from("<II", prefix)
    bits = prefix[8]
    require(declared == len(decoded), "template stream declares another size")
    attempts = []
    encoders = (("greedy", lambda: tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, max_encoded_size=stored,
                                                     verify_roundtrip=False)[0]),
                ("optimal", lambda: fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits)))
    for name, encode in encoders:
        try:
            encoded = encode()
        except tx.TxtrError as exc:
            attempts.append(f"{name}: {exc}")
            continue
        if len(encoded) > stored:
            attempts.append(f"{name}: {len(encoded)} bytes exceeds {stored}")
            continue
        filled = fill.fill_stream(encoded, decoded, stored, slack=0)[0] if len(encoded) < stored else encoded
        padding = stored - len(filled)
        alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
        if padding <= scratch and alias <= scratch:
            rebuilt = span[:HEADER.size] + filled + bytes(padding)
            back, info = tx.decompress_vc_lz(rebuilt[HEADER.size:], len(decoded))
            require(back == decoded and info.consumed_bytes == len(filled), "full-fill refit failed its decode check")
            return rebuilt, dict(encoder=name, fill="trailing-full", padding_bytes=padding, alias_scratch=alias,
                                 scratch_bytes=scratch)
        attempts.append(f"{name}/full fill: padding {padding}, needs {alias}, retail {scratch}")
    raise ModernMetLifeError("; ".join(attempts))


def fit_span(span, decoded):
    """Recompress into the retail span keeping the whole 32-byte wrapper, scratch word included.

    First the full trailing fill above (greedy, then optimal parsing), then the colour option's fitter
    (greedy/optimal with a front or trailing fill that stops up to 16 bytes short).
    """
    from . import nfl2k5_modern_color as colour
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    try:
        return _peak_aware_fit(span, decoded)
    except (ModernMetLifeError, tx.TxtrError) as first:
        try:
            return colour.fit_fixed_span(span, decoded)
        except tx.TxtrError as second:
            raise tx.TxtrError(f"full fill: {first}; colour fitter: {second}") from second


# --- bundles ------------------------------------------------------------------------------------------

def bundle_scenes(data):
    """{scene name: chunk} for the field, stadium and cityscape scenes of one bundle."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    out = {}
    for chunk in tx.parse_chunks(data, allow_trailing=True):
        if chunk.kind != "SCNE":
            continue
        rec, _decoded = _scene(data, chunk)
        if rec.get("name") in SCENES:
            out[rec["name"]] = chunk
    require({"field", "stadium"} <= set(out), "bundle lacks its field or stadium scene")
    return out


def dry_reference(dry_bundle):
    """{scene: {material: RGBA}} of a retail dry bundle."""
    out = {}
    for name, chunk in bundle_scenes(dry_bundle).items():
        rec, decoded = _scene(dry_bundle, chunk)
        out[name] = retail_textures(decoded, rec)
    return out


def scene_span(data, chunk):
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    return bytes(data[chunk.offset:chunk.offset + HEADER.size + chunk.stored_size])


PALETTE_CAPS = (256, 128, 96, 64, 48, 32)


def modern_scene_span(data, chunk, venue, weather, dry):
    """(refit span, receipt) of one retail scene; unchanged scenes keep their bytes.

    Authored textures are quantized to a full 256-entry palette first; a scene whose stream then misses
    its fixed allocation is repainted with fewer palette entries for the authored textures only (lower
    index entropy compresses better), down to 32, before refusing.
    """
    rec, decoded = _scene(data, chunk)
    span = scene_span(data, chunk)
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    attempts = []
    for cap in PALETTE_CAPS:
        edited, receipt = paint_scene(decoded, rec, venue, weather, dry, palette_cap=cap)
        if edited == decoded:
            return span, dict(receipt, refit=False)
        try:
            rebuilt, info = fit_span(span, edited)
        except tx.TxtrError as exc:
            attempts.append(f"{cap} colours: {exc}")
            continue
        check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        require(check == edited, f"{rec.get('name')}: refit read-back differs")
        return rebuilt, dict(receipt, refit=True, fit_attempts=attempts, **info)
    raise ModernMetLifeError(f"{rec.get('name')} ({venue}, weather {weather}) does not fit its span: " + " | ".join(attempts))


def field_painter(venue, weather, dry, palette_cap=256):
    """A modern_color painter: (field span, chunk) -> (painted decoded field, receipt)."""
    def paint(span, chunk):
        rec, decoded = _scene(span, chunk)
        return paint_scene(decoded, rec, venue, weather, dry.get("field"), palette_cap=palette_cap)
    return paint


def graded_field_span(before, venue, weather, dry, *, outer_index, settings=None):
    """(span, receipt) of the field composed with Modern colour: the MetLife art painted first and the colour grade and
    single refit after it; like the skin alone, a field that misses its fixed allocation is repainted with fewer
    palette entries for the authored textures (256 down to 32) before refusing (b76-u5b: the refit midfield helmet
    needs 128 in some variants)."""
    from . import nfl2k5_modern_color as colour
    tx = _tools()[0]
    attempts = []
    for cap in PALETTE_CAPS:
        try:
            after, detail = colour.modern_field_scene(before, outer_index=outer_index, settings=settings,
                                                      painter=field_painter(venue, weather, dry, palette_cap=cap))
        except tx.TxtrError as exc:
            attempts.append(f"{cap} colours: {exc}")
            continue
        return after, (dict(detail, fit_attempts=attempts) if attempts else detail)
    raise ModernMetLifeError(f"field ({venue}, weather {weather}) with Modern colour does not fit its span: "
                             + " | ".join(attempts))


def modern_bundle(data, filename, dry_bundle):
    """(modern bundle bytes, edits) for one retail MetLife bundle; ``dry_bundle`` is the retail dry variant."""
    venue, _tod, weather = variant_parts(filename)
    dry = dry_reference(dry_bundle)
    out = bytearray(data)
    edits = []
    for name, chunk in sorted(bundle_scenes(data).items(), key=lambda kv: kv[1].offset):
        before = scene_span(data, chunk)
        after, receipt = modern_scene_span(data, chunk, venue, weather, dry.get(name))
        require(len(after) == len(before), f"{filename} {name}: refit escaped its allocation")
        if after == before:
            continue
        out[chunk.offset:chunk.offset + len(before)] = after
        edits.append(dict(kind=name, offset=chunk.offset, size=len(before), before_sha256=sha(before),
                          after_sha256=sha(after), **receipt))
    return bytes(out), edits


def dry_name(filename):
    venue, tod, _weather = variant_parts(filename)
    return f"{venue}{tod}d.iff"


# --- the venue name (ROST outer 5) -------------------------------------------------------------------------

def _utf16z(body, at, limit=256):
    out = []
    while len(out) < limit:
        require(0 <= at <= len(body) - 2, "ROST string runs past the resource")
        unit = struct.unpack_from("<H", body, at)[0]
        if unit == 0:
            return "".join(out)
        out.append(chr(unit))
        at += 2
    raise ModernMetLifeError("unterminated ROST string")


def _relative_target(body, field):
    value = struct.unpack_from("<i", body, field)[0]
    return None if value == 0 else field + value - 1


def _stadium_records(body):
    """[(offset, {field name: (target, text)})] of every stadium record in a ROST body."""
    from . import nfl2k5_roster_records as rr
    doc = rr.RosterDocument(body, base=0)
    out = []
    for stadium in doc.stadiums:
        fields = {}
        for offset, name in ROST_STRING_FIELDS:
            target = _relative_target(body, stadium.offset + offset)
            require(target is not None, f"stadium {stadium.index} has no {name} string")
            fields[name] = (target, _utf16z(body, target))
        out.append((stadium.offset, fields))
    return out


def _string_block(fields):
    """(start, end) of the contiguous pool block the five strings of one record occupy, or None."""
    spans = sorted((target, target + 2 * len(text) + 2) for target, text in fields.values())
    start, end = spans[0][0], spans[-1][1]
    covered = 0
    cursor = start
    for s, e in spans:
        if s < cursor:
            return None  # overlapping strings: shared allocations are not repacked
        covered += s - cursor  # alignment padding between strings is allowed, counted below
        cursor = e
    return start, end


def _player_data_words(body):
    """Offsets of the 4-byte words of every player record other than its four pointer fields (college +0x00,
    first and last name +0x10 and +0x14, the history stream +0x2C): data, not pointers.

    A player record packs ratings, appearance and flag bits into whole words, so an edited player can hold any
    value, including one that reads as a self-relative offset into a stadium's strings. (b76-u5b: the league
    roster edits turn player 515's +0x20 bit-field word from 0x00060969 into 0x00060831, which reads as a pointer
    into "Giants Stadium", and the rename refused a whole build.) The four pointer fields stay in the scan."""
    from . import nfl2k5_roster_records as rr
    try:
        doc = rr.RosterDocument(bytes(body), base=0)
    except Exception:  # noqa: BLE001 - a body the roster reader cannot parse keeps the full scan
        return frozenset()
    pointers = {rr.FIELD_BY_NAME[name].offset for name in rr.POINTER_FIELDS}
    return frozenset(player.offset + field for player in doc.players
                     for field in range(0, rr.PLAYER_SIZE, 4) if field not in pointers)


def _history_data_words(body):
    """Only the validated history streams are data; unused pool capacity stays in the scan.

    Packed career stats can resemble relative pointers (candidate G's 0x0002FFFE at 0x46320
    lands in s23's strings). The history reader checks stream bounds, terminators, continuity
    and coverage of the used count. A body it cannot parse gets no history exemption.
    """
    from . import nfl2k5_team_history as history
    try:
        roster = history.parse_body(bytes(body))
    except Exception:  # noqa: BLE001 - unproved history words keep the full scan
        return frozenset()
    if roster.pool < 0 or roster.pool % 4:
        return frozenset()
    return frozenset(range(roster.pool, roster.pool + roster.used * 4, 4))


def _pointers_into(body, start, end, allowed, text_spans=()):
    """Offsets of every 4-byte-aligned self-relative word landing in [start, end) that is not allowed.

    Words inside the stadium string pool itself (UTF-16 text such as "A" + NUL reads as a small offset)
    are not pointers and are skipped, as are player data words and validated history stream words.
    Player pointer fields and unused history pool capacity remain in the scan.
    """
    import bisect
    spans = sorted(text_spans)
    starts = [s for s, _e in spans]
    data = _player_data_words(body) | _history_data_words(body)
    hits = []
    for field in range(0, len(body) - 3, 4):
        if field in allowed or field in data:
            continue
        i = bisect.bisect_right(starts, field + 3) - 1
        if i >= 0 and spans[i][0] <= field + 3 and field < spans[i][1]:
            continue
        if i >= 1 and spans[i - 1][0] <= field + 3 and field < spans[i - 1][1]:
            continue
        value = struct.unpack_from("<i", body, field)[0]
        if value == 0 or value == 1:
            continue
        target = field + value - 1
        if start <= target < end:
            hits.append(field)
    return hits


def rost_rename(resource):
    """(renamed ROST resource, receipt): s18 and s19 display 'MetLife Stadium'.

    For each of the two records the five strings form one contiguous block of the string pool. The block is
    repacked in place as name/display_name (one shared 'MetLife Stadium' allocation), location, asset code
    and the empty secondary label, zero-filled to the retail block end, and the record's five relative
    pointers are rewritten. Nothing outside the two blocks and the ten pointer fields changes; any other
    pointer into a block refuses.
    """
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    records = _stadium_records(bytes(body))
    by_code = {fields["asset_code"][1]: (offset, fields) for offset, fields in records}
    receipt = dict(label=LABEL, records=[])
    for venue in VENUES:
        require(venue in by_code, f"ROST has no {venue} stadium record")
        offset, fields = by_code[venue]
        texts = {name: text for name, (_t, text) in fields.items()}
        if texts["name"] == VENUE_NAME and texts["display_name"] == VENUE_NAME:
            receipt["records"].append(dict(venue=venue, state="already_applied"))
            continue
        require(texts == RETAIL_ROST_STRINGS[venue], f"{venue}: stadium strings are not retail ({texts})")
        block = _string_block(fields)
        require(block is not None, f"{venue}: stadium strings are not one contiguous block")
        start, end = block
        pointer_fields = {offset + field for field, _name in ROST_STRING_FIELDS}
        text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
        stray = _pointers_into(bytes(body), start, end, pointer_fields, text_spans)
        require(not stray, f"{venue}: other pointers reach the stadium strings at {stray[:4]}")
        layout = [("shared_name", VENUE_NAME), ("location", texts["location"]),
                  ("asset_code", texts["asset_code"]), ("secondary_label", texts["secondary_label"])]
        payload = bytearray()
        at = {}
        for key, text in layout:
            at[key] = start + len(payload)
            payload += text.encode("utf-16le") + b"\0\0"
        used = len(payload)
        require(used <= end - start, f"{venue}: MetLife strings do not fit the retail block")
        payload += bytes(end - start - used)
        body[start:end] = payload
        targets = {"name": at["shared_name"], "display_name": at["shared_name"], "location": at["location"],
                   "asset_code": at["asset_code"], "secondary_label": at["secondary_label"]}
        for field, name in ROST_STRING_FIELDS:
            struct.pack_into("<i", body, offset + field, targets[name] - (offset + field) + 1)
        check = {name: text for name, (_t, text) in dict(_stadium_records(bytes(body)))[offset].items()}
        require(check == dict(RETAIL_ROST_STRINGS[venue], name=VENUE_NAME, display_name=VENUE_NAME),
                f"{venue}: renamed record read-back differs")
        receipt["records"].append(dict(venue=venue, state="applied", record_offset=offset, block=[start, end],
                                       bytes_used=used))
    return bytes(resource[:header]) + bytes(body), receipt


def rost_status(resource):
    """retail / applied / mixed / foreign for the two stadium records of one ROST resource."""
    try:
        from . import nfl2k5_roster_records as rr
        body = resource[rr.RESOURCE_HEADER_SIZE:]
        records = {fields["asset_code"][1]: fields for _o, fields in _stadium_records(body)}
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"
    states = set()
    for venue in VENUES:
        fields = records.get(venue)
        if fields is None:
            return "foreign"
        texts = {name: text for name, (_t, text) in fields.items()}
        if texts == RETAIL_ROST_STRINGS[venue]:
            states.add("retail")
        elif texts == dict(RETAIL_ROST_STRINGS[venue], name=VENUE_NAME, display_name=VENUE_NAME):
            states.add("applied")
        else:
            return "foreign"
    return states.pop() if len(states) == 1 else "mixed"


# --- pins and images --------------------------------------------------------------------------------------

_PINS = None


def _pins(*, optional=False):
    global _PINS
    if _PINS is None:
        if not PINS_PATH.is_file():
            if optional:
                return None
            raise ModernMetLifeError("Modern MetLife pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Modern MetLife pins schema")
        require(_PINS.get("art") == art_pins(), "the authored art differs from the pinned art")
        require(_PINS.get("rules_sha256") == sha(RULES_PATH.read_bytes()), "the rules differ from the pinned rules")
    return _PINS


def metlife_entries(archive):
    """{filename: entry} for the eighteen MetLife bundles present in an archive."""
    ids = {name_id(name): name for name in VARIANTS}
    return {ids[e.name_id]: e for e in archive.entries if e.name_id in ids}


def _bundle_state(archive, pin):
    if pin["outer"] >= len(archive.entries):
        return "foreign"
    entry = archive.entries[pin["outer"]]
    if entry.name_id != pin["name_id"] or entry.size != pin["size"]:
        return "foreign"
    states = set()
    for site in pin["sites"]:
        have = sha(archive.read(entry.virtual_offset + site["offset"], site["size"]))
        if have == site["retail"]:
            states.add("retail")
        elif have == site["applied"]:
            states.add("applied")
        else:
            return "foreign"
    return "mixed" if len(states) > 1 else states.pop()


def _rost_state(archive):
    entry = archive.entries[ROST_OUTER_INDEX]
    return rost_status(archive.read(entry.virtual_offset, entry.size))


def image_status(source):
    """retail / applied / mixed / foreign across the eighteen bundles and the venue name.

    A source that carries the Modern MetLife model (b76-u5) reads as applied: the model only ever writes over the
    skin (its build step requires the skin's state) and replaces bytes this option's pins cover, so the bundles
    alone would read foreign."""
    state = _skin_status(source)
    if state in ("foreign", "mixed"):
        try:
            from . import nfl2k5_metlife_model as model
            with _outer_image()(source) as archive:
                rost = _rost_state(archive)
            if rost == "applied" and model.image_status(source) == "applied":
                return "applied"
        except (ImportError, OSError, ValueError):
            pass
    return state


def _skin_status(source):
    pins = _pins()
    from . import nfl2k5_modern_color as colour
    receipt = colour.read_image_receipt(source)
    combined = receipt.get("modern_metlife") if receipt else None
    with _outer_image()(source) as archive:
        rost = _rost_state(archive)
        if combined is not None:
            require(combined.get("art") == art_pins(), "Combined MetLife art pins differ")
            require(set(combined.get("bundles", {})) == {p["name"] for p in pins["bundles"]},
                    "Combined MetLife receipt must cover all eighteen bundles")
            for pin in pins["bundles"]:
                row = combined["bundles"][pin["name"]]
                require(row.get("retail_sha256") == pin["retail_sha256"], "Combined MetLife source differs")
                entry = archive.entries[pin["outer"]]
                require(entry.name_id == pin["name_id"] and entry.size == pin["size"], "Combined MetLife entry differs")
                data = archive.read(entry.virtual_offset, entry.size)
                if sha(data) != row.get("applied_sha256"):
                    return "foreign"
            return "applied" if rost == "applied" else ("mixed" if rost == "retail" else "foreign")
        states = {_bundle_state(archive, pin) for pin in pins["bundles"]}
    states.add(rost)
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign" if "foreign" in states else "mixed"


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    require(state == ("applied" if enabled else "retail"), "MetLife bundles do not match the requested option")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(_pins()["bundles"]))


def _compile_one(job):
    name, data, dry = job
    after, edits = modern_bundle(data, name, dry)
    return name, after, edits


def _workers(requested=None):
    import os
    if requested is not None:
        return max(1, int(requested))
    return max(1, min(len(VARIANTS), (os.cpu_count() or 2) // 2))


def run_jobs(function, jobs, *, workers=None, progress=None, label="Modern MetLife"):
    """Map ``function`` over ``jobs`` in worker processes (in order of completion), reporting progress."""
    say = progress or (lambda message, done, total: None)
    count = _workers(workers)
    results = []
    if count == 1 or len(jobs) == 1:
        for index, job in enumerate(jobs):
            say(f"{label}: {job[0]} ({index + 1} of {len(jobs)})", index, len(jobs))
            results.append(function(job))
        return results
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(official.run_with_pack, function, job, official.selected_root()) for job in jobs]
        for index, future in enumerate(as_completed(futures)):
            results.append(future.result())
            say(f"{label}: {results[-1][0]} ({index + 1} of {len(jobs)})", index + 1, len(jobs))
    return results


def _compile_all(read_bundle, progress=None, workers=None):
    """{filename: (retail bytes, applied bytes, edits)} for all eighteen bundles (compiled in parallel)."""
    retail = {name: read_bundle(name) for name in VARIANTS}
    jobs = [(name, retail[name], retail[dry_name(name)]) for name in VARIANTS]
    out = {}
    for name, after, edits in run_jobs(_compile_one, jobs, workers=workers, progress=progress):
        out[name] = (retail[name], after, edits)
    return out


@official.requires_pack("modern_metlife")
def apply_to_image(target, *, progress=None, retail_source=None):
    """Build-only: target must be the caller's disposable output image (or loose folder)."""
    from . import nfl2k5_modern_color as colour
    if colour.read_image_receipt(target) is not None:
        return apply_combined_to_image(target, retail_source=retail_source, progress=progress)
    pins = _pins()
    say = progress or (lambda message, done, total: None)
    receipt = dict(label=LABEL, runtime_witnessed=False, bundles=[], edits=[])
    by_name = {p["name"]: p for p in pins["bundles"]}
    with _outer_image()(target, writable=True) as archive:
        states = {}
        for pin in pins["bundles"]:
            states[pin["name"]] = _bundle_state(archive, pin)
            require(states[pin["name"]] in ("retail", "applied"),
                    f"{pin['name']}: {states[pin['name']]} bundle; rebuild from a supported base")

        def read(name):
            pin = by_name[name]
            entry = archive.entries[pin["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            if states[name] == "retail":
                require(sha(data) == pin["retail_sha256"], f"{name}: bundle bytes differ from the retail pin")
            return data

        if set(states.values()) != {"applied"}:
            require(set(states.values()) == {"retail"}, "MetLife bundles are partly applied; rebuild from retail")
            compiled = _compile_all(read, progress=say)
            for name, (data, after, edits) in compiled.items():
                pin = by_name[name]
                require(sha(after) == pin["applied_sha256"], f"{name}: the refit bundle differs from the applied pin")
                entry = archive.entries[pin["outer"]]
                archive.write(entry.virtual_offset, after)
                require(archive.read(entry.virtual_offset, entry.size) == after, f"{name}: write-back mismatch")
                receipt["bundles"].append(dict(name=name, state="applied",
                                               changed_bytes=sum(a != b for a, b in zip(data, after))))
                receipt["edits"].append(dict(name=name, edits=[{k: v for k, v in e.items() if k != "weather_fit"}
                                                                for e in edits]))
        else:
            receipt["bundles"] = [dict(name=n, state="already_applied") for n in states]
        receipt["venue_name"] = _apply_rost(archive)
    say("Modern MetLife: done", 1, 1)
    receipt.update(verify(target, enabled=True))
    return receipt


def _apply_rost(archive):
    entry = archive.entries[ROST_OUTER_INDEX]
    data = archive.read(entry.virtual_offset, entry.size)
    state = rost_status(data)
    require(state in ("retail", "applied"), f"ROST stadium names are {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_rename(data)
    require(len(after) == len(data), "ROST rename changed the resource size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "ROST rename write-back mismatch")
    return dict(receipt, changed_bytes=sum(a != b for a, b in zip(data, after)))


def combined_bundle(retail, graded, filename, dry_retail, *, outer_index, settings=None):
    """Compose MetLife art before the colour grade and compress the shared field once."""
    from . import nfl2k5_modern_color as colour
    require(len(retail) == len(graded), "Combined bundle changed allocation")
    venue, _tod, weather = variant_parts(filename)
    dry = dry_reference(dry_retail)
    out = bytearray(graded)
    edits = []
    for name, chunk in sorted(bundle_scenes(retail).items(), key=lambda kv: kv[1].offset):
        before = scene_span(retail, chunk)
        if name == "field":
            after, detail = graded_field_span(before, venue, weather, dry, outer_index=outer_index, settings=settings)
        else:
            require(graded[chunk.offset:chunk.offset + len(before)] == before,
                    f"{filename} {name}: the colour grade touched a scene it does not own")
            after, detail = modern_scene_span(retail, chunk, venue, weather, dry.get(name))
        require(len(after) == len(before), "Combined scene escaped its allocation")
        out[chunk.offset:chunk.offset + len(before)] = after
        edits.append(dict(kind=name, offset=chunk.offset, size=len(before), retail=sha(before), applied=sha(after),
                          detail={k: v for k, v in detail.items() if k != "weather_fit"}))
    return bytes(out), edits


def _combined_one(job):
    name, retail, graded, dry, outer_index, settings = job
    after, edits = combined_bundle(retail, graded, name, dry, outer_index=outer_index, settings=settings)
    return name, after, edits


def apply_combined_to_image(target, *, retail_source, progress=None):
    """Add MetLife to a verified colour build using its original retail source."""
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    previous = colour.read_image_receipt(target)
    require(previous is not None, "Combined MetLife requires a colour receipt")
    require(colour.image_status(target, receipt=previous) == previous["state"],
            "Colour bytes differ from their receipt; rebuild from the original retail disc")
    if previous.get("modern_metlife") is not None:
        return dict(verify(target), already_applied=len(VARIANTS), rewritten=0)
    require(retail_source is not None, "Combined MetLife needs the original retail source")
    say = progress or (lambda message, done, total: None)
    result = deepcopy(previous)
    combined = dict(art=art_pins(), rules_sha256=sha(RULES_PATH.read_bytes()), bundles={})
    pins = {p["name"]: p for p in _pins()["bundles"]}
    order = sorted(VARIANTS, key=lambda n: (n[:4], n[4] != "d", n))
    retail_cache, graded_cache, jobs = {}, {}, []
    with _outer_image()(retail_source) as source, _outer_image()(target) as output:
        for name in order:
            pin = pins[name]
            entry = source.entries[pin["outer"]]
            require(entry.name_id == pin["name_id"] and entry.size == pin["size"], "MetLife source entry differs")
            retail = source.read(entry.virtual_offset, entry.size)
            require(sha(retail) == pin["retail_sha256"], "Combined MetLife needs the original retail source")
            retail_cache[name] = retail
            target_entry = output.entries[pin["outer"]]
            graded = output.read(target_entry.virtual_offset, target_entry.size)
            require(sha(graded) == result["bundle_pins"][name]["applied_sha256"], "Colour bundle changed after preflight")
            graded_cache[name] = (target_entry.virtual_offset, graded)
    for name in order:
        jobs.append((name, retail_cache[name], graded_cache[name][1], retail_cache[dry_name(name)],
                     pins[name]["outer"], previous["settings"]))
    done = {name: (after, edits) for name, after, edits in
            run_jobs(_combined_one, jobs, progress=say, label="Modern MetLife and colour")}
    todo = []
    for name in order:
        after, edits = done[name]
        pin, row = pins[name], result["bundle_pins"][name]
        at, graded = graded_cache[name]
        result["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[dict(site,
            applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        combined["bundles"][name] = dict(retail_sha256=pin["retail_sha256"], applied_sha256=sha(after),
                                         sites=[{k: e[k] for k in ("kind", "offset", "size", "retail", "applied")}
                                                for e in edits])
        todo.append((at, sha(graded), after))
    with _outer_image()(target, writable=True) as output:
        for at, before_hash, after in todo:
            require(sha(output.read(at, len(after))) == before_hash, "Combined bundle changed before write")
            require(output.write(at, after) == len(after), "Short combined MetLife write")
            require(output.read(at, len(after)) == after, "Combined MetLife read-back differs")
        venue_receipt = _apply_rost(output)
    result["modern_metlife"] = combined
    require(colour.image_status(target, receipt=result) == result["state"], "Combined colour read-back failed")
    colour._save_image_receipt(target, result)
    return dict(verify(target), rewritten=len(todo), already_applied=0, venue_name=venue_receipt)


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compute retail and applied pins for the eighteen bundles and the ROST from a retail source."""
    say = progress or (lambda message, done, total: None)
    bundles = []
    with _outer_image()(source) as archive:
        entries = metlife_entries(archive)
        require(set(entries) == set(VARIANTS), f"MetLife bundles missing: {sorted(set(VARIANTS) - set(entries))}")

        def read(name):
            entry = entries[name]
            return archive.read(entry.virtual_offset, entry.size)

        compiled = _compile_all(read, progress=say)
        for name in VARIANTS:
            data, after, edits = compiled[name]
            entry = entries[name]
            bundles.append(dict(name=name, outer=entry.index, name_id=entry.name_id, size=entry.size,
                                retail_sha256=sha(data), applied_sha256=sha(after),
                                sites=[dict(kind=e["kind"], offset=e["offset"], size=e["size"], retail=e["before_sha256"],
                                            applied=e["after_sha256"], encoder=e.get("encoder"),
                                            padding_bytes=e.get("padding_bytes"),
                                            patches=[p["material"] for p in e.get("patches", ())],
                                            overlays=[p["material"] for p in e.get("overlays", ())],
                                            palettes=[p["material"] for p in e.get("palettes", ())],
                                            geometry=[g["shape"] for g in e.get("geometry", ())]) for e in edits]))
        rost_entry = archive.entries[ROST_OUTER_INDEX]
        rost = archive.read(rost_entry.virtual_offset, rost_entry.size)
        renamed, rost_receipt = rost_rename(rost)
    document = dict(schema=PINS_SCHEMA, venue="MetLife Stadium (Giants s18, Jets s19)", art=art_pins(),
                    rules_sha256=sha(RULES_PATH.read_bytes()), bundles=bundles,
                    rost=dict(outer=ROST_OUTER_INDEX, retail_sha256=sha(rost), applied_sha256=sha(renamed),
                              records=rost_receipt["records"]))
    Path(out_path).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    return document


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_modern_metlife")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status"); s.add_argument("source")
    r = sub.add_parser("record-pins"); r.add_argument("source"); r.add_argument("--out", default=str(PINS_PATH))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source)); return 0
    document = record_pins(args.source, args.out, progress=lambda m, d, t: print(f"  {m}", flush=True))
    print(json.dumps({b["name"]: [(s["kind"], s["encoder"], s["padding_bytes"]) for s in b["sites"]]
                      for b in document["bundles"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
