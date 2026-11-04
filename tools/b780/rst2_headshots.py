#!/usr/bin/env python3
"""b780 rst2 (Q41, Q46): official NFL.com headshots for the real players the pack gains, into the real-portraits pipeline.

The same pipeline as b779-pt1 and b780-b9 D12 (data/nfl2k5_real_portraits, mod_editor/core/nfl2k5_real_portraits.py), as
one tool with three steps. A target is {gsis, first, last, pos, college, bm, bd, url[, espn]}: ``url`` is the nflverse
roster_2026 ``headshot_url`` (the ESPN headshot of the same espn_id is the documented fallback).

  fetch    download each headshot, check it decodes, keep it as an RGBA PNG (at most 1400 px wide)
  convert  gate (placeholder or shared image, empty, no face, tiny face ...), crop to the retail portrait framing
           (eye line y = 48.4, eye to mouth 30 px of 128, YuNet landmarks, zoom out up to 1.45x for tall hair), reduce
           to the game's 128 x 128 P8 format, measure the skin tone (ITA from forehead, nose and cheek patches), and
           write review sheets. A reviewed skin tone is the one that ships (the 2026 photo set is high-key).
  append   put the accepted faces into the repo's atlases (a new atlas file when the last is full) and the manifest

  python3 tools/b780/rst2_headshots.py fetch   --targets T.json --work W
  python3 tools/b780/rst2_headshots.py convert --targets T.json --work W --model face_detection_yunet_2023mar.onnx
  python3 tools/b780/rst2_headshots.py append  --targets T.json --work W [--data data/nfl2k5_real_portraits]
                                                 [--tones tones.json] [--job b780-rst2 --fetched 2026-11-04]

The original pictures stay in the work folder; the manifest keeps each source URL, size and sha256 (as pt1 did).
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import io
import json
import math
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

EYE_Y, FACE_H, CX = 48.4, 30.0, 64.0            # retail framing, measured on 247 retail portraits
CELLS_PER_ATLAS, ATLAS_SIZE = 256, 2048
ITA_TONE = ((55, 0), (44, 1), (33, 2), (22, 3), (8, 4))     # data/nfl2k5_refresh_appearance_2026.v1.json


def tone_from_ita(ita):
    for limit, tone in ITA_TONE:
        if ita >= limit:
            return tone
    return 5


def _load_targets(path):
    return [t for t in json.loads(Path(path).read_text(encoding="utf-8")) if t.get("gsis")]


# ------------------------------------------------------------------------------------------------ fetch
def fetch(args):
    from PIL import Image
    work = Path(args.work)
    (work / "png").mkdir(parents=True, exist_ok=True)
    targets = _load_targets(args.targets)

    def one(t):
        g = t["gsis"]
        if t.get("url"):
            url, src = t["url"], "roster_2026"
        elif t.get("espn"):
            url, src = f"https://a.espncdn.com/i/headshots/nfl/players/full/{t['espn']}.png", "espn"
        else:
            return dict(gsis=g, status="no_url")
        rec, raw = dict(gsis=g, url=url, src=src), None
        for _attempt in range(3):
            try:
                resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60)
                raw = resp.read()
                break
            except Exception as exc:                       # noqa: BLE001 - recorded in the receipt
                rec["err"] = str(exc)
                time.sleep(2)
        if raw is None:
            rec["status"] = "fetch_error:" + rec.get("err", "")
            return rec
        rec.update(http=resp.status, content_type=resp.headers.get("content-type"),
                   last_modified=resp.headers.get("last-modified"), bytes=len(raw),
                   raw_sha256=hashlib.sha256(raw).hexdigest())
        try:
            im = Image.open(io.BytesIO(raw))
            rec["format"], rec["size"] = im.format, list(im.size)
            im = im.convert("RGBA")
            rec["alpha"] = list(im.getchannel("A").getextrema())
            if im.width > 1400:
                im = im.resize((1400, round(im.height * 1400 / im.width)), Image.LANCZOS)
            im.save(work / "png" / f"{g}.png")
            rec["status"] = "ok"
        except Exception as exc:                           # noqa: BLE001
            rec["status"] = "decode_error:" + str(exc)[:100]
        return rec

    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(one, targets))
    (work / "fetch_receipt.json").write_text(json.dumps(res, indent=0), encoding="utf-8")
    print(collections.Counter((r["status"].split(":")[0], r.get("src")) for r in res))


# ------------------------------------------------------------------------------------------------ convert
class Framing:
    def __init__(self, model):
        import cv2
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.6, 0.3, 50)

    @staticmethod
    def composite_gray(im, g=(128, 128, 128)):
        from PIL import Image
        bg = Image.new("RGB", im.size, g)
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg

    def detect(self, im):
        """faces (score, landmarks 5x2, box x y w h) in source pixels, best first."""
        import numpy as np
        rgb = self.composite_gray(im)
        self.detector.setInputSize(rgb.size)
        ok, f = self.detector.detect(self.cv2.cvtColor(np.asarray(rgb), self.cv2.COLOR_RGB2BGR))
        if f is None:
            return []
        return sorted(((float(r[14]), r[4:14].reshape(5, 2).astype(float), r[:4].astype(float)) for r in f),
                      key=lambda x: -x[0])

    @staticmethod
    def crop128(im, lm, ss=4):
        import numpy as np
        from PIL import Image
        re_, le, nose, rm, lmo = lm
        eye, mouth = (re_ + le) / 2, (rm + lmo) / 2
        fh = float(np.linalg.norm(mouth - eye))
        k = fh / FACE_H                                           # source px per portrait px
        ax = (eye[0] + nose[0]) / 2
        a = np.asarray(im.getchannel("A")) > 128
        lo, hi = int(max(0, ax - 2.2 * fh)), int(min(im.width, ax + 2.2 * fh))
        rows = np.where(a[:, lo:hi].any(axis=1))[0]
        top = float(rows[0]) if len(rows) else eye[1] - FACE_H * k * 1.6
        need = (eye[1] - top) / (EYE_Y - 3)
        if need > k:                                              # big hair: also centre between face and hair mass
            cols = np.where(a[int(max(0, top)):int(min(im.height, eye[1] + fh)), :].any(axis=0))[0]
            if len(cols):
                ax = (ax + (cols[0] + cols[-1]) / 2) / 2
        k = max(k, min(need, 1.45 * k))
        x0, y0, side = ax - CX * k, eye[1] - EYE_Y * k, 128 * k
        pad = int(math.ceil(max(0, -x0, -y0, x0 + side - im.width, y0 + side - im.height))) + 2
        canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
        canvas.paste(im, (pad, pad))
        box = (x0 + pad, y0 + pad, x0 + pad + side, y0 + pad + side)
        big = canvas.resize((128 * ss, 128 * ss), Image.LANCZOS, box=box)
        return big.resize((128, 128), Image.BOX), dict(face_h_src=fh, scale=1 / k, box=[x0, y0, x0 + side, y0 + side])

    @staticmethod
    def fix_holes(idx, pal, rgba):
        """libimagequant may put opaque pixels on a (semi)transparent palette entry and the reverse: nearest right kind."""
        import numpy as np
        a0, pa = rgba[..., 3].astype(int), pal[:, 3].astype(int)
        pix_a = pa[idx]
        for mask, allowed in (((a0 >= 250) & (pix_a < 250), pa >= 250), ((a0 <= 2) & (pix_a > 6), pa <= 6)):
            if not mask.any():
                continue
            cand = np.where(allowed)[0]
            if len(cand) == 0:
                continue
            ys, xs = np.where(mask)
            src = rgba[ys, xs, :3].astype(int)
            d = ((src[:, None, :] - pal[cand][None, :, :3].astype(int)) ** 2).sum(axis=2)
            idx[ys, xs] = cand[d.argmin(axis=1)]
        return idx

    def tone(self, im, box_w=640):
        """ITA (degrees) from forehead, nose and both cheeks of the best face on a 640 px wide copy; None without a face."""
        import numpy as np
        from PIL import Image
        small = im.resize((box_w, round(im.height * box_w / im.width)), Image.LANCZOS)
        faces = self.detect(small)
        if not faces:
            return None
        x, y, w, h = faces[0][2]
        arr = np.asarray(small.convert("RGBA")).astype(np.float32)
        lab = self.cv2.cvtColor(arr[..., :3] / 255.0, self.cv2.COLOR_RGB2Lab)
        patches = ((.30, .70, .10, .22), (.42, .58, .45, .60), (.12, .30, .50, .66), (.70, .88, .50, .66))
        pix = []
        for fx0, fx1, fy0, fy1 in patches:
            sl = (slice(max(0, int(y + fy0 * h)), int(y + fy1 * h)), slice(max(0, int(x + fx0 * w)), int(x + fx1 * w)))
            part = lab[sl][arr[..., 3][sl] > 200]
            if len(part):
                pix.append(part)
        if not pix:
            return None
        L, _a, b = np.median(np.concatenate(pix), axis=0)
        return dict(ita=round(math.degrees(math.atan2(L - 50, b)), 1), L=round(float(L), 1), b=round(float(b), 1))


def convert(args):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    work = Path(args.work)
    (work / "rgba").mkdir(parents=True, exist_ok=True)
    (work / "sheets").mkdir(exist_ok=True)
    targets = {t["gsis"]: t for t in _load_targets(args.targets)}
    receipt = {r["gsis"]: r for r in json.loads((work / "fetch_receipt.json").read_text(encoding="utf-8"))}
    manifest = json.loads((ROOT / "data/nfl2k5_real_portraits/portraits.json").read_text(encoding="utf-8"))
    old_sha = {r["source_sha256"] for r in manifest["portraits"]}
    old_urlid = {re.sub(r".*/", "", r["source_url"]) for r in manifest["portraits"]}
    urlid = collections.Counter(re.sub(r".*/", "", r["url"]) for r in receipt.values() if r.get("url"))
    shas = collections.Counter(r.get("raw_sha256") for r in receipt.values() if r.get("raw_sha256"))
    fr = Framing(args.model)
    gate, crops, accepted = {}, {}, []
    for g, t in targets.items():
        r = receipt.get(g, {"status": "no_fetch"})
        flags, rej = [], None
        if r["status"] != "ok":
            gate[g] = dict(rej="no_headshot_url" if r["status"] == "no_url" else r["status"], flags=flags)
            continue
        if shas[r["raw_sha256"]] > 1 or urlid[re.sub(r".*/", "", r["url"])] > 1 or r["raw_sha256"] in old_sha \
                or re.sub(r".*/", "", r["url"]) in old_urlid:
            rej = "shared_image_placeholder_or_wrong_person"
        im = Image.open(work / "png" / f"{g}.png")
        cover = float((np.asarray(im.getchannel("A")) > 128).mean())
        faces = fr.detect(im)
        info = dict(size=list(im.size), alpha_cover=round(cover, 3), faces=len(faces), src=r["src"], bytes=r["bytes"])
        if r["alpha"][0] == 255:
            flags.append("opaque_no_cutout")
        if cover < 0.05:
            rej = rej or "empty_image"
        if not faces:
            rej = rej or "no_face_detected"
        else:
            score, lm, box = faces[0]
            info["score"] = round(score, 3)
            if score < 0.7:
                flags.append("low_face_score")
            if len(faces) > 1 and faces[1][0] > 0.7:
                flags.append("two_faces")
            if box[3] / im.height < 0.10:
                flags.append("tiny_face")
            fh = float(np.linalg.norm((lm[3] + lm[4]) / 2 - (lm[0] + lm[1]) / 2))
            if not 0.8 < float(np.linalg.norm(lm[0] - lm[1])) / fh < 2.2:
                flags.append("odd_face_geometry")
            lm_ = r.get("last_modified")
            if lm_:
                try:
                    year = datetime.datetime.strptime(lm_, "%a, %d %b %Y %H:%M:%S GMT").year
                    info["photo_year"] = year
                    if year <= 2019:
                        flags.append(f"old_photo_{year}")
                except ValueError:
                    pass
        tone = fr.tone(im)
        if tone:
            info.update(tone, ita_skin=tone_from_ita(tone["ita"]))
        gate[g] = dict(rej=rej, flags=flags, info=info)
        if rej:
            continue
        crop, cinfo = fr.crop128(im, faces[0][1])
        q = crop.quantize(256, method=Image.Quantize.LIBIMAGEQUANT)
        pal = bytes(q.getpalette("RGBA")[:1024]).ljust(1024, b"\0")
        idx = fr.fix_holes(np.asarray(q).copy(), np.frombuffer(pal, np.uint8).reshape(256, 4), np.asarray(crop)).tobytes()
        np.save(work / "rgba" / f"{g}.npy", np.frombuffer(idx, np.uint8))
        (work / "rgba" / f"{g}.pal").write_bytes(pal)
        crops[g] = cinfo
        accepted.append(g)
    (work / "gate.json").write_text(json.dumps(gate, indent=0), encoding="utf-8")
    (work / "crop_info.json").write_text(json.dumps(crops), encoding="utf-8")
    (work / "accepted.json").write_text(json.dumps(accepted), encoding="utf-8")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
    per_sheet, cw, ch = 24, 200, 175
    for n in range(0, len(accepted), per_sheet):
        sheet = Image.new("RGB", (cw * 6, ch * 4), (24, 24, 30))
        draw = ImageDraw.Draw(sheet)
        for k, g in enumerate(accepted[n:n + per_sheet]):
            x, y = (k % 6) * cw, (k // 6) * ch
            idx = np.load(work / "rgba" / f"{g}.npy")
            pal = np.frombuffer((work / "rgba" / f"{g}.pal").read_bytes(), np.uint8).reshape(256, 4)
            face = Image.fromarray(pal[idx.reshape(128, 128)], "RGBA")
            back = Image.new("RGBA", face.size, (70, 72, 84, 255))
            back.alpha_composite(face)
            sheet.paste(back.convert("RGB").resize((150, 150), Image.LANCZOS), (x + 2, y + 2))
            t = targets[g]
            info = gate[g].get("info", {})
            draw.text((x + 2, y + 152), f"{n + k:3d} {t['first']} {t['last']}"[:30], fill=(255, 255, 255), font=font)
            draw.text((x + 2, y + 164), f"{t.get('pos', '')} ita {info.get('ita')} t{info.get('ita_skin')} "
                      f"{','.join(gate[g]['flags'])}"[:34], fill=(255, 170, 60), font=font)
        sheet.save(work / "sheets" / f"sheet_{n // per_sheet + 1:02d}.png")
    print(collections.Counter(str(v["rej"]) for v in gate.values()), len(accepted), "accepted",
          collections.Counter(f for v in gate.values() for f in v["flags"]))


# ------------------------------------------------------------------------------------------------ append
def append(args):
    import numpy as np
    from PIL import Image
    work, data = Path(args.work), Path(args.data)
    doc = json.loads((data / "portraits.json").read_text(encoding="utf-8"))
    targets = {t["gsis"]: t for t in _load_targets(args.targets)}
    receipt = {r["gsis"]: r for r in json.loads((work / "fetch_receipt.json").read_text(encoding="utf-8"))}
    gate = json.loads((work / "gate.json").read_text(encoding="utf-8"))
    accepted = [g for g in json.loads((work / "accepted.json").read_text(encoding="utf-8"))]
    have = {r["gsis_id"] for r in doc["portraits"]}
    named = {(r["first"], r["last"], r["birth_month"], r["birth_day"]) for r in doc["portraits"]}
    accepted = [g for g in accepted if g not in have
                and (targets[g]["first"], targets[g]["last"], targets[g]["bm"], targets[g]["bd"]) not in named]
    n_old, id_base = len(doc["portraits"]), doc["id_base"]
    atlases, rows = {}, []
    for k, g in enumerate(accepted):
        pos = n_old + k
        a, cell = divmod(pos, CELLS_PER_ATLAS)
        col, line = cell % 16, cell // 16
        name = f"faces_{a:02d}.png"
        if name not in atlases:
            if (data / name).exists():
                idx, pal = Image.open(data / name).copy(), Image.open(data / (name[:-4] + "_pal.png")).copy()
            else:
                idx, pal = Image.new("L", (ATLAS_SIZE, ATLAS_SIZE), 0), Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            assert idx.mode == "L" and idx.size == (ATLAS_SIZE, ATLAS_SIZE) and pal.mode == "RGBA" and pal.size == (256, 256)
            atlases[name] = (idx, pal)
        idx, pal = atlases[name]
        assert not np.asarray(idx.crop((col * 128, line * 128, col * 128 + 128, line * 128 + 128))).any(), (name, col, line)
        idx.paste(Image.fromarray(np.load(work / "rgba" / f"{g}.npy").reshape(128, 128), "L"), (col * 128, line * 128))
        pal.paste(Image.frombytes("RGBA", (256, 1), (work / "rgba" / f"{g}.pal").read_bytes()), (0, line * 16 + col))
        t, r = targets[g], receipt[g]
        rows.append(dict(id=id_base + pos, gsis_id=g, first=t["first"], last=t["last"], position=t["pos"],
                         college=t.get("college") or "", birth_month=t["bm"], birth_day=t["bd"], group=args.group,
                         identity_match=t.get("method") or "roster_2026_gsis_id", source_url=r["url"], source_list=r["src"],
                         source_http_last_modified=r.get("last_modified"), source_bytes=r["bytes"], source_size=r["size"],
                         source_sha256=r["raw_sha256"], atlas=name, cell=[col, line],
                         review="ok" if not gate[g]["flags"] else "ok_flagged"))
    for name, (idx, pal) in atlases.items():
        idx.save(data / name, optimize=True)
        pal.save(data / (name[:-4] + "_pal.png"), optimize=True)
        for fname, path in ((name, data / name), (name[:-4] + "_pal.png", data / (name[:-4] + "_pal.png"))):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entry = next((e for e in doc["atlases"] if e["file"] == fname), None)
            if entry:
                entry["sha256"] = digest
            else:
                doc["atlases"].append({"file": fname, "sha256": digest})
    doc["portraits"].extend(rows)
    got = {r["gsis_id"] for r in rows}
    before = len(doc.get("wrong_faces", ()))
    doc["wrong_faces"] = [w for w in doc.get("wrong_faces", ()) if w["gsis_id"] not in got]
    doc.setdefault("additions", []).append(dict(
        job=args.job, fetched=args.fetched, rows=len(rows), moved_from_wrong_faces=before - len(doc["wrong_faces"]),
        note=args.note))
    (data / "portraits.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(len(rows), "rows appended; ids", rows[0]["id"] if rows else None, "..", rows[-1]["id"] if rows else None,
          "| wrong_faces rows now", len(doc["wrong_faces"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="step", required=True)
    for name, fn in (("fetch", fetch), ("convert", convert), ("append", append)):
        p = sub.add_parser(name)
        p.add_argument("--targets", required=True)
        p.add_argument("--work", required=True)
        p.set_defaults(fn=fn)
        if name == "convert":
            p.add_argument("--model", required=True, help="face_detection_yunet_2023mar.onnx")
        if name == "append":
            p.add_argument("--data", default=str(ROOT / "data/nfl2k5_real_portraits"))
            p.add_argument("--group", default="roster_player")
            p.add_argument("--job", default="b780-rst2")
            p.add_argument("--fetched", default=datetime.date.today().isoformat())
            p.add_argument("--note", default="Real players on 2026 club rosters that the pack had no record for, and two "
                           "players whose records showed another man's stock portrait; same pipeline as pt1 and b9 D12.")
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
