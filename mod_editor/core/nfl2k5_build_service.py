"""Atomic product build service for NFL 2K5 visual-mod projects.

The reviewed visual-mod backend intentionally produces a manifest and decoded
proof artifacts alongside its output.  Those are useful implementation details,
but they are not product deliverables and some are derived from the user's game.
This service contains all backend output in a private, hidden staging directory,
runs one independent verification, and publishes only the verified XISO.

The source is always handed to the backend as a read-only input.  Publication is
an atomic, no-overwrite move on the destination filesystem, so a partial or
unverified build can never appear at the requested output path.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import Enum
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Protocol, Sequence

from .errors import ModEditorError, OutputRefusedError, ValidationError
from .nfl2k5_source_cache import (
    INVENTORY_SIZE,
    PACK0_SIZE,
    SOURCE_SHA256,
    SOURCE_SIZE,
    SourceCache,
)


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "tools/nfl2k5_visual_mod_project.py"
PROJECT_SCHEMA = "nfl2k5_visual_mod_project/v1"
BUILD_SCHEMA = "nfl2k5_visual_mod_build/v1"
MAX_PROJECT_BYTES = 64 * 1024 * 1024
EXPECTED_FINGERPRINT = "nfl2k5-usa-retail-xiso"
EXPECTED_VERIFY_PREFIX = "NFL2K5_VISUAL_MOD_VERIFY_PASS "
AUDIO_EDIT_KINDS = frozenset({
    "menu_back_audio",
    "audo_audio",
    "ausb_audio",
})
AUDIO_SOURCE_FINGERPRINTS_RELATIVE = Path(
    "derived/audio-source-pcm-fingerprints-v1.json"
)
AUDIO_SOURCE_CONTAINMENT_RELATIVE = Path(
    "derived/audio-source-pcm-containment-v2.json"
)
MAX_AUDIO_SOURCE_FINGERPRINTS_BYTES = 64 * 1024 * 1024
MAX_AUDIO_SOURCE_CONTAINMENT_BYTES = 512 * 1024 * 1024
AT_FDCWD = -100
RENAME_NOREPLACE = 1
BUILD_SPACE_MARGIN = 512 * 1024 * 1024


class Nfl2k5BuildError(ModEditorError):
    """A build failed without publishing an output XISO."""


class BuildStage(str, Enum):
    PREPARING = "preparing"
    BUILDING = "building"
    VERIFYING = "verifying"
    PUBLISHING = "publishing"
    COMPLETE = "complete"


@dataclass(frozen=True)
class BuildEvent:
    stage: BuildStage
    completed: int
    total: int
    message: str


BuildProgress = Callable[[BuildEvent], None]


@dataclass(frozen=True)
class BuildResult:
    """Small, retail-free result safe to keep in the application session."""

    output_xiso: Path
    output_size: int
    output_sha256: str
    edit_count: int
    changed_byte_count: int
    independently_verified: bool = True


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _AudioSafetyInputs:
    """Canonical private inputs required by an audio-bearing build recipe."""

    source_cache_root: Path
    source_fingerprints: Path
    source_containment: Path


class BuildCommandRunner(Protocol):
    def run(self, argv: Sequence[str], cwd: Path) -> CommandResult: ...


class CanonicalProjectWriter(Protocol):
    """Minimal StudioSession contract used by :class:`Nfl2k5BuildService`."""

    def write_canonical_project(self, destination: Path) -> Path | None: ...


class SubprocessBuildCommandRunner:
    """Run the fixed backend argv without a shell or ambient injection hooks."""

    _environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }

    def run(self, argv: Sequence[str], cwd: Path) -> CommandResult:
        fixed = tuple(os.fspath(value) for value in argv)
        try:
            process = subprocess.Popen(
                fixed,
                cwd=cwd,
                env=self._environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                start_new_session=True,
            )
        except OSError as exc:
            raise Nfl2k5BuildError(
                "2K5 Mod Studio could not start its ISO builder. "
                f"Check that Python is installed and try again ({exc})."
            ) from exc
        try:
            stdout, stderr = process.communicate()
        except BaseException:
            # The backend owns only paths below our staging directory.  Stop its
            # whole process group before that directory is removed.
            self._stop_process_group(process)
            raise
        return CommandResult(fixed, process.returncode, stdout, stderr)

    @staticmethod
    def _stop_process_group(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()


def _emit(progress: BuildProgress | None, stage: BuildStage,
          completed: int, total: int, message: str) -> None:
    if progress is None:
        return
    try:
        progress(BuildEvent(stage, completed, total, message))
    except Exception:
        # Progress is an observer, never part of the safety transaction.
        pass


def _regular_file(path: Path, label: str, expected_size: int | None = None,
                  maximum_size: int | None = None) -> tuple[Path, os.stat_result]:
    selected = path.expanduser()
    try:
        supplied = selected.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing: {selected}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError(f"{label} must be a regular, non-link file: {selected}")
    resolved = selected.resolve(strict=True)
    current = resolved.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (supplied.st_dev, supplied.st_ino):
        raise ValidationError(f"{label} changed while it was being opened")
    if expected_size is not None and current.st_size != expected_size:
        raise ValidationError(
            f"{label} has the wrong size ({current.st_size:,} bytes; "
            f"{expected_size:,} expected)."
        )
    if maximum_size is not None and not 0 < current.st_size <= maximum_size:
        raise ValidationError(f"{label} is empty or unexpectedly large")
    return resolved, current


def _read_regular_snapshot(
    path: Path,
    label: str,
    maximum_size: int,
) -> tuple[Path, bytes]:
    """Read one immutable bounded snapshot without trusting its pathname twice."""

    resolved, named = _regular_file(
        path, label, maximum_size=maximum_size)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | \
        getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise ValidationError(f"{label} could not be opened safely: {resolved}") from exc
    try:
        expected = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            ) != expected
        ):
            raise ValidationError(f"{label} changed while it was being opened")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_size + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_size:
                raise ValidationError(f"{label} is empty or unexpectedly large")
        try:
            named_after = resolved.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValidationError(f"{label} changed while it was being read") from exc
        opened_after = os.fstat(descriptor)
        if (
            total != named.st_size
            or (
                opened_after.st_dev,
                opened_after.st_ino,
                opened_after.st_size,
                opened_after.st_mtime_ns,
                opened_after.st_ctime_ns,
            ) != expected
            or (
                named_after.st_dev,
                named_after.st_ino,
                named_after.st_size,
                named_after.st_mtime_ns,
                named_after.st_ctime_ns,
            ) != expected
        ):
            raise ValidationError(f"{label} changed while it was being read")
        return resolved, b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_private_snapshot(path: Path, payload: bytes) -> Path:
    """Exclusively materialize one canonical project in private staging."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | \
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            if written <= 0:
                raise OSError("short write while staging the mod project")
            cursor += written
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != len(payload)
        ):
            raise ValidationError(
                "The mod project could not be pinned safely in private staging."
            )
    finally:
        if descriptor is not None:
            os.close(descriptor)
    staged, _ = _regular_file(
        path, "staged mod project", expected_size=len(payload))
    return staged


def _new_output_path(path: Path) -> Path:
    selected = path.expanduser()
    if not selected.is_absolute():
        selected = Path.cwd() / selected
    if selected.name in {"", ".", ".."}:
        raise ValidationError("Choose a filename for the modded XISO")
    try:
        parent_info = selected.parent.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(
            f"The output folder does not exist: {selected.parent}"
        ) from exc
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ValidationError(f"The output folder is not a directory: {selected.parent}")
    parent = selected.parent.resolve(strict=True)
    output = parent / selected.name
    try:
        output.lstat()
    except FileNotFoundError:
        return output
    raise OutputRefusedError(
        f"The output already exists and was not changed: {output}. "
        "Choose a new filename or move the existing file first."
    )


def _require_build_space(parent: Path) -> None:
    """Refuse before staging when one complete XISO cannot fit safely."""

    required = SOURCE_SIZE + BUILD_SPACE_MARGIN
    try:
        free = shutil.disk_usage(parent).free
    except OSError as exc:
        raise Nfl2k5BuildError(
            "2K5 Mod Studio could not check free space in the selected output "
            f"folder. Choose another local folder and try again ({exc})."
        ) from exc
    if free >= required:
        return
    shortfall = required - free
    if shortfall >= 1024**3:
        unit = 1024**3
        suffix = "GiB"
    elif shortfall >= 1024**2:
        unit = 1024**2
        suffix = "MiB"
    elif shortfall >= 1024:
        unit = 1024
        suffix = "KiB"
    else:
        shortfall_text = f"{shortfall} byte{'s' if shortfall != 1 else ''}"
        unit = 0
        suffix = ""
    if unit:
        # This is an instruction, so round upward: freeing the displayed amount
        # must be sufficient even when the exact shortage is between hundredths.
        hundredths = (shortfall * 100 + unit - 1) // unit
        shortfall_text = f"{hundredths / 100:.2f} {suffix}"
    raise Nfl2k5BuildError(
        "The selected drive does not have enough free space for a safe 2K5 "
        f"build. It has {free / 1024**3:.2f} GiB free; this build needs at "
        f"least {required / 1024**3:.2f} GiB. Free another {shortfall_text} "
        "or choose a different drive. No "
        "output was created."
    )


def _last_message(result: CommandResult) -> str:
    lines = [
        line.strip() for line in (result.stderr + "\n" + result.stdout).splitlines()
        if line.strip()
    ]
    if not lines:
        return "The internal tool did not provide an error message."
    message = lines[-1]
    if message.lower().startswith("error:"):
        message = message.split(":", 1)[1].strip()
    if len(message) > 600:
        message = message[:597] + "..."
    return message


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
        getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _link_then_unlink(source: Path, destination: Path) -> None:
    """Portable Unix fallback that also refuses an existing destination."""

    try:
        os.link(source, destination, follow_symlinks=False)
    except FileExistsError as exc:
        raise OutputRefusedError(
            f"The output was created by another process and was not overwritten: "
            f"{destination}"
        ) from exc
    except OSError as exc:
        raise Nfl2k5BuildError(
            "The selected folder cannot publish a large file safely. "
            "Choose a normal local Linux folder and build again."
        ) from exc
    os.unlink(source)


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically move *source* while refusing to replace *destination*.

    2K5 Mod Studio targets Linux, where renameat2(RENAME_NOREPLACE) supplies
    the exact transaction needed here.  A hard-link transaction is retained as
    a fallback for older kernels/libcs.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        _link_then_unlink(source, destination)
        return
    renameat2.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        AT_FDCWD, os.fsencode(source), AT_FDCWD, os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result == 0:
        return
    number = ctypes.get_errno()
    if number == errno.EEXIST:
        raise OutputRefusedError(
            f"The output was created by another process and was not overwritten: "
            f"{destination}"
        )
    if number in {
        errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP,
        getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
    }:
        _link_then_unlink(source, destination)
        return
    raise Nfl2k5BuildError(
        "The verified ISO could not be moved into the selected output folder: "
        f"{os.strerror(number)}"
    )


def _unlink_if_identity(path: Path, identity: tuple[int, int]) -> None:
    """Remove only the file this transaction published, never a replacement."""

    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(current.st_mode) and \
            (current.st_dev, current.st_ino) == identity:
        path.unlink()


def _audio_safety_error(detail: str) -> ValidationError:
    return ValidationError(
        "Audio edits need complete private source-audio safety data, but "
        f"{detail}. Prepare fresh audio safety data from your loaded NFL 2K5 "
        "XISO in Mod Studio, then build again. No output was created."
    )


def _private_audio_inventory_file(
    directory_fd: int,
    path: Path,
    label: str,
    maximum_size: int,
) -> Path:
    """Validate one exact owner-only file beneath an already-open dirfd."""

    try:
        named = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise _audio_safety_error(f"{label} is missing at {path}") from exc
    except OSError as exc:
        raise _audio_safety_error(
            f"{label} could not be inspected safely at {path} ({exc})"
        ) from exc
    if (
        not stat.S_ISREG(named.st_mode)
        or stat.S_ISLNK(named.st_mode)
        or named.st_uid != os.getuid()
        or named.st_nlink != 1
        or stat.S_IMODE(named.st_mode) != 0o600
    ):
        raise _audio_safety_error(
            f"{label} must be a mode-0600, owner-only, non-linked regular file "
            f"at {path}"
        )
    if not 0 < named.st_size <= maximum_size:
        raise _audio_safety_error(
            f"{label} is empty or exceeds its {maximum_size / 1024**2:.0f} MiB "
            f"safety limit at {path}"
        )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | \
        getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path.name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise _audio_safety_error(
            f"{label} could not be opened safely at {path} ({exc})"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        try:
            named_after = os.stat(
                path.name, dir_fd=directory_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise _audio_safety_error(
                f"{label} changed while it was being checked at {path}"
            ) from exc
        expected = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            ) != expected
            or (
                named_after.st_dev,
                named_after.st_ino,
                named_after.st_size,
                named_after.st_mtime_ns,
                named_after.st_ctime_ns,
            ) != expected
        ):
            raise _audio_safety_error(
                f"{label} changed while it was being checked at {path}"
            )
    finally:
        os.close(descriptor)
    return path


def _private_audio_inputs(cache: SourceCache) -> _AudioSafetyInputs:
    """Resolve exact, source-confined private inventories without following links."""

    selected_root = cache.root.expanduser()
    try:
        named_root = selected_root.lstat()
    except FileNotFoundError as exc:
        raise _audio_safety_error(
            f"the private source cache is missing at {selected_root}"
        ) from exc
    if (
        not stat.S_ISDIR(named_root.st_mode)
        or stat.S_ISLNK(named_root.st_mode)
        or named_root.st_uid != os.getuid()
        or stat.S_IMODE(named_root.st_mode) != 0o700
    ):
        raise _audio_safety_error(
            "the private source cache must be an owner-only, mode-0700 "
            f"non-link directory at {selected_root}"
        )
    try:
        root = selected_root.resolve(strict=True)
    except OSError as exc:
        raise _audio_safety_error(
            f"the private source cache could not be resolved safely ({exc})"
        ) from exc
    if selected_root.absolute() != root:
        raise _audio_safety_error(
            f"the private source-cache path is not canonical at {selected_root}"
        )

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | \
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        root_fd = os.open(root, directory_flags)
    except OSError as exc:
        raise _audio_safety_error(
            f"the private source cache could not be opened safely ({exc})"
        ) from exc
    derived_fd: int | None = None
    try:
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_uid != os.getuid()
            or stat.S_IMODE(opened_root.st_mode) != 0o700
            or (opened_root.st_dev, opened_root.st_ino)
            != (named_root.st_dev, named_root.st_ino)
        ):
            raise _audio_safety_error(
                "the private source cache changed while it was being checked"
            )

        derived = root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE.parent
        try:
            named_derived = os.stat(
                derived.name, dir_fd=root_fd, follow_symlinks=False
            )
        except FileNotFoundError as exc:
            raise _audio_safety_error(
                f"the private derived-cache directory is missing at {derived}"
            ) from exc
        except OSError as exc:
            raise _audio_safety_error(
                f"the private derived-cache directory is unsafe at {derived} ({exc})"
            ) from exc
        if (
            not stat.S_ISDIR(named_derived.st_mode)
            or stat.S_ISLNK(named_derived.st_mode)
            or named_derived.st_uid != os.getuid()
            or stat.S_IMODE(named_derived.st_mode) != 0o700
        ):
            raise _audio_safety_error(
                "the private derived-cache directory must be an owner-only, "
                f"mode-0700 non-link directory at {derived}"
            )
        try:
            derived_fd = os.open(derived.name, directory_flags, dir_fd=root_fd)
        except OSError as exc:
            raise _audio_safety_error(
                f"the private derived-cache directory could not be opened safely ({exc})"
            ) from exc
        opened_derived = os.fstat(derived_fd)
        if (
            not stat.S_ISDIR(opened_derived.st_mode)
            or opened_derived.st_uid != os.getuid()
            or stat.S_IMODE(opened_derived.st_mode) != 0o700
            or (opened_derived.st_dev, opened_derived.st_ino)
            != (named_derived.st_dev, named_derived.st_ino)
            or derived.resolve(strict=True) != derived
        ):
            raise _audio_safety_error(
                "the private derived-cache directory escapes its source cache "
                f"or changed while it was being checked at {derived}"
            )

        fingerprints = _private_audio_inventory_file(
            derived_fd,
            root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE,
            "the source-audio fingerprint inventory",
            MAX_AUDIO_SOURCE_FINGERPRINTS_BYTES,
        )
        containment = _private_audio_inventory_file(
            derived_fd,
            root / AUDIO_SOURCE_CONTAINMENT_RELATIVE,
            "the source-audio containment inventory",
            MAX_AUDIO_SOURCE_CONTAINMENT_BYTES,
        )

        named_root_after = root.lstat()
        named_derived_after = os.stat(
            derived.name, dir_fd=root_fd, follow_symlinks=False
        )
        if (
            (named_root_after.st_dev, named_root_after.st_ino)
            != (opened_root.st_dev, opened_root.st_ino)
            or (named_derived_after.st_dev, named_derived_after.st_ino)
            != (opened_derived.st_dev, opened_derived.st_ino)
        ):
            raise _audio_safety_error(
                "the private audio safety cache changed while it was being checked"
            )
        return _AudioSafetyInputs(root, fingerprints, containment)
    finally:
        if derived_fd is not None:
            os.close(derived_fd)
        os.close(root_fd)


class Nfl2k5BuildService:
    """Build, independently verify once, and atomically publish a modded XISO."""

    def __init__(self, runner: BuildCommandRunner | None = None,
                 backend: Path = BACKEND,
                 python_executable: str = sys.executable) -> None:
        self.runner = runner or SubprocessBuildCommandRunner()
        self.backend = backend
        self.python_executable = python_executable

    def build(
        self,
        cache: SourceCache,
        project: Path | str | CanonicalProjectWriter,
        output_xiso: Path,
        progress: BuildProgress | None = None,
    ) -> BuildResult:
        """Publish one verified output, or leave the destination untouched.

        ``project`` may be an existing canonical provider JSON file or a
        ``StudioSession`` implementing ``write_canonical_project(destination)``.
        Session projects are materialized only inside private staging and are
        deleted after the build; no source-game bytes are placed in a project.
        """

        _emit(progress, BuildStage.PREPARING, 0, 4, "Preparing a safe build")
        source = self._validate_cache(cache)
        output = _new_output_path(output_xiso)
        _require_build_space(output.parent)
        backend, _ = _regular_file(self.backend, "2K5 ISO builder")
        stage = Path(tempfile.mkdtemp(
            prefix=f".{output.name}.2k5mod-", dir=output.parent))
        try:
            os.chmod(stage, 0o700)
            project_path, needs_audio_safety = self._project_path(project, stage)
            audio_safety = (
                _private_audio_inputs(cache) if needs_audio_safety else None
            )
            staged_xiso = stage / "modded.xiso"
            manifest = stage / "build-manifest.json"
            artifacts = stage / "build-artifacts"

            build_command = self._command(
                "build", backend, project_path, source, staged_xiso,
                manifest, artifacts, cache, audio_safety)
            _emit(progress, BuildStage.BUILDING, 1, 4, "Building the modded XISO")
            built = self.runner.run(build_command, ROOT)
            if built.returncode != 0:
                raise Nfl2k5BuildError(
                    "The modded XISO could not be built. " + _last_message(built)
                )

            verify_command = self._command(
                "verify", backend, project_path, source, staged_xiso,
                manifest, artifacts, cache, audio_safety)
            _emit(
                progress, BuildStage.VERIFYING, 2, 4,
                "Checking the finished XISO before it is published",
            )
            verified = self.runner.run(verify_command, ROOT)
            if verified.returncode != 0 or not any(
                line.startswith(EXPECTED_VERIFY_PREFIX)
                for line in verified.stdout.splitlines()
            ):
                detail = _last_message(verified)
                raise Nfl2k5BuildError(
                    "The build finished, but its safety check did not pass. "
                    f"No output was published. {detail}"
                )

            result, staged_identity = self._read_verified_result(
                manifest, staged_xiso, source, output)
            descriptor = os.open(
                staged_xiso, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                getattr(os, "O_CLOEXEC", 0))
            publish_attempted = False
            committed = False
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != staged_identity:
                    raise Nfl2k5BuildError(
                        "The staged XISO changed after verification; no output was published."
                    )
                os.fsync(descriptor)
                _emit(
                    progress, BuildStage.PUBLISHING, 3, 4,
                    "Publishing the verified XISO",
                )
                publish_attempted = True
                _rename_noreplace(staged_xiso, output)
                published = output.lstat()
                if not stat.S_ISREG(published.st_mode) or \
                        (published.st_dev, published.st_ino) != staged_identity:
                    raise Nfl2k5BuildError(
                        "The output pathname changed during publication."
                    )
                _fsync_directory(output.parent)
                committed = True
            finally:
                os.close(descriptor)
                if publish_attempted and not committed:
                    _unlink_if_identity(output, staged_identity)
                    try:
                        _fsync_directory(output.parent)
                    except OSError:
                        pass

            final = BuildResult(
                output_xiso=output,
                output_size=result.output_size,
                output_sha256=result.output_sha256,
                edit_count=result.edit_count,
                changed_byte_count=result.changed_byte_count,
            )
            _emit(progress, BuildStage.COMPLETE, 4, 4, "Modded XISO ready")
            return final
        except (Nfl2k5BuildError, OutputRefusedError, ValidationError):
            raise
        except OSError as exc:
            raise Nfl2k5BuildError(
                f"The build could not be completed safely: {exc}"
            ) from exc
        finally:
            # The stage name is returned by mkdtemp inside the already-resolved
            # output parent.  It contains no user-selected descendants.
            if stage.exists():
                shutil.rmtree(stage)

    @staticmethod
    def _validate_cache(cache: SourceCache) -> Path:
        record = cache.source
        if (
            not record.recognized
            or record.fingerprint_id != EXPECTED_FINGERPRINT
            or record.sha256 != SOURCE_SHA256
            or record.size != SOURCE_SIZE
            or record.kind != "xiso"
            or record.detected_game != "nfl2k5"
        ):
            raise ValidationError(
                "Load the supported USA retail NFL 2K5 Xbox XISO before building."
            )
        source, _ = _regular_file(
            Path(record.inspected_path), "NFL 2K5 source XISO", SOURCE_SIZE)
        _regular_file(cache.pack0, "private NFL 2K5 archive cache", PACK0_SIZE)
        _regular_file(
            cache.inventory, "private NFL 2K5 asset index", INVENTORY_SIZE)
        return source

    @staticmethod
    def _project_path(
        project: Path | str | CanonicalProjectWriter, stage: Path,
    ) -> tuple[Path, bool]:
        if isinstance(project, (str, os.PathLike)):
            source_path = Path(project)
        else:
            writer = getattr(project, "write_canonical_project", None)
            if not callable(writer):
                raise ValidationError(
                    "The open project cannot create a build recipe. "
                    "Save the project and try again."
                )
            destination = stage / "session-project-source.json"
            returned = writer(destination)
            if returned is not None and Path(returned) != destination:
                raise ValidationError(
                    "The open project wrote its build recipe to an unexpected location."
                )
            source_path = destination
        try:
            path, payload = _read_regular_snapshot(
                source_path, "mod project", MAX_PROJECT_BYTES)
            value = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("The mod project is not valid JSON") from exc
        canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if (
            payload != canonical
            or not isinstance(value, dict)
            or set(value) != {"schema", "purpose", "edits"}
            or value.get("schema") != PROJECT_SCHEMA
            or not isinstance(value.get("purpose"), str)
            or not value["purpose"]
            or not isinstance(value.get("edits"), list)
            or not value["edits"]
        ):
            raise ValidationError(
                "The mod project is not a canonical 2K5 Mod Studio build recipe."
            )
        needs_audio_safety = any(
            isinstance(edit, dict)
            and isinstance(edit.get("kind"), str)
            and edit["kind"] in AUDIO_EDIT_KINDS
            for edit in value["edits"]
        )

        # The backend resolves relative media names against the project file.
        # Make those references absolute before moving the recipe into private
        # staging, then hand both backend passes the exact same immutable copy.
        for edit in value["edits"]:
            if not isinstance(edit, dict):
                continue
            for field in ("clean_png", "mud_png", "png", "wav"):
                supplied_text = edit.get(field)
                if not isinstance(supplied_text, str) or not supplied_text:
                    continue
                supplied = Path(supplied_text)
                if not supplied.is_absolute():
                    edit[field] = os.fspath((path.parent / supplied).absolute())
        staged_payload = (
            json.dumps(value, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(staged_payload) > MAX_PROJECT_BYTES:
            raise ValidationError(
                "The mod project becomes unexpectedly large when its media "
                "paths are pinned for building."
            )
        staged = _write_private_snapshot(stage / "project.json", staged_payload)
        return staged, needs_audio_safety

    def _command(
        self, action: str, backend: Path, project: Path, source: Path,
        output: Path, manifest: Path, artifacts: Path, cache: SourceCache,
        audio_safety: _AudioSafetyInputs | None = None,
    ) -> tuple[str, ...]:
        command = (
            self.python_executable,
            str(backend),
            action,
            "--project", str(project),
            "--source-xiso", str(source),
            "--output-xiso", str(output),
            "--manifest", str(manifest),
            "--artifact-dir", str(artifacts),
            "--index", str(cache.pack0.resolve(strict=True)),
            "--inventory", str(cache.inventory.resolve(strict=True)),
        )
        if audio_safety is None:
            return command
        return command + (
            "--source-cache-root", str(audio_safety.source_cache_root),
            "--audio-exact-inventory", str(audio_safety.source_fingerprints),
            "--audio-containment-inventory", str(audio_safety.source_containment),
        )

    @staticmethod
    def _read_verified_result(
        manifest_path: Path, staged_xiso: Path, source: Path, final_output: Path,
    ) -> tuple[BuildResult, tuple[int, int]]:
        manifest, _ = _regular_file(
            manifest_path, "internal build receipt", maximum_size=512 * 1024 * 1024)
        staged, staged_info = _regular_file(
            staged_xiso, "staged modded XISO", expected_size=SOURCE_SIZE)
        try:
            value = json.loads(manifest.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise Nfl2k5BuildError(
                "The builder produced an unreadable internal receipt."
            ) from exc
        source_row = value.get("source", {}) if isinstance(value, dict) else {}
        output_row = value.get("output", {}) if isinstance(value, dict) else {}
        project_row = value.get("project", {}) if isinstance(value, dict) else {}
        patch_row = value.get("patch", {}) if isinstance(value, dict) else {}
        staged_identity = (staged_info.st_dev, staged_info.st_ino)
        if (
            value.get("schema") != BUILD_SCHEMA
            or source_row.get("path") != str(source)
            or source_row.get("sha256_before") != SOURCE_SHA256
            or source_row.get("sha256_after") != SOURCE_SHA256
            or source_row.get("opened_read_only") is not True
            or source_row.get("modified") is not False
            or output_row.get("xiso_path") != str(staged)
            or output_row.get("xiso_size") != SOURCE_SIZE
            or output_row.get("device") != staged_info.st_dev
            or output_row.get("inode") != staged_info.st_ino
            or not isinstance(output_row.get("xiso_sha256"), str)
            or len(output_row["xiso_sha256"]) != 64
            or type(project_row.get("edit_count")) is not int
            or type(patch_row.get("changed_byte_count")) is not int
        ):
            raise Nfl2k5BuildError(
                "The verified build receipt did not match the staged XISO. "
                "No output was published."
            )
        return BuildResult(
            output_xiso=final_output,
            output_size=SOURCE_SIZE,
            output_sha256=output_row["xiso_sha256"],
            edit_count=project_row["edit_count"],
            changed_byte_count=patch_row["changed_byte_count"],
        ), staged_identity
