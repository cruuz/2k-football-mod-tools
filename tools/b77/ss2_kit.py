"""Rebuild the Seamen kit (K14) art rows in data/nfl2k5_classic_teams/kits.json (job b778 ss2).

The 2006 episodes show the kit in the Madden 07 uniform editor and on the field. Sampled and measured there:

  primary colour 009284 (the Information screen swatch), secondary white
  home  : teal jersey and sleeves, white side panels, light (white) numbers without outline, teal pants with one wide
          white stripe, white socks, white helmet with a teal centre stripe and a teal anchor on each side, teal facemask
  away  : white jersey and sleeves, teal side panels, dark teal numbers without outline, white pants with one wide
          teal stripe, white socks, the same helmet

Donors (Dolphins 2026 kits on the SOFTDRINK disc, DOLPHINS 14H0 / 14A0) only supply cloth shading and the helmet shell;
every colour, stripe, panel and the anchor is authored here.

  python3 tools/b77/ss2_kit.py            rewrite the K14 art rows in kits.json
  python3 tools/b77/ss2_kit.py --check    exit 1 if kits.json is not what this tool writes
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss2_art as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KITS = ROOT / "data/nfl2k5_classic_teams/kits.json"

TEAL = "#009284"
TEAL_DARK = "#005A52"
WHITE = "#FFFFFF"
SHELL = "#F3F4F7"                      # the donor helmet's own white
ANCHOR_FILL = "#02A081"
ANCHOR_INK = "#04201C"

AQUA = ["#00929B", "#008E97", "#008687", "#006869", "#006768"]
ORANGE = ["#F4581F", "#FB4C00", "#FC4E00", "#E74900", "#E45426"]
NAVY = ["#002E69", "#00456B"]


def pmap(aqua, orange, navy=None, tolerance=20, kind="txtr", chunk=0):
    rows = [{"from": c, "to": aqua} for c in AQUA] + [{"from": c, "to": orange} for c in ORANGE]
    if navy:
        rows += [{"from": c, "to": navy} for c in NAVY]
    return {"chunk": chunk, "kind": "palette_map", "texture_kind": kind, "map": rows, "tolerance": tolerance}


def poly(color, points, **extra):
    return dict({"op": "poly", "color": color, "points": [list(p) for p in points]}, **extra)


def rect(color, x0, y0, x1, y1, **extra):
    return poly(color, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **extra)


def stripe(color, cx, top, bottom, w_top, w_bottom, bow=0.0):
    """A tapering pants stripe: ``w_top`` wide at ``top``, ``w_bottom`` at ``bottom``, bowed by ``bow`` texels."""
    left, right = [], []
    steps = 8
    for i in range(steps + 1):
        t = i / steps
        y = top + (bottom - top) * t
        half = (w_top + (w_bottom - w_top) * t) / 2
        shift = bow * 4 * t * (1 - t)
        left.append((cx - half + shift, y))
        right.append((cx + half + shift, y))
    return poly(color, left + right[::-1])


def wedge(color, cx, y0, y1, hw_top, hw_bottom, width=512, bow=0.0, **extra):
    """A side panel: a wedge ``hw_top`` half wide at ``y0`` narrowing to ``hw_bottom`` at ``y1``, repeated across the
    texture seam when it crosses x = 0 / ``width``."""
    steps = 8
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        y = y0 + (y1 - y0) * t
        half = hw_top + (hw_bottom - hw_top) * t
        shift = bow * 4 * t * (1 - t)
        left.append((cx - half + shift, y))
        right.append((cx + half + shift, y))
    ring = left + right[::-1]
    out = [poly(color, ring, **extra)]
    xs = [p[0] for p in ring]
    if min(xs) < 0:
        out.append(poly(color, [(x + width, y) for x, y in ring], **extra))
    if max(xs) > width:
        out.append(poly(color, [(x - width, y) for x, y in ring], **extra))
    return out


def anchor_ops(cx, cy, height, rot180=False, alpha=None, ink=ANCHOR_INK, fill=ANCHOR_FILL):
    polys = A.anchor_polys(cx, cy, height, rot180=rot180)
    ops = []
    for key, colour in (("ink", ink), ("fill", fill), ("islands", ink)):
        if not polys[key]:
            continue
        op = {"op": "multipoly", "color": colour,
              "polys": [[[round(x, 2), round(y, 2)] for x, y in poly_] for poly_ in polys[key]]}
        if alpha is not None:
            op["alpha"] = alpha
        ops.append(op)
    return ops


def mesh(color, boxes, dx=4, dy=3):
    """The jersey's airy mesh: a staggered lattice of one-texel dots inside each box (texel list op)."""
    pts = []
    for x0, y0, x1, y1 in boxes:
        for row, y in enumerate(range(y0, y1, dy)):
            for x in range(x0 + (dx // 2 if row % 2 else 0), x1, dx):
                pts.append([x, y])
    return {"op": "texels", "color": color, "points": pts, "note": "mesh"}


def tex(chunk, kind, name, size, ops):
    return {"chunk": chunk, "kind": kind, "texture": name, "size": list(size), "reencode": True, "ops": ops}


def helmet_ops(chunk):
    ops = [rect(SHELL, 30, 42, 120, 104, note="donor dolphin, upper island"),
           rect(SHELL, 30, 152, 120, 214, note="donor dolphin, lower island")]
    if chunk == 12:
        ops.append(rect("#EEF0F4", 190, 60, 254, 102, note="donor Dolphins / MIAMI wordmarks"))
    else:
        ops.append(rect("#EEF0F4", 190, 60, 254, 98, note="donor Dolphins script and Riddell"))
    ops.append(rect(SHELL, 146, 20, 181, 227, note="donor stripe"))
    ops.append(rect(SHELL, 146, 227, 181, 232, note="donor stripe end"))
    ops.append(rect(TEAL, 157, 22, 169, 229, note="centre stripe"))
    ops += anchor_ops(72, 72, 33, rot180=True)       # the upper island is the player's right side, drawn upside down
    ops += anchor_ops(72, 182, 33)
    return ops


def side(letter):
    home = letter == "H"
    cloth = TEAL if home else WHITE
    panel = WHITE if home else TEAL
    number = WHITE if home else TEAL_DARK
    art = []
    # near-player texture colours
    art += [pmap(TEAL, TEAL, TEAL, kind="tset", chunk=1), pmap(TEAL, TEAL, TEAL, kind="tset", chunk=2),
            pmap(TEAL, TEAL, TEAL, kind="tset", chunk=3), pmap(WHITE, WHITE, WHITE, kind="tset", chunk=4)]
    digits = pmap(TEAL_DARK, TEAL_DARK) if not home else pmap(TEAL, WHITE)
    for base in (13, 33):
        for i in range(10):
            row = json.loads(json.dumps(digits))
            row["chunk"] = base + i
            art.append(row)
    for chunk in (11, 12):
        art.append(pmap(TEAL, TEAL, chunk=chunk))
    art.append(pmap(TEAL, TEAL, chunk=50))
    # painted textures
    dot = "#00786C" if home else "#B4BCC2"
    jersey = [rect(cloth, 78, 32, 242, 182, note="chest marks"), rect(cloth, 315, 18, 438, 165, note="back marks"),
              mesh(dot, [(92, 44, 228, 196), (322, 30, 452, 190)]),
              ] + wedge(panel, 268.5, 90, 238, 37, 23, note="side panel") + wedge(panel, 527, 90, 238, 74, 46)
    art.append(tex(1, "tset", "jersey00", (512, 256, 6), jersey))
    art.append(tex(3, "tset", "sleeve00", (128, 128, 5), [rect(cloth, 0, 0, 128, 128, note="plain sleeve")]))
    pants_cloth = cloth
    legs = []
    for cx in (142, 369):
        legs.append(stripe(panel, cx, 14, 214, 42, 8, bow=3))
    pants = [rect(pants_cloth, 0, 0, 512, 22, note="waistband marks"),
             rect(pants_cloth, 80, 22, 104, 40, note="swoosh"), rect(pants_cloth, 404, 22, 424, 42, note="shield")]
    pants = [rect(pants_cloth, 120, 0, 164, 256), rect(pants_cloth, 347, 0, 391, 256)] + pants + legs
    if not home:
        pants.insert(0, rect(WHITE, 0, 200, 512, 256, note="donor teal hem"))
    art.append(tex(2, "tset", "pants00", (512, 256, 6), pants))
    for chunk, name in ((11, "helmet00"), (12, "helmet02")):
        art.append(tex(chunk, "txtr", name, (256, 256, 6), helmet_ops(chunk)))
    art.append(tex(49, "txtr", "logo", (128, 128, 1),
                   [rect("#FFFFFF", 1, 0, 128, 128, alpha=0)] + anchor_ops(64, 64, 118, alpha=255)))
    art.append(tex(52, "txtr", "flipchip", (64, 64, 1),
                   [rect("#FFFFFF", 1, 0, 64, 64, alpha=0)] + anchor_ops(32, 32, 60, alpha=255)))
    return art


def atlas_ops(letter):
    """The far-player atlas (256x128): the donor colours move to the teal, the donor dolphin and wordmarks go, the
    anchor and the stripe come in, the lower legs turn white like the near socks."""
    home = letter == "H"
    panel = WHITE if home else TEAL
    black, white = "#000000", "#FFFFFF"
    ops = [{"op": "remap", "tolerance": 40,
            "pairs": [[black, black], [white, white], ["#00929B", TEAL], ["#F4581F", TEAL]]},
           {"op": "remap", "box": [127, 96, 190, 128], "tolerance": 40,
            "pairs": [[black, black], [white, white], [TEAL, white]]}]
    if home:
        ops.append({"op": "recolor", "box": [0, 0, 130, 82], "from": ["#00C4D0", "#04B8C3", "#00B8C4"],
                    "color": "#00988A", "tolerance": 30, "note": "bright aqua highlight of the donor pants"})
    else:
        ops.append(rect(WHITE, 0, 81, 128, 91, note="donor teal hem"))
    ops.append(rect(panel, 51, 0, 61, 82, note="pants stripe"))
    # donor wordmarks: the chest script and the sleeve dolphin
    ops.append({"op": "copy", "src": [196, 52, 208, 62], "dst": [176, 28], "note": "chest script"})
    ops.append(rect(TEAL if home else "#DDDDDD", 214, 103, 240, 121, note="sleeve dolphin"))
    # helmet: the donor dolphin goes, the anchor takes its place
    ops.append(rect("#E8E8E8" if home else "#EBEBEB", 100, 103, 121, 123, note="helmet dolphin"))
    ops += anchor_ops(110.5, 112.5, 15)
    return ops


def chunks_for(letter):
    # pants (2) and their bump map (47) come from the other side's donor for the home teal pants; the helmets are the
    # donor's own white shells (the ss1 Browns shell recolour left stray arcs)
    other = "14A0" if letter == "H" else "14H0"
    return {"2": other, "47": other}


def build(doc):
    kit = next(k for k in doc["kits"] if k["id"] == "K14")
    for letter in "HA":
        sd = kit["sides"][letter]
        sd["chunks"] = chunks_for(letter)
        sd["art"] = side(letter)
        sd["atlas"] = {"format": "A8R8G8B8", "overlays": sd["atlas"]["overlays"], "ops": atlas_ops(letter)}
        sd["unif_colours"] = [TEAL, TEAL if letter == "H" else WHITE]
    kit["look"] = ("2006 Sarasota Seamen from the SOFTDRINKTV Madden 07 episodes: teal jersey, sleeves and pants at home "
                   "(white side panels, white pants stripe, light numbers), white jersey and pants on the road (teal side "
                   "panels, teal pants stripe, dark teal numbers), white socks, white helmet with a teal centre stripe and "
                   "a teal anchor on each side, teal facemask. Primary colour 009284 sampled from the Information screen.")
    return doc


def _flat(value):
    return isinstance(value, (int, float)) or (isinstance(value, list) and all(_flat(v) for v in value))


def _dump(value, level=0):
    """indent=1 JSON, except that a list holding only numbers or lists of numbers (a polygon, a texel list) is one line."""
    pad = " " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        rows = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {_dump(v, level + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(rows) + "\n" + " " * level + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if _flat(value):
            return json.dumps(value, separators=(", ", ": "))
        rows = [f"{pad}{_dump(v, level + 1)}" for v in value]
        return "[\n" + ",\n".join(rows) + "\n" + " " * level + "]"
    return json.dumps(value, ensure_ascii=False)


def dumps(doc):
    return _dump(doc) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    doc = build(json.loads(KITS.read_text(encoding="utf-8")))
    text = dumps(doc)
    if args.check:
        return 0 if KITS.read_text(encoding="utf-8") == text else 1
    KITS.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", KITS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
