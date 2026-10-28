#!/usr/bin/env python3
"""b779-rf3: grow the rookie-face bank (data/nfl2k5_rookie_faces) without moving a face an old save already shows.

Noah, 10/28: "generate a ton more ... so the ugly faces are drowned out a bit more ... unique ... realistic".  SWeaR,
10/27: "Some rookie headshots are cut off/cropped out".

* Every beta-78 face keeps its beta-78 portrait id as ``legacy_id`` (a prospect drafted on that disc keeps the id in his
  save) and gets a new row id: the 24 rows are laid out again from ``--start`` so each row can grow.
* New faces (reviewed 128x128 crops + labels) join their (tone, build) row.
* Re-framed faces (``--recrop DIR``: crops whose head top or zoom was wrong) replace their image at both ids;
  ``--retire`` faces (a bad crop with no source left) keep their legacy id only and leave the rows.
* Inside a row: hanging hair first (the native Dreads rule is index < hanging), then the other faces by review look,
  plainest/ugliest last, so the down-weighted zone (zone_start) holds them.
* The beta-78 atlases stay byte-identical; new and re-framed faces go to new atlases (graded and quantised like rh1).

usage: rf3_bank.py --labels NEW_LABELS.json --crops DIR [--recrop DIR] [--retire IDS] [--start 13569] [--apply]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rh1_bank import CELLS, grade_quantise  # noqa: E402

SEVERITY = {"striking": 0, "good": 1, "ordinary": 2, "plain": 3, "novelty": 4, "homely": 5, "ugly": 6, "extreme": 7}


def severity(face: dict) -> float:
    return SEVERITY.get(face.get("look") or "ordinary", 2) + (0.5 if face.get("expression") in ("angry", "stare") else 0)


def row_of(face: dict) -> int:
    if face.get("rare"):
        return rf.BUCKETS + 3 * rf.RARE_GROUPS.index(face["rare"]) + face["build"]
    return face["tone"] * 3 + face["build"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, help="new faces: {key: {tone, build, hanging, look, expression, group, traits}}")
    ap.add_argument("--crops", type=Path, help="folder of the new faces' 128x128 crops (key.png)")
    ap.add_argument("--recrop", type=Path, help="folder of re-framed beta-78 faces (legacy id.png)")
    ap.add_argument("--retire", default="", help="comma-separated beta-78 ids that leave the rows")
    ap.add_argument("--start", type=int, default=13569)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    old = json.loads(rf.BANK_JSON.read_text(encoding="utf-8"))
    if old["schema"] != "nfl2k5_rookie_faces_bank/v2":
        raise SystemExit("expects the beta-78 (v2) bank")
    retire = {int(x) for x in args.retire.split(",") if x}
    recrop = {int(p.stem): p for p in args.recrop.glob("*.png")} if args.recrop else {}
    faces = []
    for f in old["faces"]:
        g = copy.deepcopy(f)
        g["legacy_id"] = g.pop("id")
        g["retired"] = g["legacy_id"] in retire
        faces.append(g)
    pending = []                                     # (face dict, crop path) that need a new atlas cell
    for g in faces:
        if g["legacy_id"] in recrop:
            g["reframed"] = True
            pending.append((g, recrop[g["legacy_id"]]))
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
    for key in sorted(labels):
        lab = labels[key]
        g = dict(face=key, tone=lab["tone"], build=lab["build"], hanging=bool(lab["hanging"]), look=lab.get("look"),
                 expression=lab.get("expression"), group=lab.get("group"), rare=lab.get("rare"),
                 traits=lab.get("traits", []), novelty=None, legacy_id=None, retired=False)
        faces.append(g)
        pending.append((g, args.crops / f"{key}.png"))
    rows = {b: [] for b in range(rf.ROWS)}
    for g in faces:
        if not g["retired"]:
            rows[row_of(g)].append(g)
    starts, cursor = {}, args.start
    for b in range(rf.ROWS):
        members = rows[b]
        hang = [g for g in members if g["hanging"]]
        rest = [g for g in members if not g["hanging"]]
        hang.sort(key=lambda g: (severity(g), str(g["face"])))
        rest.sort(key=lambda g: (severity(g), str(g["face"])))
        rows[b] = hang + rest
        n = len(rows[b])
        if n > rf.ROW_COUNT_MAX or len(hang) > rf.ROW_HANGING_MAX:
            raise SystemExit(f"row {b}: {n} faces / {len(hang)} hanging is over the native limits")
        if len(hang) > rf.zone_start(n):
            raise SystemExit(f"row {b}: the hanging faces reach into the down-weighted zone")
        starts[b] = cursor
        for k, g in enumerate(rows[b]):
            g["id"] = cursor + k
        cursor += n
    if cursor > rf.ID_END:
        raise SystemExit("the rows run past ID_END")
    for g in faces:
        if g["retired"]:
            g["id"] = None
    atlases = [dict(a) for a in old["atlases"]]
    first_new = len(atlases) // 2
    from concurrent.futures import ProcessPoolExecutor
    import numpy as np
    from PIL import Image
    with ProcessPoolExecutor(4) as pool:
        pixels = list(pool.map(grade_quantise, [str(p) for _g, p in pending]))
    per = CELLS * CELLS
    blobs = []
    for a in range(0, len(pending), per):
        chunk = list(zip(pending[a:a + per], pixels[a:a + per]))
        index = np.zeros((CELLS * 128, CELLS * 128), np.uint8)
        palettes = np.zeros((len(chunk), 256, 3), np.uint8)
        name = f"faces_{first_new + a // per:02d}"
        for c, ((g, _p), rgb) in enumerate(chunk):
            col, row = c % CELLS, c // CELLS
            arr = np.frombuffer(rgb, np.uint8).reshape(-1, 3)
            colours, inverse = np.unique(arr, axis=0, return_inverse=True)
            order = np.argsort(colours.astype(np.int64) @ np.array([299, 587, 114]), kind="stable")
            rank = np.empty_like(order); rank[order] = np.arange(len(order))
            index[row * 128:(row + 1) * 128, col * 128:(col + 1) * 128] = rank[inverse.ravel()].reshape(128, 128)
            palettes[c, :len(colours)] = colours[order]
            g["atlas"], g["cell"] = name + ".png", [col, row]
        for suffix, img in ((".png", Image.fromarray(index, "L")), ("_pal.png", Image.fromarray(palettes, "RGB"))):
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            blobs.append((name + suffix, buf.getvalue()))
            atlases.append(dict(file=name + suffix, sha256=hashlib.sha256(buf.getvalue()).hexdigest(),
                                bytes=len(buf.getvalue())))
    keys = ("id", "legacy_id", "face", "tone", "build", "hanging", "look", "expression", "group", "rare", "traits",
            "novelty", "atlas", "cell")
    out_faces = []
    for g in sorted(faces, key=lambda g: (g["id"] is None, g["id"] or 0, g["legacy_id"] or 0)):
        d = {k: g.get(k) for k in keys}
        if g.get("reframed"):
            d["reframed"] = True
        out_faces.append(d)
    bank = {
        "schema": rf.SCHEMA_BANK,
        "note": old["note"] + " b779-rf3: id = the row id the generator draws; legacy_id = the beta-78 id (old saves); "
                "reframed = re-cropped by the eyes because the beta-78 crop cut the head; a face with id null left the rows "
                "(bad crop, no source) and only keeps its legacy id. Inside a row the plainest faces sit last, in the "
                "down-weighted zone.",
        "buckets": [dict(tone=b // 3 if b < rf.BUCKETS else rf.RARE_TONES[(b - rf.BUCKETS) // 3], build=b % 3,
                         **({"group": rf.RARE_GROUPS[(b - rf.BUCKETS) // 3]} if b >= rf.BUCKETS else {}),
                         start=starts[b], count=len(rows[b]),
                         hanging=sum(1 for g in rows[b] if g["hanging"])) for b in range(rf.ROWS)],
        "atlases": atlases,
        "faces": out_faces,
    }
    summary = {"faces": len(out_faces), "drawn": sum(1 for g in out_faces if g["id"] is not None),
               "legacy": sum(1 for g in out_faces if g["legacy_id"] is not None), "new": len(labels),
               "reframed": len(recrop), "retired": len(retire), "new_atlas_bytes": sum(len(d) for _n, d in blobs),
               "rows": [(r["tone"], r["build"], r["start"], r["count"], r["hanging"], rf.zone_start(r["count"]))
                        for r in bank["buckets"]]}
    print(json.dumps(summary))
    if args.apply:
        for n, d in blobs:
            (rf.DATA_DIR / n).write_bytes(d)
        rf.BANK_JSON.write_text(json.dumps(bank, indent=0) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
