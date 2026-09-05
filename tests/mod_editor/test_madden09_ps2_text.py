"""The Madden 09 (PS2) text lane, on a synthetic disc only. No game data."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games.contract import Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, text_lane  # noqa: E402

#: The strings the synthetic disc's TEXT member carries.  They are invented in
#: the module under test, which is the point: nothing here comes from a game.
SYNTHETIC_STRINGS = containers.SYNTHETIC_TEXT_LINES


class SplitAndMeasureTests(unittest.TestCase):
    def test_a_text_member_splits_on_nul_and_drops_the_padding(self) -> None:
        payload = containers.synthetic_text_member(SYNTHETIC_STRINGS) + b"\x00\x00\x00"
        self.assertEqual(text_lane.split_strings(payload), SYNTHETIC_STRINGS)

    def test_eight_bit_bytes_decode_rather_than_raising(self) -> None:
        payload = b"caf\xe9\x00na\xefve\x00"
        self.assertEqual(text_lane.split_strings(payload), ("caf\xe9", "na\xefve"))

    def test_measure_reports_counts_and_a_digest_and_no_strings(self) -> None:
        stats = text_lane.measure(containers.synthetic_text_member(SYNTHETIC_STRINGS))
        self.assertEqual(stats["strings"], 3)
        self.assertEqual(stats["longest_string"], max(len(s) for s in SYNTHETIC_STRINGS))
        self.assertEqual(len(stats["sha256"]), 64)
        blob = json.dumps(stats)
        for text in SYNTHETIC_STRINGS:
            self.assertNotIn(text, blob)


class TextLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-text-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = text_lane.TextLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_the_lane_is_read_only_and_lands_on_the_menus_page(self) -> None:
        self.assertTrue(self.lane.read_only)
        self.assertEqual(self.lane.page, "menus")
        self.assertEqual(self.lane.surface, "menus")

    def test_the_catalogue_finds_the_synthetic_text_member(self) -> None:
        self.assertEqual(self.catalogue.document["text_members"], 1)
        self.assertEqual(self.catalogue.document["strings"], 3)
        self.assertEqual(len(self.catalogue.targets), 1)
        self.assertEqual(self.catalogue.targets[0].raw["container"],
                         containers.TEAM_DATABASE_CONTAINER)

    def test_the_catalogue_carries_no_string_from_the_source(self) -> None:
        blob = json.dumps(self.catalogue.document, default=dict)
        for text in SYNTHETIC_STRINGS:
            self.assertNotIn(text, blob, "a catalogue must never carry payload")

    def test_a_preview_reads_the_strings_from_the_source_it_is_given(self) -> None:
        target = self.catalogue.targets[0]
        self.assertEqual(self.lane.preview(self.source, target), SYNTHETIC_STRINGS)

    def test_a_preview_elides_an_over_long_string(self) -> None:
        long_one = "X" * (text_lane.PREVIEW_WIDTH + 40)
        member = containers.synthetic_text_member((long_one,))
        source = self.work / "long.iso"
        from mod_editor.games._formats import ea_terf
        import ps2_iso9660 as iso_lib

        source.write_bytes(iso_lib.build_synthetic_iso(
            files=[(b"SYSTEM.CNF;1",
                    f"BOOT2 = cdrom0:\\{containers.BOOT_FILE};1\r\n".encode("ascii")),
                   (f"{containers.BOOT_FILE};1".encode("ascii"), b"\x7fELF" + bytes(64))],
            sub_name=b"DATA",
            sub_files=[(f"{containers.TEAM_DATABASE_CONTAINER};1".encode("ascii"),
                        ea_terf.build_terf([member], chunk="DATA"))],
        ))
        catalogue = self.lane.build_catalogue(source)
        preview = self.lane.preview(source, catalogue.targets[0])
        self.assertEqual(len(preview[0]), text_lane.PREVIEW_WIDTH)
        self.assertTrue(preview[0].endswith("…"))

    def test_a_preview_of_a_target_that_names_nothing_refuses(self) -> None:
        from mod_editor.games.contract import Target

        bogus = Target(key="nowhere", label="nowhere", detail="", budget="", raw={})
        with self.assertRaises(Refusal) as caught:
            self.lane.preview(self.source, bogus)
        self.assertIn("rebuild the catalogue", str(caught.exception))

    def test_the_three_writing_methods_refuse(self) -> None:
        recipe = self.lane.compose_recipe(())
        for call in (
            lambda: self.lane.plan(self.source, recipe, self.catalogue),
            lambda: self.lane.build(self.source, self.work / "never.out", recipe, self.catalogue),
            lambda: self.lane.verify(self.source, self.work / "never.out", None),
        ):
            with self.assertRaises(Refusal) as caught:
                call()
            self.assertIn("LZH1 encoder", str(caught.exception))
        self.assertFalse((self.work / "never.out").exists())

    def test_every_field_is_read_only(self) -> None:
        for target in self.catalogue.targets:
            self.assertTrue(all(field.read_only for field in target.fields))


if __name__ == "__main__":
    unittest.main()
