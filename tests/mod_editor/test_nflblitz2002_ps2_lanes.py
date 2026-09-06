"""The NFL Blitz 2002 (PS2) lanes, proved on the synthetic disc.  No game data.

Each writer lane: the catalogue lists targets, a known-good edit plans, builds a
NEW image and verifies; the destination keeps the source's length; every member
the receipt did not name stays byte-identical; the index and the archive still
agree; a value that does not fit its span is refused before anything is written.
Each read-only lane catalogues and refuses every write with its one sentence.
Each export lane writes a PNG and its verifier re-decodes it from the source.
"""

from __future__ import annotations

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

from mod_editor.games._formats import blitz_zip  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.nflblitz2002_ps2 import (  # noqa: E402
    GAME, LANES, camera_lane, containers, roster_lane, text_lane, texture_lane,
)


class _Room(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="nflblitz2002-lanes-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def _source(self, lane) -> Path:
        return lane.synthetic_source(self.work)

    def _round_trip(self, lane, edits=None, name="built.iso"):
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        edits = edits if edits is not None else lane.conformance_edits(catalogue)
        recipe = lane.compose_recipe(edits)
        plan = lane.plan(source, recipe, catalogue)
        destination = self.work / name
        receipt = lane.build(source, destination, recipe, catalogue, work_dir=self.work)
        verdict = lane.verify(source, destination, receipt)
        return source, catalogue, plan, destination, receipt, verdict


class ModuleTests(_Room):
    def test_the_module_hosts_every_registered_lane(self) -> None:
        self.assertEqual(len(LANES), 8)
        self.assertEqual({lane.classification for lane in LANES},
                         {"offline-writer-proved", "extract-only", "read-only-mapped"})
        self.assertEqual(GAME.identity.serials, (containers.SERIAL,))
        self.assertEqual(len({lane.lane_id for lane in LANES}), len(LANES))

    def test_every_studio_page_is_answered_by_a_lane_or_a_note(self) -> None:
        from mod_editor.games.contract import PAGE_ORDER, lane_page

        covered = {lane_page(lane) for lane in LANES}
        notes = set(GAME.manifest.page_notes)
        for page_id, _title in PAGE_ORDER:
            if page_id == "build":
                continue                        # the shell's own page
            self.assertTrue(page_id in covered or page_id in notes,
                            f"page {page_id} has neither a lane nor a note")

    def test_the_synthetic_disc_is_never_mistaken_for_retail(self) -> None:
        source = containers.build_synthetic_disc()
        path = self.work / "synthetic.iso"
        path.write_bytes(source)
        identity = GAME.identifier.identify(path)
        self.assertEqual(identity.serial, containers.SERIAL)
        self.assertFalse(identity.retail_executable)

    def test_both_index_shapes_open(self) -> None:
        for shape in (blitz_zip.SHAPE_INLINE, blitz_zip.SHAPE_TABLE):
            path = self.work / f"synthetic-{shape}.iso"
            path.write_bytes(containers.build_synthetic_disc(shape=shape))
            with containers.Disc(path) as disc:
                self.assertEqual(disc.index().shape, shape)
                report = blitz_zip.cross_check(disc.index(), disc.archive())
                self.assertTrue(report["names_match_as_sets"])
                self.assertEqual(report["data_offsets_agree"], len(disc.archive().members))


class TextLaneTests(_Room):
    def test_every_text_lane_writes_a_line_inside_its_span(self) -> None:
        for number, lane in enumerate(text_lane.LANES):
            source, catalogue, plan, destination, receipt, verdict = self._round_trip(
                lane, name=f"text-{number}.iso")
            self.assertTrue(verdict.passed, verdict.summary)
            self.assertTrue(plan.declared_ranges)
            self.assertEqual(destination.stat().st_size, source.stat().st_size)
            self.assertEqual(verdict.document["members_replaced"], 1)
            self.assertEqual(verdict.document["failures"], [])

    def test_the_edit_reaches_the_member_and_only_that_member(self) -> None:
        lane = text_lane.TRIVIA_LANE
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        target = catalogue.targets[0]
        recipe = lane.compose_recipe((Edit(target.key, {"text": "REPLACED"}),))
        destination = self.work / "trivia.iso"
        receipt = lane.build(source, destination, recipe, catalogue)
        self.assertTrue(lane.verify(source, destination, receipt).passed)
        member = str(target.raw["member"])
        with containers.Disc(destination) as after, containers.Disc(source) as before:
            slots = containers.read_line_slots(member, after.member_bytes(member))
            self.assertEqual(slots[int(target.raw["line"])].text, "REPLACED")
            for row in before.archive().members:
                if row.name != member:
                    self.assertEqual(after.archive().member_bytes(row.name),
                                     before.archive().member_bytes(row.name))

    def test_a_line_longer_than_its_span_is_refused_before_anything_is_written(self) -> None:
        lane = text_lane.CROWD_LANE
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        target = catalogue.targets[0]
        problem = lane.check_edit(target, {"text": "x" * 999})
        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn(str(target.raw["span"]), problem)
        recipe = lane.compose_recipe((Edit(target.key, {"text": "x" * 999}),))
        destination = self.work / "never.iso"
        with self.assertRaises(Refusal):
            lane.build(source, destination, recipe, catalogue)
        self.assertFalse(destination.exists())

    def test_a_line_break_and_a_non_latin1_character_are_refused(self) -> None:
        lane = text_lane.CROWD_LANE
        catalogue = lane.build_catalogue(self._source(lane))
        target = catalogue.targets[0]
        self.assertIsNotNone(lane.check_edit(target, {"text": "a\nb"}))
        self.assertIsNotNone(lane.check_edit(target, {"text": "中"}))

    def test_an_empty_recipe_is_refused(self) -> None:
        lane = text_lane.FIELD_LANE
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        with self.assertRaises(Refusal):
            lane.plan(source, lane.compose_recipe(()), catalogue)

    def test_an_existing_destination_is_refused(self) -> None:
        lane = text_lane.FIELD_LANE
        source, catalogue, _plan, destination, _receipt, _verdict = self._round_trip(
            lane, name="exists.iso")
        recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
        with self.assertRaises(Refusal):
            lane.build(source, destination, recipe, catalogue)


class RosterLaneTests(_Room):
    def test_a_name_edit_round_trips_and_the_blocks_still_parse(self) -> None:
        lane = roster_lane.LANE
        source, catalogue, plan, destination, receipt, verdict = self._round_trip(
            lane, name="roster.iso")
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertEqual(destination.stat().st_size, source.stat().st_size)
        with containers.Disc(destination) as after:
            players = containers.read_roster(after.member_bytes(containers.ROSTER_MEMBER))
            self.assertEqual(players[0].first, "Fixture")
            self.assertEqual(players[0].last, "Namefield")
            for player in players:
                self.assertEqual(player.team_byte, player.block)

    def test_the_catalogue_publishes_the_block_arithmetic_and_the_team_cross_check(self) -> None:
        lane = roster_lane.LANE
        document = lane.build_catalogue(self._source(lane)).document
        self.assertEqual(document["block_bytes"], containers.ROSTER_BLOCK_BYTES)
        self.assertEqual(document["records"],
                         document["blocks"] * containers.ROSTER_RECORDS_PER_BLOCK)
        self.assertEqual(document["records_whose_team_byte_equals_their_block"],
                         document["records"])
        self.assertEqual(document["team_crowd_tables"], document["team_logo_dictionaries"])
        self.assertEqual(len(document["numeric_column_census"]), 36)

    def test_a_name_that_does_not_fit_its_field_is_refused(self) -> None:
        lane = roster_lane.LANE
        catalogue = lane.build_catalogue(self._source(lane))
        target = catalogue.targets[0]
        problem = lane.check_edit(target, {"first": "x" * 40})
        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn(str(containers.ROSTER_NAME_BYTES), problem)
        self.assertIsNotNone(lane.check_edit(target, {"last": ""}))
        self.assertIsNotNone(lane.check_edit(target, {"first": "中"}))

    def test_a_roster_that_is_not_a_whole_number_of_blocks_is_refused(self) -> None:
        with self.assertRaises(containers.DiscError) as caught:
            containers.read_roster(bytes(1805))
        self.assertIn("whole number of", str(caught.exception))

    def test_a_block_that_declares_another_record_count_is_refused(self) -> None:
        blob = bytearray(containers.ROSTER_BLOCK_BYTES)
        blob[0] = 17
        with self.assertRaises(containers.DiscError) as caught:
            containers.read_roster(bytes(blob))
        self.assertIn("declares 17 records", str(caught.exception))


class TextureLaneTests(_Room):
    def test_the_inventory_counts_and_refuses_every_write(self) -> None:
        lane = texture_lane.INVENTORY_LANE
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        totals = catalogue.document["totals"]
        self.assertEqual(totals["dictionaries"], 3)
        self.assertEqual(totals["rasters"], totals["decodable"])
        self.assertTrue(catalogue.targets)
        for target in catalogue.targets:
            self.assertTrue(all(field.read_only for field in target.fields))
        with self.assertRaises(Refusal):
            lane.plan(source, {"schema": texture_lane.SCHEMA}, catalogue)
        with self.assertRaises(Refusal):
            lane.build(source, self.work / "never.iso", {}, catalogue)

    def test_an_export_lane_writes_a_png_its_verifier_re_derives(self) -> None:
        for number, lane in enumerate((texture_lane.TEAM_LANE, texture_lane.SCREEN_LANE)):
            source, catalogue, plan, destination, receipt, verdict = self._round_trip(
                lane, name=f"export-{number}.png")
            self.assertTrue(verdict.passed, verdict.summary)
            self.assertTrue(destination.read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(len(receipt.artifacts), 1)
            self.assertEqual(source.read_bytes(), self._source(lane).read_bytes())
            self.assertEqual(receipt.declared_ranges, ())

    def test_a_tampered_export_fails_its_verifier(self) -> None:
        lane = texture_lane.TEAM_LANE
        source, _catalogue, _plan, destination, receipt, verdict = self._round_trip(
            lane, name="tamper.png")
        self.assertTrue(verdict.passed)
        tampered = self.work / "tampered.png"
        blob = bytearray(destination.read_bytes())
        blob[-1] ^= 0xFF
        tampered.write_bytes(bytes(blob))
        self.assertFalse(lane.verify(source, tampered, receipt).passed)

    def test_an_export_lane_offers_no_import(self) -> None:
        lane = texture_lane.SCREEN_LANE
        source = self._source(lane)
        catalogue = lane.build_catalogue(source)
        target = catalogue.targets[0]
        with self.assertRaises(Refusal) as caught:
            lane.encode(source, target, b"\x89PNG")
        self.assertIn("no import is offered", str(caught.exception))
        self.assertIsNotNone(lane.check_edit(target, {"png": b"x"}))

    def test_a_derived_identity_is_published_and_labelled(self) -> None:
        lane = texture_lane.TEAM_LANE
        catalogue = lane.build_catalogue(self._source(lane))
        target = catalogue.targets[0]
        self.assertIsNotNone(lane.replacement_identity(target))
        labels = {field.label for field in target.fields}
        self.assertIn("PCSX2 name (derived)", labels)


class ContainerLaneTests(_Room):
    def test_the_inventory_reads_every_head_it_names(self) -> None:
        lane = camera_lane.LANE
        source = self._source(lane)
        document = lane.build_catalogue(source).document
        self.assertEqual(document["camera_paths"], 1)
        self.assertEqual(document["wiff_members"], 1)
        self.assertEqual(document["clump_members"], 1)
        self.assertEqual(document["refusals"], [])
        with self.assertRaises(Refusal):
            lane.build(source, self.work / "never.iso", {}, lane.build_catalogue(source))

    def test_a_camera_header_whose_arithmetic_fails_is_refused(self) -> None:
        import struct

        bad = containers.CAMERA_MAGIC + struct.pack("<3I", 5, 99, 0) + bytes(32)
        with self.assertRaises(containers.DiscError) as caught:
            camera_lane.read_camera(bad, "bad.cap")
        self.assertIn("declares 99 records", str(caught.exception))

    def test_a_wiff_whose_big_endian_size_is_not_the_member_is_refused(self) -> None:
        import struct

        head = containers.WIFF_MAGIC + struct.pack(">I", 999) + b"WIPS"
        with self.assertRaises(containers.DiscError) as caught:
            camera_lane.read_wiff(head, 40, "bad.wip")
        self.assertIn("is not 40", str(caught.exception))

    def test_a_clump_walk_reports_whether_it_consumed_the_member(self) -> None:
        import struct

        clump = struct.pack("<3I", 0x10, 8, 0x0401FFFF) + bytes(8)
        self.assertTrue(camera_lane.walk_clump(clump, "a.dff")["consumed_whole_member"])
        self.assertFalse(camera_lane.walk_clump(clump + b"\x00" * 3,
                                                "b.dff")["consumed_whole_member"])


if __name__ == "__main__":
    unittest.main()
