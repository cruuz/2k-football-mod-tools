"""Standalone integrity/transaction tests; only a bounded optional USA XBE."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coverage_trail as trail
from mod_editor.core import nfl2k5_coverage_trail_code as code
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit


class PublicTests(unittest.TestCase):
    def test_budget_and_ui_contract(self):
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertIn(list(trail.REQUESTS[0]), rows)
        self.assertLessEqual(len(code.CODE), trail.CODE_SIZE)
        self.assertLessEqual(len(trail.BUILD_CAPTION), 60)
        for word in ("Retail", "Patch", "EXPERIMENTAL", "UNWITNESSED"):
            self.assertIn(word, trail.HELP_TEXT)
        # Noah played disc bp on 2026-09-08 and saw no circling: on in Advanced and Experimental, off in Basic
        self.assertEqual(trail.mapping()["presets"], {"basic": False, "advanced": True, "experimental": True})
        self.assertEqual(trail.mapping()["runtime_state_bytes"], 0)

    def test_bad_inputs_refuse_before_allocator_write(self):
        for payload in (b"", b"XBEH", bytes(512), None):
            with self.subTest(payload=type(payload).__name__):
                self.assertEqual(trail.status(payload), "foreign")
                with mock.patch.object(space, "apply", side_effect=AssertionError("premature mutation")):
                    with self.assertRaises(ValueError):
                        trail.apply(payload)

    def test_capability_structure_and_own_file_command_checks(self):
        from mod_editor.capabilities import validate_registry as registry
        capability = json.loads((ROOT / "docs/mod_editor/nfl2k5_coverage_trail_capability.json").read_text())
        document = json.loads(registry.DEFAULT_REGISTRY.read_text())
        entries = {row["id"]: row for row in document["capabilities"]}
        entries[capability["id"]] = capability
        document["capabilities"] = [entries[key] for key in sorted(entries)]
        # Existing registry evidence includes absent unrelated research files.
        # Validate all structure, then apply strict file checks to our object.
        registry.validate_data(document, check_files=False)
        for path in capability["evidence"] + capability["runtime"]["evidence"] + [capability["backend"]["module"]]:
            registry._local_path(path, "coverage_trail")
        self.assertEqual(registry._command_module(capability["backend"]["command"], "backend"),
                         capability["backend"]["module"])
        validation = registry._command_module(capability["validation_command"], "validation")
        self.assertIsNotNone(validation)
        registry._local_path(validation, "coverage_trail.validation")

    def test_template_reproduces(self):
        if not shutil.which("as") or sys.platform == "darwin":
            self.skipTest("GNU as with ELF32 output is required for template reproduction")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_coverage_trail_assemble.py"), "--check"],
                       cwd=ROOT, check=True, capture_output=True, text=True)


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = trail.apply(cls.retail)

    def test_replay_and_receipt_are_exact(self):
        self.assertEqual(trail.status(self.retail), "retail")
        self.assertEqual(trail.status(self.patched), "applied")
        self.assertEqual(self.receipt["before_sha256"], hashlib.sha256(self.retail).hexdigest())
        self.assertEqual(self.receipt["after_sha256"], hashlib.sha256(self.patched).hexdigest())
        again, receipt = trail.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(space.status(self.patched), "applied")

    def test_only_owned_code_hook_and_section_hash_change_after_reservation(self):
        allocated, _ = space.apply(self.retail, trail.REQUESTS, scaleout=True)
        result, receipt = trail.apply(allocated)
        self.assertEqual(len(result), len(allocated))
        image = XbeImage(result)
        row = next(a for a in space.layout(result)["allocations"] if a["owner"] == trail.OWNER)
        # Directory seals and section hashes are allocator-owned changes.
        allowed = [(image.offset(trail.HOOK_VA, 6), image.offset(trail.HOOK_VA, 6) + 6),
                   (row["raw"], row["raw"] + row["size"]),
                   (space.DIRECTORY, space.LIB_COPY),
                   (space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE)]
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(result):
            allowed.append((section.header_offset + 36, section.header_offset + 56))
            self.assertEqual(section.stored_digest, section_digest(result, section))
        self.assertEqual([i for i, (a, b) in enumerate(zip(allocated, result))
                          if a != b and not any(lo <= i < hi for lo, hi in allowed)], [])
        self.assertEqual(receipt["file_growth"], 0)
        self.assertFalse(image.runtime_writable(row["va"], row["size"]))
        self.assertEqual([a["kind"] for a in space.layout(result)["allocations"]
                          if a["owner"] == trail.OWNER], ["code"])

    def assert_refused(self, payload):
        self.assertEqual(trail.status(payload), "foreign")
        before = hashlib.sha256(payload).digest()
        with mock.patch.object(space, "apply", side_effect=AssertionError("premature growth")), \
             mock.patch.object(space, "install_code", side_effect=AssertionError("premature code write")):
            with self.assertRaises(ValueError):
                trail.apply(payload)
        self.assertEqual(hashlib.sha256(payload).digest(), before)

    def test_foreign_hook_and_every_prerequisite_fail_before_mutation(self):
        for va, _, _ in trail.GUARDS:
            for source in (self.retail, self.patched):
                byte = XbeImage(source).read(va, 1)
                self.assert_refused(repin_edit(source, va, bytes([byte[0] ^ 1])))

    def test_mixed_and_validly_sealed_foreign_owner_fail(self):
        allocated, _ = space.apply(self.retail, trail.REQUESTS, scaleout=True)
        row = space.layout(allocated)["allocations"][0]
        content = trail.code_for(row["va"])
        code_only = space.install_code(allocated, trail.OWNER, content)[0]
        self.assert_refused(code_only)
        self.assert_refused(repin_edit(allocated, trail.HOOK_VA, trail.sites(row["va"])[0][3]))
        bad = bytearray(content)
        bad[-1] ^= 1
        foreign = space.install_code(allocated, trail.OWNER, bytes(bad))[0]
        self.assert_refused(foreign)
        self.assert_refused(repin_edit(self.patched, trail.HOOK_VA, trail.RETAIL_HOOK))

    def test_unreserved_owner_refuses_without_mutation(self):
        from mod_editor.core import nfl2k5_coverage_slider as coverage
        other = space.apply(self.retail, coverage.REQUESTS, scaleout=True)[0]
        self.assertEqual(trail.status(other), "retail")
        with mock.patch.object(space, "install_code", side_effect=AssertionError("write without allocation")):
            with self.assertRaises(ValueError):
                trail.apply(other)

    def test_ramp_and_coverage_compose_in_both_orders(self):
        from mod_editor.core import nfl2k5_coverage_slider as coverage, nfl2k5_accel_ramp as ramp
        base = space.apply(self.retail, trail.REQUESTS + coverage.REQUESTS, scaleout=True)[0]
        left = trail.apply(coverage.apply(ramp.apply(base)[0])[0])[0]
        right = ramp.apply(coverage.apply(trail.apply(base)[0])[0])[0]
        self.assertEqual(left, right)
        for owner in (trail, coverage, ramp):
            self.assertEqual(owner.status(left), "applied")

    def test_read_only_cli(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import XBE
        result = subprocess.run([sys.executable, "-m", trail.__name__, "--xbe", str(XBE)],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["status"], "retail")

    def test_cli_writes_exact_new_file_and_refuses_existing_or_foreign(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            source, output = base / "source.xbe", base / "new.xbe"
            source.write_bytes(self.retail)
            command = [sys.executable, "-m", trail.__name__, "--xbe", str(source),
                       "--apply", "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(output.read_bytes(), self.patched)
            self.assertEqual(json.loads(result.stdout)["after_sha256"], self.receipt["after_sha256"])
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), self.patched)
            self.assertEqual(source.read_bytes(), self.retail)
            output.unlink()
            source.write_bytes(b"foreign")
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
