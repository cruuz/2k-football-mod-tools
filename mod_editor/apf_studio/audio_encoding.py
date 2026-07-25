"""Private, bounded PCM16-to-XMA1 encoding for APF audio slots.

The product does not ship an XMA1 encoder.  This module adapts an executable
selected by the user and invokes it with an argv vector (never a shell).  The
encoder receives only a canonical PCM16 WAV in a private temporary directory,
and its output remains temporary until the APF session's existing exact-slot
and source-packet validators authorize it.

The public template writer generates silence from retail-free target-shape
metadata and never reads loaded-game audio.  The encoder route treats its WAV
as unclassified user input and makes no claim about that input's provenance.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import signal
import stat
import string
import struct
import subprocess
import tempfile
import time
from typing import Callable, Mapping

from mod_editor.core import platform_compat


PCM16_TEMPLATE_SCHEMA = "apf2k8_audio_pcm16_template/v1"
EXTERNAL_XMA1_ENCODER_SCHEMA = "apf2k8_external_xma1_encoder/v1"
MAX_PCM_DATA_BYTES = 512 * 1024 * 1024
MAX_WAV_OVERHEAD_BYTES = 1024 * 1024
MAX_ENCODER_OUTPUT_OVERHEAD_BYTES = 1024 * 1024
MAX_ENCODER_LOG_BYTES = 1024 * 1024
MAX_ENCODER_ARGUMENTS = 64
MAX_ENCODER_ARGUMENT_LENGTH = 4096
MAX_EXECUTABLE_BYTES = 1024 * 1024 * 1024
MIN_TIMEOUT_SECONDS = 0.05
MAX_TIMEOUT_SECONDS = 30 * 60
PROCESS_POLL_SECONDS = 0.05
PROCESS_STOP_GRACE_SECONDS = 2.0
COPY_BLOCK_BYTES = 1024 * 1024

# Every descriptor this module opens carries audio or diagnostic *bytes*.  On
# Windows ``os.open`` defaults to the CRT's text mode, which rewrites CRLF and
# stops reading at a 0x1A byte -- silent corruption of exactly those payloads.
# ``O_BINARY`` does not exist on POSIX, where there is no translation to
# disable, so this resolves to 0 and the POSIX flags are unchanged.
_O_BINARY = getattr(os, "O_BINARY", 0)

Progress = Callable[[str, int, int], None]
CancelRequested = Callable[[], bool]


class AudioEncodingError(ValueError):
    """A user-correctable PCM template or encoder configuration error."""


class AudioEncodingCancelled(AudioEncodingError):
    """The user cancelled before an encoded result could be authorized."""


@dataclass(frozen=True)
class Pcm16Target:
    """Retail-free authoring shape for one fixed APF audio allocation."""

    channels: int
    sample_rate: int
    frame_count: int
    encoded_size: int

    @property
    def block_align(self) -> int:
        return self.channels * 2

    @property
    def data_size(self) -> int:
        return self.frame_count * self.block_align

    @property
    def wav_size(self) -> int:
        return 44 + self.data_size


@dataclass(frozen=True)
class Pcm16TemplateReceipt:
    """Receipt for one atomically published silence authoring template."""

    path: Path
    byte_size: int
    sha256: str
    channels: int
    sample_rate: int
    frame_count: int
    encoded_size: int
    schema: str = PCM16_TEMPLATE_SCHEMA
    contains_retail_audio: bool = False


@dataclass(frozen=True)
class ExternalEncodingResult:
    """Temporary encoder output held in memory for the APF slot validator."""

    xma1_riff: bytes
    receipt: Mapping[str, object]


@dataclass(frozen=True)
class _FileIdentity:
    path: Path
    device: int
    inode: int
    size: int
    mode: int
    mtime_ns: int
    # Captured by lstat and re-checked by lstat of the same pathname
    # (:func:`_validate_tool_path` and :func:`_require_unchanged_tool`), so both
    # sides of the comparison are path stats.  Two path stats agree on
    # st_ctime_ns on every platform Windows included, so the field is kept as a
    # plain int and compared everywhere.
    ctime_ns: int


@dataclass(frozen=True)
class _PcmDataLocation:
    descriptor: int
    data_offset: int
    data_size: int
    # Always the full six-field fingerprint: this is captured from an fstat and
    # re-checked against an fstat of the same descriptor, never against a path
    # stat, so no component is dropped on any platform.
    source_identity: tuple[int, int, int, int, int, int]


def _noop(_stage: str, _completed: int, _total: int) -> None:
    return None


def _not_cancelled(cancel_requested: CancelRequested | None) -> None:
    if cancel_requested is not None:
        try:
            cancelled = cancel_requested()
        except Exception as exc:
            raise AudioEncodingError(
                f"Could not check whether audio encoding was cancelled: {exc}"
            ) from exc
        if cancelled:
            raise AudioEncodingCancelled(
                "Audio encoding was cancelled; no project edit was staged"
            )


def validate_pcm16_target(target: Pcm16Target) -> Pcm16Target:
    """Fail closed unless a target can be represented as a bounded RIFF WAV."""

    if not isinstance(target, Pcm16Target):
        raise AudioEncodingError("The APF audio target has the wrong type")
    if type(target.channels) is not int or target.channels not in (1, 2):
        raise AudioEncodingError(
            "This XMA1 authoring route supports exactly one or two PCM channels"
        )
    if (
        type(target.sample_rate) is not int
        or not 1 <= target.sample_rate <= 384_000
    ):
        raise AudioEncodingError("The APF audio target sample rate is invalid")
    if type(target.frame_count) is not int or target.frame_count <= 0:
        raise AudioEncodingError("The APF audio target frame count is invalid")
    if (
        type(target.encoded_size) is not int
        or target.encoded_size <= 0
        or target.encoded_size > 64 * 1024 * 1024
        or target.encoded_size % 0x800
    ):
        raise AudioEncodingError(
            "The APF XMA1 target must be a nonempty 0x800-byte packet allocation"
        )
    if target.data_size > MAX_PCM_DATA_BYTES:
        raise AudioEncodingError(
            "This PCM template would exceed the 512 MiB authoring safety limit"
        )
    if target.wav_size - 8 > 0xFFFFFFFF:
        raise AudioEncodingError("This PCM template is too large for RIFF WAV")
    return target


def _pcm16_header(target: Pcm16Target) -> bytes:
    target = validate_pcm16_target(target)
    byte_rate = target.sample_rate * target.block_align
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", target.wav_size - 8),
            b"WAVEfmt ",
            struct.pack("<I", 16),
            struct.pack(
                "<HHIIHH",
                1,
                target.channels,
                target.sample_rate,
                byte_rate,
                target.block_align,
                16,
            ),
            b"data",
            struct.pack("<I", target.data_size),
        )
    )


def _require_destination(destination: Path) -> Path:
    if not isinstance(destination, Path):
        raise AudioEncodingError("PCM WAV destination must be a Path")
    destination = destination.expanduser()
    if destination.suffix.casefold() != ".wav" or not destination.name:
        raise AudioEncodingError("PCM authoring template must end in .wav")
    if destination.exists() or destination.is_symlink():
        raise AudioEncodingError(
            "PCM authoring template destination already exists; choose a new file"
        )
    try:
        parent = destination.parent.lstat()
    except OSError as exc:
        raise AudioEncodingError(
            f"PCM authoring template folder is unavailable: {exc}"
        ) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise AudioEncodingError(
            "PCM authoring template folder must be a real directory, not a link"
        )
    return destination


def export_pcm16_template(
    destination: Path,
    target: Pcm16Target,
    *,
    progress: Progress | None = None,
    cancel_requested: CancelRequested | None = None,
) -> Pcm16TemplateReceipt:
    """Write one exact-length silence WAV atomically and without retail bytes."""

    target = validate_pcm16_target(target)
    destination = _require_destination(destination)
    report = progress or _noop
    _not_cancelled(cancel_requested)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".creating", dir=destination.parent
    )
    temporary = Path(temporary_name)
    linked = False
    digest = hashlib.sha256()
    completed = 0
    try:
        with os.fdopen(descriptor, "wb") as stream:
            header = _pcm16_header(target)
            stream.write(header)
            digest.update(header)
            zeroes = b"\0" * min(COPY_BLOCK_BYTES, target.data_size)
            while completed < target.data_size:
                _not_cancelled(cancel_requested)
                block_size = min(len(zeroes), target.data_size - completed)
                block = zeroes[:block_size]
                stream.write(block)
                digest.update(block)
                completed += block_size
                report("Writing exact PCM16 silence template", completed, target.data_size)
            stream.flush()
            os.fsync(stream.fileno())
        _not_cancelled(cancel_requested)
        if temporary.stat().st_size != target.wav_size:
            raise AudioEncodingError("PCM authoring template size check failed")
        try:
            os.link(temporary, destination)
            linked = True
        except FileExistsError as exc:
            raise AudioEncodingError(
                "PCM authoring template destination was created by another process"
            ) from exc
        except OSError as exc:
            raise AudioEncodingError(
                f"Could not publish the PCM authoring template: {exc}"
            ) from exc
        temporary.unlink()
        report("Exact PCM16 silence template ready", target.data_size, target.data_size)
        return Pcm16TemplateReceipt(
            path=destination,
            byte_size=target.wav_size,
            sha256=digest.hexdigest(),
            channels=target.channels,
            sample_rate=target.sample_rate,
            frame_count=target.frame_count,
            encoded_size=target.encoded_size,
        )
    except BaseException:
        temporary.unlink(missing_ok=True)
        if linked:
            destination.unlink(missing_ok=True)
        raise


def _source_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """The full fingerprint, for comparing two stats of the *same* family.

    Both sides must come from ``os.fstat`` (or both from a path stat).  The
    change time is included unconditionally, because two stats of the same
    family agree on it on every platform -- so a metadata-only edit is still
    caught here on Windows.  For a path-stat-against-fd-stat comparison use
    :func:`_cross_stat_identity` instead.
    """

    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _cross_stat_identity(info: os.stat_result) -> tuple[int, ...]:
    """:func:`_source_identity` minus the field a path stat and an fd stat disagree on.

    Only for the comparisons that put a path stat on one side and an ``os.fstat``
    on the other.  Windows reaches ``st_ctime`` through a different Win32
    information class for each, so the two disagree for a file nothing touched
    and the field cannot be compared across that boundary; it is dropped there
    (see :func:`platform_compat.supports_change_time_identity`) and kept on
    POSIX.  Everything else -- ``st_dev``/``st_ino`` identity, ``st_size``,
    ``st_mtime_ns`` and ``st_nlink`` -- is compared on every platform, so a
    swapped, relinked or rewritten file is still caught; what is lost on Windows
    at these sites, and only these, is the metadata-only-change signal.
    """

    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        *platform_compat.change_time_identity(info),
        info.st_nlink,
    )


def _read_at(descriptor: int, count: int, offset: int, label: str) -> bytes:
    try:
        data = platform_compat.pread(descriptor, count, offset)
    except OSError as exc:
        raise AudioEncodingError(f"Could not read {label}: {exc}") from exc
    if len(data) != count:
        raise AudioEncodingError(f"The {label} is truncated")
    return data


def _open_pcm_data(source: Path, target: Pcm16Target) -> _PcmDataLocation:
    """Pin and parse one bounded PCM WAV without following its final link."""

    if not isinstance(source, Path):
        raise AudioEncodingError("PCM replacement must be a Path")
    source = source.expanduser()
    try:
        supplied = source.lstat()
    except OSError as exc:
        raise AudioEncodingError(f"Could not open the PCM replacement: {exc}") from exc
    maximum = target.wav_size + MAX_WAV_OVERHEAD_BYTES
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
    ):
        raise AudioEncodingError(
            "The PCM replacement must be one private regular .wav file, not a link"
        )
    if not 44 <= supplied.st_size <= maximum:
        raise AudioEncodingError(
            "The PCM replacement is empty or larger than this exact target allows"
        )
    try:
        descriptor = os.open(
            source,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | _O_BINARY,
        )
    except OSError as exc:
        raise AudioEncodingError(f"Could not open the PCM replacement: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        # ``supplied`` is a path stat and ``opened`` an fd stat, so this one
        # comparison crosses the boundary Windows cannot carry a change time
        # across.
        if _cross_stat_identity(opened) != _cross_stat_identity(supplied):
            raise AudioEncodingError("The PCM replacement changed while it was opened")
        header = _read_at(descriptor, 12, 0, "PCM replacement")
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise AudioEncodingError(
                "The replacement must be a little-endian PCM RIFF WAV"
            )
        if struct.unpack_from("<I", header, 4)[0] != opened.st_size - 8:
            raise AudioEncodingError(
                "The PCM WAV size field does not match the complete file"
            )
        fmt: bytes | None = None
        data_location: tuple[int, int] | None = None
        cursor = 12
        chunks = 0
        while cursor < opened.st_size:
            if cursor + 8 > opened.st_size:
                raise AudioEncodingError("The PCM WAV has a truncated chunk header")
            chunks += 1
            if chunks > 64:
                raise AudioEncodingError("The PCM WAV has too many chunks")
            chunk_header = _read_at(descriptor, 8, cursor, "PCM WAV chunk header")
            chunk_id = chunk_header[:4]
            chunk_size = struct.unpack_from("<I", chunk_header, 4)[0]
            start = cursor + 8
            end = start + chunk_size
            padded_end = end + (chunk_size & 1)
            if end > opened.st_size or padded_end > opened.st_size:
                raise AudioEncodingError("A PCM WAV chunk extends beyond the file")
            if chunk_id == b"fmt ":
                if fmt is not None:
                    raise AudioEncodingError("The PCM WAV repeats its fmt chunk")
                if not 16 <= chunk_size <= 40:
                    raise AudioEncodingError("The PCM WAV fmt chunk is unsupported")
                fmt = _read_at(descriptor, chunk_size, start, "PCM WAV fmt chunk")
            elif chunk_id == b"data":
                if data_location is not None:
                    raise AudioEncodingError("The PCM WAV repeats its data chunk")
                data_location = (start, chunk_size)
            cursor = padded_end
        if cursor != opened.st_size or fmt is None or data_location is None:
            raise AudioEncodingError("The PCM WAV must contain one fmt and one data chunk")
        if len(fmt) < 16:
            raise AudioEncodingError("The PCM WAV fmt chunk is truncated")
        codec, channels, sample_rate, byte_rate, block_align, bits = struct.unpack_from(
            "<HHIIHH", fmt
        )
        if codec == 1:
            if len(fmt) not in (16, 18) or (len(fmt) == 18 and fmt[16:18] != b"\0\0"):
                raise AudioEncodingError(
                    "PCM WAV format metadata must be canonical PCM16"
                )
        elif codec == 0xFFFE:
            pcm_subformat = bytes.fromhex(
                "0100000000001000800000aa00389b71"
            )
            if (
                len(fmt) != 40
                or struct.unpack_from("<H", fmt, 16)[0] != 22
                or struct.unpack_from("<H", fmt, 18)[0] != 16
                or fmt[24:40] != pcm_subformat
            ):
                raise AudioEncodingError(
                    "WAVE_FORMAT_EXTENSIBLE input must contain 16-bit PCM"
                )
        else:
            raise AudioEncodingError(
                "The replacement WAV must be uncompressed 16-bit PCM"
            )
        expected_byte_rate = target.sample_rate * target.block_align
        if (
            channels != target.channels
            or sample_rate != target.sample_rate
            or bits != 16
            or block_align != target.block_align
            or byte_rate != expected_byte_rate
        ):
            raise AudioEncodingError(
                "PCM WAV shape does not match this sound: required "
                f"{target.channels} channel(s), {target.sample_rate} Hz, 16-bit PCM"
            )
        if data_location[1] != target.data_size:
            actual_frames = (
                data_location[1] // target.block_align
                if data_location[1] % target.block_align == 0
                else "non-frame-aligned"
            )
            raise AudioEncodingError(
                "PCM WAV duration does not match this fixed sound slot: required "
                f"{target.frame_count} frames, found {actual_frames}"
            )
        if _source_identity(os.fstat(descriptor)) != _source_identity(opened):
            raise AudioEncodingError("The PCM replacement changed while it was read")
        return _PcmDataLocation(
            descriptor=descriptor,
            data_offset=data_location[0],
            data_size=data_location[1],
            source_identity=_source_identity(opened),
        )
    except BaseException:
        os.close(descriptor)
        raise


def _write_canonical_pcm(
    source: Path,
    destination: Path,
    target: Pcm16Target,
    *,
    progress: Progress,
    cancel_requested: CancelRequested | None,
) -> str:
    location = _open_pcm_data(source, target)
    digest = hashlib.sha256()
    completed = 0
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | _O_BINARY,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                header = _pcm16_header(target)
                stream.write(header)
                digest.update(header)
                while completed < location.data_size:
                    _not_cancelled(cancel_requested)
                    block_size = min(COPY_BLOCK_BYTES, location.data_size - completed)
                    block = _read_at(
                        location.descriptor,
                        block_size,
                        location.data_offset + completed,
                        "PCM sample data",
                    )
                    stream.write(block)
                    digest.update(block)
                    completed += len(block)
                    progress(
                        "Preparing private canonical PCM16 input",
                        completed,
                        location.data_size,
                    )
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        if _source_identity(os.fstat(location.descriptor)) != location.source_identity:
            destination.unlink(missing_ok=True)
            raise AudioEncodingError("The PCM replacement changed while it was copied")
        return digest.hexdigest()
    finally:
        os.close(location.descriptor)


def _validate_tool_path(
    path: Path,
    *,
    label: str,
    require_executable: bool,
) -> _FileIdentity:
    if not isinstance(path, Path):
        raise AudioEncodingError(f"{label} must be selected as a file")
    path = path.expanduser()
    if not path.is_absolute():
        raise AudioEncodingError(f"{label} path must be absolute")
    try:
        info = path.lstat()
    except OSError as exc:
        raise AudioEncodingError(f"Could not open {label}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise AudioEncodingError(f"{label} must be a regular file, not a link")
    if not 0 < info.st_size <= MAX_EXECUTABLE_BYTES:
        raise AudioEncodingError(f"{label} is empty or unreasonably large")
    # POSIX gates on the executable permission bit, which is a real, settable
    # property of the file and therefore worth reporting before we launch
    # anything.  Windows has no such bit: ``os.access(path, os.X_OK)`` there is
    # implemented as "does this file exist", so it always answers True and this
    # pre-flight cannot be the gate.  Windows decides executability from the
    # file's *content* at CreateProcess time and reports a non-image with
    # WinError 193 ("%1 is not a valid Win32 application"), which :meth:`encode`
    # turns into the same fail-closed AudioEncodingError.  We deliberately do
    # not invent a Windows substitute here -- guessing from the file extension
    # would reject a perfectly launchable tool that simply is not named
    # ``*.exe``.
    if require_executable and not platform_compat.IS_WINDOWS:
        if not os.access(path, os.X_OK):
            raise AudioEncodingError(
                f"{label} is not executable; enable its executable permission first"
            )
    return _FileIdentity(
        path=path,
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        mode=info.st_mode,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
    )


def _require_unchanged_tool(identity: _FileIdentity, label: str) -> None:
    try:
        info = identity.path.lstat()
    except OSError as exc:
        raise AudioEncodingError(f"{label} disappeared during encoding: {exc}") from exc
    # ``identity`` was captured by lstat and ``info`` is an lstat of the same
    # pathname: two path stats, which agree on st_ctime_ns everywhere, so the
    # metadata-only-change signal is kept on every platform.
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mode,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        != (
            identity.device,
            identity.inode,
            identity.size,
            identity.mode,
            identity.mtime_ns,
            identity.ctime_ns,
        )
    ):
        raise AudioEncodingError(f"{label} changed during encoding; output was discarded")


def _read_private_output(path: Path, maximum: int) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise AudioEncodingError(
            "The XMA1 encoder did not create its requested output file"
        ) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= maximum
    ):
        raise AudioEncodingError(
            "The XMA1 encoder output is empty, linked, or larger than this slot allows"
        )
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | _O_BINARY,
    )
    try:
        opened = os.fstat(descriptor)
        # Path stat against fd stat; see :func:`_cross_stat_identity`.
        if _cross_stat_identity(opened) != _cross_stat_identity(info):
            raise AudioEncodingError("The XMA1 encoder output changed while opening")
        chunks: list[bytes] = []
        total = 0
        while total < opened.st_size:
            block = os.read(descriptor, min(COPY_BLOCK_BYTES, opened.st_size - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
        if (
            total != opened.st_size
            or _source_identity(os.fstat(descriptor)) != _source_identity(opened)
        ):
            raise AudioEncodingError("The XMA1 encoder output changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


# --------------------------------------------------------------------------
# Confining the encoder: one process *group*, on two different process models.
#
# The guarantee is the same on every platform -- when :meth:`encode` returns or
# raises, nothing the user's encoder started is still running -- but the kernel
# primitive that delivers it is not.
#
# POSIX launches the encoder with ``start_new_session=True``, making it a
# session (and therefore process-group) leader whose PID doubles as the group
# id.  ``os.killpg`` then reaches every descendant even after the direct child
# has exited, and ``os.killpg(pg, 0)`` answers "is any of it still alive?".
#
# Windows has neither call: ``os.killpg`` does not exist there, ``os.kill`` is
# ``TerminateProcess`` and reaches exactly one process, and ``taskkill /T``
# walks parent PIDs, so it loses a child the moment its launcher exits -- which
# is precisely the case this code exists to catch.  The Win32 primitive with
# the same reach as a process group is a Job Object: a process assigned to one
# carries that job to everything it creates, ``TerminateJobObject`` stops all
# of them in a single call, and the job's ``ActiveProcesses`` counter answers
# the question ``killpg(pg, 0)`` answers on POSIX.  There is no group-wide
# graceful signal on Windows, so the job path is the analogue of the SIGKILL
# escalation, not of the SIGTERM that precedes it.
#
# ``tools/apf_audio.py`` carries the same two-model helper for the *decoder*
# side.  It is duplicated rather than shared because ``tools/`` modules are
# runnable standalone and must not grow a dependency on this package.
# --------------------------------------------------------------------------

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
# assignment is done; see :func:`_adopt_process_group`.  ``STATUS_SUCCESS`` is
# that call's "every thread resumed" NTSTATUS.
_WINDOWS_CREATE_SUSPENDED = 0x00000004
_WINDOWS_STATUS_SUCCESS = 0


class _WindowsProcessGroup:
    """A Job Object standing in for the POSIX session the encoder cannot have.

    Every entry point fails soft (returns ``None``/``False``) rather than
    raising, because this type is used from ``finally`` blocks where raising
    would replace the error the caller is already reporting.  A group that
    could not be established is reported as such so the caller can fall back to
    the direct child and still say honestly whether it stopped.
    """

    def __init__(self, kernel32: "ctypes.CDLL", handle: int) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @classmethod
    def create(cls) -> "_WindowsProcessGroup | None":
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

    def adopt(self, process: subprocess.Popen[bytes]) -> bool:
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
        # process on; degrade to the direct child rather than failing encode.
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


def _use_suspended_launch() -> bool:
    """Whether a child can be created suspended and confined before it runs.

    True only when *both* primitives the sequence needs are present: the job API
    (something to assign the frozen child to) and ``NtResumeProcess`` (a way to
    start it again).  Missing either, creating the child suspended would risk one
    that can never run, so the caller launches normally and assigns the job the
    instant the child starts instead -- the pre-existing, slightly racier path.
    """

    if not platform_compat.IS_WINDOWS:
        return False
    return _windows_job_api() is not None and _windows_ntdll_resume() is not None


def _resume_suspended_process(process: subprocess.Popen[bytes]) -> bool:
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


def _adopt_process_group(
    process: subprocess.Popen[bytes],
    *,
    was_suspended: bool = False,
) -> _WindowsProcessGroup | None:
    """Give *process* a group with POSIX-session reach, where one is needed.

    POSIX already has it: ``start_new_session=True`` did the work at launch.
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
    group = _WindowsProcessGroup.create()
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


def _drain_windows_job(group: "_WindowsProcessGroup") -> int | None:
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


def _stop_windows_process(
    process: subprocess.Popen[bytes],
    group: _WindowsProcessGroup | None,
) -> None:
    """Stop the encoder and its descendants through the job object.

    The fail-closed raise fires only on *positive evidence* of a survivor: the
    job's own active-process count, read after ``TerminateJobObject`` and given a
    bounded window to fall to zero, or -- when that count cannot be read at all
    -- the direct child still being alive.  A group that genuinely stopped, or
    one whose accounting merely could not be queried while the child it led is
    already gone, is never misreported as a survivor.
    """

    if group is None:
        # No job: only the direct child is reachable.  Stop it and report the
        # same fail-closed error the POSIX path raises, but only on the same
        # evidence -- an observed survivor, never merely an unobservable group.
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            pass
        if process.poll() is None:
            raise AudioEncodingError(
                "The XMA1 encoder left a background process that could not be "
                "stopped; its output was discarded and no project edit was staged"
            )
        return
    try:
        group.terminate()
        try:
            process.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
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
        if survived:
            raise AudioEncodingError(
                "The XMA1 encoder left a background process that could not be "
                "stopped; its output was discarded and no project edit was staged"
            )
    finally:
        group.close()


def _stop_process(
    process: subprocess.Popen[bytes],
    group: _WindowsProcessGroup | None = None,
) -> None:
    """Terminate the complete session-owned process group on every exit path.

    The direct encoder (or Wine loader) is started as a new session leader, so
    its PID is also the process-group ID.  A successful launcher may otherwise
    exit while a worker or deliberately backgrounded child keeps running.  We
    therefore signal and drain the group even when the direct child has already
    returned zero.  On Windows the same reach comes from *group*, the job
    object the launcher was adopted into; see the note above ``_stop_process``.
    """

    if platform_compat.IS_WINDOWS:
        _stop_windows_process(process, group)
        return

    process_group = process.pid

    def group_exists() -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def wait_for_group(timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while group_exists() and time.monotonic() < deadline:
            time.sleep(PROCESS_POLL_SECONDS)
        return not group_exists()

    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        pass
    if wait_for_group(PROCESS_STOP_GRACE_SECONDS):
        return
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=PROCESS_STOP_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        pass
    if not wait_for_group(PROCESS_STOP_GRACE_SECONDS):
        raise AudioEncodingError(
            "The XMA1 encoder left a background process that could not be stopped; "
            "its output was discarded and no project edit was staged"
        )


def _clean_stderr(path: Path) -> str:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_size > MAX_ENCODER_LOG_BYTES
        ):
            raise AudioEncodingError(
                "The XMA1 encoder produced more than 1 MiB of diagnostic output"
            )
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | _O_BINARY,
        )
        try:
            opened = os.fstat(descriptor)
            # Path stat against fd stat; see :func:`_cross_stat_identity`.
            if _cross_stat_identity(opened) != _cross_stat_identity(info):
                raise AudioEncodingError(
                    "The XMA1 encoder diagnostic output changed while opening"
                )
            wanted = min(2000, opened.st_size)
            data = platform_compat.pread(descriptor, wanted, opened.st_size - wanted)
            if len(data) != wanted:
                raise AudioEncodingError(
                    "The XMA1 encoder diagnostic output changed while reading"
                )
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise AudioEncodingError(
            f"Could not read XMA1 encoder diagnostic output: {exc}"
        ) from exc
    return data[-2000:].decode("utf-8", errors="replace").strip()


class ExternalXma1Encoder:
    """No-shell adapter for a user-installed XMA1 encoder.

    ``arguments`` is an argv template.  It must reference ``{input}`` and
    ``{output}`` exactly once each.  It may also use ``{channels}``,
    ``{sample_rate}``, ``{sample_count}``, and ``{encoded_size}``.  Direct mode
    executes ``executable``.  Wine mode executes ``wine_executable`` and passes
    the user-supplied ``.exe`` as argv[1].
    """

    _PLACEHOLDERS = frozenset(
        {
            "input",
            "output",
            "channels",
            "sample_rate",
            "sample_count",
            "encoded_size",
        }
    )

    def __init__(
        self,
        executable: Path,
        *,
        arguments: tuple[str, ...] = ("{input}", "{output}"),
        wine_executable: Path | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.executable = executable
        self.arguments = self._validate_arguments(arguments)
        self.wine_executable = wine_executable
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float)
        ):
            raise AudioEncodingError("XMA1 encoder timeout must be a number of seconds")
        self.timeout_seconds = float(timeout_seconds)
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise AudioEncodingError(
                "XMA1 encoder timeout must be between 0.05 and 1800 seconds"
            )

    @classmethod
    def _validate_arguments(cls, arguments: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(arguments, tuple) or not 1 <= len(arguments) <= MAX_ENCODER_ARGUMENTS:
            raise AudioEncodingError(
                "XMA1 encoder arguments must be a tuple containing 1 to 64 argv entries"
            )
        counts = {"input": 0, "output": 0}
        formatter = string.Formatter()
        for argument in arguments:
            if (
                not isinstance(argument, str)
                or not argument
                or len(argument) > MAX_ENCODER_ARGUMENT_LENGTH
                or "\0" in argument
            ):
                raise AudioEncodingError("Every XMA1 encoder argument must be bounded text")
            try:
                parsed = tuple(formatter.parse(argument))
            except ValueError as exc:
                raise AudioEncodingError(
                    f"XMA1 encoder argument has malformed braces: {argument!r}"
                ) from exc
            for _literal, field_name, format_spec, conversion in parsed:
                if field_name is None:
                    continue
                if (
                    field_name not in cls._PLACEHOLDERS
                    or format_spec
                    or conversion is not None
                ):
                    raise AudioEncodingError(
                        f"Unsupported XMA1 encoder placeholder: {{{field_name}}}"
                    )
                if field_name in counts:
                    counts[field_name] += 1
        if counts != {"input": 1, "output": 1}:
            raise AudioEncodingError(
                "XMA1 encoder arguments must contain {input} and {output} exactly once"
            )
        return arguments

    def validate(self) -> Mapping[str, object]:
        """Validate the configured tools now, without running either one."""

        if self.wine_executable is None:
            # Wine is how a *Unix* host runs a Windows encoder, so demanding it
            # for a ``.exe`` is correct on Linux and macOS and nonsense on
            # Windows, where a ``.exe`` is simply the native direct mode -- and
            # where every plausible encoder, including this interpreter, ends in
            # ``.exe``.  The encoder contract is unchanged: direct mode still
            # runs ``executable`` itself, Wine mode still passes the ``.exe`` as
            # argv[1] to the loader.
            if (
                not platform_compat.IS_WINDOWS
                and isinstance(self.executable, Path)
                and self.executable.suffix.casefold() == ".exe"
            ):
                raise AudioEncodingError(
                    "A Windows .exe needs a separate Wine executable path"
                )
            tool = _validate_tool_path(
                self.executable,
                label="XMA1 encoder",
                require_executable=True,
            )
            return {
                "schema": EXTERNAL_XMA1_ENCODER_SCHEMA,
                "status": "ready",
                "mode": "direct",
                "no_shell": True,
                "encoder_binary_bundled": False,
                "tool_size": tool.size,
            }
        if not isinstance(self.executable, Path) or self.executable.suffix.casefold() != ".exe":
            raise AudioEncodingError(
                "Wine mode requires a user-supplied encoder file ending in .exe"
            )
        wine = _validate_tool_path(
            self.wine_executable,
            label="Wine executable",
            require_executable=True,
        )
        encoder = _validate_tool_path(
            self.executable,
            label="Windows XMA1 encoder",
            require_executable=False,
        )
        return {
            "schema": EXTERNAL_XMA1_ENCODER_SCHEMA,
            "status": "ready",
            "mode": "wine",
            "no_shell": True,
            "encoder_binary_bundled": False,
            "tool_size": encoder.size,
            "wine_size": wine.size,
        }

    def _tool_identities(self) -> tuple[_FileIdentity, _FileIdentity | None]:
        self.validate()
        if self.wine_executable is None:
            return (
                _validate_tool_path(
                    self.executable,
                    label="XMA1 encoder",
                    require_executable=True,
                ),
                None,
            )
        return (
            _validate_tool_path(
                self.executable,
                label="Windows XMA1 encoder",
                require_executable=False,
            ),
            _validate_tool_path(
                self.wine_executable,
                label="Wine executable",
                require_executable=True,
            ),
        )

    def _command(
        self,
        encoder: _FileIdentity,
        wine: _FileIdentity | None,
        input_path: Path,
        output_path: Path,
        target: Pcm16Target,
    ) -> tuple[str, ...]:
        if wine is None:
            input_argument = str(input_path)
            output_argument = str(output_path)
        else:
            # The private paths are controlled by this module, contain no
            # backslashes, and live below the Unix root that Wine maps as Z:.
            # Windows encoder programs require Windows-form path arguments;
            # passing raw /tmp/... text is not portable across Wine versions.
            input_argument = "Z:" + str(input_path).replace("/", "\\")
            output_argument = "Z:" + str(output_path).replace("/", "\\")
        values = {
            "input": input_argument,
            "output": output_argument,
            "channels": str(target.channels),
            "sample_rate": str(target.sample_rate),
            "sample_count": str(target.frame_count),
            "encoded_size": str(target.encoded_size),
        }
        expanded = tuple(argument.format_map(values) for argument in self.arguments)
        if wine is None:
            return (str(encoder.path), *expanded)
        return (str(wine.path), str(encoder.path), *expanded)

    def encode(
        self,
        source_pcm_wav: Path,
        target: Pcm16Target,
        *,
        progress: Progress | None = None,
        cancel_requested: CancelRequested | None = None,
    ) -> ExternalEncodingResult:
        """Encode privately; callers must still run the APF exact-slot validator."""

        target = validate_pcm16_target(target)
        report = progress or _noop
        _not_cancelled(cancel_requested)
        encoder_identity, wine_identity = self._tool_identities()
        mode = "wine" if wine_identity is not None else "direct"
        maximum_output = target.encoded_size + MAX_ENCODER_OUTPUT_OVERHEAD_BYTES
        with tempfile.TemporaryDirectory(prefix="apf-xma1-encode-") as directory_name:
            directory = Path(directory_name)
            os.chmod(directory, 0o700)
            canonical_pcm = directory / "input.wav"
            output_xma = directory / "output.xma"
            stderr_path = directory / "encoder.stderr"
            input_sha256 = _write_canonical_pcm(
                source_pcm_wav,
                canonical_pcm,
                target,
                progress=report,
                cancel_requested=cancel_requested,
            )
            _not_cancelled(cancel_requested)
            command = self._command(
                encoder_identity,
                wine_identity,
                canonical_pcm,
                output_xma,
                target,
            )
            report("Running user-supplied XMA1 encoder", 0, 0)
            process: subprocess.Popen[bytes] | None = None
            group: _WindowsProcessGroup | None = None
            started = time.monotonic()
            suspended = _use_suspended_launch()
            try:
                with stderr_path.open("xb") as stderr_stream:
                    process = subprocess.Popen(
                        command,
                        cwd=directory,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=stderr_stream,
                        shell=False,
                        close_fds=True,
                        # POSIX only; ignored on Windows, where the job object
                        # assigned on the next line provides the same reach.
                        start_new_session=True,
                        # Windows only (``0`` -- the default -- everywhere else,
                        # so POSIX launch is byte-for-byte unchanged): freeze the
                        # child so it is sealed into the job before it can spawn
                        # anything; ``_adopt_process_group`` resumes it.
                        creationflags=_WINDOWS_CREATE_SUSPENDED if suspended else 0,
                    )
                    group = _adopt_process_group(process, was_suspended=suspended)
                    while process.poll() is None:
                        _not_cancelled(cancel_requested)
                        elapsed = time.monotonic() - started
                        if elapsed > self.timeout_seconds:
                            raise AudioEncodingError(
                                "XMA1 encoding timed out after "
                                f"{self.timeout_seconds:g} seconds; no project edit was staged"
                            )
                        try:
                            if stderr_path.stat().st_size > MAX_ENCODER_LOG_BYTES:
                                raise AudioEncodingError(
                                    "The XMA1 encoder produced more than 1 MiB of diagnostic output"
                                )
                            if output_xma.exists() or output_xma.is_symlink():
                                output_info = output_xma.lstat()
                                if (
                                    not stat.S_ISREG(output_info.st_mode)
                                    or stat.S_ISLNK(output_info.st_mode)
                                    or output_info.st_size > maximum_output
                                ):
                                    raise AudioEncodingError(
                                        "The XMA1 encoder output became linked or "
                                        "larger than this slot allows"
                                    )
                        except OSError as exc:
                            raise AudioEncodingError(
                                f"Could not monitor XMA1 encoder output: {exc}"
                            ) from exc
                        time.sleep(PROCESS_POLL_SECONDS)
            except OSError as exc:
                raise AudioEncodingError(
                    f"Could not start the user-supplied XMA1 encoder: {exc}"
                ) from exc
            finally:
                if process is not None:
                    _stop_process(process, group)
                elif group is not None:
                    group.close()
            assert process is not None
            _require_unchanged_tool(encoder_identity, "XMA1 encoder")
            if wine_identity is not None:
                _require_unchanged_tool(wine_identity, "Wine executable")
            stderr = _clean_stderr(stderr_path)
            if process.returncode != 0:
                detail = stderr or f"exit status {process.returncode}"
                raise AudioEncodingError(
                    f"The XMA1 encoder failed ({detail}); no project edit was staged"
                )
            _not_cancelled(cancel_requested)
            encoded = _read_private_output(output_xma, maximum_output)
            report("XMA1 encoder output ready for APF slot validation", 1, 1)
            output_sha256 = hashlib.sha256(encoded).hexdigest()
        return ExternalEncodingResult(
            xma1_riff=encoded,
            receipt={
                "schema": EXTERNAL_XMA1_ENCODER_SCHEMA,
                "status": "encoded_pending_exact_slot_validation",
                "mode": mode,
                "no_shell": True,
                "encoder_binary_bundled": False,
                "temporary_files_removed": True,
                "target": {
                    "channels": target.channels,
                    "sample_rate": target.sample_rate,
                    "frame_count": target.frame_count,
                    "encoded_size": target.encoded_size,
                },
                "input": {
                    "canonical_pcm16_sha256": input_sha256,
                    "canonical_pcm16_size": target.wav_size,
                },
                "output": {
                    "xma1_file_sha256": output_sha256,
                    "xma1_file_size": len(encoded),
                },
                "bridge_reads_loaded_game": False,
                "bridge_passes_loaded_game_path": False,
                "encoder_input_is_user_selected_pcm": True,
                "input_audio_content_classified": False,
                "retail_audio_classification": "not_evaluated",
                "contains_encoder_binary": False,
            },
        )


__all__ = [
    "AudioEncodingCancelled",
    "AudioEncodingError",
    "EXTERNAL_XMA1_ENCODER_SCHEMA",
    "ExternalEncodingResult",
    "ExternalXma1Encoder",
    "PCM16_TEMPLATE_SCHEMA",
    "Pcm16Target",
    "Pcm16TemplateReceipt",
    "export_pcm16_template",
    "validate_pcm16_target",
]
