#!/usr/bin/env python3
"""Refusal tests for the frozen APF Xenia controller capture provenance."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_xenia_controller_capture_provenance as provenance  # noqa: E402


class ApfXeniaControllerCaptureProvenanceTest(unittest.TestCase):
    def fixture_root(self, directory: str) -> Path:
        root = Path(directory)
        relatives = [provenance.MANIFEST, provenance.FROZEN_SOURCE]
        for binding in provenance.EXPECTED_BINDINGS:
            relatives.extend(
                [binding["report"]["path"], binding["transcript"]["path"]]
            )
        for relative in relatives:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return root

    def test_canonical_manifest_binds_all_three_legacy_captures(self) -> None:
        result = provenance.validate()
        self.assertEqual(result["binding_count"], 3)
        self.assertEqual(result["source_size"], 3051)
        self.assertEqual(result["source_sha256"], provenance.FROZEN_SOURCE_SHA256)

    def test_one_binding_can_be_checked_without_reading_unrelated_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            unrelated = root / provenance.EXPECTED_BINDINGS[1]["report"]["path"]
            unrelated.unlink()
            result = provenance.validate(
                root, binding_id="americans_uniform_solid_20260710"
            )
            self.assertEqual(result["binding_ids"], ["americans_uniform_solid_20260710"])

    def test_current_development_successor_is_not_capture_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            successor = root / provenance.RECORDED_INVOCATION_PATH
            successor.parent.mkdir(parents=True, exist_ok=True)
            successor.write_text("this mutable successor is deliberately unrelated\n")
            self.assertEqual(
                provenance.validate(
                    root,
                    binding_id="americans_uniform_pattern_alpha64_20260710",
                )["source_sha256"],
                provenance.FROZEN_SOURCE_SHA256,
            )

    @unittest.skipUnless(
        (
            Path.home()
            / provenance.EXPECTED_RECOVERY["session_log_home_relative"]
        ).is_file(),
        "private recovery session is not retained on this host",
    )
    def test_later_preserved_session_output_recovers_exact_frozen_bytes(self) -> None:
        session_log = (
            Path.home()
            / provenance.EXPECTED_RECOVERY["session_log_home_relative"]
        )
        recovered = provenance.recover_source_from_session_record(session_log)
        frozen = (ROOT / provenance.FROZEN_SOURCE).read_bytes()
        self.assertEqual(recovered, frozen)
        self.assertEqual(len(recovered), provenance.FROZEN_SOURCE_SIZE)

    def test_manifest_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            path = root / provenance.MANIFEST
            payload = bytearray(path.read_bytes())
            payload[20] ^= 1
            path.write_bytes(payload)
            with self.assertRaisesRegex(provenance.ProvenanceError, "manifest SHA-256"):
                provenance.validate(root)

    def test_frozen_source_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            path = root / provenance.FROZEN_SOURCE
            payload = bytearray(path.read_bytes())
            payload[100] ^= 1
            path.write_bytes(payload)
            with self.assertRaisesRegex(provenance.ProvenanceError, "source SHA-256"):
                provenance.validate(root)

    def test_bound_report_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            binding = provenance.EXPECTED_BINDINGS[0]
            path = root / binding["report"]["path"]
            payload = bytearray(path.read_bytes())
            payload[100] ^= 1
            path.write_bytes(payload)
            with self.assertRaisesRegex(provenance.ProvenanceError, "report SHA-256"):
                provenance.validate(root, binding_id=binding["id"])

    def test_frozen_source_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            path = root / provenance.FROZEN_SOURCE
            alternate = root / "alternate-controller.py"
            shutil.copyfile(path, alternate)
            path.unlink()
            path.symlink_to(alternate)
            with self.assertRaisesRegex(
                provenance.ProvenanceError, "regular non-symlink"
            ):
                provenance.validate(root)

    def test_frozen_source_hardlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture_root(directory)
            source = root / provenance.FROZEN_SOURCE
            os.link(source, root / "second-name.py")
            with self.assertRaisesRegex(provenance.ProvenanceError, "hardlinked"):
                provenance.validate(root)

    def test_unsafe_relative_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(provenance.ProvenanceError, "unsafe component"):
            provenance._safe_relative("reports/../outside", "test")

    def test_pattern_validators_rebuild_copied_volumes_in_private_scratch(self) -> None:
        validators = (
            ROOT / "tools/validate_apf_uniform_pattern_xenia_runtime.sh",
            ROOT / "tools/validate_apf_uniform_pattern_alpha0_xenia_runtime.sh",
        )
        for path in validators:
            source = path.read_text(encoding="utf-8")
            self.assertIn("scratch_root=$(mktemp -d /tmp/", source)
            self.assertIn('trap cleanup EXIT', source)
            self.assertIn('rm -rf -- "$scratch_root"', source)
            self.assertIn('--output-volume "$scratch_game/0A"', source)
            self.assertIn('! -name 0A', source)

    def test_pattern_validators_do_not_require_retained_copied_volumes(self) -> None:
        combined = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "tools/validate_apf_uniform_pattern_xenia_runtime.sh",
                "tools/validate_apf_uniform_pattern_alpha0_xenia_runtime.sh",
            )
        )
        self.assertNotIn("game-pattern-patched/0A", combined)
        self.assertNotIn("game-pattern-alpha0/0A", combined)

    def test_runtime_validators_pin_checker_and_recheck_each_binding(self) -> None:
        validators = {
            "tools/validate_apf_uniform_xenia_runtime.sh": (
                "americans_uniform_solid_20260710",
                provenance.EXPECTED_BINDINGS[0]["report"],
            ),
            "tools/validate_apf_uniform_pattern_xenia_runtime.sh": (
                "americans_uniform_pattern_alpha64_20260710",
                provenance.EXPECTED_BINDINGS[1]["report"],
            ),
            "tools/validate_apf_uniform_pattern_alpha0_xenia_runtime.sh": (
                "americans_uniform_pattern_alpha0_20260710",
                provenance.EXPECTED_BINDINGS[2]["report"],
            ),
        }
        checker = ROOT / "tools/apf_xenia_controller_capture_provenance.py"
        checker_size = checker.stat().st_size
        checker_sha256 = hashlib.sha256(checker.read_bytes()).hexdigest()
        for relative, (binding_id, report) in validators.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(f"controller_provenance_size={checker_size}", source)
            self.assertIn(
                f"controller_provenance_sha256={checker_sha256}", source
            )
            self.assertEqual(source.count(f"--binding {binding_id}"), 2)
            self.assertIn(f'"{report["sha256"]}"', source)
            self.assertIn("controller_provenance.read_bound(", source)


if __name__ == "__main__":
    unittest.main()
