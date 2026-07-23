"""Safe recipe contract for NFL 2K5's one proved audio replacement slot.

The recipe names only the fixed ``menu-back_01`` target and a user-authored
WAV.  It never accepts a raw disc offset, archive selector, payload, or retail
byte string.  Recipe creation and loading both decode the complete strict WAV
contract and pin the input by size and SHA-256.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

from .errors import ModEditorError, OutputRefusedError, ValidationError


NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA = "nfl2k5_menu_back_audio_recipe/v1"
NFL_MENU_BACK_AUDIO_TARGET = "menu-back_01"
NFL_MENU_BACK_AUDIO_CHANNELS = 1
NFL_MENU_BACK_AUDIO_SAMPLE_RATE = 16_000
NFL_MENU_BACK_AUDIO_FRAME_COUNT = 5_696
NFL_MENU_BACK_AUDIO_PCM_BYTES = NFL_MENU_BACK_AUDIO_FRAME_COUNT * 2
MAX_NFL_MENU_BACK_WAV_BYTES = 16 * 1024 * 1024
MAX_NFL_MENU_BACK_RECIPE_BYTES = 64 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class NflAudioRecipeError(ValidationError):
    """A recipe or WAV does not meet the fixed NFL audio contract."""


@dataclass(frozen=True)
class NflMenuBackAudioRecipe:
    recipe_path: Path
    purpose: str
    wav_path: Path
    wav_size: int
    wav_sha256: str


@dataclass(frozen=True)
class _RegularBytes:
    path: Path
    identity: tuple[int, int]
    payload: bytes


def canonical_nfl_audio_recipe_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NflAudioRecipeError(message)


def _read_regular(path: Path, *, maximum: int, label: str) -> _RegularBytes:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise NflAudioRecipeError(f"{label} does not exist: {requested}") from exc
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    _require(0 < supplied.st_size <= maximum, f"{label} size is outside the allowed range")
    resolved = requested.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        _require(
            stat.S_ISREG(opened.st_mode)
            and identity == (supplied.st_dev, supplied.st_ino)
            and opened.st_size == supplied.st_size,
            f"{label} changed before its read-only open",
        )
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            _require(bool(chunk), f"{label} shortened while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        _require(
            (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], opened.st_size),
            f"{label} pathname changed while reading",
        )
        return _RegularBytes(resolved, identity, b"".join(chunks))
    finally:
        os.close(descriptor)


def _validate_strict_wav(payload: bytes) -> None:
    _require(len(payload) >= 44, "NFL menu-back WAV is too short")
    _require(payload[:4] == b"RIFF" and payload[8:12] == b"WAVE", "input is not RIFF/WAVE")
    _require(
        struct.unpack_from("<I", payload, 4)[0] + 8 == len(payload),
        "RIFF size does not equal the complete WAV",
    )
    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < len(payload):
        _require(offset + 8 <= len(payload), "truncated WAV chunk header")
        kind = payload[offset : offset + 4]
        length = struct.unpack_from("<I", payload, offset + 4)[0]
        start = offset + 8
        end = start + length
        _require(end <= len(payload), "WAV chunk exceeds the RIFF boundary")
        chunks.append((kind, payload[start:end]))
        offset = end + (length & 1)
        _require(offset <= len(payload), "WAV pad byte exceeds the RIFF boundary")
    _require(offset == len(payload), "WAV chunks do not tile the input")
    _require(
        [kind for kind, _ in chunks] == [b"fmt ", b"data"],
        "strict WAV must contain exactly fmt then data; remove metadata chunks",
    )
    fmt = chunks[0][1]
    pcm = chunks[1][1]
    _require(len(fmt) == 16, "strict WAV fmt chunk must use the 16-byte PCM form")
    format_tag, channels, rate, byte_rate, block_align, bits = struct.unpack("<HHIIHH", fmt)
    _require(format_tag == 1, "WAV must use integer PCM format tag 1")
    _require(channels == NFL_MENU_BACK_AUDIO_CHANNELS, "WAV must be mono")
    _require(rate == NFL_MENU_BACK_AUDIO_SAMPLE_RATE, "WAV must be exactly 16000 Hz")
    _require(
        bits == 16 and block_align == 2 and byte_rate == NFL_MENU_BACK_AUDIO_SAMPLE_RATE * 2,
        "WAV must be canonical little-endian PCM16",
    )
    _require(
        len(pcm) == NFL_MENU_BACK_AUDIO_PCM_BYTES,
        f"WAV must contain exactly {NFL_MENU_BACK_AUDIO_FRAME_COUNT} frames",
    )


def _validate_purpose(purpose: str) -> None:
    _require(
        type(purpose) is str and 0 < len(purpose) <= 4096 and "\0" not in purpose,
        "NFL audio purpose must contain 1..4096 characters and no NUL",
    )


def _output_path(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() != ".json":
        raise OutputRefusedError("NFL audio recipe output must use a .json filename")
    if os.path.lexists(requested):
        raise OutputRefusedError(f"NFL audio recipe output already exists: {requested}")
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise OutputRefusedError(
            f"NFL audio recipe output parent does not exist: {requested.parent}"
        ) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise OutputRefusedError("NFL audio recipe parent must be a non-symlink directory")
    return requested.resolve(strict=False)


def _path_reference(source: Path, parent: Path) -> str:
    try:
        return source.relative_to(parent).as_posix()
    except ValueError:
        return os.fspath(source)


def _remove_owned(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if (
        stat.S_ISREG(current.st_mode)
        and not stat.S_ISLNK(current.st_mode)
        and (current.st_dev, current.st_ino) == identity
    ):
        path.unlink(missing_ok=True)


def _write_new_json(path: Path, document: object) -> Path:
    payload = canonical_nfl_audio_recipe_json(document)
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        opened = os.fstat(descriptor)
        _require(stat.S_ISREG(opened.st_mode), "NFL audio recipe output is not regular")
        identity = (opened.st_dev, opened.st_ino)
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            if written <= 0:
                raise OSError("short NFL audio recipe write")
            cursor += written
        os.fsync(descriptor)
        current = path.lstat()
        _require(
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], len(payload)),
            "NFL audio recipe output pathname or size changed while writing",
        )
    except FileExistsError as exc:
        raise OutputRefusedError(f"NFL audio recipe output already exists: {path}") from exc
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        _remove_owned(path, identity)
        if isinstance(exc, ModEditorError):
            raise
        raise NflAudioRecipeError(f"Could not create NFL audio recipe: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return path


def create_nfl_menu_back_audio_recipe(*, output: Path, purpose: str, wav: Path) -> Path:
    """Pin one normalized WAV and exclusively create a fixed-target recipe."""

    destination = _output_path(output)
    _validate_purpose(purpose)
    wav_file = _read_regular(wav, maximum=MAX_NFL_MENU_BACK_WAV_BYTES, label="NFL menu-back WAV")
    _require(wav_file.path.suffix.lower() == ".wav", "NFL menu-back input must use a .wav filename")
    _validate_strict_wav(wav_file.payload)
    document = {
        "purpose": purpose,
        "schema": NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
        "target": NFL_MENU_BACK_AUDIO_TARGET,
        "wav": _path_reference(wav_file.path, destination.parent),
        "wav_sha256": hashlib.sha256(wav_file.payload).hexdigest(),
        "wav_size": len(wav_file.payload),
    }
    return _write_new_json(destination, document)


def load_nfl_menu_back_audio_recipe(path: Path) -> NflMenuBackAudioRecipe:
    """Load canonical JSON, resolve its WAV, and recheck every content pin."""

    recipe_file = _read_regular(
        path, maximum=MAX_NFL_MENU_BACK_RECIPE_BYTES, label="NFL audio recipe"
    )
    try:
        value = json.loads(recipe_file.payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NflAudioRecipeError("NFL audio recipe is invalid UTF-8 JSON") from exc
    _require(
        recipe_file.payload == canonical_nfl_audio_recipe_json(value),
        "NFL audio recipe must use canonical sorted pretty JSON",
    )
    _require(isinstance(value, dict), "NFL audio recipe root must be an object")
    _require(
        set(value) == {"purpose", "schema", "target", "wav", "wav_sha256", "wav_size"},
        "NFL audio recipe fields differ from the v1 contract",
    )
    _require(
        value.get("schema") == NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
        "NFL audio recipe schema differs",
    )
    _validate_purpose(value.get("purpose"))
    _require(value.get("target") == NFL_MENU_BACK_AUDIO_TARGET, "NFL audio target is not proved")
    _require(
        type(value.get("wav")) is str and bool(value["wav"]) and "\0" not in value["wav"],
        "NFL audio recipe WAV path is invalid",
    )
    _require(
        type(value.get("wav_size")) is int
        and 44 <= value["wav_size"] <= MAX_NFL_MENU_BACK_WAV_BYTES,
        "NFL audio recipe WAV size pin is invalid",
    )
    _require(
        type(value.get("wav_sha256")) is str
        and _SHA256_RE.fullmatch(value["wav_sha256"]) is not None,
        "NFL audio recipe WAV SHA-256 pin is invalid",
    )
    wav_path = Path(value["wav"])
    if not wav_path.is_absolute():
        wav_path = recipe_file.path.parent / wav_path
    wav_file = _read_regular(
        wav_path, maximum=MAX_NFL_MENU_BACK_WAV_BYTES, label="NFL menu-back WAV"
    )
    _require(wav_file.path.suffix.lower() == ".wav", "NFL menu-back input must use a .wav filename")
    _require(len(wav_file.payload) == value["wav_size"], "NFL audio WAV size differs from recipe")
    _require(
        hashlib.sha256(wav_file.payload).hexdigest() == value["wav_sha256"],
        "NFL audio WAV SHA-256 differs from recipe",
    )
    _validate_strict_wav(wav_file.payload)
    return NflMenuBackAudioRecipe(
        recipe_path=recipe_file.path,
        purpose=value["purpose"],
        wav_path=wav_file.path,
        wav_size=len(wav_file.payload),
        wav_sha256=value["wav_sha256"],
    )


__all__ = [
    "MAX_NFL_MENU_BACK_RECIPE_BYTES",
    "MAX_NFL_MENU_BACK_WAV_BYTES",
    "NFL_MENU_BACK_AUDIO_CHANNELS",
    "NFL_MENU_BACK_AUDIO_FRAME_COUNT",
    "NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA",
    "NFL_MENU_BACK_AUDIO_SAMPLE_RATE",
    "NFL_MENU_BACK_AUDIO_TARGET",
    "NflAudioRecipeError",
    "NflMenuBackAudioRecipe",
    "canonical_nfl_audio_recipe_json",
    "create_nfl_menu_back_audio_recipe",
    "load_nfl_menu_back_audio_recipe",
]
