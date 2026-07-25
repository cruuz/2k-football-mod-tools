"""Headless, bounded batch export for APF's semantic audio inventory.

The services deliberately delegate every playable sound to
``ApfAssetIO.export_audio_identity`` and every proved physical bank to
``ApfAssetIO.export_external_audio_bank`` (or objects with the same methods).
They do not parse retail payloads, encode XMA1, replace cues, or rewrite
physical multi-cue banks.  Consequently this module contains no game bytes and
only produces private, user-requested exports from the source already bound to
the supplied exporter.

Exports are published as one collision-safe ZIP.  Payload paths are derived
from proved archive coordinates instead of retail names, so duplicate or
hostile labels cannot collide or escape the archive.  A manifest accounts for
every selected semantic row, including failures, unsupported bank/index rows,
and rows skipped after cooperative cancellation.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Callable, Iterable, Protocol
import unicodedata
import zipfile

from mod_editor.core.platform_compat import fsync_path

from .inspectors import (
    AUDIO_ROLE_LABELS,
    AudioSnapshot,
    ExportIdentity,
    InspectorRow,
    classify_ausb_role,
)
from .models import ExternalAudioBankIdentity, ExternalAudioBankOwner


MANIFEST_SCHEMA = "apf2k8_mod_studio_audio_batch_export/v2"
EXTERNAL_BANK_MANIFEST_SCHEMA = (
    "apf2k8_mod_studio_external_audio_bank_bundle/v1"
)
SUPPORTED_OUTPUT_EXTENSIONS = frozenset({".xma", ".wav"})
# The pinned retail inventory contains 2,261 AUDO rows, 20 AUSB index rows,
# 45,514 addressed substreams, and 19 physical-bank rows.  The service may
# export that entire surface, but never accepts an unbounded foreign iterable.
MAX_BATCH_ROWS = 47_814
MAX_EXTERNAL_AUDIO_BANKS = 19
_PHYSICAL_OR_INDEX_KINDS = frozenset(
    {"ausb_bank", "external_bank", "xma1_bank", "physical_bank", "bank_index"}
)
_COPY_BLOCK_SIZE = 1024 * 1024
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_SAFE_BANK_STEM = re.compile(r"[^A-Za-z0-9._-]+")
_CATALOG_COLUMNS = (
    "order",
    "row_id",
    "status",
    "kind",
    "title",
    "game_catalog_title",
    "custom_title",
    "annotation_note",
    "output_path",
    "file_size",
    "file_sha256",
    "error_code",
    "message",
    "audio_source_id",
    "audio_source_label",
    "role_id",
    "role_label",
    "role_basis",
    "audio_format",
    "sample_rate",
    "channel_count",
    "duration_seconds",
    "logical_track_number",
    "paired_bank_name",
    "paired_encoding_role",
    "track_title_status",
    "packet_count",
    "encoded_size",
    "range_length",
    "outer_table_index",
    "inner_file_index",
    "substream_index",
)
_TEXT_METADATA_FIELDS = (
    "game_catalog_title",
    "custom_title",
    "annotation_note",
    "audio_source_id",
    "audio_source_label",
    "role_id",
    "role_label",
    "role_basis",
    "audio_format",
    "paired_bank_name",
    "paired_encoding_role",
    "track_title_status",
)
_COUNT_METADATA_FIELDS = ("packet_count", "encoded_size", "range_length")


class AudioBatchExportError(ValueError):
    """A batch request cannot be completed without violating its contract."""


class AudioBatchSafetyError(AudioBatchExportError):
    """A generated payload changed or crossed a filesystem safety boundary."""


class AudioIdentityExporter(Protocol):
    """The existing verified single-sound export route used by this service."""

    def export_audio_identity(
        self, identity: ExportIdentity, destination: Path
    ) -> Path: ...


class ExternalAudioBankExporter(Protocol):
    """The existing verified original-bank export route used by the bundle."""

    def export_external_audio_bank(
        self,
        identity: ExternalAudioBankIdentity,
        destination: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path: ...


@dataclass(frozen=True)
class AudioBatchProgress:
    """One UI-independent progress notification.

    Cancellation is cooperative between sounds: the currently running
    single-sound export is allowed to finish, then ``cancel_requested`` is
    consulted before the next row.
    """

    stage: str
    completed: int
    total: int
    succeeded: int
    failed: int
    unsupported: int
    cancelled: int
    row_id: str | None = None


@dataclass(frozen=True)
class AudioBatchReceipt:
    path: Path
    requested: int
    succeeded: int
    failed: int
    unsupported: int
    cancelled: int
    was_cancelled: bool
    output_extension: str
    payload_bytes: int
    catalog_record_count: int
    playlist_record_count: int
    archive_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class ExternalAudioBankBundleProgress:
    """One UI-independent notification for an original-bank bundle export."""

    stage: str
    completed: int
    total: int
    succeeded: int
    failed: int
    cancelled: int
    bank_name: str | None = None
    bank_bytes_completed: int = 0
    bank_bytes_total: int = 0


@dataclass(frozen=True)
class ExternalAudioBankBundleReceipt:
    path: Path
    requested: int
    succeeded: int
    failed: int
    cancelled: int
    was_cancelled: bool
    payload_bytes: int
    archive_sha256: str
    manifest_sha256: str


ProgressHook = Callable[[AudioBatchProgress], None]
CancellationHook = Callable[[], bool]
ExternalBankProgressHook = Callable[[ExternalAudioBankBundleProgress], None]


def audio_snapshot_rows(snapshot: AudioSnapshot) -> tuple[InspectorRow, ...]:
    """Return the complete semantic audio surface in stable product order.

    The result includes playable AUDO/AUSB substream rows and the 20 AUSB index
    plus 19 physical-bank rows.  The latter remain visible in the batch
    manifest as unsupported and are never passed to a payload exporter.
    """

    return (
        *snapshot.audo.rows,
        *snapshot.ausb_banks.rows,
        *snapshot.ausb_substreams.rows,
        *snapshot.external_banks.rows,
    )


def _payload_path(
    identity: ExportIdentity, output_extension: str
) -> PurePosixPath:
    outer = identity.outer_table_index
    inner = identity.inner_file_index
    if (
        isinstance(outer, bool)
        or isinstance(inner, bool)
        or not isinstance(outer, int)
        or not isinstance(inner, int)
        or outer < 0
        or inner < 0
    ):
        raise AudioBatchExportError("Audio export coordinates must be non-negative integers")
    if identity.kind == "audo":
        if identity.substream_index is not None:
            raise AudioBatchExportError("AUDO coordinates unexpectedly include a substream")
        return PurePosixPath(
            "audio", "audo", f"o{outer:05d}-i{inner:05d}{output_extension}"
        )
    if identity.kind == "ausb_substream":
        substream = identity.substream_index
        if (
            isinstance(substream, bool)
            or not isinstance(substream, int)
            or substream < 0
        ):
            raise AudioBatchExportError(
                "AUSB sound coordinates are missing a non-negative substream index"
            )
        return PurePosixPath(
            "audio",
            "ausb",
            f"o{outer:05d}-i{inner:05d}",
            f"s{substream:05d}{output_extension}",
        )
    raise AudioBatchExportError(
        f"No verified single-sound exporter owns identity kind {identity.kind!r}"
    )


def _single_line_text(value: object, *, limit: int = 512) -> str | None:
    """Return bounded, printable metadata without trusting retail labels.

    The selected source owns most audio labels.  They are useful in a private
    catalog, but none may inject line breaks, terminal controls, bidi controls,
    or other invisible format characters into JSON/CSV/M3U companions.
    """

    if value is None:
        return None
    rendered = str(value)
    cleaned = "".join(
        " "
        if (
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            or ord(character) == 127
        )
        else character
        for character in rendered
    )
    normalized = " ".join(cleaned.split())
    return normalized[:limit] or None


def _metadata_integer(value: object, *, positive: bool) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    minimum = 1 if positive else 0
    return value if value >= minimum else None


def _metadata_duration(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    duration = float(value)
    return duration if math.isfinite(duration) and duration >= 0 else None


def _record_metadata(row: InspectorRow) -> dict[str, object]:
    """Project the allowlisted audio facts into one stable v2 record."""

    fields = row.fields
    checked_duration = _metadata_duration(fields.get("duration_seconds"))
    duration_basis: str | None = (
        "declared_samples" if checked_duration is not None else None
    )
    if checked_duration is None:
        checked_duration = _metadata_duration(
            fields.get("duration_seconds_candidate")
        )
        if checked_duration is not None:
            duration_basis = "ausb_boundary_candidate"

    metadata: dict[str, object] = {
        name: _single_line_text(fields.get(name))
        for name in _TEXT_METADATA_FIELDS
    }
    metadata.update(
        {
            "sample_rate": _metadata_integer(
                fields.get("sample_rate"), positive=True
            ),
            "channel_count": _metadata_integer(
                fields.get("derived_channel_count"), positive=True
            ),
            "duration_seconds": checked_duration,
            "duration_basis": duration_basis,
            "logical_track_number": _metadata_integer(
                fields.get("logical_track_number"), positive=True
            ),
        }
    )
    metadata.update(
        {
            name: _metadata_integer(fields.get(name), positive=False)
            for name in _COUNT_METADATA_FIELDS
        }
    )
    return metadata


def _record_base(row: InspectorRow) -> dict[str, object]:
    identity = row.export_identity
    coordinates: dict[str, object] | None = None
    if identity is not None:
        coordinates = {
            "kind": identity.kind,
            "outer_table_index": identity.outer_table_index,
            "inner_file_index": identity.inner_file_index,
            "substream_index": identity.substream_index,
        }
    return {
        "row_id": row.row_id,
        "kind": row.kind,
        "title": row.title,
        "coordinates": coordinates,
        "metadata": _record_metadata(row),
        "replacement_supported": False,
    }


def _unsupported_record(row: InspectorRow, code: str, message: str) -> dict[str, object]:
    return {
        **_record_base(row),
        "status": "unsupported",
        "output_path": None,
        "file_size": None,
        "file_sha256": None,
        "error_code": code,
        "message": message,
    }


def _failure_record(row: InspectorRow, code: str, message: str) -> dict[str, object]:
    return {
        **_record_base(row),
        "status": "failure",
        "output_path": None,
        "file_size": None,
        "file_sha256": None,
        "error_code": code,
        "message": message,
    }


def _cancelled_record(row: InspectorRow) -> dict[str, object]:
    return {
        **_record_base(row),
        "status": "cancelled",
        "output_path": None,
        "file_size": None,
        "file_sha256": None,
        "error_code": "batch_cancelled",
        "message": "Not attempted because cancellation was requested.",
    }


def _catalog_cell(value: object) -> str:
    """Render one safe spreadsheet cell without executable formula prefixes."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        rendered = f"{value:.9f}".rstrip("0").rstrip(".")
    elif isinstance(value, int):
        rendered = str(value)
    else:
        rendered = _single_line_text(value, limit=2_048) or ""
    if rendered.startswith(("=", "+", "-", "@")):
        rendered = "'" + rendered
    return rendered


def _catalog_bytes(records: Iterable[dict[str, object]]) -> tuple[bytes, int]:
    selected = tuple(records)
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=_CATALOG_COLUMNS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for order, record in enumerate(selected, 1):
        metadata = record["metadata"]
        coordinates = record.get("coordinates")
        if not isinstance(metadata, dict):
            raise AudioBatchSafetyError("An audio catalog record lost its metadata")
        if coordinates is not None and not isinstance(coordinates, dict):
            raise AudioBatchSafetyError("An audio catalog record lost its coordinates")
        row: dict[str, object] = {
            "order": order,
            "row_id": record.get("row_id"),
            "status": record.get("status"),
            "kind": record.get("kind"),
            "title": record.get("title"),
            "output_path": record.get("output_path"),
            "file_size": record.get("file_size"),
            "file_sha256": record.get("file_sha256"),
            "error_code": record.get("error_code"),
            "message": record.get("message"),
            **{name: metadata.get(name) for name in _TEXT_METADATA_FIELDS},
            "sample_rate": metadata.get("sample_rate"),
            "channel_count": metadata.get("channel_count"),
            "duration_seconds": metadata.get("duration_seconds"),
            "logical_track_number": metadata.get("logical_track_number"),
            **{name: metadata.get(name) for name in _COUNT_METADATA_FIELDS},
            "outer_table_index": (
                coordinates.get("outer_table_index") if coordinates else None
            ),
            "inner_file_index": (
                coordinates.get("inner_file_index") if coordinates else None
            ),
            "substream_index": (
                coordinates.get("substream_index") if coordinates else None
            ),
        }
        writer.writerow({name: _catalog_cell(row.get(name)) for name in _CATALOG_COLUMNS})
    return output.getvalue().encode("utf-8"), len(selected)


def _playlist_duration(value: object) -> str:
    duration = _metadata_duration(value)
    if duration is None:
        return "-1"
    return f"{duration:.3f}".rstrip("0").rstrip(".")


def _playlist_bytes(
    batch_name: str, records: Iterable[dict[str, object]]
) -> tuple[bytes | None, int]:
    successful = tuple(record for record in records if record.get("status") == "success")
    if not successful:
        return None, 0
    label = _single_line_text(batch_name, limit=160) or "APF 2K8 audio export"
    lines = ["#EXTM3U", f"#PLAYLIST:{label}"]
    for index, record in enumerate(successful, 1):
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise AudioBatchSafetyError("An audio playlist record lost its metadata")
        title = _single_line_text(record.get("title"), limit=512) or f"Sound {index:05d}"
        output_path = record.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise AudioBatchSafetyError("A successful audio row lost its payload path")
        lines.append(
            f"#EXTINF:{_playlist_duration(metadata.get('duration_seconds'))},{title}"
        )
        lines.append(output_path)
    return ("\n".join(lines) + "\n").encode("utf-8"), len(successful)


def _safe_failure_detail(error: Exception, private_root: Path) -> str:
    """Keep a useful bounded error without disclosing the temporary workspace."""

    detail = " ".join(str(error).split())
    detail = detail.replace(str(private_root), "<private-export-workspace>")
    if not detail:
        detail = error.__class__.__name__
    return detail[:400]


def _zip_info(relative: PurePosixPath, *, size: int | None = None) -> zipfile.ZipInfo:
    name = relative.as_posix()
    if relative.is_absolute() or ".." in relative.parts or name.startswith("/"):
        raise AudioBatchSafetyError("A batch payload path escaped its private archive")
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    if size is not None:
        info.file_size = size
    return info


def _add_regular_payload(
    archive: zipfile.ZipFile,
    source: Path,
    relative: PurePosixPath,
) -> tuple[int, str]:
    """Stream a non-symlink regular file into a deterministic ZIP member."""

    try:
        before_path = source.lstat()
    except FileNotFoundError as exc:
        raise AudioBatchExportError("The single-sound exporter produced no file") from exc
    if (
        not stat.S_ISREG(before_path.st_mode)
        or stat.S_ISLNK(before_path.st_mode)
        or before_path.st_size <= 0
    ):
        raise AudioBatchExportError(
            "The single-sound exporter did not produce a non-empty regular file"
        )
    descriptor = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (before_path.st_dev, before_path.st_ino, before_path.st_size)
        ):
            raise AudioBatchSafetyError(
                "The generated sound changed before it could be archived"
            )
        digest = hashlib.sha256()
        with archive.open(
            _zip_info(relative, size=opened.st_size), "w", force_zip64=True
        ) as output:
            remaining = opened.st_size
            while remaining:
                block = os.read(descriptor, min(_COPY_BLOCK_SIZE, remaining))
                if not block:
                    raise AudioBatchSafetyError(
                        "The generated sound ended while it was being archived"
                    )
                output.write(block)
                digest.update(block)
                remaining -= len(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    final = source.lstat()
    identity = (opened.st_dev, opened.st_ino, opened.st_size)
    if (
        (after.st_dev, after.st_ino, after.st_size) != identity
        or stat.S_ISLNK(final.st_mode)
        or (final.st_dev, final.st_ino, final.st_size) != identity
    ):
        # The ZIP member cannot be removed safely after a concurrent mutation;
        # aborting the whole unpublished archive is the fail-closed outcome.
        raise AudioBatchSafetyError(
            "The generated sound changed while it was being archived"
        )
    return opened.st_size, digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(_COPY_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def _require_source_sha256(value: str) -> str:
    if (
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AudioBatchExportError(
            "The source fingerprint must be a lowercase SHA-256 digest"
        )
    return value


def _validate_external_bank_identity(identity: ExternalAudioBankIdentity) -> None:
    outer = identity.outer_table_index
    name_id = identity.name_id
    encoded_size = identity.encoded_size
    filename = identity.external_filename
    if (
        isinstance(outer, bool)
        or not isinstance(outer, int)
        or outer < 0
        or outer > 99_999
    ):
        raise AudioBatchExportError(
            "An external audio bank has an invalid outer-record index"
        )
    if (
        isinstance(name_id, bool)
        or not isinstance(name_id, int)
        or name_id < 0
        or name_id > 0xFFFFFFFF
    ):
        raise AudioBatchExportError(
            f"External audio bank outer {outer} has an invalid name ID"
        )
    if (
        isinstance(encoded_size, bool)
        or not isinstance(encoded_size, int)
        or encoded_size <= 0
    ):
        raise AudioBatchExportError(
            f"External audio bank outer {outer} has an invalid encoded size"
        )
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
        or not filename.casefold().endswith(".bin")
    ):
        raise AudioBatchExportError(
            f"External audio bank outer {outer} has an unsafe source filename"
        )
    if not identity.owners:
        raise AudioBatchExportError(
            f"External audio bank outer {outer} has no AUSB descriptor owner"
        )
    coordinates: set[tuple[int, int]] = set()
    for owner in identity.owners:
        values = (
            owner.descriptor_outer_index,
            owner.descriptor_inner_index,
            owner.substream_count,
            owner.sample_rate,
            owner.channel_count,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in values
        ):
            raise AudioBatchExportError(
                f"External audio bank outer {outer} has invalid descriptor metadata"
            )
        if owner.substream_count <= 0 or owner.sample_rate <= 0 or owner.channel_count <= 0:
            raise AudioBatchExportError(
                f"External audio bank outer {outer} has incomplete descriptor metadata"
            )
        if not isinstance(owner.bank_name, str) or not owner.bank_name.strip():
            raise AudioBatchExportError(
                f"External audio bank outer {outer} has an unnamed descriptor owner"
            )
        if owner.coordinates in coordinates:
            raise AudioBatchExportError(
                f"External audio bank outer {outer} repeats a descriptor owner"
            )
        coordinates.add(owner.coordinates)


def _external_bank_payload_path(
    identity: ExternalAudioBankIdentity,
) -> PurePosixPath:
    """Return the deterministic, coordinate-prefixed private ZIP path."""

    source_stem = Path(identity.external_filename).stem
    safe_stem = _SAFE_BANK_STEM.sub("-", source_stem).strip("-._")
    safe_stem = (safe_stem or "external-bank")[:80]
    return PurePosixPath(
        "banks", f"o{identity.outer_table_index:05d}-{safe_stem}.bin"
    )


def _owner_document(owner: ExternalAudioBankOwner) -> dict[str, object]:
    role_id, role_basis = classify_ausb_role(owner.bank_name)
    return {
        "descriptor_outer_index": owner.descriptor_outer_index,
        "descriptor_inner_index": owner.descriptor_inner_index,
        "audio_source_id": owner.audio_source_id,
        "bank_name": owner.bank_name,
        "substream_count": owner.substream_count,
        "sample_rate": owner.sample_rate,
        "channel_count": owner.channel_count,
        "role_id": role_id,
        "role_label": AUDIO_ROLE_LABELS[role_id],
        "role_basis": role_basis,
    }


def _external_bank_record_base(
    identity: ExternalAudioBankIdentity,
) -> dict[str, object]:
    owners = tuple(_owner_document(owner) for owner in identity.owners)
    role_ids = tuple(dict.fromkeys(str(owner["role_id"]) for owner in owners))
    return {
        "outer_table_index": identity.outer_table_index,
        "original_filename": identity.external_filename,
        "name_id": f"0x{identity.name_id:08x}",
        "name_id_unsigned": identity.name_id,
        "source_encoded_size": identity.encoded_size,
        "raw_asset_id": identity.raw_asset_id,
        "descriptor_owner_count": len(owners),
        "descriptor_owners": owners,
        "linked_audio_source_ids": identity.linked_audio_source_ids,
        "linked_role_ids": role_ids,
        "linked_role_labels": tuple(AUDIO_ROLE_LABELS[value] for value in role_ids),
        "replacement_supported": False,
    }


def _cancelled_external_bank_record(
    identity: ExternalAudioBankIdentity,
) -> dict[str, object]:
    return {
        **_external_bank_record_base(identity),
        "status": "cancelled",
        "output_path": None,
        "file_size": None,
        "file_sha256": None,
        "error_code": "bundle_cancelled",
        "message": "Not attempted because cancellation was requested.",
    }


class ApfExternalAudioBankBundleExporter:
    """Atomic private export of proved original external XMA1 bank files."""

    def __init__(self, bank_exporter: ExternalAudioBankExporter):
        if not callable(getattr(bank_exporter, "export_external_audio_bank", None)):
            raise AudioBatchExportError(
                "External audio-bank bundling requires the verified original-bank exporter"
            )
        self._bank_exporter = bank_exporter

    def export_all(
        self,
        identities: Iterable[ExternalAudioBankIdentity],
        destination: Path,
        *,
        source_sha256: str,
        bundle_name: str = "APF 2K8 original external audio banks",
        progress: ExternalBankProgressHook | None = None,
        cancel_requested: CancellationHook | None = None,
    ) -> ExternalAudioBankBundleReceipt:
        """Export up to the complete 19-bank retail surface as one private ZIP.

        Ordinary source/export failures are recorded per bank and later banks
        continue.  A filesystem-integrity failure aborts the unpublished ZIP.
        Cancellation is observed only between banks, so no individual bank is
        ever deliberately cut short.
        """

        selected = tuple(identities)
        destination = destination.expanduser()
        _require_source_sha256(source_sha256)
        if destination.suffix.casefold() != ".zip":
            raise AudioBatchExportError(
                "An external APF audio-bank bundle destination must end in .zip"
            )
        if not selected:
            raise AudioBatchExportError(
                "No original APF external audio banks were supplied"
            )
        if len(selected) > MAX_EXTERNAL_AUDIO_BANKS:
            raise AudioBatchExportError(
                "One APF external audio-bank bundle is limited to "
                f"{MAX_EXTERNAL_AUDIO_BANKS} banks"
            )
        for identity in selected:
            _validate_external_bank_identity(identity)
        outer_indices = tuple(identity.outer_table_index for identity in selected)
        if len(set(outer_indices)) != len(outer_indices):
            raise AudioBatchExportError(
                "An external audio-bank outer-record index was supplied more than once"
            )
        ordered = tuple(sorted(selected, key=lambda identity: identity.outer_table_index))
        payload_paths = tuple(_external_bank_payload_path(identity) for identity in ordered)
        if len(set(payload_paths)) != len(payload_paths):
            raise AudioBatchSafetyError(
                "External audio-bank ZIP paths unexpectedly collided"
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)

        report = progress or (lambda _event: None)
        wants_cancel = cancel_requested or (lambda: False)
        total = len(ordered)
        succeeded = failed = cancelled = payload_bytes = 0
        records: list[dict[str, object]] = []
        was_cancelled = False

        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".exporting",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary_archive = Path(temporary_name)
        temporary_archive.unlink()
        try:
            with tempfile.TemporaryDirectory(
                prefix="apf-external-audio-banks-work-"
            ) as private_name:
                private_root = Path(private_name)
                candidate = private_root / "original-bank.bin"
                report(
                    ExternalAudioBankBundleProgress(
                        "preparing", 0, total, 0, 0, 0
                    )
                )
                with zipfile.ZipFile(
                    temporary_archive,
                    "x",
                    compression=zipfile.ZIP_STORED,
                    allowZip64=True,
                ) as archive:
                    for index, (identity, relative) in enumerate(
                        zip(ordered, payload_paths, strict=True)
                    ):
                        if wants_cancel():
                            was_cancelled = True
                            for remaining in ordered[index:]:
                                records.append(
                                    _cancelled_external_bank_record(remaining)
                                )
                                cancelled += 1
                            break

                        candidate.unlink(missing_ok=True)

                        def bank_progress(completed: int, size: int) -> None:
                            nonlocal progress_failure
                            try:
                                report(
                                    ExternalAudioBankBundleProgress(
                                        "exporting_bank",
                                        index,
                                        total,
                                        succeeded,
                                        failed,
                                        cancelled,
                                        identity.external_filename,
                                        completed,
                                        size,
                                    )
                                )
                            except Exception as exc:
                                progress_failure = exc
                                raise

                        progress_failure: Exception | None = None
                        try:
                            self._bank_exporter.export_external_audio_bank(
                                identity,
                                candidate,
                                progress=bank_progress,
                            )
                            candidate_stat = candidate.lstat()
                            if (
                                stat.S_ISLNK(candidate_stat.st_mode)
                                or not stat.S_ISREG(candidate_stat.st_mode)
                                or candidate_stat.st_size != identity.encoded_size
                            ):
                                raise AudioBatchExportError(
                                    "The original-bank exporter produced a file whose "
                                    "size or type does not match its source identity"
                                )
                            file_size, file_sha256 = _add_regular_payload(
                                archive, candidate, relative
                            )
                            if file_size != identity.encoded_size:
                                raise AudioBatchSafetyError(
                                    "An external audio bank changed size while it was archived"
                                )
                        except AudioBatchSafetyError:
                            raise
                        except Exception as exc:
                            if progress_failure is exc:
                                raise
                            records.append(
                                {
                                    **_external_bank_record_base(identity),
                                    "status": "failure",
                                    "output_path": None,
                                    "file_size": None,
                                    "file_sha256": None,
                                    "error_code": "original_bank_export_failed",
                                    "message": (
                                        "The verified original-bank export route failed: "
                                        + _safe_failure_detail(exc, private_root)
                                    ),
                                }
                            )
                            failed += 1
                        else:
                            records.append(
                                {
                                    **_external_bank_record_base(identity),
                                    "status": "success",
                                    "output_path": relative.as_posix(),
                                    "file_size": file_size,
                                    "file_sha256": file_sha256,
                                    "error_code": None,
                                    "message": (
                                        "Exact original external XMA1 packet bank exported."
                                    ),
                                }
                            )
                            succeeded += 1
                            payload_bytes += file_size
                        finally:
                            candidate.unlink(missing_ok=True)
                        report(
                            ExternalAudioBankBundleProgress(
                                "exporting",
                                index + 1,
                                total,
                                succeeded,
                                failed,
                                cancelled,
                                identity.external_filename,
                                identity.encoded_size,
                                identity.encoded_size,
                            )
                        )

                    if succeeded + failed + cancelled != total:
                        raise AudioBatchSafetyError(
                            "The external audio-bank manifest no longer accounts for every bank"
                        )
                    manifest = {
                        "schema": EXTERNAL_BANK_MANIFEST_SCHEMA,
                        "bundle_name": " ".join(bundle_name.split())[:160]
                        or "APF 2K8 original external audio banks",
                        "source_sha256": source_sha256,
                        "was_cancelled": was_cancelled,
                        "counts": {
                            "requested": total,
                            "success": succeeded,
                            "failure": failed,
                            "cancelled": cancelled,
                        },
                        "payload_bytes": payload_bytes,
                        "archive_layout": (
                            "banks/oNNNNN-<safe-source-name>.bin; ZIP_STORED"
                        ),
                        "capability_boundary": {
                            "export": (
                                "Exact original external XMA1 packet-bank bytes "
                                "from the user-supplied game source"
                            ),
                            "replacement_supported": False,
                            "replacement_note": (
                                "A physical bank contains many addressed cues. No "
                                "validated XMA1 encoder, cue/loop ownership writer, "
                                "or reversible bank replacement route exists."
                            ),
                        },
                        "distribution_note": (
                            "This private ZIP contains retail-derived game audio. "
                            "Do not distribute it or place it in a shareable Mod "
                            "Studio project."
                        ),
                        "banks": records,
                    }
                    manifest_bytes = (
                        json.dumps(
                            manifest,
                            indent=2,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8")
                    archive.writestr(
                        _zip_info(PurePosixPath("manifest.json")), manifest_bytes
                    )

            # The bundle must be on the platter before it is hard-linked into
            # its published name.  ``fsync_path`` keeps the POSIX ``O_RDONLY``
            # flush and opens read-write only on Windows, where
            # ``FlushFileBuffers`` refuses a read-only handle with ``EBADF``.
            fsync_path(temporary_archive)
            archive_sha256 = _sha256_file(temporary_archive)
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            os.link(temporary_archive, destination)
            temporary_archive.unlink()
            report(
                ExternalAudioBankBundleProgress(
                    "cancelled" if was_cancelled else "complete",
                    total,
                    total,
                    succeeded,
                    failed,
                    cancelled,
                )
            )
            return ExternalAudioBankBundleReceipt(
                path=destination,
                requested=total,
                succeeded=succeeded,
                failed=failed,
                cancelled=cancelled,
                was_cancelled=was_cancelled,
                payload_bytes=payload_bytes,
                archive_sha256=archive_sha256,
                manifest_sha256=manifest_sha256,
            )
        except BaseException:
            temporary_archive.unlink(missing_ok=True)
            raise


class ApfAudioBatchExporter:
    """Batch service over the existing verified single-asset audio exporter."""

    def __init__(self, identity_exporter: AudioIdentityExporter):
        if not callable(getattr(identity_exporter, "export_audio_identity", None)):
            raise AudioBatchExportError(
                "Audio batch export requires the verified single-sound export service"
            )
        self._identity_exporter = identity_exporter

    def export_all(
        self,
        snapshot: AudioSnapshot,
        destination: Path,
        **options: object,
    ) -> AudioBatchReceipt:
        """Export every row in a source-derived :class:`AudioSnapshot`."""

        return self.export_selected(
            audio_snapshot_rows(snapshot), destination, **options
        )

    def export_selected(
        self,
        rows: Iterable[InspectorRow],
        destination: Path,
        *,
        output_extension: str = ".xma",
        batch_name: str = "APF 2K8 audio export",
        source_sha256: str | None = None,
        progress: ProgressHook | None = None,
        cancel_requested: CancellationHook | None = None,
    ) -> AudioBatchReceipt:
        """Export selected semantic rows to a new, atomically published ZIP.

        Ordinary per-sound failures are recorded and the next row is attempted.
        Filesystem-integrity failures abort without publishing an archive.
        Cancellation publishes a partial archive whose manifest accounts for
        all rows and labels unattempted rows ``cancelled``.
        """

        selected = tuple(rows)
        destination = destination.expanduser()
        extension = output_extension.casefold()
        if extension not in SUPPORTED_OUTPUT_EXTENSIONS:
            raise AudioBatchExportError(
                "APF audio batches export as original .xma or decoder-verified .wav"
            )
        if destination.suffix.casefold() != ".zip":
            raise AudioBatchExportError("An APF audio batch destination must end in .zip")
        if not selected:
            raise AudioBatchExportError("Select at least one semantic audio row")
        if len(selected) > MAX_BATCH_ROWS:
            raise AudioBatchExportError(
                f"One APF audio batch is limited to {MAX_BATCH_ROWS:,} semantic rows"
            )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        if source_sha256 is not None and (
            len(source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in source_sha256)
        ):
            raise AudioBatchExportError(
                "The optional source fingerprint must be a lowercase SHA-256 digest"
            )

        report = progress or (lambda _event: None)
        wants_cancel = cancel_requested or (lambda: False)
        total = len(selected)
        succeeded = failed = unsupported = cancelled = payload_bytes = 0
        records: list[dict[str, object]] = []
        seen_row_ids: set[str] = set()
        seen_identities: set[tuple[str, int, int, int | None]] = set()
        was_cancelled = False
        normalized_batch_name = (
            _single_line_text(batch_name, limit=160) or "APF 2K8 audio export"
        )

        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".exporting",
            dir=destination.parent,
        )
        os.close(descriptor)
        temporary_archive = Path(temporary_name)
        temporary_archive.unlink()
        try:
            with tempfile.TemporaryDirectory(
                prefix="apf-audio-batch-work-"
            ) as private_name:
                private_root = Path(private_name)
                candidate = private_root / f"selected{extension}"
                report(
                    AudioBatchProgress(
                        "preparing", 0, total, 0, 0, 0, 0, None
                    )
                )
                with zipfile.ZipFile(
                    temporary_archive,
                    "x",
                    compression=zipfile.ZIP_STORED,
                    allowZip64=True,
                ) as archive:
                    for index, row in enumerate(selected):
                        if wants_cancel():
                            was_cancelled = True
                            for remaining in selected[index:]:
                                records.append(_cancelled_record(remaining))
                                cancelled += 1
                            break

                        record: dict[str, object]
                        normalized_kind = row.kind.strip().casefold()
                        if (
                            normalized_kind in _PHYSICAL_OR_INDEX_KINDS
                            or row.external_bank_identity is not None
                        ):
                            if normalized_kind == "ausb_bank":
                                code = "ausb_index_not_playable"
                                message = (
                                    "This AUSB bank row is an index, not a playable sound. "
                                    "Export its addressed substream rows instead."
                                )
                            else:
                                code = "physical_bank_not_a_cue"
                                message = (
                                    "A physical XMA1 bank is a multi-cue container, not one "
                                    "playable sound. Batch payload export is intentionally "
                                    "limited to addressed substream rows."
                                )
                            record = _unsupported_record(row, code, message)
                            unsupported += 1
                        elif row.row_id in seen_row_ids:
                            record = _failure_record(
                                row,
                                "duplicate_row_id",
                                "The same semantic row was selected more than once.",
                            )
                            failed += 1
                        elif row.export_identity is None:
                            record = _unsupported_record(
                                row,
                                "no_single_sound_export_identity",
                                "No verified single-sound exporter owns this semantic row.",
                            )
                            unsupported += 1
                        else:
                            identity = row.export_identity
                            key = (
                                identity.kind,
                                identity.outer_table_index,
                                identity.inner_file_index,
                                identity.substream_index,
                            )
                            if key in seen_identities:
                                record = _failure_record(
                                    row,
                                    "duplicate_export_coordinates",
                                    (
                                        "Another selected row already owns these exact "
                                        "sound coordinates."
                                    ),
                                )
                                failed += 1
                            elif extension not in identity.supported_extensions:
                                record = _unsupported_record(
                                    row,
                                    "format_not_supported_by_identity",
                                    f"This sound does not advertise {extension} export support.",
                                )
                                unsupported += 1
                            else:
                                try:
                                    relative = _payload_path(identity, extension)
                                except AudioBatchExportError as exc:
                                    record = _unsupported_record(
                                        row,
                                        "invalid_or_unsupported_export_identity",
                                        str(exc),
                                    )
                                    unsupported += 1
                                else:
                                    candidate.unlink(missing_ok=True)
                                    try:
                                        self._identity_exporter.export_audio_identity(
                                            identity, candidate
                                        )
                                        file_size, file_sha256 = _add_regular_payload(
                                            archive, candidate, relative
                                        )
                                    except AudioBatchSafetyError:
                                        raise
                                    except Exception as exc:
                                        record = _failure_record(
                                            row,
                                            "single_sound_export_failed",
                                            (
                                                "The verified single-sound export route failed: "
                                                + _safe_failure_detail(exc, private_root)
                                            ),
                                        )
                                        failed += 1
                                    else:
                                        record = {
                                            **_record_base(row),
                                            "status": "success",
                                            "output_path": relative.as_posix(),
                                            "file_size": file_size,
                                            "file_sha256": file_sha256,
                                            "error_code": None,
                                            "message": (
                                                "Original XMA1 sound exported."
                                                if extension == ".xma"
                                                else "Decoder-verified PCM WAV exported."
                                            ),
                                        }
                                        succeeded += 1
                                        payload_bytes += file_size
                                    finally:
                                        candidate.unlink(missing_ok=True)
                            seen_identities.add(key)
                        seen_row_ids.add(row.row_id)
                        records.append(record)
                        completed = index + 1
                        report(
                            AudioBatchProgress(
                                "exporting",
                                completed,
                                total,
                                succeeded,
                                failed,
                                unsupported,
                                cancelled,
                                row.row_id,
                            )
                        )

                    counts = {
                        "requested": total,
                        "success": succeeded,
                        "failure": failed,
                        "unsupported": unsupported,
                        "cancelled": cancelled,
                    }
                    if succeeded + failed + unsupported + cancelled != total:
                        raise AudioBatchSafetyError(
                            "The audio batch manifest no longer accounts for every row"
                        )
                    catalog_bytes, catalog_record_count = _catalog_bytes(records)
                    if catalog_record_count != total:
                        raise AudioBatchSafetyError(
                            "The audio CSV catalog no longer accounts for every row"
                        )
                    archive.writestr(
                        _zip_info(PurePosixPath("catalog.csv")), catalog_bytes
                    )
                    playlist_bytes, playlist_record_count = _playlist_bytes(
                        normalized_batch_name, records
                    )
                    if playlist_record_count != succeeded:
                        raise AudioBatchSafetyError(
                            "The audio playlist no longer accounts for every successful row"
                        )
                    if playlist_bytes is not None:
                        archive.writestr(
                            _zip_info(PurePosixPath("playlist.m3u8")), playlist_bytes
                        )
                    manifest = {
                        "schema": MANIFEST_SCHEMA,
                        "batch_name": normalized_batch_name,
                        "source_sha256": source_sha256,
                        "requested_format": extension.removeprefix("."),
                        "was_cancelled": was_cancelled,
                        "counts": counts,
                        "payload_bytes": payload_bytes,
                        "catalog": "catalog.csv",
                        "catalog_record_count": catalog_record_count,
                        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
                        "playlist": (
                            "playlist.m3u8" if playlist_record_count else None
                        ),
                        "playlist_record_count": playlist_record_count,
                        "playlist_sha256": (
                            hashlib.sha256(playlist_bytes).hexdigest()
                            if playlist_bytes is not None
                            else None
                        ),
                        "capability_boundary": {
                            "export": (
                                "Original XMA1 or decoder-verified PCM WAV from the "
                                "user-supplied game source"
                            ),
                            "replacement_supported": False,
                            "replacement_note": (
                                "This service does not encode XMA1, replace cues, or "
                                "rewrite AUSB/physical banks."
                            ),
                        },
                        "distribution_note": (
                            "The payloads are retail-derived from the user's own game "
                            "and are not part of Mod Studio or a shareable mod project."
                        ),
                        "records": records,
                    }
                    manifest_bytes = (
                        json.dumps(
                            manifest,
                            indent=2,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8")
                    archive.writestr(
                        _zip_info(PurePosixPath("manifest.json")), manifest_bytes
                    )

            # Durability before publication: the archive reaches the platter
            # first, then the hard link names it.  ``fsync_path`` preserves that
            # order on every platform (Windows needs a writable handle for
            # ``FlushFileBuffers``; POSIX keeps its ``O_RDONLY`` flush).
            fsync_path(temporary_archive)
            archive_sha256 = _sha256_file(temporary_archive)
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            # A hard link publishes the complete same-directory archive without
            # overwriting a destination that appears concurrently.
            os.link(temporary_archive, destination)
            temporary_archive.unlink()
            report(
                AudioBatchProgress(
                    "cancelled" if was_cancelled else "complete",
                    total,
                    total,
                    succeeded,
                    failed,
                    unsupported,
                    cancelled,
                    None,
                )
            )
            return AudioBatchReceipt(
                path=destination,
                requested=total,
                succeeded=succeeded,
                failed=failed,
                unsupported=unsupported,
                cancelled=cancelled,
                was_cancelled=was_cancelled,
                output_extension=extension,
                payload_bytes=payload_bytes,
                catalog_record_count=catalog_record_count,
                playlist_record_count=playlist_record_count,
                archive_sha256=archive_sha256,
                manifest_sha256=manifest_sha256,
            )
        except BaseException:
            temporary_archive.unlink(missing_ok=True)
            raise


__all__ = [
    "AudioBatchExportError",
    "AudioBatchProgress",
    "AudioBatchReceipt",
    "AudioBatchSafetyError",
    "ApfAudioBatchExporter",
    "ApfExternalAudioBankBundleExporter",
    "EXTERNAL_BANK_MANIFEST_SCHEMA",
    "ExternalAudioBankBundleProgress",
    "ExternalAudioBankBundleReceipt",
    "MANIFEST_SCHEMA",
    "MAX_BATCH_ROWS",
    "MAX_EXTERNAL_AUDIO_BANKS",
    "audio_snapshot_rows",
]
