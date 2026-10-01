"""The shared stadium environment kit (st3, 2026-09-28): real surroundings round every modern stadium, so no flyover or
exterior shot looks out over a void (Noah, 2026-09-28: "The stadiums need better environments outside of them so it
doesn't look like an endless void").

Each stadium calls ``dress`` with its venue record; the kit reads the venue's layout (data/nfl2k5_stadium_environment/
VENUE.json, built from OpenStreetMap and the Terrain Tiles elevation set by tools/nfl2k5_stadium_environment_osm.py) and
adds, outside the stadium's own keep-out polygons:

* the near ground from OpenStreetMap: the surface lots with their rows of parked cars (the stalls follow each lot's
  long axis), the roads with a dashed line between their lanes, the parks and grass, water, the trees (OSM's trees and
  tree rows, as crowns) and the buildings (boxes on each outline's minimum rectangle, walls with windows, lit at night);
* the far ground to the horizon: the venue's biome seen from the air, tinted by the land use round the site (the
  layout's class grid) and fading into the haze;
* the horizon band at BAND_RADIUS: the terrain's ridges at their true elevation angle and the tall buildings out to
  15 km, standing in the haze, clear sky above them.

Integration (one call and three hooks; the kit never changes a stadium's own helpers):

    from . import nfl2k5_stadium_environment as env
    # in the model's build():   env.dress(self, VENUE, grade=self.GRADE, keep_out=[plaza_ring], inner=plaza_ring)
    # MATERIALS:                MATERIALS.update(env.materials(VENUE))
    # _textures():              out.update(env.textures(VENUE, tod, weather))   (skip the env_ keys in the art loop)
    # light():                  if mat.startswith("env_"): return env.light(mat, P, N, tod, weather, VENUE)

Geometry is in metres (x across, y up, z along the field; the frame of every modern stadium module). Budgets are the
caller's: STYLE caps each venue's counts, and the stadium's own tests hold the bundles under retail.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path



class _LazyNumpy:
    # the Build panel imports the stadium modules (and so this one) for captions; the studios open without numpy
    def __getattr__(self, name):
        import numpy
        globals()["np"] = numpy
        return getattr(numpy, name)


np = _LazyNumpy()

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_stadium_environment"
ART_DIR = DATA_DIR / "art"
SCHEMA = "nfl2k5_stadium_environment_layout/v1"
#: the material render classes (SoFi's, PROVED OFFLINE on s23 and s24; copied here so SoFi can import the kit)
CLASS_OPAQUE = (0xD30E3557, True, 0x01)
CLASS_ALPHA = (0xBF4740BD, True, 0x03)

#: the horizon band's radius and rows (the art tool draws with the same numbers): MB's 1,900 m sky cylinder is PROVED IN
#: GAME visible (st, 2026-09-27), so the band stands inside it; a model with its own sky puts it at SKY_RADIUS
BAND_RADIUS, BAND_TOP, BAND_FOOT, HAZE_H = 1800.0, 240.0, 12.0, 10.0
#: the top eighth of every band texture stays clear and the cylinder's top edge maps to it: with wrap addressing and
#: bilinear filtering the top edge would otherwise blend in the haze of the last row (st2, 2026-09-28, in Blender), at
#: every mip down to the 8-row one
BAND_PAD = 0.125
SKY_RADIUS = 1900.0
#: the far ground fades into the haze from HAZE_START; from HAZE_END to the band it is the haze itself (white by vertex)
HAZE_START, HAZE_END = 950.0, 1550.0
#: the far ground's rings past the inner edge (metres from the centre)
FAR_RINGS = (420.0, 650.0, 950.0, 1250.0, HAZE_END)
#: road lane repeat along v (metres) and the lot tile (stalls across u, rows along v)
ROAD_REPEAT, LOT_U, LOT_V = 12.0, 16.2, 19.0

#: vertex budgets per part (a venue's STYLE overrides them; the stadium's own tests hold its bundles under retail)
BUDGET = dict(lots=600, grass=400, water=200, roads=1500, blocks=1200, trees=400)

#: per venue: the far ground's biome, the band texture's size, the haze family, the radii and the vertex budgets
STYLE = {
    "s00": dict(biome="dry", band_size=(256, 32), haze="dry", far_angles=28, tile=240.0, near=900.0, block_radius=600.0,
                roads_big=650.0, roads_minor=340.0, roads_service=170.0, far_roads=("motorway", "trunk"),
                water_min=2000.0, road_tol=2.5,
                budget=dict(lots=300, grass=110, water=80, roads=440, blocks=250, trees=144)),
    "s15": dict(biome="urban", band_size=(256, 32), haze="cool", far_angles=40, tile=240.0, near=900.0,
                block_radius=650.0, roads_big=900.0, roads_minor=520.0, roads_service=300.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=1.5, grass_min=900.0,
                budget=dict(lots=475, grass=500, water=280, roads=1700, blocks=1500, trees=480)),
    "s11": dict(biome="urban", band_size=(256, 32), haze="cool", far_angles=36, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=900.0, roads_minor=480.0, roads_service=280.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=1.5, grass_min=900.0,
                budget=dict(lots=330, grass=150, water=150, roads=620, blocks=560, trees=180)),
    # AT&T Stadium: its retail budget is spent (the night bundles already stood 2 KB over retail), so the lean set: a
    # 128-wide band, few blocks, the lots first (the biggest lots in the league)
    "s07": dict(biome="green", band_size=(128, 32), haze="cool", far_angles=22, band_columns=40, tile=240.0,
                near=800.0, block_radius=500.0, roads_big=600.0, roads_minor=300.0, roads_service=150.0,
                far_roads=("motorway", "trunk"), water_min=4000.0, road_tol=2.5, grass_min=1500.0,
                budget=dict(lots=200, grass=20, water=0, roads=180, blocks=84, trees=48)),
    # Levi's Stadium: office parks and lots by the creek, the hills beyond (a wide budget: 150 KB under retail)
    "s25": dict(biome="dry", band_size=(256, 32), haze="dry", far_angles=36, tile=240.0, near=900.0,
                block_radius=650.0, roads_big=900.0, roads_minor=450.0, roads_service=250.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=1.5, grass_min=900.0,
                budget=dict(lots=500, grass=500, water=250, roads=1500, blocks=2000, trees=900)),
    # Allegiant Stadium: the desert city by the Strip (the model draws the Strip's towers itself)
    "s20": dict(biome="dry", band_size=(256, 32), haze="dry", far_angles=32, tile=240.0, near=850.0,
                block_radius=600.0, roads_big=800.0, roads_minor=380.0, roads_service=200.0,
                far_roads=("motorway", "trunk"), water_min=4000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=500, grass=200, water=80, roads=1000, blocks=1000, trees=400)),
    # Highmark Stadium: Orchard Park's lots, farms and woods
    "s03": dict(biome="green", band_size=(256, 32), haze="cool", far_angles=32, tile=240.0, near=900.0,
                block_radius=650.0, roads_big=900.0, roads_minor=450.0, roads_service=250.0,
                far_roads=("motorway", "trunk", "primary"), water_min=3000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=380, grass=100, water=80, roads=600, blocks=420, trees=150)),
    # SoFi Stadium (s23 Chargers, s24 Rams, s40 Super Bowl LXI: one building, one layout): Inglewood's dense blocks,
    # the lots and Hollywood Park round the lake, Los Angeles' towers on the band
    "s23": dict(biome="urban", band_size=(256, 32), haze="dry", far_angles=28, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=800.0, roads_minor=400.0, roads_service=220.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=360, grass=150, water=20, roads=800, blocks=800, trees=240)),
    # st2's stadiums (st2 wires them in on job/b76-st4; the budgets are a start, st2 tunes them with st3)
    "s01": dict(biome="urban", band_size=(256, 32), haze="cool", far_angles=36, tile=240.0, near=900.0,
                block_radius=650.0, roads_big=900.0, roads_minor=450.0, roads_service=250.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=1.5, grass_min=900.0,
                budget=dict(lots=450, grass=250, water=100, roads=1400, blocks=1200, trees=300)),
    "s10": dict(biome="green", band_size=(256, 32), haze="cool", far_angles=32, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=900.0, roads_minor=450.0, roads_service=220.0,
                far_roads=("motorway", "trunk", "primary"), water_min=3000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=400, grass=120, water=100, roads=800, blocks=1200, trees=800)),
    "s12": dict(biome="urban", band_size=(256, 32), haze="cool", far_angles=32, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=900.0, roads_minor=450.0, roads_service=220.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=400, grass=120, water=260, roads=1100, blocks=600, trees=600)),
    "s14": dict(biome="green", band_size=(256, 32), haze="cool", far_angles=32, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=900.0, roads_minor=450.0, roads_service=220.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=400, grass=120, water=320, roads=800, blocks=900, trees=800)),
    "s16": dict(biome="green", band_size=(256, 32), haze="cool", far_angles=32, tile=240.0, near=900.0,
                block_radius=600.0, roads_big=900.0, roads_minor=450.0, roads_service=220.0,
                far_roads=("motorway", "trunk", "primary"), water_min=2000.0, road_tol=2.0, grass_min=1200.0,
                budget=dict(lots=600, grass=120, water=240, roads=700, blocks=500, trees=1200)),
}
#: MetLife Stadium (s18 Giants, s19 Jets): the Meadowlands' lots, marsh and highways, Manhattan on the band (512 wide)
STYLE["s18"] = dict(biome="green", band_size=(256, 32), haze="cool", far_angles=28, band_columns=40, tile=240.0,
                    near=900.0, block_radius=650.0, roads_big=900.0, roads_minor=400.0, roads_service=200.0,
                    far_roads=("motorway", "trunk"), water_min=3000.0, road_tol=2.5, grass_min=2000.0,
                    budget=dict(lots=260, grass=90, water=60, roads=300, blocks=0, trees=90))
STYLE["s19"] = dict(STYLE["s18"], layout="s18")
STYLE["s24"] = dict(STYLE["s23"], layout="s23")
#: the Super Bowl record's retail scene is SoFi's smallest (23 KB spare before the kit): the far ground, the band and
#: the nearest lots only
STYLE["s40"] = dict(STYLE["s23"], layout="s23", far_angles=24, band_columns=40,
                    budget=dict(lots=150, grass=0, water=0, roads=0, blocks=0, trees=0))
#: pass 3 (env lab 1, 2026-09-28; main scheduled it): the models fade into the sky's own horizon (SKY_HAZE) and draw
#: round crowns on trunks; st3's nine first, then st2's five (s01, s10, s12, s14, s16) opted in (main, 2026-09-29)
ST3_PASS3 = ("s00", "s01", "s03", "s07", "s10", "s11", "s12", "s14", "s15", "s16", "s18", "s19", "s20", "s23", "s24",
             "s25", "s40")
for _v in ST3_PASS3:
    STYLE[_v] = dict(STYLE[_v], sky_haze=True, crowns="round")

#: the haze by family, time of day (d, a) and weather: the sky's colour at the horizon (DESIGN, from the lab frames'
#: skies); at night the band and the haze ring carry NIGHT_HAZE
HAZE = {
    "dry": {"d": (226, 216, 198), "a": (236, 208, 172)},
    "cool": {"d": (208, 216, 226), "a": (230, 210, 184)},
    "green": {"d": (206, 216, 222), "a": (226, 210, 186)},
}
NIGHT_HAZE = (30, 34, 48)
WEATHER_HAZE = {"r": (0.74, 0.76, 0.80), "s": (0.92, 0.94, 0.98)}
#: pass 3 (env lab 1, 2026-09-28: MetLife's far ground met the band in a hard white strip): the sky texture's colour at
#: the horizon (its rows 238 to 250, the same "sky" TXTR in every bundle of a time of day and weather; PROVED OFFLINE on
#: the nine s00 bundles and the day, afternoon and night ones of s03, s07, s20, s24 and s25). A venue whose STYLE row
#: sets "sky_haze" fades its far ground, haze ring and band foot into these, and keeps the family haze above as the
#: band's own light, so the silhouettes keep their look
SKY_HAZE = {("d", "d"): (62, 87, 116), ("d", "r"): (58, 64, 70), ("d", "s"): (130, 134, 138),
            ("a", "d"): (99, 56, 27), ("a", "r"): (75, 63, 59), ("a", "s"): (185, 161, 146),
            ("n", "d"): (38, 38, 45), ("n", "r"): (38, 38, 41), ("n", "s"): (50, 50, 52)}
#: the top of the band drawing's white foot (metres over the street: the art draws its haze from HAZE_H down): a
#: sky_haze band has a row here in the haze and one a metre higher in its own light, so the white foot meets the haze
#: ring at the sky's colour and the silhouettes above keep the band's light
BAND_MID = HAZE_H
#: land use tints (the layout's classes) on the far ground
LANDUSE_TINT = {".": (1.0, 1.0, 1.0), "r": (1.0, 1.0, 1.0), "u": (0.95, 0.95, 0.97), "i": (0.92, 0.92, 0.94),
                "g": (0.82, 1.06, 0.78), "f": (0.66, 0.86, 0.64), "w": (0.55, 0.72, 0.92), "d": (1.08, 1.0, 0.86),
                "a": (0.98, 1.04, 0.80), "p": (0.84, 0.84, 0.86)}
#: default building heights by OSM type (metres, DESIGN)
BLOCK_H = {"house": 6.5, "detached": 6.5, "residential": 9.0, "apartments": 15.0, "garage": 3.5, "garages": 3.5,
           "commercial": 12.0, "retail": 8.0, "industrial": 10.0, "warehouse": 10.0, "office": 18.0, "hotel": 30.0,
           "parking": 13.0, "school": 9.0, "church": 14.0, "yes": 9.0}
TREE_R, TREE_H, TREE_Y = 3.9, 6.2, 2.8
#: pass 3 (env lab 1: the octahedron crowns read as green diamonds): a venue whose STYLE row sets "crowns": "round"
#: draws each crown as two eight-sided rings between a bottom and a top point (a rounded silhouette, the leaf tile
#: round it) on a three-sided trunk; each tree costs ROUND_TREE vertices of its budget
ROUND_TREE = 24
TRUNK_R = 0.28
#: no building within this many metres of an intro camera's eye (the eye stays in the open)
EYE_CLEAR = 30.0


def shot_eyes(shots, seconds=8.0, step=1.0):
    """(x, y, z) of each intro camera shot's eye every ``step`` seconds over its path (the ``eyes`` dress keeps clear);
    a shot is a dict with ``eye`` and optional per-second ``rates`` (x, y, z)."""
    out = []
    for s in shots:
        r = s.get("rates", {})
        for k in range(int(seconds / step) + 1):
            tt = k * step
            out.append(tuple(float(s["eye"][i]) + float(r.get(c, 0.0)) * tt for i, c in enumerate("xyz")))
    return out


def _ring_area(Q):
    A = np.asarray(Q, float)
    return 0.5 * float(np.dot(A[:, 0], np.roll(A[:, 1], 1)) - np.dot(A[:, 1], np.roll(A[:, 0], 1)))


def site_of(venue):
    """The venue whose layout and band a venue record uses (SoFi's three records share one building)."""
    return STYLE[venue].get("layout", venue)


@lru_cache(maxsize=None)
def layout(venue):
    site = site_of(venue)
    p = DATA_DIR / f"{site}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA or doc.get("venue") != site:
        raise ValueError(f"{p}: not a {SCHEMA} layout for {site}")
    return doc


def materials(venue):
    st = STYLE[venue]
    # seven textures for ten materials: the haze, the water and the roofs are the white tile coloured by vertex, the
    # grass and the tree crowns share the green tile (each texture costs its 1 KB palette too)
    return {
        "env_far": (f"env_far_{st['biome']}", CLASS_OPAQUE), "env_haze": ("env_white", CLASS_OPAQUE),
        "env_band": (f"env_band_{site_of(venue)}", CLASS_ALPHA), "env_lot": ("env_lot", CLASS_OPAQUE),
        "env_road": ("env_road", CLASS_OPAQUE), "env_grass": ("env_green", CLASS_OPAQUE),
        "env_water": ("env_white", CLASS_OPAQUE), "env_tree": ("env_green", CLASS_OPAQUE),
        "env_block": ("env_block", CLASS_OPAQUE), "env_block_b": ("env_block", CLASS_OPAQUE),
        "env_block_c": ("env_block", CLASS_OPAQUE), "env_roof": ("env_white", CLASS_OPAQUE),
        "env_roof_b": ("env_white", CLASS_OPAQUE), "env_plaza": ("env_white", CLASS_OPAQUE),
        **({"env_tree": ("env_leaf", CLASS_OPAQUE), "env_trunk": ("env_white", CLASS_OPAQUE)}
           if st.get("crowns") == "round" else {}),
    }


@lru_cache(maxsize=None)
def _png(name):
    from PIL import Image
    return np.asarray(Image.open(ART_DIR / f"{name}.png").convert("RGBA"))


def texture_name(key, tod):
    """The PNG a texture key draws in a bundle of this time of day (the night drawings: lit windows, the night band)."""
    if tod == "n" and (key == "env_block" or key.startswith("env_band_")):
        return key + "_n"
    return key


#: the weather's look on the ground tiles: snow lies on the ground, the lots and the roofs; rain darkens them
SNOW_KEYS = ("env_far_", "env_lot", "env_green")
WET_KEYS = ("env_far_", "env_lot", "env_road", "env_green")


def _weathered(key, arr, weather):
    a = arr.astype(np.float64)
    if weather == "s" and key.startswith(SNOW_KEYS):
        k = 0.55 if key == "env_green" else 0.7
        a[..., :3] = a[..., :3] * (1 - k) + np.array([236, 238, 242]) * k
    elif weather == "r" and key.startswith(WET_KEYS):
        a[..., :3] = a[..., :3] * np.array([0.78, 0.8, 0.84])
    return np.clip(a, 0, 255).astype(np.uint8)


def master_name(material, venue, tod, weather="d"):
    """The file name of a kit material's 4x master (tools/nfl2k5_stadium_environment_art.py --masters) in a bundle of this
    time of day and weather, or None: the kit weathers its ground tiles in the rain and snow bundles, so those keep their
    native drawings."""
    key = materials(venue)[material][0]
    if weather in ("r", "s") and key.startswith(tuple(set(SNOW_KEYS) | set(WET_KEYS))):
        return None
    return texture_name(key, tod) + ".png"


def textures(venue, tod, weather):
    out = {}
    for key, _cls in materials(venue).values():
        if key not in out:
            out[key] = _weathered(key, _png(texture_name(key, tod)), weather)
    return out


def band_light(venue, tod, weather):
    """The family haze: the band's own vertex light (and, before pass 3, the haze everything faded into)."""
    if tod == "n":
        return np.array(NIGHT_HAZE, float)
    c = np.array(HAZE[STYLE[venue]["haze"]][tod], float)
    return c * np.array(WEATHER_HAZE.get(weather, (1.0, 1.0, 1.0)))


def haze_colour(venue, tod, weather):
    """The colour the far ground, the haze ring and the band's foot fade into: the sky's own horizon for a venue whose
    STYLE row sets sky_haze, else the family haze."""
    if STYLE[venue].get("sky_haze"):
        return np.array(SKY_HAZE[(tod, weather if weather in ("r", "s") else "d")], float)
    return band_light(venue, tod, weather)


@lru_cache(maxsize=None)
def _tex_mean(name, weather):
    a = _weathered(name, _png(name), weather).astype(np.float64)
    return a[..., :3].reshape(-1, 3).mean(axis=0)


def _landuse_tint(venue, P):
    lu = layout(venue)["landuse"]
    rows, cell, R = lu["rows"], float(lu["cell"]), float(lu["radius"])
    n = len(rows)
    out = np.ones((len(P), 3))
    for k, (x, _y, z) in enumerate(P):
        acc, cnt = np.zeros(3), 0
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = int((x + R) / cell) + dx
                r = int((R - z) / cell) + dz
                if 0 <= r < n and 0 <= c < len(rows[r]):
                    acc += LANDUSE_TINT.get(rows[r][c], (1.0, 1.0, 1.0))
                    cnt += 1
        if cnt:
            out[k] = acc / cnt
    return out


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


#: vertex light (grey level) by material, day / afternoon / night (DESIGN)
BASE = {"env_far": (212, 204, 52), "env_lot": (214, 206, 64), "env_road": (214, 206, 60), "env_grass": (218, 210, 50),
        "env_water": (255, 240, 52), "env_tree": (170, 160, 36), "env_block": (212, 200, 255),
        "env_block_b": (212, 200, 255), "env_block_c": (212, 200, 255), "env_roof": (255, 244, 58),
        "env_roof_b": (255, 244, 58), "env_plaza": (255, 244, 70), "env_trunk": (190, 176, 40)}
#: the white tile's own colours (water: the canals and rivers from the air; roofs: gravel and tar), times the light
FLAT = {"env_water": (62, 84, 100), "env_roof": (128, 126, 122), "env_roof_b": (84, 84, 88),
        "env_plaza": (196, 192, 184), "env_trunk": (92, 70, 50)}
#: the walls' looks on the one wall tile (by day; the night drawing carries its own colour): concrete, brick, dark glass
WALL_TINT = {"env_block": (1.0, 1.0, 1.0), "env_block_b": (0.9, 0.64, 0.52), "env_block_c": (0.6, 0.66, 0.74)}
SUN = {"d": (-0.35, 0.86, 0.37), "a": (-0.78, 0.55, -0.30)}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.94, 0.86), "n": (0.9, 0.94, 1.08)}


def light(mat, P, N, tod, weather, venue):
    """Vertex colours for the kit's materials: the sun on the ground and walls, the night's lamps round the stadium's
    lots, and the fade into the haze with distance (the far ground meets the haze ring and the band at one colour)."""
    P = np.asarray(P, float)
    N = np.asarray(N, float)
    n = len(P)
    out = np.zeros((n, 4), np.uint8)
    out[:, 3] = 255
    haze = haze_colour(venue, tod, weather)
    if mat == "env_band":
        own = np.full(3, 255.0) if tod == "n" else band_light(venue, tod, weather)
        out[:, :3] = np.clip(own, 0, 255)
        if STYLE[venue].get("sky_haze") and n:
            # the band's two foot rows (at -BAND_FOOT and BAND_MID) take the haze, so the drawing's white foot meets the
            # haze ring at the sky's horizon colour; the rows above keep the band's own light
            foot = P[:, 1] <= P[:, 1].min() + BAND_FOOT + BAND_MID + 0.5
            out[foot, :3] = np.clip(haze, 0, 255)
        return out
    if mat == "env_haze":
        # from the colour the far ground reaches at HAZE_END (its texture's mean times its clamped vertex colour) to the
        # haze itself at the band's foot: no seam where one meets the other
        fkey = texture_name(materials(venue)["env_far"][0], tod)
        fmean = np.maximum(_tex_mean(fkey, weather), 1.0)
        c0 = fmean * np.clip(haze * 255.0 / fmean, 0, 255) / 255.0
        r = np.hypot(P[:, 0], P[:, 2])
        k = _smooth((r - HAZE_END) / (BAND_RADIUS - HAZE_END))[:, None]
        out[:, :3] = np.clip(c0[None, :] * (1 - k) + haze[None, :] * k, 0, 255)
        return out
    t = {"d": 0, "a": 1, "n": 2}[tod]
    base = BASE.get(mat, (210, 200, 56))[t]
    if tod == "n":
        f = np.ones(n)
    else:
        s = np.array(SUN[tod]); s /= np.linalg.norm(s)
        nd = np.clip(N @ s, 0, 1)
        f = (0.78 + 0.24 * nd) if tod == "d" else (0.66 + 0.42 * nd)
    rgb = base * f[:, None] * np.array(TINT[tod])[None, :]
    if mat in WALL_TINT and tod != "n":
        rgb = rgb * np.array(WALL_TINT[mat])[None, :]
    if mat in FLAT:
        rgb = rgb * np.array(FLAT[mat])[None, :] / 255.0
        if weather == "s" and mat.startswith("env_roof"):
            rgb = rgb * 0.3 + base * f[:, None] * 0.7 * np.array([0.93, 0.94, 0.97])[None, :]
    r = np.hypot(P[:, 0], P[:, 2])
    if tod == "n" and mat in ("env_lot", "env_road", "env_grass", "env_tree", "env_roof", "env_roof_b", "env_plaza",
                              "env_trunk"):
        # the lamps over the lots and streets round the stadium (warm, fading by 450 m)
        glow = _smooth(1.0 - (r - 150.0) / 300.0)
        rgb = rgb + glow[:, None] * np.array([118, 104, 78])[None, :]
    if weather == "r" and tod != "n":
        rgb = rgb * 0.9
    if mat == "env_far":
        rgb = rgb * _landuse_tint(venue, P)
    # into the haze: the texture's mean colour times the vertex colour meets the haze colour at HAZE_END
    key = materials(venue)[mat][0]
    mean = np.maximum(_tex_mean(texture_name(key, tod), weather), 1.0)
    target = np.clip(haze * 255.0 / mean, 0, 255)
    k = _smooth((r - HAZE_START) / (HAZE_END - HAZE_START))[:, None]
    rgb = rgb * (1 - k) + target[None, :] * k
    out[:, :3] = np.clip(rgb, 0, 255)
    return out


# ------------------------------------------------------------------------------------------------ geometry helpers

def _point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            t = (z - z1) / (z2 - z1)
            if x < x1 + t * (x2 - x1):
                inside = not inside
    return inside


def _triangulate(poly):
    """Ear clipping of a simple polygon (list of (x, z)); returns index triples (SoFi's, copied)."""
    P = [tuple(p) for p in poly]
    idx = list(range(len(P)))
    area = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
    if area < 0:
        idx.reverse()
    tris = []

    def is_ear(i0, i1, i2):
        (ax, az), (bx, bz), (cx, cz) = P[i0], P[i1], P[i2]
        if (bx - ax) * (cz - az) - (bz - az) * (cx - ax) <= 1e-9:
            return False
        for j in idx:
            if j in (i0, i1, i2):
                continue
            px, pz = P[j]
            d1 = (bx - ax) * (pz - az) - (bz - az) * (px - ax)
            d2 = (cx - bx) * (pz - bz) - (cz - bz) * (px - bx)
            d3 = (ax - cx) * (pz - cz) - (az - cz) * (px - cx)
            if d1 >= 0 and d2 >= 0 and d3 >= 0:
                return False
        return True

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if is_ear(i0, i1, i2):
                tris.append((i0, i1, i2))
                del idx[k]
                break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def _inside_any(x, z, polys):
    return any(_point_in_poly(x, z, q) for q in polys)


def _min_rect(Q):
    """The minimum-area rectangle round a point set (rotating the convex hull's edges): four corners, counter-clockwise."""
    A = np.asarray(Q, float)
    pts = sorted(set(map(tuple, A)))
    if len(pts) < 3:
        return None

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and np.cross(np.subtract(h[-1], h[-2]), np.subtract(p, h[-2])) <= 0:
                h.pop()
            h.append(p)
        return h
    hull = np.array(half(pts)[:-1] + half(pts[::-1])[:-1], float)
    best = None
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        L = float(np.hypot(*e))
        if L < 1e-6:
            continue
        u = e / L
        v = np.array([-u[1], u[0]])
        pu, pv = hull @ u, hull @ v
        area = (pu.max() - pu.min()) * (pv.max() - pv.min())
        if best is None or area < best[0]:
            best = (area, u, v, pu.min(), pu.max(), pv.min(), pv.max())
    if best is None:
        return None
    _a, u, v, u0, u1, v0, v1 = best
    return [tuple(u * a + v * b) for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def _flat(m, mat, Q, y, uvf):
    """A flat polygon (x, z) at height y, facing up, UVs from ``uvf(x, z)``."""
    Q = [tuple(p) for p in Q]
    if len(Q) >= 2 and Q[0] == Q[-1]:
        Q = Q[:-1]
    if len(Q) < 3:
        return 0
    if _ring_area(Q) < 0:
        Q = Q[::-1]
    try:
        tris = _triangulate(Q)
    except Exception:            # noqa: BLE001 - a self-touching outline: skip it
        return 0
    ids = [m.v((x, y, z), uvf(x, z), (0.0, 1.0, 0.0)) for x, z in Q]
    for i0, i1, i2 in tris:
        a, b, c = (np.array([Q[i][0], 0.0, Q[i][1]]) for i in (i0, i1, i2))
        up = np.cross(b - a, c - a)[1] > 0
        m.strip(mat, [ids[i0], ids[i1], ids[i2]] if up else [ids[i0], ids[i2], ids[i1]])
    return len(Q)


def _simplify(Q, tol):
    """Douglas-Peucker on a polyline of (x, z)."""
    Q = np.asarray(Q, float)
    if len(Q) < 3 or tol <= 0:
        return [tuple(p) for p in Q]
    keep = np.zeros(len(Q), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(Q) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        d = Q[b] - Q[a]
        L = float(np.hypot(*d)) or 1e-9
        dist = np.abs(d[0] * (Q[a + 1:b, 1] - Q[a, 1]) - d[1] * (Q[a + 1:b, 0] - Q[a, 0])) / L
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[a + 1 + k] = True
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return [tuple(p) for p in Q[keep]]


def _simplify_ring(Q, tol):
    """Douglas-Peucker on a closed ring (no repeated end point): split at the point farthest from the first."""
    Q = [tuple(map(float, p)) for p in Q]
    if len(Q) >= 2 and Q[0] == Q[-1]:
        Q = Q[:-1]
    if len(Q) < 4 or tol <= 0:
        return Q
    A = np.asarray(Q)
    k = int(np.argmax(np.hypot(A[:, 0] - A[0, 0], A[:, 1] - A[0, 1])))
    first = _simplify(Q[:k + 1], tol)
    second = _simplify(Q[k:] + [Q[0]], tol)
    return [tuple(map(float, p)) for p in first[:-1] + second[:-1]]


def _runs_outside(pts, keep_out):
    """A polyline split into runs outside the keep-out polygons."""
    runs, cur = [], []
    for p in pts:
        if _inside_any(p[0], p[1], keep_out):
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
        else:
            cur.append(p)
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def _ribbon(m, mat, pts, width, y, u_span):
    Q = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    Q = Q[np.concatenate([[True], seg > 0.5])]
    if len(Q) < 2:
        return 0
    T = np.gradient(Q, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nn = np.stack([-T[:, 1], T[:, 0]], axis=1)
    Ls = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    left = [(x + nx * width / 2, y, z + nz * width / 2) for (x, z), (nx, nz) in zip(Q, Nn)]
    right = [(x - nx * width / 2, y, z - nz * width / 2) for (x, z), (nx, nz) in zip(Q, Nn)]
    m.grid(mat, [left, right], [[(0.0, s / ROAD_REPEAT) for s in Ls], [(u_span, s / ROAD_REPEAT) for s in Ls]],
           facing=lambda p_: np.array([0.0, 1.0, 0.0]))
    return 2 * len(Q)


def _lift(r):
    """Layers over the ground rise with distance so the depth buffer keeps them apart far away."""
    return 1.0 + r / 250.0


# ------------------------------------------------------------------------------------------------ dress

def dress(model, venue, *, grade, keep_out, inner=None, exclude_ways=(), block_max_height=None, eyes=(),
          plaza=None, mesh_cls=None):
    """Add the venue's surroundings to ``model.meshes`` (the env_* meshes); returns counts per part.

    ``keep_out``: (x, z) polygons the kit leaves to the stadium (its building and plaza); ``inner``: the ring the far
    ground starts from (default the first keep-out polygon); ``exclude_ways``: OSM ways the stadium draws itself;
    ``block_max_height``: buildings taller than this are the stadium's own (its downtown towers); ``eyes``: (x, y, z)
    points on the intro cameras' paths, kept clear (no building within EYE_CLEAR of one, no tree within 12 m);
    ``plaza``: for a model that draws no plaza of its own, a concrete plaza this many metres wide round ``inner`` (the
    far ground and the keep-out then start at its outer edge)."""
    if mesh_cls is None:
        from . import nfl2k5_metlife_model as mm       # the Mesh every stadium model uses (landed)
        mesh_cls = mm.Mesh
    Mesh = mesh_cls
    L = layout(venue)
    st = STYLE[venue]
    keep = [[tuple(p) for p in q] for q in keep_out]
    ring = [tuple(p) for p in (inner if inner is not None else keep[0])]
    skip = set(exclude_ways)
    eyes_xz = np.array([(e[0], e[2]) for e in eyes], float) if len(eyes) else None
    counts = {}

    def mesh(name):
        return model.meshes.setdefault(name, Mesh(name))

    if plaza:
        R0 = np.array(ring, float)
        c0 = R0.mean(axis=0)
        grown = []
        for k in (0.0, plaza):
            row = []
            for x, z in list(R0) + [R0[0]]:
                v = np.array([x - c0[0], z - c0[1]])
                v /= max(1e-9, float(np.linalg.norm(v)))
                row.append((float(x + v[0] * k), grade, float(z + v[1] * k)))
            grown.append(row)
        mesh("env_plaza").grid("env_plaza", grown, [[(x / 20.0, z / 20.0) for x, _y, z in row] for row in grown],
                               facing=lambda p_: np.array([0.0, 1.0, 0.0]))
        ring = [(x, z) for x, _y, z in grown[-1][:-1]]
        keep = keep + [ring]

    # -- the far ground: from the inner ring (ray cast at far_angles, pulled 4% in under the plaza) to the haze ring
    A = st["far_angles"]
    inner_pts = []
    for k in range(A + 1):
        a = 2 * math.pi * (k % A) / A
        d = np.array([math.cos(a), math.sin(a)])
        best = 0.0
        for i in range(len(ring)):
            p, q = np.array(ring[i]), np.array(ring[(i + 1) % len(ring)])
            e = q - p
            den = d[0] * (-e[1]) + d[1] * e[0]
            if abs(den) < 1e-9:
                continue
            t = (p[0] * (-e[1]) + p[1] * e[0]) / den
            s = (d[0] * p[1] - d[1] * p[0]) / den
            if t > 0 and -1e-9 <= s <= 1 + 1e-9:
                best = max(best, t)
        inner_pts.append(d * best * 0.96)
    rin = max(float(np.hypot(*p)) for p in inner_pts)
    radii = [r for r in FAR_RINGS if r > rin + 60.0]
    y0 = grade - 0.08
    rows = [[(float(p[0]), y0, float(p[1])) for p in inner_pts]]
    for r in radii:
        rows.append([(r * math.cos(2 * math.pi * (k % A) / A), y0, r * math.sin(2 * math.pi * (k % A) / A))
                     for k in range(A + 1)])
    tile = st["tile"]
    far = mesh("env_far")
    far.grid("env_far", rows, [[(x / tile, z / tile) for x, _y, z in row] for row in rows],
             facing=lambda p_: np.array([0.0, 1.0, 0.0]))
    hz = mesh("env_haze")
    last = rows[-1]
    outer = [(BAND_RADIUS * math.cos(2 * math.pi * (k % A) / A), y0, BAND_RADIUS * math.sin(2 * math.pi * (k % A) / A))
             for k in range(A + 1)]
    hz.grid("env_haze", [last, outer], [[(0.5, 0.5)] * (A + 1)] * 2, facing=lambda p_: np.array([0.0, 1.0, 0.0]))
    counts["far"] = far.count() + hz.count()

    # -- the band: u = the bearing / 360 of each column (the layout's frame), v from BAND_TOP down to -BAND_FOOT
    xb = math.radians(L["frame"]["x_bearing"])
    zb = math.radians(L["frame"]["field_bearing"])
    xh, zh = np.array([math.sin(xb), math.cos(xb)]), np.array([math.sin(zb), math.cos(zb)])
    Bn = st.get("band_columns", 48)
    band = mesh("env_band")
    cols = []
    for k in range(Bn + 1):
        a = 2 * math.pi * k / Bn
        x, z = BAND_RADIUS * math.cos(a), BAND_RADIUS * math.sin(a)
        e, nn = x * xh + z * zh
        brg = math.degrees(math.atan2(e, nn)) % 360.0
        cols.append((x, z, brg))
    # unwrap the bearings so u runs monotonically round the ring
    us = [cols[0][2] / 360.0]
    for k in range(1, len(cols)):
        du = (cols[k][2] - cols[k - 1][2] + 540.0) % 360.0 - 180.0
        us.append(us[-1] + du / 360.0)
    top = [(x, grade + BAND_TOP, z) for x, z, _b in cols]
    bot = [(x, grade - BAND_FOOT, z) for x, z, _b in cols]
    if st.get("sky_haze"):
        # two rows at the top of the drawing's white foot (BAND_MID) and a metre over it: the band's own light above,
        # the haze below (light() by height), so the foot takes the sky's horizon colour
        def v_at(y):
            return BAND_PAD + (1.0 - BAND_PAD) * (BAND_TOP - y) / (BAND_TOP + BAND_FOOT)
        hi = [(x, grade + BAND_MID + 1.0, z) for x, z, _b in cols]
        lo = [(x, grade + BAND_MID, z) for x, z, _b in cols]
        band.grid("env_band", [top, hi, lo, bot], [[(u, BAND_PAD) for u in us], [(u, v_at(BAND_MID + 1.0)) for u in us],
                                                   [(u, v_at(BAND_MID)) for u in us], [(u, 1.0) for u in us]],
                  facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))
    else:
        band.grid("env_band", [top, bot], [[(u, BAND_PAD) for u in us], [(u, 1.0) for u in us]],
                  facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))
    counts["band"] = band.count()

    near = st["near"]
    budget = dict(BUDGET, **st.get("budget", {}))

    def room(m_, part, cost):
        return m_.count() + cost <= budget[part]

    # -- lots with their cars: the stalls along each lot's long axis (nearest first, to the budget)
    lots = mesh("env_lots")
    todo = []
    for lot in L["lots"]:
        if lot.get("way") in skip:
            continue
        Q = _simplify_ring(lot["points"], 1.5)
        c = np.mean(np.array(Q), axis=0)
        r = float(np.hypot(*c))
        if len(Q) < 3 or r > near or any(_inside_any(x, z, keep) for x, z in Q):
            continue
        todo.append((r, Q))
    for r, Q in sorted(todo, key=lambda t_: t_[0]):
        if not room(lots, "lots", len(Q)):
            continue
        R = _min_rect(Q)
        if R is None:
            continue
        R = np.array(R)
        e1, e2 = R[1] - R[0], R[3] - R[0]
        u = e1 / max(1e-6, np.linalg.norm(e1)) if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2 / max(1e-6, np.linalg.norm(e2))
        v = np.array([-u[1], u[0]])
        _flat(lots, "env_lot", Q, grade + 0.10 * _lift(r),
              lambda x, z, u=u, v=v: (float(np.dot((x, z), u)) / LOT_U, float(np.dot((x, z), v)) / LOT_V))
    counts["lots"] = lots.count()

    # -- grass and parks (the biggest and nearest first), water
    green = mesh("env_green")
    cand = []
    for g in L["grass"]:
        if g.get("way") in skip:
            continue
        Q = _simplify_ring(g["points"], 2.0)
        if len(Q) < 3:
            continue
        area = abs(_ring_area(Q))
        c = np.mean(np.array(Q), axis=0)
        r = float(np.hypot(*c))
        if area < st.get("grass_min", 600.0) or r > near or _inside_any(c[0], c[1], keep):
            continue
        cand.append((r - 3.0 * math.sqrt(area), r, Q))
    for _k, r, Q in sorted(cand, key=lambda t_: t_[0]):
        if room(green, "grass", len(Q)):
            # under the stadium's plaza where a park runs up to it, over the far ground everywhere
            _flat(green, "env_grass", Q, grade - 0.08 + 0.05 * _lift(r), lambda x, z: (x / 14.0, z / 14.0))
    counts["grass"] = green.count()
    wat = mesh("env_water")
    for w in sorted(L["water"], key=lambda w: -abs(_ring_area(w["points"]))):
        Q = _simplify_ring(w["points"], 4.0)
        if abs(_ring_area(Q)) < st["water_min"]:
            continue
        Qc = [p for p in Q if math.hypot(*p) < BAND_RADIUS * 0.95]
        if len(Qc) < 3 or not room(wat, "water", len(Qc)):
            continue
        c = np.mean(np.array(Qc), axis=0)
        if _inside_any(c[0], c[1], keep):
            continue
        _flat(wat, "env_water", Qc, grade + 0.03 * _lift(float(np.hypot(*c))), lambda x, z: (x / 20.0, z / 20.0))
    for w in sorted(L.get("waterways", []), key=lambda w: -float(w["width"])):
        pts = [tuple(p) for p in _simplify(w["points"], 4.0) if math.hypot(*p) < BAND_RADIUS * 0.95]
        for run in _runs_outside(pts, keep):
            if room(wat, "water", 2 * len(run)):
                rr = float(np.min(np.hypot(*np.array(run).T)))
                _ribbon(wat, "env_water", run, float(w["width"]), grade + 0.03 * _lift(rr), float(w["width"]) / 20.0)
    counts["water"] = wat.count()

    # -- roads: every run scored by its distance and its class (a freeway far out before a service road close in),
    #    added in that order to the budget
    rd = mesh("env_roads")
    weight = {"motorway": 0.35, "trunk": 0.45, "primary": 0.55, "secondary": 0.65, "tertiary": 0.8,
              "residential": 1.0, "unclassified": 1.0, "service": 1.6}
    lift_by = {"motorway": 0.26, "trunk": 0.24, "primary": 0.22, "secondary": 0.2, "tertiary": 0.19}
    runs = []
    for road in L["roads"]:
        if road["way"] in skip:
            continue
        kind = road["kind"]
        base_kind = kind[:-5] if kind.endswith("_link") else kind
        lim = (st.get("roads_big", near) if base_kind in lift_by and not kind.endswith("_link") else st["roads_minor"]
               if kind.endswith("_link") or kind in ("residential", "unclassified") else st["roads_service"])
        pts = _simplify(road["points"], st.get("road_tol", 0.0))
        for run in _runs_outside([p for p in pts if math.hypot(*p) <= lim + 60.0], keep):
            rr = float(np.min(np.hypot(*np.array(run).T)))
            if rr <= lim:
                runs.append((rr * weight.get(base_kind, 1.2), rr, kind, road, run))
    for road in L.get("far_roads", []):
        if road["kind"] not in st["far_roads"]:
            continue
        pts = [p for p in _simplify(road["points"], 2 * st.get("road_tol", 1.0)) if math.hypot(*p) < HAZE_END]
        for run in _runs_outside(pts, keep):
            rr = float(np.min(np.hypot(*np.array(run).T)))
            runs.append((rr * weight.get(road["kind"], 1.0), rr, road["kind"], road, run))
    for _score, rr, kind, road, run in sorted(runs, key=lambda t_: (t_[0], t_[3]["way"])):
        if room(rd, "roads", 2 * len(run)):
            base_kind = kind[:-5] if kind.endswith("_link") else kind
            _ribbon(rd, "env_road", run, float(road["width"]), grade + lift_by.get(base_kind, 0.16) * _lift(rr),
                    float(max(1, road["lanes"])))
    counts["roads"] = rd.count()

    # -- buildings: boxes on each outline's minimum rectangle (the near, big and tall first, to the budget)
    bd = mesh("env_blocks")
    cand = []
    for b in L["blocks"]:
        if b.get("way") in skip:
            continue
        Q = np.array(b["points"], float)
        if len(Q) < 3:
            continue
        c = Q.mean(axis=0)
        r = float(np.hypot(*c))
        if r > st["block_radius"] or _inside_any(c[0], c[1], keep):
            continue
        area = abs(_ring_area(Q))
        # an untagged small building is a one-storey pavilion, kiosk or shed (DESIGN)
        h = b.get("height") or (4.5 if area < 500.0 and (b.get("kind") or "yes") == "yes" else
                                BLOCK_H.get(b.get("kind") or "yes", 9.0))
        if block_max_height is not None and h > block_max_height:
            continue
        if area < st.get("block_min", 120.0):
            continue
        if eyes_xz is not None and _near_rect(Q, eyes_xz, EYE_CLEAR):
            continue
        R0 = _min_rect(Q)
        if R0 is None or any(_inside_any(x, z, keep) for x, z in R0):
            continue                                   # the box would stand on the stadium's own plaza
        cand.append((r - math.sqrt(area) * 2.0 - float(h), b.get("way") or 0, Q, float(h), float(b.get("min_height") or 0.0)))
    for _key, w_, Q, h, h0 in sorted(cand, key=lambda t_: (t_[0], t_[1])):
        if not room(bd, "blocks", 14):
            break
        R = _min_rect(Q)
        if R is not None:
            look = (int(w_) * 2654435761) % 7
            wall = "env_block_c" if h >= 30.0 and look < 4 else ("env_block", "env_block_b", "env_block")[look % 3]
            _box(bd, R, grade + h0, grade + max(h, h0 + 3.0), wall, "env_roof_b" if look in (1, 5) else "env_roof")
    counts["blocks"] = bd.count()

    # -- trees: OSM's trees and tree rows (every 9 m), nearest first
    tr = mesh("env_trees")
    spots = [tuple(p) for p in L["trees"]]
    for row in L["tree_rows"]:
        P_ = np.array(row["points"], float)
        for a_, b_ in zip(P_[:-1], P_[1:]):
            n_ = max(1, int(np.linalg.norm(b_ - a_) / 9.0))
            spots += [tuple(a_ + (b_ - a_) * (i / n_)) for i in range(n_)]
    spots = [p for p in spots if math.hypot(*p) < near and not _inside_any(p[0], p[1], keep)
             and (eyes_xz is None or float(np.min(np.hypot(eyes_xz[:, 0] - p[0], eyes_xz[:, 1] - p[1]))) > 12.0)]
    round_ = st.get("crowns") == "round"
    cost, crown = (ROUND_TREE, _round_tree) if round_ else (6, _crown)
    for x, z in sorted(spots, key=lambda p: (math.hypot(*p), p)):
        if not room(tr, "trees", cost):
            break
        crown(tr, x, grade, z)
    # where OpenStreetMap maps woods but few single trees, the rest of the budget goes to crowns in the woods' cells
    # (the land use grid's forest class), nearest first, at seeded spots
    lu = L["landuse"]
    cell, R, rows = float(lu["cell"]), float(lu["radius"]), lu["rows"]
    woods = []
    rnd = np.random.default_rng(int(site_of(venue)[1:]) * 7919 + 17)
    for r_, row in enumerate(rows):
        for c_, cls in enumerate(row):
            if cls != "f":
                continue
            for _k in range(2):
                x = -R + (c_ + float(rnd.random())) * cell
                z = R - (r_ + float(rnd.random())) * cell
                d = math.hypot(x, z)
                if d < near and not _inside_any(x, z, keep) and (
                        eyes_xz is None or float(np.min(np.hypot(eyes_xz[:, 0] - x, eyes_xz[:, 1] - z))) > 12.0):
                    woods.append((d, x, z))
    for _d, x, z in sorted(woods):
        if not room(tr, "trees", cost):
            break
        crown(tr, x, grade, z)
    counts["trees"] = tr.count()
    return counts


def _near_rect(Q, pts, pad):
    """True when any point lies within ``pad`` metres of the outline's minimum rectangle."""
    R = _min_rect(Q)
    if R is None:
        return False
    R = np.asarray(R, float)
    c = R.mean(axis=0)
    u, v = R[1] - R[0], R[3] - R[0]
    lu, lv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    if lu < 1e-6 or lv < 1e-6:
        return False
    u, v = u / lu, v / lv
    d = pts - c
    return bool(np.any((np.abs(d @ u) <= lu / 2 + pad) & (np.abs(d @ v) <= lv / 2 + pad)))


def _box(m, R, y0, y1, wall="env_block", roof="env_roof"):
    R = [tuple(p) for p in R]
    if _ring_area(R) < 0:
        R = R[::-1]
    per = 0.0
    lo, hi, uvl, uvh = [], [], [], []
    for i in range(5):
        x, z = R[i % 4]
        if i:
            per += math.hypot(x - R[(i - 1) % 4][0], z - R[(i - 1) % 4][1])
        lo.append((x, y0, z)); hi.append((x, y1, z))
        uvl.append((per / 8.0, (y1 - y0) / 3.5)); uvh.append((per / 8.0, 0.0))
    c = np.mean(np.array(R), axis=0)
    m.grid(wall, [lo, hi], [uvl, uvh], facing=lambda p_, c=c: np.array([p_[0] - c[0], 0.0, p_[2] - c[1]]))
    m.grid(roof, [[(R[0][0], y1, R[0][1]), (R[1][0], y1, R[1][1])], [(R[3][0], y1, R[3][1]), (R[2][0], y1, R[2][1])]],
           [[(R[0][0] / 12.0, R[0][1] / 12.0), (R[1][0] / 12.0, R[1][1] / 12.0)],
            [(R[3][0] / 12.0, R[3][1] / 12.0), (R[2][0] / 12.0, R[2][1] / 12.0)]],
           facing=lambda p_: np.array([0.0, 1.0, 0.0]))


def _crown(m, x, grade, z):
    """A tree's crown: an octahedron TREE_R wide and TREE_H tall, its bottom TREE_Y over the ground."""
    cy = grade + TREE_Y + TREE_H / 2
    top = m.v((x, cy + TREE_H / 2, z), (0.5, 0.0), (0.0, 1.0, 0.0))
    bot = m.v((x, cy - TREE_H / 2, z), (0.5, 1.0), (0.0, -1.0, 0.0))
    ring = []
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        d = (math.cos(a), 0.0, math.sin(a))
        ring.append(m.v((x + TREE_R * d[0], cy, z + TREE_R * d[2]), (k * 0.5, 0.5), d))
    for k in range(4):
        a, b = ring[k], ring[(k + 1) % 4]
        m.strip("env_tree", [top, b, a])
        m.strip("env_tree", [bot, a, b])


def _round_tree(m, x, grade, z):
    """A tree (pass 3): a crown of two eight-sided rings (at a third and two thirds of TREE_H, the upper one narrower)
    between a bottom and a top point, the leaf tile twice round it; and a three-sided trunk from the ground into the
    crown. ROUND_TREE vertices."""
    y0 = grade + TREE_Y
    top = m.v((x, y0 + TREE_H, z), (0.5, 0.0), (0.0, 1.0, 0.0))
    bot = m.v((x, y0, z), (0.5, 1.0), (0.0, -1.0, 0.0))
    rings = []
    for f, rr, v in ((0.35, 1.0, 0.62), (0.72, 0.78, 0.3)):
        ring = []
        for k in range(8):
            a = math.pi / 8 + k * math.pi / 4
            d = (math.cos(a), 0.0, math.sin(a))
            ring.append(m.v((x + TREE_R * rr * d[0], y0 + TREE_H * f, z + TREE_R * rr * d[2]), (k * 0.25, v), d))
        rings.append(ring)
    lo, hi = rings
    for k in range(8):
        a, b = lo[k], lo[(k + 1) % 8]
        c, d = hi[k], hi[(k + 1) % 8]
        m.strip("env_tree", [bot, a, b])
        m.strip("env_tree", [a, c, b])
        m.strip("env_tree", [b, c, d])
        m.strip("env_tree", [top, d, c])
    base_, up = [], []
    for k in range(3):
        a = math.pi / 2 + k * 2 * math.pi / 3
        d = (math.cos(a), 0.0, math.sin(a))
        base_.append(m.v((x + TRUNK_R * d[0], grade, z + TRUNK_R * d[2]), (k * 0.33, 1.0), d))
        up.append(m.v((x + TRUNK_R * 0.8 * d[0], y0 + TREE_H * 0.4, z + TRUNK_R * 0.8 * d[2]), (k * 0.33, 0.0), d))
    for k in range(3):
        a, b = base_[k], base_[(k + 1) % 3]
        c, d = up[k], up[(k + 1) % 3]
        m.strip("env_trunk", [a, c, b])
        m.strip("env_trunk", [b, c, d])
