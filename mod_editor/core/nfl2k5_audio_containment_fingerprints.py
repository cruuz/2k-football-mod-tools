"""Exact, digest-only PCM containment fingerprints for NFL 2K5 audio.

Whole-cue SHA-256 fingerprints are maintained by the separate private source
inventory.  This module supplies the complementary *containment* primitive: it
indexes exact source PCM windows and finds those windows at every frame offset
inside candidate PCM.  A fast rolling Adler-32 checksum selects possible hits;
SHA-256 of the candidate window is always the authority.

The policy is intentionally narrow and explicit:

* cues at least a quarter second long contribute quarter-second windows whose
  source starts lie on a quarter-second rational grid;
* shorter cues contribute one deterministic, nonzero anchor whose length is
  pinned per ``(channels, sample_rate)`` by the authenticated catalog;
* only byte-exact all-zero PCM is exempt; quiet nonconstant PCM is indexed;
* windows never span two source cues; and
* gain, resampling, filtering, time stretch, or changing a frame inside every
  indexed window are outside this exact matcher's claim.

The resulting inventory contains only digests, codec shape, owner IDs, counts,
and policy metadata.  It never retains PCM, WAV containers, source paths,
archive coordinates, or rollback bytes.  Publication and XISO authorization
belong to higher layers and are deliberately not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
from types import MappingProxyType
from typing import Callable, Iterable, Mapping
import zlib

from .errors import ValidationError


SCHEMA = "2k5_mod_studio_audio_pcm_containment/v2"
POLICY_REVISION = "exact-pcm-quarter-window-quarter-grid-short-anchor-v2"

MAX_SOURCE_CUES = 60_000
MAX_SOURCE_OWNER_IDS = 100_000
MAX_FINGERPRINT_RECORDS = 1_000_000
MAX_FINGERPRINT_OWNER_REFERENCES = 2_000_000
MAX_PCM_BYTES = 64 * 1024 * 1024
MAX_SAMPLE_RATE = 192_000
MAX_MATCHES = 4_096
DEFAULT_PROGRESS_INTERVAL_FRAMES = 16_384

_ADLER_MODULUS = 65_521
_HEX_DIGITS = frozenset("0123456789abcdef")


class AudioContainmentFingerprintError(ValidationError):
    """Containment input, policy, or private representation is invalid."""


class AudioContainmentFingerprintCancelled(AudioContainmentFingerprintError):
    """Containment indexing or candidate scanning was cancelled."""


class SourcePcmContainmentError(AudioContainmentFingerprintError):
    """Candidate PCM contains at least one exact indexed source window."""

    def __init__(self, match: "PcmContainmentMatch") -> None:
        self.match = match
        owners = ", ".join(match.owner_asset_ids[:2])
        if len(match.owner_asset_ids) > 2:
            owners += f" (+{len(match.owner_asset_ids) - 2} aliases)"
        super().__init__(
            "That audio contains an exact window of decoded source audio "
            f"({owners}). Retail-derived audio cannot enter a shareable project."
        )


@dataclass(frozen=True, slots=True, order=True)
class ShortCueAnchorShape:
    """Catalog-pinned short-cue anchor length for one PCM shape."""

    channels: int
    sample_rate: int
    frame_count: int


@dataclass(frozen=True, slots=True)
class PcmContainmentPolicy:
    """Fingerprint semantics; operational limits are module constants."""

    short_anchor_shapes: tuple[ShortCueAnchorShape, ...]
    long_window_divisor: int = 4
    source_windows_per_second: int = 4
    revision: str = POLICY_REVISION
    _anchors: Mapping[tuple[int, int], int] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _require(
            self.revision == POLICY_REVISION,
            "Unknown PCM containment policy revision",
        )
        _require(
            type(self.long_window_divisor) is int
            and self.long_window_divisor == 4,
            "PCM containment long windows must be exactly a quarter second",
        )
        _require(
            type(self.source_windows_per_second) is int
            and self.source_windows_per_second == 4,
            "PCM containment source windows must use the quarter-second grid",
        )
        _require(
            type(self.short_anchor_shapes) is tuple,
            "Short-cue anchor shapes must be a tuple",
        )
        anchors: dict[tuple[int, int], int] = {}
        previous: tuple[int, int] | None = None
        for item in self.short_anchor_shapes:
            _require(
                isinstance(item, ShortCueAnchorShape),
                "Short-cue anchor policy contains an invalid shape",
            )
            channels, sample_rate = _pcm_shape(item.channels, item.sample_rate)
            _require(
                type(item.frame_count) is int and item.frame_count > 0,
                "Short-cue anchor frame count must be a positive integer",
            )
            _require(
                item.frame_count < self.long_window_frames(sample_rate),
                "Short-cue anchors must be shorter than the long-window size",
            )
            key = (channels, sample_rate)
            _require(key not in anchors, "Duplicate short-cue anchor shape")
            _require(
                previous is None or previous < key,
                "Short-cue anchor shapes must be deterministically ordered",
            )
            anchors[key] = item.frame_count
            previous = key
        object.__setattr__(self, "_anchors", MappingProxyType(anchors))

    def short_anchor_frames(self, channels: int, sample_rate: int) -> int:
        """Return the pinned short anchor or fail closed for an unknown shape."""

        key = _pcm_shape(channels, sample_rate)
        try:
            return self._anchors[key]
        except KeyError as exc:
            raise AudioContainmentFingerprintError(
                "No authenticated short-cue anchor exists for PCM shape "
                f"{channels}ch/{sample_rate}Hz"
            ) from exc

    def long_window_frames(self, sample_rate: int) -> int:
        """Quarter-second window quantized down to a whole PCM frame."""

        _, checked_rate = _pcm_shape(1, sample_rate)
        frames = checked_rate // self.long_window_divisor
        _require(frames > 0, "Sample rate is too low for a quarter-second window")
        return frames

    def guaranteed_excerpt_frames(self, sample_rate: int) -> int:
        """Exact run length guaranteed to contain one source-grid window."""

        window = self.long_window_frames(sample_rate)
        maximum_grid_gap = (
            sample_rate + self.source_windows_per_second - 1
        ) // self.source_windows_per_second
        return window + maximum_grid_gap - 1

    def to_document(self) -> dict[str, object]:
        return {
            "long_window_divisor": self.long_window_divisor,
            "revision": self.revision,
            "short_anchor_shapes": [
                {
                    "channels": item.channels,
                    "frame_count": item.frame_count,
                    "sample_rate": item.sample_rate,
                }
                for item in self.short_anchor_shapes
            ],
            "source_windows_per_second": self.source_windows_per_second,
        }

    @classmethod
    def from_document(cls, value: object) -> "PcmContainmentPolicy":
        document = _strict_mapping(
            value,
            {
                "long_window_divisor",
                "revision",
                "short_anchor_shapes",
                "source_windows_per_second",
            },
            "PCM containment policy",
        )
        raw_shapes = document["short_anchor_shapes"]
        _require(
            type(raw_shapes) is list,
            "PCM containment short-anchor shapes must be a list",
        )
        _require(
            len(raw_shapes) <= 32,
            "PCM containment policy has too many short-anchor shapes",
        )
        shapes: list[ShortCueAnchorShape] = []
        for raw in raw_shapes:
            row = _strict_mapping(
                raw,
                {"channels", "frame_count", "sample_rate"},
                "short-cue anchor shape",
            )
            shapes.append(ShortCueAnchorShape(
                channels=_strict_int(row["channels"], "anchor channels"),
                sample_rate=_strict_int(row["sample_rate"], "anchor sample rate"),
                frame_count=_strict_int(row["frame_count"], "anchor frame count"),
            ))
        revision = document["revision"]
        _require(type(revision) is str, "PCM containment revision must be text")
        return cls(
            short_anchor_shapes=tuple(shapes),
            long_window_divisor=_strict_int(
                document["long_window_divisor"], "long-window divisor"
            ),
            source_windows_per_second=_strict_int(
                document["source_windows_per_second"],
                "source windows per second",
            ),
            revision=revision,
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_document())).hexdigest()


@dataclass(frozen=True, slots=True)
class SourcePcmCueInput:
    """Ephemeral canonical PCM for one cue; never retained by the inventory."""

    owner_asset_ids: tuple[str, ...]
    channels: int
    sample_rate: int
    frame_count: int
    pcm16le: bytes | bytearray | memoryview


@dataclass(frozen=True, slots=True, order=True)
class PcmContainmentFingerprint:
    """One digest-only exact source window (no PCM and no source offset)."""

    kind: str
    channels: int
    sample_rate: int
    frame_count: int
    rolling_checksum: str
    pcm_sha256: str
    owner_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PcmContainmentMatch:
    """Confirmed SHA-256 match at a candidate position."""

    candidate_frame_start: int
    kind: str
    channels: int
    sample_rate: int
    frame_count: int
    pcm_sha256: str
    owner_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PcmContainmentProgress:
    stage: str
    completed_units: int
    total_units: int
    fingerprint_records: int


ProgressSink = Callable[[PcmContainmentProgress], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class PcmContainmentInventory:
    """Validated immutable digest index for one private source binding."""

    source_binding_sha256: str
    policy: PcmContainmentPolicy
    source_cue_count: int
    source_owner_ids: tuple[str, ...]
    all_zero_owner_ids: tuple[str, ...]
    fingerprints: tuple[PcmContainmentFingerprint, ...]
    _by_shape_checksum: Mapping[
        tuple[int, int, int],
        Mapping[
            int,
            PcmContainmentFingerprint
            | Mapping[str, tuple[PcmContainmentFingerprint, ...]],
        ],
    ] = field(repr=False, compare=False)
    private: bool = True
    shareable: bool = False

    @property
    def fingerprint_count(self) -> int:
        return len(self.fingerprints)

    def to_private_document(self) -> dict[str, object]:
        """Return strict private-cache data containing no source payload bytes."""

        return {
            "counts": {
                "all_zero_owners": len(self.all_zero_owner_ids),
                "fingerprints": len(self.fingerprints),
                "source_cues": self.source_cue_count,
                "source_owners": len(self.source_owner_ids),
            },
            "fingerprints": [
                {
                    "channels": row.channels,
                    "frame_count": row.frame_count,
                    "kind": row.kind,
                    "owner_asset_ids": list(row.owner_asset_ids),
                    "pcm_sha256": row.pcm_sha256,
                    "rolling_checksum": row.rolling_checksum,
                    "sample_rate": row.sample_rate,
                }
                for row in self.fingerprints
            ],
            "policy": self.policy.to_document(),
            "policy_sha256": self.policy.sha256,
            "privacy": {
                "audio_payload_bytes": 0,
                "private_user_cache": True,
                "shareable": False,
            },
            "schema": SCHEMA,
            "source_binding_sha256": self.source_binding_sha256,
            "source_owner_ids": list(self.source_owner_ids),
            "zero_exempt_owner_ids": list(self.all_zero_owner_ids),
        }

    @classmethod
    def from_private_document(cls, value: object) -> "PcmContainmentInventory":
        """Strictly validate a decoded private-cache document."""

        document = _strict_mapping(
            value,
            {
                "counts",
                "fingerprints",
                "policy",
                "policy_sha256",
                "privacy",
                "schema",
                "source_binding_sha256",
                "source_owner_ids",
                "zero_exempt_owner_ids",
            },
            "PCM containment inventory",
        )
        _require(document["schema"] == SCHEMA, "Unknown PCM containment schema")
        source_binding = _sha256_text(
            document["source_binding_sha256"], "source binding SHA-256"
        )
        policy = PcmContainmentPolicy.from_document(document["policy"])
        _require(
            document["policy_sha256"] == policy.sha256,
            "PCM containment policy digest does not match its document",
        )
        privacy = _strict_mapping(
            document["privacy"],
            {"audio_payload_bytes", "private_user_cache", "shareable"},
            "PCM containment privacy declaration",
        )
        _require(
            type(privacy["audio_payload_bytes"]) is int
            and privacy["audio_payload_bytes"] == 0
            and type(privacy["private_user_cache"]) is bool
            and privacy["private_user_cache"] is True
            and type(privacy["shareable"]) is bool
            and privacy["shareable"] is False,
            "PCM containment inventory is not private metadata-only data",
        )
        source_owners = _owner_ids(
            document["source_owner_ids"], "source owner IDs", allow_list=True
        )
        zero_owners = _owner_ids(
            document["zero_exempt_owner_ids"],
            "zero-exempt owner IDs",
            allow_list=True,
            allow_empty=True,
        )
        _require(
            set(zero_owners).issubset(source_owners),
            "Zero-exempt owner IDs are not a subset of source owners",
        )
        raw_rows = document["fingerprints"]
        _require(type(raw_rows) is list, "PCM containment fingerprints must be a list")
        _require(
            len(raw_rows) <= MAX_FINGERPRINT_RECORDS,
            "PCM containment inventory exceeds its fingerprint-record bound",
        )
        rows: list[PcmContainmentFingerprint] = []
        owner_references = 0
        for raw in raw_rows:
            item = _strict_mapping(
                raw,
                {
                    "channels",
                    "frame_count",
                    "kind",
                    "owner_asset_ids",
                    "pcm_sha256",
                    "rolling_checksum",
                    "sample_rate",
                },
                "PCM containment fingerprint",
            )
            channels, sample_rate = _pcm_shape(
                _strict_int(item["channels"], "fingerprint channels"),
                _strict_int(item["sample_rate"], "fingerprint sample rate"),
            )
            frame_count = _strict_int(
                item["frame_count"], "fingerprint frame count"
            )
            kind = item["kind"]
            _require(
                type(kind) is str
                and kind in {"long_window", "short_anchor", "sparse_anchor"},
                "PCM containment fingerprint has an invalid kind",
            )
            expected_frames = (
                policy.long_window_frames(sample_rate)
                if kind in {"long_window", "sparse_anchor"}
                else policy.short_anchor_frames(channels, sample_rate)
            )
            _require(
                frame_count == expected_frames,
                "PCM containment fingerprint shape conflicts with its policy",
            )
            owners = _owner_ids(
                item["owner_asset_ids"],
                "fingerprint owner IDs",
                allow_list=True,
            )
            _require(
                set(owners).issubset(source_owners),
                "Fingerprint owner IDs are not a subset of source owners",
            )
            owner_references += len(owners)
            _require(
                owner_references <= MAX_FINGERPRINT_OWNER_REFERENCES,
                "PCM containment owner-reference count exceeds its bound",
            )
            checksum = _checksum_text(item["rolling_checksum"])
            digest = _sha256_text(item["pcm_sha256"], "window PCM SHA-256")
            rows.append(PcmContainmentFingerprint(
                kind=kind,
                channels=channels,
                sample_rate=sample_rate,
                frame_count=frame_count,
                rolling_checksum=checksum,
                pcm_sha256=digest,
                owner_asset_ids=owners,
            ))
        ordered = tuple(sorted(rows))
        _require(tuple(rows) == ordered, "PCM containment rows are not ordered")
        _require(
            len(set(rows)) == len(rows),
            "PCM containment inventory has duplicate rows",
        )
        record_keys = {
            (
                row.kind,
                row.channels,
                row.sample_rate,
                row.frame_count,
                row.rolling_checksum,
                row.pcm_sha256,
            )
            for row in rows
        }
        _require(
            len(record_keys) == len(rows),
            "PCM containment digest records were not canonically aggregated",
        )
        protected_owners = {
            owner for row in rows for owner in row.owner_asset_ids
        }
        _require(
            protected_owners.isdisjoint(zero_owners),
            "A zero-exempt source owner also has a protected fingerprint",
        )
        _require(
            protected_owners.union(zero_owners) == set(source_owners),
            "PCM containment owner coverage is incomplete",
        )
        counts = _strict_mapping(
            document["counts"],
            {"all_zero_owners", "fingerprints", "source_cues", "source_owners"},
            "PCM containment counts",
        )
        source_cue_count = _strict_int(counts["source_cues"], "source cue count")
        source_owner_count = _strict_int(
            counts["source_owners"], "source owner count"
        )
        zero_owner_count = _strict_nonnegative_int(
            counts["all_zero_owners"], "all-zero owner count"
        )
        fingerprint_count = _strict_nonnegative_int(
            counts["fingerprints"], "fingerprint count"
        )
        _require(
            source_cue_count <= MAX_SOURCE_CUES,
            "PCM containment source-cue count exceeds its bound",
        )
        _require(
            source_cue_count <= len(source_owners),
            "PCM containment has fewer owners than source cues",
        )
        _require(
            source_owner_count == len(source_owners)
            and zero_owner_count == len(zero_owners)
            and fingerprint_count == len(ordered),
            "PCM containment aggregate counts do not match their rows",
        )
        return _inventory(
            source_binding,
            policy,
            source_cue_count,
            source_owners,
            zero_owners,
            ordered,
        )

    def find_contained_source_pcm(
        self,
        pcm16le: bytes | bytearray | memoryview,
        *,
        channels: int,
        sample_rate: int,
        frame_count: int,
        cancel: CancellationCheck | None = None,
        progress: ProgressSink | None = None,
        progress_interval_frames: int = DEFAULT_PROGRESS_INTERVAL_FRAMES,
        max_matches: int = 64,
    ) -> tuple[PcmContainmentMatch, ...]:
        """Find exact indexed windows at every candidate frame position.

        Each distinct indexed window length requires one linear rolling pass.
        The catalog policy intentionally permits at most the quarter-second
        length and one short-anchor length for a channel/rate shape.
        """

        channels, sample_rate = _pcm_shape(channels, sample_rate)
        frame_count = _strict_int(frame_count, "candidate frame count")
        _require(
            type(progress_interval_frames) is int and progress_interval_frames > 0,
            "Progress interval must be a positive frame count",
        )
        _require(
            type(max_matches) is int and 1 <= max_matches <= MAX_MATCHES,
            f"Maximum matches must be between 1 and {MAX_MATCHES:,}",
        )
        _check_cancel(cancel, "Candidate PCM containment scan")
        payload = _snapshot_pcm(
            pcm16le,
            channels=channels,
            frame_count=frame_count,
            label="candidate PCM",
        )
        lengths = sorted({
            shape[2]
            for shape in self._by_shape_checksum
            if shape[:2] == (channels, sample_rate) and shape[2] <= frame_count
        })
        _require(
            len(lengths) <= 2,
            "PCM containment policy would require more than two candidate passes",
        )
        total_positions = sum(frame_count - length + 1 for length in lengths)
        _check_cancel(cancel, "Candidate PCM containment scan")
        _emit(progress, "Scanning candidate PCM", 0, total_positions, 0)
        if total_positions == 0:
            _emit(progress, "Candidate PCM containment scan ready", 0, 0, 0)
            return ()

        view = memoryview(payload)
        completed = 0
        next_check = progress_interval_frames
        matches: list[PcmContainmentMatch] = []
        for window_frames in lengths:
            checksum_rows = self._by_shape_checksum[
                (channels, sample_rate, window_frames)
            ]
            roller = _FrameRollingAdler32(view, channels, frame_count, window_frames)
            for candidate_start, checksum in roller:
                completed += 1
                bucket = checksum_rows.get(checksum)
                if bucket is not None:
                    byte_start = candidate_start * channels * 2
                    byte_end = byte_start + window_frames * channels * 2
                    digest = hashlib.sha256(view[byte_start:byte_end]).hexdigest()
                    if isinstance(bucket, PcmContainmentFingerprint):
                        records = (
                            (bucket,) if digest == bucket.pcm_sha256 else ()
                        )
                    else:
                        # Adler collisions are attacker-controlled metadata;
                        # SHA-keyed lookup keeps confirmation O(1), not O(bucket).
                        records = bucket.get(digest, ())
                    for record in records:
                        matches.append(PcmContainmentMatch(
                            candidate_frame_start=candidate_start,
                            kind=record.kind,
                            channels=channels,
                            sample_rate=sample_rate,
                            frame_count=window_frames,
                            pcm_sha256=digest,
                            owner_asset_ids=record.owner_asset_ids,
                        ))
                        if len(matches) >= max_matches:
                            _emit(
                                progress,
                                "Source PCM containment found",
                                completed,
                                total_positions,
                                len(matches),
                            )
                            return tuple(matches)
                if completed >= next_check:
                    _check_cancel(cancel, "Candidate PCM containment scan")
                    _emit(
                        progress,
                        "Scanning candidate PCM",
                        completed,
                        total_positions,
                        len(matches),
                    )
                    next_check += progress_interval_frames
        _check_cancel(cancel, "Candidate PCM containment scan")
        _emit(
            progress,
            "Candidate PCM containment scan ready",
            total_positions,
            total_positions,
            len(matches),
        )
        return tuple(matches)

    def reject_contained_source_pcm(
        self,
        pcm16le: bytes | bytearray | memoryview,
        *,
        channels: int,
        sample_rate: int,
        frame_count: int,
        cancel: CancellationCheck | None = None,
        progress: ProgressSink | None = None,
    ) -> None:
        """Raise on the first SHA-confirmed exact source-window match."""

        matches = self.find_contained_source_pcm(
            pcm16le,
            channels=channels,
            sample_rate=sample_rate,
            frame_count=frame_count,
            cancel=cancel,
            progress=progress,
            max_matches=1,
        )
        if matches:
            raise SourcePcmContainmentError(matches[0])


def build_private_containment_inventory(
    source_binding_sha256: str,
    policy: PcmContainmentPolicy,
    cues: Iterable[SourcePcmCueInput],
    *,
    expected_cue_count: int,
    expected_owner_count: int,
    cancel: CancellationCheck | None = None,
    progress: ProgressSink | None = None,
    progress_interval_frames: int = DEFAULT_PROGRESS_INTERVAL_FRAMES,
    max_fingerprint_records: int = MAX_FINGERPRINT_RECORDS,
    max_fingerprint_owner_references: int = MAX_FINGERPRINT_OWNER_REFERENCES,
) -> PcmContainmentInventory:
    """Build a bounded digest-only inventory from a one-pass PCM stream.

    ``cues`` is consumed lazily and only one bounded PCM snapshot is retained.
    Explicit authenticated counts make a short, long, or duplicated stream fail
    closed without materializing all 54,420 decoded cues at once.
    """

    source_binding = _sha256_text(source_binding_sha256, "source binding SHA-256")
    _require(isinstance(policy, PcmContainmentPolicy), "Invalid containment policy")
    _require(
        not isinstance(cues, (str, bytes, bytearray)),
        "Source PCM cues must be a one-pass iterable",
    )
    try:
        cue_iterator = iter(cues)
    except TypeError as exc:
        raise AudioContainmentFingerprintError(
            "Source PCM cues must be a one-pass iterable"
        ) from exc
    cue_count = _strict_int(expected_cue_count, "expected source cue count")
    _require(
        cue_count <= MAX_SOURCE_CUES,
        f"Source PCM cue inventory exceeds {MAX_SOURCE_CUES:,} cues",
    )
    expected_owners = _strict_int(
        expected_owner_count, "expected source owner count"
    )
    _require(
        expected_owners <= MAX_SOURCE_OWNER_IDS,
        f"Source PCM inventory exceeds {MAX_SOURCE_OWNER_IDS:,} owner IDs",
    )
    _require(
        type(progress_interval_frames) is int and progress_interval_frames > 0,
        "Progress interval must be a positive frame count",
    )
    _require(
        type(max_fingerprint_records) is int
        and 1 <= max_fingerprint_records <= MAX_FINGERPRINT_RECORDS,
        "Fingerprint record bound is invalid",
    )
    _require(
        type(max_fingerprint_owner_references) is int
        and 1
        <= max_fingerprint_owner_references
        <= MAX_FINGERPRINT_OWNER_REFERENCES,
        "Fingerprint owner-reference bound is invalid",
    )
    _check_cancel(cancel, "Source PCM containment indexing")
    _emit(progress, "Indexing source PCM containment", 0, cue_count, 0)

    owner_ids: set[str] = set()
    zero_owner_ids: set[str] = set()
    # Identical digest records share storage while retaining every logical owner.
    aggregated: dict[
        tuple[str, int, int, int, str, str], set[str]
    ] = {}
    fingerprint_owner_references = 0

    completed_cues = 0
    for cue_index, cue in enumerate(cue_iterator):
        _check_cancel(cancel, "Source PCM containment indexing")
        _require(
            cue_index < cue_count,
            "Source PCM cue stream contains more rows than authenticated",
        )
        completed_cues = cue_index + 1
        _require(
            isinstance(cue, SourcePcmCueInput),
            "Source PCM cue sequence contains an invalid item",
        )
        channels, sample_rate = _pcm_shape(cue.channels, cue.sample_rate)
        frame_count = _strict_int(cue.frame_count, "source cue frame count")
        owners = _owner_ids(cue.owner_asset_ids, "source cue owner IDs")
        overlap = owner_ids.intersection(owners)
        if overlap:
            raise AudioContainmentFingerprintError(
                "A source PCM owner ID is assigned to more than one cue: "
                + sorted(overlap)[0]
            )
        _require(
            len(owner_ids) + len(owners) <= MAX_SOURCE_OWNER_IDS,
            f"Source PCM inventory exceeds {MAX_SOURCE_OWNER_IDS:,} owner IDs",
        )
        _require(
            len(owner_ids) + len(owners) <= expected_owners,
            "Source PCM cue stream exceeds its authenticated owner count",
        )
        owner_ids.update(owners)
        payload = _snapshot_pcm(
            cue.pcm16le,
            channels=channels,
            frame_count=frame_count,
            label="source cue PCM",
        )
        _check_cancel(cancel, "Source PCM containment indexing")
        view = memoryview(payload)
        if payload.count(0) == len(payload):
            # Even a short zero cue must satisfy the catalog-pinned shape.  This
            # prevents a malformed short cue from disappearing as "silence".
            if frame_count < policy.long_window_frames(sample_rate):
                anchor_frames = policy.short_anchor_frames(channels, sample_rate)
                _require(
                    frame_count >= anchor_frames,
                    "Source cue is shorter than its authenticated short anchor",
                )
            zero_owner_ids.update(owners)
            _emit(
                progress,
                "Indexing source PCM containment",
                cue_index + 1,
                cue_count,
                len(aggregated),
            )
            # Release both caller input and the owned snapshot before asking a
            # lazy iterator to decode/yield the next cue.
            del view, payload, cue
            continue

        before_count = len(aggregated)
        if frame_count >= policy.long_window_frames(sample_rate):
            window_frames = policy.long_window_frames(sample_rate)
            starts = _quarter_grid_starts(
                frame_count,
                window_frames,
                sample_rate,
                policy.source_windows_per_second,
            )
            processed_since_check = 0
            cue_had_nonzero_window = False
            for source_start in starts:
                processed_since_check += window_frames
                if processed_since_check >= progress_interval_frames:
                    _check_cancel(cancel, "Source PCM containment indexing")
                    processed_since_check = 0
                byte_start = source_start * channels * 2
                byte_end = byte_start + window_frames * channels * 2
                window = view[byte_start:byte_end]
                digest = hashlib.sha256(window).hexdigest()
                if digest != _zero_sha256(window.nbytes):
                    fingerprint_owner_references = _aggregate_record(
                        aggregated,
                        "long_window",
                        channels,
                        sample_rate,
                        window_frames,
                        zlib.adler32(window) & 0xFFFFFFFF,
                        digest,
                        owners,
                        max_fingerprint_records,
                        fingerprint_owner_references,
                        max_fingerprint_owner_references,
                    )
                    cue_had_nonzero_window = True
            if not cue_had_nonzero_window:
                # A sparse nonzero tail can fall outside every rational grid
                # window. Index one deterministic off-grid quarter-second
                # anchor instead of leaving the authenticated cue unprotected.
                first_nonzero_frame = _first_nonzero_frame(view, channels)
                _require(
                    first_nonzero_frame is not None,
                    "Nonzero source cue was inconsistently classified as silence",
                )
                anchor_start = min(
                    first_nonzero_frame, frame_count - window_frames
                )
                byte_start = anchor_start * channels * 2
                byte_end = byte_start + window_frames * channels * 2
                window = view[byte_start:byte_end]
                digest = hashlib.sha256(window).hexdigest()
                _require(
                    digest != _zero_sha256(window.nbytes),
                    "Sparse source anchor unexpectedly contains only zero PCM",
                )
                fingerprint_owner_references = _aggregate_record(
                    aggregated,
                    "sparse_anchor",
                    channels,
                    sample_rate,
                    window_frames,
                    zlib.adler32(window) & 0xFFFFFFFF,
                    digest,
                    owners,
                    max_fingerprint_records,
                    fingerprint_owner_references,
                    max_fingerprint_owner_references,
                )
        else:
            anchor_frames = policy.short_anchor_frames(channels, sample_rate)
            _require(
                frame_count >= anchor_frames,
                "Source cue is shorter than its authenticated short anchor",
            )
            first_nonzero_frame = _first_nonzero_frame(view, channels)
            _require(
                first_nonzero_frame is not None,
                "Nonzero source cue was inconsistently classified as silence",
            )
            anchor_start = min(first_nonzero_frame, frame_count - anchor_frames)
            byte_start = anchor_start * channels * 2
            byte_end = byte_start + anchor_frames * channels * 2
            window = view[byte_start:byte_end]
            digest = hashlib.sha256(window).hexdigest()
            _require(
                digest != _zero_sha256(window.nbytes),
                "Short-cue anchor unexpectedly contains only zero PCM",
            )
            checksum = _FrameRollingAdler32(
                window, channels, anchor_frames, anchor_frames
            ).first_checksum
            fingerprint_owner_references = _aggregate_record(
                aggregated,
                "short_anchor",
                channels,
                sample_rate,
                anchor_frames,
                checksum,
                digest,
                owners,
                max_fingerprint_records,
                fingerprint_owner_references,
                max_fingerprint_owner_references,
            )
        _require(
            len(aggregated) > before_count
            or any(set(owners).issubset(existing) for existing in aggregated.values()),
            "Nonzero source cue produced no containment fingerprint",
        )
        _require(
            len(aggregated) <= max_fingerprint_records,
            "PCM containment inventory exceeds its fingerprint-record bound",
        )
        _emit(
            progress,
            "Indexing source PCM containment",
            cue_index + 1,
            cue_count,
            len(aggregated),
        )
        del window, view, payload, cue

    _check_cancel(cancel, "Source PCM containment indexing")
    _require(
        completed_cues == cue_count,
        "Source PCM cue stream ended before its authenticated row count",
    )
    _require(
        len(owner_ids) == expected_owners,
        "Source PCM owner count does not match its authenticated count",
    )
    rows = tuple(sorted(
        PcmContainmentFingerprint(
            kind=key[0],
            channels=key[1],
            sample_rate=key[2],
            frame_count=key[3],
            rolling_checksum=key[4],
            pcm_sha256=key[5],
            owner_asset_ids=tuple(sorted(owners)),
        )
        for key, owners in aggregated.items()
    ))
    _require(
        sum(len(row.owner_asset_ids) for row in rows)
        == fingerprint_owner_references,
        "PCM containment owner-reference accounting is inconsistent",
    )
    _require(
        fingerprint_owner_references <= max_fingerprint_owner_references,
        "PCM containment owner-reference count exceeds its bound",
    )
    ordered_owner_ids = tuple(sorted(owner_ids))
    ordered_zero_owner_ids = tuple(sorted(zero_owner_ids))
    # The aggregate sets are the largest temporary structure.  Drop them
    # before constructing the immutable lookup to keep publication-time peak
    # memory bounded to the final rows plus one index.
    del aggregated, owner_ids, zero_owner_ids
    inventory = _inventory(
        source_binding,
        policy,
        cue_count,
        ordered_owner_ids,
        ordered_zero_owner_ids,
        rows,
    )
    _emit(
        progress,
        "Source PCM containment inventory ready",
        cue_count,
        cue_count,
        len(rows),
    )
    return inventory


class _FrameRollingAdler32:
    """Adler-32 updated in O(1) per interleaved PCM frame.

    Source-window checksums use :func:`zlib.adler32`, so private inventory
    creation keeps the expensive overlapping-window work inside native code.
    Candidate scanning applies the equivalent removal/addition recurrence and
    confirms every checksum hit with SHA-256.
    """

    __slots__ = (
        "_channels",
        "_frame_count",
        "_pcm",
        "_window_frames",
        "_window_bytes",
        "first_checksum",
    )

    def __init__(
        self,
        pcm: memoryview,
        channels: int,
        frame_count: int,
        window_frames: int,
    ) -> None:
        _require(
            0 < window_frames <= frame_count,
            "Rolling checksum window exceeds PCM frame count",
        )
        self._pcm = pcm
        self._channels = channels
        self._frame_count = frame_count
        self._window_frames = window_frames
        self._window_bytes = window_frames * channels * 2
        self.first_checksum = zlib.adler32(pcm[:self._window_bytes]) & 0xFFFFFFFF

    def __iter__(self):
        checksum = self.first_checksum
        yield 0, checksum
        last_start = self._frame_count - self._window_frames
        frame_bytes = self._channels * 2
        window_bytes = self._window_bytes
        pcm = self._pcm
        outgoing_offset = 0
        incoming_offset = window_bytes
        if self._channels == 1:
            for start in range(1, last_start + 1):
                a = checksum & 0xFFFF
                b = checksum >> 16
                outgoing = pcm[outgoing_offset]
                incoming = pcm[incoming_offset]
                a += incoming - outgoing
                b += a - 1 - window_bytes * outgoing
                outgoing = pcm[outgoing_offset + 1]
                incoming = pcm[incoming_offset + 1]
                a += incoming - outgoing
                b += a - 1 - window_bytes * outgoing
                a %= _ADLER_MODULUS
                b %= _ADLER_MODULUS
                checksum = (b << 16) | a
                yield start, checksum
                outgoing_offset += frame_bytes
                incoming_offset += frame_bytes
            return
        for start in range(1, last_start + 1):
            a = checksum & 0xFFFF
            b = checksum >> 16
            # Stereo is the same byte recurrence, explicitly unrolled so the
            # largest 32 MiB slots do not pay a Python inner-loop cost.
            outgoing = pcm[outgoing_offset]
            incoming = pcm[incoming_offset]
            a += incoming - outgoing
            b += a - 1 - window_bytes * outgoing
            outgoing = pcm[outgoing_offset + 1]
            incoming = pcm[incoming_offset + 1]
            a += incoming - outgoing
            b += a - 1 - window_bytes * outgoing
            outgoing = pcm[outgoing_offset + 2]
            incoming = pcm[incoming_offset + 2]
            a += incoming - outgoing
            b += a - 1 - window_bytes * outgoing
            outgoing = pcm[outgoing_offset + 3]
            incoming = pcm[incoming_offset + 3]
            a += incoming - outgoing
            b += a - 1 - window_bytes * outgoing
            a %= _ADLER_MODULUS
            b %= _ADLER_MODULUS
            checksum = (b << 16) | a
            yield start, checksum
            outgoing_offset += frame_bytes
            incoming_offset += frame_bytes


def _inventory(
    source_binding: str,
    policy: PcmContainmentPolicy,
    source_cue_count: int,
    owner_ids: tuple[str, ...],
    zero_owner_ids: tuple[str, ...],
    rows: tuple[PcmContainmentFingerprint, ...],
) -> PcmContainmentInventory:
    by_shape: dict[
        tuple[int, int, int],
        dict[
            int,
            PcmContainmentFingerprint
            | dict[str, tuple[PcmContainmentFingerprint, ...]]
            | Mapping[str, tuple[PcmContainmentFingerprint, ...]],
        ],
    ] = {}
    for row in rows:
        shape = (row.channels, row.sample_rate, row.frame_count)
        checksum = int(row.rolling_checksum, 16)
        checksums = by_shape.setdefault(shape, {})
        existing = checksums.get(checksum)
        if existing is None:
            # The overwhelmingly common singleton stays allocation-light.
            checksums[checksum] = row
        elif isinstance(existing, PcmContainmentFingerprint):
            grouped = {existing.pcm_sha256: (existing,)}
            grouped[row.pcm_sha256] = (
                grouped.get(row.pcm_sha256, ()) + (row,)
            )
            checksums[checksum] = grouped
        else:
            # This branch runs only while constructing the index; values are
            # mutable dicts until the freeze loop below.
            existing[row.pcm_sha256] = (  # type: ignore[index]
                existing.get(row.pcm_sha256, ()) + (row,)
            )
    frozen_shapes: dict[
        tuple[int, int, int],
        Mapping[
            int,
            PcmContainmentFingerprint
            | Mapping[str, tuple[PcmContainmentFingerprint, ...]],
        ],
    ] = {}
    for shape, checksums in sorted(by_shape.items()):
        # Freeze only genuine collision dictionaries.  This avoids one nested
        # dict allocation for every normal record while making hostile buckets
        # direct SHA lookups.
        for checksum in checksums:
            bucket = checksums[checksum]
            if isinstance(bucket, dict):
                checksums[checksum] = MappingProxyType(bucket)
        frozen_shapes[shape] = MappingProxyType(checksums)
    frozen = MappingProxyType(frozen_shapes)
    return PcmContainmentInventory(
        source_binding_sha256=source_binding,
        policy=policy,
        source_cue_count=source_cue_count,
        source_owner_ids=owner_ids,
        all_zero_owner_ids=zero_owner_ids,
        fingerprints=rows,
        _by_shape_checksum=frozen,
    )


def _aggregate_record(
    records: dict[tuple[str, int, int, int, str, str], set[str]],
    kind: str,
    channels: int,
    sample_rate: int,
    frame_count: int,
    checksum: int,
    digest: str,
    owners: tuple[str, ...],
    maximum_records: int,
    current_owner_references: int,
    maximum_owner_references: int,
) -> int:
    key = (
        kind,
        channels,
        sample_rate,
        frame_count,
        f"{checksum:08x}",
        digest,
    )
    if key not in records:
        _require(
            len(records) < maximum_records,
            "PCM containment inventory exceeds its fingerprint-record bound",
        )
    record_owners = records.setdefault(key, set())
    added = sum(owner not in record_owners for owner in owners)
    _require(
        current_owner_references + added <= maximum_owner_references,
        "PCM containment owner-reference count exceeds its bound",
    )
    record_owners.update(owners)
    return current_owner_references + added


def _quarter_grid_starts(
    frame_count: int,
    window_frames: int,
    sample_rate: int,
    windows_per_second: int,
) -> tuple[int, ...]:
    """Quantize exact quarter-second rational positions down to PCM frames."""

    last_start = frame_count - window_frames
    starts: list[int] = []
    tick = 0
    while True:
        start = (tick * sample_rate) // windows_per_second
        if start > last_start:
            break
        if not starts or starts[-1] != start:
            starts.append(start)
            _require(
                len(starts) <= MAX_FINGERPRINT_RECORDS,
                "One source cue exceeds the containment-window record bound",
            )
        tick += 1
    _require(bool(starts) and starts[0] == 0, "Long-window grid is empty")
    return tuple(starts)


def _snapshot_pcm(
    value: bytes | bytearray | memoryview,
    *,
    channels: int,
    frame_count: int,
    label: str,
) -> bytes:
    try:
        view = memoryview(value)
    except (TypeError, ValueError) as exc:
        raise AudioContainmentFingerprintError(
            f"{label} must be a bytes-like PCM16LE payload"
        ) from exc
    if view.ndim != 1 or view.itemsize != 1 or not view.c_contiguous:
        try:
            view = view.cast("B")
        except (TypeError, ValueError) as exc:
            raise AudioContainmentFingerprintError(
                f"{label} must be a contiguous byte payload"
            ) from exc
    expected = channels * frame_count * 2
    _require(
        expected <= MAX_PCM_BYTES,
        f"{label} exceeds the {MAX_PCM_BYTES // (1024 * 1024)} MiB bound",
    )
    _require(
        view.nbytes == expected,
        f"{label} byte length does not match its channel/frame shape "
        f"({view.nbytes:,} found; {expected:,} expected)",
    )
    # One bounded owned snapshot prevents caller-side mutation during hashing.
    return bytes(view)


def _first_nonzero_frame(pcm: memoryview, channels: int) -> int | None:
    frame_bytes = channels * 2
    for byte_index, value in enumerate(pcm):
        if value:
            return byte_index // frame_bytes
    return None


@lru_cache(maxsize=128)
def _zero_sha256(byte_count: int) -> str:
    return hashlib.sha256(bytes(byte_count)).hexdigest()


def _pcm_shape(channels: object, sample_rate: object) -> tuple[int, int]:
    _require(
        type(channels) is int and channels in (1, 2),
        "PCM channels must be 1 or 2",
    )
    _require(
        type(sample_rate) is int and 1 <= sample_rate <= MAX_SAMPLE_RATE,
        f"PCM sample rate must be between 1 and {MAX_SAMPLE_RATE:,} Hz",
    )
    return channels, sample_rate


def _owner_ids(
    value: object,
    label: str,
    *,
    allow_list: bool = False,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    accepted = (tuple, list) if allow_list else (tuple,)
    _require(type(value) in accepted, f"{label} must be a tuple")
    _require(allow_empty or len(value) > 0, f"{label} cannot be empty")
    _require(len(value) <= MAX_SOURCE_OWNER_IDS, f"{label} exceeds its bound")
    result: list[str] = []
    for item in value:
        try:
            encoded = item.encode("utf-8") if type(item) is str else b""
        except UnicodeEncodeError:
            encoded = b""
        _require(
            type(item) is str
            and 1 <= len(encoded) <= 256
            and all(character.isprintable() for character in item),
            f"{label} contains an invalid owner ID",
        )
        result.append(item)
    _require(len(set(result)) == len(result), f"{label} contains duplicates")
    ordered = tuple(sorted(result))
    _require(tuple(result) == ordered, f"{label} must be deterministically ordered")
    return ordered


def _sha256_text(value: object, label: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and set(value).issubset(_HEX_DIGITS),
        f"Invalid {label}",
    )
    return value


def _checksum_text(value: object) -> str:
    _require(
        type(value) is str
        and len(value) == 8
        and set(value).issubset(_HEX_DIGITS),
        "Invalid rolling checksum",
    )
    return value


def _strict_mapping(
    value: object, keys: set[str], label: str
) -> Mapping[str, object]:
    _require(type(value) is dict, f"{label} must be an object")
    _require(set(value) == keys, f"{label} has missing or unknown fields")
    return value


def _strict_int(value: object, label: str) -> int:
    _require(type(value) is int and value > 0, f"Invalid {label}")
    return value


def _strict_nonnegative_int(value: object, label: str) -> int:
    _require(type(value) is int and value >= 0, f"Invalid {label}")
    return value


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


def _check_cancel(cancel: CancellationCheck | None, operation: str) -> None:
    if cancel is not None and cancel():
        raise AudioContainmentFingerprintCancelled(f"{operation} was cancelled")


def _emit(
    progress: ProgressSink | None,
    stage: str,
    completed: int,
    total: int,
    records: int,
) -> None:
    if progress is not None:
        progress(PcmContainmentProgress(stage, completed, total, records))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioContainmentFingerprintError(message)
