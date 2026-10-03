"""SoFi Stadium model (experimental): SoFi Stadium built from scratch as the stadium scene of the Rams (s23) and the
Chargers (s24) venue records, all eighteen bundles (day, afternoon, night; dry, rain, snow), and the nine bundles of
the first Super Bowl venue (s40: Super Bowl LXI is played at SoFi Stadium, main's option 1).

Job u6 (2026-09-24), after u5's MetLife model and with its builder. References (HKS drawings, the official level
maps, OpenStreetMap, satellite imagery, 118 Commons photos) and the measured frame are in the u6 report. The scene:

* the bowl sunk 30.5 m (100 ft) below grade, in SoFi's tier stack: the field wall and field-level clubs, the 100
  level, the 200 level over it, the suite levels 4 and 5 on the sidelines, the thin 300 level, the terrace suites
  (level 7) and the 400/500 level, with LED ribbons on the fascias and crowd billboards in the retail convention;
* the canopy: the ETFE roof over the OpenStreetMap ETFE outline (a shallow vault inside the compression ring, falling
  along the plaza tail), the aluminium edge band out to the canopy's outline, whose lip follows the HKS elevations
  (on the ground at the north corners, the south-west corner and the south-east point, up to about 47 m between
  them), the compression ring, the 37 primary columns, the operable panels and the two roof wordmarks;
* the Infinity Screen: the oval ring 110 x 59 m, bottom 36.6 m (120 ft) above the field, the 40 ft inner board and
  the 28 ft outer board over the speaker band, with the live feed on the ``jumbo_tron`` material the game draws into,
  team panels, the score and clock digits, and the SoFi Stadium band;
* the ring of sports lights under the roof, with the light-glow and flare markers moved onto it (indoors the flare
  markers are the player-shadow lights);
* outside: the facades under the canopy, the plaza at grade, Rivers Lake, the YouTube Theater, NFL Media, the Kia
  Forum, the SoFi Stadium lettering on the canopy edge, and a far sky backdrop (the Rams' retail dome bundles carry no
  sky texture);
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the screen), the markers and the materials the
  executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x plan west on the broadcast side; y up from the field; z along, +z plan north
toward azimuth 329.2 degrees) and centimetres in the game. EXPERIMENTAL and UNWITNESSED in game unless a report says
otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

import hashlib
import json
from . import exact_math as math
import struct
from pathlib import Path

class _LazyNumpy:
    # b76 u6, as main's bb9448867 for the MetLife model: the Build panel imports this module for its caption and help
    # text, and both studios must open every page without numpy (tests/mod_editor/test_numpy_optional.py). numpy loads
    # on first use, when a model is built.
    def __getattr__(self, name):
        import numpy
        globals()["np"] = numpy
        return getattr(numpy, name)


np = _LazyNumpy()

from . import nfl2k5_metlife_model as mm
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_stadium_environment as env

OWNER = "nfl2k5_sofi_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_sofi_model"
ART_DIR = DATA_DIR / "art"
#: the private portrait panels (main, 2026-09-24): the Infinity Screen's team panels with the featured players' official
#: 2026 portraits live in this gitignored hydration folder, never in the repo or a release; when they are present and
#: are the ones the pins were recorded from, the build uses them, otherwise the committed panels (team colour, number,
#: name and club mark). tools/nfl2k5_sofi_model_art.py writes both.
PRIVATE_ART = ROOT / "mod_editor" / "assets" / "nfl2k5_sofi_model"
#: None: use the private panels when present and pinned; True or False: force (author time and tests)
USE_PORTRAITS = None
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUES = ("s23", "s24")
#: the first Super Bowl venue (the executable's season index 0, row s40): Super Bowl LXI at SoFi Stadium (main's option
#: 1): the same model in the nine s40 bundles, with the LXI mark and the NFL shield for the team marks
SUPER_BOWL = "s40"
MODEL_VENUES = VENUES + (SUPER_BOWL,)
GRADE = 30.5                         # the bowl is sunk 100 ft below grade (HKS, Walter P Moore)
_FOOTPRINT = None

Mesh, plan_loop, blend = mm.Mesh, mm.plan_loop, mm.blend
toward_field, up_toward_field, up, down = mm.toward_field, mm.up_toward_field, mm.up, mm.down


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


# ------------------------------------------------------------------------------------------------ parameters

PARAMS = dict(
    loop=dict(W=40.0, L=67.5, R=22.0, step=7.0, corner_steps=9),
    wall=dict(height=1.6),
    field_club=dict(height=2.4, setback=1.8, half_length=34.0, ramp=6.0, rows_lost=2),
    lower=dict(rows_side=39, rows_end=35, tread=0.86, rise0=0.30, rise1=0.58, d0=1.2, y0=1.35),
    mid=dict(front_side=21.0, front_end=19.5, fascia_y0=20.3, fascia_h=2.0, rows_side=11, rows_end=16, tread=0.90,
             rise=0.68),
    suites=dict(each=3.3, gap=0.3, recess=1.4),
    up3=dict(front_side=37.0, front_end=35.0, gap=0.3, fascia_h=1.3, rows_side=4, rows_end=11, tread=0.85,
             rise=0.62),
    terrace=dict(height=3.2, recess=0.6),
    up4=dict(front_side=41.5, front_end=46.5, fascia_h=1.3, rows_side=17, rows_end=8, tread=0.88, rise=0.62),
    rim=dict(back_wall=2.2, walk=5.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    #: the seating sections between the aisles (c082: an aisle every 26 to 36 seats): three to a corner, about 15 m
    #: along the straights, symmetric about each straight's middle
    sections=dict(straight_m=15.0, corner=3),
    portals=dict(every_m=26.0, lower_row=11, upper_row=6, width=2.4, height=2.2),
    ring=dict(a=119.0, b=155.0, depth=5.0, width=3.5),       # compression ring half-axes (x, z), construction image
    roof=dict(ring_above_grade=48.0, crown=4.0, tail_start=-180.0, tail_end=-374.0, tail_low=4.0, etfe_rings=9,
              etfe_points=64),
    screen=dict(a=29.5, b=55.0, exponent=2.6, bottom=36.6, inner=12.2, outer=8.5, depth=3.5, segments=64),
    lights=dict(y=66.0, height=0.9, out=1.5),
    columns=dict(count=37, r0=2.2, r1=1.6, sides=10),
)

#: canopy lip heights above grade at points of the outline (x, z, h): the HKS elevations (west, east, north, south)
LIP_ANCHORS = (
    (95.0, 196.0, 0.0),        # north-west wing on the ground
    (97.0, 178.0, 36.0),       # north lip near the north-west corner (north elevation)
    (6.0, 176.0, 33.0),
    (-104.0, 162.0, 16.0),
    (-152.0, 150.0, 0.0),      # north-east wing on the ground
    (-140.0, 110.0, 18.0),
    (-120.0, 76.0, 40.0),      # east lip over the colonnade (east elevation)
    (-116.0, -30.0, 38.0),
    (-110.0, -172.0, 33.0),
    (-106.0, -278.0, 12.0),
    (-105.0, -374.0, 0.0),     # south-east point on the ground
    (40.0, -250.0, 20.0),
    (75.0, -178.0, 44.0),      # the high south-west opening (west elevation; under the roof top)
    (128.0, -128.0, 0.0),      # south-west corner on the ground
    (143.0, 20.0, 29.0),       # west lip over the west stands
    (122.0, 153.0, 11.0),
)


# ------------------------------------------------------------------------------------------------ helpers

def _ring_polyline(points, n):
    """Resample a closed polyline to n points by arc length; returns (points, normalised arc position)."""
    P = np.asarray(points, float)
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
    C = np.vstack([P, P[:1]])
    seg = math.np_norm(np.diff(C, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    out, pos = [], []
    for k in range(n):
        u = total * k / n
        i = min(int(np.searchsorted(cum, u, side="right") - 1), len(seg) - 1)
        t = (u - cum[i]) / max(seg[i], 1e-9)
        out.append(C[i] * (1 - t) + C[i + 1] * t)
        pos.append(u / total)
    return np.array(out), np.array(pos)


def _ccw(P):
    """Order a closed polyline counter-clockwise seen from above (+y), with +x plan west and +z plan north."""
    P = np.asarray(P, float)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    return P if area > 0 else P[::-1]


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
    """Ear clipping of a simple polygon (list of (x, z)); returns index triples."""
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


def superellipse(a, b, e, n, phase=0.0):
    """Points of |x/a|^e + |z/b|^e = 1, counter-clockwise from +x."""
    out = []
    for k in range(n):
        t = phase + 2 * math.pi * k / n
        c, s = math.cos(t), math.sin(t)
        out.append((a * math.copysign(math.pow(abs(c), 2 / e), c), b * math.copysign(math.pow(abs(s), 2 / e), s)))
    return out


# ------------------------------------------------------------------------------------------------ the model

class SoFi(mm.MetLife):
    SECTORS = 12

    def __init__(self, params=None, venue="s23"):
        p = json.loads(json.dumps(PARAMS))
        for k, v in (params or {}).items():
            p[k].update(v)
        self.p, self.venue = p, venue
        size = art_manifest().get(f"LIGHT_sf_screen_{venue}", {}).get("size") or [256, 64]
        self.panel_aspect = size[0] / size[1]                  # the screen panels tile at their own aspect: no stretch
        q = p["loop"]
        self.loop = plan_loop(q["W"], q["L"], q["R"], q["step"], q["corner_steps"])
        self.aisles = self._aisle_positions()
        self.meshes = {}
        self.markers = {}

    # -- the aisles (after lab 4 and c082: the bowl read as one unbroken smear of crowd) ------------------------
    def _aisle_positions(self):
        """Wall-line arc lengths (m) of the aisles: the ends of every straight and corner, three sections to a corner
        and sections of about ``straight_m`` along the straights, symmetric about each straight's middle. An aisle
        within 0.4 of a loop step of a loop point sits on it (the crowd then only moves that point's column)."""
        loop, q = self.loop, self.p["sections"]
        n = len(loop) - 1

        def flat(t):                                   # the segment from point t to t + 1 is on a straight
            return abs(loop[t].nx - loop[t + 1].nx) + abs(loop[t].nz - loop[t + 1].nz) < 1e-9

        pieces, i = [], 0
        while i < n:
            straight = flat(i)
            j = i + 1
            while j < n and flat(j) == straight:
                j += 1
            pieces.append((i, j, straight))
            i = j
        out = set()
        for a, b, straight in pieces:
            s0, s1 = loop[a].s, loop[b].s
            count = max(1, int(round((s1 - s0) / q["straight_m"]))) if straight else q["corner"]
            for k in range(count + 1):
                x = s0 + (s1 - s0) * k / count
                near = min(range(a, b + 1), key=lambda t: abs(loop[t].s - x))
                step = (s1 - s0) / max(1, b - a)
                out.add(round(loop[near].s if abs(loop[near].s - x) <= 0.4 * step else x, 6))
        total = loop[n].s
        out = sorted({0.0 if abs(x - total) < 1e-6 else x for x in out})
        return out + [total] if out[0] == 0.0 else out

    def aisle_u(self, s):
        """The seat texture's u at wall-line arc length ``s``: one repeat per section, 0 at every aisle (the texture's
        steps are centred on u = 0)."""
        A = self.aisles if self.aisles[0] == 0.0 else [self.aisles[-1] - self.loop[-1].s] + self.aisles
        return float(np.interp(s, A, np.arange(len(A), dtype=float)))

    def _aisle_cuts(self, loop):
        """[(segment index, fraction)] of the aisles on one run of the loop (the run's own segments)."""
        out = []
        for a in self.aisles:
            for i in range(len(loop) - 1):
                s0, s1 = loop[i].s, loop[i + 1].s
                if s0 - 1e-6 <= a <= s1 + 1e-6:
                    out.append((i, float(np.clip((a - s0) / max(s1 - s0, 1e-9), 0.0, 1.0))))
                    break
        return out

    def _crowd(self, m, loop, profiles, *, standing=False):
        """u5's crowd billboards, cut at every aisle: each band stops half an aisle short of it and starts again half an
        aisle past it, measured along the band itself, so the seat texture's steps show between the sections."""
        q = dict(self.p["crowd"])
        if standing:
            # A deck is a floor, not a tall pair of seating rows. Put a
            # person-height billboard on each floor without spanning its riser.
            q.update(rows_per_band=1, lean=0.0)
        half = q["aisle"] / 2.0
        R = max(len(pr) for pr in profiles) - 1
        cuts = self._aisle_cuts(loop)
        for b, k in enumerate(range(0, R, q["rows_per_band"])):
            quarter = [0.0, 0.5, 0.25, 0.75][b % 4]
            bot, top, vs = [], [], []
            for lp, pr in zip(loop, profiles):
                last = len(pr) - 1
                d0, y0 = pr[min(k, last)]
                d1, y1 = pr[min(k + q["rows_per_band"], last)]
                # a profile without this band collapses the billboard to zero height at its last row
                h = 0.0 if k >= last else (1.8 if standing else min((y1 - y0) + q["extra"], 2.8))
                bot.append(self.at(lp, d0 + 0.15, y0 + q["lift"]))
                top.append(self.at(lp, d0 + 0.15 + q["lean"] * (d1 - d0), y0 + q["lift"] + h))
                vs.append(lp.s * q["v_per_m"])
            bot, top, vs = np.array(bot), np.array(top), np.array(vs)
            L = np.concatenate([[0.0], np.cumsum(math.np_norm(np.diff(bot, axis=0), axis=1))])
            # The upper rows and corners are longer than the field-wall line.
            # Using lp.s there stretched the fan atlas several times wider.
            vs = (loop[0].s + L) * q["v_per_m"]
            aisles = [L[i] + t * (L[i + 1] - L[i]) for i, t in cuts]
            edges = [0.0] + [e for a in aisles for e in (a - half, a + half)] + [L[-1]]

            def at(x, P):
                j = int(np.clip(np.searchsorted(L, x, side="right") - 1, 0, len(L) - 2))
                t = (x - L[j]) / max(L[j + 1] - L[j], 1e-9)
                return P[j] + (P[j + 1] - P[j]) * t

            for e0, e1 in zip(edges[0::2], edges[1::2]):
                e0, e1 = max(e0, 0.0), min(e1, L[-1])
                if e1 - e0 < 0.3:
                    continue
                cols = [e0] + [x for x in L if e0 + 1e-6 < x < e1 - 1e-6] + [e1]
                pb, pt = [tuple(at(x, bot)) for x in cols], [tuple(at(x, top)) for x in cols]
                vv = [float(at(x, vs)) for x in cols]
                m.grid("crowd", [pb, pt], [[(quarter + 0.2425, v) for v in vv], [(quarter + 0.0075, v) for v in vv]],
                       facing=toward_field)

    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
        """u5's seating surface every ``seats.rows_per_grid`` rows (the crowd hides the rest; the vertices saved pay
        for the aisles), with u one texture repeat per section so the texture's steps lie under every aisle."""
        rows = self.p["seats"]["rows_per_grid"]
        R = max(len(pr) for pr in profiles) - 1
        ks = list(range(0, R + 1, rows))
        if ks[-1] != R:
            ks.append(R)
        pts = [[self.at(lp, *pr[min(k, len(pr) - 1)]) for lp, pr in zip(loop, profiles)] for k in ks]
        uvs = [[(self.aisle_u(lp.s), vstart + min(k, len(pr) - 1) / self.p["seats"]["rows_per_v"])
                for lp, pr in zip(loop, profiles)] for k in ks]
        m.grid(material, pts, uvs, facing=up_toward_field)

    def mesh(self, name):
        if name.startswith("sf_bowl_"):
            name = getattr(self, "prefix", "sf_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the section: SoFi's tier stack, blended from sideline to end -----------------------------------------
    def section(self, lp):
        p = self.p
        side = lp.side
        out = {}
        # field wall and the field-level clubs on the sidelines (Pechanga Founders Club west, SoFi Social Club east)
        q = p["lower"]
        rows = int(round(blend(side, q["rows_side"], q["rows_end"])))
        d, y = q["d0"], q["y0"]
        fc = p["field_club"]
        club = side * float(np.clip((fc["half_length"] - abs(lp.z)) / fc["ramp"], 0.0, 1.0))
        if club > 0.0:
            out["field_club"] = (0.35, p["wall"]["height"], p["wall"]["height"] + fc["height"] * club)
            d += fc["setback"] * club
            y += fc["height"] * club
            rows = max(1, rows - int(round(fc["rows_lost"] * club)))
        lower = [(d, y)]
        for i in range(rows):
            t = i / max(1, rows - 1)
            d += q["tread"]
            y += q["rise0"] + (q["rise1"] - q["rise0"]) * t * t
            lower.append((d, y))
        out["lower"] = lower
        # the 200 level hangs over the back of the 100 level
        q2 = p["mid"]
        mfront = blend(side, q2["front_side"], q2["front_end"])
        fy0 = q2["fascia_y0"]
        out["mid_fascia"] = (mfront, fy0, fy0 + q2["fascia_h"])
        dback = lower[-1][0] + 0.6
        out["lower_back"] = (dback, lower[-1][1], fy0 - 0.02)
        out["mid_soffit"] = (mfront + 0.02, dback, fy0)
        mrows = int(round(blend(side, q2["rows_side"], q2["rows_end"])))
        d, y = mfront + 0.4, fy0 + q2["fascia_h"] + 0.35
        mid = [(d, y)]
        for _i in range(mrows):
            d += q2["tread"]
            y += q2["rise"]
            mid.append((d, y))
        out["mid"] = mid
        # suite levels 4 and 5 on the sidelines (and into the corners as the perch and beach house suites)
        s = p["suites"]
        dsu = mid[-1][0] + s["recess"]
        y = mid[-1][1] + 0.3
        h = s["each"] * side
        if h > 0.05:
            out["suite4"] = (dsu, y, y + h)
            out["suite5"] = (dsu + 0.4, y + h + s["gap"], y + 2 * h + s["gap"])
            out["suites_floor"] = (mid[-1][0], dsu, mid[-1][1])
        ytop = y + 2 * h + s["gap"] * side
        # the 300 level
        q3 = p["up3"]
        f3 = max(blend(side, q3["front_side"], q3["front_end"]), mid[-1][0] + 0.8)
        f3y = max(ytop + q3["gap"], mid[-1][1] + 0.6)
        out["mid_back"] = (mid[-1][0] + 0.5, mid[-1][1], f3y)
        if h > 0.05:
            out["suites_top"] = (out["suite5"][0], out["suite5"][2], f3y)
        out["up3_fascia"] = (f3, f3y, f3y + q3["fascia_h"])
        r3 = int(round(blend(side, q3["rows_side"], q3["rows_end"])))
        d, y = f3 + 0.3, f3y + q3["fascia_h"] + 0.2
        up3 = [(d, y)]
        for _i in range(r3):
            d += q3["tread"]
            y += q3["rise"]
            up3.append((d, y))
        out["up3"] = up3
        out["up3_soffit"] = (f3 + 0.02, max(mid[-1][0] + 0.5, f3 + 0.1), f3y)
        # the terrace suites (level 7) on the sidelines, then the 400/500 level
        t = p["terrace"]
        th = t["height"] * side
        yt = up3[-1][1] + 0.25
        dt = up3[-1][0] + t["recess"]
        if th > 0.05:
            out["terrace"] = (dt, yt, yt + th)
            out["terrace_floor"] = (up3[-1][0], dt, up3[-1][1])
        q4 = p["up4"]
        f4 = max(blend(side, q4["front_side"], q4["front_end"]), up3[-1][0] + 0.8)
        f4y = yt + th + 0.2 if th > 0.05 else up3[-1][1] + 0.5
        out["up3_back"] = (up3[-1][0] + 0.4, up3[-1][1], f4y)
        out["up4_fascia"] = (f4, f4y, f4y + q4["fascia_h"])
        r4 = int(round(blend(side, q4["rows_side"], q4["rows_end"])))
        d, y = f4 + 0.3, f4y + q4["fascia_h"] + 0.2
        up4 = [(d, y)]
        for _i in range(r4):
            d += q4["tread"]
            y += q4["rise"]
            up4.append((d, y))
        out["up4"] = up4
        out["up4_soffit"] = (f4 + 0.02, max(up3[-1][0] + 0.4, f4 + 0.1), f4y)
        rim = p["rim"]
        out["rim"] = (d + 0.3, y, y + rim["back_wall"], d + 0.3 + rim["walk"])
        # outside face of the bowl under the canopy, from grade to the rim walk
        out["facade"] = (d + 0.3 + rim["walk"], GRADE, y + rim["back_wall"])
        return out

    # -- build ---------------------------------------------------------------------------------------------
    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"sf_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "sf"
        self._canopy()
        self._columns()
        self._screen()
        self._lights(loop, secs)
        self._end_signs(loop, secs)
        west = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow((lp.z - 20.0) / 40.0, 2))
        row = self.section(west)["up4"][4]
        self.nosebleed = self.at(west, row[0] + 0.3, row[1] + 0.05)
        self._exterior(loop, secs)
        self._surroundings()
        self._sky()
        self._signs()
        for name in ("sf_etfe_under", "sf_etfe_top", "sf_band"):
            self._split_by_angle(name, 6)
        return self

    # -- the bowl ------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("sf_bowl_a")
        wall = p["wall"]["height"]
        m.grid("LIGHT_sf_ribbon", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.5) for lp in loop]], facing=toward_field)
        m.grid("sf_concrete", [[(lp.x, wall, lp.z) for lp in loop],
                               [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]],
               [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]], facing=up_toward_field)
        self._band(m, "LIGHT_sf_glass", loop, secs, "field_club", 0.0, 1.0, u_per_m=1 / 8.0)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "sf_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_sf_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        # the 200 level
        m2 = self.mesh("sf_bowl_b")
        self._ledge(m2, "sf_concrete", loop, secs, "mid_soffit", down)
        self._band(m2, "LIGHT_sf_ribbon", loop, secs, "mid_fascia", 0.0, 0.5, u_per_m=1 / (8 * p["mid"]["fascia_h"]))
        mid = [sec["mid"] for sec in secs]
        self._rows_surface(m2, "sf_seat", loop, mid, 2)
        self._crowd(m2, loop, mid)
        self._band(m2, "LIGHT_sf_concourse", loop, secs, "mid_back", 0.0, 1.0, u_per_m=1 / 8.0)
        self._band(m2, "LIGHT_sf_glass", loop, secs, "suite4", 0.0, 1.0, u_per_m=1 / 8.0)
        self._band(m2, "LIGHT_sf_glass", loop, secs, "suite5", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "sf_concrete", loop, secs, "suites_floor", up)
        self._band(m2, "sf_concrete", loop, secs, "suites_top", 0.0, 0.5, u_per_m=1 / 8.0)
        # the 300 level, the terrace suites and the 400/500 level
        m3 = self.mesh("sf_bowl_c")
        self._ledge(m3, "sf_concrete", loop, secs, "up3_soffit", down)
        self._band(m3, "LIGHT_sf_ribbon", loop, secs, "up3_fascia", 0.0, 0.5, u_per_m=1 / (8 * p["up3"]["fascia_h"]))
        up3 = [sec["up3"] for sec in secs]
        self._rows_surface(m3, "sf_seat", loop, up3, 2)
        self._crowd(m3, loop, up3)
        self._band(m3, "LIGHT_sf_concourse", loop, secs, "up3_back", 0.0, 1.0, u_per_m=1 / 8.0)
        self._band(m3, "LIGHT_sf_glass", loop, secs, "terrace", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m3, "sf_concrete", loop, secs, "terrace_floor", up)
        self._ledge(m3, "sf_concrete", loop, secs, "up4_soffit", down)
        self._band(m3, "LIGHT_sf_ribbon", loop, secs, "up4_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["up4"]["fascia_h"]))
        up4 = [sec["up4"] for sec in secs]
        self._rows_surface(m3, "sf_seat", loop, up4, 2)
        self._crowd(m3, loop, up4)
        self._portals(m3, loop, secs, "up4", p["portals"]["upper_row"])
        m4 = self.mesh("sf_bowl_d")
        # the rim's back wall: the top concourse behind its glass rail, under the canopy (c082)
        m4.grid("LIGHT_sf_concourse", [[self.at(lp, sec["rim"][0], sec["rim"][1]) for lp, sec in zip(loop, secs)],
                                       [self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 1.0) for lp in loop], [(lp.s / 8, 0.0) for lp in loop]], facing=toward_field)
        m4.grid("sf_concrete", [[self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)],
                                [self.at(lp, sec["rim"][3], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.4) for lp in loop]], facing=up)
        # the outside face of the bowl, from grade to the rim walk (glass and white bands, lit at night)
        m4.grid("LIGHT_sf_facade", [[self.at(lp, sec["facade"][0], sec["facade"][1]) for lp, sec in zip(loop, secs)],
                                    [self.at(lp, sec["facade"][0], sec["facade"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 16, 1.0) for lp in loop], [(lp.s / 16, 0.0) for lp in loop]],
                facing=lambda p: -toward_field(p))

    def _portals(self, m, loop, secs, key, row):
        q = self.p["portals"]
        every = q["every_m"]
        for a, b, sa, sb_ in zip(loop[:-1], loop[1:], secs[:-1], secs[1:]):
            k0, k1 = math.floor(a.s / every), math.floor(b.s / every)
            if k1 == k0:
                continue
            t = (k1 * every - a.s) / max(b.s - a.s, 1e-9)
            pa, pb = sa[key], sb_[key]
            if row >= len(pa) - 1 or row >= len(pb) - 1:
                continue
            d = pa[row][0] * (1 - t) + pb[row][0] * t
            y = pa[row][1] * (1 - t) + pb[row][1] * t
            x0, z0 = a.x * (1 - t) + b.x * t, a.z * (1 - t) + b.z * t
            nx, nz = a.nx * (1 - t) + b.nx * t, a.nz * (1 - t) + b.nz * t
            nn = math.hypot(nx, nz)
            nx, nz = nx / nn, nz / nn
            c = np.array([x0 + nx * (d - 0.05), y, z0 + nz * (d - 0.05)])
            tv = np.array([-nz, 0.0, nx]) * (q["width"] / 2)
            h = np.array([0.0, q["height"], 0.0])
            n = np.array([nx, 0.0, nz])
            m.quad("sf_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p, n=n: -n)

    # -- the canopy ------------------------------------------------------------------------------------------
    def roof_height(self, x, z):
        """Top of the ETFE roof above the field: a shallow vault inside the compression ring, level over the plaza,
        falling along the tail to the south-east point (the HKS east and west elevations)."""
        q, r = self.p["ring"], self.p["roof"]
        re = math.hypot(x / q["a"], z / q["b"])
        if re <= 1.0:
            return GRADE + r["ring_above_grade"] + r["crown"] * (1.0 - re * re)
        y = r["ring_above_grade"]
        if z < r["tail_start"]:
            t = min(1.0, (r["tail_start"] - z) / (r["tail_start"] - r["tail_end"]))
            y = y + (r["tail_low"] - y) * t
        return GRADE + y

    def lip_heights(self, pts):
        """Canopy lip height above grade at each outline point: the HKS elevation anchors, interpolated along the
        outline between the anchors nearest to each point."""
        P = np.asarray(pts, float)
        n = len(P)
        seg = math.np_norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])[:-1]
        total = seg.sum()
        anchors = []
        for ax, az, h in LIP_ANCHORS:
            i = int(np.argmin(np.square(P[:, 0] - ax) + np.square(P[:, 1] - az)))
            anchors.append((cum[i], h))
        anchors.sort()
        s_a = [a for a, _ in anchors]
        h_a = [h for _, h in anchors]
        s_ext = [s_a[-1] - total] + s_a + [s_a[0] + total]
        h_ext = [h_a[-1]] + h_a + [h_a[0]]
        # smooth arches between the anchors (the elevations' lips curve; linear steps made sharp V's)
        out = np.empty(len(cum))
        for k, sv in enumerate(cum):
            j = int(np.searchsorted(s_ext, sv, side="right")) - 1
            j = min(max(j, 0), len(s_ext) - 2)
            t = (sv - s_ext[j]) / max(s_ext[j + 1] - s_ext[j], 1e-9)
            w = 0.5 - 0.5 * math.cos(math.pi * t)
            out[k] = h_ext[j] + (h_ext[j + 1] - h_ext[j]) * w
        return out

    def _canopy(self):
        fp = footprint()
        r = self.p["roof"]
        etfe = _ccw(np.array(fp["etfe"], float))
        outer = _ccw(np.array(fp["canopy_outer"], float))
        N, K = r["etfe_points"], r["etfe_rings"]
        # ETFE boundary sampled by angle from the field centre (the zone is star-shaped from there)
        angs = np.linspace(0, 2 * math.pi, N, endpoint=False)
        boundary = []
        for a in angs:
            d = np.array([math.cos(a), math.sin(a)])
            best = None
            for i in range(len(etfe)):
                p0, p1 = etfe[i], etfe[(i + 1) % len(etfe)]
                e = p1 - p0
                den = d[0] * (-e[1]) - d[1] * (-e[0])
                if abs(den) < 1e-12:
                    continue
                t = (p0[0] * (-e[1]) - p0[1] * (-e[0])) / den
                u = (d[0] * p0[1] - d[1] * p0[0]) / den
                if t > 0 and 0 <= u <= 1 and (best is None or t < best):
                    best = t
            boundary.append(d * (best if best is not None else 100.0))
        boundary = np.array(boundary)
        self.etfe_boundary = boundary
        grid = [[(bx * k / K, bz * k / K) for bx, bz in list(boundary) + [boundary[0]]] for k in range(K + 1)]
        under = [[(x, self.roof_height(x, z) - 0.6, z) for x, z in row] for row in grid]
        top = [[(x, self.roof_height(x, z), z) for x, z in row] for row in grid]
        uv = [[(x / 24.0, z / 24.0) for x, z in row] for row in grid]
        self.meshes.setdefault("sf_etfe_under", Mesh("sf_etfe_under")).grid("sf_etfe_under", under, uv, facing=down)
        self.meshes.setdefault("sf_etfe_top", Mesh("sf_etfe_top")).grid("sf_etfe_top", top, uv, facing=up)
        # the aluminium band: from the ETFE boundary out and down to the canopy lip (the HKS elevations)
        O, _pos = _ring_polyline(outer, 104)
        lip = self.lip_heights(O)
        band = self.meshes.setdefault("sf_band", Mesh("sf_band"))
        inner = []
        for ox, oz in O:
            j = int(np.argmin(np.square(boundary[:, 0] - ox) + np.square(boundary[:, 1] - oz)))
            # project onto the ETFE boundary polyline near j
            best, bp = None, None
            for jj in (j - 1, j):
                p0, p1 = boundary[jj % N], boundary[(jj + 1) % N]
                e = p1 - p0
                t = float(np.clip(math.np_dot([ox, oz] - p0, e) / max(math.np_dot(e, e), 1e-9), 0, 1))
                q_ = p0 + e * t
                dd = math.pow(q_[0] - ox, 2) + math.pow(q_[1] - oz, 2)
                if best is None or dd < best:
                    best, bp = dd, q_
            inner.append(bp)
        inner = np.array(inner)
        rows_top, rows_under, uvs = [], [], []
        for f in (0.0, 0.2, 0.4, 0.6, 0.8, 0.92, 1.0):
            rt, ru, uu = [], [], []
            for (ix, iz), (ox, oz), h in zip(list(inner) + [inner[0]], list(O) + [O[0]], list(lip) + [lip[0]]):
                x, z = ix + (ox - ix) * f, iz + (oz - iz) * f
                y0 = self.roof_height(ix, iz)
                y1 = GRADE + h
                # the shell: level off the roof, then a steep curl down to the lip (the aerials)
                y = y0 + (y1 - y0) * math.pow(f, 3.0)
                rt.append((x, y, z))
                ru.append((x, y - 0.8 * (1 - f), z))
                uu.append((x / 18.0, z / 18.0))
            rows_top.append(rt)
            rows_under.append(ru)
            uvs.append(uu)
        band.grid("sf_alu", rows_top, uvs, facing=lambda p: up(p) - toward_field(p) * 0.3)
        band.grid("sf_alu", rows_under, uvs, facing=lambda p: down(p) + toward_field(p) * 0.3)
        self.lip = (O, lip)

    def _columns(self):
        q, c = self.p["ring"], self.p["columns"]
        m = self.meshes.setdefault("sf_columns", Mesh("sf_columns"))
        # the compression ring (a box truss) and the 37 primary columns on it
        pts = superellipse(q["a"], q["b"], 2.0, 96)
        ring_top = [(x, self.roof_height(x, z) - 0.8, z) for x, z in pts]
        outer = [(x * 1.015, y, z * 1.015) for x, y, z in ring_top]
        inner = [(x * 0.985, y, z * 0.985) for x, y, z in ring_top]
        low = lambda P: [(x, y - q["depth"], z) for x, y, z in P]  # noqa: E731
        close = lambda P: P + [P[0]]  # noqa: E731
        uv = lambda P: [(i / 4.0, 0.0) for i in range(len(P))]  # noqa: E731
        m.grid("sf_white", [close(low(outer)), close(outer)], [uv(close(outer)), [(u, 1.0) for u, _ in uv(close(outer))]],
               facing=lambda p: -toward_field(p))
        m.grid("sf_white", [close(low(inner)), close(inner)], [uv(close(inner)), [(u, 1.0) for u, _ in uv(close(inner))]],
               facing=toward_field)
        m.grid("sf_white", [close(low(inner)), close(low(outer))], [uv(close(inner)), [(u, 1.0) for u, _ in uv(close(inner))]],
               facing=down)
        cols = superellipse(q["a"] * 1.0, q["b"] * 1.0, 2.0, c["count"], phase=math.pi / c["count"])
        self.column_points = cols
        for x, z in cols:
            ytop = self.roof_height(x, z) - q["depth"]
            ring0 = [(x + c["r0"] * math.cos(2 * math.pi * k / c["sides"]), GRADE, z + c["r0"] * math.sin(2 * math.pi * k / c["sides"]))
                     for k in range(c["sides"] + 1)]
            ring1 = [(x + c["r1"] * math.cos(2 * math.pi * k / c["sides"]), ytop, z + c["r1"] * math.sin(2 * math.pi * k / c["sides"]))
                     for k in range(c["sides"] + 1)]
            m.grid("sf_white", [ring0, ring1], [[(k / c["sides"], 1.0) for k in range(c["sides"] + 1)],
                                                [(k / c["sides"], 0.0) for k in range(c["sides"] + 1)]],
                   facing=lambda p, x=x, z=z: np.array([p[0] - x, 0.0, p[2] - z]))

    # -- the Infinity Screen -----------------------------------------------------------------------------------
    #: the live feed fills u 0 to 0.625, v 0 to 0.875 of the jumbo_tron render target (a 640 x 448 picture shown at
    #: about 4:3; PROVED OFFLINE from the retail s23 and s24 screens). The windows show its 16:9 crop, never stretched.
    FEED_U = (0.0, 0.625)
    FEED_V = (0.109, 0.766)
    #: the flanking windows show the same live picture 1.5x closer (a 16:9 crop of the crop, centred a little low,
    #: where the play is): the game-day photos (c018, c105) show the ring as several video windows side by side
    ZOOM_U = (0.3125 - 0.3125 / 1.5, 0.3125 + 0.3125 / 1.5)
    ZOOM_V = (0.46 - 0.3285 / 1.5, 0.46 + 0.3285 / 1.5)
    WINDOW_GAP = 1.0                             # metres of black between two windows
    FEED_ASPECT = 16.0 / 9.0

    def _screen(self):
        q = self.p["screen"]
        n = q["segments"]
        y0, y_sp, y1 = q["bottom"], q["bottom"] + (q["inner"] - q["outer"]), q["bottom"] + q["inner"]
        m = self.meshes.setdefault("sf_screen", Mesh("sf_screen"))
        self.screen_panels = []
        faces = (("outer", q["a"], q["b"], y_sp, y1, 1.0), ("inner", q["a"] - q["depth"], q["b"] - q["depth"], y0, y1, -1.0))
        rims = {}
        for face, a, b, fy0, fy1, outward in faces:
            loop = np.array(superellipse(a, b, q["exponent"], 720))
            seg = math.np_norm(np.diff(np.vstack([loop, loop[:1]]), axis=0), axis=1)
            cum = np.concatenate([[0], np.cumsum(seg)])
            per = cum[-1]
            h = fy1 - fy0
            W = h * self.FEED_ASPECT
            # live windows on each long side (the west side's middle is s = 0, the east side's per / 2): the full
            # picture in the middle and the closer picture either side, each 16:9 along the curve; on the outer board
            # the score and clock strip (``adjust_digits``, the game's own live digits) takes the place of the
            # window after the middle one, as the game-day photos show a score panel beside the video
            windows = []
            for s_c in (0.0, per / 2):
                windows.append((s_c, self.FEED_U, self.FEED_V))
                for side in ((-1.0,) if face == "outer" else (-1.0, 1.0)):
                    windows.append(((s_c + side * (W + self.WINDOW_GAP)) % per, self.ZOOM_U, self.ZOOM_V))

            def signed(sv, c, per=per):
                return ((sv - c + per / 2) % per) - per / 2

            cuts = sorted(set([per * k / n for k in range(n)]
                              + [(c + e) % per for c, _u, _v in windows for e in (-W / 2, W / 2)]))

            def at(sv, loop=loop, cum=cum, per=per):
                sv = sv % per
                i = min(int(np.searchsorted(cum, sv, side="right") - 1), len(loop) - 1)
                t = (sv - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
                return loop[i] * (1 - t) + loop[(i + 1) % len(loop)] * t

            rims[face] = (at, per)
            for k, sa in enumerate(cuts):
                sb_ = cuts[(k + 1) % len(cuts)] + (per if k == len(cuts) - 1 else 0.0)
                smid = 0.5 * (sa + sb_)
                pa, pb = at(sa), at(sb_)
                A0, B0 = np.array([pa[0], fy0, pa[1]]), np.array([pb[0], fy0, pb[1]])
                A1, B1 = np.array([pa[0], fy1, pa[1]]), np.array([pb[0], fy1, pb[1]])
                c_out = np.array([(pa[0] + pb[0]) / 2, 0.0, (pa[1] + pb[1]) / 2]) * outward
                win = next(((c, U, V) for c, U, V in windows if abs(signed(smid, c)) <= W / 2 + 1e-6), None)
                if win is not None:
                    c, U, V = win
                    da = signed(smid, c) - (smid - sa)
                    db = da + (sb_ - sa)
                    # u runs to the viewer's right: against the loop outside, with it inside
                    fa, fb = (da + W / 2) / W, (db + W / 2) / W
                    if outward > 0:
                        fa, fb = 1 - fa, 1 - fb
                    ua, ub = U[0] + (U[1] - U[0]) * fa, U[0] + (U[1] - U[0]) * fb
                    v0, v1 = V
                    m.quad("jumbo_tron", A0, B0, B1, A1, (ua, v1), (ub, v1), (ub, v0), (ua, v0), facing=lambda p, c=c_out: c)
                    self.screen_panels.append((A0, B0, B1, A1))
                else:
                    ua, ub = sa / (self.panel_aspect * h), sb_ / (self.panel_aspect * h)
                    if outward > 0:
                        ua, ub = -ua, -ub
                    m.quad("LIGHT_sf_screen", A0, B0, B1, A1, (ua, 1), (ub, 1), (ub, 0), (ua, 0), facing=lambda p, c=c_out: c)
        # the speaker band under the outer board, the underside, the top and the SoFi Stadium band
        at_o, per_o = rims["outer"]
        at_i, per_i = rims["inner"]
        for k in range(n):
            pa, pb = at_o(per_o * k / n), at_o(per_o * (k + 1) / n)
            ia, ib = at_i(per_i * k / n), at_i(per_i * (k + 1) / n)
            c_out = np.array([(pa[0] + pb[0]) / 2, 0.0, (pa[1] + pb[1]) / 2])
            S0, T0 = np.array([pa[0], y0, pa[1]]), np.array([pb[0], y0, pb[1]])
            S1, T1 = np.array([pa[0], y_sp, pa[1]]), np.array([pb[0], y_sp, pb[1]])
            I0, J0 = np.array([ia[0], y0, ia[1]]), np.array([ib[0], y0, ib[1]])
            U1, V1 = np.array([pa[0], y1, pa[1]]), np.array([pb[0], y1, pb[1]])
            K1, L1 = np.array([ia[0], y1, ia[1]]), np.array([ib[0], y1, ib[1]])
            m.quad("sf_dark", S0, T0, T1, S1, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p, c=c_out: c)
            m.quad("sf_dark", S0, T0, J0, I0, (0, 0), (1, 0), (1, 1), (0, 1), facing=down)
            m.quad("sf_dark", U1, V1, L1, K1, (0, 0), (1, 0), (1, 1), (0, 1), facing=up)
        self.screen_rim = rims
        self.markers["jumbo"] = [(0.0, (y0 + y1) / 2, q["b"] * 0.6), (0.0, (y0 + y1) / 2, -q["b"] * 0.6)]
        # the SoFi Stadium band on the speaker band of each long side (the CFP press-box photo), at its 8:1 aspect
        hb = (y_sp - y0) * 0.72
        for s_c in (0.0, per_o / 2):
            p = at_o(s_c)
            t = at_o(s_c + 0.5) - at_o(s_c - 0.5)
            t = t / math.np_norm(t)
            nrm = np.array([t[1], 0.0, -t[0]])
            if math.np_dot(nrm, [p[0], 0.0, p[1]]) < 0:
                nrm = -nrm
            right = np.cross(-nrm, (0.0, 1.0, 0.0))
            right = right / math.np_norm(right) * (hb * 4.0)
            c = np.array([p[0], y0 + (y_sp - y0) * 0.5 - hb / 2, p[1]]) + nrm * 0.12
            hv = np.array([0.0, hb, 0.0])
            m.quad("sf_letters_screen", c - right, c + right, c + right + hv, c - right + hv, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, f=nrm: f)

    def screen_point(self, face, z_sign, dist):
        """(point on the face at mid-height, outward normal, tangent to the viewer's right) at ``dist`` metres from the
        centre of the long side ``z_sign`` (+1 west side's north half... used for the score strips)."""
        at, per = self.screen_rim[face]
        q = self.p["screen"]
        s_c = 0.0 if z_sign > 0 else per / 2
        p = at(s_c + dist)
        t = at(s_c + dist + 0.5) - at(s_c + dist - 0.5)
        t = t / math.np_norm(t)
        nrm = np.array([t[1], 0.0, -t[0]])
        if math.np_dot(nrm, [p[0], 0.0, p[1]]) < 0:
            nrm = -nrm
        right = np.cross(-nrm, (0.0, 1.0, 0.0))
        y_sp = q["bottom"] + (q["inner"] - q["outer"])
        return np.array([p[0], y_sp + q["outer"] * 0.5, p[1]]), nrm, right / math.np_norm(right)

    # -- the ring of sports lights under the roof ----------------------------------------------------------------
    #: the light banks under the canopy's rim (Noah's reference and the game-day photos: bright banks above the upper
    #: deck, all the way round): panels of BANK_W x BANK_H metres every second loop point, tilted BANK_TILT degrees
    #: down toward the field, lit (the LIGHT class: full white at night and bright by day, the lights are on for games)
    BANK_W, BANK_H, BANK_TILT = 10.0, 3.0, 32.0

    def _lights(self, loop, secs):
        q = self.p["lights"]
        m = self.meshes.setdefault("sf_lights", Mesh("sf_lights"))
        pts = [self.at(lp, sec["rim"][0] + q["out"], q["y"]) for lp, sec in zip(loop, secs)]
        t = math.radians(self.BANK_TILT)
        for k in range(0, len(loop) - 1, 2):
            lp, c = loop[k], np.array(pts[k], float)
            inward = np.array([-lp.nx, 0.0, -lp.nz])
            along = np.array([-lp.nz, 0.0, lp.nx])                          # the loop's tangent
            normal = inward * math.cos(t) + np.array([0.0, -1.0, 0.0]) * math.sin(t)   # faces the field, down
            up = np.cross(along, normal)
            up = up / math.np_norm(up) * (1.0 if up[1] > 0 else -1.0)
            hw, hh = along * (self.BANK_W / 2), up * (self.BANK_H / 2)
            u1 = self.BANK_W / (self.BANK_H * 2.0)                          # the texture is 2:1: no stretch
            m.quad("LIGHT_sf_lights", c - hw - hh, c + hw - hh, c + hw + hh, c - hw + hh, (0, 1), (u1, 1), (u1, 0), (0, 0),
                   facing=lambda p_, n=normal: n)
        self.light_points = [tuple(np.array(p) + [0, 0.5, 0]) for p in pts[:-1]]

    # -- the SoFi Stadium sign at each end ---------------------------------------------------------------------
    def _end_signs(self, loop, secs):
        """SoFi Stadium on the wall behind the top of the lower bowl at each end, facing the field (Noah's reference
        shows the name at the end-zone level; the letters are the official logo, teal SoFi and white Stadium, 8:1)."""
        m = self.meshes.setdefault("sf_signs_end", Mesh("sf_signs_end"))
        for end in (1, -1):
            k = max(range(len(loop) - 1), key=lambda i: end * loop[i].z - abs(loop[i].x) * 0.01)
            lp, sec = loop[k], secs[k]
            d, y0, y1 = sec["lower_back"]
            h = min(4.0, (y1 - y0) * 0.8)
            w = h * 8.0
            c = np.array([0.0, (y0 + y1) / 2, lp.z + lp.nz * (d - 0.15)])
            face = np.array([0.0, 0.0, -float(end)])
            right = np.cross(-face, (0.0, 1.0, 0.0))
            right = right / math.np_norm(right) * (w / 2)
            hv = np.array([0.0, h / 2, 0.0])
            m.quad("sf_letters_screen", c - right - hv, c + right - hv, c + right + hv, c - right + hv,
                   (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)

    # -- outside -------------------------------------------------------------------------------------------------
    def _exterior(self, loop, secs):
        m = self.meshes.setdefault("sf_plaza", Mesh("sf_plaza"))
        # the plaza and the ground at grade: rings from the bowl's outside face out to the site edge
        base = [self.at(lp, sec["facade"][0], GRADE) for lp, sec in zip(loop, secs)]
        rings = [base]
        for grow in (18.0, 60.0, 160.0, 420.0, 900.0):
            rings.append([(x + lp.nx * grow, GRADE, z + lp.nz * grow) for (x, _y, z), lp in zip(base, loop)])
        uv = lambda R: [(x / 20.0, z / 20.0) for x, _y, z in R]  # noqa: E731
        m.grid("sf_plaza", rings[:3], [uv(r) for r in rings[:3]], facing=up)
        # Rivers Lake (the water a few centimetres above the plaza so it never fights it)
        fp = footprint()
        lake = [tuple(p) for p in fp["lake"]]
        wm = self.meshes.setdefault("sf_lake", Mesh("sf_lake"))
        tris = _triangulate(lake)
        for i0, i1, i2 in tris:
            a, b, c = ((lake[i][0], GRADE + 0.25, lake[i][1]) for i in (i0, i1, i2))
            ia = wm.v(a, (a[0] / 30.0, a[2] / 30.0), (0, 1, 0))
            ib = wm.v(b, (b[0] / 30.0, b[2] / 30.0), (0, 1, 0))
            ic = wm.v(c, (c[0] / 30.0, c[2] / 30.0), (0, 1, 0))
            n = np.cross(np.array(b) - np.array(a), np.array(c) - np.array(a))
            wm.strip("sf_water", [ia, ib, ic] if n[1] > 0 else [ia, ic, ib])
        # beyond the plaza (60 m out), the shared environment kit (st3, 2026-09-28): the lots with their cars, the
        # roads, Hollywood Park's grass and trees, Inglewood's blocks from OpenStreetMap, the far ground to the haze and
        # the horizon band with Los Angeles' towers; it leaves Rivers Lake and the neighbours drawn here to this model
        plaza = [(x, z) for x, _y, z in rings[2][:-1]] if rings[2][0] == rings[2][-1] else [(x, z) for x, _y, z in rings[2]]
        lk = np.array(lake, float)
        lc = lk.mean(axis=0)
        lake_keep = [tuple(lc + (q - lc) * (1.0 + 8.0 / max(1.0, float(math.np_norm(q - lc))))) for q in lk]
        self.env_counts = env.dress(self, self.venue, grade=GRADE, keep_out=[plaza, lake_keep], inner=plaza,
                                    eyes=env.shot_eyes(sofi_shots(self.venue)))

    def _extrude(self, mesh, poly, y0, y1, material, top_material=None, uscale=1 / 12.0):
        P = [tuple(p) for p in poly]
        if not _point_in_poly(*np.mean(P, axis=0), P):
            pass
        n = len(P)
        cx, cz = np.mean(P, axis=0)
        s = 0.0
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            L = math.dist(a, b)
            A0, B0 = (a[0], y0, a[1]), (b[0], y0, b[1])
            A1, B1 = (a[0], y1, a[1]), (b[0], y1, b[1])
            mid = np.array([(a[0] + b[0]) / 2 - cx, 0.0, (a[1] + b[1]) / 2 - cz])
            mesh.quad(material, A0, B0, B1, A1, (s * uscale, 1), ((s + L) * uscale, 1), ((s + L) * uscale, 0),
                      (s * uscale, 0), facing=lambda p, c=mid: c)
            s += L
        for i0, i1, i2 in _triangulate(P):
            tri = [(P[i][0], y1, P[i][1]) for i in (i0, i1, i2)]
            ids = [mesh.v(t, (t[0] / 20.0, t[2] / 20.0), (0, 1, 0)) for t in tri]
            nrm = np.cross(np.array(tri[1]) - np.array(tri[0]), np.array(tri[2]) - np.array(tri[0]))
            mesh.strip(top_material or material, ids if nrm[1] > 0 else [ids[0], ids[2], ids[1]])

    def _surroundings(self):
        fp = footprint()
        m = self.meshes.setdefault("sf_town", Mesh("sf_town"))
        self._extrude(m, fp["nfl_media"], GRADE, GRADE + 30.0, "LIGHT_sf_facade", "sf_white")
        self._extrude(m, fp["forum"], GRADE, GRADE + 19.3, "sf_white", "sf_white")
        th = self.meshes.setdefault("sf_theater", Mesh("sf_theater"))
        self._extrude(th, fp["theater"], GRADE, GRADE + 16.0, "LIGHT_sf_facade", "sf_white")

    def _sky(self):
        m = self.meshes.setdefault("sf_sky", Mesh("sf_sky"))
        R, n = 1900.0, 48
        bot = [(R * math.cos(2 * math.pi * k / n), GRADE - 30.0, R * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
        top = [(x, GRADE + 760.0, z) for x, _y, z in bot]
        m.grid("sf_sky", [bot, top], [[(k / 12.0, 1.0) for k in range(n + 1)], [(k / 12.0, 0.0) for k in range(n + 1)]],
               facing=lambda p: -np.array([p[0], 0.0, p[2]]))

    def _signs(self):
        """SoFi Stadium on the canopy edge (east, over the colonnade; south-west, toward the lake) and the two roof
        wordmarks (the satellite roof)."""
        m = self.meshes.setdefault("sf_signs", Mesh("sf_signs"))
        O, lip = self.lip
        for (tx, tz, w, h) in ((-121.0, -20.0, 48.0, 6.0), (60.0, -205.0, 44.0, 5.5)):
            i = int(np.argmin(np.square(O[:, 0] - tx) + np.square(O[:, 1] - tz)))
            a, b = O[(i - 1) % len(O)], O[(i + 1) % len(O)]
            t = (b - a) / math.np_norm(b - a)
            nrm = np.array([t[1], -t[0]])
            if math.np_dot(nrm, O[i]) < 0:
                nrm = -nrm
            y0 = GRADE + lip[i] + 0.6
            c = np.array([O[i][0] + nrm[0] * 0.3, y0, O[i][1] + nrm[1] * 0.3])
            face = np.array([nrm[0], 0.0, nrm[1]])
            right = np.cross(-face, (0.0, 1.0, 0.0))
            right = right / math.np_norm(right) * (w / 2)
            hv = np.array([0.0, h, 0.0])
            A, B, C, D = c - right, c + right, c + right + hv, c - right + hv
            m.quad("sf_letters", A, B, C, D, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p, f=face: f)
            o = -face * 0.2
            m.quad("sf_letters_back", A + o, B + o, C + o, D + o, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p, f=face: -f)
        # the roof wordmarks: on the north-east of the ETFE and over the south end (reading with plan north up)
        for (cx, cz, w, rot) in ((-104.0, 104.0, 60.0, math.pi), (2.5, -156.0, 64.0, 0.0)):
            h = w / 8.0
            dx = np.array([-math.cos(rot), 0.0, -math.sin(rot)]) * (w / 2)   # reading direction toward plan east
            dz = np.array([-math.sin(rot), 0.0, math.cos(rot)]) * (h / 2)
            c = np.array([cx, 0.0, cz])
            pts = [c - dx - dz, c + dx - dz, c + dx + dz, c - dx + dz]
            pts = [np.array([p[0], self.roof_height(p[0], p[2]) + 0.45, p[2]]) for p in pts]
            m.quad("sf_roofmark", pts[0], pts[1], pts[2], pts[3], (0, 1), (1, 1), (1, 0), (0, 0), facing=up)


def build(venue="s23", params=None):
    return SoFi(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

#: retail shapes kept whole (read by the engine or needed for play): sideline props, pylons, field-level banners
KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
#: retail submeshes kept (extracted into new shapes): the yard markers and the digits the executable writes
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}

#: material render classes (PROVED OFFLINE on s23 and s24): +0x04 state hash, +0x60 culling bit, +0x70 alpha byte
CLASS_OPAQUE = (0xD30E3557, True, 0x01)
CLASS_ALPHA = (0xBF4740BD, True, 0x03)
CLASS_ALPHA_2SIDED = (0xBF4740BD, False, 0x03)

#: new materials: texture name (a per-bundle choice is resolved in ``_textures``), render class
MATERIALS = {
    "sf_seat": ("sf_seat", CLASS_OPAQUE), "sf_concrete": ("sf_concrete", CLASS_OPAQUE),
    "LIGHT_sf_ribbon": ("LIGHT_sf_ribbon", CLASS_OPAQUE), "LIGHT_sf_glass": ("LIGHT_sf_glass", CLASS_OPAQUE),
    "LIGHT_sf_facade": ("LIGHT_sf_facade", CLASS_OPAQUE), "sf_portal": ("sf_portal", CLASS_OPAQUE),
    "LIGHT_sf_concourse": ("LIGHT_sf_concourse", CLASS_OPAQUE),
    "sf_etfe_under": ("sf_etfe_under", CLASS_OPAQUE), "sf_etfe_top": ("sf_etfe_top", CLASS_OPAQUE),
    "sf_alu": ("sf_alu", CLASS_OPAQUE),
    "sf_white": ("sf_white", CLASS_OPAQUE), "LIGHT_sf_lights": ("LIGHT_sf_lights", CLASS_OPAQUE),
    "LIGHT_sf_screen": ("LIGHT_sf_screen", CLASS_OPAQUE), "sf_dark": ("sf_dark", CLASS_OPAQUE),
    "sf_letters": ("sf_letters", CLASS_ALPHA), "sf_letters_back": ("sf_letters", CLASS_ALPHA),
    "sf_roofmark": ("sf_letters", CLASS_ALPHA), "sf_letters_screen": ("sf_letters_screen", CLASS_ALPHA),
    "sf_plaza": ("sf_plaza", CLASS_OPAQUE), "sf_ground": ("sf_ground", CLASS_OPAQUE),
    "sf_water": ("sf_water", CLASS_OPAQUE), "sf_sky": ("sf_sky", CLASS_OPAQUE),
    **env.materials("s23"),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "sf_seat": (214, 196, 196), "crowd": (224, 204, 206), "sf_concrete": (206, 188, 178),
    "LIGHT_sf_ribbon": (255, 255, 255), "LIGHT_sf_glass": (190, 176, 255), "LIGHT_sf_facade": (190, 176, 250),
    "LIGHT_sf_concourse": (220, 200, 255),
    "sf_portal": (160, 150, 120), "sf_etfe_under": (236, 214, 150), "sf_etfe_top": (250, 226, 150),
    "sf_etfe_panel": (150, 136, 110), "sf_alu": (236, 218, 120), "sf_white": (232, 214, 232),
    "LIGHT_sf_lights": (255, 255, 255), "LIGHT_sf_screen": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    "sf_dark": (200, 190, 150), "sf_letters": (250, 240, 255), "sf_letters_back": (34, 32, 28),
    "sf_roofmark": (250, 236, 255), "sf_letters_screen": (255, 255, 255), "sf_plaza": (226, 206, 178),
    "sf_ground": (220, 196, 82), "sf_water": (220, 196, 90), "sf_sky": (255, 255, 255),
}
SUN = {"d": (0.25, 0.9, 0.35), "a": (-0.55, 0.55, 0.62), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.93, 0.86), "n": (0.97, 0.99, 1.03)}
OVERCAST = (0.80, 0.83, 0.88)                  # rain and snow bundles: the outside under cloud (the bowl stays dry)
OUTSIDE = {"sf_etfe_top", "sf_alu", "sf_plaza", "sf_ground", "sf_water", "sf_sky", "sf_roofmark"}
#: the canopy's soffit is lit in team colour at night (the east plaza photo c103; Walter P Moore: "SoFi Stadium lights
#: up Los Angeles"): Rams royal, Chargers powder blue
SOFFIT_NIGHT = {"s23": (0, 53, 148), "s24": (0, 128, 198), "s40": (52, 168, 156)}      # s40: the LXI wave's teal


def light(mat, P, N, tod, weather, outside=False, venue=None):
    """Baked vertex colour. Under the canopy the light is diffuse (the ETFE spreads the sun); outside the sun
    shapes it; at night the bowl is lit by the sports lights and self-lit materials glow; rain and snow bundles
    grey the outside only (indoors the game resets the weather: PROVED OFFLINE, step 2)."""
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, venue or "s23")
    base = BASE.get(mat, (200, 190, 150))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif tod == "n":
        f = np.full(n, 1.0)
    elif outside:
        sun = np.array(SUN[tod])
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.72 + 0.28 * nd) if tod == "d" else (0.62 + 0.45 * nd)
    else:
        f = 0.90 + 0.10 * np.clip(N[:, 1], 0, 1)
    if mat == "sf_alu" and tod != "n":
        f = np.where(N[:, 1] < -0.2, 0.50 + 0.15 * (1.0 + N[:, 1]), f)
    if mat == "sf_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.55, f)          # the soffits under the overhangs sit in shade
    if mat == "sf_white":
        # the columns and the ring read round and tapered (main, after lab 5): shaded across each face by its normal,
        # from the sun by day and from the plaza's floodlights (outward and low) at night
        if tod == "n":
            L = np.stack([P[:, 0], np.full(n, 0.0), P[:, 2]], axis=1)
            L = L / np.maximum(math.np_norm(L, axis=1, keepdims=True), 1e-6)
            L[:, 1] = -0.35
            L = L / math.np_norm(L, axis=1, keepdims=True)
            f = 0.52 + 0.48 * np.clip(np.sum(N * L, axis=1), 0, 1)
        else:
            sun = np.array(SUN[tod])
            f = 0.60 + 0.40 * np.clip(math.np_matmul(N, sun / math.np_norm(sun)), 0, 1)
    if mat == "sf_alu" and tod == "n" and venue in SOFFIT_NIGHT:
        # at night (c103): the soffit glows in team colour, the canopy's lip reads as a lit warm-white band, and only
        # the roof's top stays dark
        out = np.zeros((n, 4), np.uint8)
        glow = np.array(SOFFIT_NIGHT[venue], float) * 0.95 + 30.0
        lip = np.array((156.0, 152.0, 146.0))           # under the SoFi Stadium letters (250): they still read
        dim = np.array((64.0, 68.0, 76.0))
        under = (N[:, 1] < -0.2)[:, None]
        top = (N[:, 1] > 0.5)[:, None]
        out[:, :3] = np.clip(np.where(under, glow, np.where(top, dim, lip)), 0, 255)
        out[:, 3] = 255
        return out
    tint = TINT[tod]
    if weather in "rs" and outside and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    return out


def _rgba(path):
    return official.rgba(path)


def portrait_panel(venue):
    """The private portrait panel for ``venue`` when it should be used (see USE_PORTRAITS), else None."""
    if USE_PORTRAITS is False or venue not in VENUES:
        return None
    try:
        doc = json.loads((PRIVATE_ART / "private.json").read_text(encoding="utf-8"))
        row = doc["panels"][venue]
        path = PRIVATE_ART / row["file"]
        digest = sha(path.read_bytes())
    except (OSError, ValueError, KeyError):
        sb.require(USE_PORTRAITS is not True, f"{venue}: the private portrait panels are not present")
        return None
    if digest != row["sha256"]:
        sb.require(USE_PORTRAITS is not True, f"{venue}: the private portrait panel differs from its manifest")
        return None
    if USE_PORTRAITS is None:
        pinned = (model_pins().get("portrait_art") or {}).get(venue) if PINS_PATH.is_file() else None
        if pinned != digest:
            return None
    return path


def _textures(venue, tod, weather):
    """{texture key: RGBA} for one bundle: the per-venue dressing, the day or night roof, the sky of the hour."""
    art = ART_DIR
    sky = "o" if weather in "rs" and tod != "n" else tod
    return {
        "sf_seat": _rgba(art / "sf_seat.png"), "sf_concrete": _rgba(art / "sf_concrete.png"),
        "LIGHT_sf_ribbon": _rgba(art / f"LIGHT_sf_ribbon_{venue}.png"), "LIGHT_sf_glass": _rgba(art / "LIGHT_sf_glass.png"),
        "LIGHT_sf_facade": _rgba(art / "LIGHT_sf_facade.png"), "sf_portal": _rgba(art / "sf_portal.png"),
        "LIGHT_sf_concourse": _rgba(art / "LIGHT_sf_concourse.png"),
        "sf_etfe_under": _rgba(art / f"sf_etfe_under_{'n' if tod == 'n' else 'd'}.png"),
        "sf_etfe_top": _rgba(art / f"sf_etfe_top_{'n' if tod == 'n' else 'd'}.png"),
        "sf_alu": _rgba(art / "sf_alu.png"), "sf_white": _rgba(art / "sf_white.png"),
        "LIGHT_sf_lights": _rgba(art / "LIGHT_sf_lights.png"), "LIGHT_sf_screen": _rgba(portrait_panel(venue) or art / f"LIGHT_sf_screen_{venue}.png"),
        "sf_dark": _rgba(art / "sf_dark.png"), "sf_letters": _rgba(art / "sf_letters.png"),
        "sf_letters_screen": _rgba(art / "sf_letters_screen.png"),
        "sf_plaza": _rgba(art / "sf_plaza.png"), "sf_ground": _rgba(art / "sf_ground.png"),
        "sf_water": _rgba(art / "sf_water.png"), "sf_sky": _rgba(art / f"sf_sky_{sky}.png"),
        **env.textures(venue, tod, weather),
    }


def _class_of(material):
    rec = material.record
    return (struct.unpack_from("<I", rec, 0x04)[0], bool(struct.unpack_from("<I", rec, 0x60)[0] & 0x04000000),
            rec[0x70])


def _template_material(sc, cls):
    """A retail material with a texture and the wanted render class (the classes are the same in s23 and s24)."""
    for m in sc.materials:
        if m.texture is not None and m.next_pass is None and _class_of(m) == cls and not m.name.startswith("digit"):
            return m
    raise sb.ScneBuildError(f"no template material of class {cls}")


def _template_shape(sc):
    for s in sc.shapes:
        regs = struct.unpack_from("<16I", s.record, 0x84)
        if (regs[0] == 0x32 and regs[1] == 0x00080115 and regs[3] == 0x140 and regs[6] == 0x00040121
                and s.stride(0) == 12 and s.stride(1) == 10 and s.transforms is not None):
            node = next((n for n in sc.nodes if n.shape_name == s.name), None)
            if node is not None:
                return s, node
    raise sb.ScneBuildError("no static template shape")


def _vertices(shape):
    """(positions m, colours rgba, uvs) of a static shape with the template declaration."""
    n = shape.vertex_count
    P = np.frombuffer(shape.streams[0], dtype="<f4").reshape(n, 3).astype(float) / 100.0
    su, sv, ou, ov = struct.unpack_from("<4f", shape.record, 0x30)
    C, UV = [], []
    for i in range(n):
        b, g, r, a, qu, qv, _z = struct.unpack_from("<4B2hh", shape.streams[1], 10 * i)
        C.append((r, g, b, a))
        UV.append((qu / 32767.0 * su + ou, qv / 32767.0 * sv + ov))
    return P, C, UV


def extract(sc, shapes, keep, name, tmpl_shape):
    """A new static shape made of the submeshes of ``shapes`` whose material name passes ``keep``: the vertices they
    use (positions, retail colours, UVs re-fitted to the new shape's constant) and their push words re-indexed."""
    P_out, C_out, UV_out, subs = [], [], [], []
    for s in shapes:
        P, C, UV = _vertices(s)
        for sm in s.submeshes:
            mname = sc.materials[sm.material].name
            if not keep(mname):
                continue
            prims = sb.decode_words(sm.words)
            remap = {}
            strips = []
            for mode, ix in prims:
                new = []
                for i in ix:
                    if i not in remap:
                        remap[i] = len(P_out)
                        P_out.append(tuple(P[i] * 100.0)); C_out.append(C[i]); UV_out.append(UV[i])
                    new.append(remap[i])
                strips.append((mode, new))
            for mode, new in strips:
                subs.append((sm.material, mode, new))
    if not P_out:
        return None
    words = {}
    for material, mode, ix in subs:
        words.setdefault((material, mode), []).append(ix)
    sub_words = []
    for (material, mode), lists in words.items():
        if mode == sb.QUADS:
            flat = [i for ix in lists for i in ix]
            sub_words.append((material, sb.encode_words(sb.QUADS, flat)))
        else:
            sub_words.append((material, sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(lists))))
    return sb.static_shape(tmpl_shape, name, P_out, C_out, UV_out, sub_words)


def _ml():
    from . import nfl2k5_modern_metlife as ml
    return ml


#: digit slots along the score strip (u5's layout): away score, gap, home score, gap, the clock with its colon
DIGIT_SLOTS = {"digit_away_score_L": 0, "digit_away_score_R": 1, "digit_home_score_L": 3, "digit_home_score_R": 4,
               "digit_clock_1": 6, "digit_clock_2": 7, "digit_colen": 8, "digit_clock_3": 9, "digit_clock_4": 10}


def _place_quad(P, UV, quad, centre, right, upv, hw, hh):
    """Move the four corners of ``quad`` to a rectangle at ``centre`` keeping the texture's orientation (the corner
    with the larger U goes right, the smaller V goes up)."""
    us = [UV[i][0] for i in quad]
    vs = [UV[i][1] for i in quad]
    mu, mv = sum(us) / 4, sum(vs) / 4
    for i in quad:
        su = 1.0 if UV[i][0] > mu else -1.0
        sv = 1.0 if UV[i][1] < mv else -1.0
        P[i] = centre + right * su * hw + upv * sv * hh


#: the flare markers' height above the field. The game draws a lens flare at every flare marker in view, and xemu
#: draws it through the canopy (lab 2 and lab 3: two to four flares over the exterior shots); the markers also place
#: the night and indoor player shadows. High above the light ring's diagonals they stay out of every flyover and game
#: camera, and the shadows fall almost straight down, as under SoFi's canopy lights. DESIGN, UNWITNESSED in game.
FLARE_HEIGHT = 300.0


def flare_points(model):
    """The four flare markers: over the light ring at its 45, 135, 225 and 315 degree points, FLARE_HEIGHT up."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], FLARE_HEIGHT, best[2]))
    return out


def adjust_digits(shape, sc, model):
    """The score and clock digits onto the Infinity Screen's outer board, one strip on each long side beside the feed
    window (the 2025 game-day photo shows the score panel next to the team panel); the play clocks onto the end
    walls."""
    q = model.p["screen"]
    P, _C, UV = _vertices(shape)
    P = P.copy()
    feed = q["outer"] * SoFi.FEED_ASPECT / 2
    strips = []
    for z_sign in (1, -1):
        c, nrm, right = model.screen_point("outer", z_sign, feed + 11.0)
        strips.append(dict(centre=c + nrm * 0.25, right=right))
    counters = {}
    for sm in shape.submeshes:
        mname = sc.materials[sm.material].name
        idx = sorted({i for _m, ix in sb.decode_words(sm.words) for i in ix})
        quads = [idx[k:k + 4] for k in range(0, len(idx) - 3, 4)]
        for quad in quads:
            n = counters.get(mname, 0)
            counters[mname] = n + 1
            if mname.startswith("digit_playclock"):
                zs = 1 if n % 2 == 0 else -1
                side = -1 if mname.endswith("_L") else 1
                centre = np.array([side * 0.9 * zs, 2.7, zs * (model.p["loop"]["L"] - 0.08)])
                _place_quad(P, UV, quad, centre, np.array([-zs, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 0.75, 1.1)
            else:
                s_ = strips[n % 2]
                slot = DIGIT_SLOTS.get(mname, 5)
                centre = s_["centre"] + s_["right"] * (-8.2 + slot * 1.65)
                _place_quad(P, UV, quad, centre, s_["right"], np.array([0.0, 1.0, 0.0]), 0.7, 1.05)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def _wall_point(model, x, z):
    """Nearest point of the field-wall line, its outward normal and tangent (u5's helper, kept here: the MetLife model
    dropped it in its fidelity pass, 5836bf0f6, and SoFi's field-level banners still stand on it)."""
    best = None
    loop = model.loop
    for a, b in zip(loop[:-1], loop[1:]):
        ax, az, bx, bz = a.x, a.z, b.x, b.z
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
        px, pz = ax + dx * t, az + dz * t
        d = math.pow(px - x, 2) + math.pow(pz - z, 2)
        if best is None or d < best[0]:
            nx, nz = a.nx * (1 - t) + b.nx * t, a.nz * (1 - t) + b.nz * t
            n = math.hypot(nx, nz)
            best = (d, px, pz, nx / n, nz / n)
    return best[1:]


def adjust_banners(shape, model):
    """The field-level banners onto the new wall face, 8 cm in front of it (u5's rule)."""
    P = np.frombuffer(shape.streams[0], dtype="<f4").reshape(shape.vertex_count, 3).astype(float) / 100.0
    out = P.copy()
    for q in range(0, len(P) - 3, 4):
        quad = P[q:q + 4]
        cx, cz = quad[:, 0].mean(), quad[:, 2].mean()
        wx, wz, nx, nz = _wall_point(model, cx, cz)
        tx_, tz_ = -nz, nx
        for i, p in enumerate(quad):
            along = (p[0] - cx) * tx_ + (p[2] - cz) * tz_
            out[q + i] = (wx + tx_ * along - nx * 0.08, p[1], wz + tz_ * along - nz * 0.08)
    sb.set_positions(shape, [tuple(v * 100) for v in out])


#: the field-level sponsor cloths (st's method for Highmark, 2026-09-25): job u4's reviewed 2026 league sheet
#: (``nfl2k5_modern_venues_2026.LEAGUE_ART``: the eight defunct 2004 cloths as 2026 league type; Riddell, Gatorade and
#: NFL.com kept) over the kept banner_corp texture, carried to rain and snow from the dry bundle of the same time of day
#: as u4 carries it. The SoFi option cedes s23, s24 and s40 from the 2026 venue art, so without this the kept banners
#: showed the 2004 SEGA cloth behind the bench (lab 6, the Packers at SoFi by day, fly-058; PROVED IN GAME).
LEAGUE_BANNER = "banner_corp"


def dry_of(name):
    """The dry bundle of the same time of day (s24nr.iff -> s24nd.iff)."""
    return name[:4] + "d.iff"


def league_banner(retail_bundle, filename, dry_bundle=None):
    """(retail texture index, RGBA) of the stadium scene's banner_corp with the 2026 league cloths, or None when the
    scene or the build lacks it. ``dry_bundle`` is the dry bundle of the same time of day (rain and snow need it)."""
    from . import nfl2k5_modern_venues_2026 as mv
    entry = next((e for e in mv.LEAGUE_ART if e["key"] == LEAGUE_BANNER), None)
    path = mv.DATA_DIR / entry["art"] if entry else None
    if path is None or not path.is_file():
        return None
    weather = filename[4]
    if weather != "d" and dry_bundle is None:
        return None
    ml = _ml()

    def banner(bundle):
        c = ml.bundle_scenes(bundle)["stadium"]
        rec, dec = ml._scene(bundle, c)
        row = ml.texture_rows(rec).get(LEAGUE_BANNER)
        return (None, None) if row is None else (int(row["index"]), ml.read_p8(dec, c.system_bytes, row)[0])
    index, current = banner(retail_bundle)
    if index is None:
        return None
    base = current if weather == "d" else banner(dry_bundle)[1]
    sb.require(base is not None and base.shape == current.shape, f"{filename}: the dry banner_corp differs in size")
    art = _rgba(path)
    h, w = current.shape[:2]
    if art.shape[:2] != (h, w):
        art = _resample(art, w, h)
    out = current.copy()
    sx, sy = w / art.shape[1], h / art.shape[0]
    for x0, y0, x1, y1 in entry["rects"]:
        x0, x1, y0, y1 = int(round(x0 * sx)), int(round(x1 * sx)), int(round(y0 * sy)), int(round(y1 * sy))
        piece, _fits = mm_modern().weather_transfer(base, current, art, region=(y0, y1, x0, x1), snow=weather == "s")
        out[y0:y1, x0:x1] = piece[y0:y1, x0:x1]
    return index, out


def mm_modern():
    from . import nfl2k5_modern_metlife as mmod
    return mmod


def build_scene(retail_bundle, filename, model, dry_bundle=None):
    """The SoFi stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = _ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = _template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    # 1. the kept pieces: whole props, and the yard markers and digits extracted from wherever retail put them
    yard = extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "sf_yard", tmpl_shape)
    digits = extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "sf_digits", tmpl_shape)
    sc.shapes = [s for s in sc.shapes if s.name.startswith(KEEP_PREFIXES)]
    names = {s.name for s in sc.shapes}
    sc.nodes = [n for n in sc.nodes if n.shape_name in names]
    for shp in (yard, digits):
        if shp is not None:
            sc.shapes.append(shp)
            sc.nodes.append(sb.node_for(tmpl_node, shp.name, shp.name))
    # 2. new textures and materials (cloned from retail templates of the right render class)
    tex = _textures(venue, tod, weather)
    tex_index = {}
    for key, rgba in tex.items():
        sc.textures.append(sb.p8_texture(tex_tmpl, rgba))
        tex_index[key] = len(sc.textures) - 1
    for name, (key, cls) in MATERIALS.items():
        tmpl = _template_material(sc, cls)
        mat = sb.Material(bytearray(tmpl.record), name, tex_index[key], None)
        sc.materials.append(mat)
    mat_ix = {m.name: i for i, m in enumerate(sc.materials)}
    # 3. shapes from the model meshes
    for mesh in model.meshes.values():
        if not mesh.P:
            continue
        P = np.array(mesh.P) * 100.0
        N = np.array(mesh.N)
        UV = np.array(mesh.UV)
        C = np.zeros((len(P), 4), np.uint8)
        subs = []
        for mat, strips in mesh.groups.items():
            if mat not in mat_ix:
                raise KeyError(f"{filename}: material {mat} missing")
            idxs = sorted({i for st in strips for i in st})
            C[idxs] = light(mat, P[idxs] / 100.0, N[idxs], tod, weather, outside=mat in OUTSIDE, venue=venue)
            subs.append((mat_ix[mat], sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(strips))))
        shape = sb.static_shape(tmpl_shape, mesh.name, [tuple(p) for p in P], [tuple(x) for x in C],
                                [tuple(u) for u in UV], subs)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, mesh.name, mesh.name))
    # 4. retail pieces that move: the banners onto the wall, the digits onto the screen
    for s in sc.shapes:
        if s.name.startswith("banners_"):
            adjust_banners(s, model)
    if digits is not None:
        adjust_digits(digits, sc, model)
    # 5. markers: the glows and flares on the light ring, the jumbotron markers on the screen
    lights = model.light_points
    glows = [m for m in sc.markers if m.name.startswith("marker_light")]
    for i, m in enumerate(glows):
        p = lights[int(round(i * len(lights) / max(1, len(glows)))) % len(lights)]
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
        # 0x7F210 registers a light glow at every marker whose name holds "light"; under a roof the glow sprites draw
        # through the canopy (lab 1), so these markers keep their records and positions but not the word
        m.name = m.name.replace("marker_light", "marker_lamp")
    flares = [m for m in sc.markers if "flare" in m.name]
    for m, p in zip(flares, flare_points(model)):
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
    for m, p in zip([m for m in sc.markers if m.name.startswith("jumboMarker")], model.markers["jumbo"]):
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
    for m in sc.markers:
        if m.name.startswith("nosebleed"):
            struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in model.nosebleed))
    # 6. drop the materials and textures nothing draws (keeping the ones the executable looks up by name)
    used = {sm.material for s in sc.shapes for sm in s.submeshes}
    keep_m = [i for i, m in enumerate(sc.materials) if i in used or m.name in KEEP_MATERIALS_BY_CODE
              or m.name.startswith("digit_")]
    remap_m = {old: new for new, old in enumerate(keep_m)}
    keep_t = sorted({sc.materials[i].texture for i in keep_m if sc.materials[i].texture is not None})
    remap_t = {old: new for new, old in enumerate(keep_t)}
    mats = []
    for i in keep_m:
        m = sc.materials[i]
        m.texture = remap_t.get(m.texture) if m.texture is not None else None
        m.next_pass = remap_m.get(m.next_pass) if m.next_pass is not None else None
        mats.append(m)
    sc.materials = mats
    sc.textures = [sc.textures[i] for i in keep_t]
    banner = league_banner(retail_bundle, filename, dry_bundle)
    if banner is not None and banner[0] in remap_t:
        sc.textures[remap_t[banner[0]]] = sb.p8_texture(sc.textures[remap_t[banner[0]]], banner[1])
    # the score, clock and play-clock segments light as LED bars, not the retail light bulbs (lab 2's Rams frames)
    for i in sorted({m.texture for m in sc.materials if m.name.startswith("digit_") and m.texture is not None}):
        sc.textures[i] = sb.p8_texture(sc.textures[i], led_segment())
    for s in sc.shapes:
        for sm in s.submeshes:
            struct.pack_into("<H", sm.record, 0, remap_m[sm.material])
    return sc


def led_segment(size=32):
    """The digit segment texture: one lit LED bar (warm white, a soft one-texel edge) where the retail texture had its
    2 x 2 light bulbs, black around it, so each segment of the game's digits reads as a modern LED segment."""
    y, x = np.mgrid[0:size, 0:size].astype(float) + 0.5
    x0, x1, y0, y1 = 8.0, 24.0, 3.0, 29.0
    edge = np.minimum.reduce([x - x0, x1 - x, y - y0, y1 - y])
    lit = np.clip(edge, 0.0, 1.0)[..., None]
    rgb = lit * np.array([255.0, 250.0, 236.0]) + (1 - lit) * np.array([6.0, 6.0, 8.0])
    return np.dstack([rgb, np.full((size, size), 255.0)]).astype(np.uint8)


def cityscape_scene(retail_bundle):
    """The retail cityscape (s24 only) collapsed: its shape keeps its name, node and materials, its vertices meet at one
    point under the plaza and its textures shrink to 8 x 8. The surroundings live in the stadium scene, so both venue
    records show the same building; the freed bytes go to the stadium chunk."""
    ml = _ml()
    c = ml.bundle_scenes(retail_bundle)["cityscape"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    for s in sc.shapes:
        sb.set_positions(s, [(0.0, -5000.0, 0.0)] * s.vertex_count)
    grey = np.full((8, 8, 4), (90, 90, 90, 255), np.uint8)
    sc.textures = [sb.p8_texture(t, grey) for t in sc.textures]
    return sc, c


def _chunk_span(bundle, chunk):
    return bytes(bundle[chunk.offset:chunk.offset + 32 + chunk.stored_size])


def model_bundle(retail_bundle, filename, model=None, *, cameras=None, dry_bundle=None):
    """(bundle bytes, info): the retail bundle with its stadium scene replaced by the SoFi model, its intro cameras
    rewritten when ``cameras`` gives the shots, and (s24) its cityscape collapsed. The stretch from the first
    replaced chunk to the end of the cameras keeps its length, so the bundle keeps its size; inside it the chunks
    trade bytes (the stadium chunk takes what the cityscape frees)."""
    ml = _ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    cam_chunk, cam_dec = mm._cameras_chunk(retail_bundle)
    sb.require(cam_chunk.offset == st.offset + 32 + st.stored_size, "intro cameras do not follow the stadium chunk")
    parts = []
    start = st.offset
    city_info = None
    if "cityscape" in scenes:
        city = scenes["cityscape"]
        sb.require(city.offset + 32 + city.stored_size == st.offset, "the cityscape does not precede the stadium chunk")
        csc, _c = cityscape_scene(retail_bundle)
        cdec, csys, cvid = sb.serialize(csc)
        c_out, city_info = sb.compressed_chunk("SCNE", cdec, csys, cvid, stream_tag=struct.unpack_from(
            "<I", _chunk_span(retail_bundle, city), 36)[0], offset_bits=_chunk_span(retail_bundle, city)[40])
        parts.append(c_out)
        start = city.offset
    end = cam_chunk.offset + 32 + cam_chunk.stored_size
    cam_span = _chunk_span(retail_bundle, cam_chunk)
    if cameras is not None:
        new_cam = write_cameras(cam_dec, cameras)
        extra = 0
        while True:
            try:
                cam_out, cam_info = sb.fixed_span_chunk("SCNE", new_cam, cam_chunk.system_bytes, cam_chunk.video_bytes,
                                                        cam_span, stored=cam_chunk.stored_size + extra)
                break
            except sb.ScneBuildError:
                sb.require(extra < 4096, "intro cameras do not fit even with borrowed bytes")
                extra += 64
    else:
        cam_out, cam_info, new_cam = cam_span, dict(borrowed=0), cam_dec
    room = end - start - sum(len(p) for p in parts) - len(cam_out) - 32
    room -= room % 16
    st_span = _chunk_span(retail_bundle, st)
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, st_span, stored=room)
    stretch = b"".join(parts) + chunk + cam_out
    sb.require(len(stretch) == end - start, f"{filename}: the stretch changed length ({len(stretch)} != {end - start})")
    out = bytes(retail_bundle[:start]) + stretch + bytes(retail_bundle[end:])
    sb.require(len(out) == len(retail_bundle), "model bundle changed size")
    chunks = tx.parse_chunks(out, allow_trailing=True)
    sb.require([c.kind for c in chunks] == [c.kind for c in tx.parse_chunks(retail_bundle, allow_trailing=True)],
               "model bundle chunk list differs")
    back, _ = tx.decode_chunk(out, chunks[st.index])
    sb.require(back == decoded, "model chunk read-back differs")
    back_cam, _ = tx.decode_chunk(out, chunks[cam_chunk.index])
    sb.require(back_cam == new_cam, "intro cameras read-back differs")
    return out, dict(info, shapes=len(sc.shapes), materials=len(sc.materials), textures=len(sc.textures),
                     markers=len(sc.markers), stretch=[start, end], cityscape=city_info,
                     retail_system=st.system_bytes, retail_video=st.video_bytes)


# ------------------------------------------------------------------------------------------------ intro cameras

def write_cameras(decoded, shots):
    """Same-layout rewrite of an intro_cameras scene (u5's writer, extended): every camera keeps its record, channel
    structure and time words; the rest matrices, fields of view, constants and segment coefficients change. The
    retail s23 and s24 scenes carry multi-segment curves (camera 1's pitch and yaw at the Rams' dome, its height at
    the Chargers'), whose segment timing is not settled, so a component with more than one segment holds its start
    value; a single-segment component moves at the shot's rate (value = start + rate x t, t in 1/300 s ticks)."""
    info = mm.parse_cameras(decoded)
    out = bytearray(decoded)
    for k, ((co, name), shot) in enumerate(zip(info["cameras"], shots)):
        ex, ey, ez = (v * 100.0 for v in shot["eye"])
        rows = mm.camera_matrix(ex, ey, ez, shot["yaw"], shot["pitch"])
        for r, row in enumerate(rows):
            struct.pack_into("<4f", out, co + 0x10 + 16 * r, *row)
        struct.pack_into("<f", out, co + 0x50, float(shot["fov"]))
        start = dict(x=ex, y=ey, z=ez, pitch=shot["pitch"] * mm.BAM, yaw=shot["yaw"] * mm.BAM, roll=0.0)
        rate = dict(shot.get("rates", {}))
        for ch in (c for c in info["channels"] if c["camera"] == k):
            if ch["field"] == 0x50:
                for comp in ch["comps"]:
                    sb.require("const" in comp, f"{name}: animated field of view")
                    struct.pack_into("<f", out, comp["const"], float(shot["fov"]))
                continue
            sb.require(ch["field"] == 0x10, f"{name}: channel on an unknown field")
            for comp in ch["comps"]:
                label = mm.CAMERA_COMPONENTS[comp["bit"]]
                if "const" in comp:
                    struct.pack_into("<f", out, comp["const"], float(start[label]))
                    continue
                per_tick = rate.get(label, 0.0) / 300.0 if comp["count"] == 1 else 0.0
                per_tick *= 100.0 if label in ("x", "y", "z") else mm.BAM
                for seg in range(comp["count"]):
                    struct.pack_into("<4f", out, comp["segs"] + 16 * seg, 0.0, 0.0, float(per_tick), float(start[label]))
    return bytes(out)


def camera_components(decoded):
    """[set of components each camera's channel carries (constant or animated)] of a retail intro_cameras scene."""
    info = mm.parse_cameras(decoded)
    out = [set() for _ in info["cameras"]]
    for ch in info["channels"]:
        if ch["field"] != 0x10:
            continue
        for comp in ch["comps"]:
            out[ch["camera"]].add(mm.CAMERA_COMPONENTS[comp["bit"]])
    return out


def camera_channels(decoded):
    """{camera index: set of animated components with one segment} of a retail intro_cameras scene."""
    info = mm.parse_cameras(decoded)
    out = {k: set() for k in range(len(info["cameras"]))}
    for ch in info["channels"]:
        for comp in ch["comps"]:
            if "const" not in comp and comp["count"] == 1:
                out[ch["camera"]].add(mm.CAMERA_COMPONENTS[comp["bit"]])
    return out


#: The components each retail intro camera's channel carries (constant or animated; PROVED OFFLINE from the retail
#: s23 and s24 intro_cameras scenes, ``camera_components``). A component the channel does not carry plays as 0 in
#: the game (PROVED IN GAME, labs 2 and 3: the press-box eye set at x = 90 m flew at x = 0, over the field), so the
#: shot for that camera must want 0 there. Multi-segment components hold their start value (``write_cameras``).
CAMERA_COMPONENTS_PRESENT = {
    "s23": ({"x", "y", "z", "pitch", "yaw"}, {"y", "z", "pitch"}, {"x", "y", "z", "pitch", "yaw"},
            {"y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"}),
    "s24": ({"x", "y", "z", "pitch", "yaw"}, {"y", "z", "pitch"}, {"x", "y", "z", "pitch", "yaw"},
            {"y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"}),
    "s40": ({"x", "y", "z", "pitch", "yaw", "roll"},),
}

#: DESIGN: the SoFi flyover (v4). The pregame intro plays three consecutive cameras from a varying start (lab 2 played
#: s24's 3, 4 and 5; lab 3 played s23's 4, 5 and 1), with a vertical field of view on a 16:9 picture. The order below
#: puts the whole Infinity Screen and an exterior pass in every three in a row; each shot wants 0 wherever its camera
#: carries no component; every eye keeps at least 3 m from the model along its 8 s path; the screen shots
#: (``screen``) see the whole screen (tests: Cameras). Retail speeds for scale: 5 to 8 m/s, a few degrees a second.
_PRESSBOX = dict(eye=(90.0, 62.0, -10.0), target=(0.0, 36.0, 0.0), fov=44.0, screen=True,
                 rates=dict(yaw=1.2))                          # above the west 400 level: the screen as c002 shows it
_CRANE = dict(eye=(0.0, 3.0, 64.0), target=(0.0, 22.0, -20.0), fov=44.0,
              rates=dict(y=2.0, pitch=1.6))                    # a field-level crane in the north end zone, facing south
_EXTERIOR = dict(eye=(236.0, 96.0, -400.0), target=(-20.0, 44.0, -80.0), fov=32.0,
                 rates=dict(x=-3.5, y=-1.0, z=6.0, yaw=1.2))                  # over Rivers Lake: the canopy's sail
_ENDZONE = dict(eye=(0.0, 46.0, -100.0), target=(0.0, 36.0, 10.0), fov=44.0, screen=True,
                rates=dict(z=2.0, yaw=0.8))                    # the whole ring from the south upper deck
_PLAZA = dict(eye=(-250.0, 38.0, -135.0), target=(-112.0, 38.0, -30.0), fov=40.0,
              rates=dict(x=3.0, y=0.8, z=2.0, yaw=0.8))        # the east colonnade and the canopy edge, level
SOFI_SHOTS = {venue: [_PRESSBOX, _CRANE, _EXTERIOR, _ENDZONE, _PLAZA] for venue in ("s23", "s24")}
#: the Super Bowl bundles carry one intro camera whose channel carries every component, pitch, yaw and roll each a
#: multi-segment curve. PROVED IN GAME (labs 4 and 5, 2026-09-24): that camera does not take the angles the s23/s24
#: cameras take: the lake aerial (yaw 141, pitch -7) showed only night sky, and the press-box shot (yaw 96, pitch -16)
#: looked almost straight up at the roof's lattice from 18 m below it, as if the yaw value drove the pitch. Until its
#: angle channels are decoded, the Super Bowl shot wants every angle 0, which reads the same whatever channel carries
#: which angle and in either sign: a level, still camera in the north upper deck at the screen's own height, looking
#: south down the field's axis at the whole lit Infinity Screen (a night game; zero angles look along -z in every
#: retail camera the model writes). PROVED IN GAME (lab 6, 2026-09-25): with every angle 0 the s40 camera looks down
#: about 24 degrees at the field's centre from the eye, with a horizontal field of about 40 degrees: the whole LXI field
#: from above the north end (both neutral end zones, the LXI mark, the shields on the 25s), the screen just above the
#: frame. The s40 angle channels still play unlike s23/s24's, so the shot stays at zero angles.
_SUPER_BOWL = dict(eye=(0.0, 44.0, 100.0), target=(0.0, 44.0, -10.0), fov=44.0, screen=True)
SOFI_SHOTS["s40"] = [_SUPER_BOWL]


def effective_shot(shot, present):
    """The shot as the game plays it on a camera whose channel carries ``present``: every other component 0."""
    out = dict(shot, rates={k: v for k, v in shot.get("rates", {}).items() if k in present})
    eye = list(shot["eye"])
    for i, axis in enumerate("xyz"):
        if axis not in present:
            eye[i] = 0.0
    out["eye"] = tuple(eye)
    if "yaw" not in present:
        out["yaw"] = 0.0
    if "pitch" not in present:
        out["pitch"] = 0.0
    return out


def sofi_shots(venue):
    out = []
    for s in SOFI_SHOTS[venue]:
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(dict(s, yaw=yaw, pitch=pitch))
    return out


# ------------------------------------------------------------------------------------------------ bundles and lab

VARIANTS = tuple(f"{v}{t}{w}.iff" for v in MODEL_VENUES for t in "dan" for w in "drs")


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256)}: the team bundles from the 2026 venue table, the
    Super Bowl bundles from Modern colour's pins (the venue table holds home venues only)."""
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_modern_color as colour
    pins = {pin["name"]: pin for v in VENUES for pin in mv.venues()[v]["bundles"]}
    for pin in colour._pins()["bundles"]:
        if pin["name"][:3] == SUPER_BOWL:
            pins[pin["name"]] = {k: pin[k] for k in ("name", "name_id", "outer", "size", "retail_sha256")}
    return pins


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the twenty-seven SoFi bundles, each checked against its pinned SHA-256."""
    ml = _ml()
    out = {}
    with ml._outer_image()(str(source)) as archive:
        for name, pin in _venue_pins().items():
            e = _entry(archive, pin)
            data = archive.read(e.virtual_offset, e.size)
            sb.require(sha(data) == pin["retail_sha256"], f"{name}: the source bundle is not retail")
            out[name] = data
    return out


def stretch(bundle):
    """(start, end) of the SoFi stretch: from the cityscape (s24) or stadium (s23) chunk to the end of the intro
    cameras."""
    ml = _ml()
    scenes = ml.bundle_scenes(bundle)
    start = scenes["cityscape"].offset if "cityscape" in scenes else scenes["stadium"].offset
    cam, _dec = mm._cameras_chunk(bundle)
    return start, cam.offset + 32 + cam.stored_size


def _compile(job):
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=sofi_shots(name[:3]), dry_bundle=dry)
    return name, out, info


def build_all(source, *, workers=None, progress=None, names=None):
    """{name: (retail bundle, model bundle, info)} for the twenty-seven bundles (or ``names``), compiled in parallel."""
    ml = _ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers,
                                         progress=progress, label="SoFi Stadium"):
        out[name] = (retail[name], model, info)
    return out


def apply_lab_disc(disc, source, *, progress=None):
    """Lab only: the Build step on an already built disc (the field, the stadium stretch, the rows and the crowd)."""
    return apply_to_image(disc, retail_source=source, progress=progress)


# ------------------------------------------------------------------------------------------------ the field

#: The field art (tools/nfl2k5_sofi_model_art.py; photos cited there): each end-zone panel texture carries the south
#: end (the team) in its top half and the north end (LOS ANGELES) in its bottom half. The retail panels named N sit at
#: the south end (-z) and those named S at the north; V runs from the end line (0) to the goal line (1) on both.
FIELD_ART = ART_DIR / "field"
ENDZONE_V = {"N": (0.0, 0.5), "S": (0.5, 1.0)}


def art_manifest():
    return json.loads((ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]


def _field_shape(rec, name):
    return next(s for s in rec["shapes"] if s["name"] == name)


def _stream(shape, index):
    return next(v for v in shape["vertex_streams"] if v["stream_index"] == index)


def _submesh_vertices(rec, decoded, shape, material):
    idx = set()
    for sm in rec["submeshes"]:
        if sm["shape_index"] != shape["index"] or sm["material_name"] != material:
            continue
        words = bytes(decoded[sm["command_offset"]:sm["command_offset"] + 4 * sm["primary_command_word_count"]])
        for _mode, ix in sb.decode_words(words):
            idx.update(ix)
    sb.require(idx, f"the field has no {material} vertices")
    return sorted(idx)


def _resample(rgba, width, height):
    from PIL import Image
    return np.asarray(Image.fromarray(np.ascontiguousarray(rgba)).resize((width, height), Image.LANCZOS))


def _key_colours(rgba, share=0.02):
    """The art's flat fills: every opaque colour covering at least ``share`` of the opaque pixels (the official
    paint: the Rams' royal and sol, the Chargers' powder blue, gold and white)."""
    px = rgba.reshape(-1, 4)
    px = px[px[:, 3] == 255][:, :3]
    if not len(px):
        return []
    values, counts = np.unique(px, axis=0, return_counts=True)
    return [tuple(int(x) for x in v) for v, c in zip(values, counts) if c >= share * len(px)]


def _snap_palette(out, system, row, keys, tol=8):
    """Palette entries the quantizer left within ``tol`` of a flat fill take the fill's exact colour (the P8 quantizer
    averages a fill with its anti-aliased edge: sol came out as (252, 210, 2)). Returns the entries snapped."""
    at = system + int(row["palette_offset"])
    snapped = 0
    for i in range(256):
        b, g, r = out[at + 4 * i:at + 4 * i + 3]
        for kr, kg, kb in keys:
            if (r, g, b) != (kr, kg, kb) and max(abs(r - kr), abs(g - kg), abs(b - kb)) <= tol:
                out[at + 4 * i:at + 4 * i + 3] = bytes((kb, kg, kr))
                snapped += 1
                break
    return snapped


def _half_detail(rgba):
    """The art at half resolution, each texel doubled: the same picture with LZ-friendly pairs (the light field)."""
    h, w = rgba.shape[:2]
    small = rgba.reshape(h // 2, 2, w // 2, 2, 4).astype(np.float32).mean(axis=(1, 3))
    return np.repeat(np.repeat(np.round(small).astype(np.uint8), 2, axis=0), 2, axis=1)


def paint_field(decoded, rec, system, venue, *, dry=None, turf=None, cap=256, half=False):
    """The SoFi field for one bundle (decoded, the retail layout kept): under the roof every weather looks dry (a rain
    field of the dry layout becomes the dry field; a snow field takes the dry textures resampled); both records lay
    the one SoFi turf (``turf``: the decoded s23 field, whose turf colour, surround and crisp white numbers the Chargers'
    grass field takes); then the end-zone panels and the midfield mark are written, the panels' V is split between the
    two ends, and the midfield quad takes the mark's measured size (its UVs stay)."""
    ml = _ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    if dry is not None:
        d_dec, d_rec, d_system = dry
        same = (d_system == system and len(d_dec) == len(decoded)
                and [(r["width"], r["height"], r["pixel_offset"], r["palette_offset"]) for r in d_rec["embedded_textures"]]
                == [(r["width"], r["height"], r["pixel_offset"], r["palette_offset"]) for r in rec["embedded_textures"]]
                and [s["vertex_streams"] for s in d_rec["shapes"]] == [s["vertex_streams"] for s in rec["shapes"]])
        if same:
            out = bytearray(d_dec)
        else:
            d_rows = ml.texture_rows(d_rec)
            done = set()
            for mat, row in rows.items():
                if row["index"] in done or mat not in d_rows:
                    continue
                done.add(row["index"])
                rgba, _pal = ml.read_p8(d_dec, d_system, d_rows[mat])
                if rgba.shape[:2] != (row["height"], row["width"]):
                    rgba = _resample(rgba, row["width"], row["height"])
                ml.write_p8(out, system, row, rgba, maximum=cap)
    if turf is not None:
        t_dec, t_rec, t_system = turf
        t_rows = ml.texture_rows(t_rec)
        done = set()
        for mat in TURF_MATERIALS:
            row = rows.get(mat)
            if row is None or mat not in t_rows or row["index"] in done:
                continue
            done.add(row["index"])
            t_row = t_rows[mat]
            shape = lambda r: (int(r["width"]), int(r["height"]), int(r["mip_levels"]),
                               int(r["palette_offset"]) - int(r["pixel_offset"]))
            if shape(t_row) == shape(row):
                # the same allocation (every mip level, then the palette): the dome's own bytes, exactly
                src, length = t_system + int(t_row["pixel_offset"]), shape(row)[3] + 1024
                dst = system + int(row["pixel_offset"])
                out[dst:dst + length] = t_dec[src:src + length]
                continue
            rgba, _pal = ml.read_p8(t_dec, t_system, t_row)
            if rgba.shape[:2] != (row["height"], row["width"]):
                rgba = _resample(rgba, row["width"], row["height"])
            ml.write_p8(out, system, row, rgba, maximum=cap)
    for material, art_name in FIELD_MARKS[venue]:
        art = _rgba(FIELD_ART / f"{art_name}.png")
        if half:
            art = _half_detail(art)
        ml.write_p8(out, system, rows[material], art, maximum=cap)
        _snap_palette(out, system, rows[material], _key_colours(art))
    if venue in VENUES:
        grass = _field_shape(rec, "A_grass_color")
        st1 = _stream(grass, 1)
        su, sv, ou, ov = struct.unpack_from("<4f", out, grass["record_offset"] + 0x30)
        for end, (v0, v1) in ENDZONE_V.items():
            for part in "LMR":
                for i in _submesh_vertices(rec, out, grass, f"endzone_{end}_{part}"):
                    at = st1["offset"] + st1["stride"] * i + 6
                    v = struct.unpack_from("<h", out, at)[0] / 32767.0 * sv + ov
                    v = min(1.0, max(0.0, round(v, 3)))
                    struct.pack_into("<h", out, at, int(round((v0 + (v1 - v0) * v - ov) / sv * 32767.0)))
    overlays = _field_shape(rec, "D_graphic_overlays")
    st0, st1 = _stream(overlays, 0), _stream(overlays, 1)
    su, sv, ou, ov = struct.unpack_from("<4f", out, overlays["record_offset"] + 0x30)
    for material, art_name, centre_along in FIELD_QUADS[venue]:
        across, along = art_manifest()[f"field/{art_name}"]["quad_m"]
        idx = _submesh_vertices(rec, out, overlays, material)
        for quad in [idx[k:k + 4] for k in range(0, len(idx), 4)]:
            centre = np.mean([struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i) for i in quad], axis=0)
            if centre_along is not None:
                centre[2] = math.copysign(centre_along * 100.0, centre[2])
            for i in quad:
                qu, qv = struct.unpack_from("<2h", out, st1["offset"] + st1["stride"] * i + 4)
                u = round(qu / 32767.0 * su + ou)
                v = round(qv / 32767.0 * sv + ov)
                _x, y, _z = struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i)
                struct.pack_into("<3f", out, st0["offset"] + st0["stride"] * i, centre[0] + (v - 0.5) * across * 100.0,
                                 y, centre[2] - (u - 0.5) * along * 100.0)
    return bytes(out)


#: SoFi has one turf: the s23 (dome) field's turf colour map, its surround and its crisp white numbers go into the
#: Chargers' (s24) grass field too, with the dome's detail normal map (lab 1: the two records' fields differed)
TURF_SOURCE = "s23dd.iff"
TURF_MATERIALS = ("color_premipped", "grass_outside_premipped", "numbers")
#: the field textures SoFi paints in full, and their art: the three end-zone panels (both ends share them) and the
#: midfield mark for the teams; the LXI mark at midfield and the NFL shield on the 25s for the Super Bowl (the retail s40
#: field has no end-zone textures, only these two logo textures)
FIELD_MARKS = {venue: [(f"endzone_N_{part}", f"{venue}_endzone_{part}") for part in "LMR"]
               + [("center_logo", f"{venue}_midfield")] for venue in VENUES}
FIELD_MARKS["s40"] = [("center_logo", "s40_midfield"), ("logo", "s40_shield")]
#: the overlay quads sized to their art's true proportions, each around its own centre or, where a third value is given,
#: moved along the field to that many metres from midfield (the Super Bowl shields to the 25-yard lines: the retail
#: s40 logos sat on the 30s)
FIELD_QUADS = {venue: [("center_logo", f"{venue}_midfield", None)] for venue in VENUES}
FIELD_QUADS["s40"] = [("center_logo", "s40_midfield", None), ("logo", "s40_shield", 25 * 0.9144)]


def mark_materials(venue):
    return tuple(material for material, _art in FIELD_MARKS[venue])


def keep_mark_palettes(span, graded, marks):
    """(span, entries restored): the painted marks keep their authored palettes after the Modern colour grade.

    The grade's end-zone pass is for retail end zones drawn on grass: it pulls every palette entry of hue 45 to 150
    degrees toward the graded turf. SoFi's end zones and midfield are painted in full in official colours, and that
    pass would move the Rams' sol #FFD100 to (254, 232, 0) and tint the letters' anti-aliased edges, so the marks'
    palettes go back to the authored ones (pixel indices are untouched by the grade) and the span is refit once more.
    Official marks are exact."""
    ml = _ml()
    tx = ml._tools()[0]
    chunk = tx.parse_chunks(graded, allow_trailing=True)[0]
    _rec, decoded = ml._scene(graded, chunk)
    out = bytearray(decoded)
    restored = 0
    for at, palette in marks.items():
        restored += sum(1 for i in range(0, 1024, 4) if out[at:at + 1024][i:i + 4] != palette[i:i + 4])
        out[at:at + 1024] = palette
    if not restored:
        return graded, 0
    rebuilt, _info = ml.fit_span(span, bytes(out))
    back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    sb.require(back == bytes(out), "the field refit read-back differs")
    return rebuilt, restored


#: the field's fitting ladder: the marks at full detail down to 64 colours, then at half detail (each texel doubled) from
#: 256 colours down, then full detail at the fewest colours. Half detail keeps a gradient-rich mark truer than 48 or
#: 32 colours would. Only a field whose span is small needs the lower rungs: the s40 snow fields (85,408 bytes against
#: 112,432 dry: the retail snow textures compress to little, and the NFL's LXI raster does not).
FIELD_LADDER = ([(False, c) for c in (256, 128, 96, 64)] + [(True, c) for c in (256, 128, 96, 64, 48, 32)]
                + [(False, c) for c in (48, 32)])
#: the VC-LZ stream of a field is about 1.30 times its zlib size (measured on the retail s40 snow field, 85,408 against
#: 65,913, and on the SoFi s40ds field, 117,038 against 90,206); the estimate runs low by up to 7 percent at few colours
FIELD_ZLIB_RATIO = 1.30
FIELD_SKIP_OVER = 1.08


def _estimated_size(decoded):
    import zlib
    return int(len(zlib.compress(bytes(decoded), 9)) * FIELD_ZLIB_RATIO)


def field_span(bundle, name, *, dry_bundle=None, turf_bundle=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle: the SoFi field, graded by Modern colour when its
    settings are given (the colour grade runs on the composed art and the span is compressed once, as Arrowhead,
    MetLife and the 2026 venue art do), stepping the authored textures down a palette ladder when the span misses."""
    ml = _ml()
    tx = ml._tools()[0]
    venue = name[:3]
    chunk = ml.bundle_scenes(bundle)["field"]
    span = ml.scene_span(bundle, chunk)
    dry = None
    if dry_bundle is not None and dry_bundle is not bundle:
        dchunk = ml.bundle_scenes(dry_bundle)["field"]
        d_rec, d_dec = ml._scene(dry_bundle, dchunk)
        dry = (d_dec, d_rec, dchunk.system_bytes)
    turf = None
    if turf_bundle is not None and turf_bundle is not bundle:
        tchunk = ml.bundle_scenes(turf_bundle)["field"]
        t_rec, t_dec = ml._scene(turf_bundle, tchunk)
        turf = (t_dec, t_rec, tchunk.system_bytes)
    attempts = []
    base_rec, base_dec = ml._scene(bundle, chunk)
    for half, cap in FIELD_LADDER:
        # a rung the cheap estimate says cannot fit is skipped (the encoder's optimal pass costs about a minute a try)
        estimate = _estimated_size(paint_field(base_dec, base_rec, chunk.system_bytes, venue, dry=dry, turf=turf,
                                               cap=cap, half=half))
        if estimate > chunk.stored_size * FIELD_SKIP_OVER:
            attempts.append(f"{cap} colours{' (half detail)' if half else ''}: skipped, estimated {estimate} bytes")
            continue
        try:
            if colour_settings is not None:
                from . import nfl2k5_modern_color as colour
                marks = {}

                def painter(sp, ch, cap=cap):
                    rec, dec = ml._scene(sp, ch)
                    painted = paint_field(dec, rec, ch.system_bytes, venue, dry=dry, turf=turf, cap=cap, half=half)
                    rows = ml.texture_rows(rec)
                    for material in mark_materials(venue):
                        at = ch.system_bytes + int(rows[material]["palette_offset"])
                        marks[at] = painted[at:at + 1024]
                    return painted, {}
                after, detail = colour.modern_field_scene(span, outer_index=outer_index, settings=colour_settings,
                                                          painter=painter)
                after, restored = keep_mark_palettes(span, after, marks)
                detail = dict(detail or {}, mark_palettes_restored=restored)
            else:
                rec, dec = ml._scene(bundle, chunk)
                painted = paint_field(dec, rec, chunk.system_bytes, venue, dry=dry, turf=turf, cap=cap, half=half)
                after, detail = ml.fit_span(span, painted)
            sb.require(len(after) == len(span), f"{name}: the field escaped its span")
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes", "mark_palettes_restored")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{cap} colours{' (half detail)' if half else ''}: {exc}")
    raise sb.ScneBuildError(f"{name}: the SoFi field does not fit its span: " + " | ".join(attempts))

# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_sofi_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_sofi_receipt/v1"
BUILD_CAPTION = "SoFi Stadium for the Rams and Chargers (experimental)"
HELP_TEXT = (
    "SoFi Stadium, built as a new model, for Rams and Chargers home games in every time of day and weather: the bowl "
    "sunk below grade, the translucent canopy on its 37 columns, the Infinity Screen with the live feed, the plaza, "
    "Rivers Lake and a new pregame flyover with an exterior pass; both teams' 2026 end zones and midfield; the venue "
    "named SoFi Stadium, Inglewood, CA, roofed (no rain or snow on the field) and on turf. A franchise's first Super "
    "Bowl (Super Bowl LXI) is played there too, with the LXI mark at midfield. The 2026 venue art leaves these two "
    "venues to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "SoFi Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported SoFi Stadium pins schema")
    return _PINS


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compile the twenty-seven stretches from a retail source and pin them (the field depends on the art
    and the Modern colour settings, so the receipt records it instead). The stretches are pinned with the committed
    screen panels (model_sha256) and, when the private portrait panels are present, with those too
    (model_portrait_sha256, and portrait_art: the private panels' SHA-256)."""
    global USE_PORTRAITS
    saved = USE_PORTRAITS
    try:
        USE_PORTRAITS = False
        built = build_all(source, progress=progress)
        portrait, portrait_art = {}, {}
        if all(_private_panel_ok(v) for v in VENUES):
            USE_PORTRAITS = True
            portrait_art = {v: sha(portrait_panel(v).read_bytes()) for v in VENUES}
            portrait = build_all(source, progress=progress, names=[n for n in VARIANTS if n[:3] in VENUES])
    finally:
        USE_PORTRAITS = saved
    bundles = []
    for name in VARIANTS:
        retail, model, info = built[name]
        start, end = stretch(retail)
        row = dict(name=name, size=len(retail), offset=start, length=end - start,
                   retail_sha256=sha(retail[start:end]), model_sha256=sha(model[start:end]),
                   system=info["system"], video=info["video"], scratch=info["scratch"], shapes=info["shapes"])
        if name in portrait:
            row["model_portrait_sha256"] = sha(portrait[name][1][start:end])
        bundles.append(row)
    from . import nfl2k5_sofi_crowd as crowd
    ml = _ml()
    crowds = []
    with ml._outer_image()(str(source)) as archive:
        for outer in crowd.TARGETS:
            e = archive.entries[outer]
            data = archive.read(e.virtual_offset, e.size)
            _new, rec = crowd.crowd_resource(data, outer)
            crowds.append(dict(outer=outer, name_id=e.name_id, size=e.size, offset=rec["offset"], length=rec["size"],
                               retail_sha256=rec["before_sha256"], applied_sha256=rec["after_sha256"]))
    doc = dict(schema=PINS_SCHEMA, label=LABEL, bundles=bundles, crowd=crowds, portrait_art=portrait_art,
               source_note="compiled from the retail archive")
    Path(out_path).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def _pin(name):
    return next(p for p in model_pins()["bundles"] if p["name"] == name)


def bundle_state(archive, name, *, fan_receipt=None):
    """retail / applied / foreign for the stadium stretch of one of the twenty-seven bundles."""
    pin = _pin(name)
    e = _entry(archive, _venue_pins()[name])
    if e.size != pin["size"]:
        return "foreign"
    have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
    from . import nfl2k5_model_fan_art as fans
    if fans.applied(have, pin, fan_receipt):
        return "applied"
    if have in (pin["model_sha256"], pin.get("model_portrait_sha256")):
        return "applied"
    return "retail" if have == pin["retail_sha256"] else "foreign"


def _private_panel_ok(venue):
    """The private portrait panel is present and matches its own manifest."""
    try:
        doc = json.loads((PRIVATE_ART / "private.json").read_text(encoding="utf-8"))
        row = doc["panels"][venue]
        return sha((PRIVATE_ART / row["file"]).read_bytes()) == row["sha256"]
    except (OSError, ValueError, KeyError):
        return False


def screen_panels_used():
    """{venue: 'portraits' or 'committed'}: which Infinity Screen panels a build writes now."""
    return {v: "portraits" if portrait_panel(v) is not None else "committed" for v in VENUES}


def receipt_path(source):
    return Path(str(source) + ".sofi.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported SoFi Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the twenty-seven stretches and the three stadium rows."""
    from . import nfl2k5_sofi_venue as sv
    ml = _ml()
    states = set()
    from . import nfl2k5_model_fan_art as fans
    fan_rows = fans.receipt_rows(source, read_receipt(source))
    with ml._outer_image()(str(source)) as archive:
        for name in VARIANTS:
            try:
                states.add(bundle_state(archive, name, fan_receipt=fan_rows.get(name, {}).get("fan_art")))
            except (sb.ScneBuildError, ValueError):
                return "foreign"
        entry = archive.entries[sv.ROST_OUTER_INDEX]
        rows = sv.rost_state(archive.read(entry.virtual_offset, entry.size))
        for pin in model_pins().get("crowd", ()):
            e = archive.entries[pin["outer"]]
            if e.name_id != pin["name_id"] or e.size != pin["size"]:
                return "foreign"
            have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
            states.add("applied" if have == pin["applied_sha256"] else "retail" if have == pin["retail_sha256"]
                       else "foreign")
    if "foreign" in states or rows == "foreign":
        return "foreign"
    if states == {"applied"} and rows == "applied":
        return "applied"
    if states == {"retail"} and rows == "retail":
        return "retail"
    return "mixed"


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    sb.require(state == ("applied" if enabled else "retail"), f"SoFi Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_sofi")
def check_request(source):
    """The build's quick check before any copy: the stretches and the rows are retail (or already SoFi)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Rams and Chargers packages are {state}; build from a supported "
               "retail source")
    return dict(state=state)


def normal_span(bundle):
    """(offset, span) of a bundle's detail normal map: its first TXTR chunk (after the field and the detail layer)."""
    ml = _ml()
    tx = ml._tools()[0]
    chunk = next(c for c in tx.parse_chunks(bundle, allow_trailing=True) if c.kind == "TXTR")
    return chunk.offset, bytes(bundle[chunk.offset:chunk.offset + 32 + chunk.stored_size])


def _compose(job):
    """Worker: (name, retail bundle, dry retail bundle, current image bundle, colour settings or None, outer, the retail
    turf bundle or None, the image's turf normal-map span or None)."""
    name, retail, dry, current, settings, outer, turf, normal = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=sofi_shots(name[:3]), dry_bundle=dry)
    field, finfo = field_span(retail, name, dry_bundle=dry, turf_bundle=turf, colour_settings=settings,
                              outer_index=outer)
    ml = _ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    if normal is not None:
        at, span = normal_span(current)
        sb.require(len(span) == len(normal) and span[4:16] == normal[4:16],
                   f"{name}: the detail normal map's layout differs from the turf's")
        out[at:at + len(normal)] = normal
        finfo = dict(finfo, normal_from=TURF_SOURCE)
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_sofi")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s23 and s24 to it): the SoFi field, stadium,
    cameras and (s24, s40) collapsed cityscape of the twenty-seven bundles, and the three stadium rows. The retail bundles come
    from ``retail_source``; the image's own bundles keep every other chunk (Modern colour's normal map, divots and
    tint word). With Modern colour on, the field art is composed before the colour grade and compressed once, and the
    colour receipt is updated so Modern colour still recognizes its bytes.
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_sofi_venue as sv
    ml = _ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries SoFi Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"SoFi Stadium needs retail Rams and Chargers packages (found {state})")
    try:
        colour_receipt = colour.read_image_receipt(target)
    except (OSError, ValueError):
        colour_receipt = None
    settings = colour_receipt.get("settings") if colour_receipt else None
    colour_before = _colour_states(target, colour_receipt) if colour_receipt else None
    retail = read_retail(retail_source)
    pins = _venue_pins()
    current = {}
    with ml._outer_image()(str(target)) as archive:
        for name in VARIANTS:
            e = _entry(archive, pins[name])
            data = archive.read(e.virtual_offset, e.size)
            chunk = ml.bundle_scenes(retail[name])["field"]
            have = sha(data[chunk.offset:chunk.offset + 32 + chunk.stored_size])
            graded = ((colour_receipt or {}).get("bundle_pins", {}).get(name, {}).get("sites") or [])
            ok = have == sha(ml.scene_span(retail[name], chunk)) or any(
                s.get("kind") == "field" and s.get("applied") == have for s in graded)
            sb.require(ok, f"{name}: the field is neither retail nor Modern colour's; another option wrote it")
            current[name] = data
    turf_normal = normal_span(current[TURF_SOURCE])[1]
    jobs = [(n, retail[n], retail[f"{n[:4]}d.iff"] if n[4] != "d" else None, current[n], settings, pins[n]["outer"],
             retail[TURF_SOURCE] if n[:3] != TURF_SOURCE[:3] else None,
             turf_normal if n[:3] != TURF_SOURCE[:3] else None)
            for n in VARIANTS]
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False, colour=settings is not None, bundles={},
                   screen_panels=screen_panels_used())
    new_colour = deepcopy(colour_receipt) if colour_receipt else None
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="SoFi Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the SoFi bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], applied_sha256=sha(after),
                                            field=info.get("field"), system=info["system"], video=info["video"],
                                            fan_art=info.get("fan_art"))
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        receipt["rost"] = sv.apply_rost(archive)
        receipt["crowd"] = _apply_crowd(archive)
    if new_colour is not None:
        new_colour["sofi"] = dict(bundles=sorted(receipt["bundles"]))
        # Read back bundle by bundle: the SoFi bundles must be Modern colour's under the updated receipt, and
        # every other bundle must keep the state it had before this step. (A whole-image check would also judge
        # bundles another step wrote after Modern colour without re-pinning its receipt: lab 2, 2026-09-24, failed
        # on the MetLife model's s18/s19 stretches. Those keep their state and are named in the receipt.)
        colour_after = _colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after SoFi Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"SoFi Stadium changed the colour state of other bundles: {', '.join(moved)}")
        receipt["colour_other_bundles"] = {state: sorted(n for n in colour_after if n not in mine
                                                         and colour_after[n] == state)
                                           for state in sorted({colour_after[n] for n in colour_after if n not in mine})
                                           if state != new_colour["state"]}
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("SoFi Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None,
                colour_other_bundles=receipt.get("colour_other_bundles"))


def _colour_states(target, colour_receipt):
    """{bundle name: Modern colour state under ``colour_receipt``} for every bundle Modern colour pins."""
    from . import nfl2k5_modern_color as colour
    with colour._outer_image()(str(target)) as archive:
        return {pin["name"]: colour._receipt_bundle_state(archive, pin, colour_receipt)
                for pin in colour._pins()["bundles"]}


def _apply_crowd(archive):
    """The four crowd outers (2026 superfans), each checked against its pin and written back."""
    from . import nfl2k5_sofi_crowd as crowd
    out = []
    for pin in model_pins()["crowd"]:
        e = archive.entries[pin["outer"]]
        data = archive.read(e.virtual_offset, e.size)
        have = sha(data[pin["offset"]:pin["offset"] + pin["length"]])
        if have == pin["applied_sha256"]:
            out.append(dict(outer=pin["outer"], state="already_applied"))
            continue
        sb.require(have == pin["retail_sha256"], f"crowd outer {pin['outer']} is not retail")
        new, rec = crowd.crowd_resource(data, pin["outer"])
        sb.require(rec["after_sha256"] == pin["applied_sha256"], f"crowd outer {pin['outer']} differs from its pin")
        archive.write(e.virtual_offset, new)
        sb.require(archive.read(e.virtual_offset, e.size) == new, f"crowd outer {pin['outer']}: write-back differs")
        out.append(dict(outer=pin["outer"], state="applied", offset=rec["offset"], size=rec["size"]))
    return out


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_sofi_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-bundles", help="write the twenty-seven SoFi bundles (stadium stretch and field) to a folder")
    b.add_argument("source"); b.add_argument("out")
    a = sub.add_parser("apply-lab", help="lab only: write the SoFi stretches and rows into a built disc")
    a.add_argument("disc"); a.add_argument("--source", required=True)
    st = sub.add_parser("status"); st.add_argument("source")
    rp = sub.add_parser("record-pins"); rp.add_argument("source"); rp.add_argument("--out", default=str(PINS_PATH))
    args = parser.parse_args(argv)
    say = lambda m, d, t: print(f"  {m}", flush=True)  # noqa: E731
    if args.command == "status":
        print(image_status(args.source))
        return 0
    if args.command == "record-pins":
        doc = record_pins(args.source, args.out, progress=say)
        print("PINS_OK", len(doc["bundles"]))
        return 0
    if args.command == "build-bundles":
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        info = {}
        retail = read_retail(args.source)
        for name, (_r, model, i) in build_all(args.source, progress=say).items():
            field, finfo = field_span(retail[name], name, dry_bundle=retail[f"{name[:4]}d.iff"])
            chunk = _ml().bundle_scenes(retail[name])["field"]
            model = model[:chunk.offset] + field + model[chunk.offset + len(field):]
            (out / name).write_bytes(model)
            info[name] = dict(i, field=finfo)
        (out / "build.json").write_text(json.dumps(info, indent=1, default=str) + "\n", newline="\n")
        print("SOFI_BUNDLES_OK", len(info))
        return 0
    receipt = apply_lab_disc(args.disc, args.source, progress=say)
    Path(str(args.disc) + ".u6-sofi.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("U6_SOFI_APPLIED", len(receipt["bundles"]), receipt["rost"].get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
