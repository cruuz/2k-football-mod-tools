#!/usr/bin/env python3
"""pa1 (b773, N32): author ``data/nfl2k5_pants_hem_2026.json``, the above-the-knee pants hem for the 2026 kits.

  pa1_author.py contour --census DIR [--fraction 0.44] --out HEM.json
        the hem contours: the native hi_body (o3c114) and lo_body (o3c113) pants triangles, and the sideline
        player's five LODs (o346c116), cut by the bind-pose plane at hip-to-ankle fraction ``fraction``
        (pt0's ``tools/b77/pt0_pants_probe.py``, commit a194c818 on the b772 line, writes the censuses: positions,
        UVs and triangles per surface)
  pa1_author.py data --input DISC.iso --hem HEM.json [--out data/nfl2k5_pants_hem_2026.json] [--png DIR]
        measure every listed kit's upper-sock colour (clean and wet) on the pinned input disc, compile its pants,
        bump and sideline textures with the Studio module and record the pins; ``--png`` also writes level-0
        before/after PNGs for review (game-derived: keep them outside the repository)

The kits are the 2026 primaries (style 0, home and road) and the built 2026 alternates of
``data/nfl2k5_uniform_slots_2026.json``. Historic, Anniversary and throwback kits keep their era hem (EXCLUDED).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kit  # noqa: E402
from mod_editor.core import nfl2k5_pants_hem_2026 as hem  # noqa: E402
from mod_editor.core.nfl2k5_uniform_slots import FRANCHISES  # noqa: E402
from nfl_txtr import parse_chunks  # noqa: E402

HIP_Y, LEG = -5.6075158, 91.5936027          # native hip pivot height and hip-to-ankle height, both legs (pt0)
FRACTION = 0.44                              # the Falcons target (pt0: 0.426..0.443) inside pt0's 0.42..0.49 range
SLOTS = ROOT / "data/nfl2k5_uniform_slots_2026.json"
# Throwbacks and classic-era sets keep the hem of their era (2026 players wear them, but the look is the old one).
EXCLUDED = {
    ("ATL", 9): "1966 throwback", ("DAL", 9): "1960s Thanksgiving throwback", ("GB", 6): "1923 Classic throwback",
    ("LV", 4): "1970-style road throwback", ("NE", 4): "Pat Patriot red throwback", ("PHI", 4): "Kelly Green throwback",
    ("PIT", 5): "1933 gold throwback", ("TB", 2): "1976 creamsicle throwback", ("CLE", 4): "white throwback",
}
PANTS_SHADOW = [[0.0, 1.0, 84], [1.0, 2.0, 93]]      # (from, to texels under the hem, brightness %)
SPLAYER_SHADOW = [[0.0, 1.0, 88]]
SPLAYER_BOX = [0, 0, 128, 90]                       # the sideline atlas pants island (hands and helmet below)
SPLAYER_SOCK = (160, 100, 190, 128)                 # its upper-sock box
BUMP_FLAT_FROM, BUMP_FADE = 1.5, 50
CHUNKS = {2: ("pants00", "pants", [512, 256, 6]), 47: ("bump_pants", "bump", [512, 256, 6]),
          51: ("splayer", "splayer", [256, 128, 5])}


def kits():
    """(selector, team, style, set) of every current-season kit, and the excluded built kits with the reason."""
    plan = json.loads(SLOTS.read_text(encoding="utf-8"))
    code = {v: k for k, v in FRANCHISES.items()}
    rows, skipped = [], []
    for c in sorted(FRANCHISES):
        for side, name in (("H", "home"), ("A", "road")):
            rows.append(dict(selector=f"{c}{side}0", team=FRANCHISES[c], style=0, set="2026 primary " + name))
    for team, entry in plan["teams"].items():
        for a in entry["assignments"]:
            for side in "HA":
                row = dict(selector=f"{code[team]}{side}{a['style']}", team=team, style=a["style"], set=a["set"])
                if (team, a["style"]) in EXCLUDED:
                    skipped.append(dict(row, why=EXCLUDED[(team, a["style"])]))
                elif a["status"] not in ("built", "shipped"):
                    skipped.append(dict(row, why="not built: the slot still holds its retail era kit"))
                else:
                    rows.append(row)
    return rows, skipped


# -- contours --------------------------------------------------------------------------------------------------------

def surface_mesh(census, material):
    pos, uv, tris = {}, {}, []
    for shape in census["shapes"]:
        for su in shape["surfaces"]:
            if su["submesh"]["material_name"] != material:
                continue
            for v in su["vertices"]:
                pos[v["id"]], uv[v["id"]] = v["xyz"], v["uv"]
            tris += [tuple(t) for t in su["triangles"]]
    return pos, uv, tris


def cut(pos, uv, tris, y):
    """UV segments where the plane at height ``y`` crosses the triangles."""
    segs = []
    for tri in tris:
        pts = []
        for a, b in zip(tri, tri[1:] + tri[:1]):
            ya, yb = pos[a][1], pos[b][1]
            if (ya <= y < yb) or (yb <= y < ya):
                t = (y - ya) / (yb - ya)
                p = np.array(uv[a], float) + t * (np.array(uv[b], float) - np.array(uv[a], float))
                if not any(np.allclose(p, q, atol=1e-10) for q in pts):
                    pts.append(p)
        if len(pts) == 2 and abs(pts[1][0] - pts[0][0]) > 1e-10:
            segs.append(pts)
    require(segs, "the cut misses the surface")
    return np.asarray(segs)


def average(segsets, union=False):
    """One V per knot U: the mean over the curves that cover it (all of them on their common extent, or any of them
    when ``union``)."""
    lo = (min if union else max)(s[:, :, 0].min() for s in segsets)
    hi = (max if union else min)(s[:, :, 0].max() for s in segsets)
    knots = sorted({float(u) for s in segsets for u in s[:, :, 0].flat if lo <= u <= hi})
    out = []
    for u in knots:
        vals = []
        for segs in segsets:
            vs = [a[1] + (u - a[0]) / (b[0] - a[0]) * (b[1] - a[1]) for a, b in segs
                  if min(a[0], b[0]) - 1e-9 <= u <= max(a[0], b[0]) + 1e-9]
            if vs:
                vals.append(float(np.mean(vs)))
        require(vals or union, "gap in a contour")
        if vals:
            out.append([u, float(np.mean(vals))])
    return out


def texels(curve, width, height):
    """UV to texel coordinates on the module's fixed-point grid (1/200 texel), one point per distinct x."""
    out = []
    for u, v in curve:
        p = [round(u * width * 200) / 200, round(v * height * 200) / 200]
        if not out or p[0] > out[-1][0]:
            out.append(p)
    return out


def contour(args):
    census = Path(args.census)
    y = HIP_Y - args.fraction * LEG
    body = []
    for key in ("o3c114", "o3c113"):
        d = json.loads((census / f"{key}_census.json").read_text(encoding="utf-8"))
        body.append(cut(*surface_mesh(d, "UNIF_pants"), y))
    side = json.loads((census / "o346c116_census.json").read_text(encoding="utf-8"))
    lods = []
    for shape in side["shapes"]:
        pos, uv, tris = {}, {}, []
        for su in shape["surfaces"]:
            if su["submesh"]["material_name"] != "SIDELINE_player":
                continue
            for v in su["vertices"]:
                pos[v["id"]], uv[v["id"]] = v["xyz"], v["uv"]
            tris += [tuple(t) for t in su["triangles"]]
        segs = cut(pos, uv, tris, y)
        # the pants island only (the arms and torso cross the same height elsewhere in the atlas)
        segs = segs[(segs[:, :, 0].max(axis=1) <= SPLAYER_BOX[2] / 256) & (segs[:, :, 1].max(axis=1) <= SPLAYER_BOX[3] / 128)]
        lods.append((shape["lanes"]["name"], segs))
    # the two detailed LODs (LOD5, LOD4: the near sideline views) span the island; the coarse ones only part of it
    lods = [segs for name, segs in lods if name in ("LOD5", "LOD4")]
    require(len(lods) == 2, "sideline LOD5/LOD4 absent")
    document = dict(fraction=args.fraction, plane_y_cm=y,
                    pants=dict(points=texels(average(body), 512, 256), shadow=PANTS_SHADOW,
                               bump_flat_from=BUMP_FLAT_FROM, bump_fade=BUMP_FADE),
                    splayer=dict(points=texels(average(lods), 256, 128), shadow=SPLAYER_SHADOW,
                                 box=SPLAYER_BOX))
    for name in ("pants", "splayer"):
        ys = [p[1] for p in document[name]["points"]]
        print(name, "knots", len(ys), "rows %.2f..%.2f" % (min(ys), max(ys)))
    Path(args.out).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")


# -- data ------------------------------------------------------------------------------------------------------------

def require(ok, message):
    if not ok:
        raise SystemExit("pa1_author: " + message)


def hexc(rgb):
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def sock_colours(span):
    """The upper sock (rows 0-7 of level 0: the cuff end) mean colour, clean and wet; the two TSET textures may keep
    their own index planes (CHI, CLE)."""
    chunk = parse_chunks(span)[0]
    decoded, _ = kit.decode_chunk(span, chunk)
    textures = kit._tset_textures(decoded)
    out = []
    for t in textures[:2]:
        plane = kit.read_planes(decoded, chunk, t)[0]
        rgb = kit.read_palette(decoded, chunk, t)[plane][:8, :, :3].reshape(-1, 3)
        out.append(tuple(int((c + len(rgb) // 2) // len(rgb)) for c in rgb.sum(axis=0)))
    return out


def splayer_sock(span):
    rgba = kit.texture_rgba(span).astype(np.int64)
    x0, y0, x1, y1 = SPLAYER_SOCK
    rgb = rgba[y0:y1, x0:x1, :3].reshape(-1, 3)
    return tuple(int(np.median(rgb[:, i])) for i in range(3))


def data(args):
    shape = json.loads(Path(args.hem).read_text(encoding="utf-8"))
    current, skipped = kits()
    wanted = {k["selector"]: k for k in current}
    raws = {}
    with bump._Image.open(Path(args.input), writable=False) as image:
        index = bump._parsed_index(image)
        for entry in index.entries:
            name = bump.logical_name_for(entry.name_id)
            if name and name.endswith(".IFF") and name[:-4] in wanted:
                require(name[:-4] not in raws, name + " duplicated")
                raws[name[:-4]] = image.read_segments(index.sub_extents(entry, 0, entry.size))
    require(set(raws) == set(wanted), "kit packages absent: " + ", ".join(sorted(set(wanted) - set(raws))))
    textures, notes, cache = [], [], {}
    document = dict(schema=hem.SCHEMA, source="", method="", hem=dict(pants=shape["pants"], splayer=shape["splayer"]),
                    fraction=shape["fraction"], kits=[], excluded=skipped, sideline_kept=[],
                    textures=textures)
    png = Path(args.png) if args.png else None
    if png:
        png.mkdir(parents=True, exist_ok=True)
    for selector in sorted(wanted):
        raw = raws[selector]
        by_index = {c.index: c for c in parse_chunks(raw, allow_trailing=True)}
        sock = by_index[4]
        sock_span = raw[sock.offset:sock.end_offset]
        clean, wet = sock_colours(sock_span)
        side = splayer_sock(raw[by_index[51].offset:by_index[51].end_offset])
        info = dict(wanted[selector], legging=hexc(clean), legging_wet=hexc(wet), sideline_legging=hexc(side))
        document["kits"].append(info)
        for index_, (name, kind, size) in CHUNKS.items():
            c = by_index[index_]
            span = raw[c.offset:c.end_offset]
            row = dict(selector=selector, chunk=index_, texture=name, kind=kind, size=size, resource_size=len(raw),
                       offset=c.offset, length=len(span), before_sha256=hem.sha(span))
            if kind == "pants":
                row.update(legging=info["legging"], legging_wet=info["legging_wet"], socks_chunk=4,
                           socks_sha256=hem.sha(sock_span))
            elif kind == "splayer":
                row.update(legging=info["sideline_legging"])
            try:
                new, detail = hem.compile_row(span, row, document, raw, cache)
            except hem.ScratchError:
                require(kind == "splayer", selector + " " + kind + ": cannot keep the retail loader scratch allowance")
                need, allowed = retail_margin(span)
                document["sideline_kept"].append(dict(selector=selector, retail_need=need, retail_scratch=allowed, why=(
                    "the retail stream already needs %d of its %d bytes of in-place scratch: the hem edit outgrows "
                    "the retail loader's allowance, so this sideline atlas keeps its retail hem" % (need, allowed))))
                print(selector, "sideline atlas kept (no in-place margin)", flush=True)
                continue
            row["after_sha256"] = hem.sha(new)
            textures.append(row)
            notes.append(dict(selector=selector, chunk=index_, **{k: v for k, v in detail.items() if k != "fit"}))
            if png:
                for tag, blob in (("before", span), ("after", new)):
                    rgba = (kit.texture_rgba(blob) if kind != "bump" else _bump_rgba(blob))
                    from PIL import Image
                    Image.fromarray(rgba).save(png / f"{selector}_{kind}_{tag}.png")
            if kind == "pants":
                print(selector, info["team"], info["style"], "legging", info["legging"], "wet", info["legging_wet"],
                      "added", len(detail["palette_entries_added"]), "merged", detail["merged_twin_slots"],
                      "limit", detail["merge_limit"], flush=True)
    document["source"] = ("b773-pa1 (N32), the 2026 pants hem above the knee: pinned to the kit spans of the v0.6.1 "
                          "fixes disc (520429148f57...; the uf3 finish does not touch these chunks)")
    document["method"] = ("texture only (pt0 option a): hem contour at hip-to-ankle fraction %.2f on the native "
                          "bodies; legging = the kit's own upper-sock colour, clean and wet; overhang shadow; bump "
                          "relief faded under the hem; sideline atlas from its own contour" % shape["fraction"])
    out = Path(args.out)
    out.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    if args.notes:
        Path(args.notes).write_text(json.dumps(notes, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("rows", len(textures), "kits", len(document["kits"]), "excluded", len(skipped))


def retail_margin(span):
    """(exact in-place scratch the stored stream needs, the scratch word the retail wrapper allows)."""
    from nfl_txtr import HEADER, decode_chunk, minimum_vc_lz_overlap_scratch
    chunk = parse_chunks(span)[0]
    decoded, info = decode_chunk(span, chunk)
    stream = span[HEADER.size:HEADER.size + info.consumed_bytes]
    fields = HEADER.unpack_from(span)
    return minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded)), fields[5]


def _bump_rgba(span):
    chunk, decoded, texture = hem._argb(span)
    from nfl_txtr import texture_to_rgba
    return np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("contour")
    c.add_argument("--census", required=True)
    c.add_argument("--fraction", type=float, default=FRACTION)
    c.add_argument("--out", required=True)
    d = sub.add_parser("data")
    d.add_argument("--input", required=True)
    d.add_argument("--hem", required=True)
    d.add_argument("--out", default=str(hem.DATA))
    d.add_argument("--png")
    d.add_argument("--notes")
    d.add_argument("--only", nargs="*")
    args = p.parse_args(argv)
    if args.cmd == "contour":
        contour(args)
    else:
        if args.only:
            global kits
            full = kits
            kits = lambda: ([k for k in full()[0] if k["selector"] in args.only], full()[1])  # noqa: E731
        data(args)


if __name__ == "__main__":
    main()
