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
import struct
import subprocess
import sys
import tempfile
import time
import warnings
from typing import Callable, Protocol, Sequence

from . import platform_compat
from .errors import ModEditorError, OutputRefusedError, ValidationError
from .nfl2k5_source_cache import (
    INVENTORY_SIZE,
    PACK0_SIZE,
    SOURCE_SHA256,
    SOURCE_SIZE,
    SourceCache,
)
from .platform_compat import fsync_directory, fsync_fd


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


# --------------------------------------------------------------------------
# Confining the backend: one process *group*, on two different process models.
#
# The guarantee is the same on every platform -- when the runner returns or
# raises, nothing the backend started is still running, so private staging can
# be removed without a stray writer underneath it -- but the kernel primitive
# that delivers it is not.
#
# POSIX launches the backend with ``start_new_session=True``, making it a
# session (and therefore process-group) leader whose PID doubles as the group
# id.  ``os.killpg`` then reaches every descendant even after the direct child
# has exited, and ``os.killpg(pg, 0)`` answers "is any of it still alive?".
#
# Windows has neither call: ``start_new_session`` is silently ignored there,
# ``os.killpg`` does not exist at all (calling it raises ``AttributeError``,
# which is what left the teardown below unable to stop anything), ``os.kill``
# is ``TerminateProcess`` and reaches exactly one process, and ``taskkill /T``
# walks parent PIDs, so it loses a child the moment its launcher exits -- which
# is precisely the case this code exists to catch.  The Win32 primitive with
# the same reach as a process group is a Job Object: a process assigned to one
# carries that job to everything it creates, ``TerminateJobObject`` stops all
# of them in a single call, and the job's ``ActiveProcesses`` counter answers
# the question ``killpg(pg, 0)`` answers on POSIX.  There is no group-wide
# graceful signal on Windows, so the job path is the analogue of the SIGKILL
# escalation, not of the SIGTERM that precedes it.
#
# ``mod_editor/apf_studio/audio_encoding.py`` and ``tools/apf_audio.py`` carry
# the same two-model helper for the APF audio encoder and decoder.  Those two
# are duplicates of each other because ``tools/`` modules are runnable
# standalone; this third copy exists because ``mod_editor.core`` must not
# depend on ``mod_editor.apf_studio``.  It is the *core* copy, shared
# core-to-core with :mod:`mod_editor.core.nfl2k5_stadium_cache`, whose worker
# teardown had the identical POSIX-only defect.
# --------------------------------------------------------------------------

PROCESS_POLL_SECONDS = 0.05
# The POSIX teardown below has always given the backend three seconds to die
# between TERM and KILL; the Windows path reuses that same budget so neither
# platform waits longer than the other for a stop it already requested.
PROCESS_STOP_GRACE_SECONDS = 3.0

# JOBOBJECTINFOCLASS.JobObjectBasicAccountingInformation, and the byte offset
# of ``ActiveProcesses`` within JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four
# 8-byte LARGE_INTEGERs, then the DWORDs TotalPageFaultCount and
# TotalProcesses.  The struct is 48 bytes; the buffer is oversized on purpose.
_WINDOWS_JOB_BASIC_ACCOUNTING = 1
_WINDOWS_ACTIVE_PROCESSES_OFFSET = 40
_WINDOWS_ACCOUNTING_BYTES = 64

# CreateProcess's CREATE_SUSPENDED.  A child started with it is frozen before it
# runs a single instruction, so it can be sealed into the job object *before* it
# is able to spawn a descendant -- closing the race a job assigned only after
# launch leaves open.  It is resumed through ntdll's ``NtResumeProcess`` once the
# assignment is done; see :func:`adopt_process_group`.  ``STATUS_SUCCESS`` is
# that call's "every thread resumed" NTSTATUS.
WINDOWS_CREATE_SUSPENDED = 0x00000004
_WINDOWS_STATUS_SUCCESS = 0


class WindowsProcessGroup:
    """A Job Object standing in for the POSIX session the backend cannot have.

    Every entry point fails soft (returns ``None``/``False``) rather than
    raising, because this type is used from teardown paths where raising would
    replace the error the caller is already reporting.  A group that could not
    be established is reported as such so the caller can fall back to the direct
    child and still say honestly whether it stopped.
    """

    def __init__(self, kernel32: "ctypes.CDLL", handle: int) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @classmethod
    def create(cls) -> "WindowsProcessGroup | None":
        kernel32 = _windows_job_api()
        if kernel32 is None:
            return None
        try:
            handle = kernel32.CreateJobObjectW(None, None)
        except OSError:
            return None
        if not handle:
            return None
        return cls(kernel32, handle)

    def adopt(self, process: "subprocess.Popen[str] | subprocess.Popen[bytes]") -> bool:
        """Put *process* -- and so everything it later starts -- in the job."""

        handle = getattr(process, "_handle", None)
        if self._handle is None or handle is None:
            return False
        try:
            return bool(
                self._kernel32.AssignProcessToJobObject(self._handle, int(handle))
            )
        except (OSError, TypeError, ValueError):
            return False

    def active_process_count(self) -> int | None:
        """How many processes the job still holds, or ``None`` if unreadable.

        The Win32 counterpart to ``os.killpg(pg, 0)`` -- but returned as a
        *count*, not a bool, so the stop path can tell three states apart that a
        boolean would collapse: ``0`` (the group has stopped), a positive number
        (a genuine, observed survivor), and ``None`` -- the accounting query
        itself failed.  A failed query is *not* evidence of a survivor; reporting
        it as one is exactly the false "left a background process" this returns
        ``None`` to prevent.  Callers decide what an unreadable count means from
        evidence they can trust, such as whether the direct child is still alive.
        """

        if self._handle is None:
            return 0
        buffer = ctypes.create_string_buffer(_WINDOWS_ACCOUNTING_BYTES)
        try:
            queried = self._kernel32.QueryInformationJobObject(
                self._handle,
                _WINDOWS_JOB_BASIC_ACCOUNTING,
                buffer,
                _WINDOWS_ACCOUNTING_BYTES,
                None,
            )
        except OSError:
            return None
        if not queried:
            return None
        (active_processes,) = struct.unpack_from(
            "<I", buffer.raw, _WINDOWS_ACTIVE_PROCESSES_OFFSET
        )
        return active_processes

    def terminate(self) -> bool:
        """``TerminateJobObject`` the whole group; report whether it was accepted.

        A ``True`` result means the kernel took the request to end every process
        in the job at once.  It does not promise they have already left the
        accounting count -- forced termination is not instantaneous -- which is
        why the caller confirms the group actually drained afterwards.
        """

        if self._handle is None:
            return False
        try:
            return bool(self._kernel32.TerminateJobObject(self._handle, 1))
        except OSError:
            return False

    def close(self) -> None:
        """Release the job handle.  Idempotent, so double-close is harmless."""

        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            self._kernel32.CloseHandle(handle)
        except OSError:
            pass


def _windows_job_api() -> "ctypes.CDLL | None":
    """Load kernel32's job entry points with argtypes applied, or ``None``.

    Leaving ``argtypes`` unset would let ctypes truncate 64-bit ``HANDLE``
    values to a C ``int``, which is the class of bug that silently terminates
    the wrong thing -- or nothing.
    """

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    handle = ctypes.c_void_p
    boolean = ctypes.c_int
    try:
        kernel32 = windll.kernel32
        kernel32.CreateJobObjectW.argtypes = [handle, ctypes.c_wchar_p]
        kernel32.CreateJobObjectW.restype = handle
        kernel32.AssignProcessToJobObject.argtypes = [handle, handle]
        kernel32.AssignProcessToJobObject.restype = boolean
        kernel32.TerminateJobObject.argtypes = [handle, ctypes.c_uint]
        kernel32.TerminateJobObject.restype = boolean
        kernel32.QueryInformationJobObject.argtypes = [
            handle,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.QueryInformationJobObject.restype = boolean
        kernel32.CloseHandle.argtypes = [handle]
        kernel32.CloseHandle.restype = boolean
    except (AttributeError, OSError):
        # A kernel32 without these exports is not a Windows we can confine a
        # process on; degrade to the direct child rather than failing the build.
        return None
    return kernel32


def _windows_ntdll_resume() -> "ctypes.CDLL | None":
    """ntdll's ``NtResumeProcess`` with argtypes applied, or ``None``.

    ``NtResumeProcess`` restarts every thread of a process from its handle
    alone, which is the one thing a CREATE_SUSPENDED child needs and the one
    thing ``subprocess`` cannot hand back: it closes the primary-thread handle
    ``CreateProcess`` returned before the constructor even finishes.  The call is
    absent from the Win32 headers but has been a stable ntdll export for two
    decades; if it is ever missing we simply do not create children suspended.
    """

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    try:
        ntdll = windll.ntdll
        ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
        ntdll.NtResumeProcess.restype = ctypes.c_long
    except (AttributeError, OSError):
        return None
    return ntdll


def use_suspended_launch() -> bool:
    """Whether a child can be created suspended and confined before it runs.

    True only when *both* primitives the sequence needs are present: the job API
    (something to assign the frozen child to) and ``NtResumeProcess`` (a way to
    start it again).  Missing either, creating the child suspended would risk one
    that can never run, so the caller launches normally and assigns the job the
    instant the child starts instead -- the slightly racier fallback path.
    Always ``False`` off Windows, so the POSIX launch keeps ``creationflags=0``.
    """

    if not platform_compat.IS_WINDOWS:
        return False
    return _windows_job_api() is not None and _windows_ntdll_resume() is not None


def _resume_suspended_process(
    process: "subprocess.Popen[str] | subprocess.Popen[bytes]",
) -> bool:
    """Resume a child created with CREATE_SUSPENDED; report whether it took.

    Resumes through the process handle ``subprocess`` retains, so it needs no
    thread handle of its own.  A ``False`` result means the child is stuck
    frozen and unusable, and the caller must not leave it that way.
    """

    ntdll = _windows_ntdll_resume()
    handle = getattr(process, "_handle", None)
    if ntdll is None or handle is None:
        return False
    try:
        status = ntdll.NtResumeProcess(int(handle))
    except (OSError, TypeError, ValueError):
        return False
    return status == _WINDOWS_STATUS_SUCCESS


def adopt_process_group(
    process: "subprocess.Popen[str] | subprocess.Popen[bytes]",
    *,
    was_suspended: bool = False,
) -> WindowsProcessGroup | None:
    """Give *process* a group with POSIX-session reach, where one is needed.

    POSIX already has it: ``start_new_session=True`` did the work at launch, so
    this returns ``None`` there and nothing about the POSIX path changes.
    Windows needs the job created and the child assigned to it.  When the child
    was created suspended (``was_suspended``), it is sealed into the job *before*
    it can run -- so no descendant it later spawns can escape a job that would
    otherwise have been assigned a beat too late -- and then, unconditionally,
    resumed: a suspended child must be started again whether or not confinement
    succeeded, or it hangs forever.  A child that cannot be resumed is unusable,
    so it is killed and reported as unconfined rather than left frozen.
    """

    if not platform_compat.IS_WINDOWS:
        return None
    group = WindowsProcessGroup.create()
    assigned = group is not None and group.adopt(process)
    if was_suspended and not _resume_suspended_process(process):
        if group is not None:
            group.close()
        try:
            process.kill()
        except OSError:
            pass
        return None
    if group is None or not assigned:
        if group is not None:
            group.close()
        return None
    return group


def _drain_windows_job(group: WindowsProcessGroup) -> int | None:
    """Wait, bounded, for an already-terminated job to empty; return its count.

    Polls ``ActiveProcesses`` until it reads zero or the grace window closes.
    If the window closes with survivors still counted, ``TerminateJobObject`` is
    issued once more -- catching a descendant that was mid-spawn when the first
    sweep passed over the group -- and the group is given one more bounded window
    to drain.  Returns the final count, or ``None`` when the count could not be
    read at all (never mistaken by the caller for a survivor).
    """

    def settle() -> int | None:
        deadline = time.monotonic() + PROCESS_STOP_GRACE_SECONDS
        while True:
            count = group.active_process_count()
            if count == 0:
                return 0
            if time.monotonic() >= deadline:
                return count
            time.sleep(PROCESS_POLL_SECONDS)

    count = settle()
    if count is not None and count > 0:
        group.terminate()
        count = settle()
    return count


def stop_windows_process_group(
    process: "subprocess.Popen[str] | subprocess.Popen[bytes]",
    group: WindowsProcessGroup | None,
) -> bool:
    """Stop a child and its descendants through the job object; report success.

    Returns ``True`` when the group is confirmed stopped and ``False`` only on
    *positive evidence* of a survivor: the job's own active-process count, read
    after ``TerminateJobObject`` and given a bounded window to fall to zero, or
    -- when that count cannot be read at all -- the direct child still being
    alive.  A group that genuinely stopped, or one whose accounting merely could
    not be queried while the child it led is already gone, is never misreported
    as a survivor.  The bool is returned rather than raised so each caller can
    surface its own product error; the job handle is always released here.
    """

    if group is None:
        # No job: only the direct child is reachable.  Stop it and report on the
        # same evidence the POSIX path uses -- an observed survivor, never merely
        # a group that could not be observed.
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return process.poll() is not None
    try:
        group.terminate()
        try:
            process.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            pass
        count = _drain_windows_job(group)
        # Positive evidence of a survivor is either the job still counting one
        # after it was terminated and drained, or -- when the count is
        # unreadable -- the direct child still being alive.  Everything else
        # (a drained group; an unreadable count with the child already gone) is
        # not a survivor: TerminateJobObject was issued regardless, so refusing
        # to invent one is what keeps a stopped group from being misreported.
        survived = count > 0 if count is not None else process.poll() is None
        return not survived
    finally:
        group.close()


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
        suspended = use_suspended_launch()
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
                # POSIX only; silently ignored on Windows, where the job object
                # adopted below supplies the same reach.
                start_new_session=True,
                # Windows only (``0`` -- the default -- everywhere else, so the
                # POSIX launch is byte-for-byte the one it always was): freeze
                # the child so it is sealed into the job before it can spawn a
                # descendant; ``adopt_process_group`` resumes it.
                creationflags=WINDOWS_CREATE_SUSPENDED if suspended else 0,
            )
        except OSError as exc:
            raise Nfl2k5BuildError(
                "2K5 Mod Studio could not start its ISO builder. "
                f"Check that Python is installed and try again ({exc})."
            ) from exc
        group = adopt_process_group(process, was_suspended=suspended)
        try:
            stdout, stderr = process.communicate()
        except BaseException:
            # The backend owns only paths below our staging directory.  Stop its
            # whole process group before that directory is removed.
            self._stop_process_group(process, group)
            raise
        # The backend has exited and its pipes are drained.  POSIX leaves the
        # group alone on this path and always has; Windows has one extra thing
        # to do -- release the job handle it would otherwise leak.
        if group is not None:
            group.close()
        return CommandResult(fixed, process.returncode, stdout, stderr)

    @staticmethod
    def _stop_process_group(
        process: subprocess.Popen[str],
        group: WindowsProcessGroup | None = None,
    ) -> None:
        if platform_compat.IS_WINDOWS:
            # Deliberately ahead of the "direct child already exited" shortcut
            # below: on Windows the job can still hold descendants the exited
            # launcher started, and those are what would keep writing into the
            # staging directory we are about to remove.
            if not stop_windows_process_group(process, group):
                raise Nfl2k5BuildError(
                    "The ISO builder left a background process that could not be "
                    "stopped. Sign out or restart Windows before building again; "
                    "no output was published."
                )
            return
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
        descriptor = os.open(resolved, flags | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise ValidationError(f"{label} could not be opened safely: {resolved}") from exc
    try:
        # ``named`` and ``named_after`` are PATH stats; ``opened`` and
        # ``opened_after`` are FD stats of the descriptor.  Windows reaches
        # st_ctime through a different Win32 information class for each family,
        # so the two disagree for a file nothing touched.  The path/path
        # comparison therefore keeps the change time on every platform, while
        # the two path/fd comparisons drop it where it cannot be compared --
        # hence two spellings of the ``named`` fingerprint.
        expected = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
        )
        expected_cross = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            *platform_compat.change_time_identity(named),
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                *platform_compat.change_time_identity(opened),
            ) != expected_cross
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
                *platform_compat.change_time_identity(opened_after),
            ) != expected_cross
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
        descriptor = os.open(path, flags | getattr(os, "O_BINARY", 0), 0o600)
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
            or stat.S_IMODE(opened.st_mode) != platform_compat.private_file_mode()
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


def _fsync_directory(path: Path) -> bool:
    """Commit the directory entry a publish just created, and report whether it held.

    Delegates to :func:`platform_compat.fsync_directory`, which performs the POSIX
    ``O_RDONLY | O_DIRECTORY`` flush this used to open by hand and returns ``True``,
    and on Windows now attempts ``FlushFileBuffers`` on a directory write handle --
    returning ``True`` when it genuinely committed and ``False`` only when the
    account cannot obtain that handle.  The bool is now *returned* rather than
    discarded, so the commit path can surface a non-durable Windows publish instead
    of continuing as if committed; the rollback path legitimately ignores it (it is
    undoing a publish, not making one durable).  The published file itself is always
    flushed separately, so a Windows ``False`` costs the directory entry's
    crash-durability, not the payload's.
    """

    return fsync_directory(path)


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

    Linux supplies renameat2(RENAME_NOREPLACE), the exact transaction needed
    here; a hard-link transaction is retained as a fallback for older
    kernels/libcs.  Off Linux the same guarantee comes from
    :func:`platform_compat.publish_no_replace` -- macOS ``renamex_np(RENAME_EXCL)``
    or POSIX link+unlink, and on Windows ``os.rename``, which natively refuses an
    existing destination.  Routing there is not a convenience: ``ctypes.CDLL(None)``
    raises ``TypeError`` on Windows, so the libc probe below cannot even be
    attempted, and its ``_link_then_unlink`` fallback would call ``os.link``,
    which Windows also lacks.
    """

    if not platform_compat.IS_LINUX:
        try:
            platform_compat.publish_no_replace(source, destination)
        except FileExistsError:
            raise OutputRefusedError(
                "The output was created by another process and was not "
                f"overwritten: {destination}"
            ) from None
        except OSError as exc:
            raise Nfl2k5BuildError(
                "The verified ISO could not be moved into the selected output "
                f"folder: {exc}"
            ) from exc
        return

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
    directory: platform_compat.DirHandle,
    path: Path,
    label: str,
    maximum_size: int,
) -> Path:
    """Validate one exact owner-only file beneath an already-pinned directory."""

    try:
        named = directory.stat(path.name, follow=False)
    except FileNotFoundError as exc:
        raise _audio_safety_error(f"{label} is missing at {path}") from exc
    except OSError as exc:
        raise _audio_safety_error(
            f"{label} could not be inspected safely at {path} ({exc})"
        ) from exc
    if (
        not stat.S_ISREG(named.st_mode)
        or stat.S_ISLNK(named.st_mode)
        or not platform_compat.is_owned_by_current_user(named, path=path)
        or named.st_nlink != 1
        or stat.S_IMODE(named.st_mode) != platform_compat.private_file_mode()
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
        descriptor = directory.open(path.name, flags | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise _audio_safety_error(
            f"{label} could not be opened safely at {path} ({exc})"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        try:
            named_after = directory.stat(path.name, follow=False)
        except OSError as exc:
            raise _audio_safety_error(
                f"{label} changed while it was being checked at {path}"
            ) from exc
        # ``named`` and ``named_after`` are DirHandle PATH stats; ``opened`` is
        # an FD stat.  The path/path comparison keeps the change time on every
        # platform; the path/fd one drops it where Windows cannot compare the
        # two calls (platform_compat.supports_change_time_identity).
        expected = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            named.st_ctime_ns,
        )
        expected_cross = (
            named.st_dev,
            named.st_ino,
            named.st_size,
            named.st_mtime_ns,
            *platform_compat.change_time_identity(named),
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or not platform_compat.is_owned_by_current_user(
                opened, fd=descriptor
            )
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != platform_compat.private_file_mode()
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                *platform_compat.change_time_identity(opened),
            ) != expected_cross
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
        or not platform_compat.is_owned_by_current_user(
            named_root, path=selected_root
        )
        # The mode is the number this platform genuinely produces for a private
        # directory -- 0o700 on POSIX, 0o777 on Windows -- so the equality below
        # is an honest shape check on both.  On Windows it is only that: every
        # directory reads 0o777 and the number confers no privacy, so the
        # owner-only guarantee is asked of the DACL instead (a current-user-owned
        # directory with an Everyone/Users ACE is refused).  On POSIX
        # is_private_directory_mode is the historical "no group or other access"
        # test, already implied by the exact-mode equality, so the decision Linux
        # and macOS reach is unchanged.
        or stat.S_IMODE(named_root.st_mode) != platform_compat.private_directory_mode()
        or not platform_compat.is_private_directory_mode(
            named_root, path=selected_root
        )
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
    if not platform_compat.is_canonical_absolute_path(selected_root, root):
        raise _audio_safety_error(
            f"the private source-cache path is not canonical at {selected_root}"
        )

    try:
        root_handle = platform_compat.open_dir_handle(root)
    except OSError as exc:
        raise _audio_safety_error(
            f"the private source cache could not be opened safely ({exc})"
        ) from exc
    derived_handle: platform_compat.DirHandle | None = None
    try:
        opened_root = root_handle.fstat()
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or not root_handle.is_owned_by_current_user(opened_root)
            # Mode for shape on both platforms; DACL for the owner-only
            # guarantee on Windows, read through the realpath this handle is
            # pinned to (POSIX keeps the mode-bit answer it always gave).
            or stat.S_IMODE(opened_root.st_mode) != platform_compat.private_directory_mode()
            or not platform_compat.is_private_directory_mode(
                opened_root, path=root_handle.realpath
            )
            or (opened_root.st_dev, opened_root.st_ino)
            != (named_root.st_dev, named_root.st_ino)
        ):
            raise _audio_safety_error(
                "the private source cache changed while it was being checked"
            )

        derived = root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE.parent
        try:
            named_derived = root_handle.stat(derived.name, follow=False)
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
            or not platform_compat.is_owned_by_current_user(
                named_derived, path=derived
            )
            # Mode for shape on both platforms; DACL for the owner-only
            # guarantee on Windows (POSIX keeps the mode-bit answer it always
            # gave, already implied by the exact-mode equality above).
            or stat.S_IMODE(named_derived.st_mode) != platform_compat.private_directory_mode()
            or not platform_compat.is_private_directory_mode(
                named_derived, path=derived
            )
        ):
            raise _audio_safety_error(
                "the private derived-cache directory must be an owner-only, "
                f"mode-0700 non-link directory at {derived}"
            )
        try:
            derived_handle = root_handle.open_dir(derived.name)
        except OSError as exc:
            raise _audio_safety_error(
                f"the private derived-cache directory could not be opened safely ({exc})"
            ) from exc
        opened_derived = derived_handle.fstat()
        if (
            not stat.S_ISDIR(opened_derived.st_mode)
            or not derived_handle.is_owned_by_current_user(opened_derived)
            # Mode for shape on both platforms; DACL for the owner-only
            # guarantee on Windows, read through the realpath this handle is
            # pinned to (POSIX keeps the mode-bit answer it always gave).
            or stat.S_IMODE(opened_derived.st_mode) != platform_compat.private_directory_mode()
            or not platform_compat.is_private_directory_mode(
                opened_derived, path=derived_handle.realpath
            )
            or (opened_derived.st_dev, opened_derived.st_ino)
            != (named_derived.st_dev, named_derived.st_ino)
            or derived.resolve(strict=True) != derived
        ):
            raise _audio_safety_error(
                "the private derived-cache directory escapes its source cache "
                f"or changed while it was being checked at {derived}"
            )

        fingerprints = _private_audio_inventory_file(
            derived_handle,
            root / AUDIO_SOURCE_FINGERPRINTS_RELATIVE,
            "the source-audio fingerprint inventory",
            MAX_AUDIO_SOURCE_FINGERPRINTS_BYTES,
        )
        containment = _private_audio_inventory_file(
            derived_handle,
            root / AUDIO_SOURCE_CONTAINMENT_RELATIVE,
            "the source-audio containment inventory",
            MAX_AUDIO_SOURCE_CONTAINMENT_BYTES,
        )

        named_root_after = root.lstat()
        named_derived_after = root_handle.stat(derived.name, follow=False)
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
        if derived_handle is not None:
            derived_handle.close()
        root_handle.close()


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
            # O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_BINARY on POSIX, unchanged.
            # This descriptor is held across the publish on purpose -- it pins
            # the exact inode the manifest was verified against, which is the
            # only reason the post-publish (st_dev, st_ino) comparison below
            # proves anything -- and Windows refuses to rename a file that has
            # an open handle without FILE_SHARE_DELETE, which the CRT's open()
            # never grants.  The helper grants it there and nothing else; the
            # descriptor's lifetime and access rights are identical on every
            # platform.  Closing it early instead would trade the held-descriptor
            # proof for a name lookup.
            descriptor = platform_compat.open_existing_for_publish(staged_xiso)
            publish_attempted = False
            committed = False
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != staged_identity:
                    raise Nfl2k5BuildError(
                        "The staged XISO changed after verification; no output was published."
                    )
                # Flush the exact inode just pinned above.  On POSIX this is the
                # same ``os.fsync(descriptor)`` it always was; on Windows, where
                # a read-only handle cannot be flushed, the helper reopens by
                # path and re-checks ``(st_dev, st_ino)`` against this very
                # descriptor, so the "verified inode" guarantee is preserved
                # rather than traded away for portability.
                fsync_fd(descriptor, path=staged_xiso)
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
                if not _fsync_directory(output.parent):
                    # POSIX always commits; a False is Windows telling us it could
                    # not flush the directory entry.  Surface the missing
                    # crash-durability rather than returning as if fully committed.
                    warnings.warn(
                        "nfl2k5_build_service: the published XISO's directory entry "
                        "could not be flushed to stable storage on this platform; a "
                        "crash before the OS flushes it on its own could lose the "
                        "published filename",
                        RuntimeWarning,
                        stacklevel=2,
                    )
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
