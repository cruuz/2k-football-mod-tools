#!/usr/bin/env python3
"""b778-rh1 (extended by b778-rh2): assemble the rookie-face bank (data/nfl2k5_rookie_faces) from reviewed 128x128 crops.

Inputs (authoring scratch, not shipped): a folder of 128x128 RGB crops (rNNNNN.png, already framed like the retail
generic portraits), labels.json ({face: {tone, build, hanging, look, traits, novelty}}), accept.txt (one face per line,
the faces that passed review), and the free portrait-id runs of the target image (--runs "2177-2555,5584-5785,...").

What it does: grades each crop lightly toward the retail portraits (saturation x1.10, gain x1.04), quantises it to
the 256-colour P8 palette the game stores (the Studio's deterministic quantiser, nfl_tset_png_import), groups the
faces into the 18 (tone, build) buckets (atlas = 8-bit palette indices of 16 x 16 faces, luma-sorted per face; the
_pal image holds each cell's 256-colour palette as one row), gives each bucket one contiguous id run (largest bucket first, first fit;
faces with hanging hair first inside a bucket, so the native Dreads rule is "index < hanging"), and writes atlases of
16 x 16 faces (each cell keeps its own <= 256 colours exactly) plus bank.json.

b778-rh2: 24 rows (18 tone x build buckets, then the East Asian and South Asian rows for the rare surnames, by build),
row counts up to 511 (9 bits) with up to 127 hanging faces, several crop folders, per-face look / expression tags.

usage: rh1_bank.py --crops DIR[,DIR...] --labels labels.json --accept accept.txt --runs RUNS [--jobs 8] [--apply]
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
    ap.add_argument("--crops", required=True)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--accept", required=True, type=Path)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    labels = json.loads(args.labels.read_text())
    accept = [l.strip() for l in args.accept.read_text().splitlines() if l.strip() and not l.startswith("#")]
    buckets = {b: [] for b in range(rf.ROWS)}
    for face in sorted(accept):
        lab = labels[face]
        if lab.get("rare"):
            g = rf.RARE_GROUPS.index(lab["rare"])
            if lab["tone"] != rf.RARE_TONES[g] or lab["hanging"]:
                raise SystemExit(f"{face}: a {lab['rare']} face takes tone {rf.RARE_TONES[g]} and no hanging hair")
            buckets[rf.BUCKETS + 3 * g + lab["build"]].append(face)
        else:
            buckets[lab["tone"] * 3 + lab["build"]].append(face)
    for b in buckets:
        buckets[b].sort(key=lambda f: (not labels[f]["hanging"], f))
        if not buckets[b]:
            raise SystemExit(f"row {b} is empty")
        if len(buckets[b]) > rf.ROW_COUNT_MAX:
            raise SystemExit(f"row {b} holds {len(buckets[b])} faces, more than {rf.ROW_COUNT_MAX}")
        if sum(1 for f in buckets[b] if labels[f]["hanging"]) > rf.ROW_HANGING_MAX:
            raise SystemExit(f"row {b} holds more than {rf.ROW_HANGING_MAX} hanging faces")
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
    order = [(b, k, f) for b in range(rf.ROWS) for k, f in enumerate(buckets[b])]
    with ProcessPoolExecutor(args.jobs) as pool:
        dirs = [Path(d) for d in str(args.crops).split(",")]
        pixels = list(pool.map(grade_quantise, [str(next(d / f"{f}.png" for d in dirs if (d / f"{f}.png").is_file()))
                                                for _b, _k, f in order]))
    from PIL import Image
    import numpy as np
    per = CELLS * CELLS
    atlases, faces = [], []
    for a in range(0, len(order), per):
        chunk = list(zip(order[a:a + per], pixels[a:a + per]))
        index = np.zeros((CELLS * 128, CELLS * 128), np.uint8)
        palettes = np.zeros((len(chunk), 256, 3), np.uint8)
        name = f"faces_{a // per:02d}"
        for c, ((b, k, f), rgb) in enumerate(chunk):
            col, row = c % CELLS, c // CELLS
            arr = np.frombuffer(rgb, np.uint8).reshape(-1, 3)
            colours, inverse = np.unique(arr, axis=0, return_inverse=True)
            order_l = np.argsort(colours.astype(np.int64) @ np.array([299, 587, 114]), kind="stable")
            rank = np.empty_like(order_l); rank[order_l] = np.arange(len(order_l))
            index[row * 128:(row + 1) * 128, col * 128:(col + 1) * 128] = rank[inverse.ravel()].reshape(128, 128)
            palettes[c, :len(colours)] = colours[order_l]
            lab = labels[f]
            faces.append(dict(id=starts[b] + k, face=f, tone=lab["tone"], build=lab["build"],
                              hanging=bool(lab["hanging"]), look=lab.get("look"), expression=lab.get("expression"),
                              group=lab.get("group"), rare=lab.get("rare"), traits=lab.get("traits", []),
                              novelty=lab.get("novelty"), atlas=name + ".png", cell=[col, row]))
        for suffix, img in ((".png", Image.fromarray(index, "L")), ("_pal.png", Image.fromarray(palettes, "RGB"))):
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            atlases.append((name + suffix, buf.getvalue()))
    bank = {
        "schema": rf.SCHEMA_BANK,
        "note": "Fictional draft-style headshots generated for this mod (ChatGPT image generation through the Codex CLI, "
                "Noah's subscription), reviewed one by one; no real person and no reference photo. Some unattractive "
                "faces were made a little plainer with a small landmark-guided warp of the generated image. tone = "
                "generic head skin 0..5, build 0 lean / 1 medium / 2 heavy, hanging = locs or long braids (sets the "
                "Dreads bit); rows 18..23 are the East Asian / South Asian rows the rare surnames use; look and "
                "expression are review tags (angry = a rare open scowl, stare = a cold intimidating stare).",
        "buckets": [dict(tone=b // 3 if b < rf.BUCKETS else rf.RARE_TONES[(b - rf.BUCKETS) // 3], build=b % 3,
                         **({"group": rf.RARE_GROUPS[(b - rf.BUCKETS) // 3]} if b >= rf.BUCKETS else {}),
                         start=starts[b], count=len(buckets[b]),
                         hanging=sum(1 for f in buckets[b] if labels[f]["hanging"])) for b in range(rf.ROWS)],
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
