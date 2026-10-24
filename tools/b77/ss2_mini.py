"""Seamen mini helmet cards (64x64) from the kit's helmet texture, rendered with the Studio's Blender rig (job b778 ss2).

Same rig, light and shell as the Team Select cards (``u1_cards``): the helmet alone, side on, fitted to the card.
Home faces left and away faces right, as the retail ``mini_h`` / ``mini_a`` do.

  ss2_mini.py --art ART --helmet-master M --shellc SHELLC.json --models MODELS --out OUT [--facemask 009284]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import u1_cards as C  # noqa: E402

BIG = 1024


def render(art: Path, master: Path, shellc: Path, models: Path, out: Path, facemask="009284", code="14"):
    out.mkdir(parents=True, exist_ok=True)
    items, plans = [], []
    for letter in "HA":
        sel = f"{code}{letter}0"
        helmet = str(master / sel / "helmet_helmet02.png")
        tex = {k: helmet for k in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C")}
        view = {"yaw": 100 if letter == "H" else -100, "pitch": 6, "roll": 0, "dist": 1.0, "fov": 31,
                "target": [0, -0.0545, 0.80], "size": [BIG, BIG], "parts": "head", "hide": [],
                "out": str(out / f"{sel}_mini_big.png"), "light": C.LIGHT["helmet"]}
        h = facemask.lstrip("#")
        items.append({"tex": tex, "hide": C.HEAD_HIDE + C.BODY_HIDE, "uv_scale": C.UV_SCALE,
                      "facemask_rgb": [int(h[i:i + 2], 16) for i in (0, 2, 4)], "facemask": "FACEMASK12", "shell": "C",
                      "views": [view]})
        plans.append((letter, Path(view["out"])))
    job = {"head": str(models / "hi_head_o3c115.gltf"), "body": str(models / "hi_body_o3c114.gltf"),
           "arms_down": C.LAYOUT["arms_down"], "morphs": C.LAYOUT["morphs"],
           "replace_parts": C.native_shellc(shellc), "items": items}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=out) as handle:
        json.dump(job, handle)
        job_path = handle.name
    r = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "-P", str(C.BLENDER_SCRIPT), "--", job_path],
                       capture_output=True, text=True)
    Path(job_path).unlink()
    if r.returncode:
        raise SystemExit(f"blender failed: {r.stdout[-2000:]}{r.stderr[-1000:]}")
    result = {}
    for letter, path in plans:
        im = C.saturate(Image.open(path))
        a = np.asarray(im)
        ys, xs = np.where(a[..., 3] > 16)
        crop = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        scale = 60 / max(crop.size)
        crop = crop.resize((max(1, round(crop.width * scale * 4)), max(1, round(crop.height * scale * 4))), Image.LANCZOS)
        canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        canvas.alpha_composite(crop, ((256 - crop.width) // 2, (256 - crop.height) // 2))
        final = C.box_reduce(canvas, 64)
        dest = out / f"mini_{letter.lower()}.png"
        final.save(dest)
        result[letter] = str(dest)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--art", type=Path, required=True)
    p.add_argument("--helmet-master", type=Path, required=True)
    p.add_argument("--shellc", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--facemask", default="009284")
    a = p.parse_args()
    print(render(a.art, a.helmet_master, a.shellc, a.models, a.out, a.facemask))


if __name__ == "__main__":
    main()
