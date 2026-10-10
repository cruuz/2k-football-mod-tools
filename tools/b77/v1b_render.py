#!/usr/bin/env python3
"""b77 v1b: renders of the goalpost as a normal game (35 ft) and a pre-2014 Anniversary moment (30 ft) draw it.

    v1b_render.py --pack0 RETAIL_PACK0 --out DIR

The modern scenes are compiled from the retail pack 0 (the Studio's own compiler), loaded into the Unicorn model of the game
used by tests/mod_editor/test_nfl2k5_period_goalposts.py, and the period goalposts cave is RUN twice: once with a normal game's
state and once with a moment row before 2014. The position streams it leaves in memory are decoded and drawn with the v1 renderer
(offline data renders, a 6 ft silhouette for scale; not a game capture).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools", ROOT / "tests", ROOT / "tools" / "b77"):
    sys.path.insert(0, str(extra))
from PIL import Image  # noqa: E402
import v1_render as r  # noqa: E402
from mod_editor.core import nfl2k5_modern_goalposts as g  # noqa: E402
from mod_editor.core import nfl2k5_period_goalposts as pg  # noqa: E402
from tests.mod_editor.test_nfl2k5_period_goalposts import Cpu, CODE_VA, RO_VA  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack0", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = {x["scene"]: x for x in g.pins()["resources"]}
    spans = r.scene_spans(args.pack0.read_bytes())
    modern = {s: g.decode_span(g.compile_span(span, rows[s])[0]) for s, span in spans.items()}
    after = {}
    for label, (mode, row) in (("normal", (0, 0)), ("moment", (8, 25))):
        cpu = Cpu(modern, mode, row)
        cpu.run(pg.labels(CODE_VA, RO_VA)["stub"])
        scenes = {}
        for s, image in modern.items():
            spec = g.SCENES[s]
            buf = bytearray(image)
            buf[spec["positions"]:spec["positions"] + 6 * spec["vertices"]] = cpu.positions(s)
            scenes[s] = bytes(buf)
        after[label] = scenes
    meshes = {k: r.build_meshes(v["goalpost"], "goalpost") for k, v in after.items()}
    shadows = {k: r.build_meshes(v["goalpost_shadow"], "goalpost_shadow") for k, v in after.items()}
    names = {"normal": "NORMAL GAME: 35 ft above the bar (top 45 ft)", "moment": "MOMENT BEFORE 2014: 30 ft (top 40 ft)"}
    for view in ("front", "side"):
        sheet = Image.new("RGB", (1120, 1060), "white")
        for column, k in enumerate(("normal", "moment")):
            sheet.paste(r.elevation_panel(view, meshes[k], shadows[k], names[k].split(":")[0] + f", {view}", top_label=names[k]),
                        (560 * column, 0))
        sheet.save(args.out / f"v1b_goalpost_{view}_normal_vs_moment.png")
    for k in meshes:
        print(k, round(float(meshes[k][0][:, 1].max()) / 30.48, 3), "ft top;", round(float(shadows[k][0][:, 1].max()) / 30.48, 3), "ft shadow top")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
