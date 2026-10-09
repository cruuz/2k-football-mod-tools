#!/usr/bin/env python3
"""Beta 77 u1: the Patriots' Team Select cards re-rendered from the corrected 2026 kit art.

The 70 2026 sets' cards were rendered by job k2 (2026-09-25, "cards v5": Blender on the Studio's hi_body/hi_head
exports with the shell C dump pinned at edbff6021, mask 12). This is the same layout, cameras, light and composition,
driven through the repository's own renderer (tools/b765/u1_blender.py, k2's card renderer plus the helmet-number
alpha fix), so the Patriots' cards match the other 69 sets' look:

  team-select_unif_256   pants, jersey (a "30") and helmet layers composed in the retail card layout
  team-select_helm_256   the helmet over the retail UI bar (home: its left side; road: its right side, never mirrored)
  team-select_helm_128   the 256 card box-reduced

  u1_cards.py --art ART/retail --helmet02-master ART/master4x --bars V05_CARDS --shellc SHELLC.json \
      --models MODELS_DIR --out OUT [--facemask C8102E]

``--bars``: the shipped helm cards (helm_h16_0_256.png / helm_a16_0_256.png) whose rows from 158 down are the retail UI
bar. Blender (4.x) and the Studio's model exports are authoring inputs; nothing here ships with the Studio.
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

ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPT = ROOT / "tools/b765/u1_blender.py"
M = 4                                     # masters are 1024 px for the 256 cards
HELM_BAR_TOP = 158
SATURATION = 1.2
HEAD_HIDE = ["SKIN*", "HI_turtleneck", "HAIR*", "HI_eyeblack", "MOUTHPIECE*", "HI_faceshield*", "NUMBER_helmet*"]
BODY_HIDE = ["PLAYERNAME*", "NECKROLL*", "ELBOW*", "WRIST*", "FOREARM*", "TURFTAPE*", "SHOE_tapes", "SHOE_spikes",
             "NUMBER_sleeve*", "SKIN*", "SHOE*", "SOCKS"]
UV_SCALE = {"NUMBER_L": [4, 1.6], "NUMBER_M": [4, 1.6], "NUMBER_R": [4, 1.6], "NUMBER_shoulder*": [4, 1.6],
            "NUMBER_sleeve*": [4, 1.6], "NUMBER_helmet*": [4, 2]}
SHELLC_PARTS = ["HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C", "FACEMASK12"]


def native_shellc(path: Path) -> dict:
    """Reject an already flipped glTF UV dump before the shared renderer flips V.

    The native shell puts the player's right side in the upper atlas island.
    Its V increases with physical height; the lower island has the opposite sign.
    Checking that contract prevents an input-space error from silently inverting
    every asymmetric mark. Geometry stays read only.
    """
    data = json.loads(path.read_text(encoding="utf-8"))["HI_HELMET_C"]
    pos, uv = data["pos"], data["uv"]
    if len(pos) != len(uv):
        raise ValueError("shell C position/UV counts differ")
    for sign, expected in ((-1, 1), (1, -1)):
        pairs = [(p[1], t[1]) for p, t in zip(pos, uv) if p[0]*sign > 5 and 37 < p[1] < 53 and -1 < p[2] < 12]
        if len(pairs) < 6:
            raise ValueError("shell C has insufficient native atlas landmarks")
        y = sum(p[0] for p in pairs)/len(pairs)
        v = sum(p[1] for p in pairs)/len(pairs)
        covariance = sum((p[0]-y)*(p[1]-v) for p in pairs)
        if covariance*expected <= 0 or not (v < .5 if sign < 0 else v > .5):
            raise ValueError("shell C UVs must use native top-left atlas coordinates, before Blender's V conversion")
    return {"json": str(path), "names": SHELLC_PARTS, "uv_origin": "native_top_left"}
# k2's layout and its fitted cameras (cards/ref/cameras_v5c.json, shell C)
LAYOUT = {
    "arms_down": 30,
    "morphs": {"jersey_shoulderpad_big": 1.0, "pants_thighpad_thick": 0.6},
    "jersey": {"parts": "body", "view": {"yaw": 24, "pitch": 12, "roll": 0, "dist": 3.3, "target": [0, 0, 0.3]},
               "hide": ["UNIF_pants"]},
    "pants": {"parts": "body", "view": {"yaw": 88, "pitch": 6, "roll": -4, "dist": 3.3, "target": [0, 0, -0.3]},
              "hide": ["UNIF_jersey", "UNIF_sleeve", "NUMBER*"]},
    "helmet": {"parts": "head", "view": {"yaw": -112, "pitch": 16, "roll": -6, "dist": 1.0,
                                         "target": [0, -0.0545, 0.784]}, "hide": []},
    "helm_card": {"parts": "head", "view": {"yaw": 100, "pitch": 12, "roll": 8, "dist": 1.0,
                                            "target": [0, -0.0545, 0.784]}, "hide": []},
}
CAMERAS = {
    "jersey": {"fov": 11.108986474496744, "shift_x": 0.05926957179930792, "shift_y": 0.12118836505190311},
    "pants": {"fov": 11.953518568558836, "shift_x": -0.412828947368421, "shift_y": 0.41488486842105254},
    "helmet": {"fov": 28.111493987487158, "shift_x": 0.2657660835214447, "shift_y": 0.31511004514672686},
    "helm_card": {"fov": 18.00322428256025, "shift_x": -0.06435351995565419, "shift_y": -0.07434000831485588},
}
LIGHT = {
    "helmet": {"ambient": 0.7, "world_bottom": [0.02, 0.03, 0.02], "world_top": [1.2, 1.25, 1.3],
               "horizon": [0.3, 0.9], "sun": 1.6, "sun_cam": [25, -45], "helmet_roughness": 0.3,
               "helmet_specular": 0.4, "helmet_coat": 0.5, "helmet_coat_roughness": 0.03, "facemask_metallic": 0.3},
    "cloth": {"ambient": 0.55, "world_bottom": [0.15, 0.15, 0.15], "world_top": [1.1, 1.1, 1.1],
              "horizon": [-0.2, 0.9], "sun": 2.4, "sun_cam": [30, -35], "rim": 1.0, "rim_cam": [20, 150],
              "cloth_roughness": 0.5, "cloth_specular": 0.35},
}


def torso_card(torso_png: Path, out_png: Path) -> str:
    """The card shows the inside of the collar: the neck openings become a dark shade of the jersey colour (k2)."""
    sys.path.insert(0, str(ROOT / "tools"))
    from nfl2k5_team_2026_art import torso_neck_mask
    t = np.asarray(Image.open(torso_png).convert("RGBA")).astype(np.float32)
    mask = torso_neck_mask(t.shape[:2]) > 0.5
    body = np.median(t[..., :3][~mask].reshape(-1, 3), axis=0)
    t[mask, :3] = body * 0.3
    Image.fromarray(t.clip(0, 255).astype(np.uint8)).save(out_png)
    return str(out_png)


def view(name: str, side: str, out: Path) -> dict:
    lay = LAYOUT[name]
    v = dict(lay["view"]); v.update(CAMERAS[name])
    if name == "helm_card" and side == "A":
        v["yaw"], v["roll"], v["shift_x"] = -v["yaw"], -v["roll"], -v.get("shift_x", 0.0)
    v.update({"size": [256 * M, 256 * M], "parts": lay["parts"], "hide": list(lay["hide"]), "out": str(out),
              "light": LIGHT["cloth" if name in ("jersey", "pants") else "helmet"]})
    return v


def saturate(im: Image.Image, factor: float = SATURATION) -> Image.Image:
    a = np.asarray(im.convert("RGBA")).astype(np.float32) / 255.0
    grey = (a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    a[..., :3] = np.clip(grey + (a[..., :3] - grey) * factor, 0, 1)
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA")


def box_reduce(im: Image.Image, size: int) -> Image.Image:
    a = np.asarray(im.convert("RGBA")).astype(np.float64) / 255.0
    f = a.shape[0] // size
    pm = a.copy(); pm[..., :3] *= pm[..., 3:4]
    r = pm.reshape(size, f, size, f, 4).mean(axis=(1, 3))
    al = r[..., 3:4]
    rgb = np.where(al > 1e-6, r[..., :3] / np.maximum(al, 1e-6), 0.0)
    return Image.fromarray((np.concatenate([rgb, al], axis=2) * 255 + 0.5).clip(0, 255).astype(np.uint8), "RGBA")


def render(art: Path, helmet02_master: Path, bars: Path, shellc: Path, models: Path, out: Path,
           facemask: str = "C8102E", number: str = "30") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"; work.mkdir(exist_ok=True)
    items, plans = [], []
    for sel in ("16H0", "16A0"):
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
           "replace_parts": native_shellc(shellc), "items": items}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=work) as handle:
        json.dump(job, handle)
        job_path = handle.name
    r = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "-P", str(BLENDER_SCRIPT), "--",
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
        bar_name = f"helm_{'h' if sel[2] == 'H' else 'a'}16_0_256.png"
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
    p.add_argument("--art", type=Path, required=True, help="kit natives: <dir>/<16H0|16A0>/torso.png ...")
    p.add_argument("--helmet02-master", type=Path, required=True)
    p.add_argument("--bars", type=Path, required=True)
    p.add_argument("--shellc", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--facemask", default="C8102E")
    a = p.parse_args()
    render(a.art, a.helmet02_master, a.bars, a.shellc, a.models, a.out, a.facemask)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
