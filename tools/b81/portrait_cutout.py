#!/usr/bin/env python3
"""b81 portrait cutout: take the opaque photo background off a Player Card portrait, with a local matting model.

Why (owner report 2026-11-25, Depth Chart): "the rookie photos have a grey background, while the normal images we used have no
background ... ideally I would like to keep the rookie pictures we have and in some way that doesnt destroy our usage,
maybe a smart script idk, remove the background on each image."  The real NFL.com headshots ship with a transparent
cutout; the 4,254 fictional draft faces of data/nfl2k5_rookie_faces were opaque 128 x 128 pictures with a grey studio
background, so every draftee showed a grey square on the card.

What it does (no language model, no generated pixels, nothing retouched)
-------------------------------------------------------------------------
1. The picture is padded by mirroring (a cropped shoulder keeps running past the edge for the model, so it is not cut off
   at the frame), enlarged, and a local matting network (``birefnet-portrait`` through rembg, ONNX) returns
   an alpha matte.
2. The matte is brought back to the picture's own size with an area filter (soft edge), speckle is removed, and the
   pixels the matte calls foreground keep the photograph's own colours; the edge pixels, which mix the subject with the
   grey wall, get the subject's colour back from a foreground estimate (closed-form, pymatting's ``estimate_foreground_ml``)
   so no grey fringe is left.  A pixel that is solid foreground is not changed at all.
3. Output is an RGBA PNG.  For the game's 128 x 128 P8 format (256 RGBA palette entries) the ``pack`` step reduces each
   cutout exactly as the real-portrait pipeline does (libimagequant, then the same hole fix).

Needs a venv with ``rembg[cpu]`` (onnxruntime, pymatting), numpy and Pillow; the network is fetched once
(``U2NET_HOME`` sets where the weights live).  ``pack`` and ``audit`` need only numpy and Pillow (libimagequant for ``pack``).

  portrait_cutout.py image --src DIR_OR_FILE --out DIR [--model birefnet-portrait] [--work 1024]
        any opaque photos (PNG/JPEG) -> RGBA cutouts at the same size (the headshot pipeline's step: rst2_headshots.py cutout)
  portrait_cutout.py faces --data DIR --out DIR [--only IDS] [--shard K/N]
        every face of a bank (data/nfl2k5_rookie_faces) -> 128 x 128 RGBA cutouts (face_NNNN.png by bank row)
  portrait_cutout.py pack  --data DIR --cutouts DIR
        write the cutouts back into the bank's atlases (indices + RGBA palettes) and bank.json
  portrait_cutout.py audit [--data DIR ...]
        measure every shipped portrait: is the border opaque (a background) or transparent (a cutout)?
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "birefnet-portrait"
METHOD = "rembg:" + MODEL                    # the string every manifest row carries
METHOD_NOTE = "birefnet-portrait matte through rembg (3 x 3 faces per pass, mirrored-edge margin), speckle cleaned, subject colour at the soft edge from pymatting's foreground estimate"
CELLS = 16

TILE = 3                       # 3 x 3 faces per model pass (the model sees 1024 px; 9 faces cost one pass)
CELL = 341                     # px per face cell in a tile (1024 // 3)
PAD = 0.125                    # mirrored margin around a face (a margin of 0.25 made the model lose half a dreadlock head)

# A portrait counts as cut out when its border is partly transparent (a studio wall makes it fully opaque); see border_transparent.
BORDER_ROWS = 96
BORDER_TRANSPARENT_MIN = 0.15


# ------------------------------------------------------------------------------------------------ matting
def make_session(model: str = MODEL, device: str = "cpu"):
    """A rembg session. ``device`` "cuda" needs onnxruntime-gpu and the nvidia cudnn/cublas wheels in the same venv; it
    loads them from the venv (onnxruntime.preload_dlls) and fails loudly rather than falling back to the CPU."""
    from rembg import new_session  # noqa: PLC0415 - heavy, only the matting commands need it
    if device == "cuda":
        import onnxruntime as ort  # noqa: PLC0415
        ort.preload_dlls()
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise SystemExit("device cuda asked for, but onnxruntime-gpu has no CUDAExecutionProvider here")
        return new_session(model, providers=["CUDAExecutionProvider"])
    return new_session(model, providers=["CPUExecutionProvider"])


def _cell(image, work: int, pad: float, mode: str = "reflect"):
    """(RGB PIL ``work`` px square: the picture mirrored out by ``pad`` on every side and enlarged, crop box in it)."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    rgb = image.convert("RGB")
    w, h = rgb.size
    p = max(2, int(round(max(w, h) * pad)))
    arr = np.asarray(rgb)
    if mode == "wall":       # a flat margin in the wall's own colour: hair that runs off the top edge ends against the wall
        wall = np.median(np.concatenate([arr[:, :4].reshape(-1, 3), arr[:, -4:].reshape(-1, 3)]), axis=0).astype(np.uint8)
        padded = np.empty((h + 2 * p, w + 2 * p, 3), np.uint8)
        padded[:] = wall
        padded[p:p + h, p:p + w] = arr
        big = Image.fromarray(padded)
    else:
        big = Image.fromarray(np.pad(arr, ((p, p), (p, p), (0, 0)), mode="reflect"))
    side = max(big.size)
    canvas = Image.new("RGB", (side, side))
    canvas.paste(big, ((side - big.width) // 2, (side - big.height) // 2))
    k = work / side
    return canvas.resize((work, work), Image.LANCZOS if k > 1 else Image.BOX), (p, p, w, h, side, (side - big.width) // 2,
                                                                                  (side - big.height) // 2)


def _uncell(mask, info):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    p, _p, w, h, side, ox, oy = info
    full = mask.resize((side, side), Image.BOX if side < mask.width else Image.BICUBIC)
    arr = np.asarray(full, dtype=np.float32) / 255.0
    return arr[oy + p:oy + p + h, ox + p:ox + p + w]


def matte_many(images, session, work: int = CELL, pad: float = PAD, tile: int = TILE, mode: str = "reflect"):
    """list of float alpha arrays (h, w) in 0..1, one per RGB PIL image.  Each picture is padded by mirroring (a cropped
    shoulder keeps running past the edge, so the model does not cut it at the frame) and enlarged to a ``work`` px cell;
    ``tile`` x ``tile`` cells share one model pass (the model sees ``work * tile`` px, as it was trained)."""
    from PIL import Image  # noqa: PLC0415
    from rembg import remove  # noqa: PLC0415
    out = []
    n = tile * tile
    for start in range(0, len(images), n):
        group = images[start:start + n]
        cells = [_cell(im, work, pad, mode) for im in group]
        canvas = Image.new("RGB", (work * tile, work * tile), (128, 128, 128))
        for k, (cell, _info) in enumerate(cells):
            canvas.paste(cell, ((k % tile) * work, (k // tile) * work))
        mask = remove(canvas, session=session, only_mask=True)
        for k, (_cell_img, info) in enumerate(cells):
            part = mask.crop(((k % tile) * work, (k // tile) * work, (k % tile + 1) * work, (k // tile + 1) * work))
            out.append(_uncell(part, info))
    return out


def matte(image, session, work: int = 1024, pad: float = PAD, mode: str = "reflect"):
    """float alpha (h, w) in 0..1 for one RGB PIL image (the model sees the picture alone, at ``work`` px)."""
    return matte_many([image], session, work, pad, tile=1, mode=mode)[0]


def clean(alpha, lo: float = 0.04, hi: float = 0.97, min_area: float = 0.02):
    """Drop speckle: keep connected foreground pieces of at least ``min_area`` of the picture (and the largest one),
    snap the nearly-solid ends of the matte (a halo of 0.03 or 0.98 is noise, not edge), keep the soft middle."""
    import numpy as np  # noqa: PLC0415
    from scipy import ndimage  # noqa: PLC0415
    solid = alpha > 0.5
    lab, n = ndimage.label(solid)
    if n:
        sizes = ndimage.sum(solid, lab, range(1, n + 1))
        keep = {i + 1 for i, s in enumerate(sizes) if s >= min_area * solid.size or s == sizes.max()}
        ok = np.isin(lab, list(keep))
        near = ndimage.binary_dilation(ok, iterations=3)
        alpha = np.where(near, alpha, 0.0)
    alpha = np.where(alpha < lo, 0.0, alpha)
    alpha = np.where(alpha > hi, 1.0, alpha)
    # holes inside the subject (an eye or a tooth the net rated 0.9) are not background: fill what the wall cannot reach
    solid = alpha > 0.5
    filled = ndimage.binary_fill_holes(solid)
    alpha = np.where(filled & ~solid, np.maximum(alpha, 1.0), alpha)
    return alpha.astype(np.float32)


def foreground(rgb_u8, alpha):
    """Subject colours at the matte's soft edge (the pixel there is subject mixed with wall): pymatting's closed-form
    foreground estimate; solid pixels are returned unchanged."""
    import numpy as np  # noqa: PLC0415
    from pymatting import estimate_foreground_ml  # noqa: PLC0415
    img = rgb_u8.astype(np.float64) / 255.0
    fg = estimate_foreground_ml(img, alpha.astype(np.float64))
    out = np.where((alpha >= 0.999)[..., None], img, fg)
    return np.clip(np.rint(out * 255.0), 0, 255).astype(np.uint8)


def compose(image, alpha):
    """RGBA PIL image: ``image``'s subject colours (foreground estimate at the soft edge) with ``alpha`` as its alpha."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    rgb = image.convert("RGB")
    alpha = clean(alpha)
    fg = foreground(np.asarray(rgb), alpha)
    out = np.dstack([fg, np.rint(alpha * 255).astype(np.uint8)])
    out[out[..., 3] == 0, :3] = 0
    return Image.fromarray(out, "RGBA")


def cutout(image, session, work: int = 1024, pad: float = PAD, mode: str = "reflect"):
    """RGBA PIL image, same size as ``image``: subject with a soft alpha, wall gone (the picture alone in the model)."""
    return compose(image, matte(image, session, work, pad, mode))


def face_ok(rgba) -> bool:
    """The cutout of a 128 x 128 portrait kept the head (the middle is solid), has a transparent border and is plausible in size."""
    import numpy as np  # noqa: PLC0415
    a = np.asarray(rgba)[..., 3].astype(np.float32) / 255.0
    return bool((a[40:100, 40:88] > 0.97).mean() >= 0.95 and border_transparent(rgba) >= BORDER_TRANSPARENT_MIN
                and 0.30 <= (a > 0.5).mean() <= 0.95)


def border_transparent(rgba_array) -> float:
    """Share of the picture's border (top row and both side columns down to the shoulders, rows 0..95) that is transparent
    (alpha <= 8).  A studio wall is 0; the real portraits are 0.55 or more, a draft face with big hair that runs off the
    top and sides is 0.3 or more."""
    import numpy as np  # noqa: PLC0415
    a = np.asarray(rgba_array)[..., 3]
    ring = np.concatenate([a[0], a[:BORDER_ROWS, 0], a[:BORDER_ROWS, -1]])
    return float((ring <= 8).mean())


LOST_RETRY = 0.04                # a cutout that dropped this share of clearly-not-wall pixels is tried again, other ways
LOST_GAIN = 0.005                # ... and replaced only by a clearly better one


def lost_fraction(rgb, rgba) -> float:
    """Share of the picture that differs strongly from the wall (a row-wise left/right wall model) yet is transparent in
    the cutout: hair or shoulder the matte lost.  0.003 is typical; a big afro or locs cut at the top reads 0.07 and more."""
    import numpy as np  # noqa: PLC0415
    o = np.asarray(rgb, np.float32)[..., :3]
    a = np.asarray(rgba)[..., 3] / 255.0
    w = o.shape[1]
    left, right = np.median(o[:, :5], axis=1), np.median(o[:, -5:], axis=1)
    t = np.linspace(0, 1, w)[None, :, None]
    wall = left[:, None, :] * (1 - t) + right[:, None, :] * t
    return float((((np.abs(o - wall).sum(-1)) > 110) & (a < 0.2)).mean())


RETRIES = (("alone", 1024, PAD, "reflect"), ("alone_no_margin", 1024, 0.0, "reflect"), ("alone_thin_margin", 1024, 0.0625, "reflect"),
           ("alone_wide_margin", 1024, 0.25, "reflect"), ("alone_512", 512, PAD, "reflect"))


def cutout_faces(images, session):
    """[(RGBA PIL image, how)] for 128 x 128 pictures: tiled passes first (``how`` "tile"); a face that fails ``face_ok`` or
    loses a lot of non-wall picture (``lost_fraction``) is matted alone in other ways (the model's answer depends a little
    on its neighbours in the tile and on the mirrored margin) and the one that loses least stays.  "unresolved" means no
    way passed ``face_ok``; such faces are listed for review."""
    import numpy as np  # noqa: PLC0415
    out = []
    for im, alpha in zip(images, matte_many(images, session)):
        best, how = compose(im, alpha), "tile"
        best_lost = lost_fraction(im, np.asarray(best))
        ok = face_ok(np.asarray(best))
        if not ok or best_lost > LOST_RETRY:
            for name, work, pad, mode in RETRIES:
                cand = cutout(im, session, work, pad, mode)
                cand_ok, cand_lost = face_ok(np.asarray(cand)), lost_fraction(im, np.asarray(cand))
                if (cand_ok and not ok) or (cand_ok == ok and cand_lost < best_lost - LOST_GAIN):
                    best, how, best_lost, ok = cand, name, cand_lost, cand_ok
        if best_lost > LOST_RETRY:
            # big hair that runs off the top of the frame can still be cut after the retries above (the row-wise wall
            # model in lost_fraction is itself fooled by hair at the sides): a flat margin in the wall's colour lets the model
            # see where the hair ends, and when that matte keeps clearly more of the head (4 % of the picture) it wins
            area = float((np.asarray(best)[..., 3] > 127).mean())
            for name, mode_pad in (("alone_wall_margin", PAD), ("alone_wall_margin_wide", 0.25)):
                cand = cutout(im, session, 1024, mode_pad, "wall")
                if face_ok(np.asarray(cand)) and float((np.asarray(cand)[..., 3] > 127).mean()) > area + 0.04:
                    best, how, ok = cand, name, True
                    area = float((np.asarray(cand)[..., 3] > 127).mean())
        out.append((best, how if ok else "unresolved"))
    return out


# ------------------------------------------------------------------------------------------------ P8 (128 x 128, 256 RGBA entries)
def quantize_rgba128(rgba):
    """(indices bytes 16384, palette bytes 1024 RGBA): the real-portrait pipeline's reduction (libimagequant + hole fix)."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    sys.path[:0] = [str(ROOT)]
    from tools.b780.rst2_headshots import Framing  # noqa: PLC0415 - the existing fix_holes, not copied
    q = rgba.quantize(256, method=Image.Quantize.LIBIMAGEQUANT)
    pal = bytes(q.getpalette("RGBA")[:1024]).ljust(1024, b"\0")
    idx = Framing.fix_holes(np.asarray(q).copy(), np.frombuffer(pal, np.uint8).reshape(256, 4), np.asarray(rgba)).tobytes()
    return idx, pal


# ------------------------------------------------------------------------------------------------ bank atlases
def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bank_face(face, files):
    """(128 x 128 RGBA numpy array) of a bank row; the palette PNG may be RGB (opaque) or RGBA."""
    import numpy as np  # noqa: PLC0415
    col, row = face["cell"]
    index, palette = files[face["atlas"]], files[face["atlas"][:-4] + "_pal.png"].convert("RGBA")
    cell = np.asarray(index.crop((col * 128, row * 128, col * 128 + 128, row * 128 + 128)))
    pal = np.asarray(palette.crop((0, row * 16 + col, 256, row * 16 + col + 1))).reshape(256, 4)
    return pal[cell]


def open_atlases(data: Path, bank: dict):
    from PIL import Image  # noqa: PLC0415
    files = {}
    for sheet in bank["atlases"]:
        raw = (data / sheet["file"]).read_bytes()
        if sheet.get("sha256") and sha(raw) != sheet["sha256"]:
            raise SystemExit(f"{sheet['file']} does not match its pin in bank.json")
        files[sheet["file"]] = Image.open(__import__("io").BytesIO(raw))
        files[sheet["file"]].load()
    return files


def face_key(face) -> str:
    return f"{face['atlas'][:-4]}_{face['cell'][0]:02d}_{face['cell'][1]:02d}"


def cmd_faces(args) -> int:
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bank = json.loads((data / "bank.json").read_text(encoding="utf-8"))
    files = open_atlases(data, bank)
    only = {int(x) for x in args.only.split(",")} if args.only else None
    todo = []
    for n, face in enumerate(bank["faces"]):
        if args.shard and n % int(args.shard.split("/")[1]) != int(args.shard.split("/")[0]):
            continue
        if only is not None and face.get("id") not in only and face.get("legacy_id") not in only:
            continue
        if (out / f"{face_key(face)}.png").exists() and not args.force:
            continue
        todo.append(face)
    print(f"{len(todo)} faces to do", flush=True)
    session = make_session(args.model, args.device)
    receipt_path = out / "faces_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
    step = TILE * TILE * 4
    for start in range(0, len(todo), step):
        batch = todo[start:start + step]
        pics = [read_bank_face(f, files) for f in batch]
        done = {}
        wall = [i for i, p in enumerate(pics) if border_transparent(p) < BORDER_TRANSPARENT_MIN]
        for i, p in enumerate(pics):
            if i not in wall:
                done[i] = (Image.fromarray(p, "RGBA"), "already_transparent")
        got = cutout_faces([Image.fromarray(pics[i][..., :3], "RGB") for i in wall], session)
        done.update({i: g for i, g in zip(wall, got)})
        for i, face in enumerate(batch):
            done[i][0].save(out / f"{face_key(face)}.png")
            receipt[face_key(face)] = done[i][1]
        receipt_path.write_text(json.dumps(receipt, indent=0), encoding="utf-8")
        print(f"{start + len(batch)}/{len(todo)}", flush=True)
    print(f"{len(todo)} cutouts written to {out}; unresolved: {[k for k, v in receipt.items() if v == 'unresolved']}")
    return 0


def cmd_pack(args) -> int:
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    data, cuts = Path(args.data), Path(args.cutouts)
    bank = json.loads((data / "bank.json").read_text(encoding="utf-8"))
    files = open_atlases(data, bank)
    index_atlases = {n: np.asarray(im).copy() for n, im in files.items() if not n.endswith("_pal.png")}
    pal_atlases = {n: np.asarray(im.convert("RGBA")).copy() for n, im in files.items() if n.endswith("_pal.png")}
    ratios, missing = [], []
    for face in bank["faces"]:
        src = cuts / f"{face_key(face)}.png"
        if not src.exists():
            missing.append(face_key(face))
            continue
        rgba = Image.open(src).convert("RGBA")
        assert rgba.size == (128, 128), src
        idx, pal = quantize_rgba128(rgba)
        col, row = face["cell"]
        index_atlases[face["atlas"]][row * 128:row * 128 + 128, col * 128:col * 128 + 128] = np.frombuffer(idx, np.uint8).reshape(128, 128)
        pal_atlases[face["atlas"][:-4] + "_pal.png"][row * 16 + col, :, :] = np.frombuffer(pal, np.uint8).reshape(256, 4)
        ratios.append(float(np.asarray(rgba)[..., 3].mean() / 255.0))
    if missing:
        raise SystemExit(f"{len(missing)} faces have no cutout (first: {missing[:3]}); nothing written")
    for sheet in bank["atlases"]:
        name = sheet["file"]
        im = Image.fromarray(index_atlases[name], "L") if name in index_atlases else Image.fromarray(pal_atlases[name], "RGBA")
        im.save(data / name, optimize=True)
        raw = (data / name).read_bytes()
        sheet["sha256"], sheet["bytes"] = sha(raw), len(raw)
    bank["cutout"] = {"method": METHOD_NOTE, "model": MODEL, "faces": len(bank["faces"]),
                      "note": "b81: the grey studio background of every face is removed; the palettes carry alpha (RGBA), "
                              "as the real portraits' do. Source faces were the shipped 128 x 128 P8 pictures (no larger original exists)."}
    for face in bank["faces"]:
        face["cutout"] = METHOD
    (data / "bank.json").write_text(json.dumps(bank, indent=0) + "\n", encoding="utf-8")      # the bank's own layout
    print(f"packed {len(ratios)} faces; mean foreground share {np.mean(ratios):.3f}")
    return 0


# ------------------------------------------------------------------------------------------------ headshot pipeline
def cmd_image(args) -> int:
    from PIL import Image  # noqa: PLC0415
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    paths = [src] if src.is_file() else sorted(p for p in src.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    session = make_session(args.model, args.device)
    receipt = {}
    for p in paths:
        im = Image.open(p)
        rgba = im.convert("RGBA")
        opaque = rgba.getchannel("A").getextrema()[0] == 255
        target = out / (p.stem + ".png")
        if not opaque:
            rgba.save(target)
            receipt[p.stem] = {"cutout": "source_transparent"}
            continue
        cutout(rgba.convert("RGB"), session, args.work).save(target)
        receipt[p.stem] = {"cutout": "rembg:" + args.model}
        print("cutout", p.name, flush=True)
    (out / "cutout_receipt.json").write_text(json.dumps(receipt, indent=0), encoding="utf-8")
    return 0


# ------------------------------------------------------------------------------------------------ audit
def audit_rows(data: Path):
    """[(label, border transparency, mean alpha)] for every portrait of a bank.json or a portraits.json folder."""
    import numpy as np  # noqa: PLC0415
    doc = json.loads(next(p for p in (data / "bank.json", data / "portraits.json") if p.exists()).read_text(encoding="utf-8"))
    rows = doc["faces"] if "faces" in doc else doc["portraits"]
    files = open_atlases(data, {"atlases": doc["atlases"]})
    out = []
    for row in rows:
        rgba = read_bank_face(row, files)
        out.append((row.get("id"), row.get("face") or f"{row.get('first', '')} {row.get('last', '')}".strip(),
                    border_transparent(rgba), float(rgba[..., 3].mean() / 255.0)))
    return out


def cmd_audit(args) -> int:
    for folder in args.data or [str(ROOT / "data" / "nfl2k5_real_portraits"), str(ROOT / "data" / "nfl2k5_rookie_faces")]:
        rows = audit_rows(Path(folder))
        bad = [r for r in rows if r[2] < BORDER_TRANSPARENT_MIN]
        print(f"{Path(folder).name}: {len(rows)} portraits, {len(bad)} with an opaque background")
        for r in bad[: args.show]:
            print("  ", r)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("image")
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    p.add_argument("--work", type=int, default=1024)
    p.set_defaults(fn=cmd_image)
    p = sub.add_parser("faces")
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    p.add_argument("--only")
    p.add_argument("--shard")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_faces)
    p = sub.add_parser("pack")
    p.add_argument("--data", required=True)
    p.add_argument("--cutouts", required=True)
    p.set_defaults(fn=cmd_pack)
    p = sub.add_parser("audit")
    p.add_argument("--data", action="append")
    p.add_argument("--show", type=int, default=10)
    p.set_defaults(fn=cmd_audit)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
