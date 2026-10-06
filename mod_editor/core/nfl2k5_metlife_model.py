"""Modern MetLife model (experimental): MetLife Stadium rebuilt as a new stadium scene for the Giants (s18) and
Jets (s19) venue records, all eighteen bundles (day, afternoon, night; dry, rain, snow).

Job u5 (2026-09-23/24). The skin (``nfl2k5_modern_metlife``) repainted Giants Stadium; this option replaces the
stadium scene itself with a model built from scratch to MetLife's real plan and section:

* the seating bowl: the 100 level, the 360 degree ribbon, Suite Level 3, the club fascia, the 200 level, Suite Levels 5
  and 6 on the sidelines, the board band at the ends, the 300 level, soffits and the rim, with crowd billboards in
  the retail convention (the runtime crowd atlas: U picks a quarter strip, V runs along the row at 9.14 m a unit);
* the four corner video boards (35 x 9.1 m) on the ``jumbo_tron`` material the game feeds live, with the score and
  clock digits moved onto them;
* the Solar Ring (47 frames on the rim) with its LED strip (team colour at night) and the light-glow and flare
  markers moved onto it;
* the facade on the real footprint (OpenStreetMap), limestone base, aluminium louvres (glass lit in team colour at
  night) and the concourse roof;
* kept from retail because the engine or gameplay uses them: the field scene, the sideline props, pylons and yard
  markers, the field-level banners (projected onto the new wall), the 190 markers, and every material the executable
  looks up by name (``crowd``, ``jumbo_tron``, ``digit_*``).

The scene is written from scratch by ``nfl2k5_scne_builder`` and fitted into the retail stored span of each bundle's
stadium chunk (a literal fill up to the stored size, scratch word at the exact in-place minimum), so every bundle
and archive entry keeps its size and nothing else on the disc moves. The decoded scene is smaller than retail.
Geometry is in metres here (x across, +x west on the broadcast side; y up; z along, +z north) and centimetres in the
game. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
"""
from __future__ import annotations

from . import nfl2k5_official_marks as official

import hashlib
import json
from . import exact_math as math
import struct
from pathlib import Path

class _LazyNumpy:
    # b76 main: the Build panel imports this module for its caption and help text, and both studios must open every
    # page without numpy (tests/mod_editor/test_numpy_optional.py). numpy loads on first use, when a model is built.
    def __getattr__(self, name):
        import numpy
        globals()["np"] = numpy
        return getattr(numpy, name)


np = _LazyNumpy()
from PIL import Image

from . import nfl2k5_modern_metlife as ml
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_stadium_environment as env

OWNER = "nfl2k5_metlife_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_metlife_model"
ART_DIR = DATA_DIR / "art"
FOOTPRINT_PATH = DATA_DIR / "footprint.json"
_FOOTPRINT = None


def footprint():
    global _FOOTPRINT
    if _FOOTPRINT is None:
        _FOOTPRINT = json.loads(FOOTPRINT_PATH.read_text(encoding="utf-8"))
    return _FOOTPRINT


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


# ------------------------------------------------------------------------------------------------ mesh builder

class Mesh:
    def __init__(self, name):
        self.name = name
        self.P, self.UV, self.C, self.N = [], [], [], []
        self.groups = {}

    def v(self, p, uv, n=(0.0, 1.0, 0.0)):
        self.P.append(tuple(float(x) for x in p))
        self.UV.append((float(uv[0]), float(uv[1])))
        self.N.append(tuple(float(x) for x in n))
        return len(self.P) - 1

    def strip(self, material, indices):
        if len(indices) >= 3:
            self.groups.setdefault(material, []).append(list(indices))

    def grid(self, material, pts, uvs, facing=None):
        """pts[r][c]; one strip per row pair; columns reversed when the grid faces away from ``facing``."""
        R, Cc = len(pts) - 1, len(pts[0]) - 1
        if R < 1 or Cc < 1:
            return
        P = np.asarray(pts, dtype=float)
        # per-vertex normals from the grid
        du = np.gradient(P, axis=1)
        dv = np.gradient(P, axis=0)
        nrm = np.cross(dv, du)
        ln = math.np_norm(nrm, axis=2, keepdims=True)
        nrm = np.where(ln > 1e-9, nrm / np.maximum(ln, 1e-9), np.array([0, 1.0, 0]))
        flip = False
        if facing is not None:
            votes = 0.0
            for r in range(R):
                for c in range(Cc):
                    a, b, d = P[r, c], P[r + 1, c], P[r, c + 1]
                    n = np.cross(b - a, d - a)
                    if math.np_norm(n) > 1e-6:
                        votes += np.sign(math.np_dot(n, facing((a + b + d) / 3)))
            flip = votes < 0
        sign = -1.0 if flip else 1.0
        idx = [[self.v(P[r, c], uvs[r][c], sign * nrm[r, c]) for c in range(Cc + 1)] for r in range(R + 1)]
        for r in range(R):
            cols = range(Cc, -1, -1) if flip else range(Cc + 1)
            row = []
            for c in cols:
                row += [idx[r][c], idx[r + 1][c]]
            self.strip(material, row)

    def quad(self, material, a, b, c, d, uva, uvb, uvc, uvd, facing=None):
        self.grid(material, [[a, d], [b, c]], [[uva, uvd], [uvb, uvc]], facing)

    def box(self, material, centre, axes, half, uvscale=0.2, bottom=False):
        """Oriented box: centre, three unit axes (u, up, w), half sizes; five or six faces facing out."""
        c = np.asarray(centre, float)
        U, V, Wd = (np.asarray(a, float) for a in axes)
        hu, hv, hw = half
        corners = {}
        for su in (-1, 1):
            for sv in (-1, 1):
                for sw in (-1, 1):
                    corners[(su, sv, sw)] = c + su * hu * U + sv * hv * V + sw * hw * Wd
        faces = [((1, -1, -1), (1, -1, 1), (1, 1, 1), (1, 1, -1)), ((-1, -1, 1), (-1, -1, -1), (-1, 1, -1), (-1, 1, 1)),
                 ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)),
                 ((-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1))]
        if bottom:
            faces.append(((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)))
        for f in faces:
            a, b, cc, d = (corners[k] for k in f)
            w, h = math.np_norm(b - a), math.np_norm(d - a)
            self.quad(material, a, b, cc, d, (0, h * uvscale), (w * uvscale, h * uvscale), (w * uvscale, 0), (0, 0),
                      facing=lambda p, c=c: p - c)

    def count(self):
        return len(self.P)


# ------------------------------------------------------------------------------------------------ plan loop

class LoopPoint:
    __slots__ = ("x", "z", "nx", "nz", "s", "side", "end", "corner")

    def __init__(self, x, z, nx, nz, s, side, end):
        self.x, self.z, self.nx, self.nz, self.s, self.side, self.end = x, z, nx, nz, s, side, end
        self.corner = 1.0 - max(side, end)


def plan_loop(W, L, R, step=6.0, corner_steps=10):
    """Rounded rectangle (half-width W across x, half-length L along z, corner radius R), counter-clockwise from
    above (+y), starting at the +x sideline centre. ``side``/``end`` weights: 1 on the straights, blended in the
    corners by the normal's direction."""
    segs = []
    sx, ez = L - R, W - R

    def line(p0, p1, n):
        k = max(1, int(round(math.dist(p0, p1) / step)))
        for i in range(k):
            t = i / k
            segs.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, n[0], n[1]))

    def arc(cx, cz, a0, a1):
        for i in range(corner_steps):
            a = a0 + (a1 - a0) * i / corner_steps
            segs.append((cx + R * math.cos(a), cz + R * math.sin(a), math.cos(a), math.sin(a)))

    line((W, 0.0), (W, sx), (1, 0))
    arc(W - R, sx, 0.0, math.pi / 2)
    line((ez, L), (-ez, L), (0, 1))
    arc(-(W - R), sx, math.pi / 2, math.pi)
    line((-W, sx), (-W, -sx), (-1, 0))
    arc(-(W - R), -sx, math.pi, 1.5 * math.pi)
    line((-ez, -L), (ez, -L), (0, -1))
    arc(W - R, -sx, 1.5 * math.pi, 2 * math.pi)
    line((W, -sx), (W, 0.0), (1, 0))
    pts, s, prev = [], 0.0, None

    def w(v):
        v = abs(v)
        return 1.0 if v > 0.999 else math.pow(float(np.clip((v - 0.55) / 0.4, 0, 1)), 2)
    for x, z, nx, nz in segs + [segs[0]]:
        if prev is not None:
            s += math.dist(prev, (x, z))
        prev = (x, z)
        pts.append(LoopPoint(x, z, nx, nz, s, w(nx), w(nz)))
    return pts


def toward_field(p):
    v = np.array([-p[0], 0.0, -p[2]])
    n = math.np_norm(v)
    return v / n if n else v


def up_toward_field(p):
    return toward_field(p) * 0.6 + np.array([0, 1.0, 0])


def up(p):
    return np.array([0, 1.0, 0])


def down(p):
    return np.array([0, -1.0, 0])


# ------------------------------------------------------------------------------------------------ parameters

PARAMS = dict(
    loop=dict(W=39.0, L=66.5, R=21.0, step=6.5, corner_steps=10),
    wall=dict(height=1.8),
    lower=dict(rows_side=33, rows_end=36, tread=0.86, rise0=0.24, rise1=0.42, d0=1.3, y0=1.45),
    ribbon=dict(height=1.05),
    suite3=dict(height=3.4, recess=1.0),
    club_fascia=dict(height=1.5),
    mid=dict(rows_side=15, rows_end=9, tread=0.90, rise=0.55, setback=0.9),
    suites56=dict(each=3.5, gap=0.5, recess=1.6),
    upper=dict(front_depth=40.5, front_y=36.4, rows=26, tread=0.80, rise=0.64, fascia=1.6),
    rim=dict(back_wall=2.3, walk=4.0),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35),
    field_club=dict(height=1.9, setback=1.6, half_length=38.0, ramp=6.0, rows_lost=2),
    portals=dict(every_m=26.0, lower_row=8, upper_row=9, width=2.4, height=2.2),
    letters=dict(ring_width=44.0, ring_height=5.0, facade_width=52.0, facade_height=6.2),
    logos=dict(end_width=22.0, end_height=5.5, end_y=30.5, facade_width=34.0, facade_height=8.5),
    seats=dict(u_per_m=1 / 13.0, rows_per_v=21.0),
    boards=dict(width=35.0, height=9.1, centre_x=31.0, bottom_y=24.5, header=2.0),
    ring=dict(frames=47, depth=8.5, rise=3.0, post=5.5, gap=1.2),
    facade=dict(base=6.5, louvre_top=50.5, band_top=56.0, roof_y=56.0),
)


def blend(w, a, b):
    return a * w + b * (1 - w)


# ------------------------------------------------------------------------------------------------ the model

class MetLife:
    def __init__(self, params=None, venue="s18"):
        p = json.loads(json.dumps(PARAMS))
        for k, v in (params or {}).items():
            p[k].update(v)
        self.p, self.venue = p, venue
        q = p["loop"]
        self.loop = plan_loop(q["W"], q["L"], q["R"], q["step"], q["corner_steps"])
        self.meshes = {}
        self.markers = {}
        # the home team's Ring of Honor (data/nfl2k5_metlife_model/ring_of_honor.json, the atlas order)
        roh = json.loads((DATA_DIR / "ring_of_honor.json").read_text(encoding="utf-8"))
        self.roh_count = len(roh["giants" if venue == "s18" else "jets"])

    def at(self, lp, d, y):
        return (lp.x + lp.nx * d, y, lp.z + lp.nz * d)

    # -- sections --------------------------------------------------------------------------------------
    def section(self, lp):
        """Profile of one loop point: dict of named elements (depth d from the wall line, height y)."""
        p = self.p
        q = p["lower"]
        out = {}
        rows = int(round(blend(lp.side, q["rows_side"], q["rows_end"])))
        d, y = q["d0"], q["y0"]
        fc = p["field_club"]
        club = lp.side * float(np.clip((fc["half_length"] - abs(lp.z)) / fc["ramp"], 0.0, 1.0))
        if club > 0.0:
            out["field_club"] = (0.35, p["wall"]["height"], p["wall"]["height"] + fc["height"] * club)
            d += fc["setback"] * club
            y += fc["height"] * club
            rows = max(1, rows - int(round(fc["rows_lost"] * club)))
        lower = [(d, y)]
        for i in range(rows):
            t = i / max(1, rows - 1)
            d += q["tread"]
            y += q["rise0"] + (q["rise1"] - q["rise0"]) * t
            lower.append((d, y))
        out["lower"] = lower
        d_top, y = lower[-1]
        dwall = d_top + 0.5
        out["ribbon"] = (dwall, y, y + p["ribbon"]["height"])
        y += p["ribbon"]["height"]
        s3 = p["suite3"]["height"] * lp.side
        out["suite3"] = (dwall + p["suite3"]["recess"], y, y + s3)
        y += s3
        out["club_fascia"] = (dwall, y, y + p["club_fascia"]["height"])
        y += p["club_fascia"]["height"]
        q2 = p["mid"]
        mrows = int(round(blend(lp.side, q2["rows_side"], q2["rows_end"])))
        d = dwall + q2["setback"]
        mid = [(d, y)]
        for i in range(mrows):
            d += q2["tread"]
            y += q2["rise"]
            mid.append((d, y))
        out["mid"] = mid
        q3 = p["upper"]
        fy = q3["front_y"]
        dmb = mid[-1][0] + 0.6
        out["mid_back"] = (dmb, mid[-1][1], fy)
        if lp.side > 0.02:
            s = p["suites56"]
            h = s["each"] * lp.side
            y5 = mid[-1][1] + 0.3
            out["suite5"] = (dmb + s["recess"], y5, y5 + h)
            out["suite6"] = (dmb + s["recess"] + 0.5, y5 + h + s["gap"] * lp.side, y5 + 2 * h + s["gap"] * lp.side)
        # closures, so nothing recessed can be seen through: suite level 3's floor and ceiling, the floor from the
        # 200 level's last row to the suites, and the wall from the top of suite level 6 to the soffit
        s3d, s3y0, s3y1 = out["suite3"]
        if s3y1 - s3y0 > 0.05:
            out["suite3_floor"] = (dwall, s3d, s3y0)
            out["suite3_ceiling"] = (dwall, s3d, s3y1)
        if "suite5" in out:
            out["suites_floor"] = (mid[-1][0], out["suite5"][0], mid[-1][1])
            out["suites_top"] = (out["suite6"][0], out["suite6"][2], fy)
        dfront = q3["front_depth"]
        out["upper_fascia"] = (dfront, fy, fy + q3["fascia"])
        d, y = dfront + 0.3, fy + q3["fascia"]
        upper = [(d, y)]
        for i in range(q3["rows"]):
            d += q3["tread"]
            y += q3["rise"]
            upper.append((d, y))
        out["upper"] = upper
        out["soffit"] = (dfront, dmb + 2.2, fy)
        rim = p["rim"]
        out["rim"] = (d + 0.3, y, y + rim["back_wall"], d + 0.3 + rim["walk"])
        return out

    # -- build -----------------------------------------------------------------------------------------
    SECTORS = 12

    def build(self):
        loop = self.loop
        secs = [self.section(lp) for lp in loop]
        self.secs = secs
        n = len(loop) - 1                      # the last point repeats the first
        cuts = [round(k * n / self.SECTORS) for k in range(self.SECTORS + 1)]
        for k in range(self.SECTORS):
            a, b = cuts[k], cuts[k + 1]
            self.prefix = f"ml_bowl{k:02d}"
            self._bowl(loop[a:b + 1], secs[a:b + 1])
        self._signage(loop, secs, cuts)
        self._wall(loop, cuts)
        self.prefix = "ml"
        self._boards(loop, secs)
        self._ring(loop, secs)
        self._facade(loop, secs)
        self._signs(loop, secs)
        self._gates()
        self._split_by_angle("ml_ring", 8)
        self._environment()
        return self

    def _environment(self):
        """Round the stadium, which stood on nothing before: the shared environment kit (st3, 2026-09-28): a concrete
        plaza 30 m wide round the OpenStreetMap outline, then the Meadowlands' lots with their cars, the roads and the
        Turnpike, the marsh, water and trees from OpenStreetMap, the far ground to the haze and the horizon band with
        Manhattan's towers at their true elevation angles. The gate pavilions stay this model's own (kept out)."""
        fp = footprint()
        outline = [(float(ac), float(al)) for al, ac in fp["outline"]]
        gates = [[(float(ac), float(al)) for al, ac in g] for g in fp.get("gates", {}).values()]
        self.env_counts = env.dress(self, self.venue, grade=0.0, keep_out=[outline] + gates, inner=outline,
                                    plaza=30.0, eyes=env.shot_eyes(metlife_shots()))

    def mesh(self, name):
        if name.startswith("ml_bowl_") or name == "ml_rim":
            name = getattr(self, "prefix", "ml_bowl")
        return self.meshes.setdefault(name, Mesh(name))

    def _split_by_angle(self, name, parts):
        m = self.meshes.pop(name, None)
        if m is None:
            return
        P = np.array(m.P)
        out = {}
        for mat, strips in m.groups.items():
            for st in strips:
                c = P[st].mean(0)
                a = (math.atan2(c[2], c[0]) + 2 * math.pi) % (2 * math.pi)
                k = int(a / (2 * math.pi) * parts) % parts
                mm = out.setdefault(k, Mesh(f"{name}{k:02d}"))
                remap = {}
                new = []
                for i in st:
                    if i not in remap:
                        remap[i] = mm.v(m.P[i], m.UV[i], m.N[i])
                    new.append(remap[i])
                mm.strip(mat, new)
        for k, mm in sorted(out.items()):
            self.meshes[mm.name] = mm

    def _rows_surface(self, m, material, loop, profiles, rows_per_band, vstart=0.0):
        """The seating surface; where the row count changes along the loop (sideline to end) each point keeps its
        own rows and a shorter profile repeats its last row (zero-area quads), so the surface has no hole."""
        R = max(len(pr) for pr in profiles) - 1
        ks = list(range(0, R + 1, rows_per_band))
        if ks[-1] != R:
            ks.append(R)
        su = self.p["seats"]["u_per_m"]
        pts = [[self.at(lp, *pr[min(k, len(pr) - 1)]) for lp, pr in zip(loop, profiles)] for k in ks]
        uvs = [[(lp.s * su, vstart + min(k, len(pr) - 1) / self.p["seats"]["rows_per_v"])
                for lp, pr in zip(loop, profiles)] for k in ks]
        m.grid(material, pts, uvs, facing=up_toward_field)

    def _crowd(self, m, loop, profiles):
        q = self.p["crowd"]
        R = max(len(pr) for pr in profiles) - 1
        for b, k in enumerate(range(0, R, q["rows_per_band"])):
            quarter = [0.0, 0.5, 0.25, 0.75][b % 4]
            bot, top, ub, ut = [], [], [], []
            for lp, pr in zip(loop, profiles):
                last = len(pr) - 1
                d0, y0 = pr[min(k, last)]
                d1, y1 = pr[min(k + q["rows_per_band"], last)]
                # a profile without this band collapses the billboard to zero height at its last row
                h = 0.0 if k >= last else (y1 - y0) + q["extra"]
                bot.append(self.at(lp, d0 + 0.15, y0 + q["lift"]))
                top.append(self.at(lp, d0 + 0.15 + q["lean"] * (d1 - d0), y0 + q["lift"] + h))
                v = lp.s * q["v_per_m"]
                ub.append((quarter + 0.2425, v))
                ut.append((quarter + 0.0075, v))
            m.grid("crowd", [bot, top], [ub, ut], facing=toward_field)

    # -- signage decals (b76-u5b): every sign and Ring of Honor plate is its own strip of geometry at the cell's
    #    own aspect on the dark fascia, following the fascia's curve; no texture is stretched along a band.
    #: the signage atlas (tools art: 256x512; Ring of Honor cells 128x12 from row 0, sign cells 128x16 from row
    #: 304, two columns): sign names in atlas order
    SIGNS = ["metlife_white", "metlife_dark", "team_wordmark", "team_logo", "slogan", "metlife_stadium", "verizon",
             "bud_light", "pepsi", "hcltech", "team_city", "team_extra"]
    #: the 360 ribbon runs the home team's content end to end (the 2025 Giants photos: royal blue, white type; the
    #: 2026 Jets White Out photos: "JETS", "NEW YORK JETS" in white on black), the club fascia above it MetLife's
    #: ("MetLife" and "METLIFE STADIUM" in white on black, the same 2026 photo)
    RIBBON_SIGNS = {"s18": ["team_wordmark", "team_logo", "slogan", "team_wordmark", "team_city", "team_extra"],
                    "s19": ["team_wordmark", "team_city", "team_logo"]}
    CLUB_SIGNS = ["metlife_dark", "metlife_stadium"]
    ROH_PLATE = (0.9, 128.0 / 12.0)             # plate height (m) and aspect (the atlas cell)

    @classmethod
    def sign_cell(cls, name):
        j = cls.SIGNS.index(name)
        u0, v0 = (j % 2) * 0.5, (304 + (j // 2) * 16) / 512.0
        return u0, v0, u0 + 0.5, v0 + 16 / 512.0

    @staticmethod
    def roh_cell(i):
        u0, v0 = (i % 2) * 0.5, (i // 2) * 12 / 512.0
        return u0, v0, u0 + 0.5, v0 + 12 / 512.0

    #: the fascia bands that carry signs: (band key, sign list, sign height m); the 8:1 cells run end to end, a few
    #: centimetres apart, inside the dark band (1.05 m ribbon, 1.5 m club fascia)
    SIGN_BANDS = (("ribbon", "RIBBON_SIGNS", 0.95), ("club_fascia", "CLUB_SIGNS", 1.35))

    def _band_runs(self, loop, secs, key, min_h=0.05):
        """Runs of consecutive loop indices where the band exists (a run through the loop's seam is joined)."""
        runs, run = [], []
        for i, sec in enumerate(secs):
            item = sec.get(key)
            if item is None or item[2] - item[1] < min_h:
                if len(run) >= 2:
                    runs.append(run)
                run = []
                continue
            run.append(i)
        if len(run) >= 2:
            runs.append(run)
        n = len(loop) - 1                       # the last point repeats the first
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n:
            runs = [runs[-1] + runs[0][1:]] + runs[1:-1]
        return runs

    def _band_path(self, loop, secs, key, run):
        """The band's bottom and top points along one run and their arc length (metres, along the band's middle)."""
        bot = np.array([self.at(loop[i], secs[i][key][0], secs[i][key][1]) for i in run])
        top = np.array([self.at(loop[i], secs[i][key][0], secs[i][key][2]) for i in run])
        mid = (bot + top) / 2
        s = np.concatenate([[0.0], np.cumsum(math.np_norm(np.diff(mid, axis=0), axis=1))])
        return bot, top, s

    def _sector_mesh(self, index, cuts):
        """The bowl sector mesh that holds loop point ``index``."""
        k = max(j for j in range(self.SECTORS) if cuts[j] <= min(index, cuts[-1] - 1))
        return self.meshes.setdefault(f"ml_bowl{k:02d}", Mesh(f"ml_bowl{k:02d}"))

    def _decals(self, loop, secs, cuts, key, run, placements, height):
        """Signs on one run of a fascia band: placements are (start m, width m, atlas cell). Each sign is a strip
        through the band's own vertices, so it lies on the band's facets, 3 cm in front, centred on the band, and
        goes into the sector mesh that holds its centre."""
        bot, top, s = self._band_path(loop, secs, key, run)
        total = s[-1]
        for s0, width, (u0, v0, u1, v1) in placements:
            s1 = s0 + width
            if s0 < 0 or s1 > total:
                continue
            knots = [s0] + [x for x in s if s0 + 0.05 < x < s1 - 0.05] + [s1]
            rows_b, rows_t, uv_b, uv_t = [], [], [], []
            for x in knots:
                k = min(int(np.searchsorted(s, x, side="right") - 1), len(s) - 2)
                f = (x - s[k]) / max(s[k + 1] - s[k], 1e-9)
                pb = bot[k] * (1 - f) + bot[k + 1] * f
                pt = top[k] * (1 - f) + top[k + 1] * f
                mid, half = (pb + pt) / 2, (pt - pb) / math.np_norm(pt - pb) * height / 2
                off = toward_field(mid) * 0.03
                rows_b.append(mid - half + off)
                rows_t.append(mid + half + off)
                u = u0 + (u1 - u0) * (x - s0) / width
                uv_b.append((u, v1)); uv_t.append((u, v0))
            centre = run[min(int(np.searchsorted(s, s0 + width / 2, side="right") - 1), len(run) - 1)]
            self._sector_mesh(centre, cuts).grid("ml_signs", [rows_b, rows_t], [uv_b, uv_t], facing=toward_field)

    def sign_placements(self, loop, secs):
        """[(band key, run, start m, width m, height m, atlas cell)]: the team's content on the ribbon and MetLife's
        on the club fascia (8:1 cells end to end around the whole band, in the list's order), and the home team's
        Ring of Honor on the 300-level fascia: every member on a white plate at the atlas cell's 10.67:1 aspect, a
        third of a plate apart, in the list's order read left to right from the field, the run centred on the far
        (-x) sideline (the Giants' fifty go all the way round)."""
        out = []
        for key, names, height in self.SIGN_BANDS:
            names = getattr(self, names)
            names = names[self.venue] if isinstance(names, dict) else names
            for run in self._band_runs(loop, secs, key):
                total = self._band_path(loop, secs, key, run)[2][-1]
                width = height * 8.0
                count = max(1, int(total // width))
                step = total / count
                out += [(key, run, step / 2 - width / 2 + i * step, width, height,
                         self.sign_cell(names[i % len(names)])) for i in range(count)]
        h, aspect = self.ROH_PLATE
        count = self.roh_count
        runs = self._band_runs(loop, secs, "upper_fascia")
        if count > 0 and runs:
            run = max(runs, key=len)
            total = self._band_path(loop, secs, "upper_fascia", run)[2][-1]
            width = h * aspect
            step = min(total / count, width * 1.3)      # the plates stand about a third of a plate apart (2026 photo)
            first = total / 2 - count * step / 2        # a short list is centred on the far (-x) sideline
            out += [("upper_fascia", run, first + i * step + (step - width) / 2, width, h, self.roh_cell(i))
                    for i in range(count)]
        return out

    def _signage(self, loop, secs, cuts):
        groups = {}
        for key, run, s0, width, height, cell in self.sign_placements(loop, secs):
            groups.setdefault((key, tuple(run), height), []).append((s0, width, cell))
        for (key, run, height), placements in groups.items():
            self._decals(loop, secs, cuts, key, list(run), placements, height)

    # -- the field wall (b76-u5b): panels of the venue's wall atlas (data/nfl2k5_metlife_model/wall.json), every
    #    panel at its cell's own aspect, laid left to right (as seen from the field) region by region
    def wall_spec(self):
        spec = json.loads((DATA_DIR / "wall.json").read_text(encoding="utf-8"))
        return spec, spec["venues"][self.venue]

    def wall_regions(self):
        """[(kind, start s, length, sideline index)] of the wall loop: the sidelines, the ends and the four corner
        arcs (the loop's own chords), starting with the +x sideline centred on s = 0."""
        q = self.p["loop"]
        side, end = 2 * (q["L"] - q["R"]), 2 * (q["W"] - q["R"])
        arc = q["corner_steps"] * 2 * q["R"] * math.sin(math.pi / (4 * q["corner_steps"]))
        out, s = [("sideline", -side / 2, side, 0)], side / 2
        for kind, length, k in (("corner", arc, None), ("end", end, None), ("corner", arc, None), ("sideline", side, 1),
                                ("corner", arc, None), ("end", end, None), ("corner", arc, None)):
            out.append((kind, s, length, k))
            s += length
        return out

    def wall_panels(self):
        """[(s0, width, cell)] around the wall; 'fill' shares out what the fixed panels leave, in base cells."""
        spec, v = self.wall_spec()
        H, cells = spec["height_m"], v["cells"]

        def width(name):
            if name.startswith("num_"):
                return v["number_panel_m"]
            x0, y0, x1, y1 = cells[name]
            return H * (x1 - x0) / (y1 - y0)
        out = []
        for kind, start, length, k in self.wall_regions():
            items = v["layout"][kind]
            numbers = list(v["numbers"][k]) if k is not None else []
            names = []
            for it in items:
                if it == "num":
                    names.append(f"num_{numbers.pop(0)}")
                else:
                    names.append(it)
            fixed = sum(width(n) for n in names if n != "fill")
            fills = sum(1 for n in names if n == "fill")
            f = (length - fixed) / fills if fills else 0.0
            if f < -1e-6 or (not fills and abs(length - fixed) > 1e-6):
                raise ValueError(f"wall layout {self.venue}/{kind} does not fit its {length:.2f} m")
            s = start
            for n in names:
                if n == "fill":
                    base = width("base")
                    parts = max(1, math.ceil(f / base - 1e-9))
                    for _ in range(parts):
                        out.append((s, f / parts, "base"))
                        s += f / parts
                else:
                    out.append((s, width(n), n))
                    s += width(n)
        return out

    def _wall(self, loop, cuts):
        spec, v = self.wall_spec()
        H = spec["height_m"]
        aw, ah = spec["atlas"]
        total = loop[-1].s
        S = np.array([lp.s for lp in loop])
        P = np.array([(lp.x, lp.z) for lp in loop])

        def at(x):
            x %= total
            k = min(int(np.searchsorted(S, x, side="right") - 1), len(S) - 2)
            f = (x - S[k]) / max(S[k + 1] - S[k], 1e-9)
            return P[k] * (1 - f) + P[k + 1] * f, k
        decals = v.get("number_decals")
        for s0, w, name in self.wall_panels():
            number = name if name.startswith("num_") else None
            x0, y0, x1, y1 = v["cells"]["base" if number else name]
            u0, u1, vt, vb = x0 / aw, x0 / aw + (x1 - x0) / aw * min(1.0, w / (H * (x1 - x0) / (y1 - y0))), y0 / ah, y1 / ah
            s1 = s0 + w
            if number:                      # the retired number's box over the middle of a base panel, 3 cm out
                (cx, cz), _k = at(s0 + w / 2)
                (ax, az), _k = at(s0 + w / 2 - 0.5)
                (bx, bz), _k = at(s0 + w / 2 + 0.5)
                t = np.array([bx - ax, 0.0, bz - az]); t /= math.np_norm(t)
                c = np.array([cx, 0.0, cz]) + toward_field(np.array([cx, 0.0, cz])) * 0.03
                bw, bh = decals["size_m"]
                bx0, by0, bx1, by1 = decals["cells"][number]
                sw_, sh_ = 256.0, 512.0     # the signage atlas
                lo, hi = np.array([0.0, 0.91 - bh / 2, 0.0]), np.array([0.0, 0.91 + bh / 2, 0.0])
                (_c, kk) = at(s0 + w / 2)
                self._sector_mesh(kk, cuts).quad(
                    "ml_wall_signs", c - t * bw / 2 + lo, c + t * bw / 2 + lo, c + t * bw / 2 + hi, c - t * bw / 2 + hi,
                    (bx0 / sw_, by1 / sh_), (bx1 / sw_, by1 / sh_), (bx1 / sw_, by0 / sh_), (bx0 / sw_, by0 / sh_),
                    facing=toward_field)
            knots = [s0] + [x + t * total for t in (-1, 0, 1) for x in S[:-1] if s0 + 0.05 < x + t * total < s1 - 0.05] + [s1]
            knots.sort()
            bot, top, ub, ut = [], [], [], []
            for x in knots:
                (px, pz), _k = at(x)
                bot.append((px, 0.0, pz)); top.append((px, H, pz))
                u = u0 + (u1 - u0) * (x - s0) / w
                ub.append((u, vb)); ut.append((u, vt))
            _c, k = at(s0 + w / 2)
            self._sector_mesh(k, cuts).grid("ml_wall", [bot, top], [ub, ut], facing=toward_field)

    def _band(self, m, material, loop, secs, key, v0, v1, u_per_m=1 / 12.0, facing=toward_field, min_h=0.05):
        run = []
        def flush():
            if len(run) >= 2:
                bot = [self.at(lp, d, a) for lp, (d, a, b) in run]
                top = [self.at(lp, d, b) for lp, (d, a, b) in run]
                ub = [(lp.s * u_per_m, v1) for lp, _ in run]
                ut = [(lp.s * u_per_m, v0) for lp, _ in run]
                m.grid(material, [bot, top], [ub, ut], facing=facing)
        for lp, sec in zip(loop, secs):
            item = sec.get(key)
            if item is None or item[2] - item[1] < min_h:
                flush()
                run = []
                continue
            run.append((lp, item))
        flush()

    def _ledge(self, m, material, loop, secs, key, facing):
        """Horizontal strips (per loop point (d0, d1, y)); consecutive points with the key form one grid."""
        run = []
        def flush():
            if len(run) >= 2:
                inner = [self.at(lp, d0, y) for lp, (d0, d1, y) in run]
                outer = [self.at(lp, d1, y) for lp, (d0, d1, y) in run]
                ui = [(lp.s / 8.0, 0.0) for lp, _ in run]
                uo = [(lp.s / 8.0, 0.3) for lp, _ in run]
                m.grid(material, [inner, outer], [ui, uo], facing=facing)
        for lp, sec in zip(loop, secs):
            item = sec.get(key)
            if item is None or abs(item[1] - item[0]) < 0.02:
                flush()
                run = []
                continue
            run.append((lp, item))
        flush()

    def _bowl(self, loop, secs):
        p = self.p
        m = self.mesh("ml_bowl_lower")
        # the field wall itself is laid by _wall (panels of the venue's wall atlas)
        wall = p["wall"]["height"]
        # ledge from the wall top to the first row
        m.grid("cement01", [[(lp.x, wall, lp.z) for lp in loop],
                            [self.at(lp, *sec["lower"][0]) for lp, sec in zip(loop, secs)]],
               [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.15) for lp in loop]], facing=up_toward_field)
        lower = [sec["lower"] for sec in secs]
        self._band(m, "LIGHT_suite01", loop, secs, "field_club", 0.30, 0.62)
        self._rows_surface(m, "seat01", loop, lower, 2)
        self._crowd(m, loop, lower)
        self._portals(m, loop, secs, "lower", self.p["portals"]["lower_row"])
        # back of the lower bowl up to the ribbon (a short concrete wall) and the 360 ribbon
        m2 = self.mesh("ml_bowl_mid")
        self._band(m2, "wall03", loop, secs, "ribbon", 0.0, 1.0, u_per_m=1 / 4.0)
        self._band(m2, "LIGHT_suite01", loop, secs, "suite3", 0.08, 0.62)
        self._band(m2, "wall03", loop, secs, "club_fascia", 0.0, 1.0, u_per_m=1 / 4.0)
        self._ledge(m2, "cement01", loop, secs, "suite3_floor", up)
        self._ledge(m2, "roof01", loop, secs, "suite3_ceiling", down)
        mid = [sec["mid"] for sec in secs]
        self._rows_surface(m2, "seat02", loop, mid, 2)
        self._crowd(m2, loop, mid)
        # the walls between the 200 level and the 300 level front: suites on the sidelines, a dark club band
        # behind the boards at the ends
        m3 = self.mesh("ml_bowl_upper")
        self._band(m3, "LIGHT_suite01", loop, secs, "suite5", 0.05, 0.36)
        self._band(m3, "LIGHT_suite01", loop, secs, "suite6", 0.36, 0.66)
        self._ledge(m3, "cement01", loop, secs, "suites_floor", up)
        self._band(m3, "roof01", loop, secs, "suites_top", 0.55, 0.75, u_per_m=1 / 10.0)
        self._band(m3, "suite03", loop, secs, "mid_back", 0.0, 0.42, u_per_m=1 / 16.0)
        self._band(m3, "wall03", loop, secs, "upper_fascia", 0.0, 1.0, u_per_m=1 / 4.0)
        # soffit under the 300 level
        m3.grid("roof01", [[self.at(lp, sec["soffit"][0], sec["soffit"][2] - 0.02) for lp, sec in zip(loop, secs)],
                           [self.at(lp, sec["soffit"][1], sec["soffit"][2] - 0.02) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 10, 0.0) for lp in loop], [(lp.s / 10, 0.5) for lp in loop]], facing=down)
        upper = [sec["upper"] for sec in secs]
        self._rows_surface(m3, "seat01", loop, upper, 2)
        self._crowd(m3, loop, upper)
        self._portals(m3, loop, secs, "upper", self.p["portals"]["upper_row"])
        # rim: back wall above the top row and the walkway behind it
        m4 = self.mesh("ml_rim")
        m4.grid("suite01", [[self.at(lp, sec["rim"][0], sec["rim"][1]) for lp, sec in zip(loop, secs)],
                            [self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 12, 0.97) for lp in loop], [(lp.s / 12, 0.84) for lp in loop]], facing=toward_field)
        m4.grid("cement01", [[self.at(lp, sec["rim"][0], sec["rim"][2]) for lp, sec in zip(loop, secs)],
                             [self.at(lp, sec["rim"][3], sec["rim"][2]) for lp, sec in zip(loop, secs)]],
                [[(lp.s / 8, 0) for lp in loop], [(lp.s / 8, 0.4) for lp in loop]], facing=up)

    def _portals(self, m, loop, secs, key, row):
        """Vomitory openings at every other aisle (aisles fall every 13 m of the row, where the seat texture has
        its stairs): a dark opening standing at the front of ``row`` with a concrete lintel above it."""
        q = self.p["portals"]
        every = q["every_m"]
        for a, b, sa, sb_ in zip(loop[:-1], loop[1:], secs[:-1], secs[1:]):
            k0, k1 = math.floor(a.s / every), math.floor(b.s / every)
            if k1 == k0:
                continue
            s_at = k1 * every
            t = (s_at - a.s) / max(b.s - a.s, 1e-9)
            pa, pb = sa[key], sb_[key]
            if row >= len(pa) - 1 or row >= len(pb) - 1:
                continue
            d = pa[row][0] * (1 - t) + pb[row][0] * t
            y = pa[row][1] * (1 - t) + pb[row][1] * t
            x0 = a.x * (1 - t) + b.x * t
            z0 = a.z * (1 - t) + b.z * t
            nx, nz = a.nx * (1 - t) + b.nx * t, a.nz * (1 - t) + b.nz * t
            nn = math.hypot(nx, nz)
            nx, nz = nx / nn, nz / nn
            c = np.array([x0 + nx * (d - 0.05), y, z0 + nz * (d - 0.05)])
            tv = np.array([-nz, 0.0, nx]) * (q["width"] / 2)
            h = np.array([0.0, q["height"], 0.0])
            n = np.array([nx, 0.0, nz])
            m.quad("ml_portal", c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
                   facing=lambda p, n=n: -n)

    def _signs(self, loop, secs):
        """METLIFE STADIUM on the east ring (facing the field) and on the facade tops (outward), the MetLife mark
        at each end of the board band (facing the field) and on the north and south facades (outward)."""
        m = self.meshes.setdefault("ml_signs", Mesh("ml_signs"))
        L = self.p["letters"]
        G = self.p["logos"]
        # ring letters: the rim point on the east sideline centre (normal -x)
        east = min(range(len(loop)), key=lambda i: math.pow(loop[i].nx + 1, 2) + math.pow(loop[i].z, 2))
        lp, sec = loop[east], secs[east]
        ring = self.p["ring"]
        d_in = sec["rim"][0] + 1.0 - ring["depth"] * 0.55
        y0 = sec["rim"][2] + ring["post"] - 1.2          # hung on the truss, as the Jets2 photo shows them
        self._sign_quad(m, "ml_letters", lp, d_in, y0, L["ring_width"], L["ring_height"], toward=True)
        # the MetLife mark between the boards at each end
        for zs in (1, -1):
            i = min(range(len(loop)), key=lambda i: math.pow(loop[i].nz - zs, 2) + math.pow(loop[i].x, 2))
            lp, sec = loop[i], secs[i]
            d = self.p["upper"]["front_depth"] - 1.1
            self._sign_quad(m, "ml_logo", lp, d, G["end_y"] - G["end_height"], G["end_width"], G["end_height"],
                            toward=True)
        # facade tops: letters west and east (outward), the mark north and south
        top = self.p["facade"]["band_top"]
        for i_side, (px, pz, mat, w, hgt) in enumerate(((1, 0, "ml_letters", L["facade_width"], L["facade_height"]),
                                                        (-1, 0, "ml_letters", L["facade_width"], L["facade_height"]),
                                                        (0, 1, "ml_logo", G["facade_width"], G["facade_height"]),
                                                        (0, -1, "ml_logo", G["facade_width"], G["facade_height"]))):
            p, n = self._facade_point(px, pz)
            c = np.array([p[0] - n[0] * 1.5, top, p[1] - n[1] * 1.5])
            nn = np.array([n[0], 0.0, n[1]])
            tv = np.array([n[1], 0.0, -n[0]]) * (w / 2)       # the viewer's right, seen from outside
            h = np.array([0.0, hgt, 0.0])
            m.quad(mat, c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda q, nn=nn: nn)
            if mat == "ml_letters":
                self._letters_back(m, c - tv, c + tv, c + tv + h, c - tv + h, nn)
            if mat == "ml_logo":
                # the sign box's back, so the bowl does not see the mark mirrored through the ring (the letters
                # stay open: the Jets2 photo shows them reversed from inside)
                b = -nn * 0.35
                m.quad("wall03", c - tv + b, c + tv + b, c + tv + h + b, c - tv + h + b, (0, 1), (1, 1), (1, 0), (0, 0),
                       facing=lambda q, nn=nn: -nn)

    #: gate canopy sign cells in the skin's banner04 atlas (u0, v0, u1, v1): MetLife, verizon, Bud Light, METLIFE
    #: STADIUM (the atlas holds these in both venues)
    GATE_SIGN_NAMES = {"MetLifeGate": "metlife_white", "VerizonGate": "verizon", "BudLightGate": "bud_light",
                       "PepsiGate": "pepsi", "HCLTechGate": "hcltech"}

    def _gates(self):
        """The five entrance canopies of the plaza (OpenStreetMap gate buildings): a dark block 6 m tall along
        each footprint's long axis, its sponsor sign on the side facing away from the stadium."""
        gates = footprint().get("gates", {})
        m = self.meshes.setdefault("ml_gates", Mesh("ml_gates"))
        for name, poly in gates.items():
            pts = np.array([[c, a] for a, c in poly], float)          # (x, z)
            c = pts.mean(0)
            u, sv, vt = np.linalg.svd(pts - c)
            axis = vt[0] / math.np_norm(vt[0])
            perp = np.array([-axis[1], axis[0]])
            if math.np_dot(perp, c) < 0:
                perp = -perp                                            # the side away from the stadium
            along = math.np_matmul(pts - c, axis)
            across = math.np_matmul(pts - c, perp)
            hl, hw = (along.max() - along.min()) / 2, max((across.max() - across.min()) / 2, 3.0)
            mid = c + axis * (along.max() + along.min()) / 2 + perp * (across.max() + across.min()) / 2
            h = 6.0
            U = np.array([axis[0], 0.0, axis[1]]); Wv = np.array([perp[0], 0.0, perp[1]])
            m.box("wall03", (mid[0], h / 2, mid[1]), (U, (0, 1, 0), Wv), (hl, h / 2, hw))
            u0, v0, u1, v1 = self.sign_cell(self.GATE_SIGN_NAMES.get(name, "metlife_white"))
            face = np.array([mid[0], 0.0, mid[1]]) + Wv * (hw + 0.08)
            sy0, sy1 = h - 3.2, h - 0.4
            sw = min(hl * 0.9, (sy1 - sy0) * 4.0)                      # half width: the 8:1 cell, never stretched
            right = np.cross(-Wv, (0.0, 1.0, 0.0))                         # the viewer's right, seen from outside
            a = face - right * sw + np.array([0, sy0, 0]); b = face + right * sw + np.array([0, sy0, 0])
            cc = face + right * sw + np.array([0, sy1, 0]); d = face - right * sw + np.array([0, sy1, 0])
            m.quad("ml_signs", a, b, cc, d, (u0, v1), (u1, v1), (u1, v0), (u0, v0), facing=lambda p, w=Wv: w)
            # two entry pylons flank each gate (ten in all, 54 x 20 ft: 16.5 x 6.1 m; Wikipedia), dark LED columns
            # with the team mark, the club slogan and the MetLife mark down the outer face
            for side in (-1.0, 1.0):
                pc = mid + axis * side * (hl + 5.0) + perp * 2.0
                base = np.array([pc[0], 0.2, pc[1]])
                m.box("wall03", base + np.array([0, 8.25, 0]), (U, (0, 1, 0), Wv), (3.05, 8.25, 0.6))
                face = base + Wv * 0.62
                for k, (cu0, cv0, cu1, cv1) in enumerate(self.sign_cell(n) for n in ("team_logo", "slogan", "metlife_white")):
                    y1 = 15.6 - k * 2.1; y0 = y1 - 5.8 / 8.0                 # 5.8 m wide: the 8:1 cell
                    a = face - right * 2.9 + np.array([0, y0, 0]); b = face + right * 2.9 + np.array([0, y0, 0])
                    cc = face + right * 2.9 + np.array([0, y1, 0]); d = face - right * 2.9 + np.array([0, y1, 0])
                    m.quad("ml_signs", a, b, cc, d, (cu0, cv1), (cu1, cv1), (cu1, cv0), (cu0, cv0),
                           facing=lambda p, w=Wv: w)

    def _sign_quad(self, m, material, lp, d, y0, width, height, toward=True):
        c = np.array([lp.x + lp.nx * d, y0, lp.z + lp.nz * d])
        n = np.array([lp.nx, 0.0, lp.nz])
        tv = np.array([-lp.nz, 0.0, lp.nx]) * (width / 2)
        h = np.array([0.0, height, 0.0])
        face = -n if toward else n
        m.quad(material, c - tv, c + tv, c + tv + h, c - tv + h, (0, 1), (1, 1), (1, 0), (0, 0),
               facing=lambda q, f=face: f)
        if material == "ml_letters":
            self._letters_back(m, c - tv, c + tv, c + tv + h, c - tv + h, face)

    def _letters_back(self, m, a, b, cc, d, face):
        """Channel letters: the engine draws the alpha-tested sign material from both sides, so seen from behind the
        face would read mirrored. A copy 15 cm behind, same texture and silhouette but lit dark, is what the back
        shows (the Jets2 photo: the reversed shapes of the outward letters, dark, seen from inside the bowl); from
        the front it sits exactly behind the lit letters."""
        o = -np.asarray(face, float) * 0.15
        m.quad("ml_letters_back", a + o, b + o, cc + o, d + o, (0, 1), (1, 1), (1, 0), (0, 0),
               facing=lambda q, f=face: -np.asarray(f, float))

    def _facade_point(self, px, pz):
        """Point of the facade outline in the direction (px, pz) and its outward normal (2D)."""
        ring = self.facade_ring
        a = math.atan2(pz, px)
        pts = np.array([p for p, u in ring])
        ang = math.np_arctan2(pts[:, 1], pts[:, 0])
        i = int(np.argmin(np.abs(((ang - a + math.pi) % (2 * math.pi)) - math.pi)))
        j = (i + 1) % len(pts)
        t = pts[j] - pts[i]
        n = np.array([t[1], -t[0]])
        n = n / math.np_norm(n)
        if math.np_dot(n, pts[i]) < 0:
            n = -n
        return pts[i], n

    # -- corner boards (two per end, between the 200 level and the 300 level) --------------------------------
    #: the live feed's window in the jumbo_tron render target (640x448 of 1024x512; PROVED OFFLINE from the retail
    #: s18 screens, u 0-0.625 and v 0.2022-0.6732, and u6's s23/s24 screens): u 0 to 0.625, v 0 to 0.875
    FEED_U, FEED_V = 0.625, 0.875
    PANEL_W = 11.5                      # the game-information panel on the board's inner side (tools art PANEL_M)
    #: the sponsor headers over the boards, from the signage atlas, by board (zs, xs): pepsi and BUD LIGHT at the
    #: north end, HCLTech and verizon at the south end (the 2022-2024 photos)
    HEADER_SIGN = {(1, 1): "pepsi", (1, -1): "bud_light", (-1, -1): "hcltech", (-1, 1): "verizon"}

    def _boards(self, loop, secs):
        """The four corner boards, 35 x 9.1 m, as they look on game day: an 11.5 m game-information panel on the
        inner side (the game's own score, clock and play-clock digits sit on its slots) and a 23.5 m live-video
        window. The window shows the game's jumbo_tron feed cropped to the window's own aspect: all 640 columns of
        the feed and the middle rows that fit, so the feed fills the whole window and nothing is stretched."""
        q = self.p["boards"]
        m = self.mesh("ml_boards")
        wall_d = self.p["upper"]["front_depth"] - 1.2      # board face a little behind the 300 level front
        L = self.p["loop"]["L"]
        self.board_quads = []
        self.board_frames = []
        for zs in (1, -1):
            for xs in (1, -1):
                cx = xs * q["centre_x"]
                # the board face follows the plan at its centre: find the loop normal there
                best = min(loop, key=lambda lp: math.pow(lp.x - cx, 2) + math.pow((lp.z - zs * L) * 0.3, 2)
                           + (0 if lp.nz * zs > 0 else 1e9))
                nx, nz = best.nx, best.nz
                cxp, czp = best.x + nx * wall_d, best.z + nz * wall_d
                t = np.array([-nz, 0.0, nx])            # along the face, left to right as seen from the field
                n = np.array([nx, 0.0, nz])             # outward (away from the field)
                y0, y1 = q["bottom_y"], q["bottom_y"] + q["height"]
                c = np.array([cxp, 0.0, czp])
                hw = q["width"] / 2
                face = -n * 0.25
                up = np.array([0.0, 1.0, 0.0])
                left, right = c - t * hw, c + t * hw
                panel_left = abs(left[0]) < abs(right[0])       # the panel on the inner side (toward x = 0)
                if panel_left:
                    p0, p1, v0, v1 = left, left + t * self.PANEL_W, left + t * self.PANEL_W, right
                else:
                    v0, v1, p0, p1 = left, right - t * self.PANEL_W, right - t * self.PANEL_W, right
                vw = float(math.np_norm(v1 - v0))
                rows = 640.0 * q["height"] / vw                 # feed rows that fit the window's aspect
                vt = (448.0 - rows) / 2.0 / 512.0
                vb = vt + rows / 512.0
                quad = lambda a0, a1, h0, h1: (a0 + up * h0 + face, a1 + up * h0 + face, a1 + up * h1 + face, a0 + up * h1 + face)
                va, vb_, vc, vd = quad(v0, v1, y0, y1)
                m.quad("jumbo_tron", va, vb_, vc, vd, (0, vb), (self.FEED_U, vb), (self.FEED_U, vt), (0, vt),
                       facing=lambda p, n=n: -n)
                pa, pb, pc, pd = quad(p0, p1, y0, y1)
                m.quad("LIGHT_ml_board_panel", pa, pb, pc, pd, (0, 1), (1, 1), (1, 0), (0, 0), facing=lambda p, n=n: -n)
                m.box("wall03", c + np.array([0, (y0 + y1) / 2, 0]) + n * 0.6, (t, (0, 1, 0), n), (hw + 0.6, q["height"] / 2 + 0.6, 0.6))
                hy0, hy1 = y1 + 0.6, y1 + 0.6 + q["header"]
                hh = q["header"] * 8.0 / 2.0                    # the header cell is 8:1
                u0, hv0, u1, hv1 = self.sign_cell(self.HEADER_SIGN[(zs, xs)])
                m.quad("ml_signs", c - t * hh + up * hy0 - n * 0.3, c + t * hh + up * hy0 - n * 0.3,
                       c + t * hh + up * hy1 - n * 0.3, c - t * hh + up * hy1 - n * 0.3,
                       (u0, hv1), (u1, hv1), (u1, hv0), (u0, hv0), facing=lambda p, n=n: -n)
                m.box("wall03", c + up * (hy0 + hy1) / 2 + n * 0.05, (t, (0, 1, 0), n), (hh + 0.3, q["header"] / 2 + 0.3, 0.3))
                self.board_quads.append((va, vb_, vc, vd))
                # the panel's top-left corner on the face, for the digit slots
                self.board_frames.append(dict(centre=c, t=t, n=n, y0=y0, xs=xs, zs=zs,
                                              panel_top_left=p0 + up * y1 + face))
                self.markers.setdefault("jumbo", []).append(tuple(c + np.array([0, (y0 + y1) / 2, 0]) - n * 0.5))

    # -- Solar Ring (47 frames on the rim, cantilevered over the top rows) -----------------------------------
    def _ring(self, loop, secs):
        q = self.p["ring"]
        m = self.mesh("ml_ring")
        # rim polyline: the walkway line behind the top row
        rim = [(np.array(self.at(lp, sec["rim"][0] + 1.0, sec["rim"][2])), lp) for lp, sec in zip(loop, secs)]
        S = loop[-1].s
        pts = np.array([r[0] for r in rim])
        seg = math.np_norm(np.diff(pts, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        total = cum[-1]
        def sample(u):
            u = u % total
            i = int(np.searchsorted(cum, u, side="right") - 1)
            i = min(i, len(seg) - 1)
            t = (u - cum[i]) / max(seg[i], 1e-9)
            p = pts[i] * (1 - t) + pts[i + 1] * t
            tang = (pts[i + 1] - pts[i]) / max(seg[i], 1e-9)
            return p, tang
        n = q["frames"]
        length = total / n
        self.ring_lights = []
        for k in range(n):
            u0, u1 = k * length + q["gap"] / 2, (k + 1) * length - q["gap"] / 2
            p0, t0 = sample(u0)
            p1, t1 = sample(u1)
            pm, tm = sample((u0 + u1) / 2)
            inward = np.cross(np.array([0, 1.0, 0]), tm)    # left of the travel direction (counter-clockwise loop) = toward the field
            inward = inward / math.np_norm(inward)
            if math.np_dot(inward, -np.array([pm[0], 0, pm[2]])) < 0:
                inward = -inward
            base_y = pm[1]
            post = q["post"]
            # panel: from the outer edge (over the walkway, at base+post) to the inner edge (over the seats, higher)
            o0 = p0 + np.array([0, post, 0]); o1 = p1 + np.array([0, post, 0])
            i0 = o0 + inward * q["depth"] + np.array([0, q["rise"], 0])
            i1 = o1 + inward * q["depth"] + np.array([0, q["rise"], 0])
            m.quad("ml_ring_panel", o0, o1, i1, i0, (0, 1), (2, 1), (2, 0), (0, 0), facing=up)
            m.quad("ml_ring_panel", o0, i0, i1, o1, (0, 0), (2, 0), (2, 1), (0, 1), facing=down)
            # the steel: two posts and the front beam (thin boxes)
            for pp, tt in ((p0, t0), (p1, t1)):
                c = pp + np.array([0, post / 2, 0])
                m.box("cement01", c, (tt, (0, 1, 0), np.cross(tt, (0, 1, 0))), (0.35, post / 2, 0.35))
            beam_c = (i0 + i1) / 2 - np.array([0, 0.35, 0])
            m.box("cement01", beam_c, (tm, (0, 1, 0), inward), (math.np_norm(i1 - i0) / 2, 0.35, 0.3))
            # LED strip along the inner edge (lit in team colour at night)
            m.quad("LIGHT_ml_ringled", i0 - np.array([0, 0.7, 0]) + inward * 0.32, i1 - np.array([0, 0.7, 0]) + inward * 0.32,
                   i1 + inward * 0.32, i0 + inward * 0.32, (0, 1), (4, 1), (4, 0), (0, 0), facing=lambda p, w=inward: w)
            self.ring_lights.append(tuple((i0 + i1) / 2 + np.array([0, 1.5, 0])))

    # -- facade on the OpenStreetMap outline ---------------------------------------------------------------
    def facade_outline(self, step=4.0):
        q = self.p["facade"]
        poly = np.array(footprint()["outline"])               # (along, across) = (z, x) in game terms
        pts = np.stack([poly[:, 1], poly[:, 0]], axis=1)     # (x, z)
        if np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        # order counter-clockwise by angle, starting at the +x axis like the plan loop
        ang = math.np_arctan2(pts[:, 1], pts[:, 0])
        start = int(np.argmin(np.abs(ang)))
        pts = np.roll(pts, -start, axis=0)
        if (math.atan2(pts[1][1], pts[1][0]) - math.atan2(pts[0][1], pts[0][0])) % (2 * math.pi) > math.pi:
            pts = np.vstack([pts[:1], pts[1:][::-1]])
        closed = np.vstack([pts, pts[:1]])
        seg = math.np_norm(np.diff(closed, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])
        total = cum[-1]
        N = int(total / step)
        ring = []
        for k in range(N + 1):
            u = total * k / N
            i = min(int(np.searchsorted(cum, u, side="right") - 1), len(seg) - 1)
            t = (u - cum[i]) / seg[i]
            ring.append((closed[i] * (1 - t) + closed[i + 1] * t, u))
        return ring

    def _facade(self, loop, secs, parts=8):
        q = self.p["facade"]
        ring = self.facade_outline()
        self.facade_ring = ring
        rim = np.array([self.at(lp, sec["rim"][3], sec["rim"][2]) for lp, sec in zip(loop, secs)])
        rim_ang = math.np_arctan2(rim[:, 2], rim[:, 0])
        out = lambda p: -toward_field(p)
        rows = [(0.0, "ml_limestone", q["base"], 1 / 6.0, 1 / 6.0),
                (q["base"], "ml_louvre", q["louvre_top"], 1 / 8.0, 1 / 8.0),
                (q["louvre_top"], "cement01", q["band_top"], 1 / 8.0, 1 / 8.0)]
        angs = [(math.atan2(p[1], p[0]) + 2 * math.pi) % (2 * math.pi) for p, u in ring]
        for k in range(parts):
            lo, hi = 2 * math.pi * k / parts, 2 * math.pi * (k + 1) / parts
            idx = [i for i, a in enumerate(angs) if lo <= a < hi]
            if not idx:
                continue
            idx = idx + [(idx[-1] + 1) % len(ring)]
            chunk = [ring[i] for i in idx]
            m = self.meshes.setdefault(f"ml_facade{k:02d}", Mesh(f"ml_facade{k:02d}"))
            for y0, mat, y1, uu, vv in rows:
                m.grid(mat, [[(p[0], y0, p[1]) for p, u in chunk], [(p[0], y1, p[1]) for p, u in chunk]],
                       [[(u * uu, y1 * vv) for p, u in chunk], [(u * uu, y0 * vv) for p, u in chunk]], facing=out)
            outer, inner, uo, ui = [], [], [], []
            for p, u in chunk:
                a = math.atan2(p[1], p[0])
                j = int(np.argmin(np.abs(((rim_ang - a + math.pi) % (2 * math.pi)) - math.pi)))
                outer.append((p[0], q["band_top"], p[1]))
                inner.append(tuple(rim[j]))
                uo.append((u / 8, 0)); ui.append((u / 8, 0.6))
            m.grid("cement01", [outer, inner], [uo, ui], facing=up)
            # the plaza: concrete from the facade out past the gate line (58 m on the MetLife Gate side, 32 m on
            # the east), 0.2 m above the retail lot so the parked cars stop at its edge
            base, edge, ub, ue = [], [], [], []
            for p, u in chunk:
                rr = math.hypot(p[0], p[1])
                d = 32.0 + 26.0 * max(0.0, p[0] / rr)
                base.append((p[0], 0.2, p[1])); edge.append((p[0] * (rr + d) / rr, 0.2, p[1] * (rr + d) / rr))
                ub.append((u / 8, 0.0)); ue.append((u / 8, d / 8))
            m.grid("cement01", [base, edge], [ub, ue], facing=up)


def build(venue="s18", params=None):
    return MetLife(params, venue).build()




# ------------------------------------------------------------------------------------------------ assembly

KEEP = {'sideline_home_north', 'sideline_home_south', 'sideline_away_north', 'sideline_away_south',
        'pyG001', 'pyG002', 'pyG003', 'pyG004', 'group8', 'group9', 'group11', 'group111', 'digits'}
KEEP_MATERIALS_BY_CODE = {'crowd', 'jumbo_tron'}     # looked up by name in the executable

# baked vertex light (grey level) per material: day, afternoon, night (retail medians, PROVED OFFLINE stats)
BASE = {
    'seat01': (168, 142, 132), 'seat02': (182, 150, 126), 'crowd': (212, 158, 129),
    'LIGHT_suite01': (200, 165, 255), 'LIGHT_suite03': (170, 150, 255), 'suite03': (173, 150, 130),
    'banner01': (242, 212, 200), 'banner02': (250, 219, 205), 'banner04': (242, 212, 200),
    'roof01': (120, 100, 70), 'cement01': (185, 140, 95), 'suite01': (201, 161, 110),
    'wall01': (209, 184, 188), 'wall03': (185, 165, 150), 'jumbo_tron': (255, 255, 255),
    'ml_louvre': (205, 170, 110), 'ml_limestone': (205, 170, 120), 'ml_ring_panel': (215, 180, 110),
    'LIGHT_ml_ringled': (170, 150, 255), 'LIGHT_ml_louvre': (205, 170, 255),
    'ml_letters': (235, 205, 230), 'ml_logo': (240, 215, 250), 'ml_portal': (160, 135, 120),
    'ml_signs': (238, 215, 250), 'ml_letters_back': (46, 40, 30), 'ml_wall': (209, 184, 188),
    'ml_wall_signs': (209, 184, 188),
    'LIGHT_ml_board_panel': (238, 222, 255),
}
SUN = {'d': (0.25, 0.9, 0.35), 'a': (-0.55, 0.55, 0.62), 'n': None}
TINT = {'d': (1.0, 1.0, 1.0), 'a': (1.0, 0.93, 0.86), 'n': (0.97, 0.99, 1.03)}
TEAM = {'s18': (1, 60, 255), 's19': (18, 170, 90)}      # Giants blue, Jets green (LED)


def overhang_occlusion(P, params=PARAMS):
    """Sky visibility under the 300 level's overhang (1 in the open, down to about 0.45 deep under it).

    The 300 level's front edge runs at a constant depth and height around the bowl (upper.front_depth, front_y);
    a point behind and below it sees the sky only above the angle to that edge. Depth is the signed distance to
    the field-wall line (a rounded rectangle), so the rule holds on the straights and in the corners alike.
    """
    q = params["loop"]
    u = params["upper"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    qx = np.abs(x) - (q["W"] - q["R"])
    qz = np.abs(z) - (q["L"] - q["R"])
    d = math.np_hypot(np.maximum(qx, 0), np.maximum(qz, 0)) + np.minimum(np.maximum(qx, qz), 0) - q["R"]
    df, fy = u["front_depth"], u["front_y"]
    under = (d > df - 0.5) & (y < fy - 0.05)
    theta = np.degrees(math.np_arctan2(np.maximum(fy - y, 0.0), np.maximum(d - df, 1e-3)))
    vis = np.where(under, 0.45 + 0.55 * np.clip(theta / 90.0, 0.0, 1.0), 1.0)
    return vis


def light(mat, P, N, tod, occlusion=None):
    base = BASE.get(mat, (180, 150, 120))[{'d': 0, 'a': 1, 'n': 2}[tod]]
    out = np.zeros((len(P), 4), np.uint8)
    if tod == 'n' or mat.startswith('LIGHT_') and tod == 'n':
        f = np.full(len(P), 1.0)
    else:
        sun = np.array(SUN[tod])
        s = sun / math.np_norm(sun)
        nd = np.clip(math.np_matmul(N, s), 0, 1)
        f = (0.82 + 0.22 * nd) if tod == 'd' else (0.70 + 0.45 * nd)
    if occlusion is not None and not (mat.startswith('LIGHT_') and tod == 'n'):
        f = f * occlusion
    if (mat.startswith('LIGHT_') or mat == 'ml_louvre') and tod == 'n':
        f = np.full(len(P), 1.0)              # self-lit at night (the facade glass glows in team colour)
        base = 255
    t = TINT[tod]
    for k in range(3):
        out[:, k] = np.clip(base * f * t[k], 0, 255)
    out[:, 3] = 255
    return out


def team_led(venue, tod):
    if tod != 'n':
        return np.full((8, 32, 4), (205, 210, 220, 255), np.uint8)
    c = TEAM[venue]
    a = np.zeros((8, 32, 4), np.uint8); a[..., :3] = c; a[..., 3] = 255
    return a


def louvre_night(venue):
    base = np.asarray(Image.open(ART_DIR / 'ml_louvre.png').convert('RGB')).astype(float)
    c = np.array(TEAM[venue], float)
    lum = base.mean(2, keepdims=True)
    dark = lum < 90                                  # the glass between the fins glows in team colour
    out = np.where(dark, c * 0.85 + 20, base * 0.35)
    a = np.zeros(base.shape[:2] + (4,), np.uint8); a[..., :3] = np.clip(out, 0, 255); a[..., 3] = 255
    return a


def adjust_kept(sc, model, mat_ix):
    # (b76-u5b) the retail field-level banners (fan and corporate banners hung on the wall) are gone: MetLife's wall
    # carries the teams' own wraps, which the model lays as wall panels
    # digits (b76-u5b): the game's own score, clock and play-clock digit quads on every board's panel slots (four
    # boards; the retail shape had two scoreboards), plus the two play clocks on the end walls. The shape is rebuilt
    # with the same name, node, vertex format and digit materials (the executable finds the materials by name and
    # draws each digit into its own 32x32 texture; the quads' UVs stay 0..1).
    from mod_editor.core import nfl2k5_scne_builder as _sb
    shp = sc.shape('digits')
    slots = [("digit_home_score_L", 7.70, 0.70, 8.80, 2.40), ("digit_home_score_R", 8.95, 0.70, 10.05, 2.40),
             ("digit_away_score_L", 7.70, 2.90, 8.80, 4.60), ("digit_away_score_R", 8.95, 2.90, 10.05, 4.60),
             ("digit_clock_1", 5.95, 5.10, 7.05, 6.80), ("digit_clock_2", 7.15, 5.10, 8.25, 6.80),
             ("digit_clock_3", 8.65, 5.10, 9.75, 6.80), ("digit_clock_4", 9.85, 5.10, 10.95, 6.80),
             ("digit_playclock_L", 7.70, 7.30, 8.80, 9.00), ("digit_playclock_R", 8.95, 7.30, 10.05, 9.00)]
    quads = {}
    up = np.array([0.0, 1.0, 0.0])
    for b in model.board_frames:
        tl, tvec, nvec = b['panel_top_left'], b['t'], b['n']
        for name, x0, y0, x1, y1 in slots:
            o = -nvec * 0.06
            bl = tl + tvec * x0 - up * y1 + o
            br = tl + tvec * x1 - up * y1 + o
            tr = tl + tvec * x1 - up * y0 + o
            tl_ = tl + tvec * x0 - up * y0 + o
            quads.setdefault(name, []).append((bl, br, tr, tl_))
    L = model.p['loop']['L']
    for zs in (1, -1):
        for name, side in (('digit_playclock_L', -1), ('digit_playclock_R', 1)):
            tvec = np.array([-zs, 0.0, 0.0])
            c = np.array([-side * 0.9 * zs, 2.6, zs * (L - 0.06)])
            bl = c - tvec * 0.75 - up * 1.1; br = c + tvec * 0.75 - up * 1.1
            quads.setdefault(name, []).append((bl, br, br + up * 2.2, bl + up * 2.2))
    positions, colours, uvs, subs = [], [], [], []
    for sub in shp.submeshes:
        name = sc.materials[sub.material].name
        if name not in quads:
            continue
        strips = []
        for bl, br, tr, tl_ in quads[name]:
            k = len(positions)
            for p, uv in ((bl, (0.0, 1.0)), (tl_, (0.0, 0.0)), (br, (1.0, 1.0)), (tr, (1.0, 0.0))):
                positions.append(tuple(float(v) * 100.0 for v in p))
                colours.append((255, 255, 255, 255))
                uvs.append(uv)
            strips.append([k, k + 1, k + 2, k + 3])
        subs.append((sub.material, _sb.encode_words(_sb.TRIANGLE_STRIP, _sb.strips_to_indices(strips))))
    new = _sb.static_shape(shp, 'digits', positions, colours, uvs, subs, uv_constant=(0.5, 0.5, 0.5, 0.5))
    sc.shapes[sc.shapes.index(shp)] = new


def _rgba(path):
    path = official.resolve_path(path)
    return np.asarray(Image.open(path).convert('RGBA'))


def build_scene(skin_bundle, filename, model):
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(skin_bundle)['stadium']
    rec, dec = ml._scene(skin_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape = sc.shape('group62')
    tmpl_node = next(n for n in sc.nodes if n.shape_name == 'group62')
    tex_tmpl = sc.textures[sc.materials[sc.material_index('cement01')].texture]
    # 1. drop every retail shape the model replaces
    for s in [s.name for s in sc.shapes]:
        if s not in KEEP:
            sc.remove_shape(s)
    # 2. new textures and materials
    newtex = {
        'ml_louvre': _rgba(ART_DIR / 'ml_louvre.png') if tod != 'n' else louvre_night(venue),
        'ml_limestone': _rgba(ART_DIR / 'ml_limestone.png'),
        'ml_ring_panel': _rgba(ART_DIR / 'ml_ring_panel.png'),
        'LIGHT_ml_ringled': team_led(venue, tod),
        'ml_letters': _rgba(ART_DIR / 'ml_letters.png'),
        'ml_logo': _rgba(ART_DIR / 'ml_logo.png'),
        'ml_portal': _rgba(ART_DIR / 'ml_portal.png'),
        'ml_signs': _rgba(ART_DIR / f'ml_signs_{venue}.png'),
        'LIGHT_ml_board_panel': _rgba(ART_DIR / f'ml_board_panel_{venue}.png'),
        'ml_wall': _rgba(ART_DIR / f'ml_wall_{venue}.png'),
    }
    # alpha-tested signs clone suite05 (render state hash 0xBF4740BD, alpha flags); others clone opaque retail ones
    templates = {'ml_letters': 'suite05', 'ml_logo': 'suite05', 'ml_wall': 'wall01'}
    for name, arr in newtex.items():
        sc.textures.append(sb.p8_texture(tex_tmpl, arr))
        template = templates.get(name) or ('LIGHT_suite01' if name.startswith('LIGHT_') else 'cement01')
        sc.materials.append(sb.clone_material(sc, template, name, len(sc.textures) - 1))
    # the environment kit's textures and materials (one texture per key; the alpha band clones suite05's state)
    env_tex = env.textures(venue, tod, weather)
    env_ix = {}
    for key, arr in env_tex.items():
        sc.textures.append(sb.p8_texture(tex_tmpl, arr))
        env_ix[key] = len(sc.textures) - 1
    for name, (key, cls) in env.materials(venue).items():
        template = 'suite05' if cls == env.CLASS_ALPHA else 'cement01'
        sc.materials.append(sb.clone_material(sc, template, name, env_ix[key]))
    # the dark backs of the channel letters: the letters texture again, lit dark
    letters_tex = sc.materials[sc.material_index('ml_letters')].texture
    sc.materials.append(sb.clone_material(sc, 'suite05', 'ml_letters_back', letters_tex))
    # the wall's number boxes: the signage atlas again, lit as the wall (b76-u5b)
    signs_tex = sc.materials[sc.material_index('ml_signs')].texture
    sc.materials.append(sb.clone_material(sc, 'wall01', 'ml_wall_signs', signs_tex))
    mat_ix = {m.name: i for i, m in enumerate(sc.materials)}
    # 3. shapes from the model meshes
    for mesh in model.meshes.values():
        if not mesh.P:
            continue
        P = np.array(mesh.P) * 100.0
        N = np.array(mesh.N)
        UV = np.array(mesh.UV)
        C = np.zeros((len(P), 4), np.uint8)
        subs = []
        for mat, strips in mesh.groups.items():
            name = mat
            if name not in mat_ix:
                raise KeyError(f'{filename}: material {name} missing')
            idxs = sorted({i for st in strips for i in st})
            occ = overhang_occlusion(P[idxs] / 100) if mesh.name.startswith('ml_bowl') else None
            if mat.startswith('env_'):
                C[idxs] = env.light(mat, P[idxs] / 100, N[idxs], tod, weather, venue)
            else:
                C[idxs] = light(mat, P[idxs] / 100, N[idxs], tod, occ)
            words = sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(strips))
            subs.append((mat_ix[name], words))
        shape = sb.static_shape(tmpl_shape, mesh.name, [tuple(p) for p in P], [tuple(c) for c in C],
                                [tuple(u) for u in UV], subs)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, mesh.name, mesh.name))
    # 3b. retail pieces that stay but move: field banners onto the new wall, digits onto the boards
    adjust_kept(sc, model, mat_ix)
    # 4. markers: light glows and flares on the ring, jumbotron markers on the boards
    lights = model.ring_lights
    glows = [m for m in sc.markers if m.name.startswith('marker_light')]
    flares = [m for m in sc.markers if 'flare' in m.name]
    for i, m in enumerate(glows):
        p = lights[int(round(i * len(lights) / len(glows))) % len(lights)]
        struct.pack_into('<3f', m.record, 0x10, *(v * 100 for v in p))
    corner_frames = []
    for m, ang in zip(flares, (45, 135, 225, 315)):
        a = math.radians(ang)
        best = min(lights, key=lambda p: (math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi) - math.pi if False else abs(((math.atan2(p[2], p[0]) - a + math.pi) % (2 * math.pi)) - math.pi))
        struct.pack_into('<3f', m.record, 0x10, *(v * 100 for v in best))
    jumbo = [m for m in sc.markers if m.name.startswith('jumboMarker')]
    for m, p in zip(jumbo, model.markers['jumbo']):
        struct.pack_into('<3f', m.record, 0x10, *(v * 100 for v in p))
    # 5. drop materials and textures nothing draws (keeping the ones the executable looks up by name)
    used = {sm.material for s in sc.shapes for sm in s.submeshes}
    keep_m = [i for i, m in enumerate(sc.materials) if i in used or m.name in KEEP_MATERIALS_BY_CODE
              or m.name.startswith('digit_')]
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
    for s in sc.shapes:
        for sm in s.submeshes:
            struct.pack_into('<H', sm.record, 0, remap_m[sm.material])
    return sc




# ------------------------------------------------------------------------------------------------ bundles

def stadium_span(bundle):
    """(offset, span bytes) of the stadium scene chunk of one bundle."""
    c = ml.bundle_scenes(bundle)["stadium"]
    return c.offset, bytes(bundle[c.offset:c.offset + 32 + c.stored_size])


def _cameras_chunk(bundle):
    """(chunk, decoded) of the bundle's intro_cameras scene (the chunk right after the stadium in every variant)."""
    tx = ml._tools()[0]
    for c in tx.parse_chunks(bundle, allow_trailing=True):
        if c.kind != "SCNE":
            continue
        rec, dec = ml._scene(bundle, c)
        if rec.get("name") == "intro_cameras":
            return c, dec
    raise sb.ScneBuildError("bundle has no intro_cameras scene")


def model_bundle(skin_bundle, filename, model=None, *, cameras=True):
    """(bundle bytes, info): the skin bundle with its stadium scene replaced by the model and its intro cameras
    rewritten (same layout); the bundle keeps its size. The cameras chunk follows the stadium chunk directly, so
    when the new camera stream needs more room than its retail span the stadium chunk gives up the bytes."""
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(skin_bundle, filename, model)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    offset, span = stadium_span(skin_bundle)
    cam_chunk, cam_dec = _cameras_chunk(skin_bundle)
    cam_span = bytes(skin_bundle[cam_chunk.offset:cam_chunk.offset + 32 + cam_chunk.stored_size])
    sb.require(cam_chunk.offset == offset + len(span), "intro cameras do not follow the stadium chunk")
    extra = 0
    if cameras:
        new_cam = write_cameras(cam_dec, metlife_shots())
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
    head = ml._tools()[3].unpack_from(span, 0)
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, span, stored=head[1] - extra)
    sb.require(len(chunk) + len(cam_out) == len(span) + len(cam_span), "model chunks escaped their spans")
    out = bytes(skin_bundle[:offset]) + chunk + cam_out + bytes(skin_bundle[cam_chunk.offset + len(cam_span):])
    sb.require(len(out) == len(skin_bundle), "model bundle changed size")
    chunks = tx.parse_chunks(out, allow_trailing=True)
    sb.require([c.kind for c in chunks] == [c.kind for c in tx.parse_chunks(skin_bundle, allow_trailing=True)],
               "model bundle chunk list differs")
    idx = ml.bundle_scenes(skin_bundle)["stadium"].index
    back, _ = tx.decode_chunk(out, chunks[idx])
    sb.require(back == decoded, "model chunk read-back differs")
    back_cam, _ = tx.decode_chunk(out, chunks[cam_chunk.index])
    sb.require(back_cam == new_cam, "intro cameras read-back differs")
    return out, dict(info, shapes=len(sc.shapes), materials=len(sc.materials), textures=len(sc.textures),
                     markers=len(sc.markers), cameras_borrowed=extra, cameras_scratch=cam_info.get("scratch"))


def skin_bundle(retail, filename, retail_dry):
    """The modern_metlife skin applied to one retail bundle (the model's input)."""
    applied, _edits = ml.modern_bundle(retail, filename, retail_dry)
    return applied


def _read_retail(source):
    """{filename: retail bytes} of the eighteen bundles from a retail disc image or extracted folder."""
    out = {}
    with ml._outer_image()(str(source)) as archive:
        entries = ml.metlife_entries(archive)
        sb.require(set(entries) == set(ml.VARIANTS), "MetLife bundles missing from the source")
        for name in ml.VARIANTS:
            e = entries[name]
            out[name] = archive.read(e.virtual_offset, e.size)
    return out


def _one(job):
    name, retail, dry = job
    skin = skin_bundle(retail, name, dry)
    model, info = model_bundle(skin, name)
    return name, skin, model, info


def build_all(source, *, workers=None, progress=None):
    """{filename: (skin bundle, model bundle, info)} for all eighteen variants, compiled in parallel."""
    retail = _read_retail(source)
    jobs = [(n, retail[n], retail[ml.dry_name(n)]) for n in ml.VARIANTS]
    out = {}
    for name, skin, model, info in ml.run_jobs(_one, jobs, workers=workers, progress=progress, label="MetLife model"):
        out[name] = (skin, model, info)
    return out


def apply_lab_disc(disc, source, *, progress=None):
    """Lab: on a disc that carries the skin, write the model's stadium and intro cameras chunks into all eighteen
    bundles.

    Each disc bundle's stadium and cameras chunks must equal the skin's (compiled here from the retail ``source``);
    the model's two chunks occupy exactly the same stretch of the bundle, so only those eighteen stretches change.
    Returns a receipt.
    """
    built = build_all(source, progress=progress)
    receipt = dict(label=LABEL, bundles=[])
    with ml._outer_image()(str(disc), writable=True) as archive:
        entries = ml.metlife_entries(archive)
        sb.require(set(entries) == set(ml.VARIANTS), "MetLife bundles missing on the disc")
        for name in ml.VARIANTS:
            skin, model, info = built[name]
            e = entries[name]
            disc_bundle = archive.read(e.virtual_offset, e.size)
            off, disc_span = stadium_span(disc_bundle)
            skin_off, skin_span = stadium_span(skin)
            sb.require(off == skin_off and disc_span == skin_span, f"{name}: the disc stadium chunk is not the skin's")
            cam_c, _cd = _cameras_chunk(skin)
            stretch_end = cam_c.offset + 32 + cam_c.stored_size
            sb.require(disc_bundle[off:stretch_end] == skin[off:stretch_end], f"{name}: the disc cameras are not retail")
            m_span = bytes(model[off:stretch_end])
            sb.require(len(m_span) == stretch_end - off, f"{name}: model stretch size differs")
            archive.write(e.virtual_offset + off, m_span)
            sb.require(archive.read(e.virtual_offset + off, len(m_span)) == m_span, f"{name}: read-back differs")
            receipt["bundles"].append(dict(name=name, outer=e.index, offset=off, size=len(m_span),
                                           before_sha256=sha(disc_span), after_sha256=sha(m_span),
                                           system=info["system"], video=info["video"], scratch=info["scratch"]))
    from . import nfl2k5_metlife_crowd as crowd
    receipt["crowd"] = crowd.apply_lab_disc(disc)
    return receipt


# ------------------------------------------------------------------------------------------------ build option

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_metlife_model_pins/v1"
BUILD_CAPTION = "Modern MetLife model (experimental)"
HELP_TEXT = (
    "MetLife Stadium as a new model for Giants and Jets home games (every time of day and weather): the real "
    "bowl with its suite levels, the four corner video boards, the Solar Ring, the louvre facade with the "
    "METLIFE STADIUM lettering, a new pregame flyover with an exterior shot, and 2026 superfans in the crowd. "
    "Needs Modern MetLife Stadium (the skin) in the same build. Off in every preset; appearance in game is "
    "unwitnessed."
)
_PINS = None


def _stretch(bundle):
    """(offset, bytes) of the stadium chunk plus the intro cameras chunk that follows it."""
    off, _span = stadium_span(bundle)
    cam, _dec = _cameras_chunk(bundle)
    end = cam.offset + 32 + cam.stored_size
    return off, bytes(bundle[off:end])


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "MetLife model pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported MetLife model pins schema")
    return _PINS


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compile all eighteen bundles and the four crowd outers from a retail source and pin them."""
    from . import nfl2k5_metlife_crowd as crowd
    built = build_all(source, progress=progress)
    bundles = []
    with ml._outer_image()(str(source)) as archive:
        entries = ml.metlife_entries(archive)
        for name in ml.VARIANTS:
            skin, model, info = built[name]
            off, skin_stretch = _stretch(skin)
            m_off, model_stretch = _stretch(model)
            sb.require(m_off == off and len(model_stretch) == len(skin_stretch), f"{name}: stretch differs")
            e = entries[name]
            bundles.append(dict(name=name, outer=e.index, name_id=e.name_id, size=e.size, offset=off,
                                length=len(skin_stretch), skin_sha256=sha(skin_stretch),
                                model_sha256=sha(model_stretch), system=info["system"], video=info["video"],
                                scratch=info["scratch"], shapes=info["shapes"]))
        crowds = []
        for outer in crowd.TARGETS:
            e = archive.entries[outer]
            data = archive.read(e.virtual_offset, e.size)
            new, rec = crowd.crowd_resource(data, outer)
            crowds.append(dict(outer=outer, name_id=e.name_id, size=e.size, offset=rec["offset"], length=rec["size"],
                               retail_sha256=rec["before_sha256"], applied_sha256=rec["after_sha256"]))
    doc = dict(schema=PINS_SCHEMA, label=LABEL, bundles=bundles, crowd=crowds,
               source_note="compiled from the retail archive through the modern_metlife skin")
    Path(out_path).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def image_status(source):
    """retail / skin / applied / mixed / foreign: the eighteen stretches and the four crowd scenes of an image."""
    pins = model_pins()
    states = set()
    with ml._outer_image()(str(source)) as archive:
        for pin in pins["bundles"]:
            if pin["outer"] >= len(archive.entries):
                return "foreign"
            e = archive.entries[pin["outer"]]
            if e.name_id != pin["name_id"] or e.size != pin["size"]:
                return "foreign"
            have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
            states.add("applied" if have == pin["model_sha256"] else "skin" if have == pin["skin_sha256"] else "other")
        crowd_states = set()
        for pin in pins["crowd"]:
            e = archive.entries[pin["outer"]]
            if e.name_id != pin["name_id"] or e.size != pin["size"]:
                return "foreign"
            have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
            crowd_states.add("applied" if have == pin["applied_sha256"] else
                             "retail" if have == pin["retail_sha256"] else "other")
    if states == {"applied"} and crowd_states == {"applied"}:
        return "applied"
    if states == {"skin"} and crowd_states == {"retail"}:
        return "skin"
    if "other" in states:
        # a bundle that is neither the skin nor the model: retail when the skin has not run, else foreign
        return "retail" if ml.image_status(source) == "retail" and crowd_states == {"retail"} else "foreign"
    return "mixed"


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    sb.require(state == ("applied" if enabled else "skin"), f"MetLife model state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False,
                bundles=len(model_pins()["bundles"]), crowd=len(model_pins()["crowd"]))


def repin_colour_rows(colour_receipt, written):
    """Modern colour's image receipt after the model's writes (b76-u5b; u6 found the gap): ``written`` is {bundle
    name: bundle bytes after}. Each written bundle's row is re-pinned (its whole-bundle hash and every site's applied
    hash, as the skin's combined step and the 2026 venues do), so the colour read-back and a rebuild from the output
    disc see the bundles as the grade's own; rows the model did not write stay as they were."""
    from copy import deepcopy
    out = deepcopy(colour_receipt)
    rows = out.get("bundle_pins") or {}
    for name, after in written.items():
        row = rows.get(name)
        if row is None:
            continue
        rows[name] = dict(row, applied_sha256=sha(after), sites=[
            dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row.get("sites", [])])
    out["metlife_model"] = dict(label=LABEL, bundles=sorted(written))
    return out


@official.requires_pack("modern_metlife_model")
def apply_to_image(target, *, retail_source, progress=None):
    """Build step (after modern_metlife): write the model stretch into the eighteen bundles and the 2026 superfans
    into the four crowd scenes of the disposable output image. Each bundle must carry the skin (alone or composed
    with Modern colour, which leaves the stadium and camera chunks to the skin); every write is a same-size span.
    With Modern colour on the image, its receipt's eighteen rows are re-pinned to the written bundles."""
    from . import nfl2k5_metlife_crowd as crowd
    from . import nfl2k5_modern_color as colour
    pins = model_pins()
    say = progress or (lambda message, done, total: None)
    state = image_status(target)
    if state == "applied":
        return dict(label=LABEL, state="already_applied", **verify(target))
    sb.require(state == "skin", f"MetLife model needs the MetLife skin on the image (found {state})")
    colour_receipt = colour.read_image_receipt(target)
    if colour_receipt is not None:
        sb.require(colour.image_status(target, receipt=colour_receipt) == colour_receipt["state"],
                   "Colour bytes differ from their receipt; rebuild from the original retail disc")
    built = build_all(retail_source, progress=say)
    receipt = dict(label=LABEL, runtime_witnessed=False, bundles=[], crowd=[])
    by_name = {p["name"]: p for p in pins["bundles"]}
    written = {}
    with ml._outer_image()(str(target), writable=True) as archive:
        for name in ml.VARIANTS:
            pin = by_name[name]
            skin, model, info = built[name]
            off, model_stretch = _stretch(model)
            sb.require(off == pin["offset"] and sha(model_stretch) == pin["model_sha256"],
                       f"{name}: the compiled model differs from its pin")
            e = archive.entries[pin["outer"]]
            at = e.virtual_offset + off
            sb.require(sha(archive.read(at, pin["length"])) == pin["skin_sha256"], f"{name}: not the skin")
            archive.write(at, model_stretch)
            sb.require(archive.read(at, len(model_stretch)) == model_stretch, f"{name}: write-back differs")
            receipt["bundles"].append(dict(name=name, outer=pin["outer"], offset=off, size=len(model_stretch)))
            written[name] = archive.read(e.virtual_offset, e.size)
        for pin in pins["crowd"]:
            e = archive.entries[pin["outer"]]
            data = archive.read(e.virtual_offset, e.size)
            new, rec = crowd.crowd_resource(data, pin["outer"])
            sb.require(rec["after_sha256"] == pin["applied_sha256"], f"crowd outer {pin['outer']}: differs from its pin")
            archive.write(e.virtual_offset, new)
            sb.require(archive.read(e.virtual_offset, e.size) == new, f"crowd outer {pin['outer']}: write-back differs")
            receipt["crowd"].append(dict(outer=pin["outer"], offset=rec["offset"], size=rec["size"]))
    if colour_receipt is not None:
        repinned = repin_colour_rows(colour_receipt, written)
        sb.require(colour.image_status(target, receipt=repinned) == repinned["state"], "Combined colour read-back failed")
        colour._save_image_receipt(target, repinned)
        receipt["colour_rows_repinned"] = sorted(written)
    say("MetLife model: done", 1, 1)
    receipt.update(verify(target))
    return receipt


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_metlife_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-bundles", help="write the eighteen model bundles (and their skins) to a folder")
    b.add_argument("source"); b.add_argument("out")
    a = sub.add_parser("apply-lab", help="lab only: write the model chunks into a disc that carries the skin")
    a.add_argument("disc"); a.add_argument("--source", required=True)
    st = sub.add_parser("status"); st.add_argument("source")
    rp = sub.add_parser("record-pins"); rp.add_argument("source"); rp.add_argument("--out", default=str(PINS_PATH))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source))
        return 0
    if args.command == "record-pins":
        doc = record_pins(args.source, args.out, progress=lambda m, d, t: print(f"  {m}", flush=True))
        print("PINS_OK", len(doc["bundles"]), len(doc["crowd"]))
        return 0
    say = lambda m, d, t: print(f"  {m}", flush=True)  # noqa: E731
    if args.command == "build-bundles":
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        info = {}
        for name, (skin, model, i) in build_all(args.source, progress=say).items():
            (out / name).write_bytes(model)
            info[name] = i
        (out / "build.json").write_text(json.dumps(info, indent=1) + "\n", newline="\n")
        print("MODEL_BUNDLES_OK", len(info))
        return 0
    receipt = apply_lab_disc(args.disc, args.source, progress=say)
    Path(str(args.disc) + ".u5-model.json").write_text(json.dumps(receipt, indent=1) + "\n", newline="\n")
    print("U5_MODEL_APPLIED", len(receipt["bundles"]))
    return 0



# ------------------------------------------------------------------------------------------------ intro cameras

#: The intro_cameras SCNE (PROVED OFFLINE, retail s18/s19 bundles): five camera records in the aux60 table (0x60 each:
#: +0x00 name, +0x10 a 4x4 rest matrix whose rows are right, up and back (forward = -row 2) and the position in
#: centimetres, +0x50 the field of view in degrees) and ten channels in the aux14 table, two per camera: a constant
#: channel on the field of view and a matrix channel. A matrix channel's +0x08 word lists its components (bits 0-2 the
#: translation, 6-8 the rotation about x (pitch), y (yaw) and z (roll)) and which of them are constant (bits 12-23);
#: its data holds a float per constant component and a (count, time pointer, segment pointer) entry per animated one.
#: A segment is a cubic a t^3 + b t^2 + c t + d; the time words are ticks of 1/300 s (0x253C0 scales them by
#: 0.0033333); rotations are binary angles (65536 a turn): retail camera 1 rests at yaw 27045.5 = 148.6 degrees and
#: pitch -2548.8 = -14.0 degrees, exactly the angles its rest matrix encodes.
CAMERA_COMPONENTS = {0: "x", 1: "y", 2: "z", 6: "pitch", 7: "yaw", 8: "roll"}
BAM = 65536.0 / 360.0


def camera_matrix(x, y, z, yaw_deg, pitch_deg):
    """Rest matrix rows (right, up, back, position) of a camera at (x, y, z) cm with yaw and pitch in degrees."""
    Y, P = math.radians(yaw_deg), math.radians(pitch_deg)
    right = (math.cos(Y), 0.0, -math.sin(Y), 0.0)
    upv = (math.sin(Y) * math.sin(P), math.cos(P), math.cos(Y) * math.sin(P), 0.0)
    back = (math.sin(Y) * math.cos(P), -math.sin(P), math.cos(Y) * math.cos(P), 0.0)
    return right, upv, back, (x, y, z, 1.0)


def look_angles(eye, target):
    """(yaw, pitch) in degrees for a camera at ``eye`` looking at ``target`` (forward = -back)."""
    f = np.asarray(target, float) - np.asarray(eye, float)
    f /= math.np_norm(f)
    return math.degrees(math.atan2(-f[0], -f[2])), math.degrees(math.asin(f[1]))


def parse_cameras(decoded):
    """{'cameras': [(offset, name)], 'channels': [dict]} of a retail intro_cameras scene."""
    buf = bytes(decoded)
    rel = sb._rel
    desc = rel(buf, 0x14)
    n14, p14 = struct.unpack_from("<I", buf, desc + 0x0C)[0], rel(buf, desc + 0x10)
    n60, p60 = struct.unpack_from("<I", buf, desc + 0x3C)[0], rel(buf, desc + 0x40)
    cams = [(p60 + i * 0x60, sb._utf16z(buf, rel(buf, p60 + i * 0x60))) for i in range(n60)]
    channels = []
    for i in range(n14):
        o = p14 + i * 0x14
        h, _w4, w8 = struct.unpack_from("<III", buf, o)
        target, data = rel(buf, o + 0x0C), rel(buf, o + 0x10)
        cam = next(k for k, (co, _n) in enumerate(cams) if co <= target < co + 0x60)
        present, const = w8 & 0xFFF, (w8 >> 12) & 0xFFF
        at = data
        comps = []
        for bit in range(12):
            m = 1 << bit
            if not present & m:
                continue
            if const & m:
                comps.append(dict(bit=bit, const=at))
                at += 4
            else:
                count = struct.unpack_from("<I", buf, at)[0]
                comps.append(dict(bit=bit, count=count, times=rel(buf, at + 4), segs=rel(buf, at + 8)))
                at += 12
        channels.append(dict(index=i, hash=h, camera=cam, field=target - cams[cam][0], comps=comps))
    return dict(cameras=cams, channels=channels)


def write_cameras(decoded, shots):
    """Same-layout rewrite of an intro_cameras scene: every camera keeps its record, channel structure and time words;
    only the rest matrices, the fields of view, the constant components and the segment coefficients change.

    ``shots`` is a list of five dicts: eye (m), yaw, pitch, fov (degrees), and per animated component a rate
    (x/y/z in m per second, pitch/yaw/roll in degrees per second). A component the retail channel keeps constant
    takes its start value; a component the channel lacks follows the rest matrix.
    """
    info = parse_cameras(decoded)
    out = bytearray(decoded)
    for k, ((co, name), shot) in enumerate(zip(info["cameras"], shots)):
        ex, ey, ez = (v * 100.0 for v in shot["eye"])
        rows = camera_matrix(ex, ey, ez, shot["yaw"], shot["pitch"])
        for r, row in enumerate(rows):
            struct.pack_into("<4f", out, co + 0x10 + 16 * r, *row)
        struct.pack_into("<f", out, co + 0x50, float(shot["fov"]))
        start = dict(x=ex, y=ey, z=ez, pitch=shot["pitch"] * BAM, yaw=shot["yaw"] * BAM, roll=0.0)
        rate = {c: v for c, v in shot.get("rates", {}).items()}
        for ch in (c for c in info["channels"] if c["camera"] == k):
            if ch["field"] == 0x50:
                for comp in ch["comps"]:
                    sb.require("const" in comp, f"{name}: animated field of view")
                    struct.pack_into("<f", out, comp["const"], float(shot["fov"]))
                continue
            sb.require(ch["field"] == 0x10, f"{name}: channel on an unknown field")
            for comp in ch["comps"]:
                label = CAMERA_COMPONENTS[comp["bit"]]
                if "const" in comp:
                    struct.pack_into("<f", out, comp["const"], float(start[label]))
                    continue
                sb.require(comp["count"] == 1, f"{name}: multi-segment curves are not written")
                per_tick = rate.get(label, 0.0) / 300.0
                per_tick *= 100.0 if label in ("x", "y", "z") else BAM
                struct.pack_into("<4f", out, comp["segs"], 0.0, 0.0, float(per_tick), float(start[label]))
    return bytes(out)


#: DESIGN: the MetLife flyover. Retail speeds for scale: camera 1 drifts at 7.8 m/s and pans 5 degrees a second.
#: Every eye is checked against the model's geometry in the offline previews.
METLIFE_SHOTS = [
    # 1: exterior, south-west, 95 m up: the south facade with the MetLife mark, the west letters and the Solar Ring
    dict(eye=(130.0, 95.0, -235.0), target=(-5.0, 30.0, 10.0), fov=30.0,
         rates=dict(x=-3.0, y=-1.2, z=5.5, pitch=-0.6, yaw=1.6)),
    # 2: the west 200-level front, a dolly north looking across at the east stack and the ring letters
    dict(eye=(66.0, 27.0, -38.0), target=(-80.0, 30.0, -20.0), fov=25.0, rates=dict(z=6.5, pitch=0.3, yaw=-1.5)),
    # 3: a crane up over the south end: the north boards, the MetLife mark and the ring
    dict(eye=(0.0, 22.0, -96.0), target=(0.0, 24.0, 60.0), fov=25.0, rates=dict(y=6.5, pitch=-1.2, yaw=0.0)),
    # 4: field level at the north-west corner, a pan across the east stands
    dict(eye=(30.0, 3.5, 58.0), target=(-60.0, 18.0, 20.0), fov=25.0, rates=dict(yaw=-4.0)),
    # 5: high over the south-east upper deck moving north: the Solar Ring and the bowl below
    dict(eye=(-62.0, 92.0, -98.0), target=(20.0, 5.0, 25.0), fov=25.0,
         rates=dict(x=0.0, y=0.0, z=6.0, pitch=-0.4, yaw=-1.5, roll=0.0)),
]


def metlife_shots():
    out = []
    for s in METLIFE_SHOTS:
        yaw, pitch = look_angles(s["eye"], s["target"])
        out.append(dict(s, yaw=yaw, pitch=pitch))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
