#!/usr/bin/env python3
"""co1: author the 2026 head coaches' sideline look for the 32 coach models (cNN.iff, chunk 0).

Inputs (read only): a folder of cNN.iff files copied out of the user's own disc (the retail art is the layout and
shading template; nothing retail is written to the repository), the 2026 team logos (data/nfl2k5_scorebug_mnf/logos),
the 2026 official colours (data/nfl2k5_scorebug_sprite/team_colors_official_2026.json) and, for the faces, private
reference headshots (never copied into the repository or a pack).

Per team it writes, at 4x (master4x/) and area-downscaled to the native slot (native/):
  shirt.png      128x128  polo / quarter-zip in the 2026 top colour, trims in the accent, cap patch (u 0.83-0.99,
                          v 0-0.17, used by hatShader1) in the cap colour; fabric folds keep the retail shading
  jacket.png     128x128  full-zip sideline jacket, same colours
  logo.png        64x64   the 2026 team logo where the chest mark quad samples (v 0.41-1.11); the retail maker
                          mark is gone
  accessories.png 128x64  an unbranded black headset (the 2004 Motorola earcup and band marks are gone); the shoe
                          and clipboard keep their retail pixels
  head.png       256x128  (faces step) the 2026 coach's face painted onto the coach head layout

  python3 tools/b77/co1_coach_art.py apparel --coach-dir DIR --out ART [--teams KC,PHI]
  python3 tools/b77/co1_coach_art.py faces --coach-dir DIR --refs REFS --portraits PORTRAITS --yunet MODEL --out ART
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
MASTER = 4

# 2026 team (nflverse) -> coach archive code (the coach record +0x18 body id, the team's 2K5 asset code).
CODES = {"ARI": "00", "ATL": "01", "BAL": "02", "BUF": "03", "CAR": "04", "CHI": "05", "CIN": "06", "DAL": "07",
         "DEN": "08", "DET": "09", "GB": "10", "IND": "11", "JAX": "12", "KC": "13", "MIA": "14", "MIN": "15",
         "NE": "16", "NO": "17", "NYG": "18", "NYJ": "19", "LV": "20", "PHI": "21", "PIT": "22", "LAR": "23",
         "LAC": "24", "SF": "25", "SEA": "26", "TB": "27", "TEN": "28", "WAS": "29", "CLE": "30", "HOU": "37"}
LOGO_FILE = {"WAS": "wsh"}

# The look each coach wears (top, trim, cap), from the 2026 official colours. Where a 2025-26 sideline or headshot
# frame shows the coach's choice (art-refs index apparel_notes) that colour wins; otherwise the club's primary.
APPAREL = {
    "ARI": ("#000000", "#97233F", "#000000", "dark jacket and cap (2026 preseason arrival frame)"),
    "ATL": ("#000000", "#A71930", "#000000", "black Falcons polo (headshot)"),
    "BAL": ("#24135F", "#000000", "#000000", "purple Ravens jacket (2026 Week 3 pregame)"),
    "BUF": ("#00338D", "#C60C30", "#00338D", "blue Bills hoodie or polo, blue cap (2025 practice)"),
    "CAR": ("#000000", "#0085CF", "#000000", "black Panthers polo (headshot)"),
    "CHI": ("#0B162A", "#E64100", "#0B162A", "club primary (no sideline frame)"),
    "CIN": ("#000000", "#FB4F14", "#000000", "black Bengals polo (headshot)"),
    "CLE": ("#311D00", "#FF3C00", "#000000", "brown Browns hoodie (2026 Week 2), black cap"),
    "DAL": ("#002244", "#869397", "#002244", "navy Cowboys jacket and pullover (2025 Week 7)"),
    "DEN": ("#0A2343", "#FC4C02", "#0A2343", "navy Broncos windbreaker (2026 Week 5)"),
    "DET": ("#0076B6", "#B0B7BC", "#0076B6", "blue Lions polo (headshot)"),
    "GB": ("#203731", "#FFB612", "#203731", "club primary (no sideline frame)"),
    "HOU": ("#021018", "#EB0028", "#021018", "navy Texans polo (headshot)"),
    "IND": ("#013369", "#FFFFFF", "#000000", "blue Colts hoodie, black cap (2025 pregame)"),
    "JAX": ("#000000", "#006778", "#000000", "black Jaguars quarter-zip (headshot)"),
    "KC": ("#E31837", "#FFB612", "#E31837", "red Chiefs jacket, red cap (2025 Weeks 11 and 16)"),
    "LV": ("#000000", "#C8C7C7", "#000000", "black Raiders hoodie and cap (tunnel frames)"),
    "LAC": ("#0080C6", "#FFC20E", "#0080C6", "blue Chargers polo (headshot)"),
    "LAR": ("#003594", "#FFD100", "#003594", "royal blue hoodie (sideline frame)"),
    "MIA": ("#008E97", "#FC4C02", "#008E97", "club primary (no frame)"),
    "MIN": ("#4F2683", "#FFC62F", "#4F2683", "club primary (no frame)"),
    "NE": ("#002244", "#C60C30", "#002244", "club primary (press frames only)"),
    "NO": ("#000000", "#D3BC8D", "#000000", "club secondary black with old gold (headshot is a white polo)"),
    "NYG": ("#0B2265", "#A71930", "#0B2265", "royal-blue Giants jacket (2026 Week 5 warm-up)"),
    "NYJ": ("#115740", "#FFFFFF", "#115740", "club primary (headshot is a black striped polo)"),
    "PHI": ("#004851", "#A2AAAD", "#000000", "club primary (headshot is a black polo)"),
    "PIT": ("#000000", "#FFB612", "#000000", "black Steelers jacket and black cap (2026 at NE)"),
    "SF": ("#FFFFFF", "#AA0000", "#AA0000", "white 49ers pullover, red cap (2026 Week 3)"),
    "SEA": ("#002244", "#69BE28", "#002244", "navy Seahawks polo and pullover (2026 headshot, locker room)"),
    "TB": ("#A71930", "#322F2B", "#322F2B", "red Buccaneers polo (headshot)"),
    "TEN": ("#0C2340", "#4495D2", "#0C2340", "navy Titans hoodie (2026 Week 2)"),
    "WAS": ("#5A1414", "#FFB612", "#5A1414", "burgundy Commanders polo (headshot)"),
}
# shirt texture patch the cap samples (hatShader1 u 0.83-0.99, v 0.003-0.172 on every coach)
CAP_BOX = (104, 0, 128, 24)
# chest mark quad (shirtLogoShader1 / jacketLogoShader1 sample v 0.41..1.11 across the full width)
LOGO_BOX = (6, 28, 58, 62)


def hexrgb(text):
    text = text.lstrip("#")
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def coach_scene(path):
    from mod_editor.core import nfl2k5_modern_metlife as mm
    import nfl_txtr as tx
    raw = Path(path).read_bytes()
    chunk = tx.parse_chunks(raw)[0]
    rec, decoded = mm._scene(raw, chunk)
    return rec, decoded


def textures(rec, decoded):
    """{material name: (row, rgba)} of the coach scene's P8 textures (first material that maps each)."""
    from mod_editor.core import nfl2k5_modern_metlife as mm
    out = {}
    for row in rec["embedded_textures"]:
        rgba, _ = mm.read_p8(decoded, int(rec["system_bytes"]), row)
        for name in row.get("mapped_material_names") or ():
            out[name] = (row, rgba)
    return out


def up(rgba, k=MASTER):
    im = Image.fromarray(rgba, "RGBA")
    return np.asarray(im.resize((im.width * k, im.height * k), Image.BICUBIC), dtype=np.float64)


def area_down(master, k=MASTER):
    h, w = master.shape[0] // k, master.shape[1] // k
    m = master.astype(np.float64)
    a = m[..., 3:4] / 255.0
    pre = np.concatenate([m[..., :3] * a, m[..., 3:4]], axis=-1)
    pre = pre.reshape(h, k, w, k, 4).mean(axis=(1, 3))
    alpha = pre[..., 3:4]
    rgb = np.where(alpha > 1e-3, pre[..., :3] / np.maximum(alpha / 255.0, 1e-6), 0)
    return np.uint8(np.clip(np.rint(np.concatenate([rgb, alpha], axis=-1)), 0, 255))


def luma(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def shade_fill(colour, ratio):
    """A flat colour with the retail fabric shading: multiplicative, plus a lift so black and navy keep their folds."""
    c = hexrgb(colour) if isinstance(colour, str) else colour
    r = ratio[..., None]
    lift = 34.0 if luma(c) < 60 else 0.0
    return np.clip(c[None, None, :] * r + lift * (r - 1.0) + (lift * 0.35 if lift else 0), 0, 255)


def garment(rgba_retail, top, trim, cap=None):
    """Recolour one retail garment texture: the dominant fabric colour becomes ``top``; large second colour blocks
    (two-tone 2004 jackets) become ``top`` too; thin saturated accents (stripes, piping) become ``trim``; near-white
    and grey details (zipper, placket) stay neutral; the folds keep the retail shading. Classes are decided on the
    native pixels (so an upsampled edge never reads as a stripe) and the colours are painted at 4x."""
    from scipy import ndimage
    n = rgba_retail[..., :3].astype(np.float64)
    nl = luma(n) + 1.0
    nmx, nmn = n.max(axis=-1), n.min(axis=-1)
    nsat = (nmx - nmn) / np.maximum(nmx, 1.0)
    nch = n / nl[..., None]
    q = np.round(nch * 6).astype(int)
    keys = q[..., 0] * 10000 + q[..., 1] * 100 + q[..., 2]
    vals, counts = np.unique(keys, return_counts=True)
    dom = vals[np.argmax(counts)]
    dom_chroma = np.array([dom // 10000, (dom // 100) % 100, dom % 100], dtype=np.float64) / 6
    body = np.linalg.norm(nch - dom_chroma[None, None, :], axis=-1) < 0.22
    neutral = (~body) & (nsat < 0.18)
    accent = (~body) & ~neutral
    big = ndimage.binary_opening(~body, structure=np.ones((3, 3))) & ~body
    # the shaded fringe of a big block is the block, not a stripe
    big |= accent & ndimage.binary_dilation(big, structure=np.ones((5, 5)))
    accent &= ~big
    neutral &= ~big
    # a trim is a line: accent specks (no side 8 native pixels long) are fold shading, painted as the garment
    alab, acount = ndimage.label(accent)
    for i, sl in enumerate(ndimage.find_objects(alab), start=1):
        if sl is not None and max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) < 8:
            big[sl] |= alab[sl] == i
            accent[sl] &= alab[sl] != i
    labels, count = ndimage.label(big)

    def grow(mask):
        return np.repeat(np.repeat(mask, MASTER, axis=0), MASTER, axis=1)

    m = up(rgba_retail)
    rgb = m[..., :3]
    lum = luma(rgb) + 1.0
    B, A, N = grow(body), grow(accent), grow(neutral)
    L = grow(labels)
    ratio = np.ones_like(lum)
    if B.any():
        ratio[B] = np.clip(lum[B] / np.median(lum[B]), 0.45, 1.6)
    for i in range(1, count + 1):
        sel = L == i
        ratio[sel] = np.clip(lum[sel] / np.median(lum[sel]), 0.45, 1.6)
    out = np.empty_like(m)
    out[..., 3] = m[..., 3]
    top_c = shade_fill(top, ratio)
    trim_med = np.median(lum[A]) if A.any() else np.median(lum)
    trim_c = shade_fill(trim, np.clip(lum / trim_med, 0.5, 1.5))
    neu_c = np.repeat(np.clip(lum, 0, 255)[..., None], 3, axis=-1)
    out[..., :3] = np.where(A[..., None], trim_c, np.where(N[..., None], neu_c, top_c))
    if cap is not None:
        x0, y0, x1, y1 = (v * MASTER for v in CAP_BOX)
        region = lum[y0:y1, x0:x1]
        cr = np.clip(region / np.median(region), 0.7, 1.3)
        out[y0:y1, x0:x1, :3] = shade_fill(cap, cr)
    return np.uint8(np.clip(np.rint(out), 0, 255))


def logo_texture(team):
    path = ROOT / "data/nfl2k5_scorebug_mnf/logos" / f"{LOGO_FILE.get(team, team.lower())}.png"
    with Image.open(path) as im:
        logo = im.convert("RGBA")
    x0, y0, x1, y1 = (v * MASTER for v in LOGO_BOX)
    w, h = x1 - x0, y1 - y0
    bbox = logo.getbbox() or (0, 0, logo.width, logo.height)
    logo = logo.crop(bbox)
    s = min(w / logo.width, h / logo.height)
    lw, lh = max(1, int(round(logo.width * s))), max(1, int(round(logo.height * s)))
    logo = logo.resize((lw, lh), Image.LANCZOS)
    canvas = Image.new("RGBA", (64 * MASTER, 64 * MASTER), (0, 0, 0, 0))
    canvas.alpha_composite(logo, (x0 + (w - lw) // 2, y0 + (h - lh) // 2))
    return np.asarray(canvas, dtype=np.uint8), path


def headset(rgba_retail):
    """The headset half of the accessories atlas (x < 64) becomes a matte black, unbranded headset; the shoe and the
    clipboard keep their retail pixels."""
    from scipy import ndimage
    m = up(rgba_retail)
    out = m.copy()
    w = 64 * MASTER
    region = luma(m[:, :w, :3])
    smooth = ndimage.gaussian_filter(region, 6.0)            # wipes the 2004 marks, keeps the form
    lo, hi = np.percentile(smooth, 2), np.percentile(smooth, 98)
    t = np.clip((smooth - lo) / max(1.0, hi - lo), 0, 1)
    dark = 22 + 70 * t ** 1.2
    out[:, :w, :3] = np.stack([dark, dark, dark * 1.04], axis=-1)
    return np.uint8(np.clip(np.rint(out), 0, 255))


def save(arr, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path, optimize=True)
    return sha(path)


def cmd_apparel(args):
    out = Path(args.out)
    teams = args.teams.split(",") if args.teams else list(CODES)
    manifest = {"schema": "nfl2k5_modern_coaches_art/v1", "items": []}
    for team in teams:
        code = CODES[team]
        rec, decoded = coach_scene(Path(args.coach_dir) / f"c{code}.iff")
        tex = textures(rec, decoded)
        top, trim, cap, why = APPAREL[team]
        has_cap = "hatShader1" in tex
        items = {
            "shirt": garment(tex["shirtShader1"][1], top, trim, cap),
            "jacket": garment(tex["jacketShader1"][1], top, trim),
            "accessories": headset(tex["accessoriesShader1"][1]),
        }
        logo, logo_path = logo_texture(team)
        items["logo"] = logo
        for name, master in items.items():
            mp = out / "master4x" / team / f"{name}.png"
            np_ = out / "native" / team / f"{name}.png"
            save(master, mp)
            native = area_down(master)
            manifest["items"].append({"team": team, "code": code, "texture": name, "master": str(mp.relative_to(out)),
                                      "native": str(np_.relative_to(out)), "native_sha256": save(native, np_),
                                      "size": [native.shape[1], native.shape[0]]})
        manifest.setdefault("teams", {})[team] = {"code": code, "top": top, "trim": trim, "cap": cap,
                                                  "cap_geometry": has_cap, "why": why,
                                                  "logo_source": str(logo_path.relative_to(ROOT))}
        print(team, code, "cap" if has_cap else "no cap", top, trim)
    (out / "apparel_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


# ----------------------------------------------------------------------------------------------- faces
# Retail coach head layout (256x128, every coach): YuNet finds the five landmarks on each retail head texture; the
# detected points are used per coach. Atlas patches the head mesh samples for eyes, teeth, tongue and the inner ear
# (bottom-left and the ear detail at the bottom middle) keep their retail pixels.
ATLAS_BOXES = ((0, 92, 64, 128), (140, 96, 192, 128))
# inside those, the eye, teeth and tongue keep their retail pixels; the lip and inner-ear patches take the new skin
KEEP_BOXES = ((0, 104, 62, 128),)
# median of YuNet's five landmarks over the retail coach heads (native pixels); a detection more than 8 pixels off
# this (YuNet sometimes reads the back-of-head hair panel as a face) falls back to it
CANON = np.array([[44.0, 24.4], [84.4, 24.5], [66.0, 47.6], [46.0, 67.4], [80.3, 67.9]])
# hair colour by eye from each coach's reference photo (None: shaved or bald). The automatic sample in the photo is
# kept in the manifest for comparison; studio backdrops and thin grey hair fool it.
HAIR = {"ARI": (95, 70, 50), "ATL": (92, 86, 80), "BAL": (45, 35, 30), "BUF": (160, 118, 88), "CAR": (30, 25, 22),
        "CHI": (140, 96, 66), "CIN": (62, 46, 36), "CLE": (188, 183, 178), "DAL": (52, 39, 31), "DEN": (168, 163, 158),
        "DET": (150, 145, 140), "GB": (42, 33, 28), "HOU": None, "IND": (56, 41, 31), "JAX": (150, 120, 95),
        "KC": (192, 187, 182), "LAC": (168, 163, 162), "LAR": (130, 95, 66), "LV": (46, 36, 30), "MIA": (110, 85, 66),
        "MIN": (150, 115, 80), "NE": (150, 145, 140), "NO": (56, 43, 35), "NYG": (152, 147, 142), "NYJ": (140, 135, 130),
        "PHI": (46, 36, 30), "PIT": (186, 181, 176), "SEA": (50, 38, 30), "SF": (40, 31, 26), "TB": None, "TEN": None,
        "WAS": None}


def _yunet(model):
    import cv2
    return cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.3, 0.3, 5000)


def _detect(det, bgr, pad=0):
    import cv2
    if pad:
        bgr = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(128, 128, 128))
    det.setInputSize((bgr.shape[1], bgr.shape[0]))
    _, faces = det.detect(bgr)
    if faces is None:
        return None
    f = faces[int(np.argmax(faces[:, 2] * faces[:, 3]))]
    return (f[4:14].reshape(5, 2) - pad).astype(np.float64), (f[:4] - np.array([pad, pad, 0, 0])).astype(np.float64)


def _photo(path, maxw=1600):
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, int(im.height * maxw / im.width)), Image.LANCZOS)
        elif im.width < 512:                    # a 128-pixel portrait: big enough for the detector
            im = im.resize((512, int(im.height * 512 / im.width)), Image.BICUBIC)
        return np.asarray(im, dtype=np.uint8).copy()


def _median_rgb(img, mask):
    return np.median(img[mask].reshape(-1, 3), axis=0) if mask.any() else None


# hair density by eye: close-cropped or thinning hair shows the scalp through it
DENSITY = {"NYJ": 0.45, "PIT": 0.6, "DET": 0.75, "CLE": 0.85, "KC": 0.8, "NE": 0.85, "NYG": 0.9}


def template_hair(template):
    """Hair pixels of one retail head texture (native): far from its cheek skin in chroma or brightness."""
    from scipy import ndimage
    rgb = template[..., :3].astype(np.float64)
    tl = luma(rgb) + 1
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    cheeks = np.zeros(tl.shape, bool)
    for cx, cy in ((50, 40), (78, 40)):
        cheeks |= (xx - cx) ** 2 + (yy - cy) ** 2 < 25
    skin = np.median(rgb[cheeks], axis=0)
    ch = rgb / (rgb.sum(-1, keepdims=True) + 1)
    sk = skin / (skin.sum() + 1)
    hair = (np.linalg.norm(ch - sk, axis=-1) > 0.05) | (np.abs(tl - luma(skin)) > 60)
    return ndimage.binary_opening(hair, structure=np.ones((2, 2)))


def canonical_hair_mask(templates):
    """The shared hair region of the coach head layout: hair in at least 40% of the retail heads (the same UV layout
    on every coach), so a head whose own hair is close to its skin tone still gets a hair region."""
    from scipy import ndimage
    votes = np.mean([template_hair(t) for t in templates], axis=0)
    mask = votes >= 0.4
    for x0, y0, x1, y1 in ATLAS_BOXES:
        mask[y0:y1, x0:x1] = False
    return ndimage.binary_closing(mask, structure=np.ones((3, 3)))


def paint_face(template, photo, det, bald_hint=None, hair_override=None, hair_mask=None, density=1.0):
    """(4x master RGBA, notes) of one coach head: the photo's face warped onto the template's landmarks, the
    template's skin and hair moved to the photo's tones."""
    import cv2
    from scipy import ndimage
    H, W = template.shape[0] * MASTER, template.shape[1] * MASTER
    tpl = up(template)[..., :3]
    t_big = cv2.resize(template[..., :3][:, :, ::-1], (1024, 512), interpolation=cv2.INTER_CUBIC)
    found_t = _detect(det, t_big, pad=128)
    canon = CANON * MASTER
    t_pts = found_t[0] * (W / 1024.0) if found_t is not None else None
    template_landmarks = "detected"
    if t_pts is None or np.abs(t_pts - canon).max() > 8 * MASTER:
        t_pts, template_landmarks = canon, "canonical"
    found_p = _detect(det, photo[:, :, ::-1].copy())
    if found_p is None:
        raise SystemExit("no face in the reference photo")
    p_pts, p_box = found_p
    A, _ = cv2.estimateAffinePartial2D(p_pts.astype(np.float32), t_pts.astype(np.float32), method=cv2.LMEDS)
    warped = cv2.warpAffine(photo, A, (W, H), flags=cv2.INTER_AREA if A[0, 0] < 1 else cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE).astype(np.float64)
    le, re_, nose, ml, mr = t_pts
    eye_mid, mouth_mid = (le + re_) / 2, (ml + mr) / 2
    em = np.linalg.norm(mouth_mid - eye_mid)
    ed = np.linalg.norm(re_ - le)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    # the face oval: brows to chin, cheek to cheek
    cx, cy = (eye_mid[0] + mouth_mid[0]) / 2, eye_mid[1] + em * 0.42
    rx, ry = ed * 0.98, em * 1.32
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    face = np.clip((1.0 - d) / 0.28, 0, 1)
    face = ndimage.gaussian_filter(face, 2.0 * MASTER / 4)
    # skin samples: both cheeks (beside the nose, below the eyes), in template space; the same place in the warp
    cheeks = np.zeros((H, W), bool)
    for ex in (le, re_):
        cxk, cyk = ex[0] * 0.75 + nose[0] * 0.25, (ex[1] + nose[1]) / 2 + em * 0.12
        cheeks |= ((xx - cxk) ** 2 + (yy - cyk) ** 2) < (em * 0.14) ** 2
    forehead = ((xx - eye_mid[0]) ** 2 / (ed * 0.5) ** 2 + (yy - (eye_mid[1] - em * 0.45)) ** 2 / (em * 0.12) ** 2) < 1
    p_skin = _median_rgb(warped, cheeks)
    # game exposure: studio headshots are lit brighter than the 2004 heads; a bright skin is compressed toward the
    # retail heads' level (cheek luma about 165) so a pale coach does not wash out in the stadium light
    pl = luma(p_skin)
    if pl > 170:
        k = (170 + 0.4 * (pl - 170)) / pl
        p_skin = p_skin * k
        warped = warped * k
    t_skin = _median_rgb(tpl, cheeks)
    # hair in the photo: the band above the forehead, inside the head box (not backdrop): pixels unlike the skin
    pb = p_box
    hy0, hy1 = int(max(0, pb[1] - pb[3] * 0.25)), int(max(1, pb[1] + pb[3] * 0.05))
    hx0, hx1 = int(pb[0] + pb[2] * 0.25), int(pb[0] + pb[2] * 0.75)
    band = photo[hy0:hy1, hx0:hx1].reshape(-1, 3).astype(np.float64)
    border = np.concatenate([photo[:8].reshape(-1, 3), photo[:, :8].reshape(-1, 3), photo[:, -8:].reshape(-1, 3)])
    bg = np.median(border.astype(np.float64), axis=0)
    p_skin_photo = p_skin
    not_bg = np.linalg.norm(band - bg, axis=1) > 30
    not_skin = np.linalg.norm(band / (band.sum(1, keepdims=True) + 1) - p_skin_photo / (p_skin_photo.sum() + 1), axis=1) > 0.035
    hairpix = band[not_bg & not_skin]
    bald = len(hairpix) < 0.12 * max(1, len(band)) if bald_hint is None else bald_hint
    hair_sampled = np.median(hairpix, axis=0) if len(hairpix) else None
    hair = np.array(hair_override, dtype=np.float64) if hair_override is not None else (hair_sampled if hair_sampled is not None else p_skin * 0.6)
    # template classes: skin-like vs hair, by chroma distance to the template skin
    tl = luma(tpl) + 1
    tch = tpl / (tpl.sum(-1, keepdims=True) + 1)
    sch = t_skin / (t_skin.sum() + 1)
    skin_t = np.linalg.norm(tch - sch, axis=-1) < 0.05
    skin_t &= np.abs(tl - luma(t_skin)) < 70
    if hair_mask is not None:
        from scipy import ndimage as _nd
        own = _nd.binary_opening(template_hair(template), structure=np.ones((4, 4)))   # no freckle specks
        for x0, y0, x1, y1 in ATLAS_BOXES:
            own[y0:y1, x0:x1] = False
        own &= ~(((np.mgrid[0:H // MASTER, 0:W // MASTER][1] - CANON[:, 0].mean()) / 34.0) ** 2
                 + ((np.mgrid[0:H // MASTER, 0:W // MASTER][0] - 50.0) / 40.0) ** 2 < 1)    # never the face itself
        both = (hair_mask | own) if bald else hair_mask      # a bald head loses every retail hair pixel
        hair_t = np.asarray(Image.fromarray(both.astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 127
    else:
        hair_t = ndimage.binary_opening(~skin_t, structure=np.ones((MASTER * 2, MASTER * 2)))
    soft_hair = ndimage.gaussian_filter(hair_t.astype(np.float64), MASTER * 0.8) * density
    out = tpl.copy()
    # skin: the template's own shading, shifted to the photo's tone (additive, so highlights do not blow out)
    skin_new = np.clip(tpl + (p_skin - t_skin)[None, None, :], 0, 255)
    if bald:
        # a shaved head: the photo's skin a shade darker, with only the template's broad form (no hair strands)
        form = ndimage.gaussian_filter(tl, MASTER * 6)
        fr = np.clip(form / np.median(form[skin_t]) if skin_t.any() else 1.0, 0.8, 1.1)[..., None]
        hair_new = np.clip(p_skin[None, None, :] * 0.94 * fr, 0, 255)
    else:
        sl = ndimage.gaussian_filter(tl, MASTER * 1.5)          # strands softened: no static at 256x128
        hl = sl[hair_t]
        hmed = np.median(hl) if hl.size else 128
        hr = np.clip(1.0 + 0.45 * (sl / hmed - 1.0), 0.75, 1.25)[..., None]
        hair_new = np.clip(hair[None, None, :] * hr, 0, 255)
    out = skin_new * (1 - soft_hair[..., None]) + hair_new * soft_hair[..., None]
    # the photo face, its tones pulled 15% toward a gentler contrast around its own skin
    oval = face > 0.5
    ts, ps = luma(tpl)[oval].std(), luma(warped)[oval].std()
    contrast = float(np.clip(ts / max(ps, 1.0), 0.85, 1.4))
    pw = p_skin[None, None, :] + (warped - p_skin[None, None, :]) * contrast
    out = out * (1 - face[..., None]) + pw * face[..., None]
    for x0, y0, x1, y1 in ATLAS_BOXES:
        sl_ = (slice(y0 * MASTER, y1 * MASTER), slice(x0 * MASTER, x1 * MASTER))
        out[sl_] = skin_new[sl_]
    for x0, y0, x1, y1 in KEEP_BOXES:
        sl_ = (slice(y0 * MASTER, y1 * MASTER), slice(x0 * MASTER, x1 * MASTER))
        out[sl_] = tpl[sl_]
    rgba = np.concatenate([np.clip(out, 0, 255), np.full((H, W, 1), 255.0)], axis=-1)
    notes = {"skin_rgb": [int(v) for v in p_skin], "hair_rgb": None if bald else [int(v) for v in hair],
             "hair_sampled_rgb": None if hair_sampled is None else [int(v) for v in hair_sampled],
             "bald": bool(bald), "template_skin_rgb": [int(v) for v in t_skin],
             "template_landmarks": template_landmarks, "face_contrast": round(contrast, 3)}
    return np.uint8(np.rint(rgba)), notes


def cmd_faces(args):
    out = Path(args.out)
    det = _yunet(args.yunet)
    teams = args.teams.split(",") if args.teams else list(CODES)
    photos = json.loads(Path(args.photos).read_text(encoding="utf-8"))
    bald = set((args.bald or "").split(",")) - {""}
    hairy = set((args.hair or "").split(",")) - {""}
    manifest_path = out / "faces_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {"schema": "nfl2k5_modern_coaches_faces/v1", "teams": {}}
    heads = {}
    for team, code in CODES.items():
        rec, decoded = coach_scene(Path(args.coach_dir) / f"c{code}.iff")
        heads[team] = textures(rec, decoded)["headShader1"][1]
    hair_mask = canonical_hair_mask(list(heads.values()))
    save(np.dstack([np.repeat(hair_mask[..., None].astype(np.uint8) * 255, 3, -1), np.full(hair_mask.shape + (1,), 255, np.uint8)]),
         out / "hair_mask_native.png")
    for team in teams:
        code = CODES[team]
        template = heads[team]
        photo = _photo(photos[team])
        hint = True if (team in bald or HAIR.get(team, 0) is None) else (False if (team in hairy or HAIR.get(team)) else None)
        master, notes = paint_face(template, photo, det, hint, HAIR.get(team), hair_mask, DENSITY.get(team, 1.0))
        mp, np_ = out / "master4x" / team / "head.png", out / "native" / team / "head.png"
        save(master, mp)
        native = area_down(master)
        manifest["teams"][team] = dict(notes, code=code, master=str(mp.relative_to(out)), native=str(np_.relative_to(out)),
                                       native_sha256=save(native, np_), reference=Path(photos[team]).name)
        print(team, code, notes)
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


# ----------------------------------------------------------------------------------------------- sideline staff
# The sideline assistants (gamedata.iff scene coach_asst, material SIDELINE, no embedded texture) wear the club's
# ``coachshirt`` texture from its eight team packages ({code}{h,a}{d,r}{n,s}.iff, 256x256 P8, six mips): one design
# for the d packages (polo), one for the r packages (jacket); home/away and night/sun carry the same picture.
SIDELINE_DESIGNS = (("d", "sideline_dry"), ("r", "sideline_rain"))


def package_texture(path_or_bytes, name="coachshirt"):
    """(rgba, row) of a named standalone P8 TXTR chunk in a team package."""
    import nfl_txtr as tx
    raw = Path(path_or_bytes).read_bytes() if not isinstance(path_or_bytes, (bytes, bytearray)) else bytes(path_or_bytes)
    for chunk in tx.parse_chunks(raw):
        if chunk.kind != "TXTR":
            continue
        decoded, _ = tx.decode_chunk(raw, chunk)
        texture = tx.parse_texture(decoded, chunk)
        if texture.name == name:
            rgba = np.frombuffer(tx.texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)
            return rgba.copy(), texture
    raise SystemExit(f"no {name} texture")


def cmd_sideline(args):
    out = Path(args.out)
    teams = args.teams.split(",") if args.teams else list(CODES)
    manifest = {"schema": "nfl2k5_modern_coaches_sideline/v1", "items": []}
    for team in teams:
        code = CODES[team]
        top, trim, _cap, _why = APPAREL[team]
        for weather, name in SIDELINE_DESIGNS:
            rgba, _texture = package_texture(Path(args.package_dir) / f"{code}h{weather}n.iff")
            master = garment(rgba, top, trim)
            mp, np_ = out / "master4x" / team / f"{name}.png", out / "native" / team / f"{name}.png"
            save(master, mp)
            native = area_down(master)
            manifest["items"].append({"team": team, "code": code, "texture": name, "native_sha256": save(native, np_)})
        print(team, code, "sideline staff", top, trim)
    (out / "sideline_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apparel")
    a.add_argument("--coach-dir", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--teams")
    f = sub.add_parser("faces")
    f.add_argument("--coach-dir", required=True)
    f.add_argument("--photos", required=True, help="JSON {team: private reference photo path}")
    f.add_argument("--yunet", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--teams")
    f.add_argument("--bald", help="teams whose coach has a shaved or bald head (overrides the automatic hair test)")
    f.add_argument("--hair", help="teams whose coach has hair (overrides the automatic hair test)")
    sl = sub.add_parser("sideline")
    sl.add_argument("--package-dir", required=True, help="folder of {code}h{d,r}n.iff team packages from the user's disc")
    sl.add_argument("--out", required=True)
    sl.add_argument("--teams")
    args = ap.parse_args(argv)
    if args.cmd == "sideline":
        return cmd_sideline(args)
    if args.cmd == "apparel":
        return cmd_apparel(args)
    if args.cmd == "faces":
        return cmd_faces(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
