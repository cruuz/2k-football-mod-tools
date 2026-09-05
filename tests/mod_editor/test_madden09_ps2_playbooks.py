"""Tests for the Madden NFL 09 (PS2) playbooks lane.

Synthetic sources only.  Every byte a test reads is one the lane's own
``build_synthetic_playbook_disc`` built from the format's rules, so the suite
runs for a contributor who owns none of the discs.

The two load-bearing cases are the **two packing paths**.  A renamed row makes
the database's ``LZH1`` stream a different size, and which side of the member's
existing slot it lands on decides whether the container's directory moves --
which decides whether the preload caches have to move with it.  Both are pinned
here, by an edit chosen to fall on each side: a rename to a string the payload
already carries shrinks the stream and takes the exact-size path; a rename to a
string nothing else in it resembles grows the stream and takes the rewrite path.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_tdb, ea_terf  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, playbooks_lane as lane_module  # noqa: E402

PlaybooksLane = lane_module.PlaybooksLane


class SyntheticPlaybookTests(unittest.TestCase):
    """The fixture is a nineteen-table playbook, NUL-named table included."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = lane_module.synthetic_playbook()
        cls.database = ea_tdb.parse_tdb(cls.payload)

    def test_it_carries_the_nineteen_tables_a_shipped_book_has(self) -> None:
        self.assertEqual(sorted(self.database.table_names),
                         sorted(lane_module.PLAYBOOK_TABLES))

    def test_the_nul_named_table_is_addressable_by_its_escaped_name(self) -> None:
        table = self.database.table("SGF\\x00")
        self.assertEqual(table.raw_name, b"SGF\x00")
        self.assertIn("name", table)

    def test_it_is_recognised_as_a_playbook(self) -> None:
        self.assertTrue(lane_module.is_playbook(self.database))

    def test_a_route_menu_is_not_a_playbook(self) -> None:
        menu = ea_tdb.build_tdb([
            ("ARTL", (("ARTL", ea_tdb.FIELD_UINT, 12),), ({"ARTL": 1},)),
            ("OPTM", (("OPTI", ea_tdb.FIELD_UINT, 8),), ({"OPTI": 1},)),
            ("PSAL", (("PSAL", ea_tdb.FIELD_UINT, 11),), ({"PSAL": 1},)),
        ])
        self.assertFalse(lane_module.is_playbook(ea_tdb.parse_tdb(menu)))

    def test_every_checksum_site_agrees_with_its_own_bytes(self) -> None:
        self.assertEqual(ea_tdb.verify_crcs(self.payload), [])

    def test_it_survives_the_container_codec_it_ships_under(self) -> None:
        packed = ea_terf.lzh1_compress(self.payload)
        self.assertEqual(
            ea_terf.decompress_member(packed, ea_terf.CODEC_LZH1, len(self.payload)),
            self.payload)

    def test_a_padded_stream_still_decodes_to_the_same_database(self) -> None:
        """The property the exact-size packing path rests on."""

        packed = ea_terf.lzh1_compress(self.payload)
        for padding in (1, 7, 64, 512):
            with self.subTest(padding=padding):
                self.assertEqual(
                    ea_terf.decompress_member(packed + b"\x00" * padding,
                                              ea_terf.CODEC_LZH1, len(self.payload)),
                    self.payload)

    def test_two_books_differ(self) -> None:
        self.assertNotEqual(lane_module.synthetic_playbook(0),
                            lane_module.synthetic_playbook(1))


class _LaneCase(unittest.TestCase):
    """A synthetic disc and a built catalogue, shared by the cases below."""

    cached_books: tuple = ()

    @classmethod
    def setUpClass(cls) -> None:
        cls._room = tempfile.TemporaryDirectory()
        cls.room = Path(cls._room.name)
        cls.lane = PlaybooksLane()
        cls.source = cls.room / "source.iso"
        cls.source.write_bytes(
            lane_module.build_synthetic_playbook_disc(cached_books=cls.cached_books))
        cls.catalogue = cls.lane.build_catalogue(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._room.cleanup()

    def destination(self, name: str) -> Path:
        path = self.room / name
        if path.exists():
            path.unlink()
        return path

    def build(self, edits, name: str):
        recipe = self.lane.compose_recipe(tuple(edits))
        destination = self.destination(name)
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        return destination, receipt


class CatalogueTests(_LaneCase):
    def test_every_book_is_listed_and_the_route_menu_is_not(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["books"], lane_module.SYNTHETIC_BOOKS)
        self.assertEqual(document["container"], lane_module.CONTAINER_PATH)
        self.assertEqual(document["checksum_sites_wrong"], 0)

    def test_the_document_carries_no_value_read_out_of_a_record(self) -> None:
        blob = json.dumps(dict(self.catalogue.document))
        self.assertNotIn("Formation 0", blob)
        self.assertNotIn("Play 1", blob)
        self.assertNotIn("values", blob)

    def test_the_document_says_the_disc_names_no_book(self) -> None:
        self.assertIn("no name of its own", self.catalogue.document["book_names"])

    def test_a_row_target_exists_for_every_editable_table(self) -> None:
        tables = {lane_module.parse_row_key(target.key)[2]
                  for target in self.catalogue.targets
                  if target.key.startswith(lane_module.ROW_PREFIX)}
        self.assertEqual(tables, set(lane_module.EDITABLE_TABLES))

    def test_a_row_target_offers_its_name_and_nothing_undocumented(self) -> None:
        target = self.catalogue.target(lane_module.row_key(0, "PLYL", 0))
        offered = {item.key for item in target.fields if not item.read_only}
        self.assertEqual(offered, {"name", "risk", "motn"})

    def test_a_book_and_a_table_target_are_read_only(self) -> None:
        for key in (lane_module.book_key(0), lane_module.table_key(0, "PLYL")):
            with self.subTest(key=key):
                target = self.catalogue.target(key)
                self.assertTrue(all(item.read_only for item in target.fields))

    def test_every_table_reports_itself_exactly_full(self) -> None:
        """The property that makes "no row is added" a fact and not a policy."""

        seen = 0
        for target in self.catalogue.targets:
            if not target.key.startswith("table:"):
                continue
            self.assertEqual(target.raw["records"], target.raw["capacity"],
                             target.key)
            seen += 1
        self.assertEqual(seen, lane_module.SYNTHETIC_BOOKS * len(lane_module.PLAYBOOK_TABLES))

    def test_the_preload_shape_is_read_off_the_image(self) -> None:
        preload = self.catalogue.document["preload"]
        self.assertEqual(len(preload["directory_copies"]), 2)
        self.assertEqual(preload["cached_members"], [lane_module.SYNTHETIC_BOOKS])


class CheckEditTests(_LaneCase):
    def setUp(self) -> None:
        self.target = self.catalogue.target(lane_module.row_key(0, "SETL", 0))

    def test_a_new_name_is_accepted(self) -> None:
        self.assertIsNone(self.lane.check_edit(self.target, {"name": "Another Set"}))

    def test_a_name_longer_than_its_field_is_refused_with_the_budget(self) -> None:
        problem = self.lane.check_edit(self.target, {"name": "x" * 64})
        self.assertIn("shorten it to", problem)

    def test_an_unknown_field_is_refused_by_name(self) -> None:
        problem = self.lane.check_edit(self.target, {"SETL": 3})
        self.assertIn("is not a field this lane writes", problem)

    def test_a_change_that_changes_nothing_is_refused(self) -> None:
        problem = self.lane.check_edit(
            self.target, {"name": self.target.raw["values"]["name"]})
        self.assertIn("Nothing in this row would change", problem)

    def test_text_handed_a_number_is_refused(self) -> None:
        self.assertIn("takes text", self.lane.check_edit(self.target, {"name": 7}))

    def test_a_number_outside_its_field_is_refused(self) -> None:
        target = self.catalogue.target(lane_module.row_key(0, "PLYL", 0))
        problem = self.lane.check_edit(target, {"risk": 999})
        self.assertIn("is outside that", problem)

    def test_the_keep_number_leaves_a_value_alone(self) -> None:
        target = self.catalogue.target(lane_module.row_key(0, "PLYL", 0))
        problem = self.lane.check_edit(
            target, {"risk": lane_module.KEEP_NUMBER, "motn": lane_module.KEEP_NUMBER})
        self.assertIn("Nothing in this row would change", problem)

    def test_a_book_target_is_not_a_row(self) -> None:
        problem = self.lane.check_edit(self.catalogue.target(lane_module.book_key(0)),
                                       {"name": "x"})
        self.assertIn("not a row of one", problem)

    def test_a_nul_in_a_name_is_refused(self) -> None:
        self.assertIn("NUL", self.lane.check_edit(self.target, {"name": "a\x00b"}))


class ExactSizePathTests(_LaneCase):
    """A rename that shrinks the stream leaves the directory byte-identical."""

    #: A string the payload already carries on a neighbouring row, so the
    #: stream comes out shorter and the member fits the bytes it already owns.
    NAME = "Play 0"

    def setUp(self) -> None:
        self.key = lane_module.row_key(0, "PLYL", 1)
        self.target = self.catalogue.target(self.key)

    def test_it_takes_the_exact_size_path_and_touches_no_cache(self) -> None:
        destination, receipt = self.build(
            [Edit(self.key, {"name": self.NAME})], "exact.iso")
        member = receipt.document["members"][0]
        self.assertEqual(member["path"], "exact-size")
        self.assertFalse(member["directory_changed"])
        self.assertEqual(member["stored_bytes"], member["previous_stored_size"])
        self.assertEqual([item["name"] for item in receipt.document["files"]],
                         [lane_module.CONTAINER])
        self.assertEqual(receipt.document["preload_copies"], [])
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)

    def test_the_container_directory_comes_back_byte_identical(self) -> None:
        destination, _receipt = self.build(
            [Edit(self.key, {"name": self.NAME})], "exact-directory.iso")
        source_image = containers.open_disc(self.source)
        source_files = {entry.name: entry for entry in containers.data_files(source_image)}
        before_blob = containers.read_file(source_image,
                                           source_files[lane_module.CONTAINER])
        before = ea_terf.parse_terf(before_blob, allow_size_mismatch=True)
        after_image = containers.open_disc(destination)
        after_files = {entry.name: entry for entry in containers.data_files(after_image)}
        after_blob = containers.read_file(after_image, after_files[lane_module.CONTAINER])
        after = ea_terf.parse_terf(after_blob, allow_size_mismatch=True)
        self.assertEqual(after.data_offset, before.data_offset)
        self.assertEqual(after_blob[:after.data_offset],
                         before_blob[:before.data_offset])
        for index in range(after.member_count):
            self.assertEqual(after.members[index].offset, before.members[index].offset)
            self.assertEqual(after.members[index].stored_size,
                             before.members[index].stored_size)

    def test_the_verifier_passes_and_reads_the_new_name_back(self) -> None:
        destination, receipt = self.build(
            [Edit(self.key, {"name": self.NAME})], "exact-verify.iso")
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        image = containers.open_disc(destination)
        container = containers.load_container(image, lane_module.CONTAINER)
        database = ea_tdb.parse_tdb(containers.member_uncached(container, 0))
        self.assertEqual(database.value("PLYL", 1, "name"), self.NAME)
        self.assertEqual(ea_tdb.verify_crcs(containers.member_uncached(container, 0)), [])


class GrowthPathTests(_LaneCase):
    """A rename that grows the stream moves the directory, and the caches with it."""

    NAME = "Qzx Vwk Jhy Pmf"

    def setUp(self) -> None:
        self.key = lane_module.row_key(0, "SETL", 0)

    def test_it_takes_the_rewrite_path_and_mirrors_both_directory_copies(self) -> None:
        destination, receipt = self.build([Edit(self.key, {"name": self.NAME})],
                                          "grow.iso")
        member = receipt.document["members"][0]
        self.assertEqual(member["path"], "rewrite")
        self.assertTrue(member["directory_changed"])
        copies = receipt.document["preload_copies"]
        self.assertEqual(len(copies), 2)
        self.assertEqual({copy["cache"] for copy in copies}, {"FE.QKL"})
        self.assertEqual({copy["kind"] for copy in copies}, {"header"})
        self.assertIn(containers.PRELOAD_CACHES[1],
                      [item["name"] for item in receipt.document["files"]])

    def test_the_verifier_passes_and_the_caches_match_the_new_directory(self) -> None:
        destination, receipt = self.build([Edit(self.key, {"name": self.NAME})],
                                          "grow-verify.iso")
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertGreaterEqual(verdict.document["preload_copies"], 3)

    def test_a_stale_cache_copy_fails_the_verifier(self) -> None:
        """Break the mirroring by hand; the verifier must catch it."""

        destination, receipt = self.build([Edit(self.key, {"name": self.NAME})],
                                          "grow-stale.iso")
        image = containers.open_disc(destination)
        files = {entry.name: entry for entry in containers.data_files(image)}
        entry = files[containers.PRELOAD_CACHES[1]]
        copies = containers.preload_copies(image)[lane_module.CONTAINER].header
        blob = bytearray(destination.read_bytes())
        # The cache's own extent, then the copy's offset inside it.
        at = containers.iso_lib.extent_byte_offset(
            containers.open_disc(destination), entry.lba, 0) + copies[0].offset
        blob[at] ^= 0xFF
        stale = self.destination("grow-stale-broken.iso")
        stale.write_bytes(bytes(blob))
        verdict = self.lane.verify(self.source, stale, receipt)
        self.assertFalse(verdict.passed)


class VerifierTests(_LaneCase):
    def test_a_value_changed_behind_the_receipt_is_caught(self) -> None:
        key = lane_module.row_key(0, "SETL", 0)
        destination, receipt = self.build([Edit(key, {"name": "Verifier Set"})],
                                          "tamper.iso")
        document = dict(receipt.document)
        edits = [dict(item) for item in document["edits"]]
        edits[0]["after"] = {"name": "Something Else"}
        document["edits"] = edits
        with self.assertRaises(Refusal) as caught:
            lane_module.verify_build(self.source, destination, document)
        self.assertIn("the receipt says it should read", str(caught.exception))

    def test_a_receipt_with_no_write_report_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            lane_module.verify_build(self.source, self.source, {"edits": []})
        self.assertIn("no ISO write report", str(caught.exception))


class RefusalTests(_LaneCase):
    def test_a_recipe_of_another_schema_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, {"schema": "something/v1", "edits": [{}]},
                           self.catalogue)
        self.assertIn(lane_module.RECIPE_SCHEMA, str(caught.exception))

    def test_an_empty_recipe_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, {"schema": lane_module.RECIPE_SCHEMA, "edits": []},
                           self.catalogue)
        self.assertIn("changes nothing", str(caught.exception))

    def test_a_key_that_is_not_a_row_is_refused_with_its_shape(self) -> None:
        with self.assertRaises(Refusal) as caught:
            lane_module.parse_row_key(lane_module.book_key(0))
        self.assertIn("<container>#<member>:<table>:<record>", str(caught.exception))

    def test_a_table_this_page_does_not_write_is_refused(self) -> None:
        recipe = {"schema": lane_module.RECIPE_SCHEMA,
                  "edits": [{"target": lane_module.row_key(0, "PSAL", 0),
                             "values": {"code": 3}}]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, None)
        self.assertIn("this page writes", str(caught.exception))

    def test_an_edit_with_no_value_is_refused(self) -> None:
        recipe = {"schema": lane_module.RECIPE_SCHEMA,
                  "edits": [{"target": lane_module.row_key(0, "SETL", 0), "values": {}}]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, None)
        self.assertIn("names no value to write", str(caught.exception))

    def test_the_destination_may_not_be_the_source(self) -> None:
        recipe = self.lane.compose_recipe(
            (Edit(lane_module.row_key(0, "SETL", 0), {"name": "Same File"}),))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.source, recipe, self.catalogue)
        self.assertIn("destination is the source", str(caught.exception))

    def test_an_existing_destination_is_never_overwritten(self) -> None:
        recipe = self.lane.compose_recipe(
            (Edit(lane_module.row_key(0, "SETL", 0), {"name": "Existing"}),))
        destination = self.destination("existing.iso")
        destination.write_bytes(b"not an image")
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, destination, recipe, self.catalogue)
        self.assertIn("already exists", str(caught.exception))
        self.assertEqual(destination.read_bytes(), b"not an image")


class CachedMemberTests(_LaneCase):
    """A playbook a preload cache carries is refused, by name.

    The retail disc caches no playbook [M], so this shape has to be built on
    purpose; the guard exists because the rule is read off the user's image and
    a different image could have one.
    """

    cached_books = (1,)

    def test_the_catalogue_marks_it_unwritable_and_says_why(self) -> None:
        target = self.catalogue.target(lane_module.row_key(1, "SETL", 0))
        self.assertFalse(target.raw["writable"])
        self.assertIn("preload cache", target.budget)

    def test_check_edit_refuses_it(self) -> None:
        target = self.catalogue.target(lane_module.row_key(1, "SETL", 0))
        problem = self.lane.check_edit(target, {"name": "Nope"})
        self.assertIn("cached copy is a fixed slot", problem)

    def test_the_build_refuses_it_even_without_a_catalogue(self) -> None:
        recipe = {"schema": lane_module.RECIPE_SCHEMA,
                  "edits": [{"target": lane_module.row_key(1, "SETL", 0),
                             "values": {"name": "Nope"}}]}
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, None)
        self.assertIn("GAME.QKL", str(caught.exception))

    def test_an_uncached_book_beside_it_is_still_writable(self) -> None:
        target = self.catalogue.target(lane_module.row_key(0, "SETL", 0))
        self.assertTrue(target.raw["writable"])
        self.assertIsNone(self.lane.check_edit(target, {"name": "Fine"}))


class LaneWiringTests(unittest.TestCase):
    def test_the_lane_lands_on_the_playbooks_page(self) -> None:
        self.assertEqual(PlaybooksLane.page, "playbooks")
        self.assertEqual(PlaybooksLane.surface, "scripts_config")

    def test_it_never_claims_more_than_offline(self) -> None:
        self.assertEqual(PlaybooksLane.classification, "offline-writer-proved")
        self.assertIn("has been booted", PlaybooksLane.NOT_BOOTED)

    def test_the_module_registers_it(self) -> None:
        from mod_editor.games import madden09_ps2

        self.assertIn(lane_module.CAPABILITY_ID,
                      [lane.capability_id for lane in madden09_ps2.LANES])

    def test_the_cli_selftest_runs_without_game_data(self) -> None:
        self.assertEqual(lane_module._main(["--selftest"]), 0)


if __name__ == "__main__":
    unittest.main()
