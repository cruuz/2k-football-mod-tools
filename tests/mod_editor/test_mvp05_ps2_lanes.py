"""The MVP Baseball 2005 (PS2) lanes, proved on the synthetic disc.  No game data.

Each writer lane: the catalogue lists targets, a known-good edit plans, builds a
NEW image and verifies; a byte changed outside the declared ranges fails the
verifier; the refusal sentences are the lanes' own.  Each read-only lane:
catalogues, and refuses every write with its one sentence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_big, ea_schl, ea_shps  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.mvp05_ps2 import (  # noqa: E402
    GAME, LANES, art_lane, audio_lane, containers, database_lane, disc_identity, loch_lane,
    loch_text,
)


class _Room(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="mvp05-lanes-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def _round_trip(self, lane, edits=None):
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        self.assertTrue(catalogue.targets)
        edits = edits or lane.conformance_edits(catalogue)
        for edit in edits:
            self.assertIsNone(lane.check_edit(catalogue.target(edit.target_key), edit.values))
        recipe = lane.compose_recipe(edits)
        plan = lane.plan(source, recipe, catalogue)
        self.assertTrue(plan.declared_ranges)
        destination = self.work / f"{lane.lane_id}.out.iso"
        receipt = lane.build(source, destination, recipe, catalogue)
        self.assertEqual(destination.stat().st_size, source.stat().st_size)
        verdict = lane.verify(source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        # A byte outside the declared ranges fails the verifier.
        declared = set()
        for item in receipt.declared_ranges:
            declared.update(range(item.start, item.start + item.length))
        victim = next(offset for offset in range(2048 * 16, destination.stat().st_size)
                      if offset not in declared)
        tampered = self.work / f"{lane.lane_id}.tampered.iso"
        data = bytearray(destination.read_bytes())
        data[victim] ^= 0xFF
        tampered.write_bytes(bytes(data))
        self.assertFalse(lane.verify(source, tampered, receipt).passed)
        return source, catalogue, destination, receipt


class ModuleTests(_Room):
    def test_every_lane_is_registered_and_on_a_page(self) -> None:
        self.assertEqual(len(LANES), 13)
        self.assertEqual({lane.lane_id for lane in LANES}, {
            "rosters.database_tables", "identity.team_tables", "playbooks.tuning_tables",
            "identity.ui_strings", "stadiums.park_textures", "presentation.overlay_textures",
            "menus.widget_textures", "audio.streams", "audio.banks", "uniforms.kit_banks",
            "rosters.face_banks", "field_art.banks", "textures.bank_inventory"})
        self.assertEqual(GAME.identity.serials, (containers.SERIAL,))

    def test_the_identifier_names_the_synthetic_disc_as_not_retail(self) -> None:
        source = database_lane.ROSTER_LANE.synthetic_source(self.work)
        identity = GAME.identifier.identify(source)
        self.assertEqual(identity.serial, containers.SERIAL)
        self.assertFalse(identity.retail_executable)
        self.assertIn(disc_identity.UNKNOWN_EDITION, identity.headline)
        wrong = self.work / "wrong.iso"
        wrong.write_bytes(containers.iso_lib.build_synthetic_iso())
        with self.assertRaises(Refusal) as caught:
            GAME.identifier.identify(wrong)
        self.assertIn("this studio reads the MVP Baseball 2005", str(caught.exception))


class TableLaneTests(_Room):
    def test_the_three_table_lanes_round_trip(self) -> None:
        for lane in (database_lane.ROSTER_LANE, database_lane.IDENTITY_LANE, database_lane.TUNING_LANE):
            self._round_trip(lane)

    def test_the_edited_cell_is_in_the_new_image_and_nothing_else_moved(self) -> None:
        lane = database_lane.ROSTER_LANE
        source, catalogue, destination, receipt = self._round_trip(lane)
        cell = receipt.document["cells"][0]
        with containers.Disc(destination) as disc:
            archive = disc.archive(disc.find(containers.DATABASE_ARCHIVE))
            from mod_editor.games._formats import ea_csv_db
            table = ea_csv_db.parse_table(archive.member("attrib.dat"), "attrib.dat")
        column = table.columns().index(cell["column"])
        self.assertEqual(table.cell(cell["line"], column), cell["after"])

    def test_refusals_name_the_fix(self) -> None:
        lane = database_lane.ROSTER_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        target = catalogue.targets[0]
        self.assertIn("is not a column", lane.check_edit(target, {"nope": "x"}))
        self.assertIn("comma", lane.check_edit(target, {"first_name": "a,b"}))
        self.assertIn("keep the column's kind", lane.check_edit(target, {"playerattrib_jerseynum": "ten"}))
        with self.assertRaises(Refusal) as caught:
            lane.plan(source, {"schema": lane.recipe_schema, "edits": []}, catalogue)
        self.assertIn("non-empty 'edits' list", str(caught.exception))
        with self.assertRaises(Refusal):
            lane.plan(source, lane.compose_recipe((Edit("DATABASE.BIG!attrib.dat#99", {"first_name": "x"}),)), catalogue)

    def test_a_table_that_no_longer_fits_its_slot_is_refused_by_byte_count(self) -> None:
        lane = database_lane.ROSTER_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        # Random text in every row of the table defeats the re-pack.
        import random
        random.seed(3)
        edits = []
        for target in catalogue.targets:
            if target.raw["table"] != "attrib.dat":
                continue
            noise = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(60))
            edits.append(Edit(target.key, {"first_name": noise, "last_name": noise[::-1]}))
        with self.assertRaises(Refusal) as caught:
            lane.plan(source, lane.compose_recipe(edits), catalogue)
        self.assertIn("once RefPack-packed", str(caught.exception))
        self.assertIn("Nothing was changed", str(caught.exception))


class StringLaneTests(_Room):
    def test_the_strings_lane_round_trips(self) -> None:
        source, catalogue, destination, receipt = self._round_trip(loch_lane.LANE)
        row = receipt.document["strings"][0]
        with containers.Disc(destination) as disc:
            parsed = loch_text.parse(disc.file_bytes(disc.find(row["file"])), row["file"])
        self.assertEqual(parsed.string(row["index"]).text, row["text"])

    def test_a_string_longer_than_its_span_is_refused_with_the_count(self) -> None:
        lane = loch_lane.LANE
        catalogue = lane.build_catalogue(lane.synthetic_source(self.work))
        target = catalogue.targets[0]
        self.assertIn("shorten it by", lane.check_edit(target, {"text": "x" * 400}))
        self.assertIn("NUL", lane.check_edit(target, {"text": "a\x00b"}))
        self.assertIsNone(lane.check_edit(target, {"text": ""}))

    def test_loch_parse_and_replace_are_exact(self) -> None:
        payload = containers.synthetic_loch(("ONE", "TWO TWO", "THREE"))
        parsed = loch_text.parse(payload, "t.loc")
        self.assertEqual([s.text for s in parsed.strings], ["ONE", "TWO TWO", "THREE"])
        out, (offset, span) = parsed.replace(1, "TW")
        self.assertEqual(len(out), len(payload))
        again = loch_text.parse(out, "t.loc")
        self.assertEqual(again.string(1).text, "TW")
        self.assertEqual(out[:offset], payload[:offset])
        self.assertEqual(out[offset + span:], payload[offset + span:])
        with self.assertRaises(Refusal):
            parsed.replace(1, "MUCH TOO LONG FOR THE SPAN")
        with self.assertRaises(Refusal):
            loch_text.parse(b"NOPE" + bytes(32))


class ArtLaneTests(_Room):
    def test_the_four_art_writers_round_trip(self) -> None:
        for lane in (art_lane.STADIUM_LANE, art_lane.PRESENTATION_LANE, art_lane.MENU_LANE,
                     art_lane.KIT_LANE):
            self._round_trip(lane)

    def test_export_and_the_written_pixels_agree(self) -> None:
        lane = art_lane.PRESENTATION_LANE
        source, catalogue, destination, receipt = self._round_trip(lane)
        row = receipt.document["textures"][0]
        png_in = Path(row["png"]).read_bytes()
        png_out = lane.decode_png_by_key(destination, row["texture"])
        self.assertEqual(art_lane.read_rgba_png(png_in), art_lane.read_rgba_png(png_out))

    def test_refusals_and_identities(self) -> None:
        lane = art_lane.MENU_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        direct = next(t for t in catalogue.targets if t.raw["code"] == "0x05")
        blocked = next(t for t in catalogue.targets if t.raw["code"] == "0x0e")
        indexed = next(t for t in catalogue.targets if t.raw["code"] == "0x02" and t.raw["palette_entries"] == 256)
        short = next(t for t in catalogue.targets if t.raw["code"] == "0x02" and t.raw["palette_entries"] != 256)
        png = self.work / "wrong.png"
        png.write_bytes(ea_shps.encode_png(2, 2, bytes(16)))
        self.assertIn("no encoder for code 0x05", lane.check_edit(direct, {"png": str(png)}))
        self.assertIn("0x0e", lane.check_edit(blocked, {"png": str(png)}))
        self.assertIn("give a PNG of exactly that size", lane.check_edit(indexed, {"png": str(png)}))
        self.assertIsNone(lane.check_edit(indexed, {}))
        name = lane.replacement_identity(indexed)
        self.assertIsNotNone(name)
        self.assertTrue(name.endswith(".png"))
        self.assertIn("Derived", lane.identity_note(indexed))
        self.assertIsNone(lane.replacement_identity(short))
        self.assertIn("256-entry CLUT", lane.identity_note(short))
        # Direct colour exports even though it is not written.
        self.assertTrue(lane.decode_png_by_key(source, direct.key).startswith(b"\x89PNG"))
        with self.assertRaises(Refusal):
            lane.decode_png_by_key(source, blocked.key)

    def test_the_read_only_lanes_list_and_refuse(self) -> None:
        for lane in (art_lane.UNIFORM_LANE, art_lane.FACE_LANE, art_lane.FIELD_ART_LANE):
            source = lane.synthetic_source(self.work)
            catalogue = lane.build_catalogue(source)
            self.assertTrue(catalogue.targets)
            self.assertEqual(catalogue.document["decodable"], 0)
            self.assertEqual(lane.check_edit(catalogue.targets[0], {}), art_lane.BLOCK_CODEC_REFUSAL)
            with self.assertRaises(Refusal):
                lane.plan(source, {}, catalogue)

    def test_the_kit_lane_writes_the_8bit_parts_and_refuses_the_block_codec_ones(self) -> None:
        """The kit page's whole point: llod and hat are writable, jers and jerk are not."""

        lane = art_lane.KIT_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        by_tag = {}
        for target in catalogue.targets:
            by_tag.setdefault(target.raw["tag"], []).append(target)
        # The measured vocabulary: these tags are 8-bit on the disc and these are not.
        for tag in ("llod", "hat", "lace", "A___", "zig0", "a___"):
            self.assertTrue(by_tag[tag], tag)
            self.assertTrue(all(t.raw["code"] == art_lane.INDEXED8 for t in by_tag[tag]), tag)
        for tag in ("jers", "jerk", "shoe", "face"):
            self.assertTrue(by_tag[tag], tag)
            self.assertTrue(all(t.raw["code"] == "0x0e" for t in by_tag[tag]), tag)
        png = self.work / "kit-wrong.png"
        png.write_bytes(ea_shps.encode_png(2, 2, bytes(16)))
        self.assertIn("0x0e", lane.check_edit(by_tag["jers"][0], {"png": str(png)}))
        self.assertIn("give a PNG of exactly that size",
                      lane.check_edit(by_tag["llod"][0], {"png": str(png)}))
        with self.assertRaises(Refusal):
            lane.decode_png_by_key(source, by_tag["jers"][0].key)
        # One llod written back, and its pixels come out again.
        llod = by_tag["llod"][0]
        exported = lane.decode_png_by_key(source, llod.key)
        width, height, rgba = art_lane.read_rgba_png(exported)
        rolled = bytes(rgba[width * 4:]) + bytes(rgba[:width * 4])
        replacement = self.work / "kit-llod.png"
        replacement.write_bytes(ea_shps.encode_png(width, height, rolled))
        _s, _c, destination, receipt = self._round_trip(
            lane, (Edit(llod.key, {"png": str(replacement)}, note="one llod, rolled"),))
        self.assertEqual(receipt.document["textures"][0]["texture"], llod.key)
        self.assertEqual(art_lane.read_rgba_png(lane.decode_png_by_key(destination, llod.key)),
                         (width, height, rolled))

    def test_the_parts_census_names_every_bank_family_and_counts_the_writable_ones(self) -> None:
        lane = art_lane.KIT_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        census = art_lane.parts_census(catalogue.document["rows"], source="synthetic.iso")
        self.assertEqual(census["schema"], art_lane.PARTS_SCHEMA)
        families = {group["family"]: group for group in census["families"]}
        self.assertEqual(set(families), {"kit", "lettering", "head"})
        self.assertEqual(families["head"]["writable"], 0)
        self.assertEqual(families["lettering"]["writable"], families["lettering"]["images"])
        self.assertLess(families["kit"]["writable"], families["kit"]["images"])
        self.assertEqual(census["totals"]["images"], catalogue.document["images"])
        self.assertEqual(census["totals"]["writable"],
                         sum(1 for t in catalogue.targets if t.raw["code"] == art_lane.INDEXED8))
        parts = {part["tag"]: part for part in census["parts"]}
        self.assertEqual(parts["llod"]["codes"], {art_lane.INDEXED8: parts["llod"]["images"]})
        self.assertEqual(parts["jers"]["writable"], 0)
        self.assertIn("team_artid", census["team_artid_rule"])
        # A bank the naming rule does not know is "other", never a guess.
        self.assertEqual(art_lane.bank_family("u012a.ssh"), ("kit", 12, "a"))
        self.assertEqual(art_lane.bank_family("f012b.ssh"), ("lettering", 12, "b"))
        self.assertEqual(art_lane.bank_family("c012.ssh"), ("head", 12, None))
        self.assertEqual(art_lane.bank_family("umpire.ssh"), ("kit", None, None))
        self.assertEqual(art_lane.bank_family("teamfont.ssh"), ("lettering", None, None))
        self.assertEqual(art_lane.bank_family("whatever.ssh"), ("other", None, None))

    def test_the_slot_fit_census_measures_the_writers_own_bound(self) -> None:
        lane = art_lane.KIT_LANE
        source = lane.synthetic_source(self.work)
        census = art_lane.slot_fit_census(source, lane.walker.archives)
        self.assertGreater(census["banks"], 0)
        self.assertEqual(census["fit"], census["banks"] - len(census["over_the_slot"]))
        self.assertLessEqual(census["headroom_min"], census["headroom_max"])
        self.assertEqual(set(census["by_family"]), {"kit", "lettering", "head"})

    def test_png_reader_handles_every_colour_type_and_filter(self) -> None:
        import zlib
        import binascii

        def png(colour, channels, filt):
            width, height = 3, 2
            raw = bytearray()
            for y in range(height):
                raw.append(filt)
                line = bytes(((x * 40 + y * 90 + c * 17) & 0xFF) for x in range(width) for c in range(channels))
                raw += line
            def chunk(tag, body):
                return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", binascii.crc32(tag + body) & 0xFFFFFFFF)
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
        for colour, channels in ((0, 1), (2, 3), (4, 2), (6, 4)):
            width, height, rgba = art_lane.read_rgba_png(png(colour, channels, 0))
            self.assertEqual((width, height, len(rgba)), (3, 2, 24))
        with self.assertRaises(Refusal):
            art_lane.read_rgba_png(b"not a png")


class AudioLaneTests(_Room):
    def test_the_stream_lane_round_trips_and_exports(self) -> None:
        lane = audio_lane.STREAMS_LANE
        source, catalogue, destination, receipt = self._round_trip(lane)
        row = receipt.document["sounds"][0]
        wav = lane.decode_wav_by_key(destination, row["sound"])
        self.assertTrue(wav.startswith(b"RIFF"))
        speech = next(t for t in catalogue.targets if t.raw["codec"] == ea_schl.CODEC_SPEECH)
        with self.assertRaises(Refusal) as caught:
            lane.decode_wav_by_key(source, speech.key)
        self.assertIn(ea_schl.SPEECH_REFUSAL, str(caught.exception))
        self.assertIn("cannot be replaced", lane.check_edit(speech, {"wav": str(lane._fixture_wav)}))
        archived = next(t for t in catalogue.targets if t.raw["kind"] == "entry")
        self.assertFalse(archived.raw["writable"])
        big = self.work / "big.wav"
        big.write_bytes(ea_schl.wav_bytes(ea_schl.synthetic_pcm(200000, 2, sample_rate=24000), 24000, 2))
        writable = next(t for t in catalogue.targets if t.raw["writable"])
        self.assertIn("trim it", lane.check_edit(writable, {"wav": str(big)}))

    def test_the_bank_lane_exports_and_verifies(self) -> None:
        lane = audio_lane.BANKS_LANE
        source = lane.synthetic_source(self.work)
        catalogue = lane.build_catalogue(source)
        self.assertTrue(catalogue.targets)
        recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
        destination = self.work / "banks.json"
        receipt = lane.build(source, destination, recipe, catalogue)
        self.assertTrue(receipt.artifacts)
        self.assertTrue(lane.verify(source, destination, receipt).passed)
        extra = Path(receipt.document["export_folder"]) / "stray.txt"
        extra.write_text("x", encoding="utf-8")
        self.assertFalse(lane.verify(source, destination, receipt).passed)
        self.assertIn("not something this lane takes", lane.check_edit(catalogue.targets[0], {"wav": "x"}))


class InventoryTests(_Room):
    def test_the_inventory_counts_every_archive(self) -> None:
        from mod_editor.games.mvp05_ps2 import inventory_lane
        lane = inventory_lane.LANE
        catalogue = lane.build_catalogue(lane.synthetic_source(self.work))
        self.assertEqual(catalogue.document["archives"], len(catalogue.targets))
        self.assertGreater(catalogue.document["banks"], 0)
        self.assertIn("0x0e", catalogue.document["codes"])
        self.assertEqual(lane.check_edit(catalogue.targets[0], {}), lane.REFUSAL)


if __name__ == "__main__":
    unittest.main()
