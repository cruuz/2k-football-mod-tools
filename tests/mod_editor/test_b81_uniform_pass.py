"""b81-uniforms: the 2026 uniform pass (data/nfl2k5_kit_fixes_2026_b81u.json, data/nfl2k5_glyph_fixes_2026_b81u.json and
its art folder, tools/b81_uniform_pass.py, kit_fixes.apply_uniforms_b81, glyph_fixes.apply_digits_b81), the nameplate
pass guard that kept the Jaguars name plates and the hyphen fill out of every Studio build, and (batch 4) the nameplate
letter strips redrawn to this season's lettering (``names_png`` and ``name_widths`` rows of the digit document).

The documents' shape and pins, what each first-batch row repaints (measured on the rows themselves), the authoring
helpers on synthetic pictures, the build hooks, and (with the released v0.9 disc on this machine, B81_UNIFORM_DISC)
every row compiled against the real kit package."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_uniform_pass as up  # noqa: E402
from mod_editor.core import (build_steps, mod_build, nfl2k5_glyph_fixes_2026 as gf,  # noqa: E402
                             nfl2k5_kit_fixes_2026 as kf, nfl2k5_nameplate_fixes_2026 as nf)

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
RETAIL = Path(os.environ.get("B81_RETAIL_DISC", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
REHEARSAL = Path(os.environ.get("B81_REHEARSAL_DISC",
                                "/media/noah/Storage/2K5-project/b81-rehearsal/build/full-20261121-155155/full.xiso.iso"))
SIZES = {"jersey00": [512, 256], "pants00": [512, 256], "sleeve00": [128, 128], "socks00": [64, 64]}
#: the Chargers' eight kit packages: home, road, the gold jersey, the gold-pants pair and the navy set
CHARGERS = ("24A0", "24A10", "24A11", "24A9", "24H0", "24H10", "24H11", "24H9")
#: the Bengals' six kit packages: home, road, the White Bengal pair and the orange pair
BENGALS = ("06A0", "06A5", "06A6", "06H0", "06H5", "06H6")
# every package whose numbers this pass draws again (batch 3 added the clubs measured against the 2026 photographs)
REDRAWN = CHARGERS + BENGALS + ("00A0", "00H0", "01A0", "01H0", "07H0", "14A0", "14A10", "14H0", "14H10", "18A0", "18A7",
                               "18H0", "18H7", "28A7", "28H7")
# batch 5 (measured on 2026 club game photographs, BATCH5/digits/judged.json): Rams, Bears, Jets, Commanders, Colts,
# Texans wider; Commanders heavier; Browns lighter (home and road of each)
REDRAWN += ("23H0", "23A0", "05H0", "05A0", "19H0", "19A0", "29H0", "29A0", "11H0", "11A0", "37H0", "37A0", "30H0", "30A0")
# batch 5 alternates: Broncos white and navy, Lions black and Defend the Den, Packers rivalries, Saints white Color
# Rush, Jets black and White Out, Seahawks 26A4 and 26H4, Browns brown, Texans Battle Red
REDRAWN += ("08A5", "08A6", "08H6", "09A2", "09H2", "09A9", "09H9", "10A5", "10H5", "17A1", "17H1", "19A2", "19H2",
            "19A7", "19H7", "26A4", "26H4", "30A3", "30H3", "37A2", "37H2")
# batch 6 (BATCH6/digits/judged.json): Ravens, every package of the one shape set (per-digit: only the 0 and the 4,
# measured 14 and 16 percent wide); Raiders road (silver edge 3 to 4 texels -> 1, black strokes heavier)
RAVENS = ("02A0", "02A2", "02A3", "02H0", "02H2", "02H3")
REDRAWN += RAVENS + ("20A0",)
# Noah's decisions of 11/19 (review_queue/NOAH_DECISIONS_APPLIED.png): Buccaneers road and home with the orange inline the
# 2026 numerals wear (27A0, 27H0), Patriots at full height (16H0, 16A0); the Browns road set (30A0, already redrawn) in
# the charcoal the photographs show
REDRAWN += ("27A0", "27H0", "16H0", "16A0")
# R2 (order R2-B): one Broncos number face on every look that wears it, so the home, road and Christmas navy sets join
# the alternates (08A5, 08A6, 08H6 already redrawn); the Ravens 4, the Jets 2 and the Raiders road edge change inside
# sets already listed
BRONCOS = ("08A0", "08A5", "08A6", "08H0", "08H5", "08H6")
REDRAWN += ("08H0", "08A0", "08H5")
# Noah 11/21 (uniform verdicts, uniform-marks/NOAH_VERDICTS_20261121.json: "Jersey number font was perfect in v0.9, new one is
# a regression", "Old number font is better"): these primaries wear the released v0.9 digits again; their digit rows (jersey and
# arm) were dropped from the document (b81-uniform-fix1)
REVERTED_TO_V09 = ("01H0", "01A0", "30H0", "30A0", "08H0", "08A0", "37H0", "37A0", "11H0", "11A0", "23H0", "23A0", "29H0")
# Noah 11/21 (b81-uniform-exact, his second verdict on the Chargers numerals: "The first picture is the best when they're
# italicized. That looks the closest to reality"): the Chargers home and road wear the released v0.9 italic digits again; their
# 20 upright digit rows were dropped (b81-uniform-pass2). The alternates keep R2's upright set until he rules on them.
REVERTED_TO_V09 += ("24H0", "24A0")
# Advisor round 2 (11/24; Noah: "let the advisor approve"), coordinator ruling: the Commanders road follows his home verdict
# ("Old number font is better") and his never-worse-than-v0.9 rule: 29A0 wears the released v0.9 digits again (b81-uniform-pass2)
REVERTED_TO_V09 += ("29A0",)
# Coordinator (11/24, the owner's Chargers ruling applied to the alternates): every Chargers kit wears the released v0.9 italic
# digits; the alternates' upright rows are dropped too (b81-uniform-pass2)
REVERTED_TO_V09 += ("24A9", "24H9", "24A10", "24H10", "24A11", "24H11")
# Advisor, alternates round (11/24; Noah delegated their approval): the alternates that carried a number font he rejected on
# the same club go back to the released v0.9 digits (Broncos 08H5/A5, 08H6/A6, Texans 37H2/A2, Browns 30H3/A3), and so do
# the Packers Rivalries 10H5/A5 (stray outline ticks on the redrawn set)
REVERTED_TO_V09 += ("08H5", "08A5", "08H6", "08A6", "37H2", "37A2", "30H3", "30A3", "10H5", "10A5")
# Noah 11/23 ("use charcoal browns numbers but old font"): the Browns road wears the released v0.9 digits recoloured to the
# charcoal of its name letters: 20 digit_derived rows, one colour swap on the glyph the build holds (b81-uniform-pass2)
V09_FONT_RECOLOURED = ("30A0",)
# b81 fold-in (11/24): the approved kits' helmet numerals (hn48..hn57, chunks 23-32) as the lanes staged them: colour swaps
# of the released set (digit_derived), whole sets of ten
HELMET_NUMERALS = ("04H0", "06A0", "06H0", "09A0", "09H0", "11A0", "11H0")
# b81-uniform-pass2 fold-in (11/24): the approved kits' textures as the lanes drew them (P/art/final: collars, sleeve
# stripes, the Patriots shoulder stripe, the Seahawks/Chargers set, the lane's clubs) and the advisor's alternates fixes
# (copies of approved primary jerseys and collars, the Lions grey), in retail-free form. Their jersey rows repaint more
# than the chest strip (collars from row 42, shoulders, whole jerseys); the rows added beside the earlier batches:
PASS2_JERSEY = ("03A0", "04A0", "04H0", "07A0", "09A9", "09H9", "16A0", "16H0", "17A0", "17A3", "17H0", "17H3", "19A0", "19A7",
                "19H0", "19H7", "21A0", "21A10", "21A12", "21H0", "21H10", "21H12", "22A0", "23A0", "23H0", "24A0", "24A10",
                "24H0", "24H10", "26A0", "26A4", "26H0", "26H4", "27A0", "27H0", "29A0", "30A0", "30H0", "37A0")
PASS2_ADDED = (("00A0", "pants00"), ("01H0", "pants00"), ("02A0", "pants00"), ("02H0", "pants00"), ("07A0", "pants00"),
               ("07A0", "sleeve00"), ("07H0", "pants00"), ("08A0", "sleeve00"), ("08H0", "sleeve00"), ("09A0", "pants00"),
               ("09A9", "sleeve00"), ("09H9", "sleeve00"), ("12H0", "pants00"), ("12H0", "socks00"), ("13A0", "sleeve00"),
               ("14H0", "pants00"), ("15A0", "sleeve00"), ("15H0", "sleeve00"), ("17A0", "pants00"), ("17H0", "pants00"),
               ("18A0", "pants00"), ("18H0", "pants00"), ("19A0", "pants00"), ("19H0", "pants00"), ("23A0", "sleeve00"),
               ("23H0", "pants00"), ("23H0", "sleeve00"), ("24A0", "pants00"), ("24A0", "sleeve00"), ("24A10", "sleeve00"),
               ("24H0", "pants00"), ("24H0", "sleeve00"), ("24H10", "sleeve00"), ("25A0", "pants00"), ("26A0", "pants00"),
               ("26A0", "sleeve00"), ("26A4", "sleeve00"), ("26H0", "pants00"), ("26H0", "sleeve00"), ("28A0", "pants00"),
               ("29A0", "pants00"), ("29H0", "pants00"), ("30A0", "pants00"), ("30A0", "sleeve00"), ("30H0", "pants00"),
               ("30H0", "sleeve00"), ("37A0", "pants00"), ("37A0", "sleeve00"), ("37H0", "pants00"),
               ("09A9", "socks00"), ("09H9", "socks00"))   # advisor 11/24: Defend the Den dark socks
# rows whose input an earlier step of the build writes (the swoosh step sw1 leaves these sleeves, not the released v0.9 ones):
# pinned to that input, sw1's after pin (BuildInputRows); the gate measures them on a build of the branch base (B81_TEXEL_INPUTS)
BUILD_INPUT_ROWS = (("07H0", 3), ("09A9", 3), ("09H9", 3), ("26A0", 3), ("26H0", 3))
# the approved helmet shells (helmet00 Standard, helmet02 Revolution): Lions stripe order, Dolphins stripe colours,
# Commanders stripe proportions; pinned to the helmet the build holds after the b81 helmet cleanup, rules only
HELMET_KITS = ("09A0", "09H0", "14A0", "14H0", "29A0", "29H0")
# the advisor (11/24) on Defend the Den: "Make body, sleeves and pants one colour": a neutral grey, stored as the
# palettes' nearest entries
DET_DTD_GREY = {"jersey00": (0xBE, 0xC0, 0xC1), "pants00": (0xBF, 0xC0, 0xC2)}
REVERTED_TO_V09 = tuple(s for s in REVERTED_TO_V09 if s not in V09_FONT_RECOLOURED)
#: the Chargers packages that still wear the one upright R2 shape set
CHARGERS_R2 = tuple(s for s in CHARGERS if s not in REVERTED_TO_V09)
REDRAWN = tuple(dict.fromkeys(s for s in REDRAWN if s not in REVERTED_TO_V09))
#: the Broncos looks that still wear R2's one face (the home and road went back to v0.9's)
BRONCOS_ONE_FACE = tuple(s for s in BRONCOS if s not in REVERTED_TO_V09)
#: the Raiders road silver edge measured against the jersey white on the week 8 and week 9 road photographs (R2-B)
LV_ROAD_SILVER = (0xA5, 0xAD, 0xB0)
#: the Buccaneers' orange inline (decision 1) and the Browns' road charcoal (decision 3)
TB_ORANGE = (0xD9, 0x64, 0x28)
CLE_CHARCOAL = (0x3B, 0x3B, 0x3B)
#: the Buccaneers road set is the approved prototype: the released digits with the orange inline added (one new colour),
#: so it keeps the released set's burnt orange edge shading between the black edge and the inline: a fourth flat layer
FOUR_LAYERS = ("27A0",)
#: sets redrawn digit by digit: the digits each one carries (every other redrawn set carries all ten)
PER_DIGIT = {selector: (0, 4) for selector in RAVENS}
#: batch 4 (KITS4): the only jersey rows that repaint beyond the chest strip under the collar
WHOLE_JERSEY = ("09A9", "09H9", "26H4")
#: R2 (order R2-C): the Commanders road shoulder swoosh, drawn by the game across the torso texture's front/back seam:
#: (first column, first row, last column + 1, last row + 1) of the hook on the front panel and the tail on the back panel
WAS_ROAD_SWOOSH = ((54, 9, 72, 22), (250, 9, 268, 22), (283, 14, 298, 40), (483, 14, 496, 40))


def kit_rows():
    """The texture rows (``tset``); the Unif data rows of the b81 fold-in are ``unif_rows``."""
    return [r for r in kf.uniforms_b81()["textures"] if r["kind"] == "tset"]


def unif_rows():
    return [r for r in kf.uniforms_b81()["textures"] if r["kind"] == "unif"]


def helmet_rows():
    """The approved helmet shells of the b81 fold-in (kind ``txtr``, chunks 11 and 12): see HelmetRows."""
    return [r for r in kf.uniforms_b81()["textures"] if r["kind"] == "txtr"]


def digit_rows():
    return [r for r in gf.digits_b81()["textures"] if r["kind"] == "digit_png"]


def all_digit_rows():
    """b81-retail-free-art: the shipped pictures and the ``digit_derived`` rows made at build time."""
    return [r for r in gf.digits_b81()["textures"] if r["kind"] in ("digit_png", "digit_derived")]


_KITS = {}


def picture(row):
    """A digit row's picture: its PNG, or for a ``digit_derived`` row its operations on the glyph the released disc
    holds (None without the disc: the picture exists only at build time)."""
    if row["kind"] == "digit_png":
        return png_rgba(gf.art_folder(gf.digits_b81()) / row["png"])[0]
    if not DISC.is_file():
        return None
    if not _KITS:
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        wanted = {r["selector"] for r in all_digit_rows()}
        with bump._Image.open(DISC, writable=False) as image:
            index = bump._parsed_index(image)
            for entry in index.entries:
                name = bump.logical_name_for(entry.name_id)
                if name and name[:-4] in wanted:
                    _KITS[name[:-4]] = image.read_segments(index.sub_extents(entry, 0, entry.size))
    raw = _KITS[row["selector"]]
    chunk = gf._chunk_for(raw, row["chunk"])
    return gf.derive_digit(gf.digit_level0(raw[chunk.offset:chunk.end_offset]), row["derive"])


def run_texels(row):
    """{(x, y): (r, g, b)} of every texel a row's runs repaint."""
    out = {}
    for op in row["ops"]:
        if op["op"] != "runs":
            continue
        for y, x0, colours in op["rows"]:
            for i in range(len(colours) // 6):
                out[(x0 + i, y)] = tuple(int(colours[6 * i + k:6 * i + k + 2], 16) for k in (0, 2, 4))
    return out


def near(colour, target, tolerance=24):
    return max(abs(a - b) for a, b in zip(colour, target)) <= tolerance


def png_rgba(path):
    from PIL import Image
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8), dict(image.info)


class KitDocument(unittest.TestCase):
    def test_schema_rows_and_pins(self):
        document = kf.uniforms_b81()
        self.assertEqual(document["schema"], kf.SCHEMA)
        self.assertTrue(document["source"] and document["method"])
        seen = set()
        for row in document["textures"]:
            key = (row["selector"], row["chunk"])
            self.assertNotIn(key, seen)
            seen.add(key)
            if row["kind"] == "unif":                       # the Unif data rows of the b81 fold-in: see UnifDocument
                continue
            if row["kind"] == "txtr":                       # the approved helmet shells of the b81 fold-in: see HelmetRows
                continue
            self.assertEqual(row["kind"], "tset")
            self.assertEqual((row["chunk"], "tset"), up.chunk_of(row["texture"]))
            self.assertEqual(row["size"][:2], SIZES[row["texture"]])
            self.assertEqual(len(row["before_sha256"]), 64)
            self.assertEqual(len(row["after_sha256"]), 64)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertGreater(row["resource_size"], row["offset"] + row["length"] - 1)
            self.assertTrue(row["note"] and row["defects"] and row["reference"], row["selector"])
            # b81-retail-free-art (review rule, ruling 2): a converted row names its palette colours (``want``), clears
            # old marks by rule (``clear``), applies build-time rules (``rule``, ``stamp``) and lists only drawn texels
            # in its runs, or none at all
            kinds = [op["op"] for op in row["ops"]]
            self.assertTrue(set(kinds) <= {"texels", "runs", "clear", "want", "rule", "stamp"}, (row["selector"], kinds))
            self.assertTrue(kinds.count("runs") <= 1 or "clear" in kinds, row["selector"])
            self.assertGreater(row["texels"], 0)

    def test_every_run_stays_inside_its_texture(self):
        for row in kit_rows():
            width, height = row["size"][:2]
            for op in row["ops"]:
                if op["op"] == "clear":
                    self.assertTrue(all(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height for x0, y0, x1, y1 in op["boxes"]))
            for y, x0, colours in [r for op in row["ops"] if op["op"] == "runs" for r in op["rows"]]:
                self.assertEqual(len(colours) % 6, 0)
                bytes.fromhex(colours)
                self.assertTrue(0 <= y < height and 0 <= x0 and x0 + len(colours) // 6 <= width, (row["selector"], y, x0))

    def test_every_named_colour_is_a_texel_the_runs_also_paint(self):
        # the ``texels`` operations only name the art's colours for the palette; the runs carry the picture
        for row in kit_rows():
            painted = run_texels(row)
            carriers = [op for op in row["ops"] if op["op"] == "texels"]
            self.assertLessEqual(len(carriers), 48, row["selector"])
            cleared = {op["to"] for op in row["ops"] if op["op"] == "clear"}
            colours = {"#%02X%02X%02X" % c for c in painted.values()} | cleared
            for op in carriers:
                (x, y), = op["points"]
                if not cleared:
                    self.assertEqual("#%02X%02X%02X" % painted[(x, y)], op["color"], row["selector"])
                else:                               # a converted row: the clear decides some texels (the disc test
                    self.assertIn(op["color"], colours, row["selector"])     # replays it on the real texture)

    def test_only_a_named_row_may_fold_a_palette_twin(self):
        folded = {(r["selector"], r["texture"]): (r["folded_twin_entries"], r["texels_moved_one_level"])
                  for r in kit_rows() if "folded_twin_entries" in r}
        self.assertEqual(folded, {("23A0", "pants00"): (1, 7)})       # the Rams road pants palette is full

    def test_the_first_batch_is_the_reviewed_kits(self):
        self.assertEqual(sorted((r["selector"], r["texture"]) for r in kit_rows() if r["texture"] != "jersey00"),
                         sorted(list(PASS2_ADDED) + [("00A6", "sleeve00"), ("00A7", "sleeve00"), ("00H6", "sleeve00"), ("00H7", "sleeve00"), ("01A9", "pants00"),
                          ("01H9", "pants00"),
                          ("02A3", "pants00"), ("02H3", "pants00"),
                          ("03A0", "sleeve00"), ("03H0", "sleeve00"), ("04A2", "pants00"), ("04H2", "pants00"),
                          ("06A0", "pants00"), ("06A0", "sleeve00"), ("06A5", "pants00"), ("06A5", "sleeve00"),
                          ("06A6", "pants00"), ("06A6", "sleeve00"), ("06H0", "pants00"), ("06H5", "pants00"),
                          ("06H5", "sleeve00"), ("06H6", "pants00"), ("06H6", "sleeve00"),
                          ("07A7", "sleeve00"), ("07H0", "sleeve00"), ("07H7", "sleeve00"),
                          ("09A9", "pants00"), ("09H9", "pants00"), ("11A3", "sleeve00"), ("11H3", "sleeve00"),
                          ("14A0", "pants00"), ("14A0", "sleeve00"), ("14A0", "socks00"), ("14H0", "sleeve00"),
                          ("15A0", "pants00"), ("15H0", "pants00"), ("15H0", "socks00"),
                          ("17A0", "sleeve00"), ("17A3", "sleeve00"), ("17A8", "pants00"), ("17A8", "sleeve00"),
                          ("17H0", "sleeve00"), ("17H3", "sleeve00"), ("17H8", "pants00"), ("17H8", "sleeve00"),
                          ("19A2", "pants00"), ("19H2", "pants00"),
                          ("21A4", "sleeve00"), ("21H4", "sleeve00"), ("23A0", "pants00"), ("25H0", "pants00"),
                          ("26A4", "pants00"), ("26A4", "socks00"), ("26H4", "sleeve00"), ("27A0", "pants00"),
                          ("27H0", "pants00")]))
        # batch 3: the panther the real Panthers alternate pants lack (04H2/04A2), the star the real Cowboys navy
        # sleeves and Arctic shoulder blocks lack (07H0, 07H7/07A7)
        # batch 4 marks (MARKS4): swooshes recoloured to the measured 2026 colour (Cardinals black 00H6/00A6, Bengals
        # 06A0/06H5/06A5/06H6/06A6, Colts 11H3/11A3, Dolphins road 14A0 sleeves; Falcons 1966 hip swoosh 01H9/01A9),
        # the Eagles kelly green sleeve eagle at its real size (21H4/21A4)
        # batch 4 kits (KITS4): Ravens Darkness talon stripe silver (02H3/02A3), Lions Defend the Den pants pale
        # blue-grey (09H9/09A9), Dolphins road white socks (14A0, with the sock-coloured lower leg of the pants),
        # Saints gameday gold pants (17H8/17A8), Jets legacy black pants without the green stripe (19H2/19A2),
        # Seahawks road white socks (26A4, likewise), Seahawks 26H4 sleeves (the 26H0 art of the same jersey)
        # batch 5 marks: the Cardinals desert sleeve swoosh red, not copper (00H7/00A7)
        # batch 6: the Dolphins sleeve logo at its measured size (14H0, 14A0), the 49ers home pants stripe at its
        # measured width (25H0)
        # Noah 11/19 (decision 5, "use the prototype"): the Buccaneers pants stripe black, orange, red, orange, black at
        # about 5.8 cm on the white home pants (27H0) and the pewter road pants that wear the same stripe (27A0)
        # R2 (order R2-C): the Saints sleeve fleur-de-lis at the emblem's own proportions (17H0 17A0, and 17H3 17A3 17H8
        # 17A8, which carry the same fleur art at the same squat size); the Bengals pants tiger strokes, one geometry on all six Bengals pants (06H0 06A0 06H5 06A5
        # 06H6 06A6), each in its own stroke colour; the Lions Defend the Den side stripe (09H9/09A9, rows already listed)

    def test_the_jersey_rows_repaint_only_the_chest_under_the_collar(self):
        # Round 2 (Noah 11/18: "the NY logo on the giants jersey below the nfl patch is too large. There are likely
        # similar issues on other jerseys"): the league collar shield at its real size on 166 packages (12 by 16
        # texels; it was 8 by 10), wordmarks moved clear of it, the Giants mark as wide as the shield. A jersey row
        # may touch nothing but the strip of chest between the collar point and the number.
        # Batch 3 added: wordmarks redrawn at their real width (Eagles, Titans, Broncos), the Saints 60th patch at its
        # real size, the Texans memorial oval, the Panthers alternate and Bills Nickel City shields.
        # Batch 4 (KITS4) named the only jerseys repainted beyond that strip: see test_the_batch_4_whole_jersey_rows.
        # R2 (order R2-C): the Commanders road 29A0 also repaints its two shoulder swooshes (WAS_ROAD_SWOOSH).
        jerseys = [r for r in kit_rows() if r["texture"] == "jersey00"]
        self.assertEqual(len(jerseys), 170)
        self.assertEqual(len({r["selector"] for r in jerseys}), 170)
        self.assertTrue(set(WHOLE_JERSEY) <= {r["selector"] for r in jerseys})
        for row in jerseys:
            if row["selector"] in WHOLE_JERSEY or row["selector"] in PASS2_JERSEY:
                continue
            for op in row["ops"]:                   # a clear stays inside the strip (or 29A0's swoosh boxes) too
                for x0, y0, x1, y1 in op.get("boxes", ()) if op["op"] == "clear" else ():
                    self.assertTrue((58 <= y0 and y1 <= 113 and 90 <= x0 and x1 <= 216)
                                    or (row["selector"] == "29A0" and any(a <= x0 and x1 <= c and b <= y0 and y1 <= d
                                                                          for a, b, c, d in WAS_ROAD_SWOOSH)),
                                    (row["selector"], (x0, y0, x1, y1)))
            for run in [r for op in row["ops"] if op["op"] == "runs" for r in op["rows"]]:   # [row, first column, colours]
                if row["selector"] == "29A0" and any(x0 <= run[1] and run[1] + len(run[2]) // 6 <= x1 and y0 <= run[0] < y1
                                                     for x0, y0, x1, y1 in WAS_ROAD_SWOOSH):
                    continue
                self.assertTrue(58 <= run[0] <= 112, (row["selector"], run[:2]))   # down to the old lettering some kits lose
                self.assertTrue(90 <= run[1] and run[1] + len(run[2]) // 6 <= 216, (row["selector"], run[:2]))
        for selector in ("25H7", "25A7", "28H7", "28A7", "11H4", "11A4", "07H9", "07A9"):
            self.assertNotIn(selector, {r["selector"] for r in jerseys})        # open: no 2026 picture of the look

    def test_no_row_touches_a_helmet_or_the_far_away_atlas(self):
        for row in kit_rows():
            self.assertIn(row["chunk"], (1, 2, 3, 4), row["selector"])
        for row in digit_rows():
            self.assertTrue(13 <= row["chunk"] <= 22 or 33 <= row["chunk"] <= 42, row["selector"])  # jersey and arm digits, never the helmet's


class UnifDocument(unittest.TestCase):
    """b81 fold-in (11/24): the approved kits' Unif fields as the lanes staged them (no texel): the arm numbers on the
    shoulder tops (route 1; Noah 11/21 on the Bears: "Shows sleeve numbers instead of shoulder numbers"), the helmet number
    places the helmet lane chose (helmet_number_route at 0x3C) and the Vikings facemask."""

    SHOULDER_TOPS = ("00H0", "03A0", "03H0", "05A0", "05H0", "19A0", "19H0", "29A0", "37H0",
                     # the modern-template alternates of the same clubs (coordinator's ruling 11/24 under Noah's standing
                     # rule "Yes fix every new bug we find like that"); the Cowboys Arctic 07H7/A7 keeps its sleeve number
                     # (the 10/26 photographs); the advisor's batch-2 check put the Jets Gotham 19H6/A6 (numbers across the
                     # grey shoulder bars) and the 1965-68 throwback 19H4/A4 (numbers coloured for the sleeve) back on the sleeve
                     "03A3", "03A8", "03A9", "03H3", "03H8", "03H9", "05A4", "05A6", "05H4", "05H6", "19A7", "19H7",
                     "37A2", "37H2")
    ON_THE_SLEEVE = ("07A7", "07H7", "19A4", "19A6", "19H4", "19H6")

    def test_the_rows_set_only_reviewed_fields(self):
        rows = unif_rows()
        self.assertEqual(len(rows), 48)
        self.assertEqual(len({r["selector"] for r in rows}), 48)
        self.assertFalse(set(self.ON_THE_SLEEVE) & {r["selector"] for r in rows})
        for row in rows:
            self.assertEqual((row["chunk"], row["texture"]), (0, "Unif"), row["selector"])
            self.assertNotIn("ops", row)
            self.assertTrue(row.get("ints") or row.get("fields"), row["selector"])
            for key, value in row.get("ints", {}).items():
                self.assertIn(value, kf.UNIF_INTS[key][1], (row["selector"], key))
            self.assertTrue(row["note"] and row["defects"])
        self.assertEqual(sorted(r["selector"] for r in rows if r.get("ints", {}).get("number_route") == 1),
                         sorted(self.SHOULDER_TOPS))
        self.assertEqual({r["selector"]: r["fields"] for r in rows if "fields" in r},
                         {"15H0": {"facemask": "#0C0B0C"}, "15A0": {"facemask": "#0C0B0C"}})

    @unittest.skipUnless(DISC.is_file(), "the released v0.9 disc")
    def test_the_rows_compile_to_their_pins(self):
        rows = unif_rows()
        kits = up.read_kits(DISC, sorted({r["selector"] for r in rows}))
        for row in rows:
            raw = kits[row["selector"]]
            chunk = kf._chunk_for(raw, 0)
            span = raw[chunk.offset:chunk.end_offset]
            self.assertEqual(hashlib.sha256(span).hexdigest(), row["before_sha256"], row["selector"])
            new, _detail = kf.compile_unif(span, row)
            self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"], row["selector"])
            self.assertEqual(len(new), len(span))


class HelmetRows(unittest.TestCase):
    """b81 fold-in (11/24): the approved helmet shells (helmet00 Standard, helmet02 Revolution) of the Lions (stripe
    order), Dolphins (stripe colours) and Commanders (stripe proportions), as the helmet lane staged them. The uniform
    pass runs right after the b81 helmet cleanup, so these rows are pinned to the helmet that step leaves; they carry
    rules only (no texel data: the gate measures rows on the released disc, which these inputs are not)."""

    def test_the_rows_are_rules_on_the_cleaned_helmets(self):
        rows = helmet_rows()
        self.assertEqual(sorted((r["selector"], r["chunk"], r["texture"]) for r in rows),
                         sorted((s, c, t) for s in HELMET_KITS for c, t in ((11, "helmet00"), (12, "helmet02"))))
        for row in rows:
            self.assertEqual(row["size"][:2], [256, 256])
            self.assertTrue(row["note"] and row["defects"])
            self.assertTrue({op["op"] for op in row["ops"]} <= {"want", "clear", "rule"}, row["selector"])

    @unittest.skipUnless(REHEARSAL.is_file(), "a beta 81 build of the branch base (B81_REHEARSAL_DISC)")
    def test_the_rows_compile_to_their_pins_after_the_cleanup(self):
        # the input is the helmet every earlier step of a build leaves (the b81 cleanup last): read from a build of the
        # branch base, which holds exactly that (the uniform pass's rows were not in it)
        kits = up.read_kits(REHEARSAL, list(HELMET_KITS))
        for selector in HELMET_KITS:
            raw = kits[selector]
            for row in [r for r in helmet_rows() if r["selector"] == selector]:
                chunk = kf._chunk_for(raw, row["chunk"])
                span = raw[chunk.offset:chunk.end_offset]
                self.assertEqual(hashlib.sha256(span).hexdigest(), row["before_sha256"], (selector, row["texture"]))
                new, _detail = kf.compile_texture(span, row)
                self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"], (selector, row["texture"]))


class BuildInputRows(unittest.TestCase):
    """b81-uniform-pass2 (11/24, the final-build proof): five sleeve rows pinned to the released v0.9 span never applied in a
    build, because the swoosh step (data/nfl2k5_kit_fixes_2026_sw1.json) writes these sleeves first. They are pinned to its
    output, so the approved sleeves ship."""

    def test_the_rows_wait_on_the_swoosh_steps_output(self):
        sw1 = {(r["selector"], r["chunk"]): r for r in json.loads((ROOT / "data/nfl2k5_kit_fixes_2026_sw1.json").read_text())["textures"]}
        rows = {(r["selector"], r["chunk"]): r for r in kit_rows()}
        for key in BUILD_INPUT_ROWS:
            self.assertEqual(rows[key]["before_sha256"], sw1[key]["after_sha256"], key)

    @unittest.skipUnless(REHEARSAL.is_file(), "a beta 81 build of the branch base (B81_REHEARSAL_DISC)")
    def test_the_rows_compile_to_their_pins_on_the_builds_input(self):
        rows = {(r["selector"], r["chunk"]): r for r in kit_rows()}
        kits = up.read_kits(REHEARSAL, sorted({s for s, _c in BUILD_INPUT_ROWS}))
        for key in BUILD_INPUT_ROWS:
            raw = kits[key[0]]
            chunk = kf._chunk_for(raw, key[1])
            span = raw[chunk.offset:chunk.end_offset]
            self.assertEqual(hashlib.sha256(span).hexdigest(), rows[key]["before_sha256"], key)
            new, _detail = kf.compile_texture(span, rows[key])
            self.assertEqual(hashlib.sha256(new).hexdigest(), rows[key]["after_sha256"], key)


class DigitDocument(unittest.TestCase):
    def test_schema_art_and_pins(self):
        document = gf.digits_b81()
        self.assertEqual(document["schema"], gf.SCHEMA)
        self.assertEqual(document["art"], up.DIGIT_ART)
        folder = gf.art_folder(document)
        self.assertEqual(folder, ROOT / "data" / up.DIGIT_ART)
        seen, files = set(), {r["png"] for r in document["textures"] if r.get("png")}
        for row in document["textures"]:
            key = (row["selector"], row["chunk"])
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertIn(row["kind"], ("digit_png", "names_png", "name_widths", "digit_derived", "names_derived"))
            if row["kind"] in ("digit_derived", "names_derived"):   # b81-retail-free-art: no picture ships
                self.assertNotIn("png", row)
                self.assertEqual(len(row["rgba_sha256"]), 64)
                continue
            if row["kind"] != "digit_png":
                continue                                    # the nameplate rows: see NameplateDocument
            self.assertEqual(row["texture"], str(48 + row["chunk"] - 13) if row["chunk"] < 23
                             else "an" + str(48 + row["chunk"] - 33))
            payload = (folder / row["png"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), row["png_sha256"], row["png"])
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertTrue(row["note"] and row["defects"])
            files.add(row["png"])
        self.assertEqual(sorted(p.name for p in folder.glob("*.png")), sorted(files))           # no stray art

    def test_the_redrawn_sets_are_whole_ten_jersey_digits_and_arm_digits_where_the_kit_has_them(self):
        by, helmet = {}, {}
        for row in all_digit_rows():
            if 23 <= row["chunk"] <= 32:            # the helmet numerals (b81 fold-in): see HELMET_NUMERALS below
                helmet.setdefault(row["selector"], set()).add(row["chunk"])
                continue
            by.setdefault(row["selector"], set()).add(row["chunk"])
        self.assertEqual(tuple(sorted(by)), tuple(sorted(REDRAWN)))
        self.assertEqual(helmet, {selector: set(range(23, 33)) for selector in HELMET_NUMERALS})
        for selector, chunks in by.items():
            digits = PER_DIGIT.get(selector, range(10))
            self.assertEqual({c for c in chunks if c < 23}, {13 + d for d in digits}, selector)
            self.assertIn({c for c in chunks if c >= 33}, (set(), {33 + d for d in digits}), selector)

    def test_art_is_as_authored_and_in_flat_colours(self):
        from mod_editor.core.nfl2k5_digit_art import REGISTRATION_KEY, registration_mode
        folder = gf.art_folder(gf.digits_b81())
        for path in sorted({folder / r["png"] for r in digit_rows() if "png" in r}):
            rgba, info = png_rgba(path)
            self.assertEqual(info.get(REGISTRATION_KEY), "as_authored", path.name)
            self.assertEqual(registration_mode(path.read_bytes()), "as_authored")
        for row in all_digit_rows():
            rgba = picture(row)
            if rgba is None:
                continue
            path = Path(row.get("png") or "%s_%s_%d" % (row["selector"], row["texture"], row["chunk"]))
            self.assertIn(rgba.shape, ((64, 64, 4), (32, 32, 4)), path.name)
            solid = rgba[rgba[..., 3] == 255][:, :3]
            colours, counts = np.unique(solid, axis=0, return_counts=True)
            self.assertGreater(len(solid), 500 if rgba.shape[0] == 64 else 100, path.name)
            layers = 4 if row["selector"] in FOUR_LAYERS else 3
            top = counts.argsort()[::-1][:layers]
            self.assertGreater(counts[top].sum(), 0.8 * len(solid), path.name)        # a fill, an outline, at most an inline

    def test_every_redrawn_jersey_number_stands_full_height_inside_the_safe_columns(self):
        # batch 3: a number is 62 rows of its 64 cell (22.2 cm on the player, the collar shield 0.141 of that as on the
        # real jersey). The pack drew several sets 50 to 56 rows tall. Two-digit numbers are cut outside columns 12-51.
        folder = gf.art_folder(gf.digits_b81())
        for row in all_digit_rows():
            if row["chunk"] > 22:
                continue
            rgba = picture(row)
            if rgba is None:
                continue
            solid = rgba[..., 3] > 127
            rows = np.flatnonzero(solid.any(axis=1)); cols = np.flatnonzero(solid.any(axis=0))
            name = row.get("png", (row["selector"], row["chunk"]))
            self.assertGreaterEqual(int(rows.max() - rows.min() + 1), 61, name)
            self.assertTrue(12 <= cols.min() and cols.max() <= 51, (name, int(cols.min()), int(cols.max())))

    def test_the_alternates_wear_their_primaries_final_digit_shapes(self):
        # Advisor, alternates round (11/24; Noah delegated the alternates' approval): the Bengals White Bengal 06H5/06A5 and
        # Open in Orange 06H6/06A6 take the final Bengals set of the primaries (the clean redraw: "the 2 has the sharp down on
        # the top of the 2 curve ... We need number refinement"), the Dolphins Rivalries 14H10/14A10 the primaries' in-between
        # set ("Make number font in between the old and new, neither are right"), each in its own colours: the same shapes
        by = {(r["selector"], r["chunk"]): r for r in all_digit_rows()}
        for primary, alternates in (("06A0", ("06H5", "06A5", "06H6", "06A6")), ("14H0", ("14H10", "14A10"))):
            for chunk in range(13, 23):
                want = picture(by[(primary, chunk)])
                if want is None:
                    continue
                for selector in alternates:
                    got = picture(by[(selector, chunk)])
                    self.assertTrue(np.array_equal(got[..., 3], want[..., 3]), (selector, chunk))
        for selector, chunk in by:                  # the Dolphins alternates' shoulder digits too (the primaries have none)
            if selector in ("14H10", "14A10") and chunk >= 33:
                self.assertTrue(np.array_equal(picture(by[(selector, chunk)])[..., 3], picture(by[("14H0", chunk - 20)])[..., 3]),
                                (selector, chunk))

    def test_number_widths_follow_the_measured_real_numbers(self):
        # width of the 0 in texels at 62 rows = real width over height x 62 / 1.048 (the cell is 23.8 by 22.7 cm)
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r for r in all_digit_rows()}
        for selector, width in (("18H0", 37), ("18A0", 37), ("18H7", 37), ("24A0", 35), ("00H0", 37), ("00A0", 37),
                                ("01H0", 39), ("06H0", 31), ("14H0", 32), ("07H0", 35), ("28H7", 36),   # 28H7: 34 and its 2 texel dark layer
                                # batch 5: real wider than 40 columns allow (two-digit numbers are cut outside 12-51): 40
                                ("23H0", 40), ("23A0", 40), ("05H0", 30), ("05A0", 30), ("19H0", 38), ("19A0", 38),
                                ("29H0", 40), ("29A0", 40), ("11H0", 40), ("11A0", 40), ("37H0", 40), ("37A0", 40),
                                ("30H0", 35), ("30A0", 35), ("09A2", 37),
                                ("09H2", 37), ("09A9", 40), ("09H9", 40), ("10A5", 38), ("10H5", 38), ("17A1", 37), ("17H1", 37),
                                ("19A2", 38), ("19H2", 38), ("19A7", 38), ("19H7", 38), ("26A4", 38), ("26H4", 38), ("30A3", 35),
                                ("30H3", 35), ("37A2", 40), ("37H2", 40),
                                # batch 6: the Ravens 0 at 33 (real 0.554; the released 37) and the Raiders road as released
                                ("02H0", 33), ("02A0", 33), ("02A2", 33), ("02A3", 33), ("02H2", 33), ("02H3", 33), ("20A0", 37),
                                # R2: one Broncos face, the 2026 photographs of the orange, white and navy jerseys pooled
                                # (15 digits, 0.613); restated from 40 for the alternates (batch 5's separate pool)
                                *((selector, 36) for selector in BRONCOS)):
            # 14H0: Noah 11/21 "Make number font in between the old and new, neither are right": v0.9 29, R2 37, pass2 32

            if selector in REVERTED_TO_V09:
                self.assertNotIn((selector, 13), by, selector)                   # back to the released v0.9 digits
                continue
            if selector in V09_FONT_RECOLOURED:                                      # v0.9 widths, recoloured only
                continue
            rgba = picture(by[(selector, 13)])
            if rgba is None:
                continue
            solid = rgba[..., 3] > 127
            cols = np.flatnonzero(solid.any(axis=0))
            self.assertLessEqual(abs(int(cols.max() - cols.min() + 1) - width), 1, selector)

    def test_every_chargers_kit_wears_the_released_italic_digits(self):
        # Noah 11/21 (b81-uniform-exact): "The first picture is the best when they're italicized. That looks the closest to
        # reality". Rounds 1 and 2 had stood every Chargers set upright; pass2 dropped those rows from the home and road and
        # then (coordinator 11/24) from the six alternates, so the build keeps the released v0.9 digits on all eight
        self.assertEqual(CHARGERS_R2, ())
        self.assertEqual([r for r in all_digit_rows() if r["selector"] in CHARGERS], [])

    def test_the_bengals_digits_wear_a_hairline_ring_and_open_counters(self):
        # Noah 11/18: "bengals jersey number font isnt accurate". Measured against the 2026 frames the ring was 2 to 3
        # texels (a hairline on the jersey) and it closed the counters; the digits were also narrow (0.50 of the height).
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for selector in BENGALS:
            heights, tops = [], []
            for chunk in range(13, 23):
                rgba, _info = png_rgba(folder / by[(selector, chunk)])
                solid = rgba[..., 3] > 127
                colours, counts = np.unique(rgba[rgba[..., 3] == 255][:, :3], axis=0, return_counts=True)
                fill, ring = colours[counts.argsort()[::-1][:2]]
                is_ring = solid & (np.abs(rgba[..., :3].astype(int) - ring).max(axis=2) < 40)
                is_fill = solid & (np.abs(rgba[..., :3].astype(int) - fill).max(axis=2) < 40)
                # a ring of about 1.3 texels is under half the fill's area even on the thin 7 (at 2 to 3 texels it
                # was close to the fill's own area)
                self.assertLess(is_ring.sum(), 0.55 * is_fill.sum(), (selector, chunk))
                rows = np.flatnonzero(solid.any(axis=1)); cols = np.flatnonzero(solid.any(axis=0))
                heights.append(int(rows.max() - rows.min() + 1)); tops.append(int(rows.min()))
                if chunk == 13:                                                                   # the 0
                    middle = solid[(rows.min() + rows.max()) // 2, cols.min():cols.max() + 1]
                    opening = int((~middle).sum())
                    self.assertGreaterEqual(opening / len(middle), 0.25, selector)               # it was 0.11
                    self.assertGreaterEqual(len(middle) / heights[-1], 0.49, selector)           # 0.50 at full height = 0.524 on the body, real 0.528
            self.assertLessEqual(max(heights) - min(heights), 1, (selector, heights))
            self.assertLessEqual(max(tops) - min(tops), 1, (selector, tops))

    def test_one_shape_set_serves_the_bengals_home_and_road(self):
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for chunk in range(13, 23):
            home = png_rgba(folder / by[("06H0", chunk)])[0][..., 3] > 127
            road = png_rgba(folder / by[("06A0", chunk)])[0][..., 3] > 127
            self.assertLessEqual(int((home ^ road).sum()), 4, chunk)

    def test_the_buccaneers_numbers_wear_an_unbroken_orange_inline(self):
        # Noah 11/19 (decision 1): "add the orange inline to the Bucs road numbers and their home, if their home numbers
        # have that too" (the Week 5 home photographs show it). The fill never touches the black edge or the clear
        # ground: an orange texel always lies between them, on every digit, jersey and arm.
        from scipy import ndimage
        folder = gf.art_folder(gf.digits_b81())
        for row in all_digit_rows():
            if row["selector"] not in ("27A0", "27H0"):
                continue
            rgba = picture(row)
            if rgba is None:
                continue
            opaque = rgba[..., 3] == 255
            colours, counts = np.unique(rgba[opaque][:, :3], axis=0, return_counts=True)
            fill = opaque & (rgba[..., :3] == colours[counts.argmax()]).all(-1)
            edge = ~opaque | (opaque & (rgba[..., :3].max(-1) < 0x60))
            self.assertFalse((ndimage.binary_dilation(fill, np.ones((3, 3), bool)) & edge).any(), (row["selector"], row["chunk"]))
            orange = opaque & (rgba[..., :3] == TB_ORANGE).all(-1)
            self.assertGreater(int(orange.sum()), 100, (row["selector"], row["chunk"]))

    def test_the_patriots_numbers_stand_rows_1_to_62(self):
        # Noah 11/19 (decision 2): "switch to the full height" (the game drew solid rows 2 to 61)
        folder = gf.art_folder(gf.digits_b81())
        for row in digit_rows():
            if row["selector"] in ("16H0", "16A0"):
                rows = np.flatnonzero((png_rgba(folder / row["png"])[0][..., 3] > 127).any(axis=1))
                self.assertEqual((int(rows.min()), int(rows.max())), (1, 62), row["png"])

    def test_the_browns_road_numbers_are_the_released_font_in_charcoal(self):
        # Noah 11/19 (decision 3) had the road numbers redrawn in charcoal; Noah 11/21 took the v0.9 font back; Noah 11/23:
        # "use charcoal browns numbers but old font". So the 30A0 jersey and shoulder digits are the glyphs the build holds
        # (the released v0.9 font) with one colour swap to the charcoal of the road name letters (RECOLOURED_NAMES), and
        # nothing else: no picture ships, no texel and no shape operation
        rows = [r for r in all_digit_rows() if r["selector"] == "30A0"]
        self.assertEqual(sorted(r["texture"] for r in rows), sorted([str(n) for n in range(48, 58)] + [f"an{n}" for n in range(48, 58)]))
        charcoal = "#%02X%02X%02X" % CLE_CHARCOAL
        for row in rows:
            self.assertEqual(row["kind"], "digit_derived", row["texture"])
            self.assertEqual([op["op"] for op in row["derive"]], ["recolour"], row["texture"])
            self.assertTrue(all(new.upper() == charcoal for _old, new in row["derive"][0]["pairs"]), row["texture"])

    def test_the_ravens_4_has_the_tall_closed_counter(self):
        if not DISC.is_file():                 # hosted runners: the derived picture needs the released disc
            self.skipTest("the released SOFTDRINK v0.9 disc is not on this machine")
        # R2: the 2026 Ravens 4 has a tall closed triangular counter, 0.27 and 0.30 of the height on the two photographs;
        # the released and batch 6 4 had a slit about 3 rows tall (an opening of 11 rows in the fill)
        # R2-G (retail-free): the 4 ships as the lane's remap on the glyph the build holds plus a paint of the texels
        # round 2 drew (digit_derived), so the picture is the derived one (the released disc must be on this machine)
        from scipy import ndimage
        seen = 0
        for row in all_digit_rows():
            if row["selector"] not in RAVENS or row["chunk"] not in (17, 37):
                continue
            rgba = picture(row)
            self.assertIsNotNone(rgba, "the released v0.9 disc is needed to derive the Ravens 4")
            seen += 1
            name = row.get("png", (row["selector"], row["chunk"]))
            opaque = rgba[..., 3] == 255
            colours, counts = np.unique(rgba[opaque][:, :3], axis=0, return_counts=True)
            fill = opaque & (rgba[..., :3] == colours[counts.argmax()]).all(-1)
            holes, count = ndimage.label(ndimage.binary_fill_holes(fill) & ~fill)
            self.assertGreaterEqual(count, 1, name)
            rows = np.flatnonzero((holes == np.bincount(holes.ravel())[1:].argmax() + 1).any(axis=1))
            self.assertTrue(16 <= len(rows) <= 19, (name, len(rows)))           # 0.26 to 0.31 of 62 rows
            cols = np.flatnonzero((rgba[..., 3] > 127).any(axis=0))
            self.assertEqual(len(cols), 31, name)
        self.assertEqual(seen, 12)                                # six sets, jersey and arm

    def test_the_jets_2_has_one_straight_diagonal(self):
        # R2: the 2026 Jets 2 (three photographs) is the block 2 with one diagonal from the right stem to the bottom left;
        # the squared S-shaped 2 had a middle bar, a left stem and a stub on the right above the bottom bar
        folder = gf.art_folder(gf.digits_b81())
        seen = 0
        for row in digit_rows():
            if not row["selector"].startswith("19") or row["selector"] in ("19A6", "19H6") or row["chunk"] not in (15, 35):
                continue
            seen += 1
            ink = png_rgba(folder / row["png"])[0][..., 3] > 127
            rows = np.flatnonzero(ink.any(axis=1)); cols = np.flatnonzero(ink.any(axis=0))
            top, height, left, width = rows.min(), rows.max() - rows.min() + 1, cols.min(), cols.max() - cols.min() + 1
            lefts = [np.flatnonzero(ink[y]).min() for y in range(top + int(0.42 * height), top + int(0.74 * height))]
            self.assertTrue(all(b <= a for a, b in zip(lefts, lefts[1:])), row["png"])   # moves only left, row by row
            self.assertGreaterEqual(lefts[0] - lefts[-1], 0.4 * width, row["png"])
            stub = ink[top + int(0.66 * height):top + int(0.76 * height), left + int(0.75 * width):]
            self.assertFalse(stub.any(), row["png"])
        self.assertEqual(seen, 12)                                # six sets, jersey and arm

    def test_the_broncos_wear_one_face_with_a_thin_edge(self):
        # R2: home, road and alternates wear the same numerals (photographs of the orange, white and navy jerseys); the
        # edge is about 1.3 texels on the photographs: one solid texel and a soft one
        from scipy import ndimage
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for chunk in range(13, 23):
            masks = {s: png_rgba(folder / by[(s, chunk)])[0][..., 3] > 127 for s in BRONCOS_ONE_FACE}
            for selector, mask in masks.items():
                self.assertEqual(int((mask ^ masks[BRONCOS_ONE_FACE[0]]).sum()), 0, (selector, chunk))
            for selector in BRONCOS_ONE_FACE:
                rgba, _info = png_rgba(folder / by[(selector, chunk)])
                opaque = rgba[..., 3] == 255
                colours, counts = np.unique(rgba[opaque][:, :3], axis=0, return_counts=True)
                fill = opaque & (rgba[..., :3] == colours[counts.argmax()]).all(-1)
                ring = opaque & ~fill                             # the solid edge: one texel, touching the fill
                self.assertFalse((ring & ~ndimage.binary_dilation(fill, np.ones((3, 3), bool))).any(), (selector, chunk))
                self.assertLess(int(ring.sum()), 0.33 * int(fill.sum()), (selector, chunk))
                rows = np.flatnonzero((rgba[..., 3] > 127).any(axis=1))
                self.assertEqual((int(rows.min()), int(rows.max())), (1, 62), (selector, chunk))

    def test_the_raiders_road_edge_is_the_measured_silver(self):
        if not DISC.is_file():                 # hosted runners: the derived picture needs the released disc
            self.skipTest("the released SOFTDRINK v0.9 disc is not on this machine")
        # R2: #C8C7C7 could not be seen on the white jersey in the game; the real edge reads 0.41 of the jersey white
        # R2-G (retail-free): the set ships as the lane's edge + remap + recolour on the glyph the build holds
        rows = [r for r in all_digit_rows() if r["selector"] == "20A0"]
        self.assertEqual(len(rows), 20)
        for row in rows:
            rgba = picture(row)
            self.assertIsNotNone(rgba, "the released v0.9 disc is needed to derive the Raiders road digits")
            colours = {tuple(int(v) for v in c) for c in rgba[rgba[..., 3] > 0][:, :3]}
            self.assertEqual(colours, {(0, 0, 0), LV_ROAD_SILVER}, (row["selector"], row["chunk"]))

    def test_a_document_art_folder_must_be_a_plain_glyph_folder_name(self):
        self.assertEqual(gf.art_folder({}), gf.ART)
        for bad in ("../x", "nfl2k5_glyph_fixes_2026_b81u/..", "other", "a/nfl2k5_glyph_fixes_2026"):
            with self.assertRaises(ValueError):
                gf.art_folder({"art": bad})


class AuthoringHelpers(unittest.TestCase):
    def test_chunk_of_names_every_pass_texture(self):
        self.assertEqual(up.chunk_of("jersey00"), (1, "tset"))
        self.assertEqual(up.chunk_of("pants00"), (2, "tset"))
        self.assertEqual(up.chunk_of("sleeve00"), (3, "tset"))
        self.assertEqual(up.chunk_of("socks00"), (4, "tset"))
        self.assertEqual(up.chunk_of("48"), (13, "txtr"))
        self.assertEqual(up.chunk_of("57"), (22, "txtr"))
        self.assertEqual(up.chunk_of("hn48"), (23, "txtr"))
        self.assertEqual(up.chunk_of("an57"), (42, "txtr"))
        for bad in ("helmet02", "58", "an47", "names"):
            with self.assertRaises(ValueError):
                up.chunk_of(bad)

    def test_digit_chunk(self):
        self.assertEqual(up.digit_chunk("digit_jersey_0"), (13, "48"))
        self.assertEqual(up.digit_chunk("digit_jersey_9"), (22, "57"))
        self.assertEqual(up.digit_chunk("digit_helmet_3"), (26, "hn51"))
        self.assertEqual(up.digit_chunk("digit_arm_7"), (40, "an55"))

    def test_runs_of_lists_each_changed_run_once_and_paints_back(self):
        before = np.zeros((6, 10, 4), np.uint8)
        before[..., 3] = 255
        after = before.copy()
        after[1, 2:5, :3] = (9, 8, 7)
        after[1, 7, :3] = (1, 1, 1)
        after[4, 0, :3] = (5, 5, 5)
        got = up.runs_of(before, after)
        self.assertEqual(got, [[1, 2, "090807090807090807"], [1, 7, "010101"], [4, 0, "050505"]])
        painted, scope = kf.paint(before, [dict(op="runs", rows=got)])
        self.assertTrue((painted == after).all())
        self.assertEqual(int(scope.sum()), 5)


class BuildHook(unittest.TestCase):
    def test_both_passes_are_optional_labelled_steps_after_the_helmet_cleanup(self):
        for step in ("kit_fixes_2026_b81u", "glyph_fixes_2026_b81u"):
            self.assertIn(step, mod_build.OPTIONAL_STEPS)
            self.assertIn(step, build_steps.STEP_LABELS)
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        helmets = source.index("apply_helmets_b81(target, ")
        kits = source.index("apply_uniforms_b81(target)")
        digits = source.index("apply_digits_b81(target)")
        self.assertLess(helmets, kits)
        self.assertLess(kits, digits)
        for earlier in ("kit_fixes.apply_sideline(target)", "moment_kits.apply_to_image(target",
                        "classic.apply_to_image(target, retail)", "nameplate_fixes.apply_to_image("):
            self.assertLess(source.index(earlier), kits, earlier)

    def test_the_documents_and_the_art_are_shipped(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_kit_fixes_2026_b81u.json", allow)
        self.assertIn("data/nfl2k5_glyph_fixes_2026_b81u.json", allow)
        for path in sorted((ROOT / "data" / up.DIGIT_ART).glob("*.png")):
            self.assertIn(f"data/{up.DIGIT_ART}/{path.name}", allow)
        self.assertEqual(kf.DATA_B81U, ROOT / "data/nfl2k5_kit_fixes_2026_b81u.json")
        self.assertEqual(gf.DATA_B81U, ROOT / "data/nfl2k5_glyph_fixes_2026_b81u.json")

    def test_the_shipped_documents_pass_the_release_gate_text_checks(self):
        # Beta 81 CI: the retail-free release gate refused the digit document, whose references named photographs by
        # their absolute download path, and then the compact kit documents, whose whitespace-free runs read as
        # embedded binary blobs. Every shipped b81 document goes through the gate's own text check here, and the
        # generator's writer refuses both faults.
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_2k5_mod_studio_release",
                                                      ROOT / "packaging/check_2k5_mod_studio_release.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        allow = set((ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines())
        documents = sorted(f"data/{path.name}" for path in (ROOT / "data").glob("*_b81*.json"))
        self.assertTrue({"data/nfl2k5_kit_fixes_2026_b81.json", "data/nfl2k5_kit_fixes_2026_b81u.json",
                         "data/nfl2k5_glyph_fixes_2026_b81u.json"} <= set(documents) & allow)
        for relative in documents:
            with self.subTest(document=relative):
                path = ROOT / relative
                limit = gate.REVIEWED_METADATA.get(relative, (gate.MAX_RELEASE_FILE_BYTES,))[0]
                gate._hash_and_validate_text(path, relative, path.stat().st_size, limit)
        private = gate.FORBIDDEN_PRIVATE_TEXT_FRAGMENTS[1] + "/Storage/project/photo.jpg"
        with self.assertRaisesRegex(ValueError, "private host path"):
            up.shipped_json({"references": {"CHI": [private]}}, indent=1, sort_keys=True)
        runs = {"textures": [{"runs": [[row, 0, "09" * 1500] for row in range(3)]}]}
        with self.assertRaisesRegex(ValueError, "4,096"):
            up.shipped_json(runs, separators=(",", ":"), sort_keys=True)
        self.assertEqual(up.shipped_json(runs, sort_keys=True), json.dumps(runs, sort_keys=True) + "\n")
        document = {"references": {"CHI": ["dl/batch5/photo.jpg"]}}
        self.assertEqual(up.shipped_json(document, indent=1, sort_keys=True),
                         json.dumps(document, indent=1, sort_keys=True) + "\n")


class _FakeEntry:
    def __init__(self, name_id):
        self.name_id = name_id
        self.size = 0


class NameplatePassGuard(unittest.TestCase):
    """The b778-uf2 pass (the Jaguars name plates Noah asked for on 10/22, and the hyphen fill) compared its rows'
    selectors with package FILE names, so a Studio build (not strict) always returned ``other_uniform`` and wrote
    nothing. With every Jaguars package present the pass must go on to plan its kits."""

    def _run(self, names):
        ids = {name: number for number, name in enumerate(sorted(names), 1)}
        back = {number: name for name, number in ids.items()}

        class Image:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        index = mock.Mock(entries=[_FakeEntry(i) for i in back])
        planned = []

        def compile_package(selector, raw, document, retail_kits, strict):
            planned.append(selector)
            return [], dict(selector=selector, state="applied", structure="applied", hyphen="none")

        with mock.patch.object(nf.bump._Image, "open", return_value=Image()), \
                mock.patch.object(nf.bump, "_parsed_index", return_value=index), \
                mock.patch.object(nf.bump, "logical_name_for", side_effect=lambda i: back[i]), \
                mock.patch.object(nf, "_compile_package", side_effect=compile_package), \
                mock.patch.object(Image, "read_segments", create=True, return_value=b""), \
                mock.patch.object(index, "sub_extents", return_value=[]):
            try:
                receipt = nf.apply_to_image("disc.iso")
            except Exception:  # noqa: BLE001 - the fake image carries no kit bytes; only the guard is under test
                receipt = dict(state="went on")
        return receipt, planned

    def test_a_build_with_every_jaguars_package_is_not_turned_away(self):
        wanted = sorted(r["selector"] for r in nf.structures(nf.spec()))
        self.assertEqual(wanted, ["12A0", "12A6", "12H0", "12H6"])
        receipt, planned = self._run([s + ".IFF" for s in wanted] + ["26H0.IFF"])
        self.assertNotEqual(receipt.get("state"), "other_uniform")

    def test_a_disc_without_those_packages_is_still_left_alone(self):
        receipt, planned = self._run(["26H0.IFF", "12H0.IFF"])
        self.assertEqual(receipt.get("state"), "other_uniform")
        self.assertEqual(planned, [])

    def test_the_guard_reads_selectors_not_file_names(self):
        source = (ROOT / "mod_editor/core/nfl2k5_nameplate_fixes_2026.py").read_text(encoding="utf-8")
        self.assertIn("not wanted <= set(selectors)", source)
        self.assertNotIn('not wanted <= {s + ".IFF" for s in selectors}', source)


@unittest.skipUnless(DISC.is_file(), "the released SOFTDRINK v0.9 disc is not on this machine")
class RealDisc(unittest.TestCase):
    """Offline real-disc proof: every row against the kit packages of the released build (read only)."""

    @classmethod
    def setUpClass(cls):
        selectors = sorted({r["selector"] for r in kit_rows()} | {r["selector"] for r in digit_rows()}
                           | {r["selector"] for r in nf.structures(nf.spec())})
        selectors = sorted(set(selectors) | set(kf.donor_kits(kf.uniforms_b81())))
        cls.kits = up.read_kits(DISC, selectors)

    def after(self, selector, texture):
        row = [r for r in kit_rows() if (r["selector"], r["texture"]) == (selector, texture)][0]
        raw = self.kits[selector]
        chunk = kf._chunk_for(raw, row["chunk"])
        donors = {}
        for key in (row.get("donors") or {}):           # b81-retail-free-art: rules that read another kit's texture
            other, _, at = str(key).rpartition(":")
            source = self.kits[other] if other else raw
            d = kf._chunk_for(source, int(at))
            donors[str(key) if other else int(at)] = kf.texture_rgba(source[d.offset:d.end_offset])
        new, _detail = kf.compile_texture(raw[chunk.offset:chunk.end_offset], row, donors)
        return up.level0(new, "tset")[0]

    def painted(self, selector, texture):
        """{(x, y): (r, g, b)} of every texel the finished texture changes against the released one."""
        row = [r for r in kit_rows() if (r["selector"], r["texture"]) == (selector, texture)][0]
        raw = self.kits[selector]
        chunk = kf._chunk_for(raw, row["chunk"])
        before = up.level0(raw[chunk.offset:chunk.end_offset], "tset")[0]
        after = self.after(selector, texture)
        ys, xs = np.nonzero((after[..., :3] != before[..., :3]).any(-1))
        return {(int(x), int(y)): tuple(int(v) for v in after[y, x, :3]) for y, x in zip(ys, xs)}

    def test_the_batch_4_whole_jersey_rows(self):
        # KITS4 (measured on 2026 game frames, approved from its review sheet): the Lions Defend the Den jersey and
        # pants are a pale blue-grey, not near-white (DET 2026-11-01 MIN frames: target #B6C1DB, shading kept by
        # scaling, so the median texel is the target); the Seahawks 26H4 navy home jersey wears the lime shoulder
        # panels, grey bars and lime collar chevrons of the same jersey's 26H0 art, which lie above the number only.
        for selector in ("09H9", "09A9"):
            for texture, size in (("jersey00", 512 * 256), ("pants00", None)):
                painted = self.painted(selector, texture)
                if size:
                    # the whole torso, front and back; a texel the new chest DETROIT (Noah 11/19, decision 6) paints in
                    # the colour the released texture already had there is unchanged: those lie inside the word's box
                    # (b81-retail-free-art: the recolour is a build-time rule now, so this reads the finished texture)
                    missing = {(x, y) for x in range(512) for y in range(256)} - set(painted)
                    self.assertLessEqual(len(missing), 8, (selector, texture))
                    self.assertTrue(all(132 <= x <= 190 and 93 <= y <= 105 for x, y in missing), (selector, missing))
                median = np.median(np.array(list(painted.values())), axis=0)
                # advisor 11/24 (the alternates round): one neutral grey, not the lavender blue #B6C1DB
                self.assertTrue(near(tuple(median), DET_DTD_GREY[texture], 3), (selector, texture, median))
        # 26H4: since the advisor's alternates round (11/24) the whole approved 26H0 jersey (art_v4), see
        # test_the_seahawks_26h4_wears_the_26h0_shoulder_art

    def runs_down(self, column):
        """[(first row, colour, rows)] down one texel column"""
        out = []
        for y, colour in enumerate(tuple(int(v) for v in c[:3]) for c in column):
            if out and out[-1][1] == colour:
                out[-1][2] += 1
            else:
                out.append([y, colour, 1])
        return out

    def test_bills_sleeves_are_two_bars_edged_red_with_a_gap(self):
        red, blue, white = (200, 16, 46), (11, 58, 158), (255, 255, 255)
        for selector, base, bar in (("03H0", blue, white), ("03A0", white, blue)):
            sleeve = self.after(selector, "sleeve00")
            for top in (0, 64):                                   # the two sleeve islands, 64 rows each
                solid = [(c, n) for _y, c, n in self.runs_down(sleeve[top:top + 64, 64]) if n >= 2]
                self.assertEqual([c for c, _n in solid], [base, red, bar, red, base, red, bar, red, base], (selector, top))
                widths = [n for _c, n in solid]
                self.assertTrue(all(2 <= widths[i] <= 3 for i in (1, 3, 5, 7)), widths)      # thin red edges
                self.assertTrue(all(7 <= widths[i] <= 9 for i in (2, 6)), widths)            # the two bars
                self.assertTrue(6 <= widths[4] <= 8, widths)                                 # the gap between them
            for top in (0, 64):                                   # the stack is plain rings round the arm
                stack = sleeve[top + 20:top + 53, :, :3]
                self.assertTrue((stack == stack[:, :1]).all(), selector)

    def test_vikings_home_pants_get_a_broad_purple_band_gold_in_front_and_a_white_lower_leg(self):
        # b81m (approved 11/24, staged by the lane): from the back of the leg forward a wide purple band, a gold band and
        # a narrow purple band (real 4.2 / 1.35 / 1.2 cm; the game had gold in front of one purple band)
        purple, gold, white = (79, 38, 131), (255, 198, 47), (255, 255, 255)
        pants = self.after("15H0", "pants00")
        for y in (40, 100, 160):
            for columns, front_first in ((range(100, 185), True), (range(327, 412), False)):   # left leg, right leg
                row = [tuple(int(v) for v in pants[y, x, :3]) for x in columns]
                band = [i for i, c in enumerate(row) if c == purple]
                line = [i for i, c in enumerate(row) if c == gold]
                self.assertGreaterEqual(len(band), 18, y)                                    # it was 4 texels
                self.assertTrue(4 <= len(line) <= 7, (y, len(line)))
                front = [i for i in band if (i < min(line)) == front_first]
                back = [i for i in band if i not in front]
                self.assertTrue(front and back, y)                                           # purple on both sides of the gold
                self.assertGreater(len(back), 2 * len(front), y)                             # the wide band behind
        self.assertTrue((pants[232:, :, :3] == 255).all())                                   # white below the hem
        socks = self.after("15H0", "socks00")
        self.assertTrue((socks[..., :3] == 255).all())

    def test_vikings_road_and_rams_road_pants_stripes(self):
        white, gold, sol, royal = (255, 255, 255), (255, 198, 47), (255, 209, 0), (0, 53, 148)
        vikings, rams = self.after("15A0", "pants00"), self.after("23A0", "pants00")
        for y in (40, 100, 160):
            row = [tuple(int(v) for v in vikings[y, x, :3]) for x in range(100, 185)]
            band = [i for i, c in enumerate(row) if c == white]
            line = [i for i, c in enumerate(row) if c == gold]
            self.assertGreaterEqual(len(band), 11, y)                                        # it was 2 texels
            self.assertTrue(3 <= len(line) <= 7, (y, len(line)))
            self.assertLess(max(line), min(band), y)
            row = [tuple(int(v) for v in rams[y, x, :3]) for x in range(100, 185)]
            band = [i for i, c in enumerate(row) if c == sol]
            line = [i for i, c in enumerate(row) if c == white]
            self.assertGreaterEqual(len(band), 8, y)                                         # the sol band it lacked
            self.assertGreaterEqual(len(line), 5, y)
            self.assertLess(max(line), min(band), y)                                         # white toward the front
            rest = {c for c in row} - {white, sol}
            self.assertTrue(rest and all(near(c, royal, 4) for c in rest), (y, rest))        # hard edges: no blends

    def marks(self, selector, base, rows, columns=(140, 186)):
        """box (x0, y0, x1, y1 inclusive) of the texels in a band of chest rows that are not the jersey colour"""
        torso = self.after(selector, "jersey00")[..., :3].astype(int)
        band = np.abs(torso[rows[0]:rows[1], columns[0]:columns[1]] - np.array(base)).max(-1) > 30
        ys, xs = np.nonzero(band)
        return (int(xs.min()) + columns[0], int(ys.min()) + rows[0], int(xs.max()) + columns[0], int(ys.max()) + rows[0])

    def test_the_collar_shield_is_twelve_by_sixteen_and_hangs_from_the_collar_point(self):
        # sharp 2026 game photographs, 16 players: the shield is 0.141 of the number height wide, 1.2 tall to wide. The
        # number glyph is 22.2 cm tall on the player, a texel 0.275 by 0.25 cm: 12 by 16 texels (it was 8 by 10).
        for selector, base, top in (("18H0", (14, 40, 120), 71), ("24A0", (255, 255, 255), 71), ("18H7", (255, 255, 255), 75)):
            self.assertEqual(self.marks(selector, base, (top, top + 17), (150, 172)), (155, top, 166, top + 15), selector)

    def test_the_giants_chest_mark_is_as_wide_as_the_collar_shield_and_sits_over_the_number(self):
        # real 2026 pictures: the "ny" under the shield is 0.87 to 1.12 of the shield's width (the game had 18 texels
        # beside an 8 texel shield) and sits close above the number, whose top is at row 108.
        for selector, base, top in (("18H0", (14, 40, 120), 93), ("18A0", (255, 255, 255), 93), ("18H7", (255, 255, 255), 95),
                                    ("18A7", (255, 255, 255), 95)):
            self.assertEqual(self.marks(selector, base, (top - 2, 108)), (155, top, 166, top + 9), selector)
            torso = self.after(selector, "jersey00")[..., :3].astype(int)
            bar = np.abs(torso[top + 9, 155:167] - np.array(base)).max(-1) > 30
            self.assertGreater(int(bar.sum()), 8, selector)                         # the underline bar is one solid row

    def test_the_seahawks_26h4_wears_the_26h0_shoulder_art(self):
        # KITS4: 26H4 is the same navy home jersey as 26H0 (worn with wolf-grey pants); its torso and sleeves now carry
        # 26H0's art (the lime shoulder panels it lacked: up to 244 levels away before). Each texture keeps its own
        # palette, so a colour lands within a few levels of 26H0's: the KITS4 colour acceptance is 12 levels.
        # Advisor 11/24 (alternates round): the approved 26H0 jersey (art_v4: torso and sleeves) in this slot
        torso = np.abs(self.after("26H4", "jersey00").astype(int) - self.after("26H0", "jersey00").astype(int)).max(-1)
        self.assertLessEqual(int(torso.max()), 12)
        home = self.after("26H0", "sleeve00")
        self.assertLessEqual(int(np.abs(self.after("26H4", "sleeve00").astype(int) - home.astype(int)).max()), 12)
        road = np.abs(self.after("26A4", "jersey00").astype(int) - self.after("26A0", "jersey00").astype(int)).max(-1)
        self.assertLessEqual(int(road.max()), 12)
        raw = self.kits["26H4"]
        chunk = kf._chunk_for(raw, up.chunk_of("jersey00")[0])
        before = up.level0(raw[chunk.offset:chunk.end_offset], "tset")[0]
        self.assertGreater(int(np.abs(before.astype(int) - self.after("26H0", "jersey00").astype(int)).max()), 100)

    def test_the_buccaneers_pants_stripe_is_black_orange_red_orange_black(self):
        # Noah 11/19 (decision 5, "use the prototype"): black 5, orange 2, red 9, orange 2, black 5 texels (about 5.8 cm),
        # on the white home pants and the pewter road pants, both legs, waist to the cuff
        black, orange, red = (14, 14, 14), (220, 68, 5), (178, 28, 53)
        for selector in ("27H0", "27A0"):
            pants = self.after(selector, "pants00")
            for y in (5, 60, 120, 180, 205):
                for x0 in (131, 358):
                    runs = [(c, n) for _y, c, n in self.runs_down(pants[y, x0:x0 + 23])]
                    self.assertEqual([n for _c, n in runs], [5, 2, 9, 2, 5], (selector, y, x0))
                    for (c, _n), want in zip(runs, (black, orange, red, orange, black)):
                        self.assertTrue(near(c, want, 6), (selector, y, x0, c))
                    for x in (x0 - 1, x0 + 23):                              # the pants base on both sides
                        self.assertFalse(near(tuple(int(v) for v in pants[y, x, :3]), black, 30), (selector, y, x))

    def test_the_lions_defend_the_den_detroit_is_italic_at_its_real_size(self):
        # Noah 11/19 (decision 6): "I like try one best for Detroit ... because try two isn't italicized": italic, at the
        # real size (59 by 13 texels, 0.74 of the number height), in the kit blue, bottom row kept, clear of the collar
        for selector in ("09H9", "09A9"):
            torso = self.after(selector, "jersey00")[..., :3].astype(int)
            ink = np.abs(torso - np.array((0x00, 0x76, 0xB6))).max(-1) <= 12
            band = ink[86:112, 100:216]
            ys, xs = np.nonzero(band)
            self.assertEqual((int(xs.min()) + 100, int(ys.min()) + 86, int(xs.max()) + 100, int(ys.max()) + 86),
                             (132, 93, 189, 105), selector)                 # full-colour texels; edge blends to 190
            left = {y: int(np.flatnonzero(ink[y, 120:200]).min()) for y in (93, 105)}
            self.assertGreaterEqual(left[93] - left[105], 2, selector)              # the top leans right
            self.assertFalse(ink[78:92, 150:176].any(), selector)                   # nothing new at the collar shield

    def test_the_bengals_pants_wear_seven_tiger_strokes_from_one_column(self):
        # R2 (order R2-C): the club's one pants pattern, read off the 2026 White Bengal photographs: seven strokes from
        # the waist to the knee, each thick on one column at the front side seam (111 on the left leg, 400 on the right),
        # sweeping back and up to a point, the third and fifth forked; the same geometry on all six Bengals pants in each
        # one's own stroke colour (before: seven blunt bars on 06H5, thin dashes on 06H0/06A0, nine claws on the rest)
        from scipy import ndimage
        colours = {"06H0": ((0, 0, 0), (0xFB, 0x4F, 0x14)), "06A0": ((255, 255, 255), (0, 0, 0)),
                   "06H5": ((255, 255, 255), (0x0B, 0x0B, 0x0B)), "06A5": ((255, 255, 255), (0x0F, 0x0F, 0x0F)),
                   "06H6": ((255, 255, 255), (0xFA, 0x50, 0x14)), "06A6": ((255, 255, 255), (0xFA, 0x50, 0x14))}
        shapes = {}
        for selector, (base, stroke) in colours.items():
            pants = self.after(selector, "pants00")[..., :3].astype(float)
            b, s = np.array(base, float), np.array(stroke, float)
            steps = np.round(np.clip(((pants - b) @ (s - b)) / ((s - b) @ (s - b)), 0, 1)[:200] * 4)   # blend steps 0-4
            ink = steps >= 2
            for x0, x1, seam in ((108, 200, 111), (312, 404, 400)):
                lab, n = ndimage.label(ink[:, x0:x1], structure=np.ones((3, 3)))
                strokes = [q for q in (np.argwhere(lab == i) for i in range(1, n + 1)) if len(q) >= 10]
                self.assertEqual(len(strokes), 7, (selector, seam))
                forks = 0
                for q in strokes:
                    cols = q[:, 1] + x0
                    self.assertEqual(int(cols.min() if seam == 111 else cols.max()), seam, selector)   # thick end on the seam
                    tip = cols.max() if seam == 111 else cols.min()
                    self.assertLessEqual(int((cols == tip).sum()), 2, selector)                      # a point of 1 or 2 texels
                    self.assertGreaterEqual(abs(int(tip) - seam), 30, selector)
                    split = sum(1 for c in np.unique(cols) if (np.diff(np.sort(q[cols == c, 0])) > 1).any())
                    forks += split >= 2
                self.assertEqual(forks, 2, (selector, seam))
            shapes[selector] = steps
        for selector in colours:
            self.assertTrue(np.array_equal(shapes[selector][:, 108:404], shapes["06H5"][:, 108:404]), selector)   # one geometry

    def test_the_lions_defend_the_den_pants_wear_the_black_band_and_blue_wedge(self):
        # R2 (order R2-C): the 2026 Defend the Den pants carry one black band on the side seam that starts as a slanted
        # point below the hip and widens slowly to the hem, and a kit blue wedge on its front side from a point about
        # two thirds down (picture DET 2026-11-01 4-5: black 0.076 of the thigh depth at mid-thigh, black : blue at the
        # knee 28 : 17). Flat colours, no piping; the base colour is not touched. The game had no stripe.
        black, blue, base = (0x18, 0x19, 0x1B), (0x00, 0x76, 0xB6), DET_DTD_GREY["pants00"]   # the base: advisor 11/24
        def cols(pants, y, colour):
            return [x for x in range(100, 412) if near(tuple(int(v) for v in pants[y, x, :3]), colour, 6)]
        for selector in ("09H9", "09A9"):
            pants = self.after(selector, "pants00")
            for y in range(30, 59):
                self.assertEqual(cols(pants, y, black), [], (selector, y))                     # nothing above the start
            self.assertEqual(cols(pants, 60, black), [144, 367], selector)                     # the point, both legs
            self.assertEqual(cols(pants, 61, black), [143, 144, 367, 368], selector)
            self.assertEqual(cols(pants, 120, black), [*range(138, 145), *range(367, 374)], selector)   # 7 texels, 1.7 cm
            self.assertEqual(cols(pants, 120, blue), [], selector)
            self.assertEqual(cols(pants, 190, black), [*range(136, 145), *range(367, 376)], selector)   # 9 full + a blend
            self.assertEqual(cols(pants, 190, blue), [*range(129, 135), *range(377, 383)], selector)    # 6 texels, 1.4 cm
            for y in range(100, 156):
                self.assertEqual(cols(pants, y, blue), [], (selector, y))                      # the wedge starts lower
            for x in (126, 145, 366, 385):                                                       # the base on both sides
                self.assertTrue(near(tuple(int(v) for v in pants[190 if x in (126, 385) else 120, x, :3]), base, 12), (selector, x))
            # advisor 11/24 (Noah's "fix every bug" rule): dark socks as in the photographs, the sock top below the hem too
            socks = self.after(selector, "socks00")
            self.assertTrue((np.abs(socks[..., :3].astype(int) - np.array((0x18, 0x19, 0x1B))).max(-1) <= 2).all(), selector)
            self.assertTrue((np.abs(pants[240:, :, :3].astype(int) - 0x19).max(-1) <= 2).all(), selector)

    def test_the_commanders_road_shoulder_swoosh_is_one_solid_mark(self):
        # R2 (order R2-C, art director's ruling): the game draws the road shoulder swoosh across the torso texture's
        # front/back seam: a hook of 13 or 14 solid texels on the front panel and a faint sliver of a tail on the back
        # (6 and 9 solid texels), white notches at the seam. Redrawn on the player model as one solid kit-burgundy swoosh,
        # hook to the front, tail to the back, 5.5 cm tip to tip (5.61 and 5.54 cm): the tail is solid down the back panel.
        burgundy = np.array((0x5E, 0x15, 0x19))
        torso = self.after("29A0", "jersey00")[..., :3].astype(int)
        solid = np.abs(torso - burgundy).max(-1) <= 6
        counts, spans = [], []
        for x0, y0, x1, y1 in WAS_ROAD_SWOOSH:
            box = solid[y0:y1, x0:x1]
            rows = np.flatnonzero(box.any(axis=1)) + y0
            counts.append(int(box.sum()))
            spans.append((int(rows.min()), int(rows.max()), bool((np.diff(rows) == 1).all())))
        self.assertEqual(counts, [23, 24, 30, 28])
        self.assertEqual(spans, [(12, 17, True), (12, 17, True), (17, 34, True), (17, 33, True)])
        for x0, y0, x1, y1 in WAS_ROAD_SWOOSH:
            self.assertFalse(solid[y1:y1 + 16, x0:x1].any())                     # nothing below the swoosh boxes

    def test_the_saints_sleeve_fleur_stands_taller_than_wide(self):
        # R2 (order R2-C): the game's sleeve fleur was squat (29 to 33 texels wide, 7.6 to 8.6 cm on the body against
        # 5.8 to 6.2 cm tall: w/h 1.23 to 1.50; the 2026 pictures read 0.78 and 0.86, the club emblem 0.83). Redrawn from
        # the repo's emblem at the old height and centre: 18 to 20 texels wide, w/h 0.84 to 0.86 on the body (the sleeve
        # texel is 0.26 cm across and 0.21 cm down there).
        from scipy import ndimage
        want = {"17H0": [(51, 9, 20, 30), (58, 73, 19, 30)], "17A0": [(52, 9, 19, 28), (58, 73, 18, 28)]}
        want.update({"17H3": want["17H0"], "17A3": want["17H0"], "17H8": want["17A0"], "17A8": want["17A0"]})
        for selector, boxes in want.items():
            sleeve = self.after(selector, "sleeve00")[..., :3].astype(int)
            colours, counts = np.unique(sleeve.reshape(-1, 3), axis=0, return_counts=True)
            base = colours[counts.argmax()]
            ink = np.abs(sleeve - base).sum(-1) > 24
            found = []
            for rows in (slice(0, 64), slice(64, 128)):
                half = np.zeros(ink.shape, bool)
                half[rows] = ink[rows]
                lab, n = ndimage.label(half, structure=np.ones((3, 3)))
                for i in range(1, n + 1):
                    ys, xs = np.nonzero(lab == i)
                    if ys.max() - ys.min() >= 20 and xs.max() - xs.min() < 60:          # the fleur, not the swoosh or a stripe
                        found.append((int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)))
            self.assertEqual(found, boxes, selector)

    def test_the_bengals_strokes_are_blades_that_hold_their_thickness(self):
        # R2 (order R2-C, second pass, art director): the real strokes are blades that keep nearly their full thickness
        # for most of their length and taper over the last third (2026 White Bengal pictures 3 and 5: thickness at half
        # length 0.83 of the seam end, band about half ink). The first pass thinned at once (0.56 to 0.67 on four strokes).
        from scipy import ndimage
        pants = self.after("06H5", "pants00")[..., :3].astype(float)
        b, s = np.array((255.0, 255.0, 255.0)), np.array((11.0, 11.0, 11.0))
        ink = np.round(np.clip(((pants - b) @ (s - b)) / ((s - b) @ (s - b)), 0, 1)[:200] * 4) >= 2
        ratios = []
        for x0, x1, seam, step in ((108, 200, 111, 1), (312, 404, 400, -1)):
            lab, n = ndimage.label(ink[:, x0:x1], structure=np.ones((3, 3)))
            for q in (np.argwhere(lab == i) for i in range(1, n + 1)):
                if len(q) < 10:
                    continue
                cols = q[:, 1] + x0
                tip = cols.max() if step > 0 else cols.min()
                at_seam = int((cols == seam + step).sum())
                at_half = int((cols == int(round(seam + (tip - seam) / 2))).sum())
                ratios.append(at_half / at_seam)
        self.assertEqual(len(ratios), 14)
        self.assertGreaterEqual(min(ratios), 0.75, ratios)
        self.assertGreaterEqual(float(np.mean(ratios)), 0.85, ratios)

    def test_every_kit_row_is_waiting_on_the_released_disc_and_compiles_to_its_pin(self):
        result = up.states(DISC)
        # the helmet shell rows wait on the helmet the b81 cleanup leaves (HelmetRows): on the released disc those the
        # cleanup changes read "other"
        moved = [r for r in result["rows"] if r["state"] == "other"]
        self.assertTrue(all((r["texture"] in ("helmet00", "helmet02") and r["selector"] in HELMET_KITS)
                            or (r["selector"], up.chunk_of(r["texture"])[0]) in BUILD_INPUT_ROWS for r in moved), moved)
        self.assertEqual((result["before"] + result["other"], result["after"], result["absent"]),
                         (len(kit_rows()) + len(unif_rows()) + len(helmet_rows()), 0, 0), result["rows"])
        # the helmet shell rows compile on the helmet the build holds after the cleanup (HelmetRows); here the rest
        document = dict(kf.uniforms_b81())
        document["textures"] = [r for r in document["textures"] if r["kind"] != "txtr"
                                and (r["selector"], r["chunk"]) not in BUILD_INPUT_ROWS]
        for selector in sorted({r["selector"] for r in kit_rows()}):
            replacements, receipt = kf.compile_resource(selector, self.kits[selector], strict=True,
                                                        document=document, kits=self.kits)
            rows = [r for r in document["textures"] if r["selector"] == selector]   # texture and Unif rows
            self.assertEqual(len(replacements), len(rows), selector)
            for part in receipt["parts"]:
                if part.get("texture") is None:     # a Unif row: data fields, no palette (UnifDocument)
                    continue
                folded = selector == "23A0" and part.get("texture") == "pants00"   # the one full palette (first batch)
                self.assertEqual(part["merged_twin_slots"], 1 if folded else 0, (selector, part.get("texture")))
                if not folded:
                    self.assertEqual(part["protected_texels_moved_one_level"], 0, selector)
                else:                               # over all stored mips; seven of them on the top level
                    self.assertLessEqual(part["protected_texels_moved_one_level"], 30)

    def test_a_cleared_mark_ships_no_texel_and_the_runs_are_measured(self):
        """b81-retail-free-art (review rule, round 2 rows): an old mark is cleared by rule (``clear``), so no run texel
        takes the clear colour over a base mark; the runs' cover of the base's strong edges is measured against the
        generator's limit. The Bengals strokes and the Saints fleur are redrawn by code where the old mark was: they
        ship no erasure; whether a row may ship is its Ruling 2 class (the release check judges it)."""
        sys.path.insert(0, str(ROOT / "tools/b81_uniforms"))
        import kitfix_convert as tool
        converted = [r for r in kit_rows() if any(op["op"] in ("clear", "rule", "stamp") for op in r["ops"])]
        self.assertGreaterEqual(len(converted), 150)
        for row in converted:
            raw = self.kits[row["selector"]]
            chunk = kf._chunk_for(raw, row["chunk"])
            base = tool.level0(raw[chunk.offset:chunk.end_offset], row)
            donors = {}
            for key in (row.get("donors") or {}):
                other, _, at = str(key).rpartition(":")
                source = self.kits[other] if other else raw
                d = kf._chunk_for(source, int(at))
                donors[str(key) if other else int(at)] = kf.texture_rgba(source[d.offset:d.end_offset])
            final, _ = kf.paint(base, row["ops"], donors)
            if row["ops"][-1]["op"] != "runs":
                continue                                    # a row of rules only ships no texel
            before, _ = kf.paint(base, row["ops"][:-1], donors)
            shipped = np.zeros(base.shape[:2], bool)
            for y, x0, colours in row["ops"][-1]["rows"]:
                shipped[y, x0:x0 + len(colours) // 6] = True
            self.assertTrue((final[shipped] != before[shipped]).any(-1).all(), row["selector"])   # only what still differs
        # whether a converted row may ship is judged by its class (tools/b81_uniforms/texel_rows.py, the release check)

    def test_the_compiled_kit_textures_hold_exactly_the_authored_runs(self):
        for row in kit_rows():
            if (row["selector"], row["chunk"]) in BUILD_INPUT_ROWS:
                continue                                    # compiled on the build's own input: BuildInputRows
            raw = self.kits[row["selector"]]
            chunk = kf._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            before, _native = up.level0(span, "tset")
            donors = {}
            for key in (row.get("donors") or {}):           # rules that read another kit (stamp, the Saints emblem)
                other, _, at = str(key).rpartition(":")
                source = self.kits[other] if other else raw
                d = kf._chunk_for(source, int(at))
                donors[str(key) if other else int(at)] = kf.texture_rgba(source[d.offset:d.end_offset])
            new, _detail = kf.compile_texture(span, row, donors)
            self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"])
            after, _native = up.level0(new, "tset")
            # the art the row's operations make (runs, and on a converted row its clear) on the level 0 it was made on
            native, decoded, textures = kf.native_textures(span, "tset")
            palette = kf.read_palette(decoded, native, textures[0])
            art, scope = kf.paint(palette[kf.read_planes(decoded, native, textures[0])[0]].astype(np.uint8), row["ops"],
                                  donors)
            painted = {(int(x), int(y)): tuple(int(v) for v in art[y, x, :3]) for y, x in np.argwhere(scope)}
            changed = np.argwhere((after != before).any(axis=2))
            outside = 0
            for y, x in changed:
                if (int(x), int(y)) in painted:
                    self.assertEqual(tuple(int(v) for v in after[y, x, :3]), painted[(int(x), int(y))], (row["selector"], x, y))
                else:
                    outside += 1                    # a folded twin entry: one level at most
                    self.assertLessEqual(int(np.abs(after[y, x].astype(int) - before[y, x]).max()), 1)
            self.assertEqual(outside, row.get("texels_moved_one_level", 0), row["selector"])
            self.assertEqual(len(changed), row["texels"])
            for (x, y), colour in painted.items():
                self.assertEqual(tuple(int(v) for v in after[y, x, :3]), colour)
            self.assertTrue((after[..., 3] == before[..., 3]).all())                            # alpha never moves

    def as_built(self, selector):
        """the kit package as a build holds it when the glyph step runs: the nameplate pass first (its Jaguars letters
        come from the retail disc; elsewhere it may fill a hollow hyphen), as the digit document's nameplate rows are
        pinned"""
        if not hasattr(type(self), "_retail"):
            type(self)._retail = up.retail_kits_for_nameplates(RETAIL) if RETAIL.is_file() else None
        return up.after_nameplate_pass(selector, self.kits[selector], self._retail)

    def test_every_digit_row_compiles_to_its_pin_through_the_studio_digit_route(self):
        document = gf.digits_b81()
        for selector in REDRAWN:
            replacements, receipt = gf.compile_resource(selector, self.as_built(selector), strict=True, document=document)
            digits = [p for p in receipt["parts"] if p["kind"] in ("digit_png", "digit_derived")]  # (and nameplate rows)
            self.assertEqual(len(digits), len([r for r in all_digit_rows() if r["selector"] == selector]), selector)
            drawn = len(PER_DIGIT.get(selector, range(10)))
            self.assertIn(len(digits), (drawn, 2 * drawn), selector)              # jersey digits, and arm digits where drawn
            self.assertEqual(len(replacements), len([r for r in document["textures"] if r["selector"] == selector]))
            self.assertEqual(receipt["skipped_textures"], [])

    def test_the_released_disc_still_holds_the_jaguars_plates_the_nameplate_pass_was_meant_to_replace(self):
        # the evidence for the guard: every pinned Jaguars atlas is still at the pass's own "before" hash
        for row in nf.structures(nf.spec()):
            raw = self.kits[row["selector"]]
            chunk = kf._chunk_for(raw, row["chunk"])
            self.assertEqual(hashlib.sha256(raw[chunk.offset:chunk.end_offset]).hexdigest(), row["before_sha256"],
                             row["selector"])


#: b81-uniforms batch 4 (Noah 11/19: "Jags road nameplate and all nameplates should match real ones"): the nameplate
#: strips redrawn to this season's measured lettering. selector -> (fill, outline, stem texels, bar rows). R2 (art
#: director 11/20): the weight is set from emulator close-ups, not from a stretch sum (2 texel stems read as hairlines
#: in the game, about 0.10 of the cap; 3 texels about 0.17; the real 2026 names 0.12 to 0.19).
NAMEPLATES = {
    **{s: ("#101010", None, 3, 3) for s in ("12A0", "12A6", "12H6")},       # Jaguars road and Bold City: thin horizontals
    "12H0": ("#FFFFFF", None, 3, 3),                                       # Jaguars home: white, no black outline
    "00A0": ("#A0233F", None, 3, 3), "00H0": ("#FFFFFF", None, 3, 3),      # Cardinals: cut-corner face
    "00A6": ("#A0233F", None, 3, 3), "00H6": ("#A0233F", None, 3, 3),      # the black alternate wears red names
    "01A9": ("#FFFFFF", "#D40038", 3, 4), "01H9": ("#FFFFFF", "#D40038", 3, 4),  # Falcons 1966: white, thin red edge
    "02H0": ("#FFFFFF", None, 3, 3), "02H2": ("#FFFFFF", None, 3, 3),
    "11A0": ("#0C3A9C", None, 3, 3), **{s: ("#FFFFFF", None, 3, 3) for s in ("11H0", "11A3", "11A4", "11H3", "11H4")},
    **{s: ("#0A0A0A", None, 3, 3) for s in ("17A1", "17A8", "17H8")},
    "18A7": ("#0E2878", None, 3, 3), "18H7": ("#0E2878", None, 3, 3),      # Giants Vintage White: slab serif
    **{s: ("#145F47", None, 3, 3) for s in ("19A0", "19A7", "19H7")},       # Jets white: green, as the real names
    "27A0": ("#0E0E0E", None, 3, 3),                                       # Buccaneers road: black, the strip was red
}
NAME_GLYPHS = "'-ABCDEFGHIJKLMNOPQRSTUVWXYZc"
#: Noah 11/19 (decision 3): the Browns road name strips recoloured to the charcoal of the road numbers; letters, soft
#: edges and glyph widths as released (a ``names_png`` row, no ``name_widths`` row)
RECOLOURED_NAMES = {s: CLE_CHARCOAL for s in ("30A0", "30A4", "30H4")}


def names_rows(kind=None):
    """b81-retail-free-art: ``names_png`` also yields the ``names_derived`` strips (the Jaguars road strip, made at
    build time from the strip the nameplate pass leaves; see strip_picture)."""
    kinds = ("names_png", "names_derived") if kind == "names_png" else (kind,) if kind else (
        "names_png", "names_derived", "name_widths")
    return [r for r in gf.digits_b81()["textures"] if r["kind"] in kinds]


_STRIPS = {}


def strip_picture(row):
    """A strip row's picture: its PNG, or a ``names_derived`` row's operations on the strip the released disc holds
    after the nameplate pass (None without the released and retail discs)."""
    if row["kind"] == "names_png":
        return png_rgba(gf.art_folder(gf.digits_b81()) / row["png"])[0]
    if not (DISC.is_file() and RETAIL.is_file()):
        return None
    if row["selector"] not in _STRIPS:
        raw = up.after_nameplate_pass(row["selector"], up.read_kits(DISC, [row["selector"]])[row["selector"]],
                                      up.retail_kits_for_nameplates(RETAIL))
        chunk = gf._chunk_for(raw, row["chunk"])
        _STRIPS[row["selector"]] = gf.names_level0(raw[chunk.offset:chunk.end_offset])
    return gf.derive_digit(_STRIPS[row["selector"]], row["derive"])


def hex_rgb(text):
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


def measure_strip(rgba, widths, fill):
    """cap rows, the H's stem, the E's top bar and every counter of A B D O P Q R, measured on a strip"""
    is_fill = (rgba[..., 3] == 255) & (np.abs(rgba[..., :3].astype(int) - np.array(fill)).max(-1) == 0)

    def cell(ch, mask):
        i = NAME_GLYPHS.index(ch)
        return mask[:, 32 * (i + 1):32 * (i + 1) + widths[i]]

    rows = sorted({int(y) for ch in "ABCDEFGHIJKLMNOPRSTUVWXYZ" for y in np.flatnonzero(cell(ch, is_fill).any(1))})
    h = cell("H", is_fill)
    stem = set()
    for y in range(7, 13):                                   # the left stem, clear of serifs and the crossbar
        xs = np.flatnonzero(h[y])
        run = 1
        while run < len(xs) and xs[run] == xs[0] + run:
            run += 1
        stem.add(run)
    e = cell("E", is_fill)
    right = int(np.flatnonzero(e.any(0)).max()) - 1
    bar = int(np.flatnonzero(~e[4:, right]).min())
    counters = {ch: int(nf._enclosed(~(cell(ch, rgba[..., 3] > 0))).sum()) for ch in "ABDOPQR"}
    o = nf._enclosed(~cell("O", rgba[..., 3] > 0))
    return dict(cap=(rows[0], rows[-1]), stem=stem, bar=bar, counters=counters,
                o_counter_width=int(o.sum(1).max()))


class NameplateDocument(unittest.TestCase):
    """The redrawn nameplate strips (chunk 43) and their glyph widths (the NAME chunk 44), one pair per kit."""

    def test_rows_pair_up_and_are_pinned(self):
        strips = {r["selector"]: r for r in names_rows("names_png")}
        names = {r["selector"]: r for r in names_rows("name_widths")}
        self.assertEqual(sorted(strips), sorted(set(NAMEPLATES) | set(RECOLOURED_NAMES)))
        self.assertEqual(sorted(names), sorted(NAMEPLATES))
        folder = gf.art_folder(gf.digits_b81())
        for selector, row in strips.items():
            self.assertEqual((row["chunk"], row["texture"]), (43, "names"))
            if row["kind"] == "names_derived":                # b81-retail-free-art: made at build time
                self.assertNotIn("png", row)
            else:
                self.assertEqual(hashlib.sha256((folder / row["png"]).read_bytes()).hexdigest(), row["png_sha256"], selector)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertTrue(row["note"] and row["defects"], selector)
            if selector in RECOLOURED_NAMES:
                continue
            n = names[selector]
            self.assertEqual((n["chunk"], n["texture"]), (44, "NAME"))
            self.assertEqual(len(n["widths"]), 29)
            self.assertTrue(all(1 <= w <= 32 for w in n["widths"]), selector)
            self.assertNotEqual(n["before_sha256"], n["after_sha256"])

    def test_strips_are_crisp_and_wear_only_the_kits_colours(self):
        folder = gf.art_folder(gf.digits_b81())
        for row in names_rows("names_png"):
            if row["selector"] in RECOLOURED_NAMES:
                continue
            fill, outline, _stem, _bar = NAMEPLATES[row["selector"]]
            rgba = strip_picture(row)
            if rgba is None:
                continue
            name = row.get("png", row["selector"])
            self.assertEqual(rgba.shape, (32, 1024, 4))
            self.assertEqual(set(np.unique(rgba[..., 3]).tolist()), {0, 255}, name)        # no soft edges
            opaque = {tuple(int(v) for v in c) for c in np.unique(rgba[rgba[..., 3] == 255][:, :3], axis=0)}
            self.assertEqual(opaque, {hex_rgb(fill)} | ({hex_rgb(outline)} if outline else set()), name)
            clear = {tuple(int(v) for v in c) for c in np.unique(rgba[rgba[..., 3] == 0][:, :3], axis=0)}
            self.assertEqual(clear, {hex_rgb(outline or fill)}, name)     # a filtered edge never fades to black

    def test_every_glyph_starts_on_its_offset_and_fits_its_stored_width(self):
        folder = gf.art_folder(gf.digits_b81())
        widths = {r["selector"]: r["widths"] for r in names_rows("name_widths")}
        for row in names_rows("names_png"):
            if row["selector"] in RECOLOURED_NAMES:
                continue
            rgba = strip_picture(row)
            if rgba is None:
                continue
            ink = rgba[..., 3] >= kf.NAME_ATLAS_ALPHA
            for i, width in enumerate(widths[row["selector"]]):
                cols = np.flatnonzero(ink[:, 32 * (i + 1):32 * (i + 2)].any(0))
                self.assertEqual(int(cols[0]), 0, (row["selector"], NAME_GLYPHS[i]))
                self.assertEqual(len(cols), int(cols[-1]) + 1, (row["selector"], NAME_GLYPHS[i]))   # one run of columns
                self.assertLessEqual(len(cols), width, (row["selector"], NAME_GLYPHS[i]))        # never cut
                self.assertLessEqual(width - len(cols), 2, (row["selector"], NAME_GLYPHS[i]))    # the letter gap

    def test_the_letters_measure_as_drawn(self):
        folder = gf.art_folder(gf.digits_b81())
        widths = {r["selector"]: r["widths"] for r in names_rows("name_widths")}
        for row in names_rows("names_png"):
            if row["selector"] in RECOLOURED_NAMES:
                continue
            fill, _outline, stem, bar = NAMEPLATES[row["selector"]]
            rgba = strip_picture(row)
            if rgba is None:
                continue
            got = measure_strip(rgba, widths[row["selector"]], hex_rgb(fill))
            self.assertEqual(got["cap"], (4, 27), row["selector"])                   # 24 rows, as every 2026 strip
            self.assertEqual(got["stem"], {stem}, row["selector"])
            self.assertEqual(got["bar"], bar, row["selector"])
            self.assertTrue(all(n >= 1 for n in got["counters"].values()), (row["selector"], got["counters"]))
            self.assertGreaterEqual(got["o_counter_width"], 2, row["selector"])

    def test_the_recoloured_strips_wear_one_colour_everywhere(self):
        folder = gf.art_folder(gf.digits_b81())
        for row in names_rows("names_png"):
            if row["selector"] in RECOLOURED_NAMES:
                rgba, _info = png_rgba(folder / row["png"])
                self.assertEqual(rgba.shape, (32, 1024, 4))
                self.assertTrue((rgba[..., :3] == RECOLOURED_NAMES[row["selector"]]).all(), row["png"])


@unittest.skipUnless(DISC.is_file() and RETAIL.is_file(), "the released v0.9 disc or the retail disc is not on this machine")
class RealDiscNameplates(unittest.TestCase):
    """Offline real-disc proof: each redrawn strip and its widths compile to their pins on the released kits as a build
    holds them when the pass runs (after the nameplate pass, whose Jaguars letters come from the retail disc)."""

    @classmethod
    def setUpClass(cls):
        retail = up.retail_kits_for_nameplates(RETAIL)
        kits = up.read_kits(DISC, sorted(set(NAMEPLATES) | set(RECOLOURED_NAMES)))
        cls.kits = {s: up.after_nameplate_pass(s, raw, retail) for s, raw in kits.items()}

    def test_every_names_row_compiles_to_its_pin(self):
        document = gf.digits_b81()
        for selector in sorted(set(NAMEPLATES) | set(RECOLOURED_NAMES)):
            replacements, receipt = gf.compile_resource(selector, self.kits[selector], strict=True, document=document)
            kinds = sorted("names_png" if p["kind"] == "names_derived" else p["kind"]  # a strip made at build time counts
                           for p in receipt["parts"] if p["kind"] in ("names_png", "names_derived", "name_widths"))
            self.assertEqual(kinds, ["names_png"] if selector in RECOLOURED_NAMES else ["name_widths", "names_png"],
                             selector)
            self.assertEqual(receipt["skipped_textures"], [], selector)

    def test_the_compiled_strip_is_the_authored_one_and_nothing_else_moves(self):
        folder = gf.art_folder(gf.digits_b81())
        for row in names_rows("names_png"):
            raw = self.kits[row["selector"]]
            replacements, _receipt = gf.compile_resource(row["selector"], raw, strict=True, document=gf.digits_b81())
            out = bytearray(raw)
            for offset, data in replacements:
                out[offset:offset + len(data)] = data
            chunk = kf._chunk_for(bytes(out), 43)
            name = kf._chunk_for(bytes(out), 44)
            moved = np.flatnonzero(np.frombuffer(bytes(out), np.uint8) != np.frombuffer(raw, np.uint8))
            digits = [(kf._chunk_for(raw, r["chunk"]).offset, kf._chunk_for(raw, r["chunk"]).end_offset)
                      for r in all_digit_rows() if r["selector"] == row["selector"]]
            for at in moved:
                inside = (chunk.offset <= at < chunk.end_offset or name.offset <= at < name.end_offset
                          or any(a <= at < b for a, b in digits))
                self.assertTrue(inside, (row["selector"], int(at)))
            compiled = gf.names_level0(bytes(out)[chunk.offset:chunk.end_offset])
            self.assertTrue((compiled == strip_picture(row)).all(), row["selector"])
            if row["selector"] in RECOLOURED_NAMES:                 # the released letters, only the colour moves
                before = gf.names_level0(raw[chunk.offset:chunk.end_offset])
                self.assertTrue((compiled[..., 3] == before[..., 3]).all(), row["selector"])
                self.assertEqual(bytes(out)[name.offset:name.end_offset], raw[name.offset:name.end_offset])
                continue
            widths = kf.name_metrics(bytes(out)[name.offset:name.end_offset])
            self.assertTrue(kf.layout_fits(kf.atlas_glyph_starts(bytes(out)[chunk.offset:chunk.end_offset]), widths))
            fill, _outline, stem, bar = NAMEPLATES[row["selector"]]
            got = measure_strip(compiled, [w for _x, w in widths], hex_rgb(fill))
            self.assertEqual((got["cap"], got["stem"], got["bar"]), ((4, 27), {stem}, bar), row["selector"])
            self.assertTrue(all(n >= 1 for n in got["counters"].values()), row["selector"])

    def test_the_gold_saints_kits_stop_cutting_m_and_w(self):
        # the gameday gold kits carried the white alternate's letters with another kit's widths: M and W lost columns
        for selector in ("17A8", "17H8"):
            raw = self.kits[selector]
            name = kf._chunk_for(raw, 44)
            before = dict(zip(NAME_GLYPHS, (w for _x, w in kf.name_metrics(raw[name.offset:name.end_offset]))))
            self.assertLess(before["W"], 20)
            row = [r for r in names_rows("name_widths") if r["selector"] == selector][0]
            after = dict(zip(NAME_GLYPHS, row["widths"]))
            folder = gf.art_folder(gf.digits_b81())
            png = [r for r in names_rows("names_png") if r["selector"] == selector][0]["png"]
            ink = png_rgba(folder / png)[0][..., 3] > 0
            for ch in "MW":
                i = NAME_GLYPHS.index(ch)
                self.assertGreaterEqual(after[ch], int(np.flatnonzero(ink[:, 32 * (i + 1):32 * (i + 2)].any(0)).max()) + 1)


if __name__ == "__main__":
    unittest.main()
