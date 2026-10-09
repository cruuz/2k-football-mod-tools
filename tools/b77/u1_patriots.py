#!/usr/bin/env python3
"""Beta 77 u1: the 2026 New England Patriots kits (16H0 home, 16A0 road), right this time.

Sources: the club's 2026 uniform shoot and its 2026 week 1-4 game galleries (recorded in
``data/nfl2k5_teams_2026/NE.json`` under ``sources_u1_b77``). The NFL2K27 PCSX2 textures Noah supplied are placement
references only; nothing of them is reused.

  update-spec  NE.json + the Studio's rest-pose hi_body export -> NE.json with the 2026 yoke stripes (3D bands
               along the armhole seam, as UV polygons), the chest wordmark with the Flying Elvis under it, the
               pants stripes, the road socks, the number trims and the navy helmet numbers
  author       the recipe applied to the shipped v0.5 kit art (a scope-limited edit: every texel outside the
               declared scope keeps its exact v0.5 RGBA; the jersey keeps its protected colours and coarse mips)
  compile      the art through the Studio's own importers -> exact native spans + manifest for tools/b77/u1_repair.py

Geometry is read only. No vertex, index or UV is written. Game-derived inputs and outputs stay in private scratch.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zlib

import numpy as np
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools")]
import nfl2k5_team_2026_art as art  # noqa: E402


def _b765():
    """The 76.5 Patriots helpers (the traced numerals), loaded by path: same module name."""
    import importlib.util
    if "b765_u1_patriots" not in sys.modules:
        spec = importlib.util.spec_from_file_location("b765_u1_patriots", ROOT / "tools/b765/u1_patriots.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["b765_u1_patriots"] = module
        spec.loader.exec_module(module)
    return sys.modules["b765_u1_patriots"]

MASTER = art.MASTER
SCHEMA_MANIFEST = "b77/u1/texture-repair/v1"
NE_OUTER = {"3741": "16H0.IFF", "4058": "16A0.IFF"}     # outer index of each shipped Patriots kit package

# --------------------------------------------------------------------------------------------- 2026 parameters
# The yoke insert of the 2020-2026 jersey: two red bands of constant width along its edges and a white (home) or
# navy (road) band between them, sewn along the armhole seam from the back yoke seam over the shoulder to the front
# yoke seam. On the front the panel narrows toward the yoke seam (the middle band tapers, as on the 2026 shoot's
# knit inserts). Widths are cm on the rest-pose hi_body, proportioned to the model's shoulder (the 2K5 pads are
# wider than a real player's, so a photo's inch figures are not copied): the panel covers about half of the
# shoulder from the armhole toward the collar, as on the club photos.
YOKE = {
    "red_cm": 2.8,            # each red band
    "panel_back_cm": 9.0,     # whole insert on the back and over the shoulder top
    "panel_front_end_cm": 7.0,  # whole insert where it meets the front yoke seam
    "front_taper_top_y": 66.5,  # the front taper starts at the shoulder top (rest-pose y, cm)
    "front_end_y": 56.7,      # the front yoke seam: level with the collar V tip (TORSO_V_TIP, y 56.73 cm)
    "back_end_y": 55.5,       # the back yoke seam: level with the bottom of the nameplate (PLAYERNAME y 55.4)
    "uv_bleed_px": 1.5,       # gutter padding across the UV islands' outlines only
    # the back: straight vertical bands (lateral distance from the back armhole line, |x| 26.4 cm on the model at
    # y 54-60 cm), blended into the seam distance across the shoulder top (full at z <= -8 cm, none at z >= -1 cm)
    "back_lateral": {"x_ref": 26.4, "z_full": -8.0, "z_zero": -1.0},
}
# The arched PATRIOTS wordmark with the Flying Elvis cradled under it, centred under the collar shield. Sizes are
# from the 2026 shoot measured against the 8 in (21.2 cm on the model) front numbers: wordmark 7.1 cm wide, its
# letters 1.4 cm below the shield, the logo 0.43 of the wordmark's width (retail px; torso texels are 0.275 cm
# across and 0.25 cm down at the chest, so heights are given to keep true proportions).
CHEST = {
    "wordmark": {"center": [161.0, 92.0], "width": 26.0, "height": 6.8},
    "logo": {"center": [161.5, 95.2], "width": 11.1, "height": 5.9},
    "erase": [148, 86, 174, 99],   # the v0.5 wordmark (rows 91-96, x 151-170) and its margin
}
PANTS_STRIPE_PX = 10             # three equal bands (2022+ silver/white pants and the road navy pants), 2.4 cm each
# The jersey numbers keep v0.5's trims (silver ring 1.4 %, red ring 2.4 % of the 60 px glyph). The 2026 shoot measures
# silver 2.1 % and red 1.9 %, but at 64 px a 1.1 px red ring blurs into the silver one through the importer's mips
# (tried in b77, the red outline faded), so the retail-size numbers keep the ring that reads at game distance.
HELMET_DIGITS = {"fill": "helmet_navy", "glyph_height": 29, "glyph_center": [15.0, 16.0]}


SOURCES_B77 = {
    "uniform_shoot_2026": "https://www.patriots.com/photos/photos-best-of-new-england-patriots-2026-full-uniform-shoot "
        "(club, primary): full-resolution frames static.clubs.nfl.com/image/upload/patriots/ynxg1hlzkpw2uiqqmc7t (#75 "
        "front: yoke stripes, shield, wordmark, numbers, red facemask), hz8slrsdl7sv59hshyw3 (#4 back: back stripes to "
        "the nameplate bottom, navy helmet number, flag on the left rear, no NFL shield on the back, pants stripes), "
        "m27lg4xmnrpdsc3mfedr (#16: yoke over the shoulder, swoosh above the sleeve logo), dgzs3whjdoassacz1rxx (#5 "
        "side: pants stripe bands about 2.4 cm each against the 21 cm front numbers), s4ydoptq86vm7vhmup0h (#35)",
    "week1_at_sea_2026": "https://www.patriots.com/photos/game-photos-from-the-patriots-vs-the-seahawks-regular-season-"
        "game-1-presented-by-sony (published 2026-09-10): white jersey, navy pants with red-white-red stripes, white "
        "socks (frames z5vikxrmiojge9j9jraj, idfj6rsqjnkwhizj16rl)",
    "week2_vs_pit_2026": "https://www.patriots.com/photos/game-photos-from-the-patriots-win-over-the-steelers-regular-"
        "season-game-2-presented-by-sony (2026-09-20): navy jersey, silver pants, navy socks",
    "week3_at_jax_2026": "https://www.patriots.com/photos/game-photos-from-week-3-game-against-the-jaguars-presented-"
        "by-sony (2026-09-27): white jersey, white pants, white socks",
    "week4_at_buf_2026": "https://www.patriots.com/photos/game-photos-from-the-patriots-win-over-the-bills-regular-"
        "season-game-4-presented-by-sony (2026-10-04): white jersey, silver pants, white socks",
    "design_2020": "https://www.patriots.com/news/patriots-unveil-new-uniforms-ahead-of-2020-season (2020-04-20): "
        "road numbers 'blue numbers outlined in silver and red'; 'strong red and blue stripes on the shoulders'",
    "history": "https://en.wikipedia.org/w/index.php?title=New_England_Patriots&action=raw (Logos and uniforms, with "
        "its citations): truncated shoulder striping (2020); silver pants since 2022 with red stripes as wide as the "
        "blue one; silver full time from 2024; white pants from 2025 (all-white in Super Bowl LX)",
    "placement_reference": "Noah's NFL2K27 PCSX2 textures (~/Downloads/patriots, read from the members of "
        "~/Downloads/NFL2K27-Windows.zip Team/Patriots/Uniform/Default): positions only; no file or pixel reused",
}
ALTERNATES_2026 = {
    "pat_patriot_throwback": "red jersey, white pants, white helmet with the Pat Patriot logo; scheduled 2026 week 5 "
        "(Oct 11 vs Las Vegas, Adam Vinatieri tribute) and week 14 (Dec 10 vs Minnesota). Return of the throwback: "
        "https://www.nfl.com/news/patriots-red-throwback-alternate-uniforms-2022-season; 2026 dates from secondary "
        "reports (NESN, Yahoo via fantasynerds 2026-09-04), to confirm against the club's schedule",
    "noreaster_rivalries": "Storm Blue jersey, white and navy shoulder stripes, italic white numbers with navy drop "
        "shadow, NE sleeve logo, six red stars at the neckline, white pants, matte white helmet with a silver-trimmed "
        "Flying Elvis: https://www.patriots.com/news/patriots-unveil-nor-easter-uniforms-for-week-11-rivalry-game-vs-"
        "jets (2025-08-28); 2026: week 13 (Dec 6 vs Buffalo, secondary reports)",
    "road_pants_variants": "white pants (2026 week 3) and silver pants (2026 week 4) with the white jersey",
}


# --------------------------------------------------------------------------------------------- glTF (read only)
_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
_DTYPE = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}


def gltf_triangles(path: Path, material: str, size=(512, 256)) -> list[np.ndarray]:
    """[(3, 5) arrays: rest position cm xyz + UV in texture pixels] for one material, read only."""
    g = json.loads(path.read_text())
    buffers = [(path.parent / b["uri"]).read_bytes() for b in g["buffers"]]

    def read(i):
        a = g["accessors"][i]; v = g["bufferViews"][a["bufferView"]]; dt = np.dtype(_DTYPE[a["componentType"]])
        k = _COUNT[a["type"]]; s = v.get("byteStride", dt.itemsize * k)
        arr = np.ndarray((a["count"], k), dt, buffers[v["buffer"]],
                         offset=v.get("byteOffset", 0) + a.get("byteOffset", 0), strides=(s, dt.itemsize)).copy()
        return arr.astype(np.float64)
    names = [m["name"] for m in g["materials"]]
    out = []
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            if names[p["material"]] != material:
                continue
            pos = read(p["attributes"]["POSITION"]); uv = read(p["attributes"]["TEXCOORD_0"]) * np.array(size, float)
            idx = read(p["indices"]).astype(np.int64).ravel()
            if p.get("mode", 4) == 5:
                tris = [idx[i:i + 3] if i % 2 == 0 else idx[[i + 1, i, i + 2]] for i in range(len(idx) - 2)]
            elif p.get("mode", 4) == 4:
                tris = idx.reshape(-1, 3)
            else:
                raise ValueError("unhandled primitive mode")
            out += [np.concatenate([pos[t], uv[t]], axis=1) for t in tris if len(set(t.tolist())) == 3]
    if not out:
        raise ValueError(f"{path.name} has no {material} triangles")
    return out


def armhole_segments(triangles: list[np.ndarray]) -> np.ndarray:
    """Open boundary edges of the welded jersey surface around the armholes: (n, 6) segment endpoints, cm."""
    key = {}
    ids = []
    for t in triangles:
        row = []
        for p in t[:, :3]:
            k = tuple(np.round(p * 1000).astype(np.int64))
            if k not in key:
                key[k] = (len(key), p)
            row.append(key[k][0])
        ids.append(row)
    P = np.zeros((len(key), 3))
    for i, p in key.values():
        P[i] = p
    count: dict[tuple[int, int], int] = {}
    for a, b, c in ids:
        for e in ((a, b), (b, c), (c, a)):
            e = (min(e), max(e))
            count[e] = count.get(e, 0) + 1
    segs = [(P[a], P[b]) for (a, b), n in count.items() if n == 1
            and min(P[a][1], P[b][1]) > 40.0 and min(abs(P[a][0]), abs(P[b][0])) > 15.0]
    if len(segs) < 8:
        raise ValueError("armhole boundary not found on the body export")
    return np.array([np.r_[a, b] for a, b in segs])


def distance_to_segments(points: np.ndarray, segs: np.ndarray) -> np.ndarray:
    A = segs[None, :, :3]; B = segs[None, :, 3:]
    p = points[:, None, :]
    ab = B - A
    t = np.clip(((p - A) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (A + t[..., None] * ab), axis=-1).min(axis=1)


def clip(poly: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Clip a polygon with per-vertex linear values (inside <= 0); every column is interpolated."""
    output = []
    for a, b, da, db in zip(poly, np.roll(poly, -1, axis=0), values, np.roll(values, -1)):
        if da <= 0:
            output.append(a)
        if (da <= 0) != (db <= 0):
            output.append(a + (b - a) * (da / (da - db)))
    return np.asarray(output)


def uv_outline_edges(triangles: list[np.ndarray]) -> set:
    """The UV edges used by one triangle only: the outlines of the texture islands (pixel UVs rounded to 1e-3)."""
    count: dict = {}
    for t in triangles:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            key = tuple(sorted((tuple(np.round(t[a, 3:5], 3)), tuple(np.round(t[b, 3:5], 3)))))
            count[key] = count.get(key, 0) + 1
    return {key for key, n in count.items() if n == 1}


def bleed_outline_edges(polygon, edges: list, pixels: float = 1.5) -> np.ndarray:
    """Pad a band piece across the island outline only (``edges``: the piece's triangle edges that are on it),
    keeping band boundaries fixed. Inside an island the pieces of a band meet exactly and the ``bands`` painter adds
    their coverages, so padding there is not needed; it would push a piece past its triangle along that triangle's
    own band line, a small tooth where the surface bends (seen in b8 renders)."""
    p = np.asarray(polygon, np.float64)
    area = np.sum(p[:, 0] * np.roll(p[:, 1], -1) - p[:, 1] * np.roll(p[:, 0], -1))
    if abs(area) < 1e-8 or not edges:
        return p
    lines = []
    for a, b in zip(p, np.roll(p, -1, axis=0)):
        edge = b - a
        length = np.linalg.norm(edge)
        if length < 1e-8:
            return p
        pad = 0.0
        for c, d in edges:
            v = d - c
            size = np.linalg.norm(v)
            if size and max(abs(np.cross(v, a - c)), abs(np.cross(v, b - c))) / size < 1e-5:
                pad = pixels
                break
        normal = np.array([edge[1], -edge[0]]) / length * np.sign(area)
        lines.append((a + normal * pad, edge))
    result = []
    for (a, u), (b, v) in zip(lines[-1:] + lines[:-1], lines):
        matrix = np.stack([u, -v], axis=1)
        if abs(np.linalg.det(matrix)) < 1e-9:
            return p
        result.append(a + u * np.linalg.solve(matrix, b - a)[0])
    return np.asarray(result)


def yoke_fields(points: np.ndarray, segs: np.ndarray, params: dict) -> tuple[np.ndarray, ...]:
    """Per point: distance from the armhole seam d, the insert width W and the signed height above its end cut."""
    side = points[:, 0] >= 0
    d = np.empty(len(points))
    left = segs[(segs[:, 0] + segs[:, 3]) > 0]
    right = segs[(segs[:, 0] + segs[:, 3]) < 0]
    d[side] = distance_to_segments(points[side], left)
    d[~side] = distance_to_segments(points[~side], right)
    y, z = points[:, 1], points[:, 2]
    lateral = params.get("back_lateral")
    if lateral:
        # on the back the 2026 bands run straight down (club photo #4 from behind), while the 2K5 pads flare the
        # armhole outward toward the shoulder top: below the shoulder the field is the lateral distance from a
        # vertical line at the back armhole, blended into the seam distance across the shoulder top
        w = np.clip((lateral["z_zero"] - z) / (lateral["z_zero"] - lateral["z_full"]), 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)
        d = (1.0 - w) * d + w * (lateral["x_ref"] - np.abs(points[:, 0]))
    front = z >= 0
    f = np.clip((params["front_taper_top_y"] - y) / (params["front_taper_top_y"] - params["front_end_y"]), 0.0, 1.0)
    W = np.where(front, params["panel_back_cm"] + (params["panel_front_end_cm"] - params["panel_back_cm"]) * f,
                 params["panel_back_cm"])
    above = y - np.where(front, params["front_end_y"], params["back_end_y"])
    return d, W, above


def yoke_stripe_bands(triangles: list[np.ndarray], colours: list[str], params: dict = YOKE) -> dict:
    """A ``bands`` decoration (tools/nfl2k5_team_2026_art.py decorate) in retail torso pixels: the outer red, the
    middle band (white home / navy road) and the inner red.

    Every read-only jersey triangle is split by midpoint subdivision and each piece is clipped by the band
    inequalities on its vertices' exact fields (linear across a piece). The same 3D fields drive the front and back
    islands, so the bands meet across every UV seam; the pieces of a band tile it without overlap, and only the
    islands' outlines get gutter padding (``uv_bleed_px``)."""
    segs = armhole_segments(triangles)
    outline = uv_outline_edges(triangles)
    red = float(params["red_cm"])
    bands: list[list] = [[], [], []]
    for tri in triangles:
        d, W, above = yoke_fields(tri[:, :3], segs, params)
        if (d > W + 2.0).all() or (above < -1.0).all():
            continue
        edges = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if tuple(sorted((tuple(np.round(tri[a, 3:5], 3)), tuple(np.round(tri[b, 3:5], 3))))) in outline:
                edges.append((tri[a, 3:5], tri[b, 3:5]))
        for sub in subdivide(tri, int(params.get("subdivide", 2))):
            d, W, above = yoke_fields(sub[:, :3], segs, params)
            if (d > W).all() or (above < 0).all():
                continue
            for i, polygon in _band_polygons(np.concatenate([sub, d[:, None], W[:, None], above[:, None]], axis=1),
                                             edges, red, params):
                bands[i].append(polygon)
    if not all(bands):
        raise ValueError("no yoke stripe coverage")
    return {"bands": [{"colour": c, "polygons": b} for c, b in zip(colours, bands)]}


def subdivide(tri: np.ndarray, levels: int) -> list[np.ndarray]:
    """Midpoint subdivision (4**levels pieces): the distance field is evaluated exactly at every new vertex, so the
    per-piece linear clip follows the curved band edges; positions and UVs stay on the original flat triangle."""
    pieces = [tri]
    for _ in range(levels):
        nxt = []
        for a, b, c in pieces:
            ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
            nxt += [np.array([a, ab, ca]), np.array([ab, b, bc]), np.array([ca, bc, c]), np.array([ab, bc, ca])]
        pieces = nxt
    return pieces


def _band_polygons(poly0, edges, red, params) -> list[tuple[int, list]]:
    items = []
    bands = (
        (lambda q: -q[:, 5], lambda q: q[:, 5] - red),
        (lambda q: red - q[:, 5], lambda q: q[:, 5] - (q[:, 6] - red)),
        (lambda q: (q[:, 6] - red) - q[:, 5], lambda q: q[:, 5] - q[:, 6]),
    )
    for i, (lower, upper) in enumerate(bands):
        poly = poly0
        for fn in (lower, upper, lambda q: -q[:, 7]):
            if len(poly) < 3:
                break
            poly = clip(poly, fn(poly))
        if len(poly) >= 3:
            uv = bleed_outline_edges(poly[:, 3:5], edges, float(params["uv_bleed_px"]))
            area = 0.5 * abs(float(np.sum(uv[:, 0] * np.roll(uv[:, 1], -1) - uv[:, 1] * np.roll(uv[:, 0], -1))))
            if area > 1e-4:
                items.append((i, np.round(uv, 3).tolist()))
    return items


# --------------------------------------------------------------------------------------------- recipe
def block_shapes() -> dict:
    """The 76.5 traced 2020 Patriots block numerals (unchanged; authored approximations, not a font file)."""
    return _b765().block_shapes()


def update_spec(source: Path, body: Path, out: Path) -> dict:
    spec = json.loads(source.read_text())
    if spec.get("team") != "NE":
        raise ValueError("this recipe owns only the Patriots")
    tris = gltf_triangles(body, "UNIF_jersey")
    for side, kit in spec["kits"].items():
        middle = "white" if side == "home" else "jersey_navy"
        t = kit["torso"]
        t["decorations"] = [yoke_stripe_bands(tris, ["red", middle, "red"]),
            {"mark": "logo_full", "center": list(CHEST["logo"]["center"]), "width": CHEST["logo"]["width"],
             "height": CHEST["logo"]["height"]}]
        t["chest_mark"] = {"mark": "wordmark", "colour": "white" if side == "home" else "jersey_navy",
                           "center": list(CHEST["wordmark"]["center"]), "width": CHEST["wordmark"]["width"],
                           "height": CHEST["wordmark"]["height"]}
        n = PANTS_STRIPE_PX
        kit["pants"]["stripe"] = [["red", n], ["jersey_navy" if side == "home" else "white", n], ["red", n]]
        if side == "away":
            kit["socks"] = {"colour": "white"}
        kit["helmet_digits"] = {"glyph_donor": kit["selector"], "fill": HELMET_DIGITS["fill"],
                                "glyph_shapes": block_shapes(), "glyph_height": HELMET_DIGITS["glyph_height"],
                                "glyph_center": list(HELMET_DIGITS["glyph_center"]), "registration": "as_authored"}
    spec["kits"]["home"]["note"] = (
        "2026 home: navy jersey; red-white-red yoke stripes over the shoulders, front and back, ending at the yoke "
        "seams; NFL shield at the collar; PATRIOTS wordmark with the Flying Elvis under it; white numbers with "
        "silver and red trim; Flying Elvis under the swoosh on the sleeves; silver pants with equal red-navy-red "
        "side stripes; navy socks; silver helmet, red facemask, navy number on the back, flag on the left rear")
    spec["kits"]["away"]["note"] = (
        "2026 road: white jersey; red-navy-red yoke stripes; navy PATRIOTS wordmark with the Flying Elvis under it; "
        "navy numbers with silver and red trim; navy pants with equal red-white-red side stripes (2026 week 1; "
        "the Patriots also wore white pants in week 3 and silver pants in week 4); white socks (every 2026 road "
        "game to date); the home helmet")
    spec["sources_u1_b77"] = SOURCES_B77
    spec["alternates_2026_not_built"] = ALTERNATES_2026
    spec["u1_b77"] = {
        "yoke_stripes_cm": dict(YOKE, coordinate="distance from the armhole seam of the rest-pose hi_body jersey "
                                "(open boundary edges above y 40 cm, |x| over 15 cm); on the back the lateral distance "
                                "from the line |x| = back_lateral.x_ref, blended into the seam distance across the "
                                "shoulder top (back_lateral.z_full to z_zero)"),
        "body_sha256": hashlib.sha256(body.read_bytes()).hexdigest(),
        "chest": {k: v for k, v in CHEST.items() if k != "erase"},
        "pants_stripe_px": PANTS_STRIPE_PX,
        "number_trims": "unchanged from v0.5 (silver 0.014, red 0.024 of the glyph height); see NUMBER note",
        "helmet_digits": HELMET_DIGITS,
        "helmet_back": "helmet02: the painted NFL shield on the back is removed (none on the 2026 helmets), the "
                       "US flag moves up 1.8 cm on the left rear; the navy number shows on the rear number quads",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_spec(spec), encoding="utf-8", newline="\n")
    return spec


def dumps_spec(spec: dict) -> str:
    """The recipe's usual indent-1 JSON; only the yoke band polygons are written one polygon per line."""
    doc = copy.deepcopy(spec)
    blobs = {}
    for kit in doc.get("kits", {}).values():
        for item in kit.get("torso", {}).get("decorations", []):
            for band in item.get("bands", []):
                rows = []
                for poly in band["polygons"]:
                    key = f"@@poly{len(blobs)}@@"
                    blobs[key] = json.dumps(poly, separators=(", ", ": "))
                    rows.append(key)
                band["polygons"] = rows
    text = json.dumps(doc, indent=1)
    for key, value in blobs.items():
        text = text.replace(json.dumps(key), value, 1)
    return text + "\n"


# --------------------------------------------------------------------------------------------- author (v0.5 base)
def _u8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _scope_native(cov_master: np.ndarray, grow: int = 1) -> np.ndarray:
    """Native texels whose 4x4 master block any coverage touches, grown by ``grow`` texels (filter footprint)."""
    from scipy import ndimage
    h, w = cov_master.shape[0] // MASTER, cov_master.shape[1] // MASTER
    scope = cov_master.reshape(h, MASTER, w, MASTER).max(axis=(1, 3)) > 1e-6
    return ndimage.binary_dilation(scope, iterations=grow) if grow else scope


def _decorations_coverage(shape, items: list) -> np.ndarray:
    cov = np.zeros(shape, np.float32)
    for item in items:
        polys = [item["polygon"]] if "polygon" in item else [p for b in item.get("bands", []) for p in b["polygons"]]
        for points in polys:
            cov = np.maximum(cov, art.polygon_coverage(shape, [(x * MASTER, y * MASTER) for x, y in points]))
    return cov


def _jersey_levels(resource: Path, baseline: np.ndarray):
    """The kit's stored clean/mud jersey levels (the coarse mips keep their own pixels outside the scope)."""
    import nfl_tset_png_import as tset
    from nfl_txtr import HEADER, Chunk, decode_chunk
    data = resource.read_bytes()
    start = 0x70
    header = HEADER.unpack_from(data, start)
    if header[0] != b"TSET":
        raise ValueError("unexpected jersey TSET location")
    span = data[start:start + HEADER.size + header[1]]
    clean, mud = tset.decode_tset_levels(decode_chunk(span, Chunk(1, 0, header[0].decode(), *header[1:]))[0])
    if clean[0].rgba != baseline.tobytes():
        raise ValueError("baseline torso PNG does not match the stored jersey pixels")
    for c, m in zip(clean, mud):
        if bytes((v * 60 + 50) // 100 if i % 4 != 3 else v for i, v in enumerate(c.rgba)) != m.rgba:
            raise ValueError("stored mud palette differs from the darken_60 rule")
    return clean


def author_torso(spec: "art.Spec", kit: dict, old_kit: dict, before: Path, resource: Path, marks: Path):
    """The 2026 yoke stripes and chest mark on the shipped jersey; everything outside their scope stays exact."""
    sel = kit["selector"]
    t = kit["torso"]
    base_u8 = np.asarray(Image.open(before / sel / "torso.png").convert("RGBA")).copy()
    master = art.upscale(base_u8.astype(np.float32) / 255.0)
    shape = master.shape[:2]
    base_col = spec.colour(t["base_colour"])
    # 1. the 76.5 stripes and the v0.5 wordmark go back to the jersey colour
    old_items = [d for d in old_kit["torso"].get("decorations", []) if "polygon" in d or "bands" in d]
    from scipy import ndimage
    old_cov = ndimage.grey_dilation(_decorations_coverage(shape, old_items), size=2 * MASTER + 1)
    x0, y0, x1, y1 = CHEST["erase"]
    old_cov = np.maximum(old_cov, art.rect_coverage(shape, x0 * MASTER, y0 * MASTER, x1 * MASTER, y1 * MASTER))
    art.over(master, base_col, old_cov)
    # 2. the 2026 art, in the art tool's own order: chest mark, then decorations (bands, the logo under the mark)
    before_new = master.copy()
    mark = t["chest_mark"]
    path = marks / spec.data["marks"][mark["mark"]]
    cov = art.mark_coverage(path, shape, (mark["center"][0] * MASTER, mark["center"][1] * MASTER),
                            mark["width"] * MASTER, height=float(mark["height"]) * MASTER if mark.get("height") else None)
    art.over(master, spec.colour(mark["colour"]), cov)
    master = art.decorate(master, spec, t["decorations"], marks, "torso")
    new_cov = (np.abs(master - before_new).sum(axis=2) > 1e-5).astype(np.float32)
    scope = _scope_native(np.maximum(old_cov, new_cov), grow=1)
    native = _u8(art.downscale(master))
    native[~scope] = base_u8[~scope]
    # 3. palette lock: protected colours and the protected coarse mip texels stay exactly as stored
    clean = _jersey_levels(resource, base_u8)
    tail = b"".join(level.rgba for level in clean[1:])
    locked = np.unique(base_u8[~scope].reshape(-1, 4), axis=0).tolist()
    preservation = {"scope_bits": base64.b64encode(np.packbits(scope).tobytes()).decode(),
                    "clean_tail_zlib": base64.b64encode(zlib.compress(tail, 9)).decode(),
                    "clean_tail_sha256": hashlib.sha256(tail).hexdigest()}
    meta = PngImagePlugin.PngInfo()
    meta.add_text("nfl2k5_palette_lock", json.dumps({"schema": "nfl2k5_palette_lock/v1", "rgba": locked,
                                                    "preserve_mips": preservation}, separators=(",", ":")))
    return native, master, scope, meta, {"locked_palette_colors": len(locked)}


def author_pants(spec: "art.Spec", kit: dict, before: Path):
    """Three equal 2.4 cm bands in both outer-seam bands of the shipped pants (the 2022+ stripe set)."""
    sel = kit["selector"]
    base_u8 = np.asarray(Image.open(before / sel / "pants.png").convert("RGBA")).copy()
    master = art.upscale(base_u8.astype(np.float32) / 255.0)
    shape = master.shape[:2]
    H = shape[0]
    p = kit["pants"]
    total = sum(int(n) for _, n in p["stripe"])
    cov_all = np.zeros(shape, np.float32)
    for band, (x0, x1) in enumerate(art.PANTS_STRIPE_BANDS):
        start = (x0 + x1) / 2.0 - total / 2.0
        stripes = p["stripe"] if band == 0 else list(reversed(p["stripe"]))
        for name, n in stripes:
            c = art.rect_coverage(shape, start * MASTER, 0, (start + n) * MASTER, H)
            art.over(master, spec.colour(name), c)
            cov_all = np.maximum(cov_all, c)
            start += n
    scope = _scope_native(cov_all, grow=1)
    native = _u8(art.downscale(master))
    native[~scope] = base_u8[~scope]
    return native, master, scope


def author_socks(spec: "art.Spec", kit: dict, retail: Path):
    """The road socks in white with the retail fabric shading (the art tool's own socks rule)."""
    equipment = retail / "equipment"
    master = art.author_socks(spec, kit, retail, equipment)
    native = _u8(art.downscale(master))
    mud = native.copy()
    mud[..., :3] = ((native[..., :3].astype(np.int32) * 60 + 50) // 100).astype(np.uint8)
    return native, master, mud


def author_digits(spec: "art.Spec", kit: dict, before: Path, family: str, block_key: str) -> list:
    out = []
    block = kit[block_key]
    for n in range(10):
        kit_f = dict(kit, _glyphs=block)
        name = f"digit_{family}_{n}"
        master = art.author_glyphs(spec, kit_f, before, name, "_glyphs")
        out.append((n, _u8(art.downscale(master)), master))
    return out


# --------------------------------------------------------------------------------------------- helmet back
# 2026 rear view (club shoot, #4): the US flag on the left rear about 4.4 cm above the rear bumper, the navy number
# just right of centre above the bumper, the warning label right; no NFL shield on the back. k2 painted the flag
# and the 2008 shield on the shell C art (helmet02) from a pre-2026 photo; the number quads (NUMBER_helmet_C) are
# geometry and stay where they are. Positions are rest-pose head cm (x: the player's left is +x, y up, z forward).
HELMET_BACK = {
    "shield_box_px": [167, 213, 182, 227],   # k2's painted shield (helmet02 texels), removed
    "shield_min_y": 39.25,                   # the white rear plate starts below this height (cm)
    "old_flag_cm": {"x": [3.4, 8.8], "y": [39.6, 43.4], "z_max": 1.2},
    # centre: 4.1 cm above the rear plate (the 2026 photo shows 4.4 cm; k2's flag sat 2.3 cm above it), wholly on the
    # shell's main back island (the strip island below y 42.2 cm would carry a sliver of it); k2's size is kept
    "flag": {"centre": [6.1, 43.4], "size": [4.4, 2.32], "depth": 1.2},
    "colours": {"red": "#B22234", "white": "#FFFFFF", "blue": "#3C3B6E"},   # the flag's standard colours
}


def us_flag(width: int = 1900, height: int = 1000) -> np.ndarray:
    """The US flag drawn from its public specification (13 stripes, canton 0.4 of the fly over 7 stripes, 50 stars),
    straight RGBA float, canton at the left."""
    from PIL import ImageDraw
    c = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in HELMET_BACK["colours"].items()}
    img = Image.new("RGB", (width, height), c["white"])
    d = ImageDraw.Draw(img)
    stripe = height / 13.0
    for i in range(0, 13, 2):
        d.rectangle([0, round(i * stripe), width, round((i + 1) * stripe) - 1], fill=c["red"])
    cw, ch = 0.4 * width, 7 * stripe
    d.rectangle([0, 0, round(cw) - 1, round(ch) - 1], fill=c["blue"])
    r = 0.0616 * height / 2
    for row in range(9):
        cols = 6 if row % 2 == 0 else 5
        for col in range(cols):
            x = (col * 2 + (1 if row % 2 == 0 else 2)) * cw / 12.0
            y = (row + 1) * ch / 10.0
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                rr = r if k % 2 == 0 else r * 0.382
                pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
            d.polygon(pts, fill=c["white"])
    out = np.ones((height, width, 4), np.float32)
    out[..., :3] = np.asarray(img, np.float32) / 255.0
    return out


def helmet_posmap(geometry: Path, size: int = 256 * MASTER) -> np.ndarray:
    """Rest position (cm) under every master texel of the shell C art, from the Studio's head export (read only)."""
    doc = json.loads(geometry.read_text())["HI_HELMET_C"]
    P = np.asarray(doc["pos"], np.float64)
    U = np.asarray(doc["uv"], np.float64) * size
    pm = np.full((size, size, 3), np.nan)
    for t in doc["tris"]:
        if len(set(t)) < 3:
            continue
        pos, uv = P[list(t)], U[list(t)]
        x0, y0 = np.maximum(np.floor(uv.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(uv.max(0)).astype(int), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        m = np.array([[uv[1, 0] - uv[0, 0], uv[2, 0] - uv[0, 0]], [uv[1, 1] - uv[0, 1], uv[2, 1] - uv[0, 1]]])
        if abs(np.linalg.det(m)) < 1e-12:
            continue
        l = np.stack([xs - uv[0, 0], ys - uv[0, 1]], -1) @ np.linalg.inv(m).T
        w1, w2 = l[..., 0], l[..., 1]
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if inside.any():
            q = w0[..., None] * pos[0] + w1[..., None] * pos[1] + w2[..., None] * pos[2]
            sub = pm[y0:y1 + 1, x0:x1 + 1]
            sub[inside] = q[inside]
    return pm


def author_helmet_back(spec: "art.Spec", kit: dict, before: Path, geometry: Path):
    """helmet02 (shell C, worn by the whole roster): k2's back shield removed, the flag moved up. Alpha, and every
    texel outside the scope, stay exact; protected coarse mips keep their stored texels."""
    from scipy import ndimage
    sel = kit["selector"]
    base_u8 = np.asarray(Image.open(before / sel / "helmet_helmet02.png").convert("RGBA")).copy()
    master = art.upscale(base_u8.astype(np.float32) / 255.0)
    pm = helmet_posmap(geometry)
    x, y, z = pm[..., 0], pm[..., 1], pm[..., 2]
    ok = ~np.isnan(x)
    shell = spec.colour(kit["helmet"]["shell"])
    rgb = master[..., :3].copy()
    hb = HELMET_BACK
    # the old shield (its box, above the white rear plate) and the old flag (every shell texel in its 3D box: the
    # flag's white stripes are as bright as lit shell, so a colour test leaves them behind)
    x0, y0, x1, y1 = hb["shield_box_px"]
    box = np.zeros(ok.shape, bool)
    box[y0 * MASTER:(y1 + 1) * MASTER, x0 * MASTER:(x1 + 1) * MASTER] = True
    yy = np.nan_to_num(y, nan=-99.0)
    erase = box & ok & (yy > hb["shield_min_y"])
    of = hb["old_flag_cm"]
    erase |= ok & (np.nan_to_num(x) > of["x"][0]) & (np.nan_to_num(x) < of["x"][1]) & \
        (yy > of["y"][0]) & (yy < of["y"][1]) & (np.nan_to_num(z, nan=9) < of["z_max"])
    erase = ndimage.binary_dilation(erase, iterations=2) & ok & (yy > hb["shield_min_y"] - 0.05)
    # the gutter texels around the old decals carried their colour as filter bleed: clear them with the hole
    erase |= ndimage.binary_dilation(erase, iterations=2 * MASTER) & ~ok
    # fill from the surrounding plain shell only: the reference is the shell colour measured in a ring around the
    # hole, and white (the rear plate), the logo and the vents get no weight
    ring = ndimage.binary_dilation(erase, iterations=6 * MASTER) & ~erase & ok
    plain = ring & (np.linalg.norm(rgb - shell[None, None, :], axis=2) < 0.12)
    ref = np.median(rgb[plain], axis=0) if plain.any() else shell
    shellness = np.exp(-(np.linalg.norm(rgb - ref[None, None, :], axis=2) / 0.06) ** 2)
    master = art._inpaint_weighted(master, erase.astype(np.float32), shellness, 2.0 * MASTER)
    luma = master[..., :3] @ art.LUMA
    k = np.clip(luma / max(float(ref @ art.LUMA), 1e-3), 0.0, 2.5)
    # the new flag: a decal projected along the shell's normal at its centre (true size on the surface)
    f = hb["flag"]
    target = np.array([f["centre"][0], f["centre"][1]])
    cand = ok & (np.nan_to_num(z, nan=9) < 2.0) & (np.nan_to_num(x) > 0)
    dist = np.hypot(np.nan_to_num(x) - target[0], np.nan_to_num(y) - target[1])
    dist[~cand] = np.inf
    iy, ix = np.unravel_index(np.argmin(dist), dist.shape)
    C = pm[iy, ix]
    near = ok & (np.linalg.norm(np.nan_to_num(pm) - C, axis=2) < 2.0)
    Q = pm[near] - C
    n = np.linalg.svd(Q - Q.mean(0), full_matrices=False)[2][-1]
    if n[2] > 0:
        n = -n                                    # outward on the back of the shell
    t1 = np.cross(n, [0.0, 1.0, 0.0]); t1 /= np.linalg.norm(t1)
    if t1[0] > 0:
        t1 = -t1                                  # the fly runs toward the helmet's centre line; canton outboard
    t2 = np.cross(t1, n); t2 /= np.linalg.norm(t2)
    if t2[1] > 0:
        t2 = -t2                                  # image rows run down
    rel = np.nan_to_num(pm) - C
    u = rel @ t1 / f["size"][0] + 0.5
    v = rel @ t2 / f["size"][1] + 0.5
    depth = np.abs(rel @ n)
    flag = us_flag()
    texel_cm = 0.10                               # about one master texel on the shell's back
    soft = np.minimum.reduce([u * f["size"][0], (1 - u) * f["size"][0], v * f["size"][1], (1 - v) * f["size"][1]])
    alpha = np.clip(soft / texel_cm + 0.5, 0.0, 1.0) * (ok & (depth < f["depth"]))
    sample = art._sample(flag, np.clip(u, 0, 1), np.clip(v, 0, 1))
    a = alpha[..., None]
    col = np.where(sample[..., 3:4] > 1e-6, sample[..., :3] / np.maximum(sample[..., 3:4], 1e-6), 0.0)
    light = np.clip(k[..., None], 0.85, 1.1)      # keep the shell's baked light on the decal
    master[..., :3] = master[..., :3] * (1 - a) + np.clip(col * light, 0, 1) * a
    changed = erase | (alpha > 0)
    scope = _scope_native(changed.astype(np.float32), grow=1)
    native = _u8(art.downscale(master))
    native[..., 3] = base_u8[..., 3]               # the art's alpha (quads hidden, reflection weight) is kept exactly
    native[~scope] = base_u8[~scope]
    meta, info = helmet_mip_lock(before / ".." / "resources" / f"{sel}.IFF", base_u8, native, scope)
    return native, master, scope, meta, dict(info, flag_centre_cm=C.round(2).tolist(),
                                             flag_normal=n.round(3).tolist())


def helmet_mip_lock(resource: Path, base_u8: np.ndarray, native: np.ndarray, scope: np.ndarray):
    """Authored helmet mips for the importer (``nfl2k5_palette_lock`` with ``helmet_mips``), from the stored levels."""
    from nfl_txtr import parse_chunks, decode_chunk
    from nfl_live_helmet_txtr_png_import import decode_levels
    data = resource.resolve().read_bytes()
    levels = None
    for chunk in parse_chunks(data):
        if chunk.kind == "TXTR" and chunk.index == 12:
            decoded, _ = decode_chunk(data, chunk)
            levels = decode_levels(decoded)
    if levels is None or levels[0].rgba != base_u8.tobytes():
        raise ValueError("baseline helmet02 PNG does not match the stored texture")
    stored = [np.frombuffer(level.rgba, np.uint8).reshape(level.height, level.width, 4) for level in levels]
    tail, locked = authored_mips(stored, native, scope)
    if len(locked) > 255:
        raise ValueError("protected helmet colours leave no palette room for the new art")
    meta = PngImagePlugin.PngInfo()
    meta.add_text("nfl2k5_palette_lock", json.dumps({
        "schema": "nfl2k5_palette_lock/v1", "rgba": [list(c) for c in locked],
        "helmet_mips": {"schema": "nfl2k5_helmet_mips/v1",
                        "base_rgba_sha256": hashlib.sha256(native.tobytes()).hexdigest(),
                        "tail_zlib": base64.b64encode(zlib.compress(tail, 9)).decode(),
                        "tail_sha256": hashlib.sha256(tail).hexdigest()}}, separators=(",", ":")))
    return meta, {"locked_palette_colors": len(locked)}


def authored_mips(stored: list[np.ndarray], native: np.ndarray, scope: np.ndarray) -> tuple[bytes, list]:
    """The coarse levels for a scope-limited edit: a texel whose base footprint misses the scope keeps its stored
    RGBA; the rest are the importer's own 2x2 box filter of the level above. Returns the RGBA tail of levels 1..n
    and every colour a protected texel shows at any level (to reserve in the palette)."""
    if stored[0].shape != native.shape or scope.shape != native.shape[:2]:
        raise ValueError("mip base dimensions differ")
    cur = native.astype(np.int64)
    mask = scope.copy()
    tail = bytearray()
    protected = set(map(tuple, native[~scope].reshape(-1, 4).tolist()))
    for level in stored[1:]:
        h, w = level.shape[:2]
        down = (cur.reshape(h, 2, w, 2, 4).sum(axis=(1, 3)) + 2) // 4
        mask = mask.reshape(h, 2, w, 2).any(axis=(1, 3))
        keep = level.astype(np.int64)
        out = np.where(mask[..., None], down, keep)
        protected |= set(map(tuple, keep[~mask].reshape(-1, 4).tolist()))
        tail += out.astype(np.uint8).tobytes()
        cur = out
    return bytes(tail), sorted(protected)


# --------------------------------------------------------------------------------------------- author command
def _save_png(arr: np.ndarray, path: Path, meta: PngImagePlugin.PngInfo | None = None,
              registration: str | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if registration:
        meta = meta or PngImagePlugin.PngInfo()
        meta.add_text("nfl2k5_digit_registration", registration)
    Image.fromarray(arr, "RGBA").save(path, pnginfo=meta, optimize=False, compress_level=9)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def author(spec_path: Path, old_spec_path: Path, before: Path, retail: Path, marks: Path, uniform_marks: Path,
           helmet_geometry: Path, out: Path, cards: Path | None = None, body: Path | None = None,
           sideline: Path | None = None) -> dict:
    """Every b77 Patriots texture on top of the shipped v0.5 kit; writes art, masters, scopes and project.json."""
    spec = art.Spec(spec_path)
    art.use_uniform_marks(uniform_marks)
    old = json.loads(old_spec_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    # the art tool's socks rule reads the retail socks as tset_<outer>_4_0_socks00.png
    (retail / "equipment").mkdir(exist_ok=True)
    edits, receipts = [], []
    for side, kit in spec.data["kits"].items():
        sel, code, side_code = kit["selector"], spec.data["asset_code"], kit["selector"][2]
        old_kit = old["kits"][side]
        dest = out / "retail" / sel
        mdir = out / "master4x" / sel
        resource = before.parent / "resources" / f"{sel}.IFF"
        # torso
        native, master, scope, meta, info = author_torso(spec, kit, old_kit, before, resource, marks)
        path = dest / "torso.png"
        sha = _save_png(native, path, meta)
        _save_png(_u8(master), mdir / "torso.png")
        _save_png((scope * 255).astype(np.uint8)[..., None].repeat(4, 2), dest / "torso_scope.png")
        edits.append({"kind": "torso", "asset_code": code, "side": side_code, "variant": 0,
                      "clean_png": str(path), "mud_png": None, "mud_mode": "darken_60"})
        receipts.append(dict(selector=sel, name="torso", sha256=sha, scope_texels=int(scope.sum()), **info))
        # pants
        native, master, scope = author_pants(spec, kit, before)
        path = dest / "pants.png"
        sha = _save_png(native, path)
        _save_png(_u8(master), mdir / "pants.png")
        _save_png((scope * 255).astype(np.uint8)[..., None].repeat(4, 2), dest / "pants_scope.png")
        edits.append({"kind": "pants", "asset_code": code, "side": side_code, "variant": 0,
                      "clean_png": str(path), "mud_png": None, "mud_mode": "darken_60"})
        receipts.append(dict(selector=sel, name="pants", sha256=sha, scope_texels=int(scope.sum())))
        # socks: only the road set changes colour (white in every 2026 road game to date)
        if kit["socks"] != old_kit["socks"]:
            src = retail / "uniforms" / sel / "socks00.png"
            eq = retail / "equipment" / f"tset_{kit['outer_index']}_4_0_socks00.png"
            if not eq.exists():
                eq.write_bytes(src.read_bytes())
            native, master, mud = author_socks(spec, kit, retail)
            path, mud_path = dest / "socks00.png", dest / "socks00_mud.png"
            sha = _save_png(native, path); _save_png(mud, mud_path)
            _save_png(_u8(master), mdir / "socks00.png")
            outer = kit["outer_index"]
            edits.append({"kind": "uniform_equipment_texture", "asset_id": f"tset:{outer}:4:0:socks00",
                          "png": str(path)})
            edits.append({"kind": "uniform_equipment_texture", "asset_id": f"tset:{outer}:4:1:socks00_mud",
                          "png": str(mud_path)})
            receipts.append(dict(selector=sel, name="socks00", sha256=sha))
        # jersey numbers (trims) and helmet numbers (navy)
        for family, key, project_family in (("helmet", "helmet_digits", "helmet_digit"),):
            for n, native, master in author_digits(spec, kit, before, family, key):
                path = dest / f"digit_{family}_{n}.png"
                sha = _save_png(native, path, registration=kit[key].get("registration"))
                _save_png(_u8(master), mdir / f"digit_{family}_{n}.png")
                edits.append({"kind": "live_number_nameplate", "family": project_family, "asset_code": code,
                              "side": side_code, "variant": 0, "digit": n, "png": str(path)})
                receipts.append(dict(selector=sel, name=f"digit_{family}_{n}", sha256=sha))
        # helmet02 back
        native, master, scope, meta, info = author_helmet_back(spec, kit, before, helmet_geometry)
        path = dest / "helmet_helmet02.png"
        sha = _save_png(native, path, meta)
        _save_png(_u8(master), mdir / "helmet_helmet02.png")
        _save_png((scope * 255).astype(np.uint8)[..., None].repeat(4, 2), dest / "helmet02_scope.png")
        edits.append({"kind": "live_helmet", "asset_code": code, "side": side_code, "variant": 0,
                      "family": "helmet02", "png": str(path)})
        receipts.append(dict(selector=sel, name="helmet_helmet02", sha256=sha, scope_texels=int(scope.sum()), **info))
        # the sideline players' small atlas
        if body and sideline:
            native, master, scope = author_splayer(spec, kit, old_kit, before, body, sideline)
            path = dest / "splayer.png"
            sha = _save_png(native, path)
            _save_png(_u8(master), mdir / "splayer.png")
            _save_png((scope * 255).astype(np.uint8)[..., None].repeat(4, 2), dest / "splayer_scope.png")
            edits.append({"kind": "p8_texture", "asset_id": f"p8:{kit['outer_index']}:splayer", "png": str(path)})
            receipts.append(dict(selector=sel, name="splayer", sha256=sha, scope_texels=int(scope.sum())))
        # Team Select cards re-rendered from this art (tools/b77/u1_cards.py), when given
        if cards:
            for family, res in (("unif", 256), ("helm", 256), ("helm", 128)):
                card = cards / sel / f"team-select_{family}_{res}.png"
                if card.exists():
                    edits.append({"kind": "team_select", "asset_code": code,
                                  "side": "home" if side_code == "H" else "away", "style": 0, "family": family,
                                  "resolution": res, "png": str(card)})
    project = {"schema": "nfl2k5_visual_mod_project/v1", "purpose": "b77 u1 Patriots 2026 kit correction",
               "edits": edits}
    (out / "project.json").write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
    (out / "author_receipt.json").write_text(json.dumps({"schema": "b77/u1/author-receipt/v1",
        "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(), "items": receipts}, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    return project


# --------------------------------------------------------------------------------------------- compile
def _equipment_writer():
    import importlib.util
    name = "_b77_u1_equipment_writer"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "mod_editor/core/nfl2k5_uniform_equipment_writer.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _p8_writer():
    import importlib.util
    name = "_b77_u1_p8_writer"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "mod_editor/core/nfl2k5_p8_texture_writer.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _chunk_span(resource: bytes, index: int) -> tuple[int, int]:
    from nfl_txtr import parse_chunks
    for chunk in parse_chunks(resource):
        if chunk.index == index:
            return chunk.offset, chunk.end_offset - chunk.offset
    raise ValueError(f"chunk {index} absent")


def compile_project(project_path: Path, before_resources: Path, v05_cards: Path | None, out: Path,
                    index: Path | None = None) -> dict:
    """Every edit through the Studio's own importer; spans are recorded against the shipped v0.5 bytes.

    ``index``: the retail ``vc_53450030/0`` the importers read their templates from (default: the checkout's
    ``extracted/`` copy); the importers pin its size and SHA-256 themselves."""
    import nfl2k5_jersey_png_workflow as defaults
    import nfl_jersey_tset_png_import as jersey_import
    import nfl_jersey_tset_targets as jersey_targets
    import nfl_pants_tset_png_import as pants_import
    import nfl_pants_tset_targets as pants_targets
    import nfl_live_numbers_nameplate_png_import as digit_import
    import nfl_live_numbers_nameplate_targets as digit_targets
    import nfl_live_helmet_txtr_png_import as helmet_import
    import nfl_live_helmet_txtr_targets as helmet_targets
    import nfl_team_select_card_png_import as card_import
    doc = json.loads(project_path.read_text())
    INDEX = Path(index) if index else defaults.DEFAULT_INDEX
    out.mkdir(parents=True, exist_ok=True)
    (out / "decoded").mkdir(exist_ok=True)
    spans: dict[str, list] = {}
    reports = []
    resources: dict[str, bytes] = {}
    card_index = json.loads((v05_cards / "cards.json").read_text()) if v05_cards else []

    def record(resource_key: str, offset: int, span: bytes, before: bytes, label: str):
        if len(span) != len(before):
            raise ValueError(f"{label}: stored span size changed")
        path = out / f"{hashlib.sha256(span).hexdigest()}.span"
        path.write_bytes(span)
        spans.setdefault(resource_key, []).append({
            "offset": offset, "length": len(span), "label": label,
            "before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": hashlib.sha256(span).hexdigest(),
            "replacement": path.name})

    def resource(name: str) -> bytes:
        if name not in resources:
            resources[name] = (before_resources / name).read_bytes()
        return resources[name]

    equipment_groups: dict[str, list] = {}
    for edit in doc["edits"]:
        kind = edit["kind"]
        if kind in ("torso", "pants", "sleeve"):
            code, side = edit["asset_code"], edit["side"]
            name = f"{code}{side}{edit['variant']}.IFF"
            if kind == "sleeve":      # b77 u2a: the sleeve texture (CLE), same importer route as the pants
                import nfl_sleeve_tset_png_import as sleeve_import
                import nfl_sleeve_tset_targets as sleeve_targets
                _, _, _, target = sleeve_targets.select_target(code, side, edit["variant"], sleeve_targets.DEFAULT_REPORT)
                span, previews, receipt = sleeve_import.import_png(
                    INDEX, defaults.DEFAULT_INVENTORY, sleeve_targets.DEFAULT_REPORT, target,
                    Path(edit["clean_png"]), None, edit["mud_mode"])
            elif kind == "torso":
                _, _, _, target = jersey_targets.select_target(code, side, edit["variant"], jersey_targets.DEFAULT_REPORT)
                span, previews, receipt = jersey_import.import_png(
                    INDEX, defaults.DEFAULT_INVENTORY, jersey_targets.DEFAULT_REPORT, target,
                    Path(edit["clean_png"]), None, edit["mud_mode"])
            else:
                _, _, _, target = pants_targets.select_target(code, side, edit["variant"], pants_targets.DEFAULT_REPORT)
                span, previews, receipt = pants_import.import_png(
                    INDEX, defaults.DEFAULT_INVENTORY, pants_targets.DEFAULT_REPORT, target,
                    Path(edit["clean_png"]), None, edit["mud_mode"])
            data = resource(name)
            start = target.chunk_offset
            record(name, start, span, data[start:start + target.span_size], kind)
            for i, (_label, png) in enumerate(previews):
                (out / "decoded" / f"{name[:-4]}_{kind}{'' if i == 0 else '_mud'}.png").write_bytes(png)
            reports.append({"resource": name, "kind": kind, "receipt": receipt})
        elif kind == "live_number_nameplate":
            code, side, family, digit = edit["asset_code"], edit["side"], edit["family"], edit["digit"]
            name = f"{code}{side}{edit['variant']}.IFF"
            _, _, target = digit_targets.select_target(family, code, side, edit["variant"], digit,
                                                       digit_targets.DEFAULT_REPORT)
            span, png, receipt = digit_import.build_import(INDEX, digit_targets.DEFAULT_REPORT,
                                                           family, code, side, edit["variant"], digit,
                                                           Path(edit["png"]))
            data = resource(name)
            start = target.chunk_offset
            record(name, start, span, data[start:start + target.span_size], f"{family}_{digit}")
            (out / "decoded" / f"{name[:-4]}_{family}_{digit}.png").write_bytes(png)
            reports.append({"resource": name, "kind": kind, "family": family, "digit": digit, "receipt": receipt})
        elif kind == "live_helmet":
            code, side, family = edit["asset_code"], edit["side"], edit["family"]
            name = f"{code}{side}{edit['variant']}.IFF"
            _, _, _, target = helmet_targets.select_target(code, side, edit["variant"], family,
                                                           helmet_targets.DEFAULT_REPORT)
            span, previews, receipt = helmet_import.build_import(INDEX, helmet_targets.DEFAULT_REPORT,
                                                                 code, side, edit["variant"], family, Path(edit["png"]))
            data = resource(name)
            start = target.chunk_offset
            record(name, start, span, data[start:start + target.span_size], family)
            for label, png in previews[:1]:
                (out / "decoded" / f"{name[:-4]}_{family}.png").write_bytes(png)
            reports.append({"resource": name, "kind": kind, "family": family, "receipt": receipt})
        elif kind == "p8_texture":
            outer = edit["asset_id"].split(":")[1]
            name = NE_OUTER[outer]
            span, previews, report, _sel, _rec = _p8_writer().build_unified_p8_texture_import(
                INDEX, edit["asset_id"], Path(edit["png"]))
            data = resource(name)
            start, length = _chunk_span(data, 51)
            record(name, start, span, data[start:start + length], "splayer")
            for label, png in previews[:1]:
                (out / "decoded" / f"{name[:-4]}_splayer.png").write_bytes(png)
            reports.append({"resource": name, "kind": kind, "report": report})
        elif kind == "uniform_equipment_texture":
            outer = edit["asset_id"].split(":")[1]
            equipment_groups.setdefault(outer, []).append((edit["asset_id"], Path(edit["png"])))
        elif kind == "team_select":
            span, preview, receipt = card_import.build_import(
                INDEX, ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
                edit["family"], edit["asset_code"], edit["side"], edit["style"], edit["resolution"], Path(edit["png"]))
            tex = f"{edit['family']}_{edit['side'][0]}{edit['asset_code']}_{edit['style']}"
            row = [c for c in card_index if c["name"] == tex and c["width"] == edit["resolution"]]
            if len(row) != 1:
                raise ValueError(f"{tex} {edit['resolution']} is not in the shipped card index")
            row = row[0]
            key = f"outer:{row['outer_index']}"
            if hashlib.sha256(span).hexdigest() != row["span_sha256"]:
                spans.setdefault(key, [])
                path = out / f"{hashlib.sha256(span).hexdigest()}.span"
                path.write_bytes(span)
                if len(span) != row["span_size"]:
                    raise ValueError(f"{tex}: card span size changed")
                spans[key].append({"offset": row["chunk_offset"], "length": len(span), "label": f"{tex}_{edit['resolution']}",
                                   "before_sha256": row["span_sha256"],
                                   "after_sha256": hashlib.sha256(span).hexdigest(), "replacement": path.name})
            (out / "decoded" / f"{tex}_{edit['resolution']}.png").write_bytes(preview)
            reports.append({"resource": key, "kind": kind, "card": tex, "receipt": receipt})
        else:
            raise ValueError(f"unowned edit kind {kind}")
    writer = _equipment_writer()
    for outer, rows in equipment_groups.items():
        rebuilt, previews, report, selector, target_record = writer.build_unified_uniform_equipment_imports(
            INDEX, rows, suggest_fit=False)
        name = NE_OUTER[outer]
        data = resource(name)
        chunk_index = int(rows[0][0].split(":")[2])
        start, length = _chunk_span(data, chunk_index)
        record(name, start, rebuilt, data[start:start + length], "socks00")
        for label, png in previews:
            (out / "decoded" / f"{name[:-4]}_{label}").write_bytes(png)
        reports.append({"resource": name, "kind": "uniform_equipment_texture", "report": report})
    for patches in spans.values():
        patches.sort(key=lambda p: p["offset"])
    manifest = {"schema": SCHEMA_MANIFEST, "resources": spans}
    (out / "native_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    (out / "compile_receipts.json").write_text(json.dumps(reports, indent=1, sort_keys=True, default=str) + "\n",
                                               encoding="utf-8", newline="\n")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("update-spec")
    s.add_argument("--spec", type=Path, required=True); s.add_argument("--body-gltf", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("author")
    s.add_argument("--spec", type=Path, required=True); s.add_argument("--old-spec", type=Path, required=True)
    s.add_argument("--before", type=Path, required=True, help="the v0.5 kit export's uniforms/ folder")
    s.add_argument("--retail", type=Path, required=True, help="the retail kit export (uniforms/<set>/socks00.png)")
    s.add_argument("--marks", type=Path, required=True); s.add_argument("--uniform-marks", type=Path, required=True)
    s.add_argument("--helmet-geometry", type=Path, required=True); s.add_argument("--cards", type=Path)
    s.add_argument("--body-gltf", type=Path, help="hi_body export (the splayer's 3D band transfer)")
    s.add_argument("--sideline-gltf", type=Path, help="sideline_player export (SIDELINE_player)")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("compile")
    s.add_argument("--project", type=Path, required=True); s.add_argument("--before-resources", type=Path, required=True)
    s.add_argument("--v05-cards", type=Path); s.add_argument("--index", type=Path)
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "update-spec":
        update_spec(a.spec, a.body_gltf, a.out)
    elif a.command == "author":
        author(a.spec, a.old_spec, a.before, a.retail, a.marks, a.uniform_marks, a.helmet_geometry, a.out, a.cards,
               a.body_gltf, a.sideline_gltf)
    else:
        compile_project(a.project, a.before_resources, a.v05_cards, a.out, a.index)
    return 0



# --------------------------------------------------------------------------------------------- small player atlas
def mesh_posmap(gltf: Path, material: str, size: tuple[int, int], mesh_index: int = 0) -> np.ndarray:
    """Rest position (cm) under every texel of one material of one mesh (read only)."""
    g = json.loads(gltf.read_text())
    buffers = [(gltf.parent / b["uri"]).read_bytes() for b in g["buffers"]]

    def read(i):
        a = g["accessors"][i]; v = g["bufferViews"][a["bufferView"]]; dt = np.dtype(_DTYPE[a["componentType"]])
        k = _COUNT[a["type"]]; s = v.get("byteStride", dt.itemsize * k)
        return np.ndarray((a["count"], k), dt, buffers[v["buffer"]], offset=v.get("byteOffset", 0) +
                          a.get("byteOffset", 0), strides=(s, dt.itemsize)).copy().astype(np.float64)
    names = [m["name"] for m in g["materials"]]
    W, H = size
    pm = np.full((H, W, 3), np.nan)
    for p in g["meshes"][mesh_index]["primitives"]:
        if names[p["material"]] != material:
            continue
        pos = read(p["attributes"]["POSITION"]); uv = read(p["attributes"]["TEXCOORD_0"]) * np.array(size, float)
        idx = read(p["indices"]).astype(np.int64).ravel()
        tris = ([idx[i:i + 3] if i % 2 == 0 else idx[[i + 1, i, i + 2]] for i in range(len(idx) - 2)]
                if p.get("mode", 4) == 5 else idx.reshape(-1, 3))
        for t in tris:
            if len(set(t.tolist())) < 3:
                continue
            q, u = pos[t], uv[t]
            x0, y0 = np.maximum(np.floor(u.min(0)).astype(int), 0)
            x1, y1 = np.minimum(np.ceil(u.max(0)).astype(int), [W - 1, H - 1])
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            m = np.array([[u[1, 0] - u[0, 0], u[2, 0] - u[0, 0]], [u[1, 1] - u[0, 1], u[2, 1] - u[0, 1]]])
            if abs(np.linalg.det(m)) < 1e-12:
                continue
            l = np.stack([xs - u[0, 0], ys - u[0, 1]], -1) @ np.linalg.inv(m).T
            w0 = 1 - l[..., 0] - l[..., 1]
            inside = (w0 >= -1e-6) & (l[..., 0] >= -1e-6) & (l[..., 1] >= -1e-6)
            if inside.any():
                val = w0[..., None] * q[0] + l[..., 0:1] * q[1] + l[..., 1:2] * q[2]
                sub = pm[y0:y1 + 1, x0:x1 + 1]
                sub[inside] = val[inside]
    return pm


def author_splayer(spec: "art.Spec", kit: dict, old_kit: dict, before: Path, body: Path, sideline: Path):
    """The sideline players' atlas (SIDELINE_player, the closest of five LODs): the yoke bands transferred in 3D
    from the jersey's own fields (the sideline torso lies within a few cm of the hi_body jersey), the 2026 pants
    stripe and, for the road set, the white socks. The atlas' baked shading is kept; outside the scope exact."""
    from scipy import ndimage
    sel = kit["selector"]
    base_u8 = np.asarray(Image.open(before / sel / "splayer.png").convert("RGBA")).copy()
    master = art.upscale(base_u8.astype(np.float32) / 255.0)
    shape = master.shape[:2]
    changed = np.zeros(shape, np.float32)
    # yoke bands
    pm = mesh_posmap(sideline, "SIDELINE_player", (shape[1], shape[0]))
    torso_box = art._box(shape, art.SPLAYER["torso"]) > 0.5
    ok = ~np.isnan(pm[..., 0]) & torso_box
    tris = gltf_triangles(body, "UNIF_jersey")
    segs = armhole_segments(tris)
    pts = pm[ok]
    d, W, above = yoke_fields(pts, segs, YOKE)
    from scipy.spatial import cKDTree
    jersey = np.concatenate([t[:, :3] for t in tris])
    near, _ = cKDTree(jersey).query(pts)
    field = {k: np.full(shape, np.nan) for k in ("d", "W", "h")}
    for k, v in (("d", d), ("W", W), ("h", above)):
        field[k][ok] = v
    red = float(YOKE["red_cm"])
    sd = 0.6                                       # about one sideline texel at 4x, cm
    def step(v):
        return np.clip(0.5 + np.nan_to_num(v, nan=-9.0) / sd, 0.0, 1.0)
    on = np.zeros(shape, bool); on[ok] = near < 4.0
    whole = step(field["d"]) * step(field["W"] - field["d"]) * step(field["h"]) * on
    outer = step(field["d"]) * step(red - field["d"]) * step(field["h"]) * on
    inner = step(field["d"] - (field["W"] - red)) * step(field["W"] - field["d"]) * step(field["h"]) * on
    t = kit["torso"]
    colours = [spec.colour("red"), spec.colour("white" if kit["selector"][2] == "H" else "jersey_navy"),
               spec.colour("red")]
    rgb = master[..., :3]
    base = spec.colour(t["base_colour"])
    luma = rgb @ art.LUMA
    ref = float(np.median(luma[ok & (whole < 0.01)])) if (ok & (whole < 0.01)).any() else float(base @ art.LUMA)
    shade = np.clip(luma / max(ref, 1e-3), 0.55, 1.25)[..., None]
    for cov, col in ((whole, colours[1]), (outer, colours[0]), (inner, colours[2])):
        a = cov[..., None]
        rgb[:] = rgb * (1 - a) + np.clip(col[None, None, :] * shade, 0, 1) * a
    changed = np.maximum(changed, whole)
    # the pants stripe (the art tool's own splayer rule): clear the band from the fabric, draw the 2026 set
    S = art.SPLAYER
    pants_box = art._box(shape, S["pants"])
    band = np.clip(art._box(shape, S["pants_stripe"]), 0, 1) * pants_box
    master[..., :3] = rgb
    master = art._inpaint(master, band, MASTER * 3)
    scale = S["pants_scale"]
    total = sum(int(n) for _, n in kit["pants"]["stripe"]) * scale
    start = S["pants_stripe_center"] - total / 2.0
    y0, y1 = S["pants"][1], S["pants"][3]
    for name, n in kit["pants"]["stripe"]:
        art.over(master, spec.colour(name), art.rect_coverage(shape, start * MASTER, y0 * MASTER,
                                                              (start + n * scale) * MASTER, y1 * MASTER))
        start += n * scale
    changed = np.maximum(changed, band)
    # socks: the road set's white
    if kit["socks"] != old_kit["socks"]:
        sock = spec.colour(kit["socks"]["colour"])
        socks = np.clip(art._box(shape, S["sock"]) + art._box(shape, S["sock_low"]), 0, 1)
        rgbv = master[..., :3]
        lum = rgbv.mean(axis=2)
        local = ndimage.gaussian_filter(lum, MASTER * 3)
        sh = np.clip(1.0 + (lum - local) * 0.8, 0.8, 1.15)[..., None]
        rgbv[:] = rgbv * (1 - socks[..., None]) + np.clip(sock[None, None, :] * sh, 0, 1) * socks[..., None]
        changed = np.maximum(changed, socks)
    scope = _scope_native(changed, grow=1)
    native = _u8(art.downscale(master))
    native[..., 3] = 255
    native[~scope] = base_u8[~scope]
    # the P8 writer re-quantizes the whole atlas (no palette reservation route): texels outside the scope can move
    # by a few levels; measured and reported by the b77 receipts (a snapped palette was tried and did not help)
    return native, master, scope



if __name__ == "__main__":
    raise SystemExit(main())
