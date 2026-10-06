"""Hard Rock Stadium model (experimental): the Miami Dolphins' Hard Rock Stadium (Miami Gardens, opened 1987 as Joe
Robbie Stadium; the 2015 to 2016 modernization by HOK with Thornton Tomasetti, the shade canopy on its four spires) built
as the stadium scene of venue record s14 (retail Pro Player Stadium), all nine bundles (day, afternoon, night; dry, rain,
snow).

Job st2 (2026-09-28, tier 1 of the renovations plan), on u5's builder, u6's SoFi methods and st's Highmark, AT&T, Levi's,
Allegiant and Mercedes-Benz models. References (the Wikipedia article, the Dolphins' 2016 modernization sheet, Structure
magazine, OpenStreetMap, the retail s14 scene, the Commons photos 2016 to 2026) are cited in the st2 report. The scene:

* the aqua bowl in four stacks: the 100 level from the field wall (the 2015 renovation brought the sideline seats 25 ft
  closer), the club tier and the suites, and the 2004 building's upper deck (its extent read from the retail scene);
  crowd billboards in the retail convention, cut at every aisle (u6's method); the ribbons on the fascias;
* the shade canopy over the seats: the white TPO roof on its white steel, the translucent ETFE ring round the opening
  over the field, the opening's edge truss with the lamps under it and the arches over its long sides, the four white
  spires 357 ft over the ground with their sixty-four cables, and the eight super columns under the corners;
* the four corner boards (112 x 50 ft each) on the ``jumbo_tron`` material the game draws its live feed into (a crop of
  the feed at the picture's own aspect, never stretched, at the loop gain of about 1), each between two stat panels, the
  game's digits on the south-west board's;
* the white concrete building under the canopy with its spiral ramps at the corners, the venue's name as plain type on
  the canopy's fascia over both sidelines;
* outside the plaza, the shared environment kit (nfl2k5_stadium_environment, st3): the lots with their cars, the
  roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall), the digit shapes (moved onto the corner board's stat panels), the markers and the
  materials the executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x the north sideline toward bearing 31.4 degrees and -x the south sideline, the
Dolphins', where every retail stadium keeps the home sideline props; y up from the field; z along, +z the east end zone
toward bearing 121.4 degrees: OpenStreetMap's pitch) and centimetres in the game. The row keeps its open-air word (the
canopy leaves the field open). EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
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

OWNER = "nfl2k5_hard_rock_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_hard_rock_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s14"
VENUES = (VENUE,)
#: the plazas and the concourse gates sit above the field, which lies below the surrounding grade (DESIGN from the
#: the plazas over the field (DESIGN: the 2020 aerials show the building on a podium a little over the lots)
GRADE = 3.0
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

#: DESIGN, pass 1. The side keys follow Allegiant's plan loop: E the +x side (here the north sideline), W the -x side (the
#: south sideline, the Dolphins'), S the +z end (the east end), N the -z end (the west end). The wall line clears the
#: retail s14 sideline props and banners (x +-45.4, z +-61.7; PROVED OFFLINE). The stacks keep the 2004 building's upper
#: deck (the retail s14 scene, PROVED OFFLINE: the sideline upper deck from x 77.2 at 27.9 m to x 101 at 42.7 m, the end
#: upper deck from z 98.4 at 29.1 m to z 114.3 at 42.7 m) over a new 100 level: the 2015 renovation "moved seats 25
#: feet closer to the field on the north and south sidelines" (the Dolphins' 2016 modernization sheet, SOURCED), so the
#: sideline 100 level now runs from the field wall; the club tier and the suites between them.
PARAMS = dict(
    loop=dict(xe=46.5, xw=46.5, zs=63.5, zn=63.5, R=22.0, step=7.0, corner_steps=9),
    wall=dict(height=1.25),
    sides=dict(
        W=dict(low_d0=3.0, low_y0=1.5, low_rows=26, low_tread=0.84, low_rise0=0.32, low_rise1=0.62,
               t2_over=3.0, t2_rows=8, t2_rise=0.62, band_h=5.0,
               up_d=30.7, up_y=27.8, up_rows=27, up_tread=0.84, up_rise=0.50, back_wall=2.0),
        E=dict(low_d0=3.0, low_y0=1.5, low_rows=26, low_tread=0.84, low_rise0=0.32, low_rise1=0.62,
               t2_over=3.0, t2_rows=8, t2_rise=0.62, band_h=5.0,
               up_d=30.7, up_y=27.8, up_rows=27, up_tread=0.84, up_rise=0.50, back_wall=2.0),
        N=dict(low_d0=2.5, low_y0=1.4, low_rows=28, low_tread=0.84, low_rise0=0.28, low_rise1=0.42,
               t2_over=3.0, t2_rows=4, t2_rise=0.55, band_h=4.0,
               up_d=34.9, up_y=28.5, up_rows=18, up_tread=0.84, up_rise=0.70, back_wall=2.4),
        S=dict(low_d0=2.5, low_y0=1.4, low_rows=28, low_tread=0.84, low_rise0=0.28, low_rise1=0.42,
               t2_over=3.0, t2_rows=4, t2_rise=0.55, band_h=4.0,
               up_d=34.9, up_y=28.5, up_rows=18, up_tread=0.84, up_rise=0.70, back_wall=2.4),
    ),
    tier=dict(tread=0.84, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.4, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the shade canopy (the Dolphins' 2016 modernization sheet, SOURCED: about 626,000 sq ft, 530,000 of white TPO
    #: membrane and 94,000 of translucent ETFE "immediately adjacent to the ocular over the field"; the four spires "rise
    #: an additional 200 feet above the roof surface achieving a total height of 357 feet from the ground"). Pass 2: the
    #: plan from the Esri World Imagery orthophoto (reference only; roof features centred on their own centre to remove
    #: the relief displacement, INFERRED +-3 m): the outline 219 x 281 m, the ETFE ring's outer edge 109 x 165 m, the
    #: opening 88 x 126 m, the spires at x +-80, z +-96. The heights on the solved 2026 press-box pose (PROVED OFFLINE,
    #: 1.3 px on eight field-line points) with that plan: the lamps under the opening's edge truss at 36.5 to 38.2 m, the
    #: truss's top 46.9 m, the arches over it to about 57 m, their feet 45 m either side of the long sides' middle; the
    #: roof's surface 157 ft over the ground (SOURCED, the ground taken as the field); the underside rising from the
    #: truss to the outline (DESIGN between the measured truss and the upper deck's top rows). Heights over the field.
    canopy=dict(hx=110.0, hz=141.0, r=6.0, ex=55.0, ez=83.0, er=4.0, ox=44.0, oz=63.0, orr=3.0, n=4,
                top=47.9, top_etfe=47.6, truss_top=47.0, under_out=46.8, under_etfe=42.5, truss_bottom=38.5,
                arch=10.0, arch_depth=3.0, arch_long=45.0, arch_short=30.0, rise_t=0.5),
    #: the four spires (SOURCED: 357 ft over the ground) at the orthophoto's mast circles (INFERRED; the press-box pose's
    #: ray through the north-east tip at that height lands 7 m further out), each on its
    #: transfer truss over a corner; the 64 cables (Structure magazine: "sixty-four locked coil steel cables, up to 300
    #: feet in length"), sixteen per spire; the eight super columns (SOURCED count) in pairs outside each corner (DESIGN
    #: places)
    masts=dict(x=80.0, z=96.0, top=108.8, r0=4.0, r1=0.4, sides=8, cables=16, col=((109.0, 88.0), (78.0, 123.0)),
               col_w=5.0),
    #: the four corner boards (the modernization sheet: "four 1,472-inch screens in each corner of the stadium for a total
    #: of 22,400 sq. ft.": 5,600 sq ft and a 122.7 ft diagonal each, so about 112 x 50 ft), hung from the canopy over the
    #: bowl's corners: pass 2 fits two of them on the solved press-box pose as mirror images (PROVED OFFLINE, 2.9 px on
    #: eight corners): centres at x +-65.6, z +-77.9, 28.3 to 43.5 m, turned 6.8 degrees off the field's centre (the
    #: bottom set 0.3 m lower so the tops clear the canopy's underside)
    boards=dict(x=65.6, z=77.9, w=34.1, h=15.2, bottom=28.0, depth=3.0, feed=0.76, yaw=-6.8),
    #: the building's walls under the canopy and the spiral ramps at its corners (the 2020 aerials, DESIGN sizes)
    facade=dict(top=41.0, ramp_r=10.0, ramp_h=34.0, ramp_push=14.0, sign_w=62.0),
    lights=dict(every=8.0, w=4.4, h=2.2, drop=1.2),
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

class HardRock(sm.SoFi):
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

    def board_specs(self):
        """The four corner boards: centre (x, z), the unit vector along each board's width, its width, bottom and depth,
        and the unit vector its picture faces (toward the field's centre). Board 0 (the south-west corner) carries the
        game's digits."""
        q = self.p["boards"]
        out = []
        for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            c = (sx * q["x"], sz * q["z"])
            ang = math.atan2(-c[1], -c[0]) + math.radians(q.get("yaw", 0.0) * (1 if sx * sz > 0 else -1))
            f = np.array([math.cos(ang), math.sin(ang)])
            out.append(dict(c=c, along=(float(f[1]), float(-f[0])), face=(float(f[0]), float(f[1])), w=q["w"],
                            bottom=q["bottom"], depth=q["depth"], margin=1.0))
        return out

    # -- the canopy ---------------------------------------------------------------------------------------------------
    def canopy_ring(self, which):
        """The canopy's outline ("outer"), the ETFE ring's outer edge ("etfe") or the opening ("hole"), as
        rounded_rect points (the same count each, so rings join point for point)."""
        q = self.p["canopy"]
        hx, hz, r = {"outer": (q["hx"], q["hz"], q["r"]), "etfe": (q["ex"], q["ez"], q["er"]),
                     "hole": (q["ox"], q["oz"], q["orr"])}[which]
        return rounded_rect(hx, hz, r, q["n"])

    def _canopy_t(self, x, z):
        """How far (x, z) lies from the ETFE ring's edge (0) out to the outline (1), by the rectangles' sides."""
        q = self.p["canopy"]
        return min(1.0, max(0.0, (abs(x) - q["ex"]) / (q["hx"] - q["ex"]), (abs(z) - q["ez"]) / (q["hz"] - q["ez"])))

    def roof_height(self, x, z):
        """The canopy's underside over (x, z): rising from the opening's edge truss over the ETFE ring and on up to the
        outline."""
        q = self.p["canopy"]
        if abs(x) <= q["ex"] and abs(z) <= q["ez"]:
            return q["under_etfe"]
        return q["under_etfe"] + (q["under_out"] - q["under_etfe"]) * min(1.0, self._canopy_t(x, z) / q["rise_t"])

    def _canopy(self):
        """The canopy: the white TPO roof on its white steel from the outline in to the ETFE ring, the translucent ETFE
        ring down to the opening's edge truss, the outer fascia, the lamps under the edge truss and the arches over the
        opening's four sides (the 2026 press-box and end zone views, the 2020 aerials, the orthophoto)."""
        q = self.p["canopy"]
        outer, etfe, hole = self.canopy_ring("outer"), self.canopy_ring("etfe"), self.canopy_ring("hole")
        close = lambda P: list(P) + [P[0]]  # noqa: E731
        O, E, H = close(outer), close(etfe), close(hole)
        pl = lambda x, z, s=24.0: (x / s, z / s)  # noqa: E731
        # the underside: three rings from the outline in to the ETFE's edge, so its rise follows the rectangle's sides
        und = self.meshes.setdefault("hr_canopy_under", Mesh("hr_canopy_under"))
        rings = []
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            rings.append([(ox_ + (ex_ - ox_) * f, None, oz_ + (ez_ - oz_) * f) for (ox_, oz_), (ex_, ez_) in zip(O, E)])
        rows = [[(x, self.roof_height(x, z), z) for x, _y, z in r] for r in rings]
        und.grid("hr_roof_under", rows, [[pl(x, z) for x, _y, z in r] for r in rows], facing=down)
        und.grid("hr_etfe", [[(x, q["under_etfe"], z) for x, z in E], [(x, q["truss_bottom"], z) for x, z in H]],
                 [[pl(x, z, 16.0) for x, z in E], [pl(x, z, 16.0) for x, z in H]], facing=down)
        top = self.meshes.setdefault("hr_canopy_top", Mesh("hr_canopy_top"))
        top.grid("hr_roof_top", [[(x, q["top"], z) for x, z in O], [(x, q["top_etfe"], z) for x, z in E]],
                 [[pl(x, z, 18.0) for x, z in O], [pl(x, z, 18.0) for x, z in E]], facing=up)
        top.grid("hr_etfe", [[(x, q["top_etfe"], z) for x, z in E], [(x, q["truss_top"], z) for x, z in H]],
                 [[pl(x, z, 16.0) for x, z in E], [pl(x, z, 16.0) for x, z in H]], facing=up)
        # the outer fascia
        L = [0.0]
        for a, b in zip(O[:-1], O[1:]):
            L.append(L[-1] + math.dist(a, b))
        top.grid("hr_roof_edge", [[(x, q["under_out"], z) for x, z in O], [(x, q["top"], z) for x, z in O]],
                 [[(s / 12.0, 1.0) for s in L], [(s / 12.0, 0.0) for s in L]], facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
        # the opening's edge truss, seen from the field and from above
        LH = [0.0]
        for a, b in zip(H[:-1], H[1:]):
            LH.append(LH[-1] + math.dist(a, b))
        tr = self.meshes.setdefault("hr_canopy_truss", Mesh("hr_canopy_truss"))
        rows = [[(x, q["truss_bottom"], z) for x, z in H], [(x, q["truss_top"], z) for x, z in H]]
        uvs = [[(s / 14.0, 1.0) for s in LH], [(s / 14.0, 0.0) for s in LH]]
        tr.grid("hr_truss", rows, uvs, facing=lambda p_: np.array([-p_[0], 0.0, -p_[2]]))
        tr.grid("hr_truss", rows, uvs, facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
        # the arches over the opening's four sides (bow-string lattices on the edge truss: the 2026 end zone and press-box
        # views show them over the ends and the sidelines)
        ar = self.meshes.setdefault("hr_canopy_arches", Mesh("hr_canopy_arches"))
        for axis, half, other, rise in (("z", q["arch_long"], q["ox"], q["arch"]), ("x", q["arch_short"], q["oz"], q["arch"] * 0.86)):
            ts = np.linspace(-half, half, 17 if axis == "z" else 11)
            for s_ in (1, -1):
                def pt(t, y):
                    return (s_ * other, y, float(t)) if axis == "z" else (float(t), y, s_ * other)
                lo = [pt(t, q["truss_top"] + rise * (1 - math.pow(t / half, 2))) for t in ts]
                hi = [(x, y + q["arch_depth"], z) for x, y, z in lo]
                base_ = [pt(t, q["truss_top"]) for t in ts]
                u = [(float(t) / 12.0, 1.0) for t in ts]
                u2 = [(float(t) / 12.0, 0.0) for t in ts]
                nrm = np.array([1.0, 0.0, 0.0]) if axis == "z" else np.array([0.0, 0.0, 1.0])
                for f in (nrm, -nrm):
                    ar.grid("hr_arch", [lo, hi], [u, u2], facing=lambda p_, f=f: f)
                    ar.grid("hr_arch", [base_, lo], [u, u2], facing=lambda p_, f=f: f)
        self.light_points = []
        lm = self.meshes.setdefault("hr_lights", Mesh("hr_lights"))
        ql = self.p["lights"]
        Ls = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(H[:-1], H[1:])])])
        for sv in np.arange(ql["every"] / 2, Ls[-1], ql["every"]):
            j = min(int(np.searchsorted(Ls, sv, side="right")) - 1, len(H) - 2)
            a, b = H[j], H[j + 1]
            t = (sv - Ls[j]) / max(Ls[j + 1] - Ls[j], 1e-9)
            if True:
                x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                n = np.array([x, 0.0, z]); n /= max(1e-9, math.np_norm(n))
                ctr = np.array([x, q["truss_bottom"] - ql["drop"], z])
                along = np.array([-n[2], 0.0, n[0]])
                normal = -n * math.cos(math.radians(50)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(50))
                upv = np.cross(along, normal); upv = upv / math.np_norm(upv) * (1.0 if upv[1] > 0 else -1.0)
                hw, hh = along * (ql["w"] / 2), upv * (ql["h"] / 2)
                lm.quad("LIGHT_hr_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1), (1, 0),
                        (0, 0), facing=lambda p_, nn=normal: nn)
                self.light_points.append(tuple(ctr))

    def _masts(self):
        """The four spires from the canopy's top to 357 ft over the ground, the eight super columns under the canopy's
        corners and the sixteen cables from each spire's head to the canopy."""
        q, c = self.p["masts"], self.p["canopy"]
        G = GRADE
        m = self.meshes.setdefault("hr_masts", Mesh("hr_masts"))
        S = q["sides"]
        heads = []
        for sx in (1, -1):
            for sz in (1, -1):
                cx, cz = sx * q["x"], sz * q["z"]
                y0, y1 = c["top"], q["top"]
                ring = lambda y, r: [(cx + r * math.cos(2 * math.pi * k / S), y, cz + r * math.sin(2 * math.pi * k / S))  # noqa: E731
                                     for k in range(S + 1)]
                m.grid("hr_mast", [ring(y0, q["r0"]), ring(y1, q["r1"])],
                       [[(k / S, 1.0) for k in range(S + 1)], [(k / S, 0.0) for k in range(S + 1)]],
                       facing=lambda p_, cx=cx, cz=cz: np.array([p_[0] - cx, 0.0, p_[2] - cz]))
                heads.append((cx, cz))
        col = self.meshes.setdefault("hr_columns", Mesh("hr_columns"))
        hw = q["col_w"] / 2
        for (px, pz) in q["col"]:
            for sx in (1, -1):
                for sz in (1, -1):
                    ctr = np.array([sx * px, (G + c["under_out"]) / 2, sz * pz])
                    col.box("hr_column", ctr, ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (hw, (c["under_out"] - G) / 2, hw), uvscale=0.15)
        # the cables: from the head (the top 8 m of the spire) out to anchors on the canopy's top, half on the outline and
        # half on the ETFE ring's edge, the eight each side of the corner nearest the spire
        cb = self.meshes.setdefault("hr_cables", Mesh("hr_cables"))
        outer, etfe = self.canopy_ring("outer"), self.canopy_ring("etfe")
        per = q["cables"] // 2
        for (cx, cz) in heads:
            for ring_, lift in ((outer, 0.0), (etfe, c["top_etfe"] - c["top"])):
                d = [math.hypot(x - cx, z - cz) for x, z in ring_]
                k0 = int(np.argmin(d))
                n = len(ring_)
                picks = [ring_[(k0 + j) % n] for j in range(-(per // 2) * 2, (per // 2) * 2, 2)]
                for j, (ax, az) in enumerate(picks):
                    head = np.array([cx, q["top"] - 1.0 - 7.0 * j / max(1, per - 1), cz])
                    foot = np.array([ax, c["top"] + lift + 0.2, az])
                    v = foot - head
                    side = np.cross(v, (0.0, 1.0, 0.0)); side = side / max(1e-9, math.np_norm(side)) * 0.15
                    upv = np.cross(side, v); upv = upv / max(1e-9, math.np_norm(upv)) * 0.15
                    for off in (side, upv):
                        cb.quad("hr_cable", head - off, head + off, foot + off, foot - off, (0, 0), (1, 0), (1, 1), (0, 1),
                                facing=lambda p_, n_=np.cross(off, v): n_)
                        cb.quad("hr_cable", head - off, head + off, foot + off, foot - off, (0, 0), (1, 0), (1, 1), (0, 1),
                                facing=lambda p_, n_=-np.cross(off, v): n_)

    def _boards(self, loop, secs):
        """The four corner boards under the canopy (board 0 with the game's digits on its left panel)."""
        q = self.p["boards"]
        m = self.meshes.setdefault("hr_boards", Mesh("hr_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        for k, b in enumerate(self.board_specs()):
            (cx, cz), (fx, fz) = b["c"], b["face"]
            face = np.array([fx, 0.0, fz])
            c = np.array([cx, q["bottom"], cz]) - face * (q["depth"] / 2 + 0.05)
            self._board(m, c, face, q["w"], q["h"], feed=q["feed"], frames=self.board_frames)

    def _facade(self):
        """The building under the canopy (the 2020 aerials and the 2026 exteriors): white concrete levels with dark
        ribbon windows on the facade outline (DESIGN), the spiral ramps at its corners and the venue's name as plain type
        on the canopy's fascia over both sidelines."""
        q = self.p["facade"]
        G = GRADE
        ring, _pos = self.facade_ring(96)
        R = list(ring) + [ring[0]]
        L = [0.0]
        for a, b in zip(R[:-1], R[1:]):
            L.append(L[-1] + math.dist(a, b))
        m = self.meshes.setdefault("hr_facade", Mesh("hr_facade"))
        m.grid("hr_facade", [[(x, G - 0.5, z) for x, z in R], [(x, G + q["top"], z) for x, z in R]],
               [[(s / 30.0, 1.0) for s in L], [(s / 30.0, 0.0) for s in L]], facing=lambda p_: np.array([p_[0], 0.0, p_[2]]))
        cx, cz = np.mean(ring, axis=0)
        rp = self.meshes.setdefault("hr_ramps", Mesh("hr_ramps"))
        fp = np.array(ring)
        for sx in (1, -1):
            for sz in (1, -1):
                k = int(np.argmax(fp[:, 0] * sx + fp[:, 1] * sz))
                v = np.array([sx, sz], float) / math.sqrt(2.0)
                c0 = fp[k] + v * (q["ramp_r"] + q["ramp_push"] - q["ramp_r"])
                S = 12
                ringp = lambda y: [(c0[0] + q["ramp_r"] * math.cos(2 * math.pi * j / S), y,  # noqa: E731
                                    c0[1] + q["ramp_r"] * math.sin(2 * math.pi * j / S)) for j in range(S + 1)]
                rp.grid("hr_ramp", [ringp(G - 0.5), ringp(G + q["ramp_h"])],
                        [[(j / 3.0, 3.0) for j in range(S + 1)], [(j / 3.0, 0.0) for j in range(S + 1)]],
                        facing=lambda p_, c0=c0: np.array([p_[0] - c0[0], 0.0, p_[2] - c0[1]]))
                rp.grid("hr_concrete", [ringp(G + q["ramp_h"]), [(c0[0], G + q["ramp_h"], c0[1])] * (S + 1)],
                        [[(0.0, 0.0)] * (S + 1), [(0.5, 0.5)] * (S + 1)], facing=up)
        sg = self.meshes.setdefault("hr_signs", Mesh("hr_signs"))
        c = self.p["canopy"]
        w, h = q["sign_w"], (c["top"] - c["under_out"]) * 0.8
        for sx in (1, -1):
            x = sx * (c["hx"] + 0.15)
            y0 = c["under_out"] + (c["top"] - c["under_out"] - h) / 2
            a, b = (x, y0, sx * w / 2), (x, y0, -sx * w / 2)
            sg.quad("hr_letters", a, b, (b[0], y0 + h, b[2]), (a[0], y0 + h, a[2]), (0, 1), (1, 1), (1, 0), (0, 0),
                    facing=lambda p_, sx=sx: np.array([sx, 0.0, 0.0]))

    # -- Allegiant's generic methods (copied; Hard Rock's own) ----------------------------------------------
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
        if name.startswith("hr_bowl_"):
            name = getattr(self, "prefix", "hr_bowl")
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
        for mat, i0, i1 in (("hr_seat_front", 0, a), ("hr_seat_mid", a, b), ("hr_seat_back", b, len(ks) - 1)):
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
            self._rows_surface(m, "hr_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("hr_bowl_a")
        wall = p["wall"]["height"]
        m.grid("hr_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("hr_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "hr_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        self._band(m, "LIGHT_hr_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        m2 = self.mesh("hr_bowl_b")
        self._ledge(m2, "hr_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_hr_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_hr_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "hr_concrete", loop, secs, "band_floor", up)
        m4 = self.mesh("hr_bowl_d")
        self._band(m4, "LIGHT_hr_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("hr_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                    [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_hr_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall and its walk, and behind them the concourse levels up to the roof
        # (the building is enclosed: from inside, a dark concourse band closes the gap under the roof)
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            m4.grid("LIGHT_hr_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                           [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("hr_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
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
                    m4.grid("hr_dark", [[self.at(q_, r_[3], r_[2]) for q_, r_ in sub],
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
            m.quad("hr_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
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
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= math.np_norm(right)
        hv = np.array([0.0, H, 0.0])
        m.box("hr_black", c + hv / 2, (right, (0, 1, 0), face), (W / 2 + 0.6, H / 2 + 0.6, q["depth"] / 2), uvscale=0.1,
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
                m.quad("LIGHT_hr_board_panel", pc - ph, pc + ph, pc + ph + hv, pc - ph + hv, (0, 1), (1, 1), (1, 0),
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
        m = self.meshes.setdefault("hr_plaza", Mesh("hr_plaza"))

        def grow(k):
            out = []
            for x, z in R:
                v = np.array([x - cx, z - cz]); v /= math.np_norm(v)
                out.append((x + v[0] * k, GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(12.0), grow(36.0)]
        uv = lambda P: [(x / 20.0, z / 20.0) for x, _y, z in P]  # noqa: E731
        m.grid("hr_plaza", rings, [uv(r) for r in rings], facing=up)
        # the environment kit (st3, nfl2k5_stadium_environment): outside the plaza, the lots with their cars, the
        # roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon band
        # at 1,800 m
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        self.env_counts = env.dress(self, self.venue, grade=GRADE, keep_out=[plaza], inner=plaza,
                                    eyes=env.shot_eyes(hard_rock_shots()))

    # -- build --------------------------------------------------------------------------------------------------
    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"hr_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "hr"
        self._canopy()
        self._masts()
        self._boards(loop, secs)
        east = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(east)["upper"][4]
        self.nosebleed = self.at(east, row[0] + 0.3, row[1] + 0.05)
        self._facade()
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
        pu, pv = math.np_matmul(A - c, u), math.np_matmul(A - c, v)
        area = np.ptp(pu) * np.ptp(pv)
        if best is None or area < best[0]:
            best = (area, u, v, pu.min(), pu.max(), pv.min(), pv.max())
    _a, u, v, u0, u1, v0, v1 = best
    return [tuple(c + u * a + v * b) for a, b in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]


def build(venue=VENUE, params=None):
    return HardRock(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "hr_seat_front": ("hr_seat_front", CLASS_OPAQUE), "hr_seat_mid": ("hr_seat_mid", CLASS_OPAQUE),
    "hr_seat_back": ("hr_seat_back", CLASS_OPAQUE), "hr_concrete": ("hr_concrete", CLASS_OPAQUE),
    "hr_wall": ("hr_wall", CLASS_OPAQUE), "LIGHT_hr_ribbon": ("LIGHT_hr_ribbon", CLASS_OPAQUE),
    "LIGHT_hr_glass": ("LIGHT_hr_glass", CLASS_OPAQUE), "LIGHT_hr_concourse": ("LIGHT_hr_concourse", CLASS_OPAQUE),
    "hr_portal": ("hr_portal", CLASS_OPAQUE), "hr_dark": ("hr_dark", CLASS_OPAQUE), "hr_black": ("hr_black", CLASS_OPAQUE),
    "hr_roof_under": ("hr_roof_under", CLASS_OPAQUE), "hr_roof_top": ("hr_roof_top", CLASS_OPAQUE),
    "hr_roof_edge": ("hr_roof_edge", CLASS_OPAQUE), "hr_etfe": ("hr_etfe", CLASS_ALPHA),
    "hr_truss": ("hr_truss", CLASS_ALPHA), "hr_arch": ("hr_arch", CLASS_ALPHA),
    "hr_mast": ("hr_mast", CLASS_OPAQUE), "hr_cable": ("hr_cable", CLASS_OPAQUE),
    "LIGHT_hr_lights": ("LIGHT_hr_lights", CLASS_OPAQUE), "LIGHT_hr_board_panel": ("LIGHT_hr_board_panel", CLASS_OPAQUE),
    "hr_letters": ("hr_letters", CLASS_ALPHA), "hr_facade": ("hr_facade", CLASS_OPAQUE), "hr_ramp": ("hr_ramp", CLASS_OPAQUE),
    "hr_column": ("hr_column", CLASS_OPAQUE),
    "hr_plaza": ("hr_plaza", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night. Under the canopy the bowl sits in its shade by
#: day (the sheet: 92 percent of the fans in the shade), lit by the lamps at night; outside, the sun by day
BASE = {
    "hr_seat_front": (206, 204, 196), "hr_seat_mid": (206, 204, 196), "hr_seat_back": (206, 204, 196),
    "crowd": (218, 214, 208), "hr_concrete": (206, 202, 194), "hr_wall": (230, 226, 220),
    "LIGHT_hr_ribbon": (255, 255, 255), "LIGHT_hr_glass": (190, 186, 255), "LIGHT_hr_concourse": (214, 208, 255),
    "hr_portal": (160, 156, 150), "hr_dark": (190, 186, 180), "hr_black": (200, 196, 190),
    "hr_roof_under": (214, 206, 170), "hr_roof_top": (236, 226, 130), "hr_roof_edge": (232, 222, 140),
    "hr_etfe": (240, 234, 200), "hr_truss": (238, 232, 190), "hr_arch": (240, 232, 150),
    "hr_mast": (242, 232, 140), "hr_cable": (220, 214, 170),
    "LIGHT_hr_lights": (255, 255, 255), "LIGHT_hr_board_panel": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    "hr_letters": (255, 255, 255), "hr_facade": (224, 212, 120), "hr_ramp": (224, 212, 120), "hr_column": (224, 212, 120),
    "hr_plaza": (226, 210, 120),
}
#: the sun over Miami Gardens (DESIGN): by day high in the south (bearing 180: -x and a little +z, high), in the
#: afternoon low in the west-south-west (bearing 250: -x and -z)
SUN = {"d": (-0.43, 0.87, 0.26), "a": (-0.68, 0.50, -0.54), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
#: rain and snow grey what is outside (the canopy and the building); the bowl under the canopy keeps its light
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.90, 0.92, 0.96)}
OUTSIDE = {"hr_roof_top", "hr_roof_edge", "hr_etfe", "hr_arch", "hr_mast", "hr_cable", "hr_letters", "hr_facade",
           "hr_ramp", "hr_column", "hr_plaza"}
#: under the canopy the light is its shade's: one level for every surface there, whatever the sun outside
INSIDE_LIGHT = 0.88


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
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.76 + 0.26 * nd) if tod == "d" else (0.64 + 0.45 * nd)
    if mat == "hr_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    if outside and weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat in ("hr_roof_top", "hr_roof_edge", "hr_mast", "hr_cable", "hr_arch", "hr_etfe") and tod == "n":
        # the canopy and the spires at night: grey in the glow of the lamps under the canopy and the lots
        out[:, 0] = 104; out[:, 1] = 106; out[:, 2] = 116
    if mat in ("hr_facade", "hr_ramp", "hr_column") and tod == "n":
        k = np.clip((P[:, 1] - GRADE) / 45.0, 0, 1)
        out[:, 0] = np.clip(150 - 70 * k, 0, 255); out[:, 1] = np.clip(146 - 70 * k, 0, 255); out[:, 2] = np.clip(140 - 60 * k, 0, 255)
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
                centre = np.array([-side * 0.9 * zs, 2.7, zs * (wall_z - 0.08)])
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


#: the away bench area's pieces end here (metres, +x): the retail s14 props reach x 45.4 (PROVED OFFLINE), so none moves
PROP_LIMIT_X = 46.4


def flare_points(model):
    """The four flare markers: over the roof's floodlight ring at its 45, 135, 225 and 315 degree points, u6's FLARE_HEIGHT
    (300 m) up (u6's lab 5, PROVED IN GAME at SoFi: no flare discs in the flyover, short night shadows under the feet).
    Out of every Hard Rock Stadium shot too (test: Cameras)."""
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
    """The dry bundle of the same time of day (s14nr.iff -> s14nd.iff)."""
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
    """The Hard Rock Stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "hr_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "hr_digits", tmpl_shape)
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
    its stadium scene replaced by the Hard Rock Stadium model and its intro cameras rewritten when ``cameras`` gives the shots.
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

#: The field (Platinum TE Paspalum, the Dolphins' 2016 modernization sheet): the retail s14 field is grass, one flat colour
#: quad between the goal lines. The model paints it mown in 5-yard bands (u runs along the field once the quad's UVs are
#: remapped, in place), the grass outside the field of play, and the Dolphins' 2026 end zones and midfield from the
#: league project's art (the u4 MIA venue folder), composited over clean grass. The retail s14 field gives each end its
#: own three textures (endzone_N_* at -z, the west end here, endzone_S_* at +z; PROVED OFFLINE, test: Field), so each
#: end's art goes straight onto its own panels.
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
    """{material: RGBA} of the Dolphins' field art in a league art root (``<root>/<team dir>/venue`` for prefix s14), or
    {} when the root has none."""
    if not art_root:
        return {}
    from . import nfl2k5_modern_venues_2026 as mv
    art = mv.load_art(art_root)
    venue = art["venues"].get(VENUE)
    if venue is None:
        return {}
    from . import nfl2k5_midfield_art as midfield_art
    result = midfield_art.TeamField({item["key"]: np.asarray(item["rgba"]) for item in venue["items"]
                                   if item.get("scene") == "field" and item.get("key") in TEAM_FIELD})
    result.add_missing_midfield = venue.get("add_missing_midfield", False)
    return result


def paint_field(decoded, rec, system, weather, *, team=None, cap=256, half=False):
    """The Hard Rock Stadium field for one bundle (decoded, the retail layout kept); ``half`` draws the team marks at half detail
    (u6's ``_half_detail``: each texel doubled, for the small snow spans)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass = _rgba(FIELD_ART / "hr_grass.png")
    outside = _rgba(FIELD_ART / "hr_grass_outside.png")
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

#: The components each retail s14 intro camera's channel carries (PROVED OFFLINE from the retail s14dd, s14ad, s14nd
#: and s14ns intro cameras): camera 1 all five; camera 2 all but x, with roll (it plays on x = 0); camera 3 all but x;
#: camera 4 no pitch (it plays level); camera 5 all five. A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"y", "z", "pitch", "yaw", "roll"}, {"y", "z", "pitch", "yaw"},
                             {"x", "y", "z", "yaw"}, {"x", "y", "z", "pitch", "yaw"})

#: DESIGN, pass 1: the Hard Rock Stadium flyover, one shot per retail camera, each wanting 0 wherever its camera carries
#: nothing.
#: 1: outside from the south-west over the lots, the canopy on its four spires and the ramps, drifting north-east;
#: 2 (on the axis): a crane rising in the west end zone toward the east end, the canopy's opening and two corner boards;
#: 3 (on the axis): high over the west half, panning across the east end's corner boards under the canopy;
#: 4 (level): outside to the north at the spires' mid-height, gliding east along the canopy's edge;
#: 5: field level in the east end zone, looking west down the field under the canopy.
_OUTSIDE = dict(eye=(-300.0, 80.0, -320.0), target=(0.0, 30.0, 0.0), fov=38.0, rates=dict(x=6.0, z=5.0))
_CRANE = dict(eye=(0.0, 6.0, -58.0), target=(0.0, 30.0, 60.0), fov=46.0, rates=dict(y=2.2, pitch=0.8))
_EAST = dict(eye=(0.0, 36.0, -30.0), target=(40.0, 34.0, 90.0), fov=44.0, rates=dict(z=2.0, yaw=-5.0))
_ALONG = dict(eye=(340.0, 76.0, -170.0), target=(0.0, 76.0, 0.0), fov=40.0, rates=dict(z=10.0))
_FIELD_EAST = dict(eye=(6.0, 2.5, 58.0), target=(0.0, 28.0, -140.0), fov=44.0, rates=dict(z=-3.0, yaw=1.0))
HR_SHOTS = [_OUTSIDE, _CRANE, _EAST, _ALONG, _FIELD_EAST]


def hard_rock_shots():
    out = []
    for s, present in zip(HR_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=hard_rock_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256, sites)} of the nine s14 bundles (u4's venue
    table)."""
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    """{bundle name: retail bytes} of the nine s14 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the Hard Rock Stadium stretch: from the cityscape chunk to the end of the intro cameras."""
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
                                         workers=workers, progress=progress, label="Hard Rock Stadium"):
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
    """(field span of the same size, receipt) for one retail bundle: the Hard Rock Stadium field, graded by Modern colour when its
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
            midfield = None
            if getattr(team, "add_missing_midfield", False):
                from . import nfl2k5_midfield_art as midfield_art
                after, midfield = midfield_art.append_span(after, name, team["center_logo"])
            sb.require(len(after) == len(span), f"{name}: the field escaped its span")
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               team_art=sorted(team or {}), midfield=midfield,
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{rung}: {exc}")
    raise sb.ScneBuildError(f"{name}: the Hard Rock Stadium field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_hard_rock_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_hard_rock_receipt/v1"
BUILD_CAPTION = "Hard Rock Stadium for the Dolphins (experimental)"
HELP_TEXT = (
    "The Miami Dolphins' Hard Rock Stadium as it stands since its 2016 modernization, built as a new model for Dolphins "
    "home games: the aqua bowl with the 100 level brought closer to the sidelines, the club tier, the suites and the "
    "upper deck, the white shade canopy over the seats with the translucent ring round the open field, the four white "
    "spires and their cables, the four corner boards with the live feed and the score, the building with its spiral "
    "ramps, the lots, roads, trees and blocks round it to the horizon, and a new pregame flyover with exterior passes. "
    "The field is grass mown in 5-yard bands with the 2026 venue art's Dolphins end zones and midfield when that option "
    "is on. The row reads Hard Rock Stadium, Miami Gardens, FL; rain still falls on the open field. The 2026 venue art "
    "leaves the Dolphins' packages to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Hard Rock Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Hard Rock Stadium pins schema")
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
    """retail / applied / foreign for the Hard Rock Stadium stretch of one of the nine bundles."""
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
    return Path(str(source) + ".hard-rock.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Hard Rock Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s14 row."""
    from . import nfl2k5_hard_rock_venue as agv
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
    sb.require(state == ("applied" if enabled else "retail"), f"Hard Rock Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Hard Rock Stadium)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Dolphins stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=hard_rock_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s14 to it): the Hard Rock Stadium field, stadium,
    cameras and collapsed cityscape of the nine bundles, and the s14 row. The retail bundles come from ``retail_source``;
    the image's own bundles keep every other chunk (Modern colour's normal map and tint word). With Modern colour on, the
    field is composed before the colour grade and compressed once, and the colour receipt is updated so Modern colour
    still recognizes its bytes. ``art_root`` is the 2026 venue art folder: its Dolphins end zones and midfield go onto the
    new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_hard_rock_venue as agv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Hard Rock Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Hard Rock Stadium needs retail Dolphins packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Hard Rock Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Hard Rock Stadium bundle changed size")
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
        new_colour["hard_rock"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Hard Rock Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Hard Rock Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Hard Rock Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_hard_rock_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Hard Rock Stadium stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st2-hard-rock.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST2_HARD_ROCK_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
