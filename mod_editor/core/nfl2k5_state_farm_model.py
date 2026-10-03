"""State Farm Stadium model (experimental): the Arizona Cardinals' State Farm Stadium (Glendale, opened 2006; Eisenman
Architects with Populous; the roof by Walter P Moore and Birdair) built from scratch as the stadium scene of venue
record s00 (retail Arizona Stadium), all nine bundles (day, afternoon, night; dry, rain, snow).

Job st3 (2026-09-27), on the U.S. Bank Stadium model's parts (u5's builder, u6's SoFi methods, st's Allegiant stack) and
the Levi's model's collapsed cityscape. References (Wikipedia, Walter P Moore, Daktronics, RateYourSeats' chart,
OpenStreetMap, the Esri orthophoto, 78 Commons photos 2006 to 2023) are cited in the st3 report. The scene:

* the red bowl: the 100 level, the 200 level, the loft suites and the 400 level on the sides, lower at both ends (the
  tray's end, the south-south-east, +z, like the north); crowd billboards in the retail convention, cut at every aisle;
* the roof drawn OPEN in every bundle (main, 2026-09-27: the row stays open air as retail, so rain and snow fall through
  the opening onto the grass): the translucent fabric roof on its trusses curving down from the crown (the rails'
  tangent point 206 ft over grade, Walter P Moore) to the drum, the opening over the field between the two Brunel
  trusses, and the two retractable panels (about 258 x 275 ft each) parked over the ends on their rails;
* the two end boards (the north one 30 x 117 ft, Daktronics 2022; the south one DESIGN) on the live feed;
* the silver "barrel cactus" drum on the OpenStreetMap outline (relation 7370103), its glass slots and gates, the
  wordmark on the drum and on the roof (the Commons public-domain file, never redrawn);
* outside: the plazas, the lots, the roads and blocks of Westgate, the desert and the White Tank Mountains; the retail
  cityscape is collapsed (the surroundings live in the stadium scene, as at Levi's); the sky is the engine's own (s00 is
  an open-air row, like Levi's);
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (with u4's 2026 league cloths), the digit shapes (moved onto the boards' wings), the markers and the materials the
  executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x the east-north-east sideline: the visitors' bench; -x the west-south-west
sideline: the Cardinals' bench, where every retail stadium keeps the home sideline props; y up from the field; z along,
-z the north-north-west end, +z the south-south-east end where the grass tray rolls out) and centimetres in the game.
The field axis (+z) points to bearing 151 degrees (the tray's axis on the orthophoto, INFERRED); the field's centre is
the outline's centroid (INFERRED). The field is at grade (the tray rolls out at ground level). The row keeps its
indoor word 0 and the Tempe climate (open air). EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

import json
from . import exact_math as math
import struct
from pathlib import Path

from . import nfl2k5_allegiant_model as ag
from . import nfl2k5_levis_model as lv
from . import nfl2k5_metlife_model as mm
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_sofi_model as sm
from . import nfl2k5_stadium_environment as env
from . import nfl2k5_usbank_model as um

np = um.np

OWNER = "nfl2k5_state_farm_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_state_farm_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s00"
VENUES = (VENUE,)
#: the field at grade: the tray rolls out of the building at ground level (Wikipedia; the orthophotos)
GRADE = 0.0
TOWER_AREA = 1200.0
TOWER_MIN_H, TOWN_RADIUS = 60.0, 420.0

Mesh = mm.Mesh
toward_field, up_toward_field, up, down = mm.toward_field, mm.up_toward_field, mm.up, mm.down
sha = um.sha
_FOOTPRINT = None


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


#: DESIGN, pass 1. The side keys follow the U.S. Bank frame's: N the +x side (the visitors), S the -x side (the
#: Cardinals), E the +z end (the tray's end), W the -z end (the north end). The wall line clears the retail s00 sideline
#: props (x -36.1 to 36.1, z -61.9 to 59.3). Rows after RateYourSeats' chart and the photos (f008, f009, f032).
PARAMS = dict(
    loop=dict(xn=37.8, xs=37.8, ze=64.0, zw=64.0, R=18.0, step=7.0, corner_steps=9),
    wall=dict(height=1.3),
    sides=dict(
        N=dict(low_d0=2.5, low_y0=1.2, low_rows=30, low_tread=0.86, low_rise0=0.28, low_rise1=0.50,
               t2_over=4.0, t2_rows=14, t2_rise=0.56, band_h=4.0,
               up_d=38.0, up_y=26.0, up_rows=20, up_tread=0.82, up_rise=0.62),
        S=dict(low_d0=2.5, low_y0=1.2, low_rows=30, low_tread=0.86, low_rise0=0.28, low_rise1=0.50,
               t2_over=4.0, t2_rows=14, t2_rise=0.56, band_h=4.0,
               up_d=38.0, up_y=26.0, up_rows=20, up_tread=0.82, up_rise=0.62),
        E=dict(low_d0=2.5, low_y0=1.2, low_rows=24, low_tread=0.86, low_rise0=0.28, low_rise1=0.48,
               t2_over=4.0, t2_rows=10, t2_rise=0.56, band_h=3.0,
               up_d=34.0, up_y=22.0, up_rows=14, up_tread=0.82, up_rise=0.60),
        W=dict(low_d0=2.5, low_y0=1.2, low_rows=24, low_tread=0.86, low_rise0=0.28, low_rise1=0.48,
               t2_over=4.0, t2_rows=10, t2_rise=0.56, band_h=3.0,
               up_d=34.0, up_y=22.0, up_rows=14, up_tread=0.82, up_rise=0.60),
    ),
    tier=dict(tread=0.88, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.6, walk=5.0, dark=3.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the roof (Walter P Moore: two panels about 258 x 275 ft riding rails at 15 degrees to a tangent point 206 ft above
    #: grade, one each way, travelling 180 ft; two Brunel trusses each spanning 700 ft): the crown 62.8 m over grade on
    #: the axis, falling ``c`` z^2 along the building and ``k`` per metre across it beyond the rails; the opening over the
    #: field between the Brunel trusses (half extents ``ox`` across, ``oz`` along: twice the panels' 55 m travel); the
    #: panels 78.6 m across and 83.8 m along, parked over the ends (DESIGN from f001 and the facts).
    #: Pass 2: the dome across the building steepens toward the drum (``k`` + ``k2`` per metre beyond the rails; f000,
    #: f001), as far as every rim's 3 m clearance allows; the radial ribs over the fabric; the panels parked 4 m over it
    #: on their rails (main, 2026-09-27).
    roof=dict(crown=62.8, c=0.0008, k=0.02, k2=0.0015, depth=5.0, station=9.0, ox=36.0, oz=55.0, panel=(78.6, 83.8),
              lift=4.0, brunel=(106.7, 11.0, 2.4), ribs=40, rib_w=1.4, rail=(1.6, 1.4), ridge_x=0.0, truss_depth=9.0,
              truss_w=3.0),
    #: the end boards: the north one 30 x 117 ft (Daktronics 2022), the south one the same (DESIGN); over the ends' upper
    #: decks, facing the field (DESIGN from the chart and f032)
    boards=dict(w=35.7, h=9.1, y=30.0, z=112.0, wing=(4.0, 6.0), depth=2.4, header=(0.0, 0.0), feed=1.0),
    #: the drum: the glass base, the petals' bow and the petal's length along the outline (f001: about 18 round the
    #: building; DESIGN, pass 2)
    facade=dict(base=6.0, bulge=5.0, petal=40.0, clerestory=4.0),
    logo=dict(w=36.0, h=10.6),
    roof_logos=dict(x=76.0, z=10.0, w=46.0, h=13.5),
    lights=dict(every=2, w=4.4, h=2.2, drop=1.5, x=52.0, z=(-86.0, 86.0), step=9.0),
    mountains=dict(radius=3300.0, points=48),
)


class StateFarm(um.USBank):
    GRADE = GRADE
    TOWER_AREA = TOWER_AREA
    TOWER_MIN_H, TOWN_RADIUS = TOWER_MIN_H, TOWN_RADIUS
    PARAMS = PARAMS

    def footprint(self):
        return footprint()

    def west_zone(self, lp):
        return False

    # -- the roof -------------------------------------------------------------------------------------------------------
    def roof_top(self, x, z):
        """The roof's top: the crown along the axis falling ``c`` z^2 toward the ends, and ``k`` per metre across the
        building beyond the rails (the opening's sides)."""
        q = self.p["roof"]
        y = q["crown"] - q["c"] * z * z
        ax = abs(x)
        if ax > q["ox"]:
            y -= q["k"] * (ax - q["ox"]) + q["k2"] * math.pow(ax - q["ox"], 2)
        return y

    def in_opening(self, x, z):
        q = self.p["roof"]
        return abs(x) < q["ox"] and abs(z) < q["oz"]

    def _roof_stations(self):
        q = self.p["roof"]
        st = um.USBank._roof_stations(self)
        zs = {round(s[0], 3) for s in st}
        out = list(st)
        P = self.outline()
        for zc in (-q["oz"], q["oz"]):
            if round(zc, 3) in zs:
                continue
            xs = []
            for i in range(len(P)):
                a, b = P[i], P[(i + 1) % len(P)]
                if (a[1] - zc) * (b[1] - zc) <= 0 and a[1] != b[1]:
                    t = (zc - a[1]) / (b[1] - a[1])
                    xs.append(a[0] + (b[0] - a[0]) * t)
            if len(xs) >= 2:
                out.append((zc, min(xs), max(xs)))
        return sorted(out)

    def _roof(self):
        """The fixed roof round the opening, in four grids (the north and south caps across the building, the west and
        east strips beside the opening), top and underside; the opening's edge faces."""
        q = self.p["roof"]
        st = self._roof_stations()
        top_m = self.meshes.setdefault("usb_roof_top", Mesh("usb_roof_top"))
        und = self.meshes.setdefault("usb_roof_under", Mesh("usb_roof_under"))
        ox, oz = q["ox"], q["oz"]

        def emit(rows):
            if len(rows) < 2:
                return
            rows_t = [[(x, self.roof_top(x, z), z) for x in xs] for z, xs in rows]
            rows_u = [[(x, self.roof_under(x, z), z) for x in xs] for z, xs in rows]
            uv = [[(x / 12.0, z / 12.0) for x in xs] for z, xs in rows]
            top_m.grid("sf_fabric_top", rows_t, uv, facing=up)
            und.grid("sf_fabric_under", rows_u, uv, facing=down)
        north = [(z, list(np.linspace(xa, xb, 9))) for z, xa, xb in st if z <= -oz + 1e-6]
        south = [(z, list(np.linspace(xa, xb, 9))) for z, xa, xb in st if z >= oz - 1e-6]
        west = [(z, list(np.linspace(xa, -ox, 4))) for z, xa, xb in st if -oz - 1e-6 <= z <= oz + 1e-6 and xa < -ox]
        east = [(z, list(np.linspace(ox, xb, 4))) for z, xa, xb in st if -oz - 1e-6 <= z <= oz + 1e-6 and xb > ox]
        for rows in (north, south, west, east):
            emit(rows)
        # the opening's edge: the roof's depth round the rectangle, facing into the opening
        edge = self.meshes.setdefault("usb_roof_edge", Mesh("usb_roof_edge"))
        for a, b, n in (((-ox, -oz), (ox, -oz), (0.0, 1.0)), ((ox, -oz), (ox, oz), (-1.0, 0.0)),
                        ((ox, oz), (-ox, oz), (0.0, -1.0)), ((-ox, oz), (-ox, -oz), (1.0, 0.0))):
            ts = np.linspace(0, 1, 9)
            pts = [np.array(a) + (np.array(b) - np.array(a)) * t for t in ts]
            lo = [(float(p[0]), self.roof_under(float(p[0]), float(p[1])), float(p[1])) for p in pts]
            hi = [(float(p[0]), self.roof_top(float(p[0]), float(p[1])), float(p[1])) for p in pts]
            edge.grid("sf_fabric_under", [lo, hi], [[(t * 4, 1.0) for t in ts], [(t * 4, 0.0) for t in ts]],
                      facing=lambda p_, n=n: np.array([n[0], 0.0, n[1]]))

    def _truss(self):
        """The two Brunel trusses along the opening's sides (700 ft each, Walter P Moore): deep white lattices under the
        roof's edge, the fabric and the sky showing through them, with the rails on top."""
        q = self.p["roof"]
        span, depth, w = q["brunel"]
        m = self.meshes.setdefault("usb_truss", Mesh("usb_truss"))
        zs = np.linspace(-span, span, 20)
        for side in (-1, 1):
            xr = side * (q["ox"] + w / 2)
            for face in (-1, 1):
                x = xr + face * w / 2
                upper = [(x, self.roof_top(x, z) + 1.0, z) for z in zs]
                lower = [(x, y - depth, z) for (x, y, z) in upper]
                m.grid("sf_truss", [lower, upper], [[(z / 9.0, 1.0) for z in zs], [(z / 9.0, 0.0) for z in zs]],
                       facing=lambda p_, f=face: np.array([float(f), 0.0, 0.0]))
            bot_a = [(xr - w / 2, self.roof_top(xr, z) + 1.0 - depth, z) for z in zs]
            bot_b = [(xr + w / 2, self.roof_top(xr, z) + 1.0 - depth, z) for z in zs]
            m.grid("sf_truss", [bot_a, bot_b], [[(z / 9.0, 0.004) for z in zs], [(z / 9.0, 0.02) for z in zs]], facing=down)

    def _panels(self):
        """The two retractable panels parked open over the ends (Walter P Moore: about 258 x 275 ft each, travelling 180 ft
        each way; f001): each a curved slab ``lift`` over the fixed roof from the opening's end outward, with its edge
        faces, on the Brunel trusses' rails."""
        q = self.p["roof"]
        pw, pl = q["panel"]
        m = self.meshes.setdefault("usb_panels", Mesh("usb_panels"))
        P = self.outline()
        zmax = float(max(abs(P[:, 1].min()), P[:, 1].max()))
        for zs_ in (-1, 1):
            z0 = zs_ * q["oz"]
            z1 = zs_ * min(q["oz"] + pl, zmax - 4.0)
            zz = np.linspace(z0, z1, 10)
            xs = np.linspace(-pw / 2, pw / 2, 7)
            top = [[(float(x), self.roof_top(0.0, float(z)) - q["k"] * max(0.0, abs(x) - q["ox"]) + q["lift"], float(z))
                    for x in xs] for z in zz]
            uv = [[((x + pw / 2) / pw, (z - z0) / (z1 - z0) * 2.0) for x in xs] for z in zz]
            m.grid("sf_panel_top", top, uv, facing=up)
            # the panel's edges down to the fixed roof
            for rowk, n in ((0, (0.0, -float(zs_))), (-1, (0.0, float(zs_)))):
                row = top[rowk]
                lo = [(x, y - q["lift"] - 0.5, z) for x, y, z in row]
                m.grid("sf_panel_edge", [lo, row], [[(k / 6, 1.0) for k in range(len(row))], [(k / 6, 0.0) for k in range(len(row))]],
                       facing=lambda p_, n=n: np.array([n[0], 0.0, n[1]]))
            for colk, n in ((0, (-1.0, 0.0)), (-1, (1.0, 0.0))):
                col = [r[colk] for r in top]
                lo = [(x, y - q["lift"] - 0.5, z) for x, y, z in col]
                m.grid("sf_panel_edge", [lo, col], [[(k / 9, 1.0) for k in range(len(col))], [(k / 9, 0.0) for k in range(len(col))]],
                       facing=lambda p_, n=n: np.array([n[0], 0.0, n[1]]))

    def _rails(self):
        """The panels' tracks (main, 2026-09-27; f001): a grey steel rail along each Brunel truss's top, from end to end of
        the panels' travel, standing on the fabric."""
        q = self.p["roof"]
        w, h = q["rail"]
        m = self.meshes.setdefault("usb_panels", Mesh("usb_panels"))
        P = self.outline()
        zmax = float(max(abs(P[:, 1].min()), P[:, 1].max())) - 4.0
        zs = np.linspace(-min(q["oz"] + q["panel"][1], zmax), min(q["oz"] + q["panel"][1], zmax), 24)
        for side in (-1, 1):
            xr = side * (q["ox"] + q["brunel"][2] / 2)
            for face in (-1, 1):
                x = xr + face * w / 2
                lo = [(x, self.roof_top(x, z) - 0.2, z) for z in zs]
                hi = [(x, self.roof_top(xr, z) + h, z) for z in zs]
                m.grid("sf_panel_edge", [lo, hi], [[(z / 8.0, 1.0) for z in zs], [(z / 8.0, 0.0) for z in zs]],
                       facing=lambda p_, f=face: np.array([float(f), 0.0, 0.0]))
            top_a = [(xr - w / 2, self.roof_top(xr, z) + h, z) for z in zs]
            top_b = [(xr + w / 2, self.roof_top(xr, z) + h, z) for z in zs]
            m.grid("sf_panel_edge", [top_a, top_b], [[(z / 8.0, 0.0) for z in zs], [(z / 8.0, 0.3) for z in zs]], facing=up)

    def _ribs(self):
        """The fabric roof's radial ribs (the orthophotos, f000: light grey steel lines from the opening to the drum,
        about 40 round the building), 0.25 m over the fabric."""
        q = self.p["roof"]
        m = self.meshes.setdefault("usb_ribs", Mesh("usb_ribs"))
        P = self.outline()
        ox, oz = q["ox"], q["oz"]
        for k in range(q["ribs"]):
            a = 2 * math.pi * (k + 0.5) / q["ribs"]
            d = np.array([math.cos(a), math.sin(a)])
            # from the opening's rectangle to the outline, along the ray from the centre
            t0 = min(ox / abs(d[0]) if abs(d[0]) > 1e-9 else 1e9, oz / abs(d[1]) if abs(d[1]) > 1e-9 else 1e9)
            t1 = None
            for i in range(len(P)):
                pa, pb = P[i], P[(i + 1) % len(P)]
                e = pb - pa
                den = d[0] * (-e[1]) - d[1] * (-e[0])
                if abs(den) < 1e-12:
                    continue
                tt = (pa[0] * (-e[1]) - pa[1] * (-e[0])) / den
                u = (d[0] * pa[1] - d[1] * pa[0]) / den
                if tt > 0 and 0 <= u <= 1:
                    t1 = tt if t1 is None else min(t1, tt)
            if t1 is None or t1 - 2.0 <= t0:
                continue
            ts = np.linspace(t0, t1 - 2.0, 8)
            nrm = np.array([-d[1], d[0]]) * q["rib_w"] / 2
            left = [(float(d[0] * tt - nrm[0]), 0.0, float(d[1] * tt - nrm[1])) for tt in ts]
            right = [(float(d[0] * tt + nrm[0]), 0.0, float(d[1] * tt + nrm[1])) for tt in ts]
            left = [(x, self.roof_top(x, z) + 0.25, z) for x, _y, z in left]
            right = [(x, self.roof_top(x, z) + 0.25, z) for x, _y, z in right]
            m.grid("sf_rib", [left, right], [[(tt / 30.0, 0.0) for tt in ts], [(tt / 30.0, 1.0) for tt in ts]], facing=up)

    def _roof_letters(self):
        """The wordmark on the fixed roof either side of the opening (the orthophotos), read from outside the building
        on each side, 0.3 m over the fabric."""
        q = self.p["roof_logos"]
        m = self.meshes.setdefault("usb_roof_letters", Mesh("usb_roof_letters"))
        for side in (-1, 1):
            x0 = side * q["x"]
            hw, hh = q["w"] / 2, q["h"] / 2
            # the text's up points away from the axis (toward the side), its right along -side z
            corners = [(x0 - side * hh, q["z"] + side * hw), (x0 - side * hh, q["z"] - side * hw),
                       (x0 + side * hh, q["z"] - side * hw), (x0 + side * hh, q["z"] + side * hw)]
            Pp = [(x, self.roof_top(x, z) + 0.3, z) for x, z in corners]
            m.quad("sf_logo", Pp[0], Pp[1], Pp[2], Pp[3], (0, 1), (1, 1), (1, 0), (0, 0), facing=up)

    # -- the boards -----------------------------------------------------------------------------------------------------
    def _boards(self):
        q = self.p["boards"]
        m = self.meshes.setdefault("usb_boards", Mesh("usb_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        for zs_ in (-1, 1):
            face = np.array([0.0, 0.0, -float(zs_)])
            self._board(m, np.array([0.0, q["y"], zs_ * q["z"]]), face, q["w"], q["h"], q["wing"], self.board_frames,
                        header=False)

    # -- the drum -------------------------------------------------------------------------------------------------------
    def _facade(self):
        """The drum on the outline: a glass base at the gates, then the silver panels bulging out to mid-height and back
        in to the roof's edge (the "barrel cactus", f000, f001); inside, the dark inner face; the wordmark on the drum
        over the west and east gates."""
        q = self.p["facade"]
        m = self.meshes.setdefault("usb_facade", Mesh("usb_facade"))
        g = self.meshes.setdefault("usb_glass", Mesh("usb_glass"))
        P = self.outline()
        s = 0.0
        segs, drum_pts = [], []
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            e = b - a
            L = float(math.np_hypot(*e))
            if L < 0.05:
                continue
            n = np.array([e[1], -e[0]]) / L
            segs.append((a, b, s, L, n))
            k = max(1, int(math.ceil(L / 10.0)))
            ts = np.linspace(0, 1, k + 1)
            pts = [a + (b - a) * t for t in ts]
            tops = [self.roof_top(float(p[0]), float(p[1])) for p in pts]
            outward = lambda p_, n=n: np.array([n[0], 0.0, n[1]])  # noqa: E731
            inward = lambda p_, n=n: -np.array([n[0], 0.0, n[1]])  # noqa: E731
            us = [s + L * t / q["petal"] for t in ts]
            bot = [(float(p[0]), self.GRADE - 0.5, float(p[1])) for p in pts]
            base_ = [(float(p[0]), self.GRADE + q["base"], float(p[1])) for p in pts]
            top = [(float(p[0]), t, float(p[1])) for p, t in zip(pts, tops)]
            # the barrel: the petals bow out to ``bulge`` at mid-height (sin profile) and back in to the roof's edge
            fr = (0.0, 0.25, 0.5, 0.75, 1.0)
            rows = [[(float(p[0]) + n[0] * q["bulge"] * math.sin(math.pi * f),
                      self.GRADE + q["base"] + (t - self.GRADE - q["base"]) * f,
                      float(p[1]) + n[1] * q["bulge"] * math.sin(math.pi * f)) for p, t in zip(pts, tops)] for f in fr]
            g.grid("LIGHT_sf_facade_glass", [bot, base_], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
            m.grid("sf_drum", rows, [[(u, 1.0 - f) for u in us] for f in fr], facing=outward)
            drum_pts.extend(pt for row in rows for pt in row)
            m.grid("sf_inner", [[(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in base_],
                                [(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in top]],
                   [[(u * 4, 1.0) for u in us], [(u * 4, 0.0) for u in us]], facing=inward)
            s += L
        lq = self.p["logo"]
        D = np.array(drum_pts)
        for side in (-1, 1):
            p_, n = self.logo_spot(segs, s, side)
            # 0.4 m proud of the drum wherever the sign spans it (the drum's corners bound its flat facets)
            rel = D - np.array([p_[0], 0.0, p_[1]])
            near = np.abs(math.np_matmul(rel, np.array([-n[1], 0.0, n[0]]))) <= lq["w"] / 2 + 2.0
            out = max(q["bulge"], float((math.np_matmul(rel[near], np.array([n[0], 0.0, n[1]]))).max())) + 0.4
            x, z = p_ + n * out
            y = self.roof_top(float(p_[0]), float(p_[1])) * 0.5
            # flush on the drum: no black back (lab 3, PROVED IN GAME: the transparent ground showed black there)
            self._panel(m, "sf_logo", (float(x), y, float(z)), (float(n[0]), 0.0, float(n[1])), lq["w"], lq["h"],
                        (0.0, 1.0), back=False)

    #: the drum texture's dark glass slot is the first tenth of every petal (u 0 to 0.10 of a repeat, the art tool's
    #: ``drum``); the silver runs from there to the next slot
    SLOT_U = 0.10

    def logo_spot(self, segs, total, side):
        """(point, outward normal) on the outline for the wordmark on this side: the middle of the silver petal nearest
        the outline's crossing of the x axis, so the sign sits wholly on silver between two slots (a sign across a slot
        lost its dark letters to the dark glass behind its transparent ground: pass 2's flyover sheet, shot 1)."""
        petal = self.p["facade"]["petal"]
        cross = None
        for a, b, s0, L, n in segs:
            if (a[1] <= 0.0 < b[1] or b[1] <= 0.0 < a[1]) and np.sign(a[0] + b[0]) == side:
                cross = s0 + L * float(a[1] / (a[1] - b[1]))
        sb.require(cross is not None, f"the outline never crosses the x axis on side {side}")
        mid = (self.SLOT_U + 1.0) / 2.0
        want = petal * (round(cross / petal - mid) + mid)
        want %= total
        for a, b, s0, L, n in segs:
            if s0 <= want <= s0 + L:
                return a + (b - a) * ((want - s0) / L), n
        a, b, s0, L, n = segs[-1]
        return b, n

    def _hills(self):
        """The White Tank Mountains in the west and the ranges round the valley (f000, f001): a ring of hazy ridges beyond
        the lots, highest to the west (bearing about 270: game angle, with +z at bearing 151)."""
        q = self.p["mountains"]
        m = self.meshes.setdefault("usb_hills", Mesh("usb_hills"))
        N = q["points"]
        rnd = np.random.default_rng(29)
        bot, top, uvb, uvt = [], [], [], []
        for k in range(N + 1):
            a = 2 * math.pi * (k % N) / N
            x, z = q["radius"] * math.cos(a), q["radius"] * math.sin(a)
            # the bearing of (x, z): +z is 151 degrees, +x is 61 degrees
            e = x * math.sin(math.radians(61.0)) + z * math.sin(math.radians(151.0))
            nn = x * math.cos(math.radians(61.0)) + z * math.cos(math.radians(151.0))
            bearing = math.degrees(math.atan2(e, nn)) % 360.0

            def bump(c, w):
                return math.exp(-math.pow(((bearing - c + 180) % 360 - 180) / w, 2))
            h = 150.0 * bump(265.0, 40.0) + 70.0 * bump(170.0, 35.0) + 50.0 * bump(20.0, 50.0) + 10.0
            h *= 0.85 + 0.3 * float(rnd.random())
            bot.append((x, self.GRADE - 2.0, z))
            top.append((x * 1.02, self.GRADE + h, z * 1.02))
            uvb.append((k / 4.0, 1.0))
            uvt.append((k / 4.0, 0.0))
        m.grid("sf_mountains", [bot, top], [uvb, uvt], facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))

    def _exterior(self):
        """The U.S. Bank model's plaza and the environment kit (the White Tank Mountains and the other ranges now stand on
        the kit's horizon band at their true elevation angles, from the Terrain Tiles)."""
        um.USBank._exterior(self)

    # -- build ----------------------------------------------------------------------------------------------------------
    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        self.light_points = []
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"usb_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "usb"
        self._roof()
        self._truss()
        self._panels()
        self._rails()
        self._ribs()
        self._lights()
        self._boards()
        north = min(loop, key=lambda lp: math.pow(lp.nx - 1, 2) + math.pow(lp.z / 40.0, 2))
        row = self.section(north)["upper"][4]
        self.nosebleed = self.at(north, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._roof_letters()
        self._exterior()
        self._rename()
        return self

    def camera_eyes(self):
        return um.shot_eyes(state_farm_shots())

    def _rename(self):
        def r(name):
            name = name.replace("LIGHT_usb_clerestory", "usb_inner")
            return name.replace("LIGHT_usb_", "LIGHT_sf_").replace("usb_", "sf_")
        meshes = {}
        for mesh in self.meshes.values():
            mesh.name = r(mesh.name)
            mesh.groups = {r(k): v for k, v in mesh.groups.items()}
            meshes[mesh.name] = mesh
        self.meshes = meshes


def build(venue=VENUE, params=None):
    return StateFarm(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = um.KEEP_PREFIXES
KEEP_YARD = um.KEEP_YARD
KEEP_MATERIALS_BY_CODE = um.KEEP_MATERIALS_BY_CODE
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

MATERIALS = {
    "sf_seat_front": ("sf_seat_front", CLASS_OPAQUE), "sf_seat_mid": ("sf_seat_mid", CLASS_OPAQUE),
    "sf_seat_back": ("sf_seat_back", CLASS_OPAQUE), "sf_concrete": ("sf_concrete", CLASS_OPAQUE),
    "sf_wall": ("sf_wall", CLASS_OPAQUE), "LIGHT_sf_ribbon": ("LIGHT_sf_ribbon", CLASS_OPAQUE),
    "LIGHT_sf_glass": ("LIGHT_sf_glass", CLASS_OPAQUE), "LIGHT_sf_concourse": ("LIGHT_sf_concourse", CLASS_OPAQUE),
    "sf_portal": ("sf_portal", CLASS_OPAQUE), "sf_dark": ("sf_dark", CLASS_OPAQUE), "sf_black": ("sf_black", CLASS_OPAQUE),
    "sf_fabric_under": ("sf_fabric_under", CLASS_OPAQUE), "sf_fabric_top": ("sf_fabric_top", CLASS_OPAQUE),
    "sf_panel_top": ("sf_panel_top", CLASS_OPAQUE), "sf_truss": ("sf_truss", CLASS_ALPHA),
    "sf_panel_edge": ("sf_panel_edge", CLASS_OPAQUE), "sf_rib": ("sf_rib", CLASS_OPAQUE), "sf_inner": ("sf_inner", CLASS_OPAQUE),
    "LIGHT_sf_lights": ("LIGHT_sf_lights", CLASS_OPAQUE), "sf_drum": ("sf_drum", CLASS_OPAQUE),
    "LIGHT_sf_facade_glass": ("LIGHT_sf_facade_glass", CLASS_OPAQUE), "sf_logo": ("sf_logo", CLASS_ALPHA),
    "LIGHT_sf_board_wing": ("LIGHT_sf_board_wing", CLASS_OPAQUE),
    "sf_plaza": ("sf_plaza", CLASS_OPAQUE), "sf_lawn": ("sf_lawn", CLASS_OPAQUE), "sf_asphalt": ("sf_asphalt", CLASS_OPAQUE),
    "sf_road": ("sf_road", CLASS_OPAQUE), "sf_building": ("sf_building", CLASS_OPAQUE),
    "sf_mountains": ("sf_mountains", CLASS_ALPHA),
    **env.materials(VENUE),
}

BASE = {
    "sf_seat_front": (220, 212, 200), "sf_seat_mid": (220, 212, 200), "sf_seat_back": (214, 206, 196),
    "crowd": (226, 218, 208), "sf_concrete": (214, 206, 194), "sf_wall": (236, 228, 220),
    "LIGHT_sf_ribbon": (255, 255, 255), "LIGHT_sf_glass": (196, 190, 255), "LIGHT_sf_concourse": (216, 208, 255),
    "sf_portal": (160, 156, 150), "sf_dark": (190, 186, 180), "sf_black": (200, 196, 190),
    "sf_fabric_under": (192, 188, 132), "sf_fabric_top": (230, 216, 110), "sf_panel_top": (240, 228, 120),
    "sf_panel_edge": (220, 206, 130), "sf_rib": (226, 212, 120), "sf_inner": (214, 208, 170),
    "sf_truss": (220, 214, 180), "LIGHT_sf_lights": (255, 255, 255), "sf_drum": (226, 212, 140),
    "LIGHT_sf_facade_glass": (228, 212, 255), "sf_logo": (255, 255, 255), "LIGHT_sf_board_wing": (255, 255, 255),
    "jumbo_tron": (255, 255, 255),
    "sf_plaza": (230, 210, 120), "sf_lawn": (226, 206, 84), "sf_asphalt": (222, 202, 92), "sf_road": (222, 202, 92),
    "sf_building": (224, 204, 112), "sf_mountains": (230, 214, 150),
}
#: the sun over Glendale (DESIGN): by day high in the south (bearing 180: x = -0.48, z = 0.87 in this frame), in the
#: afternoon low in the south-west (bearing 240: x = -0.99, z = 0.14)
SUN = {"d": (-0.30, 0.82, 0.49), "a": (-0.82, 0.52, 0.12), "n": None}
TINT = um.TINT
OUTSIDE = {"sf_fabric_top", "sf_panel_top", "sf_panel_edge", "sf_rib", "sf_drum", "LIGHT_sf_facade_glass", "sf_plaza", "sf_lawn", "sf_asphalt",
           "sf_road", "sf_building", "sf_mountains"}
#: the bowl under the open roof: the stands in the fabric's shade, one level (DESIGN)
INSIDE_LIGHT = um.INSIDE_LIGHT
WEATHER_TINT = {"d": (1.0, 1.0, 1.0), "r": (0.82, 0.84, 0.88), "s": (0.92, 0.94, 0.98)}


def light(mat, P, N, tod, weather, outside=False):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
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
    if mat == "sf_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    wt = WEATHER_TINT.get(weather, (1.0, 1.0, 1.0)) if not mat.startswith("LIGHT_") else (1.0, 1.0, 1.0)
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k] * wt[k], 0, 255)
    out[:, 3] = 255
    if mat in ("sf_fabric_top", "sf_panel_top", "sf_panel_edge", "sf_rib", "sf_drum") and tod == "n":
        out[:, 0] = 86; out[:, 1] = 88; out[:, 2] = 96
    return out


def _textures(venue, tod, weather):
    out = {key: um._rgba(ART_DIR / f"{key}.png") for key in dict.fromkeys(k for k, _c in MATERIALS.values())
           if not key.startswith("env_")}
    out.update(env.textures(venue, tod, weather))
    return out


flare_points = um.flare_points
adjust_digits = um.adjust_digits
dry_of = ag.dry_of
league_banner = ag.league_banner


def build_scene(retail_bundle, filename, model, dry_bundle=None):
    """The State Farm stadium scene for one bundle, built on the retail scene's records the engine reads (the U.S. Bank
    model's assembly with this model's materials)."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "sf_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "sf_digits", tmpl_shape)
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
    its stadium scene replaced by the State Farm model and its intro cameras rewritten when ``cameras`` gives the shots.
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
        new_cam = um.write_cameras(cam_dec, cameras)
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
    stretch_ = c_out + chunk + cam_out
    sb.require(len(stretch_) == end - start, f"{filename}: the stretch changed length ({len(stretch_)} != {end - start})")
    out = bytes(retail_bundle[:start]) + stretch_ + bytes(retail_bundle[end:])
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


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s00 intro camera's channel carries (PROVED OFFLINE from the retail s00dd scene): camera 1
#: all five (only y is a single-segment curve: it rises; the others hold); camera 2 pitch, y and z (x and yaw play as 0:
#: it looks north along the axis; pitch and y move); camera 3 all five (all move); camera 4 all five and roll (all move);
#: camera 5 all five (all move).
CAMERA_COMPONENTS_PRESENT = ({"pitch", "x", "y", "yaw", "z"}, {"pitch", "y", "z"}, {"pitch", "x", "y", "yaw", "z"},
                            {"pitch", "roll", "x", "y", "yaw", "z"}, {"pitch", "x", "y", "yaw", "z"})

#: DESIGN, pass 1: the State Farm flyover, one shot per retail camera.
#: 1: outside at the west gate, rising along the silver drum;
#: 2 (on the axis, looking north): a crane over midfield rising to the open roof and the north board;
#: 3: from the east upper deck, panning across the bowl under the open roof to the Cardinals' side;
#: 4: an aerial from the south-west over the open roof and the parked panels, the desert and the mountains beyond;
#: 5: field level behind the south end zone, pushing north toward the north board.
_GATE = dict(eye=(-200.0, 6.0, 40.0), target=(-110.0, 30.0, 10.0), fov=46.0, rates=dict(y=4.0))
_CRANE = dict(eye=(0.0, 8.0, 0.0), target=(0.0, 30.0, -112.0), fov=46.0, rates=dict(y=2.5, pitch=0.8))
_PAN = dict(eye=(78.0, 46.0, -20.0), target=(-40.0, 30.0, 40.0), fov=44.0, rates=dict(yaw=-2.5))
_AERIAL = dict(eye=(-330.0, 230.0, 260.0), target=(0.0, 40.0, 0.0), fov=40.0, rates=dict(x=4.0, z=-3.0))
_SOUTH = dict(eye=(6.0, 2.5, 60.0), target=(0.0, 20.0, -112.0), fov=44.0, rates=dict(z=-3.0))
SF_SHOTS = [_GATE, _CRANE, _PAN, _AERIAL, _SOUTH]


def state_farm_shots():
    out = []
    for s, present in zip(SF_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=state_farm_shots(), dry_bundle=dry)
    return name, out, info


def _venue_pins():
    from . import nfl2k5_modern_venues_2026 as mv
    return {pin["name"]: pin for pin in mv.venues()[VENUE]["bundles"]}


def _entry(archive, pin):
    from . import nfl2k5_modern_venues_2026 as mv
    entry = mv._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


def read_retail(source):
    ml = sm._ml()
    out = {}
    with ml._outer_image()(str(source)) as archive:
        for name, pin in _venue_pins().items():
            e = _entry(archive, pin)
            data = archive.read(e.virtual_offset, e.size)
            sb.require(sha(data) == pin["retail_sha256"], f"{name}: the source bundle is not retail")
            out[name] = data
    return out


stretch = lv.stretch


def build_all(source, *, workers=None, progress=None, names=None):
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers, progress=progress, label="State Farm Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field

#: The field (Tifway 419 hybrid Bermuda on the roll-out tray; Wikipedia): the retail s00 field is a grass venue with its
#: own north and south end-zone textures and no midfield submesh (like s15). The Cardinals' 2026 end zones from the
#: league project's art (the u4 ARI venue folder) go onto the retail textures over the grass's own colour (with the rain
#: and snow looks in those bundles), the turf and the apron take the Modern playing surfaces palette for s00 through that
#: option's own painter, and the midfield head is a new quad in the field scene (the U.S. Bank model's method).
GRASS_MATERIAL, OUTSIDE_MATERIAL = "color_premipped", "grass_outside_premipped"
ENDZONE_TEXTURES = ag.ENDZONE_TEXTURES
TEAM_FIELD = ENDZONE_TEXTURES + ("center_logo",)
FIELD_LADDER = ag.FIELD_LADDER
FIELD_SKIP_FIRST = ag.FIELD_SKIP_FIRST


def team_field_art(art_root):
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
    """The State Farm field for one bundle (decoded, the retail layout kept): the Cardinals' end zones over the retail
    grass's own colour, in the bundle's weather look. The grass and the apron are tf's (surface_span)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    grass, _pal = ml.read_p8(out, system, rows[GRASS_MATERIAL])
    clean = np.array(np.median(grass.reshape(-1, 4), axis=0), np.float32)

    def over_grass(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    team = {k: v for k, v in dict(team or {}).items() if k in ENDZONE_TEXTURES}
    if team and not any(k.startswith("endzone_S_") for k in team):
        team.update({k.replace("_N_", "_S_"): v for k, v in list(team.items()) if k.startswith("endzone_N_")})
    detail = sm._half_detail if half else (lambda a: a)
    for mat, art in team.items():
        row = rows.get(mat)
        if row is None:
            continue
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, detail(ag._weather_look(over_grass(a), weather)), maximum=cap)
    return bytes(out)


def surface_span(span, bundle, name, colour_settings=None):
    """(field span, tf's receipt): the grass and the apron on tf's palette for s00 (the Bermuda look, the bundle's own
    light class: s00 is open air), through tf's own painter and fit, after the end-zone art."""
    from . import nfl2k5_modern_surfaces as ms
    look = ms.venue_look(VENUE)
    cls = ms.light_class(name, False)
    rig = ms.rig_name(cls, name[3])
    return ms.field_span(span, look=look, cls=cls, rig=rig, colour_settings=colour_settings, tint=ms.field_tint(bundle),
                         target=ms.venue_target(VENUE, look, cls))


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle (Allegiant's ladder and colour path, tf's surface,
    then the midfield quad)."""
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
            continue
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
            after, surf = surface_span(after, bundle, name, colour_settings)
            sb.require(len(after) == len(span), f"{name}: the surface escaped its span")
            mid = None
            if team and "center_logo" in team:
                after, mid = um.midfield_span(after, name, team["center_logo"])
                sb.require(len(after) == len(span), f"{name}: the field escaped its span")
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               team_art=sorted(team or {}), midfield=mid,
                               surface={k: surf.get(k) for k in ("look", "light", "rig", "layout", "target", "map_mean",
                                                                  "outside_mean", "palette_cap", "refit")},
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{rung}: {exc}")
    raise sb.ScneBuildError(f"{name}: the State Farm field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_state_farm_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_state_farm_receipt/v1"
BUILD_CAPTION = "State Farm Stadium for the Cardinals (experimental)"
HELP_TEXT = (
    "The Arizona Cardinals' State Farm Stadium, built as a new model for Cardinals home games in every time of day and "
    "weather: the red bowl under the fabric roof drawn open (the dome with its radial ribs, the two retractable panels "
    "parked over the ends on their tracks, the Brunel trusses), the two end video boards with the live feed, the silver "
    "barrel-cactus drum with its slots and the wordmark, the lots, the desert and the White Tank Mountains, and a new "
    "pregame flyover with exterior passes. The field is the 2026 natural grass on the Modern surfaces palette with the "
    "2026 venue art's Cardinals end zones and midfield when that option is on. The row reads State Farm Stadium, "
    "Glendale, AZ; the roof is open, so rain and snow fall onto the grass as the retail row lets them. The 2026 venue "
    "art leaves the Cardinals' packages to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "State Farm Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported State Farm Stadium pins schema")
    return _PINS


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compile the nine stretches from a retail source and pin them (the field depends on the art root, the
    Modern colour settings and the Modern surfaces palette, so the receipt records it instead)."""
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
    """retail / applied / foreign for the State Farm stretch of one of the nine bundles."""
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
    return Path(str(source) + ".state_farm.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported State Farm Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s00 row."""
    from . import nfl2k5_state_farm_venue as uv
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
        entry = archive.entries[uv.ROST_OUTER_INDEX]
        row = uv.rost_state(archive.read(entry.virtual_offset, entry.size))
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
    sb.require(state == ("applied" if enabled else "retail"), f"State Farm Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_state_farm")
def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already State Farm)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Cardinals stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=state_farm_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_state_farm")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s00 to it; before Modern surfaces, the last
    stadium writer, which keeps this field's paint): the State Farm field, the collapsed cityscape, the stadium and the
    cameras of the nine bundles, and the s00 row. The retail bundles come from ``retail_source``; the image's own bundles
    keep every other chunk. With Modern colour on, the field is composed before the colour grade and the colour receipt
    is updated so Modern colour still recognizes its bytes; the grass and apron then take the Modern surfaces palette
    for s00 through that option's own painter. ``art_root`` is the 2026 venue art folder: its Cardinals end zones and
    midfield go onto the new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_state_farm_venue as uv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries State Farm Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"State Farm Stadium needs retail Cardinals packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="State Farm Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the State Farm bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], applied_sha256=sha(after),
                                            field=info.get("field"), system=info["system"], video=info["video"],
                                            fan_art=info.get("fan_art"))
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
        receipt["rost"] = uv.apply_rost(archive)
    if new_colour is not None:
        new_colour["state_farm"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after State Farm Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"State Farm Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("State Farm Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_state_farm_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the State Farm stretches, fields and row into a built disc")
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
            info[name] = dict(i, field=finfo)
            print(name, "decoded", i["system"] + i["video"], "retail", i["retail_system"] + i["retail_video"],
                  "stored", i["stored"], "vertices", i["vertices"], "field cap", finfo["palette_cap"], flush=True)
        (out / "build.json").write_text(json.dumps(info, indent=1, default=str) + "\n", newline="\n")
        return 0
    receipt = apply_lab_disc(args.disc, args.source, art_root=args.art_root, progress=say)
    Path(str(args.disc) + ".st3-state-farm.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST3_STATE_FARM_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
