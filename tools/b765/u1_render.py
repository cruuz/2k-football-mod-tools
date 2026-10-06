#!/usr/bin/env python3
"""Render actual decoded kit exports; make per-team before/after PNG grids."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
VIEWS = ("front", "side", "back", "helmet")


def render(args) -> None:
    doc = json.loads(args.export.read_text())
    selected = set(args.teams.split(",")) if args.teams else None
    items = []
    for s in doc["sets"]:
        if selected and s["team"] not in selected:
            continue
        art = Path(s["art"])
        tex = {"UNIF_jersey": str(art / "torso.png"), "UNIF_sleeve": str(art / "sleeve.png"),
               "UNIF_pants": str(art / "pants.png"), "SOCKS*": str(art / "socks00.png")}
        for name in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C"):
            tex[name] = str(art / "helmet_helmet02.png")
        # Show 17 for the serif/kerning-sensitive pair. The full 0..9 strips
        # are also copied into every contact sheet.
        tex.update({"NUMBER_L": str(art / "digit_jersey_1.png"),
                    "NUMBER_R": str(art / "digit_jersey_7.png")})
        for shoulder in ("A", "B"):
            for slot, digit in (("L", 1), ("R", 7)):
                tex[f"NUMBER_shoulder_{shoulder}_{slot}"] = str(art / f"digit_arm_{digit}.png")
        hide = ["PLAYERNAME*", "NECKROLL*", "ELBOW*", "WRIST*", "FOREARM*", "TURFTAPE*",
                "SHOE_tapes", "SHOE_spikes", "NUMBER_sleeve*", "NUMBER_M", "NUMBER_shoulder*_M",
                "NUMBER_shoulder_A_M", "NUMBER_shoulder_B_M", "HI_eyeblack", "MOUTHPIECE*",
                "HAIR*", "HI_faceshield*", "NUMBER_helmet*"]
        views = []
        for tag, yaw in (("front", 0), ("side", 90), ("back", 180)):
            views.append({"yaw": yaw, "pitch": 4, "roll": 0, "dist": 5.4, "fov": 23,
                          "target": [0, 0, -0.15], "size": [300, 460], "parts": "all",
                          "samples": 16, "out": str(args.out / f"{s['selector']}_{tag}.png")})
        views.append({"yaw": 95, "pitch": 8, "roll": 0, "dist": 1, "fov": 22,
                      "target": [0, -0.0545, 0.784], "size": [320, 300], "parts": "head",
                      "samples": 16, "out": str(args.out / f"{s['selector']}_helmet.png")})
        h = s["facemask"].lstrip("#")
        items.append({"tex": tex, "hide": hide, "shell": "C", "facemask": "FACEMASK12",
                      "facemask_rgb": [int(h[i:i+2], 16) for i in (0, 2, 4)],
                      "skin": [120, 86, 60], "views": views,
                      "uv_scale": {"NUMBER_L": [4, 2], "NUMBER_R": [4, 2],
                                   "NUMBER_shoulder*": [4, 2]}})
    args.out.mkdir(parents=True, exist_ok=True)
    names = ["HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C", "FACEMASK12"]
    def chunk_run(i):
        job = {"head": str(args.head), "body": str(args.body), "arms_down": 60,
               "replace_parts": {"json": str(args.geometry), "names": names},
               "items": items[i::args.jobs]}
        path = args.out / f"job_{i}.json"
        path.write_text(json.dumps(job))
        with (args.out / f"blender_{i}.log").open("w") as log:
            proc = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1",
                                   "-P", str(HERE / "u1_blender.py"),
                                   "--", str(path)], stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode:
            raise RuntimeError(f"Blender failed; inspect {args.out / f'blender_{i}.log'}")
    with ThreadPoolExecutor(args.jobs) as executor:
        list(executor.map(chunk_run, range(args.jobs)))
    images = []
    for item in items:
        for view in item["views"]:
            path = Path(view["out"])
            with Image.open(path) as im:
                im.load()
                if list(im.size) != view["size"]:
                    raise RuntimeError(f"Render dimensions differ: {path}")
            images.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "size": view["size"]})
    (args.out / "render_receipt.json").write_text(json.dumps({
        "schema": "b765/u1/offline-render-receipt/v1", "sets": len(items),
        "export_sha256": hashlib.sha256(args.export.read_bytes()).hexdigest(),
        "geometry_sha256": hashlib.sha256(args.geometry.read_bytes()).hexdigest(),
        "views": images}, indent=2) + "\n")
    print(f"rendered {len(items)} sets in {len(items)*4} views")


def sheets(args) -> None:
    before = json.loads(args.export.read_text())
    after = json.loads(args.after_export.read_text()) if args.after_export else before
    after_by = {s["selector"]: s for s in after["sets"]}
    teams = sorted({s["team"] for s in before["sets"]})
    if args.teams:
        selected = set(args.teams.split(","))
        if selected - set(teams):
            raise ValueError("contact-sheet team absent from baseline export")
        teams = [team for team in teams if team in selected]
    args.out.mkdir(parents=True, exist_ok=True)
    for team in teams:
        sets = [s for s in before["sets"] if s["team"] == team]
        width, height = 2460, 550 * len(sets)
        sheet = Image.new("RGB", (width, height), (38, 42, 54))
        draw = ImageDraw.Draw(sheet)
        for n, s in enumerate(sets):
            y = n * 550
            for phase, paths, row, x in (("BEFORE", args.before, s, 0),
                                         ("AFTER", args.after, after_by[s["selector"]], 1230)):
                draw.text((x + 5, y + 5), f"{team} {s['selector']} {phase} (offline render)", fill="white")
                cursor = x
                for tag in VIEWS:
                    path = paths / f"{s['selector']}_{tag}.png"
                    im = Image.open(path).convert("RGBA")
                    bg = Image.new("RGBA", im.size, (60, 64, 78, 255))
                    bg.alpha_composite(im)
                    bg.thumbnail((300, 460))
                    sheet.paste(bg.convert("RGB"), (cursor, y + 25))
                    cursor += 305
                for digit in range(10):
                    im = Image.open(Path(row["art"]) / f"digit_jersey_{digit}.png").convert("RGBA")
                    sheet.paste(im, (x + digit * 70, y + 480), im)
        sheet.save(args.out / f"{team}_before_after.png")
    print(f"contact sheets: {len(teams)} teams")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render")
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--head", type=Path, required=True)
    p.add_argument("--body", type=Path, required=True)
    p.add_argument("--geometry", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--teams", default="")
    p = sub.add_parser("sheets")
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--after-export", type=Path)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--teams", default="")
    args = parser.parse_args()
    (render if args.command == "render" else sheets)(args)


if __name__ == "__main__":
    main()
