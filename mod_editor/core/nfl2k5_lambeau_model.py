"""Lambeau Field model (experimental): the Green Bay Packers' Lambeau Field (Green Bay, opened 1957; the 2001 to 2003
renovation, the 2012 to 2013 south end zone expansion, the 2023 end zone boards, the 2018 LED lights) built as the
stadium scene of venue record s10 (the retail 2004 Lambeau Field), all nine bundles (day, afternoon, night; dry, rain,
snow).

Job st2 (2026-09-28, tier 1 of the renovations plan), on u5's builder, u6's SoFi methods and st's models (the Gillette
model's layout, the Hard Rock model's per-end field). References (Wikipedia; packers.com, 2012-05-15; FOX 11, 2023-04-03;
Sports Video Group, 2023-10-18; OpenStreetMap; the retail s10 scene; the Commons photos 2015 to 2025; the Esri
orthophoto, reference only) are cited in the st2 report. The scene:

* the bowl as the photos show it: one continuous bowl of bleachers from the field wall (46 rows on the sidelines, 56 at
  the north end, 40 at the south end); the suites and press levels over the sideline bowls behind their glass; crowd
  billboards in the retail convention, cut at every aisle (u6's method); the ribbons on the fascias;
* the south end zone expansion (2012 to 2013: 7,500 seats): the upper south stands over the bowl's south end, their
  one indoor row behind glass;
* the two end zone boards (2023, SOURCED: 220 x 48 ft each, behind each end zone) on the ``jumbo_tron`` material the
  game draws its live feed into (a crop of the feed at the picture's own aspect, never stretched, at the loop gain of
  about 1) between their stat panels, the game's digits on the south board's; their great green backs with the name as
  plain type over the north and south gates; the north end's rooftop terrace (2012) under the north board;
* the LED lights (2018) on their masts over the sideline roofs; the brick and green building with the north and south
  tower gates (2013), the atrium's block on the east side;
* outside the plaza, the shared environment kit (nfl2k5_stadium_environment, st3): the lots with their cars, the
  roads, parks, water, trees and blocks (Titletown and the Resch Center among them) from OpenStreetMap, the far ground
  to the haze and the horizon band;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the south board's stat panels), the markers and the
  materials the executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x the east sideline toward bearing 89.8 degrees, the visitors', and -x the west
sideline, the Packers' (SOURCED: the Packers' bench is on the west side), where every retail stadium keeps the home
sideline props; y up from the field; z along, +z the south end zone toward bearing 179.8 degrees: OpenStreetMap's pitch)
and centimetres in the game. The row keeps its open-air word and its grass word (retail) and takes today's capacity.
EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import json
import math
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

OWNER = "nfl2k5_lambeau_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_lambeau_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s10"
VENUES = (VENUE,)
#: the plazas and the concourse gates sit above the field, which lies below the surrounding grade (DESIGN from the
#: the plazas round the bowl (DESIGN: the photos show the concourses a little over the field level)
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
    return dict(E=max(nx, 0.0) ** 2, W=max(-nx, 0.0) ** 2, S=max(nz, 0.0) ** 2, N=max(-nz, 0.0) ** 2)


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
        return 1.0 if v > 0.999 else float(np.clip((v - 0.55) / 0.4, 0, 1)) ** 2

    for x, z, nx, nz in segs + [segs[0]]:
        if prev is not None:
            s += math.dist(prev, (x, z))
        prev = (x, z)
        lp = LoopPoint(x, z, nx, nz, s, w(nx), w(nz))
        lp.w = side_weights(nx, nz)
        pts.append(lp)
    return pts


# ------------------------------------------------------------------------------------------------ parameters

#: DESIGN, pass 1. The side keys follow Allegiant's plan loop: E the +x side (here the east sideline), W the -x side (the
#: west, the Packers'), N the -z end (north), S the +z end (south). The field wall stands outside the retail s10
#: sideline props (x -38.4 to 38.5) and the banners' line (x +-38.9, z +-65.4, projected onto the wall), PROVED OFFLINE.
#: The bowl on the Esri orthophoto (reference only): the sideline bleachers to x about +-79, the north end's to z -115,
#: the south end's lower bowl to about z 101 under the 2013 upper stands; the heights from the retail scene (its lower
#: bowl to 14.8 m, its second ring to 26.4 m) and the photos.
PARAMS = dict(
    loop=dict(xe=40.0, xw=40.0, zs=66.5, zn=66.5, R=16.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    sides=dict(
        W=dict(low_d0=1.0, low_y0=1.6, low_rows=46, low_tread=0.84, low_rise0=0.32, low_rise1=0.52,
               t2_over=2.0, t2_rows=0, t2_rise=0.55, band_h=12.0,
               up_d=40.0, up_y=30.0, up_rows=0, up_tread=0.84, up_rise=0.55, back_wall=2.4),
        E=dict(low_d0=1.0, low_y0=1.6, low_rows=46, low_tread=0.84, low_rise0=0.32, low_rise1=0.52,
               t2_over=2.0, t2_rows=0, t2_rise=0.55, band_h=12.0,
               up_d=40.0, up_y=30.0, up_rows=0, up_tread=0.84, up_rise=0.55, back_wall=2.4),
        N=dict(low_d0=1.0, low_y0=1.6, low_rows=56, low_tread=0.84, low_rise0=0.30, low_rise1=0.48,
               t2_over=2.0, t2_rows=0, t2_rise=0.55, band_h=0.0,
               up_d=50.0, up_y=26.0, up_rows=0, up_tread=0.84, up_rise=0.55, back_wall=2.4),
        S=dict(low_d0=1.0, low_y0=1.6, low_rows=40, low_tread=0.84, low_rise0=0.30, low_rise1=0.46,
               t2_over=2.0, t2_rows=8, t2_rise=0.58, band_h=3.5,
               up_d=40.0, up_y=27.0, up_rows=14, up_tread=0.84, up_rise=0.66, back_wall=2.0),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the two end zone boards (2023, SOURCED: FOX 11 2023-04-03 and Sports Video Group 2023-10-18, "48 ft. high by nearly
    #: 220 ft. wide", Daktronics, "behind each end zone"): 67.1 x 14.6 m each over the end stands, a feed over their middle
    #: between stat panels, a deep green housing behind with the name over the gates (the 2024 and 2025 exterior photos);
    #: their bottoms and places DESIGN on the orthophoto's shadows: the north board on the rooftop terrace's structure
    #: (2012), the south one over the 2013 upper stands
    boards=dict(w=67.1, h=14.6, north_bottom=36.0, north_z=-122.0, south_bottom=41.5, south_z=123.5, feed=0.72, depth=5.0,
                back_sign_w=48.0, back_sign_h=6.5),
    #: the north end's structure under its board: the rooftop viewing terrace (2012) from the stands' top walk out to the
    #: north gate's wall (DESIGN); the south end's under the south board
    north=dict(x=44.0, z0=-116.5, z1=-140.0, top=32.0),
    south=dict(x=44.0, z0=119.5, z1=130.0, top=37.5),
    #: the building: brick and green walls on the facade outline, the tower gates (2013) at the north and south ends with
    #: the clock and the name, and the atrium's block on the east side (the orthophoto; DESIGN heights)
    facade=dict(top=30.0, gate_w=16.0, gate_top=34.0, gate_depth=8.0, sign_w=22.0, sign_h=3.2,
                atrium=dict(x0=104.0, x1=148.0, z0=-70.0, z1=96.0, top=27.0)),
    #: the LED lights (2018) on masts over the sideline roofs (the 2016 photos: four banks a side on their masts)
    lights=dict(z=(-66.0, -22.0, 22.0, 66.0), w=13.0, h=5.0, y=54.0, x=96.0, mast_y0=38.0,
                south=((-58.0, 121.0), (58.0, 121.0)), south_y=48.0),
    #: the side scoreboards (SOURCED, FOX 11: 75 ft long by 7.5 ft tall, where the old ones stood) on the suites' fascias at
    #: midfield, facing the field (DESIGN height)
    side_boards=dict(w=22.9, h=2.3),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


def rounded_rect(hx, hz, r, n):
    """[(x, z)] counter-clockwise round a rectangle of half sides ``hx``, ``hz`` with corners of radius ``r``, ``n`` + 1
    points per corner (the straight sides run between them), the corners in the order +x+z, -x+z, -x-z, +x-z."""
    pts = []
    for sx, sz, a0 in ((1, 1, 0.0), (-1, 1, 90.0), (-1, -1, 180.0), (1, -1, 270.0)):
        cx, cz = sx * (hx - r), sz * (hz - r)
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return pts


# ------------------------------------------------------------------------------------------------ the model

class Lambeau(sm.SoFi):
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

    def lanai_zone(self, lp):
        return False

    def lanai_glass(self, lp):
        return False










    # -- Allegiant's generic methods (copied; Lambeau's own) ----------------------------------------------
    def board_hits(self, lp):
        """[(distance along the wall-line point's outward normal to a board's picture, that board)] for the boards the
        normal passes under: their seats must stay below them and the wall behind the top walk must stand behind them."""
        out = []
        for b in self.board_specs():
            (cx, cz), (ax, az) = b["c"], b["along"]
            den = lp.nx * (-az) - lp.nz * (-ax)
            if abs(den) < 1e-9:
                continue
            wx, wz = cx - lp.x, cz - lp.z
            t = (wx * (-az) - wz * (-ax)) / den
            u = (lp.nx * wz - lp.nz * wx) / den
            if t > 0 and abs(u) <= b["w"] / 2 + b["margin"]:
                out.append((t, b))
        return out

    def section(self, lp):
        p = self.p
        return self._stack(lambda key: _side_blend(lp, key, p), lp)

    def _stack(self, g, lp):
        p = self.p
        out = {}
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
        fh, gap = p["tier"]["fascia_h"], p["tier"]["gap"]
        d2 = lower[-1][0] - g("t2_over")
        y2 = lower[-1][1] + 1.1
        out["ribbon"] = (d2, y2, y2 + fh)
        out["lower_back"] = (lower[-1][0] + 0.6, lower[-1][1], y2 - 0.02)
        out["soffit2"] = (d2 + 0.02, lower[-1][0] + 0.6, y2)
        rows2 = int(round(g("t2_rows")))
        d, y = d2 + 0.4, y2 + fh + gap
        t2 = [(d, y)]
        for _i in range(rows2):
            d += p["tier"]["tread"]
            y += g("t2_rise")
            t2.append((d, y))
        out["t2"] = t2
        bh = g("band_h")
        yb = t2[-1][1] + 0.3
        db = t2[-1][0] + 1.0
        if bh > 0.2:
            out["band"] = (db, yb, yb + bh)
            out["band_floor"] = (t2[-1][0], db, t2[-1][1])
        prev = t2
        du = g("up_d")
        yu = max(g("up_y"), (yb + bh if bh > 0.2 else prev[-1][1]) + 2.5
                 - max(0.0, prev[-1][0] - du) * g("up_rise") / g("up_tread"))
        rowsu = int(round(g("up_rows")))
        hits = self.board_hits(lp) if lp is not None else []
        if lp is not None:
            room = self.facade_depth(lp) - 1.0 - p["rim"]["walk"] * 0.5 - 0.7 - (du + 0.4)
            rowsu = max(0, min(rowsu, int(room / g("up_tread"))))
            if self.lanai_zone(lp):
                rowsu = 0
            # under a board the seats stop a metre below it (the photos: the corner seats run up to the north boards'
            # bottoms, the south upper deck's front rows sit under the primary board)
            for _t, b in hits:
                rowsu = min(rowsu, max(0, int((b["bottom"] - 1.0 - (yu + fh + gap)) / g("up_rise"))))
        if rowsu < 2:
            # no upper deck (the lanai end): the club tier's back wall and a walk behind it, where the glass stands
            y = t2[-1][1]
            dback = t2[-1][0] + 0.3
            walk_end = dback + p["rim"]["walk"]
            if lp is not None:
                for t, b in hits:
                    walk_end = max(walk_end, t + b["depth"] + 0.5)
                walk_end = min(walk_end, self.facade_depth(lp) - 1.0)
            out["rim"] = (dback, y, y + g("back_wall"), max(dback + 0.3, walk_end))
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
            d += g("up_tread")
            y += g("up_rise")
            upd.append((d, y))
        out["upper"] = upd
        rim = p["rim"]
        walk_end = d + 0.3 + rim["walk"]
        if lp is not None:
            # the wall from the top walk up to the roof stands behind any board over these seats
            for t, b in hits:
                walk_end = max(walk_end, t + b["depth"] + 0.5)
            walk_end = min(walk_end, self.facade_depth(lp) - 1.0)
        out["rim"] = (d + 0.3, y, y + g("back_wall"), max(d + 0.6, walk_end))
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

    def mesh(self, name):
        if name.startswith("gb_bowl_"):
            name = getattr(self, "prefix", "gb_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
        """u6's seating surface every ``seats.rows_per_grid`` rows (u one repeat per section, the steps under every aisle),
        laid in three bands by depth in the tier (front, middle and back rows)."""
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
        for mat, i0, i1 in (("gb_seat_front", 0, a), ("gb_seat_mid", a, b), ("gb_seat_back", b, len(ks) - 1)):
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
        for run in self._runs(secs, key, lambda sec: len(sec[key]) > 1):
            lps = [loop[i] for i in run]
            prof = [secs[i][key] for i in run]
            self._rows_surface(m, "gb_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("gb_bowl_a")
        wall = p["wall"]["height"]
        m.grid("gb_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("gb_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "gb_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_gb_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        m2 = self.mesh("gb_bowl_b")
        self._ledge(m2, "gb_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_gb_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_gb_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "gb_concrete", loop, secs, "band_floor", up)
        m4 = self.mesh("gb_bowl_d")
        self._band(m4, "LIGHT_gb_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("gb_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                    [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_gb_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk, and behind them the concourse levels up to the roof
        # (the building is enclosed: from inside, a dark concourse band closes the gap under the roof)
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            m4.grid("LIGHT_gb_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                           [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("gb_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 0.4) for lp in lps]], facing=up)
            # the wall from the walk up to the roof, everywhere but where the lanai's glass stands
            sub = []
            for lp, r in list(zip(lps, rims)) + [(None, None)]:
                if lp is not None and not self.lanai_glass(lp):
                    sub.append((lp, r))
                    continue
                if len(sub) >= 2 and self.roof_height(*self.at(sub[0][0], sub[0][1][3], 0.0)[::2]) > sub[0][1][2] + 0.5:
                    tops = [self.roof_height(*self.at(q_, r_[3], 0.0)[::2]) - 0.3 for q_, r_ in sub]
                    m4.grid("gb_dark", [[self.at(q_, r_[3], r_[2]) for q_, r_ in sub],
                                        [self.at(q_, r_[3], t) for (q_, r_), t in zip(sub, tops)]],
                            [[(q_.s / 8, 1.0) for q_, _r in sub], [(q_.s / 8, 0.0) for q_, _r in sub]], facing=toward_field)
                sub = []

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
            m.quad("gb_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

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

    def _board(self, m, c, face, W, H, feed=None, frames=None):
        """One board: the black housing, the live picture (over ``feed`` of its width between two stat panels, or all of
        it), facing ``face``."""
        q = self.p["boards"]
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= np.linalg.norm(right)
        hv = np.array([0.0, H, 0.0])
        m.box("gb_black", c + hv / 2, (right, (0, 1, 0), face), (W / 2 + 0.6, H / 2 + 0.6, q["depth"] / 2), uvscale=0.1,
              bottom=True)
        fc = c + face * (q["depth"] / 2 + 0.05)
        fw = W * (feed if feed else 1.0) / 2
        (U0, U1), (V0, V1) = self.board_crop(2 * fw / H)
        A, B = fc - right * fw, fc + right * fw
        m.quad("jumbo_tron", A, B, B + hv, A + hv, (U0, V1), (U1, V1), (U1, V0), (U0, V0), facing=lambda p_, f=face: f)
        panels = []
        if feed:
            pw = W * (1.0 - feed) / 2
            for s_ in (-1, 1):
                pc = fc + right * s_ * (fw + pw / 2)
                ph = right * (pw / 2 - 0.2)
                m.quad("LIGHT_gb_board_panel", pc - ph, pc + ph, pc + ph + hv, pc - ph + hv, (0, 1), (1, 1), (1, 0),
                       (0, 0), facing=lambda p_, f=face: f)
                panels.append(pc)
        self.markers["jumbo"].append(tuple(fc + hv / 2))
        if frames is not None:
            frames.append(dict(centre=c, right=right, face=face, width=W, height=H, panels=panels,
                               panel_w=W * (1.0 - feed) / 2 if feed else 0.0))

    def _exterior(self):
        ring, _pos = self.facade_ring(72)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("gb_plaza", Mesh("gb_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= np.linalg.norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(12.0), grow(36.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("gb_plaza", rings, [uv(r) for r in rings], facing=up)
        # the environment kit (st3, nfl2k5_stadium_environment): outside the plaza and the atrium's block (it stands
        # out past the plaza on the east side), the lots with their cars, the roads, parks, water, trees and blocks
        # from OpenStreetMap, the far ground to the haze and the horizon band at 1,800 m
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        a_ = self.p["facade"]["atrium"]
        atrium = [(a_["x0"] - 8.0, a_["z0"] - 8.0), (a_["x1"] + 8.0, a_["z0"] - 8.0), (a_["x1"] + 8.0, a_["z1"] + 8.0),
                  (a_["x0"] - 8.0, a_["z1"] + 8.0)]
        self.env_counts = env.dress(self, self.venue, grade=GRADE, keep_out=[plaza, atrium], inner=plaza,
                                    eyes=env.shot_eyes(lambeau_shots()))

    def board_specs(self):
        """The two boards' footprints (for the seats under them)."""
        q = self.p["boards"]
        return [dict(c=(0.0, q["north_z"]), along=(1.0, 0.0), face=(0.0, 1.0), w=q["w"], bottom=q["north_bottom"],
                     depth=q["depth"], margin=1.0),
                dict(c=(0.0, q["south_z"]), along=(1.0, 0.0), face=(0.0, -1.0), w=q["w"], bottom=q["south_bottom"],
                     depth=q["depth"], margin=1.0)]

    def roof_height(self, x, z):
        """No roof: the rim's wall stops at its own top (``_bowl`` draws no wall above the walk)."""
        return -1.0

    def _end_board(self, end):
        """One end zone board (2023) over its end stands facing the field: the feed over its middle between two stat
        panels, the deep green housing behind it, the name as plain type high on its back (facing out, over the gate),
        and the end structure under it."""
        q = self.p["boards"]
        zc = q["north_z"] if end == "north" else q["south_z"]
        bottom = q["north_bottom"] if end == "north" else q["south_bottom"]
        face = np.array([0.0, 0.0, 1.0 if end == "north" else -1.0])
        m = self.meshes.setdefault("gb_boards", Mesh("gb_boards"))
        c = np.array([0.0, bottom, zc])
        self._board(m, c, face, q["w"], q["h"], feed=q["feed"], frames=self.board_frames)
        # the housing: the green box behind the face, its back carrying the name
        d = q["depth"]
        back_c = c - face * (d / 2 + 0.3) + np.array([0.0, q["h"] / 2, 0.0])
        m.box("gb_board_back", back_c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (q["w"] / 2 + 0.6, q["h"] / 2 + 1.2, d / 2),
              uvscale=1 / 8.0)
        zb = zc - face[2] * (d + 0.6 + 0.05)
        sw, sh = q["back_sign_w"], q["back_sign_h"]
        sy = bottom + q["h"] - sh - 1.0
        out = -face
        # the viewer outside looks along +face: screen right is cross(view, up)
        right = np.cross(face, np.array([0.0, 1.0, 0.0]))
        a = np.array([0.0, sy, zb]) - right * (sw / 2)
        b = np.array([0.0, sy, zb]) + right * (sw / 2)
        m.quad("gb_letters", a, b, b + np.array([0.0, sh, 0.0]), a + np.array([0.0, sh, 0.0]),
               (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, o=out: o)
        # the end structure under the board: the rooftop terrace's block at the north, the upper stands' back at the south
        qs = self.p["north" if end == "north" else "south"]
        st = self.meshes.setdefault("gb_ends", Mesh("gb_ends"))
        cz = (qs["z0"] + qs["z1"]) / 2
        st.box("gb_facade", np.array([0.0, (qs["top"] + GRADE) / 2, cz]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
               (qs["x"], (qs["top"] - GRADE) / 2 + 0.01, abs(qs["z0"] - qs["z1"]) / 2), uvscale=1 / 12.0)
        # its legs down to the structure's top
        for sx in (-1, 1):
            leg = np.array([sx * q["w"] * 0.36, (bottom + qs["top"]) / 2, zc - face[2] * (d / 2)])
            st.box("gb_steel", leg, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.7, max(0.2, (bottom - qs["top"]) / 2), 0.7),
                   uvscale=0.2)

    def _side_boards(self):
        """The side scoreboards (2023: 75 x 7.5 ft) on the suites' fascias over midfield, facing the field."""
        q = self.p["side_boards"]
        m = self.meshes.setdefault("gb_boards", Mesh("gb_boards"))
        for lp in (min(self.loop, key=lambda lp: (lp.nx - 1) ** 2 + (lp.z / 40.0) ** 2),
                   min(self.loop, key=lambda lp: (lp.nx + 1) ** 2 + (lp.z / 40.0) ** 2)):
            sec = self.section(lp)
            if "band" not in sec:
                continue
            db, yb0, yb1 = sec["band"]
            P = np.array(self.at(lp, db - 0.3, yb0 + 0.4))
            n = -np.array([lp.nx, 0.0, lp.nz])
            right = np.cross(-n, np.array([0.0, 1.0, 0.0]))
            right = -right
            hw, hh = right * (q["w"] / 2), np.array([0.0, q["h"], 0.0])
            m.quad("LIGHT_gb_board_panel", P - hw, P + hw, P + hw + hh, P - hw + hh, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, nn=n: nn)

    def _lights(self):
        """The LED lights (2018) on four masts a side over the sideline roofs and two banks on the south upper stands' roofs
        either side of the board (the 2016 panorama), facing the field; each lamp joins ``light_points``."""
        q = self.p["lights"]
        m = self.meshes.setdefault("gb_lights", Mesh("gb_lights"))
        self.light_points = []
        for sx in (1, -1):
            for zc in q["z"]:
                n = np.array([-sx, 0.0, 0.0])
                normal = n * math.cos(math.radians(30)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(30))
                ctr = np.array([sx * q["x"], q["y"], zc])
                along = np.array([0.0, 0.0, 1.0])
                upv = np.cross(along, normal); upv = upv / np.linalg.norm(upv) * (1.0 if upv[1] > 0 else -1.0)
                hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
                m.quad("LIGHT_gb_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1),
                       (1, 0), (0, 0), facing=lambda p_, nn=normal: nn)
                mh = (q["y"] - q["h"] / 2 - q["mast_y0"]) / 2
                for dz in (-q["w"] * 0.35, q["w"] * 0.35):
                    m.box("gb_steel", np.array([sx * (q["x"] + 1.2), q["mast_y0"] + mh, zc + dz]),
                          ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.35, mh, 0.35), uvscale=0.2)
                for k in range(-2, 3):
                    self.light_points.append(tuple(ctr + along * (k * q["w"] / 5)))
        for x, z in q["south"]:
            normal = np.array([0.0, 0.0, -1.0]) * math.cos(math.radians(30)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(30))
            ctr = np.array([x, q["south_y"], z])
            along = np.array([1.0, 0.0, 0.0])
            upv = np.cross(along, normal); upv = upv / np.linalg.norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
            m.quad("LIGHT_gb_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, nn=normal: nn)
            for k in range(-2, 3):
                self.light_points.append(tuple(ctr + along * (k * q["w"] / 5)))

    def _facade(self):
        """The building (DESIGN on the orthophoto and the 2015 to 2025 exteriors): brick walls with green window bands on
        the facade outline, the tower gates (2013) at the north and south ends (brick with the clock and the name as plain
        type over the gate), and the atrium's block on the east side (its glass toward Oneida Street)."""
        q = self.p["facade"]
        ring, _pos = self.facade_ring(96)
        R = list(ring) + [ring[0]]
        L = [0.0]
        for a, b in zip(R[:-1], R[1:]):
            L.append(L[-1] + math.dist(a, b))
        m = self.meshes.setdefault("gb_facade", Mesh("gb_facade"))
        m.grid("gb_facade", [[(x, GRADE - 0.5, z) for x, z in R], [(x, q["top"], z) for x, z in R]],
               [[(s / 24.0, 1.0) for s in L], [(s / 24.0, 0.0) for s in L]], facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
        # the walls' top: a parapet cap (flat, facing up) from the outline in a metre
        inner = [(x * 0.992, z * 0.992) for x, z in R]
        m.grid("gb_concrete", [[(x, q["top"], z) for x, z in R], [(x, q["top"], z) for x, z in inner]],
               [[(s / 24.0, 0.0) for s in L], [(s / 24.0, 0.1) for s in L]], facing=up)
        # the tower gates
        sg = self.meshes.setdefault("gb_signs", Mesh("gb_signs"))
        zmin = min(z for _x, z in ring)
        zmax = max(z for _x, z in ring)
        for zf, out in ((zmin, -1.0), (zmax, 1.0)):
            c = np.array([0.0, (q["gate_top"] + GRADE) / 2, zf + out * (q["gate_depth"] / 2 - 2.0)])
            m.box("gb_brick", c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (q["gate_w"] / 2, (q["gate_top"] - GRADE) / 2,
                                                                   q["gate_depth"] / 2), uvscale=1 / 8.0)
            zs = zf + out * (q["gate_depth"] - 2.0 + 0.1)
            w, h = q["sign_w"], q["sign_h"]
            y0 = q["gate_top"] + 0.6
            # the name over the gate, facing out; the viewer outside looks along -out: screen right = cross(view, up)
            view = np.array([0.0, 0.0, -out])
            right = np.cross(view, np.array([0.0, 1.0, 0.0]))
            a = np.array([0.0, y0, zs]) - right * (w / 2)
            b = np.array([0.0, y0, zs]) + right * (w / 2)
            sg.quad("gb_letters", a, b, b + np.array([0.0, h, 0.0]), a + np.array([0.0, h, 0.0]), (0, 1), (1, 1), (1, 0),
                    (0, 0), facing=lambda p_, o=out: np.array([0.0, 0.0, o]))
            # a plinth behind the name
            m.box("gb_board_back", np.array([0.0, y0 + h / 2, zs - out * 0.6]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                  (w / 2 + 1.0, h / 2 + 0.5, 0.5), uvscale=1 / 8.0)
        # the atrium's block on the east side
        a_ = q["atrium"]
        ac = self.meshes.setdefault("gb_atrium", Mesh("gb_atrium"))
        ac.box("gb_brick", np.array([(a_["x0"] + a_["x1"]) / 2, (a_["top"] + GRADE) / 2, (a_["z0"] + a_["z1"]) / 2]),
               ((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((a_["x1"] - a_["x0"]) / 2, (a_["top"] - GRADE) / 2, (a_["z1"] - a_["z0"]) / 2),
               uvscale=1 / 10.0)
        ac.quad("LIGHT_gb_glass", (a_["x1"] + 0.1, GRADE + 3.0, a_["z0"] + 12.0), (a_["x1"] + 0.1, GRADE + 3.0, a_["z1"] - 12.0),
                (a_["x1"] + 0.1, a_["top"] - 3.0, a_["z1"] - 12.0), (a_["x1"] + 0.1, a_["top"] - 3.0, a_["z0"] + 12.0),
                (0, 1), (6, 1), (6, 0), (0, 0), facing=lambda p_: np.array([1.0, 0.0, 0.0]))

    def _decks(self):
        """The building's roofs between the bowl's back and the outer walls (DESIGN; the 2015 aerial and the orthophoto:
        white roofs round the bowl): from the suites' glass top on the sidelines, or from the top walk's end at the ends,
        out to the facade's top."""
        q = self.p["facade"]
        m = self.meshes.setdefault("gb_decks", Mesh("gb_decks"))
        inner, outer, uv_in, uv_out = [], [], [], []
        for lp in self.loop:
            sec = self.section(lp)
            r = sec["rim"]
            if "band" in sec:
                db, _yb0, yb1 = sec["band"]
                d_in, y_in = db + 0.05, yb1
            else:
                d_in, y_in = r[3], r[2]
            d_out = self.facade_depth(lp) - 0.4
            d_in = min(d_in, d_out - 0.5)
            inner.append(self.at(lp, d_in, y_in))
            outer.append(self.at(lp, d_out, q["top"]))
            uv_in.append((lp.s / 20.0, 0.0))
            uv_out.append((lp.s / 20.0, (d_out - d_in) / 20.0))
        m.grid("gb_roof", [inner, outer], [uv_in, uv_out], facing=up)

    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"gb_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "gb"
        self.markers["jumbo"] = []
        self.board_frames = []
        self._end_board("south")
        self._end_board("north")
        self._side_boards()
        self._lights()
        south = min(loop, key=lambda lp: (lp.nz - 1) ** 2 + (lp.x / 40.0) ** 2)
        row = self.section(south)["upper"][4]
        self.nosebleed = self.at(south, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._decks()
        self._exterior()
        return self


def _min_rect(A):
    """The minimum-area rectangle round a footprint (four corners, counter-clockwise): the Strip's towers drawn as boxes."""
    A = np.asarray(A, float)
    c = A.mean(axis=0)
    best = None
    for deg in range(0, 90, 2):
        a = math.radians(deg)
        u = np.array([math.cos(a), math.sin(a)]); v = np.array([-u[1], u[0]])
        pu, pv = (A - c) @ u, (A - c) @ v
        area = np.ptp(pu) * np.ptp(pv)
        if best is None or area < best[0]:
            best = (area, u, v, pu.min(), pu.max(), pv.min(), pv.max())
    _a, u, v, u0, u1, v0, v1 = best
    return [tuple(c + u * a + v * b) for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def build(venue=VENUE, params=None):
    return Lambeau(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "gb_seat_front": ("gb_seat_front", CLASS_OPAQUE), "gb_seat_mid": ("gb_seat_mid", CLASS_OPAQUE),
    "gb_seat_back": ("gb_seat_back", CLASS_OPAQUE), "gb_concrete": ("gb_concrete", CLASS_OPAQUE),
    "gb_wall": ("gb_wall", CLASS_OPAQUE), "LIGHT_gb_ribbon": ("LIGHT_gb_ribbon", CLASS_OPAQUE),
    "LIGHT_gb_glass": ("LIGHT_gb_glass", CLASS_OPAQUE), "LIGHT_gb_concourse": ("LIGHT_gb_concourse", CLASS_OPAQUE),
    "gb_portal": ("gb_portal", CLASS_OPAQUE), "gb_dark": ("gb_dark", CLASS_OPAQUE), "gb_black": ("gb_black", CLASS_OPAQUE),
    "gb_steel": ("gb_steel", CLASS_OPAQUE), "LIGHT_gb_lights": ("LIGHT_gb_lights", CLASS_OPAQUE),
    "LIGHT_gb_board_panel": ("LIGHT_gb_board_panel", CLASS_OPAQUE), "gb_letters": ("gb_letters", CLASS_ALPHA),
    "gb_facade": ("gb_facade", CLASS_OPAQUE), "gb_brick": ("gb_brick", CLASS_OPAQUE),
    "gb_board_back": ("gb_board_back", CLASS_OPAQUE), "gb_roof": ("gb_roof", CLASS_OPAQUE),
    "gb_plaza": ("gb_plaza", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night (an open bowl: the sun on the outside surfaces, the
#: stands under a flat stadium light)
BASE = {
    "gb_seat_front": (214, 208, 198), "gb_seat_mid": (214, 208, 198), "gb_seat_back": (214, 208, 198),
    "crowd": (222, 216, 210), "gb_concrete": (208, 202, 194), "gb_wall": (230, 224, 220),
    "LIGHT_gb_ribbon": (255, 255, 255), "LIGHT_gb_glass": (190, 186, 255), "LIGHT_gb_concourse": (214, 208, 255),
    "gb_portal": (160, 156, 150), "gb_dark": (190, 186, 180), "gb_black": (200, 196, 190), "gb_steel": (214, 206, 150),
    "LIGHT_gb_lights": (255, 255, 255), "LIGHT_gb_board_panel": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    "gb_letters": (255, 255, 255), "gb_facade": (226, 212, 120), "gb_brick": (226, 212, 120),
    "gb_board_back": (220, 208, 110), "gb_roof": (226, 214, 110),
    "gb_plaza": (226, 210, 120),
}
#: the sun over Green Bay (DESIGN): by day high in the south (bearing 180: +z, high), in the afternoon low in the
#: west-south-west (bearing 250: -x, a little +z)
SUN = {"d": (-0.05, 0.80, 0.52), "a": (-0.78, 0.50, 0.30), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
#: rain and snow grey what is outside
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"gb_steel", "gb_letters", "gb_facade", "gb_brick", "gb_board_back", "gb_roof", "gb_plaza"}
#: the bowl: one level for every surface there (the stands are lit evenly in the retail scenes too)
INSIDE_LIGHT = 0.94


#: the live feed's vertex colour, the same in every light (st2 lab 2's rule, 2026-09-27: the screen draws the game's
#: previous frame at twice its vertex colour, so 116 keeps the loop gain about 1 and a screen that sees itself cannot
#: flood white)
FEED_VERTEX = 116


def light(mat, P, N, tod, weather, outside=False, occlusion=None):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
    if mat == "jumbo_tron":
        out = np.zeros((len(P), 4), np.uint8)
        out[:, :3] = FEED_VERTEX
        out[:, 3] = 255
        return out
    base = BASE.get(mat, (200, 190, 150))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif not outside:
        f = np.full(n, INSIDE_LIGHT)
    elif tod == "n":
        f = np.full(n, 1.0)
    else:
        sun = np.array(SUN[tod])
        s = sun / np.linalg.norm(sun)
        nd = np.clip(N @ s, 0, 1)
        f = (0.76 + 0.26 * nd) if tod == "d" else (0.64 + 0.45 * nd)
    if mat == "gb_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    if (outside or not mat.startswith("LIGHT_")) and weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat in ("gb_facade", "gb_brick", "gb_board_back", "gb_steel") and tod == "n":
        k = np.clip((P[:, 1] - GRADE) / 60.0, 0, 1)
        out[:, 0] = np.clip(140 - 60 * k, 0, 255); out[:, 1] = np.clip(138 - 60 * k, 0, 255); out[:, 2] = np.clip(136 - 50 * k, 0, 255)
    return out


def _rgba(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def _textures(venue, tod, weather):
    art = ART_DIR
    # MATERIALS order (deterministic across processes); the environment kit draws its own
    keys = [k for k in dict.fromkeys(k for k, _c in MATERIALS.values()) if not k.startswith("env_")]
    out = {key: _rgba(art / f"{key}.png") for key in keys}
    out.update(env.textures(venue, tod, weather))
    return out


#: the game's digits on the south board's two stat panels (slot spacing, half width, half height, metres) and their height
#: on the panel (a fraction of the board's height)
DIGIT_SLOT, DIGIT_HW, DIGIT_HH, DIGIT_Y = 0.8, 0.36, 0.64, 0.66


def adjust_digits(shape, sc, model):
    """The score and clock digits onto the south board's two stat panels (the game's own digits: two strips, one per
    panel, in each panel's dark window); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    b = model.board_frames[0]
    strips = [dict(centre=pc + b["face"] * 0.12 + np.array([0.0, b["height"] * DIGIT_Y, 0.0]), right=b["right"])
              for pc in b["panels"]]
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


def nudge_props(shape, limit_x):
    """Move each connected piece of a retail sideline prop whose far edge passes ``limit_x`` (in metres, on the +x side)
    back in along x until it ends there (Allegiant's rule, kept: an apron narrower than the retail props would need it; the
    bench area reached x 51.0). Returns the pieces moved."""
    P = [np.array(p, float) / 100.0 for p in sb.shape_positions(shape)]
    parent = list(range(len(P)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for sm_ in shape.submeshes:
        for _mode, ix in sb.decode_words(sm_.words):
            for a, b in zip(ix[:-1], ix[1:]):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    comps = {}
    for i in range(len(P)):
        comps.setdefault(find(i), []).append(i)
    moved = 0
    for idx in comps.values():
        far = max(P[i][0] for i in idx)
        if far > limit_x:
            for i in idx:
                P[i] = P[i] - np.array([far - limit_x, 0.0, 0.0])
            moved += 1
    if moved:
        sb.set_positions(shape, [tuple(p * 100.0) for p in P])
    return moved


#: the away bench area's pieces end here (metres, +x): the retail s10 props reach x 44.0 (PROVED OFFLINE), so none moves
PROP_LIMIT_X = 44.5


def flare_points(model):
    """The four flare markers: over the roof's floodlight ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT
    (300 m) up (u6's lab 5, PROVED IN GAME at SoFi: no flare discs in the flyover, short night shadows under the feet).
    Out of every Lambeau Field shot too (test: Cameras)."""
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
    """The dry bundle of the same time of day (s10nr.iff -> s10nd.iff)."""
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
    """The Lambeau Field scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "gb_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "gb_digits", tmpl_shape)
    sc.shapes = [s for s in sc.shapes if s.name.startswith(KEEP_PREFIXES)]
    for s in sc.shapes:
        if s.name.startswith("sideline_away"):
            nudge_props(s, PROP_LIMIT_X)
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
    its stadium scene replaced by the Lambeau Field model and its intro cameras rewritten when ``cameras`` gives the shots.
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

#: The field (the retail s10 field is grass, one flat colour quad between the goal lines; the grass word stays retail and
#: Modern playing surfaces lays the 2026 turf): the model paints it mown in 5-yard bands (u runs along the field once the
#: quad's UVs are remapped, in place), the grass outside the field of play, and lays the Packers' 2026 end zones and
#: midfield from the league project's art (u4's NE folder), composited over clean grass. The retail s10 field lays its
#: endzone_N_* panels at -z (the north end here) and its endzone_S_* panels at +z, both on the same three textures
#: (PROVED OFFLINE, test: Field), so each end's art goes in its own half of the shared textures (u6's split at SoFi).
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
    """{material: RGBA} of the Packers' field art in a league art root (``<root>/<team dir>/venue`` for prefix s10), or
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
    """The Lambeau Field field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "gb_grass.png")
    outside = _rgba(FIELD_ART / "gb_grass_outside.png")
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

#: The components each retail s10 intro camera's channel carries (PROVED OFFLINE from the retail s10dd and s10ns intro
#: cameras): camera 1 all five; camera 2 all but pitch; camera 3 only y, z and pitch (it plays on x = 0 looking north);
#: camera 4 all but z (it plays at z = 0); camera 5 all five. A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"}, {"y", "z", "pitch"},
                             {"x", "y", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the Lambeau Field flyover, one shot per retail camera, each wanting 0 wherever its camera carries
#: nothing.
#: 1: outside from the north-west over Lombardi Avenue's lots, the north gate and the north board's back with the name,
#:    drifting east;
#: 2 (level): over the north end's rooftop terrace looking south down the bowl to the 2013 upper stands and the south
#:    board, gliding south;
#: 3 (on the axis, looking north): a crane in the south end zone rising toward the north board;
#: 4 (at z = 0): outside from the east over Oneida Street, the atrium's block and the east side's light masts;
#: 5: field level in the north end zone looking south to the south end and its board.
_OUTSIDE = dict(eye=(-240.0, 62.0, -330.0), target=(0.0, 30.0, -110.0), fov=38.0, rates=dict(x=7.0, z=2.0))
_TERRACE = dict(eye=(-20.0, 40.0, -96.0), target=(10.0, 40.0, 120.0), fov=46.0, rates=dict(z=3.0, yaw=-1.0))
_CRANE = dict(eye=(0.0, 6.0, 58.0), target=(0.0, 30.0, -140.0), fov=46.0, rates=dict(y=2.2, pitch=0.3))
_EAST = dict(eye=(330.0, 70.0, 0.0), target=(60.0, 30.0, 0.0), fov=40.0, rates=dict(x=-6.0, yaw=0.8))
_FIELD_NORTH = dict(eye=(0.0, 2.5, -58.0), target=(0.0, 30.0, 150.0), fov=44.0, rates=dict(z=3.0))
GB_SHOTS = [_OUTSIDE, _TERRACE, _CRANE, _EAST, _FIELD_NORTH]


def lambeau_shots():
    out = []
    for s, present in zip(GB_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=lambeau_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s10 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s10 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the Lambeau Field stretch: from the cityscape chunk to the end of the intro cameras."""
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
                                         workers=workers, progress=progress, label="Lambeau Field"):
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
    """(field span of the same size, receipt) for one retail bundle: the Lambeau Field field, graded by Modern colour when its
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
    raise sb.ScneBuildError(f"{name}: the Lambeau Field field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_lambeau_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_lambeau_receipt/v1"
BUILD_CAPTION = "Lambeau Field for the Packers (experimental)"
HELP_TEXT = (
    "The Green Bay Packers' Lambeau Field as it stands today, built as a new model for Packers home games: the bowl of "
    "bleachers with the suites and press levels over the sidelines, the 2013 south end zone expansion's upper stands, the "
    "two 2023 end zone boards (220 x 48 ft) with the live feed and the score, the north end's rooftop terrace, the LED "
    "lights on their masts, the brick and green building with its tower gates, Titletown and the lots round it, and a new "
    "pregame flyover with exterior passes. The field is grass mown in 5-yard bands with the 2026 venue art's Packers end "
    "zones and midfield when that option is on. The row reads Lambeau Field, Green Bay, WI, with today's capacity; rain "
    "and snow still fall on the open bowl. The 2026 venue art leaves the Packers' packages to it. Off in every preset; "
    "appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Lambeau Field pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Lambeau Field pins schema")
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
    """retail / applied / foreign for the Lambeau Field stretch of one of the nine bundles."""
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
    return Path(str(source) + ".lambeau.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Lambeau Field receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s10 row."""
    from . import nfl2k5_lambeau_venue as agv
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
        entry = archive.entries[agv.ROST_OUTER_INDEX]
        row = agv.rost_state(archive.read(entry.virtual_offset, entry.size))
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
    sb.require(state == ("applied" if enabled else "retail"), f"Lambeau Field state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Lambeau Field)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Packers stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=lambeau_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s10 to it): the Lambeau Field field, stadium,
    cameras and collapsed cityscape of the nine bundles, and the s10 row. The retail bundles come from ``retail_source``;
    the image's own bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the
    field is composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour
    still recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Packers end zones and midfield go onto the
    new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_lambeau_venue as agv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Lambeau Field")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Lambeau Field needs retail Packers packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Lambeau Field")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Lambeau Field bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], applied_sha256=sha(after),
                                            field=info.get("field"), system=info["system"], video=info["video"],
                                            fan_art=info.get("fan_art"))
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        receipt["rost"] = agv.apply_rost(archive)
    if new_colour is not None:
        new_colour["lambeau"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Lambeau Field: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Lambeau Field changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Lambeau Field: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_lambeau_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Lambeau Field stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st2-lambeau.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST2_LAMBEAU_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
