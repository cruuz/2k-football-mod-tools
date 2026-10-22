#!/usr/bin/env python3
"""b778-rh1: assemble the rookie-face bank (data/nfl2k5_rookie_faces) from reviewed 128x128 crops.

Inputs (authoring scratch, not shipped): a folder of 128x128 RGB crops (rNNNNN.png, already framed like the retail
generic portraits), labels.json ({face: {tone, build, hanging, look, traits, novelty}}), accept.txt (one face per line,
the faces that passed review), and the free portrait-id runs of the target image (--runs "2177-2555,5584-5785,...").

What it does: grades each crop lightly toward the retail portraits (saturation x1.10, gain x1.04), quantises it to
the 256-colour P8 palette the game stores (the Studio's deterministic quantiser, nfl_tset_png_import), groups the
faces into the 18 (tone, build) buckets, gives each bucket one contiguous id run (largest bucket first, first fit;
faces with hanging hair first inside a bucket, so the native Dreads rule is "index < hanging"), and writes atlases of
16 x 16 faces (each cell keeps its own <= 256 colours exactly) plus bank.json.

usage: rh1_bank.py --crops DIR --labels labels.json --accept accept.txt --runs RUNS [--jobs 8] [--apply]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402

CELLS = 16
SAT, GAIN = 1.10, 1.04


def grade_quantise(path: str) -> bytes:
    import numpy as np
    from PIL import Image, ImageEnhance
    import nfl_tset_png_import as pt
    im = Image.open(path).convert("RGB")
    im = ImageEnhance.Color(im).enhance(SAT)
    arr = np.clip(np.asarray(im, dtype=np.float32) * GAIN, 0, 255).astype(np.uint8)
    rgba = Image.fromarray(arr, "RGB").convert("RGBA").tobytes()
    palette, levels, _q = pt.quantize_levels([pt.MipLevel(0, 128, 128, rgba)])
    out = pt.rgba_from_indices(levels[0], palette)
    return Image.frombytes("RGBA", (128, 128), out).convert("RGB").tobytes()


def parse_runs(text: str) -> list[tuple[int, int]]:
    runs = []
    for part in text.split(","):
        lo, hi = (int(x) for x in part.split("-"))
        runs.append((lo, hi))
    return runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", required=True, type=Path)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--accept", required=True, type=Path)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    labels = json.loads(args.labels.read_text())
    accept = [l.strip() for l in args.accept.read_text().splitlines() if l.strip() and not l.startswith("#")]
    buckets = {b: [] for b in range(rf.BUCKETS)}
    for face in sorted(accept):
        lab = labels[face]
        buckets[lab["tone"] * 3 + lab["build"]].append(face)
    for b in buckets:
        buckets[b].sort(key=lambda f: (not labels[f]["hanging"], f))
        if not buckets[b]:
            raise SystemExit(f"bucket {b} (tone {b // 3}, build {b % 3}) is empty")
        if len(buckets[b]) > 255:
            buckets[b] = buckets[b][:255]
    runs = [list(r) for r in parse_runs(args.runs)]
    starts = {}
    for b in sorted(buckets, key=lambda b: -len(buckets[b])):
        n = len(buckets[b])
        for run in runs:
            if run[1] - run[0] + 1 >= n:
                starts[b] = run[0]
                run[0] += n
                break
        else:
            raise SystemExit(f"no free id run holds bucket {b} ({n} faces)")
    order = [(b, k, f) for b in range(rf.BUCKETS) for k, f in enumerate(buckets[b])]
    with ProcessPoolExecutor(args.jobs) as pool:
        pixels = list(pool.map(grade_quantise, [str(args.crops / f"{f}.png") for _b, _k, f in order]))
    from PIL import Image
    per = CELLS * CELLS
    atlases, faces = [], []
    for a in range(0, len(order), per):
        sheet = Image.new("RGB", (CELLS * 128, CELLS * 128), (0, 0, 0))
        name = f"faces_{a // per:02d}.png"
        for c, ((b, k, f), rgb) in enumerate(zip(order[a:a + per], pixels[a:a + per])):
            col, row = c % CELLS, c // CELLS
            sheet.paste(Image.frombytes("RGB", (128, 128), rgb), (col * 128, row * 128))
            lab = labels[f]
            faces.append(dict(id=starts[b] + k, face=f, tone=lab["tone"], build=lab["build"],
                              hanging=bool(lab["hanging"]), look=lab.get("look"), traits=lab.get("traits", []),
                              novelty=lab.get("novelty"), atlas=name, cell=[col, row]))
        buf = io.BytesIO()
        sheet.save(buf, "PNG", optimize=True)
        atlases.append((name, buf.getvalue()))
    bank = {
        "schema": rf.SCHEMA_BANK,
        "note": "Fictional draft-style headshots generated for this mod (ChatGPT image generation through the Codex CLI, "
                "Noah's subscription), reviewed one by one; no real person and no reference photo. tone = generic head "
                "skin 0..5, build 0 lean / 1 medium / 2 heavy, hanging = locs or long braids (sets the Dreads bit).",
        "buckets": [dict(tone=b // 3, build=b % 3, start=starts[b], count=len(buckets[b]),
                         hanging=sum(1 for f in buckets[b] if labels[f]["hanging"])) for b in range(rf.BUCKETS)],
        "atlases": [dict(file=n, sha256=hashlib.sha256(d).hexdigest(), bytes=len(d)) for n, d in atlases],
        "faces": faces,
    }
    print(json.dumps({"faces": len(faces), "atlas_bytes": sum(len(d) for _n, d in atlases),
                      "buckets": [(r["tone"], r["build"], r["start"], r["count"], r["hanging"]) for r in bank["buckets"]]}))
    if args.apply:
        rf.DATA_DIR.mkdir(parents=True, exist_ok=True)
        for old in rf.DATA_DIR.glob("faces_*.png"):
            old.unlink()
        for n, d in atlases:
            (rf.DATA_DIR / n).write_bytes(d)
        rf.BANK_JSON.write_text(json.dumps(bank, indent=0) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
