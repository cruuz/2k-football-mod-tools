"""Authenticated private source pipeline for NFL 2K5 PCM containment.

The reviewed containment engine accepts ephemeral decoded PCM and returns a
digest-only private document.  This module supplies its source and publication
boundary: every cue is decoded directly from one read-only, exactly pinned
XISO descriptor, and only the reviewed canonical containment document may be
published beneath that source's private cache.

No WAV, PCM, encoded audio, archive span, source path, or rollback byte is
written.  Existing private inventories are reusable only after their complete
shape/owner/source contract and canonical bytes validate; malformed cache data
is never repaired in place.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Iterable, Mapping

from .errors import ValidationError
from .nfl2k5_audio_catalog import (
    CAPACITY_REPORT,
    Nfl2k5StreamingAudioRange,
)
from .nfl2k5_audio_containment_fingerprints import (
    AudioContainmentFingerprintCancelled,
    AudioContainmentFingerprintError,
    MAX_PCM_BYTES,
    PcmContainmentInventory,
    PcmContainmentPolicy,
    PcmContainmentProgress,
    ShortCueAnchorShape,
    SourcePcmCueInput,
    build_private_containment_inventory,
)
from . import nfl2k5_audio_source_fingerprints as private_cache
from .nfl2k5_audio_source_scan import (
    MAX_CAPACITY_REPORT_BYTES,
    AudioSourceScanPins,
    BatchDecoder,
    Nfl2k5AudioSourceScanner,
    XdvdfsParser,
    _read_authenticated_file,
    _sha256_fd,
    decode_xbox_ima_batch,
    xiso,
)
from .nfl2k5_ausb_fixed_slots import (
    CanonicalStreamingSlot,
    build_streaming_slot_catalog,
    streaming_slot_write_plan,
)
from .nfl2k5_source_cache import SourceCache
from . import platform_compat


EXPECTED_SOURCE_CUE_COUNT = 54_420
EXPECTED_SOURCE_OWNER_COUNT = 54_421
PRIVATE_RELATIVE_PATH = Path(
    "derived/audio-source-pcm-containment-v2.json"
)
MAX_PRIVATE_DOCUMENT_BYTES = 512 * 1024 * 1024
READ_BLOCK = 1024 * 1024
_PRIVATE_PARENT_NAME = PRIVATE_RELATIVE_PATH.parent.as_posix()
_STAGING_PREFIX = ".audio-source-pcm-containment-v2."
_STAGING_SUFFIX = ".tmp"
_STAGING_CREATE_ATTEMPTS = 128

_STANDALONE_ID_RE = re.compile(
    r"^nfl2k5\.audio\.audo\.o([0-9]{4})\.c([0-9]{4})$"
)
_STREAMING_OWNER_ID_RE = re.compile(
    r"^nfl2k5\.audio\.ausb\.o([0-9]{4})\.c([0-9]{4})\.r([0-9]{5})$"
)


class AudioSourceContainmentError(ValidationError):
    """Authenticated source containment could not complete safely."""


@dataclass(frozen=True, slots=True)
class AudioSourceContainmentProgress:
    stage: str
    completed: int
    total: int
    unit: str
    fingerprint_records: int = 0


@dataclass(frozen=True, slots=True)
class AudioSourceContainmentResult:
    inventory: PcmContainmentInventory
    inventory_path: Path
    source_path: Path
    source_cue_count: int
    source_owner_count: int
    standalone_count: int
    streaming_slot_count: int
    streaming_owner_count: int
    reused_inventory: bool
    elapsed_seconds: float


ProgressSink = Callable[[AudioSourceContainmentProgress], None]
CancellationCheck = Callable[[], bool]
PublicationGuard = Callable[[str], None]
InventoryBuilder = Callable[[], PcmContainmentInventory]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioSourceContainmentError(message)


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


def _emit(
    progress: ProgressSink | None,
    stage: str,
    completed: int,
    total: int,
    unit: str,
    fingerprint_records: int = 0,
) -> None:
    if progress is not None:
        progress(AudioSourceContainmentProgress(
            stage,
            completed,
            total,
            unit,
            fingerprint_records,
        ))


def _check_cancel(cancelled: CancellationCheck | None, stage: str) -> None:
    if cancelled is not None and cancelled():
        raise AudioContainmentFingerprintCancelled(
            f"{stage} was cancelled; no containment inventory was published"
        )


def _owner_ids(value: Iterable[str], expected_count: int) -> tuple[str, ...]:
    _require(not isinstance(value, (str, bytes)), "Source owner IDs are invalid")
    result = tuple(value)
    try:
        valid_items = all(
            type(item) is str
            and bool(item)
            and len(item.encode("utf-8")) <= 256
            and (
                _STANDALONE_ID_RE.fullmatch(item) is not None
                or _STREAMING_OWNER_ID_RE.fullmatch(item) is not None
            )
            for item in result
        )
        unique = len(set(result)) == len(result)
        ordered = result == tuple(sorted(result))
    except (TypeError, UnicodeEncodeError):
        valid_items = False
        unique = False
        ordered = False
    _require(
        len(result) == expected_count
        and unique
        and ordered
        and valid_items,
        "Source containment owner coverage is invalid",
    )
    return result


def _regular_directory(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise AudioSourceContainmentError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a non-link directory",
    )
    return path.resolve(strict=True)


class Nfl2k5AudioSourceContainmentStore:
    """Strict private-cache loader and no-clobber atomic publisher."""

    def __init__(
        self,
        *,
        expected_source_sha256: str,
        expected_cue_count: int = EXPECTED_SOURCE_CUE_COUNT,
        expected_owner_count: int = EXPECTED_SOURCE_OWNER_COUNT,
        maximum_serialized_bytes: int = MAX_PRIVATE_DOCUMENT_BYTES,
    ) -> None:
        _require(
            isinstance(expected_source_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256) is not None,
            "Expected source XISO SHA-256 is invalid",
        )
        _require(
            type(expected_cue_count) is int and expected_cue_count > 0,
            "Expected source cue count is invalid",
        )
        _require(
            type(expected_owner_count) is int
            and expected_owner_count >= expected_cue_count,
            "Expected source owner count is invalid",
        )
        _require(
            type(maximum_serialized_bytes) is int
            and 1 <= maximum_serialized_bytes <= MAX_PRIVATE_DOCUMENT_BYTES,
            "Private containment serialized-byte cap is invalid",
        )
        self.expected_source_sha256 = expected_source_sha256
        self.expected_cue_count = expected_cue_count
        self.expected_owner_count = expected_owner_count
        self.maximum_serialized_bytes = maximum_serialized_bytes

    def inventory_path(self, cache: SourceCache) -> Path:
        root = self._validate_cache(cache)
        return root / PRIVATE_RELATIVE_PATH

    def load_existing(
        self,
        cache: SourceCache,
        policy: PcmContainmentPolicy,
        expected_owner_ids: Iterable[str],
    ) -> PcmContainmentInventory | None:
        root = self._validate_cache(cache)
        owners = _owner_ids(expected_owner_ids, self.expected_owner_count)
        path = root / PRIVATE_RELATIVE_PATH
        if not os.path.lexists(path):
            return None
        return self._load(root, path, policy, owners)

    def ensure(
        self,
        cache: SourceCache,
        policy: PcmContainmentPolicy,
        expected_owner_ids: Iterable[str],
        builder: InventoryBuilder,
        *,
        publication_guard: PublicationGuard,
        cancelled: CancellationCheck | None = None,
    ) -> tuple[PcmContainmentInventory, bool]:
        """Load or build once; return ``(inventory, reused)``."""

        _require(isinstance(policy, PcmContainmentPolicy), "Containment policy is invalid")
        _require(callable(builder), "Containment inventory builder is not callable")
        _require(
            callable(publication_guard),
            "Containment publication guard is not callable",
        )
        root = self._validate_cache(cache)
        owners = _owner_ids(expected_owner_ids, self.expected_owner_count)
        path = root / PRIVATE_RELATIVE_PATH
        if os.path.lexists(path):
            return self._load(root, path, policy, owners), True

        _check_cancel(cancelled, "Source PCM containment build")
        inventory = builder()
        self._validate_inventory(inventory, policy, owners)
        _check_cancel(cancelled, "Source PCM containment publication")
        payload = _canonical_json(inventory.to_private_document())
        _require(
            0 < len(payload) <= self.maximum_serialized_bytes,
            "Private containment inventory exceeds its serialized-byte cap",
        )
        parsed = self._parse(payload, policy, owners)
        _require(
            parsed == inventory,
            "Private containment inventory changed during serialization",
        )
        reused = False
        try:
            self._atomic_publish(
                root,
                path,
                payload,
                publication_guard=publication_guard,
            )
        except private_cache._ConcurrentPublication:
            reused = True
        inventory = self._load(root, path, policy, owners)
        if reused:
            # The winning file is foreign and must never be rolled back here,
            # but its acceptance still needs the post-publication source guard.
            publication_guard("after_publication")
        return inventory, reused

    def _validate_cache(self, cache: SourceCache) -> Path:
        _require(isinstance(cache, SourceCache), "Containment needs a source cache")
        _require(
            cache.source.sha256 == self.expected_source_sha256
            and cache.source.recognized
            and cache.source.kind == "xiso",
            "Containment cache belongs to a different or unsupported source",
        )
        root = _regular_directory(cache.root, "NFL 2K5 source cache")
        _require(
            platform_compat.is_canonical_absolute_path(cache.root, root)
            and root.name == self.expected_source_sha256,
            "NFL 2K5 source-cache path is not canonical and source-bound",
        )
        return root

    @staticmethod
    def _directory_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )

    def _verify_open_parent(
        self,
        root: Path,
        root_fd: int,
        parent_fd: int,
        stage: str,
    ) -> None:
        """Prove both open directory handles still own their canonical names."""

        try:
            root_opened = os.fstat(root_fd)
            root_named = root.lstat()
            parent_opened = os.fstat(parent_fd)
            parent_named = os.stat(
                _PRIVATE_PARENT_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise AudioSourceContainmentError(
                f"Private containment-cache directory changed during {stage}: {exc}"
            ) from exc
        _require(
            stat.S_ISDIR(root_opened.st_mode)
            and stat.S_ISDIR(root_named.st_mode)
            and (root_opened.st_dev, root_opened.st_ino)
            == (root_named.st_dev, root_named.st_ino)
            and stat.S_ISDIR(parent_opened.st_mode)
            and stat.S_ISDIR(parent_named.st_mode)
            # Ownership is asked through platform_compat rather than compared as
            # a raw uid: Windows reports st_uid == 0 for every file, so an inline
            # comparison would degrade into a check that always passes there.
            and platform_compat.is_owned_by_current_user(
                parent_opened, fd=parent_fd
            )
            and (
                parent_opened.st_dev,
                parent_opened.st_ino,
                parent_opened.st_mode & 0o777,
            )
            == (
                parent_named.st_dev,
                parent_named.st_ino,
                0o700,
            ),
            f"Private containment-cache directory changed during {stage}",
        )

    def _open_private_parent(
        self,
        root: Path,
        *,
        create: bool,
    ) -> tuple[int, int]:
        """Open the source root and its private child without following links."""

        _require(
            _PRIVATE_PARENT_NAME
            and "/" not in _PRIVATE_PARENT_NAME
            and root / PRIVATE_RELATIVE_PATH.parent
            == root / _PRIVATE_PARENT_NAME,
            "Private containment-cache path contract is invalid",
        )
        flags = self._directory_flags()
        try:
            root_fd = os.open(root, flags)
        except OSError as exc:
            raise AudioSourceContainmentError(
                f"Could not open NFL 2K5 source cache safely: {exc}"
            ) from exc
        parent_fd: int | None = None
        try:
            root_opened = os.fstat(root_fd)
            root_named = root.lstat()
            _require(
                stat.S_ISDIR(root_opened.st_mode)
                and stat.S_ISDIR(root_named.st_mode)
                and (root_opened.st_dev, root_opened.st_ino)
                == (root_named.st_dev, root_named.st_ino),
                "NFL 2K5 source cache changed before private-cache access",
            )
            if create:
                try:
                    os.mkdir(_PRIVATE_PARENT_NAME, 0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            try:
                parent_fd = os.open(
                    _PRIVATE_PARENT_NAME,
                    flags,
                    dir_fd=root_fd,
                )
            except OSError as exc:
                raise AudioSourceContainmentError(
                    "Private containment-cache directory must be a non-link "
                    f"directory: {exc}"
                ) from exc
            opened = os.fstat(parent_fd)
            named = os.stat(
                _PRIVATE_PARENT_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
            _require(
                stat.S_ISDIR(opened.st_mode)
                and stat.S_ISDIR(named.st_mode)
                and platform_compat.is_owned_by_current_user(
                    opened, fd=parent_fd
                )
                and (opened.st_dev, opened.st_ino)
                == (named.st_dev, named.st_ino),
                "Private containment-cache directory is not source-confined",
            )
            if create:
                platform_compat.fchmod(parent_fd, 0o700, path=root / _PRIVATE_PARENT_NAME)
            self._verify_open_parent(
                root,
                root_fd,
                parent_fd,
                "private-cache open",
            )
            return root_fd, parent_fd
        except BaseException:
            if parent_fd is not None:
                os.close(parent_fd)
            os.close(root_fd)
            raise

    @staticmethod
    def _create_staging_file(directory_fd: int) -> tuple[int, str]:
        """Create a private temp file relative to the already-verified dirfd."""

        flags = (
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        for _attempt in range(_STAGING_CREATE_ATTEMPTS):
            basename = f"{_STAGING_PREFIX}{os.urandom(16).hex()}{_STAGING_SUFFIX}"
            try:
                descriptor = os.open(
                    basename,
                    flags | getattr(os, "O_BINARY", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            return descriptor, basename
        raise AudioSourceContainmentError(
            "Could not allocate a unique private containment staging file"
        )

    def _validate_inventory(
        self,
        inventory: PcmContainmentInventory,
        policy: PcmContainmentPolicy,
        owners: tuple[str, ...],
    ) -> None:
        _require(
            isinstance(inventory, PcmContainmentInventory)
            and inventory.source_binding_sha256 == self.expected_source_sha256
            and inventory.policy == policy
            and inventory.source_cue_count == self.expected_cue_count
            and inventory.source_owner_ids == owners
            and inventory.private is True
            and inventory.shareable is False,
            "Private containment inventory is incomplete or source-mismatched",
        )

    def _load(
        self,
        root: Path,
        path: Path,
        policy: PcmContainmentPolicy,
        owners: tuple[str, ...],
    ) -> PcmContainmentInventory:
        _require(
            path == root / PRIVATE_RELATIVE_PATH,
            "Private containment inventory path escapes its source cache",
        )
        root_fd, directory_fd = self._open_private_parent(root, create=False)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            try:
                named = os.stat(
                    path.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError as exc:
                raise AudioSourceContainmentError(
                    f"Private containment inventory is missing: {path}"
                ) from exc
            _require(
                stat.S_ISREG(named.st_mode)
                and platform_compat.is_owned_by_current_user(named, path=path)
                and named.st_nlink == 1
                and named.st_mode & 0o777 == 0o600,
                "Private containment inventory must be a mode-0600, non-linked file",
            )
            _require(
                0 < named.st_size <= self.maximum_serialized_bytes,
                "Private containment inventory is outside its serialized-byte cap",
            )
            try:
                descriptor = os.open(
                    path.name,
                    flags | getattr(os, "O_BINARY", 0),
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                raise AudioSourceContainmentError(
                    f"Could not open private containment inventory: {exc}"
                ) from exc
            try:
                opened = os.fstat(descriptor)
                _require(
                    stat.S_ISREG(opened.st_mode)
                    and platform_compat.is_owned_by_current_user(
                        opened, fd=descriptor
                    )
                    and opened.st_nlink == 1
                    and opened.st_mode & 0o777 == 0o600
                    and (opened.st_dev, opened.st_ino, opened.st_size)
                    == (named.st_dev, named.st_ino, named.st_size),
                    "Private containment inventory changed before it was opened",
                )
                chunks: list[bytes] = []
                remaining = opened.st_size
                while remaining:
                    block = os.read(descriptor, min(READ_BLOCK, remaining))
                    _require(bool(block), "Private containment inventory read was short")
                    chunks.append(block)
                    remaining -= len(block)
                _require(
                    os.read(descriptor, 1) == b"",
                    "Private containment inventory grew while it was read",
                )
                payload = b"".join(chunks)
                after = os.fstat(descriptor)
                named_after = os.stat(
                    path.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                _require(
                    (
                        after.st_dev,
                        after.st_ino,
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                        named_after.st_dev,
                        named_after.st_ino,
                        named_after.st_size,
                        named_after.st_mtime_ns,
                        named_after.st_ctime_ns,
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
                    "Private containment inventory changed while it was read",
                )
                self._verify_open_parent(
                    root,
                    root_fd,
                    directory_fd,
                    "private inventory read",
                )
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_fd)
            os.close(root_fd)
        return self._parse(payload, policy, owners)

    def _parse(
        self,
        payload: bytes,
        policy: PcmContainmentPolicy,
        owners: tuple[str, ...],
    ) -> PcmContainmentInventory:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AudioSourceContainmentError(
                f"Private containment inventory is not valid JSON: {exc}"
            ) from exc
        _require(
            isinstance(document, dict) and payload == _canonical_json(document),
            "Private containment inventory is not canonical or was byte-tampered",
        )
        try:
            inventory = PcmContainmentInventory.from_private_document(document)
        except AudioContainmentFingerprintError as exc:
            raise AudioSourceContainmentError(str(exc)) from exc
        self._validate_inventory(inventory, policy, owners)
        return inventory

    def _atomic_publish(
        self,
        root: Path,
        path: Path,
        payload: bytes,
        *,
        publication_guard: PublicationGuard,
    ) -> None:
        _require(
            path == root / PRIVATE_RELATIVE_PATH,
            "Private containment-cache directory escapes its source cache",
        )
        root_fd, directory_fd = self._open_private_parent(root, create=True)
        descriptor: int | None = None
        temporary_basename: str | None = None
        staged_identity: tuple[int, int] | None = None
        published_identity: tuple[int, int] | None = None
        try:
            descriptor, temporary_basename = self._create_staging_file(
                directory_fd
            )
            initial = os.fstat(descriptor)
            staged_identity = (initial.st_dev, initial.st_ino)
            platform_compat.fchmod(descriptor, 0o600, path=path.parent / temporary_basename)
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                _require(count > 0, "Private containment inventory write was incomplete")
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
                and opened.st_nlink == 1
                and opened.st_mode & 0o777 == 0o600
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
                "Private containment staging file changed before publication",
            )
            self._verify_open_parent(
                root,
                root_fd,
                directory_fd,
                "containment staging",
            )
            publication_guard("before_publication")
            self._verify_open_parent(
                root,
                root_fd,
                directory_fd,
                "pre-publication authorization",
            )
            private_cache._rename_noreplace_at(
                directory_fd,
                temporary_basename,
                path.name,
            )
            published_identity = staged_identity
            final = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            _require(
                stat.S_ISREG(final.st_mode)
                and platform_compat.is_owned_by_current_user(final, path=path)
                and final.st_nlink == 1
                and final.st_mode & 0o777 == 0o600
                and (final.st_dev, final.st_ino, final.st_size)
                == (staged_identity[0], staged_identity[1], len(payload)),
                "Private containment inventory changed during publication",
            )
            self._verify_open_parent(
                root,
                root_fd,
                directory_fd,
                "containment publication",
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
                    min(READ_BLOCK, len(payload) + 1 - len(confirmed)),
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
                and after.st_nlink == 1
                and after.st_mode & 0o777 == 0o600
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
                "Private containment inventory changed during publication",
            )
            os.fsync(descriptor)
            platform_compat.fsync_directory_fd(directory_fd)
            publication_guard("after_publication")
            self._verify_open_parent(
                root,
                root_fd,
                directory_fd,
                "post-publication authorization",
            )
        except BaseException:
            if published_identity is not None:
                if private_cache._unlink_owned_name_at(
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
                if private_cache._unlink_owned_name_at(
                    directory_fd,
                    temporary_basename,
                    staged_identity,
                ):
                    try:
                        platform_compat.fsync_directory_fd(directory_fd)
                    except OSError:
                        pass
            os.close(directory_fd)
            os.close(root_fd)


class Nfl2k5AudioSourceContainmentScanner:
    """Build/load the complete private containment inventory from one XISO."""

    def __init__(
        self,
        *,
        pins: AudioSourceScanPins = AudioSourceScanPins(),
        capacity_report: Path = CAPACITY_REPORT,
        store: Nfl2k5AudioSourceContainmentStore | None = None,
        xdvdfs_parser: XdvdfsParser = xiso.parse_xdvdfs,
        batch_decoder: BatchDecoder = decode_xbox_ima_batch,
        decode_batch_bytes: int = 4 * 1024 * 1024,
        maximum_serialized_bytes: int = MAX_PRIVATE_DOCUMENT_BYTES,
    ) -> None:
        self.source_scanner = Nfl2k5AudioSourceScanner(
            pins=pins,
            capacity_report=capacity_report,
            xdvdfs_parser=xdvdfs_parser,
            batch_decoder=batch_decoder,
            decode_batch_bytes=decode_batch_bytes,
        )
        expected_cues = pins.standalone_count + pins.streaming_slot_count
        expected_owners = pins.standalone_count + pins.streaming_owner_count
        _require(
            expected_cues > 0 and expected_owners >= expected_cues,
            "Source containment count contract is invalid",
        )
        self.store = store or Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=pins.source_sha256,
            expected_cue_count=expected_cues,
            expected_owner_count=expected_owners,
            maximum_serialized_bytes=maximum_serialized_bytes,
        )

    def ensure(
        self,
        source_xiso: Path,
        cache: SourceCache,
        *,
        progress: ProgressSink | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> AudioSourceContainmentResult:
        started = time.monotonic()
        scanner = self.source_scanner
        pins = scanner.pins
        scan_progress = self._scan_progress(progress)
        source = scanner._open_source(source_xiso, cache)
        try:
            digest = _sha256_fd(
                source.descriptor,
                offset=0,
                length=pins.source_size,
                stage="Authenticating source XISO for PCM containment",
                progress=scan_progress,
                cancelled=cancelled,
            )
            _require(
                digest == pins.source_sha256,
                "Source XISO SHA-256 is not the supported retail dump",
            )
            scanner._verify_source_identity(
                source, "initial containment source authentication"
            )
            _read_authenticated_file(
                cache.pack0,
                expected_size=pins.pack0_size,
                expected_sha256=pins.pack0_sha256,
                capture=False,
                stage="Authenticating private pack-0 index for containment",
                progress=scan_progress,
                cancelled=cancelled,
            )
            inventory_payload = _read_authenticated_file(
                cache.inventory,
                expected_size=pins.inventory_size,
                expected_sha256=pins.inventory_sha256,
                capture=True,
                stage="Authenticating private resource inventory for containment",
                progress=scan_progress,
                cancelled=cancelled,
            )
            assert inventory_payload is not None
            try:
                capacity_info = scanner.capacity_report.lstat()
            except FileNotFoundError as exc:
                raise AudioSourceContainmentError(
                    f"Shipped standalone-audio metadata is missing: "
                    f"{scanner.capacity_report}"
                ) from exc
            _require(
                stat.S_ISREG(capacity_info.st_mode)
                and not stat.S_ISLNK(capacity_info.st_mode)
                and 0 < capacity_info.st_size <= MAX_CAPACITY_REPORT_BYTES,
                "Shipped standalone-audio metadata is not a bounded regular file",
            )
            capacity_payload = _read_authenticated_file(
                scanner.capacity_report,
                expected_size=capacity_info.st_size,
                expected_sha256=pins.capacity_report_sha256,
                capture=True,
                stage="Authenticating standalone metadata for containment",
                progress=scan_progress,
                cancelled=cancelled,
            )
            assert capacity_payload is not None
            try:
                entries, _directory = scanner.xdvdfs_parser(
                    source.descriptor, pins.source_size
                )
            except (OSError, ValueError) as exc:
                raise AudioSourceContainmentError(
                    f"Could not parse source XDVDFS for containment: {exc}"
                ) from exc
            extents = scanner._pack_extents(entries)
            pack0_digest = _sha256_fd(
                source.descriptor,
                offset=extents["0"].byte_offset,
                length=extents["0"].size,
                stage="Authenticating source pack-0 extent for containment",
                progress=scan_progress,
                cancelled=cancelled,
            )
            _require(
                pack0_digest == pins.pack0_sha256,
                "Source pack-0 extent disagrees with the authenticated cache",
            )
            archive = scanner._parse_source_archive(
                source.descriptor, source.path, extents
            )
            inventory_document = scanner._json_object(
                inventory_payload, "private resource inventory"
            )
            capacity_document = scanner._json_object(
                capacity_payload, "standalone-audio metadata"
            )
            standalone = scanner._standalone_sources(
                source.descriptor,
                archive,
                extents,
                capacity_document,
                inventory_document,
                scan_progress,
                cancelled,
            )
            banks = scanner._streaming_banks(
                source.descriptor,
                archive,
                extents,
                inventory_document,
            )
            ranges = tuple(
                Nfl2k5StreamingAudioRange(bank, index, start, end)
                for bank in banks
                for index, (start, end) in enumerate(
                    zip(bank.boundaries, bank.boundaries[1:])
                )
            )
            _require(
                len(ranges) == pins.streaming_range_count,
                "Authenticated descriptors expose the wrong streaming-range count",
            )
            try:
                slot_catalog = build_streaming_slot_catalog(ranges, archive)
            except ValueError as exc:
                raise AudioSourceContainmentError(
                    f"Could not canonicalize containment source slots: {exc}"
                ) from exc
            scanner._validate_slot_catalog(slot_catalog)
            slots = slot_catalog.slots
            expected_cues = len(standalone) + len(slots)
            owner_ids = tuple(sorted(
                [item.asset_id for item in standalone]
                + [owner.asset_id for slot in slots for owner in slot.owners]
            ))
            expected_owners = len(owner_ids)
            _require(
                expected_cues == self.store.expected_cue_count
                and expected_owners == self.store.expected_owner_count,
                "Authenticated source containment coverage is incomplete",
            )
            policy = self._policy(standalone, slots)
            state = {"built": False, "source_verified": False}

            def builder() -> PcmContainmentInventory:
                state["built"] = True
                return build_private_containment_inventory(
                    pins.source_sha256,
                    policy,
                    self._source_cues(
                        source.descriptor,
                        archive,
                        extents,
                        inventory_document,
                        standalone,
                        slots,
                        cancelled,
                    ),
                    expected_cue_count=expected_cues,
                    expected_owner_count=expected_owners,
                    cancel=cancelled,
                    progress=self._containment_progress(progress),
                )

            def publication_guard(stage: str) -> None:
                _require(
                    stage in ("before_publication", "after_publication"),
                    "Containment store requested an unknown publication phase",
                )
                if stage == "before_publication":
                    scanner._final_source_hash(source, scan_progress, cancelled)
                    scanner._verify_source_identity(
                        source, "pre-publication containment source recheck"
                    )
                    state["source_verified"] = True
                else:
                    _require(
                        state["source_verified"],
                        "Containment inventory published before its source recheck",
                    )
                    scanner._verify_source_identity(
                        source, "post-publication containment source recheck"
                    )

            inventory, reused = self.store.ensure(
                cache,
                policy,
                owner_ids,
                builder,
                publication_guard=publication_guard,
                cancelled=cancelled,
            )
            if not state["built"]:
                scanner._final_source_hash(source, scan_progress, cancelled)
                scanner._verify_source_identity(
                    source, "reused containment source recheck"
                )
            else:
                _require(
                    state["source_verified"],
                    "Containment inventory reached publication without a source recheck",
                )
            _emit(
                progress,
                "Private PCM containment inventory ready",
                expected_cues,
                expected_cues,
                "cues",
                inventory.fingerprint_count,
            )
            return AudioSourceContainmentResult(
                inventory=inventory,
                inventory_path=self.store.inventory_path(cache),
                source_path=source.path,
                source_cue_count=expected_cues,
                source_owner_count=expected_owners,
                standalone_count=len(standalone),
                streaming_slot_count=len(slots),
                streaming_owner_count=sum(len(slot.owners) for slot in slots),
                reused_inventory=reused,
                elapsed_seconds=time.monotonic() - started,
            )
        finally:
            os.close(source.descriptor)

    @staticmethod
    def _scan_progress(progress: ProgressSink | None):
        if progress is None:
            return None

        def adapt(event: object) -> None:
            _emit(
                progress,
                str(getattr(event, "stage")),
                int(getattr(event, "completed")),
                int(getattr(event, "total")),
                str(getattr(event, "unit")),
            )

        return adapt

    @staticmethod
    def _containment_progress(progress: ProgressSink | None):
        if progress is None:
            return None

        def adapt(event: PcmContainmentProgress) -> None:
            _emit(
                progress,
                event.stage,
                event.completed_units,
                event.total_units,
                "cues",
                event.fingerprint_records,
            )

        return adapt

    @staticmethod
    def _policy(
        standalone: Iterable[object],
        slots: Iterable[CanonicalStreamingSlot],
    ) -> PcmContainmentPolicy:
        minimum_short: dict[tuple[int, int], int] = {}
        shapes = [
            (
                int(getattr(item, "channels")),
                int(getattr(item, "sample_rate")),
                int(getattr(item, "frame_count")),
            )
            for item in standalone
        ] + [
            (slot.channels, slot.sample_rate, slot.frame_count) for slot in slots
        ]
        for channels, sample_rate, frame_count in shapes:
            long_frames = sample_rate // 4
            _require(
                channels in (1, 2)
                and sample_rate > 0
                and frame_count > 0
                and long_frames > 0,
                "Authenticated containment PCM shape is invalid",
            )
            if frame_count < long_frames:
                key = (channels, sample_rate)
                minimum_short[key] = min(
                    minimum_short.get(key, frame_count), frame_count
                )
        anchors = tuple(
            ShortCueAnchorShape(channels, sample_rate, frames)
            for (channels, sample_rate), frames in sorted(minimum_short.items())
        )
        return PcmContainmentPolicy(anchors)

    def _source_cues(
        self,
        descriptor: int,
        archive: object,
        extents: Mapping[str, object],
        inventory: Mapping[str, object],
        standalone: Iterable[object],
        slots: Iterable[CanonicalStreamingSlot],
        cancelled: CancellationCheck | None,
    ):
        yield from self._standalone_cues(
            descriptor,
            archive,
            extents,
            inventory,
            standalone,
            cancelled,
        )
        for slot in slots:
            _check_cancel(cancelled, "Streaming containment source decode")
            encoded_parts: list[bytes] = []
            for span in streaming_slot_write_plan(slot):
                extent = extents.get(span.pack_name)
                _require(extent is not None, "Streaming cue names an absent XISO pack")
                encoded_parts.append(self.source_scanner._source_read(
                    descriptor,
                    extent,
                    span.pack_offset,
                    span.length,
                ))
            encoded = b"".join(encoded_parts)
            _require(
                len(encoded) == slot.encoded_size,
                "Streaming containment cue read was incomplete",
            )
            pcm = self.source_scanner.batch_decoder(
                encoded, slot.channels, cancelled
            )
            _require(
                len(pcm) == slot.frame_count * slot.channels * 2
                and len(pcm) <= MAX_PCM_BYTES,
                "Streaming containment cue decoded to an invalid PCM size",
            )
            yield SourcePcmCueInput(
                owner_asset_ids=tuple(sorted(
                    owner.asset_id for owner in slot.owners
                )),
                channels=slot.channels,
                sample_rate=slot.sample_rate,
                frame_count=slot.frame_count,
                pcm16le=pcm,
            )

    def _standalone_cues(
        self,
        descriptor: int,
        archive: object,
        extents: Mapping[str, object],
        inventory: Mapping[str, object],
        standalone: Iterable[object],
        cancelled: CancellationCheck | None,
    ):
        from nfl_scene_probe import ResourceRecord, decode_resource, probe_audo

        chunks = inventory.get("chunks")
        _require(isinstance(chunks, list), "Resource inventory has no chunk rows")
        indexed = {
            (int(row["outer_index"]), int(row["chunk_index"])): row
            for row in chunks
            if isinstance(row, dict) and row.get("kind") == "AUDO"
        }
        entries = getattr(archive, "entries")
        for item in standalone:
            _check_cancel(cancelled, "Standalone containment source decode")
            asset_id = str(getattr(item, "asset_id"))
            matched = _STANDALONE_ID_RE.fullmatch(asset_id)
            _require(matched is not None, "Standalone containment ID is invalid")
            selector = (int(matched.group(1)), int(matched.group(2)))
            row = indexed.get(selector)
            _require(row is not None, "Standalone containment owner is missing")
            entry = entries[selector[0]]
            word_10 = int(str(row["word_10"]), 0)
            record = ResourceRecord(
                outer_index=selector[0],
                outer_id=str(row["outer_id"]),
                outer_size=int(row["outer_size"]),
                chunk_index=selector[1],
                chunk_offset=int(row["chunk_offset"]),
                kind="AUDO",
                stored_size=int(row["stored_size"]),
                word_08=int(row["word_08"]),
                word_0c=int(row["word_0c"]),
                word_10=word_10,
                word_14=int(row["word_14"]),
            )
            span = self.source_scanner._entry_read(
                descriptor,
                extents,
                entry,
                record.chunk_offset,
                0x20 + record.stored_size,
            )
            body, _detail = decode_resource(span, record)
            semantic = probe_audo(body, record, True)
            channels = int(getattr(item, "channels"))
            sample_rate = int(getattr(item, "sample_rate"))
            frame_count = int(getattr(item, "frame_count"))
            _require(
                semantic.get("channels") == channels
                and semantic.get("sample_rate") == sample_rate
                and semantic.get("data_size") == record.word_0c,
                "Standalone containment semantic shape changed",
            )
            start = record.word_08 + int(semantic["data_offset"])
            encoded = body[start:start + record.word_0c]
            _require(
                len(encoded) == record.word_0c,
                "Standalone containment payload is truncated",
            )
            pcm = self.source_scanner.batch_decoder(encoded, channels, cancelled)
            _require(
                len(pcm) == frame_count * channels * 2
                and len(pcm) <= MAX_PCM_BYTES
                and hashlib.sha256(pcm).hexdigest()
                == str(getattr(item, "decoded_pcm_sha256")),
                "Standalone containment PCM changed between source passes",
            )
            yield SourcePcmCueInput(
                owner_asset_ids=(asset_id,),
                channels=channels,
                sample_rate=sample_rate,
                frame_count=frame_count,
                pcm16le=pcm,
            )

__all__ = [
    "AudioSourceContainmentError",
    "AudioSourceContainmentProgress",
    "AudioSourceContainmentResult",
    "EXPECTED_SOURCE_CUE_COUNT",
    "EXPECTED_SOURCE_OWNER_COUNT",
    "MAX_PRIVATE_DOCUMENT_BYTES",
    "Nfl2k5AudioSourceContainmentScanner",
    "Nfl2k5AudioSourceContainmentStore",
    "PRIVATE_RELATIVE_PATH",
]
