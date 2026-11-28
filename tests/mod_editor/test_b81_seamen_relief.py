"""b81-seamen: the classic Seamen kits' jersey relief.

The owner (2026-11-25, playing the 11/20 private disc): "also seamen have a dolphins bump texture in their jersey, have them
use a cleaner one".

Root cause (PROVED OFFLINE on the 11/20 disc): the classic teams step composes 14h14.iff / 14a14.iff from the 2026
Dolphins kits before the 2026 relief runs, so their bump maps (chunks 45, 46, 47) are byte for byte the Dolphins'
pre-relief maps (the b81u document's 14H0/14A0 ``before`` pins), the 2004 sculpt with the Dolphins chest script raised.
data/nfl2k5_relief_2026_classic.json gives them the 2026 relief with no marks (the b81u base and difference master, no
patch; the pants with every construction box lifted out), through the relief step's own machinery, after the b81u
relief and only with the classic teams on.

The regeneration test needs a built v0.10 disc that holds the Seamen packages (NFL2K5_B81_SEAMEN_DISC) and the retail
disc (NFL2K5_RETAIL_XISO); both are read only.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_relief_2026 as relief  # noqa: E402

DISC = Path(os.environ.get("NFL2K5_B81_SEAMEN_DISC", "") or "missing-NFL2K5_B81_SEAMEN_DISC")
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "") or "missing-NFL2K5_RETAIL_XISO")


class DocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = relief.relief_classic()
        cls.b81u = relief.relief_b81u()

    def test_six_plain_slots_on_the_two_seamen_kits(self):
        rows = self.doc["slots"]
        self.assertEqual([(r["selector"], r["slot"], r["chunk"]) for r in rows],
                         [(s, slot, c) for s in ("14H14", "14A14")
                          for slot, c in (("bump_jersey", 45), ("bump_sleeve", 46), ("bump_pants", 47))])
        self.assertEqual(self.doc["patches"], {})
        for row in rows:
            self.assertIsNone(row["patch"])                   # no raised marks: the Seamen paint none
            self.assertIsNone(row["offset"])
            self.assertIsNone(row["resource_size"])
        for key in ("gauss_kernels", "bases", "masters", "art", "level", "schema"):
            self.assertEqual(self.doc[key], self.b81u[key], key)

    def test_each_slot_starts_from_the_dolphins_pre_relief_map_it_carries(self):
        dolphins = {(r["selector"], r["slot"]): r for r in self.b81u["slots"] if r["selector"] in ("14H0", "14A0")}
        for row in self.doc["slots"]:
            donor = {"14H14": "14H0", "14A14": "14A0"}[row["selector"]]
            if row["slot"] == "bump_pants":           # chunk 47 comes from the other side's kit (teal pants at home)
                donor = {"14H0": "14A0", "14A0": "14H0"}[donor]
            ref = dolphins[(donor, row["slot"])]
            self.assertEqual((row["before_sha256"], row["length"]), (ref["before_sha256"], ref["length"]))
            self.assertNotEqual(row["after_sha256"], ref["after_sha256"])     # not the Dolphins' own marks
            if row["slot"] == "bump_pants":
                union = sorted({tuple(b) for s in ("14H0", "14A0") for b in dolphins[(s, "bump_pants")]["worked"]})
                self.assertEqual([tuple(b) for b in row["worked"]], union)

    def test_the_step_runs_after_the_b81u_relief_only_with_the_classic_teams(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        b81u = text.index('_optional(receipt, target, progress, "relief_2026_b81u")')
        classic = text.index('_optional(receipt, target, progress, "relief_2026_classic")')
        self.assertLess(b81u, classic)
        self.assertIn("if plan.classic_teams and plan.historic_teams_quick_game:", text[b81u:classic])
        self.assertIn("relief.apply_relief_classic(", text[classic:classic + 400])
        from mod_editor.core import mod_build
        self.assertIn("relief_2026_classic", mod_build.OPTIONAL_STEPS)


@unittest.skipUnless(DISC.is_file() and RETAIL.is_file(), "a built v0.10 disc with the Seamen kits and the retail disc")
class DiscTests(unittest.TestCase):
    def test_the_document_is_what_the_tool_derives_from_the_disc(self):
        spec = importlib.util.spec_from_file_location("relief_classic", ROOT / "tools/b81_uniforms/relief_classic.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(tool.build(DISC, RETAIL), relief.relief_classic())

    def test_the_seamen_spans_read_before_by_index_whatever_the_layout(self):
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        with bump._Image.open(DISC, writable=False) as image:
            index = bump._parsed_index(image)
            for selector in ("14H14", "14A14"):
                (entry,) = [e for e in index.entries if bump.logical_name_for(e.name_id) == selector + ".IFF"]
                raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
                for row in [r for r in relief.relief_classic()["slots"] if r["selector"] == selector]:
                    state, _chunk, _span = relief.state_of(row, raw)
                    self.assertIn(state, ("before", "after"), (selector, row["slot"]))


if __name__ == "__main__":
    unittest.main()
