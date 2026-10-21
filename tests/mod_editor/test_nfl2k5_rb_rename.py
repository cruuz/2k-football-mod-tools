"""b777-rb2: Halfback / HB display text reads Running Back / RB (Noah 10/20, "everywhere").

The rename is text only: in-place UTF-16 rewrites inside each retail slot, no pointer or position
code changes. The retail executable and packs are used when they are on this machine (digests and
decoded text only; no retail bytes are stored in the repo).
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_rb_rename as rb  # noqa: E402
from mod_editor.core import nfl2k5_modern_positions as modern  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                                 "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
XBE = EXTRACTION / "default.xbe"
PACK0 = EXTRACTION / "vc_53450030" / "0"


class SiteTableTests(unittest.TestCase):
    def test_every_replacement_fits_its_slot_and_is_display_text(self) -> None:
        sites = rb.string_sites()
        self.assertEqual(len(sites), len(rb.STRING_SITES) + 4 + 15)
        for label, _va, before, after in sites:
            self.assertEqual(len(before), len(after), label)
            text_before = before.decode("utf-16le").split("\0")[0]
            text_after = after.decode("utf-16le").split("\0")[0]
            self.assertTrue("HB" in text_before or "Halfback" in text_before, label)
            self.assertNotIn("HB", text_after)
            self.assertNotIn("Halfback", text_after)
            self.assertNotIn("FB", text_before.replace("HB", ""))       # never a fullback string
        self.assertEqual(len({va for _l, va, _b, _a in sites}), len(sites))
        self.assertEqual(rb.slot_record_text(False), modern.slot_text("RB", "RUNNING BACK"))

    def test_scene_sites_keep_their_length(self) -> None:
        for label, _e, _n, _c, size, at, before, after in rb.SCENE_SITES:
            self.assertEqual(len(before), len(after), label)
            self.assertLess(at + len(before), size)
            self.assertIn("HB".encode("utf-16le"), before)
            self.assertIn("RB".encode("utf-16le"), after)

    def test_build_option_is_on_in_every_softdrink_preset_and_off_by_default(self) -> None:
        self.assertFalse(mod_build.BuildPlan("in.iso", "out.iso").rb_rename)
        softdrink = [name for name in mod_build.PRESETS if name.startswith("softdrink")]
        self.assertTrue(softdrink)
        for name in softdrink:
            self.assertTrue(mod_build.PRESETS[name]["rb_rename"], name)
        self.assertTrue(mod_build.BuildPlan("in.iso", "out.iso", rb_rename=True).wants_xbe_patch())
        self.assertTrue(mod_build.availability()["rb_rename"])


@unittest.skipUnless(XBE.is_file(), "retail default.xbe not on this machine")
class RetailExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = rb.apply(cls.retail)

    def test_retail_to_applied_and_replay_is_a_no_op(self) -> None:
        self.assertEqual(rb.status(self.retail), "retail")
        self.assertEqual(rb.status(self.patched), "applied")
        self.assertEqual(len(self.patched), len(self.retail))
        again, receipt = rb.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_decoded_text_before_and_after(self) -> None:
        before = {row["label"]: row["text"] for row in rb.decode(self.retail)}
        after = {row["label"]: row["text"] for row in rb.decode(self.patched)}
        self.assertEqual(before["abbrev_enum_tables"], "HB")
        self.assertEqual(after["abbrev_enum_tables"], "RB")
        self.assertEqual(after["package_legend"], "|SQUARE| SUB RB")
        self.assertEqual(after["share_format"], "RB: %d%%")
        self.assertEqual(after["style_balanced"], "Balanced RB")
        self.assertEqual(before["long_singular_0"], "Halfback")
        self.assertEqual(after["long_singular_0"], "RB")
        self.assertEqual(before["long_plural_14"], "Halfbacks")
        self.assertEqual(after["long_plural_14"], "RBs")
        self.assertEqual(before["depth_slot_offense_1"], "HB / HALF BACK")
        self.assertEqual(after["depth_slot_offense_1"], "RB / RUNNING BACK")

    def test_only_site_bytes_and_section_digests_change(self) -> None:
        allowed = set()
        for _label, off, before, _after in rb._sites(self.retail):
            allowed.update(range(off, off + len(before)))
        for section in rb._sections(self.retail):
            if section.index in self.receipt["sections_repinned"]:
                allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b]
        self.assertTrue(changed)
        self.assertEqual([i for i in changed if i not in allowed], [])

    def test_position_codes_and_pool_fields_are_untouched(self) -> None:
        for unit, rows in modern.read_depth_chart_units(self.retail).items():
            after = modern.read_depth_chart_units(self.patched)[unit]
            self.assertEqual([(r["position"], r["chain"]) for r in rows], [(r["position"], r["chain"]) for r in after])
        record = modern.read_record(self.patched, rb.SLOT_UNIT, rb.SLOT_INDEX)
        self.assertEqual((record["position"], record["chain"]), rb.SLOT_POOL)
        # every pointer that reached an HB literal still reaches the same address
        for _label, va, _before, _after in rb.string_sites():
            needle = struct.pack("<I", va)
            self.assertEqual(self.retail.count(needle), self.patched.count(needle))

    def test_foreign_bytes_are_refused(self) -> None:
        bad = bytearray(self.retail)
        off = rb._offset(self.retail, rb.PLURAL_SITES[3])
        bad[off:off + 4] = "XX".encode("utf-16le")
        self.assertEqual(rb.status(bytes(bad)), "foreign")
        with self.assertRaises(rb.RbRenameError):
            rb.apply(bytes(bad))
        half = bytearray(self.retail)
        off = rb._offset(self.retail, rb.STRING_SITES[1][1])
        half[off:off + 4] = "RB".encode("utf-16le")
        self.assertEqual(rb.status(bytes(half)), "foreign")         # partial is never "applied"

    def test_companion_owners_accept_the_renamed_labels(self) -> None:
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_depth_chart_rows as rows
        mode.check_context(self.patched, [])                          # MyPlayer HUD label: RB is a known label
        self.assertEqual(rows.status(self.patched), rows.status(self.retail))
        bad = bytearray(self.patched)
        off = rb._offset(self.patched, 0x00E69C18)
        bad[off:off + 4] = "XB".encode("utf-16le")
        with self.assertRaises(Exception):
            mode.check_context(bytes(bad), [])

    def test_build_order_through_pools_and_special_rows(self) -> None:
        """The first pass renames the retail table; the SPECIAL relocation copies RB; every owner stays applied."""
        from mod_editor.core import (nfl2k5_throw_tuning as tt, nfl2k5_position_pools as pools,
                                     nfl2k5_depth_chart_rows as rows, nfl2k5_edge_rename as edge)
        x, _ = tt._apply_all(self.retail, None, catch_slider=False, arc_table=False, edge_rename=True,
                             scheme_labels=True, rb_rename=True)
        x, _ = pools.apply(x, roster_has_olb=True)
        x, _ = tt._apply_all(x, None, catch_slider=False, arc_table=False, depth_chart_rows=True)
        x, _ = pools.apply(x, roster_has_olb=False)
        self.assertEqual(modern.layout_table(x), modern.SPECIAL_TABLE_VA)
        self.assertEqual((rb.status(x), rows.status(x), pools.status(x), modern.status(x), edge.status(x)),
                         ("applied",) * 5)
        record = modern.read_record(x, rb.SLOT_UNIT, rb.SLOT_INDEX)
        self.assertEqual((record["abbreviation"], record["long_name"], record["position"], record["chain"]),
                         ("RB", "RUNNING BACK", 7, 0))
        y, receipt = rb.apply(x)                                       # a rebuild over the result replays
        self.assertEqual((y, receipt["changed_bytes"]), (x, 0))


@unittest.skipUnless(PACK0.is_file(), "retail index pack not on this machine")
class SceneTests(unittest.TestCase):
    def test_scenes_rename_on_a_copy_and_compose_with_the_team_needs_rewrite(self) -> None:
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            shutil.copyfile(PACK0, copy / "0")
            self.assertEqual(rb.image_status(copy), "retail")
            with bump._Image.open(copy, writable=False) as image:
                segments = {label: seg for label, _e, _c, seg in rb._scene_segments(image, bump._parsed_index(image))}
            team = segments["team_needs_label"]
            # position_pools' EDGE/LB overview rewrite and the RB label commute
            a, _ = rb.apply_scene("team_needs_label", pools.apply_team_needs_scene(team)[0])
            b, receipt = pools.apply_team_needs_scene(rb.apply_scene("team_needs_label", team)[0])
            self.assertEqual(a, b)
            self.assertTrue(rb.scene_state("team_needs_label", b) == "applied" and not receipt["already_applied"])
            receipt = rb.apply_image(copy)
            self.assertEqual(receipt["changed_bytes"], 2)
            self.assertEqual(rb.image_status(copy), "applied")
            self.assertEqual(rb.apply_image(copy)["changed_bytes"], 0)
            self.assertEqual(rb.scene_state("team_needs_label", team[:-1]), "foreign")


if __name__ == "__main__":
    unittest.main()
