"""b81-art: the finished 2026 helmets lose the painted 2004 Revolution vents, the 2004 flag's outline and the old-logo
pieces (data/nfl2k5_kit_fixes_2026_b81.json, tools/b81_helmet_cleanup.py, kit_fixes.apply_helmets_b81).

The document's shape and pins, the ``runs`` art operation, the authoring helpers on synthetic textures, the build hook,
and (with the released v0.9 disc on this machine, B81_ART_DISC) every row compiled against the real kit package."""
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_helmet_cleanup as hc  # noqa: E402
from mod_editor.core import build_steps, mod_build, nfl2k5_kit_fixes_2026 as kf  # noqa: E402

DISC = Path(os.environ.get("B81_ART_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
#: The texel the modern shell's vents, seams and cuts sample on every team's helmet02 (LOGO_helmet_C detail parts,
#: data/nfl2k5_modern_helmets/geometry.json): it must stay the near-black ear-hole texel, or the modern vents vanish.
DETAIL_TEXEL = (70, 220)
#: Where the six painted 2004 vents sit on the Revolution atlas (texels, generous): 4 crown crescents and 2 rear slits.
VENT_BOXES = ((28, 100, 64, 128), (66, 106, 100, 130), (66, 124, 100, 148), (28, 128, 64, 156),
              (98, 86, 128, 118), (98, 138, 128, 170))


def rows():
    return kf.helmets_b81()["textures"]


def run_texels(row):
    """Every (x, y) a row repaints."""
    out = set()
    for op in row["ops"]:
        for y, x0, colours in op["rows"]:
            for i in range(len(colours) // 6):
                out.add((x0 + i, y))
    return out


class Document(unittest.TestCase):
    def test_schema_rows_and_pins(self):
        document = kf.helmets_b81()
        self.assertEqual(document["schema"], kf.SCHEMA)
        self.assertTrue(document["source"] and document["method"])
        seen = set()
        for row in document["textures"]:
            key = (row["selector"], row["chunk"])
            self.assertNotIn(key, seen)
            seen.add(key)
            self.assertEqual(row["kind"], "txtr")
            self.assertEqual(row["chunk"], dict(hc.CHUNKS, splayer=51)[row["texture"]])
            self.assertEqual(row["size"][:2], [256, 128] if row["texture"] == "splayer" else [256, 256])
            self.assertGreaterEqual(row["size"][2], 1)
            self.assertEqual(len(row["before_sha256"]), 64)
            self.assertEqual(len(row["after_sha256"]), 64)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertGreater(row["length"], 32)
            self.assertGreater(row["resource_size"], row["offset"] + row["length"] - 1)
            self.assertTrue(row["note"])
            self.assertEqual([op["op"] for op in row["ops"]], ["runs"])
            self.assertNotIn("color", row["ops"][0])          # the compile must ask the palette for nothing new
            if row["texture"] == "splayer":
                # the patch brings colours the atlas palette only has nearby, so a few texels end as they were
                self.assertTrue(0 < row["texels"] <= len(run_texels(row)))
            else:
                self.assertEqual(row["texels"], len(run_texels(row)))

    def test_every_revolution_helmet_of_the_95_kits_is_cleaned_on_both_sides(self):
        revolution = [r for r in rows() if r["texture"] == "helmet02"]
        selectors = {r["selector"] for r in revolution}
        self.assertEqual(len(revolution), 190)
        self.assertEqual(len({s[:2] for s in selectors}), 32)
        for selector in selectors:
            other = selector[:2] + ("A" if selector[2] == "H" else "H") + selector[3:]
            self.assertIn(other, selectors, selector)

    def test_runs_stay_inside_the_texture_and_are_whole_colours(self):
        for row in rows():
            height = row["size"][1]
            for y, x0, colours in row["ops"][0]["rows"]:
                self.assertEqual(len(colours) % 6, 0)
                self.assertGreater(len(colours), 0)
                bytes.fromhex(colours)
                self.assertTrue(0 <= y < height and 0 <= x0 and x0 + len(colours) // 6 <= 256, (row["selector"], y, x0))

    def test_the_far_away_atlas_rows_are_the_carolina_blue_alternate_helmet_patch(self):
        far = [r for r in rows() if r["texture"] == "splayer"]
        self.assertEqual(sorted(r["selector"] for r in far), ["04A2", "04H2"])
        for row in far:
            for x, y in run_texels(row):
                self.assertTrue(37 <= x < 128 and 90 <= y < 128, (row["selector"], x, y))    # the helmet patch only
        self.assertEqual(far[0]["ops"], far[1]["ops"])

    def test_carolina_home_keeps_its_silver_far_away_helmet(self):
        # the sideline pass used to paint the home atlas's helmet black with the pants; now only the pants
        sideline = json.loads((ROOT / "data/nfl2k5_sideline_2026.json").read_text(encoding="utf-8"))
        row = [r for r in sideline["kits"] if r["selector"] == "04H0"]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["parts"], ["pants"])
        self.assertEqual(sorted(row[0]["field"]), ["pants"])

    def test_the_modern_shell_detail_texel_is_never_repainted(self):
        x, y = DETAIL_TEXEL
        guard = {(x + dx, y + dy) for dx in range(-4, 5) for dy in range(-4, 5)}     # the texel and its mip parents
        for row in rows():
            if row["texture"] == "helmet02":
                self.assertFalse(run_texels(row) & guard, row["selector"])

    def test_every_revolution_row_repaints_the_painted_vents(self):
        for row in rows():
            if row["texture"] != "helmet02":
                continue
            texels = run_texels(row)
            hit = sum(any(x0 <= x < x1 and y0 <= y < y1 for x, y in texels) for x0, y0, x1, y1 in VENT_BOXES)
            # a logo or a design may cover a vent's place; at least four of the six are always there to remove
            self.assertGreaterEqual(hit, 4, row["selector"])

    def test_the_standard_shell_rows_are_the_reviewed_old_logo_pieces(self):
        standard = sorted({r["selector"][:2] + "_" + r["selector"][3:] for r in rows() if r["texture"] == "helmet00"})
        self.assertEqual(standard, ["00_0", "02_0", "02_2", "02_3", "09_0", "24_10", "24_9"])
        for row in rows():
            if row["texture"] == "helmet00":
                self.assertLess(row["texels"], 900, row["selector"])      # pieces beside a logo, never a shell

    def test_home_and_away_of_one_kit_share_their_runs_except_carolina_style_0(self):
        by = {(r["selector"], r["texture"]): r for r in rows()}
        for (selector, texture), row in by.items():
            if selector[2] != "H" or texture == "splayer":
                continue
            away = by.get((selector[:2] + "A" + selector[3:], texture))
            self.assertIsNotNone(away, selector)
            if selector == "04H0":
                continue      # the league project now gives 04H0 the silver helmet; both sides end the same anyway
            self.assertEqual(row["ops"], away["ops"], selector)


class RunsOperation(unittest.TestCase):
    def test_runs_set_their_texels_and_nothing_else(self):
        rgba = np.zeros((8, 8, 4), np.uint8)
        rgba[..., :3] = (10, 20, 30)
        rgba[..., 3] = 200
        ops = [dict(op="runs", rows=[[2, 1, "010203040506"], [5, 6, "FFFEFD"]])]
        out, scope = kf.paint(rgba, ops)
        self.assertEqual(out[2, 1].tolist(), [1, 2, 3, 200])
        self.assertEqual(out[2, 2].tolist(), [4, 5, 6, 200])
        self.assertEqual(out[5, 6].tolist(), [255, 254, 253, 200])
        self.assertEqual(int(scope.sum()), 3)
        untouched = np.ones((8, 8), bool)
        untouched[2, 1:3] = untouched[5, 6] = False
        self.assertTrue((out[untouched] == rgba[untouched]).all())
        self.assertEqual(kf.art_colours([op for op in ops if "color" in op]), [])

    def test_a_run_outside_the_texture_is_refused(self):
        rgba = np.zeros((8, 8, 4), np.uint8)
        for bad in ([8, 0, "010203"], [0, 7, "010203040506"], [0, 0, ""], [0, 0, "0102"]):
            with self.assertRaises(Exception):
                kf.paint(rgba, [dict(op="runs", rows=[bad])])


class AuthoringHelpers(unittest.TestCase):
    def test_runs_of_lists_each_changed_run_once(self):
        before = np.zeros((6, 10, 4), np.uint8)
        after = before.copy()
        after[1, 2:5, :3] = (9, 8, 7)
        after[1, 7, :3] = (1, 1, 1)
        after[4, 0, :3] = (5, 5, 5)
        got = hc.runs_of(before, after)
        self.assertEqual(got, [[1, 2, "090807090807090807"], [1, 7, "010101"], [4, 0, "050505"]])
        painted, _scope = kf.paint(before, [dict(op="runs", rows=got)])
        self.assertTrue((painted == after).all())

    def test_snap_takes_the_nearest_entry_of_the_texel_alpha(self):
        palette = np.array([[0, 0, 0, 255], [100, 100, 100, 255], [104, 100, 100, 160], [200, 0, 0, 160]], np.int64)
        colours = np.array([[103, 100, 100], [103, 100, 100], [190, 10, 10]])
        alphas = np.array([255, 160, 160])
        self.assertEqual(hc.snap(colours, alphas, palette).tolist(), [[100, 100, 100], [104, 100, 100], [200, 0, 0]])


class BuildHook(unittest.TestCase):
    def test_the_pass_is_an_optional_labelled_step_after_the_last_kit_readers(self):
        self.assertIn("kit_fixes_2026_b81", mod_build.OPTIONAL_STEPS)
        self.assertIn("kit_fixes_2026_b81", build_steps.STEP_LABELS)
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = source.index("apply_helmets_b81(target)")
        for earlier in ("kit_fixes.apply_sideline(target)", "moment_kits.apply_to_image(target",
                        "classic.apply_to_image(target, retail)", "scans.apply_to_image(target, scans_source)"):
            self.assertLess(source.index(earlier), at, earlier)

    def test_the_document_is_shipped_and_pinned(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_kit_fixes_2026_b81.json", allow)
        self.assertEqual(kf.DATA_B81, ROOT / "data/nfl2k5_kit_fixes_2026_b81.json")


@unittest.skipUnless(DISC.is_file(), "the released SOFTDRINK v0.9 disc is not on this machine")
class RealDisc(unittest.TestCase):
    """Offline real-disc proof: the rows against the kit packages of the released build (read only)."""

    @classmethod
    def setUpClass(cls):
        cls.state = hc.states(DISC)

    def test_the_released_disc_is_waiting_for_every_row_but_the_new_carolina_art(self):
        # 04H0, 04H2 and 04A2 are pinned to the helmet art the league project gives them in beta 81 (the silver helmet
        # by default, the black helmet on the blue alternate), which the v0.9 disc does not have yet
        other = sorted((r["selector"], r["texture"]) for r in self.state["rows"])
        self.assertEqual(other, [("04A2", "helmet02"), ("04H0", "helmet02"), ("04H2", "helmet02")])
        self.assertEqual(self.state["after"], 0)
        self.assertEqual(self.state["absent"], 0)
        self.assertEqual(self.state["before"], len(rows()) - 3)

    def test_sample_rows_compile_to_their_pins_and_change_only_their_texels(self):
        wanted = [("02H0", "helmet02"), ("02H2", "helmet00"), ("09A0", "helmet02"), ("12H5", "helmet02"), ("06H0", "helmet02")]
        kits = hc.read_kits(DISC, sorted({s for s, _t in wanted}))
        by = {(r["selector"], r["texture"]): r for r in rows()}
        for selector, texture in wanted:
            row = by[(selector, texture)]
            raw = kits[selector]
            chunk = kf._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            self.assertEqual(hc.sha(span), row["before_sha256"], selector)
            new, detail = kf.compile_texture(span, row)
            self.assertEqual(hc.sha(new), row["after_sha256"], selector)
            self.assertEqual(detail["palette_slots_added"], [])
            self.assertEqual(detail["merged_twin_slots"], 0)
            before, palette_before, _t = hc.level0(span)
            after, palette_after, _t = hc.level0(new)
            self.assertTrue((palette_before == palette_after).all(), selector)
            self.assertTrue((before[..., 3] == after[..., 3]).all(), selector)
            changed = {(int(x), int(y)) for y, x in np.argwhere((before != after).any(axis=2))}
            self.assertEqual(changed, run_texels(row) & changed)
            self.assertEqual(len(changed), row["texels"], selector)
            # the replay on the cleaned package is a no-op
            again = raw[:chunk.offset] + new + raw[chunk.end_offset:]
            replacements, receipt = kf.compile_resource(selector, again, strict=False,
                                                        document=dict(textures=[r for r in rows() if r["selector"] == selector
                                                                                and r["texture"] == texture]))
            self.assertEqual((replacements, receipt["state"]), ([], "applied"))


if __name__ == "__main__":
    unittest.main()
