"""Standalone screen hook integrity, budgets, receipts and refusal tests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_screen_hooks as patch
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

EXTRACT = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
XBE = EXTRACT / "default.xbe"


def retail_xbe():
    if not XBE.is_file():
        raise unittest.SkipTest("private USA retail default.xbe extraction absent")
    with XBE.open("rb") as stream:
        payload = stream.read(12_300_289)
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise unittest.SkipTest("local XBE differs from pinned USA retail evidence")
    return payload


def repin(payload):
    out = bytearray(payload)
    for section in _sections(out):
        out[section.header_offset+36:section.header_offset+56] = section_digest(out, section)
    return bytes(out)


class ContractTests(unittest.TestCase):
    def test_budget_fixture_and_union(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == patch.OWNER], list(patch.REQUESTS))
        self.assertEqual([r for r in REQUESTS if r[0] == patch.OWNER], list(patch.REQUESTS))
        self.assertLessEqual(len(patch.assembly.CODE), 640)
        self.assertEqual(patch.REQUESTS, ((patch.OWNER, "code", 640, 16),))
        self.assertTrue(space.plan(rows))

    def test_second_experiment_copy(self):
        for phrase in ("Retail", "Patch", "second experiment", "timing levels A-D", "UNWITNESSED", "presets are off"):
            self.assertIn(phrase, patch.HELP_TEXT)
        self.assertLessEqual(len(patch.BUILD_CAPTION), 60)

    def test_reproducible_assembler(self):
        if not shutil.which("as"):
            self.skipTest("GNU ELF32 assembler absent; no assembler required at runtime")
        probe = subprocess.run(["as", "--version"], capture_output=True, text=True)
        if probe.returncode or "GNU assembler" not in probe.stdout:
            self.skipTest("platform assembler is not GNU as")
        from nfl2k5_screen_hooks_assemble import generate, TARGET
        self.assertEqual(generate(), TARGET.read_text())

    def test_capability_schema_commands_and_evidence_files(self):
        from mod_editor.capabilities import validate_registry as validator
        data = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        capability = json.loads((ROOT / "docs/mod_editor/nfl2k5_screen_hooks_capability.json").read_text())
        data["capabilities"] = [c for c in data["capabilities"] if c["id"] != capability["id"]]+[capability]
        data["capabilities"].sort(key=lambda c: c["id"])
        validator.validate_data(data, check_files=False)
        # Check this handoff's exact files without inheriting unrelated legacy
        # registry references to absent APF research documents.
        for relative in capability["evidence"]+[capability["backend"]["module"]]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        for command, expected in ((capability["backend"]["command"], capability["backend"]["module"]),
                                  (capability["validation_command"], "tests/mod_editor/test_nfl2k5_screen_hooks.py")):
            self.assertEqual(validator._command_module(command, capability["id"]), expected)
        self.assertFalse(capability["gui"]["default_enabled"])

    def test_invalid_payload_refuses_before_install(self):
        with mock_patch.object(space, "install_code", side_effect=AssertionError("mutation before refusal")):
            for bad in (None, b"", b"XBEH", bytes(1024)):
                self.assertEqual(patch.status(bad), "foreign")
                self.assertIsNone(patch.read_settings(bad))
                with self.assertRaises((ValueError, TypeError)):
                    patch.apply(bad)


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = patch.apply(cls.retail)

    def test_replay_exact_receipts_digests_and_permissions(self):
        self.assertEqual(patch.status(self.retail), "retail")
        self.assertEqual(patch.status(self.patched), "applied")
        replay, receipt = patch.apply(self.patched)
        self.assertIs(replay, self.patched)
        self.assertEqual((receipt["status"], receipt["changed_bytes"], receipt["edits"]), ("already_applied", 0, []))
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.retail, self.patched)) + len(self.patched)-len(self.retail))
        image = XbeImage(self.patched)
        row = patch.allocation(self.patched)
        self.assertTrue(image.section(row["va"]).executable)
        self.assertFalse(image.runtime_writable(row["va"], row["size"]))
        self.assertNotEqual(image.section(row["va"]).name, ".text")
        for edit in self.receipt["edits"]:
            self.assertEqual(image.read(int(edit["va"], 0), edit["size"]), bytes.fromhex(edit["after"]))
        self.assertEqual([e["size"] for e in self.receipt["edits"]], [9, 7])
        for section in _sections(self.patched):
            self.assertEqual(section_digest(self.patched, section), section.stored_digest)
        self.assertEqual(patch.read_settings(self.patched)["experiment_order"], 2)
        self.assertFalse(patch.read_settings(self.patched)["runtime_witnessed"])

    def test_mixed_hooks_code_padding_and_dependencies_refuse_before_mutation(self):
        image = XbeImage(self.patched)
        code = patch.allocation(self.patched)["va"]
        for va in (*[va for va, _ in patch.HOOKS.values()], code, code+639,
                   *[va for va, _size, _digest in patch.GUARDS]):
            bad = bytearray(self.patched)
            bad[image.offset(va)] ^= 1
            bad = repin(bad)
            with self.subTest(va=hex(va)), mock_patch.object(space, "install_code", side_effect=AssertionError("mutation")):
                self.assertEqual(patch.status(bad), "foreign")
                with self.assertRaises(ValueError):
                    patch.apply(bad)
        # A complete code seal cannot bless a missing hook or a different body.
        allocated, _ = space.apply(self.retail, patch.REQUESTS, scaleout=True)
        code = patch.allocation(allocated)["va"]
        installed, _ = space.install_code(allocated, patch.OWNER, patch.code_for(code))
        self.assertEqual(patch.status(installed), "foreign")
        with self.assertRaises(ValueError):
            patch.apply(installed)

    def test_preallocated_missing_and_wrong_request_refuse(self):
        for requests in ((("unrelated_screen_test", "code", 16, 16),),
                         ((patch.OWNER, "code", 624, 16),),
                         ((patch.OWNER, "data", 640, 16),)):
            allocated, _ = space.apply(self.retail, requests, scaleout=True)
            with self.assertRaisesRegex(ValueError, "allocation"):
                patch.apply(allocated)
        allocated, _ = space.apply(self.retail, patch.REQUESTS, scaleout=True)
        self.assertEqual(patch.status(allocated), "retail")
        self.assertEqual(patch.apply(allocated)[0], self.patched)

    def test_only_owned_hooks_change_retail_sections(self):
        before, after = XbeImage(self.retail), XbeImage(self.patched)
        for section in before.sections:
            # Allocator explicitly relocates the boot bitmap. All other changes
            # within the original sections must be the two exact live hooks.
            if section.name == ".XTLID":
                continue
            old = before.read(section.start, section.raw_size)
            new = bytearray(after.read(section.start, section.raw_size))
            for va, content in patch.HOOKS.values():
                if section.start <= va < section.end:
                    new[va-section.start:va-section.start+len(content)] = content
            self.assertEqual(old, new, section.name)

    def test_cli_exclusive_copy_and_bounded_read(self):
        with tempfile.TemporaryDirectory(prefix="screen-hooks-") as directory:
            root = Path(directory).resolve()
            source, target = root / "source.xbe", root / "new.xbe"
            source.write_bytes(self.retail)
            command = [sys.executable, "-m", "mod_editor.core.nfl2k5_screen_hooks", "apply", str(source), "--output", str(target)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), self.patched)
            self.assertEqual(json.loads(result.stdout)["status"], "applied")
            self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 2)
            self.assertEqual(source.read_bytes(), self.retail)
            # Sparse, bounded fixture; never a disc or archive pack.
            with source.open("wb") as stream:
                stream.truncate(12_300_289)
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("not a disc or archive pack", result.stderr)


if __name__ == "__main__":
    unittest.main()
