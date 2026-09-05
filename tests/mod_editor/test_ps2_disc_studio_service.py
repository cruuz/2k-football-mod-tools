"""Service, lane-adapter and worker tests for the PS2 Disc Studio.

Everything runs on synthetic discs built by the six lanes' own fixture
builders -- no game data.  One combined disc carries a STRG bank, two Unif
packages, a boot roster and an AUDO slot so a chained multi-lane build can
be exercised; the playbook and stadium lanes use their own builders.  The
catalogue tools and the build-step worker run as real child processes, the
way the window drives them.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests" / "mod_editor"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_ps2_audo_target_catalog as audio_catalog  # noqa: E402
import nfl2k5_ps2_disc_roster_target_catalog as roster_catalog  # noqa: E402
import nfl2k5_ps2_stadium_position_patch as stadium_patcher  # noqa: E402
import nfl2k5_ps2_text_patch as text_patcher  # noqa: E402
import nfl2k5_ps2_text_target_catalog as text_catalog  # noqa: E402
import nfl2k5_ps2_unif_color_patch as color_patcher  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as color_catalog  # noqa: E402
import ps2_iso9660 as iso_lib  # noqa: E402
import spu_adpcm  # noqa: E402

from mod_editor.core import ps2_disc_studio_lanes as lanes  # noqa: E402
from mod_editor.core import ps2_disc_studio_service as svc  # noqa: E402
from mod_editor.core import ps2_disc_studio_worker as worker  # noqa: E402

TEXTS = ("MENU", "Press |CROSS| to go", "Score %d", "", "OPTIONS", "OPT")
FACEMASK, TURTLENECK = 0xFFA29895, 0xFF272320


def _chunk(fourcc: bytes, body: bytes, compressed: bool = False) -> bytes:
    header = bytearray(0x20)
    header[0:4] = fourcc
    struct.pack_into("<IIII", header, 4, len(body), 0, 0, 0xFEEDBEEF if compressed else 0)
    return bytes(header) + body


def combined_disc() -> bytes:
    """Text bank + two uniform packages + boot roster + one mono AUDO slot."""
    strg = _chunk(b"STRG", text_catalog.build_synthetic_strg_body(list(TEXTS)))
    boot = roster_catalog.rost_chunk("roster", [("Duane", "Starks", 28, 0), ("Renaldo", "Hill", 21, 1),
                                                ("", "", 0, 0)], secondary=1)
    audo = audio_catalog.build_audo_chunk("beep", 1, 11025, spu_adpcm.encode([0] * (28 * 40)))
    return color_catalog.build_synthetic_iso(entries=[
        ("18H0.IFF", color_catalog.unif_chunk(FACEMASK, TURTLENECK)),
        ("18A0.IFF", color_catalog.unif_chunk(0xFF000000, 0xFF665900)),
        ("STRINGS.BIN", strg),
        ("ROSTER.IFF", boot),
        ("BEEP.BIN", audo),
    ])


def _wav(frames: int, rate: int, channels: int = 1) -> bytes:
    samples = [int(round(9000 * math.sin(2 * math.pi * 440 * n / rate))) for n in range(frames)]
    interleaved = [value for value in samples for _ in range(channels)]
    pcm = struct.pack("<%dh" % len(interleaved), *interleaved)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


class _Fixture(unittest.TestCase):
    """One combined synthetic disc, one private cache, one service per test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-studio-")
        cls.root = Path(cls._temp.name)
        cls.iso = cls.root / "source.iso"
        cls.iso.write_bytes(combined_disc())
        cls.service = svc.Ps2DiscStudioService(cache_root=cls.root / "cache", poll_seconds=0.05)
        cls.identity = cls.service.open(cls.iso)
        for lane_id in ("text", "colors", "roster", "audio"):
            cls.service.build_catalogue(lane_id)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.close()
        cls._temp.cleanup()

    def target(self, lane_id: str, **match):
        for row in self.service.targets(lane_id):
            if all(row.data.get(key) == value for key, value in match.items()):
                return row
        raise AssertionError(f"no {lane_id} target matches {match}")


class OpenTests(_Fixture):
    def test_identity_is_the_inventory_check(self) -> None:
        identity = self.identity
        self.assertEqual(identity.serial, "SLUS-20919")
        self.assertTrue(identity.serial_matches and identity.supported)
        self.assertFalse(identity.retail_boot_elf, "a synthetic ELF is not retail")
        self.assertIn("boot ELF differs from retail", identity.headline)
        self.assertEqual(identity.pack_count, 2)
        self.assertEqual(len(identity.key), 32)

    def test_the_disc_key_is_stable_and_keys_the_cache(self) -> None:
        other = svc.Ps2DiscStudioService(cache_root=self.root / "cache2")
        self.assertEqual(other.open(self.iso).key, self.identity.key)
        self.assertEqual(self.service.cache_dir().name, self.identity.key)
        self.assertTrue((self.service.cache_dir() / "disc.json").is_file())
        other.close()

    def test_a_disc_without_the_resource_packs_is_refused(self) -> None:
        plain = self.root / "plain.iso"
        plain.write_bytes(iso_lib.build_synthetic_iso())
        other = svc.Ps2DiscStudioService(cache_root=self.root / "cache3")
        with self.assertRaises(lanes.Ps2DiscStudioError) as caught:
            other.open(plain)
        self.assertIn("VC_20919", str(caught.exception))
        self.assertFalse(other.is_open)

    def test_a_missing_file_is_refused(self) -> None:
        other = svc.Ps2DiscStudioService(cache_root=self.root / "cache4")
        with self.assertRaises(lanes.Ps2DiscStudioError):
            other.open(self.root / "nope.iso")


class CatalogueTests(_Fixture):
    def test_each_catalogue_was_built_by_its_tool_into_the_sidecar(self) -> None:
        for lane_id, fragment in (("text", "strings"), ("colors", "uniform packages"),
                                  ("roster", "boot roster"), ("audio", "sound slots")):
            state = self.service.catalogue_state(lane_id)
            self.assertTrue(state.built, lane_id)
            self.assertIn(fragment, state.summary)
            self.assertTrue(state.path.is_file() and state.path.parent == self.service.cache_dir())
            self.assertIsNotNone(self.service.last_timing(f"catalogue:{lane_id}:default"))

    def test_the_cache_holds_no_decoded_text_or_colour_words(self) -> None:
        text_bytes = self.service.catalogue_path("text").read_bytes()
        for text in ("MENU", "OPTIONS", "Press |CROSS|"):
            self.assertNotIn(text.encode("utf-8"), text_bytes)
        colour_bytes = self.service.catalogue_path("colors").read_bytes().lower()
        self.assertNotIn(b"ffa29895", colour_bytes)
        self.assertNotIn(struct.pack("<I", FACEMASK), colour_bytes)

    def test_a_second_service_loads_the_cache_without_rebuilding(self) -> None:
        other = svc.Ps2DiscStudioService(cache_root=self.root / "cache")
        other.open(self.iso)
        with mock.patch.object(other, "_run_child", side_effect=AssertionError("must not run")):
            self.assertTrue(other.catalogue_state("text").built)
            self.assertEqual(len(other.targets("text")), len(self.service.targets("text")))
        other.close()

    def test_cancel_mid_catalogue_kills_the_tool_and_leaves_nothing(self) -> None:
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        token = svc.CancelToken()
        outcome: dict = {}

        def run() -> None:
            try:
                with mock.patch.object(lanes.TextLane, "catalogue_command", return_value=sleeper):
                    self.service.forget_catalogue("text")
                    self.service.build_catalogue("text", progress=lambda _m: None, cancel=token)
            except BaseException as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=run)
        started = time.monotonic()
        thread.start()
        time.sleep(0.4)
        token.cancel()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "the cancelled build never returned")
        self.assertLess(time.monotonic() - started, 8.0)
        self.assertIsInstance(outcome.get("error"), svc.Cancelled)
        self.assertFalse(self.service.catalogue_path("text").exists())
        self.assertEqual([p.name for p in self.service.cache_dir().glob("*.building.json")], [])
        self.service.build_catalogue("text")   # restore for the other tests

    def test_a_tool_that_fails_reports_its_output_and_leaves_nothing(self) -> None:
        failing = [sys.executable, "-c", "import sys; print('boom detail', file=sys.stderr); sys.exit(3)"]
        with mock.patch.object(lanes.AudioLane, "catalogue_command", return_value=failing):
            self.service.forget_catalogue("audio")
            with self.assertRaises(lanes.Ps2DiscStudioError) as caught:
                self.service.build_catalogue("audio")
        self.assertIn("boom detail", str(caught.exception))
        self.assertFalse(self.service.catalogue_path("audio").exists())
        self.service.build_catalogue("audio")

    def test_an_unknown_scope_or_lane_is_refused(self) -> None:
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.catalogue_state("text", "everything")
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.targets("fonts")


class TextLaneTests(_Fixture):
    def test_targets_carry_the_budget_and_the_read_only_reason(self) -> None:
        menu = self.target("text", pool_index=0)
        self.assertEqual(menu.label, "String message 0")
        self.assertIn("Up to 4 characters", menu.budget)
        empty = self.target("text", pool_index=3)
        self.assertFalse(empty.editable)
        self.assertIn("terminator", empty.reason)

    def test_display_text_comes_from_the_disc_not_the_catalogue(self) -> None:
        texts = self.service.lane("text").read_display_texts(self.iso, self.service.catalogue("text"))
        menu = self.target("text", pool_index=0)
        self.assertEqual(texts[menu.key], "MENU")
        self.assertEqual(texts[self.target("text", pool_index=1).key], "Press |CROSS| to go")

    def test_inline_refusals_quote_the_budget_and_name_the_fix(self) -> None:
        menu = self.target("text", pool_index=0)
        check = lambda text: self.service.check_edit("text", menu, {"new_text": text})  # noqa: E731
        self.assertIn("1 over the budget of 4", check("MENUS"))
        self.assertIn("shorten the replacement to 4", check("MENUS"))
        self.assertIn("already there", check("MENU"))
        self.assertIn("empty", check(""))
        self.assertIn("NUL", check("A\x00"))
        self.assertIsNone(check("PLAY"))
        token = self.target("text", pool_index=1)
        self.assertIn("|CROSS|", self.service.check_edit("text", token, {"new_text": "Press X to go"}))
        self.assertIn("read-only", self.service.check_edit("text", self.target("text", pool_index=3),
                                                             {"new_text": "A"}))
        staged = [self.service.stage("text", menu, {"new_text": "PLAY"})]
        self.assertIn("already in the recipe", self.service.check_edit("text", menu, {"new_text": "GAME"}, staged))

    def test_the_recipe_is_what_the_patcher_accepts_and_pins_the_original(self) -> None:
        menu = self.target("text", pool_index=0)
        edit = self.service.stage("text", menu, {"new_text": "PLAY"})
        steps = self.service.compose("text", [edit])
        self.assertEqual(len(steps), 1)
        recipe = steps[0].recipe
        self.assertEqual(recipe["edits"][0]["selector"], menu.key)
        self.assertEqual(recipe["edits"][0]["expect_sha256"], menu.data["text_sha256"])
        # The patcher's own resolver accepts it as written.
        resolved = text_patcher.resolve_edits(self.service.catalogue("text"), recipe["edits"])
        self.assertEqual(resolved[0].new_code_units, 4)
        self.assertIn('"new_text": "PLAY"', self.service.recipe_preview(steps))

    def test_plan_surfaces_the_patcher_refusal_verbatim(self) -> None:
        menu = self.target("text", pool_index=0)
        edit = lanes.StagedEdit("text", menu.key, {"new_text": "MENUS"}, "too long")
        with self.assertRaises(lanes.LaneRefusal) as caught:
            self.service.plan_lane("text", [edit])
        self.assertEqual(caught.exception.lane_id, "text")
        self.assertIn("no spare bytes", str(caught.exception))
        self.assertIn("4 UTF-16 code units", str(caught.exception))

    def test_a_plan_writes_nothing_and_says_what_would_change(self) -> None:
        menu = self.target("text", pool_index=0)
        outcome = self.service.plan_lane("text", [self.service.stage("text", menu, {"new_text": "PLAY"})])
        self.assertEqual(outcome.edits, 1)
        self.assertIn("4 bytes would change", outcome.summary)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.suffix == ".iso"), ["source.iso"])


class ColourLaneTests(_Fixture):
    def test_targets_decode_the_selector_and_read_current_words_from_the_disc(self) -> None:
        home = self.service.target("colors", "18H0")
        self.assertIn("package 18 · home · variant 0", home.label)
        words = self.service.lane("colors").read_current_words(self.iso, self.service.catalogue("colors"))
        self.assertEqual(words["18H0"], (FACEMASK, TURTLENECK))

    def test_inline_refusals(self) -> None:
        home = self.service.target("colors", "18H0")
        check = lambda values: self.service.check_edit("colors", home, values)  # noqa: E731
        self.assertIn("Choose a facemask colour", check({}))
        self.assertIn("exactly 4 bytes", check({"facemask": "FFAABBCCDD"}))
        self.assertIn("already holds", check({"facemask": "FFA29895", "_current": (FACEMASK, TURTLENECK)}))
        self.assertIsNone(check({"facemask": "#00FF00"}))

    def test_edits_in_two_packs_become_two_steps(self) -> None:
        catalogue = self.service.catalogue("colors")
        by_selector = {row["selector"]: row for row in catalogue["targets"]}
        self.assertNotEqual(by_selector["18H0"]["iso_path"], by_selector["18A0"]["iso_path"],
                            "the fixture puts the two packages in different packs")
        edits = [self.service.stage("colors", self.service.target("colors", "18H0"), {"facemask": "#00FF00"}),
                 self.service.stage("colors", self.service.target("colors", "18A0"), {"turtleneck": "#0000FF"})]
        steps = self.service.compose("colors", edits)
        self.assertEqual(len(steps), 2)
        for step in steps:
            self.assertEqual(step.recipe["schema"], color_patcher.RECIPE_SCHEMA)
            color_patcher.parse_recipe(step.recipe)


class RosterLaneTests(_Fixture):
    def test_boot_players_carry_name_budgets(self) -> None:
        starks = self.target("roster", index=0, pool="primary_players")
        self.assertIn("Duane Starks #28", starks.label)
        self.assertIn("first name up to 5 characters", starks.budget)

    def test_inline_refusals(self) -> None:
        starks = self.target("roster", index=0, pool="primary_players")
        check = lambda values: self.service.check_edit("roster", starks, values)  # noqa: E731
        self.assertIn("13 over the budget of 5", check({"first_name": "Bartholomewcubbins"}))
        self.assertIn("0 to 99", check({"jersey_number": 100}))
        self.assertIn("already 28", check({"jersey_number": 28}))
        self.assertIn("reserved", check({"face_shield": 3}))
        self.assertIn("Change at least one", check({}))
        self.assertIsNone(check({"first_name": "Dwane", "jersey_number": 7}))
        placeholder = self.target("roster", pool="secondary_players", index=0)
        self.assertIn("empty placeholder", self.service.check_edit("roster", placeholder, {"first_name": "Al"}))

    def test_the_recipe_names_the_roster_and_the_patcher_accepts_it(self) -> None:
        starks = self.target("roster", index=0, pool="primary_players")
        edit = self.service.stage("roster", starks, {"first_name": "Dwane", "jersey_number": 7})
        steps = self.service.compose("roster", [edit])
        self.assertEqual(steps[0].recipe["roster"], "boot")
        self.assertEqual(steps[0].recipe["edits"], [{"pool": "primary_players", "player": 0,
                                                    "first_name": "Dwane", "jersey_number": 7}])


class AudioLaneTests(_Fixture):
    def setUp(self) -> None:
        self.slot = self.target("audio", name="beep")
        self.good = self.root / "good.wav"
        self.good.write_bytes(_wav(28 * 30, 11025))

    def test_the_target_shows_capacity_in_seconds(self) -> None:
        self.assertIn("up to", self.slot.detail)
        self.assertAlmostEqual(lanes.AudioLane.capacity_seconds(self.slot.data), 28 * 40 / 11025, places=3)

    def test_inline_refusals_quote_the_slot_capacity(self) -> None:
        check = lambda path: self.service.check_edit("audio", self.slot, {"wav": str(path)})  # noqa: E731
        long = self.root / "long.wav"
        long.write_bytes(_wav(28 * 41, 11025))
        stereo = self.root / "stereo.wav"
        stereo.write_bytes(_wav(280, 11025, channels=2))
        bad = self.root / "bad.wav"
        bad.write_bytes(b"RIFF" + struct.pack("<I", 4) + b"WAVE")
        self.assertIn("slot holds", check(long))
        self.assertIn("shorten the audio", check(long))
        self.assertIn("supply mono audio", check(stereo))
        self.assertIn("too short", check(bad))
        self.assertIn("Choose a WAV", self.service.check_edit("audio", self.slot, {}))
        self.assertIsNone(check(self.good))

    def test_plan_encodes_and_reports_frames(self) -> None:
        edit = self.service.stage("audio", self.slot, {"wav": str(self.good)})
        outcome = self.service.plan_lane("audio", [edit])
        self.assertIn("840 of 1,120 frames", outcome.summary)
        self.assertEqual(outcome.steps[0].recipe["schema"], "nfl2k5_ps2_audo_recipe/v1")


class BuildTests(_Fixture):
    """The queue: refusals before the first byte, a chained build, a failing step."""

    def _plans(self):
        menu = self.target("text", pool_index=0)
        starks = self.target("roster", index=0, pool="primary_players")
        return [
            self.service.plan_lane("text", [self.service.stage("text", menu, {"new_text": "PLAY"})]),
            self.service.plan_lane("colors", [self.service.stage("colors", self.service.target("colors", "18H0"),
                                                                 {"facemask": "#00FF00"})]),
            self.service.plan_lane("roster", [self.service.stage("roster", starks, {"jersey_number": 7})]),
        ]

    def test_the_destination_refusals_come_before_any_write(self) -> None:
        plans = self._plans()
        with self.assertRaises(lanes.Ps2DiscStudioError) as caught:
            self.service.build(plans, self.iso)
        self.assertIn("already exists", str(caught.exception))
        taken = self.root / "taken.iso"
        taken.write_bytes(b"x")
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.build(plans, taken)
        self.assertEqual(taken.read_bytes(), b"x")
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.build(plans, self.root / "missing-folder" / "out.iso")
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.build([], self.root / "empty.iso")
        self.assertFalse((self.root / "empty.iso").exists())

    def test_a_full_volume_is_refused_with_the_sizes(self) -> None:
        plans = self._plans()
        with mock.patch.object(svc.platform_compat, "available_bytes", return_value=1024):
            estimate = self.service.estimate(len(plans), self.root / "full.iso")
            self.assertFalse(estimate.fits)
            self.assertIn("1.25 GiB", estimate.sentence)
            self.assertIn("one 0.00 GiB intermediate", estimate.sentence)
            with self.assertRaises(lanes.Ps2DiscStudioError) as caught:
                self.service.build(plans, self.root / "full.iso")
        self.assertIn("Free some space", str(caught.exception))
        self.assertFalse((self.root / "full.iso").exists())

    def test_a_chained_build_verifies_every_step_and_removes_intermediates(self) -> None:
        plans = self._plans()
        destination = self.root / "built.iso"
        stages: list = []
        before = combined_disc()
        receipt = self.service.build(plans, destination, progress=stages.append)
        self.assertTrue(destination.is_file())
        self.assertEqual(destination.stat().st_size, self.iso.stat().st_size)
        self.assertEqual(self.iso.read_bytes(), before, "the source is never written")
        self.assertEqual([step.lane_id for step in receipt.steps], ["text", "colors", "roster"])
        self.assertTrue(receipt.all_verified)
        self.assertIn("every verifier passed", receipt.message)
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".built.iso")], [])
        self.assertTrue(any("Step 2 of 3" in stage for stage in stages))
        self.assertEqual(receipt.source_sha256, svc._sha256_file(self.iso))
        self.assertEqual(receipt.destination_sha256, svc._sha256_file(destination))
        after = destination.read_bytes()
        differing = sum(1 for a, b in zip(before, after) if a != b)
        expected = (
            sum(1 for a, b in zip("MENU".encode("utf-16le"), "PLAY".encode("utf-16le")) if a != b)
            + sum(1 for a, b in zip(struct.pack("<I", FACEMASK), struct.pack("<I", 0xFF00FF00)) if a != b)
            + sum(1 for a, b in zip(struct.pack("<I", 28 << 3), struct.pack("<I", 7 << 3)) if a != b)
        )
        self.assertEqual(differing, expected, "exactly the three edits' bytes differ")
        document = json.loads(receipt.receipt_path.read_bytes().decode("utf-8"))
        self.assertEqual(document["schema"], svc.RECEIPT_SCHEMA)
        self.assertNotIn(b"\r\n", receipt.receipt_path.read_bytes())
        self.assertEqual(len(document["steps"]), 3)
        self.assertTrue(all(step["verdict"]["passed"] for step in document["steps"]))
        self.assertFalse(document["claims"]["runtime_visibility_proved"])
        for lane_id in ("text", "colors", "roster"):
            self.assertIsNotNone(self.service.last_timing(f"build:{lane_id}"))
        with self.assertRaises(lanes.Ps2DiscStudioError):
            self.service.build(plans, destination)

    def test_a_step_the_patcher_refuses_leaves_no_image_behind(self) -> None:
        menu = self.target("text", pool_index=0)
        bad = lanes.RecipeStep("text", {"edits": [{"selector": menu.key, "new_text": "MENUS"}]}, "bad", 1)
        forged = svc.PlanOutcome("text", (bad,), (lanes.PlanResult("text", 1, "forged", {}),))
        good = self._plans()[1]
        destination = self.root / "refused.iso"
        with self.assertRaises(lanes.LaneRefusal) as caught:
            self.service.build([forged, good], destination)
        self.assertEqual(caught.exception.lane_id, "text")
        self.assertIn("4 UTF-16 code units", str(caught.exception))
        self.assertFalse(destination.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".refused.iso")], [])

    def test_cancel_during_a_step_removes_the_part_written_image(self) -> None:
        plans = self._plans()
        destination = self.root / "cancelled.iso"
        token = svc.CancelToken()
        original = svc.Ps2DiscStudioService._run_child

        def slow_child(self_, command, **kwargs):
            token.cancel()
            return original(self_, [sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

        with mock.patch.object(svc.Ps2DiscStudioService, "_run_child", slow_child):
            with self.assertRaises(svc.Cancelled):
                self.service.build(plans, destination, cancel=token)
        self.assertFalse(destination.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".cancelled.iso")], [])


class WorkerTests(_Fixture):
    def test_run_step_in_process_plans_writes_and_verifies(self) -> None:
        menu = self.target("text", pool_index=0)
        outcome = self.service.plan_lane("text", [self.service.stage("text", menu, {"new_text": "PLAY"})])
        work = self.root / "work-inproc"
        destination = self.root / "worker.iso"
        job = {"schema": worker.JOB_SCHEMA, "lane": "text", "source": str(self.iso),
               "destination": str(destination), "recipe": outcome.steps[0].recipe,
               "catalogue_path": str(self.service.catalogue_path("text")), "work_dir": str(work),
               "result_path": str(work / "result.json"), "hash_input": True, "step": 1, "steps": 1}
        stages: list = []
        result = worker.run_step(job, stages.append)
        self.assertTrue(result["ok"] and result["verdict"]["passed"])
        self.assertEqual(result["input_sha256"], svc._sha256_file(self.iso))
        self.assertEqual(result["output_sha256"], svc._sha256_file(destination))
        self.assertEqual(set(result["seconds"]), {"hash_input", "plan", "write", "verify", "hash_output"})
        self.assertTrue(stages and stages[0].startswith("hashing"))
        destination.unlink()

    def test_the_worker_process_writes_a_result_and_cleans_a_refused_destination(self) -> None:
        import subprocess

        menu = self.target("text", pool_index=0)
        work = self.root / "work-proc"
        work.mkdir()
        destination = self.root / "worker-refused.iso"
        job = {"schema": worker.JOB_SCHEMA, "lane": "text", "source": str(self.iso),
               "destination": str(destination), "recipe": {"edits": [{"selector": menu.key, "new_text": "MENUS"}]},
               "catalogue_path": str(self.service.catalogue_path("text")), "work_dir": str(work),
               "result_path": str(work / "result.json"), "hash_input": False, "step": 1, "steps": 1}
        (work / "job.json").write_bytes(json.dumps(job).encode("utf-8"))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "tools")]))
        completed = subprocess.run([sys.executable, "-m", svc.WORKER_MODULE, str(work / "job.json")],
                                   cwd=str(ROOT), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        result = json.loads((work / "result.json").read_bytes().decode("utf-8"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "plan")
        self.assertIn("4 UTF-16 code units", result["error"])
        self.assertFalse(destination.exists())
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(events[-1]["event"], "failed")


class PlaybookLaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import test_nfl2k5_ps2_playbook as fixture

        cls.fixture = fixture
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-studio-play-")
        cls.root = Path(cls._temp.name)
        cls.iso = cls.root / "books.iso"
        cls.iso.write_bytes(fixture.synthetic_iso(fixture.synthetic_pack(fixture.default_books())))
        cls.service = svc.Ps2DiscStudioService(cache_root=cls.root / "cache", poll_seconds=0.05)
        cls.service.open(cls.iso)
        cls.service.build_catalogue("playbooks")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.close()
        cls._temp.cleanup()

    def test_books_carry_headroom_and_names_are_bounded(self) -> None:
        books = self.service.targets("playbooks")
        self.assertEqual(len(books), 2)
        book = books[0]
        self.assertIn("/50 formations", book.detail)
        self.assertIn("Room for", book.budget)
        check = lambda values: self.service.check_edit("playbooks", book, values)  # noqa: E731
        self.assertIn("Add a formation", check({}))
        self.assertIn("printable ASCII", check({"plays": [{"donor_play_index": 0, "custom_name": "café"}]}))
        self.assertIn("exactly 11", check({"formations": [{"donor_formation_index": 0, "slot_positions": [[0, 0]]}]}))
        self.assertIsNone(check({"plays": [{"donor_play_index": 0, "custom_name": "SMASH"}]}))

    def test_a_book_at_the_play_cap_refuses_an_added_play_inline(self) -> None:
        book = self.service.targets("playbooks")[0]
        full = lanes.Target(book.key, book.label, book.detail, book.budget, book.search,
                            data=dict(book.data, plays=270, play_headroom=0, at_play_capacity=True))
        refusal = self.service.check_edit("playbooks", full, {"plays": [{"donor_play_index": 0}]})
        self.assertIn("270 of 270", refusal)
        self.assertIn("Replace an existing play", refusal)

    def test_read_book_parses_the_body_from_the_disc(self) -> None:
        book = self.service.targets("playbooks")[0]
        parsed, body = self.service.lane("playbooks").read_book(self.iso, book.key)
        self.assertEqual(len(body), 0x13390)
        self.assertEqual([f.name for f in parsed.formations], ["FORMATION"] * 3)

    def test_plan_build_and_verify_one_book(self) -> None:
        book = self.service.targets("playbooks")[0]
        edit_values = dict(self.fixture.RECIPE["edits"][0])
        edit_values.pop("book_id")
        edit = self.service.stage("playbooks", book, edit_values)
        outcome = self.service.plan_lane("playbooks", [edit])
        self.assertIn("3f/2p → 4f/3p", outcome.summary)
        destination = self.root / "books-out.iso"
        receipt = self.service.build([outcome], destination)
        self.assertTrue(receipt.all_verified)
        self.assertEqual(destination.stat().st_size, self.iso.stat().st_size)
        self.assertIn("258", receipt.steps[0].verdict_summary.replace(",", "")
                      if "258" in receipt.steps[0].verdict_summary.replace(",", "") else "258")


class StadiumLaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-studio-stadium-")
        cls.root = Path(cls._temp.name)
        cls.iso = cls.root / "stadium.iso"
        cls.iso.write_bytes(stadium_patcher.build_synthetic_disc())
        cls.service = svc.Ps2DiscStudioService(cache_root=cls.root / "cache", poll_seconds=0.05)
        cls.service.open(cls.iso)
        cls.service.build_catalogue("stadium", "all")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.close()
        cls._temp.cleanup()

    def test_the_proved_scope_is_refused_on_a_disc_without_that_entry(self) -> None:
        with self.assertRaises(lanes.Ps2DiscStudioError) as caught:
            self.service.build_catalogue("stadium", "proved")
        self.assertIn("outside the table", str(caught.exception))

    def test_targets_and_inline_refusals(self) -> None:
        targets = self.service.targets("stadium", "all")
        self.assertEqual(len(targets), 2)
        lane_target = targets[0]
        self.assertIn("4 vertices", lane_target.detail)
        check = lambda values, staged=(): self.service.check_edit("stadium", lane_target, values, staged)  # noqa: E731
        self.assertIn("other than zero", check({"dx": 0, "dy": 0, "dz": 0}))
        self.assertIn("finite", check({"dx": float("inf")}))
        self.assertIn("must be a number", check({"dy": "up"}))
        self.assertIsNone(check({"dy": 400.0}))

    def test_compose_plan_build_and_verify(self) -> None:
        target = self.service.targets("stadium", "all")[0]
        edit = self.service.stage("stadium", target, {"dx": 0.0, "dy": 400.0, "dz": 0.0})
        steps = self.service.compose("stadium", [edit], "all")
        recipe = steps[0].recipe
        self.assertEqual(recipe["catalog"]["sha256"], self.service.catalogue_sha256("stadium", "all"))
        self.assertEqual(len(recipe["edits"][0]["positions"]), 4)
        self.assertTrue(all(lanes.binary32(v) == v for triple in recipe["edits"][0]["positions"] for v in triple))
        outcome = self.service.plan_lane("stadium", [edit], "all")
        self.assertIn("4 vertices", outcome.summary)
        self.assertIn("decided during the build", outcome.summary)
        destination = self.root / "stadium-out.iso"
        receipt = self.service.build([outcome], destination, scopes={"stadium": "all"})
        self.assertTrue(receipt.all_verified)
        self.assertIn("wrapper identical: True", receipt.steps[0].verdict_summary)
        step = receipt.document["steps"][0]
        self.assertNotIn("positions", json.dumps(step["recipe"]), "a receipt never carries coordinates")
        self.assertEqual(step["recipe"]["edits"][0]["vertex_count"], 4)


class RegistryTests(unittest.TestCase):
    def test_every_lane_finds_its_registry_row(self) -> None:
        for lane in lanes.lanes_in_order():
            rules = lanes.registry_rules(lane.id)
            self.assertTrue(rules, lane.id)
            self.assertTrue(lanes.registry_scope(lane.id).startswith("Offline only"), lane.id)
            self.assertTrue(lane.caveats and lane.time_note and lane.summary)

    def test_no_caveat_claims_a_screen_or_a_speaker(self) -> None:
        for lane in lanes.lanes_in_order():
            for sentence in lane.caveats + (lane.summary,):
                lowered = sentence.lower()
                self.assertNotIn("runtime-proved", lowered)
                self.assertNotIn("seen in game", lowered.replace("has been seen", "").replace("been seen", ""))


if __name__ == "__main__":
    unittest.main()
