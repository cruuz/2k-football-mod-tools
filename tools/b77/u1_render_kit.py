#!/usr/bin/env python3
"""Beta 77 u1: render decoded kit textures on the Studio's rest-pose hi body and head (Blender, tools/b765/u1_blender.py).

The comparison method of the Patriots job, for the all-teams uniform work: render a kit folder as the Studio exports it
(torso.png, sleeve.png, pants.png, socks00.png, helmet_helmet02.png, digit_*.png) from fixed cameras, then crop next to
the club's photos at matched number height. Shell C helmet parts come from the geometry dump (``--helmet-geometry``).

  u1_render_kit.py OUT_DIR LABEL=ART_DIR[:FACEMASK_HEX[:NUMBER]] ... --models DIR --helmet-geometry JSON
                   [--views full|torso|helmet|pants|all] [--jobs N]

Views: full (front, back, sides, quarters), torso (front, back, elevated back, quarters, sides), helmet (sides, back,
front, rear quarters), pants (sides, front, back). Output PNGs are named LABEL_<view>.png. Read only: no game file is
written. Blender must be on PATH.
"""
import argparse
import json
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]

HIDE = ["PLAYERNAME*", "NECKROLL*", "ELBOW*", "WRIST*", "FOREARM*", "TURFTAPE*", "SHOE_tapes", "SHOE_spikes",
        "NUMBER_sleeve*", "NUMBER_M", "NUMBER_shoulder*_M", "HI_eyeblack", "MOUTHPIECE*", "HAIR*", "HI_faceshield*",
        "NUMBER_helmet_A*", "NUMBER_helmet_B*", "NUMBER_helmet_D*", "NUMBER_helmet_C_M"]

FULL = [("front", 0, 4), ("back", 180, 4), ("left", 90, 4), ("right", 270, 4), ("q_front_l", 40, 8), ("q_back_r", 220, 8)]
TORSO = [("t_front", 0, 6), ("t_back", 180, 6), ("t_top_front", 0, 38), ("t_top_back", 180, 38), ("t_q_l", 55, 10),
         ("t_q_r", -55, 10), ("t_side_l", 90, 6), ("t_side_r", 270, 6)]
HELMET = [("h_left", 90, 8), ("h_right", 270, 8), ("h_back", 180, 10), ("h_front", 0, 6), ("h_back_l", 135, 12),
          ("h_back_r", 225, 12)]
PANTS = [("p_left", 90, 0), ("p_right", 270, 0), ("p_front", 0, 0), ("p_back", 180, 0)]


def item_for(label, art, facemask, number, out, views, shell="C"):
    art = Path(art)
    tens, units = (number // 10, number % 10) if number >= 10 else (None, number)
    tex = {"UNIF_jersey": str(art / "torso.png"), "UNIF_sleeve": str(art / "sleeve.png"),
           "UNIF_pants": str(art / "pants.png"), "SOCKS*": str(art / "socks00.png")}
    # shell C (Revolution, raw 1) wears helmet02; shell A (Standard, raw 0) wears helmet00 (nfl_live_helmet_txtr_compatibility)
    helmet_png = str(art / ("helmet_helmet02.png" if shell == "C" else "helmet_helmet00.png"))
    for name in (("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C") if shell == "C"
                 else ("HI_HELMET_A", "HELMET_A_accessories", "LOGO_helmet")) + ("HI_HELMET_flag", "LOGO_nfl"):
        tex[name] = helmet_png
    hide = [h for h in HIDE if h not in ("NUMBER_helmet_A*", "NUMBER_helmet_C_M")] if shell == "A" else list(HIDE)
    if shell == "A":
        hide += ["NUMBER_helmet_C*", "NUMBER_helmet_A_M"]
    hn = f"NUMBER_helmet_{shell}"
    if tens is None:
        tex["NUMBER_L"] = str(art / f"digit_jersey_{units}.png"); hide += ["NUMBER_R"]
        tex[hn + "_L"] = str(art / f"digit_helmet_{units}.png"); hide += [hn + "_R"]
    else:
        tex["NUMBER_L"] = str(art / f"digit_jersey_{tens}.png"); tex["NUMBER_R"] = str(art / f"digit_jersey_{units}.png")
        tex[hn + "_L"] = str(art / f"digit_helmet_{tens}.png")
        tex[hn + "_R"] = str(art / f"digit_helmet_{units}.png")
    for sh in ("A", "B"):
        for slot, d in (("L", tens if tens is not None else units), ("R", units)):
            tex[f"NUMBER_shoulder_{sh}_{slot}"] = str(art / f"digit_arm_{d}.png")
    vs = []
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    if views in ("full", "all"):
        for tag, yaw, pitch in FULL:
            vs.append({"yaw": yaw, "pitch": pitch, "dist": 5.4, "fov": 23, "target": [0, 0, -0.15], "size": [420, 640],
                       "parts": "all", "samples": 24, "out": str(out / f"{label}_{tag}.png")})
    if views in ("torso", "all"):
        for tag, yaw, pitch in TORSO:
            vs.append({"yaw": yaw, "pitch": pitch, "dist": 2.6, "fov": 23, "target": [0, 0, 0.42], "size": [640, 600],
                       "parts": "all", "samples": 24, "out": str(out / f"{label}_{tag}.png"),
                       "hide": ["HI_HELMET*", "HELMET_*", "LOGO_*", "FACEMASK*"]})
    if views in ("helmet", "all"):
        for tag, yaw, pitch in HELMET:
            vs.append({"yaw": yaw, "pitch": pitch, "dist": 1.0, "fov": 24, "target": [0, -0.0545, 0.784],
                       "size": [600, 560], "parts": "head", "samples": 24, "out": str(out / f"{label}_{tag}.png")})
    if views in ("pants", "all"):
        for tag, yaw, pitch in PANTS:
            vs.append({"yaw": yaw, "pitch": pitch, "dist": 3.0, "fov": 23, "target": [0, 0, -0.45], "size": [480, 640],
                       "parts": "body", "samples": 24, "out": str(out / f"{label}_{tag}.png")})
    h = facemask.lstrip('#')
    uv = {"NUMBER_L": [4, 2], "NUMBER_R": [4, 2], "NUMBER_shoulder*": [4, 2], "NUMBER_helmet_C_L": [4, 2],
          "NUMBER_helmet_C_R": [4, 2], "NUMBER_helmet_A_L": [4, 2], "NUMBER_helmet_A_R": [4, 2]}
    return {"tex": tex, "hide": hide, "shell": shell, "facemask": "FACEMASK12",
            "facemask_rgb": [int(h[i:i + 2], 16) for i in (0, 2, 4)], "skin": [120, 86, 60], "views": vs,
            "uv_scale": uv, "shoe": [20, 20, 22]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("kits", nargs="+", help="LABEL=ART_DIR[:FACEMASK_HEX[:NUMBER]]")
    p.add_argument("--models", required=True, type=Path, help="folder with hi_head_o3c115.gltf and hi_body_o3c114.gltf")
    p.add_argument("--helmet-geometry", required=True, type=Path, help="shell C geometry dump (JSON)")
    p.add_argument("--views", default="all", choices=["full", "torso", "helmet", "pants", "all"])
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--shell", default="C", choices=["C", "A"], help="C: Revolution (helmet02, geometry dump); A: Standard (helmet00, retail glTF shell)")
    a = p.parse_args()
    out, views, jobs = a.out, a.views, max(1, a.jobs)
    items = []
    for kit in a.kits:
        label, rest = kit.split("=", 1)
        parts = rest.split(":")
        art = parts[0]; fm = parts[1] if len(parts) > 1 and parts[1] else "C8102E"
        num = int(parts[2]) if len(parts) > 2 else 17
        items.append(item_for(label, art, fm, num, out, views, a.shell))
    out.mkdir(parents=True, exist_ok=True)

    def run(i):
        job = {"head": str(a.models / "hi_head_o3c115.gltf"), "body": str(a.models / "hi_body_o3c114.gltf"),
               "arms_down": 60,
               "items": items[i::jobs]}
        if a.shell == "C":
            job["replace_parts"] = {"json": str(a.helmet_geometry),
                                    "names": ["HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C", "FACEMASK12"]}
        if not job["items"]:
            return
        p = out / f"job_{i}.json"; p.write_text(json.dumps(job))
        with open(out / f"blender_{i}.log", "w") as log:
            r = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "-P",
                                str(ROOT / "tools/b765/u1_blender.py"), "--", str(p)], stdout=log, stderr=subprocess.STDOUT)
        if r.returncode:
            raise SystemExit(f"blender failed, see {out}/blender_{i}.log")
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(run, range(jobs)))
    print("rendered", len(items), "items")


if __name__ == "__main__":
    main()
