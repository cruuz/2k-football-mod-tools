"""b81-uniforms R54: the far-player atlas (kit chunk 51 ``splayer``) follows the 2026 uniform pass.

data/nfl2k5_sideline_2026_b81u.json (written by tools/b81_uniforms/far_atlas.py) and the optional build step
sideline_2026_b81u: the document's shape and pins, that each row's guard is the uniform pass's own finished texture,
that the runs stay inside the islands of the parts they mirror, the build hook's place, and (with the released v0.9 disc
on this machine, B81_UNIFORM_DISC) the Studio compile of the worst kits against the real packages, and the guard that
leaves a kit whose field texture is a user's own art.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_uniform_pass as up  # noqa: E402
from b81_uniforms import far_atlas as fa  # noqa: E402
from mod_editor.core import build_steps, mod_build, nfl2k5_kit_fixes_2026 as kf  # noqa: E402

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
#: the kits the survey and the R2F measures found stalest (pants stripes, hems, the Saints gold pants, the 60 patch)
WORST = ("26A4", "14A0", "15A0", "15H0", "25H0", "27H0", "17A8", "06H5", "02A3", "17A3", "23A0", "09H9")
CHUNK = {"torso": 1, "pants": 2, "sleeve": 3}
#: kits whose atlas the sideline step composes differently since the released v0.9 (b3c82862f, Carolina 04H0 pants)
SIDELINE_COMPOSED_SINCE_V09 = {"04H0"}


def rows():
    return kf.sideline_b81u()["textures"]


def run_texels(row):
    out = set()
    for op in row["ops"]:
        if op["op"] == "runs":
            for y, x0, colours in op["rows"]:
                out.update((x0 + i, y) for i in range(len(colours) // 6))
        elif op["op"] == "texels":
            out.update((x, y) for x, y in op["points"])
    return out


class Document(unittest.TestCase):
    def test_schema_rows_and_pins(self):
        document = kf.sideline_b81u()
        self.assertEqual(document["schema"], kf.SCHEMA)
        self.assertGreater(len(rows()), 100)
        seen = set()
        for row in rows():
            self.assertNotIn(row["selector"], seen)
            seen.add(row["selector"])
            self.assertEqual((row["chunk"], row["kind"], row["texture"]), (51, "txtr", "splayer"), row["selector"])
            self.assertEqual(row["size"][:2], [256, 128], row["selector"])
            for key in ("before_sha256", "after_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertTrue(row["parts"] and set(row["parts"]) <= set(CHUNK), row["selector"])
            self.assertEqual(sorted(row["donors"]), sorted(str(CHUNK[p]) for p in row["parts"]), row["selector"])
            self.assertGreater(row["texels"], 0)

    def test_each_guard_is_the_uniform_pass_finished_texture(self):
        # the atlas mirrors the corrected texture: a row is only written while that very texture is on the disc, and
        # an art change to the uniform pass that is not carried into the atlas fails here
        finished = {(r["selector"], r["chunk"]): r["after_sha256"] for r in kf.uniforms_b81()["textures"]}
        for row in rows():
            for chunk, pin in row["donors"].items():
                self.assertEqual(finished.get((row["selector"], int(chunk))), pin, (row["selector"], chunk))

    def test_every_changed_kit_is_a_row_or_named(self):
        document = kf.sideline_b81u()
        changed = {r["selector"] for r in kf.uniforms_b81()["textures"] if r["chunk"] in (1, 2, 3)}
        named = set(document.get("unchanged", [])) | set(document.get("left", {}))
        self.assertEqual(sorted(changed - {r["selector"] for r in rows()} - named), [])
        for selector, why in document.get("left", {}).items():
            self.assertTrue(isinstance(why, str) and why, selector)

    def test_runs_stay_inside_the_islands_of_the_parts_they_mirror(self):
        for row in rows():
            allowed = np.zeros((128, 256), bool)
            for part in row["parts"]:
                x0, y0, x1, y1 = fa.ISLAND[part]
                allowed[y0:y1, x0:x1] = True
            for x, y in run_texels(row):
                self.assertTrue(allowed[y, x], (row["selector"], x, y))

    def test_the_helmet_island_is_never_touched(self):
        for row in rows():
            for x, y in run_texels(row):
                self.assertFalse(37 <= x < 128 and 90 <= y < 128, (row["selector"], x, y))


class BuildHook(unittest.TestCase):
    def test_an_optional_labelled_step_after_the_uniform_pass_numbers(self):
        self.assertIn("sideline_2026_b81u", mod_build.OPTIONAL_STEPS)
        self.assertEqual(build_steps.STEP_LABELS["sideline_2026_b81u"], "the 2026 far-player uniforms")
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        kits = source.index("apply_uniforms_b81(target)")
        digits = source.index("apply_digits_b81(target)")
        atlas = source.index("apply_sideline_b81u(target)")
        relief = source.index("apply_relief_b81u(target")
        self.assertLess(kits, atlas)
        self.assertLess(digits, atlas)
        self.assertLess(atlas, relief)
        self.assertLess(source.index("kit_fixes.apply_sideline(target)"), atlas)

    def test_the_document_is_shipped(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_sideline_2026_b81u.json", allow)
        self.assertEqual(kf.DATA_SIDELINE_B81U, ROOT / "data/nfl2k5_sideline_2026_b81u.json")


class AuthoringHelpers(unittest.TestCase):
    def test_the_atlas_is_a_pass_texture(self):
        self.assertEqual(up.chunk_of("splayer"), (51, "txtr"))

    def test_reduce_is_an_area_average(self):
        img = np.zeros((4, 8))
        img[:, 4:] = 8.0
        self.assertTrue(np.allclose(fa.reduce(img, (0, 0, 8, 4), (2, 1)), [[0.0, 8.0]]))
        self.assertTrue(np.allclose(fa.reduce(img, (2, 0, 6, 4), (1, 1)), [[4.0]]))

    def test_an_unchanged_part_is_kept_and_a_stripe_is_laid_where_the_texture_changed(self):
        atlas = np.full((128, 256, 4), 255, np.uint8)
        old = np.full((256, 512, 4), 255, np.uint8)
        new = old.copy()
        new[:, 120:150, :3] = (200, 30, 40)        # a red stripe on the left leg
        want, info = fa.part_change(atlas, old, new, "pants", "retail")
        self.assertIsNotNone(want)
        # native columns 120-150 land on atlas columns 45-59 (0.467 x - 10.8, ATLAS_SURVEY.md)
        self.assertTrue(want[40, 50, 0] > 150 and want[40, 50, 1] < 120)   # the stripe reads red there
        self.assertTrue((want[40, :40, :] == 255).all())          # columns far from it keep their bytes
        belt = atlas.copy()
        belt[:fa.BELT_ROWS, :, :3] = 20                            # a dark waistband the texture does not have
        kept, _info = fa.part_change(belt, old, new, "pants", "retail")
        self.assertTrue((kept[:fa.BELT_ROWS] == 20).all())        # the renderer's belt is never painted over
        self.assertTrue(want[2, 50, 0] > 150 and want[2, 50, 1] < 120)   # a stripe through plain belt rows follows
        same, info = fa.part_change(atlas, old, old, "pants", "retail")
        self.assertTrue((same == 255).all())


@unittest.skipUnless(DISC.is_file(), "the released SOFTDRINK v0.9 disc is not on this machine")
class RealDisc(unittest.TestCase):
    """Offline real-disc proof on the stalest kits: the released package, then the helmet cleanup and the uniform pass
    as a build runs them, then this document: the compile gives the pinned atlas, only the listed texels move, and a
    user's own field texture leaves the atlas alone."""

    @classmethod
    def setUpClass(cls):
        mine = {r["selector"]: r for r in rows()}
        cls.selectors = [s for s in WORST if s in mine]
        cls.rows = mine
        cls.kits = up.read_kits(DISC, cls.selectors)

    def built(self, selector):
        raw = self.kits[selector]
        for document in (kf.helmets_b81(), kf.uniforms_b81()):
            if any(r["selector"] == selector for r in document["textures"]):
                replacements, _ = kf.compile_resource(selector, raw, strict=False, document=document)
                out = bytearray(raw)
                for offset, data in replacements:
                    out[offset:offset + len(data)] = data
                raw = bytes(out)
        return raw

    def test_every_before_pin_is_the_atlas_a_build_holds(self):
        # the atlas a v0.10 build holds when the step runs: the released one, after the helmet cleanup's own atlas rows
        # (Carolina's blue alternates). 04H0's atlas is composed by the sideline step (changed since v0.9, b3c82862f), so
        # its pin was read from a Studio build (the private uniform disc), not derivable from the released package here.
        cleanup = dict(schema=kf.SCHEMA, textures=[r for r in kf.helmets_b81()["textures"] if r["chunk"] == 51])
        kits = up.read_kits(DISC, sorted(self.rows))
        checked = 0
        for selector, row in sorted(self.rows.items()):
            raw = kits[selector]
            if any(r["selector"] == selector for r in cleanup["textures"]):
                replacements, _ = kf.compile_resource(selector, raw, strict=True, document=dict(
                    cleanup, textures=[r for r in cleanup["textures"] if r["selector"] == selector]))
                for offset, data in replacements:
                    raw = raw[:offset] + data + raw[offset + len(data):]
            chunk = kf._chunk_for(raw, 51)
            if selector in SIDELINE_COMPOSED_SINCE_V09:
                continue
            self.assertEqual(kf.sha(raw[chunk.offset:chunk.end_offset]), row["before_sha256"], selector)
            checked += 1
        self.assertEqual(checked, len(self.rows) - len(SIDELINE_COMPOSED_SINCE_V09 & set(self.rows)))

    def test_the_worst_kits_are_rows(self):
        self.assertEqual(self.selectors, list(WORST))

    def test_the_compile_gives_the_pin_and_moves_only_the_listed_texels(self):
        for selector in self.selectors:
            row = self.rows[selector]
            raw = self.built(selector)
            document = dict(schema=kf.SCHEMA, textures=[row])
            replacements, receipt = kf.compile_resource(selector, raw, strict=True, document=document)
            self.assertEqual(len(replacements), 1, selector)
            new = replacements[0][1]
            self.assertEqual(kf.sha(new), row["after_sha256"], selector)
            chunk = kf._chunk_for(raw, 51)
            before = up.level0(raw[chunk.offset:chunk.end_offset], "txtr")[0]
            after = up.level0(new, "txtr")[0]
            moved = {(int(x), int(y)) for y, x in zip(*np.nonzero((before != after).any(axis=2)))}
            self.assertTrue(moved <= run_texels(row), selector)

    def test_a_users_own_field_texture_keeps_the_atlas(self):
        selector = self.selectors[0]
        row = self.rows[selector]
        raw = self.built(selector)
        index = int(sorted(row["donors"])[0])
        released = self.kits[selector]
        chunk = kf._chunk_for(raw, index)
        own = raw[:chunk.offset] + released[chunk.offset:chunk.end_offset] + raw[chunk.end_offset:]
        self.assertNotEqual(own, raw)
        replacements, receipt = kf.compile_resource(selector, own, strict=False,
                                                    document=dict(schema=kf.SCHEMA, textures=[row]))
        self.assertEqual(replacements, [])
        self.assertEqual(receipt["skipped_textures"], [51])
        with self.assertRaises(ValueError):
            kf.compile_resource(selector, own, strict=True, document=dict(schema=kf.SCHEMA, textures=[row]))


if __name__ == "__main__":
    unittest.main()
