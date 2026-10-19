#!/usr/bin/env python3
"""Author the Super Bowl LVI kits job rk1 adds (Noah 10/18: "those aren't even the Rams' correct jerseys"; the Rams
"need their old jerseys ... that have a bit of that gradient"). Writes two entries into data/nfl2k5_moment_kits.json
(ids RK1-LAR and RK1-CIN), points both sides of moment row 48 (donald_fourth_down, Super Bowl LVI) at them and makes
them the main uniform of the two moment team files. Nothing else in the file changes.

What each team wore in Super Bowl LVI (Feb 13 2022, SoFi Stadium; the Bengals were the designated home team):

* Rams: the white "modern throwback" (introduced July 2021): white jersey, royal numerals in the 2020 number font
  (no gradient), royal horns on sol (yellow) capped sleeves, no sleeve numbers, sol pants with a royal-white-royal
  stripe, royal socks, the 2020 metallic royal helmet with the sol horn and a royal facemask. (SportsLogos.net
  2022-02-02, Sports Illustrated 2022-02-02, therams.com 2021-07-13, GUD 2021_LAR_D2.)
* Bengals: black home jersey, white pants with orange tiger stripes outlined in black, orange socks, the orange
  striped helmet (NFL.com / SportsLogos.net 2022-02-02, GUD 2021_CIN_I2).

The gradient numerals Noah remembers (sol at the top fading to white at the bottom) belong to the 2020-2025 ROYAL
home jersey (SportsLogos.net 2020-05-13; the Rams dropped the gradient for 2026). So the new Rams slot carries the
whole 2020-2025 set: H = the royal home with the gradient numerals, A = the exact Super Bowl LVI white. The moment
draws the Rams' A side (they are the visitors).

Index: the Rams have no free style index (0..12 listed, 13 = ek1's K11 Super Bowl LVI kit, 14 = the historic-styles
spare, nfl2k5_espn25_rosters.HISTORIC_SPARES), so RK1-LAR takes K11's index 13. K11 was used only by this moment side
and by the 2021 Rams moment team file (the same team-season), so no other player, team or mode changes. The Bengals
kit takes the free index 06:13 (06:8 stays the Bengals' spare).

Art (vector operations for the kit compiler, nfl2k5_kit_fixes_2026 ops; no reference pixels ship):

* RK1-LAR H: the 2026 royal home (23H0, which already has the 2020 font, the sol shoulder horns, sol pants and the
  2020 helmet) with its solid sol numerals redrawn row by row in a sol-to-white gradient. The numeral shapes are the
  kit's own (each texel row of the 2026 numerals at alpha >= 128, measured from the donor and written as plain
  rectangles); the gradient profile follows the GUD 2021 home graphic: solid sol for the top 30 percent, then an even
  fade to white at 92 percent of the numeral height.
* RK1-LAR A: the 1999 white road body (23A2: white jersey, sol sleeve caps with royal horns, sol pants with the
  royal-white-royal stripe) with the 2020-era parts of 23A0: helmet, royal facemask and turtleneck colours, royal
  socks (also on the far players), modern equipment, the royal 2020-font numerals (their dark navy edge recoloured
  royal: the real numerals are solid royal), the modern name font, and no sleeve or helmet numbers.
* RK1-CIN H: the 2021-2026 black home (06H0) over the white road pants (06A0) whose black tiger stripes become orange
  outlined in black, with the orange sock band of the home kit. A = a byte copy of the white road kit (06A0).

  rk1_kits_author.py --donors DIR_WITH_23H0.IFF_23A0.IFF_23A2.IFF_06H0.IFF_06A0.IFF [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_moment_kits.json"

SOL, WHITE, ROYAL, NAVY_EDGE = (255, 209, 0), (255, 255, 255), "#003594", "#031361"
OLD_GOLD, OLD_ROYAL = "#FCB200", "#0F337C"     # the 1999 kit's gold (252, 178, 0) and royal (15, 51, 124)
BENGAL_ORANGE, BLACK = "#FB4F14", "#000000"
RAMS_FILE, BENGALS_FILE = "h-23-2021-rams-9.iff", "h-06-2021-bengals-9.iff"
ROW = 48
GRADIENT = (0.30, 0.92)          # fraction of the numeral height: solid sol above the first, white below the second


def hexc(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def measure(donors):
    """Numbers the art needs from the donor packages: texture names and the 23H0 numeral masks."""
    sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b765")]
    import numpy as np
    from nfl_txtr import parse_chunks, decode_chunk, parse_texture, texture_to_rgba
    from mod_editor.core import nfl2k5_kit_fixes_2026 as fx

    def names(sel):
        raw = (Path(donors) / f"{sel}.IFF").read_bytes()
        out = {}
        for c in parse_chunks(raw)[:53]:
            if c.kind not in ("TSET", "TXTR"):
                continue
            try:
                t = fx.native_textures(raw[c.offset:c.end_offset], c.kind.lower())[2][0]
            except Exception:  # noqa: BLE001
                continue
            out[c.index] = [t["name"], t["width"], t["height"], t["mips"]]
        return out

    m = {"names": {s: names(s) for s in ("23H0", "23A0", "06A0")}, "digits": {}}
    raw = (Path(donors) / "23H0.IFF").read_bytes()
    chunks = parse_chunks(raw)
    for index in range(13, 23):
        decoded, _ = decode_chunk(raw, chunks[index])
        t = parse_texture(decoded, chunks[index])
        a = np.frombuffer(texture_to_rgba(decoded, chunks[index], t), np.uint8).reshape(t.height, t.width, 4)
        rows = {}
        for y in range(t.height):
            xs = np.flatnonzero(a[y, :, 3] >= 128)
            if not len(xs):
                continue
            runs, start = [], int(xs[0])
            for p, q in zip(xs, xs[1:]):
                if q != p + 1:
                    runs.append([start, int(p) + 1])
                    start = int(q)
            runs.append([start, int(xs[-1]) + 1])
            rows[y] = runs
        m["digits"][index] = rows
    ys = [y for rows in m["digits"].values() for y in rows]
    m["numeral_rows"] = [min(ys), max(ys)]
    return m


def gradient(y, top, bottom):
    t = (y + 0.5 - top) / (bottom + 1 - top)
    a, b = GRADIENT
    f = min(1.0, max(0.0, (t - a) / (b - a)))
    return tuple(int(round(s + (w - s) * f)) for s, w in zip(SOL, WHITE))


def gradient_digits(m):
    """The 23H0 numerals, binary alpha, one colour per texel row."""
    top, bottom = m["numeral_rows"]
    names = m["names"]["23H0"]
    rows_out = []
    for index in range(13, 23):
        name, tw, th, mips = names[index]
        ops = [{"op": "poly", "points": [[0, 0], [tw, 0], [tw, th], [0, th]], "color": hexc(SOL), "alpha": 0}]
        for y, runs in sorted(m["digits"][index].items()):
            ops.append({"op": "multipoly", "color": hexc(gradient(y, top, bottom)), "alpha": 255,
                        "polys": [[[x0, y], [x1, y], [x1, y + 1], [x0, y + 1]] for x0, x1 in runs]})
        rows_out.append({"chunk": index, "kind": "txtr", "texture": name, "size": [tw, th, mips], "ops": ops,
                         "max_blend_slots": 12, "reencode": True})
    return rows_out


def solid_royal_digits(m):
    names = m["names"]["23A0"]
    out = []
    for index in range(13, 23):
        name, tw, th, mips = names[index]
        out.append({"chunk": index, "kind": "txtr", "texture": name, "size": [tw, th, mips], "reencode": True,
                    "ops": [{"op": "recolor", "box": [0, 0, tw, th], "from": [NAVY_EDGE], "color": ROYAL,
                             "tolerance": 40}]})
    return out


def era_colours():
    """The 1999 body's New Century gold and its darker royal become the 2020 sol and Rams royal (palette swaps that
    keep the cloth shading): torso, pants, sleeves and the far-player atlas."""
    mapping = [{"from": OLD_GOLD, "to": hexc(SOL)}, {"from": OLD_ROYAL, "to": ROYAL}]
    rows = [{"chunk": c, "kind": "palette_map", "texture_kind": "tset", "tolerance": 40, "map": mapping}
            for c in (1, 2, 3)]
    rows.append({"chunk": 51, "kind": "palette_map", "texture_kind": "txtr", "tolerance": 40, "map": mapping})
    return rows


def bengals_pants(m):
    name, tw, th, mips = m["names"]["06A0"][2]
    stripes = ([112, 0, 172, 200], [346, 0, 402, 200])
    ops = []
    for box in stripes:
        # every texel of a tiger stripe (black and its grey edge blends: anything that is not the white cloth)
        # takes the Bengals orange
        ops.append({"op": "recolor", "box": box, "from": ["#FFFFFF"], "invert": True, "color": BENGAL_ORANGE,
                    "tolerance": 40})
    # the sock band under the wavy hem line (black on the road kit) is orange, as on the home kit
    ops.append({"op": "recolor", "box": [0, 186, 512, 256], "from": [BLACK], "color": BENGAL_ORANGE,
                "tolerance": 100, "match": "original"})
    for box in ([112, 0, 172, 196], [346, 0, 402, 196]):
        # a black edge about one and a half texels wide around each stripe, laid on the white cloth
        ops.append({"op": "grow", "box": box, "from": [BENGAL_ORANGE], "into": ["#FFFFFF"], "color": BLACK,
                    "radius": 1.5, "tolerance": 30})
    return {"chunk": 2, "kind": "tset", "texture": name, "size": [tw, th, mips], "ops": ops, "reencode": True}


def kits(m):
    rams = {
        "id": "RK1-LAR", "team": "LAR", "code": "23", "style": 13, "label": [2020, 2025],
        "look": "2020-2025 Rams. H: royal home with the 2020 number font in a sol-to-white gradient, sol shoulder "
                "horns, sol pants, royal socks, metallic royal helmet with the sol horn. A (Super Bowl LVI): the white "
                "modern throwback, solid royal 2020-font numerals, royal horns on sol capped sleeves, no sleeve "
                "numbers, sol pants with a royal-white-royal stripe, royal socks, the 2020 helmet with a royal facemask",
        "sides": {
            "H": {"base": "23H0", "art": gradient_digits(m)},
            "A": {"base": "23A2",
                  "chunks": {"4-12": "23A0", "13-22": "23A0", "23-32": "23A0", "33-44": "23A0", "48": "23A0"},
                  "unif": "23A0",
                  "atlas": {"format": "A8R8G8B8", "overlays": [{"donor": "23A0", "boxes": ["sock_low", "sock"]}]},
                  "art": era_colours() + solid_royal_digits(m)}},
        "cards": {"H": "23H0", "A": "23A2", "helm_a": "23A0", "mini_a": "23A0", "logo": "23H0"},
        "moments": [[ROW, "away"]],
        "evidence": ["SportsLogos.net 2022-02-02 'Cincinnati Bengals, Los Angeles Rams unveil uniforms for Super Bowl "
                     "LVI': Rams in 'white modern throwback uniforms'",
                     "Sports Illustrated 2022-02-02: 'white uniforms with gold pants'",
                     "therams.com 2021-07-13: 'white jersey with blue numbers and blue ram horns on the yellow capped "
                     "sleeves'",
                     "SportsLogos.net 2020-05-13: royal home numbers 'transitioning from gold at the top to white at "
                     "the bottom'; bone road 'no gradient effect'",
                     "GUD 2021_LAR_D2.png (Super Bowl LVI), 2021_LAR_M.png (royal home), reference only",
                     "art authored by rk1 (vector ops, tools/b77/rk1_kits_author.py); no reference pixels ship"]}
    bengals = {
        "id": "RK1-CIN", "team": "CIN", "code": "06", "style": 13, "label": [2021, 2025],
        "look": "2021 Bengals as in Super Bowl LVI. H: black home jersey over white pants with orange tiger stripes "
                "outlined in black, orange socks, orange striped helmet. A: the white road kit (06A0)",
        "sides": {
            "H": {"base": "06H0", "chunks": {"2": "06A0", "47": "06A0"},
                  "atlas": {"format": "A8R8G8B8", "overlays": [{"donor": "06A0", "boxes": ["pants"]}]},
                  "art": [bengals_pants(m)]},
            "A": {"base": "06A0"}},
        "cards": {"H": "06H0", "A": "06A0", "logo": "06H0"},
        "moments": [[ROW, "home"]],
        "evidence": ["NFL.com / SportsLogos.net 2022-02-02: black home jerseys, white pants with 'orange tiger "
                     "stripes outlined in black', orange socks",
                     "GUD 2021_CIN_I2.png (Super Bowl LVI), reference only",
                     "art authored by rk1 (vector ops, tools/b77/rk1_kits_author.py); no reference pixels ship"]}
    return [rams, bengals]


def edit(doc, m):
    mine = kits(m)
    rest = [k for k in doc["kits"] if k["id"] not in ("K11", "RK1-LAR", "RK1-CIN")]
    selections = []
    for s in doc["selections"]:
        if s["row"] == ROW:
            continue
        selections.append(s)
    selections += [
        {"row": ROW, "side": "away", "file": RAMS_FILE, "before": 2, "style": 13, "kit": "RK1-LAR"},
        {"row": ROW, "side": "home", "file": BENGALS_FILE, "before": 0, "style": 13, "kit": "RK1-CIN"}]
    defaults = [c for c in doc["classic_defaults"] if c["file"] not in (RAMS_FILE, BENGALS_FILE)]
    defaults += [
        {"file": RAMS_FILE, "style": 13, "before": 2, "why": "wears style 13 in row(s) 48 away"},
        {"file": BENGALS_FILE, "style": 13, "before": 1, "why": "wears style 13 in row(s) 48 home"}]
    return dict(doc, kits=rest + mine, selections=selections, classic_defaults=defaults)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--donors", required=True, type=Path, help="folder with 23H0/23A0/23A2/06H0/06A0 .IFF packages")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    new = edit(doc, measure(args.donors))
    text = json.dumps(new, indent=1, ensure_ascii=True) + "\n"
    if args.check:
        same = DATA.read_text(encoding="utf-8") == text
        print("rk1 kits reproduce exactly" if same else "rk1 kits differ")
        return 0 if same else 1
    DATA.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({k["id"]: {s: len(v.get("art", [])) for s, v in k["sides"].items()} for k in new["kits"]
                      if k["id"].startswith("RK1-")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
