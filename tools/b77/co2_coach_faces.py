#!/usr/bin/env python3
"""co2: the 2026 head coaches' faces, a strict second round, on the retail body each coach now wears.

Per coach (PARAMS): the body (cNN) he wears, his hair colour or a shaved head, and small fixes. The face of his
official 2026 headshot (private reference, never copied into the repository or a pack) is moved onto that model's
retail head texture (read from the user's own disc copy, --coach-dir of cNN.iff files):

* 468 MediaPipe face-mesh landmarks on the photo and on the retail head texture; a thin-plate-spline warp puts his eyes,
  brows, nose and mouth on the mesh features of the 2004 head;
* the photo's lighting removed (a robust quadratic fit of Lab L over his skin, and the broad left-right asymmetry of
  side-lit photos), the 2004 artist's low-frequency shading put back;
* one skin tone for the whole head: the photo's tone pulled toward the 2004 palette (light or dark group), the
  template's neck, ears and scalp recoloured to it; beard and brow pixels keep their own hue;
* Poisson blending of the face into the recoloured head (no oval, no seam); the template's closed mouth in place of
  teeth; the template's hair layout recoloured to his hair (or skin for a shaved head);
* the eye, teeth and tongue atlas keeps its retail pixels.

Kansas City (Andy Reid) is not painted: he wears the 2004 Reid model (c21), whose face the Studio derives at build time
from the disc (`reid` writes the authored mask and glasses overlay that ship instead of head.png).

  python3 tools/b77/co2_coach_faces.py faces --coach-dir DIR --refs REFS.json --work WORK --out ART \
      --mp-python VENV/bin/python --mp-model face_landmarker.task [--teams NE,PIT]
  python3 tools/b77/co2_coach_faces.py reid --coach-dir DIR --out ART
  python3 tools/b77/co2_coach_faces.py apparel --coach-dir DIR --out ART [--teams ...]
  python3 tools/b77/co2_coach_faces.py measure --gltf-dir DIR      (bodies: chest/belly width and depth, head shape)

REFS.json maps each club to its private headshot path. mediapipe (pip) and the face_landmarker.task model
(storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) are needed
for `faces` only, in any Python (--mp-python); nothing here runs in a Build.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image



def cmd_landmarks_worker(args):
    """Runs in the Python that has mediapipe (imports nothing else heavy): 478 landmarks per image, in pixels, or null."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=args.model), num_faces=1,
        min_face_detection_confidence=0.2, min_face_presence_confidence=0.2))
    out = {}
    for p in args.images:
        im = Image.open(p).convert('RGB')
        r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.asarray(im))))
        out[p] = [[l.x * im.width, l.y * im.height] for l in r.face_landmarks[0]] if r.face_landmarks else None
    Path(args.out).write_text(json.dumps(out))
    return 0


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'landmarks-worker':
    _w = argparse.ArgumentParser()
    _w.add_argument('cmd')
    _w.add_argument('--model', required=True)
    _w.add_argument('out')
    _w.add_argument('images', nargs='+')
    raise SystemExit(cmd_landmarks_worker(_w.parse_args()))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
import co1_coach_art as art  # noqa: E402

M = 4
CTX: dict = {}
# club -> body worn, hair (RGB, by eye from the headshot) or bald, density (thin or close-cropped hair), skin group,
# hide_glasses (the model's glasses geometry hidden by the Studio), extra (paint() keywords: beard_grey / beard_light /
# beard_strength grey a beard, philtrum cleans a smile shadow under the nose, mouth "template" takes the 2004 mouth,
# eye_band takes the 2004 eye band where the photo shows glasses, hair_top fills a balding 2004 crown with hair)
PARAMS = {
    "ARI": {"body": "12", "hair": [95, 70, 50]},
    "ATL": {"body": "01", "hair": [92, 86, 80], "extra": {"beard_grey": 60}},
    "BAL": {"body": "02", "hair": [45, 35, 30], "extra": {"photo_weight": 0.8, "stubble": 1.0}},
    "BUF": {"body": "03", "hair": [70, 52, 40]},
    "CAR": {"body": "09", "hair": [30, 25, 22]},
    "CHI": {"body": "37", "hair": [120, 90, 66]},
    "CIN": {"body": "06", "hair": [62, 46, 36], "extra": {"mouth": "template"}},
    "CLE": {"body": "00", "hair": [188, 183, 178], "density": 0.85},
    "DAL": {"body": "07", "hair": [52, 39, 31], "extra": {"stubble": 1.0}},
    "DEN": {"body": "08", "hair": [168, 163, 158]},
    "DET": {"body": "04", "hair": [150, 145, 140], "density": 0.8, "extra": {"beard_grey": 62}},
    "GB": {"body": "10", "hair": [42, 33, 28], "hide_glasses": True, "extra": {"philtrum": 0.8, "mouth": "template", "stubble": 1.0}},
    "HOU": {"body": "05", "bald": True, "skin_group": "dark"},
    "IND": {"body": "11", "hair": [56, 41, 31]},
    "JAX": {"body": "30", "hair": [150, 120, 95]},
    "KC": {"body": "21", "derived": "retail_recolour"},
    "LV": {"body": "20", "hair": [46, 36, 30], "extra": {"philtrum": 0.5}},
    "LAC": {"body": "24", "hair": [168, 163, 162], "extra": {"eye_band": True, "eye_band_up": 7}},
    "LAR": {"body": "23", "hair": [130, 95, 66], "hide_glasses": True},
    "MIA": {"body": "14", "hair": [110, 85, 66], "extra": {"mouth": "template", "stubble": 1.0}},
    "MIN": {"body": "28", "hair": [78, 58, 44], "extra": {"mouth": "template"}},
    "NE": {"body": "16", "hair": [150, 145, 140], "density": 0.85, "extra": {"beard_grey": 55, "beard_strength": 0.4}},
    "NO": {"body": "17", "hair": [56, 43, 35]},
    "NYG": {"body": "22", "hair": [160, 155, 150], "density": 0.9, "extra": {"mouth": "template"}},
    "NYJ": {"body": "19", "hair": [140, 135, 130], "density": 0.45, "skin_group": "dark", "extra": {"beard_grey": 0, "beard_light": True}},
    "PHI": {"body": "18", "hair": [60, 45, 36]},
    "PIT": {"body": "26", "hair": [186, 181, 176], "density": 0.9, "hide_glasses": True, "extra": {"hair_top": True}},
    "SEA": {"body": "13", "hair": [60, 45, 36], "hide_glasses": True},
    "SF": {"body": "25", "hair": [40, 31, 26]},
    "TB": {"body": "27", "bald": True, "skin_group": "dark", "extra": {"beard_grey": 0, "beard_light": True}},
    "TEN": {"body": "15", "bald": True},
    "WAS": {"body": "29", "bald": True, "hide_glasses": True, "extra": {"beard_grey": 70}}
}


def retail_head(code):
    return CTX['heads'][code]


def load_heads(coach_dir):
    heads = {}
    for p in sorted(Path(coach_dir).glob('c*.iff')):
        rec, decoded = art.coach_scene(p)
        t = art.textures(rec, decoded)
        heads[p.stem[1:]] = t['headShader1'][1]
    CTX['heads'] = heads
    CTX['canon_hair'] = art.canonical_hair_mask([heads[c] for c in sorted(heads) if c in art.CODES.values()])

import cv2  # noqa: E402
from scipy import ndimage  # noqa: E402
from scipy.interpolate import RBFInterpolator  # noqa: E402

FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149,
             150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
OUTER_LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
INNER_LIPS = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
CHEEK_SKIN = [50, 280, 101, 330, 118, 347, 36, 266, 205, 425]
CHIN_SKIN = [152, 175, 199, 32, 262, 136, 365]
FOREHEAD = [151, 9, 108, 337, 69, 299, 104, 333]
ATLAS_BOXES = ((0, 92, 64, 128), (140, 96, 192, 128))
KEEP_BOXES = ((0, 104, 62, 128),)

def landmarks(paths):
    """478 MediaPipe face-mesh points per image (pixels), cached in WORK/landmarks.json; the detection runs in the
    Python that has mediapipe (--mp-python) with the face_landmarker.task model (--mp-model)."""
    cache = CTX['work'] / 'landmarks.json'
    db = json.loads(cache.read_text()) if cache.is_file() else {}
    todo = [str(p) for p in paths if str(p) not in db]
    if todo:
        tmp = CTX['work'] / 'landmarks_tmp.json'
        subprocess.run([CTX['mp_python'], str(Path(__file__).resolve()), 'landmarks-worker', '--model', CTX['mp_model'],
                        str(tmp)] + todo, capture_output=True, check=True, cwd=str(Path(__file__).resolve().parent))
        db.update(json.loads(tmp.read_text())); cache.write_text(json.dumps(db))
    return [np.array(db[str(p)]) if db.get(str(p)) else None for p in paths]

def template_landmarks(code):
    """Landmarks of the model's retail head texture: detected on a 4x copy padded by (256, 128)."""
    p = CTX['work'] / f'tex_up/c{code}_head.png'
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        im = Image.fromarray(retail_head(code)[..., :3]).resize((1024, 512), Image.BICUBIC)
        pad = Image.new('RGB', (1536, 768), (128, 128, 128)); pad.paste(im, (256, 128)); pad.save(p)
    (lm,) = landmarks([p])
    return (lm[:468] - [256, 128]) * (M / 4.0)

def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)

def rgb_of(labim):
    return np.clip(cv2.cvtColor(labim.astype(np.float32), cv2.COLOR_LAB2RGB) * 255.0, 0, 255)

def poly_mask(pts, shape):
    m = np.zeros(shape, np.uint8); cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1); return m.astype(bool)

def quad_fit(L, mask):
    yy, xx = np.mgrid[0:L.shape[0], 0:L.shape[1]].astype(np.float64)
    xs, ys = xx / L.shape[1], yy / L.shape[0]
    A = np.stack([np.ones_like(xs), xs, ys, xs * xs, ys * ys, xs * ys], -1)
    coef, *_ = np.linalg.lstsq(A[mask], L[mask], rcond=None)
    return A @ coef

# 2004 artist palette (Lab of the retail cheeks): light and dark skin groups
def retail_skin_lab(codes):
    vals = []
    for c in codes:
        t = retail_head(c)[..., :3].astype(np.float64)
        lm = template_landmarks(c) / M
        cheek = np.zeros(t.shape[:2], bool)
        yy, xx = np.mgrid[0:t.shape[0], 0:t.shape[1]]
        for i in CHEEK_SKIN:
            cheek |= (xx - lm[i, 0]) ** 2 + (yy - lm[i, 1]) ** 2 < 9
        vals.append(np.median(lab(t)[cheek], axis=0))
    return np.median(vals, axis=0)

def paint(code, photo_path, *, skin_group, hair=None, bald=False, density=1.0, photo_weight=0.45, lift=0.0, beard_keep=1.0, eye_band=False, sym=0.85, beard_grey=None, philtrum=0.0, beard_light=False, beard_strength=1.0, mouth='photo', hair_top=False, eye_band_up=0, stubble=0.0, hairline_rows=0):
    T = retail_head(code)
    H, W = T.shape[0] * M, T.shape[1] * M
    tpl = art.up(T)[..., :3]
    tl = template_landmarks(code)
    photo = cv2.cvtColor(cv2.imread(str(photo_path)), cv2.COLOR_BGR2RGB).astype(np.float64)
    (pl,) = landmarks([photo_path]); pl = pl[:468]
    # warp: template pixel -> photo pixel (thin-plate spline on the 468 points)
    sub = np.arange(0, 468)
    rbf = RBFInterpolator(tl[sub], pl[sub], kernel='thin_plate_spline', smoothing=2.0, degree=1)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    face = poly_mask(tl[FACE_OVAL], (H, W))
    bb = ndimage.binary_dilation(face, iterations=12 * M)
    pts = np.c_[xx[bb], yy[bb]]
    mp_ = np.zeros((H, W, 2), np.float32)
    mp_[bb] = rbf(pts).astype(np.float32)
    warped = cv2.remap(photo.astype(np.float32), mp_[..., 0], mp_[..., 1], cv2.INTER_AREA if False else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE).astype(np.float64)
    # side light: the broad (6 px) luminance of the warped photo made left-right symmetric about the face midline
    xm = float((tl[33, 0] + tl[263, 0]) / 2)
    Lw = lab(warped)
    low = ndimage.gaussian_filter(Lw[..., 0], 6 * M)
    mx = np.clip(np.rint(2 * xm - xx), 0, W - 1).astype(int)
    mirrored = low[yy.astype(int), mx]
    face0 = poly_mask(tl[FACE_OVAL], (H, W))
    both_in = face0 & face0[yy.astype(int), mx]
    wsym = ndimage.gaussian_filter(both_in.astype(np.float64), 3 * M) * sym
    Lw[..., 0] += (mirrored - low) / 2 * wsym
    warped = rgb_of(Lw)
    # skin regions (template space)
    def disc(idx, r):
        m = np.zeros((H, W), bool)
        for i in idx:
            m |= (xx - tl[i, 0]) ** 2 + (yy - tl[i, 1]) ** 2 < (r * M) ** 2
        return m
    cheeks = disc(CHEEK_SKIN, 3.0) & face
    skin_zone = (disc(CHEEK_SKIN, 5.0) | disc(FOREHEAD, 4.0) | disc(CHIN_SKIN, 3.0)) & face
    Lp = lab(warped); Lt = lab(tpl)
    # photo lighting: quadratic fit of L over its skin (pixels near its own cheek tone), removed
    ps = np.median(Lp[cheeks], axis=0)
    skinlike = skin_zone & (np.abs(Lp[..., 0] - ps[0]) < 30) & (np.hypot(Lp[..., 1] - ps[1], Lp[..., 2] - ps[2]) < 14)
    SP = quad_fit(Lp[..., 0], skinlike)
    for _ in range(2):                                   # robust: drop features (brows, stubble) and refit
        keep = skinlike & (np.abs(Lp[..., 0] - SP) < 8)
        if keep.sum() > 500:
            SP = quad_fit(Lp[..., 0], keep)
    ts = np.median(Lt[cheeks], axis=0)
    tskin = face & (np.abs(Lt[..., 0] - ts[0]) < 18)
    ST = quad_fit(Lt[..., 0], tskin)
    # target skin: the photo tone pulled toward the 2004 palette of the group
    ref = SKIN_REF[skin_group]
    tgt = ref + photo_weight * (ps - ref)
    tgt[0] += lift
    # photo face in target tone with the template's broad shading
    out_face = Lp.copy()
    out_face[..., 0] = Lp[..., 0] - SP + ts[0] + (ST - ts[0]) + (tgt[0] - ts[0])
    chroma = np.hypot(Lp[..., 1], Lp[..., 2]); wch = np.clip(chroma / max(1.0, 0.35 * float(np.hypot(ps[1], ps[2]))), 0, 1)[..., None]
    dark_w = np.clip(1 - (ps[0] - Lp[..., 0] - 6) / 20, 0, 1)[..., None]          # beard/brow pixels keep their own hue
    out_face[..., 1:] = Lp[..., 1:] + (tgt[1:] - ps[1:])[None, None, :] * wch * dark_w
    # specular: compress anything brighter than skin by 60%
    over = out_face[..., 0] - (ST + tgt[0] - ts[0])
    out_face[..., 0] -= np.clip(over - 4, 0, None) * 0.6
    # recoloured template (the whole head in the target tone)
    rec = Lt.copy()
    rec[..., 0] = Lt[..., 0] - ts[0] + tgt[0]
    rec[..., 1] = Lt[..., 1] - ts[1] + tgt[1]
    rec[..., 2] = Lt[..., 2] - ts[2] + tgt[2]
    # hair of the template layout (outside the face): recolour or shave
    own = art.template_hair(T)
    own = ndimage.binary_opening(own, structure=np.ones((2, 2)))
    own = own | CTX['canon_hair']
    own = ndimage.binary_fill_holes(ndimage.binary_closing(own, structure=np.ones((4, 4))))
    own[0] |= own[1]; own[-1] |= own[-2]; own[:, 0] |= own[:, 1]; own[:, -1] |= own[:, -2]     # the edge rows the opening lost
    for x0, y0, x1, y1 in ATLAS_BOXES:
        own[y0:y1, x0:x1] = False
    hair_t = np.asarray(cv2.resize(own.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)).astype(bool)
    hair_t &= ~ndimage.binary_erosion(face, iterations=6 * M)
    if hair_top:                                    # a model whose 2004 coach was balding: the crown becomes hair
        hair_t |= (yy < tl[10, 1] - 3 * M) & (xx < 190 * M)
    soft = ndimage.gaussian_filter(hair_t.astype(np.float64), M * 0.9)
    if bald:
        form = ndimage.gaussian_filter(Lt[..., 0], M * 6)
        shaved = rec.copy(); shaved[..., 0] = tgt[0] + 0.35 * (form - np.median(form[tskin])) - 4
        shaved[..., 1] = tgt[1]; shaved[..., 2] = tgt[2]
        rec = rec * (1 - soft[..., None]) + shaved * soft[..., None]
    elif hair is not None:
        hl = lab(np.array(hair, np.float64)[None, None, :])[0, 0]
        sl = ndimage.gaussian_filter(Lt[..., 0], M * 1.2)
        hmed = np.median(sl[hair_t]) if hair_t.any() else 40
        hr = hair_t.copy()
        hcol = np.empty_like(rec)
        detail = 0.85 if hl[0] < 45 else (0.6 if hl[0] < 65 else 0.35)
        hcol[..., 0] = hl[0] + detail * np.clip(sl - hmed, -25, 25); hcol[..., 1] = hl[1] + 0.3 * (Lt[..., 1] - np.median(Lt[..., 1][hair_t])); hcol[..., 2] = hl[2] + 0.3 * (Lt[..., 2] - np.median(Lt[..., 2][hair_t]))
        k = soft[..., None] * density
        rec = rec * (1 - k) + hcol * k
    rec_rgb = rgb_of(rec)
    face_rgb = rgb_of(out_face)
    # beard/stubble keep: nothing special, the photo carries it (beard_keep scales the photo's chroma deviation)
    # Poisson blend the face (shrunk oval) into the recoloured template
    fm = ndimage.binary_erosion(face, iterations=2 * M)
    # no teeth: the inner-lip polygon takes the template there
    if beard_grey is not None or philtrum:
        lower = poly_mask(tl[[132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 425, 266, 2, 36, 205, 93]], (H, W))
        skinL = ST + tgt[0] - ts[0]
        if beard_light:
            darkness = np.clip((out_face[..., 0] - skinL - 2) / 10, 0, 1) * ndimage.gaussian_filter(lower.astype(np.float64), M)
        else:
            darkness = np.clip((skinL - out_face[..., 0] - 2) / 12, 0, 1) * ndimage.gaussian_filter(lower.astype(np.float64), M)
        darkness = darkness * beard_strength
        if beard_grey is not None:
            out_face[..., 1] -= (out_face[..., 1]) * darkness * 0.85
            out_face[..., 2] -= (out_face[..., 2]) * darkness * 0.85
            if not beard_light:
                out_face[..., 0] += (beard_grey - out_face[..., 0]) * darkness * 0.5
        if philtrum:
            ph = poly_mask(tl[[2, 98, 203, 40, 37, 0, 267, 270, 423, 327]], (H, W))
            pw = ndimage.gaussian_filter(ph.astype(np.float64), M) * philtrum
            out_face[..., 0] += np.clip(skinL - out_face[..., 0], 0, None) * pw
            out_face[..., 1:] += (tgt[1:] - out_face[..., 1:]) * pw[..., None]
    if stubble:
        # stubble and beard as hair, not mud: in the lower face the photo's warm chroma around the skin tone is halved,
        # and pixels darker than the skin go toward a low-contrast dark grey
        lower2 = poly_mask(tl[[132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 425, 266, 2, 36, 205, 93]], (H, W))
        zw = ndimage.gaussian_filter(lower2.astype(np.float64), 2 * M) * stubble
        skinL2 = ST + tgt[0] - ts[0]
        out_face[..., 1:] = tgt[1:] + (out_face[..., 1:] - tgt[1:]) * (1 - 0.5 * zw)[..., None]
        dk = np.clip((skinL2 - out_face[..., 0] - 1) / 10, 0, 1) * zw
        out_face[..., 1:] = out_face[..., 1:] * (1 - 0.8 * dk)[..., None] + tgt[1:] * 0.2 * dk[..., None] * 0
        out_face[..., 0] = skinL2 - (skinL2 - out_face[..., 0]) * (1 - 0.35 * dk)
    inner = ndimage.binary_dilation(poly_mask(tl[INNER_LIPS], (H, W)), iterations=M)
    outer = ndimage.binary_dilation(poly_mask(tl[OUTER_LIPS], (H, W)), iterations=M)
    src_lab = out_face.copy()
    ow = ndimage.gaussian_filter(outer.astype(np.float64), M * 0.8)
    src_lab[..., 1] = src_lab[..., 1] - (src_lab[..., 1] - tgt[1]) * 0.3 * ow     # lips: 30% less red than the photo
    src_lab[..., 2] = src_lab[..., 2] - (src_lab[..., 2] - tgt[2]) * 0.45 * ow
    src = rgb_of(src_lab)
    rec_m = rec.copy()                                  # the 2004 mouth: its lips half way to the skin tone
    rec_m[..., 1] -= (rec_m[..., 1] - tgt[1]) * 0.5 * ow
    rec_m[..., 2] -= (rec_m[..., 2] - tgt[2]) * 0.5 * ow
    rec_mouth = rgb_of(rec_m)
    iw = ndimage.gaussian_filter((outer if mouth == 'template' else inner).astype(np.float64), M * 0.5)[..., None]
    src = src * (1 - iw) + rec_mouth * iw                                           # no teeth: the template's closed mouth
    if eye_band:
        band = (yy > (tl[[70, 300], 1].mean() - (eye_band_up * M if eye_band_up else -1 * M))) & (yy < tl[[50, 280], 1].mean()) & face
        bw = ndimage.gaussian_filter(band.astype(np.float64), M * 3.0)[..., None]
        src = src * (1 - bw) + rec_rgb * bw
    ys, xs = np.where(fm)
    center = (int((xs.min() + xs.max() + 1) // 2), int((ys.min() + ys.max() + 1) // 2))
    blended = cv2.seamlessClone(np.uint8(np.clip(src, 0, 255)), np.uint8(np.clip(rec_rgb, 0, 255)),
                                np.uint8(fm) * 255, center, cv2.NORMAL_CLONE).astype(np.float64)
    out = blended
    if hairline_rows and hair is not None:
        # a 2004 model whose coach was receding: his hair down to this row across the face columns
        ear = ((xx / M - 137.5) / 10.0) ** 2 + ((yy / M - 36.0) / 20.0) ** 2 < 1
        crown = ((yy < hairline_rows * M) & (xx < 190 * M)) | ((xx > 104 * M) & (xx < 190 * M) & (yy < 44 * M) & ~ear)
        crown &= ~ndimage.binary_erosion(face, iterations=6 * M) | (yy < hairline_rows * M)
        hl_mask = ndimage.gaussian_filter(crown.astype(np.float64), 1.5 * M) * density
        out = out * (1 - hl_mask[..., None]) + rgb_of(hcol) * hl_mask[..., None]
    tpl_rgb = tpl
    for x0, y0, x1, y1 in ATLAS_BOXES:
        sl_ = (slice(y0 * M, y1 * M), slice(x0 * M, x1 * M)); out[sl_] = rec_rgb[sl_]
    for x0, y0, x1, y1 in KEEP_BOXES:
        sl_ = (slice(y0 * M, y1 * M), slice(x0 * M, x1 * M)); out[sl_] = tpl_rgb[sl_]
    rgba = np.concatenate([np.clip(out, 0, 255), np.full((H, W, 1), 255.0)], -1)
    return np.uint8(np.rint(rgba)), dict(photo_skin_lab=[round(float(v), 1) for v in ps], target_lab=[round(float(v), 1) for v in tgt])

LIGHT = ['01', '02', '03', '04', '07', '08', '09', '10', '12', '13', '14', '15', '16', '17', '18', '20', '21', '22', '23', '24', '25', '26', '27', '28', '30']
DARK = ['00', '05', '50', '51']
SKIN_REF = {}
def init_refs():
    SKIN_REF['light'] = retail_skin_lab(LIGHT); SKIN_REF['dark'] = retail_skin_lab(DARK)


# ----------------------------------------------------------------------------------------------- commands
def cmd_faces(args):
    CTX.update(work=Path(args.work), mp_python=args.mp_python, mp_model=args.mp_model)
    CTX['work'].mkdir(parents=True, exist_ok=True)
    load_heads(args.coach_dir)
    init_refs()
    refs = json.loads(Path(args.refs).read_text(encoding='utf-8'))
    teams = args.teams.split(',') if args.teams else [t for t in PARAMS if not PARAMS[t].get('derived')]
    landmarks([refs[t] for t in teams])
    for team in teams:
        p = PARAMS[team]
        kw = dict(skin_group=p.get('skin_group', 'light'), hair=tuple(p['hair']) if p.get('hair') else None,
                  bald=p.get('bald', False), density=p.get('density', 1.0), **p.get('extra', {}))
        master, notes = paint(p['body'], refs[team], **kw)
        art.save(master, Path(args.out) / 'master4x' / team / 'head.png')
        print(team, 'c' + p['body'], art.save(art.area_down(master), Path(args.out) / 'native' / team / 'head.png'), notes)
    return 0


def cmd_reid(args):
    """Kansas City: the authored recolour mask (R weight, G class*80: 1 hair, 2 brows, 3 moustache) and glasses overlay
    for the 2004 Reid head (c21). Both are shapes and a drawing, not retail pixels."""
    from PIL import ImageDraw
    from scipy import ndimage
    load_heads(args.coach_dir)
    h = retail_head('21')[..., :3].astype(np.float64)
    L = h @ [0.299, 0.587, 0.114]
    sat = (h[..., 0] - h[..., 1]) / (h[..., 0] + 1)
    dark = np.clip((168.0 - L - 22) / 35, 0, 1)
    ging = np.clip((sat - 0.36) / 0.10, 0, 1)
    H, W = L.shape
    yy, xx = np.mgrid[0:H, 0:W]

    def box(x0, y0, x1, y1):
        return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    hair_zone = box(0, 0, 192, 9) | box(0, 0, 14, 26) | box(108, 0, 192, 64) | box(187, 0, 256, 128)
    hair_zone &= ~box(140, 92, 192, 128) & ~box(0, 92, 64, 128)
    hair_zone &= ~(((xx - 137.5) / 9.0) ** 2 + ((yy - 36.0) / 19.0) ** 2 < 1)        # the shadow behind the ear
    lips = (L > 112) & (yy >= 63)
    back = box(192, 0, 256, 128) | box(187, 0, 192, 92)          # the back-of-head panel (not the ear atlas)
    m_hair = np.where(back, 1.0, np.where(hair_zone, dark, 0))
    m_brow = np.where(box(24, 12, 104, 22), np.maximum(dark, ging) * 0.85, 0)
    m_mous = np.where(box(34, 50, 96, 80) & ~lips, np.maximum(ging * np.clip((150 - L) / 40, 0, 1), dark), 0)
    m = ndimage.uniform_filter(np.maximum.reduce([m_hair, m_brow, m_mous]), 2)
    cls = np.zeros((H, W), np.uint8)
    cls[m_hair > 0] = 1
    cls[m_brow > 0] = 2
    cls[m_mous > 0] = 3
    cls = ndimage.grey_dilation(cls, size=3)
    out = Path(args.out) / 'native' / 'KC'
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([np.uint8(np.clip(np.rint(m * 255), 0, 255)), cls * 80, np.zeros((H, W), np.uint8)]),
                    'RGB').save(out / 'head_mask.png')
    S = 8                                                       # dark metal rectangular frames, drawn at 8x
    ov = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    frame = (58, 56, 60, 255)
    for cx in (44.5, 83.5):
        d.rounded_rectangle([(cx - 12.5) * S, 17.5 * S, (cx + 12.5) * S, 31.5 * S], radius=4 * S, outline=frame,
                            width=int(1.6 * S))
    d.line([(57 * S, 22 * S), (71 * S, 22 * S)], fill=frame, width=int(1.4 * S))
    d.line([(96 * S, 21 * S), (134 * S, 26 * S)], fill=frame, width=int(1.5 * S))
    d.line([(0, 21 * S), (32 * S, 21 * S)], fill=frame, width=int(1.5 * S))
    ov.resize((W, H), Image.BOX).save(out / 'head_overlay.png')
    print('KC head_mask.png, head_overlay.png ->', out)
    return 0


def cmd_apparel(args):
    """Shirt, jacket, logo and headset of each club, from the retail textures of the body it now wears."""
    teams = args.teams.split(',') if args.teams else list(PARAMS)
    for team in teams:
        rec, decoded = art.coach_scene(Path(args.coach_dir) / f"c{PARAMS[team]['body']}.iff")
        t = art.textures(rec, decoded)
        top, trim, cap, _why = art.APPAREL[team]
        items = {"shirt": art.garment(t["shirtShader1"][1], top, trim, cap), "jacket": art.garment(t["jacketShader1"][1], top, trim),
                 "accessories": art.headset(t["accessoriesShader1"][1]), "logo": art.logo_texture(team)[0]}
        for name, master in items.items():
            art.save(master, Path(args.out) / 'master4x' / team / f'{name}.png')
            art.save(art.area_down(master), Path(args.out) / 'native' / team / f'{name}.png')
        print(team, 'c' + PARAMS[team]['body'])
    return 0


def cmd_measure(args):
    """Chest and belly width and depth (torso-weighted vertices) and the head box of every coach model's glTF export
    (Models > Export): heavy bodies have a belly depth of 50+, lean ones under 40."""
    rows = []
    for gl in sorted(Path(args.gltf_dir).glob('c*.gltf')):
        g = json.loads(gl.read_text())
        binb = gl.with_suffix('.bin').read_bytes()
        meshes = {}
        for mi, m in enumerate(g['meshes']):
            node = next(n for n in g['nodes'] if n.get('mesh') == mi)
            names = [g['nodes'][j]['name'].split(':')[-1] for j in g['skins'][node['skin']]['joints']]
            P, J, Wt = [], [], []
            for prim in m['primitives']:
                a = prim['attributes']
                P.append(_acc(g, binb, a['POSITION'])); J.append(_acc(g, binb, a['JOINTS_0'])); Wt.append(_acc(g, binb, a['WEIGHTS_0']))
            P, J, Wt = np.concatenate(P), np.concatenate(J).astype(int), np.concatenate(Wt)
            dom = np.array([names[J[k, np.argmax(Wt[k])]] for k in range(len(J))])
            meshes[m['name']] = (P, dom)
        P, dom = meshes['coachBodyGrp1']
        Hd, hdom = meshes['coachHeadGrp1']
        allp = np.concatenate([P, Hd])
        lo, hi = allp[:, 1].min(), allp[:, 1].max()
        T = P[np.isin(dom, ['waist', 'thorax', 'root'])]
        arms = np.isin(dom, ['lhumerus', 'rhumerus', 'lelbow', 'relbow'])
        wx = 0 if np.ptp(P[arms][:, 0]) > np.ptp(P[arms][:, 2]) else 2
        dz = 2 if wx == 0 else 0

        def band(z0, z1):
            s = (T[:, 1] >= lo + z0 * (hi - lo)) & (T[:, 1] < lo + z1 * (hi - lo))
            return round(float(np.ptp(T[s][:, wx])), 1), round(float(np.ptp(T[s][:, dz])), 1)
        head = Hd[~np.isin(hdom, ['neck', 'thorax'])]
        row = dict(model=gl.stem, chest_w_d=band(0.68, 0.72), belly_w_d=band(0.53, 0.58),
                   head_w=round(float(np.ptp(head[:, wx])), 2), head_h=round(float(np.ptp(head[:, 1])), 2))
        rows.append(row)
        print(row)
    return 0


def _acc(g, binb, i):
    a = g['accessors'][i]
    bv = g['bufferViews'][a['bufferView']]
    n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
    dt = np.dtype({5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}[a['componentType']])
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride', dt.itemsize * n)
    raw = np.frombuffer(binb, np.uint8, count=stride * (a['count'] - 1) + dt.itemsize * n, offset=off)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(a['count'], dt.itemsize * n), strides=(stride, 1)).copy()
    return rows.view(dt).reshape(a['count'], n).astype(np.float64)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('faces')
    for name in ('--coach-dir', '--refs', '--work', '--out', '--mp-python', '--mp-model'):
        f.add_argument(name, required=True)
    f.add_argument('--teams')
    r = sub.add_parser('reid')
    r.add_argument('--coach-dir', required=True)
    r.add_argument('--out', required=True)
    a = sub.add_parser('apparel')
    a.add_argument('--coach-dir', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--teams')
    m = sub.add_parser('measure')
    m.add_argument('--gltf-dir', required=True)
    args = ap.parse_args(argv)
    return {'faces': cmd_faces, 'reid': cmd_reid, 'apparel': cmd_apparel,
            'measure': cmd_measure}[args.cmd](args)


if __name__ == '__main__':
    raise SystemExit(main())
