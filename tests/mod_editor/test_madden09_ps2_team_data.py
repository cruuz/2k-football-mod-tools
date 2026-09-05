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

from mod_editor.games._formats import ea_tdb  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402
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


class TeamDataLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-teamdata-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = team_data.TeamDataLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_the_lane_is_read_only_and_lands_on_the_rosters_page(self) -> None:
        self.assertTrue(self.lane.read_only)
        self.assertEqual(self.lane.page, "rosters")
        self.assertEqual(self.lane.surface, "players_rosters")
        self.assertEqual(self.lane.classification, "read-only-mapped")

    def test_the_catalogue_finds_the_database_and_both_its_tables(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["databases"], 1)
        self.assertEqual(document["tables"], 2)
        self.assertEqual(document["records"], 6)
        keys = [target.key for target in self.catalogue.targets]
        self.assertTrue(any(key.startswith("database:") for key in keys))
        self.assertTrue(any(key.endswith(":TEAM") for key in keys))
        self.assertTrue(any(key.endswith(":PLAY") for key in keys))

    def test_a_table_target_carries_field_names_and_no_record_values(self) -> None:
        table = next(t for t in self.catalogue.targets if t.key.endswith(":TEAM"))
        names = [field["name"] for field in table.raw["fields"]]
        self.assertEqual(names, ["TGID", "TDNA", "TWIN"])
        blob = json.dumps(self.catalogue.document, default=dict)
        self.assertNotIn("SYNTHETIC-A", blob,
                         "a record's contents must never reach a catalogue")

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

        self.assertFalse(contains_payload(json.loads(json.dumps(self.catalogue.document, default=dict))))

    def test_the_three_writing_methods_refuse_and_name_what_is_missing(self) -> None:
        recipe = self.lane.compose_recipe(())
        for call in (
            lambda: self.lane.plan(self.source, recipe, self.catalogue),
            lambda: self.lane.build(self.source, self.work / "never.out", recipe, self.catalogue),
            lambda: self.lane.verify(self.source, self.work / "never.out", None),
            lambda: self.lane.conformance_edits(self.catalogue),
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
