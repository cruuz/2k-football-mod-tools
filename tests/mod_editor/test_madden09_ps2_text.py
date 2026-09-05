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

from mod_editor.games.contract import Edit, Refusal  # noqa: E402
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


class SlotTests(unittest.TestCase):
    def test_a_slot_is_a_string_and_the_room_up_to_the_next_one(self) -> None:
        payload = b"AAA\x00BBB\x00"
        self.assertEqual(text_lane.slots_in(payload), ((0, 3, 3), (4, 3, 3)))

    def test_padding_a_previous_edit_left_is_still_this_slot_s_room(self) -> None:
        """The property that makes an edit reversible rather than one-way."""

        payload = b"A\x00\x00\x00BBB\x00"
        self.assertEqual(text_lane.slots_in(payload), ((0, 1, 3), (4, 3, 3)))

    def test_a_member_that_ends_without_a_terminator_uses_every_byte(self) -> None:
        self.assertEqual(text_lane.slots_in(b"HELLO"), ((0, 5, 5),))

    def test_an_empty_member_has_no_slot(self) -> None:
        self.assertEqual(text_lane.slots_in(b"\x00\x00"), ())

    def test_encode_pads_with_the_terminator(self) -> None:
        self.assertEqual(text_lane.encode_slot("HI", 6), b"HI\x00\x00\x00\x00")

    def test_encode_fills_an_exact_fit_with_no_terminator(self) -> None:
        self.assertEqual(text_lane.encode_slot("ABCDEF", 6), b"ABCDEF")

    def test_encode_refuses_a_longer_replacement_with_the_length_it_must_fit(self) -> None:
        with self.assertRaises(Refusal) as caught:
            text_lane.encode_slot("ABCDEFG", 6)
        self.assertIn("shorten it to 6", str(caught.exception))

    def test_encode_refuses_a_nul_and_says_why(self) -> None:
        with self.assertRaises(Refusal) as caught:
            text_lane.encode_slot("A\x00B", 6)
        self.assertIn("ends a string", str(caught.exception))

    def test_encode_refuses_text_the_encoding_cannot_carry(self) -> None:
        with self.assertRaises(Refusal) as caught:
            text_lane.encode_slot("中", 6)
        self.assertIn("latin-1", str(caught.exception))

    def test_a_shortened_bank_is_still_a_bank(self) -> None:
        """``identify_member`` alone would lose it; this lane must not."""

        from mod_editor.games._formats import ea_terf

        shortened = b"HI" + bytes(36) + b"THE REST OF THE BANK IS STILL HERE"
        self.assertNotEqual(ea_terf.identify_member(shortened), ea_terf.FORMAT_TEXT)
        self.assertTrue(text_lane.is_text_member(shortened))

    def test_a_member_with_a_known_magic_is_never_called_text(self) -> None:
        from mod_editor.games._formats import ea_terf

        self.assertFalse(text_lane.is_text_member(ea_terf.MMAP_MAGIC + bytes(28)))


class KeyTests(unittest.TestCase):
    def test_a_slot_key_round_trips(self) -> None:
        key = text_lane.slot_key("STRYTEXT.DAT", 12, 480)
        self.assertEqual(text_lane.parse_slot_key(key), ("STRYTEXT.DAT", 12, 480))

    def test_a_key_of_another_shape_names_the_spelling(self) -> None:
        with self.assertRaises(Refusal) as caught:
            text_lane.parse_slot_key("nonsense")
        self.assertIn("<container>:<member>", str(caught.exception))


class TextLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-text-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = text_lane.TextLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.slot = self.catalogue.targets[0]

    def test_the_lane_writes_and_lands_on_the_menus_page(self) -> None:
        self.assertFalse(self.lane.read_only)
        self.assertEqual(self.lane.page, "menus")
        self.assertEqual(self.lane.surface, "menus")
        self.assertEqual(self.lane.classification, "offline-writer-proved")
        self.assertTrue(self.lane.fixed_allocation)

    def test_the_catalogue_finds_the_member_and_one_target_per_string(self) -> None:
        self.assertEqual(self.catalogue.document["text_members"], 1)
        self.assertEqual(self.catalogue.document["strings"], 3)
        self.assertEqual(self.catalogue.document["slots"], 3)
        self.assertEqual(len(self.catalogue.targets), 3)
        self.assertEqual(self.slot.raw["container"], containers.TEAM_DATABASE_CONTAINER)

    def test_the_catalogue_document_carries_no_string_from_the_source(self) -> None:
        blob = json.dumps(self.catalogue.document, default=dict)
        for text in SYNTHETIC_STRINGS:
            self.assertNotIn(text, blob, "a catalogue document must never carry payload")

    def test_a_target_carries_the_string_it_offers_to_replace(self) -> None:
        self.assertEqual(self.slot.raw["text"], SYNTHETIC_STRINGS[0])
        self.assertEqual(self.slot.raw["allocation_bytes"], len(SYNTHETIC_STRINGS[0]))

    def test_a_preview_reads_the_strings_from_the_source_it_is_given(self) -> None:
        self.assertEqual(self.lane.preview(self.source, self.slot), SYNTHETIC_STRINGS)

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

    # -- check_edit ----------------------------------------------------

    def test_a_replacement_that_fits_is_accepted(self) -> None:
        self.assertIsNone(self.lane.check_edit(self.slot, {"new_text": "SHORTER"}))

    def test_a_replacement_over_the_allocation_is_refused_with_the_length(self) -> None:
        problem = self.lane.check_edit(
            self.slot, {"new_text": "X" * (self.slot.raw["allocation_bytes"] + 1)})
        self.assertIn(f"shorten it to {self.slot.raw['allocation_bytes']}", problem)

    def test_the_text_already_there_is_refused(self) -> None:
        self.assertIn("already there",
                      self.lane.check_edit(self.slot, {"new_text": self.slot.raw["text"]}))

    def test_an_empty_replacement_is_refused(self) -> None:
        self.assertIn("empty string", self.lane.check_edit(self.slot, {"new_text": ""}))

    def test_a_field_this_lane_does_not_write_is_refused_by_name(self) -> None:
        self.assertIn("colour", self.lane.check_edit(self.slot, {"colour": 1}) or "colour")

    def test_a_container_the_preload_cache_names_is_read_only(self) -> None:
        reason = self.lane.read_only_reason("GAMEDATA.DAT")
        self.assertIn("preload cache", reason)
        self.assertIn("GAME.QKL", reason)
        self.assertEqual(self.lane.read_only_reason("STRYTEXT.DAT"), "")

    def test_the_image_s_own_cache_list_beats_the_written_down_one(self) -> None:
        reason = self.lane.read_only_reason("STRYTEXT.DAT", {"STRYTEXT.DAT": ("FE.QKL",)})
        self.assertIn("FE.QKL", reason)

    # -- plan / build / verify -----------------------------------------

    def _built(self):
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        destination = self.work / "built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        return edits, destination, receipt

    def test_a_plan_declares_ranges_and_writes_nothing(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        before = self.source.read_bytes()
        plan = self.lane.plan(self.source, recipe, self.catalogue)
        self.assertTrue(plan.declared_ranges)
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_build_keeps_the_image_size_and_verifies(self) -> None:
        _edits, destination, receipt = self._built()
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

    def test_the_replacement_reads_back_and_its_neighbours_do_not_move(self) -> None:
        edits, destination, _receipt = self._built()
        catalogue = self.lane.build_catalogue(destination)
        self.assertEqual(catalogue.targets[0].raw["text"], edits[0].values["new_text"])
        self.assertEqual(catalogue.targets[1].raw["text"], SYNTHETIC_STRINGS[1])
        self.assertEqual(catalogue.targets[2].raw["text"], SYNTHETIC_STRINGS[2])

    def test_the_allocation_survives_the_edit_so_it_can_be_written_back(self) -> None:
        _edits, destination, _receipt = self._built()
        catalogue = self.lane.build_catalogue(destination)
        self.assertEqual(catalogue.targets[0].raw["allocation_bytes"],
                         self.slot.raw["allocation_bytes"])

    def test_a_build_leaves_the_source_alone(self) -> None:
        before = self.source.read_bytes()
        self._built()
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_build_refuses_an_existing_destination(self) -> None:
        _edits, destination, _receipt = self._built()
        with self.assertRaises(Refusal) as caught:
            self._built()
        self.assertIn("already exists", str(caught.exception))

    def test_a_build_refuses_the_source_as_its_destination(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.source, recipe, self.catalogue)
        self.assertIn("another name", str(caught.exception))

    def test_a_stale_expectation_refuses_rather_than_writing_over_someone(self) -> None:
        recipe = self.lane.compose_recipe((Edit(self.slot.key, {
            "new_text": "SOMETHING ELSE", "expect_sha256": "0" * 64}),))
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, self.catalogue)
        self.assertIn("rebuild the catalogue", str(caught.exception))

    def test_a_slot_at_a_byte_no_string_starts_at_is_refused(self) -> None:
        recipe = self.lane.compose_recipe(
            (Edit(text_lane.slot_key(containers.TEAM_DATABASE_CONTAINER, 1, 7),
                  {"new_text": "NO"}),))
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, self.catalogue)
        self.assertIn("no string starting at byte 7", str(caught.exception))

    def test_a_recipe_of_another_schema_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, {"schema": "other/v1", "edits": [{}]}, self.catalogue)
        self.assertIn(text_lane.RECIPE_SCHEMA, str(caught.exception))

    # -- the verifier has to be able to fail ---------------------------

    def test_the_verifier_catches_a_byte_flipped_outside_the_declared_ranges(self) -> None:
        _edits, destination, receipt = self._built()
        ranges = [(item.start, item.length) for item in receipt.declared_ranges]
        offset = destination.stat().st_size - 1
        while any(start <= offset < start + length for start, length in ranges):
            offset -= 1
        raw = bytearray(destination.read_bytes())
        raw[offset] ^= 0xFF
        tampered = self.work / "tampered.iso"
        tampered.write_bytes(bytes(raw))
        self.assertFalse(self.lane.verify(self.source, tampered, receipt).passed)

    def test_the_verifier_catches_a_neighbouring_string_changed(self) -> None:
        """Inside the declared ISO extent, outside the edited slot."""

        from mod_editor.games._formats import ea_terf

        _edits, destination, receipt = self._built()
        image = containers.open_disc(destination)
        entry = next(item for item in containers.data_files(image)
                     if item.name == containers.TEAM_DATABASE_CONTAINER)
        original = containers.read_file(image, entry)
        member = bytearray(ea_terf.parse_terf(original, allow_size_mismatch=True).member(1))
        second = text_lane.slots_in(bytes(member))[1]
        member[second[0]:second[0] + 4] = b"ZZZZ"
        rebuilt = ea_terf.rewrite_member(original, 1, bytes(member))
        raw = bytearray(destination.read_bytes())
        start = entry.lba * 2048
        raw[start:start + len(rebuilt)] = rebuilt
        tampered = self.work / "sneaky.iso"
        tampered.write_bytes(bytes(raw))
        verdict = self.lane.verify(self.source, tampered, receipt)
        self.assertFalse(verdict.passed, verdict.summary)

    def test_a_receipt_with_no_recipe_is_refused_rather_than_believed(self) -> None:
        _edits, destination, receipt = self._built()
        stripped = {key: value for key, value in receipt.document.items() if key != "recipe"}
        with self.assertRaises(Refusal):
            text_lane.verify_build(self.source, destination, stripped)


if __name__ == "__main__":
    unittest.main()
