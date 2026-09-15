"""Modern colour and lighting for ESPN NFL 2K5. EXPERIMENTAL / UNWITNESSED.

Two families of data edits, no executable code, no cave, no hook, no runtime
allocation:

1. Executable light rigs. ``FUN_000641c0`` selects one of seven 0x120-byte
   light tables in ``.rdata`` by indoor / rain / snow / day / afternoon / night
   and ``FUN_000f2360`` installs it: an ambient colour and intensity, then two
   or three directional lights (colour, direction, intensity). Retail day light
   is yellow (1.0, 1.0, 0.722), the afternoon rig is orange and every ambient is
   dim; blue collapses on grass and white uniforms go warm. The broadcast rigs
   are neutral white with more fill. Directions, light counts and the shadow
   value at +0x100 are untouched.

2. Stadium bundles (``sNN{d,a,n}{d,r,s}.iff``, 477 archive outers). Per bundle:
   the Fldd time-of-day tint word (uncompressed), the ``detail_normal`` grass
   bump palette (uncompressed) flattened, and the ``field`` scene refit into the
   same fixed VC-LZ span with the grass colour-map and outside-grass palettes
   re-graded toward the measured broadcast turf and the afternoon vertex tint
   softened. Bundles without a colour-map texture re-grade their grass material
   colour words instead.

Targets come from 2026 Week 1 broadcast stills measured per game (see
docs/modern_color/ and FABLE_B70_COLOR_REPORT_2026-09-15.md). Proved offline by
byte receipts and decoder read-back; appearance in game is UNWITNESSED.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_modern_color"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Modern colour and lighting (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Rewrites the seven light rigs the game installs by time "
    "of day and weather to neutral, white-balanced broadcast values with more fill, and "
    "re-grades every stadium's grass colour map and outside grass about 1.7x brighter and "
    "slightly more saturated (calibrated to the turf measured in 2026 Week 1 broadcasts), "
    "flattens the grass bump map and neutralises the night and afternoon tints. Light "
    "directions, counts and shadows keep retail values. Refits 362 field scenes: about eight "
    "minutes on an eight-core Linux machine, longer on a laptop. Off in every preset."
)
ROOT = Path(__file__).resolve().parents[2]
PINS_PATH = ROOT / "data" / "nfl2k5_modern_color_pins.json"
PINS_SCHEMA = "nfl2k5_modern_color_pins/v1"
TABLE_SIZE = 0x120
# (name, VA, retail SHA-256). Every table lives in .rdata; FUN_000641c0 picks it.
LIGHT_TABLES = (
    ("day", 0x4e73b0, "8591344f69f7a0013c4e9cf9b5ae4e8dbc4f894488b97dd2a97be8885f9073e1"),
    ("night_indoor", 0x4e74d0, "d27737d3020b5ae17ed9854c1a1f372f004b68ed7aca92d263b267414098d782"),
    ("alt_day", 0x4e75f0, "6aa37cf70658ad446dc83df3201eca0e826c6b66fbdfdf68d0cf2b546dddaedb"),
    ("alt_dynamic", 0x4e7710, "80e6f376951a72abadbc337078f48136ce23c5e03bad72e151f451add8048bd0"),
    ("rain", 0x4e7830, "1fb3e7fe93ff73a2d1ddf11ac443e57c65459cf833b6104cd357bf8b96572758"),
    ("snow", 0x4e7950, "7a28bdcdc00c37078da18e5479ea534071c6a7a9389f445fe7c72d5773ad1c5d"),
    ("afternoon", 0x4e7a70, "d789e452238ca98842b941776b63befb0b264bbf513bb303a7f67ff031d40e15"),
)
# The selector, the installer and the per-light push must be the retail routines.
GUARDS = (
    (0x641c0, 0x1d5, "6ebd76243822a62010a280cf54d9b72974a6236501f68d45aad19421d3377e28"),
    (0xf2360, 0x168, "c9f0e5c7bd79926056f91cd21d8ae05b929eb5d635e22da5ea89d941bfdc7f9b"),
    (0xf24d0, 0x4c, "ff172eb5cc10369aa706e6b6b350f94aa48d1b5de0f2ae54f4e00cc4a1a77e4d"),
)
# Broadcast rigs. Ambient (r, g, b) and intensity, then (colour, intensity) per
# light in table order. Measured 2026 Week 1 whites sit at (215..245, 218..243,
# 223..241): neutral to slightly cool, never yellow. Night is LED white.
MODERN_RIGS = {
    "day": dict(ambient=(0.94, 0.96, 1.00), ambient_intensity=0.58,
                lights=(((1.00, 0.98, 0.94), 1.20), ((0.90, 0.94, 1.00), 0.48))),
    "night_indoor": dict(ambient=(1.00, 1.00, 1.00), ambient_intensity=0.50,
                         lights=(((1.00, 1.00, 1.00), 0.86),) * 3),
    "alt_day": dict(ambient=(0.92, 0.95, 1.00), ambient_intensity=0.45,
                    lights=(((1.00, 0.98, 0.94), 1.10), ((0.90, 0.94, 1.00), 0.40), ((0.90, 0.94, 1.00), 0.40))),
    "alt_dynamic": dict(ambient=(0.95, 0.97, 1.00), ambient_intensity=0.42,
                        lights=(((1.00, 0.97, 0.92), 1.10), ((0.90, 0.94, 1.00), 0.40), ((0.90, 0.94, 1.00), 0.40))),
    "rain": dict(ambient=(0.92, 0.93, 0.98), ambient_intensity=0.46,
                 lights=(((0.92, 0.94, 1.00), 0.70),) * 3),
    "snow": dict(ambient=(0.96, 0.97, 1.00), ambient_intensity=0.50,
                 lights=(((0.95, 0.96, 1.00), 0.62),) * 3),
    "afternoon": dict(ambient=(1.00, 0.95, 0.86), ambient_intensity=0.45,
                      lights=(((1.00, 0.94, 0.84), 1.20), ((0.70, 0.78, 1.00), 0.26), ((0.70, 0.78, 1.00), 0.26))),
}
# Bundle edits (beta 71 calibration). The drawn field is far darker than the
# colour map times the rig: the beta 70 build measured (51, 61, 32) at Arrowhead
# at night where the flat estimate was (232, 255, 160), so on screen the field
# is about 0.47 x colour map (0.43 on blue) under the night rig. The broadcast
# turf there is (107, 121, 53). Hitting it needs the map about 1.7x brighter and
# the rig about 1.2x stronger, kept slightly more saturated and pulled toward
# the Arrowhead hue (73 degrees). Value is lifted through a curve, 1 - (1 - v)^G,
# so the darkest blades gain the most and the brightest never clip.
HUE_TARGET, HUE_PULL, SAT_SCALE, VAL_GAMMA = 72.0, 0.50, 1.12, 2.8
NORMAL_FLATTEN = 0.32
# v2.1 (2026-09-15, from the first colour v2 test): the field also draws a "divots"
# wear layer (64x64 P8, dark green, about 36 percent alpha over most of the turf)
# that read as player-sized dark blotches once the turf was bright; its greens are
# re-graded like the turf and its alpha scaled down. The six end-zone maps carry
# their own green background and are re-graded too; the outside grass texture is
# 45 percent darker than the field map and its shape darkens toward the edges
# through grey vertex colours, so its palette is lifted to the field's mean and
# the grey falloff is halved; the end-zone overlays take the softened tint.
DIVOTS_NAME = "divots"
DIVOTS_ALPHA = 0.30
END_ZONE_MATERIALS = ("endzone_N_L", "endzone_N_M", "endzone_N_R", "endzone_S_L", "endzone_S_M", "endzone_S_R", "center_logo")
OVERLAY_SHAPES = ("D_graphic_overlays",)
OUTSIDE_VERTEX_FALLOFF = 0.45
TINTS = {0xFFFFEECD: 0xFFFFF5E6, 0xFFF2FFFF: 0xFFFFFFFF}
VERTEX_TINTS = {(255, 238, 205, 255): (255, 245, 230, 255), (242, 255, 255, 255): (255, 255, 255, 255),
                (255, 255, 229, 255): (255, 255, 240, 255)}
# On-screen calibration per rig family: measured drawn turf divided by the flat
# estimate, flat = map x (ambient x intensity + sum of light colour x intensity).
# Night: the beta 70 build at Arrowhead (map (109, 130, 75) under the beta 70 rig,
# gain (2.56, 2.56, 2.58), flat (278, 333, 194)) drew (51, 61, 32) on 2026-09-15.
# Day: the retail build (map (100, 125, 66), retail day rig gain (1.61, 1.67, 1.34),
# flat (161, 208, 88)) drew (34, 43, 2) on 2026-09-07; blue collapsed under the
# yellow retail key, so the day blue factor is taken from green.
SCREEN_FACTOR = {"night_indoor": (0.183, 0.183, 0.165), "day": (0.21, 0.21, 0.21)}
FIELD_SCENE = "field"
COLOR_MAP_MATERIAL = "color_premipped"
OUTSIDE_MATERIAL = "grass_outside_premipped"
NORMAL_NAME = "detail_normal"
GRASS_SHAPES = ("A_grass_color", "Outside_grass")


class ModernColorError(ValueError):
    """A plain refusal before any mutation."""


def require(ok, message):
    if not ok:
        raise ModernColorError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# --- executable light rigs ---------------------------------------------------

def modern_table(retail):
    """Return the broadcast table for one retail 0x120-byte light table."""
    require(len(retail) == TABLE_SIZE, "light table size")
    name = next((n for n, _va, digest in LIGHT_TABLES if digest == sha(retail)), None)
    require(name is not None, "not a retail light table")
    rig = MODERN_RIGS[name]
    count = struct.unpack_from("<I", retail, 0x14)[0]
    require(count == len(rig["lights"]), f"{name}: light count {count} differs from the rig")
    out = bytearray(retail)
    struct.pack_into("<3f", out, 0, *rig["ambient"])
    struct.pack_into("<f", out, 0x10, rig["ambient_intensity"])
    for index, (colour, intensity) in enumerate(rig["lights"]):
        base = 0x20 + index * 0x40
        struct.pack_into("<3f", out, base, *colour)
        struct.pack_into("<f", out, base + 0x20, intensity)
    return bytes(out)


def _table_states(image):
    for va, size, digest in GUARDS:
        require(sha(image.read(va, size)) == digest, f"Light selector changed at {va:#x}; rebuild from a supported base")
    states = []
    for name, va, digest in LIGHT_TABLES:
        require(image.section(va).name == ".rdata", "light table is not in .rdata")
        have = image.read(va, TABLE_SIZE)
        if sha(have) == digest:
            states.append("retail")
            continue
        retail = _retail_table(name)
        if retail is not None and have == modern_table(retail):
            states.append("applied")
        else:
            states.append("foreign")
    return states


_RETAIL_TABLES = {}


def _retail_table(name):
    """Retail table bytes are recovered from an applied table only when the
    pins file carries them; status on an applied executable needs them."""
    if not _RETAIL_TABLES:
        pins = _pins(optional=True)
        for row in (pins or {}).get("light_tables", []):
            _RETAIL_TABLES[row["name"]] = bytes.fromhex(row["retail_hex"])
    return _RETAIL_TABLES.get(name)


def xbe_status(payload):
    try:
        states = _table_states(XbeImage(payload))
    except (ValueError, TypeError, IndexError, struct.error):
        return "foreign"
    if all(s == "retail" for s in states):
        return "retail"
    if all(s == "applied" for s in states):
        return "applied"
    return "foreign"


status = xbe_status


def verify(payload, *, enabled=True):
    require(type(enabled) is bool, "Modern colour and lighting must be Off or On")
    state = xbe_status(payload)
    require(state == ("applied" if enabled else "retail"), "Light rigs do not match the requested option")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False,
                tables=[dict(name=n, va=hex(va)) for n, va, _ in LIGHT_TABLES])


def apply(payload, *, enabled=True):
    """Executable part only. Returns (patched bytes, receipt)."""
    require(type(enabled) is bool, "Modern colour and lighting must be Off or On")
    image = XbeImage(payload)
    states = _table_states(image)
    require("foreign" not in states, "Foreign light tables; rebuild from a supported base")
    result = bytearray(payload)
    edits = []
    for (name, va, digest), state in zip(LIGHT_TABLES, states):
        retail = image.read(va, TABLE_SIZE) if state == "retail" else _retail_table(name)
        require(retail is not None, "retail light table unavailable for restore")
        after = modern_table(retail) if enabled else retail
        at = image.offset(va, TABLE_SIZE)
        if bytes(result[at:at + TABLE_SIZE]) != after:
            result[at:at + TABLE_SIZE] = after
            edits.append(dict(label=name, va=hex(va), size=TABLE_SIZE))
    section = image.section(LIGHT_TABLES[0][1])
    for s in _sections(result):
        if s.header_offset == section.header:
            result[s.header_offset + 36:s.header_offset + 56] = section_digest(result, s)
    result = bytes(result)
    return result, dict(verify(result, enabled=enabled),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)), edits=edits)


def reservations(payload):
    verify(payload)
    return [dict(owner=OWNER, start=hex(va), end=hex(va + TABLE_SIZE), size=TABLE_SIZE,
                 basis=f"pinned existing .rdata light rig '{name}' rewritten in place; no runtime space")
            for name, va, _ in LIGHT_TABLES]


# --- palettes, tints, bump map -----------------------------------------------

def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_txtr as tx  # noqa: E402
    import nfl_scne_inventory as inv  # noqa: E402
    from nfl_scene_probe import ResourceRecord, HEADER  # noqa: E402
    return tx, inv, ResourceRecord, HEADER


def regrade_palette(palette, *, gain=1.0, alpha_scale=1.0):
    """Re-grade the green entries of a 256-entry B,G,R,A palette; others untouched.

    ``gain`` multiplies the lifted value (the outside grass is brought up to the
    field's mean); ``alpha_scale`` scales every entry's alpha (the divots layer).
    """
    require(len(palette) == 1024, "palette size")
    out = bytearray(palette)
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h *= 360
        new_a = min(255, max(0, round(a * alpha_scale)))
        if not (45 <= h <= 150 and s > 0.15 and v > 0.10):
            if new_a != a:
                out[i * 4 + 3] = new_a
            continue
        h = (h + (HUE_TARGET - h) * HUE_PULL) / 360
        s = min(1.0, s * SAT_SCALE)
        v = min(1.0, lift_value(v) * gain)
        r2, g2, b2 = (min(255, max(0, round(c * 255))) for c in colorsys.hsv_to_rgb(h, s, v))
        out[i * 4:i * 4 + 4] = bytes((b2, g2, r2, new_a))
    return bytes(out)


def _green_mean_value(out, system, texture, palette):
    """Mean HSV value of the green palette entries actually used by the base level."""
    tx, inv, ResourceRecord, HEADER = _tools()
    width, height = texture["width"], texture["height"]
    at = system + texture["pixel_offset"]
    indices = tx.unswizzle_2d(out[at:at + width * height], width, height, 1)
    counts = [0] * 256
    for index in indices:
        counts[index] += 1
    total = weighted = 0.0
    for i in range(256):
        if not counts[i]:
            continue
        b, g, r, a = palette[i * 4:i * 4 + 4]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if 45 <= h * 360 <= 150 and s > 0.15 and v > 0.10:
            total += counts[i]
            weighted += counts[i] * v
    return weighted / total if total else None


def lift_value(v):
    """The beta 71 brightness curve: 1 - (1 - v)^VAL_GAMMA, monotone, never clips."""
    return 1.0 - (1.0 - v) ** VAL_GAMMA


def predicted_on_screen(colour_map_rgb, rig="night_indoor"):
    """Calibrated estimate of the drawn turf for a colour-map mean under a rig.

    flat = map x (ambient x intensity + sum of light colour x intensity) per channel;
    on screen = flat x SCREEN_FACTOR (the measured ratio, see the constants above).
    Returns (retail-map estimate is the caller's business) an (r, g, b) tuple.
    """
    table = MODERN_RIGS[rig]
    factor = SCREEN_FACTOR.get(rig, SCREEN_FACTOR["night_indoor"])
    out = []
    for c in range(3):
        gain = table["ambient"][c] * table["ambient_intensity"] + sum(col[c] * i for col, i in table["lights"])
        out.append(min(255, round(colour_map_rgb[c] * gain * factor[c])))
    return tuple(out)


def looks_like_normal_palette(palette):
    blues = sorted(palette[i * 4] for i in range(256))
    return blues[128] > 180


def flatten_normal_palette(palette):
    """Pull tangent-space normals toward flat by NORMAL_FLATTEN; z is recomputed."""
    require(len(palette) == 1024, "palette size")
    if not looks_like_normal_palette(palette):
        return bytes(palette)
    out = bytearray(palette)
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        x, y = (r / 127.5 - 1.0) * NORMAL_FLATTEN, (g / 127.5 - 1.0) * NORMAL_FLATTEN
        z = math.sqrt(max(0.0, 1.0 - x * x - y * y))
        enc = lambda c: min(255, max(0, round((c + 1.0) * 127.5)))
        out[i * 4:i * 4 + 4] = bytes((enc(z), enc(y), enc(x), a))
    return bytes(out)


def regrade_colour_word(word):
    """ARGB material colour: re-grade greens like a palette entry, keep alpha."""
    a, r, g, b = (word >> 24) & 255, (word >> 16) & 255, (word >> 8) & 255, word & 255
    entry = regrade_palette(bytes((b, g, r, a)) * 256)[:4]
    return (entry[3] << 24) | (entry[2] << 16) | (entry[1] << 8) | entry[0]


# --- one stadium bundle -----------------------------------------------------

def _chunks(data):
    tx, inv, ResourceRecord, HEADER = _tools()
    return tx.parse_chunks(data, allow_trailing=True)


def _scene(data, chunk, outer_index=0):
    tx, inv, ResourceRecord, HEADER = _tools()
    record = ResourceRecord(outer_index=outer_index, outer_id="", outer_size=len(data), chunk_index=chunk.index,
                            chunk_offset=chunk.offset, kind=chunk.kind, stored_size=chunk.stored_size,
                            word_08=chunk.system_bytes, word_0c=chunk.video_bytes, word_10=chunk.compression_magic,
                            word_14=chunk.overlap_scratch_bytes)
    output, _ = tx.decode_chunk(data, chunk)
    rec, _names, _maps, _sample = inv.parse_scene(chunk.index, record, output, {})
    return rec, output, record


def _early_fill(encoded, decoded, cap):
    """Spend spare bytes on literals from the FRONT of the stream (the stadium
    writer's proved recipe), leaving at most 16 spare bytes when possible."""
    import nfl_vc_lz_fill as fill  # noqa: E402
    size, tag, bits, tokens = fill.parse_tokens(encoded)
    require(size == len(decoded), "VC-LZ fill source size changed")
    count, length, position, result = len(tokens), len(encoded), 0, []
    for token in tokens:
        amount = token[2] if token[0] == "M" else 1
        if token[0] == "M" and length < cap - 16:
            new_count = count + amount - 1
            gain = amount - 2 + (new_count + 7) // 8 - (count + 7) // 8
            if length + gain <= cap:
                result.extend(("L", value) for value in decoded[position:position + amount])
                count, length = new_count, length + gain
            else:
                result.append(token)
        else:
            result.append(token)
        position += amount
    filled = fill.serialize(size, tag, bits, result)
    require(len(filled) == length <= cap, "VC-LZ fill exceeded its fixed span")
    return filled


def fit_fixed_span(span, decoded):
    """Recompress ``decoded`` into ``span`` keeping the 32-byte wrapper byte-identical.

    Wrapper word +0x14 is the loader's in-place scratch; raising it hung the
    loader on 2026-09-03, so every candidate is checked against the retail value:
    greedy then optimal parsing, each with the trailing fill and the front fill.
    """
    tx, inv, ResourceRecord, HEADER = _tools()
    import nfl_vc_lz_fill as fill  # noqa: E402
    fields = HEADER.unpack_from(span)
    raw_kind, stored, system_bytes, video_bytes, magic, scratch, r0, r1 = fields
    require(len(span) == HEADER.size + stored and magic == tx.COMPRESSED_SENTINEL, "not a compressed fixed span")
    require(len(decoded) == system_bytes + video_bytes, "decoded size differs from the wrapper")
    prefix = span[HEADER.size:HEADER.size + 9]
    declared, tag = struct.unpack_from("<II", prefix)
    bits = prefix[8]
    require(declared == len(decoded), "template stream declares another size")
    attempts = []
    encoders = (("greedy", lambda: tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, max_encoded_size=stored, verify_roundtrip=True)[0]),
                ("optimal", lambda: fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits)))
    for encoder_name, encode in encoders:
        try:
            encoded = encode()
        except tx.TxtrError as exc:
            attempts.append(f"{encoder_name}: {exc}")
            continue
        if len(encoded) > stored:
            attempts.append(f"{encoder_name}: {len(encoded)} bytes exceeds {stored}")
            continue
        for fill_name, filler in (("trailing", lambda e: fill.fill_stream(e, decoded, stored, slack=min(scratch, 16))[0]),
                                  ("front", lambda e: _early_fill(e, decoded, stored))):
            try:
                filled = filler(encoded) if stored - len(encoded) > scratch else encoded
            except tx.TxtrError as exc:
                attempts.append(f"{encoder_name}/{fill_name}: {exc}")
                continue
            padding = stored - len(filled)
            alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
            if padding <= scratch and alias <= scratch:
                rebuilt = span[:HEADER.size] + filled + bytes(padding)
                back, info = tx.decompress_vc_lz(rebuilt[HEADER.size:], len(decoded))
                require(back == decoded and info.consumed_bytes == len(filled), "rebuilt stream failed its decode check")
                return rebuilt, dict(encoder=encoder_name, fill=fill_name, padding_bytes=padding, alias_scratch=alias, scratch_bytes=scratch)
            attempts.append(f"{encoder_name}/{fill_name}: padding {padding}, needs {alias}, retail {scratch}")
    raise tx.TxtrError("cannot keep the retail scratch word: " + "; ".join(attempts))


def modern_field_scene(span, *, outer_index=0):
    """Refit one compressed ``field`` SCNE span with the broadcast grass edits.

    Returns (new span, receipt). The span keeps its size and wrapper structure.
    """
    tx, inv, ResourceRecord, HEADER = _tools()
    chunks = tx.parse_chunks(span, allow_trailing=True)
    require(len(chunks) == 1 and chunks[0].kind == "SCNE" and chunks[0].offset == 0, "not a single SCNE span")
    chunk = chunks[0]
    rec, output, record = _scene(span, chunk, outer_index)
    require(rec["name"] == FIELD_SCENE, "the first bundle scene is not the field")
    system = rec["system_bytes"]
    out = bytearray(output)
    receipt = dict(palettes=[], materials=[], vertex_tints=0)
    by_material = {}
    for texture in rec["embedded_textures"]:
        for name in texture.get("mapped_material_names") or ():
            by_material[name] = texture
    field_mean = None
    done_palettes = set()
    for name in (COLOR_MAP_MATERIAL, OUTSIDE_MATERIAL) + END_ZONE_MATERIALS:
        texture = by_material.get(name)
        if texture is None:
            continue
        require(texture["format_name"] == "P8", f"{name} is not P8")
        at = system + texture["palette_offset"]
        if at in done_palettes:
            continue  # the north and south end zones share one texture
        done_palettes.add(at)
        before = bytes(out[at:at + 1024])
        gain = 1.0
        if name == COLOR_MAP_MATERIAL:
            field_mean = _green_mean_value(out, system, texture, regrade_palette(before))
        elif name == OUTSIDE_MATERIAL and field_mean:
            # Lift the outside grass to the field's mean so the sidelines match the turf.
            outside_mean = _green_mean_value(out, system, texture, regrade_palette(before))
            if outside_mean:
                gain = min(2.5, max(1.0, field_mean / outside_mean))
        after = regrade_palette(before, gain=gain)
        out[at:at + 1024] = after
        receipt["palettes"].append(dict(material=name, offset=at, gain=round(gain, 3), changed=sum(a != b for a, b in zip(before, after))))
    if COLOR_MAP_MATERIAL not in by_material:
        # Turf stadiums draw the field from the material colour words instead.
        for material in rec["materials"]:
            if material["name"] != COLOR_MAP_MATERIAL or material.get("texture_index") is not None:
                continue
            base = material["record_offset"]
            for field in (0x14, 0x18):
                word = struct.unpack_from("<I", out, base + field)[0]
                new = regrade_colour_word(word)
                if new != word:
                    struct.pack_into("<I", out, base + field, new)
                    receipt["materials"].append(dict(material=material["name"], field=hex(field), before=hex(word), after=hex(new)))
    for shape in rec["shapes"]:
        if shape["name"] not in GRASS_SHAPES + OVERLAY_SHAPES:
            continue
        colour = next((a for a in shape["attribute_descriptors"] if a["format_name"] == "D3DCOLOR"), None)
        if colour is None:
            continue
        stream = shape["vertex_streams"][colour["stream_index"]]
        for index in range(shape["vertex_count"]):
            at = stream["offset"] + index * stream["stride"] + colour["byte_offset"]
            b, g, r, a = out[at:at + 4]
            new = VERTEX_TINTS.get((r, g, b, a))
            if new is None and shape["name"] == "Outside_grass" and r == g == b and r < 255 and a == 255:
                # The outside grass darkens toward the edges through grey vertex colours; keep less of the falloff.
                lifted = 255 - round((255 - r) * OUTSIDE_VERTEX_FALLOFF)
                new = (lifted, lifted, lifted, 255)
            if new is not None:
                out[at:at + 4] = bytes((new[2], new[1], new[0], new[3]))
                receipt["vertex_tints"] += 1
    if bytes(out) == output:
        return bytes(span), dict(receipt, refit=False)
    rebuilt, info = fit_fixed_span(span, bytes(out))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(out), "refit read-back differs")
    return rebuilt, dict(receipt, refit=True, **info)


def modern_normal_span(span):
    """Flatten the detail_normal palette inside its chunk span (raw or compressed)."""
    tx, inv, ResourceRecord, HEADER = _tools()
    chunks = tx.parse_chunks(span, allow_trailing=True)
    require(len(chunks) == 1 and chunks[0].kind == "TXTR" and chunks[0].offset == 0, "not a single TXTR span")
    chunk = chunks[0]
    output, decode_info = tx.decode_chunk(span, chunk)
    info = tx.parse_texture(output, chunk)
    require(info.name == NORMAL_NAME and info.format_name == "P8", "not the P8 detail_normal texture")
    edited = bytearray(output)
    # Texture offsets are relative to the video section, after the chunk's system bytes.
    at = chunk.system_bytes + info.palette_offset
    require(looks_like_normal_palette(bytes(output[at:at + 1024])), "detail_normal palette is not where the descriptor says")
    edited[at:at + 1024] = flatten_normal_palette(bytes(output[at:at + 1024]))
    if bytes(edited) == output:
        return bytes(span), dict(refit=False)
    if decode_info is None:
        # Raw chunk: the decoded bytes follow the 32-byte wrapper directly.
        require(span[HEADER.size:HEADER.size + len(output)] == output, "raw chunk layout")
        return span[:HEADER.size] + bytes(edited) + span[HEADER.size + len(output):], dict(refit=False, raw=True)
    rebuilt, fit_info = fit_fixed_span(span, bytes(edited))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(edited), "detail_normal refit read-back differs")
    return rebuilt, dict(refit=True, **fit_info)


def modern_divots_span(span):
    """Fade the divots wear layer: greens re-graded like the turf, alpha scaled down."""
    tx, inv, ResourceRecord, HEADER = _tools()
    chunks = tx.parse_chunks(span, allow_trailing=True)
    require(len(chunks) == 1 and chunks[0].kind == "TXTR" and chunks[0].offset == 0, "not a single TXTR span")
    chunk = chunks[0]
    output, decode_info = tx.decode_chunk(span, chunk)
    info = tx.parse_texture(output, chunk)
    require(info.name == DIVOTS_NAME and info.format_name == "P8", "not the P8 divots texture")
    edited = bytearray(output)
    at = chunk.system_bytes + info.palette_offset
    edited[at:at + 1024] = regrade_palette(bytes(output[at:at + 1024]), alpha_scale=DIVOTS_ALPHA)
    if bytes(edited) == output:
        return bytes(span), dict(refit=False)
    if decode_info is None:
        require(span[HEADER.size:HEADER.size + len(output)] == output, "raw chunk layout")
        return span[:HEADER.size] + bytes(edited) + span[HEADER.size + len(output):], dict(refit=False, raw=True)
    rebuilt, fit_info = fit_fixed_span(span, bytes(edited))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(edited), "divots refit read-back differs")
    return rebuilt, dict(refit=True, **fit_info)


def bundle_plan(data):
    """Locate the three edit sites of one bundle: (kind, offset, size, before, after)."""
    tx, inv, ResourceRecord, HEADER = _tools()
    chunks = tx.parse_chunks(data, allow_trailing=True)
    require(chunks and chunks[0].kind == "SCNE" and chunks[0].index == 0, "bundle does not start with the field scene")
    sites = []
    c0 = chunks[0]
    sites.append(("field", c0.offset, HEADER.size + c0.stored_size))
    for chunk in chunks:
        if chunk.kind == "TXTR":
            output, _ = tx.decode_chunk(data, chunk)
            info = tx.parse_texture(output, chunk)
            if info.name == NORMAL_NAME:
                require(info.format_name == "P8", "detail_normal is not P8")
                sites.append(("normal", chunk.offset, HEADER.size + chunk.stored_size))
            elif info.name == DIVOTS_NAME and info.format_name == "P8":
                sites.append(("divots", chunk.offset, HEADER.size + chunk.stored_size))
        if chunk.kind == "Fldd":
            body = data[chunk.offset + HEADER.size:chunk.offset + HEADER.size + chunk.stored_size]
            name_end = body[32:].decode("utf-16le", "ignore").split("\0")[0]
            at = chunk.offset + HEADER.size + 32 + (len(name_end) + 1) * 2 + 8
            sites.append(("tint", at, 4))
    require(any(k == "normal" for k, _, _ in sites) and any(k == "tint" for k, _, _ in sites), "bundle lacks detail_normal or Fldd")
    return sites


def modern_bundle(data, *, outer_index=0, field_cache=None):
    """Return the modern bundle bytes and the edit list for one retail bundle.

    ``field_cache`` maps a field span SHA-256 to its refit span so identical
    field scenes shared by several bundles are refit once.
    """
    out = bytearray(data)
    edits = []
    for kind, at, size in bundle_plan(data):
        before = bytes(data[at:at + size])
        if kind in ("field", "normal", "divots"):
            key = sha(before)
            if field_cache is not None and key in field_cache:
                after, receipt = field_cache[key]
            else:
                after, receipt = _refit_span(kind, before, outer_index)
                if field_cache is not None:
                    field_cache[key] = (after, receipt)
        else:
            word = struct.unpack("<I", before)[0]
            after, receipt = struct.pack("<I", TINTS.get(word, word)), {}
        out[at:at + size] = after
        edits.append(dict(kind=kind, offset=at, size=size, before_sha256=sha(before), after_sha256=sha(after), **receipt))
    return bytes(out), edits


def field_span(data):
    """The first chunk's span (the field scene) of one bundle."""
    tx, inv, ResourceRecord, HEADER = _tools()
    chunk = tx.parse_chunks(data, allow_trailing=True)[0]
    return data[chunk.offset:chunk.offset + HEADER.size + chunk.stored_size]


# --- pins and images -----------------------------------------------------------

_PINS = None


def _pins(*, optional=False):
    global _PINS
    if _PINS is None:
        if not PINS_PATH.is_file():
            if optional:
                return None
            raise ModernColorError("Modern colour pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        require(_PINS.get("schema") == PINS_SCHEMA, "unsupported modern colour pins schema")
    return _PINS


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def _bundle_state(archive, pin):
    entry = archive.entries[pin["outer"]]
    require(entry.name_id == pin["name_id"] and entry.size == pin["size"], f"{pin['name']}: archive entry differs from the pin")
    states = set()
    for site in pin["sites"]:
        have = sha(archive.read(entry.virtual_offset + site["offset"], site["size"]))
        if site["retail"] == site["applied"]:
            # A span the option leaves alone (day-white tint, or a stream that
            # cannot be refit inside its wrapper) cannot tell the two states apart.
            if have != site["retail"]:
                return "foreign"
            continue
        if have == site["retail"]:
            states.add("retail")
        elif have == site["applied"]:
            states.add("applied")
        else:
            return "foreign"
    if not states:
        return "applied"  # nothing for the option to change in this bundle
    return "mixed" if len(states) > 1 else states.pop()


def image_status(source):
    """retail / applied / mixed / foreign across every pinned bundle."""
    pins = _pins()
    with _outer_image()(source) as archive:
        states = {_bundle_state(archive, pin) for pin in pins["bundles"]}
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign" if "foreign" in states else "mixed"


def _refit_span(kind, span, outer_index):
    """Spans that cannot be refit inside their retail wrapper keep their retail bytes.

    A handful of retail streams leave no room. Such a field scene keeps its retail
    colour map (the stadium still gets the light rigs, the tint and, when its own
    bump span fits, the flatter bump map); such a bump map stays retail. The
    receipt names every unfit span.
    """
    tx, inv, ResourceRecord, HEADER = _tools()
    try:
        if kind == "field":
            return modern_field_scene(span, outer_index=outer_index)
        if kind == "divots":
            return modern_divots_span(span)
        return modern_normal_span(span)
    except tx.TxtrError as exc:
        message = str(exc)
        if "cannot keep the retail scratch word" in message or "exceeds" in message or "needs more than" in message:
            # This retail stream leaves no room inside its wrapper: keep it. The
            # receipt and the pins record the site as unchanged (retail == applied).
            return bytes(span), dict(refit=False, unfit=message)
        raise


def _worker(args):
    """Refit one distinct field or detail_normal span (multiprocessing entry point)."""
    kind, outer, span_hex = args
    span = bytes.fromhex(span_hex)
    after, receipt = _refit_span(kind, span, outer)
    return sha(span), after.hex(), receipt


def _refit_fields(spans, *, progress, workers=None):
    """spans: {sha: (outer, span bytes)} -> {sha: (refit span, receipt)}."""
    say = progress or (lambda message, done, total: None)
    jobs = [(kind, outer, span.hex()) for kind, outer, span in spans.values()]
    count = workers or min(8, max(1, (os.cpu_count() or 2) - 1))
    results = {}
    say(f"Modern colour: refitting {len(jobs)} distinct field scenes, bump maps and divot layers", 0, len(jobs))
    if count > 1 and len(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=count) as pool:
            for index, (key, after_hex, receipt) in enumerate(pool.map(_worker, jobs, chunksize=2)):
                results[key] = (bytes.fromhex(after_hex), receipt)
                say(f"Modern colour: {index + 1} of {len(jobs)} field scenes refit", index + 1, len(jobs))
    else:
        for index, job in enumerate(jobs):
            key, after_hex, receipt = _worker(job)
            results[key] = (bytes.fromhex(after_hex), receipt)
            say(f"Modern colour: {index + 1} of {len(jobs)} field scenes refit", index + 1, len(jobs))
    return results


def apply_to_image(target, *, progress=None, workers=None):
    """Build-only: target must be the caller's disposable output image (or loose folder)."""
    pins = _pins()
    say = progress or (lambda message, done, total: None)
    todo, done, sources = [], [], {}
    with _outer_image()(target) as archive:
        for pin in pins["bundles"]:
            state = _bundle_state(archive, pin)
            require(state in ("retail", "applied"), f"{pin['name']}: {state} bundle; rebuild from a supported base")
            (done if state == "applied" else todo).append(pin)
        for pin in todo:
            entry = archive.entries[pin["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            require(sha(data) == pin["retail_sha256"], f"{pin['name']}: bundle bytes differ from the retail pin")
            sources[pin["name"]] = data
    spans = {}
    for pin in todo:
        for kind, at, size in bundle_plan(sources[pin["name"]]):
            if kind in ("field", "normal", "divots"):
                span = sources[pin["name"]][at:at + size]
                spans.setdefault(sha(span), (kind, pin["outer"], span))
    field_cache = _refit_fields(spans, progress=say, workers=workers) if spans else {}
    receipt = dict(label=LABEL, runtime_witnessed=False, bundles=len(pins["bundles"]), already_applied=len(done),
                   rewritten=0, distinct_field_refits=len(field_cache), edits={})
    if todo:
        with _outer_image()(target, writable=True) as archive:
            for index, pin in enumerate(todo):
                after, edits = modern_bundle(sources[pin["name"]], outer_index=pin["outer"], field_cache=field_cache)
                require(sha(after) == pin["applied_sha256"], f"{pin['name']}: transform does not reproduce the applied pin")
                entry = archive.entries[pin["outer"]]
                require(sha(archive.read(entry.virtual_offset, entry.size)) == pin["retail_sha256"], f"{pin['name']}: changed after preflight")
                for site, edit in zip(pin["sites"], edits):
                    at = entry.virtual_offset + site["offset"]
                    chunk = after[site["offset"]:site["offset"] + site["size"]]
                    require(archive.write(at, chunk) == len(chunk), f"{pin['name']}: short write")
                    require(archive.read(at, len(chunk)) == chunk, f"{pin['name']}: read-back differs")
                receipt["rewritten"] += 1
                receipt["edits"][pin["name"]] = [dict(kind=e["kind"], offset=e["offset"], size=e["size"]) for e in edits]
                if index % 40 == 0:
                    say(f"Modern colour: writing stadium bundles ({index + 1} of {len(todo)})", index + 1, len(todo))
    require(image_status(target) == "applied", "modern colour bundles failed their read-back")
    return receipt


def _game_folder(source):
    source = Path(source)
    if source.name == "0" and source.parent.name == "vc_53450030":
        return source.parent.parent
    if source.name == "vc_53450030":
        return source.parent
    return source


def build_pins(source, *, progress=None, workers=None):
    """Developer step: compute retail/applied pins from the pinned retail extraction."""
    import json as _json
    audit = ROOT / "reports" / "b69_j4" / "weather_audit.json"
    require(audit.is_file(), "reports/b69_j4/weather_audit.json (bundle inventory) is missing")
    inventory = _json.loads(audit.read_text(encoding="utf-8"))["assets"]["bundles"]
    folder = _game_folder(source)
    packs = folder / "vc_53450030" if (folder / "vc_53450030").is_dir() else folder
    say = progress or (lambda message, done, total: None)
    sources, meta = {}, {}
    with _outer_image()(packs) as archive:
        for bundle in inventory:
            entry = archive.entries[bundle["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            sources[bundle["name"]] = data
            meta[bundle["name"]] = (entry.name_id, entry.size)
    spans = {}
    for bundle in inventory:
        for kind, at, size in bundle_plan(sources[bundle["name"]]):
            if kind in ("field", "normal", "divots"):
                span = sources[bundle["name"]][at:at + size]
                spans.setdefault(sha(span), (kind, bundle["outer"], span))
    field_cache = _refit_fields(spans, progress=say, workers=workers)
    rows = []
    for bundle in inventory:
        data = sources[bundle["name"]]
        after, edits = modern_bundle(data, outer_index=bundle["outer"], field_cache=field_cache)
        name_id, size = meta[bundle["name"]]
        rows.append(dict(name=bundle["name"], outer=bundle["outer"], name_id=name_id, size=size,
                         retail_sha256=sha(data), applied_sha256=sha(after),
                         sites=[dict(kind=e["kind"], offset=e["offset"], size=e["size"], retail=e["before_sha256"], applied=e["after_sha256"]) for e in edits]))
    tables = []
    xbe = folder / "default.xbe"
    if xbe.is_file():
        image = XbeImage(xbe.read_bytes())
        for name, va, digest in LIGHT_TABLES:
            retail = image.read(va, TABLE_SIZE)
            require(sha(retail) == digest, f"retail light table {name} differs")
            tables.append(dict(name=name, va=hex(va), retail_hex=retail.hex(), applied_sha256=sha(modern_table(retail))))
    return dict(schema=PINS_SCHEMA, label=LABEL, hue_target=HUE_TARGET, hue_pull=HUE_PULL, sat_scale=SAT_SCALE,
                val_gamma=VAL_GAMMA, normal_flatten=NORMAL_FLATTEN, tints={hex(k): hex(v) for k, v in TINTS.items()},
                light_tables=tables, bundles=rows)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Modern colour and lighting for ESPN NFL 2K5 (experimental).")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="report the light rigs and stadium bundles of a source")
    s.add_argument("source", help="extracted game folder, vc_53450030/0 index, or disc image")
    a = sub.add_parser("apply", help="apply to a DISPOSABLE output image copy (never the retail source)")
    a.add_argument("image")
    a.add_argument("--workers", type=int, default=None)
    p = sub.add_parser("pins", help="developer: rebuild data/nfl2k5_modern_color_pins.json from the retail extraction")
    p.add_argument("source")
    p.add_argument("--write", action="store_true")
    p.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            folder = _game_folder(args.source)
            xbe = folder / "default.xbe" if folder.is_dir() else None
            packs = folder / "vc_53450030" if folder.is_dir() and (folder / "vc_53450030").is_dir() else Path(args.source)
            print(json.dumps(dict(light_rigs=(xbe_status(xbe.read_bytes()) if xbe and xbe.is_file() else "n/a"),
                                  bundles=image_status(packs)), indent=1))
        elif args.command == "apply":
            receipt = apply_to_image(args.image, progress=lambda m, d, t: print(m, flush=True), workers=args.workers)
            print(json.dumps({k: v for k, v in receipt.items() if k != "edits"}, indent=1))
        else:
            pins = build_pins(args.source, progress=lambda m, d, t: print(m, flush=True) if d % 25 == 0 else None, workers=args.workers)
            text = json.dumps(pins, indent=0, sort_keys=True) + "\n"
            if args.write:
                PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
                print("wrote", PINS_PATH, len(pins["bundles"]), "bundles")
            else:
                print(len(pins["bundles"]), "bundles;", len(pins["light_tables"]), "tables")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Modern colour: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
