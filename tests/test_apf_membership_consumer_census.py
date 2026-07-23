#!/usr/bin/env python3
"""Synthetic tests for the retail-free APF membership census runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_membership_consumer_census as census  # noqa: E402


PC_ONE = "84A10000"
LR_ONE = "84A10004"
PC_TWO = "84B20000"
LR_TWO = "84B20004"

# Verbatim v1 hook-format fixture shared with the Xenia hook implementation.
HOOK_V1_INTEGRATION_FIXTURE = [
    "i> APF_MEMBERSHIP_CENSUS receipt=protocol version=1 observation_only=true\n",
    "i> APF_MEMBERSHIP_CENSUS receipt=epoch_invalidated epoch=8\n",
    "i> APF_MEMBERSHIP_CENSUS receipt=validation_accepted epoch=8 "
    "teams=40 memberships=1344\n",
    "i> APF_MEMBERSHIP_CENSUS receipt=access epoch=8 pc=84A10000 "
    "lr=84A10004 op=read width=1 region=count team=37 slot=0 byte=0\n",
]


def _valid_lines(*, second_consumer: bool = False) -> list[str]:
    lines = [
        "i> APF_MEMBERSHIP_CENSUS receipt=protocol version=1 "
        "observation_only=true\n",
        "i> APF_MEMBERSHIP_CENSUS receipt=epoch_invalidated epoch=8\n",
        "i> APF_MEMBERSHIP_CENSUS receipt=validation_accepted epoch=8 "
        "teams=40 memberships=1344\n",
        "i> APF_MEMBERSHIP_CENSUS receipt=access epoch=8 "
        f"pc={PC_ONE} lr={LR_ONE} op=read width=1 region=count "
        "slot=0 team=37 byte=0\n",
    ]
    if second_consumer:
        lines.append(
            "i> APF_MEMBERSHIP_CENSUS receipt=access epoch=8 "
            f"pc={PC_TWO} lr={LR_TWO} op=read width=4 region=member "
            "slot=41 team=0 byte=0\n"
        )
    return lines


class SyntheticFixture:
    def __init__(self, root: Path):
        self.root = root
        self.game = root / "game"
        self.game.mkdir()
        self.default_xex = self.game / "default.xex"
        self.default_xex.write_bytes(b"synthetic APF executable")
        (self.game / "0A").write_bytes(b"synthetic resource, never retail data")
        self.xenia = root / "xenia_canary"
        self.xenia.write_bytes(b"synthetic membership-census Xenia")
        self.xenia.chmod(0o700)
        self.xvfb = root / "xvfb-run"
        self.xvfb.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        self.xvfb.chmod(0o700)
        self.xenia_sha = hashlib.sha256(self.xenia.read_bytes()).hexdigest()
        self.xex_sha = hashlib.sha256(self.default_xex.read_bytes()).hexdigest()
        self.hook_commit = "b" * 40


def _write_document(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def _identifier_lines(
    identifiers: list[str], *, failure_reason: str | None = None
) -> list[str]:
    lines = [
        "i> APF_MEMBERSHIP_CENSUS receipt=protocol version=1 "
        "observation_only=true\n",
        "i> APF_MEMBERSHIP_CENSUS receipt=epoch_invalidated epoch=8\n",
        "i> APF_MEMBERSHIP_CENSUS receipt=validation_accepted epoch=8 "
        "teams=40 memberships=1344\n",
    ]
    for identifier in sorted(set(identifiers)):
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest().upper()
        pc = digest[:8]
        lr = digest[8:16]
        team = int(digest[16:18], 16) % 40
        slot = int(digest[18:20], 16) % 42
        byte = int(digest[20:22], 16) % 4
        lines.append(
            "i> APF_MEMBERSHIP_CENSUS receipt=access epoch=8 "
            f"pc={pc} lr={lr} op=read width=4 region=member "
            f"team={team} slot={slot} byte={byte}\n"
        )
    if failure_reason is not None:
        lines.append(
            "i> APF_MEMBERSHIP_CENSUS receipt=census_failed epoch=8 "
            f"reason={failure_reason}\n"
        )
    return lines


def _write_bundle(
    path: Path,
    scenario: str,
    pass_index: int,
    identifiers: list[str],
    *,
    failure_reason: str | None = None,
) -> Path:
    source_tree_sha256 = "c" * 64
    path.mkdir()
    logs = path / "logs"
    logs.mkdir()
    lines = _identifier_lines(identifiers, failure_reason=failure_reason)
    xenia_log = logs / "xenia.log"
    xenia_log.write_text("".join(lines), encoding="utf-8")
    parsed = census.parse_receipt_lines(lines)
    classification, reasons = census.classify_single(parsed)
    manifest = {
        "schema": census.RUN_SCHEMA,
        "scenario": scenario,
        "pass_index": pass_index,
        "dry_run": False,
        "toolchain": {
            "xenia_sha256": "a" * 64,
            "hook_commit": "b" * 40,
        },
        "source": {
            "default_xex_sha256": census.DEFAULT_XEX_SHA256,
            "tree_before": {
                "sha256": source_tree_sha256,
                "file_count": 2,
                "directory_count": 1,
                "total_bytes": 64,
            },
            "opened_read_only": True,
        },
        "command": [
            census.CENSUS_LOG_CVAR,
            "--store_all_context_values=true",
        ],
        "safety": {
            "observation_only_hook": True,
            "apply_title_update": False,
            "apply_patches": False,
            "allow_plugins": False,
            "game_files_written_by_runner": False,
        },
    }
    manifest_path = path / "manifest.json"
    _write_document(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    log_sha = hashlib.sha256(xenia_log.read_bytes()).hexdigest()
    result = {
        "schema": census.RESULT_SCHEMA,
        "mode": "single",
        "scenario": scenario,
        "pass_index": pass_index,
        "classification": classification,
        "reason_codes": reasons,
        "toolchain": {
            "xenia_sha256": "a" * 64,
            "hook_commit": "b" * 40,
            "default_xex_sha256": census.DEFAULT_XEX_SHA256,
        },
        "execution": {
            "started": True,
            "timed_out": True,
            "returncode": -15,
        },
        "integrity": {
            "source_tree_sha256_before": source_tree_sha256,
            "source_tree_sha256_after": source_tree_sha256,
            "source_tree_unchanged": True,
            "default_xex_sha256_before": census.DEFAULT_XEX_SHA256,
            "default_xex_sha256_after": census.DEFAULT_XEX_SHA256,
            "default_xex_unchanged": True,
        },
        "receipts": parsed.sanitized(),
        "artifacts": {
            "manifest": "manifest.json",
            "xenia_log": "logs/xenia.log",
            "manifest_sha256": manifest_sha,
            "xenia_log_sha256": log_sha,
        },
        "claims": {
            "retail_game_bytes_embedded_in_result": False,
            "raw_guest_locations_embedded_in_result": False,
        },
    }
    _write_document(path / "result.json", result)
    return path


def _write_ledger(
    path: Path, identifiers: list[str], *, extra_unclassified: bool = False
) -> None:
    profiles = census.parse_receipt_lines(
        _identifier_lines(identifiers)
    ).access_profiles
    candidates = [
        {
            "site_fingerprint": profile.site_fingerprint,
            "disposition": "runtime_required",
        }
        for profile in profiles
    ]
    if extra_unclassified:
        candidates.append({
            "site_fingerprint": hashlib.sha256(b"unseen-static-site").hexdigest(),
            "disposition": "unclassified",
        })
    _write_document(path, {
        "schema": census.STATIC_LEDGER_SCHEMA,
        "default_xex_sha256": census.DEFAULT_XEX_SHA256,
        "inventory_id": "membership_static_v1",
        "candidates": candidates,
    })


def _write_full_matrix(
    root: Path,
    identifiers: list[str],
    *,
    pass_indexes: tuple[int, ...] = (1, 2),
) -> list[Path]:
    paths: list[Path] = []
    for scenario in census.FULL_CENSUS_SCENARIOS:
        for pass_index in pass_indexes:
            path = root / f"{scenario}-{pass_index}"
            _write_bundle(
                path, scenario, pass_index, identifiers,
            )
            paths.append(path)
    return paths


class APFMembershipConsumerCensusTests(unittest.TestCase):
    def test_explicit_binary_and_commit_pins_fail_closed(self) -> None:
        with self.assertRaisesRegex(census.MembershipCensusError, "64 hexadecimal"):
            census.run_census(
                xenia_path=Path("missing"),
                expected_xenia_sha256="unknown",
                hook_commit="b" * 40,
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                scenario=census.HEADLESS_SCENARIO,
                dry_run=True,
            )
        with self.assertRaisesRegex(census.MembershipCensusError, "all-zero"):
            census.run_census(
                xenia_path=Path("missing"),
                expected_xenia_sha256="0" * 64,
                hook_commit="b" * 40,
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                scenario=census.HEADLESS_SCENARIO,
                dry_run=True,
            )
        with self.assertRaisesRegex(census.MembershipCensusError, "40-character"):
            census.run_census(
                xenia_path=Path("missing"),
                expected_xenia_sha256="a" * 64,
                hook_commit="pending",
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                scenario=census.HEADLESS_SCENARIO,
                dry_run=True,
            )

    def test_live_run_refuses_a_toolchain_outside_the_reviewed_pins(self) -> None:
        self.assertEqual(
            census.REVIEWED_XENIA_SHA256,
            "712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d",
        )
        self.assertEqual(
            census.REVIEWED_HOOK_COMMIT,
            "d09cae8d8374324048ef603d48a9c1696b39d552",
        )
        with self.assertRaisesRegex(
            census.MembershipCensusError,
            "requested toolchain does not match the installed reviewed pins",
        ):
            census.run_census(
                xenia_path=Path("missing"),
                expected_xenia_sha256="a" * 64,
                hook_commit="b" * 40,
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                scenario=census.HEADLESS_SCENARIO,
            )

    def test_command_forces_headless_isolation_and_observation_only_hook(self) -> None:
        roots = {
            "storage": Path("/private/storage"),
            "content": Path("/private/content"),
            "cache": Path("/private/cache"),
            "tmp": Path("/private path/tmp"),
        }
        command = census.build_command(
            xvfb_run=Path("/usr/bin/xvfb-run"),
            env_executable=Path("/usr/bin/env"),
            xenia=Path("/private/xenia"),
            default_xex=Path("/game/default.xex"),
            roots=roots,
            xenia_log=Path("/private/logs/xenia.log"),
        )
        for required in (
            "--gpu=null",
            "--apu=nop",
            "--hid=nop",
            "--apply_title_update=false",
            "--apply_patches=false",
            "--allow_plugins=false",
            "--discord=false",
            "--storage_root=/private/storage",
            "--content_root=/private/content",
            "--cache_root=/private/cache",
            "--log_file=/private/logs/xenia.log",
            "--store_all_context_values=true",
            "--apf_roster_membership_census_log=true",
        ):
            self.assertIn(required, command)
        self.assertEqual(command[3:6], [
            "/usr/bin/env",
            "TMPDIR=/private path/tmp",
            "/private/xenia",
        ])
        self.assertFalse(any("override" in argument for argument in command))
        self.assertEqual(command[-1], "/game/default.xex")

    def test_headless_runner_refuses_unproved_operator_scenario_labels(self) -> None:
        with self.assertRaisesRegex(census.MembershipCensusError, "supports only"):
            census.run_census(
                xenia_path=Path("missing"),
                expected_xenia_sha256="a" * 64,
                hook_commit="b" * 40,
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                scenario="gameplay",
                dry_run=True,
            )

    def test_parser_produces_only_sanitized_consumer_fingerprints(self) -> None:
        parsed = census.parse_receipt_lines(_valid_lines(second_consumer=True))
        classification, reasons = census.classify_single(parsed)
        self.assertEqual(classification, "scenario_census_complete")
        self.assertEqual(reasons, [])
        self.assertEqual(parsed.access_event_count, 2)
        self.assertEqual(len(parsed.fingerprints), 2)
        serialized = json.dumps(parsed.sanitized(), sort_keys=True)
        for raw in (PC_ONE, LR_ONE, PC_TWO, LR_TWO):
            self.assertNotIn(raw, serialized)
        for fingerprint in parsed.fingerprints:
            self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

    def test_verbatim_hook_v1_integration_fixture(self) -> None:
        parsed = census.parse_receipt_lines(HOOK_V1_INTEGRATION_FIXTURE)
        self.assertEqual(
            census.classify_single(parsed),
            ("scenario_census_complete", []),
        )
        self.assertEqual(parsed.protocol_receipt_count, 1)
        self.assertEqual(parsed.validation_accepted, 1)
        self.assertEqual(parsed.access_event_count, 1)

    def test_full_interval_context_affects_consumer_key_but_not_site_key(self) -> None:
        lines = _valid_lines()
        second = lines[-1].replace("team=37", "team=38")
        parsed = census.parse_receipt_lines(lines + [second])
        self.assertEqual(len(parsed.access_profiles), 2)
        self.assertNotEqual(
            parsed.access_profiles[0].fingerprint,
            parsed.access_profiles[1].fingerprint,
        )
        self.assertEqual(
            parsed.access_profiles[0].site_fingerprint,
            parsed.access_profiles[1].site_fingerprint,
        )

    def test_protocol_receipt_is_required_before_bounded_negative(self) -> None:
        empty = census.parse_receipt_lines(["ordinary Xenia line\n"])
        self.assertEqual(
            census.classify_single(empty),
            ("validation_rejected", ["hook_protocol_receipt_missing_or_invalid"]),
        )
        partial = census.parse_receipt_lines([
            "APF_MEMBERSHIP_CENSUS receipt=protocol version=1 "
            "observation_only=true\n",
        ])
        self.assertEqual(
            census.classify_single(partial),
            ("path_not_reached", ["validated_epoch_not_seen"]),
        )
        accepted = census.parse_receipt_lines([
            "APF_MEMBERSHIP_CENSUS receipt=protocol version=1 "
            "observation_only=true\n",
            "APF_MEMBERSHIP_CENSUS receipt=epoch_invalidated epoch=1\n",
            "APF_MEMBERSHIP_CENSUS receipt=validation_accepted epoch=1 "
            "teams=40 memberships=1344\n"
        ])
        self.assertEqual(
            census.classify_single(accepted),
            ("partial_coverage", ["validated_access_not_seen"]),
        )

    def test_validation_rejection_and_protocol_drift_fail_closed(self) -> None:
        rejected = census.parse_receipt_lines([
            "APF_MEMBERSHIP_CENSUS receipt=protocol version=1 "
            "observation_only=true\n",
            "APF_MEMBERSHIP_CENSUS receipt=validation_rejected epoch=1 "
            "reason=root_bad\n"
        ])
        classification, reasons = census.classify_single(rejected)
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("hook_validation_rejected", reasons)

        drift = _valid_lines() + [
            "APF_MEMBERSHIP_CENSUS receipt=census_converged count=1\n"
        ]
        classification, reasons = census.classify_single(
            census.parse_receipt_lines(drift)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("malformed_receipt", reasons)

        stray_token = list(_valid_lines())
        stray_token[-1] = stray_token[-1].rstrip() + " stray-token\n"
        classification, reasons = census.classify_single(
            census.parse_receipt_lines(stray_token)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("malformed_receipt", reasons)

    def test_epoch_mismatch_fails_closed(self) -> None:
        lines = _valid_lines()
        lines[-1] = lines[-1].replace("epoch=8", "epoch=9")
        parsed = census.parse_receipt_lines(lines)
        classification, reasons = census.classify_single(parsed)
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("invalid_epoch_lifecycle", reasons)
        self.assertEqual(parsed.access_event_count, 0)

    def test_invalidation_and_acceptance_epoch_must_match(self) -> None:
        lines = _valid_lines()
        lines[1] = lines[1].replace("epoch=8", "epoch=7")
        parsed = census.parse_receipt_lines(lines)
        classification, reasons = census.classify_single(parsed)
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("invalid_epoch_lifecycle", reasons)
        self.assertEqual(parsed.access_event_count, 0)

    def test_hook_capacity_failure_is_trace_overflow(self) -> None:
        lines = _valid_lines() + [
            "APF_MEMBERSHIP_CENSUS receipt=census_failed epoch=8 "
            "reason=event_limit\n"
        ]
        classification, reasons = census.classify_single(
            census.parse_receipt_lines(lines)
        )
        self.assertEqual(classification, "trace_overflow")
        self.assertIn("hook_reported_event_limit", reasons)

    def test_arithmetic_overflow_is_validation_failure_not_trace_capacity(self) -> None:
        lines = _valid_lines() + [
            "APF_MEMBERSHIP_CENSUS receipt=census_failed epoch=8 "
            "reason=overflow\n"
        ]
        classification, reasons = census.classify_single(
            census.parse_receipt_lines(lines)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("hook_census_failed", reasons)

    def test_partial_vector_widths_one_through_sixteen_are_valid(self) -> None:
        accepted_widths = []
        for width in range(1, 17):
            with self.subTest(width=width):
                lines = _valid_lines()
                lines[-1] = lines[-1].replace("width=1", f"width={width}")
                parsed = census.parse_receipt_lines(lines)
                self.assertEqual(
                    census.classify_single(parsed),
                    ("scenario_census_complete", []),
                )
                self.assertEqual(parsed.access_profiles[0].width, width)
                accepted_widths.append(width)
        self.assertIn(3, accepted_widths)

    def test_width_17_is_rejected(self) -> None:
        lines = _valid_lines()
        lines[-1] = lines[-1].replace("width=1", "width=17")
        parsed = census.parse_receipt_lines(lines)
        self.assertEqual(
            census.classify_single(parsed),
            ("validation_rejected", ["malformed_receipt"]),
        )
        self.assertEqual(parsed.access_event_count, 0)

    def test_memset_widths_32_and_128_are_valid_intervals(self) -> None:
        for width in (32, 128):
            with self.subTest(width=width):
                lines = _valid_lines()
                lines[-1] = lines[-1].replace("op=read", "op=write").replace(
                    "width=1", f"width={width}"
                ).replace(
                    "byte=0", f"byte={width - 1}"
                )
                parsed = census.parse_receipt_lines(lines)
                self.assertEqual(
                    census.classify_single(parsed),
                    ("scenario_census_complete", []),
                )
                self.assertEqual(parsed.access_profiles[0].width, width)

    def test_member_and_count_lane_bounds_fail_closed(self) -> None:
        cases = (
            ("region=count", "region=member"),
            ("slot=0", "slot=1"),
            ("byte=0", "byte=128"),
        )
        for replacement in cases:
            with self.subTest(replacement=replacement):
                lines = [line.replace(*replacement) for line in _valid_lines()]
                if replacement[0] == "region=count":
                    lines[-1] = lines[-1].replace("byte=0", "byte=4")
                classification, reasons = census.classify_single(
                    census.parse_receipt_lines(lines)
                )
                self.assertEqual(classification, "validation_rejected")
                self.assertIn("malformed_receipt", reasons)

    def test_count_byte_is_the_lane_within_the_original_access(self) -> None:
        lines = _valid_lines()
        lines[-1] = lines[-1].replace("width=1", "width=4").replace(
            "byte=0", "byte=1"
        )
        parsed = census.parse_receipt_lines(lines)
        self.assertEqual(
            census.classify_single(parsed),
            ("scenario_census_complete", []),
        )
        baseline = census.parse_receipt_lines(_valid_lines())
        self.assertNotEqual(
            parsed.access_profiles[0].fingerprint,
            baseline.access_profiles[0].fingerprint,
        )

        outside = list(lines)
        outside[-1] = outside[-1].replace("byte=1", "byte=4")
        classification, reasons = census.classify_single(
            census.parse_receipt_lines(outside)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("malformed_receipt", reasons)

    def test_wide_reads_zero_pc_and_epoch_zero_fail_closed(self) -> None:
        for replacement in (
            ("width=1", "width=32"),
            ("width=1", "width=128"),
            (f"pc={PC_ONE}", "pc=00000000"),
            ("epoch=8", "epoch=0"),
        ):
            with self.subTest(replacement=replacement):
                lines = [line.replace(*replacement) for line in _valid_lines()]
                classification, reasons = census.classify_single(
                    census.parse_receipt_lines(lines)
                )
                self.assertEqual(classification, "validation_rejected")
                self.assertIn("malformed_receipt", reasons)

    def test_dry_run_writes_manifest_without_launching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "dry-run"
            with (
                mock.patch.object(census, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(
                    census, "REVIEWED_XENIA_SHA256", fixture.xenia_sha
                ),
                mock.patch.object(
                    census, "REVIEWED_HOOK_COMMIT", fixture.hook_commit
                ),
                mock.patch.object(
                    census.safety, "_find_xvfb_run", return_value=fixture.xvfb
                ),
                mock.patch.object(census.safety, "_launch_bounded") as launch,
            ):
                manifest = census.run_census(
                    xenia_path=fixture.xenia,
                    expected_xenia_sha256=fixture.xenia_sha,
                    hook_commit=fixture.hook_commit,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    scenario=census.HEADLESS_SCENARIO,
                    pass_index=2,
                    timeout_seconds=5,
                    dry_run=True,
                )
            launch.assert_not_called()
            self.assertEqual(manifest["pass_index"], 2)
            self.assertTrue(manifest["dry_run_integrity"]["tree_unchanged"])
            self.assertFalse(manifest["isolation"]["xvfb_tmpdir_inherited"])
            self.assertTrue(
                manifest["isolation"]["xenia_tmpdir_restored_after_xvfb_setup"]
            )
            self.assertTrue(manifest["safety"]["observation_only_hook"])
            self.assertFalse((run_root / "result.json").exists())

    def test_synthetic_execution_writes_retail_free_positive_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "run"

            def fake_launch(command, *, cwd, environment, launcher_log,
                            timeout_seconds):
                del cwd, environment, timeout_seconds
                launcher_log.write_text("synthetic launcher\n", encoding="utf-8")
                log_argument = next(
                    value for value in command if value.startswith("--log_file=")
                )
                Path(log_argument.split("=", 1)[1]).write_text(
                    "".join(_valid_lines(second_consumer=True)), encoding="utf-8"
                )
                return census.safety.ExecutionReceipt(
                    True, True, -15, 12, "timeout_sigterm"
                )

            with (
                mock.patch.object(census, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(
                    census, "REVIEWED_XENIA_SHA256", fixture.xenia_sha
                ),
                mock.patch.object(
                    census, "REVIEWED_HOOK_COMMIT", fixture.hook_commit
                ),
                mock.patch.object(
                    census.safety, "_find_xvfb_run", return_value=fixture.xvfb
                ),
                mock.patch.object(
                    census.safety, "_launch_bounded", side_effect=fake_launch
                ),
            ):
                result = census.run_census(
                    xenia_path=fixture.xenia,
                    expected_xenia_sha256=fixture.xenia_sha,
                    hook_commit=fixture.hook_commit,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    scenario=census.HEADLESS_SCENARIO,
                    timeout_seconds=5,
                )
            self.assertEqual(result["classification"], "scenario_census_complete")
            self.assertTrue(result["integrity"]["source_tree_unchanged"])
            self.assertFalse(result["claims"]["global_census_converged"])
            serialized = json.dumps(result, sort_keys=True)
            for raw in (
                PC_ONE, LR_ONE, PC_TWO, LR_TWO, str(fixture.game), str(fixture.xenia)
            ):
                self.assertNotIn(raw, serialized)
            self.assertEqual(
                json.loads((run_root / "result.json").read_text(encoding="utf-8")),
                result,
            )

    def test_source_mutation_rejects_otherwise_valid_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "mutation-run"

            def fake_launch(command, *, cwd, environment, launcher_log,
                            timeout_seconds):
                del cwd, environment, timeout_seconds
                (fixture.game / "0A").write_bytes(b"synthetic mutation")
                launcher_log.write_text("synthetic launcher\n", encoding="utf-8")
                log_argument = next(
                    value for value in command if value.startswith("--log_file=")
                )
                Path(log_argument.split("=", 1)[1]).write_text(
                    "".join(_valid_lines()), encoding="utf-8"
                )
                return census.safety.ExecutionReceipt(
                    True, True, -15, 12, "timeout_sigterm"
                )

            with (
                mock.patch.object(census, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(
                    census, "REVIEWED_XENIA_SHA256", fixture.xenia_sha
                ),
                mock.patch.object(
                    census, "REVIEWED_HOOK_COMMIT", fixture.hook_commit
                ),
                mock.patch.object(
                    census.safety, "_find_xvfb_run", return_value=fixture.xvfb
                ),
                mock.patch.object(
                    census.safety, "_launch_bounded", side_effect=fake_launch
                ),
            ):
                result = census.run_census(
                    xenia_path=fixture.xenia,
                    expected_xenia_sha256=fixture.xenia_sha,
                    hook_commit=fixture.hook_commit,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    scenario=census.HEADLESS_SCENARIO,
                    timeout_seconds=5,
                )
            self.assertEqual(result["classification"], "validation_rejected")
            self.assertIn("source_tree_changed", result["reason_codes"])

    def test_aggregate_declares_convergence_only_for_stable_required_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fp_a = hashlib.sha256(b"consumer-a").hexdigest()
            fp_b = hashlib.sha256(b"consumer-b").hexdigest()
            inputs = _write_full_matrix(root, [fp_a, fp_b])
            output = root / "aggregate.json"
            ledger = root / "ledger.json"
            _write_ledger(ledger, [fp_a, fp_b])
            _, ledger_sha = census._load_static_ledger(ledger)
            with (
                mock.patch.object(census, "REVIEWED_XENIA_SHA256", "a" * 64),
                mock.patch.object(census, "REVIEWED_HOOK_COMMIT", "b" * 40),
                mock.patch.object(
                    census, "REVIEWED_STATIC_LEDGER_SHA256", ledger_sha
                ),
            ):
                result = census.aggregate_census_results(
                    input_paths=inputs,
                    required_scenarios=census.FULL_CENSUS_SCENARIOS,
                    convergence_passes=2,
                    static_ledger_path=ledger,
                    output_path=output,
                )
            self.assertEqual(result["classification"], "census_converged")
            self.assertTrue(result["claims"]["global_census_converged"])
            self.assertEqual(result["coverage"]["unique_consumer_count"], 2)
            self.assertTrue(result["coverage"]["runtime_trace_stable"])
            self.assertEqual(result["coverage"]["complete_matrix_cycle_count"], 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)

    def test_stable_runtime_trace_without_static_ledger_is_not_global_convergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = hashlib.sha256(b"consumer-a").hexdigest()
            paths = _write_full_matrix(root, [fingerprint])
            with (
                mock.patch.object(census, "REVIEWED_XENIA_SHA256", "a" * 64),
                mock.patch.object(census, "REVIEWED_HOOK_COMMIT", "b" * 40),
            ):
                result = census.aggregate_census_results(
                    input_paths=paths,
                    required_scenarios=census.FULL_CENSUS_SCENARIOS,
                )
            self.assertEqual(result["classification"], "partial_coverage")
            self.assertTrue(result["claims"]["runtime_trace_stable"])
            self.assertIn("static_candidate_ledger_required", result["reason_codes"])

    def test_unaccounted_static_candidate_blocks_global_convergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = hashlib.sha256(b"consumer-a").hexdigest()
            paths = _write_full_matrix(root, [fingerprint])
            ledger = root / "ledger.json"
            _write_ledger(ledger, [fingerprint], extra_unclassified=True)
            _, ledger_sha = census._load_static_ledger(ledger)
            with (
                mock.patch.object(census, "REVIEWED_XENIA_SHA256", "a" * 64),
                mock.patch.object(census, "REVIEWED_HOOK_COMMIT", "b" * 40),
                mock.patch.object(
                    census, "REVIEWED_STATIC_LEDGER_SHA256", ledger_sha
                ),
            ):
                result = census.aggregate_census_results(
                    input_paths=paths,
                    required_scenarios=census.FULL_CENSUS_SCENARIOS,
                    static_ledger_path=ledger,
                )
            self.assertEqual(result["classification"], "partial_coverage")
            self.assertIn(
                "static_candidate_coverage_incomplete", result["reason_codes"]
            )
            self.assertEqual(
                result["coverage"]["static_ledger"]["unaccounted_candidate_count"],
                1,
            )

    def test_unreviewed_static_ledger_cannot_unlock_global_convergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = hashlib.sha256(b"consumer-a").hexdigest()
            paths = _write_full_matrix(root, [fingerprint])
            ledger = root / "ledger.json"
            _write_ledger(ledger, [fingerprint])
            with (
                mock.patch.object(census, "REVIEWED_XENIA_SHA256", "a" * 64),
                mock.patch.object(census, "REVIEWED_HOOK_COMMIT", "b" * 40),
            ):
                result = census.aggregate_census_results(
                    input_paths=paths,
                    required_scenarios=census.FULL_CENSUS_SCENARIOS,
                    static_ledger_path=ledger,
                )
            self.assertEqual(result["classification"], "partial_coverage")
            self.assertIn(
                "reviewed_static_ledger_pin_required", result["reason_codes"]
            )
            self.assertFalse(
                result["claims"]["reviewed_static_ledger_pin_matched"]
            )

    def test_convergence_requires_aligned_complete_matrix_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = hashlib.sha256(b"consumer-a").hexdigest()
            paths = []
            for scenario, indexes in (("boot", (1, 2)), ("gameplay", (3, 4))):
                for pass_index in indexes:
                    path = root / f"{scenario}-{pass_index}"
                    _write_bundle(
                        path, scenario, pass_index, [fingerprint],
                    )
                    paths.append(path)
            result = census.aggregate_census_results(
                input_paths=paths,
                required_scenarios=["boot", "gameplay"],
            )
            self.assertEqual(result["classification"], "partial_coverage")
            self.assertIn(
                "insufficient_complete_matrix_cycles", result["reason_codes"]
            )

    def test_aggregate_reports_changing_or_missing_coverage_without_convergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fp_a = hashlib.sha256(b"consumer-a").hexdigest()
            fp_b = hashlib.sha256(b"consumer-b").hexdigest()
            first = _write_bundle(root / "first", "gameplay", 1, [fp_a])
            second = _write_bundle(
                root / "second", "gameplay", 2, [fp_a, fp_b]
            )
            changing = census.aggregate_census_results(
                input_paths=[first, second],
                required_scenarios=["gameplay"],
            )
            self.assertEqual(changing["classification"], "partial_coverage")
            self.assertIn(
                "complete_matrix_consumer_set_still_changing",
                changing["reason_codes"],
            )
            missing = census.aggregate_census_results(
                input_paths=[first, second],
                required_scenarios=["gameplay", "roster_management"],
            )
            self.assertEqual(missing["classification"], "partial_coverage")
            self.assertIn("required_scenario_missing", missing["reason_codes"])

    def test_aggregate_propagates_trace_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fingerprint = hashlib.sha256(b"consumer").hexdigest()
            first = _write_bundle(
                root / "first", "gameplay", 1, [fingerprint]
            )
            second = _write_bundle(
                root / "second",
                "gameplay",
                2,
                [fingerprint],
                failure_reason="event_limit",
            )
            result = census.aggregate_census_results(
                input_paths=[first, second],
                required_scenarios=["gameplay"],
            )
            self.assertEqual(result["classification"], "trace_overflow")
            self.assertFalse(result["claims"]["global_census_converged"])

    def test_aggregate_reparses_raw_log_instead_of_trusting_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = _write_bundle(root / "run", "gameplay", 1, ["consumer-a"])
            log_path = bundle / "logs" / "xenia.log"
            extra_access = _identifier_lines(["consumer-b"])[-1]
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(extra_access)
            result_path = bundle / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["artifacts"]["xenia_log_sha256"] = hashlib.sha256(
                log_path.read_bytes()
            ).hexdigest()
            _write_document(result_path, result)
            with self.assertRaisesRegex(
                census.MembershipCensusError,
                "raw hook log does not reproduce result receipts",
            ):
                census.aggregate_census_results(
                    input_paths=[bundle],
                    required_scenarios=["gameplay"],
                )

    def test_aggregate_cross_checks_result_before_and_after_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = _write_bundle(root / "run", "gameplay", 1, ["consumer"])
            result_path = bundle / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["integrity"]["source_tree_sha256_after"] = "d" * 64
            _write_document(result_path, result)
            with self.assertRaisesRegex(
                census.MembershipCensusError,
                "source-tree before/after hashes differ",
            ):
                census.aggregate_census_results(
                    input_paths=[bundle],
                    required_scenarios=["gameplay"],
                )

    def test_aggregate_cross_checks_manifest_and_result_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = _write_bundle(root / "run", "gameplay", 1, ["consumer"])
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source"]["tree_before"]["sha256"] = "d" * 64
            _write_document(manifest_path, manifest)

            result_path = bundle / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["artifacts"]["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            _write_document(result_path, result)
            with self.assertRaisesRegex(
                census.MembershipCensusError,
                "manifest source-tree hash does not match result",
            ):
                census.aggregate_census_results(
                    input_paths=[bundle],
                    required_scenarios=["gameplay"],
                )


if __name__ == "__main__":
    unittest.main()
