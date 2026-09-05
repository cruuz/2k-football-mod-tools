"""The Madden 09 (PS2) team-identity lane, on a synthetic disc only.

The databases here are built by :func:`identity_lane.synthetic_team_database`
and :func:`identity_lane.synthetic_stream_database` out of the EA TDB format's
own rules; the table and field names are the ones a real disc uses and every
value is invented -- the word SYNTHETIC and arithmetic on a team id.  No game
data.
"""

from __future__ import annotations

import copy
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
from mod_editor.games.contract import Edit, Field, Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, identity_lane  # noqa: E402


def stream_database_with(**overrides: object) -> bytes:
    """The synthetic bare database, with the first team's row altered.

    Used to build a disc whose second copy does **not** agree with the first,
    which is the case the lane has to leave alone rather than overwrite.
    """

    rows = []
    for team_id in reversed(identity_lane.SYNTHETIC_TEAM_IDS):
        row = identity_lane.synthetic_team_row(team_id)
        if team_id == identity_lane.SYNTHETIC_TEAM_IDS[0]:
            row.update(overrides)
        rows.append(row)
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        (identity_lane.TEAM_TABLE, identity_lane.SYNTHETIC_TEAM_SCHEMA, tuple(rows)),
    )))


def disc_with(stream: bytes) -> bytes:
    return containers.build_synthetic_disc(
        tdb_members=[identity_lane.synthetic_team_database(team_id)
                     for team_id in identity_lane.SYNTHETIC_TEAM_IDS],
        stream_database=stream,
    )


class SyntheticDatabaseTests(unittest.TestCase):
    def test_the_member_fixture_round_trips_through_the_reader(self) -> None:
        database = ea_tdb.parse_tdb(identity_lane.synthetic_team_database(11))
        table = database.table("TEAM")
        self.assertEqual(table.current_records, 1)
        self.assertEqual(database.value(table, 0, "TGID"), 11)
        self.assertEqual(database.value(table, 0, "TDNA"), "SYNTHETICS-11")
        self.assertEqual(database.value(table, 0, "TWIN"), -3,
                         "a signed neighbour must survive a write beside it")

    def test_the_fixtures_carry_correct_checksums(self) -> None:
        """A fixture with stale checksums would not test a writer that keeps them."""

        self.assertEqual(ea_tdb.verify_crcs(identity_lane.synthetic_team_database(11)), [])
        self.assertEqual(ea_tdb.verify_crcs(identity_lane.synthetic_stream_database()), [])

    def test_the_bare_database_lists_its_rows_in_the_other_order(self) -> None:
        """The retail disc's rows are not in team-id order, so the fixture's are not."""

        database = ea_tdb.parse_tdb(identity_lane.synthetic_stream_database())
        table = database.table("TEAM")
        found = [database.value(table, index, "TGID")
                 for index in range(table.current_records)]
        self.assertEqual(found, list(reversed(identity_lane.SYNTHETIC_TEAM_IDS)))


class KeyTests(unittest.TestCase):
    def test_a_team_key_round_trips(self) -> None:
        key = identity_lane.team_key("/DATA/DB_TEAMS.DAT", 4, 0)
        self.assertEqual(identity_lane.parse_team_key(key), ("/DATA/DB_TEAMS.DAT", 4, 0))

    def test_something_that_is_not_a_team_key_names_the_spelling(self) -> None:
        with self.assertRaises(Refusal) as caught:
            identity_lane.parse_team_key("row:/DATA/DB_TEAMS.DAT#0:PLAY:3")
        self.assertIn("team:<container>#<member>:<record>", str(caught.exception))

    def test_a_malformed_team_key_names_the_spelling(self) -> None:
        with self.assertRaises(Refusal) as caught:
            identity_lane.parse_team_key("team:nonsense")
        self.assertIn("<container>#<member>", str(caught.exception))


class ColourTests(unittest.TestCase):
    def test_six_digits_with_and_without_a_hash(self) -> None:
        self.assertEqual(identity_lane.parse_colour("#1B3A5F"), (0x1B, 0x3A, 0x5F))
        self.assertEqual(identity_lane.parse_colour("1b3a5f"), (0x1B, 0x3A, 0x5F))

    def test_an_alpha_byte_is_dropped_and_the_help_says_so(self) -> None:
        self.assertEqual(identity_lane.parse_colour("#801B3A5F"), (0x1B, 0x3A, 0x5F))
        table = ea_tdb.parse_tdb(identity_lane.synthetic_team_database(11)).table("TEAM")
        colour = next(item for item in identity_lane.fields_for(table)
                      if item.kind == "colour_argb")
        self.assertIn("alpha", colour.help)

    def test_a_colour_round_trips_through_the_hex_line(self) -> None:
        self.assertEqual(identity_lane.format_colour(*identity_lane.parse_colour("#0A141E")),
                         "#0A141E")

    def test_a_colour_of_the_wrong_length_is_refused_with_the_spelling(self) -> None:
        with self.assertRaises(Refusal) as caught:
            identity_lane.parse_colour("#FFF")
        self.assertIn("#RRGGBB", str(caught.exception))

    def test_a_colour_that_is_not_hex_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            identity_lane.parse_colour("#GGHHII")
        self.assertIn("hex digit", str(caught.exception))


class FieldShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = ea_tdb.parse_tdb(
            identity_lane.synthetic_team_database(11)).table("TEAM")
        self.shape = identity_lane.fields_for(self.table)

    def test_the_offered_fields_are_the_names_the_colours_and_the_city_id(self) -> None:
        self.assertEqual([item.key for item in self.shape],
                         ["TDNA", "TLNA", "TSNA", "TMNC",
                          "primary", "secondary", "CYID"])

    def test_no_hypothesis_field_is_offered(self) -> None:
        drawn = {item.key for item in self.shape}
        for name in identity_lane.MEASURED_NOT_EDITED:
            self.assertNotIn(name, drawn,
                             f"{name} is measured-but-not-edited and must not be drawn")

    def test_a_name_budget_leaves_room_for_the_terminator(self) -> None:
        """17, 18, 7 and 17 bytes on the disc; one less each on screen."""

        budgets = {item.key: item.maximum for item in self.shape if item.kind == "text"}
        self.assertEqual(budgets, {"TDNA": 16, "TLNA": 17, "TSNA": 6, "TMNC": 16})

    def test_the_city_id_is_bounded_by_its_own_width(self) -> None:
        city = next(item for item in self.shape if item.key == "CYID")
        self.assertEqual(city.maximum, 255)
        self.assertEqual(city.minimum, identity_lane.KEEP_NUMBER)

    def test_a_colour_needs_all_three_channels_before_it_is_offered(self) -> None:
        partial = ea_tdb.parse_tdb(ea_tdb.recompute_crcs(ea_tdb.build_tdb((
            ("TEAM", (("TGID", ea_tdb.FIELD_UINT, 10),
                      ("TDNA", ea_tdb.FIELD_STRING, 17 * 8),
                      ("TBCR", ea_tdb.FIELD_UINT, 8),
                      ("TBCG", ea_tdb.FIELD_UINT, 8)),
             ({"TGID": 1, "TDNA": "A", "TBCR": 1, "TBCG": 2},)),
        )))).table("TEAM")
        self.assertEqual([item.key for item in identity_lane.fields_for(partial)],
                         ["TDNA"])

    def test_a_colour_is_written_as_three_channel_fields(self) -> None:
        self.assertEqual(identity_lane.record_writes({"primary": "#0A141E"}),
                         {"TBCR": 0x0A, "TBCG": 0x14, "TBCB": 0x1E})
        self.assertEqual(identity_lane.record_writes({"secondary": "#010203"}),
                         {"TB2R": 1, "TB2G": 2, "TB2B": 3})

    def test_a_name_and_a_number_pass_through_unchanged(self) -> None:
        self.assertEqual(identity_lane.record_writes({"TSNA": "AB", "CYID": 7}),
                         {"TSNA": "AB", "CYID": 7})


class IdentityLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-identity-")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = identity_lane.IdentityLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.team = self.catalogue.targets[0]

    def _built(self, values=None, name="built.iso"):
        values = values or {"TSNA": "MOD", "primary": "#123456"}
        recipe = self.lane.compose_recipe((Edit(self.team.key, values),))
        destination = self.work / name
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        return recipe, destination, receipt

    # -- shape ---------------------------------------------------------

    def test_the_lane_writes_and_lands_on_the_identity_page(self) -> None:
        self.assertFalse(self.lane.read_only)
        self.assertEqual(self.lane.page, "identity")
        self.assertEqual(self.lane.surface, "colors")
        self.assertEqual(self.lane.classification, "offline-writer-proved")
        self.assertTrue(self.lane.fixed_allocation)

    def test_the_catalogue_lists_one_target_per_team(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["teams_listed"], len(identity_lane.SYNTHETIC_TEAM_IDS))
        self.assertEqual(len(self.catalogue.targets), document["teams_listed"])
        self.assertTrue(document["stream_present"])
        self.assertEqual(document["stream_rows"], len(identity_lane.SYNTHETIC_TEAM_IDS))

    def test_a_target_carries_the_values_and_the_copies(self) -> None:
        values = dict(self.team.raw["values"])
        self.assertEqual(values["TDNA"], "SYNTHETICS-11")
        self.assertEqual(values["primary"], identity_lane.format_colour(11, 33, 77))
        copies = [dict(item) for item in self.team.raw["copies"]]
        self.assertEqual([item["file"] for item in copies],
                         [identity_lane.TEAM_CONTAINER, identity_lane.STREAM_DATABASE])
        self.assertTrue(all(item["written"] for item in copies))

    def test_the_second_copy_is_found_by_team_id_and_not_by_position(self) -> None:
        """Member 0 is team 11 and the bare database lists team 11 second."""

        stream = [item for item in self.team.raw["copies"]
                  if item["file"] == identity_lane.STREAM_DATABASE][0]
        self.assertEqual(self.team.raw["team_id"], identity_lane.SYNTHETIC_TEAM_IDS[0])
        self.assertEqual(self.team.raw["member"], 0)
        self.assertEqual(stream["record"], 1)

    def test_the_document_carries_no_value_from_the_disc(self) -> None:
        text = json.dumps(dict(self.catalogue.document))
        self.assertNotIn("SYNTHETICS", text)
        self.assertNotIn("Nowhere", text)
        self.assertIn("TDNA", text, "the field names are the point of the document")

    def test_two_teams_of_one_schema_share_one_field_shape(self) -> None:
        """Thirty-two teams must not carry thirty-two copies of one description."""

        first, second = self.catalogue.targets[0], self.catalogue.targets[1]
        self.assertIs(first.fields, second.fields)

    def test_a_member_with_another_schema_gets_its_own_shape(self) -> None:
        """A modified image must not be offered the first member's controls."""

        odd = ea_tdb.recompute_crcs(ea_tdb.build_tdb((
            (identity_lane.TEAM_TABLE,
             (("TGID", ea_tdb.FIELD_UINT, 10),
              ("TDNA", ea_tdb.FIELD_STRING, 9 * 8)),
             ({"TGID": 11, "TDNA": "SHORT"},)),
        )))
        source = self.work / "mixed.iso"
        source.write_bytes(containers.build_synthetic_disc(
            tdb_members=[identity_lane.synthetic_team_database(
                identity_lane.SYNTHETIC_TEAM_IDS[0]), odd],
            stream_database=identity_lane.synthetic_stream_database()))
        catalogue = self.lane.build_catalogue(source)
        full, narrow = catalogue.targets[0], catalogue.targets[1]
        self.assertEqual([item.key for item in narrow.fields], ["TDNA"])
        self.assertEqual(narrow.fields[0].maximum, 8)
        self.assertGreater(len(full.fields), len(narrow.fields))

    def test_the_document_names_what_is_measured_but_not_edited(self) -> None:
        for name in ("TCDO", "TCRP", "TGPT", "TCTX"):
            self.assertIn(name, self.catalogue.document["measured_not_edited"])

    # -- check_edit ----------------------------------------------------

    def test_a_good_edit_is_accepted(self) -> None:
        self.assertIsNone(self.lane.check_edit(self.team,
                                               {"TSNA": "MOD", "primary": "#112233"}))

    def test_a_field_this_lane_does_not_write_is_refused_by_name(self) -> None:
        problem = self.lane.check_edit(self.team, {"TCDO": 4})
        self.assertIn("TCDO", problem or "")

    def test_a_name_over_its_budget_is_refused_with_the_length(self) -> None:
        problem = self.lane.check_edit(self.team, {"TSNA": "TOOLONGNAME"})
        self.assertIn("11 characters", problem or "")
        self.assertIn("holds 6", problem or "")

    def test_text_outside_the_encoding_is_refused(self) -> None:
        self.assertIn("latin-1", self.lane.check_edit(self.team, {"TSNA": "中"}) or "")

    def test_a_name_with_a_nul_is_refused(self) -> None:
        self.assertIn("NUL", self.lane.check_edit(self.team, {"TSNA": "A\x00B"}) or "")

    def test_a_bad_colour_is_refused_with_the_spelling(self) -> None:
        problem = self.lane.check_edit(self.team, {"primary": "#ZZZ"})
        self.assertIn("#RRGGBB", problem or "")

    def test_a_colour_handed_a_number_is_refused(self) -> None:
        self.assertIn("hex colour", self.lane.check_edit(self.team, {"primary": 3}) or "")

    def test_a_city_id_over_its_width_is_refused_with_the_range(self) -> None:
        problem = self.lane.check_edit(self.team, {"CYID": 999})
        self.assertIn("0 to 255", problem or "")

    def test_the_keep_value_leaves_a_number_alone(self) -> None:
        problem = self.lane.check_edit(
            self.team, {"CYID": identity_lane.KEEP_NUMBER, "TSNA": "MOD"})
        self.assertIsNone(problem)

    def test_a_team_where_nothing_changes_is_refused(self) -> None:
        same = {key: self.team.raw["values"][key] for key in ("TSNA", "primary")}
        self.assertIn("Nothing about this team", self.lane.check_edit(self.team, same) or "")

    def test_a_recipe_drops_the_blanks_and_the_keep_values(self) -> None:
        recipe = self.lane.compose_recipe((Edit(self.team.key, {
            "TSNA": "MOD", "TDNA": "", "primary": "  ",
            "CYID": identity_lane.KEEP_NUMBER}),))
        self.assertEqual(recipe["edits"][0]["values"], {"TSNA": "MOD"})
        self.assertEqual(recipe["schema"], identity_lane.RECIPE_SCHEMA)

    # -- plan / build --------------------------------------------------

    def test_a_plan_declares_ranges_and_writes_nothing(self) -> None:
        before = self.source.read_bytes()
        recipe = self.lane.compose_recipe((Edit(self.team.key, {"TSNA": "MOD"}),))
        plan = self.lane.plan(self.source, recipe, self.catalogue)
        self.assertTrue(plan.declared_ranges)
        self.assertEqual(plan.target_keys, (self.team.key,))
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_plan_for_an_unknown_target_refuses(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.plan(self.source,
                           self.lane.compose_recipe((Edit("nope", {"TSNA": "MOD"}),)),
                           self.catalogue)

    def test_a_plan_for_a_member_past_the_nfl_teams_refuses(self) -> None:
        key = identity_lane.team_key(
            f"{containers.DATA_DIRECTORY}/{identity_lane.TEAM_CONTAINER}",
            identity_lane.NFL_TEAM_MEMBERS + 1, 0)
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source,
                           self.lane.compose_recipe((Edit(key, {"TSNA": "MOD"}),)),
                           self.catalogue)
        self.assertIn("historical squads", str(caught.exception))

    def test_a_build_writes_a_new_image_of_the_same_size_and_verifies(self) -> None:
        _recipe, destination, receipt = self._built()
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

    def test_a_build_writes_both_copies_of_the_row(self) -> None:
        _recipe, _destination, receipt = self._built()
        files = {(edit["iso_path"], edit["record"]) for edit in receipt.document["edits"]}
        self.assertEqual(files, {
            (f"{containers.DATA_DIRECTORY}/{identity_lane.TEAM_CONTAINER}", 0),
            (f"{containers.DATA_DIRECTORY}/{identity_lane.STREAM_DATABASE}", 1),
        })
        self.assertEqual(receipt.document["copies_not_written"], [])

    def test_the_written_values_read_back_through_the_plain_reader(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        member = containers.load_container(
            image, identity_lane.TEAM_CONTAINER).member(0)
        database = ea_tdb.parse_tdb(member)
        self.assertEqual(database.value("TEAM", 0, "TSNA"), "MOD")
        self.assertEqual((database.value("TEAM", 0, "TBCR"),
                          database.value("TEAM", 0, "TBCG"),
                          database.value("TEAM", 0, "TBCB")), (0x12, 0x34, 0x56))
        entry = next(item for item in containers.data_files(image)
                     if item.name == identity_lane.STREAM_DATABASE)
        stream = ea_tdb.parse_tdb(containers.read_file(image, entry, limit=None))
        self.assertEqual(stream.value("TEAM", 1, "TSNA"), "MOD",
                         "the second copy must carry the same new value")
        self.assertEqual(stream.value("TEAM", 0, "TSNA"), "SY22",
                         "the other team's row must be untouched")

    def test_a_shorter_name_is_padded_out_over_the_old_one(self) -> None:
        _recipe, destination, _receipt = self._built(values={"TDNA": "AB"})
        image = containers.open_disc(destination)
        database = ea_tdb.parse_tdb(containers.load_container(
            image, identity_lane.TEAM_CONTAINER).member(0))
        table = database.table("TEAM")
        record = database.record_bytes(table, 0)
        field = table.field("TDNA")
        start = field.bit_offset // 8
        raw = record[start:start + field.bit_width // 8]
        self.assertEqual(raw, b"AB" + b"\x00" * (len(raw) - 2))

    def test_every_other_value_in_the_database_is_untouched(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        after = ea_tdb.parse_tdb(containers.load_container(
            image, identity_lane.TEAM_CONTAINER).member(0))
        before = ea_tdb.parse_tdb(identity_lane.synthetic_team_database(
            identity_lane.SYNTHETIC_TEAM_IDS[0]))
        changed = {"TSNA", "TBCR", "TBCG", "TBCB"}
        for name in before.table("TEAM").field_names:
            if name in changed:
                continue
            self.assertEqual(after.value("TEAM", 0, name), before.value("TEAM", 0, name),
                             f"{name} moved and nothing asked it to")

    def test_the_destination_databases_still_checksum(self) -> None:
        _recipe, destination, _receipt = self._built()
        image = containers.open_disc(destination)
        member = containers.load_container(
            image, identity_lane.TEAM_CONTAINER).member(0)
        self.assertEqual(ea_tdb.verify_crcs(member), [])
        entry = next(item for item in containers.data_files(image)
                     if item.name == identity_lane.STREAM_DATABASE)
        self.assertEqual(
            ea_tdb.verify_crcs(containers.read_file(image, entry, limit=None)), [])

    def test_a_build_leaves_the_source_alone(self) -> None:
        before = self.source.read_bytes()
        self._built()
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_build_refuses_an_existing_destination(self) -> None:
        _recipe, destination, _receipt = self._built()
        digest = destination.read_bytes()
        with self.assertRaises(Refusal):
            self._built(name=destination.name)
        self.assertEqual(destination.read_bytes(), digest)

    def test_a_build_refuses_the_source_as_its_destination(self) -> None:
        recipe = self.lane.compose_recipe((Edit(self.team.key, {"TSNA": "MOD"}),))
        with self.assertRaises(Refusal):
            self.lane.build(self.source, self.source, recipe, self.catalogue)

    def test_a_recipe_of_another_schema_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, {"schema": "something/v1", "edits": [
                {"target": self.team.key, "values": {"TSNA": "MOD"}}]}, self.catalogue)

    def test_an_empty_recipe_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.plan(self.source,
                           {"schema": identity_lane.RECIPE_SCHEMA, "edits": []},
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
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed)

    def test_the_verifier_catches_a_byte_no_declared_span_covers(self) -> None:
        """The ISO ranges still hold; a field span the receipt dropped does not.

        Narrowing the receipt is the only way to reach the database-level walk
        with a real destination, and it is the walk that stops a writer that
        wrote correctly and scribbled somewhere else as well.
        """

        _recipe, destination, receipt = self._built()
        document = copy.deepcopy(dict(receipt.document))
        for edit in document["edits"]:
            edit["field_spans"] = [span for span in edit["field_spans"]
                                   if span["field"] != "TSNA"]
            edit["after"] = {key: value for key, value in edit["after"].items()
                             if key != "TSNA"}
        with self.assertRaises(Refusal) as caught:
            identity_lane.verify_build(self.source, destination, document)
        self.assertIn("outside what it declared", str(caught.exception))

    def test_the_verifier_catches_a_value_that_does_not_read_back(self) -> None:
        _recipe, destination, receipt = self._built()
        document = copy.deepcopy(dict(receipt.document))
        document["edits"][0]["after"]["TSNA"] = "XYZ"
        with self.assertRaises(Refusal) as caught:
            identity_lane.verify_build(self.source, destination, document)
        self.assertIn("should read 'XYZ'", str(caught.exception))

    def test_the_verifier_catches_a_stale_checksum(self) -> None:
        _recipe, destination, receipt = self._built()
        image = containers.open_disc(destination)
        entry = next(item for item in containers.data_files(image)
                     if item.name == identity_lane.TEAM_CONTAINER)
        original = containers.read_file(image, entry)
        member = ea_terf.parse_terf(original, allow_size_mismatch=True).member(0)
        stale = ea_tdb.set_value(ea_tdb.parse_tdb(member), "TEAM", 0, "TSNA", "ZZ",
                                 recompute=False)
        rebuilt = ea_terf.rewrite_member(original, 0, stale)
        raw = bytearray(destination.read_bytes())
        start = entry.lba * 2048
        raw[start:start + len(rebuilt)] = rebuilt
        tampered = self.work / "stale.iso"
        tampered.write_bytes(bytes(raw))
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed)

    def test_a_receipt_with_no_iso_report_is_refused_rather_than_believed(self) -> None:
        _recipe, destination, _receipt = self._built()
        with self.assertRaises(Refusal):
            identity_lane.verify_build(self.source, destination, {"edits": []})


class PaddingRuleTests(unittest.TestCase):
    """The rule the verifier re-expresses: a name, then NULs to the field's width."""

    def _edit(self, database: ea_tdb.TdbDatabase, value: str) -> dict:
        table = database.table("TEAM")
        field = table.field("TSNA")
        start = database.record_offset("TEAM", 0) + field.bit_offset // 8
        return {
            "iso_path": "/DATA/DB_TEAMS.DAT", "member": 0, "table": "TEAM", "record": 0,
            "after": {"TSNA": value},
            "field_spans": [{"field": "TSNA", "start": start,
                             "length": field.bit_width // 8,
                             "bit_offset": field.bit_offset,
                             "bit_width": field.bit_width, "type": "STRING"}],
        }

    def test_a_padded_name_passes(self) -> None:
        payload = ea_tdb.set_value(
            ea_tdb.parse_tdb(identity_lane.synthetic_team_database(11)),
            "TEAM", 0, "TSNA", "AB")
        edits = [self._edit(ea_tdb.parse_tdb(payload), "AB")]
        identity_lane._check_padding(payload, edits, "/DATA/DB_TEAMS.DAT", 0, "member 0")

    def test_a_name_with_the_old_tail_left_behind_is_refused(self) -> None:
        payload = bytearray(ea_tdb.set_value(
            ea_tdb.parse_tdb(identity_lane.synthetic_team_database(11)),
            "TEAM", 0, "TSNA", "AB"))
        database = ea_tdb.parse_tdb(bytes(payload))
        table = database.table("TEAM")
        field = table.field("TSNA")
        start = database.record_offset("TEAM", 0) + field.bit_offset // 8
        payload[start + 4] = ord("X")             # a NUL the writer should have left
        repaired = ea_tdb.recompute_crcs(bytes(payload))
        edits = [self._edit(ea_tdb.parse_tdb(repaired), "AB")]
        with self.assertRaises(Refusal) as caught:
            identity_lane._check_padding(repaired, edits, "/DATA/DB_TEAMS.DAT", 0, "member 0")
        self.assertIn("leaves the old one's tail behind", str(caught.exception))


class DisagreeingCopyTests(unittest.TestCase):
    """A second copy that already says something else is left alone, and named."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-identity-differ-")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = identity_lane.IdentityLane()
        self.source = self.work / "differing.iso"
        self.source.write_bytes(disc_with(stream_database_with(TSNA="OTHER")))
        self.catalogue = self.lane.build_catalogue(self.source)
        self.team = self.catalogue.targets[0]

    def test_the_catalogue_names_the_field_the_copy_will_not_take(self) -> None:
        """One name differs, so that name is held back and the rest are not."""

        stream = [dict(item) for item in self.team.raw["copies"]
                  if item["file"] == identity_lane.STREAM_DATABASE][0]
        self.assertEqual(list(stream["fields_not_written"]), ["TSNA"])
        self.assertTrue(stream["written"], "a colour still goes into this copy")
        self.assertIn("TSNA", stream["reason"])
        self.assertIn("TSNA", self.team.detail)

    def test_a_copy_that_differs_in_everything_is_not_written_at_all(self) -> None:
        source = self.work / "all-different.iso"
        source.write_bytes(disc_with(stream_database_with(
            TDNA="OTHERNAME", TLNA="Elsewhere", TSNA="OTH", TMNC="Other",
            CYID=200, TBCR=1, TBCG=2, TBCB=3, TB2R=4, TB2G=5, TB2B=6)))
        catalogue = self.lane.build_catalogue(source)
        stream = [dict(item) for item in catalogue.targets[0].raw["copies"]
                  if item["file"] == identity_lane.STREAM_DATABASE][0]
        self.assertFalse(stream["written"])
        self.assertIn("every field this page writes", stream["reason"])

    def test_a_build_writes_the_anchor_and_reports_the_copy_it_left(self) -> None:
        recipe = self.lane.compose_recipe((Edit(self.team.key, {"TSNA": "MOD"}),))
        destination = self.work / "built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        paths = {edit["iso_path"] for edit in receipt.document["edits"]}
        self.assertEqual(paths,
                         {f"{containers.DATA_DIRECTORY}/{identity_lane.TEAM_CONTAINER}"})
        skipped = list(receipt.document["copies_not_written"])
        self.assertEqual(len(skipped), 1)
        self.assertIn("TSNA", skipped[0]["reason"])
        self.assertTrue(self.lane.verify(self.source, destination, receipt).passed)

    def test_a_colour_still_agrees_and_is_still_written_to_both(self) -> None:
        """Agreement is per field: one disagreeing name does not stop a colour."""

        recipe = self.lane.compose_recipe((Edit(self.team.key, {"primary": "#010203"}),))
        destination = self.work / "colour.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        paths = {edit["iso_path"] for edit in receipt.document["edits"]}
        self.assertIn(f"{containers.DATA_DIRECTORY}/{identity_lane.STREAM_DATABASE}", paths)
        self.assertTrue(self.lane.verify(self.source, destination, receipt).passed)


class PreloadCacheTests(unittest.TestCase):
    """A file a preload cache names is refused, and the list comes off the image."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-identity-cache-")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = identity_lane.IdentityLane()
        self.source = self.lane.synthetic_source(self.work)
        self.real = containers.preload_names
        self.addCleanup(setattr, containers, "preload_names", self.real)

    def test_a_cached_team_container_refuses_the_whole_catalogue(self) -> None:
        containers.preload_names = lambda image: {
            identity_lane.TEAM_CONTAINER.upper(): ("FE.QKL",)}
        with self.assertRaises(Refusal) as caught:
            self.lane.build_catalogue(self.source)
        self.assertIn("FE.QKL", str(caught.exception))

    def test_a_cached_bare_database_is_left_out_rather_than_written(self) -> None:
        containers.preload_names = lambda image: {
            identity_lane.STREAM_DATABASE.upper(): ("GAME.QKL",)}
        catalogue = self.lane.build_catalogue(self.source)
        self.assertFalse(catalogue.document["stream_present"])
        self.assertIn("GAME.QKL", catalogue.document["stream_note"])
        team = catalogue.targets[0]
        recipe = self.lane.compose_recipe((Edit(team.key, {"TSNA": "MOD"}),))
        receipt = self.lane.build(self.source, self.work / "cached.iso", recipe, catalogue)
        self.assertEqual({edit["iso_path"] for edit in receipt.document["edits"]},
                         {f"{containers.DATA_DIRECTORY}/{identity_lane.TEAM_CONTAINER}"})
        self.assertIn("GAME.QKL", receipt.document["copies_not_written"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
