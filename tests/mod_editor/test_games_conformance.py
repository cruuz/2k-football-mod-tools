"""The conformance suite: every hosted game module, proved without game data.

This is the file the maintainer's CI runs for a game he has never seen.  It
discovers every game package, runs the generic harness on each -- manifest,
boundary, registry agreement, and the behavioural half on the game's own
synthetic source: identify, catalogue (retail-free), plan, refuse, build,
verify, tamper -- and fails on any check.  It also proves the harness can
fail, with a deliberately broken lane, because a harness that cannot fail
proves nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import conformance, contract  # noqa: E402


class EveryHostedGameConformsTests(unittest.TestCase):
    """The CI gate.  A new game under mod_editor/games/ is covered with no edit here."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = games.discover()
        cls.work = Path(tempfile.mkdtemp(prefix="games-conformance-"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_no_package_is_refused(self) -> None:
        self.assertEqual(self.report.refused, ())
        self.assertTrue(self.report.games, "at least one game module is hosted")

    def test_every_hosted_game_passes_the_harness(self) -> None:
        for game in self.report.games:
            with self.subTest(game=game.game_id):
                result = conformance.run(game, self.work / game.game_id)
                self.assertTrue(result.passed, "\n".join(check.line() for check in result.failures))
                self.assertGreaterEqual(len(result.checks), 20)

    def test_the_command_line_entry_agrees(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "mod_editor.games", "--conformance", "--static-only"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("conformance checks passed", completed.stdout)
        self.assertNotIn("FAIL", completed.stdout)


class Ps2AdapterBehaviourTests(unittest.TestCase):
    """The wrapped lane, driven only through the contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.game = games.load("nfl2k5_ps2")
        cls.lane = cls.game.lane("colors.unif_words")
        cls.work = Path(tempfile.mkdtemp(prefix="ps2-adapter-"))
        cls.source = cls.lane.synthetic_source(cls.work)
        cls.catalogue = cls.lane.build_catalogue(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_identity_through_the_shared_ps2_format_package(self) -> None:
        identity = self.game.identifier.identify(self.source)
        self.assertEqual(identity.kind, "ps2-iso")
        self.assertEqual(identity.serial, "SLUS-20919")
        self.assertTrue(identity.serial_matches)
        self.assertFalse(identity.retail_executable)
        self.assertIn("boot ELF differs from retail", identity.headline)
        self.assertEqual(identity.details["expected_serials"], ["SLUS-20919"])
        with self.assertRaisesRegex(contract.Refusal, "cannot be opened|not a regular file"):
            self.game.identifier.identify(self.work / "absent.iso")
        junk = self.work / "junk.iso"
        junk.write_bytes(b"not a disc" * 100)
        with self.assertRaises(contract.Refusal):
            self.game.identifier.identify(junk)

    def test_catalogue_targets_and_inline_refusals(self) -> None:
        keys = [target.key for target in self.catalogue.targets]
        self.assertEqual(keys, ["18H0", "18A0"])
        target = self.catalogue.target("18H0")
        self.assertIn("uniform package 18 · home · variant 0", target.label)
        self.assertIn("4 bytes", target.budget)
        self.assertIsNone(self.lane.check_edit(target, {"facemask": "#112233"}))
        self.assertIn("choose facemask, turtleneck or both", self.lane.check_edit(target, {"visor": "#1"}))
        self.assertIn("give a facemask colour", self.lane.check_edit(target, {}))
        self.assertIn("exactly 4 bytes", self.lane.check_edit(target, {"turtleneck": "FFAABBCCDD"}))

    def test_refusals_are_the_tools_own_sentences(self) -> None:
        recipe = self.lane.compose_recipe((contract.Edit("07H1", {"facemask": "#000000"}),))
        with self.assertRaisesRegex(contract.Refusal, "recompressed back into the stored span"):
            self.lane.plan(self.source, recipe, self.catalogue)
        noop = self.lane.compose_recipe((contract.Edit("18H0", {"facemask": "FFA29895"}),))
        with self.assertRaisesRegex(contract.Refusal, "already uses those colours"):
            self.lane.plan(self.source, noop, self.catalogue)
        with self.assertRaisesRegex(contract.Refusal, "recipe schema"):
            self.lane.plan(self.source, {"schema": "nope", "edits": []}, self.catalogue)
        destination = self.work / "refused.iso"
        with self.assertRaises(contract.Refusal):
            self.lane.build(self.source, destination, recipe, self.catalogue, work_dir=self.work)
        self.assertFalse(destination.exists(), "a refusal leaves no destination behind")

    def test_plan_build_verify_and_a_lying_receipt(self) -> None:
        recipe = self.lane.compose_recipe((contract.Edit("18A0", {"turtleneck": "FF010203"}),))
        plan = self.lane.plan(self.source, recipe, self.catalogue)
        self.assertEqual(plan.target_keys, ("18A0",))
        self.assertEqual(plan.declared_bytes, 8)
        destination = self.work / "built.iso"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue, work_dir=self.work)
        self.assertEqual(receipt.schema, "nfl2k5_ps2_unif_color_write/v1")
        self.assertEqual([(r.start, r.length) for r in receipt.declared_ranges],
                         [(r.start, r.length) for r in plan.declared_ranges])
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("1 edit(s) verified", verdict.summary)
        lying = json.loads(json.dumps(dict(receipt.document)))
        lying["edits"][0]["after_sha256"] = "0" * 64
        bad = contract.Receipt(receipt.schema, receipt.lane_id, receipt.source, receipt.destination,
                               receipt.declared_ranges, lying)
        verdict = self.lane.verify(self.source, destination, bad)
        self.assertFalse(verdict.passed)
        self.assertIn("does not hold the span the receipt recorded", verdict.summary)


class _BrokenLane:
    """A lane that changes a byte it never declares and whose verifier cannot fail."""

    lane_id = "broken.lane"
    capability_id = "broken.lane.row"
    surface = "saves"
    title = "Broken"
    classification = "offline-writer-proved"
    recipe_schema = "broken/v1"
    validators = ()
    fixed_allocation = True

    def build_catalogue(self, source, *, progress=None):
        return contract.Catalogue("broken_catalog/v1", self.lane_id, str(source),
                                  (contract.Target("t0", "Target 0"),), {"targets": ["t0"]})

    def check_edit(self, target, values):
        return None

    def compose_recipe(self, edits):
        return {"schema": self.recipe_schema, "edits": [edit.target_key for edit in edits]}

    def plan(self, source, recipe, catalogue):
        if recipe["edits"] != ["t0"]:
            raise contract.Refusal("only t0 exists here")
        return contract.Plan(self.lane_id, ("t0",), (contract.DeclaredRange(0, 1, "t0"),))

    def build(self, source, destination, recipe, catalogue, *, work_dir=None):
        contract.require(not Path(destination).exists(), f"{destination} exists")
        contract.require(Path(destination) != Path(source), "source is destination")
        data = bytearray(Path(source).read_bytes())
        data[0] ^= 0xFF
        data[5] ^= 0xFF  # never declared
        Path(destination).write_bytes(bytes(data))
        return contract.Receipt("broken_write/v1", self.lane_id, str(source), str(destination),
                                (contract.DeclaredRange(0, 1, "t0"),), {})

    def verify(self, source, destination, receipt):
        return contract.Verdict(True, "always fine")

    def synthetic_source(self, work_dir):
        path = Path(work_dir) / "broken.bin"
        path.write_bytes(bytes(range(16)))
        return path

    def conformance_edits(self, catalogue):
        return (contract.Edit("t0", {}),)


class HarnessCanFailTests(unittest.TestCase):
    def test_a_broken_lane_is_caught_by_name(self) -> None:
        game = games.load("nfl2k5_ps2")
        work = Path(tempfile.mkdtemp(prefix="broken-lane-"))
        self.addCleanup(shutil.rmtree, work, True)
        lane = _BrokenLane()
        checks = conformance.check_lane_behaviour(game, lane, work)
        prefix = f"lane.{lane.lane_id}."
        failed = {check.name[len(prefix):] for check in checks if not check.passed}
        self.assertIn("every_changed_byte_is_declared", failed)
        self.assertIn("verify_fails_on_undeclared_change", failed)
        self.assertIn("identify", failed, "a synthetic source that is not this game's is caught")
        passed = {check.name[len(prefix):] for check in checks if check.passed}
        self.assertIn("build_refuses_existing_destination", passed)

    def test_payload_detection_matches_the_release_gate_rules(self) -> None:
        self.assertTrue(conformance.contains_payload({"payload": "abc"}))
        self.assertTrue(conformance.contains_payload({"x": [0] * 300}))
        self.assertTrue(conformance.contains_payload({"x": "data:image/png;base64,AAAA"}))
        self.assertFalse(conformance.contains_payload({"sha256": "ab" * 32, "offsets": [1, 2, 3]}))


if __name__ == "__main__":
    unittest.main()
