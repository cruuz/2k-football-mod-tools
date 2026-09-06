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
from mod_editor.games.ncaa09_ps2.texture_lane import TextureLane  # noqa: E402
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

    def test_the_preload_caches_name_the_container_they_copy(self) -> None:
        image = containers.open_disc(self.source)
        named = containers.preload_names(image)
        self.assertEqual(set(named), set(containers.PRELOAD_CACHES))
        for cache, containers_named in named.items():
            self.assertIn(containers.LEAGUE_CONTAINER.upper(),
                          [name.upper() for name in containers_named], cache)

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
        self.assertEqual(document["crc_sites_differ"], 0)
        self.assertGreater(document["crc_sites_agree"], 0)
        shapes = document["schemas"]
        self.assertTrue(shapes)
        for shape in shapes.values():
            for table in shape["tables"]:
                for field in table["fields"]:
                    self.assertEqual(set(field), {"name", "type", "type_name",
                                                  "bits", "offset"})

    def test_database_lane_records_a_refused_database_rather_than_dropping_it(self) -> None:
        """Two of the real disc's 582 refuse; a catalogue that hid them would lie."""

        lane = DatabaseLane()
        row, refused = lane._describe(b"DB" + bytes(30), "FIXTURE.DAT", 7, {})
        self.assertEqual(row, {})
        self.assertIsNotNone(refused)
        self.assertEqual(refused["where"], "FIXTURE.DAT:7")
        self.assertEqual(refused["reader"], "ea_tdb.parse_tdb")
        self.assertTrue(refused["sentence"])

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

    def test_texture_lane_reads_headers_and_never_claims_a_pixel(self) -> None:
        lane = TextureLane()
        _source, catalogue = self._catalogue(lane)
        document = catalogue.document
        self.assertGreater(document["mmap_members"], 0)
        self.assertIn("never imports another game", document["decoder"])
        for row in document["rows"]:
            self.assertGreater(row["width"], 0)
            self.assertGreater(row["height"], 0)

    def test_every_read_only_lane_refuses_to_write_with_a_sentence(self) -> None:
        for lane in (InventoryLane(), DatabaseLane(), TextLane(), TextureLane()):
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


if __name__ == "__main__":
    unittest.main()
