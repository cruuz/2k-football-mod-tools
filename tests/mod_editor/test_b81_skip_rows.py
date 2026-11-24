"""b81 skip rows (11/24): the art rows the release row check (tools/b81_release_row_check.py) found skipped on the standard
build of 11/21, one test per cause. Noah's rule: every bug found gets fixed; a row meant not to apply says so.

Causes:
  * a row pinned against its input's order: an earlier step (the swoosh step, sw1) writes the texture first, so the row's
    before pin must be that step's output (07H0's sleeve; the 26H0, 26A0, 09H9, 09A9 sleeves were re-pinned with it);
  * a donor pinned against its input's order: the 26H4 sleeve read 26H0's sleeve as a donor at the released pin, but sw1
    rewrites 26H0's sleeve first (the alternates round replaced that row with one that reads no donor);
  * far-player atlas rows pinned to a field or an atlas the build does not hold: 07H0 and 26H4 (their field textures were
    the two skipped sleeves) and the Lions 09H9/09A9 (sideline_2026 composes their atlas from sw1's sleeve first);
  * a row meant not to apply: the Chiefs ku1 helmet00 remap. The league project's cleaned helmet already carries its
    colours, and remapping it again would move the red a second time. The row pins that helmet as an equivalent
    finished texture (``after_equivalent_sha256``), so the build records it finished, not skipped."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import b81_uniform_pass as up  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402

REHEARSAL = Path(os.environ.get("B81_REHEARSAL_DISC",
                                "/media/noah/Storage/2K5-project/b81-rehearsal/build/full-20261121-155155/full.xiso.iso"))
#: the kit-fix documents in build order (mod_build's art steps), the uniform pass last
ORDER = ("kit_fixes_2026", "kit_fixes_2026_alts", "kit_fixes_2026_uf3", "kit_fixes_2026_sea1", "kit_fixes_2026_ov1",
         "kit_fixes_2026_ku1", "kit_fixes_2026_sw1", "kit_fixes_2026_names", "kit_fixes_2026_b81", "kit_fixes_2026_b81u")
CHIEFS_HELMET00 = (("13H0", 11), ("13A0", 11))
FAR_KITS = ("07H0", "09A9", "09H9", "26H4")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def doc(step):
    return json.loads((ROOT / "data" / f"nfl2k5_{step}.json").read_text(encoding="utf-8"))


def rows(step):
    return {(r["selector"], r["chunk"]): r for r in doc(step)["textures"]}


class SleeveInputOrder(unittest.TestCase):
    def test_a_later_row_on_a_sleeve_the_swoosh_step_writes_starts_from_its_output(self):
        sw1 = rows("kit_fixes_2026_sw1")
        later = [(step, key, row) for step in ORDER[ORDER.index("kit_fixes_2026_sw1") + 1:]
                 for key, row in rows(step).items() if key in sw1]
        self.assertTrue(later)
        for step, key, row in later:
            self.assertEqual(row["before_sha256"], sw1[key]["after_sha256"], (step, key))
        self.assertTrue({("07H0", 3), ("26H0", 3), ("26A0", 3), ("09H9", 3), ("09A9", 3)} <= {k for _s, k, _r in later})


class DonorInputOrder(unittest.TestCase):
    def test_no_donor_is_pinned_to_a_texture_an_earlier_step_rewrites(self):
        last = {}
        for step in ORDER:
            for key, row in rows(step).items():
                for donor, pin in (row.get("donors") or {}).items():
                    other, _, chunk = str(donor).rpartition(":")
                    if not other or other.startswith(("retail", "logo")):
                        continue
                    writer = last.get((other, int(chunk)))
                    if writer is not None:
                        self.assertEqual(pin, writer[1]["after_sha256"], (step, key, donor, writer[0]))
            for key, row in rows(step).items():
                last[key] = (step, row)

    def test_the_26h4_sleeve_reads_no_donor(self):
        self.assertFalse(rows("kit_fixes_2026_b81u")[("26H4", 3)].get("donors"))


class FarAtlasInputs(unittest.TestCase):
    def far(self):
        return {r["selector"]: r for r in doc("sideline_2026_b81u")["kits"]}

    def test_the_fields_are_the_uniform_pass_results(self):
        kits = rows("kit_fixes_2026_b81u")
        for sel in FAR_KITS:
            row = self.far()[sel]
            for part, pin in row["field_sha256"].items():
                self.assertEqual(pin, kits[(sel, {"pants": 2, "sleeve": 3}[part])]["after_sha256"], (sel, part))

    @unittest.skipUnless(REHEARSAL.is_file(), "a beta 81 build of bbf2235f7 (B81_REHEARSAL_DISC)")
    def test_the_atlas_is_the_one_the_far_step_finds(self):
        # the 11/21 build left these four atlases as the far step found them (its rows skipped), so it holds their input
        packages = up.read_kits(REHEARSAL, list(FAR_KITS))
        for sel in FAR_KITS:
            raw = packages[sel]
            chunk = kf._chunk_for(raw, 51)
            self.assertEqual(sha(raw[chunk.offset:chunk.end_offset]), self.far()[sel]["before_sha256"], sel)


class ChiefsHelmetAlreadyFinished(unittest.TestCase):
    def test_the_rows_pin_the_finished_helmet_and_say_why(self):
        ku1 = rows("kit_fixes_2026_ku1")
        for key in CHIEFS_HELMET00:
            row = ku1[key]
            self.assertEqual(len(row["after_equivalent_sha256"]), 1, key)
            self.assertIn("b81art_helmet00", row["note"])
            self.assertIn("a second time", row["note"])
        self.assertEqual(ku1[CHIEFS_HELMET00[0]]["after_equivalent_sha256"], ku1[CHIEFS_HELMET00[1]]["after_equivalent_sha256"])

    @unittest.skipUnless(REHEARSAL.is_file(), "a beta 81 build of bbf2235f7 (B81_REHEARSAL_DISC)")
    def test_the_build_holds_that_helmet_in_the_rows_colours_and_records_it_finished(self):
        document = doc("kit_fixes_2026_ku1")
        ku1 = rows("kit_fixes_2026_ku1")
        packages = up.read_kits(REHEARSAL, ["13H0", "13A0"])
        for sel, chunk in CHIEFS_HELMET00:
            row = ku1[(sel, chunk)]
            raw = packages[sel]
            part = kf._chunk_for(raw, chunk)
            span = raw[part.offset:part.end_offset]
            self.assertEqual([sha(span)], row["after_equivalent_sha256"], sel)
            # its red is the row's own output red (#C0142F -> #CC242A), and remapping it again moves that red once more
            rgba = kf.texture_rgba(span)
            colours, counts = __import__("numpy").unique(rgba[..., :3].reshape(-1, 3), axis=0, return_counts=True)
            self.assertEqual("#%02X%02X%02X" % tuple(int(v) for v in colours[counts.argmax()]), "#CC242A", sel)
            again, _detail = kf.compile_texture(span, row)
            self.assertNotEqual(sha(again), sha(span), sel)
            # the Studio's own record for the kit: texture 11 finished, not skipped
            _replacements, record = kf.compile_resource(sel, raw, strict=False, document=document)
            self.assertNotIn(chunk, record["skipped_textures"], sel)


if __name__ == "__main__":
    unittest.main()
