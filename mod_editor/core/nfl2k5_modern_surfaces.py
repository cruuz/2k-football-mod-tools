"""Modern playing surfaces for ESPN NFL 2K5 (experimental): today's synthetic turf and natural grass.

The retail field is either flat AstroTurf-style carpet or dull grass. This option gives every team's 2026 home venue
the surface it really has (``data/nfl2k5_modern_surfaces/venues.json``, cited per venue):

* **synthetic turf** (FieldTurf CORE, Hellas Matrix Helix and the like): the saturated, even green of today's fields
  on broadcasts, with the factory two-tone 5-yard bands, and a ``detail_normal`` of lying fibres in groomed patches
  with dark infill between them, so the turf reads as blades up close instead of sandpaper;
* **natural grass** (Bermuda, Kentucky bluegrass, hybrids): brighter and healthier than retail, mown in 5-yard
  stripes (or a checkerboard), with a fine-blade ``detail_normal``.

How the field is drawn (PROVED OFFLINE from the retail packs and the executable):

* ``color_premipped`` (128 x 64 P8, 4 mips) colours the playing field. Grass venues lay it on a 1,499-vertex grid,
  tiled at 5 cm per texel at 45 degrees and mirrored per 2.29 m cell; turf venues on one quad from goal line to
  goal line. Neither can hold field-aligned stripes, so this option rewrites the colour submesh's UVs as one planar
  mapping (one period = 10 yards along and 10 yards across, 7 cm per texel along) inside the shape's own UV
  constant (shape +0x30: scale and offset of the NORMSHORT2 UVs) and re-encodes the end-zone vertices of the same
  shape so their UVs do not move. Four venues (s02, s06, s09, s26) draw the field from a material colour with no
  texture: there the colour quad takes the outside-grass texture record (its material pointer), and the outside
  grass keeps a plain matching colour.
* ``detail_normal`` (512 x 256 P8, 6 mips, a RAW chunk of 175,872 bytes) is the layer the detail scene
  (``E_detail``) blends over the whole field at 1.27 cm per texel (``FUN_0009c160`` binds it with a specular map and
  the stadium shadow), each triangle mapping its own half of the texture (discontinuous UVs). What the game SHOWS of
  it is the palette alpha (PROVED IN GAME, 2026-09-27: the field's brightness follows the alpha almost in proportion,
  the retail map's visible grain goes with its alpha, and tf-v1's tilted normals under one alpha showed nothing even
  up close). tf-v3 therefore carries short blades or fibres in the alpha (one flat normal, alpha = the index), every
  mip level's mean on the alpha the colours were measured with (DETAIL_ALPHA) and the spread falling with distance;
  it is replaced in place (the two compressed chunks take three 64 x 64 tiles in TILE_GRID).
* ``divots`` (64 x 64 P8) is the wear decal the engine draws on grass-word venues; on synthetic venues its alpha is
  cleared (no divots in turf), on grass venues its greens follow the new grass. The Fldd dirt colour (word 1) becomes
  a dark worn-turf tone on synthetic venues that keep the retail grass word.

Colour targets are the medians of 2026 broadcast stills measured with Modern colour's method (see
``docs/modern_surfaces/README.md``), per surface and light (day, afternoon, night, dome, rain, snow), and a venue whose
own 2026 broadcast was measured follows it (``broadcast`` in the venue table). The colour map of each bundle is solved
against the light rig that bundle is drawn under (retail rigs, or Modern colour's configured rigs when that option
graded the disc) with Modern colour's calibrated screen factor, the bundle's Fldd tint and the grass vertex tint, then
divided by the response the game was MEASURED to add on top of that model (FIELD_RESPONSE, QUAD_RESPONSE,
APRON_RESPONSE: tf lab 3 and ig's smoke lab on candidate B, 2026-09-27), so the drawn pixels land on the broadcast
values; the outside grass (the apron) follows the field's colour a touch darker. The ROST turf word (+0x1C, which
changes wear, divots, shadows, stains and two gameplay scalars) is never written: this option changes how surfaces
LOOK only.

Composition: the build step runs after every stadium writer (Modern colour, Modern Arrowhead, Modern MetLife and its
model, the 2026 venue art, SoFi Stadium, Highmark Stadium). It repaints the surface of the field span each of them
left, refits it inside its fixed VC-LZ span (the retail 32-byte wrapper and loader scratch word unchanged), and
updates their receipts so their status still reads applied. The painter is idempotent, so a writer may also call
``paint_field`` itself; the post-pass then leaves identical bytes.

EXPERIMENTAL / UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
import os
import struct
import sys
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

OWNER = "nfl2k5_modern_surfaces"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Modern playing surfaces (experimental)"
HELP_TEXT = (
    "Gives every team's home field the surface its 2026 stadium really has: modern synthetic turf (saturated even "
    "green with factory 5-yard bands, fibres up close instead of flat carpet) or modern natural grass (brighter, "
    "mown in stripes). Colours follow 2026 broadcast stills for day, afternoon, night and domes, and compose with "
    "Modern colour, the 2026 venue art, MetLife, SoFi and Highmark. Gameplay is unchanged (the turf word stays "
    "retail). Every field is refit inside its fixed span. Off in every preset; needs a disc image. Appearance in "
    "game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_surfaces"
ART_DIR = DATA_DIR / "art"
VENUES_PATH = DATA_DIR / "venues.json"
PINS_PATH = DATA_DIR / "pins.json"
VENUES_SCHEMA = "nfl2k5_modern_surfaces_venues/v1"
PINS_SCHEMA = "nfl2k5_modern_surfaces_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_modern_surfaces_receipt/v1"
TRANSFORM_REVISION = "tf-v3.1"
HOME_PREFIXES = tuple(f"s{i:02d}" for i in range(31)) + ("s37",)
TIMES, WEATHERS = "dan", "drs"
CODES = tuple(t + w for t in TIMES for w in WEATHERS)
ROST_OUTER_INDEX = 5
PALETTE_CAPS = (256, 128, 96, 64, 48, 32)

# --- the field scene --------------------------------------------------------------------------------------------
FIELD_SCENE = "field"
COLOUR_SHAPE = "A_grass_color"
COLOUR_MATERIAL = "color_premipped"
OUTSIDE_MATERIAL = "grass_outside_premipped"
END_ZONE_MATERIALS = ("endzone_N_L", "endzone_N_M", "endzone_N_R", "endzone_S_L", "endzone_S_M", "endzone_S_R")
NORMAL_NAME = "detail_normal"
DIVOTS_NAME = "divots"
#: goal line to goal line (the colour submesh spans z = +-45.72 m) and the colour quad's half width (+-25.1458 m)
GOAL_Z, HALF_WIDTH = 45.72, 25.1458
#: one period of the colour map: 10 yards along (two 5-yard bands) and 10 yards across (two checker cells)
PERIOD = 9.144
#: the colour shape's UV constant after the remap: 4,096 NORMSHORT2 steps per period (u = n x 32767/4096 + 5 covers
#: 0..10 periods goal line to goal line, v = n x 32767/4096 + 3 covers 0..5.5 across), so the grid's 2.286 m steps
#: land on multiples of 1,024 and the vertex stream stays compressible; the end zones keep their UVs, re-encoded
UV_CONSTANT = (32767 / 4096, 32767 / 4096, 5.0, 3.0)
#: A quad field (one quad goal line to goal line: the retail turf venues) samples its colour map CLAMPED (PROVED IN
#: GAME, tf lab 3 on candidate B: MetLife and Lumen showed one light band at the goal line where u = 0 and the edge
#: texel's tone everywhere past u = 1, no 5-yard bands; the grid fields showed their bands). So a quad field takes the
#: WHOLE field inside 0..1: 20 bands of 5 yards along (6 texels each on 128), a 1/32 margin each side, and this
#: constant (u, v = n x 32767/65536 + 0.5; the end zones keep their UVs, re-encoded).
UV_CONSTANT_QUAD = (32767 / 65536, 32767 / 65536, 0.5, 0.5)
QUAD_BANDS = 20
#: Fldd word 1 (the wear dirt colour, ARGB) on synthetic venues that keep the retail grass word: scuffed turf and
#: dark infill instead of brown dirt (retail 0xE05E5430)
SYNTHETIC_WEAR = 0x9A2A3324

# --- looks --------------------------------------------------------------------------------------------------------
#: Measured 2026 broadcast turf medians (docs/modern_surfaces/README.md, same mask as docs/modern_color): synthetic
#: day = Lumen/Nissan/Paycor, afternoon = Lumen 5:20 PM PT, night = MetLife SNF, dome = Lucas Oil/Reliant/U.S. Bank/
#: SoFi; grass day = Acrisure/EverBank, afternoon = Lincoln Financial, night = Arrowhead MNF, dome = Allegiant.
#: Rain and snow are extrapolated (DESIGN). Each look nudges the family's targets (DESIGN, Noah picks).
LIGHT_CLASSES = ("day", "afternoon", "night", "dome", "rain", "snow")
LOOKS = {
    "synthetic_fieldturf": dict(family="synthetic", detail="fibre", targets=dict(
        day=(88, 108, 64), afternoon=(86, 106, 68), night=(74, 94, 62), dome=(100, 122, 72))),
    "synthetic_helix": dict(family="synthetic", detail="helix", targets=dict(
        day=(86, 107, 58), afternoon=(84, 105, 62), night=(72, 93, 58), dome=(98, 124, 66))),
    "synthetic_vivid": dict(family="synthetic", detail="fibre", targets=dict(
        day=(84, 114, 56), afternoon=(84, 112, 60), night=(70, 100, 54), dome=(94, 130, 62))),
    "grass_bluegrass": dict(family="grass", detail="blade_bluegrass", targets=dict(
        day=(88, 110, 64), afternoon=(94, 118, 68), night=(90, 110, 56), dome=(82, 106, 58))),
    "grass_bermuda": dict(family="grass", detail="blade_bermuda", targets=dict(
        day=(102, 121, 70), afternoon=(110, 132, 76), night=(106, 121, 56), dome=(88, 114, 58))),
    "grass_checker": dict(family="grass", detail="blade_bermuda", targets=dict(
        day=(100, 120, 68), afternoon=(108, 130, 74), night=(104, 120, 56), dome=(86, 112, 58))),
}
#: rain darkens and cools (wet), snow lays a light cover over the surface (DESIGN; the retail snow fields whiten too)
RAIN_GAIN = (0.84, 0.88, 0.93)
SNOW_COVER, SNOW_RGB = 0.40, (205, 212, 220)
#: the outside grass (beyond the white border, under the benches and the stands) follows the field a touch darker
OUTSIDE_SHADE = 0.93

# --- the game's measured response ------------------------------------------------------------------------------------
#: PROVED IN GAME (tf lab 3 and ig's smoke lab, candidate B, stock xemu at 1x, 2026-09-27): the game draws the playing
#: field brighter than the offline model (Modern colour's screen factor, fitted under the retail detail normal) by a
#: factor that follows this option's detail normal (its palette alpha: 0.64 fibre, 0.66 helix, 0.56 the blades) and
#: the field's layout. Game / model, median turf of each run's play frames: Arrowhead (grid, blades) day 1.085, night
#: 1.02; Highmark (quad, blades) day 1.16, night 1.09, so a quad field draws 1.07 x a grid field; MetLife and Lumen
#: (quads, fibre) day 1.35, night 1.25; SoFi (quad, helix, dome) 1.34. The table holds the grid values. INFERRED: the
#: afternoon is the mean of day and night, rain and snow follow the day, fibre and blade domes follow the helix dome's
#: ratio to the night (1.035), helix day and night follow fibre scaled by the helix dome.
FIELD_RESPONSE = {
    "fibre": dict(day=1.26, afternoon=1.215, night=1.17, dome=1.21),
    "helix": dict(day=1.30, afternoon=1.255, night=1.21, dome=1.25),
    "blade_bermuda": dict(day=1.085, afternoon=1.05, night=1.02, dome=1.055),
    "blade_bluegrass": dict(day=1.085, afternoon=1.05, night=1.02, dome=1.055),
}
QUAD_RESPONSE = 1.07
#: PROVED IN GAME (the same runs): the outside grass is not under the detail layer and draws about twice the field
#: model per unit of map, nearly neutral: in-game apron / (map x rig gain x screen factor x Fldd tint x vertex tint)
#: = day 1.98..2.19, night 1.88..2.09, SoFi's dome 1.97..2.11 per channel. Modern colour's OUTSIDE_RESPONSE (1.17,
#: 1.41, 1.49, one retail sample) under-weights red, so an apron solved with it drew lime in game.
APRON_RESPONSE = dict(day=(2.11, 2.09, 1.99), night=(2.06, 2.01, 1.92), dome=(2.11, 2.04, 1.97))
#: the brightest a colour-map channel may be authored (headroom for the P8 quantizer and the bands)
MAP_CEILING = 238.0
MAP_RED_OVER_GREEN, MAP_BLUE_OVER_GREEN = 0.95, 0.85


class ModernSurfacesError(ValueError):
    """A plain refusal before any mutation."""


def require(ok, message):
    if not ok:
        raise ModernSurfacesError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_txtr as tx  # noqa: E402
    from nfl_scene_probe import HEADER  # noqa: E402
    return tx, HEADER


def _ml():
    from . import nfl2k5_modern_metlife as ml
    return ml


# --- the venue table ----------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def venues():
    doc = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    require(doc.get("schema") == VENUES_SCHEMA, "unsupported Modern surfaces venue table")
    rows = {row["prefix"]: row for row in doc["venues"]}
    require(set(rows) == set(HOME_PREFIXES), "the venue table must name all 32 home venues")
    for prefix, row in rows.items():
        require(row["look"] in LOOKS and LOOKS[row["look"]]["family"] == row["surface"],
                f"{prefix}: look {row['look']} does not match surface {row['surface']}")
        require(row.get("sources"), f"{prefix}: every venue cites its surface")
        for key in ("broadcast", "design"):
            seen = row.get(key)
            if seen is not None:
                require(seen.get("light") in ("day", "afternoon", "night", "dome") and len(seen.get("rgb") or ()) == 3
                        and seen.get("source"), f"{prefix}: a {key} target needs a light, an RGB and a source")
    return rows


def venue_look(prefix, overrides=None):
    """The look a home venue gets (the table's, or a family-wide override: {"synthetic": look, "grass": look})."""
    row = venues()[prefix]
    look = (overrides or {}).get(row["surface"]) or row["look"]
    require(look in LOOKS and LOOKS[look]["family"] == row["surface"], f"{prefix}: {look} is not a {row['surface']} look")
    return look


def bundle_parts(name):
    """('s13', 'n', 'd') of 's13nd.iff'."""
    require(len(name) == 9 and name.endswith(".iff") and name[:3] in HOME_PREFIXES and name[3] in TIMES
            and name[4] in WEATHERS, f"{name} is not a home venue bundle")
    return name[:3], name[3], name[4]


def light_class(name, indoor):
    """day / afternoon / night / dome / rain / snow for one bundle (the engine picks the rig the same way:
    indoor, rain, snow, then the time of day; FUN_000641c0)."""
    _prefix, t, w = bundle_parts(name)
    if indoor:
        return "dome"
    if w == "r":
        return "rain"
    if w == "s":
        return "snow"
    return {"d": "day", "a": "afternoon", "n": "night"}[t]


def rig_name(cls, time_code):
    """The light table name Modern colour uses for a light class."""
    return {"day": "day", "afternoon": "afternoon", "night": "night_indoor", "dome": "night_indoor", "rain": "rain",
            "snow": "snow"}[cls]


# --- art ------------------------------------------------------------------------------------------------------------
MIP_ORIGINS = ((0, 0), (0, 256), (256, 256), (384, 256), (448, 256), (480, 256))


@lru_cache(maxsize=None)
def detail_art(kind):
    """(index levels [6 arrays], palette BGRA bytes) of one shipped detail normal (data/.../detail_<kind>.png)."""
    import numpy as np
    from PIL import Image
    path = ART_DIR / f"detail_{kind}.png"
    require(path.is_file(), f"Modern surfaces art is missing: {path.name}")
    with Image.open(path) as img:
        require(img.mode == "P" and img.size == (512, 384), f"{path.name}: expected a 512 x 384 palette PNG")
        idx = np.array(img, dtype=np.uint8)
        pal = img.getpalette()[:768]
        trns = img.info.get("transparency")
    require(isinstance(trns, (bytes, bytearray)) and len(trns) == 256, f"{path.name}: tRNS alpha missing")
    rgb = np.array(pal, dtype=np.uint8).reshape(256, 3)
    bgra = np.concatenate([rgb[:, [2, 1, 0]], np.frombuffer(bytes(trns), np.uint8)[:, None]], 1).astype(np.uint8)
    levels = []
    for k, (ox, oy) in enumerate(MIP_ORIGINS):
        w, h = 512 >> k, 256 >> k
        levels.append(np.ascontiguousarray(idx[oy:oy + h, ox:ox + w]))
    return tuple(levels), bgra.tobytes()


#: The palette alpha of each detail kind (tf-v1 and v2 as one constant, tf-v3 as every mip level's mean): the game
#: draws the field's brightness nearly in proportion to it, and FIELD_RESPONSE was measured with these values, so the
#: v3 blades vary around them without moving the mean.
DETAIL_ALPHA = {"fibre": 163, "helix": 168, "blade_bermuda": 143, "blade_bluegrass": 143}
#: SHA-256 of the detail videos earlier revisions wrote (tf-v1 and v2: normals in the palette, one alpha; tf-v3: the
#: alpha blades before v3.1 calmed mips 0 and 1): discs built with them keep reading this option's signature.
LEGACY_DETAIL_SHA256 = {
    "67963d00b6a73109eb853082770886544b8d1a2c6c027230cc4c99cf42adb9b2": ("blade_bermuda", "full"),
    "7a57a3fe44720d42e5e4adfb1ebfb978894ed0a690d11e0448bab696944624c6": ("blade_bermuda", "tiled"),
    "9ab0ec99c505efcfd22d191bfeb7c6dd578cc447a1770a993a82c427c4e30dde": ("blade_bluegrass", "full"),
    "48fbf139db5a9e94f49d1b1720728d1235d6edb0547a8bfdfe2f5173bb1f2671": ("blade_bluegrass", "tiled"),
    "ec57f347a7690235aa97c468cea26535cdede82e0e2f523402af1a096b052aa5": ("fibre", "full"),
    "696572c423ba914f002ae1d615865f35192b712f3a5ace8db1e287769f601ff4": ("fibre", "tiled"),
    "28cb7d0a8172a0da800aa6dd770d8da0497cacb653b9887badda8fb680f41605": ("helix", "full"),
    "d8eefc7bdd421be575e4da7c371140a0e19021d84e16465f5b220ada04fc5d09": ("helix", "tiled"),
    "d86f9aa3bdaebc52207d360afe4553d7f45251cb0e14a87561a2759d712a5f8c": ("blade_bermuda", "full"),
    "fa5960335f839ded25e705740bad1cc2de3cf3c7875175451da182215ad548d5": ("blade_bermuda", "tiled"),
    "17b99519cea25b164b6bac8605ffd4cad5e493b96bf0f0129a941960e5ca10cd": ("blade_bluegrass", "full"),
    "cb92ea2b386dc4fa60d52705a8cea59602c7b3969cab65813f0dcd9cb758568d": ("blade_bluegrass", "tiled"),
    "7f7d58454b56ceaab6bcae69c5ae51c481b13c2abfd306c92644c6261d46a824": ("fibre", "full"),
    "f86060c942c38af5feb9937adbc0e00c1814dddcc01321d0f6a2aa6a6f5d2921": ("fibre", "tiled"),
    "1e23a2d295921cdbc80c48e4cfa89057b73070d496dcb57df7d5ddb5d759d8f9": ("helix", "full"),
    "178467740fa03967a8316de949eecd2489c317c23623a27ed9e2bd5131a3a05f": ("helix", "tiled"),
}
TILE_ORIGINS = ((0, 0), (0, 64), (32, 64), (48, 64), (56, 64), (60, 64))
#: which of the three 64 x 64 tiles fills each 64 x 64 block (4 rows x 8 columns) of the 512 x 256 texture, and the
#: same block at every mip. In the texture's swizzled order the blocks run 0, 1, 8, 9, 2, 3, 10, 11, 16, ... and the
#: tiles follow 0, 1, 2, 0, 1, 2, ...: every block repeats the one three blocks back (12,288 bytes at mip 0, inside the
#: 14-bit match distance), while on the field no tile repeats as a lattice (one tile repeated did, PROVED OFFLINE)
TILE_GRID = ((0, 1, 1, 2, 1, 2, 2, 0),
             (2, 0, 0, 1, 0, 1, 1, 2),
             (2, 0, 0, 1, 0, 1, 1, 2),
             (1, 2, 2, 0, 2, 0, 0, 1))
TILED_DISTANCES = (12288, 3072, 768, 192, 48, 12, 4096, 1024, 256, 64, 16, 4, 8192, 2048, 512, 128, 32, 8)


@lru_cache(maxsize=None)
def detail_tile_art(kind):
    """((index levels [64, 32, 16, 8, 4, 2] of each of the three 64 x 64 tiles), palette BGRA) of one detail kind."""
    import numpy as np
    from PIL import Image
    path = ART_DIR / f"detail_{kind}_tile.png"
    require(path.is_file(), f"Modern surfaces art is missing: {path.name}")
    with Image.open(path) as img:
        require(img.mode == "P" and img.size == (192, 96), f"{path.name}: expected a 192 x 96 palette PNG")
        idx = np.array(img, dtype=np.uint8)
    tiles = []
    for t in range(3):
        levels = []
        for k, (ox, oy) in enumerate(TILE_ORIGINS):
            n = 64 >> k
            levels.append(np.ascontiguousarray(idx[oy:oy + n, 64 * t + ox:64 * t + ox + n]))
        tiles.append(tuple(levels))
    return tuple(tiles), detail_art(kind)[1]


@lru_cache(maxsize=None)
def pattern_art(look):
    """{'map': (64, 128), 'map_square': (128, 128), 'outside': (128, 128)} luminance multipliers of one look."""
    import numpy as np
    from PIL import Image
    path = ART_DIR / f"pattern_{look}.png"
    require(path.is_file(), f"Modern surfaces art is missing: {path.name}")
    with Image.open(path) as img:
        require(img.mode == "L" and img.size == (128, 320), f"{path.name}: expected a 128 x 320 grey PNG")
        a = np.array(img, dtype=np.float64) / 128.0
    return {"map": a[0:64], "map_square": a[64:192], "outside": a[192:320]}


#: pattern detail, stepped down only when a field span misses: 2 the shipped pattern, 1 its bands (or checker) as two
#: flat tones, 0 one flat colour
PATTERN_DETAILS = (2, 1, 0)


def pattern_level(look, key, detail):
    import numpy as np
    pat = pattern_art(look)[key]
    if detail >= 2:
        return pat
    if detail == 1 and key != "outside":
        amp = float(np.mean(np.abs(pat - 1.0)))
        return np.where(pat >= 1.0, 1.0 + amp, 1.0 - amp)
    return np.ones_like(pat)


# --- colour solving -------------------------------------------------------------------------------------------------
def rig_gain(rig, colour_settings=None):
    """Per-channel ambient x intensity + sum(light colour x intensity) of the rig the bundle is drawn under: retail,
    or Modern colour's configured rig when that option graded the disc (colour_settings is its receipt settings)."""
    from . import nfl2k5_modern_color as colour
    table = colour.configured_rig(rig, colour_settings) if colour_settings is not None else colour.read_rig(colour._retail_table(rig))
    return tuple(table["ambient"][c] * table["ambient_intensity"] + sum(col[c] * i for col, i in table["lights"])
                 for c in range(3))


def screen_factor(rig):
    from . import nfl2k5_modern_color as colour
    return colour.SCREEN_FACTOR.get(rig, colour.SCREEN_FACTOR["night_indoor"])


def target_rgb(look, cls):
    t = LOOKS[look]["targets"]
    if cls == "rain":
        return tuple(v * g for v, g in zip(t["day"], RAIN_GAIN))
    if cls == "snow":
        return t["day"]
    return t[cls]


def venue_target(prefix, look, cls):
    """The broadcast target of one venue's surface under one light: the look's, scaled per channel by the venue's own
    measured 2026 broadcast when the table has one (its ratio to the look at the light it was measured under carries
    to the venue's other lights). A venue row may carry a ``design`` target of the same shape that replaces its measured
    broadcast (Allegiant, Beta 77 pass 4: the measurement stays in the row as the evidence)."""
    target = target_rgb(look, cls)
    row = venues()[prefix]
    seen = row.get("design") or row.get("broadcast")
    if not seen:
        return target
    base = target_rgb(look, seen["light"])
    return tuple(t * (m / max(1e-6, b)) for t, m, b in zip(target, seen["rgb"], base))


def field_response(look, cls, layout="grid"):
    """The measured in-game factor over the offline model for this look's detail normal, light and field layout."""
    table = FIELD_RESPONSE[LOOKS[look]["detail"]]
    base = table.get(cls, table["day"])
    return base * (QUAD_RESPONSE if layout == "quad" else 1.0)


def apron_response(cls):
    """The measured in-game response of the outside grass (per channel) for a light class."""
    if cls == "afternoon":
        return tuple((a + b) / 2 for a, b in zip(APRON_RESPONSE["day"], APRON_RESPONSE["night"]))
    return APRON_RESPONSE.get(cls, APRON_RESPONSE["day"])


def solve_map_mean(look, cls, rig, *, colour_settings=None, tint=(255, 255, 255), vertex=(255, 255, 255), response=1.0,
                   target=None):
    """Mean colour-map RGB that draws the broadcast target under this rig: Modern colour's calibrated model (on screen
    = map x rig gain x screen factor x Fldd tint x vertex tint) times the game's measured ``response`` for this
    surface (field_response). Scaled down as a whole (hue kept) when a channel would pass MAP_CEILING."""
    gain = rig_gain(rig, colour_settings)
    factor = screen_factor(rig)
    target = target or target_rgb(look, cls)
    m = [t / max(1e-6, g * f * (ti / 255.0) * (ve / 255.0) * response)
         for t, g, f, ti, ve in zip(target, gain, factor, tint, vertex)]
    # a map stays a plausible green whatever the rig: the blue calibration under the warm retail rigs is the model's
    # weakest part (FABLE_B70_COLOR_REPORT: blue collapses on screen), so red and blue never pass green
    m[0] = min(m[0], MAP_RED_OVER_GREEN * m[1])
    m[2] = min(m[2], MAP_BLUE_OVER_GREEN * m[1])
    top = max(m)
    if top > MAP_CEILING:
        m = [v * MAP_CEILING / top for v in m]
    return tuple(m)


def _pattern_at(pat, size):
    """A pattern resampled to (width, height) when a bundle's texture has another size (one period either way)."""
    import numpy as np
    if pat.shape == (size[1], size[0]):
        return pat
    from PIL import Image
    grey = Image.fromarray(np.clip(np.round(pat * 128), 0, 255).astype(np.uint8), "L")
    return np.asarray(grey.resize(size, Image.BOX), np.float64) / 128.0


def solve_outside_mean(look, cls, rig, *, colour_settings=None, tint=(255, 255, 255), vertex=(255, 255, 255),
                       target=None):
    """Mean outside-grass RGB that draws OUTSIDE_SHADE of the field target, in the field's own chroma. The outside
    grass is not under the detail layer, so it draws about twice as bright per unit of map as the field model: the
    game's measured apron response (APRON_RESPONSE), with the outside shape's vertex tint."""
    gain = rig_gain(rig, colour_settings)
    factor = screen_factor(rig)
    target = target or target_rgb(look, cls)
    m = [t * OUTSIDE_SHADE / max(1e-6, g * f * (ti / 255.0) * (ve / 255.0) * r)
         for t, g, f, ti, ve, r in zip(target, gain, factor, tint, vertex, apron_response(cls))]
    m[0] = min(m[0], MAP_RED_OVER_GREEN * m[1])
    m[2] = min(m[2], MAP_BLUE_OVER_GREEN * m[1])
    top = max(m)
    if top > MAP_CEILING:
        m = [v * MAP_CEILING / top for v in m]
    return tuple(m)


def quad_pattern(look, size, detail=2):
    """The look's pattern laid over the WHOLE field for a quad field (sampled clamped, so it cannot repeat): the band
    (or checker) tones of one period in QUAD_BANDS 5-yard bands along the field between 1/32 margins, and the
    period's mottle shrunk to one band pair per period and tiled."""
    import numpy as np
    from PIL import Image
    w, h = size
    period = pattern_level(look, "map_square" if w == h else "map", detail)
    ph, pw = period.shape
    light, dark = float(period[:, :pw // 2].mean()), float(period[:, pw // 2:].mean())
    tones = np.where(np.arange(pw) < pw // 2, light, dark)[None, :]
    mottle = period - tones
    mu, mv = max(1, w // 32), max(1, h // 32)
    per_band = (w - 2 * mu) / QUAD_BANDS
    cols = np.clip(np.floor((np.arange(w) + 0.5 - mu) / per_band).astype(int), 0, QUAD_BANDS - 1)
    checker = LOOKS[look].get("checker") or look == "grass_checker"
    if checker:
        across = (h - 2 * mv) / (2 * HALF_WIDTH / (5 * 0.9144))
        rows = np.clip(np.floor((np.arange(h) + 0.5 - mv) / across).astype(int), 0, 10 ** 6)
        parity = (cols[None, :] + rows[:, None]) % 2
    else:
        parity = np.broadcast_to((cols % 2)[None, :], (h, w))
    out = np.where(parity == 0, light, dark).astype(np.float64)
    if detail >= 2:
        band_pair = max(2, int(round(2 * per_band)))
        rows_per_period = max(2, int(round((h - 2 * mv) * PERIOD / (2 * HALF_WIDTH))))
        grey = Image.fromarray(np.clip(np.round((mottle + 1.0) * 128), 0, 255).astype(np.uint8), "L")
        small = np.asarray(grey.resize((band_pair, rows_per_period), Image.BOX), np.float64) / 128.0 - 1.0
        tiled = np.tile(small, (h // rows_per_period + 2, w // band_pair + 2))[:h, :w]
        out = out + tiled
    return out


def colour_map_rgba(look, cls, mean, *, size=(128, 64), detail=2, layout="grid"):
    """RGBA uint8 colour map for one bundle: the look's pattern around ``mean`` (one period repeated on a grid field,
    the whole field once on a quad field); snow lays a light cover."""
    import numpy as np
    w, h = size
    require(w in (32, 64, 128, 256) and h in (w, w // 2), f"unexpected colour map size {w}x{h}")
    if layout == "quad":
        pat = quad_pattern(look, size, detail)
    else:
        pat = _pattern_at(pattern_level(look, "map_square" if w == h else "map", detail), size)
    rgb = np.array(mean, np.float64)[None, None, :] * pat[..., None]
    if cls == "snow":
        rgb = rgb * (1 - SNOW_COVER) + np.array(SNOW_RGB, np.float64)[None, None, :] * SNOW_COVER * pat[..., None]
    out = np.concatenate([np.clip(np.round(rgb), 0, 255), np.full(pat.shape + (1,), 255.0)], -1)
    return out.astype(np.uint8)


def outside_rgba(look, cls, mean, size, detail=2):
    import numpy as np
    pat = _pattern_at(pattern_level(look, "outside", detail), size)
    rgb = np.array(mean, np.float64)[None, None, :] * pat[..., None]
    if cls == "snow":
        rgb = rgb * (1 - SNOW_COVER) + np.array(SNOW_RGB, np.float64)[None, None, :] * SNOW_COVER * pat[..., None]
    out = np.concatenate([np.clip(np.round(rgb), 0, 255), np.full(pat.shape + (1,), 255.0)], -1)
    return out.astype(np.uint8)


# --- the field scene ------------------------------------------------------------------------------------------------
def _rel(buf, at):
    value = struct.unpack_from("<i", buf, at)[0]
    return None if value == 0 else at + value - 1


def _set_rel(buf, at, target):
    struct.pack_into("<i", buf, at, 0 if target is None else target - at + 1)


def _shape(rec, name):
    shape = next((s for s in rec["shapes"] if s["name"] == name), None)
    require(shape is not None, f"the field has no {name} shape")
    return shape


def _stream(shape, slot):
    a = shape["attribute_descriptors"][slot]
    return a, shape["vertex_streams"][a["stream_index"]]


def _submesh_vertices(rec, decoded, shape, material):
    from . import nfl2k5_scne_builder as sb
    mats = [m["name"] for m in rec["materials"]]
    at = shape["record_offset"]
    count = struct.unpack_from("<H", decoded, at + 0x54)[0]
    table = _rel(decoded, at + 0x70)
    out = set()
    for k in range(count):
        s = table + k * 0x80
        if mats[struct.unpack_from("<H", decoded, s)[0]] != material:
            continue
        words = struct.unpack_from("<H", decoded, s + 0x7C)[0]
        push = _rel(decoded, s + 0x78)
        for _mode, ix in sb.decode_words(bytes(decoded[push:push + 4 * words])):
            out.update(ix)
    return sorted(out)


def _material(rec, name):
    return next((m for m in rec["materials"] if m["name"] == name), None)


def _texture_rows(rec):
    return _ml().texture_rows(rec)


def field_tint(bundle):
    """(r, g, b) of the bundle's Fldd time-of-day tint (word 2), which the engine multiplies into the field."""
    tx, HEADER = _tools()
    for chunk in tx.parse_chunks(bundle, allow_trailing=True):
        if chunk.kind == "Fldd":
            at = _fldd_words(bundle, chunk)
            word = struct.unpack_from("<I", bundle, at + 8)[0]
            return ((word >> 16) & 255, (word >> 8) & 255, word & 255)
    raise ModernSurfacesError("bundle lacks its Fldd chunk")


def _fldd_words(bundle, chunk):
    """Offset (in the bundle) of Fldd word 0."""
    tx, HEADER = _tools()
    body = bundle[chunk.offset + HEADER.size:chunk.offset + HEADER.size + chunk.stored_size]
    name = body[32:].decode("utf-16le", "ignore").split("\0")[0]
    return chunk.offset + HEADER.size + 32 + (len(name) + 1) * 2


def _grass_vertex_tint(decoded, rec):
    """The colour submesh's vertex colour (retail white; afternoon bundles bake a warm tint Modern colour softens)."""
    shape = _shape(rec, COLOUR_SHAPE)
    a, st = _stream(shape, 3)
    if a["format_name"] != "D3DCOLOR":
        return (255, 255, 255)
    idx = _submesh_vertices(rec, decoded, shape, COLOUR_MATERIAL)
    b, g, r, _a = decoded[st["offset"] + st["stride"] * idx[0] + a["byte_offset"]:][:4]
    return (r, g, b)


def _outside_vertex_tint(decoded, rec):
    """Mean vertex colour of the outside grass's own submesh (Modern colour's edge shading sits in it)."""
    shape = next((s for s in rec["shapes"] if s["name"] == "Outside_grass"), None)
    if shape is None:
        return (255, 255, 255)
    a, st = _stream(shape, 3)
    if a["format_name"] != "D3DCOLOR":
        return (255, 255, 255)
    idx = _submesh_vertices(rec, decoded, shape, OUTSIDE_MATERIAL)
    if not idx:
        return (255, 255, 255)
    sums = [0, 0, 0]
    for i in idx:
        b, g, r, _a = decoded[st["offset"] + st["stride"] * i + a["byte_offset"]:][:4]
        sums[0] += r
        sums[1] += g
        sums[2] += b
    return tuple(v / len(idx) for v in sums)


def field_layout(decoded, rec):
    """"quad" for a field drawn as one quad from goal line to goal line (the retail turf venues), else "grid"."""
    shape = _shape(rec, COLOUR_SHAPE)
    return "quad" if len(_submesh_vertices(rec, decoded, shape, COLOUR_MATERIAL)) <= 8 else "grid"


def remap_uvs(out, rec, *, layout="grid", size=(128, 64)):
    """Planar UVs for the colour submesh, and every other vertex of the shape (the end zones) re-encoded so its UV
    does not move. A grid field: u along the field in 10-yard periods from the +z goal line, v across in 10-yard
    periods, under UV_CONSTANT (the grid wraps). A quad field: the whole field inside 0..1 between 1/32 margins of the
    colour map of ``size``, under UV_CONSTANT_QUAD (the quad is sampled clamped). Returns the vertices written."""
    shape = _shape(rec, COLOUR_SHAPE)
    at = shape["record_offset"] + 0x30
    su, sv, ou, ov = struct.unpack_from("<4f", out, at)
    nsu, nsv, nou, nov = UV_CONSTANT_QUAD if layout == "quad" else UV_CONSTANT
    w, h = size
    mu, mv = max(1, w // 32) / w, max(1, h // 32) / h
    a0, st0 = _stream(shape, 0)
    a6, st6 = _stream(shape, 6)
    require(a6["format_name"] == "NORMSHORT2" and a0["format_name"] == "FLOAT3", "unexpected colour shape layout")
    colour = set(_submesh_vertices(rec, out, shape, COLOUR_MATERIAL))
    written = 0
    for i in range(shape["vertex_count"]):
        uv_at = st6["offset"] + st6["stride"] * i + a6["byte_offset"]
        if i in colour:
            x, _y, z = struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i + a0["byte_offset"])
            if layout == "quad":
                u = mu + (GOAL_Z - z / 100.0) / (2 * GOAL_Z) * (1 - 2 * mu)
                v = mv + (x / 100.0 + HALF_WIDTH) / (2 * HALF_WIDTH) * (1 - 2 * mv)
            else:
                u = (GOAL_Z - z / 100.0) / PERIOD
                v = (x / 100.0 + HALF_WIDTH) / PERIOD
        else:
            qu, qv = struct.unpack_from("<2h", out, uv_at)
            u, v = qu / 32767.0 * su + ou, qv / 32767.0 * sv + ov
        nu, nv = round((u - nou) / nsu * 32767.0), round((v - nov) / nsv * 32767.0)
        if layout == "quad":   # a retail end-zone UV of exactly 0 or 1 sits one step past the quad constant's range
            nu, nv = max(-32767, min(32767, nu)), max(-32767, min(32767, nv))
        require(-32767 <= nu <= 32767 and -32767 <= nv <= 32767, "a colour-shape UV does not fit the new constant")
        struct.pack_into("<2h", out, uv_at, nu, nv)
        written += 1
    struct.pack_into("<4f", out, at, nsu, nsv, nou, nov)
    return written


def _borrow_outside_texture(out, rec, outside_colour):
    """For a field drawn from a material colour: the colour material takes the outside-grass texture record, the
    outside grass keeps a plain colour. Returns the texture row the colour map now lives in."""
    cm, om = _material(rec, COLOUR_MATERIAL), _material(rec, OUTSIDE_MATERIAL)
    require(cm is not None and om is not None, "the field lacks its colour or outside-grass material")
    require(cm.get("texture_index") is None, "the colour material already has a texture")
    require(om.get("texture_index") is not None, "the outside grass has no texture to lend")
    tex_at = _rel(out, om["record_offset"] + 0x30)
    require(tex_at is not None, "outside-grass texture pointer missing")
    _set_rel(out, cm["record_offset"] + 0x30, tex_at)
    _set_rel(out, om["record_offset"] + 0x30, None)
    for field in (0x14, 0x18):
        struct.pack_into("<I", out, cm["record_offset"] + field, 0xFFFFFFFF)
    r, g, b = (int(round(min(255, max(0, v)))) for v in outside_colour)
    struct.pack_into("<I", out, om["record_offset"] + 0x18, 0xFF000000 | (r << 16) | (g << 8) | b)
    rows = {int(t["index"]): t for t in rec["embedded_textures"]}
    return rows[int(om["texture_index"])]


def borrowed(decoded, rec):
    """True when this field's colour material already draws the outside-grass texture (a second pass)."""
    cm, om = _material(rec, COLOUR_MATERIAL), _material(rec, OUTSIDE_MATERIAL)
    if cm is None or om is None:
        return False
    return (_rel(decoded, om["record_offset"] + 0x30) is None and _rel(decoded, cm["record_offset"] + 0x30) is not None)


def turf_envelope(rgb_samples):
    """(hue lo, hue hi, sat lo, sat hi, val lo, val hi) of the current turf (2nd..98th percentiles)."""
    hs, ss, vs = [], [], []
    for r, g, b in rgb_samples:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hs.append(h * 360)
        ss.append(s)
        vs.append(v)

    def pct(values, q):
        values = sorted(values)
        return values[min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))]
    return (pct(hs, .02), pct(hs, .98), pct(ss, .02), pct(ss, .98), pct(vs, .02), pct(vs, .98))


#: an end-zone palette entry is turf when it sits inside the field turf's own envelope widened by these margins (a
#: tighter rule than Modern colour's end-zone pass: dark team greens and saturated paint are never turf)
ENV_HUE, ENV_SAT, ENV_VAL = 12.0, 0.10, 0.10


def recolour_end_zone_palette(palette, envelope, old_mean, new_mean):
    """(new BGRA palette, entries changed): the turf-coloured entries of an end-zone palette take the new surface
    colour, keeping each entry's shading relative to the old turf mean; paint entries are untouched."""
    h_lo, h_hi, s_lo, s_hi, v_lo, v_hi = envelope
    old_luma = max(1e-6, 0.299 * old_mean[0] + 0.587 * old_mean[1] + 0.114 * old_mean[2])
    out = bytearray(palette)
    changed = 0
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h *= 360
        if not (h_lo - ENV_HUE <= h <= h_hi + ENV_HUE and s_lo - ENV_SAT <= s <= s_hi + ENV_SAT
                and v_lo - ENV_VAL <= v <= v_hi + ENV_VAL):
            continue
        k = (0.299 * r + 0.587 * g + 0.114 * b) / old_luma
        nr, ng, nb = (int(min(255, max(0, round(c * k)))) for c in new_mean)
        if (nb, ng, nr) != (b, g, r):
            out[i * 4:i * 4 + 3] = bytes((nb, ng, nr))
            changed += 1
    return bytes(out), changed


def _current_turf(decoded, rec, system):
    """(RGB samples of the current turf, mean RGB) before this pass paints: the colour map's pixels, or the colour
    material's word when the field has no colour texture."""
    import numpy as np
    ml = _ml()
    rows = _texture_rows(rec)
    if COLOUR_MATERIAL in rows:
        rgba, _pal = ml.read_p8(decoded, system, rows[COLOUR_MATERIAL])
        px = rgba.reshape(-1, 4)[:, :3].astype(np.float64)
        step = max(1, len(px) // 2048)
        samples = [tuple(p) for p in px[::step]]
        return samples, tuple(px.mean(0))
    cm = _material(rec, COLOUR_MATERIAL)
    word = struct.unpack_from("<I", decoded, cm["record_offset"] + 0x18)[0]
    rgb = ((word >> 16) & 255, (word >> 8) & 255, word & 255)
    return [rgb], rgb


SURFACED_CONSTANTS = (struct.pack("<4f", *UV_CONSTANT), struct.pack("<4f", *UV_CONSTANT_QUAD))


def surfaced(decoded, rec):
    """True when this field already carries the modern surface (its colour shape has the widened UV constant)."""
    shape = _shape(rec, COLOUR_SHAPE)
    return bytes(decoded[shape["record_offset"] + 0x30:shape["record_offset"] + 0x40]) in SURFACED_CONSTANTS


def _texture_row_at(rec, record_offset):
    for t in rec["embedded_textures"]:
        if int(t["descriptor_offset"]) == record_offset:
            return t
    raise ModernSurfacesError("texture record not found")


def paint_field(decoded, rec, system, *, look, cls, rig, colour_settings=None, tint=(255, 255, 255), cap=256,
                detail=2, target=None):
    """The modern surface on one decoded field scene (sizes and layout kept). Returns (decoded, receipt).

    Idempotent: a field this function already painted comes out byte-identical (the end zones were recoloured on the
    first pass; a writer that composes this painter calls it after its own end-zone art)."""
    ml = _ml()
    out = bytearray(decoded)
    rows = _texture_rows(rec)
    receipt = dict(look=look, light=cls, rig=rig)
    target = tuple(target or target_rgb(look, cls))
    layout = field_layout(out, rec)
    response = field_response(look, cls, layout)
    vertex = _grass_vertex_tint(out, rec)
    mean = solve_map_mean(look, cls, rig, colour_settings=colour_settings, tint=tint, vertex=vertex, response=response,
                          target=target)
    receipt.update(target=[round(v, 2) for v in target], layout=layout, response=response,
                   map_mean=[round(v, 2) for v in mean])
    again = surfaced(out, rec)
    samples, old_mean = (None, None) if again else _current_turf(out, rec, system)
    outside_mean = solve_outside_mean(look, cls, rig, colour_settings=colour_settings, tint=tint,
                                      vertex=_outside_vertex_tint(out, rec), target=target)
    receipt["outside_mean"] = [round(v, 2) for v in outside_mean]
    outside_word = tuple(int(round(min(255, max(0, v)))) for v in outside_mean)
    if borrowed(out, rec) or COLOUR_MATERIAL not in rows:
        # the colour material has no texture of its own: it borrows the outside grass's; a plain colour stays there
        if borrowed(out, rec):
            row = _texture_row_at(rec, _rel(out, _material(rec, COLOUR_MATERIAL)["record_offset"] + 0x30))
        else:
            row = _borrow_outside_texture(out, rec, outside_word)
        om = _material(rec, OUTSIDE_MATERIAL)
        r, g, b = outside_word
        struct.pack_into("<I", out, om["record_offset"] + 0x18, 0xFF000000 | (r << 16) | (g << 8) | b)
        receipt["outside"] = "plain colour"
        receipt["colour_map"] = f"borrowed {row['width']}x{row['height']}"
    else:
        row = rows[COLOUR_MATERIAL]
        receipt["colour_map"] = f"{row['width']}x{row['height']}"
        if OUTSIDE_MATERIAL in rows:
            orow = rows[OUTSIDE_MATERIAL]
            ml.write_p8(out, system, orow, outside_rgba(look, cls, outside_mean, (int(orow["width"]), int(orow["height"])),
                                                        detail), maximum=cap)
            receipt["outside"] = "texture"
    width, height = int(row["width"]), int(row["height"])
    ml.write_p8(out, system, row, colour_map_rgba(look, cls, mean, size=(width, height), detail=detail, layout=layout),
                maximum=cap)
    receipt["pattern_detail"] = detail
    receipt["uv_vertices"] = remap_uvs(out, rec, layout=layout, size=(width, height))
    if samples:
        env = turf_envelope(samples)
        new_mean = tuple(min(255.0, v) for v in mean)
        done, changed = set(), 0
        for name in END_ZONE_MATERIALS:
            erow = rows.get(name)
            if erow is None:
                continue
            at = system + int(erow["palette_offset"])
            if at in done:
                continue
            done.add(at)
            new_pal, n = recolour_end_zone_palette(bytes(out[at:at + 1024]), env, old_mean, new_mean)
            out[at:at + 1024] = new_pal
            changed += n
        receipt["end_zone_entries"] = changed
    return bytes(out), receipt


# --- the bundle -------------------------------------------------------------------------------------------------------
def detail_video(kind, *, tiled=False):
    """The detail_normal TXTR's video bytes (six swizzled mip levels, then the BGRA palette) for one detail kind; tiled
    repeats the 64 x 64 variant (8 x 4 at mip 0) so a compressed chunk can hold it."""
    import numpy as np
    tx, HEADER = _tools()
    if tiled:
        tiles, palette = detail_tile_art(kind)
        levels = []
        for k in range(6):
            n = 64 >> k
            level = np.zeros((256 >> k, 512 >> k), np.uint8)
            for by, row in enumerate(TILE_GRID):
                for bx, t in enumerate(row):
                    level[by * n:(by + 1) * n, bx * n:(bx + 1) * n] = tiles[t][k]
            levels.append(level)
    else:
        levels, palette = detail_art(kind)
    out = b"".join(tx.swizzle_2d(np.ascontiguousarray(lv).tobytes(), lv.shape[1], lv.shape[0], 1) for lv in levels)
    return out + palette


def flattened_palette(palette, residual=0.45):
    """The retail detail palette with every normal's tilt scaled toward flat (the fallback for a compressed chunk
    that cannot take new indices): the retail white noise at a finer, gentler grain."""
    out = bytearray(palette)
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        x, y = (r / 127.5 - 1.0) * residual, (g / 127.5 - 1.0) * residual
        z = math.sqrt(max(0.0, 1.0 - x * x - y * y))
        enc = lambda c: min(255, max(0, round((c + 1.0) * 127.5)))
        out[i * 4:i * 4 + 4] = bytes((enc(z), enc(y), enc(x), a))
    return bytes(out)


def _chunk_span(data, chunk):
    tx, HEADER = _tools()
    return chunk.offset, HEADER.size + chunk.stored_size


def bundle_sites(data):
    """{kind: (offset, size)} of the sites this option writes in one bundle: the field span, the detail normal span,
    the divots span (grass-word venues) and the Fldd word block (words 1 and 2)."""
    tx, HEADER = _tools()
    chunks = tx.parse_chunks(data, allow_trailing=True)
    require(chunks and chunks[0].kind == "SCNE" and chunks[0].index == 0, "bundle does not start with the field scene")
    sites = {"field": _chunk_span(data, chunks[0])}
    for chunk in chunks:
        if chunk.kind == "TXTR":
            output, _ = tx.decode_chunk(data, chunk)
            info = tx.parse_texture(output, chunk)
            if info.name == NORMAL_NAME:
                require(info.format_name == "P8" and (info.width, info.height, info.mip_levels) == (512, 256, 6),
                        "detail_normal is not the 512 x 256 P8 texture")
                sites["normal"] = _chunk_span(data, chunk)
            elif info.name == DIVOTS_NAME and info.format_name == "P8":
                sites["divots"] = _chunk_span(data, chunk)
        elif chunk.kind == "Fldd":
            sites["fldd"] = (_fldd_words(data, chunk), 12)
    require({"field", "normal", "fldd"} <= set(sites), "bundle lacks its field, detail_normal or Fldd")
    return sites


def _encode_repeats(decoded, tag, bits, distances):
    """VC-LZ stream (greedy, fixed candidate distances) for data built of repeated tiles: the general encoders walk
    very long hash chains on such input (minutes); the tiles repeat at known Morton-block distances."""
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_vc_lz_fill as fill  # noqa: E402
    max_len = 3 + (1 << (16 - bits)) - 1
    max_dist = (1 << bits) - 1
    data = bytes(decoded)
    n = len(data)
    tokens = []
    i = 0
    usable = [d for d in distances if 0 < d <= max_dist]
    while i < n:
        best_len, best_d = 0, 0
        for d in usable:
            if d > i:
                continue
            k = 0
            # the game copies a match BACKWARDS (default.xbe 0x004DC00), so a match may not overlap its own output:
            # a length above the distance would read bytes the copy has not written yet
            limit = min(max_len, n - i, d)
            while k < limit and data[i + k] == data[i + k - d]:
                k += 1
            if k > best_len:
                best_len, best_d = k, d
                if k == max_len:
                    break
        if best_len >= 3:
            tokens.append(("M", best_d, best_len))
            i += best_len
        else:
            tokens.append(("L", data[i]))
            i += 1
    return fill.serialize(n, tag, bits, tokens)


def _fit_encoded(span, decoded, encoded):
    """Place a ready VC-LZ stream in a fixed span with the retail wrapper (trailing or front fill, scratch kept)."""
    from . import nfl2k5_modern_color as colour
    tx, HEADER = _tools()
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_vc_lz_fill as fill  # noqa: E402
    fields = HEADER.unpack_from(span)
    stored, scratch = fields[1], fields[5]
    require(len(encoded) <= stored, "the stream exceeds its span")
    for filler in (lambda e: fill.fill_stream(e, decoded, stored, slack=min(scratch, 16))[0],
                   lambda e: colour._early_fill(e, decoded, stored)):
        try:
            filled = filler(encoded) if stored - len(encoded) > scratch else encoded
        except tx.TxtrError:
            continue
        padding = stored - len(filled)
        alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
        if padding <= scratch and alias <= scratch:
            rebuilt = span[:HEADER.size] + filled + bytes(padding)
            back, info = tx.decompress_vc_lz(rebuilt[HEADER.size:], len(decoded))
            require(back == decoded and info.consumed_bytes == len(filled), "rebuilt stream failed its decode check")
            return rebuilt
    raise ModernSurfacesError("the stream cannot keep the retail scratch word")


def normal_span(span, kind, *, preserve_full=False):
    """(detail_normal chunk with this kind's normals, variant): the same size, wrapper and descriptor. A raw chunk takes
    the full art; a compressed chunk (s11, s15) takes the tiled art refit inside its span, or, if that misses, its
    retail indices with a flattened palette."""
    tx, HEADER = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    output, info0 = tx.decode_chunk(span, chunk)
    info = tx.parse_texture(output, chunk)
    require(info.name == NORMAL_NAME and info.format_name == "P8" and (info.width, info.height, info.mip_levels)
            == (512, 256, 6) and info.pixel_offset == 0, "detail_normal is not the 512 x 256 P8 texture")
    body = chunk.system_bytes
    if info0 is None:
        video = detail_video(kind)
        require(len(video) == chunk.video_bytes and len(span) == HEADER.size + body + len(video),
                "detail_normal size differs")
        return span[:HEADER.size + body] + video, "full"
    if preserve_full:
        require(output == bytes(output[:body]) + detail_video(kind),
                "the selected field allocation needs its exact full-resolution normal")
        return bytes(span), "full"
    from . import nfl2k5_modern_color as colour
    fields = HEADER.unpack_from(span)
    prefix = span[HEADER.size:HEADER.size + 9]
    _declared, tag = struct.unpack_from("<II", prefix)
    bits = prefix[8]
    tiled = bytes(output[:body]) + detail_video(kind, tiled=True)
    require(len(tiled) == len(output), "detail_normal size differs")
    try:
        # a block repeats the one three blocks back in swizzled order (TILE_GRID) at every mip
        rebuilt = _fit_encoded(span, tiled, _encode_repeats(tiled, tag, bits, TILED_DISTANCES))
        return rebuilt, "tiled"
    except (ModernSurfacesError, tx.TxtrError):
        pass
    pal_at = body + info.palette_offset
    flat = bytearray(output)
    flat[pal_at:pal_at + 1024] = flattened_palette(bytes(output[pal_at:pal_at + 1024]))
    flat = bytes(flat)
    if flat == output:
        return bytes(span), "retail indices, flattened palette"
    try:
        rebuilt, _fit = colour.fit_fixed_span(span, flat)
    except tx.TxtrError:
        rebuilt = None
    if rebuilt is not None:
        check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        require(check == flat and len(rebuilt) == len(span), "detail_normal refit read-back differs")
        return rebuilt, "retail indices, flattened palette"
    raise ModernSurfacesError("the detail_normal does not fit its span")


def divots_span(span, family, grass_mean=None):
    """Divots on synthetic turf vanish (every palette alpha 0); on grass their greens follow the new grass."""
    tx, HEADER = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    output, info0 = tx.decode_chunk(span, chunk)
    info = tx.parse_texture(output, chunk)
    edited = bytearray(output)
    at = chunk.system_bytes + info.palette_offset
    pal = bytearray(output[at:at + 1024])
    for i in range(256):
        b, g, r, a = pal[i * 4:i * 4 + 4]
        if family == "synthetic":
            pal[i * 4 + 3] = 0
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if 60 <= h * 360 <= 160 and s > 0.15 and grass_mean is not None:
            luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            gl = max(1e-6, (0.299 * grass_mean[0] + 0.587 * grass_mean[1] + 0.114 * grass_mean[2]) / 255.0)
            k = min(1.6, luma / gl) * 0.92
            pal[i * 4:i * 4 + 3] = bytes(int(min(255, max(0, round(c * k)))) for c in (grass_mean[2], grass_mean[1], grass_mean[0]))
    edited[at:at + 1024] = pal
    if bytes(edited) == output:
        return bytes(span)
    if info0 is None:
        return span[:HEADER.size] + bytes(edited) + span[HEADER.size + len(output):]
    from . import nfl2k5_modern_color as colour
    rebuilt, _fit = colour.fit_fixed_span(span, bytes(edited))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(edited), "divots refit read-back differs")
    return rebuilt


#: (pattern detail, palette cap) tried in order until the field fits its span
FIT_LADDER = ((2, 256), (2, 64), (1, 64), (1, 32), (0, 32))


def _fit(span, decoded, *, optimal):
    """Recompress into the fixed span with the whole retail wrapper (the loader scratch word included): the greedy
    encoder (and, when ``optimal``, the optimal parser), each with a full trailing fill, a trailing fill that stops up
    to 16 bytes short, or a front fill (Modern MetLife's and Modern colour's proven fills, in one pass)."""
    from . import nfl2k5_modern_color as colour
    tx, HEADER = _tools()
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
    encoders = [("greedy", lambda: tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, max_encoded_size=stored,
                                                     verify_roundtrip=False)[0])]
    if optimal:
        encoders.append(("optimal", lambda: fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits)))
    fills = (("trailing-full", lambda e: fill.fill_stream(e, decoded, stored, slack=0)[0]),
             ("trailing", lambda e: fill.fill_stream(e, decoded, stored, slack=min(scratch, 16))[0]),
             ("front", lambda e: colour._early_fill(e, decoded, stored)))
    attempts = []
    for name, encode in encoders:
        try:
            encoded = encode()
        except tx.TxtrError as exc:
            attempts.append(f"{name}: {exc}")
            continue
        if len(encoded) > stored:
            attempts.append(f"{name}: {len(encoded)} bytes exceeds {stored}")
            continue
        for fill_name, filler in fills:
            try:
                filled = filler(encoded) if len(encoded) < stored else encoded
            except tx.TxtrError as exc:
                attempts.append(f"{name}/{fill_name}: {exc}")
                continue
            padding = stored - len(filled)
            alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
            if padding <= scratch and alias <= scratch:
                rebuilt = span[:HEADER.size] + filled + bytes(padding)
                back, info = tx.decompress_vc_lz(rebuilt[HEADER.size:], len(decoded))
                require(back == decoded and info.consumed_bytes == len(filled), "rebuilt stream failed its decode check")
                return rebuilt, dict(encoder=name, fill=fill_name, padding_bytes=padding)
            attempts.append(f"{name}/{fill_name}: padding {padding}, needs {alias}, retail {scratch}")
    raise tx.TxtrError("; ".join(attempts))


def field_span(span, *, look, cls, rig, colour_settings=None, tint=(255, 255, 255), target=None,
               full_detail=False):
    """(new field span of the same size, receipt): paint, then refit inside the fixed VC-LZ span with the retail
    wrapper, stepping the pattern detail and the palette down (FIT_LADDER) when a span misses."""
    ml = _ml()
    tx, HEADER = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    rec, decoded = ml._scene(span, chunk)
    require(rec["name"] == FIELD_SCENE, "the first bundle scene is not the field")
    attempts = []
    # the greedy encoder over the whole ladder first (seconds); the optimal parser (minutes) only if none fits
    for optimal in (False, True):
        for detail, cap in (((2, 256),) if full_detail else FIT_LADDER):
            painted, receipt = paint_field(decoded, rec, chunk.system_bytes, look=look, cls=cls, rig=rig,
                                           colour_settings=colour_settings, tint=tint, cap=cap, detail=detail,
                                           target=target)
            if painted == decoded:
                return bytes(span), dict(receipt, refit=False, palette_cap=cap)
            try:
                rebuilt, fit = _fit(span, painted, optimal=optimal)
            except (tx.TxtrError, ValueError) as exc:
                attempts.append(f"detail {detail}, {cap} colours{' (optimal)' if optimal else ''}: {str(exc)[:120]}")
                continue
            back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
            require(back == painted and len(rebuilt) == len(span) and rebuilt[:HEADER.size] == span[:HEADER.size],
                    "field refit read-back differs")
            return rebuilt, dict(receipt, refit=True, palette_cap=cap, attempts=len(attempts), **fit)
    raise ModernSurfacesError("the field does not fit its span: " + " | ".join(attempts))


def _span_surfaced(span):
    ml = _ml()
    tx, HEADER = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    rec, decoded = ml._scene(span, chunk)
    return surfaced(decoded, rec)


def surface_bundle(data, name, *, indoor, colour_settings=None, overrides=None,
                   preserve_full_normal=False, full_detail=False, field_normal_loan=False):
    """(new bundle bytes of the same size, receipt) for one home-venue bundle as it stands (retail, graded, or
    written by a stadium option)."""
    prefix, t, _w = bundle_parts(name)
    require(type(preserve_full_normal) is bool and type(full_detail) is bool,
            "surface allocation options must be booleans")
    require(type(field_normal_loan) is bool, "field normal allocation option must be a boolean")
    require(not field_normal_loan or prefix == "s29", "field normal allocation is reviewed only for WAS")
    if preserve_full_normal or full_detail:
        from . import nfl2k5_split_endzone_art as endzone_art
        require(prefix in endzone_art.LOAN_VENUES, "full surface allocation is not reviewed for " + prefix)
    look = venue_look(prefix, overrides)
    family = LOOKS[look]["family"]
    cls = light_class(name, indoor)
    rig = rig_name(cls, t)
    sites = bundle_sites(data)
    out = bytearray(data)
    tint = field_tint(data)
    at, size = sites["field"]
    again = _span_surfaced(bytes(data[at:at + size]))
    field_args = dict(full_detail=True) if full_detail else {}
    loan_receipt = None
    if field_normal_loan:
        from . import nfl2k5_midfield_art as midfield
        normal_at, normal_size = sites["normal"]
        new_normal, normal_variant = normal_span(bytes(data[normal_at:normal_at + normal_size]), LOOKS[look]["detail"])
        require(normal_variant == "full", "WAS allocation donor must be the ordinary full-resolution normal")
        def painter(span):
            from . import nfl2k5_modern_color as colour
            ml = _ml()
            chunk = _tools()[0].parse_chunks(span, allow_trailing=True)[0]
            rec, decoded = ml._scene(span, chunk)
            painted, receipt = paint_field(decoded, rec, chunk.system_bytes, look=look, cls=cls, rig=rig,
                                            colour_settings=colour_settings, tint=tint, cap=256, detail=2,
                                            target=venue_target(prefix, look, cls))
            after, fit = colour.fit_fixed_span(span, painted)
            return after, dict(receipt, refit=True, palette_cap=256, **fit)
        rebuilt, loan_receipt = midfield.refit_washington_field(data, name, painter, normal_span=new_normal)
        out = bytearray(rebuilt)
        frec = loan_receipt["paint"]
    else:
        new_field, frec = field_span(bytes(data[at:at + size]), look=look, cls=cls, rig=rig,
                                     colour_settings=colour_settings, tint=tint, target=venue_target(prefix, look, cls),
                                     **field_args)
        out[at:at + size] = new_field
        at, size = sites["normal"]
        normal_args = dict(preserve_full=True) if preserve_full_normal else {}
        new_normal, normal_variant = normal_span(bytes(data[at:at + size]), LOOKS[look]["detail"], **normal_args)
        out[at:at + size] = new_normal
    if "divots" in sites and (not again or preserve_full_normal):
        at, size = sites["divots"]
        grass_mean = [v * (tt / 255.0) for v, tt in zip(frec["map_mean"], tint)]
        out[at:at + size] = divots_span(bytes(data[at:at + size]), family, grass_mean)
    if family == "synthetic":
        at, _size = sites["fldd"]
        struct.pack_into("<I", out, at + 4, SYNTHETIC_WEAR)
    require(len(out) == len(data), f"{name}: bundle changed size")
    edits = []
    if loan_receipt is not None:
        end = loan_receipt["scope_size"]
        edits.append(dict(kind="field_detail_prefix", offset=0, size=end,
                          before=sha(data[:end]), after=sha(bytes(out[:end]))))
    for kind, (at, size) in sorted(sites.items()):
        if loan_receipt is not None and kind in {"field", "normal"}:
            continue
        before, after = bytes(data[at:at + size]), bytes(out[at:at + size])
        if before != after:
            edits.append(dict(kind=kind, offset=at, size=size, before=sha(before), after=sha(after)))
    receipt = dict(name=name, look=look, family=family, light=cls, rig=rig, field=frec, normal=normal_variant, edits=edits)
    if loan_receipt is not None:
        receipt["field_normal_loan"] = loan_receipt
    return bytes(out), receipt


# --- disc images -----------------------------------------------------------------------------------------------------
HOME_BUNDLES = tuple(f"{p}{c}.iff" for p in HOME_PREFIXES for c in CODES)


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def home_entries(archive):
    """{bundle name: archive entry} for the 288 home-venue bundles, found by the engine's name id."""
    ml = _ml()
    ids = {ml.name_id(name): name for name in HOME_BUNDLES}
    out = {}
    for entry in archive.entries:
        name = ids.get(entry.name_id)
        if name is not None:
            require(name not in out, f"{name} appears twice in the archive")
            out[name] = entry
    return out


def indoor_flags(archive):
    """{venue prefix: True when its ROST stadium row is indoor (+0x18)}, read from the image's own main ROST (SoFi's
    rows are roofed on a SoFi build, so its bundles take the dome light)."""
    from . import nfl2k5_roster_records as rr
    ml = _ml()
    entry = archive.entries[ROST_OUTER_INDEX]
    body = archive.read(entry.virtual_offset, entry.size)[rr.RESOURCE_HEADER_SIZE:]
    out = {}
    for offset, fields in ml._stadium_records(bytes(body)):
        code = fields["asset_code"][1]
        if code in HOME_PREFIXES:
            out[code] = bool(struct.unpack_from("<I", body, offset + 0x18)[0])
    require(set(out) == set(HOME_PREFIXES), "the main ROST does not name every home venue")
    return out


def receipt_path(source):
    return Path(str(source) + ".surfaces.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    require(path.stat().st_size <= 4 * 1024 * 1024, "the Modern surfaces receipt is too large")
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(doc, dict) and doc.get("schema") == RECEIPT_SCHEMA, "unsupported Modern surfaces receipt")
    return doc


def _save_json(path, doc):
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write((json.dumps(doc, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_receipt(target, receipt):
    """Write this option's receipt beside ``target`` (the build publishes it with the disc, like the colour and venue
    receipts)."""
    _save_json(receipt_path(target), receipt)


@lru_cache(maxsize=1)
def _detail_by_hash():
    """Recognize written normals using the release pins, without compiling art.

    Source inspection runs for plain builds too. Generating every normal here
    required NumPy just to read a retail disc and did unnecessary image work.
    The art tests independently compare generated bytes with these same pins.
    """
    out = {digest: tuple(row) for digest, row in LEGACY_DETAIL_SHA256.items()}
    details = pins()["details"]
    for kind in sorted({look["detail"] for look in LOOKS.values()}):
        for variant in ("full", "tiled"):
            out[details[kind][variant]] = (kind, variant)
    return out


@lru_cache(maxsize=1)
def _retail_sites():
    """{bundle name: {site kind: retail SHA-256}} from the pins (the retail extraction the option was pinned on)."""
    try:
        return {row["name"]: {k: v["retail"] for k, v in row["sites"].items()} for row in pins()["bundles"]}
    except (ModernSurfacesError, OSError, ValueError, KeyError):
        return {}


def _utf16z(buf, at, limit=256):
    end = at
    while end + 1 < len(buf) and end - at < 2 * limit and buf[end:end + 2] != b"\0\0":
        end += 2
    return bytes(buf[at:end]).decode("utf-16le", "replace")


def field_uv_constant(span):
    """The colour shape's UV constant (16 bytes) of a field SCNE span: decoded and walked without the full scene
    parse (a tenth of a second), for the deep status."""
    tx, HEADER = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    desc = _rel(decoded, 0x14)
    require(desc is not None, "field descriptor missing")
    count = struct.unpack_from("<I", decoded, desc + 0x2C)[0]
    first = _rel(decoded, desc + 0x30)
    require(first is not None and 0 < count < 64, "field shape table missing")
    for i in range(count):
        at = first + i * 0x100
        name_at = _rel(decoded, at + 0x40)
        if name_at is not None and _utf16z(decoded, name_at) == COLOUR_SHAPE:
            return bytes(decoded[at + 0x30:at + 0x40])
    raise ModernSurfacesError("the field has no colour shape")


def _normal_state(name, data):
    """('ours', kind, variant) / ('retail', None, None) / ('other', None, None) for a bundle's detail normal."""
    tx, HEADER = _tools()
    at, size = bundle_sites(data)["normal"]
    span = bytes(data[at:at + size])
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    if chunk.compression_magic == 0:
        video = span[HEADER.size + chunk.system_bytes:]
    else:
        decoded, _ = tx.decode_chunk(span, chunk)
        video = decoded[chunk.system_bytes:]
    hit = _detail_by_hash().get(sha(video))
    if hit is not None:
        return ("ours",) + hit
    if _retail_sites().get(name, {}).get("normal") == sha(span):
        return ("retail", None, None)
    return ("other", None, None)


def bundle_report(archive, name, entry, receipt, *, deep=False):
    """{state, reason} for one home bundle.

    applied: the bundle matches this option's receipt, or (no receipt, or bytes changed after this option by another
    writer: end zones, logos, the stadium) it still carries this option's detail normal, and with ``deep`` its field
    still carries the planar colour UVs. retail: not surfaced, whatever other writers did to it (no receipt row and a
    detail normal that is not this option's). foreign: the receipt names it but this option's signature is gone, or
    the bundle cannot be read."""
    rows = (receipt or {}).get("bundles") or {}
    row = rows.get(name)
    data = archive.read(entry.virtual_offset, entry.size)
    if row is not None and sha(data) == row.get("applied_sha256"):
        return dict(state="applied", reason="receipt")
    try:
        normal, kind, variant = _normal_state(name, data)
    except (ModernSurfacesError, ValueError, KeyError, IndexError, struct.error) as exc:
        return dict(state="foreign", reason=f"unreadable bundle: {exc}")
    if normal == "ours":
        if row is None:
            why = "no receipt row"
        else:
            changed = sorted({e["kind"] for e in row.get("edits", ())
                              if sha(bytes(data[e["offset"]:e["offset"] + e["size"]])) != e["after"]})
            why = ("changed after this option in " + ", ".join(changed)) if changed else "changed after this option outside its sites"
        if deep:
            try:
                at, size = bundle_sites(data)["field"]
                surfaced_field = field_uv_constant(bytes(data[at:at + size])) in SURFACED_CONSTANTS
            except (ModernSurfacesError, ValueError, KeyError, IndexError, struct.error) as exc:
                return dict(state="foreign", reason=f"detail {kind} ({variant}) but the field is unreadable: {exc}")
            if not surfaced_field:
                return dict(state="foreign", reason=f"detail {kind} ({variant}) but the field lost the planar colour UVs ({why})")
            return dict(state="applied", reason=f"signature: detail {kind} ({variant}) and planar field UVs ({why})")
        return dict(state="applied", reason=f"signature: detail {kind} ({variant}) ({why})")
    # Not this option's detail normal. Without a receipt row that is "retail" for this option (not surfaced), whoever
    # else wrote the bundle: Modern colour flattens every detail normal's palette and SoFi copies its turf normal into
    # s24, and those bundles are exactly what this step starts from (lab 2, 2026-09-25: reading them as foreign made
    # the build step refuse its own input).
    if row is not None:
        return dict(state="foreign", reason=f"the receipt names it but its detail normal is {normal} (not this option's)")
    if normal == "retail":
        return dict(state="retail", reason="not surfaced (retail detail normal)")
    return dict(state="retail", reason="not surfaced (another writer's detail normal, for example Modern colour's)")


def image_report(source, *, deep=False):
    """{state, counts, bundles: {name: {state, reason}}} across the 288 home bundles."""
    receipt = read_receipt(source)
    out = {}
    with _outer_image()(str(source)) as archive:
        entries = home_entries(archive)
        for name in HOME_BUNDLES:
            if name not in entries:
                out[name] = dict(state="foreign", reason="missing from the archive")
                continue
            out[name] = bundle_report(archive, name, entries[name], receipt, deep=deep)
    states = {row["state"] for row in out.values()}
    state = "applied" if states == {"applied"} else "retail" if states == {"retail"} else "foreign"
    counts = {}
    for row in out.values():
        key = f"{row['state']}: {row['reason'].split(' (')[0]}"
        counts[key] = counts.get(key, 0) + 1
    return dict(state=state, receipt=receipt is not None, deep=deep, counts=dict(sorted(counts.items())), bundles=out)


def image_status(source, *, deep=False):
    """retail / applied / foreign across the 288 home bundles (see bundle_report)."""
    return image_report(source, deep=deep)["state"]


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    require(state == ("applied" if enabled else "retail"), "the home-venue surfaces do not match the requested option")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def check_request(source):
    """Preflight on the disc the build starts from: every home bundle present and not already surfaced."""
    state = image_status(source)
    require(state == "retail", "This disc already carries modern playing surfaces (or unknown field bytes). "
                               "Choose the original retail disc as the source.")
    return state


def _job(args):
    """Worker: (name, bundle bytes, indoor, colour settings, overrides) -> (name, new bytes, receipt)."""
    name, data, indoor, settings, overrides, *selected = args
    options = dict(preserve_full_normal=True, full_detail=True) if selected and selected[0] else {}
    if len(selected) > 1 and selected[1]:
        options["field_normal_loan"] = True
    out, rec = surface_bundle(data, name, indoor=indoor, colour_settings=settings, overrides=overrides, **options)
    return name, out, rec


def _workers(requested=None):
    return requested or max(1, min(8, (os.cpu_count() or 2) - 1))


def _update_colour_receipt(colour_receipt, name, after):
    """Keep Modern colour's receipt (and the MetLife and Arrowhead rows it carries) describing this bundle's bytes."""
    rows = colour_receipt.get("bundle_pins") or {}
    if name in rows:
        row = rows[name]
        rows[name] = dict(row, applied_sha256=sha(after), sites=[dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]]))
                                                                 for site in row.get("sites", [])])
    for key in ("modern_metlife", "modern_arrowhead"):
        combined = colour_receipt.get(key)
        if isinstance(combined, dict) and name in (combined.get("bundles") or {}):
            row = combined["bundles"][name]
            combined["bundles"][name] = dict(row, applied_sha256=sha(after), sites=[
                dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row.get("sites", [])])


def apply_to_image(target, *, progress=None, workers=None, overrides=None, preserve_full_normal_prefixes=(),
                   field_normal_loan_prefixes=()):
    """Build step (after every stadium writer): the modern surface in all 288 home-venue bundles of a DISPOSABLE
    output image, written in place (same sizes), with read-back; the colour and 2026 venue receipts are updated so
    those options still read applied, and this option's receipt is written beside the image."""
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_split_endzone_art as endzone_art
    selected = frozenset(preserve_full_normal_prefixes)
    require(selected <= endzone_art.LOAN_VENUES, "full surface allocation includes an unreviewed venue")
    loan_selected = frozenset(field_normal_loan_prefixes)
    require(loan_selected <= {"s29"}, "field normal allocation includes an unreviewed venue")
    say = progress or (lambda message, done, total: None)
    before_report = image_report(target)
    allowed_prepass = bool(selected) and all(row["state"] == "retail" or
                         (name[:3] in selected and row["state"] == "applied")
                         for name, row in before_report["bundles"].items())
    require(before_report["state"] == "retail" or allowed_prepass,
            "the home-venue bundles are not all unsurfaced before this step: "
            + "; ".join(f"{count} {key}" for key, count in before_report["counts"].items()))
    try:
        colour_receipt = colour.read_image_receipt(target)
    except (OSError, ValueError):
        colour_receipt = None
    settings = colour_receipt.get("settings") if colour_receipt else None
    colour_before = colour.image_status(target, receipt=colour_receipt) if colour_receipt else None
    from . import nfl2k5_modern_venues_2026 as venues26
    venues_receipt = venues26.read_receipt(target)
    jobs, before = [], {}
    with _outer_image()(str(target)) as archive:
        entries = home_entries(archive)
        require(set(entries) == set(HOME_BUNDLES), "the image lacks home-venue bundles")
        indoor = indoor_flags(archive)
        for name in HOME_BUNDLES:
            data = archive.read(entries[name].virtual_offset, entries[name].size)
            before[name] = (entries[name].virtual_offset, sha(data))
            args = (name, data, indoor[name[:3]], settings, overrides)
            jobs.append(args + (name[:3] in selected, True) if name[:3] in loan_selected
                        else args + (True,) if name[:3] in selected else args)
    say(f"Modern surfaces: {len(jobs)} home-venue bundles", 0, len(jobs))
    results = {}
    count = _workers(workers)
    if count > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=count) as pool:
            for index, (name, out, rec) in enumerate(pool.map(_job, jobs, chunksize=1)):
                results[name] = (out, rec)
                say(f"Modern surfaces: {index + 1} of {len(jobs)} bundles", index + 1, len(jobs))
    else:
        for index, job in enumerate(jobs):
            name, out, rec = _job(job)
            results[name] = (out, rec)
            say(f"Modern surfaces: {index + 1} of {len(jobs)} bundles", index + 1, len(jobs))
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False, revision=TRANSFORM_REVISION,
                   overrides=overrides or {}, colour=settings is not None, bundles={})
    if selected:
        receipt["preserve_full_normal_prefixes"] = sorted(selected)
    if loan_selected:
        receipt["field_normal_loan_prefixes"] = sorted(loan_selected)
    with _outer_image()(str(target), writable=True) as archive:
        for name in HOME_BUNDLES:
            out, rec = results[name]
            at, before_hash = before[name]
            data_now = archive.read(at, len(out))
            require(sha(data_now) == before_hash, f"{name}: the bundle changed while it was being surfaced")
            for edit in rec["edits"]:
                chunk = out[edit["offset"]:edit["offset"] + edit["size"]]
                require(archive.write(at + edit["offset"], chunk) == len(chunk), f"{name}: short write")
            require(archive.read(at, len(out)) == out, f"{name}: read-back differs")
            receipt["bundles"][name] = dict(look=rec["look"], light=rec["light"], rig=rec["rig"], normal=rec["normal"],
                                            before_sha256=before_hash, applied_sha256=sha(out),
                                            pattern_detail=rec["field"].get("pattern_detail"),
                                            palette_cap=rec["field"].get("palette_cap"),
                                            layout=rec["field"].get("layout"), response=rec["field"].get("response"),
                                            target=rec["field"].get("target"),
                                            edits=[{k: e[k] for k in ("kind", "offset", "size", "before", "after")}
                                                   for e in rec["edits"]])
            if colour_receipt is not None:
                _update_colour_receipt(colour_receipt, name, out)
            if venues_receipt is not None and name in (venues_receipt.get("bundles") or {}):
                venues_receipt["bundles"][name] = dict(venues_receipt["bundles"][name], applied_sha256=sha(out))
    if colour_receipt is not None:
        colour_receipt["modern_surfaces"] = dict(bundles=sorted(receipt["bundles"]))
        after_state = colour.image_status(target, receipt=colour_receipt)
        require(after_state == colour_before, f"the colour read-back failed after Modern surfaces ({after_state})")
        colour._save_image_receipt(target, colour_receipt)
    if venues_receipt is not None:
        _save_json(venues26.receipt_path(target), venues_receipt)
        venue_report = venues26.image_report(target)
        require(venue_report["state"] in ("applied", "retail"),
                "the 2026 venue read-back failed after Modern surfaces: " + venues26.readback_details(venue_report))
    save_receipt(target, receipt)
    require(image_status(target) == "applied", "the Modern surfaces read-back failed")
    looks = {}
    for row in receipt["bundles"].values():
        looks[row["look"]] = looks.get(row["look"], 0) + 1
    return dict(state="applied", label=LABEL, runtime_witnessed=False, bundles=len(receipt["bundles"]), looks=looks,
                colour=settings is not None, detail_fallbacks=sorted(n for n, r in receipt["bundles"].items() if r["normal"] != "full"),
                reduced_patterns=sorted(n for n, r in receipt["bundles"].items() if (r.get("pattern_detail") or 2) < 2))


# --- pins (developer) -------------------------------------------------------------------------------------------------
def build_pins(source, *, progress=None):
    """Retail SHA-256 of every site this option writes in the 288 home bundles, plus the detail videos it ships."""
    say = progress or (lambda message, done, total: None)
    rows = []
    with _outer_image()(str(source)) as archive:
        entries = home_entries(archive)
        for index, name in enumerate(HOME_BUNDLES):
            entry = entries[name]
            data = archive.read(entry.virtual_offset, entry.size)
            sites = bundle_sites(data)
            rows.append(dict(name=name, outer=archive.entries.index(entry), name_id=entry.name_id, size=entry.size,
                             retail_sha256=sha(data), sites={k: dict(offset=v[0], size=v[1], retail=sha(data[v[0]:v[0] + v[1]]))
                                                             for k, v in sorted(sites.items())}))
            if index % 48 == 0:
                say(f"pins: {index + 1} of {len(HOME_BUNDLES)}", index + 1, len(HOME_BUNDLES))
    details = {kind: dict(full=sha(detail_video(kind)), tiled=sha(detail_video(kind, tiled=True)))
               for kind in sorted({look["detail"] for look in LOOKS.values()})}
    return dict(schema=PINS_SCHEMA, label=LABEL, revision=TRANSFORM_REVISION, uv_constant=list(UV_CONSTANT),
                uv_constant_quad=list(UV_CONSTANT_QUAD),
                details=details, bundles=rows)


_PINS = None


def pins():
    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "Modern surfaces pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Modern surfaces pins schema")
    return _PINS


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Modern playing surfaces for ESPN NFL 2K5 (experimental).")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status", help="retail / applied / foreign across the 288 home-venue bundles; the per-bundle "
                                      "counts and every bundle that is not applied are printed first, the state last")
    s.add_argument("image")
    s.add_argument("--deep", action="store_true", help="also decode each field and check its planar colour UVs")
    s.add_argument("--report", help="write the per-bundle report (JSON) here")
    a = sub.add_parser("apply", help="apply to a DISPOSABLE output image copy (never the retail source)")
    a.add_argument("image")
    a.add_argument("--workers", type=int, default=None)
    p = sub.add_parser("pins", help="developer: rebuild data/nfl2k5_modern_surfaces/pins.json from a retail image")
    p.add_argument("source")
    p.add_argument("--write", action="store_true")
    t = sub.add_parser("table", help="print the venue table")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            report = image_report(args.image, deep=args.deep)
            if args.report:
                Path(args.report).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            print(f"receipt beside the image: {'yes' if report['receipt'] else 'no'}; deep: {report['deep']}")
            for key, count in report["counts"].items():
                print(f"  {count:4d}  {key}")
            odd = [(n, r) for n, r in report["bundles"].items() if r["state"] != "applied"]
            for n, r in odd[:40]:
                print(f"  {n}: {r['state']} ({r['reason']})")
            if len(odd) > 40:
                print(f"  ... {len(odd) - 40} more (see --report)")
            print(report["state"])
        elif args.command == "apply":
            receipt = apply_to_image(args.image, progress=lambda m, d, t: print(m, flush=True) if d % 24 == 0 else None,
                                     workers=args.workers)
            print(json.dumps(receipt, indent=1, sort_keys=True))
        elif args.command == "pins":
            doc = build_pins(args.source, progress=lambda m, d, t: print(m, flush=True))
            text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
            if args.write:
                PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
                print("wrote", PINS_PATH, len(doc["bundles"]), "bundles")
            else:
                print(len(doc["bundles"]), "bundles")
        else:
            for prefix, row in sorted(venues().items()):
                print(prefix, row["team"], row["venue"], row["surface"], row["look"], row["product"], sep=" | ")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Modern surfaces: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
