"""b81-uniforms R54 (small, retail-free form): the far-player atlas pants and sleeves follow the 2026 uniform pass.

data/nfl2k5_sideline_2026_b81u.json is a second rule list of the shipped sideline kind (tools/b81_uniforms/far_compose.py):
per kit the parts, the field colours, the pants crop the island shows and SHA-256 pins; the optional step
sideline_2026_b81u composes the pieces at build time from the kit's own finished field texture (the sideline step's
compose). Model tests as the shipped sideline tests do, the document's shape and the guard that no atlas texel or
picture is stored in it, its pins against the uniform pass, the build hook, and (with the released v0.9 disc on this
machine, B81_UNIFORM_DISC) the compose of real kits giving the pinned bytes and leaving a user's own field art alone.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_uniform_pass as up  # noqa: E402
from b81_uniforms import far_compose as fc  # noqa: E402
from mod_editor.core import build_steps, mod_build, nfl2k5_kit_fixes_2026 as kf  # noqa: E402

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
ROW_KEYS = {"selector", "parts", "field", "compose", "before_sha256", "after_sha256", "field_sha256"}
#: kits whose atlas the build holds differently from the released v0.9 one (the sideline step composes Carolina 04H0's
#: pants since b3c82862f; the helmet cleanup writes 04A2/04H2's atlas): their before pins come from a Studio build
SINCE_V09 = {"04H0", "04A2", "04H2"}
#: sleeve changes below the sideline step's own palette-noise rule (a swoosh recolour of a few atlas texels)
SETTLED = {("00A6", "sleeve"), ("00H6", "sleeve"), ("11A3", "sleeve"), ("11H3", "sleeve"), ("17A3", "sleeve")}
#: the stalest pants and sleeves (the survey's worst pants, the Saints, Bengals and Buccaneers)
WORST = ("26A4", "14A0", "15A0", "15H0", "25H0", "27H0", "17H8", "06H5", "03A0", "17H0")


def rows():
    return kf.sideline_b81u()["kits"]


def texture(colour, size=(256, 512), stripe=None):
    image = np.zeros(size + (4,), np.uint8)
    image[..., 3] = 255
    image[..., :3] = colour
    if stripe is not None:
        x0, x1, c = stripe
        image[:, x0:x1, :3] = c
    return image


def atlas(pants=(14, 75, 203)):
    image = np.zeros((128, 256, 4), np.uint8)
    image[..., 3] = 255
    image[..., :3] = (80, 40, 130)
    image[0:90, 0:128, :3] = pants
    image[100:128, 190:256, :3] = (80, 40, 130)
    return image


class Document(unittest.TestCase):
    def test_rules_and_pins_only(self):
        # the retail-free guard: a rule list, never a picture, a difference or atlas texels; put one back and this fails
        document = json.loads(kf.DATA_SIDELINE_B81U.read_text(encoding="utf-8"))
        self.assertEqual(set(document), {"schema", "note", "kits"})
        self.assertEqual(document["schema"], kf.SIDELINE_SCHEMA)
        self.assertLess(kf.DATA_SIDELINE_B81U.stat().st_size, 64 * 1024)
        for row in document["kits"]:
            self.assertEqual(set(row), ROW_KEYS, row["selector"])
            self.assertTrue(row["parts"] and set(row["parts"]) <= {"pants", "sleeve"}, row["selector"])
            self.assertEqual(sorted(row["compose"]), sorted(row["parts"]), row["selector"])
            for part, op in row["compose"].items():
                self.assertLessEqual(set(op), {"crop"}, row["selector"])
                if "crop" in op:
                    self.assertTrue(len(op["crop"]) == 4 and all(isinstance(v, int) for v in op["crop"]))
            for colour in row["field"].values():
                self.assertEqual(len(colour), 3)
        self.assertEqual(len(kf._sideline_rows(document)), len(document["kits"]))

    def test_an_unpinned_row_or_a_bad_rule_is_refused(self):
        import tempfile
        from unittest.mock import patch
        document = kf.sideline_b81u()
        good = document["kits"][0]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "doc.json"
            unpinned = dict(good)
            unpinned.pop("after_sha256")
            path.write_text(json.dumps(dict(document, kits=[unpinned])), encoding="utf-8")
            with patch.object(kf, "DATA_SIDELINE_B81U", path), self.assertRaises(ValueError):
                kf.sideline_b81u()
        for broken in ({"compose": {p: {"crop": [0, 0, 600, 10]} for p in good["parts"]}},
                       {"before_sha256": "not a hash"},
                       {"field_sha256": {"torso": "0" * 64}}):
            with self.assertRaises(ValueError, msg=str(broken)):
                kf._sideline_rows(dict(document, kits=[dict(good, **broken)]))

    def test_every_changed_pants_and_sleeve_is_a_rule_on_the_finished_texture(self):
        finished = {(r["selector"], r["chunk"]): r["after_sha256"] for r in kf.uniforms_b81()["textures"]}
        changed = {(s, {2: "pants", 3: "sleeve"}[c]) for s, c in finished if c in (2, 3)}
        listed = {(row["selector"], p) for row in rows() for p in row["parts"]}
        # five sleeve swooshes recoloured on islands the sideline step already composed move fewer texels than the step's
        # own palette-noise rule (SIDELINE_SETTLED): the compose leaves them, so they carry no rule
        self.assertEqual(sorted(changed - listed), sorted(SETTLED))
        for row in rows():
            for part, pin in row["field_sha256"].items():
                self.assertEqual(finished[(row["selector"], {"pants": 2, "sleeve": 3}[part])], pin, row["selector"])

    def test_far_atlas_rows_start_from_what_the_helmet_pass_writes(self):
        """b81-retail-free-art round 3: where the helmet pass (data/nfl2k5_kit_fixes_2026_b81.json) writes a kit's far
        atlas (chunk 51: the Carolina far view, now the far_helmet rule), this step's row for that kit is pinned to the
        atlas that pass writes, so the step still composes its far-view pants (it skipped them on the old pins)."""
        helmets = {(r["selector"], r["chunk"]): r for r in kf.helmets_b81()["textures"]}
        rows = {r["selector"]: r for r in kf.sideline_b81u()["kits"]} if hasattr(kf, "sideline_b81u") else \
            {r["selector"]: r for r in json.loads((ROOT / "data/nfl2k5_sideline_2026_b81u.json").read_text())["kits"]}
        far = sorted(sel for (sel, chunk) in helmets if chunk == 51 and sel in rows)
        self.assertEqual(far, ["04A2", "04H2"])
        for sel in far:
            self.assertEqual(rows[sel]["before_sha256"], helmets[(sel, 51)]["after_sha256"], sel)

    def test_no_torso(self):
        self.assertFalse(any("torso" in row["parts"] for row in rows()))


class Compose(unittest.TestCase):
    def test_a_crop_lays_that_part_of_the_field_texture(self):
        alt = atlas()
        alt[30:40, 0:128, :3] = (10, 60, 160)                                    # a darker fold
        pants = texture((255, 255, 255), stripe=(130, 155, (200, 30, 40)))        # the LEFT leg's stripe
        row = {"selector": "99A9", "parts": ["pants"], "field": {"pants": [255, 255, 255]},
               "compose": {"pants": {"crop": list(fc.RETAIL_PANTS_CROP)}}}
        out, changed = kf.sideline_measured_repair(alt, {}, {"pants": np.array([255, 255, 255])}, row,
                                                   {"pants": pants})
        self.assertGreater(changed["pants"], 8000)
        x = int(round((142 - 23) * 128 / (297 - 23)))                            # the stripe's centre in the island
        self.assertGreater(int(out[60, x, 0]), 150)
        self.assertLess(int(out[60, x, 1]), 100)                                  # red where the left stripe is
        self.assertGreater(int(out[60, 10, :3].min()), 225)                       # white fabric
        default = dict(row, compose={"pants": {}})                                # the right-half crop
        out2, _ = kf.sideline_measured_repair(alt, {}, {"pants": np.array([255, 255, 255])}, default,
                                              {"pants": pants})
        self.assertGreater(int(out2[60, x, 1]), 200)                              # no stripe there


class BuildHook(unittest.TestCase):
    def test_an_optional_labelled_step_after_the_uniform_pass_numbers(self):
        self.assertIn("sideline_2026_b81u", mod_build.OPTIONAL_STEPS)
        self.assertEqual(build_steps.STEP_LABELS["sideline_2026_b81u"], "the 2026 far-player uniforms")
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        atlas_at = source.index("apply_sideline_b81u(target)")
        self.assertLess(source.index("apply_uniforms_b81(target)"), atlas_at)
        self.assertLess(source.index("apply_digits_b81(target)"), atlas_at)
        self.assertLess(atlas_at, source.index("apply_relief_b81u(target"))

    def test_the_document_is_shipped(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_sideline_2026_b81u.json", allow)
        self.assertEqual(kf.DATA_SIDELINE_B81U, ROOT / "data/nfl2k5_sideline_2026_b81u.json")


@unittest.skipUnless(DISC.is_file(), "the released SOFTDRINK v0.9 disc is not on this machine")
class RealDisc(unittest.TestCase):
    """Offline real-disc proof: the released package, the helmet cleanup's own atlas rows and the uniform pass as a
    build runs them, then the rule: the compose gives the pinned atlas, and a user's own field texture keeps it."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {row["selector"]: row for row in rows()}
        cls.kits = up.read_kits(DISC, [s for s in WORST if s in cls.rows])
        # b81-retail-free-art: donor kits the uniform pass reads (the Saints sleeve emblem's 24H0 swoosh template)
        cls.donors = up.read_kits(DISC, kf.donor_kits(kf.uniforms_b81()))

    def built(self, selector):
        raw = self.kits[selector]
        cleanup = dict(kf.helmets_b81(), textures=[r for r in kf.helmets_b81()["textures"]
                                                  if r["selector"] == selector and r["chunk"] == 51])
        if cleanup["textures"]:
            reps, _ = kf.compile_resource(selector, raw, strict=True, document=cleanup)
            for off, data in reps:
                raw = raw[:off] + data + raw[off + len(data):]
        return fc.finished(raw, selector, kits=self.donors)

    def test_the_worst_kits_compose_to_their_pins(self):
        for selector in WORST:
            row = self.rows[selector]
            raw = self.built(selector)
            new, receipt, splayer = fc.plan(row, raw)
            self.assertEqual(hashlib.sha256(splayer).hexdigest(), row["before_sha256"], selector)
            self.assertIsNotNone(new, selector)
            self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"], selector)

    def test_a_users_own_field_texture_keeps_the_atlas(self):
        selector = WORST[0]
        row = self.rows[selector]
        raw = self.built(selector)
        own = self.kits[selector]                      # the released pants: not the finished texture the rule pins
        chunk = kf._chunk_for(raw, 2)
        raw = raw[:chunk.offset] + own[chunk.offset:chunk.end_offset] + raw[chunk.end_offset:]
        new, receipt, _ = fc.plan(row, raw)
        self.assertIsNone(new)
        self.assertEqual(receipt["state"], "field_differs")

    def test_a_result_that_is_not_the_pin_is_not_written(self):
        selector = WORST[1]
        row = dict(self.rows[selector], after_sha256="0" * 64)
        new, receipt, _ = fc.plan(row, self.built(selector))
        self.assertIsNone(new)
        self.assertEqual(receipt["state"], "after_differs")


if __name__ == "__main__":
    unittest.main()
