"""Mercedes-Benz Stadium model (experimental): the Atlanta Falcons' Mercedes-Benz Stadium (Atlanta, opened 2017; HOK)
built from scratch as the stadium scene of venue record s01 (retail Georgia Dome), all nine bundles (day, afternoon,
night; dry, rain, snow).

Job st2 (2026-09-27), on u5's builder, u6's SoFi methods and st's Highmark, AT&T, Levi's and Allegiant models. References
(the Wikipedia article, OpenStreetMap, the Commons photos 2016 to 2025, the Falcons' 2025 bird's-eye galleries) are cited
in the st2 report. The scene:

* the red bowl in four stacks: both sidelines and the west end the 100 level, the 200 level with the suites behind
  glass over it and the tall 300 level; the east end the 100 and 200 levels under the window to the city; crowd
  billboards in the retail convention, cut at every aisle (u6's method); the LED ribbons on the fascias;
* the roof: the fixed roof's dark steel round the opening and the eight triangular panels of the pinwheel, closed (the
  record stays indoor), the floodlights round the opening's edge;
* the Halo (58 x 1,100 ft, Wikipedia) hung under the opening: the live picture on every other panel (the ``jumbo_tron``
  material the game draws its feed into, at the picture's own aspect) and the club graphics between them, the game's
  digits on the two graphics panels over the sidelines;
* the window to the city at the east end with downtown's towers beyond it, the tall column board at its side and the
  Mercedes-Benz star on its black panel under the glass;
* the facade on the OpenStreetMap outline (way 536744534): the glass band over the plaza and the leaning petals, metal
  and glass in turn, the star (the official vector) and the venue's sign (the wordmark of its own logo) on the petals
  where the building shows them; the plaza, downtown and Midtown's towers from OpenStreetMap; outside the plaza, the
  shared environment kit (nfl2k5_stadium_environment, st3): the lots with their cars, the roads, parks, water, trees
  and blocks from OpenStreetMap, the far ground to the haze and the horizon band inside the sky backdrop;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the Halo), the markers and the materials the executable
  looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

The record stays indoor (retail s01's word, the roof modelled closed) and turf (FieldTurf). Geometry is in metres here
(x across, +x the north sideline toward azimuth 349.5 degrees and -x the Falcons' south sideline, where every retail
stadium keeps the home props; y up from the field; z along, +z the east end zone under the window toward azimuth 79.5
degrees) and centimetres in the game. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

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

OWNER = "nfl2k5_mercedes_benz_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_mercedes_benz_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s01"
VENUES = (VENUE,)
#: the field sits below the plazas (DESIGN, the photos: the 100 level's back concourse opens toward the plazas)
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

# ------------------------------------------------------------------------------------------------ parameters

#: pass 2: heights measured on two solved photo poses (PROVED OFFLINE): the 2018 Peach Bowl from the north side's 300
#: level (m72: 20 yard-line and sideline crossings, 3.0 px rms) sits at 36.8 m, 42 m behind the north wall line, and puts
#: the south side's lower bowl top at 13 m, its ribbon at 17 m, the club glass up to 20.5 m and the 300 level's first
#: rows at 22 to 27 m; the 2018 Peach Bowl from the west end's 300 level on the axis (m69: goalposts and far corners, 2.9
#: px, then the painted-line fit; the posts' 30 ft uprights) sits at 36.5 m, 42 m behind the west wall line, and puts
#: the east end's stands' top at 21.7 m under the bridge. Rows and rises are DESIGN to reach them and to leave both
#: photographers standing just over their rows.
#: DESIGN, pass 1 (the photos: the 2018 and 2019 Peach Bowls, the 2025 CFP final from the press box, the 2024 interiors,
#: the Falcons' 2025 bird's-eye galleries). Sides in this frame: W is -x (the south sideline, the Falcons'), E is +x (the
#: north sideline), N is -z (the west end), S is +z (the east end under the window to the city). The wall line clears the
#: retail s01 sideline props (x -38.9 to 40.6, z -61.9 to 32.9) and the field-level banners (x +-42.5, z +-66.7, projected
#: onto the new wall). Both sidelines: the 100 level, the 200 level with the suites behind glass over it, the tall 300
#: level; the west end the same; the east end the 100 and 200 levels and, over its middle, the window to the city instead
#: of the 300 level (the 2018 photo: the upper deck runs round the corners to the window's sides).
PARAMS = dict(
    loop=dict(xe=44.0, xw=43.5, zs=66.0, zn=66.0, R=20.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    sides=dict(
        W=dict(low_d0=3.0, low_y0=1.5, low_rows=32, low_tread=0.84, low_rise0=0.30, low_rise1=0.52,
               t2_over=3.0, t2_rows=2, t2_rise=0.60, band_h=3.0,
               up_d=33.0, up_y=24.0, up_rows=36, up_tread=0.84, up_rise=0.80, back_wall=2.4),
        E=dict(low_d0=3.0, low_y0=1.5, low_rows=32, low_tread=0.84, low_rise0=0.30, low_rise1=0.52,
               t2_over=3.0, t2_rows=2, t2_rise=0.60, band_h=3.0,
               up_d=33.0, up_y=24.0, up_rows=36, up_tread=0.84, up_rise=0.80, back_wall=2.4),
        N=dict(low_d0=3.0, low_y0=1.5, low_rows=30, low_tread=0.84, low_rise0=0.30, low_rise1=0.52,
               t2_over=3.0, t2_rows=2, t2_rise=0.60, band_h=3.0,
               up_d=33.0, up_y=24.0, up_rows=34, up_tread=0.84, up_rise=0.80, back_wall=2.4),
        S=dict(low_d0=3.0, low_y0=1.5, low_rows=30, low_tread=0.84, low_rise0=0.30, low_rise1=0.52,
               t2_over=3.0, t2_rows=9, t2_rise=0.60, band_h=0.0,
               up_d=34.0, up_y=24.0, up_rows=30, up_tread=0.84, up_rise=0.80, back_wall=1.2),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the roof (Wikipedia: a retractable roof, a "pinwheel" of eight translucent triangular panels round a circular
    #: opening; closed here, the record stays indoor): the fixed roof from the outline in to the opening, its dark steel
    #: underside rising from ``eave`` at the outline to ``rim`` at the opening's edge (radius ``oculus_r``); the eight
    #: panels closed over the opening as a shallow pinwheel cone to ``apex``; the tops ``depth`` over them. Pass 2: the
    #: facade's petals rise to their top edge (``top_ring``, ``overhang`` out past the outline) and turn over the roofline,
    #: sloping in as facets up to a narrow ring (``ring_y``, ``ring_w`` wide) round the opening, the pinwheel's top rising
    #: out of it to ``apex_top`` (OSM: 93 m over the plaza); the opening's edge just over the Halo (DESIGN on the measured
    #: Halo, main's pass-2 note on the aerials)
    #: pass 3 (main's notes on the pair lab and the Super Bowl LIII aerials): the facets meet the ring lower
    #: (``ring_y``) and the ring stands proud of the petals, its outer wall up to ``ring_top`` (white in the aerials), the
    #: pinwheel's panels rising from its top to ``apex_top``; the underside's outer edge stays ``eave_inset`` inside the
    #: facade (the pair lab's exterior frames and the pass-3 renders: the old edge on the outline cut through the petals'
    #: chords as dark streaks)
    roof=dict(eave=60.5, rim=76.5, oculus_r=58.0, apex=91.0, twist=14.0, depth=3.0, points=96, rings=4, top_ring=78.0,
              overhang=4.0, ring_y=88.0, ring_w=3.5, ring_top=93.5, apex_top=97.0, eave_inset=0.8),
    #: the Halo (Wikipedia: a 58 x 1,100 ft ring-shaped video board round the roof's opening, 62,350 sq ft): a ring
    #: 17.7 m tall and 107 m across hung under the opening's edge, twelve panels round it, the live picture on every other
    #: one and the club graphics between them (the game's digits on the two facing the sidelines)
    #: pass 2: its bottom 57.7 m (m69's pose, the far side of the ring over the east end, PROVED OFFLINE)
    halo=dict(r=53.36, h=17.68, bottom=57.7, panels=12, sub=4, frame=0.5),
    #: the window to the city (the east end: the 2018 Peach Bowl photos and the Centennial Olympic Park Drive view): glass
    #: from the east stands' top walk up to the roof over the end's middle; m69's pose (PROVED OFFLINE): about 86 m wide
    #: between two dark towers (x +46 and -44), its top about 58 m; the bridge across it with the venue's name, its fascia
    #: at 31.6 m; the tall column board at x +30 from 28.6 m to 66 m
    window=dict(half_w=46.0, glass_w=96.0, column_x=30.0, column_z=128.0, column_w=6.0, column_y0=28.6, column_h=37.4,
                towers=(46.0, -44.0), tower_w=8.0, tower_y1=54.0, bridge_y=30.5, bridge_h=2.6, bridge_z=118.0),
    #: the facade (the 2019 exteriors and the Super Bowl LIII aerials): a band of tall glass round the concourses over the
    #: plaza, then the leaning petals, metal and glass in turn, up to the roof's edge; ``lean`` is how far the petals'
    #: tops sit inside the outline
    #: pass 3 (main's notes: "irregular petals (sizes, pitches, heights; not a regular octagon)", the big south-west
    #: petal carries the star; the Super Bowl LIII aerials and the 2018 to 2024 exteriors): the sixteen points round the
    #: outline move off the even spacing by ``shifts`` (fractions of a sixteenth; even indices the units' corners, odd
    #: ones their tips), so the south-west and north-east units are the widest and the south one the narrowest; each
    #: corner has its own height (``corner_y``, field metres: the roofline rises and falls) and lean (``corner_out``, metres
    #: out past the outline), each metal petal's tip its own height over the plaza (``tip_y``). DESIGN.
    facade=dict(base=14.0, lean=6.0, star_d=14.0, star_big_d=22.0, star_y=44.0, sign_w=34.0, sign_h=17.0, sign_y=36.0,
                shifts=(-0.35, -0.15, 0.0, 0.0, 0.0, 0.2, 0.25, -0.1, -0.35, -0.05, 0.3, 0.2, 0.1, -0.2, -0.15, -0.2),
                corner_y=(84.0, 78.0, 78.0, 72.0, 76.0, 86.0, 74.0, 80.0),
                corner_out=(6.0, 4.0, 4.0, 3.0, 5.0, 7.0, 3.0, 5.0),
                tip_y=(12.0, 14.0, 16.0, 18.0, 10.0, 15.0, 17.0, 13.0),
                band_u_m=36.0),
    lights=dict(every=2, w=4.4, h=2.2, drop=2.0),
    #: downtown's towers past ``far`` are pulled in along their bearings to it (their heights scaled the same way),
    #: in front of the environment kit's horizon band at 1,800 m
    skyline=dict(far=1700.0),
    #: pass 3: a far sky backdrop (the pair lab, PROVED IN GAME: black above the building in the exterior shots,
    #: fly-024 to fly-030; the Georgia Dome's retail bundles carry no sky chunk, u6's finding for the Rams' dome and his
    #: SoFi fix, whose sky he saw in his lab 4)
    sky=dict(radius=1900.0, bottom=-30.0, top=1000.0, points=48),
)


#: the Halo's graphics texture holds two layouts, half a texel in from the seam: the top half with the digits' dark
#: window (the two panels over the sidelines, where adjust_digits lays the game's digits), the bottom half the club
#: layout without it (the pair lab, 2026-09-28: the four other panels showed the window empty and black)
HALO_DIGIT_V = (0.5 / 128, 0.5 - 0.5 / 128)
HALO_CLUB_V = (0.5 + 0.5 / 128, 1.0 - 0.5 / 128)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "WENS")


# ------------------------------------------------------------------------------------------------ the model

class MercedesBenz(sm.SoFi):
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

    def window_zone(self, lp):
        """True on the east end in front of the window to the city (no 300 level there)."""
        return lp.w["S"] > 0.6 and abs(lp.x) < self.p["window"]["half_w"]

    def window_glass(self, lp):
        """True where the window's glass stands behind the east 200 level (the wall up to the roof stops there)."""
        return lp.w["S"] > 0.6 and abs(lp.x) < self.p["window"]["glass_w"] / 2 - 1.0

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
        if lp is not None:
            room = self.facade_depth(lp) - 1.0 - p["rim"]["walk"] * 0.5 - 0.7 - (du + 0.4)
            rowsu = max(0, min(rowsu, int(room / g("up_tread"))))
            if self.window_zone(lp):
                rowsu = 0
        if rowsu < 2:
            # no 300 level (the window's end): the 200 level's back wall and a walk behind it, where the glass stands
            y = (yb + bh) if bh > 0.2 else t2[-1][1]
            dback = (db if bh > 0.2 else t2[-1][0]) + 0.3
            walk_end = dback + p["rim"]["walk"]
            if lp is not None:
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
            self.prefix = f"mb_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "mb"
        self._roof()
        self._lights()
        self._halo()
        self._window(loop, secs)
        self._column()
        north = min(loop, key=lambda lp: (lp.nx - 1) ** 2 + (lp.z / 40.0) ** 2)
        row = self.section(north)["upper"][4]
        self.nosebleed = self.at(north, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._exterior()
        return self

    def mesh(self, name):
        if name.startswith("mb_bowl_"):
            name = getattr(self, "prefix", "mb_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats: red on every level -------------------------------------------------------------------------------
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
        for mat, i0, i1 in (("mb_seat_front", 0, a), ("mb_seat_mid", a, b), ("mb_seat_back", b, len(ks) - 1)):
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
            self._rows_surface(m, "mb_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("mb_bowl_a")
        wall = p["wall"]["height"]
        m.grid("mb_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("mb_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "mb_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_mb_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        m2 = self.mesh("mb_bowl_b")
        self._ledge(m2, "mb_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_mb_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_mb_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "mb_concrete", loop, secs, "band_floor", up)
        m4 = self.mesh("mb_bowl_d")
        self._band(m4, "LIGHT_mb_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("mb_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                    [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_mb_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk, and behind them the dark structure up to the roof
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            m4.grid("LIGHT_mb_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                           [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("mb_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
                                    [self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 0.4) for lp in lps]], facing=up)
            sub = []
            for lp, r in list(zip(lps, rims)) + [(None, None)]:
                if lp is not None and not self.window_glass(lp):
                    sub.append((lp, r))
                    continue
                if len(sub) >= 2:
                    tops = [self.roof_height(*self.at(q_, r_[3], 0.0)[::2]) - 0.3 for q_, r_ in sub]
                    m4.grid("mb_dark", [[self.at(q_, r_[3], r_[2]) for q_, r_ in sub],
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
            m.quad("mb_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    # -- the roof -------------------------------------------------------------------------------------------------
    def facade_ring(self, n):
        """(points (x, z), normalised arc position) of the OSM facade outline resampled to n points, counter-clockwise."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        return sm._ring_polyline(P, n)

    def roof_height(self, x, z):
        """The roof's underside over (x, z): the fixed roof's dark steel from the eave at the outline up to the rim of the
        opening, then the closed panels' cone to the apex."""
        q = self.p["roof"]
        r = math.hypot(x, z)
        R0 = q["oculus_r"]
        if r <= R0:
            return q["rim"] + (q["apex"] - q["rim"]) * (1.0 - r / R0)
        ring = self.__dict__.get("_eave_polar")
        if ring is None:
            pts, _pos = self.facade_ring(360)
            P = np.array(pts)
            ang = np.arctan2(P[:, 1], P[:, 0])
            order = np.argsort(ang)
            ring = (ang[order], np.hypot(P[:, 0], P[:, 1])[order])
            self._eave_polar = ring
        a, rr = ring
        Ro = float(np.interp(math.atan2(z, x), a, rr, period=2 * math.pi))
        f = min(1.0, max(0.0, (r - R0) / max(1e-6, Ro - R0)))
        return q["rim"] + (q["eave"] - q["rim"]) * f

    def _outline_at(self, frac):
        """(x, z) on the OSM facade outline at a normalised arc position (the same start and direction as
        ``facade_ring``)."""
        P = sm._ccw(np.array(footprint()["facade"], float))
        if np.allclose(P[0], P[-1]):
            P = P[:-1]
        C = np.vstack([P, P[:1]])
        seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        u = (frac % 1.0) * cum[-1]
        i = min(int(np.searchsorted(cum, u, side="right") - 1), len(seg) - 1)
        t = (u - cum[i]) / max(seg[i], 1e-9)
        p = C[i] * (1 - t) + C[i + 1] * t
        return float(p[0]), float(p[1])

    def petal_layout(self):
        """The facade's eight units, irregular (pass 3; see ``PARAMS["facade"]``): unit k runs from corner k through tip
        k to corner k + 1. Returns dict(corners=[dict(base=(x, z), top=(x, y, z))], tips=[(x, y, z)], centre=(x, z)):
        a corner's base is its point on the outline, its top that point pushed out by its lean at its height; a tip is
        its point on the outline at its height over the plaza."""
        lay = self.__dict__.get("_petal_layout")
        if lay is not None:
            return lay
        q = self.p["facade"]
        pts = [self._outline_at((i + q["shifts"][i]) / 16.0) for i in range(16)]
        cx, cz = (float(v) for v in np.mean(pts, axis=0))
        corners, tips = [], []
        for k in range(8):
            x, z = pts[2 * k]
            v = np.array([x - cx, z - cz]); v /= max(1e-9, np.linalg.norm(v))
            o = q["corner_out"][k]
            corners.append(dict(base=(x, z), top=(float(x + v[0] * o), q["corner_y"][k], float(z + v[1] * o))))
            tx, tz = pts[2 * k + 1]
            tips.append((tx, GRADE + q["tip_y"][k], tz))
        lay = dict(corners=corners, tips=tips, centre=(cx, cz))
        self._petal_layout = lay
        return lay

    def petal_triangles(self):
        """[(unit, kind, [3 points])]: each unit's metal petal (tip-down from its two top corners to its tip) and the
        glass either side of it (tip-up from the band's top to a top corner), before the east face turns them over."""
        lay = self.petal_layout()
        C, T = lay["corners"], lay["tips"]
        yb = GRADE + self.p["facade"]["base"]
        out = []
        for k in range(8):
            a, c = C[k], C[(k + 1) % 8]
            b = T[k]
            ta, tc = a["top"], c["top"]
            out.append((k, "petal", [ta, tc, b]))
            out.append((k, "glass_l", [(a["base"][0], yb, a["base"][1]), b, ta]))
            out.append((k, "glass_r", [b, (c["base"][0], yb, c["base"][1]), tc]))
        return out

    def facade_section_radius(self, y, angles):
        """The facade's radius from the layout's centre at height y along each angle (radians, game plan angle
        atan2(z, x)): the nearest crossing of that bearing with the facade's triangles cut at y."""
        segs = []
        for _k, _kind, tri in self.petal_triangles():
            pts = [np.array(p_, float) for p_ in tri]
            cut = []
            for i in range(3):
                p0, p1 = pts[i], pts[(i + 1) % 3]
                if (p0[1] - y) * (p1[1] - y) < 0:
                    t = (y - p0[1]) / (p1[1] - p0[1])
                    q_ = p0 + (p1 - p0) * t
                    cut.append((float(q_[0]), float(q_[2])))
            if len(cut) == 2:
                segs.append(cut)
        cx, cz = self.petal_layout()["centre"]
        out = []
        for a in angles:
            d = np.array([math.cos(a), math.sin(a)])
            best = None
            for (x0, z0), (x1, z1) in segs:
                e = np.array([x1 - x0, z1 - z0])
                M = np.array([[d[0], -e[0]], [d[1], -e[1]]])
                det = float(np.linalg.det(M))
                if abs(det) < 1e-9:
                    continue
                t, u = np.linalg.solve(M, np.array([x0 - cx, z0 - cz]))
                if t > 0 and -1e-6 <= u <= 1 + 1e-6 and (best is None or t < best):
                    best = float(t)
            out.append(best if best is not None else float("inf"))
        return out

    def petal_tops(self):
        """[(x, z)] of the eight corners' tops (where the petals turn over the roofline)."""
        return [(c["top"][0], c["top"][2]) for c in self.petal_layout()["corners"]]

    def _roof(self):
        """The roof. From below: the fixed roof's dark steel from the eave at the outline up to the opening's edge, and
        the eight closed panels of the pinwheel over the opening (the Commons roof photos, closed: a web of steel over the
        translucent panels), the ring truss's inner face between them. From above (main's pass-2 note on the aerials): the
        silver petals ARE the roofline, sloping in from the facade's top edge in facets up to a narrow white ring round the
        opening, and the pinwheel's eight dark panels on their steel in the middle, up to the apex. Pass 3: each facet
        starts at its corner's own height, the ring stands proud of them (its outer wall to ``ring_top``), and the
        underside's outer edge keeps inside the facade (``eave_inset`` in from the petals' section at the eave)."""
        q = self.p["roof"]
        N = q["points"]
        ring, _pos = self.facade_ring(N)
        R0 = q["oculus_r"]
        cx0, cz0 = self.petal_layout()["centre"]
        sec = self.facade_section_radius(q["eave"], [math.atan2(z - cz0, x - cx0) for x, z in ring])
        und = self.meshes.setdefault("mb_roof_under", Mesh("mb_roof_under"))
        top = self.meshes.setdefault("mb_roof_top", Mesh("mb_roof_top"))
        rows_u, uvs = [], []
        K = q["rings"]
        for k in range(K + 1):
            f = k / K
            ru, uv = [], []
            for j, (x, z) in enumerate(list(ring) + [ring[0]]):
                a = math.atan2(z, x)
                Ro = math.hypot(x, z)
                # the outer edge on the outline, or inside the facade where the petals' chords cut in (pass 3)
                ao = math.atan2(z - cz0, x - cx0)
                so = sec[j % len(sec)]
                edge = np.array([cx0 + (so - q["eave_inset"]) * math.cos(ao), cz0 + (so - q["eave_inset"]) * math.sin(ao)])
                Re = min(Ro, float(np.hypot(*edge))) if math.isfinite(so) else Ro
                r = Re + (R0 - Re) * f
                px, pz = r * math.cos(a), r * math.sin(a)
                ru.append((px, self.roof_height(px, pz) if (f > 0 or Re < Ro - 1e-6) else q["eave"], pz))
                uv.append((a * 9.0, f * 2.0))
            rows_u.append(ru); uvs.append(uv)
        und.grid("mb_ring", rows_u, uvs, facing=down)
        self.rim_ring = rows_u[-1]
        circ = [(R0 * math.cos(2 * math.pi * j / 64), R0 * math.sin(2 * math.pi * j / 64)) for j in range(65)]
        # the ring truss's inner face round the opening, from the pinwheel's underside up to the ring (seen from inside)
        und.grid("mb_ring", [[(x, q["rim"], z) for x, z in circ], [(x, q["ring_top"], z) for x, z in circ]],
                 [[(j / 8.0, 1.0) for j in range(65)], [(j / 8.0, 0.0) for j in range(65)]],
                 facing=lambda p_: np.array([-p_[0], 0.0, -p_[2]]))
        # the petals over the top: facets from the eight petal tops at the facade's edge in to eight points on the ring
        # (each petal a triangle to the ring point at its middle, the triangles between them to two ring points)
        T3 = [c["top"] for c in self.petal_layout()["corners"]]
        T = [(p_[0], p_[2]) for p_ in T3]
        n8 = len(T)
        # the ring points' octagon circumscribes the ring: its edges pass ``ring_w`` outside the opening's circle
        Rr = (R0 + q["ring_w"]) / math.cos(math.pi / 8)
        Ipts = []
        for k in range(n8):
            ax, az = T[k]; bx, bz = T[(k + 1) % n8]
            ang = math.atan2((az + bz) / 2, (ax + bx) / 2)
            Ipts.append((Rr * math.cos(ang), Rr * math.sin(ang)))
        ry, rt = q["ring_y"], q["ring_top"]

        def facet(mat, P3):
            p0, p1, p2 = (np.array(v_, float) for v_ in P3)
            n_ = np.cross(p1 - p0, p2 - p0)
            if n_[1] < 0:
                n_ = -n_
                p1, p2 = p2, p1
            n_ = n_ / max(1e-9, np.linalg.norm(n_))
            pl = lambda v_: (float(v_[0]) / 30.0, float(v_[2]) / 30.0)  # noqa: E731
            top.strip(mat, [top.v(tuple(v_), pl(v_), tuple(n_)) for v_ in (p0, p1, p2)])
        for k in range(n8):
            a3, b3 = T3[k], T3[(k + 1) % n8]
            i0_, i1_ = Ipts[k], Ipts[(k + 1) % n8]
            facet("mb_panel_top", [a3, b3, (i0_[0], ry, i0_[1])])
            facet("mb_panel_top", [b3, (i1_[0], ry, i1_[1]), (i0_[0], ry, i0_[1])])
            # the ring's outer wall over this edge of the octagon, up from where the facets meet it (pass 3: proud)
            o_ = np.array([(i0_[0] + i1_[0]) / 2, 0.0, (i0_[1] + i1_[1]) / 2])
            top.quad("mb_roof_top", (i0_[0], ry, i0_[1]), (i1_[0], ry, i1_[1]), (i1_[0], rt, i1_[1]), (i0_[0], rt, i0_[1]),
                     (0, 1), (1, 1), (1, 0.8), (0, 0.8), facing=lambda p_, o_=o_: o_)
        # the narrow ring: from the ring points in to the opening's circle, flat, and its outer lip
        ringp = []
        for j in range(65):
            a = 2 * math.pi * j / 64
            # the ring's outer edge follows the octagon of ring points (so the facets meet it)
            k = int(((a - math.atan2(Ipts[0][1], Ipts[0][0])) % (2 * math.pi)) / (2 * math.pi / n8)) % n8
            p0 = np.array(Ipts[k]); p1 = np.array(Ipts[(k + 1) % n8])
            a0_ = math.atan2(p0[1], p0[0]); a1_ = math.atan2(p1[1], p1[0])
            span = (a1_ - a0_) % (2 * math.pi)
            t = ((a - a0_) % (2 * math.pi)) / max(1e-9, span)
            e = p0 + (p1 - p0) * min(1.0, max(0.0, t))
            ringp.append((float(e[0]), float(e[1])))
        top.grid("mb_roof_top", [[(x, rt, z) for x, z in ringp], [(x, rt, z) for x, z in circ]],
                 [[(j / 8.0, 0.0) for j in range(65)], [(j / 8.0, 0.2) for j in range(65)]], facing=up)
        top.grid("mb_roof_top", [[(x, rt, z) for x, z in circ], [(x, rt + 0.4, z) for x, z in circ]],
                 [[(j / 8.0, 0.0) for j in range(65)], [(j / 8.0, 0.1) for j in range(65)]],
                 facing=lambda p_: np.array([-p_[0], 0.0, -p_[2]]))
        # the eight panels, closed: from below each a fan over its eighth of the opening from the circle to the apex (it
        # follows the circle, so no gap opens against the fixed roof), a dark steel blade along its leading edge turned
        # ``twist`` degrees round (the pinwheel); from above the same panels from the ring up to the apex's top, dark
        # translucent on their steel
        P8, F = 8, 8                    # 64 steps round the circle, as the ring's lip and inner face, so no sliver opens
        apex_u = np.array([0.0, q["apex"], 0.0])
        apex_t = np.array([0.0, q["apex_top"], 0.0])
        tw = math.radians(q["twist"])
        for k in range(P8):
            a0 = 2 * math.pi * k / P8
            angs = [a0 + (2 * math.pi / P8) * j / F for j in range(F + 1)]
            arc = [np.array([R0 * math.cos(a), q["rim"], R0 * math.sin(a)]) for a in angs]
            arc_t = [np.array([R0 * math.cos(a), rt + 0.4, R0 * math.sin(a)]) for a in angs]
            for j in range(F):
                A, B = arc[j], arc[j + 1]
                # planar UVs: the steel web reads as one lattice across the panels (u6's roof rule: no rings)
                pl = lambda v_: (float(v_[0]) / 22.0, float(v_[2]) / 22.0)  # noqa: E731
                i_ = [und.v(tuple(A), pl(A), (0.0, -1.0, 0.0)), und.v(tuple(B), pl(B), (0.0, -1.0, 0.0)),
                      und.v(tuple(apex_u), pl(apex_u), (0.0, -1.0, 0.0))]
                n_ = np.cross(B - A, apex_u - A)
                und.strip("mb_roof_under", i_ if n_[1] < 0 else [i_[0], i_[2], i_[1]])
                At, Bt = arc_t[j], arc_t[j + 1]
                n_t = np.cross(Bt - At, apex_t - At)
                n_t = n_t if n_t[1] > 0 else -n_t
                n_t = n_t / np.linalg.norm(n_t)
                t_ = [top.v(tuple(At), pl(At), tuple(n_t)), top.v(tuple(Bt), pl(Bt), tuple(n_t)),
                      top.v(tuple(apex_t), pl(apex_t), tuple(n_t))]
                top.strip("mb_pinwheel", t_ if np.cross(Bt - At, apex_t - At)[1] > 0 else [t_[0], t_[2], t_[1]])
            # the blade: from the circle at the panel's leading edge to a point near the apex turned by the twist
            e0 = arc[0]
            e1 = np.array([10.0 * math.cos(a0 + tw), q["apex"] - (q["apex"] - q["rim"]) * 10.0 / R0, 10.0 * math.sin(a0 + tw)])
            side = np.cross(e1 - e0, [0.0, 1.0, 0.0]); side = side / max(1e-9, np.linalg.norm(side)) * 0.9
            und.quad("mb_black", e0 - side - [0, 0.3, 0], e0 + side - [0, 0.3, 0], e1 + side - [0, 0.3, 0], e1 - side - [0, 0.3, 0],
                     (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, -1.0, 0.0]))
            # and its white steel from above, from the ring to the apex's top
            f0 = arc_t[0] + [0, 0.25, 0]
            f1 = np.array([10.0 * math.cos(a0 + tw), q["apex_top"] - (q["apex_top"] - (rt + 0.4)) * 10.0 / R0 + 0.25,
                           10.0 * math.sin(a0 + tw)])
            side = np.cross(f1 - f0, [0.0, 1.0, 0.0]); side = side / max(1e-9, np.linalg.norm(side)) * 0.8
            top.quad("mb_roof_top", f0 - side, f0 + side, f1 + side, f1 - side, (0, 1), (1, 1), (1, 0), (0, 0),
                     facing=lambda p_: np.array([0.0, 1.0, 0.0]))

    def _lights(self):
        """Floodlights hung round the opening's edge (the photos: rows of lamps on the steel round the Halo); each lamp's
        centre joins ``light_points``."""
        q = self.p["lights"]
        m = self.meshes.setdefault("mb_lights", Mesh("mb_lights"))
        R1 = self.p["roof"]["oculus_r"] + 10.0
        n = 48
        for k in range(0, n, 1):
            a = 2 * math.pi * k / n
            x, z = R1 * math.cos(a), R1 * math.sin(a)
            y = self.roof_height(x, z)
            nrm = np.array([x, 0.0, z]); nrm /= max(1e-9, np.linalg.norm(nrm))
            ctr = np.array([x, y - q["drop"], z])
            along = np.array([-nrm[2], 0.0, nrm[0]])
            normal = -nrm * math.cos(math.radians(55)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(55))
            upv = np.cross(along, normal); upv = upv / np.linalg.norm(upv) * (1.0 if upv[1] > 0 else -1.0)
            hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
            m.quad("LIGHT_mb_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, nn=normal: nn)
            self.light_points.append(tuple(ctr))

    # -- the Halo --------------------------------------------------------------------------------------------------
    #: the live feed fills u 0 to 0.625, v 0 to 0.875 of the jumbo_tron render target (PROVED OFFLINE by u5 and u6); a
    #: panel shows the band of it at the picture's own aspect (the middle rows of the picture, where the play is)
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

    def halo_angle(self, k):
        """The centre angle (game angle, atan2(z, x)) of the Halo's panel k: panel 0 faces the south stands from +x."""
        return 2 * math.pi * k / self.p["halo"]["panels"]

    def _halo(self):
        """The Halo: a ring round the opening, its inside the live picture (every odd panel, at the picture's aspect) and
        the club graphics (every even panel: the ones at +x and -x carry the game's digits); black outside, black
        frames top and bottom; the jumbo markers on the two feed panels over the ends."""
        q = self.p["halo"]
        m = self.meshes.setdefault("mb_halo", Mesh("mb_halo"))
        self.markers["jumbo"] = []
        r, h, y0, K, S = q["r"], q["h"], q["bottom"], q["panels"], q["sub"]
        y1 = y0 + h
        arc = 2 * math.pi * r / K
        (U0, U1), (V0, V1) = self.board_crop(arc / h)
        self.halo_frames = []
        for k in range(K):
            ac = self.halo_angle(k)
            a0, a1 = ac - math.pi / K, ac + math.pi / K
            angs = [a0 + (a1 - a0) * j / S for j in range(S + 1)]
            inner = [(r * math.cos(a), r * math.sin(a)) for a in angs]
            outer = [((r + 1.2) * math.cos(a), (r + 1.2) * math.sin(a)) for a in angs]
            inward = lambda p_: np.array([-p_[0], 0.0, -p_[2]])  # noqa: E731
            outward = lambda p_: np.array([p_[0], 0.0, p_[2]])  # noqa: E731
            # u runs WITH the angle: seen from inside, the game's screen right is cross(view, up), the direction of
            # increasing angle (PROVED IN GAME, the pair lab's fly-016: the digits laid along it read left to right,
            # while pass 1's panels, u against the angle, read mirrored and the feed showed the frame mirrored)
            us = [j / S for j in range(S + 1)]
            if k % 2 == 1:
                m.grid("jumbo_tron", [[(x, y0, z) for x, z in inner], [(x, y1, z) for x, z in inner]],
                       [[(U0 + (U1 - U0) * u, V1) for u in us], [(U0 + (U1 - U0) * u, V0) for u in us]], facing=inward)
            else:
                # the two panels over the sidelines carry the game's digits in their dark window (the texture's top
                # half); the other four the club layout without a window (its bottom half)
                hv0, hv1 = HALO_DIGIT_V if abs(math.sin(ac)) <= 0.5 else HALO_CLUB_V
                m.grid("LIGHT_mb_halo", [[(x, y0, z) for x, z in inner], [(x, y1, z) for x, z in inner]],
                       [[(u, hv1) for u in us], [(u, hv0) for u in us]], facing=inward)
            m.grid("mb_black", [[(x, y0, z) for x, z in outer], [(x, y1 + 0.6, z) for x, z in outer]],
                   [[(j / S, 1.0) for j in range(S + 1)], [(j / S, 0.0) for j in range(S + 1)]], facing=outward)
            m.grid("mb_black", [[(x, y0 - q["frame"], z) for x, z in inner], [(x, y0 - q["frame"], z) for x, z in outer]],
                   [[(j / S, 0.0) for j in range(S + 1)], [(j / S, 0.2) for j in range(S + 1)]], facing=down)
            m.grid("mb_black", [[(x, y0 - q["frame"], z) for x, z in inner], [(x, y0, z) for x, z in inner]],
                   [[(j / S, 0.0) for j in range(S + 1)], [(j / S, 0.1) for j in range(S + 1)]], facing=inward)
            m.grid("mb_black", [[(x, y1, z) for x, z in inner], [(x, y1 + 0.6, z) for x, z in inner]],
                   [[(j / S, 0.0) for j in range(S + 1)], [(j / S, 0.1) for j in range(S + 1)]], facing=inward)
            c = np.array([r * math.cos(ac), y0 + h / 2, r * math.sin(ac)])
            face = -np.array([math.cos(ac), 0.0, math.sin(ac)])
            right = np.cross(-face, (0.0, 1.0, 0.0)); right /= np.linalg.norm(right)
            self.halo_frames.append(dict(centre=c, face=face, right=right, feed=k % 2 == 1, angle=ac))
        for k in (K // 4, 3 * K // 4):
            kk = k if k % 2 == 1 else k + 1
            self.markers["jumbo"].append(tuple(self.halo_frames[kk % K]["centre"]))
        # four hangers from the opening's rim to the Halo's top at the panel seams
        st = self.meshes.setdefault("mb_halo_hangers", Mesh("mb_halo_hangers"))
        for k in range(0, K, 3):
            a = self.halo_angle(k) - math.pi / K
            p0 = np.array([(r + 0.6) * math.cos(a), y1 + 0.6, (r + 0.6) * math.sin(a)])
            p1 = np.array([(r + 0.6) * math.cos(a), self.roof_height(r * math.cos(a), r * math.sin(a)), (r + 0.6) * math.sin(a)])
            t = np.array([-math.sin(a), 0.0, math.cos(a)]) * 0.5
            st.quad("mb_black", p0 - t, p0 + t, p1 + t, p1 - t, (0, 1), (1, 1), (1, 0), (0, 0),
                    facing=lambda p_: np.array([-p_[0], 0.0, -p_[2]]))

    # -- the window to the city ---------------------------------------------------------------------------------------
    def window_arc(self, n=15):
        """[(x, z)] of the window's glass along the outline's east curve (OSM), |x| up to half the glass width, 0.5 m inside
        the outline."""
        half = self.p["window"]["glass_w"] / 2
        ring, _pos = self.facade_ring(720)
        P = np.array([p_ for p_ in ring if p_[1] > 60.0 and abs(p_[0]) <= half + 8.0], float)
        P = P[np.argsort(P[:, 0])]
        xs = np.linspace(-half, half, n)
        zs = np.interp(xs, P[:, 0], P[:, 1]) - 0.5
        return [(float(x), float(z)) for x, z in zip(xs, zs)]

    def _window(self, loop, secs):
        """The window to the city (the east end: the 2018 photo, the Centennial Olympic Park Drive view): the glass on the
        outline's east face from the 200 level's top walk up to the roof, downtown's towers beyond it; the walk out to it
        and the side walls; the star on its black panel under the glass, over the end's middle (the 2018 photo)."""
        m = self.meshes.setdefault("mb_window", Mesh("mb_window"))
        mid = min(range(len(loop) - 1), key=lambda i: (loop[i].nz - 1) ** 2 + (loop[i].x / 30.0) ** 2)
        y0 = secs[mid]["rim"][2]
        arc = self.window_arc()
        x0, x1 = arc[0][0], arc[-1][0]
        tops = [self.roof_height(x, z) - 0.2 for x, z in arc]
        inward = lambda p_: np.array([-p_[0], 0.0, -p_[2]])  # noqa: E731
        u = [(x - x0) / 12.0 for x, _z in arc]
        m.grid("LIGHT_mb_window", [[(x, y0, z) for x, z in arc], [(x, t, z) for (x, z), t in zip(arc, tops)]],
               [[(uu, 1.0) for uu in u], [(uu, 0.0) for uu in u]], facing=inward)
        rim_pts = sorted((loop[i].x + loop[i].nx * secs[i]["rim"][3], loop[i].z + loop[i].nz * secs[i]["rim"][3])
                         for i in range(len(loop) - 1) if loop[i].z > 0 and loop[i].w["S"] > 0.3 and "rim" in secs[i])
        RX = np.array([p_[0] for p_ in rim_pts]); RZ = np.array([p_[1] for p_ in rim_pts])
        inner = [(x, y0 - 0.2, float(np.interp(x, RX, RZ))) for x, _z in arc]
        outer = [(x, y0 - 0.2, z - 0.2) for x, z in arc]
        m.grid("mb_concrete", [inner, outer], [[(x / 8.0, 0.0) for x, _z in arc], [(x / 8.0, 1.0) for x, _z in arc]], facing=up)
        for (xe, ze), (xi, _yi, zi), sgn in ((arc[0], inner[0], 1.0), (arc[-1], inner[-1], -1.0)):
            ytop = self.roof_height(xe, ze) - 0.3
            m.quad("mb_dark", (xe, y0 - 0.2, ze), (xi, y0 - 0.2, zi), (xi, ytop, zi), (xe, ytop, ze), (0, 1), (1, 1), (1, 0),
                   (0, 0), facing=lambda p_, s_=sgn: np.array([s_, 0.0, 0.0]))
        # the star on its black panel over the east 200 level's suites, over the end's middle, facing the field (the 2018
        # photo: a black square with the star under the window)
        q = self.p["facade"]
        d = q["star_d"] * 0.5
        sec = secs[mid]
        band = sec.get("band") or (sec["rim"][0], sec["rim"][1] - 3.0, sec["rim"][1])
        yb = band[1] + 0.6
        zc = loop[mid].z + band[0] - 0.35
        zc2 = zc - 0.05
        facing_w = lambda p_: np.array([0.0, 0.0, -1.0])  # noqa: E731
        m.quad("mb_black", (d * 0.62, yb - 0.4, zc), (-d * 0.62, yb - 0.4, zc), (-d * 0.62, yb + d + 0.4, zc),
               (d * 0.62, yb + d + 0.4, zc), (0, 1), (1, 1), (1, 0), (0, 0), facing=facing_w)
        m.quad("mb_star", (d / 2, yb, zc2), (-d / 2, yb, zc2), (-d / 2, yb + d, zc2), (d / 2, yb + d, zc2),
               (0, 1), (1, 1), (1, 0), (0, 0), facing=facing_w)
        self.window = dict(x0=x0, x1=x1, y0=y0, arc=arc, z=float(np.interp(0.0, [a for a, _b in arc], [b for _a, b in arc])))

    def _column(self):
        """The tall board by the window (the 2018 and 2019 photos: a vertical LED column at the window's north side)."""
        q = self.p["window"]
        w = getattr(self, "window", None)
        if not w:
            return
        m = self.meshes.setdefault("mb_column", Mesh("mb_column"))
        x = q["column_x"]
        z = q["column_z"]
        c = np.array([x, q["column_y0"], z])
        face = np.array([0.0, 0.0, -1.0])
        right = np.array([-1.0, 0.0, 0.0])
        hv = np.array([0.0, q["column_h"], 0.0])
        m.box("mb_black", c + hv / 2, (right, (0, 1, 0), face), (q["column_w"] / 2 + 0.4, q["column_h"] / 2 + 0.4, 0.8),
              uvscale=0.1, bottom=True)
        fc = c + face * 0.85
        A, B = fc - right * q["column_w"] / 2, fc + right * q["column_w"] / 2
        m.quad("LIGHT_mb_column", A, B, B + hv, A + hv, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: face)
        # the two dark towers either side of the glass and the bridge across it with the venue's name (m69)
        tw = q["tower_w"]
        for tx in q["towers"]:
            zt = float(np.interp(tx, [a for a, _b in w["arc"]], [b for _a, b in w["arc"]], left=w["arc"][0][1],
                                 right=w["arc"][-1][1])) - tw / 2 - 1.0
            y0t = w["y0"] - 4.0
            m.box("mb_black", np.array([tx, (y0t + q["tower_y1"]) / 2, zt]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                  (tw / 2, (q["tower_y1"] - y0t) / 2, tw / 2), uvscale=0.1, bottom=True)
        xa, xb = min(q["towers"]) + tw / 2, max(q["towers"]) - tw / 2
        zb, yb_, hb = q["bridge_z"], q["bridge_y"], q["bridge_h"]
        m.box("mb_concrete", np.array([(xa + xb) / 2, yb_ - 0.3, zb + 2.0]), ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
              ((xb - xa) / 2, 0.3, 2.0), uvscale=0.1, bottom=True)
        m.quad("mb_black", (xb, yb_ - 0.6, zb), (xa, yb_ - 0.6, zb), (xa, yb_ + hb, zb), (xb, yb_ + hb, zb),
               (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, 0.0, -1.0]))
        sw, sh = 24.0, 3.0
        m.quad("mb_name", (sw / 2, yb_ - 0.3, zb - 0.1), (-sw / 2, yb_ - 0.3, zb - 0.1), (-sw / 2, yb_ - 0.3 + sh, zb - 0.1),
               (sw / 2, yb_ - 0.3 + sh, zb - 0.1), (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_: np.array([0.0, 0.0, -1.0]))

    # -- the facade ---------------------------------------------------------------------------------------------------
    def _facade(self):
        """The facade (the 2019 exteriors and the aerials; pass 3 on main's notes): the tall glass band round the
        concourses over the plaza on the units' chords (main: "fewer, larger glass facets": its own texture, two rows
        of big panes split on their diagonals, one repeat of four panes every ``band_u_m``), then
        the eight irregular units (``petal_layout``): each a metal petal hanging tip-down from its two top corners, glass
        rising tip-up either side of it. The window to the city is the east face's glass: that unit turns over (the
        window the tip-down glass, the two tip-up triangles either side of it metal). The star on the big south-west
        petal and on the south-east one, the venue's sign on the north-east and north-west ones (DESIGN places; the 2024
        south-west view shows the star on the big petal)."""
        q = self.p["facade"]
        lay = self.petal_layout()
        C, Tp = lay["corners"], lay["tips"]
        cx, cz = lay["centre"]
        m = self.meshes.setdefault("mb_facade", Mesh("mb_facade"))
        outward = lambda p_: np.array([p_[0] - cx, 0.0, p_[2] - cz])  # noqa: E731
        yb = GRADE + q["base"]
        # the band: on the sixteen points' chords, three steps each, its top at the band's height at the corners and at
        # each tip's own height
        stops = []
        for k in range(8):
            stops.append((C[k]["base"][0], yb, C[k]["base"][1]))
            stops.append((Tp[k][0], Tp[k][1], Tp[k][2]))
        stops.append(stops[0])
        band = []
        for i in range(16):
            p0, p1 = np.array(stops[i], float), np.array(stops[i + 1], float)
            for t in (0.0, 1 / 3, 2 / 3):
                band.append(p0 + (p1 - p0) * t)
        band.append(np.array(stops[0], float))
        L = np.concatenate([[0.0], np.cumsum([math.dist((a[0], a[2]), (b[0], b[2])) for a, b in zip(band[:-1], band[1:])])])
        m.grid("mb_glass_base", [[(float(p_[0]), GRADE - 0.5, float(p_[2])) for p_ in band],
                                [(float(p_[0]), float(p_[1]), float(p_[2])) for p_ in band]],
               [[(s_ / q["band_u_m"], 1.0) for s_ in L], [(s_ / q["band_u_m"], 0.0) for s_ in L]], facing=outward)
        win = getattr(self, "window", None)
        metal_tris = []
        for k, kind, tri in self.petal_triangles():
            b = Tp[k]
            east = win is not None and b[2] > 100.0 and abs(b[0]) < win["x1"] + 10.0
            mat = ("mb_glass_out" if kind == "petal" else "mb_panel") if east else \
                ("mb_panel" if kind == "petal" else "mb_glass_out")
            p0, p1, p2 = (np.array(v_, float) for v_ in tri)
            n_ = np.cross(p1 - p0, p2 - p0)
            o = outward(p0)
            if float(n_ @ o) < 0:
                n_ = -n_
                p1, p2 = p2, p1
            n_ = n_ / max(1e-9, np.linalg.norm(n_))
            tip_down = kind == "petal"
            uvs_ = ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0)) if tip_down else ((0.0, 1.0), (1.0, 1.0), (0.5, 0.0))
            ids = [m.v(tuple(p0), uvs_[0], tuple(n_)), m.v(tuple(p1), uvs_[1], tuple(n_)), m.v(tuple(p2), uvs_[2], tuple(n_))]
            m.strip(mat, ids)
            if mat == "mb_panel":
                metal_tris.append((np.array(tri, float), n_, k, kind))
        # the star and the sign on the metal petals facing south-west (the big one) and south-east (the star) and
        # north-east and north-west (the sign): each at its triangle's incentre, upright in the triangle's plane, sized to
        # its incircle, a little proud of it. Game plan angle = compass bearing - 349.5 degrees (+x north-north-west).
        sg = self.meshes.setdefault("mb_signs", Mesh("mb_signs"))
        places = [(math.radians(220.0 - 349.5), "mb_star", q["star_big_d"]),
                  (math.radians(126.0 - 349.5), "mb_star", q["star_d"]),
                  (math.radians(40.0 - 349.5), "mb_sign", None), (math.radians(306.0 - 349.5), "mb_sign", None)]
        used = set()
        self.sign_places = []
        for ang, what, dia in places:
            def off(k):
                c_ = metal_tris[k][0].mean(axis=0)
                return abs(((math.atan2(c_[2], c_[0]) - ang + math.pi) % (2 * math.pi)) - math.pi)
            k = min((k for k in range(len(metal_tris)) if k not in used and metal_tris[k][3] == "petal"), key=off)
            used.add(k)
            T, nrm, unit, _kind = metal_tris[k]
            A_, B_, C_ = T
            la, lb, lc = np.linalg.norm(B_ - C_), np.linalg.norm(C_ - A_), np.linalg.norm(A_ - B_)
            inc = (la * A_ + lb * B_ + lc * C_) / (la + lb + lc)
            area = 0.5 * np.linalg.norm(np.cross(B_ - A_, C_ - A_))
            rin = 2 * area / (la + lb + lc)
            upv = np.array([0.0, 1.0, 0.0]) - nrm * nrm[1]
            upv /= np.linalg.norm(upv)
            right = np.cross(upv, nrm)
            if what == "mb_star":
                w = h = min(dia, 1.3 * rin) / 2
            else:
                f_ = min(1.0, 1.3 * rin / math.hypot(q["sign_w"], q["sign_h"]))
                w, h = q["sign_w"] * f_ / 2, q["sign_h"] * f_ / 2
            c = inc + nrm * 0.5
            sg.quad(what, c - right * w - upv * h, c + right * w - upv * h, c + right * w + upv * h, c - right * w + upv * h,
                    (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, nn=nrm: nn)
            self.sign_places.append(dict(what=what, unit=unit, centre=tuple(float(v_) for v_ in c), size=2 * w))
        self.metal_tris = [(t_, n_) for t_, n_, _u, _k in metal_tris]

    # -- outside -----------------------------------------------------------------------------------------------------
    def _exterior(self):
        ring, _pos = self.facade_ring(72)
        R = list(ring) + [ring[0]]
        cx, cz = np.mean(ring, axis=0)
        m = self.meshes.setdefault("mb_plaza", Mesh("mb_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= np.linalg.norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(12.0), grow(36.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("mb_plaza", rings, [uv(r) for r in rings], facing=up)
        # the environment kit (st3, nfl2k5_stadium_environment): outside the plaza, the lots with their cars, the
        # roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band
        # at 1,800 m inside the sky; the kit leaves downtown's towers (60 m and taller, and the skyline's own ways)
        # to ``_skyline``
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        towers = {b.get("way") for b in footprint().get("skyline", [])}
        self.env_counts = env.dress(self, self.venue, grade=GRADE, keep_out=[plaza], inner=plaza,
                                    exclude_ways=towers, block_max_height=SKYLINE_MIN_H,
                                    eyes=env.shot_eyes(mb_shots()))
        self._skyline()
        self._sky()

    def _skyline(self):
        """Downtown and Midtown's towers (OSM heights, 60 m and taller within 3.8 km): lit boxes to the east and
        north-east (the window to the city's view, the 2025 rooftop photo of the Bank of America Plaza)."""
        m = self.meshes.setdefault("mb_skyline", Mesh("mb_skyline"))
        for b in footprint().get("skyline", []):
            P = [tuple(p) for p in b["points"]]
            if len(P) < 3:
                continue
            A = np.array(P, float)
            if float(np.max(np.abs(A[:, 0]))) < 140.0 and float(np.max(np.abs(A[:, 1]))) < 170.0:
                continue
            height = float(b["height"])
            d = float(np.max(np.hypot(A[:, 0], A[:, 1])))
            far = self.p["skyline"]["far"]
            if d > far:
                # pass 3: inside the sky backdrop, along its bearing, the same size seen from the stadium
                A = A * (far / d)
                height *= far / d
            self._extrude(m, _min_rect(A), GRADE, GRADE + height, "LIGHT_mb_skyline", "mb_concrete",
                          uscale=1 / 30.0)

    def _sky(self):
        """The sky backdrop (pass 3; ``PARAMS["sky"]``): a cylinder round everything, facing in, its texture the sky of
        the bundle's hour (overcast in the rain and snow bundles by day), drawn at its own colour."""
        q = self.p["sky"]
        m = self.meshes.setdefault("mb_sky", Mesh("mb_sky"))
        R, n = q["radius"], q["points"]
        bot = [(R * math.cos(2 * math.pi * k / n), GRADE + q["bottom"], R * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
        top = [(x, GRADE + q["top"], z) for x, _y, z in bot]
        m.grid("mb_sky", [bot, top], [[(k / 12.0, 1.0) for k in range(n + 1)], [(k / 12.0, 0.0) for k in range(n + 1)]],
               facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))


def _min_rect(A):
    """The minimum-area rectangle round a footprint (four corners, counter-clockwise): the towers drawn as boxes."""
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


#: downtown's towers (the footprint's skyline: OSM heights of 60 m and more) are ``_skyline``'s boxes; the environment
#: kit draws the lower blocks
SKYLINE_MIN_H = 60.0


def build(venue=VENUE, params=None):
    return MercedesBenz(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "mb_seat_front": ("mb_seat_front", CLASS_OPAQUE), "mb_seat_mid": ("mb_seat_mid", CLASS_OPAQUE),
    "mb_seat_back": ("mb_seat_back", CLASS_OPAQUE), "mb_concrete": ("mb_concrete", CLASS_OPAQUE),
    "mb_wall": ("mb_wall", CLASS_OPAQUE), "LIGHT_mb_ribbon": ("LIGHT_mb_ribbon", CLASS_OPAQUE),
    "LIGHT_mb_glass": ("LIGHT_mb_glass", CLASS_OPAQUE), "LIGHT_mb_concourse": ("LIGHT_mb_concourse", CLASS_OPAQUE),
    "mb_portal": ("mb_portal", CLASS_OPAQUE), "mb_dark": ("mb_dark", CLASS_OPAQUE), "mb_black": ("mb_black", CLASS_OPAQUE),
    "mb_roof_under": ("mb_roof_under", CLASS_OPAQUE), "mb_ring": ("mb_ring", CLASS_OPAQUE),
    "mb_roof_top": ("mb_roof_top", CLASS_OPAQUE), "LIGHT_mb_lights": ("LIGHT_mb_lights", CLASS_OPAQUE),
    "LIGHT_mb_halo": ("LIGHT_mb_halo", CLASS_OPAQUE), "LIGHT_mb_window": ("LIGHT_mb_window", CLASS_ALPHA),
    "mb_panel": ("mb_panel", CLASS_OPAQUE), "mb_glass_out": ("mb_glass_out", CLASS_OPAQUE),
    "mb_panel_top": ("mb_panel", CLASS_OPAQUE), "mb_pinwheel": ("mb_pinwheel", CLASS_OPAQUE),
    "mb_star": ("mb_star", CLASS_ALPHA), "mb_sign": ("mb_sign", CLASS_ALPHA), "mb_name": ("mb_name", CLASS_OPAQUE),
    "LIGHT_mb_column": ("LIGHT_mb_column", CLASS_OPAQUE),
    "mb_plaza": ("mb_plaza", CLASS_OPAQUE), "LIGHT_mb_skyline": ("LIGHT_mb_skyline", CLASS_OPAQUE),
    "mb_sky": ("mb_sky", CLASS_OPAQUE), "mb_glass_base": ("mb_glass_base", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night. Under the closed roof the bowl is lit the same in
#: every time of day (the record stays indoor), a little warmer in the afternoon; outside, the sun by day and the lit
#: glass at night.
BASE = {
    "mb_seat_front": (212, 206, 198), "mb_seat_mid": (212, 206, 198), "mb_seat_back": (212, 206, 198),
    "crowd": (222, 216, 210), "mb_concrete": (206, 200, 192), "mb_wall": (230, 224, 220),
    "LIGHT_mb_ribbon": (255, 255, 255), "LIGHT_mb_glass": (196, 190, 255), "LIGHT_mb_concourse": (214, 208, 255),
    "mb_portal": (160, 156, 150), "mb_dark": (190, 186, 180), "mb_black": (200, 196, 190),
    "mb_roof_under": (230, 222, 150), "mb_ring": (200, 194, 150), "mb_roof_top": (236, 226, 110),
    "LIGHT_mb_lights": (255, 255, 255), "LIGHT_mb_halo": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    # pass 3 (main: "silver-grey metal, not white"): the petals at about their texture's own grey by day (the game draws
    # a texture modulated by twice its vertex colour: 226 had them near white); their facets over the roofline a little
    # lighter, facing the sky
    "LIGHT_mb_window": (240, 232, 255), "mb_panel": (146, 138, 120), "mb_glass_out": (214, 200, 110),
    "mb_panel_top": (176, 166, 110), "mb_pinwheel": (226, 214, 120), "mb_glass_base": (214, 200, 110),
    "mb_star": (240, 232, 150), "mb_sign": (236, 226, 140), "mb_name": (236, 230, 220), "LIGHT_mb_column": (255, 255, 255),
    "mb_plaza": (226, 210, 120), "LIGHT_mb_skyline": (214, 204, 255),
}
#: the sun over Atlanta (DESIGN): by day high in the south (bearing 180: game angle about -100 degrees, -x a little -z,
#: high), in the afternoon low in the west (bearing 250: -z, a little -x)
SUN = {"d": (-0.40, 0.86, -0.07), "a": (-0.22, 0.48, -0.85), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
#: rain and snow grey only what is outside: under the closed roof every weather looks dry
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"mb_roof_top", "mb_panel", "mb_panel_top", "mb_pinwheel", "mb_glass_out", "mb_glass_base", "mb_star",
           "mb_sign", "mb_plaza", "LIGHT_mb_skyline"}
#: inside the roof the light is the stadium's own: one level for every surface, whatever the sun outside (AT&T's rule)
INSIDE_LIGHT = 0.96


#: the live feed's vertex colour, the same in every light. The game copies its own previous frame (640 x 448) into the
#: jumbo_tron texture, and the screen draws that copy modulated by twice its vertex colour: in st2 lab 2 (2026-09-27,
#: PROVED IN GAME) the copy of the stands inside the AT&T board drew 2.0 to 2.3 times the stands themselves under the
#: bowl's vertex colour (245), so a screen that saw itself brightened on every pass and went solid white once it
#: filled the flyover's view (fly-029 to fly-034). At 116 the loop gain is about 1 (0.9 to 1.1 on that measurement):
#: the screen draws the picture as bright as the frame, and a screen in view of itself shows a steady nest of copies
#: instead of flooding white (retail's own screens: 204, 229, 255 under much smaller boards).
FEED_VERTEX = 116
#: the sky backdrop draws at its texture's own colour (twice 128)
SKY_VERTEX = 128


def light(mat, P, N, tod, weather, outside=False, occlusion=None):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
    if mat == "jumbo_tron":
        out = np.zeros((len(P), 4), np.uint8)
        out[:, :3] = FEED_VERTEX
        out[:, 3] = 255
        return out
    if mat == "mb_sky":
        out = np.zeros((len(P), 4), np.uint8)
        out[:, :3] = SKY_VERTEX
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
    if mat == "mb_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    if outside and weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat == "mb_roof_under" and tod == "n":
        # the panels at night: the black sky through them, the steel web lit from below (DESIGN)
        out[:, 0] = 96; out[:, 1] = 98; out[:, 2] = 108
    if mat in ("mb_glass_out", "mb_glass_base") and tod == "n":
        # the glass at night: lit from within, warm at the concourses (the 2019 night view on Commons)
        k = np.clip((P[:, 1] - GRADE) / 50.0, 0, 1)
        out[:, 0] = np.clip(220 - 120 * k, 0, 255); out[:, 1] = np.clip(206 - 110 * k, 0, 255)
        out[:, 2] = np.clip(190 - 90 * k, 0, 255)
    if mat in ("mb_panel", "mb_panel_top", "mb_star", "mb_sign") and tod == "n":
        # the petals at night: grey in the plaza lights and the city's glow
        out[:, 0] = 92; out[:, 1] = 94; out[:, 2] = 104
    if mat == "LIGHT_mb_window" and tod == "n":
        out[:, 0] = 170; out[:, 1] = 176; out[:, 2] = 196               # the window by night: the city's lights beyond
    return out


def _rgba(path):
    path = official.resolve_path(path)
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def sky_kind(tod, weather):
    """The sky backdrop's texture for one bundle: the hour's, or overcast in the rain and snow bundles by day."""
    return "o" if weather in "rs" and tod != "n" else tod


def _textures(venue, tod, weather):
    art = ART_DIR
    # MATERIALS order (deterministic across processes); the environment kit draws its own
    keys = [k for k in dict.fromkeys(k for k, _c in MATERIALS.values()) if not k.startswith("env_")]
    out = {key: _rgba(art / (f"mb_sky_{sky_kind(tod, weather)}.png" if key == "mb_sky" else f"{key}.png"))
           for key in keys}
    out.update(env.textures(venue, tod, weather))
    return out


#: the game's digits on the Halo's two graphics panels that face the sidelines (slot spacing, half width, half height,
#: metres) and their height on the panel (a fraction of the Halo's height: the digits' window in the panel's upper half)
DIGIT_SLOT, DIGIT_HW, DIGIT_HH, DIGIT_Y = 1.0, 0.46, 0.84, 0.63


def adjust_digits(shape, sc, model):
    """The score and clock digits onto the Halo's two graphics panels over the sidelines (the game's own digits: two
    strips, one per panel, in each panel's dark window, a little inside the ring); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    q = model.p["halo"]
    strips = []
    for fr in model.halo_frames:
        if fr["feed"] or abs(math.sin(fr["angle"])) > 0.5:
            continue
        centre = fr["centre"] + fr["face"] * 0.8 + np.array([0.0, q["h"] * (DIGIT_Y - 0.5), 0.0])
        strips.append(dict(centre=centre, right=fr["right"]))
    sb.require(len(strips) == 2, "the Halo has no two sideline graphics panels for the digits")
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
    """The four flare markers: over the light ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT (300 m)
    up (u6's lab 5, PROVED IN GAME at SoFi: no flare discs in the flyover and short night shadows). Out of every
    Mercedes-Benz Stadium shot too (test: Cameras)."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], sm.FLARE_HEIGHT, best[2]))
    return out


#: the field-level sponsor cloths: job u4's reviewed 2026 league sheet (``nfl2k5_modern_venues_2026.LEAGUE_ART``: the
#: eight defunct 2004 cloths as 2026 league type; Riddell, Gatorade and NFL.com kept) over the retail texture, carried
#: to each bundle's weather from the dry bundle as u4 carries it. The 2026 venue art cedes s01 to this model, so without
#: this the kept banners would show the 2004 cloths (AT&T's lab 1 at night, 2026-09-25, PROVED IN GAME at s07).
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
    """The Mercedes-Benz Stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "mb_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "mb_digits", tmpl_shape)
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
    """(bundle bytes, info): the retail bundle with its stadium scene replaced by the Mercedes-Benz Stadium model and its
    intro cameras rewritten when ``cameras`` gives the shots (s01 has no cityscape, as AT&T's s07). The stretch from the
    stadium chunk to the end of the cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    sb.require("cityscape" not in scenes, f"{filename}: s01 carries no cityscape; this bundle does")
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

#: The field (FieldTurf CORE, job u8's surfaces table: data/nfl2k5_modern_surfaces/venues.json): the retail s01 field is
#: turf, one flat colour quad between the goal lines, as s07's. The model paints the turf's light and dark 5-yard bands
#: (u runs along the field once the quad's UVs are remapped, in place), the turf outside the field of play, and lays the
#: Falcons' 2026 end zones and midfield from the league project's art (u4's ATL folder), composited over clean turf. The
#: surface word stays turf. s01's field has no Stadium_logo texture (PROVED OFFLINE); the code clears one only if present.
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
    """{material: RGBA} of the Falcons' field art in a league art root (``<root>/<team dir>/venue`` for prefix s01), or
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
    """The Mercedes-Benz Stadium field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at
    half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "mb_grass.png")
    outside = _rgba(FIELD_ART / "mb_grass_outside.png")
    for mat, art in ((GRASS_MATERIAL, grass), (OUTSIDE_MATERIAL, outside)):
        row = rows[mat]
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, _weather_look(a, weather), maximum=cap)
    clean = np.array(np.median(grass.reshape(-1, 4), axis=0), np.float32)

    def over_grass(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    # a retail field's stadium marks by the sidelines at midfield (s07's TEXAS STADIUM; s01 has none): cleared where
    # present (transparent: the overlay draws nothing)
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

#: The components each retail s01 intro camera's channel carries (PROVED OFFLINE from the retail s01dd, s01nd, s01ad and
#: s01ns intro cameras): camera 1 all five; camera 2 all five and roll; cameras 3 and 4 no pitch (they play level);
#: camera 5 no x (it plays on x = 0). A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw", "roll"},
                             {"x", "y", "z", "yaw"}, {"x", "y", "z", "yaw"}, {"y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the Mercedes-Benz Stadium flyover, one shot per retail camera, each wanting 0 wherever its camera
#: carries nothing.
#: 1: outside from the east (Centennial Olympic Park's side), sliding across the window to the city, the star left of it
#:    and the sign right of it, downtown behind the camera;
#: 2: a crane rising in the west end zone toward the Halo and the closed pinwheel;
#: 3 (level): the Halo close, gliding along it at its height;
#: 4 (level): outside from the south-west at the petals' mid-height, gliding east along the metal and glass;
#: 5 (on the axis): field level in the west end zone, looking east down the field to the window, drifting forward.
_OUTSIDE = dict(eye=(-60.0, 50.0, 420.0), target=(0.0, 40.0, 120.0), fov=38.0, rates=dict(x=6.0, z=-4.0))
_CRANE = dict(eye=(6.0, 8.0, -58.0), target=(0.0, 62.0, 40.0), fov=46.0, rates=dict(y=2.4, pitch=0.6))
_HALO = dict(eye=(30.0, 62.0, -20.0), target=(-60.0, 62.0, 40.0), fov=44.0, rates=dict(x=-2.0, z=3.0, yaw=-2.5))
_PASS = dict(eye=(-300.0, 40.0, -260.0), target=(0.0, 40.0, -20.0), fov=40.0, rates=dict(x=8.0, z=5.0, yaw=0.6))
_FIELD_WEST = dict(eye=(0.0, 2.5, -58.0), target=(0.0, 30.0, 160.0), fov=44.0, rates=dict(z=3.0))
MB_SHOTS = [_OUTSIDE, _CRANE, _HALO, _PASS, _FIELD_WEST]


def mb_shots():
    out = []
    for s, present in zip(MB_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=mb_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s01 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s01 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the Mercedes-Benz Stadium stretch: from the stadium chunk to the end of the intro cameras."""
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
                                         progress=progress, label="Mercedes-Benz Stadium"):
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
    """(field span of the same size, receipt) for one retail bundle: the Mercedes-Benz Stadium field, graded by Modern colour when
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
    raise sb.ScneBuildError(f"{name}: the Mercedes-Benz Stadium field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_mercedes_benz_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_mercedes_benz_receipt/v1"
BUILD_CAPTION = "Mercedes-Benz Stadium for the Falcons (experimental)"
HELP_TEXT = (
    "The Atlanta Falcons' Mercedes-Benz Stadium (opened 2017), built as a new model for Falcons home games in every time of "
    "day: the red bowl with its 200 level, suites and tall 300 level, the Halo board round the roof's opening with the "
    "live feed and the score, the eight-panel pinwheel roof closed over the field, the window to the city at the east end "
    "with downtown beyond it, the metal and glass petals of the facade with the Mercedes-Benz star and the venue's sign "
    "where the building shows them, the site, and a new pregame flyover with exterior passes. The field is turf in 5-yard "
    "bands with the 2026 venue art's Falcons end zones and midfield when that option is on. The row reads Mercedes-Benz "
    "Stadium, Atlanta, GA; the roof stays closed (no rain or snow falls, as retail). The 2026 venue art leaves the "
    "Falcons' packages to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Mercedes-Benz Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Mercedes-Benz Stadium pins schema")
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
    """retail / applied / foreign for the Mercedes-Benz Stadium stretch of one of the nine bundles."""
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
    return Path(str(source) + ".mercedes-benz.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Mercedes-Benz Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s01 row."""
    from . import nfl2k5_mercedes_benz_venue as hv
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
    sb.require(state == ("applied" if enabled else "retail"), f"Mercedes-Benz Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_mercedes_benz")
def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Mercedes-Benz Stadium)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Falcons stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=mb_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_mercedes_benz")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s01 to it): the Mercedes-Benz Stadium field, stadium
    and cameras of the nine bundles, and the s01 row. The retail bundles come from ``retail_source``; the image's own
    bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the field is
    composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour still
    recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Falcons end zones and midfield go onto the new
    field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_mercedes_benz_venue as hv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Mercedes-Benz Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Mercedes-Benz Stadium needs retail Falcons packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Mercedes-Benz Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Mercedes-Benz Stadium bundle changed size")
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
        new_colour["mercedes_benz"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Mercedes-Benz Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Mercedes-Benz Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Mercedes-Benz Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_mercedes_benz_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Mercedes-Benz Stadium stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st2-mercedes-benz.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST2_MERCEDES_BENZ_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
