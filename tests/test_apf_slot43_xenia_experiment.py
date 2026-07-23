#!/usr/bin/env python3
"""Synthetic tests for the retail-free APF slot-43 experiment runner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_slot43_xenia_experiment as slot43  # noqa: E402


TEAM = "10002000"
CANDIDATE = "10003000"
THREAD = "0000002A"


def _event(site: str, action: str, *, ordinal: str = "00000000") -> str:
    lr = slot43.SITE_LR[site]
    return (
        f"i> APF_SLOT43 site={site} action={action} lr={lr} "
        f"thread={THREAD} ordinal={ordinal} stock_cb_count=4 team0={TEAM} "
        f"candidate={CANDIDATE}\n"
    )


def _observe_lines() -> list[str]:
    return [
        "i> APF_SLOT43 receipt=target_matched mode=observe "
        "site=count_entry lr=84A16D34\n",
        "i> APF_SLOT43 receipt=validation_accepted mode=observe "
        f"team0={TEAM} candidate={CANDIDATE} stock_cb_count=4\n",
        _event("count_entry", "observed"),
        _event("count_exit", "observed"),
        _event("getter_entry", "observed"),
        _event("getter_found", "stock_return"),
    ]


def _modified_lines() -> list[str]:
    return [
        "i> APF_SLOT43 receipt=target_matched mode=modified "
        "site=count_entry lr=84A16D34\n",
        "i> APF_SLOT43 receipt=validation_accepted mode=modified "
        f"team0={TEAM} candidate={CANDIDATE} stock_cb_count=4\n",
        _event("count_entry", "observed"),
        _event("count_exit", "count_incremented"),
        _event("getter_entry", "observed"),
        _event("getter_miss", "candidate_returned", ordinal="00000004"),
    ]


class SyntheticFixture:
    def __init__(self, root: Path):
        self.root = root
        self.game = root / "game"
        self.game.mkdir()
        self.default_xex = self.game / "default.xex"
        self.default_xex.write_bytes(b"synthetic APF executable")
        (self.game / "0A").write_bytes(b"synthetic resource, not retail data")
        self.xenia = root / "xenia_canary"
        self.xenia.write_bytes(b"synthetic Xenia executable")
        self.xenia.chmod(0o700)
        self.xvfb = root / "xvfb-run"
        self.xvfb.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        self.xvfb.chmod(0o700)
        self.xenia_sha = hashlib.sha256(self.xenia.read_bytes()).hexdigest()
        self.xex_sha = hashlib.sha256(self.default_xex.read_bytes()).hexdigest()

    def patches(self):
        return mock.patch.multiple(
            slot43,
            XENIA_SHA256=self.xenia_sha,
            DEFAULT_XEX_SHA256=self.xex_sha,
            _find_xvfb_run=mock.DEFAULT,
        )


class APFSlot43XeniaExperimentTests(unittest.TestCase):
    def test_final_toolchain_pins_and_obsolete_pins_are_absent(self) -> None:
        self.assertEqual(
            slot43.XENIA_SHA256,
            "e8d7fda95239d12c11a1d2b336bbed33b39d1da738a65dc2e757c16b8d215641",
        )
        self.assertEqual(
            slot43.DEFAULT_XEX_SHA256,
            "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        )
        self.assertEqual(
            slot43.HOOK_COMMIT,
            "d145430737f787f522e08e7d86d3e94bdde6d6a1",
        )
        source = (ROOT / "tools/apf_slot43_xenia_experiment.py").read_text(
            encoding="utf-8"
        )
        for obsolete in (
            "b6fc6b",
            "fdfb9b",
            "1b3b39",
            "6d2e7be",
            "6f9c25",
            "6e1ef5",
            "c9e6f8",
        ):
            self.assertNotIn(obsolete, source)

    def test_command_forces_every_isolation_flag(self) -> None:
        roots = {
            "storage": Path("/private/storage"),
            "content": Path("/private/content"),
            "cache": Path("/private/cache"),
            "tmp": Path("/private path/tmp"),
        }
        observe = slot43.build_command(
            xvfb_run=Path("/usr/bin/xvfb-run"),
            env_executable=Path("/usr/bin/env"),
            xenia=Path("/private/xenia"),
            default_xex=Path("/game/default.xex"),
            roots=roots,
            xenia_log=Path("/private/logs/xenia.log"),
            mode="observe",
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
            "--apf_roster_slot43_log=true",
            "--apf_roster_slot43_override=false",
        ):
            self.assertIn(required, observe)
        self.assertEqual(observe[:3], [
            "/usr/bin/xvfb-run",
            "-a",
            "--server-args=-screen 0 1280x720x24",
        ])
        self.assertEqual(observe[3:6], [
            "/usr/bin/env",
            "TMPDIR=/private path/tmp",
            "/private/xenia",
        ])
        self.assertEqual(observe[-1], "/game/default.xex")
        modified = slot43.build_command(
            xvfb_run=Path("/usr/bin/xvfb-run"),
            env_executable=Path("/usr/bin/env"),
            xenia=Path("/private/xenia"),
            default_xex=Path("/game/default.xex"),
            roots=roots,
            xenia_log=Path("/private/logs/xenia.log"),
            mode="modified",
        )
        self.assertIn("--apf_roster_slot43_override=true", modified)
        self.assertNotIn("--apf_roster_slot43_override=false", modified)

    def test_path_with_spaces_keeps_xvfb_tmp_default_and_xenia_tmp_private(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf runner spaces ") as temporary:
            root = Path(temporary)
            run_root = root / "private run root"
            run_root.mkdir(mode=0o700)
            roots = slot43._create_isolated_roots(run_root)

            fake_xvfb = root / "synthetic xvfb-run"
            fake_xvfb.write_text(
                """#!/usr/bin/python3
import os
import sys

if sys.argv[1:3] != [\"-a\", \"--server-args=-screen 0 1280x720x24\"]:
    raise SystemExit(90)
child_environment = dict(os.environ)
child_environment[\"SYNTHETIC_XVFB_SAW_TMPDIR\"] = str(\"TMPDIR\" in os.environ)
child_environment[\"DISPLAY\"] = \":123\"
child_environment[\"XAUTHORITY\"] = \"/tmp/synthetic-xvfb/Xauthority\"
os.execvpe(sys.argv[3], sys.argv[3:], child_environment)
""",
                encoding="utf-8",
            )
            fake_xvfb.chmod(0o700)
            fake_xenia = root / "synthetic xenia"
            fake_xenia.write_text(
                """#!/usr/bin/python3
import json
import os

print(json.dumps({
    \"display\": os.environ.get(\"DISPLAY\"),
    \"tmpdir\": os.environ.get(\"TMPDIR\"),
    \"xauthority\": os.environ.get(\"XAUTHORITY\"),
    \"xvfb_saw_tmpdir\": os.environ.get(\"SYNTHETIC_XVFB_SAW_TMPDIR\"),
}))
""",
                encoding="utf-8",
            )
            fake_xenia.chmod(0o700)
            command = slot43.build_command(
                xvfb_run=fake_xvfb,
                env_executable=Path("/usr/bin/env"),
                xenia=fake_xenia,
                default_xex=root / "synthetic game" / "default.xex",
                roots=roots,
                xenia_log=roots["logs"] / "xenia.log",
                mode="observe",
            )
            environment = slot43._isolated_environment(roots)
            self.assertNotIn("TMPDIR", environment)
            launcher_log = roots["logs"] / "launcher.log"
            receipt = slot43._launch_bounded(
                command,
                cwd=run_root,
                environment=environment,
                launcher_log=launcher_log,
                timeout_seconds=5,
            )
            self.assertTrue(receipt.started)
            self.assertFalse(receipt.timed_out)
            self.assertEqual(receipt.returncode, 0)
            observed = json.loads(launcher_log.read_text(encoding="utf-8"))
            self.assertEqual(observed["xvfb_saw_tmpdir"], "False")
            self.assertEqual(observed["tmpdir"], str(roots["tmp"]))
            self.assertEqual(observed["display"], ":123")
            self.assertEqual(
                observed["xauthority"], "/tmp/synthetic-xvfb/Xauthority"
            )

    def test_modified_mode_requires_exact_confirmation(self) -> None:
        with self.assertRaisesRegex(
            slot43.Slot43ExperimentError, "exact --confirm-modified token"
        ):
            slot43.run_experiment(
                xenia_path=Path("missing"),
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                mode="modified",
                confirmation="yes",
                dry_run=True,
            )
        with self.assertRaisesRegex(
            slot43.Slot43ExperimentError, "only valid in modified mode"
        ):
            slot43.run_experiment(
                xenia_path=Path("missing"),
                game_directory=Path("missing"),
                run_root_path=Path("missing"),
                mode="observe",
                confirmation=slot43.MODIFIED_CONFIRMATION,
                dry_run=True,
            )

    def test_observe_receipts_prove_only_the_observe_path(self) -> None:
        parsed = slot43.parse_receipt_lines(_observe_lines())
        classification, reasons = slot43.classify_receipts("observe", parsed)
        self.assertEqual(classification, "observe_path_proved")
        self.assertEqual(reasons, [])
        sanitized = json.dumps(parsed.sanitized(), sort_keys=True)
        self.assertNotIn(TEAM, sanitized)
        self.assertNotIn(CANDIDATE, sanitized)

    def test_modified_receipts_require_count_and_candidate_actions(self) -> None:
        parsed = slot43.parse_receipt_lines(_modified_lines())
        classification, reasons = slot43.classify_receipts("modified", parsed)
        self.assertEqual(classification, "modified_path_proved")
        self.assertEqual(reasons, [])
        incomplete = slot43.parse_receipt_lines(_modified_lines()[:-1])
        classification, reasons = slot43.classify_receipts("modified", incomplete)
        self.assertEqual(classification, "path_not_reached")
        self.assertEqual(reasons, ["complete_modified_path_not_seen"])

    def test_events_from_different_traversals_cannot_form_a_proof(self) -> None:
        lines = _observe_lines()[:2]
        lines.extend((
            _event("count_entry", "observed"),
            _event("count_exit", "observed"),
            _event("count_entry", "observed"),
            _event("getter_entry", "observed"),
            _event("getter_found", "stock_return"),
        ))
        parsed = slot43.parse_receipt_lines(lines)
        self.assertEqual(parsed.complete_observe_traversals, 0)
        self.assertEqual(
            slot43.classify_receipts("observe", parsed),
            ("path_not_reached", ["complete_observe_path_not_seen"]),
        )

    def test_validation_rejection_and_malformed_override_fail_closed(self) -> None:
        rejected = _observe_lines()[:1] + [
            "i> APF_SLOT43 receipt=validation_rejected "
            "site=count_entry lr=84A16D34\n"
        ]
        classification, reasons = slot43.classify_receipts(
            "observe", slot43.parse_receipt_lines(rejected)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("hook_validation_rejected", reasons)

        wrong_action = _observe_lines()
        wrong_action[3] = _event("count_exit", "count_incremented")
        classification, reasons = slot43.classify_receipts(
            "observe", slot43.parse_receipt_lines(wrong_action)
        )
        self.assertEqual(classification, "validation_rejected")
        self.assertIn("observe_log_contains_override", reasons)

    def test_no_receipts_is_a_bounded_negative_result(self) -> None:
        parsed = slot43.parse_receipt_lines(["ordinary Xenia log line\n"])
        self.assertEqual(
            slot43.classify_receipts("observe", parsed),
            ("path_not_reached", ["complete_target_receipts_not_seen"]),
        )

    def test_dry_run_writes_manifest_without_launching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "dry-run"
            with (
                mock.patch.object(slot43, "XENIA_SHA256", fixture.xenia_sha),
                mock.patch.object(slot43, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(slot43, "_find_xvfb_run", return_value=fixture.xvfb),
                mock.patch.object(slot43, "_launch_bounded") as launch,
            ):
                manifest = slot43.run_experiment(
                    xenia_path=fixture.xenia,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    dry_run=True,
                    timeout_seconds=5,
                )
            launch.assert_not_called()
            written = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written, manifest)
            self.assertTrue(manifest["dry_run_integrity"]["tree_unchanged"])
            self.assertTrue(manifest["isolation"]["fresh_empty_content_root"])
            self.assertFalse(manifest["isolation"]["xvfb_tmpdir_inherited"])
            self.assertTrue(
                manifest["isolation"]["xenia_tmpdir_restored_after_xvfb_setup"]
            )
            self.assertFalse(manifest["safety"]["slot43_override"])
            self.assertFalse((run_root / "result.json").exists())

    def test_synthetic_execution_writes_sanitized_positive_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "observe-run"

            def fake_launch(command, *, cwd, environment, launcher_log, timeout_seconds):
                del cwd, environment, timeout_seconds
                launcher_log.write_text("synthetic launcher\n", encoding="utf-8")
                log_argument = next(value for value in command if value.startswith("--log_file="))
                Path(log_argument.split("=", 1)[1]).write_text(
                    "".join(_observe_lines()), encoding="utf-8"
                )
                return slot43.ExecutionReceipt(
                    True, True, -15, 12, "timeout_sigterm"
                )

            with (
                mock.patch.object(slot43, "XENIA_SHA256", fixture.xenia_sha),
                mock.patch.object(slot43, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(slot43, "_find_xvfb_run", return_value=fixture.xvfb),
                mock.patch.object(slot43, "_launch_bounded", side_effect=fake_launch),
            ):
                result = slot43.run_experiment(
                    xenia_path=fixture.xenia,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    timeout_seconds=5,
                )
            self.assertEqual(result["classification"], "observe_path_proved")
            self.assertTrue(result["integrity"]["source_tree_unchanged"])
            self.assertTrue(result["claims"]["observe_consumer_path_proved"])
            self.assertFalse(result["claims"]["true_53_man_rosters_proved"])
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(TEAM, serialized)
            self.assertNotIn(CANDIDATE, serialized)
            self.assertNotIn(str(fixture.game), serialized)
            self.assertEqual(
                json.loads((run_root / "result.json").read_text(encoding="utf-8")),
                result,
            )

    def test_source_tree_mutation_rejects_an_otherwise_valid_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticFixture(Path(temporary))
            run_root = fixture.root / "mutation-run"

            def fake_launch(command, *, cwd, environment, launcher_log, timeout_seconds):
                del cwd, environment, timeout_seconds
                (fixture.game / "0A").write_bytes(b"changed during synthetic run")
                launcher_log.write_text("synthetic launcher\n", encoding="utf-8")
                log_argument = next(value for value in command if value.startswith("--log_file="))
                Path(log_argument.split("=", 1)[1]).write_text(
                    "".join(_observe_lines()), encoding="utf-8"
                )
                return slot43.ExecutionReceipt(
                    True, True, -15, 12, "timeout_sigterm"
                )

            with (
                mock.patch.object(slot43, "XENIA_SHA256", fixture.xenia_sha),
                mock.patch.object(slot43, "DEFAULT_XEX_SHA256", fixture.xex_sha),
                mock.patch.object(slot43, "_find_xvfb_run", return_value=fixture.xvfb),
                mock.patch.object(slot43, "_launch_bounded", side_effect=fake_launch),
            ):
                result = slot43.run_experiment(
                    xenia_path=fixture.xenia,
                    game_directory=fixture.game,
                    run_root_path=run_root,
                    timeout_seconds=5,
                )
            self.assertEqual(result["classification"], "validation_rejected")
            self.assertIn("source_tree_changed", result["reason_codes"])
            self.assertFalse(result["integrity"]["source_tree_unchanged"])


if __name__ == "__main__":
    unittest.main()
