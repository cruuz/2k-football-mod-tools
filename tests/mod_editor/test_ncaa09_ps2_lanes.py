"""The NCAA Football 09 (PS2) lanes, on synthetic sources.  No game data.

Everything here is built from the formats' own rules by
``mod_editor.games.ncaa09_ps2.containers``: a synthetic ISO carrying synthetic
TERF containers, synthetic EA TDB databases with their four checksums correct,
synthetic MMAP wrappers, synthetic TEXT banks and ``ea_schl``'s own synthetic
stream and bank.  No byte of any disc is in this repository.
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
from mod_editor.games.ncaa09_ps2 import containers  # noqa: E402
from mod_editor.games.ncaa09_ps2.audio_lane import AudioBanksLane, AudioStreamsLane  # noqa: E402
from mod_editor.games.ncaa09_ps2.database_lane import DatabaseLane  # noqa: E402
from mod_editor.games.ncaa09_ps2.disc_identity import Ncaa09DiscIdentifier  # noqa: E402
from mod_editor.games.ncaa09_ps2.inventory_lane import InventoryLane  # noqa: E402
from mod_editor.games.ncaa09_ps2.text_lane import TextLane, slots_in, split_strings  # noqa: E402
from mod_editor.games.ncaa09_ps2.identity_lane import IdentityLane  # noqa: E402
from mod_editor.games.ncaa09_ps2.playbooks_lane import PlaybooksLane  # noqa: E402
from mod_editor.games.ncaa09_ps2 import art_pages, saves_lane  # noqa: E402
from mod_editor.games.ncaa09_ps2.texture_lane import (  # noqa: E402
    TextureLane,
    UniformDiscArtWriteLane,
)
from mod_editor.games.ncaa09_ps2 import IDENTITY  # noqa: E402


def _plain(value):
    """Serialise the read-only mappings the contract freezes a document into."""

    try:
        return dict(value)
    except TypeError:
        return str(value)


class SyntheticDiscTests(unittest.TestCase):
    """The fixture every lane stands on has the shapes the real disc has."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-lanes-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "synthetic.iso"
        self.source.write_bytes(containers.build_synthetic_disc())

    def test_the_disc_carries_the_containers_the_lanes_open(self) -> None:
        image = containers.open_disc(self.source)
        names = {entry.name for entry in containers.data_files(image)}
        for wanted in (containers.LEAGUE_CONTAINER, containers.GAME_DATA_CONTAINER,
                       containers.TEMPLATE_CONTAINER, *containers.PRELOAD_CACHES):
            self.assertIn(wanted, names)

    def test_a_synthetic_database_has_its_four_checksums_right(self) -> None:
        """A fixture with wrong CRCs would let a CRC check pass by never firing."""

        blob = containers.synthetic_tdb(tables=2)
        self.assertEqual(ea_tdb.verify_crcs(blob), [])
        sites = ea_tdb.crc_sites(blob)
        self.assertTrue(sites)
        self.assertTrue(all(site.matches for site in sites))

    def test_a_tampered_database_fails_its_checksums(self) -> None:
        blob = bytearray(containers.synthetic_tdb(tables=2))
        blob[-8] ^= 0xFF
        self.assertNotEqual(ea_tdb.verify_crcs(bytes(blob)), [])

    def test_the_preload_caches_name_the_containers_they_copy(self) -> None:
        image = containers.open_disc(self.source)
        named = containers.preload_names(image)
        self.assertEqual(set(named), set(containers.PRELOAD_CACHES))
        # Each cache names at least one container, and between them they name
        # LEAGUE.DAT -- the one the roster and identity rows write, and so the
        # one whose cache coherence the fixture has to exercise.
        for cache, names in named.items():
            self.assertTrue(names, cache)
        every = {name.upper() for names in named.values() for name in names}
        self.assertIn(containers.LEAGUE_CONTAINER.upper(), every)

    def test_a_cache_that_is_not_a_cache_is_refused_by_name(self) -> None:
        with self.assertRaises(Refusal) as caught:
            containers.parse_preload_cache(b"NOPE" + bytes(32), "FAKE.QKL")
        self.assertIn("QL01", str(caught.exception))

    def test_the_synthetic_disc_never_passes_as_retail(self) -> None:
        identity = Ncaa09DiscIdentifier(IDENTITY).identify(self.source)
        self.assertTrue(identity.serial_matches)
        self.assertFalse(identity.retail_executable)
        self.assertIn("unknown edition", identity.headline)

    def test_a_disc_that_boots_another_serial_is_refused(self) -> None:
        import ps2_iso9660 as iso_lib

        other = self.work / "other.iso"
        other.write_bytes(iso_lib.build_synthetic_iso(
            files=[(b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_999.99;1\r\n"),
                   (b"SLUS_999.99;1", b"\x7fELF" + bytes(4092))],
            sub_name=b"DATA", sub_files=[(b"NOTHING.DAT;1", b"\x00" * 16)]))
        with self.assertRaises(Refusal) as caught:
            Ncaa09DiscIdentifier(IDENTITY).identify(other)
        self.assertIn(containers.SERIAL, str(caught.exception))


class ReadOnlyLaneTests(unittest.TestCase):
    """Every read-only lane catalogues, refuses to write, and leaks no payload."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-readonly-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def _catalogue(self, lane):
        source = lane.synthetic_source(self.work)
        return source, lane.build_catalogue(source)

    def test_inventory_lists_the_containers_and_their_members(self) -> None:
        lane = InventoryLane()
        _source, catalogue = self._catalogue(lane)
        document = catalogue.document
        self.assertGreaterEqual(document["containers"], 5)
        self.assertGreater(document["members"], 0)
        self.assertIn("TDB", document["format_totals"])
        self.assertIn("MMAP", document["format_totals"])

    def test_database_lane_reports_the_schema_and_the_checksums(self) -> None:
        lane = DatabaseLane()
        _source, catalogue = self._catalogue(lane)
        document = catalogue.document
        self.assertGreater(document["databases"], 0)
        self.assertGreater(document["tables"], 0)
        self.assertGreater(document["fields"], 0)
        for row in document["rows"]:
            if row.get("note"):
                continue
            self.assertEqual(row["checksum_sites_wrong"], 0, row["path"])
            for table in row["tables"]:
                for field in table["fields"]:
                    self.assertEqual(set(field),
                                     {"name", "type", "bit_offset", "bit_width"})

    def test_database_lane_records_a_refused_database_rather_than_dropping_it(self) -> None:
        """Two of the real disc's 582 refuse; a catalogue that hid them would lie."""

        row = DatabaseLane._database_row("/DATA/FIXTURE.DAT", 7, b"DB" + bytes(30))
        self.assertEqual(row["member"], 7)
        self.assertEqual(row["tables"], [])
        self.assertTrue(row["note"], "the reader's own sentence belongs on the row")

    def test_the_database_catalogue_carries_no_record_contents(self) -> None:
        """A field name is the schema; a record's contents are the user's data."""

        lane = DatabaseLane()
        _source, catalogue = self._catalogue(lane)
        serialised = json.dumps(catalogue.document, default=_plain)
        for value in ("SYNTHETIC", "FIXTURE", "SYN", "FIX"):
            self.assertNotIn(value, serialised,
                             f"{value!r} is a record's contents and must not be here")

    def test_text_lane_measures_without_storing_a_string(self) -> None:
        lane = TextLane()
        _source, catalogue = self._catalogue(lane)
        document = catalogue.document
        self.assertGreater(document["text_members"], 0)
        self.assertGreater(document["slots"], 0)
        self.assertIn("FNTS", document["fonts"])
        serialised = json.dumps(document, default=_plain)
        for line in containers.SYNTHETIC_TEXT_LINES:
            self.assertNotIn(line, serialised)

    def test_text_slots_give_a_shortened_string_its_room_back(self) -> None:
        """The allocation is the room, not the string; that is what makes an edit
        reversible."""

        payload = b"HELLO\x00" + b"WORLD\x00"
        self.assertEqual(split_strings(payload), ("HELLO", "WORLD"))
        slots = slots_in(payload)
        self.assertEqual([(offset, length) for offset, length, _room in slots],
                         [(0, 5), (6, 5)])
        shortened = b"HI\x00\x00\x00\x00" + b"WORLD\x00"
        self.assertEqual(slots_in(shortened)[0][2], 5,
                         "a shortened slot keeps the room its padding occupies")

    def test_texture_lane_decodes_and_says_there_is_no_kit_table(self) -> None:
        """The census row became an exporter when the MMAP decoder moved into
        ``_formats``; what it still says is that no kit record exists to pair
        the art with."""

        lane = TextureLane()
        _source, catalogue = self._catalogue(lane)
        document = catalogue.document
        self.assertGreater(document["members_read"], 0)
        self.assertGreater(document["images_decodable"], 0)
        self.assertIn("0 rows", document["no_kit_table"])
        for row in document["rows"]:
            self.assertGreater(row["width"], 0)
            self.assertGreater(row["height"], 0)

    def test_every_read_only_lane_refuses_to_write_with_a_sentence(self) -> None:
        # DatabaseLane, TextLane and TextureLane were on this list until each
        # gained the half its page was missing; what stays here is the two
        # lanes whose whole promise is still the three things they will not do.
        for lane in (InventoryLane(),):
            source, catalogue = self._catalogue(lane)
            before = source.read_bytes()
            recipe = lane.compose_recipe(())
            for step, call in (
                ("plan", lambda: lane.plan(source, recipe, catalogue)),
                ("build", lambda: lane.build(source, self.work / "out.iso", recipe,
                                             catalogue)),
                ("verify", lambda: lane.verify(source, self.work / "out.iso", None)),
            ):
                with self.assertRaises(Refusal, msg=f"{lane.lane_id}.{step}") as caught:
                    call()
                self.assertGreater(len(str(caught.exception)), 40)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((self.work / "out.iso").exists())


class AudioExportTests(unittest.TestCase):
    """The two extract-only lanes export, verify, and fail on a tampered export."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-audio-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def _export(self, lane):
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        edits = lane.conformance_edits(catalogue)
        recipe = lane.compose_recipe(edits)
        destination = self.work / f"{lane.lane_id.replace('.', '-')}-manifest.json"
        receipt = lane.build(source, destination, recipe, catalogue, work_dir=self.work)
        return lane, source, destination, receipt

    def test_streams_export_and_verify(self) -> None:
        lane, source, destination, receipt = self._export(AudioStreamsLane())
        self.assertTrue(destination.is_file())
        self.assertTrue(receipt.artifacts)
        verdict = lane.verify(source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

    def test_banks_export_and_verify(self) -> None:
        lane, source, destination, receipt = self._export(AudioBanksLane())
        verdict = lane.verify(source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

    def test_a_tampered_export_fails_verification(self) -> None:
        lane, source, destination, receipt = self._export(AudioBanksLane())
        wav = [Path(a.path) for a in receipt.artifacts if a.kind == "wav"][0]
        blob = bytearray(wav.read_bytes())
        blob[-2] ^= 0xFF
        wav.write_bytes(bytes(blob))
        verdict = lane.verify(source, destination, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("not the file the receipt recorded", verdict.summary)

    def test_an_undeclared_file_in_the_export_folder_fails_verification(self) -> None:
        lane, source, destination, receipt = self._export(AudioBanksLane())
        root = lane.export_root_for(destination)
        (root / "stowaway.wav").write_bytes(b"RIFF")
        verdict = lane.verify(source, destination, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("undeclared", verdict.summary)

    def test_a_build_over_the_source_is_refused(self) -> None:
        lane = AudioBanksLane()
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
        with self.assertRaises(Refusal) as caught:
            lane.build(source, source, recipe, catalogue)
        self.assertIn("never the disc", str(caught.exception))

    def test_a_stream_whose_codec_has_no_decoder_is_refused_by_name(self) -> None:
        lane = AudioStreamsLane()
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        target = catalogue.targets[0]
        raw = dict(target.raw)
        raw["decodable"] = False
        raw["codec"] = "MicroTalk (EA speech, ~10:1)"
        problem = lane.check_edit(type(target)(**{**target.__dict__, "raw": raw}), {})
        self.assertIsNotNone(problem)
        self.assertIn("MicroTalk", problem)


class WriterTests(unittest.TestCase):
    """The five writers, end to end on the synthetic disc, and their refusals.

    Every one of them is proved the same way, because they are the same lane:
    plan, build a NEW image, verify with a verifier that imports none of the
    writer, and then break the destination in two different places and check
    the verdict flips.  What differs between them is the field map, which is
    exactly the thing this module could not borrow from Madden 09.
    """

    #: ``(lane, what the conformance edit is)`` for each writer.
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-writers-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def _write(self, lane):
        room = self.work / lane.lane_id.replace(".", "-")
        room.mkdir(parents=True, exist_ok=True)
        source = lane.synthetic_source(room)
        before = source.read_bytes()
        catalogue = lane.build_catalogue(source)
        edits = lane.conformance_edits(catalogue)
        self.assertTrue(edits, lane.lane_id)
        for edit in edits:
            self.assertIsNone(lane.check_edit(catalogue.target(edit.target_key),
                                              edit.values), lane.lane_id)
        recipe = lane.compose_recipe(edits)
        self.assertEqual(recipe["schema"], lane.recipe_schema)
        plan = lane.plan(source, recipe, catalogue)
        self.assertTrue(plan.declared_ranges, lane.lane_id)
        destination = room / "written.iso"
        receipt = lane.build(source, destination, recipe, catalogue)
        self.assertEqual(source.read_bytes(), before,
                         f"{lane.lane_id} touched its source")
        verdict = lane.verify(source, destination, receipt)
        self.assertTrue(verdict.passed, f"{lane.lane_id}: {verdict.summary}")
        return lane, source, destination, receipt, verdict

    def _writers(self):
        return (DatabaseLane(), IdentityLane(), TextLane(), PlaybooksLane(),
                UniformDiscArtWriteLane())

    def test_every_writer_plans_builds_and_verifies(self) -> None:
        for lane in self._writers():
            with self.subTest(lane=lane.lane_id):
                _lane, source, destination, _receipt, verdict = self._write(lane)
                self.assertEqual(destination.stat().st_size, source.stat().st_size,
                                 "a bounded write keeps the image's exact size")

    def test_every_writer_refuses_a_byte_changed_outside_what_it_declared(self) -> None:
        for lane in self._writers():
            with self.subTest(lane=lane.lane_id):
                _lane, source, destination, receipt, _verdict = self._write(lane)
                spans = [(item.start, item.length) for item in receipt.declared_ranges]
                offset = 0
                while any(start <= offset < start + length for start, length in spans):
                    offset += 1
                blob = bytearray(destination.read_bytes())
                blob[offset] ^= 0xFF
                destination.write_bytes(bytes(blob))
                verdict = lane.verify(source, destination, receipt)
                self.assertFalse(verdict.passed)
                self.assertIn("Verification failed", verdict.summary)

    def test_every_writer_refuses_a_destination_that_already_exists(self) -> None:
        for lane in self._writers():
            with self.subTest(lane=lane.lane_id):
                room = self.work / ("exists-" + lane.lane_id.replace(".", "-"))
                room.mkdir(parents=True, exist_ok=True)
                source = lane.synthetic_source(room)
                catalogue = lane.build_catalogue(source)
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                destination = room / "already.iso"
                destination.write_bytes(b"not empty")
                with self.assertRaises(Refusal) as caught:
                    lane.build(source, destination, recipe, catalogue)
                self.assertIn("already exists", str(caught.exception))
                self.assertEqual(destination.read_bytes(), b"not empty")

    def test_a_recipe_of_another_lanes_schema_is_refused_by_name(self) -> None:
        lane = DatabaseLane()
        room = self.work / "schema"
        room.mkdir(parents=True, exist_ok=True)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        with self.assertRaises(Refusal) as caught:
            lane.plan(source, {"schema": "somebody_else/v1", "edits": [{"target": "x"}]},
                      catalogue)
        self.assertIn(lane.recipe_schema, str(caught.exception))


class RosterFieldMapTests(unittest.TestCase):
    """What the roster editor offers, and the two things it must never offer."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-roster-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = DatabaseLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.player = next(t for t in self.catalogue.targets
                           if t.key.startswith("row:") and t.raw.get("table") == "PLAY")

    def test_no_name_field_is_offered_because_the_disc_has_none(self) -> None:
        offered = {item.key for item in self.player.fields}
        self.assertNotIn("PFNA", offered)
        self.assertNotIn("PLNA", offered)
        self.assertNotIn("PAGE", offered)

    def test_the_class_and_the_redshirt_flag_stand_in_for_an_age(self) -> None:
        offered = {item.key for item in self.player.fields}
        self.assertIn("PYER", offered)
        self.assertIn("PRSD", offered)

    def test_a_rating_stops_at_the_five_bit_field_s_own_ceiling(self) -> None:
        overall = next(item for item in self.player.fields if item.key == "POVR")
        self.assertEqual(overall.maximum, 31,
                         "a five-bit field holds 0..31 and the editor may not claim 0..99")
        self.assertIsNone(self.lane.check_edit(self.player, {"POVR": 31}))
        problem = self.lane.check_edit(self.player, {"POVR": 32})
        self.assertIsNotNone(problem)
        self.assertIn("31", problem)

    def test_a_field_this_lane_does_not_write_is_refused_by_name(self) -> None:
        problem = self.lane.check_edit(self.player, {"PFNA": "Nope"})
        self.assertIsNotNone(problem)
        self.assertIn("PFNA", problem)

    def test_the_league_database_is_not_this_page_s_to_edit(self) -> None:
        members = {t.raw.get("member") for t in self.catalogue.targets
                   if t.key.startswith("row:")}
        self.assertNotIn(0, members,
                         "member 0 is the league database and the identity page's subject")


class IdentityFieldMapTests(unittest.TestCase):
    """The identity page offers names and, deliberately, no colour."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-identity-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = IdentityLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_no_colour_control_exists_and_the_document_says_why(self) -> None:
        for target in self.catalogue.targets:
            for item in target.fields:
                self.assertNotIn(item.key, ("TBCR", "TBCG", "TBCB", "TB2R", "TB2G", "TB2B",
                                            "TLNA", "TMNC"))
        note = self.catalogue.document["colour_note"]
        self.assertIn("no colour field", note)
        self.assertIn("PACL", note)

    def test_the_palette_is_read_and_reported_as_a_count(self) -> None:
        palette = self.catalogue.document["palette"]
        self.assertGreater(palette["rows"], 0)
        self.assertEqual(sorted(palette["fields"]), ["CBLU", "CGRN", "CRED", "PCID"])

    def test_only_the_league_database_is_editable(self) -> None:
        members = {t.raw.get("member") for t in self.catalogue.targets
                   if t.key.startswith("row:")}
        self.assertEqual(members, {0})

    def test_a_name_longer_than_its_field_is_refused_with_the_budget(self) -> None:
        team = next(t for t in self.catalogue.targets
                    if t.key.startswith("row:") and t.raw.get("table") == "TEAM")
        budget = next(item.maximum for item in team.fields if item.key == "TSNA")
        problem = self.lane.check_edit(team, {"TSNA": "X" * (budget + 1)})
        self.assertIsNotNone(problem)
        self.assertIn(str(budget), problem)


class PlaybookTests(unittest.TestCase):
    """A rename is possible on this disc and an insertion is not."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-books-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = PlaybooksLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_the_play_name_is_in_plyl_and_not_in_pbpl(self) -> None:
        tables = {t.raw.get("table") for t in self.catalogue.targets
                  if t.key.startswith("row:")}
        self.assertIn("PLYL", tables)
        self.assertNotIn("PBPL", tables,
                         "PBPL has no name field on this disc; that is why the Madden "
                         "writer does not port")

    def test_the_page_says_the_tables_are_packed_full(self) -> None:
        self.assertIn("packed exactly full", self.catalogue.document["packed_full"])

    def test_a_member_that_is_not_a_playbook_offers_no_row(self) -> None:
        source = self.work / "not-books.iso"
        source.write_bytes(containers.build_synthetic_disc())
        catalogue = self.lane.build_catalogue(source)
        self.assertFalse([t for t in catalogue.targets if t.key.startswith("row:")],
                         "a TDB that is not a playbook must not offer a rename")


class DraftClassTests(unittest.TestCase):
    """The Saves page recognises a class, reads it, and refuses to write one."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-class-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = saves_lane.DraftClassLane()
        self.source = self.lane.synthetic_source(self.work)

    def test_a_class_is_recognised_by_its_length_and_its_header(self) -> None:
        blob = self.source.read_bytes()
        self.assertEqual(len(blob), saves_lane.FILE_BYTES)
        self.assertTrue(saves_lane.is_draft_class(blob))
        self.assertFalse(saves_lane.is_draft_class(blob[:-1]))
        self.assertFalse(saves_lane.is_draft_class(b"\x00" * saves_lane.FILE_BYTES))

    def test_every_slot_is_filled_because_an_empty_one_hangs_the_game(self) -> None:
        catalogue = self.lane.build_catalogue(self.source)
        self.assertEqual(catalogue.document["empty_records"], 0)
        self.assertEqual(catalogue.document["records"], saves_lane.RECORD_COUNT)

    def test_the_catalogue_carries_no_record_contents(self) -> None:
        catalogue = self.lane.build_catalogue(self.source)
        blob = json.dumps(_plain(catalogue.document), default=str)
        self.assertNotIn("SynthPick", blob)
        self.assertNotIn("Filler", blob)

    def test_a_disc_handed_to_the_saves_page_is_refused_by_name(self) -> None:
        disc = self.work / "disc.iso"
        disc.write_bytes(containers.build_synthetic_disc())
        with self.assertRaises(Refusal) as caught:
            self.lane.build_catalogue(disc)
        self.assertIn(saves_lane.SAVE_DIRECTORY, str(caught.exception))

    def test_the_identifier_names_a_class_rather_than_refusing_it(self) -> None:
        identity = Ncaa09DiscIdentifier(IDENTITY).identify(self.source)
        self.assertTrue(identity.serial_matches)
        self.assertFalse(identity.retail_executable)
        self.assertIn("draft class", identity.headline)

    def test_the_page_refuses_to_write_and_names_where_the_writer_is(self) -> None:
        catalogue = self.lane.build_catalogue(self.source)
        problem = self.lane.check_edit(catalogue.targets[0], {})
        self.assertIn("NCAA-Draft-Class-Editor", problem)
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, self.lane.compose_recipe(()), catalogue)


class ArtPageTests(unittest.TestCase):
    """Four pages, one lane, and the containers each is pointed at."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-art-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_every_art_page_names_containers_this_disc_really_ships(self) -> None:
        known = set(containers.UNIFORM_CONTAINERS + containers.FACE_CONTAINERS
                    + containers.STADIUM_CONTAINERS + containers.FIELD_ART_CONTAINERS
                    + containers.PRESENTATION_CONTAINERS)
        for lane_class in art_pages.ART_PAGE_LANES:
            lane = lane_class()
            with self.subTest(page=lane.page):
                self.assertTrue(lane.art_containers)
                for name, _group, note in lane.art_containers:
                    self.assertIn(name, known)
                    self.assertGreater(len(note), 40)

    def test_every_art_page_says_what_it_does_not_edit(self) -> None:
        for lane_class in art_pages.ART_PAGE_LANES:
            lane = lane_class()
            with self.subTest(page=lane.page):
                self.assertGreater(len(lane.page_scope), 80)

    def test_each_art_page_writes_and_verifies_on_the_synthetic_disc(self) -> None:
        for lane_class in art_pages.ART_PAGE_LANES:
            lane = lane_class()
            with self.subTest(page=lane.page):
                room = self.work / lane.page
                room.mkdir(parents=True, exist_ok=True)
                source = lane.synthetic_source(room)
                catalogue = lane.build_catalogue(source)
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                destination = room / "written.iso"
                receipt = lane.build(source, destination, recipe, catalogue)
                verdict = lane.verify(source, destination, receipt)
                self.assertTrue(verdict.passed, f"{lane.page}: {verdict.summary}")

    def test_no_identity_is_confirmed_because_no_dump_is_paired_with_this_disc(self) -> None:
        lane = art_pages.StadiumArtLane()
        self.assertIsNone(lane.identity_document)
        room = self.work / "identity"
        room.mkdir(parents=True, exist_ok=True)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        note = lane.identity_note(catalogue.targets[0])
        self.assertNotIn("Confirmed by a PCSX2 dump", note)


class SharedLaneBaseTests(unittest.TestCase):
    """What the two games share, asserted rather than assumed."""

    def test_both_games_instantiate_the_same_bases(self) -> None:
        from mod_editor.games._lanes import tdb_records, terf_art, text_banks
        from mod_editor.games.madden09_ps2 import team_data as madden_tdb
        from mod_editor.games.madden09_ps2 import text_lane as madden_text
        from mod_editor.games.madden09_ps2 import uniform_art as madden_art

        self.assertTrue(issubclass(DatabaseLane, tdb_records.TdbRecordLane))
        self.assertTrue(issubclass(IdentityLane, tdb_records.TdbRecordLane))
        self.assertTrue(issubclass(PlaybooksLane, tdb_records.TdbRecordLane))
        self.assertTrue(issubclass(madden_tdb.TeamDataLane, tdb_records.TdbRecordLane))
        self.assertTrue(issubclass(TextLane, text_banks.TextBankLane))
        self.assertTrue(issubclass(madden_text.TextLane, text_banks.TextBankLane))
        self.assertTrue(issubclass(TextureLane, terf_art.TerfArtLane))
        self.assertTrue(issubclass(madden_art.UniformArtLane, terf_art.TerfArtLane))
        for lane_class in art_pages.ART_PAGE_LANES:
            self.assertTrue(issubclass(lane_class, terf_art.TerfArtWriteLane))

    def test_the_shared_mmap_fixture_is_the_one_both_games_use(self) -> None:
        from mod_editor.games._lanes import synthetic_art
        from mod_editor.games.madden09_ps2 import containers as madden_containers

        self.assertIs(madden_containers.synthetic_mmap, synthetic_art.synthetic_mmap)
        self.assertEqual(containers.synthetic_texture_member(8, 8, seed=4),
                         synthetic_art.synthetic_mmap(8, 8, seed=4, mips=1, images=1,
                                                      retail_layout=True))

    def test_a_base_never_reaches_into_a_game(self) -> None:
        import mod_editor.games._lanes as lanes_package

        root = Path(lanes_package.__file__).resolve().parent
        for path in sorted(root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for game in ("madden09_ps2", "ncaa09_ps2", "nfl2k5_ps2"):
                self.assertNotIn(f"import {game}", text, path.name)
                self.assertNotIn(f"games.{game}", text, path.name)


class PreloadCacheTests(unittest.TestCase):
    """The rule that decides what a write costs on this disc."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ncaa09-cache-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "synthetic.iso"
        self.source.write_bytes(containers.build_synthetic_disc())

    def test_every_cached_copy_equals_what_it_copies(self) -> None:
        from mod_editor.games._formats import ea_terf

        image = containers.open_disc(self.source)
        files = {entry.name.upper(): entry for entry in containers.data_files(image)}
        copies = containers.preload_copies(image)
        self.assertTrue(copies)
        checked = 0
        for name, row in copies.items():
            blob = containers.read_file(image, files[name.upper()], limit=None)
            parsed = ea_terf.parse_terf(blob, allow_size_mismatch=True)
            for copy in list(row.header) + [c for v in row.members.values() for c in v]:
                cache = containers.read_file(image, files[copy.cache.upper()], limit=None)
                length = copy.length_in(parsed)
                wanted = (blob[:length] if copy.is_header
                          else parsed.stored(int(copy.member)))
                self.assertEqual(cache[copy.offset:copy.offset + length], wanted,
                                 f"{copy.cache} copy of {name}")
                checked += 1
        self.assertGreater(checked, 4)

    def test_a_disc_without_caches_is_still_a_disc_the_lanes_open(self) -> None:
        bare = self.work / "no-caches.iso"
        bare.write_bytes(containers.build_synthetic_disc(preload_caches=False))
        image = containers.open_disc(bare)
        self.assertEqual(containers.preload_copies(image), {})
        lane = DatabaseLane()
        catalogue = lane.build_catalogue(bare)
        self.assertTrue(catalogue.targets)

    def test_the_writable_text_containers_are_named_by_no_cache(self) -> None:
        from mod_editor.games.ncaa09_ps2 import text_lane as ncaa_text

        self.assertEqual(sorted(ncaa_text.PRELOAD_COPIES), ["GAMEDATA.DAT"])
        for name in ncaa_text.WRITABLE_TEXT_CONTAINERS:
            self.assertNotIn(name, ncaa_text.PRELOAD_COPIES)


if __name__ == "__main__":
    unittest.main()
