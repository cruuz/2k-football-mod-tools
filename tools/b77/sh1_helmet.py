#!/usr/bin/env python3
"""Beta 77 sh1: side logos on the Revolution helmet (shell C, ``helmet02``), projected from the side.

Noah, 10/8, v0.6: "seahawks helmets have logo wrong way and not connected its off". Cause (proved in
``b77_session/reports/sh1_REPORT.md``): the Seahawks' side hawks were painted into ``helmet02`` with their heads toward
the FRONT of the helmet on both sides, drawn at the retail template's decal boxes (large, far forward). The real
helmet wears the standard logo with its head toward the REAR on both sides (Riddell's authentic SpeedFlex photos of the
2026 helmet, the club's 2026 game photos), its tail feathers sweeping forward, and the head's rear edge runs into the
grey wrap that crosses the back of the helmet. The art tool's ``author_helmet`` draws a logo in two texture boxes
and only knows "upright" and "turned 180 degrees"; it cannot say which way a logo faces on the shell.

This module places a logo by 3D position instead: each side island texel of ``helmet02`` has a rest position on the shell
(the Studio's head export, read only), the logo is a plane decal seen from the side (an orthographic projection along the
player's x axis, like the photographs), given by a centre (z, y), a width and a tilt in cm, and a facing ("rear" or
"front"). Both sides use the same numbers; the left side is the mirror of the right by construction.

Method (the Patriots job's, ``u1_patriots.author_helmet_back``): author on top of the shipped ``helmet02``; erase the old
side logos (every texel of their footprint, filled from the surrounding shell); paint the new decal at 4x; box-reduce to
native; every native texel outside the scope keeps its exact RGBA; alpha is kept; the coarse mips keep their stored texels
(the importer's palette lock).

Geometry (``HI_HELMET_C``: positions, texture coordinates, triangles; game cm, y up, +z forward, +x the player's left) is
read only from the user's disc; nothing game-derived is in the repository.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools")]
import nfl2k5_team_2026_art as art  # noqa: E402

MASTER = art.MASTER
RIGHT, LEFT = "right", "left"          # right: the player's right (x < 0, upper half of helmet02); left: x > 0 (lower half)
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

#: Real-helmet placement of the Seahawks side hawk (rest-pose head cm): centre (z, y), width along the logo's axis
#: (head to tail tip), tilt in degrees (the tail end, toward the front, rises), facing. From Riddell's authentic
#: SpeedFlex SEA-1 (right) and SEA-2 (left) photographs and the club's week 1 game photographs (see the sh1 report).
SEA_PLACEMENT = {"centre": [2.1, 45.6], "width": 12.0, "angle": 40.0, "facing": "rear"}


def _u1():
    name = "b77_u1_patriots_helpers"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools/b77/u1_patriots.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------------------------------------------ geometry
def posmap(geometry, size: int = 256 * MASTER) -> np.ndarray:
    """Rest position (cm) under every master texel of the shell C art. ``geometry``: the head export's JSON path (the
    ``HI_HELMET_C`` entry has ``pos``, ``uv`` and ``tris``) or the loaded dict. NaN where no triangle covers the texel."""
    if isinstance(geometry, dict):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "geometry.json"
            path.write_text(json.dumps(geometry))
            return _u1().helmet_posmap(path, size)
    return _u1().helmet_posmap(Path(geometry), size)


def side_masks(pm: np.ndarray) -> dict:
    """Texels of the player's right (x < 0) and left (x > 0) side islands."""
    ok = ~np.isnan(pm[..., 0])
    x = np.nan_to_num(pm[..., 0])
    return {RIGHT: ok & (x < -0.05), LEFT: ok & (x > 0.05)}


# ------------------------------------------------------------------------------------------------------ the old logos
def old_logo_footprint(rgb: np.ndarray, pm: np.ndarray, box, protect=(), bright: float = 0.10, chroma: float = 0.30,
                       min_part: float = 0.05, grow: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """The old side logo's footprint inside ``box`` (native-size master texels, x0 y0 x1 y1): bright or coloured texels
    (the white and grey of a hawk, its green or gold eye), the parts of them that matter, closed and filled, grown by
    ``grow`` texels; black vents and anything in ``protect`` (boxes) are left alone. Returns (footprint, shell colour)."""
    from scipy import ndimage
    ok = ~np.isnan(pm[..., 0])
    size = rgb.shape[0]
    f = size // 256
    x0, y0, x1, y1 = [int(round(v * f)) for v in box]
    reg = np.zeros(ok.shape, bool)
    reg[y0:y1, x0:x1] = True
    reg &= ok
    if not reg.any():
        return np.zeros(ok.shape, bool), np.zeros(3, np.float32)
    # the shell colour: the commonest colour in the outer ring of the box (the old logo sits inside it); the whole box
    # when the ring holds too little shell
    inner = np.zeros(ok.shape, bool)
    inner[y0 + 2 * f:y1 - 2 * f, x0 + 2 * f:x1 - 2 * f] = True
    ring = reg & ~inner
    sample = ring if ring.sum() > 200 * f * f // 4 else reg
    q = (rgb[sample] * 255 // 12).astype(int)
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    vals, cnt = np.unique(keys, return_counts=True)
    shell = rgb[sample][keys == vals[np.argmax(cnt)]].mean(0)
    luma = rgb @ LUMA
    sl = float(shell @ LUMA)
    chroma_px = (rgb.max(2) - rgb.min(2) > chroma) & (rgb[..., 1] > rgb[..., 2])
    cand = ((luma > sl + bright) | chroma_px) & reg
    for (a, b, c, d) in protect:
        cand[int(b * f):int(d * f), int(a * f):int(c * f)] = False
    cand = ndimage.binary_closing(cand, iterations=3 * f // 4 or 1)
    lab, n = ndimage.label(cand)
    if n == 0:
        return np.zeros(ok.shape, bool), shell.astype(np.float32)
    sizes = ndimage.sum(cand, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_part * sizes.max()])
    fp = ndimage.binary_fill_holes(ndimage.binary_closing(keep, iterations=3 * f // 4 or 1))
    fp = ndimage.binary_dilation(fp, iterations=grow * f // 4 or 1) & ok
    fp &= ~(luma < 0.06)
    for (a, b, c, d) in protect:
        fp[int(b * f):int(d * f), int(a * f):int(c * f)] = False
    return fp, shell.astype(np.float32)


def erase_footprint(master: np.ndarray, erase: np.ndarray, shell: np.ndarray) -> np.ndarray:
    """Fill the erased texels from the surrounding plain shell only (no weight for white, grey or black neighbours)."""
    rgb = master[..., :3]
    luma = rgb @ LUMA
    sl = float(shell @ LUMA)
    k = np.clip(luma / max(sl, 1e-3), 0.0, 2.5)
    shellness = np.exp(-(np.linalg.norm(rgb - shell[None, None, :] * k[..., None], axis=2) / 0.06) ** 2)
    shellness = shellness * (~erase) * (luma > 0.5 * sl)
    return art._inpaint_weighted(master, erase.astype(np.float32), shellness, 2.0 * MASTER)


# ------------------------------------------------------------------------------------------------------ the new logo
def prepare_mark(path_or_array, width: int = 1024) -> np.ndarray:
    """The mark cropped to its alpha box, reduced to ``width`` pixels wide (straight RGBA float)."""
    if isinstance(path_or_array, np.ndarray):
        arr = path_or_array.astype(np.float32)
        image = Image.fromarray(_u8(arr), "RGBA")
    else:
        image = Image.open(path_or_array).convert("RGBA")
    image = image.crop(image.getbbox())
    h = max(1, int(round(image.height * width / image.width)))
    pre = np.asarray(image, dtype=np.float32) / 255.0
    pre[..., :3] *= pre[..., 3:4]
    out = np.stack([np.asarray(Image.fromarray(pre[..., c]).resize((width, h), Image.LANCZOS), dtype=np.float32)
                    for c in range(4)], axis=-1)
    out = np.clip(out, 0.0, 1.0)
    a = out[..., 3:4]
    out[..., :3] = np.where(a > 1e-4, out[..., :3] / np.maximum(a, 1e-4), 0.0)
    return out


def project_mark(mark: np.ndarray, pm: np.ndarray, side_mask: np.ndarray, centre, width: float, angle: float,
                 facing: str = "rear") -> tuple[np.ndarray, np.ndarray]:
    """Straight RGB and alpha (master size) of a mark seen from the side. ``centre`` = (z, y) cm; ``width`` = the logo's
    length along its own axis in cm; ``angle`` degrees (the axis rises toward the front); ``facing`` the way the mark's
    head points ("rear" or "front") assuming the mark is drawn facing right with its head at the right end."""
    if facing not in ("rear", "front"):
        raise ValueError("facing is 'rear' or 'front'")
    z, y = pm[..., 2], pm[..., 1]
    th = math.radians(angle)
    dz, dy = z - centre[0], y - centre[1]
    a = (dz * math.cos(th) + dy * math.sin(th)) / width
    b = (-dz * math.sin(th) + dy * math.cos(th)) / width
    u = 0.5 - a if facing == "rear" else 0.5 + a
    hm = mark.shape[0] / mark.shape[1]
    v = 0.5 - b / hm
    u = np.where(side_mask, u, np.nan)
    sample = art._sample(mark, u, v)
    alpha = np.clip(sample[..., 3], 0.0, 1.0)
    rgb = np.where(alpha[..., None] > 1e-5, sample[..., :3] / np.maximum(alpha[..., None], 1e-5), 0.0)
    return np.clip(rgb, 0.0, 1.0), alpha * side_mask


def facing_of(rgb: np.ndarray, pm: np.ndarray, side_mask: np.ndarray, eye) -> dict | None:
    """Which way a logo's head points on a side: the eye colour mask ``eye`` (a boolean array) against the centroid of
    the bright logo texels, along the front-back axis. ``head_z - logo_z`` > 0: head toward the front."""
    luma = rgb @ LUMA
    ok = side_mask & ~np.isnan(pm[..., 2])
    e, logo = eye & ok, (luma > 0.55) & ok
    if not e.any() or not logo.any():
        return None
    dz = float(pm[..., 2][e].mean() - pm[..., 2][logo].mean())
    return {"head_z_minus_logo_z": round(dz, 2), "facing": "front" if dz > 0 else "rear", "eye_texels": int(e.sum())}


# ------------------------------------------------------------------------------------------------------ the back wrap
SHELL_CENTRE = np.array([0.0, 42.0, 9.0])      # a point inside the shell (hm's C) used to orient normals outward


def surface_normals(pm: np.ndarray) -> np.ndarray:
    """Outward unit normals under every texel (from the position map's finite differences; zero where undefined)."""
    p = np.nan_to_num(pm)
    n = np.cross(np.gradient(p, axis=1), np.gradient(p, axis=0))
    n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-9)
    n[((p - SHELL_CENTRE) * n).sum(2) < 0] *= -1
    n[np.isnan(pm[..., 0])] = 0
    return n


def load_wrap(png: Path, meta: Path | None = None) -> dict:
    """The digitized back wrap (``sh1_digitize_wrap``): mask cells 0 none, 1 white, 2 grey in view-plane cm."""
    meta = meta or png.with_suffix(".json")
    doc = json.loads(Path(meta).read_text(encoding="utf-8"))
    mask = np.asarray(Image.open(png).convert("L"))
    if doc.get("schema") != "nfl2k5_helmet_wrap/v1" or mask.max() > 2:
        raise ValueError("not a helmet wrap mask")
    return {"mask": mask, "camera": doc["camera"], "res": float(doc["res_cm"]), "u0": float(doc["u_range"][0]),
            "w1": float(doc["w_range"][1])}


def view_plane(pm: np.ndarray, elevation: float) -> tuple[np.ndarray, np.ndarray]:
    """(u, w) of every texel in the back camera's view plane (cm): u = -x, w = y cos(el) + z sin(el)."""
    e = math.radians(elevation)
    return -pm[..., 0], pm[..., 1] * math.cos(e) + pm[..., 2] * math.sin(e)


def sample_wrap(wrap: dict, pm: np.ndarray, region: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coverage (0..1) of the wrap's white lines and grey band at every texel (zero outside ``region``)."""
    from scipy import ndimage
    u, w = view_plane(pm, wrap["camera"]["elevation"])
    col = (np.nan_to_num(u) - wrap["u0"]) / wrap["res"] - 0.5
    row = (wrap["w1"] - np.nan_to_num(w)) / wrap["res"] - 0.5
    out = []
    for value in (1, 2):
        f = ndimage.gaussian_filter((wrap["mask"] == value).astype(np.float32), 0.8)
        c = ndimage.map_coordinates(f, [row, col], order=1, mode="constant", cval=0.0)
        out.append(np.clip((c - 0.25) / 0.5, 0.0, 1.0) * region)
    return out[0], out[1]


def old_wrap_footprint(rgb: np.ndarray, region: np.ndarray, shell: np.ndarray, bright: float = 0.12,
                       min_texels: int = 300, grow: int = 2) -> np.ndarray:
    """The old wrap: the large bright parts (white lines, grey band) inside the back-facing ``region``; the small dots
    of the crown's feather pattern are not touched."""
    from scipy import ndimage
    luma = rgb @ LUMA
    cand = (luma > float(shell @ LUMA) + bright) & region
    lab, n = ndimage.label(cand)
    if n == 0:
        return np.zeros(region.shape, bool)
    sizes = ndimage.sum(cand, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_texels * (rgb.shape[0] // 256) ** 2 // 16])
    return ndimage.binary_dilation(keep, iterations=grow) & region


# ------------------------------------------------------------------------------------------------------ author
def apply_master(master: np.ndarray, pm: np.ndarray, mark: np.ndarray, layout: dict, placement: dict | None = None,
                 shade: tuple[float, float] = (0.85, 1.10), wrap: dict | None = None,
                 wrap_colours: tuple = ((0.97, 0.97, 0.97), (0.647, 0.675, 0.686)), back_y_min: float = 43.5) -> dict:
    """Erase the old side logos (and, with ``wrap``, the old back wrap) from a 4x ``master`` (straight RGBA float, edited in
    place) and paint the projected logos and the wrap. ``layout``: {"right": {"box": [x0, y0, x1, y1], "protect": [...]},
    "left": {...}} (native texels: where each old logo lives). Returns the changed-texel masks."""
    from scipy import ndimage
    placement = placement or SEA_PLACEMENT
    if pm.shape[0] != master.shape[0]:
        raise ValueError("position map and master sizes differ")
    sides = side_masks(pm)
    erase = np.zeros(pm.shape[:2], bool)
    shells = {}
    for side in (RIGHT, LEFT):
        lay = layout[side]
        fp, shell = old_logo_footprint(master[..., :3], pm, lay["box"], [tuple(p) for p in lay.get("protect", ())])
        erase |= fp & sides[side]
        shells[side] = shell
    shell = np.mean([shells[RIGHT], shells[LEFT]], axis=0)
    normals = surface_normals(pm)
    back = (~np.isnan(pm[..., 0])) & (normals[..., 2] < -0.15) & (np.nan_to_num(pm[..., 1]) > back_y_min)
    if wrap is not None:
        erase |= old_wrap_footprint(master[..., :3], back, shell)
    master[...] = erase_footprint(master, erase, shell)
    k = np.clip((master[..., :3] @ LUMA) / max(float(shell @ LUMA), 1e-3), shade[0], shade[1])
    painted = np.zeros(pm.shape[:2], np.float32)
    projected = {side: project_mark(mark, pm, sides[side], placement["centre"], placement["width"], placement["angle"],
                                    placement.get("facing", "rear")) for side in (RIGHT, LEFT)}
    marks_alpha = np.maximum(projected[RIGHT][1], projected[LEFT][1])
    if wrap is not None:
        free = back & ~ndimage.binary_dilation(marks_alpha > 0.02, iterations=MASTER)
        white, grey = sample_wrap(wrap, pm, free.astype(np.float32))
        for cov, colour in ((grey, wrap_colours[1]), (white, wrap_colours[0])):
            a = cov[..., None]
            tone = np.clip(np.asarray(colour, np.float32)[None, None, :] * k[..., None], 0, 1)
            master[..., :3] = master[..., :3] * (1 - a) + tone * a
        painted = np.maximum(painted, np.maximum(white, grey))
    for side in (RIGHT, LEFT):
        col, alpha = projected[side]
        a = alpha[..., None]
        master[..., :3] = master[..., :3] * (1 - a) + np.clip(col * k[..., None], 0, 1) * a
        painted = np.maximum(painted, alpha)
    return {"erase": erase, "painted": painted, "shell": shell}


def author(base_u8: np.ndarray, pm: np.ndarray, mark: np.ndarray, layout: dict, placement: dict | None = None,
           **kw) -> dict:
    """The corrected ``helmet02`` on top of ``base_u8`` (native RGBA, uint8). Alpha and every texel outside the scope
    stay exactly as in ``base_u8``. Returns master, native, scope and the masks of :func:`apply_master`."""
    master = art.upscale(base_u8.astype(np.float32) / 255.0)
    r = apply_master(master, pm, mark, layout, placement, **kw)
    changed = (r["erase"] | (r["painted"] > 0)).astype(np.float32)
    scope = _u1()._scope_native(changed, grow=1)
    native = _u8(art.downscale(master))
    native[..., 3] = base_u8[..., 3]
    native[~scope] = base_u8[~scope]
    return dict(r, master=master, native=native, scope=scope, scope_texels=int(scope.sum()))


def mirror_left(master: np.ndarray, pm: np.ndarray, box, tolerance: float = 0.25) -> np.ndarray:
    """The left side takes the right side's art inside ``box`` (native texels): each left texel gets the colour of the
    right island at the same height and depth (the 3D mirror x -> -x, job k2's ``mirror_left``). A directional logo then
    faces the same way relative to the helmet on both sides. Edited in place; returns the texels written."""
    from scipy.spatial import cKDTree
    sides = side_masks(pm)
    right = np.argwhere(sides[RIGHT])
    tree = cKDTree(pm[right[:, 0], right[:, 1]][:, [1, 2]])
    f = master.shape[0] // 256
    x0, y0, x1, y1 = [int(round(v * f)) for v in box]
    region = np.zeros(pm.shape[:2], bool)
    region[y0:y1, x0:x1] = True
    region &= sides[LEFT]
    left = np.argwhere(region)
    dist, j = tree.query(pm[left[:, 0], left[:, 1]][:, [1, 2]])
    good = dist < tolerance
    src = right[j[good]]
    dst = left[good]
    master[dst[:, 0], dst[:, 1], :3] = master[src[:, 0], src[:, 1], :3]
    written = np.zeros(pm.shape[:2], bool)
    written[dst[:, 0], dst[:, 1]] = True
    return written


# ------------------------------------------------------------------------------------------------------ the kits
#: Where the old side logos sit in the shipped art, by kit (native helmet02 texels). The k2 art of the primary helmet
#: draws them large (they reach texel 143); the retail-derived alternates draw them at the retail decal boxes.
LAYOUT_PRIMARY = {"right": {"box": [28, 28, 143, 108]}, "left": {"box": [28, 148, 143, 222]}}
LAYOUT_ALT3 = {"right": {"box": [20, 50, 112, 110], "protect": [[42, 53, 56, 67]]},
               "left": {"box": [20, 150, 112, 205]}}
#: The six Seahawks helmet02 resources that carry the side logos (home and road are identical in every style). SEA 4
#: ("2026 Alternate 2") wears the primary helmet by definition (u3e: the primary navy and white kits), so it takes the
#: primary helmet's corrected art; SEA 3 (Rivalries) keeps its own toned shell and speed lines and gets only its logos
#: turned to the rear.
SEA_KITS = {
    "26H0": {"mark": "club_logo_full.png", "layout": LAYOUT_PRIMARY, "wrap": True},
    "26A0": {"mark": "club_logo_full.png", "layout": LAYOUT_PRIMARY, "wrap": True},
    "26H3": {"mark": "logo_chrome.png", "layout": LAYOUT_ALT3, "wrap": False},
    "26A3": {"mark": "logo_chrome.png", "layout": LAYOUT_ALT3, "wrap": False},
    "26H4": {"same_as": "26H0"},
    "26A4": {"same_as": "26A0"},
}
#: Alternates whose helmet was drawn by the art tool's ``decal`` route (the same image on both sides: head toward the
#: front on the right, toward the rear on the left) for a team whose real helmet mirrors its logo: ARI 7 and NE 9. The
#: left side takes the right side's art (3D mirror) inside the box (native helmet02 texels).
LEFT_BOX = [20, 132, 143, 225]
MIRROR_KITS = {sel: {"mirror_left": LEFT_BOX} for sel in ("00H7", "00A7", "16H9", "16A9")}
SCHEMA_MANIFEST = "b77/sh1/texture-repair/v1"


def find_mark(name: str, dirs) -> Path:
    for d in dirs:
        if (Path(d) / name).is_file():
            return Path(d) / name
    raise FileNotFoundError(f"mark {name} not found in {[str(d) for d in dirs]}")


def author_kits(export: Path, geometry: Path, marks: list, wrap_png: Path, out: Path, kits: dict | None = None,
                placement: dict | None = None) -> dict:
    """Author the corrected helmet02 of every kit in ``kits`` (default SEA_KITS) on top of the shipped art in ``export``
    (``uniforms/<sel>/helmet_helmet02.png``, ``resources/<sel>.IFF``, ``export.json``): writes ``out/uniforms/<sel>/
    helmet_helmet02.png`` (with the importer's palette lock and authored mips), ``out/art/<sel>/`` (the kit folder with the
    new helmet, for renders), ``out/project.json`` and ``out/author_receipt.json``."""
    import shutil
    from PIL import PngImagePlugin  # noqa: F401  (the lock metadata is built by u1's helper)
    kits = kits or dict(SEA_KITS, **MIRROR_KITS)
    u1 = _u1()
    pm = posmap(geometry)
    wrap = load_wrap(wrap_png)
    export_doc = json.loads((export / "export.json").read_text())
    sets = {row["selector"]: row for row in export_doc["sets"]}
    edits, items, done = [], [], {}
    order = sorted(kits, key=lambda k: "same_as" in kits[k])
    for sel in order:
        conf = kits[sel]
        base = np.asarray(Image.open(export / "uniforms" / sel / "helmet_helmet02.png").convert("RGBA")).copy()
        if "mirror_left" in conf:
            master = art.upscale(base.astype(np.float32) / 255.0)
            written = mirror_left(master, pm, conf["mirror_left"])
            scope = _u1()._scope_native(written.astype(np.float32), grow=1)
            native = _u8(art.downscale(master))
            native[..., 3] = base[..., 3]
            native[~scope] = base[~scope]
            info = {"mirror_left": conf["mirror_left"]}
        elif "same_as" in conf:
            src = done[conf["same_as"]]["native"]
            native = src.copy()
            native[..., 3] = base[..., 3]
            scope = (native[..., :3] != base[..., :3]).any(axis=2)
            master = done[conf["same_as"]]["master"].copy()
            master[..., 3] = np.repeat(np.repeat(base[..., 3], MASTER, axis=0), MASTER, axis=1) / 255.0
            info = {"same_as": conf["same_as"]}
        else:
            mark = prepare_mark(find_mark(conf["mark"], marks))
            r = author(base, pm, mark, conf["layout"], placement, wrap=wrap if conf["wrap"] else None)
            native, scope, master = r["native"], r["scope"], r["master"]
            info = {"mark": conf["mark"], "wrap": conf["wrap"]}
        done[sel] = {"native": native, "master": master}
        mpath = out / "master4x" / sel / "helmet_helmet02.png"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(_u8(master), "RGBA").save(mpath, optimize=False, compress_level=9)
        meta, lock = u1.helmet_mip_lock(export / "resources" / f"{sel}.IFF", base, native, scope)
        png = out / "uniforms" / sel / "helmet_helmet02.png"
        digest = u1._save_png(native, png, meta)
        art_dir = out / "art" / sel
        if art_dir.exists():
            shutil.rmtree(art_dir)
        shutil.copytree(export / "uniforms" / sel, art_dir)
        shutil.copyfile(png, art_dir / "helmet_helmet02.png")
        row = sets[sel]
        edits.append({"kind": "live_helmet", "asset_code": sel[:2], "side": sel[2], "variant": int(sel[3:]),
                      "family": "helmet02", "png": str(png)})
        items.append(dict(selector=sel, name="helmet_helmet02", sha256=digest, base_sha256=sha(base.tobytes()),
                          scope_texels=int(scope.sum()), outer_index=row["outer_index"], **info, **lock))
    project = {"schema": "nfl2k5_visual_mod_project/v1", "purpose": "b77 sh1 Seahawks helmet side logos", "edits": edits}
    out.mkdir(parents=True, exist_ok=True)
    (out / "project.json").write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (out / "author_receipt.json").write_text(json.dumps({"schema": "b77/sh1/author-receipt/v1", "placement": placement or SEA_PLACEMENT,
                                                          "items": items}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return project


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("author", help="corrected helmet02 PNGs (with palette lock) and the Studio project")
    s.add_argument("--export", type=Path, required=True, help="kit export of the baseline (uniforms/, resources/, export.json)")
    s.add_argument("--geometry", type=Path, required=True, help="head export JSON with HI_HELMET_C")
    s.add_argument("--marks", type=Path, nargs="+", required=True, help="folders holding club_logo_full.png / logo_chrome.png")
    s.add_argument("--wrap", type=Path, default=ROOT / "data/nfl2k5_helmet_wraps/sea_wrap.png")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("compile", help="the Studio's own importers on the project: exact native spans and the manifest")
    s.add_argument("--project", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--index", type=Path, required=True, help="retail vc_53450030/0")
    s.add_argument("--card-edits", type=Path, help="card_edits.json of tools/b77/sh1_cards.py render (Team Select cards)")
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "author":
        project = author_kits(a.export, a.geometry, a.marks, a.wrap, a.out)
        print(json.dumps({"edits": len(project["edits"]), "out": str(a.out)}))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import u2a_kits
        project_path = a.project
        if a.card_edits:
            doc = json.loads(a.project.read_text())
            doc["edits"] = [e for e in doc["edits"] if e["kind"] != "team_select"] + json.loads(a.card_edits.read_text())
            a.out.mkdir(parents=True, exist_ok=True)
            project_path = a.out / "project_with_cards.json"
            project_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        manifest = u2a_kits.compile_all(project_path, a.export, a.index, a.out, SCHEMA_MANIFEST)
        print(json.dumps({"resources": {k: len(v) for k, v in manifest["resources"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
