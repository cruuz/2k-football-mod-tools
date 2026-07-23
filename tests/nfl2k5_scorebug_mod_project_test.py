#!/usr/bin/env python3
"""Tests for the typed NFL 2K5 scorebug project backend."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_scorebug_mod_project as project  # noqa: E402


EXAMPLE = ROOT / "reports/assets/nfl2k5_scorebug_mod_project_example.json"


class ScorebugProjectTests(unittest.TestCase):
    def fixture(self) -> dict[str, object]:
        return json.loads(EXAMPLE.read_bytes())

    def write_project(self, root: Path, value: dict[str, object]) -> Path:
        path = root / "project.json"
        path.write_bytes(project.canonical_json(value))
        return path

    def test_example_is_canonical_and_all_three_importers_pass(self) -> None:
        parsed = project.read_project(EXAMPLE)
        self.assertEqual(
            [edit["target"] for edit in parsed.value["edits"]],
            ["score_buga", "shield_espn", "digital_font"],
        )
        result = project.validate_only(EXAMPLE)
        self.assertTrue(result["source_pins_valid"])
        self.assertTrue(result["strict_importers_passed"])
        self.assertEqual(result["edit_count"], 3)

    def test_noncanonical_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "project.json"
            path.write_text(json.dumps(self.fixture()))
            with self.assertRaisesRegex(project.ScorebugProjectError, "canonical"):
                project.read_project(path)

    def test_duplicate_target_is_rejected(self) -> None:
        value = self.fixture()
        value["edits"] = [value["edits"][0], copy.deepcopy(value["edits"][0])]
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_project(Path(temporary), value)
            with self.assertRaisesRegex(project.ScorebugProjectError, "at most once"):
                project.read_project(path)

    def test_unknown_field_and_target_are_rejected(self) -> None:
        for mutation in ("field", "target"):
            value = self.fixture()
            value["edits"] = [copy.deepcopy(value["edits"][0])]
            if mutation == "field":
                value["edits"][0]["offset"] = 1234
            else:
                value["edits"][0]["target"] = "arbitrary_texture"
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                path = self.write_project(Path(tmp), value)
                with self.assertRaises(project.ScorebugProjectError):
                    project.read_project(path)

    def test_forged_source_pin_is_rejected(self) -> None:
        value = self.fixture()
        value["source"]["xiso_size"] -= 1
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_project(Path(temporary), value)
            with self.assertRaisesRegex(project.ScorebugProjectError, "source pins"):
                project.read_project(path)

    def test_png_hash_pin_is_rejected_before_import(self) -> None:
        value = self.fixture()
        value["edits"] = [copy.deepcopy(value["edits"][0])]
        value["edits"][0]["png"] = str(
            ROOT / "reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png")
        value["edits"][0]["png_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_project(Path(temporary), value)
            parsed = project.read_project(path)
            with self.assertRaisesRegex(project.ScorebugProjectError, "size/SHA-256"):
                project.pin_project_pngs(parsed)

    def test_symlink_png_is_rejected(self) -> None:
        value = self.fixture()
        value["edits"] = [copy.deepcopy(value["edits"][0])]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / "linked.png"
            link.symlink_to(
                ROOT / "reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png")
            value["edits"][0]["png"] = "linked.png"
            path = self.write_project(root, value)
            parsed = project.read_project(path)
            with self.assertRaisesRegex(project.ScorebugProjectError, "non-symlink"):
                project.pin_project_pngs(parsed)

    def test_artifact_verifier_reconstructs_bytes_and_rejects_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "artifacts"
            payloads = {"a.import.json": b"{}\n", "a.preview.png": b"PNG"}
            created, identity, files, ledger = project.create_artifacts(root, payloads)
            try:
                verified, verified_identity, rebuilt = project.verify_artifacts(
                    root, payloads)
                self.assertEqual((verified, verified_identity, rebuilt),
                                 (created, identity, ledger))
                (root / "a.preview.png").write_bytes(b"forged")
                with self.assertRaisesRegex(project.ScorebugProjectError,
                                            "independently rebuilt"):
                    project.verify_artifacts(root, payloads)
            finally:
                project.cleanup_artifacts(created, identity, files)

    def test_difference_run_and_offset_hash_are_deterministic(self) -> None:
        offsets = [1, 2, 5, 6, 7, 100]
        self.assertEqual(project.runs(offsets), [[1, 2], [5, 7], [100, 100]])
        self.assertEqual(project.offset_hash(offsets, "<I"),
                         project.offset_hash(list(offsets), "<I"))

    def test_union_record_checks_every_byte_in_a_synthetic_image(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        output[4:7] = b"xyz"
        allowed = {index for index, (left, right) in
                   enumerate(zip(source, output)) if left != right}
        with tempfile.TemporaryDirectory() as temporary:
            source_path = Path(temporary) / "source.bin"
            output_path = Path(temporary) / "output.bin"
            source_path.write_bytes(source)
            output_path.write_bytes(output)
            source_fd = os.open(source_path, os.O_RDONLY)
            output_fd = os.open(output_path, os.O_RDONLY)
            original_size = project.common.EXPECTED_XISO_SIZE
            project.common.EXPECTED_XISO_SIZE = len(source)
            try:
                record = project.union_record(
                    [], source_fd, output_fd, hashlib.sha256(source).hexdigest(), allowed)
                self.assertEqual(record["actual_changed_byte_count"], len(allowed))
                self.assertTrue(record["all_bytes_outside_union_identical"])
                with self.assertRaises(ValueError):
                    project.union_record(
                        [], source_fd, output_fd,
                        hashlib.sha256(source).hexdigest(), {4})
            finally:
                project.common.EXPECTED_XISO_SIZE = original_size
                os.close(source_fd)
                os.close(output_fd)


if __name__ == "__main__":
    unittest.main()
