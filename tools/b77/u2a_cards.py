#!/usr/bin/env python3
"""Beta 77 u2a: Team Select cards for any team, re-rendered from its corrected 2026 kit art.

Same layout, cameras and light as the Patriots job (tools/b77/u1_cards.py, which itself reuses job k2's card
renderer); only the team code differs (selectors ``<code>H0``/``<code>A0`` and the shipped helm bars
``helm_h<code>_0_256.png``).

  u2a_cards.py --code 03 --art ART --helmet02-master M4 --bars V05_CARDS --shellc SHELLC.json --models MODELS --out OUT
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
from u1_cards import (BODY_HIDE, HEAD_HIDE, HELM_BAR_TOP, LAYOUT, M, SHELLC_PARTS, UV_SCALE, box_reduce,  # noqa: E402,F401
                      saturate, torso_card, view)


def render(art: Path, helmet02_master: Path, bars: Path, shellc: Path, models: Path, out: Path, code: str,
           facemask: str = "C8102E", number: str = "30") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"; work.mkdir(exist_ok=True)
    items, plans = [], []
    for sel in (f"{code}H0", f"{code}A0"):
        a = art / sel
        tex = {"UNIF_jersey": torso_card(a / "torso.png", work / f"torso_card_{sel}.png"),
               "UNIF_sleeve": str(a / "sleeve.png"), "UNIF_pants": str(a / "pants.png")}
        helmet = str(helmet02_master / sel / "helmet_helmet02.png")
        tex.update({k: helmet for k in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C")})
        hide = []
        for pos, digit in (("L", number[0]), ("R", number[1])):
            tex[f"NUMBER_{pos}"] = str(a / f"digit_jersey_{digit}.png")
            for sh in ("shoulder_A", "shoulder_B"):
                tex[f"NUMBER_{sh}_{pos}"] = str(a / f"digit_arm_{digit}.png")
        hide += ["NUMBER_M", "NUMBER_shoulder_A_M", "NUMBER_shoulder_B_M"]
        layers = {n: work / f"{sel}_{n}.png" for n in ("jersey", "pants", "helmet", "helm_card")}
        h = facemask.lstrip("#")
        items.append({"tex": tex, "hide": hide + BODY_HIDE + HEAD_HIDE, "uv_scale": UV_SCALE,
                      "facemask_rgb": [int(h[i:i + 2], 16) for i in (0, 2, 4)], "facemask": "FACEMASK12",
                      "shell": "C", "views": [view(n, sel[2], p) for n, p in layers.items()]})
        plans.append((sel, layers))
    job = {"head": str(models / "hi_head_o3c115.gltf"), "body": str(models / "hi_body_o3c114.gltf"),
           "arms_down": LAYOUT["arms_down"], "morphs": LAYOUT["morphs"],
           "replace_parts": C.native_shellc(shellc), "items": items}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=work) as handle:
        json.dump(job, handle)
        job_path = handle.name
    r = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "-P", str(C.BLENDER_SCRIPT), "--",
                        job_path], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"blender failed: {r.stdout[-2000:]}{r.stderr[-1000:]}")
    manifest = {}
    for sel, layers in plans:
        mdir, ndir = out / "master4x" / sel, out / sel
        mdir.mkdir(parents=True, exist_ok=True); ndir.mkdir(parents=True, exist_ok=True)
        size = 256 * M
        card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for name in ("pants", "jersey", "helmet"):
            card = Image.alpha_composite(card, saturate(Image.open(layers[name])))
        card.save(mdir / "team-select_unif_256.png")
        box_reduce(card, 256).save(ndir / "team-select_unif_256.png")
        helm = np.asarray(saturate(Image.open(layers["helm_card"]))).copy()
        bar_name = f"helm_{'h' if sel[2] == 'H' else 'a'}{code}_0_256.png"
        bar = np.asarray(Image.open(bars / bar_name).convert("RGBA").resize((size, size), Image.NEAREST))
        helm[HELM_BAR_TOP * M:] = bar[HELM_BAR_TOP * M:]
        hm = Image.fromarray(helm)
        hm.save(mdir / "team-select_helm_256.png")
        box_reduce(hm, 256).save(ndir / "team-select_helm_256.png")
        h128 = box_reduce(hm, 512)
        h128.save(mdir / "team-select_helm_128.png")
        box_reduce(h128, 128).save(ndir / "team-select_helm_128.png")
        manifest[sel] = [str(ndir / f"team-select_{k}.png") for k in ("unif_256", "helm_256", "helm_128")]
    (out / "cards_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--code", required=True)
    p.add_argument("--art", type=Path, required=True)
    p.add_argument("--helmet02-master", type=Path, required=True)
    p.add_argument("--bars", type=Path, required=True)
    p.add_argument("--shellc", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--facemask", default="000000")
    a = p.parse_args()
    render(a.art, a.helmet02_master, a.bars, a.shellc, a.models, a.out, a.code, a.facemask)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
