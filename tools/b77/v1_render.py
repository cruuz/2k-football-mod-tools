#!/usr/bin/env python3
"""b77 v1: offline renders of the shared goalpost, retail against modern, from the decoded scene data.

    v1_render.py --pack0 PACK0 --out DIR [--pack0-after PACK0_AFTER]

PACK0 is a vc_53450030/0 holding the retail goalpost scenes (the retail pack 0, or the SOFTDRINK v0.5 one: its two
goalpost spans are retail). The modern scenes are compiled from it with the Studio's own compiler
(mod_editor/core/nfl2k5_modern_goalposts.py), or read from PACK0_AFTER (a repaired pack 0) when given, so the
picture shows exactly the bytes a disc carries.

What is drawn is the game's data: the decoded NORMSHORT3 positions, the submesh triangle strips, the baked vertex
colours times the material colour (the pole's gold, the shadow's black). The pad carries the stadium's own pad art at
runtime (pad_north / pad_south), which is not part of this scene, so it is drawn in a flat stand-in blue. The figure
is a plain 6 ft (182.9 cm) silhouette for scale, not a game model. Software z-buffer, 3x supersampled; no game
lighting, fog or LOD. Offline inspection only: not a capture of the game.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from mod_editor.core import nfl2k5_modern_goalposts as g  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

FOOT = 30.48
PLAYER = 6 * FOOT
PAD_STANDIN = (40, 70, 140)
SS = 3
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ATTRIBUTES = {"goalpost": 3680, "goalpost_shadow": 2752}     # D3DCOLOR lane (stride 10) of each retail scene


def _font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()


def scene_spans(pack0: bytes) -> dict[str, bytes]:
    at, size = g.locate_outer(pack0)
    outer = pack0[at:at + size]
    where = g.locate_chunks(outer)
    return {scene: outer[off:off + n] for scene, (off, n) in where.items()}


def mesh(decoded: bytes, scene: str):
    """(positions Nx3 in cm, colours Nx3 0..1, [(material name, triangles Mx3)])."""
    spec = g.SCENES[scene]
    parsed = sb.parse(decoded, spec["size"])
    shape = parsed.shapes[0]
    P = np.array(g.positions(decoded, scene), dtype=float)
    base = ATTRIBUTES[scene]
    C = []
    for k in range(spec["vertices"]):
        b, gg, r, _a = struct.unpack_from("<4B", decoded, base + 10 * k)
        C.append((r / 255.0, gg / 255.0, b / 255.0))
    groups = []
    for sub in shape.submeshes:
        name = parsed.materials[sub.material].name
        tris = []
        for mode, idx in sb.decode_words(sub.words):
            if mode != sb.TRIANGLE_STRIP:
                continue
            for i in range(len(idx) - 2):
                a, b, c = idx[i], idx[i + 1], idx[i + 2]
                if len({a, b, c}) < 3:
                    continue
                tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
        groups.append((name, np.array(tris, dtype=int)))
    return P, np.array(C), groups


def material_colour(decoded: bytes, scene: str, name: str):
    parsed = sb.parse(decoded, g.SCENES[scene]["size"])
    for m in parsed.materials:
        if m.name == name:
            argb = struct.unpack_from("<I", m.record, 0x18)[0]
            return ((argb >> 16) & 255) / 255.0, ((argb >> 8) & 255) / 255.0, (argb & 255) / 255.0
    return 1.0, 1.0, 1.0


class Canvas:
    """A z-buffered RGB raster in supersampled pixels."""

    def __init__(self, w, h, background=(236, 240, 232)):
        self.w, self.h = w * SS, h * SS
        self.rgb = np.zeros((self.h, self.w, 3), dtype=float)
        self.rgb[:] = np.array(background) / 255.0
        self.z = np.full((self.h, self.w), np.inf)

    def triangle(self, pts, cols):
        """pts: 3x(x, y, depth) in supersampled pixels; cols: 3x rgb."""
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
        minx, maxx = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), self.w - 1)
        miny, maxy = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), self.h - 1)
        if minx > maxx or miny > maxy:
            return
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            return
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        c = 1 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        if not inside.any():
            return
        depth = a * z0 + b * z1 + c * z2
        zslice = self.z[miny:maxy + 1, minx:maxx + 1]
        win = inside & (depth < zslice)
        if not win.any():
            return
        zslice[win] = depth[win]
        col = (a[..., None] * np.array(cols[0]) + b[..., None] * np.array(cols[1]) + c[..., None] * np.array(cols[2]))
        self.rgb[miny:maxy + 1, minx:maxx + 1][win] = col[win]

    def image(self):
        img = Image.fromarray((np.clip(self.rgb, 0, 1) * 255).astype(np.uint8))
        return img.resize((self.w // SS, self.h // SS), Image.LANCZOS)


def draw_mesh(canvas, project, P, C, groups, colours):
    S = np.array([project(p) for p in P])
    for name, tris in groups:
        tint = np.array(colours.get(name, (1, 1, 1)))
        for t in tris:
            pts = [tuple(S[i]) for i in t]
            if any(not np.isfinite(v).all() for v in pts):
                continue
            cols = [tuple(C[i] * tint) for i in t]
            canvas.triangle(pts, cols)


def figure(canvas, project, base_x, base_z, colour=(0.12, 0.12, 0.12)):
    """A plain 6 ft silhouette standing at (base_x, 0, base_z), facing the viewer: head, torso, arms and legs."""
    h = PLAYER

    def box(x0, x1, y0, y1, z=0.0):
        a, b, c, d = [(base_x + x, y, base_z + z) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        pa, pb, pc, pd = project(a), project(b), project(c), project(d)
        canvas.triangle((pa, pb, pc), (colour,) * 3)
        canvas.triangle((pa, pc, pd), (colour,) * 3)
    box(-14, -3, 0, 0.47 * h)                 # legs
    box(3, 14, 0, 0.47 * h)
    box(-20, 20, 0.45 * h, 0.82 * h)          # torso
    box(-27, -20, 0.50 * h, 0.80 * h)         # arms
    box(20, 27, 0.50 * h, 0.80 * h)
    box(-5, 5, 0.80 * h, 0.86 * h)            # neck
    cx, cy, r = 0.0, 0.93 * h, 0.07 * h       # head
    ring = [(base_x + cx + r * math.cos(t), cy + r * math.sin(t), base_z) for t in np.linspace(0, 2 * math.pi, 24)]
    centre = project((base_x + cx, cy, base_z))
    for p, q in zip(ring, ring[1:]):
        canvas.triangle((centre, project(p), project(q)), (colour,) * 3)


def ortho(view, scale, ox, oy):
    """Orthographic projection to supersampled pixels: 'front' looks from the field (+z) at the goal, 'side' from +x."""
    def project(p):
        x, y, z = p
        u = x if view == "front" else -z
        depth = -z if view == "front" else -x
        return (ox + u * scale) * SS, (oy - y * scale) * SS, depth
    return project


def perspective(eye, target, fov_deg, w, h):
    eye, target = np.array(eye, float), np.array(target, float)
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, (0, 1, 0))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = (h / 2) / math.tan(math.radians(fov_deg) / 2)

    def project(p):
        d = np.array(p, float) - eye
        zc = d @ fwd
        if zc < 1.0:
            return (float("nan"),) * 3
        return ((w / 2 + (d @ right) * f / zc) * SS, (h / 2 - (d @ up) * f / zc) * SS, zc)
    return project


def elevation_panel(view, meshes, shadow_meshes, title, *, w=560, h=1060, top_label):
    scale = (h - 120) / (MAX_Y + 60)
    ox = w / 2 if view == "front" else w * 0.62
    oy = h - 60
    canvas = Canvas(w, h)
    project = ortho(view, scale, ox, oy)
    P, C, groups, colours = meshes
    draw_mesh(canvas, project, P, C, groups, colours)
    if view == "front":
        figure(canvas, project, -140.0, 60.0)
    else:
        figure(canvas, ortho("front", scale, ox - 170 * scale, oy), 0.0, 0.0)   # on the field side of the end line
    img = canvas.image()
    d = ImageDraw.Draw(img)
    f, fb = _font(15), _font(17, True)
    ground = oy
    d.line([(0, ground), (w, ground)], fill=(90, 120, 70), width=2)
    for feet, label, colour in ((10, "crossbar 10 ft", (60, 60, 60)), (40, "2004 top: 40 ft", (170, 40, 40)),
                                (45, "NFL 2014+: 45 ft", (30, 110, 40))):
        y = oy - feet * FOOT * scale
        for x0 in range(0, w, 14):
            d.line([(x0, y), (x0 + 7, y)], fill=colour, width=1)
        d.text((6, y - 18), label, fill=colour, font=f)
    d.text((10, 10), title, fill=(20, 20, 20), font=fb)
    d.text((10, 34), top_label, fill=(20, 20, 20), font=f)
    d.text((10, h - 40), "figure: 6 ft for scale", fill=(60, 60, 60), font=f)
    return img


MAX_Y = 1400.0


def build_meshes(decoded, scene):
    P, C, groups = mesh(decoded, scene)
    colours = {name: material_colour(decoded, scene, name) for name, _t in groups}
    if "pad" in colours:
        colours["pad"] = tuple(v / 255.0 for v in PAD_STANDIN)
    return P, C, groups, colours


def perspective_panel(meshes, title, *, w=900, h=640, eye, target, fov):
    canvas = Canvas(w, h, background=(150, 190, 230))
    project = perspective(eye, target, fov, w, h)
    # the field: a large green quad at y = 0 and the end line / goal line as thin white strips
    def quad(a, b, c, d, colour):
        pa, pb, pc, pd = project(a), project(b), project(c), project(d)
        if all(np.isfinite(v).all() for v in (pa, pb, pc, pd)):
            canvas.triangle((pa, pb, pc), (colour,) * 3)
            canvas.triangle((pa, pc, pd), (colour,) * 3)
    grass = (0.25, 0.48, 0.22)
    for z0 in range(-30000, 6000, 400):
        quad((-90000, -0.5, z0), (90000, -0.5, z0), (90000, -0.5, z0 + 400), (-90000, -0.5, z0 + 400), grass)
    for z in (0.0, 914.4):            # the end line under the crossbar, the goal line 10 yards in front
        quad((-2438, -0.2, z - 5), (2438, -0.2, z - 5), (2438, -0.2, z + 5), (-2438, -0.2, z + 5), (0.95, 0.95, 0.95))
    P, C, groups, colours = meshes
    draw_mesh(canvas, project, P, C, groups, colours)
    figure(canvas, project, -150.0, 90.0)
    img = canvas.image()
    d = ImageDraw.Draw(img)
    d.text((12, 10), title, fill=(10, 10, 10), font=_font(18, True))
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack0", type=Path, required=True)
    ap.add_argument("--pack0-after", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    before_spans = scene_spans(args.pack0.read_bytes())
    document = g.pins()
    rows = {r["scene"]: r for r in document["resources"]}
    for scene, span in before_spans.items():
        g.require(g.sha(span) == rows[scene]["retail_sha256"], f"{scene}: PACK0 does not hold the retail span")
    if args.pack0_after:
        after_spans = scene_spans(args.pack0_after.read_bytes())
    else:
        after_spans = {scene: g.compile_span(span, rows[scene])[0] for scene, span in before_spans.items()}
    for scene, span in after_spans.items():
        g.require(g.sha(span) == rows[scene]["applied_sha256"], f"{scene}: the modern span differs from its pin")
    dec = {(k, s): g.decode_span(span) for k, spans in (("before", before_spans), ("after", after_spans))
           for s, span in spans.items()}
    meshes = {k: build_meshes(dec[(k, "goalpost")], "goalpost") for k in ("before", "after")}
    shadows = {k: build_meshes(dec[(k, "goalpost_shadow")], "goalpost_shadow") for k in ("before", "after")}
    stats = {}
    for k in ("before", "after"):
        P = meshes[k][0]
        top = float(P[:, 1].max())
        stats[k] = dict(top_cm=round(top, 3), top_ft=round(top / FOOT, 3),
                        above_crossbar_ft=round((top - g.CROSSBAR_TOP) / FOOT, 3),
                        inside_width_cm=round(float(2 * min(abs(x) for x, y, _z in P if y > 400)), 3),
                        sphere=struct.unpack_from("<4f", dec[(k, "goalpost")], 704)[:3]
                        + struct.unpack_from("<f", dec[(k, "goalpost")], 704 + 0x48))
    labels = {k: f"uprights {stats[k]['above_crossbar_ft']:.1f} ft above the crossbar, top {stats[k]['top_ft']:.1f} ft"
              for k in stats}
    front = Image.new("RGB", (1120, 1060), "white")
    front.paste(elevation_panel("front", meshes["before"], shadows["before"], "RETAIL (2004)", top_label=labels["before"]),
                (0, 0))
    front.paste(elevation_panel("front", meshes["after"], shadows["after"], "MODERN (this option)",
                                top_label=labels["after"]), (560, 0))
    front.save(args.out / "goalpost_front_before_after.png")
    side = Image.new("RGB", (1120, 1060), "white")
    side.paste(elevation_panel("side", meshes["before"], shadows["before"], "RETAIL (2004), side",
                               top_label=labels["before"]), (0, 0))
    side.paste(elevation_panel("side", meshes["after"], shadows["after"], "MODERN, side", top_label=labels["after"]),
               (560, 0))
    side.save(args.out / "goalpost_side_before_after.png")
    # a PAT kicker's view: eye 1.8 m up, 33 yards in front of the end line (the 15-yard-line snap, 7 yards deep)
    eye, target = (0.0, 180.0, 33 * 91.44), (0.0, 650.0, 0.0)
    kick = Image.new("RGB", (900, 1280), "white")
    kick.paste(perspective_panel(meshes["before"], "RETAIL: a PAT from the kicker's eye (33 yd)", eye=eye,
                                 target=target, fov=34), (0, 0))
    kick.paste(perspective_panel(meshes["after"], "MODERN: same view", eye=eye, target=target, fov=34), (0, 640))
    kick.save(args.out / "goalpost_kicker_view_before_after.png")
    # shadows: the planar shadow mesh (drawn flattened by the game's projector), shown upright in side view
    shadow = Image.new("RGB", (1120, 1060), "white")
    shadow.paste(elevation_panel("front", shadows["before"], None, "RETAIL shadow mesh", top_label="goalpost_shadow"),
                 (0, 0))
    shadow.paste(elevation_panel("front", shadows["after"], None, "MODERN shadow mesh", top_label="goalpost_shadow"),
                 (560, 0))
    shadow.save(args.out / "goalpost_shadow_mesh_before_after.png")
    # close-ups of the right upright's top (caps closed, colours kept) and of the crossbar join (unchanged)
    close = Image.new("RGB", (1200, 600), "white")
    for column, (k, y0) in enumerate((("before", 1100.0), ("after", 1250.0), ("before", 230.0), ("after", 230.0))):
        canvas = Canvas(300, 560)
        scale = 560 / 160.0
        project = (lambda y_low: (lambda p: ((150 + (p[0] - 287.0) * scale) * SS,
                                              (560 - (p[1] - y_low) * scale) * SS, -p[2])))(y0)
        P, C, groups, colours = meshes[k]
        draw_mesh(canvas, project, P, C, groups, colours)
        img = canvas.image()
        d = ImageDraw.Draw(img)
        what = "top" if y0 > 1000 else "crossbar join"
        d.text((8, 8), f"{'RETAIL' if k == 'before' else 'MODERN'} {what}", fill=(10, 10, 10), font=_font(15, True))
        d.text((8, 28), f"y {y0:.0f}..{y0 + 160:.0f} cm", fill=(40, 40, 40), font=_font(13))
        close.paste(img, (300 * column, 20))
    close.save(args.out / "goalpost_closeups_before_after.png")
    (args.out / "render_stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
