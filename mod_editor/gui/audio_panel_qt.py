"""Self-contained PyQt5 Audio panel for 2K5 Mod Studio.

The widget is deliberately isolated from the current application shell.  A
small :class:`AudioPanelHost` protocol makes it possible to mount the panel in
the existing PyQt5 window without importing project/session internals.  The included
catalog-backed host is useful for a standalone integration and keeps staged
user WAVs separate from retail-derived originals.

Playback uses an available Linux audio helper (``ffplay``, ``paplay``, or
``aplay``) without opening a terminal. Mod Studio keeps that process under its
own lifecycle control, so selecting another sound or source can stop it; if no
supported helper is installed, Play explains what to install instead of opening
an unowned external application. No second Qt binding or QtMultimedia package is
required. Complete streaming soundtrack/commentary banks can be exported as
exact raw ``.bin`` containers; their indexed ranges can also play/export as
WAV and accept source-safe fixed-slot replacement. Complete raw banks remain
export-only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Callable, Iterable, Protocol, Sequence, runtime_checkable

from mod_editor.core import audio_conform
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_catalog import (
    AudioReplacementMetadata,
    AudioReplacementPlan,
    EXPECTED_PLAYABLE_AUDIO_COUNT,
    MENU_BACK_SELECTOR,
    Nfl2k5AudioAsset,
    Nfl2k5AudioCatalog,
    Nfl2k5AudioService,
    Nfl2k5StreamingAudioBank,
    Nfl2k5StreamingAudioRange,
    PLAYABLE_AUDIO_FAMILIES,
    PLAYABLE_AUDIO_SCOPE_ID,
    STANDALONE_AUDIO_FAMILIES,
    STREAMING_AUDIO_FAMILIES,
)
from mod_editor.core.nfl2k5_universal_asset_index import (
    Nfl2k5UniversalAssetIndex,
    UniversalAssetRecord,
)
from mod_editor.studio.audio_bundle import (
    AudioBundleRow,
    bundle_row_for_asset,
    export_audio_bundle as publish_audio_bundle,
)
from mod_editor.studio.audio_replacement_pack import (
    FAMILY_REVIEWED_MEANING_STATUS,
    complete_standalone_pack_path,
    standalone_runtime_meaning_status,
)
from mod_editor.studio.audio_annotations import (
    AudioCueAnnotation,
    MAX_NOTE_CHARS,
    MAX_TITLE_CHARS,
)


ProgressSink = Callable[[str, int, int], None]
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_SHORTLIST_SIZE = 256
AUDIO_DETAIL_MIN_WIDTH = 320
AUDIO_DETAIL_SCROLL_MIN_HEIGHT = 120
AUDIO_DETAIL_LAYOUT_CONTRACT = "scrollable_pinned_actions"
AUDIO_TOOLBAR_TARGET_WIDTH = 930
AUDIO_TOOLBAR_LAYOUT_CONTRACT = "two_row_930"
AUDIO_PREVIEW_LIFECYCLE_CONTRACT = "selection_source_epoch_owned_process"
AUDIO_WAVEFORM_LIFECYCLE_CONTRACT = "explicit_read_only_session_wav"
AUDIO_MEDIA_INVALIDATION_CONTRACT = "selection_source_content_owned"
AUDIO_QUERY_LIFECYCLE_CONTRACT = "applied_token_debounce_guarded"
AUDIO_SHORTLIST_CLEAR_CONTRACT = "one_level_ordered_restore"
AUDIO_SOURCE_FAILURE_CONTRACT = "transactional_old_catalog_restore"
AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT = (
    "default_mixed_54421_standalone_then_streaming_ranges"
)
AUDIO_REPLACEMENT_PREFLIGHT_CONTRACT = (
    "fully_validated_read_only_preview_then_explicit_apply"
)
AUDIO_ANNOTATION_CONTRACT = "project_metadata_only_stable_logical_cue_id"
SOUNDTRACK_RANGE_COUNT = 136
SOUNDTRACK_WAV_PAYLOAD_BYTES = 1_309_146_208
RAW_AUDIO_CONTAINER_KINDS = ("BANK", "ABNK", "WBNK")
RAW_AUDIO_CONTAINER_COUNT = 9
MENU_BACK_MEANING_STATUS = "menu_back_route_runtime_unproved"
REVIEWED_LABEL_MEANING_STATUS = "reviewed_label_runtime_meaning_unproved"
PROVISIONAL_LABEL_MEANING_STATUS = "provisional_label_runtime_meaning_unproved"
STANDALONE_MEANING_STATUSES = (
    MENU_BACK_MEANING_STATUS,
    REVIEWED_LABEL_MEANING_STATUS,
    FAMILY_REVIEWED_MEANING_STATUS,
    PROVISIONAL_LABEL_MEANING_STATUS,
)


def _literal_tooltip(value: str) -> str:
    """Render untrusted text literally inside Qt's rich-text-only tooltip API."""

    escaped = html.escape(value, quote=True).replace("\n", "<br/>")
    return f"<qt>{escaped}</qt>"


_FAMILY_COUNTS = {
    PLAYABLE_AUDIO_SCOPE_ID: {
        "frontend_ui": 36,
        "field_crowd_player": 13,
        "team_crowd": 680,
        "crib_minigames": 121,
        "music": 136,
        "commentary": 52_940,
        "stadium": 9,
        "presentation": 482,
        "ambient": 4,
    },
    "standalone": {
        "frontend_ui": 36,
        "field_crowd_player": 13,
        "team_crowd": 680,
        "crib_minigames": 121,
    },
    "streaming": {
        "music": 5,
        "commentary": 3,
        "stadium": 1,
        "presentation": 5,
        "ambient": 3,
    },
    "streaming_ranges": {
        "music": 136,
        "commentary": 52_940,
        "stadium": 9,
        "presentation": 482,
        "ambient": 4,
    },
}


@dataclass(frozen=True, slots=True)
class AudioPage:
    """One deterministic browser page returned by an :class:`AudioPanelHost`."""

    assets: tuple[
        Nfl2k5AudioAsset
        | Nfl2k5StreamingAudioBank
        | Nfl2k5StreamingAudioRange
        | UniversalAssetRecord,
        ...,
    ]
    total: int
    offset: int
    limit: int

    @property
    def first_number(self) -> int:
        return self.offset + 1 if self.assets else 0

    @property
    def last_number(self) -> int:
        return self.offset + len(self.assets)

    @property
    def has_previous(self) -> bool:
        return self.offset > 0

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.assets) < self.total


@runtime_checkable
class AudioPanelHost(Protocol):
    """Narrow host contract consumed by :class:`AudioPanel`.

    Disk operations receive a progress callback and are run on a Qt worker.
    The catalog query is metadata-only and is intentionally synchronous.
    """

    @property
    def source_ready(self) -> bool: ...

    @property
    def modified_audio_asset_ids(self) -> Iterable[str]: ...

    def audio_affected_asset_ids(self, asset_id: str) -> tuple[str, ...]: ...

    def audio_complete_pack_path(self, asset_id: str) -> str | None: ...

    def browse_audio(
        self,
        *,
        search: str,
        status: str | None,
        offset: int,
        limit: int,
        scope: str = "standalone",
        family: str | None = None,
        meaning_status: str | None = None,
        labeled_only: bool = False,
    ) -> AudioPage: ...

    def prepare_audio(
        self, asset_id: str, progress: ProgressSink
    ) -> Path: ...

    def export_audio(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_audio_bank(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_audio_range(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_audio_range_wav(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_audio_bundle(
        self,
        *,
        search: str,
        status: str | None,
        scope: str,
        family: str | None,
        meaning_status: str | None = None,
        labeled_only: bool = False,
        destination: Path,
        output_format: str,
        bundle_name: str,
        progress: ProgressSink,
    ) -> Path: ...

    def export_audio_selection(
        self,
        asset_ids: Sequence[str],
        destination: Path,
        *,
        bundle_name: str,
        progress: ProgressSink,
    ) -> Path: ...

    def browse_resources(
        self,
        *,
        search: str,
        kind: str | None,
        offset: int,
        limit: int,
        progress: ProgressSink,
    ) -> object: ...

    def export_resource(
        self,
        asset: UniversalAssetRecord | str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def replace_audio(
        self, asset_id: str, supplied_wav: Path, progress: ProgressSink
    ) -> object: ...

    def revert_audio(self, asset_id: str, progress: ProgressSink) -> object: ...

def audio_search_text(asset: Nfl2k5AudioAsset) -> str:
    """Return the product-facing metadata searched by the panel."""

    fields = [
        asset.name,
        asset.asset_id,
        asset.outer_id,
        asset.edit_status,
        asset.alias_status,
        asset.ownership_status,
        asset.family_id,
        asset.family_label,
        asset.container_label,
        asset.format_label,
        str(asset.outer_index),
        str(asset.chunk_index),
        str(asset.sample_rate),
        f"{asset.channels} channel",
        "stereo" if asset.channels == 2 else "mono" if asset.channels == 1 else "",
    ]
    if asset.family_reviewed_label is not None:
        fields.append(asset.family_reviewed_label)
    return " ".join(fields).casefold()


def filter_audio_assets(
    assets: Iterable[Nfl2k5AudioAsset],
    *,
    search: str = "",
    status: str | None = None,
    family: str | None = None,
) -> tuple[Nfl2k5AudioAsset, ...]:
    """Filter the complete catalog without touching Qt or audio payloads."""

    if status not in (None, "Editable", "Export-only"):
        raise ValidationError(
            "Audio status filter must be All, Editable, or Export-only"
        )
    valid_families = {family_id for family_id, _label in STANDALONE_AUDIO_FAMILIES}
    if family is not None and family not in valid_families:
        raise ValidationError("Unknown standalone-audio family filter")
    words = tuple(word for word in search.casefold().split() if word)
    rows: list[Nfl2k5AudioAsset] = []
    for asset in assets:
        if status is not None and asset.edit_status != status:
            continue
        if family is not None and asset.family_id != family:
            continue
        if words:
            haystack = audio_search_text(asset)
            if not all(word in haystack for word in words):
                continue
        rows.append(asset)
    return tuple(rows)


def audio_bank_search_text(asset: Nfl2k5StreamingAudioBank) -> str:
    """Return searchable metadata for one opaque external bank."""

    return " ".join((
        asset.name,
        asset.asset_id,
        asset.external_filename,
        asset.outer_id,
        asset.external_outer_id,
        asset.family_id,
        asset.family_label,
        asset.role_class,
        asset.container_label,
        asset.format_label,
        asset.edit_status,
        asset.replacement_status,
        asset.alias_status,
        asset.ownership_status,
        str(asset.outer_index),
        str(asset.chunk_index),
        str(asset.external_outer_index),
        str(asset.entry_count),
        str(asset.sample_rate),
        "raw bin aggregate undecoded edit individual indexed ranges",
    )).casefold()


def filter_audio_banks(
    assets: Iterable[Nfl2k5StreamingAudioBank],
    *,
    search: str = "",
    status: str | None = None,
    family: str | None = None,
) -> tuple[Nfl2k5StreamingAudioBank, ...]:
    """Filter streaming banks without decoding or reading bank payloads."""

    if status not in (None, "Editable", "Export-only"):
        raise ValidationError(
            "Audio status filter must be All, Editable, or Export-only"
        )
    valid_families = {family_id for family_id, _label in STREAMING_AUDIO_FAMILIES}
    if family is not None and family not in valid_families:
        raise ValidationError("Unknown streaming-audio family filter")
    words = tuple(word for word in search.casefold().split() if word)
    rows: list[Nfl2k5StreamingAudioBank] = []
    for asset in assets:
        if status is not None and asset.edit_status != status:
            continue
        if family is not None and asset.family_id != family:
            continue
        if words:
            haystack = audio_bank_search_text(asset)
            if not all(word in haystack for word in words):
                continue
        rows.append(asset)
    return tuple(rows)


def audio_range_search_text(asset: Nfl2k5StreamingAudioRange) -> str:
    """Return searchable metadata for one decoded Xbox IMA bank range."""

    return " ".join((
        asset.name,
        asset.asset_id,
        asset.external_filename,
        asset.outer_id,
        asset.family_id,
        asset.family_label,
        asset.role_class,
        asset.container_label,
        asset.format_label,
        asset.edit_status,
        asset.replacement_status,
        asset.alias_status,
        asset.ownership_status,
        str(asset.outer_index),
        str(asset.chunk_index),
        str(asset.external_outer_index),
        str(asset.range_index),
        str(asset.start),
        str(asset.end),
        f"0x{asset.start:x}",
        f"0x{asset.end:x}",
        str(asset.stored_size),
        str(asset.sample_rate),
        "play playable wav pcm16 xbox ima adpcm decoded raw range bin cue "
        "replace replacement editable fixed slot shared alias",
    )).casefold()


def filter_audio_ranges(
    assets: Iterable[Nfl2k5StreamingAudioRange],
    *,
    search: str = "",
    status: str | None = None,
    family: str | None = None,
) -> tuple[Nfl2k5StreamingAudioRange, ...]:
    """Filter indexed streaming ranges without reading their retail bytes."""

    if status not in (None, "Editable", "Export-only"):
        raise ValidationError(
            "Audio status filter must be All, Editable, or Export-only"
        )
    valid_families = {family_id for family_id, _label in STREAMING_AUDIO_FAMILIES}
    if family is not None and family not in valid_families:
        raise ValidationError("Unknown streaming-audio family filter")
    words = tuple(word for word in search.casefold().split() if word)
    rows: list[Nfl2k5StreamingAudioRange] = []
    for asset in assets:
        if status is not None and asset.edit_status != status:
            continue
        if family is not None and asset.family_id != family:
            continue
        if words:
            haystack = audio_range_search_text(asset)
            if not all(word in haystack for word in words):
                continue
        rows.append(asset)
    return tuple(rows)


def paginate_audio_assets(
    assets: Iterable[
        Nfl2k5AudioAsset | Nfl2k5StreamingAudioBank | Nfl2k5StreamingAudioRange
    ],
    *,
    offset: int,
    limit: int,
) -> AudioPage:
    """Create a bounded page and clamp a stale offset after filters change."""

    rows = tuple(assets)
    if type(offset) is not int or offset < 0:
        raise ValidationError("Audio page offset cannot be negative")
    if type(limit) is not int or not 1 <= limit <= MAX_SHORTLIST_SIZE:
        raise ValidationError(
            f"Audio page size must be between 1 and {MAX_SHORTLIST_SIZE}"
        )
    if rows and offset >= len(rows):
        offset = ((len(rows) - 1) // limit) * limit
    elif not rows:
        offset = 0
    return AudioPage(rows[offset:offset + limit], len(rows), offset, limit)


def audio_player_command(
    path: Path,
    resolver: Callable[[str], str | None] = shutil.which,
) -> tuple[str, tuple[str, ...]] | None:
    """Choose a controllable no-terminal Linux WAV player, or return ``None``."""

    candidates = (
        ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "error", str(path))),
        ("paplay", (str(path),)),
        ("aplay", ("-q", str(path))),
    )
    for name, arguments in candidates:
        program = resolver(name)
        if program is not None:
            return program, arguments
    return None


def _copy_atomic(source: Path, destination: Path, *, replace: bool) -> Path:
    """Copy a user-authored WAV atomically without following links."""

    try:
        source_info = source.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"WAV is missing: {source}") from exc
    if not stat.S_ISREG(source_info.st_mode) or stat.S_ISLNK(source_info.st_mode):
        raise ValidationError("WAV must be a regular, non-link file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination) and not replace:
        raise ValidationError(f"A file already exists there: {destination}")
    if destination.is_symlink():
        raise ValidationError(f"Refusing to replace a symbolic link: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    output_fd: int | None = None
    try:
        opened = os.fstat(source_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (source_info.st_dev, source_info.st_ino, source_info.st_size)
        ):
            raise ValidationError("WAV changed before its read-only open")
        output_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        remaining = opened.st_size
        while remaining:
            block = os.read(source_fd, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("WAV shortened while it was copied")
            view = memoryview(block)
            while view:
                written = os.write(output_fd, view)
                if written <= 0:
                    raise OSError("short WAV staging write")
                view = view[written:]
            remaining -= len(block)
        if os.read(source_fd, 1):
            raise ValidationError("WAV grew while it was copied")
        os.fsync(output_fd)
        os.close(output_fd)
        output_fd = None
        if not replace and os.path.lexists(destination):
            raise ValidationError(f"A file appeared at the destination: {destination}")
        os.replace(temporary, destination)
        return destination.resolve(strict=True)
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(source_fd)
        temporary.unlink(missing_ok=True)


def _replace_atomic_bytes(destination: Path, payload: bytes) -> Path:
    """Stage authorized user bytes without reopening the caller's path."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = destination.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and (
        not stat.S_ISREG(existing.st_mode) or stat.S_ISLNK(existing.st_mode)
    ):
        raise ValidationError(
            "The audio replacement destination is not a regular private file"
        )
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{hashlib.sha256(payload).hexdigest()[:12]}.tmp"
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short audio replacement write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, destination)
        return destination.resolve(strict=True)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


class CatalogAudioPanelHost:
    """Standalone host backed by the private catalog/service.

    Only user-authored WAVs enter ``replacement_root``.  Retail-derived WAVs
    remain in the source cache managed by :class:`Nfl2k5AudioService`.
    """

    source_ready = True

    def __init__(
        self,
        catalog: Nfl2k5AudioCatalog,
        service: Nfl2k5AudioService,
        replacement_root: Path,
        universal_index: Nfl2k5UniversalAssetIndex | None = None,
    ) -> None:
        if catalog.cache.root != service.cache.root:
            raise ValidationError("Audio catalog and service use different source caches")
        self.catalog = catalog
        self.service = service
        self.replacement_root = replacement_root.expanduser()
        self.universal_index = universal_index
        # State is keyed by the reviewed physical slot, not the clicked alias.
        self._replacements: dict[str, Path] = {}
        self._replacement_owners: dict[str, tuple[str, ...]] = {}

    @property
    def modified_audio_asset_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            asset_id
            for owners in self._replacement_owners.values()
            for asset_id in owners
        }))

    def audio_affected_asset_ids(self, asset_id: str) -> tuple[str, ...]:
        return self.service.audio_affected_asset_ids(asset_id)

    def audio_complete_pack_path(self, asset_id: str) -> str | None:
        """Return the public v4 all-850 path without exposing a selector."""

        return complete_standalone_pack_path(self.catalog, asset_id)

    def _resolve_playable_audio(
        self, asset_id: str
    ) -> Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange:
        return self.service.resolve_playable_audio(asset_id)

    def browse_resources(
        self,
        *,
        search: str,
        kind: str | None,
        offset: int,
        limit: int,
        progress: ProgressSink,
    ) -> object:
        if self.universal_index is None:
            raise ValidationError(
                "The universal source index is unavailable for raw bank containers."
            )
        progress("Reading raw bank container metadata", 0, 1)
        rows = self.universal_index.query(
            search=search, kind=kind, offset=offset, limit=limit
        )
        progress("Raw bank container metadata ready", 1, 1)
        return rows, self.universal_index.asset_count

    def export_resource(
        self,
        asset: UniversalAssetRecord | str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path:
        if self.universal_index is None:
            raise ValidationError(
                "The universal source index is unavailable for raw bank containers."
            )
        progress("Exporting exact raw bank container", 0, 1)
        path = self.universal_index.export_raw(asset, destination)
        progress("Raw bank container exported", 1, 1)
        return path

    def browse_audio(
        self,
        *,
        search: str,
        status: str | None,
        offset: int,
        limit: int,
        scope: str = "standalone",
        family: str | None = None,
        meaning_status: str | None = None,
        labeled_only: bool = False,
    ) -> AudioPage:
        rows = self._matching_audio_rows(
            search=search,
            status=status,
            scope=scope,
            family=family,
            meaning_status=meaning_status,
        )
        if labeled_only:
            rows = ()
        return paginate_audio_assets(rows, offset=offset, limit=limit)

    def _matching_audio_rows(
        self,
        *,
        search: str,
        status: str | None,
        scope: str,
        family: str | None,
        meaning_status: str | None = None,
    ) -> tuple[
        Nfl2k5AudioAsset | Nfl2k5StreamingAudioBank
        | Nfl2k5StreamingAudioRange,
        ...,
    ]:
        if status not in (None, "Editable", "Export-only", "Modified"):
            raise ValidationError(
                "Audio status must be All, Modified, Editable, or Export-only"
            )
        if meaning_status not in (None, *STANDALONE_MEANING_STATUSES):
            raise ValidationError("Audio meaning-confidence filter is invalid")
        if meaning_status is not None and scope != "standalone":
            raise ValidationError(
                "Meaning confidence applies only to standalone audio sounds"
            )
        if scope == PLAYABLE_AUDIO_SCOPE_ID:
            playable_families = {
                family_id for family_id, _label in PLAYABLE_AUDIO_FAMILIES
            }
            if family is not None and family not in playable_families:
                raise ValidationError("Unknown playable-audio family filter")
        modified = set(self.modified_audio_asset_ids)
        if scope == PLAYABLE_AUDIO_SCOPE_ID:
            standalone_rows = filter_audio_assets(
                self.catalog.assets,
                search=search,
                status=None if status == "Modified" else status,
                family=family,
            ) if family in (
                None,
                *(family_id for family_id, _label in STANDALONE_AUDIO_FAMILIES),
            ) else ()
            streaming_rows = filter_audio_ranges(
                self.catalog.streaming_ranges,
                search=search,
                status=None if status == "Modified" else status,
                family=family,
            ) if family in (
                None,
                *(family_id for family_id, _label in STREAMING_AUDIO_FAMILIES),
            ) else ()
            rows = standalone_rows + streaming_rows
            if status == "Modified":
                rows = tuple(asset for asset in rows if asset.asset_id in modified)
        elif scope == "standalone":
            rows = filter_audio_assets(
                self.catalog.assets,
                search=search,
                status=None if status == "Modified" else status,
                family=family,
            )
            if status == "Modified":
                rows = tuple(asset for asset in rows if asset.asset_id in modified)
            if meaning_status is not None:
                rows = tuple(
                    asset for asset in rows
                    if standalone_runtime_meaning_status(asset) == meaning_status
                )
        elif scope == "streaming":
            rows = () if status == "Modified" else filter_audio_banks(
                self.catalog.streaming_banks, search=search, status=status, family=family
            )
        elif scope == "streaming_ranges":
            rows = filter_audio_ranges(
                self.catalog.streaming_ranges,
                search=search,
                status=None if status == "Modified" else status,
                family=family,
            )
            if status == "Modified":
                rows = tuple(asset for asset in rows if asset.asset_id in modified)
        else:
            raise ValidationError(
                "Audio scope must be all playable sounds, standalone sounds, "
                "streaming banks, or indexed streaming ranges"
            )
        return rows

    def prepare_audio(self, asset_id: str, progress: ProgressSink) -> Path:
        asset = self._resolve_playable_audio(asset_id)
        progress("Preparing WAV", 0, 1)
        state_id = (
            self.service.audio_physical_id(asset) if asset.editable else asset.asset_id
        )
        replacement = self._replacements.get(state_id) if asset.editable else None
        if replacement is None:
            result = (
                self.service.audio_playback_path(asset)
                if asset.editable else self.service.playback_path(asset)
            )
        else:
            snapshot = self.service.read_replacement_snapshot(asset, replacement)
            issued = self.service.authorize_replacement_snapshot(asset, snapshot)
            if issued.wav_sha256 != snapshot.metadata.wav_sha256:
                raise ValidationError(
                    f"The staged WAV for {asset.name} changed outside Mod Studio"
                )
            result = replacement
        progress("WAV ready", 1, 1)
        return result

    def export_audio(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        asset = self._resolve_playable_audio(asset_id)
        progress("Exporting WAV", 0, 1)
        replacement = (
            self._replacements.get(self.service.audio_physical_id(asset))
            if asset.editable else None
        )
        if replacement is None:
            if isinstance(asset, Nfl2k5StreamingAudioRange):
                result = self.service.export_streaming_range_wav(asset, destination)
            else:
                result = self.service.export_wav(asset, destination)
        else:
            current = self.prepare_audio(asset.asset_id, lambda *_args: None)
            result = _copy_atomic(current, destination.expanduser(), replace=False)
        progress("WAV exported", 1, 1)
        return result

    def export_audio_bank(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        bank = self.catalog.get_streaming_bank(asset_id)
        result = self.service.export_streaming_bank(
            bank,
            destination,
            progress=lambda completed, total: progress(
                "Exporting raw streaming bank", completed, total
            ),
        )
        progress("Raw streaming bank exported", bank.external_size, bank.external_size)
        return result

    def export_audio_range(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        item = self.catalog.get_streaming_range(asset_id)
        result = self.service.export_streaming_range(
            item,
            destination,
            progress=lambda completed, total: progress(
                "Exporting raw streaming range", completed, total
            ),
        )
        progress("Raw streaming range exported", item.stored_size, item.stored_size)
        return result

    def export_audio_range_wav(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        item = self.catalog.get_streaming_range(asset_id)
        result = self.export_audio(asset_id, destination, progress)
        progress("Streaming-range WAV exported", item.stored_size, item.stored_size)
        return result

    def export_audio_bundle(
        self,
        *,
        search: str,
        status: str | None,
        scope: str,
        family: str | None,
        meaning_status: str | None = None,
        labeled_only: bool = False,
        destination: Path,
        output_format: str,
        bundle_name: str,
        progress: ProgressSink,
    ) -> Path:
        if scope == PLAYABLE_AUDIO_SCOPE_ID and output_format != "wav":
            raise ValidationError(
                "All Playable Audio exports as WAV. Raw BIN export is available "
                "only from Streaming Banks or Playable Streaming Ranges."
            )
        rows = self._matching_audio_rows(
            search=search,
            status=status,
            scope=scope,
            family=family,
            meaning_status=meaning_status,
        )
        if labeled_only:
            rows = ()
        if not 1 <= len(rows) <= 256:
            raise ValidationError(
                "Export matching audio requires 1–256 rows. Narrow the current "
                "search, family, or status filters."
            )
        assets = {asset.asset_id: asset for asset in rows}
        bundle_rows = tuple(
            bundle_row_for_asset(
                asset,
                output_format=output_format,
                content_origin=(
                    "user_replacement"
                    if (
                        isinstance(asset, Nfl2k5AudioAsset)
                        or (
                            isinstance(asset, Nfl2k5StreamingAudioRange)
                            and output_format == "wav"
                        )
                    ) and asset.asset_id in set(self.modified_audio_asset_ids)
                    else "retail_derived"
                ),
            )
            for asset in rows
        )

        def write_payload(row: AudioBundleRow, output: Path) -> Path:
            asset = assets[row.stable_id]
            if isinstance(asset, Nfl2k5AudioAsset):
                return self.export_audio(
                    asset.asset_id, output, lambda *_args: None
                )
            if isinstance(asset, Nfl2k5StreamingAudioBank):
                return self.export_audio_bank(
                    asset.asset_id, output, lambda *_args: None
                )
            if output_format == "bin":
                return self.export_audio_range(
                    asset.asset_id, output, lambda *_args: None
                )
            return self.export_audio_range_wav(
                asset.asset_id, output, lambda *_args: None
            )

        return publish_audio_bundle(
            bundle_rows,
            destination,
            bundle_name=bundle_name,
            payload_writer=write_payload,
            progress=lambda completed, total: progress(
                "Exporting matching NFL 2K5 audio", completed, total
            ),
        )

    def export_audio_selection(
        self,
        asset_ids: Sequence[str],
        destination: Path,
        *,
        bundle_name: str,
        progress: ProgressSink,
    ) -> Path:
        """Export an ordered session shortlist of playable sounds as WAVs."""

        if isinstance(asset_ids, (str, bytes)):
            raise ValidationError("Choose audio sounds before exporting a shortlist.")
        selected_ids = tuple(asset_ids)
        if not 1 <= len(selected_ids) <= 256:
            raise ValidationError(
                "An audio shortlist must contain between 1 and 256 sounds."
            )
        if any(not isinstance(asset_id, str) or not asset_id for asset_id in selected_ids):
            raise ValidationError("Every shortlisted sound must have a valid asset ID.")
        if len(set(selected_ids)) != len(selected_ids):
            raise ValidationError("An audio shortlist cannot contain duplicate sounds.")

        standalone = {asset.asset_id: asset for asset in self.catalog.assets}
        ranges = {item.asset_id: item for item in self.catalog.streaming_ranges}
        banks = {bank.asset_id for bank in self.catalog.streaming_banks}
        assets: list[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange] = []
        for asset_id in selected_ids:
            if asset_id in banks:
                raise ValidationError(
                    "A complete streaming bank is not one playable sound and cannot "
                    "enter an audio shortlist. Choose its indexed ranges instead."
                )
            asset = standalone.get(asset_id)
            if asset is None:
                asset = ranges.get(asset_id)
            if asset is None:
                raise ValidationError(f"Unknown shortlisted audio asset: {asset_id}")
            assets.append(asset)

        by_id = {asset.asset_id: asset for asset in assets}
        bundle_rows = tuple(
            bundle_row_for_asset(
                asset,
                output_format="wav",
                content_origin=(
                    "user_replacement"
                    if asset.asset_id in set(self.modified_audio_asset_ids)
                    else "retail_derived"
                ),
            )
            for asset in assets
        )

        def write_payload(row: AudioBundleRow, output: Path) -> Path:
            asset = by_id[row.stable_id]
            if isinstance(asset, Nfl2k5AudioAsset):
                return self.export_audio(asset.asset_id, output, lambda *_args: None)
            return self.export_audio_range_wav(
                asset.asset_id, output, lambda *_args: None
            )

        return publish_audio_bundle(
            bundle_rows,
            destination,
            bundle_name=bundle_name,
            payload_writer=write_payload,
            progress=lambda completed, total: progress(
                "Exporting selected NFL 2K5 audio", completed, total
            ),
        )

    def replace_audio(
        self, asset_id: str, supplied_wav: Path, progress: ProgressSink
    ) -> AudioReplacementMetadata:
        asset = self.service.resolve_editable_audio(asset_id)
        progress("Checking replacement WAV", 0, 2)
        snapshot = self.service.read_replacement_snapshot(asset, supplied_wav)
        original = self.service.audio_original_path(asset).read_bytes()
        if snapshot.wav_bytes == original:
            self.revert_audio(asset.asset_id, progress)
            return snapshot.metadata
        issued = self.service.authorize_replacement_snapshot(asset, snapshot)
        progress("Staging replacement WAV", 1, 2)
        state_id = self.service.audio_physical_id(asset)
        destination = self.replacement_root / (
            hashlib.sha256(state_id.encode("utf-8")).hexdigest() + ".wav"
        )
        _replace_atomic_bytes(destination, issued.wav_bytes)
        # Authorize the exact staged snapshot before publishing live state.
        staged_snapshot = self.service.read_replacement_snapshot(asset, destination)
        staged_issued = self.service.authorize_replacement_snapshot(
            asset, staged_snapshot
        )
        if staged_issued.wav_sha256 != issued.wav_sha256:
            destination.unlink(missing_ok=True)
            raise ValidationError("The staged audio changed during replacement")
        self._replacements[state_id] = destination
        self._replacement_owners[state_id] = self.service.audio_affected_asset_ids(
            asset
        )
        progress("Replacement staged", 2, 2)
        return staged_snapshot.metadata

    def revert_audio(self, asset_id: str, progress: ProgressSink) -> bool:
        asset = self.service.resolve_editable_audio(asset_id)
        state_id = self.service.audio_physical_id(asset)
        progress("Reverting audio", 0, 1)
        path = self._replacements.get(state_id)
        if path is not None:
            # Refuse to erase an externally changed file masquerading as the
            # authorized user replacement.
            self.prepare_audio(asset.asset_id, lambda *_args: None)
            try:
                info = path.lstat()
            except FileNotFoundError:
                info = None
            if info is not None:
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise ValidationError("Staged audio replacement is no longer a regular file")
                path.unlink()
            self._replacements.pop(state_id, None)
            self._replacement_owners.pop(state_id, None)
        progress("Original audio restored", 1, 1)
        return path is not None

    def create_build_plan(
        self, recipe_output: Path, *, purpose: str
    ) -> AudioReplacementPlan:
        """Return the existing provider plan for the one staged replacement."""

        if not self._replacements:
            raise ValidationError("No audio replacement is staged")
        if len(self._replacements) != 1:
            raise ValidationError("The fixed audio provider accepts one replacement")
        state_id, wav = next(iter(self._replacements.items()))
        owners = self._replacement_owners.get(state_id, ())
        if len(owners) != 1 or owners[0].startswith("nfl2k5.audio.ausb."):
            raise ValidationError(
                "This standalone plan helper does not build streaming ranges; use "
                "the main Mod Studio Build action."
            )
        asset_id = owners[0]
        return self.service.create_replacement_plan(
            asset_id, wav, recipe_output, purpose=purpose
        )


from PyQt5.QtCore import (
    QObject,
    QProcess,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtWidgets import (
    QAbstractScrollArea,
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from mod_editor.gui.audio_waveform_qt import (
    AudioWaveformPreview,
    WaveformCancelled,
    WaveformEnvelope,
    WaveformRequest,
    read_pcm16_waveform,
)


PYQT5_AVAILABLE = True


if PYQT5_AVAILABLE:

    class _TaskSignals(QObject):
        result = pyqtSignal(object)
        error = pyqtSignal(str)
        progress = pyqtSignal(str, int, int)
        finished = pyqtSignal()


    class _Task(QRunnable):
        def __init__(self, operation: Callable[[ProgressSink], object]) -> None:
            super().__init__()
            self.operation = operation
            self.signals = _TaskSignals()
            self.setAutoDelete(False)

        def run(self) -> None:
            try:
                result = self.operation(self.signals.progress.emit)
            except BaseException as exc:
                self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
            else:
                self.signals.result.emit(result)
            finally:
                self.signals.finished.emit()


    class _WavDropZone(QFrame):
        wav_dropped = pyqtSignal(object)

        def __init__(self) -> None:
            super().__init__()
            self._accepting = False
            self.setAcceptDrops(True)
            self.setObjectName("audioDropZone")
            self.setMinimumHeight(86)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 12, 16, 12)
            self.title = QLabel("Drop replacement audio here")
            self.title.setObjectName("audioDropTitle")
            self.hint = QLabel("Select an Editable standalone sound first")
            self.hint.setWordWrap(True)
            self.hint.setObjectName("audioMuted")
            layout.addWidget(self.title)
            layout.addWidget(self.hint)

        def set_accepting(self, accepting: bool, hint: str) -> None:
            self._accepting = accepting
            self.setEnabled(accepting)
            self.hint.setText(hint)

        def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
            mime = event.mimeData()  # type: ignore[attr-defined]
            urls = mime.urls() if mime.hasUrls() else []
            if not self._accepting:
                event.ignore()  # type: ignore[attr-defined]
                return
            if urls:
                # Accept the drag so an unusable drop can explain itself with
                # a plain message instead of silently bouncing off the zone.
                event.acceptProposedAction()  # type: ignore[attr-defined]
            else:
                event.ignore()  # type: ignore[attr-defined]

        def dropEvent(self, event: object) -> None:  # type: ignore[override]
            urls = event.mimeData().urls()  # type: ignore[attr-defined]
            if len(urls) != 1:
                QMessageBox.information(
                    self,
                    "That drop can't be used yet",
                    "Drop one audio file at a time. Pick the single sound you "
                    "want to use and drop it here again.",
                )
                event.ignore()  # type: ignore[attr-defined]
                return
            url = urls[0]
            if not url.isLocalFile() or url.host():
                QMessageBox.information(
                    self,
                    "That drop can't be used yet",
                    "That drop is a link or a web address, not a file on this "
                    "computer. Save or download the audio first, then drop the "
                    "real file here.",
                )
                event.ignore()  # type: ignore[attr-defined]
                return
            path = Path(url.toLocalFile())
            if not audio_conform.is_supported_suffix(str(path)):
                QMessageBox.information(
                    self,
                    "That drop can't be used yet",
                    "Drop one local audio file — WAV, MP3, FLAC, OGG, M4A and "
                    "similar. It is converted to this sound's exact shape for "
                    "you.",
                )
                event.ignore()  # type: ignore[attr-defined]
                return
            self.wav_dropped.emit(path)
            event.acceptProposedAction()  # type: ignore[attr-defined]


    class AudioPanel(QWidget):
        """Searchable browser/editor for standalone and streaming audio."""

        error_raised = pyqtSignal(str)
        operation_state_changed = pyqtSignal(bool)
        audio_modified = pyqtSignal(str)
        audio_reverted = pyqtSignal(str)
        audio_batch_imported = pyqtSignal(int)
        audio_annotation_changed = pyqtSignal(str)

        def __init__(
            self,
            host: AudioPanelHost,
            *,
            page_size: int = DEFAULT_PAGE_SIZE,
            operation_admission: Callable[[], str | None] | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            if not isinstance(host, AudioPanelHost):
                raise TypeError("Audio panel host does not implement AudioPanelHost")
            if not 1 <= page_size <= MAX_PAGE_SIZE:
                raise ValueError(f"page_size must be 1..{MAX_PAGE_SIZE}")
            self.host = host
            self._annotation_capable = bool(
                hasattr(host, "labeled_audio_asset_ids")
                and all(
                    callable(getattr(host, name, None))
                    for name in (
                        "audio_annotation",
                        "set_audio_annotation",
                        "clear_audio_annotation",
                    )
                )
            )
            self._operation_admission = operation_admission
            self.page_size = page_size
            self.offset = 0
            self.page = AudioPage((), 0, 0, page_size)
            self.selected_asset_id: str | None = None
            self._audio_shortlist: dict[
                str, Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange
            ] = {}
            self._cleared_audio_shortlist: tuple[
                tuple[str, Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange], ...
            ] = ()
            self._affected_owner_cache: dict[str, tuple[str, ...]] = {}
            self._affected_owner_errors: dict[str, str] = {}
            self._raw_audio_containers: tuple[UniversalAssetRecord, ...] | None = None
            self._shortlist_reviewing = False
            self._catalog_offset_before_review = 0
            self._catalog_selection_before_review: str | None = None
            self._busy = False
            self._refresh_after_busy = False
            self._post_operation_continuation: Callable[[], None] | None = None
            self._tasks: set[_Task] = set()
            self._pool = QThreadPool(self)
            self._audio_process = QProcess(self)
            self._preview_epoch = 0
            self._preview_request: tuple[int, str] | None = None
            self._prepared_preview: (
                tuple[tuple[int, str], str, tuple[str, ...]] | None
            ) = None
            self._playing_preview_request: tuple[int, str] | None = None
            self._waveform_generation = 0
            self._waveform_request: WaveformRequest | None = None
            self._waveform_selected_asset_id: str | None = None
            self._catalog_source_epoch = 0
            self._applied_query_token: (
                tuple[
                    int, str, str, str | None, str | None, str | None, bool
                ] | None
            ) = None
            self._source_change_query_was_current: bool | None = None
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.setInterval(220)
            self._search_timer.timeout.connect(self._filters_changed)
            self._annotation_loading = False
            self._annotation_drafts: dict[str, tuple[str, str]] = {}
            self.setObjectName("audioPanel")
            self._build_ui()
            self._apply_style()
            self._connect()
            if self.host.source_ready:
                self.refresh()
            else:
                self.count_label.setText("Load your NFL 2K5 XISO")
                self._show_asset(None)

        @property
        def operation_in_progress(self) -> bool:
            """Whether this panel owns its one background-operation lane."""

            return self._busy

        def _build_ui(self) -> None:
            root = QVBoxLayout(self)
            root.setContentsMargins(24, 22, 24, 22)
            root.setSpacing(14)
            header = QHBoxLayout()
            titles = QVBoxLayout()
            title = QLabel("Audio")
            title.setObjectName("audioTitle")
            self.subtitle_label = QLabel(
                "Browse and export every indexed sound; play cues and ranges; "
                "replace supported standalone and streaming-range WAVs."
            )
            self.subtitle_label.setObjectName("audioMuted")
            self.subtitle_label.setWordWrap(True)
            self.subtitle_label.setToolTip(
                "850 standalone cues, 17 complete streaming banks, and 53,571 "
                "playable indexed ranges covering soundtrack, commentary, stadium, "
                "and presentation audio."
            )
            titles.addWidget(title)
            titles.addWidget(self.subtitle_label)
            self.count_label = QLabel("Loading catalog…")
            self.count_label.setObjectName("audioCountPill")
            header.addLayout(titles, 1)
            header.addWidget(self.count_label, 0, Qt.AlignTop | Qt.AlignRight)
            root.addLayout(header)

            self.filters_layout = QGridLayout()
            self.filters_layout.setHorizontalSpacing(9)
            self.filters_layout.setVerticalSpacing(8)
            self.search = QLineEdit()
            self.search.setPlaceholderText(
                "Search cue, bank, range, soundtrack, commentary, crowd, format, ID…"
            )
            self.search.setClearButtonEnabled(True)
            self.search.setAccessibleName("Search NFL 2K5 audio")
            self.search.setToolTip(
                "Search names, families, formats, physical IDs, and ownership status"
            )
            self.scope_filter = QComboBox()
            self.scope_filter.addItem(
                f"All Playable Audio ({EXPECTED_PLAYABLE_AUDIO_COUNT:,})",
                PLAYABLE_AUDIO_SCOPE_ID,
            )
            self.scope_filter.addItem("Standalone sounds (850)", "standalone")
            self.scope_filter.addItem("Streaming banks (17)", "streaming")
            self.scope_filter.addItem(
                "Playable streaming ranges (53,571)", "streaming_ranges"
            )
            self.scope_filter.addItem(
                f"Raw bank containers ({RAW_AUDIO_CONTAINER_COUNT})",
                "raw_containers",
            )
            self.scope_filter.setMinimumWidth(250)
            self.scope_filter.setSizeAdjustPolicy(
                QComboBox.AdjustToMinimumContentsLengthWithIcon
            )
            self.scope_filter.setMinimumContentsLength(14)
            self.scope_filter.setAccessibleName("Audio container scope")
            self.scope_filter.setAccessibleDescription(
                "Defaults to every playable sound: 850 standalone cues first, then "
                "53,571 playable streaming ranges. Complete banks and opaque raw "
                "containers remain available in their separate export-only scopes."
            )
            self.scope_filter.setToolTip(
                "Browse every playable cue together, or choose standalone cues, "
                "AUSB external banks/ranges, or the nine opaque BANK/ABNK/WBNK "
                "resource containers"
            )
            self.family_filter = QComboBox()
            self.family_filter.setMinimumWidth(210)
            self.family_filter.setAccessibleName("Audio family filter")
            self.family_filter.setToolTip(
                "Limit this audio scope to one user-facing family"
            )
            self.status_filter = QComboBox()
            self.status_filter.addItem("All statuses", None)
            self.status_filter.addItem("Modified", "Modified")
            self.status_filter.addItem("Editable", "Editable")
            self.status_filter.addItem("Export-only", "Export-only")
            self.status_filter.setMinimumWidth(150)
            self.status_filter.setAccessibleName("Audio edit status filter")
            self.status_filter.setToolTip(
                "Modified isolates staged WAVs; Editable accepts a strict WAV; "
                "Export-only never exposes a writer"
            )
            self.meaning_filter = QComboBox()
            self.meaning_filter.addItem("All meaning confidence (850)", None)
            self.meaning_filter.addItem(
                "Menu Back route (1)", MENU_BACK_MEANING_STATUS
            )
            self.meaning_filter.addItem(
                "Reviewed labels (152)", REVIEWED_LABEL_MEANING_STATUS
            )
            self.meaning_filter.addItem(
                "Family-reviewed labels (1)", FAMILY_REVIEWED_MEANING_STATUS
            )
            self.meaning_filter.addItem(
                "Provisional labels (696)", PROVISIONAL_LABEL_MEANING_STATUS
            )
            self.meaning_filter.setMinimumWidth(205)
            self.meaning_filter.setAccessibleName(
                "Standalone audio meaning confidence filter"
            )
            self.meaning_filter.setAccessibleDescription(
                "Separate from edit status. Limit standalone sounds to the one "
                "Menu Back writer route, 152 reviewed labels, one family-reviewed "
                "label inferred from a reviewed sibling, or 696 provisional "
                "labels whose exact runtime cue meanings remain unproved."
            )
            self.meaning_filter.setToolTip(
                "Meaning confidence describes cue naming and runtime ownership, not "
                "whether the exact physical sound is Editable. Available only for "
                "standalone sounds."
            )
            self.labeled_only_filter = QCheckBox("Labeled only")
            self.labeled_only_filter.setAccessibleName(
                "Show only audio cues with a custom project label or note"
            )
            self.labeled_only_filter.setToolTip(
                "Show only playable sounds you have named or annotated in this project."
            )
            self.labeled_only_filter.setVisible(self._annotation_capable)
            self.filters_layout.addWidget(self.search, 0, 0, 1, 2)
            self.filters_layout.addWidget(self.scope_filter, 0, 2)
            self.filters_layout.addWidget(self.family_filter, 1, 0)
            self.filters_layout.addWidget(self.status_filter, 1, 1)
            self.filters_layout.addWidget(self.meaning_filter, 1, 2)
            self.filters_layout.setColumnStretch(0, 1)
            root.addLayout(self.filters_layout)
            self._populate_family_filter()
            self._sync_meaning_filter_for_scope()

            collection_actions = QHBoxLayout()
            collection_actions.setSpacing(9)
            self.soundtrack_button = QPushButton(
                f"Soundtrack && music ({SOUNDTRACK_RANGE_COUNT})"
            )
            self.soundtrack_button.setAccessibleName(
                "Show all soundtrack and music ranges"
            )
            self.soundtrack_button.setToolTip(
                f"Show all {SOUNDTRACK_RANGE_COUNT} known soundtrack and music "
                "ranges. Human song "
                "titles have not been recovered, so rows retain exact bank/range IDs. "
                "The complete decoded WAV collection is about "
                f"{SOUNDTRACK_WAV_PAYLOAD_BYTES / 1024 ** 3:.2f} GiB before ZIP."
            )
            self.export_matching_button = QPushButton("Export matching audio…")
            self.export_matching_button.setAccessibleName(
                "Export all matching audio as a ZIP"
            )
            self.export_matching_button.setEnabled(False)
            self.export_matching_button.setToolTip(
                "Narrow the current filters to 1–256 audio rows."
            )
            collection_actions.addWidget(self.soundtrack_button)
            collection_actions.addWidget(self.labeled_only_filter)
            collection_actions.addStretch(1)
            collection_actions.addWidget(self.export_matching_button)
            root.addLayout(collection_actions)

            replacement_pack = QFrame()
            replacement_pack.setObjectName("audioBatchCard")
            replacement_pack_layout = QVBoxLayout(replacement_pack)
            replacement_pack_layout.setContentsMargins(14, 11, 14, 11)
            replacement_pack_layout.setSpacing(8)
            replacement_pack_header = QHBoxLayout()
            replacement_pack_header.setSpacing(8)
            replacement_pack_title = QLabel("Replacement templates")
            replacement_pack_title.setObjectName("audioPackPathHeading")
            self.replacement_pack_help_toggle = QPushButton(
                "What's in a template?"
            )
            self.replacement_pack_help_toggle.setObjectName("audioHelpToggle")
            self.replacement_pack_help_toggle.setCheckable(True)
            self.replacement_pack_help_toggle.setChecked(False)
            self.replacement_pack_help_toggle.setAccessibleName(
                "Show or hide replacement template details"
            )
            self.replacement_pack_help_toggle.setToolTip(
                "Explain what an exported audio replacement template contains "
                "and how the v1–v4 pack formats differ."
            )
            replacement_pack_header.addWidget(replacement_pack_title)
            replacement_pack_header.addStretch(1)
            replacement_pack_header.addWidget(self.replacement_pack_help_toggle)
            replacement_pack_layout.addLayout(replacement_pack_header)
            self.replacement_pack_note = QLabel(
                "The current default creates a v4 metadata-only template for all 850 "
                "standalone sounds. It includes a spreadsheet-safe, read-only "
                "AUDIO-CUE-MAP.csv with names, current status, exact WAV contracts, and "
                "replacement paths. Use Selected shortlist for 1–256 hand-picked "
                "standalone sounds or exact streaming ranges. Every template contains "
                "zero retail WAVs. Old v3 all-850, v2 shortlist, and v1 legacy packs "
                "remain import-compatible; whole streaming banks stay excluded."
            )
            self.replacement_pack_note.setWordWrap(True)
            self.replacement_pack_note.setObjectName("audioMuted")
            # Long-form documentation: collapsed by default so the pack controls
            # read as controls.  The full text stays available on demand.
            self.replacement_pack_note.setVisible(False)
            self.replacement_pack_help_toggle.toggled.connect(
                self._set_replacement_pack_help_visible
            )
            replacement_pack_layout.addWidget(self.replacement_pack_note)
            replacement_pack_contents = QHBoxLayout()
            replacement_pack_contents.setSpacing(9)
            self.replacement_pack_contents = QComboBox()
            self.replacement_pack_contents.addItem(
                "All standalone sounds (850)", "all_standalone"
            )
            self.replacement_pack_contents.addItem(
                "Selected shortlist (1–256)", "shortlist"
            )
            self.replacement_pack_contents.addItem(
                "Legacy 153-cue pack", "standalone"
            )
            self.replacement_pack_contents.setMinimumWidth(250)
            self.replacement_pack_contents.setAccessibleName(
                "Audio replacement pack contents"
            )
            self.replacement_pack_contents.setAccessibleDescription(
                "Choose the current v4 all-850 template with its read-only audio cue "
                "map, an ordered 1–256-sound shortlist, or the backward-compatible "
                "legacy 153-cue pack."
            )
            self.replacement_pack_contents.setToolTip(
                "All standalone sounds is the current v4 default and includes a "
                "spreadsheet-safe, read-only AUDIO-CUE-MAP.csv. Exact streaming ranges "
                "belong in Selected shortlist. Old v3 all-850, v2 shortlist, and v1 "
                "legacy packs still import. No choice includes retail WAVs."
            )
            self.replacement_pack_shortlist_count = QLabel("Shortlist: 0 selected")
            self.replacement_pack_shortlist_count.setObjectName("audioCountPill")
            self.replacement_pack_shortlist_count.setAccessibleName(
                "Replacement pack shortlist count"
            )
            self.replacement_pack_shortlist_count.setAccessibleDescription(
                "No sounds are currently selected for a shortlist replacement pack."
            )
            self.replacement_pack_shortlist_count.setToolTip(
                "This count controls only Selected shortlist mode; all-850 and legacy "
                "template exports do not depend on the shortlist."
            )
            replacement_pack_contents.addWidget(self.replacement_pack_contents)
            replacement_pack_contents.addWidget(self.replacement_pack_shortlist_count)
            replacement_pack_contents.addStretch(1)
            replacement_pack_layout.addLayout(replacement_pack_contents)
            replacement_pack_actions = QHBoxLayout()
            replacement_pack_actions.setSpacing(9)
            self.replacement_pack_container = QComboBox()
            self.replacement_pack_container.addItem("Editable folder", "folder")
            self.replacement_pack_container.addItem("ZIP hand-off", "zip")
            self.replacement_pack_container.setAccessibleName(
                "Audio replacement template format"
            )
            self.replacement_pack_container.setToolTip(
                "Both formats contain metadata and an empty replacements folder. The "
                "default all-850 v4 format also includes its read-only AUDIO-CUE-MAP.csv; "
                "neither format contains retail WAVs."
            )
            self.export_replacement_template_button = QPushButton(
                "Export replacement template…"
            )
            self.export_replacement_template_button.setAccessibleName(
                "Export an audio replacement template"
            )
            self.import_replacement_pack_button = QPushButton(
                "Preview & import pack…"
            )
            self.import_replacement_pack_button.setObjectName("audioPrimaryButton")
            self.import_replacement_pack_button.setAccessibleName(
                "Preview, confirm, and import authored audio WAV replacements from "
                "a v1 through v4 pack"
            )
            replacement_pack_actions.addWidget(self.replacement_pack_container)
            replacement_pack_actions.addWidget(self.export_replacement_template_button)
            replacement_pack_actions.addStretch(1)
            replacement_pack_actions.addWidget(self.import_replacement_pack_button)
            replacement_pack_layout.addLayout(replacement_pack_actions)
            root.addWidget(replacement_pack)

            self.shortlist_actions_layout = QGridLayout()
            self.shortlist_actions_layout.setHorizontalSpacing(6)
            self.shortlist_actions_layout.setVerticalSpacing(8)
            self.shortlist_toggle_button = QPushButton("Add selected sound")
            self.shortlist_toggle_button.setAccessibleName(
                "Add or remove the selected sound from the audio shortlist"
            )
            self.shortlist_page_button = QPushButton("Add this page")
            self.shortlist_page_button.setAccessibleName(
                "Add every playable sound on this page to the audio shortlist"
            )
            self.shortlist_matching_button = QPushButton("Add all matching")
            self.shortlist_matching_button.setAccessibleName(
                "Add every matching playable sound to the audio shortlist"
            )
            self.shortlist_matching_button.setAccessibleDescription(
                "Adds all 1 to 256 standalone sounds or playable streaming ranges "
                "matching the current search, family, edit-status, and meaning-"
                "confidence filters. Existing shortlist sounds are kept once."
            )
            self.shortlist_matching_button.setEnabled(False)
            self.shortlist_matching_button.setToolTip(
                "Narrow the current filters to 1–256 standalone sounds or playable "
                "streaming ranges."
            )
            self.shortlist_review_button = QPushButton("Review selected")
            self.shortlist_review_button.setAccessibleName(
                "Review selected audio sounds or return to the audio browser"
            )
            self.shortlist_review_button.setEnabled(False)
            self.shortlist_review_button.setToolTip(
                "Add sounds first, then review the complete ordered shortlist."
            )
            self.shortlist_count_label = QLabel("Selected 0 / 256")
            self.shortlist_count_label.setObjectName("audioCountPill")
            self.shortlist_count_label.setAccessibleName("Audio shortlist count")
            self.shortlist_count_label.setToolTip(
                "This session-only list can cross searches, pages, families, and "
                "audio scopes. It stays until you clear it or load another XISO; "
                "a Clear can be undone until the next shortlist change."
            )
            self.shortlist_clear_button = QPushButton("Clear")
            self.shortlist_clear_button.setAccessibleName("Clear audio shortlist")
            self.export_shortlist_button = QPushButton("Export selected WAVs…")
            self.export_shortlist_button.setObjectName("audioPrimaryButton")
            self.export_shortlist_button.setAccessibleName(
                "Export selected sounds as one WAV ZIP"
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_toggle_button, 0, 0
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_page_button, 0, 1
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_matching_button, 0, 2, 1, 2
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_review_button, 1, 0
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_count_label, 1, 1
            )
            self.shortlist_actions_layout.addWidget(
                self.shortlist_clear_button, 1, 2
            )
            self.shortlist_actions_layout.addWidget(
                self.export_shortlist_button, 1, 3
            )
            self.shortlist_actions_layout.setColumnStretch(3, 1)
            root.addLayout(self.shortlist_actions_layout)

            splitter = QSplitter(Qt.Horizontal)
            browser = QFrame()
            browser.setObjectName("audioCard")
            browser_layout = QVBoxLayout(browser)
            browser_layout.setContentsMargins(0, 0, 0, 0)
            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels(
                (
                    "Cue / bank / range", "Family", "Format", "Length / ranges",
                    "Location", "Status",
                )
            )
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setAlternatingRowColors(True)
            self.table.verticalHeader().setVisible(False)
            header_view = self.table.horizontalHeader()
            header_view.setSectionResizeMode(0, QHeaderView.Stretch)
            for column in range(1, 6):
                header_view.setSectionResizeMode(
                    column, QHeaderView.ResizeToContents
                )
            browser_layout.addWidget(self.table, 1)
            paging = QHBoxLayout()
            paging.setContentsMargins(12, 8, 12, 10)
            self.previous_button = QPushButton("Previous")
            self.next_button = QPushButton("Next")
            self.range_label = QLabel("0 results")
            self.range_label.setAlignment(Qt.AlignCenter)
            self.range_label.setObjectName("audioMuted")
            self.shortlist_move_up_button = QPushButton("Move up")
            self.shortlist_move_up_button.setAccessibleName(
                "Move selected sound earlier in the audio shortlist"
            )
            self.shortlist_move_up_button.setToolTip(
                "Move this sound one place earlier in the exported shortlist."
            )
            self.shortlist_move_up_button.hide()
            self.shortlist_move_down_button = QPushButton("Move down")
            self.shortlist_move_down_button.setAccessibleName(
                "Move selected sound later in the audio shortlist"
            )
            self.shortlist_move_down_button.setToolTip(
                "Move this sound one place later in the exported shortlist."
            )
            self.shortlist_move_down_button.hide()
            paging.addWidget(self.shortlist_move_up_button)
            paging.addWidget(self.shortlist_move_down_button)
            paging.addWidget(self.previous_button)
            paging.addStretch(1)
            paging.addWidget(self.range_label)
            paging.addStretch(1)
            paging.addWidget(self.next_button)
            browser_layout.addLayout(paging)
            splitter.addWidget(browser)

            self.detail_card = QFrame()
            self.detail_card.setObjectName("audioCard")
            self.detail_card.setMinimumWidth(AUDIO_DETAIL_MIN_WIDTH)
            self.detail_card.setMaximumWidth(460)
            detail_layout = QVBoxLayout(self.detail_card)
            detail_layout.setContentsMargins(20, 18, 20, 18)
            detail_layout.setSpacing(12)

            self.detail_scroll = QScrollArea()
            self.detail_scroll.setObjectName("audioDetailScroll")
            self.detail_scroll.setWidgetResizable(True)
            self.detail_scroll.setFrameShape(QFrame.NoFrame)
            self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.detail_scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
            self.detail_scroll.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self.detail_scroll.setMinimumHeight(AUDIO_DETAIL_SCROLL_MIN_HEIGHT)
            self.detail_scroll.viewport().setAutoFillBackground(False)

            self.detail_content = QWidget()
            self.detail_content.setObjectName("audioDetailContent")
            self.detail_content.setAutoFillBackground(False)
            detail_content_layout = QVBoxLayout(self.detail_content)
            detail_content_layout.setContentsMargins(0, 0, 0, 0)
            detail_content_layout.setSpacing(12)
            selectable_text = (
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            self.asset_title = QLabel("Select a sound")
            self.asset_title.setObjectName("audioDetailTitle")
            self.asset_title.setTextFormat(Qt.PlainText)
            self.asset_title.setWordWrap(True)
            self.asset_title.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.asset_title.setTextInteractionFlags(selectable_text)
            self.asset_title.setAccessibleName("Selected audio title")
            self.status_label = QLabel("Browse every known audio container")
            self.status_label.setObjectName("audioStatus")
            self.status_label.setAccessibleName("Selected audio edit status")
            self.metadata_label = QLabel("")
            self.metadata_label.setObjectName("audioMuted")
            self.metadata_label.setTextFormat(Qt.PlainText)
            self.metadata_label.setWordWrap(True)
            self.metadata_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.metadata_label.setTextInteractionFlags(selectable_text)
            self.metadata_label.setAccessibleName("Selected audio technical details")
            self.ownership_label = QLabel("")
            self.ownership_label.setTextFormat(Qt.PlainText)
            self.ownership_label.setWordWrap(True)
            self.ownership_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.ownership_label.setTextInteractionFlags(selectable_text)
            self.ownership_label.setAccessibleName(
                "Selected audio ownership and shared-slot details"
            )
            self.note_label = QLabel(
                "Standalone cues and indexed ranges play/export as WAV. Complete "
                "streaming banks remain raw export-only; editable ranges accept WAVs."
            )
            self.note_label.setWordWrap(True)
            self.note_label.setObjectName("audioNote")
            self.note_label.setTextFormat(Qt.PlainText)
            self.note_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.note_label.setTextInteractionFlags(selectable_text)
            self.note_label.setAccessibleName(
                "Selected audio action and WAV requirements"
            )
            detail_content_layout.addWidget(self.asset_title)
            detail_content_layout.addWidget(self.status_label)
            detail_content_layout.addWidget(self.metadata_label)
            detail_content_layout.addWidget(self.ownership_label)
            detail_content_layout.addWidget(self.note_label)
            self.annotation_card = QFrame()
            self.annotation_card.setObjectName("audioAnnotationCard")
            annotation_layout = QVBoxLayout(self.annotation_card)
            annotation_layout.setContentsMargins(12, 11, 12, 11)
            annotation_layout.setSpacing(7)
            self.annotation_heading = QLabel("Your cue label & notes")
            self.annotation_heading.setObjectName("audioPackPathHeading")
            self.annotation_help = QLabel(
                "Project metadata only — searchable and shareable, but never written "
                "into the game or counted as a build edit."
            )
            self.annotation_help.setObjectName("audioMuted")
            self.annotation_help.setWordWrap(True)
            self.annotation_title_edit = QLineEdit()
            self.annotation_title_edit.setMaxLength(MAX_TITLE_CHARS)
            self.annotation_title_edit.setPlaceholderText(
                "Custom title, song name, call, crowd cue…"
            )
            self.annotation_title_edit.setAccessibleName(
                "Custom title for the selected audio cue"
            )
            self.annotation_title_count = QLabel(f"0 / {MAX_TITLE_CHARS}")
            self.annotation_title_count.setObjectName("audioMuted")
            self.annotation_title_count.setAlignment(Qt.AlignRight)
            self.annotation_note_edit = QTextEdit()
            self.annotation_note_edit.setPlaceholderText(
                "What you heard, where it plays, replacement idea, or research note…"
            )
            self.annotation_note_edit.setAcceptRichText(False)
            self.annotation_note_edit.setMaximumHeight(112)
            self.annotation_note_edit.setAccessibleName(
                "Notes for the selected audio cue"
            )
            self.annotation_note_count = QLabel(f"0 / {MAX_NOTE_CHARS}")
            self.annotation_note_count.setObjectName("audioMuted")
            self.annotation_note_count.setAlignment(Qt.AlignRight)
            annotation_actions = QHBoxLayout()
            self.save_annotation_button = QPushButton("Save label")
            self.save_annotation_button.setObjectName("audioPrimaryButton")
            self.save_annotation_button.setAccessibleName(
                "Save the custom title and notes for this audio cue"
            )
            self.clear_annotation_button = QPushButton("Clear")
            self.clear_annotation_button.setAccessibleName(
                "Clear the custom title and notes for this audio cue"
            )
            annotation_actions.addWidget(self.save_annotation_button, 1)
            annotation_actions.addWidget(self.clear_annotation_button)
            annotation_layout.addWidget(self.annotation_heading)
            annotation_layout.addWidget(self.annotation_help)
            annotation_layout.addWidget(self.annotation_title_edit)
            annotation_layout.addWidget(self.annotation_title_count)
            annotation_layout.addWidget(self.annotation_note_edit)
            annotation_layout.addWidget(self.annotation_note_count)
            annotation_layout.addLayout(annotation_actions)
            detail_content_layout.addWidget(self.annotation_card)
            self.pack_path_card = QFrame()
            self.pack_path_card.setObjectName("audioPackPathCard")
            pack_path_layout = QVBoxLayout(self.pack_path_card)
            pack_path_layout.setContentsMargins(12, 10, 12, 10)
            pack_path_layout.setSpacing(7)
            self.pack_path_heading = QLabel("All-850 replacement pack path")
            self.pack_path_heading.setObjectName("audioPackPathHeading")
            self.pack_path_label = QLabel("")
            self.pack_path_label.setObjectName("audioPackPath")
            self.pack_path_label.setWordWrap(True)
            self.pack_path_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            self.pack_path_label.setAccessibleName(
                "All-850 audio replacement pack path"
            )
            self.copy_pack_path_button = QPushButton("Copy pack path")
            self.copy_pack_path_button.setAccessibleName(
                "Copy the all-850 audio replacement pack path"
            )
            self.copy_pack_path_button.setAccessibleDescription(
                "Copies this standalone sound's exact metadata-only v4 template "
                "path to the clipboard."
            )
            self.copy_pack_path_button.setShortcut("Ctrl+Shift+C")
            self.copy_pack_path_button.setToolTip(
                "Copy this exact v4 template path (Ctrl+Shift+C)"
            )
            pack_path_layout.addWidget(self.pack_path_heading)
            pack_path_layout.addWidget(self.pack_path_label)
            pack_path_layout.addWidget(
                self.copy_pack_path_button, 0, Qt.AlignLeft
            )
            self.pack_path_card.hide()
            detail_content_layout.addWidget(self.pack_path_card)
            self.waveform_heading = QLabel("Waveform preview")
            self.waveform_heading.setObjectName("audioPackPathHeading")
            self.waveform_heading.setAccessibleName("Waveform preview heading")
            self.waveform_preview = AudioWaveformPreview()
            self.load_waveform_button = QPushButton("Load waveform")
            self.load_waveform_button.setAccessibleName(
                "Load a read-only waveform for the selected sound"
            )
            self.load_waveform_button.setAccessibleDescription(
                "Explicitly reads the selected sound through the private current-WAV "
                "route and draws a bounded waveform. It never starts playback or "
                "changes the mod project."
            )
            self.load_waveform_button.setEnabled(False)
            detail_content_layout.addWidget(self.waveform_heading)
            detail_content_layout.addWidget(self.waveform_preview)
            detail_content_layout.addWidget(
                self.load_waveform_button, 0, Qt.AlignLeft
            )
            detail_content_layout.addStretch(1)
            self.detail_scroll.setWidget(self.detail_content)
            detail_layout.addWidget(self.detail_scroll, 1)
            self.drop_zone = _WavDropZone()
            detail_layout.addWidget(self.drop_zone)
            buttons = QHBoxLayout()
            self.play_button = QPushButton("Play")
            self.export_button = QPushButton("Export WAV")
            buttons.addWidget(self.play_button)
            buttons.addWidget(self.export_button)
            detail_layout.addLayout(buttons)
            edit_buttons = QHBoxLayout()
            self.replace_button = QPushButton("Replace WAV")
            self.replace_button.setObjectName("audioPrimaryButton")
            self.revert_button = QPushButton("Revert")
            edit_buttons.addWidget(self.replace_button, 1)
            edit_buttons.addWidget(self.revert_button)
            detail_layout.addLayout(edit_buttons)
            splitter.addWidget(self.detail_card)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
            root.addWidget(splitter, 1)

            progress_row = QHBoxLayout()
            self.progress_label = QLabel("Ready")
            self.progress_label.setObjectName("audioMuted")
            self.progress_label.setTextFormat(Qt.PlainText)
            self.progress_bar = QProgressBar()
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedWidth(180)
            self.progress_bar.hide()
            progress_row.addWidget(self.progress_label)
            progress_row.addStretch(1)
            progress_row.addWidget(self.progress_bar)
            root.addLayout(progress_row)

        def _set_replacement_pack_help_visible(self, shown: bool) -> None:
            """Show or hide the collapsible replacement-template explainer.

            The explanatory paragraph is long-form documentation, not a control,
            so it stays collapsed by default to keep the toolbar readable.  The
            label itself (and its full text) is always present; only its
            visibility changes.
            """

            self.replacement_pack_note.setVisible(shown)
            self.replacement_pack_help_toggle.setText(
                "Hide template details" if shown else "What's in a template?"
            )

        def _apply_style(self) -> None:
            self.setStyleSheet(
                """
                QWidget#audioPanel {
                    background: #111823;
                    color: #eaf0f8;
                    font-family: Inter, "Noto Sans", sans-serif;
                    font-size: 13px;
                }
                QLabel#audioTitle {
                    color: #ffffff;
                    font-size: 27px;
                    font-weight: 750;
                }
                QLabel#audioDetailTitle {
                    color: #ffffff;
                    font-size: 20px;
                    font-weight: 700;
                }
                QLabel#audioMuted { color: #91a0b5; }
                QLabel#audioCountPill, QLabel#audioStatus {
                    color: #7ce8b2;
                    background: #16352c;
                    border: 1px solid #2a6751;
                    border-radius: 10px;
                    padding: 5px 10px;
                    font-weight: 650;
                }
                QLabel#audioNote {
                    color: #cbd6e4;
                    background: #172130;
                    border: 1px solid #28384d;
                    border-radius: 8px;
                    padding: 11px;
                }
                QFrame#audioPackPathCard, QFrame#audioAnnotationCard {
                    background: #111b28;
                    border: 1px solid #31506a;
                    border-radius: 8px;
                }
                QLabel#audioPackPathHeading {
                    color: #91a0b5;
                    font-size: 12px;
                    font-weight: 650;
                }
                QLabel#audioPackPath {
                    color: #dce8f7;
                    font-family: "Noto Sans Mono", monospace;
                }
                QFrame#audioCard {
                    background: #151f2c;
                    border: 1px solid #28384d;
                    border-radius: 10px;
                }
                QScrollArea#audioDetailScroll, QWidget#audioDetailContent {
                    background: transparent;
                    border: none;
                }
                QFrame#audioBatchCard {
                    background: #141f2b;
                    border: 1px solid #31506a;
                    border-radius: 9px;
                }
                QFrame#audioDropZone {
                    background: #121b27;
                    border: 1px dashed #50729a;
                    border-radius: 8px;
                }
                QFrame#audioDropZone:disabled {
                    color: #718096;
                    border-color: #35465b;
                }
                QLabel#audioDropTitle {
                    color: #dce8f7;
                    font-weight: 650;
                }
                QLineEdit, QComboBox, QTextEdit {
                    color: #eaf0f8;
                    background: #151f2c;
                    border: 1px solid #34475e;
                    border-radius: 7px;
                    padding: 8px 10px;
                    min-height: 20px;
                }
                QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                    border-color: #4f9cf9;
                }
                QTableWidget {
                    color: #dce5f1;
                    background: transparent;
                    alternate-background-color: #182433;
                    border: none;
                    gridline-color: #26364a;
                    selection-background-color: #244f76;
                    selection-color: #ffffff;
                }
                QHeaderView::section {
                    color: #91a0b5;
                    background: #121b27;
                    border: none;
                    border-bottom: 1px solid #304158;
                    padding: 8px;
                    font-weight: 650;
                }
                QPushButton {
                    color: #dce8f7;
                    background: #233247;
                    border: 1px solid #3a506b;
                    border-radius: 7px;
                    padding: 8px 13px;
                    font-weight: 600;
                }
                QPushButton:hover { background: #2a3d56; }
                QPushButton:pressed { background: #1c293a; }
                QPushButton:disabled { color: #68778b; background: #192330; }
                QPushButton#audioPrimaryButton {
                    color: #07150e;
                    background: #43d590;
                    border-color: #43d590;
                }
                QPushButton#audioPrimaryButton:hover { background: #58e3a2; }
                QPushButton#audioPrimaryButton:disabled {
                    color: #68778b;
                    background: #192330;
                    border-color: #2a394c;
                }
                QPushButton#audioHelpToggle {
                    color: #8ea3bd;
                    background: transparent;
                    border: 1px solid #31506a;
                    padding: 4px 10px;
                    font-weight: 600;
                }
                QPushButton#audioHelpToggle:hover {
                    color: #cfe0f5;
                    background: #1b2634;
                    border-color: #4f9cf9;
                }
                QPushButton#audioHelpToggle:checked {
                    color: #cfe0f5;
                    background: #1b2634;
                }
                QProgressBar {
                    background: #172130;
                    border: 1px solid #304158;
                    border-radius: 4px;
                    height: 7px;
                }
                QProgressBar::chunk { background: #43d590; border-radius: 3px; }
                """
            )

        def _connect(self) -> None:
            self.search.textChanged.connect(self._search_text_changed)
            self.scope_filter.currentIndexChanged.connect(self._scope_changed)
            self.family_filter.currentIndexChanged.connect(self._filters_changed)
            self.status_filter.currentIndexChanged.connect(self._filters_changed)
            self.meaning_filter.currentIndexChanged.connect(self._filters_changed)
            self.labeled_only_filter.toggled.connect(self._filters_changed)
            self.soundtrack_button.clicked.connect(self._show_soundtrack)
            self.export_matching_button.clicked.connect(
                self._export_matching_audio
            )
            self.export_replacement_template_button.clicked.connect(
                self._export_audio_replacement_template
            )
            self.replacement_pack_contents.currentIndexChanged.connect(
                self._update_replacement_pack_actions
            )
            self.import_replacement_pack_button.clicked.connect(
                self._import_audio_replacement_pack
            )
            self.shortlist_toggle_button.clicked.connect(
                self._toggle_audio_shortlist
            )
            self.shortlist_page_button.clicked.connect(
                self._add_visible_audio_to_shortlist
            )
            self.shortlist_matching_button.clicked.connect(
                self._add_all_matching_audio_to_shortlist
            )
            self.shortlist_review_button.clicked.connect(
                self._toggle_audio_shortlist_review
            )
            self.shortlist_clear_button.clicked.connect(
                self._clear_audio_shortlist
            )
            self.shortlist_move_up_button.clicked.connect(
                lambda: self._move_shortlisted_audio(-1)
            )
            self.shortlist_move_down_button.clicked.connect(
                lambda: self._move_shortlisted_audio(1)
            )
            self.export_shortlist_button.clicked.connect(
                self._export_shortlisted_audio
            )
            self.table.itemSelectionChanged.connect(self._selection_changed)
            self.previous_button.clicked.connect(self._previous_page)
            self.next_button.clicked.connect(self._next_page)
            self.play_button.clicked.connect(self._play_selected)
            self.load_waveform_button.clicked.connect(
                self._load_audio_waveform
            )
            self.export_button.clicked.connect(self._export_selected)
            self.replace_button.clicked.connect(self._choose_replacement)
            self.revert_button.clicked.connect(self._revert_selected)
            self.copy_pack_path_button.clicked.connect(
                self._copy_selected_pack_path
            )
            self.annotation_title_edit.textChanged.connect(
                self._annotation_fields_changed
            )
            self.annotation_note_edit.textChanged.connect(
                self._annotation_fields_changed
            )
            self.save_annotation_button.clicked.connect(
                self._save_selected_annotation
            )
            self.clear_annotation_button.clicked.connect(
                self._clear_selected_annotation
            )
            self.drop_zone.wav_dropped.connect(self._replace_with_path)
            self._audio_process.finished.connect(self._audio_process_finished)
            self._audio_process.errorOccurred.connect(
                self._audio_process_failed
            )
            self.error_raised.connect(
                lambda message: QMessageBox.warning(self, "Audio", message)
            )

        def _populate_family_filter(self) -> None:
            current = self.family_filter.currentData()
            scope = str(self.scope_filter.currentData())
            if scope == "raw_containers":
                self.family_filter.blockSignals(True)
                self.family_filter.clear()
                self.family_filter.addItem(
                    f"All container types ({RAW_AUDIO_CONTAINER_COUNT})", None
                )
                for kind in RAW_AUDIO_CONTAINER_KINDS:
                    self.family_filter.addItem(f"{kind} containers (3)", kind)
                matched = self.family_filter.findData(current)
                self.family_filter.setCurrentIndex(matched if matched >= 0 else 0)
                self.family_filter.blockSignals(False)
                return
            families = (
                STANDALONE_AUDIO_FAMILIES
                if scope == "standalone"
                else PLAYABLE_AUDIO_FAMILIES
                if scope == PLAYABLE_AUDIO_SCOPE_ID
                else STREAMING_AUDIO_FAMILIES
            )
            self.family_filter.blockSignals(True)
            self.family_filter.clear()
            total = {
                PLAYABLE_AUDIO_SCOPE_ID: EXPECTED_PLAYABLE_AUDIO_COUNT,
                "standalone": 850,
                "streaming": 17,
                "streaming_ranges": 53_571,
            }[scope]
            self.family_filter.addItem(f"All families ({total:,})", None)
            for family_id, label in families:
                if family_id != "unknown":
                    count = _FAMILY_COUNTS[scope].get(family_id)
                    display = f"{label} ({count:,})" if count is not None else label
                    self.family_filter.addItem(display, family_id)
            matched = self.family_filter.findData(current)
            self.family_filter.setCurrentIndex(matched if matched >= 0 else 0)
            self.family_filter.blockSignals(False)

        def _scope_changed(self, *_args: object) -> None:
            self._search_timer.stop()
            if self._busy or self._shortlist_reviewing:
                return
            self._populate_family_filter()
            self._sync_meaning_filter_for_scope()
            self.offset = 0
            self.refresh(keep_selection=False)

        def _sync_meaning_filter_for_scope(self) -> None:
            """Expose confidence only where its exact standalone domain applies."""

            standalone = self.scope_filter.currentData() == "standalone"
            if not standalone and self.meaning_filter.currentData() is not None:
                self.meaning_filter.blockSignals(True)
                try:
                    self.meaning_filter.setCurrentIndex(
                        self.meaning_filter.findData(None)
                    )
                finally:
                    self.meaning_filter.blockSignals(False)
            self.meaning_filter.setEnabled(
                standalone and not self._shortlist_reviewing and not self._busy
            )
            playable_scope = self.scope_filter.currentData() in {
                PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming_ranges",
            }
            if (
                not self._annotation_capable or not playable_scope
            ) and self.labeled_only_filter.isChecked():
                self.labeled_only_filter.blockSignals(True)
                try:
                    self.labeled_only_filter.setChecked(False)
                finally:
                    self.labeled_only_filter.blockSignals(False)
            self.labeled_only_filter.setEnabled(
                self._annotation_capable
                and playable_scope
                and not self._shortlist_reviewing
                and not self._busy
            )

        def _show_soundtrack(self) -> None:
            """Open the complete, truthfully named soundtrack/music collection."""

            if self._busy or self._shortlist_reviewing:
                return
            self._search_timer.stop()

            self.search.blockSignals(True)
            self.scope_filter.blockSignals(True)
            self.status_filter.blockSignals(True)
            self.labeled_only_filter.blockSignals(True)
            try:
                self.search.clear()
                self.labeled_only_filter.setChecked(False)
                self.scope_filter.setCurrentIndex(
                    self.scope_filter.findData("streaming_ranges")
                )
                self.status_filter.setCurrentIndex(
                    self.status_filter.findData(None)
                )
                self._sync_meaning_filter_for_scope()
                self._populate_family_filter()
                self.family_filter.blockSignals(True)
                try:
                    self.family_filter.setCurrentIndex(
                        self.family_filter.findData("music")
                    )
                finally:
                    self.family_filter.blockSignals(False)
            finally:
                self.search.blockSignals(False)
                self.scope_filter.blockSignals(False)
                self.status_filter.blockSignals(False)
                self.labeled_only_filter.blockSignals(False)
            self.offset = 0
            self.refresh(keep_selection=False)

        def _load_raw_audio_containers(self) -> tuple[UniversalAssetRecord, ...]:
            """Resolve the exact 3+3+3 bank wrappers through the universal index."""

            if self._raw_audio_containers is not None:
                return self._raw_audio_containers
            records: list[UniversalAssetRecord] = []
            for kind in RAW_AUDIO_CONTAINER_KINDS:
                result = self.host.browse_resources(
                    search="",
                    kind=kind,
                    offset=0,
                    limit=RAW_AUDIO_CONTAINER_COUNT + 1,
                    progress=lambda _stage, _completed, _total: None,
                )
                try:
                    values, _total = result  # type: ignore[misc]
                    rows = tuple(values)
                except (TypeError, ValueError) as exc:
                    raise ValidationError(
                        "The universal source index returned an invalid raw-bank page."
                    ) from exc
                if len(rows) != 3 or any(
                    not isinstance(row, UniversalAssetRecord) or row.kind != kind
                    for row in rows
                ):
                    raise ValidationError(
                        f"Expected exactly three indexed {kind} containers in this "
                        "NFL 2K5 source; the universal index does not match the "
                        "supported retail inventory."
                    )
                records.extend(rows)
            records.sort(
                key=lambda row: (row.outer_index, row.chunk_index, row.kind)
            )
            if (
                len(records) != RAW_AUDIO_CONTAINER_COUNT
                or len({row.asset_id for row in records}) != len(records)
            ):
                raise ValidationError(
                    "Raw BANK/ABNK/WBNK container identities are incomplete or duplicated."
                )
            self._raw_audio_containers = tuple(records)
            return self._raw_audio_containers

        def _browse_raw_audio_containers(self) -> AudioPage:
            rows = self._load_raw_audio_containers()
            status = self.status_filter.currentData()
            if status not in (None, "Export-only"):
                filtered: tuple[UniversalAssetRecord, ...] = ()
            else:
                kind = self.family_filter.currentData()
                needle = self.search.text().strip().casefold()
                filtered = tuple(
                    row for row in rows
                    if (kind is None or row.kind == kind)
                    and (
                        not needle
                        or needle in " ".join(
                            (
                                row.asset_id,
                                row.kind,
                                row.outer_head,
                                row.outer_id,
                                str(row.outer_index),
                                str(row.chunk_index),
                                str(row.stored_size),
                                str(row.raw_size),
                                "raw opaque bank container export only",
                            )
                        ).casefold()
                    )
                )
            if not filtered:
                return AudioPage((), 0, 0, self.page_size)
            last_offset = ((len(filtered) - 1) // self.page_size) * self.page_size
            offset = min(self.offset, last_offset)
            return AudioPage(
                filtered[offset:offset + self.page_size],
                len(filtered),
                offset,
                self.page_size,
            )

        def reset_for_source(self) -> None:
            """Clear source-bound curation only after a new XISO is loaded."""

            self._search_timer.stop()
            self._catalog_source_epoch += 1
            self._applied_query_token = None
            self._source_change_query_was_current = None
            self._invalidate_audio_preview()
            self._cancel_audio_waveform()
            self._audio_shortlist.clear()
            self._cleared_audio_shortlist = ()
            self._affected_owner_cache.clear()
            self._affected_owner_errors.clear()
            self._raw_audio_containers = None
            self._annotation_drafts.clear()
            self._shortlist_reviewing = False
            self._catalog_offset_before_review = 0
            self._catalog_selection_before_review = None
            self.offset = 0
            self._set_selected_asset_id(None)
            self._set_audio_browser_filters_enabled(True)
            self.refresh(keep_selection=False)

        def refresh(self, *, keep_selection: bool = True) -> None:
            if self._busy:
                self._refresh_after_busy = True
                return
            wanted = self.selected_asset_id if keep_selection else None
            query_token = (
                None
                if self._shortlist_reviewing else self._current_audio_query_token()
            )
            if self._shortlist_reviewing:
                ordered = tuple(self._audio_shortlist.values())
                if not ordered:
                    self._leave_audio_shortlist_review()
                    return
                last_offset = ((len(ordered) - 1) // self.page_size) * self.page_size
                self.offset = min(max(0, self.offset), last_offset)
                self.page = AudioPage(
                    ordered[self.offset:self.offset + self.page_size],
                    len(ordered),
                    self.offset,
                    self.page_size,
                )
            elif self.scope_filter.currentData() == "raw_containers":
                try:
                    self.page = self._browse_raw_audio_containers()
                except Exception as exc:
                    self.page = AudioPage((), 0, 0, self.page_size)
                    self.offset = 0
                    self._set_selected_asset_id(None)
                    self.table.setRowCount(0)
                    self._show_asset(None)
                    self.count_label.setText("Raw bank inventory unavailable")
                    self.range_label.setText("No raw containers were assumed")
                    self.previous_button.setEnabled(False)
                    self.next_button.setEnabled(False)
                    self._update_collection_actions()
                    self.error_raised.emit(str(exc).strip() or exc.__class__.__name__)
                    return
            else:
                try:
                    query: dict[str, object] = {
                        "search": self.search.text(),
                        "status": self.status_filter.currentData(),
                        "offset": self.offset,
                        "limit": self.page_size,
                        "scope": str(self.scope_filter.currentData()),
                        "family": self.family_filter.currentData(),
                        "meaning_status": self.meaning_filter.currentData(),
                    }
                    if self.labeled_only_filter.isChecked():
                        query["labeled_only"] = True
                    self.page = self.host.browse_audio(
                        **query,
                    )
                except Exception as exc:
                    self.error_raised.emit(str(exc).strip() or exc.__class__.__name__)
                    self._mark_catalog_query_pending()
                    return
            self.offset = self.page.offset
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.setRowCount(len(self.page.assets))
            selected_row = -1
            modified = set(self.host.modified_audio_asset_ids)
            for row, asset in enumerate(self.page.assets):
                annotation: AudioCueAnnotation | None = None
                status, full_status = self._audio_status_texts(asset, modified)
                if isinstance(asset, UniversalAssetRecord):
                    values = (
                        f"{asset.kind} container",
                        "Raw bank resource",
                        f"Raw {asset.kind}",
                        f"{asset.raw_size:,} bytes",
                        f"outer {asset.outer_index} / chunk {asset.chunk_index}",
                        status,
                    )
                    full_values = (
                        f"{asset.kind} raw bank container",
                        "Opaque resource indexed by the universal game-asset catalog",
                        f"Raw {asset.kind} wrapper/body (.bin); no cue decoder",
                        (
                            f"{asset.raw_size:,} total bytes • "
                            f"{asset.stored_size:,} stored body bytes"
                        ),
                        (
                            f"outer {asset.outer_index} ({asset.outer_id}) / "
                            f"chunk {asset.chunk_index} / offset 0x{asset.chunk_offset:x}"
                        ),
                        full_status,
                    )
                elif isinstance(asset, Nfl2k5AudioAsset):
                    annotation = self._annotation_for(asset.asset_id)
                    shown_name = (
                        annotation.title if annotation is not None
                        and annotation.title else asset.name
                    )
                    if annotation is not None:
                        shown_name = f"✎ {shown_name}"
                    values = (
                        shown_name,
                        asset.family_label,
                        f"WAV • {asset.channels}ch",
                        self._duration(asset.duration_seconds),
                        f"AUDO {asset.outer_index}:{asset.chunk_index}",
                        status,
                    )
                    full_values = (
                        (
                            f"Custom title: {annotation.title or '(game label retained)'}\n"
                            f"Game/catalog label: {asset.name}\n"
                            f"Note: {annotation.note or '(none)'}"
                            if annotation is not None else asset.name
                        ),
                        asset.family_label,
                        f"WAV • {asset.channels}ch • {asset.sample_rate:,} Hz",
                        self._duration(asset.duration_seconds),
                        f"AUDO {asset.outer_index}:{asset.chunk_index}",
                        full_status,
                    )
                elif isinstance(asset, Nfl2k5StreamingAudioBank):
                    values = (
                        asset.name,
                        asset.family_label,
                        "Raw bank (.bin)",
                        f"{asset.entry_count:,} ranges",
                        (
                            f"AUSB {asset.outer_index}:{asset.chunk_index} → "
                            f"outer {asset.external_outer_index}"
                        ),
                        status,
                    )
                    full_values = (
                        asset.name,
                        asset.family_label,
                        asset.format_label,
                        f"{asset.entry_count:,} indexed ranges",
                        (
                            f"AUSB {asset.outer_index}:{asset.chunk_index} → "
                            f"external outer {asset.external_outer_index}"
                        ),
                        full_status,
                    )
                else:
                    annotation = self._annotation_for(asset.asset_id)
                    shown_name = (
                        annotation.title if annotation is not None
                        and annotation.title else asset.name
                    )
                    if annotation is not None:
                        shown_name = f"✎ {shown_name}"
                    values = (
                        shown_name,
                        asset.family_label,
                        f"WAV • {asset.channels}ch",
                        self._duration(asset.duration_seconds),
                        (
                            f"AUSB {asset.outer_index}:{asset.chunk_index} • "
                            f"range {asset.range_index:,}"
                        ),
                        status,
                    )
                    full_values = (
                        (
                            f"Custom title: {annotation.title or '(game label retained)'}\n"
                            f"Game/catalog label: {asset.name}\n"
                            f"Note: {annotation.note or '(none)'}"
                            if annotation is not None else asset.name
                        ),
                        asset.family_label,
                        f"WAV • {asset.channels}ch • {asset.sample_rate:,} Hz",
                        self._duration(asset.duration_seconds),
                        (
                            f"AUSB {asset.outer_index}:{asset.chunk_index} • "
                            f"range {asset.range_index:,}"
                        ),
                        full_status,
                    )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, asset.asset_id)
                    tooltip = full_values[column]
                    if column == 0:
                        tooltip = f"{tooltip}\n{asset.asset_id}"
                    item.setToolTip(
                        _literal_tooltip(tooltip)
                        if column == 0 and annotation is not None else tooltip
                    )
                    self.table.setItem(row, column, item)
                if asset.asset_id == wanted:
                    selected_row = row
            if selected_row < 0 and self.page.assets:
                selected_row = 0
            if selected_row >= 0:
                self.table.selectRow(selected_row)
                self._set_selected_asset_id(
                    self.page.assets[selected_row].asset_id
                )
                self._show_asset(self.page.assets[selected_row])
            else:
                self._set_selected_asset_id(None)
                self._show_asset(None)
            self.table.blockSignals(False)
            if (
                query_token is not None
                and query_token == self._current_audio_query_token()
            ):
                self._applied_query_token = query_token
            self._restore_applied_query_presentation()

        def _restore_applied_query_presentation(self) -> None:
            """Render labels/actions for the page whose query token is applied."""

            self.count_label.setToolTip("")
            if self._shortlist_reviewing:
                self.count_label.setText(
                    f"Reviewing {self.page.total:,} selected "
                    f"{'sound' if self.page.total == 1 else 'sounds'}"
                )
            elif self.scope_filter.currentData() == "raw_containers":
                self.count_label.setText(
                    f"{self.page.total:,} shown • {RAW_AUDIO_CONTAINER_COUNT} raw "
                    "BANK / ABNK / WBNK containers"
                )
            elif self.scope_filter.currentData() == "streaming":
                self.count_label.setText(
                    f"{self.page.total:,} shown • 17 banks • 53,571 ranges"
                )
            elif self.scope_filter.currentData() == "streaming_ranges":
                self.count_label.setText(
                    f"{self.page.total:,} shown • 53,571 playable ranges"
                )
            elif self.scope_filter.currentData() == PLAYABLE_AUDIO_SCOPE_ID:
                self.count_label.setText(
                    f"{self.page.total:,} shown • "
                    f"{EXPECTED_PLAYABLE_AUDIO_COUNT:,} playable"
                )
                self.count_label.setToolTip(
                    "All Playable Audio contains 850 standalone cues followed by "
                    "53,571 playable streaming ranges; complete banks and opaque "
                    "raw containers stay in separate scopes."
                )
            else:
                self.count_label.setText(
                    f"{self.page.total:,} shown • 850 Editable standalone cues • "
                    "0 Export-only"
                )
            self.range_label.setText(
                f"{self.page.first_number:,}–{self.page.last_number:,} "
                f"of {self.page.total:,}" if self.page.total else "No matching audio"
            )
            pagination_ready = self._pagination_query_ready()
            self.previous_button.setEnabled(self.page.has_previous and pagination_ready)
            self.next_button.setEnabled(self.page.has_next and pagination_ready)
            self._update_collection_actions()

        def _current_audio_query_token(
            self,
        ) -> tuple[int, str, str, str | None, str | None, str | None, bool]:
            """Identify the exact catalog query represented by the filter controls."""

            def selected_data(widget: object) -> str | None:
                value = widget.currentData()  # type: ignore[attr-defined]
                return None if value is None else str(value)

            return (
                self._catalog_source_epoch,
                self.search.text(),
                str(self.scope_filter.currentData()),
                selected_data(self.family_filter),
                selected_data(self.status_filter),
                selected_data(self.meaning_filter),
                self.labeled_only_filter.isChecked(),
            )

        def _catalog_query_is_current(self) -> bool:
            """Return whether the visible page belongs to the current controls."""

            return (
                self._applied_query_token is not None
                and self._applied_query_token == self._current_audio_query_token()
            )

        def _catalog_page_actions_ready(self) -> bool:
            return bool(
                self.host.source_ready
                and not self._busy
                and not self._shortlist_reviewing
                and self._catalog_query_is_current()
            )

        def _pagination_query_ready(self) -> bool:
            return bool(
                self.host.source_ready
                and not self._busy
                and (
                    self._shortlist_reviewing
                    or self._catalog_query_is_current()
                )
            )

        def _mark_catalog_query_pending(self) -> None:
            """Make stale-page actions inert without disturbing its selected row."""

            if self._shortlist_reviewing or self._catalog_query_is_current():
                return
            self.count_label.setText("Updating audio results…")
            self.range_label.setText("Waiting for the new search and filters…")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self._update_collection_actions()

        def _search_text_changed(self, _text: str) -> None:
            """Debounce catalog work while immediately fencing the previous page."""

            if self._busy:
                self._search_timer.stop()
                return
            if self._shortlist_reviewing:
                return
            self._search_timer.start()
            if self._catalog_query_is_current():
                self._search_timer.stop()
                self._restore_applied_query_presentation()
                return
            self._mark_catalog_query_pending()

        def _update_collection_actions(self) -> None:
            if self._shortlist_reviewing:
                self.soundtrack_button.setEnabled(False)
                self.export_matching_button.setEnabled(False)
                self.export_matching_button.setText("Export matching audio…")
                self.export_matching_button.setToolTip(
                    "Return to the audio browser to export its filtered results."
                )
                self._update_audio_shortlist_actions()
                return
            if self.scope_filter.currentData() == "raw_containers":
                self.soundtrack_button.setEnabled(
                    self.host.source_ready and not self._busy
                )
                self.export_matching_button.setEnabled(False)
                self.export_matching_button.setText("Export matching audio…")
                self.export_matching_button.setToolTip(
                    "Raw BANK/ABNK/WBNK wrappers export one at a time through "
                    "the verified universal-resource path."
                )
                self._update_audio_shortlist_actions()
                return
            self.soundtrack_button.setEnabled(
                self.host.source_ready and not self._busy
            )
            count = self.page.total if self.host.source_ready else 0
            query_current = self._catalog_query_is_current()
            enabled = self._catalog_page_actions_ready() and 1 <= count <= 256
            self.export_matching_button.setEnabled(enabled)
            soundtrack = (
                self.scope_filter.currentData() == "streaming_ranges"
                and self.family_filter.currentData() == "music"
                and not self.search.text().strip()
                and self.status_filter.currentData() is None
            )
            if enabled:
                label = (
                    "Export soundtrack && music"
                    if soundtrack else "Export matching audio"
                )
                self.export_matching_button.setText(f"{label} ({count:,})…")
                self.export_matching_button.setToolTip(
                    f"Export all {count:,} filtered rows as one all-or-nothing ZIP. "
                    "The manifest distinguishes staged user WAVs from audio "
                    "derived from your own game copy."
                    + (
                        " The complete soundtrack/music WAV payload is about "
                        f"{SOUNDTRACK_WAV_PAYLOAD_BYTES / 1024 ** 3:.2f} GiB; "
                        "allow roughly 3 GiB of temporary free space."
                        if soundtrack else ""
                    )
                )
            else:
                self.export_matching_button.setText("Export matching audio…")
                self.export_matching_button.setToolTip(
                    "Load your NFL 2K5 XISO first."
                    if not self.host.source_ready else
                    "Updating results. This action will unlock when the visible page "
                    "matches the search and filters."
                    if not query_current else
                    "No audio rows match the current filters."
                    if count == 0 else
                    f"{count:,} rows match; narrow search, family, or status to "
                    "256 or fewer before exporting."
                )
            self._update_audio_shortlist_actions()

        def _audio_status_texts(
            self,
            asset: (
                Nfl2k5AudioAsset
                | Nfl2k5StreamingAudioBank
                | Nfl2k5StreamingAudioRange
                | UniversalAssetRecord
            ),
            modified: set[str] | None = None,
        ) -> tuple[str, str]:
            modified_ids = (
                set(self.host.modified_audio_asset_ids)
                if modified is None else modified
            )
            if isinstance(asset, UniversalAssetRecord):
                base = "Export-only"
                detail = (
                    "Export-only • exact opaque wrapper/body • no decode or replacement"
                )
            elif isinstance(asset, Nfl2k5AudioAsset):
                base = (
                    "Modified" if asset.asset_id in modified_ids
                    else asset.edit_status
                )
                detail = (
                    f"{base} • exact Menu Back slot • runtime audibility unproved"
                    if asset.selector == MENU_BACK_SELECTOR else
                    f"{base} • exact physical slot • runtime cue meaning unproved"
                    if asset.editable else
                    "Export-only • no exact-slot writer"
                )
            elif isinstance(asset, Nfl2k5StreamingAudioBank):
                base = "Export-only"
                detail = "Export-only • raw aggregate; edit individual indexed ranges"
            else:
                base = (
                    "Modified" if asset.asset_id in modified_ids
                    else asset.edit_status
                )
                shared = len(self._affected_audio_owner_ids(asset)) > 1
                detail = (
                    "Modified • shared fixed streaming slot"
                    if asset.asset_id in modified_ids and shared else
                    "Modified • fixed streaming slot"
                    if asset.asset_id in modified_ids else
                    "Editable • strict PCM16 WAV • shared fixed streaming slot"
                    if asset.editable and shared else
                    "Editable • strict PCM16 WAV • fixed streaming slot"
                    if asset.editable else
                    "Export-only • no exact-range writer"
                )
            annotation = (
                self._annotation_for(asset.asset_id)
                if self._is_annotatable_asset(asset) else None
            )
            if annotation is not None:
                base = f"✎ Labeled · {base}"
                detail = f"Labeled project metadata • {detail}"
            if asset.asset_id in self._audio_shortlist:
                return f"★ Selected · {base}", f"★ Selected · {detail}"
            return base, detail

        def _affected_audio_owner_ids(
            self, asset: Nfl2k5StreamingAudioRange
        ) -> tuple[str, ...]:
            cached = self._affected_owner_cache.get(asset.asset_id)
            if cached is not None:
                return cached
            try:
                owners = tuple(self.host.audio_affected_asset_ids(asset.asset_id))
                if (
                    not owners
                    or asset.asset_id not in owners
                    or len(set(owners)) != len(owners)
                    or any(not isinstance(owner, str) or not owner for owner in owners)
                ):
                    raise ValidationError(
                        "The shared-slot owner list is incomplete or duplicated."
                    )
            except Exception as exc:
                owners = (asset.asset_id,)
                self._affected_owner_errors[asset.asset_id] = (
                    str(exc).strip() or exc.__class__.__name__
                )
            self._affected_owner_cache[asset.asset_id] = owners
            return owners

        def _update_audio_shortlist_badges(self) -> None:
            modified = set(self.host.modified_audio_asset_ids)
            visible = {asset.asset_id: asset for asset in self.page.assets}
            for row in range(self.table.rowCount()):
                first = self.table.item(row, 0)
                status_item = self.table.item(row, 5)
                if first is None or status_item is None:
                    continue
                asset = visible.get(str(first.data(Qt.UserRole)))
                if asset is None:
                    continue
                compact, detailed = self._audio_status_texts(asset, modified)
                status_item.setText(compact)
                status_item.setToolTip(detailed)

        def _shortlisted_audio_ids(self) -> tuple[str, ...]:
            return tuple(self._audio_shortlist)

        def _replacement_pack_ineligible_audio_ids(self) -> tuple[str, ...]:
            """Return listening-shortlist rows that cannot be batch-replaced."""

            return tuple(
                asset_id
                for asset_id, asset in self._audio_shortlist.items()
                if not asset.editable
            )

        def _set_audio_browser_filters_enabled(self, enabled: bool) -> None:
            """Keep the underlying catalog query visible but inert during review."""

            effective = enabled and not self._busy
            self.search.setEnabled(effective)
            self.scope_filter.setEnabled(effective)
            self.family_filter.setEnabled(effective)
            self.status_filter.setEnabled(effective)
            self.meaning_filter.setEnabled(
                effective and self.scope_filter.currentData() == "standalone"
            )
            self.labeled_only_filter.setEnabled(
                self._annotation_capable
                and effective
                and self.scope_filter.currentData() in {
                    PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming_ranges",
                }
            )

        def _toggle_audio_shortlist_review(self) -> None:
            if self._busy:
                return
            if self._shortlist_reviewing:
                self._leave_audio_shortlist_review()
                return
            if not self._audio_shortlist or not self.host.source_ready or self._busy:
                return
            self._search_timer.stop()
            self._catalog_offset_before_review = self.offset
            self._catalog_selection_before_review = self.selected_asset_id
            self._shortlist_reviewing = True
            self.offset = 0
            self._set_audio_browser_filters_enabled(False)
            self.refresh(keep_selection=False)

        def _leave_audio_shortlist_review(self) -> None:
            if self._busy or not self._shortlist_reviewing:
                return
            self._shortlist_reviewing = False
            self.offset = self._catalog_offset_before_review
            self._set_selected_asset_id(self._catalog_selection_before_review)
            self._set_audio_browser_filters_enabled(True)
            self.refresh(keep_selection=True)

        def _move_shortlisted_audio(self, delta: int) -> None:
            if self._busy or not self._shortlist_reviewing or delta not in {-1, 1}:
                return
            selected = self._selected_asset()
            if selected is None or selected.asset_id not in self._audio_shortlist:
                return
            ordered = list(self._audio_shortlist.items())
            current = next(
                index for index, (asset_id, _asset) in enumerate(ordered)
                if asset_id == selected.asset_id
            )
            target = current + delta
            if target < 0 or target >= len(ordered):
                return
            ordered[current], ordered[target] = ordered[target], ordered[current]
            self._audio_shortlist = dict(ordered)
            self.offset = (target // self.page_size) * self.page_size
            self._set_selected_asset_id(selected.asset_id)
            self.refresh(keep_selection=True)

        def _visible_playable_audio_assets(
            self,
        ) -> tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange, ...]:
            return tuple(
                asset for asset in self.page.assets
                if isinstance(
                    asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
                )
            )

        @staticmethod
        def _canonical_shortlist_asset_key(
            asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange,
        ) -> tuple[int, int, int, int, str]:
            """Return the catalog order shared by both playable audio scopes."""

            return (
                0 if isinstance(asset, Nfl2k5AudioAsset) else 1,
                asset.outer_index,
                asset.chunk_index,
                asset.range_index
                if isinstance(asset, Nfl2k5StreamingAudioRange) else -1,
                asset.asset_id,
            )

        def _validated_all_matching_audio(
            self,
        ) -> tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange, ...]:
            """Re-query and structurally validate one complete filtered result set."""

            if not self._catalog_query_is_current():
                raise ValidationError(
                    "Wait for the current audio search and filters to finish updating."
                )
            scope = str(self.scope_filter.currentData())
            if scope not in {
                PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming_ranges",
            }:
                raise ValidationError(
                    "Add all matching accepts standalone sounds or playable streaming "
                    "ranges, not complete banks or raw containers."
                )
            expected_total = self.page.total
            if type(expected_total) is not int or not 1 <= expected_total <= MAX_SHORTLIST_SIZE:
                raise ValidationError(
                    "Add all matching requires 1–256 rows in the current filtered view."
                )

            query: dict[str, object] = {
                "search": self.search.text(),
                "status": self.status_filter.currentData(),
                "offset": 0,
                "limit": MAX_SHORTLIST_SIZE,
                "scope": scope,
                "family": self.family_filter.currentData(),
                "meaning_status": self.meaning_filter.currentData(),
            }
            if self.labeled_only_filter.isChecked():
                query["labeled_only"] = True
            result = self.host.browse_audio(**query)
            try:
                assets = result.assets
                total = result.total
                offset = result.offset
                limit = result.limit
            except (AttributeError, TypeError) as exc:
                raise ValidationError(
                    "The audio catalog returned an invalid all-matching page."
                ) from exc
            if (
                not isinstance(assets, tuple)
                or type(total) is not int
                or type(offset) is not int
                or type(limit) is not int
                or offset != 0
                or limit != MAX_SHORTLIST_SIZE
                or total != expected_total
                or len(assets) != total
            ):
                raise ValidationError(
                    "The audio catalog's all-matching page/count changed or is "
                    "incomplete. No sounds were added."
                )

            expected_types = (
                (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
                if scope == PLAYABLE_AUDIO_SCOPE_ID else
                (Nfl2k5AudioAsset,) if scope == "standalone" else
                (Nfl2k5StreamingAudioRange,)
            )
            if any(type(asset) not in expected_types for asset in assets):
                raise ValidationError(
                    "The audio catalog returned a bank, raw container, or wrong-scope "
                    "row. No sounds were added."
                )
            asset_ids = tuple(asset.asset_id for asset in assets)
            if (
                any(not isinstance(asset_id, str) or not asset_id for asset_id in asset_ids)
                or len(set(asset_ids)) != len(asset_ids)
            ):
                raise ValidationError(
                    "The audio catalog returned a blank or duplicate sound ID. "
                    "No sounds were added."
                )
            canonical_keys = tuple(
                self._canonical_shortlist_asset_key(asset) for asset in assets
            )
            if canonical_keys != tuple(sorted(canonical_keys)):
                raise ValidationError(
                    "The audio catalog returned matching sounds out of canonical order. "
                    "No sounds were added."
                )

            current_offset = self.page.offset
            current_assets = self.page.assets
            if (
                type(current_offset) is not int
                or current_offset < 0
                or not isinstance(current_assets, tuple)
                or current_offset + len(current_assets) > total
                or tuple(asset.asset_id for asset in current_assets)
                != asset_ids[current_offset:current_offset + len(current_assets)]
            ):
                raise ValidationError(
                    "The audio catalog changed the matching page order. No sounds "
                    "were added."
                )

            family = self.family_filter.currentData()
            status = self.status_filter.currentData()
            meaning_status = self.meaning_filter.currentData()
            modified = set(self.host.modified_audio_asset_ids)
            words = tuple(
                word for word in self.search.text().casefold().split() if word
            )
            for asset in assets:
                if family is not None and asset.family_id != family:
                    raise ValidationError(
                        "The audio catalog returned a sound outside the family filter. "
                        "No sounds were added."
                    )
                if status == "Modified":
                    status_matches = asset.asset_id in modified
                else:
                    status_matches = status is None or asset.edit_status == status
                if not status_matches:
                    raise ValidationError(
                        "The audio catalog returned a sound outside the edit-status "
                        "filter. No sounds were added."
                    )
                if (
                    meaning_status is not None
                    and (
                        not isinstance(asset, Nfl2k5AudioAsset)
                        or standalone_runtime_meaning_status(asset) != meaning_status
                    )
                ):
                    raise ValidationError(
                        "The audio catalog returned a sound outside the meaning-"
                        "confidence filter. No sounds were added."
                    )
                haystack = (
                    audio_search_text(asset)
                    if isinstance(asset, Nfl2k5AudioAsset)
                    else audio_range_search_text(asset)
                )
                annotation = self._annotation_for(asset.asset_id)
                if self.labeled_only_filter.isChecked() and annotation is None:
                    raise ValidationError(
                        "The audio catalog returned an unlabeled sound while Labeled "
                        "only is active. No sounds were added."
                    )
                annotation_haystack = (
                    f"{annotation.title} {annotation.note}".casefold()
                    if annotation is not None else ""
                )
                if words and not all(
                    word in haystack or word in annotation_haystack
                    for word in words
                ):
                    raise ValidationError(
                        "The audio catalog returned a sound outside the search filter. "
                        "No sounds were added."
                    )
            return assets

        def _update_audio_shortlist_actions(self) -> None:
            count = len(self._audio_shortlist)
            cleared_count = len(self._cleared_audio_shortlist)
            selected = self._selected_asset()
            selected_playable = isinstance(
                selected, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            )
            selected_added = bool(
                selected_playable and selected
                and selected.asset_id in self._audio_shortlist
            )
            ready = self.host.source_ready and not self._busy
            catalog_ready = self._catalog_page_actions_ready()
            self.shortlist_count_label.setText(f"Selected {count} / 256")
            self.shortlist_clear_button.setEnabled(
                ready and (count > 0 or cleared_count > 0)
            )
            self.shortlist_clear_button.setText(
                "Clear" if count else
                "Undo" if cleared_count else
                "Clear"
            )
            self.shortlist_clear_button.setAccessibleName(
                "Clear audio shortlist" if count or not cleared_count else
                f"Restore the {cleared_count} sounds cleared from the audio shortlist"
            )
            self.shortlist_clear_button.setToolTip(
                f"Clear these {count} selected sounds. You can undo this until the "
                "next shortlist change or source load."
                if count else
                f"Restore all {cleared_count} cleared sounds in their original order."
                if cleared_count else
                "Add sounds before clearing the shortlist."
            )
            self.shortlist_review_button.setEnabled(
                ready and (count > 0 or self._shortlist_reviewing)
            )
            self.shortlist_review_button.setText(
                "Back to browser"
                if self._shortlist_reviewing else
                f"Review selected ({count})" if count else
                "Review selected"
            )
            self.shortlist_review_button.setToolTip(
                "Return to the catalog with its search, filters, page, and selection restored."
                if self._shortlist_reviewing else
                f"Review, play, remove, and reorder these {count} selected sounds."
                if count else
                "Add sounds first, then review the complete ordered shortlist."
            )
            self.export_shortlist_button.setEnabled(ready and count > 0)
            self.export_shortlist_button.setText(
                f"Export selected WAVs ({count})…"
                if count else "Export selected WAVs…"
            )
            self.export_shortlist_button.setToolTip(
                f"Export these {count} hand-picked sounds as one transactional "
                "WAV ZIP."
                if count else
                "Add up to 256 standalone sounds or playable streaming ranges first."
            )
            self.shortlist_toggle_button.setText(
                "Remove selected sound" if selected_added else "Add selected sound"
            )
            self.shortlist_toggle_button.setEnabled(
                ready and selected_playable and (selected_added or count < 256)
            )
            self.shortlist_toggle_button.setToolTip(
                "Remove this sound from the session-only shortlist."
                if selected_added else
                "The shortlist is full. Remove a sound before adding another."
                if selected_playable and count >= 256 else
                "Add this sound to a shortlist that survives searches, pages, and "
                "scope changes."
                if selected_playable else
                "Raw BANK/ABNK/WBNK containers are opaque export-only resources "
                "and cannot enter a playable-sound shortlist."
                if isinstance(selected, UniversalAssetRecord) else
                "Complete streaming banks are excluded; choose a standalone sound "
                "or an indexed streaming range."
                if isinstance(selected, Nfl2k5StreamingAudioBank) else
                "Choose a playable sound first."
            )
            additions = tuple(
                asset for asset in self._visible_playable_audio_assets()
                if asset.asset_id not in self._audio_shortlist
            )
            self.shortlist_page_button.setText(
                "Add this page"
                if self._shortlist_reviewing else
                "Add this page"
                if not self._catalog_query_is_current() else
                f"Add this page ({len(additions)})"
                if additions else "Add this page"
            )
            self.shortlist_page_button.setEnabled(
                catalog_ready
                and bool(additions) and count < 256
            )
            self.shortlist_page_button.setToolTip(
                "Return to the audio browser to add another page."
                if self._shortlist_reviewing else
                "Updating results. This action will unlock when the visible page "
                "matches the search and filters."
                if not self._catalog_query_is_current() else
                "Raw BANK/ABNK/WBNK containers are opaque export-only resources "
                "and cannot enter a playable-sound shortlist."
                if self.scope_filter.currentData() == "raw_containers" else
                f"This would exceed the 256-sound limit; {256 - count} spaces remain."
                if additions and count + len(additions) > 256 else
                f"Add {len(additions)} playable sounds from this page."
                if additions else
                "Complete banks are excluded because a bank is not one playable "
                "sound."
                if self.page.assets else
                "No playable sounds are visible on this page."
            )
            scope = str(self.scope_filter.currentData())
            matching_count = self.page.total if self.host.source_ready else 0
            matching_scope = scope in {
                PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming_ranges",
            }
            self.shortlist_matching_button.setText(
                f"Add all matching ({matching_count:,})"
                if self._catalog_query_is_current()
                and matching_scope and 1 <= matching_count <= MAX_SHORTLIST_SIZE
                else "Add all matching"
            )
            self.shortlist_matching_button.setEnabled(
                catalog_ready
                and matching_scope
                and 1 <= matching_count <= MAX_SHORTLIST_SIZE
                and count < MAX_SHORTLIST_SIZE
            )
            self.shortlist_matching_button.setToolTip(
                "Return to the audio browser to add its filtered results."
                if self._shortlist_reviewing else
                "Load your NFL 2K5 XISO first."
                if not self.host.source_ready else
                "Wait for the current audio task to finish."
                if self._busy else
                "Updating results. This action will unlock when the visible page "
                "matches the search and filters."
                if not self._catalog_query_is_current() else
                "Complete streaming banks are not individual sounds. Choose "
                "Playable streaming ranges first."
                if scope == "streaming" else
                "Raw BANK/ABNK/WBNK containers cannot enter a playable-sound "
                "shortlist."
                if scope == "raw_containers" else
                "No audio rows match the current filters."
                if matching_count == 0 else
                f"{matching_count:,} rows match; narrow search, family, edit status, "
                "or meaning confidence to 256 or fewer."
                if matching_count > MAX_SHORTLIST_SIZE else
                "The shortlist is full. Remove a sound before adding more."
                if count >= MAX_SHORTLIST_SIZE else
                f"Add all {matching_count:,} matching sounds in canonical filtered "
                "order. Sounds already selected stay selected once."
            )
            self.shortlist_move_up_button.setVisible(self._shortlist_reviewing)
            self.shortlist_move_down_button.setVisible(self._shortlist_reviewing)
            selected_index = (
                tuple(self._audio_shortlist).index(selected.asset_id)
                if selected_added and selected is not None else -1
            )
            self.shortlist_move_up_button.setEnabled(
                ready and self._shortlist_reviewing and selected_index > 0
            )
            self.shortlist_move_down_button.setEnabled(
                ready and self._shortlist_reviewing
                and 0 <= selected_index < count - 1
            )
            self._update_replacement_pack_actions()

        def _update_replacement_pack_actions(self, *_args: object) -> None:
            """Bind template export to all standalone, shortlist, or legacy mode."""

            if self._busy:
                self.replacement_pack_contents.setEnabled(False)
                self.replacement_pack_container.setEnabled(False)
                self.export_replacement_template_button.setEnabled(False)
                self.import_replacement_pack_button.setEnabled(False)
                return
            count = len(self._audio_shortlist)
            ineligible_count = len(self._replacement_pack_ineligible_audio_ids())
            content_mode = str(self.replacement_pack_contents.currentData())
            all_mode = content_mode == "all_standalone"
            selected_mode = content_mode == "shortlist"
            batch_export = callable(
                getattr(self.host, "export_audio_replacement_template", None)
            )
            batch_import = callable(
                getattr(self.host, "import_audio_replacement_pack", None)
            )
            batch_preflight = callable(
                getattr(self.host, "preflight_audio_replacement_pack", None)
            )
            batch_ready = self.host.source_ready and not self._busy
            self.replacement_pack_shortlist_count.setText(
                f"Shortlist: {count} selected · {ineligible_count} Export-only"
                if ineligible_count else
                f"Shortlist: {count} selected"
            )
            self.replacement_pack_shortlist_count.setAccessibleDescription(
                (
                    f"{count} sounds are currently selected; {ineligible_count} are "
                    "Export-only and must be removed before creating a replacement "
                    "pack."
                    if ineligible_count else
                    f"{count} sounds are currently selected, in order, for a "
                    "shortlist replacement pack."
                )
                if count else
                "No sounds are currently selected for a shortlist replacement pack."
            )
            self.replacement_pack_shortlist_count.setEnabled(selected_mode)
            self.replacement_pack_contents.setEnabled(batch_ready and batch_export)
            self.replacement_pack_container.setEnabled(
                batch_ready and (batch_export or batch_import)
            )
            can_export = bool(
                batch_ready
                and batch_export
                and (not selected_mode or (count > 0 and ineligible_count == 0))
            )
            self.export_replacement_template_button.setEnabled(can_export)
            self.export_replacement_template_button.setText(
                f"Export shortlist template ({count})…"
                if selected_mode else
                "Export all-850 + cue map…"
                if all_mode else
                "Export legacy 153-cue template…"
            )
            self.export_replacement_template_button.setAccessibleName(
                (
                    f"Export the ordered {count}-sound shortlist replacement template"
                    if count else
                    "Export the ordered audio shortlist replacement template"
                )
                if selected_mode else
                "Export the current v4 all-850 standalone audio template with its "
                "spreadsheet-safe read-only cue map"
                if all_mode else
                "Export the backward-compatible legacy 153-cue audio replacement template"
            )
            if not batch_export:
                export_tooltip = (
                    "This host does not provide the batch replacement-pack workflow."
                )
            elif selected_mode and ineligible_count:
                export_tooltip = (
                    f"Remove {ineligible_count} Export-only sound"
                    f"{'s' if ineligible_count != 1 else ''} first. Replacement "
                    "packs accept only Editable sounds; Export selected WAVs remains "
                    "available for the complete listening shortlist."
                )
            elif selected_mode and count == 0:
                export_tooltip = (
                    "Add at least one Editable standalone sound or streaming range to "
                    "the audio shortlist before exporting this template."
                )
            elif selected_mode:
                export_tooltip = (
                    f"Export a metadata-only template for these {count} sounds in "
                    "their current shortlist order. Complete streaming banks and raw "
                    "bank containers remain excluded."
                )
            elif all_mode:
                export_tooltip = (
                    "Export the current v4 metadata-only template for all 850 standalone "
                    "sounds. Its spreadsheet-safe, read-only AUDIO-CUE-MAP.csv lists "
                    "names, current status, exact WAV contracts, and replacement paths. "
                    "It contains zero retail WAVs. Add exact streaming ranges through "
                    "Selected shortlist; whole streaming banks remain excluded."
                )
            else:
                export_tooltip = (
                    "Export the backward-compatible v1 metadata-only map for the "
                    "original 152 fixed-AUDO cues plus Menu Back. Existing legacy packs "
                    "remain import-compatible; use All standalone sounds for the current "
                    "complete 850-sound workflow."
                )
            self.export_replacement_template_button.setToolTip(export_tooltip)
            self.import_replacement_pack_button.setEnabled(
                batch_ready and batch_import and batch_preflight
            )
            self.import_replacement_pack_button.setToolTip(
                "Choose the folder or ZIP format above. The manifest automatically "
                "detects current v4 all-850 packs, old v3 all-850 packs, v2 shortlists, "
                "and v1 legacy packs. Preview fully validates the read-only cue map, "
                "every supplied WAV, linked aliases, and the current project without "
                "staging anything. You must explicitly Apply before the exact pack is "
                "reopened, revalidated, and staged as one Undo action. Templates and "
                "projects contain no retail WAVs."
                if batch_import and batch_preflight else
                "This host does not provide the safe preview-and-confirm replacement-pack "
                "workflow."
            )

        @staticmethod
        def _duration(seconds: float) -> str:
            minutes = int(seconds // 60)
            remainder = seconds - minutes * 60
            return f"{minutes}:{remainder:04.1f}" if minutes else f"{remainder:.2f}s"

        def _selected_asset(
            self,
        ) -> (
            Nfl2k5AudioAsset
            | Nfl2k5StreamingAudioBank
            | Nfl2k5StreamingAudioRange
            | UniversalAssetRecord
            | None
        ):
            if self.selected_asset_id is None:
                return None
            return next(
                (asset for asset in self.page.assets
                 if asset.asset_id == self.selected_asset_id),
                None,
            )

        @staticmethod
        def _waveform_asset_is_playable(
            asset: (
                Nfl2k5AudioAsset
                | Nfl2k5StreamingAudioBank
                | Nfl2k5StreamingAudioRange
                | UniversalAssetRecord
                | None
            ),
        ) -> bool:
            """Only one decoded cue or range owns one waveform."""

            return isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            )

        def _cancel_audio_waveform(self, *, clear_selection: bool = True) -> None:
            """Fence one private read; in-process source decoding is not killable."""

            self._waveform_generation += 1
            if self._waveform_request is not None:
                self._waveform_request.cancel()
            if clear_selection:
                self._waveform_selected_asset_id = None

        def _configure_audio_waveform(
            self,
            asset: (
                Nfl2k5AudioAsset
                | Nfl2k5StreamingAudioBank
                | Nfl2k5StreamingAudioRange
                | UniversalAssetRecord
                | None
            ),
            *,
            force: bool = False,
        ) -> None:
            """Describe the selected row without decoding or starting playback."""

            asset_id = asset.asset_id if asset is not None else None
            if (
                not force
                and self._waveform_request is None
                and asset_id == self._waveform_selected_asset_id
                and self.waveform_preview.state == "ready"
            ):
                self.load_waveform_button.setText("Reload waveform")
                self.load_waveform_button.setEnabled(
                    bool(self.host.source_ready and not self._busy)
                )
                return
            self._waveform_selected_asset_id = asset_id
            if self._waveform_request is not None:
                self.waveform_preview.set_empty(
                    "The previous private request was cancelled and is finishing. "
                    "You can keep browsing; its result will be discarded."
                )
                self.load_waveform_button.setText("Cancelling previous…")
                self.load_waveform_button.setEnabled(False)
                return
            self.load_waveform_button.setText("Load waveform")
            if not self.host.source_ready:
                self.waveform_preview.set_unavailable(
                    "Load your NFL 2K5 XISO before preparing a waveform."
                )
                self.load_waveform_button.setEnabled(False)
                return
            if asset is None:
                self.waveform_preview.set_unavailable(
                    "Choose a standalone sound or playable streaming range."
                )
                self.load_waveform_button.setEnabled(False)
                return
            if isinstance(asset, UniversalAssetRecord):
                self.waveform_preview.set_unavailable(
                    "This opaque raw container has no decoded playable-sound route."
                )
                self.load_waveform_button.setEnabled(False)
                return
            if isinstance(asset, Nfl2k5StreamingAudioBank):
                self.waveform_preview.set_unavailable(
                    "A complete streaming bank contains many sounds and is not one "
                    "waveform. Choose one of its Playable Streaming Ranges."
                )
                self.load_waveform_button.setEnabled(False)
                return
            self.waveform_preview.set_empty(
                "Waveforms are never loaded automatically. Click Load waveform to "
                "read this sound through the private current-WAV route; playback "
                "will not start and your project will not change."
            )
            self.load_waveform_button.setToolTip(
                "Draw a bounded, read-only waveform from this sound's private current "
                "PCM16 WAV. Source decoding runs in-process and cannot be interrupted; "
                "Cancel discards the result at the next safe boundary."
            )
            self.load_waveform_button.setEnabled(not self._busy)

        def _load_audio_waveform(self) -> None:
            """Start or cancel one explicit, selection-owned waveform request."""

            if self._waveform_request is not None:
                self._waveform_request.cancel()
                self.waveform_preview.set_empty(
                    "Cancelling the private waveform read. In-process source decoding "
                    "finishes safely before its result is discarded."
                )
                self.load_waveform_button.setText("Cancelling…")
                self.load_waveform_button.setEnabled(False)
                return
            asset = self._selected_asset()
            if (
                not self._waveform_asset_is_playable(asset)
                or self._busy
                or not self.host.source_ready
            ):
                self._configure_audio_waveform(asset, force=True)
                return
            assert isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            )
            request = WaveformRequest()
            self._waveform_request = request
            self._waveform_generation += 1
            generation = self._waveform_generation
            source_epoch = self._catalog_source_epoch
            asset_id = asset.asset_id
            self._waveform_selected_asset_id = asset_id
            self.waveform_preview.set_loading(
                "Preparing only this sound through the private current-WAV route…"
            )
            self.load_waveform_button.setText("Cancel waveform")
            self.load_waveform_button.setEnabled(True)
            self.load_waveform_button.setToolTip(
                "Cancel this read at its next safe in-process boundary and discard "
                "the waveform result. Source decoding itself runs in-process and "
                "cannot be interrupted."
            )

            def operation(progress: ProgressSink) -> tuple[str, object | None]:
                try:
                    request.check()

                    def guarded_progress(
                        stage: str, completed: int, total: int
                    ) -> None:
                        request.check()
                        progress(stage, completed, total)

                    path = self.host.prepare_audio(asset_id, guarded_progress)
                    request.check()
                    envelope = read_pcm16_waveform(
                        Path(path),
                        cancelled=lambda: request.cancelled,
                    )
                    request.check()
                    return "ready", envelope
                except WaveformCancelled:
                    return "cancelled", None
                except Exception as exc:
                    return "error", str(exc).strip() or exc.__class__.__name__

            self._run(
                operation,
                lambda result: self._audio_waveform_complete(
                    request,
                    generation,
                    source_epoch,
                    asset_id,
                    result,
                ),
            )

        def _audio_waveform_complete(
            self,
            request: WaveformRequest,
            generation: int,
            source_epoch: int,
            asset_id: str,
            result: object,
        ) -> None:
            """Publish only the still-current row/source request inline."""

            if self._waveform_request is request:
                self._waveform_request = None
            selected = self._selected_asset()
            if (
                request.cancelled
                or generation != self._waveform_generation
                or source_epoch != self._catalog_source_epoch
                or selected is None
                or selected.asset_id != asset_id
            ):
                self._configure_audio_waveform(selected, force=True)
                return
            try:
                state, value = result  # type: ignore[misc]
            except (TypeError, ValueError):
                state, value = "error", "The waveform worker returned an invalid result"
            if state == "ready" and isinstance(value, WaveformEnvelope):
                self.waveform_preview.set_envelope(value)
                self.load_waveform_button.setText("Reload waveform")
                self.load_waveform_button.setEnabled(not self._busy)
                return
            if state == "cancelled":
                self._configure_audio_waveform(selected, force=True)
                return
            message = str(value or "The selected sound could not be read as PCM16 WAV")
            self.waveform_preview.set_error(message)
            self.load_waveform_button.setText("Retry waveform")
            self.load_waveform_button.setEnabled(not self._busy)

        def _preview_request_is_current(
            self, request: tuple[int, str]
        ) -> bool:
            """Bind a preview request to one selection and one source epoch."""

            return bool(
                request == self._preview_request
                and self.selected_asset_id == request[1]
                and self.host.source_ready
            )

        def _invalidate_audio_preview(self) -> None:
            """Invalidate pending work and stop only Mod Studio's own player."""

            self._preview_epoch += 1
            self._preview_request = None
            self._prepared_preview = None
            if self._audio_process.state() != QProcess.NotRunning:
                self._audio_process.kill()
            else:
                self._playing_preview_request = None
            self.play_button.setText("Play")

        def invalidate_audio_content(self) -> None:
            """Forget every same-ID playback/waveform view of current audio bytes."""

            self._invalidate_audio_preview()
            self._cancel_audio_waveform()
            self._configure_audio_waveform(
                self._selected_asset(), force=True
            )
            self._refresh_controls()

        def invalidate_preview_for_source_change(self) -> None:
            """Public source-transition boundary; identical asset IDs stay stale."""

            self._search_timer.stop()
            self._source_change_query_was_current = self._catalog_query_is_current()
            self.invalidate_audio_content()
            self.waveform_preview.set_unavailable(
                "Changing game sources. Any old waveform result will be discarded."
            )
            self.load_waveform_button.setText("Load waveform")
            self.load_waveform_button.setEnabled(False)

        def recover_after_source_change_failure(self) -> None:
            """Restore the old catalog after a transactional source load refuses."""

            query_was_current = self._source_change_query_was_current
            self._source_change_query_was_current = None
            self._search_timer.stop()
            if self.host.source_ready:
                if query_was_current:
                    self._restore_applied_query_presentation()
                    self._configure_audio_waveform(
                        self._selected_asset(), force=True
                    )
                    self._refresh_controls()
                    return
                self.offset = 0
                self.refresh(keep_selection=False)
                return
            self.page = AudioPage((), 0, 0, self.page_size)
            self.offset = 0
            self._applied_query_token = None
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self._set_selected_asset_id(None)
            self._show_asset(None)
            self.count_label.setText("Load your NFL 2K5 XISO")
            self.range_label.setText("0 results")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self._update_collection_actions()

        def _set_selected_asset_id(self, asset_id: str | None) -> bool:
            """Set the effective selection and invalidate preview only on change."""

            if asset_id is not None and (
                type(asset_id) is not str or not asset_id
            ):
                raise ValidationError("Selected audio asset ID must be non-empty")
            if asset_id == self.selected_asset_id:
                return False
            self._cancel_audio_waveform()
            self.selected_asset_id = asset_id
            self._invalidate_audio_preview()
            return True

        def _start_prepared_preview(
            self,
            prepared: tuple[tuple[int, str], str, tuple[str, ...]],
        ) -> None:
            """Start now or queue until an older controlled process exits."""

            request, program, arguments = prepared
            if not self._preview_request_is_current(request):
                return
            if self._audio_process.state() != QProcess.NotRunning:
                self._prepared_preview = prepared
                self._audio_process.kill()
                return
            self._prepared_preview = None
            self._playing_preview_request = request
            self._audio_process.start(program, list(arguments))
            self.play_button.setText("Stop")

        def _audio_process_finished(self, *_args: object) -> None:
            """Finish the old run, then start a still-current queued preview."""

            finished_request = self._playing_preview_request
            self._playing_preview_request = None
            prepared = self._prepared_preview
            if prepared is not None and self._preview_request_is_current(
                prepared[0]
            ):
                self._prepared_preview = None
                self._start_prepared_preview(prepared)
                return
            self._prepared_preview = None
            if (
                finished_request is not None
                and self._preview_request == finished_request
            ):
                self._preview_request = None
            if self._preview_request is None:
                self.play_button.setText("Play")

        def _audio_process_failed(self, _error: object) -> None:
            """Report only a failure belonging to the still-current preview."""

            failed_request = self._playing_preview_request
            if (
                failed_request is None
                or failed_request != self._preview_request
                or not self._preview_request_is_current(failed_request)
            ):
                # Qt emits ``errorOccurred(FailedToStart)`` after returning to
                # NotRunning and does not emit ``finished``. Drain that exact
                # stale-process case so a newer prepared request is not stranded.
                # Kill/crash errors arrive while still Running and are followed
                # by ``finished``, so those continue through the normal signal.
                if self._audio_process.state() == QProcess.NotRunning:
                    self._audio_process_finished()
                return
            self._playing_preview_request = None
            self._prepared_preview = None
            self._preview_request = None
            self.play_button.setText("Play")
            detail = self._audio_process.errorString().strip()
            self.error_raised.emit(
                "Audio preview could not start with the configured Linux player. "
                + (detail or "Try installing ffplay, paplay, or aplay.")
            )

        @staticmethod
        def _is_annotatable_asset(asset: object) -> bool:
            return isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            )

        def _annotation_for(self, asset_id: str) -> AudioCueAnnotation | None:
            getter = getattr(self.host, "audio_annotation", None)
            if not callable(getter):
                return None
            value = getter(asset_id)
            if value is None:
                return None
            if not isinstance(value, AudioCueAnnotation):
                raise ValidationError(
                    "The audio annotation store returned an invalid label record."
                )
            if value.cue_id != asset_id:
                raise ValidationError(
                    "The audio annotation belongs to a different logical cue."
                )
            return value

        def _populate_annotation_editor(self, asset: object | None) -> None:
            annotation = None
            draft: tuple[str, str] | None = None
            if self._is_annotatable_asset(asset):
                draft = self._annotation_drafts.get(asset.asset_id)  # type: ignore[union-attr]
                try:
                    annotation = self._annotation_for(asset.asset_id)  # type: ignore[union-attr]
                except Exception as exc:
                    self.error_raised.emit(str(exc).strip() or exc.__class__.__name__)
            self._annotation_loading = True
            self.annotation_title_edit.blockSignals(True)
            self.annotation_note_edit.blockSignals(True)
            try:
                self.annotation_title_edit.setText(
                    draft[0] if draft is not None else
                    annotation.title if annotation is not None else ""
                )
                self.annotation_note_edit.setPlainText(
                    draft[1] if draft is not None else
                    annotation.note if annotation is not None else ""
                )
            finally:
                self.annotation_title_edit.blockSignals(False)
                self.annotation_note_edit.blockSignals(False)
                self._annotation_loading = False
            self._refresh_annotation_controls()

        def _annotation_fields_changed(self, *_args: object) -> None:
            if self._annotation_loading:
                return
            note = self.annotation_note_edit.toPlainText()
            if len(note) > MAX_NOTE_CHARS:
                self.annotation_note_edit.blockSignals(True)
                try:
                    self.annotation_note_edit.setPlainText(note[:MAX_NOTE_CHARS])
                    cursor = self.annotation_note_edit.textCursor()
                    cursor.movePosition(cursor.End)
                    self.annotation_note_edit.setTextCursor(cursor)
                finally:
                    self.annotation_note_edit.blockSignals(False)
            self._remember_annotation_draft()
            self._refresh_annotation_controls()

        def _remember_annotation_draft(self) -> None:
            """Retain unsaved cue text while rows, filters, and pages change."""

            if self._annotation_loading or not self._annotation_capable:
                return
            asset = self._selected_asset()
            if not self._is_annotatable_asset(asset):
                return
            asset_id = asset.asset_id  # type: ignore[union-attr]
            title = self.annotation_title_edit.text()
            note = self.annotation_note_edit.toPlainText()
            try:
                existing = self._annotation_for(asset_id)
            except Exception:
                self._annotation_drafts[asset_id] = (title, note)
                return
            current = (
                (existing.title, existing.note)
                if existing is not None else ("", "")
            )
            if (title.strip(), note.strip()) == current:
                self._annotation_drafts.pop(asset_id, None)
            else:
                self._annotation_drafts[asset_id] = (title, note)

        def _refresh_annotation_controls(self) -> None:
            asset = self._selected_asset()
            playable = self._is_annotatable_asset(asset)
            getter = getattr(self.host, "audio_annotation", None)
            setter = getattr(self.host, "set_audio_annotation", None)
            clearer = getattr(self.host, "clear_audio_annotation", None)
            supported = self._annotation_capable and playable and callable(getter)
            existing = None
            if supported and asset is not None:
                try:
                    existing = self._annotation_for(asset.asset_id)
                except Exception:
                    supported = False
            enabled = bool(self.host.source_ready and not self._busy and supported)
            self.annotation_title_edit.setEnabled(enabled)
            self.annotation_note_edit.setEnabled(enabled)
            title = self.annotation_title_edit.text().strip()
            note = self.annotation_note_edit.toPlainText().strip()
            current = (
                (existing.title, existing.note)
                if existing is not None else ("", "")
            )
            changed = (title, note) != current
            drafted = bool(
                asset is not None and asset.asset_id in self._annotation_drafts
            )
            self.save_annotation_button.setEnabled(
                enabled and callable(setter) and bool(title or note) and changed
            )
            self.clear_annotation_button.setEnabled(
                enabled and callable(clearer) and existing is not None
            )
            self.annotation_title_count.setText(
                f"{len(self.annotation_title_edit.text()):,} / {MAX_TITLE_CHARS:,}"
            )
            self.annotation_note_count.setText(
                f"{len(self.annotation_note_edit.toPlainText()):,} / {MAX_NOTE_CHARS:,}"
            )
            self.annotation_help.setText(
                "Unsaved draft retained while you browse — choose Save label to "
                "write it into the project."
                if supported and drafted and changed else
                "Project metadata only — searchable and shareable, but never written "
                "into the game or counted as a build edit."
                if supported else
                "Custom labels are available for standalone sounds and exact playable "
                "streaming ranges after an NFL 2K5 project is loaded."
            )

        def _save_selected_annotation(self) -> None:
            asset = self._selected_asset()
            method = getattr(self.host, "set_audio_annotation", None)
            if (
                self._busy or not self._is_annotatable_asset(asset)
                or not callable(method) or not self.save_annotation_button.isEnabled()
            ):
                return
            asset_id = asset.asset_id  # type: ignore[union-attr]
            title = self.annotation_title_edit.text().strip()
            note = self.annotation_note_edit.toPlainText().strip()

            def complete(value: object) -> None:
                self._annotation_drafts.pop(asset_id, None)
                changed = getattr(value, "changed", True)
                if changed is not False:
                    self.audio_annotation_changed.emit(asset_id)
                self.progress_label.setText(
                    getattr(value, "message", "Audio cue label saved")
                )
                self.refresh(keep_selection=True)

            self._run(
                lambda progress: method(asset_id, title, note, progress),
                complete,
            )

        def _clear_selected_annotation(self) -> None:
            asset = self._selected_asset()
            method = getattr(self.host, "clear_audio_annotation", None)
            if (
                self._busy or not self._is_annotatable_asset(asset)
                or not callable(method) or not self.clear_annotation_button.isEnabled()
            ):
                return
            asset_id = asset.asset_id  # type: ignore[union-attr]

            def complete(value: object) -> None:
                self._annotation_drafts.pop(asset_id, None)
                changed = getattr(value, "changed", True)
                if changed is not False:
                    self.audio_annotation_changed.emit(asset_id)
                self.progress_label.setText(
                    getattr(value, "message", "Audio cue label cleared")
                )
                self.refresh(keep_selection=True)

            self._run(
                lambda progress: method(asset_id, progress),
                complete,
            )

        def _selection_changed(self) -> None:
            if self._busy:
                return
            rows = self.table.selectionModel().selectedRows()
            if not rows:
                self._set_selected_asset_id(None)
                self._show_asset(None)
                return
            item = self.table.item(rows[0].row(), 0)
            self._set_selected_asset_id(str(item.data(Qt.UserRole)))
            self._show_asset(self._selected_asset())

        def _selected_complete_pack_path(self) -> str | None:
            """Resolve only the public authoring path for a standalone cue."""

            asset = self._selected_asset()
            if not isinstance(asset, Nfl2k5AudioAsset):
                return None
            path = self.host.audio_complete_pack_path(asset.asset_id)
            if type(path) is not str or not re.fullmatch(
                r"replacements/[0-9]{3}__selected-audio\.wav", path
            ):
                return None
            return path

        def _copy_selected_pack_path(self) -> None:
            """Copy on explicit activation; selection changes never touch clipboard."""

            path = self._selected_complete_pack_path()
            if path is None or not self.copy_pack_path_button.isEnabled():
                return
            QApplication.clipboard().setText(path)
            self.progress_label.setText("Copied all-850 replacement pack path")

        def _show_asset(
            self,
            asset: (
                Nfl2k5AudioAsset
                | Nfl2k5StreamingAudioBank
                | Nfl2k5StreamingAudioRange
                | UniversalAssetRecord
                | None
            ),
        ) -> None:
            self._configure_audio_waveform(asset)
            self._populate_annotation_editor(asset)
            if asset is None:
                self.asset_title.setText("Select a sound")
                self.status_label.setText("No sound selected")
                self.metadata_label.clear()
                self.ownership_label.clear()
                self.note_label.setText(
                    "Choose a row to see its format, ownership, and edit status."
                )
                self.note_label.setToolTip("")
            else:
                if isinstance(asset, UniversalAssetRecord):
                    self.asset_title.setText(f"{asset.kind} raw bank container")
                    self.status_label.setText("Export-only • opaque resource")
                    self.metadata_label.setText(
                        f"Format: raw {asset.kind} resource wrapper/body (.bin)\n"
                        f"Total span: {asset.raw_size:,} bytes • stored body: "
                        f"{asset.stored_size:,} bytes • 0x20-byte wrapper\n"
                        f"Outer {asset.outer_index} / chunk {asset.chunk_index} • "
                        f"chunk offset 0x{asset.chunk_offset:x}\n"
                        f"Outer ID {asset.outer_id} • outer head {asset.outer_head}\n"
                        f"{asset.asset_id}"
                    )
                    self.ownership_label.setText(
                        "Exact source-bound identity from the universal resource "
                        "index. Export copies this one verified wrapper/body only."
                    )
                    self.note_label.setText(
                        "The inner bank directory, cue names, codec references, "
                        "loops, and mixer rules are not decoded. This container can "
                        "be exported raw, but it cannot be played, replaced, or "
                        "added to the sound shortlist."
                    )
                    self.note_label.setToolTip(
                        "Raw exports contain retail bytes from your own game copy, "
                        "stay outside projects/recovery, and must not be redistributed."
                    )
                    self._refresh_controls()
                    self.detail_scroll.verticalScrollBar().setValue(0)
                    return
                modified = asset.asset_id in set(self.host.modified_audio_asset_ids)
                annotation = (
                    self._annotation_for(asset.asset_id)
                    if self._is_annotatable_asset(asset) else None
                )
                self.asset_title.setText(
                    annotation.title
                    if annotation is not None and annotation.title else asset.name
                )
                self.status_label.setText(
                    "Modified • Editable" if modified else (
                        "Export-only • raw aggregate; edit individual indexed ranges"
                        if isinstance(asset, Nfl2k5StreamingAudioBank)
                        else asset.edit_status
                    )
                )
                if isinstance(asset, Nfl2k5AudioAsset):
                    self.metadata_label.setText(
                        (
                            f"Game/catalog label: {asset.name}\n"
                            if annotation is not None else ""
                        ) +
                        f"{asset.family_label} • {asset.container_label}\n"
                        f"{asset.channels} channel • {asset.sample_rate:,} Hz • "
                        f"{asset.frame_count:,} frames • "
                        f"{self._duration(asset.duration_seconds)}\n"
                        f"Playable export: WAV (PCM16) • Source codec: Xbox IMA ADPCM\n"
                        f"Physical selector {asset.outer_index}:{asset.chunk_index}\n"
                        f"{asset.asset_id}"
                    )
                elif isinstance(asset, Nfl2k5StreamingAudioBank):
                    self.metadata_label.setText(
                        f"{asset.family_label} • {asset.container_label}\n"
                        f"{asset.entry_count:,} indexed ranges • "
                        f"{asset.sample_rate:,} Hz descriptor metadata\n"
                        f"Export: raw {asset.external_filename} "
                        f"({asset.external_size:,} bytes) • complete bank is not one cue\n"
                        f"Descriptor {asset.outer_index}:{asset.chunk_index} • "
                        f"external outer {asset.external_outer_index}\n"
                        f"{asset.asset_id}"
                    )
                else:
                    self.metadata_label.setText(
                        (
                            f"Game/catalog label: {asset.name}\n"
                            if annotation is not None else ""
                        ) +
                        f"{asset.family_label} • {asset.container_label}\n"
                        f"Range {asset.range_index:,} • {asset.stored_size:,} bytes • "
                        f"0x{asset.start:x}..0x{asset.end:x}\n"
                        f"Xbox IMA ADPCM • {asset.channels} channel • "
                        f"{asset.sample_rate:,} Hz • {asset.frame_count:,} frames • "
                        f"{self._duration(asset.duration_seconds)}\n"
                        "Playable export: PCM16 WAV • optional export: exact raw .bin\n"
                        f"Source bank: {asset.external_filename}\n"
                        f"Descriptor {asset.outer_index}:{asset.chunk_index} • "
                        f"external outer {asset.external_outer_index}\n"
                        f"{asset.asset_id}"
                    )
                owner_note = ""
                if isinstance(asset, Nfl2k5StreamingAudioRange):
                    owners = self._affected_audio_owner_ids(asset)
                    owner_error = self._affected_owner_errors.get(asset.asset_id)
                    if owner_error is not None:
                        owner_note = (
                            "\nShared-slot owner details are unavailable: "
                            f"{owner_error}"
                        )
                    else:
                        if len(owners) > 1:
                            owner_note = (
                                "\nShared physical slot — Replace, Revert, and Undo "
                                f"affect all {len(owners):,} logical owners:\n"
                                + "\n".join(f"• {owner}" for owner in owners)
                            )
                        elif owners:
                            owner_note = "\nThis physical slot has one logical owner."
                self.ownership_label.setText(
                    f"{asset.ownership_status}\n{asset.alias_status}{owner_note}"
                )
                if isinstance(asset, Nfl2k5StreamingAudioBank):
                    visible_note = (
                        "Complete bank: export raw only. Open Playable Streaming "
                        "Ranges to listen or export WAV."
                    )
                else:
                    visible_note = asset.action_note
                self.note_label.setText(visible_note)
                self.note_label.setToolTip(asset.action_note)
            self._refresh_controls()
            self.detail_scroll.verticalScrollBar().setValue(0)

        def _refresh_controls(self) -> None:
            asset = self._selected_asset()
            self._refresh_annotation_controls()
            ready = self.host.source_ready and not self._busy and asset is not None
            pack_path = self._selected_complete_pack_path()
            if pack_path is None:
                self.pack_path_label.clear()
                self.pack_path_card.hide()
                self.copy_pack_path_button.setEnabled(False)
            else:
                self.pack_path_label.setText(pack_path)
                self.pack_path_label.setAccessibleDescription(
                    f"Exact v4 all-850 template path: {pack_path}"
                )
                self.pack_path_card.show()
                self.copy_pack_path_button.setEnabled(ready)
            modified = bool(
                asset and asset.asset_id in set(self.host.modified_audio_asset_ids)
            )
            raw_container = isinstance(asset, UniversalAssetRecord)
            standalone = isinstance(asset, Nfl2k5AudioAsset)
            streaming_range = isinstance(asset, Nfl2k5StreamingAudioRange)
            playable = bool(
                standalone or streaming_range
            )
            if self._waveform_request is not None:
                if self._waveform_request.cancelled:
                    self.load_waveform_button.setText("Cancelling…")
                    self.load_waveform_button.setEnabled(False)
                else:
                    self.load_waveform_button.setText("Cancel waveform")
                    self.load_waveform_button.setEnabled(True)
            elif (
                playable
                and asset is not None
                and asset.asset_id == self._waveform_selected_asset_id
            ):
                self.load_waveform_button.setEnabled(ready)
            else:
                self.load_waveform_button.setEnabled(False)
            audio_editing_ready = bool(
                getattr(self.host, "audio_editing_ready", True)
            )
            self.play_button.setEnabled(ready and playable)
            self.export_button.setEnabled(ready)
            editable = bool(
                ready and (standalone or streaming_range)
                and asset and asset.editable
            )
            self.replace_button.setEnabled(editable)
            self.revert_button.setEnabled(editable and modified)
            self.export_button.setText(
                "Export"
                if asset is None else
                "Export Raw Container"
                if raw_container else
                "Export WAV" if standalone else
                "Export WAV / Raw"
                if isinstance(asset, Nfl2k5StreamingAudioRange) else
                "Export Raw Bank"
            )
            self.export_button.setToolTip(
                "Select an audio item"
                if asset is None else
                "Export this exact opaque resource wrapper/body as .bin."
                if raw_container else
                asset.export_format_label
            )
            self.play_button.setToolTip(
                "Play the privately decoded WAV"
                if playable else
                "This opaque raw container has no decoded playable-cue contract."
                if raw_container else
                "A complete bank is not one cue; choose an indexed range to play it."
            )
            self.replace_button.setToolTip(
                "Raw BANK/ABNK/WBNK replacement is not decoded or exposed."
                if raw_container else
                (
                    "The first audio replacement may take roughly 20–35 minutes "
                    "while Mod Studio reads your XISO and builds private safety "
                    "indexes. This happens once; your XISO stays read-only. "
                    "Progress appears below and no terminal steps are required.\n\n"
                    + asset.action_note
                )
                if editable and not audio_editing_ready and asset is not None else
                asset.action_note if asset is not None else "Select an audio item"
            )
            self.revert_button.setToolTip(
                "Restore the private original for this staged WAV"
                if modified else
                "This audio item has no staged replacement"
            )
            hint = (
                "Opaque raw container: export-only; decoding and replacement are unavailable"
                if raw_container else
                "A complete bank is an export-only aggregate; edit its individual indexed ranges"
                if isinstance(asset, Nfl2k5StreamingAudioBank) else
                "The first audio replacement may take roughly 20–35 minutes while "
                "Mod Studio reads your XISO and builds private safety indexes. This "
                "happens once; your XISO stays read-only."
                if editable and not audio_editing_ready else
                self._replacement_hint(asset) if asset is not None else
                "Select one of the Editable fixed-allocation sounds or ranges"
            )
            self.drop_zone.set_accepting(editable, hint)
            self._update_replacement_pack_actions()
            pagination_ready = self._pagination_query_ready()
            self.previous_button.setEnabled(self.page.has_previous and pagination_ready)
            self.next_button.setEnabled(self.page.has_next and pagination_ready)
            self._update_collection_actions()
            self._apply_operation_interlock()

        def _apply_operation_interlock(self) -> None:
            """While a worker owns the facade, leave only waveform Cancel live."""

            self._set_audio_browser_filters_enabled(
                not self._shortlist_reviewing
            )
            self.table.setEnabled(not self._busy)
            if not self._busy:
                return
            self._search_timer.stop()
            for button in self.findChildren(QPushButton):
                button.setEnabled(False)
            request = self._waveform_request
            if request is not None and not request.cancelled:
                self.load_waveform_button.setText("Cancel waveform")
                self.load_waveform_button.setEnabled(True)

        def _filters_changed(self, *_args: object) -> None:
            self._search_timer.stop()
            if self._busy or self._shortlist_reviewing:
                return
            self.offset = 0
            self.refresh(keep_selection=False)

        def _previous_page(self) -> None:
            if not self._pagination_query_ready():
                return
            self.offset = max(0, self.offset - self.page_size)
            self.refresh(keep_selection=False)

        def _next_page(self) -> None:
            if not self._pagination_query_ready():
                return
            self.offset += self.page_size
            self.refresh(keep_selection=False)

        def _toggle_audio_shortlist(self) -> None:
            if self._busy:
                return
            asset = self._selected_asset()
            if not isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            ):
                return
            if asset.asset_id in self._audio_shortlist:
                self._cleared_audio_shortlist = ()
                ordered_ids = tuple(self._audio_shortlist)
                removed_index = ordered_ids.index(asset.asset_id)
                del self._audio_shortlist[asset.asset_id]
                if self._shortlist_reviewing:
                    if not self._audio_shortlist:
                        self._leave_audio_shortlist_review()
                        return
                    remaining = tuple(self._audio_shortlist)
                    self._set_selected_asset_id(
                        remaining[min(removed_index, len(remaining) - 1)]
                    )
                    last_offset = (
                        (len(remaining) - 1) // self.page_size
                    ) * self.page_size
                    self.offset = min(self.offset, last_offset)
                    self.refresh(keep_selection=True)
                    return
            elif len(self._audio_shortlist) >= 256:
                QMessageBox.information(
                    self,
                    "Audio shortlist is full",
                    "A shortlist can contain up to 256 sounds. Remove one before "
                    "adding another.",
                )
                return
            else:
                self._cleared_audio_shortlist = ()
                self._audio_shortlist[asset.asset_id] = asset
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()

        def _add_visible_audio_to_shortlist(self) -> None:
            if not self._catalog_page_actions_ready():
                return
            additions = tuple(
                asset for asset in self._visible_playable_audio_assets()
                if asset.asset_id not in self._audio_shortlist
            )
            if not additions:
                return
            total = len(self._audio_shortlist) + len(additions)
            if total > 256:
                QMessageBox.information(
                    self,
                    "Too many sounds for one shortlist",
                    f"This page would bring the shortlist to {total:,} sounds, "
                    "above the 256-sound limit. No sounds were added. Remove sounds "
                    f"or use a narrower page; {256 - len(self._audio_shortlist)} "
                    "spaces remain.",
                )
                return
            self._cleared_audio_shortlist = ()
            for asset in additions:
                self._audio_shortlist[asset.asset_id] = asset
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()

        def _add_all_matching_audio_to_shortlist(self) -> None:
            """Append one complete, safely revalidated filtered result set."""

            if (
                self._shortlist_reviewing
                or self._busy
                or not self.host.source_ready
                or not self._catalog_query_is_current()
                or self.scope_filter.currentData()
                not in {
                    PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming_ranges",
                }
            ):
                return
            try:
                matching = self._validated_all_matching_audio()
            except Exception as exc:
                self.error_raised.emit(
                    "Add all matching was refused: "
                    + (str(exc).strip() or exc.__class__.__name__)
                )
                return
            additions = tuple(
                asset for asset in matching
                if asset.asset_id not in self._audio_shortlist
            )
            if not additions:
                self.progress_label.setText(
                    "All matching sounds are already selected"
                )
                self._update_audio_shortlist_actions()
                return
            total = len(self._audio_shortlist) + len(additions)
            if total > MAX_SHORTLIST_SIZE:
                QMessageBox.information(
                    self,
                    "Too many sounds for one shortlist",
                    f"All matching audio would bring the shortlist to {total:,} "
                    f"sounds, above the {MAX_SHORTLIST_SIZE}-sound limit. No sounds "
                    "were added. Remove selected sounds or narrow the current filters; "
                    f"{MAX_SHORTLIST_SIZE - len(self._audio_shortlist)} spaces remain.",
                )
                return
            self._cleared_audio_shortlist = ()
            for asset in additions:
                self._audio_shortlist[asset.asset_id] = asset
            self.progress_label.setText(
                f"Added {len(additions):,} matching "
                f"{'sound' if len(additions) == 1 else 'sounds'}"
            )
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()

        def _clear_audio_shortlist(self) -> None:
            if self._busy or not self.host.source_ready:
                return
            if not self._audio_shortlist:
                if not self._cleared_audio_shortlist:
                    return
                restored = self._cleared_audio_shortlist
                self._audio_shortlist = dict(restored)
                self._cleared_audio_shortlist = ()
                self.progress_label.setText(
                    f"Restored {len(restored):,} cleared "
                    f"{'sound' if len(restored) == 1 else 'sounds'}"
                )
                self._update_audio_shortlist_badges()
                self._update_audio_shortlist_actions()
                return
            cleared_count = len(self._audio_shortlist)
            self._cleared_audio_shortlist = tuple(self._audio_shortlist.items())
            self._audio_shortlist.clear()
            self.progress_label.setText(
                f"Cleared {cleared_count:,} selected "
                f"{'sound' if cleared_count == 1 else 'sounds'} — Undo is available"
            )
            if self._shortlist_reviewing:
                self._leave_audio_shortlist_review()
                return
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()

        def _play_selected(self) -> None:
            asset = self._selected_asset()
            if asset is None or not isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            ) or self._busy or not self.host.source_ready:
                return
            if (
                self._audio_process.state() != QProcess.NotRunning
                and self._playing_preview_request == self._preview_request
                and self._preview_request is not None
                and self._preview_request[1] == asset.asset_id
            ):
                self._invalidate_audio_preview()
                return

            self._preview_epoch += 1
            request = (self._preview_epoch, asset.asset_id)
            self._preview_request = request
            self._prepared_preview = None
            self.play_button.setText("Preparing…")

            def ready(value: object) -> None:
                if not self._preview_request_is_current(request):
                    return
                path = Path(value)  # type: ignore[arg-type]
                selected = audio_player_command(path)
                if selected is None:
                    if self._preview_request == request:
                        self._preview_request = None
                    self._prepared_preview = None
                    self.play_button.setText("Play")
                    self.error_raised.emit(
                        "No controllable WAV player is installed. Install ffplay, "
                        "paplay, or aplay, then press Play again. Mod Studio will not "
                        "open an external player it cannot stop."
                    )
                    return
                program, arguments = selected
                self._start_prepared_preview(
                    (request, str(program), tuple(arguments))
                )

            def failed(message: str) -> None:
                if not self._preview_request_is_current(request):
                    return
                self._preview_request = None
                self._prepared_preview = None
                self.play_button.setText("Play")
                self.error_raised.emit(message)

            self._run(
                lambda progress: self.host.prepare_audio(asset.asset_id, progress),
                ready,
                on_error=failed,
            )

        def _export_selected(self) -> None:
            if self._busy:
                return
            asset = self._selected_asset()
            if asset is None:
                return
            raw_container = isinstance(asset, UniversalAssetRecord)
            bank = isinstance(asset, Nfl2k5StreamingAudioBank)
            raw_range = isinstance(asset, Nfl2k5StreamingAudioRange)
            suggested = (
                asset.suggested_wav_filename if raw_range else asset.suggested_filename
            )
            filters = (
                "Raw BANK/ABNK/WBNK resource (*.bin)"
                if raw_container else
                "Wave audio (*.wav);;Raw streaming range (*.bin)"
                if raw_range else
                "Raw streaming bank (*.bin)" if bank else
                "Wave audio (*.wav)"
            )
            selected, selected_filter = QFileDialog.getSaveFileName(
                self,
                (
                    "Export raw bank container" if raw_container else
                    "Export streaming range" if raw_range else
                    "Export raw streaming bank" if bank else
                    "Export WAV"
                ),
                suggested,
                filters,
            )
            if not selected:
                return
            destination = Path(selected)
            if raw_container:
                if not destination.suffix:
                    destination = destination.with_suffix(".bin")
                if destination.suffix.casefold() != ".bin":
                    QMessageBox.information(
                        self,
                        "Choose a BIN filename",
                        "Raw BANK/ABNK/WBNK containers export as exact .bin files.",
                    )
                    return
                self._run(
                    lambda progress: self.host.export_resource(
                        asset, destination, progress
                    ),
                    lambda value: self.progress_label.setText(
                        f"Exported raw container {Path(value).name}"
                    ),
                )
            elif raw_range:
                raw_requested = destination.suffix.casefold() == ".bin" or (
                    not destination.suffix
                    and selected_filter.startswith("Raw streaming range")
                )
                if not destination.suffix:
                    destination = destination.with_suffix(
                        ".bin" if raw_requested else ".wav"
                    )
                if raw_requested:
                    self._run(
                        lambda progress: self.host.export_audio_range(
                            asset.asset_id, destination, progress
                        ),
                        lambda value: self.progress_label.setText(
                            f"Exported raw range {Path(value).name}"
                        ),
                    )
                else:
                    self._run(
                        lambda progress: self.host.export_audio_range_wav(
                            asset.asset_id, destination, progress
                        ),
                        lambda value: self.progress_label.setText(
                            f"Exported range WAV {Path(value).name}"
                        ),
                    )
            elif bank:
                self._run(
                    lambda progress: self.host.export_audio_bank(
                        asset.asset_id, destination, progress
                    ),
                    lambda value: self.progress_label.setText(
                        f"Exported raw bank {Path(value).name}"
                    ),
                )
            else:
                self._run(
                    lambda progress: self.host.export_audio(
                        asset.asset_id, destination, progress
                    ),
                    lambda value: self.progress_label.setText(
                        f"Exported WAV {Path(value).name}"
                    ),
                )

        def _export_shortlisted_audio(self) -> None:
            if self._busy:
                return
            asset_ids = self._shortlisted_audio_ids()
            count = len(asset_ids)
            if not 1 <= count <= 256:
                return
            selected, _selected_filter = QFileDialog.getSaveFileName(
                self,
                "Export selected NFL 2K5 sounds",
                str(Path.home() / "nfl2k5-selected-sounds-wav.zip"),
                "Decoded WAV audio ZIP (*.zip)",
            )
            if not selected:
                return
            destination = Path(selected)
            if not destination.suffix:
                destination = destination.with_suffix(".zip")
            if destination.suffix.casefold() != ".zip":
                QMessageBox.information(
                    self,
                    "Choose a ZIP filename",
                    "Selected WAVs export transactionally as one .zip archive.",
                )
                return
            if destination.exists() or destination.is_symlink():
                QMessageBox.information(
                    self,
                    "Choose a new filename",
                    "Audio collection exports never overwrite an existing file. "
                    "Choose a new filename and try again.",
                )
                return
            self._run(
                lambda progress: self.host.export_audio_selection(
                    asset_ids,
                    destination,
                    bundle_name="NFL 2K5 audio shortlist",
                    progress=progress,
                ),
                lambda value: self._audio_bundle_exported(Path(value), count),
            )

        def _export_matching_audio(self) -> None:
            if self._busy:
                return
            if not self._catalog_page_actions_ready():
                return
            count = self.page.total
            if not 1 <= count <= 256:
                return
            scope = str(self.scope_filter.currentData())
            family = self.family_filter.currentData()
            soundtrack = (
                scope == "streaming_ranges"
                and family == "music"
                and not self.search.text().strip()
                and self.status_filter.currentData() is None
            )
            suggested_stem = (
                "nfl2k5-soundtrack-music"
                if soundtrack else "nfl2k5-matching-audio"
            )
            if scope == "streaming":
                filters = "Exact raw bank audio ZIP (*.zip)"
                suggested = f"{suggested_stem}-raw.zip"
            elif scope == "streaming_ranges":
                filters = (
                    "Decoded WAV audio ZIP (*.zip);;"
                    "Exact raw range audio ZIP (*.zip)"
                )
                suggested = f"{suggested_stem}-wav.zip"
            else:
                filters = "Current WAV audio ZIP (*.zip)"
                suggested = f"{suggested_stem}-wav.zip"
            selected, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Export matching NFL 2K5 audio",
                str(Path.home() / suggested),
                filters,
            )
            if not selected:
                return
            destination = Path(selected)
            if not destination.suffix:
                destination = destination.with_suffix(".zip")
            if destination.suffix.casefold() != ".zip":
                QMessageBox.information(
                    self,
                    "Choose a ZIP filename",
                    "Matching audio exports transactionally as one .zip archive.",
                )
                return
            if destination.exists() or destination.is_symlink():
                QMessageBox.information(
                    self,
                    "Choose a new filename",
                    "Audio collection exports never overwrite an existing file. "
                    "Choose a new filename and try again.",
                )
                return
            output_format = (
                "bin"
                if scope == "streaming" or selected_filter.startswith("Exact raw")
                else "wav"
            )
            bundle_name = " · ".join(
                part for part in (
                    "NFL 2K5 Audio",
                    self.scope_filter.currentText(),
                    self.family_filter.currentText(),
                    self.status_filter.currentText()
                    if self.status_filter.currentData() is not None else "",
                    self.meaning_filter.currentText()
                    if self.meaning_filter.currentData() is not None else "",
                    "Labeled only" if self.labeled_only_filter.isChecked() else "",
                    self.search.text().strip(),
                ) if part
            )
            query = {
                "search": self.search.text(),
                "status": self.status_filter.currentData(),
                "scope": scope,
                "family": family,
                "meaning_status": self.meaning_filter.currentData(),
            }
            if self.labeled_only_filter.isChecked():
                query["labeled_only"] = True

            self._run(
                lambda progress: self.host.export_audio_bundle(
                    **query,
                    destination=destination,
                    output_format=output_format,
                    bundle_name=bundle_name,
                    progress=progress,
                ),
                lambda value: self._audio_bundle_exported(Path(value), count),
            )

        def _audio_bundle_exported(self, path: Path, count: int) -> None:
            self.progress_label.setText(
                f"Exported {count:,} local audio rows to {path.name}"
            )
            QMessageBox.information(
                self,
                "Audio collection exported",
                f"Saved {count:,} audio rows to:\n{path}\n\n"
                "This is a local export from your own game copy, not a shareable "
                ".2k5mod project. Its manifest identifies staged user WAVs and "
                "retail-derived entries separately. Do not redistribute "
                "retail-derived audio.",
            )

        def _export_audio_replacement_template(self) -> None:
            if self._busy:
                return
            export_method = getattr(
                self.host, "export_audio_replacement_template", None
            )
            if not callable(export_method):
                return
            content_mode = str(self.replacement_pack_contents.currentData())
            all_mode = content_mode == "all_standalone"
            selected_mode = content_mode == "shortlist"
            asset_ids: tuple[str, ...] | None = (
                self._shortlisted_audio_ids() if selected_mode else None
            )
            ineligible_ids = (
                self._replacement_pack_ineligible_audio_ids()
                if selected_mode else ()
            )
            if selected_mode and not asset_ids:
                QMessageBox.information(
                    self,
                    "Choose sounds for this template",
                    "Add 1–256 Editable standalone sounds or streaming ranges to the "
                    "audio shortlist first. Use Add selected sound or Add this page, "
                    "then export the ordered shortlist template.",
                )
                self._update_replacement_pack_actions()
                return
            if ineligible_ids:
                count = len(ineligible_ids)
                QMessageBox.information(
                    self,
                    "Remove Export-only sounds",
                    f"This listening shortlist contains {count} Export-only sound"
                    f"{'s' if count != 1 else ''}. Replacement packs accept only "
                    "Editable sounds. Use Review selected to remove the Export-only "
                    "rows, or use Export selected WAVs to keep them in a listening "
                    "collection.",
                )
                self._update_replacement_pack_actions()
                return
            container = str(self.replacement_pack_container.currentData())
            template_stem = (
                "nfl2k5-selected-audio-replacement-template"
                if selected_mode else
                "nfl2k5-all-850-standalone-audio-replacement-template"
                if all_mode else
                "nfl2k5-legacy-153-audio-replacement-template"
            )
            if container == "zip":
                selected, _selected_filter = QFileDialog.getSaveFileName(
                    self,
                    "Export NFL 2K5 audio replacement template",
                    str(Path.home() / f"{template_stem}.zip"),
                    "Audio replacement template ZIP (*.zip)",
                )
                if not selected:
                    return
                destination = Path(selected)
                if not destination.suffix:
                    destination = destination.with_suffix(".zip")
                if destination.suffix.casefold() != ".zip":
                    QMessageBox.information(
                        self,
                        "Choose a ZIP filename",
                        "ZIP audio templates need a .zip filename.",
                    )
                    return
            else:
                selected, _selected_filter = QFileDialog.getSaveFileName(
                    self,
                    "Name the NFL 2K5 audio replacement folder",
                    str(Path.home() / template_stem),
                    "New template folder (*)",
                )
                if not selected:
                    return
                destination = Path(selected)
            if destination.exists() or destination.is_symlink():
                QMessageBox.information(
                    self,
                    "Choose a new destination",
                    "Audio templates never overwrite an existing file or folder.",
                )
                return

            def complete(value: object) -> None:
                path = Path(getattr(value, "path", destination))
                self.progress_label.setText(
                    "Retail-free v4 all-850 audio template and cue map exported"
                    if all_mode else
                    "Retail-free shortlist audio template exported"
                    if selected_mode else
                    "Retail-free legacy audio template exported"
                )
                contents = (
                    f"the ordered {len(asset_ids)}-sound shortlist"
                    if asset_ids is not None else
                    "all 850 standalone sounds with a spreadsheet-safe, read-only "
                    "AUDIO-CUE-MAP.csv"
                    if all_mode else
                    "the legacy v1 153-cue standalone collection"
                )
                boundary = (
                    "Exact streaming ranges are available through Selected shortlist; "
                    "whole streaming banks remain excluded."
                    if all_mode else
                    "Whole streaming banks and raw bank containers remain excluded."
                    if selected_mode else
                    "This v1-compatible scope intentionally remains 153 cues; choose "
                    "All standalone sounds for the current complete workflow."
                )
                map_instruction = (
                    "AUDIO-CUE-MAP.csv is a read-only reference; do not edit it. "
                    if all_mode else ""
                )
                QMessageBox.information(
                    self,
                    "Audio replacement template ready",
                    f"Saved the metadata template for {contents} to:\n{path}\n\n"
                    "It contains zero retail WAVs. Add only your authored WAVs at "
                    "the declared replacements/ paths, then import the folder or ZIP. "
                    f"{map_instruction}Import "
                    "automatically recognizes current v4 all-850, old v3 all-850, v2 "
                    f"shortlist, and v1 legacy packs. {boundary}",
                )

            def export(progress: ProgressSink) -> object:
                if all_mode:
                    return export_method(
                        destination,
                        container=container,
                        progress=progress,
                        complete_standalone=True,
                        with_authoring_map=True,
                        asset_ids=None,
                    )
                if selected_mode:
                    return export_method(
                        destination,
                        container=container,
                        progress=progress,
                        asset_ids=asset_ids,
                    )
                return export_method(
                    destination,
                    container=container,
                    progress=progress,
                    asset_ids=None,
                )

            self._run(
                export,
                complete,
            )

        def _import_audio_replacement_pack(self) -> None:
            if self._busy:
                return
            import_method = getattr(self.host, "import_audio_replacement_pack", None)
            preflight_method = getattr(
                self.host, "preflight_audio_replacement_pack", None
            )
            if not callable(import_method) or not callable(preflight_method):
                return
            container = str(self.replacement_pack_container.currentData())
            if container == "zip":
                selected, _selected_filter = QFileDialog.getOpenFileName(
                    self,
                    "Choose edited NFL 2K5 audio replacement ZIP",
                    "",
                    "Audio replacement pack ZIP (*.zip)",
                )
            else:
                selected = QFileDialog.getExistingDirectory(
                    self,
                    "Choose edited NFL 2K5 audio replacement folder",
                    "",
                )
            if not selected:
                return
            source = Path(selected)
            source_epoch = self._catalog_source_epoch

            def import_complete(value: object) -> None:
                changed = int(getattr(value, "changed_count", 0))
                fallback_message = (
                    f"Imported {changed} changed audio cue"
                    f"{'s' if changed != 1 else ''} as one Undo action."
                )
                result_message = getattr(value, "message", None)
                if not isinstance(result_message, str) or not result_message.strip():
                    result_message = fallback_message
                else:
                    result_message = result_message.strip()
                self.audio_batch_imported.emit(changed)
                self.progress_label.setText(result_message)
                if changed:
                    self.invalidate_audio_content()
                self.refresh()
                QMessageBox.information(
                    self,
                    "Audio replacement pack imported",
                    f"{result_message}\n\n"
                    "The source XISO was not changed. Save a .2k5mod project or "
                    "Build when you are ready.",
                )

            def confirm_after_worker(value: object) -> None:
                if self._busy:
                    self.error_raised.emit(
                        "Another audio operation started before pack confirmation. "
                        "Nothing was imported; preview the pack again."
                    )
                    return
                if (
                    source_epoch != self._catalog_source_epoch
                    or not self.host.source_ready
                ):
                    self.error_raised.emit(
                        "The loaded game changed after the audio-pack preview. "
                        "Choose the replacement pack again for the current game."
                    )
                    return
                if self._operation_admission is not None:
                    denial = self._operation_admission()
                    if denial is not None:
                        self.error_raised.emit(
                            denial + " Nothing was imported; preview the pack again."
                        )
                        return
                supplied = int(getattr(value, "supplied_count", 0))
                would_change = int(getattr(value, "would_change_count", 0))
                physical = int(
                    getattr(value, "unique_physical_change_count", would_change)
                )
                already_current = int(
                    getattr(value, "already_current_count", 0)
                )
                restores = int(
                    getattr(value, "would_restore_original_count", 0)
                )
                physical_restores = int(
                    getattr(value, "unique_physical_restore_count", restores)
                )
                aliases = int(getattr(value, "affected_alias_count", 0))
                resulting = int(getattr(value, "resulting_modified_count", 0))
                token = getattr(value, "confirmation_token", None)
                if (
                    supplied < 1
                    or min(
                        would_change, physical, already_current, restores,
                        physical_restores, aliases, resulting,
                    ) < 0
                    or would_change + already_current != supplied
                    or physical > would_change
                    or restores > would_change
                    or physical_restores > restores
                    or physical_restores > physical
                    or not isinstance(token, str)
                    or re.fullmatch(r"2k5apf1\.[0-9a-f]{64}", token) is None
                ):
                    self.error_raised.emit(
                        "The audio-pack preview returned an invalid summary. Nothing "
                        "was imported; preview the pack again."
                    )
                    return
                if would_change == 0:
                    self.progress_label.setText(
                        "Audio pack checked · every supplied WAV is already current"
                    )
                    QMessageBox.information(
                        self,
                        "No audio changes to apply",
                        f"All {supplied} supplied WAV"
                        f"{'s already match' if supplied != 1 else ' already matches'} "
                        "the current project. Nothing was staged and no Undo action "
                        "was added.",
                    )
                    return

                kind_labels = {
                    "all_standalone_850_mapped": "Mapped all-850 standalone pack (v4)",
                    "all_standalone_850": "All-850 standalone pack (v3)",
                    "selected_audio": "Selected-audio shortlist pack (v2)",
                    "legacy_standalone": "Legacy 153-cue standalone pack (v1)",
                }
                kind = kind_labels.get(
                    str(getattr(value, "pack_kind", "")),
                    "Audio replacement pack",
                )
                summary = [
                    kind,
                    "",
                    f"Supplied WAVs: {supplied}",
                    f"Would change: {would_change} logical cue"
                    f"{'s' if would_change != 1 else ''} across {physical} physical "
                    f"slot{'s' if physical != 1 else ''}",
                    f"Already current: {already_current}",
                    f"Result after Apply: {resulting} modified logical cue"
                    f"{'s' if resulting != 1 else ''}",
                ]
                if restores:
                    summary.append(
                        f"Restore source original: {restores} logical cue"
                        f"{'s' if restores != 1 else ''} across {physical_restores} "
                        f"physical slot{'s' if physical_restores != 1 else ''}"
                    )
                if aliases:
                    summary.append(
                        f"Linked aliases affected beyond their owning slots: {aliases}"
                    )
                changed_rows = tuple(getattr(value, "changed_rows", ()))
                shown_rows = changed_rows[:8]
                if shown_rows:
                    summary.extend(("", "First changes:"))
                    for row in shown_rows:
                        action = (
                            "Restore original"
                            if getattr(row, "action", "") == "restore_original"
                            else "Replace"
                        )
                        label = str(getattr(row, "label", "Audio cue")).strip()
                        affected = tuple(getattr(row, "affected_asset_ids", ()))
                        linked = max(0, len(affected) - 1)
                        summary.append(
                            f"• {action}: {label}"
                            + (f" (+{linked} linked)" if linked else "")
                        )
                hidden = max(0, len(changed_rows) - len(shown_rows)) + int(
                    getattr(value, "omitted_changed_count", 0)
                )
                if hidden:
                    summary.append(f"• …and {hidden} more change"
                                   f"{'s' if hidden != 1 else ''}")
                summary.extend((
                    "",
                    "Apply reopens and revalidates the exact pack before staging one "
                    "Undoable action. Your source XISO is never changed.",
                ))
                self.progress_label.setText(
                    f"Preview ready · {would_change} change"
                    f"{'s' if would_change != 1 else ''} awaiting confirmation"
                )
                answer = QMessageBox.question(
                    self,
                    "Apply audio replacement pack?",
                    "\n".join(summary),
                    QMessageBox.Apply | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if answer != QMessageBox.Apply:
                    self.progress_label.setText(
                        "Audio replacement-pack import canceled · nothing changed"
                    )
                    return
                self._run(
                    lambda progress: import_method(
                        source,
                        progress,
                        confirmation_token=token,
                    ),
                    import_complete,
                )

            def preflight_complete(value: object) -> None:
                # ``result`` is delivered before ``finished``. Queue the modal
                # confirmation so the preview worker and global operation lane
                # have fully drained before Apply can start a second worker.
                self._post_operation_continuation = (
                    lambda: confirm_after_worker(value)
                )

            self._run(
                lambda progress: preflight_method(source, progress),
                preflight_complete,
            )

        def _choose_replacement(self) -> None:
            if self._busy:
                return
            asset = self._selected_asset()
            if not isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            ) or not asset.editable:
                return
            selected, _filter = QFileDialog.getOpenFileName(
                self,
                f"Choose replacement audio for {asset.name}",
                "",
                audio_conform.file_dialog_filter(),
            )
            if selected:
                self._replace_with_path(Path(selected))

        def _replacement_hint(self, asset: object) -> str:
            """Say what this sound needs, and that the app will handle it.

            The slot's shape is fixed and unforgiving, which used to mean the
            modder had to build a file to match it by hand. It no longer does,
            but only if the panel says so -- otherwise "exactly 10,624 frames"
            reads like a wall rather than something already taken care of.
            """

            note = getattr(asset, "action_note", "") or ""
            channels = getattr(asset, "channels", None)
            sample_rate = getattr(asset, "sample_rate", None)
            frame_count = getattr(asset, "frame_count", None)
            if not isinstance(channels, int) or not isinstance(sample_rate, int) \
                    or not isinstance(frame_count, int) or sample_rate <= 0:
                return note

            layout = {1: "mono", 2: "stereo"}.get(channels, f"{channels}-channel")
            seconds = frame_count / sample_rate
            shape = f"{layout}, {sample_rate:,} Hz, {seconds:.2f} seconds"
            if audio_conform.conversion_available():
                lead = (
                    f"Drop any common audio file here (MP3, WAV, FLAC, OGG, M4A) — "
                    f"it is converted automatically to fit this sound: {shape}. "
                    f"Longer audio is trimmed, shorter is padded with silence."
                )
            else:
                lead = (
                    f"This sound needs a PCM16 WAV that is exactly {shape}. "
                    f"Install FFmpeg to drop other formats and have them "
                    f"converted for you."
                )
            return f"{lead}\n\n{note}" if note else lead

        def _replace_with_path(self, supplied: Path) -> None:
            if self._busy:
                return
            asset = self._selected_asset()
            if not isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            ) or not asset.editable:
                self.error_raised.emit(
                    "Select an Editable standalone sound or streaming range before "
                    "replacing audio. Complete streaming banks and opaque raw bank "
                    "containers stay export-only."
                )
                return

            # Anything that is not already the slot's exact shape is converted
            # first, so a modder can drop an ordinary mp3 or a 48 kHz stereo WAV
            # instead of hand-building a file in an audio editor. The conversion
            # runs inside the worker because the largest slots take a few
            # seconds, and its output then goes through `replace_audio` and every
            # validation behind it exactly as a hand-made file would -- nothing
            # downstream is relaxed to accommodate it.
            conformed_notes: list[str] = []

            def operation(progress: ProgressSink) -> object:
                try:
                    shape = audio_conform.shape_for(
                        asset.channels, asset.sample_rate, asset.frame_count
                    )
                except audio_conform.AudioConformError:
                    return self.host.replace_audio(asset.asset_id, supplied, progress)

                with tempfile.TemporaryDirectory(
                    prefix="nfl2k5-audio-conform-"
                ) as workspace:
                    try:
                        result = audio_conform.conform(supplied, shape, Path(workspace))
                    except audio_conform.AudioConformError:
                        # Strictly additive: a file that cannot be converted goes
                        # through untouched, so the existing importer produces the
                        # same refusal it always did. Conversion adds a route; it
                        # never removes one or rewords an existing failure.
                        return self.host.replace_audio(
                            asset.asset_id, supplied, progress
                        )
                    if result.converted:
                        conformed_notes.extend(result.notes)
                    return self.host.replace_audio(
                        asset.asset_id, result.path, progress
                    )

            def complete(_value: object) -> None:
                self.audio_modified.emit(asset.asset_id)
                if conformed_notes:
                    # Reported, not hidden: someone who hears something
                    # unexpected should be able to see that the file was
                    # resampled or trimmed, and why. It is not an error, so it
                    # does not go to error_raised. The status line names the
                    # changes; the tooltip carries the full sentences.
                    changes: list[str] = []
                    joined = " ".join(conformed_notes)
                    if "Resampled" in joined:
                        changes.append("resampled")
                    if "Channels" in joined:
                        changes.append("channels changed")
                    if "trimmed" in joined:
                        changes.append("trimmed to fit")
                    if "padded" in joined:
                        changes.append("padded with silence")
                    if "headroom" in joined:
                        changes.append("level lowered to avoid clipping")
                    summary = ", ".join(changes) if changes else "converted"
                    self.progress_label.setText(
                        f"Replacement staged. Your file was {summary}. "
                        "Hover for details."
                    )
                    self.progress_label.setToolTip("\n".join(conformed_notes))
                else:
                    self.progress_label.setText("Replacement staged")
                    self.progress_label.setToolTip("")
                self.invalidate_audio_content()
                self.refresh()

            self._run(operation, complete)

        def _revert_selected(self) -> None:
            if self._busy:
                return
            asset = self._selected_asset()
            if not isinstance(
                asset, (Nfl2k5AudioAsset, Nfl2k5StreamingAudioRange)
            ) or not asset.editable:
                return

            def complete(_value: object) -> None:
                self.audio_reverted.emit(asset.asset_id)
                self.progress_label.setText("Original audio restored")
                self.invalidate_audio_content()
                self.refresh()

            self._run(
                lambda progress: self.host.revert_audio(asset.asset_id, progress),
                complete,
            )

        def _run(
            self,
            operation: Callable[[ProgressSink], object],
            on_success: Callable[[object], None],
            *,
            on_error: Callable[[str], None] | None = None,
        ) -> None:
            if self._busy:
                return
            if self._operation_admission is not None:
                denial = self._operation_admission()
                if denial is not None:
                    self.error_raised.emit(denial)
                    return
            self._search_timer.stop()
            self._busy = True
            self.operation_state_changed.emit(True)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            self._refresh_controls()
            task = _Task(operation)
            self._tasks.add(task)
            task.signals.progress.connect(self._progress)
            task.signals.result.connect(on_success)
            task.signals.error.connect(on_error or self.error_raised.emit)

            def finished() -> None:
                self._tasks.discard(task)
                if self._busy:
                    self._busy = False
                    if self._refresh_after_busy:
                        self._refresh_after_busy = False
                        self.refresh(keep_selection=True)
                    self.operation_state_changed.emit(False)
                self.progress_bar.hide()
                self._refresh_controls()
                continuation = self._post_operation_continuation
                self._post_operation_continuation = None
                if continuation is not None:
                    QTimer.singleShot(0, continuation)

            task.signals.finished.connect(finished)
            try:
                self._pool.start(task)
            except BaseException:
                self._tasks.discard(task)
                if self._busy:
                    self._busy = False
                    self._refresh_after_busy = False
                    self._post_operation_continuation = None
                    self.operation_state_changed.emit(False)
                self.progress_bar.hide()
                self._refresh_controls()
                raise

        def _progress(self, stage: str, completed: int, total: int) -> None:
            self.progress_label.setText(stage)
            if total > 0:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setValue(max(0, min(total, completed)))
            else:
                self.progress_bar.setRange(0, 0)
__all__ = [
    "AUDIO_ANNOTATION_CONTRACT",
    "AUDIO_MEDIA_INVALIDATION_CONTRACT",
    "AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT",
    "AUDIO_REPLACEMENT_PREFLIGHT_CONTRACT",
    "AUDIO_WAVEFORM_LIFECYCLE_CONTRACT",
    "AudioPage",
    "AudioPanel",
    "AudioPanelHost",
    "CatalogAudioPanelHost",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MAX_SHORTLIST_SIZE",
    "PYQT5_AVAILABLE",
    "audio_bank_search_text",
    "audio_player_command",
    "audio_range_search_text",
    "audio_search_text",
    "filter_audio_assets",
    "filter_audio_banks",
    "filter_audio_ranges",
    "paginate_audio_assets",
]
