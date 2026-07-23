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
    ctime_ns: int


@dataclass(frozen=True)
class _PcmDataLocation:
    descriptor: int
    data_offset: int
    data_size: int
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
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _read_at(descriptor: int, count: int, offset: int, label: str) -> bytes:
    try:
        data = os.pread(descriptor, count, offset)
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
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise AudioEncodingError(f"Could not open the PCM replacement: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        if _source_identity(opened) != _source_identity(supplied):
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
            | getattr(os, "O_CLOEXEC", 0),
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
    if require_executable and not os.access(path, os.X_OK):
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
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if _source_identity(opened) != _source_identity(info):
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


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate the complete session-owned process group on every exit path.

    The direct encoder (or Wine loader) is started as a new session leader, so
    its PID is also the process-group ID.  A successful launcher may otherwise
    exit while a worker or deliberately backgrounded child keeps running.  We
    therefore signal and drain the group even when the direct child has already
    returned zero.
    """

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
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if _source_identity(opened) != _source_identity(info):
                raise AudioEncodingError(
                    "The XMA1 encoder diagnostic output changed while opening"
                )
            wanted = min(2000, opened.st_size)
            data = os.pread(descriptor, wanted, opened.st_size - wanted)
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
            if isinstance(self.executable, Path) and self.executable.suffix.casefold() == ".exe":
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
            started = time.monotonic()
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
                        start_new_session=True,
                    )
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
                    _stop_process(process)
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
