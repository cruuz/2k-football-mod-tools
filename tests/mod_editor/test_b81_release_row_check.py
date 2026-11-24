"""Beta 81 release row check (tools/b81_release_row_check.py): the standard full build must apply every kit, glyph and
card row; the check reads the Studio receipt's own skip records. Coordinator 11/24, Noah's fix-every-bug rule."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_release_row_check as check  # noqa: E402

#: The 11/21 head (rehearsal) build's Studio receipt, a private file (b81/env.sh): it applied kit 07H0 of the uniform
#: pass but skipped its sleeve texture, which nothing reported.
REHEARSAL = Path(os.environ.get("NFL2K5_B81_REHEARSAL_RECEIPT", "") or "missing-NFL2K5_B81_REHEARSAL_RECEIPT")


def clean_receipt():
    return {"steps": [
        {"step": "kit_fixes_2026_b81u", "state": "applied", "skipped_kits": [],
         "kits": [{"selector": "07H0", "state": "applied", "skipped_textures": []}]},
        {"step": "sideline_2026_b81u", "state": "applied", "kits": [{"selector": "07H0", "state": "repaired"},
                                                                    {"selector": "09H9", "state": "unchanged"}]},
        {"step": "era_kits", "state": "applied", "kits": [{"selector": "16H11", "state": "composed"}]},
        {"step": "relief_2026_b81u", "state": "applied", "skipped_slots": []},
        {"step": "moment_kits", "state": "applied", "skipped_kits": {}},
        {"step": "menu_helmet_w2026", "state": "partial", "slots": [{"member": "helm_h29_0", "state": "not_applicable"},
                                                                     {"member": "helm_h01_0", "state": "applied"}]},
        {"step": "shared_project", "kept_retail": []},
        {"step": "honors_history", "skipped": 0},
        {"step": "modern_venues_2026", "skipped": ["ATL"]},
    ]}


class Rows(unittest.TestCase):
    def test_a_build_that_applied_every_art_row_passes(self):
        self.assertEqual(check.problems(clean_receipt()), [])

    def test_each_kind_of_skipped_art_row_is_reported(self):
        cases = (
            ("kit_fixes_2026_b81u", lambda s: s["kits"][0]["skipped_textures"].append(3),
             "kit_fixes_2026_b81u: kit 07H0 texture 3 not applied"),
            ("kit_fixes_2026_b81u", lambda s: s["skipped_kits"].append("26H4"), "kit_fixes_2026_b81u: kit 26H4 skipped"),
            ("kit_fixes_2026_b81u", lambda s: s["kits"][0].update(state="other_uniform"),
             "kit_fixes_2026_b81u: kit 07H0 other_uniform"),
            ("sideline_2026_b81u", lambda s: s["kits"][1].update(state="other_atlas"),
             "sideline_2026_b81u: kit 09H9 other_atlas"),
            ("relief_2026_b81u", lambda s: s["skipped_slots"].append({"selector": "24H0", "slot": "jersey"}),
             "relief_2026_b81u: skipped_slot 24H0"),
            ("moment_kits", lambda s: s["skipped_kits"].update({"K14": "other art"}), "moment_kits: kit K14 skipped"),
            ("menu_helmet_w2026", lambda s: s["slots"][1].update(state="other"), "menu_helmet_w2026: slot helm_h01_0 other"),
            ("shared_project", lambda s: s["kept_retail"].append({"asset_id": "unif_h15_0_256", "message": "did not fit"}),
             "shared_project: kept the retail picture for unif_h15_0_256"),
        )
        for name, damage, line in cases:
            with self.subTest(line=line):
                receipt = clean_receipt()
                damage(next(step for step in receipt["steps"] if step["step"] == name))
                self.assertEqual(check.problems(receipt), [line])

    def test_a_left_out_art_step_fails_and_other_steps_skips_do_not_count(self):
        receipt = clean_receipt()
        receipt["left_out"] = [{"step": "glyph_fixes_2026_b81u", "reason": "Foreign glyph texture"},
                               {"step": "modern_fans", "reason": "not art of a kit"}]
        self.assertEqual(check.problems(receipt),
                         ["glyph_fixes_2026_b81u: the whole step was left out (Foreign glyph texture)"])

    def test_the_command_exits_1_on_a_skipped_row_and_0_on_a_clean_build(self):
        with tempfile.TemporaryDirectory() as folder:
            good, bad = Path(folder) / "good.json", Path(folder) / "bad.json"
            good.write_text(json.dumps(clean_receipt()))
            receipt = clean_receipt()
            receipt["steps"][0]["kits"][0]["skipped_textures"] = [3]
            bad.write_text(json.dumps(receipt))
            tool = str(ROOT / "tools/b81_release_row_check.py")
            ok = subprocess.run([sys.executable, "-B", tool, str(good)], capture_output=True, text=True)
            refused = subprocess.run([sys.executable, "-B", tool, str(bad)], capture_output=True, text=True)
        self.assertEqual((ok.returncode, refused.returncode), (0, 1))
        self.assertIn("RELEASE ROW CHECK PASSED", ok.stdout)
        self.assertIn("kit 07H0 texture 3 not applied", refused.stdout)


@unittest.skipUnless(REHEARSAL.is_file(), "private 11/21 rehearsal build receipt absent: NFL2K5_B81_REHEARSAL_RECEIPT")
class TheElevenTwentyOneHeadBuild(unittest.TestCase):
    def test_the_skipped_07H0_sleeve_is_caught(self):
        found = check.problems(json.loads(REHEARSAL.read_text(encoding="utf-8")))
        self.assertIn("kit_fixes_2026_b81u: kit 07H0 texture 3 not applied", found)


if __name__ == "__main__":
    unittest.main()
