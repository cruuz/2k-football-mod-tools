"""Levi's Stadium model (experimental): the San Francisco 49ers' Levi's Stadium (Santa Clara, opened 2014; the 2025
renovation's 4K video boards) built from scratch as the stadium scene of venue record s25 (retail San Francisco Park),
all nine bundles (day, afternoon, night; dry, rain, snow).

Job st2 (2026-09-25), on u5's builder, u6's SoFi methods and st's Highmark Stadium model. References (the Wikipedia
article, OpenStreetMap, the Commons photos 2014 to 2026, the 2025 board facts from ANC and the trade press, the seating
guides for the benches) are cited in the st2 report. The scene:

* the open-air bowl in its four different stacks: west, the 100 level and the 200 level in front of the suite tower;
  east, the 100 level, the LED ribbon, the 200 level with the loge glass over it and the steep upper deck with the
  light truss on its rim; the two ends, the 100 and 200 levels and a short upper tier; crowd billboards in the retail
  convention, cut at every aisle (u6's method), on 49ers-red seats;
* the suite tower along the west sideline: the club level's glass, four suite levels with their balconies, the teal
  press level leaning out, the roof with its solar panels and green roof, and the light truss along its front edge;
* the two end-zone video boards (the 2025 4K boards: 9,120 x 2,400 pixels at the north end, 39 million pixels for the
  pair, so the south board is narrower) on the ``jumbo_tron`` material the game draws its live feed into (a crop of the
  feed at the picture's own aspect, never stretched) between their stat panels, standing on steel legs over the end
  stands with the LEVI'S STADIUM sign (plain type) on top;
* the facade on the OpenStreetMap outline: the tower's grey precast west face with its windows and the LEVI'S STADIUM
  name, and round the east side and the ends the concourse base under the open white steel frame;
* outside: the plaza, the parking lots, Tasman Drive, the light rail and the San Tomas Aquino Creek from OpenStreetMap,
  the neighbours, and the dry brown hills of the Diablo Range on the horizon;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the boards' stat panels), the markers and the materials the
  executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x plan east; y up from the field; z along, +z the south end zone toward azimuth
151.85 degrees: Highmark's handedness turned 180 degrees, so the suite tower, the press box and the 49ers' bench are on
-x, where every retail stadium keeps the home sideline props and s25 its press box) and centimetres in the game.
EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import json
from . import exact_math as math
import struct
from pathlib import Path


class _LazyNumpy:
    # the Build panel imports this module for its caption and help text; both studios must open without numpy
    def __getattr__(self, name):
        import numpy
        globals()["np"] = numpy
        return getattr(numpy, name)


np = _LazyNumpy()

from . import nfl2k5_metlife_model as mm
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_sofi_model as sm
from . import nfl2k5_stadium_environment as env

OWNER = "nfl2k5_levis_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_levis_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s25"
VENUES = (VENUE,)
#: the plazas and the concourse gates sit a little above the field (DESIGN from the 2014 exterior photos)
GRADE = 2.0
_FOOTPRINT = None

Mesh, blend = mm.Mesh, mm.blend
toward_field, up_toward_field, up, down = mm.toward_field, mm.up_toward_field, mm.up, mm.down


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


# ------------------------------------------------------------------------------------------------ the plan loop

class LoopPoint(mm.LoopPoint):
    """mm.LoopPoint plus the four side weights (west, east, north, south; they sum to 1)."""
    __slots__ = ("w",)


def side_weights(nx, nz):
    """The four sides in this frame: east +x, west -x, south +z, north -z."""
    return dict(E=math.pow(max(nx, 0.0), 2), W=math.pow(max(-nx, 0.0), 2), S=math.pow(max(nz, 0.0), 2),
                N=math.pow(max(-nz, 0.0), 2))


def plan_loop4(xe, xw, zs, zn, R, step=7.0, corner_steps=9):
    """The field-wall line: a rounded rectangle with its four straights at x = +xe (east), x = -xw (west), z = +zs (south)
    and z = -zn (north), corner radius R, counter-clockwise from above (+y), starting on the east straight level with
    the field centre. Each point carries its outward normal, its arc length and the four side weights."""
    segs = []

    def line(p0, p1, n):
        k = max(1, int(round(math.dist(p0, p1) / step)))
        for i in range(k):
            t = i / k
            segs.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, n[0], n[1]))

    def arc(cx, cz, a0, a1):
        for i in range(corner_steps):
            a = a0 + (a1 - a0) * i / corner_steps
            segs.append((cx + R * math.cos(a), cz + R * math.sin(a), math.cos(a), math.sin(a)))

    line((xe, 0.0), (xe, zs - R), (1, 0))
    arc(xe - R, zs - R, 0.0, math.pi / 2)
    line((xe - R, zs), (-xw + R, zs), (0, 1))
    arc(-xw + R, zs - R, math.pi / 2, math.pi)
    line((-xw, zs - R), (-xw, -zn + R), (-1, 0))
    arc(-xw + R, -zn + R, math.pi, 1.5 * math.pi)
    line((-xw + R, -zn), (xe - R, -zn), (0, -1))
    arc(xe - R, -zn + R, 1.5 * math.pi, 2 * math.pi)
    line((xe, -zn + R), (xe, 0.0), (1, 0))
    pts, s, prev = [], 0.0, None

    def w(v):
        v = abs(v)
        return 1.0 if v > 0.999 else math.pow(float(np.clip((v - 0.55) / 0.4, 0, 1)), 2)

    for x, z, nx, nz in segs + [segs[0]]:
        if prev is not None:
            s += math.dist(prev, (x, z))
        prev = (x, z)
        lp = LoopPoint(x, z, nx, nz, s, w(nx), w(nz))
        lp.w = side_weights(nx, nz)
        pts.append(lp)
    return pts


# ------------------------------------------------------------------------------------------------ parameters

#: DESIGN, pass 1. The wall line is the OpenStreetMap bowl rim (relation 14507664's inner way: the west wall 39.9 m and
#: the east 39.4 m off the field's centre line, the ends 64.8 and 63.7 m), each straight moved out just past the retail
#: s25 sideline props (they reach x -40.6 and 44.4, z -64.5 and 68.7: the cameras behind the end zones). The stacks
#: follow the photos (the 2014 interiors and panoramas, the 2019 panorama, Super Bowl LX, the 2026 World Cup): west, 26
#: rows of the 100 level and 10 of the 200 level under the suite tower; east, 30 and 12 rows, the loge glass and a
#: 30-row upper deck to about 47 m; the ends, 22 to 24 and 12 rows and an upper tier under the boards (pass 2: 18 rows
#: at the north end, deeper than the south's 16, from the 2016 satellite view and the 2014 north-end photo).
PARAMS = dict(
    loop=dict(xe=45.6, xw=41.8, zs=69.8, zn=65.8, R=22.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    sides=dict(
        W=dict(low_d0=3.0, low_y0=1.5, low_rows=26, low_tread=0.84, low_rise0=0.30, low_rise1=0.56,
               t2_over=3.0, t2_rows=10, t2_rise=0.52, band_h=0.0,
               up_d=40.0, up_y=30.0, up_rows=0, up_tread=0.80, up_rise=0.62),
        E=dict(low_d0=2.5, low_y0=1.4, low_rows=30, low_tread=0.84, low_rise0=0.28, low_rise1=0.48,
               t2_over=3.5, t2_rows=12, t2_rise=0.54, band_h=3.2,
               up_d=33.0, up_y=26.5, up_rows=30, up_tread=0.80, up_rise=0.62),
        N=dict(low_d0=2.5, low_y0=1.4, low_rows=22, low_tread=0.84, low_rise0=0.30, low_rise1=0.46,
               t2_over=3.0, t2_rows=12, t2_rise=0.54, band_h=0.0,
               up_d=27.0, up_y=21.0, up_rows=18, up_tread=0.80, up_rise=0.62),
        S=dict(low_d0=2.5, low_y0=1.4, low_rows=24, low_tread=0.84, low_rise0=0.30, low_rise1=0.46,
               t2_over=3.0, t2_rows=12, t2_rise=0.54, band_h=0.0,
               up_d=28.0, up_y=22.0, up_rows=16, up_tread=0.80, up_rise=0.62),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the suite tower (pass 2, from the Super Bowl LX photo's solved pose and the 2016 satellite view): its face over the
    #: west 200 level's front row (the 200 level runs under its first floor, the 2014 tower photo), its glass from about
    #: 19.5 m up, its south end near z 80 and its north end near z -88; its back on the outline's west straight (OSM, x
    #: -109.7); the club level, four suite levels with balconies, the press level leaning out, the roof over it
    tower=dict(z0=-88.0, z1=80.0, base_y=19.5, club_h=4.6, suite_h=4.2, suites=4, press_h=4.8, roof_h=1.4, overhang=4.0,
               balcony=2.2, lean=1.2, rail_h=1.1, roof_white=0.45, roof_green=0.30),
    #: the light trusses (the 2014 interiors: a white lattice along the east rim and the tower roof's front edge)
    rails=dict(h=3.2, every=2, east_every=1, w=5.0, lamp_h=2.2),
    #: the 2025 boards (ANC: the largest outdoor 4K boards in the NFL, 9,120 x 2,400 pixels, 19.2 m tall at 8 mm): the
    #: south board measured on the Super Bowl LX photo's solved pose (st2 pass 2: 7 px rms from the goalposts and the
    #: field's corners): 66 m across its frame, its centre 17 m west of the field axis, its bottom about 33 m up, the live
    #: picture over the middle 61 percent between the stat panels; the north board 73 m (the 9,120-pixel one, INFERRED)
    #: and west of the axis by the same 17 m (INFERRED: the 2014 north board stood west of the axis, the Commons interior)
    boards=dict(north_w=73.0, south_w=66.0, h=19.2, feed=0.61, offset_x=-17.0, bottom=33.0, depth=3.0, sign_w=30.0,
                sign_h=7.5, leg=1.2),
    #: the west face: the glass curtain's middle and width, the banner's place (the 2014 photo from the west lots)
    facade=dict(base=8.0, frame_u=9.0, stair_h=22.0, curtain_z=4.0, curtain_w=64.0, banner_z=-52.0),
    hills=dict(radius=3600.0, points=40),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


# ------------------------------------------------------------------------------------------------ the model

class Levis(sm.SoFi):
    SECTORS = 12

    def __init__(self, params=None, venue=VENUE):
        p = json.loads(json.dumps(PARAMS))
        for k, v in (params or {}).items():
            if k == "sides":
                for s, vv in v.items():
                    p["sides"][s].update(vv)
            else:
                p[k].update(v)
        self.p, self.venue = p, venue
        q = p["loop"]
        self.loop = plan_loop4(q["xe"], q["xw"], q["zs"], q["zn"], q["R"], q["step"], q["corner_steps"])
        self.aisles = self._aisle_positions()
        self.meshes = {}
        self.markers = {}
        # the suite tower's face stands over the west 200 level's front row; the 200 level runs under its first floor
        west = self._stack(lambda key: p["sides"]["W"][key], None)
        t = p["tower"]
        self.tower_d = west["t2"][0][0] + 0.6
        self.tower_x = -(q["xw"] + self.tower_d)
        self.tower_y = max(t["base_y"], west["t2"][-1][1] + 2.2)
        self.tower_under_d = west["t2"][-1][0] + 0.8
        # its west face is the outline's long west straight (OSM: x -109.7 from z -91.7 to 92.6)
        ring = np.array(footprint()["facade"], float)
        back = ring[ring[:, 0] < self.tower_x - 20.0]
        self.tower_back = float(back[:, 0].min()) if len(back) else self.tower_x - 30.0

    def in_tower(self, x, z, margin=0.0, y=None):
        """True inside the tower's plan (with ``margin``), and at or over its first floor when ``y`` is given (the 200 level
        runs under it)."""
        t = self.p["tower"]
        inside = x < self.tower_x + margin and t["z0"] - margin < z < t["z1"] + margin
        return inside and (y is None or y > self.tower_y - 1.0)

    def tower_zone(self, lp):
        t = self.p["tower"]
        return lp.w["W"] > 0.5 and t["z0"] < lp.z < t["z1"]

    # -- the section: four stacks, blended round the corners ------------------------------------------------------
    def section(self, lp):
        p = self.p
        return self._stack(lambda key: _side_blend(lp, key, p), lp)

    def _stack(self, g, lp):
        p = self.p
        out = {}

        def blocked(d, y=None):
            if lp is None or not hasattr(self, "tower_x"):
                return False
            x, _y, z = self.at(lp, d, 0.0)
            return self.in_tower(x, z, 1.0, y)
        # the 100 level
        rows = int(round(g("low_rows")))
        d, y = g("low_d0"), g("low_y0")
        lower = [(d, y)]
        r0, r1, tread = g("low_rise0"), g("low_rise1"), g("low_tread")
        for i in range(rows):
            t = i / max(1, rows - 1)
            d += tread
            y += r0 + (r1 - r0) * t * t
            lower.append((d, y))
        out["lower"] = lower
        # the ribbon over the 100 level (WELCOME TO LEVI'S STADIUM all round, the 2014 interiors)
        fh, gap = p["tier"]["fascia_h"], p["tier"]["gap"]
        d2 = lower[-1][0] - g("t2_over")
        y2 = lower[-1][1] + 1.1
        out["ribbon"] = (d2, y2, y2 + fh)
        out["lower_back"] = (lower[-1][0] + 0.6, lower[-1][1], y2 - 0.02)
        out["soffit2"] = (d2 + 0.02, lower[-1][0] + 0.6, y2)
        # the 200 level
        rows2 = int(round(g("t2_rows")))
        d, y = d2 + 0.4, y2 + fh + gap
        t2 = [(d, y)]
        for _i in range(rows2):
            if blocked(d + p["tier"]["tread"], y + g("t2_rise") + 2.0):
                break
            d += p["tier"]["tread"]
            y += g("t2_rise")
            t2.append((d, y))
        out["t2"] = t2
        if lp is not None and self.tower_zone(lp):
            # the west side: the 200 level runs under the tower's first floor; behind its last row the concourse wall up
            # to the tower's underside
            out["tower_back"] = (t2[-1][0] + 0.8, t2[-1][1], self.tower_y - 0.4)
            out["tower_ledge"] = (t2[-1][0], t2[-1][0] + 0.8, t2[-1][1])
            return out
        # the loge glass over the east 200 level
        bh = g("band_h")
        yb = t2[-1][1] + 0.3
        db = t2[-1][0] + 1.0
        if bh > 0.2:
            out["band"] = (db, yb, yb + bh)
            out["band_floor"] = (t2[-1][0], db, t2[-1][1])
        prev = t2
        # the upper deck: its front where the side's stack puts it, never lower than 2.5 m over the 200 level's last row
        du = g("up_d")
        yu = max(g("up_y"), prev[-1][1] + 2.5 - max(0.0, prev[-1][0] - du) * g("up_rise") / g("up_tread"))
        rowsu = int(round(g("up_rows")))
        if lp is not None:
            room = self.facade_depth(lp) - 1.0 - p["rim"]["walk"] * 0.5 - 0.7 - (du + 0.4)
            rowsu = max(0, min(rowsu, int(room / g("up_tread"))))
            if blocked(du, yu):
                rowsu = 0
        if rowsu < 2:
            # no upper deck here (the tower's ends): the 200 level's back wall and a walk behind it
            y = t2[-1][1]
            dback = t2[-1][0] + 0.3
            walk_end = dback + p["rim"]["walk"]
            if lp is not None:
                walk_end = min(walk_end, self.facade_depth(lp) - 1.0)
            out["rim"] = (dback, y, y + p["rim"]["back_wall"], max(dback + 0.3, walk_end))
            return out
        out["up_fascia"] = (du, yu, yu + fh)
        slope = g("up_rise") / g("up_tread")
        dback = max(prev[-1][0] + 0.5, du + 0.5)
        yback = yu + (dback - du) * slope - 1.4 * (1.0 if dback > du + 2.0 else 0.0)
        yback = max(yback, prev[-1][1] + 2.2)
        out["back3"] = (dback, prev[-1][1], yback - 0.02)
        out["up_soffit_slope"] = ((du + 0.02, yu), (dback, yback))
        d, y = du + 0.4, yu + fh + gap
        upd = [(d, y)]
        for _i in range(rowsu):
            if blocked(d + g("up_tread"), y + g("up_rise")):
                break
            d += g("up_tread")
            y += g("up_rise")
            upd.append((d, y))
        out["upper"] = upd
        rim = p["rim"]
        walk_end = d + 0.3 + rim["walk"]
        if lp is not None:
            walk_end = min(walk_end, self.facade_depth(lp) - 1.0)
        out["rim"] = (d + 0.3, y, y + rim["back_wall"], max(d + 0.6, walk_end))
        return out

    def facade_depth(self, lp):
        """Distance from a wall-line point along its outward normal to the facade outline (OSM)."""
        cache = self.__dict__.setdefault("_facade_depth", {})
        key = (round(lp.x, 4), round(lp.z, 4), round(lp.nx, 4), round(lp.nz, 4))
        if key not in cache:
            ring = np.array(footprint()["facade"], float)
            p_ = np.array([lp.x, lp.z]); d_ = np.array([lp.nx, lp.nz])
            best = 1e9
            for i in range(len(ring)):
                a, b = ring[i], ring[(i + 1) % len(ring)]
                e = b - a
                den = d_[0] * (-e[1]) - d_[1] * (-e[0])
                if abs(den) < 1e-12:
                    continue
                w = a - p_
                t = (w[0] * (-e[1]) - w[1] * (-e[0])) / den
                u = (d_[0] * w[1] - d_[1] * w[0]) / den
                if t > 0 and 0 <= u <= 1:
                    best = min(best, t)
            cache[key] = best
        return cache[key]

    # -- build --------------------------------------------------------------------------------------------------
    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        self.light_points = []
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"lv_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "lv"
        self._tower()
        self._rails(loop, secs)
        self._boards(loop, secs)
        east = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(east)["upper"][4]
        self.nosebleed = self.at(east, row[0] + 0.3, row[1] + 0.05)
        self._facade(loop, secs)
        self._exterior()
        return self

    def mesh(self, name):
        if name.startswith("lv_bowl_"):
            name = getattr(self, "prefix", "lv_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats: red on every level, a few faded seats toward the back --------------------------------------------
    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
        """u6's seating surface every ``seats.rows_per_grid`` rows (u one repeat per section, the steps under every aisle),
        laid in three bands by depth in the tier (front, middle and back rows: the same red with more faded seats
        toward the back)."""
        rows = self.p["seats"]["rows_per_grid"]
        R = max(len(pr) for pr in profiles) - 1
        if R < 1:
            return
        ks = list(range(0, R + 1, rows))
        if ks[-1] != R:
            ks.append(R)
        pts = [[self.at(lp, *pr[min(k, len(pr) - 1)]) for lp, pr in zip(loop, profiles)] for k in ks]
        uvs = [[(self.aisle_u(lp.s), vstart + min(k, len(pr) - 1) / self.p["seats"]["rows_per_v"])
                for lp, pr in zip(loop, profiles)] for k in ks]
        a = min(range(len(ks)), key=lambda i: abs(ks[i] - 0.35 * R))
        b = max(a, min(range(len(ks)), key=lambda i: abs(ks[i] - 0.68 * R)))
        for mat, i0, i1 in (("lv_seat_front", 0, a), ("lv_seat_mid", a, b), ("lv_seat_back", b, len(ks) - 1)):
            if i1 > i0:
                m.grid(mat, pts[i0:i1 + 1], uvs[i0:i1 + 1], facing=up_toward_field)

    @staticmethod
    def _runs(secs, key, extra=None):
        """Runs of consecutive indices whose sections carry ``key`` (and pass ``extra``), at least two long."""
        out, run = [], []
        for i, sec in enumerate(secs):
            if key in sec and (extra is None or extra(sec)):
                run.append(i)
            else:
                if len(run) >= 2:
                    out.append(run)
                run = []
        if len(run) >= 2:
            out.append(run)
        return out

    def _rows_runs(self, m, loop, secs, key):
        """Seats and crowd for a tier that exists on part of the loop (runs of points with at least two rows)."""
        for run in self._runs(secs, key, lambda sec: len(sec[key]) > 1):
            lps = [loop[i] for i in run]
            prof = [secs[i][key] for i in run]
            self._rows_surface(m, "lv_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("lv_bowl_a")
        wall = p["wall"]["height"]
        m.grid("lv_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        # the apron from the wall top to the first row
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("lv_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "lv_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_lv_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        # the ribbon and the 200 level
        m2 = self.mesh("lv_bowl_b")
        self._ledge(m2, "lv_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_lv_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_lv_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "lv_concrete", loop, secs, "band_floor", up)
        self._ledge(m2, "lv_concrete", loop, secs, "tower_ledge", up)
        self._band(m2, "LIGHT_lv_concourse", loop, secs, "tower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        # the upper deck (east and the ends)
        m4 = self.mesh("lv_bowl_d")
        self._band(m4, "LIGHT_lv_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("lv_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                    [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_lv_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall, its walk and the wall down to the plaza behind it
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            m4.grid("LIGHT_lv_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                           [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("lv_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 0.4) for lp in lps]], facing=up)
            m4.grid("lv_concrete", [[self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, r[3], GRADE - 0.5) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 1.0) for lp in lps]],
                    facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
            # the concourse decks behind the rim out to the steel frame on the outline (from above, the 2016 satellite
            # view: grey decks and roofs fill the ring between the seats and the facade)
            outer = [max(r[3] + 0.5, self.facade_depth(lp) - 0.8) for lp, r in zip(lps, rims)]
            m4.grid("lv_concrete", [[self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, o, r[2]) for lp, r, o in zip(lps, rims, outer)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 1.0) for lp in lps]], facing=up)

    def _portals(self, m, loop, secs, key, row):
        q = self.p["portals"]
        every = q["every_m"]
        for a, b, sa, sb_ in zip(loop[:-1], loop[1:], secs[:-1], secs[1:]):
            k0, k1 = math.floor(a.s / every), math.floor(b.s / every)
            if k1 == k0:
                continue
            t = (k1 * every - a.s) / max(b.s - a.s, 1e-9)
            pa, pb = sa.get(key), sb_.get(key)
            if pa is None or pb is None or row >= len(pa) - 1 or row >= len(pb) - 1:
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
            m.quad("lv_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    # -- the suite tower ---------------------------------------------------------------------------------------------
    def tower_levels(self):
        """[(material, y0, y1)] of the tower's field face from the club level up to the roof's underside."""
        t = self.p["tower"]
        y = self.tower_y
        out = [("LIGHT_lv_glass", y, y + t["club_h"])]
        y += t["club_h"]
        for _k in range(t["suites"]):
            out.append(("LIGHT_lv_suites", y, y + t["suite_h"]))
            y += t["suite_h"]
        out.append(("LIGHT_lv_press", y, y + t["press_h"]))
        return out

    def _tower(self):
        """The suite tower along the west sideline (the 2014 tower photo): the club level's glass over the 200 level,
        four suite levels behind white balcony slabs with glass rails, the teal press level leaning out, and the roof:
        its white fascia and underside over the press level, the solar panels and the green roof on top, the light
        truss along its front edge. Its end walls are grey precast; its west face is the facade (``_facade``)."""
        t = self.p["tower"]
        m = self.meshes.setdefault("lv_tower", Mesh("lv_tower"))
        z0, z1 = t["z0"], t["z1"]
        xf = self.tower_x
        face = lambda p_: np.array([1.0, 0.0, 0.0])  # noqa: E731
        zs = [z0 + (z1 - z0) * k / 6 for k in range(7)]

        def wall_x(x, y0, y1, mat, u_per_m=1 / 8.0, xtop=None):
            xt = x if xtop is None else xtop
            m.grid(mat, [[(x, y0, z) for z in zs], [(xt, y1, z) for z in zs]],
                   [[(z * u_per_m, 1.0) for z in zs], [(z * u_per_m, 0.0) for z in zs]], facing=face)
        levels = self.tower_levels()
        for mat, y0, y1 in levels:
            if mat == "LIGHT_lv_press":
                wall_x(xf + 0.5, y0, y1, mat, 1 / 12.0, xtop=xf + 0.5 + t["lean"])
                continue
            wall_x(xf, y0, y1, mat, 1 / 12.0 if mat == "LIGHT_lv_suites" else 1 / 8.0)
            if mat == "LIGHT_lv_suites":
                # the balcony: its white slab edge, its floor and the glass rail at its front
                xb = xf + t["balcony"]
                m.grid("lv_white", [[(xf, y0, z) for z in zs], [(xb, y0, z) for z in zs]],
                       [[(z / 8.0, 0.0) for z in zs], [(z / 8.0, 0.3) for z in zs]], facing=up)
                m.grid("lv_white", [[(xb, y0 - 0.45, z) for z in zs], [(xb, y0, z) for z in zs]],
                       [[(z / 8.0, 1.0) for z in zs], [(z / 8.0, 0.0) for z in zs]], facing=face)
                m.grid("lv_white", [[(xf, y0 - 0.45, z) for z in zs], [(xb, y0 - 0.45, z) for z in zs]],
                       [[(z / 8.0, 0.0) for z in zs], [(z / 8.0, 0.3) for z in zs]], facing=down)
                m.grid("lv_balcony", [[(xb, y0, z) for z in zs], [(xb, y0 + t["rail_h"], z) for z in zs]],
                       [[(z / 4.0, 1.0) for z in zs], [(z / 4.0, 0.0) for z in zs]], facing=face)
        # the roof: fascia, underside over the press level, the top (solar panels then the green roof)
        yr = levels[-1][2]
        xr = xf + 0.5 + t["lean"] + t["overhang"]
        xb = self.tower_back
        m.grid("lv_white", [[(xr, yr, z) for z in zs], [(xr, yr + t["roof_h"], z) for z in zs]],
               [[(z / 8.0, 1.0) for z in zs], [(z / 8.0, 0.0) for z in zs]], facing=face)
        m.grid("lv_roof_under", [[(xr, yr, z) for z in zs], [(xf + 0.5 + t["lean"], yr, z) for z in zs]],
               [[(z / 6.0, 0.0) for z in zs], [(z / 6.0, 0.6) for z in zs]], facing=down)
        # the roof from the front: white panels over the press level, the green roof, the solar panels along the back
        # (the 2016 satellite view: a light roof toward the field, the dark striped solar strip along the west edge)
        top = yr + t["roof_h"]
        xw_ = xr + (xb - xr) * t["roof_white"]
        xg_ = xw_ + (xb - xr) * t["roof_green"]
        for mat, a_, b_, per in (("lv_roof_under", xr, xw_, 6.0), ("lv_green", xw_, xg_, 12.0), ("lv_solar", xg_, xb, 10.0)):
            m.grid(mat, [[(a_, top, z) for z in zs], [(b_, top, z) for z in zs]],
                   [[(z / per, 0.0) for z in zs], [(z / per, (a_ - b_) / per) for z in zs]], facing=up)
        # the first floor's underside over the 200 level, from the glass back to the concourse wall behind its last row
        xu = -(self.p["loop"]["xw"] + self.tower_under_d)
        yu = self.tower_y - 0.4
        m.grid("lv_roof_under", [[(xf, yu, z) for z in zs], [(xu, yu, z) for z in zs]],
               [[(z / 6.0, 0.0) for z in zs], [(z / 6.0, (xf - xu) / 6.0) for z in zs]], facing=down)
        m.grid("lv_white", [[(xf, yu, z) for z in zs], [(xf, self.tower_y, z) for z in zs]],
               [[(z / 8.0, 1.0) for z in zs], [(z / 8.0, 0.0) for z in zs]], facing=face)
        # the end walls (grey precast): over the stands from the first floor to the roof, and behind the 200 level's
        # concourse wall down to the plaza
        for zc, sgn in ((z0, -1.0), (z1, 1.0)):
            xs_ = (xr, xf, xb)
            m.grid("lv_facade", [[(x, yu, zc) for x in xs_], [(x, top, zc) for x in xs_]],
                   [[(x / 12.0, (top - yu) / 12.0) for x in xs_], [(x / 12.0, 0.0) for x in xs_]],
                   facing=lambda p_, s=sgn: np.array([0.0, 0.0, s]))
            xl = (xu - 2.0, xb)
            m.grid("lv_facade", [[(x, GRADE - 0.5, zc) for x in xl], [(x, yu, zc) for x in xl]],
                   [[(x / 12.0, (yu - GRADE) / 12.0) for x in xl], [(x / 12.0, 0.0) for x in xl]],
                   facing=lambda p_, s=sgn: np.array([0.0, 0.0, s]))
        self.tower_top = top
        self.tower_roof_front = xr
        # the light truss along the roof's front edge, its lamps facing the field
        self._truss_line(m, [(xr - 0.4, top, z) for z in np.linspace(z0 + 4, z1 - 4, 25)], np.array([1.0, 0.0, 0.0]))

    # -- the light trusses ----------------------------------------------------------------------------------------
    def _truss_line(self, m, base_pts, toward):
        """A white lattice truss standing on ``base_pts`` (a polyline), its floodlights on the field side tilted down,
        every ``rails.every`` points; each lamp's centre joins ``light_points``."""
        q = self.p["rails"]
        P = [np.array(b, float) for b in base_pts]
        L = np.concatenate([[0.0], np.cumsum([math.np_norm(b - a) for a, b in zip(P[:-1], P[1:])])])
        if toward is None:
            facing = lambda p_: -np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        else:
            facing = lambda p_, t=np.asarray(toward, float): t  # noqa: E731
        m.grid("lv_truss", [[tuple(b) for b in P], [tuple(b + [0.0, q["h"], 0.0]) for b in P]],
               [[(s / (2 * q["h"]), 1.0) for s in L], [(s / (2 * q["h"]), 0.0) for s in L]], facing=facing)
        lm = self.meshes.setdefault("lv_lights", Mesh("lv_lights"))
        for k in range(0, len(P) - 1, getattr(self, "_lamp_every", q["every"])):
            a, b = P[k], P[min(k + 1, len(P) - 1)]
            along = b - a
            along[1] = 0.0
            along /= max(1e-9, math.np_norm(along))
            n = toward if toward is not None else np.array([-a[0], 0.0, -a[2]])
            n = np.asarray(n, float) / max(1e-9, math.np_norm(n))
            ctr = (a + b) / 2 + np.array([0.0, q["h"] * 0.6, 0.0]) + n * 0.4
            normal = n * math.cos(math.radians(35)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(35))
            upv = np.cross(along, normal)
            upv = upv / math.np_norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["lamp_h"] / 2)
            lm.quad("LIGHT_lv_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                    (0, 0), facing=lambda p_, nn=normal: nn)
            self.light_points.append(tuple(ctr))

    def _rails(self, loop, secs):
        """The east rim's light truss (the 2014 interiors and the World Cup photo: a row of floodlights along the top of
        the east upper deck), on the rim's back wall wherever the east weight leads."""
        m = self.meshes.setdefault("lv_rails", Mesh("lv_rails"))
        self._lamp_every = self.p["rails"]["east_every"]
        for run in self._runs(secs, "rim", lambda sec: "upper" in sec):
            pts = []
            for i in run:
                lp, r = loop[i], secs[i]["rim"]
                if lp.w["E"] < 0.5:
                    if len(pts) >= 2:
                        self._truss_line(m, pts, None)
                    pts = []
                    continue
                pts.append(self.at(lp, r[0] + 0.3, r[2]))
            if len(pts) >= 2:
                self._truss_line(m, pts, None)

    # -- the video boards --------------------------------------------------------------------------------------------
    #: the live feed fills u 0 to 0.625, v 0 to 0.875 of the jumbo_tron render target (PROVED OFFLINE by u5 and u6); a
    #: board shows the band of it at the picture's own aspect (the middle rows of the picture, where the play is)
    FEED_U = (0.0, 0.625)
    FEED_V = (0.0, 0.875)

    def board_crop(self, aspect):
        u0, u1 = self.FEED_U
        v0, v1 = self.FEED_V
        w_px, h_px = 640.0, 448.0
        if aspect >= w_px / h_px:
            hh = w_px / aspect / 512.0
            vc = (v0 + v1) / 2
            return (u0, u1), (vc - hh / 2, vc + hh / 2)
        ww = h_px * aspect / 1024.0
        uc = (u0 + u1) / 2
        return (uc - ww / 2, uc + ww / 2), (v0, v1)

    def _boards(self, loop, secs):
        """A board over each end stand, west of the field axis by ``offset_x`` behind the upper tier's rim, facing the
        field: the black housing on four steel legs, the live picture over the middle ``feed`` of it between two stat
        panels, the LEVI'S STADIUM sign on top (both faces; plain type)."""
        q = self.p["boards"]
        m = self.meshes.setdefault("lv_boards", Mesh("lv_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        H, Dp, ox = q["h"], q["depth"], q["offset_x"]
        for end, W in ((-1, q["north_w"]), (1, q["south_w"])):
            (U0, U1), (V0, V1) = self.board_crop(W * q["feed"] / H)
            k = max(range(len(loop) - 1), key=lambda i: end * loop[i].z - abs(loop[i].x - ox) * 0.01)
            lp, sec = loop[k], secs[k]
            r = sec["rim"]
            zc = lp.z + lp.nz * (r[3] + Dp / 2 + 0.6)
            y0 = max(q["bottom"], r[1] + 0.5)          # never below the end's last row (its bottom hides behind the rim wall)
            face = np.array([0.0, 0.0, -float(end)])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
            c = np.array([ox, y0, zc])
            hv = np.array([0.0, H, 0.0])
            m.box("lv_black", c + hv / 2, (right, (0, 1, 0), face), (W / 2 + 0.6, H / 2 + 0.6, Dp / 2), uvscale=0.1,
                  bottom=True)
            # the legs, down to the plaza behind the end stand
            for s_ in (-0.42, -0.14, 0.14, 0.42):
                lc = c + right * (s_ * W) - face * 0.0
                hy = (y0 - 0.6 - (GRADE - 0.5)) / 2
                m.box("lv_steel", np.array([lc[0], GRADE - 0.5 + hy, lc[2]]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                      (q["leg"] / 2, hy, q["leg"] / 2), uvscale=0.1)
            fc = c + face * (Dp / 2 + 0.05)
            fw = W * q["feed"] / 2
            A, B = fc - right * fw, fc + right * fw
            m.quad("jumbo_tron", A, B, B + hv, A + hv, (U0, V1), (U1, V1), (U1, V0), (U0, V0), facing=lambda p_, f=face: f)
            pw = W * (1.0 - q["feed"]) / 2
            panels = []
            for s_ in (-1, 1):
                pc = fc + right * s_ * (fw + pw / 2)
                ph = right * (pw / 2 - 0.2)
                m.quad("LIGHT_lv_board_panel", pc - ph, pc + ph, pc + ph + hv, pc - ph + hv, (0, 1), (1, 1), (1, 0),
                       (0, 0), facing=lambda p_, f=face: f)
                panels.append(pc)
            # the sign on top, both faces
            sw, sh = q["sign_w"], q["sign_h"]
            for f_, sgn in ((face, 1.0), (-face, -1.0)):
                sc = np.array([ox, y0 + H + 1.0, zc]) + f_ * (Dp / 2 + 0.1)
                rr = np.cross(-f_, (0.0, 1.0, 0.0)); rr /= math.np_norm(rr)
                m.quad("lv_letters", sc - rr * sw / 2, sc + rr * sw / 2, sc + rr * sw / 2 + [0, sh, 0],
                       sc - rr * sw / 2 + [0, sh, 0], (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=f_: f)
            m.box("lv_black", np.array([ox, y0 + H + 1.0 + sh / 2, zc]), (right, (0, 1, 0), face), (sw / 2, sh / 2, Dp / 2 - 0.2),
                  uvscale=0.1)
            self.markers["jumbo"].append((ox, y0 + H / 2, float(fc[2])))
            self.board_frames.append(dict(centre=c, right=right, face=face, width=W, height=H, panels=panels,
                                          panel_w=pw))

    # -- the facade ---------------------------------------------------------------------------------------------------
    def rim_height_at(self, x, z):
        """The rim's top height of the nearest loop point by direction from the field centre."""
        a = math.atan2(z, x)
        best, h = 1e9, 0.0
        for lp, sec in zip(self.loop, self.secs):
            if "rim" not in sec:
                continue
            da = abs(((math.atan2(lp.z, lp.x) - a + math.pi) % (2 * math.pi)) - math.pi)
            if da < best:
                best, h = da, sec["rim"][2]
        return h

    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

    def _facade(self, loop, secs):
        """The outline (OSM): along the west straight the suite tower's precast face with its windows up to the roof
        (lower at the stair towers past its ends) and the LEVI'S STADIUM name high on it; elsewhere the concourse base
        and, over it, the open white steel frame up to the rim (the stands' backs show through it)."""
        q = self.p["facade"]
        t = self.p["tower"]
        ring, _pos = self.facade_ring(200)
        R = list(ring) + [ring[0]]
        n = len(ring)
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(R[:-1], R[1:])])])
        m = self.meshes.setdefault("lv_facade", Mesh("lv_facade"))
        outward = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        west = lambda x, z: x < self.tower_back + 3.0  # noqa: E731

        def top_of(x, z):
            if west(x, z):
                return self.tower_top if t["z0"] <= z <= t["z1"] else GRADE + q["stair_h"]
            return max(GRADE + q["base"] + 4.0, self.rim_height_at(x, z) + 1.0)

        def runs(pred):
            out, run = [], []
            for i in range(n + 1):
                if pred(*R[i]):
                    run.append(i)
                else:
                    if len(run) >= 2:
                        out.append(run)
                    run = []
            if len(run) >= 2:
                out.append(run)
            return out
        tops = [top_of(x, z) for x, z in R]
        base_top = GRADE + q["base"]
        # the west face: precast wings either side of the glass curtain in its middle (the 2014 photo from the lots)
        glass = lambda x, z: west(x, z) and abs(z - q["curtain_z"]) < q["curtain_w"] / 2  # noqa: E731
        for run in runs(lambda x, z: west(x, z) and not glass(x, z)):
            m.grid("lv_facade", [[(R[j][0], GRADE - 0.5, R[j][1]) for j in run], [(R[j][0], tops[j], R[j][1]) for j in run]],
                   [[(L[j] / 16.0, (tops[j] - GRADE) / 16.0) for j in run], [(L[j] / 16.0, 0.0) for j in run]],
                   facing=outward)
        for run in runs(glass):
            m.grid("LIGHT_lv_curtain", [[(R[j][0], GRADE - 0.5, R[j][1]) for j in run], [(R[j][0], tops[j], R[j][1]) for j in run]],
                   [[(L[j] / 20.0, (tops[j] - GRADE) / 20.0) for j in run], [(L[j] / 20.0, 0.0) for j in run]],
                   facing=outward)
        for run in runs(lambda x, z: not west(x, z)):
            m.grid("LIGHT_lv_base", [[(R[j][0], GRADE - 0.5, R[j][1]) for j in run], [(R[j][0], base_top, R[j][1]) for j in run]],
                   [[(L[j] / 16.0, 1.0) for j in run], [(L[j] / 16.0, 0.0) for j in run]], facing=outward)
            m.grid("lv_frame", [[(R[j][0], base_top, R[j][1]) for j in run], [(R[j][0], tops[j], R[j][1]) for j in run]],
                   [[(L[j] / q["frame_u"], (tops[j] - base_top) / q["frame_u"]) for j in run], [(L[j] / q["frame_u"], 0.0) for j in run]],
                   facing=outward)
        # the name over the glass, right of its middle as the lots see it (plain type; the club's own sign is the
        # Levi's mark, never drawn), and the tall club banner on the north wing
        sg = self.meshes.setdefault("lv_signs", Mesh("lv_signs"))
        sw, sh = 44.0, 11.0
        x = self.tower_back - 0.4
        y0 = self.tower_top - sh - 3.0
        zc = q["curtain_z"] + q["curtain_w"] * 0.18
        sg.quad("lv_letters", (x, y0, zc - sw / 2), (x, y0, zc + sw / 2), (x, y0 + sh, zc + sw / 2), (x, y0 + sh, zc - sw / 2),
                (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([-1.0, 0.0, 0.0]))
        bw, bh, bz = 16.0, 30.0, q["banner_z"]
        by = GRADE + 8.0
        sg.quad("lv_banner", (x, by, bz - bw / 2), (x, by, bz + bw / 2), (x, by + bh, bz + bw / 2), (x, by + bh, bz - bw / 2),
                (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([-1.0, 0.0, 0.0]))

    # -- outside -----------------------------------------------------------------------------------------------------
    def _exterior(self):
        fp = footprint()
        ring, _pos = self.facade_ring(72)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("lv_plaza", Mesh("lv_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= math.np_norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(10.0), grow(30.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("lv_plaza", rings, [uv(r) for r in rings], facing=up)
        # beyond the plaza, the shared environment kit (st3, 2026-09-28): the lots with their cars, the roads, the creek,
        # grass, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band (the Diablo Range
        # and the Santa Cruz Mountains at their true elevation angles, which _hills drew by hand before)
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        self.env_counts = env.dress(self, VENUE, grade=GRADE, keep_out=[plaza], inner=plaza,
                                    eyes=env.shot_eyes(levis_shots()))

    def _hills(self):
        """The Diablo Range's foothills on the eastern horizon and the lower Santa Cruz Mountains far to the south-west
        (every photo from the lots and Great America), a band of ridges beyond the retail cityscape's reach (4.4 km)."""
        q = self.p["hills"]
        m = self.meshes.setdefault("lv_hills", Mesh("lv_hills"))
        N = q["points"]
        ridge = np.random.default_rng(25)
        bot, top, uvb, uvt = [], [], [], []
        for k in range(N + 1):
            a = 2 * math.pi * (k % N) / N                 # game angle (atan2(z, x)); bearing = angle + 61.85 degrees
            bearing = (math.degrees(a) + 61.85) % 360.0
            # east (bearings 40 to 160): the Diablo Range, 250 to 420 m; south-west (190 to 290): the Santa Cruz
            # Mountains, lower in the haze; north (the bay): flat
            def bump(c, w):
                return math.exp(-math.pow(((bearing - c + 180) % 360 - 180) / w, 2))
            h = 330.0 * bump(95.0, 55.0) + 150.0 * bump(240.0, 45.0) + 12.0
            h *= 0.85 + 0.3 * float(ridge.random())
            x, z = q["radius"] * math.cos(a), q["radius"] * math.sin(a)
            bot.append((x, GRADE - 2.0, z))
            top.append((x * 1.02, GRADE + h, z * 1.02))
            uvb.append((k / 4.0, 1.0))
            uvt.append((k / 4.0, 0.0))
        m.grid("lv_hills", [bot, top], [uvb, uvt], facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))


def build(venue=VENUE, params=None):
    return Levis(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "lv_seat_front": ("lv_seat_front", CLASS_OPAQUE), "lv_seat_mid": ("lv_seat_mid", CLASS_OPAQUE),
    "lv_seat_back": ("lv_seat_back", CLASS_OPAQUE), "lv_concrete": ("lv_concrete", CLASS_OPAQUE),
    "lv_wall": ("lv_wall", CLASS_OPAQUE), "LIGHT_lv_ribbon": ("LIGHT_lv_ribbon", CLASS_OPAQUE),
    "LIGHT_lv_glass": ("LIGHT_lv_glass", CLASS_OPAQUE), "LIGHT_lv_concourse": ("LIGHT_lv_concourse", CLASS_OPAQUE),
    "lv_portal": ("lv_portal", CLASS_OPAQUE), "lv_dark": ("lv_dark", CLASS_OPAQUE), "lv_black": ("lv_black", CLASS_OPAQUE),
    "LIGHT_lv_suites": ("LIGHT_lv_suites", CLASS_OPAQUE), "LIGHT_lv_press": ("LIGHT_lv_press", CLASS_OPAQUE),
    "lv_balcony": ("lv_balcony", CLASS_ALPHA), "lv_white": ("lv_white", CLASS_OPAQUE),
    "lv_solar": ("lv_solar", CLASS_OPAQUE), "lv_green": ("lv_green", CLASS_OPAQUE),
    "lv_roof_under": ("lv_roof_under", CLASS_OPAQUE), "lv_truss": ("lv_truss", CLASS_ALPHA),
    "lv_frame": ("lv_frame", CLASS_ALPHA), "lv_steel": ("lv_steel", CLASS_OPAQUE),
    "LIGHT_lv_lights": ("LIGHT_lv_lights", CLASS_OPAQUE), "LIGHT_lv_board_panel": ("LIGHT_lv_board_panel", CLASS_OPAQUE),
    "lv_letters": ("lv_letters", CLASS_ALPHA), "lv_facade": ("lv_facade", CLASS_OPAQUE),
    "LIGHT_lv_curtain": ("LIGHT_lv_curtain", CLASS_OPAQUE), "lv_banner": ("lv_banner", CLASS_OPAQUE),
    "LIGHT_lv_base": ("LIGHT_lv_base", CLASS_OPAQUE),
    "lv_plaza": ("lv_plaza", CLASS_OPAQUE), "lv_ground": ("lv_ground", CLASS_OPAQUE),
    "lv_asphalt": ("lv_asphalt", CLASS_OPAQUE), "lv_road": ("lv_road", CLASS_OPAQUE),
    "lv_building": ("lv_building", CLASS_OPAQUE), "lv_water": ("lv_water", CLASS_OPAQUE),
    "lv_hills": ("lv_hills", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "lv_seat_front": (214, 196, 188), "lv_seat_mid": (214, 196, 188), "lv_seat_back": (214, 196, 188),
    "crowd": (224, 204, 206), "lv_concrete": (206, 188, 176), "lv_wall": (230, 212, 214),
    "LIGHT_lv_ribbon": (255, 255, 255), "LIGHT_lv_glass": (190, 176, 255), "LIGHT_lv_concourse": (214, 196, 255),
    "lv_portal": (160, 150, 120), "lv_dark": (190, 176, 150), "lv_black": (200, 190, 170),
    "LIGHT_lv_suites": (200, 186, 255), "LIGHT_lv_press": (210, 196, 240), "lv_balcony": (230, 214, 200),
    "lv_white": (226, 208, 184), "lv_solar": (214, 196, 110), "lv_green": (214, 196, 100),
    "lv_roof_under": (200, 182, 170), "lv_truss": (236, 220, 200), "lv_frame": (230, 212, 150),
    "lv_steel": (214, 196, 150), "LIGHT_lv_lights": (255, 255, 255), "LIGHT_lv_board_panel": (255, 255, 255),
    "jumbo_tron": (255, 255, 255), "lv_letters": (255, 255, 255), "lv_facade": (218, 200, 120),
    "LIGHT_lv_curtain": (214, 196, 255), "lv_banner": (226, 208, 150),
    "LIGHT_lv_base": (206, 190, 255), "lv_plaza": (226, 206, 120), "lv_ground": (222, 200, 70),
    "lv_asphalt": (220, 200, 90), "lv_road": (220, 200, 90), "lv_building": (220, 200, 100),
    "lv_water": (210, 190, 70), "lv_hills": (236, 214, 40),
}
#: the sun at Santa Clara (DESIGN): by day high in the south (-x, +z in this frame), in the afternoon low in the
#: west-south-west, behind the suite tower
SUN = {"d": (-0.23, 0.87, 0.44), "a": (-0.85, 0.50, 0.05), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.93, 0.85), "n": (0.97, 0.99, 1.03)}
#: open air: rain and snow bundles grey everything under the cloud (the field and the bowl included)
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"lv_facade", "lv_banner", "lv_frame", "lv_solar", "lv_green", "lv_plaza", "lv_ground", "lv_asphalt", "lv_road",
           "lv_building", "lv_water", "lv_hills", "lv_steel"}


def light(mat, P, N, tod, weather, outside=False, occlusion=None):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
    base = BASE.get(mat, (200, 190, 150))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif tod == "n":
        f = np.full(n, 1.0)
    else:
        sun = np.array(SUN[tod])
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.76 + 0.26 * nd) if tod == "d" else (0.64 + 0.45 * nd)
    if occlusion is not None and not (mat.startswith("LIGHT_") and tod == "n"):
        f = f * occlusion
    if mat == "lv_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.55, f)
    tint = TINT[tod]
    if weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat == "lv_facade" and tod == "n":
        # the tower's precast face at night: lit from the lots below, fading up (DESIGN)
        k = np.clip((P[:, 1] - GRADE) / 50.0, 0, 1)
        out[:, 0] = np.clip(120 - 70 * k, 0, 255); out[:, 1] = np.clip(118 - 70 * k, 0, 255); out[:, 2] = np.clip(126 - 70 * k, 0, 255)
    if mat == "lv_hills" and tod == "n":
        out[:, 0] = 16; out[:, 1] = 18; out[:, 2] = 26
    return out


def _rgba(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def _textures(venue, tod, weather):
    art = ART_DIR
    keys = list(dict.fromkeys(k for k, _c in MATERIALS.values() if not k.startswith("env_")))   # deterministic order
    out = {key: _rgba(art / f"{key}.png") for key in keys}
    out.update(env.textures(venue, tod, weather))
    return out


#: the game's digits on the boards' stat panels (slot spacing, half width, half height, metres) and their height on the
#: panel (a fraction of the board's height)
DIGIT_SLOT, DIGIT_HW, DIGIT_HH, DIGIT_Y = 0.9, 0.40, 0.70, 0.66


def adjust_digits(shape, sc, model):
    """The score and clock digits onto each board's left stat panel (the game's own digits: two strips, one per board,
    in the panel's dark window); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    strips = []
    for b in model.board_frames:
        pc = b["panels"][0] + b["face"] * 0.12 + np.array([0.0, b["height"] * DIGIT_Y, 0.0])
        strips.append(dict(centre=pc, right=b["right"]))
    counters = {}
    for sm_ in shape.submeshes:
        mname = sc.materials[sm_.material].name
        idx = sorted({i for _m, ix in sb.decode_words(sm_.words) for i in ix})
        quads = [idx[k:k + 4] for k in range(0, len(idx) - 3, 4)]
        for quad in quads:
            n = counters.get(mname, 0)
            counters[mname] = n + 1
            if mname.startswith("digit_playclock"):
                zs = 1 if n % 2 == 0 else -1
                side = -1 if mname.endswith("_L") else 1
                wall_z = model.p["loop"]["zs"] if zs > 0 else model.p["loop"]["zn"]
                centre = np.array([side * 0.9 * zs, 2.7, zs * (wall_z - 0.08)])
                sm._place_quad(P, UV, quad, centre, np.array([-zs, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 0.75, 1.1)
            else:
                s_ = strips[n % 2]
                slot = sm.DIGIT_SLOTS.get(mname, 5)
                centre = s_["centre"] + s_["right"] * ((slot - 5) * DIGIT_SLOT)
                sm._place_quad(P, UV, quad, centre, s_["right"], np.array([0.0, 1.0, 0.0]), DIGIT_HW, DIGIT_HH)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def flare_points(model):
    """The four flare markers: over the light trusses at their 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT
    (300 m) up (u6's lab 5, PROVED IN GAME at SoFi: no flare discs in the flyover, short night shadows under the feet).
    Out of every Levi's shot too (test: Cameras)."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], sm.FLARE_HEIGHT, best[2]))
    return out


#: the field-level sponsor cloths: job u4's reviewed 2026 league sheet (``nfl2k5_modern_venues_2026.LEAGUE_ART``) over the
#: retail texture, carried to each bundle's weather from the dry bundle as u4 carries it (Highmark's method: the 2026
#: venue art cedes the venue to this model, so without it the kept banners would show the 2004 cloths).
LEAGUE_BANNER = "banner_corp"


def dry_of(name):
    """The dry bundle of the same time of day (s25nr.iff -> s25nd.iff)."""
    return name[:4] + "d.iff"


def league_banner(retail_bundle, filename, dry_bundle=None):
    """(retail texture index, RGBA) of the stadium scene's banner_corp with the 2026 league cloths, or None when the
    scene or the build lacks it. ``dry_bundle`` is the dry bundle of the same time of day (rain and snow need it)."""
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_modern_metlife as mmod
    entry = next((e for e in mv.LEAGUE_ART if e["key"] == LEAGUE_BANNER), None)
    path = mv.DATA_DIR / entry["art"] if entry else None
    if path is None or not path.is_file():
        return None
    weather = filename[4]
    if weather != "d" and dry_bundle is None:
        return None
    ml = sm._ml()

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
        art = sm._resample(art, w, h)
    out = current.copy()
    sx, sy = w / art.shape[1], h / art.shape[0]
    for x0, y0, x1, y1 in entry["rects"]:
        x0, x1, y0, y1 = int(round(x0 * sx)), int(round(x1 * sx)), int(round(y0 * sy)), int(round(y1 * sy))
        piece, _fits = mmod.weather_transfer(base, current, art, region=(y0, y1, x0, x1), snow=weather == "s")
        out[y0:y1, x0:x1] = piece[y0:y1, x0:x1]
    return index, out


def build_scene(retail_bundle, filename, model, dry_bundle=None):
    """The Levi's stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "lv_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "lv_digits", tmpl_shape)
    sc.shapes = [s for s in sc.shapes if s.name.startswith(KEEP_PREFIXES)]
    names = {s.name for s in sc.shapes}
    sc.nodes = [n for n in sc.nodes if n.shape_name in names]
    for shp in (yard, digits):
        if shp is not None:
            sc.shapes.append(shp)
            sc.nodes.append(sb.node_for(tmpl_node, shp.name, shp.name))
    tex = _textures(venue, tod, weather)
    tex_index = {}
    for key, rgba in tex.items():
        sc.textures.append(sb.p8_texture(tex_tmpl, rgba))
        tex_index[key] = len(sc.textures) - 1
    for name, (key, cls) in MATERIALS.items():
        tmpl = sm._template_material(sc, cls)
        sc.materials.append(sb.Material(bytearray(tmpl.record), name, tex_index[key], None))
    mat_ix = {m.name: i for i, m in enumerate(sc.materials)}
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
            C[idxs] = light(mat, P[idxs] / 100.0, N[idxs], tod, weather, outside=mat in OUTSIDE)
            subs.append((mat_ix[mat], sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(strips))))
        shape = sb.static_shape(tmpl_shape, mesh.name, [tuple(p) for p in P], [tuple(x) for x in C],
                                [tuple(u) for u in UV], subs)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, mesh.name, mesh.name))
    for s in sc.shapes:
        if s.name.startswith("banners_"):
            sm.adjust_banners(s, model)
    if digits is not None:
        adjust_digits(digits, sc, model)
    lights = model.light_points
    glows = [m for m in sc.markers if m.name.startswith("marker_light")]
    for i, m in enumerate(glows):
        p = lights[int(round(i * len(lights) / max(1, len(glows)))) % len(lights)]
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
        # 0x7F210 registers a light glow at every marker whose name holds "light"; u6 and st (labs at SoFi and
        # Highmark, PROVED IN GAME) keep the records and positions but not the word
        m.name = m.name.replace("marker_light", "marker_lamp")
    flares = [m for m in sc.markers if "flare" in m.name]
    for m, p in zip(flares, flare_points(model)):
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
    for m, p in zip([m for m in sc.markers if m.name.startswith("jumboMarker")], model.markers["jumbo"]):
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
    for m in sc.markers:
        if m.name.startswith("nosebleed"):
            struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in model.nosebleed))
    used = {sm_.material for s in sc.shapes for sm_ in s.submeshes}
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
    for i in sorted({m.texture for m in sc.materials if m.name.startswith("digit_") and m.texture is not None}):
        sc.textures[i] = sb.p8_texture(sc.textures[i], sm.led_segment())
    for s in sc.shapes:
        for sm_ in s.submeshes:
            struct.pack_into("<H", sm_.record, 0, remap_m[sm_.material])
    return sc


def model_bundle(retail_bundle, filename, model=None, *, cameras=None, dry_bundle=None):
    """(bundle bytes, info): the retail bundle with its cityscape collapsed (the surroundings live in the stadium scene),
    its stadium scene replaced by the Levi's model and its intro cameras rewritten when ``cameras`` gives the shots.
    The stretch from the cityscape to the end of the cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    cam_chunk, cam_dec = mm._cameras_chunk(retail_bundle)
    sb.require(cam_chunk.offset == st.offset + 32 + st.stored_size, "intro cameras do not follow the stadium chunk")
    city = scenes["cityscape"]
    sb.require(city.offset + 32 + city.stored_size == st.offset, "the cityscape does not precede the stadium chunk")
    csc, _c = sm.cityscape_scene(retail_bundle)
    cdec, csys, cvid = sb.serialize(csc)
    cspan = sm._chunk_span(retail_bundle, city)
    c_out, city_info = sb.compressed_chunk("SCNE", cdec, csys, cvid, stream_tag=struct.unpack_from("<I", cspan, 36)[0],
                                           offset_bits=cspan[40])
    start = city.offset
    end = cam_chunk.offset + 32 + cam_chunk.stored_size
    cam_span = sm._chunk_span(retail_bundle, cam_chunk)
    if cameras is not None:
        new_cam = sm.write_cameras(cam_dec, cameras)
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
    room = end - start - len(c_out) - len(cam_out) - 32
    room -= room % 16
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, sm._chunk_span(retail_bundle, st), stored=room)
    stretch = c_out + chunk + cam_out
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
                     retail_system=st.system_bytes, retail_video=st.video_bytes,
                     vertices=sum(s.vertex_count for s in sc.shapes))


# ------------------------------------------------------------------------------------------------ the field

#: The field (natural grass: Bermuda and rye, Wikipedia; OSM: West Coast Turf's Ready Play Grass): the retail s25 field is
#: grass already, one flat colour quad between the goal lines. The model paints it mown in 5-yard bands (u runs along
#: the field once the quad's UVs are remapped, in place), the grass outside the field of play, and the 49ers' 2026 end
#: zones and midfield from the league project's art (the u4 SF venue folder), composited over clean grass. Unlike s03,
#: the retail s25 field gives each end its own three textures (endzone_N_* at -z, the north end here, endzone_S_* at +z;
#: PROVED OFFLINE from the nine retail fields), so each end's art goes straight onto its own panels.
FIELD_ART = ART_DIR / "field"
GRASS_MATERIAL, OUTSIDE_MATERIAL = "color_premipped", "grass_outside_premipped"
ENDZONE_TEXTURES = ("endzone_N_L", "endzone_N_M", "endzone_N_R", "endzone_S_L", "endzone_S_M", "endzone_S_R")
TEAM_FIELD = ENDZONE_TEXTURES + ("center_logo",)


def _weather_look(rgba, weather):
    """Rain darkens and cools the grass; snow lays a thin white cover (DESIGN; the retail snow fields whiten the same
    way)."""
    a = rgba.astype(np.float32)
    if weather == "r":
        a[..., :3] = a[..., :3] * np.array([0.84, 0.88, 0.94])
    elif weather == "s":
        a[..., :3] = a[..., :3] * 0.55 + np.array([214.0, 220.0, 226.0]) * 0.45
    return np.clip(a, 0, 255).astype(np.uint8)


def remap_grass_uv(out, rec):
    """The grass quad between the goal lines: u from 0 at the -z goal line to 1 at the +z one (retail: 0.5 to 1), in
    place, inside the shape's own UV constant; returns the vertices changed."""
    g = sm._field_shape(rec, "A_grass_color")
    st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
    su, sv, ou, ov = struct.unpack_from("<4f", out, g["record_offset"] + 0x30)
    changed = 0
    for i in sm._submesh_vertices(rec, out, g, GRASS_MATERIAL):
        _x, _y, z = struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i)
        u = min(1.0, max(0.0, (45.72 - z / 100.0) / 91.44))
        q = int(round((u - ou) / su * 32767.0))
        sb.require(-32767 <= q <= 32767, "the grass UV constant cannot hold the remap")
        struct.pack_into("<h", out, st1["offset"] + st1["stride"] * i + 4, q)
        changed += 1
    return changed


def team_field_art(art_root):
    """{material: RGBA} of the 49ers' field art in a league art root (``<root>/<team dir>/venue`` for prefix s25), or
    {} when the root has none."""
    if not art_root:
        return {}
    from . import nfl2k5_modern_venues_2026 as mv
    art = mv.load_art(art_root)
    venue = art["venues"].get(VENUE)
    if venue is None:
        return {}
    return {item["key"]: np.asarray(item["rgba"]) for item in venue["items"]
            if item.get("scene") == "field" and item.get("key") in TEAM_FIELD}


def paint_field(decoded, rec, system, weather, *, team=None, cap=256, half=False):
    """The Levi's field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "lv_grass.png")
    outside = _rgba(FIELD_ART / "lv_grass_outside.png")
    for mat, art in ((GRASS_MATERIAL, grass), (OUTSIDE_MATERIAL, outside)):
        row = rows[mat]
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, _weather_look(a, weather), maximum=cap)
    clean = np.array(np.median(grass.reshape(-1, 4), axis=0), np.float32)

    def over_grass(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    team = dict(team or {})
    if team and not any(k.startswith("endzone_S_") for k in team):
        # a root with one end's art only: the same art at both ends
        team.update({k.replace("_N_", "_S_"): v for k, v in list(team.items()) if k.startswith("endzone_N_")})
    detail = sm._half_detail if half else (lambda a: a)
    for mat, art in team.items():
        row = rows.get(mat)
        if row is None:
            continue
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        if mat in ENDZONE_TEXTURES:
            a = _weather_look(over_grass(a), weather)
        ml.write_p8(out, system, row, detail(a), maximum=cap)
    remap_grass_uv(out, rec)
    return bytes(out)


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s25 intro camera's channel carries (PROVED OFFLINE from the nine retail intro_cameras
#: scenes, identical in all nine): camera 1 moves x, z, pitch and yaw (y constant); camera 2 has no x (it plays on
#: x = 0) and moves y, pitch and yaw; camera 3 has no pitch (it plays level) and moves x, z and yaw; camera 4 only pans
#: (yaw); camera 5 moves x, y, pitch and yaw (z constant). A component a channel lacks plays as 0 (u6, labs 2 and 3).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"},
                             {"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the Levi's flyover, one shot per retail camera.
#: 1: the approach from the west lots toward the suite tower's face and the LEVI'S STADIUM name, gliding in;
#: 2 (on x = 0): a crane rising from behind the south end zone, looking up the field at the north board;
#: 3 (level): a slow pass along the east upper deck's rim level, looking west across the bowl at the suite tower;
#: 4 (a pan from a still eye): over the south-west corner, turning across the bowl and the east stands;
#: 5 (z constant): field level in the north end zone, turning and rising toward the south board.
_APPROACH = dict(eye=(-330.0, 70.0, 140.0), target=(-100.0, 34.0, 0.0), fov=36.0, rates=dict(x=9.0, z=-3.0, yaw=0.6))
_CRANE = dict(eye=(0.0, 8.0, 62.0), target=(0.0, 40.0, -110.0), fov=44.0, rates=dict(y=2.2, pitch=0.9))
_RIM = dict(eye=(78.0, 42.0, -40.0), target=(-80.0, 30.0, 10.0), fov=42.0, rates=dict(z=5.0, yaw=-1.0))
_PAN = dict(eye=(-70.0, 95.0, 160.0), target=(10.0, 20.0, 0.0), fov=42.0, rates=dict(yaw=2.6))
_FIELD_NORTH = dict(eye=(8.0, 3.0, -52.0), target=(0.0, 30.0, 140.0), fov=44.0, rates=dict(yaw=-2.5, y=0.6))
LV_SHOTS = [_APPROACH, _CRANE, _RIM, _PAN, _FIELD_NORTH]


def levis_shots():
    out = []
    for s, present in zip(LV_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=levis_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s25 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s25 bundles, each checked against its pinned SHA-256."""
    ml = sm._ml()
    out = {}
    with ml._outer_image()(str(source)) as archive:
        for name, pin in _venue_pins().items():
            e = _entry(archive, pin)
            data = archive.read(e.virtual_offset, e.size)
            sb.require(sha(data) == pin["retail_sha256"], f"{name}: the source bundle is not retail")
            out[name] = data
    return out


def stretch(bundle):
    """(start, end) of the Levi's stretch: from the cityscape chunk to the end of the intro cameras."""
    ml = sm._ml()
    scenes = ml.bundle_scenes(bundle)
    cam, _dec = mm._cameras_chunk(bundle)
    return scenes["cityscape"].offset, cam.offset + 32 + cam.stored_size


def build_all(source, *, workers=None, progress=None, names=None):
    """{name: (retail bundle, model bundle, info)} for the nine bundles (or ``names``), compiled in parallel."""
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers, progress=progress, label="Levi's Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field span

#: the field's fitting ladder (u6's): the marks at full detail down to 64 colours, then at half detail from 256 colours
#: down, then full detail at the fewest colours
FIELD_LADDER = ([(False, c) for c in (256, 128, 96, 64)] + [(True, c) for c in (256, 128, 96, 64, 48, 32)]
                + [(False, c) for c in (48, 32)])
#: the first pass tries only rungs estimated under 0.93 of the span (st's Highmark measurements: the VC-LZ streams run
#: 6 to 10 percent over u6's estimate)
FIELD_SKIP_FIRST = 0.93


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle: the Levi's field, graded by Modern colour when its
    settings are given (painted before the grade and compressed once, as SoFi, MetLife and the 2026 venue art do),
    stepping the written textures down a palette ladder when the span misses."""
    ml = sm._ml()
    tx = ml._tools()[0]
    chunk = ml.bundle_scenes(bundle)["field"]
    span = ml.scene_span(bundle, chunk)
    weather = name[4]
    attempts = []
    base_rec, base_dec = ml._scene(bundle, chunk)
    import zlib
    estimates = {}
    for half, cap in FIELD_LADDER:
        if half and not team:
            continue                    # half detail only redraws the team marks
        painted = paint_field(base_dec, base_rec, chunk.system_bytes, weather, team=team, cap=cap, half=half)
        estimates[(half, cap)] = int(len(zlib.compress(painted, 9)) * sm.FIELD_ZLIB_RATIO)
    order = [(r, FIELD_SKIP_FIRST) for r in estimates] + [(r, sm.FIELD_SKIP_OVER) for r in estimates]
    tried = set()
    for (half, cap), margin in order:
        rung = f"{cap} colours{' (half detail)' if half else ''}"
        if (half, cap) in tried:
            continue
        estimate = estimates[(half, cap)]
        if estimate > chunk.stored_size * margin:
            if margin == sm.FIELD_SKIP_OVER:
                attempts.append(f"{rung}: skipped, estimated {estimate} bytes")
            continue
        tried.add((half, cap))
        try:
            if colour_settings is not None:
                from . import nfl2k5_modern_color as colour

                def painter(sp, ch, cap=cap, half=half):
                    rec, dec = ml._scene(sp, ch)
                    return paint_field(dec, rec, ch.system_bytes, weather, team=team, cap=cap, half=half), {}
                after, detail = colour.modern_field_scene(span, outer_index=outer_index, settings=colour_settings,
                                                          painter=painter)
            else:
                rec, dec = ml._scene(bundle, chunk)
                after, detail = ml.fit_span(span, paint_field(dec, rec, chunk.system_bytes, weather, team=team, cap=cap,
                                                              half=half))
            sb.require(len(after) == len(span), f"{name}: the field escaped its span")
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               team_art=sorted(team or {}),
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{rung}: {exc}")
    raise sb.ScneBuildError(f"{name}: the Levi's field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_levis_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_levis_receipt/v1"
BUILD_CAPTION = "Levi's Stadium for the 49ers (experimental)"
HELP_TEXT = (
    "The San Francisco 49ers' Levi's Stadium, built as a new model for 49ers home games in every time of day and "
    "weather: the red bowl with the suite tower along the west sideline (club, suites, press level, the solar roof and "
    "its light truss), the steep east upper deck with its lights, the two end-zone 4K video boards with the live feed "
    "and the LEVI'S STADIUM signs, the precast west face and the open steel frame round the other sides, the lots, "
    "Tasman Drive and the hills, and a new pregame flyover with exterior passes. The field is natural grass mown in "
    "5-yard bands with the 2026 venue art's 49ers end zones and midfield when that option is on. The row reads Levi's "
    "Stadium, Santa Clara, CA; the field stays open to rain. The 2026 venue art leaves the 49ers' packages to it. Off "
    "in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Levi's Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Levi's Stadium pins schema")
    return _PINS


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compile the nine stretches from a retail source and pin them (the field depends on the art root
    and the Modern colour settings, so the receipt records it instead)."""
    built = build_all(source, progress=progress)
    bundles = []
    for name in VARIANTS:
        retail, model, info = built[name]
        start, end = stretch(retail)
        bundles.append(dict(name=name, size=len(retail), offset=start, length=end - start,
                            retail_sha256=sha(retail[start:end]), model_sha256=sha(model[start:end]),
                            system=info["system"], video=info["video"], scratch=info["scratch"], shapes=info["shapes"],
                            vertices=info["vertices"]))
    doc = dict(schema=PINS_SCHEMA, label=LABEL, bundles=bundles, source_note="compiled from the retail archive")
    Path(out_path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return doc


def _pin(name):
    return next(p for p in model_pins()["bundles"] if p["name"] == name)


def bundle_state(archive, name, *, fan_receipt=None):
    """retail / applied / foreign for the Levi's stretch of one of the nine bundles."""
    pin = _pin(name)
    e = _entry(archive, _venue_pins()[name])
    if e.size != pin["size"]:
        return "foreign"
    have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
    from . import nfl2k5_model_fan_art as fans
    if fans.applied(have, pin, fan_receipt):
        return "applied"
    if have == pin["model_sha256"]:
        return "applied"
    return "retail" if have == pin["retail_sha256"] else "foreign"


def receipt_path(source):
    return Path(str(source) + ".levis.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Levi's Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s25 row."""
    from . import nfl2k5_levis_venue as lvv
    ml = sm._ml()
    states = set()
    from . import nfl2k5_model_fan_art as fans
    fan_rows = fans.receipt_rows(source, read_receipt(source))
    with ml._outer_image()(str(source)) as archive:
        for name in VARIANTS:
            try:
                states.add(bundle_state(archive, name, fan_receipt=fan_rows.get(name, {}).get("fan_art")))
            except (sb.ScneBuildError, ValueError):
                return "foreign"
        entry = archive.entries[lvv.ROST_OUTER_INDEX]
        row = lvv.rost_state(archive.read(entry.virtual_offset, entry.size))
    if "foreign" in states or row == "foreign":
        return "foreign"
    if states == {"applied"} and row == "applied":
        return "applied"
    if states == {"retail"} and row == "retail":
        return "retail"
    return "mixed"


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    sb.require(state == ("applied" if enabled else "retail"), f"Levi's Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Levi's)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the 49ers stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=levis_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s25 to it): the Levi's field, stadium, cameras
    and collapsed cityscape of the nine bundles, and the s25 row. The retail bundles come from ``retail_source``; the
    image's own bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the
    field is composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour
    still recognizes its bytes. ``art_root`` is the 2026 venue art folder: its 49ers end zones and midfield go onto the
    new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_levis_venue as lvv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Levi's Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Levi's Stadium needs retail 49ers packages (found {state})")
    try:
        colour_receipt = colour.read_image_receipt(target)
    except (OSError, ValueError):
        colour_receipt = None
    settings = colour_receipt.get("settings") if colour_receipt else None
    colour_before = sm._colour_states(target, colour_receipt) if colour_receipt else None
    retail = read_retail(retail_source)
    pins = _venue_pins()
    team = team_field_art(art_root) if art_root else {}
    current = {}
    with ml._outer_image()(str(target)) as archive:
        for name in VARIANTS:
            e = _entry(archive, pins[name])
            data = archive.read(e.virtual_offset, e.size)
            chunk = ml.bundle_scenes(retail[name])["field"]
            have = sha(data[chunk.offset:chunk.offset + 32 + chunk.stored_size])
            graded = ((colour_receipt or {}).get("bundle_pins", {}).get(name, {}).get("sites") or [])
            ok = have == sha(ml.scene_span(retail[name], chunk)) or any(
                s_.get("kind") == "field" and s_.get("applied") == have for s_ in graded)
            sb.require(ok, f"{name}: the field is neither retail nor Modern colour's; another option wrote it")
            current[name] = data
    jobs = [(n, retail[n], current[n], settings, pins[n]["outer"], team or None, retail[dry_of(n)]) for n in VARIANTS]
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False, colour=settings is not None, bundles={},
                   team_art=sorted(team), art_root=str(art_root) if art_root else None)
    new_colour = deepcopy(colour_receipt) if colour_receipt else None
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Levi's Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Levi's bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], applied_sha256=sha(after),
                                            field=info.get("field"), system=info["system"], video=info["video"],
                                            fan_art=info.get("fan_art"))
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        receipt["rost"] = lvv.apply_rost(archive)
    if new_colour is not None:
        new_colour["levis"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Levi's Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Levi's Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Levi's Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_levis_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Levi's stretches, fields and row into a built disc")
    a.add_argument("disc"); a.add_argument("--source", required=True); a.add_argument("--art-root", default=None)
    st_ = sub.add_parser("status"); st_.add_argument("source")
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
    if args.command == "build-dir":
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        team = team_field_art(args.art_root) if args.art_root else None
        info = {}
        for name in args.names or VARIANTS:
            data = (Path(args.retail_dir) / name).read_bytes()
            _n, model, i = _compile((name, data, (Path(args.retail_dir) / dry_of(name)).read_bytes()))
            field, finfo = field_span(data, name, team=team)
            chunk = sm._ml().bundle_scenes(data)["field"]
            model = model[:chunk.offset] + field + model[chunk.offset + len(field):]
            (out / name).write_bytes(model)
            info[name] = dict({k: v for k, v in i.items() if k != "cityscape"}, field=finfo)
            print(name, "decoded", i["system"] + i["video"], "retail", i["retail_system"] + i["retail_video"],
                  "stored", i["stored"], "vertices", i["vertices"], "field cap", finfo["palette_cap"], flush=True)
        (out / "build.json").write_text(json.dumps(info, indent=1, default=str) + "\n", newline="\n")
        return 0
    receipt = apply_lab_disc(args.disc, args.source, art_root=args.art_root, progress=say)
    Path(str(args.disc) + ".st2-levis.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST2_LEVIS_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
