"""Highmark Stadium model (experimental): the Buffalo Bills' new Highmark Stadium (Orchard Park, opened 2026) built from
scratch as the stadium scene of venue record s03 (retail Ralph Wilson Stadium), all nine bundles (day, afternoon, night;
dry, rain, snow).

Job st (2026-09-25), on u5's builder and u6's SoFi methods. References (the Wikipedia article, the Populous and Dezeen
texts, OpenStreetMap, the ticketing seat map, the Commons photos and the Bills' 2026 galleries) are cited in the st
report. The scene:

* the open-air bowl in its four different stacks: west (the Bills' and press side), the 100 level, two suite levels,
  the VIP boxes, the 300 and the 400 level; east, the 100 level, the LED ribbon, the two 200-level club tiers with the
  loge band between them and the steep 400 level; north, the field-level club, the GA+ concourse 12 ft above the field,
  sections 121 to 125 and the 22-row 300 level under the video board; south, 38 rows, the 200 level and the 400 level;
  crowd billboards in the retail convention, cut at every aisle (u6's method), on a red and royal seat mosaic;
* the 360-degree canopy over the stands, rising from its inner edge to the facade and higher along the sidelines than
  at the ends, with the blue LED line and the floodlights under its inner edge and the light-glow and flare markers on
  it; the field stays open to the sky, the rain and the snow;
* the two end-zone video boards on the ``jumbo_tron`` material the game draws its live feed into (a crop of the feed at
  the board's own aspect, never stretched), their partner panels, and the Highmark Stadium sign over each;
* the facade on the OpenStreetMap outline: the dark iron-spot brick base, the colonnade of fins with grey perforated
  panels up to the canopy, the glass entrances at the north end and the corners, and the Highmark Stadium wordmark on
  each of its four aspects;
* outside: the plaza, the lawns, the parking lots and roads from OpenStreetMap, Abbott Road, and the old stadium's
  cleared site across it;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the boards), the markers and the materials the executable
  looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x plan west on the Bills' and press side; y up from the field; z along, +z the
north end zone toward azimuth 347 degrees) and centimetres in the game. EXPERIMENTAL and UNWITNESSED in game unless a
report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

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

OWNER = "nfl2k5_highmark_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_highmark_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s03"
VENUES = (VENUE,)
#: the field sits below the surrounding grade ("The Pit"); the concourses open at grade (DESIGN from the 2026 photos)
GRADE = 7.5
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

#: DESIGN, pass 1. The plan of the 100 level follows the ticketing seat map (metric at the lower bowl: 0.82 to 0.88 m
#: rows); the east wall line was measured on the Commons scrimmage photo (16.6 m off the east sideline at midfield, the
#: pose solved from the painted field); the tier stacks follow the photos and the seat map's row counts (sections
#: 101 to 151, 200 to 252, 300 to 346, 400 to 451); heights are fitted to the scrimmage photo's pose (a west 400-level
#: seat 38 m above the field about 40 m behind the west wall).
PARAMS = dict(
    loop=dict(xw=45.0, xe=41.0, zn=69.0, zs=69.0, R=19.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    #: per side: the field-level club (north: the field club and the GA+ concourse on its roof, 12 ft up), the 100 level,
    #: the tier over it (fascia with the LED ribbon), a glass band (east: the loge boxes; west: two suite levels), the
    #: tier over that, and the upper deck
    sides=dict(
        W=dict(club_h=0.0, club_d=0.0, low_d0=3.5, low_y0=1.6, low_rows=38, low_tread=0.84, low_rise0=0.26, low_rise1=0.44,
               t2_over=4.0, t2_rows=0, t2_rise=0.52, band_h=6.4, t3_rows=11, t3_rise=0.56, t3_over=1.0,
               up_d=38.0, up_y=35.0, up_rows=16, up_tread=0.80, up_rise=0.60),
        E=dict(club_h=0.0, club_d=0.0, low_d0=3.0, low_y0=1.6, low_rows=38, low_tread=0.84, low_rise0=0.26, low_rise1=0.44,
               t2_over=4.0, t2_rows=9, t2_rise=0.50, band_h=2.8, t3_rows=9, t3_rise=0.52, t3_over=1.0,
               up_d=35.0, up_y=28.5, up_rows=30, up_tread=0.80, up_rise=0.555),
        N=dict(club_h=3.7, club_d=10.5, low_d0=11.5, low_y0=4.3, low_rows=12, low_tread=0.90, low_rise0=0.42, low_rise1=0.50,
               t2_over=1.0, t2_rows=22, t2_rise=0.64, band_h=0.0, t3_rows=0, t3_rise=0.56, t3_over=1.0,
               up_d=40.0, up_y=27.5, up_rows=18, up_tread=0.80, up_rise=0.60),
        S=dict(club_h=0.0, club_d=0.0, low_d0=3.0, low_y0=1.6, low_rows=38, low_tread=0.84, low_rise0=0.26, low_rise1=0.44,
               t2_over=4.0, t2_rows=9, t2_rise=0.50, band_h=0.0, t3_rows=0, t3_rise=0.56, t3_over=1.0,
               up_d=36.0, up_y=24.5, up_rows=19, up_tread=0.80, up_rise=0.58),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=5.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the canopy: its inner edge (d from the wall line; height above the field, sidelines and ends) and the height of its
    #: outer edge at the facade (it rises outward; higher along the sidelines than at the ends: Wikipedia, Populous)
    canopy=dict(inner_d_side=24.0, board_lead=1.0, inner_y_side=62.0, inner_y_end=52.0, outer_y_side=52.0,
                outer_y_end=47.0, depth=2.2, end_depth=8.5, points=96, led_every=12.0),
    boards=dict(width=38.5, height=11.2, panel_w=4.0, sign_w=26.0, sign_h=6.5, gap_half=26.5),
    lights=dict(every=2, drop=1.4, w=4.4, h=2.2),
    facade=dict(base=10.0, fin_every=6.2, panel_h=12.5, portal_w=64.0, portal_h=30.0),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


# ------------------------------------------------------------------------------------------------ the model

class Highmark(sm.SoFi):
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

    # -- the section: four stacks, blended round the corners ------------------------------------------------------
    def section(self, lp):
        p = self.p
        g = lambda key: _side_blend(lp, key, p)  # noqa: E731
        out = {}
        # the north end's field club under the GA+ concourse (glass front at the wall, its roof the concourse floor)
        club_h, club_d = g("club_h"), g("club_d")
        if club_h > 0.3:
            out["club"] = (0.4, p["wall"]["height"], club_h - 0.6)
            out["club_frame"] = (0.38, club_h - 0.6, club_h)
            out["club_roof"] = (0.4, max(0.5, club_d), club_h)
        # the 100 level
        rows = int(round(g("low_rows")))
        d, y = g("low_d0"), g("low_y0")
        if club_h > 0.3 and y - club_h > 0.05:
            out["gaplus_front"] = (club_d, club_h, y - 0.02)
        lower = [(d, y)]
        r0, r1, tread = g("low_rise0"), g("low_rise1"), g("low_tread")
        for i in range(rows):
            t = i / max(1, rows - 1)
            d += tread
            y += r0 + (r1 - r0) * t * t
            lower.append((d, y))
        out["lower"] = lower
        # the tier over the 100 level: its fascia carries the LED ribbon
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
        # the glass band (east: the loge boxes over the 200 level; west: the two suite levels)
        bh = g("band_h")
        yb = t2[-1][1] + 0.3
        db = t2[-1][0] + 1.0
        if bh > 0.2:
            out["band"] = (db, yb, yb + bh)
            out["band_floor"] = (t2[-1][0], db, t2[-1][1])
        ytop = yb + bh if bh > 0.2 else t2[-1][1]
        # the tier over the band (east: the upper 200 level; west: the 300 level)
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
        # the upper deck: its front where the side's stack puts it, cantilevered over the tiers below (the stacked
        # design: the scrimmage photo's angles put the east upper deck's front near 28 m and its top rows near 44 m);
        # never lower than 2.5 m over the last row of the tier it overhangs
        du = g("up_d")
        yu = max(g("up_y"), prev[-1][1] + 2.5 - max(0.0, prev[-1][0] - du) * g("up_rise") / g("up_tread"))
        out["up_fascia"] = (du, yu, yu + fh)
        # the upper deck's underside follows its rake, 1.4 m under the rows, back to the tier below's back wall
        slope = g("up_rise") / g("up_tread")
        dback = max(prev[-1][0] + 0.5, du + 0.5)
        yback = yu + (dback - du) * slope - 1.4 * (1.0 if dback > du + 2.0 else 0.0)
        yback = max(yback, prev[-1][1] + 2.2)
        out["back3"] = (dback, prev[-1][1], yback - 0.02)
        out["up_soffit_slope"] = ((du + 0.02, yu), (dback, yback))
        rowsu = int(round(g("up_rows")))
        if lp.end > 0.99 and abs(lp.x - (p["loop"]["xw"] - p["loop"]["xe"]) / 2) < p["boards"]["gap_half"]:
            rowsu = 0                   # the video board stands in the upper deck's gap at each end (seat map: no 422-424)
        # the upper deck never reaches the facade: where the OSM outline pulls in (the north-west corner), it loses
        # its back rows so its rim walk stays a metre inside
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
        # the rim walk stops a metre inside the facade (the OSM outline is not a rounded rectangle: it pulls in at
        # the north-west corner)
        walk_end = min(d + 0.3 + rim["walk"], self.facade_depth(lp) - 1.0)
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
            self.prefix = f"hm_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "hm"
        self._canopy(loop, secs)
        self._lights()
        self._boards(loop, secs)
        west = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(west)["upper"][4]
        self.nosebleed = self.at(west, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._exterior()
        return self

    def mesh(self, name):
        if name.startswith("hm_bowl_"):
            name = getattr(self, "prefix", "hm_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats: every tier fades from red at the front rows to royal at the back ------------------------------------
    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
        """u6's seating surface every ``seats.rows_per_grid`` rows (u one repeat per section, the steps under every aisle),
        laid in three bands by depth in the tier: red front rows, a mixed middle, royal back rows (the 2026 construction
        and video-board photos: every section of every level runs red at the bottom to royal at the top)."""
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
        for mat, i0, i1 in (("hm_seat_front", 0, a), ("hm_seat_mid", a, b), ("hm_seat_back", b, len(ks) - 1)):
            if i1 > i0:
                m.grid(mat, pts[i0:i1 + 1], uvs[i0:i1 + 1], facing=up_toward_field)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("hm_bowl_a")
        wall = p["wall"]["height"]
        m.grid("hm_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        # the north club: glass front, its roof (the GA+ concourse floor) and the step up to the 100 level
        self._band(m, "LIGHT_hm_glass", loop, secs, "club", 0.0, 1.0, u_per_m=1 / 8.0)
        # the club's white frame: a band over the glass and the players' tunnel at the north end's centre (the 2026
        # drone photos: a long white-framed glass front behind the north apron, the tunnel mouth in the middle)
        for lp, sec in zip(loop, secs):
            if "club" in sec and abs(lp.nz - 1.0) < 1e-6 and abs(lp.x) < 4.0:
                c = np.array(self.at(lp, 0.0, 0.0))
                m.box("hm_concrete", c + np.array([0.0, 2.4, -1.2]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (7.0, 2.4, 1.2),
                      uvscale=0.2)
                m.quad("hm_portal", c + np.array([-5.0, 0.0, -2.45]), c + np.array([5.0, 0.0, -2.45]),
                       c + np.array([5.0, 3.6, -2.45]), c + np.array([-5.0, 3.6, -2.45]), (0, 1), (1, 1), (1, 0), (0, 0),
                       facing=lambda p_: np.array([0.0, 0.0, -1.0]))
                break
        self._band(m, "hm_concrete", loop, secs, "club_frame", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m, "hm_concrete", loop, secs, "club_roof", up)
        self._band(m, "LIGHT_hm_concourse", loop, secs, "gaplus_front", 0.0, 1.0, u_per_m=1 / 8.0)
        # the apron from the wall top (or the club roof) to the first row
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) if "club" not in sec else self.at(lp, sec["club_roof"][1], sec["club_roof"][2])
                    for lp, sec in zip(loop, secs)]
        m.grid("hm_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "hm_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_hm_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        # the ribbon tier
        m2 = self.mesh("hm_bowl_b")
        self._ledge(m2, "hm_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_hm_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        t2 = [sec["t2"] for sec in secs]
        if max(len(x) for x in t2) > 1:
            self._rows_surface(m2, "hm_seat", loop, t2, 2)
            self._crowd(m2, loop, t2)
        self._band(m2, "LIGHT_hm_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "hm_concrete", loop, secs, "band_floor", up)
        # the third tier and the wall behind it up to the upper deck
        m3 = self.mesh("hm_bowl_c")
        self._band(m3, "LIGHT_hm_ribbon", loop, secs, "t3_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        t3 = [sec["t3"] for sec in secs]
        if max(len(x) for x in t3) > 1:
            self._rows_surface(m3, "hm_seat", loop, t3, 2)
            self._crowd(m3, loop, t3)
        self._band(m3, "LIGHT_hm_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        # the upper deck
        m4 = self.mesh("hm_bowl_d")
        # the upper deck's sloped underside (from its front fascia back to the tier below's back wall)
        run = [(lp, sec["up_soffit_slope"]) for lp, sec in zip(loop, secs)]
        m4.grid("hm_concrete", [[self.at(lp, *a) for lp, (a, b) in run], [self.at(lp, *b) for lp, (a, b) in run]],
                [[(lp.s / 8.0, 0.0) for lp, _ in run], [(lp.s / 8.0, 0.4) for lp, _ in run]], facing=down)
        self._band(m4, "hm_dark", loop, secs, "up_fascia", 0.0, 1.0, u_per_m=1 / 8.0)
        upd = [sec["upper"] for sec in secs]
        self._rows_surface(m4, "hm_seat", loop, upd, 2)
        self._crowd(m4, loop, upd)
        self._portals(m4, loop, secs, "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk
        m4.grid("LIGHT_hm_concourse", [[self.at(lp, sec["rim"][0], sec["rim"][1]) for lp, sec in zip(loop, secs)],
                                       [self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 1.0) for lp in loop], [(lp.s / 8, 0.0) for lp in loop]], facing=toward_field)
        m4.grid("hm_concrete", [[self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)],
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
            m.quad("hm_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    # -- the canopy ----------------------------------------------------------------------------------------------
    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

    def canopy_inner(self, n):
        """The canopy's inner edge: the wall line pushed out by ``inner_d``, resampled to n points by angle from the
        field centre, with its height (higher along the sidelines than at the ends)."""
        q = self.p["canopy"]
        loop = self.loop
        # over the ends the inner edge runs along the video board's face, so the Highmark Stadium sign sits on the
        # fascia right over the board and the canopy covers the upper deck only (lab 1 against the video-board test
        # photos 008, 010 and 015, 2026-09-25: the roof's edge passes just above each board). DESIGN from the photos.
        d_end = {}
        for end in (1, -1):
            k = max(range(len(loop) - 1), key=lambda i: end * loop[i].z - abs(loop[i].x) * 0.01)
            d_end[end] = self.secs[k]["up_fascia"][0] + 2.5 - q["board_lead"]
        dd = lambda lp: d_end[1 if lp.z > 0 else -1] + (q["inner_d_side"] - d_end[1 if lp.z > 0 else -1]) * lp.side  # noqa: E731
        pts = [(lp.x + lp.nx * dd(lp), lp.z + lp.nz * dd(lp), lp) for lp in loop[:-1]]
        out = []
        for k in range(n):
            a = 2 * math.pi * k / n
            d = np.array([math.cos(a), math.sin(a)])
            best, bt = None, None
            for i in range(len(pts)):
                (x0, z0, l0), (x1, z1, l1) = pts[i], pts[(i + 1) % len(pts)]
                e = np.array([x1 - x0, z1 - z0])
                den = d[0] * (-e[1]) - d[1] * (-e[0])
                if abs(den) < 1e-12:
                    continue
                t = (x0 * (-e[1]) - z0 * (-e[0])) / den
                u = (d[0] * z0 - d[1] * x0) / den
                if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
                    best, bt = t, (l0, l1, u)
            l0, l1, u = bt
            side = l0.side * (1 - u) + l1.side * u
            out.append((d[0] * best, d[1] * best, side))
        return out

    def _canopy(self, loop, secs):
        q = self.p["canopy"]
        N = q["points"]
        inner = self.canopy_inner(N)
        outer_ring, _pos = self.facade_ring(4 * N)
        O = np.array(outer_ring)
        # the outer point for each inner point: along the same direction from the field centre
        outer = []
        for x, z, side in inner:
            a = math.atan2(z, x)
            angs = math.np_arctan2(O[:, 1], O[:, 0])
            j = int(np.argmin(np.abs(((angs - a + math.pi) % (2 * math.pi)) - math.pi)))
            outer.append((O[j][0], O[j][1], side))
        yi = [q["inner_y_end"] + (q["inner_y_side"] - q["inner_y_end"]) * s for _x, _z, s in inner]
        #: the fascia is deep over the ends (the sign's panel over each board), thin along the sidelines
        dep = [q["end_depth"] + (q["depth"] - q["end_depth"]) * min(1.0, s * 1.6) for _x, _z, s in inner]
        self.fascia_depth = dep
        yo = [q["outer_y_end"] + (q["outer_y_side"] - q["outer_y_end"]) * s for _x, _z, s in outer]
        self.canopy_edge = [(x, y, z) for (x, z, _s), y in zip(inner, yi)]
        self.canopy_bottom = [(x, y - d, z) for (x, z, _s), y, d in zip(inner, yi, dep)]
        close = lambda L: L + [L[0]]  # noqa: E731
        rows_top, rows_under, uvs = [], [], []
        self.under_rows = {}
        for f in (0.0, 0.25, 0.5, 0.75, 0.9, 1.0):
            rt, ru, uu = [], [], []
            for (ix, iz, _s), (ox, oz, _s2), y0, y1 in zip(close(inner), close(outer), close(yi), close(yo)):
                x, z = ix + (ox - ix) * f, iz + (oz - iz) * f
                y = y0 + (y1 - y0) * math.pow(f, 0.8)
                rt.append((x, y + q["depth"] * (1 - f) * 0.4, z))
                ru.append((x, y - q["depth"] * (1 - 0.6 * f), z))
                uu.append((math.atan2(z, x) * 40.0, f * 6.0))
            rows_top.append(rt)
            rows_under.append(ru)
            uvs.append(uu)
            self.under_rows[f] = ru
        self.meshes.setdefault("hm_roof_top", Mesh("hm_roof_top")).grid("hm_roof_top", rows_top, uvs, facing=up)
        self.meshes.setdefault("hm_roof_under", Mesh("hm_roof_under")).grid("hm_roof_under", rows_under, uvs, facing=down)
        # the inner fascia: a black band from the underside's edge to the top's edge, facing the field
        fas = self.meshes.setdefault("hm_fascia", Mesh("hm_fascia"))
        top = [(x, y + q["depth"] * 0.4, z) for (x, z, _s), y in zip(close(inner), close(yi))]
        bot = [(x, y - d, z) for (x, z, _s), y, d in zip(close(inner), close(yi), close(dep))]
        fas.grid("hm_dark", [bot, top], [[(k / 4.0, 1.0) for k in range(len(top))], [(k / 4.0, 0.0) for k in range(len(top))]],
                 facing=toward_field)
        # the blue LED line along the fascia's bottom edge
        # the blue LED line: along the back of the underside, over the top concourse (the scrimmage photo: the line of
        # blue lights runs just above the upper deck's back), a little below the underside
        back = self.under_rows[0.9]
        led_t = [(x, y - 0.25, z) for x, y, z in back]
        led_b = [(x, y - 0.95, z) for x, y, z in back]
        # the underside between the deep fascia and the roof: a closure so the deep end panel reads as solid
        under_edge = [(x * 1.0, y - q["depth"], z) for (x, z, _s), y in zip(close(inner), close(yi))]
        fas.grid("hm_dark", [[(x * 1.002, y, z * 1.002) for x, y, z in bot], [(x * 1.03, y, z * 1.03) for x, y, z in under_edge]],
                 [[(k / 4.0, 1.0) for k in range(len(bot))], [(k / 4.0, 0.0) for k in range(len(bot))]], facing=down)
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(led_t[:-1], led_t[1:])])])
        fas.grid("LIGHT_hm_led", [led_b, led_t], [[(s / 4.0, 1.0) for s in L], [(s / 4.0, 0.0) for s in L]],
                 facing=lambda p_: toward_field(p_) + np.array([0.0, -0.5, 0.0]))
        # pass 5, the week 2 night photos (2026-09-17, 039 and 019): a row of blue LEDs along the fascia's bottom edge
        # all around (directly under the Highmark Stadium sign at the ends), and a second ring of them across the
        # underside, so the underside reads dark with blue light lines rather than one flat blue
        fl_b = [(x * 1.001, y + 0.1, z * 1.001) for x, y, z in bot]
        fl_t = [(x * 1.001, y + 0.7, z * 1.001) for x, y, z in bot]
        Lf = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(fl_b[:-1], fl_b[1:])])])
        fas.grid("LIGHT_hm_led", [fl_b, fl_t], [[(s_ / 4.0, 1.0) for s_ in Lf], [(s_ / 4.0, 0.0) for s_ in Lf]],
                 facing=toward_field)
        mid = self.under_rows[0.5]
        ring_t = [(x, y - 0.05, z) for x, y, z in mid]
        ring_b = [(x, y - 0.55, z) for x, y, z in mid]
        Lr = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(ring_t[:-1], ring_t[1:])])])
        fas.grid("LIGHT_hm_led", [ring_b, ring_t], [[(s_ / 4.0, 1.0) for s_ in Lr], [(s_ / 4.0, 0.0) for s_ in Lr]],
                 facing=lambda p_: toward_field(p_) + np.array([0.0, -0.5, 0.0]))
        # blue LED lines along the underside's trusses, from the inner edge outward (the 2026 photos, day and night)
        und = self.meshes.setdefault("hm_roof_leds", Mesh("hm_roof_leds"))
        per = L[-1]
        k = 0
        while k * q["led_every"] < per:
            sv = k * q["led_every"]
            j = int(np.searchsorted(L, sv, side="right") - 1)
            j = min(max(j, 0), len(inner) - 1)
            (ix, iz, _s), (ox, oz, _s2), y0, y1 = inner[j], outer[j], yi[j], yo[j]
            a = np.array([ix, y0 - q["depth"] - 0.05, iz]); b_ = np.array([ix + (ox - ix) * 0.7, 0.0, iz + (oz - iz) * 0.7])
            b_[1] = y0 + (y1 - y0) * math.pow(0.7, 0.8) - q["depth"] * (1 - 0.42) - 0.05
            t = np.array([-(oz - iz), 0.0, ox - ix]); t = t / math.np_norm(t) * 0.25
            und.quad("LIGHT_hm_led", a - t, a + t, b_ + t, b_ - t, (0, 1), (1, 1), (1, 0), (0, 0), facing=down)
            k += 1

    # -- the floodlights under the inner edge ----------------------------------------------------------------------
    def _lights(self):
        q = self.p["lights"]
        c = self.p["canopy"]
        m = self.meshes.setdefault("hm_lights", Mesh("hm_lights"))
        edge = self.under_rows[0.75]
        pts = []
        for k in range(0, len(edge) - 1, q["every"]):
            x, y, z = edge[k]
            n = np.array([x, 0.0, z]); n /= math.np_norm(n)
            ctr = np.array([x, y - q["drop"], z])
            along = np.array([-n[2], 0.0, n[0]])
            normal = -n * math.cos(math.radians(35)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(35))
            upv = np.cross(along, normal); upv = upv / math.np_norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
            m.quad("LIGHT_hm_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, nn=normal: nn)
            pts.append(tuple(ctr))
        self.light_points = pts

    # -- the video boards --------------------------------------------------------------------------------------------
    #: the live feed fills u 0 to 0.625, v 0 to 0.875 of the jumbo_tron render target (PROVED OFFLINE by u5 and u6); a
    #: board shows the band of it at the board's own aspect (the middle rows of the picture, where the play is)
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
        """A board over each end, centred on the field axis in the upper deck's gap, facing the field, with partner
        panels either side; the Highmark Stadium sign on the canopy's deep fascia above it (the 2026 photos: the sign on
        the dark fascia over each board, the board between the upper deck's corner blocks)."""
        q = self.p["boards"]
        m = self.meshes.setdefault("hm_boards", Mesh("hm_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        W, H = q["width"], q["height"]
        (U0, U1), (V0, V1) = self.board_crop(W / H)
        edge_b = np.array(self.canopy_bottom)
        for end in (1, -1):
            k = max(range(len(loop) - 1), key=lambda i: end * loop[i].z - abs(loop[i].x) * 0.01)
            lp, sec = loop[k], secs[k]
            back = sec["up_fascia"][0] + 2.5
            zc = lp.z + lp.nz * back
            j = int(np.argmin(np.abs(edge_b[:, 0]) + (edge_b[:, 2] * end < 0) * 1e6))
            fascia_bottom = edge_b[j][1]
            # the board hangs just under the fascia and its sign (photo 015: the sign right over the board, the board
            # on an open steel frame over the upper deck's gap); never below the upper deck's front
            y0 = max(fascia_bottom - 0.8 - H, sec["up_fascia"][1] + 0.3)
            face = np.array([0.0, 0.0, -float(end)])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
            c = np.array([0.0, y0, zc])
            hw = right * (W / 2)
            hv = np.array([0.0, H, 0.0])
            m.box("hm_dark", c + hv / 2 - face * 0.8, (right, (0, 1, 0), face), (W / 2 + q["panel_w"] + 0.6, H / 2 + 0.6, 0.7),
                  uvscale=0.1)
            yb = sec["up_fascia"][1]
            if y0 - 0.6 - yb > 0.3:
                # the frame under the board, down to the upper deck's front (the gap behind it stays hidden)
                hb = (y0 - 0.6 - yb) / 2
                m.box("hm_dark", np.array([0.0, yb + hb, zc]) - face * 0.8, (right, (0, 1, 0), face),
                      (W / 2 + q["panel_w"] + 0.6, hb, 0.7), uvscale=0.1)
            A, B = c - hw + face * 0.05, c + hw + face * 0.05
            m.quad("jumbo_tron", A, B, B + hv, A + hv, (U0, V1), (U1, V1), (U1, V0), (U0, V0), facing=lambda p_, f=face: f)
            for s_ in (-1, 1):
                pc = c + right * s_ * (W / 2 + q["panel_w"] / 2 + 0.2) + face * 0.05
                pw = right * (q["panel_w"] / 2)
                m.quad("LIGHT_hm_board_panel", pc - pw, pc + pw, pc + pw + hv, pc - pw + hv, (0, 1), (1, 1), (1, 0), (0, 0),
                       facing=lambda p_, f=face: f)
            # the sign on the fascia: its face is the fascia's own plane at the end (inner edge), centred on x = 0
            ez = edge_b[j][2]
            sw, sh = q["sign_w"], q["sign_h"]
            sy0 = fascia_bottom + 0.8
            sc = np.array([0.0, sy0, ez]) + face * 0.15
            sr = right * (sw / 2)
            svh = np.array([0.0, sh, 0.0])
            m.quad("hm_letters", sc - sr, sc + sr, sc + sr + svh, sc - sr + svh, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, f=face: f)
            self.markers["jumbo"].append((0.0, y0 + H / 2, zc))
            self.board_frames.append(dict(centre=c, right=right, face=face, width=W, height=H))

    # -- the facade ---------------------------------------------------------------------------------------------------
    def _facade(self):
        """The drum on the OSM outline: the dark lower band (brick plinth and concourse glass), the folded silver-grey
        panels up to the canopy's outer edge, the black portal of the main entrance at the north end with the white
        wordmark, glass entries at the four corners, and the charcoal wordmark on the other three aspects (the Bills'
        charging buffalo under it on the west, as the 2026 photos show)."""
        q, cq = self.p["facade"], self.p["canopy"]
        ring, _pos = self.facade_ring(240)
        R = list(ring) + [ring[0]]
        n = len(ring)

        def side_of(x, z):
            sa = abs(math.sin(math.atan2(x, z)))
            return math.pow(float(np.clip((sa - 0.5) / 0.4, 0, 1)), 2) if sa < 0.9 else 1.0
        tops = [cq["outer_y_end"] + (cq["outer_y_side"] - cq["outer_y_end"]) * side_of(x, z) for x, z in R]
        self.facade_tops = (R, tops)
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(R[:-1], R[1:])])])
        base_top = GRADE + q["base"]
        m = self.meshes.setdefault("hm_facade", Mesh("hm_facade"))
        facing = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        # the north portal spans the facade points within portal_w / 2 of the north end's centre line
        pw = q["portal_w"] / 2

        def in_portal(x, z):
            return z > 0 and abs(x) < pw

        def corner_entry(x, z):
            a = math.degrees(math.atan2(x, z))
            return any(abs(((a - c + 180) % 360) - 180) < 3.2 for c in (50.0, -50.0, 130.0, -130.0))

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
        bot = [(x, GRADE - 0.5, z) for x, z in R]
        mid = [(x, base_top, z) for x, z in R]
        topv = [(x, t, z) for (x, z), t in zip(R, tops)]
        for run in runs(lambda x, z: not in_portal(x, z) and not corner_entry(x, z)):
            m.grid("LIGHT_hm_base", [[bot[j] for j in run], [mid[j] for j in run]],
                   [[(L[j] / 12.0, 1.0) for j in run], [(L[j] / 12.0, 0.0) for j in run]], facing=facing)
        for run in runs(lambda x, z: corner_entry(x, z) and not in_portal(x, z)):
            m.grid("LIGHT_hm_entry", [[bot[j] for j in run], [mid[j] for j in run]],
                   [[(L[j] / 8.0, 1.0) for j in run], [(L[j] / 8.0, 0.0) for j in run]], facing=facing)
        for run in runs(lambda x, z: not in_portal(x, z)):
            m.grid("hm_facade", [[mid[j] for j in run], [topv[j] for j in run]],
                   [[(L[j] / q["fin_every"], (mid[j][1] - GRADE) / q["panel_h"]) for j in run],
                    [(L[j] / q["fin_every"], (topv[j][1] - GRADE) / q["panel_h"]) for j in run]], facing=facing)
        # the fins' lit edges: a warm white line down each fin seam between the plinth and the top band, standing just
        # proud of the drum (the week 2 night photo, 2026-09-17; by day the fins' bright metal edges)
        for kf in range(int(L[-1] // q["fin_every"]) + 1):
            s_ = kf * q["fin_every"]
            j = int(np.searchsorted(L, s_, side="right")) - 1
            if j < 0 or j >= n:
                continue
            t_ = (s_ - L[j]) / max(1e-9, L[j + 1] - L[j])
            x, z = (np.array(R[j]) * (1 - t_) + np.array(R[j + 1]) * t_)
            if in_portal(x, z) or corner_entry(x, z):
                continue
            tan = np.array(R[j + 1]) - np.array(R[j])
            tan /= max(1e-9, math.np_norm(tan))
            out_n = np.array([tan[1], -tan[0]])
            if math.np_matmul(out_n, np.array([x, z])) < 0:
                out_n = -out_n
            top = tops[j] * (1 - t_) + tops[j + 1] * t_
            y0, y1 = base_top + 3.0, top - 6.0
            c = np.array([x, 0.0, z]) + np.array([out_n[0], 0.0, out_n[1]]) * 0.15
            hw = np.array([tan[0], 0.0, tan[1]]) * 0.22
            face = np.array([out_n[0], 0.0, out_n[1]])
            m.quad("LIGHT_hm_finline", c - hw + [0, y0, 0], c + hw + [0, y0, 0], c + hw + [0, y1, 0], c - hw + [0, y1, 0],
                   (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)
        # the portal: a black frame standing 3 m proud of the drum, a recessed glass wall, the white wordmark above it
        pr = [j for j in range(n + 1) if in_portal(*R[j])]
        if len(pr) >= 2:
            ph = GRADE + q["portal_h"]
            out_ = [np.array([R[j][0], 0.0, R[j][1]]) * (1 + 3.0 / max(1.0, math.hypot(*R[j]))) for j in pr]
            inn_ = [np.array([R[j][0], 0.0, R[j][1]]) * (1 - 6.0 / max(1.0, math.hypot(*R[j]))) for j in pr]
            m.grid("hm_black", [[(p_[0], ph, p_[2]) for p_ in out_], [(topv[j][0], topv[j][1], topv[j][2]) for j in pr]],
                   [[(L[j] / 8.0, 1.0) for j in pr], [(L[j] / 8.0, 0.0) for j in pr]], facing=facing)
            m.grid("hm_black", [[(p_[0], GRADE - 0.5, p_[2]) for p_ in out_], [(p_[0], ph, p_[2]) for p_ in out_]],
                   [[(L[j] / 8.0, 1.0) for j in pr], [(L[j] / 8.0, 0.0) for j in pr]], facing=facing)
            m.grid("LIGHT_hm_entry", [[(p_[0], GRADE - 0.5, p_[2]) for p_ in inn_], [(p_[0], GRADE + 16.0, p_[2]) for p_ in inn_]],
                   [[(L[j] / 8.0, 1.0) for j in pr], [(L[j] / 8.0, 0.0) for j in pr]], facing=facing)
            m.grid("hm_black", [[(p_[0], GRADE + 16.0, p_[2]) for p_ in inn_], [(p_[0], ph - 1.0, p_[2]) for p_ in inn_]],
                   [[(L[j] / 8.0, 1.0) for j in pr], [(L[j] / 8.0, 0.0) for j in pr]], facing=facing)
            m.grid("hm_black", [[(p_[0], ph - 1.0, p_[2]) for p_ in inn_], [(p_[0], ph - 1.0, p_[2]) for p_ in out_]],
                   [[(L[j] / 8.0, 1.0) for j in pr], [(L[j] / 8.0, 0.0) for j in pr]], facing=down)
            zc = max(p_[2] for p_ in inn_)
            sc = np.array([0.0, GRADE + 17.5, zc + 0.3])
            sw, sh = 44.0, 11.0
            m2 = self.meshes.setdefault("hm_signs", Mesh("hm_signs"))
            m2.quad("hm_letters", sc - [sw / 2, 0, 0], sc + [sw / 2, 0, 0], sc + [sw / 2, sh, 0], sc + [-sw / 2, sh, 0],
                    (1, 1), (0, 1), (0, 0), (1, 0), facing=lambda p_: np.array([0.0, 0.0, 1.0]))
        # the charcoal wordmark (and the charging buffalo on the west) on the other three aspects
        sg = self.meshes.setdefault("hm_signs", Mesh("hm_signs"))
        for ang in (90.0, -90.0, 180.0):
            a = math.radians(ang)
            d = np.array([math.sin(a), math.cos(a)])
            i = int(np.argmax([x * d[0] + z * d[1] for x, z in ring]))
            x, z = ring[i]
            t = np.array(ring[(i + 1) % n]) - np.array(ring[(i - 1) % n])
            t /= math.np_norm(t)
            nrm = np.array([t[1], -t[0]])
            if math.np_matmul(nrm, d) < 0:
                nrm = -nrm
            face = np.array([nrm[0], 0.0, nrm[1]])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
            w, h = (46.0, 11.5) if abs(ang) == 90.0 else (40.0, 10.0)
            y0 = tops[i] - h - 5.0
            c = np.array([x, y0, z]) + face * 0.5
            sg.quad("hm_letters_out", c - right * w / 2, c + right * w / 2, c + right * w / 2 + [0, h, 0],
                    c - right * w / 2 + [0, h, 0], (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)
            if ang == 90.0:
                lw, lh = 20.0, 12.0
                lc = c - np.array([0.0, lh + 2.0, 0.0])
                sg.quad("hm_logo", lc - right * lw / 2, lc + right * lw / 2, lc + right * lw / 2 + [0, lh, 0],
                        lc - right * lw / 2 + [0, lh, 0], (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)

    # -- outside -----------------------------------------------------------------------------------------------------
    def _exterior(self):
        fp = footprint()
        ring, _pos = self.facade_ring(120)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("hm_plaza", Mesh("hm_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= math.np_norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(8.0), grow(22.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("hm_plaza", rings, [uv(r) for r in rings], facing=up)
        # beyond the plaza, the shared environment kit (st3, 2026-09-28): the lots with their cars, the roads, grass,
        # trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band; the old stadium's
        # cleared site stays this model's own (the kit leaves it alone)
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        keep = [plaza]
        rd = self.meshes.setdefault("hm_roads", Mesh("hm_roads"))
        old_ = fp.get("old_site")
        if old_:
            (ox, oz), (a_, b_) = old_["centre"], old_["half_axes"]
            keep.append([(ox + (a_ + 12.0) * math.cos(2 * math.pi * i / 24), oz + (b_ + 12.0) * math.sin(2 * math.pi * i / 24))
                         for i in range(24)])
        self.env_counts = env.dress(self, VENUE, grade=GRADE, keep_out=keep, inner=plaza,
                                    eyes=env.shot_eyes(highmark_shots()))
        # the old stadium's cleared site across Abbott Road
        old = fp.get("old_site")
        if old:
            (ox, oz), (a, b) = old["centre"], old["half_axes"]
            k = 40
            ring_o = [(ox + a * math.cos(2 * math.pi * i / k), GRADE + 0.08, oz + b * math.sin(2 * math.pi * i / k))
                      for i in range(k + 1)]
            ctr = [(ox, GRADE + 0.08, oz)] * (k + 1)
            rd.grid("hm_dirt", [ctr, ring_o], [[(ox / 30.0, oz / 30.0)] * (k + 1), [(x / 30.0, z / 30.0) for x, _y, z in ring_o]],
                    facing=up)


def build(venue=VENUE, params=None):
    return Highmark(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "hm_seat_front": ("hm_seat_front", CLASS_OPAQUE), "hm_seat_mid": ("hm_seat_mid", CLASS_OPAQUE),
    "hm_seat_back": ("hm_seat_back", CLASS_OPAQUE), "hm_concrete": ("hm_concrete", CLASS_OPAQUE), "hm_wall": ("hm_wall", CLASS_OPAQUE),
    "hm_black": ("hm_black", CLASS_OPAQUE), "LIGHT_hm_base": ("LIGHT_hm_base", CLASS_OPAQUE), "hm_logo": ("hm_logo", CLASS_ALPHA),
    "LIGHT_hm_ribbon": ("LIGHT_hm_ribbon", CLASS_OPAQUE), "LIGHT_hm_glass": ("LIGHT_hm_glass", CLASS_OPAQUE),
    "LIGHT_hm_concourse": ("LIGHT_hm_concourse", CLASS_OPAQUE), "hm_portal": ("hm_portal", CLASS_OPAQUE),
    "hm_dark": ("hm_dark", CLASS_OPAQUE), "hm_roof_top": ("hm_roof_top", CLASS_OPAQUE),
    "hm_roof_under": ("hm_roof_under", CLASS_OPAQUE), "LIGHT_hm_led": ("LIGHT_hm_led", CLASS_OPAQUE),
    "LIGHT_hm_lights": ("LIGHT_hm_lights", CLASS_OPAQUE), "hm_facade": ("hm_facade", CLASS_OPAQUE),
    "LIGHT_hm_finline": ("LIGHT_hm_finline", CLASS_OPAQUE),
    "hm_brick": ("hm_brick", CLASS_OPAQUE), "LIGHT_hm_entry": ("LIGHT_hm_entry", CLASS_OPAQUE),
    "hm_letters": ("hm_letters", CLASS_ALPHA), "hm_letters_out": ("hm_letters_out", CLASS_ALPHA),
    "hm_letters_back": ("hm_letters_back", CLASS_OPAQUE), "LIGHT_hm_board_panel": ("LIGHT_hm_board_panel", CLASS_OPAQUE),
    "hm_plaza": ("hm_plaza", CLASS_OPAQUE), "hm_ground": ("hm_ground", CLASS_OPAQUE), "hm_asphalt": ("hm_asphalt", CLASS_OPAQUE),
    "hm_dirt": ("hm_dirt", CLASS_OPAQUE), "hm_road": ("hm_road", CLASS_OPAQUE), "hm_building": ("hm_building", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "hm_seat_front": (212, 194, 190), "hm_seat_mid": (212, 194, 190), "hm_seat_back": (212, 194, 190),
    "crowd": (224, 204, 206), "hm_black": (200, 184, 150), "LIGHT_hm_base": (200, 184, 255), "hm_logo": (250, 236, 220), "hm_concrete": (206, 188, 176), "hm_wall": (230, 212, 214),
    "LIGHT_hm_ribbon": (255, 255, 255), "LIGHT_hm_glass": (190, 176, 255), "LIGHT_hm_concourse": (214, 196, 255),
    "hm_portal": (160, 150, 120), "hm_dark": (190, 176, 150), "hm_roof_top": (210, 192, 120),
    "hm_roof_under": (196, 178, 150), "LIGHT_hm_led": (255, 255, 255), "LIGHT_hm_lights": (255, 255, 255),
    "jumbo_tron": (255, 255, 255), "hm_facade": (214, 196, 118), "hm_brick": (220, 200, 120),
    "LIGHT_hm_finline": (214, 196, 255),
    "LIGHT_hm_entry": (210, 190, 255), "hm_letters": (255, 255, 255), "hm_letters_out": (250, 236, 200),
    "hm_letters_back": (40, 38, 34), "LIGHT_hm_board_panel": (255, 255, 255), "hm_plaza": (226, 206, 120),
    "hm_ground": (220, 196, 70), "hm_asphalt": (220, 200, 90), "hm_dirt": (220, 198, 90), "hm_road": (220, 200, 90),
    "hm_building": (220, 200, 100),
}
SUN = {"d": (0.30, 0.85, 0.40), "a": (-0.60, 0.50, 0.62), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.93, 0.86), "n": (0.97, 0.99, 1.03)}
#: open air: rain and snow bundles grey everything under the cloud (the field and the bowl included)
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"hm_roof_top", "hm_facade", "hm_brick", "hm_plaza", "hm_ground", "hm_asphalt", "hm_dirt", "hm_road",
           "hm_building", "hm_letters_out", "hm_black", "hm_logo"}
#: the canopy's LED line and the fins' lighting at night: Bills royal
NIGHT_BLUE = (30, 90, 255)


def canopy_occlusion(P, model):
    """Sky light under the canopy: a point under the roof (inside its inner edge ring in plan, below its underside)
    sees less sky the deeper it sits behind the inner edge. 1 in the open, down to 0.55."""
    q = model.p["canopy"]
    edge = np.array([(x, z) for x, _y, z in model.canopy_edge])
    r_edge = math.np_hypot(edge[:, 0], edge[:, 1])
    a_edge = math.np_arctan2(edge[:, 1], edge[:, 0])
    a = math.np_arctan2(P[:, 2], P[:, 0])
    r = math.np_hypot(P[:, 0], P[:, 2])
    idx = np.argmin(np.abs(((a[:, None] - a_edge[None, :] + math.pi) % (2 * math.pi)) - math.pi), axis=1)
    beyond = r - r_edge[idx]
    y_edge = np.array([y for _x, y, _z in model.canopy_edge])[idx]
    under = (beyond > 0) & (P[:, 1] < y_edge)
    depth = np.clip(beyond / 30.0, 0, 1)
    return np.where(under, 1.0 - 0.45 * depth, 1.0)


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
    if mat == "hm_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.55, f)
    tint = TINT[tod]
    if weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat == "hm_roof_under" and tod == "n":
        # the underside washed in Bills blue by its LED lines at night (the home-opener photos, 2026-09-17), a darker
        # navy since pass 5 so the LED rows read against it (lab 2 showed one flat royal band; photos 039 and 019)
        out[:, 0] = 46; out[:, 1] = 70; out[:, 2] = 190
    if mat == "hm_facade" and tod == "n":
        # the panels at night: lit from the plaza, fading up the drum, with a cool cast (the Family Circle night photo,
        # 2026-08-08: grey panels over the lit concourse glass)
        # and the week 2 night photo (2026-09-17): the drum reads dark between the lit fin edges
        k = np.clip((P[:, 1] - GRADE) / 50.0, 0, 1)
        out[:, 0] = np.clip(96 - 60 * k, 0, 255); out[:, 1] = np.clip(100 - 60 * k, 0, 255); out[:, 2] = np.clip(120 - 70 * k, 0, 255)
    return out


def _rgba(path):
    path = official.resolve_path(path)
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def _textures(venue, tod, weather):
    art = ART_DIR
    keys = list(dict.fromkeys(k for k, _c in MATERIALS.values() if not k.startswith("env_")))   # deterministic order
    out = {key: _rgba(art / f"{key}.png") for key in keys}
    out.update(env.textures(venue, tod, weather))
    return out


def adjust_digits(shape, sc, model):
    """The score and clock digits onto each board's left partner panel (the game's own digits: two strips, one per
    board); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    q = model.p["boards"]
    strips = []
    for b in model.board_frames:
        c, right, face = b["centre"], b["right"], b["face"]
        pc = c + right * -(b["width"] / 2 + q["panel_w"] / 2 + 0.2) + face * 0.12 + np.array([0.0, b["height"] * 0.22, 0.0])
        strips.append(dict(centre=pc, right=right))
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
                centre = np.array([-side * 0.9 * zs, 2.7, zs * (wall_z - 0.08)])
                sm._place_quad(P, UV, quad, centre, np.array([-zs, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 0.75, 1.1)
            else:
                s_ = strips[n % 2]
                slot = sm.DIGIT_SLOTS.get(mname, 5)
                centre = s_["centre"] + s_["right"] * (-2.9 + slot * 0.58)
                sm._place_quad(P, UV, quad, centre, s_["right"], np.array([0.0, 1.0, 0.0]), 0.25, 0.4)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def flare_points(model):
    """The four flare markers: over the light ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT (300 m)
    up. The game draws a lens flare at every flare marker in view and xemu draws it through the canopy; the markers
    also place the night player shadows. u6's lab 5 (2026-09-24, PROVED IN GAME at SoFi): 300 m up, no flare discs in
    the flyover and short night shadows under the feet. Out of every Highmark shot too (test: Cameras)."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], sm.FLARE_HEIGHT, best[2]))
    return out


#: the field-level sponsor cloths: job u4's reviewed 2026 league sheet (``nfl2k5_modern_venues_2026.LEAGUE_ART``: the
#: eight defunct 2004 cloths as 2026 league type; Riddell, Gatorade and NFL.com kept) over the retail texture, carried
#: to each bundle's weather from the dry bundle as u4 carries it. The 2026 venue art cedes s03 to Highmark Stadium, so
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
    """The Highmark stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "hm_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "hm_digits", tmpl_shape)
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
            occ = canopy_occlusion(P[idxs] / 100.0, model) if mesh.name.startswith("hm_bowl") else None
            C[idxs] = light(mat, P[idxs] / 100.0, N[idxs], tod, weather, outside=mat in OUTSIDE, occlusion=occ)
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
    """(bundle bytes, info): the retail bundle with its cityscape collapsed (the surroundings live in the stadium scene),
    its stadium scene replaced by the Highmark model and its intro cameras rewritten when ``cameras`` gives the shots.
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

#: The field (natural grass: Kentucky bluegrass on a heated base, Wikipedia "Highmark Stadium"): the retail s03 field is
#: turf, one flat colour quad between the goal lines. The model paints the bluegrass mown in 5-yard bands (u runs along
#: the field once the quad's UVs are remapped, in place), the grass outside the field of play, and the Bills' 2026 end
#: zones and midfield from the league project's art (the u1 BUF venue folder: red end zones with the white BILLS wordmark,
#: the AFC and NFL marks; the charging buffalo at midfield), composited over clean grass. The surface word stays turf
#: (main, 2026-09-25: the grass word needs the divots chunk; proposed separately).
FIELD_ART = ART_DIR / "field"
GRASS_MATERIAL, OUTSIDE_MATERIAL = "color_premipped", "grass_outside_premipped"
ENDZONE_TEXTURES = ("endzone_N_L", "endzone_N_M", "endzone_N_R")
#: the art root's keys: the north end's panels (endzone_N_*), the south end's (endzone_S_*, optional: the league project's
#: 2026 end-line stencils differ by end, k2 from the week 2 photos: IT TAKES ALL OF US north (photo 025), CHOOSE LOVE
#: south (photo 019)) and the midfield mark. The art keys name the real ends (north is +z here), not the retail
#: materials: the retail s03 field lays its endzone_N_* panels at the south end (-z) and its endzone_S_* panels at the
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
    """{material: RGBA} of the Bills' field art in a league art root (``<root>/<team dir>/venue`` for prefix s03), or
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
    """The Highmark field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "hm_grass.png")
    outside = _rgba(FIELD_ART / "hm_grass_outside.png")
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

#: The components each retail s03 intro camera's channel carries (PROVED OFFLINE from the nine retail intro_cameras
#: scenes, identical in all nine): camera 1 animates x, z and pitch in three segments and y and yaw in two (so, in
#: u6's writer, it holds its start); camera 2 has no pitch (it plays level); camera 3 has no z (it plays on z = 0);
#: camera 5 moves only its yaw. A component a channel lacks plays as 0 (u6, labs 2 and 3).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"}, {"x", "y", "pitch", "yaw"},
                             {"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the Highmark flyover, one shot per retail camera, each wanting 0 wherever its camera carries nothing.
#: 1 (a still: its channels have several segments): the exterior from the south-west, over the plaza, the west facade's
#: wordmark and the canopy; 2 (level: no pitch): a pan across the east stands from in front of the west 300 level;
#: 3 (on z = 0): the bowl from above the west side at midfield, turning from the east stands to the north board;
#: 4 (every component): the approach from the south, over the parking and the facade, onto the roof and into the bowl;
#: 5 (yaw only): field level in the south end zone, turning across the north end and its board.
_EXTERIOR = dict(eye=(190.0, 90.0, -250.0), target=(0.0, 28.0, 5.0), fov=34.0, rates={})
_PAN_EAST = dict(eye=(71.0, 33.0, 20.0), target=(-60.0, 26.0, 0.0), fov=40.0, rates=dict(z=-2.0, yaw=2.5))
_BOWL_ABOVE = dict(eye=(60.0, 72.0, 0.0), target=(-30.0, 0.0, -20.0), fov=44.0, rates=dict(pitch=1.5, yaw=4.0))
_APPROACH = dict(eye=(20.0, 120.0, -360.0), target=(0.0, 25.0, 0.0), fov=36.0, rates=dict(y=-3.0, z=14.0, pitch=-1.0))
_FIELD_NORTH = dict(eye=(15.0, 3.0, -48.0), target=(8.0, 26.0, 110.0), fov=44.0, rates=dict(yaw=-3.0))
HM_SHOTS = [_EXTERIOR, _PAN_EAST, _BOWL_ABOVE, _APPROACH, _FIELD_NORTH]


def highmark_shots():
    out = []
    for s, present in zip(HM_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=highmark_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s03 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s03 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the Highmark stretch: from the cityscape chunk to the end of the intro cameras."""
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
                                         workers=workers,
                                         progress=progress, label="Highmark Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field span

#: the field's palette ladder (the Bills' red end zones and the charging buffalo compress worse than the retail turf)
#: the field's fitting ladder (u6's): the marks at full detail down to 64 colours, then at half detail from 256 colours
#: down, then full detail at the fewest colours. The snow fields have the smallest spans (s03ds: 91,968 bytes), and the
#: two ends' own end-line stencils (k2, 2026-09-25) cost a little more than one shared end zone.
FIELD_LADDER = ([(False, c) for c in (256, 128, 96, 64)] + [(True, c) for c in (256, 128, 96, 64, 48, 32)]
                + [(False, c) for c in (48, 32)])
#: the first pass tries only rungs estimated under 0.93 of the span (measured 2026-09-25: s03dd's full 256 at 0.947
#: missed, its 128 at 0.888 fit; s03ds's full 128 at 1.014 came out 1.095, its half-detail 64 at 0.888 fit)
FIELD_SKIP_FIRST = 0.93


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle: the Highmark field, graded by Modern colour when
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
    # two passes: first the rungs the estimate gives a real chance (the Highmark fields' VC-LZ streams run 6 to 10 percent
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
    raise sb.ScneBuildError(f"{name}: the Highmark field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_highmark_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_highmark_receipt/v1"
BUILD_CAPTION = "Highmark Stadium for the Bills (experimental)"
HELP_TEXT = (
    "The Buffalo Bills' new Highmark Stadium (opened 2026), built as a new model for Bills home games in every time "
    "of day and weather: the steep stacked bowl with its red-to-royal seats, the canopy over the stands with its "
    "floodlights and blue LED lines, the two end-zone video boards with the live feed and the Highmark Stadium signs, "
    "the silver facade with the north portal, the parking and the old stadium's cleared site, and a new pregame flyover "
    "with exterior passes. The field is bluegrass mown in 5-yard bands with the 2026 venue art's Bills end zones (each end "
    "its own when the art carries a south set) and "
    "midfield when that option is on. The row reads Highmark Stadium, Orchard Park, NY; the field stays open to rain "
    "and snow. The 2026 venue art leaves the Bills' packages to it. Off in every preset; appearance in game is "
    "unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Highmark Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Highmark Stadium pins schema")
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
    """retail / applied / foreign for the Highmark stretch of one of the nine bundles."""
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
    return Path(str(source) + ".highmark.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Highmark Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s03 row."""
    from . import nfl2k5_highmark_venue as hv
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
    sb.require(state == ("applied" if enabled else "retail"), f"Highmark Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_highmark")
def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Highmark)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Bills stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=highmark_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_highmark")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s03 to it): the Highmark field, stadium,
    cameras and collapsed cityscape of the nine bundles, and the s03 row. The retail bundles come from
    ``retail_source``; the image's own bundles keep every other chunk (Modern colour's normal map and tint word). With
    Modern colour on, the field is composed before the colour grade and compressed once, and the colour receipt is
    updated so Modern colour still recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Bills end zones
    and midfield go onto the new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_highmark_venue as hv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Highmark Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Highmark Stadium needs retail Bills packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Highmark Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Highmark bundle changed size")
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
        new_colour["highmark"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Highmark Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Highmark Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Highmark Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_highmark_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Highmark stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st-highmark.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST_HIGHMARK_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
