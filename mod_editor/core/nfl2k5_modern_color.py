"""Configurable broadcast colour and lighting for ESPN NFL 2K5.

The C4 field and light rigs are preserved; linked outside grass follows their predicted colour. Custom looks are EXPERIMENTAL /
UNWITNESSED; the swatch model is a calibrated estimate, not an in-game render.

Two families of data edits, no executable code, no cave, no hook, no runtime
allocation:

1. Executable light rigs. ``FUN_000641c0`` selects one of seven 0x120-byte
   light tables in ``.rdata`` by indoor / rain / snow / day / afternoon / night
   and ``FUN_000f2360`` installs it: an ambient colour and intensity, then two
   or three directional lights (colour, direction, intensity). Retail day light
   is yellow (1.0, 1.0, 0.722), the afternoon rig is orange and every ambient is
   dim; blue collapses on grass and white uniforms go warm. The broadcast rigs
   use warm daylight keys with cool sky fill and neutral white at night.
   Directions and light counts stay retail. Day/afternoon shadow strength at
   +0x100 follows their colour recipe; the other five tables keep retail shadows.

2. Stadium bundles (``sNN{d,a,n}{d,r,s}.iff``, 477 archive outers). Per bundle:
   the Fldd time-of-day tint word (uncompressed), the ``detail_normal`` grass
   bump palette flattened, and the ``field`` scene refit into the
   same fixed VC-LZ span with the grass colour-map and outside-grass palettes
   re-graded toward the measured broadcast turf and the afternoon vertex tint
   softened. Bundles without a colour-map texture re-grade their grass material
   colour words instead.

Targets come from 2026 Week 1 broadcast stills measured per game (see
docs/modern_color/ and FABLE_B70_COLOR_REPORT_2026-09-15.md). Proved offline by
byte receipts and decoder read-back; custom appearance in game is UNWITNESSED.
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
from copy import deepcopy
from functools import lru_cache

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_modern_color"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Modern colour and lighting (experimental)"
HELP_TEXT = (
    "Enable the saved Colour & lighting controls below. Broadcast (default) tunes daylight and links outside grass to the field. "
    "Tune turf, linked end zones and outside grass, wear, bump detail, tints and seven existing light rigs. "
    "Each slider has an Off switch; values stay with the project. Directions, counts and retail wrappers stay unchanged. "
    "Day and afternoon colour balance also blends their shadow strength. Refits add build time; any span that cannot fit stays retail "
    "and is named in the receipt. Swatches are predicted means, and custom appearance is unwitnessed. "
    "Off in every preset. Use the original retail source to change or reset an already-built grade."
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
    "day": dict(ambient=(0.94, 0.96, 1.00), ambient_intensity=0.44, shadow=0.32,
                lights=(((1.00, 0.94, 0.88), 1.60), ((0.32, 0.40, 1.00), 0.99))),
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
    "afternoon": dict(ambient=(1.00, 0.96, 1.00), ambient_intensity=0.60, shadow=0.22,
                      lights=(((1.00, 0.91, 0.78), 1.20), ((0.40, 0.445, 1.00), 1.04), ((0.40, 0.445, 1.00), 1.04))),
}
# Day/afternoon desaturation is in the channel gains, not the shared grass map.
# Cool sky fill restores blue while the direct sun stays warm. C5 keeps every
# field map and all seven C4 rigs; only outside-grass bundle data changes.
# Day key/ambient = 3.64, afternoon = 2.0; +0x100 controls the negative
# shadow-light term read by 0x64000 -> 0x12fb8d -> 0x2af50. It is not a blur
# radius or a sun-angle control. Actual shadow shape remains game-dependent.
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
# their own green background and are re-graded too. C5 replaces the old outside
# brightness lift with a FIELD prediction match, including its separate vertex
# tints. The end-zone overlays still take the v2.1 softened tint.
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
# Outside grass has a different drawn response from the layered playing field.
# Calibration: C4 s08dd decoded outside mean below -> supplied day strip sample
# (101,151,76). Divide by that map's unrounded C4 field-model prediction. This
# is a surface-response estimate, not a shader proof. Applying this ratio to
# other rigs/classes is explicitly an extrapolation; do not alter FIELD factors.
OUTSIDE_REFERENCE_MAP = (175.833251953125, 218.8282470703125, 85.738525390625)
OUTSIDE_REFERENCE_SCREEN = (101, 151, 76)
OUTSIDE_RESPONSE = tuple(
    observed / (sample * (MODERN_RIGS["day"]["ambient"][c] * MODERN_RIGS["day"]["ambient_intensity"]
                          + sum(rgb[c] * power for rgb, power in MODERN_RIGS["day"]["lights"])) * SCREEN_FACTOR["day"][c])
    for c, (sample, observed) in enumerate(zip(OUTSIDE_REFERENCE_MAP, OUTSIDE_REFERENCE_SCREEN)))
OUTSIDE_FIELD_RATIO = .97
OUTSIDE_MIN_SHADE = 246  # neutral tint: at most 3.53% darker, including old coloured edge tints
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


# Project controls. The existing owner is the only writer; these are recipes,
# never preset edits. Disabled controls retain their authored value for re-use.
SETTINGS_SCHEMA = "nfl2k5_colour_lighting/v1"
RECEIPT_SCHEMA = "nfl2k5_colour_lighting_receipt/v1"
TRANSFORM_REVISION = "c5-field-linked-outside-v1"
RIG_LABELS = {"day": "Day", "afternoon": "Afternoon", "night_indoor": "Night / dome (shared)",
              "rain": "Rain", "snow": "Snow", "alt_day": "Alternate day", "alt_dynamic": "Alternate dynamic"}
GROUPS = {"turf": "Turf", "endzones": "End zones / centre logo", "outside": "Outside grass",
          "divots": "Blotches / wear", "normal": "Bump detail", "tints": "Time-of-day tints",
          **{"rig_" + name: label + " lights" for name, label in RIG_LABELS.items()}}


def read_rig(table):
    count = struct.unpack_from("<I", table, 0x14)[0]
    require(count in (2, 3), "Unsupported light count")
    return dict(shadow=struct.unpack_from("<f", table, 0x100)[0],
                ambient=struct.unpack_from("<3f", table),
                ambient_intensity=struct.unpack_from("<f", table, 0x10)[0],
                lights=tuple((struct.unpack_from("<3f", table, 0x20 + i * 0x40),
                              struct.unpack_from("<f", table, 0x40 + i * 0x40)[0]) for i in range(count)))


@lru_cache(maxsize=1)
def control_specs():
    """label, default, retail/off value, minimum, maximum, step for every slider."""
    specs = {}
    def add(group, key, label, default, retail, low, high, step):
        specs[group + "." + key] = dict(group=group, label=label, default=default,
                                        retail=retail, minimum=low, maximum=high, step=step)
    for group in ("turf", "endzones", "outside"):
        add(group, "hue_target", "Broadcast hue (degrees)", HUE_TARGET, HUE_TARGET, 45, 150, 1)
        add(group, "hue_pull", "Hue pull", HUE_PULL, 0, 0, 1, .01)
        add(group, "saturation", "Saturation", SAT_SCALE, 1, 0, 2, .01)
        add(group, "value_lift", "Brightness curve", VAL_GAMMA, 1, .25, 5, .01)
    add("turf", "map_contrast", "Map contrast / mowing stripes", 1, 1, 0, 2, .01)
    add("outside", "match", "Match field colour", 1, 0, 0, 1, .01)
    add("outside", "falloff", "Edge shade strength", OUTSIDE_VERTEX_FALLOFF, 1, 0, 1, .01)
    add("divots", "contrast", "Blotch / wear contrast", DIVOTS_ALPHA, 1, 0, 1, .01)
    add("normal", "flatten", "Bump flatten amount", round(1 - NORMAL_FLATTEN, 6), 0, 0, 1, .01)
    for key in ("day", "afternoon", "night"):
        add("tints", key, key.title() + " tint correction", 1, 0, 0, 2, .01)
    for name, rig in MODERN_RIGS.items():
        retail = read_rig(_retail_table(name))
        group = "rig_" + name
        add(group, "gain", "Overall gain", 1, 1, 0, 2, .01)
        add(group, "balance", "Light colour / shadow recipe" if "shadow" in rig else "White balance (retail to broadcast)", 1, 0, 0, 1, .01)
        add(group, "ambient", "Ambient strength", rig["ambient_intensity"], retail["ambient_intensity"], 0, 2, .01)
        add(group, "key", "Key light strength", rig["lights"][0][1], retail["lights"][0][1], 0, 2, .01)
        add(group, "fill", "Fill light strength", rig["lights"][1][1], retail["lights"][1][1], 0, 2, .01)
    return specs


def default_settings(*, retail=False):
    return dict(schema=SETTINGS_SCHEMA,
                values={k: s["retail" if retail else "default"] for k, s in control_specs().items()},
                disabled=list(control_specs()) if retail else [],
                enabled={group: not retail for group in GROUPS},
                linked={"endzones": True, "outside": True},
                preview_class="outdoor", preview_rig="night_indoor")


def normalize_settings(settings=None):
    base = default_settings()
    if settings is None or settings == {}:
        return base
    require(type(settings) is dict and set(settings) == set(base) and settings.get("schema") == SETTINGS_SCHEMA,
            "Colour & lighting settings are unsupported. Reset to Broadcast (default).")
    out = deepcopy(settings)
    require(type(out["values"]) is dict and set(out["values"]) == set(base["values"]), "Colour & lighting controls are incomplete")
    for key, spec in control_specs().items():
        value = out["values"][key]
        require(type(value) in (int, float) and math.isfinite(value) and spec["minimum"] <= value <= spec["maximum"],
                f"{GROUPS[spec['group']]}: {spec['label']} must be {spec['minimum']} to {spec['maximum']}")
        out["values"][key] = float(value)
    for key in ("enabled", "linked"):
        require(type(out[key]) is dict and set(out[key]) == set(base[key]) and all(type(v) is bool for v in out[key].values()),
                f"Colour & lighting {key} switches must be On or Off")
    require(type(out["disabled"]) is list and all(type(k) is str and k in control_specs() for k in out["disabled"])
            and len(out["disabled"]) == len(set(out["disabled"])), "Colour & lighting disabled controls are invalid")
    out["disabled"] = sorted(out["disabled"])
    require(type(out["preview_class"]) is str and type(out["preview_rig"]) is str
            and out["preview_class"] in ("outdoor", "dome", "material") and out["preview_rig"] in MODERN_RIGS,
            "Choose a supported stadium class and light condition")
    return out


def settings_id(settings=None):
    doc = normalize_settings(settings)
    doc = {k: v for k, v in doc.items() if not k.startswith("preview_")}
    # Do not reuse a C4 baked-grade receipt/cache for the new linked transform.
    doc["transform_revision"] = TRANSFORM_REVISION
    # All numeric inputs use a canonical representation (1 and 1.0 are equal).
    doc["values"] = {k: float(v) for k, v in doc["values"].items()}
    return sha(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def is_custom(settings=None):
    return settings_id(settings) != settings_id()


def control_value(settings, key):
    spec = control_specs()[key]
    return (spec["retail"] if key in settings["disabled"] or not settings["enabled"][spec["group"]]
            else settings["values"][key])


def surface_group(settings, surface):
    return "turf" if surface in settings["linked"] and settings["linked"][surface] else surface


def configured_rig(name, settings=None):
    doc = normalize_settings(settings)
    retail = read_rig(_retail_table(name))
    group = "rig_" + name
    if not doc["enabled"][group]:
        return retail
    modern = MODERN_RIGS[name]
    val = lambda key: control_value(doc, group + "." + key)
    blend = lambda a, b: tuple(x + (y - x) * val("balance") for x, y in zip(a, b))
    return dict(shadow=retail["shadow"] + (modern.get("shadow", retail["shadow"]) - retail["shadow"]) * val("balance"),
                ambient=blend(retail["ambient"], modern["ambient"]),
                ambient_intensity=val("ambient") * val("gain"),
                lights=tuple((blend(old[0], new[0]), val("key" if i == 0 else "fill") * val("gain"))
                             for i, (old, new) in enumerate(zip(retail["lights"], modern["lights"]))))


def corrected_tint(rgba, settings=None):
    doc = normalize_settings(settings)
    target = VERTEX_TINTS.get(tuple(rgba))
    if target is None:
        return tuple(rgba)
    bucket = "afternoon" if rgba[:3] == (255, 238, 205) else "night" if rgba[:3] == (242, 255, 255) else "day"
    amount = control_value(doc, "tints." + bucket)
    return tuple(min(255, max(0, round(a + (b - a) * amount))) for a, b in zip(rgba, target))


def corrected_tint_word(word, settings=None):
    if word not in TINTS:
        return word
    rgba = ((word >> 16) & 255, (word >> 8) & 255, word & 255, word >> 24)
    r, g, b, a = corrected_tint(rgba, settings)
    return (a << 24) | (r << 16) | (g << 8) | b


# --- executable light rigs ---------------------------------------------------

def modern_table(retail, settings=None):
    """Return the broadcast table for one retail 0x120-byte light table."""
    require(len(retail) == TABLE_SIZE, "light table size")
    name = next((n for n, _va, digest in LIGHT_TABLES if digest == sha(retail)), None)
    require(name is not None, "not a retail light table")
    doc = normalize_settings(settings)
    if not doc["enabled"]["rig_" + name]:
        return bytes(retail)
    rig = configured_rig(name, doc)
    count = struct.unpack_from("<I", retail, 0x14)[0]
    require(count == len(rig["lights"]), f"{name}: light count {count} differs from the rig")
    out = bytearray(retail)
    struct.pack_into("<3f", out, 0, *rig["ambient"])
    struct.pack_into("<f", out, 0x10, rig["ambient_intensity"])
    struct.pack_into("<f", out, 0x100, rig["shadow"])
    for index, (colour, intensity) in enumerate(rig["lights"]):
        base = 0x20 + index * 0x40
        struct.pack_into("<3f", out, base, *colour)
        struct.pack_into("<f", out, base + 0x20, intensity)
    return bytes(out)


def _table_states(image, settings=None):
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
        elif retail is not None and settings is not None and have == modern_table(retail, settings):
            states.append("applied (custom)")
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


def xbe_status(payload, settings=None):
    try:
        image = XbeImage(payload)
        states = _table_states(image, settings)
        if settings is not None and is_custom(settings) and all(
                image.read(va, TABLE_SIZE) == modern_table(_retail_table(name), settings) for name, va, _ in LIGHT_TABLES):
            return "applied (custom)"
    except (ValueError, TypeError, IndexError, struct.error):
        return "foreign"
    if all(s == "retail" for s in states):
        return "retail"
    if all(s == "applied" for s in states):
        return "applied"
    return "foreign"


status = xbe_status


def verify(payload, *, enabled=True, settings=None):
    require(type(enabled) is bool, "Modern colour and lighting must be Off or On")
    settings = normalize_settings(settings)
    state = xbe_status(payload, settings if enabled else None)
    expected = ("applied (custom)" if is_custom(settings) else "applied") if enabled else "retail"
    require(state == expected, "Light rigs do not match the requested option")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False,
                schema=RECEIPT_SCHEMA, settings=settings, settings_sha256=settings_id(settings),
                tables=[dict(name=n, va=hex(va)) for n, va, _ in LIGHT_TABLES])


def apply(payload, *, enabled=True, settings=None, previous_settings=None):
    """Executable part only. Returns (patched bytes, receipt)."""
    require(type(enabled) is bool, "Modern colour and lighting must be Off or On")
    image = XbeImage(payload)
    settings = normalize_settings(settings)
    states = _table_states(image, previous_settings if previous_settings is not None else settings)
    require("foreign" not in states, "Foreign light tables; rebuild from a supported base")
    result = bytearray(payload)
    edits = []
    for (name, va, digest), state in zip(LIGHT_TABLES, states):
        retail = image.read(va, TABLE_SIZE) if state == "retail" else _retail_table(name)
        require(retail is not None, "retail light table unavailable for restore")
        after = modern_table(retail, settings) if enabled else retail
        at = image.offset(va, TABLE_SIZE)
        if bytes(result[at:at + TABLE_SIZE]) != after:
            result[at:at + TABLE_SIZE] = after
            edits.append(dict(label=name, va=hex(va), size=TABLE_SIZE))
    section = image.section(LIGHT_TABLES[0][1])
    for s in _sections(result):
        if s.header_offset == section.header:
            result[s.header_offset + 36:s.header_offset + 56] = section_digest(result, s)
    result = bytes(result)
    return result, dict(verify(result, enabled=enabled, settings=settings),
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


def regrade_palette(palette, *, gain=1.0, alpha_scale=1.0, settings=None, surface="turf", mean_value=None):
    """Re-grade the green entries of a 256-entry B,G,R,A palette; others untouched.

    ``gain`` multiplies the lifted value; ``alpha_scale`` scales every entry's
    alpha (the divots layer). Linked outside matching is a separate transform.
    """
    require(len(palette) == 1024, "palette size")
    doc = normalize_settings(settings)
    group = surface_group(doc, surface)
    val = lambda key: (control_value(doc, group + "." + key) if doc["enabled"][surface]
                       else control_specs()[group + "." + key]["retail"])
    contrast = control_value(doc, "turf.map_contrast") if surface == "turf" else 1.0
    out = bytearray(palette)
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h *= 360
        new_a = min(255, max(0, round(a * alpha_scale)))
        if not (45 <= h <= (180 if surface == "outside" else 150) and s > 0.15 and v > 0.10):
            if new_a != a:
                out[i * 4 + 3] = new_a
            continue
        h = (h + (val("hue_target") - h) * val("hue_pull")) / 360
        s = min(1.0, s * val("saturation"))
        if mean_value is not None and contrast != 1.0:
            v = min(1.0, max(0.0, mean_value + (v - mean_value) * contrast))
        v = min(1.0, lift_value(v, val("value_lift")) * gain)
        r2, g2, b2 = (min(255, max(0, round(c * 255))) for c in colorsys.hsv_to_rgb(h, s, v))
        out[i * 4:i * 4 + 4] = bytes((b2, g2, r2, new_a))
    return bytes(out)


def _palette_counts(out, system, texture):
    tx, inv, ResourceRecord, HEADER = _tools()
    width, height = texture["width"], texture["height"]
    at = system + texture["pixel_offset"]
    indices = tx.unswizzle_2d(out[at:at + width * height], width, height, 1)
    counts = [0] * 256
    for index in indices:
        counts[index] += 1
    return counts


def _green_entry(entry, *, hue_max=150):
    b, g, r, a = entry
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return 45 <= h * 360 <= hue_max and s > .15 and v > .10


def _palette_mean(palette, counts, *, mask=None, hue_max=150):
    # Select greens using the source palette, even when custom controls make
    # the result grey. Non-green paint and unused entries cannot bias the mean.
    mask = palette if mask is None else mask
    used = [(i, count) for i, count in enumerate(counts)
            if count and _green_entry(mask[i*4:i*4+4], hue_max=hue_max)]
    total = sum(count for i, count in used)
    if not total:
        return None
    return tuple(sum(palette[i*4+c] * count for i, count in used) / total for c in (2, 1, 0))


def _green_mean_value(out, system, texture, palette):
    """Mean HSV value of used green entries (the original field contrast input)."""
    counts = _palette_counts(out, system, texture)
    used = [(i, count) for i, count in enumerate(counts)
            if count and _green_entry(palette[i*4:i*4+4])]
    total = sum(count for i, count in used)
    return sum(max(palette[i*4:i*4+3]) * count for i, count in used) / (255 * total) if total else None


def outside_link_amount(settings):
    return control_value(settings, "outside.match") if settings["linked"]["outside"] else 0.0


def match_outside_palette(palette, field_rgb, counts, settings=None, *, mask=None):
    """Match the FIELD prediction under every rig through the surface response.

    Rig gain and FIELD screen factors cancel from the inverse: outside map =
    field map / OUTSIDE_RESPONSE. Keep the texture's value variation, use field
    chroma, and leave 3% brightness and 8% saturation headroom for byte rounding.
    Only the linked match control opts in; unlinked custom colour remains free.
    """
    doc = normalize_settings(settings)
    amount = outside_link_amount(doc)
    mask = palette if mask is None else mask
    mean = _palette_mean(palette, counts, mask=mask, hue_max=180)
    if not amount or mean is None or field_rgb is None:
        return palette
    peak = max(field_rgb)
    target = tuple(OUTSIDE_FIELD_RATIO * (v + (peak-v) * .08) / response
                   for v, response in zip(field_rgb, OUTSIDE_RESPONSE))
    value_mean = sum(max(palette[i*4:i*4+3]) * count for i, count in enumerate(counts)
                     if _green_entry(mask[i*4:i*4+4], hue_max=180))
    total = sum(count for i, count in enumerate(counts) if _green_entry(mask[i*4:i*4+4], hue_max=180))
    value_mean /= total
    if not value_mean:
        return palette
    result = bytearray(palette)
    for i in range(256):
        entry = palette[i*4:i*4+4]
        if not _green_entry(mask[i*4:i*4+4], hue_max=180):
            continue
        detail = max(entry[:3]) / value_mean
        for c, channel in enumerate((2, 1, 0)):
            value = entry[channel] + (target[c] * detail - entry[channel]) * amount
            result[i*4+channel] = min(255, max(0, round(value)))
    return bytes(result)


def linked_outside_tint(rgba, settings=None):
    """Remove separate colour casts and bound edge shade for a linked surface."""
    doc = normalize_settings(settings)
    amount = outside_link_amount(doc)
    r, g, b, a = rgba
    shade = max(OUTSIDE_MIN_SHADE, 255 - round((255-max(r, g, b)) * control_value(doc, "outside.falloff")))
    return tuple(round(v + (shade-v) * amount) for v in (r, g, b)) + (a,)


def lift_value(v, gamma=VAL_GAMMA):
    """The beta 71 brightness curve: 1 - (1 - v)^VAL_GAMMA, monotone, never clips."""
    return 1.0 - (1.0 - v) ** gamma


def predicted_on_screen(colour_map_rgb, rig="night_indoor", *, settings=None, table=None, surface="turf", tint=(255, 255, 255), rounded=True):
    """Calibrated estimate of the drawn turf for a colour-map mean under a rig.

    flat = map x (ambient x intensity + sum of light colour x intensity) per channel;
    on screen = flat x SCREEN_FACTOR (the measured ratio, see the constants above).
    Outside uses the separately calibrated surface response and optional vertex
    tint. rounded=False exposes float predictions for value/saturation bounds.
    """
    table = table if table is not None else configured_rig(rig, settings)
    factor = SCREEN_FACTOR.get(rig, SCREEN_FACTOR["night_indoor"])
    out = []
    for c in range(3):
        gain = table["ambient"][c] * table["ambient_intensity"] + sum(col[c] * i for col, i in table["lights"])
        value = colour_map_rgb[c] * gain * factor[c] * tint[c] / 255
        if surface == "outside":
            value *= OUTSIDE_RESPONSE[c]
        out.append(min(255, round(value) if rounded else value))
    return tuple(out)


# Safe numeric reference measurements, not texture data. Each class names its
# representative; other conditions are extrapolations of the two calibrations.
PREVIEW_CLASSES = {
    "outdoor": dict(label="Outdoor grass (Arrowhead reference)", rgb=(100, 125, 66), map=True,
                    target=(107, 121, 53), source="s13nd.iff colour-map median"),
    "dome": dict(label="Dome grass (Indianapolis reference)", rgb=(52, 90, 61), map=True,
                 target=(102, 125, 78), source="s11dd.iff used colour-map mean, rounded"),
    "material": dict(label="Material turf (Detroit reference)", rgb=(64, 96, 51), map=False,
                     target=(63, 85, 58), source="s09dd.iff color_premipped material +0x18"),
}


def preview(settings=None, *, surface="turf"):
    doc = normalize_settings(settings)
    reference = PREVIEW_CLASSES[doc["preview_class"]]
    r, g, b = reference["rgb"]
    entry = regrade_palette(bytes((b, g, r, 255)) * 256, settings=doc)[:4]
    rgb = (entry[2], entry[1], entry[0])
    targets = {"day": (88, 105, 61), "afternoon": (98, 119, 72)}
    target = targets.get(doc["preview_rig"], reference["target"]) if doc["preview_class"] == "outdoor" else reference["target"]
    field_prediction = predicted_on_screen(rgb, doc["preview_rig"], settings=doc)
    if surface == "outside":
        # Same numeric class reference for the custom swatch; actual builds use
        # the stadium's own outside texture and decoded field mean.
        palette = regrade_palette(bytes((b, g, r, 255)) * 256, settings=doc, surface="outside")
        palette = match_outside_palette(palette, rgb, [1] * 256, doc, mask=bytes((b, g, r, 255)) * 256)
        rgb = (palette[2], palette[1], palette[0])
        target = field_prediction
    return dict(predicted=predicted_on_screen(rgb, doc["preview_rig"], settings=doc, surface=surface), target=target,
                colour_map=rgb, source=reference["source"], map=reference["map"],
                scope="PREDICTED mean only: map × light rig × calibrated screen factor. "
                      "Wear, bump detail and stripe contrast are outside this model. Outside swatches use the unshaded mean; "
                      "builds also bound linked outside tints. Outside response is calibrated from one day strip; "
                      "FIELD is calibrated for outdoor day/night; other classes and conditions, and outside response beyond its day reference, are extrapolated.")


def looks_like_normal_palette(palette):
    blues = sorted(palette[i * 4] for i in range(256))
    return blues[128] > 180


def flatten_normal_palette(palette, settings=None):
    """Pull tangent-space normals toward flat by NORMAL_FLATTEN; z is recomputed."""
    require(len(palette) == 1024, "palette size")
    doc = normalize_settings(settings)
    amount = control_value(doc, "normal.flatten")
    if amount == 0:
        return bytes(palette)
    residual = NORMAL_FLATTEN if amount == control_specs()["normal.flatten"]["default"] else 1 - amount
    if not looks_like_normal_palette(palette):
        return bytes(palette)
    out = bytearray(palette)
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        x, y = (r / 127.5 - 1.0) * residual, (g / 127.5 - 1.0) * residual
        z = math.sqrt(max(0.0, 1.0 - x * x - y * y))
        enc = lambda c: min(255, max(0, round((c + 1.0) * 127.5)))
        out[i * 4:i * 4 + 4] = bytes((enc(z), enc(y), enc(x), a))
    return bytes(out)


def regrade_colour_word(word, settings=None):
    """ARGB material colour: re-grade greens like a palette entry, keep alpha."""
    a, r, g, b = (word >> 24) & 255, (word >> 16) & 255, (word >> 8) & 255, word & 255
    entry = regrade_palette(bytes((b, g, r, a)) * 256, settings=settings)[:4]
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


def modern_field_scene(span, *, outer_index=0, settings=None):
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
    doc = normalize_settings(settings)
    receipt = dict(palettes=[], materials=[], vertex_tints=0)
    by_material = {}
    for texture in rec["embedded_textures"]:
        for name in texture.get("mapped_material_names") or ():
            by_material[name] = texture
    field_rgb = None
    outside_linked = False
    # Material-only fields need their target before processing the outside map.
    if COLOR_MAP_MATERIAL not in by_material:
        for material in rec["materials"]:
            if material["name"] != COLOR_MAP_MATERIAL or material.get("texture_index") is not None:
                continue
            base = material["record_offset"]
            for field in (0x14, 0x18):
                word = struct.unpack_from("<I", out, base + field)[0]
                new = regrade_colour_word(word, doc)
                if field == 0x18:
                    field_rgb = ((new >> 16) & 255, (new >> 8) & 255, new & 255)
                if new != word:
                    struct.pack_into("<I", out, base + field, new)
                    receipt["materials"].append(dict(material=material["name"], field=hex(field), before=hex(word), after=hex(new)))
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
        surface = "turf" if name == COLOR_MAP_MATERIAL else "outside" if name == OUTSIDE_MATERIAL else "endzones"
        mean = _green_mean_value(out, system, texture, before)
        graded = regrade_palette(before, settings=doc, surface=surface, mean_value=mean)
        counts = _palette_counts(out, system, texture)
        if name == COLOR_MAP_MATERIAL:
            # Measure blue-green fields too, without changing their C4 grading mask.
            field_rgb = _palette_mean(graded, counts, mask=before, hue_max=180)
        after = match_outside_palette(graded, field_rgb, counts, doc, mask=before) if name == OUTSIDE_MATERIAL else graded
        out[at:at + 1024] = after
        receipt["palettes"].append(dict(material=name, offset=at, changed=sum(a != b for a, b in zip(before, after))))
        if name == OUTSIDE_MATERIAL:
            outside_mean = _palette_mean(graded, counts, mask=before, hue_max=180)
            outside_linked = bool(field_rgb is not None and outside_mean and max(outside_mean) and outside_link_amount(doc))
            receipt["outside"] = dict(link_amount=outside_link_amount(doc) if outside_linked else 0, field_rgb=list(field_rgb) if field_rgb is not None else None,
                                      before_rgb=list(_palette_mean(graded, counts, mask=before, hue_max=180) or ()),
                                      after_rgb=list(_palette_mean(after, counts, mask=before, hue_max=180) or ()))
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
            new = corrected_tint((r, g, b, a), doc) if (r, g, b, a) in VERTEX_TINTS else None
            if new is None and shape["name"] == "Outside_grass" and r == g == b and r < 255 and a == 255:
                # The outside grass darkens toward the edges through grey vertex colours; keep less of the falloff.
                lifted = 255 - round((255 - r) * control_value(doc, "outside.falloff"))
                new = (lifted, lifted, lifted, 255)
            if shape["name"] == "Outside_grass" and outside_linked:
                new = linked_outside_tint((r, g, b, a), doc)
            if new is not None and new != (r, g, b, a):
                out[at:at + 4] = bytes((new[2], new[1], new[0], new[3]))
                receipt["vertex_tints"] += 1
    if bytes(out) == output:
        return bytes(span), dict(receipt, refit=False)
    rebuilt, info = fit_fixed_span(span, bytes(out))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(out), "refit read-back differs")
    return rebuilt, dict(receipt, refit=True, **info)


def modern_normal_span(span, settings=None):
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
    edited[at:at + 1024] = flatten_normal_palette(bytes(output[at:at + 1024]), settings)
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


def modern_divots_span(span, settings=None):
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
    doc = normalize_settings(settings)
    if not doc["enabled"]["divots"]:
        return bytes(span), dict(refit=False)
    edited[at:at + 1024] = regrade_palette(bytes(output[at:at + 1024]), alpha_scale=control_value(doc, "divots.contrast"), settings=doc)
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
    """Locate the fixed edit sites of one bundle: (kind, offset, size, before, after)."""
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


def modern_bundle(data, *, outer_index=0, field_cache=None, settings=None):
    """Return the modern bundle bytes and the edit list for one retail bundle.

    ``field_cache`` maps a field span SHA-256 to its refit span so identical
    field scenes shared by several bundles are refit once.
    """
    settings = normalize_settings(settings)
    out = bytearray(data)
    edits = []
    for kind, at, size in bundle_plan(data):
        before = bytes(data[at:at + size])
        if kind in ("field", "normal", "divots"):
            key = (settings_id(settings), kind, sha(before))
            if field_cache is not None and key in field_cache:
                after, receipt = field_cache[key]
            else:
                after, receipt = _refit_span(kind, before, outer_index, settings)
                if field_cache is not None:
                    field_cache[key] = (after, receipt)
        else:
            word = struct.unpack("<I", before)[0]
            after, receipt = struct.pack("<I", corrected_tint_word(word, settings)), {}
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


def receipt_path(source):
    return Path(str(source) + ".colour-lighting.json")


def read_image_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    require(path.stat().st_size <= 4 * 1024 * 1024, "Colour & lighting receipt is too large")
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(type(doc) is dict and doc.get("schema") == RECEIPT_SCHEMA, "Unsupported colour & lighting receipt")
    require(type(doc.get("settings")) is dict and doc.get("settings_sha256") == settings_id(doc["settings"]),
            "Colour & lighting receipt uses a different recipe or settings. Choose the original retail source.")
    return doc


def _receipt_bundle_state(archive, pin, receipt):
    rows = receipt.get("bundle_pins", {})
    require(type(rows) is dict, "Colour & lighting receipt bundle pins are invalid")
    row = rows.get(pin["name"], {})
    require(type(row) is dict and row.get("retail_sha256") == pin["retail_sha256"] and row.get("size") == pin["size"]
            and row.get("outer") == pin["outer"], f"{pin['name']}: custom receipt scope differs")
    entry = archive.entries[pin["outer"]]
    require(entry.name_id == pin["name_id"] and entry.size == pin["size"], f"{pin['name']}: archive entry differs")
    data = archive.read(entry.virtual_offset, entry.size)
    if sha(data) != row.get("applied_sha256"):
        return "foreign"
    sites = row.get("sites", [])
    require(type(sites) is list and len(sites) == len(pin["sites"]), f"{pin['name']}: custom receipt sites differ")
    for site, original in zip(sites, pin["sites"]):
        require(type(site) is dict and all(site.get(k) == original[k] for k in ("kind", "offset", "size", "retail")),
                f"{pin['name']}: custom receipt escaped its pinned span")
        if sha(data[site["offset"]:site["offset"] + site["size"]]) != site.get("applied"):
            return "foreign"
    return "applied (custom)" if is_custom(receipt["settings"]) else "applied"


_AUTO_RECEIPT = object()


def image_status(source, *, receipt=_AUTO_RECEIPT):
    """Recognize custom bytes only with their own settings and per-bundle receipt."""
    pins = _pins()
    receipt = read_image_receipt(source) if receipt is _AUTO_RECEIPT else receipt
    if receipt is not None:
        require(type(receipt) is dict and receipt.get("schema") == RECEIPT_SCHEMA and type(receipt.get("settings")) is dict
                and receipt.get("settings_sha256") == settings_id(receipt["settings"]),
                "Colour & lighting receipt uses a different recipe or settings. Choose the original retail source.")
        require(type(receipt.get("bundle_pins")) is dict and set(receipt["bundle_pins"]) == {p["name"] for p in pins["bundles"]},
                "Colour & lighting receipt does not cover every bundle")
    with _outer_image()(source) as archive:
        states = {(_receipt_bundle_state(archive, pin, receipt) if receipt is not None else _bundle_state(archive, pin))
                  for pin in pins["bundles"]}
    if len(states) == 1:
        return states.pop()
    return "foreign" if "foreign" in states else "mixed"


def check_image_request(source, settings=None, *, receipt=_AUTO_RECEIPT):
    """Check before copying a build. Regrading always starts at pinned retail bytes."""
    receipt = read_image_receipt(source) if receipt is _AUTO_RECEIPT else receipt
    state = image_status(source, receipt=receipt)
    if receipt is not None:
        require(state in ("applied", "applied (custom)"), "The colour & lighting receipt does not match this disc. Choose the original retail source.")
        require(settings_id(settings) == receipt["settings_sha256"],
                "This disc already has a colour grade. Choose the original retail disc as the source to change or reset it.")
    else:
        require(state in ("retail", "applied"), "The stadium bundles are not recognized. Choose a supported retail source.")
        require(state == "retail" or not is_custom(settings),
                "This disc already has the Broadcast grade. Choose the original retail disc as the source to change or reset it.")
    return state


def _save_image_receipt(target, receipt):
    import tempfile
    path = receipt_path(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write((json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _refit_span(kind, span, outer_index, settings=None):
    """Spans that cannot be refit inside their retail wrapper keep their retail bytes.

    A handful of retail streams leave no room. Such a field scene keeps its retail
    colour map (the stadium still gets the light rigs, the tint and, when its own
    bump span fits, the flatter bump map); such a bump map stays retail. The
    receipt names every unfit span.
    """
    tx, inv, ResourceRecord, HEADER = _tools()
    try:
        if kind == "field":
            return modern_field_scene(span, outer_index=outer_index, settings=settings)
        if kind == "divots":
            return modern_divots_span(span, settings)
        return modern_normal_span(span, settings)
    except tx.TxtrError as exc:
        message = str(exc)
        if "cannot keep the retail scratch word" in message or "exceeds" in message or "needs more than" in message:
            # This retail stream leaves no room inside its wrapper: keep it. The
            # receipt and the pins record the site as unchanged (retail == applied).
            return bytes(span), dict(refit=False, unfit=message)
        raise


def _worker(args):
    """Refit one distinct field or detail_normal span (multiprocessing entry point)."""
    kind, outer, span_hex, settings = args
    span = bytes.fromhex(span_hex)
    after, receipt = _refit_span(kind, span, outer, settings)
    return (settings_id(settings), kind, sha(span)), after.hex(), receipt


def _refit_fields(spans, *, progress, workers=None, settings=None):
    """spans: {sha: (outer, span bytes)} -> {sha: (refit span, receipt)}."""
    say = progress or (lambda message, done, total: None)
    jobs = [(kind, outer, span.hex(), settings) for kind, outer, span in spans.values()]
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


def apply_to_image(target, *, progress=None, workers=None, settings=None, source_receipt=_AUTO_RECEIPT):
    """Build-only: disposable output, fixed spans, reparsed read-back and sidecar receipt."""
    settings = normalize_settings(settings)
    pins = _pins()
    say = progress or (lambda message, done, total: None)
    previous = read_image_receipt(target) if source_receipt is _AUTO_RECEIPT else source_receipt
    state = check_image_request(target, settings, receipt=previous)
    if previous is not None:
        replay = dict(previous, already_applied=len(pins["bundles"]), rewritten=0)
        _save_image_receipt(target, replay)
        return replay
    todo, done, sources = [], [], {}
    with _outer_image()(target) as archive:
        for pin in pins["bundles"]:
            entry = archive.entries[pin["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            if sha(data) == pin["retail_sha256"]:
                todo.append(pin)
                sources[pin["name"]] = data
            else:
                require(not is_custom(settings) and sha(data) == pin["applied_sha256"],
                        f"{pin['name']}: bundle differs from its whole-bundle pin")
                done.append(pin)
    spans = {}
    for pin in todo:
        for kind, at, size in bundle_plan(sources[pin["name"]]):
            if kind in ("field", "normal", "divots"):
                span = sources[pin["name"]][at:at + size]
                spans.setdefault((kind, sha(span)), (kind, pin["outer"], span))
    field_cache = _refit_fields(spans, progress=say, workers=workers, settings=settings) if spans else {}
    receipt = dict(schema=RECEIPT_SCHEMA, settings=settings, settings_sha256=settings_id(settings),
                   state="applied (custom)" if is_custom(settings) else "applied",
                   label=LABEL, runtime_witnessed=False, bundles=len(pins["bundles"]), already_applied=len(done),
                   rewritten=0, distinct_field_refits=len(field_cache), edits={}, bundle_pins={})
    for pin in done:
        receipt["bundle_pins"][pin["name"]] = deepcopy(pin)
    # All refits above finish before opening the output for writes. Unfit spans
    # keep retail bytes and carry an explicit reason in the receipt.
    if todo:
        with _outer_image()(target, writable=True) as archive:
            for index, pin in enumerate(todo):
                after, edits = modern_bundle(sources[pin["name"]], outer_index=pin["outer"], field_cache=field_cache, settings=settings)
                require(len(after) == pin["size"], f"{pin['name']}: bundle changed size")
                if not is_custom(settings):
                    require(sha(after) == pin["applied_sha256"], f"{pin['name']}: transform does not reproduce the applied pin")
                entry = archive.entries[pin["outer"]]
                require(sha(archive.read(entry.virtual_offset, entry.size)) == pin["retail_sha256"], f"{pin['name']}: changed after preflight")
                require(len(edits) == len(pin["sites"]), f"{pin['name']}: site count differs")
                for site, edit in zip(pin["sites"], edits):
                    require(all(edit[k] == site[k] for k in ("kind", "offset", "size")), f"{pin['name']}: site moved")
                    at = entry.virtual_offset + site["offset"]
                    chunk = after[site["offset"]:site["offset"] + site["size"]]
                    before = sources[pin["name"]][site["offset"]:site["offset"] + site["size"]]
                    if site["kind"] != "tint":
                        require(chunk[:32] == before[:32], f"{pin['name']}: retail wrapper changed")
                    require(archive.write(at, chunk) == len(chunk), f"{pin['name']}: short write")
                    require(archive.read(at, len(chunk)) == chunk, f"{pin['name']}: read-back differs")
                receipt["rewritten"] += 1
                receipt["edits"][pin["name"]] = edits
                receipt["bundle_pins"][pin["name"]] = dict(pin, applied_sha256=sha(after), sites=[
                    dict(kind=e["kind"], offset=e["offset"], size=e["size"], retail=e["before_sha256"], applied=e["after_sha256"]) for e in edits])
                if index % 40 == 0:
                    say(f"Colour & lighting: writing stadium bundles ({index + 1} of {len(todo)})", index + 1, len(todo))
    require(image_status(target, receipt=receipt) == receipt["state"], "Colour & lighting bundles failed their read-back")
    _save_image_receipt(target, receipt)
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
