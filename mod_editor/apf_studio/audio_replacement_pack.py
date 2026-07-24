"""Retail-free batch authoring packs for APF exact-slot XMA1 audio.

The template deliberately contains no source audio and no source-owned sound
names.  It records only stable semantic coordinates, bounded slot shape,
alias ownership, and the hash of the source selected by the user.  A modder
adds independently encoded, one-stream RIFF XMA1 files to the generated
``xma1`` folder, then imports the complete folder or ZIP through
:class:`ApfSession`.

This module owns filesystem publication and manifest validation.  The session
continues to own packet validation, complete decode verification, cross-family
retail-packet rejection, private replacement storage, and the one-action Undo
boundary.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Iterable, Iterator, Mapping
from uuid import uuid4
import zipfile
import zlib

from mod_editor.core import platform_compat

from .audio_encoding import (
    MAX_WAV_OVERHEAD_BYTES,
    AudioEncodingError,
    Pcm16Target,
    validate_pcm16_target,
)
from .inspectors import ExportIdentity, InspectorRow
from .models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    Modification,
)


MANIFEST_SCHEMA = "apf2k8_mod_studio_audio_replacement_pack/v1"
PCM_MANIFEST_SCHEMA = "apf2k8_mod_studio_audio_replacement_pack/v2"
BASELINE_SCHEMA = "apf2k8_mod_studio_audio_target_baseline/v1"
MANIFEST_FILENAME = "replacement-pack.json"
README_FILENAME = "README.md"
PAYLOAD_DIRECTORY = "xma1"
PCM_PAYLOAD_DIRECTORY = "pcm16"
GAME_ID = "apf2k8_xbox360"
MAX_PACK_ENTRIES = 2_261 + 45_514
MAX_PCM_PACK_SUPPLIED = 256
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_PAYLOAD_FILES = MAX_PACK_ENTRIES
MAX_ARCHIVE_MEMBERS = MAX_PACK_ENTRIES + 3
MAX_EXPANDED_PACK_BYTES = 64 * 1024 * 1024 * 1024
TEMPLATE_PAYLOADS_INCLUDED = False
_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)

INPUT_CONTRACT: Mapping[str, object] = {
    "container": "RIFF",
    "codec": "XMA1",
    "stream_count": 1,
    "filename_extension": ".xma",
    "wav_flac_input_supported": False,
}

PCM_INPUT_CONTRACT: Mapping[str, object] = {
    "container": "RIFF",
    "codec": "PCM",
    "bits_per_sample": 16,
    "byte_order": "little_endian",
    "stream_count": 1,
    "filename_extension": ".wav",
    "shape": "exact_target",
    "encoder": "user_configured_external_xma1",
}

_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "game",
        "source",
        "payloads_included",
        "input_contract",
        "project_baseline",
        "entry_count",
        "entries",
    }
)
_ENTRY_KEYS = frozenset(
    {"asset_id", "kind", "replacement_file", "target", "baseline"}
)
_PROJECT_BASELINE_KEYS = frozenset({"schema", "target_count", "sha256"})
_ENTRY_BASELINE_KEYS = frozenset({"schema", "owners"})
_ORIGINAL_BASELINE_STATE_KEYS = frozenset({"asset_id", "state"})
_MODIFIED_BASELINE_STATE_KEYS = frozenset(
    {"asset_id", "state", "kind", "replacement_sha256"}
)
_AUDO_TARGET_KEYS = frozenset(
    {
        "outer_table_index",
        "inner_file_index",
        "encoded_size",
        "sample_rate",
        "channel_count",
        "declared_sample_count",
        "packet_count",
        "writer_schema",
    }
)
_AUSB_TARGET_KEYS = frozenset(
    {
        "outer_table_index",
        "inner_file_index",
        "substream_index",
        "encoded_size",
        "sample_rate",
        "channel_count",
        "declared_sample_count",
        "packet_count",
        "shared_owner_asset_ids",
        "owner_fingerprint",
        "writer_schema",
    }
)

_README = """# APF 2K8 audio replacement pack

This folder or ZIP is a retail-free authoring template. It contains no original
game audio and no decoded source sound names.

1. Open `replacement-pack.json` to see each exact target and filename.
2. Put a pre-encoded, one-stream RIFF XMA1 file at any listed path under
   `xma1/`. Leave targets you do not want to change absent.
3. In APF 2K8 Mod Studio, choose **Import replacement ZIP** or **Import
   replacement folder**, then select this pack.

Every supplied file must exactly match its target's channels, sample rate,
packet allocation, and decoded duration. This batch importer accepts finished
XMA1 only, not WAV, FLAC, MP3, WMA, xWMA, or XMA2. For one exact-shape PCM16
WAV, use the selected sound's **Replace from PCM WAV…** action with a separately
installed external encoder; batch PCM and FLAC/MP3 remain unsupported.

Import validates the whole manifest and every supplied file before changing
the project. All real changes become one Undo action. Do not add unlisted files
to this pack or `xma1/`; unknown files are rejected instead of guessed.
"""

# Alpha 25 exported this exact folder guide. Keep accepting it so adding ZIP
# hand-off does not invalidate a modder's already-authored folder.
_LEGACY_FOLDER_README = """# APF 2K8 audio replacement pack

This folder is a retail-free authoring template. It contains no original game
audio and no decoded source sound names.

1. Open `replacement-pack.json` to see each exact target and filename.
2. Put a pre-encoded, one-stream RIFF XMA1 file at any listed path under
   `xma1/`. Leave targets you do not want to change absent.
3. In APF 2K8 Mod Studio, choose **Import replacement folder** and select this
   folder.

Every supplied file must exactly match its target's channels, sample rate,
packet allocation, and decoded duration. Ordinary WAV, FLAC, MP3, WMA, xWMA,
and XMA2 files are not accepted. Friendly WAV/FLAC input still requires a
distributable XMA1 encoder.

Import validates the whole manifest and every supplied file before changing
the project. All real changes become one Undo action. Do not add unlisted files
to this folder or `xma1/`; unknown files are rejected instead of guessed.
"""
_ACCEPTED_README_BYTES = frozenset(
    {_README.encode("utf-8"), _LEGACY_FOLDER_README.encode("utf-8")}
)

_PCM_README = """# APF 2K8 PCM16 audio replacement pack

This folder or ZIP is a retail-free authoring template. It contains no original
game audio, decoded source sound names, encoder binary, or rollback bytes.

1. Open `replacement-pack.json` to see each exact target and filename.
2. Put an independently authored, exact-shape PCM16 RIFF WAV at any listed path
   under `pcm16/`. Leave targets you do not want to change absent.
3. In APF 2K8 Mod Studio, configure your separately installed XMA1 encoder,
   choose **Import replacement ZIP** or **Import replacement folder**, and
   select this pack.

Every supplied WAV must exactly match its target's channels, sample rate, and
PCM frame count. Import accepts at most 256 supplied WAVs in one transaction.
The app privately encodes every supplied WAV, then runs the normal exact XMA1
allocation, packet, complete-decode, source-reuse, target, and alias checks.

Import validates and encodes the complete supplied set before changing the
project. All real changes become one Undo action. Do not add unlisted files to
this pack or `pcm16/`; unknown files are rejected instead of guessed. FLAC,
MP3, WMA, xWMA, XMA1, and XMA2 files are not accepted by this PCM pack.
"""
_PCM_README_BYTES = _PCM_README.encode("utf-8")


class AudioReplacementPackError(ValueError):
    """A template or import folder violates the modder-facing contract."""


def _normalize_input_kind(value: object) -> str:
    if value not in {"xma1", "pcm16"}:
        raise AudioReplacementPackError(
            "Audio replacement-pack input must be xma1 or pcm16"
        )
    return str(value)


def _schema_for_input_kind(input_kind: str) -> str:
    return PCM_MANIFEST_SCHEMA if input_kind == "pcm16" else MANIFEST_SCHEMA


def _payload_directory_for_input_kind(input_kind: str) -> str:
    return PCM_PAYLOAD_DIRECTORY if input_kind == "pcm16" else PAYLOAD_DIRECTORY


def _input_contract_for_input_kind(input_kind: str) -> Mapping[str, object]:
    return PCM_INPUT_CONTRACT if input_kind == "pcm16" else INPUT_CONTRACT


def _readme_bytes_for_input_kind(input_kind: str) -> bytes:
    return _PCM_README_BYTES if input_kind == "pcm16" else _README.encode("utf-8")


@dataclass(frozen=True)
class AudioTargetBaselineState:
    asset_id: str
    state: str
    kind: str | None = None
    replacement_sha256: str | None = None


@dataclass(frozen=True)
class AudioReplacementEntry:
    asset_id: str
    kind: str
    identity: ExportIdentity
    replacement_file: PurePosixPath
    target: Mapping[str, object]
    baseline: tuple[AudioTargetBaselineState, ...] = ()


@dataclass(frozen=True)
class AudioReplacementDirectoryIdentity:
    device: int
    inode: int
    modified_ns: int
    changed_ns: int
    link_count: int


@dataclass(frozen=True)
class AudioReplacementFileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    content_sha256: str | None = None


@dataclass(frozen=True)
class SuppliedAudioReplacement:
    entry: AudioReplacementEntry
    path: Path
    file_identity: AudioReplacementFileIdentity | None = None


@dataclass(frozen=True)
class AudioReplacementTemplateReceipt:
    path: Path
    entry_count: int
    manifest_sha256: str
    payload_count: int = 0
    container: str = "folder"
    input_kind: str = "xma1"


@dataclass(frozen=True)
class AudioReplacementPackPlan:
    root: Path
    source_sha256: str
    template_entry_count: int
    supplied: tuple[SuppliedAudioReplacement, ...]
    missing_count: int
    manifest_sha256: str
    baseline_sha256: str
    root_identity: AudioReplacementDirectoryIdentity | None = None
    payload_directory_identity: AudioReplacementDirectoryIdentity | None = None
    reported_root: Path | None = None
    input_kind: str = "xma1"


@dataclass(frozen=True)
class AudioReplacementApplyProgress:
    """One between-file progress checkpoint for an atomic pack import."""

    stage: str
    completed: int
    total: int
    asset_id: str | None = None


@dataclass(frozen=True)
class AudioReplacementApplyReceipt:
    root: Path
    template_entry_count: int
    supplied_count: int
    staged_count: int
    unchanged_count: int
    missing_count: int
    undo_action_count: int
    validated_count: int = 0
    was_cancelled: bool = False
    input_kind: str = "xma1"


@dataclass(frozen=True)
class AudioReplacementPreviewReceipt:
    """Sanitized, read-only result shown before an audio pack can be applied."""

    root: Path
    template_entry_count: int
    supplied_count: int
    would_change_count: int
    already_current_count: int
    missing_count: int
    current_modified_audio_count: int
    resulting_modified_audio_count: int
    validated_count: int
    confirmation_token: str = field(repr=False)
    was_cancelled: bool = False
    input_kind: str = "xma1"


def _sha256_hex(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AudioReplacementPackError(f"{label} must be a SHA-256 string")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise AudioReplacementPackError(f"{label} must be a 64-digit SHA-256")
    return normalized


def _expected_modification_kind(entry: AudioReplacementEntry) -> str:
    return (
        AUDO_EXACT_SLOT_KIND
        if entry.kind == "audo"
        else AUSB_EXACT_SLOT_KIND
    )


def _baseline_owner_ids(entry: AudioReplacementEntry) -> tuple[str, ...]:
    if entry.kind == "audo":
        return (entry.asset_id,)
    raw = entry.target.get("shared_owner_asset_ids")
    if not isinstance(raw, list):
        raise AudioReplacementPackError(
            f"AUSB alias ownership is missing: {entry.asset_id}"
        )
    owners = tuple(str(value) for value in raw)
    if (
        not owners
        or tuple(sorted(owners)) != owners
        or len(set(owners)) != len(owners)
        or entry.asset_id not in owners
    ):
        raise AudioReplacementPackError(
            f"AUSB alias ownership is malformed: {entry.asset_id}"
        )
    return owners


def _validate_active_audio_modification(
    entry: AudioReplacementEntry,
    owner_asset_id: str,
    modification: Modification,
) -> None:
    expected_kind = _expected_modification_kind(entry)
    if modification.asset_id != owner_asset_id or modification.kind != expected_kind:
        raise AudioReplacementPackError(
            f"The active edit type changed for audio target {owner_asset_id}"
        )
    _sha256_hex(
        modification.replacement_sha256,
        f"Active audio replacement {owner_asset_id}",
    )
    metadata = dict(modification.metadata)
    if entry.kind == "audo":
        if metadata != dict(entry.target):
            raise AudioReplacementPackError(
                f"The active audio target shape changed: {owner_asset_id}"
            )
        return
    owners = list(_baseline_owner_ids(entry))
    fields = owner_asset_id.split(":")
    try:
        outer, inner, substream = map(int, fields[3:])
    except (TypeError, ValueError) as exc:
        raise AudioReplacementPackError(
            f"The active AUSB alias identity is malformed: {owner_asset_id}"
        ) from exc
    common_fields = {
        "encoded_size",
        "sample_rate",
        "channel_count",
        "declared_sample_count",
        "packet_count",
        "shared_owner_asset_ids",
        "owner_fingerprint",
        "writer_schema",
    }
    if (
        len(fields) != 6
        or fields[:3] != ["apf", "audio", "ausb"]
        or metadata.get("outer_table_index") != outer
        or metadata.get("inner_file_index") != inner
        or metadata.get("substream_index") != substream
        or any(metadata.get(name) != entry.target.get(name) for name in common_fields)
        or metadata.get("shared_owner_asset_ids") != owners
    ):
        raise AudioReplacementPackError(
            f"The active AUSB alias target shape changed: {owner_asset_id}"
        )


def current_audio_target_baseline(
    entry: AudioReplacementEntry,
    modifications: Mapping[str, Modification],
) -> tuple[AudioTargetBaselineState, ...]:
    """Return the canonical replacement-only state for one affected sound.

    Only the selected target and its disclosed physical aliases participate.
    Unrelated project edits deliberately do not broaden this optimistic-lock
    boundary.
    """

    states: list[AudioTargetBaselineState] = []
    for owner_asset_id in _baseline_owner_ids(entry):
        modification = modifications.get(owner_asset_id)
        if modification is None:
            states.append(AudioTargetBaselineState(owner_asset_id, "original"))
            continue
        _validate_active_audio_modification(entry, owner_asset_id, modification)
        states.append(
            AudioTargetBaselineState(
                owner_asset_id,
                "modified",
                modification.kind,
                _sha256_hex(
                    modification.replacement_sha256,
                    f"Active audio replacement {owner_asset_id}",
                ),
            )
        )
    return tuple(states)


def _baseline_state_document(
    state: AudioTargetBaselineState,
) -> dict[str, object]:
    if state.state == "original":
        if state.kind is not None or state.replacement_sha256 is not None:
            raise AudioReplacementPackError(
                f"Original baseline state carries replacement data: {state.asset_id}"
            )
        return {"asset_id": state.asset_id, "state": "original"}
    if state.state != "modified" or state.kind not in {
        AUDO_EXACT_SLOT_KIND,
        AUSB_EXACT_SLOT_KIND,
    }:
        raise AudioReplacementPackError(
            f"Audio baseline state is invalid: {state.asset_id}"
        )
    digest = _sha256_hex(
        state.replacement_sha256,
        f"Audio baseline replacement {state.asset_id}",
    )
    return {
        "asset_id": state.asset_id,
        "state": "modified",
        "kind": state.kind,
        "replacement_sha256": digest,
    }


def _entry_baseline_document(entry: AudioReplacementEntry) -> dict[str, object]:
    if not entry.baseline:
        raise AudioReplacementPackError(
            f"Audio replacement entry has no project baseline: {entry.asset_id}"
        )
    return {
        "schema": BASELINE_SCHEMA,
        "owners": [_baseline_state_document(state) for state in entry.baseline],
    }


def _project_baseline_sha256(entries: Iterable[AudioReplacementEntry]) -> str:
    rows = [
        {
            "asset_id": entry.asset_id,
            "baseline": _entry_baseline_document(entry),
        }
        for entry in entries
    ]
    data = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _exact_int(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 1_000_000_000,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AudioReplacementPackError(
            f"{label} must be an integer from {minimum:,} through {maximum:,}"
        )
    return value


def _identity_asset_id(identity: ExportIdentity) -> str:
    outer = _exact_int(
        identity.outer_table_index,
        "Audio outer-table index",
        maximum=1_542,
    )
    inner = _exact_int(
        identity.inner_file_index,
        "Audio inner-file index",
        maximum=99_999,
    )
    if identity.kind == "audo":
        if identity.substream_index is not None:
            raise AudioReplacementPackError(
                "A standalone AUDO target unexpectedly has a substream index"
            )
        return f"apf:audio:audo:{outer}:{inner}"
    if identity.kind == "ausb_substream":
        substream = _exact_int(
            identity.substream_index,
            "AUSB substream index",
            maximum=99_999,
        )
        return f"apf:audio:ausb:{outer}:{inner}:{substream}"
    raise AudioReplacementPackError(
        "Replacement templates support individual AUDO and AUSB sound rows only"
    )


def _replacement_path(
    identity: ExportIdentity,
    input_kind: str = "xma1",
) -> PurePosixPath:
    input_kind = _normalize_input_kind(input_kind)
    outer = int(identity.outer_table_index)
    inner = int(identity.inner_file_index)
    suffix = ".wav" if input_kind == "pcm16" else ".xma"
    if identity.kind == "audo":
        name = f"audo-o{outer:05d}-i{inner:05d}{suffix}"
    else:
        assert identity.substream_index is not None
        name = (
            f"ausb-o{outer:05d}-i{inner:05d}-"
            f"s{identity.substream_index:05d}{suffix}"
        )
    return PurePosixPath(_payload_directory_for_input_kind(input_kind), name)


def _row_integer(
    row: InspectorRow,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    return _exact_int(
        row.fields.get(name),
        f"{row.row_id} {name}",
        minimum=minimum,
        maximum=maximum,
    )


def _entry_from_row(
    row: InspectorRow,
    input_kind: str = "xma1",
) -> AudioReplacementEntry:
    input_kind = _normalize_input_kind(input_kind)
    identity = row.export_identity
    if identity is None:
        raise AudioReplacementPackError(
            f"{row.row_id} is an index or physical bank, not one editable sound"
        )
    asset_id = _identity_asset_id(identity)
    expected_kind = "audo" if identity.kind == "audo" else "ausb_substream"
    if row.kind != expected_kind or row.row_id != asset_id:
        raise AudioReplacementPackError(
            f"Audio row identity changed or is not an exact-slot target: {row.row_id}"
        )
    if (
        row.fields.get("outer_table_index") != identity.outer_table_index
        or row.fields.get("inner_file_index") != identity.inner_file_index
        or row.fields.get("substream_index") != identity.substream_index
    ):
        raise AudioReplacementPackError(
            f"Audio row coordinates disagree with its export identity: {asset_id}"
        )

    encoded_field = "encoded_size" if identity.kind == "audo" else "range_length"
    encoded_size = _row_integer(
        row, encoded_field, minimum=0x800, maximum=24 * 1024 * 1024
    )
    if encoded_size % 0x800:
        raise AudioReplacementPackError(
            f"Audio target is no longer packet aligned: {asset_id}"
        )
    sample_rate = _row_integer(
        row, "sample_rate", minimum=8_000, maximum=192_000
    )
    channel_count = _row_integer(
        row,
        "derived_channel_count",
        minimum=1,
        maximum=8 if identity.kind == "audo" else 2,
    )
    declared_sample_count = _row_integer(
        row,
        "declared_sample_count",
        minimum=1,
        maximum=1_000_000_000,
    )
    packet_count = _row_integer(
        row, "packet_count", minimum=1, maximum=24 * 1024 * 1024 // 0x800
    )
    if packet_count != encoded_size // 0x800:
        raise AudioReplacementPackError(
            f"Audio target packet count changed: {asset_id}"
        )
    target: dict[str, object] = {
        "outer_table_index": identity.outer_table_index,
        "inner_file_index": identity.inner_file_index,
        "encoded_size": encoded_size,
        "sample_rate": sample_rate,
        "channel_count": channel_count,
        "declared_sample_count": declared_sample_count,
        "packet_count": packet_count,
        "writer_schema": AUDO_EXACT_SLOT_WRITER_SCHEMA,
    }
    if identity.kind == "ausb_substream":
        owners_value = row.fields.get("shared_owner_asset_ids")
        if not isinstance(owners_value, (tuple, list)):
            raise AudioReplacementPackError(
                f"AUSB alias ownership is missing: {asset_id}"
            )
        owners = [str(value) for value in owners_value]
        if (
            not 1 <= len(owners) <= 8
            or len(set(owners)) != len(owners)
            or owners != sorted(owners)
            or asset_id not in owners
            or any(
                not owner.startswith("apf:audio:ausb:")
                or len(owner.split(":")) != 6
                for owner in owners
            )
        ):
            raise AudioReplacementPackError(
                f"AUSB alias ownership changed or is malformed: {asset_id}"
            )
        target.update(
            {
                "substream_index": identity.substream_index,
                "shared_owner_asset_ids": owners,
                "owner_fingerprint": hashlib.sha256(
                    "\n".join(owners).encode("ascii")
                ).hexdigest(),
                "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
            }
        )
    return AudioReplacementEntry(
        asset_id=asset_id,
        kind=identity.kind,
        identity=identity,
        replacement_file=_replacement_path(identity, input_kind),
        target=target,
    )


def _entry_contract_document(entry: AudioReplacementEntry) -> dict[str, object]:
    return {
        "asset_id": entry.asset_id,
        "kind": entry.kind,
        "replacement_file": entry.replacement_file.as_posix(),
        "target": dict(entry.target),
    }


def _entry_document(entry: AudioReplacementEntry) -> dict[str, object]:
    return {
        **_entry_contract_document(entry),
        "baseline": _entry_baseline_document(entry),
    }


def _manifest_document(
    rows: Iterable[InspectorRow],
    source_sha256: str,
    active_modifications: Iterable[Modification],
    input_kind: str = "xma1",
) -> tuple[dict[str, object], tuple[AudioReplacementEntry, ...]]:
    input_kind = _normalize_input_kind(input_kind)
    source_digest = _sha256_hex(source_sha256, "Loaded source")
    selected = tuple(rows)
    if not 1 <= len(selected) <= MAX_PACK_ENTRIES:
        raise AudioReplacementPackError(
            f"Choose between 1 and {MAX_PACK_ENTRIES:,} individual sounds"
        )
    raw_modifications = tuple(active_modifications)
    modification_map = {
        modification.asset_id: modification for modification in raw_modifications
    }
    if len(modification_map) != len(raw_modifications):
        raise AudioReplacementPackError(
            "The active project repeats one modification identity"
        )
    entries = tuple(
        AudioReplacementEntry(
            asset_id=entry.asset_id,
            kind=entry.kind,
            identity=entry.identity,
            replacement_file=entry.replacement_file,
            target=entry.target,
            baseline=current_audio_target_baseline(entry, modification_map),
        )
        for entry in (_entry_from_row(row, input_kind) for row in selected)
    )
    asset_ids = [entry.asset_id for entry in entries]
    replacement_files = [entry.replacement_file for entry in entries]
    if len(set(asset_ids)) != len(asset_ids):
        raise AudioReplacementPackError(
            "The selected audio set contains a duplicate sound identity"
        )
    if len(set(replacement_files)) != len(replacement_files):
        raise AudioReplacementPackError(
            "Two selected sounds resolve to the same replacement filename"
        )
    baseline_sha256 = _project_baseline_sha256(entries)
    document: dict[str, object] = {
        "schema": _schema_for_input_kind(input_kind),
        "game": GAME_ID,
        "source": {"sha256": source_digest},
        "payloads_included": TEMPLATE_PAYLOADS_INCLUDED,
        "input_contract": dict(_input_contract_for_input_kind(input_kind)),
        "project_baseline": {
            "schema": BASELINE_SCHEMA,
            "target_count": len(entries),
            "sha256": baseline_sha256,
        },
        "entry_count": len(entries),
        "entries": [_entry_document(entry) for entry in entries],
    }
    return document, entries


def _absolute_destination(path: Path) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    result = Path(os.path.abspath(os.fspath(supplied)))
    if result.name in {"", ".", ".."}:
        raise AudioReplacementPackError(
            "Choose a named folder for the replacement template"
        )
    return result


def _directory_identity(info: os.stat_result) -> AudioReplacementDirectoryIdentity:
    return AudioReplacementDirectoryIdentity(
        info.st_dev,
        info.st_ino,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _file_identity(
    info: os.stat_result,
    content_sha256: str | None = None,
) -> AudioReplacementFileIdentity:
    return AudioReplacementFileIdentity(
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        modified_ns=info.st_mtime_ns,
        changed_ns=info.st_ctime_ns,
        content_sha256=content_sha256,
    )


def _file_stat_identity(
    identity: AudioReplacementFileIdentity,
) -> tuple[int, int, int, int, int]:
    return (
        identity.device,
        identity.inode,
        identity.size,
        identity.modified_ns,
        identity.changed_ns,
    )


def _private_staging_directory(prefix: str, label: str) -> Path:
    """Create one private scratch directory for game-derived audio, and verify it.

    ``mkdtemp`` is the right primitive on both platforms -- ``0o700`` on POSIX,
    and on Windows a directory under the per-user ``%TEMP%``, which has no mode
    bits at all.  What differs is what can be *checked* afterwards, so the check
    is delegated to :mod:`~mod_editor.core.platform_compat`: the unchanged
    owner-only ``0o700`` assertion on POSIX, and on Windows the strongest
    equivalent available -- a real, non-reparse-point directory.  A failure is
    fatal rather than a warning: decoded retail audio is about to be written
    here.
    """

    staging = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        platform_compat.verify_private_directory(staging, label)
    except platform_compat.PrivatePathError as exc:
        platform_compat.remove_private_tree(staging, ignore_errors=True)
        raise AudioReplacementPackError(str(exc)) from exc
    return staging


def _open_pinned_directory(
    path: Path,
    *,
    label: str,
) -> tuple[int, AudioReplacementDirectoryIdentity, os.stat_result]:
    """Open one directory and bind later work to that exact inode."""

    try:
        before = path.stat(follow_symlinks=False)
        descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS)
    except OSError as exc:
        raise AudioReplacementPackError(f"Could not open {label}: {exc}") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise AudioReplacementPackError(f"The {label} changed while it was opened")
    return descriptor, _directory_identity(opened), opened


def _open_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[int, AudioReplacementDirectoryIdentity, os.stat_result]:
    try:
        before = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        descriptor = os.open(
            name,
            _DIRECTORY_OPEN_FLAGS,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise AudioReplacementPackError(f"Could not open {label}: {exc}") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise AudioReplacementPackError(f"The {label} changed while it was opened")
    return descriptor, _directory_identity(opened), opened


def _path_still_names_directory(
    path: Path,
    identity: AudioReplacementDirectoryIdentity,
) -> bool:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and (info.st_dev, info.st_ino) == (identity.device, identity.inode)
    )


def _directory_name_has_identity_at(
    parent_descriptor: int,
    name: str,
    identity: AudioReplacementDirectoryIdentity,
) -> bool:
    try:
        info = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and (info.st_dev, info.st_ino) == (identity.device, identity.inode)
    )


def _file_name_is_owned_inode_at(
    parent_descriptor: int,
    name: str,
    identity: AudioReplacementFileIdentity,
) -> bool:
    """Return whether ``name`` is still the writer-created regular inode.

    This deliberately ignores mutable content metadata.  It is used only by
    failure cleanup, where an attacker may have changed the writer's inode but
    a substituted foreign race winner must never be unlinked.
    """

    try:
        info = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_nlink == 1
        and (info.st_dev, info.st_ino) == (identity.device, identity.inode)
    )


def _file_name_has_content_identity_at(
    parent_descriptor: int,
    name: str,
    identity: AudioReplacementFileIdentity,
    *,
    tolerate_rename_ctime: bool,
) -> bool:
    """Verify one pinned regular file's metadata and exact SHA-256 content."""

    expected_digest = identity.content_sha256
    if (
        not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or any(character not in "0123456789abcdef" for character in expected_digest)
    ):
        return False
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
    except OSError:
        return False
    try:
        before = os.fstat(descriptor)
        candidate = _file_identity(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_nlink != 1
        ):
            return False
        if tolerate_rename_ctime:
            if (
                candidate.device,
                candidate.inode,
                candidate.size,
                candidate.modified_ns,
            ) != (
                identity.device,
                identity.inode,
                identity.size,
                identity.modified_ns,
            ):
                return False
        elif _file_stat_identity(candidate) != _file_stat_identity(identity):
            return False
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        named_after = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _file_stat_identity(_file_identity(after))
            != _file_stat_identity(candidate)
            or _file_stat_identity(_file_identity(named_after))
            != _file_stat_identity(candidate)
            or named_after.st_nlink != 1
            or not stat.S_ISREG(named_after.st_mode)
            or stat.S_ISLNK(named_after.st_mode)
        ):
            return False
        return digest.hexdigest() == expected_digest
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _file_name_has_strict_content_identity_at(
    parent_descriptor: int,
    name: str,
    identity: AudioReplacementFileIdentity,
) -> bool:
    """Require unchanged ctime and content before publishing a staging ZIP."""

    return _file_name_has_content_identity_at(
        parent_descriptor,
        name,
        identity,
        tolerate_rename_ctime=False,
    )


def _file_name_has_published_content_identity_at(
    parent_descriptor: int,
    name: str,
    identity: AudioReplacementFileIdentity,
) -> bool:
    """Verify published bytes while allowing only rename's expected ctime change."""

    return _file_name_has_content_identity_at(
        parent_descriptor,
        name,
        identity,
        tolerate_rename_ctime=True,
    )


def _write_exclusive_at(directory_descriptor: int, name: str, data: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError(errno.EIO, "short write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _zip_file_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.flag_bits = 0x800
    return info


def _zip_directory_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(
        name.rstrip("/") + "/",
        date_time=(1980, 1, 1, 0, 0, 0),
    )
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFDIR | 0o700) << 16
    info.flag_bits = 0x800
    return info


def _clear_owned_template_directory(
    directory_descriptor: int,
    payload_directory: str = PAYLOAD_DIRECTORY,
) -> None:
    """Best-effort removal of only the three names this writer owns."""

    for name in (MANIFEST_FILENAME, README_FILENAME):
        try:
            os.unlink(name, dir_fd=directory_descriptor)
        except OSError:
            pass
    try:
        os.rmdir(payload_directory, dir_fd=directory_descriptor)
    except OSError:
        pass


def _publish_name_noreplace(
    parent_descriptor: int,
    staging_name: str,
    destination_name: str,
    *,
    object_label: str,
    is_directory: bool,
) -> None:
    """Atomically publish one complete name without replacing a race winner.

    Only the OS-primitive layer differs per platform, and it lives in
    :mod:`platform_compat`.  Linux keeps ``renameat2(RENAME_NOREPLACE)``
    byte-for-byte.  macOS and any POSIX kernel without it publish a file with
    ``os.link`` + unlink and a folder by reserving the name with ``os.mkdir``
    then ``os.rename`` -- both refuse an existing destination
    (``FileExistsError``).  Windows cannot open the directory descriptor this
    stages through, so it fails closed there with the historical message rather
    than a silent, clobbering path-based publish.
    """

    try:
        platform_compat.publish_no_replace(
            staging_name,
            destination_name,
            dir_fd=parent_descriptor,
            is_directory=is_directory,
        )
    except FileExistsError as exc:
        raise FileExistsError(destination_name) from exc
    except platform_compat.NoReplacePublishUnavailable as exc:
        raise AudioReplacementPackError(
            f"This system cannot publish a replacement-template {object_label} "
            "atomically"
        ) from exc


def _publish_directory_noreplace(
    parent_descriptor: int,
    staging_name: str,
    destination_name: str,
) -> None:
    """Atomically publish one complete folder without replacing a race winner."""

    _publish_name_noreplace(
        parent_descriptor,
        staging_name,
        destination_name,
        object_label="folder",
        is_directory=True,
    )


def _publish_file_noreplace(
    parent_descriptor: int,
    staging_name: str,
    destination_name: str,
) -> None:
    """Atomically publish one complete file without replacing a race winner."""

    _publish_name_noreplace(
        parent_descriptor,
        staging_name,
        destination_name,
        object_label="ZIP",
        is_directory=False,
    )


def _create_audio_replacement_zip_at(
    parent_descriptor: int,
    staging_name: str,
    *,
    manifest_data: bytes,
    payload_directory: str = PAYLOAD_DIRECTORY,
    readme_data: bytes | None = None,
) -> AudioReplacementFileIdentity:
    """Build and verify one deterministic metadata-only ZIP under a pinned parent."""

    if payload_directory not in {PAYLOAD_DIRECTORY, PCM_PAYLOAD_DIRECTORY}:
        raise AudioReplacementPackError("Unknown audio-template payload directory")
    selected_readme = _README.encode("utf-8") if readme_data is None else readme_data

    descriptor = os.open(
        staging_name,
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=parent_descriptor,
    )
    stream = os.fdopen(descriptor, "w+b", closefd=False)
    try:
        with zipfile.ZipFile(stream, "w", allowZip64=True) as archive:
            archive.writestr(_zip_file_info(MANIFEST_FILENAME), manifest_data)
            archive.writestr(_zip_file_info(README_FILENAME), selected_readme)
            archive.writestr(_zip_directory_info(payload_directory), b"")
        stream.flush()
        os.fsync(descriptor)
        stream.seek(0)
        with zipfile.ZipFile(stream, "r") as verify:
            if verify.namelist() != [
                MANIFEST_FILENAME,
                README_FILENAME,
                f"{payload_directory}/",
            ]:
                raise AudioReplacementPackError(
                    "The metadata-only audio template ZIP contains an unexpected member"
                )
            if (
                verify.read(MANIFEST_FILENAME) != manifest_data
                or verify.read(README_FILENAME) != selected_readme
                or verify.read(f"{payload_directory}/") != b""
            ):
                raise AudioReplacementPackError(
                    "The metadata-only audio template ZIP failed its read-back check"
                )
        before_hash = _file_identity(os.fstat(descriptor))
        stream.seek(0)
        digest = hashlib.sha256()
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
        final = os.fstat(descriptor)
        if (
            not stat.S_ISREG(final.st_mode)
            or stat.S_ISLNK(final.st_mode)
            or final.st_nlink != 1
            or _file_stat_identity(_file_identity(final))
            != _file_stat_identity(before_hash)
        ):
            raise AudioReplacementPackError(
                "The audio-template ZIP staging file changed while it was built"
            )
        return _file_identity(final, digest.hexdigest())
    except BaseException:
        try:
            failed_identity = _file_identity(os.fstat(descriptor))
        except OSError:
            failed_identity = None
        stream.close()
        os.close(descriptor)
        if failed_identity is not None and _file_name_is_owned_inode_at(
            parent_descriptor,
            staging_name,
            failed_identity,
        ):
            try:
                os.unlink(staging_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if not stream.closed:
            stream.close()
        try:
            os.close(descriptor)
        except OSError:
            pass


def create_audio_replacement_template(
    rows: Iterable[InspectorRow],
    destination: Path,
    *,
    source_sha256: str,
    active_modifications: Iterable[Modification],
    container: str | None = None,
    input_kind: str = "xma1",
) -> AudioReplacementTemplateReceipt:
    """Publish one new metadata-only authoring folder or deterministic ZIP.

    The destination is never overwritten.  Everything is assembled beside it
    first so a generation failure cannot publish a half-written manifest.
    """

    input_kind = _normalize_input_kind(input_kind)
    payload_directory = _payload_directory_for_input_kind(input_kind)
    readme_data = _readme_bytes_for_input_kind(input_kind)
    document, entries = _manifest_document(
        rows,
        source_sha256,
        active_modifications,
        input_kind,
    )
    manifest_data = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    if len(manifest_data) > MAX_MANIFEST_BYTES:
        raise AudioReplacementPackError(
            "The replacement template manifest is unexpectedly large"
        )
    target = _absolute_destination(destination)
    normalized_container = (
        container.strip().casefold()
        if isinstance(container, str)
        else ("zip" if target.suffix.casefold() == ".zip" else "folder")
    )
    if normalized_container not in {"folder", "zip"}:
        raise AudioReplacementPackError(
            "Audio replacement-template format must be folder or ZIP"
        )
    if normalized_container == "zip" and target.suffix.casefold() != ".zip":
        raise AudioReplacementPackError(
            "ZIP audio templates need a filename ending in .zip"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    parent_descriptor, parent_identity, _parent_info = _open_pinned_directory(
        target.parent,
        label="replacement-template parent",
    )
    staging_name = f".apf-audio-{uuid4().hex}.tmp"
    if normalized_container == "zip":
        staging_identity: AudioReplacementFileIdentity | None = None
        try:
            try:
                os.stat(target.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError(target)
            if input_kind == "xma1":
                # Preserve the exact Alpha.26 v1 call and deterministic archive.
                staging_identity = _create_audio_replacement_zip_at(
                    parent_descriptor,
                    staging_name,
                    manifest_data=manifest_data,
                )
            else:
                staging_identity = _create_audio_replacement_zip_at(
                    parent_descriptor,
                    staging_name,
                    manifest_data=manifest_data,
                    payload_directory=payload_directory,
                    readme_data=readme_data,
                )
            if not _path_still_names_directory(target.parent, parent_identity):
                raise AudioReplacementPackError(
                    "The replacement-template parent changed before publication"
                )
            if not _file_name_has_strict_content_identity_at(
                parent_descriptor,
                staging_name,
                staging_identity,
            ):
                raise AudioReplacementPackError(
                    "The audio-template ZIP staging file changed before publication"
                )
            _publish_file_noreplace(
                parent_descriptor,
                staging_name,
                target.name,
            )
            if not _file_name_has_published_content_identity_at(
                parent_descriptor,
                target.name,
                staging_identity,
            ):
                raise AudioReplacementPackError(
                    "The audio-template ZIP changed during publication"
                )
            # Commit the publish through the directory descriptor this
            # transaction pinned, never by re-opening the directory by name.
            # POSIX issues the same single fsync as before; Windows has no
            # directory-flush primitive and the helper reports that rather than
            # letting a skipped flush read as a completed one.
            platform_compat.fsync_directory_fd(parent_descriptor)
            if not _path_still_names_directory(target.parent, parent_identity):
                raise AudioReplacementPackError(
                    "The replacement-template parent changed during publication"
                )
            if not _file_name_has_published_content_identity_at(
                parent_descriptor,
                target.name,
                staging_identity,
            ):
                raise AudioReplacementPackError(
                    "The audio-template ZIP changed before publication completed"
                )
        except BaseException:
            if staging_identity is not None:
                for candidate_name in (staging_name, target.name):
                    if not _file_name_is_owned_inode_at(
                        parent_descriptor,
                        candidate_name,
                        staging_identity,
                    ):
                        continue
                    try:
                        os.unlink(candidate_name, dir_fd=parent_descriptor)
                    except OSError:
                        pass
            raise
        finally:
            os.close(parent_descriptor)
        return AudioReplacementTemplateReceipt(
            path=target,
            entry_count=len(entries),
            manifest_sha256=hashlib.sha256(manifest_data).hexdigest(),
            container="zip",
            input_kind=input_kind,
        )

    staging_descriptor: int | None = None
    staging_identity: AudioReplacementDirectoryIdentity | None = None
    try:
        try:
            os.stat(target.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(target)
        os.mkdir(staging_name, mode=0o700, dir_fd=parent_descriptor)
        staging_descriptor, staging_identity, _info = _open_directory_at(
            parent_descriptor,
            staging_name,
            label="private replacement-template staging folder",
        )
        os.mkdir(payload_directory, mode=0o700, dir_fd=staging_descriptor)
        payload_descriptor, _payload_identity, _payload_info = _open_directory_at(
            staging_descriptor,
            payload_directory,
            label="private replacement-template payload folder",
        )
        try:
            platform_compat.fsync_directory_fd(payload_descriptor)
        finally:
            os.close(payload_descriptor)
        _write_exclusive_at(staging_descriptor, MANIFEST_FILENAME, manifest_data)
        _write_exclusive_at(
            staging_descriptor,
            README_FILENAME,
            readme_data,
        )
        platform_compat.fsync_directory_fd(staging_descriptor)
        if not _path_still_names_directory(target.parent, parent_identity):
            raise AudioReplacementPackError(
                "The replacement-template parent changed before publication"
            )
        if not _directory_name_has_identity_at(
            parent_descriptor,
            staging_name,
            staging_identity,
        ):
            raise AudioReplacementPackError(
                "The replacement-template staging folder changed before publication"
            )
        _publish_directory_noreplace(
            parent_descriptor,
            staging_name,
            target.name,
        )
        if not _directory_name_has_identity_at(
            parent_descriptor,
            target.name,
            staging_identity,
        ):
            raise AudioReplacementPackError(
                "The replacement-template staging folder changed during publication"
            )
        platform_compat.fsync_directory_fd(parent_descriptor)
        if not _path_still_names_directory(target.parent, parent_identity):
            raise AudioReplacementPackError(
                "The replacement-template parent changed during publication"
            )
    except BaseException:
        if staging_descriptor is not None:
            _clear_owned_template_directory(staging_descriptor, payload_directory)
        if staging_identity is not None:
            for candidate_name in (staging_name, target.name):
                if not _directory_name_has_identity_at(
                    parent_descriptor,
                    candidate_name,
                    staging_identity,
                ):
                    continue
                try:
                    os.rmdir(candidate_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
        raise
    finally:
        if staging_descriptor is not None:
            os.close(staging_descriptor)
        os.close(parent_descriptor)
    return AudioReplacementTemplateReceipt(
        path=target,
        entry_count=len(entries),
        manifest_sha256=hashlib.sha256(manifest_data).hexdigest(),
        container="folder",
        input_kind=input_kind,
    )


def _read_regular_bounded_at(
    directory_descriptor: int,
    name: str,
    *,
    maximum: int,
    label: str,
    expected_identity: AudioReplacementFileIdentity | None = None,
) -> bytes:
    """Read one dirfd-relative private file through one stable descriptor."""

    try:
        before = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise AudioReplacementPackError(f"Could not open {label}: {exc}") from exc
    identity = _file_identity(before)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= maximum
        or (
            expected_identity is not None
            and _file_stat_identity(identity)
            != _file_stat_identity(expected_identity)
        )
    ):
        raise AudioReplacementPackError(
            f"The {label} changed, exceeds its size limit, or is not one private regular file"
        )
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if (
            _file_identity(opened) != identity
            or opened.st_nlink != 1
            or not stat.S_ISREG(opened.st_mode)
        ):
            raise AudioReplacementPackError(f"The {label} changed while it was opened")
        blocks: list[bytes] = []
        total = 0
        while True:
            block = os.read(
                descriptor,
                min(1024 * 1024, maximum + 1 - total),
            )
            if not block:
                break
            blocks.append(block)
            total += len(block)
            if total > maximum:
                raise AudioReplacementPackError(
                    f"The {label} grew beyond its size limit while it was read"
                )
        after = os.fstat(descriptor)
        if (
            _file_identity(after) != identity
            or after.st_nlink != 1
            or total != identity.size
        ):
            raise AudioReplacementPackError(f"The {label} changed while it was read")
        data = b"".join(blocks)
        if (
            expected_identity is not None
            and expected_identity.content_sha256 is not None
            and hashlib.sha256(data).hexdigest()
            != expected_identity.content_sha256
        ):
            raise AudioReplacementPackError(
                f"The {label} content changed after validation"
            )
        return data
    finally:
        os.close(descriptor)


def _stream_regular_bounded_at(
    directory_descriptor: int,
    name: str,
    *,
    maximum: int,
    label: str,
    expected_identity: AudioReplacementFileIdentity | None = None,
    destination: Path | None = None,
) -> AudioReplacementFileIdentity:
    """Hash or privately copy one pinned file without loading it into memory."""

    try:
        before = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise AudioReplacementPackError(f"Could not open {label}: {exc}") from exc
    identity = _file_identity(before)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= maximum
        or (
            expected_identity is not None
            and _file_stat_identity(identity)
            != _file_stat_identity(expected_identity)
        )
    ):
        raise AudioReplacementPackError(
            f"The {label} changed, exceeds its size limit, or is not one private regular file"
        )
    source_descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_descriptor,
    )
    destination_descriptor: int | None = None
    published_destination = False
    try:
        opened = os.fstat(source_descriptor)
        if _file_identity(opened) != identity:
            raise AudioReplacementPackError(f"The {label} changed while it was opened")
        if destination is not None:
            destination_descriptor = os.open(
                destination,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
            published_destination = True
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(
                source_descriptor,
                min(1024 * 1024, maximum + 1 - total),
            )
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise AudioReplacementPackError(
                    f"The {label} grew beyond its size limit while it was read"
                )
            digest.update(block)
            if destination_descriptor is not None:
                view = memoryview(block)
                written = 0
                while written < len(view):
                    count = os.write(destination_descriptor, view[written:])
                    if count <= 0:
                        raise OSError(errno.EIO, "short write")
                    written += count
        after = os.fstat(source_descriptor)
        content_sha256 = digest.hexdigest()
        if (
            _file_identity(after) != identity
            or after.st_nlink != 1
            or total != identity.size
            or (
                expected_identity is not None
                and expected_identity.content_sha256 is not None
                and content_sha256 != expected_identity.content_sha256
            )
        ):
            raise AudioReplacementPackError(f"The {label} changed while it was read")
        if destination_descriptor is not None:
            os.fsync(destination_descriptor)
        return _file_identity(after, content_sha256)
    except BaseException:
        if published_destination and destination is not None:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        os.close(source_descriptor)


def _directory_unchanged(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    )


def _safe_replacement_path(
    value: object,
    input_kind: str = "xma1",
) -> PurePosixPath:
    input_kind = _normalize_input_kind(input_kind)
    if not isinstance(value, str) or not value:
        raise AudioReplacementPackError(
            "Every audio replacement entry needs a filename"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) != 2
        or path.parts[0] != _payload_directory_for_input_kind(input_kind)
        or path.parts[1] in {"", ".", ".."}
        or path.suffix != (".wav" if input_kind == "pcm16" else ".xma")
        or "\\" in value
    ):
        raise AudioReplacementPackError(
            "Replacement filename must be a generated "
            f"{_payload_directory_for_input_kind(input_kind)}/*"
            f"{'.wav' if input_kind == 'pcm16' else '.xma'} path: {value}"
        )
    return path


def _safe_zip_member_name(value: object, *, directory: bool = False) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
    ):
        raise AudioReplacementPackError(
            "The audio replacement ZIP contains an unsafe path"
        )
    normalized = value.rstrip("/") if directory else value
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or normalized != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (directory and not value.endswith("/"))
        or (not directory and value.endswith("/"))
    ):
        raise AudioReplacementPackError(
            f"The audio replacement ZIP path escapes the pack: {value}"
        )
    return normalized


def _path_still_names_file(
    path: Path,
    identity: AudioReplacementFileIdentity,
) -> bool:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_nlink == 1
        and _file_stat_identity(_file_identity(info))
        == _file_stat_identity(identity)
    )


def _read_zip_member(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    *,
    maximum: int,
    label: str,
) -> bytes:
    if not 0 < member.file_size <= maximum:
        raise AudioReplacementPackError(
            f"The {label} is empty or exceeds its size limit"
        )
    try:
        with archive.open(member, "r") as source:
            chunks: list[bytes] = []
            total = 0
            while True:
                block = source.read(min(1024 * 1024, maximum + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > maximum:
                    raise AudioReplacementPackError(
                        f"The {label} expands beyond its size limit"
                    )
    except AudioReplacementPackError:
        raise
    except (
        OSError,
        EOFError,
        RuntimeError,
        zipfile.BadZipFile,
        zlib.error,
    ) as exc:
        raise AudioReplacementPackError(
            f"Could not read audio replacement ZIP member {member.filename}: {exc}"
        ) from exc
    data = b"".join(chunks)
    if len(data) != member.file_size:
        raise AudioReplacementPackError(
            f"The audio replacement ZIP member size changed: {member.filename}"
        )
    return data


def _extract_zip_member_at(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    directory_descriptor: int,
    name: str,
    *,
    maximum: int,
) -> None:
    """Stream one bounded member to one exclusive private regular file."""

    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        try:
            with archive.open(member, "r") as source:
                total = 0
                while True:
                    block = source.read(min(1024 * 1024, maximum + 1 - total))
                    if not block:
                        break
                    total += len(block)
                    if total > maximum:
                        raise AudioReplacementPackError(
                            "The audio replacement ZIP member expands beyond its "
                            f"target limit: {member.filename}"
                        )
                    view = memoryview(block)
                    written = 0
                    while written < len(view):
                        count = os.write(descriptor, view[written:])
                        if count <= 0:
                            raise OSError(errno.EIO, "short write")
                        written += count
        except AudioReplacementPackError:
            raise
        except (
            OSError,
            EOFError,
            RuntimeError,
            zipfile.BadZipFile,
            zlib.error,
        ) as exc:
            raise AudioReplacementPackError(
                f"Could not read audio replacement ZIP member {member.filename}: {exc}"
            ) from exc
        if total != member.file_size:
            raise AudioReplacementPackError(
                f"The audio replacement ZIP member size changed: {member.filename}"
            )
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            os.unlink(name, dir_fd=directory_descriptor)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)


def _manifest_input_kind(document: Mapping[str, object]) -> str:
    schema = document.get("schema")
    contract = document.get("input_contract")
    if schema == MANIFEST_SCHEMA and contract == dict(INPUT_CONTRACT):
        input_kind = "xma1"
    elif schema == PCM_MANIFEST_SCHEMA and contract == dict(PCM_INPUT_CONTRACT):
        input_kind = "pcm16"
    else:
        raise AudioReplacementPackError(
            "This is not a supported APF 2K8 Mod Studio audio replacement pack"
        )
    if document.get("payloads_included") is not TEMPLATE_PAYLOADS_INCLUDED:
        raise AudioReplacementPackError(
            "The replacement pack lost its metadata-only template declaration"
        )
    return input_kind


def _pcm_wav_maximum(target: Mapping[str, object], asset_id: object) -> int:
    try:
        pcm_target = validate_pcm16_target(
            Pcm16Target(
                channels=_exact_int(
                    target.get("channel_count"),
                    f"{asset_id} PCM channel count",
                    minimum=1,
                    maximum=2,
                ),
                sample_rate=_exact_int(
                    target.get("sample_rate"),
                    f"{asset_id} PCM sample rate",
                    minimum=8_000,
                    maximum=192_000,
                ),
                frame_count=_exact_int(
                    target.get("declared_sample_count"),
                    f"{asset_id} PCM frame count",
                    minimum=1,
                    maximum=1_000_000_000,
                ),
                encoded_size=_exact_int(
                    target.get("encoded_size"),
                    f"{asset_id} encoded size",
                    minimum=0x800,
                    maximum=24 * 1024 * 1024,
                ),
            )
        )
    except AudioEncodingError as exc:
        raise AudioReplacementPackError(
            f"PCM target shape is invalid: {asset_id}: {exc}"
        ) from exc
    return pcm_target.wav_size + MAX_WAV_OVERHEAD_BYTES


def _zip_payload_limits(
    manifest_data: bytes,
) -> tuple[str, str, dict[str, int]]:
    """Recover conservative extraction bounds; full source validation follows."""

    try:
        document = json.loads(manifest_data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AudioReplacementPackError(
            f"The audio replacement manifest is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise AudioReplacementPackError(
            "The audio replacement manifest must be a JSON object"
        )
    input_kind = _manifest_input_kind(document)
    payload_directory = _payload_directory_for_input_kind(input_kind)
    entries = document.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PACK_ENTRIES:
        raise AudioReplacementPackError(
            "The replacement pack entry count is invalid"
        )
    limits: dict[str, int] = {}
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise AudioReplacementPackError(
                "An audio replacement entry is invalid"
            )
        path = _safe_replacement_path(
            raw_entry.get("replacement_file"), input_kind
        )
        target = raw_entry.get("target")
        encoded_size = target.get("encoded_size") if isinstance(target, dict) else None
        if (
            type(encoded_size) is not int
            or not 0x800 <= encoded_size <= 24 * 1024 * 1024
        ):
            raise AudioReplacementPackError(
                f"Audio target size is invalid: {raw_entry.get('asset_id')}"
            )
        name = path.as_posix()
        if name in limits:
            raise AudioReplacementPackError(
                f"The replacement pack repeats one payload filename: {name}"
            )
        limits[name] = (
            _pcm_wav_maximum(target, raw_entry.get("asset_id"))
            if input_kind == "pcm16"
            else encoded_size + 1024 * 1024
        )
    return input_kind, payload_directory, limits


@contextmanager
def _materialized_audio_replacement_pack(
    source: Path,
) -> Iterator[tuple[Path, Path]]:
    """Yield a real pack folder, privately materializing ZIP members if needed."""

    requested = _absolute_destination(source)
    try:
        before = requested.stat(follow_symlinks=False)
    except OSError as exc:
        raise AudioReplacementPackError(
            f"Choose an existing audio replacement-pack folder or ZIP: {source}"
        ) from exc
    if stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode):
        yield requested, requested
        return
    if requested.suffix.casefold() != ".zip":
        raise AudioReplacementPackError(
            "Choose an APF audio replacement-pack folder or a .zip file"
        )
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= MAX_EXPANDED_PACK_BYTES
    ):
        raise AudioReplacementPackError(
            "The audio replacement-pack ZIP must be one private regular file "
            "within the size limit"
        )
    try:
        descriptor = os.open(
            requested,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise AudioReplacementPackError(
            f"Could not open audio replacement-pack ZIP: {exc}"
        ) from exc
    opened = os.fstat(descriptor)
    archive_identity = _file_identity(opened)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        os.close(descriptor)
        raise AudioReplacementPackError(
            "The audio replacement-pack ZIP changed while it was opened"
        )

    temporary = _private_staging_directory(
        "apf-audio-pack-import-",
        "The private audio replacement-pack extraction folder",
    )
    stream = os.fdopen(descriptor, "rb", closefd=False)
    try:
        try:
            archive = zipfile.ZipFile(stream, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise AudioReplacementPackError(
                f"Could not open audio replacement-pack ZIP: {exc}"
            ) from exc
        with archive:
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_ARCHIVE_MEMBERS:
                raise AudioReplacementPackError(
                    "The audio replacement ZIP has an invalid number of members"
                )
            by_name: dict[str, zipfile.ZipInfo] = {}
            casefolded: set[str] = set()
            for info in infos:
                name = _safe_zip_member_name(info.filename, directory=info.is_dir())
                folded = name.casefold()
                if name in by_name or folded in casefolded:
                    raise AudioReplacementPackError(
                        f"The audio replacement ZIP repeats or case-collides a path: {name}"
                    )
                casefolded.add(folded)
                if info.flag_bits & 0x1:
                    raise AudioReplacementPackError(
                        "Encrypted audio replacement ZIPs are not supported. "
                        "Create a normal unencrypted ZIP and try again."
                    )
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if info.is_dir():
                    if (
                        info.file_size != 0
                        or stat.S_ISLNK(mode)
                        or file_type not in {0, stat.S_IFDIR}
                    ):
                        raise AudioReplacementPackError(
                            f"The audio replacement ZIP directory is unsafe or unknown: {name}"
                        )
                elif (
                    stat.S_ISLNK(mode)
                    or file_type not in {0, stat.S_IFREG}
                    or info.compress_type
                    not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                ):
                    raise AudioReplacementPackError(
                        f"The audio replacement ZIP member is unsafe or uses an unsupported compression method: {name}"
                    )
                by_name[name] = info

            manifest_member = by_name.get(MANIFEST_FILENAME)
            readme_member = by_name.get(README_FILENAME)
            if manifest_member is None or readme_member is None:
                nested_manifest = next(
                    (
                        name
                        for name, info in by_name.items()
                        if not info.is_dir()
                        and name.endswith(f"/{MANIFEST_FILENAME}")
                    ),
                    None,
                )
                if nested_manifest is not None:
                    raise AudioReplacementPackError(
                        "This ZIP has one extra folder level. Put replacement-pack.json, "
                        "README.md, and its generated payload folder at the ZIP root."
                    )
                raise AudioReplacementPackError(
                    "The audio replacement ZIP is incomplete; replacement-pack.json "
                    "and README.md must be at the ZIP root"
                )
            manifest_data = _read_zip_member(
                archive,
                manifest_member,
                maximum=MAX_MANIFEST_BYTES,
                label="audio replacement manifest",
            )
            input_kind, payload_directory, payload_limits = _zip_payload_limits(
                manifest_data
            )
            accepted_readmes = (
                frozenset({_PCM_README_BYTES})
                if input_kind == "pcm16"
                else _ACCEPTED_README_BYTES
            )
            readme_data = _read_zip_member(
                archive,
                readme_member,
                maximum=max(map(len, accepted_readmes)),
                label="replacement-pack README",
            )
            if readme_data not in accepted_readmes:
                raise AudioReplacementPackError(
                    "The replacement-pack README changed. Export a fresh template "
                    "and add only listed audio payloads."
                )
            payload_directory_member = by_name.get(payload_directory)
            if (
                payload_directory_member is not None
                and not payload_directory_member.is_dir()
            ):
                raise AudioReplacementPackError(
                    f"The {payload_directory} path in the audio replacement ZIP "
                    "must be a folder"
                )
            allowed = {
                MANIFEST_FILENAME,
                README_FILENAME,
                payload_directory,
                *payload_limits,
            }
            unknown = sorted(set(by_name).difference(allowed))
            if unknown:
                raise AudioReplacementPackError(
                    "Unknown file in audio replacement ZIP: " + unknown[0]
                )
            supplied_payload_names = set(by_name).intersection(payload_limits)
            if (
                input_kind == "pcm16"
                and len(supplied_payload_names) > MAX_PCM_PACK_SUPPLIED
            ):
                raise AudioReplacementPackError(
                    "A PCM replacement pack accepts at most 256 supplied PCM16 "
                    "WAV files per import; remove or split this authored set."
                )
            expanded_total = 0
            for name, info in by_name.items():
                if info.is_dir():
                    continue
                maximum = (
                    MAX_MANIFEST_BYTES
                    if name == MANIFEST_FILENAME
                    else max(map(len, accepted_readmes))
                    if name == README_FILENAME
                    else payload_limits[name]
                )
                if not 0 < info.file_size <= maximum:
                    raise AudioReplacementPackError(
                        f"The audio replacement ZIP member is empty or too large: {name}"
                    )
                expanded_total += info.file_size
                if expanded_total > MAX_EXPANDED_PACK_BYTES:
                    raise AudioReplacementPackError(
                        "The audio replacement ZIP expands beyond the 64 GiB safety limit"
                    )
            filesystem = os.statvfs(temporary)
            available = filesystem.f_bavail * filesystem.f_frsize
            reserve = 128 * 1024 * 1024
            if expanded_total + reserve > available:
                raise AudioReplacementPackError(
                    "Not enough temporary free space to import this audio ZIP. "
                    f"It needs about {(expanded_total + reserve) / (1024 ** 3):.1f} GiB."
                )

            root_descriptor, _root_identity, _root_opened = _open_pinned_directory(
                temporary,
                label="private audio replacement ZIP extraction folder",
            )
            payload_descriptor: int | None = None
            try:
                os.mkdir(payload_directory, mode=0o700, dir_fd=root_descriptor)
                payload_descriptor, _identity, _opened = _open_directory_at(
                    root_descriptor,
                    payload_directory,
                    label=(
                        "private audio replacement ZIP "
                        f"{payload_directory} folder"
                    ),
                )
                for name, info in by_name.items():
                    if info.is_dir():
                        continue
                    if name == MANIFEST_FILENAME:
                        _write_exclusive_at(root_descriptor, name, manifest_data)
                    elif name == README_FILENAME:
                        _write_exclusive_at(root_descriptor, name, readme_data)
                    else:
                        assert payload_descriptor is not None
                        _extract_zip_member_at(
                            archive,
                            info,
                            payload_descriptor,
                            PurePosixPath(name).name,
                            maximum=payload_limits[name],
                        )
                platform_compat.fsync_directory_fd(payload_descriptor)
                platform_compat.fsync_directory_fd(root_descriptor)
            finally:
                if payload_descriptor is not None:
                    os.close(payload_descriptor)
                os.close(root_descriptor)

        after = os.fstat(descriptor)
        if (
            _file_stat_identity(_file_identity(after))
            != _file_stat_identity(archive_identity)
            or not _path_still_names_file(requested, archive_identity)
        ):
            raise AudioReplacementPackError(
                "The audio replacement-pack ZIP changed while it was checked"
            )
        yield temporary, requested
    finally:
        stream.close()
        try:
            os.close(descriptor)
        except OSError:
            pass
        # Not ``shutil.rmtree``: extracted payloads can carry the read-only
        # attribute on Windows, which refuses to delete such a file at all and
        # would leave the user's temp directory holding decoded game audio.
        platform_compat.remove_private_tree(temporary, ignore_errors=True)


def _parse_entry_baseline(
    entry: AudioReplacementEntry,
    value: object,
) -> tuple[AudioTargetBaselineState, ...]:
    if not isinstance(value, dict) or set(value) != _ENTRY_BASELINE_KEYS:
        raise AudioReplacementPackError(
            f"Audio project baseline has unknown or missing fields: {entry.asset_id}"
        )
    if value.get("schema") != BASELINE_SCHEMA:
        raise AudioReplacementPackError(
            f"Audio project baseline schema changed: {entry.asset_id}"
        )
    raw_owners = value.get("owners")
    expected_owner_ids = _baseline_owner_ids(entry)
    if not isinstance(raw_owners, list) or len(raw_owners) != len(
        expected_owner_ids
    ):
        raise AudioReplacementPackError(
            f"Audio project baseline ownership changed: {entry.asset_id}"
        )

    expected_kind = _expected_modification_kind(entry)
    states: list[AudioTargetBaselineState] = []
    for expected_owner_id, raw_state in zip(expected_owner_ids, raw_owners):
        if not isinstance(raw_state, dict):
            raise AudioReplacementPackError(
                f"Audio project baseline state is invalid: {expected_owner_id}"
            )
        state = raw_state.get("state")
        if state == "original":
            if set(raw_state) != _ORIGINAL_BASELINE_STATE_KEYS:
                raise AudioReplacementPackError(
                    f"Original audio baseline carries extra data: {expected_owner_id}"
                )
            parsed = AudioTargetBaselineState(expected_owner_id, "original")
        elif state == "modified":
            if set(raw_state) != _MODIFIED_BASELINE_STATE_KEYS:
                raise AudioReplacementPackError(
                    f"Modified audio baseline is incomplete: {expected_owner_id}"
                )
            kind = raw_state.get("kind")
            if kind != expected_kind:
                raise AudioReplacementPackError(
                    f"Audio baseline edit type changed: {expected_owner_id}"
                )
            parsed = AudioTargetBaselineState(
                expected_owner_id,
                "modified",
                kind,
                _sha256_hex(
                    raw_state.get("replacement_sha256"),
                    f"Audio baseline replacement {expected_owner_id}",
                ),
            )
        else:
            raise AudioReplacementPackError(
                f"Audio project baseline state is invalid: {expected_owner_id}"
            )
        if raw_state.get("asset_id") != expected_owner_id:
            raise AudioReplacementPackError(
                f"Audio project baseline ownership changed: {entry.asset_id}"
            )
        states.append(parsed)
    return tuple(states)


def _parse_entry(
    value: object,
    input_kind: str = "xma1",
) -> AudioReplacementEntry:
    input_kind = _normalize_input_kind(input_kind)
    if not isinstance(value, dict) or set(value) != _ENTRY_KEYS:
        raise AudioReplacementPackError(
            "An audio replacement entry has unknown or missing fields"
        )
    asset_id = value.get("asset_id")
    kind = value.get("kind")
    target = value.get("target")
    if not isinstance(asset_id, str) or kind not in {"audo", "ausb_substream"}:
        raise AudioReplacementPackError(
            "An audio replacement entry has an invalid identity"
        )
    if not isinstance(target, dict):
        raise AudioReplacementPackError(
            f"Audio target shape is missing: {asset_id}"
        )
    expected_target_keys = (
        _AUDO_TARGET_KEYS if kind == "audo" else _AUSB_TARGET_KEYS
    )
    if set(target) != expected_target_keys:
        raise AudioReplacementPackError(
            f"Audio target shape has unknown or missing fields: {asset_id}"
        )
    outer = _exact_int(
        target.get("outer_table_index"),
        f"{asset_id} outer-table index",
        maximum=1_542,
    )
    inner = _exact_int(
        target.get("inner_file_index"),
        f"{asset_id} inner-file index",
        maximum=99_999,
    )
    substream: int | None = None
    if kind == "ausb_substream":
        substream = _exact_int(
            target.get("substream_index"),
            f"{asset_id} substream index",
            maximum=99_999,
        )
    identity = ExportIdentity(kind, outer, inner, substream, asset_id)
    if _identity_asset_id(identity) != asset_id:
        raise AudioReplacementPackError(
            f"Audio entry coordinates do not match its identity: {asset_id}"
        )
    replacement_file = _safe_replacement_path(
        value.get("replacement_file"), input_kind
    )
    if replacement_file != _replacement_path(identity, input_kind):
        raise AudioReplacementPackError(
            f"Audio replacement filename changed: {asset_id}"
        )
    entry = AudioReplacementEntry(
        asset_id=asset_id,
        kind=kind,
        identity=identity,
        replacement_file=replacement_file,
        target=dict(target),
    )
    return AudioReplacementEntry(
        asset_id=entry.asset_id,
        kind=entry.kind,
        identity=entry.identity,
        replacement_file=entry.replacement_file,
        target=entry.target,
        baseline=_parse_entry_baseline(entry, value.get("baseline")),
    )


def _load_audio_replacement_pack_at(
    selected_root: Path,
    root_descriptor: int,
    root_identity: AudioReplacementDirectoryIdentity,
    root_opened: os.stat_result,
    *,
    expected_source_sha256: str,
    live_rows: Iterable[InspectorRow],
) -> AudioReplacementPackPlan:
    """Validate a complete authoring folder without reading retail audio.

    Every manifest entry is reconciled to the loaded source-owned inspector
    row before any supplied XMA file reaches the session's exact-slot writer.
    """

    recognized_root_names = {
        MANIFEST_FILENAME,
        README_FILENAME,
        PAYLOAD_DIRECTORY,
        PCM_PAYLOAD_DIRECTORY,
    }
    discovered_root_names: set[str] = set()
    with os.scandir(root_descriptor) as iterator:
        for directory_entry in iterator:
            if directory_entry.name not in recognized_root_names:
                raise AudioReplacementPackError(
                    f"Unknown file in replacement-pack folder: {directory_entry.name}"
                )
            discovered_root_names.add(directory_entry.name)
    contract_names = {MANIFEST_FILENAME, README_FILENAME}
    missing_contract_names = contract_names.difference(discovered_root_names)
    if missing_contract_names:
        raise AudioReplacementPackError(
            "The replacement-pack folder is incomplete; missing "
            + ", ".join(sorted(missing_contract_names))
        )
    manifest_data = _read_regular_bounded_at(
        root_descriptor,
        MANIFEST_FILENAME,
        maximum=MAX_MANIFEST_BYTES,
        label="audio replacement manifest",
    )
    try:
        document = json.loads(manifest_data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AudioReplacementPackError(
            f"The audio replacement manifest is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(document, dict) or set(document) != _MANIFEST_KEYS:
        raise AudioReplacementPackError(
            "The audio replacement manifest has unknown or missing top-level fields"
        )
    input_kind = _manifest_input_kind(document)
    payload_directory = _payload_directory_for_input_kind(input_kind)
    required_root_names = {
        MANIFEST_FILENAME,
        README_FILENAME,
        payload_directory,
    }
    if discovered_root_names != required_root_names:
        missing = sorted(required_root_names.difference(discovered_root_names))
        extra = sorted(discovered_root_names.difference(required_root_names))
        detail = (
            "missing " + ", ".join(missing)
            if missing
            else "unexpected " + ", ".join(extra)
        )
        raise AudioReplacementPackError(
            f"The replacement-pack folder layout is invalid; {detail}"
        )
    accepted_readmes = (
        frozenset({_PCM_README_BYTES})
        if input_kind == "pcm16"
        else _ACCEPTED_README_BYTES
    )
    readme_data = _read_regular_bounded_at(
        root_descriptor,
        README_FILENAME,
        maximum=max(map(len, accepted_readmes)),
        label="replacement-pack README",
    )
    if readme_data not in accepted_readmes:
        raise AudioReplacementPackError(
            "The replacement-pack README changed. Export a fresh template and "
            "copy only your listed audio payloads into it."
        )
    if document.get("game") != GAME_ID:
        raise AudioReplacementPackError(
            "This folder is not an APF 2K8 Mod Studio audio replacement pack"
        )
    source = document.get("source")
    if not isinstance(source, dict) or set(source) != {"sha256"}:
        raise AudioReplacementPackError(
            "The audio replacement manifest has invalid source binding"
        )
    expected_digest = _sha256_hex(expected_source_sha256, "Loaded source")
    manifest_digest = _sha256_hex(source.get("sha256"), "Pack source")
    if manifest_digest != expected_digest:
        raise AudioReplacementPackError(
            "This audio replacement pack was created for a different game source. "
            "Export a fresh template from the game currently loaded."
        )
    raw_entries = document.get("entries")
    entry_count = document.get("entry_count")
    if (
        not isinstance(raw_entries, list)
        or type(entry_count) is not int
        or entry_count != len(raw_entries)
        or not 1 <= entry_count <= MAX_PACK_ENTRIES
    ):
        raise AudioReplacementPackError(
            "The replacement pack entry count is invalid"
        )
    entries = tuple(_parse_entry(value, input_kind) for value in raw_entries)
    asset_ids = [entry.asset_id for entry in entries]
    replacement_files = [entry.replacement_file for entry in entries]
    if len(set(asset_ids)) != len(asset_ids):
        raise AudioReplacementPackError(
            "The replacement pack repeats one audio identity"
        )
    if len(set(replacement_files)) != len(replacement_files):
        raise AudioReplacementPackError(
            "The replacement pack repeats one payload filename"
        )
    project_baseline = document.get("project_baseline")
    if (
        not isinstance(project_baseline, dict)
        or set(project_baseline) != _PROJECT_BASELINE_KEYS
        or project_baseline.get("schema") != BASELINE_SCHEMA
        or type(project_baseline.get("target_count")) is not int
        or project_baseline.get("target_count") != len(entries)
    ):
        raise AudioReplacementPackError(
            "The replacement pack project baseline is invalid"
        )
    baseline_digest = _sha256_hex(
        project_baseline.get("sha256"),
        "Pack project baseline",
    )
    if baseline_digest != _project_baseline_sha256(entries):
        raise AudioReplacementPackError(
            "The replacement pack project baseline was changed"
        )

    live_by_id: dict[str, AudioReplacementEntry] = {}
    for row in live_rows:
        live = _entry_from_row(row, input_kind)
        if live.asset_id in live_by_id:
            raise AudioReplacementPackError(
                f"The loaded audio inventory repeats {live.asset_id}"
            )
        live_by_id[live.asset_id] = live
    for entry in entries:
        live = live_by_id.get(entry.asset_id)
        if live is None:
            raise AudioReplacementPackError(
                f"Unknown audio target in replacement pack: {entry.asset_id}"
            )
        if _entry_contract_document(entry) != _entry_contract_document(live):
            raise AudioReplacementPackError(
                f"Audio target shape or alias ownership changed: {entry.asset_id}"
            )

    payload_descriptor, payload_identity, payload_opened = _open_directory_at(
        root_descriptor,
        payload_directory,
        label=f"replacement-pack {payload_directory} folder",
    )
    entry_by_name = {entry.replacement_file.name: entry for entry in entries}
    discovered: dict[
        str,
        tuple[Path, AudioReplacementFileIdentity],
    ] = {}
    try:
        if input_kind == "pcm16":
            # Count only directory entries first. A folder with too many WAVs
            # must fail before any user-controlled payload byte is opened,
            # copied, or hashed. The second pass repeats this ceiling so a
            # concurrent insertion can cause at most one bounded refusal.
            with os.scandir(payload_descriptor) as iterator:
                for supplied_count, _directory_entry in enumerate(
                    iterator, start=1
                ):
                    if supplied_count > MAX_PCM_PACK_SUPPLIED:
                        raise AudioReplacementPackError(
                            "A PCM replacement pack accepts at most 256 supplied "
                            "PCM16 WAV files per import; remove or split this "
                            "authored set."
                        )
            if not _directory_unchanged(
                payload_opened, os.fstat(payload_descriptor)
            ):
                raise AudioReplacementPackError(
                    "The replacement-pack pcm16 folder changed during its "
                    "fail-fast file-count check"
                )
        with os.scandir(payload_descriptor) as iterator:
            for index, directory_entry in enumerate(iterator, start=1):
                if index > MAX_PAYLOAD_FILES:
                    raise AudioReplacementPackError(
                        "The replacement pack contains too many payload files"
                    )
                if input_kind == "pcm16" and index > MAX_PCM_PACK_SUPPLIED:
                    raise AudioReplacementPackError(
                        "A PCM replacement pack accepts at most 256 supplied "
                        "PCM16 WAV files per import; remove or split this "
                        "authored set."
                    )
                entry = entry_by_name.get(directory_entry.name)
                try:
                    info = os.stat(
                        directory_entry.name,
                        dir_fd=payload_descriptor,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise AudioReplacementPackError(
                        f"Could not inspect {payload_directory}/"
                        f"{directory_entry.name}: {exc}"
                    ) from exc
                maximum = (
                    _pcm_wav_maximum(entry.target, entry.asset_id)
                    if entry is not None and input_kind == "pcm16"
                    else int(entry.target["encoded_size"]) + 1024 * 1024
                    if entry is not None
                    else 0
                )
                if (
                    entry is None
                    or not stat.S_ISREG(info.st_mode)
                    or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink != 1
                    or not (44 if input_kind == "pcm16" else 1)
                    <= info.st_size
                    <= maximum
                ):
                    raise AudioReplacementPackError(
                        "Unknown or unsafe, oversized, or hardlinked file in "
                        f"{payload_directory}/: "
                        f"{directory_entry.name}"
                    )
                if input_kind == "pcm16":
                    content_identity = _stream_regular_bounded_at(
                        payload_descriptor,
                        directory_entry.name,
                        maximum=maximum,
                        label=f"{payload_directory}/{directory_entry.name}",
                        expected_identity=_file_identity(info),
                    )
                else:
                    data = _read_regular_bounded_at(
                        payload_descriptor,
                        directory_entry.name,
                        maximum=maximum,
                        label=f"{payload_directory}/{directory_entry.name}",
                        expected_identity=_file_identity(info),
                    )
                    content_identity = _file_identity(
                        info,
                        hashlib.sha256(data).hexdigest(),
                    )
                discovered[directory_entry.name] = (
                    selected_root / payload_directory / directory_entry.name,
                    content_identity,
                )
        if not _directory_unchanged(payload_opened, os.fstat(payload_descriptor)):
            raise AudioReplacementPackError(
                f"The replacement-pack {payload_directory} folder changed "
                "during enumeration"
            )
    finally:
        os.close(payload_descriptor)
    supplied = tuple(
        SuppliedAudioReplacement(
            entry,
            discovered[entry.replacement_file.name][0],
            discovered[entry.replacement_file.name][1],
        )
        for entry in entries
        if entry.replacement_file.name in discovered
    )
    if not supplied:
        if input_kind == "pcm16":
            raise AudioReplacementPackError(
                "No exact PCM16 .wav replacements were found. Add at least one "
                "listed WAV before importing this pack."
            )
        raise AudioReplacementPackError(
            "No pre-encoded .xma replacements were found. Add at least one listed "
            "RIFF XMA1 file before importing this folder."
        )
    if input_kind == "pcm16" and len(supplied) > MAX_PCM_PACK_SUPPLIED:
        raise AudioReplacementPackError(
            "A PCM replacement pack accepts at most 256 supplied PCM16 WAV files "
            "per import; remove or split this authored set."
        )
    if (
        not _directory_unchanged(root_opened, os.fstat(root_descriptor))
        or not _path_still_names_directory(selected_root, root_identity)
    ):
        raise AudioReplacementPackError(
            "The audio replacement-pack folder changed while it was checked"
        )
    return AudioReplacementPackPlan(
        root=selected_root,
        source_sha256=manifest_digest,
        template_entry_count=len(entries),
        supplied=supplied,
        missing_count=len(entries) - len(supplied),
        manifest_sha256=hashlib.sha256(manifest_data).hexdigest(),
        baseline_sha256=baseline_digest,
        root_identity=root_identity,
        payload_directory_identity=payload_identity,
        input_kind=input_kind,
    )


def load_audio_replacement_pack(
    root: Path,
    *,
    expected_source_sha256: str,
    live_rows: Iterable[InspectorRow],
) -> AudioReplacementPackPlan:
    """Open and validate one pack through a pinned root-directory descriptor."""

    selected_root = _absolute_destination(root)
    root_descriptor, root_identity, root_opened = _open_pinned_directory(
        selected_root,
        label="audio replacement-pack folder",
    )
    try:
        return _load_audio_replacement_pack_at(
            selected_root,
            root_descriptor,
            root_identity,
            root_opened,
            expected_source_sha256=expected_source_sha256,
            live_rows=live_rows,
        )
    finally:
        os.close(root_descriptor)


@contextmanager
def open_audio_replacement_pack(
    source: Path,
    *,
    expected_source_sha256: str,
    live_rows: Iterable[InspectorRow],
) -> Iterator[AudioReplacementPackPlan]:
    """Open a folder or ZIP while keeping private ZIP extraction alive."""

    rows = tuple(live_rows)
    with _materialized_audio_replacement_pack(source) as (root, reported_root):
        plan = load_audio_replacement_pack(
            root,
            expected_source_sha256=expected_source_sha256,
            live_rows=rows,
        )
        yield replace(plan, reported_root=reported_root)


def read_audio_replacement_payload(
    plan: AudioReplacementPackPlan,
    supplied: SuppliedAudioReplacement,
    *,
    maximum: int,
) -> bytes:
    """Re-open and read one listed payload through the pack's pinned identity."""

    if plan.input_kind != "xma1":
        raise AudioReplacementPackError(
            "PCM16 replacement packs must be materialized through their bounded WAV route"
        )

    if (
        plan.root_identity is None
        or plan.payload_directory_identity is None
        or supplied.file_identity is None
    ):
        raise AudioReplacementPackError(
            "The audio replacement plan has no pinned filesystem identity"
        )
    root_descriptor, root_identity, root_opened = _open_pinned_directory(
        plan.root,
        label="audio replacement-pack folder",
    )
    try:
        if root_identity != plan.root_identity:
            raise AudioReplacementPackError(
                "The audio replacement-pack folder changed after validation"
            )
        payload_descriptor, payload_identity, payload_opened = _open_directory_at(
            root_descriptor,
            PAYLOAD_DIRECTORY,
            label="replacement-pack xma1 folder",
        )
        try:
            if payload_identity != plan.payload_directory_identity:
                raise AudioReplacementPackError(
                    "The replacement-pack xma1 folder changed after validation"
                )
            data = _read_regular_bounded_at(
                payload_descriptor,
                supplied.entry.replacement_file.name,
                maximum=maximum,
                label=(
                    "pre-encoded audio replacement "
                    f"{supplied.entry.asset_id}"
                ),
                expected_identity=supplied.file_identity,
            )
            if not _directory_unchanged(
                payload_opened,
                os.fstat(payload_descriptor),
            ):
                raise AudioReplacementPackError(
                    "The replacement-pack xma1 folder changed while a payload was read"
                )
        finally:
            os.close(payload_descriptor)
        if (
            not _directory_unchanged(root_opened, os.fstat(root_descriptor))
            or not _path_still_names_directory(plan.root, plan.root_identity)
        ):
            raise AudioReplacementPackError(
                "The audio replacement-pack folder changed while a payload was read"
            )
        return data
    finally:
        os.close(root_descriptor)


@contextmanager
def materialize_audio_replacement_pcm(
    plan: AudioReplacementPackPlan,
    supplied: SuppliedAudioReplacement,
) -> Iterator[Path]:
    """Yield one private, identity-checked PCM copy for the external encoder."""

    if plan.input_kind != "pcm16":
        raise AudioReplacementPackError(
            "Only a PCM16 replacement pack can materialize a WAV input"
        )
    if (
        plan.root_identity is None
        or plan.payload_directory_identity is None
        or supplied.file_identity is None
    ):
        raise AudioReplacementPackError(
            "The PCM16 replacement plan has no pinned filesystem identity"
        )
    maximum = _pcm_wav_maximum(supplied.entry.target, supplied.entry.asset_id)
    temporary = _private_staging_directory(
        "apf-audio-pcm-input-",
        "The private PCM16 replacement staging folder",
    )
    copied = temporary / "input.wav"
    try:
        root_descriptor, root_identity, root_opened = _open_pinned_directory(
            plan.root,
            label="PCM16 replacement-pack folder",
        )
        try:
            if root_identity != plan.root_identity:
                raise AudioReplacementPackError(
                    "The PCM16 replacement-pack folder changed after validation"
                )
            payload_descriptor, payload_identity, payload_opened = _open_directory_at(
                root_descriptor,
                PCM_PAYLOAD_DIRECTORY,
                label="replacement-pack pcm16 folder",
            )
            try:
                if payload_identity != plan.payload_directory_identity:
                    raise AudioReplacementPackError(
                        "The replacement-pack pcm16 folder changed after validation"
                    )
                copied_identity = _stream_regular_bounded_at(
                    payload_descriptor,
                    supplied.entry.replacement_file.name,
                    maximum=maximum,
                    label=f"PCM16 replacement {supplied.entry.asset_id}",
                    expected_identity=supplied.file_identity,
                    destination=copied,
                )
                if (
                    copied_identity.content_sha256
                    != supplied.file_identity.content_sha256
                ):
                    raise AudioReplacementPackError(
                        "The PCM16 replacement content changed after validation"
                    )
                if not _directory_unchanged(
                    payload_opened,
                    os.fstat(payload_descriptor),
                ):
                    raise AudioReplacementPackError(
                        "The replacement-pack pcm16 folder changed while a WAV was copied"
                    )
            finally:
                os.close(payload_descriptor)
            if (
                not _directory_unchanged(root_opened, os.fstat(root_descriptor))
                or not _path_still_names_directory(plan.root, plan.root_identity)
            ):
                raise AudioReplacementPackError(
                    "The PCM16 replacement-pack folder changed while a WAV was copied"
                )
        finally:
            os.close(root_descriptor)
        yield copied
    finally:
        # Same reasoning as the ZIP import path: a read-only copy is undeletable
        # on Windows, so the attribute is cleared before the tree is removed.
        platform_compat.remove_private_tree(temporary, ignore_errors=True)


__all__ = [
    "AudioReplacementApplyProgress",
    "AudioReplacementApplyReceipt",
    "AudioReplacementPreviewReceipt",
    "AudioReplacementEntry",
    "AudioReplacementDirectoryIdentity",
    "AudioReplacementFileIdentity",
    "AudioReplacementPackError",
    "AudioReplacementPackPlan",
    "AudioReplacementTemplateReceipt",
    "AudioTargetBaselineState",
    "BASELINE_SCHEMA",
    "GAME_ID",
    "INPUT_CONTRACT",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA",
    "PCM_MANIFEST_SCHEMA",
    "MAX_PACK_ENTRIES",
    "MAX_PCM_PACK_SUPPLIED",
    "PAYLOAD_DIRECTORY",
    "PCM_PAYLOAD_DIRECTORY",
    "PCM_INPUT_CONTRACT",
    "TEMPLATE_PAYLOADS_INCLUDED",
    "SuppliedAudioReplacement",
    "create_audio_replacement_template",
    "current_audio_target_baseline",
    "load_audio_replacement_pack",
    "materialize_audio_replacement_pcm",
    "open_audio_replacement_pack",
    "read_audio_replacement_payload",
]
