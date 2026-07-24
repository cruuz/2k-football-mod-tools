"""Private source-audio PCM fingerprints for NFL 2K5 Mod Studio.

Shareable Mod Studio projects may contain only user-authored replacement audio.
Comparing a replacement solely with its selected cue is not enough: a decoded
retail cue could otherwise be placed in a different, same-shaped slot.  This
module maintains the complete decoded-PCM SHA-256 set for one recognized user
XISO, covering all standalone ``AUDO`` assets and every deduplicated physical
``AUSB`` slot.

The inventory is deliberately private and source-bound.  It is published only
beneath ``SourceCache.root/derived``, contains hashes, source-private canonical
IDs, and codec shape metadata but no WAV, PCM, encoded audio, or separate
archive/pack coordinates, and has no API for copying itself into a project or
release.  Callers supply the costly streaming-slot hash operation; this module
owns completeness, deterministic serialization, cancellation, atomic
publication, strict loading, and lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from .errors import ValidationError
from .nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    streaming_slot_write_plan,
)
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache
from . import platform_compat


SCHEMA = "2k5_mod_studio_audio_source_pcm_fingerprints/v1"
PRIVATE_RELATIVE_PATH = Path("derived/audio-source-pcm-fingerprints-v1.json")
EXPECTED_STANDALONE_COUNT = 850
EXPECTED_STREAMING_SLOT_COUNT = 53_570
EXPECTED_STREAMING_OWNER_COUNT = 53_571
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
_RENAME_NOREPLACE = 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STANDALONE_ID_RE = re.compile(
    r"^nfl2k5\.audio\.audo\.o[0-9]{4}\.c[0-9]{4}$"
)
_STREAMING_CANONICAL_ID_RE = re.compile(
    r"^nfl2k5\.audio\.ausb\.physical\.o[0-9]{4}\."
    r"s[0-9a-f]{10}\.n[0-9a-f]{10}$"
)
_STREAMING_OWNER_ID_RE = re.compile(
    r"^nfl2k5\.audio\.ausb\.o[0-9]{4}\.c[0-9]{4}\.r[0-9]{5}$"
)


class AudioSourceFingerprintError(ValidationError):
    """The private fingerprint inventory is unsafe, incomplete, or invalid."""


class AudioSourceFingerprintCancelled(AudioSourceFingerprintError):
    """Fingerprint generation was cancelled before publication."""


class SourceDerivedPcmError(AudioSourceFingerprintError):
    """Caller-supplied PCM exactly matches decoded audio from the source XISO."""

    def __init__(self, matches: tuple["SourcePcmMatch", ...]) -> None:
        self.matches = matches
        first = matches[0]
        owners = ", ".join(first.owner_asset_ids[:2])
        if len(first.owner_asset_ids) > 2:
            owners += f" (+{len(first.owner_asset_ids) - 2} aliases)"
        super().__init__(
            "That audio exactly matches decoded source audio "
            f"({owners}). Retail-derived audio cannot enter a shareable project."
        )


@dataclass(frozen=True, slots=True)
class AudioFingerprintProgress:
    """Deterministic item-level progress for the private one-time inventory."""

    stage: str
    completed_items: int
    total_items: int


@dataclass(frozen=True, slots=True)
class StandalonePcmFingerprint:
    asset_id: str
    channels: int
    sample_rate: int
    frame_count: int
    pcm_sha256: str


@dataclass(frozen=True, slots=True)
class StreamingPcmFingerprint:
    canonical_id: str
    owner_asset_ids: tuple[str, ...]
    channels: int
    sample_rate: int
    frame_count: int
    pcm_sha256: str


@dataclass(frozen=True, slots=True)
class SourcePcmMatch:
    """One standalone asset or canonical streaming slot owning a PCM hash."""

    family: str
    canonical_id: str
    owner_asset_ids: tuple[str, ...]
    channels: int
    sample_rate: int
    frame_count: int
    pcm_sha256: str


@dataclass(frozen=True, slots=True)
class AudioSourceFingerprintInventory:
    """Validated, immutable private lookup for one exact source-XISO SHA."""

    source_sha256: str
    path: Path
    standalone: tuple[StandalonePcmFingerprint, ...]
    streaming_slots: tuple[StreamingPcmFingerprint, ...]
    by_asset_id: Mapping[str, SourcePcmMatch]
    by_pcm_sha256: Mapping[str, tuple[SourcePcmMatch, ...]]
    private: bool = True
    shareable: bool = False

    @property
    def standalone_count(self) -> int:
        return len(self.standalone)

    @property
    def streaming_slot_count(self) -> int:
        return len(self.streaming_slots)

    @property
    def streaming_owner_count(self) -> int:
        return sum(len(row.owner_asset_ids) for row in self.streaming_slots)

    def resolve(self, asset_id: str) -> SourcePcmMatch:
        """Resolve a standalone, canonical-slot, or logical streaming ID."""

        try:
            return self.by_asset_id[asset_id]
        except KeyError as exc:
            raise AudioSourceFingerprintError(
                f"Unknown private source-audio fingerprint ID: {asset_id}"
            ) from exc

    def matches_pcm_sha256(self, pcm_sha256: str) -> tuple[SourcePcmMatch, ...]:
        """Return every source owner of an exact decoded-PCM digest."""

        digest = _sha256_text(pcm_sha256, "decoded PCM SHA-256")
        return self.by_pcm_sha256.get(digest, ())

    def matches_pcm(
        self,
        pcm16le: bytes | bytearray | memoryview,
        *,
        channels: int,
        sample_rate: int,
        frame_count: int,
    ) -> tuple[SourcePcmMatch, ...]:
        """Hash canonical PCM16LE and return exact source matches.

        Shape is validated to prevent callers from hashing a truncated or
        container-framed payload by mistake.  Rejection itself is digest-wide:
        source PCM remains source-derived even when a different slot interprets
        the same bytes with another rate or channel layout.
        """

        shape = _shape(channels, sample_rate, frame_count, "candidate PCM")
        try:
            view = memoryview(pcm16le)
        except TypeError as exc:
            raise AudioSourceFingerprintError(
                "Candidate PCM must be a bytes-like PCM16LE payload"
            ) from exc
        if view.ndim != 1 or view.itemsize != 1 or not view.c_contiguous:
            try:
                view = view.cast("B")
            except (TypeError, ValueError) as exc:
                raise AudioSourceFingerprintError(
                    "Candidate PCM must be a contiguous byte payload"
                ) from exc
        expected_bytes = shape[0] * shape[2] * 2
        if view.nbytes != expected_bytes:
            raise AudioSourceFingerprintError(
                "Candidate PCM byte length does not match its channel/frame shape "
                f"({view.nbytes:,} found; {expected_bytes:,} expected)"
            )
        return self.matches_pcm_sha256(hashlib.sha256(view).hexdigest())

    def reject_exact_source_pcm(
        self,
        pcm16le: bytes | bytearray | memoryview,
        *,
        channels: int,
        sample_rate: int,
        frame_count: int,
    ) -> None:
        """Raise when user-supplied PCM exactly matches either source family."""

        matches = self.matches_pcm(
            pcm16le,
            channels=channels,
            sample_rate=sample_rate,
            frame_count=frame_count,
        )
        if matches:
            raise SourceDerivedPcmError(matches)


ProgressSink = Callable[[AudioFingerprintProgress], None]
CancellationCheck = Callable[[], bool]
StreamingPcmHasher = Callable[[CanonicalStreamingSlot], str]
PublicationGuard = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class _ExpectedStandalone:
    asset_id: str
    channels: int
    sample_rate: int
    frame_count: int
    pcm_sha256: str


@dataclass(frozen=True, slots=True)
class _ExpectedStreaming:
    canonical_id: str
    owner_asset_ids: tuple[str, ...]
    channels: int
    sample_rate: int
    frame_count: int


class _ConcurrentPublication(FileExistsError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioSourceFingerprintError(message)


def _strict_int(value: object, label: str, *, minimum: int = 1) -> int:
    _require(
        type(value) is int and value >= minimum,
        f"Private source-audio inventory has an invalid {label}",
    )
    return value


def _sha256_text(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None,
        f"Private source-audio inventory has an invalid {label}",
    )
    return value


def _shape(
    channels: object,
    sample_rate: object,
    frame_count: object,
    label: str,
) -> tuple[int, int, int]:
    parsed_channels = _strict_int(channels, f"{label} channel count")
    _require(
        parsed_channels in (1, 2),
        f"Private source-audio inventory has an unsupported {label} channel count",
    )
    return (
        parsed_channels,
        _strict_int(sample_rate, f"{label} sample rate"),
        _strict_int(frame_count, f"{label} frame count"),
    )


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _records_sha256(
    standalone: list[dict[str, object]],
    streaming_slots: list[dict[str, object]],
) -> str:
    return hashlib.sha256(_canonical_json({
        "standalone": standalone,
        "streaming_slots": streaming_slots,
    })).hexdigest()


def _regular_private_directory(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise AudioSourceFingerprintError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a private, non-link directory",
    )
    return path.resolve(strict=True)


def _regular_private_file(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise AudioSourceFingerprintError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_nlink == 1
        # Ownership is asked through platform_compat rather than compared as a
        # raw uid: Windows reports st_uid == 0 for every file, so an inline
        # comparison would degrade into a check that always passes there.
        and platform_compat.is_owned_by_current_user(info, path=path)
        and info.st_mode & 0o077 == 0,
        f"{label} must be an owner-only, non-linked regular file",
    )
    return info


def _private_derived_directory(root: Path, path: Path) -> Path:
    """Resolve the owner-only, non-link directory holding the inventory."""

    resolved = _regular_private_directory(path, "Private derived-cache directory")
    info = path.lstat()
    _require(
        platform_compat.is_owned_by_current_user(info, path=path)
        and info.st_mode & 0o077 == 0
        and path.absolute() == resolved
        and resolved == root / PRIVATE_RELATIVE_PATH.parent,
        "Private derived-cache directory must be owner-only and stay inside "
        "its source cache",
    )
    return resolved


def _rename_noreplace_at(
    directory_fd: int,
    source_name: str,
    destination_name: str,
) -> None:
    """Atomically publish one complete file without replacing a race winner."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise AudioSourceFingerprintError(
            "This Linux system cannot publish the private source-audio "
            "inventory atomically"
        )
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        os.fsencode(source_name),
        directory_fd,
        os.fsencode(destination_name),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return
    value = ctypes.get_errno()
    if value == errno.EEXIST:
        raise _ConcurrentPublication(destination_name)
    if value in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise AudioSourceFingerprintError(
            "The private cache filesystem cannot publish the source-audio "
            "inventory atomically"
        )
    raise OSError(value, os.strerror(value), destination_name)


def _unlink_owned_name_at(
    directory_fd: int,
    name: str,
    identity: tuple[int, int],
) -> bool:
    """Best-effort cleanup that never removes a replacement inode."""

    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return False
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
    ):
        return False
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        return False
    return True


class Nfl2k5AudioSourceFingerprintStore:
    """Build/load the complete private PCM fingerprint set for one XISO."""

    def __init__(
        self,
        *,
        expected_source_sha256: str = SOURCE_SHA256,
        expected_standalone_count: int = EXPECTED_STANDALONE_COUNT,
        expected_streaming_slot_count: int = EXPECTED_STREAMING_SLOT_COUNT,
        expected_streaming_owner_count: int = EXPECTED_STREAMING_OWNER_COUNT,
        progress_interval_items: int = 250,
    ) -> None:
        self.expected_source_sha256 = _sha256_text(
            expected_source_sha256, "expected source SHA-256"
        )
        self.expected_standalone_count = _strict_int(
            expected_standalone_count,
            "expected standalone count",
            minimum=0,
        )
        self.expected_streaming_slot_count = _strict_int(
            expected_streaming_slot_count,
            "expected streaming-slot count",
            minimum=0,
        )
        self.expected_streaming_owner_count = _strict_int(
            expected_streaming_owner_count,
            "expected streaming-owner count",
            minimum=0,
        )
        self.progress_interval_items = _strict_int(
            progress_interval_items, "progress interval"
        )

    def inventory_path(self, cache: SourceCache) -> Path:
        root = self._validate_cache(cache)
        return root / PRIVATE_RELATIVE_PATH

    def load_existing(
        self,
        cache: SourceCache,
        standalone_assets: Iterable[Any],
        streaming_slots: Iterable[CanonicalStreamingSlot],
    ) -> AudioSourceFingerprintInventory | None:
        """Load a complete cache; missing returns ``None``, unsafe never does."""

        root = self._validate_cache(cache)
        expected_standalone = self._expected_standalone(tuple(standalone_assets))
        expected_streaming = self._expected_streaming(tuple(streaming_slots))
        path = root / PRIVATE_RELATIVE_PATH
        if not os.path.lexists(path):
            return None
        return self._load(
            root,
            path,
            cache.source.sha256,
            expected_standalone,
            expected_streaming,
        )

    def ensure(
        self,
        cache: SourceCache,
        standalone_assets: Iterable[Any],
        streaming_slots: Iterable[CanonicalStreamingSlot],
        streaming_pcm_hasher: StreamingPcmHasher,
        *,
        progress: ProgressSink | None = None,
        cancelled: CancellationCheck | None = None,
        publication_guard: PublicationGuard | None = None,
    ) -> AudioSourceFingerprintInventory:
        """Generate once, atomically publish, then reload with full validation."""

        _require(
            publication_guard is None or callable(publication_guard),
            "Private source-audio publication guard is not callable",
        )
        root = self._validate_cache(cache)
        standalone_assets = tuple(standalone_assets)
        streaming_slots = tuple(streaming_slots)
        expected_standalone = self._expected_standalone(standalone_assets)
        expected_streaming = self._expected_streaming(streaming_slots)
        path = root / PRIVATE_RELATIVE_PATH
        if os.path.lexists(path):
            result = self._load(
                root,
                path,
                cache.source.sha256,
                expected_standalone,
                expected_streaming,
            )
            self._emit(progress, "Private source-audio fingerprints ready", 1, 1)
            return result
        _require(callable(streaming_pcm_hasher), "Streaming PCM hasher is not callable")

        total = len(expected_standalone) + len(expected_streaming)
        completed = 0
        self._check_cancelled(cancelled, completed)
        self._emit(progress, "Fingerprinting private source audio", 0, total)
        standalone_rows: list[dict[str, object]] = []
        for row in expected_standalone:
            self._check_cancelled(cancelled, completed)
            standalone_rows.append({
                "asset_id": row.asset_id,
                "channels": row.channels,
                "frame_count": row.frame_count,
                "pcm_sha256": row.pcm_sha256,
                "sample_rate": row.sample_rate,
            })
            completed += 1
            self._emit_periodic(progress, completed, total)

        streaming_rows: list[dict[str, object]] = []
        slot_by_id = {slot.canonical_id: slot for slot in streaming_slots}
        _require(
            set(slot_by_id) == {row.canonical_id for row in expected_streaming},
            "Streaming slots changed while the fingerprint inventory was starting",
        )
        for expected in expected_streaming:
            self._check_cancelled(cancelled, completed)
            digest = _sha256_text(
                streaming_pcm_hasher(slot_by_id[expected.canonical_id]),
                f"decoded PCM SHA-256 for {expected.canonical_id}",
            )
            streaming_rows.append({
                "canonical_id": expected.canonical_id,
                "channels": expected.channels,
                "frame_count": expected.frame_count,
                "owner_asset_ids": list(expected.owner_asset_ids),
                "pcm_sha256": digest,
                "sample_rate": expected.sample_rate,
            })
            completed += 1
            self._emit_periodic(progress, completed, total)

        self._check_cancelled(cancelled, completed)
        document = self._document(
            cache.source.sha256, standalone_rows, streaming_rows
        )
        payload = _canonical_json(document)
        _require(
            0 < len(payload) <= MAX_INVENTORY_BYTES,
            "Private source-audio inventory exceeds its storage bound",
        )
        # Validate the exact bytes before making a name visible in the cache.
        self._parse_document(
            payload,
            path,
            cache.source.sha256,
            expected_standalone,
            expected_streaming,
        )
        try:
            self._atomic_publish(
                root,
                path,
                payload,
                publication_guard=publication_guard,
            )
        except _ConcurrentPublication:
            # Another Mod Studio process won the no-clobber publication race.
            pass
        result = self._load(
            root,
            path,
            cache.source.sha256,
            expected_standalone,
            expected_streaming,
        )
        self._emit(progress, "Private source-audio fingerprints ready", 1, 1)
        return result

    def _validate_cache(self, cache: SourceCache) -> Path:
        _require(isinstance(cache, SourceCache), "Audio fingerprinting needs a source cache")
        source_sha256 = _sha256_text(cache.source.sha256, "source XISO SHA-256")
        _require(
            source_sha256 == self.expected_source_sha256,
            "Private source-audio fingerprints belong to a different XISO",
        )
        _require(
            cache.source.recognized and cache.source.kind == "xiso",
            "Audio fingerprinting needs a recognized NFL 2K5 XISO cache",
        )
        root = _regular_private_directory(cache.root, "NFL 2K5 source cache")
        _require(
            cache.root.absolute() == root,
            "NFL 2K5 source-cache path must be absolute and canonical",
        )
        _require(
            root.name == source_sha256,
            "NFL 2K5 source-cache directory is not bound to its XISO SHA-256",
        )
        return root

    def _expected_standalone(
        self, assets: Iterable[Any]
    ) -> tuple[_ExpectedStandalone, ...]:
        rows: list[_ExpectedStandalone] = []
        seen: set[str] = set()
        for asset in assets:
            asset_id = getattr(asset, "asset_id", None)
            _require(
                isinstance(asset_id, str)
                and _STANDALONE_ID_RE.fullmatch(asset_id) is not None,
                "Standalone fingerprint source has an invalid semantic asset ID",
            )
            _require(asset_id not in seen, f"Standalone asset ID is duplicated: {asset_id}")
            seen.add(asset_id)
            channels, rate, frames = _shape(
                getattr(asset, "channels", None),
                getattr(asset, "sample_rate", None),
                getattr(asset, "frame_count", None),
                asset_id,
            )
            rows.append(_ExpectedStandalone(
                asset_id,
                channels,
                rate,
                frames,
                _sha256_text(
                    getattr(asset, "decoded_pcm_sha256", None),
                    f"decoded PCM SHA-256 for {asset_id}",
                ),
            ))
        rows.sort(key=lambda row: row.asset_id)
        _require(
            len(rows) == self.expected_standalone_count,
            "Standalone fingerprint source is incomplete "
            f"({len(rows):,} found; {self.expected_standalone_count:,} expected)",
        )
        return tuple(rows)

    def _expected_streaming(
        self, slots: Iterable[CanonicalStreamingSlot]
    ) -> tuple[_ExpectedStreaming, ...]:
        rows: list[_ExpectedStreaming] = []
        canonical_ids: set[str] = set()
        owner_ids: set[str] = set()
        for slot in slots:
            _require(
                isinstance(slot, CanonicalStreamingSlot),
                "Streaming fingerprint source is not a canonical slot",
            )
            # Re-run the fixed-slot module's complete codec/allocation check;
            # physical spans are validated but never serialized here.
            streaming_slot_write_plan(slot)
            _require(
                _STREAMING_CANONICAL_ID_RE.fullmatch(slot.canonical_id) is not None,
                "Streaming fingerprint source has an invalid canonical ID",
            )
            _require(
                slot.canonical_id not in canonical_ids,
                f"Streaming canonical ID is duplicated: {slot.canonical_id}",
            )
            canonical_ids.add(slot.canonical_id)
            _require(
                isinstance(slot.owners, tuple),
                f"Streaming slot {slot.canonical_id} has an invalid owner collection",
            )
            owner_values: list[str] = []
            for owner in slot.owners:
                owner_id = getattr(owner, "asset_id", None)
                _require(
                    isinstance(owner_id, str),
                    f"Streaming slot {slot.canonical_id} has an invalid logical owner",
                )
                owner_values.append(owner_id)
            owners = tuple(sorted(owner_values))
            _require(owners, f"Streaming slot {slot.canonical_id} has no logical owner")
            _require(
                len(set(owners)) == len(owners),
                f"Streaming slot {slot.canonical_id} repeats a logical owner",
            )
            for owner_id in owners:
                _require(
                    _STREAMING_OWNER_ID_RE.fullmatch(owner_id) is not None,
                    "Streaming fingerprint source has an invalid logical owner ID",
                )
                _require(
                    owner_id not in owner_ids,
                    f"Streaming logical owner is mapped more than once: {owner_id}",
                )
                owner_ids.add(owner_id)
            channels, rate, frames = _shape(
                slot.channels, slot.sample_rate, slot.frame_count, slot.canonical_id
            )
            rows.append(_ExpectedStreaming(
                slot.canonical_id, owners, channels, rate, frames
            ))
        rows.sort(key=lambda row: row.canonical_id)
        _require(
            len(rows) == self.expected_streaming_slot_count,
            "Canonical streaming fingerprint source is incomplete "
            f"({len(rows):,} found; {self.expected_streaming_slot_count:,} expected)",
        )
        _require(
            len(owner_ids) == self.expected_streaming_owner_count,
            "Streaming owner map is incomplete "
            f"({len(owner_ids):,} found; {self.expected_streaming_owner_count:,} expected)",
        )
        return tuple(rows)

    @staticmethod
    def _emit(
        progress: ProgressSink | None, stage: str, completed: int, total: int
    ) -> None:
        if progress is not None:
            progress(AudioFingerprintProgress(stage, completed, total))

    def _emit_periodic(
        self, progress: ProgressSink | None, completed: int, total: int
    ) -> None:
        if completed == total or completed % self.progress_interval_items == 0:
            self._emit(
                progress, "Fingerprinting private source audio", completed, total
            )

    @staticmethod
    def _check_cancelled(
        cancelled: CancellationCheck | None, completed: int
    ) -> None:
        if cancelled is not None and cancelled():
            raise AudioSourceFingerprintCancelled(
                "Private source-audio fingerprinting was cancelled "
                f"after {completed:,} item(s); no inventory was published"
            )

    @staticmethod
    def _document(
        source_sha256: str,
        standalone: list[dict[str, object]],
        streaming_slots: list[dict[str, object]],
    ) -> dict[str, object]:
        unique_hashes = {
            str(row["pcm_sha256"]) for row in (*standalone, *streaming_slots)
        }
        return {
            "privacy": {
                "audio_payload_bytes": 0,
                "private_user_cache": True,
                "shareable": False,
            },
            "records_sha256": _records_sha256(standalone, streaming_slots),
            "schema": SCHEMA,
            "source": {"xiso_sha256": source_sha256},
            "standalone": standalone,
            "streaming_slots": streaming_slots,
            "summary": {
                "standalone_count": len(standalone),
                "streaming_owner_count": sum(
                    len(row["owner_asset_ids"]) for row in streaming_slots
                ),
                "streaming_slot_count": len(streaming_slots),
                "unique_pcm_sha256_count": len(unique_hashes),
            },
        }

    @staticmethod
    def _atomic_publish(
        root: Path,
        path: Path,
        payload: bytes,
        *,
        publication_guard: PublicationGuard | None = None,
    ) -> None:
        parent = path.parent
        parent.mkdir(mode=0o700, parents=False, exist_ok=True)
        resolved_parent = _regular_private_directory(
            parent, "Private derived-cache directory"
        )
        _require(
            parent.absolute() == resolved_parent
            and resolved_parent == root / PRIVATE_RELATIVE_PATH.parent,
            "Private source-audio inventory path escapes its source cache",
        )
        os.chmod(resolved_parent, 0o700)
        _private_derived_directory(root, parent)

        directory_fd = os.open(
            resolved_parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        descriptor: int | None = None
        temporary_name: str | None = None
        temporary_basename: str | None = None
        staged_identity: tuple[int, int] | None = None
        published_identity: tuple[int, int] | None = None
        try:
            parent_opened = os.fstat(directory_fd)
            parent_named = parent.lstat()
            _require(
                stat.S_ISDIR(parent_opened.st_mode)
                and platform_compat.is_owned_by_current_user(
                    parent_opened, fd=directory_fd
                )
                and (
                    parent_opened.st_dev,
                    parent_opened.st_ino,
                    parent_opened.st_mode & 0o077,
                )
                == (
                    parent_named.st_dev,
                    parent_named.st_ino,
                    0,
                ),
                "Private derived-cache directory changed before publication",
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".audio-source-pcm-fingerprints-v1.",
                suffix=".tmp",
                dir=resolved_parent,
            )
            temporary_basename = Path(temporary_name).name
            initial = os.fstat(descriptor)
            staged_identity = (initial.st_dev, initial.st_ino)
            platform_compat.fchmod(descriptor, 0o600, path=temporary_name)
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise AudioSourceFingerprintError(
                        "Private source-audio inventory write was incomplete"
                    )
                written += count
            os.fsync(descriptor)
            opened = os.fstat(descriptor)
            named = os.stat(
                temporary_basename,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            _require(
                stat.S_ISREG(opened.st_mode)
                and platform_compat.is_owned_by_current_user(
                    opened, fd=descriptor
                )
                and opened.st_mode & 0o077 == 0
                and opened.st_nlink == 1
                and (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    named.st_dev,
                    named.st_ino,
                    named.st_size,
                )
                == (
                    staged_identity[0],
                    staged_identity[1],
                    len(payload),
                    staged_identity[0],
                    staged_identity[1],
                    len(payload),
                ),
                "Private source-audio staging file changed before publication",
            )
            if publication_guard is not None:
                publication_guard("before_publication")
            _rename_noreplace_at(
                directory_fd,
                temporary_basename,
                path.name,
            )
            published_identity = staged_identity
            final = os.stat(
                path.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            _require(
                stat.S_ISREG(final.st_mode)
                and platform_compat.is_owned_by_current_user(final, path=path)
                and final.st_mode & 0o077 == 0
                and final.st_nlink == 1
                and (final.st_dev, final.st_ino, final.st_size)
                == (staged_identity[0], staged_identity[1], len(payload)),
                "Private source-audio inventory changed during publication",
            )
            # Flush the directory descriptor this transaction pinned, rather
            # than re-opening the directory by name and throwing that pin away.
            # POSIX issues the same single fsync as before; Windows has no
            # directory-flush primitive at all and the helper reports that
            # instead of letting a skipped flush look like a completed one.
            platform_compat.fsync_directory_fd(directory_fd)
            os.lseek(descriptor, 0, os.SEEK_SET)
            confirmed = bytearray()
            while len(confirmed) <= len(payload):
                block = os.read(
                    descriptor,
                    min(1024 * 1024, len(payload) + 1 - len(confirmed)),
                )
                if not block:
                    break
                confirmed.extend(block)
            after = os.fstat(descriptor)
            named_after = os.stat(
                path.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            _require(
                bytes(confirmed) == payload
                and stat.S_ISREG(after.st_mode)
                and platform_compat.is_owned_by_current_user(
                    after, fd=descriptor
                )
                and after.st_mode & 0o077 == 0
                and after.st_nlink == 1
                and (
                    named_after.st_dev,
                    named_after.st_ino,
                    named_after.st_size,
                    named_after.st_mtime_ns,
                    named_after.st_ctime_ns,
                    named_after.st_nlink,
                )
                == (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                    after.st_nlink,
                ),
                "Private source-audio inventory changed during publication",
            )
            os.fsync(descriptor)
            platform_compat.fsync_directory_fd(directory_fd)
            if publication_guard is not None:
                publication_guard("after_publication")
        except BaseException:
            if published_identity is not None:
                if _unlink_owned_name_at(
                    directory_fd,
                    path.name,
                    published_identity,
                ):
                    platform_compat.fsync_directory_fd(directory_fd)
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_basename is not None and staged_identity is not None:
                if _unlink_owned_name_at(
                    directory_fd,
                    temporary_basename,
                    staged_identity,
                ):
                    try:
                        platform_compat.fsync_directory_fd(directory_fd)
                    except OSError:
                        pass
            os.close(directory_fd)

    def _load(
        self,
        root: Path,
        path: Path,
        source_sha256: str,
        expected_standalone: tuple[_ExpectedStandalone, ...],
        expected_streaming: tuple[_ExpectedStreaming, ...],
    ) -> AudioSourceFingerprintInventory:
        _private_derived_directory(root, path.parent)
        info = _regular_private_file(path, "Private source-audio inventory")
        _require(
            0 < info.st_size <= MAX_INVENTORY_BYTES,
            "Private source-audio inventory is outside its size bound",
        )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) \
            | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise AudioSourceFingerprintError(
                f"Could not open the private source-audio inventory: {exc}"
            ) from exc
        try:
            opened = os.fstat(descriptor)
            _require(
                stat.S_ISREG(opened.st_mode)
                and opened.st_nlink == 1
                and platform_compat.is_owned_by_current_user(
                    opened, fd=descriptor
                )
                and opened.st_mode & 0o077 == 0
                and (opened.st_dev, opened.st_ino, opened.st_size)
                == (info.st_dev, info.st_ino, info.st_size),
                "Private source-audio inventory changed before it was opened",
            )
            chunks: list[bytes] = []
            remaining = info.st_size
            while remaining:
                block = os.read(descriptor, min(1024 * 1024, remaining))
                _require(block != b"", "Private source-audio inventory read was short")
                chunks.append(block)
                remaining -= len(block)
            _require(
                os.read(descriptor, 1) == b"",
                "Private source-audio inventory grew while it was being read",
            )
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            named = path.lstat()
            _require(
                (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                    named.st_dev,
                    named.st_ino,
                    named.st_size,
                    named.st_mtime_ns,
                    named.st_ctime_ns,
                )
                == (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                ),
                "Private source-audio inventory changed while it was being read",
            )
        except OSError as exc:
            raise AudioSourceFingerprintError(
                f"Could not read the private source-audio inventory: {exc}"
            ) from exc
        finally:
            os.close(descriptor)
        return self._parse_document(
            payload,
            path.resolve(strict=True),
            source_sha256,
            expected_standalone,
            expected_streaming,
        )

    def _parse_document(
        self,
        payload: bytes,
        path: Path,
        source_sha256: str,
        expected_standalone: tuple[_ExpectedStandalone, ...],
        expected_streaming: tuple[_ExpectedStreaming, ...],
    ) -> AudioSourceFingerprintInventory:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AudioSourceFingerprintError(
                f"Private source-audio inventory is not valid JSON: {exc}"
            ) from exc
        _require(isinstance(document, dict), "Private source-audio inventory is not an object")
        _require(
            set(document) == {
                "privacy", "records_sha256", "schema", "source", "standalone",
                "streaming_slots", "summary",
            },
            "Private source-audio inventory has unexpected or missing fields",
        )
        _require(
            payload == _canonical_json(document),
            "Private source-audio inventory is not canonical or was byte-tampered",
        )
        _require(document["schema"] == SCHEMA, "Private source-audio schema is unsupported")
        _require(
            document["source"] == {"xiso_sha256": source_sha256},
            "Private source-audio inventory belongs to a different XISO",
        )
        privacy = document["privacy"]
        _require(
            isinstance(privacy, dict)
            and set(privacy) == {
                "audio_payload_bytes", "private_user_cache", "shareable"
            }
            and type(privacy["audio_payload_bytes"]) is int
            and privacy["audio_payload_bytes"] == 0
            and privacy["private_user_cache"] is True
            and privacy["shareable"] is False,
            "Private source-audio inventory has an unsafe privacy marker",
        )
        standalone_raw = document["standalone"]
        streaming_raw = document["streaming_slots"]
        _require(
            isinstance(standalone_raw, list) and isinstance(streaming_raw, list),
            "Private source-audio inventory record collections are invalid",
        )
        _require(
            document["records_sha256"]
            == _records_sha256(standalone_raw, streaming_raw),
            "Private source-audio inventory record digest does not match",
        )
        expected_standalone_map = {row.asset_id: row for row in expected_standalone}
        expected_streaming_map = {row.canonical_id: row for row in expected_streaming}

        standalone: list[StandalonePcmFingerprint] = []
        seen_standalone: set[str] = set()
        for raw in standalone_raw:
            _require(isinstance(raw, dict), "Standalone fingerprint row is not an object")
            _require(
                set(raw) == {
                    "asset_id", "channels", "frame_count", "pcm_sha256", "sample_rate"
                },
                "Standalone fingerprint row has unexpected or missing fields",
            )
            asset_id = raw["asset_id"]
            _require(isinstance(asset_id, str), "Standalone fingerprint ID is not text")
            _require(
                asset_id not in seen_standalone,
                f"Private source-audio inventory duplicates {asset_id}",
            )
            seen_standalone.add(asset_id)
            expected = expected_standalone_map.get(asset_id)
            _require(expected is not None, f"Unexpected standalone fingerprint: {asset_id}")
            channels, rate, frames = _shape(
                raw["channels"], raw["sample_rate"], raw["frame_count"], asset_id
            )
            digest = _sha256_text(raw["pcm_sha256"], f"PCM SHA-256 for {asset_id}")
            _require(
                (channels, rate, frames, digest)
                == (
                    expected.channels,
                    expected.sample_rate,
                    expected.frame_count,
                    expected.pcm_sha256,
                ),
                f"Standalone fingerprint shape/hash changed for {asset_id}",
            )
            standalone.append(StandalonePcmFingerprint(
                asset_id, channels, rate, frames, digest
            ))
        _require(
            seen_standalone == set(expected_standalone_map),
            "Private source-audio inventory is missing standalone fingerprints",
        )

        streaming: list[StreamingPcmFingerprint] = []
        seen_canonical: set[str] = set()
        seen_owners: set[str] = set()
        for raw in streaming_raw:
            _require(isinstance(raw, dict), "Streaming fingerprint row is not an object")
            _require(
                set(raw) == {
                    "canonical_id", "channels", "frame_count", "owner_asset_ids",
                    "pcm_sha256", "sample_rate",
                },
                "Streaming fingerprint row has unexpected or missing fields",
            )
            canonical_id = raw["canonical_id"]
            _require(isinstance(canonical_id, str), "Streaming canonical ID is not text")
            _require(
                canonical_id not in seen_canonical,
                f"Private source-audio inventory duplicates {canonical_id}",
            )
            seen_canonical.add(canonical_id)
            expected = expected_streaming_map.get(canonical_id)
            _require(expected is not None, f"Unexpected streaming fingerprint: {canonical_id}")
            owners_raw = raw["owner_asset_ids"]
            _require(
                isinstance(owners_raw, list)
                and all(isinstance(owner, str) for owner in owners_raw),
                f"Streaming owner map is invalid for {canonical_id}",
            )
            owners = tuple(owners_raw)
            _require(
                owners == tuple(sorted(set(owners)))
                and owners == expected.owner_asset_ids,
                f"Streaming owner map changed for {canonical_id}",
            )
            for owner in owners:
                _require(
                    owner not in seen_owners,
                    f"Streaming logical owner is mapped more than once: {owner}",
                )
                seen_owners.add(owner)
            channels, rate, frames = _shape(
                raw["channels"], raw["sample_rate"], raw["frame_count"], canonical_id
            )
            _require(
                (channels, rate, frames)
                == (expected.channels, expected.sample_rate, expected.frame_count),
                f"Streaming fingerprint shape changed for {canonical_id}",
            )
            digest = _sha256_text(
                raw["pcm_sha256"], f"PCM SHA-256 for {canonical_id}"
            )
            streaming.append(StreamingPcmFingerprint(
                canonical_id, owners, channels, rate, frames, digest
            ))
        _require(
            seen_canonical == set(expected_streaming_map),
            "Private source-audio inventory is missing streaming fingerprints",
        )
        _require(
            len(seen_owners) == self.expected_streaming_owner_count,
            "Private source-audio inventory has an incomplete streaming owner map",
        )
        standalone.sort(key=lambda row: row.asset_id)
        streaming.sort(key=lambda row: row.canonical_id)
        _require(
            standalone_raw == [
                {
                    "asset_id": row.asset_id,
                    "channels": row.channels,
                    "frame_count": row.frame_count,
                    "pcm_sha256": row.pcm_sha256,
                    "sample_rate": row.sample_rate,
                }
                for row in standalone
            ]
            and streaming_raw == [
                {
                    "canonical_id": row.canonical_id,
                    "channels": row.channels,
                    "frame_count": row.frame_count,
                    "owner_asset_ids": list(row.owner_asset_ids),
                    "pcm_sha256": row.pcm_sha256,
                    "sample_rate": row.sample_rate,
                }
                for row in streaming
            ],
            "Private source-audio fingerprint rows are not deterministically ordered",
        )
        all_hashes = {row.pcm_sha256 for row in (*standalone, *streaming)}
        expected_summary = {
            "standalone_count": len(standalone),
            "streaming_owner_count": len(seen_owners),
            "streaming_slot_count": len(streaming),
            "unique_pcm_sha256_count": len(all_hashes),
        }
        summary = document["summary"]
        _require(
            isinstance(summary, dict)
            and set(summary) == set(expected_summary)
            and all(type(summary[key]) is int for key in expected_summary)
            and summary == expected_summary,
            "Private source-audio inventory summary is incomplete or inconsistent",
        )
        return self._inventory(
            source_sha256, path, tuple(standalone), tuple(streaming)
        )

    @staticmethod
    def _inventory(
        source_sha256: str,
        path: Path,
        standalone: tuple[StandalonePcmFingerprint, ...],
        streaming: tuple[StreamingPcmFingerprint, ...],
    ) -> AudioSourceFingerprintInventory:
        by_asset_id: dict[str, SourcePcmMatch] = {}
        by_hash: dict[str, list[SourcePcmMatch]] = {}
        for row in standalone:
            match = SourcePcmMatch(
                "standalone",
                row.asset_id,
                (row.asset_id,),
                row.channels,
                row.sample_rate,
                row.frame_count,
                row.pcm_sha256,
            )
            by_asset_id[row.asset_id] = match
            by_hash.setdefault(row.pcm_sha256, []).append(match)
        for row in streaming:
            match = SourcePcmMatch(
                "streaming",
                row.canonical_id,
                row.owner_asset_ids,
                row.channels,
                row.sample_rate,
                row.frame_count,
                row.pcm_sha256,
            )
            by_asset_id[row.canonical_id] = match
            for owner in row.owner_asset_ids:
                _require(
                    owner not in by_asset_id,
                    f"Source-audio semantic ID collides across families: {owner}",
                )
                by_asset_id[owner] = match
            by_hash.setdefault(row.pcm_sha256, []).append(match)
        frozen_hashes = {
            digest: tuple(sorted(matches, key=lambda row: (row.family, row.canonical_id)))
            for digest, matches in by_hash.items()
        }
        return AudioSourceFingerprintInventory(
            source_sha256=source_sha256,
            path=path,
            standalone=standalone,
            streaming_slots=streaming,
            by_asset_id=MappingProxyType(by_asset_id),
            by_pcm_sha256=MappingProxyType(frozen_hashes),
        )


__all__ = [
    "AudioFingerprintProgress",
    "AudioSourceFingerprintCancelled",
    "AudioSourceFingerprintError",
    "AudioSourceFingerprintInventory",
    "EXPECTED_STANDALONE_COUNT",
    "EXPECTED_STREAMING_OWNER_COUNT",
    "EXPECTED_STREAMING_SLOT_COUNT",
    "Nfl2k5AudioSourceFingerprintStore",
    "PRIVATE_RELATIVE_PATH",
    "PublicationGuard",
    "SCHEMA",
    "SourceDerivedPcmError",
    "SourcePcmMatch",
    "StandalonePcmFingerprint",
    "StreamingPcmFingerprint",
]
