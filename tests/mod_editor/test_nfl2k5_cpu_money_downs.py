"""Standalone policy, sealed-owner, refusal and CLI checks; bounded XBE only."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_money_downs as patch
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit, XBE


class PolicyTests(unittest.TestCase):
    def test_published_table_and_defaults(self):
        self.assertEqual(patch.GO_LIMITS["modern"], (0, 1, 2, 3, 2, 2))
        self.assertEqual(patch.GO_LIMITS["aggressive"], (0, 2, 3, 5, 3, 3))
        self.assertEqual(set(patch.mapping()["presets"].values()), {"retail"})
        self.assertEqual(patch.decision(), "go")
        self.assertEqual(patch.decision(level="retail"), "retail")
        self.assertLessEqual(len(patch.assembly.CODE), patch.CODE_SIZE)
        rows = json.loads((ROOT/"tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertIn(list(patch.REQUESTS[0]), rows)

    def test_late_protection_and_trailing_limits(self):
        for margin in (-3, -2, -1, 0, 1, 8, 9, 28):
            self.assertEqual(patch.decision(quarter=4, seconds=120, score_margin=margin), "retail")
        self.assertEqual(patch.decision(quarter=2, seconds=30), "retail")
        self.assertEqual(patch.decision(quarter=4, seconds=121, score_margin=-9, distance=4), "go")
        self.assertEqual(patch.decision(quarter=4, seconds=120, score_margin=-4, distance=6), "go")
        self.assertEqual(patch.decision(quarter=4, seconds=120, score_margin=-4, distance=7), "retail")
        self.assertEqual(patch.decision(quarter=4, seconds=240, score_margin=9, distance=2), "retail")

    def test_invalid_and_non_cpu_states_retain_retail(self):
        for changes in ({"down": 3}, {"quarter": 5}, {"cpu": False}, {"phase": 3},
                        {"own_yard": 19.9}, {"own_yard": 101}, {"distance": 0},
                        {"distance": 21}, {"seconds": -1}, {"score_margin": math.nan}):
            self.assertEqual(patch.decision(**changes), "retail", changes)
        for field in ("own_yard", "distance", "seconds"):
            for value in (math.nan, math.inf, -math.inf, None, True):
                self.assertEqual(patch.decision(**{field: value}), "retail")
        with self.assertRaises(ValueError):
            patch.decision(level="unknown")

    def test_ui_labels(self):
        self.assertLessEqual(len(patch.BUILD_CAPTION), 60)
        for word in ("Retail", "Patch", "EXPERIMENTAL", "UNWITNESSED"):
            self.assertIn(word, patch.HELP_TEXT)
        self.assertNotIn("\u2014", patch.HELP_TEXT)

    def test_bad_payloads_refuse_before_writes(self):
        for payload in (None, b"", b"XBEH", bytes(512)):
            self.assertEqual(patch.status(payload), "foreign")
            with mock.patch.object(space, "apply", side_effect=AssertionError("premature mutation")):
                for level in patch.LEVELS:
                    with self.assertRaises(ValueError):
                        patch.apply(payload, level=level)

    def test_assembly_reproduces(self):
        if not shutil.which("as") or sys.platform in ("darwin", "win32"):
            self.skipTest("GNU as with ELF32 output is required for assembly reproduction")
        subprocess.run([sys.executable, str(ROOT/"tools/nfl2k5_cpu_money_downs_assemble.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True, check=True)

    def test_capability_structure_and_paths(self):
        from mod_editor.capabilities import validate_registry as registry
        own = json.loads((ROOT/"docs/mod_editor/nfl2k5_cpu_money_downs_capability.json").read_text())
        document = json.loads(registry.DEFAULT_REGISTRY.read_text())
        document["capabilities"] = [c for c in document["capabilities"] if c["id"] != own["id"]] + [own]
        document["capabilities"].sort(key=lambda row: row["id"])
        registry.validate_data(document, check_files=False)
        for path in own["evidence"] + own["runtime"]["evidence"] + [own["backend"]["module"]]:
            registry._local_path(path, "cpu_money_downs")
        self.assertEqual(registry._command_module(own["backend"]["command"], "backend"), own["backend"]["module"])
        registry._local_path(registry._command_module(own["validation_command"], "validation"), "validation")


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.outputs = {level: patch.apply(cls.retail, level=level) for level in patch.LEVELS}

    def test_every_level_replay_and_receipts(self):
        for level, (output, receipt) in self.outputs.items():
            with self.subTest(level=level):
                self.assertEqual(patch.status(output), "retail" if level == "retail" else "applied")
                replay, repeated = patch.apply(output, level=level)
                self.assertIs(replay, output)
                self.assertEqual(repeated["changed_bytes"], 0)
                if level != "retail":
                    self.assertEqual(patch.read_settings(output)["level"], level)
                    self.assertEqual(receipt["before_sha256"], hashlib.sha256(self.retail).hexdigest())
                    self.assertEqual(receipt["after_sha256"], hashlib.sha256(output).hexdigest())
                    self.assertEqual(space.status(output), "applied")
                    self.assertTrue(space.is_scaleout(output))
        self.assertIs(self.outputs["retail"][0], self.retail)

    def assert_refused(self, payload):
        self.assertEqual(patch.status(payload), "foreign")
        with mock.patch.object(space, "apply", side_effect=AssertionError("premature allocation")), \
             mock.patch.object(space, "install_code", side_effect=AssertionError("premature write")):
            with self.assertRaises(ValueError):
                patch.apply(payload)

    def test_each_dependency_hook_and_mixed_state_refuses(self):
        active = self.outputs["modern"][0]
        for source in (self.retail, active):
            image = XbeImage(source)
            for va, _size, _digest in patch.GUARDS:
                self.assert_refused(repin_edit(source, va, bytes([image.read(va, 1)[0] ^ 1])))
            for va, before in patch.HOOKS.values():
                self.assert_refused(repin_edit(source, va, bytes([image.read(va, 1)[0] ^ 1])))
        for va, before in patch.HOOKS.values():
            self.assert_refused(repin_edit(active, va, before))

    def test_sealed_foreign_code_and_code_without_hooks_refuse(self):
        allocated = space.apply(self.retail, patch.REQUESTS, scaleout=True)[0]
        row = next(a for a in space.layout(allocated)["allocations"] if a["owner"] == patch.OWNER)
        code = patch.code_for(row["va"])
        self.assert_refused(space.install_code(allocated, patch.OWNER, code)[0])
        active = patch.apply(allocated)[0]
        with self.assertRaises(ValueError):
            space.install_code(active, patch.OWNER, code[:-1]+b"\0")
        bad = space.install_code(allocated, patch.OWNER, code[:-1]+b"\0")[0]
        for _name, va, _before, after in patch.sites(row["va"]):
            bad = repin_edit(bad, va, after)
        self.assertEqual(space.status(bad), "applied")
        self.assert_refused(bad)
        for _name, va, _before, after in patch.sites(row["va"]):
            self.assert_refused(repin_edit(allocated, va, after))

    def test_missing_allocation_and_level_change_require_rebuild(self):
        from mod_editor.core import nfl2k5_coverage_slider as other
        allocated = space.apply(self.retail, other.REQUESTS, scaleout=True)[0]
        with self.assertRaises(ValueError):
            patch.apply(allocated)
        for before in patch.LEVELS[1:]:
            for after in patch.LEVELS:
                if before != after:
                    with self.assertRaises(ValueError):
                        patch.apply(self.outputs[before][0], level=after)

    def test_read_only_cli_and_existing_output_preserved(self):
        command = [sys.executable, "-m", "mod_editor.core.nfl2k5_cpu_money_downs", "--xbe", str(XBE)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["status"], "retail")
        with tempfile.TemporaryDirectory(prefix="money-downs-cli-") as directory:
            target = Path(directory).resolve()/"existing.xbe"
            target.write_bytes(b"keep this file")
            result = subprocess.run(command+["--apply", "--output", str(target)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(target.read_bytes(), b"keep this file")


if __name__ == "__main__":
    unittest.main()
