#!/usr/bin/env python3
"""Author 2026 player faces and portraits from official headshots, each in its own native slot.

Job u1 (2026 modernization pilot). NFL 2K5 keys a player's live head textures (``f####`` face, ``h####`` alternate
face, ``n####`` neck and skull) and his menu portrait on one number, the record's +0x06 photo id. For every player
this tool:

1. finds five facial landmarks (eyes, nose tip, mouth corners) on the headshot with OpenCV's YuNet detector;
2. picks the retail face texture whose skin and hair are closest as the template (the head texture layout is
   shared by every face, so any template fits any slot);
3. warps the photo's face onto the template's own landmarks (a similarity transform), feathers it in, moves the
   template's skin to the photo's skin tone, tints the template's hair to the photo's hair, and keeps the template's
   eye, teeth and mouth atlas patches;
4. crops the portrait (head and shoulders, the headshot's own alpha as the cut-out);
5. gives the player his own slot: a face id that no roster record (main or historic) references and that has a
   portrait, so one pack key maps to exactly one player and no historic team changes.

Everything is authored at 4x (1024 faces, 512 portraits) and area-downscaled to the retail size (256, 128).
Headshots and outputs stay on the private research drive; nothing is written to the repository.

  python3 tools/nfl2k5_team_2026_faces.py headshots --roster roster_2026.csv --team NYG --out HEADSHOTS
  python3 tools/nfl2k5_team_2026_faces.py export --source-xiso RETAIL.iso --out RETAIL_FACES
  python3 tools/nfl2k5_team_2026_faces.py slots --source-xiso RETAIL.iso --pool-own --out SLOTS
  python3 tools/nfl2k5_team_2026_faces.py build --rows roster_rows.csv --headshots HEADSHOTS --retail-faces RETAIL_FACES \
      --slots SLOTS/NYG.json --likeness 6 --yunet face_detection_yunet_2023mar.onnx --spec NYG.json --out FACES
  python3 tools/nfl2k5_team_2026_faces.py fit --faces FACES/manifest.json --source-xiso RETAIL.iso --out FACES_FIT
  python3 tools/nfl2k5_team_2026_faces.py rebuild --faces FACES/faces.json --headshots HEADSHOTS \
      --retail-faces RETAIL_FACES --head-gltf hi_head_o3c115.gltf --yunet face_detection_yunet_2023mar.onnx \
      --spec NYG.json --out FACES_V2        # face fit v2 (tools/nfl2k5_face_fit_v2.py), then fit as above

``slots`` allocates the league's face ids (custom faces are scarce: about six a team when all 32 are rewritten);
``fit`` makes the h and n textures fit their slots' fixed compressed spans (see FIT_LADDER).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MASTER = 4
FACE = 256
PORTRAIT = 128
# The head texture layout is the head mesh's UV layout, shared by every face. Landmark detection on an unwrapped
# texture is unreliable (571 retail faces: median deviation 45 px at 1024), so every template uses the canonical
# positions: the per-landmark median of YuNet's detections over the 571 retail f textures (retail 256 pixels).
CANON_256 = np.array([[93.55, 54.03], [161.82, 53.98], [128.98, 99.65], [98.12, 131.9], [156.97, 132.2]], np.float32)


def _cv2():
    import cv2
    return cv2


class Landmarks:
    def __init__(self, model: str):
        cv2 = _cv2()
        self.det = cv2.FaceDetectorYN.create(model, "", (320, 320), 0.6, 0.3, 5000)

    def find(self, bgr: np.ndarray, maxw: int = 1200):
        cv2 = _cv2()
        s = min(1.0, maxw / bgr.shape[1])
        small = cv2.resize(bgr, (int(bgr.shape[1] * s), int(bgr.shape[0] * s)))
        self.det.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self.det.detect(small)
        if faces is None:
            return None
        f = faces[int(np.argmax(faces[:, 14]))]
        return (f[4:14].reshape(5, 2) / s).astype(np.float32), float(f[14]), (f[:4] / s)


def headshot_bgr(path: Path):
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    bg.alpha_composite(im)
    return np.array(bg.convert("RGB"))[:, :, ::-1].copy(), np.array(im)


def lab(bgr: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)


def skin_and_hair(bgr: np.ndarray, pts: np.ndarray, alpha: np.ndarray | None = None):
    """Median Lab of the cheeks and of the hair above the forehead (opaque, non-skin pixels only: a short cut
    shows background, a bald head shows skin, and neither is the hair colour)."""
    le, re_, nose, lm, rm = pts
    eye_d = float(np.linalg.norm(re_ - le))
    L = lab(bgr)
    samples = []
    for eye, mouth, sign in ((le, lm, -1), (re_, rm, 1)):
        c = (eye + mouth) / 2 + np.array([sign * 0.18 * eye_d, 0])
        r = max(2, int(0.14 * eye_d))
        x, y = int(c[0]), int(c[1])
        samples.append(L[y - r:y + r, x - r:x + r].reshape(-1, 3))
    # the chin and the forehead too; then drop the studio highlights (the brightest third) before the median
    for c in (np.array([nose[0], (lm[1] + rm[1]) / 2 + 0.35 * eye_d]), np.array([nose[0], le[1] - 0.45 * eye_d])):
        r = max(2, int(0.12 * eye_d))
        x, y = int(c[0]), int(c[1])
        samples.append(L[y - r:y + r, x - r:x + r].reshape(-1, 3))
    allpx = np.concatenate(samples)
    cut = np.percentile(allpx[:, 0], 66)
    skin = np.median(allpx[allpx[:, 0] <= cut], axis=0)
    top = int(((le + re_) / 2)[1] - 0.95 * eye_d)
    x0, x1 = int(le[0]), int(re_[0])
    y0, y1 = max(0, top - int(0.3 * eye_d)), max(1, top + int(0.05 * eye_d))
    band = L[y0:y1, x0:x1].reshape(-1, 3)
    keep = np.ones(len(band), bool)
    if alpha is not None:
        keep &= alpha[y0:y1, x0:x1].reshape(-1) > 200
    keep &= np.linalg.norm(band - skin, axis=1) > 18
    hair = np.median(band[keep], axis=0) if keep.sum() > 20 else skin
    return skin, hair


def tone_from_skin(skin_lab: np.ndarray) -> int:
    """2K5 skin tone 0 (lightest) .. 5 (darkest) from the cheek lightness (OpenCV L* scaled 0..255)."""
    l_star = float(skin_lab[0]) * 100.0 / 255.0
    for tone, limit in enumerate((63.0, 55.0, 48.0, 41.0, 34.0)):
        if l_star >= limit:
            return tone
    return 5


def shift_colours(tpl: np.ndarray, tpl_skin: np.ndarray, tpl_hair: np.ndarray, skin: np.ndarray, hair: np.ndarray,
                  size: int) -> np.ndarray:
    """Move a template's skin to ``skin`` and its hair to ``hair`` with a smooth, soft per-pixel shift (no hard
    region edges): each pixel weighs how close it is to the template's skin versus its hair."""
    cv2 = _cv2()
    tl = lab(tpl)
    ds = np.linalg.norm(tl - tpl_skin, axis=2)
    dh = np.linalg.norm(tl - tpl_hair, axis=2)
    sig = 22.0
    ws = np.exp(-(ds / sig) ** 2)
    wh = np.exp(-(dh / sig) ** 2)
    w = ws / np.maximum(ws + wh, 1e-6)
    w = cv2.GaussianBlur(w.astype(np.float32), (0, 0), size / 128.0)
    shift = w[..., None] * (skin - tpl_skin)[None, None, :] + (1 - w[..., None]) * (hair - tpl_hair)[None, None, :]
    shift = cv2.GaussianBlur(shift.astype(np.float32), (0, 0), size / 96.0)
    return to_bgr(tl + shift)


def to_bgr(lab_img: np.ndarray) -> np.ndarray:
    cv2 = _cv2()
    return cv2.cvtColor(np.clip(lab_img, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def compose_face(photo: np.ndarray, ppts: np.ndarray, tpl: np.ndarray, tpts: np.ndarray, skin: np.ndarray,
                 hair: np.ndarray, tpl_skin: np.ndarray, tpl_hair: np.ndarray, size: int):
    cv2 = _cv2()
    M, _ = cv2.estimateAffinePartial2D(ppts, tpts, method=cv2.LMEDS)
    warped = cv2.warpAffine(photo, M, (size, size), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    cx = float(tpts[:, 0].mean())
    eye_y = float(tpts[:2, 1].mean())
    mouth_y = float(tpts[3:, 1].mean())
    eye_d = float(np.linalg.norm(tpts[1] - tpts[0]))
    mask = np.zeros((size, size), np.float32)
    # forehead to the jaw line: beards, which most 2026 players wear, belong to the photo
    cv2.ellipse(mask, (int(cx), int((eye_y + mouth_y) / 2 + 0.04 * eye_d)),
                (int(eye_d * 1.06), int((mouth_y - eye_y) * 1.62)), 0, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), eye_d * 0.17)
    tpl2 = shift_colours(tpl, tpl_skin, tpl_hair, skin, hair, size)
    out = tpl2.astype(np.float32) * (1 - mask[..., None]) + warped.astype(np.float32) * mask[..., None]
    atlas = np.zeros((size, size), np.float32)
    atlas[int(size * 0.77):, :int(size * 0.53)] = 1.0
    out = out * (1 - atlas[..., None]) + tpl.astype(np.float32) * atlas[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def compose_skull(tpl: np.ndarray, skin: np.ndarray, hair: np.ndarray, tpl_skin: np.ndarray, tpl_hair: np.ndarray,
                  size: int) -> np.ndarray:
    """The neck and skull texture: the same soft skin/hair shift as the face."""
    return shift_colours(tpl, tpl_skin, tpl_hair, skin, hair, size)


def portrait(rgba: np.ndarray, pts: np.ndarray, box, size: int) -> np.ndarray:
    """Head and shoulders like the retail portraits: the face fills about half the height, the chin a little below
    centre, the headshot's own alpha as the cut-out."""
    le, re_, nose, lm, rm = pts
    eye_mid = (le + re_) / 2
    mouth_mid = (lm + rm) / 2
    face_h = float(np.linalg.norm(mouth_mid - eye_mid))
    side = face_h * 4.4
    cx, cy = float(nose[0]), float(eye_mid[1] + face_h * 0.55)
    x0, y0 = int(cx - side / 2), int(cy - side * 0.5)
    img = Image.fromarray(rgba, "RGBA")
    crop = img.crop((x0, y0, x0 + int(side), y0 + int(side)))
    return np.asarray(crop.resize((size, size), Image.LANCZOS), dtype=np.uint8)


def area_down(rgba_u8: np.ndarray, factor: int) -> np.ndarray:
    a = rgba_u8.astype(np.float32) / 255.0
    if a.shape[2] == 3:
        a = np.concatenate([a, np.ones(a.shape[:2] + (1,), np.float32)], axis=2)
    h, w = a.shape[:2]
    pre = a.copy()
    pre[..., :3] *= pre[..., 3:4]
    pre = pre.reshape(h // factor, factor, w // factor, factor, 4).mean(axis=(1, 3))
    al = pre[..., 3:4]
    pre[..., :3] = np.where(al > 1e-4, pre[..., :3] / np.maximum(al, 1e-4), 0)
    return (np.clip(pre, 0, 1) * 255 + 0.5).astype(np.uint8)


def save_png(arr: np.ndarray, path: Path) -> str:
    """RGBA8, non-interlaced (the face importer takes opaque RGBA8 only; the texture pack keeps alpha too)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.full(arr.shape[:2] + (1,), 255, np.uint8)], axis=2)
    Image.fromarray(np.ascontiguousarray(arr), "RGBA").save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def template_features(faces_dir: Path, lm: Landmarks, cache: Path) -> dict:
    """Skin and hair colour of every retail custom face (ids below 9000), sampled at the canonical landmarks."""
    if cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("_schema") == "canon-v1":
            return {k: v for k, v in data.items() if not k.startswith("_")}
    cv2 = _cv2()
    pts = CANON_256 * 4
    feats = {"_schema": "canon-v1"}
    for f in sorted(faces_dir.glob("f*.png")):
        fid = f.stem[1:]
        if not fid.isdigit() or int(fid) >= 9000 or not (faces_dir / f"n{fid}.png").is_file():
            continue
        bgr = cv2.resize(np.array(Image.open(f).convert("RGB"))[:, :, ::-1].copy(), (1024, 1024),
                         interpolation=cv2.INTER_LANCZOS4)
        skin, hair = skin_and_hair(bgr, pts)
        feats[fid] = {"skin": skin.tolist(), "hair": hair.tolist()}
    cache.write_text(json.dumps(feats) + "\n", encoding="utf-8")
    return {k: v for k, v in feats.items() if not k.startswith("_")}


def build(args) -> int:
    cv2 = _cv2()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lm = Landmarks(args.yunet)
    faces_dir = Path(args.retail_faces)
    feats = template_features(faces_dir, lm, out / "template_features.json")
    heads = {m["gsis_id"]: m for m in json.loads((Path(args.headshots) / "headshots.json").read_text(encoding="utf-8"))}
    rows = list(csv.DictReader(Path(args.rows).open(encoding="utf-8")))
    # starters first, the most visible positions first, so a team's share of custom face slots goes to the players
    # the camera shows most (quarterback, receivers, backs, pass rushers, corners)
    importance = {p: i for i, p in enumerate(("QB", "WR", "HB", "TE", "EDGE", "CB", "LB", "DT", "FS", "SS", "T", "G",
                                              "C", "K", "P", "FB"))}
    rows.sort(key=lambda r: (int(r["written_depth_rank"]) > 0, int(r["written_depth_rank"]),
                             importance.get(r["written_position"], 20)))
    slot_doc = json.loads(Path(args.slots).read_text(encoding="utf-8"))
    slots = slot_doc["face_free_with_portrait"]
    portrait_slots = slot_doc.get("portrait_only_free", [])
    likeness = len(rows) if args.likeness is None else args.likeness
    portraits_used = 0
    dreads = {n.strip().casefold() for n in (args.dreads or "").split(",") if n.strip()}
    tone_overrides = {}
    hair_overrides = {}
    if args.spec:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        tone_overrides = spec.get("faces", {}).get("skin_tone_by_eye", {})
        # the automatic hair sample reads shadowed curls as near black (lab 2026-09-23: Dart's light brown hair
        # came out dark); a hair colour set by eye wins
        hair_overrides = spec.get("faces", {}).get("hair_by_eye", {})
        dreads |= {n.casefold() for n in spec.get("faces", {}).get("dreads", [])}
    used_templates = set()
    plan, items = {}, []
    for n, r in enumerate(rows):
        if args.limit is not None and n >= args.limit:
            break
        gid = r["gsis_id"]
        m = heads.get(gid)
        name = f"{r['written_first']} {r['written_last']}"
        if not m or not m.get("file"):
            print(f"  {name}: no headshot, keeps a generic head")
            continue
        photo, rgba = headshot_bgr(Path(args.headshots) / m["file"])
        found = lm.find(photo)
        if found is None or found[1] < 0.8:
            print(f"  {name}: no confident face, keeps a generic head")
            continue
        ppts, score, box = found
        skin, hair = skin_and_hair(photo, ppts, rgba[..., 3])
        if name in hair_overrides:
            h = hair_overrides[name].lstrip("#")
            swatch = np.array([[[int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)]]], np.uint8)  # BGR
            hair = lab(swatch)[0, 0]
        tone = tone_from_skin(skin)
        if name in tone_overrides:
            tone = int(tone_overrides[name])
        # nearest template by skin then hair, preferring templates not used yet
        def dist(fid):
            f = feats[fid]
            return (float(np.linalg.norm(np.array(f["skin"]) - skin)) + 0.5 * float(np.linalg.norm(np.array(f["hair"]) - hair))
                    + (25.0 if fid in used_templates else 0.0))
        if len([v for v in plan.values() if v.get("likeness")]) >= likeness:
            # past the team's share of custom face slots: an exclusive portrait slot and a generic head (the game
            # picks the generic face from the skin tone and the record's face field)
            slot = f"{portrait_slots[portraits_used]:04d}"
            portraits_used += 1
            port = portrait(rgba, ppts, box, PORTRAIT * MASTER)
            master = out / "master4x" / f"portrait_{slot}.png"
            retail = out / "retail" / f"portrait_{slot}.png"
            save_png(port, master)
            items.append({"kind": "player_portrait", "portrait_id": slot, "gsis_id": gid, "player": name,
                          "master": str(master.relative_to(out)), "retail": str(retail.relative_to(out)),
                          "sha256": save_png(area_down(port, MASTER), retail)})
            plan[gid] = {"photo_id": int(slot), "skin_tone": tone, "dreads": int(name.casefold() in dreads),
                         "likeness": False, "player": name, "skin_lab": [round(float(v), 1) for v in skin]}
            print(f"  {name}: portrait slot {slot}, generic head, tone {tone}")
            continue
        template = min(feats, key=dist)
        used_templates.add(template)
        slot = f"{slots[len([v for v in plan.values() if v.get('likeness')])]:04d}"
        size = FACE * MASTER
        tpts = CANON_256 * (size / FACE)
        for fam in ("f", "h"):
            tpl = cv2.resize(np.array(Image.open(faces_dir / f"{fam}{template}.png").convert("RGB"))[:, :, ::-1].copy(),
                             (size, size), interpolation=cv2.INTER_LANCZOS4)
            pts_t = tpts
            tskin = np.array(feats[template]["skin"], np.float32)
            thair = np.array(feats[template]["hair"], np.float32)
            face = compose_face(photo, ppts, tpl, pts_t, skin, hair, tskin, thair, size)[:, :, ::-1]
            master = out / "master4x" / f"{fam}{slot}.png"
            retail = out / "retail" / f"{fam}{slot}.png"
            save_png(np.ascontiguousarray(face), master)
            items.append({"kind": "live_face", "face_id": slot, "family": fam, "gsis_id": gid, "player": name,
                          "template": template, "master": str(master.relative_to(out)),
                          "retail": str(retail.relative_to(out)),
                          "sha256": save_png(area_down(np.ascontiguousarray(face), MASTER)[..., :3].copy(), retail)})
        tpl_n = cv2.resize(np.array(Image.open(faces_dir / f"n{template}.png").convert("RGB"))[:, :, ::-1].copy(),
                           (size, size), interpolation=cv2.INTER_LANCZOS4)
        skull = compose_skull(tpl_n, skin, hair, np.array(feats[template]["skin"], np.float32),
                              np.array(feats[template]["hair"], np.float32), size)[:, :, ::-1]
        master = out / "master4x" / f"n{slot}.png"
        retail = out / "retail" / f"n{slot}.png"
        save_png(np.ascontiguousarray(skull), master)
        items.append({"kind": "live_face", "face_id": slot, "family": "n", "gsis_id": gid, "player": name,
                      "template": template, "master": str(master.relative_to(out)), "retail": str(retail.relative_to(out)),
                      "sha256": save_png(area_down(np.ascontiguousarray(skull), MASTER)[..., :3].copy(), retail)})
        port = portrait(rgba, ppts, box, PORTRAIT * MASTER)
        master = out / "master4x" / f"portrait_{slot}.png"
        retail = out / "retail" / f"portrait_{slot}.png"
        save_png(port, master)
        items.append({"kind": "player_portrait", "portrait_id": slot, "gsis_id": gid, "player": name,
                      "master": str(master.relative_to(out)), "retail": str(retail.relative_to(out)),
                      "sha256": save_png(area_down(port, MASTER), retail)})
        plan[gid] = {"photo_id": int(slot), "skin_tone": tone, "dreads": int(name.casefold() in dreads),
                     "likeness": True, "template": template, "player": name, "skin_lab": [round(float(v), 1) for v in skin],
                     "hair_lab": [round(float(v), 1) for v in hair], "detector_score": round(score, 3)}
        print(f"  {name}: slot {slot}, template {template}, tone {tone}")
    (out / "faces.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "manifest.json").write_text(json.dumps({"schema": "nfl2k5_team_2026_faces/v1", "items": items}, indent=1) + "\n",
                                       encoding="utf-8", newline="\n")
    print(f"faces: {len(plan)} players, {len(items)} textures into {out}")
    return 0


# --------------------------------------------------------------------------------------------- retail faces
def _studio_imports():
    root = Path(__file__).resolve().parents[1]
    for p in (root, root / "tools"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    return root


def cmd_headshots(args) -> int:
    """Download a team's official headshots (nflverse ``headshot_url``) into a private folder with headshots.json,
    the ``--headshots`` input of ``build``. The images are copyrighted press photos: keep them off the repository."""
    import time
    import urllib.request
    root = _studio_imports()
    out = Path(args.out).resolve()
    if out == root or root in out.parents:
        raise SystemExit("headshots are press photos: choose a folder outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    statuses = tuple(s.strip() for s in args.statuses.split(",") if s.strip())
    rows = [r for r in csv.DictReader(Path(args.roster).open(encoding="utf-8"))
            if r["team"] == args.team and r["status"] in statuses]
    index = []
    for r in rows:
        url = (r.get("headshot_url") or "").strip()
        entry = {"gsis_id": r["gsis_id"], "name": r["full_name"], "status": r["status"], "url": url, "file": None}
        dest = out / f"{r['gsis_id']}.png"
        if url and not dest.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
                                                           "Accept": "image/png,image/webp,image/*"})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        import io
                        Image.open(io.BytesIO(response.read())).save(dest)
                    break
                except Exception as exc:  # noqa: BLE001 - retry, then record the miss
                    print(f"  {r['full_name']}: {type(exc).__name__}: {exc}")
                    time.sleep(5 * (attempt + 1))
            time.sleep(args.pause)
        if dest.exists():
            entry["file"] = dest.name
        index.append(entry)
    (out / "headshots.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"headshots: {sum(1 for e in index if e['file'])} of {len(index)} players -> {out}")
    return 0


def cmd_export(args) -> int:
    """Every retail live face texture (f, h, n) as PNG, from the user's own disc (the templates of ``build``)."""
    root = _studio_imports()
    from mod_editor.core.nfl2k5_extended_visual_catalog import load_nfl2k5_extended_visual_catalog
    from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO
    from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache
    out = Path(args.out).resolve()
    if out == root or root in out.parents:
        raise SystemExit("export writes retail textures: choose a folder outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    io = Nfl2k5ExtendedVisualIO(Nfl2k5SourceCache().index(Path(args.source_xiso)))
    written = 0
    for a in load_nfl2k5_extended_visual_catalog().assets_for_kind("live_face"):
        dest = out / f"{a.family}{a.face_id}.png"
        if not dest.exists():
            io.export_original(a, dest)
            written += 1
    print(f"export: {written} new retail face textures -> {out}")
    return 0


# --------------------------------------------------------------------------------------------- face slots
def cmd_slots(args) -> int:
    """The league's face slots, from the disc: which photo ids no record uses, which ones only one team's records
    use (free once that team's 53 records are rewritten), and an allocation of the shared ones across teams.

    A custom face id has live textures (f, h, n) and a portrait; a portrait-only id has just the portrait, and the
    game draws a generic head for it (fallback face 9001 + 100 * skin + face variant). Historic rosters count as
    users, so no historic team changes."""
    from collections import defaultdict
    root = _studio_imports()
    from mod_editor.core import nfl2k5_roster_records as rr
    doc = rr.load_image(args.source_xiso)
    refs: dict[int, set] = defaultdict(set)
    team_of = {}
    for t in doc.teams:
        for p in doc.team_players(t.index):
            team_of[p.offset] = t.abbreviation if t.index < 32 else f"special:{t.abbreviation}"
    for p in doc.players:
        refs[p.record.values["photo_id"]].add(team_of.get(p.offset, "unattached"))
    with rr._outer_image()(args.source_xiso) as archive:
        for e in archive.entries:
            if e.size > 16384 or e.size < 64 or archive.read(e.virtual_offset, 4) != b"ROST":
                continue
            try:
                hist = rr.RosterDocument(archive.read(e.virtual_offset, e.size)[32:])
            except Exception:  # noqa: BLE001 - not a player roster
                continue
            for p in hist.players:
                refs[p.record.values["photo_id"]].add("historic")
    face_report = json.loads((root / "reports/assets/nfl2k5_live_face_texture_compatibility.json").read_text(encoding="utf-8"))
    face_ids = {int(r["face_id"]) for r in face_report["resources"]}
    portrait_report = json.loads((root / "reports/assets/nfl2k5_player_portrait_compatibility.json").read_text(encoding="utf-8"))
    portrait_ids = {int(t["name"]) for t in portrait_report["targets"] if str(t.get("name", "")).isdigit()}
    custom = sorted(i for i in face_ids if i < 9000 and i in portrait_ids)
    portrait_only = sorted(i for i in portrait_ids if i not in face_ids)
    free_custom = [i for i in custom if i not in refs]
    free_portrait = [i for i in portrait_only if i not in refs]
    nfl = [t.abbreviation for t in doc.teams if t.index < 32]
    own_custom = {a: [i for i in custom if refs.get(i) == {a}] for a in nfl}
    own_portrait = {a: [i for i in portrait_only if refs.get(i) == {a}] for a in nfl}
    teams = [t.strip() for t in (args.teams or ",".join(nfl)).split(",") if t.strip()]
    unknown = [t for t in teams if t not in nfl]
    if unknown:
        raise SystemExit(f"not 2004 roster abbreviations: {unknown} (use the disc's, e.g. SD, STL, OAK, ARZ)")
    league = {"schema": "nfl2k5_team_2026_face_slots/v1", "source": str(args.source_xiso),
              "custom_face_ids": len(custom), "portrait_only_ids": len(portrait_only),
              "free_custom": free_custom, "free_portrait_only_count": len(free_portrait),
              "own_custom_by_team": {a: len(v) for a, v in own_custom.items()},
              "own_portrait_only_by_team": {a: len(v) for a, v in own_portrait.items()},
              "allocation_order": teams, "teams": {}}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.pool_own:
        # every listed team's 53 records are rewritten in the same build, so their own ids join the shared pool and
        # the custom faces split evenly
        free_custom = sorted(set(free_custom) | {i for t in teams for i in own_custom[t]})
        free_portrait = sorted(set(free_portrait) | {i for t in teams for i in own_portrait[t]})
        own_custom = {t: [] for t in nfl}
        own_portrait = {t: [] for t in nfl}
        league["pooled"] = True
    for k, team in enumerate(teams):
        share_custom = free_custom[k::len(teams)]
        share_portrait = free_portrait[k::len(teams)]
        slots = {"team": team, "face_free_with_portrait": own_custom[team] + share_custom,
                 "portrait_only_free": own_portrait[team] + share_portrait,
                 "note": "own = ids only this team's records use (free once its 53 records are rewritten); "
                         "the rest is this team's share of the ids no record uses"}
        league["teams"][team] = {"custom": len(slots["face_free_with_portrait"]),
                                 "portrait_only": len(slots["portrait_only_free"])}
        (out / f"{team}.json").write_text(json.dumps(slots, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "league_slots.json").write_text(json.dumps(league, indent=1) + "\n", encoding="utf-8", newline="\n")
    customs = [v["custom"] for v in league["teams"].values()]
    print(f"slots: {len(custom)} custom face ids, {len(free_custom)} available; {len(portrait_only)} portrait-only ids, "
          f"{len(free_portrait)} available; custom faces per team {min(customs)}..{max(customs)} "
          f"(total {sum(customs)}) -> {out}")
    return 0


# --------------------------------------------------------------------------------------------- span fit
# The h (face) and n (neck and skull) textures are DXT1 in VC-LZ streams that must fit the slot's fixed span.
# Photo detail compresses worse than the retail faces, so the fit repeats near-identical 4x4 blocks: identical
# pixels encode to identical DXT1 blocks, which the stream stores as back-references. The eyes, nose and mouth
# weigh eight times more, so they change last.
FIT_LADDER = (0, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024)
FIT_MARGIN = 32


def _fit_weights(family: str) -> np.ndarray:
    yy, xx = np.mgrid[0:64, 0:64] * 4 + 1.5
    if family in ("f", "h"):
        cx = float(CANON_256[:, 0].mean())
        cy = float((CANON_256[:2, 1].mean() + CANON_256[3:, 1].mean()) / 2)
        inside = ((xx - cx) / 64.0) ** 2 + ((yy - cy) / 60.0) ** 2 <= 1.0
        return np.where(inside, 8.0, 1.0)
    return np.ones((64, 64))


def _block_reuse(rgb: np.ndarray, threshold: float, weights: np.ndarray, window_blocks: int):
    blocks = rgb.reshape(64, 4, 64, 4, 3).transpose(0, 2, 1, 3, 4).reshape(4096, 48).astype(np.float32)
    w = weights.reshape(4096)
    replaced = 0
    if threshold > 0:
        for i in range(1, 4096):
            lo = max(0, i - window_blocks)
            d = ((blocks[lo:i] - blocks[i]) ** 2).mean(axis=1)
            j = int(d.argmin())
            if 0 < d[j] and d[j] * w[i] <= threshold:
                blocks[i] = blocks[lo + j]
                replaced += 1
    out = blocks.reshape(64, 64, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(256, 256, 3)
    return np.clip(np.round(out), 0, 255).astype(np.uint8), replaced


def _fit_one(job: tuple) -> dict:
    face_id, family, png, dest, index = job
    _studio_imports()
    import nfl_live_face_texture_png_import as fi
    import nfl_live_face_texture_targets as ft
    from nfl_dxt1 import encode_dxt1_opaque
    from nfl_txtr import compress_vc_lz
    _, _, _, target = fi.select_target(face_id, family, Path(ft.DEFAULT_REPORT))
    _, _, decoded, _ = fi.load_template(Path(index), target)
    rgb = np.asarray(Image.open(png).convert("RGB"))
    bound = target.stored_size - FIT_MARGIN
    window = ((1 << target.offset_bits) - 1) // 8
    weights = _fit_weights(family)

    def size(img: np.ndarray) -> int:
        enc, _ = encode_dxt1_opaque(np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.uint8)], 2).tobytes(),
                                    256, 256)
        stream, _ = compress_vc_lz(decoded[:128] + enc, stream_tag=target.stream_tag, offset_bits=target.offset_bits,
                                   max_encoded_size=None, verify_roundtrip=False)
        return len(stream)

    start = size(rgb)
    best = (0, rgb, 0, start)
    if start > bound:
        lo, hi = 1, len(FIT_LADDER) - 1
        found = None
        while lo <= hi:  # the smallest ladder step that fits
            mid = (lo + hi) // 2
            img, n = _block_reuse(rgb, FIT_LADDER[mid], weights, window)
            s = size(img)
            if s <= bound:
                found, hi = (FIT_LADDER[mid], img, n, s), mid - 1
            else:
                lo = mid + 1
        if found is None:
            return {"face_id": face_id, "family": family, "bound": bound, "start": start, "fits": False}
        best = found
    thr, img, n, s = best
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    save_png(img, Path(dest))
    rms = float(np.sqrt(((img.astype(np.float32) - rgb) ** 2).mean()))
    # the proof: the Studio's own importer takes the written PNG into the slot's span
    try:
        fi.build_import(Path(index), Path(ft.DEFAULT_REPORT), face_id, family, Path(dest))
        importer = "ok"
    except Exception as exc:  # noqa: BLE001 - reported, and the fit counts as failed
        importer = f"{type(exc).__name__}: {exc}"
    return {"face_id": face_id, "family": family, "bound": bound, "start": start, "fitted": s, "threshold": thr,
            "blocks_reused": n, "rms": round(rms, 2), "importer": importer, "fits": importer == "ok"}


def cmd_fit(args) -> int:
    """Fit every h and n texture of a faces folder into its slot's fixed span (see FIT_LADDER). Writes a new faces
    folder whose manifest points at the fitted textures and, for everything unchanged, back at the source folder."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    _studio_imports()
    from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache
    index = str(Nfl2k5SourceCache().index(Path(args.source_xiso)).pack0)
    src_manifest = Path(args.faces).resolve()
    src = src_manifest.parent
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(src_manifest.read_text(encoding="utf-8"))
    jobs = []
    for item in manifest["items"]:
        if item["kind"] == "live_face" and item["family"] in ("h", "n"):
            jobs.append((item["face_id"], item["family"], str(src / item["retail"]),
                         str(out / "retail" / Path(item["retail"]).name), index))
    with ProcessPoolExecutor(args.jobs) as pool:
        results = {(r["face_id"], r["family"]): r for r in pool.map(_fit_one, jobs)}
    failed = [r for r in results.values() if not r["fits"]]
    items = []
    for item in manifest["items"]:
        item = dict(item)
        fit = results.get((item.get("face_id"), item.get("family")))
        if fit and fit["fits"]:
            path = out / "retail" / Path(item["retail"]).name
            item["retail"] = str(path.relative_to(out))
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            item["fit"] = {k: fit[k] for k in ("bound", "start", "fitted", "threshold", "blocks_reused", "rms",
                                               "importer")}
        else:
            item["retail"] = os.path.relpath(src / item["retail"], out)
        item["master"] = os.path.relpath(src / item["master"], out)
        items.append(item)
    (out / "manifest.json").write_text(json.dumps({"schema": manifest["schema"], "fitted_from": str(src_manifest),
                                                   "items": items}, indent=1) + "\n", encoding="utf-8", newline="\n")
    if (src / "faces.json").is_file():
        (out / "faces.json").write_text((src / "faces.json").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    fitted = [r for r in results.values() if r["fits"] and r.get("threshold", 0) > 0]
    worst = max((r["rms"] for r in fitted), default=0.0)
    print(f"fit: {len(results)} h/n textures, {len(fitted)} refitted (worst RMS {worst} of 255), "
          f"{len(failed)} cannot fit; every written texture went through the Studio importer -> {out}")
    for r in failed:
        print(f"  CANNOT FIT {r['family']}{r['face_id']}: {r['start']} bytes for {r['bound']} {r.get('importer', '')}")
    return 1 if failed else 0


# --------------------------------------------------------------------------------------------- coach portrait
def key_out_backdrop(rgb: np.ndarray, floor: int = 200, spread: int = 28) -> np.ndarray:
    """Alpha for a studio portrait on a light seamless backdrop: the light, grey pixels connected to the image
    border are backdrop (0); a two-pixel feather softens the cut."""
    from scipy import ndimage
    lo, hi = rgb.min(axis=2).astype(np.int32), rgb.max(axis=2).astype(np.int32)
    light = (lo >= floor) & (hi - lo <= spread)
    lab, _ = ndimage.label(light)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    backdrop = np.isin(lab, list(border))
    alpha = 1.0 - ndimage.gaussian_filter(backdrop.astype(np.float32), 2.0)
    return (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)


def key_out_border(rgb: np.ndarray, tolerance: float = 18.0) -> np.ndarray:
    """Alpha for a studio portrait on any plain backdrop (the NFL's grey studio backdrop included): the backdrop is
    every pixel within ``tolerance`` (CIE Lab, OpenCV scale) of the photo border's median colour that connects to
    the border, so a light shirt inside the figure stays; a two-pixel feather softens the cut."""
    from scipy import ndimage
    cv2 = _cv2()
    lab_img = cv2.cvtColor(rgb[:, :, ::-1].copy(), cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = rgb.shape[:2]
    band = max(4, int(0.02 * min(h, w)))
    border = np.concatenate([lab_img[:band].reshape(-1, 3), lab_img[-band:].reshape(-1, 3),
                             lab_img[:, :band].reshape(-1, 3), lab_img[:, -band:].reshape(-1, 3)])
    ref = np.median(border, axis=0)
    near = np.linalg.norm(lab_img - ref[None, None, :], axis=2) <= tolerance
    lab_ids, _ = ndimage.label(near)
    edge = set(np.unique(np.concatenate([lab_ids[0], lab_ids[-1], lab_ids[:, 0], lab_ids[:, -1]]))) - {0}
    backdrop = np.isin(lab_ids, list(edge))
    alpha = 1.0 - ndimage.gaussian_filter(backdrop.astype(np.float32), 2.0)
    return (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)


def key_out_grabcut(rgb: np.ndarray, face_box, iterations: int = 8) -> np.ndarray:
    """Alpha for a portrait on a busy or graded backdrop (club photos with gradients, vignettes and logos): OpenCV
    GrabCut seeded with the face as sure foreground; a thin frame and the backdrop colours that touch the frame
    (Lab distance to the frame's colours) as sure background; the head and a shoulders-wide body block below it as
    the probable person, everything else as probable background. A two-pixel feather softens the cut."""
    from scipy import ndimage
    cv2 = _cv2()
    h, w = rgb.shape[:2]
    fx, fy, fw, fh = (float(v) for v in face_box)
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[int(max(0, fy - 0.65 * fh)):int(min(h, fy + 1.1 * fh)),
         int(max(0, fx - 0.3 * fw)):int(min(w, fx + 1.3 * fw))] = cv2.GC_PR_FGD                 # the head
    mask[int(min(h, fy + 1.0 * fh)):h, int(max(0, fx - 1.4 * fw)):int(min(w, fx + 2.4 * fw))] = cv2.GC_PR_FGD  # body
    # sure background: the frame, and the frame's colours wherever they connect to it
    lab_img = cv2.cvtColor(rgb[:, :, ::-1].copy(), cv2.COLOR_BGR2LAB).astype(np.float32)
    band = max(3, int(0.012 * min(h, w)))
    frame = np.zeros((h, w), bool)
    frame[:band], frame[:, :band], frame[:, -band:] = True, True, True
    samples = lab_img[frame][:: max(1, int(frame.sum() // 4000))]
    from scipy.spatial import cKDTree
    dist, _ = cKDTree(samples).query(lab_img.reshape(-1, 3), k=1)
    near = (dist.reshape(h, w) <= 10.0)
    ids, _ = ndimage.label(near | frame)
    touching = set(np.unique(ids[frame])) - {0}
    sure_bg = np.isin(ids, list(touching)) & (mask != cv2.GC_PR_FGD)
    mask[sure_bg | frame] = cv2.GC_BGD
    mask[int(fy + 0.1 * fh):int(fy + 0.95 * fh), int(fx + 0.15 * fw):int(fx + 0.85 * fw)] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(rgb[:, :, ::-1].copy(), mask, None, bgd, fgd, iterations, cv2.GC_INIT_WITH_MASK)
    person = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    ids, n = ndimage.label(person)
    if n > 1:                                   # keep the piece holding the face
        keep = ids[int(fy + 0.5 * fh), int(fx + 0.5 * fw)]
        person = ids == keep if keep else person
    person = ndimage.binary_fill_holes(person)
    alpha = ndimage.gaussian_filter(person.astype(np.float32), 2.0)
    return (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)


def cmd_coach(args) -> int:
    """A head coach's photo (his record's identity code names the portrait the Coach Matchup screen shows, e.g.
    7018 for the Giants' retail coach) framed like the retail coach portraits: the head fills the frame, the chin
    near the bottom, the backdrop keyed out. Writes a faces-style manifest for ``nfl2k5_team_2026_art.py project``."""
    lm = Landmarks(args.yunet)
    with Image.open(args.photo) as image:
        rgb = np.array(image.convert("RGB"))
    found = lm.find(rgb[:, :, ::-1].copy())
    if found is None:
        raise SystemExit("no face found in the coach photo")
    pts = found[0]
    le, re_, nose, ml, mr = pts
    eye_mid, mouth_mid = (le + re_) / 2, (ml + mr) / 2
    face_h = float(np.linalg.norm(mouth_mid - eye_mid))
    side = face_h * float(args.frame)
    cx, cy = float(nose[0]), float(eye_mid[1] + face_h * float(args.centre))
    if args.key == "grabcut":
        alpha = key_out_grabcut(rgb, found[2])
    elif args.key == "border":
        alpha = key_out_border(rgb, float(args.key_tolerance))
    else:
        alpha = key_out_backdrop(rgb)
    rgba = np.concatenate([rgb, alpha[..., None]], axis=2)
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    crop = Image.fromarray(rgba, "RGBA").crop((x0, y0, x0 + int(side), y0 + int(side)))
    out = Path(args.out)
    master = np.asarray(crop.resize((PORTRAIT * MASTER, PORTRAIT * MASTER), Image.LANCZOS), dtype=np.uint8)
    mpath, rpath = out / "master4x" / f"portrait_{args.portrait_id}.png", out / "retail" / f"portrait_{args.portrait_id}.png"
    save_png(master, mpath)
    item = {"kind": "player_portrait", "portrait_id": args.portrait_id, "player": args.name, "role": "head coach",
            "master": str(mpath.relative_to(out)), "retail": str(rpath.relative_to(out)),
            "sha256": save_png(area_down(master, MASTER), rpath), "source": str(args.photo)}
    (out / "manifest.json").write_text(json.dumps({"schema": "nfl2k5_team_2026_faces/v1", "items": [item]}, indent=1)
                                       + "\n", encoding="utf-8", newline="\n")
    print(f"coach portrait {args.portrait_id} ({args.name}) -> {out}")
    return 0


# --------------------------------------------------------------------------------------------- face fit v2 (fx)
def _v2_worker_init(head_gltf, calibration):
    root = _studio_imports()
    import nfl2k5_face_fit_v2 as v2
    v2.use_head(head_gltf)
    if calibration:
        v2.set_calibration(calibration)


def _v2_features(job):
    gsis, headshot, yunet = job
    import nfl2k5_face_fit_v2 as v2
    if not headshot or not Path(headshot).is_file():
        return gsis, None
    bgr, rgba = headshot_bgr(Path(headshot))
    found = Landmarks(yunet).find(bgr)
    if found is None:
        return gsis, None
    f = v2.photo_features(rgba, found[0])
    return gsis, {"skin": f["skin"].tolist(), "beard": f["beard"], "hair": None if f["hair"] is None else f["hair"].tolist()}


def _v2_one(job):
    gsis, slot, template, tone, name, hair_override, headshot, retail_faces, yunet = job
    import nfl2k5_face_fit_v2 as v2
    found = None
    rgba = None
    if headshot and Path(headshot).is_file():
        bgr, rgba = headshot_bgr(Path(headshot))
        found = Landmarks(yunet).find(bgr)
    imgs, method, checks = v2.build_player(rgba, found, Path(retail_faces), template, tone, hair_override)
    return gsis, slot, template, name, method, checks, imgs


def cmd_rebuild(args) -> int:
    """Rebuild a team's custom faces with face fit v2 (tools/nfl2k5_face_fit_v2.py) in the same slots with the same
    templates ``build`` gave them: the headshot projected onto the head mesh and relit, open mouths closed, skin in
    the roster tone's range; method B (template plus the photo's beard and brows) or C (the template) for a photo
    that fails the checks. Writes master4x/, retail/, manifest.json (as ``build``), faces.json and checks.json; then
    run ``fit`` on the manifest."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    cv2 = _cv2()
    out = Path(args.out).resolve()
    root = _studio_imports()
    if out == root or root in out.parents:
        raise SystemExit("faces are built from press photos: choose a folder outside the repository")
    plan = json.loads(Path(args.faces).read_text(encoding="utf-8"))
    hair_by_eye = {}
    if args.spec:
        for name, hx in json.loads(Path(args.spec).read_text(encoding="utf-8")).get("faces", {}).get("hair_by_eye", {}).items():
            hx = hx.lstrip("#")
            sw = np.array([[[int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)]]], np.uint8)
            hair_by_eye[name] = cv2.cvtColor(sw, cv2.COLOR_RGB2LAB)[0, 0].astype(float).tolist()
    jobs = []
    for gsis, p in plan.items():
        if not p.get("likeness"):
            continue
        jobs.append((gsis, f"{int(p['photo_id']):04d}", p["template"], p.get("skin_tone"), p["player"],
                     hair_by_eye.get(p["player"]), str(Path(args.headshots) / f"{gsis}.png"), args.retail_faces,
                     args.yunet))
    for d in ("master4x", "retail"):
        (out / d).mkdir(parents=True, exist_ok=True)
    items, checks_all = [], {}
    with ProcessPoolExecutor(args.jobs, initializer=_v2_worker_init, initargs=(args.head_gltf, args.calibration)) as pool:
        if args.templates:
            # the template is chosen again: same roster skin tone, nearest skull hair and beard, brown irises for
            # tones 2 and darker, each once a team (build's choice went by colour samples alone)
            import nfl2k5_face_fit_v2 as v2
            table = json.loads(Path(args.templates).read_text(encoding="utf-8"))["templates"]
            feats = dict(pool.map(_v2_features, [(j[0], j[6], j[8]) for j in jobs]))
            used, rechosen = set(), []
            for n, j in enumerate(jobs):
                f = feats.get(j[0])
                if f is None:
                    used.add(j[2])
                    continue
                hair = j[5] if j[5] is not None else f["hair"]
                t = v2.choose_template(table, j[3], hair, f["beard"], f["skin"], used)
                used.add(t)
                if t != j[2]:
                    rechosen.append(f"{j[4]}: {j[2]} -> {t}")
                jobs[n] = (j[0], j[1], t) + j[3:]
            print(f"templates: {len(rechosen)} of {len(jobs)} chosen again")
        for gsis, slot, template, name, method, checks, imgs in pool.map(_v2_one, jobs):
            for fam in ("f", "h", "n"):
                retail = out / "retail" / f"{fam}{slot}.png"
                item = {"kind": "live_face", "face_id": slot, "family": fam, "gsis_id": gsis, "player": name,
                        "template": template, "method": method, "retail": str(retail.relative_to(out))}
                if method == "C":           # the nearest retail face as it is
                    retail.write_bytes((Path(args.retail_faces) / f"{fam}{template}.png").read_bytes())
                    item["sha256"] = hashlib.sha256(retail.read_bytes()).hexdigest()
                else:
                    master = out / "master4x" / f"{fam}{slot}.png"
                    save_png(np.ascontiguousarray(imgs[fam]), master)
                    item["master"] = str(master.relative_to(out))
                    item["sha256"] = save_png(area_down(np.ascontiguousarray(imgs[fam]), MASTER)[..., :3].copy(), retail)
                items.append(item)
            checks_all[slot] = {"player": name, "gsis_id": gsis, "method": method, **checks}
            plan[gsis] = dict(plan[gsis], method=method, template=template)
    items.sort(key=lambda i: (i["face_id"], i["family"]))
    (out / "manifest.json").write_text(json.dumps({"schema": "nfl2k5_team_2026_faces/v1", "face_fit": "v2", "items": items},
                                                  indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "faces.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "checks.json").write_text(json.dumps(checks_all, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    methods = {m: sum(1 for c in checks_all.values() if c["method"] == m) for m in "ABC"}
    print(f"rebuild: {len(checks_all)} faces (A {methods['A']}, B {methods['B']}, C {methods['C']}) -> {out}")
    for slot, c in sorted(checks_all.items()):
        if c["method"] != "A":
            print(f"  {c['method']} {slot} {c['player']}: {json.dumps({k: v for k, v in c.items() if k not in ('player', 'gsis_id', 'method')})}")
    return 0


def cmd_templates(args) -> int:
    """The template table for ``rebuild --templates``: every retail custom face with its roster skin tone (the retail
    roster's skin field of the records that use it), cheek skin, skull hair, iris, beard and bare-skull flag."""
    from collections import Counter
    _studio_imports()
    from mod_editor.core import nfl2k5_roster_records as rr
    import nfl2k5_face_fit_v2 as v2
    doc = rr.load_image(args.source_xiso)
    tones = {}
    for p in doc.players:
        pid = p.record.values["photo_id"]
        if pid < 9000:
            tones.setdefault(f"{pid:04d}", Counter())[p.record.skin & 7] += 1
    table = v2.template_features(Path(args.retail_faces), {k: c.most_common(1)[0][0] for k, c in tones.items()})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": "nfl2k5_team_2026_face_templates/v1", "templates": table}, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"templates: {len(table)} retail faces -> {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    co = sub.add_parser("coach")
    co.add_argument("--photo", required=True, help="the coach's studio portrait (light backdrop)")
    co.add_argument("--portrait-id", required=True, help="the coach record's identity code, e.g. 7018")
    co.add_argument("--name", required=True)
    co.add_argument("--yunet", required=True)
    co.add_argument("--frame", default=4.0, help="frame side in eye-to-mouth heights")
    co.add_argument("--centre", default=0.3, help="frame centre below the eyes, in eye-to-mouth heights")
    co.add_argument("--key", choices=("light", "border", "grabcut"), default="light",
                    help="light: a white or near-white backdrop (the Giants' photo); border: any plain backdrop, "
                         "keyed by its distance to the photo border's colour (the NFL's grey studio backdrop); "
                         "grabcut: graded or busy backdrops (GrabCut seeded by the face)")
    co.add_argument("--key-tolerance", type=float, default=18.0, help="border keying: CIE Lab distance")
    co.add_argument("--out", required=True)
    hs = sub.add_parser("headshots")
    hs.add_argument("--roster", required=True, help="nflverse roster_<season>.csv")
    hs.add_argument("--team", required=True, help="nflverse team abbreviation, e.g. NYG")
    hs.add_argument("--statuses", default="ACT,DEV")
    hs.add_argument("--pause", type=float, default=1.0, help="seconds between downloads")
    hs.add_argument("--out", required=True, help="a folder outside the repository")
    ex = sub.add_parser("export")
    ex.add_argument("--source-xiso", required=True)
    ex.add_argument("--out", required=True, help="a folder outside the repository")
    sl = sub.add_parser("slots")
    sl.add_argument("--source-xiso", required=True)
    sl.add_argument("--teams", help="comma-separated 2004 roster abbreviations in allocation order (default: all 32)")
    sl.add_argument("--pool-own", action="store_true",
                    help="all listed teams are rewritten in the same build: pool their own ids and split evenly")
    sl.add_argument("--out", required=True)
    ft_ = sub.add_parser("fit")
    ft_.add_argument("--faces", required=True, help="a faces manifest.json from build")
    ft_.add_argument("--source-xiso", required=True)
    ft_.add_argument("--jobs", type=int, default=16)
    ft_.add_argument("--out", required=True)
    tp = sub.add_parser("templates", help="the retail template table for rebuild --templates")
    tp.add_argument("--source-xiso", required=True)
    tp.add_argument("--retail-faces", required=True)
    tp.add_argument("--out", required=True)
    rb = sub.add_parser("rebuild", help="face fit v2: rebuild a team's custom faces in their slots (see cmd_rebuild)")
    rb.add_argument("--faces", required=True, help="the team's faces.json from build (slots, templates, skin tones)")
    rb.add_argument("--headshots", required=True, help="folder with <gsis_id>.png headshots")
    rb.add_argument("--retail-faces", required=True, help="exported retail live faces (f####.png, h####.png, n####.png)")
    rb.add_argument("--head-gltf", required=True, help="the retail hi_head exported by the Models tab (glTF)")
    rb.add_argument("--yunet", required=True, help="OpenCV YuNet face detector model (.onnx)")
    rb.add_argument("--spec", help="team spec (faces.hair_by_eye)")
    rb.add_argument("--calibration", help="photo-to-texture skin calibration JSON (default: the built-in one)")
    rb.add_argument("--templates", help="choose each template again from this table (templates subcommand)")
    rb.add_argument("--jobs", type=int, default=6)
    rb.add_argument("--out", required=True)
    b = sub.add_parser("build")
    b.add_argument("--rows", required=True, help="roster_rows.csv from nfl2k5_team_2026_roster.py")
    b.add_argument("--headshots", required=True, help="folder with headshots.json and the headshot PNGs")
    b.add_argument("--retail-faces", required=True, help="exported retail live faces (f####.png, h####.png, n####.png)")
    b.add_argument("--slots", required=True, help="JSON with face_free_with_portrait: unreferenced face ids")
    b.add_argument("--yunet", required=True, help="OpenCV YuNet face detector model (.onnx)")
    b.add_argument("--dreads", help="comma-separated player names with dreadlocks")
    b.add_argument("--limit", type=int)
    b.add_argument("--likeness", type=int, help="custom-face players (priority order); the rest get portrait slots")
    b.add_argument("--spec", help="team spec (faces.skin_tone_by_eye, faces.dreads)")
    b.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.command == "headshots":
        return cmd_headshots(args)
    if args.command == "coach":
        return cmd_coach(args)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "slots":
        return cmd_slots(args)
    if args.command == "fit":
        return cmd_fit(args)
    if args.command == "rebuild":
        return cmd_rebuild(args)
    if args.command == "templates":
        return cmd_templates(args)
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
