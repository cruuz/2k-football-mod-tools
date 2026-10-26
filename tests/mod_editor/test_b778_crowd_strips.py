"""b778 sd5: the stadium crowd's sprite strips keep their retail bytes.

The SOFTDRINK v0.6 author inputs repainted the crowd sprite strips (p001..p006, p011..p016 of the team crowd
packages 513..1192) of five clubs on the strips' linear export; in the game's frame order the paint is a speckle, and
the crowd behind the bench at AT&T Stadium and Highmark Stadium looked pixelated and ragged. tools/b77/
sd5_crowd_strips.py finds those edits in a project and writes the project without them; on a disc it lists every
crowd strip that differs from retail.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools", ROOT / "tools" / "b77"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import sd5_crowd_strips as strips  # noqa: E402

# private images, never shipped: the retail disc and the released SOFTDRINK 2K28 v0.6.1 disc
RETAIL = Path(os.environ.get("B778_RETAIL_ISO", "")) if os.environ.get("B778_RETAIL_ISO") else None
RELEASED = Path(os.environ.get("B778_RELEASED_ISO", "")) if os.environ.get("B778_RELEASED_ISO") else None


def p8(outer, name, png="art.png"):
    return dict(kind="p8_texture", asset_id=f"p8:{outer}:{name}", png=png)


def project(edits):
    from tools import nfl2k5_visual_mod_project as compiler
    return dict(schema=compiler.SCHEMA, purpose="sd5 crowd strips", edits=edits)


class StripEdits(unittest.TestCase):
    def test_every_strip_of_every_crowd_package_is_a_strip_target(self):
        for outer in (513, 520, 852, 853, 1192):
            for name in sorted(strips.STRIP_NAMES):
                self.assertEqual(strips.strip_target(p8(outer, name)), (outer, name))
        self.assertEqual(len(strips.STRIP_NAMES), 12)

    def test_other_textures_of_the_same_packages_are_not(self):
        for name in ("crowdbase", "seat", "coachshirt", "endzone_north_left", "p007", "p010", "p017", "p0011"):
            self.assertIsNone(strips.strip_target(p8(520, name)), name)

    def test_strip_names_outside_the_crowd_packages_are_not(self):
        for outer in (512, 1193, 3136, 1):
            self.assertIsNone(strips.strip_target(p8(outer, "p001")), outer)

    def test_other_kinds_and_malformed_ids_are_not(self):
        self.assertIsNone(strips.strip_target(dict(kind="team_identity", asset_id="p8:520:p001")))
        for asset_id in ("p8:520", "p8:x20:p001", "x8:520:p001", "p8:520:p001:extra", ""):
            self.assertIsNone(strips.strip_target(dict(kind="p8_texture", asset_id=asset_id)), asset_id)
        self.assertIsNone(strips.strip_target("p8:520:p001"))

    def test_the_drop_keeps_every_other_edit_in_order(self):
        keep = [dict(kind="team_identity", team_index=3), p8(520, "coachshirt"), p8(520, "endzone_south_left"),
                p8(3136, "pad_north"), p8(1193, "p001")]
        drop = [p8(520, "p001"), p8(706, "p016"), p8(961, "p011")]
        edits = [keep[0], drop[0], keep[1], drop[1], keep[2], keep[3], drop[2], keep[4]]
        document = project(edits)
        before = list(document["edits"])
        self.assertEqual(strips.strip_edits(document), drop)
        fixed = strips.without_strip_edits(document)
        self.assertEqual(fixed["edits"], keep)
        self.assertEqual({k: v for k, v in fixed.items() if k != "edits"},
                         {k: v for k, v in document.items() if k != "edits"})
        self.assertEqual(document["edits"], before, "the input document is not changed")
        self.assertEqual(strips.without_strip_edits(fixed), fixed)

    def test_the_project_command_writes_a_project_the_compiler_reads(self):
        from tools import nfl2k5_visual_mod_project as compiler
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / "in.json", Path(td) / "out.json"
            src.write_bytes(compiler.canonical_json(project([p8(520, "p001"), p8(3136, "pad_north")])))
            self.assertEqual(strips.main(["project", str(src), "--out", str(out)]), 0)
            self.assertEqual(out.read_bytes(), compiler.canonical_json(project([p8(3136, "pad_north")])))
            with self.assertRaises(SystemExit):
                strips.main(["project", str(src), "--out", str(out)])


@unittest.skipUnless(RETAIL is not None and RETAIL.is_file() and RELEASED is not None and RELEASED.is_file(),
                     "needs the retail and v0.6.1 images (B778_RETAIL_ISO, B778_RELEASED_ISO)")
class ReleasedDisc(unittest.TestCase):
    def test_the_released_disc_carries_the_five_clubs_repainted_strips(self):
        found = strips.changed_strips(RELEASED, RETAIL)
        self.assertEqual(len(found), 240)
        codes = {(outer - 513) % 85 for outer, _name in found}
        self.assertEqual(codes, {3, 7, 23, 24, 25})          # BUF, DAL, LAR, LAC, SF
        self.assertEqual(strips.changed_strips(RETAIL, RETAIL), [])


if __name__ == "__main__":
    unittest.main()
