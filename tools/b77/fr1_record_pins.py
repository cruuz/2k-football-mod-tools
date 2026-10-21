#!/usr/bin/env python3
"""fr1: write data/nfl2k5_modern_fans/pins.json from a retail USA image and the shipped fan art (read only)."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_fans as mf  # noqa: E402

# 2026 team -> the club's 2K5 asset code; ORDER is the 85 asset codes in archive order (the crowd sets are code order)
CODES = {"ARI": 0, "ATL": 1, "BAL": 2, "BUF": 3, "CAR": 4, "CHI": 5, "CIN": 6, "DAL": 7, "DEN": 8, "DET": 9, "GB": 10,
         "IND": 11, "JAX": 12, "KC": 13, "MIA": 14, "MIN": 15, "NE": 16, "NO": 17, "NYG": 18, "NYJ": 19, "LV": 20,
         "PHI": 21, "PIT": 22, "LAR": 23, "LAC": 24, "SF": 25, "SEA": 26, "TB": 27, "TEN": 28, "WAS": 29, "CLE": 30,
         "HOU": 37}
ORDER = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
         30, 31, 33, 34, 35, 36, 37, 40, 41, 42, 43, 44, 45, 46, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63,
         64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 95, 96, 97, 98, 99]


# the close-up scenes with embedded textures this option replaces (art in data/nfl2k5_modern_fans/scenes/)
SCENES = [
    dict(scene="crowds13", team="KC", textures=[dict(material="y_hats29_feathers", art="scenes/crowds13_y_hats29_feathers.png"),
                                                dict(material="z_hats29_headdress", art="scenes/crowds13_z_hats29_headdress.png")]),
    dict(scene="crowds29", team="WAS", textures=[dict(material="y_hats29_feathers", art="scenes/crowds29_y_hats29_feathers.png"),
                                                 dict(material="z_hats29_headdress", art="scenes/crowds29_z_hats29_headdress.png")]),
    dict(scene="crowddrink", team=None, textures=[dict(material="drinkleft", art="scenes/crowddrink_drinkleft.png")]),
]


def _one_team(job):
    retail, team = job
    return mf.record_pins(retail, mf.DATA_DIR, {team: CODES[team]}, ORDER)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retail", required=True)
    p.add_argument("--write", action="store_true")
    p.add_argument("--scenes-only", action="store_true", help="keep the texture parts of pins.json, re-record scenes")
    p.add_argument("--jobs", type=int, default=6)
    a = p.parse_args(argv)
    t0 = time.time()
    if a.scenes_only:
        doc = json.loads(mf.PINS_PATH.read_text(encoding="utf-8"))
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=a.jobs) as pool:
            docs = list(pool.map(_one_team, [(a.retail, team) for team in CODES]))
        doc = dict(docs[0], parts=[p for d in docs for p in d["parts"]])
    doc["codes"] = CODES
    doc["scenes"] = mf.record_scene_pins(a.retail, SCENES)
    print("scenes", [(sc["scene"], sc["outer_index"], sc["palette_max"]) for sc in doc["scenes"]])
    # the name ids of the ns and tg families are nsNN.iff / tgNN.iff (CRC-32 of the upper-case UTF-16LE name);
    # sets A and B are pinned by their outer ids (their file names are not known)
    for part in doc["parts"]:
        if part["set"] in ("ns", "tg"):
            assert int(part["outer_id"], 16) == mf._mm().name_id(f"{part['set']}{part['code']:02d}.iff"), part
    text = json.dumps(doc, indent=1) + "\n"
    if a.write:
        mf.PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
    import collections
    pal = collections.Counter(pt["palette_max"] for pt in doc["parts"])
    print("parts", len(doc["parts"]), "palettes", dict(pal), f"{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
