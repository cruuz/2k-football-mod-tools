"""Retail-free batch authoring packs for NFL 2K5 audio.

An exported pack is a metadata template: it contains one canonical JSON
manifest, a short editing guide, and an empty ``replacements`` directory. It
never exports source-derived WAVs. Modders add only the WAVs they authored at
the declared paths, then import the folder or ZIP. The complete supplied set is
validated before :class:`StudioSession` stages true changes as one Undo action.

The legacy v1 route owns the frozen 153-cue standalone inventory.  The v2
route accepts an ordered selection of Editable standalone cues and fixed AUSB
streaming ranges.  The frozen v3 route owns the complete canonical 850-cue
standalone inventory.  The v4 route adds a deterministic, reference-only CSV
authoring map to that same inventory.  All formats remain metadata-only and
import through the same atomic session transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass, field
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Callable, Iterator, Sequence
from uuid import uuid4
import zipfile
import zlib

from mod_editor.core.errors import ValidationError
from mod_editor.core.json_stream import read_bounded_regular_file
from mod_editor.core.nfl2k5_audio_catalog import (
    MAX_AUDIO_REPLACEMENT_WAV_BYTES,
    MENU_BACK_SELECTOR,
    Nfl2k5AudioAsset,
    Nfl2k5AudioCatalog,
    Nfl2k5AudioService,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core.platform_compat import (
    DIRHANDLE_POSIX_DIR_FD,
    DirHandle,
    NoReplacePublishUnavailable,
    fsync_path,
    open_dir_handle,
)

from .session import BatchReplaceResult, StudioSession


AUDIO_REPLACEMENT_PACK_SCHEMA = "2k5_mod_studio_audio_replacement_pack/v1"
AUDIO_REPLACEMENT_PACK_V2_SCHEMA = "2k5_mod_studio_audio_replacement_pack/v2"
AUDIO_REPLACEMENT_PACK_V3_SCHEMA = "2k5_mod_studio_audio_replacement_pack/v3"
AUDIO_REPLACEMENT_PACK_V4_SCHEMA = "2k5_mod_studio_audio_replacement_pack/v4"
AUDIO_REPLACEMENT_MANIFEST = "audio-replacement-pack.json"
AUDIO_REPLACEMENT_GUIDE = "EDIT-AUDIO.md"
AUDIO_CUE_MAP = "AUDIO-CUE-MAP.csv"
AUDIO_CUE_MAP_SCHEMA = "2k5_mod_studio_audio_cue_map/v1"
REPLACEMENTS_DIRECTORY = "replacements"
EXPECTED_EDITABLE_AUDIO_COUNT = 153
EXPECTED_FIXED_AUDO_COUNT = 152
EXPECTED_MENU_BACK_COUNT = 1
EXPECTED_COMPLETE_STANDALONE_COUNT = 850
FAMILY_REVIEWED_MEANING_STATUS = "family_reviewed_label_runtime_meaning_unproved"
MAX_SELECTED_AUDIO_COUNT = 256
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_AUDIO_CUE_MAP_BYTES = 1024 * 1024
MAX_REPLACEMENT_WAV_BYTES = MAX_AUDIO_REPLACEMENT_WAV_BYTES
MAX_EXPANDED_PACK_BYTES = 4 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = EXPECTED_COMPLETE_STANDALONE_COUNT + 4
MAX_PREFLIGHT_CHANGED_ROWS = 32
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9._-]+")

PackProgress = Callable[[str, int, int], None]
EditableAudioAsset = Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange


def _quiet_progress(_stage: str, _completed: int, _total: int) -> None:
    pass


class AudioReplacementPackError(ValidationError):
    """A metadata template or edited replacement pack failed closed."""


@dataclass(frozen=True, slots=True)
class AudioReplacementPackExportResult:
    path: Path
    container: str
    asset_count: int
    fixed_audo_count: int
    menu_back_count: int
    manifest_sha256: str
    retail_audio_file_count: int = 0
    streaming_range_count: int = 0

    @property
    def message(self) -> str:
        kind = (
            f"audio cues ({self.asset_count - self.streaming_range_count} standalone, "
            f"{self.streaming_range_count} streaming ranges)"
            if self.streaming_range_count else "standalone cues"
        )
        return (
            f"Exported a metadata-only template for {self.asset_count} Editable "
            f"{kind}. It contains zero retail WAVs."
        )


@dataclass(frozen=True, slots=True)
class AudioReplacementPackImportResult:
    path: Path
    supplied_count: int
    changed_count: int
    unchanged_count: int
    modified_count: int
    batch: BatchReplaceResult

    @property
    def message(self) -> str:
        return (
            f"Imported {self.changed_count} changed audio cue"
            f"{'s' if self.changed_count != 1 else ''} as one Undo action; "
            f"{self.unchanged_count} supplied cue"
            f"{'s were' if self.unchanged_count != 1 else ' was'} already current."
        )


@dataclass(frozen=True, slots=True)
class AudioReplacementPackChangedRow:
    """One bounded, human-readable logical row that confirmation would change."""

    asset_id: str
    label: str
    action: str
    affected_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AudioReplacementPackPreflightResult:
    """A retail-free, read-only summary bound to one opaque confirmation token."""

    schema: str
    pack_kind: str
    confirmation_token: str = field(repr=False)
    supplied_count: int
    would_change_count: int
    unique_physical_change_count: int
    already_current_count: int
    would_restore_original_count: int
    unique_physical_restore_count: int
    affected_alias_count: int
    resulting_modified_count: int
    changed_rows: tuple[AudioReplacementPackChangedRow, ...]
    omitted_changed_count: int

    @property
    def can_apply(self) -> bool:
        return self.would_change_count > 0

    @property
    def message(self) -> str:
        if not self.can_apply:
            return (
                f"Preflight passed: all {self.supplied_count} supplied audio cue"
                f"{'s are' if self.supplied_count != 1 else ' is'} already current."
            )
        return (
            f"Preflight passed: {self.would_change_count} of "
            f"{self.supplied_count} supplied cue"
            f"{'s' if self.supplied_count != 1 else ''} would change "
            f"{self.unique_physical_change_count} physical slot"
            f"{'s' if self.unique_physical_change_count != 1 else ''}; "
            f"{self.would_restore_original_count} supplied cue"
            f"{'s' if self.would_restore_original_count != 1 else ''} would "
            "restore the source original."
        )


@dataclass(frozen=True, slots=True)
class _ValidatedAudioReplacementPack:
    reported_source: Path
    schema: str
    pack_kind: str
    member_digest: str
    replacements: tuple[tuple[EditableAudioAsset, Path], ...]


_PACK_KINDS = {
    AUDIO_REPLACEMENT_PACK_SCHEMA: "legacy_standalone",
    AUDIO_REPLACEMENT_PACK_V2_SCHEMA: "selected_audio",
    AUDIO_REPLACEMENT_PACK_V3_SCHEMA: "all_standalone_850",
    AUDIO_REPLACEMENT_PACK_V4_SCHEMA: "all_standalone_850_mapped",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioReplacementPackError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _pack_member_digest(
    records: Sequence[tuple[str, int, str]],
) -> str:
    """Hash exact member names/sizes/content hashes without exposing them."""

    canonical = _canonical_json({
        "schema": "2k5_audio_replacement_pack_member_digest/v1",
        "members": [
            {"path": path, "size": size, "sha256": sha256}
            for path, size, sha256 in sorted(records)
        ],
    })
    return _sha256(canonical)


def _safe_relative(value: object, *, suffix: str | None = None) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 512,
             "Audio pack contains an invalid relative path")
    _require("\\" not in value and "\x00" not in value,
             "Audio pack path contains unsafe characters")
    pure = PurePosixPath(value)
    _require(
        not pure.is_absolute()
        and value == pure.as_posix()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        f"Audio pack path escapes its folder: {value}",
    )
    if suffix is not None:
        _require(pure.suffix.casefold() == suffix,
                 f"Audio replacement path must end in {suffix}: {value}")
    return value


def _regular_file(
    path: Path, label: str, *, maximum: int | None = None
) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise AudioReplacementPackError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a regular file, not a folder or link: {path}",
    )
    _require(info.st_nlink == 1, f"{label} must not be a hard-linked file: {path}")
    if maximum is not None:
        _require(0 < info.st_size <= maximum, f"{label} is empty or too large: {path}")
    return info


def _read_regular_file(path: Path, label: str, *, maximum: int) -> bytes:
    """Read a bounded, unchanged regular file through its validated descriptor."""

    _resolved, payload = read_bounded_regular_file(
        path,
        label,
        maximum=maximum,
        error_type=AudioReplacementPackError,
    )
    return payload


def _open_directory_handle(path: Path, label: str) -> DirHandle:
    """Open and identity-pin a real directory for relative filesystem calls.

    Returns a :class:`~mod_editor.core.platform_compat.DirHandle` -- a POSIX
    directory descriptor where one exists (byte-for-byte the pin this used to
    open by hand) and a realpath+inode pin on Windows, which has no directory
    descriptor.  Either way the identity is re-checked against the pre-open
    ``lstat`` so a swap between the check and the open is refused.
    """

    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise AudioReplacementPackError(f"{label} is missing: {path}") from exc
    _require(
        stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        f"{label} must be a real directory, not a link: {path}",
    )
    try:
        handle = open_dir_handle(path)
    except OSError as exc:
        raise AudioReplacementPackError(
            f"{label} could not be opened safely: {path}"
        ) from exc
    opened = handle.fstat()
    if not (
        stat.S_ISDIR(opened.st_mode)
        and (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino)
    ):
        handle.close()
        raise AudioReplacementPackError(f"{label} changed while it was opened: {path}")
    return handle


def _pinned_staging_root(handle: DirHandle) -> Path:
    """POSIX ``/proc/self/fd`` anchor for inode-pinned staged path writes.

    POSIX-only.  ``/proc/self/fd/<fd>`` follows the directory *inode* the handle
    holds open, so the path-based staging writes below cannot be redirected by a
    swap of the parent path.  Windows has no such fd-path and a bare ``realpath``
    is NOT pinned -- that was the weakening this closes -- so on Windows the caller
    routes every staged write and the enumeration through the parent
    :class:`DirHandle`'s own re-verified at-operations (:func:`_staged_write`,
    :func:`_staged_mkdir`, :func:`_staged_template_files`) instead of this path, and
    reaching here on Windows is a bug that fails closed rather than handing back an
    unpinned root.
    """

    if handle.mechanism != DIRHANDLE_POSIX_DIR_FD:
        raise AudioReplacementPackError(
            "Windows audio-template staging must go through the pinned DirHandle, "
            "not a realpath"
        )
    return Path("/proc/self/fd") / str(handle.dir_fd)


def _staged_mkdir(
    stage: Path, stage_handle: DirHandle | None, name: str, mode: int
) -> None:
    """Create ``name`` in the staging root, pinned where the platform can.

    Byte-identical path ``mkdir`` on POSIX (``stage_handle is None``); a re-verified
    :meth:`DirHandle.mkdir` on Windows, where the staging directory is pinned by a
    held handle rather than an fd-path.
    """

    if stage_handle is None:
        (stage / name).mkdir(mode=mode)
    else:
        stage_handle.mkdir(name, mode)


def _staged_write(
    stage: Path, stage_handle: DirHandle | None, name: str, payload: bytes
) -> None:
    """Create and write ``name`` in the staging root, pinned where the platform can.

    Byte-identical :func:`_write_new` on POSIX (``stage_handle is None``); the pinned
    :func:`_write_new_at` on Windows, so a swapped parent or a symlinked child is
    refused -- as far as a re-verified realpath pin can, which is not the
    kernel-enforced refusal POSIX gets; see
    :func:`platform_compat.directory_transaction_guarantee` for the residual --
    instead of a bare path write being silently redirected.
    """

    if stage_handle is None:
        _write_new(stage / name, payload)
    else:
        _write_new_at(stage_handle, name, payload)


def _staged_template_files(
    stage: Path, stage_handle: DirHandle | None
) -> set[str]:
    """The relative FILE set in the staging root for the zero-retail-audio check.

    Byte-identical ``set(_folder_files(...))`` on POSIX (``stage_handle is None``);
    the pinned, re-verified :func:`_folder_files_at` enumeration on Windows, so a
    swapped parent is refused rather than a bare ``realpath`` being walked
    (on Windows by re-verified identity, not kernel resolution -- see
    :func:`platform_compat.directory_transaction_guarantee`).
    """

    if stage_handle is None:
        return set(_folder_files(stage))
    return _folder_files_at(stage_handle)


def _rename_noreplace(
    parent: int | DirHandle, source_name: str, destination_name: str
) -> None:
    """Publish one relative name, or refuse if the publish cannot be no-clobber.

    An exported template folder is a name in a directory the modder chose, so
    "this never replaces something that is already there" is a guarantee this
    export makes and not a nicety: it is the only thing standing between an
    export and someone else's folder.  A publish that reports
    ``atomic_no_clobber=False`` cannot support that promise (see
    :class:`~mod_editor.core.platform_compat.NoReplacePublication`), so it is
    refused here rather than returned as a success.
    """

    _require(
        source_name not in {"", ".", ".."}
        and destination_name not in {"", ".", ".."}
        and "/" not in source_name
        and "/" not in destination_name,
        "Audio-template publication names are invalid",
    )
    # Only the OS-primitive layer differs per platform, and it lives in
    # platform_compat.  Linux keeps renameat2(RENAME_NOREPLACE) byte-for-byte;
    # macOS uses renameatx_np(RENAME_EXCL), the atomic exclusive directory rename;
    # a POSIX kernel or volume with neither reserves the destination name with
    # os.mkdir (atomic; refuses an existing name) then os.rename the staged folder
    # onto that placeholder -- two steps, and platform_compat reports that as
    # atomic_no_clobber=False.  A destination that already exists raises
    # FileExistsError.  Windows, which has no directory descriptor, publishes by
    # the handle's re-verified realpath (its native no-clobber os.rename) rather
    # than failing closed.  A raw descriptor (the POSIX transaction, and what the
    # directory-descriptor race test drives this through) is borrowed into a
    # DirHandle so every branch runs the identical at-operation.
    handle = parent if isinstance(parent, DirHandle) else DirHandle._borrow_posix_fd(parent)
    try:
        # require_atomic: refuse the two-step reserve-then-swap fallback before
        # it can overwrite a concurrently created destination, rather than
        # inspecting atomic_no_clobber after the swap has already happened.
        published = handle.publish_no_replace(
            source_name,
            destination_name,
            is_directory=True,
            require_atomic=True,
        )
    except FileExistsError as exc:
        raise FileExistsError(
            errno.EEXIST, os.strerror(errno.EEXIST), destination_name
        ) from exc
    except NoReplacePublishUnavailable as exc:
        raise AudioReplacementPackError(
            "This system does not provide atomic no-overwrite folder publication."
        ) from exc
    if not published.atomic_no_clobber:
        # The two-step mkdir-reserve fallback got the folder onto disk, but a
        # same-user racer that replaced the reserved placeholder in the window
        # between the two steps would have been overwritten by the swap, so this
        # export cannot claim it replaced nothing.  Fail closed: the caller is
        # told a folder is now there and is not handed a success result.  The
        # staged folder is NOT rolled back -- undoing it would mean deleting or
        # renaming a name whose ownership is exactly what could not be
        # established, which is the same unsafe operation in reverse.
        raise AudioReplacementPackError(
            "This system published the audio template folder without an atomic "
            f"no-overwrite guarantee (mechanism {published.mechanism}): "
            f"'{destination_name}' now exists but Mod Studio cannot prove the "
            "publish did not replace a folder another process created at the "
            "same instant. Inspect that folder and remove it, then export to a "
            "destination on a filesystem that supports atomic no-replace folder "
            "publication."
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise AudioReplacementPackError(f"Pack path already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_new_at(directory: DirHandle, name: str, payload: bytes) -> None:
    """Pinned parallel of :func:`_write_new`: create+write a child through the handle.

    Every step is a re-verified :class:`DirHandle` at-operation on the pinned
    staging directory, so on Windows -- where the parent is pinned by realpath and
    inode identity rather than a descriptor -- a swap of the parent is refused and a
    symlinked child is rejected (the nearest thing the handle has to
    ``O_NOFOLLOW``: a separate lstat, with the check-to-use residual that
    implies) instead of
    a bare path write being silently redirected.  The flags, ``0o600`` mode, the
    fdopen/write/flush/fsync and the unlink-on-failure mirror :func:`_write_new`
    exactly (``O_NOFOLLOW`` is the handle's own symlinked-child refusal, so it is not
    in the flag set); POSIX callers stay on :func:`_write_new` and are byte-identical.
    """

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = directory.open(name, flags, 0o600)
    except FileExistsError as exc:
        raise AudioReplacementPackError(f"Pack path already exists: {name}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            directory.unlink(name)
        except OSError:
            pass
        raise


def _source_sha256(session: StudioSession) -> str:
    value = getattr(getattr(session.cache, "source", None), "sha256", None)
    _require(isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None,
             "The active NFL 2K5 source identity is unavailable")
    return value


def _display_text(value: str, *, fallback: str) -> str:
    cleaned = " ".join(
        "".join(character if character.isprintable() else " " for character in value).split()
    )
    return cleaned[:160] or fallback


def _safe_stem(asset: Nfl2k5AudioAsset) -> str:
    stem = _SAFE_STEM_RE.sub("-", _display_text(asset.name, fallback="cue")).strip("-._")
    return (stem[:48] or "cue").casefold()


def _replacement_path(asset: Nfl2k5AudioAsset, ordinal: int) -> str:
    return (
        f"{REPLACEMENTS_DIRECTORY}/{ordinal:03d}__"
        f"o{asset.outer_index:04d}_c{asset.chunk_index:04d}__"
        f"{_safe_stem(asset)}.wav"
    )


def _editable_assets(
    catalog: Nfl2k5AudioCatalog,
    *,
    expected_editable_count: int | None,
) -> tuple[Nfl2k5AudioAsset, ...]:
    """Return the frozen v1 complete-pack set, not every modern Editable row."""

    assets = tuple(
        asset for asset in catalog.assets if asset.legacy_complete_pack_editable
    )
    _require(assets, "The active source exposes no legacy complete-pack audio cues")
    _require(
        len({asset.asset_id for asset in assets}) == len(assets),
        "Editable standalone audio IDs are duplicated",
    )
    if expected_editable_count is not None:
        _require(
            len(assets) == expected_editable_count,
            f"The active source exposes {len(assets)} legacy complete-pack cues; "
            f"{expected_editable_count} are required by this pack format.",
        )
    if expected_editable_count == EXPECTED_EDITABLE_AUDIO_COUNT:
        menu_count = sum(asset.selector == MENU_BACK_SELECTOR for asset in assets)
        _require(
            menu_count == EXPECTED_MENU_BACK_COUNT
            and len(assets) - menu_count == EXPECTED_FIXED_AUDO_COUNT,
            "The legacy 152 fixed-AUDO plus Menu Back authoring boundary changed",
        )
    return assets


def _selected_audio_service(
    catalog: Nfl2k5AudioCatalog, session: StudioSession
) -> Nfl2k5AudioService:
    """Return the source-bound service that owns logical AUSB aliases."""

    service = session._require_audio_service()  # noqa: SLF001
    _require(
        isinstance(service, Nfl2k5AudioService) and service.catalog is catalog,
        "Selected audio packs require the active NFL 2K5 audio service",
    )
    return service


def _selected_assets(
    catalog: Nfl2k5AudioCatalog,
    service: Nfl2k5AudioService,
    asset_ids: Sequence[str],
) -> tuple[EditableAudioAsset, ...]:
    """Resolve one bounded, ordered public selection without physical metadata."""

    _require(
        not isinstance(asset_ids, (str, bytes, bytearray)),
        "Selected audio asset IDs must be a sequence, not one text value",
    )
    requested = tuple(asset_ids)
    _require(
        1 <= len(requested) <= MAX_SELECTED_AUDIO_COUNT,
        f"Select between 1 and {MAX_SELECTED_AUDIO_COUNT} Editable audio cues",
    )
    bank_ids = {bank.asset_id for bank in catalog.streaming_banks}
    seen: set[str] = set()
    selected: list[EditableAudioAsset] = []
    for ordinal, asset_id in enumerate(requested, 1):
        _require(
            type(asset_id) is str
            and asset_id == asset_id.strip()
            and 0 < len(asset_id) <= 512,
            f"Selected audio asset ID {ordinal} is invalid",
        )
        _require(
            asset_id not in seen,
            f"Selected audio asset ID is duplicated: {asset_id}",
        )
        seen.add(asset_id)
        _require(
            asset_id not in bank_ids,
            "Whole streaming banks cannot be placed in a replacement pack; "
            f"select an indexed streaming range instead: {asset_id}",
        )
        item = service.resolve_editable_audio(asset_id)
        _require(
            isinstance(item, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange))
            and item.asset_id == asset_id,
            f"Selected audio asset could not be resolved exactly: {asset_id}",
        )
        selected.append(item)
    return tuple(selected)


def _complete_standalone_assets(
    catalog: Nfl2k5AudioCatalog,
    service: Nfl2k5AudioService,
) -> tuple[Nfl2k5AudioAsset, ...]:
    """Resolve the exact canonical all-850 standalone v3 inventory."""

    assets = tuple(catalog.assets)
    _require(
        len(assets) == EXPECTED_COMPLETE_STANDALONE_COUNT,
        f"Complete standalone audio packs require exactly "
        f"{EXPECTED_COMPLETE_STANDALONE_COUNT} catalog cues; "
        f"the active source exposes {len(assets)}.",
    )
    _require(
        all(isinstance(asset, Nfl2k5AudioAsset) for asset in assets),
        "Complete standalone audio packs may contain standalone cues only",
    )
    _require(
        assets
        == tuple(sorted(assets, key=lambda asset: asset.selector)),
        "The standalone audio catalog is not in canonical physical order",
    )
    _require(
        len({asset.asset_id for asset in assets}) == len(assets),
        "Complete standalone audio IDs are duplicated",
    )
    _require(
        len({asset.selector for asset in assets}) == len(assets),
        "Complete standalone audio selectors are duplicated",
    )
    _require(
        sum(asset.selector == MENU_BACK_SELECTOR for asset in assets)
        == EXPECTED_MENU_BACK_COUNT,
        "Complete standalone audio packs require exactly one Menu Back cue",
    )
    for ordinal, asset in enumerate(assets, 1):
        resolved = service.resolve_editable_audio(asset.asset_id)
        _require(
            isinstance(resolved, Nfl2k5AudioAsset)
            and resolved == asset
            and resolved.asset_id == asset.asset_id,
            f"Complete standalone audio cue {ordinal} did not resolve exactly: "
            f"{asset.asset_id}",
        )
    return assets


def _v2_replacement_path(ordinal: int) -> str:
    # Keep physical selectors, bank names, offsets, and source-derived labels out
    # of the public path. The manifest's logical asset ID is the sole identity.
    return f"{REPLACEMENTS_DIRECTORY}/{ordinal:03d}__selected-audio.wav"


def complete_standalone_pack_path(
    catalog: Nfl2k5AudioCatalog, asset_id: str
) -> str | None:
    """Return one cue's public all-850 authoring path, if it is standalone.

    The ordinal is deliberately derived from the catalog's canonical order—the
    same order consumed by v3/v4 export—rather than from a physical selector.
    This keeps the GUI useful without exposing offsets or private ownership data.
    """

    if type(asset_id) is not str or not asset_id:
        return None
    for ordinal, asset in enumerate(catalog.assets, 1):
        if asset.asset_id == asset_id:
            return _v2_replacement_path(ordinal)
    return None


def _logical_alias_ids(
    service: Nfl2k5AudioService, asset: EditableAudioAsset
) -> tuple[str, ...]:
    aliases = tuple(service.audio_affected_asset_ids(asset))
    _require(
        aliases
        and asset.asset_id in aliases
        and len(set(aliases)) == len(aliases)
        and all(type(value) is str and value for value in aliases),
        f"Logical alias ownership is invalid: {asset.asset_id}",
    )
    return aliases


def _v2_asset_static_document(
    asset: EditableAudioAsset,
    ordinal: int,
    service: Nfl2k5AudioService,
) -> dict[str, object]:
    """Public v2 row: logical identity and authoring contract only."""

    contract = asset.replacement_contract
    _require(contract is not None, f"Audio cue is not Editable: {asset.asset_id}")
    aliases = _logical_alias_ids(service, asset)
    return {
        "asset_id": asset.asset_id,
        "contract": {
            "channels": contract.channels,
            "exact_frame_count": contract.frame_count,
            "metadata_chunks_allowed": contract.metadata_chunks_allowed,
            "sample_format": contract.sample_format,
            "sample_rate_hz": contract.sample_rate,
        },
        "logical_aliases": {
            "asset_ids": list(aliases),
            "count": len(aliases),
        },
        "path": _v2_replacement_path(ordinal),
    }


def _asset_static_document(
    asset: Nfl2k5AudioAsset, ordinal: int
) -> dict[str, object]:
    contract = asset.replacement_contract
    _require(contract is not None, f"Audio cue is not Editable: {asset.asset_id}")
    return {
        "asset_id": asset.asset_id,
        "contract": {
            "channels": contract.channels,
            "exact_frame_count": contract.frame_count,
            "metadata_chunks_allowed": contract.metadata_chunks_allowed,
            "sample_format": contract.sample_format,
            "sample_rate_hz": contract.sample_rate,
        },
        "display_name": _display_text(asset.label_text, fallback=asset.asset_id),
        "family": {
            "id": asset.family_id,
            "label": _display_text(asset.family_label, fallback=asset.family_id),
        },
        "path": _replacement_path(asset, ordinal),
        "route": {
            "capability_id": contract.capability_id,
            "kind": (
                "menu_back" if asset.selector == MENU_BACK_SELECTOR else "fixed_audo"
            ),
            "provider_id": contract.provider_id,
        },
        "selector": {
            "chunk_index": asset.chunk_index,
            "outer_index": asset.outer_index,
        },
    }


def _working_baseline(
    session: StudioSession, asset: EditableAudioAsset
) -> dict[str, object]:
    origin = session.audio_content_origin(asset)
    if origin == "retail_derived":
        return {"origin": "source_original"}
    _require(origin == "user_replacement", "Audio working-state origin is invalid")
    path = session.current_audio_path(asset)
    payload = _read_regular_file(
        path,
        f"Current WAV for {asset.name}",
        maximum=MAX_REPLACEMENT_WAV_BYTES,
    )
    return {
        "origin": "user_replacement",
        "wav_sha256": _sha256(payload),
        "wav_size": len(payload),
    }


def _capability_boundary(assets: Sequence[Nfl2k5AudioAsset]) -> dict[str, object]:
    menu_count = sum(asset.selector == MENU_BACK_SELECTOR for asset in assets)
    return {
        "editable_standalone_cues": len(assets),
        "fixed_audo_cues": len(assets) - menu_count,
        "menu_back_cues": menu_count,
        "streaming_bank_replacement_supported": False,
        "streaming_range_replacement_supported": False,
        "streaming_boundary": (
            "Soundtrack, commentary, stadium, and presentation banks/ranges remain "
            "browse/play/export-only until cue ownership and reversible bank repacking "
            "are decoded. Do not place streaming-bank audio in this pack."
        ),
    }


def _guide(asset_count: int) -> bytes:
    return (
        "# NFL 2K5 batch audio replacement pack\n\n"
        "This folder is a retail-free authoring template. It contains no sound "
        "from the game.\n\n"
        "1. Open `audio-replacement-pack.json`. Each of its "
        f"{asset_count} asset rows gives one declared WAV path and that cue's exact "
        "channel count, sample rate, and frame count.\n"
        "2. Export or create your replacement in Audacity, Reaper, or another audio "
        "editor as strict RIFF PCM16 little-endian WAV. Do not add metadata chunks.\n"
        "3. Put only the cues you want to change at their declared paths below "
        "`replacements/`. Missing WAVs are skipped. Do not rename files, edit this "
        "guide or the JSON manifest, or add editor backup files.\n"
        "4. In 2K5 Mod Studio, open Audio and click `Import replacement pack`. "
        "Every supplied WAV is checked before any cue changes; all true changes "
        "become one Undo action.\n"
        "5. Save a `.2k5mod` project to share the authored replacements. The source "
        "XISO is never modified.\n\n"
        "Streaming soundtrack/commentary/stadium/presentation banks and indexed "
        "ranges are not accepted here. They remain browse, play, and export-only "
        "until a reversible bank-repack contract is decoded.\n"
    ).encode("utf-8")


def _manifest_document(
    assets: Sequence[Nfl2k5AudioAsset],
    baselines: Sequence[dict[str, object]],
    *,
    source_sha256: str,
) -> tuple[dict[str, object], bytes]:
    _require(len(assets) == len(baselines), "Audio pack baseline count changed")
    guide = _guide(len(assets))
    rows = []
    for ordinal, (asset, baseline) in enumerate(zip(assets, baselines), 1):
        row = _asset_static_document(asset, ordinal)
        row["working_baseline"] = baseline
        rows.append(row)
    document = {
        "assets": rows,
        "capability_boundary": _capability_boundary(assets),
        "counts": {
            "editable_standalone_cues": len(assets),
            "replacement_wavs_in_template": 0,
        },
        "guide": {"path": AUDIO_REPLACEMENT_GUIDE, "sha256": _sha256(guide)},
        "import_policy": (
            "All supplied WAVs validate before any project mutation; true changes "
            "stage atomically as one Undo action; unchanged-only packs are refused."
        ),
        "payload_policy": "metadata-only-template; zero-retail-audio-by-construction",
        "schema": AUDIO_REPLACEMENT_PACK_SCHEMA,
        "source": {"sha256": source_sha256},
    }
    return document, guide


def _v2_guide(asset_count: int) -> bytes:
    return (
        "# NFL 2K5 selected audio replacement pack\n\n"
        "This folder is a retail-free authoring template. It contains no sound "
        "from the game.\n\n"
        "1. Open `audio-replacement-pack.json`. Each of its "
        f"{asset_count} ordered asset rows gives one logical audio ID, its linked "
        "logical aliases, one declared WAV path, and the exact channel count, "
        "sample rate, and frame count.\n"
        "2. Export or create each replacement in Audacity, Reaper, or another "
        "audio editor as strict RIFF PCM16 little-endian WAV. Do not add metadata "
        "chunks.\n"
        "3. Put only the cues you want to change at their declared paths below "
        "`replacements/`. Missing WAVs are skipped. Do not rename files, edit this "
        "guide or the JSON manifest, or add editor backup files.\n"
        "4. Import the folder or ZIP in 2K5 Mod Studio. Every supplied WAV is "
        "checked before any project mutation and all true changes become one Undo "
        "action. Two listed aliases that own one physical slot must use identical "
        "WAVs; identical files collapse safely and different files fail closed.\n"
        "5. Save a `.2k5mod` project to share the authored replacements. The source "
        "XISO is never modified.\n\n"
        "Whole streaming banks are not accepted. Select their indexed streaming "
        "ranges instead.\n"
    ).encode("utf-8")


def _v2_manifest_document(
    assets: Sequence[EditableAudioAsset],
    baselines: Sequence[dict[str, object]],
    *,
    service: Nfl2k5AudioService,
    source_sha256: str,
) -> tuple[dict[str, object], bytes]:
    _require(len(assets) == len(baselines), "Audio pack baseline count changed")
    _require(
        1 <= len(assets) <= MAX_SELECTED_AUDIO_COUNT,
        f"Selected audio packs require 1 to {MAX_SELECTED_AUDIO_COUNT} assets",
    )
    guide = _v2_guide(len(assets))
    rows: list[dict[str, object]] = []
    for ordinal, (asset, baseline) in enumerate(zip(assets, baselines), 1):
        row = _v2_asset_static_document(asset, ordinal, service)
        row["working_baseline"] = baseline
        rows.append(row)
    standalone_count = sum(
        isinstance(asset, Nfl2k5AudioAsset) for asset in assets
    )
    document = {
        "assets": rows,
        "counts": {
            "replacement_wavs_in_template": 0,
            "selected_audio_cues": len(assets),
            "standalone_cues": standalone_count,
            "streaming_ranges": len(assets) - standalone_count,
        },
        "guide": {"path": AUDIO_REPLACEMENT_GUIDE, "sha256": _sha256(guide)},
        "import_policy": (
            "All supplied WAVs validate before any project mutation; true changes "
            "stage atomically as one Undo action; identical logical aliases collapse; "
            "divergent aliases and unchanged-only packs are refused."
        ),
        "payload_policy": "metadata-only-template; zero-retail-audio-by-construction",
        "schema": AUDIO_REPLACEMENT_PACK_V2_SCHEMA,
        "source": {"sha256": source_sha256},
    }
    return document, guide


def _v3_guide(asset_count: int) -> bytes:
    return (
        "# NFL 2K5 complete 850-cue standalone audio replacement pack\n\n"
        "This folder is a retail-free authoring template. It contains no sound "
        "from the game. It lists every standalone AUDO cue in canonical game "
        "catalog order. Physical slot ownership is exact, but 697 provisional "
        "labels and runtime cue owners are not yet semantically confirmed. A "
        "replacement changes only its listed physical slot; test the result in "
        "a copied build before publishing what that sound means.\n\n"
        "1. Open `audio-replacement-pack.json`. Its "
        f"{asset_count} ordered rows give each logical standalone audio ID, one "
        "declared WAV path, and the exact channel count, sample rate, and frame "
        "count.\n"
        "2. Export or create each replacement in Audacity, Reaper, or another "
        "audio editor as strict RIFF PCM16 little-endian WAV. Do not add metadata "
        "chunks.\n"
        "3. Put only the cues you want to change at their declared paths below "
        "`replacements/`. Missing WAVs are skipped. Do not rename files, reorder "
        "or remove rows, edit this guide or manifest, or add backup files.\n"
        "4. Import the folder or ZIP in 2K5 Mod Studio. All supplied WAVs and all "
        "850 canonical metadata rows are checked before any project mutation; "
        "true changes become one Undo action.\n"
        "5. Save a `.2k5mod` project to share the authored replacements. The "
        "source XISO is never modified.\n\n"
        "This complete pack contains standalone AUDO cues only. Use a selected "
        "v2 shortlist for indexed soundtrack, commentary, crowd, stadium, and "
        "presentation streaming ranges. Whole streaming banks remain excluded.\n"
    ).encode("utf-8")


def _v3_manifest_document(
    assets: Sequence[Nfl2k5AudioAsset],
    baselines: Sequence[dict[str, object]],
    *,
    service: Nfl2k5AudioService,
    source_sha256: str,
) -> tuple[dict[str, object], bytes]:
    _require(len(assets) == len(baselines), "Audio pack baseline count changed")
    _require(
        len(assets) == EXPECTED_COMPLETE_STANDALONE_COUNT,
        f"Complete standalone audio packs require exactly "
        f"{EXPECTED_COMPLETE_STANDALONE_COUNT} assets",
    )
    guide = _v3_guide(len(assets))
    rows: list[dict[str, object]] = []
    for ordinal, (asset, baseline) in enumerate(zip(assets, baselines), 1):
        row = _v2_asset_static_document(asset, ordinal, service)
        row["working_baseline"] = baseline
        rows.append(row)
    menu_count = sum(asset.selector == MENU_BACK_SELECTOR for asset in assets)
    document = {
        "assets": rows,
        "counts": {
            "complete_standalone_cues": len(assets),
            "fixed_audo_cues": len(assets) - menu_count,
            "menu_back_cues": menu_count,
            "replacement_wavs_in_template": 0,
        },
        "guide": {"path": AUDIO_REPLACEMENT_GUIDE, "sha256": _sha256(guide)},
        "import_policy": (
            "Exactly 850 canonical standalone rows and all supplied WAVs validate "
            "before any project mutation; true changes stage atomically as one "
            "Undo action; unchanged-only packs are refused."
        ),
        "payload_policy": "metadata-only-template; zero-retail-audio-by-construction",
        "schema": AUDIO_REPLACEMENT_PACK_V3_SCHEMA,
        "source": {"sha256": source_sha256},
    }
    return document, guide


_AUDIO_CUE_MAP_COLUMNS = (
    "ordinal",
    "asset_id",
    "replacement_path",
    "display_name",
    "family_id",
    "family_label",
    "channels",
    "sample_rate_hz",
    "exact_frame_count",
    "duration_seconds",
    "product_edit_status",
    "writer_route",
    "legacy_v1_pack_member",
    "alias_status",
    "runtime_meaning_status",
)
_SPREADSHEET_FORMULA_PREFIXES = frozenset("=+-@")


def _spreadsheet_safe_text(value: str, *, fallback: str) -> str:
    """Return one printable catalog label that cannot start a CSV formula."""

    cleaned = _display_text(value, fallback=fallback)
    first_non_space = cleaned.lstrip()
    if first_non_space and first_non_space[0] in _SPREADSHEET_FORMULA_PREFIXES:
        leading_count = len(cleaned) - len(first_non_space)
        cleaned = cleaned[:leading_count] + "'" + cleaned[leading_count:]
    return cleaned


def standalone_runtime_meaning_status(asset: Nfl2k5AudioAsset) -> str:
    """Return the public confidence/status code shared by v4 and Audio search."""

    if asset.selector == MENU_BACK_SELECTOR:
        return "menu_back_route_runtime_unproved"
    if asset.legacy_complete_pack_editable:
        return "reviewed_label_runtime_meaning_unproved"
    if asset.family_label_promotion is not None:
        return FAMILY_REVIEWED_MEANING_STATUS
    return "provisional_label_runtime_meaning_unproved"


def _v4_cue_map(assets: Sequence[Nfl2k5AudioAsset]) -> bytes:
    """Build the public, reference-only all-850 authoring map."""

    _require(
        len(assets) == EXPECTED_COMPLETE_STANDALONE_COUNT,
        f"Complete standalone audio maps require exactly "
        f"{EXPECTED_COMPLETE_STANDALONE_COUNT} assets",
    )
    output = io.StringIO(newline="")
    writer = csv.writer(
        output,
        dialect="excel",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(_AUDIO_CUE_MAP_COLUMNS)
    for ordinal, asset in enumerate(assets, 1):
        contract = asset.replacement_contract
        _require(contract is not None, f"Audio cue is not Editable: {asset.asset_id}")
        writer.writerow((
            ordinal,
            _spreadsheet_safe_text(asset.asset_id, fallback=f"audio-cue-{ordinal}"),
            _spreadsheet_safe_text(
                _v2_replacement_path(ordinal),
                fallback=f"{REPLACEMENTS_DIRECTORY}/{ordinal:03d}.wav",
            ),
            _spreadsheet_safe_text(asset.label_text, fallback=f"Audio cue {ordinal}"),
            _spreadsheet_safe_text(asset.family_id, fallback="unknown"),
            _spreadsheet_safe_text(asset.family_label, fallback="Unknown family"),
            contract.channels,
            contract.sample_rate,
            contract.frame_count,
            f"{contract.duration_seconds:.6f}",
            _spreadsheet_safe_text(asset.edit_status, fallback="Editable"),
            "menu_back" if asset.selector == MENU_BACK_SELECTOR else "fixed_audo",
            "true" if asset.legacy_complete_pack_editable else "false",
            _spreadsheet_safe_text(asset.alias_status, fallback="Unknown alias status"),
            _spreadsheet_safe_text(
                standalone_runtime_meaning_status(asset),
                fallback="Runtime cue meaning is provisional",
            ),
        ))
    payload = output.getvalue().encode("utf-8")
    _require(
        0 < len(payload) <= MAX_AUDIO_CUE_MAP_BYTES,
        "Complete standalone audio map is empty or too large",
    )
    _require(
        not payload.startswith(b"\xef\xbb\xbf") and b"\r" not in payload,
        "Complete standalone audio map must be UTF-8 with LF line endings",
    )
    return payload


def _v4_guide(asset_count: int) -> bytes:
    return (
        "# NFL 2K5 mapped complete 850-cue audio replacement pack\n\n"
        "This folder is a retail-free authoring template. It contains no sound "
        "from the game. It lists every standalone AUDO cue in canonical game "
        "catalog order. Physical slot ownership is exact, but provisional labels "
        "and runtime cue meanings are not yet confirmed. Test replacements in a "
        "copied build before publishing what a sound means.\n\n"
        "1. Open `AUDIO-CUE-MAP.csv` in a spreadsheet for the friendly name, "
        "family, exact WAV shape, duration, confidence note, and replacement path "
        f"for all {asset_count} cues. A friendly name beginning with `family: ` "
        "is a disclosed family inference: the cue decodes byte-identical to a "
        "reviewed cue, so it sounds the same, but its own runtime trigger is "
        "still unproved. The CSV is reference-only; filter it in place, but copy "
        "it outside this pack before saving notes or annotations.\n"
        "2. Export or create each replacement in Audacity, Reaper, or another "
        "audio editor as strict RIFF PCM16 little-endian WAV. Do not add metadata "
        "chunks.\n"
        "3. Put only the cues you want to change at the map's exact path below "
        "`replacements/`. Missing WAVs are skipped. Do not rename files, reorder "
        "or remove JSON rows, edit the guide, manifest, or CSV, or add backups.\n"
        "4. Import the folder or ZIP in 2K5 Mod Studio. The guide, manifest, map, "
        "all 850 canonical rows, and every supplied WAV are checked before any "
        "project mutation; true changes become one Undo action.\n"
        "5. Save a `.2k5mod` project to share the authored replacements. The "
        "source XISO is never modified.\n\n"
        "This complete pack contains standalone AUDO cues only. Use a selected "
        "v2 shortlist for indexed soundtrack, commentary, crowd, stadium, and "
        "presentation streaming ranges. Whole streaming banks remain excluded.\n"
    ).encode("utf-8")


def _v4_manifest_document(
    assets: Sequence[Nfl2k5AudioAsset],
    baselines: Sequence[dict[str, object]],
    *,
    service: Nfl2k5AudioService,
    source_sha256: str,
) -> tuple[dict[str, object], bytes, bytes]:
    _require(len(assets) == len(baselines), "Audio pack baseline count changed")
    _require(
        len(assets) == EXPECTED_COMPLETE_STANDALONE_COUNT,
        f"Complete standalone audio packs require exactly "
        f"{EXPECTED_COMPLETE_STANDALONE_COUNT} assets",
    )
    guide = _v4_guide(len(assets))
    cue_map = _v4_cue_map(assets)
    rows: list[dict[str, object]] = []
    for ordinal, (asset, baseline) in enumerate(zip(assets, baselines), 1):
        row = _v2_asset_static_document(asset, ordinal, service)
        row["working_baseline"] = baseline
        rows.append(row)
    menu_count = sum(asset.selector == MENU_BACK_SELECTOR for asset in assets)
    document = {
        "assets": rows,
        "counts": {
            "complete_standalone_cues": len(assets),
            "fixed_audo_cues": len(assets) - menu_count,
            "menu_back_cues": menu_count,
            "replacement_wavs_in_template": 0,
        },
        "cue_map": {
            "path": AUDIO_CUE_MAP,
            "row_count": len(assets),
            "schema": AUDIO_CUE_MAP_SCHEMA,
            "sha256": _sha256(cue_map),
        },
        "guide": {"path": AUDIO_REPLACEMENT_GUIDE, "sha256": _sha256(guide)},
        "import_policy": (
            "Exactly 850 canonical standalone rows, the immutable reference map, "
            "and all supplied WAVs validate before any project mutation; true "
            "changes stage atomically as one Undo action; unchanged-only packs "
            "are refused."
        ),
        "payload_policy": "metadata-only-template; zero-retail-audio-by-construction",
        "schema": AUDIO_REPLACEMENT_PACK_V4_SCHEMA,
        "source": {"sha256": source_sha256},
    }
    return document, guide, cue_map


def _zip_file_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.flag_bits = 0x800
    return info


def _zip_directory_info(name: str) -> zipfile.ZipInfo:
    normalized = name.rstrip("/") + "/"
    info = zipfile.ZipInfo(normalized, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFDIR | 0o700) << 16
    info.flag_bits = 0x800
    return info


def _write_template_archive(
    archive: zipfile.ZipFile,
    guide: bytes,
    manifest_payload: bytes,
    cue_map_payload: bytes | None,
) -> None:
    """Write the fixed, retail-free template members into ``archive``.

    Shared verbatim by the POSIX path-based publish and the Windows handle-pinned
    :func:`_publish_zip_template_at`, so both emit the identical member set -- the
    guide, the manifest, an optional cue map, and the empty ``replacements``
    directory -- and neither can drift from the other.
    """

    archive.writestr(_zip_file_info(AUDIO_REPLACEMENT_GUIDE), guide)
    archive.writestr(_zip_file_info(AUDIO_REPLACEMENT_MANIFEST), manifest_payload)
    if cue_map_payload is not None:
        archive.writestr(_zip_file_info(AUDIO_CUE_MAP), cue_map_payload)
    archive.writestr(_zip_directory_info(REPLACEMENTS_DIRECTORY), b"")


def _publish_zip_template_at(
    parent_handle: DirHandle,
    archive_name: str,
    destination_name: str,
    *,
    guide: bytes,
    manifest_payload: bytes,
    cue_map_payload: bytes | None,
) -> None:
    """Create, verify and atomically publish the ZIP template through the pinned parent.

    Windows-only counterpart to the byte-identical POSIX path-based flow in
    :meth:`AudioReplacementPackService.export_template`.  Every step is a re-verified
    :class:`DirHandle` at-operation on the pinned parent directory: the archive is
    created ``O_EXCL`` through the handle -- never written to a bare ``realpath`` --
    flushed on that same descriptor, re-read for the zero-retail-WAV check, and
    published with the handle's own no-clobber ``os.link``, so a swap of the parent
    is refused rather than silently followed -- kernel-enforced on POSIX, and on
    Windows by the handle's re-verified identity pin, which leaves the
    check-to-use residual
    :func:`platform_compat.directory_transaction_guarantee` reports.  The temporary archive is removed
    through the handle on the way out whether or not the link succeeded.
    """

    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = parent_handle.open(archive_name, flags, 0o600)
    except FileExistsError as exc:
        raise AudioReplacementPackError(
            f"A file already exists there: {destination_name}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w+b", closefd=True) as stream:
            with zipfile.ZipFile(stream, "w", allowZip64=True) as archive:
                _write_template_archive(
                    archive, guide, manifest_payload, cue_map_payload
                )
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            with zipfile.ZipFile(stream, "r") as verify:
                _require(
                    all(
                        not name.casefold().endswith(".wav")
                        for name in verify.namelist()
                    ),
                    "Metadata template unexpectedly contains a WAV",
                )
        try:
            parent_handle.link(archive_name, destination_name)
        except FileExistsError as exc:
            raise AudioReplacementPackError(
                f"A file already exists there: {destination_name}"
            ) from exc
    finally:
        try:
            parent_handle.unlink(archive_name)
        except OSError:
            pass


def _folder_files(
    root: Path,
    *,
    allowed_directories: set[str] | None = None,
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            path = current_path / directory
            info = path.lstat()
            _require(
                stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"Audio pack contains an unsafe directory link: {path}",
            )
            relative_directory = _safe_relative(
                path.relative_to(root).as_posix()
            )
            if allowed_directories is not None:
                _require(
                    relative_directory in allowed_directories,
                    "Audio replacement pack contains an undeclared or unknown "
                    f"directory: {relative_directory}",
                )
        for name in files:
            path = current_path / name
            _regular_file(path, "Audio pack file")
            relative = _safe_relative(path.relative_to(root).as_posix())
            _require(relative not in result, f"Audio pack repeats path: {relative}")
            result[relative] = path
    return result


def _folder_files_at(root: DirHandle) -> set[str]:
    """Pinned staging-tree enumeration: the relative FILE set under ``root`` (Windows).

    The byte-identical POSIX enumeration is :func:`_folder_files` walking the
    ``/proc/self/fd`` anchor; Windows has no such fd-path, so this reproduces that
    result -- the set of relative regular-file names, with the same
    ``S_ISREG``/``S_ISLNK``/``st_nlink == 1`` gates :func:`_regular_file` applies --
    but every ``scandir``, ``stat`` and directory descent is a re-verified
    :class:`DirHandle` at-operation, so a swapped parent is refused rather than
    walked (on Windows by re-verified identity, not kernel resolution -- see
    :func:`platform_compat.directory_transaction_guarantee`).  The staged template tree is exactly one level of files plus the single
    empty ``replacements`` directory this writer just created, so a re-verified
    scandir of ``root`` and of its one child directory covers it; anything
    unexpected -- a symlink, or a directory nested deeper than can occur here --
    fails closed.
    """

    files: set[str] = set()
    for entry in root.scandir():
        info = root.stat(entry.name, follow=False)
        if stat.S_ISLNK(info.st_mode):
            raise AudioReplacementPackError(
                f"Audio pack contains an unsafe directory link: {entry.name}"
            )
        if stat.S_ISDIR(info.st_mode):
            child = root.open_dir(entry.name)
            try:
                for nested in child.scandir():
                    nested_info = child.stat(nested.name, follow=False)
                    if not (
                        stat.S_ISREG(nested_info.st_mode)
                        and not stat.S_ISLNK(nested_info.st_mode)
                        and nested_info.st_nlink == 1
                    ):
                        raise AudioReplacementPackError(
                            "Audio pack contains an unsafe or unexpected entry: "
                            f"{entry.name}/{nested.name}"
                        )
                    files.add(f"{entry.name}/{nested.name}")
            finally:
                child.close()
            continue
        if not (stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
            raise AudioReplacementPackError(
                f"Audio pack contains an unexpected entry: {entry.name}"
            )
        files.add(entry.name)
    return files


@contextmanager
def _pack_root(source: Path) -> Iterator[tuple[Path, Path]]:
    requested = source.expanduser()
    try:
        info = requested.lstat()
    except FileNotFoundError as exc:
        raise AudioReplacementPackError(
            f"Choose an existing audio replacement-pack folder or ZIP: {source}"
        ) from exc
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        yield requested.resolve(strict=True), requested.resolve(strict=True)
        return
    _regular_file(requested, "Audio replacement-pack ZIP")
    _require(requested.suffix.casefold() == ".zip",
             "Audio replacement-pack archive must end in .zip")
    temporary = Path(tempfile.mkdtemp(prefix="2k5-audio-pack-import-"))
    try:
        try:
            archive = zipfile.ZipFile(requested, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise AudioReplacementPackError(f"Could not open audio pack ZIP: {exc}") from exc
        with archive:
            infos = archive.infolist()
            _require(len(infos) <= MAX_ARCHIVE_MEMBERS,
                     "Audio pack ZIP contains too many members")
            names = [row.filename for row in infos]
            _require(len(names) == len(set(names)),
                     "Audio pack ZIP contains duplicate paths")
            total = 0
            for row in infos:
                mode = row.external_attr >> 16
                if row.is_dir():
                    name = _safe_relative(row.filename.rstrip("/"))
                    _require(
                        name == REPLACEMENTS_DIRECTORY
                        and row.file_size == 0
                        and not stat.S_ISLNK(mode)
                        and not (row.flag_bits & 0x1),
                        f"Audio pack ZIP directory is unsafe or unknown: {name}",
                    )
                    (temporary / REPLACEMENTS_DIRECTORY).mkdir(mode=0o700, exist_ok=True)
                    continue
                name = _safe_relative(row.filename)
                _require(
                    not stat.S_ISLNK(mode)
                    and row.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    and not (row.flag_bits & 0x1),
                    f"Audio pack ZIP member is unsafe or encrypted: {name}",
                )
                maximum = (
                    MAX_MANIFEST_BYTES
                    if name in {AUDIO_REPLACEMENT_MANIFEST, AUDIO_REPLACEMENT_GUIDE}
                    else MAX_AUDIO_CUE_MAP_BYTES
                    if name == AUDIO_CUE_MAP
                    else MAX_REPLACEMENT_WAV_BYTES
                )
                _require(0 < row.file_size <= maximum,
                         f"Audio pack ZIP member is empty or too large: {name}")
                total += row.file_size
                _require(total <= MAX_EXPANDED_PACK_BYTES,
                         "Audio pack ZIP expands beyond the safety limit")
                try:
                    with archive.open(row, "r") as reader:
                        payload = reader.read(maximum + 1)
                except (
                    OSError,
                    EOFError,
                    RuntimeError,
                    zipfile.BadZipFile,
                    zlib.error,
                ) as exc:
                    raise AudioReplacementPackError(
                        f"Could not read audio pack ZIP member {name}: {exc}"
                    ) from exc
                _require(len(payload) == row.file_size <= maximum,
                         f"Audio pack ZIP member size changed: {name}")
                _write_new(temporary.joinpath(*PurePosixPath(name).parts), payload)
        yield temporary, requested.resolve(strict=True)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


class AudioReplacementPackService:
    """Export retail-free templates and atomically import authored WAV sets."""

    def __init__(
        self,
        catalog: Nfl2k5AudioCatalog,
        session: StudioSession,
        *,
        expected_editable_count: int | None = EXPECTED_EDITABLE_AUDIO_COUNT,
    ) -> None:
        self.catalog = catalog
        self.session = session
        self.expected_editable_count = expected_editable_count

    def export_template(
        self,
        destination: Path,
        *,
        container: str | None = None,
        progress: PackProgress = _quiet_progress,
        complete_standalone: bool = False,
        with_authoring_map: bool = False,
        asset_ids: Sequence[str] | None = None,
    ) -> AudioReplacementPackExportResult:
        """Publish a folder or deterministic ZIP containing metadata only.

        Neither container ever replaces a name that already exists: the ZIP is
        published with ``os.link`` (atomic; ``FileExistsError`` if the name is
        taken) and the folder through :func:`_rename_noreplace`, which refuses a
        platform mechanism that cannot promise no-clobber instead of using it.
        """

        _require(
            type(complete_standalone) is bool,
            "Complete standalone audio-pack mode must be true or false",
        )
        _require(
            type(with_authoring_map) is bool,
            "Audio authoring-map mode must be true or false",
        )
        _require(
            not with_authoring_map or complete_standalone,
            "The authoring map is available only for the complete 850-cue "
            "standalone pack",
        )
        _require(
            not (complete_standalone and asset_ids is not None),
            "Choose either the complete 850-cue standalone pack or a selected "
            "audio shortlist, not both",
        )
        selected_mode = asset_ids is not None
        service: Nfl2k5AudioService | None = None
        if complete_standalone:
            service = _selected_audio_service(self.catalog, self.session)
            assets: tuple[EditableAudioAsset, ...] = _complete_standalone_assets(
                self.catalog, service
            )
        elif selected_mode:
            service = _selected_audio_service(self.catalog, self.session)
            assert asset_ids is not None
            assets = _selected_assets(
                self.catalog, service, asset_ids
            )
        else:
            assets = _editable_assets(
                self.catalog, expected_editable_count=self.expected_editable_count
            )
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        normalized = (
            container.strip().casefold() if isinstance(container, str)
            else ("zip" if requested.suffix.casefold() == ".zip" else "folder")
        )
        _require(normalized in {"folder", "zip"},
                 "Audio replacement-pack container must be folder or zip")
        if normalized == "zip":
            _require(requested.suffix.casefold() == ".zip",
                     "Audio replacement-pack ZIP destination must end in .zip")
        _require(
            requested.name not in {"", ".", ".."},
            "Audio replacement-pack destination needs a file or folder name",
        )
        _require(not os.path.lexists(requested),
                 f"A file or folder already exists there: {requested}")
        requested.parent.mkdir(parents=True, exist_ok=True)

        progress(
            (
                "Preparing complete standalone-audio contracts"
                if complete_standalone
                else "Preparing selected-audio contracts"
                if selected_mode
                else "Preparing standalone-audio contracts"
            ),
            0,
            len(assets) + 1,
        )
        baselines: list[dict[str, object]] = []
        for completed, asset in enumerate(assets, 1):
            baselines.append(_working_baseline(self.session, asset))
            progress("Reading current audio edit state", completed, len(assets) + 1)
        cue_map_payload: bytes | None = None
        if complete_standalone:
            assert service is not None
            complete_assets = tuple(
                asset for asset in assets
                if isinstance(asset, Nfl2k5AudioAsset)
            )
            if with_authoring_map:
                document, guide, cue_map_payload = _v4_manifest_document(
                    complete_assets,
                    baselines,
                    service=service,
                    source_sha256=_source_sha256(self.session),
                )
            else:
                document, guide = _v3_manifest_document(
                    complete_assets,
                    baselines,
                    service=service,
                    source_sha256=_source_sha256(self.session),
                )
        elif selected_mode:
            assert service is not None
            document, guide = _v2_manifest_document(
                assets,
                baselines,
                service=service,
                source_sha256=_source_sha256(self.session),
            )
        else:
            document, guide = _manifest_document(
                assets, baselines, source_sha256=_source_sha256(self.session)
            )
        manifest_payload = _canonical_json(document)

        parent_handle = _open_directory_handle(
            requested.parent, "Audio-template destination folder"
        )
        stage_name = f".{requested.name}.audio-pack-{uuid4().hex}"
        try:
            parent_handle.mkdir(stage_name, 0o700)
        except BaseException:
            parent_handle.close()
            raise
        # Raw descriptor on POSIX so the atomic-publish helper stays byte-identical
        # (and the directory-descriptor race test can drive it through that fd);
        # the handle itself on Windows, which has no descriptor to hand out.
        posix_staging = parent_handle.mechanism == DIRHANDLE_POSIX_DIR_FD
        parent_ref = parent_handle.dir_fd if posix_staging else parent_handle
        # Where the staged files are written.  POSIX anchors them under
        # /proc/self/fd/<parent_fd>, inode-pinned through the descriptor and
        # byte-identical.  Windows has no fd-path, so the staging directory is
        # opened as its OWN re-verified DirHandle (below, inside the try so a
        # failure cleans up) and every nested write and the enumeration is a handle
        # at-operation -- a bare realpath would be unpinned.
        stage_handle: DirHandle | None = None
        if posix_staging:
            pinned_parent = _pinned_staging_root(parent_handle)
            stage = pinned_parent / stage_name
        else:
            assert parent_handle.realpath is not None
            stage = Path(parent_handle.realpath) / stage_name
        try:
            if not posix_staging:
                stage_handle = parent_handle.open_dir(stage_name)
            _staged_mkdir(stage, stage_handle, REPLACEMENTS_DIRECTORY, 0o700)
            _staged_write(stage, stage_handle, AUDIO_REPLACEMENT_GUIDE, guide)
            _staged_write(
                stage, stage_handle, AUDIO_REPLACEMENT_MANIFEST, manifest_payload
            )
            if cue_map_payload is not None:
                _staged_write(stage, stage_handle, AUDIO_CUE_MAP, cue_map_payload)
            # This exact allowlist is the structural zero-retail-audio rule.
            expected_template_files = {
                AUDIO_REPLACEMENT_GUIDE,
                AUDIO_REPLACEMENT_MANIFEST,
            }
            if cue_map_payload is not None:
                expected_template_files.add(AUDIO_CUE_MAP)
            _require(
                _staged_template_files(stage, stage_handle)
                == expected_template_files,
                "Metadata template unexpectedly contains an audio payload",
            )
            # The staged writes and their check are done; release the Windows
            # staging pin now.  Holding the staging directory's own handle would
            # make Windows refuse to rename it during the folder publish below (the
            # pin withholds delete/rename), and would block its removal at cleanup;
            # the publish itself is pinned by parent_handle.  No-op on POSIX.
            if stage_handle is not None:
                stage_handle.close()
                stage_handle = None
            progress("Publishing retail-free audio template", len(assets), len(assets) + 1)
            if normalized == "folder":
                _rename_noreplace(
                    parent_ref, stage_name, requested.name
                )
            elif posix_staging:
                archive_name = f"{stage_name}.zip"
                archive_path = pinned_parent / archive_name
                try:
                    with zipfile.ZipFile(archive_path, "x", allowZip64=True) as archive:
                        _write_template_archive(
                            archive, guide, manifest_payload, cue_map_payload
                        )
                    os.chmod(archive_path, 0o600)
                    # Durable before the hard link below names it.  POSIX still
                    # flushes through a read-only open; Windows needs the
                    # writable handle ``FlushFileBuffers`` demands.
                    fsync_path(archive_path)
                    with zipfile.ZipFile(archive_path, "r") as verify:
                        _require(
                            all(not name.casefold().endswith(".wav")
                                for name in verify.namelist()),
                            "Metadata template unexpectedly contains a WAV",
                        )
                    try:
                        parent_handle.link(archive_name, requested.name)
                    except FileExistsError as exc:
                        raise AudioReplacementPackError(
                            f"A file already exists there: {requested}"
                        ) from exc
                finally:
                    archive_path.unlink(missing_ok=True)
            else:
                # Windows: create, verify and publish the ZIP through the pinned
                # parent handle so its creation is bound to the pinned directory
                # rather than a bare realpath.
                _publish_zip_template_at(
                    parent_handle,
                    f"{stage_name}.zip",
                    requested.name,
                    guide=guide,
                    manifest_payload=manifest_payload,
                    cue_map_payload=cue_map_payload,
                )
            progress("Audio replacement template ready", len(assets) + 1, len(assets) + 1)
            menu_count = sum(
                isinstance(asset, Nfl2k5AudioAsset)
                and asset.selector == MENU_BACK_SELECTOR
                for asset in assets
            )
            streaming_count = sum(
                isinstance(asset, Nfl2k5StreamingAudioRange) for asset in assets
            )
            fixed_audo_count = sum(
                isinstance(asset, Nfl2k5AudioAsset)
                and asset.selector != MENU_BACK_SELECTOR
                for asset in assets
            )
            return AudioReplacementPackExportResult(
                path=requested.resolve(strict=True),
                container=normalized,
                asset_count=len(assets),
                fixed_audo_count=fixed_audo_count,
                menu_back_count=menu_count,
                manifest_sha256=_sha256(manifest_payload),
                streaming_range_count=streaming_count,
            )
        except FileExistsError as exc:
            raise AudioReplacementPackError(
                f"A file or folder already exists there: {requested}"
            ) from exc
        finally:
            # Release the Windows staging pin before removing the directory it
            # pins (a held handle blocks the delete there); idempotent and a no-op
            # on POSIX or once already closed above.
            if stage_handle is not None:
                stage_handle.close()
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            parent_handle.close()

    @contextmanager
    def _validated_edited(
        self,
        source: Path,
        *,
        progress: PackProgress = _quiet_progress,
    ) -> Iterator[_ValidatedAudioReplacementPack]:
        """Yield immutable private snapshots after every pack-level gate passes."""

        with _pack_root(source) as (root, reported_source):
            files = _folder_files(
                root, allowed_directories={REPLACEMENTS_DIRECTORY}
            )
            manifest_path = files.get(AUDIO_REPLACEMENT_MANIFEST)
            _require(manifest_path is not None,
                     f"{AUDIO_REPLACEMENT_MANIFEST} is missing")
            manifest_payload = _read_regular_file(
                manifest_path,
                "Audio pack manifest",
                maximum=MAX_MANIFEST_BYTES,
            )
            try:
                document = json.loads(manifest_payload)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AudioReplacementPackError(
                    "Audio replacement-pack manifest is not valid JSON"
                ) from exc
            _require(isinstance(document, dict), "Audio pack manifest must be an object")
            schema = document.get("schema")
            _require(
                schema in {
                    AUDIO_REPLACEMENT_PACK_SCHEMA,
                    AUDIO_REPLACEMENT_PACK_V2_SCHEMA,
                    AUDIO_REPLACEMENT_PACK_V3_SCHEMA,
                    AUDIO_REPLACEMENT_PACK_V4_SCHEMA,
                },
                "Audio replacement-pack manifest schema is unsupported",
            )
            _require(document.get("source") == {"sha256": _source_sha256(self.session)},
                     "This audio pack was exported for a different NFL 2K5 source")

            raw_rows = document.get("assets")
            _require(isinstance(raw_rows, list), "Audio pack asset inventory is invalid")
            selected_service: Nfl2k5AudioService | None = None
            expected_cue_map: bytes | None = None
            if schema == AUDIO_REPLACEMENT_PACK_SCHEMA:
                assets: tuple[EditableAudioAsset, ...] = _editable_assets(
                    self.catalog,
                    expected_editable_count=self.expected_editable_count,
                )
                _require(
                    len(raw_rows) == len(assets),
                    "Audio pack does not list the complete legacy 153-cue inventory",
                )
            elif schema == AUDIO_REPLACEMENT_PACK_V2_SCHEMA:
                _require(
                    1 <= len(raw_rows) <= MAX_SELECTED_AUDIO_COUNT,
                    f"Selected audio packs must list 1 to "
                    f"{MAX_SELECTED_AUDIO_COUNT} asset rows",
                )
                selected_ids: list[str] = []
                for ordinal, raw_row in enumerate(raw_rows, 1):
                    _require(
                        isinstance(raw_row, dict),
                        f"Audio pack asset row {ordinal} is invalid",
                    )
                    asset_id = raw_row.get("asset_id")
                    _require(
                        type(asset_id) is str,
                        f"Audio pack asset row {ordinal} has an invalid logical ID",
                    )
                    selected_ids.append(asset_id)
                selected_service = _selected_audio_service(
                    self.catalog, self.session
                )
                assets = _selected_assets(
                    self.catalog, selected_service, selected_ids
                )
            else:
                selected_service = _selected_audio_service(
                    self.catalog, self.session
                )
                assets = _complete_standalone_assets(
                    self.catalog, selected_service
                )
                _require(
                    len(raw_rows) == EXPECTED_COMPLETE_STANDALONE_COUNT,
                    "Complete standalone audio packs must list exactly "
                    f"{EXPECTED_COMPLETE_STANDALONE_COUNT} canonical asset rows",
                )

            baselines: list[dict[str, object]] = []
            declared_paths: set[str] = set()
            replacements: list[tuple[EditableAudioAsset, Path, str]] = []
            progress("Checking audio replacement-pack metadata", 0, len(assets) + 1)
            for ordinal, (asset, raw_row) in enumerate(zip(assets, raw_rows), 1):
                _require(isinstance(raw_row, dict),
                         f"Audio pack asset row {ordinal} is invalid")
                baseline = raw_row.get("working_baseline")
                _require(isinstance(baseline, dict),
                         f"Audio pack baseline is invalid: {asset.asset_id}")
                if schema == AUDIO_REPLACEMENT_PACK_SCHEMA:
                    _require(
                        isinstance(asset, Nfl2k5AudioAsset),
                        "Legacy audio packs may contain standalone cues only",
                    )
                    expected_static = _asset_static_document(asset, ordinal)
                else:
                    assert selected_service is not None
                    expected_static = _v2_asset_static_document(
                        asset, ordinal, selected_service
                    )
                expected_row = dict(expected_static)
                expected_row["working_baseline"] = baseline
                _require(raw_row == expected_row,
                         f"Audio pack metadata changed: {asset.asset_id}")
                current_baseline = _working_baseline(self.session, asset)
                _require(
                    baseline == current_baseline,
                    f"The current project state changed after this pack was exported: "
                    f"{asset.name}. Export a fresh audio replacement pack.",
                )
                baselines.append(current_baseline)
                relative = _safe_relative(expected_static["path"], suffix=".wav")
                _require(relative not in declared_paths,
                         f"Audio pack repeats replacement path: {relative}")
                declared_paths.add(relative)
                supplied = files.get(relative)
                if supplied is not None:
                    _regular_file(
                        supplied,
                        f"Replacement WAV for {asset.name}",
                        maximum=MAX_REPLACEMENT_WAV_BYTES,
                    )
                    replacements.append((asset, supplied, relative))
                progress("Checking audio replacement-pack metadata", ordinal, len(assets) + 1)

            if schema == AUDIO_REPLACEMENT_PACK_SCHEMA:
                legacy_assets = tuple(
                    asset for asset in assets
                    if isinstance(asset, Nfl2k5AudioAsset)
                )
                expected_document, expected_guide = _manifest_document(
                    legacy_assets,
                    baselines,
                    source_sha256=_source_sha256(self.session),
                )
            elif schema == AUDIO_REPLACEMENT_PACK_V2_SCHEMA:
                assert selected_service is not None
                expected_document, expected_guide = _v2_manifest_document(
                    assets,
                    baselines,
                    service=selected_service,
                    source_sha256=_source_sha256(self.session),
                )
            elif schema == AUDIO_REPLACEMENT_PACK_V3_SCHEMA:
                assert selected_service is not None
                complete_assets = tuple(
                    asset for asset in assets
                    if isinstance(asset, Nfl2k5AudioAsset)
                )
                expected_document, expected_guide = _v3_manifest_document(
                    complete_assets,
                    baselines,
                    service=selected_service,
                    source_sha256=_source_sha256(self.session),
                )
            else:
                assert selected_service is not None
                complete_assets = tuple(
                    asset for asset in assets
                    if isinstance(asset, Nfl2k5AudioAsset)
                )
                expected_document, expected_guide, expected_cue_map = (
                    _v4_manifest_document(
                        complete_assets,
                        baselines,
                        service=selected_service,
                        source_sha256=_source_sha256(self.session),
                    )
                )
            _require(document == expected_document,
                     "Audio replacement-pack manifest was edited; export a fresh template")
            guide_row = document.get("guide")
            _require(isinstance(guide_row, dict), "Audio pack guide record is invalid")
            guide_path = files.get(AUDIO_REPLACEMENT_GUIDE)
            _require(guide_path is not None, f"{AUDIO_REPLACEMENT_GUIDE} is missing")
            guide_payload = _read_regular_file(
                guide_path,
                "Audio pack editing guide",
                maximum=MAX_MANIFEST_BYTES,
            )
            _require(
                guide_payload == expected_guide
                and guide_row == {
                    "path": AUDIO_REPLACEMENT_GUIDE,
                    "sha256": _sha256(expected_guide),
                },
                "Audio replacement-pack editing guide changed",
            )
            validated_cue_map_payload: bytes | None = None
            if expected_cue_map is not None:
                cue_map_row = document.get("cue_map")
                cue_map_path = files.get(AUDIO_CUE_MAP)
                _require(cue_map_path is not None, f"{AUDIO_CUE_MAP} is missing")
                cue_map_payload = _read_regular_file(
                    cue_map_path,
                    "Audio cue authoring map",
                    maximum=MAX_AUDIO_CUE_MAP_BYTES,
                )
                _require(
                    cue_map_payload == expected_cue_map
                    and cue_map_row == {
                        "path": AUDIO_CUE_MAP,
                        "row_count": len(assets),
                        "schema": AUDIO_CUE_MAP_SCHEMA,
                        "sha256": _sha256(expected_cue_map),
                    },
                    "Audio replacement-pack authoring map changed",
                )
                validated_cue_map_payload = cue_map_payload
            allowed_files = {
                AUDIO_REPLACEMENT_MANIFEST,
                AUDIO_REPLACEMENT_GUIDE,
                *(relative for relative in declared_paths if relative in files),
            }
            if expected_cue_map is not None:
                allowed_files.add(AUDIO_CUE_MAP)
            unexpected = sorted(set(files) - allowed_files)
            if unexpected:
                raise AudioReplacementPackError(
                    "Audio replacement pack contains an undeclared or unknown file: "
                    + unexpected[0]
                )
            _require(
                replacements,
                "Add at least one authored WAV at a declared replacements/ path "
                "before importing this metadata template.",
            )

            member_records = [
                (
                    AUDIO_REPLACEMENT_MANIFEST,
                    len(manifest_payload),
                    _sha256(manifest_payload),
                ),
                (
                    AUDIO_REPLACEMENT_GUIDE,
                    len(guide_payload),
                    _sha256(guide_payload),
                ),
            ]
            if validated_cue_map_payload is not None:
                member_records.append((
                    AUDIO_CUE_MAP,
                    len(validated_cue_map_payload),
                    _sha256(validated_cue_map_payload),
                ))

            # Snapshot caller-controlled WAVs into one private temporary folder.
            # Both preflight and commit consume only these exact bytes; neither
            # returns a caller path, payload, member hash, or private source hash.
            with tempfile.TemporaryDirectory(
                prefix="2k5-audio-pack-snapshot-"
            ) as snapshot_name:
                snapshot_root = Path(snapshot_name)
                snapshot_rows: list[tuple[EditableAudioAsset, Path]] = []
                for ordinal, (asset, supplied, relative) in enumerate(
                    replacements, 1
                ):
                    payload = _read_regular_file(
                        supplied,
                        f"Replacement WAV for {asset.name}",
                        maximum=MAX_REPLACEMENT_WAV_BYTES,
                    )
                    snapshot_path = snapshot_root / f"{ordinal:04d}.wav"
                    _write_new(snapshot_path, payload)
                    snapshot_rows.append((asset, snapshot_path))
                    member_records.append((relative, len(payload), _sha256(payload)))

                yield _ValidatedAudioReplacementPack(
                    reported_source=reported_source,
                    schema=str(schema),
                    pack_kind=_PACK_KINDS[str(schema)],
                    member_digest=_pack_member_digest(member_records),
                    replacements=tuple(snapshot_rows),
                )

    def preflight_edited(
        self,
        source: Path,
        *,
        progress: PackProgress = _quiet_progress,
    ) -> AudioReplacementPackPreflightResult:
        """Fully validate and simulate one pack without editing the project."""

        with self._validated_edited(source, progress=progress) as validated:
            progress(
                "Preflighting every supplied audio WAV",
                0,
                len(validated.replacements),
            )
            batch = self.session.preflight_audio_batch(validated.replacements)
            token = self.session.issue_audio_pack_preflight_token(
                member_digest=validated.member_digest,
                schema=validated.schema,
            )
            changed = tuple(row for row in batch.rows if row.would_change)
            bounded = tuple(
                AudioReplacementPackChangedRow(
                    asset_id=row.asset_id,
                    label=_display_text(row.label, fallback=row.asset_id),
                    action=(
                        "restore_original"
                        if row.would_restore_original else "stage_replacement"
                    ),
                    affected_asset_ids=row.affected_asset_ids,
                )
                for row in changed[:MAX_PREFLIGHT_CHANGED_ROWS]
            )
            restore_count = sum(row.would_restore_original for row in batch.rows)
            affected_alias_count = max(
                0,
                len(batch.affected_asset_ids)
                - batch.unique_physical_change_count,
            )
            progress(
                "Audio replacement-pack preview ready",
                len(validated.replacements),
                len(validated.replacements),
            )
            return AudioReplacementPackPreflightResult(
                schema=validated.schema,
                pack_kind=validated.pack_kind,
                confirmation_token=token,
                supplied_count=len(batch.rows),
                would_change_count=len(changed),
                unique_physical_change_count=batch.unique_physical_change_count,
                already_current_count=len(batch.rows) - len(changed),
                would_restore_original_count=restore_count,
                unique_physical_restore_count=batch.unique_physical_restore_count,
                affected_alias_count=affected_alias_count,
                resulting_modified_count=len(batch.resulting_modified_asset_ids),
                changed_rows=bounded,
                omitted_changed_count=len(changed) - len(bounded),
            )

    def import_edited(
        self,
        source: Path,
        *,
        confirmation_token: str | None = None,
        progress: PackProgress = _quiet_progress,
    ) -> AudioReplacementPackImportResult:
        """Revalidate an edited pack and stage true changes atomically.

        A token returned by :meth:`preflight_edited` binds confirmation to the
        exact member contents, source, session, and monotonic mutation revision.
        Omitting the token is accepted only far enough to preserve detailed
        validation errors for older callers; it can never reach the mutation.
        """

        with self._validated_edited(source, progress=progress) as validated:
            progress(
                "Revalidating every supplied audio WAV",
                0,
                len(validated.replacements),
            )
            # This pass both computes the current comparison and repeats every
            # WAV shape/origin/containment/alias/staged-byte check. It produces
            # no edit or Undo entry.
            batch_preview = self.session.preflight_audio_batch(
                validated.replacements
            )
            if confirmation_token is None:
                if not any(row.would_change for row in batch_preview.rows):
                    raise ValidationError(
                        "Every supplied audio WAV already matches the current "
                        "project. Nothing was imported."
                    )
                raise ValidationError(
                    "Preview this audio replacement pack, review the proposed "
                    "changes, and confirm that preview before importing it."
                )
            self.session.verify_audio_pack_preflight_token(
                confirmation_token,
                member_digest=validated.member_digest,
                schema=validated.schema,
            )
            # The transaction reads and authorizes every private snapshot again;
            # no verdict or decoded payload from preflight is reused for commit.
            batch = self.session.replace_audio_batch(
                validated.replacements,
                label="Import audio replacement pack",
            )
            progress(
                "Audio replacement pack imported",
                len(validated.replacements),
                len(validated.replacements),
            )
            changed_ids = set(batch.changed_asset_ids)
            changed_supplied_count = sum(
                asset.asset_id in changed_ids
                for asset, _path in validated.replacements
            )
            return AudioReplacementPackImportResult(
                validated.reported_source,
                len(validated.replacements),
                changed_supplied_count,
                len(validated.replacements) - changed_supplied_count,
                len(batch.modified_asset_ids),
                batch,
            )


__all__ = [
    "AUDIO_CUE_MAP",
    "AUDIO_CUE_MAP_SCHEMA",
    "AUDIO_REPLACEMENT_GUIDE",
    "AUDIO_REPLACEMENT_MANIFEST",
    "AUDIO_REPLACEMENT_PACK_SCHEMA",
    "AUDIO_REPLACEMENT_PACK_V2_SCHEMA",
    "AUDIO_REPLACEMENT_PACK_V3_SCHEMA",
    "AUDIO_REPLACEMENT_PACK_V4_SCHEMA",
    "AudioReplacementPackError",
    "AudioReplacementPackChangedRow",
    "AudioReplacementPackExportResult",
    "AudioReplacementPackImportResult",
    "AudioReplacementPackPreflightResult",
    "AudioReplacementPackService",
    "complete_standalone_pack_path",
    "standalone_runtime_meaning_status",
    "EXPECTED_COMPLETE_STANDALONE_COUNT",
    "EXPECTED_EDITABLE_AUDIO_COUNT",
    "FAMILY_REVIEWED_MEANING_STATUS",
    "MAX_AUDIO_CUE_MAP_BYTES",
    "MAX_ARCHIVE_MEMBERS",
    "MAX_PREFLIGHT_CHANGED_ROWS",
    "MAX_SELECTED_AUDIO_COUNT",
]
