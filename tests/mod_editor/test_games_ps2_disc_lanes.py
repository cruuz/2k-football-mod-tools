"""The six PS2 disc lanes on the game-module contract, proved with no game data.

Every case here runs against a lane's own ``synthetic_source`` -- the retail-free
image its catalogue tool, patcher and verifier are all built to accept -- so the
whole file runs on a machine that has never seen the disc.

The conformance harness already drives the happy path of each lane end to end
(catalogue → plan → build → verify → tamper) from
``tests/mod_editor/test_games_conformance.py``.  What is pinned here is the part
a generic harness cannot know: the *shape* each lane offers an editor, the exact
sentence each refusal says, the two "leave it alone" readings the roster lane
needs because a spinner and a combo always have a value, and the promise that a
receipt never carries the coordinates the user's disc held.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from mod_editor.games import contract  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.nfl2k5_ps2 import GAME, disc_lanes  # noqa: E402


def _lane(lane_id: str):
    for lane in disc_lanes.DISC_LANES:
        if lane.lane_id == lane_id:
            return lane
    raise AssertionError(f"no disc lane is called {lane_id!r}")


class _OnASyntheticDisc(unittest.TestCase):
    """One lane, its synthetic source and its catalogue, built once per class."""

    lane_id = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-lane-")
        cls.room = Path(cls._temp.name).resolve()
        cls.lane = _lane(cls.lane_id)
        cls.source = Path(cls.lane.synthetic_source(cls.room))
        cls.catalogue = cls.lane.build_catalogue(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def target_where(self, **match):
        for target in self.catalogue.targets:
            if all(target.raw.get(key) == value for key, value in match.items()):
                return target
        raise AssertionError(f"no {self.lane_id} target matches {match}")


# --------------------------------------------------------------------------
# What every lane owes the contract and the registry
# --------------------------------------------------------------------------

class EveryDiscLaneTests(unittest.TestCase):
    def test_each_lane_answers_the_contract(self) -> None:
        for lane in disc_lanes.DISC_LANES:
            with self.subTest(lane=lane.lane_id):
                self.assertIsInstance(lane, contract.Lane)

    def test_each_lane_is_one_registry_row_that_agrees_with_it(self) -> None:
        rows = {row["id"]: row for row in GAME.manifest.registry_document()["capabilities"]}
        for lane in disc_lanes.DISC_LANES:
            with self.subTest(lane=lane.lane_id):
                row = rows.get(lane.capability_id)
                self.assertIsNotNone(row, f"{lane.capability_id} is not in the fragment")
                self.assertEqual(row["surface"], lane.surface)
                self.assertEqual(row["classification"], lane.classification)
                self.assertEqual(row["game"], "nfl2k5_ps2")

    def test_each_lane_names_the_validators_its_registry_row_names(self) -> None:
        rows = {row["id"]: row for row in GAME.manifest.registry_document()["capabilities"]}
        for lane in disc_lanes.DISC_LANES:
            with self.subTest(lane=lane.lane_id):
                named = [token for token in str(rows[lane.capability_id]["validation_command"]).split()
                         if token.startswith("tools/")]
                self.assertTrue(named, "the row must name a validator")
                for token in named:
                    self.assertIn(token, lane.validators)
                for relative in lane.validators:
                    self.assertTrue((ROOT / relative).is_file(), relative)

    def test_every_lane_lands_on_a_studio_page(self) -> None:
        pages = {page_id for page_id, _title in contract.PAGE_ORDER}
        for lane in disc_lanes.DISC_LANES:
            with self.subTest(lane=lane.lane_id):
                self.assertIn(contract.lane_page(lane), pages)

    def test_the_module_lists_them_all_and_no_capability_twice(self) -> None:
        ids = [lane.capability_id for lane in GAME.lanes]
        self.assertEqual(len(ids), len(set(ids)))
        for lane in disc_lanes.DISC_LANES:
            self.assertIn(lane.capability_id, ids)

    def test_the_colour_lane_now_offers_its_two_words_as_fields(self) -> None:
        colour = [lane for lane in GAME.lanes if lane.lane_id == "colors.unif_words"][0]
        with tempfile.TemporaryDirectory(prefix="ps2-colour-") as work:
            source = colour.synthetic_source(Path(work).resolve())
            catalogue = colour.build_catalogue(source)
        target = catalogue.targets[0]
        self.assertEqual([item.key for item in target.fields], ["facemask", "turtleneck"])
        for item in target.fields:
            self.assertEqual(item.kind, "colour_argb")
            self.assertFalse(item.read_only)


# --------------------------------------------------------------------------
# Text banks
# --------------------------------------------------------------------------

class TextLaneTests(_OnASyntheticDisc):
    lane_id = "menus.text_banks"

    def test_a_target_quotes_the_budget_and_offers_one_text_field(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("characters", target.budget)
        self.assertEqual([item.key for item in target.fields], ["new_text"])
        self.assertEqual(target.fields[0].kind, "text")

    def test_a_replacement_past_the_budget_is_refused_with_the_number(self) -> None:
        target = self.catalogue.targets[0]
        limit = self.lane.limit_of(target.raw)
        refusal = self.lane.check_edit(target, {"new_text": "X" * (limit + 3)})
        self.assertIn(f"budget of {limit}", refusal)
        self.assertIn("the original string's own length", refusal)

    def test_dropping_an_inline_token_is_refused_by_name(self) -> None:
        target = [row for row in self.catalogue.targets if row.raw.get("tokens")][0]
        refusal = self.lane.check_edit(target, {"new_text": "Go"})
        self.assertIn("Keep the inline tokens", refusal)
        for token in target.raw["tokens"]:
            self.assertIn(token, refusal)

    def test_the_text_already_there_is_refused_rather_than_written(self) -> None:
        target = self.catalogue.targets[0]
        already = self.lane.SYNTHETIC_TEXTS[int(target.raw["pool_index"])]
        refusal = self.lane.check_edit(target, {"new_text": already})
        self.assertIn("already there", refusal)

    def test_a_nul_and_an_empty_string_are_refused(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("empty string", self.lane.check_edit(target, {"new_text": ""}))
        self.assertIn("NUL", self.lane.check_edit(target, {"new_text": "A\x00B"}))

    def test_the_recipe_is_what_the_patcher_takes_and_pins_the_original(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        self.assertEqual(recipe["schema"], "nfl2k5_ps2_text_patch/v1")
        row = recipe["edits"][0]
        self.assertEqual(set(row), {"selector", "new_text", "expect_sha256"})
        self.assertEqual(row["expect_sha256"], self.catalogue.target(row["selector"]).raw["text_sha256"])

    def test_a_plan_declares_the_allocation_and_writes_nothing(self) -> None:
        before = self.source.read_bytes()
        edits = self.lane.conformance_edits(self.catalogue)
        plan = self.lane.plan(self.source, self.lane.compose_recipe(edits), self.catalogue)
        self.assertTrue(plan.declared_ranges)
        self.assertEqual(plan.declared_bytes,
                         self.catalogue.target(edits[0].target_key).raw["allocation_bytes"])
        self.assertEqual(self.source.read_bytes(), before)

    def test_the_receipt_carries_the_recipe_the_verifier_needs(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        destination = self.room / "text-built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue, work_dir=self.room)
        self.assertEqual(receipt.document["recipe"], dict(recipe))
        self.assertTrue(self.lane.verify(self.source, destination, receipt).passed)


# --------------------------------------------------------------------------
# Disc roster
# --------------------------------------------------------------------------

class RosterLaneTests(_OnASyntheticDisc):
    lane_id = "players.disc_roster"

    def writable(self):
        return [row for row in self.catalogue.targets if row.raw.get("first_name_writable")][0]

    def test_a_target_offers_names_a_jersey_and_a_shield(self) -> None:
        target = self.writable()
        self.assertEqual([item.key for item in target.fields],
                         ["first_name", "last_name", "jersey_number", "face_shield"])
        by_key = {item.key: item for item in target.fields}
        self.assertEqual(by_key["jersey_number"].kind, "int")
        self.assertEqual(by_key["jersey_number"].minimum, disc_lanes.KEEP_JERSEY)
        self.assertEqual(by_key["face_shield"].choices,
                         (disc_lanes.KEEP_CHOICE,) + disc_lanes.FACE_SHIELDS)

    def test_a_placeholder_name_slot_says_it_has_no_room(self) -> None:
        empty = [row for row in self.catalogue.targets
                 if int(row.raw.get("first_name_capacity", 0)) <= 2]
        self.assertTrue(empty, "the synthetic roster must carry a placeholder slot")
        refusal = self.lane.check_edit(empty[0], {"first_name": "Ann"})
        self.assertIn("empty placeholder", refusal)
        self.assertTrue(empty[0].fields[0].read_only)

    def test_a_name_past_its_own_bytes_is_refused_with_the_budget(self) -> None:
        target = self.writable()
        limit = self.lane.name_limit(target.raw, "first_name")
        refusal = self.lane.check_edit(target, {"first_name": "Q" * (limit + 2)})
        self.assertIn(f"budget of {limit}", refusal)
        self.assertIn("fit the bytes the original occupies", refusal)

    def test_the_untouched_spinner_and_picker_are_not_writes(self) -> None:
        # A shell's spinner and combo always have *some* value; these two
        # readings mean "leave it", so an edit that only renames a player does
        # not silently set jersey 0 and shield None as well.
        target = self.writable()
        values = {"first_name": "Ann",
                  "jersey_number": disc_lanes.KEEP_JERSEY,
                  "face_shield": disc_lanes.KEEP_CHOICE}
        self.assertIsNone(self.lane.check_edit(target, values))
        row = self.lane.compose_recipe((Edit(target.key, values),))["edits"][0]
        self.assertEqual(set(row), {"pool", "player", "first_name"})

    def test_a_shield_is_written_as_the_number_the_writer_takes(self) -> None:
        target = self.writable()
        row = self.lane.compose_recipe((Edit(target.key, {"face_shield": "Dark"}),))["edits"][0]
        self.assertEqual(row["face_shield"], 2)
        self.assertEqual(self.lane.shield_value(1), 1)
        self.assertIsNone(self.lane.shield_value(disc_lanes.KEEP_CHOICE))
        self.assertIsNone(self.lane.shield_value(3))

    def test_an_edit_that_changes_nothing_is_refused(self) -> None:
        target = self.writable()
        self.assertIn("Change at least one", self.lane.check_edit(target, {}))

    def test_the_recipe_names_the_boot_roster_the_patcher_expects(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        self.assertEqual(recipe["roster"], "boot")
        self.assertEqual(recipe["schema"], "nfl2k5_ps2_disc_roster_recipe/v1")


# --------------------------------------------------------------------------
# Playbooks
# --------------------------------------------------------------------------

class PlaybookLaneTests(_OnASyntheticDisc):
    lane_id = "scripts.director_playbook"

    def test_a_book_shows_its_headroom_and_offers_a_donor_and_a_name(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("/50 formations", target.detail)
        self.assertIn("Room for", target.budget)
        self.assertEqual(sorted(item.key for item in target.fields),
                         ["create", "custom_name", "donor_formation_index", "donor_play_index"])

    def test_a_name_the_writer_would_refuse_is_refused_inline(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("printable ASCII",
                      self.lane.check_edit(target, {"create": "play", "custom_name": "café"}))
        self.assertIn("1 through 40",
                      self.lane.check_edit(target, {"create": "play", "custom_name": "X" * 41}))

    def test_a_book_at_the_play_cap_refuses_another_play(self) -> None:
        target = self.catalogue.targets[0]
        full = contract.Target(target.key, target.label, target.detail, target.budget,
                               target.searchable,
                               raw=dict(target.raw, plays=270, play_headroom=0,
                                        at_play_capacity=True),
                               fields=target.fields)
        refusal = self.lane.check_edit(full, {"create": "play"})
        self.assertIn("270 of 270", refusal)
        self.assertIn("Choose a book with room", refusal)

    def test_a_donor_outside_the_book_is_refused_with_the_range(self) -> None:
        target = self.catalogue.targets[0]
        refusal = self.lane.check_edit(target, {"create": "play", "donor_play_index": 99})
        self.assertIn("donor play must be one of this book's", refusal)

    def test_creating_both_asks_the_writer_for_both(self) -> None:
        target = self.catalogue.targets[0]
        recipe = self.lane.compose_recipe(
            (Edit(target.key, {"create": "both", "custom_name": "SMASH"}),))
        row = recipe["edits"][0]
        self.assertEqual(row["book_id"], target.key)
        self.assertEqual(row["formations"][0]["custom_name"], "SMASH")
        self.assertEqual(row["plays"][0]["custom_name"], "SMASH")

    def test_the_plan_declares_only_the_bytes_the_compile_changed(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        plan = self.lane.plan(self.source, self.lane.compose_recipe(edits), self.catalogue)
        self.assertTrue(plan.declared_ranges)
        self.assertEqual(plan.declared_bytes, plan.document["changed_byte_count"])


# --------------------------------------------------------------------------
# Stadium position lanes
# --------------------------------------------------------------------------

class StadiumLaneTests(_OnASyntheticDisc):
    lane_id = "stadiums.position_lanes"

    def test_a_lane_offers_three_offsets_and_names_its_vertex_count(self) -> None:
        target = self.catalogue.targets[0]
        self.assertEqual([item.key for item in target.fields], ["dx", "dy", "dz"])
        self.assertEqual({item.kind for item in target.fields}, {"float"})
        self.assertIn("vertices", target.budget)

    def test_moving_nothing_and_moving_by_infinity_are_both_refused(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn("other than zero",
                      self.lane.check_edit(target, {"dx": 0, "dy": 0, "dz": 0}))
        self.assertIn("finite", self.lane.check_edit(target, {"dy": float("inf")}))
        self.assertIn("must be a number", self.lane.check_edit(target, {"dy": "up"}))
        self.assertIsNone(self.lane.check_edit(target, {"dy": 400.0}))

    def test_the_composed_recipe_carries_offsets_not_coordinates(self) -> None:
        target = self.catalogue.targets[0]
        recipe = self.lane.compose_recipe((Edit(target.key, {"dy": 400.0}),))
        self.assertEqual(recipe["schema"], "nfl2k5_ps2_stadium_offset_recipe/v1")
        self.assertEqual(recipe["edits"][0], {"target_id": target.key, "dx": 0.0, "dy": 400.0, "dz": 0.0})
        self.assertNotIn("positions", json.dumps(recipe))

    def test_a_build_moves_every_vertex_and_its_receipt_holds_no_coordinates(self) -> None:
        target = self.catalogue.targets[0]
        recipe = self.lane.compose_recipe((Edit(target.key, {"dy": 400.0}),))
        destination = self.room / "stadium-built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue, work_dir=self.room)
        # The patcher's report names each lane and counts its vertices; the
        # coordinates the disc held, and the ones we wrote, appear nowhere.
        for row in receipt.document["edits"]:
            self.assertNotIn("positions", row)
            self.assertEqual(row["vertex_count"], target.raw["position"]["vertex_count"])
        self.assertEqual(receipt.document["offset_recipe"], dict(recipe))
        self.assertNotIn("400.0", json.dumps(receipt.document["edits"]))
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("every one inside a declared lane", verdict.summary)

    def test_a_lane_this_disc_does_not_have_is_refused_by_name(self) -> None:
        recipe = self.lane.compose_recipe((Edit("nfl2k5ps2/stadium/e9/c9/s9/b9/l9", {"dy": 1.0}),))
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, recipe, self.catalogue)
        self.assertIn("is not a lane this disc's catalogue names", str(caught.exception))

    def test_a_recipe_row_this_lane_does_not_read_is_refused(self) -> None:
        for row, expected in (({"dy": 1.0}, "must name the position lane"),
                              ({"target_id": self.catalogue.targets[0].key, "scale": 2},
                               "a key this lane does not read")):
            with self.subTest(row=row):
                with self.assertRaises(Refusal) as caught:
                    self.lane.plan(self.source,
                                   {"schema": self.lane.recipe_schema, "edits": [row]},
                                   self.catalogue)
                self.assertIn(expected, str(caught.exception))


# --------------------------------------------------------------------------
# AUDO sounds
# --------------------------------------------------------------------------

def _wav(frames: int, rate: int, channels: int = 1) -> bytes:
    planes = [[int(round(9000 * math.sin(2 * math.pi * 440 * n / rate))) for n in range(frames)]
              for _channel in range(channels)]
    return disc_lanes._wav_bytes(planes, frames, rate)


class AudioLaneTests(_OnASyntheticDisc):
    lane_id = "audio.audo_exact_slot_replace"

    def test_the_lane_answers_the_audio_protocol(self) -> None:
        self.assertIsInstance(self.lane, contract.AudioLane)

    def test_a_slot_shows_its_capacity_in_seconds_and_takes_a_wav(self) -> None:
        target = self.catalogue.targets[0]
        self.assertIn(" s", target.budget)
        self.assertEqual([item.key for item in target.fields], ["wav"])
        self.assertEqual(target.fields[0].kind, "wav")

    def test_a_sound_past_the_slot_is_refused_with_the_slot_capacity(self) -> None:
        target = self.catalogue.targets[0]
        rate = int(target.raw["sample_rate"])
        path = self.room / "too-long.wav"
        path.write_bytes(_wav(int(target.raw["max_frames"]) + rate, rate))
        refusal = self.lane.check_edit(target, {"wav": str(path)})
        self.assertIn("never grows a slot", refusal)
        self.assertIn(f"{self.lane.capacity_seconds(target.raw):.2f} s", refusal)

    def test_the_wrong_channel_count_is_refused_by_name(self) -> None:
        target = self.catalogue.targets[0]
        path = self.room / "stereo.wav"
        path.write_bytes(_wav(64, int(target.raw["sample_rate"]), channels=2))
        refusal = self.lane.check_edit(target, {"wav": str(path)})
        self.assertIn("supply mono audio", refusal)

    def test_a_missing_file_is_refused_rather_than_raised(self) -> None:
        target = self.catalogue.targets[0]
        refusal = self.lane.check_edit(target, {"wav": str(self.room / "nowhere.wav")})
        self.assertIn("not a regular file", refusal)

    def test_decode_wav_reads_the_slot_off_the_disc(self) -> None:
        target = self.catalogue.targets[0]
        payload = self.lane.decode_wav(self.source, target)
        with wave.open(io.BytesIO(payload)) as handle:
            self.assertEqual(handle.getnchannels(), int(target.raw["channels"]))
            self.assertEqual(handle.getframerate(), int(target.raw["sample_rate"]))
            self.assertEqual(handle.getsampwidth(), 2)
            self.assertEqual(handle.getnframes(), int(target.raw["max_frames"]))

    def test_a_built_slot_decodes_back_as_the_sound_that_was_put_in_it(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        destination = self.room / "audio-built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue, work_dir=self.room)
        self.assertTrue(self.lane.verify(self.source, destination, receipt).passed)
        target = self.catalogue.target(edits[0].target_key)
        with wave.open(io.BytesIO(self.lane.decode_wav(destination, target))) as handle:
            samples = struct.unpack("<%dh" % handle.getnframes(),
                                    handle.readframes(handle.getnframes()))
        # Silence went in with the fixture; the conformance edit is a 440 Hz
        # tone, and SPU-ADPCM is lossy but nowhere near this lossy.
        self.assertGreater(max(abs(value) for value in samples), 8000)


# --------------------------------------------------------------------------
# The read-only disc inventory
# --------------------------------------------------------------------------

class DiscInventoryLaneTests(_OnASyntheticDisc):
    lane_id = "textures.disc_inventory"

    def test_the_lane_answers_the_read_only_protocol(self) -> None:
        self.assertIsInstance(self.lane, contract.ReadOnlyLane)
        self.assertIs(self.lane.read_only, True)
        self.assertIs(self.lane.fixed_allocation, False)

    def test_every_field_on_every_target_is_read_only(self) -> None:
        self.assertTrue(self.catalogue.targets)
        for target in self.catalogue.targets:
            with self.subTest(target=target.key):
                self.assertTrue(target.fields)
                self.assertTrue(all(item.read_only for item in target.fields))

    def test_planning_building_and_verifying_all_refuse_with_one_sentence(self) -> None:
        recipe = self.lane.compose_recipe(())
        destination = self.room / "never-written.iso"
        for name, call in (
            ("plan", lambda: self.lane.plan(self.source, recipe, self.catalogue)),
            ("build", lambda: self.lane.build(self.source, destination, recipe, self.catalogue)),
            ("verify", lambda: self.lane.verify(self.source, destination, None)),
        ):
            with self.subTest(step=name):
                with self.assertRaises(Refusal) as caught:
                    call()
                message = str(caught.exception)
                self.assertNotIn("\n", message)
                self.assertIn("writes nothing", message)
        self.assertFalse(destination.exists())

    def test_an_edit_is_refused_before_it_is_staged(self) -> None:
        refusal = self.lane.check_edit(self.catalogue.targets[0], {"name": "anything"})
        self.assertIn("writes nothing", refusal)


# --------------------------------------------------------------------------
# House rules that hold across the file
# --------------------------------------------------------------------------

class RefusalWordingTests(unittest.TestCase):
    def test_no_refusal_is_a_traceback(self) -> None:
        # Every refusal a lane makes reaches a user verbatim, so it must be a
        # sentence: one line, no exception class name, no repr of a Path.
        with tempfile.TemporaryDirectory(prefix="ps2-refusal-") as work:
            room = Path(work).resolve()
            for lane in disc_lanes.DISC_LANES:
                source = Path(lane.synthetic_source(room))
                catalogue = lane.build_catalogue(source)
                with self.subTest(lane=lane.lane_id):
                    with self.assertRaises(Refusal) as caught:
                        lane.plan(source, {"schema": lane.recipe_schema, "edits": [{"nonsense": 1}]},
                                  catalogue)
                    message = str(caught.exception)
                    self.assertTrue(message.strip())
                    self.assertNotIn("\n", message)
                    self.assertNotIn("Traceback", message)

    def test_a_build_never_overwrites_and_never_writes_the_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ps2-destination-") as work:
            room = Path(work).resolve()
            for lane in disc_lanes.DISC_LANES:
                if getattr(lane, "read_only", False):
                    continue
                source = Path(lane.synthetic_source(room))
                catalogue = lane.build_catalogue(source)
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                taken = room / f"{lane.lane_id}-taken.iso"
                taken.write_bytes(b"not an image")
                with self.subTest(lane=lane.lane_id):
                    with self.assertRaises(Refusal) as caught:
                        lane.build(source, taken, recipe, catalogue, work_dir=room)
                    self.assertIn("already exists", str(caught.exception))
                    self.assertEqual(taken.read_bytes(), b"not an image")
                    with self.assertRaises(Refusal) as caught:
                        lane.build(source, source, recipe, catalogue, work_dir=room)
                    self.assertIn("never the source", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
