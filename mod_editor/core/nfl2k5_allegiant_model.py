"""Allegiant Stadium model (experimental): the Las Vegas Raiders' Allegiant Stadium (Paradise, NV, opened 2020; MANICA and
HNTB) built from scratch as the stadium scene of venue record s20 (retail Network Associates Coliseum, Oakland), all
nine bundles (day, afternoon, night; dry, rain, snow).

Job st2 (2026-09-25), on u5's builder, u6's SoFi methods and st's Highmark, AT&T and Levi's models. References (the
Wikipedia article, OpenStreetMap, the Commons photos 2019 to 2024, the 2024 board facts from Sports Video Group) are cited
in the st2 report. The scene:

* the charcoal bowl in four stacks: both sidelines the 100 level, the club tier, the suites and the upper deck; the
  south end the same, shorter, under the main board; the north end the 100 level and a short club tier in front of the
  lanai; crowd billboards in the retail convention, cut at every aisle (u6's method); the ribbons on the fascias;
* the fixed ETFE roof over the whole building (bright panels on a white steel grid from below, a silver skin from
  above), the floodlights hung under it;
* the lanai at the north end: the tall glass wall facing the Strip (the Strip's towers stand beyond it), its black
  frame and the plain-type name over it, and the Al Davis memorial torch in front of it;
* the boards on the ``jumbo_tron`` material the game draws its live feed into (a crop of the feed at the picture's own
  aspect, never stretched): the south end's primary board between its stat panels (the game's digits on them) with the
  name over it, and the two north boards either side of the lanai;
* the black glass drum on the OpenStreetMap outline with its white light lines, the LED mesh on the east face toward
  I-15 and the plain-type name on the north and south faces;
* outside: the plazas, lots and roads (I-15, Russell Road), the neighbours, the Strip's towers from OpenStreetMap (the
  Luxor's pyramid, the Mandalay Bay) and the ranges round the valley on the horizon;
* kept from retail because the engine reads them: the sideline props (one flat piece of the away bench area nudged in
  from x 51.0, see ``nudge_props``), pylons, yard markers, the field-level banners (projected onto the new wall), the
  digit shapes (moved onto the south board's stat panels), the markers and the materials the executable looks up by
  name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x plan east-south-east; y up from the field; z along, +z the south end zone
toward azimuth 205 degrees: Levi's frame, so the Raiders' bench and the press box are on -x, where every retail stadium
keeps the home sideline props and s20 its press box) and centimetres in the game. The row's indoor word becomes 1 (the
roof is fixed). EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
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

OWNER = "nfl2k5_allegiant_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_allegiant_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s20"
VENUES = (VENUE,)
#: the plazas and the concourse gates sit above the field, which lies below the surrounding grade (DESIGN from the
#: exterior photos: the black drum rises about 60 m over the field, the roof about 76 m)
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

#: pass 2: the heights are measured on two solved photo poses (PROVED OFFLINE): the 2021 north-end photo (a00) puts the
#: lower bowl's ribbon at 17.2 m at the south end, the upper deck's front at 25.5 m under the board and its top rows at
#: 56 to 60 m in the corners; the 2022 Las Vegas Bowl photo (a02, 2.4 px rms) puts the north ribbon at 16.2 m and the
#: north club tier's top at 25.6 m, where the lanai's glass starts. The row counts and rises are DESIGN to reach them.
#: The south end's upper section is shallow: the 2022 photographer (a02) stood at 35.8 m, 111 m south of midfield with
#: a clear view north, and the 2021 south-west corner photographer (a01, the painted-line fit) sat at 37.9 m, 100 m
#: south; both sit just over a section rising 0.24 m a row from its front at 25.5 m (PROVED OFFLINE positions; the
#: rise is DESIGN to fit them).
#: DESIGN, pass 1. The wall line clears the retail s20 sideline props (they reach x -40.6 and z -68.7 on the home side;
#: on the away side one flat piece reaches x 51.0 and is nudged in to 46.4, see ``nudge_props``); the stacks follow the
#: 2021 to 2024 photos (Commons: the Vegas Kickoff Classic interiors, the 2022 Las Vegas Bowl, the torch): both
#: sidelines the 100 level, the club tier with the suites over it and the upper deck; the south end the same, shorter,
#: under the main board; the north end the 100 level and a short club tier in front of the lanai's glass (no upper deck
#: there: the corners' upper deck stops at the lanai's sides).
PARAMS = dict(
    loop=dict(xe=47.5, xw=41.8, zs=62.0, zn=69.5, R=20.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    sides=dict(
        W=dict(low_d0=3.0, low_y0=1.5, low_rows=28, low_tread=0.84, low_rise0=0.34, low_rise1=0.74,
               t2_over=3.0, t2_rows=10, t2_rise=0.60, band_h=7.0,
               up_d=37.0, up_y=33.5, up_rows=31, up_tread=0.84, up_rise=0.70, back_wall=2.4),
        E=dict(low_d0=2.5, low_y0=1.4, low_rows=28, low_tread=0.84, low_rise0=0.34, low_rise1=0.74,
               t2_over=3.0, t2_rows=10, t2_rise=0.60, band_h=5.0,
               up_d=35.0, up_y=31.5, up_rows=33, up_tread=0.84, up_rise=0.70, back_wall=2.4),
        N=dict(low_d0=3.0, low_y0=1.5, low_rows=24, low_tread=0.84, low_rise0=0.40, low_rise1=0.80,
               t2_over=3.0, t2_rows=9, t2_rise=0.72, band_h=0.0,
               up_d=33.0, up_y=28.0, up_rows=0, up_tread=0.84, up_rise=0.70, back_wall=2.4),
        S=dict(low_d0=3.0, low_y0=1.5, low_rows=26, low_tread=0.84, low_rise0=0.38, low_rise1=0.78,
               t2_over=3.0, t2_rows=7, t2_rise=0.60, band_h=2.5,
               up_d=32.0, up_y=25.0, up_rows=34, up_tread=0.84, up_rise=0.24, back_wall=0.9),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the fixed roof (Wikipedia: a translucent ETFE roof; OSM: 69 m tall, the dome 7 m of it): the dark steel ring round
    #: the outline, its underside 60 m at the outline rising to 66 m at 0.82 of the way out (the a00 and a02 poses: the
    #: ETFE starts at 65 to 69 m over both ends, the ring's dark underside is right over the lanai's header), then the ETFE
    #: dome to its crown; the top of the ring (the drum's top) and of the dome sit ``depth`` over them
    roof=dict(eave=60.0, ring_top=66.0, ring_rho=0.82, crown=72.0, power=0.55, rings=6, points=72, depth=3.0),
    #: the black glass drum (the exterior photos): its height over the plaza and the white light lines round it
    facade=dict(base=8.0, lines=(16.0, 29.0, 42.0, 52.0)),
    #: the lanai at the north end: the tall glass wall over the club tier facing the Strip, and the Al Davis torch (85 ft,
    #: Wikipedia) in front of it
    #: pass 2: the glass is the drum's north face (the North Entry photo: the curved glass in the black drum), along the
    #: outline's north curve; the 2022 Las Vegas Bowl photo, scaled by the end zone at that end, gives about 100 m by
    #: 24 m; the black header with the name over it
    #: a02's pose: the glass's top 46.1 m (45.8 to 47.1 across the curve), the header's top 54.7 m (it meets the ring's
    #: dark underside), the name's lowercase type from 48.4 m to 53 m and about 33 m wide (PROVED OFFLINE)
    lanai=dict(half_w=46.0, glass_w=100.0, glass_top=46.1, name_bottom=46.2, name_w=36.0, name_h=9.0),
    #: the torch's top 39.6 m on the field axis, 123 m north of midfield (a02's pose, where the ray through its top
    #: crosses x = 0; PROVED OFFLINE for the height, the depth rests on the torch standing on the axis)
    torch=dict(top=39.6, z=-123.0, radius=2.6, flame=4.5, sides=10),
    #: the boards (Sports Video Group, 2024-01-24: the south end's 12,250 sq ft primary board, the north end's two 5,978
    #: sq ft boards): the south board lies on the rays of the 2021 north-end photo's solved pose (a00; the painted-line
    #: fit agrees with the point fit within 1 m); at 12,250 sq ft it would stand at z 105, in front of the 2022 photo's
    #: camera (a02, z 111 in the south stand, with a clear view north), so it stands 116 m south on the same rays: 79.1 x
    #: 16 m, bottom 34 m, the name over it to 54.8 m (INFERRED depth; its outline in the a00 photo PROVED OFFLINE); the
    #: north pair triangulated on the 2022 photo's pose as mirror images: 38 x 14.6 m (555 m2, the
    #: published 5,978 sq ft), bottoms 37.0 m, centres x +-63.5 and z -97.6 over the corner seats, each turned 42
    #: degrees in toward the field (PROVED OFFLINE)
    boards=dict(south_w=79.1, south_h=16.0, south_z=116.0, south_bottom=34.0, north_w=38.0, north_h=14.6, feed=0.62,
                depth=3.0, sign_w=40.0, sign_h=4.2, south_wing=10.0, north_x=63.5, north_z=-97.6, north_bottom=37.0, north_yaw=42.0),
    #: the LED mesh on the east face toward I-15 (27,600 sq ft, 345 x 80 ft: Sports Video Group, Wikipedia)
    mesh=dict(w=105.0, h=24.0, y=16.0),
    lights=dict(every=2, w=4.4, h=2.2, drop=2.0),
    hills=dict(radius=3600.0, points=48),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


# ------------------------------------------------------------------------------------------------ the model

class Allegiant(sm.SoFi):
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
        """True on the north end straight in front of the lanai's glass."""
        return lp.w["N"] > 0.6 and abs(lp.x) < self.p["lanai"]["half_w"]

    def board_specs(self):
        """The three boards' footprints: centre (x, z), the unit vector along each board's width (x, z), its width, bottom
        and depth, and the unit vector its picture faces."""
        q = self.p["boards"]
        a = math.radians(q["north_yaw"])
        # the south board's housing runs on past its picture into the grey wings either side (the a00 photo), so the seats
        # stay low under the wings too
        out = [dict(c=(0.0, q["south_z"]), along=(1.0, 0.0), face=(0.0, -1.0), w=q["south_w"], bottom=q["south_bottom"],
                    depth=q["depth"], margin=q["south_wing"])]
        for s_ in (-1, 1):
            face = (-s_ * math.sin(a), math.cos(a))
            out.append(dict(c=(s_ * q["north_x"], q["north_z"]), along=(face[1], -face[0]), face=face, w=q["north_w"],
                            bottom=q["north_bottom"], depth=q["depth"], margin=1.0))
        return out

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

    def lanai_glass(self, lp):
        """True where the lanai's glass stands behind the club tier (the wall up to the roof stops there)."""
        return lp.w["N"] > 0.6 and abs(lp.x) < self.p["lanai"]["glass_w"] / 2 - 1.0

    # -- the section: four stacks, blended round the corners ------------------------------------------------------
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
            self.prefix = f"ag_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "ag"
        self._roof()
        self._lights()
        self._lanai(loop, secs)
        self._torch(loop, secs)
        self._boards(loop, secs)
        east = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(east)["upper"][4]
        self.nosebleed = self.at(east, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._exterior()
        return self

    def mesh(self, name):
        if name.startswith("ag_bowl_"):
            name = getattr(self, "prefix", "ag_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats: charcoal and black on every level, lighter grey scattered toward the back ------------------------
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
        for mat, i0, i1 in (("ag_seat_front", 0, a), ("ag_seat_mid", a, b), ("ag_seat_back", b, len(ks) - 1)):
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
            self._rows_surface(m, "ag_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("ag_bowl_a")
        wall = p["wall"]["height"]
        m.grid("ag_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("ag_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "ag_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_ag_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        m2 = self.mesh("ag_bowl_b")
        self._ledge(m2, "ag_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_ag_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_ag_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "ag_concrete", loop, secs, "band_floor", up)
        m4 = self.mesh("ag_bowl_d")
        self._band(m4, "LIGHT_ag_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("ag_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                    [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_ag_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk, and behind them the concourse levels up to the roof
        # (the building is enclosed: from inside, a dark concourse band closes the gap under the roof)
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            m4.grid("LIGHT_ag_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                           [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("ag_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 0.4) for lp in lps]], facing=up)
            # the wall from the walk up to the roof, everywhere but where the lanai's glass stands
            sub = []
            for lp, r in list(zip(lps, rims)) + [(None, None)]:
                if lp is not None and not self.lanai_glass(lp):
                    sub.append((lp, r))
                    continue
                if len(sub) >= 2:
                    tops = [self.roof_height(*self.at(q_, r_[3], 0.0)[::2]) - 0.3 for q_, r_ in sub]
                    m4.grid("ag_dark", [[self.at(q_, r_[3], r_[2]) for q_, r_ in sub],
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
            m.quad("ag_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    # -- the roof -------------------------------------------------------------------------------------------------
    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

    def _roof_rho(self, x, z):
        ring = self.__dict__.get("_eave_polar")
        if ring is None:
            pts, _pos = self.facade_ring(360)
            P = np.array(pts)
            ang = math.np_arctan2(P[:, 1], P[:, 0])
            order = np.argsort(ang)
            ring = (ang[order], math.np_hypot(P[:, 0], P[:, 1])[order])
            self._eave_polar = ring
        a, r = ring
        th = math.atan2(z, x)
        R = float(np.interp(th, a, r, period=2 * math.pi))
        return math.hypot(x, z) / R

    def roof_height(self, x, z):
        """The roof's underside over (x, z): the dark ring from the eave at the outline up to ``ring_top`` at ``ring_rho``,
        then the ETFE as a shallow dome to the crown."""
        q = self.p["roof"]
        rho = min(1.0, self._roof_rho(x, z))
        rr = q["ring_rho"]
        if rho >= rr:
            return q["eave"] + (q["ring_top"] - q["eave"]) * (1.0 - rho) / (1.0 - rr)
        dome = math.pow(max(0.0, 1.0 - math.pow(rho / rr, 2)), q["power"])
        return q["ring_top"] + (q["crown"] - q["ring_top"]) * dome

    def roof_top(self, x, z):
        """The roof's top over (x, z): flat over the ring (the drum's top), then ``depth`` over the ETFE."""
        q = self.p["roof"]
        if min(1.0, self._roof_rho(x, z)) >= q["ring_rho"]:
            return q["ring_top"] + q["depth"]
        return self.roof_height(x, z) + q["depth"]

    def _roof(self):
        """The fixed roof: from below, the ETFE's bright panels on the white steel grid (the 2021 and 2022 interiors); from
        above, the silver-white skin; its eave on the outline at the drum's top."""
        q = self.p["roof"]
        N, K = q["points"], q["rings"]
        ring, _pos = self.facade_ring(N)
        E = list(ring) + [ring[0]]
        rr = q["ring_rho"]
        # rows by the fraction of the way in: two bands across the ring, then K over the ETFE
        fs = [0.0, (1.0 - rr) / 2, 1.0 - rr] + [(1.0 - rr) + rr * k / K for k in range(1, K + 1)]
        rows_u, rows_t, uvs = [], [], []
        for f in fs:
            ring_u, ring_t, uv = [], [], []
            for x, z in E:
                px, pz = x * (1 - f), z * (1 - f * 0.985)
                y = self.roof_height(px, pz)
                ring_u.append((px, y, pz))
                ring_t.append((px, self.roof_top(px, pz), pz))
                uv.append((math.atan2(z, x) * 7.0, f * 3.0))
            rows_u.append(ring_u); rows_t.append(ring_t); uvs.append(uv)
        self.roof_rows = rows_u
        self.ring_row = 2
        und = self.meshes.setdefault("ag_roof_under", Mesh("ag_roof_under"))
        # the ring is the dark steel structure with its rigs over the stands (the 2021 and 2022 photos: a black ring
        # round the bright ETFE, right over the lanai's header and the south board's name)
        und.grid("ag_roof_rim", rows_u[:3], uvs[:3], facing=down)
        und.grid("ag_roof_under", rows_u[2:], uvs[2:], facing=down)
        top = self.meshes.setdefault("ag_roof_top", Mesh("ag_roof_top"))
        ks = [0, 2] + list(range(4, len(fs), 2)) + ([len(fs) - 1] if (len(fs) - 1) % 2 else [])
        top.grid("ag_roof_top", [[r[j] for j in list(range(0, len(r), 2)) + [len(r) - 1]] for r in (rows_t[i] for i in ks)],
                 [[u[j] for j in list(range(0, len(u), 2)) + [len(u) - 1]] for u in (uvs[i] for i in ks)], facing=up)

    def _lights(self):
        """Floodlights hung under the roof in a ring over the stands' front (the 2021 interiors: rows of lamps under the
        roof's inner rim); each lamp's centre joins ``light_points``."""
        q = self.p["lights"]
        m = self.meshes.setdefault("ag_lights", Mesh("ag_lights"))
        ring = self.roof_rows[self.ring_row]
        for k in range(0, len(ring) - 1, q["every"]):
            x, y, z = ring[k]
            n = np.array([x, 0.0, z]); n /= max(1e-9, math.np_norm(n))
            ctr = np.array([x, y - q["drop"], z])
            along = np.array([-n[2], 0.0, n[0]])
            normal = -n * math.cos(math.radians(55)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(55))
            upv = np.cross(along, normal); upv = upv / math.np_norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
            m.quad("LIGHT_ag_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, nn=normal: nn)
            self.light_points.append(tuple(ctr))

    # -- the lanai and the torch ------------------------------------------------------------------------------------
    def lanai_arc(self, n=15):
        """[(x, z)] of the lanai's glass along the outline's north curve (OSM), |x| up to half the glass width, 0.5 m
        inside the outline; the glass doors are the building's north face (the North Entry photo: the curved glass wall in
        the black drum)."""
        half = self.p["lanai"]["glass_w"] / 2
        ring, _pos = self.facade_ring(720)
        P = np.array([p_ for p_ in ring if p_[1] < -60.0 and abs(p_[0]) <= half + 8.0], float)
        P = P[np.argsort(P[:, 0])]
        xs = np.linspace(-half, half, n)
        zs = np.interp(xs, P[:, 0], P[:, 1]) + 0.5
        return [(float(x), float(z)) for x, z in zip(xs, zs)]

    def _lanai(self, loop, secs):
        """The lanai at the north end (Wikipedia: large retractable curtain-like windows facing the Strip; the torch and
        North Entry photos): the curved glass wall in the drum's north face, from the lanai deck behind the north club
        tier up to the black header with the name (plain type; the sunburst mark is never drawn), the header up to the
        roof's dark ring; inside the glass is clear (the Strip beyond it), outside it reads dark blue-grey; the deck from
        the club tier's top walk to the glass and dark side walls up to the roof."""
        q = self.p["lanai"]
        m = self.meshes.setdefault("ag_lanai", Mesh("ag_lanai"))
        mid = min(range(len(loop) - 1), key=lambda i: math.pow(loop[i].nz + 1, 2) + math.pow(loop[i].x / 30.0, 2))
        y0 = secs[mid]["rim"][2]
        y1 = q["glass_top"]
        arc = self.lanai_arc()
        x0, x1 = arc[0][0], arc[-1][0]
        hy = [self.roof_height(x, z) - 0.2 for x, z in arc]
        inward = lambda p_: np.array([-p_[0], 0.0, -p_[2]])  # noqa: E731
        outward = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        u = [(x - x0) / 10.0 for x, _z in arc]
        m.grid("LIGHT_ag_lanai", [[(x, y0, z) for x, z in arc], [(x, y1, z) for x, z in arc]],
               [[(uu, 1.0) for uu in u], [(uu, 0.0) for uu in u]], facing=inward)
        m.grid("ag_glass_out", [[(x, y0, z - 0.15) for x, z in arc], [(x, y1, z - 0.15) for x, z in arc]],
               [[(uu, 1.0) for uu in u], [(uu, 0.0) for uu in u]], facing=outward)
        m.grid("ag_black", [[(x, y1, z + 0.05) for x, z in arc], [(x, h, z + 0.05) for (x, z), h in zip(arc, hy)]],
               [[(uu, 1.0) for uu in u], [(uu, 0.0) for uu in u]], facing=inward)
        # the name on the header, inside, following the glass's curve
        zc = float(np.interp(0.0, [a for a, _b in arc], [b for _a, b in arc]))
        nw, nh, nb = q["name_w"], q["name_h"], q["name_bottom"]
        xs = np.linspace(-nw / 2, nw / 2, 9)
        zs = [float(np.interp(x, [a for a, _b in arc], [b for _a, b in arc])) + 0.35 for x in xs]
        m.grid("ag_letters", [[(x, nb, z) for x, z in zip(xs, zs)], [(x, nb + nh, z) for x, z in zip(xs, zs)]],
               [[(k / 8, 1.0) for k in range(9)], [(k / 8, 0.0) for k in range(9)]], facing=inward)
        # the deck from the club tier's top walk to the glass, and the side walls from it to the roof
        rim_pts = sorted((loop[i].x + loop[i].nx * secs[i]["rim"][3], loop[i].z + loop[i].nz * secs[i]["rim"][3])
                         for i in range(len(loop) - 1) if loop[i].z < 0 and loop[i].w["N"] > 0.3 and "rim" in secs[i])
        RX = np.array([p_[0] for p_ in rim_pts]); RZ = np.array([p_[1] for p_ in rim_pts])
        inner = [(x, y0 - 0.2, float(np.interp(x, RX, RZ))) for x, _z in arc]
        outer = [(x, y0 - 0.2, z + 0.2) for x, z in arc]
        m.grid("ag_concrete", [inner, outer], [[(x / 8.0, 0.0) for x, _z in arc], [(x / 8.0, 1.0) for x, _z in arc]], facing=up)
        for (xe, ze), (xi, _yi, zi), sgn in ((arc[0], inner[0], 1.0), (arc[-1], inner[-1], -1.0)):
            ytop = self.roof_height(xe, ze) - 0.3
            m.quad("ag_dark", (xe, y0 - 0.2, ze), (xi, y0 - 0.2, zi), (xi, ytop, zi), (xe, ytop, ze), (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, s_=sgn: np.array([s_, 0.0, 0.0]))
        self.lanai = dict(x0=x0, x1=x1, z=zc, y0=y0, y1=y1, header=min(hy), roof=self.roof_height(0.0, zc) - 0.4, arc=arc)

    def _torch(self, loop, secs):
        """The Al Davis memorial torch (85 ft, Wikipedia) on the lanai deck in front of the glass: a tall tapering black
        column with its silver lines, its flame at the top."""
        if not getattr(self, "lanai", None):
            return
        q = self.p["torch"]
        m = self.meshes.setdefault("ag_torch", Mesh("ag_torch"))
        la = self.lanai
        c = np.array([0.0, la["y0"], q["z"]])
        height = q["top"] - la["y0"]
        n = q["sides"]
        rows = []
        for k, (h, r) in enumerate(((0.0, q["radius"] * 1.3), (0.25, q["radius"] * 0.8), (0.75, q["radius"] * 0.9),
                                    (1.0, q["radius"] * 1.5))):
            rows.append([(c[0] + r * math.cos(2 * math.pi * j / n), c[1] + h * height, c[2] + r * math.sin(2 * math.pi * j / n))
                         for j in range(n + 1)])
        uv = [[(j / n, 1.0 - k / 3) for j in range(n + 1)] for k in range(4)]
        m.grid("ag_torch", rows, uv, facing=lambda p_, c=c: np.array([p_[0] - c[0], 0.0, p_[2] - c[2]]))
        top = c[1] + height
        for a in (0.0, math.pi / 2):
            d = np.array([math.cos(a), 0.0, math.sin(a)]) * (q["radius"] * 1.2)
            m.quad("LIGHT_ag_flame", c + [0, top - c[1], 0] - d, c + [0, top - c[1], 0] + d,
                   c + [0, top - c[1] + q["flame"], 0] + d * 0.4, c + [0, top - c[1] + q["flame"], 0] - d * 0.4,
                   (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, 0.0, 1.0]))
            m.quad("LIGHT_ag_flame", c + [0, top - c[1], 0] + d, c + [0, top - c[1], 0] - d,
                   c + [0, top - c[1] + q["flame"], 0] - d * 0.4, c + [0, top - c[1] + q["flame"], 0] + d * 0.4,
                   (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, 0.0, -1.0]))
        self.torch_top = top

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

    def _board(self, m, c, face, W, H, feed=None, frames=None):
        """One board: the black housing, the live picture (over ``feed`` of its width between two stat panels, or all of
        it), facing ``face``."""
        q = self.p["boards"]
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
        hv = np.array([0.0, H, 0.0])
        m.box("ag_black", c + hv / 2, (right, (0, 1, 0), face), (W / 2 + 0.6, H / 2 + 0.6, q["depth"] / 2), uvscale=0.1,
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
                m.quad("LIGHT_ag_board_panel", pc - ph, pc + ph, pc + ph + hv, pc - ph + hv, (0, 1), (1, 1), (1, 0),
                       (0, 0), facing=lambda p_, f=face: f)
                panels.append(pc)
        self.markers["jumbo"].append(tuple(fc + hv / 2))
        if frames is not None:
            frames.append(dict(centre=c, right=right, face=face, width=W, height=H, panels=panels,
                               panel_w=W * (1.0 - feed) / 2 if feed else 0.0))

    def _boards(self, loop, secs):
        """The south end's primary board over its upper deck (the stat panels either side of the picture, the game's
        digits on the left one, the plain-type name over it) and the two north boards either side of the lanai."""
        q = self.p["boards"]
        m = self.meshes.setdefault("ag_boards", Mesh("ag_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        zc = q["south_z"]
        H = q["south_h"]
        y0 = q["south_bottom"]
        face = np.array([0.0, 0.0, -1.0])
        self._board(m, np.array([0.0, y0, zc]), face, q["south_w"], H, feed=q["feed"], frames=self.board_frames)
        sw, sh = q["sign_w"], q["sign_h"]
        sy = y0 + H + 1.0
        m.box("ag_black", np.array([0.0, sy + sh / 2, zc]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (sw / 2 + 1.0, sh / 2 + 0.4, 0.6),
              uvscale=0.1)
        m.quad("ag_letters", (sw / 2, sy, zc - 0.7), (-sw / 2, sy, zc - 0.7), (-sw / 2, sy + sh, zc - 0.7), (sw / 2, sy + sh, zc - 0.7),
               (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, 0.0, -1.0]))
        for b in self.board_specs()[1:]:
            (cx, cz), (fx, fz) = b["c"], b["face"]
            face = np.array([fx, 0.0, fz])
            # the picture's plane through the measured centre; the housing's centre half its depth behind it
            c = np.array([cx, q["north_bottom"], cz]) - face * (q["depth"] / 2 + 0.05)
            self._board(m, c, face, q["north_w"], q["north_h"])

    # -- the facade ---------------------------------------------------------------------------------------------------
    def _facade(self):
        """The black glass drum on the outline (the exterior photos): dark glass from the plaza to the roof's eave with
        white light lines round it, the LED mesh on the east face toward I-15, and the plain-type name on the north and
        south faces."""
        q = self.p["facade"]
        top_y = self.p["roof"]["ring_top"] + self.p["roof"]["depth"]
        ring, _pos = self.facade_ring(160)
        R = list(ring) + [ring[0]]
        L = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(R[:-1], R[1:])])])
        m = self.meshes.setdefault("ag_facade", Mesh("ag_facade"))
        outward = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
        # the drum opens where the lanai's glass is its face (the glass doors are the building's north face toward the
        # Strip): between the deck and the glass's top the glass is the wall; below and above it the drum runs on
        la = getattr(self, "lanai", None)
        opening = lambda x, z: la is not None and z < 0 and la["x0"] - 0.5 <= x <= la["x1"] + 0.5  # noqa: E731
        vt = lambda y: 0.85 * (1.0 - (y - GRADE - q["base"]) / (top_y - GRADE - q["base"]))  # noqa: E731
        runs, run, kinds = [], [], []
        for j, (x, z) in enumerate(R):
            k_ = bool(opening(x, z))
            if run and k_ != kinds[-1]:
                runs.append((run + [j], kinds[-1]))
                run = []
            if not run:
                kinds.append(k_)
            run.append(j)
        if len(run) >= 2:
            runs.append((run, kinds[-1]))
        for run, is_open in runs:
            if is_open:
                bands = [(GRADE - 0.5, GRADE + q["base"], la["y0"]), (la["y1"], top_y)]
            else:
                bands = [(GRADE - 0.5, GRADE + q["base"], top_y)]
            for ys in bands:
                m.grid("ag_facade", [[(R[j][0], y, R[j][1]) for j in run] for y in ys],
                       [[(L[j] / 16.0, 1.0 if y < GRADE else vt(y)) for j in run] for y in ys], facing=outward)
        self.facade_opening = opening
        for run, is_open in runs:
            R2 = [R[j] for j in run[::2]] + ([R[run[-1]]] if (len(run) - 1) % 2 else [])
            L2 = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(R2[:-1], R2[1:])])])
            for h in q["lines"]:
                y = GRADE + h
                if is_open and la["y0"] - 0.6 <= y <= la["y1"]:
                    continue
                m.grid("LIGHT_ag_lines", [[(x * 1.002, y, z * 1.002) for x, z in R2], [(x * 1.002, y + 0.6, z * 1.002) for x, z in R2]],
                       [[(s / 8.0, 1.0) for s in L2], [(s / 8.0, 0.0) for s in L2]], facing=outward)
        # the LED mesh on the east face (toward I-15), a lit band following the outline
        me = self.p["mesh"]
        run = [(x, z) for x, z in R if x > 0 and abs(z) < me["w"] / 2]
        if len(run) >= 2:
            run.sort(key=lambda p_: p_[1])
            Lr = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(run[:-1], run[1:])])])
            y0 = GRADE + me["y"]
            # u runs from the south end of the band to its north end, as a reader on I-15 (east of it) sees it
            m.grid("LIGHT_ag_mesh", [[(x * 1.004, y0, z) for x, z in run], [(x * 1.004, y0 + me["h"], z) for x, z in run]],
                   [[(1.0 - s / Lr[-1], 1.0) for s in Lr], [(1.0 - s / Lr[-1], 0.0) for s in Lr]], facing=outward)
        sg = self.meshes.setdefault("ag_signs", Mesh("ag_signs"))
        w, h = 56.0, 9.3
        # the name on the south face of the drum, and on the north over the lanai's glass (the header's outer face)
        i = int(np.argmax([z - abs(x) * 0.2 for x, z in ring]))
        x, z = ring[i]
        c = np.array([0.0, GRADE + q["lines"][-1] - h - 1.5, z]) + np.array([0.0, 0.0, 0.6])
        face = np.array([0.0, 0.0, 1.0])
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
        sg.quad("ag_letters", c - right * w / 2, c + right * w / 2, c + right * w / 2 + [0, h, 0], c - right * w / 2 + [0, h, 0],
                (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)
        if la:
            # the name on the drum over the lanai's glass, following the outline's curve 0.6 m out
            P_ = np.array([p_ for p_ in ring if p_[1] < 0 and abs(p_[0]) < 40.0]); P_ = P_[np.argsort(P_[:, 0])]
            ww, hh = w * 0.7, h * 0.7
            yb = la["y1"] + (la["header"] - la["y1"] - hh) / 2
            xs = np.linspace(ww / 2, -ww / 2, 9)
            zs = [float(np.interp(x, P_[:, 0], P_[:, 1])) - 0.6 for x in xs]
            out = lambda p_: np.array([0.0, 0.0, -1.0])  # noqa: E731
            sg.grid("ag_letters", [[(x, yb, z_) for x, z_ in zip(xs, zs)], [(x, yb + hh, z_) for x, z_ in zip(xs, zs)]],
                    [[(k / 8, 1.0) for k in range(9)], [(k / 8, 0.0) for k in range(9)]], facing=out)

    # -- outside -----------------------------------------------------------------------------------------------------
    def _exterior(self):
        fp = footprint()
        ring, _pos = self.facade_ring(72)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("ag_plaza", Mesh("ag_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= math.np_norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(12.0), grow(36.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("ag_plaza", rings, [uv(r) for r in rings], facing=up)
        # beyond the plaza, the shared environment kit (st3, 2026-09-28): the lots with their cars, the roads, grass,
        # trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band (the Spring Mountains and
        # the ranges round the valley at their true elevation angles, which _hills drew by hand before); the Strip's
        # towers stay this model's own
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        strip = {b.get("way") for b in fp.get("strip", [])}
        self.env_counts = env.dress(self, VENUE, grade=GRADE, keep_out=[plaza], inner=plaza, exclude_ways=strip,
                                    block_max_height=60.0, eyes=env.shot_eyes(allegiant_shots()))
        self._strip()

    def _strip(self):
        """The Las Vegas Strip's towers beyond the lanai (OSM heights, 60 m and taller within 3.5 km): lit glass boxes,
        the Luxor's pyramid and the Mandalay Bay's gold (the view through the lanai, the torch photo)."""
        m = self.meshes.setdefault("ag_strip", Mesh("ag_strip"))
        for b in footprint().get("strip", []):
            P = [tuple(p) for p in b["points"]]
            if len(P) < 3:
                continue
            A = np.array(P, float)
            if float(np.max(np.abs(A[:, 0]))) < 130.0 and float(np.max(np.abs(A[:, 1]))) < 150.0:
                continue
            name = (b.get("name") or "").lower()
            h = float(b["height"])
            if "luxor" in name:
                c = A.mean(axis=0)
                half = math.sqrt(max(1.0, 0.5 * abs(float(math.np_dot(A[:, 0], np.roll(A[:, 1], 1)) - math.np_dot(A[:, 1], np.roll(A[:, 0], 1)))))) / 2
                apex = (c[0], GRADE + h, c[1])
                base = [(c[0] - half, GRADE, c[1] - half), (c[0] + half, GRADE, c[1] - half), (c[0] + half, GRADE, c[1] + half),
                        (c[0] - half, GRADE, c[1] + half)]
                for a_, b_ in zip(base, base[1:] + base[:1]):
                    m.quad("ag_pyramid", a_, b_, apex, apex, (0, 1), (1, 1), (0.5, 0), (0.5, 0),
                           facing=lambda p_, cc=(c[0], c[1]): np.array([p_[0] - cc[0], 0.2, p_[2] - cc[1]]))
                continue
            self._extrude(m, _min_rect(A), GRADE, GRADE + h, "LIGHT_ag_strip", "ag_concrete", uscale=1 / 30.0)

    def _hills(self):
        """The ranges round the valley on the horizon: the Spring Mountains to the west (highest), the McCullough Range
        to the south, the Frenchman and Sunrise mountains to the east (DESIGN, at their angular heights)."""
        q = self.p["hills"]
        m = self.meshes.setdefault("ag_hills", Mesh("ag_hills"))
        N = q["points"]
        ridge = np.random.default_rng(20)
        bot, top, uvb, uvt = [], [], [], []
        for k in range(N + 1):
            a = 2 * math.pi * (k % N) / N                 # game angle (atan2(z, x)); bearing = angle + 115 degrees
            bearing = (math.degrees(a) + 115.0) % 360.0

            def bump(c, w):
                return math.exp(-math.pow(((bearing - c + 180) % 360 - 180) / w, 2))
            h = 230.0 * bump(270.0, 45.0) + 130.0 * bump(90.0, 40.0) + 120.0 * bump(180.0, 35.0) + 90.0 * bump(0.0, 30.0) + 15.0
            h *= 0.85 + 0.3 * float(ridge.random())
            x, z = q["radius"] * math.cos(a), q["radius"] * math.sin(a)
            bot.append((x, GRADE - 2.0, z))
            top.append((x * 1.02, GRADE + h, z * 1.02))
            uvb.append((k / 4.0, 1.0))
            uvt.append((k / 4.0, 0.0))
        m.grid("ag_hills", [bot, top], [uvb, uvt], facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))


def _min_rect(A):
    """The minimum-area rectangle round a footprint (four corners, counter-clockwise): the Strip's towers drawn as boxes."""
    A = np.asarray(A, float)
    c = A.mean(axis=0)
    best = None
    for deg in range(0, 90, 2):
        a = math.radians(deg)
        u = np.array([math.cos(a), math.sin(a)]); v = np.array([-u[1], u[0]])
        pu, pv = math.np_matmul(A - c, u), math.np_matmul(A - c, v)
        area = np.ptp(pu) * np.ptp(pv)
        if best is None or area < best[0]:
            best = (area, u, v, pu.min(), pu.max(), pv.min(), pv.max())
    _a, u, v, u0, u1, v0, v1 = best
    return [tuple(c + u * a + v * b) for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def build(venue=VENUE, params=None):
    return Allegiant(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "ag_seat_front": ("ag_seat_front", CLASS_OPAQUE), "ag_seat_mid": ("ag_seat_mid", CLASS_OPAQUE),
    "ag_seat_back": ("ag_seat_back", CLASS_OPAQUE), "ag_concrete": ("ag_concrete", CLASS_OPAQUE),
    "ag_wall": ("ag_wall", CLASS_OPAQUE), "LIGHT_ag_ribbon": ("LIGHT_ag_ribbon", CLASS_OPAQUE),
    "LIGHT_ag_glass": ("LIGHT_ag_glass", CLASS_OPAQUE), "LIGHT_ag_concourse": ("LIGHT_ag_concourse", CLASS_OPAQUE),
    "ag_portal": ("ag_portal", CLASS_OPAQUE), "ag_dark": ("ag_dark", CLASS_OPAQUE), "ag_black": ("ag_black", CLASS_OPAQUE),
    "ag_roof_under": ("ag_roof_under", CLASS_OPAQUE), "ag_roof_top": ("ag_roof_top", CLASS_OPAQUE),
    "ag_roof_rim": ("ag_roof_rim", CLASS_OPAQUE),
    "LIGHT_ag_lights": ("LIGHT_ag_lights", CLASS_OPAQUE), "LIGHT_ag_lanai": ("LIGHT_ag_lanai", CLASS_ALPHA),
    "ag_glass_out": ("ag_glass_out", CLASS_OPAQUE),
    "ag_torch": ("ag_torch", CLASS_OPAQUE), "LIGHT_ag_flame": ("LIGHT_ag_flame", CLASS_ALPHA),
    "LIGHT_ag_board_panel": ("LIGHT_ag_board_panel", CLASS_OPAQUE), "ag_letters": ("ag_letters", CLASS_ALPHA),
    "ag_facade": ("ag_facade", CLASS_OPAQUE), "LIGHT_ag_lines": ("LIGHT_ag_lines", CLASS_OPAQUE),
    "LIGHT_ag_mesh": ("LIGHT_ag_mesh", CLASS_OPAQUE),
    "ag_plaza": ("ag_plaza", CLASS_OPAQUE), "ag_ground": ("ag_ground", CLASS_OPAQUE),
    "ag_asphalt": ("ag_asphalt", CLASS_OPAQUE), "ag_road": ("ag_road", CLASS_OPAQUE),
    "ag_building": ("ag_building", CLASS_OPAQUE), "LIGHT_ag_strip": ("LIGHT_ag_strip", CLASS_OPAQUE),
    "ag_pyramid": ("ag_pyramid", CLASS_OPAQUE), "ag_hills": ("ag_hills", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "ag_seat_front": (212, 206, 196), "ag_seat_mid": (212, 206, 196), "ag_seat_back": (212, 206, 196),
    "crowd": (222, 216, 210), "ag_concrete": (206, 200, 192), "ag_wall": (230, 224, 220),
    "LIGHT_ag_ribbon": (255, 255, 255), "LIGHT_ag_glass": (190, 186, 255), "LIGHT_ag_concourse": (214, 208, 255),
    "ag_portal": (160, 156, 150), "ag_dark": (190, 186, 180), "ag_black": (200, 196, 190),
    "ag_roof_under": (238, 226, 150), "ag_roof_top": (226, 208, 120), "LIGHT_ag_lights": (255, 255, 255),
    "ag_roof_rim": (200, 196, 150),
    "LIGHT_ag_lanai": (240, 226, 255), "ag_torch": (216, 210, 200), "LIGHT_ag_flame": (255, 255, 255),
    "ag_glass_out": (214, 196, 120),
    "LIGHT_ag_board_panel": (255, 255, 255), "jumbo_tron": (255, 255, 255), "ag_letters": (255, 255, 255),
    "ag_facade": (200, 186, 110), "LIGHT_ag_lines": (240, 230, 255), "LIGHT_ag_mesh": (255, 255, 255),
    "ag_plaza": (226, 206, 120), "ag_ground": (224, 204, 70), "ag_asphalt": (220, 200, 90), "ag_road": (220, 200, 90),
    "ag_building": (220, 200, 100), "LIGHT_ag_strip": (214, 200, 255), "ag_pyramid": (190, 176, 60),
    "ag_hills": (236, 214, 40),
}
#: the sun over Paradise, NV (DESIGN): by day high in the south (bearing 180: game angle 65 degrees, +x and +z), in the
#: afternoon low in the west-south-west (bearing 250: game angle 135 degrees)
SUN = {"d": (0.21, 0.87, 0.45), "a": (-0.62, 0.50, 0.62), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
#: the rain and snow bundles only tint the outside (indoors under the fixed roof; the row's indoor word is 1)
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"ag_roof_top", "ag_facade", "ag_glass_out", "LIGHT_ag_lines", "LIGHT_ag_mesh", "ag_plaza", "ag_ground", "ag_asphalt", "ag_road",
           "ag_building", "LIGHT_ag_strip", "ag_pyramid", "ag_hills"}
#: inside the dome the light is the stadium's own: one level for every surface, whatever the sun outside (AT&T's rule)
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
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif not outside:
        f = np.full(n, INSIDE_LIGHT)
    elif tod == "n":
        f = np.full(n, 1.0)
    else:
        sun = np.array(SUN[tod])
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.76 + 0.26 * nd) if tod == "d" else (0.64 + 0.45 * nd)
    if mat == "ag_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    if outside and weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat == "ag_roof_under" and tod == "n":
        # the ETFE at night: the black sky through it, the white steel grid lit from below (DESIGN)
        out[:, 0] = 92; out[:, 1] = 94; out[:, 2] = 104
    if mat == "ag_facade" and tod == "n":
        # the black glass at night: a faint glow from the concourses behind it
        k = np.clip((P[:, 1] - GRADE) / 60.0, 0, 1)
        out[:, 0] = np.clip(58 - 30 * k, 0, 255); out[:, 1] = np.clip(60 - 30 * k, 0, 255); out[:, 2] = np.clip(70 - 30 * k, 0, 255)
    if mat in ("ag_hills", "ag_pyramid") and tod == "n":
        out[:, 0] = 18; out[:, 1] = 20; out[:, 2] = 30
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
    back in along x until it ends there (Allegiant's east apron is narrower than Oakland's: one flat piece of the away
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


#: the away bench area's pieces end here (metres, +x): one flat piece reached x 51.0 in Oakland (PROVED OFFLINE)
PROP_LIMIT_X = 46.4


def flare_points(model):
    """The four flare markers: over the roof's floodlight ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT
    (300 m) up (u6's lab 5, PROVED IN GAME at SoFi: no flare discs in the flyover, short night shadows under the feet).
    Out of every Allegiant shot too (test: Cameras)."""
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
    """The dry bundle of the same time of day (s20nr.iff -> s20nd.iff)."""
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
    """The Allegiant stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "ag_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "ag_digits", tmpl_shape)
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
    its stadium scene replaced by the Allegiant model and its intro cameras rewritten when ``cameras`` gives the shots.
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

#: The field (natural Bermuda grass on the tray that rolls in for Raiders games, Wikipedia): the retail s20 field is grass
#: already, one flat colour quad between the goal lines. The model paints it mown in 5-yard bands (u runs along the field
#: once the quad's UVs are remapped, in place), the grass outside the field of play, and the Raiders' 2026 end zones and
#: midfield from the league project's art (the u4 LV venue folder), composited over clean grass. The retail s20 field,
#: like s25's, gives each end its own three textures (endzone_N_* at -z, the north end here, endzone_S_* at +z; PROVED
#: OFFLINE from the nine retail fields), so each end's art goes straight onto its own panels.
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
    """{material: RGBA} of the Raiders' field art in a league art root (``<root>/<team dir>/venue`` for prefix s20), or
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
    """The Allegiant field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "ag_grass.png")
    outside = _rgba(FIELD_ART / "ag_grass_outside.png")
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

#: The components each retail s20 intro camera's channel carries (PROVED OFFLINE from the nine retail intro_cameras
#: scenes): camera 1 all five (x and z move); camera 2 no pitch (it plays level; x, z and yaw move); camera 3 no z (it
#: plays on z = 0; yaw moves); camera 4 no x and no z (it rises at midfield: y, pitch and yaw move; it also carries
#: roll); camera 5 all five and roll (x, z, y, yaw and roll move). A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"}, {"x", "y", "pitch", "yaw"},
                             {"y", "pitch", "yaw", "roll"}, {"x", "y", "z", "pitch", "yaw", "roll"})

#: DESIGN, pass 1: the Allegiant flyover, one shot per retail camera.
#: 1: outside from the north-east, sliding past the black drum and the lanai with the Strip behind the camera;
#: 2 (level): outside from the south-west at the drum's mid-height, gliding east along the black glass and its lines;
#: 3 (on z = 0): from the east side at midfield, panning from the south board round to the lanai and the torch;
#: 4 (at midfield, rising): a crane over the centre of the field looking north at the lanai and the Strip through it;
#: 5: field level behind the south end zone, drifting north toward the torch and the lanai.
_OUTSIDE = dict(eye=(170.0, 60.0, -380.0), target=(0.0, 30.0, -40.0), fov=36.0, rates=dict(x=-7.0, z=6.0))
_PASS = dict(eye=(-250.0, 34.0, 280.0), target=(0.0, 34.0, 20.0), fov=40.0, rates=dict(x=9.0, z=-3.0, yaw=-0.8))
_PAN = dict(eye=(58.0, 46.0, 0.0), target=(-40.0, 34.0, 110.0), fov=44.0, rates=dict(yaw=-15.0))
_CRANE = dict(eye=(0.0, 10.0, 0.0), target=(0.0, 22.0, -100.0), fov=46.0, rates=dict(y=3.0, pitch=0.8, yaw=1.5))
_FIELD_SOUTH = dict(eye=(8.0, 2.5, 57.5), target=(0.0, 24.0, -120.0), fov=44.0, rates=dict(z=-3.0, yaw=1.0))
AG_SHOTS = [_OUTSIDE, _PASS, _PAN, _CRANE, _FIELD_SOUTH]


def allegiant_shots():
    out = []
    for s, present in zip(AG_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=allegiant_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s20 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s20 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the Allegiant stretch: from the cityscape chunk to the end of the intro cameras."""
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
                                         workers=workers, progress=progress, label="Allegiant Stadium"):
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
    """(field span of the same size, receipt) for one retail bundle: the Allegiant field, graded by Modern colour when its
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
    raise sb.ScneBuildError(f"{name}: the Allegiant field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_allegiant_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_allegiant_receipt/v1"
BUILD_CAPTION = "Allegiant Stadium for the Raiders (experimental)"
HELP_TEXT = (
    "The Las Vegas Raiders' Allegiant Stadium, built as a new model for Raiders home games: the charcoal bowl under the "
    "fixed ETFE roof, the lanai's glass wall at the north end with the Strip beyond it and the Al Davis torch in front, "
    "the south end's primary board and the two north boards with the live feed, the black glass drum with its light lines "
    "and the LED mesh toward I-15, the lots, the Strip's towers and the ranges round the valley, and a new pregame flyover "
    "with exterior passes. The field is natural grass mown in 5-yard bands with the 2026 venue art's Raiders end zones and "
    "midfield when that option is on. The row reads Allegiant Stadium, Las Vegas, NV and turns indoor (the roof is fixed: "
    "no rain or snow falls). The 2026 venue art leaves the Raiders' packages to it. Off in every preset; appearance in "
    "game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Allegiant Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Allegiant Stadium pins schema")
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
    """retail / applied / foreign for the Allegiant stretch of one of the nine bundles."""
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
    return Path(str(source) + ".allegiant.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Allegiant Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s20 row."""
    from . import nfl2k5_allegiant_venue as agv
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
    sb.require(state == ("applied" if enabled else "retail"), f"Allegiant Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Allegiant)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Raiders stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=allegiant_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s20 to it): the Allegiant field, stadium,
    cameras and collapsed cityscape of the nine bundles, and the s20 row. The retail bundles come from ``retail_source``;
    the image's own bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the
    field is composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour
    still recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Raiders end zones and midfield go onto the
    new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_allegiant_venue as agv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Allegiant Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Allegiant Stadium needs retail Raiders packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Allegiant Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Allegiant bundle changed size")
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
        new_colour["allegiant"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Allegiant Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Allegiant Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Allegiant Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_allegiant_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Allegiant stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st2-allegiant.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST2_ALLEGIANT_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
