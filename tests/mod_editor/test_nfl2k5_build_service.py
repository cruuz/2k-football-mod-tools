"""Product-boundary tests for the Phase 1 atomic NFL 2K5 builder."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mod_editor.core import platform_compat
from mod_editor.core.errors import OutputRefusedError, ValidationError
from mod_editor.core.model import SourceRecord
from mod_editor.core.nfl2k5_build_service import (
    AUDIO_SOURCE_CONTAINMENT_RELATIVE,
    AUDIO_SOURCE_FINGERPRINTS_RELATIVE,
    BUILD_SPACE_MARGIN,
    MAX_AUDIO_SOURCE_CONTAINMENT_BYTES,
    MAX_AUDIO_SOURCE_FINGERPRINTS_BYTES,
    BuildStage,
    CommandResult,
    Nfl2k5BuildError,
    Nfl2k5BuildService,
)
from mod_editor.core.nfl2k5_source_cache import (
    INVENTORY_SIZE,
    PACK0_SIZE,
    SOURCE_SHA256,
    SOURCE_SIZE,
    SourceCache,
)


def _sparse(path: Path, size: int, prefix: bytes = b"") -> None:
    with path.open("wb") as stream:
        if prefix:
            stream.write(prefix)
        stream.truncate(size)


def _canonical_project(path: Path, kind: str = "synthetic-test-edit") -> None:
    value = {
        "edits": [{"kind": kind}],
        "purpose": "Synthetic build-service test",
        "schema": "nfl2k5_visual_mod_project/v1",
    }
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class FakeBackendRunner:
    def __init__(self, mode: str = "success", collision: Path | None = None) -> None:
        self.mode = mode
        self.collision = collision
        self.calls: list[tuple[str, ...]] = []

    @staticmethod
    def _argument(argv: tuple[str, ...], name: str) -> Path:
        return Path(argv[argv.index(name) + 1])

    def run(self, argv, cwd: Path) -> CommandResult:
        fixed = tuple(str(value) for value in argv)
        self.calls.append(fixed)
        action = fixed[2]
        output = self._argument(fixed, "--output-xiso")
        manifest = self._argument(fixed, "--manifest")
        artifact_dir = self._argument(fixed, "--artifact-dir")
        source = self._argument(fixed, "--source-xiso")
        project = self._argument(fixed, "--project")
        if action == "build":
            if self.mode == "build_failure":
                output.write_bytes(b"partial and unverified")
                return CommandResult(fixed, 1, "", "error: replacement PNG is wrong\n")
            if self.mode == "crib_too_noisy":
                return CommandResult(
                    fixed, 1, "",
                    "error: This Crib screen image has too much fine noise or "
                    "dithering for the fixed game slot. Simplify those areas "
                    "and try again.\n",
                )
            if self.mode == "crib_too_flat":
                return CommandResult(
                    fixed, 1, "",
                    "error: This Crib screen image is too flat for the safe game "
                    "slot. Add a small amount of repeated visual detail and try "
                    "again.\n",
                )
            _sparse(output, SOURCE_SIZE, b"verified-synthetic-output")
            artifact_dir.mkdir()
            (artifact_dir / "derived.bin").write_bytes(b"private derived artifact")
            info = output.stat()
            receipt = {
                "schema": "nfl2k5_visual_mod_build/v1",
                "project": {"edit_count": 1, "path": str(project)},
                "source": {
                    "path": str(source),
                    "sha256_before": SOURCE_SHA256,
                    "sha256_after": SOURCE_SHA256,
                    "opened_read_only": True,
                    "modified": False,
                },
                "output": {
                    "xiso_path": str(output.resolve()),
                    "xiso_size": SOURCE_SIZE,
                    "xiso_sha256": "a" * 64,
                    "device": info.st_dev,
                    "inode": info.st_ino,
                },
                "patch": {"changed_byte_count": 1234},
            }
            manifest.write_text(json.dumps(receipt), encoding="utf-8")
            return CommandResult(fixed, 0, "BUILD PASS\n", "")
        if action != "verify":
            raise AssertionError(f"unexpected backend action: {action}")
        if self.mode == "verify_failure":
            return CommandResult(fixed, 1, "", "error: changed bytes escaped spans\n")
        if self.mode == "interrupt":
            raise KeyboardInterrupt
        if self.mode == "missing_pass_line":
            return CommandResult(fixed, 0, "not actually verified\n", "")
        if self.mode == "collision":
            assert self.collision is not None
            self.collision.write_bytes(b"another process owns this file")
        return CommandResult(
            fixed,
            0,
            "NFL2K5_VISUAL_MOD_VERIFY_PASS edits=1 changed=1234 "
            f"sha256={'a' * 64} runtime=false\n",
            "",
        )


class SyntheticFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.source = root / "retail.xiso.iso"
        _sparse(self.source, SOURCE_SIZE, b"source-must-stay-read-only")
        self.pack0 = root / "0"
        self.inventory = root / "inventory.json"
        _sparse(self.pack0, PACK0_SIZE)
        _sparse(self.inventory, INVENTORY_SIZE)
        self.originals = root / "originals"
        self.originals.mkdir()
        record = SourceRecord(
            selected_path=str(self.source.resolve()),
            inspected_path=str(self.source.resolve()),
            kind="xiso",
            sha256=SOURCE_SHA256,
            size=SOURCE_SIZE,
            recognized=True,
            fingerprint_id="nfl2k5-usa-retail-xiso",
            detected_game="nfl2k5",
            note="Synthetic cache fixture",
        )
        self.cache = SourceCache(
            source=record,
            root=root,
            pack0=self.pack0,
            inventory=self.inventory,
            originals=self.originals,
            resource_count=1,
            outer_entry_count=1,
            kind_counts={"TSET": 1},
        )
        self.project = root / "project.json"
        _canonical_project(self.project)
        self.output = root / "My Modded 2K5.xiso.iso"

    def stage_paths(self) -> list[Path]:
        return list(self.root.glob(f".{self.output.name}.2k5mod-*"))

    def set_project_kind(self, kind: str) -> None:
        _canonical_project(self.project, kind)

    def create_audio_safety_files(self) -> tuple[Path, Path]:
        derived = self.root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE.parent
        derived.mkdir(mode=0o700)
        derived.chmod(0o700)
        fingerprints = self.root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE
        containment = self.root / AUDIO_SOURCE_CONTAINMENT_RELATIVE
        fingerprints.write_bytes(b'{"private":"fingerprints"}\n')
        containment.write_bytes(b'{"private":"containment"}\n')
        fingerprints.chmod(0o600)
        containment.chmod(0o600)
        return fingerprints, containment


class Nfl2k5BuildServiceTests(unittest.TestCase):
    def test_low_space_is_refused_before_staging_or_backend_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            runner = FakeBackendRunner()
            required = SOURCE_SIZE + BUILD_SPACE_MARGIN
            with patch(
                "mod_editor.core.nfl2k5_build_service.shutil.disk_usage",
                return_value=SimpleNamespace(free=0),
            ), self.assertRaisesRegex(
                Nfl2k5BuildError,
                r"enough free space.*choose a different drive.*No output was created",
            ):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertFalse(runner.calls)
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.stage_paths())

            with patch(
                "mod_editor.core.nfl2k5_build_service.shutil.disk_usage",
                return_value=SimpleNamespace(free=required - 1025),
            ), self.assertRaisesRegex(
                Nfl2k5BuildError,
                r"Free another 1\.01 KiB or choose a different drive",
            ):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertFalse(runner.calls)
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.stage_paths())

            with patch(
                "mod_editor.core.nfl2k5_build_service.shutil.disk_usage",
                return_value=SimpleNamespace(free=required - 1),
            ), self.assertRaisesRegex(
                Nfl2k5BuildError,
                r"Free another 1 byte or choose a different drive",
            ):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertFalse(runner.calls)
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.stage_paths())

    def test_success_runs_build_and_one_verify_then_publishes_only_iso(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            source_before = fixture.source.stat()
            with fixture.source.open("rb") as stream:
                source_prefix = stream.read(64)
            runner = FakeBackendRunner()
            events = []

            result = Nfl2k5BuildService(runner=runner).build(
                fixture.cache, fixture.project, fixture.output, events.append
            )

            self.assertEqual([call[2] for call in runner.calls], ["build", "verify"])
            for call in runner.calls:
                self.assertNotIn("--source-cache-root", call)
                self.assertNotIn("--audio-exact-inventory", call)
                self.assertNotIn("--audio-containment-inventory", call)
            self.assertEqual(result.output_xiso, fixture.output.resolve())
            self.assertEqual(result.output_size, SOURCE_SIZE)
            self.assertEqual(result.output_sha256, "a" * 64)
            self.assertEqual(result.edit_count, 1)
            self.assertEqual(result.changed_byte_count, 1234)
            self.assertTrue(result.independently_verified)
            self.assertTrue(fixture.output.is_file())
            self.assertEqual(fixture.output.stat().st_size, SOURCE_SIZE)
            self.assertFalse(fixture.stage_paths())
            self.assertFalse((fixture.root / "build-manifest.json").exists())
            self.assertFalse((fixture.root / "build-artifacts").exists())
            self.assertEqual(
                [event.stage for event in events],
                [
                    BuildStage.PREPARING,
                    BuildStage.BUILDING,
                    BuildStage.VERIFYING,
                    BuildStage.PUBLISHING,
                    BuildStage.COMPLETE,
                ],
            )
            source_after = fixture.source.stat()
            self.assertEqual(
                (source_after.st_dev, source_after.st_ino, source_after.st_size,
                 source_after.st_mtime_ns),
                (source_before.st_dev, source_before.st_ino, source_before.st_size,
                 source_before.st_mtime_ns),
            )
            with fixture.source.open("rb") as stream:
                self.assertEqual(stream.read(64), source_prefix)

    def test_each_audio_kind_passes_exact_private_inputs_to_build_and_verify(self) -> None:
        for kind in ("menu_back_audio", "audo_audio", "ausb_audio"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                fixture.set_project_kind(kind)
                fingerprints, containment = fixture.create_audio_safety_files()
                runner = FakeBackendRunner()

                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )

                self.assertEqual(
                    [call[2] for call in runner.calls], ["build", "verify"]
                )
                for call in runner.calls:
                    self.assertEqual(
                        FakeBackendRunner._argument(call, "--source-cache-root"),
                        fixture.root.resolve(),
                    )
                    self.assertEqual(
                        FakeBackendRunner._argument(
                            call, "--audio-exact-inventory"
                        ),
                        fingerprints,
                    )
                    self.assertEqual(
                        FakeBackendRunner._argument(
                            call, "--audio-containment-inventory"
                        ),
                        containment,
                    )

    def test_external_project_is_one_private_snapshot_for_both_backend_passes(self) -> None:
        class ProjectSwapRunner(FakeBackendRunner):
            def __init__(self, fixture: SyntheticFixture, original: bytes) -> None:
                super().__init__()
                self.fixture = fixture
                self.original = original
                self.staged_payloads: list[bytes] = []

            def run(self, argv, cwd: Path) -> CommandResult:
                fixed = tuple(str(value) for value in argv)
                staged = self._argument(fixed, "--project")
                self.assert_private_snapshot(staged)
                self.staged_payloads.append(staged.read_bytes())
                if not self.calls:
                    _canonical_project(self.fixture.project, "audo_audio")
                if staged.read_bytes() != self.original:
                    raise AssertionError("private project snapshot changed")
                return super().run(argv, cwd)

            def assert_private_snapshot(self, staged: Path) -> None:
                if staged == self.fixture.project.resolve():
                    raise AssertionError("backend received the caller-owned project path")
                if staged.parent == self.fixture.project.parent:
                    raise AssertionError("backend project was not in private build staging")
                # Owner-only is 0o600 on POSIX and is asserted unchanged there.
                # Windows implements no group/other bits, so the same private
                # staging copy reports 0o666 and its confidentiality comes from
                # the per-user profile root's inherited ACL instead.
                expected_mode = 0o666 if platform_compat.IS_WINDOWS else 0o600
                if expected_mode != platform_compat.private_file_mode():
                    raise AssertionError("private-file mode contract drifted")
                if (staged.stat().st_mode & 0o777) != expected_mode:
                    raise AssertionError("staged project is not owner-only")

        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            original = fixture.project.read_bytes()
            runner = ProjectSwapRunner(fixture, original)

            Nfl2k5BuildService(runner=runner).build(
                fixture.cache, fixture.project, fixture.output
            )

            self.assertEqual(runner.staged_payloads, [original, original])
            self.assertEqual(
                [FakeBackendRunner._argument(call, "--project") for call in runner.calls],
                [
                    FakeBackendRunner._argument(runner.calls[0], "--project"),
                    FakeBackendRunner._argument(runner.calls[0], "--project"),
                ],
            )
            self.assertNotIn("--audio-exact-inventory", runner.calls[0])
            self.assertFalse(fixture.stage_paths())

    def test_staged_project_preserves_relative_media_origin(self) -> None:
        class RelativePathRunner(FakeBackendRunner):
            def __init__(self, expected: Path) -> None:
                super().__init__()
                self.expected = expected

            def run(self, argv, cwd: Path) -> CommandResult:
                fixed = tuple(str(value) for value in argv)
                project = self._argument(fixed, "--project")
                value = json.loads(project.read_bytes())
                if Path(value["edits"][0]["png"]) != self.expected:
                    raise AssertionError("relative media path changed meaning in staging")
                return super().run(argv, cwd)

        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            replacement = fixture.root / "portrait.png"
            replacement.write_bytes(b"user replacement")
            value = {
                "edits": [{
                    "kind": "player_portrait",
                    "png": replacement.name,
                    "portrait_id": "0001",
                }],
                "purpose": "Synthetic build-service test",
                "schema": "nfl2k5_visual_mod_project/v1",
            }
            fixture.project.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            runner = RelativePathRunner(replacement.resolve())

            Nfl2k5BuildService(runner=runner).build(
                fixture.cache, fixture.project, fixture.output
            )

            self.assertEqual([call[2] for call in runner.calls], ["build", "verify"])

    def test_audio_inventory_failure_precedes_backend_and_publication(self) -> None:
        for kind in ("menu_back_audio", "audo_audio", "ausb_audio"):
            for missing_name in ("fingerprints", "containment"):
                with self.subTest(kind=kind, missing=missing_name):
                    with tempfile.TemporaryDirectory(
                        prefix="2k5-build-service-test-"
                    ) as temporary:
                        fixture = SyntheticFixture(Path(temporary))
                        fixture.set_project_kind(kind)
                        fingerprints, containment = \
                            fixture.create_audio_safety_files()
                        missing = (
                            fingerprints
                            if missing_name == "fingerprints"
                            else containment
                        )
                        inventory_label = (
                            "fingerprint"
                            if missing_name == "fingerprints"
                            else "containment"
                        )
                        missing.unlink()
                        runner = FakeBackendRunner()

                        with self.assertRaisesRegex(
                            ValidationError,
                            rf"{inventory_label} inventory is missing.*Prepare fresh "
                            r"audio safety data.*No output was created",
                        ):
                            Nfl2k5BuildService(runner=runner).build(
                                fixture.cache, fixture.project, fixture.output
                            )

                        self.assertFalse(runner.calls)
                        self.assertFalse(fixture.output.exists())
                        self.assertFalse(fixture.stage_paths())

    def test_project_fields_cannot_select_private_audio_control_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            fingerprints, containment = fixture.create_audio_safety_files()
            attacker = fixture.root / "attacker-controlled.json"
            attacker.write_bytes(b"attacker")
            value = {
                "edits": [{
                    "audio_containment_inventory": str(attacker),
                    "audio_exact_inventory": str(attacker),
                    "kind": "audo_audio",
                    "source_cache_root": str(attacker),
                    "wav": str(attacker),
                }],
                "purpose": "Synthetic build-service test",
                "schema": "nfl2k5_visual_mod_project/v1",
            }
            fixture.project.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            runner = FakeBackendRunner()

            Nfl2k5BuildService(runner=runner).build(
                fixture.cache, fixture.project, fixture.output
            )

            for call in runner.calls:
                self.assertEqual(
                    FakeBackendRunner._argument(call, "--source-cache-root"),
                    fixture.root.resolve(),
                )
                self.assertEqual(
                    FakeBackendRunner._argument(call, "--audio-exact-inventory"),
                    fingerprints,
                )
                self.assertEqual(
                    FakeBackendRunner._argument(
                        call, "--audio-containment-inventory"
                    ),
                    containment,
                )

    def test_audio_inventory_rejects_unsafe_modes_links_and_sizes(self) -> None:
        cases = (
            "derived_symlink",
            "derived_public_mode",
            "file_symlink",
            "containment_symlink",
            "file_hardlink",
            "public_mode",
            "empty_file",
            "fingerprints_too_large",
            "containment_too_large",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                fixture.set_project_kind("menu_back_audio")
                if case == "derived_symlink":
                    elsewhere = fixture.root / "elsewhere"
                    elsewhere.mkdir(mode=0o700)
                    elsewhere.chmod(0o700)
                    (fixture.root / "derived").symlink_to(
                        elsewhere, target_is_directory=True
                    )
                else:
                    fingerprints, containment = fixture.create_audio_safety_files()
                    if case == "derived_public_mode":
                        fingerprints.parent.chmod(0o755)
                    elif case == "file_symlink":
                        fingerprints.unlink()
                        outside = fixture.root / "outside.json"
                        outside.write_bytes(b"{}\n")
                        outside.chmod(0o600)
                        fingerprints.symlink_to(outside)
                    elif case == "containment_symlink":
                        containment.unlink()
                        outside = fixture.root / "outside.json"
                        outside.write_bytes(b"{}\n")
                        outside.chmod(0o600)
                        containment.symlink_to(outside)
                    elif case == "file_hardlink":
                        os.link(fingerprints, fixture.root / "second-link.json")
                    elif case == "public_mode":
                        fingerprints.chmod(0o644)
                    elif case == "empty_file":
                        fingerprints.write_bytes(b"")
                    elif case == "fingerprints_too_large":
                        _sparse(
                            fingerprints,
                            MAX_AUDIO_SOURCE_FINGERPRINTS_BYTES + 1,
                        )
                        fingerprints.chmod(0o600)
                    elif case == "containment_too_large":
                        _sparse(
                            containment,
                            MAX_AUDIO_SOURCE_CONTAINMENT_BYTES + 1,
                        )
                        containment.chmod(0o600)
                runner = FakeBackendRunner()

                with self.assertRaisesRegex(
                    ValidationError,
                    r"Audio edits need complete private source-audio safety data.*"
                    r"No output was created",
                ):
                    Nfl2k5BuildService(runner=runner).build(
                        fixture.cache, fixture.project, fixture.output
                    )

                self.assertFalse(runner.calls)
                self.assertFalse(fixture.output.exists())
                self.assertFalse(fixture.stage_paths())

    def test_audio_inventory_rejects_unsafe_source_cache_root(self) -> None:
        for case in ("public_mode", "symlink"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                fixture.set_project_kind("ausb_audio")
                fixture.create_audio_safety_files()
                cache = fixture.cache
                if case == "public_mode":
                    fixture.root.chmod(0o755)
                else:
                    alias = fixture.root / "cache-alias"
                    alias.symlink_to(fixture.root, target_is_directory=True)
                    cache = SourceCache(
                        source=cache.source,
                        root=alias,
                        pack0=cache.pack0,
                        inventory=cache.inventory,
                        originals=cache.originals,
                        resource_count=cache.resource_count,
                        outer_entry_count=cache.outer_entry_count,
                        kind_counts=cache.kind_counts,
                    )
                runner = FakeBackendRunner()

                with self.assertRaisesRegex(
                    ValidationError,
                    r"private source cache must be an owner-only, mode-0700 "
                    r"non-link directory.*No output was created",
                ):
                    Nfl2k5BuildService(runner=runner).build(
                        cache, fixture.project, fixture.output
                    )

                self.assertFalse(runner.calls)
                self.assertFalse(fixture.output.exists())
                self.assertFalse(fixture.stage_paths())

    def test_build_failure_removes_partial_stage_and_never_calls_verify(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            runner = FakeBackendRunner("build_failure")
            with self.assertRaisesRegex(Nfl2k5BuildError, "replacement PNG is wrong"):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertEqual([call[2] for call in runner.calls], ["build"])
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.stage_paths())

    def test_crib_compression_failures_remain_concise_and_actionable(self) -> None:
        expectations = {
            "crib_too_noisy": "too much fine noise or dithering",
            "crib_too_flat": "too flat for the safe game slot",
        }
        for mode, phrase in expectations.items():
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                runner = FakeBackendRunner(mode)
                with self.assertRaisesRegex(Nfl2k5BuildError, phrase):
                    Nfl2k5BuildService(runner=runner).build(
                        fixture.cache, fixture.project, fixture.output
                    )
                self.assertEqual([call[2] for call in runner.calls], ["build"])
                self.assertFalse(fixture.output.exists())
                self.assertFalse(fixture.stage_paths())

    def test_failed_or_unconfirmed_verify_never_publishes(self) -> None:
        for mode in ("verify_failure", "missing_pass_line"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                runner = FakeBackendRunner(mode)
                with self.assertRaisesRegex(Nfl2k5BuildError, "safety check"):
                    Nfl2k5BuildService(runner=runner).build(
                        fixture.cache, fixture.project, fixture.output
                    )
                self.assertEqual([call[2] for call in runner.calls], ["build", "verify"])
                self.assertFalse(fixture.output.exists())
                self.assertFalse(fixture.stage_paths())

    def test_interruption_cleans_staging_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            runner = FakeBackendRunner("interrupt")
            with self.assertRaises(KeyboardInterrupt):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.stage_paths())

    def test_atomic_publish_preserves_a_racing_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            runner = FakeBackendRunner("collision", fixture.output)
            with self.assertRaisesRegex(OutputRefusedError, "not overwritten"):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertEqual(
                fixture.output.read_bytes(), b"another process owns this file"
            )
            self.assertFalse(fixture.stage_paths())

    def test_existing_destination_is_refused_before_backend_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            fixture.output.write_bytes(b"keep me")
            runner = FakeBackendRunner()
            with self.assertRaisesRegex(OutputRefusedError, "already exists"):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output
                )
            self.assertEqual(fixture.output.read_bytes(), b"keep me")
            self.assertFalse(runner.calls)

    def test_session_recipe_is_private_and_removed_after_build(self) -> None:
        class Session:
            def __init__(self) -> None:
                self.written: Path | None = None

            def write_canonical_project(self, destination: Path) -> Path:
                self.written = destination
                _canonical_project(destination)
                return destination

        with tempfile.TemporaryDirectory(prefix="2k5-build-service-test-") as temporary:
            fixture = SyntheticFixture(Path(temporary))
            session = Session()
            runner = FakeBackendRunner()
            Nfl2k5BuildService(runner=runner).build(
                fixture.cache, session, fixture.output
            )
            assert session.written is not None
            self.assertFalse(session.written.exists())
            self.assertFalse(fixture.stage_paths())
            backend_project = Path(
                runner.calls[0][runner.calls[0].index("--project") + 1]
            )
            self.assertNotEqual(backend_project, session.written)
            self.assertEqual(backend_project.parent, session.written.parent)
            self.assertFalse(backend_project.exists())


if __name__ == "__main__":
    unittest.main()
