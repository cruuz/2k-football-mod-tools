#!/usr/bin/env python3
"""cm1: coach models that match each 2026 head coach: authored geometry (head, hair, headset, body) and heads painted
in 3D, for ``mod_editor/core/nfl2k5_modern_coaches.py``.

Every coach is the retail model his club record names (``c%02d.iff``, chunk 0: body, LOD and head shapes on one shared
skeleton). Where texture alone cannot reach the man, this tool moves the model's own vertices (same vertex count,
triangles, skin weights and animations) and writes the result as integers the Studio applies at build time:

* ``bald``: the 2004 hair volume comes off the scalp (inward along the normal, thickest on the crown, faded out below
  the hairline and around the ears); the headset band on the body and the low-detail head and headset follow by the
  same displacement field, so the band stays seated;
* ``body``: the body of a leaner retail coach of the same mesh family (identical vertex order and skin) replaces the
  torso, hips and legs of a paunchy one; the neck, head-borne parts (headset, glasses, cap) and hands stay; the
  low-detail body follows by the displacement field.

Heads (``head``): one continuous skin tone over the whole head, painted per texel at its 3D point on the mesh (so the
UV islands meet without a seam), the fine detail of the club's previous authored face kept on the features only, and
facial hair painted as shapes on the head around its landmarks (lighter than the skin for white or grey hair, never a
dark smudge on a light face). Reference photos are only looked at; no photo pixel enters a texture.

  python3 tools/b77/cm1_coach_models.py geometry --retail RETAIL.iso [--teams WAS]
  python3 tools/b77/cm1_coach_models.py head --retail RETAIL.iso --detail-ref 0a2bcf5c [--teams WAS]

``--detail-ref`` names the commit whose ``<club>/head.png`` gives the fine facial detail (co2's authored faces).
Extending to the historical moment coaches: give a person a recipe (body, ``bald`` or a body donor, a head paint
recipe with his landmarks' heights) and an archive to dress; the operations take any head or body shape of the coach
mesh families (see FAMILIES).
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as mm  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402
import nfl_txtr as tx  # noqa: E402

DATA = mc.DATA_DIR
SHAPES = mc.GEOMETRY_SHAPES

# --- recipes ------------------------------------------------------------------------------------------------------
# heights are in the head shape's bind space (cm; y up, z forward). Landmarks per head model: eye line, brow, nose
# base, mouth line, lower lip, chin, mouth half-width (measured on each model's own mesh through its UV layout).
RECIPES: dict[str, dict] = {
    "WAS": {
        "who": "Dan Quinn",
        "bald": dict(centre=(0.0, 41.0, 7.5), front=44.0, side=45.0, back=36.5, t_top=1.0, t_side=0.6),
        "head": dict(
            skin=(222, 167, 140), warm=(218, 150, 126), neck=0.10, mottling=0.035, freckles=0.07,
            brows=(128, 100, 82), brow_strength=0.8, lips=(200, 128, 116),
            facial=[dict(parts=("moustache", "corners", "chin"), colour=(216, 211, 203), density=0.78)]),
    },
    # Brian Schottenheimer: fair, ruddy skin; short dark-brown hair under the cap; a short salt-and-pepper beard that
    # must read grey on a light face, never a dark smudge (Noah 10/14)
    "DAL": {
        "who": "Brian Schottenheimer",
        "head": dict(
            skin=(200, 146, 128), warm=(196, 128, 112), neck=0.08, lips=(186, 116, 106), brows=(92, 70, 60),
            hair=dict(colour=(58, 44, 36), grey=0.08, front=46.5, recede=1.2, side=43.5, back=34.5, sideburn=38.6),
            facial=[dict(parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(138, 130, 122),
                         density=0.72, light=0.6, light_colour=(198, 192, 184))]),
    },
    # Zac Taylor: very fair, rosy skin; short brown hair greying a little at the sides; clean-shaven; lean
    "CIN": {
        "who": "Zac Taylor",
        "body": dict(donor="20"),
        "head": dict(
            skin=(222, 166, 150), warm=(220, 144, 134), neck=0.08, lips=(205, 122, 116), brows=(110, 86, 72),
            hair=dict(colour=(86, 70, 58), grey=0.02, grey_sides=0.15, front=46.5, recede=0.6, side=43.5, back=34.5,
                      sideburn=38.8)),
    },
    # Dave Canales: olive, tanned skin; short black hair; a light shadow of stubble; lean and fit
    "CAR": {
        "who": "Dave Canales",
        "body": dict(donor="03"),
        "head": dict(
            skin=(208, 158, 134), warm=(204, 140, 118), neck=0.08, lips=(186, 118, 104), brows=(52, 40, 34),
            hair=dict(colour=(34, 28, 25), front=46.8, recede=0.5, side=43.5, back=34.5, sideburn=38.4),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks"), colour=(70, 58, 52), density=0.14)]),
    },
    # Matt LaFleur: tanned skin; short dark hair; heavy dark stubble (a light grey cast, never a smudge)
    "GB": {
        "who": "Matt LaFleur",
        "body": dict(donor="13"),
        "head": dict(
            skin=(200, 146, 124), warm=(196, 126, 104), neck=0.08, lips=(182, 114, 100), brows=(50, 38, 32),
            hair=dict(colour=(38, 30, 26), front=46.6, recede=0.9, side=43.5, back=34.5, sideburn=38.4),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(62, 54, 50),
                         density=0.45)]),
    },
    # Robert Saleh: olive skin; a shaved head; a short dark stubble beard greying at the chin; lean and muscular
    "TEN": {
        "who": "Robert Saleh",
        "body": dict(donor="03"),
        "head": dict(
            skin=(206, 148, 112), warm=(202, 132, 100), neck=0.08, lips=(176, 112, 98), brows=(64, 46, 38),
            hair=dict(colour=(120, 92, 74), opacity=0.22, front=46.0, recede=1.6, side=43.0, back=34.5, sideburn=38.4),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(70, 62, 58),
                         density=0.5, light=0.25, light_colour=(170, 164, 158))]),
    },
    # Sean McVay: fair skin; short light-brown hair; a full, short brown beard; lean
    "LAR": {
        "who": "Sean McVay",
        "body": dict(donor="29"),
        "head": dict(
            skin=(220, 166, 142), warm=(214, 146, 122), neck=0.08, lips=(196, 120, 106), brows=(120, 88, 66),
            hair=dict(colour=(112, 82, 58), front=46.8, recede=1.0, side=43.5, back=34.5, sideburn=38.2),
            facial=[dict(parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(112, 80, 58), density=0.72,
                         light=0.2, light_colour=(150, 112, 80))]),
    },
    # Kyle Shanahan: fair skin; dark hair swept back, greying at the temples; a light stubble; lean
    "SF": {
        "who": "Kyle Shanahan",
        "body": dict(donor="20"),
        "head": dict(
            skin=(196, 146, 128), warm=(190, 126, 110), neck=0.08, lips=(180, 112, 102), brows=(58, 44, 38),
            hair=dict(colour=(42, 35, 31), grey=0.06, grey_sides=0.4, front=46.6, recede=1.2, side=43.5, back=34.5,
                      sideburn=38.6),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks"), colour=(80, 70, 64), density=0.14)]),
    },
    # Aaron Glenn: medium-dark brown skin (co2's was a saturated red); very short grey-black hair under the cap; a white
    # moustache and goatee
    "NYJ": {
        "who": "Aaron Glenn",
        "head": dict(
            skin=(134, 88, 66), warm=(132, 80, 62), neck=0.06, mottling=0.03, lips=(118, 72, 64), brows=(58, 40, 32),
            brow_strength=0.5,
            hair=dict(colour=(58, 52, 50), grey=0.35, grey_colour=(150, 146, 142), front=46.0, recede=1.0, side=43.5,
                      back=34.5, sideburn=38.8),
            facial=[dict(parts=("moustache", "corners", "chin"), colour=(206, 204, 200), density=0.8),
                    dict(kind="stubble", parts=("cheeks", "neck"), colour=(150, 146, 142), density=0.18)]),
    },
    # Todd Bowles: dark brown skin (co2's was a saturated orange); shaved head under the cap; a short grey-black beard
    "TB": {
        "who": "Todd Bowles",
        "head": dict(
            skin=(100, 64, 50), warm=(100, 58, 46), neck=0.06, mottling=0.03, lips=(104, 62, 56), brows=(48, 34, 28),
            brow_strength=0.5, eyes=(80, 52, 36),
            hair=dict(colour=(44, 36, 32), opacity=0.25, front=46.0, recede=1.4, side=43.0, back=34.5, sideburn=38.6),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(64, 58, 56),
                         density=0.45, light=0.3, light_colour=(140, 136, 132))]),
    },
    # Jeff Hafley: fair skin (co2's was orange with a dark line at the smile); short brown hair receding at the temples;
    # a light brown-grey stubble
    "MIA": {
        "who": "Jeff Hafley",
        "head": dict(
            skin=(212, 162, 142), warm=(208, 142, 124), neck=0.08, lips=(192, 120, 106), brows=(96, 74, 60),
            hair=dict(colour=(96, 76, 60), front=47.0, recede=1.7, side=43.5, back=34.5, sideburn=38.8),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks"), colour=(112, 100, 92),
                         density=0.16)]),
    },
    # Dan Campbell: fair, ruddy skin; short grey-brown hair; a grey moustache and goatee
    "DET": {
        "who": "Dan Campbell",
        "head": dict(
            skin=(214, 160, 144), warm=(212, 138, 124), neck=0.08, lips=(192, 118, 108), brows=(118, 98, 86),
            hair=dict(colour=(112, 98, 88), grey=0.3, grey_colour=(176, 172, 166), front=47.0, recede=1.4, side=43.2,
                      back=34.5, sideburn=38.8),
            facial=[dict(parts=("moustache", "corners", "chin"), colour=(118, 110, 104), density=0.85, light=0.4,
                         light_colour=(204, 200, 192)),
                    dict(kind="stubble", parts=("cheeks",), colour=(150, 144, 138), density=0.15)]),
    },
    # Todd Monken: fair, ruddy skin (co2's c00 head was a dark 2004 head pulled light, still too orange); full white-grey
    # hair; clean-shaven
    "CLE": {
        "who": "Todd Monken",
        "head": dict(
            skin=(218, 156, 136), warm=(214, 134, 116), neck=0.08, lips=(196, 122, 110), brows=(160, 140, 126),
            hair=dict(colour=(196, 190, 184), front=46.6, recede=1.0, side=43.5, back=34.5, sideburn=39.0)),
    },
    # Mike Vrabel: fair skin; short salt-and-pepper hair; a short grey stubble beard (light grey, never a smudge)
    "NE": {
        "who": "Mike Vrabel",
        "head": dict(
            skin=(206, 156, 144), warm=(204, 136, 126), neck=0.08, lips=(186, 118, 110), brows=(84, 70, 64),
            hair=dict(colour=(80, 72, 70), grey=0.45, grey_colour=(172, 168, 166), front=46.8, recede=1.2, side=43.2,
                      back=34.5, sideburn=38.6),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks", "neck"), colour=(104, 100, 98),
                         density=0.6, light=0.45, light_colour=(196, 192, 188))]),
    },
    # Kevin Stefanski: fair skin; short grey hair; a short grey beard heaviest on the chin
    "ATL": {
        "who": "Kevin Stefanski",
        "head": dict(
            skin=(212, 156, 138), warm=(208, 136, 120), neck=0.08, lips=(190, 118, 106), brows=(100, 82, 74),
            hair=dict(colour=(112, 106, 102), grey=0.5, grey_colour=(176, 172, 168), front=46.8, recede=1.0, side=43.4,
                      back=34.5, sideburn=38.6),
            facial=[dict(parts=("moustache", "corners", "chin"), colour=(120, 116, 112), density=0.85, light=0.45,
                         light_colour=(196, 192, 188)),
                    dict(kind="stubble", parts=("cheeks", "neck"), colour=(112, 108, 104), density=0.45, light=0.4,
                         light_colour=(190, 186, 182))]),
    },
    # Liam Coen: very fair, pink skin; full light-brown hair (co2's read thin and blond on the short 2004 layout);
    # clean-shaven; an athletic build (c30 is heavy-ish and has its own vertex order: the slim build comes over by
    # position from c28, which has the same build, to the lean c12)
    "JAX": {
        "who": "Liam Coen",
        "body": dict(donor="12", via="28"),
        "head": dict(
            skin=(222, 170, 158), warm=(218, 148, 140), neck=0.08, lips=(204, 128, 118), brows=(128, 100, 84),
            hair=dict(colour=(128, 100, 78), front=46.6, recede=0.6, side=43.6, back=34.2, sideburn=39.0)),
    },
    # John Harbaugh: fair skin; dark grey hair under the cap, greying at the sides; clean-shaven (co2's grin read as a
    # grimace: less of the photo's fine detail)
    "NYG": {
        "who": "John Harbaugh",
        "head": dict(
            skin=(216, 166, 148), warm=(212, 146, 130), neck=0.08, lips=(196, 124, 112), brows=(80, 66, 60), detail=0.55,
            hair=dict(colour=(66, 58, 54), grey=0.2, grey_sides=0.35, grey_colour=(160, 156, 152), front=46.8, recede=1.0,
                      side=43.5, back=34.5, sideburn=38.8)),
    },
    # Kevin O'Connell: fair skin; light-brown hair, a little receded; clean-shaven; lean and tall
    "MIN": {
        "who": "Kevin O'Connell",
        "body": dict(donor="12"),
        "head": dict(
            skin=(214, 170, 152), warm=(210, 152, 136), neck=0.08, lips=(200, 126, 112), brows=(130, 102, 84),
            hair=dict(colour=(98, 78, 60), front=47.0, recede=1.4, side=43.5, back=34.5, sideburn=38.8)),
    },
}


# --- the coach scene from a disc image ------------------------------------------------------------------------------

def read_archive(image, name: str) -> bytes:
    with mc._outer_image()(image) as archive:
        entry = {e.name_id: e for e in archive.entries}.get(mc.name_id(name))
        if entry is None:
            raise SystemExit(f"{name} is not on {image}")
        return archive.read(entry.virtual_offset, entry.size)


class Scene:
    """One coach scene: decoded bytes, per shape the game-order positions, normals, UVs, triangles and materials."""

    def __init__(self, raw: bytes, name: str):
        self.raw, self.name = raw, name
        self.chunk = tx.parse_chunks(raw)[0]
        self.rec, decoded = mm._scene(raw, self.chunk)
        self.decoded = bytearray(decoded)
        self.shapes = {}
        with tempfile.TemporaryDirectory() as tmp:
            key = models.model_key(0, 0)
            span = raw[:0x20 + self.chunk.stored_size]
            src = models.ModelSpanSource({key: span})
            path = Path(tmp) / "scene.gltf"
            models.export_model(src, key, path)
            self.mesh = load_gltf(path)
            self.joints = joint_world(path)
        for name_ in SHAPES:
            lanes, position_at, normal_at = mc._geometry_lanes(self.rec, self.decoded, name_)
            P = np.array(models.read_positions(bytes(self.decoded), _shape(self.rec, name_), lanes))
            words = np.array([int.from_bytes(self.decoded[normal_at(v):normal_at(v) + 4], "little")
                              for v in range(lanes.vertex_count)], np.int64)
            m = self.mesh[name_]
            assert np.abs(P - m["P"]).max() < 1e-3, name_
            self.shapes[name_] = dict(P=P, words=words, lanes=lanes, T=m["T"], U=m["U"], mats=m["mats"],
                                      digest=mc.geometry_lanes_digest(self.rec, self.decoded, name_))


def _shape(rec, name):
    return next(s for s in rec["shapes"] if str(s["name"]) == name and int(s["vertex_count"]) > 0)


def load_gltf(path: Path) -> dict:
    g = json.loads(path.read_text()); b = path.with_suffix(".bin").read_bytes()

    def acc(i):
        a = g["accessors"][i]; bv = g["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[a["componentType"]]
        return np.frombuffer(b, dt, count=a["count"] * n, offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(a["count"], n)
    mats = [m["name"] for m in g["materials"]]
    out = {}
    for m in g["meshes"]:
        n = m["extras"]["nfl2k5_vertex_count"]
        P = np.zeros((n, 3)); U = np.zeros((n, 2)); tris = []; pm = []
        for pr in m["primitives"]:
            vi = acc(pr["attributes"]["_NFL_VERTEX_INDEX"])[:, 0].astype(int)
            P[vi] = acc(pr["attributes"]["POSITION"]); U[vi] = acc(pr["attributes"]["TEXCOORD_0"])
            idx = acc(pr["indices"])[:, 0].astype(int)
            if pr.get("mode", 4) == 5:
                t = np.array([(idx[k], idx[k + 1], idx[k + 2]) if k % 2 == 0 else (idx[k + 1], idx[k], idx[k + 2])
                              for k in range(len(idx) - 2)]).reshape(-1, 3)
                t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
            else:
                t = idx.reshape(-1, 3)
            tris.append(vi[t]); pm.append((mats[pr["material"]], len(t)))
        out[m["name"]] = dict(P=P, U=U, T=np.concatenate(tris), mats=pm)
    return out


def joint_world(path: Path) -> dict:
    g = json.loads(path.read_text()); b = path.with_suffix(".bin").read_bytes()
    out = {}
    for s in g.get("skins", []):
        a = g["accessors"][s["inverseBindMatrices"]]; bv = g["bufferViews"][a["bufferView"]]
        m = np.frombuffer(b, np.float32, count=16 * a["count"], offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        for j, mat in zip(s["joints"], m.reshape(-1, 4, 4)):
            out[g["nodes"][j]["name"]] = np.linalg.inv(mat.T.astype(float))[:3, 3]
    return out


def tris_of(shape: dict, material: str | None = None) -> np.ndarray:
    out, start = [], 0
    for name, count in shape["mats"]:
        if material is None or name == material:
            out.append(shape["T"][start:start + count])
        start += count
    return np.concatenate(out) if out else np.zeros((0, 3), int)


# --- mesh helpers -------------------------------------------------------------------------------------------------

def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def weld_groups(P):
    key = {}
    for i, p in enumerate(np.round(P, 3)):
        key.setdefault(tuple(p), []).append(i)
    return [g for g in key.values() if len(g) > 1]


def vertex_normals(P, T):
    N = np.zeros_like(P)
    f = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    for k in range(3):
        np.add.at(N, T[:, k], f)
    for g in weld_groups(P):
        N[g] = N[g].sum(0)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)


def carry_field(src_pts, src_disp, dst_pts, radius=2.5, sigma=1.0):
    """Displacement of points near a displaced surface (Gaussian-weighted mean of the nearby source moves)."""
    out = np.zeros_like(dst_pts)
    if not (np.linalg.norm(src_disp, axis=1) > 1e-6).any():
        return out
    for i, q in enumerate(dst_pts):
        d2 = ((src_pts - q) ** 2).sum(1)
        near = d2 < radius * radius
        if near.any():
            w = np.exp(-d2[near] / (sigma * sigma))
            out[i] = (w[:, None] * src_disp[near]).sum(0) / max(w.sum(), 1e-9)
    return out


def ear_mask(head: dict) -> np.ndarray:
    u, v = head["U"][:, 0] % 1, head["U"][:, 1] % 1
    return (u > 0.56) & (u < 0.76) & (v > 0.78)


def bald_cranium(P, T, N, ears, *, centre, front, side, back, low=1.5, high=2.5, t_top=1.0, t_side=0.6,
                 ear_near=0.8, ear_far=2.5):
    """The 2004 hair volume off a head: the scalp moves inward along its normal (``t_top`` on the crown, ``t_side``
    round the sides and back), faded out below the hairline (``front`` / ``side`` / ``back`` heights) and near the
    ears."""
    d = P - np.asarray(centre, float)
    a = np.abs(np.arctan2(d[:, 0], d[:, 2])) / np.pi
    boundary = np.where(a < 0.5, front + (side - front) * (a / 0.5), side + (back - side) * ((a - 0.5) / 0.5))
    w = smoothstep(boundary - low, boundary + high, P[:, 1])
    if ears.any():
        E = P[ears]
        dist = np.sqrt(((P[:, None, :] - E[None, :, :]) ** 2).sum(-1)).min(1)
        w = w * smoothstep(ear_near, ear_far, dist)
    up = np.clip(d[:, 1] / np.maximum(np.linalg.norm(d, axis=1), 1e-9), 0, 1)
    return P - (w * (t_side + (t_top - t_side) * up ** 2))[:, None] * N


def hair_volume(P, N, ears, *, front, amount, crown=0.5, back=0.15, low=0.6, high=2.0, centre=(0.0, 41.0, 7.5)):
    """More hair on a 2004 head (a fuller or spiked top): the scalp above the front hairline moves outward along its
    normal, ``amount`` cm over the front of the top, ``crown`` x that at the crown and ``back`` x at the back, faded in
    above the hairline and kept off the ears."""
    d = P - np.asarray(centre, float)
    w = smoothstep(front - low, front + high, P[:, 1])
    frontness = smoothstep(-6.0, 12.0, d[:, 2])                  # 0 at the back of the head, 1 at the forehead
    profile = back + (1.0 - back) * frontness
    profile = profile * (crown + (1 - crown) * smoothstep(3.0, 9.0, d[:, 2]))
    if ears.any():
        E = P[ears]
        dist = np.sqrt(((P[:, None, :] - E[None, :, :]) ** 2).sum(-1)).min(1)
        w = w * smoothstep(1.0, 3.0, dist)
    return P + (w * amount * profile)[:, None] * N


def carried_normals(words, P_old, P_new, T):
    """The shape's own normals carried through the change (only where a vertex or a neighbour moved)."""
    n0 = np.array([models.decode_normpacked3(int(w)) for w in words])
    moved = np.linalg.norm(P_new - P_old, axis=1) > 1e-4
    region = moved.copy()
    for a, b, c in T:
        if moved[a] or moved[b] or moved[c]:
            region[[a, b, c]] = True
    na, nb = vertex_normals(P_old, T), vertex_normals(P_new, T)
    n = n0.copy()
    v = n0[region] + (nb[region] - na[region])
    n[region] = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
    return n, region


def geometry_document(scene: Scene, new_positions: dict, new_normals: dict | None = None) -> dict:
    """The integer edit for every shape whose positions change: NORMSHORT3 values and NORMPACKED3 normals of the
    vertices that move (and the normals of their neighbours)."""
    shapes = []
    for name in SHAPES:
        if name not in new_positions:
            continue
        s = scene.shapes[name]
        lanes, P, Q = s["lanes"], s["P"], new_positions[name]
        off, scale = np.asarray(lanes.offset), lanes.scale
        old_q = np.array([[models.encode_normshort(max(-1.0, min(1.0, (p[a] - off[a]) / scale))) for a in range(3)]
                          for p in P])
        new_q = np.array([[models.encode_normshort(max(-1.0, min(1.0, (q[a] - off[a]) / scale))) for a in range(3)]
                          for q in Q])
        # the retail lane values decode to P exactly; keep them for every vertex that did not move
        moved = np.linalg.norm(Q - P, axis=1) > scale / 32767.0
        assert np.all(np.abs(new_q) <= 32767), name
        n, region = carried_normals(s["words"], P, Q, tris_of(s))
        if new_normals and name in new_normals:          # normals given by the edit (a donor body's own)
            n, region = new_normals[name], np.ones(len(P), bool)
        words = [models.encode_normpacked3(*v) for v in n]
        positions = [[int(i), *map(int, new_q[i])] for i in np.nonzero(moved)[0] if not np.array_equal(new_q[i], old_q[i])]
        normals = [[int(i), int(words[i])] for i in np.nonzero(region)[0] if int(words[i]) != int(s["words"][i])]
        shapes.append(dict(name=name, vertex_count=int(lanes.vertex_count), lanes_sha256=s["digest"],
                           positions=positions, normals=normals))
    return dict(schema=mc.GEOMETRY_SCHEMA, archive=scene.name, shapes=shapes)


# the retail coach bodies in mesh families (identical vertex order, triangles and skin; only the sculpt differs)
FAMILIES = {
    "plain": ("00", "01", "02", "03", "04", "05", "06", "08", "09", "12", "14", "15", "16", "17", "20", "25", "28",
              "33", "36"),
    "glasses": ("10", "13", "23", "26", "29"),
    "cap": ("07", "11", "18", "19", "22", "27", "37"),
}


def body_from_donor(body: dict, donor: dict, keep_from=(58.0, 64.0)) -> np.ndarray:
    """The torso, arms, hips and legs of a donor body of the same family; the neck and everything the head carries
    (headset, glasses, cap) stay where this model has them, faded between ``keep_from`` heights (cm)."""
    assert body["P"].shape == donor["P"].shape and np.array_equal(body["T"], donor["T"]), "not the same mesh family"
    keep = smoothstep(keep_from[0], keep_from[1], body["P"][:, 1])
    return body["P"] + (1 - keep)[:, None] * (donor["P"] - body["P"])


def make_geometry(scene: Scene, recipe: dict, donor: "Scene | None" = None) -> tuple[dict, dict]:
    head, body, lod = (scene.shapes[n] for n in ("coachHeadGrp1", "coachBodyGrp1", "coachLodGrp1"))
    new, normals = {}, {}
    offset = scene.joints["coachBodyGrp1:thorax"] - scene.joints["coachHeadGrp1:thorax"]
    if "body" in recipe and recipe["body"].get("via"):
        # a model with its own vertex order (c30): the change from the "via" body (same build, another family) to
        # the donor is carried over by position (each vertex takes the move of the via body's vertices around it)
        via, dn = donor
        Pv = via.shapes["coachBodyGrp1"]["P"]
        keep_v = smoothstep(58.0, 64.0, Pv[:, 1])[:, None]
        Dv = (1 - keep_v) * (dn.shapes["coachBodyGrp1"]["P"] - Pv)
        Db = carry_field(Pv, Dv, body["P"], 1.5, 0.5)
        new["coachBodyGrp1"] = body["P"] + Db
        new["coachLodGrp1"] = lod["P"] + carry_field(body["P"], Db, lod["P"], 6.0, 2.5)
    elif "body" in recipe:
        Qb = body_from_donor(body, donor.shapes["coachBodyGrp1"])
        Db = Qb - body["P"]
        new["coachBodyGrp1"] = Qb
        # the donor's own shading normals where its shape is taken, this model's where it stays
        keep = smoothstep(58.0, 64.0, body["P"][:, 1])[:, None]
        n_own = np.array([models.decode_normpacked3(int(w)) for w in body["words"]])
        n_don = np.array([models.decode_normpacked3(int(w)) for w in donor.shapes["coachBodyGrp1"]["words"]])
        nb = keep * n_own + (1 - keep) * n_don
        normals["coachBodyGrp1"] = nb / np.maximum(np.linalg.norm(nb, axis=1, keepdims=True), 1e-9)
        # the low-detail body follows the same change (its vertices take the move of the body around them)
        new["coachLodGrp1"] = lod["P"] + carry_field(body["P"], Db, lod["P"], 6.0, 2.5)
    if "hair_volume" in recipe:
        Ph = head["P"]
        Qh = hair_volume(Ph, vertex_normals(Ph, tris_of(head)), ear_mask(head), **recipe["hair_volume"])
        Dh = Qh - Ph
        new["coachHeadGrp1"] = Qh
        Pb = new.get("coachBodyGrp1", body["P"]); Pl = new.get("coachLodGrp1", lod["P"])
        new["coachBodyGrp1"] = Pb + carry_field(Ph + offset, Dh, body["P"], 2.5, 1.0)
        new["coachLodGrp1"] = Pl + carry_field(Ph + offset, Dh, lod["P"], 3.0, 1.2)
    if "bald" in recipe:
        Ph = head["P"]
        Qh = bald_cranium(Ph, tris_of(head), vertex_normals(Ph, tris_of(head)), ear_mask(head), **recipe["bald"])
        Dh = Qh - Ph
        new["coachHeadGrp1"] = Qh
        Pb = new.get("coachBodyGrp1", body["P"]); Pl = new.get("coachLodGrp1", lod["P"])
        new["coachBodyGrp1"] = Pb + carry_field(Ph + offset, Dh, body["P"], 2.5, 1.0)
        new["coachLodGrp1"] = Pl + carry_field(Ph + offset, Dh, lod["P"], 3.0, 1.2)
    return geometry_document(scene, new, normals), new


# --- head painting ------------------------------------------------------------------------------------------------

def raster(U, P, T, W, H, shared_cm=1.0):
    """Per texel of the UV layout: the 3D point it paints, its triangle (-1 where none covers it), and for texels the
    2004 layout shares between two places of the head (not mirror images: the tiled scalp strip) the other place."""
    pos = np.zeros((H, W, 3)); tri = -np.ones((H, W), int); alt = np.full((H, W, 3), np.nan)
    # u or v exactly 1.0 is the texture's far edge, not its start: only values outside [0, 1] wrap
    UV = np.where((U < -1e-6) | (U > 1.0 + 1e-6), U % 1.0, np.clip(U, 0.0, 1.0)) * (W, H)
    for ti, t in enumerate(T):
        a, b, c = UV[t[0]], UV[t[1]], UV[t[2]]
        x0, x1 = int(np.floor(min(a[0], b[0], c[0]))), int(np.ceil(max(a[0], b[0], c[0])))
        y0, y1 = int(np.floor(min(a[1], b[1], c[1]))), int(np.ceil(max(a[1], b[1], c[1])))
        if x1 - x0 > W / 2 or y1 - y0 > H / 2:
            continue
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1 + 1, W)) + 0.5, np.arange(max(y0, 0), min(y1 + 1, H)) + 0.5)
        m = np.array([[b[0] - a[0], c[0] - a[0]], [b[1] - a[1], c[1] - a[1]]])
        if xs.size == 0 or abs(np.linalg.det(m)) < 1e-9:
            continue
        inv = np.linalg.inv(m)
        dx, dy = xs - a[0], ys - a[1]
        s = inv[0, 0] * dx + inv[0, 1] * dy; r = inv[1, 0] * dx + inv[1, 1] * dy
        inside = (s >= -1e-4) & (r >= -1e-4) & (s + r <= 1 + 1e-4)
        ix = np.minimum((xs[inside] - 0.5).astype(int), W - 1); iy = np.minimum((ys[inside] - 0.5).astype(int), H - 1)
        ss, rr = s[inside][:, None], r[inside][:, None]
        p = P[t[0]] + ss * (P[t[1]] - P[t[0]]) + rr * (P[t[2]] - P[t[0]])
        had = tri[iy, ix] >= 0
        prev = pos[iy, ix]
        mirror = np.abs(prev) - np.abs(p)
        mirror[:, 1:] = (prev - p)[:, 1:]
        far = had & (np.linalg.norm(mirror, axis=1) > shared_cm)
        alt[iy[far], ix[far]] = p[far]
        fresh = ~had
        pos[iy[fresh], ix[fresh]] = p[fresh]
        tri[iy[fresh], ix[fresh]] = ti
    return pos, tri, alt


def dilate(field, mask, iterations):
    f, m = field.copy(), mask.copy()
    for _ in range(iterations):
        acc = np.zeros_like(f); cnt = np.zeros(m.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sm = np.roll(np.roll(m, dy, 0), dx, 1); sf = np.roll(np.roll(f, dy, 0), dx, 1)
            acc += sf * sm[..., None]; cnt += sm
        grow = (~m) & (cnt > 0)
        if not grow.any():
            break
        f[grow] = acc[grow] / cnt[grow][:, None]
        m = m | grow
    return f


def gblur(a, sigma):
    r = int(3 * sigma + 0.5)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    out = np.asarray(a, float)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim; pad[axis] = (r, r)
        p = np.pad(out, pad, mode="reflect"); acc = np.zeros_like(out)
        for i, w in enumerate(k):
            sl = [slice(None)] * out.ndim; sl[axis] = slice(i, i + out.shape[axis])
            acc += w * p[tuple(sl)]
        out = acc
    return out


def value_noise3(pos, scale, seed):
    table = np.random.default_rng(seed).uniform(-1, 1, 4096)
    p = np.asarray(pos, float) / scale
    i = np.floor(p).astype(np.int64); f = p - i; f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((f[..., 0] if dx else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1])
                     * (f[..., 2] if dz else 1 - f[..., 2]))
                out = out + w * table[(((i[..., 0] + dx) * 73856093) ^ ((i[..., 1] + dy) * 19349663)
                                       ^ ((i[..., 2] + dz) * 83492791)) & 4095]
    return out


def fbm3(pos, scale, octaves, seed):
    out, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        out = out + amp * value_noise3(pos, scale / 2 ** o, seed + o); tot += amp; amp *= 0.5
    return out / tot


def skin_component(head: dict) -> set:
    """Vertices of the head's skin shell (the largest piece once UV seams are welded; not the eyes or the teeth)."""
    n = len(head["P"])
    nb = [set() for _ in range(n)]
    for a, b, c in head["T"]:
        nb[a].update((b, c)); nb[b].update((a, c)); nb[c].update((a, b))
    for g in weld_groups(head["P"]):
        for a in g:
            nb[a].update(g)
    seen = np.zeros(n, bool); best = []
    for s0 in range(n):
        if seen[s0]:
            continue
        stack, comp = [s0], []
        seen[s0] = True
        while stack:
            a = stack.pop(); comp.append(a)
            for b in nb[a]:
                if not seen[b]:
                    seen[b] = True; stack.append(b)
        if len(comp) > len(best):
            best = comp
    return set(best)


# the face rig every coach head shares (same facial joints on every model): landmark heights in head space, cm,
# measured on c29 through its UV layout; a recipe may override any of them
LANDMARKS = dict(eye=40.2, brow=41.46, nose_base=35.37, lip_top=33.57, mouth=32.88, lip_bottom=32.32, chin=28.27,
                 mouth_half=2.6, face_z=12.0, ear_front=9.5, ear_top=44.6, ear_bottom=35.6)


def _lm(r: dict) -> dict:
    return dict(LANDMARKS, **r.get("landmarks", {}))


def skin_tone(pos, r: dict) -> np.ndarray:
    """The base skin colour at head points ``pos`` (texture space, before the game's lighting): one tone with warmth
    on the cheeks, nose and ears, a slightly darker throat, and fine mottling (symmetric left and right)."""
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    sym = np.stack([ax, y, z], -1)
    lm = _lm(r)
    rgb = np.ones(pos.shape[:-1] + (3,)) * (np.array(r["skin"]) / 255.0)
    cheek = np.exp(-(((ax - 4.6) / 1.8) ** 2 + ((y - (lm["nose_base"] + 0.2)) / 1.8) ** 2)) * (z > lm["face_z"])
    nose = np.exp(-((x / 1.2) ** 2 + ((y - (lm["nose_base"] + 1.4)) / 1.6) ** 2)) * (z > lm["face_z"] + 4)
    ear = (smoothstep(7.8, 8.8, ax) * smoothstep(34.5, 36.0, y) * (1 - smoothstep(44.0, 45.5, y))
           * smoothstep(4.0, 5.5, z) * (1 - smoothstep(lm["ear_front"] - 0.4, lm["ear_front"] + 0.2, z)))
    warm = np.clip(r.get("warmth", 1.0) * (0.55 * cheek + 0.6 * nose + 0.5 * ear), 0, 1)[..., None]
    rgb = rgb * (1 - warm) + (np.array(r["warm"]) / 255.0) * warm
    throat = ((1 - smoothstep(lm["chin"] - 1.3, lm["chin"] + 3.2, y)) * (1 - smoothstep(14.0, 18.5, z))
              * smoothstep(4.0, 8.0, z))[..., None]
    rgb = rgb * (1 - r.get("neck", 0.1) * throat) + np.array([-0.01, 0.0, 0.01]) * throat
    rgb = rgb * (1 + r.get("mottling", 0.035) * fbm3(sym, 1.6, 3, 11))[..., None]
    freck = (smoothstep(0.62, 0.8, value_noise3(sym, 0.22, 5)) * smoothstep(44.5, 48.0, y))[..., None]
    rgb = rgb * (1 - r.get("freckles", 0.0) * freck) + np.array([0.012, -0.004, -0.012]) * freck * (r.get("freckles", 0.0) > 0)
    return rgb


def hair_cover(pos, r: dict) -> np.ndarray:
    """0..1 scalp hair coverage at head points: above the hairline (forehead, temples, above the ears, nape) and the
    sideburns in front of the ears; a soft, broken edge."""
    h = r.get("hair")
    if not h:
        return np.zeros(pos.shape[:-1])
    lm = _lm(r)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    a = np.abs(np.arctan2(x, z - 7.5)) / np.pi            # 0 front, 0.5 over the ear, 1 back
    front = h["front"] + h.get("recede", 0.0) * smoothstep(1.2, 4.2, ax)
    side, back = h["side"], h["back"]
    line = np.where(a < 0.5, front + (side - front) * smoothstep(0.18, 0.5, a), side + (back - side) * smoothstep(0.5, 0.82, a))
    jitter = 0.18 * value_noise3(np.stack([ax, y, z], -1), 0.25, 31)
    cover = smoothstep(line - h.get("edge", 0.35) + jitter, line + h.get("edge", 0.35) + jitter, y)
    sb = h.get("sideburn")
    if sb is not None:
        # a strip in front of the ear down to ``sb`` (cm), joining the hair above the ear
        burn = (smoothstep(sb - 0.3, sb + 0.3, y) * smoothstep(lm["ear_front"] - 0.7, lm["ear_front"] - 0.2, z)
                * (1 - smoothstep(lm["ear_front"] + 1.1, lm["ear_front"] + 1.7, z)) * smoothstep(5.0, 6.0, ax))
        cover = np.maximum(cover, burn)
    return np.clip(cover, 0, 1)


def facial_parts(pos, r: dict) -> dict:
    """0..1 areas of the face where beard hair grows (shapes on the head around the face-rig landmarks)."""
    lm = _lm(r)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    soft = 0.22
    mh = lm["mouth_half"]

    def band(v, lo, hi, sf=soft):
        return smoothstep(lo - sf, lo + sf, v) * (1 - smoothstep(hi - sf, hi + sf, v))
    front = smoothstep(lm["face_z"], lm["face_z"] + 2, z)
    mlo, mhi = lm["lip_top"] - 0.12, lm["nose_base"] - 0.32
    yy = np.clip(y, mlo, mhi)
    width = mh - 0.3 + 0.35 * (mhi - yy)
    moustache = band(y, mlo, mhi) * (1 - smoothstep(width - soft, width + soft, ax)) * front
    corners = band(y, lm["mouth"] - 2.3, lm["lip_top"] + 0.3) * band(ax, mh - 0.45, mh + 0.55) * front
    chin_w = mh + 0.45 + 0.18 * np.clip(lm["chin"] + 2.7 - y, 0, 4) * -1
    chin = ((1 - smoothstep(lm["lip_bottom"] - 0.27 - soft, lm["lip_bottom"] - 0.27 + soft, y))
            * smoothstep(lm["chin"] - 1.9, lm["chin"] - 0.7, y) * (1 - smoothstep(chin_w - soft, chin_w + soft, ax))
            * smoothstep(lm["face_z"] - 1.0, lm["face_z"] + 1.0, z))
    # cheeks and jaw: below a line from the nose wing rising to the sideburn, in front of the ear, above the neck
    cheek_top = (lm["nose_base"] - 0.5 + 0.28 * np.clip(ax - 2.5, 0, None) ** 1.3
                 + 1.6 * smoothstep(5.8, 7.6, ax))           # up to the sideburn in front of the ear
    neck_line = lm["chin"] - 2.2 + 0.55 * ax
    cheeks = ((1 - smoothstep(cheek_top - 0.55, cheek_top + 0.55, y)) * smoothstep(neck_line - 0.3, neck_line + 0.5, y)
              * smoothstep(lm["ear_front"] - 0.2, lm["ear_front"] + 0.8, z) * smoothstep(mh - 0.6, mh + 0.6, ax))
    neck = (smoothstep(neck_line - 1.6, neck_line - 0.4, y) * (1 - smoothstep(neck_line + 0.2, neck_line + 0.6, y))
            * smoothstep(6.0, 9.0, z))
    return dict(moustache=moustache, corners=corners, chin=chin, cheeks=cheeks, neck=neck)


def paint_head(head: dict, detail_rgba: np.ndarray, r: dict, scale: int = 4) -> np.ndarray:
    """The 256x128 head texture (RGBA uint8) for recipe ``r``: skin, scalp hair (or a bald head), facial hair."""
    H0, W0 = detail_rgba.shape[:2]
    W, H = W0 * scale, H0 * scale
    T = tris_of(head, "headShader1")
    pos, tri, alt = raster(head["U"], head["P"], T, W, H)
    cov = tri >= 0
    main = skin_component(head)
    tri_main = np.array([t[0] in main for t in T])
    skin = cov & tri_main[np.maximum(tri, 0)]
    shared = skin & ~np.isnan(alt[..., 0])
    lm = _lm(r)
    src = np.asarray(Image.fromarray(detail_rgba).convert("RGB").resize((W, H), Image.BICUBIC), float) / 255.0
    L = src[..., 0] * 0.299 + src[..., 1] * 0.587 + src[..., 2] * 0.114
    m = skin.astype(float)
    LB = gblur(L * m, 5.0 * scale / 4) / np.maximum(gblur(m, 5.0 * scale / 4), 1e-6)
    detail = np.clip(L / np.maximum(LB, 1e-4), 0.55, 1.45)

    def colour_at(p, with_detail):
        """The texture colour at head points ``p`` (detail only where with_detail)."""
        x, y, z = p[..., 0], p[..., 1], p[..., 2]
        ax = np.abs(x)
        sym = np.stack([ax, y, z], -1)
        rgb = skin_tone(p, r)
        ear = (smoothstep(7.8, 8.8, ax) * smoothstep(34.5, 36.0, y) * (1 - smoothstep(44.0, 45.5, y))
               * smoothstep(4.0, 5.5, z) * (1 - smoothstep(lm["ear_front"] - 0.4, lm["ear_front"] + 0.2, z)))
        if with_detail:
            facew = ((1 - smoothstep(5.6, 6.9, ax)) * (1 - smoothstep(lm["brow"] + 1.0, lm["brow"] + 3.0, y))
                     * smoothstep(lm["face_z"] - 3.0, lm["face_z"], z))
            dw = np.maximum(facew, ear * 0.9) * r.get("detail", 0.9)
            if r.get("facial"):
                parts0 = facial_parts(p, r)
                grown = np.clip(sum(parts0[k] for layer in r["facial"] for k in layer["parts"]
                                    if layer.get("kind") != "stubble"), 0, 1)
                dw = dw * (1 - 0.8 * grown)
            rgb = rgb * (1 + (detail - 1) * dw)[..., None]
            mh = lm["mouth_half"]
            lips = ((1 - smoothstep(mh - 0.4, mh + 0.3, ax)) * smoothstep(lm["lip_bottom"] - 0.3, lm["lip_bottom"] + 0.05, y)
                    * (1 - smoothstep(lm["lip_top"] - 0.12, lm["lip_top"] + 0.18, y)) * (z > lm["face_z"] + 5.6))
            lipc = np.array(r["lips"]) / 255.0 * (0.75 + 0.25 * detail[..., None])
            rgb = rgb * (1 - 0.55 * lips[..., None]) + lipc * 0.55 * lips[..., None]
            brow = ((1 - smoothstep(4.8, 6.2, ax)) * smoothstep(lm["brow"] - 0.86, lm["brow"] - 0.46, y)
                    * (1 - smoothstep(lm["brow"] + 0.54, lm["brow"] + 1.14, y)) * (z > lm["face_z"] + 2))
            dark = (np.clip((1 - detail) / 0.35, 0, 1) * brow * r.get("brow_strength", 0.6))[..., None]
            rgb = rgb * (1 - dark) + np.array(r["brows"]) / 255.0 * dark
        else:
            lips = 0.0
        # scalp hair
        h = r.get("hair")
        if h:
            cover = hair_cover(p, r)
            strands = value_noise3(sym * np.array([1.0, 0.5, 1.0]), h.get("strand", 0.12), 41)
            base = np.array(h["colour"]) / 255.0
            hair = base * (0.9 + 0.18 * (0.5 + 0.5 * strands))[..., None]
            grey = h.get("grey", 0.0)
            if grey:
                g = smoothstep(0.55 - grey, 0.85 - grey, value_noise3(sym, 0.07, 43))
                if "grey_sides" in h:          # greyer at the temples and sides
                    g = np.clip(g + h["grey_sides"] * smoothstep(3.0, 6.5, ax), 0, 1)
                hair = hair * (1 - g[..., None]) + (np.array(h.get("grey_colour", (180, 176, 170))) / 255.0) * g[..., None]
            o = (cover * h.get("opacity", 1.0))[..., None]
            rgb = rgb * (1 - o) + hair * o
        # facial hair layers
        parts = facial_parts(p, r)
        for layer in r.get("facial", ()):
            area = np.clip(sum(parts[k] for k in layer["parts"]), 0, 1) * (1 - lips if with_detail else 1)
            strands = value_noise3(sym * np.array([1.0, 0.35, 1.0]), layer.get("strand", 0.09), 21)
            if layer.get("kind") == "stubble":
                dots = smoothstep(0.1, 0.6, value_noise3(sym, 0.045, 23))
                dens = area * layer["density"] * (0.55 + 0.45 * dots)
            else:
                edge = np.where(area < 0.95, 0.65 + 0.35 * value_noise3(sym, 0.18, 3), 1.0)
                dens = np.clip(area * (0.78 + 0.22 * strands), 0, 1) * edge * layer["density"]
            col = np.array(layer["colour"]) / 255.0 * (0.86 + 0.14 * strands[..., None])
            if layer.get("light"):
                col = col * (1 - layer["light"] * 0.5 * (1 + value_noise3(sym, 0.06, 29)))[..., None] \
                    + (np.array(layer.get("light_colour", (205, 200, 192))) / 255.0) * (layer["light"] * 0.5 * (1 + value_noise3(sym, 0.06, 29)))[..., None]
            rgb = rgb * (1 - dens[..., None]) + col * dens[..., None]
        return rgb

    rgb = colour_at(pos, True)
    if shared.any():                       # a texel two places of the scalp sample: the mean of both colours
        other = colour_at(alt[shared][None, :, :], False)[0]
        mine = colour_at(pos[shared][None, :, :], False)[0]
        rgb[shared] = 0.5 * (mine + other)
    # pad: every texel no skin triangle covers takes the nearest skin colour (wrapping, as the sampler does), so the
    # mips and the filter never pull the eye atlas or a background into the skin; the eye, teeth and mouth atlas
    # (covered by their own triangles) keeps the previous texture's pixels
    out = np.clip(dilate(np.where(skin[..., None], rgb, 0.0), skin, 4 * W), 0, 1)
    out = np.where((cov & ~skin)[..., None], src, out)
    if r.get("eyes"):
        # brown eyes for a brown-eyed coach on a model whose 2004 eye is blue (luminance kept, the white untouched)
        eye_tris = np.array([t[0] not in main and float(np.mean(head["P"][t][:, 2])) > 13.0 for t in T])
        eye = cov & ~skin & eye_tris[np.maximum(tri, 0)]
        lum = src[..., 0] * 0.299 + src[..., 1] * 0.587 + src[..., 2] * 0.114
        # the iris is where the atlas is blue (a blue 2004 eye on a brown-eyed coach): those texels take his colour
        blue = src[..., 2] - np.maximum(src[..., 0], src[..., 1] * 0.9)
        iris = (eye * smoothstep(0.0, 0.08, blue)).astype(float)
        target = np.array(r["eyes"]) / 255.0
        tl = target[0] * 0.299 + target[1] * 0.587 + target[2] * 0.114
        recol = np.clip(target[None, None, :] * (lum / max(tl, 1e-3))[..., None], 0, 1)
        out = out * (1 - iris[..., None]) + recol * iris[..., None]
    small = out.reshape(H0, scale, W0, scale, 3).mean(axis=(1, 3))
    rgba = np.concatenate([np.clip(np.rint(small * 255), 0, 255), np.full((H0, W0, 1), 255.0)], -1).astype(np.uint8)
    return rgba


# --- commands -----------------------------------------------------------------------------------------------------

def _pins_row(team: str) -> dict:
    return next(r for r in mc.pins()["teams"] if r["team"] == team)


def cmd_geometry(args) -> int:
    for team in args.teams:
        recipe = RECIPES[team]
        row = _pins_row(team)
        scene = Scene(read_archive(args.retail, row["archive"]), row["archive"])
        donor = None
        if "body" in recipe:
            name = f"c{recipe['body']['donor']}.iff"
            donor = Scene(read_archive(args.retail, name), name)
            if recipe["body"].get("via"):
                via = f"c{recipe['body']['via']}.iff"
                donor = (Scene(read_archive(args.retail, via), via), donor)
        doc, _new = make_geometry(scene, recipe, donor)
        # spaced separators: plain short text tokens (the release gate refuses long whitespace-free runs as blobs)
        text = json.dumps(doc, separators=(", ", ": ")) + "\n"
        path = mc.geometry_path(team)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(team, row["archive"], {s["name"]: (len(s["positions"]), len(s["normals"])) for s in doc["shapes"]},
              f"{len(text)} bytes")
    return 0


def cmd_head(args) -> int:
    for team in args.teams:
        recipe = RECIPES[team]["head"]
        row = _pins_row(team)
        scene = Scene(read_archive(args.retail, row["archive"]), row["archive"])
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{args.detail_ref}:data/nfl2k5_modern_coaches/{team}/head.png"],
                              check=True, capture_output=True).stdout
        detail = np.asarray(Image.open(io.BytesIO(blob)).convert("RGBA"))
        rgba = paint_head(scene.shapes["coachHeadGrp1"], detail, recipe)
        Image.fromarray(rgba).save(mc.art_path(team, "head"), optimize=True)
        print(team, "head.png", rgba.shape)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("geometry"); g.add_argument("--retail", required=True); g.add_argument("--teams", default="")
    h = sub.add_parser("head"); h.add_argument("--retail", required=True); h.add_argument("--teams", default="")
    h.add_argument("--detail-ref", default="0a2bcf5c")
    a = p.parse_args(argv)
    a.teams = [t for t in a.teams.split(",") if t] or [t for t in RECIPES if (a.command != "head" or "head" in RECIPES[t])
                                                         and (a.command != "geometry" or set(RECIPES[t]) & {"bald", "body"})]
    return {"geometry": cmd_geometry, "head": cmd_head}[a.command](a)


if __name__ == "__main__":
    raise SystemExit(main())
