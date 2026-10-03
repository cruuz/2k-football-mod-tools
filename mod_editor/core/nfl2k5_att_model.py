"""AT&T Stadium model (experimental): the Dallas Cowboys' AT&T Stadium (Arlington, opened 2009; HKS) built from scratch as
the stadium scene of venue record s07 (retail Texas Stadium), all nine bundles (day, afternoon, night; dry, rain, snow).

Job st2 (2026-09-25), on u5's builder, u6's SoFi methods and st's Highmark Stadium model. References (the Wikipedia
article, OpenStreetMap, the Commons photos and the Cowboys' 2026 galleries) are cited in the st2 report. The scene:

* the bowl in its sideline and end stacks: along the sidelines the lower bowl, the club level under its ribbon, the suite
  levels behind glass, the 300 level and the tall upper deck; at the ends the lower end-zone seats and the six stepped
  Party Pass decks in front of the glass end walls (Wikipedia); navy and charcoal seats and u6's crowd billboards;
* the dome on the leaning glass facade (the OSM outline pushed out by the facade's tilt), dark steel from below, its
  operable panels closed between the arches as the bright translucent corridor the photos show; the two box arches
  along the field over it, from their feet outside the end walls, hanging below the panels inside;
* the centre-hung board over midfield: two sideline screens (about 160 x 72 ft) and two end screens (about 51 x 29 ft) on
  the ``jumbo_tron`` material the game draws its live feed into (a crop of the feed at each screen's own aspect), a black
  housing with the LED ring under it and four cables to the roof; the game's score and clock digits under the end screens;
* the glass curtain wall on the OpenStreetMap outline (way 47086748), the glass end walls, the plaza, the parking lots,
  roads and neighbouring buildings from OpenStreetMap;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes, the markers and the materials the executable looks up by name
  (``crowd``, ``jumbo_tron``, ``digit_*``). The retail light rays through Texas Stadium's roof hole are dropped.

The record stays indoor (retail s07's word): the roof is modelled closed, so rain and snow bundles show a dry bowl.
Geometry is in metres here (x across; y up from the field; z along, +z the east end zone toward azimuth 68.75 degrees)
and centimetres in the game. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
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

OWNER = "nfl2k5_att_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_att_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s07"
VENUES = (VENUE,)
#: the field sits below the plaza (DESIGN, the photos: the lower bowl's back concourse opens toward the plazas)
GRADE = 6.0
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
    return dict(W=math.pow(max(nx, 0.0), 2), E=math.pow(max(-nx, 0.0), 2), N=math.pow(max(nz, 0.0), 2),
                S=math.pow(max(-nz, 0.0), 2))


def plan_loop4(xw, xe, zn, zs, R, step=7.0, corner_steps=9):
    """The field-wall line: a rounded rectangle with its four straights at x = +xw (west), x = -xe (east), z = +zn (north)
    and z = -zs (south), corner radius R, counter-clockwise from above (+y), starting on the west straight level with
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

    line((xw, 0.0), (xw, zn - R), (1, 0))
    arc(xw - R, zn - R, 0.0, math.pi / 2)
    line((xw - R, zn), (-xe + R, zn), (0, 1))
    arc(-xe + R, zn - R, math.pi / 2, math.pi)
    line((-xe, zn - R), (-xe, -zs + R), (-1, 0))
    arc(-xe + R, -zs + R, math.pi, 1.5 * math.pi)
    line((-xe + R, -zs), (xw - R, -zs), (0, -1))
    arc(xw - R, -zs + R, 1.5 * math.pi, 2 * math.pi)
    line((xw, -zs + R), (xw, 0.0), (1, 0))
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

#: DESIGN, pass 1 (st2, 2026-09-25). AT&T Stadium (HKS, opened 2009) in the retail Texas Stadium record s07. The plan: the
#: OpenStreetMap outline (way 47086748, 242 x 319 m, the long axis at bearing 68.75 is the field's; its flat ends are the
#: glass end walls), the field wall 15.1 m off the sidelines and 14.6 m behind the end lines, clear of the retail
#: sideline props (they reach x 37.8 m and z 68.2 m) (the photos: the wide
#: sideline apron with the benches and the navy star wall); the sideline stack of the lower bowl, the club level, the
#: suite levels behind glass and the tall upper deck; the end stack of the lower end-zone seats and the six stepped
#: Party Pass decks (Wikipedia); the dome on the leaning glass facade, the two arches, the centre-hung board.
PARAMS = dict(
    loop=dict(xw=39.5, xe=39.5, zn=69.5, zs=69.5, R=22.0, step=7.0, corner_steps=9),
    wall=dict(height=1.3),
    sides=dict(
        W=dict(low_d0=2.6, low_y0=1.7, low_rows=34, low_tread=0.86, low_rise0=0.30, low_rise1=0.47,
               t2_over=3.0, t2_rows=12, t2_rise=0.52, t2_tread=0.86, band_h=8.4, t3_rows=8, t3_rise=0.56, t3_over=1.0,
               up_d=41.0, up_y=39.0, up_rows=30, up_tread=0.82, up_rise=0.64, deck=0.0),
        E=dict(low_d0=2.6, low_y0=1.7, low_rows=34, low_tread=0.86, low_rise0=0.30, low_rise1=0.47,
               t2_over=3.0, t2_rows=12, t2_rise=0.52, t2_tread=0.86, band_h=8.4, t3_rows=8, t3_rise=0.56, t3_over=1.0,
               up_d=41.0, up_y=39.0, up_rows=30, up_tread=0.82, up_rise=0.64, deck=0.0),
        N=dict(low_d0=2.6, low_y0=1.7, low_rows=24, low_tread=0.86, low_rise0=0.32, low_rise1=0.46,
               t2_over=0.0, t2_rows=6, t2_rise=2.8, t2_tread=4.6, band_h=0.0, t3_rows=0, t3_rise=0.56, t3_over=1.0,
               up_d=51.5, up_y=28.0, up_rows=0, up_tread=0.82, up_rise=0.64, deck=1.0),
        S=dict(low_d0=2.6, low_y0=1.7, low_rows=24, low_tread=0.86, low_rise0=0.32, low_rise1=0.46,
               t2_over=0.0, t2_rows=6, t2_rise=2.8, t2_tread=4.6, band_h=0.0, t3_rows=0, t3_rise=0.56, t3_over=1.0,
               up_d=51.5, up_y=28.0, up_rows=0, up_tread=0.82, up_rise=0.64, deck=1.0),
    ),
    tier=dict(tread=0.86, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=3.0, walk=6.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the dome: its eave on the facade ring (the facade leans out 14 degrees, Wikipedia and HKS), its crown over the
    #: field between the arches; the operable panels are the part between the arches (closed: the record stays indoor)
    roof=dict(eave=50.0, crown=87.0, power=0.45, arch_x=40.0, depth=3.0, rings=10, points=84, panels_z=118.0,
              panel_drop=1.5),
    #: the two box arches along the field (Wikipedia: nearly 300 ft tall, anchored at each end), their feet outside the
    #: end walls at the grey arch-support blocks OSM maps
    arches=dict(x=40.0, feet_z=176.0, peak=97.0, power=3.2, depth=14.0, width=8.0, samples=36),
    #: the centre-hung board (Wikipedia: the Mitsubishi board; the photos: two sideline screens about 160 x 72 ft and two
    #: end screens about 51 x 29 ft on a black housing, its bottom about 90 ft over the field)
    board=dict(side_w=48.8, side_h=21.9, end_w=15.5, end_h=8.8, depth=15.0, bottom=27.4, cable=0.35),
    lights=dict(every=3, drop=1.2, w=3.6, h=1.8),
    facade=dict(lean=14.0, height=40.0, base=4.0, mullion_every=3.0, end_wall_w=54.9),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


# ------------------------------------------------------------------------------------------------ the model

class ATT(sm.SoFi):
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
        self.loop = plan_loop4(q["xw"], q["xe"], q["zn"], q["zs"], q["R"], q["step"], q["corner_steps"])
        self.aisles = self._aisle_positions()
        self.meshes = {}
        self.markers = {}

    # -- the section: the sideline and end stacks, blended round the corners ---------------------------------------
    def section(self, lp):
        p = self.p
        g = lambda key: _side_blend(lp, key, p)  # noqa: E731
        out = {}
        # the lower bowl
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
        # the club level's fascia (the Ring of Honor ribbon) over the lower bowl; at the ends the first Party Pass deck
        fh, gap = p["tier"]["fascia_h"], p["tier"]["gap"]
        d2 = lower[-1][0] - g("t2_over")
        y2 = lower[-1][1] + 1.1
        out["ribbon"] = (d2, y2, y2 + fh)
        out["lower_back"] = (lower[-1][0] + 0.6, lower[-1][1], y2 - 0.02)
        out["soffit2"] = (d2 + 0.02, lower[-1][0] + 0.6, y2)
        rows2 = int(round(g("t2_rows")))
        d, y = d2 + 0.4, y2 + fh + gap
        t2 = [(d, y)]
        tread2, rise2 = g("t2_tread"), g("t2_rise")
        for _i in range(rows2):
            d += tread2
            y += rise2
            t2.append((d, y))
        out["t2"] = t2
        out["deck"] = g("deck")
        # the suite levels behind glass (sidelines)
        bh = g("band_h")
        yb = t2[-1][1] + 0.3
        db = t2[-1][0] + 1.0
        if bh > 0.2:
            out["band"] = (db, yb, yb + bh)
            out["band_floor"] = (t2[-1][0], db, t2[-1][1])
        ytop = yb + bh if bh > 0.2 else t2[-1][1]
        # the 300 level over the suites
        rows3 = int(round(g("t3_rows")))
        d3 = max(db - g("t3_over"), t2[-1][0] + 0.6)
        y3 = ytop + 0.35
        if rows3 > 0:
            out["t3_fascia"] = (d3, y3, y3 + fh)
        d, y = d3 + 0.4, y3 + fh + gap
        t3 = [(d, y)]
        for _i in range(rows3):
            d += p["tier"]["tread"]
            y += g("t3_rise")
            t3.append((d, y))
        out["t3"] = t3
        prev = t3 if rows3 > 0 else (t2 if rows2 > 0 else lower)
        # the upper deck (the 400 level) along the sidelines and round the corners; over the ends a parapet on the top
        # Party Pass deck
        du = max(g("up_d"), prev[-1][0] + 0.4)
        yu = max(g("up_y"), prev[-1][1] + 0.4)
        out["up_fascia"] = (du, yu, yu + fh)
        slope = g("up_rise") / g("up_tread")
        dback = max(prev[-1][0] + 0.5, du + 0.5)
        yback = yu + (dback - du) * slope - 1.4 * (1.0 if dback > du + 2.0 else 0.0)
        yback = max(yback, prev[-1][1] + 2.2)
        out["back3"] = (dback, prev[-1][1], yback - 0.02)
        out["up_soffit_slope"] = ((du + 0.02, yu), (dback, yback))
        rowsu = int(round(g("up_rows")))
        room = self.facade_depth(lp) - 1.0 - p["rim"]["walk"] * 0.5 - 0.7 - (du + 0.4)
        rowsu = max(0, min(rowsu, int(room / g("up_tread"))))
        d, y = du + 0.4, yu + fh + gap
        upd = [(d, y)]
        for _i in range(rowsu):
            d += g("up_tread")
            y += g("up_rise")
            upd.append((d, y))
        out["upper"] = upd
        rim = p["rim"]
        walk_end = self.facade_depth(lp) - 1.0
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
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"att_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "att"
        ends = [sec for lp, sec in zip(loop, secs) if abs(lp.nz) > 0.999 and abs(lp.x) < 10.0]
        self.end_floor = max(sec["rim"][2] for sec in ends) if ends else 34.0
        self._roof()
        self._arches()
        self._lights()
        self._board()
        west = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(west)["upper"][min(4, len(self.section(west)["upper"]) - 1)]
        self.nosebleed = self.at(west, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._exterior()
        return self

    def mesh(self, name):
        if name.startswith("att_bowl_"):
            name = getattr(self, "prefix", "att_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats: navy and silver, darker toward the back of each tier --------------------------------------------
    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0, deck=None):
        """u6's seating surface every ``seats.rows_per_grid`` rows (u one repeat per section, the steps under every aisle),
        in three bands by depth in the tier (the photos: navy and dark silver seats). Where ``deck`` is over 0.5 the rows
        are the Party Pass decks' floors."""
        rows = self.p["seats"]["rows_per_grid"]
        R = max(len(pr) for pr in profiles) - 1
        if R < 1:
            return
        ks = list(range(0, R + 1, rows if not deck else 1))
        if ks[-1] != R:
            ks.append(R)
        pts = [[self.at(lp, *pr[min(k, len(pr) - 1)]) for lp, pr in zip(loop, profiles)] for k in ks]
        uvs = [[(self.aisle_u(lp.s), vstart + min(k, len(pr) - 1) / self.p["seats"]["rows_per_v"])
                for lp, pr in zip(loop, profiles)] for k in ks]
        if deck:
            m.grid("att_deck", pts, uvs, facing=up_toward_field)
            return
        a = min(range(len(ks)), key=lambda i: abs(ks[i] - 0.35 * R))
        b = max(a, min(range(len(ks)), key=lambda i: abs(ks[i] - 0.68 * R)))
        for mat, i0, i1 in (("att_seat_front", 0, a), ("att_seat_mid", a, b), ("att_seat_back", b, len(ks) - 1)):
            if i1 > i0:
                m.grid(mat, pts[i0:i1 + 1], uvs[i0:i1 + 1], facing=up_toward_field)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("att_bowl_a")
        wall = p["wall"]["height"]
        m.grid("att_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("att_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "att_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_att_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        # the club level and, at the ends, the Party Pass decks
        m2 = self.mesh("att_bowl_b")
        self._ledge(m2, "att_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_att_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        t2 = [sec["t2"] for sec in secs]
        decks = [sec["deck"] for sec in secs]
        if max(len(x) for x in t2) > 1:
            # split the loop into runs of seats and runs of decks
            runs, cur, kind = [], [], None
            for i, dk in enumerate(decks):
                k = dk > 0.5
                if kind is None or k == kind:
                    cur.append(i)
                else:
                    runs.append((kind, cur)); cur = [cur[-1], i]
                kind = k
            runs.append((kind, cur))
            for is_deck, idx in runs:
                if len(idx) < 2:
                    continue
                lp_r = [loop[i] for i in idx]
                pr_r = [t2[i] for i in idx]
                self._rows_surface(m2, "att_seat", lp_r, pr_r, 2, deck=is_deck)
                self._crowd(m2, lp_r, pr_r)
                if is_deck:
                    # each deck's glass railing along its front edge (the 2022 end-zone photo: glass rails, steel tops)
                    R_ = min(len(pr) for pr in pr_r)
                    Ls = [lp.s for lp in lp_r]
                    for k in range(1, R_):
                        lo_ = [self.at(lp, pr[k][0] + 0.15, pr[k][1]) for lp, pr in zip(lp_r, pr_r)]
                        hi_ = [self.at(lp, pr[k][0] + 0.15, pr[k][1] + 1.1) for lp, pr in zip(lp_r, pr_r)]
                        m2.grid("att_rail", [lo_, hi_], [[(s_ / 6.0, 1.0) for s_ in Ls], [(s_ / 6.0, 0.0) for s_ in Ls]],
                                facing=toward_field)
        self._band(m2, "LIGHT_att_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "att_concrete", loop, secs, "band_floor", up)
        # the 300 level over the suites
        m3 = self.mesh("att_bowl_c")
        self._band(m3, "LIGHT_att_ribbon", loop, secs, "t3_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        t3 = [sec["t3"] for sec in secs]
        if max(len(x) for x in t3) > 1:
            self._rows_surface(m3, "att_seat", loop, t3, 2)
            self._crowd(m3, loop, t3)
        self._band(m3, "LIGHT_att_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        # the upper deck
        m4 = self.mesh("att_bowl_d")
        run = [(lp, sec["up_soffit_slope"]) for lp, sec in zip(loop, secs)]
        m4.grid("att_concrete", [[self.at(lp, *a) for lp, (a, b) in run], [self.at(lp, *b) for lp, (a, b) in run]],
                [[(lp.s / 8.0, 0.0) for lp, _ in run], [(lp.s / 8.0, 0.4) for lp, _ in run]], facing=down)
        self._band(m4, "att_dark", loop, secs, "up_fascia", 0.0, 1.0, u_per_m=1 / 8.0)
        upd = [sec["upper"] for sec in secs]
        self._rows_surface(m4, "att_seat", loop, upd, 2)
        self._crowd(m4, loop, upd)
        self._portals(m4, loop, secs, "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk to the facade
        m4.grid("LIGHT_att_concourse", [[self.at(lp, sec["rim"][0], sec["rim"][1]) for lp, sec in zip(loop, secs)],
                                        [self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 1.0) for lp in loop], [(lp.s / 8, 0.0) for lp in loop]], facing=toward_field)
        m4.grid("att_concrete", [[self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)],
                                 [self.at(lp, sec["rim"][3], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.4) for lp in loop]], facing=up)

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
            m.quad("att_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    # -- the dome -------------------------------------------------------------------------------------------------
    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

    def eave_ring(self, n):
        """The dome's eave: the facade outline pushed out by the facade's lean at its top, at the eave height."""
        q, f = self.p["roof"], self.p["facade"]
        ring, _pos = self.facade_ring(n)
        ring = np.array(ring, float)
        c = ring.mean(axis=0)
        out = []
        push = f["height"] * math.tan(math.radians(f["lean"]))
        for x, z in ring:
            v = np.array([x, z]) - c
            v /= math.np_norm(v)
            out.append((x + v[0] * push, z + v[1] * push))
        return out, q["eave"]

    def roof_height(self, x, z):
        """The dome's underside over (x, z): the eave height on the eave ring rising to the crown over the field; between
        the arches the operable panels ride just under the arches' top chords (the 2010 full view: the bright panels
        between two deep arch trusses that hang below them), so the corridor is higher than the dome round it."""
        q = self.p["roof"]
        rho = self._roof_rho(x, z)
        dome = q["eave"] + (q["crown"] - q["eave"]) * math.pow(max(0.0, 1.0 - rho * rho), q["power"])
        a = self.p["arches"]
        if abs(x) < a["x"] - 0.5 and abs(z) < q["panels_z"]:
            return max(dome, self.arch_y(z) - q["panel_drop"])
        return dome

    def _roof_rho(self, x, z):
        ring = self.__dict__.get("_eave_polar")
        if ring is None:
            pts, _y = self.eave_ring(360)
            P = np.array(pts)
            ang = math.np_arctan2(P[:, 1], P[:, 0])
            order = np.argsort(ang)
            ring = (ang[order], math.np_hypot(P[:, 0], P[:, 1])[order])
            self._eave_polar = ring
        a, r = ring
        th = math.atan2(z, x)
        R = float(np.interp(th, a, r, period=2 * math.pi))
        return math.hypot(x, z) / R

    def _roof(self):
        """The dome over the bowl: its underside seen from the seats (translucent panels on steel trusses; the operable
        panels between the arches closed), its top seen from outside (white membrane, the panels' raised centre)."""
        q = self.p["roof"]
        N, K = q["points"], q["rings"]
        eave, _y = self.eave_ring(N)
        E = np.array(eave + [eave[0]])
        rows_u, rows_t, uvs = [], [], []
        for k in range(K + 1):
            f = k / K                                   # 0 at the eave, 1 at the centre
            ring_u, ring_t, uv = [], [], []
            for x, z in E:
                px, pz = x * (1 - f), z * (1 - f * 0.985)  # never collapse to one point: a short ridge along the field
                y = self.roof_height(px, pz)
                ring_u.append((px, y, pz))
                ring_t.append((px, y + q["depth"], pz))
                uv.append((math.atan2(z, x) * 30.0, f * 10.0))
            rows_u.append(ring_u); rows_t.append(ring_t); uvs.append(uv)
        self.roof_rows = rows_u
        und = self.meshes.setdefault("att_roof_under", Mesh("att_roof_under"))
        top = self.meshes.setdefault("att_roof_top", Mesh("att_roof_top"))
        ax = self.p["arches"]["x"]
        pz = q["panels_z"]
        # the underside: the fixed roof (dark steel) outside the operable panels, the panels (translucent, closed) in the
        # rectangle between the arches (the 2010 full view and the 2022 roof photos: a bright band between two dark arch
        # trusses, dark structure all round it); each ring is cut into runs of one kind
        for i in range(K):
            ra, rb = rows_u[i], rows_u[i + 1]
            ua, ub = uvs[i], uvs[i + 1]
            kinds = []
            for j in range(len(ra) - 1):
                cx_ = (ra[j][0] + ra[j + 1][0] + rb[j][0] + rb[j + 1][0]) / 4
                cz_ = (ra[j][2] + ra[j + 1][2] + rb[j][2] + rb[j + 1][2]) / 4
                kinds.append("att_panels" if abs(cx_) < ax - 1.0 and abs(cz_) < pz else "att_roof_under")
            j0 = 0
            for j in range(1, len(kinds) + 1):
                if j == len(kinds) or kinds[j] != kinds[j0]:
                    und.grid(kinds[j0], [ra[j0:j + 1], rb[j0:j + 1]], [ua[j0:j + 1], ub[j0:j + 1]], facing=down)
                    j0 = j
        # the top, seen only from outside: every other ring and every other point
        ks = list(range(0, K + 1, 2)) + ([K] if K % 2 else [])
        for i0, i1 in zip(ks[:-1], ks[1:]):
            top.grid("att_roof_top", [rows_t[i0][::2] + [rows_t[i0][-1]], rows_t[i1][::2] + [rows_t[i1][-1]]],
                     [uvs[i0][::2] + [uvs[i0][-1]], uvs[i1][::2] + [uvs[i1][-1]]], facing=up)
        # the eave's fascia: from the facade top to the roof edge
        f_ = self.p["facade"]
        base = [(x, GRADE + f_["height"], z) for x, z in E]
        top_e = [(x, q["eave"] + q["depth"], z) for x, z in E]
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(E[:-1], E[1:])])])
        top.grid("att_roof_edge", [base, top_e], [[(s / 12.0, 1.0) for s in L], [(s / 12.0, 0.0) for s in L]],
                 facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))

    # -- the arches -------------------------------------------------------------------------------------------------
    def arch_y(self, z):
        q = self.p["arches"]
        t = min(1.0, abs(z) / q["feet_z"])
        return q["peak"] * (1.0 - math.pow(t, q["power"]))

    def _arches(self):
        """The two box arches (lattice steel, grey) along the field over the dome, from their feet outside the end walls."""
        q = self.p["arches"]
        m = self.meshes.setdefault("att_arches", Mesh("att_arches"))
        zs = np.linspace(-q["feet_z"], q["feet_z"], q["samples"] + 1)
        for sx in (1.0, -1.0):
            x0 = sx * q["x"]
            top = [(x0, self.arch_y(z) + 0.0, z) for z in zs]
            bot = [(x0, max(GRADE, self.arch_y(z) - q["depth"]), z) for z in zs]
            L = np.concatenate([[0.0], np.cumsum(math.np_hypot(np.diff(zs), np.diff([p_[1] for p_ in top])))])
            for off, face in ((q["width"] / 2, 1.0), (-q["width"] / 2, -1.0)):
                m.grid("att_truss", [[(x + off, y, z) for x, y, z in bot], [(x + off, y, z) for x, y, z in top]],
                       [[(s / q["depth"], 1.0) for s in L], [(s / q["depth"], 0.0) for s in L]],
                       facing=lambda p_, f=face: np.array([f, 0.0, 0.0]))
            m.grid("att_steel", [[(x - q["width"] / 2, y, z) for x, y, z in top], [(x + q["width"] / 2, y, z) for x, y, z in top]],
                   [[(0.0, s / 8.0) for s in L], [(1.0, s / 8.0) for s in L]], facing=up)
            m.grid("att_steel", [[(x + q["width"] / 2, y, z) for x, y, z in bot], [(x - q["width"] / 2, y, z) for x, y, z in bot]],
                   [[(0.0, s / 8.0) for s in L], [(1.0, s / 8.0) for s in L]], facing=down)

    # -- the lights on the roof trusses round the operable panels ------------------------------------------------------
    def _lights(self):
        q = self.p["lights"]
        m = self.meshes.setdefault("att_lights", Mesh("att_lights"))
        ring = self.roof_rows[max(1, len(self.roof_rows) // 2)]
        pts = []
        for k in range(0, len(ring) - 1, q["every"]):
            x, y, z = ring[k]
            n = np.array([x, 0.0, z]); n /= max(1e-9, math.np_norm(n))
            ctr = np.array([x, y - q["drop"], z])
            along = np.array([-n[2], 0.0, n[0]])
            normal = -n * math.cos(math.radians(55)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(55))
            upv = np.cross(along, normal); upv = upv / math.np_norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
            m.quad("LIGHT_att_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, nn=normal: nn)
            pts.append(tuple(ctr))
        self.light_points = pts

    # -- the centre-hung board ---------------------------------------------------------------------------------------
    #: the live feed fills u 0 to 0.625, v 0 to 0.875 of the jumbo_tron render target (PROVED OFFLINE by u5 and u6); each
    #: screen shows the band of it at the screen's own aspect (the middle rows, where the play is)
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

    def _board(self):
        """The board over midfield: a black housing, the two sideline screens (they face the stands along the field) and
        the two end screens, all on the live feed at their own aspect, the LED ring under it and the four cables up to the
        roof."""
        q = self.p["board"]
        m = self.meshes.setdefault("att_board", Mesh("att_board"))
        self.markers["jumbo"] = []
        self.board_frames = []
        W, H, Dp = q["side_w"], q["side_h"], q["depth"]
        y0 = q["bottom"]
        c = np.array([0.0, y0 + H / 2, 0.0])
        m.box("att_black", c, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (Dp / 2, H / 2 + 0.4, W / 2 + 0.6), uvscale=0.1, bottom=True)
        (U0, U1), (V0, V1) = self.board_crop(W / H)
        for sx in (1.0, -1.0):
            face = np.array([sx, 0.0, 0.0])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
            fc = c + face * (Dp / 2 + 0.05)
            hw, hv = right * (W / 2), np.array([0.0, H / 2, 0.0])
            m.quad("jumbo_tron", fc - hw - hv, fc + hw - hv, fc + hw + hv, fc - hw + hv, (U0, V1), (U1, V1), (U1, V0), (U0, V0),
                   facing=lambda p_, f=face: f)
            self.markers["jumbo"].append(tuple(fc))
            self.board_frames.append(dict(centre=fc - hv, right=right, face=face, width=W, height=H))
        (u0, u1), (v0, v1) = self.board_crop(q["end_w"] / q["end_h"])
        for sz in (1.0, -1.0):
            face = np.array([0.0, 0.0, sz])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
            fc = c + face * (W / 2 + 0.65) + np.array([0.0, -H / 2 + q["end_h"] / 2 + 0.6, 0.0])
            hw, hv = right * (q["end_w"] / 2), np.array([0.0, q["end_h"] / 2, 0.0])
            m.quad("jumbo_tron", fc - hw - hv, fc + hw - hv, fc + hw + hv, fc - hw + hv, (u0, v1), (u1, v1), (u1, v0), (u0, v0),
                   facing=lambda p_, f=face: f)
        # the LED ring round the housing's bottom edge
        ring = [(Dp / 2 + 0.1, -(W / 2 + 0.7)), (Dp / 2 + 0.1, W / 2 + 0.7), (-(Dp / 2 + 0.1), W / 2 + 0.7),
                (-(Dp / 2 + 0.1), -(W / 2 + 0.7)), (Dp / 2 + 0.1, -(W / 2 + 0.7))]
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(ring[:-1], ring[1:])])])
        m.grid("LIGHT_att_ribbon", [[(x, y0 - 0.4, z) for x, z in ring], [(x, y0 + 1.0, z) for x, z in ring]],
               [[(s / 12.0, 0.5) for s in L], [(s / 12.0, 0.0) for s in L]], facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
        # the cables from the housing's top corners to the roof
        for sx in (1.0, -1.0):
            for sz in (1.0, -1.0):
                a = np.array([sx * Dp / 2 * 0.8, y0 + H + 0.4, sz * W / 2 * 0.8])
                b = np.array([sx * self.p["arches"]["x"] * 0.9, self.roof_height(sx * self.p["arches"]["x"] * 0.9, sz * W / 2), sz * W / 2])
                t = np.array([0.0, 0.0, q["cable"]])
                m.quad("att_steel", a - t, a + t, b + t, b - t, (0, 1), (1, 1), (1, 0), (0, 0),
                       facing=lambda p_, f=np.array([sx, 0.0, 0.0]): f)

    # -- the facade and the glass end walls -----------------------------------------------------------------------
    def _facade(self):
        """The curtain wall on the OSM outline, leaning outward (Wikipedia, HKS: the glass walls tilt out), dark blue glass
        with its mullions over a stone base; the flat ends of the outline are the glass end walls (the end-zone doors)."""
        f = self.p["facade"]
        ring, _pos = self.facade_ring(160)
        R = list(ring) + [ring[0]]
        c = np.mean(ring, axis=0)
        push = f["height"] * math.tan(math.radians(f["lean"]))
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(R[:-1], R[1:])])])
        m = self.meshes.setdefault("att_facade", Mesh("att_facade"))
        bot = [(x, GRADE - 0.5, z) for x, z in R]
        mid = [(x, GRADE + f["base"], z) for x, z in R]
        topv = []
        for x, z in R:
            v = np.array([x, z]) - c
            v /= math.np_norm(v)
            topv.append((x + v[0] * push, GRADE + f["height"], z + v[1] * push))
        end_w = f["end_wall_w"] / 2

        def is_end(x, z):
            return abs(x) < end_w and abs(z) > 120.0

        def runs(pred):
            out, run = [], []
            for i in range(len(R)):
                if pred(*R[i]):
                    run.append(i)
                else:
                    if len(run) >= 2:
                        out.append(run)
                    run = []
            if len(run) >= 2:
                out.append(run)
            return out
        outward = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        m.grid("att_stone", [bot, mid], [[(s / 10.0, 1.0) for s in L], [(s / 10.0, 0.0) for s in L]], facing=outward)
        for run in runs(lambda x, z: not is_end(x, z)):
            m.grid("att_facade", [[mid[j] for j in run], [topv[j] for j in run]],
                   [[(L[j] / (4 * f["mullion_every"]), 1.0) for j in run], [(L[j] / (4 * f["mullion_every"]), 0.0) for j in run]],
                   facing=outward)
        # the end walls (the end-zone doors, 120 ft of glass): outside, glass from the plaza to the roof's edge; inside,
        # the glass seen over the top Party Pass deck from the field (bright by day behind the decks: the 2010 full view)
        eave_q = self.p["roof"]
        for run in runs(is_end):
            hi = [(topv[j][0], eave_q["eave"] + eave_q["depth"], topv[j][2]) for j in run]
            m.grid("LIGHT_att_endglass", [[mid[j] for j in run], hi],
                   [[(L[j] / 18.0, 1.0) for j in run], [(L[j] / 18.0, 0.0) for j in run]], facing=outward)
            floor = self.end_floor
            lo = [(topv[j][0] * 0.998, floor, topv[j][2] * 0.998) for j in run]
            hi_in = [(x * 0.998, y, z * 0.998) for x, y, z in hi]
            m.grid("LIGHT_att_endglass", [hi_in, lo],
                   [[(L[j] / 18.0, 0.0) for j in run], [(L[j] / 18.0, 1.0) for j in run]],
                   facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))

    # -- outside --------------------------------------------------------------------------------------------------
    def _exterior(self):
        fp = footprint()
        ring, _pos = self.facade_ring(72)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("att_plaza", Mesh("att_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= math.np_norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(10.0), grow(34.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("att_plaza", rings, [uv(r) for r in rings], facing=up)
        # beyond the plaza, the shared environment kit (st3, 2026-09-28: the lots with their cars, the roads, grass,
        # trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band); its eyes: the flyover's
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        self.env_counts = env.dress(self, VENUE, grade=GRADE, keep_out=[plaza], inner=plaza,
                                    eyes=env.shot_eyes(att_shots()))


def build(venue=VENUE, params=None):
    return ATT(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "att_seat_front": ("att_seat_front", CLASS_OPAQUE), "att_seat_mid": ("att_seat_mid", CLASS_OPAQUE),
    "att_seat_back": ("att_seat_back", CLASS_OPAQUE), "att_deck": ("att_deck", CLASS_OPAQUE),
    "att_concrete": ("att_concrete", CLASS_OPAQUE), "att_wall": ("att_wall", CLASS_OPAQUE),
    "att_rail": ("att_rail", CLASS_ALPHA),
    "LIGHT_att_ribbon": ("LIGHT_att_ribbon", CLASS_OPAQUE), "LIGHT_att_glass": ("LIGHT_att_glass", CLASS_OPAQUE),
    "LIGHT_att_concourse": ("LIGHT_att_concourse", CLASS_OPAQUE), "att_portal": ("att_portal", CLASS_OPAQUE),
    "att_dark": ("att_dark", CLASS_OPAQUE), "att_black": ("att_black", CLASS_OPAQUE),
    "att_roof_under": ("att_roof_under", CLASS_OPAQUE), "att_panels": ("att_panels", CLASS_OPAQUE),
    "att_roof_top": ("att_roof_top", CLASS_OPAQUE), "att_roof_edge": ("att_roof_edge", CLASS_OPAQUE),
    "att_truss": ("att_truss", CLASS_ALPHA), "att_steel": ("att_steel", CLASS_OPAQUE),
    "LIGHT_att_lights": ("LIGHT_att_lights", CLASS_OPAQUE),
    "att_facade": ("att_facade", CLASS_OPAQUE), "LIGHT_att_endglass": ("LIGHT_att_endglass", CLASS_OPAQUE),
    "att_stone": ("att_stone", CLASS_OPAQUE),
    "att_plaza": ("att_plaza", CLASS_OPAQUE), "att_ground": ("att_ground", CLASS_OPAQUE),
    "att_asphalt": ("att_asphalt", CLASS_OPAQUE), "att_road": ("att_road", CLASS_OPAQUE),
    "att_building": ("att_building", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night. Under the closed roof the bowl is lit the same in
#: every time of day (the record stays indoor: the game's indoor rig lights the players at any hour), a little warmer
#: in the afternoon; outside, the sun by day and the lit glass at night.
BASE = {
    "att_seat_front": (208, 204, 196), "att_seat_mid": (208, 204, 196), "att_seat_back": (208, 204, 196),
    "att_deck": (206, 202, 194), "crowd": (222, 216, 210), "att_concrete": (206, 200, 192), "att_wall": (230, 224, 220),
    "att_rail": (220, 216, 210),
    "LIGHT_att_ribbon": (255, 255, 255), "LIGHT_att_glass": (200, 196, 255), "LIGHT_att_concourse": (214, 208, 255),
    "att_portal": (150, 146, 140), "att_dark": (190, 184, 176), "att_black": (170, 166, 160),
    "att_roof_under": (212, 206, 120), "att_panels": (236, 230, 110), "att_roof_top": (232, 222, 90),
    "att_roof_edge": (222, 212, 100), "att_truss": (200, 194, 120), "att_steel": (200, 194, 110),
    "LIGHT_att_lights": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    "att_facade": (214, 200, 110), "LIGHT_att_endglass": (236, 228, 255), "att_stone": (220, 206, 110),
    "att_plaza": (226, 210, 110), "att_ground": (220, 200, 70), "att_asphalt": (220, 204, 90), "att_road": (220, 204, 90),
    "att_building": (220, 204, 100),
}
SUN = {"d": (0.30, 0.85, 0.40), "a": (-0.60, 0.50, 0.62), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
#: rain and snow grey only what is outside: under the closed roof every weather looks dry (as SoFi's s23)
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"att_roof_top", "att_roof_edge", "att_facade", "att_stone", "att_plaza", "att_ground", "att_asphalt",
           "att_road", "att_building", "att_truss", "att_steel"}
INSIDE_LIGHT = 0.96


#: the live feed's vertex colour, the same in every light. The game copies its own previous frame (640 x 448) into the
#: jumbo_tron texture, and the screen draws that copy modulated by twice its vertex colour: in st2 lab 2 (2026-09-27,
#: PROVED IN GAME) the copy of the stands inside the AT&T board drew 2.0 to 2.3 times the stands themselves under the
#: bowl's vertex colour (245), so a screen that saw itself brightened on every pass and went solid white once it
#: filled the flyover's view (fly-029 to fly-034). At 116 the loop gain is about 1 (0.9 to 1.1 on that measurement):
#: the screen draws the picture as bright as the frame, and a screen in view of itself shows a steady nest of copies
#: instead of flooding white (retail's own screens: 204, 229, 255 under much smaller boards).
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
    out_side = mat in OUTSIDE
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif not out_side:
        f = np.full(n, INSIDE_LIGHT)                    # the bowl under the roof: the stadium's own light
    elif tod == "n":
        f = np.full(n, 1.0)
    else:
        sun = np.array(SUN[tod])
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.76 + 0.26 * nd) if tod == "d" else (0.64 + 0.45 * nd)
    tint = TINT[tod] if out_side or tod != "n" else (1.0, 1.0, 1.0)
    if weather in OVERCAST and out_side:
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat in ("att_roof_under", "att_panels") and tod == "n":
        # the membrane at night: no daylight through it, lit from below by the bowl (the night photos: a pale grey
        # underside over the lit bowl)
        out[:, 0] = 118; out[:, 1] = 122; out[:, 2] = 132
    if mat == "att_facade" and tod == "n":
        # the glass at night: lit from within, warm at the concourses (the 2009 night photo on Commons)
        k = np.clip((P[:, 1] - GRADE) / 30.0, 0, 1)
        out[:, 0] = np.clip(236 - 70 * k, 0, 255); out[:, 1] = np.clip(226 - 70 * k, 0, 255); out[:, 2] = np.clip(206 - 50 * k, 0, 255)
    if mat == "LIGHT_att_endglass" and tod == "n":
        out[:, 0] = 70; out[:, 1] = 84; out[:, 2] = 120            # the glass ends dark by night (outside is dark)
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


def adjust_digits(shape, sc, model):
    """The score and clock digits over each end screen of the board, on the housing's black end panel (the game's own
    digits: two strips, one per end); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    q = model.p["board"]
    strips = []
    for sz in (1.0, -1.0):
        face = np.array([0.0, 0.0, sz])
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
        centre = np.array([0.0, q["bottom"] + q["end_h"] + 3.6, sz * (q["side_w"] / 2 + 0.72)])
        strips.append(dict(centre=centre, right=right))
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
                wall_z = model.p["loop"]["zn"] if zs > 0 else model.p["loop"]["zs"]
                centre = np.array([side * 0.9 * zs, 2.7, zs * (wall_z - 0.08)])
                sm._place_quad(P, UV, quad, centre, np.array([-zs, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 0.75, 1.1)
            else:
                s_ = strips[n % 2]
                slot = sm.DIGIT_SLOTS.get(mname, 5)
                centre = s_["centre"] + s_["right"] * (-6.5 + slot * 1.3)
                sm._place_quad(P, UV, quad, centre, s_["right"], np.array([0.0, 1.0, 0.0]), 0.55, 0.95)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def flare_points(model):
    """The four flare markers: over the light ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT (300 m)
    up. The game draws a lens flare at every flare marker in view and xemu draws it through the canopy; the markers
    also place the night player shadows. u6's lab 5 (2026-09-24, PROVED IN GAME at SoFi): 300 m up, no flare discs in
    the flyover and short night shadows under the feet. Out of every AT&T Stadium shot too (test: Cameras)."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], sm.FLARE_HEIGHT, best[2]))
    return out


#: the field-level sponsor cloths: job u4's reviewed 2026 league sheet (``nfl2k5_modern_venues_2026.LEAGUE_ART``: the
#: eight defunct 2004 cloths as 2026 league type; Riddell, Gatorade and NFL.com kept) over the retail texture, carried
#: to each bundle's weather from the dry bundle as u4 carries it. The 2026 venue art cedes s07 to AT&T Stadium, so
#: without this the model's kept banners showed the 2004 SEGA cloth (lab 1 at night, 2026-09-25, PROVED IN GAME).
LEAGUE_BANNER = "banner_corp"


def dry_of(name):
    """The dry bundle of the same time of day (s03nr.iff -> s03nd.iff)."""
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
    """The AT&T Stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "att_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "att_digits", tmpl_shape)
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
        # 0x7F210 registers a light glow at every marker whose name holds "light", and the glow sprites draw through
        # the canopy: lab 1 (2026-09-25, PROVED IN GAME) showed a ring of them over the roof in the exterior shots, as
        # u6's lab 1 did at SoFi. The markers keep their records and positions but not the word (u6's fix).
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
    """(bundle bytes, info): the retail bundle with its stadium scene replaced by the AT&T Stadium model and its intro
    cameras rewritten when ``cameras`` gives the shots (s07 has no cityscape, as SoFi's s23). The stretch from the
    stadium chunk to the end of the cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    sb.require("cityscape" not in scenes, f"{filename}: s07 carries no cityscape; this bundle does")
    cam_chunk, cam_dec = mm._cameras_chunk(retail_bundle)
    sb.require(cam_chunk.offset == st.offset + 32 + st.stored_size, "intro cameras do not follow the stadium chunk")
    start = st.offset
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
    room = end - start - len(cam_out) - 32
    room -= room % 16
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, sm._chunk_span(retail_bundle, st), stored=room)
    stretch = chunk + cam_out
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
                     markers=len(sc.markers), stretch=[start, end], retail_system=st.system_bytes,
                     retail_video=st.video_bytes, vertices=sum(s.vertex_count for s in sc.shapes))


# ------------------------------------------------------------------------------------------------ the field

#: The field (Hellas Matrix turf, Wikipedia "AT&T Stadium"): the retail s07 field is turf, one flat colour quad between
#: the goal lines. The model paints the turf's light and dark 5-yard bands (u runs along the field once the quad's UVs
#: are remapped, in place), the turf outside the field of play, clears the retail TEXAS STADIUM marks, and lays the
#: Cowboys' 2026 end zones and midfield from the league project's art (u4's DAL folder: blue end zones with the silver
#: COWBOYS wordmark, the navy star at midfield), composited over clean turf. The surface word stays turf.
FIELD_ART = ART_DIR / "field"
GRASS_MATERIAL, OUTSIDE_MATERIAL = "color_premipped", "grass_outside_premipped"
STADIUM_LOGO = "Stadium_logo"
ENDZONE_TEXTURES = ("endzone_N_L", "endzone_N_M", "endzone_N_R")
#: the art root's keys: the north end's panels (endzone_N_*), the south end's (endzone_S_*, optional: the league project's
#: 2026 end-line stencils differ by end, k2 from the week 2 photos: IT TAKES ALL OF US north (photo 025), CHOOSE LOVE
#: south (photo 019)) and the midfield mark. The art keys name the real ends (north is +z here), not the retail
#: materials: the retail field lays its endzone_N_* panels at the south end (-z) and its endzone_S_* panels at the
#: north, both on the same three textures (PROVED OFFLINE from the nine retail fields), so ``paint_field`` places each
#: end's art by the panels' positions.
SOUTH_ENDZONE = ("endzone_S_L", "endzone_S_M", "endzone_S_R")
TEAM_FIELD = ("endzone_N_L", "endzone_N_M", "endzone_N_R", "center_logo") + SOUTH_ENDZONE


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
    """The turf quad between the goal lines: u from 0 at the north goal line to 1 at the south (retail: 0.5 to 1), in
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
    """{material: RGBA} of the Cowboys' field art in a league art root (``<root>/<team dir>/venue`` for prefix s07), or
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
    """The AT&T Stadium field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "att_grass.png")
    outside = _rgba(FIELD_ART / "att_grass_outside.png")
    for mat, art in ((GRASS_MATERIAL, grass), (OUTSIDE_MATERIAL, outside)):
        row = rows[mat]
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, _weather_look(a, weather), maximum=cap)
    clean = np.array(np.median(grass.reshape(-1, 4), axis=0), np.float32)

    def over_grass(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    # the retail field's TEXAS STADIUM marks by the sidelines at midfield: the 2026 field has none (the Dec 2025 and 2026
    # photos), so their texture is cleared (transparent: the overlay draws nothing)
    if STADIUM_LOGO in rows:
        row = rows[STADIUM_LOGO]
        ml.write_p8(out, system, row, np.zeros((int(row["height"]), int(row["width"]), 4), np.uint8), maximum=cap)
    team = dict(team or {})
    split = any(k in team for k in SOUTH_ENDZONE)
    detail = sm._half_detail if half else (lambda a: a)
    for mat, art in team.items():
        if mat in SOUTH_ENDZONE or (split and mat in ENDZONE_TEXTURES):
            continue
        row = rows[mat]
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        if mat in ENDZONE_TEXTURES:
            a = over_grass(a)
        ml.write_p8(out, system, row, detail(_weather_look(a, weather) if mat in ENDZONE_TEXTURES else a), maximum=cap)
    if split:
        split_endzones(out, rec, system, team, over_grass, weather, cap, detail=detail)
    remap_grass_uv(out, rec)
    return bytes(out)


def split_endzones(out, rec, system, team, over_grass, weather, cap, detail=lambda a: a):
    """Each end its own art on the retail panels' shared textures (u6's method at SoFi): every panel texture carries
    one end's art in its top half and the other end's in its bottom half, each panel's V (0 at the end line, 1 at the
    goal line) is squeezed into its half, half a texel in from the seam. The north art (endzone_N_*) goes on the panels
    that lie at +z, the south art (endzone_S_*, the north art where a part is missing) on those at -z."""
    ml = sm._ml()
    rows = ml.texture_rows(rec)
    g = sm._field_shape(rec, "A_grass_color")
    st0, st1 = sm._stream(g, 0), sm._stream(g, 1)
    _su, sv, _ou, ov = struct.unpack_from("<4f", out, g["record_offset"] + 0x30)
    for part in "LMR":
        mats = (f"endzone_N_{part}", f"endzone_S_{part}")
        north_art = team.get(f"endzone_N_{part}")
        south_art = team.get(f"endzone_S_{part}", north_art)
        if north_art is None:
            north_art = south_art
        sb.require(north_art is not None, f"the {part} end-zone panels have no art")
        row = rows[mats[0]]
        sb.require(rows[mats[1]]["index"] == row["index"], "the two ends' panels no longer share a texture")
        width, height = int(row["width"]), int(row["height"])
        half = height // 2
        ends = []
        for mat in mats:
            idx = sm._submesh_vertices(rec, out, g, mat)
            z = float(np.mean([struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i)[2] for i in idx]))
            ends.append((mat, idx, north_art if z > 0 else south_art))
        sb.require(len({art is north_art for _m, _i, art in ends}) == 2 or north_art is south_art,
                   "the two ends' panels do not lie at the two ends")
        halves = []
        for _mat, _idx, art in ends:
            a = sm._resample(art, width, half) if art.shape[:2] != (half, width) else art
            halves.append(detail(_weather_look(over_grass(a), weather)))
        ml.write_p8(out, system, row, np.vstack(halves), maximum=cap)
        pad = 0.5 / height
        for k, (_mat, idx, _art) in enumerate(ends):
            v0, v1 = k * 0.5 + pad, (k + 1) * 0.5 - pad
            for i in idx:
                at = st1["offset"] + st1["stride"] * i + 6
                v = min(1.0, max(0.0, round(struct.unpack_from("<h", out, at)[0] / 32767.0 * sv + ov, 3)))
                q = int(round((v0 + (v1 - v0) * v - ov) / sv * 32767.0))
                sb.require(-32767 <= q <= 32767, "the end-zone UV constant cannot hold the split")
                struct.pack_into("<h", out, at, q)


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s07 intro camera's channel carries (PROVED OFFLINE from the retail s07dd and s07ns intro
#: cameras, the same pattern as SoFi's s23): cameras 1, 3 and 5 carry every component; camera 2 only y, z and pitch (it
#: plays on x = 0 looking along -z); camera 4 all but x (it plays on x = 0). A component a channel lacks plays as 0.
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"y", "z", "pitch"}, {"x", "y", "z", "pitch", "yaw"},
                             {"y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the AT&T Stadium flyover, one shot per retail camera, each wanting 0 wherever its camera carries
#: nothing. 1: the exterior from the south-east plaza, the east glass wall under the arch; 2 (on the axis, looking west):
#: a crane rising in the east end zone toward the board; 3: the board from over the west end, panning; 4 (on the
#: axis): the approach from the east over the arches onto the dome; 5: field level in the west end zone, turning onto the
#: east end's glass wall, the Party Pass decks and the board.
_EXTERIOR = dict(eye=(170.0, 62.0, 250.0), target=(0.0, 40.0, 70.0), fov=36.0, rates=dict(x=-2.0, yaw=0.6))
_CRANE = dict(eye=(0.0, 10.0, 58.0), target=(0.0, 34.0, -40.0), fov=44.0, rates=dict(y=1.6, pitch=0.8))
#: 3 (st2 lab 2 fix, 2026-09-27): pass 1's sweep past the sideline screen filled 57 to 65 percent of the picture with
#: the live feed, which draws the game's own frame, so the screen fed on itself (fly-029 to fly-034 solid white). The
#: shot now pans slowly across the board from over the west end at its top's height (the feed about 21 percent of the
#: picture, test: Cameras), the dome's roof over it.
_BOARD = dict(eye=(5.0, 50.0, -55.0), target=(-1.0, 45.0, -6.0), fov=40.0, rates=dict(yaw=-1.5))
_APPROACH = dict(eye=(0.0, 150.0, 430.0), target=(0.0, 60.0, 0.0), fov=38.0, rates=dict(y=-3.0, z=-14.0, pitch=-0.8))
_FIELD_EAST = dict(eye=(10.0, 3.0, -50.0), target=(0.0, 30.0, 140.0), fov=44.0, rates=dict(yaw=2.5))
ATT_SHOTS = [_EXTERIOR, _CRANE, _BOARD, _APPROACH, _FIELD_EAST]


def att_shots():
    out = []
    for s, present in zip(ATT_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=att_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s07 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s07 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the AT&T Stadium stretch: from the stadium chunk to the end of the intro cameras."""
    ml = sm._ml()
    scenes = ml.bundle_scenes(bundle)
    cam, _dec = mm._cameras_chunk(bundle)
    return scenes["stadium"].offset, cam.offset + 32 + cam.stored_size


def build_all(source, *, workers=None, progress=None, names=None):
    """{name: (retail bundle, model bundle, info)} for the nine bundles (or ``names``), compiled in parallel."""
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers,
                                         progress=progress, label="AT&T Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field span

#: the field's palette ladder (the team's end zones and midfield mark compress worse than the retail turf)
#: the field's fitting ladder (u6's): the marks at full detail down to 64 colours, then at half detail from 256 colours
#: down, then full detail at the fewest colours. The snow fields have the smallest spans (s03ds: 91,968 bytes), and the
#: two ends' own end-line stencils (k2, 2026-09-25) cost a little more than one shared end zone.
FIELD_LADDER = ([(False, c) for c in (256, 128, 96, 64)] + [(True, c) for c in (256, 128, 96, 64, 48, 32)]
                + [(False, c) for c in (48, 32)])
#: the first pass tries only rungs estimated under 0.93 of the span (measured 2026-09-25: s03dd's full 256 at 0.947
#: missed, its 128 at 0.888 fit; s03ds's full 128 at 1.014 came out 1.095, its half-detail 64 at 0.888 fit)
FIELD_SKIP_FIRST = 0.93


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle: the AT&T Stadium field, graded by Modern colour when
    its settings are given (painted before the grade and compressed once, as SoFi, MetLife and the 2026 venue art do),
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
    # two passes: first the rungs the estimate gives a real chance (st's Highmark fields' VC-LZ streams ran 6 to 10 percent
    # over u6's estimate: each failed try costs the optimal encoder a minute or two), then u6's wider margin
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
    raise sb.ScneBuildError(f"{name}: the AT&T Stadium field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_att_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_att_receipt/v1"
BUILD_CAPTION = "AT&T Stadium for the Cowboys (experimental)"
HELP_TEXT = (
    "The Dallas Cowboys' AT&T Stadium (opened 2009), built as a new model for Cowboys home games in every time of day: the "
    "bowl with its club and suite levels and the tall upper deck, the Party Pass decks and the glass end walls, the "
    "centre-hung board over midfield with the live feed on its four screens, the dome closed over the field with its "
    "two arches, the glass facade and the site, and a new pregame flyover with exterior passes. The field is turf in "
    "5-yard bands with the 2026 venue art's Cowboys end zones and midfield when that option is on. The row reads AT&T "
    "Stadium, Arlington, TX; the roof stays closed (no rain or snow falls, as retail). The 2026 venue art leaves the "
    "Cowboys' packages to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "AT&T Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported AT&T Stadium pins schema")
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
    """retail / applied / foreign for the AT&T Stadium stretch of one of the nine bundles."""
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
    return Path(str(source) + ".att.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported AT&T Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s07 row."""
    from . import nfl2k5_att_venue as hv
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
        entry = archive.entries[hv.ROST_OUTER_INDEX]
        row = hv.rost_state(archive.read(entry.virtual_offset, entry.size))
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
    sb.require(state == ("applied" if enabled else "retail"), f"AT&T Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already AT&T Stadium)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Cowboys stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=att_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s07 to it): the AT&T Stadium field, stadium
    and cameras of the nine bundles, and the s07 row. The retail bundles come from ``retail_source``; the image's own
    bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the field is
    composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour still
    recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Cowboys end zones and midfield go onto the new
    field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_att_venue as hv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries AT&T Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"AT&T Stadium needs retail Cowboys packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="AT&T Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the AT&T Stadium bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], applied_sha256=sha(after),
                                            field=info.get("field"), system=info["system"], video=info["video"],
                                            fan_art=info.get("fan_art"))
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        receipt["rost"] = hv.apply_rost(archive)
    if new_colour is not None:
        new_colour["att"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after AT&T Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"AT&T Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("AT&T Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_att_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the AT&T Stadium stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st2-att.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST_HIGHMARK_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
