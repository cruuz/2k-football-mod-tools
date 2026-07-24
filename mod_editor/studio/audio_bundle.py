"""Transactional local audio-collection exports for 2K5 Mod Studio.

This module deliberately knows nothing about the retail source or the active
project.  Callers describe each selected row with metadata and provide a
payload writer which exports that row into a private temporary path.  Only a
complete ZIP is published, and publication can never replace a file which the
user (or another process) created first.

Audio bundles are local exports containing retail-derived and/or user-authored
audio.  They are not shareable ``.2k5mod`` projects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_catalog import (
    Nfl2k5AudioAsset,
    Nfl2k5StreamingAudioBank,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core import platform_compat
from mod_editor.core.platform_compat import fsync_path


AUDIO_BUNDLE_SCHEMA = "nfl2k5_mod_studio_audio_bundle_export/v1"
MAX_BUNDLE_ROWS = 256
# Large enough for a decoded soundtrack collection, while making an accidental
# multi-gigabyte broad export structurally impossible.
MAX_BUNDLE_PAYLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_ROW_METADATA_BYTES = 64 * 1024
_CONTENT_ORIGINS = frozenset({"retail_derived", "user_replacement"})
_OUTPUT_EXTENSIONS = frozenset({".bin", ".wav"})
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_COPY_BLOCK = 1024 * 1024


class AudioBundleError(ValidationError):
    """A local audio bundle request failed its bounded safety contract."""


@dataclass(frozen=True, slots=True)
class AudioBundleRow:
    """One selected browser row and the metadata written beside its payload.

    ``predicted_payload_bytes`` is the caller's preflight estimate for the
    requested output format.  It is checked before any payload writer runs.
    The core also enforces the same aggregate limit against actual output.
    """

    stable_id: str
    display_name: str
    suggested_basename: str
    extension: str
    predicted_payload_bytes: int
    content_origin: str
    metadata: Mapping[str, object] = field(default_factory=dict)


PayloadWriter = Callable[[AudioBundleRow, Path], Path | None]
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class _PreparedRow:
    row: AudioBundleRow
    metadata: dict[str, object]
    relative_path: str


def _checked_text(value: object, label: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise AudioBundleError(f"Audio bundle {label} must be text")
    checked = value.strip()
    if not checked or len(checked) > limit:
        raise AudioBundleError(
            f"Audio bundle {label} must contain 1–{limit} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in checked):
        raise AudioBundleError(f"Audio bundle {label} contains control characters")
    return checked


def _safe_stem(value: str, extension: str, index: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("._-")
    for known_extension in _OUTPUT_EXTENSIONS:
        if stem.casefold().endswith(known_extension):
            stem = stem[: -len(known_extension)].rstrip("._-")
            break
    stem = stem[:96].rstrip("._-")
    return stem or f"sound-{index:03d}"


def _normalized_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise AudioBundleError("Audio bundle row metadata must be a JSON object")
    if not all(isinstance(key, str) and key for key in value):
        raise AudioBundleError("Audio bundle metadata keys must be non-empty text")
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AudioBundleError("Audio bundle row metadata must be valid JSON") from exc
    if len(encoded) > MAX_ROW_METADATA_BYTES:
        raise AudioBundleError(
            f"Audio bundle row metadata exceeds {MAX_ROW_METADATA_BYTES:,} bytes"
        )
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # Defensive; Mapping always encoded as an object.
        raise AudioBundleError("Audio bundle row metadata must be a JSON object")
    return decoded


def _prepare_rows(
    rows: Iterable[AudioBundleRow], max_payload_bytes: int
) -> tuple[tuple[_PreparedRow, ...], int]:
    if (
        type(max_payload_bytes) is not int
        or not 1 <= max_payload_bytes <= MAX_BUNDLE_PAYLOAD_BYTES
    ):
        raise AudioBundleError(
            "Audio bundle payload limit must be between 1 byte and "
            f"{MAX_BUNDLE_PAYLOAD_BYTES:,} bytes"
        )
    selected = tuple(rows)
    if not 1 <= len(selected) <= MAX_BUNDLE_ROWS:
        raise AudioBundleError(
            f"Audio bundle export requires 1–{MAX_BUNDLE_ROWS} selected rows"
        )

    prepared: list[_PreparedRow] = []
    seen_ids: set[str] = set()
    predicted_total = 0
    for index, row in enumerate(selected, 1):
        if not isinstance(row, AudioBundleRow):
            raise AudioBundleError("Every audio bundle item must be an AudioBundleRow")
        stable_id = _checked_text(row.stable_id, "stable ID", limit=512)
        if stable_id in seen_ids:
            raise AudioBundleError(
                f"Audio bundle rows must have unique stable IDs: {stable_id}"
            )
        seen_ids.add(stable_id)
        _checked_text(row.display_name, "display name", limit=512)
        suggested = _checked_text(
            row.suggested_basename, "suggested filename", limit=512
        )
        extension = row.extension.casefold() if isinstance(row.extension, str) else ""
        if extension not in _OUTPUT_EXTENSIONS:
            raise AudioBundleError("Audio bundle outputs must be .wav or raw .bin")
        if row.content_origin not in _CONTENT_ORIGINS:
            raise AudioBundleError(
                "Audio bundle content origin must be retail_derived or user_replacement"
            )
        if type(row.predicted_payload_bytes) is not int \
                or row.predicted_payload_bytes < 1:
            raise AudioBundleError(
                "Audio bundle predicted payload sizes must be positive integers"
            )
        predicted_total += row.predicted_payload_bytes
        if predicted_total > max_payload_bytes:
            raise AudioBundleError(
                "The predicted audio payload exceeds the bounded bundle limit; "
                "narrow the current filters"
            )
        safe_stem = _safe_stem(suggested, extension, index)
        prepared.append(
            _PreparedRow(
                row=row,
                metadata=_normalized_metadata(row.metadata),
                relative_path=f"audio/{index:03d}-{safe_stem}{extension}",
            )
        )
    return tuple(prepared), predicted_total


def bundle_row_for_asset(
    asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioBank | Nfl2k5StreamingAudioRange,
    *,
    output_format: str,
    content_origin: str,
) -> AudioBundleRow:
    """Describe one catalog asset with shared, exact bundle semantics.

    ``output_format`` accepts ``wav``/``.wav`` or ``bin``/``.bin``. Standalone
    AUDO resources export only as playable WAV, complete streaming banks only
    as raw BIN, and indexed streaming ranges as either. A Modified indexed
    range exports its current user-replacement WAV; raw range/bank payloads are
    always retail-derived.
    """

    if not isinstance(output_format, str):
        raise AudioBundleError("Audio bundle output format must be wav or bin")
    normalized = output_format.strip().casefold()
    extension = normalized if normalized.startswith(".") else f".{normalized}"
    if extension not in _OUTPUT_EXTENSIONS:
        raise AudioBundleError("Audio bundle output format must be wav or bin")
    if content_origin not in _CONTENT_ORIGINS:
        raise AudioBundleError(
            "Audio bundle content origin must be retail_derived or user_replacement"
        )

    if not isinstance(
        asset,
        (Nfl2k5AudioAsset, Nfl2k5StreamingAudioBank, Nfl2k5StreamingAudioRange),
    ):
        raise AudioBundleError("That object is not a supported 2K5 audio asset")
    common: dict[str, object] = {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "scope_id": asset.scope_id,
        "family_id": asset.family_id,
        "family_label": asset.family_label,
        "container_label": asset.container_label,
        "source_format_label": asset.format_label,
        "edit_status": asset.edit_status,
        "current_status": (
            "Modified" if content_origin == "user_replacement" else asset.edit_status
        ),
        "outer_index": asset.outer_index,
        "outer_id": asset.outer_id,
        "chunk_index": asset.chunk_index,
        "sample_rate": asset.sample_rate,
    }

    if isinstance(asset, Nfl2k5AudioAsset):
        if extension != ".wav":
            raise AudioBundleError("Standalone 2K5 sounds export as playable WAV")
        if content_origin == "user_replacement" and not asset.editable:
            raise AudioBundleError(
                "An export-only standalone sound cannot be labeled as a user replacement"
            )
        common.update(
            {
                "channels": asset.channels,
                "frame_count": asset.frame_count,
                "duration_seconds": asset.duration_seconds,
            }
        )
        return AudioBundleRow(
            stable_id=asset.asset_id,
            display_name=asset.name,
            suggested_basename=asset.suggested_filename,
            extension=extension,
            predicted_payload_bytes=44 + asset.frame_count * asset.channels * 2,
            content_origin=content_origin,
            metadata=common,
        )

    if isinstance(asset, Nfl2k5StreamingAudioBank):
        if content_origin != "retail_derived":
            raise AudioBundleError(
                "Complete streaming banks cannot be user replacements"
            )
        if extension != ".bin":
            raise AudioBundleError("Complete 2K5 streaming banks export as raw BIN")
        common.update(
            {
                "role_class": asset.role_class,
                "external_filename": asset.external_filename,
                "external_outer_index": asset.external_outer_index,
                "external_size": asset.external_size,
                "entry_count": asset.entry_count,
                "channels": asset.channel_word,
            }
        )
        return AudioBundleRow(
            stable_id=asset.asset_id,
            display_name=asset.name,
            suggested_basename=asset.suggested_filename,
            extension=extension,
            predicted_payload_bytes=asset.external_size,
            content_origin=content_origin,
            metadata=common,
        )

    assert isinstance(asset, Nfl2k5StreamingAudioRange)
    if content_origin == "user_replacement":
        if extension != ".wav":
            raise AudioBundleError(
                "Streaming-range user replacements export as playable WAV, not raw BIN"
            )
        if not asset.editable:
            raise AudioBundleError(
                "An export-only streaming range cannot be labeled as a user replacement"
            )
    common.update(
        {
            "role_class": asset.role_class,
            "external_filename": asset.external_filename,
            "external_outer_index": asset.external_outer_index,
            "range_index": asset.range_index,
            "start": asset.start,
            "end": asset.end,
            "stored_size": asset.stored_size,
            "channels": asset.channels,
            "frame_count": asset.frame_count,
            "duration_seconds": asset.duration_seconds,
        }
    )
    return AudioBundleRow(
        stable_id=asset.asset_id,
        display_name=asset.name,
        suggested_basename=(
            asset.suggested_wav_filename
            if extension == ".wav"
            else asset.suggested_filename
        ),
        extension=extension,
        predicted_payload_bytes=(
            44 + asset.frame_count * asset.channels * 2
            if extension == ".wav"
            else asset.stored_size
        ),
        content_origin=content_origin,
        metadata=common,
    )


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _stream_payload_into_zip(
    archive: zipfile.ZipFile,
    source: Path,
    relative_path: str,
    *,
    remaining_bytes: int,
) -> tuple[int, str]:
    try:
        supplied = source.lstat()
    except FileNotFoundError as exc:
        raise AudioBundleError("The audio payload writer did not create its output") from exc
    if stat.S_ISLNK(supplied.st_mode) or not stat.S_ISREG(supplied.st_mode):
        raise AudioBundleError("Audio bundle payloads must be regular, non-link files")
    if supplied.st_size < 1:
        raise AudioBundleError("Audio bundle payloads cannot be empty")
    if supplied.st_size > remaining_bytes:
        raise AudioBundleError(
            "The actual audio payload exceeds the bounded bundle limit"
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
            != (supplied.st_dev, supplied.st_ino, supplied.st_size)
        ):
            raise AudioBundleError("An audio bundle payload changed while opening")
        digest = hashlib.sha256()
        written = 0
        with archive.open(_zip_info(relative_path), "w", force_zip64=True) as member:
            while block := os.read(descriptor, _COPY_BLOCK):
                written += len(block)
                if written > remaining_bytes:
                    raise AudioBundleError(
                        "The actual audio payload exceeds the bounded bundle limit"
                    )
                digest.update(block)
                member.write(block)
        after = os.fstat(descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        )
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ) != identity or written != opened.st_size:
            raise AudioBundleError("An audio bundle payload changed while reading")
        return written, digest.hexdigest()
    finally:
        os.close(descriptor)


def _write_manifest(archive: zipfile.ZipFile, document: dict[str, object]) -> None:
    payload = (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    archive.writestr(_zip_info("manifest.json"), payload)


def _playlist_text(value: object, *, fallback: str) -> str:
    """Return one safe, single-line UTF-8 playlist label."""

    if not isinstance(value, str):
        return fallback
    cleaned = "".join(
        character if ord(character) >= 32 and ord(character) != 127 else " "
        for character in value
    ).strip()
    return cleaned or fallback


def _playlist_duration(metadata: object) -> str:
    if not isinstance(metadata, Mapping):
        return "-1"
    value = metadata.get("duration_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-1"
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        return "-1"
    return f"{duration:.3f}".rstrip("0").rstrip(".")


def _write_playlist(
    archive: zipfile.ZipFile,
    bundle_name: str,
    records: Iterable[Mapping[str, object]],
) -> int:
    """Write an ordered M3U8 for playable WAV members and return its size.

    Raw bank/range ``.bin`` members are deliberately omitted: presenting those
    encoded payloads to a normal media player as playable audio would be
    misleading.  The playlist contains paths and labels only; its audio bytes
    are the already selected, locally exported ZIP members.
    """

    playable = tuple(record for record in records if record.get("format") == "wav")
    if not playable:
        return 0
    lines = [
        "#EXTM3U",
        f"#PLAYLIST:{_playlist_text(bundle_name, fallback='2K5 audio collection')}",
    ]
    for index, record in enumerate(playable, 1):
        title = _playlist_text(
            record.get("display_name"), fallback=f"Sound {index:03d}"
        )
        lines.append(
            f"#EXTINF:{_playlist_duration(record.get('metadata'))},{title}"
        )
        lines.append(str(record["path"]))
    archive.writestr(
        _zip_info("playlist.m3u8"), ("\n".join(lines) + "\n").encode("utf-8")
    )
    return len(playable)


def _regular_file_identity(path: Path) -> tuple[int, int]:
    """``(st_dev, st_ino)`` of a finished bundle, refusing a symlink or non-regular file.

    Captured on Windows so the publisher can pin the exact archive it wrote:
    ``os.lstat`` does not follow a final reparse point, so this is the identity of
    the name itself, and a symlink or a non-regular file is refused outright.
    """

    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AudioBundleError(
            "The finished audio bundle is not a regular file; refusing to publish"
        )
    return (info.st_dev, info.st_ino)


def _exclusive_publish(
    source: Path, destination: Path, *, expected_identity: tuple[int, int] | None
) -> Path:
    """Hard-link the finished bundle to its destination, never overwriting.

    ``expected_identity`` is the ``(st_dev, st_ino)`` of the archive the caller
    wrote and flushed.  On Windows -- which has no ``O_NOFOLLOW``, so
    :func:`fsync_path` flushed the file we wrote but ``os.link`` re-resolves the
    name by path -- the source is re-checked without following a reparse point
    immediately before the link: a symlink, a non-regular file, or a *different*
    inode swapped in after the flush is refused rather than published, so a swap
    cannot redirect the published bytes.  The sub-operation window between this
    check and ``os.link`` is the same documented Windows realpath-pin residual.

    POSIX passes ``None`` and the publish is byte-identical: the ``O_NOFOLLOW``
    open inside :func:`fsync_path` already refused a symlink and the archive lives
    in a ``0o700`` private temporary directory only this user can write, so no
    identity compare is added to the Linux path.
    """

    if expected_identity is not None:
        current = os.lstat(source)
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != expected_identity
        ):
            raise AudioBundleError(
                "The finished audio bundle changed identity before publication; "
                "refusing to publish a swapped target"
            )
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise FileExistsError(
            f"A file already exists at the audio bundle destination: {destination}"
        ) from exc
    return destination.resolve(strict=True)


def export_audio_bundle(
    rows: Iterable[AudioBundleRow],
    destination: Path,
    *,
    bundle_name: str,
    payload_writer: PayloadWriter,
    progress: ProgressCallback | None = None,
    max_payload_bytes: int = MAX_BUNDLE_PAYLOAD_BYTES,
) -> Path:
    """Build and exclusively publish one bounded local audio ZIP.

    The writer receives an absent path inside a private temporary directory.
    It may return that path (matching existing Mod Studio exporters) or ``None``.
    Any exception, invalid payload, size-limit violation, or publication race
    removes the temporary work and leaves the requested destination untouched.
    """

    if not callable(payload_writer):
        raise AudioBundleError("Audio bundle payload writer is not callable")
    name = _checked_text(bundle_name, "name", limit=256)
    prepared, predicted_total = _prepare_rows(rows, max_payload_bytes)

    requested = Path(destination).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.casefold() != ".zip":
        raise AudioBundleError("Audio bundles must use a .zip filename")
    requested.parent.mkdir(parents=True, exist_ok=True)
    parent_info = requested.parent.lstat()
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise AudioBundleError(
            "The audio bundle destination folder must be a regular, non-link folder"
        )
    parent = requested.parent.resolve(strict=True)
    target = parent / requested.name
    if target.is_symlink():
        raise AudioBundleError("Refusing an audio bundle destination symbolic link")
    if os.path.lexists(target):
        raise FileExistsError(f"A file already exists there: {target}")

    report = progress or (lambda _completed, _total: None)
    report(0, len(prepared))
    with tempfile.TemporaryDirectory(
        prefix=f".{target.name}.exporting-", dir=parent
    ) as temporary_name:
        temporary_root = Path(temporary_name)
        payload_root = temporary_root / "audio"
        payload_root.mkdir()
        archive_path = temporary_root / "complete.zip"
        records: list[dict[str, object]] = []
        actual_total = 0
        with zipfile.ZipFile(
            archive_path,
            "x",
            compression=zipfile.ZIP_DEFLATED,
            allowZip64=True,
        ) as archive:
            for completed, item in enumerate(prepared, 1):
                output = temporary_root / item.relative_path
                returned = payload_writer(item.row, output)
                if returned is not None:
                    try:
                        same_output = os.path.samefile(Path(returned), output)
                    except (FileNotFoundError, OSError, TypeError) as exc:
                        raise AudioBundleError(
                            "The audio payload writer returned an unexpected path"
                        ) from exc
                    if not same_output:
                        raise AudioBundleError(
                            "The audio payload writer returned an unexpected path"
                        )
                payload_size, payload_sha256 = _stream_payload_into_zip(
                    archive,
                    output,
                    item.relative_path,
                    remaining_bytes=max_payload_bytes - actual_total,
                )
                actual_total += payload_size
                row = item.row
                records.append(
                    {
                        "path": item.relative_path,
                        "stable_id": row.stable_id.strip(),
                        "display_name": row.display_name.strip(),
                        "format": row.extension.casefold().removeprefix("."),
                        "predicted_payload_bytes": row.predicted_payload_bytes,
                        "payload_bytes": payload_size,
                        "sha256": payload_sha256,
                        "content_origin": row.content_origin,
                        "metadata": item.metadata,
                    }
                )
                report(completed, len(prepared))
            playlist_record_count = _write_playlist(archive, name, records)
            _write_manifest(
                archive,
                {
                    "schema": AUDIO_BUNDLE_SCHEMA,
                    "artifact_kind": "local_audio_collection",
                    "bundle_name": name,
                    "record_count": len(records),
                    "predicted_payload_bytes": predicted_total,
                    "payload_bytes": actual_total,
                    "shareable_project": False,
                    "contains_retail_derived": any(
                        row["content_origin"] == "retail_derived"
                        for row in records
                    ),
                    "contains_user_replacements": any(
                        row["content_origin"] == "user_replacement"
                        for row in records
                    ),
                    "playlist": (
                        "playlist.m3u8" if playlist_record_count else None
                    ),
                    "playlist_record_count": playlist_record_count,
                    "records": records,
                    "note": (
                        "Local export from the user's own game and edits. "
                        "Retail-derived payloads must not be redistributed; this "
                        "ZIP is not a shareable 2K5 Mod Studio project."
                    ),
                },
            )
        os.chmod(archive_path, 0o644)
        # The finished archive's identity, captured before the flush+publish so the
        # publisher can prove os.link targets exactly the inode we wrote and not a
        # reparse point swapped in afterwards.  Windows only: it has no O_NOFOLLOW,
        # so an identity compare is the refusal (see _exclusive_publish); POSIX
        # keeps its byte-identical publish, protected by fsync_path's O_NOFOLLOW
        # open and the 0o700 private temporary directory.
        written_identity = (
            _regular_file_identity(archive_path)
            if platform_compat.IS_WINDOWS
            else None
        )
        # Get the finished ZIP onto stable storage before it is published.  The
        # helper keeps the POSIX ``O_RDONLY | O_NOFOLLOW`` open this replaced and
        # switches only Windows to a writable handle, which is the sole access
        # mode ``FlushFileBuffers`` accepts there.
        fsync_path(archive_path, follow_symlinks=False)
        return _exclusive_publish(
            archive_path, target, expected_identity=written_identity
        )
