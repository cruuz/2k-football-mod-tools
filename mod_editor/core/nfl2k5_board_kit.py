"""The board kit (st3, jobs st5 and st7, 2026-09-28 and 29): the tier 2 and tier 3 renovations of the retail stadiums
the teams still play in (ST2_RENOVATIONS_PLAN_2026-09-25.md, items 5 to 18): the video boards the renovations brought,
at their published sizes, on a bowl the game already draws, with the seating and structures that changed around them.
st3 built the Superdome, NRG Stadium, Huntington Bank Field, Empower Field at Mile High, Paycor Stadium, Lincoln
Financial Field, Ford Field and M&T Bank Stadium; st2 put Bank of America Stadium, Raymond James Stadium, Northwest
Stadium, Lumen Field, Acrisure Stadium and Arrowhead Stadium on the same reader.

The retail stadium scene stays; the kit replaces only what changed since 2004, as each venue's data file says
(``data/nfl2k5_board_kit/VENUE.json``, one reader for every venue):

* ``replace``: a retail shape is rebuilt without the submeshes the change removes (the old board, its frame, the ad
  strips behind it); the rest of it is copied as it was (positions, the retail vertex colours, UVs); a replace that
  keeps nothing removes the shape outright (one that was only the old board's housing);
* ``drop``: submeshes removed from a retail shape in place (the old boards' feed quads among the digits);
* ``cut``: the triangles of the named materials inside a box (x, y, z and |z| ranges, metres) removed from every shape
  (an old scoreboard's panels, wherever the retail artist grouped them);
* ``move``: the named materials' vertices in a shape moved toward the field, or ``onto`` a straight board's face (the
  game's clock and score digits onto the new board that now stands where the old board carried them; digits the old
  boards did not carry, such as Ford Field's on its fascias, stay where they are);
* ``boards``: new boards along a plan path (a polyline on the wall or on posts), each one ``jumbo_tron`` quad
  across its whole width (or an ``outline`` in the board's plane), cropped to the board's own aspect from the 640 x 448
  feed picture (never stretched), at the loop-gain vertex colour FEED_VERTEX (116: a board that sees itself dims the
  echo instead of saturating to white), with a frame in a retail material behind it and, for a free-standing board, a
  ``structure``: the body behind it, ``depth`` metres deep, in a retail material (a plain one, so a board's back shows
  no stretched texture); ``lean`` tilts a path board's face, its top that many metres toward the field (the retail
  corner boards look down at the field);
* ``paint``: a freed retail texture (one no drawn material uses after the steps above) repainted with an authored image
  from ``data/nfl2k5_board_kit/art`` at the slot's own size (the ribbons' art; the budget does not move);
* ``ribbons``: LED fascia boards, RIBBON_HEIGHT high strips along a plan path on a dark backing, drawing a repainted
  slot only (u along the length, ``tile_m`` a repeat; v across one ``row`` of the art);
* ``panels``: flat parts in retail materials (a deck, a glass front, a roof, a steel frame, a post): the structures that
  replace cut seating or that a renovation added (Cleveland's fan area, M&T Bank Stadium's corner notch suites);
* ``markers``: the jumbotron markers moved to the new boards' centres.

Every venue file also carries ``schema`` (SCHEMA), ``venue`` (the bundle prefix, a row of the 2026 venue art's table),
``name`` (the stadium's 2026 name), ``team``, ``help`` (the phrase the Build tab's help gives it, e.g. "the 2016 boards,
333 x 38 ft"), ``sources`` (the published facts each size and place comes from, and what the retail scene showed) and
``env``, which stays null in this schema: the renovated stadiums keep their retail cityscapes (the environment kit is
for the new models). The steps run in the order above; each is optional. A venue joins the Build option when it has a
data file here and its pins (``python3 -m mod_editor.core.nfl2k5_board_kit record-pins SOURCE --venues sXX``).

The rule on the 2026 venue art (main, 2026-09-28): the kit never covers venue art on a structure that still stands in
2026 (so no ribbon goes over a fascia sign band the venue art repaints); it may remove a venue-art panel that belongs
to a board housing the renovation replaced (the old boards' ad strips, frames and housings), and it cuts such a panel
rather than leave it behind a new surface. covered_venue_art checks every venue's scene against the rule.

The kit adds no texture and no material (the new boards draw the retail ``jumbo_tron`` and frame materials), and every
texture keeps its index and bytes except the freed slots ``paint`` repaints, which nothing else draws and the 2026
venue art never paints (checked against its table): the 2026 venue art (u4) and Modern colour, which write before it in
a build, keep their work, and Modern playing surfaces, after it, leaves the stadium scene alone.

A stadium the kit cannot build on is left as it is (b77 e4, Coach Edwards' photo of 4 October 2026: one stadium, Kansas
City, refused a whole build after hours of work). Every stadium is judged whole, by what its nine bundles hold:

* ``retail`` or ``venues`` (the 2026 venue art's repaint of retail): the boards go on;
* ``applied``: the boards are already there (the kit's own work, or a published SOFTDRINK 2K28 pack: each pack's
  stadium scenes are pinned by hash beside the kit's own pins, so nothing the project ever published reads as foreign);
* ``arrowhead``: Modern Arrowhead wrote Kansas City's scenes (the one stadium both options write); they stay as written;
* anything else (``foreign``): another tool changed it; it stays as it is.

Stadiums that stay are named in the build's result and in the finished-disc message; the build only refuses when no
stadium at all can take the boards. ``check_request`` looks at the source before any copy, ``apply_to_image`` judges the
bytes it is about to write (the earlier steps of the same build may have changed them), and both take ``owned``: the
stadiums another selected option writes in this very build ({"s13": "Modern Arrowhead"}).

EXPERIMENTAL / UNWITNESSED in game.
"""
from __future__ import annotations

import hashlib
import json
from . import exact_math as math
import struct
from functools import lru_cache
from pathlib import Path

from . import nfl2k5_metlife_model as mm        # Mesh, the camera and chunk helpers (landed)
from . import nfl2k5_scne_builder as sb
from . import nfl2k5_sofi_model as sm           # template shapes, submesh extraction, vertex reader (landed)

np = mm.np

OWNER = "nfl2k5_board_kit"
LABEL = "EXPERIMENTAL / UNWITNESSED"
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_board_kit"
SCHEMA = "nfl2k5_board_kit/v1"
PINS_SCHEMA = "nfl2k5_board_kit_pins/v1"

#: the loop-gain rule: the feed quad's vertex colour (the feed is the game's own frame; at 255 a board that sees itself
#: feeds back to white, st at AT&T PROVED IN GAME; 116 dims each echo)
FEED_VERTEX = 116
#: the feed picture inside the 1024 x 512 render target (u, v extents of the 640 x 448 frame)
FEED_U, FEED_V = 0.625, 0.875
FEED_ASPECT = 640.0 / 448.0


def sha(data):
    return hashlib.sha256(data).hexdigest()


def venues():
    """The venues that have a data file, sorted."""
    return tuple(sorted(p.stem for p in DATA_DIR.glob("s??.json")))


@lru_cache(maxsize=None)
def spec(venue):
    p = DATA_DIR / f"{venue}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == SCHEMA and doc.get("venue") == venue, f"{p}: not a {SCHEMA} file for {venue}")
    sb.require(doc.get("env") is None, f"{p}: env must be null (the renovated stadiums keep their retail cityscapes)")
    sb.require(all(isinstance(doc.get(k), str) and doc[k] for k in ("name", "team", "help")) and doc.get("sources"),
               f"{p}: name, team, help and sources are required")
    known = {"schema", "venue", "name", "team", "help", "sources", "env", "replace", "drop", "cut", "move", "boards",
             "paint", "ribbons", "panels", "markers"}
    sb.require(set(doc) <= known, f"{p}: unknown keys {sorted(set(doc) - known)}")
    return doc


def _help_text():
    """The Build tab's help: the kit, then every venue it renovates by name with its own phrase."""
    try:
        docs = sorted((spec(v) for v in venues()), key=lambda d: d["name"])
    except (OSError, ValueError):
        docs = []
    parts = [f"{d['name']} ({d['help']})" for d in docs]
    listed = (", ".join(parts[:-1]) + " and " + parts[-1]) if len(parts) > 1 else "".join(parts)
    return ("The renovations since 2004 in the stadiums the teams still play in, on the retail stadiums: the end-zone "
            "video boards at their 2026 size and place, each showing the live picture cropped to the board's own shape, "
            "with the old boards and their frames taken out and the game clock and scores moved onto the new boards where "
            "the old boards carried them"
            + (f": {listed}" if listed else "") + ". The 2026 venue art and Modern colour keep their work on these "
            "stadiums. A stadium the boards cannot be built on (Kansas City when Modern Arrowhead is on, or one another "
            "tool changed) stays exactly as it is and is named when the disc is ready. "
            "Off in every preset; appearance in game is unwitnessed.")


def feed_crop(aspect):
    """(u0, u1, v0, v1) of the largest centred window of the feed picture at ``aspect`` (width over height)."""
    if aspect >= FEED_ASPECT:
        h = FEED_V * FEED_ASPECT / aspect
        return 0.0, FEED_U, FEED_V / 2 - h / 2, FEED_V / 2 + h / 2
    w = FEED_U * aspect / FEED_ASPECT
    return FEED_U / 2 - w / 2, FEED_U / 2 + w / 2, 0.0, FEED_V


def _ordered(path):
    """The path's points ordered from the left to the right of a viewer at the field centre facing the board, with
    each point's unit normal toward the field (in plan)."""
    P = np.array(path, float)
    c = P.mean(axis=0)
    face = -c / max(1e-9, float(math.np_norm(c)))                 # toward the field (the origin)
    f3 = np.array([face[0], 0.0, face[1]])
    right3 = np.cross(f3, (0.0, 1.0, 0.0))
    right3 /= -math.np_norm(right3)                                 # a viewer facing the board has this on the right
    right = np.array([right3[0], right3[2]])
    if float(math.np_dot(P[-1] - P[0], right)) < 0:
        P = P[::-1]
    N = []
    for i in range(len(P)):
        a, b = P[max(0, i - 1)], P[min(len(P) - 1, i + 1)]
        t = (b - a) / max(1e-9, float(math.np_norm(b - a)))
        n = np.array([-t[1], t[0]])
        if float(math.np_dot(n, face)) < 0:
            n = -n
        N.append(n)
    return P, np.array(N), face


def board_geometry(board):
    """(points, normals, arc lengths) of one board's front face in plan: the path moved ``inset`` metres toward the
    field and trimmed or centred to the board's width along it."""
    P, N, face = _ordered(board["path"])
    inset = float(board.get("inset", 0.3))
    Q = P + N * inset
    seg = math.np_norm(np.diff(Q, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    width = float(board["width"])
    mid = s[-1] / 2.0
    a, b = mid - width / 2.0, mid + width / 2.0
    sb.require(a >= -1e-6 and b <= s[-1] + 1e-6, f"{board['name']}: the path is shorter than the board ({s[-1]:.1f} m)")

    def at(t):
        k = int(np.clip(np.searchsorted(s, t) - 1, 0, len(Q) - 2))
        f = (t - s[k]) / max(1e-9, s[k + 1] - s[k])
        return Q[k] + (Q[k + 1] - Q[k]) * f, N[k] if f < 0.5 else N[k + 1]
    ts = [a] + [float(x) for x in s if a < x < b] + [b]
    pts, nrm = zip(*(at(t) for t in ts))
    return np.array(pts), np.array(nrm), np.array(ts) - a


def _material_colour(sc, name):
    """The mean retail vertex colour (r, g, b, a) of a material over every static shape that draws it, or None."""
    acc, n = np.zeros(4), 0
    for s in sc.shapes:
        if struct.unpack_from("<I", s.record, 0x84)[0] != 0x32 or s.stride(1) != 10:
            continue
        users = [sm_ for sm_ in s.submeshes if sc.materials[sm_.material].name == name]
        if not users:
            continue
        _P, C, _UV = sm._vertices(s)
        for sm_ in users:
            for _mode, ix in sb.decode_words(sm_.words):
                for i in ix:
                    acc += C[i]
                    n += 1
    return tuple(int(round(v)) for v in acc / n) if n else None


def _box_behind(m, material, loop, normal, back0, depth):
    """The board's body: the face loop (3D points, counter-clockwise or not) moved ``back0`` metres behind the face and
    extruded ``depth`` metres further back, with side walls facing out and a back face facing away from the field."""
    n3 = np.array([normal[0], 0.0, normal[1]])
    L = [np.array(p, float) - n3 * back0 for p in loop]
    B = [p - n3 * depth for p in L]
    c = np.mean(np.array(L), axis=0)
    for i in range(len(L)):
        a, b = L[i], L[(i + 1) % len(L)]
        a2, b2 = B[i], B[(i + 1) % len(L)]
        out = (a + b) / 2 - c
        out = out - n3 * float(math.np_dot(out, n3))
        w = float(math.np_norm(b - a))
        m.quad(material, a, b, b2, a2, (0, 0), (w / 4.0, 0), (w / 4.0, depth / 4.0), (0, depth / 4.0),
               facing=lambda p_, o=out: o)
    # the back face: fan triangles over the back loop (the loops here are convex or star-shaped from the centre)
    cb = np.mean(np.array(B), axis=0)
    ic = m.v(tuple(cb), (0.5, 0.5), tuple(-n3))
    ids = [m.v(tuple(p), (0.0, 0.0), tuple(-n3)) for p in B]
    for i in range(len(B)):
        a, b = ids[i], ids[(i + 1) % len(B)]
        pa, pb = np.array(m.P[a]), np.array(m.P[b])
        up = float(math.np_dot(np.cross(pa - cb, pb - cb), -n3)) > 0
        m.strip(material, [ic, a, b] if up else [ic, b, a])


def _outline_mesh(board, feed_colour, frame_colour):
    """An irregular board on a straight path: ``outline`` is its face as (s, h) points, s metres from the left end of
    the path (as a viewer at the field sees it) and h over ``y[0]``; the feed covers the outline's bounding box cropped
    to that box's aspect, and the frame is the outline grown by ``border`` on every side, set back by ``depth``."""
    P, N, _face = _ordered(board["path"])
    sb.require(len(P) == 2, f"{board['name']}: an outline board stands on a straight path")
    inset = float(board.get("inset", 0.3))
    n = N[0]
    left = P[0] + n * inset
    right = (P[1] - P[0]) / float(math.np_norm(P[1] - P[0]))
    y0 = float(board["y"][0])
    O = np.array(board["outline"], float)
    W, H = float(np.ptp(O[:, 0])), float(np.ptp(O[:, 1]))
    s0, h0 = O[:, 0].min(), O[:, 1].min()
    u0, u1, v0, v1 = feed_crop(W / H)
    m = mm.Mesh(board["name"])
    f3 = np.array([n[0], 0.0, n[1]])

    def put(poly, mat, back, uvf):
        poly = [tuple(p) for p in poly]
        tris = sm._triangulate(poly)
        ids = []
        for s_, h_ in poly:
            q = left + right * s_ - n * back
            ids.append(m.v((float(q[0]), y0 + h_, float(q[1])), uvf(s_, h_), tuple(f3)))
        for a, b, c in tris:
            pa, pb, pc = (np.array(m.P[ids[k]]) for k in (a, b, c))
            ok = float(math.np_dot(np.cross(pb - pa, pc - pa), f3)) > 0
            m.strip(mat, [ids[a], ids[b], ids[c]] if ok else [ids[a], ids[c], ids[b]])
    put(O, "jumbo_tron", 0.0, lambda s_, h_: (u0 + (u1 - u0) * (s_ - s0) / W, v1 - (v1 - v0) * (h_ - h0) / H))
    fr = board.get("frame")
    colours = {"jumbo_tron": feed_colour}
    if fr:
        b, d = float(fr.get("border", 0.4)), float(fr.get("depth", 0.12))
        c = O.mean(axis=0)
        grown = [tuple(c + (p - c) * np.array([(W + 2 * b) / W, (H + 2 * b) / H])) for p in O]
        put(grown, fr["material"], d, lambda s_, h_: (s_ / 4.0, h_ / 4.0))
        colours[fr["material"]] = frame_colour
        body = board.get("structure")
        if body:
            loop = [tuple(left + right * s_) for s_, _h in grown]
            loop3 = [(float(q[0]), y0 + h_, float(q[1])) for q, (_s, h_) in zip(loop, grown)]
            _box_behind(m, body["material"], loop3, n, d + 0.02, float(body["depth"]))
    return m, colours


def board_height(board):
    """A path board's face height in metres: its rise ``y``, slanted by ``lean`` (the metres its top edge stands toward
    the field from its bottom edge, as the retail corner boards tilt down at the field)."""
    y0, y1 = (float(v) for v in board["y"])
    return math.hypot(y1 - y0, float(board.get("lean", 0.0)))


def _board_mesh(board, feed_colour, frame_colour):
    """One board: the feed across its whole width (one quad per path segment, u along the arc length) and the frame
    (the same strip, a border wider on every side and set back behind the feed); with ``lean`` the whole face tilts,
    its top that many metres toward the field."""
    if "outline" in board:
        return _outline_mesh(board, feed_colour, frame_colour)
    pts, nrm, ts = board_geometry(board)
    y0, y1 = (float(v) for v in board["y"])
    lean = float(board.get("lean", 0.0))

    def at(p, n, y):
        """A face point at height ``y`` over plan point ``p`` (normal ``n``), leaned toward the field."""
        k = lean * (y - y0) / (y1 - y0)
        return (float(p[0] + n[0] * k), y, float(p[1] + n[1] * k))
    width = ts[-1]
    u0, u1, v0, v1 = feed_crop(width / board_height(board))
    m = mm.Mesh(board["name"])
    top = [at(p, n, y1) for p, n in zip(pts, nrm)]
    bot = [at(p, n, y0) for p, n in zip(pts, nrm)]
    uv_top = [(u0 + (u1 - u0) * t / width, v0) for t in ts]
    uv_bot = [(u0 + (u1 - u0) * t / width, v1) for t in ts]
    face = lambda p_, n=nrm: np.array([n.mean(axis=0)[0], 0.0, n.mean(axis=0)[1]])  # noqa: E731
    m.grid("jumbo_tron", [top, bot], [uv_top, uv_bot], facing=face)
    fr = board.get("frame")
    if fr:
        b, d = float(fr.get("border", 0.4)), float(fr.get("depth", 0.12))
        end = [pts[0] - (pts[1] - pts[0]) / max(1e-9, float(math.np_norm(pts[1] - pts[0]))) * b]
        tail = [pts[-1] + (pts[-1] - pts[-2]) / max(1e-9, float(math.np_norm(pts[-1] - pts[-2]))) * b]
        F = np.array(end + list(pts) + tail)
        NF = np.array([nrm[0]] + list(nrm) + [nrm[-1]])
        F = F - NF * d
        ftop = [at(p, n, y1 + b) for p, n in zip(F, NF)]
        fbot = [at(p, n, y0 - b) for p, n in zip(F, NF)]
        L = np.concatenate([[0.0], np.cumsum(math.np_norm(np.diff(F, axis=0), axis=1))])
        m.grid(fr["material"], [ftop, fbot], [[(t / 4.0, 0.0) for t in L], [(t / 4.0, 1.0) for t in L]], facing=face)
        body = board.get("structure")
        if body:
            sb.require(len(pts) == 2, f"{board['name']}: a structure stands behind a straight board")
            loop3 = [fbot[0], fbot[-1], ftop[-1], ftop[0]]
            _box_behind(m, body["material"], loop3, nrm[0], 0.02, float(body["depth"]))
    colours = {"jumbo_tron": feed_colour}
    if fr:
        colours[fr["material"]] = frame_colour
    return m, colours


def _shape_from_mesh(sc, mesh, colours, tmpl_shape):
    mat_ix = {mt.name: i for i, mt in enumerate(sc.materials)}
    P = np.array(mesh.P) * 100.0
    UV = np.array(mesh.UV)
    C = np.zeros((len(P), 4), np.uint8)
    subs = []
    for mat, strips in mesh.groups.items():
        sb.require(mat in mat_ix, f"{mesh.name}: the retail scene has no material {mat}")
        idx = sorted({i for st in strips for i in st})
        C[idx] = colours[mat]
        subs.append((mat_ix[mat], sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices(strips))))
    return sb.static_shape(tmpl_shape, mesh.name, [tuple(p) for p in P], [tuple(int(x) for x in c) for c in C],
                           [tuple(u) for u in UV], subs)


def _triangles(words):
    """Every triangle (i, j, k) a submesh's push words draw, in the retail winding."""
    out = []
    for mode, ix in sb.decode_words(words):
        if mode == sb.QUADS:
            for k in range(0, len(ix) - 3, 4):
                a, b, c, d = ix[k:k + 4]
                out += [(a, b, c), (a, c, d)]
        elif mode == sb.TRIANGLE_STRIP:
            for k in range(len(ix) - 2):
                a, b, c = ix[k:k + 3]
                if a == b or b == c or a == c:
                    continue
                out.append((a, b, c) if k % 2 == 0 else (b, a, c))
        else:
            out += [tuple(ix[k:k + 3]) for k in range(0, len(ix) - 2, 3)]
    return out


def _in_box(p, box):
    """True when a point (metres) lies in a box of x, y, z (signed) and z_abs ranges (each optional)."""
    x, y, z = p
    return all((lo <= v <= hi) for v, (lo, hi) in ((x, box.get("x", (-1e9, 1e9))), (y, box.get("y", (-1e9, 1e9))),
                                                  (z, box.get("z", (-1e9, 1e9))), (abs(z), box.get("z_abs", (0.0, 1e9)))))


def _cut(sc, materials, box):
    """Remove the named materials' triangles that lie inside ``box`` from every static shape; returns the count."""
    cut = 0
    for s in sc.shapes:
        if struct.unpack_from("<I", s.record, 0x84)[0] != 0x32:
            continue
        P = None
        subs = []
        for sub in s.submeshes:
            if sc.materials[sub.material].name not in materials:
                subs.append(sub)
                continue
            if P is None:
                P = np.array(sb.shape_positions(s)) / 100.0
            tris = _triangles(sub.words)
            keep = [tr for tr in tris if not all(_in_box(P[i], box) for i in tr)]
            cut += len(tris) - len(keep)
            if len(keep) == len(tris):
                subs.append(sub)
            elif keep:
                words = sb.encode_words(sb.TRIANGLE_STRIP, sb.strips_to_indices([list(tr) for tr in keep]))
                rec = bytearray(sub.record)
                struct.pack_into("<2H", rec, 0x7C, len(words) // 4, 0)
                subs.append(sb.Submesh(rec, words))
        if len(subs) != len(s.submeshes) or any(a is not b for a, b in zip(subs, s.submeshes)):
            s.submeshes = subs
            struct.pack_into("<H", s.record, 0x54, len(subs))
    return cut


def _onto(sc, shape, materials, board, dy=0.0, toward_centre=0.0, min_abs_z=0.0, side=None):
    """Move the named materials' vertices of one shape onto a straight board's face (0.15 m in front of it), up by
    ``dy`` and ``toward_centre`` metres toward x = 0; only those on the board's side of the field (the sign of z)."""
    P0, N, _face = _ordered(board["path"])
    n = N[0]
    base = P0[0] + n * (float(board.get("inset", 0.3)) + 0.15)
    s = sc.shape(shape)
    ids = sorted({i for sub in s.submeshes if sc.materials[sub.material].name in materials
                  for _mode, ix in sb.decode_words(sub.words) for i in ix})
    P = [list(p) for p in sb.shape_positions(s)]
    sign = math.copysign(1.0, float(P0.mean(axis=0)[1]))
    moved = 0
    for i in ids:
        x, y, z = (v / 100.0 for v in P[i])
        if abs(z) < min_abs_z or math.copysign(1.0, z) != sign:
            continue
        q = np.array([x - math.copysign(min(abs(x), toward_centre), x), z])
        q = q - n * float(math.np_dot(q - base, n))                   # onto the face's plane (plan)
        P[i] = [float(q[0]) * 100.0, (y + dy) * 100.0, float(q[1]) * 100.0]
        moved += 1
    sb.set_positions(s, [tuple(p) for p in P])
    return moved


def _move(sc, shape, materials, toward_field, dy=0.0, min_abs_z=0.0, axis="radial"):
    """Move the named materials' vertices of one shape ``toward_field`` metres toward the field (``axis`` "radial": toward
    the field centre in plan; "z": along z, toward the halfway line) and up by ``dy``, those with |z| of at least
    ``min_abs_z``."""
    s = sc.shape(shape)
    ids = sorted({i for sub in s.submeshes if sc.materials[sub.material].name in materials
                  for _mode, ix in sb.decode_words(sub.words) for i in ix})
    P = [list(p) for p in sb.shape_positions(s)]
    moved = 0
    for i in ids:
        x, y, z = (v / 100.0 for v in P[i])
        if abs(z) < min_abs_z:
            continue
        if axis == "z":
            P[i] = [x * 100.0, (y + dy) * 100.0, (z - math.copysign(toward_field, z)) * 100.0]
        else:
            r = math.hypot(x, z)
            k = max(0.0, r - toward_field) / max(1e-9, r)
            P[i] = [x * k * 100.0, (y + dy) * 100.0, z * k * 100.0]
        moved += 1
    sb.set_positions(s, [tuple(p) for p in P])
    return moved


ART_DIR = DATA_DIR / "art"
#: an LED ribbon's height (2.5 ft, the Daktronics figure for the 2014 Cleveland ribbons and the usual NFL fascia board)
RIBBON_HEIGHT = 0.762


def _venue_art_materials(venue):
    """The materials whose textures the 2026 venue art paints at a venue (its table's targets)."""
    try:
        row = _mv().venues()[venue]
    except (KeyError, OSError, ValueError):
        return set()
    return {n for t in row.get("targets", ()) for n in t.get("names", ())}


def _drawn_materials(sc):
    """The names of the materials some static shape still draws."""
    return {sc.materials[sub.material].name for s in sc.shapes for sub in s.submeshes}


def _art(name):
    """An authored RGBA image from the kit's art folder (reviewed PNGs; plain type, no marks)."""
    from PIL import Image
    p = ART_DIR / name
    sb.require(p.is_file(), f"board kit art {name} is missing from this build")
    with Image.open(p) as im:
        return np.asarray(im.convert("RGBA"))


def _paint(sc, entry):
    """Repaint a freed retail texture: the texture of ``material``, which no drawn material may use any more (the kit
    cut or dropped everything that drew it), takes the art at the slot's own size and mip chain, so the decoded budget
    stays where it was. Returns the texture index."""
    from PIL import Image
    mi = sc.material_index(entry["material"])
    k = sc.materials[mi].texture
    sb.require(k is not None, f"{entry['material']}: no texture to repaint")
    drawn = _drawn_materials(sc)
    users = sorted(m.name for m in sc.materials if m.texture == k)
    sb.require(not (set(users) & drawn), f"{entry['material']}: its texture is still drawn by {sorted(set(users) & drawn)}")
    old = sc.textures[k]
    rgba = _art(entry["art"])
    if rgba.shape[:2] != (old.height, old.width):
        rgba = np.asarray(Image.fromarray(rgba).resize((old.width, old.height), Image.LANCZOS))
    new = sb.p8_texture(old, rgba)
    sb.require(len(new.pixels) <= len(old.pixels), f"{entry['material']}: the repainted texture grew")
    sc.textures[k] = new
    return k


def _ribbon_mesh(m, rib, colour, backing_colour):
    """An LED ribbon into mesh ``m``: a strip ``y`` high along its whole plan path, ``inset`` metres toward the field, u
    along the arc length (``tile_m`` metres a repeat) and v across one row of the repainted atlas (``row``), on a dark
    backing a ``border`` wider, set back ``depth``. Every ribbon of a venue shares one shape (a shape's records cost
    more than a ribbon's vertices)."""
    P, N, _face = _ordered(rib["path"])
    Q = P + N * float(rib.get("inset", 0.05))
    s = np.concatenate([[0.0], np.cumsum(math.np_norm(np.diff(Q, axis=0), axis=1))])
    y0, y1 = (float(v) for v in rib["y"])
    v0, v1 = (float(v) for v in rib["row"])
    tile = float(rib.get("tile_m", 8.0))
    face = lambda p_, n=N: np.array([n.mean(axis=0)[0], 0.0, n.mean(axis=0)[1]])  # noqa: E731
    top = [(float(p[0]), y1, float(p[1])) for p in Q]
    bot = [(float(p[0]), y0, float(p[1])) for p in Q]
    m.grid(rib["material"], [top, bot], [[(t / tile, v0) for t in s], [(t / tile, v1) for t in s]], facing=face)
    colours = {rib["material"]: colour}
    bk_ = rib.get("backing")
    if bk_:
        b, d = float(bk_.get("border", 0.12)), float(bk_.get("depth", 0.03))
        ends = [Q[0] - (Q[1] - Q[0]) / max(1e-9, float(math.np_norm(Q[1] - Q[0]))) * b]
        tail = [Q[-1] + (Q[-1] - Q[-2]) / max(1e-9, float(math.np_norm(Q[-1] - Q[-2]))) * b]
        F = np.array(ends + list(Q) + tail) - np.array([N[0]] + list(N) + [N[-1]]) * d
        L = np.concatenate([[0.0], np.cumsum(math.np_norm(np.diff(F, axis=0), axis=1))])
        m.grid(bk_["material"], [[(float(p[0]), y1 + b, float(p[1])) for p in F],
                                 [(float(p[0]), y0 - b, float(p[1])) for p in F]],
               [[(t / 4.0, 0.0) for t in L], [(t / 4.0, 1.0) for t in L]], facing=face)
        colours[bk_["material"]] = backing_colour
    return colours


def _panel_mesh(panel, colours_of):
    """Flat parts in retail materials (a deck, a glass front, a roof, a steel frame): each part a quad (four points in
    metres, in order round its edge) facing the point ``toward``, u and v in metres over ``uv_m`` a repeat; ``two_sided``
    parts are drawn from both sides."""
    m = mm.Mesh(panel["name"])
    colours = {}
    for part in panel["parts"]:
        a, b, c, d = (np.array(p, float) for p in part["quad"])
        w, h = float(math.np_norm(b - a)), float(math.np_norm(d - a))
        k = float(part.get("uv_m", 4.0))
        uv = [(0.0, h / k), (w / k, h / k), (w / k, 0.0), (0.0, 0.0)]
        toward = np.array(part["toward"], float)
        m.quad(part["material"], a, b, c, d, *uv, facing=lambda p_, t=toward: t - p_)
        if part.get("two_sided"):
            m.quad(part["material"], a, b, c, d, *uv, facing=lambda p_, t=toward: p_ - t)
        colours[part["material"]] = colours_of(part)
    return m, colours


def renovate(sc, venue):
    """Apply a venue's renovation to a parsed stadium scene in place; returns what changed."""
    s = spec(venue)
    tmpl_shape, tmpl_node = sm._template_shape(sc)
    info = dict(replaced=[], dropped=[], boards=[])
    frame_colours = {}
    for board in s.get("boards", ()):
        for part in (board.get("frame"), board.get("structure")):
            if part and part["material"] not in frame_colours:
                frame_colours[part["material"]] = (tuple(part["colour"]) + (255,))[:4] if "colour" in part else (
                    _material_colour(sc, part["material"]) or (40, 40, 40, 255))
    # the retail colours the ribbons and panels borrow, read before anything is cut
    retail_colours = {}
    for item in list(s.get("ribbons", ())) + [p for pn in s.get("panels", ()) for p in pn["parts"]]:
        for key in ("colour_from",):
            if key in item and item[key] not in retail_colours:
                retail_colours[item[key]] = _material_colour(sc, item[key]) or (128, 128, 128, 255)
        bk_ = item.get("backing")
        if bk_ and bk_["material"] not in frame_colours:
            frame_colours[bk_["material"]] = _material_colour(sc, bk_["material"]) or (40, 40, 40, 255)

    def colour_of(item):
        if "colour" in item:
            return (tuple(item["colour"]) + (255,))[:4]
        return retail_colours[item["colour_from"]]
    # replace: rebuild a shape from the submeshes it keeps
    for rep in s.get("replace", ()):
        old = sc.shape(rep["shape"])
        keep = set(rep["keep"])
        new = sm.extract(sc, [old], lambda name, keep=keep: name in keep, f"bk_{rep['shape']}", tmpl_shape)
        sc.remove_shape(rep["shape"])
        if new is not None:
            sc.shapes.append(new)
            sc.nodes.append(sb.node_for(tmpl_node, new.name, new.name))
        info["replaced"].append(rep["shape"])
    # drop: submeshes out of a shape in place
    for dr in s.get("drop", ()):
        shp = sc.shape(dr["shape"])
        names = set(dr["materials"])
        before = len(shp.submeshes)
        shp.submeshes = [x for x in shp.submeshes if sc.materials[x.material].name not in names]
        sb.require(len(shp.submeshes) < before, f"{dr['shape']}: none of {sorted(names)} to drop")
        struct.pack_into("<H", shp.record, 0x54, len(shp.submeshes))
        info["dropped"].append(dr["shape"])
    # cut: the old boards' panels by region
    info["cut"] = [_cut(sc, set(c_["materials"]), c_["box"]) for c_ in s.get("cut", ())]
    # move: the clock digits onto the new boards' faces
    boards = {b["name"]: b for b in s.get("boards", ())}
    info["moved"] = [
        _onto(sc, mv_["shape"], set(mv_["materials"]), boards[mv_["onto"]], float(mv_.get("dy", 0.0)),
              float(mv_.get("toward_centre", 0.0)), float(mv_.get("min_abs_z", 0.0))) if "onto" in mv_ else
        _move(sc, mv_["shape"], set(mv_["materials"]), float(mv_.get("toward_field", 0.0)), float(mv_.get("dy", 0.0)),
              float(mv_.get("min_abs_z", 0.0)), mv_.get("axis", "radial"))
        for mv_ in s.get("move", ())]
    # boards
    feed = (FEED_VERTEX, FEED_VERTEX, FEED_VERTEX, 255)
    centres = {}
    for board in s.get("boards", ()):
        fr = board.get("frame")
        mesh, colours = _board_mesh(board, feed, frame_colours.get(fr["material"]) if fr else None)
        if board.get("structure"):
            colours[board["structure"]["material"]] = frame_colours[board["structure"]["material"]]
        shape = _shape_from_mesh(sc, mesh, colours, tmpl_shape)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, shape.name, shape.name))
        Pm = np.array(mesh.P)
        feed_ids = sorted({i for st in mesh.groups["jumbo_tron"] for i in st})
        cen = Pm[feed_ids].mean(axis=0)
        centres[board["name"]] = tuple(float(v) for v in cen)
        Q = Pm[feed_ids]
        width = float(math.np_hypot(*np.ptp(Q[:, [0, 2]], axis=0))) if "outline" in board else float(board["width"])
        height = float(np.ptp(Q[:, 1])) if "outline" in board else board_height(board)
        info["boards"].append(dict(name=board["name"], width=round(width, 2), height=round(height, 2),
                                   crop=[round(v, 4) for v in feed_crop(width / height)]))
    # paint: freed retail textures take the ribbons' art (checked free before any ribbon draws them, and never a
    # texture the 2026 venue art paints)
    painted = {e["material"] for e in s.get("paint", ())}
    art_owned = _venue_art_materials(venue)
    sb.require(not (painted & art_owned), f"{venue}: the 2026 venue art paints {sorted(painted & art_owned)}")
    info["painted"] = [_paint(sc, e) for e in s.get("paint", ())]
    # ribbons: the LED fascia boards, on a repainted slot only (never a retail texture with its old marks)
    info["ribbons"] = []
    if s.get("ribbons"):
        mesh, colours = mm.Mesh("bk_ribbons"), {}
        for rib in s["ribbons"]:
            sb.require(rib["material"] in painted, f"{rib['name']}: a ribbon draws a repainted slot only")
            bk_ = rib.get("backing")
            got = _ribbon_mesh(mesh, rib, colour_of(rib), frame_colours.get(bk_["material"]) if bk_ else None)
            for mat, col in got.items():
                sb.require(colours.setdefault(mat, col) == col, f"{rib['name']}: the ribbons of a venue share one colour "
                           f"per material ({mat})")
            info["ribbons"].append(rib["name"])
        shape = _shape_from_mesh(sc, mesh, colours, tmpl_shape)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, shape.name, shape.name))
    # panels: flat parts in retail materials (the structures that replace cut seating)
    info["panels"] = []
    for panel in s.get("panels", ()):
        mesh, colours = _panel_mesh(panel, colour_of)
        shape = _shape_from_mesh(sc, mesh, colours, tmpl_shape)
        sc.shapes.append(shape)
        sc.nodes.append(sb.node_for(tmpl_node, shape.name, shape.name))
        info["panels"].append(panel["name"])
    for marker, board in s.get("markers", {}).items():
        mk = sc.marker(marker)
        struct.pack_into("<3f", mk.record, 0x10, *(v * 100.0 for v in centres[board]))
    return info


# ------------------------------------------------------------------------------------------------ the venue-art rule

def made_shapes(venue):
    """The names of the shapes the kit makes at a venue (its boards, ribbons and panels)."""
    doc = spec(venue)
    out = {b["name"] for b in doc.get("boards", ())} | {p["name"] for p in doc.get("panels", ())}
    return out | ({"bk_ribbons"} if doc.get("ribbons") else set())


def _static_triangles(sc, keep):
    """[(shape name, material name, 3 x 3 metres)] of the static shapes' triangles that ``keep(shape, material)``."""
    out = []
    for s in sc.shapes:
        if struct.unpack_from("<I", s.record, 0x84)[0] != 0x32:
            continue
        P = None
        for sub in s.submeshes:
            name = sc.materials[sub.material].name
            if not keep(s.name, name):
                continue
            if P is None:
                P = np.array(sb.shape_positions(s)) / 100.0
            out += [(s.name, name, P[list(tr)]) for tr in _triangles(sub.words)]
    return out


def _covered(points, dirs, tris, reach):
    """For each point, True when the ray from it along its direction (the art's face, turned toward the field) meets
    one of the triangles within ``reach`` metres: something stands in front of the art, between it and the field."""
    points, dirs = np.asarray(points, float), np.asarray(dirs, float)
    hit = np.zeros(len(points), bool)
    if not len(tris) or not len(points):
        return hit
    T = np.asarray(tris, float)
    A, B, C = T[:, 0], T[:, 1], T[:, 2]
    lo, hi = np.minimum(np.minimum(A, B), C), np.maximum(np.maximum(A, B), C)
    E1, E2 = B - A, C - A
    for i0 in range(0, len(points), 256):
        X, D = points[i0:i0 + 256], dirs[i0:i0 + 256]
        Y = X + D * reach
        slo, shi = np.minimum(X, Y), np.maximum(X, Y)
        inbox = np.all((shi[:, None, :] >= lo[None] - 1e-6) & (slo[:, None, :] <= hi[None] + 1e-6), axis=2)
        pi, ti = np.nonzero(inbox)
        if not len(pi):
            continue
        d = D[pi]
        pv = np.cross(d, E2[ti])
        det = np.einsum("ij,ij->i", E1[ti], pv)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = X[pi] - A[ti]
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, E1[ti])
        v = np.einsum("ij,ij->i", d, qv) * inv
        t = np.einsum("ij,ij->i", E2[ti], qv) * inv
        good = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 0.02) & (t <= reach)
        hit[i0 + pi[good]] = True
    return hit


def covered_venue_art(retail_sc, kit_sc, venue, *, reach=1.5, least=3):
    """The rule on the 2026 venue art: the kit never covers venue art on a structure that still stands in 2026; it may
    remove a venue-art panel that belongs to a board housing the renovation replaced. Returns [(shape, material,
    samples, centroid)]: the venue-art triangles that survive in the kit's scene with at least ``least`` of their five
    sample points (the centroid and three inner points) behind a surface the kit made, standing in front of them toward
    the field within ``reach`` metres where nothing stood in the retail scene. A triangle the kit hides like that must be
    cut instead (it belongs to a housing the renovation replaced) or the kit's surface moved. Empty when the rule
    holds; a big retail triangle a board's edge overlaps (one or two samples) is not a cover."""
    art = _venue_art_materials(venue)
    made = made_shapes(venue)
    kit_tris = [t for _s, _m, t in _static_triangles(kit_sc, lambda s, m: s in made)]
    out = []
    art_tris = _static_triangles(kit_sc, lambda s, m: m in art and s not in made)
    if not art_tris or not kit_tris:
        return out
    samples, dirs, owner = [], [], []
    eye = np.array([0.0, 15.0, 0.0])
    for k, (_s, _m, t) in enumerate(art_tris):
        c = t.mean(axis=0)
        n = np.cross(t[1] - t[0], t[2] - t[0])
        ln = float(math.np_norm(n))
        if ln < 1e-9:
            continue
        n = n / ln
        if float(math.np_dot(eye - c, n)) < 0:                   # the art's face, turned toward the field
            n = -n
        for q in [c] + [c + (v - c) * 0.6 for v in t]:
            samples.append(q)
            dirs.append(n)
            owner.append(k)
    samples, dirs = np.array(samples), np.array(dirs)
    by_kit = _covered(samples, dirs, kit_tris, reach)
    if not by_kit.any():
        return out
    idx = np.nonzero(by_kit)[0]
    retail = _static_triangles(retail_sc, lambda s, m: m not in art)
    was = _covered(samples[idx], dirs[idx], [t for _s, _m, t in retail], reach)
    count = {}
    for j, i in enumerate(idx):
        if not was[j]:
            count[owner[i]] = count.get(owner[i], 0) + 1
    for k, n in sorted(count.items()):
        if n >= least:
            s_, m_, t = art_tris[k]
            out.append((s_, m_, n, tuple(round(float(v), 2) for v in t.mean(axis=0))))
    return out


# ------------------------------------------------------------------------------------------------ bundles

def _ml():
    from . import nfl2k5_modern_metlife as ml
    return ml


def variants(venue):
    return tuple(f"{venue}{t}{w}.iff" for t in "dan" for w in "drs")


def build_scene(bundle, filename):
    """(scene, info): the stadium scene of one bundle, renovated."""
    ml = _ml()
    c = ml.bundle_scenes(bundle)["stadium"]
    _rec, dec = ml._scene(bundle, c)
    sc = sb.parse(dec, c.system_bytes)
    info = renovate(sc, filename[:3])
    return sc, info


def model_bundle(bundle, filename):
    """(bundle bytes, info): the bundle with its stadium scene renovated inside the stadium chunk's own stored span
    (the bundle and the archive entry keep their sizes; nothing else moves)."""
    ml = _ml()
    tx = ml._tools()[0]
    sc, info = build_scene(bundle, filename)
    decoded, system_bytes, video_bytes = sb.serialize(sc)
    st = ml.bundle_scenes(bundle)["stadium"]
    span = bytes(bundle[st.offset:st.offset + 32 + st.stored_size])
    chunk, cinfo = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, span)
    head, new_head = tx.HEADER.unpack_from(span, 0), tx.HEADER.unpack_from(chunk, 0)
    if new_head[5] > head[5]:
        # the refit asked for more in-place scratch than the chunk it replaces: refit keeping the wrapper's word
        from . import nfl2k5_usbank_model as um
        chunk, cinfo = um.fit_keep_scratch(decoded, system_bytes, video_bytes, span)
    sb.require(tx.HEADER.unpack_from(chunk, 0)[5] <= head[5], f"{filename}: the stadium chunk's scratch word rose")
    sb.require(len(chunk) == len(span), f"{filename}: the stadium chunk changed length")
    out = bytes(bundle[:st.offset]) + chunk + bytes(bundle[st.offset + len(span):])
    sb.require(len(out) == len(bundle), f"{filename}: the bundle changed size")
    chunks = tx.parse_chunks(out, allow_trailing=True)
    back, _ = tx.decode_chunk(out, chunks[st.index])
    sb.require(back == decoded, f"{filename}: stadium chunk read-back differs")
    return out, dict({k: v for k, v in cinfo.items() if k not in ('system', 'video')}, **info, system=system_bytes, video=video_bytes, retail_system=st.system_bytes,
                     retail_video=st.video_bytes, stretch=[st.offset, st.offset + len(span)],
                     vertices=sum(x.vertex_count for x in sc.shapes), shapes=len(sc.shapes))


# ------------------------------------------------------------------------------------------------ the Build option

PINS_DIR = DATA_DIR / "pins"
RECEIPT_SCHEMA = "nfl2k5_board_kit_receipt/v1"
BUILD_CAPTION = "Modern stadium boards (experimental)"
HELP_TEXT = _help_text()
#: how Modern Arrowhead is named in the boards' own sentences; Kansas City (s13) is the one kit stadium it also writes
ARROWHEAD = "Modern Arrowhead"
#: the bundle states the boards can be built on (``applied`` already carries them)
BUILDABLE = ("retail", "venues")


def _mv():
    from . import nfl2k5_modern_venues_2026 as mv
    return mv


def _venue_pins(venue):
    """{bundle name: the 2026 venue table's archive pin} of one venue (outer index, name id, size)."""
    return {pin["name"]: pin for pin in _mv().venues()[venue]["bundles"]}


def _entry(archive, pin):
    entry = _mv()._entry(archive, pin)
    sb.require(entry is not None, f"{pin['name']}: the archive entry differs from the venue table")
    return entry


@lru_cache(maxsize=None)
def model_pins(venue):
    p = PINS_DIR / f"{venue}.json"
    sb.require(p.is_file(), f"board kit pins for {venue} are missing from this build")
    doc = json.loads(p.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == PINS_SCHEMA and doc.get("venue") == venue, f"{p}: unsupported board kit pins")
    return doc


def pinned_venues():
    """The venues with both a data file and pins (the Build option writes exactly these)."""
    return tuple(v for v in venues() if (PINS_DIR / f"{v}.json").is_file())


def _pin(name):
    return next(p for p in model_pins(name[:3])["bundles"] if p["name"] == name)


def read_retail(source, venue):
    """{bundle name: retail bytes} of a venue's nine bundles, each checked against the 2026 venue table's retail pin."""
    ml = _ml()
    out = {}
    with ml._outer_image()(str(source)) as archive:
        for name, vp in _venue_pins(venue).items():
            e = _entry(archive, vp)
            data = archive.read(e.virtual_offset, e.size)
            sb.require(sha(data) == vp["retail_sha256"], f"{name}: the source bundle is not retail")
            out[name] = data
    return out


def record_pins(source, venues_=None, *, progress=None):
    """Author-time: renovate every bundle of each venue from a retail source and pin the stadium spans."""
    say = progress or (lambda message, done, total: None)
    PINS_DIR.mkdir(parents=True, exist_ok=True)
    docs = {}
    for venue in venues_ or venues():
        retail = read_retail(source, venue)
        bundles = []
        for k, name in enumerate(variants(venue)):
            out, info = model_bundle(retail[name], name)
            a, b = info["stretch"]
            bundles.append(dict(name=name, size=len(retail[name]), offset=a, length=b - a,
                                retail_sha256=sha(retail[name][a:b]), model_sha256=sha(out[a:b]), system=info["system"],
                                video=info["video"], retail_system=info["retail_system"], retail_video=info["retail_video"],
                                scratch=info.get("scratch"), vertices=info["vertices"]))
            say(f"board kit: {name}", k + 1, 9)
        doc = dict(schema=PINS_SCHEMA, label=LABEL, venue=venue, bundles=bundles,
                   source_note="renovated from the retail archive")
        (PINS_DIR / f"{venue}.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                                newline="\n")
        docs[venue] = doc
    model_pins.cache_clear()
    return docs


def _renovated(data, name):
    """True when a bundle's stadium scene carries every board of its venue (the kit composed on another option's
    stadium bytes: the 2026 venue art's repaint keeps the scene's structure)."""
    ml = _ml()
    try:
        tx, inventory, ResourceRecord, _header, _writer = ml._tools()
        pin = _pin(name)
        class MetadataTextures:
            def get(self, key):
                return {"conversion_status": "not_requested"}
        # Keep bundle_scenes' structural validation of every scene, including
        # field/cityscape chunks. Pixel conversion failures never affected
        # recognition; converting preview pixels here used to take minutes.
        found = {}
        for c in tx.parse_chunks(data, allow_trailing=True):
            if c.kind != "SCNE":
                continue
            dec, _ = tx.decode_chunk(data, c)
            record = ResourceRecord(outer_index=0, outer_id="", outer_size=len(data), chunk_index=c.index,
                                    chunk_offset=c.offset, kind=c.kind, stored_size=c.stored_size,
                                    word_08=c.system_bytes, word_0c=c.video_bytes, word_10=c.compression_magic,
                                    word_14=c.overlap_scratch_bytes)
            rec, *_ = inventory.parse_scene(c.index, record, dec, MetadataTextures())
            if rec.get("name") in ml.SCENES:
                # The original selector keeps the last chunk for each name.
                found[rec["name"]] = (c, dec if rec["name"] == "stadium" else None)
        sb.require({"field", "stadium"} <= set(found), "bundle lacks its field or stadium scene")
        c, dec = found["stadium"]
        sb.require(c.offset == pin["offset"] and tx.HEADER.size + c.stored_size == pin["length"],
                   "stadium span differs from its pin")
        sc = sb.parse(dec, c.system_bytes)
        sb.require(sc.name == "stadium", "pinned scene is not the stadium")
    except Exception:  # noqa: BLE001 - a scene the parser refuses is not the kit's
        return False
    names = {s.name for s in sc.shapes}
    return all(b["name"] in names for b in spec(name[:3]).get("boards", ()))


def _venues_receipt(source):
    """The 2026 venue art's receipt beside ``source`` (None without one, or when it does not read)."""
    try:
        return _mv().read_receipt(source)
    except (OSError, ValueError):
        return None


def published_spans(name):
    """{stadium span sha-256: [pack labels]} of the published SOFTDRINK 2K28 packs' scene for one kit bundle.

    Recorded by ``tools/b77/e4s_record_published.py`` from the published packs themselves; every hash in it was read
    as a stadium scene carrying the boards before it was kept."""
    return dict(_pin(name).get("published") or {})


def _arrowhead_owns(archive, name, colour_receipt=None):
    """True when Modern Arrowhead wrote this Kansas City bundle (alone, or combined with Modern colour)."""
    mv = _mv()
    if name[:3] != mv.ARROWHEAD_VENUE:
        return False
    try:
        return bool(mv._arrowhead_applied(archive, name, colour_receipt))
    except Exception:  # noqa: BLE001 - without Arrowhead's pins the bundle is not Arrowhead's
        return False


def bundle_state(archive, name, venues_receipt=None, colour_receipt=None):
    """retail / venues / applied / arrowhead / foreign for the stadium scene of one kit bundle.

    retail: the pinned retail stadium span. venues: the 2026 venue art's wall art on the retail scene, the bundle
    exactly as that option's receipt records it (the kit builds on it: it keeps every texture). applied: the pinned
    renovation of the retail scene, the kit's boards on a scene the 2026 venue art repainted, or the scene of a
    published SOFTDRINK 2K28 pack (pinned by hash). arrowhead: Kansas City as Modern Arrowhead wrote it (the boards
    are not built on it). foreign: anything else."""
    pin = _pin(name)
    e = _entry(archive, _venue_pins(name[:3])[name])
    if e.size != pin["size"]:
        return "foreign"
    data = archive.read(e.virtual_offset, e.size)
    have = sha(data[pin["offset"]:pin["offset"] + pin["length"]])
    if have == pin["model_sha256"]:
        return "applied"
    if have == pin["retail_sha256"]:
        return "retail"
    if have in (pin.get("published") or {}):
        return "applied"
    if _renovated(data, name):
        return "applied"
    row = ((venues_receipt or {}).get("bundles") or {}).get(name) or {}
    if row.get("applied_sha256") == sha(data):
        return "venues"
    if _arrowhead_owns(archive, name, colour_receipt):
        return "arrowhead"
    return "foreign"


def receipt_path(source):
    return Path(str(source) + ".board_kit.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    sb.require(doc.get("schema") == RECEIPT_SCHEMA, "unsupported board kit receipt")
    return doc


def bundle_states(source, *, stop_after_foreign=None, brief=False):
    """{bundle name: bundle_state} for every pinned venue's nine bundles.

    ``brief`` stops reading a stadium at its first bundle that is foreign or Modern Arrowhead's: the stadium is judged
    whole, so the other eight cannot change what the boards do with it, and an image that no stadium of can take the
    boards is refused in seconds, not after parsing every scene."""
    ml = _ml()
    receipt = _venues_receipt(source)
    colour_receipt = _mv()._colour_receipt(source)
    out = {}
    foreign = 0
    with ml._outer_image()(str(source)) as archive:
        for venue in pinned_venues():
            for name in variants(venue):
                try:
                    out[name] = bundle_state(archive, name, receipt, colour_receipt)
                except (sb.ScneBuildError, ValueError, StopIteration):
                    out[name] = "foreign"
                if out[name] == "foreign":
                    foreign += 1
                    if stop_after_foreign is not None and foreign >= stop_after_foreign:
                        return out
                if brief and out[name] in ("foreign", "arrowhead"):
                    break
    return out


def venue_label(venue):
    """The stadium as a person knows it: "Arrowhead Stadium (KC)"."""
    try:
        doc = spec(venue)
        return f"{doc['name']} ({doc['team']})"
    except (OSError, ValueError, KeyError):
        return venue


def plan_venues(states, owned=None):
    """What the boards do with each stadium, from {bundle name: bundle state}.

    {"write": [venues whose scenes the boards go on], "keep": [venues that already carry them],
    "skip": {venue: {"kind": "owned" | "foreign", "by": option or None, "bundles": [names]}}}. A stadium is judged
    whole: one changed bundle keeps all nine as they are, so the day, afternoon and night boards never disagree.
    ``owned`` names the stadiums another selected option writes in this very build ({"s13": "Modern Arrowhead"})."""
    owned = dict(owned or {})
    grouped = {}
    for name, state in states.items():
        grouped.setdefault(name[:3], {})[name] = state
    plan = dict(write=[], keep=[], skip={})
    for venue in pinned_venues():
        rows = grouped.get(venue)
        if not rows:
            continue
        by = owned.get(venue) or (ARROWHEAD if "arrowhead" in rows.values() else None)
        other = sorted(n for n, st in rows.items() if st not in BUILDABLE + ("applied", "arrowhead"))
        if by is not None:
            plan["skip"][venue] = dict(kind="owned", by=by, bundles=sorted(rows))
        elif other:
            plan["skip"][venue] = dict(kind="foreign", by=None, bundles=other)
        elif all(st == "applied" for st in rows.values()):
            plan["keep"].append(venue)
        else:
            plan["write"].append(venue)
    return plan


def _skipped(plan):
    return [dict(venue=venue, stadium=venue_label(venue), **info) for venue, info in sorted(plan["skip"].items())]


def _why(row):
    if row["kind"] == "owned":
        return (f"this stadium belongs to {row['by']} and the boards cannot be built on its scenes, so it stays "
                f"exactly as {row['by']} made it.")
    names = ", ".join(row["bundles"][:3]) + (f" and {len(row['bundles']) - 3} more" if len(row["bundles"]) > 3 else "")
    return (f"something other than the 2026 venue art or these boards changed its scenes ({names}), so the boards "
            "cannot be built on them and they stay exactly as they are.")


def skip_notes(plan):
    """The sentences for the finished-disc message: empty unless a stadium was left as it was."""
    if not plan["skip"]:
        return []
    total = len(plan["write"]) + len(plan["keep"]) + len(plan["skip"])
    have = len(plan["write"]) + len(plan["keep"])
    lines = [f"Modern stadium boards: {have} of {total} stadiums have them. These stayed as they were:"]
    lines += [f"{row['stadium']}: {_why(row)}" for row in _skipped(plan)]
    return lines


def _state_of(rows, plan):
    """retail (every stadium takes the boards) / partial (some do, some already have them or stay) / applied (nothing
    left to do, at least one stadium has them) / foreign (no stadium can take them)."""
    if not rows:
        return "retail"
    if plan["write"]:
        return "partial" if (plan["keep"] or plan["skip"]) else "retail"
    return "applied" if plan["keep"] else "foreign"


def _nothing_to_build_on(rows, plan):
    bad = sorted(name for name, state in rows.items() if state not in BUILDABLE + ("applied",))
    shown = ", ".join(bad[:6]) + (f" and {len(bad) - 6} more" if len(bad) > 6 else "")
    text = ("No stadium in this image has scenes the modern stadium boards can be built on (the retail scenes, or the "
            f"2026 venue art on them). Modified scenes: {shown}. "
            "Choose your unmodified USA retail image, or turn off Modern stadium boards "
            "to keep this project's stadium artwork. ")
    owners = sorted({row["by"] for row in plan["skip"].values() if row["kind"] == "owned"})
    if owners:
        text += f"{' and '.join(owners)} already writes some of these stadiums. "
    text += ("The 2026 venue art is recognized through the .venues-2026.json file kept beside the image it was built "
             "into (the image's name, then .venues-2026.json); a copy that was moved or renamed without it reads as "
             "modified.")
    return text


def image_report(source, *, owned=None, brief=False):
    """One reading of an image for the Build page: its state, what the boards would write or keep, what stays."""
    rows = bundle_states(source, brief=brief)
    plan = plan_venues(rows, owned)
    return dict(state=_state_of(rows, plan), write=list(plan["write"]), keep=list(plan["keep"]),
                skipped=_skipped(plan), notes=skip_notes(plan))


def image_status(source):
    """retail / partial / applied / foreign across every pinned venue's nine bundles (a stadium scene carrying the
    2026 venue art's wall art, as that option's receipt records it, counts as retail: the kit builds on it)."""
    return image_report(source)["state"]


status = image_status


def verify(source, *, enabled=True, states=None, owned=None):
    rows = bundle_states(source) if states is None else states
    plan = plan_venues(rows, owned)
    state = "applied" if (plan["keep"] and not plan["write"]) else _state_of(rows, plan)
    sb.require(state == ("applied" if enabled else "retail"), f"the stadium boards' state is {state}")
    covered = plan["keep"] if enabled else plan["write"]
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, venues=sorted(covered),
                skipped_venues=sorted(plan["skip"]))


def check_request(source, *, owned=None):
    """The build's quick check before any copy: some stadium's scenes are retail (the 2026 venue art may repaint them
    later in the build; the kit writes after it) or already carry the boards. A stadium that is neither stays as it is
    (the result's ``skipped`` names it); only an image with no usable stadium at all is refused."""
    rows = bundle_states(source, brief=True)
    plan = plan_venues(rows, owned)
    if rows:
        sb.require(plan["write"] or plan["keep"], _nothing_to_build_on(rows, plan))
    out = dict(state=_state_of(rows, plan))
    if plan["skip"]:
        out["skipped"] = _skipped(plan)
    return out


def _compose(job):
    name, current = job
    out, info = model_bundle(current, name)
    return name, out, info


def apply_to_image(target, *, progress=None, workers=None, owned=None):
    """Build step (after Modern colour and the 2026 venue art, which may have repainted these stadium scenes' textures;
    the kit keeps every texture and changes geometry only): each stadium whose scenes the boards can be built on has its
    nine bundles renovated in place. The 2026 venue art's and Modern colour's receipts take the new bundle hashes, so
    both still recognize their work.

    A stadium the boards cannot be built on (Kansas City after Modern Arrowhead, a stadium another tool changed) stays
    byte for byte as it is, is named in the result (``skipped``, ``user_notes``) and does not fail the build; one that
    already carries the boards is kept. Only a disc with no usable stadium at all is refused. The bytes are judged here,
    on the copy, because the earlier steps of the same build may have changed them since the early check."""
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    ml = _ml()
    mv = _mv()
    say = progress or (lambda message, done, total: None)
    sb.require(read_receipt(target) is None, "the output already carries the modern stadium boards")
    states = bundle_states(target)
    plan = plan_venues(states, owned)
    skipped = _skipped(plan)
    sb.require(plan["write"] or plan["keep"], _nothing_to_build_on(states, plan))
    if skipped:
        say("Modern stadium boards: leaving " + ", ".join(row["stadium"] for row in skipped) + " as it is", 0, 0)
    if not plan["write"]:
        return dict(verify(target, states=states, owned=owned), state="already_applied", skipped=skipped,
                    venues_written=[], venues_kept=list(plan["keep"]), user_notes=skip_notes(plan))
    try:
        colour_receipt = colour.read_image_receipt(target)
    except (OSError, ValueError):
        colour_receipt = None
    colour_before = sm._colour_states(target, colour_receipt) if colour_receipt else None
    venues_receipt = mv.read_receipt(target)
    jobs, pins, untouched = [], {}, {}
    with ml._outer_image()(str(target)) as archive:
        for venue in pinned_venues():
            for name, vp in _venue_pins(venue).items():
                e = _entry(archive, vp)
                data = archive.read(e.virtual_offset, e.size)
                if venue in plan["write"] and states.get(name) in BUILDABLE:
                    pins[name] = vp
                    jobs.append((name, data))
                else:
                    untouched[name] = (vp, sha(data))      # the scope receipt: what the boards must not change
    results = ml.run_jobs(_compose, jobs, workers=workers, progress=say, label="Modern stadium boards")
    current = dict(jobs)
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False,
                   venues=sorted(plan["write"] + plan["keep"]),
                   skipped={row["venue"]: {k: v for k, v in row.items() if k != "venue"} for row in skipped}, bundles={})
    new_colour = deepcopy(colour_receipt) if colour_receipt else None
    new_venues = deepcopy(venues_receipt) if venues_receipt else None
    with ml._outer_image()(str(target), writable=True) as archive:
        for name, after, info in results:
            e = _entry(archive, pins[name])
            before = archive.read(e.virtual_offset, e.size)
            sb.require(before == current[name], f"{name}: the bundle changed during the build")
            sb.require(len(after) == len(before), f"{name}: the renovated bundle changed size")
            archive.write(e.virtual_offset, after)
            sb.require(archive.read(e.virtual_offset, e.size) == after, f"{name}: write-back differs")
            receipt["bundles"][name] = dict(outer=pins[name]["outer"], before_sha256=sha(before), applied_sha256=sha(after),
                                            system=info["system"], video=info["video"])
            if new_colour is not None and name in new_colour.get("bundle_pins", {}):
                row = new_colour["bundle_pins"][name]
                new_colour["bundle_pins"][name] = dict(row, applied_sha256=sha(after), sites=[
                    dict(site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
            if new_venues is not None and name in (new_venues.get("bundles") or {}):
                new_venues["bundles"][name] = dict(new_venues["bundles"][name], applied_sha256=sha(after))
    if new_colour is not None:
        new_colour["board_kit"] = dict(bundles=sorted(receipt["bundles"]))
        colour_after = sm._colour_states(target, new_colour)
        mine = set(receipt["bundles"])
        wrong = sorted(n for n in mine if n in colour_after and colour_after[n] != colour_before[n])
        sb.require(not wrong, f"the colour read-back failed after the stadium boards: {', '.join(wrong)}")
        moved = sorted(n for n in colour_after if n not in mine and colour_after[n] != colour_before[n])
        sb.require(not moved, f"the stadium boards changed the colour state of other bundles: {', '.join(moved)}")
        colour._save_image_receipt(target, new_colour)
    if new_venues is not None:
        mv._save_receipt(target, new_venues)
    # read-back: the 2026 venue art still reads every bundle it wrote as its own, and the others as the kit's
    rows = (new_venues or {}).get("bundles") or {}
    with ml._outer_image()(str(target)) as archive:
        wrong = []
        for name in sorted(receipt["bundles"]):
            got = mv.bundle_state(archive, pins[name], new_venues, new_colour)
            if got != ("venues" if name in rows else "board_kit"):
                wrong.append(f"{name} {got}")
        # the scope receipt: every bundle the boards were to leave alone is byte for byte what it was
        changed = []
        for name, (vp, digest) in sorted(untouched.items()):
            e = _entry(archive, vp)
            if sha(archive.read(e.virtual_offset, e.size)) != digest:
                changed.append(name)
    sb.require(not wrong, f"the 2026 venue art's read-back failed after the stadium boards: {', '.join(wrong[:6])}")
    sb.require(not changed, f"the stadium boards changed stadiums they were to leave alone: {', '.join(changed[:6])}")
    receipt_path(target).write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    say("Modern stadium boards: done", 1, 1)
    return dict(verify(target, owned=owned), bundles_written=len(results), colour=new_colour is not None,
                venue_art=new_venues is not None, venues_written=list(plan["write"]), venues_kept=list(plan["keep"]),
                skipped=skipped, user_notes=skip_notes(plan))


def apply_lab_disc(disc, *, progress=None):
    """Lab only: the Build step on an already built disc."""
    return apply_to_image(disc, progress=progress)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_board_kit")
    sub = parser.add_subparsers(dest="command", required=True)
    st_ = sub.add_parser("status"); st_.add_argument("source")
    rp = sub.add_parser("record-pins"); rp.add_argument("source"); rp.add_argument("--venues", nargs="*")
    a = sub.add_parser("apply-lab"); a.add_argument("disc")
    args = parser.parse_args(argv)

    def say(message, done, total):
        print(f"{message} ({done}/{total})", flush=True)
    if args.command == "status":
        print(image_status(args.source))
    elif args.command == "record-pins":
        docs = record_pins(args.source, args.venues, progress=say)
        print(json.dumps({v: len(d["bundles"]) for v, d in docs.items()}))
    else:
        print(json.dumps(apply_lab_disc(args.disc, progress=say), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
