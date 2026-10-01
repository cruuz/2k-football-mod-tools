"""Author-time: one stadium's surroundings for the shared environment kit (nfl2k5_stadium_environment), from OpenStreetMap
(ODbL 1.0) and the Terrain Tiles elevation set (Mapzen / AWS Open Data; SRTM, USGS 3DEP and others, public sources).

    python3 tools/nfl2k5_stadium_environment_osm.py VENUE LAT LON FIELD_BEARING [--cache DIR]

VENUE is the retail venue record (s00, s15 ...). LAT, LON is the field centre and FIELD_BEARING the bearing of the game's
+z axis; +x points to FIELD_BEARING - 90 (the frame every modern stadium module uses: x across, y up, z along, metres, the
origin at the field centre). The layout goes to data/nfl2k5_stadium_environment/VENUE.json as canonical JSON:

* near features within NEAR_RADIUS: surface parking, roads with their lanes, grass and parks, water, trees, tree rows,
  rail and the buildings (outline, height or levels);
* the land use round the site to BAND_RADIUS as a class grid (the far ground's tint);
* the horizon: every 1 degree of bearing, the terrain's elevation angle out to 70 km (earth curvature and refraction
  applied) and the tall buildings out to 15 km (bearing, angular width, elevation angle).

Network access is needed here only (Overpass and the tile server); the build reads the JSON."""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "nfl2k5_stadium_environment"
SCHEMA = "nfl2k5_stadium_environment_layout/v1"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = "nfl2k5-mod-tools/1.0 (stadium environment kit; author-time fetch)"
NEAR_RADIUS = 900.0          # features as geometry
FAR_RADIUS = 1900.0          # land use for the far ground
GRID_CELL = 30.0             # the land use grid's cell (metres)
SKY_RADIUS = 15000.0         # tall buildings for the skyline
TERRAIN_RADIUS = 70000.0
EARTH_R = 6371000.0
REFRACTION = 0.13

ROADS = {"motorway": (3, 3.6), "trunk": (2, 3.5), "primary": (2, 3.4), "secondary": (2, 3.3), "tertiary": (1, 3.2),
         "unclassified": (1, 3.0), "residential": (1, 3.0), "motorway_link": (1, 3.6), "trunk_link": (1, 3.5),
         "primary_link": (1, 3.4), "secondary_link": (1, 3.3), "tertiary_link": (1, 3.2), "service": (1, 2.8)}
#: land use classes: u urban, r residential, i industrial, g grass, f forest, w water, d desert, a farmland, p parking
LANDUSE = {"commercial": "u", "retail": "u", "construction": "i", "industrial": "i", "railway": "i", "residential": "r",
           "grass": "g", "recreation_ground": "g", "cemetery": "g", "meadow": "g", "village_green": "g", "forest": "f",
           "orchard": "f", "reservoir": "w", "basin": "w", "farmland": "a", "farmyard": "a", "vineyard": "a",
           "greenfield": "g", "brownfield": "d", "military": "i", "education": "u", "institutional": "u"}
NATURAL = {"water": "w", "wood": "f", "scrub": "d", "sand": "d", "bare_rock": "d", "heath": "d", "grassland": "g",
           "wetland": "g", "beach": "d"}
LEISURE = {"park": "g", "golf_course": "g", "pitch": "g", "garden": "g", "nature_reserve": "g", "dog_park": "g"}


def overpass(query, cache):
    if cache.is_file():
        return json.loads(cache.read_text())
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url, tries in zip(OVERPASS, (5, 2)):
        for attempt in range(tries):
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = json.loads(r.read())
                cache.write_text(json.dumps(data))
                return data
            except Exception as e:          # noqa: BLE001 - a busy server: wait, then the next one
                last = e
                time.sleep(20 * (attempt + 1))
    raise SystemExit(f"Overpass failed: {last}")


def tile(z, x, y, cache_dir):
    from PIL import Image
    p = cache_dir / f"t{z}_{x}_{y}.png"
    if not p.is_file():
        req = urllib.request.Request(TILES.format(z=z, x=x, y=y), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            p.write_bytes(r.read())
    a = np.asarray(Image.open(p).convert("RGB"), np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


class Frame:
    def __init__(self, lat, lon, bearing, shift=(0.0, 0.0)):
        self.lat, self.lon, self.b = lat, lon, bearing
        self.shift = (float(shift[0]), float(shift[1]))
        self.kx = 111320.0 * math.cos(math.radians(lat))
        self.ky = 110950.0
        br = math.radians(bearing)
        self.zh = np.array([math.sin(br), math.cos(br)])
        self.xh = np.array([math.sin(br - math.pi / 2), math.cos(br - math.pi / 2)])

    def game(self, lat, lon):
        en = np.array([(lon - self.lon) * self.kx, (lat - self.lat) * self.ky])
        return float(en @ self.xh) + self.shift[0], float(en @ self.zh) + self.shift[1]

    def bearing_of(self, lat, lon):
        e, n = (lon - self.lon) * self.kx, (lat - self.lat) * self.ky
        return math.degrees(math.atan2(e, n)) % 360.0, math.hypot(e, n)


def ring_join(ways):
    """Closed rings from a multipolygon's member ways (joined end to end)."""
    rings, open_ = [], [list(w) for w in ways if len(w) >= 2]
    while open_:
        cur = open_.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, w in enumerate(open_):
                if w[0] == cur[-1]:
                    cur += w[1:]
                elif w[-1] == cur[-1]:
                    cur += w[::-1][1:]
                elif w[-1] == cur[0]:
                    cur = w + cur[1:]
                elif w[0] == cur[0]:
                    cur = w[::-1] + cur[1:]
                else:
                    continue
                open_.pop(i)
                changed = True
                break
        if len(cur) >= 4 and cur[0] == cur[-1]:
            rings.append(cur)
    return rings


def rnd(v):
    return round(float(v), 1)


def area(Q):
    A = np.asarray(Q, float)
    return 0.5 * abs(float(np.dot(A[:, 0], np.roll(A[:, 1], 1)) - np.dot(A[:, 1], np.roll(A[:, 0], 1))))


def simplify(Q, tol):
    """Douglas-Peucker on a polyline (list of (x, z))."""
    Q = np.asarray(Q, float)
    if len(Q) < 3:
        return Q.tolist()
    keep = np.zeros(len(Q), bool); keep[0] = keep[-1] = True
    stack = [(0, len(Q) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        d = Q[b] - Q[a]
        L = float(np.hypot(*d)) or 1e-9
        dist = np.abs(np.cross(d, Q[a + 1:b] - Q[a])) / L
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[a + 1 + k] = True
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return Q[keep].tolist()


def fetch(venue, lat, lon, cache):
    near = f"""[out:json][timeout:180];
(
  way(around:{NEAR_RADIUS + 100:.0f},{lat},{lon})[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|service)$"];
  way(around:{NEAR_RADIUS + 100:.0f},{lat},{lon})[railway~"^(rail|light_rail|tram)$"];
  way(around:{NEAR_RADIUS:.0f},{lat},{lon})[amenity=parking];
  way(around:{NEAR_RADIUS:.0f},{lat},{lon})[building];
  node(around:{NEAR_RADIUS:.0f},{lat},{lon})[natural=tree];
  way(around:{NEAR_RADIUS:.0f},{lat},{lon})[natural=tree_row];
);
out geom tags;"""
    far = f"""[out:json][timeout:240];
(
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[landuse];
  relation(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[landuse];
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[natural~"^(water|wood|scrub|sand|bare_rock|heath|grassland|wetland|beach)$"];
  relation(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[natural~"^(water|wood|scrub|sand|bare_rock|heath|grassland|wetland|beach)$"];
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[leisure~"^(park|golf_course|pitch|garden|nature_reserve|dog_park)$"];
  relation(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[leisure~"^(park|golf_course|nature_reserve)$"];
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[waterway~"^(river|canal|riverbank)$"];
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[amenity=parking];
  way(around:{FAR_RADIUS + 400:.0f},{lat},{lon})[highway~"^(motorway|trunk|primary|secondary)$"];
);
out geom tags;"""
    tall = f"""[out:json][timeout:180];
(
  way(around:{SKY_RADIUS:.0f},{lat},{lon})[building][height~"^([5-9][0-9]|[1-9][0-9][0-9])"];
  way(around:{SKY_RADIUS:.0f},{lat},{lon})[building]["building:levels"~"^(1[5-9]|[2-9][0-9]|1[0-9][0-9])$"];
  relation(around:{SKY_RADIUS:.0f},{lat},{lon})[building][height~"^([5-9][0-9]|[1-9][0-9][0-9])"];
);
out bb tags;"""
    return (overpass(near, cache / f"{venue}_near.json"), overpass(far, cache / f"{venue}_far.json"),
            overpass(tall, cache / f"{venue}_tall.json"))


def geom(e, F):
    return [F.game(p["lat"], p["lon"]) for p in e.get("geometry", []) if p]


def polygons(e, F):
    """Closed outer rings (game frame) of a way or a multipolygon relation."""
    if e["type"] == "way":
        g = e.get("geometry") or []
        pts = [(p["lat"], p["lon"]) for p in g if p]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return [[F.game(*p) for p in pts[:-1]]]
        return []
    outers = [[(p["lat"], p["lon"]) for p in m.get("geometry") or [] if p] for m in e.get("members", [])
              if m.get("type") == "way" and m.get("role") in ("outer", "")]
    return [[F.game(*p) for p in r[:-1]] for r in ring_join(outers)]


def num(v):
    try:
        return float(str(v).strip().split()[0].replace("m", "").replace(",", "."))
    except (ValueError, IndexError):
        return None


def height_of(tags):
    for key in ("height", "building:height"):
        h = num(tags.get(key, ""))
        if h:
            return h
    lv = num(tags.get("building:levels", ""))
    return 3.5 * lv + 2.0 if lv else None


def build_layout(venue, lat, lon, bearing, cache, shift=(0.0, 0.0), exclude=()):
    F = Frame(lat, lon, bearing, shift)
    skip = set(int(x) for x in exclude)
    near, far, tall = fetch(venue, lat, lon, cache)
    out = dict(schema=SCHEMA, venue=venue,
               source=("OpenStreetMap contributors (ODbL 1.0), fetched " + time.strftime("%Y-%m-%d")
                       + " through Overpass; elevation: Terrain Tiles (Mapzen, AWS Open Data: SRTM, USGS 3DEP and other"
                       " public sources)"),
               frame=dict(origin_latlon=[lat, lon], field_bearing=bearing, x_bearing=(bearing - 90.0) % 360.0,
                          shift=[round(float(s), 2) for s in shift], excluded=sorted(skip)),
               lots=[], roads=[], grass=[], water=[], trees=[], tree_rows=[], rail=[], blocks=[])
    for e in near["elements"]:
        tags = e.get("tags", {})
        if e["id"] in skip:
            continue
        if e["type"] == "node":
            x, z = F.game(e["lat"], e["lon"])
            out["trees"].append([rnd(x), rnd(z)])
            continue
        pts = geom(e, F)
        if len(pts) < 2:
            continue
        hw, rw = tags.get("highway"), tags.get("railway")
        if hw in ROADS:
            lanes, lw = ROADS[hw]
            try:
                lanes = max(1, int(str(tags.get("lanes", "")).split(";")[0]))
            except ValueError:
                lanes = lanes * (1 if tags.get("oneway") == "yes" else 2)
            out["roads"].append(dict(way=e["id"], kind=hw, lanes=lanes, oneway=tags.get("oneway") == "yes",
                                     width=rnd(lanes * lw + 1.0),
                                     points=[[rnd(x), rnd(z)] for x, z in simplify(pts, 0.8)]))
        elif rw:
            out["rail"].append(dict(way=e["id"], kind=rw, points=[[rnd(x), rnd(z)] for x, z in simplify(pts, 0.8)]))
        elif tags.get("natural") == "tree_row":
            out["tree_rows"].append(dict(way=e["id"], points=[[rnd(x), rnd(z)] for x, z in simplify(pts, 1.0)]))
        elif tags.get("amenity") == "parking":
            if "building" in tags or tags.get("parking") in ("multi-storey", "underground", "rooftop"):
                h = height_of(tags) or 12.0
                if tags.get("parking") != "underground" and len(pts) >= 4:
                    out["blocks"].append(dict(way=e["id"], kind="parking", height=rnd(h),
                                              points=[[rnd(x), rnd(z)] for x, z in simplify(pts[:-1], 0.8)]))
                continue
            if len(pts) >= 4 and area(pts) >= 150.0:
                out["lots"].append(dict(way=e["id"], name=tags.get("name"),
                                        points=[[rnd(x), rnd(z)] for x, z in simplify(pts[:-1], 0.8)]))
        elif "building" in tags and tags.get("building") not in ("roof", "no", "construction") and len(pts) >= 4:
            if area(pts) < 60.0:
                continue
            h = height_of(tags)
            h0 = num(tags.get("min_height", "0")) or 0.0
            out["blocks"].append(dict(way=e["id"], kind=tags.get("building"), height=rnd(h) if h else None,
                                      min_height=rnd(h0), name=tags.get("name"),
                                      points=[[rnd(x), rnd(z)] for x, z in simplify(pts[:-1], 0.8)]))
    # far: land use polygons, water, parks, lots and the big roads, rasterized into the class grid
    n = int(round(2 * FAR_RADIUS / GRID_CELL))
    grid = np.full((n, n), ".", dtype="<U1")
    from PIL import Image, ImageDraw

    def paint(polys, cls, order):
        img = Image.new("L", (n, n), 0)
        d = ImageDraw.Draw(img)
        for Q in polys:
            px = [((x + FAR_RADIUS) / GRID_CELL, (FAR_RADIUS - z) / GRID_CELL) for x, z in Q]
            if len(px) >= 3:
                d.polygon(px, fill=255)
        mask = np.asarray(img) > 0
        layers.append((order, mask, cls))

    layers = []
    for e in far["elements"]:
        tags = e.get("tags", {})
        cls, order = None, 0
        if tags.get("landuse") in LANDUSE:
            cls, order = LANDUSE[tags["landuse"]], 1
        if tags.get("leisure") in LEISURE:
            cls, order = LEISURE[tags["leisure"]], 2
        if tags.get("natural") in NATURAL:
            cls, order = NATURAL[tags["natural"]], 3
        if tags.get("waterway") == "riverbank":
            cls, order = "w", 4
        if tags.get("amenity") == "parking":
            cls, order = "p", 5
        if cls is not None:
            polys = polygons(e, F)
            if polys:
                paint(polys, cls, order)
            if cls == "w":
                for Q in polys:
                    if area(Q) >= 2000.0:
                        out["water"].append(dict(id=e["id"], points=[[rnd(x), rnd(z)] for x, z in simplify(Q, 3.0)]))
            if cls == "g" and e["type"] == "way":
                for Q in polys:
                    if area(Q) >= 400.0 and min(math.hypot(x, z) for x, z in Q) < NEAR_RADIUS:
                        out["grass"].append(dict(way=e["id"], kind=tags.get("leisure") or tags.get("landuse")
                                                 or tags.get("natural"),
                                                 points=[[rnd(x), rnd(z)] for x, z in simplify(Q, 1.5)]))
        if tags.get("waterway") in ("river", "canal") and e["type"] == "way":
            pts = geom(e, F)
            if len(pts) >= 2:
                w = num(tags.get("width", "")) or (40.0 if tags["waterway"] == "river" else 15.0)
                out.setdefault("waterways", []).append(dict(way=e["id"], width=rnd(w),
                                                            points=[[rnd(x), rnd(z)] for x, z in simplify(pts, 3.0)]))
        if tags.get("highway") in ("motorway", "trunk", "primary", "secondary") and e["type"] == "way":
            pts = geom(e, F)
            if len(pts) >= 2 and min(math.hypot(x, z) for x, z in pts) > NEAR_RADIUS:
                lanes, lw = ROADS[tags["highway"]]
                try:
                    lanes = max(1, int(str(tags.get("lanes", "")).split(";")[0]))
                except ValueError:
                    lanes = lanes * (1 if tags.get("oneway") == "yes" else 2)
                out.setdefault("far_roads", []).append(dict(way=e["id"], kind=tags["highway"], lanes=lanes,
                                                            width=rnd(lanes * lw + 1.0),
                                                            points=[[rnd(x), rnd(z)] for x, z in simplify(pts, 4.0)]))
    for _order, mask, cls in sorted(layers, key=lambda t: t[0]):
        grid[mask] = cls
    out["landuse"] = dict(cell=GRID_CELL, radius=FAR_RADIUS, rows=["".join(r) for r in grid])
    # the skyline: tall buildings to 15 km (bearing, angular width and elevation angle from the centre)
    sky = []
    for e in tall["elements"]:
        tags = e.get("tags", {})
        if e["id"] in skip:
            continue
        h = height_of(tags)
        bb = e.get("bounds")
        if not h or not bb:
            continue
        clat, clon = (bb["minlat"] + bb["maxlat"]) / 2, (bb["minlon"] + bb["maxlon"]) / 2
        brg, dist = F.bearing_of(clat, clon)
        if dist < NEAR_RADIUS:
            continue
        w = math.hypot((bb["maxlon"] - bb["minlon"]) * F.kx, (bb["maxlat"] - bb["minlat"]) * F.ky) * 0.6
        sky.append([round(brg, 2), round(math.degrees(math.atan2(max(w, 12.0), dist)), 3),
                    round(math.degrees(math.atan2(h, dist)), 3), round(dist), round(h, 1), e["id"]])
    out["skyline"] = sorted(sky)
    # the terrain horizon from the tiles (zoom 9: about 250 m a pixel at these latitudes)
    out["terrain"], out["site_elevation"] = terrain(F, cache)
    return out


def terrain(F, cache, z=9):
    def tilexy(lat, lon):
        n = 2 ** z
        x = (lon + 180.0) / 360.0 * n
        y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
        return x, y
    dlat = TERRAIN_RADIUS / F.ky
    dlon = TERRAIN_RADIUS / F.kx
    x0, y0 = tilexy(F.lat + dlat, F.lon - dlon)
    x1, y1 = tilexy(F.lat - dlat, F.lon + dlon)
    tx0, tx1, ty0, ty1 = int(x0), int(x1), int(y0), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = tile(z, tx, ty, cache)

    def elev(lat, lon):
        x, y = tilexy(lat, lon)
        px, py = (x - tx0) * 256, (y - ty0) * 256
        i, j = int(py), int(px)
        fy, fx = py - i, px - j
        m = mosaic
        i1, j1 = min(i + 1, m.shape[0] - 1), min(j + 1, m.shape[1] - 1)
        return (m[i, j] * (1 - fx) * (1 - fy) + m[i, j1] * fx * (1 - fy) + m[i1, j] * (1 - fx) * fy + m[i1, j1] * fx * fy)

    e0 = float(elev(F.lat, F.lon))
    prof = []
    ds = np.arange(2000.0, TERRAIN_RADIUS, 250.0)
    for b in range(360):
        br = math.radians(b)
        best = -90.0
        for d in ds:
            lat = F.lat + d * math.cos(br) / F.ky
            lon = F.lon + d * math.sin(br) / F.kx
            drop = d * d / (2 * EARTH_R) * (1 - REFRACTION)
            best = max(best, math.degrees(math.atan2(float(elev(lat, lon)) - e0 - drop, d)))
        prof.append(round(best, 3))
    return prof, round(e0, 1)


#: what the kit can use, and no more (the release carries every layout): roads by class out to these radii, blocks
#: to 750 m, the nearest 1,500 trees, the big far roads only
TRIM_ROADS = {"service": 400.0, "residential": 650.0, "unclassified": 650.0}
TRIM_BIG, TRIM_BLOCKS, TRIM_TREES = 950.0, 750.0, 1500


def trim(doc):
    near = lambda pts: min(math.hypot(*p) for p in pts)  # noqa: E731
    doc["roads"] = [r for r in doc["roads"] if near(r["points"]) <=
                    (TRIM_ROADS.get(r["kind"], 650.0 if r["kind"].endswith("_link") else TRIM_BIG))]
    doc["blocks"] = [b for b in doc["blocks"] if near(b["points"]) <= TRIM_BLOCKS]
    doc["trees"] = sorted(doc["trees"], key=lambda p: (math.hypot(*p), p))[:TRIM_TREES]
    doc["far_roads"] = [r for r in doc.get("far_roads", []) if r["kind"] in ("motorway", "trunk", "primary")]
    return doc


def dump(doc):
    """The layout's canonical text: JSON on one line with sorted keys, a space after every comma and colon (the release
    checker refuses any whitespace-free run over 4,096 characters, a guard against embedded blobs), one trailing
    newline."""
    return json.dumps(doc, sort_keys=True, separators=(", ", ": ")) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("venue"); ap.add_argument("lat", type=float); ap.add_argument("lon", type=float)
    ap.add_argument("bearing", type=float)
    ap.add_argument("--cache", default="/media/noah/Storage/.b76-research/st3/env/osm")
    ap.add_argument("--shift", nargs=2, type=float, default=(0.0, 0.0), help="metres added to x and z (the model's own "
                    "frame, fitted on its outline)")
    ap.add_argument("--exclude", nargs="*", type=int, default=(), help="OSM ids the stadium draws itself")
    a = ap.parse_args(argv)
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    doc = build_layout(a.venue, a.lat, a.lon, a.bearing, cache, shift=a.shift, exclude=a.exclude)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = trim(doc)
    p = OUT_DIR / f"{a.venue}.json"
    p.write_text(dump(doc), encoding="utf-8", newline="\n")
    print(p, {k: len(v) for k, v in doc.items() if isinstance(v, list)}, "site", doc["site_elevation"])


if __name__ == "__main__":
    sys.exit(main())
