"""Practice facility model (experimental): a modern outdoor NFL practice facility built from scratch as the stadium scene
of venue record s32 (retail "The Practice Facility", a college-style bowl), all nine bundles (day, afternoon, night; dry,
rain, snow). The game loads s32 for main-menu Practice (Scrimmage and Basic Training), franchise Free Practice and
MyCareer practice (job pf's report, section 2).

Job pf (2026-09-27), on u5's builder and the stadium models of u6 (SoFi) and st (Highmark, AT&T, Levi's, Allegiant).
The facility is a composite, neutral for all 32 teams (the venue is shared), built from cited references (the pf
report, section 4: the Commons photos of the Ravens', Seahawks', Bears', Dolphins', Eagles', 49ers' and Chargers'
facilities and camps; Wikipedia's articles on the Vikings', Seahawks', Bears' and Steelers' facilities; OpenStreetMap
plans of nine facilities). The scene:

* the game's field in the middle (its own field scene, painted by :func:`paint_field`), framed by walkways;
* two more full practice fields beside it, natural grass on the home side (-x) and synthetic on the away side (+x), with
  their lines, hash marks and yellow single-post goalposts;
* the indoor field house behind the +z end (white ribbed metal walls, a translucent clerestory lit at night, roll-up
  doors, a barrel roof) and the team headquarters behind the -z end (a three-storey glass front with a taller entrance
  bay, a white roof slab and a canopy over the players' door);
* windscreen fences round the fields, six light poles with LED heads, three filming towers (scissor lifts), training
  camp bleachers with fans on the away side, two portable practice clocks carrying the game's digits, blocking sleds,
  tackling dummies, JUGS machines and pop-up tents;
* outside: lawns, parking, a road and tree lines, and the horizon, drawn with the retail cityscape's own textures of the
  same bundle (the user's game data: grass, parking, road, trees and the hills line), the retail cityscape collapsed;
* kept from retail because the engine reads them: the sideline props, pylons, yard markers, the digit shapes (moved
  onto the practice clocks), the markers and the materials the executable looks up by name (``crowd``, ``jumbo_tron``,
  ``digit_*``).

Geometry is in metres here (x across, +x the away bench as in every retail stadium; y up from the field; z along) and
centimetres in the game. The row is not written. EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.
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

from . import nfl2k5_metlife_model as mm  # noqa: E402
from . import nfl2k5_scne_builder as sb  # noqa: E402
from . import nfl2k5_sofi_model as sm  # noqa: E402

OWNER = "nfl2k5_practice_field_model"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_practice_field_model"
ART_DIR = DATA_DIR / "art"
FIELD_ART = ART_DIR / "field"
VENUE = "s32"
VENUES = (VENUE,)

Mesh = mm.Mesh

#: a field: 53 1/3 yards wide, the goal lines 50 yards from midfield, the end lines 10 yards behind them
FIELD_HALF_W = 24.384
GOAL_Z = 45.72
END_Z = 54.864


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _v(*a):
    return np.array(a, float)


# ------------------------------------------------------------------------------------------------ parameters

#: DESIGN, pass 1 (the pf report, section 5). Every piece clears what the engine keeps on the ground: the retail
#: sideline props (x -41.6 to -31.9 and 32.3 to 41.7), the sideline markers (media, security and VIP up to x +/-38.6,
#: z +/-62.2) and the field scene's own grass (x +/-58.5, z +/-87.7).
PARAMS = dict(
    #: the walkways framing the field scene's grass (they also hide its edge)
    pad=dict(x=58.5, z=87.7, path=3.0),
    #: the side fields: centre 86 m out (the game needs the bench area; real facilities sit 61 m apart, OSM), natural
    #: grass on the home side, synthetic on the away side (TCO and the Steelers keep one synthetic outdoor field)
    side_fields=dict(x=86.0, line=0.16),
    goalpost=dict(post_back=1.83, bar_h=3.048, bar_w=5.639, upright=10.668, thick=0.16, pad_h=2.0),
    #: the indoor field house behind the +z end (UPMC's centre ridge, the Seahawks' and Ravens' white field houses)
    field_house=dict(x0=-72.0, x1=72.0, z0=110.0, z1=190.0, eave=14.0, ridge=27.0, clere=(10.0, 13.6), wall_u=12.0,
                     roof_steps=12, overhang=0.8, doors=((-54.0, 9.0, 7.5), (54.0, 9.0, 7.5))),
    #: the team headquarters behind the -z end (Halas Hall's glass entrance, the Dolphins' complex)
    hq=dict(x0=-78.0, x1=78.0, z_front=-106.0, z_back=-142.0, storey=5.0, storeys=3, base=0.9, slab=0.8, overhang=1.4,
            bay=dict(x0=-22.0, x1=22.0, z_front=-103.0, top=21.0), canopy=dict(x0=-11.0, x1=11.0, depth=6.0, h=4.4),
            patio=dict(x0=-40.0, x1=40.0, z0=-106.0, z1=-96.0)),
    fence=dict(x=122.0, z_south=-106.0, z_north=110.0, h=2.4, u=12.0),
    #: six light poles on the walkways' outer edge (the Rooney fields' lighting for evening sessions), LED heads aimed
    #: at the main field
    poles=dict(x=62.5, z=(-48.0, 0.0, 48.0), h=24.0, width=0.55, head_w=3.4, head_h=2.0, tilt=18.0),
    #: filming towers (scissor lifts: UPMC's viewing towers; every NFL practice films from lifts)
    lifts=(dict(x=-50.0, z=0.0, h=11.0, face=(1.0, 0.0)), dict(x=14.0, z=-74.0, h=10.0, face=(0.0, 1.0)),
           dict(x=-14.0, z=74.0, h=10.0, face=(0.0, -1.0))),
    #: training-camp bleachers on the away side facing the main field (the Eagles' and Giants' camps; VMAC's fan berm)
    bleachers=dict(x0=46.6, z0=-36.0, z1=36.0, rows=10, tread=0.80, rise=0.42, y0=0.45, aisle_every=12.0, aisle=1.2),
    crowd=dict(rows_per_band=2, lift=0.20, extra=1.0, v_per_m=1 / 9.14, lean=0.35),
    #: a practice video board in front of the field house, facing the field (the Eagles' 2019 camp at the NovaCare
    #: Complex, R07, and the Chargers' 2026 camp, R25, practise beside one): the game's live feed on ``jumbo_tron``
    video_board=dict(x=0.0, z=96.0, w=16.0, h=9.0, bottom=4.2, depth=0.8, face=(0.0, -1.0)),
    #: two portable practice clocks carrying the game's digits, facing the field from behind each end zone
    clocks=(dict(x=-24.0, z=72.0, face=(0.0, -1.0)), dict(x=24.0, z=-72.0, face=(0.0, 1.0))),
    clock=dict(w=4.4, h=2.4, depth=0.40, bottom=2.3),
    #: the sideline gear between the benches and the walkway on the home side, and by the away side's bleachers
    sleds=(dict(x=-51.0, z=12.0, pads=7), dict(x=-51.0, z=-36.0, pads=2), dict(x=-46.5, z=-45.0, pads=2)),
    dummies=dict(x=-55.5, z0=-26.0, z1=-8.0, n=7),
    jugs=((-46.0, 24.0), (-46.0, -54.0)),
    tents=((-51.5, -55.0), (51.0, 46.0)),
    #: a white frame pavilion along the home side (the Eagles' camp, R07: a long white tent beside the practice field)
    pavilion=dict(x0=-58.0, x1=-51.0, z0=30.0, z1=56.0, eave=3.0, ridge=4.6, bay=4.33),
    #: outside: lawns out to the horizon, parking and a road behind the headquarters and beside the field house, tree
    #: lines outside the fence
    ground=dict(r=720.0, tile=8.0),
    parking=((-78.0, 78.0, -198.0, -150.0), (80.0, 170.0, 122.0, 186.0)),
    road=dict(z=-208.0, w=9.0, x=320.0),
    #: tree lines outside the fence: rows of the retail tree-row billboards (trees_01, trees_02), single trees in front
    trees=dict(west=(-205.0, -132.0), east=(132.0, 205.0), north=(198.0, 250.0), south=(-262.0, -214.0), row_w=28.0,
               row_h=(13.0, 17.0), rows=3, singles=90, h=(11.0, 18.0)),
    #: the neighbourhood beyond the trees: low office blocks and the retail cityscape's aerial ground
    far=dict(r0=340.0, blocks=14, seed=4101),
    horizon=dict(r=650.0, top=56.0, bottom=-2.0, points=48),
)


def _merge(base, over):
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def _rng(seed):
    return np.random.default_rng(seed)


# ------------------------------------------------------------------------------------------------ the model

class PracticeFacility:
    def __init__(self, params=None, venue=VENUE):
        self.p = _merge(PARAMS, params)
        self.venue = venue
        self.meshes = {}
        self.markers = {}
        self.light_points = []
        self.clock_frames = []
        self.nosebleed = (54.2, 4.9, -20.0)

    def mesh(self, name):
        return self.meshes.setdefault(name, Mesh(name))

    # -- primitives -----------------------------------------------------------------------------------------------
    @staticmethod
    def quad(m, mat, p0, p1, p2, p3, uv0, uv1, uv2, uv3, face):
        """A quad p0 p1 p2 p3 (a loop), facing ``face`` (a vector)."""
        f = np.asarray(face, float)
        m.quad(mat, _v(*p0), _v(*p1), _v(*p2), _v(*p3), uv0, uv1, uv2, uv3, facing=lambda _p, f=f: f)

    def rect_xz(self, m, mat, x0, x1, z0, z1, y, tile=None, uv=None):
        """A flat rectangle facing up; UVs from world metres over ``tile`` (u along x, v along z) or given as
        (u0, u1, v0, v1)."""
        if uv is None:
            uv = (x0 / tile, x1 / tile, z0 / tile, z1 / tile)
        u0, u1, v0, v1 = uv
        self.quad(m, mat, (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1), (u0, v0), (u1, v0), (u1, v1), (u0, v1),
                  (0.0, 1.0, 0.0))

    def wall(self, m, mat, a, b, y0, y1, face, u_len=None, v_rng=(1.0, 0.0), double=False):
        """A vertical wall from plan point a to b between heights y0 and y1; u along it in ``u_len`` metres, v from
        ``v_rng[0]`` at the bottom to ``v_rng[1]`` at the top."""
        ax, az = a
        bx, bz = b
        L = math.hypot(bx - ax, bz - az)
        u1 = L / u_len if u_len else 1.0
        vb, vt = v_rng
        self.quad(m, mat, (ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az), (0.0, vb), (u1, vb), (u1, vt),
                  (0.0, vt), (face[0], 0.0, face[1]))
        if double:
            # the back face 2 cm behind the front one (never coplanar)
            ox, oz = -face[0] * 0.02, -face[1] * 0.02
            self.quad(m, mat, (bx + ox, y0, bz + oz), (ax + ox, y0, az + oz), (ax + ox, y1, az + oz),
                      (bx + ox, y1, bz + oz), (0.0, vb), (u1, vb), (u1, vt), (0.0, vt), (-face[0], 0.0, -face[1]))

    @staticmethod
    def box(m, mat, centre, half, axes=None, uvscale=0.25, bottom=False):
        axes = axes or ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        m.box(mat, _v(*centre), axes, half, uvscale=uvscale, bottom=bottom)

    @staticmethod
    def prism(m, mat, base, top, r0, r1, sides=8, uv_h=1.0, cap=True):
        """An upright tapered prism (poles, dummies): centre ``base`` to ``top``, radii r0 to r1."""
        bx, by, bz = base
        tx, ty, tz = top
        ring0, ring1, uvs0, uvs1 = [], [], [], []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            c, s = math.cos(a), math.sin(a)
            ring0.append(_v(bx + r0 * c, by, bz + r0 * s))
            ring1.append(_v(tx + r1 * c, ty, tz + r1 * s))
            uvs0.append((k / sides, uv_h))
            uvs1.append((k / sides, 0.0))
        m.grid(mat, [ring0, ring1], [uvs0, uvs1], facing=lambda p, c=_v(bx, (by + ty) / 2, bz): _v(p[0] - c[0], 0.0, p[2] - c[2]))
        if cap:
            centre = _v(tx, ty, tz)
            ci = m.v(centre, (0.5, 0.5), (0.0, 1.0, 0.0))
            idx = [m.v(p, (0.5, 0.5), (0.0, 1.0, 0.0)) for p in ring1]
            for k in range(sides):
                m.strip(mat, [ci, idx[k + 1], idx[k]])

    # -- build ----------------------------------------------------------------------------------------------------
    def build(self):
        self._ground()
        self._walks()
        for side in (-1, 1):
            self._side_field(side)
        self._field_house()
        self._headquarters()
        self._fences()
        self._poles()
        self._lifts()
        self._bleachers()
        self._clocks()
        self._video_board()
        self._gear()
        self._pavilion()
        self._parking()
        self._trees()
        self._neighbourhood()
        self._horizon()
        self.markers["jumbo"] = [self.board_centre, self.clock_frames[1]["centre"]]
        return self

    # -- the ground and walks -----------------------------------------------------------------------------------
    def _ground(self):
        """Lawns round the field scene's grass, out past the horizon ring (the retail cityscape's grass texture). The
        hole in the middle is the field scene's own grass (x +/-58.5, z +/-87.7), so nothing lies on it."""
        m = self.mesh("pf_ground")
        q, t = self.p["pad"], self.p["ground"]
        R, X, Z, tile = t["r"], q["x"], q["z"], t["tile"]
        for x0, x1, z0, z1 in ((-R, -X, -R, R), (X, R, -R, R), (-X, X, Z, R), (-X, X, -R, -Z)):
            # a coarse grid: the vertex light varies over it (the pools under the poles at night)
            nx = max(1, int(round((x1 - x0) / 60.0)))
            nz = max(1, int(round((z1 - z0) / 60.0)))
            xs = np.linspace(x0, x1, nx + 1)
            zs = np.linspace(z0, z1, nz + 1)
            pts = [[_v(x, -0.02, z) for x in xs] for z in zs]
            uvs = [[(x / tile, z / tile) for x in xs] for z in zs]
            m.grid("pf_ground", pts, uvs, facing=lambda _p: _v(0, 1, 0))

    def _walks(self):
        """Concrete walkways round the field scene's grass (hiding its edge), the headquarters' walk and patio and the
        apron in front of the field house."""
        m = self.mesh("pf_walks")
        q = self.p["pad"]
        X, Z, w = q["x"], q["z"], q["path"]
        y = 0.03
        self.rect_xz(m, "pf_path", -X - w, -X, -Z - w, Z + w, y, tile=4.0)
        self.rect_xz(m, "pf_path", X, X + w, -Z - w, Z + w, y, tile=4.0)
        self.rect_xz(m, "pf_path", -X, X, -Z - w, -Z, y, tile=4.0)
        self.rect_xz(m, "pf_path", -X, X, Z, Z + w, y, tile=4.0)
        h = self.p["hq"]
        pa = h["patio"]
        self.rect_xz(m, "pf_path", pa["x0"], pa["x1"], pa["z0"], pa["z1"], y, tile=4.0)
        self.rect_xz(m, "pf_path", -3.0, 3.0, pa["z1"], -Z - w, y, tile=4.0)
        f = self.p["field_house"]
        self.rect_xz(m, "pf_path", f["x0"], f["x1"], f["z0"] - 6.0, f["z0"], y, tile=4.0)
        for x in (-54.0, 54.0):
            self.rect_xz(m, "pf_path", x - 2.5, x + 2.5, Z + w, f["z0"] - 6.0, y, tile=4.0)

    # -- the side fields ---------------------------------------------------------------------------------------
    def _side_field(self, side):
        """A full practice field centred at x = side * 86 m: the field of play mown in 5-yard bands with its yard lines
        and hash marks (a 10-yard texture tile), plain end zones, the boundary and goal lines, goalposts."""
        synthetic = side > 0
        m = self.mesh("pf_field_" + ("turf" if synthetic else "grass"))
        cx = side * self.p["side_fields"]["x"]
        x0, x1 = cx - FIELD_HALF_W, cx + FIELD_HALF_W
        y = 0.04
        strip = "pf_turf_strip" if synthetic else "pf_field_strip"
        ez = "pf_endzone_turf" if synthetic else "pf_endzone_grass"
        # the texture's u runs across the field and v along it, 10 yards per repeat, a yard line at v = 0 and 0.5
        zs = np.linspace(-GOAL_Z, GOAL_Z, 11)
        pts = [[_v(x0, y, z), _v(x1, y, z)] for z in zs]
        uvs = [[(0.0, k * 1.0), (1.0, k * 1.0)] for k in range(11)]
        m.grid(strip, pts, uvs, facing=lambda _p: _v(0, 1, 0))
        for z0, z1 in ((-END_Z, -GOAL_Z), (GOAL_Z, END_Z)):
            self.rect_xz(m, ez, x0, x1, z0, z1, y, uv=(x0 / 8.0, x1 / 8.0, z0 / 8.0, z1 / 8.0))
        lw = self.p["side_fields"]["line"]
        yl = y + 0.01
        for x in (x0, x1):
            self.rect_xz(m, "pf_paint", x - lw / 2, x + lw / 2, -END_Z - lw / 2, END_Z + lw / 2, yl, uv=(0, 1, 0, 1))
        for z in (-END_Z, END_Z, GOAL_Z):
            self.rect_xz(m, "pf_paint", x0, x1, z - lw / 2, z + lw / 2, yl, uv=(0, 1, 0, 1))
        # the yard numbers every 10 yards, 6 ft tall, their tops 9 yards in from each sideline, their bottoms toward it
        # (NFL rule 1); the text reads along the field as seen from that sideline
        h = 1.8288
        w = h * 5.0 * 64.0 / 128.0         # one row of the five-number atlas, at the texture's own aspect
        yn = y + 0.02
        for j in range(1, 10):
            z = -GOAL_Z + 9.144 * j
            k = (min(j, 10 - j)) - 1                  # 10, 20, 30, 40, 50, 40, 30, 20, 10
            for sx, xs in ((-1, x0), (1, x1)):
                up = _v(-sx, 0.0, 0.0)                 # toward the field's middle
                right = _v(0.0, 0.0, -sx)              # the reader's right, standing on that sideline facing the field
                c = _v(xs, yn, z) + up * (8.2296 - h / 2)
                self.quad(m, "pf_numbers", c - right * w / 2 - up * h / 2, c + right * w / 2 - up * h / 2,
                          c + right * w / 2 + up * h / 2, c - right * w / 2 + up * h / 2, (0.0, (k + 1) / 5.0),
                          (1.0, (k + 1) / 5.0), (1.0, k / 5.0), (0.0, k / 5.0), (0.0, 1.0, 0.0))
        for zs_ in (-1, 1):
            self._goalpost(cx, zs_)

    def _goalpost(self, cx, zs):
        """An NFL single-post goalpost over the end line: the post 6 ft behind it with its pad, the gooseneck, the
        crossbar 10 ft up and 18 ft 6 in wide, the uprights 35 ft above it (NFL rule 1, section 5)."""
        m = self.mesh("pf_goalposts")
        g = self.p["goalpost"]
        t = g["thick"] / 2
        zb = zs * (END_Z + g["post_back"])
        ze = zs * END_Z
        h = g["bar_h"]
        self.box(m, "pf_yellow", (cx, h / 2, zb), (t * 1.4, h / 2, t * 1.4))
        self.box(m, "pf_dark", (cx, g["pad_h"] / 2, zb), (0.32, g["pad_h"] / 2, 0.32))
        self.box(m, "pf_yellow", (cx, h - t, (zb + ze) / 2), (t, t, abs(zb - ze) / 2 + t))
        w = g["bar_w"] / 2
        self.box(m, "pf_yellow", (cx, h, ze), (w + t, t, t))
        for sx in (-1, 1):
            self.box(m, "pf_yellow", (cx + sx * w, h + g["upright"] / 2, ze), (t * 0.8, g["upright"] / 2, t * 0.8))

    # -- the field house ----------------------------------------------------------------------------------------
    def roof_y(self, z):
        f = self.p["field_house"]
        t = (z - f["z0"]) / (f["z1"] - f["z0"])
        return f["eave"] + (f["ridge"] - f["eave"]) * math.sin(math.pi * min(1.0, max(0.0, t)))

    def _field_house(self):
        """The indoor field house: white ribbed walls over a dark base, the translucent clerestory band under the
        eaves (lit at night), two roll-up doors facing the fields, the gable walls under a barrel roof."""
        m = self.mesh("pf_field_house")
        f = self.p["field_house"]
        x0, x1, z0, z1 = f["x0"], f["x1"], f["z0"], f["z1"]
        c0, c1 = f["clere"]
        u = f["wall_u"]
        for (a, b, face) in (((x1, z0), (x0, z0), (0.0, -1.0)), ((x0, z1), (x1, z1), (0.0, 1.0))):
            self.wall(m, "pf_fh_wall", a, b, 0.0, c0, face, u_len=u)
            self.wall(m, "LIGHT_pf_clere", a, b, c0, c1, face, u_len=8.0)
            self.wall(m, "pf_white", a, b, c1, f["eave"], face, u_len=8.0)
        for (dx, w, h) in f["doors"]:
            self.wall(m, "pf_door", (dx + w / 2, z0 - 0.06), (dx - w / 2, z0 - 0.06), 0.0, h, (0.0, -1.0))
        # the gables: the walls up to the clerestory, the band, then white panels up to the roof's curve
        n = f["roof_steps"]
        zs = np.linspace(z0, z1, n + 1)
        for x, face in ((x0, -1.0), (x1, 1.0)):
            self.wall(m, "pf_fh_wall", (x, z1) if face < 0 else (x, z0), (x, z0) if face < 0 else (x, z1), 0.0, c0,
                      (face, 0.0), u_len=u)
            self.wall(m, "LIGHT_pf_clere", (x, z1) if face < 0 else (x, z0), (x, z0) if face < 0 else (x, z1), c0, c1,
                      (face, 0.0), u_len=8.0)
            order = zs[::-1] if face < 0 else zs
            bot = [_v(x, c1, z) for z in order]
            top = [_v(x, self.roof_y(z), z) for z in order]
            m.grid("pf_white", [bot, top], [[(i * 0.25, 1.0) for i in range(n + 1)], [(i * 0.25, 0.0) for i in range(n + 1)]],
                   facing=lambda _p, face=face: _v(face, 0.0, 0.0))
        # the barrel roof, a little past the walls
        o = f["overhang"]
        rz = np.linspace(z0 - o, z1 + o, n + 1)
        rows = [[_v(x0 - o, self.roof_y(z) + 0.05, z), _v(x1 + o, self.roof_y(z) + 0.05, z)] for z in rz]
        s = 0.0
        vs = [0.0]
        for a, b in zip(rz[:-1], rz[1:]):
            s += math.hypot(b - a, self.roof_y(b) - self.roof_y(a))
            vs.append(s / 8.0)
        uvs = [[(0.0, v), ((x1 - x0 + 2 * o) / 8.0, v)] for v in vs]
        m.grid("pf_fh_roof", rows, uvs, facing=lambda p: _v(0.0, 1.0, -(p[2] - (z0 + z1) / 2) * 0.02))
        # the gutters along the eaves and a row of roof vents along the ridge
        for zg in (z0 - o, z1 + o):
            self.box(m, "pf_steel", ((x0 + x1) / 2, f["eave"] - 0.1, zg), ((x1 - x0) / 2 + o, 0.18, 0.18))
        zr = (z0 + z1) / 2
        for xv in np.linspace(x0 + 14.0, x1 - 14.0, 6):
            self.box(m, "pf_steel", (float(xv), self.roof_y(zr) + 0.6, zr), (1.4, 0.6, 1.4), uvscale=0.5)
        # floodlights over the doors (two of the glow markers)
        for (dx, _w, h) in f["doors"]:
            self.light_points.append((dx, h + 2.2, z0 - 0.8))
            self.box(m, "LIGHT_pf_led", (dx, h + 2.2, z0 - 0.35), (0.8, 0.3, 0.35))

    # -- the headquarters -----------------------------------------------------------------------------------------
    def _headquarters(self):
        """The team building: a three-storey glass front facing the fields over a stone base, a taller glass entrance
        bay in the middle, stone side and back walls, a white roof slab with an overhang, a canopy over the players'
        door."""
        m = self.mesh("pf_headquarters")
        h = self.p["hq"]
        x0, x1, zf, zb = h["x0"], h["x1"], h["z_front"], h["z_back"]
        top = h["base"] + h["storey"] * h["storeys"]
        b = h["bay"]
        base = h["base"]
        vtop = top / h["storey"]
        # the glass front, either side of the entrance bay
        for a_x, b_x in ((x1, b["x1"]), (b["x0"], x0)):
            self.wall(m, "pf_stone", (a_x, zf), (b_x, zf), 0.0, base, (0.0, 1.0), u_len=4.0, v_rng=(0.2, 0.0))
            self.wall(m, "LIGHT_pf_glass", (a_x, zf), (b_x, zf), base, top, (0.0, 1.0), u_len=6.0,
                      v_rng=((top - base) / h["storey"], 0.0))
        # the entrance bay, 3 m proud of the front and taller
        bz, btop = b["z_front"], b["top"]
        self.wall(m, "pf_stone", (b["x1"], bz), (b["x0"], bz), 0.0, base, (0.0, 1.0), u_len=4.0, v_rng=(0.2, 0.0))
        self.wall(m, "LIGHT_pf_glass", (b["x1"], bz), (b["x0"], bz), base, btop, (0.0, 1.0), u_len=6.0,
                  v_rng=((btop - base) / h["storey"], 0.0))
        for x, face in ((b["x0"], -1.0), (b["x1"], 1.0)):
            a, c = ((x, zf), (x, bz)) if face > 0 else ((x, bz), (x, zf))
            self.wall(m, "LIGHT_pf_glass", a, c, base, btop, (face, 0.0), u_len=6.0, v_rng=((btop - base) / h["storey"], 0.0))
            self.wall(m, "pf_stone", a, c, 0.0, base, (face, 0.0), u_len=4.0, v_rng=(0.2, 0.0))
        # the bay's side glass above the main roof, back to the main block
        for x, face in ((b["x0"], -1.0), (b["x1"], 1.0)):
            a, c = ((x, zb + 6.0), (x, zf)) if face > 0 else ((x, zf), (x, zb + 6.0))
            self.wall(m, "LIGHT_pf_glass", a, c, top, btop, (face, 0.0), u_len=6.0, v_rng=((btop - top) / h["storey"], 0.0))
        self.wall(m, "pf_stone", (b["x0"], zb + 6.0), (b["x1"], zb + 6.0), top, btop, (0.0, -1.0), u_len=4.0,
                  v_rng=((btop - top) / 4.0, 0.0))
        # side and back walls
        self.wall(m, "pf_stone", (x0, zb), (x0, zf), 0.0, top, (-1.0, 0.0), u_len=4.0, v_rng=(top / 4.0, 0.0))
        self.wall(m, "pf_stone", (x1, zf), (x1, zb), 0.0, top, (1.0, 0.0), u_len=4.0, v_rng=(top / 4.0, 0.0))
        self.wall(m, "pf_stone", (x0, zb), (x1, zb), 0.0, top, (0.0, -1.0), u_len=4.0, v_rng=(top / 4.0, 0.0))
        # the roof and the white slab edge with its overhang
        o, s = h["overhang"], h["slab"]
        self.rect_xz(m, "pf_roof", x0, x1, zb, zf, top + 0.02, tile=8.0)
        self.box(m, "pf_white", ((x0 + x1) / 2, top + s / 2, (zf + zb) / 2 + o / 2),
                 ((x1 - x0) / 2 + o, s / 2, (zf - zb) / 2 + o / 2 + 0.01), uvscale=0.125)
        self.box(m, "pf_white", ((b["x0"] + b["x1"]) / 2, btop + s / 2, (bz + zb + 6.0) / 2 + o / 2),
                 ((b["x1"] - b["x0"]) / 2 + o, s / 2, (bz - zb - 6.0) / 2 + o / 2), uvscale=0.125)
        # the canopy over the players' door, on two steel columns
        c = h["canopy"]
        self.box(m, "pf_white", ((c["x0"] + c["x1"]) / 2, c["h"], bz + c["depth"] / 2),
                 ((c["x1"] - c["x0"]) / 2, 0.22, c["depth"] / 2), uvscale=0.125, bottom=True)
        for x in (c["x0"] + 0.6, c["x1"] - 0.6):
            self.box(m, "pf_steel", (x, c["h"] / 2, bz + c["depth"] - 0.6), (0.12, c["h"] / 2, 0.12))
        # the doors under the canopy (dark glass)
        self.wall(m, "pf_dark", (4.0, bz + 0.05), (-4.0, bz + 0.05), 0.0, 3.2, (0.0, 1.0), u_len=8.0)

    # -- fences, poles, lifts ----------------------------------------------------------------------------------
    def _fences(self):
        """Windscreened fences round the fields (plain dark mesh on posts, both faces)."""
        m = self.mesh("pf_fences")
        f = self.p["fence"]
        X, zs, zn, h, u = f["x"], f["z_south"], f["z_north"], f["h"], f["u"]
        hq, fh = self.p["hq"], self.p["field_house"]
        runs = [((-X, zs), (-X, zn), (1.0, 0.0)), ((X, zn), (X, zs), (-1.0, 0.0)),
                ((-X, zs), (hq["x0"], zs), (0.0, 1.0)), ((hq["x1"], zs), (X, zs), (0.0, 1.0)),
                ((fh["x0"], zn), (-X, zn), (0.0, -1.0)), ((X, zn), (fh["x1"], zn), (0.0, -1.0))]
        for a, b, face in runs:
            self.wall(m, "pf_windscreen", a, b, 0.0, h, face, u_len=u, v_rng=(1.0, 0.0), double=True)

    def _poles(self):
        """Six light poles: a galvanised shaft, a head frame with its LED fixtures aimed down at the main field."""
        m = self.mesh("pf_poles")
        q = self.p["poles"]
        for sx in (-1, 1):
            for z in q["z"]:
                x = sx * q["x"]
                self.prism(m, "pf_steel", (x, 0.0, z), (x, q["h"] - 1.0, z), q["width"] * 0.62, q["width"] * 0.40,
                           sides=6, uv_h=4.0)
                # the head: a frame across the pole, tilted toward the field; the LEDs on its field side
                tilt = math.radians(q["tilt"])
                face = _v(-sx * math.cos(tilt), -math.sin(tilt), 0.0)
                up = _v(-sx * math.sin(tilt), math.cos(tilt), 0.0)
                along = _v(0.0, 0.0, 1.0)
                c = _v(x, q["h"], z)
                hw, hh = q["head_w"] / 2, q["head_h"] / 2
                self.box(m, "pf_dark", tuple(c - face * 0.25), (hw + 0.1, hh + 0.1, 0.2),
                         axes=(tuple(along), tuple(up), tuple(-face)), uvscale=0.5)
                p0 = c + face * 0.02 - along * hw - up * hh
                p1 = c + face * 0.02 + along * hw - up * hh
                p2 = c + face * 0.02 + along * hw + up * hh
                p3 = c + face * 0.02 - along * hw + up * hh
                self.quad(m, "LIGHT_pf_led", p0, p1, p2, p3, (0, 2), (3, 2), (3, 0), (0, 0), face)
                self.light_points.append(tuple(c + face * 0.6))

    def _lifts(self):
        """Filming towers: scissor lifts (a dark base, the X-braced scissor stack, a platform with its rail) with a
        camera operator under a shade umbrella."""
        m = self.mesh("pf_lifts")
        for q in self.p["lifts"]:
            x, z, h = q["x"], q["z"], q["h"]
            fx, fz = q["face"]
            L, W = 2.6, 1.3
            self.box(m, "pf_dark", (x, 0.75, z), (L / 2 if abs(fz) > 0.5 else W / 2, 0.45, W / 2 if abs(fz) > 0.5 else L / 2),
                     uvscale=0.5)
            # the scissor: an alpha-tested X stack on both long sides (drawn from both sides by the engine)
            y0 = 1.2
            stage = 1.45
            for s in (-1, 1):
                if abs(fz) > 0.5:
                    zz = z + s * (W / 2 - 0.05)
                    p0, p1 = (x - L / 2 + 0.2, y0, zz), (x + L / 2 - 0.2, y0, zz)
                    p2, p3 = (x + L / 2 - 0.2, h, zz), (x - L / 2 + 0.2, h, zz)
                    face = (0.0, 0.0, s)
                else:
                    xx = x + s * (W / 2 - 0.05)
                    p0, p1 = (xx, y0, z - L / 2 + 0.2), (xx, y0, z + L / 2 - 0.2)
                    p2, p3 = (xx, h, z + L / 2 - 0.2), (xx, h, z - L / 2 + 0.2)
                    face = (s, 0.0, 0.0)
                nv = (h - y0) / stage
                self.quad(m, "pf_scissor", p0, p1, p2, p3, (0, nv), (1, nv), (1, 0), (0, 0), face)
            hx, hz = (L / 2 + 0.1, W / 2 + 0.1) if abs(fz) > 0.5 else (W / 2 + 0.1, L / 2 + 0.1)
            self.box(m, "pf_steel", (x, h + 0.08, z), (hx, 0.08, hz), uvscale=0.5, bottom=True)
            for sx, sz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if sx:
                    self.box(m, "pf_yellow", (x + sx * hx, h + 1.05, z), (0.03, 0.03, hz))
                else:
                    self.box(m, "pf_yellow", (x, h + 1.05, z + sz * hz), (hx, 0.03, 0.03))
            # the operator, the camera on its tripod and a shade umbrella
            ox, oz = x - fx * 0.3, z - fz * 0.3
            self.box(m, "pf_dark", (ox, h + 1.0, oz), (0.22, 0.85, 0.22))
            self.box(m, "pf_dark", (x + fx * 0.35, h + 1.45, z + fz * 0.35), (0.18, 0.14, 0.18))
            top = _v(x, h + 3.0, z)
            ring = [_v(x + 1.3 * math.cos(a), h + 2.45, z + 1.3 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 9)]
            ti = m.v(top, (0.5, 0.0), (0.0, 1.0, 0.0))
            ri = [m.v(p, (k / 8.0, 1.0), tuple((p - top) / np.linalg.norm(p - top))) for k, p in enumerate(ring)]
            for k in range(8):
                m.strip("pf_canvas", [ti, ri[k], ri[k + 1]])
            self.box(m, "pf_steel", (x, h + 1.9, z), (0.03, 1.1, 0.03))

    # -- the bleachers and fans --------------------------------------------------------------------------------
    def _bleachers(self):
        """Training-camp bleachers facing the main field: ten aluminium rows, the frame and back, and the fans as crowd
        billboards in the retail convention (a band per two rows; U a quarter strip of the runtime crowd atlas, V 9.14 m
        per unit), cut at the aisles."""
        m = self.mesh("pf_bleachers")
        q, cq = self.p["bleachers"], self.p["crowd"]
        x0, z0, z1 = q["x0"], q["z0"], q["z1"]
        rows, tread, rise, y0 = q["rows"], q["tread"], q["rise"], q["y0"]
        prof = [(x0, 0.0), (x0, y0)]
        for k in range(rows):
            xa = x0 + k * tread
            ya = y0 + k * rise
            prof += [(xa + tread, ya), (xa + tread, ya + rise)] if k < rows - 1 else [(xa + tread, ya)]
        xb = prof[-1][0]
        ytop = prof[-1][1]
        # the seats (the texture holds ten rows per v repeat): the stepped profile swept along z, facing the field
        vs = [0.0]
        for (a, b) in zip(prof[:-1], prof[1:]):
            vs.append(vs[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = vs[-1]
        vv = [v / total for v in vs]
        pts = [[_v(px, py, z0), _v(px, py, z1)] for px, py in prof]
        uvs = [[(z0 / 6.0, v), (z1 / 6.0, v)] for v in vv]
        m.grid("pf_bleacher", pts, uvs, facing=lambda _p: _v(-0.6, 0.8, 0.0))
        # the back and the ends
        self.wall(m, "pf_steel", (xb, z1), (xb, z0), 0.0, ytop + 1.0, (1.0, 0.0), u_len=3.0, v_rng=(1.0, 0.0))
        self.box(m, "pf_steel", (xb - 0.05, ytop + 1.0, (z0 + z1) / 2), (0.05, 0.05, (z1 - z0) / 2))
        for z, face in ((z0, -1.0), (z1, 1.0)):
            bot = [_v(px, 0.0, z) for px, _py in prof]
            top = [_v(px, py, z) for px, py in prof]
            m.grid("pf_steel", [bot, top], [[(px / 3.0, 1.0) for px, _py in prof], [(px / 3.0, 1.0 - py / 3.0) for px, py in prof]],
                   facing=lambda _p, face=face: _v(0.0, 0.0, face))
        # the fans: one billboard per two rows, standing on the tread, cut at the aisles
        aisles = [a for a in np.arange(z0 + q["aisle_every"], z1 - 1.0, q["aisle_every"])]
        half = q["aisle"] / 2
        edges = [z0] + [e for a in aisles for e in (a - half, a + half)] + [z1]
        for b, k in enumerate(range(0, rows - 1, cq["rows_per_band"])):
            quarter = [0.0, 0.5, 0.25, 0.75][b % 4]
            xa = x0 + k * tread + 0.15
            ya = y0 + k * rise + cq["lift"]
            h = cq["rows_per_band"] * rise + cq["extra"]
            lean = cq["lean"] * cq["rows_per_band"] * tread
            for e0, e1 in zip(edges[0::2], edges[1::2]):
                pb = [_v(xa, ya, e0), _v(xa, ya, e1)]
                pt = [_v(xa + lean, ya + h, e0), _v(xa + lean, ya + h, e1)]
                v0, v1 = e0 * cq["v_per_m"], e1 * cq["v_per_m"]
                m.grid("crowd", [pb, pt], [[(quarter + 0.2425, v0), (quarter + 0.2425, v1)],
                                           [(quarter + 0.0075, v0), (quarter + 0.0075, v1)]],
                       facing=lambda _p: _v(-1.0, 0.0, 0.0))
        self.nosebleed = (xb - 0.6, ytop + 1.6, -20.0)

    # -- the practice clocks ----------------------------------------------------------------------------------
    def _clocks(self):
        """Two portable practice scoreboards on posts behind the end zones, facing the field; the game's digits go onto
        their faces (``adjust_digits``)."""
        m = self.mesh("pf_clocks")
        c = self.p["clock"]
        for q in self.p["clocks"]:
            x, z = q["x"], q["z"]
            fx, fz = q["face"]
            face = _v(fx, 0.0, fz)
            right = _v(-fz, 0.0, fx)                 # the viewer's right, facing the clock
            cy = c["bottom"] + c["h"] / 2
            centre = _v(x, cy, z)
            self.box(m, "pf_dark", (x, cy, z), (c["w"] / 2, c["h"] / 2, c["depth"] / 2),
                     axes=(tuple(right), (0.0, 1.0, 0.0), tuple(face)), uvscale=0.5)
            fc = centre + face * (c["depth"] / 2 + 0.02)
            hw, hh = c["w"] / 2 - 0.05, c["h"] / 2 - 0.05
            up = _v(0.0, 1.0, 0.0)
            self.quad(m, "pf_clock", fc - right * hw - up * hh, fc + right * hw - up * hh, fc + right * hw + up * hh,
                      fc - right * hw + up * hh, (0, 1), (1, 1), (1, 0), (0, 0), face)
            for s in (-1, 1):
                px = centre + right * s * (c["w"] / 2 - 0.5)
                self.box(m, "pf_steel", (px[0], c["bottom"] / 2, px[2]), (0.09, c["bottom"] / 2, 0.09))
            self.clock_frames.append(dict(centre=tuple(fc), face=tuple(face), right=tuple(right), w=c["w"], h=c["h"]))

    #: the live feed's picture inside the jumbo_tron render target (u5b and u6, PROVED IN GAME: a 640 x 448 image at the
    #: top left of a 1024 x 512 texture), cropped to the board's 16:9 (640 x 360 of it, centred): never stretched
    FEED_UV = (0.0, 640 / 1024, (448 - 360) / 2 / 512, ((448 - 360) / 2 + 360) / 512)

    def _video_board(self):
        """The practice video board: a dark cabinet on two steel legs with the game's live feed on its face (16:9)."""
        m = self.mesh("pf_video_board")
        q = self.p["video_board"]
        x, z, w, h, b, dp = q["x"], q["z"], q["w"], q["h"], q["bottom"], q["depth"]
        fx, fz = q["face"]
        face = _v(fx, 0.0, fz)
        right = _v(-fz, 0.0, fx)
        cy = b + h / 2
        self.box(m, "pf_dark", (x, cy, z), (w / 2 + 0.3, h / 2 + 0.3, dp / 2), axes=(tuple(right), (0.0, 1.0, 0.0),
                                                                                       tuple(face)), uvscale=0.5)
        fc = _v(x, cy, z) + face * (dp / 2 + 0.03)
        up = _v(0.0, 1.0, 0.0)
        u0, u1, v0, v1 = self.FEED_UV
        self.quad(m, "jumbo_tron", fc - right * w / 2 - up * h / 2, fc + right * w / 2 - up * h / 2,
                  fc + right * w / 2 + up * h / 2, fc - right * w / 2 + up * h / 2, (u0, v1), (u1, v1), (u1, v0), (u0, v0),
                  face)
        for s_ in (-1, 1):
            leg = _v(x, 0.0, z) + right * s_ * (w / 2 - 1.5) - face * 0.2
            self.box(m, "pf_steel", (leg[0], b / 2, leg[2]), (0.25, b / 2, 0.25))
        self.board_centre = tuple(fc)

    # -- the gear -----------------------------------------------------------------------------------------------
    def _gear(self):
        """Blocking sleds (the Broncos' camp, R12), a row of tackling dummies, JUGS machines and pop-up tents (the
        Eagles', 49ers' and Chargers' camps)."""
        m = self.mesh("pf_gear")
        for q in self.p["sleds"]:
            # a blocking sled (R12): two skids, a frame bar, and per pad an upright and a black pad at chest height
            x, z, n = q["x"], q["z"], q["pads"]
            L = 1.1 * n + 0.5
            for s in (-1, 1):
                self.box(m, "pf_steel", (x + s * 0.75, 0.07, z), (0.06, 0.07, L / 2))
            self.box(m, "pf_steel", (x - 0.45, 0.62, z), (0.05, 0.05, L / 2))
            for k in range(n):
                pz = z - L / 2 + 0.6 + k * 1.1
                self.box(m, "pf_steel", (x - 0.1, 0.62, pz), (0.36, 0.04, 0.04))
                self.box(m, "pf_steel", (x + 0.22, 0.52, pz), (0.04, 0.46, 0.04))
                self.box(m, "pf_pad", (x + 0.42, 0.98, pz), (0.2, 0.40, 0.30), uvscale=0.9)
        d = self.p["dummies"]
        for z in np.linspace(d["z0"], d["z1"], d["n"]):
            self.prism(m, "pf_pad", (d["x"], 0.0, float(z)), (d["x"], 1.65, float(z)), 0.30, 0.27, sides=8, uv_h=1.0)
        for (x, z) in self.p["jugs"]:
            self.box(m, "pf_steel", (x, 0.5, z), (0.04, 0.5, 0.04))
            for a in (0.0, 2.1, 4.2):
                self.box(m, "pf_steel", (x + 0.35 * math.cos(a), 0.3, z + 0.35 * math.sin(a)), (0.03, 0.3, 0.03))
            self.box(m, "pf_dark", (x, 1.15, z), (0.25, 0.28, 0.42))
            self.box(m, "pf_white", (x, 1.15, z + 0.25), (0.22, 0.22, 0.02))
        for (x, z) in self.p["tents"]:
            w, hh, hr = 1.5, 2.4, 3.3
            top = _v(x, hr, z)
            corners = [_v(x - w, hh, z - w), _v(x + w, hh, z - w), _v(x + w, hh, z + w), _v(x - w, hh, z + w)]
            ti = m.v(top, (0.5, 0.0), (0.0, 1.0, 0.0))
            ci = []
            for k, p in enumerate(corners):
                ci.append(m.v(p, ((k % 2) * 1.0, 1.0), (0.0, 1.0, 0.0)))
            for k in range(4):
                m.strip("pf_canvas", [ti, ci[(k + 1) % 4], ci[k]])
            for p in corners:
                self.box(m, "pf_steel", (p[0], hh / 2, p[2]), (0.03, hh / 2, 0.03))
            for k in range(4):
                a, b = corners[k], corners[(k + 1) % 4]
                self.wall(m, "pf_canvas", (a[0], a[2]), (b[0], b[2]), hh - 0.25, hh, tuple(
                    np.array([(a[0] + b[0]) / 2 - x, (a[2] + b[2]) / 2 - z]) / max(1e-6, np.hypot((a[0] + b[0]) / 2 - x,
                                                                                                  (a[2] + b[2]) / 2 - z))),
                          u_len=3.0, double=True)

    def _pavilion(self):
        """A white frame pavilion along the home side (R07): posts every bay, a gabled canvas roof, a valance, open
        sides."""
        m = self.mesh("pf_gear")
        q = self.p["pavilion"]
        x0, x1, z0, z1, e, r = q["x0"], q["x1"], q["z0"], q["z1"], q["eave"], q["ridge"]
        xm = (x0 + x1) / 2
        for side, xe in ((-1, x0), (1, x1)):
            a, b = _v(xe, e, z0), _v(xe, e, z1)
            c, d = _v(xm, r, z1), _v(xm, r, z0)
            self.quad(m, "pf_canvas", a, b, c, d, (0.0, 1.0), ((z1 - z0) / 4.0, 1.0), ((z1 - z0) / 4.0, 0.0), (0.0, 0.0),
                      (side * (r - e), abs(xe - xm), 0.0))
            dn = _v(0.0, -0.02, 0.0)                   # the underside 2 cm below the top (never coplanar)
            self.quad(m, "pf_canvas", b + dn, a + dn, d + dn, c + dn, (0.0, 1.0), ((z1 - z0) / 4.0, 1.0),
                      ((z1 - z0) / 4.0, 0.0), (0.0, 0.0), (-side * (r - e), -abs(xe - xm), 0.0))
            self.wall(m, "pf_canvas", (xe, z0), (xe, z1), e - 0.35, e, (float(side), 0.0), u_len=4.0, double=True)
        for zz, face in ((z0, -1.0), (z1, 1.0)):
            for f_, off in ((face, 0.0), (-face, -face * 0.02)):
                ia = m.v(_v(x0, e, zz + off), (0.0, 1.0), (0.0, 0.0, f_))
                ib = m.v(_v(x1, e, zz + off), (1.0, 1.0), (0.0, 0.0, f_))
                ic = m.v(_v(xm, r, zz + off), (0.5, 0.0), (0.0, 0.0, f_))
                tri = [ia, ib, ic]
                a_, b_, c_ = (np.array(m.P[i]) for i in tri)
                if np.dot(np.cross(b_ - a_, c_ - a_), _v(0.0, 0.0, f_)) < 0:
                    tri = [ib, ia, ic]
                m.strip("pf_canvas", tri)
        for zz in np.arange(z0, z1 + 0.01, q["bay"]):
            for xe in (x0, x1):
                self.box(m, "pf_steel", (xe, e / 2, float(zz)), (0.05, e / 2, 0.05))
        # tables under it
        for zz in np.arange(z0 + 3.0, z1 - 2.0, 6.5):
            self.box(m, "pf_white", (xm, 0.75, float(zz)), (0.4, 0.03, 1.2))

    # -- outside --------------------------------------------------------------------------------------------------
    def _parking(self):
        """Parking behind the headquarters and beside the field house, and the road (the retail cityscape's parking
        and road textures)."""
        m = self.mesh("pf_site")
        for x0, x1, z0, z1 in self.p["parking"]:
            self.rect_xz(m, "pf_parking", x0, x1, z0, z1, 0.02, uv=(x0 / 16.0, x1 / 16.0, z0 / 12.0, z1 / 12.0))
        r = self.p["road"]
        self.rect_xz(m, "pf_road", -r["x"], r["x"], r["z"] - r["w"] / 2, r["z"] + r["w"] / 2, 0.02,
                     uv=(-r["x"] / 16.0, r["x"] / 16.0, 0.0, 1.0))

    def _trees(self):
        """Tree lines outside the fence: rows of the retail cityscape's tree-row billboards (trees_01, trees_02, a stand of
        trees per quad) in staggered rows, and single crossed trees (trees_03, trees_04) in front of them and round the
        buildings; alpha-tested, drawn from both sides; deterministic."""
        m = self.mesh("pf_trees")
        t = self.p["trees"]
        r = _rng(3207)
        keep_out = [(x0 - 6, x1 + 6, z0 - 6, z1 + 6) for x0, x1, z0, z1 in self.p["parking"]]
        rd = self.p["road"]
        keep_out.append((-rd["x"], rd["x"], rd["z"] - rd["w"] / 2 - 5, rd["z"] + rd["w"] / 2 + 5))
        fh, hq = self.p["field_house"], self.p["hq"]
        keep_out.append((fh["x0"] - 8, fh["x1"] + 8, fh["z0"] - 8, fh["z1"] + 8))
        keep_out.append((hq["x0"] - 8, hq["x1"] + 8, hq["z_back"] - 8, hq["z_front"] + 8))

        def clear(x, z):
            return not any(a <= x <= b and c <= z <= d for a, b, c, d in keep_out)

        def row(x0, z0, x1, z1, mats, depth):
            """Billboards of about ``row_w`` along the line from (x0, z0) to (x1, z1), ``depth`` rows deep."""
            L = math.hypot(x1 - x0, z1 - z0)
            dx, dz = (x1 - x0) / L, (z1 - z0) / L
            nx, nz = -dz, dx
            for k in range(depth):
                off = k * 9.0
                s_ = r.uniform(0, t["row_w"] * 0.5)
                while s_ < L:
                    w = t["row_w"] * r.uniform(0.8, 1.1)
                    h = r.uniform(*t["row_h"]) * (1.0 + 0.08 * k)
                    cx = x0 + dx * (s_ + w / 2) + nx * off + r.uniform(-2, 2)
                    cz = z0 + dz * (s_ + w / 2) + nz * off + r.uniform(-2, 2)
                    if clear(cx, cz):
                        mat = mats[int(r.integers(0, len(mats)))]
                        p0 = (cx - dx * w / 2, 0.0, cz - dz * w / 2)
                        p1 = (cx + dx * w / 2, 0.0, cz + dz * w / 2)
                        self.quad(m, mat, p0, p1, (p1[0], h, p1[2]), (p0[0], h, p0[2]), (0.0, 1.0), (1.0, 1.0),
                                  (1.0, 0.0), (0.0, 0.0), (-nx, 0.0, -nz))
                    s_ += w * r.uniform(0.62, 0.8)

        rows = ("pf_tree1", "pf_tree2")
        (wx0, wx1), (ex0, ex1) = t["west"], t["east"]
        (nz0, nz1), (sz0, sz1) = t["north"], t["south"]
        row(wx1, -300.0, wx1, 300.0, rows, t["rows"])          # the west band's face toward the fields, rows behind it
        row(ex0, 300.0, ex0, -300.0, rows, t["rows"])
        row(-140.0, nz0, 140.0, nz0, rows, t["rows"])
        row(140.0, sz1, -140.0, sz1, rows, t["rows"])
        # single trees in front of the rows and round the buildings
        singles = []
        while len(singles) < t["singles"]:
            side = int(r.integers(0, 4))
            if side == 0:
                x, z = r.uniform(wx1 - 2, wx1 + 10), r.uniform(-260, 260)
            elif side == 1:
                x, z = r.uniform(ex0 - 10, ex0 + 2), r.uniform(-260, 260)
            elif side == 2:
                x, z = r.uniform(-140, 140), r.uniform(nz0 - 8, nz0 + 2)
            else:
                x, z = r.uniform(-140, 140), r.uniform(sz1 - 2, sz1 + 8)
            if clear(x, z):
                singles.append((x, z))
        for (x, z) in singles:
            h = r.uniform(*t["h"])
            w = h * r.uniform(0.75, 0.95)
            mat = ("pf_tree3", "pf_tree4")[int(r.integers(0, 2))]
            a = r.uniform(0, math.pi)
            for da in (0.0, math.pi / 2):
                c, s_ = math.cos(a + da), math.sin(a + da)
                p0, p1 = (x - c * w / 2, 0.0, z - s_ * w / 2), (x + c * w / 2, 0.0, z + s_ * w / 2)
                p2, p3 = (x + c * w / 2, h, z + s_ * w / 2), (x - c * w / 2, h, z - s_ * w / 2)
                self.quad(m, mat, p0, p1, p2, p3, (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0), (-s_, 0.0, c))

    def _neighbourhood(self):
        """Beyond the trees: the retail cityscape's aerial ground (city blocks) on a ring past the tree lines, and a few low
        office blocks in stone and glass (a suburban campus's neighbours; neutral, no names)."""
        m = self.mesh("pf_far")
        q, g = self.p["far"], self.p["ground"]
        r0, R = q["r0"], g["r"]
        for x0, x1, z0, z1 in ((-R, -r0, -R, R), (r0, R, -R, R), (-r0, r0, r0, R), (-r0, r0, -R, -r0)):
            self.rect_xz(m, "pf_city", x0, x1, z0, z1, 0.01, uv=(x0 / 60.0, x1 / 60.0, z0 / 60.0, z1 / 60.0))
        rng = _rng(q["seed"])
        placed = 0
        while placed < q["blocks"]:
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(r0 + 30.0, 520.0)
            x, z = d * math.cos(a), d * math.sin(a)
            w, dp, h = rng.uniform(30, 60), rng.uniform(20, 36), rng.uniform(9, 18)
            ang = rng.uniform(0, math.pi)
            U = (math.cos(ang), 0.0, math.sin(ang))
            Wd = (-math.sin(ang), 0.0, math.cos(ang))
            self.box(m, "pf_stone" if placed % 2 else "LIGHT_pf_glass", (x, h / 2, z), (w / 2, h / 2, dp / 2),
                     axes=(U, (0.0, 1.0, 0.0), Wd), uvscale=1 / 5.0)
            self.box(m, "pf_roof", (x, h + 0.3, z), (w / 2 + 0.3, 0.3, dp / 2 + 0.3), axes=(U, (0.0, 1.0, 0.0), Wd),
                     uvscale=1 / 8.0)
            placed += 1

    def _horizon(self):
        """The horizon: a ring of the retail cityscape's hills line (the lower half of its skyline texture) round the site
        (no city skyline: the facility is neutral)."""
        m = self.mesh("pf_horizon")
        q = self.p["horizon"]
        n = q["points"]
        ang = np.linspace(0.0, 2 * math.pi, n + 1)
        R = q["r"]
        bot = [_v(R * math.cos(a), q["bottom"], R * math.sin(a)) for a in ang]
        top = [_v(R * math.cos(a), q["top"], R * math.sin(a)) for a in ang]
        us = [k / 6.0 for k in range(n + 1)]
        m.grid("pf_horizon", [bot, top], [[(u, 0.985) for u in us], [(u, 0.515) for u in us]],
               facing=lambda p: _v(-p[0], 0.0, -p[2]))


def build(venue=VENUE, params=None):
    return PracticeFacility(params, venue).build()


# ------------------------------------------------------------------------------------------------ assembly

KEEP_PREFIXES = ("sideline_", "pyG", "banners_")
KEEP_YARD = {"yardfront", "yardside"}
KEEP_MATERIALS_BY_CODE = {"crowd", "jumbo_tron"}
CLASS_OPAQUE, CLASS_ALPHA = sm.CLASS_OPAQUE, sm.CLASS_ALPHA

#: new materials: texture key, render class. ``city:`` keys are the retail cityscape's own textures of the same bundle.
MATERIALS = {
    "pf_ground": ("city:grass_01", CLASS_OPAQUE), "pf_path": ("pf_path", CLASS_OPAQUE),
    "pf_field_strip": ("pf_field_strip", CLASS_OPAQUE), "pf_turf_strip": ("pf_turf_strip", CLASS_OPAQUE),
    "pf_endzone_grass": ("pf_endzone_grass", CLASS_OPAQUE), "pf_endzone_turf": ("pf_endzone_turf", CLASS_OPAQUE),
    "pf_paint": ("pf_paint", CLASS_OPAQUE), "pf_yellow": ("pf_yellow", CLASS_OPAQUE), "pf_dark": ("pf_dark", CLASS_OPAQUE),
    "pf_fh_wall": ("pf_fh_wall", CLASS_OPAQUE), "LIGHT_pf_clere": ("LIGHT_pf_clere", CLASS_OPAQUE),
    "pf_white": ("pf_white", CLASS_OPAQUE), "pf_door": ("pf_door", CLASS_OPAQUE), "pf_fh_roof": ("pf_fh_roof", CLASS_OPAQUE),
    "LIGHT_pf_led": ("LIGHT_pf_led", CLASS_OPAQUE), "pf_stone": ("pf_stone", CLASS_OPAQUE),
    "LIGHT_pf_glass": ("LIGHT_pf_glass", CLASS_OPAQUE), "pf_roof": ("pf_roof", CLASS_OPAQUE),
    "pf_steel": ("pf_steel", CLASS_OPAQUE), "pf_windscreen": ("pf_windscreen", CLASS_OPAQUE),
    "pf_scissor": ("pf_scissor", CLASS_ALPHA), "pf_canvas": ("pf_canvas", CLASS_OPAQUE),
    "pf_bleacher": ("pf_bleacher", CLASS_OPAQUE), "pf_clock": ("pf_clock", CLASS_OPAQUE), "pf_pad": ("pf_pad", CLASS_OPAQUE),
    "pf_numbers": ("pf_numbers", CLASS_ALPHA), "pf_city": ("city:city_premipped", CLASS_OPAQUE),
    "pf_parking": ("city:parking_premipped", CLASS_OPAQUE), "pf_road": ("city:road_01", CLASS_OPAQUE),
    "pf_tree1": ("city:trees_01", CLASS_ALPHA), "pf_tree2": ("city:trees_02", CLASS_ALPHA),
    "pf_tree3": ("city:trees_03", CLASS_ALPHA), "pf_tree4": ("city:trees_04", CLASS_ALPHA),
    "pf_horizon": ("city:skyline_01", CLASS_ALPHA),
}
#: materials drawn with their night variant in the night bundles (the art's ``_night`` drawings)
NIGHT_ART = {"LIGHT_pf_clere", "LIGHT_pf_glass", "LIGHT_pf_led"}

#: baked vertex light (grey level) per material: day, afternoon, night (DESIGN, from the renders beside the photos)
BASE = {
    "pf_ground": (206, 212, 96), "pf_path": (212, 214, 100), "pf_field_strip": (214, 218, 104),
    "pf_turf_strip": (214, 218, 104), "pf_endzone_grass": (214, 218, 104), "pf_endzone_turf": (214, 218, 104),
    "pf_paint": (228, 230, 120), "pf_yellow": (226, 228, 118), "pf_dark": (214, 216, 110), "pf_fh_wall": (220, 222, 104),
    "LIGHT_pf_clere": (222, 224, 255), "pf_white": (224, 226, 110), "pf_door": (212, 214, 100), "pf_fh_roof": (218, 222, 88),
    "LIGHT_pf_led": (220, 222, 255), "pf_stone": (218, 222, 100), "LIGHT_pf_glass": (220, 224, 255),
    "pf_roof": (210, 214, 80), "pf_steel": (214, 216, 110), "pf_windscreen": (212, 214, 100), "pf_scissor": (214, 216, 110),
    "pf_canvas": (226, 228, 118), "pf_bleacher": (214, 216, 112), "pf_clock": (220, 222, 150), "pf_pad": (214, 216, 110),
    "pf_parking": (212, 214, 84), "pf_road": (212, 214, 84), "pf_tree1": (206, 204, 70), "pf_tree2": (206, 204, 70),
    "pf_tree3": (206, 204, 70), "pf_tree4": (206, 204, 70), "pf_horizon": (216, 214, 64), "pf_numbers": (228, 230, 120),
    "pf_city": (176, 178, 54),
    "crowd": (222, 216, 120),
}
#: the sun (DESIGN, a neutral site): by day high over the away side and the -z end, in the afternoon low from the home side
SUN = {"d": (0.38, 0.84, -0.40), "a": (-0.72, 0.42, -0.55), "n": None}
TINT = {"d": (1.0, 1.0, 1.0), "a": (1.0, 0.94, 0.86), "n": (0.90, 0.96, 1.10)}
OVERCAST = {"r": (0.80, 0.83, 0.88), "s": (0.92, 0.94, 0.98)}
#: at night the poles light the fields round them (a pool of light with a soft falloff)
NIGHT_POOL = dict(gain=150.0, radius=46.0)


def light(mat, P, N, tod, weather, poles=()):
    """Vertex colours (n, 4) for one material's vertices of one bundle."""
    base = BASE.get(mat, (210, 212, 100))[{"d": 0, "a": 1, "n": 2}[tod]]
    n = len(P)
    if mat == "jumbo_tron":
        # the live feed draws at full brightness in every bundle (u5 and u6's boards)
        out = np.full((n, 4), 255, np.uint8)
        return out
    if mat.startswith("LIGHT_") and tod == "n":
        f = np.full(n, 1.0)
        base = 255
    elif tod == "n":
        f = np.full(n, 1.0)
        if poles and mat != "pf_horizon":
            pool = np.zeros(n)
            L = np.asarray(poles, float)
            for p in L:
                d2 = ((P[:, 0] - p[0]) ** 2 + (P[:, 2] - p[2]) ** 2) / NIGHT_POOL["radius"] ** 2
                pool += 1.0 / (1.0 + d2)
            f = f + np.clip(pool, 0, 2.0) * NIGHT_POOL["gain"] / max(1.0, base)
    else:
        sun = np.array(SUN[tod])
        s = sun / np.linalg.norm(sun)
        nd = np.clip(N @ s, 0, 1)
        f = (0.74 + 0.28 * nd) if tod == "d" else (0.62 + 0.46 * nd)
        if mat in ("pf_tree1", "pf_tree2", "pf_tree3", "pf_tree4"):
            f = np.full(n, 0.92 if tod == "d" else 0.86)
    tint = TINT[tod]
    if weather in OVERCAST and not mat.startswith("LIGHT_"):
        tint = tuple(a * b for a, b in zip(tint, OVERCAST[weather]))
    out = np.zeros((n, 4), np.uint8)
    for k in range(3):
        out[:, k] = np.clip(base * f * tint[k], 0, 255)
    out[:, 3] = 255
    return out


def _rgba(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


#: the textures that take a snow cover in the snow bundles, and a wet darkening in the rain bundles (DESIGN)
SNOW_COVER = {"pf_path": 0.55, "pf_field_strip": 0.45, "pf_turf_strip": 0.45, "pf_endzone_grass": 0.55,
              "pf_endzone_turf": 0.55, "pf_fh_roof": 0.70, "pf_roof": 0.75, "pf_canvas": 0.30, "pf_bleacher": 0.25}
RAIN_GAIN = (0.86, 0.89, 0.93)


def _weather(rgba, key, weather):
    if weather == "d":
        return rgba
    a = rgba.astype(np.float32)
    if weather == "r" and key in SNOW_COVER:
        a[..., :3] *= np.array(RAIN_GAIN, np.float32)
    elif weather == "s" and key in SNOW_COVER:
        k = SNOW_COVER[key]
        a[..., :3] = a[..., :3] * (1 - k) + np.array([214.0, 220.0, 228.0]) * k
    return np.clip(a, 0, 255).astype(np.uint8)


def _textures(venue, tod, weather):
    """{art key: RGBA} of the model's own art for one bundle (the night variants of the LIGHT_ art at night; the snow
    cover and the wet look in the snow and rain bundles)."""
    keys = list(dict.fromkeys(k for k, _c in MATERIALS.values() if not k.startswith("city:")))
    out = {}
    for key in keys:
        name = f"{key}_night" if (tod == "n" and key in NIGHT_ART) else key
        rgba = _rgba(ART_DIR / f"{name}.png")
        if key in GRASS_ART:
            rgba = regrade_green(rgba, texture_mean_for(SURFACE_LOOK, key))
        elif key in TURF_ART:
            rgba = regrade_green(rgba, texture_mean_for(SYNTHETIC_LOOK, key))
        out[key] = _weather(rgba, key, weather)
    return out


def city_textures(retail_bundle):
    """{material name: sb.Texture} of the retail cityscape scene of a bundle (its own textures, native)."""
    ml = sm._ml()
    c = ml.bundle_scenes(retail_bundle)["cityscape"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    return {m.name: sc.textures[m.texture] for m in sc.materials if m.texture is not None}


#: The greens follow job tf's surfaces (main, 2026-09-27: tf is correcting its palette per venue after Noah's note that
#: the turf read too bright; this model takes tf's targets, it does not tune its own). The field scene draws map x rig
#: x screen factor, which tf solves for; the stadium scene draws texture x the baked vertex colour, so the side fields,
#: their end zones and the lawns take tf's day target divided by their own baked light (the lawns a touch darker, as
#: tf's outside grass: OUTSIDE_SHADE). DESIGN; the lab checks the match on screen.
SYNTHETIC_LOOK = "synthetic_fieldturf"
GRASS_ART = ("pf_field_strip", "pf_endzone_grass")
TURF_ART = ("pf_turf_strip", "pf_endzone_turf")


def surface_target(look):
    """tf's on-screen day target (r, g, b) of a look."""
    from . import nfl2k5_modern_surfaces as ms
    return tuple(float(v) for v in ms.LOOKS[look]["targets"]["day"])


def flat_day_light(material):
    """The baked day light (0..1) of a level surface of ``material``: ``light``'s day term with the normal straight up."""
    s = np.array(SUN["d"], float)
    s = s / np.linalg.norm(s)
    return BASE[material][0] * (0.74 + 0.28 * max(0.0, float(s[1]))) / 255.0


def texture_mean_for(look, material, shade=1.0):
    """The texture mean that draws ``shade`` x tf's day target through a material's baked day light (level ground)."""
    light = flat_day_light(material)
    return tuple(v * shade / light for v in surface_target(look))


def lawn_mean():
    from . import nfl2k5_modern_surfaces as ms
    return texture_mean_for(SURFACE_LOOK, "pf_ground", ms.OUTSIDE_SHADE)


LAWN_MEAN = None        # computed from tf's target (see ``lawn_mean``)


def regrade_green(rgba, mean):
    """A copy of an RGBA texture whose green texels' mean becomes ``mean`` (per-channel scale; the white lines and
    anything not green stay)."""
    a = rgba.astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    green = (g >= r) & (g >= b) & (mx > 1) & ((mx - mn) / np.maximum(mx, 1) > 0.12) & (a[..., 3] > 0)
    if not green.any():
        return rgba
    cur = a[green][:, :3].mean(0)
    k = np.array(mean, np.float32) / np.maximum(cur, 1.0)
    out = a.copy()
    out[..., :3] = np.where(green[..., None], np.clip(a[..., :3] * k, 0, 255), a[..., :3])
    return out.astype(np.uint8)


def regrade_palette(tex, mean, snow=False):
    """A copy of a P8 texture whose palette's pixel-weighted mean colour becomes ``mean`` (hue and detail kept by a
    per-channel scale). Snow textures (already white) are only lifted toward the mean's value."""
    from . import nfl2k5_stadium_texture_writer as stw
    pal = bytearray(tex.palette)
    idx = np.frombuffer(tex.pixels[:tex.width * tex.height], np.uint8)
    counts = np.bincount(idx, minlength=256).astype(float)
    bgra = np.frombuffer(bytes(pal), np.uint8).reshape(256, 4).astype(float)
    rgb = bgra[:, [2, 1, 0]]
    cur = (rgb * counts[:, None]).sum(0) / max(1.0, counts.sum())
    if snow:
        return tex
    k = np.array(mean) / np.maximum(cur, 1.0)
    new = np.clip(rgb * k, 0, 255)
    bgra[:, 2], bgra[:, 1], bgra[:, 0] = new[:, 0], new[:, 1], new[:, 2]
    return sb.Texture(bytearray(tex.record), tex.pixels, bytes(np.round(bgra).astype(np.uint8).tobytes()))


#: the digits on the practice clocks' faces (face-local metres: right, up from the face's centre; half width and height)
CLOCK_SLOTS = {"digit_clock_1": (-0.95, 0.47, 0.25, 0.33), "digit_clock_2": (-0.42, 0.47, 0.25, 0.33),
               "digit_colen": (0.0, 0.47, 0.10, 0.33), "digit_clock_3": (0.42, 0.47, 0.25, 0.33),
               "digit_clock_4": (0.95, 0.47, 0.25, 0.33),
               "digit_home_score_L": (-1.67, -0.08, 0.15, 0.20), "digit_home_score_R": (-1.33, -0.08, 0.15, 0.20),
               "digit_playclock_L": (-0.17, -0.08, 0.15, 0.20), "digit_playclock_R": (0.17, -0.08, 0.15, 0.20),
               "digit_away_score_L": (1.33, -0.08, 0.15, 0.20), "digit_away_score_R": (1.67, -0.08, 0.15, 0.20)}


def adjust_digits(shape, sc, model):
    """The game's digits onto the two practice clocks: each material's quads alternate between the clocks (the retail
    scene has two scoreboards), placed in the face's windows (the time on top; home, play clock and away below)."""
    P, _C, UV = sm._vertices(shape)
    P = P.copy()
    counters = {}
    frames = model.clock_frames
    up = np.array([0.0, 1.0, 0.0])
    for sm_ in shape.submeshes:
        mname = sc.materials[sm_.material].name
        idx = sorted({i for _m, ix in sb.decode_words(sm_.words) for i in ix})
        quads = [idx[k:k + 4] for k in range(0, len(idx) - 3, 4)]
        for quad in quads:
            n = counters.get(mname, 0)
            counters[mname] = n + 1
            f = frames[n % len(frames)]
            du, dv, hw, hh = CLOCK_SLOTS.get(mname, (0.0, -0.6, 0.15, 0.2))
            right = np.array(f["right"])
            centre = np.array(f["centre"]) + np.array(f["face"]) * 0.03 + right * du + up * dv
            sm._place_quad(P, UV, quad, centre, right, up, hw, hh)
    sb.set_positions(shape, [tuple(v * 100.0) for v in P])


def flare_points(model):
    """The four flare markers 300 m over the four corner poles (u6's FLARE_HEIGHT; its lab 5, PROVED IN GAME at SoFi: no
    flare discs in view, short night shadows under the feet)."""
    q = model.p["poles"]
    return [(sx * q["x"], sm.FLARE_HEIGHT, z) for sx in (-1, 1) for z in (q["z"][0], q["z"][-1])]


def build_scene(retail_bundle, filename, model):
    """The practice facility's stadium scene for one bundle, built on the retail scene's records the engine reads."""
    ml = sm._ml()
    venue, tod, weather = filename[:3], filename[3], filename[4]
    c = ml.bundle_scenes(retail_bundle)["stadium"]
    _rec, dec = ml._scene(retail_bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    tex_tmpl = next(t for t in sc.textures)
    yard = sm.extract(sc, sc.shapes, lambda n: n in KEEP_YARD, "pf_yard", tmpl_shape)
    digits = sm.extract(sc, sc.shapes, lambda n: n.startswith("digit_"), "pf_digits", tmpl_shape)
    sc.shapes = [s for s in sc.shapes if s.name.startswith(KEEP_PREFIXES)]
    names = {s.name for s in sc.shapes}
    sc.nodes = [n for n in sc.nodes if n.shape_name in names]
    for shp in (yard, digits):
        if shp is not None:
            sc.shapes.append(shp)
            sc.nodes.append(sb.node_for(tmpl_node, shp.name, shp.name))
    tex = _textures(venue, tod, weather)
    city = city_textures(retail_bundle)
    tex_index = {}
    for key, rgba in tex.items():
        sc.textures.append(sb.p8_texture(tex_tmpl, rgba))
        tex_index[key] = len(sc.textures) - 1
    for key in dict.fromkeys(k for k, _c in MATERIALS.values() if k.startswith("city:")):
        sb.require(key[5:] in city, f"{filename}: the retail cityscape lacks {key[5:]}")
        t = city[key[5:]]
        if key == "city:grass_01":
            t = regrade_palette(t, lawn_mean(), snow=weather == "s")
        sc.textures.append(t)
        tex_index[key] = len(sc.textures) - 1
    for name, (key, cls) in MATERIALS.items():
        tmpl = sm._template_material(sc, cls)
        sc.materials.append(sb.Material(bytearray(tmpl.record), name, tex_index[key], None))
    mat_ix = {m.name: i for i, m in enumerate(sc.materials)}
    poles = [p for p in model.light_points]
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
            C[idxs] = light(mat, P[idxs] / 100.0, N[idxs], tod, weather, poles=poles)
            subs.append((mat_ix[mat], sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(strips))))
        shape = sb.static_shape(tmpl_shape, mesh.name, [tuple(p) for p in P], [tuple(x) for x in C],
                                [tuple(u) for u in UV], subs)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, mesh.name, mesh.name))
    if digits is not None:
        adjust_digits(digits, sc, model)
    lights = model.light_points
    glows = [m for m in sc.markers if m.name.startswith("marker_light")]
    for i, m in enumerate(glows):
        p = lights[i % len(lights)]
        struct.pack_into("<3f", m.record, 0x10, *(v * 100 for v in p))
        # 0x7F210 registers a light glow at every marker whose name holds "light"; u6 and st (labs at SoFi and
        # Highmark, PROVED IN GAME; at open-air Highmark the glow sprites showed by day) keep the records and positions
        # but not the word. The LED heads' LIGHT_ texture carries the lit look at night.
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
    for i in sorted({m.texture for m in sc.materials if m.name.startswith("digit_") and m.texture is not None}):
        sc.textures[i] = sb.p8_texture(sc.textures[i], sm.led_segment())
    for s in sc.shapes:
        for sm_ in s.submeshes:
            struct.pack_into("<H", sm_.record, 0, remap_m[sm_.material])
    return sc


def model_bundle(retail_bundle, filename, model=None, *, cameras=None):
    """(bundle bytes, info): the retail bundle with its cityscape collapsed (its textures now serve the stadium scene),
    its stadium scene replaced by the practice facility and its intro cameras rewritten when ``cameras`` gives the
    shots. The stretch from the cityscape to the end of the cameras keeps its length, so the bundle keeps its size."""
    ml = sm._ml()
    tx = ml._tools()[0]
    model = model or build(venue=filename[:3])
    sc = build_scene(retail_bundle, filename, model)
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
    chunk, info = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, sm._chunk_span(retail_bundle, st),
                                      stored=room)
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
                     retail_city=city.system_bytes + city.video_bytes, city_decoded=len(cdec),
                     vertices=sum(s.vertex_count for s in sc.shapes))


# ------------------------------------------------------------------------------------------------ the field

#: The practice field (the game's own field scene, the retail grass-grid layout kept): natural Kentucky bluegrass in
#: job tf's G-A look (``nfl2k5_modern_surfaces`` paints it, as it paints every grass venue), plain end zones (the
#: practice fields in the references carry no end-zone paint), no conference shields and no playoff mark (a practice
#: field carries none), and at midfield the current NFL shield on a square quad at the shield's own proportions, taken
#: from the 2026 venue art folder's league marks when the build has that folder (league marks never ship; without it the
#: midfield keeps the game's own mark and quad). With the team-logo swap on, the midfield material is named ``teamlogo``
#: and the game swaps in the practicing team's logo (the pf report, section 3, P1).
ENDZONE_TEXTURES = ("endzone_N_L", "endzone_N_M", "endzone_N_R", "endzone_S_L", "endzone_S_M", "endzone_S_R")
CLEARED = ("AFC_shield", "NFC_shield", "playoff_logo")
MIDFIELD = "center_logo"
TEAM_LOGO = "teamlogo"
MIDFIELD_HALF = 5.0          # metres: a 10 m square midfield mark (about 11 yards)
SURFACE_LOOK = "grass_bluegrass"


def _field_shape(rec, name):
    return sm._field_shape(rec, name)


def square_midfield(out, rec, half=MIDFIELD_HALF):
    """The midfield quad made square (retail s32: 8.46 x 9.16 m) and centred, in place; UVs kept."""
    g = _field_shape(rec, "D_graphic_overlays")
    st0 = sm._stream(g, 0)
    idx = sm._submesh_vertices(rec, out, g, MIDFIELD)
    sb.require(len(idx) == 4, "the midfield mark is not one quad")
    for i in idx:
        x, y, z = struct.unpack_from("<3f", out, st0["offset"] + st0["stride"] * i)
        struct.pack_into("<3f", out, st0["offset"] + st0["stride"] * i, math.copysign(half * 100.0, x), y,
                         math.copysign(half * 100.0, z))
    return len(idx)


def rename_midfield(out, rec, name=TEAM_LOGO):
    """The midfield material renamed in place (its UTF-16 name string is referenced by that material record only, PROVED
    OFFLINE on the nine retail s32 fields; the new name is shorter and zero-padded). The game's field swap then gives it
    the practicing team's ``logo`` TXTR when the team-logo table is installed (the pf report, P1)."""
    m = next((m for m in rec["materials"] if m["name"] in (MIDFIELD, name)), None)
    sb.require(m is not None, "the field has no midfield material")
    at = m["name_target"]
    old = (m["name"] + "\0").encode("utf-16le")
    sb.require(bytes(out[at:at + len(old)]) == old, "the midfield material's name is not where the scene says")
    refs = [pos for pos in range(0, len(out) - 3) if pos % 4 == 0 and struct.unpack_from("<i", out, pos)[0]
            and pos - 1 + struct.unpack_from("<i", out, pos)[0] == at]
    sb.require(refs == [m["record_offset"]], "another record shares the midfield material's name")
    new = (name + "\0").encode("utf-16le")
    sb.require(len(new) <= len(old), "the new name is longer than the old one")
    out[at:at + len(old)] = new + bytes(len(old) - len(new))
    return at


def midfield_master(shield, size=(256, 256)):
    """The 4x master (a PIL RGBA image) of the practice field's midfield texture of ``size`` from the current NFL shield
    (an RGBA master from the 2026 venue art folder's league marks, which never ship): the shield at its own proportions,
    centred with a clear margin in a square (the midfield quad is made square to carry it)."""
    from PIL import Image
    import numpy as np
    S = 4 * max(size)
    box = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m = Image.fromarray(np.asarray(shield, dtype=np.uint8), "RGBA")
    bbox = m.getbbox()
    m = m.crop(bbox) if bbox else m
    inner = int(S * 0.84)
    k = inner / max(m.width, m.height)
    m = m.resize((max(1, int(round(m.width * k))), max(1, int(round(m.height * k)))), Image.LANCZOS)
    box.alpha_composite(m, ((S - m.width) // 2, (S - m.height) // 2))
    return box


def midfield_art(shield, size=(256, 256)):
    """The midfield texture (RGBA array of ``size``): ``midfield_master`` reduced."""
    from PIL import Image
    import numpy as np
    return np.asarray(midfield_master(shield, size).resize(tuple(size), Image.LANCZOS).convert("RGBA"),
                      dtype=np.uint8).copy()


def league_shield(art_root):
    """The current NFL shield (RGBA master) from the 2026 venue art folder's league marks, or None."""
    if not art_root:
        return None
    from . import nfl2k5_modern_venues_2026 as mv
    mark = mv.load_league_marks(art_root).get("nfl_shield")
    return None if mark is None else mark["rgba"]


def paint_field(decoded, rec, system, name, *, cap=256, team_logo=False, shield=None):
    """The practice field's own art on one decoded field scene (sizes and layout kept, before the surface look): plain
    grass end zones and the conference shields and the playoff mark cleared; at midfield the current NFL shield on a
    square quad when ``shield`` (the venue art folder's master) is given, else the retail mark and quad as they are (the
    game's 2004 shield: league marks never ship); either stays when the team-logo swap finds no logo. With ``team_logo``
    the midfield material is named ``teamlogo``."""
    ml = sm._ml()
    out = bytearray(decoded)
    rows = ml.texture_rows(rec)
    weather = name[4]
    grass = _weather(_rgba(ART_DIR / "pf_endzone_grass.png"), "pf_endzone_grass", weather)
    done = set()
    for mat in ENDZONE_TEXTURES:
        row = rows.get(mat)
        if row is None or int(row["index"]) in done:
            continue
        done.add(int(row["index"]))
        a = sm._resample(grass, row["width"], row["height"])
        ml.write_p8(out, system, row, a, maximum=cap)
    clear = _rgba(FIELD_ART / "pf_clear.png")
    for mat in CLEARED:
        row = rows.get(mat)
        if row is not None:
            ml.write_p8(out, system, row, sm._resample(clear, row["width"], row["height"]), maximum=cap)
    row = rows.get(MIDFIELD)
    if row is not None and shield is not None:
        ml.write_p8(out, system, row, midfield_art(shield, (int(row["width"]), int(row["height"]))), maximum=cap)
        square_midfield(out, rec)
    if team_logo:
        rename_midfield(out, rec)
    return bytes(out)


def surface_look(bundle, decoded, rec, system, name, *, colour_settings=None, cap=256, detail=2):
    """Job tf's G-A (Kentucky bluegrass) surface on the painted field (tf's own painter, which every grass venue takes):
    the colour map mown in bands, the outside grass and the end zones' grass recoloured to it."""
    from . import nfl2k5_modern_surfaces as ms
    t, w = name[3], name[4]
    cls = "rain" if w == "r" else "snow" if w == "s" else {"d": "day", "a": "afternoon", "n": "night"}[t]
    rig = ms.rig_name(cls, t)
    tint = ms.field_tint(bundle)
    painted, receipt = ms.paint_field(decoded, rec, system, look=SURFACE_LOOK, cls=cls, rig=rig,
                                      colour_settings=colour_settings, tint=tint, cap=cap, detail=detail)
    return painted, dict(receipt, look=SURFACE_LOOK, light=cls)


def field_decoded(bundle, name, *, colour_settings=None, cap=256, detail=2, team_logo=False, outer_index=0,
                  tint_bundle=None, shield=None):
    """(decoded field scene, record, system bytes, receipt): the practice field for one retail bundle, not yet fitted.
    The practice field's art goes on the retail field; with Modern colour's settings the grade follows (the art before
    the grade, as Levi's, SoFi and the 2026 venue art compose theirs); job tf's G-A surface goes on last (after the
    grade, as tf paints every home venue), so the end zones' grass takes the surface colour either way (PROVED OFFLINE,
    the pf report section 10). ``tint_bundle`` is the image's own bundle, whose Fldd tint word tf's colour solve reads
    (Modern colour may have written it); the retail bundle when omitted."""
    ml = sm._ml()
    chunk = ml.bundle_scenes(bundle)["field"]
    if colour_settings is None:
        rec, dec = ml._scene(bundle, chunk)
        painted = paint_field(dec, rec, chunk.system_bytes, name, cap=cap, team_logo=team_logo, shield=shield)
        system = chunk.system_bytes
    else:
        from . import nfl2k5_modern_color as colour
        tx = ml._tools()[0]

        def painter(sp, ch):
            r, d = ml._scene(sp, ch)
            return paint_field(d, r, ch.system_bytes, name, cap=cap, team_logo=team_logo, shield=shield), {}
        graded, _ = colour.modern_field_scene(ml.scene_span(bundle, chunk), outer_index=outer_index,
                                              settings=colour_settings, painter=painter)
        gchunk = tx.parse_chunks(graded, allow_trailing=True)[0]
        rec, painted = ml._scene(graded, gchunk)
        system = gchunk.system_bytes
    looked, receipt = surface_look(tint_bundle if tint_bundle is not None else bundle, painted, rec, system, name,
                                   colour_settings=colour_settings, cap=cap, detail=detail)
    return looked, rec, system, dict(receipt, colour=colour_settings is not None, shield=shield is not None)


#: the field's fitting ladder: (surface detail, palette cap)
FIELD_LADDER = ((2, 256), (2, 128), (1, 128), (1, 64), (0, 64), (0, 32))


def field_span(bundle, name, *, colour_settings=None, team_logo=False, outer_index=0, tint_bundle=None, shield=None):
    """(field span of the same size, receipt) for one retail bundle: the practice field painted, graded by Modern colour
    when its settings are given, the surface look on top (``field_decoded``), refitted inside the fixed span."""
    ml = sm._ml()
    tx = ml._tools()[0]
    chunk = ml.bundle_scenes(bundle)["field"]
    span = ml.scene_span(bundle, chunk)
    attempts = []
    for detail, cap in FIELD_LADDER:
        try:
            looked, _rec, _sys, receipt = field_decoded(bundle, name, colour_settings=colour_settings, cap=cap,
                                                        detail=detail, team_logo=team_logo, outer_index=outer_index,
                                                        tint_bundle=tint_bundle, shield=shield)
            after, fit = ml.fit_span(span, looked)
        except (tx.TxtrError, ValueError) as exc:
            attempts.append(f"detail {detail}, {cap} colours: {str(exc)[:100]}")
            continue
        sb.require(len(after) == len(span), f"{name}: the field escaped its span")
        return after, dict(receipt, palette_cap=cap, detail=detail, fit_attempts=attempts, team_logo=team_logo,
                           **{k: v for k, v in (fit or {}).items() if k in ("encoder", "fill", "padding_bytes")})
    raise sb.ScneBuildError(f"{name}: the practice field does not fit its span: " + " | ".join(attempts))


# ------------------------------------------------------------------------------------------------ intro cameras

#: The components each retail s32 intro camera's channel carries (PROVED OFFLINE from the nine retail intro_cameras
#: scenes, the pf report section 1): cameras 1 and 2 all five; camera 3 no z (it plays on z = 0); cameras 4 and 5 no
#: pitch (they play level). A component a channel lacks plays as 0 (u6).
CAMERA_COMPONENTS_PRESENT = ({"x", "y", "z", "pitch", "yaw"}, {"x", "y", "z", "pitch", "yaw"}, {"x", "y", "pitch", "yaw"},
                             {"x", "y", "z", "yaw"}, {"x", "y", "z", "yaw"})

#: DESIGN, pass 1: the facility flyover, one shot per retail camera (written whether or not practice plays it).
#: 1: an aerial from behind the headquarters, drifting over its roof toward the fields and the field house;
#: 2: field level behind the -z end zone by the filming tower, looking up the main field at the field house;
#: 3 (on z = 0): beside the home side's filming tower, panning across the main field to the bleachers and field 3;
#: 4 (level): in front of the field house, gliding along it with the fields and the headquarters beyond;
#: 5 (level): along field 2's sideline toward its goalposts, the field house beyond.
_AERIAL = dict(eye=(-190.0, 85.0, -262.0), target=(-10.0, 4.0, 30.0), fov=40.0, rates=dict(x=6.0, z=5.0))
_ENDZONE = dict(eye=(6.0, 2.6, -84.0), target=(0.0, 10.0, 120.0), fov=44.0, rates=dict(z=2.5, yaw=1.0))
_TOWER = dict(eye=(-43.5, 12.5, 0.0), target=(60.0, 2.0, 18.0), fov=46.0, rates=dict(yaw=-2.5))
_FIELDHOUSE = dict(eye=(48.0, 6.5, 100.0), target=(-40.0, 6.5, -80.0), fov=44.0, rates=dict(x=-4.0))
_ROW = dict(eye=(-64.0, 2.8, -84.0), target=(-86.0, 2.8, 60.0), fov=42.0, rates=dict(z=4.0))
PF_SHOTS = [_AERIAL, _ENDZONE, _TOWER, _FIELDHOUSE, _ROW]


def practice_shots():
    out = []
    for s, present in zip(PF_SHOTS, CAMERA_COMPONENTS_PRESENT):
        yaw, pitch = mm.look_angles(s["eye"], s["target"])
        out.append(sm.effective_shot(dict(s, yaw=yaw, pitch=pitch), present))
    return out


# ------------------------------------------------------------------------------------------------ bundles

VARIANTS = tuple(f"{VENUE}{t}{w}.iff" for t in "dan" for w in "drs")


def _compile(job):
    """Worker: (name, retail bundle) -> (name, model bundle, info)."""
    name, data = job
    out, info = model_bundle(data, name, build(venue=name[:3]), cameras=practice_shots())
    return name, out, info


def _venue_pins():
    """{bundle name: pin (name, name_id, outer, size, retail_sha256)} of the nine s32 bundles, from Modern colour's
    pins (the 2026 venue table holds home venues only)."""
    from . import nfl2k5_modern_color as colour
    doc = json.loads(colour.PINS_PATH.read_text(encoding="utf-8")) if hasattr(colour, "PINS_PATH") else None
    if doc is None:
        doc = json.loads((ROOT / "data" / "nfl2k5_modern_color_pins.json").read_text(encoding="utf-8"))
    out = {}
    for row in doc["bundles"]:
        if row["name"] in VARIANTS:
            out[row["name"]] = dict(name=row["name"], name_id=row["name_id"], outer=row["outer"],
                                    retail_sha256=row["retail_sha256"])
    sb.require(sorted(out) == sorted(VARIANTS), "the s32 bundles are missing from Modern colour's pins")
    return out


def _entry(archive, pin):
    sb.require(pin["outer"] < len(archive.entries), f"{pin['name']}: no such archive entry")
    e = archive.entries[pin["outer"]]
    sb.require(e.name_id == pin["name_id"], f"{pin['name']}: the archive entry differs from the pins")
    return e


def read_retail(source):
    """{bundle name: retail bytes} of the nine s32 bundles, each checked against its pinned SHA-256."""
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
    """(start, end) of the practice facility's stretch: from the cityscape chunk to the end of the intro cameras."""
    ml = sm._ml()
    scenes = ml.bundle_scenes(bundle)
    cam, _dec = mm._cameras_chunk(bundle)
    return scenes["cityscape"].offset, cam.offset + 32 + cam.stored_size


def build_all(source, *, workers=None, progress=None, names=None):
    """{name: (retail bundle, model bundle, info)} for the nine bundles (or ``names``), compiled in parallel."""
    ml = sm._ml()
    retail = read_retail(source)
    out = {}
    for name, model, info in ml.run_jobs(_compile, [(n, retail[n]) for n in (names or VARIANTS)],
                                         workers=workers, progress=progress, label="Practice facility"):
        out[name] = (retail[name], model, info)
    return out


# ------------------------------------------------------------------------------------------------ the build step

PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_practice_field_model_pins/v1"
RECEIPT_SCHEMA = "nfl2k5_practice_field_receipt/v1"
BUILD_CAPTION = "Modern practice facility (experimental)"
HELP_TEXT = (
    "A modern outdoor NFL practice facility replaces the practice field (the college-style bowl every practice mode "
    "loads: main-menu Practice and Basic Training, franchise Free Practice and MyCareer practice): the practice field in "
    "the modern natural-grass look (job tf's surface) with plain end zones, two more practice fields with their goalposts, "
    "the indoor field house, the glass team headquarters, windscreen fences, light poles, filming towers, training-camp "
    "bleachers with fans, a pavilion, a practice video board with the live picture, practice clocks with the game's "
    "digits, sleds and dummies, and lawns, trees and parking round it. With a 2026 venue art folder the current NFL "
    "shield from its league marks goes to midfield; without one the field keeps the game's own mark. The stadium row is "
    "not changed. Off in every preset; appearance in game is unwitnessed."
)
_PINS = None


def model_pins():
    global _PINS
    if _PINS is None:
        sb.require(PINS_PATH.is_file(), "the practice facility pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        sb.require(_PINS.get("schema") == PINS_SCHEMA, "unsupported practice facility pins schema")
    return _PINS


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compile the nine stretches from a retail source and pin them (the field depends on Modern colour's
    settings, so the receipt records it instead). The stretches depend on job tf's surface targets (the greens follow
    them): re-record after tf changes its LOOKS."""
    built = build_all(source, progress=progress)
    bundles = []
    for name in VARIANTS:
        retail, model, info = built[name]
        start, end = stretch(retail)
        bundles.append(dict(name=name, size=len(retail), offset=start, length=end - start,
                            retail_sha256=sha(retail[start:end]), model_sha256=sha(model[start:end]),
                            system=info["system"], video=info["video"], scratch=info["scratch"], shapes=info["shapes"],
                            vertices=info["vertices"]))
    doc = dict(schema=PINS_SCHEMA, label=LABEL, bundles=bundles, source_note="compiled from the retail archive",
               surface_targets={SURFACE_LOOK: list(surface_target(SURFACE_LOOK)),
                                SYNTHETIC_LOOK: list(surface_target(SYNTHETIC_LOOK))})
    Path(out_path).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return doc


def _pin(name):
    return next(p for p in model_pins()["bundles"] if p["name"] == name)


def bundle_state(archive, name):
    """retail / applied / foreign for the practice facility's stretch of one of the nine bundles."""
    pin = _pin(name)
    e = _entry(archive, _venue_pins()[name])
    if e.size != pin["size"]:
        return "foreign"
    have = sha(archive.read(e.virtual_offset + pin["offset"], pin["length"]))
    if have == pin["model_sha256"]:
        return "applied"
    return "retail" if have == pin["retail_sha256"] else "foreign"


def receipt_path(source):
    return Path(str(source) + ".practice-field.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported practice facility receipt")
    return doc


def image_status(source):
    """retail / applied / mixed / foreign across the nine stretches (the row is never written)."""
    ml = sm._ml()
    states = set()
    with ml._outer_image()(str(source)) as archive:
        for name in VARIANTS:
            try:
                states.add(bundle_state(archive, name))
            except (sb.ScneBuildError, ValueError, StopIteration):
                return "foreign"
    if "foreign" in states:
        return "foreign"
    if states == {"applied"}:
        return "applied"
    if states == {"retail"}:
        return "retail"
    return "mixed"


status = image_status


def midfield_named_team_logo(source):
    """True when the image's practice field names its midfield material ``teamlogo`` (the team-logo swap's field)."""
    ml = sm._ml()
    name = VARIANTS[0]
    with ml._outer_image()(str(source)) as archive:
        e = _entry(archive, _venue_pins()[name])
        data = archive.read(e.virtual_offset, e.size)
    rec, _dec = ml._scene(data, ml.bundle_scenes(data)["field"])
    return any(m["name"] == TEAM_LOGO for m in rec["materials"])


def verify(source, *, enabled=True):
    state = image_status(source)
    sb.require(state == ("applied" if enabled else "retail"), f"the practice facility state is {state}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(VARIANTS))


def check_request(source):
    """The build's quick check before any copy: the stretches are retail (or already the practice facility)."""
    state = image_status(source)
    sb.require(state in ("retail", "applied"), f"the practice field packages are {state}; build from a supported retail "
               "source")
    return dict(state=state)


def compose_bundle(retail, current, name, *, colour_settings=None, team_logo=False, outer_index=0, shield=None):
    """(bundle bytes, info): ``current`` (the image's bundle: retail, or graded by Modern colour) with the practice
    facility's stretch (compiled from ``retail``), the practice field (composed on the retail field: the art, Modern
    colour's grade when its settings are given, job tf's G-A look) and tf's G-A detail normal and divots. Every other
    byte of ``current`` stays (Modern colour's tint word among them)."""
    from . import nfl2k5_modern_surfaces as ms
    ml = sm._ml()
    model, info = model_bundle(retail, name, build(venue=name[:3]), cameras=practice_shots())
    start, end = stretch(retail)
    sb.require(len(current) == len(retail) and stretch(current) == (start, end), f"{name}: the bundle layout differs")
    out = bytearray(current)
    out[start:end] = model[start:end]
    chunk = ml.bundle_scenes(retail)["field"]
    field, finfo = field_span(retail, name, colour_settings=colour_settings, team_logo=team_logo, outer_index=outer_index,
                              tint_bundle=current, shield=shield)
    out[chunk.offset:chunk.offset + len(field)] = field
    sites = ms.bundle_sites(bytes(out))
    at, size = sites["normal"]
    normal, variant = ms.normal_span(bytes(out[at:at + size]), ms.LOOKS[SURFACE_LOOK]["detail"])
    out[at:at + size] = normal
    if "divots" in sites:
        at, size = sites["divots"]
        tint = ms.field_tint(bytes(out))
        grass_mean = [v * (t / 255.0) for v, t in zip(finfo["map_mean"], tint)]
        out[at:at + size] = ms.divots_span(bytes(out[at:at + size]), "grass", grass_mean)
    sb.require(len(out) == len(current), f"{name}: the bundle changed size")
    return bytes(out), dict(info, field=finfo, normal=variant)


def _compose(job):
    """Worker: (name, retail bundle, current image bundle, colour settings or None, team logo, outer index, NFL shield or
    None) -> (name, bytes, info)."""
    name, retail, current, settings, team_logo, outer, shield = job
    out, info = compose_bundle(retail, current, name, colour_settings=settings, team_logo=team_logo, outer_index=outer,
                               shield=shield)
    return name, out, info


def apply_to_image(target, *, retail_source, art_root=None, team_logo=False, progress=None, workers=None):
    """Build step (after Modern colour): the practice facility in the nine s32 bundles (the stretch compiled from the
    retail disc, the practice field over the image's own field in job tf's G-A look, tf's detail normal and divots), the
    colour receipt updated so Modern colour still recognizes the bytes. ``team_logo`` names the midfield material for the
    team-logo swap (its executable table is its own option). The row is not written."""
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    ml = sm._ml()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries the practice facility")
    state = image_status(target)
    if state == "applied":
        sb.require(midfield_named_team_logo(target) == bool(team_logo), "the practice field already built here "
                   f"{'lacks' if team_logo else 'carries'} the team-logo midfield; rebuild from the retail disc")
        return dict(state="already_applied", **verify(target))
    sb.require(state == "retail", f"the practice facility needs retail practice field packages (found {state})")
    try:
        colour_receipt = colour.read_image_receipt(target)
    except (OSError, ValueError):
        colour_receipt = None
    settings = colour_receipt.get("settings") if colour_receipt else None
    colour_before = sm._colour_states(target, colour_receipt) if colour_receipt else None
    retail = read_retail(retail_source)
    pins = _venue_pins()
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
    shield = league_shield(art_root)
    jobs = [(n, retail[n], current[n], settings, bool(team_logo), pins[n]["outer"], shield) for n in VARIANTS]
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False, colour=settings is not None,
                   team_logo=bool(team_logo), shield=shield is not None, art_root=str(art_root) if art_root else None,
                   bundles={})
    new_colour = deepcopy(colour_receipt) if colour_receipt else None
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Practice facility")
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the practice facility bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], before_sha256=sha(before), applied_sha256=sha(after),
                                            field={k: v for k, v in (info.get("field") or {}).items()
                                                   if k in ("look", "light", "rig", "palette_cap", "detail", "team_logo",
                                                            "map_mean", "outside_mean")},
                                            normal=info.get("normal"), system=info["system"], video=info["video"])
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
    if new_colour is not None:
        new_colour["practice_field"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if colour_after[n] != new_colour["state"])
        sb.require(not wrong, f"the colour read-back failed after the practice facility: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"the practice facility changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    say("Practice facility: done", 1, 1)
    return dict(verify(target), bundles_written=len(results), colour=settings is not None, team_logo=bool(team_logo),
                shield=shield is not None)


def apply_lab_disc(disc, source, *, art_root=None, team_logo=False, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, retail_source=source, art_root=art_root, team_logo=team_logo, progress=progress)


# ------------------------------------------------------------------------------------------------ CLI

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_practice_field_model")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build-dir", help="compile the model into retail bundles read from a folder (author time)")
    b.add_argument("retail_dir"); b.add_argument("out"); b.add_argument("--names", nargs="*")
    b.add_argument("--no-field", action="store_true")
    b.add_argument("--team-logo", action="store_true")
    b.add_argument("--art-root", default=None, help="the 2026 venue art folder (its current NFL shield goes to midfield)")
    a = sub.add_parser("apply-lab", help="lab only: write the practice facility into a built disc")
    a.add_argument("disc"); a.add_argument("--source", required=True); a.add_argument("--team-logo", action="store_true")
    a.add_argument("--art-root", default=None, help="the 2026 venue art folder (its current NFL shield goes to midfield)")
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
    if args.command == "apply-lab":
        receipt = apply_lab_disc(args.disc, args.source, art_root=args.art_root, team_logo=args.team_logo, progress=say)
        Path(str(args.disc) + ".pf.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", newline="\n")
        print("PF_PRACTICE_FIELD_APPLIED", receipt.get("bundles_written"), receipt.get("state"))
        return 0
    if args.command == "build-dir":
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        info = {}
        for name in args.names or VARIANTS:
            data = (Path(args.retail_dir) / name).read_bytes()
            _n, model, i = _compile((name, data))
            finfo = None
            if not args.no_field:
                field, finfo = field_span(data, name, team_logo=args.team_logo, shield=league_shield(args.art_root))
                chunk = sm._ml().bundle_scenes(data)["field"]
                model = model[:chunk.offset] + field + model[chunk.offset + len(field):]
            (out / name).write_bytes(model)
            info[name] = dict({k: v for k, v in i.items() if k != "cityscape"}, field=finfo)
            print(name, "decoded", i["system"] + i["video"], "retail", i["retail_system"] + i["retail_video"],
                  "+ city", i["retail_city"], "stored", i["stored"], "vertices", i["vertices"],
                  "field cap", (finfo or {}).get("palette_cap"), flush=True)
        (out / "build.json").write_text(json.dumps(info, indent=1, default=str) + "\n", newline="\n")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
