"""Product-boundary tests for the Phase 1 atomic NFL 2K5 builder."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from mod_editor.core import platform_compat
from mod_editor.core import nfl2k5_build_service as build_service_mod
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
    SubprocessBuildCommandRunner,
    adopt_process_group,
    use_suspended_launch,
)
from mod_editor.core.nfl2k5_source_cache import (
    INVENTORY_SIZE,
    PACK0_SIZE,
    SOURCE_SHA256,
    SOURCE_SIZE,
    SourceCache,
)


# Below this, a physically allocated file is cheap enough not to matter; above
# it, allocating for real is the difference between an instant fixture and one
# that cannot finish inside the CI per-file timeout.
_SPARSE_REQUIRED_ABOVE = 1 << 30


def _mark_sparse_on_windows(stream, path: Path, size: int) -> None:
    """Ask NTFS to make this file sparse, and confirm it agreed.

    ``truncate`` leaves a hole on ext4/APFS, but on NTFS it physically
    zero-fills unless the file has been flagged sparse first.  The fixtures here
    are ``SOURCE_SIZE`` = 5.87 GiB each and there are eighteen of them, so
    without the hole this file cannot finish: that is exactly how it hit the CI
    per-file timeout on the Windows runner and was killed with no output.

    ``FSCTL_SET_SPARSE`` is the documented request.  It is checked rather than
    assumed -- a volume that is not NTFS would accept the call and still
    allocate -- and if the flag did not take on a file large enough to matter,
    the test is skipped with the reason instead of hanging for seven minutes and
    reporting nothing.  A skip that names its cause is information; a timeout is
    not.
    """

    if not platform_compat.IS_WINDOWS:
        return
    granted = False
    try:
        import ctypes
        import msvcrt

        fsctl_set_sparse = 0x000900C4
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.DeviceIoControl.argtypes = [
            ctypes.c_void_p,   # hDevice
            ctypes.c_ulong,    # dwIoControlCode
            ctypes.c_void_p,   # lpInBuffer
            ctypes.c_ulong,    # nInBufferSize
            ctypes.c_void_p,   # lpOutBuffer
            ctypes.c_ulong,    # nOutBufferSize
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,   # lpOverlapped
        ]
        kernel32.DeviceIoControl.restype = ctypes.c_int
        handle = msvcrt.get_osfhandle(stream.fileno())
        returned = ctypes.c_ulong(0)
        granted = bool(
            kernel32.DeviceIoControl(
                ctypes.c_void_p(handle),
                ctypes.c_ulong(fsctl_set_sparse),
                None,
                0,
                None,
                0,
                ctypes.byref(returned),
                None,
            )
        )
        if granted:
            stream.flush()
            attributes = getattr(os.stat(path), "st_file_attributes", 0)
            sparse_flag = getattr(stat, "FILE_ATTRIBUTE_SPARSE_FILE", 0x200)
            granted = bool(attributes & sparse_flag)
    except Exception:  # pragma: no cover - diagnosed by the skip below
        granted = False
    if not granted and size > _SPARSE_REQUIRED_ABOVE:
        raise unittest.SkipTest(
            f"this volume would physically allocate the {size / (1 << 30):.2f} GiB "
            f"fixture at {path} (FSCTL_SET_SPARSE did not take), which cannot "
            "finish inside the per-file timeout"
        )


def _set_end_of_file_on_windows(stream, size: int) -> bool:
    """Extend to ``size`` with ``SetEndOfFile``, which does not write anything.

    ``truncate`` is the wrong tool on Windows even after FSCTL_SET_SPARSE: the
    CRT implements it as ``_chsize_s``, which explicitly ZERO-FILLS the range it
    adds, and writing zeros allocates real clusters straight through the sparse
    flag.  That is what made each of these 5.87 GiB fixtures take roughly a
    hundred seconds on the runner and walked the file into its 420s per-file
    timeout four cases in -- it was never a deadlock, just eighteen fixtures at
    six gigabytes of real writes each.

    ``SetFilePointerEx`` + ``SetEndOfFile`` only moves the end marker, so on a
    sparse file it is O(1) and allocates nothing.  Returns whether it worked;
    the caller falls back to ``truncate`` if it did not.
    """

    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetFilePointerEx.argtypes = [
            ctypes.c_void_p,                    # hFile
            ctypes.c_longlong,                  # liDistanceToMove
            ctypes.POINTER(ctypes.c_longlong),  # lpNewFilePointer
            ctypes.c_ulong,                     # dwMoveMethod
        ]
        kernel32.SetFilePointerEx.restype = ctypes.c_int
        kernel32.SetEndOfFile.argtypes = [ctypes.c_void_p]
        kernel32.SetEndOfFile.restype = ctypes.c_int

        stream.flush()
        handle = ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno()))
        file_begin = 0
        if not kernel32.SetFilePointerEx(
            handle, ctypes.c_longlong(size), None, ctypes.c_ulong(file_begin)
        ):
            return False
        return bool(kernel32.SetEndOfFile(handle))
    except Exception:  # pragma: no cover - falls back to truncate
        return False


def _sparse(path: Path, size: int, prefix: bytes = b"") -> None:
    with path.open("wb") as stream:
        _mark_sparse_on_windows(stream, path, size)
        if prefix:
            stream.write(prefix)
        if platform_compat.IS_WINDOWS and _set_end_of_file_on_windows(stream, size):
            return
        stream.truncate(size)


def _canonical_project(path: Path, kind: str = "synthetic-test-edit") -> None:
    value = {
        "edits": [{"kind": kind}],
        "purpose": "Synthetic build-service test",
        "schema": "nfl2k5_visual_mod_project/v1",
    }
    path.write_text(  # newline="" keeps the bytes canonical on Windows
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
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
            output_size = source.stat().st_size
            _sparse(output, output_size, b"verified-synthetic-output")
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
                    "xiso_size": output_size,
                    "xiso_sha256": "a" * 64,
                    "device": info.st_dev,
                    "inode": info.st_ino,
                },
                "patch": {"changed_byte_count": 1234},
            }
            manifest.write_text(json.dumps(receipt), encoding="utf-8", newline="")
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

            # The publish pin.  The service opens the staged XISO and holds that
            # descriptor across the rename on purpose: it is what keeps the
            # verified inode alive, so the post-publish (st_dev, st_ino)
            # comparison is a proof rather than a coincidence about a number the
            # filesystem may recycle.  Two things must therefore stay true, and
            # neither is visible from the build's return value:
            #   * the descriptor comes from platform_compat, which is the only
            #     place that grants Windows FILE_SHARE_DELETE -- without that bit
            #     Windows refuses the rename outright (WinError 32);
            #   * it is still open, and still names the staged file, at the
            #     instant of the publish.  Closing it earlier would make Windows
            #     happy and silently trade the held-descriptor proof for a name
            #     lookup.
            pin: dict[str, object] = {}
            open_pin = platform_compat.open_existing_for_publish
            publish = build_service_mod._rename_noreplace

            def recording_open_pin(path):
                descriptor = open_pin(path)
                pin["path"] = Path(path)
                pin["descriptor"] = descriptor
                return descriptor

            def recording_publish(source, destination):
                # os.fstat raises if the pin was closed early; that is the check.
                pin["held"] = os.fstat(pin["descriptor"])
                pin["staged"] = source.stat()
                return publish(source, destination)

            with (
                patch.object(
                    platform_compat, "open_existing_for_publish", recording_open_pin
                ),
                patch(
                    "mod_editor.core.nfl2k5_build_service._rename_noreplace",
                    recording_publish,
                ),
            ):
                result = Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output, events.append
                )

            self.assertEqual(pin["path"].name, "modded.xiso")
            self.assertEqual(
                (pin["held"].st_dev, pin["held"].st_ino),
                (pin["staged"].st_dev, pin["staged"].st_ino),
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

    def test_alternate_container_layout_build_reports_its_actual_size(self) -> None:
        for actual_size in (6_300_958_720, 7_825_162_240):
            with self.subTest(actual_size=actual_size), tempfile.TemporaryDirectory(
                prefix="2k5-build-layout-test-"
            ) as temporary:
                fixture = SyntheticFixture(Path(temporary))
                with fixture.source.open("r+b") as stream:
                    stream.truncate(actual_size)
                fixture.cache = replace(
                    fixture.cache,
                    source=replace(
                        fixture.cache.source,
                        sha256=("a" if actual_size < 7_000_000_000 else "b") * 64,
                        size=actual_size,
                    ),
                )
                source_before = fixture.source.stat()

                result = Nfl2k5BuildService(runner=FakeBackendRunner()).build(
                    fixture.cache, fixture.project, fixture.output
                )

                self.assertEqual(result.output_size, actual_size)
                self.assertEqual(fixture.output.stat().st_size, actual_size)
                source_after = fixture.source.stat()
                self.assertEqual(
                    (
                        source_after.st_dev,
                        source_after.st_ino,
                        source_after.st_size,
                        source_after.st_mtime_ns,
                    ),
                    (
                        source_before.st_dev,
                        source_before.st_ino,
                        source_before.st_size,
                        source_before.st_mtime_ns,
                    ),
                )

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
                        fingerprints.resolve(),
                    )
                    self.assertEqual(
                        FakeBackendRunner._argument(
                            call, "--audio-containment-inventory"
                        ),
                        containment.resolve(),
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
            fixture.project.write_text(  # newline="" keeps the bytes canonical on Windows
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="",
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
            fixture.project.write_text(  # newline="" keeps the bytes canonical on Windows
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="",
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
                    fingerprints.resolve(),
                )
                self.assertEqual(
                    FakeBackendRunner._argument(
                        call, "--audio-containment-inventory"
                    ),
                    containment.resolve(),
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
            # Announce each case as it STARTS, flushed.  verbosity=2 narrowed
            # the Windows hang to this test but only prints a subTest once it
            # has finished, so a case that never returns is still anonymous.
            # This makes the next timeout name it exactly.
            if platform_compat.IS_WINDOWS and case in {
                "derived_public_mode", "public_mode",
            }:
                # These two express "unsafe" by chmod-ing something public.
                # On Windows mode bits confer no privacy at all -- a directory
                # always reports 0o777 and a writable file 0o666 -- so a chmod
                # cannot produce the unsafe state the case is about, and the
                # guard correctly does not fire.  Privacy there is the DACL,
                # which verify_private_root_placement checks and which these
                # cases do not touch.  Skipped with the reason rather than
                # asserted into a false pass.
                with self.subTest(case=case):
                    self.skipTest(
                        f"{case} makes its subject public with chmod, which "
                        "confers no privacy on Windows; the DACL is what does"
                    )
                continue
            print(f"  [case] {case}", file=sys.stderr, flush=True)
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix="2k5-build-service-test-"
            ) as temporary:
                # Phase markers: the CI per-file timeout on Windows kills this
                # file mid-case, and "which case" was not enough to say whether
                # the fixture, the product call or the temp-directory teardown
                # is what does not return.
                print("    [phase] fixture", file=sys.stderr, flush=True)
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

                print("    [phase] build", file=sys.stderr, flush=True)
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
                print("    [phase] teardown", file=sys.stderr, flush=True)

    def test_audio_inventory_rejects_unsafe_source_cache_root(self) -> None:
        for case in ("public_mode", "symlink"):
            if platform_compat.IS_WINDOWS and case == "public_mode":
                # Same reason as the mode cases in the test above: chmod cannot
                # make a directory public on Windows -- it always reports 0o777
                # and the mode confers no privacy -- so the unsafe state this
                # case is about cannot be produced, and the guard correctly does
                # not fire.  The DACL is what carries privacy there, and this
                # case does not touch it.
                with self.subTest(case=case):
                    self.skipTest(
                        "public_mode makes the cache root public with chmod, "
                        "which confers no privacy on Windows; the DACL does"
                    )
                continue
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


class FakeJobGroup:
    """A stand-in for the Win32 job object, answering a scripted count."""

    def __init__(self, counts: list[int | None]) -> None:
        self._counts = list(counts)
        self.terminate_calls = 0
        self.closed = False

    def terminate(self) -> bool:
        self.terminate_calls += 1
        return True

    def active_process_count(self) -> int | None:
        return self._counts.pop(0) if len(self._counts) > 1 else self._counts[0]

    def close(self) -> None:
        self.closed = True


class FakeChild:
    """A stand-in for ``Popen`` exposing only what the teardown path touches."""

    def __init__(self, alive: bool, dies_when_killed: bool = True) -> None:
        self.alive = alive
        self.dies_when_killed = dies_when_killed
        self.kill_calls = 0
        self.communicate_calls = 0
        self.pid = -1

    def poll(self) -> int | None:
        return None if self.alive else 0

    def kill(self) -> None:
        self.kill_calls += 1
        if self.dies_when_killed:
            self.alive = False

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.communicate_calls += 1
        return "", ""


class _FakePublishKernel32:
    """The two kernel32 entry points the publish-pin open touches.

    ``CreateFileW`` resolves against the real filesystem of this host and returns
    a real descriptor as the "handle", so the Windows branch yields a descriptor
    with genuine ``fstat``/``fsync``/``close`` semantics here and can be driven
    end to end.  Every argument it was called with is recorded, because the share
    mode is the entire fix and an assertion about it is the only thing that can
    fail on a host that is not Windows.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def CreateFileW(  # noqa: N802 - mirrors the Win32 name
        self, path, access, share, security, disposition, flags, template
    ):
        self.calls.append(
            {
                "path": os.fspath(path),
                "access": access,
                "share": share,
                "disposition": disposition,
                "flags": flags,
            }
        )
        try:
            return os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        except OSError:
            # The Win32 last-error itself cannot be simulated here --
            # ctypes.set_last_error/get_last_error exist only on Windows, so
            # platform_compat._win_last_error() reads 0 on this host.  The
            # translation of a specific code is therefore asserted by driving
            # that seam directly; this only has to report the failure.
            return platform_compat._win_invalid_handle()

    def CloseHandle(self, handle):  # noqa: N802
        try:
            os.close(handle)
        except OSError:
            return 0
        return 1


@contextlib.contextmanager
def _simulated_windows_publish():
    """Run the enclosed block on the Windows branch of the publish-pin open.

    Windows cannot run here, so the two primitives that branch needs are
    supplied: ``_windows_kernel_api`` by the fake above, and ``msvcrt`` by a
    stand-in whose ``open_osfhandle`` returns the descriptor the fake already
    made.  Everything between them -- the access rights, the share mode, the
    disposition, the handle-ownership guard, the error translation -- is the
    shipped code, so what the assertions see is what a real ``CreateFileW`` would
    be asked for.
    """

    saved_flags = (
        platform_compat.IS_WINDOWS,
        platform_compat.IS_LINUX,
        platform_compat.IS_MACOS,
    )
    saved_loader = platform_compat._windows_kernel_api
    saved_cache = platform_compat._windows_kernel_api_cache
    saved_msvcrt = sys.modules.get("msvcrt")
    kernel32 = _FakePublishKernel32()
    fake_api = platform_compat._WindowsKernelApi(kernel32=kernel32)
    fake_msvcrt = ModuleType("msvcrt")
    fake_msvcrt.open_osfhandle = lambda handle, flags: handle
    platform_compat.IS_WINDOWS = True
    platform_compat.IS_LINUX = False
    platform_compat.IS_MACOS = False
    platform_compat._windows_kernel_api_cache = None
    platform_compat._windows_kernel_api = lambda: fake_api
    sys.modules["msvcrt"] = fake_msvcrt
    try:
        yield kernel32
    finally:
        (
            platform_compat.IS_WINDOWS,
            platform_compat.IS_LINUX,
            platform_compat.IS_MACOS,
        ) = saved_flags
        platform_compat._windows_kernel_api = saved_loader
        platform_compat._windows_kernel_api_cache = saved_cache
        if saved_msvcrt is None:
            sys.modules.pop("msvcrt", None)
        else:
            sys.modules["msvcrt"] = saved_msvcrt


class PublishPinOpenTests(unittest.TestCase):
    """The descriptor held across the publish must be opened in a way Windows
    will still rename through -- without altering a single POSIX syscall.

    The staged XISO is created by the *backend*, under a pathname that backend's
    contract fixes, so the existing share-delete precedent (``CREATE_NEW``, for a
    staging file the process creates itself) cannot be reused; this is its
    ``OPEN_EXISTING`` twin, and these assertions are what distinguish the two.
    """

    def test_posix_open_keeps_the_exact_flags_it_always_used(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("this asserts the POSIX branch, which Windows never takes")
        with tempfile.TemporaryDirectory() as name:
            staged = Path(name) / "modded.xiso"
            staged.write_bytes(b"verified bytes")
            expected = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_BINARY", 0)
            )
            seen: list[tuple[str, int]] = []
            real_open = os.open

            def recording(path, flags, *rest):
                seen.append((os.fspath(path), flags))
                return real_open(path, flags, *rest)

            with patch.object(os, "open", recording):
                descriptor = platform_compat.open_existing_for_publish(staged)
            try:
                # One open, read-only, no-follow: byte for byte the call this
                # replaced, so Linux and macOS are unchanged.
                self.assertEqual(seen, [(str(staged), expected)])
                self.assertEqual(os.fstat(descriptor).st_ino, staged.stat().st_ino)
            finally:
                os.close(descriptor)
            self.assertEqual(
                platform_compat.existing_publish_open_mechanism(),
                platform_compat.PUBLISH_PIN_POSIX_OPEN,
            )

    def test_windows_opens_the_existing_file_with_share_delete(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            staged = root / "modded.xiso"
            staged.write_bytes(b"verified bytes")
            published = root / "My Modded 2K5.xiso.iso"
            with _simulated_windows_publish() as kernel32:
                self.assertEqual(
                    platform_compat.existing_publish_open_mechanism(),
                    platform_compat.PUBLISH_PIN_WINDOWS_SHARE_DELETE,
                )
                descriptor = platform_compat.open_existing_for_publish(staged)
                try:
                    (call,) = kernel32.calls
                    self.assertEqual(call["path"], str(staged))
                    # OPEN_EXISTING, not CREATE_NEW: the backend made this file
                    # and its name is not ours to invent, which is exactly why
                    # create_private_staging_file could not be reused.
                    self.assertEqual(
                        call["disposition"], platform_compat._WIN_OPEN_EXISTING
                    )
                    self.assertNotEqual(
                        call["disposition"], platform_compat._WIN_CREATE_NEW
                    )
                    # GENERIC_READ and nothing more -- the same rights O_RDONLY
                    # already asked for, so only the share mode changed.
                    self.assertEqual(
                        call["access"], platform_compat._WIN_GENERIC_READ
                    )
                    # The bit whose absence is WinError 32.
                    self.assertTrue(
                        call["share"] & platform_compat._WIN_FILE_SHARE_DELETE
                    )
                    self.assertEqual(
                        call["share"], platform_compat._WIN_STAGE_SHARE_MODE
                    )
                    # And the descriptor is a real one, still naming the verified
                    # object across the publish -- the proof the share bit exists
                    # to preserve, not replace.
                    pinned = os.fstat(descriptor)
                    staged_identity = staged.stat()
                    self.assertEqual(
                        (pinned.st_dev, pinned.st_ino),
                        (staged_identity.st_dev, staged_identity.st_ino),
                    )
                    # Renaming WHILE the descriptor is open is the behaviour
                    # the share bit buys, and it is demonstrated here against
                    # the simulated kernel32 -- whose open_osfhandle hands back
                    # the descriptor the fake made with a plain os.open.  That
                    # descriptor genuinely has no FILE_SHARE_DELETE, so on a
                    # real Windows host this rename is refused by the very
                    # mechanism under test: the demonstration would be asserting
                    # the shim's limits, not the product's.  The CreateFileW
                    # contract above -- disposition, access, share mode -- is
                    # the real assertion and runs on every platform.
                    # sys.platform, not IS_WINDOWS: the simulation above sets
                    # that flag True on every host, so keying on it would skip
                    # the demonstration everywhere.  The question here is what
                    # the REAL kernel underneath will permit.
                    if not sys.platform.startswith("win"):
                        os.rename(staged, published)
                        after = os.fstat(descriptor)
                        self.assertEqual(
                            (after.st_dev, after.st_ino),
                            (pinned.st_dev, pinned.st_ino),
                        )
                finally:
                    os.close(descriptor)
            if not sys.platform.startswith("win"):
                self.assertEqual(published.read_bytes(), b"verified bytes")

    def test_windows_failure_is_translated_not_swallowed(self) -> None:
        # A CreateFileW that fails must raise the same exception os.open would
        # have raised for that Win32 code, so the caller's existing except
        # clauses keep working -- and must never return a descriptor.  The
        # last-error is patched at the seam the product reads it from because
        # ctypes.set_last_error exists only on Windows.
        translations = (
            (platform_compat._WIN_ERROR_FILE_NOT_FOUND, FileNotFoundError),
            (platform_compat._WIN_ERROR_PATH_NOT_FOUND, FileNotFoundError),
            (platform_compat._WIN_ERROR_ACCESS_DENIED, PermissionError),
            (platform_compat._WIN_ERROR_SHARING_VIOLATION, PermissionError),
            (1234, OSError),
        )
        with tempfile.TemporaryDirectory() as name:
            missing = Path(name) / "modded.xiso"
            for code, expected in translations:
                with self.subTest(win_error=code):
                    with _simulated_windows_publish():
                        with patch.object(
                            platform_compat, "_win_last_error", lambda code=code: code
                        ):
                            with self.assertRaises(expected) as caught:
                                platform_compat.open_existing_for_publish(missing)
                    # Exactly this type: an untranslated code must stay a plain
                    # OSError rather than be reported as a missing file.
                    self.assertIs(type(caught.exception), expected)

    def test_windows_without_the_primitives_fails_closed_on_windows(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("a real Windows host has both primitives")
        with tempfile.TemporaryDirectory() as name:
            staged = Path(name) / "modded.xiso"
            staged.write_bytes(b"verified bytes")
            # IS_WINDOWS flipped on a POSIX host with no kernel32 and no msvcrt:
            # the documented simulation fallback, which this host can honour
            # because its own open really does carry O_NOFOLLOW and it really can
            # rename an open file.
            with patch.object(platform_compat, "IS_WINDOWS", True):
                descriptor = platform_compat.open_existing_for_publish(staged)
                os.close(descriptor)
                # On a real Windows interpreter the same missing primitive
                # re-raises instead of degrading, so a descriptor that cannot be
                # published through is never handed back.
                with patch.object(sys, "platform", "win32"):
                    with self.assertRaises(
                        platform_compat.DirectoryTransactionUnavailable
                    ):
                        platform_compat.open_existing_for_publish(staged)


class WindowsBackendTeardownTests(unittest.TestCase):
    """The Windows teardown, exercised on any host, without a Windows kernel.

    ``os.killpg`` and ``signal.SIGKILL`` do not exist on Windows, so the POSIX
    teardown raised ``AttributeError`` on its very first call, stopped nothing,
    and left a runaway backend writing into the staging directory the caller was
    about to remove.  Its Job Object replacement has to keep three outcomes
    distinct: a group that drained, a genuine observed survivor, and an
    accounting query that could not be read at all -- which is not evidence of a
    survivor and must never be reported as one.
    """

    def _windows_teardown(self, process: object, group: object) -> None:
        with (
            patch.object(platform_compat, "IS_WINDOWS", True),
            patch(
                "mod_editor.core.nfl2k5_build_service.PROCESS_STOP_GRACE_SECONDS",
                0.01,
            ),
            patch("mod_editor.core.nfl2k5_build_service.PROCESS_POLL_SECONDS", 0.0),
            # The POSIX group calls do not exist on Windows; a single one left
            # on that path is the defect this replaces, so fail loudly on it.
            patch.object(
                os,
                "killpg",
                create=True,
                side_effect=AssertionError("POSIX killpg ran on the Windows branch"),
            ),
        ):
            SubprocessBuildCommandRunner._stop_process_group(process, group)

    def test_drained_job_is_not_reported_as_a_survivor(self) -> None:
        process = FakeChild(alive=True)
        group = FakeJobGroup([0])

        self._windows_teardown(process, group)

        self.assertEqual(group.terminate_calls, 1)
        self.assertTrue(group.closed)

    def test_observed_survivor_is_reported_and_never_silently_ignored(self) -> None:
        process = FakeChild(alive=True)
        group = FakeJobGroup([2])

        with self.assertRaisesRegex(Nfl2k5BuildError, "background process"):
            self._windows_teardown(process, group)

        # Terminated once, then re-terminated when the group had not drained.
        self.assertEqual(group.terminate_calls, 2)
        self.assertTrue(group.closed)

    def test_unreadable_accounting_alone_is_not_a_survivor(self) -> None:
        process = FakeChild(alive=False)
        group = FakeJobGroup([None])

        self._windows_teardown(process, group)

        self.assertTrue(group.closed)

    def test_unreadable_accounting_with_a_live_child_is_a_survivor(self) -> None:
        process = FakeChild(alive=True, dies_when_killed=False)
        group = FakeJobGroup([None])

        with self.assertRaisesRegex(Nfl2k5BuildError, "background process"):
            self._windows_teardown(process, group)

        self.assertTrue(group.closed)

    def test_without_a_job_the_direct_child_still_decides_the_outcome(self) -> None:
        stopped = FakeChild(alive=True)
        self._windows_teardown(stopped, None)
        self.assertEqual(stopped.kill_calls, 1)

        unstoppable = FakeChild(alive=True, dies_when_killed=False)
        with self.assertRaisesRegex(Nfl2k5BuildError, "background process"):
            self._windows_teardown(unstoppable, None)
        self.assertEqual(unstoppable.kill_calls, 1)

    def test_posix_launch_and_teardown_keep_their_exact_behaviour(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("this asserts the POSIX branch, which Windows never takes")
        # No CREATE_SUSPENDED and no job object off Windows: the launch keeps
        # ``creationflags=0`` and the teardown stays the pure killpg path.
        self.assertFalse(use_suspended_launch())
        self.assertIsNone(adopt_process_group(FakeChild(alive=True)))

        process = FakeChild(alive=False)
        SubprocessBuildCommandRunner._stop_process_group(process)
        self.assertEqual(process.communicate_calls, 0)


if __name__ == "__main__":
    # verbosity=2 prints each test's name as it STARTS.  This file has twice
    # been killed by the CI per-file timeout on the Windows runner, and a killed
    # unittest run has printed nothing at all -- the report is emitted at the
    # end, which never arrives -- so the log could not say which test hung.
    # Naming them as they start costs nothing and makes the next timeout
    # self-diagnosing.
    unittest.main(verbosity=2)
