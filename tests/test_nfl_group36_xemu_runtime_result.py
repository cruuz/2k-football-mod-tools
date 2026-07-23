#!/usr/bin/env python3
"""Synthetic tests for the bounded NFL group36 xemu result envelope."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
import sys

sys.path.insert(0, str(TOOLS))
import nfl_group36_xemu_runtime_result as result  # noqa: E402


REPORT = ROOT / "reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json"
SCHEMA = ROOT / "reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json"


def artifact(path: str, digest: str = "1" * 64, size: int = 1) -> dict:
    return {"path": path, "sha256": digest, "size": size}


def screenshot(role: str, suffix: str) -> dict:
    return {
        "path": f"synthetic/{suffix}.png",
        "role": role,
        "sha256": hashlib.sha256(suffix.encode()).hexdigest(),
        "size": len(suffix) + 1,
    }


def boot() -> dict:
    return {
        "evidence_screenshot_roles": ["title_or_gameplay"],
        "kind": "boot_acceptance",
        "observation": {
            "clean_shutdown_observed": True,
            "reached": "rendered_title_or_gameplay",
        },
    }


def target_visible(pair_id: str, geometry: bool) -> dict:
    return {
        "evidence_screenshot_roles": ["target_visible"],
        "kind": "target_visible",
        "observation": {
            "geometry_difference_visible": geometry,
            "matched_pair_id": pair_id,
            "outer_filename": "s42nd.iff",
            "stadium": "Super Bowl 2006 Stadium",
            "time_of_day": "Night",
            "weather": "Clear",
        },
    }


def pins(document: dict) -> dict:
    return {
        name: {
            "artifacts": copy.deepcopy(document["runs"][name]["artifacts"]),
            "observation_status": document["runs"][name]["observation_status"],
            "outcomes": [row["kind"] for row in document["runs"][name]["outcomes"]],
        }
        for name in result.RUN_NAMES
    }


def refresh(document: dict) -> None:
    document["claims"] = result.derive_claims(document["runs"])
    document["status"] = result.derive_status(document["claims"])


class RuntimeResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(REPORT.read_bytes())

    def test_checked_partial_result_has_only_control_selector_negative(self) -> None:
        claims = result.validate_document(self.document, pins(self.document))
        self.assertTrue(claims["control_selector_skip_negative_observed"])
        self.assertTrue(claims["s42_index18_quick_game_skip_observed"])
        self.assertFalse(claims["xemu_boot_acceptance_proved"])
        self.assertFalse(claims["target_outer_loaded_proved"])
        self.assertFalse(claims["control_target_visible"])
        self.assertFalse(claims["expanded_target_visible"])
        self.assertFalse(claims["geometry_visibility_proved"])
        self.assertEqual(self.document["status"], "selector_skip_negative")

    def test_fully_unobserved_result_derives_all_false(self) -> None:
        document = copy.deepcopy(self.document)
        for name in result.RUN_NAMES:
            run = document["runs"][name]
            run["artifacts"] = {"config": None, "hdd": None, "screenshots": [], "xiso": None}
            run["observation_status"] = "unobserved"
            run["outcomes"] = []
            run["reason"] = "No runtime observation is admitted."
        refresh(document)
        claims = result.validate_document(document, pins(document))
        self.assertTrue(all(value is False for value in claims.values()))
        self.assertEqual(document["status"], "unobserved")

    def test_unobserved_run_refuses_placeholder_hashes(self) -> None:
        document = copy.deepcopy(self.document)
        document["runs"]["expanded_wall"]["artifacts"]["config"] = artifact(
            "synthetic/not-observed.toml"
        )
        with self.assertRaisesRegex(result.ResultError, "no artifact placeholder"):
            result.validate_document(document)

    def test_cli_pin_mismatch_is_refused(self) -> None:
        expected = pins(self.document)
        expected["control"]["artifacts"]["hdd"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(result.ResultError, "CLI control artifact pins differ"):
            result.validate_document(self.document, expected)

    def test_selector_negative_cannot_promote_target_or_geometry(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["target_outer_loaded_proved"] = True
        with self.assertRaisesRegex(result.ResultError, "independently derived"):
            result.validate_document(document)
        document = copy.deepcopy(self.document)
        document["runs"]["control"]["outcomes"][0]["observation"][
            "rewritten_record_presented"
        ] = True
        with self.assertRaisesRegex(result.ResultError, "observation differs"):
            result.validate_document(document)

    def test_outcome_enum_and_canonical_order_are_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["runs"]["control"]["outcomes"][0]["kind"] = "no_crash"
        with self.assertRaisesRegex(result.ResultError, "kind is invalid"):
            result.validate_document(document)
        document = self._paired_target_document()
        document["runs"]["control"]["outcomes"].reverse()
        with self.assertRaisesRegex(result.ResultError, "canonical-order"):
            result.validate_document(document)

    def _paired_target_document(self) -> dict:
        document = copy.deepcopy(self.document)
        pair_id = "matched-night-clear-camera-001"
        control = document["runs"]["control"]
        control["artifacts"]["screenshots"].extend(
            [screenshot("target_visible", "control-target"),
             screenshot("title_or_gameplay", "control-boot")]
        )
        control["artifacts"]["screenshots"].sort(key=lambda row: row["role"])
        control["outcomes"] = [boot(), control["outcomes"][0], target_visible(pair_id, False)]

        expanded = document["runs"]["expanded_wall"]
        expanded["artifacts"] = {
            "config": artifact("synthetic/expanded.toml", "2" * 64, 20),
            "hdd": artifact("synthetic/expanded.qcow2", "3" * 64, 30),
            "screenshots": [
                screenshot("target_visible", "expanded-target"),
                screenshot("title_or_gameplay", "expanded-boot"),
            ],
            "xiso": artifact(
                "synthetic/expanded.xiso.iso",
                result.PROFILE["expanded_wall"]["xiso_sha256"],
                result.PROFILE["expanded_wall"]["xiso_size"],
            ),
        }
        expanded["artifacts"]["screenshots"].sort(key=lambda row: row["role"])
        expanded["observation_status"] = "observed"
        expanded["outcomes"] = [boot(), target_visible(pair_id, True)]
        expanded["reason"] = "Synthetic matched expanded target witness."
        refresh(document)
        return document

    def test_geometry_visibility_requires_matched_control_and_expanded_targets(self) -> None:
        document = self._paired_target_document()
        claims = result.validate_document(document, pins(document))
        self.assertTrue(claims["paired_target_visible"])
        self.assertTrue(claims["geometry_visibility_proved"])
        self.assertTrue(claims["xemu_boot_acceptance_proved"])
        self.assertEqual(document["status"], "target_visible")

        document["runs"]["expanded_wall"]["outcomes"][1]["observation"][
            "matched_pair_id"
        ] = "different-camera"
        refresh(document)
        claims = result.validate_document(document, pins(document))
        self.assertFalse(claims["paired_target_visible"])
        self.assertFalse(claims["geometry_visibility_proved"])

    def test_target_visible_requires_explicit_boot_outcome(self) -> None:
        document = self._paired_target_document()
        document["runs"]["expanded_wall"]["outcomes"] = [
            document["runs"]["expanded_wall"]["outcomes"][1]
        ]
        refresh(document)
        with self.assertRaisesRegex(result.ResultError, "requires explicit boot"):
            result.validate_document(document)

    def test_file_verifier_refuses_hash_size_and_symlink_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "evidence.bin"
            source.write_bytes(b"runtime evidence")
            row = artifact(
                "evidence.bin", hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size
            )
            result._verify_file(root, row, "fixture")
            wrong = dict(row, size=row["size"] + 1)
            with self.assertRaisesRegex(result.ResultError, "size differs"):
                result._verify_file(root, wrong, "fixture")
            link = root / "evidence-link.bin"
            link.symlink_to(source)
            with self.assertRaisesRegex(result.ResultError, "non-symlink"):
                result._verify_file(root, dict(row, path=link.name), "fixture")

    def test_schema_and_validator_publish_only_three_outcomes(self) -> None:
        schema = json.loads(SCHEMA.read_bytes())
        self.assertEqual(schema["$id"], result.SCHEMA_URI)
        self.assertEqual(
            schema["$defs"]["outcome"]["properties"]["kind"]["enum"],
            ["boot_acceptance", "selector_skip_negative", "target_visible"],
        )
        source = (ROOT / "tools/nfl_group36_xemu_runtime_result.py").read_text()
        self.assertNotIn("flatpak run", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("image", source.lower())


if __name__ == "__main__":
    unittest.main()
