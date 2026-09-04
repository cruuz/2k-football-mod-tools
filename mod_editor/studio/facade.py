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
from typing import Callable, Iterable, Mapping, Sequence

from mod_editor.core.errors import ValidationError
from mod_editor.core.texture_master import (
    AuthoringTransform,
    save_texture_master_bundle,
)
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
from mod_editor.core.nfl2k5_playbook_route_writer import (
    PlayRouteCloneRequest,
    route_selector as play_route_selector,
)
from mod_editor.core.nfl2k5_formation_play_writer import (
    FormationLinkRequest,
    FormationCreateRequest,
    PlayCreateRequest,
    formation_request_from_mapping,
    play_request_from_mapping,
)
from mod_editor.core import nfl2k5_playbook_pack as playbook_pack
from mod_editor.core.nfl2k5_stadium_studio import (
    Nfl2k5StadiumStudio,
    StadiumGltfTextureWriteBack,
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
from mod_editor.core.nfl2k5_crib_geometry_writer import (
    compile_crib_geometry_recipe,
    export_crib_scene_gltf,
    list_editable_scenes as list_editable_crib_geometry_scenes,
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
    FAMILY_REVIEWED_MEANING_STATUS,
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
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
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
_STADIUM_GEOMETRY_CATALOG = (
    _PRODUCT_ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
)
_GAMEPLAY_SNAPSHOT = (
    _PRODUCT_ROOT / "mod_editor/data/nfl2k5_gameplay_inspection.v1.json"
)
_GAMEPLAY_SNAPSHOT_SIZE = 22_874
_GAMEPLAY_SNAPSHOT_SHA256 = (
    "e613180ecb825187aabd0ece2c70d3fc42fa01756a7920981d2c2bccbe53feb7"
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
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
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
        # ``opened`` and ``after`` are both os.fstat of this one descriptor.
        # Two fd stats agree on st_ctime_ns on every platform, Windows
        # included, so it stays in the fingerprint here and the
        # metadata-only-change signal is not lost on any platform.
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
class ExternalBuild:
    """A disc written outside the texture-project build (Build & Share); only the path matters to Launch."""

    output_xiso: Path


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
        if asset.family_reviewed_label is not None:
            extra = (*extra, asset.family_reviewed_label)
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


#: Where a chosen xemu executable is remembered between sessions, matching the
#: APF editor's ``~/.config/apf2k8-mod-studio/settings.json``.
XEMU_SETTINGS_PATH = Path.home() / ".config" / "2k5-mod-studio" / "settings.json"
XEMU_SETTINGS_SCHEMA = "2k5_mod_studio_xemu_settings/v1"


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


def _stored_xemu_command(path: Path | None = None) -> tuple[str, ...]:
    """The xemu executable the user chose, if it is still runnable."""

    settings = path or XEMU_SETTINGS_PATH
    try:
        document = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(document, dict) or document.get("schema") != XEMU_SETTINGS_SCHEMA:
        return ()
    chosen = document.get("xemu_path")
    if not isinstance(chosen, str) or not chosen:
        return ()
    executable = Path(chosen)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return ()
    return (str(executable),)


def _store_xemu_command(executable: Path, path: Path | None = None) -> None:
    settings = path or XEMU_SETTINGS_PATH
    settings.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"schema": XEMU_SETTINGS_SCHEMA, "xemu_path": str(executable)},
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary = settings.with_name(f".{settings.name}.{os.getpid()}.tmp")
    # Explicit newline: this file is compared byte-for-byte across platforms,
    # so the host must never choose CRLF for it.
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(temporary, settings)


def _xemu_launch_argv(command: Sequence[str], xiso: Path) -> tuple[str, ...]:
    """The exact argv to start, including sandbox access for a Flatpak xemu.

    A Flatpak xemu can only open paths its sandbox exposes, and a modded XISO
    normally lands somewhere it has no permission for -- an external drive, a
    project folder outside home. The launch then failed with an I/O error that
    read like a bad build rather than a sandbox refusal. Granting read-only
    access to that one directory for this one run is the narrowest fix, and
    nothing is ever written back through it.
    """

    argv = tuple(command)
    if len(argv) >= 3 and Path(argv[0]).name == "flatpak" and argv[1] == "run":
        share = f"--filesystem={xiso.parent}:ro"
        return (*argv[:2], share, *argv[2:], "-dvd_path", str(xiso))
    return (*argv, "-dvd_path", str(xiso))


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
        # A caller-supplied command wins (tests, packaging). Otherwise the
        # user's own choice comes first and auto-detection is the fallback.
        self._xemu_command_pinned = xemu_command is not None
        self._xemu_command = (
            tuple(xemu_command)
            if xemu_command is not None
            else (_stored_xemu_command() or _detect_xemu_command())
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
    def models_source_paths(self) -> tuple[Path, Path] | None:
        """(pack-0 archive index, resource inventory) of the private source cache, for the Models page.

        Both files are derived from the user's own disc by the source cache, so a model exported
        here is the user's own game data regardless of how their disc image is laid out.
        """

        with self._lock:
            cache = self._cache
            if cache is None:
                return None
            return (Path(cache.pack0), Path(cache.inventory))

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
        return not self.xemu_blocker

    def register_external_build(self, image: Path) -> None:
        """Make a disc written by Build & Share the build that Launch starts.

        Until now only the texture-project build counted as "the latest build", so a
        modder who built a patched copy on the Build & Share page saw Launch Latest
        Build stay tied to an older (or nonexistent) project build. The page's own
        finished copy is what they want to run."""

        image = Path(image)
        if not image.is_file() or image.is_symlink():
            raise ValidationError(f"The built copy is not a regular file: {image}")
        with self._lock:
            self._last_build = ExternalBuild(output_xiso=image)

    @property
    def xemu_blocker(self) -> str:
        """Why one-click launch is unavailable, or ``""`` when it is ready.

        The button used to gray out with one message covering two unrelated
        causes -- no build yet, and no emulator found -- so a modder could not
        tell which one applied to them. Naming the exact blocker is what makes
        the control honest.
        """

        if not self.xemu_command:
            return (
                "xemu was not found. Install it (or its app.xemu.xemu Flatpak), "
                "or choose the xemu executable yourself with Configure xemu."
            )
        with self._lock:
            result = self._last_build
        if result is None:
            return (
                "Build a modded XISO first — Launch starts the most recent "
                "build, and there is not one yet in this session."
            )
        if not result.output_xiso.is_file() or result.output_xiso.is_symlink():
            return (
                f"The last build is no longer at {result.output_xiso}. Build "
                "again, then launch."
            )
        return ""

    @property
    def xemu_command(self) -> tuple[str, ...]:
        """The resolved xemu invocation, re-detected while it is still unknown.

        Detection used to run once, when the app started. Someone who installed
        xemu because the editor told them to then had to restart the editor
        before the button believed them.
        """

        with self._lock:
            if self._xemu_command or self._xemu_command_pinned:
                return self._xemu_command
        found = _stored_xemu_command() or _detect_xemu_command()
        with self._lock:
            if not self._xemu_command and not self._xemu_command_pinned:
                self._xemu_command = found
            return self._xemu_command

    def configure_xemu(self, executable: Path) -> tuple[str, ...]:
        """Remember the xemu executable the user picked, for every session."""

        chosen = Path(executable).expanduser()
        try:
            chosen = chosen.resolve(strict=True)
        except OSError as exc:
            raise ValidationError(f"That xemu path could not be opened: {exc}") from exc
        if not chosen.is_file():
            raise ValidationError(
                "Choose the xemu program itself, not a folder or a shortcut."
            )
        if not os.access(chosen, os.X_OK):
            raise ValidationError(
                f"{chosen.name} is not executable. Choose the xemu binary, or "
                "mark it executable first."
            )
        try:
            _store_xemu_command(chosen)
        except OSError as exc:
            raise ValidationError(
                f"The xemu choice could not be saved: {exc}"
            ) from exc
        with self._lock:
            self._xemu_command = (str(chosen),)
            self._xemu_command_pinned = False
        return (str(chosen),)

    @property
    def last_build_output(self) -> Path | None:
        with self._lock:
            return self._last_build.output_xiso if self._last_build else None

    def preflight_visual_edits(
        self, progress: ProgressSink = _quiet_progress
    ) -> tuple[object, ...]:
        """Predict what each staged PNG will become in its fixed slot.

        Read-only, and safe to run at any time: it changes no session state and
        tells the user which replacements come through untouched, which lose
        palette entries to fit a fixed compressed span, and which cannot fit at
        all -- before a build makes that decision silently.
        """

        from mod_editor.core import nfl2k5_import_preflight as preflight

        with self._lock:
            session = self._require_session()
            staged = session.staged_preflight_inputs()
        if not staged:
            progress("Nothing staged to check", 1, 1)
            return ()
        # The ladder runs for seconds per slot, so it runs outside the lock --
        # holding it would freeze every status field the window polls.
        rows = preflight.predict_edits(staged, progress=progress)
        progress("Image check complete", len(staged), len(staged))
        return rows

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

    def _attach_visual_catalog(self, session: object) -> None:
        """Hand a new session the aggregate this facade already loaded.

        The session can derive its own, but building the extended catalog costs
        about 1.7 s and this one is already in memory. Duck-typed so a
        stand-in session factory needs no new signature.
        """

        attach = getattr(session, "attach_visual_catalog", None)
        if callable(attach):
            attach(self.visual_catalog)

    def load_source(self, source_xiso: Path, progress: ProgressSink) -> object:
        cache = self.source_cache.index(source_xiso, progress)
        progress("Preparing the complete asset browser", 0, 1)
        universal_index = self._universal_index_factory(cache)
        session = self.session_factory(cache, self.uniform_catalog)
        self._attach_visual_catalog(session)
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

    def list_crib_model_scenes(self) -> tuple[dict[str, object], ...]:
        """Return the seven scenes with bounded position-only model import."""

        with self._lock:
            if self._session is None:
                return ()
            return list_editable_crib_geometry_scenes()

    @property
    def modified_crib_model_scene_ids(self) -> frozenset[str]:
        with self._lock:
            session = self._session
            if session is None or not hasattr(
                session, "modified_crib_model_scene_ids"
            ):
                return frozenset()
            return frozenset(session.modified_crib_model_scene_ids)

    def export_crib_model(
        self, scene_id: str, destination: Path, progress: ProgressSink
    ) -> tuple[Path, Path]:
        """Export one source-derived Crib scene glTF and adjacent buffer."""

        progress("Exporting Crib model", 0, 1)
        with self._lock:
            cache = self._cache
            self._require_session()
            if cache is None:
                raise ValidationError("Load your NFL 2K5 XISO first.")
            paths = export_crib_scene_gltf(
                cache.pack0, cache.inventory, scene_id, destination
            )
        progress("Crib model exported", 1, 1)
        return paths

    def _crib_model_source_export(self, scene_id: str) -> Path:
        cache = self._cache
        self._require_session()
        if cache is None:
            raise ValidationError("Load your NFL 2K5 XISO first.")
        key = hashlib.sha256(scene_id.encode("utf-8")).hexdigest()
        directory = cache.originals / "crib-models" / key
        source = directory / "source.gltf"
        if not source.exists():
            directory.mkdir(parents=True, exist_ok=True)
            export_crib_scene_gltf(
                cache.pack0, cache.inventory, scene_id, source
            )
        # The compiler revalidates the source positions/topology against the
        # pinned retail-free catalog; a modified private cache cannot stage.
        return source

    def import_crib_model(
        self, scene_id: str, edited_gltf: Path, progress: ProgressSink
    ) -> object:
        """Stage same-topology vertex moves after a full fixed-span preflight."""

        progress("Validating edited Crib model", 0, 2)
        with self._lock:
            source = self._crib_model_source_export(scene_id)
            compiled = compile_crib_geometry_recipe(
                scene_id, source, edited_gltf
            )
            progress("Checking fixed Crib scene allocation", 1, 2)
            result = self._require_session().replace_crib_geometry(compiled)
        progress("Edited Crib model staged", 2, 2)
        return result

    def revert_crib_model(
        self, scene_id: str, progress: ProgressSink
    ) -> object:
        progress("Reverting edited Crib model", 0, 1)
        with self._lock:
            changed = self._require_session().revert_crib_geometry(scene_id)
        progress("Crib model reverted", 1, 1)
        return StudioOperationResult(
            "Original Crib model positions restored." if changed else
            "That Crib model was already original."
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
            FAMILY_REVIEWED_MEANING_STATUS,
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
            attach_playbooks = getattr(
                self._require_session(), "attach_playbook_inspector", None
            )
            if callable(attach_playbooks):
                attach_playbooks(inspector)
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

    def export_playbook_link_table_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export a PLAY with one formation's play-link table copied from a donor.

        **Experimental / offline-only.** Writes a private copy under
        ``destination``. Does **not** stage a project edit, does **not** claim
        runtime G2 (TE→WR) fix, and never mutates the loaded source archive.
        Independent byte-diff verifier runs inside the patch builder.
        """

        from mod_editor.core.playbook_package_rule_spike import (
            build_formation_link_table_copy_patch,
            verify_formation_link_table_copy_patch,
        )

        progress("Reading stock PLAY for experimental link-table copy", 0, 3)
        with self._lock:
            inspector = self._require_playbook_inspector()
            index = self._require_universal_index()
        book = inspector.load(asset_id)
        if not 0 <= target_formation_index < len(book.formations):
            raise ValidationError(
                f"Target formation {target_formation_index} is outside this book."
            )
        if not 0 <= donor_formation_index < len(book.formations):
            raise ValidationError(
                f"Donor formation {donor_formation_index} is outside this book."
            )
        if target_formation_index == donor_formation_index:
            raise ValidationError("Donor and target formations must differ.")

        # Same raw path as export_playbook, into a temp buffer then patch.
        progress("Building offline link-table copy (menu composition only)", 1, 3)
        import tempfile

        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="2k5-play-link-copy-") as tmpdir:
            src_path = Path(tmpdir) / "source.PLAY.bin"
            index.export_raw(asset_id, src_path)
            source_bytes = src_path.read_bytes()
            patch = build_formation_link_table_copy_patch(
                source_bytes, target_formation_index, donor_formation_index
            )
            verify_formation_link_table_copy_patch(
                source_bytes,
                patch.raw_resource,
                target_formation_index,
                donor_formation_index,
            )
            dest.write_bytes(patch.raw_resource)
        progress(
            "Experimental patched PLAY exported "
            f"(links {patch.target_link_count_before}→{patch.target_link_count_after}; "
            "runtime unproved)",
            3,
            3,
        )
        return dest

    def export_playbook_package_map_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export a PLAY with one formation package map copied from a donor.

        **Experimental / offline-only.** Private file only. Does not stage a
        project edit. Does not claim a runtime G1 (Dime ILB→OLB) fix. Source
        archive never mutated. Independent verifier inside the patch path.
        """

        from mod_editor.core.playbook_package_rule_spike import (
            build_formation_package_map_patch,
            read_formation_package_map,
            verify_formation_package_map_patch,
        )

        progress("Reading stock PLAY for experimental package-map copy", 0, 3)
        with self._lock:
            inspector = self._require_playbook_inspector()
            index = self._require_universal_index()
        book = inspector.load(asset_id)
        if not 0 <= target_formation_index < len(book.formations):
            raise ValidationError(
                f"Target formation {target_formation_index} is outside this book."
            )
        if not 0 <= donor_formation_index < len(book.formations):
            raise ValidationError(
                f"Donor formation {donor_formation_index} is outside this book."
            )
        if target_formation_index == donor_formation_index:
            raise ValidationError("Donor and target formations must differ.")

        progress("Building offline package-map copy (G1 surface; runtime unproved)", 1, 3)
        import tempfile

        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="2k5-play-pkgmap-copy-") as tmpdir:
            src_path = Path(tmpdir) / "source.PLAY.bin"
            index.export_raw(asset_id, src_path)
            source_bytes = src_path.read_bytes()
            donor_map = read_formation_package_map(
                source_bytes, donor_formation_index
            )
            patch = build_formation_package_map_patch(
                source_bytes, target_formation_index, donor_map
            )
            verify_formation_package_map_patch(
                source_bytes,
                patch.raw_resource,
                target_formation_index,
                donor_map,
            )
            dest.write_bytes(patch.raw_resource)
        progress(
            "Experimental package-map PLAY exported "
            f"(formation {target_formation_index} ← {donor_formation_index}; "
            "runtime unproved)",
            3,
            3,
        )
        return dest

    def export_g1_dime_from_nickel_package_map_pack(
        self,
        asset_id: str,
        destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export a PLAY with every Dime package map copied from Nickel.

        **Experimental / offline-only multi-formation G1 pack.** Private PLAY
        + honesty JSON sidecar. Does not stage a project edit. Does not claim a
        runtime G1 fix. Source archive never mutated.
        """

        import json
        import tempfile

        from mod_editor.core.playbook_package_rule_spike import (
            build_g1_dime_from_nickel_package_map_pack,
        )

        progress("Reading stock PLAY for G1 multi-Dime package-map pack", 0, 3)
        with self._lock:
            inspector = self._require_playbook_inspector()
            index = self._require_universal_index()
        # Ensure the book is loadable (raises if missing).
        inspector.load(asset_id)

        progress(
            "Building offline G1 pack (all Dime ← Nickel map; runtime unproved)",
            1,
            3,
        )
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="2k5-g1-dime-pack-") as tmpdir:
            src_path = Path(tmpdir) / "source.PLAY.bin"
            index.export_raw(asset_id, src_path)
            source_bytes = src_path.read_bytes()
            pack = build_g1_dime_from_nickel_package_map_pack(source_bytes)
            dest.write_bytes(pack.raw_resource)
            sidecar = dest.with_suffix(dest.suffix + ".g1_manifest.json")
            if not sidecar.suffix.endswith(".json"):
                sidecar = Path(str(dest) + ".g1_manifest.json")
            sidecar.write_text(
                json.dumps(pack.manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        progress(
            "Experimental G1 multi-Dime package-map PLAY exported "
            f"({len(pack.targets)} Dime target(s); runtime unproved)",
            3,
            3,
        )
        return dest

    def export_g2_ace_from_quads_link_table_pack(
        self,
        asset_id: str,
        destination: Path,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Export a PLAY with every Ace play-link table copied from Quads.

        **Experimental / offline-only multi-formation G2 pack.** Private PLAY
        + honesty JSON sidecar. Does not stage a project edit. Does not claim a
        runtime G2 fix. Source archive never mutated. Menu composition only —
        package maps and play assignments are untouched.
        """

        import json
        import tempfile

        from mod_editor.core.playbook_package_rule_spike import (
            build_g2_ace_from_quads_link_table_pack,
        )

        progress("Reading stock PLAY for G2 multi-Ace link-table pack", 0, 3)
        with self._lock:
            inspector = self._require_playbook_inspector()
            index = self._require_universal_index()
        inspector.load(asset_id)

        progress(
            "Building offline G2 pack (all Ace ← Quads menu; runtime unproved)",
            1,
            3,
        )
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="2k5-g2-ace-pack-") as tmpdir:
            src_path = Path(tmpdir) / "source.PLAY.bin"
            index.export_raw(asset_id, src_path)
            source_bytes = src_path.read_bytes()
            pack = build_g2_ace_from_quads_link_table_pack(source_bytes)
            dest.write_bytes(pack.raw_resource)
            sidecar = dest.with_suffix(dest.suffix + ".g2_manifest.json")
            if not sidecar.suffix.endswith(".json"):
                sidecar = Path(str(dest) + ".g2_manifest.json")
            sidecar.write_text(
                json.dumps(pack.manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        progress(
            "Experimental G2 multi-Ace link-table PLAY exported "
            f"({len(pack.targets)} Ace target(s); runtime unproved)",
            3,
            3,
        )
        return dest

    def copy_play_assignment_route(
        self,
        asset_id: str,
        target_play_index: int,
        target_slot_index: int,
        donor_play_index: int,
        donor_slot_index: int,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        """Copy one exact stock assignment route inside the same PLAY book."""

        progress("Checking source and target assignment routes", 0, 2)
        request = PlayRouteCloneRequest(
            asset_id, target_play_index, target_slot_index,
            donor_play_index, donor_slot_index,
        )
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            changed = session.copy_play_assignment_route(request)
        progress("Assignment route copied", 2, 2)
        return StudioOperationResult(
            "Assignment route copied. Build uses the donor's exact existing "
            "descriptor and chain; waypoint drawing is not implied."
            if changed else "That assignment route copy is already staged."
        )

    def revert_play_assignment_route(
        self,
        asset_id: str,
        target_play_index: int,
        target_slot_index: int,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        progress("Reverting assignment route", 0, 1)
        selector = play_route_selector(
            asset_id, target_play_index, target_slot_index
        )
        with self._lock:
            changed = self._require_session().revert_play_assignment_route(selector)
        progress("Assignment route reverted", 1, 1)
        return StudioOperationResult(
            "Assignment route reverted."
            if changed else "That assignment route is already original."
        )

    def create_formation(
        self,
        asset_id: str,
        donor_formation_index: int,
        custom_name: str | None = None,
        progress: ProgressSink = _quiet_progress,
        slot_positions: object = None,
        category_index: int | None = None,
        replace_index: int | None = None,
        category_positions: object = None,
    ) -> object:
        progress("Creating formation", 0, 2)
        request = formation_request_from_mapping({
            "asset_id": asset_id,
            "donor_formation_index": donor_formation_index,
            "custom_name": custom_name,
            "slot_positions": slot_positions,
            "category_index": category_index,
            "replace_index": replace_index,
            "category_positions": category_positions,
        })
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            changed = session.create_formation(request)
        progress("Formation created", 2, 2)
        return StudioOperationResult(
            "Formation created as clone — new formation appears at end of book."
            if changed else "That formation clone is already staged."
        )

    def create_play(
        self,
        asset_id: str,
        donor_play_index: int,
        custom_name: str | None = None,
        progress: ProgressSink = _quiet_progress,
        assignments: object = None,
    ) -> object:
        progress("Creating play", 0, 2)
        request = play_request_from_mapping({
            "asset_id": asset_id,
            "donor_play_index": donor_play_index,
            "custom_name": custom_name,
            "assignments": assignments,
        })
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            changed = session.create_play(request)
        progress("Play created", 2, 2)
        return StudioOperationResult(
            "Play created as clone — new play appears at end of book."
            if changed else "That play clone is already staged."
        )

    def playbook_raw_body(self, asset_id: str) -> bytes:
        """The fixed 0x13390 PLAY body of one private book (for the designers)."""
        from nfl_outer import read_entry_range

        with self._lock:
            inspector = self._require_playbook_inspector()
            record = inspector.index.get(asset_id)
            entry = inspector.index.archive.entries[record.outer_index]
            raw = read_entry_range(inspector.index.archive, entry, record.chunk_offset, record.raw_size)
        return raw[0x20:]

    def staged_replace_targets(self, asset_id: str) -> tuple[set[int], set[int]]:
        """Stock (formation, play) indices already replaced by staged creates in this book."""
        with self._lock:
            session = self._session
            if session is None:
                return set(), set()
            forms = {r.replace_index for r in session.formation_creates
                     if r.asset_id == asset_id and r.replace_index is not None}
            plays = {r.replace_index for r in session.play_creates
                     if r.asset_id == asset_id and r.replace_index is not None}
        return forms, plays

    def stage_formation_selector(self, asset_id: str, donor_formation_index: int, custom_name: str | None,
                                 slot_positions: object, category_index: int | None,
                                 replace_index: int | None = None, category_positions: object = None) -> str:
        request = formation_request_from_mapping({
            "asset_id": asset_id, "donor_formation_index": donor_formation_index, "custom_name": custom_name,
            "slot_positions": slot_positions, "category_index": category_index, "replace_index": replace_index,
            "category_positions": category_positions,
        })
        return request.selector

    def create_authored_play(
        self,
        asset_id: str,
        donor_play_index: int,
        custom_name: str | None,
        assignments: object,
        link_formation_index: int | None = None,
        link_formation_selector: str | None = None,
        progress: ProgressSink = _quiet_progress,
        replace_index: int | None = None,
        play_flags: int | None = None,
        link_group: int | None = None,
    ) -> object:
        """Stage an authored play and, optionally, list it in a formation.

        ``link_formation_selector`` names a formation create staged in this
        session (its Build index is derived from the build's row order);
        ``link_formation_index`` names an existing formation; ``replace_index``
        overwrites a stock play in place (its existing menu listings stay).
        """
        progress("Creating play", 0, 3)
        mapping: dict[str, object] = {
            "asset_id": asset_id, "donor_play_index": donor_play_index,
            "custom_name": custom_name, "assignments": assignments, "replace_index": replace_index,
        }
        if play_flags is not None:
            mapping["play_flags"] = int(play_flags)
        request = play_request_from_mapping(mapping)
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            book = inspector.load(asset_id)
            changed = session.create_play(request)
            message = "Play staged with authored assignments."
            if link_formation_index is not None or link_formation_selector is not None:
                progress("Listing play", 1, 3)
                play_index = (
                    replace_index if replace_index is not None
                    else session.staged_play_index(request.selector, len(book.plays))
                )
                formation_index = (
                    session.staged_formation_index(link_formation_selector, len(book.formations))
                    if link_formation_selector is not None else int(link_formation_index)
                )
                link = FormationLinkRequest(asset_id, formation_index, play_index, link_group)
                session.create_formation_link(link)
                message += f" Listed as play {play_index} in formation {formation_index}"
                message += (f" (audible group {link_group})." if link_group is not None else ".")
        progress("Play created", 3, 3)
        return StudioOperationResult(message if changed else "That authored play is already staged.")

    def revert_formation_create(self, selector: str, progress: ProgressSink = _quiet_progress) -> object:
        progress("Reverting formation", 0, 1)
        with self._lock:
            changed = self._require_session().revert_formation_create(selector)
        progress("Formation reverted", 1, 1)
        return StudioOperationResult("Formation reverted." if changed else "Already original.")

    def revert_play_create(self, selector: str, progress: ProgressSink = _quiet_progress) -> object:
        progress("Reverting play", 0, 1)
        with self._lock:
            changed = self._require_session().revert_play_create(selector)
        progress("Play reverted", 1, 1)
        return StudioOperationResult("Play reverted." if changed else "Already original.")

    def create_formation_link(
        self,
        asset_id: str,
        formation_index: int,
        play_index: int,
        group: int | None = None,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        progress("Listing play in formation", 0, 2)
        request = FormationLinkRequest(asset_id, formation_index, play_index, group)
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            changed = session.create_formation_link(request)
        progress("Play listed", 2, 2)
        return StudioOperationResult(
            "Play listed in the formation's first empty menu slot."
            if changed else "That link is already staged."
        )

    def revert_formation_link(self, selector: str, progress: ProgressSink = _quiet_progress) -> object:
        progress("Reverting link", 0, 1)
        with self._lock:
            changed = self._require_session().revert_formation_link(selector)
        progress("Link reverted", 1, 1)
        return StudioOperationResult("Link reverted." if changed else "Already original.")

    # -- community playbook packs (.2k5book) -------------------------------------------------

    def playbook_teams(self) -> tuple[str, ...]:
        """The team books this source carries, in the pack format's order."""

        available = {book.book_name for book in self._playbook_books()}
        return tuple(name for name in playbook_pack.TEAM_BOOKS if name in available)

    def _playbook_books(self) -> tuple[Nfl2k5Playbook, ...]:
        with self._lock:
            inspector = self._require_playbook_inspector()
        return inspector.load_all()

    def _playbook_book_for_team(self, team: str) -> tuple[str, Nfl2k5Playbook, bytes]:
        for book in self._playbook_books():
            if book.book_name == team:
                return book.asset_id, book, self.playbook_raw_body(book.asset_id)
        raise ValidationError(
            f"This game source has no playbook named “{team}”. "
            f"Choose one of: {', '.join(self.playbook_teams())}."
        )

    def load_playbook_pack(self, path: Path | str) -> playbook_pack.PlaybookPack:
        """Read and schema-check a ``.2k5book`` (no game data needed)."""

        return playbook_pack.load_pack(Path(path))

    def preview_playbook_pack(
        self,
        pack: playbook_pack.PlaybookPack | Path | str,
        team: str | None = None,
        progress: ProgressSink = _quiet_progress,
    ) -> playbook_pack.PackPreview:
        """The plan table, budget totals and full offline check for one target book."""

        if not isinstance(pack, playbook_pack.PlaybookPack):
            pack = self.load_playbook_pack(pack)
        target = team or pack.book.team
        progress(f"Reading {target}'s playbook", 0, 2)
        asset_id, book, body = self._playbook_book_for_team(target)
        staged_f, staged_p = self.staged_replace_targets(asset_id)
        progress("Planning the install", 1, 2)
        preview = playbook_pack.preview_pack(
            pack, target, book, body,
            resource=self._playbook_raw_resource(asset_id),
            staged_formation_targets=staged_f,
            staged_play_targets=staged_p,
        )
        progress("Plan ready", 2, 2)
        return preview

    def _playbook_raw_resource(self, asset_id: str) -> bytes:
        from nfl_outer import read_entry_range

        with self._lock:
            inspector = self._require_playbook_inspector()
            record = inspector.index.get(asset_id)
            entry = inspector.index.archive.entries[record.outer_index]
            return read_entry_range(
                inspector.index.archive, entry, record.chunk_offset, record.raw_size
            )

    def install_playbook_pack(
        self,
        pack: playbook_pack.PlaybookPack | Path | str,
        teams: Sequence[str] | None = None,
        progress: ProgressSink = _quiet_progress,
    ) -> object:
        """Stage one pack's rows as ordinary project edits, per target team.

        Nothing new is persisted: the rows are the same ``formation_creates`` /
        ``play_creates`` / ``formation_links`` the designers already stage, so
        they appear in the edit list, revert one by one, and serialise into
        ``.2k5mod`` with no schema change."""

        if not isinstance(pack, playbook_pack.PlaybookPack):
            pack = self.load_playbook_pack(pack)
        targets = tuple(teams) if teams else (pack.book.team,)
        staged_rows = 0
        installed: list[str] = []
        total = len(targets)
        for done, team in enumerate(targets):
            progress(f"Installing “{pack.book.name}” into {team}", done, total)
            asset_id, book, body = self._playbook_book_for_team(team)
            staged_f, staged_p = self.staged_replace_targets(asset_id)
            preview = playbook_pack.preview_pack(
                pack, team, book, body,
                staged_formation_targets=staged_f, staged_play_targets=staged_p,
            )
            blocked = [row for row in preview.plan.rows if row.status not in ("ok", "retargeted")]
            if blocked or preview.plan.blocked:
                first = blocked[0] if blocked else None
                reason = first.detail if first is not None else preview.plan.blocked[0]
                raise ValidationError(
                    f"{team}: “{first.name}” cannot be installed — {reason}"
                    if first is not None else f"{team}: {reason}"
                )
            if not preview.check.ok:
                raise ValidationError(f"{team}: {preview.check.errors[0]}")
            staged_rows += self._stage_pack(preview.pack, asset_id, book)
            installed.append(team)
        progress("Playbook pack staged", total, total)
        return StudioOperationResult(
            f"Staged “{pack.book.name}” into {', '.join(installed)} "
            f"({staged_rows} edit(s)). Revert them like any other edit."
        )

    def _stage_pack(
        self, pack: playbook_pack.PlaybookPack, asset_id: str, book: Nfl2k5Playbook
    ) -> int:
        staged = 0
        formation_selectors: dict[str, str] = {}
        play_selectors: dict[str, str] = {}
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            session.attach_playbook_inspector(inspector)
            for entry in pack.formations:
                request = formation_request_from_mapping(entry.request_mapping(asset_id))
                formation_selectors[entry.id] = request.selector
                staged += 1 if session.create_formation(request) else 0
            for entry in pack.plays:
                request = play_request_from_mapping(entry.request_mapping(asset_id))
                play_selectors[entry.id] = request.selector
                staged += 1 if session.create_play(request) else 0
            for entry in pack.plays:
                if entry.link_formation is None:
                    continue
                if isinstance(entry.link_formation, str):
                    target = pack.formations_by_id[entry.link_formation]
                    formation_index = (
                        target.replace_index if target.replace_index is not None
                        else session.staged_formation_index(
                            formation_selectors[target.id], len(book.formations)
                        )
                    )
                else:
                    formation_index = int(entry.link_formation)
                play_index = (
                    entry.replace_index if entry.replace_index is not None
                    else session.staged_play_index(play_selectors[entry.id], len(book.plays))
                )
                link = FormationLinkRequest(asset_id, formation_index, play_index, entry.link_group)
                staged += 1 if session.create_formation_link(link) else 0
        return staged

    def export_playbook_pack(
        self,
        asset_id: str,
        destination: Path,
        *,
        name: str = "",
        author: str = "",
        version: str = "1.0.0",
        license: str = "CC0-1.0",
        notes: str = "",
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Write this project's staged rows for one book out as a ``.2k5book``."""

        progress("Reading the staged playbook edits", 0, 3)
        with self._lock:
            inspector = self._require_playbook_inspector()
            session = self._require_session()
            book = inspector.load(asset_id)
            formation_rows = [r.provider_edit() for r in session.formation_creates
                              if r.asset_id == asset_id]
            play_rows = [r.provider_edit() for r in session.play_creates if r.asset_id == asset_id]
            link_rows = [r.provider_edit() for r in session.formation_links if r.asset_id == asset_id]
        if not formation_rows and not play_rows:
            raise ValidationError(
                "This project stages no designed formations or plays for that book, so there "
                "is nothing to share. Use Design Formation… / Design Play… or Create a Play first."
            )
        body = self.playbook_raw_body(asset_id)
        progress("Building the pack", 1, 3)
        pack = playbook_pack.pack_from_staged_rows(
            team=book.book_name, book=book, body=body,
            formation_rows=formation_rows, play_rows=play_rows, link_rows=link_rows,
            name=name or f"{book.book_name} playbook pack", author=author or "unknown",
            version=version, license=license, notes=notes,
        )
        progress("Checking the pack", 2, 3)
        report = playbook_pack.check_pack(
            pack, resource=self._playbook_raw_resource(asset_id), asset_id=asset_id
        )
        if not report.ok:
            raise ValidationError(
                "The staged edits do not pass the pack check, so they were not exported:\n\n"
                + "\n".join(report.errors[:5])
            )
        path = playbook_pack.save_pack(pack, Path(destination))
        progress("Playbook pack written", 3, 3)
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

    def export_stadium_scene_gltf(
        self, scene_id: str, destination: Path, progress: ProgressSink
    ) -> tuple[Path, Path]:
        """Save the selected stadium model as glTF, with its buffer beside it.

        The viewport could already draw a stadium; this is what lets a modder
        take it into Blender. Returns the ``(gltf, bin)`` pair, which the caller
        needs because the buffer keeps its own name.
        """

        progress("Exporting stadium model", 0, 1)
        with self._lock:
            self._require_session()
            paths = self._require_stadium_studio().export_scene_gltf(
                scene_id, destination
            )
        progress("Stadium model exported", 1, 1)
        return paths

    def import_stadium_scene_gltf(
        self, scene_id: str, source: Path, progress: ProgressSink
    ) -> object:
        """Stage same-topology vertex moves from an edited Stadium glTF."""

        progress("Validating edited stadium model", 0, 1)
        with self._lock:
            self._require_session()
            result = self._require_stadium_studio().import_scene_gltf(
                scene_id, source
            )
        progress("Edited stadium model staged", 1, 1)
        return result

    def replace_stadium_textures_from_gltf(
        self, scene_id: str, source: Path, progress: ProgressSink
    ) -> tuple[StadiumGltfTextureWriteBack, ...]:
        """Write Blender-edited glTF images back to their stadium texture slots.

        Export embeds every game texture into the glTF under its canonical
        ``nfl2k5_texture_id``; a modder edits those images in Blender, and this
        routes the edited bytes back through the same bounded replace route the
        Stadiums page uses. Returns one receipt per written texture slot.
        """

        progress("Applying edited stadium textures", 0, 1)
        with self._lock:
            self._require_session()
            results = self._require_stadium_studio().replace_textures_from_gltf(
                scene_id, source
            )
        progress("Edited stadium textures applied", 1, 1)
        return results

    def uniform_colors(
        self, selector: str, progress: ProgressSink
    ) -> tuple[str, str, bool]:
        """Read one set's current facemask/faceshield and turtleneck pair."""
        progress(f"Reading {selector} uniform colours", 0, 1)
        with self._lock:
            chosen = self._require_session().uniform_colors(selector)
        progress(f"{selector} uniform colours ready", 1, 1)
        return chosen

    def set_uniform_colors(
        self, selector: str, facemask: str, turtleneck: str,
        progress: ProgressSink,
    ) -> tuple[str, str, bool]:
        """Stage one set's facemask/faceshield and HI_turtleneck tints.

        This is a project edit like any other: nothing touches the source, and
        the colours only reach a disc when Build Modded XISO runs.
        """
        progress(f"Setting {selector} uniform colours", 0, 1)
        with self._lock:
            session = self._require_session()
            chosen = session.set_uniform_colors(
                selector, facemask, turtleneck
            )
        progress(f"{selector} uniform colours set", 1, 1)
        return chosen

    def clear_uniform_colors(
        self, selector: str, progress: ProgressSink
    ) -> bool:
        """Revert one selected set and leave every other set unchanged."""
        progress(f"Reverting {selector} uniform colours", 0, 1)
        with self._lock:
            had = self._require_session().clear_uniform_colors(selector)
        progress(f"{selector} uniform colours reverted", 1, 1)
        return had

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

    def save_texture_authoring_master(
        self,
        asset: UniformAsset,
        *,
        source_image: Path,
        source_sha256: str,
        destination: Path,
        transform: AuthoringTransform,
        editor_transform: Mapping[str, object],
        high_resolution_scale: int,
        native_baseline_png: Path | None = None,
        progress: ProgressSink = _quiet_progress,
    ) -> Path:
        """Save one imported full-res source beside its staged native PNG."""

        progress(f"Validating {asset.label} authoring master", 0, 2)
        with self._lock:
            native = self._require_session().current_path(asset)
            output = save_texture_master_bundle(
                source_image=source_image,
                destination=destination,
                asset_id=asset.asset_id,
                editor_target="nfl2k5_xbox",
                native_width=asset.width,
                native_height=asset.height,
                transform=transform,
                high_resolution_scale=high_resolution_scale,
                compiled_native_png=native,
                compiled_native_baseline_png=native_baseline_png,
                expected_source_sha256=source_sha256,
                editor_transform=editor_transform,
            )
        progress(f"Saved {asset.label} authoring master", 2, 2)
        return output

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
        candidate = self.session_factory(cache, self.uniform_catalog)
        self._attach_visual_catalog(candidate)
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
        attach_playbooks = getattr(candidate, "attach_playbook_inspector", None)
        if callable(attach_playbooks):
            with self._lock:
                attach_playbooks(self._require_playbook_inspector())
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
        command = self.xemu_command
        with self._lock:
            result = self._last_build
        if not command:
            raise ValidationError(
                "xemu is not configured. Install xemu or its app.xemu.xemu "
                "Flatpak, or choose the xemu program with Configure xemu."
            )
        if result is None or not result.output_xiso.is_file() \
                or result.output_xiso.is_symlink():
            raise ValidationError("Build a modded XISO before launching xemu.")
        progress("Starting xemu", 0, 1)
        argv = _xemu_launch_argv(command, result.output_xiso)
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
            geometry_catalog=_STADIUM_GEOMETRY_CATALOG,
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
            geometry_catalog=_STADIUM_GEOMETRY_CATALOG,
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
