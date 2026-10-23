#!/usr/bin/env python3
"""cf1 (b778): a scanned face for a 2026 head coach, from 2-4 private reference photos to the authored ``head.png`` and
the head shape in ``geometry.json`` of ``data/nfl2k5_modern_coaches/<club>/`` (the files the Studio already ships and
applies; ``mod_editor/core/nfl2k5_modern_coaches.py`` is unchanged by this tool).

Noah, 10/22: "Build every single coach a proper face. All 32 coaches should have their face scanned." The earlier
heads were a photo warped in texture space (co2), then repainted per texel with only co2's fine detail kept (cm1,
cm2): a continuous tone, but a generic face. This tool works in 3D on the model the coach wears:

1. ``landmarks``: 478 MediaPipe face-mesh points on a front render of the model's own head (its retail texture) are
   lifted onto the mesh through the render's depth buffer, so every point is a 3D point on the 2004 head; the same 478
   points are found on each reference photo.
2. ``shape``: the photo's head pose is solved from those pairs (perspective n-point); the part of the photo points the
   pose cannot explain is the man's own proportions (face width, jaw and chin, eye spacing and height, nose length and
   width, brow). That remainder, made left-right symmetric and limited to ``shape_max`` cm, becomes a smooth
   displacement of the head's face vertices (eyes, teeth and the low-detail head move with it; the ears, scalp, neck and
   the headset band do not). Written as integer vertex edits (``geometry.json``), merged with any body edit already
   there.
3. ``project``: every texel of the head texture is a point on the reshaped mesh; each photo is projected onto it (its
   solved camera, a depth test, a weight that falls off as the surface turns away from the camera, and a thin-plate
   correction that puts the photo's eye corners, lids, nostrils and lip lines on the mesh's), the side light of the
   photo taken out (its broad luminance made left-right symmetric), the open mouth of a smiling photo closed (the lips
   painted between the lip lines), and the photos merged by weight.
4. ``compose``: the projected face is laid over a painted base head (cm1's painter: one skin tone, scalp hair at his
   hairline in his colour, or a shaved head; facial hair shapes; no co2 detail) whose skin and hair colours are measured
   from the projected photo; near the face the base takes the photo's local tone (smoothed over the surface in 3D), and
   the blend weight is a function of the 3D point, so neither a UV seam nor the edge of the photo shows. The photo
   never paints the backdrop, his collar, or the temple hair and shadow beside a face wider than the 2004 head. The eye,
   teeth and tongue atlas keeps the retail pixels (the iris recoloured to his eye colour).
5. ``qc``: a sheet per coach (reference crop, flat-lit render of the result in front, three-quarter and side, the
   texture) for strict review; the Blender renders and the emulator close-ups come after (see the cf1 report).

What ships is the texture this tool writes (his photo resampled onto the 2004 head, relit and blended into painted
skin and hair, the same kind of photo-derived face co2 shipped; Noah 10/12: real coach faces ship publicly) and the
integer geometry; the reference photos themselves stay in the private ``--refs`` folder (never in the repository or a
pack). mediapipe runs in a separate Python (``--mp-python``) with the
``face_landmarker.task`` model; nothing here runs in a Build.

  python3 tools/b77/cf1_face_scan.py build --retail RETAIL.iso --refs REFS.json --work WORK \
      --mp-python VENV/bin/python --mp-model face_landmarker.task --teams JAX [--write]

REFS.json: {"JAX": {"photos": [{"path": "headshot.jpg", "role": "texture", "mouth": "close"},
{"path": "sideline.jpg", "role": "check"}]}}: "texture" photos are projected (the first one also fits the shape),
"check" photos are for the reviewer only; the
recipe of each coach (``cf1_recipes/<club>.json``) names his hair, facial hair, eye colour and the base paint settings.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as mm  # noqa: E402
import cm1_coach_models as cm1  # noqa: E402

HEAD = "coachHeadGrp1"
CO2 = ROOT / "tools" / "b77" / "co2_coach_faces.py"     # its landmarks-worker runs in the mediapipe Python

# MediaPipe face-mesh index groups
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176,
             149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
OUTER_LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
INNER_LIPS = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]
LEFT_BROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
RIGHT_BROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
NOSE = [1, 2, 4, 5, 6, 19, 94, 97, 98, 326, 327, 168, 195, 197, 48, 278, 64, 294, 129, 358, 220, 440]
CHEEKS = [50, 280, 101, 330, 118, 347, 36, 266, 205, 425, 123, 352, 147, 376]
FOREHEAD = [151, 9, 108, 337, 69, 299, 104, 333, 67, 297]
# the shape fit uses the rigid frame of the face: not the mouth or the lower jaw line of an open or smiling mouth
SHAPE_POINTS = sorted(set(FACE_OVAL) | set(LEFT_EYE) | set(RIGHT_EYE) | set(LEFT_BROW) | set(RIGHT_BROW) | set(NOSE)
                      | set(CHEEKS) | set(FOREHEAD) | {61, 291})
POSE_POINTS = sorted(set(LEFT_EYE) | set(RIGHT_EYE) | set(NOSE) | set(FOREHEAD) | {10, 151, 9, 234, 454, 127, 356})

# --- recipes ------------------------------------------------------------------------------------------------------
# One JSON file per coach in tools/b77/cf1_recipes/<club>.json (so scans of different clubs never touch one file):
#   who         his name
#   eyes        iris colour [r, g, b] (the retail eye atlas recoloured; omit to keep it)
#   mouth       "close": paint the lips between the lip lines (a smiling or open-mouthed photo); "photo": keep it
#   hair        cm1 hairline (front, recede, side, back, sideburn, edge; heights in head space, cm) or omit when bald
#   hair_colour [r, g, b] by eye from the photos (else measured above his forehead)
#   facial      cm1 facial-hair layers (kind "stubble" or a full beard; parts; density; colour defaults to the hair)
#   skin        [r, g, b] to override the measured skin of the base head
#   shape_max   largest face move in cm (default 0.8); "shape": false keeps the model's face shape
#   photo       0..1 strength of the projected photo over the base (default 1)
#   symmetry    0..1 how much of the photo's side light is evened out (default 0.9)
#   notes       what was judged and why
RECIPE_DIR = Path(__file__).resolve().parent / "cf1_recipes"


def recipe_for(team: str) -> dict:
    path = RECIPE_DIR / f"{team}.json"
    if not path.is_file():
        raise SystemExit(f"{team}: no recipe {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# --- model --------------------------------------------------------------------------------------------------------

def load_model(retail: str, team: str):
    """(Scene, head dict with the positions any shipped geometry.json already gives the head, retail head RGBA)."""
    row = next(r for r in mc.pins()["teams"] if r["team"] == team)
    scene = cm1.Scene(cm1.read_archive(retail, row["archive"]), row["archive"])
    head = dict(scene.shapes[HEAD])
    head["P"] = shipped_positions(scene, team)[HEAD]
    rows = {}
    for tex in scene.rec["embedded_textures"]:
        for material in tex.get("mapped_material_names") or ():
            rows.setdefault(material, tex)
    rgba, _pal = mm.read_p8(bytes(scene.decoded), int(scene.rec["system_bytes"]), rows["headShader1"])
    return scene, head, np.asarray(rgba, np.uint8), row


BASE_REF = "54a30bc7b"      # the geometry a scan starts from (before any cf1 face move): b778 round-1 integration


def base_geometry(team: str, ref: str | None = None) -> dict | None:
    """The club's ``geometry.json`` as it was at ``ref`` (git), before this tool moved the face; None if it had none.
    A scan always starts from there, so running it again replaces its own earlier face move instead of adding to it."""
    rel = f"data/nfl2k5_modern_coaches/{team}/{mc.GEOMETRY_FILE}"
    run = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref or BASE_REF}:{rel}"], capture_output=True)
    if run.returncode != 0:
        return None
    return json.loads(run.stdout.decode("utf-8"))


def shipped_positions(scene, team: str, ref: str | None = None) -> dict:
    """Per geometry shape, the positions the base ``geometry.json`` gives it (the retail ones where it has none)."""
    from mod_editor.core import nfl2k5_models as models
    out = {name: scene.shapes[name]["P"].copy() for name in mc.GEOMETRY_SHAPES}
    doc = base_geometry(team, ref)
    if doc:
        for item in doc["shapes"]:
            lanes = scene.shapes[item["name"]]["lanes"]
            off, scale = np.asarray(lanes.offset), lanes.scale
            for v, *q in item["positions"]:
                out[item["name"]][v] = [models.normshort(int(q[a])) * scale + off[a] for a in range(3)]
    return out


def write_geometry(scene, team: str, head_P: np.ndarray) -> dict:
    """``geometry.json`` with the scanned head shape: the head entry regenerated (cm1's integer writer, normals carried
    through the move from retail), and the low-detail head and the full-detail body parts near the face (headset
    microphone, glasses) following by the displacement field: those two entries keep every row an earlier edit wrote
    (a leaner body, Quinn's bald head band) and only gain or update the positions the face move reaches."""
    from mod_editor.core import nfl2k5_models as models
    have = shipped_positions(scene, team)
    gpath = mc.geometry_path(team)
    base = base_geometry(team)
    old = {s["name"]: s for s in base["shapes"]} if base else {}
    Dh = head_P - have[HEAD]
    offset = scene.joints["coachBodyGrp1:thorax"] - scene.joints["coachHeadGrp1:thorax"]
    Ph = have[HEAD] + offset
    doc = cm1.geometry_document(scene, {HEAD: head_P})
    shapes = {s["name"]: s for s in doc["shapes"]}
    for name, radius, sigma in (("coachBodyGrp1", 1.2, 0.5), ("coachLodGrp1", 3.0, 1.2)):
        move = cm1.carry_field(Ph, Dh, have[name], radius, sigma)
        entry = old.get(name)
        moved = np.nonzero(np.linalg.norm(move, axis=1) > 1e-3)[0]
        if len(moved):
            lanes = scene.shapes[name]["lanes"]
            off, scale = np.asarray(lanes.offset), lanes.scale
            rows = {r[0]: r for r in (entry["positions"] if entry else [])}
            Q = have[name] + move
            for v in moved:
                rows[int(v)] = [int(v)] + [models.encode_normshort(max(-1.0, min(1.0, (Q[v][a] - off[a]) / scale)))
                                           for a in range(3)]
            entry = dict(entry) if entry else dict(name=name, vertex_count=int(lanes.vertex_count),
                                                   lanes_sha256=scene.shapes[name]["digest"], positions=[], normals=[])
            entry["positions"] = [rows[k] for k in sorted(rows)]
        if entry:
            shapes[name] = entry
    doc["shapes"] = [shapes[n] for n in mc.GEOMETRY_SHAPES if n in shapes and (shapes[n]["positions"]
                                                                              or shapes[n]["normals"])]
    text = json.dumps(doc, separators=(", ", ": ")) + "\n"
    gpath.write_text(text, encoding="utf-8", newline="\n")
    return {s["name"]: (len(s["positions"]), len(s["normals"])) for s in doc["shapes"]}


def skin_tris(head: dict) -> np.ndarray:
    T = cm1.tris_of(head, "headShader1")
    main = cm1.skin_component(head)
    return T, np.array([t[0] in main for t in T])


# --- a small rasteriser --------------------------------------------------------------------------------------------

def rasterise(V2: np.ndarray, depth: np.ndarray, T: np.ndarray, W: int, H: int):
    """Per pixel (W x H, pixel centres at +0.5) of screen points ``V2`` (n x 2) with view depth ``depth`` (smaller is
    nearer): the nearest triangle (-1 where none) and its barycentrics."""
    zb = np.full((H, W), np.inf)
    tri = -np.ones((H, W), int)
    bary = np.zeros((H, W, 3))
    for ti, t in enumerate(T):
        a, b, c = V2[t[0]], V2[t[1]], V2[t[2]]
        x0, x1 = int(np.floor(min(a[0], b[0], c[0]))), int(np.ceil(max(a[0], b[0], c[0])))
        y0, y1 = int(np.floor(min(a[1], b[1], c[1]))), int(np.ceil(max(a[1], b[1], c[1])))
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
        det = np.linalg.det(m)
        if abs(det) < 1e-12:
            continue
        inv = np.linalg.inv(m)
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        dx, dy = xs - a[0], ys - a[1]
        s = inv[0, 0] * dx + inv[0, 1] * dy
        r = inv[1, 0] * dx + inv[1, 1] * dy
        inside = (s >= -1e-6) & (r >= -1e-6) & (s + r <= 1 + 1e-6)
        if not inside.any():
            continue
        z = depth[t[0]] + s * (depth[t[1]] - depth[t[0]]) + r * (depth[t[2]] - depth[t[0]])
        iy, ix = (ys[inside] - 0.5).astype(int), (xs[inside] - 0.5).astype(int)
        zz = z[inside]
        near = zz < zb[iy, ix]
        iy, ix, zz = iy[near], ix[near], zz[near]
        zb[iy, ix] = zz
        tri[iy, ix] = ti
        bary[iy, ix] = np.stack([1 - s[inside][near] - r[inside][near], s[inside][near], r[inside][near]], -1)
    return tri, bary, zb


def sample_uv(tex: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Bilinear lookup of ``tex`` (H x W x C float) at texture coordinates ``uv`` (... x 2, wrapping)."""
    H, W = tex.shape[:2]
    x = (uv[..., 0] % 1.0) * W - 0.5
    y = (uv[..., 1] % 1.0) * H - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    x0w, x1w, y0w, y1w = x0 % W, (x0 + 1) % W, y0 % H, (y0 + 1) % H
    return ((1 - fx) * (1 - fy) * tex[y0w, x0w] + fx * (1 - fy) * tex[y0w, x1w]
            + (1 - fx) * fy * tex[y1w, x0w] + fx * fy * tex[y1w, x1w])


def front_view(P: np.ndarray, size: int = 768, margin: float = 1.6):
    """An orthographic front camera on the face (x right, y up, looking down -z): screen points, depth, scale."""
    face = P[P[:, 2] > np.percentile(P[:, 2], 40)]
    lo, hi = face[:, :2].min(0), face[:, :2].max(0)
    centre = (lo + hi) / 2
    span = (hi - lo).max() * margin
    s = size / span
    V2 = np.c_[(P[:, 0] - centre[0]) * s + size / 2, (centre[1] - P[:, 1]) * s + size / 2]
    return V2, -P[:, 2], dict(scale=s, centre=centre.tolist(), size=size)


def render_textured(head: dict, tex_rgba: np.ndarray, P=None, size=768, view="front", bg=(128, 128, 128),
                    light: float = 0.0, margin: float = 1.6):
    """A flat (or lightly lit) render of the head mesh with ``tex_rgba``: image, triangle map, barycentrics, camera.
    ``view``: front, or an angle in degrees about the vertical axis (the head turned to its right for positive)."""
    P = head["P"] if P is None else P
    T = head["T"]
    if view != "front":
        a = np.radians(float(view))
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        c = P.mean(0)
        P = (P - c) @ R.T + c
    V2, depth, cam = front_view(P, size, margin)
    tri, bary, _zb = rasterise(V2, depth, T, size, size)
    U = head["U"]
    hit = tri >= 0
    uv = np.zeros((size, size, 2))
    tt = T[np.maximum(tri, 0)]
    uv[hit] = (bary[hit][:, 0:1] * U[tt[hit][:, 0]] + bary[hit][:, 1:2] * U[tt[hit][:, 1]]
               + bary[hit][:, 2:3] * U[tt[hit][:, 2]])
    img = np.zeros((size, size, 3)) + np.array(bg, float)
    col = sample_uv(np.asarray(tex_rgba[..., :3], float), uv[hit])
    if light:
        N = cm1.vertex_normals(P, T)
        n = (bary[hit][:, 0:1] * N[tt[hit][:, 0]] + bary[hit][:, 1:2] * N[tt[hit][:, 1]]
             + bary[hit][:, 2:3] * N[tt[hit][:, 2]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        ld = np.array([-0.35, 0.45, 0.82]); ld /= np.linalg.norm(ld)
        shade = (1 - light) + light * np.clip(n @ ld, 0, 1)
        col = col * shade[:, None]
    img[hit] = col
    return np.clip(img, 0, 255).astype(np.uint8), tri, bary, cam, P


# --- landmarks ----------------------------------------------------------------------------------------------------

def detect(paths, mp_python: str, mp_model: str, work: Path) -> list:
    """478 MediaPipe points (pixels) per image, cached in WORK/landmarks.json."""
    cache = work / "landmarks.json"
    db = json.loads(cache.read_text()) if cache.is_file() else {}
    todo = [str(p) for p in paths if str(p) not in db]
    if todo:
        tmp = work / "landmarks_tmp.json"
        subprocess.run([mp_python, str(CO2), "landmarks-worker", "--model", mp_model, str(tmp)] + todo,
                       capture_output=True, check=True, cwd=str(work))
        db.update(json.loads(tmp.read_text()))
        cache.write_text(json.dumps(db))
    return [np.array(db[str(p)]) if db.get(str(p)) else None for p in paths]


def mesh_landmarks(head: dict, tex_rgba, work: Path, tag: str, mp_python: str, mp_model: str, P=None):
    """The 478 points on the head mesh (3D, head space): detected on a front render, lifted through its triangles."""
    img, tri, bary, cam, Pv = render_textured(head, tex_rgba, P=P, size=768)
    path = work / f"mesh_front_{tag}.png"
    Image.fromarray(img).save(path)
    (lm,) = detect([path], mp_python, mp_model, work)
    if lm is None:
        raise SystemExit(f"{tag}: MediaPipe found no face on the model's front render")
    P = head["P"] if P is None else P
    T = head["T"]
    out = np.zeros((len(lm), 3))
    ok = np.zeros(len(lm), bool)
    for i, (x, y) in enumerate(lm):
        ix, iy = int(np.clip(x, 0, 767)), int(np.clip(y, 0, 767))
        # nearest covered pixel (contour points can sit just off the silhouette)
        if tri[iy, ix] < 0:
            ys, xs = np.nonzero(tri >= 0)
            k = np.argmin((xs - ix) ** 2 + (ys - iy) ** 2)
            ix, iy = xs[k], ys[k]
        else:
            ok[i] = True
        t = T[tri[iy, ix]]
        b = bary[iy, ix]
        out[i] = b[0] * P[t[0]] + b[1] * P[t[1]] + b[2] * P[t[2]]
    return out, ok, lm


# --- pose and shape -------------------------------------------------------------------------------------------------

def mirror_pairs(L3: np.ndarray) -> np.ndarray:
    """For each mesh landmark, the index of its mirror image (x -> -x) among the landmarks."""
    M = L3 * np.array([-1, 1, 1])
    d = ((L3[None, :, :] - M[:, None, :]) ** 2).sum(-1)
    return np.argmin(d, axis=1)


def solve_pose(L3, L2, idx, image_size, f_scale=3.0):
    """Perspective camera (rvec, tvec, K) mapping head points L3[idx] to photo pixels L2[idx] (OpenCV axes: the head's
    y up and z forward become the camera's -y and -z)."""
    import cv2
    w, h = image_size
    f = f_scale * max(w, h)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], float)
    flip = np.diag([1.0, -1.0, -1.0])
    obj = (L3[idx] @ flip.T).astype(np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, L2[idx].astype(np.float64), K, None, flags=cv2.SOLVEPNP_EPNP)
    ok, rvec, tvec = cv2.solvePnP(obj, L2[idx].astype(np.float64), K, None, rvec, tvec, True,
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    return dict(rvec=rvec, tvec=tvec, K=K, flip=flip)


def project(pose, X):
    """Head points X (n x 3) -> photo pixels (n x 2) and camera depth (n,)."""
    import cv2
    R, _ = cv2.Rodrigues(pose["rvec"])
    Xc = (X @ pose["flip"].T) @ R.T + pose["tvec"].ravel()
    uv = Xc[:, :2] / Xc[:, 2:3]
    uv = uv * [pose["K"][0, 0], pose["K"][1, 1]] + [pose["K"][0, 2], pose["K"][1, 2]]
    return uv, Xc[:, 2]


def pose_axes(pose):
    """The camera's x and y axes and its viewing direction, in head space."""
    import cv2
    R, _ = cv2.Rodrigues(pose["rvec"])
    A = R @ pose["flip"]                       # head -> camera
    return A[0], -A[1], A[2]                   # image right, image up (head space), viewing direction (into the scene)


def yaw_of(pose) -> float:
    _x, _y, d = pose_axes(pose)
    return float(np.degrees(np.arctan2(-d[0], -d[2])))


def shape_offsets(L3, L2, pose, pairs, idx):
    """Per landmark, the move (head space, cm, in the camera's image plane) that would put the mesh point on the photo
    point, made left-right symmetric (the mean of each point and its mirror)."""
    uv, z = project(pose, L3)
    f = pose["K"][0, 0]
    ax, ay, _d = pose_axes(pose)
    res = L2 - uv                                           # pixels
    cm = res * (z / f)[:, None]                              # pixel -> cm at that depth
    D = cm[:, 0:1] * ax[None, :] + (-cm[:, 1:2]) * ay[None, :]
    S = 0.5 * (D + D[pairs] * np.array([-1, 1, 1]))
    out = np.zeros_like(S)
    out[idx] = S[idx]
    return out


def face_weight(P: np.ndarray, lm: dict) -> np.ndarray:
    """0..1 how much of a face move a head vertex takes: the face in front of the ears, below the hairline, above the
    neck; nothing on the scalp, ears, neck or the back of the head."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    w = cm1.smoothstep(lm["ear_front"] + 0.5, lm["ear_front"] + 3.5, z)
    w = w * (1 - cm1.smoothstep(lm["brow"] + 2.5, lm["brow"] + 5.0, y))
    w = w * cm1.smoothstep(lm["chin"] - 4.5, lm["chin"] - 1.5, y)
    w = w * (1 - cm1.smoothstep(6.0, 8.0, np.abs(x)))
    return w


def shape_field(P, L3, D, idx, weight, sigma=1.6, cap=0.9):
    """A smooth displacement of every vertex from the landmark moves D[idx] (Gaussian-weighted, normalised), limited
    to ``cap`` cm and scaled by ``weight``; the depth (z) part is kept small (photos are 2D)."""
    src, disp = L3[idx], D[idx]
    d2 = ((P[:, None, :] - src[None, :, :]) ** 2).sum(-1)
    k = np.exp(-d2 / (2 * sigma * sigma))
    near = k.sum(1)
    move = (k @ disp) / np.maximum(near, 1e-9)[:, None]
    move = move * np.clip(near / 1.5, 0, 1)[:, None]        # fades out away from the landmarks
    move[:, 2] *= 0.3
    n = np.linalg.norm(move, axis=1, keepdims=True)
    move = move * np.minimum(1.0, cap / np.maximum(n, 1e-9))
    return move * weight[:, None]


# --- projection of a photo onto the texture -------------------------------------------------------------------------

def texel_field(head: dict, P: np.ndarray, W: int, H: int):
    """Per texel (W x H): its 3D point on the reshaped head, its normal, skin mask and coverage (cm1's raster)."""
    T, is_skin = skin_tris(head)
    pos, tri, alt = cm1.raster(head["U"], P, T, W, H)
    N = cm1.vertex_normals(P, T)
    cov = tri >= 0
    # the normal at the texel, interpolated from its triangle's vertex normals (a per-triangle normal makes every
    # weight that depends on it a patchwork of triangles)
    tt = T[np.maximum(tri, 0)]
    a, b, c = P[tt[..., 0]], P[tt[..., 1]], P[tt[..., 2]]
    v0, v1, v2 = b - a, c - a, pos - a
    d00, d01, d11 = (v0 * v0).sum(-1), (v0 * v1).sum(-1), (v1 * v1).sum(-1)
    d20, d21 = (v2 * v0).sum(-1), (v2 * v1).sum(-1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-12, 1.0, d00 * d11 - d01 * d01)
    bv = np.clip((d11 * d20 - d01 * d21) / den, 0, 1)
    bw = np.clip((d00 * d21 - d01 * d20) / den, 0, 1)
    bu = np.clip(1 - bv - bw, 0, 1)
    tn = bu[..., None] * N[tt[..., 0]] + bv[..., None] * N[tt[..., 1]] + bw[..., None] * N[tt[..., 2]]
    tn /= np.maximum(np.linalg.norm(tn, axis=-1, keepdims=True), 1e-9)
    skin = cov & is_skin[np.maximum(tri, 0)]
    return pos, tn, cov, skin, alt, tri, T


def photo_face_mask(shape, L2, grow=0.0, up=0.4, photo=None, shrink=0.05):
    """0..1 where the photo shows his head (face oval grown by ``grow`` of the face height, the hairline band above
    it ``up``), feathered; nothing below the jaw (his collar and shirt) or beside the head (the backdrop)."""
    import cv2
    H, W = shape
    face_h = np.linalg.norm(L2[10] - L2[152])
    oval = L2[FACE_OVAL].copy()
    c = oval.mean(0)
    top, chin = L2[10], L2[152]
    upv = (top - chin) / np.linalg.norm(top - chin)
    # the lower half of the oval pulled in a little: the jaw line of a photo is where his face meets the collar, the
    # backdrop or the shadow beside it
    lower = ((oval - c) @ upv) < 0
    grown = np.where(lower[:, None], c + (oval - c) * (1 - shrink), c + (oval - c) * (1 + grow))
    # the upper half of the oval also reaches up over the hairline
    above = ((oval - c) @ upv) > 0
    lift = np.clip(((oval - c) @ upv) / (0.5 * face_h), 0, 1)[:, None] * up * face_h * upv[None, :]
    grown = np.where(above[:, None], grown + lift, grown)
    m = poly_mask((H, W), grown).astype(np.float32)
    k = max(3, int(0.03 * face_h) | 1)
    m = cv2.GaussianBlur(m, (0, 0), k / 2.0)
    if photo is not None:
        m = m * (1.0 - background_like(photo, L2))
        m = m * side_skin_gate(photo, L2)
    return m


def side_skin_gate(photo: np.ndarray, L2: np.ndarray) -> np.ndarray:
    """1 everywhere except the sides of the face between the brows and the mouth corners (temples, outer cheeks),
    where it is how much the pixel looks like his skin: a 2004 head is often narrower than the man, and there its
    texels reach his temple hair, ears or the shadow beside his face, which must not paint the cheek."""
    import cv2
    H, W = photo.shape[:2]
    lab = to_lab(photo)
    face_w = np.linalg.norm(L2[234] - L2[454])
    face_h = np.linalg.norm(L2[10] - L2[152])
    skin_m = disc_mask((H, W), L2[[50, 280, 101, 330, 151]], 0.045 * face_h)
    sk = np.median(lab[skin_m], axis=0)
    d = np.hypot(np.hypot(lab[..., 1] - sk[1], lab[..., 2] - sk[2]), 0.6 * (lab[..., 0] - sk[0]))
    skin_like = 1 - cm1.smoothstep(10.0, 22.0, d)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    mid = (L2[168] + L2[1]) / 2
    across = (L2[454] - L2[234]) / max(face_w, 1e-6)
    side = np.abs((xx - mid[0]) * across[0] + (yy - mid[1]) * across[1]) / face_w
    brow_y = (L2[105, 1] + L2[334, 1]) / 2
    mouth_y = (L2[61, 1] + L2[291, 1]) / 2
    band = (cm1.smoothstep(0.39, 0.46, side) * cm1.smoothstep(brow_y - 0.05 * face_h, brow_y + 0.03 * face_h, yy)
            * (1 - cm1.smoothstep(mouth_y - 0.03 * face_h, mouth_y + 0.05 * face_h, yy)))
    gate = 1 - band * (1 - skin_like)
    return cv2.GaussianBlur(gate.astype(np.float32), (0, 0), max(1.0, 0.01 * face_h))


def background_like(photo: np.ndarray, L2: np.ndarray) -> np.ndarray:
    """0..1 how much each photo pixel looks like the studio backdrop (the median colour of the photo's top corners and
    its edges at eye level, in Lab); his face itself is never counted (the face oval is cleared)."""
    import cv2
    H, W = photo.shape[:2]
    b = max(4, int(0.04 * min(H, W)))
    eye_y = int(np.clip((L2[33, 1] + L2[263, 1]) / 2, b, H - b))
    patches = [photo[:b, :b], photo[:b, -b:], photo[eye_y - b:eye_y + b, :b], photo[eye_y - b:eye_y + b, -b:]]
    lab = to_lab(photo)
    samples = np.concatenate([to_lab(p).reshape(-1, 3) for p in patches])
    bg = np.median(samples, axis=0)
    spread = float(np.median(np.linalg.norm(samples - bg, axis=1)))
    d = np.linalg.norm(lab - bg, axis=-1)
    like = 1 - cm1.smoothstep(6 + 2 * spread, 16 + 2 * spread, d)
    face = poly_mask((H, W), L2[FACE_OVAL]).astype(np.float32)
    face = cv2.erode(face, np.ones((5, 5), np.uint8))
    like = like * (1 - face)
    return cv2.GaussianBlur(like.astype(np.float32), (0, 0), 1.5)


def project_photo(photo: np.ndarray, pose, head, P, L3, L2, pos, tn, skin, idx_fix):
    """The photo's colour at every texel and its weight (0 where hidden, turned away or off his head)."""
    import cv2
    from scipy.interpolate import RBFInterpolator
    H, W = pos.shape[:2]
    h, w = photo.shape[:2]
    # visibility: depth buffer of the reshaped head from the photo camera, at a working resolution
    scale = 900.0 / max(w, h)
    uvv, zv = project(pose, P)
    T = head["T"]
    tri, _bary, zb = rasterise(uvv * scale, zv, T, int(w * scale) + 1, int(h * scale) + 1)
    pts = pos.reshape(-1, 3)
    uv, z = project(pose, pts)
    # thin-plate correction: the photo's feature points where the mesh's project, offsets applied to every texel
    luv, _lz = project(pose, L3)
    rbf = RBFInterpolator(luv[idx_fix], (L2 - luv)[idx_fix], kernel="thin_plate_spline", smoothing=5.0, degree=1)
    corr = rbf(uv)
    # (outside the landmarks the spline continues smoothly toward its affine part; cutting it off there folds the
    # photo back over itself where a wide face meets a narrow 2004 head)
    uvc = uv + corr
    sx = np.clip((uv[:, 0] * scale).astype(int), 0, zb.shape[1] - 1)
    sy = np.clip((uv[:, 1] * scale).astype(int), 0, zb.shape[0] - 1)
    vis = z <= zb[sy, sx] + 0.35
    _ax, _ay, d = pose_axes(pose)
    facing = np.clip(-(tn.reshape(-1, 3) @ d), 0, 1)
    wgt = vis * cm1.smoothstep(0.25, 0.75, facing) * skin.reshape(-1)
    inside = (uvc[:, 0] > 1) & (uvc[:, 1] > 1) & (uvc[:, 0] < w - 2) & (uvc[:, 1] < h - 2)
    wgt = wgt * inside
    fm = photo_face_mask(photo.shape[:2], L2, photo=photo)
    wgt = wgt * cv2.remap(fm, uvc[:, 0].astype(np.float32).reshape(H, W), uvc[:, 1].astype(np.float32).reshape(H, W),
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).ravel()
    col = cv2.remap(photo.astype(np.float32), uvc[:, 0].astype(np.float32).reshape(H, W),
                    uvc[:, 1].astype(np.float32).reshape(H, W), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return col.astype(np.float64), wgt.reshape(H, W), uvc.reshape(H, W, 2)


def mirror_index(pos: np.ndarray, skin: np.ndarray):
    """For each texel, the texel at its mirror point (x -> -x) on the head (nearest skin texel in 3D)."""
    from scipy.spatial import cKDTree
    H, W = skin.shape
    ys, xs = np.nonzero(skin)
    tree = cKDTree(pos[ys, xs])
    q = pos.reshape(-1, 3) * np.array([-1, 1, 1])
    d, k = tree.query(q)
    mi = np.stack([ys[k], xs[k]], -1).reshape(H, W, 2)
    return mi, d.reshape(H, W)


def smooth3d(values: np.ndarray, mask: np.ndarray, pos: np.ndarray, sigma: float = 1.6, voxel: float = 0.4,
             return_density: bool = False):
    """Gaussian low-pass (``sigma`` cm) of per-texel ``values`` over the head surface in 3D (texels where ``mask``),
    read back at every texel: the same at both sides of a UV seam, unlike a blur in texture space."""
    from scipy import ndimage
    pts = pos[mask]
    lo = pos[mask].min(0) - 4 * sigma
    hi = pos[mask].max(0) + 4 * sigma
    shape = np.ceil((hi - lo) / voxel).astype(int) + 1
    idx = np.clip(np.rint((pts - lo) / voxel).astype(int), 0, shape - 1)
    num = np.zeros(shape); den = np.zeros(shape)
    np.add.at(num, tuple(idx.T), values[mask])
    np.add.at(den, tuple(idx.T), 1.0)
    num = ndimage.gaussian_filter(num, sigma / voxel)
    den = ndimage.gaussian_filter(den, sigma / voxel)
    q = (pos.reshape(-1, 3) - lo) / voxel
    a = ndimage.map_coordinates(num, q.T, order=1, mode="nearest")
    b = ndimage.map_coordinates(den, q.T, order=1, mode="nearest")
    if return_density:
        return (a / np.maximum(b, 1e-9)).reshape(values.shape), b.reshape(values.shape) / max(float(den.max()), 1e-9)
    return (a / np.maximum(b, 1e-9)).reshape(values.shape)


def to_lab(rgb):
    import cv2
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB).astype(np.float64)


def from_lab(lab):
    import cv2
    return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB).astype(np.float64) * 255.0, 0, 255)


# --- colours measured on the photo ----------------------------------------------------------------------------------

def disc_mask(shape, pts, r):
    H, W = shape
    yy, xx = np.mgrid[0:H, 0:W]
    m = np.zeros(shape, bool)
    for x, y in pts:
        m |= (xx - x) ** 2 + (yy - y) ** 2 < r * r
    return m


def poly_mask(shape, pts):
    import cv2
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1)
    return m.astype(bool)


def measure(photo: np.ndarray, L2: np.ndarray) -> dict:
    """Skin, lip, brow and hair colours (RGB) of the photo, from regions around its landmarks."""
    H, W = photo.shape[:2]
    face_h = np.linalg.norm(L2[10] - L2[152])
    r = 0.045 * face_h
    lab = to_lab(photo)
    skin_m = disc_mask((H, W), L2[[50, 280, 101, 330, 151, 108, 337]], r)
    sk = np.median(lab[skin_m], axis=0)
    near = skin_m & (np.abs(lab[..., 0] - sk[0]) < 12)
    skin = np.median(photo[near], axis=0)
    lips_m = poly_mask((H, W), L2[OUTER_LIPS]) & ~poly_mask((H, W), L2[INNER_LIPS])
    lips = np.median(photo[lips_m], axis=0)
    brow_m = poly_mask((H, W), L2[[70, 63, 105, 66, 107, 55, 65, 52, 53, 46]]) | poly_mask((H, W), L2[[300, 293, 334, 296, 336, 285, 295, 282, 283, 276]])
    bl = lab[brow_m]
    brows = np.median(photo[brow_m][bl[:, 0] <= np.percentile(bl[:, 0], 35)], axis=0)
    # hair: a band above the top of the forehead, the pixels unlike skin
    top, chin = L2[10], L2[152]
    up = (top - chin) / np.linalg.norm(top - chin)
    band = np.zeros((H, W), bool)
    for k in np.linspace(0.06, 0.16, 6):
        c = top + up * k * face_h
        band |= disc_mask((H, W), [c, c + [0.12 * face_h, 0], c - [0.12 * face_h, 0]], 0.04 * face_h)
    hl = lab[band]
    unlike = hl[:, 0] < sk[0] - 22
    hair = np.median(photo[band][unlike], axis=0) if unlike.sum() > 20 else np.median(photo[band], axis=0)
    return dict(skin=skin, lips=lips, brows=brows, hair=hair)


# --- one coach --------------------------------------------------------------------------------------------------------

def build(team: str, args) -> dict:
    import cv2
    work = Path(args.work).resolve() / team
    work.mkdir(parents=True, exist_ok=True)
    recipe = recipe_for(team)
    refs = json.loads(Path(args.refs).read_text())[team]
    scene, head, retail, row = load_model(args.retail, team)
    mp = (args.mp_python, args.mp_model)
    L3, _ok, _l2m = mesh_landmarks(head, retail, work, row["archive"].split(".")[0], *mp)
    L3 = L3[:468]
    pairs = mirror_pairs(L3)
    lm = cm1._lm({})
    P0 = head["P"]
    photos = []
    for ref in refs["photos"]:
        if ref.get("role", "texture") not in ("texture", "front"):
            continue
        img = cv2.cvtColor(cv2.imread(ref["path"]), cv2.COLOR_BGR2RGB)
        # crop to the head (full-size headshots are 7000+ px; the texture needs ~1000 px of face)
        (l2,) = detect([ref["path"]], *mp, work)
        if l2 is None:
            raise SystemExit(f"{team}: no face found in {ref['path']}")
        l2 = l2[:468]
        lo, hi = l2.min(0), l2.max(0)
        size = (hi - lo).max()
        c = (lo + hi) / 2
        x0, y0 = int(max(c[0] - 1.1 * size, 0)), int(max(c[1] - 1.2 * size, 0))
        x1, y1 = int(min(c[0] + 1.1 * size, img.shape[1])), int(min(c[1] + 1.0 * size, img.shape[0]))
        crop = img[y0:y1, x0:x1]
        f = 1100.0 / max(crop.shape[:2])
        if f < 1:
            crop = cv2.resize(crop, (int(crop.shape[1] * f), int(crop.shape[0] * f)), interpolation=cv2.INTER_AREA)
        else:
            f = 1.0
        l2 = (l2 - [x0, y0]) * f
        photos.append(dict(img=crop.astype(np.float64), L2=l2, weight=float(ref.get("weight", 1.0)),
                           mouth=ref.get("mouth", recipe.get("mouth", "photo")), path=ref["path"]))
    assert photos, "no texture photo"
    # shape: the symmetric remainder of the front photo, applied to the face
    front = photos[0]
    P = P0.copy()
    L3w = L3.copy()
    wface = face_weight(P0, lm)
    wl = face_weight(L3, lm)
    total = np.zeros_like(P0)
    shape_max = float(recipe.get("shape_max", 0.8))
    for it in range(3):
        pose = solve_pose(L3w, front["L2"], POSE_POINTS, front["img"].shape[1::-1])
        D = shape_offsets(L3w, front["L2"], pose, pairs, SHAPE_POINTS)
        step = shape_field(P0, L3w, D * 0.7, SHAPE_POINTS, wface, cap=shape_max)
        stepl = shape_field(L3, L3w, D * 0.7, SHAPE_POINTS, wl, cap=shape_max)
        total = total + step
        n = np.linalg.norm(total, axis=1, keepdims=True)
        total = total * np.minimum(1.0, shape_max / np.maximum(n, 1e-9))
        P = P0 + total
        L3w = L3w + stepl
        res = np.linalg.norm(front["L2"][SHAPE_POINTS] - project(pose, L3w)[0][SHAPE_POINTS], axis=1)
        print(f"{team} shape pass {it}: yaw {yaw_of(pose):+.1f} deg, landmark error median {np.median(res):.1f} px,"
              f" largest move {np.linalg.norm(total, axis=1).max():.2f} cm", flush=True)
    if recipe.get("shape", True) is False:
        P, L3w = P0.copy(), L3.copy()
    # texture
    scale = 4
    W, H = 256 * scale, 128 * scale
    pos, tn, cov, skin, alt, tri, T = texel_field(head, P, W, H)
    acc = np.zeros((H, W, 3)); wsum = np.zeros((H, W))
    mouth_fill = np.zeros((H, W))
    fixed = list(range(468))
    for ph in photos:
        pose = solve_pose(L3w, ph["L2"], POSE_POINTS, ph["img"].shape[1::-1])
        col, wgt, uvc = project_photo(ph["img"], pose, head, P, L3w, ph["L2"], pos, tn, skin, fixed)
        if ph["mouth"] == "close":
            hh, ww = ph["img"].shape[:2]
            inner = poly_mask((hh, ww), ph["L2"][INNER_LIPS])
            inner = cv2.dilate(inner.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            ix = np.clip(uvc[..., 0].astype(int), 0, ww - 1); iy = np.clip(uvc[..., 1].astype(int), 0, hh - 1)
            mouth_fill = np.maximum(mouth_fill, inner[iy, ix] * (wgt > 0))
        acc += col * (wgt * ph["weight"])[..., None]
        wsum += wgt * ph["weight"]
        ph["pose"] = pose
    proj = acc / np.maximum(wsum, 1e-6)[..., None]
    wproj = np.clip(wsum / max(sum(p["weight"] for p in photos), 1e-6), 0, 1)
    Image.fromarray(np.clip(proj, 0, 255).astype(np.uint8)).save(work / "debug_proj.png")       # review aids
    Image.fromarray((wproj * 255).astype(np.uint8)).save(work / "debug_weight.png")
    # left-right: where one side is seen worse than its mirror, take the mirror's colour
    mi, md = mirror_index(pos, skin)
    wm = wproj[mi[..., 0], mi[..., 1]] * (md < 0.6)
    pm = proj[mi[..., 0], mi[..., 1]]
    use_m = cm1.smoothstep(0.1, 0.5, wm - wproj)[..., None]       # soft, and only where the mirror is seen much better
    proj = proj * (1 - use_m) + pm * use_m
    wproj = np.maximum(wproj, wm)
    Image.fromarray(np.clip(proj, 0, 255).astype(np.uint8)).save(work / "debug_mirrored.png")
    # side light out: the broad luminance made symmetric, highlights compressed
    labp = to_lab(proj)
    valid = (wproj > 0.3) & skin
    low = smooth3d(labp[..., 0], valid, pos, sigma=float(recipe.get("light_sigma", 1.6)))
    low_m = low[mi[..., 0], mi[..., 1]]
    labp[..., 0] += (0.5 * (low + low_m) - low) * float(recipe.get("symmetry", 0.9))
    over = labp[..., 0] - (low + 6)
    labp[..., 0] -= np.clip(over, 0, None) * 0.5
    proj = from_lab(labp)
    Image.fromarray(np.clip(proj, 0, 255).astype(np.uint8)).save(work / "debug_delit.png")
    # the mouth of a smiling or open photo closed: the lip colour, a darker line where the lips meet
    meas = measure(front["img"], front["L2"])
    if mouth_fill.any():
        from scipy import ndimage
        mf = ndimage.gaussian_filter(mouth_fill.astype(float), 1.0 * scale)
        lipc = np.array(meas["lips"], float)
        core = ndimage.gaussian_filter(mouth_fill.astype(float), 0.4 * scale)
        line = lipc * 0.62
        fill = lipc * (1 - core[..., None]) + line * core[..., None]
        proj = proj * (1 - mf[..., None]) + fill * mf[..., None]
    # base head: one tone in his measured skin, his hair, facial hair shapes
    # the base skin is the projected face's own tone where it fades out (sides of the face, jaw, temples), so the
    # head around the face continues it without an edge
    ring = skin & (wproj > 0.9)
    skin_rgb = np.array(recipe.get("skin", np.median(proj[ring], axis=0)), float)
    meas["skin_ring"] = skin_rgb
    hair_rgb = np.array(recipe.get("hair_colour", meas["hair"]), float)
    base_recipe = dict(skin=tuple(skin_rgb), warm=tuple(np.clip(skin_rgb * [1.0, 0.9, 0.88], 0, 255)), neck=0.06,
                       mottling=0.03, lips=tuple(meas["lips"]), brows=tuple(meas["brows"]), detail=0.0, form=0.6)
    if recipe.get("hair"):
        base_recipe["hair"] = dict(recipe["hair"], colour=tuple(hair_rgb))
    if recipe.get("facial"):
        base_recipe["facial"] = [dict(layer, colour=tuple(layer.get("colour", np.array(meas["hair"]) * 0.9)))
                                 for layer in recipe["facial"]]
    base_head = dict(head, P=P)
    base, base_small = paint_base(base_head, retail, base_recipe, scale)
    # compose: projected face over the base, multi-band, only on skin texels
    from scipy import ndimage
    # the weight is a smooth function of the 3D point (facing, depth test, the photo's head mask), so it agrees on
    # both sides of a UV seam; no smoothing in texture space (the UV islands are not neighbours there)
    w = cm1.smoothstep(0.1, 0.7, wproj) * skin * float(recipe.get("photo", 1.0))
    w = np.clip(w, 0, 1)[..., None]
    # the painted base takes the photo's local tone near the face (its broad colour, smoothed over the surface in
    # 3D, as a ratio to the base skin), fading to the base's own tone away from it: no step where the photo ends
    strong = skin & (w[..., 0] > 0.6)
    tint = np.ones_like(base)
    dens = None
    for ch in range(3):
        local, dens = smooth3d(proj[..., ch], strong, pos, sigma=2.0, return_density=True)
        tint[..., ch] = np.clip(local / max(skin_rgb[ch], 1.0), 0.75, 1.3)
    reach = np.clip(dens * 4.0, 0, 1)[..., None]
    tint = 1 + (tint - 1) * reach
    base = np.where(skin[..., None], np.clip(base * tint, 0, 255), base)
    out = proj * w + base * (1 - w)
    # texels no skin triangle covers take the nearest skin texel's colour (so the downsample, the mips and the
    # sampler's filter never mix another colour into an island's edge); the eye atlas keeps the painter's pixels
    _d, (iy, ix) = ndimage.distance_transform_edt(~skin, return_indices=True)
    out = out[iy, ix]
    out = np.where((cov & ~skin)[..., None], base, out)
    small = out.reshape(128, scale, 256, scale, 3).mean(axis=(1, 3))
    atlas_small = (cov & ~skin).reshape(128, scale, 256, scale).mean(axis=(1, 3)) > 0.5
    small = np.where(atlas_small[..., None], base_small[..., :3].astype(float), small)   # eye atlas: the painter's own
    rgba = np.concatenate([np.clip(np.rint(small), 0, 255), np.full((128, 256, 1), 255.0)], -1).astype(np.uint8)
    if recipe.get("eyes"):
        rgba = recolour_iris(rgba, head, recipe["eyes"])
    Image.fromarray(rgba).save(work / "head.png")
    np.save(work / "P.npy", P)
    report = dict(team=team, who=recipe["who"], archive=row["archive"], photos=[p["path"] for p in photos],
                  measured={k: [int(round(x)) for x in v] for k, v in meas.items()},
                  max_move_cm=float(np.linalg.norm(P - P0, axis=1).max()),
                  moved_vertices=int((np.linalg.norm(P - P0, axis=1) > 0.01).sum()),
                  yaw=[yaw_of(p["pose"]) for p in photos])
    (work / "build.json").write_text(json.dumps(report, indent=1))
    return dict(report=report, scene=scene, head=head, P=P, rgba=rgba, row=row, retail=retail)


def recolour_iris(rgba: np.ndarray, head: dict, target) -> np.ndarray:
    """The iris of the model's eye atlas in his eye colour: inside the UV box of the eyeball triangles, the texels
    darker than the white of the eye and lighter than the pupil take ``target`` at their own relative luminance."""
    T, is_skin = skin_tris(head)
    eye = [t for t, sk in zip(T, is_skin) if not sk and float(np.mean(head["P"][t][:, 2])) > 13.0]
    if not eye:
        return rgba
    U = head["U"][np.unique(np.array(eye))]
    U = np.where((U < 0) | (U > 1), U % 1.0, U)          # 1.0 is the far edge, not the start (as cm1's raster)
    H, W = rgba.shape[:2]
    x0, y0 = np.floor(U.min(0) * [W, H]).astype(int)
    x1, y1 = np.ceil(U.max(0) * [W, H]).astype(int)
    out = rgba.copy()
    box = out[y0:y1, x0:x1, :3].astype(float)
    lum = box @ [0.299, 0.587, 0.114]
    sclera = np.percentile(lum, 85)
    iris = (lum < 0.72 * sclera) & (lum > 0.22 * sclera)
    if iris.sum() < 4:
        return rgba
    t = np.asarray(target, float)
    rel = lum / max(float(np.median(lum[iris])), 1.0)
    new = np.clip(t[None, None, :] * rel[..., None], 0, 255)
    box = np.where(iris[..., None], new, box)
    out[y0:y1, x0:x1, :3] = np.rint(box).astype(np.uint8)
    return out


def paint_base(head: dict, retail_rgba: np.ndarray, r: dict, scale: int) -> np.ndarray:
    """cm1's painter: the head at ``scale`` x the texture (float RGB 0..255, for the blend) and at its own size."""
    rgba = cm1.paint_head(head, retail_rgba, r, scale=scale)       # 256 x 128 (it averages down)
    up = Image.fromarray(rgba[..., :3]).resize((256 * scale, 128 * scale), Image.BICUBIC)
    return np.asarray(up, float), rgba


def qc_sheet(team: str, res: dict, out: Path, before_rgba=None, ref_path: str | None = None, size: int = 360):
    """One row: the reference crop | before (front) | after front, 25 and 55 degrees, side (flat and lit) | texture."""
    import cv2
    head, P, rgba = res["head"], res["P"], res["rgba"]
    tiles = []
    if ref_path:
        img = cv2.cvtColor(cv2.imread(ref_path), cv2.COLOR_BGR2RGB)
        work = out.parent
        tiles.append(_ref_crop(img, ref_path, work, size))
    if before_rgba is not None:
        tiles.append(render_textured(head, before_rgba, P=head["P"], size=size, light=0.35)[0])
    for view in ("front", "25", "55", "90"):
        tiles.append(render_textured(head, rgba, P=P, size=size, view=view, light=0.35)[0])
    tex = np.asarray(Image.fromarray(rgba[..., :3]).resize((2 * size, size), Image.NEAREST))
    tiles.append(tex)
    sheet = np.concatenate(tiles, axis=1)
    Image.fromarray(sheet).save(out)
    return out


_CROPS: dict = {}


def _ref_crop(img, path, work, size):
    lms = json.loads((work / "landmarks.json").read_text()) if (work / "landmarks.json").is_file() else {}
    l2 = np.array(lms.get(path)) if lms.get(path) else None
    if l2 is None:
        h, w = img.shape[:2]
        s = min(h, w)
        c = img[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2]
    else:
        lo, hi = l2[:468].min(0), l2[:468].max(0)
        c0 = (lo + hi) / 2
        half = 0.5 * (hi - lo).max() * 1.6
        x0, y0 = int(max(c0[0] - half, 0)), int(max(c0[1] - half * 1.05, 0))
        c = img[y0:int(y0 + 2 * half), x0:int(x0 + 2 * half)]
    return np.asarray(Image.fromarray(c).resize((size, size), Image.LANCZOS))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="scan the named coaches (WORK/<club>/head.png, P.npy, qc.png; --write ships them)")
    b.add_argument("--retail", required=True)
    b.add_argument("--refs", required=True)
    b.add_argument("--work", required=True)
    b.add_argument("--mp-python", required=True)
    b.add_argument("--mp-model", required=True)
    b.add_argument("--teams", required=True)
    b.add_argument("--write", action="store_true", help="write <club>/head.png and geometry.json into the data folder")
    a = p.parse_args(argv)
    for team in [t for t in a.teams.split(",") if t]:
        res = build(team, a)
        work = Path(a.work) / team
        run = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_REF}:data/nfl2k5_modern_coaches/{team}/head.png"],
                             capture_output=True)
        before = np.asarray(Image.open(io.BytesIO(run.stdout)).convert("RGBA")) if run.returncode == 0 else None
        qc_sheet(team, res, work / "qc.png", before, res["report"]["photos"][0])
        if a.write:
            Image.fromarray(res["rgba"]).save(mc.art_path(team, "head"), optimize=True)
            shapes = write_geometry(res["scene"], team, res["P"])
            print(team, "head.png and geometry.json written", shapes)
        print(json.dumps(res["report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
