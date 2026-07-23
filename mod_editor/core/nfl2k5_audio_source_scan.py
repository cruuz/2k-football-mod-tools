"""Read-only real-source scanner for NFL 2K5 audio PCM fingerprints.

This orchestrator binds the private fingerprint inventory to the exact
supported XISO without trusting mutable extracted audio payloads.  It:

* opens and hashes the source XISO through one read-only descriptor;
* authenticates the private cache's pack-0 index and resource inventory;
* reconstructs outer-archive topology from pack 0 inside that XISO;
* derives and canonicalizes every AUSB range;
* reads each physical span directly from the XISO's XDVDFS pack extents;
* decodes and hashes PCM in bounded batches without writing WAV/PCM; and
* re-hashes/re-stats the source before the fingerprint store can publish.

Only the private metadata inventory owned by
``Nfl2k5AudioSourceFingerprintStore`` is persisted.  This module never opens
the XISO or extracted packs writable and never stores source audio bytes.
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
import sys
import time
from typing import Any, Callable, Iterable, Mapping
import zlib

from .errors import ValidationError
from .nfl2k5_audio_catalog import (
    CAPACITY_REPORT,
    CAPACITY_REPORT_SCHEMA,
    CAPACITY_REPORT_SHA256,
    EXPECTED_AUDIO_COUNT,
    EXPECTED_STREAMING_BANK_COUNT,
    EXPECTED_STREAMING_RANGE_COUNT,
    Nfl2k5StreamingAudioBank,
    Nfl2k5StreamingAudioRange,
    _BANK_ROLE_CLASSES,
)
from .nfl2k5_audio_source_fingerprints import (
    AudioSourceFingerprintCancelled,
    AudioSourceFingerprintInventory,
    Nfl2k5AudioSourceFingerprintStore,
)
from .nfl2k5_ausb_fixed_slots import (
    CHANNEL_BLOCK_BYTES,
    IMA_INDEX_TABLE,
    IMA_STEP_TABLE,
    CanonicalStreamingSlot,
    StreamingSlotCatalog,
    build_streaming_slot_catalog,
    decode_xbox_ima_time_block,
    streaming_slot_write_plan,
)
from .nfl2k5_source_cache import (
    INVENTORY_SHA256,
    INVENTORY_SIZE,
    PACK0_SHA256,
    PACK0_SIZE,
    SOURCE_SHA256,
    SOURCE_SIZE,
    SourceCache,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import (  # noqa: E402
    ALIGNMENT,
    ENTRY_SIZE,
    HEADER_SIZE,
    MAX_ENTRIES,
    PACK_NAMES as OUTER_PACK_NAMES,
    PACK_SLOT_COUNT,
    Archive,
    Entry,
    Pack,
    align_up,
    range_segments,
)
from nfl_scene_probe import (  # noqa: E402
    ProbeError,
    ResourceRecord,
    decode_resource,
    named_inner,
    probe_audo,
    utf16z,
)
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


EXPECTED_STREAMING_SLOT_COUNT = 53_570
EXPECTED_STREAMING_OWNER_COUNT = 53_571
PACK_FOLDER = "vc_53450030"
PACK_NAMES = tuple("0123456789ABCDEF")
READ_BLOCK = 16 * 1024 * 1024
DECODE_BATCH_BYTES = 4 * 1024 * 1024
MAX_CAPACITY_REPORT_BYTES = 16 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAPACITY_KEY_RE = re.compile(r"^outer_(\d{4})_chunk_(\d{4})$")


class AudioSourceScanError(ValidationError):
    """The XISO/cache/topology/codec scan failed closed."""


@dataclass(frozen=True, slots=True)
class AudioSourceScanPins:
    """Exact source/cache/public-metadata contract; injectable for tests."""

    source_size: int = SOURCE_SIZE
    source_sha256: str = SOURCE_SHA256
    pack0_size: int = PACK0_SIZE
    pack0_sha256: str = PACK0_SHA256
    inventory_size: int = INVENTORY_SIZE
    inventory_sha256: str = INVENTORY_SHA256
    capacity_report_sha256: str = CAPACITY_REPORT_SHA256
    standalone_count: int = EXPECTED_AUDIO_COUNT
    streaming_bank_count: int = EXPECTED_STREAMING_BANK_COUNT
    streaming_range_count: int = EXPECTED_STREAMING_RANGE_COUNT
    streaming_slot_count: int = EXPECTED_STREAMING_SLOT_COUNT
    streaming_owner_count: int = EXPECTED_STREAMING_OWNER_COUNT
    pack_names: tuple[str, ...] = PACK_NAMES


@dataclass(frozen=True, slots=True)
class AudioSourceScanProgress:
    stage: str
    completed: int
    total: int
    unit: str
    completed_slots: int = 0
    total_slots: int = 0


@dataclass(frozen=True, slots=True)
class StandaloneFingerprintSource:
    """The exact standalone fields consumed by the private fingerprint store."""

    asset_id: str
    channels: int
    sample_rate: int
    frame_count: int
    decoded_pcm_sha256: str


@dataclass(frozen=True, slots=True)
class AudioSourceScanResult:
    inventory: AudioSourceFingerprintInventory
    source_path: Path
    standalone_count: int
    streaming_bank_count: int
    streaming_range_count: int
    streaming_slot_count: int
    streaming_owner_count: int
    streaming_encoded_bytes: int
    reused_inventory: bool
    elapsed_seconds: float


ProgressSink = Callable[[AudioSourceScanProgress], None]
CancellationCheck = Callable[[], bool]
XdvdfsParser = Callable[[int, int], tuple[dict[str, xiso.XdvdfsEntry], dict[str, int]]]
BatchDecoder = Callable[[bytes, int, CancellationCheck | None], bytes]


@dataclass(frozen=True, slots=True)
class _OpenedSource:
    path: Path
    descriptor: int
    initial_stat: os.stat_result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioSourceScanError(message)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    _require(
        type(value) is int and value >= minimum,
        f"Audio source scan has an invalid {label}",
    )
    return value


def _text(value: object, label: str) -> str:
    _require(isinstance(value, str) and bool(value), f"Audio source scan has no {label}")
    return value


def _sha256(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None,
        f"Audio source scan has an invalid {label}",
    )
    return value


def _emit(
    progress: ProgressSink | None,
    stage: str,
    completed: int,
    total: int,
    unit: str,
    *,
    completed_slots: int = 0,
    total_slots: int = 0,
) -> None:
    if progress is not None:
        progress(AudioSourceScanProgress(
            stage,
            completed,
            total,
            unit,
            completed_slots,
            total_slots,
        ))


def _check_cancelled(cancelled: CancellationCheck | None, stage: str) -> None:
    if cancelled is not None and cancelled():
        raise AudioSourceFingerprintCancelled(
            f"Private source-audio scan was cancelled during {stage}; "
            "no fingerprint inventory was published"
        )


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _sha256_fd(
    descriptor: int,
    *,
    offset: int,
    length: int,
    stage: str,
    progress: ProgressSink | None,
    cancelled: CancellationCheck | None,
    block_size: int = READ_BLOCK,
) -> str:
    _require(type(offset) is int and offset >= 0, "hash extent offset")
    _require(type(length) is int and length >= 0, "hash extent length")
    digest = hashlib.sha256()
    completed = 0
    _emit(progress, stage, 0, length, "bytes")
    while completed < length:
        _check_cancelled(cancelled, stage)
        request = min(block_size, length - completed)
        payload = os.pread(descriptor, request, offset + completed)
        _require(
            len(payload) == request,
            f"Short read while {stage.lower()} at byte {completed:,}",
        )
        digest.update(payload)
        completed += len(payload)
        _emit(progress, stage, completed, length, "bytes")
    return digest.hexdigest()


def _read_authenticated_file(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    capture: bool,
    stage: str,
    progress: ProgressSink | None,
    cancelled: CancellationCheck | None,
) -> bytes | None:
    try:
        named_before = path.lstat()
    except FileNotFoundError as exc:
        raise AudioSourceScanError(f"{stage} is missing: {path}") from exc
    _require(
        stat.S_ISREG(named_before.st_mode)
        and not stat.S_ISLNK(named_before.st_mode)
        and named_before.st_size == expected_size,
        f"{stage} is not the pinned regular file",
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) \
        | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AudioSourceScanError(f"Could not open {stage}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        _require(
            _stat_signature(opened) == _stat_signature(named_before),
            f"{stage} changed before authentication",
        )
        digest = hashlib.sha256()
        parts: list[bytes] = []
        completed = 0
        _emit(progress, stage, 0, expected_size, "bytes")
        while completed < expected_size:
            _check_cancelled(cancelled, stage)
            request = min(READ_BLOCK, expected_size - completed)
            payload = os.pread(descriptor, request, completed)
            _require(len(payload) == request, f"Short read while authenticating {stage}")
            digest.update(payload)
            if capture:
                parts.append(payload)
            completed += request
            _emit(progress, stage, completed, expected_size, "bytes")
        after = os.fstat(descriptor)
        named_after = path.lstat()
        _require(
            _stat_signature(after) == _stat_signature(opened)
            and _stat_signature(named_after) == _stat_signature(opened),
            f"{stage} changed during authentication",
        )
        _require(digest.hexdigest() == expected_sha256, f"{stage} hash is not pinned")
        return b"".join(parts) if capture else None
    finally:
        os.close(descriptor)


def _decode_xbox_ima_numpy(
    payload: bytes,
    channels: int,
    cancelled: CancellationCheck | None = None,
) -> bytes:
    """Vectorized exact Xbox IMA decode; returns one bounded PCM batch."""

    _require(channels in (1, 2), "Xbox IMA channel count")
    block_align = CHANNEL_BLOCK_BYTES * channels
    _require(
        payload and len(payload) % block_align == 0,
        "Xbox IMA batch does not contain whole time blocks",
    )
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised through fallback API
        raise AudioSourceScanError("NumPy decoder is unavailable") from exc

    encoded = np.frombuffer(payload, dtype=np.uint8).reshape(
        (-1, channels, CHANNEL_BLOCK_BYTES)
    )
    raw_predictor = (
        encoded[:, :, 0].astype(np.int32)
        | (encoded[:, :, 1].astype(np.int32) << 8)
    )
    predictor = np.where(raw_predictor >= 0x8000, raw_predictor - 0x10000,
                         raw_predictor).astype(np.int32, copy=False)
    index = (
        encoded[:, :, 2].astype(np.int32)
        | (encoded[:, :, 3].astype(np.int32) << 8)
    )
    _require(
        bool(np.all((index >= 0) & (index <= 88))),
        "Xbox IMA step index exceeds 88",
    )
    output = np.empty((encoded.shape[0], 64, channels), dtype="<i2")
    output[:, 0, :] = predictor
    steps = np.asarray(IMA_STEP_TABLE, dtype=np.int32)
    adjustments = np.asarray(IMA_INDEX_TABLE, dtype=np.int16)

    # A block contains 64 nibbles after its predictor, but only the first 63
    # become output frames.  The established scalar decoder likewise outputs
    # predictor + 63 samples and consumes the final padding/state nibble only.
    for sample_index in range(63):
        if sample_index % 8 == 0:
            _check_cancelled(cancelled, "streaming PCM decode")
        coded = encoded[:, :, 4 + sample_index // 2]
        nibble = coded & 0x0F if sample_index % 2 == 0 else coded >> 4
        step = steps[index]
        difference = (
            (step >> 3)
            + ((nibble & 1) != 0) * (step >> 2)
            + ((nibble & 2) != 0) * (step >> 1)
            + ((nibble & 4) != 0) * step
        )
        predictor = np.where(
            (nibble & 8) != 0, predictor - difference, predictor + difference
        )
        predictor = np.clip(predictor, -32_768, 32_767)
        index = np.clip(index + adjustments[nibble & 7], 0, 88)
        output[:, sample_index + 1, :] = predictor
    return output.tobytes(order="C")


def _decode_xbox_ima_scalar(
    payload: bytes,
    channels: int,
    cancelled: CancellationCheck | None = None,
) -> bytes:
    block_align = CHANNEL_BLOCK_BYTES * channels
    _require(
        channels in (1, 2) and payload and len(payload) % block_align == 0,
        "Xbox IMA batch does not contain whole time blocks",
    )
    parts: list[bytes] = []
    for block_index, offset in enumerate(range(0, len(payload), block_align)):
        if block_index % 1024 == 0:
            _check_cancelled(cancelled, "streaming PCM decode")
        try:
            parts.append(decode_xbox_ima_time_block(
                payload[offset:offset + block_align], channels
            ))
        except ValueError as exc:
            raise AudioSourceScanError(str(exc)) from exc
    return b"".join(parts)


def decode_xbox_ima_batch(
    payload: bytes,
    channels: int,
    cancelled: CancellationCheck | None = None,
) -> bytes:
    """Use the vectorized decoder when available, with an exact scalar fallback."""

    try:
        return _decode_xbox_ima_numpy(payload, channels, cancelled)
    except AudioSourceScanError as exc:
        if str(exc) != "NumPy decoder is unavailable":
            raise
    return _decode_xbox_ima_scalar(payload, channels, cancelled)


class Nfl2k5AudioSourceScanner:
    """Facade-ready coordinator for the complete private source fingerprint scan."""

    def __init__(
        self,
        *,
        pins: AudioSourceScanPins = AudioSourceScanPins(),
        capacity_report: Path = CAPACITY_REPORT,
        store: Nfl2k5AudioSourceFingerprintStore | None = None,
        xdvdfs_parser: XdvdfsParser = xiso.parse_xdvdfs,
        batch_decoder: BatchDecoder = decode_xbox_ima_batch,
        decode_batch_bytes: int = DECODE_BATCH_BYTES,
    ) -> None:
        self.pins = self._validate_pins(pins)
        self.capacity_report = capacity_report
        self.store = store or Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=pins.source_sha256,
            expected_standalone_count=pins.standalone_count,
            expected_streaming_slot_count=pins.streaming_slot_count,
            expected_streaming_owner_count=pins.streaming_owner_count,
        )
        _require(callable(xdvdfs_parser), "XDVDFS parser")
        _require(callable(batch_decoder), "streaming batch decoder")
        _require(
            type(decode_batch_bytes) is int and decode_batch_bytes >= 72,
            "streaming decode batch size",
        )
        self.xdvdfs_parser = xdvdfs_parser
        self.batch_decoder = batch_decoder
        self.decode_batch_bytes = decode_batch_bytes

    @staticmethod
    def _validate_pins(pins: AudioSourceScanPins) -> AudioSourceScanPins:
        _require(isinstance(pins, AudioSourceScanPins), "audio source scan pins")
        for label, value in (
            ("source size", pins.source_size),
            ("pack-0 size", pins.pack0_size),
            ("inventory size", pins.inventory_size),
            ("standalone count", pins.standalone_count),
            ("streaming bank count", pins.streaming_bank_count),
            ("streaming range count", pins.streaming_range_count),
            ("streaming slot count", pins.streaming_slot_count),
            ("streaming owner count", pins.streaming_owner_count),
        ):
            _integer(value, label, minimum=1)
        for label, value in (
            ("source SHA-256", pins.source_sha256),
            ("pack-0 SHA-256", pins.pack0_sha256),
            ("inventory SHA-256", pins.inventory_sha256),
            ("capacity-report SHA-256", pins.capacity_report_sha256),
        ):
            _sha256(value, label)
        _require(
            isinstance(pins.pack_names, tuple)
            and pins.pack_names
            and len(set(pins.pack_names)) == len(pins.pack_names)
            and all(
                isinstance(name, str)
                and len(name) == 1
                and name in OUTER_PACK_NAMES
                for name in pins.pack_names
            ),
            "audio archive pack-name contract",
        )
        return pins

    def ensure(
        self,
        source_xiso: Path,
        cache: SourceCache,
        *,
        progress: ProgressSink | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> AudioSourceScanResult:
        started = time.monotonic()
        source = self._open_source(source_xiso, cache)
        try:
            initial_hash = _sha256_fd(
                source.descriptor,
                offset=0,
                length=self.pins.source_size,
                stage="Authenticating source XISO",
                progress=progress,
                cancelled=cancelled,
            )
            _require(initial_hash == self.pins.source_sha256,
                     "Source XISO SHA-256 is not the supported retail dump")
            self._verify_source_identity(source, "initial source authentication")

            # Cache metadata is accepted only after its exact known hashes pass.
            _read_authenticated_file(
                cache.pack0,
                expected_size=self.pins.pack0_size,
                expected_sha256=self.pins.pack0_sha256,
                capture=False,
                stage="Authenticating private pack-0 index",
                progress=progress,
                cancelled=cancelled,
            )
            inventory_payload = _read_authenticated_file(
                cache.inventory,
                expected_size=self.pins.inventory_size,
                expected_sha256=self.pins.inventory_sha256,
                capture=True,
                stage="Authenticating private resource inventory",
                progress=progress,
                cancelled=cancelled,
            )
            assert inventory_payload is not None
            try:
                capacity_info = self.capacity_report.lstat()
            except FileNotFoundError as exc:
                raise AudioSourceScanError(
                    f"Shipped standalone-audio metadata is missing: "
                    f"{self.capacity_report}"
                ) from exc
            _require(
                stat.S_ISREG(capacity_info.st_mode)
                and not stat.S_ISLNK(capacity_info.st_mode)
                and 0 < capacity_info.st_size <= MAX_CAPACITY_REPORT_BYTES,
                "Shipped standalone-audio metadata is not a bounded regular file",
            )
            capacity_payload = _read_authenticated_file(
                self.capacity_report,
                expected_size=capacity_info.st_size,
                expected_sha256=self.pins.capacity_report_sha256,
                capture=True,
                stage="Authenticating standalone-audio metadata",
                progress=progress,
                cancelled=cancelled,
            )
            assert capacity_payload is not None

            try:
                entries, _directory = self.xdvdfs_parser(
                    source.descriptor, self.pins.source_size
                )
            except (OSError, ValueError) as exc:
                raise AudioSourceScanError(f"Could not parse source XDVDFS: {exc}") from exc
            pack_extents = self._pack_extents(entries)
            source_pack0_hash = _sha256_fd(
                source.descriptor,
                offset=pack_extents["0"].byte_offset,
                length=pack_extents["0"].size,
                stage="Authenticating source pack-0 extent",
                progress=progress,
                cancelled=cancelled,
            )
            _require(
                source_pack0_hash == self.pins.pack0_sha256,
                "Source XISO pack-0 extent does not match the authenticated cache index",
            )
            archive = self._parse_source_archive(
                source.descriptor, source.path, pack_extents
            )
            inventory_document = self._json_object(
                inventory_payload, "private resource inventory"
            )
            capacity_document = self._json_object(
                capacity_payload, "standalone-audio metadata"
            )
            standalone = self._standalone_sources(
                source.descriptor,
                archive,
                pack_extents,
                capacity_document,
                inventory_document,
                progress,
                cancelled,
            )
            banks = self._streaming_banks(
                source.descriptor,
                archive,
                pack_extents,
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
                len(ranges) == self.pins.streaming_range_count,
                "Authenticated descriptors expose the wrong streaming-range count",
            )
            try:
                slot_catalog = build_streaming_slot_catalog(ranges, archive)
            except ValueError as exc:
                raise AudioSourceScanError(
                    f"Could not canonicalize streaming source slots: {exc}"
                ) from exc
            self._validate_slot_catalog(slot_catalog)
            total_encoded = sum(slot.encoded_size for slot in slot_catalog.slots)

            existing = self.store.load_existing(
                cache, standalone, slot_catalog.slots
            )
            if existing is not None:
                self._final_source_hash(source, progress, cancelled)
                self._verify_source_identity(source, "completed source recheck")
                _emit(progress, "Private audio fingerprint inventory ready", 1, 1,
                      "inventory", completed_slots=len(slot_catalog.slots),
                      total_slots=len(slot_catalog.slots))
                return self._result(
                    existing,
                    source.path,
                    standalone,
                    banks,
                    ranges,
                    slot_catalog,
                    total_encoded,
                    True,
                    started,
                )

            scan_state = {
                "encoded": 0,
                "slots": 0,
                "final_verified": False,
            }

            def hash_slot(slot: CanonicalStreamingSlot) -> str:
                digest = self._hash_slot_pcm(
                    source.descriptor,
                    pack_extents,
                    slot,
                    scan_state,
                    total_encoded,
                    len(slot_catalog.slots),
                    progress,
                    cancelled,
                )
                return digest

            def publication_guard(stage: str) -> None:
                _require(
                    stage in ("before_publication", "after_publication"),
                    "Fingerprint store requested an unknown publication phase",
                )
                if stage == "before_publication":
                    self._final_source_hash(source, progress, cancelled)
                    self._verify_source_identity(
                        source, "pre-publication source recheck"
                    )
                    scan_state["final_verified"] = True
                else:
                    _require(
                        bool(scan_state["final_verified"]),
                        "Fingerprint inventory published before its source recheck",
                    )
                    self._verify_source_identity(
                        source, "post-publication source recheck"
                    )

            inventory = self.store.ensure(
                cache,
                standalone,
                slot_catalog.slots,
                hash_slot,
                cancelled=cancelled,
                publication_guard=publication_guard,
            )
            _require(
                bool(scan_state["final_verified"]),
                "Fingerprint inventory reached publication without a final source recheck",
            )
            _emit(progress, "Private audio fingerprint inventory ready", 1, 1,
                  "inventory", completed_slots=len(slot_catalog.slots),
                  total_slots=len(slot_catalog.slots))
            return self._result(
                inventory,
                source.path,
                standalone,
                banks,
                ranges,
                slot_catalog,
                total_encoded,
                False,
                started,
            )
        finally:
            os.close(source.descriptor)

    def _open_source(self, source_xiso: Path, cache: SourceCache) -> _OpenedSource:
        _require(isinstance(cache, SourceCache), "NFL 2K5 private source cache")
        _require(
            cache.source.sha256 == self.pins.source_sha256
            and cache.source.size == self.pins.source_size
            and cache.source.recognized
            and cache.source.kind == "xiso",
            "Private source cache is not bound to the requested XISO",
        )
        selected = source_xiso.expanduser()
        _require(selected.is_absolute(), "Source XISO path must be absolute")
        try:
            named = selected.lstat()
        except FileNotFoundError as exc:
            raise AudioSourceScanError(f"Source XISO is missing: {selected}") from exc
        _require(
            stat.S_ISREG(named.st_mode)
            and not stat.S_ISLNK(named.st_mode)
            and named.st_size == self.pins.source_size,
            "Source XISO is not the pinned regular file",
        )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) \
            | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(selected, flags)
        except OSError as exc:
            raise AudioSourceScanError(f"Could not open source XISO read-only: {exc}") from exc
        opened = os.fstat(descriptor)
        if _stat_signature(opened) != _stat_signature(named):
            os.close(descriptor)
            raise AudioSourceScanError("Source XISO changed before its read-only scan")
        return _OpenedSource(selected, descriptor, opened)

    @staticmethod
    def _verify_source_identity(source: _OpenedSource, stage: str) -> None:
        current = os.fstat(source.descriptor)
        try:
            named = source.path.lstat()
        except FileNotFoundError as exc:
            raise AudioSourceScanError(f"Source XISO disappeared during {stage}") from exc
        _require(
            _stat_signature(current) == _stat_signature(source.initial_stat)
            and _stat_signature(named) == _stat_signature(source.initial_stat),
            f"Source XISO identity/content metadata changed during {stage}",
        )

    def _final_source_hash(
        self,
        source: _OpenedSource,
        progress: ProgressSink | None,
        cancelled: CancellationCheck | None,
    ) -> None:
        digest = _sha256_fd(
            source.descriptor,
            offset=0,
            length=self.pins.source_size,
            stage="Rechecking source XISO after audio scan",
            progress=progress,
            cancelled=cancelled,
        )
        _require(
            digest == self.pins.source_sha256,
            "Source XISO content changed during the audio scan",
        )

    def _pack_extents(
        self, entries: Mapping[str, xiso.XdvdfsEntry]
    ) -> dict[str, xiso.XdvdfsEntry]:
        result: dict[str, xiso.XdvdfsEntry] = {}
        for name in self.pins.pack_names:
            key = f"{PACK_FOLDER}/{name}".casefold()
            entry = entries.get(key)
            _require(entry is not None, f"Source XISO has no archive pack {name}")
            _require(
                not entry.attributes & 0x10
                and bool(entry.attributes & 0x20)
                and entry.size > 0
                and entry.byte_offset >= 0
                and entry.byte_offset % xiso.SECTOR_SIZE == 0
                and entry.byte_offset + entry.size <= self.pins.source_size,
                f"Source XISO archive pack {name} has an unsafe extent",
            )
            result[name] = entry
        _require(
            len(result) == len(self.pins.pack_names),
            "Source XISO archive pack set is incomplete",
        )
        ordered_extents = sorted(
            (entry.byte_offset, entry.byte_offset + entry.size, name)
            for name, entry in result.items()
        )
        _require(
            all(
                left_end <= right_start
                for (_left_start, left_end, _left_name),
                    (right_start, _right_end, _right_name)
                in zip(ordered_extents, ordered_extents[1:])
            ),
            "Source XISO archive pack extents overlap",
        )
        return result

    @staticmethod
    def _source_read(
        descriptor: int,
        extent: xiso.XdvdfsEntry,
        offset: int,
        size: int,
    ) -> bytes:
        _require(
            type(offset) is int and type(size) is int
            and offset >= 0 and size >= 0 and offset + size <= extent.size,
            f"Source pack range escapes {extent.path}",
        )
        parts: list[bytes] = []
        completed = 0
        while completed < size:
            payload = os.pread(
                descriptor,
                size - completed,
                extent.byte_offset + offset + completed,
            )
            _require(bool(payload), f"Short read from source pack {extent.path}")
            parts.append(payload)
            completed += len(payload)
        return b"".join(parts)

    def _parse_source_archive(
        self,
        descriptor: int,
        source_path: Path,
        extents: Mapping[str, xiso.XdvdfsEntry],
    ) -> Archive:
        pack0 = extents.get("0")
        _require(pack0 is not None, "Source archive has no pack-0 topology")
        fixed = self._source_read(descriptor, pack0, 0, HEADER_SIZE)
        entry_count, reserved, populated_pack_count = struct.unpack_from("<III", fixed)
        _require(1 <= entry_count <= MAX_ENTRIES, "Source archive entry count")
        _require(reserved == 0, "Source archive reserved header word")
        _require(
            populated_pack_count == len(self.pins.pack_names),
            "Source archive populated-pack count changed",
        )
        block_counts = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", fixed, 12)
        _require(
            all(value > 0 for value in block_counts[:populated_pack_count])
            and all(value == 0 for value in block_counts[populated_pack_count:]),
            "Source archive pack-size table is invalid",
        )
        table_end = HEADER_SIZE + entry_count * ENTRY_SIZE
        _require(table_end <= pack0.size, "Source archive entry table exceeds pack 0")
        raw_table = self._source_read(
            descriptor, pack0, HEADER_SIZE, entry_count * ENTRY_SIZE
        )
        raw_entries = [
            struct.unpack_from("<III", raw_table, index * ENTRY_SIZE)
            for index in range(entry_count)
        ]

        packs: list[Pack] = []
        virtual_start = 0
        for ordinal, (name, blocks) in enumerate(
            zip(self.pins.pack_names, block_counts[:populated_pack_count])
        ):
            extent = extents[name]
            size = blocks * ALIGNMENT
            _require(extent.size == size, f"Source archive pack {name} size changed")
            packs.append(Pack(
                ordinal,
                name,
                blocks,
                size,
                virtual_start,
                Path(f"/authenticated-source-xiso/{PACK_FOLDER}/{name}"),
            ))
            virtual_start += size
        pack_tuple = tuple(packs)
        starts = [pack.virtual_start for pack in pack_tuple]
        entries: list[Entry] = []
        previous_end = 0
        seen_ids: set[int] = set()
        for index, (name_id, size, offset_blocks) in enumerate(raw_entries):
            offset = offset_blocks * ALIGNMENT
            _require(name_id not in seen_ids, "Source archive repeats an entry ID")
            _require(size > 0, "Source archive contains a zero-sized entry")
            _require(offset >= previous_end, "Source archive entries overlap")
            if index > 0:
                _require(
                    offset == align_up(previous_end),
                    "Source archive entries are not aligned and contiguous",
                )
            seen_ids.add(name_id)
            try:
                segments = range_segments(pack_tuple, starts, offset, size)
            except ValueError as exc:
                raise AudioSourceScanError(f"Source archive range is invalid: {exc}") from exc
            first = segments[0]
            head = self._source_read(
                descriptor,
                extents[first.pack_name],
                first.pack_offset,
                min(4, first.size),
            )
            head_ascii = "".join(
                chr(value) if 0x20 <= value < 0x7F else "." for value in head
            )
            entries.append(Entry(
                index,
                name_id,
                size,
                offset_blocks,
                offset,
                head.hex(),
                head_ascii,
                segments,
            ))
            previous_end = offset + size
        _require(
            entries[0].virtual_offset == align_up(table_end),
            "Source archive first payload does not follow its table",
        )
        _require(
            entries[-1].virtual_end == pack_tuple[-1].virtual_end,
            "Source archive coverage does not reach its last pack",
        )
        return Archive(
            source_path,
            reserved,
            populated_pack_count,
            pack_tuple,
            tuple(entries),
        )

    @staticmethod
    def _json_object(payload: bytes, label: str) -> dict[str, Any]:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AudioSourceScanError(f"Authenticated {label} is invalid JSON: {exc}") from exc
        _require(isinstance(document, dict), f"Authenticated {label} is not an object")
        return document

    def _standalone_sources(
        self,
        descriptor: int,
        archive: Archive,
        extents: Mapping[str, xiso.XdvdfsEntry],
        report: Mapping[str, Any],
        inventory: Mapping[str, Any],
        progress: ProgressSink | None,
        cancelled: CancellationCheck | None,
    ) -> tuple[StandaloneFingerprintSource, ...]:
        _require(
            report.get("schema") == CAPACITY_REPORT_SCHEMA,
            "Standalone-audio metadata schema changed",
        )
        records = report.get("records")
        chunks = inventory.get("chunks")
        _require(
            isinstance(records, list) and isinstance(chunks, list),
            "Authenticated audio metadata collections are invalid",
        )
        summary = report.get("summary")
        _require(
            isinstance(summary, dict)
            and summary.get("record_count") == self.pins.standalone_count,
            "Standalone-audio metadata summary count changed",
        )
        inventory_rows: dict[tuple[int, int], dict[str, Any]] = {}
        for raw in chunks:
            _require(isinstance(raw, dict), "Resource inventory contains a non-object row")
            if raw.get("kind") != "AUDO":
                continue
            selector = (
                _integer(raw.get("outer_index"), "AUDO outer index"),
                _integer(raw.get("chunk_index"), "AUDO chunk index"),
            )
            _require(selector not in inventory_rows, "Resource inventory repeats AUDO")
            inventory_rows[selector] = raw
        _require(
            len(inventory_rows) == self.pins.standalone_count,
            "Authenticated inventory exposes the wrong AUDO resource count",
        )
        rows: list[StandaloneFingerprintSource] = []
        seen: set[tuple[int, int]] = set()
        _emit(
            progress,
            "Hashing standalone source PCM",
            0,
            self.pins.standalone_count,
            "assets",
        )
        for raw in records:
            _check_cancelled(cancelled, "standalone PCM hash")
            _require(isinstance(raw, dict), "Standalone-audio record is not an object")
            key = _text(raw.get("key"), "standalone asset key")
            matched = _CAPACITY_KEY_RE.fullmatch(key)
            _require(matched is not None, "Standalone-audio record key is invalid")
            selector = (int(matched.group(1)), int(matched.group(2)))
            _require(selector not in seen, "Standalone-audio metadata repeats a selector")
            seen.add(selector)
            outer = raw.get("outer")
            chunk = raw.get("chunk")
            fmt = raw.get("format")
            hashes = raw.get("hashes")
            indexed = inventory_rows.get(selector)
            _require(
                isinstance(outer, dict) and isinstance(chunk, dict)
                and isinstance(fmt, dict) and isinstance(hashes, dict)
                and indexed is not None,
                f"Standalone-audio metadata is incomplete for {key}",
            )
            _require(
                outer.get("index") == selector[0]
                and chunk.get("index") == selector[1]
                and chunk.get("kind") == "AUDO",
                f"Standalone selector metadata disagrees for {key}",
            )
            outer_index, chunk_index = selector
            _require(
                outer_index < len(archive.entries),
                f"Standalone AUDO owner is absent for {key}",
            )
            entry = archive.entries[outer_index]
            outer_id = _text(indexed.get("outer_id"), "AUDO outer ID")
            outer_head = _text(indexed.get("outer_head"), "AUDO outer head")
            outer_size = _integer(
                indexed.get("outer_size"), "AUDO outer size", minimum=1
            )
            chunk_offset = _integer(
                indexed.get("chunk_offset"), "AUDO chunk offset"
            )
            stored_size = _integer(
                indexed.get("stored_size"), "AUDO stored size", minimum=1
            )
            _require(
                entry.size == outer_size
                and f"0x{entry.name_id:08x}" == outer_id
                and entry.head_ascii == outer_head,
                f"Standalone AUDO outer ownership changed for {key}",
            )
            _require(
                outer.get("id") == outer_id
                and outer.get("head_ascii") == outer_head
                and outer.get("size") == outer_size
                and chunk.get("offset_in_outer") == chunk_offset
                and chunk.get("stored_body_bytes") == stored_size
                and chunk.get("wrapper_span_bytes") == 0x20 + stored_size
                and indexed.get("end_offset") == chunk_offset + 0x20 + stored_size,
                f"Standalone report/inventory ownership disagrees for {key}",
            )
            word_10_text = _text(indexed.get("word_10"), "AUDO word_10")
            try:
                word_10 = int(word_10_text, 0)
            except ValueError as exc:
                raise AudioSourceScanError("AUDO word_10 is invalid") from exc
            record = ResourceRecord(
                outer_index=outer_index,
                outer_id=outer_id,
                outer_size=outer_size,
                chunk_index=chunk_index,
                chunk_offset=chunk_offset,
                kind="AUDO",
                stored_size=stored_size,
                word_08=_integer(indexed.get("word_08"), "AUDO word_08"),
                word_0c=_integer(indexed.get("word_0c"), "AUDO word_0c"),
                word_10=word_10,
                word_14=_integer(indexed.get("word_14"), "AUDO word_14"),
            )
            try:
                span = self._entry_read(
                    descriptor,
                    extents,
                    entry,
                    chunk_offset,
                    0x20 + stored_size,
                )
                body, _detail = decode_resource(span, record)
                semantic = probe_audo(body, record, True)
            except (ProbeError, struct.error, UnicodeError, ValueError) as exc:
                raise AudioSourceScanError(
                    f"Could not decode standalone AUDO {key}: {exc}"
                ) from exc
            channels = _integer(fmt.get("channels"), "standalone channels", minimum=1)
            _require(channels in (1, 2), "Standalone-audio channel count is unsupported")
            sample_rate = _integer(
                fmt.get("sample_rate"), "standalone sample rate", minimum=1
            )
            frame_count = _integer(
                fmt.get("frame_count"), "standalone frame count", minimum=1
            )
            payload_size = _integer(
                fmt.get("payload_allocation_bytes"),
                "standalone payload allocation",
                minimum=1,
            )
            data_offset = _integer(
                fmt.get("data_offset"), "standalone data offset"
            )
            expected_name = _text(raw.get("name"), "standalone audio name")
            _require(
                semantic.get("name") == expected_name
                and semantic.get("channels") == channels
                and semantic.get("sample_rate") == sample_rate
                and semantic.get("data_size") == payload_size
                and semantic.get("data_offset") == data_offset
                and record.word_08 == fmt.get("system_bytes")
                and record.word_0c == payload_size
                and len(body) - record.word_08 - record.word_0c
                == fmt.get("tail_bytes"),
                f"Standalone AUDO semantic shape changed for {key}",
            )
            payload_start = record.word_08 + data_offset
            payload = body[payload_start:payload_start + payload_size]
            _require(
                len(payload) == payload_size,
                f"Standalone AUDO payload is truncated for {key}",
            )
            expected_span_sha256 = _sha256(
                hashes.get("resource_span_sha256"),
                "standalone resource span SHA-256",
            )
            expected_body_sha256 = _sha256(
                hashes.get("resource_body_sha256"),
                "standalone resource body SHA-256",
            )
            expected_payload_sha256 = _sha256(
                hashes.get("payload_sha256"),
                "standalone encoded payload SHA-256",
            )
            _require(
                hashlib.sha256(span).hexdigest() == expected_span_sha256
                and hashlib.sha256(body).hexdigest() == expected_body_sha256
                and hashlib.sha256(payload).hexdigest() == expected_payload_sha256,
                f"Standalone AUDO source bytes disagree with pinned metadata for {key}",
            )
            pcm = self.batch_decoder(payload, channels, cancelled)
            _require(
                len(pcm) == frame_count * channels * 2
                and len(pcm) == fmt.get("pcm16le_bytes"),
                f"Standalone AUDO decoded frame count changed for {key}",
            )
            decoded_pcm_sha256 = hashlib.sha256(pcm).hexdigest()
            _require(
                decoded_pcm_sha256 == _sha256(
                    hashes.get("decoded_pcm_sha256"),
                    "standalone decoded PCM SHA-256",
                ),
                f"Standalone AUDO decoded PCM disagrees with pinned metadata for {key}",
            )
            rows.append(StandaloneFingerprintSource(
                asset_id=(
                    f"nfl2k5.audio.audo.o{selector[0]:04d}.c{selector[1]:04d}"
                ),
                channels=channels,
                sample_rate=sample_rate,
                frame_count=frame_count,
                decoded_pcm_sha256=decoded_pcm_sha256,
            ))
            _emit(
                progress,
                "Hashing standalone source PCM",
                len(rows),
                self.pins.standalone_count,
                "assets",
            )
        rows.sort(key=lambda row: row.asset_id)
        _require(
            len(rows) == self.pins.standalone_count,
            "Standalone-audio fingerprint source count changed",
        )
        _require(
            seen == set(inventory_rows),
            "Standalone-audio report and authenticated resource inventory disagree",
        )
        return tuple(rows)

    def _entry_read(
        self,
        descriptor: int,
        extents: Mapping[str, xiso.XdvdfsEntry],
        entry: Entry,
        relative_offset: int,
        size: int,
    ) -> bytes:
        _require(
            type(relative_offset) is int and type(size) is int
            and relative_offset >= 0 and size >= 0
            and relative_offset + size <= entry.size,
            "Descriptor range escapes its outer entry",
        )
        result = bytearray()
        logical_start = 0
        relative_end = relative_offset + size
        for segment in entry.segments:
            logical_end = logical_start + segment.size
            part_start = max(relative_offset, logical_start)
            part_end = min(relative_end, logical_end)
            if part_start < part_end:
                pack_offset = segment.pack_offset + part_start - logical_start
                result.extend(self._source_read(
                    descriptor,
                    extents[segment.pack_name],
                    pack_offset,
                    part_end - part_start,
                ))
            logical_start = logical_end
            if part_end == relative_end:
                break
        _require(len(result) == size, "Descriptor range read was incomplete")
        return bytes(result)

    def _streaming_banks(
        self,
        descriptor: int,
        archive: Archive,
        extents: Mapping[str, xiso.XdvdfsEntry],
        inventory: Mapping[str, Any],
    ) -> tuple[Nfl2k5StreamingAudioBank, ...]:
        chunks = inventory.get("chunks")
        _require(isinstance(chunks, list), "Resource inventory has no chunk collection")
        rows = [row for row in chunks if isinstance(row, dict) and row.get("kind") == "AUSB"]
        _require(
            len(rows) == self.pins.streaming_bank_count,
            "Authenticated inventory exposes the wrong AUSB descriptor count",
        )
        pending: list[dict[str, Any]] = []
        seen_selectors: set[tuple[int, int]] = set()
        for raw in sorted(rows, key=lambda row: (
            _integer(row.get("outer_index"), "AUSB outer index"),
            _integer(row.get("chunk_index"), "AUSB chunk index"),
        )):
            outer_index = _integer(raw.get("outer_index"), "AUSB outer index")
            chunk_index = _integer(raw.get("chunk_index"), "AUSB chunk index")
            selector = (outer_index, chunk_index)
            _require(selector not in seen_selectors, "Resource inventory repeats AUSB")
            seen_selectors.add(selector)
            _require(outer_index < len(archive.entries), "AUSB descriptor owner is absent")
            entry = archive.entries[outer_index]
            outer_id = _text(raw.get("outer_id"), "AUSB outer ID")
            outer_head = _text(raw.get("outer_head"), "AUSB outer head")
            outer_size = _integer(raw.get("outer_size"), "AUSB outer size", minimum=1)
            chunk_offset = _integer(raw.get("chunk_offset"), "AUSB chunk offset")
            stored_size = _integer(raw.get("stored_size"), "AUSB stored size", minimum=1)
            _require(
                entry.size == outer_size
                and f"0x{entry.name_id:08x}" == outer_id
                and entry.head_ascii == outer_head,
                f"AUSB descriptor owner changed at {outer_index}:{chunk_index}",
            )
            word_10_text = _text(raw.get("word_10"), "AUSB word_10")
            try:
                word_10 = int(word_10_text, 0)
            except ValueError as exc:
                raise AudioSourceScanError("AUSB word_10 is invalid") from exc
            record = ResourceRecord(
                outer_index=outer_index,
                outer_id=outer_id,
                outer_size=outer_size,
                chunk_index=chunk_index,
                chunk_offset=chunk_offset,
                kind="AUSB",
                stored_size=stored_size,
                word_08=_integer(raw.get("word_08"), "AUSB word_08"),
                word_0c=_integer(raw.get("word_0c"), "AUSB word_0c"),
                word_10=word_10,
                word_14=_integer(raw.get("word_14"), "AUSB word_14"),
            )
            try:
                span = self._entry_read(
                    descriptor, extents, entry, chunk_offset, 0x20 + stored_size
                )
                body, detail = decode_resource(span, record)
                name = named_inner(body, "AUSB")[0]
                external_filename = utf16z(body, 0x40, 0x80)[0]
                _require(
                    external_filename.casefold() == f"{name}.bin".casefold(),
                    f"AUSB bank {name} has a mismatched external filename",
                )
                _require(len(body) >= 0x9C, f"AUSB bank {name} descriptor is truncated")
                count, unknown, channels, rate, unit_word = struct.unpack_from(
                    "<5I", body, 0x80
                )
                _require(
                    count > 0 and channels in (1, 2)
                    and rate == 22_050 and unit_word == 0x12000,
                    f"AUSB bank {name} has an unsupported codec shape",
                )
                table_end = 0x98 + (count + 1) * 4
                _require(table_end <= len(body), f"AUSB bank {name} boundary table is truncated")
                boundaries = tuple(struct.unpack_from(f"<{count + 1}I", body, 0x98))
                _require(
                    boundaries[0] == 0
                    and all(left < right for left, right in zip(boundaries, boundaries[1:])),
                    f"AUSB bank {name} boundaries are invalid",
                )
                external_id = zlib.crc32(
                    external_filename.upper().encode("utf-16le")
                ) & 0xFFFFFFFF
                matches = [entry for entry in archive.entries if entry.name_id == external_id]
                _require(
                    len(matches) == 1 and boundaries[-1] == matches[0].size,
                    f"AUSB bank {name} does not own one exact external entry",
                )
            except (ProbeError, struct.error, UnicodeError, ValueError) as exc:
                if isinstance(exc, AudioSourceScanError):
                    raise
                raise AudioSourceScanError(
                    f"Could not decode AUSB {outer_index}:{chunk_index}: {exc}"
                ) from exc
            external = matches[0]
            pending.append({
                "asset_id": f"nfl2k5.audio.ausb.o{outer_index:04d}.c{chunk_index:04d}",
                "name": name,
                "role_class": _BANK_ROLE_CLASSES.get(name, "unknown"),
                "outer_index": outer_index,
                "outer_id": outer_id,
                "outer_head": outer_head,
                "outer_size": outer_size,
                "chunk_index": chunk_index,
                "chunk_offset": chunk_offset,
                "stored_size": stored_size,
                "external_filename": external_filename,
                "external_outer_index": external.table_index,
                "external_outer_id": f"0x{external.name_id:08x}",
                "external_size": external.size,
                "entry_count": count,
                "sample_rate": rate,
                "channel_word": channels,
                "unknown_word": unknown,
                "unit_word": unit_word,
                "boundaries": boundaries,
                "descriptor_sha256": str(detail["decoded_sha256"]),
            })
        sharing: dict[int, int] = {}
        for row in pending:
            external_index = int(row["external_outer_index"])
            sharing[external_index] = sharing.get(external_index, 0) + 1
        return tuple(Nfl2k5StreamingAudioBank(
            **row,
            shared_external_descriptor_count=sharing[int(row["external_outer_index"])],
        ) for row in pending)

    def _validate_slot_catalog(self, catalog: StreamingSlotCatalog) -> None:
        _require(
            len(catalog.slots) == self.pins.streaming_slot_count,
            "Canonical streaming slot count changed",
        )
        owners: set[str] = set()
        for slot in catalog.slots:
            streaming_slot_write_plan(slot)
            for owner in slot.owners:
                _require(owner.asset_id not in owners, "Streaming owner is mapped twice")
                owners.add(owner.asset_id)
        _require(
            len(owners) == self.pins.streaming_owner_count,
            "Canonical streaming owner count changed",
        )

    def _hash_slot_pcm(
        self,
        descriptor: int,
        extents: Mapping[str, xiso.XdvdfsEntry],
        slot: CanonicalStreamingSlot,
        state: dict[str, int | bool],
        total_encoded: int,
        total_slots: int,
        progress: ProgressSink | None,
        cancelled: CancellationCheck | None,
    ) -> str:
        spans = streaming_slot_write_plan(slot)
        block_align = CHANNEL_BLOCK_BYTES * slot.channels
        batch_size = max(block_align, self.decode_batch_bytes // block_align * block_align)
        pending = bytearray()
        decoded_hash = hashlib.sha256()
        decoded_bytes = 0
        slot_encoded = 0
        for span in spans:
            _require(span.pack_name in extents, "Streaming span names an absent XISO pack")
            extent = extents[span.pack_name]
            _require(
                span.pack_ordinal < len(self.pins.pack_names)
                and self.pins.pack_names[span.pack_ordinal] == span.pack_name
                and span.pack_offset >= 0 and span.length > 0
                and span.pack_offset + span.length <= extent.size,
                "Streaming span escapes its authenticated XISO pack extent",
            )
            completed_in_span = 0
            while completed_in_span < span.length:
                _check_cancelled(cancelled, "streaming PCM hash")
                request = min(
                    batch_size - len(pending), span.length - completed_in_span
                )
                payload = os.pread(
                    descriptor,
                    request,
                    extent.byte_offset + span.pack_offset + completed_in_span,
                )
                _require(len(payload) == request, "Short read from streaming XISO span")
                pending.extend(payload)
                completed_in_span += request
                slot_encoded += request
                state["encoded"] = int(state["encoded"]) + request
                if len(pending) == batch_size:
                    decoded = self.batch_decoder(bytes(pending), slot.channels, cancelled)
                    _require(
                        len(decoded) == len(pending) // block_align * 64
                        * slot.channels * 2,
                        "Streaming PCM decoder returned the wrong byte count",
                    )
                    decoded_hash.update(decoded)
                    decoded_bytes += len(decoded)
                    pending.clear()
                _emit(
                    progress,
                    "Hashing streaming source PCM",
                    int(state["encoded"]),
                    total_encoded,
                    "encoded_bytes",
                    completed_slots=int(state["slots"]),
                    total_slots=total_slots,
                )
        _require(slot_encoded == slot.encoded_size, "Streaming slot XISO read was incomplete")
        _require(len(pending) % block_align == 0, "Streaming slot ends inside an IMA block")
        if pending:
            decoded = self.batch_decoder(bytes(pending), slot.channels, cancelled)
            _require(
                len(decoded) == len(pending) // block_align * 64 * slot.channels * 2,
                "Streaming PCM decoder returned the wrong final byte count",
            )
            decoded_hash.update(decoded)
            decoded_bytes += len(decoded)
        _require(
            decoded_bytes == slot.frame_count * slot.channels * 2,
            "Streaming slot decoded PCM shape changed",
        )
        state["slots"] = int(state["slots"]) + 1
        _emit(
            progress,
            "Hashing streaming source PCM",
            int(state["encoded"]),
            total_encoded,
            "encoded_bytes",
            completed_slots=int(state["slots"]),
            total_slots=total_slots,
        )
        _check_cancelled(cancelled, "between streaming slots")
        return decoded_hash.hexdigest()

    @staticmethod
    def _result(
        inventory: AudioSourceFingerprintInventory,
        source_path: Path,
        standalone: Iterable[StandaloneFingerprintSource],
        banks: Iterable[Nfl2k5StreamingAudioBank],
        ranges: Iterable[Nfl2k5StreamingAudioRange],
        slots: StreamingSlotCatalog,
        total_encoded: int,
        reused: bool,
        started: float,
    ) -> AudioSourceScanResult:
        standalone = tuple(standalone)
        banks = tuple(banks)
        ranges = tuple(ranges)
        return AudioSourceScanResult(
            inventory=inventory,
            source_path=source_path,
            standalone_count=len(standalone),
            streaming_bank_count=len(banks),
            streaming_range_count=len(ranges),
            streaming_slot_count=len(slots.slots),
            streaming_owner_count=sum(len(slot.owners) for slot in slots.slots),
            streaming_encoded_bytes=total_encoded,
            reused_inventory=reused,
            elapsed_seconds=time.monotonic() - started,
        )


__all__ = [
    "AudioSourceScanError",
    "AudioSourceScanPins",
    "AudioSourceScanProgress",
    "AudioSourceScanResult",
    "Nfl2k5AudioSourceScanner",
    "StandaloneFingerprintSource",
    "decode_xbox_ima_batch",
]
