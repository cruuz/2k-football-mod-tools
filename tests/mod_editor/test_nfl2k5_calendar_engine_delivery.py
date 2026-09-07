"""Calendar capability handoff and bounded executable-copy CLI. Standalone unittest."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.capabilities import validate_registry as registry
from mod_editor.core import nfl2k5_calendar_engine as calendar
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.product_catalog import build_nfl2k5_product_catalog
from tests.mod_editor.test_nfl2k5_calendar_engine import XBE, RETAIL_SHA256


class HandoffTests(unittest.TestCase):
    def test_candidate_registry_schema_and_product_catalog(self):
        data = json.loads(registry.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
        rows = json.loads((ROOT / "docs/mod_editor/nfl2k5_calendar_engine_capability.json").read_text())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for command in (row["backend"]["command"], row["validation_command"]):
            self.assertTrue(command.startswith("python3 -m "), command)
            self.assertIsNotNone(registry._command_module(command, "calendar.command"))
        # This source checkout omits historical research evidence for other
        # products. Their metadata still participates in the real catalog;
        # the calendar row's file checks are exercised separately below.
        before = CapabilityRegistryLoader().load(allow_sample_fallback=False, check_files=False)
        original_count = len(data["capabilities"])
        existing = any(c["id"] == row["id"] for c in data["capabilities"])
        data["capabilities"] = sorted(
            [c for c in data["capabilities"] if c["id"] != row["id"]] + rows,
            key=lambda c: c["id"])
        registry.validate_data(data, check_files=False)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory).resolve() / "registry.v1.json"
            candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            checked = registry.load_and_validate(candidate, check_files=False)
            self.assertEqual(len(checked["capabilities"]), original_count + int(not existing))
            result = subprocess.run(
                [sys.executable, "mod_editor/capabilities/validate_registry.py", "--registry", str(candidate),
                 "--skip-file-checks"],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            after = CapabilityRegistryLoader(candidate).load(allow_sample_fallback=False, check_files=False)
        old_catalog, catalog = map(build_nfl2k5_product_catalog, (before, after))
        self.assertEqual(len(catalog.sections), len(old_catalog.sections))
        self.assertEqual(len(catalog.capabilities), len(old_catalog.capabilities) + int(not existing))
        self.assertEqual(row["runtime"]["status"], "not-tested")
        self.assertEqual(row["runtime"]["evidence"], [])

    def test_calendar_row_passes_real_validator_file_check_mode(self):
        # validate_data requires complete game/surface coverage, not an isolated
        # capability. Use clearly synthetic coverage rows to exercise the exact
        # unmodified calendar object without requiring unrelated private docs.
        data = json.loads(registry.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
        row, = json.loads((ROOT / "docs/mod_editor/nfl2k5_calendar_engine_capability.json").read_text())
        data["capabilities"] = [row] + [
            {**row, "id": f"fixture.{game}.{surface}", "game": game, "surface": surface,
             "title": "Test-only registry coverage envelope"}
            for surface in registry.SURFACES for game in registry.SURFACE_GAMES[surface]
        ]
        data["capabilities"].sort(key=lambda c: c["id"])
        registry.validate_data(data, check_files=True)
        with tempfile.TemporaryDirectory() as directory:
            envelope = Path(directory).resolve() / "calendar-file-check.json"
            envelope.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
            result = subprocess.run(
                [sys.executable, "mod_editor/capabilities/validate_registry.py", "--registry", str(envelope)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CliTests(unittest.TestCase):
    def run_main(self, source, output):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = calendar.main(["--xbe", str(source), "--output", str(output)])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_module_help_is_a_real_cli(self):
        result = subprocess.run([sys.executable, "-m", "mod_editor.core.nfl2k5_calendar_engine", "--help"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--xbe", result.stdout)
        self.assertIn("--output", result.stdout)

    def test_malformed_and_oversize_inputs_refuse_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = (Path(directory).resolve() / name for name in ("input.xbe", "copy.xbe"))
            source.write_bytes(b"not an executable")
            output.write_bytes(b"KEEP")
            result, stdout, stderr = self.run_main(source, output)
            self.assertEqual(result, 2)
            self.assertEqual(stdout, "")
            self.assertIn("refused", stderr)
            self.assertEqual(output.read_bytes(), b"KEEP")
            output.unlink()
            with source.open("wb") as stream:
                stream.truncate(calendar.space.SCALE_FILE_SIZE + 1)
            result, _, stderr = self.run_main(source, output)
            self.assertEqual(result, 2)
            self.assertIn("exceeds the supported default.xbe size", stderr)
            self.assertFalse(output.exists())

    def test_write_failure_closes_then_removes_only_the_new_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = (Path(directory).resolve() / name for name in ("input.xbe", "copy.xbe"))
            source.write_bytes(b"transport fixture")
            real_open = Path.open
            handles = []

            def failing_open(path, mode="r", *args, **kwargs):
                stream = real_open(path, mode, *args, **kwargs)
                if path == output:
                    handles.append(stream)
                    stream.write = lambda data: 0
                return stream

            with patch.object(calendar, "apply", return_value=(b"transport output", {})), patch.object(
                    Path, "open", new=failing_open):
                result, _, stderr = self.run_main(source, output)
            self.assertEqual(result, 2)
            self.assertIn("short executable write", stderr)
            self.assertTrue(handles[0].closed)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), b"transport fixture")

    @unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe absent")
    def test_cli_receipt_replay_and_existing_output_refusal(self):
        retail = XBE.read_bytes()
        self.assertEqual(hashlib.sha256(retail).hexdigest(), RETAIL_SHA256)
        seed, _ = calendar.season.apply(retail)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, output, replay = (root / name for name in ("source.xbe", "copy.xbe", "replay.xbe"))
            source.write_bytes(seed)
            command = [sys.executable, "-m", "mod_editor.core.nfl2k5_calendar_engine",
                       "--xbe", str(source), "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            written = output.read_bytes()
            self.assertEqual(calendar.status(written), "applied")
            self.assertEqual(receipt["after_sha256"], hashlib.sha256(written).hexdigest())
            self.assertEqual(receipt["base_year"], 2026)
            self.assertFalse(receipt["runtime_witnessed"])
            self.assertEqual(self.run_main(output, replay)[0], 0)
            self.assertEqual(replay.read_bytes(), written)
            for target in (output, source):
                self.assertEqual(self.run_main(source, target)[0], 2)
            self.assertEqual(source.read_bytes(), seed)
            self.assertEqual(output.read_bytes(), written)


if __name__ == "__main__":
    unittest.main()
