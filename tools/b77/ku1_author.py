#!/usr/bin/env python3
"""ku1 (b776): the 2026 Kansas City Chiefs home (13H0) and road (13A0) kits redone to the current look.

Noah (10/18): the Chiefs read a pinkish red in game, and their numbers and sleeve stripes look like the old uniforms.
Measured causes and the recipe (references: chiefs.com 2026 week 1 DEN, week 2 IND, week 4 LV galleries and the 2025
week 8 WSH Wikimedia photo; reference only, nothing of them ships):

* Colour. The kits were flat #E31837 (227, 24, 55). In game the drawn colour is about 1.02 x texture - 19 per channel
  (xemu captures of these kits; the same fit holds on the Bears navy), so green drops to about 5 while blue keeps
  about 39: a raspberry red, hue 349. The club photos read (202, 27, 32), green and blue equal, hue 358. The new
  albedo is chosen so the drawn colour lands there: red #E4282E, helmet #CC242A, gold #F7C542 (the old #FFB612 drew
  orange). Every Chiefs texture moves through a palette remap that keeps each shade and blend.
* Numbers (v3, Noah 10/18: "use the OLD number font from 2K5, because that's still the same font"): the retail 2K5
  Chiefs jersey and shoulder digits, read from the user's disc at build time and re-tinted to the 2026 colours with
  their retail gold edge (glyph pass, ``digit_retint``). The two hand-drawn ku1 sets are dropped. The retail glyphs
  already fill the 64-texel digit texture top to bottom (rows 1-62), so the texture cannot carry a taller number:
  the number cell's size is set by the shared body mesh and the executable's number binder (U 4.0, V 2.0).
* Arm numbers move from the sleeves (Unif number route 4, the 2004 placement) to the shoulder tops (route 1), and are
  stored at 0.7 of the jersey colour, because the game lights the shoulder tops 1.4 to 2 times brighter (job sea1).
* Sleeves: the Nike band (white-gold-white at home, red-gold-red on the road) sits above a cloth hem, not at the hem.
* Socks: home red with a white-gold-white band and a red band over the white foot; road white with a red-gold-red band.
* Pants stripes re-proportioned (home red 6 / gold 9 / red 6; road white 6 / red 3 / gold 5 / red 3 / white 6).
* The AFL (Lamar Hunt) chest roundel at its real size and place, drawn as our own simple vector roundel.
* Nameplates (fn2's retail-structure retint) take the new colours.

  ku1_author.py spec                               colours, number shapes and notes into data/nfl2k5_teams_2026/KC.json
  ku1_author.py data --input DISC.iso --retail RETAIL.iso
                                                   compile and pin data/nfl2k5_kit_fixes_2026_ku1.json and the Chiefs
                                                   rows of data/nfl2k5_glyph_fixes_2026.json against the input disc

``DISC`` is the disc whose Chiefs kits are the pinned input (b775: every earlier uniform writer applied). Game-derived
files stay outside the repository; only vector art and hashes go into the data files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]

SPEC = ROOT / "data/nfl2k5_teams_2026/KC.json"
DATA = ROOT / "data/nfl2k5_kit_fixes_2026_ku1.json"
GLYPHS = ROOT / "data/nfl2k5_glyph_fixes_2026.json"
GLYPH_ART = ROOT / "data/nfl2k5_glyph_fixes_2026"
MENU = ROOT / "data/nfl2k5_menu_chiefs_2026.json"
MENU_SLOTS = (("logos", "unif_h13_0"), ("logos", "unif_a13_0"), ("logos", "helm_h13_0"), ("logos", "helm_a13_0"),
              ("logos128", "helm_h13_0"), ("logos128", "helm_a13_0"), ("mini", "mini_h13_0"), ("mini", "mini_a13_0"))
MENU_RULE = {"red_over_green": 40, "red_over_blue": 20, "pull": [2, 5]}

OLD_RED, RED = "#E31837", "#E4282E"
OLD_HELMET, HELMET = "#C0142F", "#CC242A"
OLD_GOLD, GOLD = "#FFB612", "#F7C542"
WHITE, BLACK = "#FFFFFF", "#000000"
ARM_GAIN = (7, 10)              # shoulder (TV) numbers are lit brighter than the jersey: stored at 0.7


def hexs(rgb):
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def rgb(text):
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def scaled(text, num, den):
    return hexs(min(255, (c * num + den // 2) // den) for c in rgb(text))


ARM_RED, ARM_GOLD = scaled(RED, *ARM_GAIN), scaled(GOLD, *ARM_GAIN)
# the retail 2K5 Chiefs digit colours (the line every retail digit palette entry is projected on)
RETAIL_FILL = {"13H0": "#FFFFFF", "13A0": "#BC001C"}
RETAIL_OUTLINE = "#FEAF16"
# Remap pairs. The old red comes first so a pure old red takes exactly the new red (ties go to the first pair). The
# "bright" points (1.12 x) carry the lit highlights of the shaded helmet and sideline-player textures.
CLOTH_PAIRS = [[OLD_RED, RED], [OLD_GOLD, GOLD], [WHITE, WHITE], [BLACK, BLACK],
               [scaled(OLD_RED, 112, 100), scaled(RED, 112, 100)]]
SHADED_PAIRS = [[OLD_RED, RED], [OLD_HELMET, HELMET], [OLD_GOLD, GOLD], [WHITE, WHITE], [BLACK, BLACK],
                [scaled(OLD_RED, 112, 100), scaled(RED, 112, 100)],
                [scaled(OLD_HELMET, 112, 100), scaled(HELMET, 112, 100)]]
REMAP_TOLERANCE = 8

# -- shapes (native texel coordinates) ----------------------------------------------------------------------------


def rect(x0, y0, x1, y1, color):
    return {"op": "poly", "color": color, "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def poly(points, color):
    return {"op": "poly", "color": color, "points": [[round(x, 3), round(y, 3)] for x, y in points]}


def disc(cx, cy, r, color, n=40):
    return poly([(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)],
                color)


def ellipse(cx, cy, rx, ry, color, n=28):
    return poly([(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)],
                color)


# The old b775 roundel (job u1) and the new one. Torso texture right of the collar V is the player's left chest.
OLD_PATCH = (211.0, 74.0, 5.6)
PATCH = (200.0, 89.0, 9.3)      # centre x, y and radius, measured against the NFL shield in the club photos
PATCH_RIM, PATCH_FIELD, PATCH_NAVY = "#D8B26A", "#FFF3D6", "#22307E"


def afl_patch(cloth):
    cx, cy, r = PATCH
    ox, oy, orr = OLD_PATCH
    a = r / 8.4
    ops = [disc(ox, oy, orr, cloth), disc(cx, cy, r, PATCH_RIM), disc(cx, cy, r - 1.0 * a, PATCH_FIELD)]
    # the A: two legs and a bar in navy over a white letter, on the cream field; the red football under it
    top, foot, half, leg = cy - 5.6 * a, cy + 2.6 * a, 4.9 * a, 2.3 * a
    ops.append(poly([(cx, top - 0.6 * a), (cx + half + 0.7 * a, foot + 0.5 * a), (cx + half - leg - 0.5 * a, foot + 0.5 * a),
                     (cx, top + 3.2 * a), (cx - half + leg + 0.5 * a, foot + 0.5 * a),
                     (cx - half - 0.7 * a, foot + 0.5 * a)], PATCH_NAVY))
    ops.append(poly([(cx, top + 0.6 * a), (cx + half - 0.3 * a, foot), (cx + half - leg + 0.3 * a, foot),
                     (cx, top + 4.4 * a), (cx - half + leg - 0.3 * a, foot), (cx - half + 0.3 * a, foot)], WHITE))
    ops.append(rect(cx - 2.6 * a, cy - 0.2 * a, cx + 2.6 * a, cy + 1.0 * a, PATCH_NAVY))
    ops.append(ellipse(cx, cy + 4.9 * a, 3.6 * a, 1.6 * a, RED))
    return ops


def sleeve(band, hem):
    """The Nike band on both arm islands (rows 0-63 and 64-127; row 0 meets the jersey, row 63 is the hem): cloth to
    row 26, band 26-37, gold 37-44, band 44-55, then the hem in the cloth colour of the other side."""
    ops = []
    for top in (0, 64):
        ops += [rect(0, top + 26, 128, top + 37, band), rect(0, top + 37, 128, top + 44, GOLD),
                rect(0, top + 44, 128, top + 55, band), rect(0, top + 55, 128, top + 64, hem)]
    return ops


def socks(layers):
    ops, y = [], 0.0
    for height, colour in layers:
        ops.append(rect(0, y, 64, y + height, colour))
        y += height
    return ops


# The pants stripe bands (measured on the b775 pants: the band edges and the hem seam line under each stripe).
PANTS_LEGS = (dict(x0=131.5, hem=((128.0, 209.0), (154.0, 212.5))),
              dict(x0=358.5, hem=((356.0, 212.5), (382.0, 209.0))))
PANTS_AWAY_LEGS = (dict(x0=130.5, hem=((128.0, 209.0), (154.0, 212.5))),
                   dict(x0=357.5, hem=((356.0, 212.5), (382.0, 209.0))))


def pants(legs, layers):
    ops = []
    for leg in legs:
        (ax, ay), (bx, by) = leg["hem"]
        hem = lambda x: ay + (by - ay) * (x - ax) / (bx - ax)
        x = leg["x0"]
        for width, colour in layers:
            ops.append(poly([(x, 0), (x + width, 0), (x + width, hem(x + width)), (x, hem(x))], colour))
            x += width
    return ops


def entries():
    rows = []

    def add(selector, chunk, texture, kind, size, note, **extra):
        rows.append(dict(selector=selector, chunk=chunk, texture=texture, kind=kind, size=size,
                         defects=["ku1-KC-2026-look"], note=note, **extra))

    remap = {"pairs": CLOTH_PAIRS, "tolerance": REMAP_TOLERANCE}
    shaded = {"pairs": SHADED_PAIRS, "tolerance": REMAP_TOLERANCE}
    for sel, cloth, other in (("13H0", RED, WHITE), ("13A0", WHITE, RED)):
        home = sel == "13H0"
        add(sel, 0, "Unif", "unif", None, "arm numbers on the shoulder tops (route 1, the Nike placement), "
            "not on the sleeves (route 4, the 2004 placement)", ints={"number_route": 1})
        add(sel, 1, "jersey00", "tset", [512, 256, 6], "2026 red; the AFL (Lamar Hunt) roundel at its real size and "
            "place on the player's left chest", palette_remap=remap, ops=afl_patch(cloth))
        add(sel, 2, "pants00", "tset", [512, 256, 6],
            "2026 red; home stripe red 6 / gold 9 / red 6" if home else
            "2026 red; road stripe white 6 / red 3 / gold 5 / red 3 / white 6", palette_remap=remap,
            ops=pants(PANTS_LEGS, [(6, RED), (9, GOLD), (6, RED)]) if home else
            pants(PANTS_AWAY_LEGS, [(6, WHITE), (3, RED), (5, GOLD), (3, RED), (6, WHITE)]))
        add(sel, 3, "sleeve00", "tset", [128, 128, 5],
            "Nike band above a red hem: white / gold / white" if home else
            "Nike band above a white hem: red / gold / red", palette_remap=remap,
            ops=sleeve(WHITE, RED) if home else sleeve(RED, WHITE))
        add(sel, 4, "socks00", "tset", [64, 64, 4],
            "red sock, white / gold / white band, red band, white foot" if home else
            "white sock with a red / gold / red band", palette_remap=remap,
            ops=socks([(40, RED), (2.5, WHITE), (4, GOLD), (2.5, WHITE), (5, RED), (10, WHITE)]) if home else
            socks([(41, WHITE), (3.5, RED), (3.5, GOLD), (3.5, RED), (12.5, WHITE)]))
        for chunk, name in ((11, "helmet00"), (12, "helmet02")):
            add(sel, chunk, name, "txtr", [256, 256, 6], "2026 helmet red and arrowhead red (shading kept)",
                palette_remap=shaded)
        add(sel, 51, "splayer", "txtr", [256, 128, 5], "sideline / far player atlas in the 2026 colours",
            palette_remap=shaded)
    return rows


# -- KC.json ----------------------------------------------------------------------------------------------------------

def digit_block(donor, fill, outline):
    """The retail 2K5 Chiefs digits (the club's font), re-tinted at build time by the glyph pass (digit_retint)."""
    return {"glyph_donor": donor, "fill": fill, "outline": outline, "structure": "retail",
            "note": "ku1 v3 (Noah 10/18): the retail 2K5 Chiefs digit shapes and edge, in the 2026 colours"}


def cmd_spec(_args):
    doc = json.loads(SPEC.read_text(encoding="utf-8"))
    doc["palette"].update(red=RED, gold=GOLD)
    doc["albedo"].update(red=RED, helmet_red=HELMET, gold=GOLD, arm_red=ARM_RED, arm_gold=ARM_GOLD,
                         ku1_retired_red=OLD_RED, ku1_retired_gold=OLD_GOLD, ku1_retired_helmet_red=OLD_HELMET)
    doc["status_ku1"] = (
        "b776 ku1 (2026-10-18, Noah: pinkish red, old numbers and sleeve stripes): the 2026 look. Albedo red #E4282E, "
        "helmet #CC242A, gold #F7C542 chosen through the measured in-game response (drawn ~ 1.02 x texture - 19 per "
        "channel) to land on the club photos' red (202, 27, 32) and gold (233, 182, 48); Nike block numbers "
        "(v3: the retail 2K5 digit shapes re-tinted, Noah 10/18); arm numbers on the shoulder tops (route 1); Nike sleeve band above the hem; 2026 "
        "socks and pants stripes; AFL roundel. Applied by the Studio pass data/nfl2k5_kit_fixes_2026_ku1.json and the "
        "Chiefs rows of data/nfl2k5_glyph_fixes_2026.json.")
    doc["sources_ku1"] = [
        "https://www.chiefs.com/photos/photos-game-action-from-regular-season-week-1-broncos-vs-chiefs (home: red, white numbers with a gold edge, white/gold/white sleeve band, white pants with red/gold/red stripe, red socks with white/gold/white band)",
        "https://www.chiefs.com/photos (2026 week 2 vs IND gallery: home #9, #4, #15 front close-ups, AFL roundel)",
        "https://www.chiefs.com/photos (2026 week 4 at LV gallery: road white, red numbers with a gold edge, red/gold/red sleeve band, red pants with white/red/gold/red/white stripe, white socks with a red/gold/red band)",
        "https://commons.wikimedia.org/wiki/File:Washington_Commanders_at_Kansas_City_Chiefs_(55091352530).jpg (2025 week 8 home, #77 back)",
    ]
    for side, (fill, arm_fill) in (("home", ("white", "white")), ("away", ("red", "arm_red"))):
        kit = doc["kits"][side]
        kit["digits"] = digit_block(kit["selector"], fill, "gold")
        kit["arm_digits"] = digit_block(kit["selector"], arm_fill, "arm_gold")
        kit["nameplate"].update(fill=fill, outline="gold")
    doc["part_intents"]["home"].update(
        digit_jersey="white retail 2K5 Chiefs numbers with their gold edge",
        digit_arm="white shoulder-top numbers with a gold edge (stored at 0.7: the shoulder tops are lit brighter)",
        sleeve="red sleeve, white / gold / white band above a red hem",
        socks00="red sock, white / gold / white band, red band, white foot")
    doc["part_intents"]["away"].update(
        digit_jersey="red retail 2K5 Chiefs numbers with their gold edge",
        digit_arm="red shoulder-top numbers with a gold edge (stored at 0.7)",
        sleeve="white sleeve, red / gold / red band above a white hem",
        socks00="white sock with a red / gold / red band")
    with SPEC.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, indent=1, ensure_ascii=False)
        stream.write("\n")
    print("spec:", SPEC)


# -- compile and pin --------------------------------------------------------------------------------------------------

def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_kits(disc, selectors):
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    with bump._Image.open(Path(disc), writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        return {s: image.read_segments(index.sub_extents(by_name[s + ".IFF"], 0, by_name[s + ".IFF"].size))
                for s in selectors}


def compile_rows(raws):
    from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
    rows = entries()
    for row in rows:
        raw = raws[row["selector"]]
        chunk = fixes._chunk_for(raw, row["chunk"])
        span = raw[chunk.offset:chunk.end_offset]
        if row["kind"] == "unif":
            new, detail = fixes.compile_unif(span, row)
        else:
            new, detail = fixes.compile_texture(span, row)
        row.update(resource_size=len(raw), offset=chunk.offset, length=len(span), before_sha256=sha(span),
                   after_sha256=sha(new))
        print(row["selector"], row["chunk"], row["texture"], "remapped", detail.get("palette_remapped"),
              "added", len(detail.get("palette_slots_added", [])), flush=True)
    return rows


def glyph_rows(raws, retail_raws):
    from mod_editor.core import nfl2k5_glyph_fixes_2026 as glyphs
    doc = json.loads(GLYPHS.read_text(encoding="utf-8"))
    keep = [r for r in doc["textures"] if not (r["selector"] in ("13H0", "13A0") and r["kind"] in ("digit_png", "digit_retint"))]
    for row in keep:
        if row["selector"] in ("13H0", "13A0") and row["kind"] == "names_retint":
            raw = raws[row["selector"]]
            span = raw[row["offset"]:row["offset"] + row["length"]]
            require_equal(sha(span), row["before_sha256"], row["selector"] + " nameplate input differs from fn2's pin")
            home = row["selector"] == "13H0"
            row.update(fill=WHITE if home else RED, outline=GOLD)
            rchunk = glyphs._chunk_for(retail_raws[row["retail_selector"]], 43)
            rspan = retail_raws[row["retail_selector"]][rchunk.offset:rchunk.end_offset]
            new, _ = glyphs.compile_names(span, rspan, row)
            row["after_sha256"] = sha(new)
            row.setdefault("defects", [])
            if "ku1-KC-2026-colours" not in row["defects"]:
                row["defects"].append("ku1-KC-2026-colours")
    added = []
    for sel in ("13H0", "13A0"):
        raw, retail = raws[sel], retail_raws[sel]
        home = sel == "13H0"
        for family, base, prefix in (("jersey", 13, ""), ("arm", 33, "an")):
            fill = (WHITE if home else RED) if family == "jersey" else (WHITE if home else ARM_RED)
            outline = GOLD if family == "jersey" else ARM_GOLD
            for d in range(10):
                chunk = glyphs._chunk_for(raw, base + d)
                span = raw[chunk.offset:chunk.end_offset]
                rchunk = glyphs._chunk_for(retail, base + d)
                rspan = retail[rchunk.offset:rchunk.end_offset]
                row = dict(selector=sel, chunk=base + d, kind="digit_retint", texture=prefix + str(48 + d),
                           resource_size=len(raw), offset=chunk.offset, length=len(span), retail_selector=sel,
                           retail_sha256=sha(rspan), retail_fill=RETAIL_FILL[sel], retail_outline=RETAIL_OUTLINE,
                           fill=fill, outline=outline)
                new, detail = glyphs.compile_names(span, rspan, row, name=row["texture"], storage="P8")
                row.update(before_sha256=sha(span), after_sha256=sha(new), defects=["ku1-KC-2026-numbers"])
                added.append(row)
    doc["textures"] = keep + added
    doc["references"]["KC"] = [
        "https://www.chiefs.com/photos/photos-game-action-from-regular-season-week-1-broncos-vs-chiefs (home numbers)",
        "https://www.chiefs.com/photos (2026 week 4 at LV: road numbers and nameplates)",
        "https://commons.wikimedia.org/wiki/File:Washington_Commanders_at_Kansas_City_Chiefs_(55091352530).jpg (#77)"]
    with GLYPHS.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, indent=1)
        stream.write("\n")
    print("glyph rows:", len(added), "digits; nameplates recoloured")


def require_equal(a, b, what):
    if a != b:
        raise SystemExit(f"ku1: {what} ({a} != {b})")


def cmd_data(args):
    from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
    raws = read_kits(args.input, ("13H0", "13A0"))
    retail = read_kits(args.retail, ("13H0", "13A0"))
    rows = compile_rows(raws)
    document = {"schema": fixes.SCHEMA,
                "source": "ku1 (b776): Noah's 10/18 note (pinkish red, old numbers and sleeve stripes) checked against "
                          "dated 2025/26 club photos and the measured in-game colour response",
                "method": "Palette remap of the whole scheme (shades and blends kept, indices unchanged), then vector "
                          "art in native texel coordinates drawn at 4x and averaged onto the native pixels; Unif arm "
                          "number route; fixed spans.",
                "textures": [{k: row[k] for k in ("selector", "chunk", "texture", "kind", "size", "resource_size",
                                                  "offset", "length", "before_sha256", "after_sha256", "defects",
                                                  "note", "palette_remap", "ops", "ints") if k in row}
                             for row in rows]}
    for row in document["textures"]:
        if row["kind"] == "unif":
            row.pop("size", None)
    with DATA.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=1)
        stream.write("\n")
    print("kit rows:", len(rows), "->", DATA)
    glyph_rows(raws, retail)
    menu_rows(args.input)


def menu_rows(disc):
    from mod_editor.core import nfl2k5_menu_chiefs_2026 as menu, nfl2k5_menu_helmet_w2026 as hu
    from tools.nfl2k5_playbook_position_recode import OuterImage
    targets = []
    with OuterImage(Path(disc)) as archive:
        for aggregate, member in MENU_SLOTS:
            _, span = hu.locate(archive, aggregate, member)
            after, receipt = menu.paint(span, MENU_RULE)
            targets.append(dict(aggregate=aggregate, member=member, before_sha256=sha(span), after_sha256=sha(after),
                                **receipt))
    doc = {"schema": menu.SCHEMA,
           "source": "ku1 (b776): the Chiefs Team Select cards and schedule miniatures were rendered from the old "
                     "raspberry red #E31837; their red palette entries move toward the 2026 club red",
           "rule": MENU_RULE, "targets": targets}
    with MENU.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, indent=1)
        stream.write("\n")
    print("menu slots:", len(targets))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spec")
    c = sub.add_parser("data")
    c.add_argument("--input", required=True)
    c.add_argument("--retail", required=True)
    args = parser.parse_args(argv)
    {"spec": cmd_spec, "data": cmd_data}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
