"""U.S. Bank Stadium model (experimental): the Minnesota Vikings' U.S. Bank Stadium (Minneapolis, opened 2016; HKS) built
from scratch as the stadium scene of venue record s15 (retail H. H. H. Metrodome), all nine bundles (day, afternoon,
night; dry, rain, snow).

Job st3 (2026-09-27), on u5's builder, u6's SoFi methods and st's Highmark, AT&T, Levi's and Allegiant models. References
(Wikipedia, the stadium's own fact guide, vikings.com 2016 and 2026, Daktronics, Thornton Tomasetti, Kawneer, the
official stadium maps, TickPick's rows, OpenStreetMap, the Minnesota county orthophotos, 62 Commons photos 2015 to 2026
and the Vikings' 2026 week 1 galleries) are cited in the st3 report. The scene:

* the purple bowl: on both sidelines the 100 level, the suite band, the 200 level (the clubs), the Loft suites and the
  300 level; the east end the same, with the 51 x 88 ft board in its upper level; the west end the lower bowl only, its
  main concourse open to the Legacy Gate's glass wall; crowd billboards in the retail convention, cut at every aisle
  (u6's method); the ribbons on the fascias;
* the fixed roof on its single ridge truss down the length of the field: the ETFE south of the ridge (bright panels on a
  white steel grid from below), the opaque roof north of it (dark steel), 205 ft at the east rising to 272 ft at the tip
  of the prow on the west (vikings.com 2016-07-22), the floodlights under it;
* the west end: the glass wall from the concourse to the roof with downtown's towers beyond it, and the 68 x 120 ft
  board with its two 43 x 15 ft wings and the usbankstadium header in front of it (Daktronics; the board's bottom about
  10 ft over the main concourse, vikings.com 2016-01-20);
* the facade on the OpenStreetMap outline: dark zinc-coloured panels over a glass base, the reflective glass of the
  west walls, the prow leaning out over Medtronic Plaza with the two-line wordmark and its 49 x 76 ft display;
* outside: Medtronic Plaza, the Commons park, the light rail, the streets, the blocks round the site from OpenStreetMap,
  downtown's towers and a sky backdrop (s15's bundles carry no sky texture);
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the field-level banners
  (projected onto the new wall, with u4's 2026 league cloths), the digit shapes (moved onto the board wings), the
  markers and the materials the executable looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

Geometry is in metres here (x across, +x the north sideline: the visitors' bench; -x the south sideline: the Vikings'
bench, where every retail stadium keeps the home sideline props; y up from the field; z along, +z the east end, -z the
west end) and centimetres in the game. The field axis (+z) points to bearing 126 degrees (INFERRED from two interior
photos sighting the Capella Tower). The row keeps its indoor word 1 (the roof is fixed). EXPERIMENTAL and UNWITNESSED in
game unless a report says otherwise.
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

from . import nfl2k5_allegiant_model as ag
from . import nfl2k5_metlife_model as mm
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_sofi_model as sm
from . import nfl2k5_stadium_environment as env

OWNER = "nfl2k5_usbank_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_usbank_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
VENUE = "s15"
VENUES = (VENUE,)
#: the plaza and the main concourse over the field (INFERRED: the west board's bottom solves to 20.4 m over the field in
#: the 2023 end-zone photo, and the boards hang about 10 ft over the main concourse, vikings.com 2016-01-20)
GRADE = 17.0
#: the largest plan a downtown tower's box keeps (m2): the shafts read about 35 m wide from the stadium (INFERRED: the
#: Capella Tower spans about 2 degrees at 909 m in the 2023 end-zone photo u014; its OSM box is 45 m square)
TOWER_AREA = 1200.0
#: the budget: downtown's towers of 90 m and more; the blocks round the site within 420 m as boxes
TOWER_MIN_H, TOWN_RADIUS = 90.0, 420.0
_FOOTPRINT = None

Mesh = mm.Mesh
toward_field, up_toward_field, up, down = mm.toward_field, mm.up_toward_field, mm.up, mm.down


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


# ------------------------------------------------------------------------------------------------ the plan loop

def plan_loop(xn, xs, ze, zw, R, step=7.0, corner_steps=9):
    """The field-wall line (Allegiant's rounded rectangle) with the side weights renamed to this frame: N +x (north), S -x
    (south), E +z (east), W -z (west)."""
    pts = ag.plan_loop4(xn, xs, ze, zw, R, step, corner_steps)
    for lp in pts:
        w = lp.w
        lp.w = dict(N=w["E"], S=w["W"], E=w["S"], W=w["N"])
    return pts


# ------------------------------------------------------------------------------------------------ parameters

#: DESIGN, pass 1. The wall line clears the retail s15 sideline props (x -41.5 to 41.4; one away piece reaches z 63.3 at
#: the east end). Rows from TickPick's USBANK_NFL2 map (100 level about 37 rows on the sidelines, 40 to 44 at the ends;
#: 200 level 15; 300 level 5 balcony rows plus 18 to 25) and the photos; heights from the 2023 end-zone photo's solve.
PARAMS = dict(
    loop=dict(xn=43.5, xs=43.5, ze=65.0, zw=66.0, R=20.0, step=7.0, corner_steps=9),
    wall=dict(height=1.3),
    sides=dict(
        N=dict(low_d0=2.5, low_y0=1.4, low_rows=36, low_tread=0.86, low_rise0=0.30, low_rise1=0.52,
               t2_over=4.0, t2_rows=15, t2_rise=0.56, band_h=4.0,
               up_d=40.0, up_y=34.0, up_rows=26, up_tread=0.82, up_rise=0.64),
        S=dict(low_d0=2.5, low_y0=1.4, low_rows=33, low_tread=0.86, low_rise0=0.30, low_rise1=0.54,
               t2_over=4.0, t2_rows=15, t2_rise=0.56, band_h=4.0,
               up_d=40.0, up_y=34.0, up_rows=24, up_tread=0.82, up_rise=0.64),
        E=dict(low_d0=2.5, low_y0=1.4, low_rows=40, low_tread=0.86, low_rise0=0.30, low_rise1=0.50,
               t2_over=4.0, t2_rows=15, t2_rise=0.56, band_h=3.0,
               up_d=38.0, up_y=28.0, up_rows=20, up_tread=0.82, up_rise=0.64),
        W=dict(low_d0=2.5, low_y0=1.4, low_rows=40, low_tread=0.86, low_rise0=0.30, low_rise1=0.50,
               t2_over=4.0, t2_rows=0, t2_rise=0.56, band_h=0.0,
               up_d=41.0, up_y=37.0, up_rows=0, up_tread=0.82, up_rise=0.64),
    ),
    tier=dict(tread=0.88, fascia_h=1.25, gap=0.45),
    rim=dict(back_wall=2.6, walk=5.0, dark=3.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35, aisle=1.2),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0, rows_per_grid=4),
    sections=dict(straight_m=14.0, corner=3),
    portals=dict(every_m=24.0, lower_row=12, upper_row=6, width=2.4, height=2.2),
    #: the fixed roof (vikings.com 2016-07-22: 205 ft at the east rising to 272 ft at the tip of the prow; the roof
    #: pitches steeply from the single ridge truss to the gutters; Thornton Tomasetti: the ridge truss runs down the length
    #: of the field, 36 ft deep and 16 ft wide; the ETFE south of it). Heights over the field (the street is GRADE over
    #: it). The ridge sits over the field's axis (INFERRED: the ETFE's edge in the 2022 Hennepin orthophoto); the pitches
    #: are DESIGN, pass 1.
    #: Pass 2: the south slope falls to a level gutter ``eave_s`` over the field at x ``eave_x`` (the aerials u053 and
    #: u054, and u047: the Legacy Gate glass is about two thirds as tall at its south corner as at the prow; DESIGN).
    #: Pass 3: the ridge 10 m north of the field's axis (INFERRED, +-8 m: the ETFE's edge over the stands in the solved
    #: 2023 end-zone photo u014 and in u003; the ETFE's 60 percent share of the roof puts it near 20; the Esri
    #: orthophoto's edge, corrected for the roof's lean, near 0), both slopes falling to level gutters (the opaque
    #: north plane steeper: u054, u055).
    roof=dict(ridge_x=10.0, ridge_e=79.5, ridge_w=93.0, ridge_z_e=130.0, ridge_z_w=-125.0, tip=99.9,
              pitch_s=0.19, pitch_n=0.17, eave_s=61.0, eave_x=-115.0, eave_n=62.0, eave_xn=116.0, depth=6.0, station=9.0,
              truss_depth=11.0, truss_w=4.9),
    #: the Legacy Gate's glass (the west faces of the outline) and the five pivoting doors, 75 to 95 ft high and 55 ft
    #: wide (the stadium's fact guide)
    glass=dict(face_nz=0.45, north_x=6.0, door_w=16.8, door_h=(22.9, 29.0)),
    #: the boards (Daktronics 2016): the west board 68 x 120 ft with two 43 x 15 ft wings, the east board 51 x 88 ft with
    #: two 25 x 15 ft wings; the west board's bottom 20.4 m over the field and its middle about 2 m south of the axis in
    #: the 2023 end-zone photo's solve (DESIGN: centred on the axis)
    boards=dict(w_w=36.6, w_h=20.7, w_y=20.4, w_z=-118.0, w_wing=(4.6, 13.1),
                e_w=26.8, e_h=15.5, e_y=17.5, e_z=96.5, e_wing=(4.6, 7.6),
                depth=2.4, header=(0.70, 4.6), feed=1.0, blue_sign=(30.0, 6.0, 2.5)),
    #: the walls: the glass base's height over the plaza, the prow's north-west glass (its dark band under the roof at
    #: the tip, its height over the plaza at the face's far end) and the clerestory band inside under the roof (u017)
    facade=dict(base=7.0, nw_band=4.0, nw_low=14.0, clerestory=9.0),
    prow=dict(display=(23.2, 14.9), letters=(34.0, 17.0), gap=2.5),
    #: the wordmark on the north slope (u055; the orthophotos: about 140 m long) and the transverse trusses along the
    #: rafters (bearing 26.6 degrees: x 0.987, z -0.163 in this frame)
    roof_letters=dict(x=(34.0, 56.0), z=(72.0, -72.0)),
    trusses=dict(count=11, z=(-108.0, 108.0), dir=(0.987, -0.163), w=1.4, depth=7.5),
    #: the flag hung vertically (u003, u019: about 27 x 51 ft) between the 3M panel and the banner
    flag=dict(at=(23.0, 118.0), size=(8.2, 15.5)),
    #: the east end (u003, u019; sizes against the 88 ft board, DESIGN): the banner (width, slope height, its bottom
    #: edge's height and z, lean back in degrees); the 3M panel along the top concourse's back (from x, to x, height,
    #: bottom, offset toward the field); the Land O'Lakes panel over the north upper deck's west end, facing the field
    #: (its ends' x and z, height, bottom: the south end triangulated from u014 and u044, 2.5 m apart; the north end on
    #: u014's ray, within 20 px of the photo in both)
    east=dict(banner=(38.0, 14.0, 47.0, 119.5, 20.0), panel_3m=(27.5, 53.0, 8.2, 47.0, 0.6),
              panel_lol=(57.5, -110.0, 84.7, -93.0, 8.5, 47.5)),
    lights=dict(every=2, w=4.4, h=2.2, drop=1.5, x=64.0, z=(-88.0, 92.0), step=9.0),
    sky=dict(radius=1900.0, points=48, height=800.0),
)


def _side_blend(lp, key, p):
    return sum(lp.w[s] * p["sides"][s][key] for s in "NSEW")


# ------------------------------------------------------------------------------------------------ the model

class USBank(sm.SoFi):
    SECTORS = 12
    #: the building's constants, as class attributes so a sibling model (Lucas Oil) can reuse the methods
    GRADE = GRADE
    TOWER_AREA = TOWER_AREA
    TOWER_MIN_H, TOWN_RADIUS = TOWER_MIN_H, TOWN_RADIUS
    PARAMS = PARAMS

    def footprint(self):
        return footprint()

    def __init__(self, params=None, venue=VENUE):
        p = json.loads(json.dumps(self.PARAMS))
        for k, v in (params or {}).items():
            if k == "sides":
                for s, vv in v.items():
                    p["sides"][s].update(vv)
            else:
                p[k].update(v)
        self.p, self.venue = p, venue
        q = p["loop"]
        self.loop = plan_loop(q["xn"], q["xs"], q["ze"], q["zw"], q["R"], q["step"], q["corner_steps"])
        self.aisles = self._aisle_positions()
        self.meshes = {}
        self.markers = {}

    def west_zone(self, lp):
        """True on the west end straight, where the lower bowl alone stands before the glass wall."""
        return lp.w["W"] > 0.6

    # -- the section: four stacks, blended round the corners ------------------------------------------------------
    def section(self, lp):
        p = self.p
        return self._allegiant_stack_pass1(lambda key: _side_blend(lp, key, p), lp)

    # ig (integration, 2026-09-28): Allegiant pass 2 (b76-st2 72ec9716) gave Allegiant._stack board clearances
    # (self.board_hits) and a per-side back wall. U.S. Bank, Lucas Oil and State Farm were built and pinned against
    # pass 1's section (the stack st3 was rebased on), so they keep that exact code: a verbatim copy of
    # Allegiant._stack at eb11b3d7. It reads only self.p, self.facade_depth and self.lanai_zone, all U.S. Bank's own.
    def _allegiant_stack_pass1(self, g, lp):
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
                if self.lanai_zone(lp):
                    rowsu = 0
            if rowsu < 2:
                # no upper deck (the lanai end): the club tier's back wall and a walk behind it, where the glass stands
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

    def lanai_zone(self, lp):                   # Allegiant's _stack asks: no upper deck at the west end
        return self.west_zone(lp)

    def facade_depth(self, lp):
        """Distance from a wall-line point along its outward normal to the building's outline (OSM)."""
        cache = self.__dict__.setdefault("_facade_depth", {})
        key = (round(lp.x, 4), round(lp.z, 4), round(lp.nx, 4), round(lp.nz, 4))
        if key not in cache:
            ring = np.array(self.footprint()["facade"], float)
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
            self.prefix = f"usb_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self.prefix = "usb"
        self._concourse_west(loop, secs)
        self._roof()
        self._truss()
        self._lights()
        self._boards()
        self._east_wall()
        self._signs(loop, secs)
        north = min(loop, key=lambda lp: (lp.nx - 1) ** 2 + (lp.z / 40.0) ** 2)
        row = self.section(north)["upper"][4]
        self.nosebleed = self.at(north, row[0] + 0.3, row[1] + 0.05)
        self._facade()
        self._prow()
        self._roof_letters()
        self._queen_trusses()
        self._flag()
        self._exterior()
        self._sky()
        return self

    def mesh(self, name):
        if name.startswith("usb_bowl_"):
            name = getattr(self, "prefix", "usb_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    # -- the seats ------------------------------------------------------------------------------------------------
    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
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
        for mat, i0, i1 in (("usb_seat_front", 0, a), ("usb_seat_mid", a, b), ("usb_seat_back", b, len(ks) - 1)):
            if i1 > i0:
                m.grid(mat, pts[i0:i1 + 1], uvs[i0:i1 + 1], facing=up_toward_field)

    _runs = staticmethod(ag.Allegiant._runs)

    def _rows_runs(self, m, loop, secs, key):
        for run in self._runs(secs, key, lambda sec: len(sec[key]) > 1):
            lps = [loop[i] for i in run]
            prof = [secs[i][key] for i in run]
            self._rows_surface(m, "usb_seat", lps, prof, 2)
            self._crowd(m, lps, prof)

    # -- the bowl -----------------------------------------------------------------------------------------------
    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("usb_bowl_a")
        wall = p["wall"]["height"]
        m.grid("usb_wall", [[(lp.x, 0.0, lp.z) for lp in loop], [(lp.x, wall, lp.z) for lp in loop]],
               [[(lp.s / (8 * wall), 1.0) for lp in loop], [(lp.s / (8 * wall), 0.0) for lp in loop]], facing=toward_field)
        first = [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]
        wall_top = [(lp.x, wall, lp.z) for lp in loop]
        m.grid("usb_concrete", [wall_top, first], [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]],
               facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._rows_surface(m, "usb_seat", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", p["portals"]["lower_row"])
        m2 = self.mesh("usb_bowl_b")
        # the fascia over the lower bowl, the concourse behind it and the 200 level (not at the west end)
        self._band(m2, "LIGHT_usb_concourse", loop, secs, "lower_back", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "usb_concrete", loop, secs, "soffit2", down)
        self._band(m2, "LIGHT_usb_ribbon", loop, secs, "ribbon", 0.0, 0.5, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m2, loop, secs, "t2")
        self._band(m2, "LIGHT_usb_glass", loop, secs, "band", 0.0, 1.0, u_per_m=1 / 8.0)
        self._ledge(m2, "usb_concrete", loop, secs, "band_floor", up)
        m4 = self.mesh("usb_bowl_d")
        self._band(m4, "LIGHT_usb_concourse", loop, secs, "back3", 0.0, 1.0, u_per_m=1 / 8.0)
        for run in self._runs(secs, "up_soffit_slope"):
            lps = [loop[i] for i in run]
            ss = [secs[i]["up_soffit_slope"] for i in run]
            m4.grid("usb_concrete", [[self.at(lp, *a) for lp, (a, b) in zip(lps, ss)],
                                     [self.at(lp, *b) for lp, (a, b) in zip(lps, ss)]],
                    [[(lp.s / 8.0, 0.0) for lp in lps], [(lp.s / 8.0, 0.4) for lp in lps]], facing=down)
        self._band(m4, "LIGHT_usb_ribbon", loop, secs, "up_fascia", 0.5, 1.0, u_per_m=1 / (8 * p["tier"]["fascia_h"]))
        self._rows_runs(m4, loop, secs, "upper")
        for run in self._runs(secs, "upper", lambda sec: len(sec["upper"]) > p["portals"]["upper_row"] + 1):
            self._portals(m4, [loop[i] for i in run], [secs[i] for i in run], "upper", p["portals"]["upper_row"])
        # the rim: the top concourse's back wall, its walk and the dark wall up to the roof (enclosed building); at the
        # west end the concourse opens to the glass wall instead (``_concourse_west``)
        for run in self._runs(secs, "rim"):
            lps = [loop[i] for i in run]
            rims = [secs[i]["rim"] for i in run]
            keep = [not self.west_zone(lp) for lp in lps]
            if not any(keep):
                continue
            m4.grid("LIGHT_usb_concourse", [[self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)],
                                            [self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 1.0) for lp in lps], [(lp.s / 8, 0.0) for lp in lps]], facing=toward_field)
            m4.grid("usb_concrete", [[self.at(lp, r[0], r[2]) for lp, r in zip(lps, rims)],
                                     [self.at(lp, r[3], r[2]) for lp, r in zip(lps, rims)]],
                    [[(lp.s / 8, 0) for lp in lps], [(lp.s / 8, 0.4) for lp in lps]], facing=up)
            sub = []
            for (lp, r), k in list(zip(zip(lps, rims), keep)) + [((None, None), False)]:
                if lp is not None and k:
                    sub.append((lp, r))
                    continue
                if len(sub) >= 2:
                    # the top concourse's dark back, and over it the clerestory windows up to the roof (u003, u017,
                    # u019: a band of glass right under the roof all round), tiled every ``clerestory`` metres
                    tops = [self.roof_under(*self.at(q_, r_[3], 0.0)[::2]) - 0.3 for q_, r_ in sub]
                    mids = [min(r_[2] + p["rim"]["dark"], t) for (q_, r_), t in zip(sub, tops)]
                    m4.grid("usb_dark", [[self.at(q_, r_[3], r_[2]) for q_, r_ in sub],
                                         [self.at(q_, r_[3], y) for (q_, r_), y in zip(sub, mids)]],
                            [[(q_.s / 8, 1.0) for q_, _r in sub], [(q_.s / 8, 0.0) for q_, _r in sub]], facing=toward_field)
                    ch = p["facade"]["clerestory"]
                    m4.grid("LIGHT_usb_clerestory", [[self.at(q_, r_[3], y) for (q_, r_), y in zip(sub, mids)],
                                                     [self.at(q_, r_[3], y) for (q_, r_), y in zip(sub, tops)]],
                            [[(q_.s / 10.7, (t - y) / ch) for (q_, _r), y, t in zip(sub, mids, tops)],
                             [(q_.s / 10.7, 0.0) for q_, _r in sub]], facing=toward_field)
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
            m.quad("usb_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, n=n: -n)

    def _concourse_west(self, loop, secs):
        """The west end's main concourse: from the lower bowl's back to the glass wall at the street's level (the Legacy
        Gate opens onto it; u001 and u014 show the lower bowl alone under the glass), with a rail along its edge."""
        m = self.meshes.setdefault("usb_west", Mesh("usb_west"))
        run = [i for i, lp in enumerate(loop[:-1]) if self.west_zone(lp) and "rim" in secs[i]]
        if len(run) < 2:
            return
        lps = [loop[i] for i in run]
        rims = [secs[i]["rim"] for i in run]
        y = max(r[1] for r in rims)
        inner = [self.at(lp, r[0], r[1]) for lp, r in zip(lps, rims)]
        far = [self.at(lp, self.facade_depth(lp) - 0.5, y) for lp in lps]
        mid = [tuple(np.array(a) * 0.5 + np.array(b) * 0.5) for a, b in zip(inner, far)]
        m.grid("usb_concrete", [inner, mid, far], [[(lp.s / 8, 0.0) for lp in lps], [(lp.s / 8, 0.5) for lp in lps],
                                                  [(lp.s / 8, 1.0) for lp in lps]], facing=up)
        rail = [self.at(lp, r[0] + 0.2, r[1] + 1.1) for lp, r in zip(lps, rims)]
        m.grid("usb_black", [inner, rail], [[(lp.s / 4, 1.0) for lp in lps], [(lp.s / 4, 0.0) for lp in lps]],
               facing=toward_field)

    # -- the roof -------------------------------------------------------------------------------------------------
    def outline(self):
        """The OSM outline in this frame, counter-clockwise."""
        return sm._ccw(np.array(self.footprint()["facade"], float))

    def _ridge_polyline(self):
        q = self.p["roof"]
        tip = self.prow_tip()
        return [((q["ridge_x"], q["ridge_z_e"]), q["ridge_e"]), ((q["ridge_x"], q["ridge_z_w"]), q["ridge_w"]),
                ((tip[0], tip[1]), q["tip"])]

    def prow_tip(self):
        """The outline point farthest to the west (the prow's tip)."""
        P = self.outline()
        return tuple(P[int(np.argmin(P[:, 1]))])

    def roof_top(self, x, z):
        """The roof's top over (x, z): each side falls from the ridge (and from the prow's rising edge) at its own pitch."""
        q = self.p["roof"]
        best = None
        pl = self._ridge_polyline()
        for ((ax, az), ha), ((bx, bz), hb) in zip(pl[:-1], pl[1:]):
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
            px, pz = ax + dx * t, az + dz * t
            d = math.hypot(x - px, z - pz)
            h = ha + (hb - ha) * t
            if best is None or d < best[0]:
                best = (d, h, px)
        d, h, px = best
        if x < px and q.get("eave_s") is not None:
            # the ETFE side: a ruled slope from the ridge down to a level south gutter (u053, u054: the south eave runs
            # level while the ridge rises toward the prow), so the slope steepens toward the west
            pitch = (h - q["eave_s"]) / (q["ridge_x"] - q["eave_x"])
        elif x >= px and q.get("eave_n") is not None:
            # the opaque side the same way down to a level north gutter (u055: the dark plane falls from the ridge to
            # a level eave over short north walls)
            pitch = (h - q["eave_n"]) / (q["eave_xn"] - q["ridge_x"])
        else:
            pitch = q["pitch_s"] if x < px else q["pitch_n"]
        return h - pitch * d

    def roof_under(self, x, z):
        return self.roof_top(x, z) - self.p["roof"]["depth"]

    def _roof_stations(self):
        """(z, x_south, x_north) cross-sections of the outline every ``station`` metres and at every outline vertex."""
        q = self.p["roof"]
        P = self.outline()
        zs = set(np.round(P[:, 1], 3))
        z0, z1 = P[:, 1].min(), P[:, 1].max()
        for z in np.arange(math.ceil(z0 / q["station"]) * q["station"], z1, q["station"]):
            zs.add(round(float(z), 3))
        out = []
        for z in sorted(zs):
            z_ = min(max(z, z0 + 0.05), z1 - 0.05)
            xs = []
            for i in range(len(P)):
                a, b = P[i], P[(i + 1) % len(P)]
                if (a[1] - z_) * (b[1] - z_) <= 0 and a[1] != b[1]:
                    t = (z_ - a[1]) / (b[1] - a[1])
                    xs.append(a[0] + (b[0] - a[0]) * t)
            if len(xs) >= 2:
                out.append((z_, min(xs), max(xs)))
        return out

    def _roof(self):
        """The roof over the whole outline: its top (ETFE south of the ridge, the opaque membrane north of it) and its
        underside (the ETFE's bright panels on the white grid; the dark steel of the opaque roof), and the fascia at the
        edges. One grid of stations across the building, split at the ridge."""
        q = self.p["roof"]
        st = self._roof_stations()
        xr = q["ridge_x"]
        cols = 8
        rows_top, rows_under, uvs, split = [], [], [], []
        for z, xa, xb in st:
            xs = list(np.linspace(xa, xb, cols + 1))
            if xa < xr < xb:
                xs = sorted(set(xs) | {xr})
            # a fixed column count per row: resample the columns at even fractions, the ridge snapped to its nearest
            xs = list(np.linspace(xa, xb, cols + 1))
            if xa < xr < xb:
                k = int(np.argmin([abs(x - xr) for x in xs[1:-1]])) + 1
                xs[k] = xr
            rows_top.append([(x, self.roof_top(x, z), z) for x in xs])
            rows_under.append([(x, self.roof_under(x, z), z) for x in xs])
            uvs.append([(x / 12.0, z / 12.0) for x in xs])
        self.roof_rows = rows_under
        top_s = self.meshes.setdefault("usb_roof_top", Mesh("usb_roof_top"))
        und = self.meshes.setdefault("usb_roof_under", Mesh("usb_roof_under"))
        # one grid per side of the ridge (shared vertices): each row's columns up to the ridge, and from it
        for south in (True, False):
            rows_t, rows_u, rows_uv = [], [], []
            for rt, ru, uv in zip(rows_top, rows_under, uvs):
                cols_ = [c for c in range(len(rt)) if (rt[c][0] <= xr + 1e-6 if south else rt[c][0] >= xr - 1e-6)]
                if len(cols_) < 2:
                    if len(rows_t) >= 2:
                        self._roof_grid(top_s, und, rows_t, rows_u, rows_uv, south)
                    rows_t, rows_u, rows_uv = [], [], []
                    continue
                # a fixed column count per grid: resample this row's side at even fractions
                xs_side = [rt[c][0] for c in cols_]
                x0, x1 = min(xs_side), max(xs_side)
                z = rt[0][2]
                xs = list(np.linspace(x0, x1, 5))
                rows_t.append([(x, self.roof_top(x, z), z) for x in xs])
                rows_u.append([(x, self.roof_under(x, z), z) for x in xs])
                rows_uv.append([(x / 12.0, z / 12.0) for x in xs])
            if len(rows_t) >= 2:
                self._roof_grid(top_s, und, rows_t, rows_u, rows_uv, south)

    @staticmethod
    def _roof_grid(top_s, und, rows_t, rows_u, rows_uv, south):
        top_s.grid("usb_etfe_top" if south else "usb_zinc_top", rows_t, rows_uv, facing=up)
        und.grid("usb_etfe_under" if south else "usb_roof_under", rows_u, rows_uv, facing=down)

    def _truss(self):
        """The ridge truss (36 ft deep, 16 ft wide; Thornton Tomasetti) under the roof along the ridge: the dark wedge
        the 2023 end-zone photo shows over the north stands."""
        q = self.p["roof"]
        m = self.meshes.setdefault("usb_truss", Mesh("usb_truss"))
        xr = q["ridge_x"]
        zs = np.linspace(q["ridge_z_w"] + 4.0, q["ridge_z_e"] - 6.0, 16)
        top = [(xr, self.roof_under(xr, z), z) for z in zs]
        for side in (-1, 1):
            x = xr + side * q["truss_w"] / 2
            upper = [(x, y, z) for (_x, y, z) in top]
            lower = [(x, y - q["truss_depth"], z) for (_x, y, z) in top]
            m.grid("usb_truss", [lower, upper], [[(z / 9.0, 1.0) for z in zs], [(z / 9.0, 0.0) for z in zs]],
                   facing=lambda p_, s=side: np.array([s, 0.0, 0.0]))
        bottom_a = [(xr - q["truss_w"] / 2, y - q["truss_depth"], z) for (_x, y, z) in top]
        bottom_b = [(xr + q["truss_w"] / 2, y - q["truss_depth"], z) for (_x, y, z) in top]
        m.grid("usb_truss", [bottom_a, bottom_b], [[(z / 9.0, 0.004) for z in zs], [(z / 9.0, 0.02) for z in zs]], facing=down)

    def _lights(self):
        """Rows of floodlights under the roof over both upper decks' fronts (u014: a lit row along the north roof); each
        lamp's centre joins ``light_points``."""
        q = self.p["lights"]
        m = self.meshes.setdefault("usb_lights", Mesh("usb_lights"))
        for side in (-1, 1):
            x = side * q["x"]
            for z in np.arange(q["z"][0], q["z"][1] + 0.1, q["step"]):
                y = self.roof_under(x, z) - q["drop"]
                n = np.array([-side, 0.0, 0.0])
                ctr = np.array([x, y, z])
                along = np.array([0.0, 0.0, 1.0])
                normal = n * math.cos(math.radians(55)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(55))
                upv = np.cross(along, normal)
                upv = upv / np.linalg.norm(upv) * (1.0 if upv[1] > 0 else -1.0)
                hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
                m.quad("LIGHT_usb_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1),
                       (1, 0), (0, 0), facing=lambda p_, nn=normal: nn)
                self.light_points.append(tuple(ctr))
        for zside in (-1, 1):
            z = zside * 96.0
            for x in np.arange(-54.0, 54.1, q["step"]):
                y = self.roof_under(x, z) - q["drop"]
                n = np.array([0.0, 0.0, -zside])
                ctr = np.array([x, y, z])
                along = np.array([1.0, 0.0, 0.0])
                normal = n * math.cos(math.radians(55)) + np.array([0.0, -1.0, 0.0]) * math.sin(math.radians(55))
                upv = np.cross(along, normal)
                upv = upv / np.linalg.norm(upv) * (1.0 if upv[1] > 0 else -1.0)
                hw, hh = along * (q["w"] / 2), upv * (q["h"] / 2)
                m.quad("LIGHT_usb_lights", ctr - hw - hh, ctr + hw - hh, ctr + hw + hh, ctr - hw + hh, (0, 1), (1, 1),
                       (1, 0), (0, 0), facing=lambda p_, nn=normal: nn)
                self.light_points.append(tuple(ctr))

    def _roof_letters(self):
        """The venue's wordmark across the opaque north slope (u055, the 2016 to 2025 orthophotos: white lowercase letters
        about 140 m long, their baseline along the north side, read from the north), lying 0.3 m over the roof."""
        q = self.p["roof_letters"]
        m = self.meshes.setdefault("usb_roof_letters", Mesh("usb_roof_letters"))
        x0, x1 = q["x"]
        z0, z1 = q["z"]
        corners = [(x1, z0), (x1, z1), (x0, z1), (x0, z0)]       # baseline at the north (x1), read from east (z0) to west (z1)
        P = [(x, self.roof_top(x, z) + 0.3, z) for x, z in corners]
        m.quad("usb_roof_letters", P[0], P[1], P[2], P[3], (0, 1), (1, 1), (1, 0), (0, 0), facing=up)

    def _queen_trusses(self):
        """The roof's transverse trusses under the roof (u001, u014, u019: deep steel trusses across the building at even
        spacing; vikings.com: the ridge truss and 11 queen's post trusses), run along the roof's rafters (26.6 degrees in
        five orthophotos: about 9 degrees off square to the field)."""
        q = self.p["trusses"]
        m = self.meshes.setdefault("usb_trusses", Mesh("usb_trusses"))
        d = np.array(q["dir"], float); d /= np.linalg.norm(d)
        P = self.outline()
        for zc in np.linspace(q["z"][0], q["z"][1], q["count"]):
            # the truss's line through (x_r, zc) along d, clipped to the outline inset by 3 m
            xr = self.p["roof"]["ridge_x"]
            ts = []
            for i in range(len(P)):
                a, b = P[i], P[(i + 1) % len(P)]
                e = b - a
                den = d[0] * (-e[1]) - d[1] * (-e[0])
                if abs(den) < 1e-12:
                    continue
                w = a - np.array([xr, zc])
                t = (w[0] * (-e[1]) - w[1] * (-e[0])) / den
                u = (d[0] * w[1] - d[1] * w[0]) / den
                if 0 <= u <= 1:
                    ts.append(t)
            if len(ts) < 2:
                continue
            t0, t1 = min(ts) + 3.0, max(ts) - 3.0
            ts_ = np.linspace(t0, t1, 12)
            pts = [(xr + d[0] * t, zc + d[1] * t) for t in ts_]
            tops = [(x, self.roof_under(x, z) - 0.2, z) for x, z in pts]
            nrm = np.array([-d[1], 0.0, d[0]])
            for side in (-1, 1):
                off = nrm * side * q["w"] / 2
                upper = [tuple(np.array(p) + off) for p in tops]
                lower = [tuple(np.array(p) + off - np.array([0.0, q["depth"], 0.0])) for p in tops]
                m.grid("usb_truss", [lower, upper], [[(t / 7.0, 1.0) for t in ts_], [(t / 7.0, 0.0) for t in ts_]],
                       facing=lambda p_, s_=side, n_=nrm: n_ * s_)
            bot_a = [tuple(np.array(p) - nrm * q["w"] / 2 - np.array([0.0, q["depth"], 0.0])) for p in tops]
            bot_b = [tuple(np.array(p) + nrm * q["w"] / 2 - np.array([0.0, q["depth"], 0.0])) for p in tops]
            m.grid("usb_truss", [bot_a, bot_b], [[(t / 7.0, 0.004) for t in ts_], [(t / 7.0, 0.02) for t in ts_]], facing=down)

    def _flag(self):
        """The United States flag hanging vertically from the roof between the 3M panel and the banner, over the east
        upper deck's back (u003, u019: the stripes run down and the union is at the top left, seen from the field)."""
        q = self.p["flag"]
        m = self.meshes.setdefault("usb_flag", Mesh("usb_flag"))
        x, z = q["at"]
        top = self.roof_under(x, z) - 0.5
        w, h = q["size"]
        face = -np.array([x, 0.0, z]); face /= np.linalg.norm(face)
        right = np.cross(face, (0.0, 1.0, 0.0)); right /= -np.linalg.norm(right)
        c = np.array([x, top, z])
        A, B = c - right * w / 2, c + right * w / 2
        dn = np.array([0.0, h, 0.0])
        # the texture is the flag flying (the union at its top left): hung, the fly runs down and the hoist across
        uv = {"tl": (0, 0), "tr": (0, 1), "bl": (1, 0), "br": (1, 1)}
        m.quad("usb_flag", A - dn, B - dn, B, A, uv["bl"], uv["br"], uv["tr"], uv["tl"], facing=lambda p_, f=face: f)
        k = face * 0.05
        m.quad("usb_flag", B - dn - k, A - dn - k, A - k, B - k, uv["br"], uv["bl"], uv["tl"], uv["tr"],
               facing=lambda p_, f=face: -f)

    # -- the video boards --------------------------------------------------------------------------------------------
    FEED_U = ag.Allegiant.FEED_U
    FEED_V = ag.Allegiant.FEED_V
    board_crop = ag.Allegiant.board_crop

    def _board(self, m, c, face, W, H, wing, frames, header=True):
        """One board: the black housing, the live picture over its whole face (cropped at the board's own aspect, never
        stretched), a wing display either side (the game's digits go on them) and, on the west board, the usbankstadium
        header over it (the east board has none: u003, u019)."""
        q = self.p["boards"]
        right = np.cross(-face, (0.0, 1.0, 0.0)); right /= np.linalg.norm(right)
        hv = np.array([0.0, H, 0.0])
        ww, wh = wing
        total = W + 2 * ww + 1.0
        m.box("usb_black", c + hv / 2, (right, (0, 1, 0), face), (total / 2 + 0.6, H / 2 + 0.6, q["depth"] / 2), uvscale=0.1,
              bottom=True)
        fc = c + face * (q["depth"] / 2 + 0.05)
        (U0, U1), (V0, V1) = self.board_crop(W / H)
        A, B = fc - right * W / 2, fc + right * W / 2
        m.quad("jumbo_tron", A, B, B + hv, A + hv, (U0, V1), (U1, V1), (U1, V0), (U0, V0), facing=lambda p_, f=face: f)
        panels = []
        for s_ in (-1, 1):
            pc = fc + right * s_ * (W / 2 + 0.5 + ww / 2) + np.array([0.0, (H - wh) / 2, 0.0])
            ph = right * (ww / 2)
            pv = np.array([0.0, wh, 0.0])
            m.quad("LIGHT_usb_board_wing", pc - ph, pc + ph, pc + ph + pv, pc - ph + pv, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p_, f=face: f)
            panels.append(pc)
        if header:
            hw_, hh_ = W * q["header"][0] / 2, q["header"][1]
            hc = c + np.array([0.0, H + 0.9, 0.0])
            m.box("usb_black", hc + np.array([0.0, hh_ / 2, 0.0]), (right, (0, 1, 0), face), (hw_ + 0.6, hh_ / 2 + 0.3, 0.6),
                  uvscale=0.1)
            hf = hc + face * 0.65
            m.quad("usb_header", hf - right * hw_, hf + right * hw_, hf + right * hw_ + [0, hh_, 0],
                   hf - right * hw_ + [0, hh_, 0], (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)
        self.markers["jumbo"].append(tuple(fc + hv / 2))
        frames.append(dict(centre=c, right=right, face=face, width=W, height=H, panels=panels, wing=wing))

    def _boards(self):
        q = self.p["boards"]
        m = self.meshes.setdefault("usb_boards", Mesh("usb_boards"))
        self.markers["jumbo"] = []
        self.board_frames = []
        self._board(m, np.array([0.0, q["w_y"], q["w_z"]]), np.array([0.0, 0.0, 1.0]), q["w_w"], q["w_h"], q["w_wing"],
                    self.board_frames)
        self._board(m, np.array([0.0, q["e_y"], q["e_z"]]), np.array([0.0, 0.0, -1.0]), q["e_w"], q["e_h"], q["e_wing"],
                    self.board_frames, header=False)

    def _panel(self, m, mat, centre, face, w, h, v, tilt=0.0, hang_to=None, back=True):
        """A flat sign ``w`` x ``h`` facing ``face`` (horizontal), its bottom edge's middle at ``centre``, leaning back by
        ``tilt`` degrees, showing rows ``v`` of its texture; a black back and, with ``hang_to`` (a height), two straps
        up to the roof."""
        face = np.array(face, float); face /= np.linalg.norm(face)
        right = np.cross(face, (0.0, 1.0, 0.0)); right /= -np.linalg.norm(right)   # a viewer facing it has this on the right
        up = np.array([0.0, math.cos(math.radians(tilt)), 0.0]) - face * math.sin(math.radians(tilt))
        c = np.array(centre, float)
        A, B = c - right * w / 2, c + right * w / 2
        v0, v1 = v
        m.quad(mat, A, B, B + up * h, A + up * h, (0, v1), (1, v1), (1, v0), (0, v0), facing=lambda p_, f=face: f)
        back_off = -face * 0.25
        if back:
            m.quad("usb_black", B + back_off, A + back_off, A + back_off + up * h, B + back_off + up * h, (0, 1), (1, 1),
                   (1, 0), (0, 0), facing=lambda p_, f=face: -f)
        if hang_to is not None:
            for s_ in (-0.35, 0.35):
                p0 = c + right * (w * s_) + up * h + back_off / 2
                top = np.array([p0[0], hang_to, p0[2]])
                m.box("usb_black", (p0 + top) / 2, (right, (0, 1, 0), face), (0.2, (hang_to - p0[1]) / 2, 0.2), uvscale=0.1)

    def rim_back(self, x, east=True):
        """(z, height) of the top concourse's back wall at plan ``x`` over the east (or west) half of the bowl."""
        pts = []
        for lp, sec in zip(self.loop, self.secs):
            if "rim" not in sec or (lp.z > 0) != east or self.west_zone(lp):
                continue
            b = self.at(lp, sec["rim"][3], sec["rim"][2])
            pts.append((b[0], b[2], b[1]))
        pts.sort()
        xs = [p_[0] for p_ in pts]
        return float(np.interp(x, xs, [p_[1] for p_ in pts])), float(np.interp(x, xs, [p_[2] for p_ in pts]))

    def _east_wall(self):
        """The east end over the east upper deck (u003, u019): the usbankstadium banner (the two-line lockup on blue,
        leaning back) over the deck's middle and the 3M panel to its north along the top concourse's back, both under
        the roof; the Land O'Lakes panel at the north-west, over the north stands' west end (u014, u017, u044: its south
        end triangulated from two solved photos, 2.5 m apart)."""
        q = self.p["east"]
        m = self.meshes.setdefault("usb_east", Mesh("usb_east"))
        w, h, y, z, tilt = q["banner"]
        self._panel(m, "LIGHT_usb_blue_sign", (0.0, y, z), (0.0, 0.0, -1.0), w, h, (0.0, 1.0), tilt=tilt)
        x0, x1, h, y, off = q["panel_3m"]
        (z0, _y0), (z1, _y1) = self.rim_back(x0), self.rim_back(x1)
        a, b = np.array([x0, z0]), np.array([x1, z1])
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        n = n if n[1] < 0 else -n                               # toward the field (west)
        c = (a + b) / 2 + n * off
        self._panel(m, "LIGHT_usb_panels", (c[0], y, c[1]), (n[0], 0.0, n[1]), float(np.linalg.norm(b - a)), h, (0.0, 0.5))
        x0, z0, x1, z1, h, y = q["panel_lol"]
        a, b = np.array([x0, z0]), np.array([x1, z1])
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        n = n if float(n @ -((a + b) / 2)) > 0 else -n            # toward the field
        c = (a + b) / 2
        self._panel(m, "LIGHT_usb_panels", (c[0], y, c[1]), (n[0], 0.0, n[1]), float(np.linalg.norm(b - a)), h, (0.5, 1.0),
                    hang_to=self.roof_under(float(c[0]), float(c[1])) - 0.2)

    def _signs(self, loop, secs):
        """The club's plain-type bands: SKOL VIKINGS and MINNESOTA VIKINGS on the north side's top fascia (DESIGN, after
        the 2023 and 2026 photos), HOME OF THE MINNESOTA VIKINGS on the south side's suite fascia toward the east (u017),
        and the white wordmark on the north suites' fascia (u094)."""
        m = self.meshes.setdefault("usb_signs", Mesh("usb_signs"))
        for side, sgn in (("N", 1.0), ("S", -1.0)):
            pts = [(lp, sec) for lp, sec in zip(loop, secs) if lp.w[side] > 0.99 and "rim" in sec]
            if len(pts) < 2:
                continue
            lp0 = min(pts, key=lambda t_: abs(t_[0].z))[0]
            sec0 = self.section(lp0)
            face = np.array([-sgn, 0.0, 0.0])
            if side == "N":
                r = sec0["rim"]
                y = r[2] + 0.4
                x = lp0.x + sgn * (r[0] - 0.1)
                for z0, band in ((-48.0, 1), (-8.0, 2), (32.0, 3)):
                    w = 34.0
                    h = w / 8.0
                    v0, v1 = band / 4.0, (band + 1) / 4.0
                    # seen from the field (looking north, +z on the right), the band's left end is its -z end
                    m.quad("LIGHT_usb_signs", (x, y, z0 - w / 2), (x, y, z0 + w / 2), (x, y + h, z0 + w / 2),
                           (x, y + h, z0 - w / 2), (0, v1), (1, v1), (1, v0), (0, v0), facing=lambda p_, f=face: f)
                if "band" in sec0:
                    d, a, b = sec0["band"]
                    x = lp0.x + d - 0.1
                    h = min(30.0 / 4.0, b - a)
                    w = h * 4.0
                    yb = a + (b - a - h) / 2
                    m.quad("usb_letters", (x, yb, -w / 2), (x, yb, w / 2), (x, yb + h, w / 2), (x, yb + h, -w / 2),
                           (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, f=face: f)
            elif "band" in sec0:
                d, a, b = sec0["band"]
                x = lp0.x - d + 0.1
                h = min(4.0, b - a)
                w = h * 8.0
                yb = a + (b - a - h) / 2
                z0 = 40.0
                # seen from the field (looking south, -z on the right), the band's left end is its +z end
                m.quad("LIGHT_usb_signs", (x, yb, z0 + w / 2), (x, yb, z0 - w / 2), (x, yb + h, z0 - w / 2),
                       (x, yb + h, z0 + w / 2), (0, 0.25), (1, 0.25), (1, 0.0), (0, 0.0), facing=lambda p_, f=face: f)

    # -- the facade --------------------------------------------------------------------------------------------------
    def _edges(self):
        """[(a, b, outward normal, west)] of the outline's edges; ``west`` marks the Legacy Gate's glass faces: facing west
        (-z) and south of the prow's base (u047: the prow's faces and the north-west face are dark panels)."""
        P = self.outline()
        out = []
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            e = b - a
            L = float(np.hypot(*e))
            if L < 0.05:
                continue
            n = np.array([e[1], -e[0]]) / L          # counter-clockwise ring: the right-hand normal points outward
            west = n[1] < -self.p["glass"]["face_nz"] and max(a[0], b[0]) <= self.p["glass"]["north_x"]
            out.append((a, b, n, west))
        return out

    def _prow_edges(self):
        """The prow's faces (u036, u047): ``blade``, the edge that ends at the tip (the dark blade facing the plaza), and
        ``nw``, the edges that leave the tip in one direction (its north-west face)."""
        tip = np.array(self.prow_tip())
        edges = self._edges()
        blade, nw = None, []
        for i, (a, b, n, _w) in enumerate(edges):
            if np.allclose(b, tip):
                blade = i
            if np.allclose(a, tip):
                k = i
                while k < len(edges) and float(np.dot(edges[k][2], edges[i][2])) > math.cos(math.radians(5.0)):
                    nw.append(k)
                    k += 1
        return blade, nw

    def blade_edge(self, s):
        """The blade's lower edge ``s`` metres from the glass wall's north end: the blade is the triangle between the
        tip, the glass wall's top and the glass wall's foot (u047), so this line runs from the foot up to the tip."""
        blade, _nw = self._prow_edges()
        a, b, _n, _w = self._edges()[blade]
        L = float(np.linalg.norm(b - a))
        top = self.roof_top(*self.prow_tip())
        return self.GRADE + (top - self.GRADE) * min(max(s / L, 0.0), 1.0)

    def _facade(self):
        """The outline's walls from below the plaza to the roof's edge: the west faces glass (reflective outside, see-through
        inside); the prow's blade dark over the glass under its lower edge, and its north-west face glass under a dark
        band (u036, u047); the others dark zinc-coloured panels over a glass base (u036, u053 to u055). Inside, under the
        roof, a band of clerestory windows (u003, u017, u019) over the dark inner face."""
        q = self.p["facade"]
        m = self.meshes.setdefault("usb_facade", Mesh("usb_facade"))
        g = self.meshes.setdefault("usb_glass", Mesh("usb_glass"))
        edges = self._edges()
        blade, nw = self._prow_edges()
        tip_top = self.roof_top(*self.prow_tip())
        nw_len = sum(float(np.hypot(*(edges[k][1] - edges[k][0]))) for k in nw)
        nw_run = 0.0
        s = 0.0
        for i, (a, b, n, west) in enumerate(edges):
            L = float(np.hypot(*(b - a)))
            k = max(1, int(math.ceil(L / 12.0)))
            ts = np.linspace(0, 1, k + 1)
            pts = [a + (b - a) * t for t in ts]
            tops = [self.roof_top(float(p[0]), float(p[1])) for p in pts]
            outward = lambda p_, n=n: np.array([n[0], 0.0, n[1]])  # noqa: E731
            inward = lambda p_, n=n: -np.array([n[0], 0.0, n[1]])  # noqa: E731
            us = [s + L * t / 16.0 for t in ts]
            bot = [(float(p[0]), self.GRADE - 0.5, float(p[1])) for p in pts]
            top = [(float(p[0]), y, float(p[1])) for p, y in zip(pts, tops)]
            if west:
                split = tops
            elif i == blade:
                split = [self.blade_edge(L * t) for t in ts]
            elif i in nw:
                low = self.GRADE + q["nw_low"]
                split = [tip_top - q["nw_band"] - (tip_top - q["nw_band"] - low) * (nw_run + L * t) / nw_len for t in ts]
                split[0] = min(split[0], tops[0])
                nw_run += L
            else:
                split = [self.GRADE + q["base"]] * len(pts)
            split = [min(y, yt) for y, yt in zip(split, tops)]
            mid = [(float(p[0]), y, float(p[1])) for p, y in zip(pts, split)]
            g.grid("LIGHT_usb_facade_glass", [bot, mid], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
            if west or i == blade or i in nw:
                inset = [(x - n[0] * 0.3, y, z - n[1] * 0.3) for x, y, z in bot]
                inset_t = [(x - n[0] * 0.3, y, z - n[1] * 0.3) for x, y, z in mid]
                g.grid("LIGHT_usb_glasswall", [inset, inset_t], [[(u * 2, 1.0) for u in us],
                                                                 [(u * 2, (y - self.GRADE) / 18.0) for u, y in zip(us, split)]],
                       facing=inward)
            if west:
                s += L
                continue
            m.grid("usb_zinc", [mid, top], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=outward)
            # inside: the dark inner face, and the clerestory windows under the roof
            inner = lambda Q, n=n: [(x - n[0] * 0.4, y, z - n[1] * 0.4) for x, y, z in Q]  # noqa: E731
            cl = [(x, max(ys, yt - q["clerestory"]), z) for (x, ys, z), yt in zip(mid, tops)]
            m.grid("usb_dark", [inner(mid), inner(cl)], [[(u, 1.0) for u in us], [(u, 0.0) for u in us]], facing=inward)
            m.grid("LIGHT_usb_clerestory", [inner(cl), inner(top)],
                   [[(u * 1.5, 1.0) for u in us], [(u * 1.5, 0.0) for u in us]], facing=inward)
            s += L

    def _prow(self):
        """The blade's wordmark and the 49 x 76 ft display under it, each centred in the blade's width at its own height
        (u036, u047: the two-line wordmark high on the blade, the display below it), facing the plaza."""
        q = self.p["prow"]
        blade, _nw = self._prow_edges()
        if blade is None:
            return
        a, b, n, _w = self._edges()[blade]
        L = float(np.linalg.norm(b - a))
        d = np.array([(b - a)[0], 0.0, (b - a)[1]]) / L        # from the glass wall's north end toward the tip
        m = self.meshes.setdefault("usb_prow", Mesh("usb_prow"))
        out = np.array([n[0], 0.0, n[1]]) * 0.35
        top_t = self.roof_top(*self.prow_tip())
        width_at = lambda y: L * (y - self.GRADE) / (top_t - self.GRADE)  # noqa: E731  (the blade's width at height y)
        lw, lh = q["letters"]
        dw, dh = q["display"]
        ly = self.GRADE + (top_t - self.GRADE) * (lw + 2.0) / L
        dy = ly - q["gap"] - dh
        self.prow_boxes = []
        for mat, w, h, y in (("usb_prow_letters", lw, lh, ly), ("LIGHT_usb_prow_display", dw, dh, dy)):
            sc = width_at(y) / 2.0
            c = np.array([a[0], 0.0, a[1]]) + d * sc + out
            left, right = c + d * (w / 2), c - d * (w / 2)       # a viewer facing the blade has the tip on the left
            m.quad(mat, left + [0, y, 0], right + [0, y, 0], right + [0, y + h, 0], left + [0, y + h, 0],
                   (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p_, nn=n: np.array([nn[0], 0.0, nn[1]]))
            self.prow_boxes.append((mat, sc - w / 2, sc + w / 2, y, y + h))

    # -- outside -----------------------------------------------------------------------------------------------------
    _extrude = sm.SoFi._extrude

    def _exterior(self):
        """The plaza round the building, then the shared environment kit (nfl2k5_stadium_environment: the lots with their
        cars, the roads, parks, water, trees and blocks from OpenStreetMap, the far ground to the haze and the horizon
        band), then downtown's towers (this model's own boxes: the kit leaves every building of TOWER_MIN_H and more, and
        the towers' own ways, to them)."""
        P = self.outline()
        ring = list(P) + [P[0]]
        cx, cz = np.mean(P, axis=0)
        m = self.meshes.setdefault("usb_plaza", Mesh("usb_plaza"))

        def grow(k):
            out = []
            for x, z in ring:
                v = np.array([x - cx, z - cz]); v /= np.linalg.norm(v)
                out.append((x + v[0] * k, self.GRADE, z + v[1] * k))
            return out
        rings = [grow(0.0), grow(14.0), grow(40.0)]
        uv = lambda Q: [(x / 20.0, z / 20.0) for x, _y, z in Q]  # noqa: E731
        m.grid("usb_plaza", rings, [uv(r) for r in rings], facing=up)
        plaza = [(x, z) for x, _y, z in rings[-1][:-1]]
        towers = {t.get("way") for t in self.footprint().get("towers", []) if float(t["height"]) >= self.TOWER_MIN_H}
        self.env_counts = env.dress(self, self.venue, grade=self.GRADE, keep_out=[plaza], inner=plaza,
                                    exclude_ways=towers, block_max_height=self.TOWER_MIN_H, eyes=self.camera_eyes())
        tw = self.meshes.setdefault("usb_towers", Mesh("usb_towers"))
        for t in self.tower_boxes():
            self._extrude(tw, t["rect"], self.GRADE + t["h0"], self.GRADE + t["h1"], "LIGHT_usb_towers", "usb_concrete", uscale=1 / 30.0)

    def camera_eyes(self):
        """The intro cameras' eye points (every second of each shot), which the environment kit keeps clear."""
        return shot_eyes(usbank_shots())

    def tower_boxes(self):
        """Downtown's towers as boxes: each outline's minimum rectangle, shrunk about its centre to at most TOWER_AREA
        square metres (a height-tagged way can be a whole block with its podium; the shafts the photos show are narrower,
        u014 and u001); a tower inside a taller one's box is dropped (OSM draws parts and their building)."""
        out = []
        for t in sorted(self.footprint().get("towers", []), key=lambda t: -float(t["height"])):
            Q = np.array(t["points"], float)
            if len(Q) < 3:
                continue
            R = np.array(ag._min_rect(Q), float)
            c = R.mean(axis=0)
            area = float(np.linalg.norm(R[1] - R[0]) * np.linalg.norm(R[2] - R[1]))
            if area > self.TOWER_AREA:
                R = c + (R - c) * math.sqrt(self.TOWER_AREA / area)
            if float(t["height"]) < self.TOWER_MIN_H or any(sm._point_in_poly(c[0], c[1], [tuple(p) for p in o["rect"]]) for o in out):
                continue
            out.append(dict(rect=[tuple(p) for p in R], h0=float(t.get("min_height") or 0.0), h1=float(t["height"]),
                            name=t.get("name")))
        return out

    def _sky(self):
        """The sky backdrop: a cylinder round the site and a cap over it (the retail s15 bundles carry no sky texture;
        the ETFE and the west glass show the sky)."""
        q = self.p["sky"]
        m = self.meshes.setdefault("usb_sky", Mesh("usb_sky"))
        N = q["points"]
        bot, top, uvb, uvt = [], [], [], []
        for k in range(N + 1):
            a = 2 * math.pi * (k % N) / N
            x, z = q["radius"] * math.cos(a), q["radius"] * math.sin(a)
            bot.append((x, self.GRADE - 20.0, z))
            top.append((x, q["height"], z))
            uvb.append((k / 8.0, 0.999))
            uvt.append((k / 8.0, 0.02))
        m.grid("usb_sky", [bot, top], [uvb, uvt], facing=lambda p_: -np.array([p_[0], 0.0, p_[2]]))
        cap = [(q["radius"] * math.cos(2 * math.pi * k / N), q["height"], q["radius"] * math.sin(2 * math.pi * k / N))
               for k in range(N + 1)]
        centre = [(0.0, q["height"] * 1.3, 0.0)] * (N + 1)
        m.grid("usb_sky", [cap, centre], [[(k / 8.0, 0.02) for k in range(N + 1)], [(k / 8.0, 0.0) for k in range(N + 1)]],
               facing=down)


def build(venue=VENUE, params=None):
    return USBank(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class
MATERIALS = {
    "usb_seat_front": ("usb_seat_front", CLASS_OPAQUE), "usb_seat_mid": ("usb_seat_mid", CLASS_OPAQUE),
    "usb_seat_back": ("usb_seat_back", CLASS_OPAQUE), "usb_concrete": ("usb_concrete", CLASS_OPAQUE),
    "usb_wall": ("usb_wall", CLASS_OPAQUE), "LIGHT_usb_ribbon": ("LIGHT_usb_ribbon", CLASS_OPAQUE),
    "LIGHT_usb_glass": ("LIGHT_usb_glass", CLASS_OPAQUE), "LIGHT_usb_concourse": ("LIGHT_usb_concourse", CLASS_OPAQUE),
    "usb_portal": ("usb_portal", CLASS_OPAQUE), "usb_dark": ("usb_dark", CLASS_OPAQUE), "usb_black": ("usb_black", CLASS_OPAQUE),
    "usb_etfe_under": ("usb_etfe_under", CLASS_OPAQUE), "usb_roof_under": ("usb_roof_under", CLASS_OPAQUE),
    "usb_truss": ("usb_truss", CLASS_ALPHA), "usb_etfe_top": ("usb_etfe_top", CLASS_OPAQUE),
    "usb_zinc_top": ("usb_zinc_top", CLASS_OPAQUE), "LIGHT_usb_lights": ("LIGHT_usb_lights", CLASS_OPAQUE),
    "LIGHT_usb_glasswall": ("LIGHT_usb_glasswall", CLASS_ALPHA), "usb_zinc": ("usb_zinc", CLASS_OPAQUE),
    "LIGHT_usb_facade_glass": ("LIGHT_usb_facade_glass", CLASS_OPAQUE),
    "LIGHT_usb_prow_display": ("LIGHT_usb_prow_display", CLASS_OPAQUE),
    "LIGHT_usb_board_wing": ("LIGHT_usb_board_wing", CLASS_OPAQUE), "usb_header": ("usb_header", CLASS_OPAQUE),
    "usb_letters": ("usb_letters", CLASS_ALPHA), "usb_prow_letters": ("usb_prow_letters", CLASS_ALPHA),
    "LIGHT_usb_signs": ("LIGHT_usb_signs", CLASS_OPAQUE), "usb_roof_letters": ("usb_letters", CLASS_ALPHA),
    "usb_flag": ("usb_flag", CLASS_OPAQUE), "LIGHT_usb_blue_sign": ("LIGHT_usb_blue_sign", CLASS_OPAQUE),
    "LIGHT_usb_panels": ("LIGHT_usb_panels", CLASS_OPAQUE), "LIGHT_usb_clerestory": ("LIGHT_usb_clerestory", CLASS_OPAQUE),
    "usb_plaza": ("usb_plaza", CLASS_OPAQUE), "usb_lawn": ("usb_lawn", CLASS_OPAQUE), "usb_asphalt": ("usb_asphalt", CLASS_OPAQUE),
    "usb_road": ("usb_road", CLASS_OPAQUE), "usb_building": ("usb_building", CLASS_OPAQUE),
    "LIGHT_usb_towers": ("LIGHT_usb_towers", CLASS_OPAQUE), "usb_sky": ("usb_sky", CLASS_OPAQUE),
    **env.materials(VENUE),
}

#: baked vertex light (grey level) per material: day, afternoon, night
BASE = {
    "usb_seat_front": (214, 208, 200), "usb_seat_mid": (214, 208, 200), "usb_seat_back": (214, 208, 200),
    "crowd": (222, 216, 210), "usb_concrete": (206, 200, 192), "usb_wall": (232, 226, 222),
    "LIGHT_usb_ribbon": (255, 255, 255), "LIGHT_usb_glass": (190, 186, 255), "LIGHT_usb_concourse": (214, 208, 255),
    "usb_portal": (160, 156, 150), "usb_dark": (190, 186, 180), "usb_black": (200, 196, 190),
    "usb_etfe_under": (244, 236, 160), "usb_roof_under": (210, 204, 170), "usb_truss": (210, 204, 180),
    "usb_etfe_top": (196, 180, 104), "usb_zinc_top": (176, 162, 92), "LIGHT_usb_lights": (255, 255, 255),
    "usb_roof_letters": (236, 220, 120), "usb_flag": (220, 214, 200), "LIGHT_usb_blue_sign": (255, 255, 255),
    "LIGHT_usb_panels": (240, 236, 255), "LIGHT_usb_clerestory": (236, 230, 255),
    "LIGHT_usb_glasswall": (244, 234, 255), "usb_zinc": (214, 200, 150), "LIGHT_usb_facade_glass": (228, 212, 255),
    "LIGHT_usb_prow_display": (255, 255, 255), "LIGHT_usb_board_wing": (255, 255, 255), "jumbo_tron": (255, 255, 255),
    "usb_header": (255, 255, 255), "usb_letters": (255, 255, 255), "usb_prow_letters": (255, 255, 255),
    "LIGHT_usb_signs": (255, 255, 255),
    "usb_plaza": (226, 206, 120), "usb_lawn": (224, 204, 80), "usb_asphalt": (220, 200, 90), "usb_road": (220, 200, 90),
    "usb_building": (220, 200, 110), "LIGHT_usb_towers": (214, 200, 255), "usb_sky": (255, 255, 255),
}
#: the sun over Minneapolis (DESIGN): by day high in the south (bearing 180: game angle -36 degrees from +x toward -z... the
#: plan vector (sin 180, cos 180) = (0, -1) in east/north is x = -0.81, z = +0.59 in this frame), in the afternoon low in
#: the south-west (bearing 240: x = -0.99, z = -0.14)
SUN = {"d": (-0.46, 0.80, 0.34), "a": (-0.84, 0.52, -0.12), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.95, 0.88), "n": (0.97, 0.99, 1.03)}
OUTSIDE = {"usb_etfe_top", "usb_zinc_top", "usb_roof_letters", "usb_zinc", "LIGHT_usb_facade_glass", "usb_plaza", "usb_lawn", "usb_asphalt",
           "usb_road", "usb_building", "LIGHT_usb_towers", "usb_prow_letters", "LIGHT_usb_prow_display", "usb_sky"}
#: inside, the light is the stadium's own by day through the ETFE and the glass, one level for every surface (the rain
#: and snow bundles look the same: main, 2026-09-27, no weather shown through the roof)
INSIDE_LIGHT = 0.96


def light(mat, P, N, tod, weather, outside=False):
    if mat.startswith("env_"):
        return env.light(mat, P, N, tod, weather, VENUE)
    base = BASE.get(mat, (200, 190, 150))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat == "usb_sky":
        out = np.full((n, 4), 255, np.uint8)
        return out
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
    if mat == "usb_concrete":
        f = np.where(N[:, 1] < -0.5, f * 0.6, f)
    tint = TINT[tod] if outside else (1.0, 1.0, 1.0)
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    if mat == "usb_etfe_under" and tod == "n":
        # the ETFE at night: the dark sky through it, the white steel grid lit from below (DESIGN)
        out[:, 0] = 96; out[:, 1] = 98; out[:, 2] = 108
    if mat in ("usb_zinc", "usb_etfe_top", "usb_zinc_top") and tod == "n":
        out[:, 0] = 58; out[:, 1] = 60; out[:, 2] = 68
    return out


def _rgba(path):
    path = official.resolve_path(path)
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


#: textures with their own night drawing (downtown's towers: dark, lit windows; the clerestory: the night sky; the
#: glass wall: dark and nearly clear, so the full-bright night light leaves no white veil over the view, u044)
NIGHT_TEXTURES = ("LIGHT_usb_towers", "LIGHT_usb_clerestory", "LIGHT_usb_glasswall")


def _textures(venue, tod, weather):
    art = ART_DIR
    out = {}
    for key in dict.fromkeys(k for k, _c in MATERIALS.values()):   # MATERIALS order: deterministic across processes
        if key.startswith("env_"):
            continue
        name = f"usb_sky_{tod}" if key == "usb_sky" else f"{key}_n" if key in NIGHT_TEXTURES and tod == "n" else key
        out[key] = _rgba(art / f"{name}.png")
    out.update(env.textures(venue, tod, weather))
    return out


#: the game's digits on the west board's two wings (slot spacing, half width, half height, metres) and their height on
#: the wing (a fraction of the wing's height)
DIGIT_SLOT, DIGIT_HW, DIGIT_HH, DIGIT_Y = 0.78, 0.34, 0.62, 0.72


def adjust_digits(shape, sc, model):
    """The score and clock digits onto the west board's two wings (the game's own digits: one strip per wing, in the
    wing's dark window); the play clocks onto the end walls."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    b = model.board_frames[0]
    wh = b["wing"][1]
    strips = [dict(centre=pc + b["face"] * 0.12 + np.array([0.0, wh * DIGIT_Y, 0.0]), right=b["right"])
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
                wall_z = model.p["loop"]["ze"] if zs > 0 else model.p["loop"]["zw"]
                centre = np.array([side * 0.9 * zs, 2.7, zs * (wall_z - 0.08)])
                sm._place_quad(P, UV, quad, centre, np.array([-zs, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 0.75, 1.1)
            else:
                s_ = strips[n % 2]
                slot = sm.DIGIT_SLOTS.get(mname, 5)
                # a wing is narrow: the strip's eleven slots fold into two rows (score over clock)
                row, col = (0, slot) if slot < 5 else (1, slot - 6)
                centre = s_["centre"] + s_["right"] * ((col - 2) * DIGIT_SLOT) - np.array([0.0, row * 1.6, 0.0])
                sm._place_quad(P, UV, quad, centre, s_["right"], np.array([0.0, 1.0, 0.0]), DIGIT_HW, DIGIT_HH)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def flare_points(model):
    """The four flare markers over the floodlights' diagonals, u6's FLARE_HEIGHT (300 m) up (u6's lab 5, PROVED IN GAME at
    SoFi: no flare discs in the flyover, short night shadows under the feet)."""
    out = []
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        best = min(model.light_points, key=lambda p: abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        out.append((best[0], sm.FLARE_HEIGHT, best[2]))
    return out


LEAGUE_BANNER = ag.LEAGUE_BANNER
dry_of = ag.dry_of
league_banner = ag.league_banner


def build_scene(retail_bundle, filename, model, dry_bundle=None):
    """The U.S. Bank stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "usb_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "usb_digits", tmpl_shape)
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
    """(bundle bytes, info): the retail bundle with its stadium scene replaced by the U.S. Bank model and its intro
    cameras rewritten when ``cameras`` gives the shots. s15 has no cityscape: the stretch from the stadium chunk to the
    end of the cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model, dry_bundle=dry_bundle)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    scenes = ml.bundle_scenes(retail_bundle)
    st = scenes["stadium"]
    sb.require("cityscape" not in scenes, "s15 carries no cityscape chunk")
    cam_chunk, cam_dec = mm._cameras_chunk(retail_bundle)
    sb.require(cam_chunk.offset == st.offset + 32 + st.stored_size, "intro cameras do not follow the stadium chunk")
    start = st.offset
    end = cam_chunk.offset + 32 + cam_chunk.stored_size
    cam_span = sm._chunk_span(retail_bundle, cam_chunk)
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


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s15 intro camera's channel carries (PROVED OFFLINE from the nine retail intro_cameras
#: scenes): camera 1 x, y, z, pitch and yaw (multi-segment curves: held still); camera 2 y and pitch only (it plays at
#: midfield looking west, -z; both animate); cameras 3 and 4 all five (3 yaws, 4 yaws and moves along z); camera 5 x,
#: y, z and yaw (no pitch: level; multi-segment: held still). A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"y", "pitch"}, {"x", "y", "z", "pitch", "yaw"},
                             {"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "yaw"})

#: DESIGN, pass 1: the U.S. Bank flyover, one shot per retail camera.
#: 1: outside over Medtronic Plaza, the prow and the Legacy Gate's glass (still);
#: 2 (midfield, looking west): a crane rising toward the west board, the glass wall and downtown beyond it;
#: 3: from the north upper deck, panning across the bowl under the ETFE to the west glass;
#: 4: a dolly along the south club level, looking at the north stands under the dark roof;
#: 5 (level): outside from the south-east, pushing in over the blocks (a sight line clear of every town box, pass 3):
#: the pale ETFE beside the dark opaque plane and the prow beyond them (u054).
_PLAZA = dict(eye=(-70.0, 58.0, -330.0), target=(10.0, 62.0, -140.0), fov=42.0, rates=dict())
_CRANE = dict(eye=(0.0, 6.0, 0.0), target=(0.0, 34.0, -118.0), fov=46.0, rates=dict(y=2.2, pitch=0.6))
_PAN = dict(eye=(78.0, 50.0, 30.0), target=(-20.0, 40.0, -110.0), fov=44.0, rates=dict(yaw=2.0))
_DOLLY = dict(eye=(-66.0, 28.0, 45.0), target=(40.0, 34.0, 0.0), fov=44.0, rates=dict(z=-4.0, yaw=-0.8))
_SOUTHEAST = dict(eye=(-160.0, 75.0, 277.0), target=(0.0, 75.0, 0.0), fov=40.0, rates=dict(x=3.0, z=-4.0))
USB_SHOTS = [_PLAZA, _CRANE, _PAN, _DOLLY, _SOUTHEAST]


def write_cameras(decoded, shots):
    """u6's same-layout camera writer (``sm.write_cameras``) for s15, whose camera 1 animates its field of view (PROVED
    OFFLINE: a multi-segment channel on +0x50 in all nine retail scenes): every field-of-view segment holds the shot's
    field of view (rate 0), as the other multi-segment components hold their start value."""
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
                    if "const" in comp:
                        struct.pack_into("<f", out, comp["const"], float(shot["fov"]))
                        continue
                    for seg in range(comp["count"]):
                        struct.pack_into("<4f", out, comp["segs"] + 16 * seg, 0.0, 0.0, 0.0, float(shot["fov"]))
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


#: The feed screens show the game's own frame (640 x 448), so a flyover shot whose view the screens fill feeds back on
#: itself and saturates to white (st, PROVED IN GAME at AT&T Stadium, 2026-09-27). A shot keeps every feed screen under
#: FEED_COVERAGE_LIMIT of the frame at every moment of its 8 s path (occlusion ignored: the bound is conservative).
FEED_ASPECT = 640.0 / 448.0
FEED_COVERAGE_LIMIT = 0.25


def _clip_poly(poly, keep):
    """Sutherland-Hodgman against one half-space: ``keep(p)`` gives the signed distance (inside when >= 0)."""
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        da, db = keep(a), keep(b)
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            t_ = da / (da - db)
            out.append(tuple(pa + (pb - pa) * t_ for pa, pb in zip(a, b)))
    return out


def feed_coverage(model, shot, *, seconds=8.0, step=0.25, aspect=FEED_ASPECT):
    """The largest share of the frame the model's feed screens (the ``jumbo_tron`` quads) cover over the shot's path:
    [(t, share)] and the maximum. The shot's ``fov`` is the vertical field of view; rates are per second."""
    quads = [[np.array(mesh.P[i], float) for i in strip] for mesh in model.meshes.values()
             for strip in mesh.groups.get("jumbo_tron", ())]
    r = shot.get("rates", {})
    vf = math.radians(shot["fov"])
    th, tv = math.tan(vf / 2) * aspect, math.tan(vf / 2)
    worst, trace = 0.0, []
    for t_ in np.arange(0.0, seconds + 1e-9, step):
        eye = np.array(shot["eye"], float) + np.array([r.get("x", 0.0), r.get("y", 0.0), r.get("z", 0.0)]) * t_
        yaw = math.radians(shot["yaw"] + r.get("yaw", 0.0) * t_)
        pitch = math.radians(shot["pitch"] + r.get("pitch", 0.0) * t_)
        f = np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
        right = np.cross(f, (0.0, 1.0, 0.0))
        right /= np.linalg.norm(right)
        upv = np.cross(right, f)
        share = 0.0
        for q in quads:
            cam = [((p - eye) @ right, (p - eye) @ upv, (p - eye) @ f) for p in q]
            cam = [cam[0], cam[1], cam[3], cam[2]] if len(cam) == 4 else cam     # strip order to a ring
            poly = _clip_poly(cam, lambda c: c[2] - 0.3)
            if len(poly) < 3:
                continue
            pts = [(c[0] / (c[2] * th), c[1] / (c[2] * tv)) for c in poly]
            for keep in (lambda s: 1 - s[0], lambda s: s[0] + 1, lambda s: 1 - s[1], lambda s: s[1] + 1):
                pts = _clip_poly(pts, keep)
                if len(pts) < 3:
                    break
            if len(pts) < 3:
                continue
            area = 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                                 for i in range(len(pts))))
            share += area / 4.0
        trace.append((float(t_), share))
        worst = max(worst, share)
    return worst, trace


#: the intro cameras' eye points (the environment kit's helper)
shot_eyes = env.shot_eyes


def usbank_shots():
    out = []
    for s, present in zip(USB_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle, the dry retail bundle of the same time of day)."""
    name, data, dry = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=usbank_shots(), dry_bundle=dry)
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
    """{bundle name: retail bytes} of the nine s15 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the U.S. Bank stretch: from the stadium chunk to the end of the intro cameras."""
    ml = sm._ml()
    scenes = ml.bundle_scenes(bundle)
    cam, _dec = mm._cameras_chunk(bundle)
    return scenes["stadium"].offset, cam.offset + 32 + cam.stored_size


def build_all(source, *, workers=None, progress=None, names=None):
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n], retail[dry_of(n)]) for n in (names or VARIANTS)],
                                         workers=workers, progress=progress, label="U.S. Bank Stadium"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the field

#: The field (Act Global Xtreme Turf DX, synthetic; ESPN 2023-12-21): the retail s15 field is a turf venue, one colour
#: quad between the goal lines. The model paints it in 5-yard bands (u runs along the field once the quad's UVs are
#: remapped, in place), the turf outside the field of play, and the Vikings' 2026 end zones from the league project's
#: art (the u4 MIN venue folder: purple, white VIKINGS; the retail s15 field shares each end-zone texture between the
#: two ends, so both ends take it).
FIELD_ART = ART_DIR / "field"
GRASS_MATERIAL, OUTSIDE_MATERIAL = "color_premipped", "grass_outside_premipped"
ENDZONE_TEXTURES = ag.ENDZONE_TEXTURES
TEAM_FIELD = ENDZONE_TEXTURES + ("center_logo",)
remap_grass_uv = ag.remap_grass_uv


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
    """The U.S. Bank field for one bundle (decoded, the retail layout kept). The rain and snow bundles keep the dry look
    (the roof is fixed)."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    turf = _rgba(FIELD_ART / "usb_turf.png")
    outside = _rgba(FIELD_ART / "usb_turf_outside.png")
    for mat, art in ((GRASS_MATERIAL, turf), (OUTSIDE_MATERIAL, outside)):
        row = rows[mat]
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, a, maximum=cap)
    clean = np.array(np.median(turf.reshape(-1, 4), axis=0), np.float32)

    def over_turf(a):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = a[..., :3].astype(np.float32) * al + clean[:3] * (1 - al)
        return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), np.full(a.shape[:2], 255, np.uint8)])
    team = {k: v for k, v in dict(team or {}).items() if k in ENDZONE_TEXTURES}
    detail = sm._half_detail if half else (lambda a: a)
    for mat, art in team.items():
        row = rows.get(mat)
        if row is None:
            continue
        a = art if art.shape[:2] == (row["height"], row["width"]) else sm._resample(art, row["width"], row["height"])
        ml.write_p8(out, system, row, detail(over_turf(a)), maximum=cap)
    remap_grass_uv(out, rec)
    return bytes(out)


#: The Vikings' 2026 midfield head (the Norseman, main's go on 2026-09-27): s15's field has no midfield submesh (u4), so
#: the model adds one to the field scene: a 15.2 m square quad (the retail midfield quads are 7.59 x 7.68 m half
#: extents; the head measures about 14 m tip to tip on the solved 2023 photo u044) at the centre spot, with the mark's
#: top toward the north sideline (+x) and its face toward the east end (+z), as u044 shows it; painted from the league
#: project's art (the u4 MIN venue folder's ``center_logo``, 256 x 256). Material: the retail center_logo record (an
#: alpha overlay drawn after the numbers), cloned from s15's own ``numbers`` with the one word that differs.
MIDFIELD_HALF = 7.6
MIDFIELD_MATERIAL = "center_logo"
#: +0x40 of every retail center_logo material (s02, s09, s11: 0x02042000; the other overlays carry 0x02062000)
MIDFIELD_WORD_40 = 0x02042000


def add_midfield(decoded, system_bytes, logo, *, cap=256, half=False):
    """(decoded, system, video): the field scene with the midfield quad, its material and its texture added (the scene is
    laid out anew; the other records keep their bytes). ``logo`` is the mark's RGBA (256 x 256, alpha kept)."""
    sc = sb.parse(decoded, system_bytes, secondary=True)
    sb.require(all(m.name != MIDFIELD_MATERIAL for m in sc.materials), "the field already has a midfield mark")
    ov = sc.shape("D_graphic_overlays")
    tmpl_m = sc.materials[sc.material_index("numbers")]
    tmpl_t = sc.textures[tmpl_m.texture]
    art = np.asarray(logo, np.uint8)
    if art.shape[:2] != (256, 256):
        art = sm._resample(art, 256, 256)
    if half:
        art = sm._half_detail(art)
    sc.textures.append(sb.p8_texture(tmpl_t, art, palette_cap=cap))
    rec = bytearray(tmpl_m.record)
    struct.pack_into("<I", rec, 0x40, MIDFIELD_WORD_40)
    sc.materials.append(sb.Material(rec, MIDFIELD_MATERIAL, len(sc.textures) - 1, None))
    mat = len(sc.materials) - 1
    # four vertices: u runs toward +z (the mark's right), v toward -x (the mark's top is at +x)
    h = MIDFIELD_HALF
    corners = [((+h, -h), (0.0, 0.0)), ((+h, +h), (1.0, 0.0)), ((-h, -h), (0.0, 1.0)), ((-h, +h), (1.0, 1.0))]
    su, sv, ou, ov_ = struct.unpack_from("<4f", ov.record, 0x30)
    n0 = ov.vertex_count
    s0, s1 = bytearray(ov.streams[0]), bytearray(ov.streams[1])
    for (x, z), (u, v) in corners:
        s0 += struct.pack("<3f", x * 100.0, 0.0, z * 100.0)
        qu = int(round((u - ou) / su * 32767.0)); qv = int(round((v - ov_) / sv * 32767.0))
        sb.require(-32767 <= qu <= 32767 and -32767 <= qv <= 32767, "the overlay UV constant cannot hold the midfield quad")
        s1 += struct.pack("<4B2hh", 255, 255, 255, 255, qu, qv, 0)
    ov.streams[0], ov.streams[1] = bytes(s0), bytes(s1)
    struct.pack_into("<H", ov.record, 0x4C, n0 + 4)
    srec = bytearray(next(sm_ for sm_ in ov.submeshes if sc.materials[sm_.material].name == "numbers").record)
    words = sb.encode_words(sb.TRIANGLE_STRIP, [n0, n0 + 1, n0 + 2, n0 + 3])
    struct.pack_into("<H", srec, 0x00, mat)
    struct.pack_into("<HH", srec, 0x7C, len(words) // 4, 0)
    ov.submeshes.append(sb.Submesh(srec, words))
    struct.pack_into("<H", ov.record, 0x54, len(ov.submeshes))
    sb.set_sphere(ov, sb.shape_positions(ov))
    return sb.serialize(sc)


def fit_keep_scratch(decoded, system_bytes, video_bytes, span):
    """(chunk, info): a scene of a new decoded size in a field span's stored size, the wrapper's scratch word kept at its
    retail value (the 2026-09-03 hard rule: a refit that raises +0x14 hangs the loader at the field load). The system
    and video words describe the new scene; the stream is encoded greedy then optimal, each with the trailing and the
    front literal fill (Modern colour's fitter), and a candidate is taken only when its padding and its in-place alias
    both stay within the retail scratch."""
    ml = sm._ml()
    tx = ml._tools()[0]
    import nfl_vc_lz_fill as fill  # noqa: E402  (on sys.path through ml._tools())
    from . import nfl2k5_modern_color as colour
    head = tx.HEADER.unpack_from(span, 0)
    kind, stored, magic, scratch = head[0], head[1], head[4], head[5]
    sb.require(magic == 0xFEEDBEEF and len(span) == tx.HEADER.size + stored, "not a compressed fixed span")
    sb.require(len(decoded) == system_bytes + video_bytes, "decoded size differs from its parts")
    tag = struct.unpack_from("<I", span, tx.HEADER.size + 4)[0]
    bits = span[tx.HEADER.size + 8]
    attempts = []
    encoders = (("greedy", lambda: tx.compress_vc_lz(bytes(decoded), stream_tag=tag, offset_bits=bits, max_encoded_size=stored,
                                                       verify_roundtrip=False)[0]),
                ("optimal", lambda: fill.compress_optimal(bytes(decoded), stream_tag=tag, offset_bits=bits)))
    for ename, encode in encoders:
        try:
            encoded = encode()
        except tx.TxtrError as exc:
            attempts.append(f"{ename}: {exc}")
            continue
        if len(encoded) > stored:
            attempts.append(f"{ename}: {len(encoded)} > {stored}")
            continue
        for fname, filler in (("trailing", lambda e: fill.fill_stream(e, bytes(decoded), stored, slack=min(scratch, 16))[0]),
                              ("front", lambda e: colour._early_fill(e, bytes(decoded), stored))):
            try:
                filled = filler(encoded) if stored - len(encoded) > scratch else encoded
            except tx.TxtrError as exc:
                attempts.append(f"{ename}/{fname}: {exc}")
                continue
            padding = stored - len(filled)
            alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
            if padding <= scratch and alias <= scratch:
                body = filled + bytes(padding)
                back, info = tx.decompress_vc_lz(body, len(decoded))
                sb.require(back == bytes(decoded) and info.consumed_bytes == len(filled), "refit field failed its decode check")
                chunk = tx.HEADER.pack(kind, stored, system_bytes, video_bytes, 0xFEEDBEEF, scratch, head[6], head[7]) + body
                return chunk, dict(encoder=ename, fill=fname, encoded=len(encoded), padding=padding, alias_scratch=alias,
                                   scratch=scratch)
            attempts.append(f"{ename}/{fname}: padding {padding}, alias {alias}, retail scratch {scratch}")
    raise sb.ScneBuildError("the field does not fit with the retail scratch word: " + "; ".join(attempts))


def midfield_span(span, name, logo, *, caps=(256, 128, 64)):
    """(span of the same stored size, info): a painted field span with the midfield added, the logo stepped down its own
    palette ladder and then to half detail when the scene misses the span."""
    ml = sm._ml()
    tx = ml._tools()[0]
    chunks = tx.parse_chunks(span, allow_trailing=True)
    sb.require(len(chunks) == 1 and chunks[0].kind == "SCNE", f"{name}: not a single field span")
    decoded, _ = tx.decode_chunk(span, chunks[0])
    attempts = []
    for half in (False, True):
        for cap in caps:
            try:
                dec, system, video = add_midfield(decoded, chunks[0].system_bytes, logo, cap=cap, half=half)
                out, info = fit_keep_scratch(dec, system, video, span)
                return out, dict(midfield_cap=cap, midfield_half=half, system=system, video=video, **info)
            except sb.ScneBuildError as exc:
                attempts.append(f"{cap}{' half' if half else ''}: {exc}")
    raise sb.ScneBuildError(f"{name}: the midfield does not fit: " + " | ".join(attempts))


FIELD_LADDER = ag.FIELD_LADDER
FIELD_SKIP_FIRST = ag.FIELD_SKIP_FIRST


def surface_span(span, bundle, name, colour_settings=None):
    """(field span, tf's receipt): the playing surface and the apron on tf's palette (modern_surfaces, tf-v2: s15's look,
    the 2026 broadcast measured at U.S. Bank Stadium, the game's measured response; main, 2026-09-27: keep the field's
    colours on tf's palette, never tuned here), through tf's own painter and fit, after the end-zone art. The fixed roof
    puts every s15 bundle under the dome light. Modern surfaces, run later as the last stadium writer, leaves this
    field's paint as it is (its painter is idempotent) and adds its detail normal."""
    from . import nfl2k5_modern_surfaces as ms
    look = ms.venue_look(VENUE)
    cls = ms.light_class(name, True)
    rig = ms.rig_name(cls, name[3])
    return ms.field_span(span, look=look, cls=cls, rig=rig, colour_settings=colour_settings, tint=ms.field_tint(bundle),
                         target=ms.venue_target(VENUE, look, cls))


def field_span(bundle, name, *, team=None, colour_settings=None, outer_index=0):
    """(field span of the same size, receipt) for one retail bundle (Allegiant's ladder and colour path)."""
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
            if team and MIDFIELD_MATERIAL in team:
                after, mid = midfield_span(after, name, team[MIDFIELD_MATERIAL])
                sb.require(len(after) == len(span), f"{name}: the field escaped its span")
            return after, dict(palette_cap=cap, half_detail=half, fit_attempts=attempts, colour=colour_settings is not None,
                               team_art=sorted(team or {}), midfield=mid,
                               surface={k: surf.get(k) for k in ("look", "light", "rig", "layout", "target", "map_mean",
                                                                  "outside_mean", "palette_cap", "refit")},
                               **{k: v for k, v in (detail or {}).items() if k in ("encoder", "fill", "padding_bytes")})
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"{rung}: {exc}")
    raise sb.ScneBuildError(f"{name}: the U.S. Bank field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_usbank_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_usbank_receipt/v1"
BUILD_CAPTION = "U.S. Bank Stadium for the Vikings (experimental)"
HELP_TEXT = (
    "The Minnesota Vikings' U.S. Bank Stadium, built as a new model for Vikings home games in every time of day: the "
    "purple bowl under the fixed roof (the pale ETFE south of the ridge truss, the dark opaque half north of it, the "
    "open trusses), the Legacy Gate glass wall and the prow with its wordmark and display, the two end-zone video "
    "boards with the live feed, the east end's banner, flag and partner panels, downtown's towers through the glass, "
    "and a new pregame flyover with exterior passes. The field is the 2026 turf on the Modern surfaces palette with "
    "the 2026 venue art's Vikings end zones and the midfield head when that option is on. The row reads U.S. Bank "
    "Stadium, Minneapolis, MN; the roof is fixed, so no rain or snow falls. The 2026 venue art leaves the Vikings' "
    "packages to it. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "U.S. Bank Stadium pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported U.S. Bank Stadium pins schema")
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
    """retail / applied / foreign for the U.S. Bank stretch of one of the nine bundles."""
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
    return Path(str(source) + ".usbank.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported U.S. Bank Stadium receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches and the s15 row."""
    from . import nfl2k5_usbank_venue as uv
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
    sb.require(state == ("applied" if enabled else "retail"), f"U.S. Bank Stadium state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


@official.requires_pack("modern_usbank")
def check_request(source):
    """The build's quick check before any copy: the stretches and the row are retail (or already U.S. Bank)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the Vikings stadium packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, outer, team art or None, the dry
    retail bundle of the same time of day)."""
    name, retail, current, settings, outer, team, dry = job
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=usbank_shots(), dry_bundle=dry)
    field, finfo = field_span(retail, name, team=team, colour_settings=settings, outer_index=outer)
    ml = sm._ml()
    chunk = ml.bundle_scenes(retail)["field"]
    start, end = stretch(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field)] = field
    out[start:end] = model[start:end]
    return name, bytes(out), dict(info, field=finfo)


@official.requires_pack("modern_usbank")
def apply_to_image(target, *, retail_source, art_root=None, progress=None, workers=None):
    """Build step (after Modern colour and the 2026 venue art, which leaves s15 to it; before Modern surfaces, the last
    stadium writer, which keeps this field's paint): the U.S. Bank field, stadium and cameras of the nine bundles, and
    the s15 row. The retail bundles come from ``retail_source``; the image's own bundles keep every other chunk (Modern
    colour's normal map and tint word). With Modern colour on, the field is composed before the colour grade and the
    colour receipt is updated so Modern colour still recognizes its bytes; the turf and apron then take the Modern
    surfaces palette for s15 through that option's own painter. ``art_root`` is the 2026 venue art folder: its Vikings
    end zones and midfield head go onto the new field (without it the field keeps the retail end zones).
    Retained fan banners use this same art root through nfl2k5_model_fan_art;
    the composed model stretch is recorded and verified in the build receipt.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_usbank_venue as uv
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries U.S. Bank Stadium")
    state = image_status(target)
    if state == "applied":
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"U.S. Bank Stadium needs retail Vikings packages (found {state})")
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
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="U.S. Bank Stadium")
    from . import nfl2k5_model_fan_art as fans
    results = fans.paint_results(results, retail, art_root, model_pins())
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the U.S. Bank bundle changed size")
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
        new_colour["usbank"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after U.S. Bank Stadium: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"U.S. Bank Stadium changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    fans.preserve_receipts(target, receipt)
    say("U.S. Bank Stadium: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_art=sorted(team))


def apply_lab_disc(disc, source, *, art_root=None, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_usbank_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--art-root", default=None)
    a = sub.add_parser("apply-lab", help="lab only: write the U.S. Bank stretches, fields and row into a built disc")
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
    Path(str(args.disc) + ".st3-usbank.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
    print("ST3_USBANK_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
