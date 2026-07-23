"""Product adapter connecting the Qt shell to the NFL 2K5 backend."""

from __future__ import annotations

import csv
import copy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import stat
import threading
from typing import Callable, Iterable, Sequence

from mod_editor.core.errors import ValidationError
from mod_editor.core.gameplay_inspection import (
    DEFAULT_FRANCHISE_REPORT,
    DEFAULT_NFL_SAVE_REPORT,
    DEFAULT_PS2_FIXTURE_REPORT,
    DEFAULT_TUNING_REPORT,
    inspect_draft_priority,
    inspect_gameplay_sliders,
    inspect_nfl_franchise_limit,
    inspect_nfl_save_inventory,
)
from mod_editor.core.menu_modes import (
    DEFAULT_REPORT_DIR as DEFAULT_MENU_REPORT_DIR,
    inspect_main_menu as inspect_named_main_menu,
)
from mod_editor.core.nfl2k5_build_service import (
    BuildEvent,
    BuildResult,
    Nfl2k5BuildService,
)
from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache, SourceCache
from mod_editor.core.nfl2k5_universal_asset_index import (
    Nfl2k5UniversalAssetIndex,
    UniversalAssetRecord,
)
from mod_editor.core.nfl2k5_playbook_inspector import (
    Nfl2k5Playbook,
    Nfl2k5PlaybookInspector,
)
from mod_editor.core.nfl2k5_stadium_studio import (
    Nfl2k5StadiumStudio,
    StadiumScene,
    StadiumSceneDetails,
)
from mod_editor.core.nfl2k5_stadium_cache import (
    Nfl2k5StadiumCacheCoordinator,
    StadiumCacheResult,
)
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    Nfl2k5StadiumTextureWriter,
    TARGET_SCENE_ID,
    TARGET_TEXTURE_ID,
)
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    Nfl2k5ProductVisualCatalog,
    load_nfl2k5_product_visual_catalog,
)
from mod_editor.core.nfl2k5_uniform_catalog import (
    Nfl2k5UniformCatalog,
    UniformAsset,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    RosterNumberAsset,
    TextAsset,
)
from mod_editor.core.nfl2k5_audio_catalog import (
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
from mod_editor.core.nfl2k5_audio_origin_preparation import (
    Nfl2k5AudioOriginPreparation,
)
from mod_editor.core.nfl2k5_crib import (
    CribAsset,
    Nfl2k5CribCatalog,
    Nfl2k5CribIO,
    load_nfl2k5_crib_catalog,
)

from .session import (
    AudioProjectPreparationRequired,
    StadiumProjectPreparationRequired,
    StudioSession,
)
from .audio_annotations import AudioCueAnnotation
from .project_archive import ProjectTargetIdentity, project_target_identity
from .audio_bundle import (
    AudioBundleRow,
    bundle_row_for_asset,
    export_audio_bundle as publish_audio_bundle,
)
from .audio_replacement_pack import (
    AudioReplacementPackService,
    complete_standalone_pack_path,
    standalone_runtime_meaning_status,
)
from .uniform_bundle import TeamKitBundleService


ProgressSink = Callable[[str, int, int], None]


def _quiet_progress(_stage: str, _completed: int, _total: int) -> None:
    pass


def _with_audio_annotation(
    row: AudioBundleRow,
    annotation: AudioCueAnnotation | None,
) -> AudioBundleRow:
    """Overlay user discovery metadata without changing the stable cue path."""

    if annotation is None:
        return row
    metadata = dict(row.metadata)
    metadata.update({
        "annotation_note": annotation.note,
        "custom_title": annotation.title,
        "game_catalog_name": row.display_name,
    })
    return AudioBundleRow(
        stable_id=row.stable_id,
        display_name=annotation.title or row.display_name,
        suggested_basename=row.suggested_basename,
        extension=row.extension,
        predicted_payload_bytes=row.predicted_payload_bytes,
        content_origin=row.content_origin,
        metadata=metadata,
    )


def _publish_new_export(payload: bytes, destination: Path) -> Path:
    """Publish one user-requested export without overwriting an existing path."""

    requested = destination.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            requested,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise ValidationError(f"A file already exists there: {requested}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        requested.unlink(missing_ok=True)
        raise
    return requested.resolve(strict=True)


_PRODUCT_ROOT = Path(__file__).resolve().parents[2]
_GAMEPLAY_SNAPSHOT = (
    _PRODUCT_ROOT / "mod_editor/data/nfl2k5_gameplay_inspection.v1.json"
)
_GAMEPLAY_SNAPSHOT_SIZE = 22_874
_GAMEPLAY_SNAPSHOT_SHA256 = (
    "864c785d3b0a689dace1ec9c37be0bc276519a334775c9df8953d6d62722dbe3"
)
_GAMEPLAY_SNAPSHOT_SCHEMA = "nfl2k5_mod_studio_gameplay_inspection/v1"
_MENU_SNAPSHOT = _PRODUCT_ROOT / "mod_editor/data/nfl2k5_main_menu_inspection.v1.json"
_MENU_SNAPSHOT_SIZE = 3_563
_MENU_SNAPSHOT_SHA256 = (
    "fae27305eada0ac1200896f0b907307e20942d2cf4506b2ff172c22ceb767629"
)
_MENU_SNAPSHOT_SCHEMA = "mod_editor_named_main_menu_inspector/v1"


def _read_product_snapshot(
    path: Path, *, label: str, size: int, sha256: str, schema: str
) -> dict[str, object]:
    """Read one release-safe product snapshot with exact identity checks."""

    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} product snapshot is missing: {path}") from exc
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
        or supplied.st_size != size
    ):
        raise ValidationError(f"{label} product snapshot identity does not match")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError(f"{label} product snapshot changed while opening")
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError(f"{label} product snapshot ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError(f"{label} product snapshot grew while reading")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        ):
            raise ValidationError(f"{label} product snapshot changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise ValidationError(f"{label} product snapshot hash does not match")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} product snapshot is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValidationError(f"{label} product snapshot schema does not match")
    return value


def _complete_evidence_set(paths: tuple[Path, ...], label: str) -> bool:
    available = tuple(path.is_file() and not path.is_symlink() for path in paths)
    if all(available):
        return True
    if any(available):
        raise ValidationError(
            f"{label} source evidence is incomplete; refusing a mixed snapshot."
        )
    return False


@lru_cache(maxsize=1)
def _verified_gameplay_snapshot() -> dict[str, object]:
    snapshot = _read_product_snapshot(
        _GAMEPLAY_SNAPSHOT,
        label="Gameplay",
        size=_GAMEPLAY_SNAPSHOT_SIZE,
        sha256=_GAMEPLAY_SNAPSHOT_SHA256,
        schema=_GAMEPLAY_SNAPSHOT_SCHEMA,
    )
    if _complete_evidence_set(
        (
            DEFAULT_TUNING_REPORT,
            DEFAULT_FRANCHISE_REPORT,
            DEFAULT_NFL_SAVE_REPORT,
            DEFAULT_PS2_FIXTURE_REPORT,
        ),
        "Gameplay",
    ):
        live = {
            "schema": _GAMEPLAY_SNAPSHOT_SCHEMA,
            "game": "ESPN NFL 2K5",
            "read_only": True,
            "sliders": inspect_gameplay_sliders("nfl2k5"),
            "fantasy_draft": inspect_draft_priority("nfl2k5"),
            "saves": inspect_nfl_save_inventory(),
            "franchise": inspect_nfl_franchise_limit("all"),
            "product_boundary": (
                "This is an evidence-backed inspector, not a settings or executable "
                "writer. No preset or writeback is enabled here."
            ),
        }
        if live != snapshot:
            raise ValidationError(
                "Gameplay product snapshot no longer matches the proved core inspection."
            )
    return snapshot


@lru_cache(maxsize=1)
def _verified_menu_snapshot() -> dict[str, object]:
    snapshot = _read_product_snapshot(
        _MENU_SNAPSHOT,
        label="Main Menu",
        size=_MENU_SNAPSHOT_SIZE,
        sha256=_MENU_SNAPSHOT_SHA256,
        schema=_MENU_SNAPSHOT_SCHEMA,
    )
    menu_sources = (
        DEFAULT_MENU_REPORT_DIR / "menu_state_trace.json",
        DEFAULT_MENU_REPORT_DIR / "nfl_main_menu_live_state.json",
    )
    if _complete_evidence_set(menu_sources, "Main Menu"):
        live = inspect_named_main_menu("nfl2k5")
        if live != snapshot:
            raise ValidationError(
                "Main Menu product snapshot no longer matches the proved core inspection."
            )
    return snapshot


def collect_nfl2k5_gameplay_inspection() -> dict[str, object]:
    """Collect the four sanitized, read-only NFL gameplay product views."""

    return copy.deepcopy(_verified_gameplay_snapshot())


def collect_nfl2k5_main_menu_inspection() -> dict[str, object]:
    """Collect the sanitized named Main Menu state/transition view."""

    return copy.deepcopy(_verified_menu_snapshot())


def _csv_payload(
    fieldnames: tuple[str, ...], rows: Iterable[dict[str, object]]
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def serialize_gameplay_inspection_csv(snapshot: dict[str, object]) -> bytes:
    """Flatten the product gameplay snapshot into a useful spreadsheet."""

    sliders = snapshot["sliders"]
    draft = snapshot["fantasy_draft"]
    saves = snapshot["saves"]
    franchise = snapshot["franchise"]
    if not all(isinstance(value, dict) for value in (sliders, draft, saves, franchise)):
        raise ValidationError("Gameplay inspection is incomplete and cannot be exported.")
    sliders = sliders  # type: ignore[assignment]
    draft = draft  # type: ignore[assignment]
    saves = saves  # type: ignore[assignment]
    franchise = franchise  # type: ignore[assignment]

    rows: list[dict[str, object]] = []
    stock_range = sliders["stock_ui_range"]
    stock_note = (
        f"stock UI {stock_range['minimum']}..{stock_range['maximum']} "
        f"step {stock_range['step']}"
    )
    for row in sliders["sliders"]:
        rows.append({
            "section": "gameplay_slider",
            "index": row["index"],
            "name": row["name"],
            "settings1": row.get("observed_settings1_value", ""),
            "franchise1": row.get("observed_franchise1_value", ""),
            "status": "mapped read-only",
            "details": stock_note,
        })
    for index, row in enumerate(draft["position_weights"]):
        rows.append({
            "section": "fantasy_draft_weight",
            "index": index,
            "id": row["position_code"],
            "name": row["position"],
            "position_code": row["position_code"],
            "value": row["weight"],
            "status": draft["proof_status"]["classification"],
            "details": "Fantasy Draft only; no released writer or runtime A/B.",
        })
    for index, row in enumerate(saves["containers"]):
        rows.append({
            "section": "observed_save_container",
            "index": index,
            "id": row["display_name"],
            "name": row["display_name"],
            "value": f"SAVEGAME {row['savegame_size']} bytes; EXTRA {row['extra_size']} bytes",
            "status": row["type"],
            "details": "Sanitized fixture metadata; not the user's current save.",
        })
    integrity = saves["integrity_boundary"]
    rows.append({
        "section": "save_integrity",
        "id": "signature_boundary",
        "name": "SAVEGAME signature",
        "value": integrity["signature_mode"],
        "status": (
            "safe writer available" if integrity["safe_writer_available"]
            else "writeback unavailable"
        ),
        "details": f"EXTRA size {integrity['extra_size']} bytes",
    })
    for index, row in enumerate(franchise["targets"]):
        rows.append({
            "section": "franchise_finding",
            "index": index,
            "id": row["id"],
            "name": str(row["id"]).replace("_", " ").title(),
            "status": row["feasibility"],
            "details": (
                f"{row['user_limitation']} | layer: {row['likely_mutation_layer']} | "
                "writer unavailable"
            ),
        })
    return _csv_payload(
        (
            "section", "index", "id", "name", "position_code", "value",
            "settings1", "franchise1", "status", "details",
        ),
        rows,
    )


def serialize_main_menu_inspection_csv(snapshot: dict[str, object]) -> bytes:
    """Flatten named Main Menu rows, layouts, and blockers for modders."""

    state = snapshot.get("state")
    layouts = snapshot.get("layout_reachability")
    blockers = snapshot.get("known_blockers")
    if not isinstance(state, dict) or not isinstance(layouts, list) \
            or not isinstance(blockers, list):
        raise ValidationError("Main Menu inspection is incomplete and cannot be exported.")
    rows: list[dict[str, object]] = []
    for row in state["rows"]:
        activation = row["activation"]
        rows.append({
            "section": "main_menu_transition",
            "position": row["position"],
            "name": row["label"],
            "kind": activation["kind"],
            "target": activation["target"],
            "status": activation["status"],
            "details": (
                f"initially drawable: {row.get('initially_drawable')}"
                if "initially_drawable" in row else ""
            ),
        })
    for index, row in enumerate(layouts):
        rows.append({
            "section": "layout_reachability",
            "position": index,
            "name": row["layout"],
            "kind": row["relation"],
            "target": row.get("archive", ""),
            "status": row["status"],
            "details": "Read-only ownership evidence.",
        })
    for index, row in enumerate(blockers):
        rows.append({
            "section": "known_blocker",
            "position": index,
            "name": row["id"],
            "kind": "limitation",
            "status": row["status"],
            "details": row["needed"],
        })
    return _csv_payload(
        ("section", "position", "name", "kind", "target", "status", "details"),
        rows,
    )


@dataclass(frozen=True)
class StudioOperationResult:
    message: str
    output: Path | None = None
    project_identity: ProjectTargetIdentity | None = None
    changed: bool | None = None


@dataclass(frozen=True)
class StudioAudioPage:
    assets: tuple[
        Nfl2k5AudioAsset | Nfl2k5StreamingAudioBank | Nfl2k5StreamingAudioRange,
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


AudioCatalogItem = (
    Nfl2k5AudioAsset | Nfl2k5StreamingAudioBank | Nfl2k5StreamingAudioRange
)
AudioSearchIndex = dict[str, tuple[tuple[AudioCatalogItem, str], ...]]


def _audio_search_haystack(asset: AudioCatalogItem) -> str:
    """Build one immutable search row instead of rebuilding it per keystroke."""

    if isinstance(asset, Nfl2k5AudioAsset):
        extra = (
            "stereo" if asset.channels == 2 else "mono",
        )
    elif isinstance(asset, Nfl2k5StreamingAudioBank):
        extra = (
            asset.role_class,
            asset.external_filename,
            str(asset.external_outer_index),
            str(asset.entry_count),
            asset.replacement_status,
            "raw bin opaque undecoded replace replacement",
        )
    else:
        extra = (
            asset.role_class,
            asset.external_filename,
            str(asset.external_outer_index),
            str(asset.range_index),
            str(asset.start),
            str(asset.end),
            f"0x{asset.start:x}",
            f"0x{asset.end:x}",
            str(asset.stored_size),
            asset.replacement_status,
            "play playable wav pcm16 xbox ima adpcm decoded raw range "
            "bin cue replace replacement editable fixed slot shared alias",
        )
    return " ".join((
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
        *extra,
    )).casefold()


def _build_audio_search_index(catalog: Nfl2k5AudioCatalog) -> AudioSearchIndex:
    """Precompute metadata-only audio scopes once per source.

    The mixed playable scope concatenates the already-indexed row tuples. It
    therefore reuses the exact same immutable haystack strings instead of
    retaining another 54,421 copies of searchable metadata.
    """

    standalone = tuple(
        (asset, _audio_search_haystack(asset)) for asset in catalog.assets
    )
    streaming = tuple(
        (asset, _audio_search_haystack(asset)) for asset in catalog.streaming_banks
    )
    streaming_ranges = tuple(
        (asset, _audio_search_haystack(asset)) for asset in catalog.streaming_ranges
    )
    return {
        "standalone": standalone,
        "streaming": streaming,
        "streaming_ranges": streaming_ranges,
        PLAYABLE_AUDIO_SCOPE_ID: standalone + streaming_ranges,
    }


def _detect_xemu_command() -> tuple[str, ...]:
    direct = shutil.which("xemu")
    if direct:
        return (direct,)
    flatpak = shutil.which("flatpak")
    if not flatpak:
        return ()
    try:
        found = subprocess.run(
            (flatpak, "info", "app.xemu.xemu"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    return (flatpak, "run", "app.xemu.xemu") if found.returncode == 0 else ()


class Nfl2k5StudioFacade:
    """Thread-safe, human-facing Phase 1 application backend."""

    def __init__(
        self,
        *,
        uniform_catalog: Nfl2k5UniformCatalog | None = None,
        visual_catalog: Nfl2k5ProductVisualCatalog | None = None,
        source_cache: Nfl2k5SourceCache | None = None,
        build_service: Nfl2k5BuildService | None = None,
        session_factory: Callable[[SourceCache, Nfl2k5UniformCatalog], StudioSession]
        = StudioSession,
        xemu_command: Sequence[str] | None = None,
        process_launcher: Callable[..., object] = subprocess.Popen,
        universal_index_factory: Callable[[SourceCache], Nfl2k5UniversalAssetIndex]
        = Nfl2k5UniversalAssetIndex.from_cache,
        playbook_inspector_factory: Callable[
            [Nfl2k5UniversalAssetIndex], Nfl2k5PlaybookInspector
        ] = Nfl2k5PlaybookInspector,
        stadium_studio: Nfl2k5StadiumStudio | None = None,
        stadium_cache_coordinator: Nfl2k5StadiumCacheCoordinator | None = None,
        text_catalog_factory: Callable[[SourceCache], Nfl2k5TextCatalog]
        = Nfl2k5TextCatalog.from_cache,
        audio_catalog_factory: Callable[[SourceCache], Nfl2k5AudioCatalog]
        = Nfl2k5AudioCatalog,
        crib_catalog_factory: Callable[[], Nfl2k5CribCatalog]
        = load_nfl2k5_crib_catalog,
        crib_io_factory: Callable[[SourceCache, Nfl2k5CribCatalog], Nfl2k5CribIO]
        = Nfl2k5CribIO,
        team_kit_service_factory: Callable[
            [Nfl2k5UniformCatalog, StudioSession], TeamKitBundleService
        ] = TeamKitBundleService,
        audio_replacement_pack_factory: Callable[
            [Nfl2k5AudioCatalog, StudioSession], AudioReplacementPackService
        ] = AudioReplacementPackService,
        audio_origin_preparation: Nfl2k5AudioOriginPreparation | None = None,
    ) -> None:
        supplied_uniform_catalog = uniform_catalog
        self.uniform_catalog = uniform_catalog or load_nfl2k5_uniform_catalog()
        self.visual_catalog = visual_catalog or (
            load_nfl2k5_product_visual_catalog()
            if supplied_uniform_catalog is None
            else self.uniform_catalog
        )
        self.source_cache = source_cache or Nfl2k5SourceCache()
        self.build_service = build_service or Nfl2k5BuildService()
        self.session_factory = session_factory
        self._xemu_command = (
            tuple(xemu_command) if xemu_command is not None else _detect_xemu_command()
        )
        self._process_launcher = process_launcher
        self._universal_index_factory = universal_index_factory
        self._playbook_inspector_factory = playbook_inspector_factory
        self._provided_stadium_studio = stadium_studio
        self._stadium_studio = stadium_studio
        self._stadium_cache_result: StadiumCacheResult | None = None
        self._stadium_cache_coordinator = (
            stadium_cache_coordinator or Nfl2k5StadiumCacheCoordinator()
        )
        self._text_catalog_factory = text_catalog_factory
        self._audio_catalog_factory = audio_catalog_factory
        self._crib_catalog_factory = crib_catalog_factory
        self._crib_io_factory = crib_io_factory
        self._team_kit_service_factory = team_kit_service_factory
        self._audio_replacement_pack_factory = audio_replacement_pack_factory
        self._audio_origin_preparation = (
            audio_origin_preparation or Nfl2k5AudioOriginPreparation()
        )
        self._cache: SourceCache | None = None
        self._session: StudioSession | None = None
        self._source_name = "No game loaded"
        self._last_build: BuildResult | None = None
        self._universal_index: Nfl2k5UniversalAssetIndex | None = None
        self._playbook_inspector: Nfl2k5PlaybookInspector | None = None
        self._text_catalog: Nfl2k5TextCatalog | None = None
        self._audio_catalog: Nfl2k5AudioCatalog | None = None
        self._audio_service: Nfl2k5AudioService | None = None
        self._audio_search_catalog: Nfl2k5AudioCatalog | None = None
        self._audio_search_index: AudioSearchIndex = {}
        self._crib_catalog: Nfl2k5CribCatalog | None = None
        self._crib_io: Nfl2k5CribIO | None = None
        self._lock = threading.RLock()
        self._audio_preparation_lock = threading.Lock()

    @property
    def source_ready(self) -> bool:
        with self._lock:
            return self._session is not None

    @property
    def source_display_name(self) -> str:
        with self._lock:
            return self._source_name

    @property
    def source_path(self) -> Path | None:
        """Return the active private source path for local recovery metadata."""

        with self._lock:
            cache = self._cache
            return (
                Path(os.path.abspath(os.fspath(cache.source.selected_path)))
                if cache is not None else None
            )

    @property
    def source_sha256(self) -> str | None:
        """Return the active source identity without exposing any game bytes."""

        with self._lock:
            return self._cache.source.sha256 if self._cache is not None else None

    @property
    def modified_asset_ids(self) -> Iterable[str]:
        with self._lock:
            return (
                self._session.modified_asset_ids if self._session is not None
                else frozenset()
            )

    @property
    def modified_count(self) -> int:
        with self._lock:
            return self._session.modified_count if self._session is not None else 0

    @property
    def project_metadata_count(self) -> int:
        """Return authored metadata rows that do not alter a built XISO."""

        with self._lock:
            return (
                self._session.project_metadata_count
                if self._session is not None
                and hasattr(self._session, "project_metadata_count")
                else 0
            )

    @property
    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._session and self._session.can_undo)

    @property
    def can_launch_xemu(self) -> bool:
        with self._lock:
            result = self._last_build
            return bool(
                self._xemu_command
                and result is not None
                and result.output_xiso.is_file()
                and not result.output_xiso.is_symlink()
            )

    @property
    def last_build_output(self) -> Path | None:
        with self._lock:
            return self._last_build.output_xiso if self._last_build else None

    def inspect_gameplay(
        self, progress: ProgressSink = _quiet_progress
    ) -> dict[str, object]:
        """Return the bounded NFL gameplay/save/franchise product snapshot."""

        progress("Reading mapped gameplay findings", 0, 1)
        value = collect_nfl2k5_gameplay_inspection()
        progress("Gameplay findings ready", 1, 1)
        return value

    def export_gameplay_inspection(
        self,
        destination: Path,
        export_format: str,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export sanitized inspection metadata, never executable/save bytes."""

        normalized = export_format.strip().lower()
        if normalized not in {"json", "csv"}:
            raise ValidationError("Gameplay report format must be JSON or CSV.")
        progress(f"Preparing gameplay {normalized.upper()} report", 0, 1)
        snapshot = collect_nfl2k5_gameplay_inspection()
        payload = (
            (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if normalized == "json"
            else serialize_gameplay_inspection_csv(snapshot)
        )
        output = _publish_new_export(payload, destination)
        progress("Gameplay report exported", 1, 1)
        return output

    def inspect_main_menu(
        self, progress: ProgressSink = _quiet_progress
    ) -> dict[str, object]:
        """Return named NFL Main Menu state, transition, and limitation data."""

        progress("Reading named Main Menu findings", 0, 1)
        value = collect_nfl2k5_main_menu_inspection()
        progress("Main Menu findings ready", 1, 1)
        return value

    def export_main_menu_inspection(
        self,
        destination: Path,
        export_format: str,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export sanitized named-menu metadata as JSON or tabular CSV."""

        normalized = export_format.strip().lower()
        if normalized not in {"json", "csv"}:
            raise ValidationError("Main Menu report format must be JSON or CSV.")
        progress(f"Preparing Main Menu {normalized.upper()} report", 0, 1)
        snapshot = collect_nfl2k5_main_menu_inspection()
        payload = (
            (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if normalized == "json"
            else serialize_main_menu_inspection_csv(snapshot)
        )
        output = _publish_new_export(payload, destination)
        progress("Main Menu report exported", 1, 1)
        return output

    def load_source(self, source_xiso: Path, progress: ProgressSink) -> object:
        cache = self.source_cache.index(source_xiso, progress)
        progress("Preparing the complete asset browser", 0, 1)
        universal_index = self._universal_index_factory(cache)
        session = self.session_factory(cache, self.visual_catalog)
        text_catalog = None
        attach_text = getattr(session, "attach_text_catalog", None)
        if callable(attach_text):
            progress("Reading text banks and historical rosters", 0, 1)
            text_catalog = self._text_catalog_factory(cache)
            attach_text(text_catalog)
            progress("Text editor ready", 1, 1)
        audio_catalog = None
        audio_service = None
        audio_search_index: AudioSearchIndex = {}
        attach_audio = getattr(session, "attach_audio_service", None)
        if callable(attach_audio):
            progress("Reading 850 sounds and 17 streaming banks", 0, 1)
            audio_catalog = self._audio_catalog_factory(cache)
            audio_service = Nfl2k5AudioService(cache, audio_catalog)
            attach_audio(audio_service)
            progress("Audio browser ready", 1, 1)
            progress("Optimizing audio search", 0, 1)
            audio_search_index = _build_audio_search_index(audio_catalog)
            progress("Audio search ready", 1, 1)
        crib_catalog = None
        crib_io = None
        attach_crib = getattr(session, "attach_crib", None)
        if callable(attach_crib):
            progress("Reading all 498 Crib textures", 0, 1)
            crib_catalog = self._crib_catalog_factory()
            crib_io = self._crib_io_factory(cache, crib_catalog)
            attach_crib(crib_catalog, crib_io)
            progress("The Crib browser ready", 1, 1)
        stadium_studio = self._provided_stadium_studio
        stadium_result = None
        if stadium_studio is None:
            progress("Checking private Stadium Studio cache", 0, 1)
            existing_stadium = self._stadium_cache_coordinator.load_existing(cache)
            if existing_stadium is not None:
                stadium_result = existing_stadium
                stadium_studio = self._studio_for_session(
                    existing_stadium, cache, session
                )
                progress("Stadium Studio private assets ready", 1, 1)
            else:
                progress("Stadium Studio will prepare when first opened", 1, 1)
        with self._lock:
            self._cache = cache
            self._session = session
            self._source_name = Path(cache.source.selected_path).name
            self._last_build = None
            self._universal_index = universal_index
            # PLAY bodies are decoded lazily only when the dedicated tab opens.
            # Dropping this service also drops all decoded private names/nodes
            # from the previous source lifecycle.
            self._playbook_inspector = None
            self._text_catalog = text_catalog
            self._audio_catalog = audio_catalog
            self._audio_service = audio_service
            self._audio_search_catalog = audio_catalog
            self._audio_search_index = audio_search_index
            self._crib_catalog = crib_catalog
            self._crib_io = crib_io
            self._stadium_studio = stadium_studio
            self._stadium_cache_result = stadium_result
        progress("Complete asset browser ready", 1, 1)
        return StudioOperationResult(
            f"Game ready — {cache.resource_count:,} assets indexed from your copy."
        )

    @property
    def text_available(self) -> bool:
        with self._lock:
            return self._text_catalog is not None

    def text_catalog_snapshot(
        self, progress: ProgressSink = _quiet_progress
    ) -> Nfl2k5TextCatalog:
        progress("Loading searchable text", 0, 1)
        with self._lock:
            catalog = self._require_text_catalog()
        progress("Text ready", 1, 1)
        return catalog

    def search_text(
        self, *, search: str, editable: bool | None, bank_id: str | None,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        progress("Searching text", 0, 1)
        with self._lock:
            rows = self._require_text_catalog().search(
                search, editable=editable, bank_id=bank_id
            )
        progress("Text results ready", 1, 1)
        return rows

    def text_value(self, asset: TextAsset | str) -> str:
        asset_id = asset.asset_id if isinstance(asset, TextAsset) else asset
        with self._lock:
            return self._require_session().text_value(asset_id)

    def number_value(self, asset: RosterNumberAsset | str) -> int:
        asset_id = asset.asset_id if isinstance(asset, RosterNumberAsset) else asset
        with self._lock:
            return self._require_session().number_value(asset_id)

    def replace_text(
        self, asset: TextAsset | str, value: str,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        selected = (
            self._require_text_catalog().get_asset(asset)
            if isinstance(asset, str) else asset
        )
        progress(f"Checking {selected.label}", 0, 1)
        with self._lock:
            result = self._require_session().set_text(selected, value)
        progress("Text replacement ready", 1, 1)
        return result

    def replace_number(
        self, asset: RosterNumberAsset | str, value: int,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        selected = (
            self._require_text_catalog().get_number_asset(asset)
            if isinstance(asset, str) else asset
        )
        progress(f"Checking {selected.label}", 0, 1)
        with self._lock:
            result = self._require_session().set_number(selected, value)
        progress("Jersey number ready", 1, 1)
        return result

    def revert_text(
        self, asset_id: str, progress: ProgressSink = _quiet_progress
    ) -> object:
        progress("Reverting text", 0, 1)
        with self._lock:
            changed = self._require_session().revert_text(asset_id)
        progress("Text reverted", 1, 1)
        return StudioOperationResult(
            "Text reverted." if changed else "That text was already original."
        )

    def export_text(
        self, asset: TextAsset | str, destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        asset_id = asset.asset_id if isinstance(asset, TextAsset) else asset
        progress("Exporting text", 0, 1)
        with self._lock:
            selected = self._require_text_catalog().get_asset(asset_id)
            payload = (self._require_session().text_value(selected.asset_id) + "\n").encode(
                "utf-8"
            )
        requested = _publish_new_export(payload, destination)
        progress("Text exported", 1, 1)
        return requested

    def export_number(
        self, asset: RosterNumberAsset | str, destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export the current staged number without exposing any retail payload."""

        asset_id = asset.asset_id if isinstance(asset, RosterNumberAsset) else asset
        progress("Exporting jersey number", 0, 1)
        with self._lock:
            selected = self._require_text_catalog().get_number_asset(asset_id)
            payload = (
                str(self._require_session().number_value(selected.asset_id)) + "\n"
            ).encode("utf-8")
        requested = _publish_new_export(payload, destination)
        progress("Jersey number exported", 1, 1)
        return requested

    @property
    def modified_crib_asset_ids(self) -> Iterable[str]:
        with self._lock:
            return (
                self._session.modified_crib_asset_ids
                if self._session is not None
                and hasattr(self._session, "modified_crib_asset_ids") else ()
            )

    def list_crib_assets(self) -> Iterable[CribAsset]:
        """Return metadata only; an empty tuple is the safe pre-source state."""

        with self._lock:
            return self._crib_catalog.assets if self._crib_catalog is not None else ()

    def preview_crib_asset(
        self, asset_id: str, progress: ProgressSink
    ) -> Path:
        progress("Preparing Crib PNG", 0, 1)
        with self._lock:
            path = self._require_session().current_crib_path(asset_id)
        progress("Crib PNG ready", 1, 1)
        return path

    def export_crib_asset(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        progress("Exporting Crib PNG", 0, 1)
        with self._lock:
            path = self._require_session().export_crib(asset_id, destination)
        progress("Crib PNG exported", 1, 1)
        return path

    def replace_crib_photo(
        self, asset_id: str, supplied_png: Path, progress: ProgressSink
    ) -> object:
        progress("Checking Crib PNG", 0, 1)
        with self._lock:
            result = self._require_session().replace_crib(asset_id, supplied_png)
        progress("Crib replacement staged", 1, 1)
        return result

    def revert_crib_photo(
        self, asset_id: str, progress: ProgressSink
    ) -> object:
        progress("Reverting Crib texture", 0, 1)
        with self._lock:
            changed = self._require_session().revert_crib(asset_id)
        progress("Crib texture reverted", 1, 1)
        return StudioOperationResult(
            "Original Crib texture restored." if changed else
            "That Crib texture was already original."
        )

    @property
    def modified_audio_asset_ids(self) -> Iterable[str]:
        with self._lock:
            return (
                self._session.modified_audio_asset_ids
                if self._session is not None and
                hasattr(self._session, "modified_audio_asset_ids") else ()
            )

    @property
    def audio_editing_ready(self) -> bool:
        """Cheaply report whether first-edit private safety data is available."""

        with self._lock:
            cache = self._cache
            service = self._audio_service
            return bool(
                cache is not None
                and service is not None
                and (
                    service.audio_origin_ready
                    or self._audio_origin_preparation.is_ready(cache)
                )
            )

    def prepare_audio_editing(
        self,
        progress: ProgressSink,
        cancelled: Callable[[], bool] | None = None,
    ) -> object:
        """Prepare and strictly load source-bound safety data for audio edits."""

        with self._lock:
            cache = self._cache
            service = self._audio_service
            if cache is None or service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before preparing audio editing."
                )
        # Never hold the facade lock during the 20–35 minute first scan or the
        # large strict JSON load.  The exact cache/service identity is checked
        # again before this work is allowed to affect the active project.
        with self._audio_preparation_lock:
            with self._lock:
                if self._cache is not cache or self._audio_service is not service:
                    raise ValidationError(
                        "A different game was loaded before audio editing preparation "
                        "started. Choose the replacement again for the loaded game."
                    )
            result: object = StudioOperationResult(
                "Audio editing safety data was already loaded."
            )
            if not service.audio_origin_ready:
                if not self._audio_origin_preparation.is_ready(cache):
                    result = self._audio_origin_preparation.prepare(
                        cache, progress, cancelled
                    )
                progress("Loading private audio safety data", 0, 1)
                service.load_private_origin_inventories()
                if not service.audio_origin_ready:
                    raise ValidationError(
                        "Audio safety data could not be loaded. Try Prepare Audio "
                        "Editing again; the source XISO was not changed."
                    )
            with self._lock:
                if self._cache is not cache or self._audio_service is not service:
                    raise ValidationError(
                        "A different game was loaded while audio editing was being "
                        "prepared. Nothing was staged. Choose the audio replacement "
                        "again for the game that is loaded now."
                    )
            progress("Audio editing ready", 1, 1)
            return result

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
    ) -> StudioAudioPage:
        if status not in (None, "Modified", "Editable", "Export-only", "Coming Soon"):
            raise ValidationError(
                "Audio status must be All, Modified, Editable, Export-only, or Coming Soon."
            )
        if scope not in {
            PLAYABLE_AUDIO_SCOPE_ID, "standalone", "streaming", "streaming_ranges",
        }:
            raise ValidationError(
                "Audio scope must be all playable sounds, standalone sounds, "
                "streaming banks, or indexed streaming ranges."
            )
        meaning_domain = {
            "menu_back_route_runtime_unproved",
            "reviewed_label_runtime_meaning_unproved",
            "provisional_label_runtime_meaning_unproved",
        }
        if meaning_status is not None and (
            type(meaning_status) is not str
            or meaning_status not in meaning_domain
        ):
            raise ValidationError("Audio meaning-confidence filter is invalid.")
        if meaning_status is not None and scope != "standalone":
            raise ValidationError(
                "Meaning confidence applies only to standalone audio sounds."
            )
        if family is not None and (
            not isinstance(family, str) or not family or len(family) > 64
        ):
            raise ValidationError("Audio family filter is invalid.")
        family_options = (
            STANDALONE_AUDIO_FAMILIES
            if scope == "standalone"
            else PLAYABLE_AUDIO_FAMILIES
            if scope == PLAYABLE_AUDIO_SCOPE_ID
            else STREAMING_AUDIO_FAMILIES
        )
        family_domain = {value for value, _label in family_options}
        if family is not None and family not in family_domain:
            raise ValidationError("That audio family does not belong to this scope.")
        if type(offset) is not int or offset < 0 or type(limit) is not int \
                or not 1 <= limit <= 256:
            raise ValidationError("Audio page selection is outside the supported range.")
        if type(labeled_only) is not bool:
            raise ValidationError("Audio labeled-only filter is invalid.")
        terms = search.casefold().split()
        with self._lock:
            catalog = self._require_audio_catalog()
            annotations = {
                row.cue_id: row
                for row in (
                    self._session.audio_annotations
                    if self._session is not None
                    and hasattr(self._session, "audio_annotations")
                    else ()
                )
            }
            modified = set(
                self._session.modified_audio_asset_ids
                if self._session is not None
                and hasattr(self._session, "modified_audio_asset_ids")
                else ()
            )
            rows = []
            if scope == PLAYABLE_AUDIO_SCOPE_ID:
                candidates = catalog.playable_assets
            elif scope == "standalone":
                candidates = catalog.assets
            elif scope == "streaming":
                candidates = catalog.streaming_banks
            else:
                candidates = catalog.streaming_ranges
            if terms:
                if self._audio_search_catalog is not catalog:
                    self._audio_search_index = _build_audio_search_index(catalog)
                    self._audio_search_catalog = catalog
                indexed_candidates = self._audio_search_index[scope]
            else:
                indexed_candidates = ((asset, "") for asset in candidates)
            for asset, haystack in indexed_candidates:
                annotation = annotations.get(asset.asset_id)
                if labeled_only and annotation is None:
                    continue
                if status == "Modified":
                    if asset.asset_id not in modified:
                        continue
                elif status is not None and asset.edit_status != status:
                    continue
                if family is not None and asset.family_id != family:
                    continue
                if (
                    meaning_status is not None
                    and (
                        not isinstance(asset, Nfl2k5AudioAsset)
                        or standalone_runtime_meaning_status(asset)
                        != meaning_status
                    )
                ):
                    continue
                if not terms:
                    rows.append(asset)
                    continue
                annotation_haystack = (
                    f"{annotation.title} {annotation.note}".casefold()
                    if annotation is not None else ""
                )
                if all(
                    term in haystack or term in annotation_haystack
                    for term in terms
                ):
                    rows.append(asset)
        if rows and offset >= len(rows):
            offset = ((len(rows) - 1) // limit) * limit
        elif not rows:
            offset = 0
        return StudioAudioPage(
            tuple(rows[offset:offset + limit]), len(rows), offset, limit
        )

    def audio_annotation(self, asset_id: str) -> AudioCueAnnotation | None:
        """Return one user-authored cue label without reading game audio."""

        with self._lock:
            self._resolve_annotatable_audio(asset_id)
            session = self._require_session()
            method = getattr(session, "audio_annotation", None)
            return method(asset_id) if callable(method) else None

    @property
    def labeled_audio_asset_ids(self) -> Iterable[str]:
        with self._lock:
            session = self._session
            return (
                session.labeled_audio_asset_ids
                if session is not None
                and hasattr(session, "labeled_audio_asset_ids")
                else frozenset()
            )

    def set_audio_annotation(
        self,
        asset_id: str,
        title: str,
        note: str,
        progress: ProgressSink,
    ) -> object:
        """Save retail-free discovery metadata for one playable logical cue."""

        progress("Saving audio cue label", 0, 1)
        with self._lock:
            asset = self._resolve_annotatable_audio(asset_id)
            changed = self._require_session().set_audio_annotation(
                asset.asset_id, title, note
            )
        progress("Audio cue label saved", 1, 1)
        return StudioOperationResult(
            f"Saved the custom label for {asset.name}."
            if changed else
            f"The custom label for {asset.name} was already current.",
            changed=changed,
        )

    def clear_audio_annotation(
        self, asset_id: str, progress: ProgressSink
    ) -> object:
        """Remove only one user-authored cue label; game audio is untouched."""

        progress("Clearing audio cue label", 0, 1)
        with self._lock:
            asset = self._resolve_annotatable_audio(asset_id)
            changed = self._require_session().clear_audio_annotation(asset.asset_id)
        progress("Audio cue label cleared", 1, 1)
        return StudioOperationResult(
            f"Cleared the custom label for {asset.name}."
            if changed else
            f"{asset.name} did not have a custom label.",
            changed=changed,
        )

    def prepare_audio(self, asset_id: str, progress: ProgressSink) -> Path:
        if asset_id.startswith("nfl2k5.audio.ausb."):
            with self._lock:
                service = self._audio_service
                if service is None:
                    raise ValidationError(
                        "Load your NFL 2K5 XISO before playing streaming audio."
                    )
                item = service.catalog.get_streaming_range(asset_id)
                # The session resolves both original and staged range WAVs.  A
                # shared physical slot therefore previews the same current
                # replacement through every logical owner ID.
                progress("Preparing current streaming-range WAV", 0, 1)
                path = self._require_session().current_audio_path(item)
            progress("WAV ready", item.stored_size, item.stored_size)
            return path
        progress("Preparing WAV", 0, 1)
        with self._lock:
            path = self._require_session().current_audio_path(asset_id)
        progress("WAV ready", 1, 1)
        return path

    def export_audio(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        progress("Exporting WAV", 0, 1)
        with self._lock:
            path = self._require_session().export_audio(asset_id, destination)
        progress("WAV exported", 1, 1)
        return path

    def export_audio_bank(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        with self._lock:
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before exporting streaming audio."
                )
            bank = service.catalog.get_streaming_bank(asset_id)
            path = service.export_streaming_bank(
                bank,
                destination,
                progress=lambda completed, total: progress(
                    "Exporting raw streaming bank", completed, total
                ),
            )
        progress("Raw streaming bank exported", bank.external_size, bank.external_size)
        return path

    def export_audio_range(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        with self._lock:
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before exporting streaming audio."
                )
            item = service.catalog.get_streaming_range(asset_id)
            path = service.export_streaming_range(
                item,
                destination,
                progress=lambda completed, total: progress(
                    "Exporting raw streaming range", completed, total
                ),
            )
        progress("Raw streaming range exported", item.stored_size, item.stored_size)
        return path

    def export_audio_range_wav(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        with self._lock:
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before exporting streaming audio."
                )
            item = service.catalog.get_streaming_range(asset_id)
            progress("Exporting current streaming-range WAV", 0, 1)
            path = self._require_session().export_audio(item, destination)
        progress("Streaming-range WAV exported", item.stored_size, item.stored_size)
        return path

    def audio_affected_asset_ids(self, asset_id: str) -> tuple[str, ...]:
        """Return every logical owner changed by one physical audio edit."""

        with self._lock:
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before checking shared audio owners."
                )
            return service.audio_affected_asset_ids(asset_id)

    def audio_complete_pack_path(self, asset_id: str) -> str | None:
        """Return the public v4 all-850 destination for one standalone cue."""

        with self._lock:
            catalog = self._require_audio_catalog()
            return complete_standalone_pack_path(catalog, asset_id)

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
        """Export one bounded filtered audio collection without mutating a project."""

        if output_format not in {"wav", "bin"}:
            raise ValidationError("Audio collections export as WAV or exact raw audio.")
        if scope == PLAYABLE_AUDIO_SCOPE_ID and output_format != "wav":
            raise ValidationError(
                "All Playable Audio exports as WAV. Raw BIN export is available "
                "only from Streaming Banks or Indexed Streaming Ranges."
            )
        with self._lock:
            page = self.browse_audio(
                search=search,
                status=status,
                offset=0,
                limit=256,
                scope=scope,
                family=family,
                meaning_status=meaning_status,
                labeled_only=labeled_only,
            )
            if not 1 <= page.total <= 256 or len(page.assets) != page.total:
                raise ValidationError(
                    "Export matching audio requires 1–256 rows. Narrow the current "
                    "search, family, or status filters."
                )
            session = self._require_session()
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before exporting an audio collection."
                )
            assets = {asset.asset_id: asset for asset in page.assets}
            rows = tuple(
                _with_audio_annotation(
                    bundle_row_for_asset(
                        asset,
                        output_format=output_format,
                        content_origin=(
                            session.audio_content_origin(asset)
                            if isinstance(asset, Nfl2k5AudioAsset)
                            or (
                                isinstance(asset, Nfl2k5StreamingAudioRange)
                                and output_format == "wav"
                            )
                            else "retail_derived"
                        ),
                    ),
                    session.audio_annotation(asset.asset_id)
                    if hasattr(session, "audio_annotation") else None,
                )
                for asset in page.assets
            )

            def write_payload(row: AudioBundleRow, output: Path) -> Path:
                asset = assets[row.stable_id]
                if isinstance(asset, Nfl2k5AudioAsset):
                    return session.export_audio(asset, output)
                if isinstance(asset, Nfl2k5StreamingAudioBank):
                    return service.export_streaming_bank(asset, output)
                if output_format == "bin":
                    return service.export_streaming_range(asset, output)
                return session.export_audio(asset, output)

            return publish_audio_bundle(
                rows,
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
        """Export exact ordered playable IDs without consulting browser filters."""

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

        with self._lock:
            catalog = self._require_audio_catalog()
            session = self._require_session()
            service = self._audio_service
            if service is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before exporting an audio shortlist."
                )
            standalone = {asset.asset_id: asset for asset in catalog.assets}
            ranges = {item.asset_id: item for item in catalog.streaming_ranges}
            banks = {bank.asset_id for bank in catalog.streaming_banks}
            assets: list[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange] = []
            for asset_id in selected_ids:
                if asset_id in banks:
                    raise ValidationError(
                        "A complete streaming bank is not one playable sound and "
                        "cannot enter an audio shortlist. Choose its indexed ranges "
                        "instead."
                    )
                asset = standalone.get(asset_id)
                if asset is None:
                    asset = ranges.get(asset_id)
                if asset is None:
                    raise ValidationError(
                        f"Unknown shortlisted audio asset: {asset_id}"
                    )
                assets.append(asset)

            by_id = {asset.asset_id: asset for asset in assets}
            rows = tuple(
                _with_audio_annotation(
                    bundle_row_for_asset(
                        asset,
                        output_format="wav",
                        content_origin=session.audio_content_origin(asset),
                    ),
                    session.audio_annotation(asset.asset_id)
                    if hasattr(session, "audio_annotation") else None,
                )
                for asset in assets
            )

            def write_payload(row: AudioBundleRow, output: Path) -> Path:
                asset = by_id[row.stable_id]
                return session.export_audio(asset, output)

            return publish_audio_bundle(
                rows,
                destination,
                bundle_name=bundle_name,
                payload_writer=write_payload,
                progress=lambda completed, total: progress(
                    "Exporting selected NFL 2K5 audio", completed, total
                ),
            )

    def replace_audio(
        self, asset_id: str, supplied_wav: Path, progress: ProgressSink
    ) -> object:
        progress("Checking replacement WAV shape", 0, 3)
        with self._lock:
            cache = self._cache
            service = self._audio_service
            session = self._session
            if cache is None or service is None or session is None:
                raise ValidationError(
                    "Load your NFL 2K5 XISO before replacing audio."
                )
            # Reject a wrong shape immediately, before a first-time source scan
            # that can take several minutes.  The session safely rereads and
            # reauthorizes the caller file after preparation.
            service.read_replacement_snapshot(asset_id, supplied_wav)
        progress("WAV shape accepted", 1, 3)
        self.prepare_audio_editing(progress)
        progress("Staging authorized replacement", 2, 3)
        with self._lock:
            if (
                self._cache is not cache
                or self._audio_service is not service
                or self._session is not session
            ):
                raise ValidationError(
                    "The loaded game or working project changed while audio editing "
                    "was being prepared. Nothing was staged. Choose the replacement "
                    "again for the current project."
                )
            result = session.replace_audio(asset_id, supplied_wav)
        progress("Replacement staged", 3, 3)
        return result

    def export_audio_replacement_template(
        self,
        destination: Path,
        *,
        container: str,
        progress: ProgressSink,
        complete_standalone: bool = False,
        with_authoring_map: bool = False,
        asset_ids: Sequence[str] | None = None,
    ) -> object:
        """Export a mapped all-standalone, plain v3, selected, or legacy pack."""

        with self._lock:
            service = self._audio_replacement_pack_factory(
                self._require_audio_catalog(), self._require_session()
            )
            # Preserve the RC16 v1/v2 service call exactly: both routes always
            # receive ``asset_ids`` and never receive complete/map flags. A
            # direct complete_standalone=True call without the map flag remains
            # the existing v3 route. Forward either opt-in flag only when true,
            # and leave invalid combinations for the core service to reject.
            options: dict[str, object] = {"asset_ids": asset_ids}
            if complete_standalone:
                options["complete_standalone"] = True
            if with_authoring_map:
                options["with_authoring_map"] = True
            return service.export_template(
                destination,
                container=container,
                progress=progress,
                **options,
            )

    def preflight_audio_replacement_pack(
        self, source: Path, progress: ProgressSink
    ) -> object:
        """Validate and simulate one folder/ZIP without changing the project."""

        with self._lock:
            cache = self._cache
            session = self._session
            catalog = self._audio_catalog
            audio_service = self._audio_service
            if (
                cache is None or session is None or catalog is None
                or audio_service is None
            ):
                raise ValidationError(
                    "Load your NFL 2K5 XISO before previewing audio replacements."
                )
        self.prepare_audio_editing(progress)
        with self._lock:
            if (
                self._cache is not cache
                or self._session is not session
                or self._audio_catalog is not catalog
                or self._audio_service is not audio_service
            ):
                raise ValidationError(
                    "The loaded game or working project changed while audio editing "
                    "was being prepared. Preview the replacement pack again."
                )
            service = self._audio_replacement_pack_factory(catalog, session)
            return service.preflight_edited(source, progress=progress)

    def import_audio_replacement_pack(
        self,
        source: Path,
        progress: ProgressSink,
        *,
        confirmation_token: str | None = None,
    ) -> object:
        """Validate and stage one folder/ZIP as a single session transaction."""

        with self._lock:
            cache = self._cache
            session = self._session
            catalog = self._audio_catalog
            audio_service = self._audio_service
            if (
                cache is None or session is None or catalog is None
                or audio_service is None
            ):
                raise ValidationError(
                    "Load your NFL 2K5 XISO before importing audio replacements."
                )
        self.prepare_audio_editing(progress)
        with self._lock:
            if (
                self._cache is not cache
                or self._session is not session
                or self._audio_catalog is not catalog
                or self._audio_service is not audio_service
            ):
                raise ValidationError(
                    "The loaded game or working project changed while audio editing "
                    "was being prepared. No replacement pack was imported."
                )
            service = self._audio_replacement_pack_factory(
                catalog, session
            )
            if confirmation_token is None:
                return service.import_edited(source, progress=progress)
            return service.import_edited(
                source,
                confirmation_token=confirmation_token,
                progress=progress,
            )

    def revert_audio(self, asset_id: str, progress: ProgressSink) -> object:
        progress("Reverting audio", 0, 1)
        with self._lock:
            changed = self._require_session().revert_audio(asset_id)
        progress("Original audio restored", 1, 1)
        return StudioOperationResult(
            "Original audio restored." if changed else
            "That audio was already original."
        )

    def resource_kinds(self, progress: ProgressSink) -> object:
        progress("Reading resource kinds", 0, 1)
        with self._lock:
            index = self._require_universal_index()
            rows = index.kinds()
        progress("Resource kinds ready", 1, 1)
        return rows

    def browse_resources(
        self,
        *,
        search: str,
        kind: str | None,
        offset: int,
        limit: int,
        progress: ProgressSink,
    ) -> object:
        progress("Loading asset page", 0, 1)
        with self._lock:
            index = self._require_universal_index()
            rows = index.query(search=search, kind=kind, offset=offset, limit=limit)
            count = index.asset_count
        progress("Asset page ready", 1, 1)
        return rows, count

    def export_resource(
        self,
        asset: UniversalAssetRecord | str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path:
        progress("Exporting the exact resource wrapper", 0, 1)
        with self._lock:
            path = self._require_universal_index().export_raw(asset, destination)
        progress("Raw resource exported", 1, 1)
        return path

    @property
    def playbook_available(self) -> bool:
        """The source index can construct the private PLAY service on demand."""

        with self._lock:
            return self._universal_index is not None

    def browse_playbooks(
        self, search: str, progress: ProgressSink = _quiet_progress
    ) -> tuple[Nfl2k5Playbook, ...]:
        """Decode and search all 37 source-bound books without persisting them."""

        with self._lock:
            inspector = self._require_playbook_inspector()
            records = inspector.records()
        books: list[Nfl2k5Playbook] = []
        total = len(records)
        progress(f"Reading {total} private PLAY books", 0, total)
        for completed, record in enumerate(records, 1):
            books.append(inspector.load(record))
            progress("Reading private PLAY structure", completed, total)
        with self._lock:
            if self._playbook_inspector is not inspector:
                raise ValidationError(
                    "A different game source was loaded while playbooks were read. "
                    "Open the Playbooks & Plays tab again."
                )
        words = tuple(
            word for word in search.replace("_", " ").casefold().split() if word
        )
        if not words:
            return tuple(books)
        return tuple(
            book for book in books
            if all(
                word in " ".join((
                    book.book_name,
                    book.asset_id,
                    *(formation.name for formation in book.formations),
                    *(play.name for play in book.plays),
                    *(play.family_label for play in book.plays),
                    *(category.name for category in book.categories),
                )).replace("_", " ").casefold()
                for word in words
            )
        )

    def export_playbook(
        self,
        asset_id: str,
        destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export one exact PLAY wrapper/body through the universal route."""

        progress("Checking the selected PLAY resource", 0, 2)
        with self._lock:
            inspector = self._require_playbook_inspector()
            index = self._require_universal_index()
        # Parsing proves the logical selector is one of this source's exact 37
        # PLAY resources before the generic raw exporter is allowed to run.
        inspector.load(asset_id)
        progress("Exporting the exact raw PLAY resource", 1, 2)
        path = index.export_raw(asset_id, destination)
        progress("Raw PLAY resource exported", 2, 2)
        return path

    @property
    def stadium_available(self) -> bool:
        with self._lock:
            return self._session is not None and (
                self._stadium_studio is not None
                or self._stadium_cache_coordinator is not None
            )

    def prepare_stadium_studio(
        self, progress: ProgressSink = _quiet_progress
    ) -> object:
        """Generate private source-derived Stadium assets once, on demand."""

        with self._lock:
            if self._stadium_studio is not None:
                return StudioOperationResult("Stadium Studio is ready.")
            cache = self._cache
            session = self._session
        if cache is None:
            raise ValidationError(
                "Load your NFL 2K5 XISO before preparing Stadium Studio."
            )
        result = self._stadium_cache_coordinator.ensure(cache, progress)
        if session is None:
            raise ValidationError(
                "Load your NFL 2K5 XISO before preparing Stadium Studio."
            )
        studio = self._studio_for_session(result, cache, session)
        with self._lock:
            if self._cache is not cache or self._session is not session:
                raise ValidationError(
                    "A different game source was loaded while Stadium Studio was "
                    "being prepared. Open the Stadiums tab again."
                )
            self._stadium_studio = studio
            self._stadium_cache_result = result
        return StudioOperationResult(
            f"Stadium Studio ready — {result.scene_count:,} private scenes indexed."
        )

    def stadium_scenes(self, search: str, progress: ProgressSink) -> object:
        progress("Loading stadium scenes", 0, 1)
        with self._lock:
            self._require_session()
            studio = self._stadium_studio
        if studio is None:
            self.prepare_stadium_studio(progress)
            with self._lock:
                studio = self._require_stadium_studio()
        with self._lock:
            rows = studio.list_scenes(search=search)
        progress("Stadium scenes ready", 1, 1)
        return rows

    def stadium_details(
        self, scene: StadiumScene | str, progress: ProgressSink
    ) -> StadiumSceneDetails:
        progress("Reading stadium materials and textures", 0, 1)
        with self._lock:
            self._require_session()
            details = self._require_stadium_studio().scene_details(scene)
        progress("Stadium ready", 1, 1)
        return details

    def preview_stadium_texture(self, texture_id: str, progress: ProgressSink) -> Path:
        progress("Preparing stadium texture", 0, 1)
        with self._lock:
            self._require_session()
            path = self._require_stadium_studio().preview_texture(texture_id)
        progress("Stadium texture ready", 1, 1)
        return path

    def export_stadium_texture(
        self, texture_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        progress("Exporting stadium texture", 0, 1)
        with self._lock:
            self._require_session()
            path = self._require_stadium_studio().export_texture(
                texture_id, destination
            )
        progress("Stadium texture exported", 1, 1)
        return path

    def replace_stadium_texture(
        self, texture_id: str, supplied_png: Path, progress: ProgressSink
    ) -> object:
        progress("Checking stadium texture writer", 0, 1)
        with self._lock:
            self._require_session()
            result = self._require_stadium_studio().replace_texture(
                texture_id, supplied_png
            )
        progress("Stadium texture replaced", 1, 1)
        return result

    def revert_stadium_texture(
        self, texture_id: str, progress: ProgressSink
    ) -> object:
        progress("Reverting stadium texture", 0, 1)
        with self._lock:
            self._require_session()
            result = self._require_stadium_studio().revert_texture(texture_id)
        progress("Stadium texture reverted", 1, 1)
        return result

    def stadium_scene_people_texture_ids(
        self, scene_id: str, progress: ProgressSink = _quiet_progress
    ) -> tuple[str, ...]:
        """Texture ids in one stadium scene that are people/sideline assets."""
        progress("Filtering stadium people textures", 0, 1)
        with self._lock:
            self._require_session()
            if self._stadium_studio is None:
                self.prepare_stadium_studio(progress)
            ids = self._require_stadium_studio().scene_people_texture_ids(scene_id)
        progress("Stadium people textures ready", 1, 1)
        return ids

    def stadium_people_and_sideline(
        self, progress: ProgressSink = _quiet_progress
    ) -> tuple[dict[str, object], ...]:
        """List editable stadium people/sideline textures grouped by category.

        Fans, cheerleaders, coaches, officials, chain crew, camera/media,
        ushers, and sideline props are matched by their decoded SCNE names.
        Each returned texture can be previewed, exported, replaced, or reverted
        through the existing stadium texture methods.  The owning 3D geometry is
        not editable here.
        """
        progress("Grouping stadium people and sideline textures", 0, 1)
        with self._lock:
            self._require_session()
            if self._stadium_studio is None:
                self.prepare_stadium_studio(progress)
            studio = self._require_stadium_studio()
            groups = studio.people_and_sideline_textures()
        result = tuple(
            {
                "category": category_id,
                "label": label,
                "count": len(textures),
                "textures": tuple(
                    {
                        "texture_id": texture.texture_id,
                        "scene_id": texture.scene_id,
                        "width": texture.width,
                        "height": texture.height,
                        "format_name": texture.format_name,
                        "mapped_material_names": texture.mapped_material_names,
                    }
                    for texture in textures
                ),
            }
            for category_id, label, textures in groups
        )
        progress("Stadium people and sideline textures ready", 1, 1)
        return result

    def preview_asset(self, asset: UniformAsset, progress: ProgressSink) -> Path:
        progress(f"Preparing {asset.label}", 0, 1)
        with self._lock:
            session = self._require_session()
            path = session.current_path(asset)
        progress(f"{asset.label} ready", 1, 1)
        return path

    def export_asset(
        self, asset: UniformAsset, destination: Path, progress: ProgressSink
    ) -> Path:
        progress(f"Exporting {asset.label}", 0, 1)
        with self._lock:
            path = self._require_session().export_asset(asset, destination)
        progress(f"Exported {asset.label}", 1, 1)
        return path

    def export_team_kit_sets(
        self,
        selectors: Sequence[str],
        destination: Path,
        *,
        container: str,
        progress: ProgressSink,
    ) -> object:
        """Export complete explicit physical sets while source/session stay pinned."""

        with self._lock:
            session = self._require_session()
            service = self._team_kit_service_factory(self.uniform_catalog, session)
            return service.export(
                selectors,
                destination,
                container=container,
                progress=progress,
            )

    def export_team_kit(
        self,
        *,
        asset_code: str,
        variant: int,
        sides: str,
        destination: Path,
        container: str,
        progress: ProgressSink,
    ) -> object:
        """Export one team's HOME, AWAY, or paired complete Team Kit."""

        with self._lock:
            session = self._require_session()
            service = self._team_kit_service_factory(self.uniform_catalog, session)
            return service.export_team(
                asset_code=asset_code,
                variant=variant,
                sides=sides,
                destination=destination,
                container=container,
                progress=progress,
            )

    def import_team_kit(
        self,
        source: Path,
        progress: ProgressSink,
    ) -> object:
        """Validate and stage an edited Team Kit as one locked session action."""

        with self._lock:
            session = self._require_session()
            service = self._team_kit_service_factory(self.uniform_catalog, session)
            return service.import_edited(source, progress=progress)

    def replace_asset(
        self, asset: UniformAsset, supplied_png: Path, progress: ProgressSink
    ) -> object:
        progress(f"Checking {asset.width}×{asset.height} PNG", 0, 1)
        with self._lock:
            result = self._require_session().replace(asset, supplied_png)
        progress(f"{asset.label} ready", 1, 1)
        return result

    def revert_asset(self, asset: UniformAsset, progress: ProgressSink) -> object:
        progress(f"Reverting {asset.label}", 0, 1)
        with self._lock:
            changed = self._require_session().revert(asset)
        progress(f"{asset.label} reverted", 1, 1)
        return StudioOperationResult(
            f"Reverted {asset.label}." if changed
            else f"{asset.label} was already original."
        )

    def undo(self, progress: ProgressSink) -> object:
        progress("Undoing the last edit", 0, 1)
        with self._lock:
            label = self._require_session().undo()
        progress("Undo complete", 1, 1)
        return StudioOperationResult(
            f"Undid: {label}." if label else "There is nothing left to undo."
        )

    def revert_all(self, progress: ProgressSink) -> object:
        progress("Reverting every replacement", 0, 1)
        with self._lock:
            count = self._require_session().revert_all()
        progress("All replacements reverted", 1, 1)
        return StudioOperationResult(
            f"Reverted {count} project change{'s' if count != 1 else ''}."
        )

    def save_project(
        self,
        destination: Path,
        progress: ProgressSink,
        *,
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
        allow_empty: bool = False,
    ) -> object:
        progress("Saving project edits and metadata", 0, 1)
        with self._lock:
            session = self._require_session()
            save_keywords: dict[str, object] = {"replace": replace}
            if expected_target is not None:
                save_keywords["expected_target"] = expected_target
            if allow_empty:
                save_keywords["allow_empty"] = True
            path = session.save_shareable_project(destination, **save_keywords)
            identity = project_target_identity(path)
        progress("Project saved", 1, 1)
        return StudioOperationResult(
            f"Project saved — {path.name}. No retail game data was included.",
            path,
            identity,
        )

    def save_recovery_project(
        self,
        destination: Path,
        expected_source_sha256: str,
        progress: ProgressSink,
    ) -> object:
        """Atomically autosave only if the active source is still the caller's.

        Recovery runs quietly beside the UI.  Binding the write to the source
        hash inside the facade lock prevents a concurrent source switch from
        labeling one game's edit set as another game's recovery archive.
        """

        progress("Saving a private recovery snapshot", 0, 1)
        with self._lock:
            cache = self._cache
            if cache is None or cache.source.sha256 != expected_source_sha256:
                raise ValidationError(
                    "The loaded source changed before recovery could be saved."
                )
            path = self._require_session().save_shareable_project(
                destination, replace=True, allow_empty=True
            )
        progress("Recovery snapshot saved", 1, 1)
        return StudioOperationResult("Recovery snapshot updated.", path)

    def load_project(self, source: Path, progress: ProgressSink) -> object:
        progress("Checking every project replacement", 0, 2)
        opened_identity = project_target_identity(source)
        with self._lock:
            cache = self._cache
            text_catalog = self._text_catalog
            audio_service = self._audio_service
            crib_catalog = self._crib_catalog
            crib_io = self._crib_io
            stadium_result = self._stadium_cache_result
            active_session = self._session
        if cache is None:
            raise ValidationError(
                "Load your own NFL 2K5 XISO before opening a shared project."
            )
        candidate = self.session_factory(cache, self.visual_catalog)
        try:
            return self._load_project_candidate(
                source=source,
                progress=progress,
                opened_identity=opened_identity,
                cache=cache,
                text_catalog=text_catalog,
                audio_service=audio_service,
                crib_catalog=crib_catalog,
                crib_io=crib_io,
                stadium_result=stadium_result,
                active_session=active_session,
                candidate=candidate,
            )
        except BaseException as original_error:
            with self._lock:
                adopted = self._session is candidate
            if not adopted:
                discard = getattr(candidate, "discard_private_workspace", None)
                if callable(discard):
                    try:
                        discard()
                    except BaseException as cleanup_error:
                        raise ValidationError(
                            "Project open failed and its disposable private workspace "
                            f"could not be removed: {cleanup_error}"
                        ) from original_error
            raise

    def _load_project_candidate(
        self,
        *,
        source: Path,
        progress: ProgressSink,
        opened_identity: ProjectTargetIdentity,
        cache: object,
        text_catalog: object | None,
        audio_service: object | None,
        crib_catalog: object | None,
        crib_io: object | None,
        stadium_result: object | None,
        active_session: object | None,
        candidate: object,
    ) -> object:
        """Validate and atomically adopt one disposable candidate session."""

        if text_catalog is not None:
            attach_text = getattr(candidate, "attach_text_catalog", None)
            if callable(attach_text):
                attach_text(text_catalog)
        if audio_service is not None:
            attach_audio = getattr(candidate, "attach_audio_service", None)
            if callable(attach_audio):
                attach_audio(audio_service)
        if crib_catalog is not None and crib_io is not None:
            attach_crib = getattr(candidate, "attach_crib", None)
            if callable(attach_crib):
                attach_crib(crib_catalog, crib_io)
        candidate_stadium = None
        if stadium_result is not None:
            candidate_stadium = self._studio_for_session(
                stadium_result, cache, candidate
            )
        audio_prepared = False
        stadium_prepared = stadium_result is not None
        for _attempt in range(3):
            try:
                count = candidate.load_shareable_project(source)
                break
            except AudioProjectPreparationRequired:
                if audio_prepared or audio_service is None:
                    raise ValidationError(
                        "The project contains audio, but its private safety data "
                        "could not be attached to this working session."
                    ) from None
                if candidate.modified_count or candidate.can_undo:
                    raise ValidationError(
                        "Audio preparation was requested after project edits had "
                        "already been applied. The current workspace was kept."
                    ) from None
                progress("Preparing private audio safety data for this project", 0, 2)
                self.prepare_audio_editing(progress)
                audio_prepared = True
                with self._lock:
                    if self._cache is not cache or self._session is not active_session:
                        raise ValidationError(
                            "The loaded game or working project changed during audio "
                            "preparation. Open the project again."
                        )
                continue
            except StadiumProjectPreparationRequired:
                if stadium_prepared:
                    raise ValidationError(
                        "The project contains a Stadium texture, but its editor could "
                        "not be attached to this working session."
                    ) from None
                if candidate.modified_count or candidate.can_undo:
                    raise ValidationError(
                        "Stadium preparation was requested after project edits had "
                        "already been applied. The current workspace was kept."
                    ) from None
                progress("Preparing private Stadium assets for this project", 0, 2)
                stadium_result = self._stadium_cache_coordinator.ensure(cache, progress)
                candidate_stadium = self._studio_for_session(
                    stadium_result, cache, candidate
                )
                stadium_prepared = True
                continue
        else:
            raise ValidationError(
                "The project still needs private preparation after both supported "
                "preparation passes. The current workspace was kept."
            )
        progress("Project replacements validated", 1, 2)
        current_identity = project_target_identity(source)
        if current_identity != opened_identity:
            raise ValidationError(
                "The project changed outside Mod Studio while it was opening. "
                "The current workspace was kept; open the project again."
            )
        with self._lock:
            if self._cache is not cache or self._session is not active_session:
                raise ValidationError(
                    "The loaded game or working project changed while this project "
                    "was being checked. Open the project again."
                )
            self._session = candidate
            self._last_build = None
            if candidate_stadium is not None:
                self._stadium_studio = candidate_stadium
                self._stadium_cache_result = stadium_result
        progress("Project ready", 2, 2)
        replacement_count = candidate.modified_count
        annotation_count = int(getattr(candidate, "annotation_count", 0))
        parts = [
            f"{replacement_count} replacement"
            f"{'s' if replacement_count != 1 else ''}"
        ]
        if annotation_count:
            parts.append(
                f"{annotation_count} audio cue label"
                f"{'s' if annotation_count != 1 else ''}"
            )
        return StudioOperationResult(
            f"Loaded {' and '.join(parts)} from {source.name}. "
            + (
                "Build when you are ready."
                if replacement_count else
                "Cue labels are project metadata and do not change a built XISO."
            ),
            current_identity.path,
            current_identity,
        )

    def build_iso(self, destination: Path, progress: ProgressSink) -> object:
        with self._lock:
            cache = self._cache
            session = self._require_session()
        if cache is None:
            raise ValidationError("Load your NFL 2K5 XISO before building.")

        def build_progress(event: BuildEvent) -> None:
            progress(event.message, event.completed, event.total)

        result = self.build_service.build(cache, session, destination, build_progress)
        with self._lock:
            self._last_build = result
        return result

    def launch_xemu(self, progress: ProgressSink) -> object:
        with self._lock:
            result = self._last_build
            command = self._xemu_command
        if not command:
            raise ValidationError(
                "xemu is not configured. Install xemu or its app.xemu.xemu Flatpak."
            )
        if result is None or not result.output_xiso.is_file() \
                or result.output_xiso.is_symlink():
            raise ValidationError("Build a modded XISO before launching xemu.")
        progress("Starting xemu", 0, 1)
        argv = (*command, "-dvd_path", str(result.output_xiso))
        try:
            self._process_launcher(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
        except OSError as exc:
            raise ValidationError(f"xemu could not be started: {exc}") from exc
        progress("xemu launched", 1, 1)
        return StudioOperationResult(
            f"xemu launched with {result.output_xiso.name}.", result.output_xiso
        )

    def _require_session(self) -> StudioSession:
        if self._session is None:
            raise ValidationError("Load your NFL 2K5 XISO before using this action.")
        return self._session

    def _require_universal_index(self) -> Nfl2k5UniversalAssetIndex:
        if self._universal_index is None:
            raise ValidationError("Load your NFL 2K5 XISO before browsing its assets.")
        return self._universal_index

    def _require_playbook_inspector(self) -> Nfl2k5PlaybookInspector:
        if self._playbook_inspector is None:
            self._playbook_inspector = self._playbook_inspector_factory(
                self._require_universal_index()
            )
        return self._playbook_inspector

    @staticmethod
    def _studio_from_stadium_cache(
        result: StadiumCacheResult,
    ) -> Nfl2k5StadiumStudio:
        return Nfl2k5StadiumStudio(
            result.gltf_manifest,
            result.texture_manifest,
            result.texture_root,
            geometry_catalog=None,
        )

    def _studio_for_session(
        self,
        result: StadiumCacheResult,
        cache: SourceCache,
        session: StudioSession,
    ) -> Nfl2k5StadiumStudio:
        """Bind the source-derived fixed-allocation Stadium P8 writer."""

        studio = self._studio_from_stadium_cache(result)
        attach = getattr(session, "attach_stadium_texture", None)
        if not callable(attach):
            return studio
        details = studio.scene_details(TARGET_SCENE_ID)
        texture = next(
            (row for row in details.textures if row.texture_id == TARGET_TEXTURE_ID),
            None,
        )
        if texture is None:
            raise ValidationError(
                "The private Stadium cache is missing its baseline proved texture."
            )
        writer = Nfl2k5StadiumTextureWriter(cache, result)
        attach(writer, texture)
        return Nfl2k5StadiumStudio(
            result.gltf_manifest,
            result.texture_manifest,
            result.texture_root,
            geometry_catalog=None,
            edit_delegate=session.stadium_delegate,
        )

    def _require_stadium_studio(self) -> Nfl2k5StadiumStudio:
        if self._stadium_studio is None:
            raise ValidationError(
                "Stadium previews have not been generated from this copy yet. "
                "Open the Stadiums tab to prepare the private glTF and texture "
                "cache; interrupted preparation resumes automatically."
            )
        return self._stadium_studio

    def _require_text_catalog(self) -> Nfl2k5TextCatalog:
        if self._text_catalog is None:
            raise ValidationError(
                "Load your NFL 2K5 XISO before browsing or editing text."
            )
        return self._text_catalog

    def _require_audio_catalog(self) -> Nfl2k5AudioCatalog:
        if self._audio_catalog is None:
            raise ValidationError(
                "Load your NFL 2K5 XISO before browsing or editing audio."
            )
        return self._audio_catalog

    def _resolve_annotatable_audio(
        self, asset_id: str
    ) -> Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange:
        """Resolve a logical playable row; complete/raw banks cannot own labels."""

        if type(asset_id) is not str or not asset_id:
            raise ValidationError("Choose a playable audio cue before labeling it.")
        catalog = self._require_audio_catalog()
        try:
            return catalog.get_asset(asset_id)
        except ValidationError:
            try:
                return catalog.get_streaming_range(asset_id)
            except ValidationError as exc:
                raise ValidationError(
                    "Custom labels apply to standalone sounds and exact playable "
                    "streaming ranges, not complete or opaque audio banks."
                ) from exc


__all__ = [
    "Nfl2k5StudioFacade",
    "StudioOperationResult",
    "collect_nfl2k5_gameplay_inspection",
    "collect_nfl2k5_main_menu_inspection",
    "serialize_gameplay_inspection_csv",
    "serialize_main_menu_inspection_csv",
]
