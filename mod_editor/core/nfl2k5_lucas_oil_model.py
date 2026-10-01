"""Lucas Oil Stadium model (experimental): the Indianapolis Colts' Lucas Oil Stadium (Indianapolis, opened 2008; HKS with
Walter P Moore) built from scratch as the stadium scene of venue record s11 (retail RCA Dome), all nine bundles (day,
afternoon, night; dry, rain, snow).

Job st3 (2026-09-27), on the U.S. Bank Stadium model's parts (u5's builder, u6's SoFi methods, st's Allegiant stack).
References (Wikipedia, the stadium's own fast facts, Uni-Systems, RateYourSeats' 2026 chart, OpenStreetMap, the Esri
orthophoto, 149 Commons photos 2008 to 2024) are cited in the st3 report. The scene:

* the blue bowl: on both sidelines and the south end the 100 level, the 200 level, the suite band and the upper deck
  (the 400 to 600 levels); the north end the retractable 100 level and the 400 level under the window; crowd billboards
  in the retail convention, cut at every aisle; the ribbons on the fascias;
* the gabled roof on the field's axis (Uni-Systems: "a gabled, side-opening roof, with its peak running north and south
  down the center of the field"), drawn closed as the Colts play most games (main, 2026-09-27): the two retractable
  panels (160 x 600 ft each, the stadium's own facts) either side of the ridge, the fixed roof falling east and west,
  the dark steel trusses under it, the floodlights;
* the north window (six glass panels, 88 ft high; 214 ft wide, Uni-Systems) over the north end's stands with
  downtown's towers beyond it, the stadium's wordmark over it and the Colts' banners;
* the two main boards (37 x 97 ft) in the north-west and south-east corners with two auxiliary boards over each;
* the brick and limestone fieldhouse on the OpenStreetMap outline with its tall arched windows, the corner towers and
  the wordmark on the facades; the lots, the streets, the rail and downtown;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (with u4's 2026 league cloths), the digit shapes (moved onto the boards' wings), the markers and the materials the
  executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x the east sideline: the visitors' bench; -x the west sideline: the Colts' bench,
where every retail stadium keeps the home sideline props; y up from the field; z along, -z the north end (the window),
+z the south end) and centimetres in the game. The field axis (+z) points to bearing 205.8 degrees (the outline's walls,
INFERRED); the field centre sits 12 m north of the building's centre (the solved photo l137, INFERRED). The row keeps its
indoor word 1 (the roof drawn closed). EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

import hashlib
import json
import math
import struct
from pathlib import Path

from . import nfl2k5_allegiant_model as ag
from . import nfl2k5_metlife_model as mm
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_sofi_model as sm
from . import nfl2k5_stadium_environment as env
from . import nfl2k5_usbank_model as um

np = um.np

OWNER = "nfl2k5_lucas_oil_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_lucas_oil_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s11"
VENUES = (VENUE,)
#: the street over the field: 25 ft (the stadium's own facts: "Field ... sits 25' below Street Level")
GRADE = 7.62
#: downtown's towers as boxes no larger than this (m2) and no lower than TOWER_MIN_H; the blocks within TOWN_RADIUS
TOWER_AREA = 1200.0
TOWER_MIN_H, TOWN_RADIUS = 60.0, 420.0

Mesh = mm.Mesh
toward_field, up_toward_field, up, down = mm.toward_field, mm.up_toward_field, mm.up, mm.down
sha = um.sha
plan_loop = um.plan_loop
_FOOTPRINT = None


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


# ------------------------------------------------------------------------------------------------ parameters

#: DESIGN, pass 1. The side keys follow the U.S. Bank frame's: N the +x side (here the east sideline), S the -x side
#: (the west sideline, the Colts'), E the +z end (the south end), W the -z end (the north end, the window). The wall line
#: clears the retail s11 sideline props (x -35.4 to 36.3). Rows from RateYourSeats' 2026 chart and the seat guides (the
#: 100 level 23 rows on the sidelines, 35 at the ends) and the photos; heights from the solved photo l137 (the south upper
#: deck's top about 44 m over the field, 140 m from the centre).
PARAMS = dict(
    loop=dict(xn=37.5, xs=37.5, ze=64.0, zw=62.0, R=16.0, step=7.0, corner_steps=9),
    wall=dict(height=1.3),
    sides=dict(
        N=dict(low_d0=2.5, low_y0=1.4, low_rows=23, low_tread=0.86, low_rise0=0.30, low_rise1=0.52,
               t2_over=4.0, t2_rows=12, t2_rise=0.56, band_h=4.0,
               up_d=36.0, up_y=24.0, up_rows=30, up_tread=0.82, up_rise=0.62),
        S=dict(low_d0=2.5, low_y0=1.4, low_rows=23, low_tread=0.86, low_rise0=0.30, low_rise1=0.52,
               t2_over=4.0, t2_rows=12, t2_rise=0.56, band_h=4.0,
               up_d=36.0, up_y=24.0, up_rows=30, up_tread=0.82, up_rise=0.62),
        E=dict(low_d0=2.5, low_y0=1.4, low_rows=35, low_tread=0.86, low_rise0=0.30, low_rise1=0.50,
               t2_over=4.0, t2_rows=12, t2_rise=0.56, band_h=4.0,
               up_d=40.0, up_y=23.0, up_rows=34, up_tread=0.85, up_rise=0.40),
        W=dict(low_d0=2.5, low_y0=1.4, low_rows=35, low_tread=0.86, low_rise0=0.30, low_rise1=0.50,
               t2_over=4.0, t2_rows=16, t2_rise=0.56, band_h=0.0,
               up_d=40.0, up_y=30.0, up_rows=0, up_tread=0.82, up_rise=0.62),
    ),
    tier=dict(tread=0.88, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.6, walk=5.0, dark=3.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the gabled roof (Uni-Systems; the stadium's facts: two panels 160 ft east to west by 600 ft north to south): the
    #: ridge on the axis 82 m over the street (270 ft overall, American Football Wiki, INFERRED), the panels falling
    #: ``p1`` to their outer edges, the fixed roof ``p2`` beyond them to the eaves (DESIGN, pass 1). The ridge truss and
    #: the panels' rails run the length of the building (``ridge_z_w`` to ``ridge_z_e``).
    roof=dict(ridge=89.9, panel_w=48.8, p1=0.18, p2=0.40, depth=6.0, station=9.0, ridge_x=0.0,
              ridge_z_w=-112.0, ridge_z_e=136.0, truss_depth=9.0, truss_w=4.0),
    #: the north window: centred on the axis in the north wall, 214 x 88 ft (Uni-Systems; the arch's rise and the sill
    #: over the north stands DESIGN from l096 and l137)
    window=dict(w=65.2, h=26.8, sill=31.0, arch=10.0, cols=6),
    #: the south facade's fixed arched window over the south gate (l056, l059; DESIGN: as wide as the north window, its
    #: sill over the gate's canopy)
    south_window=dict(w=58.0, h=38.0, sill=16.0, arch=12.0),
    #: the main boards 37 x 97 ft in the north-west and south-east corners (the stadium's facts), their centres from the
    #: solved photo l137 (the north-west one about 36.5 m up, INFERRED; the south-east one mirrored, DESIGN), each facing
    #: the field's centre, with two auxiliary boards over it
    boards=dict(w=29.6, h=11.3, y=30.9, nw=(-60.0, -88.0), se=(60.0, 88.0), wing=(4.6, 7.6), aux=(13.0, 3.8), depth=2.4,
                header=(0.0, 0.0), feed=1.0),
    facade=dict(base=7.0, clerestory=9.0, arch_band=(0.18, 0.86)),
    #: the corner towers (the orthophotos and l048: square limestone-capped towers at the four corners)
    towers=dict(size=22.0, extra=6.0),
    #: the wordmark over the window inside and on the facades (the Commons file's aspect, 2000 x 618)
    logo=dict(w=30.0, h=9.3),
    roof_letters=dict(x=(8.0, 40.0), z=(90.0, -60.0)),
    #: the transverse trusses under the roof (l092, l137: deep dark lattices across the building at even spacing)
    trusses=dict(count=12, z=(-100.0, 128.0), dir=(1.0, 0.0), w=1.6, depth=7.0),
    #: the trusses standing on the fixed roof (l056, l059: six a side, about 4 m high at the panels rising to 9 m at the
    #: eaves; DESIGN)
    outer_trusses=dict(count=6, z=(-92.0, 118.0), w=1.2, h=(4.0, 9.0)),
    banners=dict(w=3.2, h=7.5, north=8, side=6),
    flag=dict(at=(-78.0, -70.0), size=(8.2, 15.5)),
    lights=dict(every=2, w=4.4, h=2.2, drop=1.5, x=60.0, z=(-80.0, 112.0), step=9.0),
    sky=dict(radius=1900.0, points=48, height=800.0),
)


class LucasOil(um.USBank):
    GRADE = GRADE
    TOWER_AREA = TOWER_AREA
    TOWER_MIN_H, TOWN_RADIUS = TOWER_MIN_H, TOWN_RADIUS
    PARAMS = PARAMS

    def footprint(self):
        return footprint()

    def west_zone(self, lp):
        """True on the north end (-z): the retractable 100 level and the 400 level alone under the window."""
        return lp.w["W"] > 0.6

    # -- the gabled roof --------------------------------------------------------------------------------------------
    def roof_top(self, x, z):
        """The roof's top over (x, z): level along the axis, falling ``p1`` across the retractable panels and ``p2``
        across the fixed roof beyond them."""
        q = self.p["roof"]
        ax = abs(x - q["ridge_x"])
        if ax <= q["panel_w"]:
            return q["ridge"] - q["p1"] * ax
        return q["ridge"] - q["p1"] * q["panel_w"] - q["p2"] * (ax - q["panel_w"])

    def _roof(self):
        """The roof over the whole outline, in four grids across the building: the fixed roof west, the two panels on the
        ridge, the fixed roof east; the top (the panels' standing seams, the fixed membrane) and the underside (the deck
        between the purlins)."""
        q = self.p["roof"]
        st = self._roof_stations()
        cuts = [-q["panel_w"], 0.0, q["panel_w"]]
        top_m = self.meshes.setdefault("usb_roof_top", Mesh("usb_roof_top"))
        und = self.meshes.setdefault("usb_roof_under", Mesh("usb_roof_under"))
        parts = [(-1e9, cuts[0], "los_fixed_top"), (cuts[0], cuts[1], "los_panel_top"), (cuts[1], cuts[2], "los_panel_top"),
                 (cuts[2], 1e9, "los_fixed_top")]
        for lo, hi, mat in parts:
            rows_t, rows_u, rows_uv = [], [], []
            for z, xa, xb in st:
                a, b = max(xa, lo), min(xb, hi)
                if b - a < 0.5:
                    if len(rows_t) >= 2:
                        top_m.grid(mat, rows_t, rows_uv, facing=up)
                        und.grid("los_roof_under", rows_u, rows_uv, facing=down)
                    rows_t, rows_u, rows_uv = [], [], []
                    continue
                xs = list(np.linspace(a, b, 4))
                rows_t.append([(x, self.roof_top(x, z), z) for x in xs])
                rows_u.append([(x, self.roof_under(x, z), z) for x in xs])
                rows_uv.append([(x / 12.0, z / 12.0) for x in xs])
            if len(rows_t) >= 2:
                top_m.grid(mat, rows_t, rows_uv, facing=up)
                und.grid("los_roof_under", rows_u, rows_uv, facing=down)

    def _rails(self):
        """The panels' rail trusses along the building at the panels' outer edges (l092, l137: the deep lattices that
        carry the panels), like the ridge truss."""
        q = self.p["roof"]
        m = self.meshes.setdefault("usb_truss", Mesh("usb_truss"))
        zs = np.linspace(q["ridge_z_w"] + 4.0, q["ridge_z_e"] - 6.0, 16)
        for xr in (-q["panel_w"], q["panel_w"]):
            top = [(xr, self.roof_under(xr, z), z) for z in zs]
            for side in (-1, 1):
                x = xr + side * q["truss_w"] / 2
                upper = [(x, self.roof_under(x, z), z) for z in zs]
                lower = [(x, y - q["truss_depth"], z) for (_x, y, z) in upper]
                m.grid("usb_truss", [lower, upper], [[(z / 9.0, 1.0) for z in zs], [(z / 9.0, 0.0) for z in zs]],
                       facing=lambda p_, s=side: np.array([s, 0.0, 0.0]))
            bot_a = [(xr - q["truss_w"] / 2, y - q["truss_depth"], z) for (_x, y, z) in top]
            bot_b = [(xr + q["truss_w"] / 2, y - q["truss_depth"], z) for (_x, y, z) in top]
            m.grid("usb_truss", [bot_a, bot_b], [[(z / 9.0, 0.004) for z in zs], [(z / 9.0, 0.02) for z in zs]], facing=down)

    def _roof_letters(self):
        """LUCAS OIL STADIUM painted along the east panel (the orthophotos), read from the east, 0.3 m over the roof."""
        q = self.p["roof_letters"]
        m = self.meshes.setdefault("usb_roof_letters", Mesh("usb_roof_letters"))
        x0, x1 = q["x"]
        z0, z1 = q["z"]
        corners = [(x1, z0), (x1, z1), (x0, z1), (x0, z0)]
        P = [(x, self.roof_top(x, z) + 0.3, z) for x, z in corners]
        m.quad("los_roof_letters", P[0], P[1], P[2], P[3], (0, 1), (1, 1), (1, 0), (0, 0), facing=up)

    # -- the north window -------------------------------------------------------------------------------------------
    def north_wall_z(self):
        """z of the north wall's inner face on the axis (the outline's north edge less 0.4 m)."""
        P = self.outline()
        return float(min(P[:, 1])) + 0.4

    def window_top(self, x, q=None):
        q = q or self.p["window"]
        t = min(1.0, abs(x) / (q["w"] / 2))
        return q["sill"] + q["h"] - q["arch"] * t * t

    def _window(self):
        """The north window (l095, l096): six panels of lites in slim mullions from the sill over the north stands to the
        arch; the glass see-through inside and reflective outside (downtown's towers beyond it), the steel frame round it,
        the wordmark over it inside and the dark wall of the north end round it up to the roof (the facade leaves the
        window's opening)."""
        q = self.p["window"]
        z = self.north_wall_z()
        m = self.meshes.setdefault("usb_window", Mesh("usb_window"))
        n = 16
        xs = np.linspace(-q["w"] / 2, q["w"] / 2, n + 1)
        bot = [(x, q["sill"], z) for x in xs]
        top = [(x, self.window_top(x), z) for x in xs]
        us = [(x + q["w"] / 2) / q["w"] for x in xs]
        vt = [(q["sill"] + q["h"] - t[1]) / q["h"] for t in top]
        m.grid("LIGHT_los_window", [bot, top], [[(u, 1.0) for u in us], [(u, v) for u, v in zip(us, vt)]],
               facing=lambda p_: np.array([0.0, 0.0, 1.0]))
        out = [(x, y, z - 0.6) for x, y, z in bot], [(x, y, z - 0.6) for x, y, z in top]
        m.grid("LIGHT_los_facade_glass", [out[0], out[1]], [[(u * 2, 1.0) for u in us], [(u * 2, 0.0) for u in us]],
               facing=lambda p_: np.array([0.0, 0.0, -1.0]))
        # the frame: a mullion band round the opening
        for side in (-1, 1):
            x = side * (q["w"] / 2 + 0.8)
            m.box("los_window_frame", (x, (q["sill"] + self.window_top(side * q["w"] / 2)) / 2, z + 0.4),
                  ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                  (0.8, (self.window_top(side * q["w"] / 2) - q["sill"]) / 2 + 0.8, 0.5), uvscale=0.1)
        m.box("los_window_frame", (0.0, q["sill"] - 0.6, z + 0.4), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
              (q["w"] / 2 + 1.6, 0.6, 0.6), uvscale=0.1)
        # the wordmark over the window, inside
        lq = self.p["logo"]
        y0 = q["sill"] + q["h"] + 2.0
        right = np.array([1.0, 0.0, 0.0])
        c = np.array([0.0, y0, z + 0.3])
        self._panel(m, "los_logo", (0.0, y0, z + 0.9), (0.0, 0.0, 1.0), lq["w"], lq["h"], (0.0, 1.0))
        del right, c

    # -- the boards -------------------------------------------------------------------------------------------------
    def _boards(self):
        """The two main boards in the north-west and south-east corners (37 x 97 ft), each facing the field's centre with
        the live picture at its own aspect and a wing either side for the game's digits, and two auxiliary boards over
        each (the stadium's facts)."""
        q = self.p["boards"]
        m = self.meshes.setdefault("usb_boards", Mesh("usb_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        for key in ("nw", "se"):
            x, z = q[key]
            face = -np.array([x, 0.0, z])
            face /= np.linalg.norm(face)
            c = np.array([x, q["y"], z])
            self._board(m, c, face, q["w"], q["h"], q["wing"], self.board_frames, header=False)
            right = np.cross(-face, (0.0, 1.0, 0.0))
            right /= np.linalg.norm(right)
            aw, ah = q["aux"]
            for s_ in (-1, 1):
                ac = c + right * s_ * (aw / 2 + 0.6) + np.array([0.0, q["h"] + 1.4, 0.0])
                m.box("usb_black", ac + np.array([0.0, ah / 2, 0.0]), (right, (0, 1, 0), face),
                      (aw / 2 + 0.3, ah / 2 + 0.3, q["depth"] / 2), uvscale=0.1)
                fc = ac + face * (q["depth"] / 2 + 0.05)
                hv = np.array([0.0, ah, 0.0])
                m.quad("los_logo_aux", fc - right * aw / 2, fc + right * aw / 2, fc + right * aw / 2 + hv,
                       fc - right * aw / 2 + hv, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)

    # -- the banners --------------------------------------------------------------------------------------------------
    def _banners(self):
        """The Colts' banners hung from the trusses (l092, l137): a row over the north window and a row along each side
        under the roof (DESIGN, pass 1)."""
        q = self.p["banners"]
        m = self.meshes.setdefault("usb_banners", Mesh("usb_banners"))
        zw = self.north_wall_z() + 6.0
        for k in range(q["north"]):
            x = (k - (q["north"] - 1) / 2) * (q["w"] + 3.0)
            top = self.roof_under(x, zw) - 3.0
            u0 = (k % 4) / 4.0
            self._hang(m, (x, top, zw), (0.0, 0.0, 1.0), q["w"], q["h"], u0)
        for side in (-1, 1):
            x = side * 70.0
            for k in range(q["side"]):
                z = -60.0 + k * 30.0
                top = self.roof_under(x, z) - 2.5
                u0 = ((k + 1) % 4) / 4.0
                self._hang(m, (x, top, z), (-side, 0.0, 0.0), q["w"], q["h"], u0)

    def _hang(self, m, top, face, w, h, u0):
        face = np.array(face, float)
        right = -np.cross(face, (0.0, 1.0, 0.0))
        right /= np.linalg.norm(right)
        t = np.array(top, float)
        A, B = t - right * w / 2, t + right * w / 2
        dn = np.array([0.0, h, 0.0])
        m.quad("los_banners", A - dn, B - dn, B, A, (u0, 1), (u0 + 0.25, 1), (u0 + 0.25, 0), (u0, 0),
               facing=lambda p_, f=face: f)
        k = face * 0.05
        # printed on both sides: the back reads left to right too
        m.quad("los_banners", B - dn - k, A - dn - k, A - k, B - k, (u0, 1), (u0 + 0.25, 1), (u0 + 0.25, 0), (u0, 0),
               facing=lambda p_, f=face: -f)

    # -- the facade ---------------------------------------------------------------------------------------------------
    def _facade(self):
        """The outline's walls from below the plaza to the roof's edge: a glass base (the gates and the concourses), then
        the brick fieldhouse with its tall arched windows in a limestone surround (l035 to l049); on the north wall the
        window's opening is left for the window. Inside, the dark inner face and the clerestory under the roof."""
        q = self.p["facade"]
        wq = self.p["window"]
        m = self.meshes.setdefault("usb_facade", Mesh("usb_facade"))
        g = self.meshes.setdefault("usb_glass", Mesh("usb_glass"))
        P = self.outline()
        s = 0.0
        zn = float(min(P[:, 1]))
        zs_ = float(max(P[:, 1]))
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            e = b - a
            L = float(np.hypot(*e))
            if L < 0.05:
                continue
            n = np.array([e[1], -e[0]]) / L
            k = max(1, int(math.ceil(L / 10.0)))
            ts = np.linspace(0, 1, k + 1)
            pts = [a + (b - a) * t for t in ts]
            tops = [self.roof_top(float(p[0]), float(p[1])) for p in pts]
            outward = lambda p_, n=n: np.array([n[0], 0.0, n[1]])  # noqa: E731
            inward = lambda p_, n=n: -np.array([n[0], 0.0, n[1]])  # noqa: E731
            us = [s + L * t / 16.0 for t in ts]
            bot = [(float(p[0]), self.GRADE - 0.5, float(p[1])) for p in pts]
            base_ = [(float(p[0]), self.GRADE + q["base"], float(p[1])) for p in pts]
            top = [(float(p[0]), y, float(p[1])) for p, y in zip(pts, tops)]
            g.grid("LIGHT_los_facade_glass", [bot, base_], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
            north = n[1] < -0.9 and max(abs(a[1] - zn), abs(b[1] - zn)) < 1.5
            south = n[1] > 0.9 and max(abs(a[1] - zs_), abs(b[1] - zs_)) < 3.0
            if north:
                self._north_wall(m, a, b, n, s, L)
            elif south:
                self._north_wall(m, a, b, n, s, L, inner_mat="usb_dark", window=self.p["south_window"])
            else:
                lo, hi = q["arch_band"]
                mid = [(x, self.GRADE + q["base"] + (yt - self.GRADE - q["base"]) * hi, z) for (x, _y, z), yt in zip(base_, tops)]
                m.grid("los_arch_windows", [base_, mid], [[(u * 1.6, 1.0) for u in us], [(u * 1.6, lo) for u in us]],
                       facing=outward)
                m.grid("los_brick", [mid, top], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
                inner = lambda Q, n=n: [(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in Q]  # noqa: E731
                cl = [(x, max(yb, yt - q["clerestory"]), z) for (x, yb, z), yt in zip(base_, tops)]
                m.grid("usb_dark", [inner(base_), inner(cl)], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=inward)
                m.grid("LIGHT_usb_clerestory", [inner(cl), inner(top)],
                       [[(u * 1.5, 1.0) for u in us], [(u * 1.5, 0.0) for u in us]], facing=inward)
            s += L
        self._signs_outside()

    def _north_wall(self, m, a, b, n, s, L, inner_mat="usb_roof_under", window=None):
        """An end wall's brick round its arched window: full height outside the opening, below the sill and over the arch
        inside it. The north wall's inner face is the light steel structure round the window (l096: pale deck and steel,
        not a dark wall); the south wall's (``window`` the fixed arched glass, l056 and l059) is hidden by the stands."""
        wq = dict(self.p["window"], **(window or {}))
        wx = wq["w"] / 2 + 1.6
        outward = lambda p_, n=n: np.array([n[0], 0.0, n[1]])  # noqa: E731
        inward = lambda p_, n=n: -np.array([n[0], 0.0, n[1]])  # noqa: E731
        xa, xb = float(a[0]), float(b[0])
        lo_x, hi_x = min(xa, xb), max(xa, xb)

        def point(x):
            t_ = (x - xa) / (xb - xa)
            return a + (b - a) * t_

        def strip(x0, x1, ybot, ytop, mat, inner=False):
            if x1 - x0 < 0.2:
                return
            xs = np.linspace(x0, x1, max(2, int(math.ceil((x1 - x0) / 4.0)) + 1))
            ps = [point(x) for x in xs]
            lo_row = [(float(p[0]), ybot(float(p[0])), float(p[1])) for p in ps]
            hi_row = [(float(p[0]), ytop(float(p[0]), float(p[1])), float(p[1])) for p in ps]
            us = [s + abs(x - xa) / 16.0 for x in xs]
            m.grid(mat, [lo_row, hi_row], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
            if inner:
                m.grid(inner_mat, [[(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in lo_row],
                                    [(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in hi_row]],
                       [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=inward)
        base = lambda x: self.GRADE + self.p["facade"]["base"]  # noqa: E731
        roof = lambda x, z: self.roof_top(x, z)  # noqa: E731
        strip(lo_x, max(lo_x, -wx), base, roof, "los_brick", inner=True)
        strip(min(hi_x, wx), hi_x, base, roof, "los_brick", inner=True)
        a0, a1 = max(lo_x, -wx), min(hi_x, wx)
        strip(a0, a1, base, lambda x, z: wq["sill"], "los_brick", inner=True)
        arch = lambda x: min(self.window_top(x, wq) + 1.6, self.roof_top(x, a[1]) - 0.5)  # noqa: E731
        strip(a0, a1, arch, roof, "los_brick", inner=True)
        if window is not None:
            # the south facade's fixed arched window: reflective glass in the opening, facing out
            strip(a0, a1, lambda x: wq["sill"], lambda x, z: arch(x) - 1.6, "LIGHT_los_facade_glass")

    def _signs_outside(self):
        """The wordmark on the north and south facades over the gates (l040, l041), facing out."""
        lq = self.p["logo"]
        m = self.meshes.setdefault("usb_facade", Mesh("usb_facade"))
        P = self.outline()
        for zs in (-1, 1):
            z = (float(min(P[:, 1])) - 0.5) if zs < 0 else (float(max(P[:, 1])) + 0.5)
            face = (0.0, 0.0, float(zs))
            # over the window's arch on the north facade, and as high on the south one (l056, l059)
            y = self.p["window"]["sill"] + self.p["window"]["h"] + 2.0
            self._panel(m, "los_logo", (0.0, y, z), face, lq["w"], lq["h"], (0.0, 1.0), back=False)   # flush on the brick

    def _corner_towers(self):
        """The four corner towers (the orthophotos, l048): square brick shafts with limestone caps rising a little over the
        roof's edge at the outline's corners."""
        q = self.p["towers"]
        m = self.meshes.setdefault("usb_facade", Mesh("usb_facade"))
        P = self.outline()
        x0, x1 = float(min(P[:, 0])), float(max(P[:, 0]))
        z0, z1 = float(min(P[:, 1])), float(max(P[:, 1]))
        h = q["size"] / 2
        for cx, cz in ((x0 + h, z0 + h), (x1 - h, z0 + h), (x0 + h, z1 - h), (x1 - h, z1 - h)):
            top = self.roof_top(cx, cz) + q["extra"]
            box = [(cx - h, cz - h), (cx + h, cz - h), (cx + h, cz + h), (cx - h, cz + h)]
            self._extrude(m, box, self.GRADE, top, "los_brick", "los_tower_cap", uscale=1 / 16.0)

    def _outer_trusses(self):
        """The transverse trusses standing on the fixed roof either side of the panels (l056, l059: dark steel lattices
        rising over the roof from the panels' edges to the eaves), ``count`` a side, facing along the field."""
        q = self.p["outer_trusses"]
        rq = self.p["roof"]
        m = self.meshes.setdefault("usb_trusses_out", Mesh("usb_trusses_out"))
        P = self.outline()
        x_eave = float(max(P[:, 0])) - 2.0
        for z in np.linspace(q["z"][0], q["z"][1], q["count"]):
            for side in (-1, 1):
                xs = np.linspace(rq["panel_w"], x_eave, 8) * side
                base = [(float(x), self.roof_top(float(x), float(z)) + 0.2, float(z)) for x in xs]
                h0, h1 = q["h"]
                top = [(x, y + h0 + (h1 - h0) * k / (len(xs) - 1), zz) for k, (x, y, zz) in enumerate(base)]
                us = [abs(x) / 7.0 for x in xs]
                for face in (-1, 1):
                    off = np.array([0.0, 0.0, face * q["w"] / 2])
                    m.grid("usb_truss", [[tuple(np.array(p) + off) for p in base], [tuple(np.array(p) + off) for p in top]],
                           [[(u, 1.0) for u in us], [(u, 0.0) for u in us]],
                           facing=lambda p_, f=face: np.array([0.0, 0.0, float(f)]))

    def _flag(self):
        """The United States flag hung vertically from the roof over the west side's north stands (l092, l137)."""
        um.USBank._flag(self)

    # -- build --------------------------------------------------------------------------------------------------------
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
        self._concourse_west(loop, secs)
        self._roof()
        self._truss()
        self._rails()
        self._lights()
        self._boards()
        self._window()
        self._banners()
        north = min(loop, key=lambda lp: (lp.nx - 1) ** 2 + (lp.z / 40.0) ** 2)
        row = self.section(north)["upper"][4]
        self.nosebleed = self.at(north, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._corner_towers()
        self._roof_letters()
        self._queen_trusses()
        self._outer_trusses()
        self._flag()
        self._exterior()
        self._sky()
        self._rename()
        return self

    def camera_eyes(self):
        return um.shot_eyes(lucas_oil_shots())

    def _rename(self):
        """The shared parts draw with the U.S. Bank model's material and mesh names: this model's own are ``los_``."""
        def r(name):
            return name.replace("LIGHT_usb_", "LIGHT_los_").replace("usb_", "los_")
        meshes = {}
        for mesh in self.meshes.values():
            mesh.name = r(mesh.name)
            mesh.groups = {r(k): v for k, v in mesh.groups.items()}
            meshes[mesh.name] = mesh
        self.meshes = meshes


def build(venue=VENUE, params=None):
    return LucasOil(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = um.KEEP_PREFIXES
KEEP_YARD = um.KEEP_YARD
KEEP_MATERIALS_BY_CODE = um.KEEP_MATERIALS_BY_CODE
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "los_seat_front": ("los_seat_front", CLASS_OPAQUE), "los_seat_mid": ("los_seat_mid", CLASS_OPAQUE),
    "los_seat_back": ("los_seat_back", CLASS_OPAQUE), "los_concrete": ("los_concrete", CLASS_OPAQUE),
    "los_wall": ("los_wall", CLASS_OPAQUE), "LIGHT_los_ribbon": ("LIGHT_los_ribbon", CLASS_OPAQUE),
    "LIGHT_los_glass": ("LIGHT_los_glass", CLASS_OPAQUE), "LIGHT_los_concourse": ("LIGHT_los_concourse", CLASS_OPAQUE),
    "los_portal": ("los_portal", CLASS_OPAQUE), "los_dark": ("los_dark", CLASS_OPAQUE), "los_black": ("los_black", CLASS_OPAQUE),
    "los_roof_under": ("los_roof_under", CLASS_OPAQUE), "los_truss": ("los_truss", CLASS_ALPHA),
    "los_panel_top": ("los_panel_top", CLASS_OPAQUE), "los_fixed_top": ("los_fixed_top", CLASS_OPAQUE),
    "los_roof_letters": ("los_roof_letters", CLASS_ALPHA), "LIGHT_los_lights": ("LIGHT_los_lights", CLASS_OPAQUE),
    "LIGHT_los_window": ("LIGHT_los_window", CLASS_ALPHA), "los_window_frame": ("los_window_frame", CLASS_OPAQUE),
    "LIGHT_los_facade_glass": ("LIGHT_los_facade_glass", CLASS_OPAQUE),
    "los_brick": ("los_brick", CLASS_OPAQUE), "los_arch_windows": ("los_arch_windows", CLASS_OPAQUE),
    "los_tower_cap": ("los_tower_cap", CLASS_OPAQUE), "los_logo": ("los_logo", CLASS_ALPHA),
    "los_logo_aux": ("los_logo", CLASS_ALPHA), "LIGHT_los_board_wing": ("LIGHT_los_board_wing", CLASS_OPAQUE),
    "los_banners": ("los_banners", CLASS_OPAQUE), "LIGHT_los_clerestory": ("LIGHT_los_clerestory", CLASS_OPAQUE),
    "los_flag": ("los_flag", CLASS_OPAQUE),
    "los_plaza": ("los_plaza", CLASS_OPAQUE), "los_lawn": ("los_lawn", CLASS_OPAQUE), "los_asphalt": ("los_asphalt", CLASS_OPAQUE),
    "los_road": ("los_road", CLASS_OPAQUE), "los_building": ("los_building", CLASS_OPAQUE),
    "LIGHT_los_towers": ("LIGHT_los_towers", CLASS_OPAQUE), "los_sky": ("los_sky", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "los_seat_front": (214, 208, 200), "los_seat_mid": (214, 208, 200), "los_seat_back": (214, 208, 200),
    "crowd": (222, 216, 210), "los_concrete": (206, 200, 192), "los_wall": (232, 226, 222),
    "LIGHT_los_ribbon": (255, 255, 255), "LIGHT_los_glass": (190, 186, 255), "LIGHT_los_concourse": (214, 208, 255),
    "los_portal": (160, 156, 150), "los_dark": (190, 186, 180), "los_black": (200, 196, 190),
    "los_roof_under": (216, 210, 176), "los_truss": (210, 204, 180), "los_panel_top": (200, 184, 110),
    "los_fixed_top": (190, 176, 100), "los_roof_letters": (236, 220, 120), "LIGHT_los_lights": (255, 255, 255),
    "LIGHT_los_window": (244, 234, 255), "los_window_frame": (200, 196, 190), "LIGHT_los_facade_glass": (228, 212, 255),
    "los_brick": (220, 204, 150), "los_arch_windows": (220, 204, 150), "los_tower_cap": (224, 208, 150),
    "los_logo": (255, 255, 255), "los_logo_aux": (255, 255, 255), "LIGHT_los_board_wing": (255, 255, 255),
    "jumbo_tron": (255, 255, 255), "los_banners": (228, 222, 214), "LIGHT_los_clerestory": (236, 230, 255),
    "los_flag": (220, 214, 200),
    "los_plaza": (226, 206, 120), "los_lawn": (224, 204, 80), "los_asphalt": (220, 200, 90), "los_road": (220, 200, 90),
    "los_building": (220, 200, 110), "LIGHT_los_towers": (214, 200, 255), "los_sky": (255, 255, 255),
}
#: the sun over Indianapolis (DESIGN): by day high in the south (bearing 180: x 0.435, z 0.900 in this frame), in the
#: afternoon low in the south-west (bearing 240)
SUN = {"d": (0.26, 0.80, 0.54), "a": (-0.48, 0.52, 0.71), "n": None}
TINT = um.TINT
OUTSIDE = {"los_panel_top", "los_fixed_top", "los_roof_letters", "LIGHT_los_facade_glass", "los_brick", "los_arch_windows",
           "los_tower_cap", "los_plaza", "los_lawn", "los_asphalt", "los_road", "los_building", "LIGHT_los_towers",
           "los_sky"}
#: inside, one light level for every surface (the roof closed: main, 2026-09-27)
INSIDE_LIGHT = um.INSIDE_LIGHT
#: textures with their own night drawing (downtown's towers, the clerestory and the north window)
NIGHT_TEXTURES = ("LIGHT_los_towers", "LIGHT_los_clerestory", "LIGHT_los_window")


def light(mat, P, N, tod, weather, outside=False):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
    base = BASE.get(mat, (200, 190, 150))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat == "los_sky":
        return np.full((n, 4), 255, np.uint8)
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
    if mat == "los_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat in ("los_panel_top", "los_fixed_top", "los_brick", "los_arch_windows", "los_tower_cap") and tod == "n":
        out[:, 0] = 70; out[:, 1] = 70; out[:, 2] = 78
    return out


def _textures(venue, tod, weather):
    out = {}
    for key in dict.fromkeys(k for k, _c in MATERIALS.values()):   # MATERIALS order: deterministic across processes
        if key.startswith("env_"):
            continue
        name = f"los_sky_{tod}" if key == "los_sky" else f"{key}_n" if key in NIGHT_TEXTURES and tod == "n" else key
        out[key] = um._rgba(ART_DIR / f"{name}.png")
    out.update(env.textures(venue, tod, weather))
    return out


flare_points = um.flare_points
adjust_digits = um.adjust_digits
dry_of = ag.dry_of
league_banner = ag.league_banner


def build_scene(retail_bundle, filename, model, dry_bundle=None):
    """The Lucas Oil stadium scene for one bundle, built on the retail scene's records the engine reads (the U.S. Bank
    model's assembly with this model's materials)."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "los_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "los_digits", tmpl_shape)
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
    """(bundle bytes, info): the retail bundle with its stadium scene replaced by the Lucas Oil model and its intro cameras
    rewritten when ``cameras`` gives the shots. s11 has no cityscape: the stretch from the stadium chunk to the end of the
    cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    sb.require("cityscape" not in scenes, "s11 carries no cityscape chunk")
    cam_chunk, cam_dec = mm._cameras_chunk(retail_bundle)
    sb.require(cam_chunk.offset == st.offset + 32 + st.stored_size, "intro cameras do not follow the stadium chunk")
    start = st.offset
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
    room = end - start - len(cam_out) - 32
    room -= room % 16
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, sm._chunk_span(retail_bundle, st), stored=room)
    stretch_ = chunk + cam_out
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
                     markers=len(sc.markers), stretch=[start, end], retail_system=st.system_bytes,
                     retail_video=st.video_bytes, vertices=sum(s.vertex_count for s in sc.shapes))


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s11 intro camera's channel carries (PROVED OFFLINE from the retail s11 scenes): camera 1
#: pitch, y and z (pitch and y move; x and yaw play as 0: it looks north along the axis); camera 2 x, y, yaw and z (no
#: pitch: level; x, yaw and z move); camera 3 pitch, x, y and yaw (no z: at midfield; yaw moves); camera 4 all five
#: (multi-segment: held still); camera 5 all five (all move).
CAMERA_COMPONENTS_PRESENT = ({"pitch", "y", "z"}, {"x", "y", "yaw", "z"}, {"pitch", "x", "y", "yaw"},
                             {"pitch", "x", "y", "yaw", "z"}, {"pitch", "x", "y", "yaw", "z"})

#: DESIGN, pass 1: the Lucas Oil flyover, one shot per retail camera.
#: 1: a crane on the axis rising toward the north window and downtown in it;
#: 2 (level): a pass along the west side's upper level toward the north end;
#: 3 (at midfield): from the east upper deck, panning across the bowl to the north-west board and the window;
#: 4 (still): outside at the north-east, the window wall and the wordmark from the street;
#: 5: an aerial push over the gabled roof from the south-east with downtown beyond it.
_CRANE = dict(eye=(0.0, 8.0, 30.0), target=(0.0, 40.0, -117.0), fov=46.0, rates=dict(y=2.4, pitch=0.5))
_PASS = dict(eye=(-72.0, 44.0, 60.0), target=(-10.0, 44.0, -70.0), fov=44.0, rates=dict(z=-4.0, yaw=-1.0))
_PAN = dict(eye=(70.0, 46.0, 0.0), target=(-40.0, 32.0, -100.0), fov=44.0, rates=dict(yaw=2.5))
_NORTH = dict(eye=(150.0, 22.0, -330.0), target=(0.0, 45.0, -118.0), fov=40.0, rates=dict())
_AERIAL = dict(eye=(240.0, 170.0, 330.0), target=(0.0, 60.0, 10.0), fov=40.0, rates=dict(x=-4.0, z=-5.0, y=-1.0))
LOS_SHOTS = [_CRANE, _PASS, _PAN, _NORTH, _AERIAL]


def lucas_oil_shots():
    out = []
    for s, present in zip(LOS_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=lucas_oil_shots(), dry_bundle=dry)
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
    """{bundle name: retail bytes} of the nine s11 bundles, each checked against its pinned SHA-256."""
    ml = sm._ml()
    out = {}
    with ml._outer_image()(str(source)) as archive:
        for name, pin in _venue_pins().items():
            e = _entry(archive, pin)
            data = archive.read(e.virtual_offset, e.size)
            sb.require(sha(data) == pin["retail_sha256"], f"{name}: the source bundle is not retail")
            out[name] = data
    return out


stretch = um.stretch


def build_all(source, *, workers=None, progress=None, names=None):
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers, progress=progress, label="Lucas Oil Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field

#: The field (Hellas Matrix Turf, synthetic, 2024; Wikipedia): the retail s11 field is a turf venue with one colour quad
#: between the goal lines, its own north and south end-zone textures and its own midfield logo. The model puts the
#: Colts' 2026 end zones and midfield horseshoe from the league project's art (the u4 IND venue folder) in place, over
#: the retail turf's own colour, and then the turf and the apron take the Modern playing surfaces palette for s11 through
#: that option's own painter (main, 2026-09-27: the field's colours on tf's palette, never tuned here).
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
    """The Lucas Oil field for one bundle (decoded, the retail layout kept): the Colts' end zones over the retail turf's own
    colour and the midfield horseshoe in the retail midfield texture. The turf and the apron are tf's (surface_span)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    turf, _pal = ml.read_p8(out, system, rows[GRASS_MATERIAL])
    clean = np.array(np.median(turf.reshape(-1, 4), axis=0), np.float32)

    def over_turf(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    team = {k: v for k, v in dict(team or {}).items() if k in TEAM_FIELD}
    if team and not any(k.startswith("endzone_S_") for k in team):
        team.update({k.replace("_N_", "_S_"): v for k, v in list(team.items()) if k.startswith("endzone_N_")})
    detail = sm._half_detail if half else (lambda a: a)
    for mat, art in team.items():
        row = rows.get(mat)
        if row is None:
            continue
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        if mat in ENDZONE_TEXTURES:
            a = over_turf(a)
        ml.write_p8(out, system, row, detail(a), maximum=cap)
    return bytes(out)


def surface_span(span, bundle, name, colour_settings=None):
    """(field span, tf's receipt): the playing surface and the apron on tf's palette for s11 (the synthetic look, the 2026
    broadcast measured at Lucas Oil Stadium, the dome light), through tf's own painter and fit, after the end-zone art."""
    from . import nfl2k5_modern_surfaces as ms
    look = ms.venue_look(VENUE)
    cls = ms.light_class(name, True)
    rig = ms.rig_name(cls, name[3])
    return ms.field_span(span, look=look, cls=cls, rig=rig, colour_settings=colour_settings, tint=ms.field_tint(bundle),
                         target=ms.venue_target(VENUE, look, cls))


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle (Allegiant's ladder and colour path, then tf's
    surface)."""
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
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               team_art=sorted(team or {}),
                               surface={k: surf.get(k) for k in ("look", "light", "rig", "layout", "target", "map_mean",
                                                                  "outside_mean", "palette_cap", "refit")},
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{rung}: {exc}")
    raise sb.ScneBuildError(f"{name}: the Lucas Oil field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_lucas_oil_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_lucas_oil_receipt/v1"
BUILD_CAPTION = "Lucas Oil Stadium for the Colts (experimental)"
HELP_TEXT = (
    "The Indianapolis Colts' Lucas Oil Stadium, built as a new model for Colts home games in every time of day: the "
    "blue bowl under the gabled roof drawn closed (the two retractable panels on the ridge, the fixed roof and its "
    "trusses), the north window with downtown's skyline beyond it, the two corner video boards with the live feed, the "
    "Colts' banners, the brick and limestone fieldhouse with its corner towers and the wordmark, and a new pregame "
    "flyover with exterior passes. The field is the 2026 turf on the Modern surfaces palette with the 2026 venue art's "
    "Colts end zones and midfield horseshoe when that option is on. The row reads Lucas Oil Stadium, Indianapolis, IN; the "
    "roof is drawn closed, so no rain or snow falls. The 2026 venue art leaves the Colts' packages to it. Off in every "
    "preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "Lucas Oil Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Lucas Oil Stadium pins schema")
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
    """retail / applied / foreign for the Lucas Oil stretch of one of the nine bundles."""
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
    return Path(str(source) + ".lucas_oil.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported Lucas Oil Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s11 row."""
    from . import nfl2k5_lucas_oil_venue as uv
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
    sb.require(state == ("applied" if enabled else "retail"), f"Lucas Oil Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_lucas_oil")
def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already Lucas Oil)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Colts stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=lucas_oil_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_lucas_oil")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s11 to it; before Modern surfaces, the last
    stadium writer, which keeps this field's paint): the Lucas Oil field, stadium and cameras of the nine bundles, and the
    s11 row. The retail bundles come from ``retail_source``; the image's own bundles keep every other chunk. With Modern
    colour on, the field is composed before the colour grade and the colour receipt is updated so Modern colour still
    recognizes its bytes; the turf and apron then take the Modern surfaces palette for s11 through that option's own
    painter. ``art_root`` is the 2026 venue art folder: its Colts end zones and midfield horseshoe go onto the new field
    (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_lucas_oil_venue as uv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries Lucas Oil Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"Lucas Oil Stadium needs retail Colts packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Lucas Oil Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the Lucas Oil bundle changed size")
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
        new_colour["lucas_oil"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after Lucas Oil Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"Lucas Oil Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("Lucas Oil Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_lucas_oil_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the Lucas Oil stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st3-lucas-oil.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST3_LUCAS_OIL_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
