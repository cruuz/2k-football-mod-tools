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


def kit_rows():
    return kf.uniforms_b81()["textures"]


def digit_rows():
    return [r for r in gf.digits_b81()["textures"] if r["kind"] == "digit_png"]


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
            self.assertEqual(row["kind"], "tset")
            self.assertEqual((row["chunk"], "tset"), up.chunk_of(row["texture"]))
            self.assertEqual(row["size"][:2], SIZES[row["texture"]])
            self.assertEqual(len(row["before_sha256"]), 64)
            self.assertEqual(len(row["after_sha256"]), 64)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertGreater(row["resource_size"], row["offset"] + row["length"] - 1)
            self.assertTrue(row["note"] and row["defects"] and row["reference"], row["selector"])
            self.assertEqual(row["ops"][-1]["op"], "runs")
            self.assertTrue(all(op["op"] == "texels" for op in row["ops"][:-1]))
            self.assertGreater(row["texels"], 0)

    def test_every_run_stays_inside_its_texture(self):
        for row in kit_rows():
            width, height = row["size"][:2]
            for y, x0, colours in row["ops"][-1]["rows"]:
                self.assertEqual(len(colours) % 6, 0)
                bytes.fromhex(colours)
                self.assertTrue(0 <= y < height and 0 <= x0 and x0 + len(colours) // 6 <= width, (row["selector"], y, x0))

    def test_every_named_colour_is_a_texel_the_runs_also_paint(self):
        # the ``texels`` operations only name the art's colours for the palette; the runs carry the picture
        for row in kit_rows():
            painted = run_texels(row)
            self.assertLessEqual(len(row["ops"]) - 1, 48, row["selector"])
            for op in row["ops"][:-1]:
                (x, y), = op["points"]
                self.assertEqual("#%02X%02X%02X" % painted[(x, y)], op["color"], row["selector"])

    def test_only_a_named_row_may_fold_a_palette_twin(self):
        folded = {(r["selector"], r["texture"]): (r["folded_twin_entries"], r["texels_moved_one_level"])
                  for r in kit_rows() if "folded_twin_entries" in r}
        self.assertEqual(folded, {("23A0", "pants00"): (1, 7)})       # the Rams road pants palette is full

    def test_the_first_batch_is_the_reviewed_kits(self):
        self.assertEqual(sorted((r["selector"], r["texture"]) for r in kit_rows() if r["texture"] != "jersey00"),
                         [("00A6", "sleeve00"), ("00A7", "sleeve00"), ("00H6", "sleeve00"), ("00H7", "sleeve00"), ("01A9", "pants00"),
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
                          ("17A8", "pants00"), ("17H8", "pants00"), ("19A2", "pants00"), ("19H2", "pants00"),
                          ("21A4", "sleeve00"), ("21H4", "sleeve00"), ("23A0", "pants00"), ("25H0", "pants00"),
                          ("26A4", "pants00"), ("26A4", "socks00"), ("26H4", "sleeve00"), ("27A0", "pants00"),
                          ("27H0", "pants00")])
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
        # R2 (order R2-C): the Bengals pants tiger strokes, one geometry on all six Bengals pants (06H0 06A0 06H5 06A5
        # 06H6 06A6), each in its own stroke colour

    def test_the_jersey_rows_repaint_only_the_chest_under_the_collar(self):
        # Round 2 (Noah 11/18: "the NY logo on the giants jersey below the nfl patch is too large. There are likely
        # similar issues on other jerseys"): the league collar shield at its real size on 166 packages (12 by 16
        # texels; it was 8 by 10), wordmarks moved clear of it, the Giants mark as wide as the shield. A jersey row
        # may touch nothing but the strip of chest between the collar point and the number.
        # Batch 3 added: wordmarks redrawn at their real width (Eagles, Titans, Broncos), the Saints 60th patch at its
        # real size, the Texans memorial oval, the Panthers alternate and Bills Nickel City shields.
        # Batch 4 (KITS4) named the only jerseys repainted beyond that strip: see test_the_batch_4_whole_jersey_rows.
        jerseys = [r for r in kit_rows() if r["texture"] == "jersey00"]
        self.assertEqual(len(jerseys), 170)
        self.assertEqual(len({r["selector"] for r in jerseys}), 170)
        self.assertTrue(set(WHOLE_JERSEY) <= {r["selector"] for r in jerseys})
        for row in jerseys:
            if row["selector"] in WHOLE_JERSEY:
                continue
            for run in [op for op in row["ops"] if op["op"] == "runs"][0]["rows"]:   # [row, first column, colours]
                self.assertTrue(58 <= run[0] <= 112, (row["selector"], run[:2]))   # down to the old lettering some kits lose
                self.assertTrue(90 <= run[1] and run[1] + len(run[2]) // 6 <= 216, (row["selector"], run[:2]))
        for selector in ("25H7", "25A7", "28H7", "28A7", "11H4", "11A4", "07H9", "07A9"):
            self.assertNotIn(selector, {r["selector"] for r in jerseys})        # open: no 2026 picture of the look

    def test_the_batch_4_whole_jersey_rows(self):
        # KITS4 (measured on 2026 game frames, approved from its review sheet): the Lions Defend the Den jersey and
        # pants are a pale blue-grey, not near-white (DET 2026-11-01 MIN frames: target #B6C1DB, shading kept by
        # scaling, so the median texel is the target); the Seahawks 26H4 navy home jersey wears the lime shoulder
        # panels, grey bars and lime collar chevrons of the same jersey's 26H0 art, which lie above the number only.
        for selector in ("09H9", "09A9"):
            for texture, size in (("jersey00", 512 * 256), ("pants00", None)):
                row = [r for r in kit_rows() if (r["selector"], r["texture"]) == (selector, texture)][0]
                painted = run_texels(row)
                if size:
                    # the whole torso, front and back; a texel the new chest DETROIT (Noah 11/19, decision 6) paints in
                    # the colour the released texture already had there is not a run: those lie inside the word's box
                    missing = {(x, y) for x in range(512) for y in range(256)} - set(painted)
                    self.assertLessEqual(len(missing), 8, (selector, texture))
                    self.assertTrue(all(132 <= x <= 190 and 93 <= y <= 105 for x, y in missing), (selector, missing))
                median = np.median(np.array(list(painted.values())), axis=0)
                self.assertTrue(near(tuple(median), (0xB6, 0xC1, 0xDB), 12), (selector, texture, median))
        row = [r for r in kit_rows() if (r["selector"], r["texture"]) == ("26H4", "jersey00")][0]
        painted = run_texels(row)
        self.assertLessEqual(max(y for _x, y in painted), 112)                  # never below the chest strip
        shoulders = {(x, y): c for (x, y), c in painted.items() if not (58 <= y <= 112 and 90 <= x < 216)}
        self.assertTrue(shoulders)
        self.assertLessEqual(max(y for _x, y in shoulders), 73)                 # the shoulder panels and the collar
        lime = sum(1 for c in shoulders.values() if c == (105, 190, 40))        # Action Green #69BE28
        self.assertGreater(lime, len(shoulders) // 2)

    def test_no_row_touches_a_helmet_or_the_far_away_atlas(self):
        for row in kit_rows():
            self.assertIn(row["chunk"], (1, 2, 3, 4), row["selector"])
        for row in digit_rows():
            self.assertTrue(13 <= row["chunk"] <= 22 or 33 <= row["chunk"] <= 42, row["selector"])  # jersey and arm digits, never the helmet's


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
            self.assertIn(row["kind"], ("digit_png", "names_png", "name_widths"))
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
        by = {}
        for row in digit_rows():
            by.setdefault(row["selector"], set()).add(row["chunk"])
        self.assertEqual(tuple(sorted(by)), tuple(sorted(REDRAWN)))
        for selector, chunks in by.items():
            digits = PER_DIGIT.get(selector, range(10))
            self.assertEqual({c for c in chunks if c < 23}, {13 + d for d in digits}, selector)
            self.assertIn({c for c in chunks if c >= 33}, (set(), {33 + d for d in digits}), selector)

    def test_art_is_as_authored_and_in_flat_colours(self):
        from mod_editor.core.nfl2k5_digit_art import REGISTRATION_KEY, registration_mode
        folder = gf.art_folder(gf.digits_b81())
        for path in sorted({folder / r["png"] for r in digit_rows()}):
            rgba, info = png_rgba(path)
            self.assertIn(rgba.shape, ((64, 64, 4), (32, 32, 4)), path.name)
            self.assertEqual(info.get(REGISTRATION_KEY), "as_authored", path.name)
            self.assertEqual(registration_mode(path.read_bytes()), "as_authored")
            solid = rgba[rgba[..., 3] == 255][:, :3]
            colours, counts = np.unique(solid, axis=0, return_counts=True)
            self.assertGreater(len(solid), 500 if rgba.shape[0] == 64 else 100, path.name)
            layers = 4 if path.name.split("_")[1] in FOUR_LAYERS else 3
            top = counts.argsort()[::-1][:layers]
            self.assertGreater(counts[top].sum(), 0.8 * len(solid), path.name)        # a fill, an outline, at most an inline

    def test_every_redrawn_jersey_number_stands_full_height_inside_the_safe_columns(self):
        # batch 3: a number is 62 rows of its 64 cell (22.2 cm on the player, the collar shield 0.141 of that as on the
        # real jersey). The pack drew several sets 50 to 56 rows tall. Two-digit numbers are cut outside columns 12-51.
        folder = gf.art_folder(gf.digits_b81())
        for row in digit_rows():
            if row["chunk"] > 22:
                continue
            solid = png_rgba(folder / row["png"])[0][..., 3] > 127
            rows = np.flatnonzero(solid.any(axis=1)); cols = np.flatnonzero(solid.any(axis=0))
            self.assertGreaterEqual(int(rows.max() - rows.min() + 1), 61, row["png"])
            self.assertTrue(12 <= cols.min() and cols.max() <= 51, (row["png"], int(cols.min()), int(cols.max())))

    def test_number_widths_follow_the_measured_real_numbers(self):
        # width of the 0 in texels at 62 rows = real width over height x 62 / 1.048 (the cell is 23.8 by 22.7 cm)
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for selector, width in (("18H0", 37), ("18A0", 37), ("18H7", 37), ("24A0", 35), ("00H0", 37), ("00A0", 37),
                                ("01H0", 39), ("06H0", 31), ("14H0", 37), ("07H0", 35), ("28H7", 36),   # 28H7: 34 and its 2 texel dark layer
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
            solid = png_rgba(folder / by[(selector, 13)])[0][..., 3] > 127
            cols = np.flatnonzero(solid.any(axis=0))
            self.assertLessEqual(abs(int(cols.max() - cols.min() + 1) - width), 1, selector)

    def test_the_chargers_digits_stand_upright(self):
        # the slant the pass removes: on the released digits the opaque box of the top rows sits to the right of the
        # bottom rows' (the 1's stem leans about 0.13 texel per row). Upright: the 1's stem keeps its column.
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for selector in CHARGERS:
            rgba, _info = png_rgba(folder / by[(selector, 14)])                                 # the digit 1
            solid = rgba[..., 3] > 127
            rows = np.flatnonzero(solid.any(axis=1))
            body = rows[len(rows) // 3:]                                                        # below the flag
            centres = np.array([np.flatnonzero(solid[y]).mean() for y in body])
            slope = np.polyfit(body.astype(float), centres, 1)[0]
            self.assertLess(abs(slope), 0.03, (selector, slope))

    def test_one_shape_set_serves_every_chargers_kit(self):
        # the alternates' own digits were of uneven height; every kit now wears the home shapes in its own colours
        folder = gf.art_folder(gf.digits_b81())
        by = {(r["selector"], r["chunk"]): r["png"] for r in digit_rows()}
        for chunk in range(13, 23):
            masks = {selector: png_rgba(folder / by[(selector, chunk)])[0][..., 3] > 127 for selector in CHARGERS}
            first = masks[CHARGERS[0]]
            for selector, mask in masks.items():
                self.assertLessEqual(int((mask ^ first).sum()), 4, (selector, chunk))
        heights = []
        for chunk in range(13, 23):
            solid = png_rgba(folder / by[("24H0", chunk)])[0][..., 3] > 127
            rows = np.flatnonzero(solid.any(axis=1))
            heights.append(int(rows.max() - rows.min() + 1))
        self.assertLessEqual(max(heights) - min(heights), 2, heights)

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
        for row in digit_rows():
            if row["selector"] not in ("27A0", "27H0"):
                continue
            rgba, _info = png_rgba(folder / row["png"])
            opaque = rgba[..., 3] == 255
            colours, counts = np.unique(rgba[opaque][:, :3], axis=0, return_counts=True)
            fill = opaque & (rgba[..., :3] == colours[counts.argmax()]).all(-1)
            edge = ~opaque | (opaque & (rgba[..., :3].max(-1) < 0x60))
            self.assertFalse((ndimage.binary_dilation(fill, np.ones((3, 3), bool)) & edge).any(), row["png"])
            orange = opaque & (rgba[..., :3] == TB_ORANGE).all(-1)
            self.assertGreater(int(orange.sum()), 100, row["png"])

    def test_the_patriots_numbers_stand_rows_1_to_62(self):
        # Noah 11/19 (decision 2): "switch to the full height" (the game drew solid rows 2 to 61)
        folder = gf.art_folder(gf.digits_b81())
        for row in digit_rows():
            if row["selector"] in ("16H0", "16A0"):
                rows = np.flatnonzero((png_rgba(folder / row["png"])[0][..., 3] > 127).any(axis=1))
                self.assertEqual((int(rows.min()), int(rows.max())), (1, 62), row["png"])

    def test_the_browns_road_numbers_are_charcoal(self):
        # Noah 11/19 (decision 3): "switch to the neutral charcoal the photos show" (not the kit brown #311D00)
        folder = gf.art_folder(gf.digits_b81())
        rows = [r for r in digit_rows() if r["selector"] == "30A0"]
        self.assertEqual(len(rows), 20)
        for row in rows:
            rgba, _info = png_rgba(folder / row["png"])
            self.assertEqual({tuple(int(v) for v in c) for c in rgba[rgba[..., 3] > 0][:, :3]}, {CLE_CHARCOAL}, row["png"])

    def test_the_ravens_4_has_the_tall_closed_counter(self):
        # R2: the 2026 Ravens 4 has a tall closed triangular counter, 0.27 and 0.30 of the height on the two photographs;
        # the released and batch 6 4 had a slit about 3 rows tall (an opening of 11 rows in the fill)
        from scipy import ndimage
        folder = gf.art_folder(gf.digits_b81())
        for row in digit_rows():
            if row["selector"] not in RAVENS or row["chunk"] not in (17, 37):
                continue
            rgba, _info = png_rgba(folder / row["png"])
            opaque = rgba[..., 3] == 255
            colours, counts = np.unique(rgba[opaque][:, :3], axis=0, return_counts=True)
            fill = opaque & (rgba[..., :3] == colours[counts.argmax()]).all(-1)
            holes, count = ndimage.label(ndimage.binary_fill_holes(fill) & ~fill)
            self.assertGreaterEqual(count, 1, row["png"])
            rows = np.flatnonzero((holes == np.bincount(holes.ravel())[1:].argmax() + 1).any(axis=1))
            self.assertTrue(16 <= len(rows) <= 19, (row["png"], len(rows)))           # 0.26 to 0.31 of 62 rows
            cols = np.flatnonzero((rgba[..., 3] > 127).any(axis=0))
            self.assertEqual(len(cols), 31, row["png"])

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
            masks = {s: png_rgba(folder / by[(s, chunk)])[0][..., 3] > 127 for s in BRONCOS}
            for selector, mask in masks.items():
                self.assertEqual(int((mask ^ masks["08H0"]).sum()), 0, (selector, chunk))
            for selector in BRONCOS:
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
        # R2: #C8C7C7 could not be seen on the white jersey in the game; the real edge reads 0.41 of the jersey white
        folder = gf.art_folder(gf.digits_b81())
        rows = [r for r in digit_rows() if r["selector"] == "20A0"]
        self.assertEqual(len(rows), 20)
        for row in rows:
            rgba, _info = png_rgba(folder / row["png"])
            colours = {tuple(int(v) for v in c) for c in rgba[rgba[..., 3] > 0][:, :3]}
            self.assertEqual(colours, {(0, 0, 0), LV_ROAD_SILVER}, row["png"])

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
        helmets = source.index("apply_helmets_b81(target)")
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
        cls.kits = up.read_kits(DISC, selectors)

    def after(self, selector, texture):
        row = [r for r in kit_rows() if (r["selector"], r["texture"]) == (selector, texture)][0]
        raw = self.kits[selector]
        chunk = kf._chunk_for(raw, row["chunk"])
        new, _detail = kf.compile_texture(raw[chunk.offset:chunk.end_offset], row)
        return up.level0(new, "tset")[0]

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
        purple, gold, white = (79, 38, 131), (255, 198, 47), (255, 255, 255)
        pants = self.after("15H0", "pants00")
        for y in (40, 100, 160):
            for columns, front_first in ((range(100, 185), True), (range(327, 412), False)):   # left leg, right leg
                row = [tuple(int(v) for v in pants[y, x, :3]) for x in columns]
                band = [i for i, c in enumerate(row) if c == purple]
                line = [i for i, c in enumerate(row) if c == gold]
                self.assertGreaterEqual(len(band), 11, y)                                    # it was 4 texels
                self.assertTrue(3 <= len(line) <= 7, (y, len(line)))
                self.assertGreater(len(band), 2 * len(line), y)
                if front_first:
                    self.assertLess(max(line), min(band), y)                                 # gold toward the front
                else:
                    self.assertGreater(min(line), max(band), y)
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
        torso = np.abs(self.after("26H4", "jersey00").astype(int) - self.after("26H0", "jersey00").astype(int)).max(-1)
        self.assertLessEqual(int(torso.max()), 12)
        raw = self.kits["26H0"]
        chunk = kf._chunk_for(raw, up.chunk_of("sleeve00")[0])
        home = up.level0(raw[chunk.offset:chunk.end_offset], "tset")[0]
        self.assertLessEqual(int(np.abs(self.after("26H4", "sleeve00").astype(int) - home.astype(int)).max()), 12)
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

    def test_every_kit_row_is_waiting_on_the_released_disc_and_compiles_to_its_pin(self):
        result = up.states(DISC)
        self.assertEqual((result["before"], result["after"], result["other"], result["absent"]),
                         (len(kit_rows()), 0, 0, 0), result["rows"])
        for selector in sorted({r["selector"] for r in kit_rows()}):
            replacements, receipt = kf.compile_resource(selector, self.kits[selector], strict=True,
                                                        document=kf.uniforms_b81())
            rows = [r for r in kit_rows() if r["selector"] == selector]
            self.assertEqual(len(replacements), len(rows), selector)
            for part in receipt["parts"]:
                folded = selector == "23A0" and part.get("texture") == "pants00"   # the one full palette (first batch)
                self.assertEqual(part["merged_twin_slots"], 1 if folded else 0, (selector, part.get("texture")))
                if not folded:
                    self.assertEqual(part["protected_texels_moved_one_level"], 0, selector)
                else:                               # over all stored mips; seven of them on the top level
                    self.assertLessEqual(part["protected_texels_moved_one_level"], 30)

    def test_the_compiled_kit_textures_hold_exactly_the_authored_runs(self):
        for row in kit_rows():
            raw = self.kits[row["selector"]]
            chunk = kf._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            before, _native = up.level0(span, "tset")
            new, _detail = kf.compile_texture(span, row)
            self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"])
            after, _native = up.level0(new, "tset")
            painted = run_texels(row)
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
            digits = [p for p in receipt["parts"] if p["kind"] == "digit_png"]     # (a kit may also carry nameplate rows)
            self.assertEqual(len(digits), len([r for r in digit_rows() if r["selector"] == selector]), selector)
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
RETAIL = Path(os.environ.get("B81_RETAIL_DISC", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
#: Noah 11/19 (decision 3): the Browns road name strips recoloured to the charcoal of the road numbers; letters, soft
#: edges and glyph widths as released (a ``names_png`` row, no ``name_widths`` row)
RECOLOURED_NAMES = {s: CLE_CHARCOAL for s in ("30A0", "30A4", "30H4")}


def names_rows(kind=None):
    return [r for r in gf.digits_b81()["textures"] if r["kind"] in ("names_png", "name_widths")
            and (kind is None or r["kind"] == kind)]


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
            rgba, _info = png_rgba(folder / row["png"])
            self.assertEqual(rgba.shape, (32, 1024, 4))
            self.assertEqual(set(np.unique(rgba[..., 3]).tolist()), {0, 255}, row["png"])        # no soft edges
            opaque = {tuple(int(v) for v in c) for c in np.unique(rgba[rgba[..., 3] == 255][:, :3], axis=0)}
            self.assertEqual(opaque, {hex_rgb(fill)} | ({hex_rgb(outline)} if outline else set()), row["png"])
            clear = {tuple(int(v) for v in c) for c in np.unique(rgba[rgba[..., 3] == 0][:, :3], axis=0)}
            self.assertEqual(clear, {hex_rgb(outline or fill)}, row["png"])     # a filtered edge never fades to black

    def test_every_glyph_starts_on_its_offset_and_fits_its_stored_width(self):
        folder = gf.art_folder(gf.digits_b81())
        widths = {r["selector"]: r["widths"] for r in names_rows("name_widths")}
        for row in names_rows("names_png"):
            if row["selector"] in RECOLOURED_NAMES:
                continue
            ink = png_rgba(folder / row["png"])[0][..., 3] >= kf.NAME_ATLAS_ALPHA
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
            got = measure_strip(png_rgba(folder / row["png"])[0], widths[row["selector"]], hex_rgb(fill))
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
            kinds = sorted(p["kind"] for p in receipt["parts"] if p["kind"] in ("names_png", "name_widths"))
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
                      for r in digit_rows() if r["selector"] == row["selector"]]
            for at in moved:
                inside = (chunk.offset <= at < chunk.end_offset or name.offset <= at < name.end_offset
                          or any(a <= at < b for a, b in digits))
                self.assertTrue(inside, (row["selector"], int(at)))
            compiled = gf.names_level0(bytes(out)[chunk.offset:chunk.end_offset])
            self.assertTrue((compiled == png_rgba(folder / row["png"])[0]).all(), row["selector"])
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
