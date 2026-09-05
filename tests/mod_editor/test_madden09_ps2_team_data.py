"""The Madden 09 (PS2) team-database lane, on a synthetic disc only.

The databases here are built by :func:`team_data.synthetic_database` out of the
EA TDB format's own rules; the table and field names are chosen to look like
the ones a real disc uses, and every value is a counting ramp.  No game data.
"""

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

from mod_editor.games._formats import ea_tdb, ea_terf  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, team_data  # noqa: E402


class SyntheticDatabaseTests(unittest.TestCase):
    def test_the_fixture_round_trips_through_the_reader(self) -> None:
        database = ea_tdb.parse_tdb(team_data.synthetic_database())
        self.assertEqual([table.name for table in database.tables], ["TEAM", "PLAY"])
        team = database.table("TEAM")
        self.assertEqual(team.current_records, 2)
        self.assertEqual(database.value(team, 0, "TGID"), 1)
        self.assertEqual(database.value(team, 1, "TWIN"), -4,
                         "a signed field must come back negative")
        self.assertEqual(database.value(team, 0, "TDNA"), "SYNTHETIC-A")
        play = database.table("PLAY")
        self.assertEqual(play.current_records, 4)
        self.assertEqual(database.value(play, 3, "PGID"), 16387)

    def test_the_fixture_carries_correct_checksums(self) -> None:
        """A fixture with stale checksums would not test a writer that keeps them."""

        self.assertEqual(ea_tdb.verify_crcs(team_data.synthetic_database()), [])


class KeyTests(unittest.TestCase):
    def test_a_row_key_round_trips(self) -> None:
        key = team_data.row_key("/DATA/DB_TEAMS.DAT", 12, "PLAY", 34)
        self.assertEqual(team_data.parse_row_key(key),
                         ("/DATA/DB_TEAMS.DAT", 12, "PLAY", 34))

    def test_a_schema_target_is_not_a_row(self) -> None:
        with self.assertRaises(Refusal) as caught:
            team_data.parse_row_key("table:/DATA/DB_TEAMS.DAT#0:PLAY")
        self.assertIn("read-only", str(caught.exception))

    def test_a_malformed_row_key_names_the_spelling(self) -> None:
        with self.assertRaises(Refusal) as caught:
            team_data.parse_row_key("row:nonsense")
        self.assertIn("<container>#<member>", str(caught.exception))


class FieldShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = ea_tdb.parse_tdb(team_data.synthetic_database())

    def test_a_text_budget_leaves_room_for_the_terminator(self) -> None:
        field = self.database.table("PLAY").field("PFNA")
        self.assertEqual(field.bit_width // 8, 11)
        self.assertEqual(team_data.text_budget(field), 10)

    def test_a_rating_is_bounded_by_the_scale_not_the_bit_width(self) -> None:
        field = self.database.table("PLAY").field("POVR")
        self.assertEqual((1 << field.bit_width) - 1, 127)
        self.assertEqual(team_data.number_bound(field, team_data.RATING_MAX), 99)

    def test_a_field_with_no_scale_is_bounded_by_its_own_width(self) -> None:
        field = self.database.table("PLAY").field("PAGE")
        self.assertEqual(team_data.number_bound(field, None), 63)

    def test_only_the_listed_fields_are_offered(self) -> None:
        shape = team_data.fields_for(self.database.table("PLAY"))
        self.assertEqual([item.key for item in shape],
                         ["PFNA", "PLNA", "PJEN", "PAGE", "POVR", "PSPD", "PAWR"])
        self.assertNotIn("PGID", [item.key for item in shape],
                         "PGID is not on the offered list and must not be drawn")
        self.assertNotIn("PWGT", [item.key for item in shape])

    def test_the_offered_shape_is_shared_between_rows_of_one_table(self) -> None:
        """Twelve thousand rows must not carry twelve thousand copies."""

        lane = team_data.TeamDataLane()
        work = Path(tempfile.mkdtemp(prefix="madden09-shape-")).resolve()
        self.addCleanup(shutil.rmtree, work, True)
        catalogue = lane.build_catalogue(lane.synthetic_source(work))
        rows = [t for t in catalogue.targets if t.key.startswith(team_data.ROW_PREFIX)
                and ":PLAY:" in t.key]
        self.assertGreater(len(rows), 1)
        self.assertIs(rows[0].fields, rows[1].fields)


class TeamDataLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-teamdata-")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = team_data.TeamDataLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.player = next(t for t in self.catalogue.targets
                           if t.key.startswith(team_data.ROW_PREFIX) and ":PLAY:" in t.key)
        self.team = next(t for t in self.catalogue.targets
                         if t.key.startswith(team_data.ROW_PREFIX) and ":TEAM:" in t.key)

    # -- shape ---------------------------------------------------------

    def test_the_lane_writes_and_lands_on_the_rosters_page(self) -> None:
        self.assertFalse(self.lane.read_only)
        self.assertEqual(self.lane.page, "rosters")
        self.assertEqual(self.lane.surface, "players_rosters")
        self.assertEqual(self.lane.classification, "offline-writer-proved")
        self.assertTrue(self.lane.fixed_allocation)

    def test_the_catalogue_finds_the_database_its_tables_and_its_rows(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["databases"], 1)
        self.assertEqual(document["tables"], 2)
        self.assertEqual(document["records"], 6)
        self.assertEqual(document["editable_rows_listed"], 6)
        keys = [target.key for target in self.catalogue.targets]
        self.assertTrue(any(key.startswith("database:") for key in keys))
        self.assertTrue(any(key.endswith(":TEAM") for key in keys))
        self.assertTrue(any(key.endswith(":PLAY") for key in keys))

    def test_a_table_target_carries_field_names_and_no_record_values(self) -> None:
        table = next(t for t in self.catalogue.targets if t.key.endswith(":TEAM"))
        names = [field["name"] for field in table.raw["fields"]]
        self.assertEqual(names, ["TGID", "TDNA", "TLNA", "TSNA", "TMNC", "TWIN"])
        blob = json.dumps(self.catalogue.document, default=dict)
        self.assertNotIn("SYNTHETIC-A", blob,
                         "a record's contents must never reach a catalogue document")

    def test_a_row_target_carries_the_values_it_offers_to_edit(self) -> None:
        self.assertEqual(self.player.raw["values"]["PFNA"], "Synth")
        self.assertEqual(self.player.raw["table"], "PLAY")
        self.assertEqual(self.team.raw["values"]["TSNA"], "SYN")

    def test_a_schema_target_still_offers_no_edit(self) -> None:
        table = next(t for t in self.catalogue.targets if t.key.startswith("table:"))
        self.assertTrue(all(field.read_only for field in table.fields))
        self.assertIn("not a row", self.lane.check_edit(table, {"PFNA": "X"}))

    def test_a_container_the_disc_does_not_carry_is_recorded_as_skipped(self) -> None:
        skipped = self.catalogue.document["skipped"]
        self.assertIn(containers.TEMPLATE_CONTAINER, skipped)
        self.assertIn(containers.STREAM_DATABASE_FILE, skipped)

    def test_a_database_this_reader_cannot_open_becomes_a_note_not_a_crash(self) -> None:
        row = team_data.TeamDataLane._database_row("/DATA/BROKEN.DAT", 3, b"DB" + bytes(6))
        self.assertEqual(row["tables"], [])
        self.assertTrue(row["note"], "an unreadable database must say why")

    def test_the_document_carries_no_payload(self) -> None:
        from mod_editor.games.conformance import contains_payload

        self.assertFalse(contains_payload(
            json.loads(json.dumps(self.catalogue.document, default=dict))))

    # -- check_edit ----------------------------------------------------

    def test_a_good_edit_is_accepted(self) -> None:
        self.assertIsNone(self.lane.check_edit(
            self.player, {"PFNA": "Kit", "PJEN": 7, "POVR": 88}))

    def test_a_field_this_lane_does_not_write_is_refused_by_name(self) -> None:
        problem = self.lane.check_edit(self.player, {"PGID": 5})
        self.assertIn("PGID is not a field this lane writes", problem)

    def test_a_name_over_its_budget_is_refused_with_the_length(self) -> None:
        problem = self.lane.check_edit(self.player, {"PFNA": "X" * 11})
        self.assertIn("the field holds 10", problem)

    def test_a_rating_over_the_scale_is_refused_with_the_range(self) -> None:
        problem = self.lane.check_edit(self.player, {"POVR": 100})
        self.assertIn("takes 0 to 99", problem)

    def test_a_rating_below_zero_that_is_not_the_keep_value_is_refused(self) -> None:
        self.assertIn("outside", self.lane.check_edit(self.player, {"POVR": -2}))

    def test_the_keep_value_leaves_a_number_alone(self) -> None:
        self.assertIsNone(self.lane.check_edit(
            self.player, {"POVR": team_data.KEEP_NUMBER, "PJEN": 3}))

    def test_a_row_where_nothing_changes_is_refused(self) -> None:
        values = {key: self.player.raw["values"][key] for key in ("PFNA", "POVR")}
        self.assertIn("Nothing in this row would change",
                      self.lane.check_edit(self.player, values))

    def test_text_outside_the_encoding_is_refused(self) -> None:
        self.assertIn("latin-1", self.lane.check_edit(self.player, {"PFNA": "中"}))

    def test_a_number_handed_text_is_refused(self) -> None:
        self.assertIn("whole number", self.lane.check_edit(self.player, {"POVR": "88"}))

    def test_a_recipe_drops_the_keep_values(self) -> None:
        recipe = self.lane.compose_recipe(
            (Edit(self.player.key, {"PJEN": 9, "POVR": team_data.KEEP_NUMBER, "PFNA": ""}),))
        self.assertEqual(recipe["edits"][0]["values"], {"PJEN": 9})
        self.assertEqual(recipe["schema"], team_data.RECIPE_SCHEMA)

    # -- plan / build / verify -----------------------------------------

    def _built(self, edits=None):
        edits = edits or self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        destination = self.work / "built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        return recipe, destination, receipt

    def test_a_plan_declares_ranges_and_writes_nothing(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        before = self.source.read_bytes()
        plan = self.lane.plan(self.source, recipe, self.catalogue)
        self.assertTrue(plan.declared_ranges)
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_plan_for_an_unknown_target_refuses(self) -> None:
        recipe = self.lane.compose_recipe((Edit("row:/DATA/DB_TEAMS.DAT#0:PLAY:99",
                                                {"POVR": 50}),))
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, recipe, self.catalogue)

    def test_a_build_writes_a_new_image_of_the_same_size_and_verifies(self) -> None:
        _recipe, destination, receipt = self._built()
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

    def test_the_written_values_read_back_through_the_plain_reader(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        member = containers.load_container(
            image, containers.TEAM_DATABASE_CONTAINER).member(0)
        database = ea_tdb.parse_tdb(member)
        index = int(self.player.key.rsplit(":", 1)[1])
        self.assertEqual(database.value("PLAY", index, "PFNA"), "Kit")
        self.assertEqual(database.value("PLAY", index, "PJEN"), 7)
        self.assertEqual(database.value("PLAY", index, "POVR"), 88)
        self.assertEqual(database.value("TEAM", 0, "TDNA"), "Testers")

    def test_the_destination_database_still_checksums(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        member = containers.load_container(
            image, containers.TEAM_DATABASE_CONTAINER).member(0)
        self.assertEqual(ea_tdb.verify_crcs(member), [])

    def test_every_other_value_in_the_database_is_untouched(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        after = ea_tdb.parse_tdb(containers.load_container(
            image, containers.TEAM_DATABASE_CONTAINER).member(0))
        before = ea_tdb.parse_tdb(team_data.synthetic_database())
        self.assertEqual(after.row("PLAY", 1), before.row("PLAY", 1))
        self.assertEqual(after.row("TEAM", 1), before.row("TEAM", 1))
        edited = after.row("PLAY", 0)
        self.assertEqual(edited["PGID"], before.row("PLAY", 0)["PGID"])
        self.assertEqual(edited["PWGT"], before.row("PLAY", 0)["PWGT"])
        self.assertEqual(edited["PLNA"], before.row("PLAY", 0)["PLNA"])

    def test_a_build_leaves_the_source_alone(self) -> None:
        before = self.source.read_bytes()
        self._built()
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_build_refuses_an_existing_destination(self) -> None:
        _recipe, destination, _receipt = self._built()
        digest = destination.read_bytes()
        with self.assertRaises(Refusal) as caught:
            self._built()
        self.assertIn("already exists", str(caught.exception))
        self.assertEqual(destination.read_bytes(), digest)

    def test_a_build_refuses_the_source_as_its_destination(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.source, recipe, self.catalogue)
        self.assertIn("another name", str(caught.exception))

    def test_a_recipe_of_another_schema_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, {"schema": "something/v1", "edits": [{}]},
                           self.catalogue)
        self.assertIn(team_data.RECIPE_SCHEMA, str(caught.exception))

    def test_an_empty_recipe_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, {"schema": team_data.RECIPE_SCHEMA, "edits": []},
                           self.catalogue)

    # -- the verifier has to be able to fail ---------------------------

    def test_the_verifier_catches_a_byte_flipped_outside_the_declared_ranges(self) -> None:
        _recipe, destination, receipt = self._built()
        ranges = [(item.start, item.length) for item in receipt.declared_ranges]
        offset = destination.stat().st_size - 1
        while any(start <= offset < start + length for start, length in ranges):
            offset -= 1
        tampered = self.work / "tampered.iso"
        raw = bytearray(destination.read_bytes())
        raw[offset] ^= 0xFF
        tampered.write_bytes(bytes(raw))
        verdict = self.lane.verify(self.source, tampered, receipt)
        self.assertFalse(verdict.passed, verdict.summary)

    def test_the_verifier_catches_a_record_changed_behind_the_receipts_back(self) -> None:
        """A change inside the declared ISO extent but outside the edited fields."""

        _recipe, destination, receipt = self._built()
        image = containers.open_disc(destination)
        entry = next(item for item in containers.data_files(image)
                     if item.name == containers.TEAM_DATABASE_CONTAINER)
        original = containers.read_file(image, entry)
        member = ea_terf.parse_terf(original, allow_size_mismatch=True).member(0)
        sneaky = ea_tdb.set_value(ea_tdb.parse_tdb(member), "PLAY", 1, "POVR", 12)
        rebuilt = ea_terf.rewrite_member(original, 0, sneaky)
        raw = bytearray(destination.read_bytes())
        start = entry.lba * 2048
        raw[start:start + len(rebuilt)] = rebuilt
        tampered = self.work / "sneaky.iso"
        tampered.write_bytes(bytes(raw))
        verdict = self.lane.verify(self.source, tampered, receipt)
        self.assertFalse(verdict.passed, verdict.summary)
        self.assertIn(containers.TEAM_DATABASE_CONTAINER, verdict.summary)

    def test_the_verifier_catches_a_stale_checksum(self) -> None:
        _recipe, destination, receipt = self._built()
        image = containers.open_disc(destination)
        entry = next(item for item in containers.data_files(image)
                     if item.name == containers.TEAM_DATABASE_CONTAINER)
        original = containers.read_file(image, entry)
        member = ea_terf.parse_terf(original, allow_size_mismatch=True).member(0)
        stale = ea_tdb.set_value(ea_tdb.parse_tdb(member), "PLAY", 1, "POVR", 12,
                                 recompute=False)
        rebuilt = ea_terf.rewrite_member(original, 0, stale)
        raw = bytearray(destination.read_bytes())
        start = entry.lba * 2048
        raw[start:start + len(rebuilt)] = rebuilt
        tampered = self.work / "stale.iso"
        tampered.write_bytes(bytes(raw))
        verdict = self.lane.verify(self.source, tampered, receipt)
        self.assertFalse(verdict.passed, verdict.summary)

    def test_a_receipt_with_no_iso_report_is_refused_rather_than_believed(self) -> None:
        _recipe, destination, _receipt = self._built()
        with self.assertRaises(Refusal):
            team_data.verify_build(self.source, destination, {"edits": []})


if __name__ == "__main__":
    unittest.main()
