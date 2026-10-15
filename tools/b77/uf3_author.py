#!/usr/bin/env python3
"""uf3 (b773): author the third layer of 2026 kit fixes for ``data/nfl2k5_kit_fixes_2026_uf3.json``.

uf3 judged the uniform elements that ur1 (v0.6 against v0.6.1 for all 680 kits), uw2 (in-game captures) and Noah's
10/14 playtest video flagged against the 2026 reference library (official game highlights, weeks 1 to 5). For each
element it kept the current art, went back to the v0.6 art, or drew a fix. This file holds the drawn fixes and the
reversions as the same native-texel vector art the uf1/uf2 passes use (``mod_editor/core/nfl2k5_kit_fixes_2026.py``),
drawn at 4x and averaged onto the native pixels. Every entry is pinned to the kit span the v0.6.1 Studio build
produces, so this layer runs after the alternates pass and leaves user-replaced textures alone.

  uf3_author.py preview --tex DIR --out DIR      paint level 0 onto extracted kit PNGs (``<selector>_c<chunk>.png``)
  uf3_author.py data --input DISC.iso [--out data/nfl2k5_kit_fixes_2026_uf3.json]
                                                 compile against the pinned input disc and record the pins

Game-derived files stay outside the repository; only the vector art and the hashes go into the data file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
import uf1_author as uf1  # noqa: E402

DATA = fixes.DATA_UF3
NAMES = {1: ("jersey00", "tset", [512, 256, 6]), 2: ("pants00", "tset", [512, 256, 6]),
         3: ("sleeve00", "tset", [128, 128, 5]), 4: ("socks00", "tset", [64, 64, 4]),
         11: ("helmet00", "txtr", [256, 256, 6]), 12: ("helmet02", "txtr", [256, 256, 6])}
poly, rect, offset_polygon = uf1.poly, uf1.rect, uf1.offset_polygon


# -- Washington: the 2026 helmet W -----------------------------------------------------------------------------------
# The 2026 helmet decal (official Week 4 and Week 5 highlights, refs/uniforms_2026/WSH) is the Commanders W drawn as
# four solid gold strokes split by thin burgundy lines, with no outline: a "\\" wedge whose top-left corner bends, a
# "/" upstroke whose tip reaches the top, a "\\" wedge and a full "/" upstroke with a small ear at its top-left, each
# later stroke lying over the one before it. v0.6 painted the club's outlined W (gold outline, burgundy body) on the
# helmet and v0.6.1 flood-filled that outline into one gold mass, losing the splits.
#
# W_STROKES are the four stroke bodies of the club W, in units of 1/1884 of the W's width (y down from its top edge;
# measured on the club W master the v0.6 helmet art was made from). Each body grows W_GROW into the outline band
# between strokes, leaving splits of about 1.3 texels (2.3 % of the width, as worn), and the W is scaled by W_SCALE so
# it keeps the outlined v0.6 W's width, height and centre on the shell (Noah's player: the v0.6 placement was right).
# Across the decal just under its top edge: stroke 1 25 %, first notch with the stroke 2 tip 16 %, stroke 3 22 %,
# second notch 12 %, stroke 4 26 % of the width; the Week 5 close-up (helmet_right_0744, side-on, curved shell)
# reads about 21/18/21/16/24 %.
W_STROKES = [
    [(124, 69), (240, 258), (443, 879), (608, 371), (511, 69)],
    [(761, 126), (489, 960), (821, 960), (927, 636)],
    [(815, 69), (1100, 944), (1266, 434), (1147, 69)],
    [(1789, 69), (1382, 69), (1419, 187), (1168, 960), (1500, 959)],
]
W_OUTER = (1.0, 1.0, 1885.0, 1028.0)     # the outlined W's bounding box, same units
W_GROW = 16.0
W_SCALE = 1.111
W_TEXEL = 0.03222                         # texels per unit, both shells, both sides
W_GOLD, W_SHELL = "#FFB612", "#5B0F12"
# Where the W's top-left corner (unit 0, 0) sits. Side B (lower island, W upright): texture (45 + 4.495, 157 + 5.524).
# Side A (upper island) is the same W turned 180 degrees about the texture point (115 - 4.758, 98 - 5.334).
# Fitted on the v0.6 helmet02 and helmet00 art (both shells agree within 0.006 texel).
W_SIDES = {"B": lambda x, y: (45.0 + 4.495 + W_TEXEL * x, 157.0 + 5.524 + W_TEXEL * y),
           "A": lambda x, y: (115.0 - 4.758 - W_TEXEL * x, 98.0 - 5.334 - W_TEXEL * y)}


def w_pieces(side):
    """The grown, scaled stroke polygons in texture coordinates for one helmet side."""
    grown = [offset_polygon(stroke, W_GROW) for stroke in W_STROKES]
    xs = [x for g in grown for x, _ in g]
    ys = [y for g in grown for _, y in g]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    ox, oy = (W_OUTER[0] + W_OUTER[2]) / 2.0, (W_OUTER[1] + W_OUTER[3]) / 2.0
    place = W_SIDES[side]
    return [[tuple(round(v, 3) for v in place(ox + (x - cx) * W_SCALE, oy + (y - cy) * W_SCALE)) for x, y in g]
            for g in grown]


W_FOOTPRINT = [(1, 1), (178, 288), (418, 1027), (1550, 1027), (1884, 2)]


def w_erase(side):
    """The old W's whole footprint (the outlined v0.6 W's hull, one texel wider), texture coordinates."""
    place = W_SIDES[side]
    hull = offset_polygon(W_FOOTPRINT, 1.0 / W_TEXEL)
    return [tuple(round(v, 3) for v in place(x, y)) for x, y in hull]


# The 2026 art pass erased the retail Indian-head roundel only inside a box, so the tips of its feathers (gold and
# white with a black edge) and a darker inpainted ghost where the feathers hung are still on both shells, beside and
# under the W. The 2026 shell is plain gloss burgundy there; these polygons repaint only those spots (they stop short
# of the flag, the NFL shield, the ear hole ring and the lighter highlight band beside them).
WAS_CLEAN = {
    11: [[(92.6, 32.6), (109.4, 32.6), (109.4, 43.2), (116.3, 43.2), (116.3, 74.5), (92.6, 74.5)],
         [(93.2, 181.6), (116.6, 181.6), (116.6, 223.6), (93.2, 223.6)],
         [(68.0, 102.6), (86.0, 102.6), (86.0, 109.6), (68.0, 109.6)]],
    12: [[(93.0, 32.6), (104.0, 32.6), (104.0, 38.6), (100.4, 41.6), (100.4, 48.6), (93.0, 48.6)],
         [(112.5, 44.6), (115.8, 44.6), (115.8, 73.0), (110.6, 73.0), (110.6, 53.6), (112.5, 53.6)],
         [(105.0, 175.0), (115.8, 175.0), (115.8, 217.0), (113.0, 219.6), (105.0, 219.6)],
         [(93.5, 218.0), (102.5, 218.0), (102.5, 223.0), (93.5, 223.0)],
         [(68.0, 107.0), (85.0, 107.0), (85.0, 109.0), (68.0, 109.0)]],
}


def opaque(op):
    """The shell's reflection alpha is 252..255 in places; a repainted texel takes 255 so it quantises to the exact
    shell and gold entries rather than the darker colours the palette keeps at 252."""
    return dict(op, alpha=255)


def was_clean_ops(chunk):
    return [opaque(poly(points, W_SHELL)) for points in WAS_CLEAN[chunk]]


def was_w_ops():
    ops = []
    for side in ("A", "B"):
        ops.append(opaque(poly(w_erase(side), W_SHELL)))
        ops.append(opaque({"op": "multipoly", "color": W_GOLD,
                           "polys": [[list(p) for p in piece] for piece in w_pieces(side)]}))
    return ops


# -- Baltimore: the old Ravens logo left around the new one (N03) -----------------------------------------------------
# The 2026 art pass erased the retail Ravens decal only where its main piece was, then drew the club mark smaller, so
# the retail logo's gold rear spike, beak tip and its gold outline arcs above and below are still on the black shell
# beside the new bird (Noah, 09:04: "the Ravens logo plastered over the old logo"), on both shells and both sides,
# plus a dotted ghost of a moved flag on helmet02. The 2026 primary helmet carries the one gold-edged bird on plain
# black. The texels below are those left-overs, measured on the v0.6.1 art: every coloured texel in the two decal
# areas outside the new bird (the bird is the region its white border closes, grown by one texel) and outside the US
# flag on helmet00. Row runs "y:x0-x1,...", end exclusive. They are painted the shell black around them.
BAL_REMNANTS = {
    11: ("80:122-124 81:121-124 82:119-124 83:117-123 84:34-36,115-122 85:33-39,111-112,113-122 "
         "86:33-39,112-121 87:33-37,112-121 88:33-36,112-115,116-120 89:33-36,112-113,115-119 90:34-36,114-119 "
         "91:34-37,111-113,114-118 92:35-38,113-117 93:36-39,112-116 94:37-40,111-115 95:38-40,110-114 "
         "96:109-113 97:108-112 98:107-111 99:105-110 100:104-108 101:102-107 102:100-105 103:98-104 "
         "104:96-102 105:93-100 106:89-98 107:80-95 108:71-92 109:76-87 158:39-40,112-113 159:38-40,112-114 "
         "160:37-40,112-115 161:36-39,112-116 162:35-38,113-117 163:34-37,112-113,114-118 164:34-36,115-119 "
         "165:33-36,112-113,115-119 166:33-36,112-115,116-120 167:33-37,112-121 168:33-40,113-121 "
         "169:34-40,114-122 170:34-35,39-40,116-123 171:118-123 172:120-124 173:121-124 174:123-124"),
    12: ("80:122-124 81:121-124 82:119-124 83:117-123 84:34-36,38-39,115-122 85:33-39,111-112,113-122 "
         "86:33-39,112-121 87:33-37,112-121 88:33-36,112-115,116-120 89:33-36,112-113,115-119 90:34-37,114-119 "
         "91:34-37,111-113,114-118 92:35-38,113-117 93:36-39,112-116 94:37-40,112-115 95:38-40,112-114 "
         "96:112-113 108:71-92 109:75-88 136:129-130 138:106-107,128-129 139:127-128 140:126-127 "
         "141:110-111,125-126 142:111-112,125-126 143:124-125 144:123-124 145:115-116,122-123 "
         "146:73-90,116-117,121-123 147:71-92,121-122 148:119-121 159:39-40,112-113 160:38-40,112-115 "
         "161:36-40,112-115 162:35-39,112-116 163:35-38,111-112,113-117 164:34-37,111-113,114-118 "
         "165:33-36,115-119 166:33-36,112-113,115-120 167:33-37,112-115,116-120 168:33-37,112-121 "
         "169:33-39,112-121 170:33-39,111-112,114-122 171:116-122 172:118-123 173:120-124 174:121-124 "
         "175:123-124"),
}
BAL_SHELL = {11: "#010103", 12: "#010001"}


def runs_to_points(text):
    points = []
    for item in text.split():
        y, spans = item.split(":")
        for span in spans.split(","):
            x0, x1 = span.split("-")
            points.extend([x, int(y)] for x in range(int(x0), int(x1)))
    return points


def bal_ops(chunk):
    return [{"op": "texels", "color": BAL_SHELL[chunk], "alpha": 255, "points": runs_to_points(BAL_REMNANTS[chunk])}]


# -- Indianapolis: the shoulder stripes and the sleeve swoosh (N21, N24) ---------------------------------------------
# N21: the two shoulder stripes of both primary jerseys run from the collar down the front of the chest to the armpit
# (torso rows 0-112 at the front, 10-136 at the back, plus a piece under the arm). The 2026 jerseys (Week 1 home,
# Week 5 away) carry them over the top of the shoulder only: from the collar to the shoulder's edge and down the back
# to the shoulder blade. Cut them at torso row 70 (front) and 85 (back), where the shoulder cap ends in the model, and
# drop the under-arm piece.
IND_STRIPE_TAILS = [(75, 70, 105, 116), (219, 70, 249, 116), (298, 85, 321, 141), (458, 85, 481, 141),
                    (0, 84, 25, 143)]


def ind_torso_ops(cloth):
    return [rect(x0, y0, x1, y1, cloth) for x0, y0, x1, y1 in IND_STRIPE_TAILS]


# -- the sleeve swoosh on kits with sleeve (route 3/4) arm numbers (N24, N30) ------------------------------------------
# Every SOFTDRINK sleeve carries the swoosh at the same spot (sleeve island rows 2-15, x 60-81; island 1 mirrored).
# Kits whose Unif route puts the arm number on the sleeve (3: sleeve_B, 4: sleeve_A) draw that number over it: the
# swoosh peeks out under the top-left of the number on all fourteen of them (renders at the native route; Noah's
# 31:02 Colts frame). On the 2026 jerseys the swoosh sits ahead of the number, toward the collar (Colts Week 5, Bears,
# Chiefs, Raiders frames). Move it 16 texels forward around the arm, clear of the number, on both islands. Left as
# they are: shoulder-number kits (route 1/2, no clash), the Chargers (no arm number) and the Texans (Noah: their
# swoosh is right; their sleeve logo sits under the swoosh).
SWOOSH_BOXES = [((58, 1, 84, 16), 16), ((43, 64, 69, 79), -16)]   # (box on the island, move along x)
SWOOSH_FORWARD = {"00H0": "#A0233F", "03H0": "#0B3A9E", "03A0": "#FFFFFF", "05H0": "#0D1A32", "05A0": "#FFFFFF",
                  "11H0": "#0C3A9C", "11A0": "#FFFFFF", "13H0": "#E31837", "13A0": "#FFFFFF", "19H0": "#145F47",
                  "19A0": "#FFFFFF", "20H0": "#121216", "20A0": "#FFFFFF", "29A0": "#FFFFFF"}


def swoosh_ops(cloth):
    ops = [rect(x0, y0, x1, y1, cloth) for (x0, y0, x1, y1), _ in SWOOSH_BOXES]
    ops += [{"op": "copy", "src": [x0, y0, x1, y1], "dst": [x0 + dx, y0], "skip": cloth, "tolerance": 6}
            for (x0, y0, x1, y1), dx in SWOOSH_BOXES]
    return ops


# -- Denver: the sleeve swoosh on the mountain panel (N30, ur1) ------------------------------------------------------
# uf1 moved Denver's sleeve panel up to the shoulder (right, per the 2026 photos) but its band ran through the swoosh:
# the swoosh's hook merged into the navy band on the home kit (navy on white) and was cut by the panel edge on the
# away kit (left white on orange). The 2026 jerseys (Week 2 home, Week 5 away) show a whole navy swoosh on the panel
# with the band below it. Keep uf1's panel and band but set the band's front end 4 rows lower (its back end stays),
# repaint the panel over the old mark, and place a clean swoosh two rows higher on the panel, taken at build time
# from another SOFTDRINK sleeve (16A0: navy on white, the same mark at the same spot; the repository never draws
# it) and set to Denver navy on the panel colour.
DEN_NAVY, DEN_SWOOSH_DONOR, DONOR_NAVY = "#0A2343", "16A0:3", "#0A244E"
DEN_BACK, DEN_FRONT, DEN_B0, DEN_B1, DEN_BAND, DEN_DROP = 6.0, 122.0, 24.0, 9.0, 5.5, 4.0
# uf2's stepped "mountain" band top edge on the alternates (08H5, 08H6, 08A5, 08A6), island 0
DEN_STEPS = [(6.0, 24.0), (25.333, 19.3), (44.667, 19.0), (64.0, 14.3), (83.333, 14.0), (102.667, 9.3), (122.0, 9.0)]


def den_ops(panel, band=DEN_NAVY, swoosh=DEN_NAVY, stepped=False):
    """Repaint the sleeve panel and its band with the band's front end DEN_DROP rows lower (the back end stays), then
    place a clean swoosh two rows higher on the panel, in ``swoosh`` colour."""
    ops = []
    drop = lambda x, y: (x, y + DEN_DROP * (x - DEN_BACK) / (DEN_FRONT - DEN_BACK))
    top_edge = DEN_STEPS if stepped else [(DEN_BACK, DEN_B0), (DEN_FRONT, DEN_B1)]
    top_edge = [drop(x, y) for x, y in top_edge]
    bottom = [drop(DEN_FRONT, DEN_B1 + DEN_BAND), drop(DEN_BACK, DEN_B0 + DEN_BAND)]
    for top, mirror, src, dst in ((0, False, [58, 2, 84, 16], [58, 0, 84, 14]),
                                  (64, True, [43, 66, 69, 80], [43, 64, 69, 78])):
        col = (lambda c: 127.0 - c) if mirror else (lambda c: c)
        edge = [(col(x), top + y) for x, y in top_edge]
        panel_pts = [(col(DEN_BACK), top), (col(DEN_FRONT), top)] + list(reversed(edge))
        band_pts = edge + [(col(x), top + y) for x, y in bottom]
        ops.append(poly(panel_pts, panel))
        ops.append(poly(band_pts, band))
        ops.append({"op": "stamp", "donor": DEN_SWOOSH_DONOR, "src": src, "dst": dst, "skip": ["#FFFFFF"],
                    "tolerance": 14})
        ops.append({"op": "retint", "box": dst, "base": "#FFFFFF", "source": DONOR_NAVY, "color": swoosh,
                    "field": panel, "tolerance": 30})
    return ops


# -- Houston: the red alternate's sleeve swoosh (ur1) ---------------------------------------------------------------
# uf2's navy horn on the Battle Red alternate is painted over the white swoosh, so only broken white pieces of it show
# along the horn's edge. Lay a whole white swoosh back on top at the same spot, from another SOFTDRINK sleeve at build
# time (16A0, the same mark; its anti-aliasing kept on the mixed red/navy ground).

def maker_on_top(colour):
    return [{"op": "stamp", "donor": DEN_SWOOSH_DONOR, "src": box, "dst": box, "color": colour,
             "alpha_line": {"field": "#FFFFFF", "mark": DONOR_NAVY}} for box in ([58, 1, 84, 16], [43, 65, 69, 80])]


# -- Chicago: the home sleeve's GSH (ur1) ---------------------------------------------------------------------------
# uf1 moved the GSH initials up with the home sleeve bands, copying with a per-row background skip; where a letter
# texel matched its row's stripe colour it was dropped, so the white letters broke into fragments across a navy
# gap and the orange band. The away kit's copy (05A0) survived whole: navy letters on one orange band, as the Week 5
# away frame shows. Take that same strip at build time (05A0, same art, same place), keep its orange band behind the
# letters, and set the letters white for the navy home jersey (the v0.6 home GSH was white on orange).

def chi_gsh_ops():
    box = [55, 87, 86, 100]
    return [{"op": "stamp", "donor": "05A0:3", "src": box, "dst": box},
            {"op": "retint", "box": box, "base": "#C83803", "source": "#0D1A32", "color": "#FFFFFF", "tolerance": 40}]


# -- Pittsburgh: the Unc Bowl (2025) kits -----------------------------------------------------------------------------
# ur1 (N04): the moment-kit builder put the current 22H0 jersey, sleeves, digits and name atlas into the style-4 slots
# 22H4/22A4 but left each slot's retail arm-number route (4: sleeve_A, the digits over the gold sleeve stripes) and, in
# 22A4, the retail NAME glyph widths (G/A/I/N/W 9/9/3/9/11 against the atlas's 16/16/5/15/25), so every nameplate is
# cut (GAINWELL read CAINVELL). 22H0's route (1: shoulder_B, the TV numbers on the shoulder top, as in the dated
# October 16, 2025 game photos) and its NAME metrics go with its art; colours and equipment fields stay.

def pit_rows():
    rows = []
    for sel in ("22A4", "22H4"):
        rows.append((sel, {"chunk": 0, "texture": "Unif", "kind": "unif", "ints": {"number_route": 1}},
                     ["N04", "ur1-22A4-route"], "arm numbers on the shoulder top like the 22H0 jersey they wear "
                                                  "(route 1), not over the sleeve stripes (retail route 4)"))
    rows.append(("22A4", {"chunk": 44, "texture": "NAME", "kind": "name", "donor_selector": "22H0"},
                 ["N04", "ur1-22A4-name"], "the name atlas's own glyph widths (from 22H0, whose atlas it carries), so "
                                           "nameplates are no longer cut"))
    return rows


# -- recipes ---------------------------------------------------------------------------------------------------------

def recipes():
    """Every uf3 entry, keyed by kit selector: (chunk, ops, evidence ids, note)."""
    R = {}
    add = lambda sel, *items: R.setdefault(sel, []).extend(items)
    for sel, cloth in (("11H0", "#0C3A9C"), ("11A0", "#FFFFFF")):
        add(sel, (1, ind_torso_ops(cloth), ["N21", "ur1-11-torso-stripes"],
                  "the shoulder stripes end at the shoulder cap (front row 70, back row 85), not at the armpit"))
    for sel, cloth in sorted(SWOOSH_FORWARD.items()):
        ops, evidence = swoosh_ops(cloth), ["N24" if sel.startswith("11") else "N30", "ur1-maker-route-clearance"]
        note = "the sleeve swoosh moved 16 texels forward, ahead of the sleeve arm number instead of under it"
        if sel == "05H0":
            ops = ops + chi_gsh_ops()
            evidence, note = evidence + ["ur1-05H0-gsh"], note + "; the GSH initials whole again (white on orange)"
        if sel == "13A0":
            # ur1: uf1's clearing rectangles stopped at row 62/126, leaving the old red hem band's last two rows as a
            # thin red line at the hem; the 2026 away sleeve has only the red/gold/red stack (Week 4 at LV)
            ops = [rect(0, 62, 128, 65, cloth), rect(0, 126, 128, 128, cloth)] + ops
            evidence, note = evidence + ["ur1-13A0-hem"], note + "; the old red hem line removed"
        add(sel, (3, ops, evidence, note))
    for sel, panel in (("08H0", "#FFFFFF"), ("08A0", "#FC4C02")):
        add(sel, (3, den_ops(panel), ["N30", "ur1-08-maker"],
                  "a whole navy swoosh high on the mountain panel, clear of the band (it had merged into the band)"))
    # the alternates: orange panel over a stepped band, white swoosh (it ran into the white band)
    for sel, band in (("08H5", "#FFFFFF"), ("08H6", "#FFFFFF"), ("08A6", "#FFFFFF"), ("08A5", DEN_NAVY)):
        add(sel, (3, den_ops("#FC4C02", band=band, swoosh="#FFFFFF", stepped=True), ["N30", "ur1-08-alt-maker"],
                  "a whole white swoosh high on the orange panel, clear of the mountain band (it had run into it)"))
    for sel in ("37H2", "37A2"):
        add(sel, (3, maker_on_top("#FFFFFF"), ["N30", "ur1-37H2-maker"],
                  "a whole white swoosh back on top of the navy horn (the horn had painted over most of it)"))
    for sel in ("02H0", "02A0"):
        for chunk in (11, 12):
            add(sel, (chunk, bal_ops(chunk), ["N03", "ur1-02-helmet-remnants"],
                      "the retail Ravens logo's gold spike, beak tip and outline arcs left beside the new bird painted "
                      "out (shell black)"))
    for sel in ("29H0", "29A0"):
        for chunk in (11, 12):
            add(sel, (chunk, was_clean_ops(chunk) + was_w_ops(), ["N13", "N13b", "ur1-29-c12", "uw2-WAS-helmet-w"],
                      "the 2026 helmet W: four solid gold strokes split by thin burgundy lines, v0.6 size and place; "
                      "the retail feather tips and their dark ghost beside the W painted out"))
    return R


def entries():
    rows = []
    for selector, items in sorted(recipes().items()):
        for chunk, ops, evidence, note in items:
            name, kind, size = NAMES[chunk]
            row = {"selector": selector, "chunk": chunk, "texture": name, "kind": kind, "size": size,
                   "defects": evidence, "note": note, "ops": ops}
            keys = sorted({op["donor"] for op in ops if op["op"] == "stamp" and op.get("donor", "self") != "self"})
            if keys:
                row["donors"] = {k: None for k in keys}          # pinned by ``data``
            rows.append(row)
    for selector, row, evidence, note in pit_rows():
        rows.append(dict({"selector": selector}, **row, defects=evidence, note=note))
    return sorted(rows, key=lambda r: (r["selector"], r["chunk"]))


# -- commands --------------------------------------------------------------------------------------------------------

def preview(tex: Path, out: Path, only: list[str], tag: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for row in entries():
        if (only and row["selector"] not in only) or "ops" not in row:
            continue
        src = tex / f"{row['selector']}_c{row['chunk']}{tag}.png"
        if not src.exists():
            print("missing", src)
            continue
        rgba = np.asarray(Image.open(src).convert("RGBA")).copy()
        donors = {}
        for key in row.get("donors") or {}:
            other, at = key.split(":")
            donors[key] = np.asarray(Image.open(tex / f"{other}_c{at}{tag}.png").convert("RGBA")).copy()
        painted, scope = fixes.paint(rgba, row["ops"], donors)
        Image.fromarray(painted).save(out / f"{row['selector']}_c{row['chunk']}_uf3.png")
        print(row["selector"], row["chunk"], "scope texels", int(scope.sum()))


def data(disc: Path, out: Path) -> None:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    rows = entries()
    with bump._Image.open(disc, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for row in rows:
            entry = by_name[row["selector"] + ".IFF"]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunk = fixes._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            if row["kind"] == "unif":
                new, detail = fixes.compile_unif(span, row)
            elif row["kind"] == "name":
                donor_entry = by_name[row["donor_selector"] + ".IFF"]
                donor_raw = image.read_segments(index.sub_extents(donor_entry, 0, donor_entry.size))
                donor = fixes._chunk_for(donor_raw, row["chunk"])
                donor_span = donor_raw[donor.offset:donor.end_offset]
                row["donor_sha256"] = fixes.sha(donor_span)
                new, detail = fixes.compile_name(span, donor_span, row)
            else:
                donors = {}
                for key in sorted(row.get("donors") or {}):
                    other, at = key.split(":")
                    donor_entry = by_name[other + ".IFF"]
                    donor_raw = image.read_segments(index.sub_extents(donor_entry, 0, donor_entry.size))
                    donor = fixes._chunk_for(donor_raw, int(at))
                    donor_span = donor_raw[donor.offset:donor.end_offset]
                    row["donors"][key] = fixes.sha(donor_span)
                    donors[key] = fixes.texture_rgba(donor_span)
                new, detail = fixes.compile_texture(span, row, donors)
                detail = dict(added=len(detail["palette_slots_added"]), scope=detail["level0_scope_texels"])
            print(row["selector"], row["chunk"], row["texture"], json.dumps(detail), flush=True)
            row.update(resource_size=len(raw), offset=chunk.offset, length=len(span),
                       before_sha256=fixes.sha(span), after_sha256=fixes.sha(new))
    document = {"schema": fixes.SCHEMA,
                "source": "uf3 (b773): the uniform elements ur1, uw2 and Noah's 10/14 playtest flagged, each judged "
                          "against the 2026 game highlights (weeks 1 to 5) and kept, reverted to v0.6 or redrawn",
                "method": "Vector art in native texel coordinates, drawn at 4x (4x4 samples per texel, exact "
                          "integer arithmetic) and averaged onto the existing native pixels; existing palette plus "
                          "spare slots, the mud twin's own rule, fixed spans. Runs after the uf1 and uf2 layers.",
                "textures": [{k: row[k] for k in ("selector", "chunk", "texture", "kind", "size", "resource_size",
                                                  "offset", "length", "before_sha256", "after_sha256", "defects",
                                                  "note", "ops", "ints", "donor_selector", "donor_sha256",
                                                  "donors")
                              if k in row} for row in rows]}
    with out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=1)
        stream.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--tex", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--tag", default="_base")
    p.add_argument("selectors", nargs="*")
    d = sub.add_parser("data")
    d.add_argument("--input", type=Path, required=True)
    d.add_argument("--out", type=Path, default=DATA)
    args = parser.parse_args(argv)
    if args.cmd == "preview":
        preview(args.tex, args.out, args.selectors, args.tag)
    else:
        data(args.input, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
