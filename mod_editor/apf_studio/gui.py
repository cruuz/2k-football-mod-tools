"""Polished PyQt5 product shell for APF 2K8 Mod Studio.

The module is intentionally a view/controller layer.  It contains no game
assets and does not touch a user's source directly; every operation crosses the
``ApfStudioFacade`` boundary.  Importing this module never creates a
``QApplication`` or opens a window, which also keeps automated checks headless.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import html
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import traceback
from typing import Any, Callable, Iterable, Mapping, Sequence
from uuid import uuid4
import wave

from PyQt5.QtCore import (
    QObject,
    QProcess,
    QRunnable,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import audio_conform, platform_compat
from mod_editor.core import update_check
from mod_editor.core.texture_master import (
    AuthoringTransform,
    fit_transform as texture_master_fit_transform,
    snapshot_texture_master_source,
)
from mod_editor.gui import branding
from mod_editor.gui import crash_report
from mod_editor.gui import update_ui
from mod_editor.gui.apf_audio_waveform_qt import (
    AudioWaveformPreview,
    WaveformCancelled,
    WaveformEnvelope,
    WaveformError,
    WaveformRequest,
    read_pcm16_waveform,
)
from mod_editor.gui.stadium_viewer import GltfWireframeModel, StadiumViewport

from . import __version__
_TOOLS_DIR = str(Path(__file__).resolve().parents[2] / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
import apf_crest_box_patch  # noqa: E402
import apf_custom_team_appearance_patch  # noqa: E402
from apf_team_crests import TEAM_CRESTS, crest_slots, default_crest  # noqa: E402

from .audio_encoding import ExternalXma1Encoder
from .build import (
    compile_full_shell_crest_entries,
    publish_compiled_outer_entries,
)
from .custom_team_appearance_qt import CustomTeamAppearancePanel
from .uniform_equipment_colors_qt import UniformEquipmentColorsPanel
from .uniform_independence_panel import UniformIndependencePanel
from .textlogo_authoring import (
    WORDMARK_HEIGHT,
    WORDMARK_WIDTH,
    prepare_wordmark_png,
)
from .facade import (
    ApfStudioFacade,
    ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE,
    TEAM_DISPLAY_NAME_EDIT_SCOPE_MESSAGE,
)
from .field_art import (
    ENDZONE_IDENTITY_NOTE,
    ENDZONE_MASK_CONTRACT,
    FieldArtInventory,
    FieldArtInventoryError,
    FieldArtKind,
    build_field_art_inventory,
    endzone_team_labels,
    export_endzone_contact_sheets,
)
from .inspectors import ApfInspectorService, ExportIdentity, InspectorRow, PagedModel
from .helmet_crest_design import (
    FULL_SHELL_CREST_PROFILE,
    GLOBAL_HELMET_WARNING,
    HELMET_CREST_DESIGN_EDIT_ID,
    RETAIL_CREST_PROFILE,
)
from .helmet_logo_placement import (
    HelmetLogoPlacementError,
    Placement,
    compose_contained_master_transform,
    import_mask_nearest,
)
from .helmet_logo_placement_qt import place_helmet_logo
from .helmet_logo_regions import (
    NORMAL_LOGO_IMPORT_MODE,
    REGION_MASK_IMPORT_MODE,
    HelmetLogoRegionError,
    validate_region_mask_rgba,
)
from .helmet_logo_regions_qt import convert_normal_logo
from .models import (
    APF_CATEGORY_ORDER,
    ApfAsset,
    ApfCategory,
    ApfStatus,
    AssetActionBinding,
    CapabilityCard,
    DIGITAL_FONT_EDIT_ID,
    UniformAsset,
    asset_action_binding,
)
from .number_targets import action_binding as number_action_binding
from .model_export_qt import PlayerEquipmentModelExportPanel
from .project import (
    ProjectError,
    ProjectTargetIdentity,
    RecoveryCandidate,
    WorkspaceStateStore,
    project_target_identity,
)
from .product_findings import gameplay_snapshot, presentation_snapshot
from .roster_workspace_qt import RosterReservePlanner
from .save_playbooks_qt import SavePlaybookAssignmentsPanel
from .playbook_route_qt import PlayAssignmentRoutePanel
from .playbook_membership_qt import ApfPlaybookMembershipPanel
from .save_roster_players_qt import SaveRosterPlayersPanel
from .scene_textures import SceneTexture, shared_texture_ids
from .stadium import ApfStadiumPreview, ApfStadiumScene
from .stadium_material_findings import load_stadium_material_findings
from . import stadium_model_import
from . import stadium_texture
from .workspace_routes import (
    DIGITAL_FONT_NAME,
    DIGITAL_FONT_TAB,
    TEAM_LOGO_TAB,
    UNIFORM_MATERIALS_TAB,
    WORDMARK_TAB,
    WorkspaceHandoff,
    WorkspaceRoute,
    route_for_asset,
)


PRODUCT_NAME = "APF 2K8 Mod Studio"
PROJECT_EXTENSION = ".apf2k8mod"
PAGE_SIZE = 100
# Minimum height reserved for a scrolled workspace page.  Pages are wrapped in a
# resizable QScrollArea so the shell's own minimum height stays independent of
# each page's full content height; a tall page scrolls inside this viewport
# instead of forcing the whole window past a 1080p display.
WORKSPACE_PAGE_MIN_HEIGHT = 400


def _window_icon() -> QIcon | None:
    """Return the bundled application icon, or None if it is unavailable."""
    return branding.app_icon("apf2k8-mod-studio")

AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT = (
    "fully_validated_read_only_preview_then_explicit_apply"
)
AUDIO_DIRECT_DROP_CONTRACT = "selected_exact_slot_xma1_or_conformed_audio"
AUDIO_ANNOTATION_UI_CONTRACT = "project_metadata_only_stable_logical_cue_id"
AUDIO_ANNOTATION_MAX_TITLE_CHARS = 120
AUDIO_ANNOTATION_MAX_NOTE_CHARS = 2_000


CATEGORY_BLURBS: dict[ApfCategory, str] = {
    ApfCategory.GETTING_STARTED: "Load your own game, make familiar PNG edits, then build a separate playable copy.",
    ApfCategory.UNIFORMS: "Edit all 96 mapped material-color textures and browse or export every one of the 408 indexed uniform and equipment records.",
    ApfCategory.ROSTERS: "Browse the on-disc roster or open Save Players for a raw Roster.ROS / verified STFS handoff. The save editor exposes 149 exact packed fields per player, all 15 fixed-allocation identity text fields, and count-preserving populated roster-slot swaps. Overall and capacity expansion remain locked because their complete engine contracts are not proved.",
    ApfCategory.TEAM_IDENTITY: "Browse team-facing resources; more identity editing unlocks here as each field is proven safe.",
    ApfCategory.LOGOS: "Replace the shared 512×512 team-logo crest and the 128×128 draft logo, and browse every indexed logo and team-art record.",
    ApfCategory.SCOREBUG: "See the field scorebug\u2019s own artwork \u2014 every graphic embedded in its seven scene parts plus the shared score-digit mask \u2014 and preview or export any of it. Only digital_font has a proved writer; geometry, layout, and timing are read-only.",
    ApfCategory.FIELD_ART: "Browse 235 stock endzone layers (118 endzone_l0 + 117 endzone_l1) plus practice/divot inventory. Every package is one team's own artwork — outer 6 is not a shared layer. Format-18 DXT1 endzones, package-659 weave/dirtmaps, and the original six bases are writable. Format-59 DXT5A endzones stay browse-only. Format-18 endzones are red/green/blue region masks, not paintable art.",
    ApfCategory.STADIUMS: "Explore stadium geometry in 3D, edit any of the 78 statically owned embedded textures, and round-trip same-topology POSITION edits for 77 catalog-authorized surfaces into a separately verified copied 1A.",
    ApfCategory.MENUS: "Search menu, layout, font, and localized text structures across the complete archive.",
    ApfCategory.AUDIO: "Browse soundtrack, commentary, stadium, presentation, and standalone XMA1 audio; play verified WAV previews, export original XMA, import ordinary audio through exact-slot conversion with your own XMA1 encoder, or batch-stage a retail-free XMA1 or PCM16 WAV folder or ZIP.",
    ApfCategory.GAMEPLAY: "Inspect mapped sliders and follow gameplay research; nothing is offered as an edit until it is proven safe.",
    ApfCategory.PLAYBOOKS: "Inspect mapped PLAY and DRCT structures, copy or safely swap exact stock player-assignment routes in MASTER PLAY, or reassign the 69 existing offensive/defensive books across all 40 team slots in a raw roster save. Freehand route nodes and DRCT remain read-only.",
    ApfCategory.FRANCHISE: "Browse season, schedule, save, and franchise structures while deeper franchise editing is researched.",
    ApfCategory.ALL_ASSETS: "Every record the live indexer sees appears here, including opaque and export-only resources.",
}


def _human_bytes(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024.0 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{value} B"


def _duration_text(value: object) -> str:
    try:
        seconds = max(0.0, float(value))
    except (TypeError, ValueError):
        return "—"
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}:{remainder:02d}"


def _literal_tooltip(value: str) -> str:
    """Render untrusted game or project text literally in a Qt tooltip."""

    escaped = html.escape(value, quote=True).replace("\n", "<br/>")
    return f"<qt>{escaped}</qt>"


def _audio_player_command(
    path: Path,
    resolver: Callable[[str], str | None] = shutil.which,
) -> tuple[str, tuple[str, ...]]:
    """Choose a quiet, non-shell Linux player for a private PCM preview."""

    candidates = (
        ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "error", str(path))),
        ("paplay", (str(path),)),
        ("aplay", ("-q", str(path))),
    )
    for executable, arguments in candidates:
        resolved = resolver(executable)
        if resolved:
            return resolved, arguments
    raise RuntimeError(
        "No local audio player was found. Install ffplay, paplay, or aplay to use Play; export still works."
    )


def _status_color(status: ApfStatus) -> str:
    return {
        ApfStatus.EDITABLE: "#39d98a",
        ApfStatus.PREVIEW: "#73a8ff",
        ApfStatus.EXPORT_ONLY: "#f2bd5a",
        ApfStatus.COMING_SOON: "#8795aa",
        ApfStatus.EVIDENCE: "#9aa8bd",
        ApfStatus.RESEARCH: "#8795aa",
    }[status]


def _status_text(status: ApfStatus) -> str:
    """Pair every capability color with a readable, non-color-only cue."""

    return {
        ApfStatus.EDITABLE: "✓ Editable",
        ApfStatus.PREVIEW: "◉ Preview",
        ApfStatus.EXPORT_ONLY: "↓ Export only",
        ApfStatus.COMING_SOON: "◷ Coming soon",
        ApfStatus.EVIDENCE: "◇ Proof boundary",
        ApfStatus.RESEARCH: "⌕ Research boundary",
    }[status]


def _capability_next_step(status: ApfStatus) -> str:
    """A plain next step so capability cards never end at a boundary."""

    return {
        ApfStatus.EDITABLE: (
            "Next: pick an item in this category, then use Replace — or drop "
            "your image right onto its preview. Any size or format works."
        ),
        ApfStatus.PREVIEW: (
            "Next: pick a row to preview it. Editing unlocks once a proved "
            "writer exists for that exact resource."
        ),
        ApfStatus.EXPORT_ONLY: (
            "Next: pick a row to export it. Editing unlocks once a proved "
            "writer exists for that exact resource."
        ),
        ApfStatus.COMING_SOON: (
            "Next: choose your game on the Getting Started page to unlock "
            "this category."
        ),
        ApfStatus.EVIDENCE: (
            "Next: review the linked findings; editable rows are listed "
            "separately in this category."
        ),
        ApfStatus.RESEARCH: (
            "Next: review the linked findings; editable rows are listed "
            "separately in this category."
        ),
    }[status]


def _spec_pill(text: str, *, emphasis: bool = False, tooltip: str = "") -> QLabel:
    """One compact fact chip so the input contract is scannable at a glance.

    The focused editor panels (digital font, team logo, field art) surface the
    exact required PNG size and format as pills above their prose, so a modder
    can read the contract before choosing a file.  ``emphasis`` marks the one
    non-negotiable fact (the exact dimensions) in the accent color.
    """

    pill = QLabel(text)
    pill.setObjectName("specPill")
    if emphasis:
        pill.setProperty("emphasis", True)
    if tooltip:
        pill.setToolTip(tooltip)
    return pill


def _asset_product_action(asset: ApfAsset) -> AssetActionBinding | None:
    action = asset_action_binding(
        asset.asset_id,
        asset.outer_index,
        asset.inner_index,
        asset.name,
        asset.type_name,
    )
    if action is not None:
        return action
    return number_action_binding(
        asset.asset_id,
        asset.outer_index,
        asset.inner_index,
        asset.name,
        asset.type_name,
    )


def _edit_id_for_asset(asset: ApfAsset) -> str:
    action = _asset_product_action(asset)
    return action.edit_id if action is not None else asset.asset_id


def _is_editable_png_asset(asset: ApfAsset) -> bool:
    return _asset_product_action(asset) is not None


def _workspace_route_for(
    facade: ApfStudioFacade, asset: ApfAsset
) -> WorkspaceRoute | None:
    """The dedicated workspace that owns a proved writer for this exact row.

    The universal browser can only replace the two exact-size PNG slots bound
    in :data:`ASSET_ACTION_BINDINGS`, but hundreds of the rows it lists -- every
    helmet crest layer, all 96 uniform materials, all 206 wordmarks, the six
    field-art base textures -- are written every day by a focused editor
    elsewhere in the app.  Resolving that here lets the browser hand a row over
    instead of refusing it.  Every lookup uses tables the catalog already built,
    so this costs nothing per selection and never reads the archive again.
    """

    uniform_assets: tuple[UniformAsset, ...] = ()
    if getattr(facade, "source_ready", False):
        try:
            uniform_assets = facade.uniform_assets()
        except Exception:  # noqa: BLE001 - a hand-off hint must never break selection
            uniform_assets = ()
    return route_for_asset(
        asset,
        uniform_assets=uniform_assets,
        field_art_targets={
            target.key: target.name for target in FIELD_ART_COVERED_TARGETS
        },
        stadium_texture_location=(
            stadium_texture.OUTER_INDEX,
            stadium_texture.INNER_INDEX,
        ),
    )


def _asset_status_text(asset: ApfAsset) -> str:
    if asset.status is ApfStatus.EDITABLE:
        return f"✓ {asset.export_label}"
    if asset.status is ApfStatus.PREVIEW:
        return f"◉ Preview • {asset.export_label}"
    if asset.status is ApfStatus.EXPORT_ONLY:
        return f"↓ {asset.export_label}"
    return _status_text(asset.status)


def _copy_new(source: Path, destination: Path) -> Path:
    """Copy one user replacement to a new path without overwriting anything."""

    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        0o644,
    )
    try:
        with source.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                view = memoryview(block)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short write")
                    view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        destination.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    return destination


def _link_reference(source: Path, destination: Path) -> None:
    """Reference one read-only pack beside a staged volume.

    An APF index only parses under its own pack name and beside every sibling
    pack it declares, so chaining two writers over one volume needs those packs
    visible next to the intermediate copy. Symlinks are tried first because
    they work across filesystems; a hard link is the fallback for platforms
    that restrict symlink creation. If both link types are unavailable (for
    example, a Windows user chose an output drive different from the game
    drive), copy the read-only pack as a final fallback. That costs disk space
    and time but needs no administrator privilege and preserves the same
    parser contract.
    """

    failures: list[str] = []
    for linker in (os.symlink, os.link):
        try:
            linker(source, destination)
            return
        except (OSError, NotImplementedError, AttributeError) as exc:
            failures.append(f"{getattr(linker, '__name__', 'link')}: {exc}")
    try:
        if not source.is_file() or source.is_symlink():
            raise OSError("source pack is not a regular non-symlink file")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        shutil.copyfile(source, destination)
        if destination.stat().st_size != source.stat().st_size:
            destination.unlink(missing_ok=True)
            raise OSError("copied sibling pack has the wrong size")
        return
    except OSError as exc:
        failures.append(f"copy: {exc}")
    raise RuntimeError(
        f"Could not stage the sibling pack {source.name} beside the staged "
        f"volume ({'; '.join(failures)}). Choose a writable output folder and "
        "try again."
    )


def _declared_sibling_packs(index_path: Path) -> tuple[str, ...]:
    """The pack names an APF 0A volume declares, other than the index itself.

    Shared by :class:`ApfTeamLogoPanel` and the facade's copied-volume build so
    the intermediate the cache writer re-parses is staged beside every sibling
    pack the index declares.  Read-only: the user's game is never opened for
    writing.
    """

    root = Path(__file__).resolve().parents[2]
    for candidate in (str(root), str(root / "tools")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    import apf_outer  # noqa: E402 - tools/ placed on sys.path above

    archive = apf_outer.parse_archive(index_path)
    return tuple(
        pack.name for pack in archive.packs if pack.name != index_path.name
    )


def _write_json_new(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _build_full_shell_team_logo_volume(
    index_path: Path,
    staged_png: Path,
    out_volume: Path,
    package_manifest: Path,
    cache_manifest: Path,
    cache_verify_manifest: Path,
    crest_wrap_manifest: Path,
    progress: Callable[[str, int, int], None],
    *,
    cache_catalog_index: int,
    outer_entry_index: int,
    siblings: tuple[str, ...],
    appearance_replacements: Mapping[
        int, apf_custom_team_appearance_patch.CustomTeamAppearance
    ] | None,
    appearance_manifest: Path | None,
) -> dict[str, object]:
    """Compile everything first, then atomically publish one complete new 0A."""

    compilation = compile_full_shell_crest_entries(
        index_path,
        staged_png,
        selected_asset_index=cache_catalog_index,
        selected_outer_index=outer_entry_index,
        progress=progress,
    )
    created_receipts: list[Path] = []
    appearance_verification: dict[str, object] | None = None
    stage_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{out_volume.name}.full-shell-", dir=str(out_volume.parent)
        )
    )
    staged_volume = stage_directory / out_volume.name
    staged_sibling_links: list[Path] = []
    final_published = False
    try:
        staged_publication = publish_compiled_outer_entries(
            index_path, staged_volume, compilation.entries, progress=progress
        )
        if appearance_replacements:
            # The staged 0A still declares its retail sibling packs. Make those
            # read-only packs visible beside the private copy for the bounded
            # appearance parser; reference them without copying or modifying
            # the user's game files.
            for pack in siblings:
                destination = stage_directory / pack
                _link_reference(index_path.parent / pack, destination)
                staged_sibling_links.append(destination)
            progress("Writing HOME/AWAY appearance into the private stage", 0, 1)
            appearance_receipt = (
                apf_custom_team_appearance_patch.patch_private_staged_volume(
                    staged_volume, appearance_replacements
                )
            )
            appearance_verification = (
                apf_custom_team_appearance_patch.verify_output_appearances(
                    index_path, staged_volume, appearance_replacements
                )
            )
            assert appearance_manifest is not None
            _write_json_new(appearance_manifest, {
                "schema": "apf2k8_team_logo_and_custom_appearance_build/v2",
                "appearance_stage": appearance_receipt,
                "final_appearance_verification": appearance_verification,
                "selected_crest_asset_index": cache_catalog_index,
                "appearance_slots": sorted(appearance_replacements),
                "all_home_away_crest_selectors_match_selected_asset": True,
                "source_opened_read_only": True,
                "output_created_new": True,
            })
            created_receipts.append(appearance_manifest)

        publication = dict(staged_publication)
        publication.update({
            "private_stage_completed_before_final_name": True,
            "final_publish_atomic_no_replace": True,
        })
        _write_json_new(package_manifest, {
            "schema": "apf2k8_full_shell_all_package_build/v1",
            "compilation": compilation.report,
            "publication": publication,
        })
        created_receipts.append(package_manifest)
        _write_json_new(cache_manifest, compilation.cache_manifest)
        created_receipts.append(cache_manifest)
        _write_json_new(
            cache_verify_manifest, compilation.cache_structure_verification
        )
        created_receipts.append(cache_verify_manifest)
        crest_document = json.loads(json.dumps(compilation.carrier_manifest))
        crest_document["product_integration"] = {
            "coverage_profile": FULL_SHELL_CREST_PROFILE,
            "creates_xenia_patch": False,
            "edits_default_xex": False,
            "selected_package_l0_l1_identical_atlas": True,
            "selected_cache_l0_l1_semantic_not_atlas": True,
            "all_118_packages_migrated_before_publication": True,
            "verification": compilation.carrier_verification,
        }
        _write_json_new(crest_wrap_manifest, crest_document)
        created_receipts.append(crest_wrap_manifest)

        progress("Publishing the complete full-shell 0A", 0, 1)
        final_publication = platform_compat.publish_no_replace(
            staged_volume,
            out_volume,
            is_directory=False,
            require_atomic=True,
        )
        if not final_publication.atomic_no_clobber:
            raise RuntimeError("The platform did not provide atomic no-replace publish")
        final_published = True
        progress("Publishing the complete full-shell 0A", 1, 1)
    except BaseException:
        for path in reversed(created_receipts):
            path.unlink(missing_ok=True)
        # The final name never exists until the hidden same-filesystem stage is
        # complete. Never unlink the final path here: after a no-replace race it
        # may belong to somebody else.
        if not final_published:
            staged_volume.unlink(missing_ok=True)
        raise
    finally:
        for path in reversed(staged_sibling_links):
            path.unlink(missing_ok=True)
        try:
            stage_directory.rmdir()
        except OSError:
            # A failed cleanup can leave only this exact empty/private staging
            # directory; it must never turn a completed final 0A into failure.
            pass
    return {
        "volume": out_volume,
        "cache_manifest": cache_manifest,
        "cache_verify_manifest": cache_verify_manifest,
        "package_manifest": package_manifest,
        "crest_patch": None,
        "crest_coverage": 1.0,
        "appearance_manifest": appearance_manifest,
        "appearance_verification": appearance_verification,
        "crest_profile": FULL_SHELL_CREST_PROFILE,
        "crest_wrap_manifest": crest_wrap_manifest,
    }


def build_team_logo_copied_volume(
    index_path: Path,
    staged_png: Path,
    out_volume: Path,
    package_manifest: Path,
    cache_manifest: Path,
    progress: Callable[[str, int, int], None],
    *,
    cache_catalog_index: int,
    outer_entry_index: int | None = None,
    siblings: tuple[str, ...] | None = None,
    crest_coverage: float = 1.0,
    crest_patch: Path | None = None,
    appearance_replacements: Mapping[
        int, apf_custom_team_appearance_patch.CustomTeamAppearance
    ] | None = None,
    appearance_manifest: Path | None = None,
    crest_profile: str = RETAIL_CREST_PROFILE,
    crest_wrap_manifest: Path | None = None,
    detail_png: Path | None = None,
) -> dict[str, object]:
    """Build one complete package/cache crest result from a read-only source.

    A crest is six region masks: ``logo_l0`` carries regions 0-2 and
    ``logo_l1`` carries regions 3-5.  Supply ``detail_png`` to author both
    layers; with one image the detail layer's masks are cleared so the mark
    renders exactly once, which is what the panel has always told people it
    does and what the project build already did.  Retail
    side-decal builds use the bounded package/cache tools; full-shell builds
    compile every crest package plus the cache and shell route before a hidden
    same-filesystem stage is atomically published to the requested 0A name.
    Either profile fails closed, and the retail source is never opened for
    writing.

    This is the exact builder :class:`ApfTeamLogoPanel` dispatches and that
    ``tests/mod_editor/test_apf_team_logo_gui.py`` pins; the facade's
    ``build_team_logo`` reuses it so the GUI-panel route and the facade route
    can never diverge.  ``siblings`` is resolved when not supplied; the panel
    passes it explicitly so its declared-sibling resolver stays the seam its
    tests patch.
    """

    import subprocess

    tools = Path(__file__).resolve().parents[2] / "tools"

    def run(writer: Path, arguments: list[str], stage: str) -> None:
        progress(stage, 0, 0)
        completed = subprocess.run(
            [sys.executable, str(writer), *arguments],
            cwd=str(tools.parent),
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"The {writer.stem} writer failed."
            )

    cache_verify_manifest = cache_manifest.with_name(
        f"{cache_manifest.stem}.verify.json"
    )
    destinations = [
        out_volume,
        package_manifest,
        cache_manifest,
        cache_verify_manifest,
    ]
    if crest_patch is not None:
        destinations.append(crest_patch)
    if appearance_manifest is not None:
        destinations.append(appearance_manifest)
    if crest_wrap_manifest is not None:
        destinations.append(crest_wrap_manifest)
    for destination in destinations:
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(
                "The proved team-logo build never overwrites existing files; "
                f"choose a new location ({destination} already exists)."
            )

    if (crest_coverage > 1.0) != (crest_patch is not None):
        raise RuntimeError(
            "A non-retail crest coverage and its Xenia patch destination must "
            "be supplied together."
        )
    if crest_profile not in {RETAIL_CREST_PROFILE, FULL_SHELL_CREST_PROFILE}:
        raise RuntimeError("Unknown helmet crest coverage profile")
    if (crest_profile == FULL_SHELL_CREST_PROFILE) != (
        crest_wrap_manifest is not None
    ):
        raise RuntimeError(
            "The full-shell crest profile and its verifier receipt destination "
            "must be supplied together."
        )
    if bool(appearance_replacements) != (appearance_manifest is not None):
        raise RuntimeError(
            "Custom-team appearance replacements and their receipt destination "
            "must be supplied together."
        )
    if appearance_replacements:
        for slot, requested in sorted(appearance_replacements.items()):
            try:
                appearance = apf_custom_team_appearance_patch.validate_appearance(
                    requested
                )
            except apf_custom_team_appearance_patch.CustomTeamAppearanceError as exc:
                raise RuntimeError(
                    f"Custom-team appearance slot {slot} is invalid: {exc}"
                ) from exc
            if slot != appearance.slot:
                raise RuntimeError(
                    f"Custom-team appearance mapping key {slot} does not match "
                    f"payload slot {appearance.slot}"
                )
            for bank_name, bank in (("HOME", appearance.home), ("AWAY", appearance.away)):
                if bank.logo_selector[0] != cache_catalog_index:
                    raise RuntimeError(
                        f"Custom-team appearance slot {slot} {bank_name} selects "
                        f"crest asset {bank.logo_selector[0]}, but this Team Logo "
                        f"build selected asset {cache_catalog_index}"
                    )
    # Validate the tiny patch before copying a 1.1 GB volume.  The document is
    # rebuilt on the final write, but this catches a bad multiplier with zero
    # disk cost and before either offline writer starts.
    if crest_patch is not None:
        if crest_patch.exists() or crest_patch.is_symlink():
            raise RuntimeError(f"Crest patch destination already exists: {crest_patch}")
        apf_crest_box_patch.patch_document(crest_coverage)
    if siblings is None:
        siblings = _declared_sibling_packs(index_path)
    out_volume.parent.mkdir(parents=True, exist_ok=True)
    try:
        free_bytes = shutil.disk_usage(out_volume.parent).free
        # Retail chains two legacy copied-volume writers. Full-shell compiles
        # every bounded entry first and then creates exactly one delivered
        # copy, which also avoids wasting another 1.1 GB temporary allocation.
        copy_count = 1 if crest_profile == FULL_SHELL_CREST_PROFILE else 2
        required_bytes = (
            index_path.stat().st_size * copy_count + 256 * 1024 * 1024
        )
    except OSError as exc:
        raise RuntimeError(
            f"Could not check free space for the team-logo build: {exc}"
        ) from exc
    if free_bytes < required_bytes:
        raise RuntimeError(
            "Not enough free space for a safe team-logo build: "
            f"{required_bytes:,} bytes are required and {free_bytes:,} are free."
        )
    if crest_profile == FULL_SHELL_CREST_PROFILE:
        if outer_entry_index is None or crest_wrap_manifest is None:
            raise RuntimeError(
                "Full-shell builds require one source-resolved crest package"
            )
        return _build_full_shell_team_logo_volume(
            index_path,
            staged_png,
            out_volume,
            package_manifest,
            cache_manifest,
            cache_verify_manifest,
            crest_wrap_manifest,
            progress,
            cache_catalog_index=cache_catalog_index,
            outer_entry_index=outer_entry_index,
            siblings=siblings,
            appearance_replacements=appearance_replacements,
            appearance_manifest=appearance_manifest,
        )
    workspace = Path(
        tempfile.mkdtemp(
            prefix=".apf-team-logo-build-", dir=str(out_volume.parent)
        )
    )
    retained: Path | None = None
    appearance_receipt: dict[str, object] | None = None
    appearance_verification: dict[str, object] | None = None
    build_complete = False
    try:
        texture_png = staged_png
        # The cache writer re-parses its --index volume, and an APF index only
        # parses under its own pack name beside every sibling pack it declares.
        # Stage the intermediate that way and reference the siblings by link, so
        # no pack is copied and the retail source is still never opened for
        # writing.
        staged_volume = workspace / index_path.name
        for pack in siblings:
            _link_reference(index_path.parent / pack, workspace / pack)
        staged_manifest = workspace / "team_logo_package.json"
        # The two layers hold different regions of one crest and are not
        # interchangeable, so a single image goes to logo_l0 and clears the
        # detail layer rather than being copied into both.
        layer_arguments = (
            ["--png-l1", str(detail_png)]
            if detail_png is not None
            else ["--clear-l1"]
        )
        package_arguments = [
            "--index",
            str(index_path),
            "--png",
            str(texture_png),
            *layer_arguments,
            "--output-volume",
            str(staged_volume),
            "--manifest",
            str(staged_manifest),
        ]
        if outer_entry_index is not None:
            # Which team's crest this is.  Omitted, the writer keeps its own
            # historical default, so callers that never chose a team are
            # unaffected.
            package_arguments += ["--entry-index", str(outer_entry_index)]
        run(
            tools / "apf_logo_patch.py",
            package_arguments,
            "Copying volume and writing the crest package through the proved writer",
        )
        if appearance_replacements:
            progress(
                "Writing HOME/AWAY colors and helmet/crest selectors into the private stage",
                0,
                0,
            )
            appearance_receipt = (
                apf_custom_team_appearance_patch.patch_private_staged_volume(
                    staged_volume, appearance_replacements
                )
            )
        run(
            tools / "apf_logocache_patch.py",
            [
                "--index",
                str(staged_volume),
                "--catalog-index",
                str(cache_catalog_index),
                "--png",
                str(texture_png),
                *layer_arguments,
                "--output-volume",
                str(out_volume),
                "--manifest",
                str(cache_manifest),
            ],
            "Writing the same crest into the prebuilt logo cache",
        )
        # The verifier matches the changed entries exactly. Clearing a detail
        # layer that a crest never used rewrites nothing, so ask the cache
        # writer's own receipt which layers it actually touched rather than
        # asserting a second one always moved.
        detail_entry = f"{cache_catalog_index:02d}_logo_l1"
        detail_changed = True
        try:
            cache_layers = json.loads(
                cache_manifest.read_text(encoding="utf-8")
            ).get("layers")
        except (OSError, ValueError):
            cache_layers = None
        if isinstance(cache_layers, dict) and detail_entry in cache_layers:
            detail_changed = bool(cache_layers[detail_entry].get("changed", True))
        verify_arguments = [
            "--source",
            str(staged_volume),
            "--output",
            str(out_volume),
            "--catalog-index",
            str(cache_catalog_index),
            "--manifest",
            str(cache_verify_manifest),
        ]
        if detail_changed:
            verify_arguments.append("--expect-l1")
        run(
            tools / "apf_logocache_verify.py",
            verify_arguments,
            "Independently verifying the copied volume and regenerated crest mips",
        )
        if appearance_replacements:
            progress(
                "Independently reopening the final ROST appearance records",
                0,
                0,
            )
            appearance_verification = (
                apf_custom_team_appearance_patch.verify_output_appearances(
                    staged_volume,
                    out_volume,
                    appearance_replacements,
                )
            )
            assert appearance_manifest is not None
            try:
                package_document = json.loads(
                    staged_manifest.read_text(encoding="utf-8")
                )
                cache_document = json.loads(
                    cache_manifest.read_text(encoding="utf-8")
                )
                source_volume_sha256 = package_document["copied_volume"][
                    "source_volume_sha256_before"
                ]
                final_volume_sha256 = cache_document["copied_volume"][
                    "output_volume_sha256"
                ]
            except (OSError, KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "The unified appearance provenance receipts are incomplete"
                ) from exc
            if any(
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                for digest in (source_volume_sha256, final_volume_sha256)
            ):
                raise RuntimeError(
                    "The unified appearance provenance hashes are invalid"
                )
            document = {
                "schema": "apf2k8_team_logo_and_custom_appearance_build/v1",
                "provenance": {
                    "source_volume": str(index_path),
                    "source_volume_sha256": source_volume_sha256,
                    "source_opened_read_only": True,
                    "final_volume": str(out_volume),
                    "final_volume_sha256": final_volume_sha256,
                    "final_volume_created_new": True,
                },
                "appearance_stage": appearance_receipt,
                "final_appearance_verification": appearance_verification,
                "composition": {
                    "crest_package_then_roster_then_logo_cache": True,
                    "original_source_opened_read_only": True,
                    "private_intermediate_exclusively_owned": True,
                    "final_output_created_new": True,
                    "all_three_consumers_present_in_one_0A": True,
                },
            }
            appearance_manifest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with appearance_manifest.open("x", encoding="utf-8") as stream:
                    json.dump(document, stream, indent=2, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                appearance_manifest.unlink(missing_ok=True)
                raise
        try:
            retained = _copy_new(staged_manifest, package_manifest)
        except OSError:
            # The volume and its cache manifest are already written and
            # verified; only the package-stage evidence copy failed.
            retained = None
        if crest_patch is not None:
            progress("Writing the optional Xenia crest-coverage patch", 0, 0)
            apf_crest_box_patch.write_new_patch(crest_patch, crest_coverage)
        build_complete = True
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        if not build_complete and crest_wrap_manifest is not None:
            crest_wrap_manifest.unlink(missing_ok=True)
    return {
        "volume": out_volume,
        "cache_manifest": cache_manifest,
        "cache_verify_manifest": cache_verify_manifest,
        "package_manifest": retained,
        "crest_patch": crest_patch,
        "crest_coverage": crest_coverage,
        "appearance_manifest": appearance_manifest,
        "appearance_verification": appearance_verification,
        "crest_profile": crest_profile,
        "crest_wrap_manifest": crest_wrap_manifest,
    }


def build_field_art_copied_volume(
    index_path: Path,
    staged_png: Path,
    entry_index: int,
    file_index: int,
    out_volume: Path,
    manifest: Path,
    progress: Callable[[str, int, int], None],
    *,
    writer_path: Path | None = None,
    slot_name: str = "field-art texture",
) -> Path:
    """Run the offline-proved field-art writer over a copy of one 0A.

    ``tools/apf_field_art_patch.py`` copies the whole volume, rewrites only the
    selected base mip level, byte-preserves the descriptor pad, the packed mip
    tail, and every sibling inner part, and pairs the write with an independent
    verifier; the retail source is never opened for writing.

    This is the exact builder :class:`ApfFieldArtPanel` dispatches and that
    ``tests/mod_editor/test_apf_field_art_gui.py`` pins; the facade's
    ``build_field_art`` reuses it so the two routes can never diverge.
    """

    import subprocess

    if writer_path is None:
        writer_path = (
            Path(__file__).resolve().parents[2]
            / "tools"
            / "apf_field_art_patch.py"
        )
    progress(
        f"Copying volume and writing {slot_name} through the proved writer",
        0,
        0,
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(writer_path),
            "--index",
            str(index_path),
            "--png",
            str(staged_png),
            "--entry-index",
            str(entry_index),
            "--file-index",
            str(file_index),
            "--output-volume",
            str(out_volume),
            "--manifest",
            str(manifest),
        ],
        cwd=str(writer_path.parents[1]),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or "The field-art writer failed."
        )
    return manifest


class _TaskSignals(QObject):
    progress = pyqtSignal(str, int, int)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    finished = pyqtSignal()


class _BackgroundTask(QRunnable):
    """Small exception-safe QRunnable used for all archive and image work."""

    def __init__(self, operation: Callable[[Callable[[str, int, int], None]], Any]):
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()

    def run(self) -> None:  # pragma: no cover - exercised through Qt's pool
        try:
            result = self.operation(self.signals.progress.emit)
        except BaseException as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.signals.failed.emit(message, traceback.format_exc())
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


TaskRunner = Callable[
    [
        str,
        Callable[[Callable[[str, int, int], None]], Any],
        Callable[[Any], None] | None,
        bool,
    ],
    bool | None,
]
IdleRunner = Callable[[Callable[[], None]], None]

# Every image route in the editor accepts the same ordinary formats.  The fit
# layer (mod_editor.core.image_fit) converts whatever arrives to the slot's
# exact size and an 8-bit RGBA PNG, so the chooser and the drop target both
# advertise the full set instead of only PNG.
IMAGE_IMPORT_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga",
}
IMAGE_IMPORT_FILTER = (
    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)"
)

# First-run guidance: before a game is loaded the panels would otherwise be a
# wall of disabled buttons.  Every empty state names the one next step.
START_HERE_HINT = (
    "Start here: File → Open APF ISO… (or Getting Started → Choose ISO). "
    "Everything on this page unlocks once your game is recognized."
)


def _plain_image_formats() -> str:
    return "PNG, JPEG, BMP, GIF, WebP or TGA"


# Plain-language "what to do next" for the backend's exact-slot refusals.  The
# fail-closed behaviour itself never changes -- the writer still rejects the
# same bytes -- but the GUI pairs each refusal with the fix a first-time
# modder should try, instead of leaving them with jargon and a dead end.
_ERROR_FIX_HINTS: tuple[tuple[str, str], ...] = (
    (
        "Expected an exact",
        "Fix: this slot needs one exact pixel size, but you don't need another "
        "app to get there — use the panel's Replace button or drop the image on "
        "its preview, and Mod Studio resizes it for you.",
    ),
    (
        "Wordmark PNG alpha must be 255",
        "Fix: use Logos → Wordmarks → Import, which flattens transparent art "
        "onto black for you automatically.",
    ),
    (
        "PNG alpha must be 255",
        "Fix: this slot stores fully opaque pixels. Open the image and fill in "
        "its transparent areas, or export it without transparency, then try again.",
    ),
    (
        "must stay",
        "Fix: that image has the wrong dimensions for this slot. Import it "
        "through its panel and let Mod Studio resize it to the exact slot size.",
    ),
    (
        "RGB must be solid white",
        "Fix: the score-digit mask draws only in transparency. Use the panel's "
        "Replace button — it converts any image to solid-white-with-alpha for you.",
    ),
    (
        "blue must be 0",
        "Fix: this helmet mask stores only red/green region weights. Use the "
        "Team Logo panel's Normal-logo import, which converts ordinary artwork.",
    ),
    (
        "could not be read as an image",
        "Fix: choose or drop a "
        "PNG, JPEG, BMP, GIF, WebP or TGA image. Any size works.",
    ),
    (
        "require opaque artwork",
        "Fix: this stadium slot cannot store transparency. Flatten the image's "
        "transparent areas to a solid colour, then try again.",
    ),
    (
        "FFmpeg was not found",
        "Fix: install FFmpeg to convert ordinary audio (MP3, FLAC, OGG, M4A), or "
        "supply a PCM16 WAV that already matches the slot's exact shape.",
    ),
    (
        "administrator rights",
        "Fix: Mod Studio does not need Run as administrator. Choose an empty "
        "output folder you can write to, such as Documents or Desktop. If the "
        "game is on another drive, the build may copy read-only sibling packs "
        "instead of linking them; that is slower but still needs no elevation.",
    ),
    (
        "Access is denied",
        "Fix: do not choose Program Files, the game disc, or another protected "
        "folder for output. Choose a new empty folder under Documents/Desktop; "
        "the installer and editor are designed to run as a normal Windows user.",
    ),
    (
        "Permission denied",
        "Fix: choose a new empty output folder under Documents or Desktop. "
        "Never build into the original game folder; Mod Studio always creates a "
        "separate copy and does not require administrator mode.",
    ),
)


def friendly_fix_hint(message: str) -> str | None:
    """Return the plain next-step for a known refusal, or None."""

    lowered = message.casefold()
    for needle, hint in _ERROR_FIX_HINTS:
        if needle.casefold() in lowered:
            return hint
    return None


class ImageDropLabel(QLabel):
    """Scaled preview that also accepts one local image replacement.

    Any ordinary image format may be dropped -- the panels convert it to the
    slot's exact size.  Drops that cannot be used (several files at once,
    links, non-image files) are refused with a plain explanation instead of
    silently bouncing, so a first-time modder learns what to do next.
    """

    pngDropped = pyqtSignal(Path)

    def __init__(
        self,
        empty_text: str = (
            "Select a texture on the left to preview it here.\n"
            "Search tips: logo_l0, number_0_color, font_albedo, shoulder_color."
        ),
    ):
        super().__init__()
        self._source_pixmap: QPixmap | None = None
        self.setObjectName("imagePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(260, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setWordWrap(True)
        self.setAcceptDrops(True)

        # Transparent texture work is much easier to understand against a
        # checkerboard than a featureless black rectangle.  This tile is
        # generated at runtime and contains no game data.
        tile = QPixmap(24, 24)
        tile.fill(QColor("#0b121e"))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 12, 12, QColor("#21314a"))
        painter.fillRect(12, 12, 12, 12, QColor("#21314a"))
        painter.end()
        palette = self.palette()
        palette.setBrush(QPalette.Window, QBrush(tile))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.set_message(empty_text)

    def _set_state(self, state: str) -> None:
        self.setProperty("previewState", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._source_pixmap = None
            self.setPixmap(QPixmap())
            self.set_error("That PNG could not be previewed.")
            return
        self._source_pixmap = pixmap
        self.setText("")
        self._set_state("ready")
        self.setToolTip(
            f"PNG preview ready ({pixmap.width()}×{pixmap.height()}). "
            "Transparent areas use the checkerboard background."
        )
        self._fit()

    def set_message(self, text: str) -> None:
        self._source_pixmap = None
        self.setPixmap(QPixmap())
        self._set_state("empty")
        self.setText(f"▧  PREVIEW\n\n{text}")
        self.setToolTip(text)

    def set_loading(self, text: str) -> None:
        self._source_pixmap = None
        self.setPixmap(QPixmap())
        self._set_state("loading")
        self.setText(
            f"◌  PREPARING PREVIEW\n\n{text}\n\n"
            "The PNG and transparency checkerboard will appear here when ready."
        )
        self.setToolTip(text)

    def set_error(self, text: str) -> None:
        self._source_pixmap = None
        self.setPixmap(QPixmap())
        self._set_state("error")
        self.setText(f"!  PREVIEW UNAVAILABLE\n\n{text}")
        self.setToolTip(text)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit()

    def _fit(self) -> None:
        if self._source_pixmap is None:
            return
        target = self.size() - QSize(28, 28)
        if target.width() < 1 or target.height() < 1:
            return

        # Compose the ready preview ourselves instead of relying on QLabel's
        # palette behind a transparent pixmap.  Some Qt styles suppress that
        # palette once a pixmap is assigned, which used to make alpha-heavy
        # uniform textures look like an unexplained empty dark box.
        canvas = QPixmap(target)
        canvas.fill(QColor("#0b121e"))
        painter = QPainter(canvas)
        square = 18
        for y in range(0, target.height(), square):
            for x in range(0, target.width(), square):
                if (x // square + y // square) % 2 == 0:
                    painter.fillRect(x, y, square, square, QColor("#21314a"))

        image_bounds = QSize(
            max(1, target.width() - 18),
            max(1, target.height() - 46),
        )
        fitted = self._source_pixmap.scaled(
            image_bounds, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        image_x = (target.width() - fitted.width()) // 2
        image_y = max(6, (target.height() - fitted.height()) // 2 - 8)
        painter.drawPixmap(image_x, image_y, fitted)

        badge = (
            f"✓ PNG READY  •  {self._source_pixmap.width()}"
            f"×{self._source_pixmap.height()}"
        )
        metrics = painter.fontMetrics()
        badge_width = min(target.width() - 16, metrics.horizontalAdvance(badge) + 18)
        badge_height = metrics.height() + 10
        badge_x = 8
        badge_y = max(8, target.height() - badge_height - 8)
        painter.fillRect(
            badge_x, badge_y, badge_width, badge_height, QColor(16, 27, 43, 220)
        )
        painter.setPen(QColor("#d9f7eb"))
        painter.drawText(badge_x + 9, badge_y + badge_height - 7, badge)
        painter.end()
        self.setPixmap(canvas)

    def dragEnterEvent(self, event: object) -> None:
        mime = event.mimeData()  # type: ignore[attr-defined]
        if mime.hasUrls() and mime.urls():
            # Accept the drag so an unusable drop can explain itself with a
            # plain message instead of silently bouncing off the panel.
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def _refuse_drop(self, message: str) -> None:
        QMessageBox.information(self, "That drop can't be used yet", message)

    def dropEvent(self, event: object) -> None:
        urls = event.mimeData().urls()  # type: ignore[attr-defined]
        if len(urls) != 1:
            self._refuse_drop(
                "Drop one file at a time. Pick the single image you want to "
                "use and drop it on this panel again."
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        url = urls[0]
        if not url.isLocalFile() or url.host():
            self._refuse_drop(
                "That drop is a link or a web address, not a file on this "
                "computer. Save or download the image first, then drop the "
                "real file here."
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        path = Path(url.toLocalFile())
        if path.suffix.casefold() not in IMAGE_IMPORT_EXTENSIONS:
            self._refuse_drop(
                f"That file is not an image this panel can read. Drop a "
                f"{_plain_image_formats()} image — any size is fine, the "
                "editor resizes it for you."
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        self.pngDropped.emit(path)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class AudioReplacementDropZone(QFrame):
    """Accept one local XMA1 or convertible audio file for one exact slot."""

    audioDropped = pyqtSignal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("audioReplacementDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(58)
        self.setAccessibleName("Drop an audio replacement for the selected sound")
        self.setAccessibleDescription(
            "Accepts one pre-encoded RIFF XMA1 file, or ordinary audio such as "
            "WAV, MP3, FLAC, OGG or M4A when a user-supplied XMA1 encoder is configured."
        )
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(2)
        self.title = QLabel("Drop .xma or audio file here")
        self.title.setObjectName("audioDropTitle")
        self.hint = QLabel(
            "The selected slot's normal validation and Undo-safe writer still apply."
        )
        self.hint.setObjectName("mutedLabel")
        self.hint.setWordWrap(True)
        box.addWidget(self.title)
        box.addWidget(self.hint)
        self.set_available(False)

    @staticmethod
    def local_audio_path(mime: object) -> Path | None:
        """Return one admitted local authoring file, never a URL or file set."""

        try:
            urls = mime.urls() if mime.hasUrls() else []  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            return None
        if (
            len(urls) != 1
            or not urls[0].isLocalFile()
            or bool(urls[0].host())
        ):
            return None
        path = Path(urls[0].toLocalFile())
        try:
            regular = path.is_file() and not path.is_symlink()
        except OSError:
            regular = False
        # ``.xma`` stays the direct passthrough: an already-encoded XMA1 file is
        # written without re-encoding, which is the only lossless route on this
        # console and the right answer for anyone who already has XMA. Every
        # other accepted extension is converted to the slot's exact PCM shape
        # and then handed to the user's own XMA1 encoder, exactly as a
        # hand-shaped WAV always was.
        return (
            path
            if regular
            and (
                path.suffix.casefold() == ".xma"
                or audio_conform.is_supported_suffix(path)
            )
            else None
        )

    def set_available(self, available: bool, *, modified: bool = False) -> None:
        self.setEnabled(available)
        self.setProperty("dropReady", bool(available))
        self.style().unpolish(self)
        self.style().polish(self)
        if available:
            self.title.setText(
                "Drop another .xma or audio file here"
                if modified
                else "Drop .xma or audio file here"
            )
            self.hint.setText(
                "MP3, WAV, FLAC, OGG and M4A are converted to this sound's exact "
                "shape, then encoded by the XMA1 encoder you configured. "
                "An .xma goes straight in with no re-encoding at all."
            )
            self.setToolTip(
                "Drop one local audio file for the selected sound.\n\n"
                "Already have an .xma? That is the only lossless route: it is "
                "written unchanged.\n\n"
                "Anything else is resampled and fitted to the slot first, then "
                "handed to your own XMA1 encoder. The Xbox 360 stores this "
                "game's audio as XMA1 and no free XMA1 encoder exists, which is "
                "why that one step needs a tool you supply.\n\n"
                "Nothing is staged if any check fails."
            )
        else:
            self.title.setText("Select an Editable sound to drop audio")
            self.hint.setText(
                "Raw banks and index rows cannot accept one-sound replacements."
            )
            self.setToolTip(self.hint.text())

    def dragEnterEvent(self, event: object) -> None:
        mime = event.mimeData()  # type: ignore[attr-defined]
        if not self.isEnabled():
            event.ignore()  # type: ignore[attr-defined]
            return
        if mime.hasUrls() and mime.urls():
            # Accept the drag so an unusable drop can explain itself instead
            # of silently bouncing off the zone.
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:
        mime = event.mimeData()  # type: ignore[attr-defined]
        path = self.local_audio_path(mime) if self.isEnabled() else None
        if not self.isEnabled() or path is None:
            if self.isEnabled():
                try:
                    urls = mime.urls() if mime.hasUrls() else []
                except (AttributeError, TypeError):
                    urls = []
                if len(urls) > 1:
                    QMessageBox.information(
                        self,
                        "That drop can't be used yet",
                        "Drop one audio file at a time. Pick the single sound "
                        "you want to use and drop it here again.",
                    )
                elif urls and (not urls[0].isLocalFile() or urls[0].host()):
                    QMessageBox.information(
                        self,
                        "That drop can't be used yet",
                        "That drop is a link or a web address, not a file on "
                        "this computer. Save or download the audio first, then "
                        "drop the real file here.",
                    )
                elif urls:
                    QMessageBox.information(
                        self,
                        "That drop can't be used yet",
                        "Drop one local audio file: an already-encoded .xma, or "
                        "ordinary audio such as WAV, MP3, FLAC, OGG or M4A, "
                        "which is converted to this sound's exact shape first.",
                    )
            event.ignore()  # type: ignore[attr-defined]
            return
        self.audioDropped.emit(path)
        event.acceptProposedAction()  # type: ignore[attr-defined]


def fit_slot_image(
    parent: QWidget | None,
    path: Path,
    width: int,
    height: int,
    label: str,
    *,
    mode: str = "auto",
    staged_destination: Path,
) -> Path | None:
    """Return an exact-size image for one slot, offering to convert for the user.

    Any format and any size are accepted. Dialog and drag/drop share this
    helper. When a resize is required and ``mode`` is ``auto``, the user
    chooses Contain, Cover, or Stretch. An already-correct RGBA PNG is
    returned untouched. Returns ``None`` when the file cannot be read or the
    user cancels.
    """
    from mod_editor.core.errors import ValidationError
    from mod_editor.core.image_fit import (
        fit_image,
        fit_mode_from_label,
        fit_mode_labels,
        fit_to_png,
    )

    try:
        probe = fit_image(path, width, height, mode="auto")
    except ValidationError as exc:
        QMessageBox.information(
            parent,
            "That file could not be read as an image",
            f"{exc}\n\nFix: choose or drop a {_plain_image_formats()} image. "
            "Any size works -- the editor resizes it for you.",
        )
        return None

    needs_png_conversion = (
        probe.source_format != "PNG" or probe.source_mode != "RGBA"
    )
    if not probe.changed and not needs_png_conversion:
        return path

    chosen_mode = mode
    if mode == "auto":
        if probe.changed:
            labels = fit_mode_labels()
            choice, accepted = QInputDialog.getItem(
                parent,
                "How should this image fit the slot?",
                f"{label} must be exactly {width}×{height}, and that image is "
                f"{probe.source_width}×{probe.source_height}.\n\n"
                "Choose Contain, Cover, or Stretch. Dialog and drag/drop share "
                "this path. Your original file is not modified.",
                labels,
                0,
                False,
            )
            if not accepted:
                return None
            try:
                chosen_mode = fit_mode_from_label(str(choice))
            except ValidationError as exc:
                QMessageBox.information(parent, "Invalid fit mode", str(exc))
                return None
        else:
            chosen_mode = "contain"
    else:
        answer = QMessageBox.question(
            parent,
            "Prepare this image?",
            f"{label} must be exactly {width}×{height}, and that image is "
            f"{probe.source_width}×{probe.source_height}.\n\n"
            f"Mod Studio will apply fit mode “{chosen_mode}”.\n\n"
            "Your original file is not modified -- the prepared copy is used for "
            "this edit only.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return None
    try:
        result = fit_to_png(
            path, width, height, staged_destination, mode=chosen_mode
        )
    except ValidationError as exc:
        QMessageBox.information(
            parent,
            "Could not prepare that image",
            f"{exc}\n\nFix: try a different {_plain_image_formats()} image. "
            "No edit was staged.",
        )
        return None
    del result
    return staged_destination


class SlotImagePreviewDialog(QDialog):
    """Shows exactly what will land in a slot before the edit is committed.

    Placement and fit matter for crests and wordmarks, so a plain text dialog
    is not enough: this renders the prepared, exact-size PNG against a
    checkerboard so the modder sees the real result -- not a promise -- before
    anything is staged.  It previews only; the writer semantics are unchanged.
    """

    def __init__(
        self,
        image_path: Path,
        *,
        width: int,
        height: int,
        title: str,
        summary_lines: Iterable[str] = (),
        accept_label: str = "Use this image",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(10)

        heading = QLabel("Preview of the result")
        heading.setObjectName("panelTitle")
        root.addWidget(heading)
        explanation = QLabel(
            f"This is exactly what will be written into the {width}×{height} "
            "slot. Nothing is staged until you choose "
            f"“{accept_label}”."
        )
        explanation.setObjectName("findingText")
        explanation.setWordWrap(True)
        root.addWidget(explanation)

        board = QFrame()
        board.setObjectName("previewCheckerboard")
        tile = QPixmap(24, 24)
        tile.fill(QColor("#0b121e"))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 12, 12, QColor("#21314a"))
        painter.fillRect(12, 12, 12, 12, QColor("#21314a"))
        painter.end()
        palette = board.palette()
        palette.setBrush(QPalette.Window, QBrush(tile))
        board.setPalette(palette)
        board.setAutoFillBackground(True)
        board_layout = QVBoxLayout(board)
        board_layout.setContentsMargins(14, 14, 14, 14)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        board_layout.addWidget(self.image_label)
        root.addWidget(board, 1)

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.image_label.setText("This prepared image could not be previewed.")
        else:
            fitted = pixmap.scaled(
                QSize(520, 240), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_label.setPixmap(fitted)
        self.image_label.setToolTip(
            f"Exact slot pixels: {width}×{height}. Transparency uses the "
            "checkerboard background."
        )

        for line in summary_lines:
            detail = QLabel(line)
            detail.setObjectName("metadataText")
            detail.setWordWrap(True)
            root.addWidget(detail)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        accept = buttons.button(QDialogButtonBox.Ok)
        accept.setText(accept_label)
        accept.setObjectName("primaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


def confirm_prepared_slot_image(
    parent: QWidget | None,
    image_path: Path,
    *,
    width: int,
    height: int,
    title: str,
    summary_lines: Iterable[str] = (),
    accept_label: str = "Use this image",
) -> bool:
    """True when the modder approves the exact pixels about to be staged."""

    dialog = SlotImagePreviewDialog(
        image_path,
        width=width,
        height=height,
        title=title,
        summary_lines=summary_lines,
        accept_label=accept_label,
        parent=parent,
    )
    return dialog.exec_() == QDialog.Accepted


class WordElidedLabel(QLabel):
    """One-line label that truncates at a word boundary and keeps full help."""

    def __init__(self, text: str):
        super().__init__()
        self._full_text = ""
        # Eliding the drawn text is only half of it: QLabel still reports the
        # full sentence as its minimum width, so a layout can never actually
        # shrink the label and the whole page inherits the sentence as a hard
        # floor.  Declaring here that this label may be shrunk is what makes
        # the eliding reachable, and it belongs with the class rather than at
        # each call site -- omitting it is invisible on a wide desktop and only
        # surfaces on a narrow screen or a wider system font.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, self.sizePolicy().verticalPolicy())
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._full_text = " ".join(text.split())
        self.setToolTip(self._full_text)
        self._refresh_text()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._refresh_text()

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        # Stylesheets are applied after most pages are constructed, so refresh
        # once the final font metrics and card width are known.
        self._refresh_text()

    def _refresh_text(self) -> None:
        width = max(0, self.contentsRect().width())
        metrics = self.fontMetrics()
        if width <= 0 or metrics.horizontalAdvance(self._full_text) <= width:
            QLabel.setText(self, self._full_text)
            return
        suffix = "…"
        words = self._full_text.split()
        visible: list[str] = []
        for word in words:
            candidate = " ".join((*visible, word))
            if metrics.horizontalAdvance(candidate + suffix) > width:
                break
            visible.append(word)
        if visible:
            QLabel.setText(self, " ".join(visible) + suffix)
        else:
            QLabel.setText(
                self,
                metrics.elidedText(self._full_text, Qt.ElideRight, width),
            )


class CapabilityPanel(QFrame):
    """Compact, registry-driven capability cards used by every category."""

    def __init__(self, category: ApfCategory):
        super().__init__()
        self.category = category
        self.setObjectName("capabilityPanel")
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setHorizontalSpacing(8)
        self.layout.setVerticalSpacing(8)
        self.set_cards(())

    def set_cards(
        self,
        cards: tuple[CapabilityCard, ...],
        *,
        catalog_ready: bool = False,
        inventory_count: int = 0,
    ) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        # Each entry: title, summary, status, tooltip findings, badge override.
        # A None badge falls back to the shared status wording; the pre-load
        # placeholder overrides it because "Coming soon" would misread a page
        # that is simply waiting for a game.
        display: list[tuple[str, str, ApfStatus, str, str | None]] = [
            (card.title, card.summary, card.status, "\n".join(card.findings[:2]), None)
            for card in cards
        ]
        if not display:
            if catalog_ready:
                display.append(
                    (
                        "Complete category inventory",
                        f"All {inventory_count:,} records in this category are browsable; each row shows decoded export versus raw-only access.",
                        ApfStatus.EXPORT_ONLY,
                        "Rows unlock for editing only after a writer for that exact resource is proven byte-exact.",
                        None,
                    )
                )
            else:
                display.append(
                    (
                        "Load a game to see what's editable here",
                        "Capability cards appear once your APF 2K8 ISO or game folder is recognized. The source is opened read-only.",
                        ApfStatus.COMING_SOON,
                        "Nothing is ever written to your original files.",
                        "○ No game loaded",
                    )
                )
        for index, (title, summary, status, findings, badge_text) in enumerate(display):
            card = QFrame()
            card.setObjectName("capabilityCard")
            card.setProperty("status", status.value)
            card.setFixedHeight(66)
            # Every card's full text ends with a plain next step, so a
            # first-time modder always knows what to do after reading the
            # boundary.  The one-line summary on the card itself is unchanged.
            next_step = _capability_next_step(status)
            details = "\n\n".join(
                part for part in (summary, findings, next_step) if part
            )
            card.setToolTip(f"{title}\n\n{details}")
            box = QVBoxLayout(card)
            box.setContentsMargins(10, 7, 10, 7)
            box.setSpacing(3)
            top = QHBoxLayout()
            top.setSpacing(6)
            name = WordElidedLabel(title)
            name.setObjectName("capabilityTitle")
            name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            badge = QLabel(badge_text or _status_text(status))
            badge.setObjectName("statusBadge")
            badge.setStyleSheet(
                f"color: {_status_color(status)}; border-color: {_status_color(status)};"
            )
            top.addWidget(name, 1)
            top.addWidget(badge, 0, Qt.AlignTop)
            body = WordElidedLabel(summary)
            body.setObjectName("capabilitySummary")
            body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            body.setFixedHeight(16)
            body.setToolTip(details)
            box.addLayout(top)
            box.addWidget(body)
            if len(display) == 1:
                self.layout.addWidget(card, 0, 0, 1, 3)
            else:
                self.layout.addWidget(card, index // 3, index % 3)
        for column in range(3):
            self.layout.setColumnStretch(column, 1)


class PageHeading(QWidget):
    def __init__(self, category: ApfCategory):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        subtitle = QLabel(CATEGORY_BLURBS[category])
        subtitle.setObjectName("pageSummary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.setAccessibleName(f"{category.title} summary")


class AssetBrowser(QWidget):
    """Searchable, filtered, paged browser for the complete live APF catalog."""

    modifiedChanged = pyqtSignal()
    #: A selected row asking the shell to open the workspace that owns its
    #: writer, optionally carrying the image the user already chose here.
    openWorkspaceRequested = pyqtSignal(object)

    def __init__(
        self,
        facade: ApfStudioFacade,
        category: ApfCategory,
        run_task: TaskRunner,
        *,
        browse_export_only: bool = False,
        action_lock_reason: str = "",
    ):
        super().__init__()
        self.facade = facade
        self.category = category
        self.run_task = run_task
        self._matches: tuple[ApfAsset, ...] = ()
        self._visible: dict[str, ApfAsset] = {}
        self._route: WorkspaceRoute | None = None
        self._excluded_asset_ids: frozenset[str] = frozenset()
        self._included_asset_ids: frozenset[str] | None = None
        self.browse_export_only = browse_export_only
        self.action_lock_reason = action_lock_reason.strip()
        self._page = 0
        self._preview_token = 0
        # Private exact-size copies prepared from ordinary images; removed with
        # the browser, never entered into a project.
        self._fit_dir: Path | None = None
        self.destroyed.connect(self._cleanup_fitted_images)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search… e.g. logo_l0, number_0_color, font_albedo, shoulder_color  (Ctrl+F)"
        )
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search assets in this category")
        self.search.setProperty("studioSearch", True)
        self.search.setToolTip(
            "Search the current category by name, type, class, or archive index. "
            "Jersey digits are number_0_color…number_9_color (not under shoulder — "
            "search All Textures if arm/shoulder numbers look missing). "
            "Nameplate glyphs are font_albedo / font_normal (NameFont packages). "
            "Press Ctrl+F from anywhere to focus this box; × to clear."
        )
        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(145)
        self.type_filter.addItem("All asset types", None)
        self.status_filter = QComboBox()
        self.status_filter.setMinimumWidth(140)
        self.status_filter.addItem("Any status", None)
        for status in ApfStatus:
            self.status_filter.addItem(_status_text(status), status.value)
        self.result_count = QLabel("Load a game to browse")
        self.result_count.setObjectName("countPill")
        controls.addWidget(self.search, 1)
        controls.addWidget(self.type_filter)
        controls.addWidget(self.status_filter)
        controls.addWidget(self.result_count)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(
            ("Status", "Asset", "Type", "Archive location", "Decoded size")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, self.table.horizontalHeader().ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, self.table.horizontalHeader().ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        splitter.addWidget(self.table)

        detail = QFrame()
        detail.setObjectName("panel")
        detail.setMinimumWidth(330)
        detail.setMaximumWidth(440)
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(16, 16, 16, 16)
        detail_box.setSpacing(9)
        self.detail_title = QLabel("Choose an asset")
        self.detail_title.setObjectName("panelTitle")
        self.detail_title.setWordWrap(True)
        self.detail_status = QLabel("Every indexed record remains visible.")
        self.detail_status.setObjectName("mutedLabel")
        self.detail_status.setWordWrap(True)
        self.preview = ImageDropLabel(
            "Select a texture to generate a PNG preview. You can also drop a "
            "replacement image here — any size or format works."
        )
        self.preview.setAcceptDrops(False)
        self.preview.pngDropped.connect(self._replace_from_drop)
        self.preview.setMinimumHeight(190)
        self.preview.setMaximumHeight(270)
        self.detail_metadata = QLabel("")
        self.detail_metadata.setObjectName("metadataText")
        self.detail_metadata.setWordWrap(True)
        self.detail_notes = QLabel("")
        self.detail_notes.setObjectName("findingText")
        self.detail_notes.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.export_button = QPushButton("Export…")
        self.export_button.setObjectName("primaryButton")
        self.replace_button = QPushButton("Replace PNG…")
        self.replace_button.setObjectName("secondaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.export_button.setToolTip("Export this asset from your own game copy.")
        self.replace_button.setToolTip(
            "Choose any image (any size or format), or drop one onto the "
            "preview — it is resized to this slot for you."
        )
        self.revert_button.setToolTip("Nothing to revert—this asset is unmodified.")
        self.export_button.clicked.connect(self._export_selected)
        self.replace_button.clicked.connect(self._replace_selected)
        self.revert_button.clicked.connect(self._revert_selected)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.replace_button)
        buttons.addWidget(self.revert_button)
        detail_box.addWidget(self.detail_title)
        detail_box.addWidget(self.detail_status)
        detail_box.addWidget(self.preview, 1)
        detail_box.addWidget(self.detail_metadata)
        detail_box.addWidget(self.detail_notes)
        detail_box.addStretch(1)
        detail_box.addLayout(buttons)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        pager = QHBoxLayout()
        pager.setSpacing(8)
        self.previous_button = QPushButton("← Previous")
        self.next_button = QPushButton("Next →")
        self.page_label = QLabel("Page 0 of 0")
        self.page_label.setObjectName("mutedLabel")
        self.previous_button.clicked.connect(lambda: self._change_page(-1))
        self.next_button.clicked.connect(lambda: self._change_page(1))
        pager.addStretch(1)
        pager.addWidget(self.previous_button)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next_button)
        root.addLayout(pager)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _text: self._queue_refresh())
        self.type_filter.currentIndexChanged.connect(lambda _index: self._queue_refresh())
        self.status_filter.currentIndexChanged.connect(lambda _index: self._queue_refresh())
        self._clear_detail()

    def set_excluded_asset_ids(self, asset_ids: Iterable[str]) -> None:
        """Hide exact records already represented by a safer specialist UI.

        Exclusion is identity-based rather than name-based because many APF
        resources intentionally share names such as ``helmet_normal``.  Every
        normal category browser leaves this set empty; the uniform page uses it
        only to avoid displaying the 96 typed writer targets a second time.
        """

        values = frozenset(asset_ids)
        if values != self._excluded_asset_ids:
            self._excluded_asset_ids = values
            self._page = 0

    def set_included_asset_ids(self, asset_ids: Iterable[str] | None) -> None:
        """Optionally narrow a category to an exact semantic identity set.

        The filter operates only on catalog IDs.  It cannot grant a writer or
        alter an asset's capability status, which makes it suitable for
        reviewed semantic views such as the bounded Field Art families.
        Passing ``None`` restores the complete category inventory.
        """

        values = None if asset_ids is None else frozenset(asset_ids)
        if values != self._included_asset_ids:
            self._included_asset_ids = values
            self._page = 0

    def _scoped_assets(
        self,
        *,
        search: str = "",
        status: ApfStatus | None = None,
        type_name: str | None = None,
    ) -> tuple[ApfAsset, ...]:
        if not self.facade.source_ready:
            return ()
        values = self.facade.browse_assets(
            search=search,
            category=self.category,
            status=status,
            type_name=type_name,
            limit=len(self.facade.require_catalog().assets) + 1,
        )
        return tuple(
            asset
            for asset in values
            if asset.asset_id not in self._excluded_asset_ids
            and (
                self._included_asset_ids is None
                or asset.asset_id in self._included_asset_ids
            )
        )

    def set_context(self) -> None:
        current_type = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("All asset types", None)
        if self.facade.source_ready:
            for type_name in sorted(
                {asset.type_name for asset in self._scoped_assets()}
            ):
                self.type_filter.addItem(type_name, type_name)
        if current_type:
            index = self.type_filter.findData(current_type)
            if index >= 0:
                self.type_filter.setCurrentIndex(index)
        self.type_filter.blockSignals(False)
        self._page = 0
        self.refresh()

    def _queue_refresh(self) -> None:
        self._page = 0
        self._filter_timer.start()

    def refresh(self, preserve_asset_id: str | None = None) -> None:
        if preserve_asset_id is None:
            selected = self._selected_asset()
            preserve_asset_id = selected.asset_id if selected else None
        if not self.facade.source_ready:
            self._matches = ()
            self.table.setRowCount(0)
            self.result_count.setText("Load a game to browse")
            self.page_label.setText("Page 0 of 0")
            load_tip = (
                "Load your APF game first, then page All Textures / inventory results."
            )
            for button in (self.previous_button, self.next_button):
                button.setEnabled(True)
                button.setToolTip(load_tip)
                button.setProperty("disableReason", load_tip)
            self._clear_detail()
            return
        status_value = self.status_filter.currentData()
        status = ApfStatus(status_value) if status_value else None
        self._matches = self._scoped_assets(
            search=self.search.text(),
            status=status,
            type_name=self.type_filter.currentData(),
        )
        page_count = max(1, (len(self._matches) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = max(0, min(self._page, page_count - 1))
        start = self._page * PAGE_SIZE
        rows = self._matches[start : start + PAGE_SIZE]
        self._visible = {asset.asset_id: asset for asset in rows}
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for row, asset in enumerate(rows):
            edit_id = _edit_id_for_asset(asset)
            modified = edit_id in self.facade.modified_asset_ids
            status_text = "● Modified" if modified else _asset_status_text(asset)
            values = (
                status_text,
                asset.name,
                asset.type_name,
                asset.location,
                _human_bytes(asset.decoded_size),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, asset.asset_id)
                if column == 0:
                    item.setForeground(QColor("#39d98a" if modified else _status_color(asset.status)))
                self.table.setItem(row, column, item)
        self.table.setUpdatesEnabled(True)
        self.result_count.setText(f"{len(self._matches):,} assets")
        self.page_label.setText(f"Page {self._page + 1} of {page_count}")
        # Never silent-gray: Previous/Next teach first/last page walls.
        if self._page > 0:
            self.previous_button.setEnabled(True)
            self.previous_button.setToolTip("Show the previous page of assets.")
            self.previous_button.setProperty("disableReason", "")
        else:
            tip = "Already on the first page of matching assets."
            self.previous_button.setEnabled(True)
            self.previous_button.setToolTip(tip)
            self.previous_button.setProperty("disableReason", tip)
        if self._page + 1 < page_count:
            self.next_button.setEnabled(True)
            self.next_button.setToolTip("Show the next page of assets.")
            self.next_button.setProperty("disableReason", "")
        else:
            tip = "Already on the last page of matching assets."
            self.next_button.setEnabled(True)
            self.next_button.setToolTip(tip)
            self.next_button.setProperty("disableReason", tip)
        restored = False
        if preserve_asset_id:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.UserRole) == preserve_asset_id:
                    self.table.selectRow(row)
                    restored = True
                    break
        if not restored and rows:
            self.table.selectRow(0)
            # Re-selecting the same row *number* emits no selection change, so
            # after a search that keeps the row count the detail panel would
            # keep describing the asset that used to be there -- and Export or
            # Replace would then act on that stale row instead of the visible
            # one. Refresh the detail from the table every time.
            self._selection_changed()
        elif not rows:
            query = self.search.text().strip()
            empty_msg = (
                "No assets match those filters.\n\n"
                "Try: logo_l0 · logo_l1 · number_0_color…number_9_color · "
                "font_albedo · shoulder_color · draft_logo.\n"
                "Jersey digits are not under shoulder materials — search "
                "number_N_color in All Textures. Press Esc or × to clear search."
            )
            if query:
                empty_msg = (
                    f"No assets match “{query}”.\n\n"
                    "Try: logo_l0 · number_0_color · font_albedo · shoulder_color. "
                    "Clear search (Esc) or switch type/status filters."
                )
            self.result_count.setText("0 assets · clear search?")
            self._clear_detail(empty_msg)

    def _change_page(self, delta: int) -> None:
        button = self.previous_button if delta < 0 else self.next_button
        reason = str(button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot change page yet", reason)
            return
        self._page += delta
        self.refresh()

    def _selected_asset(self) -> ApfAsset | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return self._visible.get(item.data(Qt.UserRole)) if item else None

    def _selection_changed(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            self._clear_detail()
            return
        edit_id = _edit_id_for_asset(asset)
        modified = edit_id in self.facade.modified_asset_ids
        self.detail_title.setText(asset.name)
        self.detail_status.setText(
            f"{'● Modified  •  ' if modified else ''}{_asset_status_text(asset)}  •  {asset.asset_class}"
        )
        self.detail_metadata.setText(
            f"{asset.type_name}  •  {asset.location}\n"
            f"{_human_bytes(asset.decoded_size)} decoded  •  {asset.part_count} stored part"
            f"{'s' if asset.part_count != 1 else ''}\n"
            f"ID: {asset.asset_id}"
        )
        editable_png = _is_editable_png_asset(asset) and not self.browse_export_only
        # A row this browser cannot write itself may still be owned by a proved
        # editor elsewhere in the app.  Resolving that turns the old refusal
        # into a hand-off, which is the whole point of this panel's actions.
        route = None if editable_png else _workspace_route_for(self.facade, asset)
        self._route = route
        notes = list(asset.notes)
        action = _asset_product_action(asset)
        if action is not None:
            notes.insert(0, action.authoring_note)
        if route is not None:
            notes.insert(0, route.summary)
        elif self.browse_export_only and self.action_lock_reason:
            notes.insert(0, self.action_lock_reason)
        notes.append(f"Export action: {asset.export_label}.")
        self.detail_notes.setText("\n".join(notes) or "This exact record can be exported from your own game.")
        self.export_button.setEnabled(True)
        self.export_button.setProperty("disableReason", "")
        self.export_button.setToolTip(f"Export {asset.name} ({asset.export_label}).")
        # Drop parity with the Replace button: a drop is admitted when Replace
        # works here, and also when a workspace can finish the same drop.
        self.preview.setAcceptDrops(editable_png or route is not None)
        if route is not None:
            self.replace_button.setText(route.action_label)
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(True)
            self.replace_button.setProperty("disableReason", "")
            self.replace_button.setToolTip(
                f"Open {asset.name} in {route.destination}, the workspace whose "
                "proved writer owns it. Choose or drop your image here and it "
                "arrives there already staged."
            )
            self.revert_button.setText("Revert")
            self.revert_button.setVisible(True)
            self.revert_button.setEnabled(True)
            rev = (
                f"{asset.name} is edited in {route.destination}; revert it "
                "there, or use Revert All in the footer."
            )
            self.revert_button.setToolTip(rev)
            self.revert_button.setProperty("disableReason", rev)
        elif self.browse_export_only:
            self.replace_button.setText("Replace locked")
            self.revert_button.setText("Revert locked")
            self.replace_button.setVisible(True)
            # Stay clickable: Field Art stock rows teach the wall instead of silent gray.
            self.replace_button.setEnabled(True)
            self.revert_button.setVisible(True)
            self.revert_button.setEnabled(True)
            lock = self.action_lock_reason or (
                "Replacement is locked for this browse surface. Click explains why."
            )
            self.replace_button.setToolTip(lock)
            self.replace_button.setProperty("disableReason", lock)
            self.revert_button.setToolTip(
                "There is no staged replacement to revert here because "
                "replacement is locked on this browse surface."
            )
            self.revert_button.setProperty("disableReason", lock)
        else:
            self.replace_button.setText("Replace PNG…")
            self.revert_button.setText("Revert")
            # Always visible+enabled when a row is selected; non-editable rows explain.
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(True)
            if editable_png:
                self.replace_button.setProperty("disableReason", "")
                self.replace_button.setToolTip(
                    f"Replace {asset.name} with any image (auto-resized to the slot)."
                )
            else:
                tip = (
                    f"No proved writer owns {asset.name} yet, so this build "
                    "does not offer a replacement for it. Export raw/parts to "
                    "study it; editing unlocks when an exact writer exists."
                )
                self.replace_button.setToolTip(tip)
                self.replace_button.setProperty("disableReason", tip)
            self.revert_button.setVisible(True)
            # Never silent-gray: stay clickable; non-editable/unmodified teach.
            if editable_png and modified:
                rev_tip = f"Restore the original {asset.name} texture."
                rev_block = ""
            elif not editable_png:
                rev_tip = rev_block = (
                    f"There is no staged replacement for {asset.name}, because "
                    "no proved writer owns it yet."
                )
            else:
                rev_tip = rev_block = (
                    f"Nothing to revert—{asset.name} is still original."
                )
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(rev_tip)
            self.revert_button.setProperty("disableReason", rev_block)
        self._preview_token += 1
        token = self._preview_token
        if modified and editable_png:
            modification = self.facade.require_session().modification(edit_id)
            if modification is not None:
                self.preview.set_image(modification.replacement_path)
                return
        if asset.type_name != "TXTR":
            self.preview.set_message("Raw and structured export is available for this asset.")
            return
        self.preview.set_loading("Preparing preview from your game…")

        def operation(progress: Callable[[str, int, int], None]) -> tuple[bool, object]:
            try:
                if action is not None and action.replace_method == "replace_number":
                    path = self.facade.preview_asset(asset.asset_id, progress)
                elif action is not None:
                    preview = getattr(self.facade, action.preview_method)
                    path = preview(progress)
                else:
                    path = self.facade.preview_asset(asset.asset_id, progress)
                return True, path
            except Exception as exc:
                return False, str(exc)

        def complete(result: object) -> None:
            if token != self._preview_token or self._selected_asset() != asset:
                return
            ok, value = result  # type: ignore[misc]
            if ok:
                self.preview.set_image(Path(value))
                note = getattr(self.facade, "preview_alpha_note", None)
                if note:
                    self.preview.setToolTip(
                        self.preview.toolTip() + "\n\n" + str(note)
                    )
            else:
                self.preview.set_error(str(value))

        # Fail closed after 45s so "Preparing preview…" never means blank forever.
        # Token must still match: a newer selection cancels this watchdog silently.
        def _preview_watchdog() -> None:
            if token != self._preview_token:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                f"{asset.name}: preview still preparing after 45s. "
                "Re-select the row, Export raw TXTR parts, or search another asset. "
                "PORTME formats show an explicit error instead of hanging blank."
            )

        QTimer.singleShot(45_000, _preview_watchdog)
        self.run_task("Preparing asset preview", operation, complete, False)

    def _clear_detail(
        self,
        message: str = (
            "Choose an asset on the left to inspect, export, or replace it.\n"
            "Try search: logo_l0 · number_0_color · font_albedo · shoulder_color."
        ),
    ) -> None:
        self.detail_title.setText("Choose an asset")
        self.detail_status.setText("Every indexed record remains visible.")
        self.preview.set_message(message)
        self.preview.setAcceptDrops(False)
        self._route = None
        self.detail_metadata.setText("")
        self.detail_notes.setText("")
        choose_tip = (
            "Choose an asset on the left first. Export/Replace stay clickable so "
            "a gray control is never a dead no-op."
        )
        self.export_button.setEnabled(True)
        self.export_button.setToolTip(choose_tip)
        self.export_button.setProperty("disableReason", choose_tip)
        if self.browse_export_only:
            self.replace_button.setText("Replace locked")
            self.revert_button.setText("Revert locked")
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(True)
            self.revert_button.setVisible(True)
            self.revert_button.setEnabled(True)
            lock = self.action_lock_reason or choose_tip
            self.replace_button.setToolTip(lock)
            self.replace_button.setProperty("disableReason", lock)
            self.revert_button.setToolTip(
                "There is no staged replacement to revert here because "
                "replacement is locked on this browse surface."
            )
            self.revert_button.setProperty("disableReason", lock)
        else:
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(True)
            self.replace_button.setToolTip(choose_tip)
            self.replace_button.setProperty("disableReason", choose_tip)
            self.revert_button.setVisible(False)
            self.revert_button.setToolTip("Nothing to revert—choose a modified editable asset first.")

    def _export_selected(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export yet",
                reason + "\n\nFix: select a row in the list, then Export.",
            )
            return
        asset = self._selected_asset()
        if asset is None:
            return
        if asset.type_name == "TXTR":
            default_suffix = ".png"
            filters = "PNG preview (*.png);;Raw parts bundle (*.zip)"
        elif asset.type_name == "AUDO":
            default_suffix = ".wav"
            filters = "Decoded WAV (*.wav);;Original XMA (*.xma);;Raw parts bundle (*.zip)"
        elif asset.inner_index is None:
            default_suffix = ".bin"
            filters = "Raw outer record (*.bin)"
        else:
            default_suffix = ".zip"
            filters = "Raw parts bundle (*.zip)"
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in asset.name)
        destination, chosen_filter = QFileDialog.getSaveFileName(
            self,
            "Export asset from your game",
            str(Path.home() / f"{safe_name}{default_suffix}"),
            filters,
        )
        if not destination:
            return
        path = Path(destination)
        suffix_by_filter = {
            "PNG": ".png",
            "Decoded": ".wav",
            "Original": ".xma",
            "Raw parts": ".zip",
            "Raw outer": ".bin",
        }
        if not path.suffix:
            for prefix, suffix in suffix_by_filter.items():
                if chosen_filter.startswith(prefix):
                    path = path.with_suffix(suffix)
                    break
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            action = _asset_product_action(asset)
            if action is not None and path.suffix.casefold() == ".png":
                modification = self.facade.require_session().modification(
                    action.edit_id
                )
                if modification is not None:
                    progress(f"Exporting current {asset.name} PNG", 0, 0)
                    return _copy_new(modification.replacement_path, path)
                if action.replace_method == "replace_number":
                    return self.facade.export_asset(asset.asset_id, path, progress)
                export = getattr(self.facade, action.export_method)
                return export(path, progress)
            return self.facade.export_asset(asset.asset_id, path, progress)

        self.run_task(
            "Exporting game asset",
            operation,
            lambda result: self._export_complete(Path(result)),
            True,
        )

    def _export_complete(self, path: Path) -> None:
        QMessageBox.information(
            self,
            "Export complete",
            f"Saved to:\n{path}\n\nThis local export came from your own game copy.",
        )

    def _cleanup_fitted_images(self, *_args: object) -> None:
        root = self._fit_dir
        self._fit_dir = None
        if root is not None and root.name.startswith("apf-browser-fitted-"):
            shutil.rmtree(root, ignore_errors=True)

    def _fitted_path(self, name: str) -> Path:
        if self._fit_dir is None:
            self._fit_dir = Path(tempfile.mkdtemp(prefix="apf-browser-fitted-"))
        return self._fit_dir / f"{name}-{uuid4().hex}.png"

    def _replace_selected(self) -> None:
        asset = self._selected_asset()
        route = self._route
        if asset is not None and route is not None:
            # The row has a proved writer, just not in this browser. Let the
            # user pick the image here and carry it to the workspace that
            # owns it, so one click finishes the job they started.
            path, _filter = QFileDialog.getOpenFileName(
                self,
                f"Choose an image for {asset.name} (any size or format)",
                str(Path.home()),
                IMAGE_IMPORT_FILTER,
            )
            self._hand_off(asset, route, Path(path) if path else None)
            return
        reason = str(self.replace_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace this texture yet",
                reason
                + "\n\nReplacement never mutates your original dump.",
            )
            return
        if asset is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose an image for {asset.name} (any size or format)",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
        )
        if not path:
            return
        self._replace_from_drop(Path(path))

    def _hand_off(
        self, asset: ApfAsset, route: WorkspaceRoute, image: Path | None
    ) -> None:
        """Ask the shell to open this row in the workspace that can write it."""

        self.openWorkspaceRequested.emit(
            WorkspaceHandoff(
                route=route,
                asset_name=asset.name,
                asset_id=asset.asset_id,
                image=str(image) if image is not None else "",
            )
        )

    def _replace_from_drop(self, path: Path) -> None:
        """Replace the selected row from a chosen or dropped image.

        The file dialog and the drop target share this one route, so both
        accept any ordinary image and hand the writer an exact-size PNG.
        """

        asset = self._selected_asset()
        if asset is not None and self._route is not None:
            self._hand_off(asset, self._route, Path(path))
            return
        action = _asset_product_action(asset) if asset is not None else None
        if asset is None or action is None:
            return
        if not self.preview.acceptDrops():
            QMessageBox.information(
                self,
                "This row can't be replaced yet",
                "Only editable texture rows accept a replacement image. "
                "Choose a row marked Editable and try again.",
            )
            return

        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in asset.name
        )
        replace_method = action.replace_method
        if replace_method == "replace_digital_font":
            # The score-digit mask has a white-RGB / alpha-only contract; the
            # dedicated preparer converts any image into that exact shape.
            prepared = _prepare_digital_font_mask(
                self, Path(path), self._fitted_path(safe_name)
            )
        elif replace_method == "replace_number":
            prepared = fit_slot_image(
                self,
                Path(path),
                512,
                512,
                f"The {asset.name} jersey digit",
                mode="contain",
                staged_destination=self._fitted_path(safe_name),
            )
            if prepared is not None:
                prepared = _conform_number_png(prepared, asset.name)
        else:
            # draft_logo (and any future exact-size PNG editor) accepts any
            # image, contained onto the slot with transparent padding.
            prepared = fit_slot_image(
                self,
                Path(path),
                128,
                128,
                f"The {asset.name} texture",
                mode="contain",
                staged_destination=self._fitted_path(safe_name),
            )
        if prepared is None:
            return
        if replace_method == "replace_number":
            replace = lambda png, progress, asset_id=asset.asset_id: (
                self.facade.replace_number(asset_id, png, progress)
            )
        else:
            replace = getattr(self.facade, replace_method)
        self.run_task(
            f"Replacing {asset.name}",
            lambda progress: replace(prepared, progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _revert_selected(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Nothing to revert", reason)
            return
        asset = self._selected_asset()
        action = _asset_product_action(asset) if asset is not None else None
        if asset is None or action is None:
            return
        self.run_task(
            f"Reverting {asset.name}",
            lambda progress: self.facade.revert(action.edit_id, progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _mutation_complete(self, preserve_asset_id: str) -> None:
        self.refresh(preserve_asset_id)
        self.modifiedChanged.emit()


class UniformStudioPage(QWidget):
    """The fully editable 96-asset APF physical-uniform workspace."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._assets: tuple[UniformAsset, ...] = ()
        self._visible: dict[str, UniformAsset] = {}
        self._preview_token = 0
        # Private exact-size copies prepared from ordinary images.  They serve
        # one edit and are removed with the panel, never entered into projects.
        self._fit_dir: Path | None = None
        self.destroyed.connect(self._cleanup_fitted_images)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(10)
        outer.addWidget(PageHeading(ApfCategory.UNIFORMS))
        self.capabilities = CapabilityPanel(ApfCategory.UNIFORMS)
        outer.addWidget(self.capabilities)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        browser = QFrame()
        browser.setObjectName("panel")
        browser.setMinimumWidth(330)
        browser.setMaximumWidth(430)
        browser_box = QVBoxLayout(browser)
        browser_box.setContentsMargins(14, 13, 14, 13)
        browser_box.setSpacing(8)
        heading = QHBoxLayout()
        label = QLabel("Uniform texture cards")
        label.setObjectName("panelTitle")
        self.count = QLabel("96 textures")
        self.count.setObjectName("countPill")
        heading.addWidget(label)
        heading.addStretch(1)
        heading.addWidget(self.count)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search slots or linked teams… (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search uniform slots")
        self.search.setProperty("studioSearch", True)
        self.search.setToolTip(
            "Search uniform slots. Press Ctrl+F to focus; Clear or × to reset."
        )
        self.clear_search_button = QToolButton()
        self.clear_search_button.setObjectName("clearSearchButton")
        self.clear_search_button.setText("×")
        self.clear_search_button.setAccessibleName("Clear uniform search")
        self.clear_search_button.setToolTip("Clear the uniform search")
        self.clear_search_button.setVisible(False)
        self.clear_search_button.clicked.connect(self.search.clear)
        self.family_filter = QComboBox()
        self.family_filter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.family_filter.addItem("All families (96)", None)
        for label, family in (
            ("Jerseys (24)", "jersey"),
            ("Pants (24)", "pants"),
            ("Helmets (24)", "helmet"),
            ("Shoulders (24)", "shoulder"),
        ):
            self.family_filter.addItem(label, family)
        search_row = QHBoxLayout()
        search_row.setSpacing(7)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.clear_search_button)
        family_row = QHBoxLayout()
        family_row.setSpacing(9)
        family_label = QLabel("FILTER BY FAMILY")
        family_label.setObjectName("filterLabel")
        family_row.addWidget(family_label)
        family_row.addWidget(self.family_filter, 1)
        self.list = QListWidget()
        self.list.setObjectName("assetList")
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setSpacing(2)
        self.list.currentItemChanged.connect(lambda _current, _previous: self._selection_changed())
        self.search.textChanged.connect(self._search_changed)
        self.family_filter.currentIndexChanged.connect(lambda _index: self.refresh())
        browser_box.addLayout(heading)
        browser_box.addLayout(search_row)
        browser_box.addLayout(family_row)
        browser_box.addWidget(self.list, 1)
        splitter.addWidget(browser)

        detail = QFrame()
        detail.setObjectName("panel")
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(18, 17, 18, 17)
        detail_box.setSpacing(10)
        detail_heading = QHBoxLayout()
        titles = QVBoxLayout()
        self.title = QLabel("Choose a uniform texture")
        self.title.setObjectName("panelTitle")
        self.subtitle = QLabel("Jerseys, pants, helmets, and shoulders each have 24 physical slots.")
        self.subtitle.setObjectName("mutedLabel")
        self.subtitle.setWordWrap(True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        self.modified_badge = QLabel("Editable")
        self.modified_badge.setObjectName("statusBadge")
        detail_heading.addLayout(titles, 1)
        detail_heading.addWidget(self.modified_badge, 0, Qt.AlignTop)
        self.preview = ImageDropLabel(
            "Load your game, then choose one of the 96 texture cards.\n\n"
            "You can also drop any image here — any size or format works; it "
            "is resized to the slot for you."
        )
        self.preview.pngDropped.connect(self._replace_path)
        self.contract = QLabel("")
        self.contract.setObjectName("contractText")
        self.contract.setWordWrap(True)
        self.teams = QLabel("")
        self.teams.setObjectName("metadataText")
        self.teams.setWordWrap(True)
        self.notes = QLabel("")
        self.notes.setObjectName("findingText")
        self.notes.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export PNG…")
        self.export_button.setObjectName("secondaryButton")
        self.replace_button = QPushButton("Replace PNG…")
        self.replace_button.setObjectName("primaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.export_button.setToolTip("Export the current PNG, including your replacement if modified.")
        self.replace_button.setToolTip(
            "Choose any image (any size or format) or drop one onto the "
            "preview — it is resized to this slot for you."
        )
        self.revert_button.setToolTip("Nothing to revert—this texture is unmodified.")
        self.export_button.clicked.connect(self._export_selected)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.revert_button.clicked.connect(self._revert_selected)
        actions.addWidget(self.export_button)
        actions.addWidget(self.replace_button)
        actions.addWidget(self.revert_button)
        actions.addStretch(1)
        detail_box.addLayout(detail_heading)
        detail_box.addWidget(self.preview, 1)
        detail_box.addWidget(self.contract)
        detail_box.addWidget(self.teams)
        detail_box.addWidget(self.notes)
        detail_box.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        self.tabs.setAccessibleName("Uniform and equipment workspaces")
        editor_tab = QWidget()
        editor_tab.setAccessibleName("Editable uniform materials")
        editor_layout = QVBoxLayout(editor_tab)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.addWidget(splitter, 1)
        self.tabs.addTab(editor_tab, "Editable Materials (96)")
        self.tabs.setTabToolTip(
            0,
            "The 96 bounded jersey, pants, helmet, and shoulder material-color writers.",
        )

        inventory_tab = QWidget()
        inventory_tab.setAccessibleName("Additional uniform and equipment assets")
        inventory_layout = QVBoxLayout(inventory_tab)
        inventory_layout.setContentsMargins(10, 10, 10, 10)
        inventory_layout.setSpacing(8)
        self.inventory_summary = QLabel(
            "Load your game to inventory every uniform and equipment record outside the 96 safe material writers."
        )
        self.inventory_summary.setObjectName("metadataText")
        self.inventory_summary.setWordWrap(True)
        self.inventory_browser = AssetBrowser(
            facade, ApfCategory.UNIFORMS, run_task
        )
        self.inventory_browser.modifiedChanged.connect(self.modifiedChanged)
        inventory_layout.addWidget(self.inventory_summary)
        inventory_layout.addWidget(self.inventory_browser, 1)
        self.tabs.addTab(inventory_tab, "Additional Assets")
        self.tabs.setTabToolTip(
            1,
            "Every remaining indexed uniform/equipment record, with decoded PNG when supported and exact raw export always available.",
        )
        self.independence_panel = UniformIndependencePanel(facade, run_task)
        self.tabs.addTab(self.independence_panel, "Team Independence")
        self.tabs.setTabToolTip(
            2,
            "Teams share helmet, jersey and sock textures, so editing one team "
            "changes others. This gives every team its own.",
        )
        self.custom_team_appearance_panel = CustomTeamAppearancePanel(
            facade, run_task
        )
        self.custom_team_appearance_panel.modifiedChanged.connect(
            self.modifiedChanged
        )
        self.tabs.addTab(
            self.custom_team_appearance_panel, "Custom Team Appearance"
        )
        self.tabs.setTabToolTip(
            3,
            "HOME/AWAY ARGB palettes and exact helmet/crest selectors for "
            "safe user-team slots 32–39, including the 2017 Eagles preset.",
        )
        self.model_export_panel = PlayerEquipmentModelExportPanel(facade, run_task)
        self.tabs.addTab(self.model_export_panel, "Model Round Trip")
        self.tabs.setTabToolTip(
            4,
            "Export stock helmet/equipment and player-body geometry, then import "
            "same-topology POSITION edits into a separately verified copied 0A. "
            "Materials, skinning, attachment and changed topology stay preserved/locked.",
        )
        self.uniform_equipment_colors_panel = UniformEquipmentColorsPanel(
            facade, run_task
        )
        self.uniform_equipment_colors_panel.modifiedChanged.connect(
            self.modifiedChanged
        )
        self.tabs.addTab(
            self.uniform_equipment_colors_panel, "Equipment Colors"
        )
        self.tabs.setTabToolTip(
            5,
            "Independent HOME/AWAY facemask and Team-turtleneck palette "
            "selectors for all 40 teams.",
        )
        outer.addWidget(self.tabs, 1)
        self._clear_detail()

    def _search_changed(self, text: str) -> None:
        self.clear_search_button.setVisible(bool(text))
        self.refresh()

    def set_context(self) -> None:
        self.model_export_panel.set_context()
        self.custom_team_appearance_panel.set_context()
        self.uniform_equipment_colors_panel.set_context()
        if not self.facade.source_ready:
            self.independence_panel.set_source_ready(False)
            self._assets = ()
            self.inventory_browser.set_excluded_asset_ids(())
            self.capabilities.set_cards(())
            self.tabs.setTabText(0, "Editable Materials (96)")
            self.tabs.setTabText(1, "Additional Assets")
            self.inventory_summary.setText(
                "Load your game to inventory every uniform and equipment record outside the 96 safe material writers."
            )
            self.refresh()
            self.inventory_browser.set_context()
            return
        self.independence_panel.set_source_ready(True)
        # Rectangular textlogo assets share the same project/build transport,
        # but their user-facing home is Logos → Wordmarks, not this material
        # color workspace.
        self._assets = tuple(
            asset
            for asset in self.facade.uniform_assets()
            if asset.family != "textlogo"
        )
        all_uniform_records = self.facade.browse_assets(
            category=ApfCategory.UNIFORMS,
            limit=len(self.facade.require_catalog().assets) + 1,
        )
        editable_locations = {
            (asset.outer_index, asset.inner_index) for asset in self._assets
        }
        represented_record_ids = frozenset(
            asset.asset_id
            for asset in all_uniform_records
            if (asset.outer_index, asset.inner_index) in editable_locations
        )
        self.inventory_browser.set_excluded_asset_ids(represented_record_ids)
        additional_count = len(all_uniform_records) - len(represented_record_ids)
        self.capabilities.set_cards(
            self.facade.capability_cards(ApfCategory.UNIFORMS),
            catalog_ready=True,
            inventory_count=len(all_uniform_records),
        )
        self.tabs.setTabText(0, f"Editable Materials ({len(self._assets):,})")
        self.tabs.setTabText(1, f"Additional Assets ({additional_count:,})")
        self.inventory_summary.setText(
            f"{len(all_uniform_records):,} indexed uniform/equipment records total  •  "
            f"{len(represented_record_ids):,} safely editable material colors  •  "
            f"{additional_count:,} additional source records. Additional assets are "
            "preview/export-only until an exact bounded writer owns them."
        )
        self.refresh()
        self.inventory_browser.set_context()

    def refresh(self, preserve_asset_id: str | None = None) -> None:
        selected = self._selected_asset()
        if preserve_asset_id is None and selected is not None:
            preserve_asset_id = selected.asset_id
        needle = self.search.text().strip().casefold()
        family = self.family_filter.currentData()
        matches = []
        for asset in self._assets:
            haystack = f"{asset.family} {asset.asset_index} {asset.title} {' '.join(asset.affected_teams)}".casefold()
            if family and asset.family != family:
                continue
            if needle and needle not in haystack:
                continue
            matches.append(asset)
        self._visible = {asset.asset_id: asset for asset in matches}
        self.list.blockSignals(True)
        self.list.clear()
        selected_item: QListWidgetItem | None = None
        for asset in matches:
            modified = asset.asset_id in self.facade.modified_asset_ids
            affected = f"{len(asset.affected_teams)} linked team{'s' if len(asset.affected_teams) != 1 else ''}"
            item = QListWidgetItem(
                f"{asset.family.upper()}  {asset.asset_index:02d}"
                f"\n{asset.width}×{asset.height}  •  {affected}"
                f"{'  •  ✓ MODIFIED' if modified else ''}"
            )
            item.setData(Qt.UserRole, asset.asset_id)
            item.setSizeHint(QSize(0, 52))
            if modified:
                item.setForeground(QColor("#55e5b0"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list.addItem(item)
            if asset.asset_id == preserve_asset_id:
                selected_item = item
        self.list.blockSignals(False)
        if not self.facade.source_ready:
            self.count.setText("Load game")
        else:
            family_total = sum(
                1 for asset in self._assets if not family or asset.family == family
            )
            scope = {
                "jersey": "Jerseys",
                "pants": "Pants",
                "helmet": "Helmets",
                "shoulder": "Shoulders",
            }.get(family, "all families")
            if needle:
                self.count.setText(f"{len(matches)} / {family_total} shown")
            else:
                self.count.setText(f"{family_total} • {scope}")
            self.count.setToolTip(f"Showing {len(matches)} of {family_total} textures in {scope}.")
        if selected_item is not None:
            self.list.setCurrentItem(selected_item)
        elif self.list.count():
            self.list.setCurrentRow(0)
        elif self.facade.source_ready:
            self._clear_detail("No uniform textures match that search.")
        else:
            # Before a game is loaded the list is empty because there is no
            # source yet, not because a search failed; say so honestly.
            self._clear_detail(
                "Uniform textures · exact-size RGBA PNG\n"
                "Load your game to browse and edit all 96 mapped slots.\n\n"
                + START_HERE_HINT
            )

    def _selected_asset(self) -> UniformAsset | None:
        item = self.list.currentItem()
        return self._visible.get(item.data(Qt.UserRole)) if item else None

    def focus_workspace_route(self, route: WorkspaceRoute, image: Path | None) -> bool:
        """Select one material slot handed over from an asset browser.

        Any active family filter or search text is cleared first: a hand-off
        that lands on an empty list because of a filter the user forgot about
        would be a worse wall than the one this replaced.
        """

        if route.tab != UNIFORM_MATERIALS_TAB:
            return False
        self.tabs.setCurrentIndex(0)
        if self.family_filter.currentData() is not None:
            self.family_filter.setCurrentIndex(0)
        if self.search.text():
            self.search.clear()
        self.refresh(route.key)
        asset = self._selected_asset()
        if asset is None or asset.asset_id != route.key:
            return False
        if image is not None:
            self._replace_path(image)
        return True

    def _selection_changed(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            self._clear_detail()
            return
        modified = asset.asset_id in self.facade.modified_asset_ids
        self.title.setText(asset.title)
        self.subtitle.setText(
            f"Physical {asset.family} slot {asset.asset_index:02d}  •  "
            f"outer {asset.outer_index} / inner {asset.inner_index}"
        )
        self.modified_badge.setText("● Modified" if modified else _status_text(asset.status))
        color = "#39d98a" if modified else _status_color(asset.status)
        self.modified_badge.setStyleSheet(f"color: {color}; border-color: {color};")
        # A fixed-allocation slot's budget is set by how detailed retail's own
        # artwork there is, not by the free space around it, so the answer has
        # to arrive while the slot is being chosen rather than 40 s into a
        # build that refuses it (davidhbui, Beta 38).
        capacity_line = self._capacity_summary(asset)
        team_line = self._team_capacity_line(asset)
        extra = "".join(
            f"\n{line}" for line in (capacity_line, team_line) if line
        )
        self.contract.setText(f"PNG contract\n{asset.png_contract}{extra}")
        self.contract.setVisible(True)
        teams = ", ".join(asset.affected_teams) if asset.affected_teams else "No current team selector references this physical slot."
        self.teams.setText(f"Selector ownership\n{teams}")
        self.teams.setVisible(True)
        self.notes.setText("\n".join(asset.notes))
        self.notes.setVisible(bool(asset.notes))
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        self.export_button.setProperty("disableReason", "")
        self.replace_button.setProperty("disableReason", "")
        self.export_button.setToolTip(
            f"Export {asset.title} as {asset.width}×{asset.height} RGBA PNG."
        )
        self.replace_button.setToolTip(
            f"Replace {asset.title} with any image — resized to "
            f"{asset.width}×{asset.height} (Contain/Cover/Stretch)."
        )
        if modified:
            rev_tip = "Restore the original texture for this slot."
            rev_block = ""
        else:
            rev_tip = rev_block = (
                "Nothing to revert—this texture is still original."
            )
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(rev_tip)
        self.revert_button.setProperty("disableReason", rev_block)
        self.preview.setAcceptDrops(True)
        self._preview_token += 1
        token = self._preview_token
        if modified:
            modification = self.facade.require_session().modification(asset.asset_id)
            if modification is not None:
                self.preview.set_image(modification.replacement_path)
                return
        self.preview.set_loading(
            f"Preparing {asset.title} from your game  •  "
            f"{asset.width}×{asset.height} PNG"
        )

        def complete(result: object) -> None:
            if token == self._preview_token and self._selected_asset() == asset:
                self.preview.set_image(Path(result))
                note = getattr(self.facade, "preview_alpha_note", None)
                if note:
                    self.preview.setToolTip(
                        self.preview.toolTip() + "\n\n" + str(note)
                    )

        def _uniform_preview_watchdog() -> None:
            if token != self._preview_token:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                f"{asset.title}: preview still preparing after 45s. "
                "Re-select the slot or Export PNG / Export raw."
            )

        QTimer.singleShot(45_000, _uniform_preview_watchdog)
        self.run_task(
            "Preparing uniform preview",
            lambda progress: self.facade.preview_uniform(asset.asset_id, progress),
            complete,
            False,
        )

    def _capacity_summary(self, asset) -> str:
        """The selected slot's replacement budget, or "" when there is no model."""

        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return ""
        try:
            from . import uniform_targets

            capacity = uniform_targets.slot_capacity(
                Path(index_0a), str(asset.family), int(asset.asset_index)
            )
            return uniform_targets.capacity_summary(capacity)
        except Exception:
            return ""

    def _team_capacity_line(self, asset) -> str:
        """Per-team jersey+shoulder ranks when this slot names its owners."""

        teams = tuple(getattr(asset, "affected_teams", ()) or ())
        if not teams:
            return ""
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return ""
        try:
            from . import uniform_targets

            jersey_by_team: dict[str, int] = {}
            shoulder_by_team: dict[str, int] = {}
            for item in self._assets:
                if item.family == "jersey":
                    for team in item.affected_teams:
                        jersey_by_team[team] = item.asset_index
                elif item.family == "shoulder":
                    for team in item.affected_teams:
                        shoulder_by_team[team] = item.asset_index
            lines: list[str] = []
            for team in teams:
                line = uniform_targets.team_capacity_line(
                    Path(index_0a),
                    jersey_by_team.get(team),
                    shoulder_by_team.get(team),
                )
                if not line:
                    continue
                lines.append(f"{team}: {line}" if len(teams) > 1 else line)
                if len(lines) >= 3:
                    break
            return "\n".join(lines)
        except Exception:
            return ""

    def _clear_detail(
        self,
        message: str = "Load your APF game to begin.\n\n" + START_HERE_HINT,
    ) -> None:
        self.title.setText("Choose a uniform texture")
        self.subtitle.setText("All 96 mapped physical uniform slots appear in this browser.")
        self.modified_badge.setText("○ Not loaded")
        self.modified_badge.setStyleSheet("")
        self.preview.setAcceptDrops(False)
        self.preview.set_message(message)
        # These rows carry their own card backgrounds, so an empty string
        # would still paint a hollow box; hide them until they have content.
        self.contract.setText("")
        self.contract.setVisible(False)
        self.teams.setText("")
        self.teams.setVisible(False)
        self.notes.setText("")
        self.notes.setVisible(False)
        # Never silent-gray: stay clickable; explain load/select next step.
        load_tip = (
            "Load your APF game and select a uniform texture row first. "
            "Export/Replace stay clickable so a gray control is never a dead no-op."
        )
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        self.export_button.setToolTip(load_tip)
        self.replace_button.setToolTip(load_tip)
        self.export_button.setProperty("disableReason", load_tip)
        self.replace_button.setProperty("disableReason", load_tip)
        revert_tip = "Nothing to revert—choose a modified texture first."
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty("disableReason", revert_tip)

    def _export_selected(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export uniform yet",
                reason
                + "\n\nFix: File → Load game, open Uniforms, select a jersey/helmet "
                "slot, then Export.",
            )
            return
        asset = self._selected_asset()
        if asset is None:
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Export current uniform PNG",
            str(Path.home() / f"apf-{asset.family}-{asset.asset_index:02d}.png"),
            "RGBA PNG (*.png)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".png")
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            modification = self.facade.require_session().modification(asset.asset_id)
            if modification is not None:
                progress("Exporting current replacement PNG", 0, 0)
                return _copy_new(modification.replacement_path, path)
            return self.facade.export_uniform(asset.asset_id, path, progress)

        self.run_task(
            "Exporting uniform PNG",
            operation,
            lambda result: QMessageBox.information(
                self, "PNG exported", f"Saved to:\n{Path(result)}"
            ),
            True,
        )

    def _choose_replacement(self) -> None:
        reason = str(self.replace_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace uniform yet",
                reason
                + "\n\nFix: File → Load game, open Uniforms, select a slot, then "
                "Replace. Import stages a project copy — never mutates your original.",
            )
            return
        asset = self._selected_asset()
        if asset is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose an image for {asset.title} (any size — "
            f"{asset.width}×{asset.height} exact, or it can be resized)",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
        )
        if path:
            self._replace_path(Path(path))

    def _cleanup_fitted_images(self, *_args: object) -> None:
        root = self._fit_dir
        self._fit_dir = None
        if root is not None and root.name.startswith("apf-uniform-fitted-"):
            shutil.rmtree(root, ignore_errors=True)

    def _fitted_path(self, name: str) -> Path:
        if self._fit_dir is None:
            self._fit_dir = Path(tempfile.mkdtemp(prefix="apf-uniform-fitted-"))
        return self._fit_dir / f"{name}-{uuid4().hex}.png"

    def _replace_path(self, path: Path) -> None:
        asset = self._selected_asset()
        if asset is None:
            return
        # Uniform slots occupy fixed byte spans, so the writers still require
        # the exact pixel size.  Any image the user has is converted here
        # instead of being refused, so the chooser and the drop target both
        # hand the writer an already-correct RGBA PNG.
        fitted = fit_slot_image(
            self,
            Path(path),
            asset.width,
            asset.height,
            f"The {asset.family} texture “{asset.title}”",
            mode="auto",
            staged_destination=self._fitted_path(
                f"{asset.family}-{asset.asset_index:02d}"
            ),
        )
        if fitted is None:
            return
        self.run_task(
            f"Replacing {asset.title}",
            lambda progress: self.facade.replace_uniform(asset.asset_id, fitted, progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _revert_selected(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Nothing to revert", reason)
            return
        asset = self._selected_asset()
        if asset is None:
            return
        self.run_task(
            f"Reverting {asset.title}",
            lambda progress: self.facade.revert(asset.asset_id, progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _mutation_complete(self, asset_id: str) -> None:
        self.refresh(asset_id)
        self.modifiedChanged.emit()


def _conform_number_png(path: Path, name: str) -> Path:
    """Force the jersey-number channel contract the writer will validate.

    Writes a sibling copy. The user's source file is never overwritten.
    """

    from PIL import Image

    with Image.open(path) as image:
        image.load()
        size = image.size
        rgba = bytearray(image.convert("RGBA").tobytes())
    if not name.endswith("_normal"):
        return path
    for offset in range(0, len(rgba), 4):
        rgba[offset + 2] = 0
        rgba[offset + 3] = 255
    destination = path.with_name(f"{path.stem}.apf-number-normal{path.suffix}")
    Image.frombytes("RGBA", size, bytes(rgba)).save(destination)
    return destination


def _prepare_digital_font_mask(
    parent: QWidget | None,
    path: Path,
    destination: Path,
) -> Path | None:
    """Convert any image into the score-digit slot's white-on-alpha mask.

    The writer's contract is unchanged: exactly 128×128, RGB solid white, and
    the digits drawn only in the alpha channel.  This helper does that work
    for the user -- resizing any size, reading any ordinary format, keeping
    existing transparency where the image has it, and otherwise turning
    brightness into transparency -- instead of refusing the file.
    """
    from mod_editor.core.errors import ValidationError
    from mod_editor.core.image_fit import fit_image
    from PIL import Image

    width = height = 128
    try:
        probe = fit_image(path, width, height, mode="contain")
    except ValidationError as exc:
        QMessageBox.information(
            parent,
            "That file could not be read as an image",
            f"{exc}\n\nFix: choose or drop a {_plain_image_formats()} image. "
            "Any size works -- the editor resizes it for you.",
        )
        return None
    rgba = probe.rgba
    has_alpha = any(
        rgba[offset + 3] != 255 for offset in range(0, len(rgba), 4)
    )
    converted = bytearray(len(rgba))
    if has_alpha:
        for offset in range(0, len(rgba), 4):
            converted[offset] = 255
            converted[offset + 1] = 255
            converted[offset + 2] = 255
            converted[offset + 3] = rgba[offset + 3]
        change = (
            "keep its transparency as the digit mask and make the rest of "
            "the image solid white"
        )
    else:
        for offset in range(0, len(rgba), 4):
            luminance = (
                rgba[offset] * 54
                + rgba[offset + 1] * 183
                + rgba[offset + 2] * 19
            ) >> 8
            converted[offset] = 255
            converted[offset + 1] = 255
            converted[offset + 2] = 255
            converted[offset + 3] = luminance
        change = (
            "turn its brightness into transparency (bright stays visible, "
            "dark fades out) and make the color solid white"
        )
    size_note = (
        f"That image is {probe.source_width}×{probe.source_height}, so Mod "
        f"Studio will also {probe.describe().lower()} to the exact 128×128 "
        "slot size. "
        if probe.changed
        else ""
    )
    answer = QMessageBox.question(
        parent,
        "Prepare this image?",
        "The score-digit texture reads only transparency: the digits are "
        "drawn in the alpha channel and the color must stay solid white.\n\n"
        f"{size_note}Mod Studio can {change} for you.\n\n"
        "Your original file is not modified -- the prepared copy is used for "
        "this edit only.",
        QMessageBox.Yes | QMessageBox.Cancel,
        QMessageBox.Yes,
    )
    if answer != QMessageBox.Yes:
        return None
    try:
        Image.frombytes("RGBA", (width, height), bytes(converted)).save(
            destination, "PNG"
        )
    except (OSError, ValueError) as exc:
        QMessageBox.information(
            parent,
            "Could not prepare that image",
            f"{exc}\n\nFix: try a different {_plain_image_formats()} image. "
            "No edit was staged.",
        )
        return None
    return destination


class DigitalFontPanel(QFrame):
    """Focused editor for the proved 128×128 DXT5A score-digit mask."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._fit_dir: Path | None = None
        self.destroyed.connect(self._cleanup_fitted_images)
        self.setObjectName("panel")
        box = QHBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(16)
        self.preview = ImageDropLabel(
            "digital_font · 128×128 RGBA PNG\nLoad your game to see the original mask."
        )
        self.preview.setFixedSize(220, 220)
        self.preview.pngDropped.connect(self._replace_path)
        box.addWidget(self.preview)
        content = QVBoxLayout()
        title_row = QHBoxLayout()
        title = WordElidedLabel("digital_font — score digit mask")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.status)
        specs = QHBoxLayout()
        specs.setSpacing(6)
        specs.addWidget(
            _spec_pill(
                "128×128 RGBA PNG",
                emphasis=True,
                tooltip=(
                    "The writer accepts exactly 128×128. Drop or choose any "
                    "image size or format — the editor resizes and converts "
                    "it for you before anything is staged."
                ),
            )
        )
        specs.addWidget(
            _spec_pill(
                "Alpha-only mask",
                tooltip=(
                    "The game reads only the alpha channel of this texture. "
                    "Keep RGB solid white and draw the digits in alpha — or "
                    "drop any image and Mod Studio converts it for you."
                ),
            )
        )
        specs.addStretch(1)
        description = QLabel(
            "Choose or drop any image — the editor resizes it to 128×128 and "
            "converts it to the white-on-transparency mask this slot needs. "
            "Replace stores your original automatically; Revert removes only "
            "this edit."
        )
        description.setObjectName("cardBody")
        description.setWordWrap(True)
        description.setToolTip(
            "The proved writer owns exactly outer 1310 / inner 246 (digital_font), "
            "a 128×128 DXT5A alpha mask."
        )
        self.path_note = QLabel("No source loaded.")
        self.path_note.setObjectName("metadataText")
        self.path_note.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export PNG…")
        self.export_button.setObjectName("secondaryButton")
        self.replace_button = QPushButton("Replace PNG…")
        self.replace_button.setObjectName("primaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.export_button.setToolTip("Export the current score-digit mask PNG.")
        self.replace_button.setToolTip(
            "Choose any image (any size or format) or drop it onto the "
            "preview — it is resized and converted to the digit mask for you."
        )
        self.revert_button.setToolTip("Nothing to revert—digital_font is unmodified.")
        self.export_button.clicked.connect(self._export)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.revert_button.clicked.connect(self._revert)
        actions.addWidget(self.export_button)
        actions.addWidget(self.replace_button)
        actions.addWidget(self.revert_button)
        actions.addStretch(1)
        content.addLayout(title_row)
        content.addLayout(specs)
        content.addWidget(description)
        content.addWidget(self.path_note)
        # Actions stay attached to the copy above; leftover panel height falls
        # below them so the edit workflow never sinks toward a distant bottom
        # edge inside a tall tab pane.
        content.addLayout(actions)
        content.addStretch(1)
        box.addLayout(content, 1)
        self.set_context()

    def set_context(self) -> None:
        ready = self.facade.source_ready
        modified = ready and DIGITAL_FONT_EDIT_ID in self.facade.modified_asset_ids
        # Never silent-gray: stay clickable; explain when game not loaded.
        load_tip = (
            "Load your APF game first (0A). digital_font export/replace needs the "
            "score-digit mask outer. Click still explains — buttons stay clickable."
        )
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        if ready:
            self.export_button.setProperty("disableReason", "")
            self.replace_button.setProperty("disableReason", "")
            self.export_button.setToolTip("Export the current score-digit mask PNG.")
            self.replace_button.setToolTip(
                "Choose any image (any size or format) or drop it onto the "
                "preview — it is resized and converted to the digit mask for you."
            )
        else:
            self.export_button.setProperty("disableReason", load_tip)
            self.replace_button.setProperty("disableReason", load_tip)
            self.export_button.setToolTip(load_tip)
            self.replace_button.setToolTip(load_tip)
        self.revert_button.setEnabled(True)
        self.revert_button.setProperty(
            "disableReason",
            "" if modified else "Nothing to revert—digital_font is still original.",
        )
        self.revert_button.setToolTip(
            "Restore the original digital_font texture."
            if modified
            else "Nothing to revert—digital_font is still original."
        )
        self.preview.setAcceptDrops(ready)
        self.status.setText(
            "● Modified"
            if modified
            else (_status_text(ApfStatus.EDITABLE) if ready else "○ Not loaded")
        )
        color = "#39d98a" if ready else "#8795aa"
        self.status.setStyleSheet(f"color: {color}; border-color: {color};")
        if not ready:
            self.preview.set_message(
                "digital_font · 128×128 RGBA PNG\nLoad your game to see the original mask."
            )
            self.path_note.setText(
                "No source loaded.\n\n" + START_HERE_HINT
            )
            return
        modification = self.facade.require_session().modification(DIGITAL_FONT_EDIT_ID)
        if modification is not None:
            self.preview.set_image(modification.replacement_path)
            self.path_note.setText(
                "Current preview: your validated replacement. The original remains in the private backup cache."
            )
            return
        self.preview.set_loading("Generating the original mask from your game…")
        self.path_note.setText("Current preview: original texture from your own game.")
        started = id(self.preview)

        def _digital_font_watchdog() -> None:
            if id(self.preview) != started:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                "digital_font: preview still preparing after 45s. "
                "Re-open Score digits or Export the mask PNG."
            )

        QTimer.singleShot(45_000, _digital_font_watchdog)
        self.run_task(
            "Preparing digital_font preview",
            lambda progress: self.facade.preview_digital_font(progress),
            lambda result: self.preview.set_image(Path(result)),
            False,
        )

    def _export(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export digital_font yet",
                reason + "\n\nFix: File → Load game, then Export the score-digit mask.",
            )
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Export current digital_font PNG",
            str(Path.home() / "apf-digital_font.png"),
            "RGBA PNG (*.png)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".png")
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            modification = self.facade.require_session().modification(DIGITAL_FONT_EDIT_ID)
            if modification is not None:
                progress("Exporting current digital_font PNG", 0, 0)
                return _copy_new(modification.replacement_path, path)
            return self.facade.export_digital_font(path, progress)

        self.run_task(
            "Exporting digital_font",
            operation,
            lambda result: QMessageBox.information(
                self, "PNG exported", f"Saved to:\n{Path(result)}"
            ),
            True,
        )

    def _choose_replacement(self) -> None:
        reason = str(self.replace_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace digital_font yet",
                reason
                + "\n\nFix: File → Load game, then Replace or drop an image. "
                "Never mutates your original dump.",
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose an image for digital_font (any size or format)",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
        )
        if path:
            self._replace_path(Path(path))

    def _cleanup_fitted_images(self, *_args: object) -> None:
        root = self._fit_dir
        self._fit_dir = None
        if root is not None and root.name.startswith("apf-digital-font-fitted-"):
            shutil.rmtree(root, ignore_errors=True)

    def _fitted_path(self) -> Path:
        if self._fit_dir is None:
            self._fit_dir = Path(
                tempfile.mkdtemp(prefix="apf-digital-font-fitted-")
            )
        return self._fit_dir / f"digital-font-{uuid4().hex}.png"

    def stage_image(self, path: Path) -> None:
        """Finish a replacement a browser row started, after a hand-off."""

        self._replace_path(Path(path))

    def _replace_path(self, path: Path) -> None:
        if not self.facade.source_ready:
            return
        # The writer still demands exactly 128×128, white RGB, alpha-only
        # digits.  Instead of refusing anything else, prepare that exact mask
        # from whatever ordinary image the user chose or dropped.
        prepared = _prepare_digital_font_mask(
            self, Path(path), self._fitted_path()
        )
        if prepared is None:
            return
        self.run_task(
            "Replacing digital_font",
            lambda progress: self.facade.replace_digital_font(prepared, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Nothing to revert",
                reason + "\n\nStage a digital_font replacement first.",
            )
            return
        self.run_task(
            "Reverting digital_font",
            lambda progress: self.facade.revert(DIGITAL_FONT_EDIT_ID, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _mutation_complete(self) -> None:
        self.set_context()
        self.modifiedChanged.emit()


@dataclass(frozen=True)
class _HelmetTextureMasterDraft:
    source_image: Path
    source_sha256: str
    source_width: int
    source_height: int
    source_resample: str
    pipeline: Mapping[str, object]
    transform: AuthoringTransform
    editor_transform: Mapping[str, object]
    native_baseline_png: Path | None = None
    native_canvas_edited: bool = False


@dataclass(frozen=True)
class _HelmetTextureMasterInput:
    source_image: Path
    source_width: int
    source_height: int
    source_resample: str
    pipeline: Mapping[str, object]
    source_sha256: str | None = None
    private_snapshot: bool = False


class ApfTeamLogoPanel(QFrame):
    """Focused editor for a selected APF team-logo / helmet crest.

    This surface is intentionally self-contained.  It reads the loaded game's
    read-only ``0A`` to render a source-derived preview of the selected
    ``uniform_logo_NN`` ``logo_l0`` helmet crest, stages
    exactly one 512x512 RGBA PNG, mirrors it to the package's ``logo_l0`` and
    ``logo_l1`` crest consumers, and presents one "Team Logo" build that keeps
    package and menu-cache ownership explicit:

    * ``apf2k8.logos_cards.team_logo`` (``tools/apf_logo_patch.py``) rewrites the
      crest layers inside the selected ``uniform_logo_NN`` package and rebuilds
      their packed mip tails from the new mask;
    * ``apf2k8.logos_cards.team_logo_cache`` (``tools/apf_logocache_patch.py``)
      rewrites the matching catalog entry inside the prebuilt, runtime-resident
      ``uniform_logocache`` aggregate.

    Full-shell compiles all package/cache/shell bytes before a private staged
    volume is created; only a complete, reopened stage receives the requested
    final name through atomic no-replace publication. The retail source is never
    opened for writing, and any failed gate leaves the final name absent.

    Coverage is one of two fixed product profiles: the retail side decal or the
    whole-shell atlas route. The latter affects every
    team's shared helmet material, so all 118 packages are migrated before the
    selected art is applied. It
    creates no emulator patch and never edits ``default.xex``.  The staged design
    participates in the normal shareable project and complete-game Build.
    """

    modifiedChanged = pyqtSignal()

    # tools/apf_logo_patch.py is the authority for these dimensions; the panel
    # mirrors them only for its honest, read-only-safe stage guard.
    _WIDTH = 512
    _HEIGHT = 512

    def selected_crest(self):
        """The team whose crest a build will write.

        Falls back to the historical default rather than raising, so a panel
        constructed without its combo populated still targets something real.
        """
        crest = self.slot.currentData()
        return crest if crest is not None else default_crest()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._staged_png: Path | None = None
        self._source_staged_png: Path | None = None
        # A crest's detail layer, staged only when someone authors both halves.
        # Left None, one supplied mark goes to logo_l0 and logo_l1 is cleared.
        self._staged_detail_png: Path | None = None
        self._placement_source_rgba: bytes | None = None
        self._placement_state: Placement | None = None
        self._texture_master_draft: _HelmetTextureMasterDraft | None = None
        self._texture_master_game_source: str | None = None
        self._staged_profile: str | None = None
        self._preview_dir: Path | None = None
        self.destroyed.connect(self._cleanup_private_preview_files)
        self.setObjectName("panel")
        box = QHBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(16)
        self.preview = ImageDropLabel(
            "Team crest + linked Team Select cache · 512×512 RGBA PNG\n"
            "Load your game to see the original."
        )
        self.preview.setFixedSize(220, 220)
        self.preview.pngDropped.connect(self._stage_path)
        box.addWidget(self.preview)

        content = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel("Team Logo — crest + frontend cache")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.status)

        specs = QHBoxLayout()
        specs.setSpacing(6)
        specs.addWidget(
            _spec_pill(
                "512×512 RGBA PNG",
                emphasis=True,
                tooltip=(
                    "The crest slot holds exactly 512×512. Drop or choose any "
                    "image size or format — an off-size file is resized and "
                    "converted for you before anything is staged."
                ),
            )
        )
        specs.addWidget(
            _spec_pill(
                "4-bit color channels",
                tooltip=(
                    "The stored format is Xenos 4_4_4_4 — one nibble per channel, "
                    "16 levels each — so colors are quantized on write and the "
                    "build reports the exact decode-back error."
                ),
            )
        )
        self.crest_cache_pill = _spec_pill(
            "Co-writes crest + Team Select cache",
            tooltip=(
                "One Team Logo build writes selector-slot-5 crest index N to "
                "both the selected uniform_logo_NN package and linked index N "
                "in the statically mapped frontend/Team Select "
                "uniform_logocache. This describes storage ownership, not a "
                "changed-logo runtime capture."
            ),
        )
        specs.addWidget(self.crest_cache_pill)
        specs.addWidget(
            _spec_pill(
                "Two layers · one mark",
                tooltip=(
                    "A crest is six region masks across two textures: logo_l0 "
                    "carries regions 0-2 in its R/G/B and logo_l1 carries "
                    "regions 3-5, each filled from its own palette entry. 79 "
                    "of the 118 packages use both. One image dropped here is "
                    "written to logo_l0 and the detail layer's masks are "
                    "cleared, so your mark is drawn exactly once — putting the "
                    "same art in both would draw it again in the other three "
                    "colours. Use Export both layers to see the real masks, and "
                    "tools/apf_logo_patch.py --png/--png-l1 to author both."
                ),
            )
        )
        specs.addStretch(1)

        slot_row = QHBoxLayout()
        slot_row.setSpacing(8)
        self.slot_label = QLabel("Crest slot (selector slot 5):")
        self.slot_label.setObjectName("metadataText")
        self.slot = QComboBox()
        self.slot.setObjectName("comboField")
        # Starts as the built-in teams; _populate_slots() widens this to every
        # crest package once a game is loaded and the archive can be read.
        self._slots_populated = False
        for crest in TEAM_CRESTS:
            self.slot.addItem(crest.label, crest)
        self.slot.setCurrentIndex(
            max(0, self.slot.findData(default_crest()))
        )
        self.slot.setToolTip(
            "Selector slot 5 chooses the square crest. Every built-in team wears "
            "a crest package, and each is written the same way: both "
            "uniform_logo_NN layers plus linked index NN in the statically mapped "
            "frontend/Team Select cache. Selector slot 6 independently chooses a "
            "rectangular uniform_textlogo wordmark, which Team Logo does not edit. "
            "Load your game and "
            "this list widens from the twenty-four teams to all 118 crest slots "
            "the disc carries -- the other ninety-four are the game's own logo "
            "library. Which package belongs to which team comes from the disc's "
            "selector table, not a typed list; library slots are named by index "
            "because what a given slot shows in game has not been established."
        )
        slot_row.addWidget(self.slot_label)
        slot_row.addWidget(self.slot, 1)

        coverage_row = QHBoxLayout()
        coverage_row.setSpacing(8)
        coverage_label = QLabel("Helmet coverage:")
        coverage_label.setObjectName("metadataText")
        self.coverage = QComboBox()
        self.coverage.setObjectName("comboField")
        self.coverage.addItem("Retail side decal", RETAIL_CREST_PROFILE)
        self.coverage.addItem(
            "Full-shell crest wrap — entire helmet shell (affects every team)",
            FULL_SHELL_CREST_PROFILE,
        )
        self.coverage.setToolTip(
            "Retail keeps the original side decal (bounded crest). Full-shell "
            "uses the stock helmet-shell atlas and migrates every team package "
            "first. Recommended default for whole-shell paint: Full-shell + "
            "Normal logo (opaque shell body alpha 255 — the old 0x88 "
            "translucent body makes helmets see-through in game). "
            + GLOBAL_HELMET_WARNING
        )
        coverage_row.addWidget(coverage_label)
        coverage_row.addWidget(self.coverage, 1)

        import_mode_row = QHBoxLayout()
        import_mode_row.setSpacing(8)
        self.import_mode_label = QLabel("Full-shell import:")
        self.import_mode_label.setObjectName("metadataText")
        self.import_mode = QComboBox()
        self.import_mode.setObjectName("comboField")
        self.import_mode.addItem(
            "Normal logo — convert to APF regions (recommended)",
            NORMAL_LOGO_IMPORT_MODE,
        )
        self.import_mode.addItem(
            "APF region mask — exact channels (advanced)",
            REGION_MASK_IMPORT_MODE,
        )
        self.import_mode.setToolTip(
            "Normal logo converts ordinary artwork through three colors you "
            "confirm and shows the palette-mapped material preview. Advanced "
            "accepts only an exact zero-blue Xenos 4-bit APF red/green weight mask."
        )
        import_mode_row.addWidget(self.import_mode_label)
        import_mode_row.addWidget(self.import_mode, 1)

        self.fit_visible_mask = QCheckBox(
            "Fit visible mask to full helmet wrap"
        )
        self.fit_visible_mask.setToolTip(
            "Legacy project state only. New full-shell imports use Place on "
            "helmet, where Auto-fit is explicit and reversible before staging."
        )
        # The direct placement canvas supersedes this one-shot transform. Keep
        # the object only to load/re-save legacy project metadata; exposing it
        # after placement could silently refit and erase authored X/Y.
        self.fit_visible_mask.setVisible(False)
        self.fit_visible_mask.setEnabled(False)
        self.coverage_warning = QLabel(GLOBAL_HELMET_WARNING)
        self.coverage_warning.setObjectName("warningText")
        self.coverage_warning.setWordWrap(True)
        self.coverage.currentIndexChanged.connect(self._coverage_changed)
        self.slot.currentIndexChanged.connect(self._coverage_changed)

        description = QLabel(
            "This is the team-logo texture that serves as the helmet crest. "
            "Recommended path: Full-shell coverage + Normal logo import — "
            "opaque shell body (alpha 255), two detail colors, honest palette "
            "preview, then Place on helmet. Avoid translucent shell-body "
            "blacks (retail 0x88 alpha) — they make the whole helmet "
            "see-through in Xenia. Choose APF region mask only for an already-"
            "authored weight map; its colors are always weights, and strict "
            "validation rejects blue, hidden transparent color, overweight "
            "red/green, or non-four-bit values. "
            "The game fills mask regions from its palette, so arbitrary source RGB "
            "cannot be preserved literally. "
            "One build writes the crest into both places the disc stores it, "
            "and regenerates the packed mip levels so the crest is right at "
            "every distance rather than only in close-up."
        )
        description.setObjectName("cardBody")
        description.setWordWrap(True)
        description.setToolTip(
            "Full contract: the writers own both crest layers in the selected "
            "team's uniform_logo_NN package and both matching uniform_logocache "
            "entries, and regenerate every edited packed mip tail from the new "
            "base. Byte-preserving those tails, or leaving logo_l1 retail, is why "
            "older mods showed the old logo at a distance or in uniform previews."
        )
        self.ownership_note = QLabel("")
        self.ownership_note.setObjectName("ownershipText")
        self.ownership_note.setWordWrap(True)
        self.ownership_note.setToolTip(
            "Crest selector slot 5 and wordmark selector slot 6 are independent. "
            "Team Logo never derives, resizes, or overwrites a wordmark."
        )
        self.path_note = QLabel("No source loaded.")
        self.path_note.setObjectName("metadataText")
        self.path_note.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export original PNG…")
        self.export_button.setObjectName("secondaryButton")
        # A crest is two region-mask textures, and 79 of the 118 packages use
        # both. Offering only one flattened export hid the layer a modder has
        # to see before they can author a real crest.
        self.export_layers_button = QPushButton("Export both layers…")
        self.export_layers_button.setObjectName("secondaryButton")
        layers_tip = (
            "Load a team logo first, then export logo_l0 and logo_l1 as "
            "separate PNGs."
        )
        self.export_layers_button.setEnabled(True)
        self.export_layers_button.setToolTip(layers_tip)
        self.export_layers_button.setProperty("disableReason", layers_tip)
        self.master_button = QPushButton(
            "Save high-resolution authoring master…"
        )
        self.master_button.setObjectName("secondaryButton")
        master_tip = (
            "Load a team logo first, then import external artwork before saving "
            "a high-resolution authoring master."
        )
        self.master_button.setEnabled(True)
        self.master_button.setToolTip(master_tip)
        self.master_button.setProperty("disableReason", master_tip)
        self.replace_button = QPushButton("Replace PNG…")
        self.replace_button.setObjectName("primaryButton")
        # Exporting both layers without a way to bring both back left the
        # second half of every real crest reachable only from a terminal.
        self.replace_layers_button = QPushButton("Replace both layers…")
        self.replace_layers_button.setObjectName("secondaryButton")
        replace_layers_tip = (
            "Load a team logo first, then import a logo_l0 and a logo_l1 PNG "
            "to author both halves of the crest."
        )
        self.replace_layers_button.setEnabled(True)
        self.replace_layers_button.setToolTip(replace_layers_tip)
        self.replace_layers_button.setProperty("disableReason", replace_layers_tip)
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.build_button = QPushButton("Build copied 0A (team logo)…")
        self.build_button.setObjectName("secondaryButton")
        # Editing in place removes the export/other-program/import round trip,
        # which is where crests lose their alpha or come back the wrong size.
        # The canvas is 512x512 with no resize control, so it always fits.
        self.edit_button = QPushButton("Edit…")
        self.edit_button.setObjectName("secondaryButton")
        self.edit_button.setToolTip(
            "Draw on the crest here at its exact 512×512 size."
        )
        self.place_button = QPushButton("Place on helmet…")
        self.place_button.setObjectName("secondaryButton")
        self.place_button.setToolTip(
            "For Full-shell coverage: drag the logo on a labeled front/crown/rear "
            "canvas, then adjust width, height, and rotation before staging."
        )
        self.place_button.clicked.connect(self._place_current_logo)
        self.edit_button.clicked.connect(self._edit_in_place)
        self.export_button.setToolTip(
            "Export the current source-derived 512×512 RGBA crest PNG from your game."
        )
        self.replace_button.setToolTip(
            "Choose an edited 512×512 RGBA PNG or drop it onto the preview."
        )
        self.revert_button.setToolTip("Nothing to revert—no replacement is staged.")
        self.build_button.setToolTip(
            "Copy your 0A and write this crest into the selected uniform_logo_NN "
            "package and matching logo-cache slot through the offline-proved "
            "writers. The full-shell profile also writes the shared shell-atlas "
            "route; it creates no Xenia patch and never edits default.xex."
        )
        self.export_button.clicked.connect(self._export_original)
        self.export_layers_button.clicked.connect(self._export_both_layers)
        self.master_button.clicked.connect(self._save_authoring_master)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.replace_layers_button.clicked.connect(self._choose_both_layers)
        self.revert_button.clicked.connect(self._revert)
        self.build_button.clicked.connect(self._build_copied_volume)
        actions.addWidget(self.export_button)
        actions.addWidget(self.export_layers_button)
        actions.addWidget(self.master_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.place_button)
        actions.addWidget(self.replace_button)
        actions.addWidget(self.replace_layers_button)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.build_button)
        actions.addStretch(1)

        content.addLayout(title_row)
        content.addLayout(specs)
        content.addLayout(slot_row)
        content.addLayout(coverage_row)
        content.addLayout(import_mode_row)
        content.addWidget(self.fit_visible_mask)
        content.addWidget(self.coverage_warning)
        content.addWidget(description)
        content.addWidget(self.ownership_note)
        content.addWidget(self.path_note)
        # Keep the edit workflow with its copy; spare height goes below.
        content.addLayout(actions)
        content.addStretch(1)
        box.addLayout(content, 1)
        self.set_context()

    def _selected_profile(self) -> str:
        value = self.coverage.currentData()
        return (
            str(value)
            if value in {RETAIL_CREST_PROFILE, FULL_SHELL_CREST_PROFILE}
            else RETAIL_CREST_PROFILE
        )

    def _selected_import_mode(self) -> str:
        value = self.import_mode.currentData()
        return (
            str(value)
            if value in {NORMAL_LOGO_IMPORT_MODE, REGION_MASK_IMPORT_MODE}
            else NORMAL_LOGO_IMPORT_MODE
        )

    def _refresh_logo_ownership(self) -> None:
        """Expose the proved linked crest owners and independent wordmark bank."""

        crest = self.selected_crest()
        asset_index = int(crest.asset_index)
        package_name = str(crest.package_name)
        self.ownership_note.setText(
            f"Linked crest index {asset_index} (selector slot 5): {package_name} "
            f"(outer {crest.outer_entry_index}) logo_l0/logo_l1 + frontend/Team "
            f"Select cache {asset_index}_logo_l0/{asset_index}_logo_l1. Team Logo "
            "co-writes those two storage owners. Separate wordmark ownership: "
            "selector slot 6 selects an independent uniform_textlogo_00..205 "
            "slot in the Wordmarks tab; it is not resized or changed here. The "
            "frontend cache path is statically mapped; changed-logo runtime "
            "consumption remains unproved."
        )

    def _clear_texture_master_draft(self) -> None:
        draft = self._texture_master_draft
        self._texture_master_draft = None
        self._texture_master_game_source = None
        self._delete_texture_master_files(draft)
        if hasattr(self, "master_button"):
            tip = (
                "Stage a crest with an authoring master draft first, then save. "
                "Click still explains — button stays clickable."
            )
            self.master_button.setEnabled(True)
            self.master_button.setToolTip(tip)
            self.master_button.setProperty("disableReason", tip)

    def _cleanup_private_preview_files(self, *_args: object) -> None:
        """Remove only this panel's exact session-temporary workspace."""

        draft = self._texture_master_draft
        self._texture_master_draft = None
        self._texture_master_game_source = None
        self._delete_texture_master_files(draft)
        root = self._preview_dir
        self._preview_dir = None
        if root is not None and root.name.startswith("apf-team-logo-"):
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _delete_texture_master_files(
        draft: _HelmetTextureMasterDraft | None,
    ) -> None:
        if draft is None:
            return
        draft.source_image.unlink(missing_ok=True)
        if (
            draft.native_baseline_png is not None
            and draft.native_baseline_png != draft.source_image
        ):
            draft.native_baseline_png.unlink(missing_ok=True)

    def _current_game_source_identity(self) -> str | None:
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        return str(Path(index_0a)) if index_0a is not None else None

    @staticmethod
    def _placement_editor_transform(
        placement: Placement, pipeline: Mapping[str, object]
    ) -> dict[str, object]:
        return {
            "canvas_height": 512,
            "canvas_width": 512,
            "coordinate_space": "native-semantic-mask-pixels",
            "operation": "apf-full-shell-semantic-mask-placement",
            "pipeline": dict(pipeline),
            "placement": {
                "center_x": placement.center_x,
                "center_y": placement.center_y,
                "height_scale": placement.scale_y,
                "height_scale_percent": placement.scale_y * 100.0,
                "resample": "nearest",
                "rotation_degrees": placement.rotation_degrees,
                "source_basis": "contained-512x512-semantic-region-mask-active-bbox",
                "width_scale": placement.scale_x,
                "width_scale_percent": placement.scale_x * 100.0,
            },
        }

    def _prepare_placed_texture_master_draft(
        self,
        normalized_rgba: bytes,
        placement: Placement,
        master_input: _HelmetTextureMasterInput | None,
    ) -> tuple[_HelmetTextureMasterDraft | None, bool]:
        """Return a composed original→contain→placement draft and ownership flag."""

        existing = self._texture_master_draft
        if master_input is None and existing is None:
            return None, False
        if master_input is not None:
            if master_input.private_snapshot:
                if master_input.source_sha256 is None:
                    raise ValueError("Private helmet-logo source hash is missing.")
                snapshot = master_input.source_image
                source_sha256 = master_input.source_sha256
            else:
                snapshot, source_sha256 = snapshot_texture_master_source(
                    master_input.source_image,
                    self._preview_path(f"master-{uuid4().hex}.source"),
                )
            source_width = master_input.source_width
            source_height = master_input.source_height
            source_resample = master_input.source_resample
            pipeline = dict(master_input.pipeline)
            owns_new_snapshot = True
        else:
            assert existing is not None
            snapshot = existing.source_image
            source_sha256 = existing.source_sha256
            source_width = existing.source_width
            source_height = existing.source_height
            source_resample = existing.source_resample
            pipeline = dict(existing.pipeline)
            owns_new_snapshot = False
        transform = compose_contained_master_transform(
            source_width,
            source_height,
            normalized_rgba,
            placement,
            resample=source_resample,
        )
        editor_transform = self._placement_editor_transform(
            placement, pipeline
        )
        native_baseline_png = None
        native_canvas_edited = False
        if master_input is None and existing is not None:
            native_baseline_png = existing.native_baseline_png
            native_canvas_edited = existing.native_canvas_edited
            if native_canvas_edited:
                editor_transform.update({
                    "native_canvas_edit": dict(
                        existing.editor_transform.get("native_canvas_edit", {})
                    ),
                    "native_canvas_edit_revision": int(
                        existing.editor_transform.get(
                            "native_canvas_edit_revision", 1
                        )
                    ),
                    "subsequent_placement_captured_by_final_native_delta": True,
                })
        return (
            _HelmetTextureMasterDraft(
                source_image=snapshot,
                source_sha256=source_sha256,
                source_width=source_width,
                source_height=source_height,
                source_resample=source_resample,
                pipeline=pipeline,
                transform=transform,
                editor_transform=editor_transform,
                native_baseline_png=native_baseline_png,
                native_canvas_edited=native_canvas_edited,
            ),
            owns_new_snapshot,
        )

    def _install_texture_master_draft(
        self, draft: _HelmetTextureMasterDraft, *, owns_new_snapshot: bool
    ) -> None:
        previous = self._texture_master_draft
        if owns_new_snapshot and previous is not None:
            self._delete_texture_master_files(previous)
        self._texture_master_draft = draft
        self._texture_master_game_source = self._current_game_source_identity()

    def _attach_native_baseline(
        self, draft: _HelmetTextureMasterDraft, native: Path
    ) -> _HelmetTextureMasterDraft:
        if draft.native_baseline_png is not None:
            return draft
        baseline, _digest = snapshot_texture_master_source(
            native, self._preview_path(f"master-{uuid4().hex}.native.png")
        )
        if draft.pipeline.get("import_mode") == "retail-literal-crest":
            from mod_editor.core.errors import ValidationError
            from mod_editor.core.image_fit import fit_image

            expected = fit_image(
                draft.source_image, self._WIDTH, self._HEIGHT, mode="contain"
            )
            compiled = fit_image(
                baseline, self._WIDTH, self._HEIGHT, mode="scale"
            )
            if expected.rgba != compiled.rgba:
                baseline.unlink(missing_ok=True)
                raise ValidationError(
                    "The image changed while Mod Studio was preparing its native "
                    "crest. Import it again; the inconsistent master was not kept."
                )
        return replace(draft, native_baseline_png=baseline)

    def _prepare_retail_texture_master_draft(
        self, source: Path, probe: object
    ) -> _HelmetTextureMasterDraft:
        source_width = int(getattr(probe, "source_width"))
        source_height = int(getattr(probe, "source_height"))
        transform = texture_master_fit_transform(
            source_width,
            source_height,
            self._WIDTH,
            self._HEIGHT,
            mode="contain",
            resample="lanczos",
        )
        snapshot, source_sha256 = snapshot_texture_master_source(
            source, self._preview_path(f"master-{uuid4().hex}.source")
        )
        pipeline = {
            "import_mode": "retail-literal-crest",
            "normalization": {
                "action": str(getattr(probe, "action")),
                "canvas_height": self._HEIGHT,
                "canvas_width": self._WIDTH,
                "fit_mode": "contain",
                "padded_x": int(getattr(probe, "padded_x")),
                "padded_y": int(getattr(probe, "padded_y")),
                "resample": "lanczos",
                "source_height": source_height,
                "source_width": source_width,
            },
        }
        editor_transform = {
            "canvas_height": self._HEIGHT,
            "canvas_width": self._WIDTH,
            "center_x": transform.center_x,
            "center_y": transform.center_y,
            "coordinate_space": "native-texture-pixels",
            "height": transform.height,
            "operation": "apf-retail-crest-contain",
            "pipeline": pipeline,
            "resample": "lanczos",
            "rotation_degrees": 0.0,
            "width": transform.width,
        }
        return _HelmetTextureMasterDraft(
            snapshot,
            source_sha256,
            source_width,
            source_height,
            "lanczos",
            pipeline,
            transform,
            editor_transform,
        )

    def _save_authoring_master(self) -> None:
        reason = str(self.master_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot save authoring master yet",
                reason
                + "\n\nFix: load APF → import/place a crest with an authoring "
                "draft → Save master.",
            )
            return
        draft = self._texture_master_draft
        save = getattr(self.facade, "save_helmet_crest_authoring_master", None)
        if draft is None or not callable(save):
            QMessageBox.information(
                self,
                "Import a logo first",
                "Import and place external artwork in this session before saving "
                "its full-resolution authoring master. Existing project files "
                "retain the exact native 512×512 PNG only.",
            )
            return
        choice, accepted = QInputDialog.getItem(
            self,
            "Authoring preview size",
            "Render directly from the preserved full-resolution source at:",
            ("4× (recommended)", "2×"),
            0,
            False,
        )
        if not accepted:
            return
        scale = 4 if str(choice).startswith("4") else 2
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Save high-resolution helmet-logo authoring master",
            str(Path.home() / "apf-helmet-logo.2ktexmaster"),
            "2K texture authoring master (*.2ktexmaster)",
        )
        if not destination:
            return
        output = Path(destination)
        if output.suffix.casefold() != ".2ktexmaster":
            output = output.with_suffix(".2ktexmaster")

        self.run_task(
            "Saving high-resolution helmet-logo authoring master",
            lambda progress: save(
                source_image=draft.source_image,
                source_sha256=draft.source_sha256,
                destination=output,
                transform=draft.transform,
                editor_transform=draft.editor_transform,
                high_resolution_scale=scale,
                native_baseline_png=(
                    draft.native_baseline_png
                    if draft.native_canvas_edited
                    else None
                ),
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Authoring master saved",
                f"Saved to:\n{Path(str(result))}\n\n"
                "The 2×/4× image is an authoring preview rendered from your "
                "preserved source. The game build still uses the exact native "
                "512×512 semantic mask; no RPCS3 pack was created.",
            ),
            True,
        )

    @staticmethod
    def _coverage_text(value: float) -> str:
        return f"{value:.0%}" if value in {0.0, 1.0} else f"{value:.1%}"

    def _coverage_changed(self, *_args: object) -> None:
        self._refresh_logo_ownership()
        full_shell = self._selected_profile() == FULL_SHELL_CREST_PROFILE
        self.fit_visible_mask.setEnabled(False)
        self.coverage_warning.setVisible(full_shell)
        self.import_mode_label.setVisible(full_shell)
        self.import_mode.setVisible(full_shell)
        ready = bool(self.facade.source_ready)
        self.import_mode.setEnabled(ready and full_shell)
        # Never silent-gray: Place stays clickable; disableReason teaches retail wall.
        place_tip = (
            "For Full-shell coverage: drag the logo on a labeled front/crown/rear "
            "canvas, then adjust width, height, and rotation before staging."
            if ready and full_shell
            else (
                "Select Full-shell coverage first, then Place on helmet. "
                "Retail side-decal profile does not use placement."
                if ready
                else "Load your APF game first, then choose Full-shell and Place."
            )
        )
        self.place_button.setEnabled(True)
        self.place_button.setToolTip(place_tip)
        self.place_button.setProperty(
            "disableReason",
            "" if (ready and full_shell) else place_tip,
        )
        if not full_shell and self.fit_visible_mask.isChecked():
            self.fit_visible_mask.blockSignals(True)
            self.fit_visible_mask.setChecked(False)
            self.fit_visible_mask.blockSignals(False)
        if self._staged_png is not None:
            # Keep tooltips/disableReason in sync via set_context (never silent-gray).
            self.set_context()
            profile_ready = self._staged_profile == self._selected_profile()
            if not profile_ready:
                self.path_note.setText(
                    "Helmet coverage changed. Import or drop the logo again so "
                    "Mod Studio can validate/convert it for this profile before Build."
                )

    def _commit_design(self, path: Path, *, remember_source: bool = True) -> bool:
        """Stage through the shareable session; retain a fake-facade test seam."""

        if remember_source:
            self._source_staged_png = Path(path)
        replace = getattr(self.facade, "replace_helmet_crest_design", None)
        if not callable(replace):
            self._staged_png = Path(path)
            self._staged_profile = self._selected_profile()
            self.set_context()
            return True
        crest = self.selected_crest()
        try:
            modification = replace(
                Path(path),
                profile=self._selected_profile(),
                crest_asset_index=int(crest.asset_index),
                crest_outer_entry_index=int(crest.outer_entry_index),
                fit_visible_mask=bool(self.fit_visible_mask.isChecked()),
            )
        except Exception as exc:  # facade/session errors are user-correctable
            QMessageBox.information(
                self,
                "Could not stage helmet crest",
                str(exc),
            )
            return False
        self._staged_png = Path(modification.replacement_path)
        self._staged_profile = self._selected_profile()
        self.set_context()
        self.modifiedChanged.emit()
        return True

    def stage_image(self, path: Path) -> None:
        """Stage one user image exactly as a drop onto the preview would.

        Public because a hand-off from the asset browser has to finish the
        action the user already started there, not just change page.
        """

        self._stage_path(path)

    def focus_outer_entry(self, outer_entry_index: int) -> bool:
        """Select the crest package stored at one outer archive entry.

        This is how a ``logo_l0`` / ``logo_l1`` row handed over from the asset
        browser lands on the right team: the browser knows only the archive
        location, and the picker already carries it on every slot.
        """

        self._populate_slots()
        for index in range(self.slot.count()):
            slot = self.slot.itemData(index)
            if getattr(slot, "outer_entry_index", None) == outer_entry_index:
                self.slot.setCurrentIndex(index)
                return True
        return False

    def _populate_slots(self) -> None:
        """Offer every crest package the loaded game carries, not just the teams.

        The picker is built before a game is loaded, so it starts as the
        twenty-four built-in teams -- the only rows knowable without reading a
        disc.  Once a source is ready the archive itself is asked, which adds the
        game's other ninety-four logo packages: real crest slots with their own
        art, catalogued by the same runtime aggregate that already declares 118,
        and writable by the same writer.  A modder wanting more helmet art was
        previously held to twenty-four by this list alone.
        """

        if self._slots_populated:
            return
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return
        try:
            slots = crest_slots(Path(index_0a))
        except Exception:  # noqa: BLE001 - a picker must never break loading a game
            return
        if not slots:
            return
        previous = self.slot.currentData()
        self.slot.blockSignals(True)
        self.slot.clear()
        for slot in slots:
            self.slot.addItem(slot.label, slot)
        restored = -1
        if previous is not None:
            restored = next(
                (index for index in range(self.slot.count())
                 if self.slot.itemData(index).asset_index == previous.asset_index),
                -1,
            )
        self.slot.setCurrentIndex(restored if restored >= 0 else 0)
        self.slot.blockSignals(False)
        self._slots_populated = True

    def set_context(self) -> None:
        ready = self.facade.source_ready
        current_game_source = self._current_game_source_identity()
        if (
            self._texture_master_game_source is not None
            and self._texture_master_game_source != current_game_source
        ):
            self._clear_texture_master_draft()
        if ready:
            self._populate_slots()
        self._refresh_logo_ownership()
        session = getattr(self.facade, "session", None)
        modification = (
            session.modification(HELMET_CREST_DESIGN_EDIT_ID)
            if session is not None and hasattr(session, "modification")
            else None
        )
        if modification is not None:
            wanted_asset_index = int(
                modification.metadata.get("crest_asset_index", -1)
            )
            wanted_slot = next(
                (
                    index
                    for index in range(self.slot.count())
                    if getattr(self.slot.itemData(index), "asset_index", -2)
                    == wanted_asset_index
                ),
                -1,
            )
            if wanted_slot >= 0 and wanted_slot != self.slot.currentIndex():
                self.slot.blockSignals(True)
                self.slot.setCurrentIndex(wanted_slot)
                self.slot.blockSignals(False)
            wanted_profile = str(
                modification.metadata.get("profile", RETAIL_CREST_PROFILE)
            )
            wanted_index = self.coverage.findData(wanted_profile)
            if wanted_index >= 0 and wanted_index != self.coverage.currentIndex():
                self.coverage.blockSignals(True)
                self.coverage.setCurrentIndex(wanted_index)
                self.coverage.blockSignals(False)
            wanted_fit = bool(modification.metadata.get("fit_visible_mask", False))
            if wanted_fit != self.fit_visible_mask.isChecked():
                self.fit_visible_mask.blockSignals(True)
                self.fit_visible_mask.setChecked(wanted_fit)
                self.fit_visible_mask.blockSignals(False)
            self._staged_png = Path(modification.replacement_path)
            self._staged_profile = wanted_profile
            if self._source_staged_png is None:
                self._source_staged_png = self._staged_png
        staged = self._staged_png is not None
        self.slot.setEnabled(ready)
        self.coverage.setEnabled(ready)
        full_shell = self._selected_profile() == FULL_SHELL_CREST_PROFILE
        self.fit_visible_mask.setEnabled(False)
        self.coverage_warning.setVisible(full_shell)
        self.import_mode_label.setVisible(full_shell)
        self.import_mode.setVisible(full_shell)
        # Place/import-mode: stay clickable; explain when not full-shell or unloaded.
        place_tip = (
            "For Full-shell coverage: drag the logo on a labeled front/crown/rear "
            "canvas, then adjust width, height, and rotation before staging."
            if ready and full_shell
            else (
                "Select Full-shell coverage first, then Place on helmet. "
                "Retail side-decal profile does not use placement."
                if ready
                else "Load your APF game first, then choose Full-shell and Place."
            )
        )
        self.import_mode.setEnabled(ready)
        self.place_button.setEnabled(True)
        self.place_button.setToolTip(place_tip)
        self.place_button.setProperty(
            "disableReason",
            "" if (ready and full_shell) else place_tip,
        )
        # Never silent-gray: Export/Replace/Build/Revert stay clickable + explain.
        load_tip = (
            "Load your APF game first (0A). Team Logo export/replace needs a "
            "source. Click still explains — buttons stay clickable."
        )
        replace_tip = (
            "Choose ordinary artwork or an advanced APF weight mask according "
            "to Full-shell import. Normal artwork is palette-converted and "
            "previewed before the front/crown/rear placement canvas opens."
            if full_shell and ready
            else (
                "Choose an edited image; Retail keeps the normal contain/resize flow."
                if ready
                else load_tip
            )
        )
        profile_ready = self._staged_profile == self._selected_profile()
        can_build = bool(ready and staged and profile_ready)
        if can_build:
            build_tip = (
                "Copy your 0A and write this crest into the selected uniform_logo_NN "
                "package and its linked frontend/Team Select logo-cache index through "
                "the offline-proved writers. The separate selector-slot-6 wordmark "
                "is not changed. Full-shell also writes the shared shell-atlas route; "
                "no Xenia patch or default.xex edit is created. Changed-logo runtime "
                "consumption remains unproved."
            )
            build_block = ""
        elif not ready:
            build_tip = build_block = load_tip
        elif not staged:
            build_tip = build_block = (
                "Stage a crest first (Replace or drop a PNG), then Build a "
                "verified copied 0A. Click still explains this."
            )
        else:
            build_tip = build_block = (
                "Helmet coverage/profile changed. Re-import or drop the logo "
                "again so it matches the selected profile before Build."
            )
        export_tip = (
            "Export the current source-derived 512×512 RGBA crest PNG from your game."
            if ready
            else load_tip
        )
        revert_tip = (
            "Discard the staged replacement PNG and show your original crest again."
            if staged
            else "Nothing to revert—no replacement is staged."
        )
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.revert_button.setEnabled(True)
        self.export_button.setToolTip(export_tip)
        self.replace_button.setToolTip(replace_tip)
        self.build_button.setToolTip(build_tip)
        self.revert_button.setToolTip(revert_tip)
        self.export_button.setProperty("disableReason", "" if ready else load_tip)
        self.export_layers_button.setEnabled(True)
        self.export_layers_button.setToolTip(
            "Save this crest's two region-mask layers as separate PNGs. "
            "logo_l0 carries regions 0-2 and logo_l1 regions 3-5; 79 of the "
            "118 crest packages use both."
            if ready
            else load_tip
        )
        self.export_layers_button.setProperty(
            "disableReason", "" if ready else load_tip
        )
        self.replace_layers_button.setEnabled(True)
        self.replace_layers_button.setToolTip(
            "Import an edited logo_l0 and logo_l1 together. Use this to bring "
            "back what Export both layers saved; a single image goes through "
            "Replace PNG instead, which clears logo_l1 for you."
            if ready
            else load_tip
        )
        self.replace_layers_button.setProperty(
            "disableReason", "" if ready else load_tip
        )
        self.replace_button.setProperty("disableReason", "" if ready else load_tip)
        self.build_button.setProperty("disableReason", build_block)
        self.revert_button.setProperty(
            "disableReason", "" if staged else revert_tip
        )
        can_master = bool(
            ready
            and staged
            and profile_ready
            and self._texture_master_draft is not None
            and callable(
                getattr(self.facade, "save_helmet_crest_authoring_master", None)
            )
        )
        self.master_button.setEnabled(True)
        master_tip = (
            "After an external logo import, save the exact original artwork, "
            "the final X/Y, independent width/height, rotation and palette/region "
            "pipeline, the exact 512×512 native semantic mask, and a direct 2×/4× "
            "master render. This is not an RPCS3 pack and does not change the "
            "game's native texture resolution."
            if can_master
            else (
                "Stage a crest with an authoring master draft first, then save. "
                "Click still explains — button stays clickable."
                if ready
                else load_tip
            )
        )
        self.master_button.setToolTip(master_tip)
        self.master_button.setProperty(
            "disableReason", "" if can_master else master_tip
        )
        self.preview.setAcceptDrops(ready)
        if staged and ready:
            self.status.setText("● Staged" if profile_ready else "△ Re-import needed")
            color = "#39d98a"
        elif ready:
            self.status.setText(_status_text(ApfStatus.EDITABLE))
            color = "#39d98a"
        else:
            self.status.setText("○ Not loaded")
            color = "#8795aa"
        self.status.setStyleSheet(f"color: {color}; border-color: {color};")

        if not ready:
            self.preview.set_message(
                "Team crest + linked Team Select cache · 512×512 RGBA PNG\n"
                "Load your game to see the original."
            )
            self.path_note.setText(
                "No game loaded yet — preview, export, and Replace unlock once "
                "your source is recognized.\n\n" + START_HERE_HINT
            )
            return
        if staged:
            self.preview.set_image(self._staged_png)
            coverage_detail = ""
            if modification is not None:
                before = float(
                    modification.metadata.get("source_horizontal_coverage", 1.0)
                )
                after = float(
                    modification.metadata.get("output_horizontal_coverage", before)
                )
                coverage_detail = (
                    " Visible horizontal mask coverage: "
                    f"{self._coverage_text(before)} → "
                    f"{self._coverage_text(after)}."
                )
            self.path_note.setText(
                "Current preview: your staged 512×512 RGBA replacement. It is "
                "included in shareable projects and the main complete-game Build; "
                "your source stays untouched." + coverage_detail
            )
            return
        self.preview.set_loading("Decoding the original crest from your game…")
        self.path_note.setText(
            "Current preview: original crest decoded from your own game (read-only)."
        )
        crest_token = getattr(self, "_preview_token", 0)

        def _crest_preview_watchdog() -> None:
            if getattr(self, "_preview_token", 0) != crest_token:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                "Team crest: preview still preparing after 45s. "
                "Re-select the logo slot or Export original PNG."
            )

        QTimer.singleShot(45_000, _crest_preview_watchdog)
        self.run_task(
            "Decoding team-logo crest",
            self._decode_source_operation,
            self._apply_preview,
            False,
        )

    def _writer_module(self) -> Any:
        root = Path(__file__).resolve().parents[2]
        for candidate in (str(root), str(root / "tools")):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        import apf_logo_patch  # noqa: E402 - tools/ writer added to sys.path above

        return apf_logo_patch

    def _preview_path(self, name: str) -> Path:
        if self._preview_dir is None:
            self._preview_dir = Path(tempfile.mkdtemp(prefix="apf-team-logo-"))
        return self._preview_dir / name

    def _declared_sibling_packs(self, index_path: Path) -> tuple[str, ...]:
        """The pack names this volume declares, other than the index itself."""

        self._writer_module()  # puts tools/ on sys.path for apf_outer
        import apf_outer  # noqa: E402

        archive = apf_outer.parse_archive(index_path)
        return tuple(
            pack.name for pack in archive.packs if pack.name != index_path.name
        )

    def _decode_source_operation(
        self, progress: Callable[[str, int, int], None]
    ) -> Path:
        source = self.facade.source
        if source is None:
            raise RuntimeError("Load your APF 2K8 game first.")
        index_path = Path(source.index_0a)
        progress("Reading the read-only team-logo crest", 0, 0)
        writer = self._writer_module()
        import apf_inner  # noqa: E402 - resolved once the writer added tools/
        import apf_outer  # noqa: E402
        from PIL import Image

        archive = apf_outer.parse_archive(index_path)
        entry = archive.entries[writer.ENTRY_INDEX]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            blocks = [
                apf_inner.decode_block(reader, record, index, 1 << 30)
                for index in range(record.block_count)
            ]
        target = record.files[writer.FILE_INDEX]
        dram_part, vram_part = target.parts[0], target.parts[1]
        dram = blocks[dram_part.block_index][
            dram_part.offset : dram_part.offset + dram_part.length
        ]
        metadata = apf_inner.parse_txtr_metadata(dram)
        base = blocks[vram_part.block_index][
            vram_part.offset : vram_part.offset + writer.BASE_LEN
        ]
        rgba = writer.decode_4444_base(metadata, base)
        output = self._preview_path("team_logo_source.png")
        Image.frombytes("RGBA", (writer.WIDTH, writer.HEIGHT), rgba).save(output)
        return output

    def _apply_preview(self, result: object) -> None:
        # A stage (drop/choose) may have won the race while the decode ran; keep
        # the staged preview rather than overwriting it with the original.
        if self._staged_png is not None:
            return
        self.preview.set_image(Path(str(result)))

    def _export_original(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export team logo yet",
                reason + "\n\nFix: File → Load game, then Export original PNG.",
            )
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Export source-derived team-logo PNG",
            str(Path.home() / "apf-team-logo.png"),
            "RGBA PNG (*.png)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".png")
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            decoded = self._decode_source_operation(progress)
            return _copy_new(decoded, path)

        self.run_task(
            "Exporting team-logo PNG",
            operation,
            lambda result: QMessageBox.information(
                self, "PNG exported", f"Saved to:\n{Path(str(result))}"
            ),
            True,
        )

    def _export_both_layers(self) -> None:
        """Save this crest's two region-mask layers as separate PNGs.

        A crest is six region masks: ``logo_l0`` carries regions 0-2 in its
        R/G/B and ``logo_l1`` carries regions 3-5, and 79 of the game's 118
        packages use both. Exporting one flattened picture hid that, so anyone
        wanting to edit a real crest had no way to see what they were editing.
        """

        reason = str(self.export_layers_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self, "Cannot export the crest layers yet", reason
            )
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose a folder for this crest's two layers",
            str(Path.home()),
        )
        if not directory:
            return
        crest = self.selected_crest()
        stem = f"uniform_logo_{crest.asset_index:02d}"
        folder = Path(directory)
        targets = (folder / f"{stem}_logo_l0.png", folder / f"{stem}_logo_l1.png")
        existing = [str(path) for path in targets if path.exists()]
        if existing:
            QMessageBox.information(
                self,
                "Choose an empty folder",
                "Exports never overwrite an existing file. These already "
                "exist:\n\n" + "\n".join(existing),
            )
            return
        source = self.facade.source
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return

        def operation(progress: Callable[[str, int, int], None]) -> tuple[Path, Path]:
            from PIL import Image

            progress("Decoding both crest layers", 0, 2)
            writer = self._writer_module()
            rgba_l0, rgba_l1 = writer.read_logo_layers(
                Path(index_0a), crest.outer_entry_index
            )
            for step, (rgba, target) in enumerate(
                zip((rgba_l0, rgba_l1), targets), start=1
            ):
                Image.frombytes(
                    "RGBA", (self._WIDTH, self._HEIGHT), bytes(rgba)
                ).save(target)
                progress("Writing crest layer PNGs", step, 2)
            return targets

        def done(result: object) -> None:
            first, second = result  # type: ignore[misc]
            QMessageBox.information(
                self,
                "Crest layers exported",
                f"Saved:\n{first}\n{second}\n\n"
                "These are region masks, not painted pictures: R, G and B each "
                "select a region the game fills with one flat colour. logo_l0 "
                "holds regions 0-2 and logo_l1 holds regions 3-5.\n\n"
                "Dropping a single image here writes it to logo_l0 and clears "
                "logo_l1, so your mark is drawn exactly once. Edit these two "
                "files and bring them back with Replace both layers to author "
                "the whole crest.",
            )

        self.run_task("Exporting both crest layers", operation, done, True)

    def _choose_both_layers(self) -> None:
        """Stage an edited logo_l0 and logo_l1 together.

        Export both layers has always been able to take a crest apart; without
        this the only way to put one back together was
        ``tools/apf_logo_patch.py --png --png-l1`` in a terminal, so the 79
        packages that use both layers were effectively read-only in the app.
        """

        reason = str(
            self.replace_layers_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace the crest layers yet",
                reason
                + "\n\nFix: File → Load game, then Export both layers, edit "
                "them, and bring both back here.",
            )
            return
        if self._selected_profile() == FULL_SHELL_CREST_PROFILE:
            QMessageBox.information(
                self,
                "Two-layer import is a retail-decal workflow",
                "The whole-shell profile derives its own art from one image "
                "before it is placed on the shell, so it has no second layer "
                "to import.\n\nFix: switch coverage to the retail side decal, "
                "then import both layers.",
            )
            return
        image_filter = (
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)"
        )
        base_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Step 1 of 2 — choose the logo_l0 image (crest regions 0-2)",
            str(Path.home()),
            image_filter,
        )
        if not base_path:
            return
        detail_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Step 2 of 2 — choose the logo_l1 image (crest regions 3-5)",
            str(Path(base_path).parent),
            image_filter,
        )
        if not detail_path:
            return
        if Path(base_path) == Path(detail_path):
            QMessageBox.information(
                self,
                "Choose two different images",
                "The layers carry different regions of one crest and are not "
                "interchangeable. Writing the same mask to both draws your "
                "mark once per region.\n\nFix: to use a single image, cancel "
                "and use Replace PNG — that clears logo_l1 for you.",
            )
            return
        # The detail layer is prepared first: staging the base layer commits it
        # to the project, and a detail layer that cannot be read should not
        # leave a half-applied crest behind.
        staged_detail = self._prepare_detail_layer(Path(detail_path))
        if staged_detail is None:
            return
        if not self._stage_path(Path(base_path), keep_detail_layer=True):
            return
        if self._staged_png is None:
            return
        self._staged_detail_png = staged_detail
        self.set_context()
        QMessageBox.information(
            self,
            "Both crest layers staged",
            f"logo_l0: {Path(base_path).name}\n"
            f"logo_l1: {Path(detail_path).name}\n\n"
            "Build copied 0A writes both layers into the selected "
            "uniform_logo_NN package and the matching logo-cache slot.\n\n"
            "The preview shows logo_l0; logo_l1 has no standalone appearance "
            "because its channels select regions the game fills with flat "
            "colours.",
        )

    def _prepare_detail_layer(self, path: Path) -> Path | None:
        """Validate and size one logo_l1 image, returning a private staged PNG.

        Returns ``None`` when the file cannot be used; the user has already
        been told why.
        """

        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_to_png

        staged = self._preview_path(f"team_logo_l1-{uuid4().hex}.png")
        try:
            # 'contain' matches the base layer: a region mask must keep its
            # whole shape, and padding with transparency selects no region.
            fit_to_png(path, self._WIDTH, self._HEIGHT, staged, mode="contain")
        except ValidationError as exc:
            QMessageBox.information(
                self,
                "That detail layer could not be read as an image",
                f"{exc}\n\nFix: choose a {_plain_image_formats()} image for "
                "logo_l1. Any size works — the editor resizes it for you.",
            )
            return None
        except OSError as exc:
            QMessageBox.information(
                self, "Could not stage the detail layer", str(exc)
            )
            return None
        return staged

    def _choose_replacement(self) -> None:
        reason = str(self.replace_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace team logo yet",
                reason
                + "\n\nFix: File → Load game, then Replace or drop a crest PNG. "
                "Build writes a copied 0A — never mutates your original.",
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose a team-logo image (any size — {self._WIDTH}×{self._HEIGHT} exact, "
            "or it can be resized for you)",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)",
        )
        if path:
            self._stage_path(Path(path))

    def _edit_in_place(self) -> None:
        """Draw on the crest at its exact size, then stage the result.

        The pixels come from whatever is current -- a staged replacement if one
        exists, otherwise the crest decoded out of the user's own game -- so a
        second edit continues from where the first finished rather than
        starting over from retail.
        """
        if not self.facade.source_ready:
            QMessageBox.information(
                self, "Load your game first",
                "Open your APF 2K8 disc or game folder before editing the crest.",
            )
            return
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_image
        from mod_editor.gui.texture_editor import edit_texture
        from PIL import Image

        source = self._staged_png
        if source is None:
            try:
                source = self._decode_source_operation(lambda *_a: None)
            except Exception as exc:  # noqa: BLE001 - decode paths raise broadly
                QMessageBox.information(
                    self, "Could not open the crest",
                    f"The current crest could not be decoded for editing.\n\n{exc}",
                )
                return
        try:
            pixels = fit_image(Path(str(source)), self._WIDTH, self._HEIGHT).rgba
        except ValidationError as exc:
            QMessageBox.information(self, "Could not open the crest", str(exc))
            return

        edited = edit_texture(
            pixels, self._WIDTH, self._HEIGHT, "team-logo crest", self
        )
        if edited is None:
            return
        staged = self._preview_path("team_logo_edited.png")
        Image.frombytes(
            "RGBA", (edited.width, edited.height), edited.rgba
        ).save(staged)
        if self._selected_profile() == FULL_SHELL_CREST_PROFILE:
            try:
                validate_region_mask_rgba(edited.rgba)
            except HelmetLogoRegionError as exc:
                QMessageBox.information(
                    self,
                    "APF region mask required",
                    "Full-shell Edit accepts semantic region weights only. Use "
                    "Normal logo import to convert painted artwork first.\n\n"
                    f"{exc}",
                )
                return
        existing_master = self._texture_master_draft
        changed_pixels = sum(
            pixels[offset:offset + 4] != edited.rgba[offset:offset + 4]
            for offset in range(0, len(pixels), 4)
        )
        if self._commit_design(staged):
            self._placement_source_rgba = None
            self._placement_state = None
            if existing_master is not None:
                revision = int(
                    existing_master.editor_transform.get(
                        "native_canvas_edit_revision", 0
                    )
                ) + 1
                editor_transform = dict(existing_master.editor_transform)
                editor_transform.update({
                    "native_canvas_edit": {
                        "changed_pixel_count_from_previous_canvas": changed_pixels,
                        "operation": "native-canvas-raster-edit-after-import",
                        "preview_composition": (
                            "nearest-native-pixel-edits-over-direct-master-render"
                        ),
                    },
                    "native_canvas_edit_revision": revision,
                })
                self._texture_master_draft = replace(
                    existing_master,
                    editor_transform=editor_transform,
                    native_canvas_edited=True,
                )
                self.set_context()

    def _place_mask_rgba(
        self,
        source_rgba: bytes,
        *,
        auto_fit: bool,
        initial_placement: Placement | None = None,
        master_input: _HelmetTextureMasterInput | None = None,
    ) -> bool:
        """Edit from one stable import basis, never a repeatedly flattened copy."""

        edit = place_helmet_logo(
            source_rgba,
            auto_fit=auto_fit,
            initial_placement=initial_placement,
            parent=self,
        )
        if edit is None:
            return False
        candidate_master: _HelmetTextureMasterDraft | None = None
        owns_new_snapshot = False
        try:
            from PIL import Image

            staged = self._preview_path("team_logo_placed.png")
            Image.frombytes("RGBA", (self._WIDTH, self._HEIGHT), edit.rgba).save(staged)
            candidate_master, owns_new_snapshot = (
                self._prepare_placed_texture_master_draft(
                    source_rgba, edit.placement, master_input
                )
            )
            if candidate_master is not None and owns_new_snapshot:
                candidate_master = self._attach_native_baseline(
                    candidate_master, staged
                )
        except Exception as exc:  # noqa: BLE001 - Pillow reports format details
            if owns_new_snapshot and candidate_master is not None:
                self._delete_texture_master_files(candidate_master)
            QMessageBox.information(
                self,
                "Could not stage helmet placement",
                "The exact 512×512 placement or its full-resolution source "
                f"could not be preserved.\n\n{exc}",
            )
            return False

        # The placement output is already the semantic pre-guard 512x512
        # design. Session-level one-click fitting would erase the user's X/Y,
        # independent width/height, and rotation choices, so disable it before
        # crossing the normal staging boundary.
        self.fit_visible_mask.blockSignals(True)
        self.fit_visible_mask.setChecked(False)
        self.fit_visible_mask.blockSignals(False)
        if not self._commit_design(staged):
            if owns_new_snapshot and candidate_master is not None:
                self._delete_texture_master_files(candidate_master)
            return False
        self._placement_source_rgba = bytes(source_rgba)
        self._placement_state = edit.placement
        if candidate_master is not None:
            self._install_texture_master_draft(
                candidate_master, owns_new_snapshot=owns_new_snapshot
            )
            self.set_context()
        return True

    def _place_region_mask_path(
        self,
        path: Path,
        *,
        auto_fit: bool,
        preserve_external_master: bool = True,
    ) -> bool:
        """Normalize and strictly validate an advanced semantic mask."""

        private_source: Path | None = None
        source_sha256: str | None = None
        if preserve_external_master:
            try:
                private_source, source_sha256 = snapshot_texture_master_source(
                    Path(path),
                    self._preview_path(f"master-input-{uuid4().hex}.source.png"),
                )
            except Exception as exc:
                QMessageBox.information(
                    self, "Could not preserve region-mask source", str(exc)
                )
                return False
        try:
            imported = import_mask_nearest(private_source or Path(path))
        except HelmetLogoPlacementError as exc:
            if private_source is not None:
                private_source.unlink(missing_ok=True)
            QMessageBox.information(
                self,
                "Could not place helmet logo",
                str(exc),
            )
            return False
        try:
            validate_region_mask_rgba(imported.rgba)
        except HelmetLogoRegionError as exc:
            if private_source is not None:
                private_source.unlink(missing_ok=True)
            QMessageBox.information(
                self,
                "Invalid APF region mask",
                str(exc)
                + "\n\nUse Normal logo import for ordinary painted artwork.",
            )
            return False
        master_input = (
            _HelmetTextureMasterInput(
                source_image=private_source or Path(path),
                source_width=imported.source_width,
                source_height=imported.source_height,
                source_resample="nearest",
                pipeline={
                    "import_mode": REGION_MASK_IMPORT_MODE,
                    "normalization": {
                        "canvas_height": self._HEIGHT,
                        "canvas_width": self._WIDTH,
                        "fit_mode": "contain",
                        "resample": "nearest",
                        "source_height": imported.source_height,
                        "source_width": imported.source_width,
                    },
                    "semantic_conversion": "already-authored exact APF red/green region weights",
                },
                source_sha256=source_sha256,
                private_snapshot=True,
            )
            if preserve_external_master
            else None
        )
        placed = self._place_mask_rgba(
            imported.rgba, auto_fit=auto_fit, master_input=master_input
        )
        if not placed and private_source is not None:
            private_source.unlink(missing_ok=True)
        return placed

    def _place_normal_logo_path(self, path: Path, *, auto_fit: bool) -> bool:
        """Contain normal artwork, confirm its palette mapping, then place its mask."""

        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_image

        private_source: Path | None = None
        try:
            private_source, source_sha256 = snapshot_texture_master_source(
                Path(path),
                self._preview_path(f"master-input-{uuid4().hex}.source.png"),
            )
            normalized = fit_image(
                private_source, self._WIDTH, self._HEIGHT, mode="contain"
            )
        except (ValidationError, OSError) as exc:
            if private_source is not None:
                private_source.unlink(missing_ok=True)
            QMessageBox.information(self, "Could not read normal logo", str(exc))
            return False
        assert private_source is not None
        conversion = convert_normal_logo(normalized.rgba, parent=self)
        if conversion is None:
            private_source.unlink(missing_ok=True)
            return False
        palette = conversion.palette
        master_input = _HelmetTextureMasterInput(
            source_image=private_source,
            source_width=normalized.source_width,
            source_height=normalized.source_height,
            source_resample="bicubic",
            pipeline={
                "import_mode": NORMAL_LOGO_IMPORT_MODE,
                "normalization": {
                    "canvas_height": self._HEIGHT,
                    "canvas_width": self._WIDTH,
                    "fit_mode": "contain",
                    "resample": "lanczos",
                    "source_height": normalized.source_height,
                    "source_width": normalized.source_width,
                },
                "semantic_conversion": {
                    "mapping": conversion.mapping,
                    "palette": {
                        "green_region_rgb": list(palette.green_region),
                        "red_region_rgb": list(palette.red_region),
                        "shell_rgb": list(palette.shell),
                    },
                    "stored_channels": "red/green Xenos 4-bit unit-simplex weights; blue zero",
                },
            },
            source_sha256=source_sha256,
            private_snapshot=True,
        )
        placed = self._place_mask_rgba(
            conversion.mask_rgba,
            auto_fit=auto_fit,
            master_input=master_input,
        )
        if not placed:
            private_source.unlink(missing_ok=True)
        return placed

    def _place_full_shell_path(self, path: Path, *, auto_fit: bool) -> bool:
        if self._selected_import_mode() == REGION_MASK_IMPORT_MODE:
            return self._place_region_mask_path(path, auto_fit=auto_fit)
        return self._place_normal_logo_path(path, auto_fit=auto_fit)

    def _place_current_logo(self) -> None:
        """Reposition the staged design, or start from the decoded retail crest."""

        reason = str(self.place_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot place logo yet",
                reason
                + "\n\nFix: load APF → set coverage to Full-shell → Place on helmet.",
            )
            return
        if (
            not self.facade.source_ready
            or self._selected_profile() != FULL_SHELL_CREST_PROFILE
        ):
            return
        if self._placement_source_rgba is not None:
            self._place_mask_rgba(
                self._placement_source_rgba,
                auto_fit=False,
                initial_placement=self._placement_state,
            )
            return
        source = self._staged_png
        if source is None:
            try:
                source = self._decode_source_operation(lambda *_args: None)
            except Exception as exc:  # noqa: BLE001 - decode paths raise broadly
                QMessageBox.information(
                    self,
                    "Could not open the crest",
                    f"The current crest could not be decoded for placement.\n\n{exc}",
                )
                return
        # A staged/source crest is already an APF region mask regardless of the
        # import mode selected for the next external file.
        self._place_region_mask_path(
            Path(source), auto_fit=False, preserve_external_master=False
        )

    def _stage_path(self, path: Path, *, keep_detail_layer: bool = False) -> bool:
        """Stage an image for the crest, resizing it when it is not exact.

        The crest occupies a fixed byte span, so the writer needs exactly
        512x512 and always will. Refusing anything else was the app's choice,
        not the disc's, and it stopped people at the first step: a logo pulled
        from anywhere is never already that size. Now the wrong size is an
        offer rather than a dead end, and the exact case is untouched -- an
        already-correct PNG is handed to the writer as the user supplied it.

        Returns whether an edit was staged.  Staging one image drops any
        previously staged detail layer, so a single mark is never silently
        combined with the regions of an earlier crest; ``keep_detail_layer``
        is how the two-layer import stages its base half without doing that.
        """
        if not self.facade.source_ready:
            return False
        if not keep_detail_layer:
            self._clear_staged_detail_layer()
        if self._selected_profile() == FULL_SHELL_CREST_PROFILE:
            # Full-shell normal art is converted to semantic weights first;
            # advanced masks are strict-validated. Only then can placement and
            # staging receive a semantic pre-guard PNG.
            self._place_full_shell_path(Path(path), auto_fit=True)
            return self._staged_png is not None
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_image, fit_to_png

        try:
            # 'contain' for a crest: keep the whole shape and pad the
            # difference with transparency. Cropping the sides off an
            # Eagles logo to fill a square is exactly the wrong answer,
            # and this texture already has an alpha channel.
            probe = fit_image(path, self._WIDTH, self._HEIGHT,
                              mode="contain")
        except ValidationError as exc:
            QMessageBox.information(
                self,
                "That file could not be read as an image",
                f"{exc}\n\nFix: choose or drop a {_plain_image_formats()} "
                "image. Any size works -- the editor resizes it for you.",
            )
            return False

        needs_png_conversion = (
            probe.source_format != "PNG" or probe.source_mode != "RGBA"
        )
        if not probe.changed and not needs_png_conversion:
            draft: _HelmetTextureMasterDraft | None = None
            try:
                draft = self._prepare_retail_texture_master_draft(Path(path), probe)
                draft = self._attach_native_baseline(draft, Path(path))
            except Exception as exc:  # user source/disk validation is recoverable
                self._delete_texture_master_files(draft)
                QMessageBox.information(
                    self,
                    "Could not preserve full-resolution source",
                    str(exc),
                )
                return False
            if self._commit_design(Path(path)):
                self._placement_source_rgba = None
                self._placement_state = None
                self._install_texture_master_draft(
                    draft, owns_new_snapshot=True
                )
                self.set_context()
                return True
            self._delete_texture_master_files(draft)
            return False

        # Prepare the exact pixels first, then show them for approval. A
        # modder deciding a crest fit should see the actual result, not a
        # promise, before anything is staged.
        try:
            staged = self._preview_path(f"team_logo_resized-{uuid4().hex}.png")
            result = fit_to_png(path, self._WIDTH, self._HEIGHT, staged,
                                mode="contain")
        except ValidationError as exc:
            QMessageBox.information(
                self,
                "Could not prepare that image",
                f"{exc}\n\nFix: try a different {_plain_image_formats()} "
                "image. No edit was staged.",
            )
            return False
        if not confirm_prepared_slot_image(
            self,
            staged,
            width=self._WIDTH,
            height=self._HEIGHT,
            title="Preview the prepared crest",
            summary_lines=(
                (
                    f"That image is {probe.source_width}×{probe.source_height}. "
                    f"Mod Studio prepared it by: {result.describe()}."
                ),
                "Your original file is not modified — this prepared copy is "
                "staged for this build only.",
            ),
            accept_label="Stage this crest",
        ):
            staged.unlink(missing_ok=True)
            return False
        draft = None
        try:
            draft = self._prepare_retail_texture_master_draft(Path(path), probe)
            draft = self._attach_native_baseline(draft, staged)
        except Exception as exc:  # user source/disk validation is recoverable
            self._delete_texture_master_files(draft)
            QMessageBox.information(
                self,
                "Could not preserve full-resolution source",
                str(exc),
            )
            return False
        if not self._commit_design(staged):
            self._delete_texture_master_files(draft)
            return False
        assert draft is not None
        self._placement_source_rgba = None
        self._placement_state = None
        self._install_texture_master_draft(draft, owns_new_snapshot=True)
        self.set_context()
        return True

    def _clear_staged_detail_layer(self) -> None:
        staged = self._staged_detail_png
        self._staged_detail_png = None
        if staged is not None:
            staged.unlink(missing_ok=True)

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Nothing to revert",
                reason + "\n\nStage a team crest first, then Revert clears it.",
            )
            return
        revert = getattr(self.facade, "revert", None)
        if callable(revert):
            revert(HELMET_CREST_DESIGN_EDIT_ID)
        self._staged_png = None
        self._source_staged_png = None
        self._clear_staged_detail_layer()
        self._placement_source_rgba = None
        self._placement_state = None
        self._clear_texture_master_draft()
        self.set_context()
        self.modifiedChanged.emit()

    def _build_copied_volume(self) -> None:
        reason = str(self.build_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot build team logo copy yet",
                reason
                + "\n\nFix: load APF → Replace/stage a crest → Build a verified "
                "copied 0A. Never mutates your original dump.",
            )
            return
        source = self.facade.source
        if not self.facade.source_ready or source is None or self._staged_png is None:
            return
        if self._staged_profile != self._selected_profile():
            QMessageBox.information(
                self,
                "Re-import for this helmet coverage",
                "The staged crest belongs to the other helmet coverage profile. "
                "Import or drop it again so Mod Studio can validate/convert it "
                "before Build.",
            )
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Choose the new copied 0A volume to create",
            str(Path.home() / "APF-team-logo" / "0A"),
            "APF 0A volume (0A);;All files (*)",
        )
        if not destination:
            return
        out_volume = Path(destination)
        package_manifest = (
            out_volume.parent / f"{out_volume.name}.team_logo_package.json"
        )
        cache_manifest = out_volume.parent / f"{out_volume.name}.team_logo_cache.json"
        cache_verify_manifest = cache_manifest.with_name(
            f"{cache_manifest.stem}.verify.json"
        )
        appearance_replacements = {
            slot: self.facade.custom_team_appearance_value(slot)
            for slot in apf_custom_team_appearance_patch.USER_SLOTS
            if apf_custom_team_appearance_patch.asset_id(slot)
            in self.facade.modified_asset_ids
        }
        appearance_manifest = (
            out_volume.parent / f"{out_volume.name}.custom_team_appearance.json"
            if appearance_replacements
            else None
        )
        crest_profile = self._selected_profile()
        crest_wrap_manifest = (
            out_volume.parent / f"{out_volume.name}.helmet_crest_wrap.json"
            if crest_profile == FULL_SHELL_CREST_PROFILE
            else None
        )
        if (
            out_volume.exists()
            or package_manifest.exists()
            or cache_manifest.exists()
            or cache_verify_manifest.exists()
            or (
                appearance_manifest is not None
                and appearance_manifest.exists()
            )
            or (
                crest_wrap_manifest is not None
                and crest_wrap_manifest.exists()
            )
        ):
            QMessageBox.information(
                self,
                "Choose a new location",
                "The proved writers never overwrite existing files. Pick a folder and "
                "name that do not exist yet, then try again.",
            )
            return
        index_path = Path(source.index_0a)
        crest = self.selected_crest()
        coverage_detail = (
            "\nHelmet coverage: entire helmet shell\n"
            f"Wrap verifier: {crest_wrap_manifest.name}\n"
            + GLOBAL_HELMET_WARNING
            if crest_wrap_manifest is not None
            else "\nHelmet coverage: retail side decal"
        )
        layer_detail = (
            "\nCrest layers: logo_l0 and logo_l1 both written from the two "
            "images you staged"
            if self._staged_detail_png is not None
            else "\nCrest layers: your image goes to logo_l0 and logo_l1 is "
            "cleared, so the mark is drawn exactly once"
        )
        appearance_detail = (
            "\nCustom-team appearance slots: "
            + ", ".join(str(slot) for slot in sorted(appearance_replacements))
            + f"\nAppearance verifier: {appearance_manifest.name}"
            if appearance_manifest is not None
            else "\nCustom-team appearance: no staged slot edits"
        )
        confirm = QMessageBox.question(
            self,
            "Build copied 0A (team logo)?",
            "This copies your entire ~1.1 GB 0A volume to the chosen path and "
            "replaces both sibling layers of the selected team-logo crest in both "
            "places the disc stores "
            f"it: {crest.package_name} (outer {crest.outer_entry_index}) and catalog "
            f"slot {crest.asset_index} in "
            "the prebuilt uniform_logocache aggregate. Both writes go through "
            "offline-proved writers; each byte-diffs the whole copied volume so "
            "only its own fixed extents change, and your source game is never "
            "modified.\n\n"
            "This writes the team-logo edit and any staged Custom Team Appearance "
            "slot listed below into one 0A. Other Mod Studio edits are not included. "
            "Boot it alongside your own unmodified game packs.\n\n"
            "The builder checks free space first and keeps the requested output "
            "name absent until a complete private stage has passed every gate.\n\n"
            f"Source (read-only): {index_path}\n"
            f"New copied 0A: {out_volume}\n"
            f"Manifests: {package_manifest.name}\n"
            f"           {cache_manifest.name}\n"
            f"Verifier:  {cache_verify_manifest.name}\n"
            f"{coverage_detail}\n"
            f"{layer_detail}\n\n"
            f"{appearance_detail}\n\n"
            "The selected uniform_logo_NN package is the helmet-crest source. "
            "The cache is co-written for the other logo surfaces that may read it.\n\n"
            "Proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        staged = self._staged_png
        staged_detail = self._staged_detail_png

        def operation(progress: Callable[[str, int, int], None]) -> dict[str, object]:
            # One Team Logo action through the shared copied-volume builder the
            # facade reuses. Sibling resolution stays
            # a panel seam so this path keeps its declared-sibling behaviour.
            siblings = self._declared_sibling_packs(index_path)
            return build_team_logo_copied_volume(
                index_path,
                staged,
                out_volume,
                package_manifest,
                cache_manifest,
                progress,
                cache_catalog_index=crest.asset_index,
                outer_entry_index=crest.outer_entry_index,
                siblings=siblings,
                appearance_replacements=appearance_replacements or None,
                appearance_manifest=appearance_manifest,
                crest_profile=crest_profile,
                crest_wrap_manifest=crest_wrap_manifest,
                detail_png=staged_detail,
            )

        self.run_task(
            "Building copied 0A (team logo)",
            operation,
            self._build_complete,
            True,
        )

    def _build_complete(self, result: object) -> None:
        report = result if isinstance(result, dict) else {}
        volume = report.get("volume")
        cache_manifest = report.get("cache_manifest")
        cache_verify_manifest = report.get("cache_verify_manifest")
        package_manifest = report.get("package_manifest")
        crest_profile = report.get("crest_profile", RETAIL_CREST_PROFILE)
        crest_wrap_manifest = report.get("crest_wrap_manifest")
        appearance_manifest = report.get("appearance_manifest")
        detail = ""
        if package_manifest is not None:
            try:
                document = json.loads(
                    Path(str(package_manifest)).read_text(encoding="utf-8")
                )
                metrics = document.get("base_data", {}).get("decode_back_metrics", {})
                max_error = metrics.get("maximum_absolute_error")
                if max_error is not None:
                    detail += (
                        f"\n\nDecode-back max per-channel error: {max_error} "
                        "(0 = exact; larger means 4-bit quantization moved a color)."
                    )
            except (OSError, ValueError):
                pass
        try:
            document = json.loads(
                Path(str(cache_manifest)).read_text(encoding="utf-8")
            )
            copied = document.get("copied_volume") or {}
            if copied.get("output_volume_sha256"):
                detail += f"\nCopied 0A sha256: {copied['output_volume_sha256']}"
        except (OSError, ValueError):
            pass
        evidence = (
            f"Cache manifest:\n{cache_manifest}\n"
            f"Independent cache verification:\n{cache_verify_manifest}\n"
        )
        if package_manifest is not None:
            evidence += f"Package manifest:\n{package_manifest}"
        else:
            evidence += (
                "Package manifest: the package-stage evidence copy could not be "
                "written; the copied volume and its cache manifest are unaffected."
            )
        if crest_wrap_manifest is not None:
            evidence += (
                "\nFull-shell helmet-atlas verification:\n"
                f"{crest_wrap_manifest}"
            )
        if appearance_manifest is not None:
            evidence += (
                "\nCustom-team palette/selector verification:\n"
                f"{appearance_manifest}"
            )
        if crest_profile == FULL_SHELL_CREST_PROFILE:
            opening = (
                "The full-shell builder created one new 0A only after every team "
                "package, the selected menu cache, and the shared shell route "
                "compiled and reparsed successfully. Any staged Custom Team "
                "Appearance was composed into that same new volume."
            )
            proof_summary = (
                "The full-shell builder compiled and reparsed all 118 team crest "
                "packages in memory before creating one new 0A. The selected "
                "package contains identical l0/l1 shell atlases; the selected "
                "menu cache keeps the undistorted semantic design; every other "
                "package preserves its retail RGBA mask at the original physical "
                "side-logo placement. The shell route and neutralized old overlay "
                "were independently reopened. No Xenia patch or default.xex edit "
                "was created."
            )
        else:
            opening = (
                "The offline-proved writers copied your 0A and wrote the same crest "
                "into the selected uniform_logo_NN package and the prebuilt "
                "uniform_logocache aggregate, then independently re-read and "
                "verified the cache edit against the whole volume. Any staged "
                "Custom Team Appearance slot was composed into the same 0A and its "
                "ROST was independently reopened and decoded."
            )
            proof_summary = (
                "The three manifests are the evidence chain: the package manifest "
                "covers your game → the intermediate copy, and the cache manifest "
                "covers that copy → this volume. The independent verifier re-parses "
                "all 236 cached logo layers and proves the intended base and packed "
                "mips changed while all other cached content stayed intact."
            )
        QMessageBox.information(
            self,
            "Copied 0A built",
            f"{opening}\n\nCopied 0A:\n"
            f"{volume}\n\n{evidence}{detail}\n\n{proof_summary}"
            + (
                "\n\n" + GLOBAL_HELMET_WARNING
                if crest_profile == FULL_SHELL_CREST_PROFILE
                else ""
            ),
        )


class ApfTextLogoPanel(QFrame):
    """All 206 rectangular selector-slot-6 wordmarks, never helmet crests."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._assets: dict[int, UniformAsset] = {}
        self._preview_token = 0
        self._source_identity: str | None = None
        self._prepare_root: Path | None = None
        self.destroyed.connect(self._cleanup_prepared_wordmarks)
        self.setObjectName("panel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)
        self.preview = ImageDropLabel(
            "Wordmark · 512×128 RGBA PNG\nLoad your game, then choose slot 0..205."
        )
        self.preview.setMinimumSize(420, 150)
        self.preview.setMaximumHeight(210)
        self.preview.pngDropped.connect(self._stage_path)
        layout.addWidget(self.preview, 2)

        content = QVBoxLayout()
        heading = QHBoxLayout()
        title = QLabel("Team/menu wordmark")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)
        content.addLayout(heading)

        selector = QHBoxLayout()
        selector.addWidget(QLabel("Wordmark slot:"))
        self.slot = QSpinBox()
        self.slot.setRange(0, 205)
        self.slot.setPrefix("#")
        self.slot.setAccessibleName("APF wordmark asset index 0 through 205")
        self.slot.setToolTip(
            "Exact selector-slot-6 asset index. Teams may share a physical "
            "wordmark; the owner line lists every current reference."
        )
        self.fit_mode = QComboBox()
        self.fit_mode.addItem("Contain — keep the entire logo", "contain")
        self.fit_mode.addItem("Cover — fill and center-crop", "cover")
        self.fit_mode.addItem("Stretch — force 512×128 (may distort)", "stretch")
        self.fit_mode.setToolTip(
            "Contain is the safe default for long logos. Cover fills all 512×128 "
            "pixels and trims overflow. Stretch forces exact size and may distort. "
            "Transparent pixels are flattened onto the retail opaque-black background."
        )
        selector.addWidget(self.slot)
        selector.addSpacing(8)
        selector.addWidget(QLabel("Import fit:"))
        selector.addWidget(self.fit_mode, 1)
        content.addLayout(selector)

        self.identity = QLabel(
            "uniform_textlogo is a rectangular wordmark. It is not the square "
            "uniform_logo helmet crest and is never squeezed into that texture."
        )
        self.identity.setObjectName("findingText")
        self.identity.setWordWrap(True)
        self.owners = QLabel("Load a game to resolve package ownership.")
        self.owners.setObjectName("metadataText")
        self.owners.setWordWrap(True)
        self.contract = QLabel(
            "512×128 opaque RGBA → tiled BC1/DXT1 · all six mips regenerated · "
            "fixed-allocation IFF/H7A rebuild · included in normal project Build"
        )
        self.contract.setObjectName("contractText")
        self.contract.setWordWrap(True)
        content.addWidget(self.identity)
        content.addWidget(self.owners)
        content.addWidget(self.contract)

        actions = QHBoxLayout()
        self.export_button = QPushButton("Export current PNG…")
        self.export_button.setObjectName("secondaryButton")
        self.import_button = QPushButton("Import logo/image…")
        self.import_button.setObjectName("primaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        # Never silent-gray: stay clickable; explain when source/catalog is not ready.
        self.export_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.export_button.clicked.connect(self._export_current)
        self.import_button.clicked.connect(self._choose_image)
        self.revert_button.clicked.connect(self._revert)
        actions.addWidget(self.export_button)
        actions.addWidget(self.import_button)
        actions.addWidget(self.revert_button)
        actions.addStretch(1)
        content.addLayout(actions)
        content.addStretch(1)
        layout.addLayout(content, 3)

        self.slot.valueChanged.connect(lambda _value: self._selection_changed())
        self.set_context()

    def _cleanup_prepared_wordmarks(self, *_args: object) -> None:
        root = self._prepare_root
        self._prepare_root = None
        if root is not None and root.name.startswith("apf-textlogo-authoring-"):
            shutil.rmtree(root, ignore_errors=True)

    def _prepared_path(self) -> Path:
        if self._prepare_root is None:
            self._prepare_root = Path(
                tempfile.mkdtemp(prefix="apf-textlogo-authoring-")
            )
        return self._prepare_root / (
            f"wordmark-{self.slot.value():03d}-{uuid4().hex}.png"
        )

    def current_asset(self) -> UniformAsset | None:
        return self._assets.get(self.slot.value())

    def focus_slot(self, asset_index: int) -> bool:
        """Select one wordmark slot, for a hand-off from the asset browser."""

        if not self.slot.minimum() <= asset_index <= self.slot.maximum():
            return False
        self.slot.setValue(asset_index)
        return True

    def stage_image(self, path: Path) -> None:
        """Stage one user image exactly as a drop onto the preview would."""

        self._stage_path(path)

    def set_context(self) -> None:
        source = getattr(self.facade, "source", None)
        source_identity = (
            str(getattr(source, "source_sha256", "")) if source is not None else None
        )
        if source_identity != self._source_identity:
            self._cleanup_prepared_wordmarks()
            self._source_identity = source_identity
        if not self.facade.source_ready:
            self._assets = {}
            self.preview.setAcceptDrops(False)
            self.preview.set_message(
                "Wordmark · 512×128 RGBA PNG\nLoad your game to browse all 206 slots."
            )
            self.status.setText("Not loaded")
            self.status.setStyleSheet("")
            self.owners.setText(
                "Load a game to resolve package ownership.\n\n" + START_HERE_HINT
            )
            load_tip = (
                "Load your APF game first (0A). Wordmark export/import needs the "
                "206-slot catalog. Click still explains this — buttons stay "
                "clickable so gray never means a silent no-op."
            )
            self.export_button.setEnabled(True)
            self.import_button.setEnabled(True)
            self.export_button.setToolTip(load_tip)
            self.import_button.setToolTip(load_tip)
            self.export_button.setProperty("disableReason", load_tip)
            self.import_button.setProperty("disableReason", load_tip)
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(load_tip)
            self.revert_button.setProperty("disableReason", load_tip)
            return
        assets = self.facade.uniform_assets("textlogo")
        if len(assets) != 206 or [asset.asset_index for asset in assets] != list(range(206)):
            self._assets = {}
            self.preview.set_error("The 206-slot wordmark catalog did not validate.")
            self.status.setText("Catalog error")
            catalog_tip = (
                "The 206-slot wordmark catalog did not validate. Re-load a complete "
                "APF dump (0A with full outer table). Click still explains this."
            )
            self.export_button.setEnabled(True)
            self.import_button.setEnabled(True)
            self.export_button.setToolTip(catalog_tip)
            self.import_button.setToolTip(catalog_tip)
            self.export_button.setProperty("disableReason", catalog_tip)
            self.import_button.setProperty("disableReason", catalog_tip)
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(catalog_tip)
            self.revert_button.setProperty("disableReason", catalog_tip)
            return
        self._assets = {asset.asset_index: asset for asset in assets}
        self.preview.setAcceptDrops(True)
        self.export_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.export_button.setToolTip(
            "Export this 512×128 wordmark PNG (staged replacement if present)."
        )
        self.import_button.setToolTip(
            "Import any image — Contain/Cover/Stretch fit to 512×128, then stage "
            "into the project Build. Never mutates your original archive."
        )
        self.export_button.setProperty("disableReason", "")
        self.import_button.setProperty("disableReason", "")
        self._selection_changed()

    def _selection_changed(self) -> None:
        asset = self.current_asset()
        if asset is None:
            return
        modified = asset.asset_id in self.facade.modified_asset_ids
        self.status.setText("● Modified" if modified else "Editable")
        self.status.setStyleSheet(
            "color: #39d98a; border-color: #39d98a;"
        )
        owner_text = (
            ", ".join(asset.affected_teams)
            if asset.affected_teams
            else "No current team selector references this library slot."
        )
        self.owners.setText(
            f"uniform_textlogo_{asset.asset_index:02d}.iff · outer "
            f"{asset.outer_index} / inner {asset.inner_index} · selector owners: "
            f"{owner_text}"
        )
        if modified:
            rev_tip = "Remove this staged wordmark from the project."
            rev_block = ""
        else:
            rev_tip = rev_block = "Nothing to revert for this wordmark."
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(rev_tip)
        self.revert_button.setProperty("disableReason", rev_block)
        modification = self.facade.require_session().modification(asset.asset_id)
        if modification is not None:
            self.preview.set_image(modification.replacement_path)
            return
        self._preview_token += 1
        token = self._preview_token
        self.preview.set_loading(
            f"Decoding wordmark {asset.asset_index} from your read-only game…"
        )

        def complete(result: object) -> None:
            if token == self._preview_token and self.current_asset() == asset:
                self.preview.set_image(Path(str(result)))
                note = getattr(self.facade, "preview_alpha_note", None)
                if note:
                    self.preview.setToolTip(
                        self.preview.toolTip() + "\n\n" + str(note)
                    )

        def _wordmark_preview_watchdog() -> None:
            if token != self._preview_token:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                f"Wordmark {asset.asset_index}: preview still preparing after 45s. "
                "Re-select the slot or Export current PNG."
            )

        QTimer.singleShot(45_000, _wordmark_preview_watchdog)
        self.run_task(
            f"Preparing wordmark {asset.asset_index}",
            lambda progress: self.facade.preview_uniform(asset.asset_id, progress),
            complete,
            False,
        )

    def _choose_image(self) -> None:
        reason = str(self.import_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot import wordmark yet",
                reason
                + "\n\nFix: File → Load game, point at your APF folder/ISO, then "
                "import again. Import stages a project copy — it never mutates "
                "your original dump.",
            )
            return
        asset = self.current_asset()
        if asset is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Import art for wordmark {asset.asset_index} (any size)",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)",
        )
        if path:
            self._stage_path(Path(path))

    def _stage_path(self, source_path: Path) -> None:
        asset = self.current_asset()
        if asset is None:
            return
        fit_mode = str(self.fit_mode.currentData() or "contain")
        prepared_path = self._prepared_path()

        def prepare_operation(
            progress: Callable[[str, int, int], None]
        ) -> object:
            progress("Fitting your image to the 512×128 wordmark slot", 0, 1)
            return prepare_wordmark_png(
                source_path, prepared_path, fit_mode=fit_mode
            )

        self.run_task(
            f"Preparing wordmark {asset.asset_index} preview",
            prepare_operation,
            lambda prepared: self._preview_prepared_wordmark(asset, prepared),
            True,
        )

    def _preview_prepared_wordmark(
        self, asset: UniformAsset, prepared: object
    ) -> None:
        """Show the exact fitted wordmark and stage it only on approval."""

        output_path = Path(getattr(prepared, "output_path"))
        fit_description = str(getattr(prepared, "fit_description"))
        fit_mode = str(getattr(prepared, "fit_mode"))
        transparent_pixels = int(
            getattr(prepared, "transparent_source_pixels")
        )
        approved = confirm_prepared_slot_image(
            self,
            output_path,
            width=WORDMARK_WIDTH,
            height=WORDMARK_HEIGHT,
            title=f"Preview wordmark {asset.asset_index}",
            summary_lines=(
                (
                    f"Fitted {getattr(prepared, 'source_width')}×"
                    f"{getattr(prepared, 'source_height')} with "
                    f"{fit_mode.title()}: {fit_description}."
                ),
                (
                    f"Transparent source pixels flattened onto black: "
                    f"{transparent_pixels:,}. This wordmark slot stores "
                    "opaque pixels only."
                ),
                "Nothing is staged until you choose “Stage this wordmark”.",
            ),
            accept_label="Stage this wordmark",
        )
        if not approved:
            output_path.unlink(missing_ok=True)
            return

        def operation(progress: Callable[[str, int, int], None]) -> object:
            progress("Validating and staging wordmark", 0, 1)
            return self.facade.replace_uniform(
                asset.asset_id, output_path, progress
            )

        def complete(_result: object) -> None:
            self._selection_changed()
            self.modifiedChanged.emit()
            QMessageBox.information(
                self,
                "Wordmark staged",
                f"Slot {asset.asset_index}: {fit_description}.\n\n"
                f"Fit mode: {fit_mode.title()}\n\n"
                "The square helmet crest was not changed. This wordmark is "
                "now part of the normal project Build and can be undone or "
                "reverted.",
            )

        self.run_task(
            f"Importing wordmark {asset.asset_index}",
            operation,
            complete,
            True,
        )

    def _export_current(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export wordmark yet",
                reason
                + "\n\nFix: File → Load game with a complete APF dump, then export "
                "the 512×128 wordmark PNG.",
            )
            return
        asset = self.current_asset()
        if asset is None:
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            f"Export wordmark {asset.asset_index}",
            str(Path.home() / f"apf-wordmark-{asset.asset_index:03d}.png"),
            "RGBA PNG (*.png)",
        )
        if not destination:
            return
        output = Path(destination)
        if not output.suffix:
            output = output.with_suffix(".png")
        if output.exists() or output.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            modification = self.facade.require_session().modification(asset.asset_id)
            if modification is not None:
                progress("Exporting staged wordmark", 0, 0)
                return _copy_new(modification.replacement_path, output)
            return self.facade.export_uniform(asset.asset_id, output, progress)

        self.run_task(
            f"Exporting wordmark {asset.asset_index}",
            operation,
            lambda result: QMessageBox.information(
                self, "Wordmark exported", f"Saved to:\n{Path(str(result))}"
            ),
            True,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Nothing to revert", reason)
            return
        asset = self.current_asset()
        if asset is None:
            return
        self.run_task(
            f"Reverting wordmark {asset.asset_index}",
            lambda progress: self.facade.revert(asset.asset_id, progress),
            lambda _result: self._revert_complete(),
            True,
        )

    def _revert_complete(self) -> None:
        self._selection_changed()
        self.modifiedChanged.emit()


class LogosStudioPage(QWidget):
    """Logos & Team Art: the offline-proved team-logo crest editor plus the full
    category browser (draft_logo and every other logo/team-art record)."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(ApfCategory.LOGOS))
        self.capabilities = CapabilityPanel(ApfCategory.LOGOS)
        layout.addWidget(self.capabilities)
        tabs = QTabWidget()
        tabs.setObjectName("workspaceTabs")
        self.team_logo = ApfTeamLogoPanel(facade, run_task)
        self.wordmarks = ApfTextLogoPanel(facade, run_task)
        self.browser = AssetBrowser(facade, ApfCategory.LOGOS, run_task)
        # Both the crest design and browser edits participate in the shareable
        # project and normal complete-game Build.
        self.team_logo.modifiedChanged.connect(self.modifiedChanged)
        self.wordmarks.modifiedChanged.connect(self.modifiedChanged)
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        team_logo_index = tabs.addTab(self.team_logo, "Team Logo")
        wordmark_index = tabs.addTab(self.wordmarks, "Wordmarks (206)")
        tabs.addTab(self.browser, "All Logo && Team Art")
        tabs.setTabToolTip(
            team_logo_index,
            "Selector slot 5: co-writes the square crest package and its linked "
            "frontend/Team Select cache index.",
        )
        tabs.setTabToolTip(
            wordmark_index,
            "Separate selector slot 6: edits rectangular uniform_textlogo "
            "wordmarks; Team Logo never resizes a crest into this family.",
        )
        layout.addWidget(tabs, 1)
        self.tabs = tabs
        self._team_logo_tab = team_logo_index
        self._wordmark_tab = wordmark_index

    def focus_workspace_route(self, route: WorkspaceRoute, image: Path | None) -> bool:
        """Open a crest or wordmark handed over from an asset browser."""

        if route.tab == TEAM_LOGO_TAB:
            self.tabs.setCurrentIndex(self._team_logo_tab)
            if not route.key:
                # A row that only samples a crest at runtime -- the scorebug's
                # team-logo component -- names no one package to preselect.
                return True
            if not self.team_logo.focus_outer_entry(int(route.key)):
                return False
            if image is not None:
                self.team_logo.stage_image(image)
            return True
        if route.tab == WORDMARK_TAB:
            self.tabs.setCurrentIndex(self._wordmark_tab)
            if not self.wordmarks.focus_slot(int(route.key)):
                return False
            if image is not None:
                self.wordmarks.stage_image(image)
            return True
        return False

    def set_context(self) -> None:
        if self.facade.source_ready:
            count = len(
                self.facade.browse_assets(
                    category=ApfCategory.LOGOS,
                    limit=len(self.facade.require_catalog().assets) + 1,
                )
            )
            self.capabilities.set_cards(
                self.facade.capability_cards(ApfCategory.LOGOS),
                catalog_ready=True,
                inventory_count=count,
            )
        else:
            self.capabilities.set_cards(())
        self.team_logo.set_context()
        self.wordmarks.set_context()
        self.browser.set_context()

    def refresh(self) -> None:
        self.team_logo.set_context()
        self.wordmarks.set_context()
        self.browser.refresh()


class CatalogCategoryPage(QWidget):
    """Capability cards plus a category-filtered universal browser."""

    modifiedChanged = pyqtSignal()

    def __init__(
        self,
        facade: ApfStudioFacade,
        category: ApfCategory,
        run_task: TaskRunner,
    ):
        super().__init__()
        self.facade = facade
        self.category = category
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(category))
        self.capabilities = CapabilityPanel(category)
        layout.addWidget(self.capabilities)
        self.browser = AssetBrowser(facade, category, run_task)
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        layout.addWidget(self.browser, 1)

    def set_context(self) -> None:
        if self.facade.source_ready:
            count = len(
                self.facade.browse_assets(
                    category=self.category,
                    limit=len(self.facade.require_catalog().assets) + 1,
                )
            )
            self.capabilities.set_cards(
                self.facade.capability_cards(self.category),
                catalog_ready=True,
                inventory_count=count,
            )
        else:
            self.capabilities.set_cards(())
        self.browser.set_context()

    def refresh(self) -> None:
        self.browser.refresh()


@dataclass(frozen=True)
class _FieldArtTarget:
    """One offline-proved, writable field-art base texture offered by the editor."""

    entry_index: int
    file_index: int
    name: str
    width: int
    height: int
    codec: str
    lossless: bool
    note: str

    @property
    def key(self) -> tuple[int, int]:
        return (self.entry_index, self.file_index)

    @property
    def label(self) -> str:
        return (
            f"{self.name} — {self.width}×{self.height} {self.codec} "
            f"(outer {self.entry_index} / inner {self.file_index})"
        )


# tools/apf_field_art_patch.py is the authority for these pins: its frozen
# per-slot contracts re-validate the outer entry, the inner file, the Xenos
# descriptor, the base/mip lengths, and the retail entry/base SHA-256, and it
# refuses anything that disagrees.  The panel mirrors them only for honest
# labels and its exact-size stage guard.  The deferred families (field_radiance
# DXT5A and the divot_Grass* weather textures, 5_6_5) are deliberately absent:
# the writer refuses them with a typed error, so they are never offered here.
FIELD_ART_COVERED_TARGETS: tuple[_FieldArtTarget, ...] = (
    _FieldArtTarget(
        6, 0, "endzone_l0", 2048, 512, "DXT1", False,
        "Endzone base layer for the one team that owns package 6 — not a "
        "shared layer, so editing it repaints that team's endzone only. It is "
        "structurally identical to the other 117 packages and is simply the "
        "pair proved writable first. A red/green/blue region mask over black, "
        "like jersey_color and shoulder_color: hard edges and flat colours, "
        "because intermediate values are invalid region IDs, not blends. The "
        "sibling endzone_l1 layer, the descriptor pad, and the packed mip tail "
        "all stay byte-identical.",
    ),
    _FieldArtTarget(
        6, 1, "endzone_l1", 2048, 512, "DXT1", False,
        "Endzone second layer for the same single team as endzone_l0 above, "
        "and not a shared layer either. Also a red/green/blue region mask over black; "
        "author it with flat colours and no anti-aliasing. The sibling "
        "endzone_l0 layer, the descriptor pad, and the packed mip tail all "
        "stay byte-identical.",
    ),
    _FieldArtTarget(
        659, 18, "pc_field_goal", 256, 256, "DXT1", False,
        "Practice field-goal overlay. Every other inner part of the shared "
        "package stays byte-identical.",
    ),
    _FieldArtTarget(
        659, 23, "Field_Pass_text", 128, 128, "BC3", False,
        "Practice passing overlay. Every other inner part of the shared package "
        "stays byte-identical.",
    ),
    _FieldArtTarget(
        659, 252, "Stride_number_field", 128, 128, "BC3", False,
        "Practice stride-number overlay. Every other inner part of the shared "
        "package stays byte-identical.",
    ),
    _FieldArtTarget(
        53, 0, "divots", 64, 64, "8_8_8_8", True,
        "Base divot texture, uncompressed and lossless. The divot_GrassRain / "
        "GrassSnow / GrassDry weather textures are a deferred 5_6_5 codec.",
    ),
)


def _extra_field_art_targets() -> tuple[_FieldArtTarget, ...]:
    """Descriptor-derived weave, dirtmap, and format-18 endzone slots."""

    from .backend import ensure_tools_importable

    ensure_tools_importable()
    import apf_field_art_patch as field_art_writer

    core = {(6, 0), (6, 1), (659, 18), (659, 23), (659, 252), (53, 0)}
    codec_label = {"dxt1": "DXT1", "bc3": "BC3", "rgba8888": "8_8_8_8"}
    notes = {
        "UNIFORM_WEAVE": (
            "Uniform weave/detail map. Layout comes from the retail descriptor, "
            "not a typed table. Runtime visibility is unproved."
        ),
        "UNIFORM_DIRTMAP": (
            "Uniform dirt/wear map. Layout comes from the retail descriptor. "
            "Runtime visibility is unproved."
        ),
        "ENDZONE_TEXTURE": (
            "Per-team endzone region mask, same DXT1 structure as package 6. "
            "Format-59 DXT5A packages are not offered. Not a shared layer."
        ),
    }
    extras: list[_FieldArtTarget] = []
    for key, contract in sorted(field_art_writer._CONTRACTS.items()):
        if key in core:
            continue
        extras.append(
            _FieldArtTarget(
                contract.entry_index,
                contract.file_index,
                contract.name,
                contract.width,
                contract.height,
                codec_label[contract.codec],
                contract.codec == "rgba8888",
                notes.get(contract.kind, "Descriptor-derived writable texture."),
            )
        )
    return tuple(extras)


FIELD_ART_COVERED_TARGETS = FIELD_ART_COVERED_TARGETS + _extra_field_art_targets()


class ApfFieldArtPanel(QFrame):
    """Focused editor for the offline-proved, writable field-art base textures.

    This surface mirrors :class:`ApfTeamLogoPanel` and is deliberately
    self-contained.  It reads the loaded game's read-only ``0A`` to render a
    source-derived preview of the selected pinned slot, stages exactly one PNG
    at that slot's exact base dimensions, and routes the build through the
    offline ``apf2k8.field_art.base_texture`` capability whose backend is
    ``tools/apf_field_art_patch.py``.  That writer copies the whole volume,
    rewrites only the selected base mip level, byte-preserves the descriptor
    pad, the packed mip tail, and every sibling inner part, reparses the
    rebuilt entry in RAM before it is written, and pairs the write with an
    independent verifier; the retail source is never opened for writing.

    The original six proved bases, package-659 weave/dirtmaps, and format-18
    endzones are offered.  Format-59 DXT5A endzones, ``field_radiance``, the
    ``divot_Grass*`` weather textures, and the SCNE/CurveAnim rows stay locked
    in the inventory browser below.

    The panel never mutates the shared editing session, so it never marks
    unrelated project state modified, and it makes no in-game/runtime claim:
    what a changed field texture looks like in play is unproved without a Xenia
    capture.
    """

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._staged: dict[tuple[int, int], Path] = {}
        self._preview_dir: Path | None = None
        self._preview_token = 0
        self._display_alpha_note: str | None = None
        self.setObjectName("panel")
        box = QHBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(16)
        self.preview = ImageDropLabel(
            "Field art · exact-size RGBA PNG\nLoad your game to see the original."
        )
        self.preview.setFixedSize(220, 220)
        self.preview.pngDropped.connect(self._stage_path)
        box.addWidget(self.preview)

        content = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel("Field art — proven base textures")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.status)

        # The three chips restate the selected slot's contract at a glance:
        # exact size (the one fact a modder must honor before picking a file),
        # stored codec, and the write's scope.  Text updates per selection.
        specs = QHBoxLayout()
        specs.setSpacing(6)
        self.size_pill = _spec_pill(
            "2048×512 RGBA PNG",
            emphasis=True,
            tooltip=(
                "The slot holds exactly this size for the selected texture. "
                "Drop or choose any image size — an off-size file is resized "
                "to this for you before anything is staged."
            ),
        )
        self.codec_pill = _spec_pill(
            "DXT1 · re-encoded",
            tooltip=(
                "The codec the game stores this texture in. Compressed codecs "
                "re-encode your colors and the build reports the exact "
                "decode-back error; uncompressed slots are lossless."
            ),
        )
        self.scope_pill = _spec_pill(
            "Writes this texture only",
            tooltip=(
                "A build copies your 0A and regenerates only this slot's base "
                "mip level; every other byte of the volume stays identical."
            ),
        )
        specs.addWidget(self.size_pill)
        specs.addWidget(self.codec_pill)
        specs.addWidget(self.scope_pill)
        specs.addStretch(1)

        slot_row = QHBoxLayout()
        slot_row.setSpacing(8)
        slot_label = QLabel("Texture:")
        slot_label.setObjectName("metadataText")
        self.slot_filter = QLineEdit()
        self.slot_filter.setObjectName("searchField")
        self.slot_filter.setPlaceholderText("Filter textures… (name, codec, outer)")
        self.slot_filter.setClearButtonEnabled(True)
        self.slot_filter.setAccessibleName("Filter writable field-art textures")
        self.slot_filter.setProperty("studioSearch", True)
        self.slot_filter.setToolTip(
            "Filter the writable field-art list by name, codec, or outer/inner "
            "index. Clear the box to see every proved slot. Format-59 DXT5A "
            "endzones and the deferred codecs never appear here."
        )
        self.slot = QComboBox()
        self.slot.setObjectName("comboField")
        self.slot.setMaxVisibleItems(24)
        self.slot.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.slot.setMinimumContentsLength(24)
        self.slot.setToolTip(
            "Writable field-art slots: the original six proved bases, "
            "package-659 weave/dirtmaps, and format-18 endzones. "
            "field_radiance (DXT5A), format-59 endzones, and the "
            "divot_Grass* weather textures (5_6_5) are deferred, and the "
            "SCNE/CurveAnim rows have no serializer, so none of them are "
            "offered here."
        )
        self._populate_slots()
        slot_row.addWidget(slot_label)
        slot_row.addWidget(self.slot_filter, 1)
        slot_row.addWidget(self.slot, 2)

        self.description = QLabel("")
        self.description.setObjectName("cardBody")
        self.description.setWordWrap(True)
        self.lock_note = QLabel(
            "Stock NFL endzone packages (≈118 l0/l1 pairs) appear under All "
            "Textures / the Field Art inventory browser below — browse and "
            "export every one. This editor writes the original six proved "
            "bases, package-659 weave/dirtmaps, and format-18 per-team "
            "endzones. Format-59 DXT5A endzones and field_radiance / "
            "weather-divot codecs remain export-only; see "
            "docs/product/APF_FIELD_ART_STOCK_NFL_WALL.md."
        )
        self.lock_note.setObjectName("metadataText")
        self.lock_note.setWordWrap(True)
        self.path_note = QLabel("No source loaded.")
        self.path_note.setObjectName("metadataText")
        self.path_note.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export original PNG…")
        self.export_button.setObjectName("secondaryButton")
        self.replace_button = QPushButton("Replace PNG…")
        self.replace_button.setObjectName("primaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.build_button = QPushButton("Build copied 0A (this texture only)…")
        self.build_button.setObjectName("secondaryButton")
        self.export_button.clicked.connect(self._export_original)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.revert_button.clicked.connect(self._revert)
        self.build_button.clicked.connect(self._build_copied_volume)
        actions.addWidget(self.export_button)
        actions.addWidget(self.replace_button)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.build_button)
        actions.addStretch(1)

        content.addLayout(title_row)
        content.addLayout(specs)
        content.addLayout(slot_row)
        content.addWidget(self.description)
        content.addWidget(self.lock_note)
        content.addWidget(self.path_note)
        # Keep the edit workflow with its copy; spare height goes below.
        content.addLayout(actions)
        content.addStretch(1)
        box.addLayout(content, 1)
        # Connected only once every widget set_context() touches exists.
        self.slot.currentIndexChanged.connect(self._target_changed)
        self.slot_filter.textChanged.connect(self._filter_slots)
        self.set_context()

    def _populate_slots(
        self, preserve_key: tuple[int, int] | None = None
    ) -> None:
        """Fill the combo from the proved table, optionally filtered."""

        needle = self.slot_filter.text().strip().casefold()
        if preserve_key is None:
            current = self.slot.currentData()
            if isinstance(current, _FieldArtTarget):
                preserve_key = current.key
        if needle:
            matches = tuple(
                target
                for target in FIELD_ART_COVERED_TARGETS
                if needle
                in (
                    f"{target.name} {target.codec} {target.entry_index} "
                    f"{target.file_index} {target.label}"
                ).casefold()
            )
        else:
            matches = FIELD_ART_COVERED_TARGETS
        self.slot.blockSignals(True)
        self.slot.clear()
        selected = 0
        for target in matches:
            self.slot.addItem(target.label, target)
            if target.key == preserve_key:
                selected = self.slot.count() - 1
        if self.slot.count():
            self.slot.setCurrentIndex(selected)
        self.slot.blockSignals(False)

    def _filter_slots(self, _text: str = "") -> None:
        self._populate_slots()
        self._target_changed()

    def current_target(self) -> _FieldArtTarget:
        target = self.slot.currentData()
        if isinstance(target, _FieldArtTarget):
            return target
        return FIELD_ART_COVERED_TARGETS[0]

    def staged_path(self, target: _FieldArtTarget) -> Path | None:
        return self._staged.get(target.key)

    def focus_target(self, name: str) -> bool:
        """Select one writable base texture by slot name or ``outer:inner``."""

        wanted: _FieldArtTarget | None = None
        if name.count(":") == 1:
            left, right = name.split(":")
            if left.isdigit() and right.isdigit():
                key = (int(left), int(right))
                wanted = next(
                    (target for target in FIELD_ART_COVERED_TARGETS if target.key == key),
                    None,
                )
        if wanted is None:
            wanted = next(
                (target for target in FIELD_ART_COVERED_TARGETS if target.name == name),
                None,
            )
        if wanted is None:
            return False
        if self.slot_filter.text():
            self.slot_filter.blockSignals(True)
            self.slot_filter.clear()
            self.slot_filter.blockSignals(False)
        self._populate_slots(preserve_key=wanted.key)
        self._target_changed()
        return self.current_target().key == wanted.key

    def stage_image(self, path: Path) -> None:
        """Stage one user image exactly as a drop onto the preview would."""

        self._stage_path(path)

    def _target_changed(self, _index: int = -1) -> None:
        self.set_context()

    def set_context(self) -> None:
        ready = self.facade.source_ready
        target = self.current_target()
        staged = self.staged_path(target)
        # Never silent-gray: the 221-slot combo stays searchable even before
        # a game is loaded, and export/replace/build/revert stay clickable.
        self.slot.setEnabled(True)
        self.slot_filter.setEnabled(True)
        load_tip = (
            "Load your APF game first. Field Art export/replace needs a source. "
            "Click still explains — buttons stay clickable."
        )
        export_tip = (
            f"Export the current source-derived {target.width}×{target.height} "
            f"RGBA {target.name} PNG from your game."
            if ready
            else load_tip
        )
        replace_tip = (
            f"Choose an edited {target.width}×{target.height} RGBA PNG for "
            f"{target.name}, or drop it onto the preview."
            if ready
            else load_tip
        )
        build_tip = (
            "Copy your 0A and write only this one field-art texture through the "
            "offline-proved writer and its independent verifier."
            if (ready and staged is not None)
            else (
                f"Load your game and stage a {target.width}×{target.height} RGBA "
                "PNG to build."
                if not ready
                else f"Stage a {target.width}×{target.height} RGBA PNG for "
                f"{target.name} first, then Build."
            )
        )
        revert_tip = (
            f"Discard the staged replacement PNG and show your original "
            f"{target.name} again."
            if staged is not None
            else "Nothing to revert—no replacement is staged for this texture."
        )
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        self.build_button.setEnabled(True)
        self.revert_button.setEnabled(True)
        self.export_button.setToolTip(export_tip)
        self.replace_button.setToolTip(replace_tip)
        self.build_button.setToolTip(build_tip)
        self.revert_button.setToolTip(revert_tip)
        self.export_button.setProperty("disableReason", "" if ready else load_tip)
        self.replace_button.setProperty("disableReason", "" if ready else load_tip)
        self.build_button.setProperty(
            "disableReason", "" if (ready and staged is not None) else build_tip
        )
        self.revert_button.setProperty(
            "disableReason", "" if staged is not None else revert_tip
        )
        self.preview.setAcceptDrops(ready)
        codec_display = target.codec.replace("_", "·")
        self.size_pill.setText(f"{target.width}×{target.height} RGBA PNG")
        self.codec_pill.setText(
            f"{codec_display} · lossless"
            if target.lossless
            else f"{codec_display} · re-encoded"
        )
        lead = target.note.split(".")[0].strip()
        codec_sentence = (
            "This slot is uncompressed, so your pixels land losslessly."
            if target.lossless
            else (
                f"{target.codec} re-encodes colors in 4×4 blocks, and the build "
                "reports the exact decode-back error."
            )
        )
        self.description.setText(
            f"{lead}. Drop or choose any image — an off-size file is resized to "
            f"the exact {target.width}×{target.height} slot for you before "
            f"anything is staged. {codec_sentence} Only this base level changes "
            "— the packed mip tail keeps its original bytes — and how the edit "
            "looks in play is not proved without a Xenia capture."
        )
        self.description.setToolTip(
            f"Full contract: the offline-proved writer owns outer "
            f"{target.entry_index} / inner {target.file_index} ({target.name}), "
            f"a {target.width}×{target.height} Xenos {target.codec} texture. "
            f"{target.note} Only the base mip level is regenerated; the packed "
            "mip tail is byte-preserved, so it stays stale relative to your edit."
        )

        self._preview_token += 1
        if not ready:
            self.status.setText("○ Not loaded")
            self.status.setStyleSheet("color: #8795aa; border-color: #8795aa;")
            self.preview.set_message(
                f"{target.name} · {target.width}×{target.height} RGBA PNG\n"
                "Load your game to see the original."
            )
            self.path_note.setText(
                "No game loaded yet — preview, export, and Replace unlock once "
                "your source is recognized.\n\n" + START_HERE_HINT
            )
            return
        if staged is not None:
            self.status.setText("● Staged")
            self.status.setStyleSheet("color: #39d98a; border-color: #39d98a;")
            self.preview.set_image(staged)
            self.path_note.setText(
                f"Current preview: your staged {target.width}×{target.height} RGBA "
                "replacement. Build copies your 0A and writes only this texture; "
                "your source game stays untouched."
            )
            return
        self.status.setText(_status_text(ApfStatus.EDITABLE))
        self.status.setStyleSheet("color: #39d98a; border-color: #39d98a;")
        self.preview.set_loading(f"Decoding the original {target.name} from your game…")
        self.path_note.setText(
            f"Current preview: original {target.name} decoded from your own game "
            "(read-only)."
        )
        token = self._preview_token

        def _field_art_preview_watchdog() -> None:
            if token != self._preview_token:
                return
            if str(self.preview.property("previewState") or "") != "loading":
                return
            self.preview.set_error(
                f"{target.name}: preview still preparing after 45s. "
                "Re-select the Field Art slot or Export original."
            )

        QTimer.singleShot(45_000, _field_art_preview_watchdog)
        self.run_task(
            f"Decoding {target.name}",
            lambda progress: self._decode_source_operation(target, progress),
            lambda result: self._apply_preview(target, token, result),
            False,
        )

    def _writer_module(self) -> Any:
        root = Path(__file__).resolve().parents[2]
        for candidate in (str(root), str(root / "tools")):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        import apf_field_art_patch  # noqa: E402 - tools/ writer added to sys.path above

        return apf_field_art_patch

    def _writer_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "tools" / "apf_field_art_patch.py"

    def _preview_path(self, name: str) -> Path:
        if self._preview_dir is None:
            self._preview_dir = Path(tempfile.mkdtemp(prefix="apf-field-art-"))
        return self._preview_dir / name

    def _decode_source_operation(
        self,
        target: _FieldArtTarget,
        progress: Callable[[str, int, int], None],
        *,
        for_display: bool = True,
    ) -> tuple[bool, object]:
        try:
            source = self.facade.source
            if source is None:
                raise RuntimeError("Load your APF 2K8 game first.")
            index_path = Path(source.index_0a)
            progress(f"Reading the read-only {target.name} texture", 0, 0)
            writer = self._writer_module()
            import apf_inner  # noqa: E402 - resolved once the writer added tools/
            import apf_outer  # noqa: E402
            from PIL import Image

            contract = writer._CONTRACTS.get(target.key)
            if contract is None:
                raise RuntimeError(
                    f"{target.name} is not a pinned writable field-art slot."
                )
            archive = apf_outer.parse_archive(index_path)
            entry = archive.entries[contract.entry_index]
            with apf_inner.ArchiveReader(archive) as reader:
                record = apf_inner.parse_iff(reader, entry)
                blocks = [
                    apf_inner.decode_block(reader, record, index, 1 << 30)
                    for index in range(record.block_count)
                ]
            _file, _pixel_part, _descriptor, pixel_bytes, metadata = (
                writer._resolve_target(record, blocks, contract)
            )
            head_len = len(pixel_bytes) - contract.base_len - contract.mip_len
            if head_len < 0:
                raise RuntimeError(
                    f"{target.name} pixel part is smaller than its pinned base "
                    "and mip tail."
                )
            base = pixel_bytes[head_len : head_len + contract.base_len]
            width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
            self._display_alpha_note = None
            if for_display:
                rgba, applied = apf_inner.force_opaque_alpha_for_display(rgba)
                if applied:
                    self._display_alpha_note = (
                        "This mask's alpha is unused storage (all zero); "
                        "the preview is shown opaque so its RGB data is visible."
                    )
            output = self._preview_path(f"{contract.name}_source.png")
            Image.frombytes("RGBA", (width, height), rgba).save(output)
            return True, output
        except Exception as exc:  # surfaced inline in the preview, not as a modal
            return False, str(exc)

    def _apply_preview(
        self, target: _FieldArtTarget, token: int, result: object
    ) -> None:
        # A slot change or a stage (drop/choose) may have won the race while the
        # decode ran; keep whatever the panel shows now rather than overwriting it.
        if token != self._preview_token or self.current_target().key != target.key:
            return
        if self.staged_path(target) is not None:
            return
        ok, value = result  # type: ignore[misc]
        if ok:
            self.preview.set_image(Path(str(value)))
            if self._display_alpha_note:
                self.path_note.setText(
                    self.path_note.text() + "\n\n" + self._display_alpha_note
                )
        else:
            self.preview.set_error(str(value))

    def _export_original(self) -> None:
        reason = str(self.export_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export Field Art yet",
                reason + "\n\nFix: File → Load game, then Export original PNG.",
            )
            return
        target = self.current_target()
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            f"Export source-derived {target.name} PNG",
            str(Path.home() / f"apf-{target.name}.png"),
            "RGBA PNG (*.png)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".png")
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            ok, value = self._decode_source_operation(
                target, progress, for_display=False
            )
            if not ok:
                raise RuntimeError(str(value))
            return _copy_new(Path(str(value)), path)

        self.run_task(
            f"Exporting {target.name} PNG",
            operation,
            lambda result: QMessageBox.information(
                self, "PNG exported", f"Saved to:\n{Path(str(result))}"
            ),
            True,
        )

    def _choose_replacement(self) -> None:
        reason = str(self.replace_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace Field Art yet",
                reason
                + "\n\nFix: File → Load game, then Replace or drop an image. "
                "Build writes a copied 0A — never mutates your original.",
            )
            return
        target = self.current_target()
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose a {target.name} image (any size — "
            f"{target.width}×{target.height} exact, or it can be resized)",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)",
        )
        if path:
            self._stage_path(Path(path))

    def _stage_path(self, path: Path) -> None:
        """Stage an image for this slot, resizing it when it is not exact.

        These are full-bleed textures -- a jersey, pants, a colour map -- so a
        mismatched aspect ratio fills the slot and trims the overflow rather
        than padding. Transparent bars baked into a jersey read as holes in
        game, which is the opposite of what a crest wants.
        """
        if not self.facade.source_ready:
            return
        target = self.current_target()
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_image, fit_to_png

        try:
            probe = fit_image(path, target.width, target.height)
        except ValidationError as exc:
            QMessageBox.information(
                self,
                "That file could not be read as an image",
                f"{exc}\n\nFix: choose or drop a {_plain_image_formats()} "
                "image. Any size works -- the editor resizes it for you.",
            )
            return

        if not probe.changed:
            self._staged[target.key] = Path(path)
            self.set_context()
            return

        answer = QMessageBox.question(
            self,
            "Resize this image?",
            f"{target.name} must be exactly {target.width}×{target.height}, and "
            f"that image is {probe.source_width}×{probe.source_height}.\n\n"
            f"Mod Studio can {probe.describe()} for you.\n\n"
            "Your original file is not modified — the resized copy is staged "
            "for this build only.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            staged = self._preview_path(f"{target.key}_resized.png")
            result = fit_to_png(path, target.width, target.height, staged)
        except ValidationError as exc:
            QMessageBox.information(
                self,
                "Could not prepare that image",
                f"{exc}\n\nFix: try a different {_plain_image_formats()} "
                "image. No edit was staged.",
            )
            return
        self._staged[target.key] = staged
        self.set_context()
        QMessageBox.information(
            self, "Resized",
            f"Staged a {target.width}×{target.height} copy — {result.describe()}."
            "\n\nPreview it before building; your original file is unchanged.",
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Nothing to revert",
                reason + "\n\nStage a Field Art replacement first.",
            )
            return
        self._staged.pop(self.current_target().key, None)
        self.set_context()

    def _build_copied_volume(self) -> None:
        reason = str(self.build_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot build Field Art copy yet",
                reason
                + "\n\nFix: load APF → stage one of the six proved slots → Build "
                "a verified copied 0A.",
            )
            return
        source = self.facade.source
        target = self.current_target()
        staged = self.staged_path(target)
        if not self.facade.source_ready or source is None or staged is None:
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Choose the new copied 0A volume to create",
            str(Path.home() / f"APF-{target.name}" / "0A"),
            "APF 0A volume (0A);;All files (*)",
        )
        if not destination:
            return
        out_volume = Path(destination)
        manifest = out_volume.parent / f"{out_volume.name}.field_art_patch.json"
        if out_volume.exists() or manifest.exists():
            QMessageBox.information(
                self,
                "Choose a new location",
                "The proved writer never overwrites existing files. Pick a folder and "
                "name that do not exist yet, then try again.",
            )
            return
        index_path = Path(source.index_0a)
        confirm = QMessageBox.question(
            self,
            "Build copied 0A (one field-art texture)?",
            "This copies your entire ~1.1 GB 0A volume to the chosen path and "
            f"replaces only the {target.name} base texture (outer "
            f"{target.entry_index} / inner {target.file_index}) through the "
            "offline-proved writer. The descriptor pad, the packed mip tail, "
            "every sibling inner part, and every other byte of the volume are "
            "verified unchanged, and your source game is never modified.\n\n"
            "One build writes exactly one field-art texture: the writer is pinned "
            "to the retail bytes of each slot, so re-running it against an "
            "already-edited volume is not proved and will be refused.\n\n"
            "This writes only the 0A volume and only this field-art edit — not other "
            "Mod Studio edits. Boot it alongside your own unmodified game packs.\n\n"
            f"Source (read-only): {index_path}\n"
            f"New copied 0A: {out_volume}\n"
            f"Manifest: {manifest}\n\n"
            "Proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        def operation(progress: Callable[[str, int, int], None]) -> Path:
            # Route through the shared copied-volume builder the facade reuses,
            # keeping the writer-path seam this panel owns.
            return build_field_art_copied_volume(
                index_path,
                staged,
                target.entry_index,
                target.file_index,
                out_volume,
                manifest,
                progress,
                writer_path=self._writer_path(),
                slot_name=target.name,
            )

        self.run_task(
            f"Building copied 0A ({target.name})",
            operation,
            self._build_complete,
            True,
        )

    def _build_complete(self, manifest_path: object) -> None:
        path = Path(str(manifest_path))
        detail = ""
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            metrics = document.get("base_data", {}).get("decode_back_metrics", {})
            max_error = metrics.get("maximum_absolute_error")
            copied = document.get("copied_volume") or {}
            if max_error is not None:
                detail += (
                    f"\n\nDecode-back max per-channel error: {max_error} "
                    "(0 = exact; larger means block compression moved a color)."
                )
            if copied.get("output_volume_sha256"):
                detail += f"\nCopied 0A sha256: {copied['output_volume_sha256']}"
        except (OSError, ValueError):
            pass
        QMessageBox.information(
            self,
            "Copied 0A built",
            "The offline-proved field-art writer copied your 0A and wrote only "
            f"this texture, verified against the whole volume.\n\nManifest:\n{path}"
            f"{detail}\n\nOnly the base mip level was regenerated; the packed mip "
            "tail is byte-preserved. How this looks in play is not proved without "
            "a Xenia capture.",
        )


class FieldArtStudioPage(QWidget):
    """Reviewed APF field-art families over the universal asset browser.

    Authorship on this page is the offline-proved writable set the field-art
    writer owns — the original six bases, package-659 weave/dirtmaps, and
    format-18 endzones.  :class:`ApfFieldArtPanel` routes every write through
    ``tools/apf_field_art_patch.py``.  Format-59 DXT5A endzones and the
    deferred codecs stay discovery: each semantic row below is still the
    original catalog identity consumed by :class:`AssetBrowser`, so preview
    and export keep using the existing bounded I/O path, and the page never
    manufactures selector, material, stadium, or team ownership.
    """

    modifiedChanged = pyqtSignal()

    ACTION_LOCK_REASON = (
        "This full Field Art inventory is browse and export-only. Writable "
        "bases, weave/dirtmaps, and format-18 endzones are edited in the "
        "Field Art editor above; here, archive-package co-location still "
        "does not prove the runtime field material or its team/stadium "
        "selector, and the deferred codecs (field_radiance, format-59 "
        "endzones, the divot_Grass* weather textures) and the "
        "SCNE/CurveAnim rows have no bounded writer at all."
    )

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.inventory: FieldArtInventory | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(ApfCategory.FIELD_ART))
        self.capabilities = CapabilityPanel(ApfCategory.FIELD_ART)
        layout.addWidget(self.capabilities)

        # The bounded authorship surface: only the slots the offline writer
        # proved.  The inventory below stays browse/export-only.
        self.editor = ApfFieldArtPanel(facade, run_task)
        layout.addWidget(self.editor)

        semantic_panel = QFrame()
        semantic_panel.setObjectName("panel")
        semantic_layout = QVBoxLayout(semantic_panel)
        semantic_layout.setContentsMargins(14, 12, 14, 12)
        semantic_layout.setSpacing(8)

        semantic_header = QHBoxLayout()
        semantic_header.setSpacing(10)
        semantic_title = QLabel("Field Art ownership map")
        semantic_title.setObjectName("panelTitle")
        self.summary_label = QLabel("Load a game to build the semantic map.")
        self.summary_label.setObjectName("countPill")
        self.group_filter = QComboBox()
        self.group_filter.setMinimumWidth(245)
        self.group_filter.setToolTip(
            "Filter the exact catalog rows by a reviewed semantic family."
        )
        self.stock_endzone_button = QPushButton("Stock team endzones")
        self.stock_endzone_button.setObjectName("secondaryButton")
        self.stock_endzone_button.setToolTip(
            "Jump the ownership map + inventory to the endzone family (235 "
            "per-team layers in 118 packages). Browse/export only — per-team "
            "writers are not proved. The focused editor writes package 6, which "
            "is one team's own endzone rather than a shared layer."
        )
        self.stock_endzone_button.setProperty(
            "disableReason",
            "Load your APF game first, then Stock team endzones filters the inventory.",
        )
        self.stock_endzone_button.clicked.connect(self._show_stock_endzones)
        self.contact_sheet_button = QPushButton("Export endzone contact sheet…")
        self.contact_sheet_button.setObjectName("secondaryButton")
        self.contact_sheet_button.setToolTip(
            "Render every endzone package into labelled sheets so you can find "
            "a team's endzone by looking at it. A name search cannot work — the "
            "nicknames are not on the disc at all, only in Roster.ROS. Your "
            "game is opened read-only."
        )
        self.contact_sheet_button.setProperty(
            "disableReason",
            "Load your APF game first, then export the endzone contact sheet.",
        )
        self.contact_sheet_button.clicked.connect(self._export_endzone_contact_sheet)
        semantic_header.addWidget(semantic_title)
        semantic_header.addWidget(self.summary_label)
        semantic_header.addStretch(1)
        semantic_header.addWidget(self.contact_sheet_button)
        semantic_header.addWidget(self.stock_endzone_button)
        semantic_header.addWidget(QLabel("Show"))
        semantic_header.addWidget(self.group_filter)
        semantic_layout.addLayout(semantic_header)

        self.group_table = QTableWidget(0, 4)
        self.group_table.setObjectName("fieldArtGroupTable")
        self.group_table.setHorizontalHeaderLabels(
            ("Semantic family", "Resources", "Packages", "Authoring boundary")
        )
        self.group_table.verticalHeader().setVisible(False)
        self.group_table.verticalHeader().setDefaultSectionSize(30)
        self.group_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.group_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.group_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.group_table.setAlternatingRowColors(True)
        self.group_table.horizontalHeader().setSectionResizeMode(
            0, self.group_table.horizontalHeader().ResizeToContents
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            1, self.group_table.horizontalHeader().ResizeToContents
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            2, self.group_table.horizontalHeader().ResizeToContents
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            3, self.group_table.horizontalHeader().Stretch
        )
        self.group_table.setFixedHeight(236)
        semantic_layout.addWidget(self.group_table)

        self.group_note = QLabel(
            "Choose a family to see its exact package-local evidence boundary."
        )
        self.group_note.setObjectName("findingText")
        self.group_note.setWordWrap(True)
        self.package_note = QLabel(
            "Package note: package ownership has not been established."
        )
        self.package_note.setObjectName("mutedLabel")
        self.package_note.setWordWrap(True)
        semantic_layout.addWidget(self.group_note)
        semantic_layout.addWidget(self.package_note)
        layout.addWidget(semantic_panel)

        self.browser = AssetBrowser(
            facade,
            ApfCategory.FIELD_ART,
            run_task,
            browse_export_only=True,
            action_lock_reason=self.ACTION_LOCK_REASON,
        )
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        layout.addWidget(self.browser, 1)

        self.group_filter.currentIndexChanged.connect(self._group_changed)
        self.group_table.cellClicked.connect(self._group_row_clicked)

    def _clear_semantic_view(self, message: str) -> None:
        self.inventory = None
        self.summary_label.setText(message)
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All Field Art records", None)
        self.group_filter.blockSignals(False)
        self.group_table.clearContents()
        self.group_table.setRowCount(0)
        self.group_note.setText(
            "Semantic families are unavailable; the raw catalog remains visible below."
        )
        self.package_note.setText(
            "This inventory stays browse/export-only. Writable bases, "
            "weave/dirtmaps, and format-18 endzones are edited above; "
            "format-59 DXT5A endzones stay export-only."
        )
        self.browser.set_included_asset_ids(None)
        load_tip = (
            "Load your APF game first, then Stock team endzones filters the inventory "
            "to ≈118 package pairs (browse/export only)."
        )
        self.stock_endzone_button.setEnabled(True)
        self.stock_endzone_button.setToolTip(load_tip)
        self.stock_endzone_button.setProperty("disableReason", load_tip)
        sheet_tip = (
            "Load your APF game first, then export the endzone contact sheet to "
            "identify a team's endzone package by its artwork."
        )
        self.contact_sheet_button.setEnabled(True)
        self.contact_sheet_button.setToolTip(sheet_tip)
        self.contact_sheet_button.setProperty("disableReason", sheet_tip)

    def _show_stock_endzones(self) -> None:
        """Community path: surface stock NFL endzone packages without Discord help."""

        reason = str(self.stock_endzone_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Stock NFL endzones", reason)
            return
        if self.inventory is None:
            return
        index = self.group_filter.findData(FieldArtKind.ENDZONE_TEXTURE.value)
        if index < 0:
            QMessageBox.information(
                self,
                "Stock NFL endzones",
                "No endzone semantic family is in this inventory map. "
                "Reload the game or open All Textures and search endzone_l0.",
            )
            return
        self.group_filter.setCurrentIndex(index)

    def _export_endzone_contact_sheet(self) -> None:
        """Turn "which package is my team's endzone" into one action.

        The rows carry no team identity and the nicknames are not on the disc,
        so no search can answer this. Rendering all 118 packages and looking is
        the only route, and it was previously an afternoon of scripting.
        """

        reason = str(self.contact_sheet_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Endzone contact sheet", reason)
            return
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Choose a folder for the endzone contact sheets", str(Path.home())
        )
        if not directory:
            return
        destination = Path(directory)
        outer_indices: tuple[int, ...] = ()
        if self.inventory is not None:
            outer_indices = tuple(
                sorted(
                    {
                        record.outer_index
                        for record in self.inventory.records
                        if record.kind is FieldArtKind.ENDZONE_TEXTURE
                    }
                )
            )

        def operation(progress) -> dict:
            written = export_endzone_contact_sheets(
                Path(index_0a),
                destination,
                progress=progress,
                outer_indices=outer_indices or None,
            )
            return {"paths": written}

        def done(result: object) -> None:
            written = result["paths"]  # type: ignore[index]
            labelled = len(endzone_team_labels())
            QMessageBox.information(
                self,
                "Endzone contact sheets written",
                f"Wrote {len(written)} sheet{'s' if len(written) != 1 else ''} to:\n"
                f"{destination}\n\n"
                f"Every endzone package is tiled and labelled with its package "
                f"index; {labelled} of them also carry the team that has been "
                "identified from the artwork so far. Find your team, note the "
                "package number, and open that package under All Textures.\n\n"
                + ENDZONE_MASK_CONTRACT
                + "\n\n"
                + ENDZONE_IDENTITY_NOTE,
            )

        self.run_task("Rendering endzone contact sheets", operation, done, False)

    def _populate_semantic_view(self, inventory: FieldArtInventory) -> None:
        self.inventory = inventory
        summary = inventory.summary
        self.summary_label.setText(
            f"{summary['semantic_records']:,} resources  •  "
            f"{summary['semantic_groups']} families  •  "
            f"{summary['archive_packages']:,} packages"
        )

        previous_kind = self.group_filter.currentData()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem(
            f"All families ({summary['semantic_records']:,})", None
        )
        self.group_table.setRowCount(len(inventory.semantic_groups))
        for row, group in enumerate(inventory.semantic_groups):
            self.group_filter.addItem(
                f"{group.title} ({len(group.records):,})", group.kind.value
            )
            values = (
                group.title,
                f"{len(group.records):,}",
                f"{len(group.package_ids):,}",
                group.author_note,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, group.kind.value)
                if column == 3:
                    item.setToolTip(value)
                self.group_table.setItem(row, column, item)
        restore_index = self.group_filter.findData(previous_kind)
        self.group_filter.setCurrentIndex(max(0, restore_index))
        self.group_filter.blockSignals(False)

        package_note = inventory.package_groups[0].ownership_note
        self.package_note.setText(
            f"Package note: {package_note} Exact asset IDs below remain the "
            "source of truth for preview and export."
        )
        # Never silent-gray stock jump: ready once inventory maps endzone family.
        stock_tip = (
            "Filter to the 235 per-team stock endzone layers. "
            "Browse and Export original PNG only — per-team writers are not "
            "proved; the focused editor owns package 6, which is one team's own "
            "endzone and not a shared layer."
        )
        self.stock_endzone_button.setEnabled(True)
        self.stock_endzone_button.setToolTip(stock_tip)
        self.stock_endzone_button.setProperty("disableReason", "")
        labelled = len(endzone_team_labels())
        self.contact_sheet_button.setEnabled(True)
        self.contact_sheet_button.setToolTip(
            "Render all 118 endzone packages into labelled sheets so a team's "
            f"endzone can be found by eye ({labelled} are already identified). "
            "A name search cannot work: the nicknames are not on the disc, only "
            "in Roster.ROS. Your game is opened read-only."
        )
        self.contact_sheet_button.setProperty("disableReason", "")

    def _selected_group(self):
        if self.inventory is None:
            return None
        value = self.group_filter.currentData()
        if not value:
            return None
        return self.inventory.semantic_group(FieldArtKind(value))

    def _group_changed(self, _index: int = -1) -> None:
        if self.inventory is None:
            self.browser.set_included_asset_ids(None)
            self.browser.set_context()
            return
        group = self._selected_group()
        if group is None:
            self.browser.set_included_asset_ids(
                record.asset_id for record in self.inventory.records
            )
            self.group_note.setText(
                "All seven reviewed families are visible. The map contains "
                f"{self.inventory.summary['txtr_records']} TXTR, "
                f"{self.inventory.summary['scne_records']} SCNE, and "
                f"{self.inventory.summary['curve_anim_records']} CurveAnim records; "
                "zero records are claimed editable."
            )
            self.group_table.clearSelection()
        else:
            self.browser.set_included_asset_ids(
                record.asset_id for record in group.records
            )
            self.group_note.setText(
                f"{group.title}: {len(group.records):,} records across "
                f"{len(group.package_ids):,} archive packages. {group.author_note}"
            )
            for row in range(self.group_table.rowCount()):
                item = self.group_table.item(row, 0)
                if item is not None and item.data(Qt.UserRole) == group.kind.value:
                    self.group_table.selectRow(row)
                    break
        self.browser.set_context()

    def _group_row_clicked(self, row: int, _column: int) -> None:
        item = self.group_table.item(row, 0)
        if item is None:
            return
        index = self.group_filter.findData(item.data(Qt.UserRole))
        if index >= 0:
            self.group_filter.setCurrentIndex(index)

    def focus_workspace_route(self, route: WorkspaceRoute, image: Path | None) -> bool:
        """Select one writable base texture handed over from an asset browser."""

        if not self.editor.focus_target(route.key):
            return False
        if image is not None:
            self.editor.stage_image(image)
        return True

    def set_context(self) -> None:
        self.editor.set_context()
        if not self.facade.source_ready:
            self.capabilities.set_cards(())
            self._clear_semantic_view(
                "Load your APF game to map Field Art.\n\n"
                "Next: File → Load game, then open Field Art. Stock NFL "
                "endzones appear in the semantic list (~118 packages). "
                "Format-18 layers, package-659 weave/dirtmaps, and the "
                "original six bases are writable; format-59 DXT5A layers "
                "stay browse/export-only."
            )
            self.browser.set_context()
            return

        catalog = self.facade.require_catalog()
        category_count = len(
            self.facade.browse_assets(
                category=ApfCategory.FIELD_ART,
                limit=len(catalog.assets) + 1,
            )
        )
        self.capabilities.set_cards(
            self.facade.capability_cards(ApfCategory.FIELD_ART),
            catalog_ready=True,
            inventory_count=category_count,
        )
        try:
            inventory = build_field_art_inventory(catalog)
        except FieldArtInventoryError as exc:
            self._clear_semantic_view(f"Semantic map needs review: {exc}")
            self.browser.set_context()
            return
        self._populate_semantic_view(inventory)
        self._group_changed()

    def refresh(self) -> None:
        self.editor.set_context()
        self.browser.refresh()


class StadiumStudioPage(QWidget):
    """Private stadium viewer plus the bounded same-count POSITION hand-off."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        # This compact product projection is retail-free and deliberately
        # validated at construction time.  If its proof boundary is changed,
        # the UI must be reviewed instead of silently unlocking a writer.
        self.material_findings = load_stadium_material_findings()
        self._scenes: tuple[ApfStadiumScene, ...] = ()
        self._visible_scenes: dict[str, ApfStadiumScene] = {}
        self._package_assets: dict[str, ApfAsset] = {}
        self._embedded_textures: dict[str, stadium_texture.EmbeddedTexture] = {}
        self._staged_embedded_textures: dict[int, tuple[Path, tuple[int, int]]] = {}
        self._texture_catalog: stadium_texture.StadiumTextureCatalog | None = None
        self._stadium_texture_preview_dir: Path | None = None
        self._preview: ApfStadiumPreview | None = None
        self._model: GltfWireframeModel | None = None
        self._mesh_targets: tuple[stadium_model_import.StadiumTarget, ...] = ()
        self._scene_generation = 0
        self._texture_generation = 0
        self._source_sha256: str | None = None
        self._selected_model_target: stadium_model_import.StadiumTarget | None = None
        self.destroyed.connect(self._cleanup_stadium_texture_previews)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(10)
        outer.addWidget(PageHeading(ApfCategory.STADIUMS))
        self.capabilities = CapabilityPanel(ApfCategory.STADIUMS)
        outer.addWidget(self.capabilities)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)

        scenes_panel = QFrame()
        scenes_panel.setObjectName("panel")
        scenes_panel.setMinimumWidth(245)
        scenes_panel.setMaximumWidth(320)
        scenes_box = QVBoxLayout(scenes_panel)
        scenes_box.setContentsMargins(14, 13, 14, 13)
        scenes_box.setSpacing(8)
        scenes_heading = QHBoxLayout()
        scenes_title = QLabel("Stadium scenes")
        scenes_title.setObjectName("panelTitle")
        self.scene_count = QLabel("Load a game")
        self.scene_count.setObjectName("countPill")
        scenes_heading.addWidget(scenes_title)
        scenes_heading.addStretch(1)
        scenes_heading.addWidget(self.scene_count)
        self.scene_search = QLineEdit()
        self.scene_search.setPlaceholderText("Search outer or scene ID…")
        self.scene_search.setClearButtonEnabled(True)
        self.scene_search.setAccessibleName("Search APF stadium scenes")
        self.scene_search.setToolTip(
            "Search exact stadium SCNE identities. Venue names are not joined to archive outers yet."
        )
        self.scene_list = QListWidget()
        self.scene_list.setObjectName("assetList")
        self.scene_list.setSpacing(2)
        scene_note = QLabel(
            "These are exact stadium SCNE records. The 31 roster stadium names are not guessed onto archive entries."
        )
        scene_note.setObjectName("mutedLabel")
        scene_note.setWordWrap(True)
        scenes_box.addLayout(scenes_heading)
        scenes_box.addWidget(self.scene_search)
        scenes_box.addWidget(self.scene_list, 1)
        scenes_box.addWidget(scene_note)
        splitter.addWidget(scenes_panel)

        view_panel = QFrame()
        view_panel.setObjectName("panel")
        view_panel.setMinimumWidth(500)
        view_box = QVBoxLayout(view_panel)
        view_box.setContentsMargins(14, 13, 14, 13)
        view_box.setSpacing(8)
        view_heading = QHBoxLayout()
        view_titles = QVBoxLayout()
        view_titles.setSpacing(1)
        self.scene_title = QLabel("Choose a stadium scene")
        self.scene_title.setObjectName("panelTitle")
        self.scene_metadata = QLabel(
            "Drag to orbit • Shift/middle-drag to pan • wheel to zoom • click a surface"
        )
        self.scene_metadata.setObjectName("mutedLabel")
        self.scene_metadata.setWordWrap(True)
        view_titles.addWidget(self.scene_title)
        view_titles.addWidget(self.scene_metadata)
        self.reset_view_button = QPushButton("Reset View")
        self.reset_view_button.setObjectName("secondaryButton")
        self.export_scene_button = QPushButton("Export 3D Scene ZIP…")
        self.export_scene_button.setObjectName("secondaryButton")
        self.export_model_button = QPushButton("Export selected mesh…")
        self.export_model_button.setObjectName("secondaryButton")
        self.import_model_button = QPushButton("Import edited mesh…")
        self.import_model_button.setObjectName("primaryButton")
        # Never silent-gray scene/view actions: teach select-scene wall.
        _scene_boot = (
            "Select a stadium scene first. Reset View / Export scene stay clickable."
        )
        self.reset_view_button.setEnabled(True)
        self.reset_view_button.setToolTip(_scene_boot)
        self.reset_view_button.setProperty("disableReason", _scene_boot)
        self.export_scene_button.setEnabled(True)
        self.export_scene_button.setToolTip(_scene_boot)
        self.export_scene_button.setProperty("disableReason", _scene_boot)
        # Never silent-gray: mesh import/export stay clickable and explain.
        self.export_model_button.setEnabled(True)
        self.import_model_button.setEnabled(True)
        # Finding an editable mesh used to mean clicking around the wireframe
        # until one of the 77 authorized nodes happened to be under the cursor;
        # 12 of the scene's 89 nodes are not authorized, and nothing on screen
        # said which. The picker lists every authorized target by name so the
        # editable set is a list, not a hunt.
        self.mesh_target = QComboBox()
        self.mesh_target.setObjectName("comboField")
        self.mesh_target.setMinimumWidth(230)
        self.mesh_target.setAccessibleName("Editable stadium mesh")
        self.mesh_target.setToolTip(
            "Every catalog-authorized POSITION target in this scene. Choosing "
            "one selects it for Export/Import and highlights it in the view; "
            "clicking a surface in the view still works and updates this list."
        )
        self.mesh_target.addItem("Editable meshes — load a stadium scene", None)
        self.mesh_target.currentIndexChanged.connect(self._mesh_target_chosen)
        self._refresh_mesh_action_buttons()
        view_heading.addLayout(view_titles, 1)
        view_heading.addWidget(self.mesh_target)
        view_heading.addWidget(self.reset_view_button)
        view_heading.addWidget(self.export_scene_button)
        view_heading.addWidget(self.export_model_button)
        view_heading.addWidget(self.import_model_button)
        self.viewport = StadiumViewport()
        self.viewport.setMinimumSize(480, 330)
        self.surface_identity = QLabel("No surface selected")
        self.surface_identity.setObjectName("codeLabel")
        self.surface_identity.setWordWrap(True)
        self.surface_boundary = QLabel(
            "Texture ownership unresolved. APF glTF currently contains geometry only; a clicked surface is never presented as owning a package texture."
        )
        self.surface_boundary.setObjectName("findingsNote")
        self.surface_boundary.setWordWrap(True)
        self.material_findings_note = QLabel(
            f"Material experiment: {self.material_findings.author_summary}"
        )
        self.material_findings_note.setObjectName("findingText")
        self.material_findings_note.setWordWrap(True)
        self.material_findings_note.setToolTip(
            "Best next experiment: "
            f"{self.material_findings.best_next_experiment}"
        )
        view_box.addLayout(view_heading)
        view_box.addWidget(self.viewport, 1)
        view_box.addWidget(self.surface_identity)
        view_box.addWidget(self.surface_boundary)
        view_box.addWidget(self.material_findings_note)
        splitter.addWidget(view_panel)

        package_panel = QFrame()
        package_panel.setObjectName("panel")
        package_panel.setMinimumWidth(320)
        package_panel.setMaximumWidth(410)
        package_box = QVBoxLayout(package_panel)
        package_box.setContentsMargins(14, 13, 14, 13)
        package_box.setSpacing(8)
        package_heading = QHBoxLayout()
        self.package_panel_title = QLabel("Owning outer package")
        self.package_panel_title.setObjectName("panelTitle")
        self.package_count = QLabel("0 records")
        self.package_count.setObjectName("countPill")
        package_heading.addWidget(self.package_panel_title)
        package_heading.addStretch(1)
        package_heading.addWidget(self.package_count)
        self.package_list = QListWidget()
        self.package_list.setObjectName("assetList")
        self.package_list.setSpacing(1)
        self.package_list.setMaximumHeight(190)
        self.package_preview = ImageDropLabel(
            "Choose a package texture to prepare its private PNG preview. You "
            "can also drop a replacement image here — any size or format works."
        )
        self.package_preview.setAcceptDrops(False)
        self.package_preview.pngDropped.connect(
            self._replace_embedded_texture_from_drop
        )
        self.package_preview.setMinimumHeight(185)
        self.package_preview.setMaximumHeight(245)
        self.package_title = QLabel("Choose a package record")
        self.package_title.setObjectName("codeLabel")
        self.package_title.setWordWrap(True)
        self.package_detail = QLabel(
            "Related records share the same outer archive package. Shared packaging does not prove a surface/material relationship."
        )
        self.package_detail.setObjectName("findingText")
        self.package_detail.setWordWrap(True)
        package_actions = QHBoxLayout()
        package_actions.setSpacing(7)
        self.export_package_button = QPushButton("Export…")
        self.export_package_button.setObjectName("secondaryButton")
        self.replace_package_button = QPushButton("Replace (locked)")
        self.replace_package_button.setObjectName("primaryButton")
        self.revert_package_button = QPushButton("Revert")
        self.revert_package_button.setObjectName("dangerQuietButton")
        self.build_package_button = QPushButton("Build copied 1A…")
        self.build_package_button.setObjectName("secondaryButton")
        # Never silent-gray at construction either.
        self.export_package_button.setEnabled(True)
        self.replace_package_button.setEnabled(True)
        self.revert_package_button.setEnabled(True)
        self.build_package_button.setEnabled(True)
        self.build_package_button.setVisible(True)
        unresolved = (
            "Package texture replacement remains unavailable until a surface owns "
            "an editable embedded TXTR. Related package rows are not surface-owned. "
            "Use selected-mesh controls for the separate same-count POSITION-only "
            "geometry lane. Click still explains — buttons stay clickable."
        )
        self.replace_package_button.setToolTip(unresolved)
        self.replace_package_button.setProperty("disableReason", unresolved)
        self.revert_package_button.setToolTip(unresolved)
        self.revert_package_button.setProperty("disableReason", unresolved)
        self.export_package_button.setToolTip(
            "Export after a package record or editable embedded texture is selected."
        )
        self.export_package_button.setProperty(
            "disableReason",
            "Select a stadium scene and package record (or surface texture) first.",
        )
        self.build_package_button.setToolTip(
            "Stage an editable embedded texture first, then Build a copied 1A."
        )
        self.build_package_button.setProperty(
            "disableReason",
            "Stage an editable embedded texture first, then Build a copied 1A.",
        )
        package_actions.addWidget(self.export_package_button)
        package_actions.addWidget(self.replace_package_button)
        package_actions.addWidget(self.revert_package_button)
        package_actions.addWidget(self.build_package_button)
        package_box.addLayout(package_heading)
        package_box.addWidget(self.package_list)
        package_box.addWidget(self.package_preview, 1)
        package_box.addWidget(self.package_title)
        package_box.addWidget(self.package_detail)
        package_box.addLayout(package_actions)
        splitter.addWidget(package_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        outer.addWidget(splitter, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_scene_filter)
        self.scene_search.textChanged.connect(lambda _text: self._search_timer.start())
        self.scene_list.currentItemChanged.connect(self._scene_selected)
        self.package_list.currentItemChanged.connect(self._package_selected)
        self.viewport.surfaceSelected.connect(self._surface_selected)
        self.reset_view_button.clicked.connect(self.viewport.reset_view)
        self.export_scene_button.clicked.connect(self._export_scene)
        self.export_model_button.clicked.connect(self._export_selected_mesh)
        self.import_model_button.clicked.connect(self._import_selected_mesh)
        self.export_package_button.clicked.connect(self._export_package_asset)
        self.replace_package_button.clicked.connect(self._replace_embedded_texture)
        self.revert_package_button.clicked.connect(self._revert_embedded_texture)
        self.build_package_button.clicked.connect(self._build_embedded_texture_output)

    def set_context(self) -> None:
        if not self.facade.source_ready:
            self._source_sha256 = None
            self._texture_catalog = None
            self._scenes = ()
            self._clear_scene("Load your APF game to browse stadium geometry.")
            self.capabilities.set_cards(())
            self.scene_list.clear()
            self.scene_count.setText("Load a game")
            return
        catalog = self.facade.require_catalog()
        inventory_count = len(
            self.facade.browse_assets(
                category=ApfCategory.STADIUMS,
                limit=len(catalog.assets) + 1,
            )
        )
        self.capabilities.set_cards(
            self.facade.capability_cards(ApfCategory.STADIUMS),
            catalog_ready=True,
            inventory_count=inventory_count,
        )
        source_sha = self.facade.source.source_sha256 if self.facade.source else None
        if source_sha != self._source_sha256:
            self._cleanup_stadium_texture_previews()
            self._staged_embedded_textures = {}
            self._source_sha256 = source_sha
            self._texture_catalog = None
            self._preview = None
            self._model = None
            self._scenes = self.facade.stadium_scenes()
            self._apply_scene_filter()
        elif not self._scenes:
            self._scenes = self.facade.stadium_scenes()
            self._apply_scene_filter()

    def _cleanup_stadium_texture_previews(self, *_args: object) -> None:
        root = self._stadium_texture_preview_dir
        self._stadium_texture_preview_dir = None
        self._staged_embedded_textures = {}
        if root is not None and root.name.startswith("apf-stadium-texture-"):
            shutil.rmtree(root, ignore_errors=True)

    def _stadium_texture_preview_path(self, texture_index: int) -> Path:
        if self._stadium_texture_preview_dir is None:
            self._stadium_texture_preview_dir = Path(
                tempfile.mkdtemp(prefix="apf-stadium-texture-")
            )
        return self._stadium_texture_preview_dir / (
            f"texture-{texture_index:03d}-{uuid4().hex}.png"
        )

    def refresh(self) -> None:
        if not self.facade.source_ready:
            self.set_context()
            return
        selected = self._selected_scene()
        selected_id = selected.asset_id if selected else None
        self._scenes = self.facade.stadium_scenes()
        self._apply_scene_filter(preserve_asset_id=selected_id, open_selection=False)

    def _apply_scene_filter(
        self,
        preserve_asset_id: str | None = None,
        *,
        open_selection: bool = True,
    ) -> None:
        if preserve_asset_id is None:
            selected = self._selected_scene()
            preserve_asset_id = selected.asset_id if selected else None
        needle = self.scene_search.text().strip().casefold()
        rows = tuple(
            scene
            for scene in self._scenes
            if not needle
            or needle
            in (
                f"{scene.asset_id} outer {scene.outer_index} inner {scene.inner_index}"
            ).casefold()
        )
        self._visible_scenes = {scene.asset_id: scene for scene in rows}
        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        selected_row = -1
        for index, scene in enumerate(rows):
            item = QListWidgetItem(
                f"Outer {scene.outer_index} / inner {scene.inner_index}"
            )
            item.setData(Qt.UserRole, scene.asset_id)
            item.setToolTip(
                f"{scene.asset_id} • {scene.decoded_size:,} decoded bytes • "
                f"{scene.package_asset_count} package records"
            )
            item.setSizeHint(QSize(245, 42))
            self.scene_list.addItem(item)
            if scene.asset_id == preserve_asset_id:
                selected_row = index
        if selected_row < 0 and rows:
            selected_row = 0
        if selected_row >= 0:
            self.scene_list.setCurrentRow(selected_row)
        self.scene_list.blockSignals(False)
        self.scene_count.setText(f"{len(rows):,} / {len(self._scenes):,}")
        if not rows:
            self._clear_scene("No stadium SCNE matches that search.")
        elif open_selection:
            self._scene_selected(self.scene_list.currentItem(), None)

    def _selected_scene(self) -> ApfStadiumScene | None:
        item = self.scene_list.currentItem()
        return (
            self._visible_scenes.get(str(item.data(Qt.UserRole)))
            if item is not None
            else None
        )

    def focus_workspace_route(
        self, route: WorkspaceRoute, _image: Path | None = None
    ) -> bool:
        """Open the stadium scene handed over from an asset browser.

        No image is staged here: an embedded stadium texture is chosen from the
        package list on this page, so the hand-off lands the user on the scene
        and lets them pick the exact texture.
        """

        outer, _, inner = route.key.partition(":")
        target = f"apf:outer:{outer}:inner:{inner}"
        if not any(scene.asset_id == target for scene in self._scenes):
            return False
        # Cleared before the filter runs, so an active search cannot hide the
        # scene the user was just sent to.
        self.scene_search.clear()
        self._apply_scene_filter(preserve_asset_id=target)
        scene = self._selected_scene()
        return scene is not None and scene.asset_id == target

    def _scene_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        scene = self._visible_scenes.get(str(current.data(Qt.UserRole)))
        if scene is None:
            return
        self._scene_generation += 1
        generation = self._scene_generation
        self._preview = None
        self._model = None
        self._texture_catalog = None
        self._embedded_textures = {}
        self._texture_catalog = None
        self._embedded_textures = {}
        self._selected_model_target = None
        self.viewport.set_model(None)
        self.scene_title.setText(f"Outer {scene.outer_index} • stadium SCNE")
        self.scene_metadata.setText(
            "Preparing private geometry from your game…"
        )
        self.surface_identity.setText("No surface selected")
        self.surface_boundary.setText(
            "Texture ownership unresolved. Related package textures are candidates, not surface owners."
        )
        prep_tip = "Stadium geometry is still preparing — wait for the private view."
        self.reset_view_button.setEnabled(True)
        self.reset_view_button.setToolTip(prep_tip)
        self.reset_view_button.setProperty("disableReason", prep_tip)
        export_ready = (
            "Export the private glTF, binary buffer, and evidence manifest. "
            "Geometry is raw game data; a root node scales it from centimetres "
            "to metres so it opens at a sane size."
        )
        self.export_scene_button.setEnabled(True)
        self.export_scene_button.setToolTip(export_ready)
        self.export_scene_button.setProperty("disableReason", "")
        self._selected_model_target = None
        self._populate_mesh_targets(scene)
        self._refresh_mesh_action_buttons()
        self._populate_package(self.facade.stadium_package_assets(scene))

        def operation(
            progress: Callable[[str, int, int], None]
        ) -> tuple[
            ApfStadiumPreview,
            GltfWireframeModel,
            stadium_texture.StadiumTextureCatalog | None,
        ]:
            preview = self.facade.prepare_stadium_scene(scene, progress)
            progress("Building the interactive stadium view", 0, 1)
            model = GltfWireframeModel.load(preview.gltf_path, preview.bin_path)
            texture_catalog = None
            source = self.facade.source
            if (
                scene.outer_index == stadium_texture.OUTER_INDEX
                and scene.inner_index == stadium_texture.INNER_INDEX
                and source is not None
            ):
                progress("Resolving draw, material, and texture ownership", 0, 1)
                texture_catalog = stadium_texture.load_catalog(source.game_root)
            progress("Interactive stadium view ready", 1, 1)
            return preview, model, texture_catalog

        def complete(result: object) -> None:
            if generation != self._scene_generation:
                return
            preview, model, texture_catalog = result  # type: ignore[misc]
            self._preview = preview
            self._model = model
            self._texture_catalog = texture_catalog
            self.viewport.set_model(model)
            self.reset_view_button.setEnabled(True)
            self.reset_view_button.setToolTip("Reset the stadium viewport camera.")
            self.reset_view_button.setProperty("disableReason", "")
            self.scene_metadata.setText(
                f"{preview.mesh_count:,} meshes • {preview.vertex_count:,} vertices • "
                f"{preview.triangle_count:,} source triangles • "
                f"{preview.skipped_mesh_count:,} unsupported meshes skipped"
            )
            if texture_catalog is not None:
                editable = sum(texture.editable for texture in texture_catalog.textures)
                self.package_panel_title.setText("Selected surface textures")
                self.material_findings_note.setText(
                    "Exact static join: 89 scene nodes → 84 draw-used materials → "
                    f"78 embedded textures. {editable} have bounded full-mip writers; "
                    "every owned texture has an exact transport."
                )
                self.material_findings_note.setToolTip(
                    "Click a rendered surface to list only the TXTR descriptors named "
                    "by its serialized material command payload."
                )
                self.surface_boundary.setText(
                    "Texture ownership is resolved for this authenticated outer-14 / "
                    "inner-8 scene. Click a surface to see its exact embedded textures."
                )
                self._populate_embedded_textures(())
            self._selected_model_target = None
            self._refresh_mesh_action_buttons()

        self.run_task("Opening APF Stadium Studio", operation, complete, False)

    def _clear_scene(self, message: str) -> None:
        self._scene_generation += 1
        self._texture_generation += 1
        self._preview = None
        self._model = None
        self._selected_model_target = None
        self.viewport.set_model(None)
        self.scene_title.setText("Choose a stadium scene")
        self.scene_metadata.setText(message)
        self.surface_identity.setText("No surface selected")
        tip = (
            "Select a stadium scene first. Reset View / Export scene stay clickable."
        )
        self.reset_view_button.setEnabled(True)
        self.reset_view_button.setToolTip(tip)
        self.reset_view_button.setProperty("disableReason", tip)
        self.export_scene_button.setEnabled(True)
        self.export_scene_button.setToolTip(tip)
        self.export_scene_button.setProperty("disableReason", tip)
        self._selected_model_target = None
        self._populate_mesh_targets(None)
        self._refresh_mesh_action_buttons()
        self.package_panel_title.setText("Owning outer package")
        self._populate_package(())

    def _populate_mesh_targets(self, scene: ApfStadiumScene | None) -> None:
        """List every authorized POSITION target in the opened scene.

        The catalog is the authority for which meshes are writable, so the
        picker is derived from it rather than from anything the viewer guesses
        about the geometry.
        """

        targets = (
            tuple(
                target
                for target in stadium_model_import.targets()
                if target.outer_index == scene.outer_index
                and target.inner_index == scene.inner_index
            )
            if scene is not None
            else ()
        )
        self._mesh_targets = targets
        self.mesh_target.blockSignals(True)
        self.mesh_target.clear()
        if not targets:
            self.mesh_target.addItem(
                "No editable meshes in this scene", None
            )
            self.mesh_target.setEnabled(False)
            self.mesh_target.setToolTip(
                "This stadium scene has no catalog-authorized POSITION target, "
                "so it is view and scene-export only. The scene that does carry "
                "them lists its editable meshes here."
            )
        else:
            self.mesh_target.addItem(
                f"Choose one of {len(targets)} editable meshes…", None
            )
            for target in targets:
                self.mesh_target.addItem(
                    f"{target.node_name} — {target.vertex_count:,} vertices",
                    target,
                )
            self.mesh_target.setEnabled(True)
            self.mesh_target.setToolTip(
                f"All {len(targets)} catalog-authorized POSITION targets in "
                "this scene. Choosing one selects it for Export/Import and "
                "highlights it in the view; clicking a surface in the view "
                "still works and updates this list."
            )
        self.mesh_target.setCurrentIndex(0)
        self.mesh_target.blockSignals(False)
        # The picker and the Export/Import walls describe the same state, so
        # they are never refreshed apart.
        self._refresh_mesh_action_buttons()

    def _sync_mesh_target_choice(self) -> None:
        """Show the currently selected target in the picker without recursing."""

        target = self._selected_model_target
        self.mesh_target.blockSignals(True)
        index = 0
        if target is not None:
            found = self.mesh_target.findData(target)
            if found >= 0:
                index = found
        self.mesh_target.setCurrentIndex(index)
        self.mesh_target.blockSignals(False)

    def _mesh_target_chosen(self, _index: int) -> None:
        """Select a mesh from the picker and mirror it into the 3D view."""

        target = self.mesh_target.currentData()
        if target is None:
            return
        self._selected_model_target = target
        model = self._model
        surface = None
        if model is not None:
            surface = next(
                (
                    (identity.mesh_index, identity.primitive_index)
                    for identity in model.surfaces
                    if target.node_index in identity.apf_scene_node_indices
                ),
                None,
            )
        if surface is not None:
            # Re-uses the click path so the identity/ownership panes, the
            # highlight, and the buttons all describe one selection.
            self.viewport.set_selected_surface(*surface)
            self._surface_selected(*surface)
            return
        self.surface_identity.setText(
            f"{target.node_name} • APF scene node {target.node_index} • "
            f"{target.vertex_count:,} vertices"
        )
        self.surface_boundary.setText(
            f"Editable geometry target {target.target_id}: export then re-import "
            "the exact same vertex count and expanded topology. Only POSITION "
            "may change; original UVs, normals, materials and attachments stay "
            "byte-identical."
        )
        self._refresh_mesh_action_buttons()

    def _refresh_mesh_action_buttons(self) -> None:
        """Keep stadium mesh Import/Export clickable; gray never means silent no-op."""

        ready = bool(getattr(self.facade, "source_ready", False))
        has_preview = self._preview is not None
        has_target = self._selected_model_target is not None and has_preview
        if not ready:
            block = (
                "Load your APF game first. Stadium mesh export/import needs the "
                "retail archive (0A/1A). Click still explains this — buttons stay "
                "clickable so a gray control is never a dead no-op."
            )
        elif not has_preview:
            block = (
                "Open a stadium scene from the list first, wait for the private "
                "geometry preview, then click a catalog-authorized surface. "
                "Click still explains this."
            )
        elif not self._mesh_targets:
            block = (
                "This stadium scene carries no catalog-authorized POSITION "
                "target, so it is view and scene-export only. Open the scene "
                "whose Editable meshes picker lists targets. Click still "
                "explains this."
            )
        elif not has_target:
            block = (
                f"Choose one of the {len(self._mesh_targets)} editable meshes "
                "from the picker above, or click that surface in the view. "
                "Other surfaces are view-only. Click still explains this."
            )
        else:
            block = ""
        export_tip = (
            block
            if block
            else (
                "Export this surface as an editable glTF (POSITION targets). "
                "Keep vertex count and triangles exact; only positions may change."
            )
        )
        import_tip = (
            block
            if block
            else (
                "Import a same-topology POSITION-only glTF for this surface into a "
                "new verified volume copy. Never mutates your original archive."
            )
        )
        self.export_model_button.setEnabled(True)
        self.import_model_button.setEnabled(True)
        self.export_model_button.setToolTip(export_tip)
        self.import_model_button.setToolTip(import_tip)
        self.export_model_button.setProperty("disableReason", block)
        self.import_model_button.setProperty("disableReason", block)

    def _surface_selected(self, mesh_index: int, primitive_index: int) -> None:
        model = self._model
        if model is None:
            return
        identity = model.surface_identity(mesh_index, primitive_index)
        if identity is None:
            self._selected_model_target = None
            self._sync_mesh_target_choice()
            self._refresh_mesh_action_buttons()
            self.surface_identity.setText(
                f"Mesh {mesh_index} / primitive {primitive_index}"
            )
            return
        apf_nodes = (
            ", ".join(str(value) for value in identity.apf_scene_node_indices)
            or "not retained"
        )
        source_mesh = (
            str(identity.apf_source_mesh_index)
            if identity.apf_source_mesh_index is not None
            else "not retained"
        )
        self.surface_identity.setText(
            f"{identity.mesh_name} • glTF mesh {mesh_index} / primitive {primitive_index}\n"
            f"APF scene node {apf_nodes} • source mesh {source_mesh}"
        )
        scene = self._selected_scene()
        selected_target = (
            stadium_model_import.target_for_surface(
                scene.outer_index,
                scene.inner_index,
                identity.apf_scene_node_indices,
            )
            if scene is not None
            else None
        )
        self._selected_model_target = selected_target
        # A click in the view and a choice in the picker are the same selection.
        self._sync_mesh_target_choice()
        texture_ownership = ""
        if self._texture_catalog is not None:
            owned = self._texture_catalog.textures_for_nodes(
                identity.apf_scene_node_indices
            )
            self._populate_embedded_textures(owned)
            slots = sorted(
                {
                    slot
                    for node_index in identity.apf_scene_node_indices
                    for surface in self._texture_catalog.surfaces
                    if surface.node_index == node_index
                    for slot in surface.material_slots
                }
            )
            texture_ownership = (
                f" Exact serialized ownership resolves material slots {slots or 'none'} "
                f"to {len(owned)} embedded texture{'s' if len(owned) != 1 else ''}."
            )
        self._refresh_mesh_action_buttons()
        if selected_target is None:
            self.surface_boundary.setText(
                "Surface selected, but it is not one of the 77 catalog-authorized "
                "outer-14/inner-8 POSITION targets."
                + texture_ownership
            )
        else:
            self.surface_boundary.setText(
                f"Editable geometry target {selected_target.target_id}: export then "
                "re-import the exact same vertex count and expanded topology. Only "
                "POSITION may change; original UVs, normals, materials and attachments "
                "stay byte-identical."
                + texture_ownership
            )

    def _export_selected_mesh(self) -> None:
        reason = str(
            self.export_model_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export stadium mesh yet",
                reason
                + "\n\nFix: load APF → open a stadium scene → click an authorized "
                "surface → Export selected mesh.",
            )
            return
        target = self._selected_model_target
        preview = self._preview
        if target is None or preview is None:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export editable APF stadium mesh",
            str(Path.home() / f"{target.target_id.replace('.', '-')}.gltf"),
            "glTF 2.0 (*.gltf)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".gltf")
        self.run_task(
            "Exporting editable stadium mesh",
            lambda _progress: stadium_model_import.export_editable_mesh(
                preview.gltf_path, target.target_id, path
            ),
            lambda result: QMessageBox.information(
                self,
                "Editable stadium mesh exported",
                f"Saved:\n{result.gltf_path}\n{result.bin_path}\n\n"
                "Keep the vertex count and triangles exact, apply object transforms, "
                "and export POSITION only. The game keeps its original UVs, normals, "
                "materials and attachments during import.",
            ),
            True,
        )

    def _import_selected_mesh(self) -> None:
        reason = str(
            self.import_model_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot import stadium mesh yet",
                reason
                + "\n\nFix: load APF → open a stadium scene → click an authorized "
                "surface → export glTF first → edit POSITION only → Import.\n\n"
                "Import builds a new volume copy — it never mutates your original.",
            )
            return
        target = self._selected_model_target
        preview = self._preview
        source = self.facade.source
        if target is None or preview is None or source is None:
            return
        edited, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose edited APF stadium mesh",
            str(Path.home()),
            "glTF 2.0 (*.gltf)",
        )
        if not edited:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Choose a new stadium output-folder name",
            str(Path.home() / f"{target.target_id.replace('.', '-')}-copied-1A"),
            "Output folder name (*)",
        )
        if not destination:
            return
        output = Path(destination)
        self.run_task(
            "Importing and independently verifying stadium mesh",
            lambda _progress: stadium_model_import.import_edited_mesh(
                source.game_root,
                preview.gltf_path,
                target.target_id,
                Path(edited),
                output,
            ),
            lambda result: QMessageBox.information(
                self,
                "Stadium mesh output verified",
                f"Saved a copied 1A and manifest to:\n{result.output_directory}\n\n"
                f"Changed decoded POSITION bytes: {result.changed_byte_count:,}. "
                "The source game was not modified. Runtime visibility still requires "
                "your own target-system test.",
            ),
            True,
        )

    def _populate_embedded_textures(
        self, textures: Iterable[stadium_texture.EmbeddedTexture]
    ) -> None:
        values = tuple(textures)
        self._package_assets = {}
        self._embedded_textures = {texture.selector: texture for texture in values}
        self.package_list.blockSignals(True)
        self.package_list.clear()
        for texture in values:
            suffix = "editable" if texture.editable else "locked descriptor"
            item = QListWidgetItem(f"{texture.index:02d} • {texture.label} • {suffix}")
            item.setData(Qt.UserRole, texture.selector)
            item.setToolTip(
                f"{texture.selector} • material slots {list(texture.material_slots)}\n"
                "Exact draw → material command payload → embedded TXTR ownership."
            )
            self.package_list.addItem(item)
        if values:
            self.package_list.setCurrentRow(0)
        self.package_list.blockSignals(False)
        self.package_count.setText(f"{len(values):,} textures")
        if values:
            self._package_selected(self.package_list.currentItem(), None)
        else:
            self.package_title.setText("Click a stadium surface")
            self.package_detail.setText(
                "Its serialized draw/material route will populate only the embedded "
                "textures that surface owns."
            )
            self.package_preview.set_message("No surface texture selected.")
            surface_tip = (
                "Click a stadium surface first so exact embedded textures appear. "
                "Buttons stay clickable to explain this."
            )
            self.export_package_button.setEnabled(True)
            self.replace_package_button.setEnabled(True)
            self.revert_package_button.setEnabled(True)
            self.build_package_button.setEnabled(True)
            for button in (
                self.export_package_button,
                self.replace_package_button,
                self.revert_package_button,
                self.build_package_button,
            ):
                button.setToolTip(surface_tip)
                button.setProperty("disableReason", surface_tip)

    def _selected_embedded_texture(
        self,
    ) -> stadium_texture.EmbeddedTexture | None:
        item = self.package_list.currentItem()
        return (
            self._embedded_textures.get(str(item.data(Qt.UserRole)))
            if item is not None
            else None
        )

    def _populate_package(self, assets: Iterable[ApfAsset]) -> None:
        values = tuple(assets)
        self._embedded_textures = {}
        self.revert_package_button.setVisible(True)
        self.build_package_button.setVisible(True)
        package_lock = (
            "Related package records share the scene outer; they are not "
            "surface-owned. Click a rendered surface for editable embedded "
            "TXTRs. Use selected-mesh controls for the separate same-count "
            "POSITION-only geometry lane. Buttons stay clickable to explain."
        )
        self.replace_package_button.setText("Replace (locked)")
        self.replace_package_button.setEnabled(True)
        self.replace_package_button.setToolTip(package_lock)
        self.replace_package_button.setProperty("disableReason", package_lock)
        self.export_package_button.setEnabled(True)
        self.export_package_button.setToolTip(
            "Export package records when selected (TXTR PNG or raw). "
            "Surface-owned editable embeds use the exact embedded path."
        )
        self.export_package_button.setProperty("disableReason", "")
        self.revert_package_button.setEnabled(True)
        self.revert_package_button.setProperty(
            "disableReason", "Nothing staged on this package-level path."
        )
        self.build_package_button.setEnabled(True)
        self.build_package_button.setProperty(
            "disableReason",
            "Stage an editable embedded surface texture first, then Build.",
        )
        self._package_assets = {asset.asset_id: asset for asset in values}
        self.package_list.blockSignals(True)
        self.package_list.clear()
        first_texture = -1
        for index, asset in enumerate(values):
            status = _status_text(asset.status)
            item = QListWidgetItem(
                f"{asset.inner_index if asset.inner_index is not None else 'outer'} • "
                f"{asset.name} • {asset.type_name}"
            )
            item.setData(Qt.UserRole, asset.asset_id)
            item.setToolTip(
                f"{status} • {asset.asset_id}\n"
                "Same outer package only; surface ownership is unresolved."
            )
            self.package_list.addItem(item)
            if first_texture < 0 and asset.type_name == "TXTR":
                first_texture = index
        if values:
            self.package_list.setCurrentRow(first_texture if first_texture >= 0 else 0)
        self.package_list.blockSignals(False)
        self.package_count.setText(f"{len(values):,} records")
        if values:
            self._package_selected(self.package_list.currentItem(), None)
        else:
            self.package_title.setText("Choose a package record")
            self.package_detail.setText(
                "Related package assets appear after a stadium scene is selected."
            )
            self.package_preview.set_message("No package record selected.")
            empty_tip = (
                "Select a stadium scene first, then a package record or surface."
            )
            self.export_package_button.setEnabled(True)
            self.export_package_button.setToolTip(empty_tip)
            self.export_package_button.setProperty("disableReason", empty_tip)

    def _selected_package_asset(self) -> ApfAsset | None:
        item = self.package_list.currentItem()
        return (
            self._package_assets.get(str(item.data(Qt.UserRole)))
            if item is not None
            else None
        )

    def _package_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        embedded = self._embedded_textures.get(str(current.data(Qt.UserRole)))
        if embedded is not None:
            self._embedded_texture_selected(embedded)
            return
        asset = self._package_assets.get(str(current.data(Qt.UserRole)))
        if asset is None:
            return
        self._texture_generation += 1
        generation = self._texture_generation
        self.package_title.setText(
            f"{asset.name} • {asset.type_name} • {asset.location}"
        )
        self.package_detail.setText(
            f"{_asset_status_text(asset)} • {_human_bytes(asset.decoded_size)} decoded.\n"
            "This record shares the scene's outer package; that does not prove it belongs to a clicked surface."
        )
        ready = bool(getattr(self.facade, "source_ready", False))
        export_tip = (
            f"Export {asset.name} ({asset.type_name}) from the related package."
            if ready
            else "Load your APF game first to export package records."
        )
        replace_tip = (
            "Related package records are not surface-owned. Click a rendered "
            "surface for editable embedded TXTRs with proved writers. Use "
            "selected-mesh controls for the separate same-count POSITION-only "
            "geometry lane. Click still explains this wall."
        )
        self.export_package_button.setEnabled(True)
        self.export_package_button.setToolTip(export_tip)
        self.export_package_button.setProperty(
            "disableReason", "" if ready else export_tip
        )
        self.replace_package_button.setText("Replace (locked)")
        self.replace_package_button.setEnabled(True)
        self.replace_package_button.setToolTip(replace_tip)
        self.replace_package_button.setProperty("disableReason", replace_tip)
        self.revert_package_button.setEnabled(True)
        self.revert_package_button.setProperty(
            "disableReason", "Nothing staged on this package-level path."
        )
        if asset.type_name != "TXTR":
            self.package_preview.set_message(
                "Exact raw export is available. This record has no PNG preview."
            )
            return
        self.package_preview.set_loading("Preparing package texture from your game…")

        def operation(progress: Callable[[str, int, int], None]) -> tuple[bool, object]:
            try:
                return True, self.facade.preview_asset(asset.asset_id, progress)
            except Exception as exc:
                return False, str(exc)

        def complete(result: object) -> None:
            if generation != self._texture_generation or self._selected_package_asset() != asset:
                return
            ok, value = result  # type: ignore[misc]
            if ok:
                self.package_preview.set_image(Path(value))
            else:
                self.package_preview.set_error(str(value))

        def _package_preview_watchdog() -> None:
            if generation != self._texture_generation:
                return
            if str(self.package_preview.property("previewState") or "") != "loading":
                return
            self.package_preview.set_error(
                f"{asset.name}: package preview still preparing after 45s. "
                "Re-select the record or Export raw."
            )

        QTimer.singleShot(45_000, _package_preview_watchdog)
        self.run_task("Preparing stadium package texture", operation, complete, False)

    def _embedded_texture_selected(
        self, texture: stadium_texture.EmbeddedTexture
    ) -> None:
        self._texture_generation += 1
        generation = self._texture_generation
        source = self.facade.source
        self.package_title.setText(
            f"{texture.selector} • ID 0x{texture.texture_id:08x}"
        )
        self.package_detail.setText(
            f"{texture.width}×{texture.height} {texture.format_name} • "
            f"{_human_bytes(texture.payload_length)} full mip allocation • "
            f"material slots {list(texture.material_slots)}.\n"
            + (
                "Replace accepts any image (any size or format), resizes it to "
                "this slot, regenerates every declared mip, and builds a "
                "separately verified copied 1A."
                if texture.editable
                else "This unusual descriptor has no proved writer and remains locked."
            )
        )
        available = source is not None and texture.editable
        staged = self._staged_embedded_textures.get(texture.index)
        # Never silent-gray: stay clickable; disableReason + click-to-explain when locked.
        export_tip = (
            f"Export {texture.selector} as PNG from the exact embedded TXTR."
            if available
            else (
                "This embedded texture descriptor has no proved bounded writer "
                "(or no game is loaded). Click still explains — buttons stay "
                "clickable so gray never means a silent no-op."
            )
        )
        replace_tip = (
            "Choose any image — any size or format works; Mod Studio resizes it "
            "to this slot and snapshots it inside this private session. Build "
            "then regenerates the complete mip chain in a copied 1A; your source "
            "remains read-only."
            if available
            else (
                "This embedded texture descriptor has no proved bounded writer. "
                "Click still explains this. Export raw/scene instead, or pick a "
                "surface whose material owns an editable embedded TXTR."
            )
        )
        self.export_package_button.setEnabled(True)
        self.export_package_button.setToolTip(export_tip)
        self.export_package_button.setProperty(
            "disableReason", "" if available else export_tip
        )
        self.replace_package_button.setText(
            "Replace image…" if available else "Replace (locked)"
        )
        self.replace_package_button.setEnabled(True)
        self.replace_package_button.setToolTip(replace_tip)
        self.replace_package_button.setProperty(
            "disableReason", "" if available else replace_tip
        )
        # Drop parity with the Replace button (drops only when writable).
        self.package_preview.setAcceptDrops(available)
        self.revert_package_button.setVisible(True)
        self.revert_package_button.setEnabled(True)
        self.revert_package_button.setToolTip(
            "Clear the staged embedded texture snapshot."
            if staged is not None
            else "Nothing staged to revert for this embedded texture."
        )
        self.revert_package_button.setProperty(
            "disableReason",
            "" if staged is not None else "Nothing staged to revert for this texture.",
        )
        self.build_package_button.setVisible(True)
        self.build_package_button.setEnabled(True)
        self.build_package_button.setToolTip(
            "Build a verified copied 1A with staged embedded textures."
            if staged is not None
            else "Stage a replacement image first, then Build."
        )
        self.build_package_button.setProperty(
            "disableReason",
            "" if staged is not None else "Stage a replacement image first, then Build.",
        )
        if not available:
            self.package_preview.set_message(
                "PNG preview/export is unavailable for this locked descriptor. "
                "Replace stays clickable to explain the wall."
            )
            return
        if staged is not None:
            staged_path, source_size = staged
            self.package_preview.set_image(staged_path)
            self.package_detail.setText(
                self.package_detail.text()
                + f"\nStaged from {source_size[0]}×{source_size[1]}; the private "
                f"snapshot is {texture.width}×{texture.height}."
            )
            return
        self.package_preview.set_loading("Decoding the exact embedded texture…")
        destination = self._stadium_texture_preview_path(texture.index)

        def operation(_progress: Callable[[str, int, int], None]) -> Path:
            assert source is not None
            return stadium_texture.export_png(
                source.game_root, texture.index, destination
            )

        def complete(result: object) -> None:
            if (
                generation != self._texture_generation
                or self._selected_embedded_texture() != texture
            ):
                Path(result).unlink(missing_ok=True)
                return
            self.package_preview.set_image(Path(result))

        def _embed_preview_watchdog() -> None:
            if generation != self._texture_generation:
                return
            if str(self.package_preview.property("previewState") or "") != "loading":
                return
            self.package_preview.set_error(
                f"{texture.selector}: embedded texture still preparing after 45s. "
                "Re-click the surface or Export."
            )

        QTimer.singleShot(45_000, _embed_preview_watchdog)
        self.run_task("Preparing exact stadium surface texture", operation, complete, False)

    def _export_scene(self) -> None:
        reason = str(
            self.export_scene_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export stadium scene yet",
                reason,
            )
            return
        scene = self._selected_scene()
        if scene is None:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export private APF stadium 3D scene",
            str(Path.home() / f"apf-stadium-outer-{scene.outer_index:04d}.zip"),
            "glTF scene ZIP (*.zip)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "The glTF, binary buffer, and manifest export together as one .zip archive.",
            )
            return
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting private APF stadium scene",
            lambda progress: self.facade.export_stadium_scene_bundle(
                scene, path, progress
            ),
            lambda result: QMessageBox.information(
                self,
                "Stadium scene exported",
                f"Saved to:\n{Path(result)}\n\n"
                "This geometry came from your own game copy and is not part of a shareable mod project.",
            ),
            True,
        )

    def _export_package_asset(self) -> None:
        reason = str(
            self.export_package_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export stadium package texture yet",
                reason
                + "\n\nFix: open a scene, click a surface that owns an editable "
                "embedded TXTR, then Export.",
            )
            return
        embedded = self._selected_embedded_texture()
        if embedded is not None:
            self._export_embedded_texture(embedded)
            return
        asset = self._selected_package_asset()
        if asset is None:
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in asset.name
        )
        if asset.type_name == "TXTR":
            default = Path.home() / f"{safe_name}.png"
            filters = "PNG preview (*.png);;Raw parts bundle (*.zip)"
        else:
            default = Path.home() / f"{safe_name}.zip"
            filters = "Raw parts bundle (*.zip)"
        destination, chosen_filter = QFileDialog.getSaveFileName(
            self,
            "Export stadium package record",
            str(default),
            filters,
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip" if chosen_filter.startswith("Raw") else ".png")
        allowed_suffixes = {".png", ".zip"} if asset.type_name == "TXTR" else {".zip"}
        if path.suffix.casefold() not in allowed_suffixes:
            expected = "a .png or .zip filename" if asset.type_name == "TXTR" else "a .zip filename"
            QMessageBox.information(
                self,
                "Choose a supported filename",
                f"Export this package record using {expected}.",
            )
            return
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting stadium package record",
            lambda progress: self.facade.export_asset(
                asset.asset_id, path, progress
            ),
            lambda result: QMessageBox.information(
                self,
                "Package record exported",
                f"Saved to:\n{Path(result)}\n\n"
                "Package proximity does not establish surface/texture ownership.",
            ),
            True,
        )

    def _export_embedded_texture(
        self, texture: stadium_texture.EmbeddedTexture
    ) -> None:
        source = self.facade.source
        if source is None or not texture.editable:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export exact APF stadium surface texture",
            str(Path.home() / f"stadium-texture-{texture.index:03d}.png"),
            "PNG image (*.png)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".png")
        self.run_task(
            "Exporting exact stadium surface texture",
            lambda _progress: stadium_texture.export_png(
                source.game_root, texture.index, path
            ),
            lambda result: QMessageBox.information(
                self,
                "Stadium texture exported",
                f"Saved the decoded source texture to:\n{Path(result)}",
            ),
            True,
        )

    def _replace_embedded_texture(self) -> None:
        reason = str(
            self.replace_package_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot replace stadium texture yet",
                reason
                + "\n\nFix: click a surface that owns an editable embedded TXTR, "
                "then Replace. Build writes a copied 1A — never mutates your original.",
            )
            return
        texture = self._selected_embedded_texture()
        source = self.facade.source
        if texture is None or source is None or not texture.editable:
            return
        replacement, _selected_filter = QFileDialog.getOpenFileName(
            self,
            f"Choose an image for this stadium texture (any size or format — "
            f"it is resized to {texture.width}×{texture.height} for you)",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
        )
        if not replacement:
            return
        self._replace_embedded_texture_path(texture, Path(replacement))

    def _replace_embedded_texture_path(
        self, texture: stadium_texture.EmbeddedTexture, supplied: Path
    ) -> None:
        """Stage a chosen or dropped image for one embedded stadium texture.

        The stadium writer reads PNG only, so any other ordinary format is
        converted to an exact-size RGBA PNG first; a PNG is handed straight
        through and resized by the existing staging step, exactly as before.
        """

        source = self.facade.source
        if source is None or not texture.editable:
            return

        def operation(_progress: Callable[[str, int, int], None]) -> object:
            candidate = Path(supplied)
            if candidate.suffix.casefold() != ".png":
                from mod_editor.core.image_fit import fit_to_png

                converted = self._stadium_texture_preview_path(
                    texture.index
                ).with_name(
                    f"stadium-{texture.index:03d}-converted-{uuid4().hex}.png"
                )
                fit_to_png(
                    candidate,
                    texture.width,
                    texture.height,
                    converted,
                    mode="auto",
                )
                candidate = converted
            return stadium_texture.stage_replacement_png(
                source.game_root,
                texture.index,
                candidate,
                self._stadium_texture_preview_path(texture.index),
            )

        def complete(result: object) -> None:
            staged_path, source_size = result  # type: ignore[misc]
            previous = self._staged_embedded_textures.get(texture.index)
            if previous is not None:
                previous[0].unlink(missing_ok=True)
            self._staged_embedded_textures[texture.index] = (
                Path(staged_path),
                tuple(source_size),
            )
            self._embedded_texture_selected(texture)
            self.modifiedChanged.emit()

        self.run_task(
            "Validating and staging stadium texture",
            operation,
            complete,
            True,
        )

    def _replace_embedded_texture_from_drop(self, supplied: Path) -> None:
        texture = self._selected_embedded_texture()
        source = self.facade.source
        if texture is None or source is None or not texture.editable:
            QMessageBox.information(
                self,
                "This stadium texture can't be replaced yet",
                "Select an editable stadium texture first, then drop your image "
                "again. Locked descriptors stay preview/export-only.",
            )
            return
        self._replace_embedded_texture_path(texture, Path(supplied))

    def _revert_embedded_texture(self) -> None:
        reason = str(
            self.revert_package_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Nothing to revert",
                reason + "\n\nStage a replacement first, then Revert clears it.",
            )
            return
        texture = self._selected_embedded_texture()
        if texture is None:
            return
        staged = self._staged_embedded_textures.pop(texture.index, None)
        if staged is None:
            return
        staged[0].unlink(missing_ok=True)
        self._embedded_texture_selected(texture)
        self.modifiedChanged.emit()

    def _build_embedded_texture_output(self) -> None:
        reason = str(
            self.build_package_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot build stadium texture output yet",
                reason
                + "\n\nFix: Replace/stage an editable embedded texture, then Build "
                "a verified copied 1A.",
            )
            return
        texture = self._selected_embedded_texture()
        source = self.facade.source
        staged = (
            self._staged_embedded_textures.get(texture.index)
            if texture is not None
            else None
        )
        if texture is None or source is None or staged is None:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Choose a new copied-1A output folder",
            str(Path.home() / f"stadium-texture-{texture.index:03d}-copied-1A"),
            "Output folder name (*)",
        )
        if not destination:
            return
        output = Path(destination)
        self.run_task(
            "Building and verifying copied stadium 1A",
            lambda _progress: stadium_texture.write_output(
                source.game_root,
                staged[0],
                texture.index,
                output,
            ),
            lambda receipt: QMessageBox.information(
                self,
                "Stadium texture output verified",
                f"Saved a copied 1A and manifest to:\n{receipt.output_directory}\n\n"
                f"Original input was {staged[1][0]}×{staged[1][1]} and the staged "
                f"snapshot is {texture.width}×{texture.height}; "
                f"{receipt.changed_vram_bytes:,} decoded VRAM bytes changed. Your "
                "source game was not modified. Runtime visibility still requires "
                "your own target-system test.",
            ),
            True,
        )


#: One scorebug graphic as the page presents it.  ``texture`` is set for a
#: descriptor embedded in a SCNE part, which has no catalog identity and no
#: writer; it is ``None`` for the one indexed TXTR a writer owns.
@dataclass(frozen=True)
class _ScorebugGraphic:
    key: str
    title: str
    where: str
    size: str
    format_name: str
    editing: str
    detail: str
    texture: SceneTexture | None = None
    editable: bool = False


#: Presentation systems that share this category but not the field HUD.  Each
#: entry is (button label, name tokens, one-line boundary).
SCOREBUG_SYSTEM_FILTERS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "Field scorebug",
        ("scorebug", "digital_font"),
        "The seven-part in-game HUD above. This is the system this page is named after.",
    ),
    (
        "Season GameCast",
        ("gamecast",),
        "A separate season/franchise presentation system. Editing it does not change the field HUD.",
    ),
    (
        "Instant replay",
        ("replay", "telestrator"),
        "The replay overlay is a separate system. Editing it does not change the field HUD.",
    ),
    (
        "Halftime",
        ("halftime",),
        "Halftime show, ticker, and team comparison are a separate system. Editing them does not change the field HUD.",
    ),
)

#: Repeated verbatim beside every read-only control on this page.  The
#: embedded-texture writer that does exist is pinned to the authenticated
#: stadium package and authorizes nothing here.
SCENE_TEXTURE_NO_WRITER_REASON = (
    "Not proved: no writer exists for a texture embedded inside a SCNE part. "
    "The stadium embedded-texture writer is pinned to that one authenticated "
    "package and does not authorize this descriptor. Preview and export are "
    "read-only, and the scene geometry that draws it has no writer either."
)


class ScorebugGraphicsPanel(QFrame):
    """The artwork the field scorebug is actually built from.

    The page used to name this inventory and show none of it: eleven TXTR
    descriptors live inside the ``scorebug_*`` SCNE parts, and a texture with
    no inner-file index can never become a catalog row.  This panel reads them
    straight out of the user's own game and previews them, while stating on the
    row itself that only the shared digit atlas has a proved writer.
    """

    editDigitalFontRequested = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        self._graphics: tuple[_ScorebugGraphic, ...] = ()
        self._selected_key = ""
        self._preview_token = 0
        self._read_token = 0

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = WordElidedLabel("Field scorebug graphics")
        title.setObjectName("panelTitle")
        self.count = WordElidedLabel("Load a game to see the scorebug")
        self.count.setObjectName("countPill")
        header.addWidget(title)
        header.addWidget(self.count)
        header.addStretch(1)
        box.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.preview = ImageDropLabel(
            "Load your APF game, then pick a graphic to see it here."
        )
        # Read-only artwork: nothing on this preview accepts a replacement.
        self.preview.setAcceptDrops(False)
        self.preview.setMinimumSize(210, 190)
        splitter.addWidget(self.preview)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("scorebugGraphicsTable")
        self.table.setHorizontalHeaderLabels(
            ("Graphic", "Size", "Format", "Editing")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumWidth(320)
        self.table.setMinimumHeight(250)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, header_view.Stretch)
        header_view.setSectionResizeMode(1, header_view.ResizeToContents)
        header_view.setSectionResizeMode(2, header_view.ResizeToContents)
        header_view.setSectionResizeMode(3, header_view.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 620])
        box.addWidget(splitter, 1)

        self.detail = QLabel(
            "Every graphic here is read-only except the shared score-digit mask."
        )
        self.detail.setObjectName("findingText")
        self.detail.setWordWrap(True)
        # A plain wrapped label makes its longest word the panel's minimum
        # width; this page has to survive a 1040-wide shell.
        self.detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.detail.setMinimumWidth(0)
        box.addWidget(self.detail)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_png_button = QPushButton("Export PNG…")
        self.export_png_button.setObjectName("secondaryButton")
        self.export_raw_button = QPushButton("Export raw descriptor…")
        self.export_raw_button.setObjectName("utilityButton")
        self.edit_button = QPushButton("Edit the score digits…")
        self.edit_button.setObjectName("primaryButton")
        # Three verbose labels side by side are the widest row on the page, and
        # a button reports its whole label as a hard minimum. Qt already elides
        # button text that will not fit, so let the row shrink rather than have
        # it set the floor for the entire shell.
        for button in (
            self.export_png_button,
            self.export_raw_button,
            self.edit_button,
        ):
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Ignored, button.sizePolicy().verticalPolicy()
            )
        self.export_png_button.clicked.connect(self._export_png)
        self.export_raw_button.clicked.connect(self._export_raw)
        self.edit_button.clicked.connect(self._edit_selected)
        actions.addWidget(self.export_png_button)
        actions.addWidget(self.export_raw_button)
        actions.addWidget(self.edit_button)
        actions.addStretch(1)
        box.addLayout(actions)
        self._set_actions("Load your APF game to preview and export the scorebug art.")

    def _set_actions(self, reason: str) -> None:
        """Never silent-gray: a blocked button still says why when clicked."""

        for button in (
            self.export_png_button,
            self.export_raw_button,
            self.edit_button,
        ):
            button.setEnabled(True)
            button.setProperty("disableReason", reason)
            if reason:
                button.setToolTip(reason)

    def _selected(self) -> _ScorebugGraphic | None:
        for graphic in self._graphics:
            if graphic.key == self._selected_key:
                return graphic
        return None

    def set_context(self) -> None:
        if not self.facade.source_ready:
            self._graphics = ()
            self._selected_key = ""
            self.table.clearContents()
            self.table.setRowCount(0)
            self.count.setText("Load a game to see the scorebug")
            self.preview.set_message(
                "Load your APF game, then pick a graphic to see it here."
            )
            self.detail.setText(
                "The field scorebug's artwork is stored inside its scene "
                "packages. Load your own game and it is read straight out of "
                "there — your original files are never modified."
            )
            self._set_actions(
                "Load your APF game first (File → Load game), then the scorebug "
                "art can be previewed and exported."
            )
            return
        assets = self.facade.browse_assets(
            category=ApfCategory.SCOREBUG,
            limit=len(self.facade.require_catalog().assets) + 1,
        )
        scenes = [
            asset
            for asset in assets
            if asset.type_name == "SCNE" and asset.name.startswith("scorebug")
        ]
        self.count.setText("Reading the scorebug scenes…")
        self._read_token += 1
        token = self._read_token

        def _watchdog() -> None:
            # A read that fails raises into the shell's error path, which never
            # reaches this panel.  Without this the count pill would keep
            # claiming a read is in flight long after it stopped.
            if token != self._read_token or self._graphics:
                return
            self.count.setText("Could not read the scorebug scenes")
            self.detail.setText(
                "This copy's scorebug scene packages could not be read. The "
                "presentation inventory below still lists every indexed record."
            )
            self._set_actions(
                "The embedded scorebug graphics could not be read from this "
                "copy, so there is nothing here to preview or export. Reload "
                "your game, or use the inventory below."
            )

        QTimer.singleShot(45_000, _watchdog)
        self.run_task(
            "Reading embedded scorebug graphics",
            lambda progress: self.facade.scene_textures(
                [asset.asset_id for asset in scenes], progress
            ),
            lambda textures: self._populate(tuple(textures), assets),
            False,
        )

    def _populate(
        self, textures: tuple[SceneTexture, ...], assets: Sequence[ApfAsset]
    ) -> None:
        shared = shared_texture_ids(textures)
        rows: list[_ScorebugGraphic] = []
        for texture in textures:
            note = SCENE_TEXTURE_NO_WRITER_REASON
            editing = "Read-only · no writer"
            if texture.texture_id in shared:
                editing = "Read-only · shared id"
                note = (
                    f"Texture id 0x{texture.texture_id:08x} is declared by more "
                    "than one scorebug component, so these are one image reused, "
                    "not independent slots. " + SCENE_TEXTURE_NO_WRITER_REASON
                )
            rows.append(
                _ScorebugGraphic(
                    key=texture.key,
                    title=texture.title,
                    where=f"{texture.location} · id 0x{texture.texture_id:08x} · {texture.vram_span}",
                    size=texture.dimensions,
                    format_name=texture.format_name,
                    editing=editing,
                    detail=note,
                    texture=texture,
                )
            )
        for asset in assets:
            if asset.type_name != "TXTR" or asset.name != DIGITAL_FONT_NAME:
                continue
            rows.append(
                _ScorebugGraphic(
                    key=asset.asset_id,
                    title="digital_font · score digits",
                    where=f"{asset.location} · shared global atlas",
                    size="128×128",
                    format_name="DXT5A",
                    editing="Editable · shared atlas",
                    detail=(
                        "The one graphic on this page with a proved writer. It "
                        "is a global atlas, so edits may affect UI outside the "
                        "field scorebug, and runtime visibility is not proved — "
                        "the write itself is proved only offline, into a new "
                        "copied volume."
                    ),
                    editable=True,
                )
            )
        self._graphics = tuple(rows)
        editable = sum(1 for row in rows if row.editable)
        self.count.setText(
            f"{len(rows)} graphics · {editable} with a proved writer"
        )
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        for index, graphic in enumerate(rows):
            values = (graphic.title, graphic.size, graphic.format_name, graphic.editing)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, graphic.key)
                cell.setToolTip(f"{graphic.where}\n\n{graphic.detail}")
                if column == 3:
                    cell.setForeground(
                        QColor("#39d98a" if graphic.editable else "#f2bd5a")
                    )
                self.table.setItem(index, column, cell)
        self.table.blockSignals(False)
        if rows:
            wanted = next(
                (i for i, row in enumerate(rows) if row.key == self._selected_key), 0
            )
            self.table.selectRow(wanted)
        else:
            self._selected_key = ""
            self.detail.setText(
                "No embedded scorebug graphics were found in this copy. The "
                "presentation inventory below still lists every indexed record."
            )
            self._set_actions("This copy exposed no embedded scorebug graphics to export.")

    def _selection_changed(self) -> None:
        items = self.table.selectedItems()
        self._selected_key = str(items[0].data(Qt.UserRole)) if items else ""
        graphic = self._selected()
        if graphic is None:
            self.detail.setText("Choose a graphic to see where it lives.")
            return
        self.detail.setText(f"{graphic.where}\n{graphic.detail}")
        if graphic.editable:
            self._set_actions("")
            self.export_png_button.setToolTip(
                "Export the current score-digit mask as a PNG."
            )
            raw_note = (
                "digital_font is an indexed TXTR, not an embedded scene "
                "descriptor. Use Export PNG, or the inventory below for its raw parts."
            )
            self.export_raw_button.setProperty("disableReason", raw_note)
            self.export_raw_button.setToolTip(raw_note)
            self.edit_button.setToolTip(
                "Open the Digital Font editor below with this slot selected."
            )
        else:
            self._set_actions("")
            self.export_png_button.setToolTip(
                "Save this embedded graphic as a decoded PNG."
            )
            self.export_raw_button.setToolTip(
                "Save the exact descriptor metadata and payload bytes as a ZIP."
            )
            self.edit_button.setProperty("disableReason", graphic.detail)
            self.edit_button.setToolTip(graphic.detail)
        self._load_preview(graphic)

    def _load_preview(self, graphic: _ScorebugGraphic) -> None:
        self._preview_token += 1
        token = self._preview_token
        self.preview.set_loading(f"Decoding {graphic.title}…")

        def _apply(result: object) -> None:
            if token != self._preview_token:
                return
            self.preview.set_image(Path(str(result)))

        if graphic.texture is not None:
            texture = graphic.texture
            self.run_task(
                "Decoding embedded scorebug graphic",
                lambda progress: self.facade.preview_scene_texture(texture, progress),
                _apply,
                False,
            )
            return
        self.run_task(
            "Preparing digital_font preview",
            lambda progress: self.facade.preview_digital_font(progress),
            _apply,
            False,
        )

    def _blocked(self, button: QPushButton, title: str) -> bool:
        reason = str(button.property("disableReason") or "").strip()
        if not reason:
            return False
        QMessageBox.information(self, title, reason)
        return True

    def _new_destination(self, suggestion: str, caption: str, filter_text: str) -> Path | None:
        destination, _filter = QFileDialog.getSaveFileName(
            self, caption, str(Path.home() / suggestion), filter_text
        )
        if not destination:
            return None
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(Path(suggestion).suffix)
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return None
        return path

    def _export_png(self) -> None:
        if self._blocked(self.export_png_button, "Cannot export this graphic yet"):
            return
        graphic = self._selected()
        if graphic is None:
            return
        safe = graphic.key.replace(":", "-")
        path = self._new_destination(
            f"apf-{safe}.png", "Export this scorebug graphic as PNG", "RGBA PNG (*.png)"
        )
        if path is None:
            return
        if graphic.texture is not None:
            texture = graphic.texture
            operation = lambda progress: self.facade.export_scene_texture(  # noqa: E731
                texture, path, progress
            )
        else:
            operation = lambda progress: self.facade.export_digital_font(  # noqa: E731
                path, progress
            )
        self.run_task(
            "Exporting scorebug graphic",
            operation,
            lambda result: QMessageBox.information(
                self, "PNG exported", f"Saved to:\n{Path(result)}"
            ),
            True,
        )

    def _export_raw(self) -> None:
        if self._blocked(self.export_raw_button, "Cannot export raw bytes here"):
            return
        graphic = self._selected()
        if graphic is None or graphic.texture is None:
            return
        texture = graphic.texture
        safe = graphic.key.replace(":", "-")
        path = self._new_destination(
            f"apf-{safe}.zip",
            "Export the exact descriptor and payload",
            "ZIP bundle (*.zip)",
        )
        if path is None:
            return
        self.run_task(
            "Exporting embedded descriptor",
            lambda progress: self.facade.export_scene_texture(texture, path, progress),
            lambda result: QMessageBox.information(
                self,
                "Raw bytes exported",
                f"Saved to:\n{Path(result)}\n\nThe bundle records that no writer "
                "is proved for this descriptor.",
            ),
            True,
        )

    def _edit_selected(self) -> None:
        if self._blocked(self.edit_button, "This graphic has no proved writer"):
            return
        self.editDigitalFontRequested.emit()

    def focus_digital_font(self) -> bool:
        for index, graphic in enumerate(self._graphics):
            if graphic.editable:
                self.table.selectRow(index)
                return True
        return False


class ScorebugComponentsPanel(QFrame):
    """The seven SCNE parts the field HUD is assembled from, read-only."""

    openWorkspaceRequested = pyqtSignal(object)

    def __init__(self, facade: ApfStudioFacade):
        super().__init__()
        self.facade = facade
        self.setObjectName("panel")
        self._route: WorkspaceRoute | None = None
        self._route_name = ""

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = WordElidedLabel("How the field scorebug is assembled")
        title.setObjectName("panelTitle")
        self.summary = WordElidedLabel("Load a game to map the components.")
        self.summary.setObjectName("countPill")
        header.addWidget(title)
        header.addWidget(self.summary)
        header.addStretch(1)
        self.route_button = QPushButton("Open Team Logo…")
        self.route_button.setObjectName("secondaryButton")
        self.route_button.clicked.connect(self._open_route)
        header.addWidget(self.route_button)
        box.addLayout(header)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("scorebugComponentTable")
        self.table.setHorizontalHeaderLabels(
            ("Component", "Meshes", "Triangles", "Own artwork", "What you can change")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setFixedHeight(230)
        view = self.table.horizontalHeader()
        view.setSectionResizeMode(0, view.Stretch)
        view.setSectionResizeMode(1, view.ResizeToContents)
        view.setSectionResizeMode(2, view.ResizeToContents)
        view.setSectionResizeMode(3, view.ResizeToContents)
        view.setSectionResizeMode(4, view.Stretch)
        box.addWidget(self.table)

        self.note = QLabel(
            "Geometry, layout, and component timing are read-only: no SCNE "
            "writer exists for either title. Scores, the clock, down and "
            "distance, and team identity are executable behaviour — no asset "
            "edit changes them."
        )
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.note.setMinimumWidth(0)
        box.addWidget(self.note)
        self._set_route(None, "")

    def _set_route(self, route: WorkspaceRoute | None, name: str) -> None:
        self._route = route
        self._route_name = name
        # Never silent-gray: the button stays clickable and explains itself.
        self.route_button.setEnabled(True)
        if route is None:
            reason = (
                "Load your APF game first. The team-logo component then routes "
                "to the crest writer that feeds its runtime samplers."
            )
            self.route_button.setProperty("disableReason", reason)
            self.route_button.setToolTip(reason)
            return
        self.route_button.setProperty("disableReason", "")
        # One place owns the wording of a hand-off: the route table itself.
        self.route_button.setText(route.action_label)
        self.route_button.setToolTip(f"{name} — {route.summary}")

    def _open_route(self) -> None:
        reason = str(self.route_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Open Team Logo", reason)
            return
        if self._route is None:
            return
        self.openWorkspaceRequested.emit(
            WorkspaceHandoff(
                route=self._route,
                asset_name=self._route_name,
                asset_id=self._route_name,
            )
        )

    def set_context(self) -> None:
        snapshot = presentation_snapshot()
        components = [
            row for row in snapshot.model.rows if row.kind == "scorebug_scene_component"
        ]
        self.table.clearContents()
        self.table.setRowCount(len(components))
        for index, row in enumerate(components):
            fields = dict(row.fields)
            embedded = int(fields.get("embedded_texture_count", 0) or 0)
            samplers = int(fields.get("dynamic_logo_sampler_count", 0) or 0)
            if samplers:
                art = f"{samplers} runtime sampler(s)"
                boundary = (
                    "Draws a team logo the game supplies at runtime. Team Logo "
                    "writes both candidate reservoirs; which one this reads is "
                    "not proved."
                )
            elif embedded:
                art = f"{embedded} embedded texture(s)"
                boundary = "Artwork previews and exports above; no writer is proved for it."
            else:
                art = "none"
                boundary = "Geometry only — nothing here is editable."
            values = (
                row.title,
                f"{int(fields.get('mesh_count', 0) or 0):,}",
                f"{int(fields.get('triangle_count', 0) or 0):,}",
                art,
                boundary,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(f"{row.title} — {boundary}")
                self.table.setItem(index, column, cell)
        self.summary.setText(
            f"{len(components)} components · "
            f"{int(snapshot.summary.get('bounded_texture_writers', 0))} proved writer"
        )
        if not self.facade.source_ready:
            self._set_route(None, "")
            return
        for asset in self.facade.browse_assets(
            category=ApfCategory.SCOREBUG,
            limit=len(self.facade.require_catalog().assets) + 1,
        ):
            route = route_for_asset(asset)
            if route is not None and route.category is ApfCategory.LOGOS:
                self._set_route(route, asset.name)
                return
        self._set_route(None, "")


class ScorebugStudioPage(QWidget):
    """Field scorebug art first, then its components, then the full inventory."""

    modifiedChanged = pyqtSignal()
    openWorkspaceRequested = pyqtSignal(object)

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(ApfCategory.SCOREBUG))
        self.capabilities = CapabilityPanel(ApfCategory.SCOREBUG)
        layout.addWidget(self.capabilities)

        self.graphics = ScorebugGraphicsPanel(facade, run_task)
        self.graphics.editDigitalFontRequested.connect(self._show_digital_font)
        layout.addWidget(self.graphics)

        self.components = ScorebugComponentsPanel(facade)
        self.components.openWorkspaceRequested.connect(self.openWorkspaceRequested)
        layout.addWidget(self.components)

        systems = QFrame()
        systems.setObjectName("panel")
        systems_box = QVBoxLayout(systems)
        systems_box.setContentsMargins(14, 10, 14, 10)
        systems_box.setSpacing(6)
        systems_title = WordElidedLabel("This category also holds four separate systems")
        systems_title.setObjectName("panelTitle")
        systems_box.addWidget(systems_title)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for label, tokens, boundary in SCOREBUG_SYSTEM_FILTERS:
            button = QPushButton(label)
            button.setObjectName("utilityButton")
            button.setToolTip(boundary)
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Ignored, button.sizePolicy().verticalPolicy()
            )
            button.clicked.connect(
                lambda _checked=False, value=tokens, text=boundary: self._filter_system(
                    value, text
                )
            )
            buttons.addWidget(button)
        show_all = QPushButton("Show everything")
        show_all.setObjectName("utilityButton")
        show_all.setToolTip("Clear the filter and list every indexed presentation record.")
        show_all.setMinimumWidth(0)
        show_all.setSizePolicy(
            QSizePolicy.Ignored, show_all.sizePolicy().verticalPolicy()
        )
        show_all.clicked.connect(lambda: self._filter_system((), ""))
        buttons.addWidget(show_all)
        buttons.addStretch(1)
        systems_box.addLayout(buttons)
        self.system_note = QLabel(
            "Overlay audio for replays, challenges, and halftime lives in "
            "sfx_overlay.iff and is owned by the Audio workspace."
        )
        self.system_note.setObjectName("mutedLabel")
        self.system_note.setWordWrap(True)
        self.system_note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.system_note.setMinimumWidth(0)
        systems_box.addWidget(self.system_note)
        layout.addWidget(systems)

        tabs = QTabWidget()
        tabs.setObjectName("workspaceTabs")
        self.presentation = InspectorBrowser(
            "Mapped field-scorebug semantics", facade, run_task
        )
        self.digital_font = DigitalFontPanel(facade, run_task)
        self.browser = AssetBrowser(
            facade,
            ApfCategory.SCOREBUG,
            run_task,
            browse_export_only=True,
            action_lock_reason=(
                "This presentation inventory is browse and export-only. The one "
                "proved writer on this page is the shared digital_font score-digit "
                "mask, edited in the Digital Font tab. The SCNE geometry, the "
                "textures embedded inside it, and the GameCast, replay, and "
                "halftime records have no proved writer."
            ),
        )
        self.digital_font.modifiedChanged.connect(self.modifiedChanged)
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        tabs.addTab(self.presentation, "Presentation Map")
        self._digital_font_tab = tabs.addTab(self.digital_font, DIGITAL_FONT_TAB)
        self._browser_tab = tabs.addTab(self.browser, "Raw Presentation Assets")
        tabs.setTabToolTip(
            self._digital_font_tab,
            "The one proved writer on this page: the shared 128×128 score-digit mask.",
        )
        layout.addWidget(tabs, 1)
        self.tabs = tabs

    def _show_digital_font(self) -> None:
        self.tabs.setCurrentIndex(self._digital_font_tab)

    def _filter_system(self, tokens: tuple[str, ...], boundary: str) -> None:
        if not self.facade.source_ready:
            QMessageBox.information(
                self,
                "Load your game first",
                "Load your APF game (File → Load game), then these buttons filter "
                "the presentation inventory to one system at a time.",
            )
            return
        assets = self.facade.browse_assets(
            category=ApfCategory.SCOREBUG,
            limit=len(self.facade.require_catalog().assets) + 1,
        )
        if tokens:
            matched = [
                asset.asset_id
                for asset in assets
                if any(token in asset.name.casefold() for token in tokens)
            ]
            self.browser.set_included_asset_ids(matched)
            self.system_note.setText(f"{len(matched)} records. {boundary}")
        else:
            self.browser.set_included_asset_ids(None)
            self.system_note.setText(
                f"All {len(assets)} indexed presentation records. Overlay audio "
                "for replays, challenges, and halftime lives in sfx_overlay.iff "
                "and is owned by the Audio workspace."
            )
        self.tabs.setCurrentIndex(self._browser_tab)
        self.browser.set_context()

    def focus_workspace_route(self, route: WorkspaceRoute, image: Path | None) -> bool:
        """Open the shared score-digit mask handed over from a browser row."""

        if route.tab != DIGITAL_FONT_TAB or route.key != DIGITAL_FONT_NAME:
            return False
        self.graphics.focus_digital_font()
        self._show_digital_font()
        if image is not None:
            self.digital_font.stage_image(image)
        return True

    def set_context(self) -> None:
        if self.facade.source_ready:
            count = len(
                self.facade.browse_assets(
                    category=ApfCategory.SCOREBUG,
                    limit=len(self.facade.require_catalog().assets) + 1,
                )
            )
            self.capabilities.set_cards(
                self.facade.capability_cards(ApfCategory.SCOREBUG),
                catalog_ready=True,
                inventory_count=count,
            )
        else:
            self.capabilities.set_cards(())
        if self.facade.source_ready:
            snapshot = presentation_snapshot()
            self.presentation.set_model(
                snapshot.model, _format_summary(dict(snapshot.summary))
            )
        else:
            self.presentation.set_unavailable(
                "Load your APF game to open the mapped presentation inspector."
            )
        self.graphics.set_context()
        self.components.set_context()
        self.digital_font.set_context()
        self.browser.set_context()

    def refresh(self) -> None:
        self.presentation.refresh()
        self.graphics.set_context()
        self.components.set_context()
        self.digital_font.set_context()
        self.browser.refresh()


class BaseRatingsPanel(QFrame):
    """Searchable exact-value editor for one player's 31 native rating bytes."""

    applyRequested = pyqtSignal(int, str, int)
    revertRequested = pyqtSignal(int, str)

    def __init__(self, facade: ApfStudioFacade) -> None:
        super().__init__()
        self.facade = facade
        self.setObjectName("baseRatingsPanel")
        self._rows: tuple[dict[str, object], ...] = ()
        self._player_index: int | None = None
        self._selected_field_id: str | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 9, 10, 9)
        box.setSpacing(6)

        heading = QHBoxLayout()
        title = QLabel("Base Ratings")
        title.setObjectName("fieldLabel")
        self.status = QLabel("EDITABLE · EXACT 0–99")
        self.status.setObjectName("countPill")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)

        self.search = QLineEdit()
        self.search.setObjectName("baseRatingsSearch")
        self.search.setAccessibleName("Search this player's base ratings")
        self.search.setPlaceholderText("Search 31 ratings…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("baseRatingsTable")
        self.table.setHorizontalHeaderLabels(
            ("Attribute", "Value", "Byte", "State")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(176)
        self.table.setMaximumHeight(252)
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, self.table.horizontalHeader().ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, self.table.horizontalHeader().ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, self.table.horizontalHeader().ResizeToContents
        )
        self.table.itemSelectionChanged.connect(self._rating_selection_changed)

        self.selected_rating = QLabel("Choose a rating to edit its exact byte value.")
        self.selected_rating.setObjectName("metadataText")
        self.selected_rating.setWordWrap(True)

        editor = QHBoxLayout()
        editor.setSpacing(7)
        self.value_editor = QSpinBox()
        self.value_editor.setObjectName("baseRatingValueEditor")
        self.value_editor.setAccessibleName("New exact APF base rating value")
        self.value_editor.setRange(0, 99)
        self.value_editor.setAlignment(Qt.AlignRight)
        self.value_editor.setEnabled(False)
        self.value_editor.valueChanged.connect(self._editor_changed)
        self.apply_button = QPushButton("Apply Rating")
        self.apply_button.setObjectName("primaryButton")
        _rating_boot = (
            "Select a player and base rating first. Apply/Revert stay clickable."
        )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(_rating_boot)
        self.apply_button.setProperty("disableReason", _rating_boot)
        self.apply_button.clicked.connect(self._apply_rating)
        self.revert_button = QPushButton("Revert Rating")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(_rating_boot)
        self.revert_button.setProperty("disableReason", _rating_boot)
        self.revert_button.clicked.connect(self._revert_rating)
        editor.addWidget(self.value_editor)
        editor.addWidget(self.apply_button, 1)
        editor.addWidget(self.revert_button, 1)

        self.note = QLabel(
            "Each value is the game's independent native byte—not a converted "
            "star scale. Apply writes an exact whole number from 0–99. A source "
            "mod's native 100 is shown exactly and can be reverted to, but a new "
            "edit must be 0–99; Mod Studio never silently clamps it. Overall, "
            "abilities, and Gold/Silver/Bronze tier are separate and do not "
            "change automatically. The token-preserving candidate booted and "
            "loaded Dan Marino in Xenia; APF's star-selection screen offered no "
            "on-screen numeric rating readout."
        )
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)

        box.addLayout(heading)
        box.addWidget(self.search)
        box.addWidget(self.selected_rating)
        box.addLayout(editor)
        box.addWidget(self.table)
        box.addWidget(self.note)
        self.setVisible(False)

    def set_player(self, row: InspectorRow) -> None:
        values = row.fields.get("base_ratings")
        if row.kind != "player" or not isinstance(values, (list, tuple)):
            self.clear_player()
            return
        parsed: list[dict[str, object]] = []
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                raise ValueError(f"Base rating row {index} is not a mapping")
            label = value.get("label")
            field_id = value.get("id")
            rating = value.get("value")
            offset = value.get("relative_offset_hex")
            if (
                not isinstance(label, str)
                or not label
                or not isinstance(field_id, str)
                or not field_id
                or isinstance(rating, bool)
                or not isinstance(rating, int)
                or not 0 <= rating <= 100
                or not isinstance(offset, str)
                or not offset.startswith("0x")
            ):
                raise ValueError(f"Base rating row {index} is malformed")
            parsed.append(dict(value))
        # Imported here rather than at module scope: this panel is a pure view, and
        # the count has to follow the schema instead of a frozen literal that goes
        # stale the next time a rating byte gets named.
        from .player_ratings import load_player_rating_schema

        expected_ratings = len(load_player_rating_schema().fields)
        if len(parsed) != expected_ratings:
            raise ValueError(
                f"Player exposes {len(parsed)} base ratings; "
                f"expected {expected_ratings}"
            )
        player_index = row.fields.get("player_index")
        if (
            isinstance(player_index, bool)
            or not isinstance(player_index, int)
            or not 0 <= player_index <= 2_253
        ):
            raise ValueError("Player row has no valid 0..2253 player index")
        self._rows = tuple(parsed)
        self._player_index = player_index
        self._selected_field_id = None
        self.setVisible(True)
        self._refresh()

    def clear_player(self) -> None:
        self._rows = ()
        self._player_index = None
        self._selected_field_id = None
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self.status.setText("EDITABLE · EXACT 0–99")
        self.selected_rating.setText("Choose a rating to edit its exact byte value.")
        self.value_editor.setEnabled(False)
        tip = (
            "Select a player and a base rating first. Apply/Revert stay "
            "clickable so blocked states explain themselves."
        )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(tip)
        self.apply_button.setProperty("disableReason", tip)
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(tip)
        self.revert_button.setProperty("disableReason", tip)
        self.setVisible(False)

    @staticmethod
    def _asset_id(player_index: int, field_id: str) -> str:
        return f"apf:player-rating:{player_index}:{field_id}"

    def _current_value(self, field_id: str) -> int:
        if self._player_index is None:
            raise RuntimeError("No APF player is selected")
        value = self.facade.player_base_rating_value(
            self._player_index, field_id
        )
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(
                f"APF player {self._player_index} rating {field_id} returned "
                "an invalid value"
            )
        return value

    def select_field(self, field_id: str) -> None:
        """Restore a semantic selection after the surrounding model refreshes."""

        self._selected_field_id = field_id
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and item.data(Qt.UserRole) == field_id:
                self.table.selectRow(row_index)
                self._rating_selection_changed()
                return

    def refresh_values(self, preserve_field_id: str | None = None) -> None:
        if preserve_field_id is not None:
            self._selected_field_id = preserve_field_id
        self._refresh()

    def _refresh(self, _text: str = "") -> None:
        wanted_field_id = self._selected_field_id
        needle = self.search.text().strip().casefold()
        visible = tuple(
            row
            for row in self._rows
            if not needle
            or needle
            in " ".join(
                str(row.get(key, ""))
                for key in ("label", "id", "value", "relative_offset_hex")
            ).casefold()
        )
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(visible))
        modified_count = 0
        for row_index, rating in enumerate(visible):
            label = str(rating["label"])
            field_id = str(rating["id"])
            value = self._current_value(field_id)
            offset = str(rating["relative_offset_hex"])
            asset_id = self._asset_id(self._player_index or 0, field_id)
            modified = asset_id in self.facade.modified_asset_ids
            modified_count += int(modified)
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.UserRole, field_id)
            label_item.setToolTip(
                f"{field_id} · player record {offset} · "
                f"{rating.get('label_status', 'evidence status unavailable')}"
            )
            value_item = QTableWidgetItem(str(value))
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_item.setToolTip(
                "Native engine maximum" if value == 100 else "Exact stored base value"
            )
            offset_item = QTableWidgetItem(offset)
            offset_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            state_item = QTableWidgetItem("● Modified" if modified else "Original")
            if modified:
                state_item.setForeground(QBrush(QColor("#f2bd5a")))
            self.table.setItem(row_index, 0, label_item)
            self.table.setItem(row_index, 1, value_item)
            self.table.setItem(row_index, 2, offset_item)
            self.table.setItem(row_index, 3, state_item)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.status.setText(
            f"EDITABLE · {len(visible)} / {self.table.rowCount()}"
            + (f" · {modified_count} MODIFIED" if modified_count else "")
        )
        if visible:
            target = next(
                (
                    index
                    for index, rating in enumerate(visible)
                    if rating["id"] == wanted_field_id
                ),
                0,
            )
            self.table.selectRow(target)
            # Repopulating a QTableWidget can retain the same selected index;
            # bind controls explicitly so modified/revert state cannot lag.
            self._rating_selection_changed()
        else:
            self._selected_field_id = None
            self.selected_rating.setText("No ratings match this search.")
            self.value_editor.setEnabled(False)
            tip = "No ratings match this search. Clear the filter, then select a rating."
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(tip)
            self.revert_button.setProperty("disableReason", tip)

    def _selected_rating(self) -> dict[str, object] | None:
        selected = (
            self.table.selectionModel().selectedRows()
            if self.table.selectionModel()
            else []
        )
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        field_id = item.data(Qt.UserRole) if item is not None else None
        if not isinstance(field_id, str):
            return None
        return next(
            (rating for rating in self._rows if rating.get("id") == field_id),
            None,
        )

    def _rating_selection_changed(self) -> None:
        rating = self._selected_rating()
        if rating is None or self._player_index is None:
            self._selected_field_id = None
            self.value_editor.setEnabled(False)
            tip = "Select a base rating row first."
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(tip)
            self.revert_button.setProperty("disableReason", tip)
            return
        field_id = str(rating["id"])
        label = str(rating["label"])
        offset = str(rating["relative_offset_hex"])
        value = self._current_value(field_id)
        self._selected_field_id = field_id
        self.value_editor.blockSignals(True)
        # Native 100 may exist in an externally authored source. Keep it exact
        # in the control until the user deliberately chooses a public 0..99
        # replacement; changing the range first would silently clamp it to 99.
        self.value_editor.setRange(0, 100 if value == 100 else 99)
        self.value_editor.setValue(value)
        self.value_editor.blockSignals(False)
        self.value_editor.setEnabled(True)
        staged = (
            self._asset_id(self._player_index, field_id)
            in self.facade.modified_asset_ids
        )
        state = (
            "modified in this project"
            if staged
            else "original source value"
        )
        self.selected_rating.setText(
            f"{label} · {field_id} · player byte {offset} · exact current "
            f"value {value} · {state}"
        )
        if staged:
            revert_tip = "Restore this one rating to the exact value in the loaded source."
            revert_block = ""
        else:
            revert_tip = revert_block = "This rating still matches the loaded source."
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty("disableReason", revert_block)
        self._editor_changed()

    def _editor_changed(self, _value: int = 0) -> None:
        rating = self._selected_rating()
        if rating is None:
            tip = "Select a base rating row first."
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            return
        field_id = str(rating["id"])
        current = self._current_value(field_id)
        value = self.value_editor.value()
        valid = 0 <= value <= 99
        if valid and value != current:
            tip = f"Write exact native value {value} as one reversible project edit."
            block = ""
        elif not valid:
            tip = block = (
                "Choose a deliberate value from 0 to 99; native 100 is shown "
                "exactly but is source/revert-only."
            )
        else:
            tip = block = "This exact value is already active."
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(tip)
        self.apply_button.setProperty("disableReason", block)

    def _apply_rating(self) -> None:
        reason = str(self.apply_button.property("disableReason") or "").strip()
        if reason:
            # Status-line teach; tooltip already shows the wall.
            self.selected_rating.setText(reason)
            return
        rating = self._selected_rating()
        if rating is None or self._player_index is None:
            return
        self.applyRequested.emit(
            self._player_index,
            str(rating["id"]),
            self.value_editor.value(),
        )

    def _revert_rating(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            self.selected_rating.setText(reason)
            return
        rating = self._selected_rating()
        if rating is None or self._player_index is None:
            return
        self.revertRequested.emit(self._player_index, str(rating["id"]))


class PlayerPositionPanel(QFrame):
    """Fixed-choice editor for one player's exact native position code."""

    applyRequested = pyqtSignal(int, int)
    revertRequested = pyqtSignal(int)

    def __init__(self, facade: ApfStudioFacade) -> None:
        super().__init__()
        self.facade = facade
        self.setObjectName("playerPositionPanel")
        self._player_index: int | None = None
        self._choices: tuple[dict[str, object], ...] = ()

        box = QVBoxLayout(self)
        box.setContentsMargins(10, 9, 10, 9)
        box.setSpacing(8)

        heading = QHBoxLayout()
        title = QLabel("Player Position")
        title.setObjectName("fieldLabel")
        self.status = QLabel("EDITABLE · 17 POSITIONS")
        self.status.setObjectName("countPill")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)

        self.position = QComboBox()
        self.position.setObjectName("playerPositionEditor")
        self.position.setAccessibleName("New APF player position")
        self.position.setEnabled(False)
        self.position.currentIndexChanged.connect(self._editor_changed)

        self.current_state = QLabel(
            "Choose a player to edit the position stored in that player's record."
        )
        self.current_state.setObjectName("metadataText")
        self.current_state.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.apply_button = QPushButton("Apply Position")
        self.apply_button.setObjectName("primaryButton")
        _pos_boot = (
            "Select a player first. Apply/Revert stay clickable."
        )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(_pos_boot)
        self.apply_button.setProperty("disableReason", _pos_boot)
        self.apply_button.clicked.connect(self._apply_position)
        self.revert_button = QPushButton("Revert Position")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(_pos_boot)
        self.revert_button.setProperty("disableReason", _pos_boot)
        self.revert_button.clicked.connect(self._revert_position)
        actions.addWidget(self.apply_button, 1)
        actions.addWidget(self.revert_button, 1)

        self.note = QLabel(
            "This changes only the player's exact position code. It does not "
            "move the player to another team or depth-chart slot, recalculate "
            "ratings or Overall, or change tier and abilities. Mod Studio writes "
            "the game's semantic +0x34 byte and required +0x35 mirror together. "
            "The bounded writer is offline-proved; the first changed-position "
            "Xenia spot check is still pending."
        )
        self.note.setObjectName("mutedLabel")
        self.note.setWordWrap(True)

        box.addLayout(heading)
        box.addWidget(self.position)
        box.addWidget(self.current_state)
        box.addLayout(actions)
        box.addWidget(self.note)
        box.addStretch(1)
        self.setVisible(False)

    @staticmethod
    def _asset_id(player_index: int) -> str:
        return f"apf:player-position:{player_index}"

    @staticmethod
    def _parse_editor(row: InspectorRow) -> tuple[int, tuple[dict[str, object], ...]]:
        editor = row.fields.get("position_editor")
        player_index = row.fields.get("player_index")
        if row.kind != "player" or not isinstance(editor, dict):
            raise ValueError("This roster row has no editable player position.")
        if (
            isinstance(player_index, bool)
            or not isinstance(player_index, int)
            or not 0 <= player_index <= 2_253
        ):
            raise ValueError("This player has no valid position-editor identity.")
        if editor.get("asset_id") != PlayerPositionPanel._asset_id(player_index):
            raise ValueError(
                "This player's position editor does not match the selected player."
            )
        if (
            editor.get("editable") is not True
            or editor.get("backend_editable") is not True
            or editor.get("source_mirror_required") is not True
            or editor.get("semantic_relative_offset") != 0x34
            or editor.get("mirror_relative_offset") != 0x35
        ):
            raise ValueError(
                "This player's position safety contract is unavailable; no edit was enabled."
            )
        raw_choices = editor.get("choices")
        if not isinstance(raw_choices, (list, tuple)) or len(raw_choices) != 17:
            raise ValueError(
                "The player-position list is incomplete; expected all 17 positions."
            )
        choices: list[dict[str, object]] = []
        for code, raw in enumerate(raw_choices):
            if not isinstance(raw, dict):
                raise ValueError("The player-position list contains an invalid choice.")
            abbreviation = raw.get("abbreviation")
            name = raw.get("name")
            if (
                raw.get("code") != code
                or not isinstance(abbreviation, str)
                or not abbreviation
                or not isinstance(name, str)
                or not name
            ):
                raise ValueError(
                    "The player-position list is out of order or has an invalid label."
                )
            choices.append(dict(raw))
        return player_index, tuple(choices)

    def set_player(self, row: InspectorRow) -> None:
        if row.kind != "player" or not isinstance(
            row.fields.get("position_editor"), dict
        ):
            self.clear_player()
            return
        player_index, choices = self._parse_editor(row)
        self._player_index = player_index
        self._choices = choices
        self.position.blockSignals(True)
        self.position.clear()
        for choice in choices:
            self.position.addItem(
                f"{choice['abbreviation']} — {choice['name']}",
                int(choice["code"]),
            )
        self.position.blockSignals(False)
        self.position.setEnabled(True)
        self.setVisible(True)
        self.refresh_value()

    def clear_player(self) -> None:
        self._player_index = None
        self._choices = ()
        self.position.blockSignals(True)
        self.position.clear()
        self.position.blockSignals(False)
        self.position.setEnabled(False)
        self.status.setText("EDITABLE · 17 POSITIONS")
        self.current_state.setText(
            "Choose a player to edit the position stored in that player's record."
        )
        tip = (
            "Select a player first. Apply/Revert stay clickable so blocked "
            "states explain themselves."
        )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(tip)
        self.apply_button.setProperty("disableReason", tip)
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(tip)
        self.revert_button.setProperty("disableReason", tip)
        self.setVisible(False)

    def _current_value(self) -> int:
        if self._player_index is None:
            raise RuntimeError("No APF player is selected")
        value = self.facade.player_position_value(self._player_index)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 16:
            raise ValueError(
                "The selected player's current position is invalid; no edit was applied."
            )
        return value

    def refresh_value(self, preserve_code: int | None = None) -> None:
        if self._player_index is None:
            return
        current = self._current_value()
        target = current if preserve_code is None else preserve_code
        index = self.position.findData(target)
        if index < 0:
            index = self.position.findData(current)
        self.position.blockSignals(True)
        self.position.setCurrentIndex(index)
        self.position.blockSignals(False)
        self._editor_changed()

    def _editor_changed(self, _index: int = -1) -> None:
        if self._player_index is None:
            tip = "Select a player first."
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            self.revert_button.setEnabled(True)
            self.revert_button.setToolTip(tip)
            self.revert_button.setProperty("disableReason", tip)
            return
        selected = self.position.currentData()
        if isinstance(selected, bool) or not isinstance(selected, int):
            tip = (
                "Choose one of the 17 named positions; free-form codes are not accepted."
            )
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            return
        current = self._current_value()
        modified = self._asset_id(self._player_index) in self.facade.modified_asset_ids
        current_choice = self._choices[current]
        self.status.setText(
            "EDITABLE · MODIFIED" if modified else "EDITABLE · ORIGINAL"
        )
        self.current_state.setText(
            f"Current: {current_choice['abbreviation']} — {current_choice['name']} "
            f"(exact code {current}) · "
            + ("modified in this project" if modified else "original source value")
        )
        if selected != current:
            apply_tip = (
                f"Change only this player's position to code {selected} as one "
                "reversible project edit."
            )
            apply_block = ""
        else:
            apply_tip = apply_block = "This position is already active."
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(apply_tip)
        self.apply_button.setProperty("disableReason", apply_block)
        if modified:
            revert_tip = "Restore this player's exact source position."
            revert_block = ""
        else:
            revert_tip = revert_block = (
                "This player's position still matches the loaded source."
            )
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty("disableReason", revert_block)

    def _apply_position(self) -> None:
        reason = str(self.apply_button.property("disableReason") or "").strip()
        if reason:
            self.current_state.setText(reason)
            return
        selected = self.position.currentData()
        if (
            self._player_index is None
            or isinstance(selected, bool)
            or not isinstance(selected, int)
        ):
            return
        self.applyRequested.emit(self._player_index, selected)

    def _revert_position(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            self.current_state.setText(reason)
            return
        if self._player_index is None:
            return
        self.revertRequested.emit(self._player_index)


class RatingSheetImportPreviewDialog(QDialog):
    """Bounded, non-mutating review step for one private ratings CSV.

    The backend owns parsing and conflict detection.  This dialog deliberately
    receives only its immutable preview receipt; accepting it never performs a
    write by itself.  ``InspectorBrowser`` starts the one logical batch only
    after this modal has closed and the validation worker is fully idle.
    """

    def __init__(self, source: Path, preview: object, parent: QWidget | None = None):
        super().__init__(parent)
        self.source = Path(source)
        self.preview = preview
        self.setObjectName("ratingSheetImportPreviewDialog")
        self.setWindowTitle("Review APF ratings-sheet import")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.resize(680, 500)
        # Keep the review gate independently legible even when Qt applies a
        # platform dialog palette instead of the main-window palette.  This is
        # intentionally scoped to the modal so native file choosers and the
        # rest of the product theme remain untouched.
        self.setStyleSheet(
            """
            QDialog#ratingSheetImportPreviewDialog {
                background: #101827;
                color: #eef4ff;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel {
                color: #dce7f6;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel#panelTitle {
                color: #ffffff;
                font-size: 15px;
                font-weight: 700;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel#fieldLabel {
                color: #f4f7fb;
                font-weight: 700;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel#countPill {
                color: #ffffff;
                background: #243750;
                border: 1px solid #526984;
                border-radius: 8px;
                padding: 4px 8px;
                font-weight: 700;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel#findingText {
                color: #d7e2f1;
                background: #0b1220;
                border: 1px solid #2d4059;
                border-radius: 6px;
                padding: 7px 9px;
            }
            QDialog#ratingSheetImportPreviewDialog QLabel#mutedLabel {
                color: #c7d2e2;
            }
            QDialog#ratingSheetImportPreviewDialog QPlainTextEdit#ratingSheetImportSample {
                background: #0b1220;
                color: #e7edf7;
                border: 1px solid #405673;
                border-radius: 5px;
                padding: 7px;
            }
            QDialog#ratingSheetImportPreviewDialog QCheckBox {
                color: #eef4ff;
            }
            QDialog#ratingSheetImportPreviewDialog QPushButton {
                min-height: 32px;
                padding: 0 14px;
                color: #eef4ff;
                background: #25354b;
                border: 1px solid #526984;
                border-radius: 5px;
                font-weight: 700;
            }
            QDialog#ratingSheetImportPreviewDialog QPushButton:hover {
                border-color: #7d94b1;
                background: #31445e;
            }
            QDialog#ratingSheetImportPreviewDialog QPushButton#primaryButton {
                color: #111827;
                background: #f29a60;
                border-color: #f29a60;
            }
            QDialog#ratingSheetImportPreviewDialog QPushButton#primaryButton:hover {
                background: #ffad76;
            }
            QDialog#ratingSheetImportPreviewDialog QPushButton#primaryButton:disabled {
                color: #8090a5;
                background: #182235;
                border-color: #334158;
            }
            """
        )

        self.replacement_count = self._count(
            "replacement_count", "new_replacement_count"
        )
        self.revert_count = self._count("revert_count", "source_revert_count")
        self.unchanged_count = self._count(
            "unchanged_count", "already_matches_count"
        )
        reported_conflicts = self._count("conflict_count")
        self.source_conflict_count = self._count("source_conflict_count")
        self.project_conflict_count = self._count("project_conflict_count")
        # Fail closed if a future/older receipt reports conflicts without the
        # reviewed source-vs-project classification.  An unclassified conflict
        # must never gain the project's explicit override route by accident.
        self.source_conflict_count += max(
            0,
            reported_conflicts
            - self.source_conflict_count
            - self.project_conflict_count,
        )
        self.conflict_count = (
            self.source_conflict_count + self.project_conflict_count
        )
        self.error_count = self._count("error_count")
        self.change_count = self.replacement_count + self.revert_count

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("Review before anything changes")
        title.setObjectName("panelTitle")
        intro = QLabel(
            f"Checked <b>{self.source.name}</b>. Mod Studio has not changed the "
            "project yet."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(title)
        layout.addWidget(intro)

        counts = QGridLayout()
        counts.setHorizontalSpacing(10)
        counts.setVerticalSpacing(8)
        count_rows = (
            (
                "New replacements",
                self.replacement_count,
                "Sheet values that create or update a project rating edit.",
            ),
            (
                "Reverts to source",
                self.revert_count,
                "Sheet values that remove an active edit and restore the loaded game value.",
            ),
            (
                "Already matches",
                self.unchanged_count,
                "Cells that need no project change.",
            ),
            (
                "Source conflicts",
                self.source_conflict_count,
                "Wrong source fingerprint or edited source-owned metadata. These cannot be overridden.",
            ),
            (
                "Project conflicts",
                self.project_conflict_count,
                "Sheet values that disagree with active project edits and require explicit confirmation.",
            ),
            (
                "Errors",
                self.error_count,
                "Invalid or unsafe cells that cannot be applied.",
            ),
        )
        self.count_labels: dict[str, QLabel] = {}
        for row, (label, value, tooltip) in enumerate(count_rows):
            name = QLabel(label)
            name.setObjectName("fieldLabel")
            number = QLabel(f"{value:,}")
            number.setObjectName("countPill")
            number.setAlignment(Qt.AlignCenter)
            number.setMinimumWidth(72)
            name.setToolTip(tooltip)
            number.setToolTip(tooltip)
            counts.addWidget(name, row, 0)
            counts.addWidget(number, row, 1)
            self.count_labels[label] = number
        counts.setColumnStretch(0, 1)
        layout.addLayout(counts)

        samples = self._sample_lines()
        self.sample_heading = QLabel(
            "Conflict / error sample"
            if self.conflict_count or self.error_count
            else "Change sample"
        )
        self.sample_heading.setObjectName("fieldLabel")
        self.sample_view = QPlainTextEdit()
        self.sample_view.setObjectName("ratingSheetImportSample")
        self.sample_view.setReadOnly(True)
        self.sample_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.sample_view.setMinimumHeight(76)
        self.sample_view.setMaximumHeight(132)
        self.sample_view.setPlainText(
            "\n".join(samples)
            if samples
            else "No bounded sample was needed; the aggregate counts above are complete."
        )
        layout.addWidget(self.sample_heading)
        layout.addWidget(self.sample_view)

        self.conflict_confirmation = QCheckBox(
            "I understand: existing rating edits will be replaced or reverted by this sheet."
        )
        self.conflict_confirmation.setObjectName("ratingSheetConflictConfirmation")
        self.conflict_confirmation.setVisible(
            self.project_conflict_count > 0 and self.source_conflict_count == 0
        )
        self.conflict_confirmation.setEnabled(
            self.error_count == 0 and self.source_conflict_count == 0
        )
        self.conflict_confirmation.toggled.connect(self._update_apply_state)
        layout.addWidget(self.conflict_confirmation)

        self.private_warning = QLabel(
            "Private file warning · This CSV contains names and ratings derived "
            "from your own game. Keep it private. The shareable project stores "
            "only your replacement values and metadata—never this sheet or retail "
            "game bytes. A native source value of 100 is source/revert-only; new "
            "rating edits remain exact 0–99 values."
        )
        self.private_warning.setObjectName("findingText")
        self.private_warning.setWordWrap(True)
        layout.addWidget(self.private_warning)

        self.state_note = QLabel("")
        self.state_note.setObjectName("mutedLabel")
        self.state_note.setWordWrap(True)
        layout.addWidget(self.state_note)

        self.buttons = QDialogButtonBox()
        self.apply_button = self.buttons.addButton(
            "Apply ratings", QDialogButtonBox.AcceptRole
        )
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setAccessibleName("Apply reviewed APF ratings sheet")
        self.cancel_button = self.buttons.addButton(QDialogButtonBox.Cancel)
        self.cancel_button.setObjectName("ratingSheetCancelButton")
        self.cancel_button.setAccessibleName("Cancel APF ratings-sheet import")
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_apply_state()

    @property
    def allow_conflicts(self) -> bool:
        return (
            self.source_conflict_count == 0
            and self.project_conflict_count > 0
            and self.conflict_confirmation.isChecked()
        )

    def _count(self, *names: str) -> int:
        for name in names:
            value = getattr(self.preview, name, None)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return 0

    @staticmethod
    def _sample_value(sample: object, *names: str) -> object | None:
        for name in names:
            if isinstance(sample, dict) and name in sample:
                return sample[name]
            if hasattr(sample, name):
                return getattr(sample, name)
        return None

    def _sample_lines(self) -> tuple[str, ...]:
        raw_samples: list[object] = []
        for attribute in (
            "source_conflicts",
            "conflicts",
            "errors",
            "conflict_samples",
            "error_samples",
            "change_samples",
            "samples",
        ):
            value = getattr(self.preview, attribute, ())
            if isinstance(value, (tuple, list)):
                raw_samples.extend(value)
        lines: list[str] = []
        seen: set[str] = set()
        for sample in raw_samples:
            if isinstance(sample, str):
                line = sample.strip()
            else:
                player_index = self._sample_value(sample, "player_index")
                player_name = self._sample_value(
                    sample, "player_name", "display_name"
                )
                field = self._sample_value(
                    sample, "field_label", "field_id", "rating"
                )
                current = self._sample_value(
                    sample,
                    "current_value",
                    "project_value",
                    "source_value",
                    "from_value",
                )
                sheet = self._sample_value(
                    sample,
                    "desired_value",
                    "sheet_value",
                    "replacement_value",
                    "to_value",
                )
                reason = self._sample_value(sample, "reason", "message")
                identity = " · ".join(
                    str(value)
                    for value in (
                        f"Player {player_index}" if player_index is not None else None,
                        player_name,
                        field,
                    )
                    if value not in (None, "")
                )
                transition = (
                    f"{current} → {sheet}"
                    if current is not None and sheet is not None
                    else ""
                )
                line = " · ".join(
                    str(value)
                    for value in (identity, transition, reason)
                    if value not in (None, "")
                )
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
            if len(lines) >= 8:
                break
        return tuple(lines)

    def _update_apply_state(self, _checked: bool = False) -> None:
        project_conflicts_confirmed = (
            self.project_conflict_count == 0
            or self.conflict_confirmation.isChecked()
        )
        enabled = (
            self.change_count > 0
            and self.error_count == 0
            and self.source_conflict_count == 0
            and project_conflicts_confirmed
        )
        self.apply_button.setEnabled(enabled)
        self.apply_button.setText(
            f"Apply {self.change_count:,} rating change"
            + ("s" if self.change_count != 1 else "")
        )
        if self.source_conflict_count:
            note = (
                "This sheet does not match the exact loaded game source, or its "
                "source-owned identity metadata was edited. Source conflicts cannot "
                "be overridden. Export a fresh ratings sheet from this exact game and "
                "make rating-only changes there."
            )
        elif self.error_count:
            note = "Fix the CSV errors shown above, then preview the sheet again. Nothing can be applied yet."
        elif self.project_conflict_count and not project_conflicts_confirmed:
            note = (
                "Conflicts stay untouched unless you explicitly acknowledge replacing "
                "those active project edits."
            )
        elif not self.change_count:
            note = "This sheet already matches the project and loaded source; there is nothing to apply."
        else:
            note = (
                "Apply runs this entire reviewed plan as one action. One Undo restores "
                "the exact project edit set that existed before import."
            )
        self.state_note.setText(note)


class ExternalXma1EncoderDialog(QDialog):
    """File-picker-only setup for a user-installed XMA1 encoder.

    The default adapter contract is one input WAV followed by one output XMA
    filename.  An optional Advanced panel accepts one literal argv entry per
    line for other legal tools; it never accepts or invokes a shell command.
    Windows encoders are launched through a separately selected Wine
    executable. Neither tool is copied into a project or release.
    """

    def __init__(
        self,
        *,
        encoder_path: Path | None = None,
        wine_path: Path | None = None,
        use_wine: bool = False,
        arguments: tuple[str, ...] = ("{input}", "{output}"),
        timeout_seconds: int = 600,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._encoder: ExternalXma1Encoder | None = None
        self.setWindowTitle("Configure external XMA1 encoder")
        self.setModal(True)
        self.setMinimumWidth(570)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        heading = QLabel("Use your own XMA1 encoder")
        heading.setObjectName("panelTitle")
        explanation = QLabel(
            "APF 2K8 Mod Studio does not include an encoder. Choose a legally "
            "obtained XMA1 encoder already installed on this PC. Its binary/path and "
            "the input PCM WAV are not copied into a mod project; exact source-audio "
            "packet reuse is rejected."
        )
        explanation.setObjectName("findingText")
        explanation.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(explanation)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)
        encoder_label = QLabel("XMA1 encoder")
        encoder_label.setObjectName("fieldLabel")
        self.encoder_path = QLineEdit(
            str(encoder_path) if encoder_path is not None else ""
        )
        self.encoder_path.setReadOnly(True)
        self.encoder_path.setPlaceholderText("Choose an encoder executable…")
        self.encoder_path.setAccessibleName("Selected external XMA1 encoder path")
        self.encoder_browse_button = QPushButton("Browse…")
        self.encoder_browse_button.setObjectName("secondaryButton")
        self.encoder_browse_button.setAccessibleName(
            "Choose an external XMA1 encoder executable"
        )
        self.encoder_browse_button.clicked.connect(self._browse_encoder)
        form.addWidget(encoder_label, 0, 0)
        form.addWidget(self.encoder_path, 0, 1)
        form.addWidget(self.encoder_browse_button, 0, 2)

        self.use_wine_checkbox = QCheckBox("Run a Windows .exe through Wine")
        self.use_wine_checkbox.setAccessibleName(
            "Run the selected Windows XMA1 encoder through Wine"
        )
        self.use_wine_checkbox.setToolTip(
            "Windows .exe encoders require a real Wine executable on Linux. "
            "Native Linux encoder tools run directly."
        )
        form.addWidget(self.use_wine_checkbox, 1, 1, 1, 2)

        wine_label = QLabel("Wine executable")
        wine_label.setObjectName("fieldLabel")
        self.wine_path = QLineEdit(str(wine_path) if wine_path is not None else "")
        self.wine_path.setReadOnly(True)
        self.wine_path.setPlaceholderText("Wine will be detected when available…")
        self.wine_path.setAccessibleName("Selected Wine executable path")
        self.wine_browse_button = QPushButton("Browse…")
        self.wine_browse_button.setObjectName("secondaryButton")
        self.wine_browse_button.setAccessibleName("Choose a Wine executable")
        self.wine_browse_button.clicked.connect(self._browse_wine)
        form.addWidget(wine_label, 2, 0)
        form.addWidget(self.wine_path, 2, 1)
        form.addWidget(self.wine_browse_button, 2, 2)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        self.advanced_checkbox = QCheckBox(
            "Advanced: customize encoder arguments"
        )
        self.advanced_checkbox.setAccessibleName(
            "Show advanced external XMA1 encoder arguments"
        )
        self.arguments_editor = QPlainTextEdit()
        self.arguments_editor.setObjectName("externalEncoderArguments")
        self.arguments_editor.setAccessibleName(
            "External XMA1 encoder arguments, one argument per line"
        )
        self.arguments_editor.setPlaceholderText("{input}\n{output}")
        self.arguments_editor.setPlainText("\n".join(arguments))
        self.arguments_editor.setFixedHeight(108)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 1800)
        self.timeout_spin.setSingleStep(30)
        self.timeout_spin.setSuffix(" seconds")
        self.timeout_spin.setValue(max(30, min(1800, int(timeout_seconds))))
        self.timeout_spin.setAccessibleName(
            "External XMA1 encoder timeout in seconds"
        )
        self.timeout_label = QLabel("Encoding timeout")
        self.timeout_label.setObjectName("fieldLabel")
        self.arguments_note = QLabel(
            "One argument per line—not a command line. Spaces stay inside that one "
            "argument; shell syntax is never interpreted. {input} and {output} are "
            "required exactly once. Optional placeholders: {channels}, {sample_rate}, "
            "{sample_count}, and {encoded_size}. The 600-second default covers long "
            "soundtrack slots through Wine; use 30–1800 seconds if your encoder differs."
        )
        self.arguments_note.setObjectName("mutedLabel")
        self.arguments_note.setWordWrap(True)
        custom_configuration = (
            arguments != ("{input}", "{output}")
            or int(timeout_seconds) != 600
        )
        self.advanced_checkbox.setChecked(custom_configuration)
        self.arguments_editor.setVisible(custom_configuration)
        self.timeout_label.setVisible(custom_configuration)
        self.timeout_spin.setVisible(custom_configuration)
        self.arguments_note.setVisible(custom_configuration)
        self.advanced_checkbox.toggled.connect(self.arguments_editor.setVisible)
        self.advanced_checkbox.toggled.connect(self.timeout_label.setVisible)
        self.advanced_checkbox.toggled.connect(self.timeout_spin.setVisible)
        self.advanced_checkbox.toggled.connect(self.arguments_note.setVisible)
        root.addWidget(self.advanced_checkbox)
        root.addWidget(self.arguments_editor)
        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(10)
        timeout_row.addWidget(self.timeout_label)
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch(1)
        root.addLayout(timeout_row)
        root.addWidget(self.arguments_note)

        self.contract_note = QLabel(
            "Compatibility contract • The selected tool must accept an input PCM WAV "
            "and output XMA filename. Mod Studio runs it privately without a shell. "
            "Its result is never trusted automatically: every final XMA1 stream must "
            "pass the exact-slot size, packet, decode, duration, source-fingerprint, "
            "and shared-owner gates before the project changes."
        )
        self.contract_note.setObjectName("mutedLabel")
        self.contract_note.setWordWrap(True)
        root.addWidget(self.contract_note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.save_button = self.buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Save encoder settings")
        self.save_button.setObjectName("primaryButton")
        self.buttons.accepted.connect(self._accept_configuration)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        is_windows_encoder = self._is_windows_encoder(self.encoder_path.text())
        self.use_wine_checkbox.setChecked(is_windows_encoder and use_wine)
        if is_windows_encoder and not self.use_wine_checkbox.isChecked():
            # A Windows executable cannot be launched directly on Linux. Keep
            # the no-terminal default useful when loading older settings.
            self.use_wine_checkbox.setChecked(True)
        self.encoder_path.textChanged.connect(self._update_state)
        self.wine_path.textChanged.connect(self._update_state)
        self.use_wine_checkbox.toggled.connect(self._update_state)
        self._update_state()

    @staticmethod
    def _is_windows_encoder(value: str) -> bool:
        return Path(value.strip()).suffix.casefold() == ".exe" if value.strip() else False

    @staticmethod
    def _canonical_tool_path(value: str) -> Path:
        try:
            return Path(value).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"That tool path could not be resolved to a real local file: {exc}"
            ) from exc

    def _browse_encoder(self) -> None:
        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose your external XMA1 encoder",
            str(Path.home()),
            "Windows XMA1 encoder (*.exe);;Executable files (*)",
        )
        if not selected:
            return
        try:
            selected_path = self._canonical_tool_path(selected)
        except ValueError as exc:
            QMessageBox.information(self, "Encoder path is unavailable", str(exc))
            return
        self.encoder_path.setText(str(selected_path))
        windows_encoder = selected_path.suffix.casefold() == ".exe"
        self.use_wine_checkbox.setChecked(windows_encoder)
        if windows_encoder and not self.wine_path.text().strip():
            discovered = shutil.which("wine")
            if discovered:
                try:
                    discovered_path = self._canonical_tool_path(discovered)
                except ValueError:
                    discovered_path = None
                if discovered_path is not None:
                    self.wine_path.setText(str(discovered_path))
        self._update_state()

    def _browse_wine(self) -> None:
        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose the Wine executable",
            str(Path.home()),
            "Executable files (*)",
        )
        if not selected:
            return
        try:
            selected_path = self._canonical_tool_path(selected)
        except ValueError as exc:
            QMessageBox.information(self, "Wine path is unavailable", str(exc))
            return
        self.wine_path.setText(str(selected_path))

    def _update_state(self, _value: object = None) -> None:
        encoder_value = self.encoder_path.text().strip()
        windows_encoder = self._is_windows_encoder(encoder_value)
        self.use_wine_checkbox.setEnabled(windows_encoder)
        if not windows_encoder and self.use_wine_checkbox.isChecked():
            self.use_wine_checkbox.blockSignals(True)
            self.use_wine_checkbox.setChecked(False)
            self.use_wine_checkbox.blockSignals(False)
        wine_enabled = windows_encoder and self.use_wine_checkbox.isChecked()
        self.wine_path.setEnabled(wine_enabled)
        self.wine_browse_button.setEnabled(wine_enabled)
        save_ready = bool(encoder_value) and (
            not windows_encoder
            or (
                self.use_wine_checkbox.isChecked()
                and bool(self.wine_path.text().strip())
            )
        )
        # Never silent-gray: Save stays clickable; disableReason teaches walls.
        self.save_button.setEnabled(True)
        if save_ready:
            self.save_button.setToolTip("Save encoder settings.")
            self.save_button.setProperty("disableReason", "")
        else:
            tip = (
                "Choose a valid encoder path"
                + (
                    " and Wine when using a Windows .exe"
                    if windows_encoder
                    else ""
                )
                + " before saving."
            )
            self.save_button.setToolTip(tip)
            self.save_button.setProperty("disableReason", tip)

    def _accept_configuration(self) -> None:
        reason = str(self.save_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot save encoder yet", reason)
            return
        encoder_value = self.encoder_path.text().strip()
        if not encoder_value:
            return
        wine_value = (
            self.wine_path.text().strip()
            if self.use_wine_checkbox.isChecked()
            else ""
        )
        try:
            arguments = (
                tuple(self.arguments_editor.toPlainText().splitlines())
                if self.advanced_checkbox.isChecked()
                else ("{input}", "{output}")
            )
            timeout_seconds = (
                self.timeout_spin.value()
                if self.advanced_checkbox.isChecked()
                else 600
            )
            encoder = ExternalXma1Encoder(
                self._canonical_tool_path(encoder_value),
                arguments=arguments,
                wine_executable=(
                    self._canonical_tool_path(wine_value) if wine_value else None
                ),
                timeout_seconds=timeout_seconds,
            )
            encoder.validate()
        except Exception as exc:
            QMessageBox.information(
                self,
                "Encoder is not ready",
                f"{exc}\n\nChoose another encoder or Wine executable. No setting was changed.",
            )
            return
        self._encoder = encoder
        self.accept()

    @property
    def encoder(self) -> ExternalXma1Encoder:
        if self._encoder is None:
            raise RuntimeError("The encoder dialog has not accepted a configuration")
        return self._encoder


# Guided XMA1 encoder setup -----------------------------------------------
#
# No XMA1 encoder ships with the editor, so the first audio replacement needs
# a user-supplied tool.  The wizard below auto-detects what it can (ffmpeg for
# format conversion, Wine for Windows .exe tools), explains the two required
# argv placeholders, and test-runs the chosen encoder on a private one-second
# tone before anything is saved.  The real exact-slot gates still run on every
# genuine encode; the tone test is a setup-time sanity check only.

XMA1_WIZARD_TEMPLATE_ARGUMENTS = ("{input}", "{output}")
XMA1_SMOKE_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Xma1SmokeTestResult:
    """Outcome of test-running a user-supplied encoder on a one-second tone."""

    passed: bool
    testable: bool
    summary: str
    exit_code: int | None = None
    output_bytes: int = 0


def xma1_encoder_argument_problem(
    arguments: tuple[str, ...] | list[str],
) -> str | None:
    """Plain-language check of the argv template, before anything runs."""

    if not arguments:
        return (
            "The encoder needs at least two arguments: {input} and {output}. "
            "Choose “Use the recommended template” to fill them in."
        )
    for placeholder in ("{input}", "{output}"):
        count = sum(argument.count(placeholder) for argument in arguments)
        if count != 1:
            plural = "s" if count != 1 else ""
            return (
                f"The encoder arguments must contain {placeholder} exactly "
                f"once (currently {count} time{plural}). {input_hint(placeholder)}"
            )
    return None


def input_hint(placeholder: str) -> str:
    if placeholder == "{input}":
        return "That is where the PCM WAV to encode goes. "
    return "That is where the encoder must write the finished XMA1 file. "


def write_xma1_test_tone(destination: Path) -> Path:
    """Write a private one-second 440 Hz PCM16 WAV used only to test encoders."""

    import struct

    sample_rate = 44100
    frames = b"".join(
        struct.pack(
            "<h",
            int(12000.0 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)),
        )
        for index in range(sample_rate)
    )
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as tone:
        tone.setnchannels(1)
        tone.setsampwidth(2)
        tone.setframerate(sample_rate)
        tone.writeframes(frames)
    return destination


def run_xma1_smoke_test(
    *,
    executable: Path,
    arguments: tuple[str, ...],
    wine_executable: Path | None = None,
    work_dir: Path,
    timeout_seconds: float = XMA1_SMOKE_TIMEOUT_SECONDS,
) -> Xma1SmokeTestResult:
    """Run the user's encoder once on a one-second tone and report plainly.

    This never touches game audio and stages nothing; it exists so a setup
    mistake is caught at configuration time rather than mid-encode.
    """

    problem = xma1_encoder_argument_problem(arguments)
    if problem is not None:
        return Xma1SmokeTestResult(False, False, problem)
    if any("{encoded_size}" in argument for argument in arguments):
        return Xma1SmokeTestResult(
            False,
            False,
            "Your arguments use {encoded_size}, the slot's exact byte count. "
            "A one-second tone has no slot to predict that from, so the test "
            "cannot run. You can still save this setup — every real encode is "
            "fully validated against its slot.",
        )
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    tone = work / "tone-input.wav"
    output = work / "tone-output.xma"
    output.unlink(missing_ok=True)
    write_xma1_test_tone(tone)

    argv: list[str] = []
    if wine_executable is not None:
        argv.append(str(wine_executable))
    argv.append(str(executable))
    replacements = {
        "{input}": str(tone),
        "{output}": str(output),
        "{channels}": "1",
        "{sample_rate}": "44100",
        "{sample_count}": "44100",
    }
    for argument in arguments:
        rendered = argument
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)
        argv.append(rendered)

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return Xma1SmokeTestResult(
            False,
            True,
            "The encoder could not be started. Fix: check that the path points "
            "to a real program, and that a Windows .exe has a Wine executable "
            "selected.",
        )
    except subprocess.TimeoutExpired:
        return Xma1SmokeTestResult(
            False,
            True,
            f"The encoder did not finish within {int(timeout_seconds)} seconds "
            "on a one-second tone. Fix: check that it is the right program and "
            "that its arguments write the output file.",
        )
    except OSError as exc:
        return Xma1SmokeTestResult(
            False, True, f"The encoder could not be started: {exc}"
        )

    size = output.stat().st_size if output.exists() else 0
    if completed.returncode == 0 and size > 0:
        return Xma1SmokeTestResult(
            True,
            True,
            f"Success — the encoder ran and wrote {size:,} bytes of XMA1 for "
            "the one-second tone.",
            completed.returncode,
            size,
        )
    detail = (completed.stderr or completed.stdout or b"").decode(
        "utf-8", "replace"
    ).strip()
    if detail:
        detail = "\n\nEncoder output:\n" + "\n".join(detail.splitlines()[:6])
    if completed.returncode != 0:
        message = (
            f"The encoder exited with code {completed.returncode}. Fix: check "
            "its arguments — one literal argument per line, with {input} and "
            "{output} exactly once."
        )
    else:
        message = (
            "The encoder exited cleanly but did not write the {output} file. "
            "Fix: check that {output} is the argument where it writes the "
            "result."
        )
    return Xma1SmokeTestResult(
        False, True, message + detail, completed.returncode, size
    )


class Xma1EncoderSetupWizard(QDialog):
    """Guided first-time setup for a user-supplied XMA1 encoder.

    The editor cannot ship an XMA1 encoder, so audio replacement needs one
    the user already has.  This wizard walks that setup end to end: it shows
    what was auto-detected, explains the two required {input}/{output}
    placeholders with a copy-paste template, test-runs the encoder on a
    one-second tone, and only then saves anything.
    """

    def __init__(
        self,
        *,
        encoder_path: Path | None = None,
        wine_path: Path | None = None,
        use_wine: bool = False,
        arguments: tuple[str, ...] = XMA1_WIZARD_TEMPLATE_ARGUMENTS,
        timeout_seconds: int = 600,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set up your XMA1 encoder")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._encoder: ExternalXma1Encoder | None = None
        self._smoke_passed = False
        self._smoke_testable = True
        self._temporary: Path | None = None
        self._timeout_seconds = max(30, min(1800, int(timeout_seconds)))
        self.destroyed.connect(self._cleanup_tone_workspace)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(11)

        heading = QLabel("Set up your XMA1 encoder")
        heading.setObjectName("heroTitle")
        root.addWidget(heading)
        explanation = QLabel(
            "The Xbox 360 stores this game's audio as XMA1, and no XMA1 encoder "
            "ships with Mod Studio. Point this setup at a legally obtained "
            "encoder already on this PC. The editor test-runs it on a private "
            "one-second tone before saving, and every real encode is still "
            "checked against its exact slot before anything is staged. The "
            "encoder path stays in this PC's settings and never enters a "
            "project."
        )
        explanation.setObjectName("findingText")
        explanation.setWordWrap(True)
        root.addWidget(explanation)

        self.ffmpeg_status = QLabel(self._ffmpeg_status_text())
        self.ffmpeg_status.setObjectName("metadataText")
        self.ffmpeg_status.setWordWrap(True)
        root.addWidget(self.ffmpeg_status)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)
        encoder_label = QLabel("XMA1 encoder")
        encoder_label.setObjectName("fieldLabel")
        self.encoder_path = QLineEdit(
            str(encoder_path) if encoder_path is not None else ""
        )
        self.encoder_path.setReadOnly(True)
        self.encoder_path.setPlaceholderText("Choose an encoder executable…")
        self.encoder_path.setAccessibleName("Selected external XMA1 encoder path")
        self.encoder_browse_button = QPushButton("Browse…")
        self.encoder_browse_button.setObjectName("secondaryButton")
        self.encoder_browse_button.clicked.connect(self._browse_encoder)
        form.addWidget(encoder_label, 0, 0)
        form.addWidget(self.encoder_path, 0, 1)
        form.addWidget(self.encoder_browse_button, 0, 2)

        self.use_wine_checkbox = QCheckBox("Run a Windows .exe through Wine")
        self.use_wine_checkbox.setToolTip(
            "Windows .exe encoders require a real Wine executable on Linux. "
            "Native Linux encoder tools run directly."
        )
        form.addWidget(self.use_wine_checkbox, 1, 1, 1, 2)

        wine_label = QLabel("Wine executable")
        wine_label.setObjectName("fieldLabel")
        self.wine_path = QLineEdit(str(wine_path) if wine_path is not None else "")
        self.wine_path.setReadOnly(True)
        self.wine_path.setPlaceholderText("Wine is detected automatically when available…")
        self.wine_browse_button = QPushButton("Browse…")
        self.wine_browse_button.setObjectName("secondaryButton")
        self.wine_browse_button.clicked.connect(self._browse_wine)
        form.addWidget(wine_label, 2, 0)
        form.addWidget(self.wine_path, 2, 1)
        form.addWidget(self.wine_browse_button, 2, 2)
        form.setColumnStretch(1, 1)
        root.addLayout(form)

        arguments_heading = QLabel("Encoder arguments")
        arguments_heading.setObjectName("fieldLabel")
        root.addWidget(arguments_heading)
        self.arguments_editor = QPlainTextEdit()
        self.arguments_editor.setObjectName("externalEncoderArguments")
        self.arguments_editor.setAccessibleName(
            "External XMA1 encoder arguments, one argument per line"
        )
        self.arguments_editor.setPlainText("\n".join(arguments))
        self.arguments_editor.setFixedHeight(96)
        root.addWidget(self.arguments_editor)
        template_row = QHBoxLayout()
        self.template_note = QLabel(
            "One argument per line — not a shell command. {input} is the PCM WAV "
            "to encode and {output} is where the XMA1 result is written; each "
            "must appear exactly once. Optional: {channels}, {sample_rate}, "
            "{sample_count}, {encoded_size}."
        )
        self.template_note.setObjectName("mutedLabel")
        self.template_note.setWordWrap(True)
        self.use_template_button = QPushButton("Use the recommended template")
        self.use_template_button.setObjectName("secondaryButton")
        self.use_template_button.clicked.connect(self._use_recommended_template)
        template_row.addWidget(self.template_note, 1)
        template_row.addWidget(self.use_template_button)
        root.addLayout(template_row)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test encoder on a 1-second tone")
        self.test_button.setObjectName("primaryButton")
        self.test_button.clicked.connect(self._run_smoke_test)
        self.test_result = QLabel("Not tested yet.")
        self.test_result.setObjectName("mutedLabel")
        self.test_result.setWordWrap(True)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_result, 1)
        root.addLayout(test_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.save_button = self.buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Save encoder settings")
        self.save_button.setObjectName("primaryButton")
        # Never silent-gray at construction; _update_state teaches walls.
        self.save_button.setEnabled(True)
        self.save_button.setProperty(
            "disableReason",
            "Choose an encoder path and pass the 1-second tone test first.",
        )
        self.buttons.accepted.connect(self._accept_configuration)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        if use_wine and wine_path is None:
            discovered = shutil.which("wine")
            if discovered:
                self.wine_path.setText(str(Path(discovered).resolve()))
        is_windows_encoder = self._is_windows_encoder(self.encoder_path.text())
        self.use_wine_checkbox.setChecked(use_wine or is_windows_encoder)
        self.encoder_path.textChanged.connect(self._update_state)
        self.wine_path.textChanged.connect(self._update_state)
        self.use_wine_checkbox.toggled.connect(self._update_state)
        self.arguments_editor.textChanged.connect(self._invalidate_test)
        self._update_state()

    @staticmethod
    def _ffmpeg_status_text() -> str:
        if audio_conform.conversion_available():
            return (
                "✓ FFmpeg was found — MP3, FLAC, OGG, M4A and other formats are "
                "converted to the slot's exact shape automatically."
            )
        return (
            "○ FFmpeg was not found — install it to drop MP3, FLAC, OGG or M4A "
            "and have them converted. Exact PCM16 WAVs work without it."
        )

    @staticmethod
    def _is_windows_encoder(value: str) -> bool:
        return Path(value.strip()).suffix.casefold() == ".exe" if value.strip() else False

    @staticmethod
    def _canonical_tool_path(value: str) -> Path:
        try:
            return Path(value).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"That tool path could not be resolved to a real local file: {exc}"
            ) from exc

    def _browse_encoder(self) -> None:
        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose your external XMA1 encoder",
            str(Path.home()),
            "Windows XMA1 encoder (*.exe);;Executable files (*)",
        )
        if not selected:
            return
        try:
            selected_path = self._canonical_tool_path(selected)
        except ValueError as exc:
            QMessageBox.information(self, "Encoder path is unavailable", str(exc))
            return
        self.encoder_path.setText(str(selected_path))
        if selected_path.suffix.casefold() == ".exe":
            self.use_wine_checkbox.setChecked(True)
            if not self.wine_path.text().strip():
                discovered = shutil.which("wine")
                if discovered:
                    try:
                        self.wine_path.setText(
                            str(self._canonical_tool_path(discovered))
                        )
                    except ValueError:
                        pass
        self._update_state()

    def _browse_wine(self) -> None:
        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose the Wine executable",
            str(Path.home()),
            "Executable files (*)",
        )
        if not selected:
            return
        try:
            selected_path = self._canonical_tool_path(selected)
        except ValueError as exc:
            QMessageBox.information(self, "Wine path is unavailable", str(exc))
            return
        self.wine_path.setText(str(selected_path))

    def _use_recommended_template(self) -> None:
        self.arguments_editor.setPlainText(
            "\n".join(XMA1_WIZARD_TEMPLATE_ARGUMENTS)
        )

    def _cleanup_tone_workspace(self, *_args: object) -> None:
        root = self._temporary
        self._temporary = None
        if root is not None and root.name.startswith("apf-xma1-wizard-"):
            shutil.rmtree(root, ignore_errors=True)

    def _current_arguments(self) -> tuple[str, ...]:
        return tuple(
            line
            for line in (
                line.strip()
                for line in self.arguments_editor.toPlainText().splitlines()
            )
            if line
        )

    def _invalidate_test(self) -> None:
        # Any change to the tool or its arguments voids a previous test run.
        self._smoke_passed = False
        self._smoke_testable = True
        self.test_result.setText("Not tested yet.")
        self._update_state()

    def _update_state(self, *_args: object) -> None:
        encoder_value = self.encoder_path.text().strip()
        windows_encoder = self._is_windows_encoder(encoder_value)
        self.use_wine_checkbox.setEnabled(windows_encoder)
        if not windows_encoder and self.use_wine_checkbox.isChecked():
            self.use_wine_checkbox.blockSignals(True)
            self.use_wine_checkbox.setChecked(False)
            self.use_wine_checkbox.blockSignals(False)
        wine_enabled = windows_encoder and self.use_wine_checkbox.isChecked()
        self.wine_path.setEnabled(wine_enabled)
        self.wine_browse_button.setEnabled(wine_enabled)
        configuration_complete = bool(encoder_value) and (
            not windows_encoder
            or (self.use_wine_checkbox.isChecked() and bool(self.wine_path.text().strip()))
        )
        # Never silent-gray: Test/Save stay clickable; disableReason teaches walls.
        if configuration_complete:
            self.test_button.setEnabled(True)
            self.test_button.setToolTip(
                "Run a 1-second tone through the configured encoder (smoke test)."
            )
            self.test_button.setProperty("disableReason", "")
        else:
            tip = (
                "Choose a valid encoder path first"
                + (
                    " (and Wine when using a Windows .exe)."
                    if windows_encoder
                    else "."
                )
            )
            self.test_button.setEnabled(True)
            self.test_button.setToolTip(tip)
            self.test_button.setProperty("disableReason", tip)
        save_ready = bool(
            configuration_complete
            and (self._smoke_passed or not self._smoke_testable)
        )
        if save_ready:
            self.save_button.setEnabled(True)
            self.save_button.setToolTip("Save encoder settings for APF audio replace.")
            self.save_button.setProperty("disableReason", "")
        else:
            tip = (
                "Pass the 1-second tone test first, then Save encoder settings."
                if configuration_complete
                else "Choose an encoder path"
                + (
                    " (and Wine for Windows encoders)"
                    if windows_encoder
                    else ""
                )
                + ", run the tone test, then Save."
            )
            self.save_button.setEnabled(True)
            self.save_button.setToolTip(tip)
            self.save_button.setProperty("disableReason", tip)

    def _spec_from_fields(self) -> tuple[Path, tuple[str, ...], Path | None] | None:
        encoder_value = self.encoder_path.text().strip()
        if not encoder_value:
            return None
        try:
            executable = self._canonical_tool_path(encoder_value)
        except ValueError as exc:
            QMessageBox.information(self, "Encoder path is unavailable", str(exc))
            return None
        wine_executable: Path | None = None
        if self._is_windows_encoder(encoder_value) and self.use_wine_checkbox.isChecked():
            wine_value = self.wine_path.text().strip()
            if not wine_value:
                return None
            try:
                wine_executable = self._canonical_tool_path(wine_value)
            except ValueError as exc:
                QMessageBox.information(self, "Wine path is unavailable", str(exc))
                return None
        return executable, self._current_arguments(), wine_executable

    def _run_smoke_test(self) -> None:
        reason = str(self.test_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot test encoder yet", reason)
            return
        spec = self._spec_from_fields()
        if spec is None:
            return
        executable, arguments, wine_executable = spec
        if self._temporary is None:
            self._temporary = Path(tempfile.mkdtemp(prefix="apf-xma1-wizard-"))
        self.test_result.setText("Running the encoder on a one-second tone…")
        application = QApplication.instance()
        if application is not None:
            application.processEvents()
        result = run_xma1_smoke_test(
            executable=executable,
            arguments=arguments,
            wine_executable=wine_executable,
            work_dir=self._temporary,
        )
        self._smoke_passed = result.passed
        self._smoke_testable = result.testable
        self.test_result.setText(result.summary)
        self._update_state()

    def _accept_configuration(self) -> None:
        reason = str(self.save_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot save encoder yet", reason)
            return
        spec = self._spec_from_fields()
        if spec is None:
            return
        executable, arguments, wine_executable = spec
        try:
            encoder = ExternalXma1Encoder(
                executable,
                arguments=arguments,
                wine_executable=wine_executable,
                timeout_seconds=self._timeout_seconds,
            )
            encoder.validate()
        except Exception as exc:
            QMessageBox.information(
                self,
                "Encoder is not ready",
                f"{exc}\n\nFix: choose another encoder or Wine executable. No "
                "setting was changed.",
            )
            return
        self._encoder = encoder
        self.accept()

    @property
    def encoder(self) -> ExternalXma1Encoder:
        if self._encoder is None:
            raise RuntimeError("The encoder wizard has not saved a configuration")
        return self._encoder


class InspectorBrowser(QFrame):
    """Paged renderer for live-source semantic models and their owned actions."""

    modifiedChanged = pyqtSignal()
    audioExportStarted = pyqtSignal()
    audioExportFinished = pyqtSignal()
    audioImportStarted = pyqtSignal()
    audioImportFinished = pyqtSignal()
    pcmEncodingStarted = pyqtSignal()
    pcmEncodingFinished = pyqtSignal()
    directAudioReplacementWorkerFinished = pyqtSignal()
    audioAnnotationChanged = pyqtSignal(str)
    audioAnnotationWorkerFinished = pyqtSignal()

    def __init__(
        self,
        title: str,
        facade: ApfStudioFacade,
        run_task: TaskRunner,
        *,
        run_when_idle: IdleRunner | None = None,
        audio_mode: bool = False,
        text_mode: bool = False,
        roster_mode: bool = False,
        roster_writes_enabled: bool = False,
        audio_settings: QSettings | None = None,
    ):
        super().__init__()
        self.setObjectName("panel")
        self.title_text = title
        self.facade = facade
        self.run_task = run_task
        self._worker_idle_barrier_available = run_when_idle is not None
        self._run_when_idle = run_when_idle or (
            lambda callback: QTimer.singleShot(0, callback)
        )
        self.audio_mode = audio_mode
        self.text_mode = text_mode
        self.roster_mode = roster_mode
        self.roster_writes_enabled = roster_writes_enabled
        self._annotation_capable = bool(
            audio_mode
            and hasattr(facade, "labeled_audio_asset_ids")
            and all(
                callable(getattr(facade, name, None))
                for name in (
                    "audio_annotation",
                    "set_audio_annotation",
                    "clear_audio_annotation",
                )
            )
        )
        self._audio_settings = (
            audio_settings
            if audio_mode and audio_settings is not None
            else QSettings(
                QSettings.IniFormat,
                QSettings.UserScope,
                PRODUCT_NAME,
                "audio-authoring",
            )
            if audio_mode
            else None
        )
        self.model: PagedModel | None = None
        self.offset = 0
        self._visible: dict[str, InspectorRow] = {}
        # Audio shortlists deliberately live only for this loaded inspector
        # session.  They contain decoded row identities, never audio bytes, and
        # do not enter a shareable project.
        self._audio_shortlist: dict[str, InspectorRow] = {}
        self._cleared_audio_shortlist: tuple[tuple[str, InspectorRow], ...] = ()
        self._audio_review_mode = False
        self._audio_review_restore_offset = 0
        self._audio_review_restore_row_id: str | None = None
        self._soundtrack_album_mode = False
        self._soundtrack_album_restore_offset = 0
        self._soundtrack_album_restore_row_id: str | None = None
        self._soundtrack_album_rows: dict[str, tuple[InspectorRow, ...]] = {}
        # A displayed page is safe for page-wide actions only while these exact
        # controls still describe it.  The epoch prevents a token from one
        # decoded game/model being accepted by another.
        self._audio_catalog_epoch = 0
        self._applied_audio_query_token: (
            tuple[int, str, str | None, str | None, str | None, bool] | None
        ) = None
        self._applied_audio_offset = 0
        self._applied_audio_count_text = ""
        self._applied_audio_page_text = ""
        self._applied_audio_previous_available = False
        self._applied_audio_next_available = False
        # Filtering the complete 47,814-row Audio model is independent of the
        # selected table row. Cache one exact applied-query/album result so a
        # selection change only recomputes shortlist differences, not the
        # whole catalog search.
        self._matching_audio_cache_key: tuple[object, ...] | None = None
        self._matching_audio_cache: tuple[InspectorRow, ...] = ()
        self._annotation_loading = False
        self._annotation_drafts: dict[str, tuple[str, str]] = {}
        self._audio_annotation_running = False
        self._text_allocations: dict[str, object] = {}
        self._roster_allocations: dict[str, object] = {}
        self._selected_roster_alias_asset_id: str | None = None
        self._selected_roster_alias_labels: tuple[str, ...] = ()
        # Waveforms are explicit, session-only reads of the already verified
        # preview WAV.  One request at a time prevents repeated long-track
        # decodes from competing with the 47,814-row browser.
        self._waveform_generation = 0
        self._waveform_request: WaveformRequest | None = None
        self._waveform_selected_row_id: str | None = None
        # Bulk audio exports are read-only but can be large.  The event never
        # crosses into a project or source write; exporters check it only
        # between complete sounds/banks so a file is never cut in half.
        self._audio_export_cancel = threading.Event()
        self._audio_export_running = False
        # Replacement packs stay project-atomic.  Cancellation is observed at
        # safe boundaries and can also stop a user-supplied encoder before any
        # exact-slot edit is staged.
        self._audio_import_cancel = threading.Event()
        self._audio_import_running = False
        # A long soundtrack slot can spend several minutes in a user-supplied
        # encoder, especially through Wine. Cancellation is cooperative and is
        # checked by the backend before any exact-slot edit can be staged.
        self._pcm_encoding_cancel = threading.Event()
        self._pcm_encoding_running = False
        # Direct XMA1 replacement is also a blocking worker. Keep every Audio
        # mutation action disabled from submission until the product runner has
        # unregistered that exact worker; a rapid second drop must never look
        # accepted and then disappear at the admission gate.
        self._direct_audio_replacement_running = False
        self.audioExportStarted.connect(self._audio_export_started)
        self.audioExportFinished.connect(self._audio_export_finished)
        self.audioImportStarted.connect(self._audio_import_started)
        self.audioImportFinished.connect(self._audio_import_finished)
        self.pcmEncodingStarted.connect(self._pcm_encoding_started)
        self.pcmEncodingFinished.connect(self._pcm_encoding_finished)
        self.directAudioReplacementWorkerFinished.connect(
            self._direct_audio_replacement_worker_finished
        )
        self.audioAnnotationWorkerFinished.connect(
            self._audio_annotation_worker_finished
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        self.summary = QLabel("Open this tab after loading a game to decode its live model.")
        self.summary.setObjectName("mutedLabel")
        self.summary.setWordWrap(True)
        heading.addWidget(title_label)
        heading.addStretch(1)
        heading.addWidget(self.summary)
        layout.addLayout(heading)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search decoded names, identities, and fields…")
        self.search.setClearButtonEnabled(True)
        self.kind_filter = QComboBox()
        self.kind_filter.setMinimumWidth(190)
        self.kind_filter.addItem("All decoded record kinds", None)
        self.role_filter = QComboBox()
        self.role_filter.setMinimumWidth(190)
        self.role_filter.addItem("All audio roles", None)
        self.role_filter.setVisible(audio_mode)
        self.source_filter = QComboBox()
        self.source_filter.setMinimumWidth(270)
        self.source_filter.addItem("All audio sources", None)
        self.source_filter.setVisible(audio_mode)
        self.source_filter.setAccessibleName("Audio source or bank filter")
        self.source_filter.setToolTip(
            "Choose standalone AUDO or one exact AUSB bank. Bank identity includes "
            "archive coordinates so duplicate names remain distinct."
        )
        self.export_rows_button = QPushButton("Export decoded rows…")
        self.export_rows_button.setObjectName("secondaryButton")
        self.export_rows_button.setToolTip(
            "Save every row matching the current search and filters as useful JSON or CSV."
        )
        self.export_rows_button.clicked.connect(self._export_rows)
        self.export_ratings_sheet_button = QPushButton(
            "Export ratings sheet…"
        )
        self.export_ratings_sheet_button.setObjectName("secondaryButton")
        self.export_ratings_sheet_button.setVisible(roster_mode)
        # Never silent-gray: stay clickable; disableReason teaches Load game.
        _ratings_boot = (
            "Load a supported APF game first, then Export/Import ratings sheet."
        )
        self.export_ratings_sheet_button.setEnabled(True)
        self.export_ratings_sheet_button.setToolTip(_ratings_boot)
        self.export_ratings_sheet_button.setProperty("disableReason", _ratings_boot)
        self.export_ratings_sheet_button.clicked.connect(
            self._export_player_rating_sheet
        )
        self.import_ratings_sheet_button = QPushButton(
            "Import ratings sheet…"
        )
        self.import_ratings_sheet_button.setObjectName("secondaryButton")
        self.import_ratings_sheet_button.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.import_ratings_sheet_button.setAccessibleName(
            "Import complete APF player ratings sheet"
        )
        self.import_ratings_sheet_button.setVisible(roster_mode)
        self.import_ratings_sheet_button.setEnabled(True)
        self.import_ratings_sheet_button.setToolTip(_ratings_boot)
        self.import_ratings_sheet_button.setProperty("disableReason", _ratings_boot)
        self.import_ratings_sheet_button.clicked.connect(
            self._import_player_rating_sheet
        )
        self.count = QLabel("Not loaded")
        self.count.setObjectName("countPill")
        controls.addWidget(self.search, 1)
        if not audio_mode:
            controls.addWidget(self.kind_filter)
        if roster_mode:
            controls.addWidget(self.export_ratings_sheet_button)
            controls.addWidget(self.import_ratings_sheet_button)
        controls.addWidget(self.export_rows_button)
        controls.addWidget(self.count)
        layout.addLayout(controls)
        if audio_mode:
            audio_filters = QHBoxLayout()
            audio_filters.setSpacing(8)
            audio_filter_label = QLabel("Audio filters")
            audio_filter_label.setObjectName("fieldLabel")
            self.soundtrack_album_button = QPushButton("Soundtrack album")
            self.soundtrack_album_button.setObjectName("secondaryButton")
            self.soundtrack_album_button.setEnabled(True)
            self.soundtrack_album_button.setToolTip('Load a supported APF game first for the soundtrack album.')
            self.soundtrack_album_button.setProperty("disableReason", 'Load a supported APF game first for the soundtrack album.')
            self.soundtrack_album_button.setToolTip(
                "Available when the exact 15-track jukeboxmusic/jukebox22 pair is present."
            )
            self.soundtrack_album_button.clicked.connect(
                self._toggle_soundtrack_album
            )
            self.soundtrack_version = QComboBox()
            self.soundtrack_version.setAccessibleName("Soundtrack audio version")
            self.soundtrack_version.addItem(
                "Stereo masters · jukeboxmusic (15)", "jukeboxmusic"
            )
            self.soundtrack_version.addItem(
                "Mono companions · jukebox22 (15)", "jukebox22"
            )
            self.soundtrack_version.setVisible(False)
            self.soundtrack_version.currentIndexChanged.connect(
                self._soundtrack_version_changed
            )
            self.labeled_only_filter = QCheckBox("Labeled only")
            self.labeled_only_filter.setAccessibleName(
                "Show only APF audio cues with a custom project label or note"
            )
            self.labeled_only_filter.setToolTip(
                "Show only playable sounds you have named or annotated in this project."
            )
            self.labeled_only_filter.setVisible(self._annotation_capable)
            self.labeled_only_filter.setEnabled(False)
            audio_filters.addWidget(audio_filter_label)
            audio_filters.addWidget(self.kind_filter)
            audio_filters.addWidget(self.role_filter)
            audio_filters.addWidget(self.source_filter, 1)
            audio_filters.addWidget(self.labeled_only_filter)
            audio_filters.addWidget(self.soundtrack_album_button)
            audio_filters.addWidget(self.soundtrack_version)
            layout.addLayout(audio_filters)
            self.soundtrack_album_note = QLabel(
                "Track numbers pair the two source-owned banks by substream index and "
                "matching duration. Artist and song title are Unknown; APF 2K8 Mod "
                "Studio does not guess names."
            )
            self.soundtrack_album_note.setObjectName("findingText")
            self.soundtrack_album_note.setWordWrap(True)
            self.soundtrack_album_note.setVisible(False)
            layout.addWidget(self.soundtrack_album_note)

        self.export_complete_audio_catalog_button = QPushButton(
            "Export complete audio catalog…"
        )
        self.export_complete_audio_catalog_button.setObjectName("primaryButton")
        self.export_complete_audio_catalog_button.setVisible(audio_mode)
        self.export_complete_audio_catalog_button.setEnabled(True)
        self.export_complete_audio_catalog_button.setToolTip('Load a supported APF game first, then export the complete audio catalog.')
        self.export_complete_audio_catalog_button.setProperty("disableReason", 'Load a supported APF game first, then export the complete audio catalog.')
        self.export_complete_audio_catalog_button.setAccessibleName(
            "Export complete APF audio catalog"
        )
        self.export_complete_audio_catalog_button.setToolTip(
            "Export every semantic audio row from the loaded game to one new ZIP. "
            "The manifest and searchable catalog.csv account for all 47,814 pinned "
            "rows; successful sounds also receive checksums and an ordered "
            "playlist.m3u8. The 20 AUSB index rows and 19 physical-bank rows are "
            "recorded as unsupported metadata, not cues."
        )
        self.export_complete_audio_catalog_button.clicked.connect(
            self._export_complete_audio_catalog
        )
        self.export_original_audio_banks_button = QPushButton(
            "Export all original banks…"
        )
        self.export_original_audio_banks_button.setObjectName("secondaryButton")
        self.export_original_audio_banks_button.setVisible(audio_mode)
        self.export_original_audio_banks_button.setEnabled(True)
        self.export_original_audio_banks_button.setToolTip('Load a supported APF game first, then export original banks.')
        self.export_original_audio_banks_button.setProperty("disableReason", 'Load a supported APF game first, then export original banks.')
        self.export_original_audio_banks_button.setAccessibleName(
            "Export all original APF external audio banks"
        )
        self.export_original_audio_banks_button.setToolTip(
            "Copy every source-owned physical XMA1 bank—including the two "
            "soundtrack banks—into one private, checksummed ZIP. Raw banks are "
            "multi-cue containers; this does not make them playable or editable."
        )
        self.export_original_audio_banks_button.clicked.connect(
            self._export_all_original_audio_banks
        )
        self.cancel_audio_export_button = QPushButton("Cancel audio export")
        self.cancel_audio_export_button.setObjectName("dangerQuietButton")
        self.cancel_audio_export_button.setVisible(audio_mode)
        self.cancel_audio_export_button.setEnabled(False)
        self.cancel_audio_export_button.setAccessibleName(
            "Cancel the running APF bulk audio export"
        )
        self.cancel_audio_export_button.setToolTip(
            "Stop after the current complete sound or bank. The partial ZIP "
            "manifest will account for every skipped item."
        )
        self.cancel_audio_export_button.clicked.connect(
            self._cancel_running_audio_export
        )
        self.complete_audio_catalog_note = QLabel(
            "Private bulk export • The complete catalog can include all 47,814 "
            "semantic rows in a searchable CSV, with an ordered playlist and per-file "
            "checksums for successful sounds. Its 20 AUSB indexes and 19 physical "
            "banks stay honestly marked as non-cues. Export all original banks copies "
            "those 19 physical containers separately. Neither ZIP enters a shareable project."
        )
        self.complete_audio_catalog_note.setObjectName("findingText")
        self.complete_audio_catalog_note.setWordWrap(True)
        self.complete_audio_catalog_note.setVisible(audio_mode)
        complete_audio_catalog_actions = QHBoxLayout()
        complete_audio_catalog_actions.setSpacing(10)
        complete_audio_catalog_actions.addWidget(
            self.export_complete_audio_catalog_button
        )
        complete_audio_catalog_actions.addWidget(
            self.export_original_audio_banks_button
        )
        complete_audio_catalog_actions.addWidget(self.cancel_audio_export_button)
        complete_audio_catalog_actions.addStretch(1)
        layout.addLayout(complete_audio_catalog_actions)
        layout.addWidget(self.complete_audio_catalog_note)

        self.audio_replacement_pack_format = QComboBox()
        self.audio_replacement_pack_format.addItem("Editable folder", "folder")
        self.audio_replacement_pack_format.addItem("ZIP hand-off", "zip")
        self.audio_replacement_pack_format.setVisible(audio_mode)
        self.audio_replacement_pack_format.setAccessibleName(
            "APF audio replacement pack format"
        )
        self.audio_replacement_pack_format.setToolTip(
            "Folders are easiest to edit. ZIPs are easiest to move or hand off. "
            "Both are retail-free metadata templates."
        )
        self.audio_replacement_pack_format.currentIndexChanged.connect(
            self._update_audio_replacement_pack_actions
        )
        self.audio_replacement_pack_input = QComboBox()
        self.audio_replacement_pack_input.addItem("Pre-encoded XMA1", "xma1")
        self.audio_replacement_pack_input.addItem(
            "Exact PCM16 WAV", "pcm16"
        )
        self.audio_replacement_pack_input.setVisible(audio_mode)
        self.audio_replacement_pack_input.setAccessibleName(
            "APF audio replacement template input format"
        )
        self.audio_replacement_pack_input.setToolTip(
            "Pre-encoded XMA1 is the legacy pack format and needs no configured "
            "encoder. Exact PCM16 WAV is encoded during import with your configured "
            "external XMA1 encoder. Import detects either pack automatically."
        )
        self.audio_replacement_pack_input.currentIndexChanged.connect(
            self._update_audio_replacement_pack_actions
        )
        self.export_audio_replacement_template_button = QPushButton(
            "Create replacement template…"
        )
        self.export_audio_replacement_template_button.setObjectName(
            "secondaryButton"
        )
        self.export_audio_replacement_template_button.setVisible(audio_mode)
        self.export_audio_replacement_template_button.setEnabled(True)
        self.export_audio_replacement_template_button.setToolTip('Load a supported APF game first for replacement templates.')
        self.export_audio_replacement_template_button.setProperty("disableReason", 'Load a supported APF game first for replacement templates.')
        self.export_audio_replacement_template_button.setAccessibleName(
            "Create APF audio replacement template"
        )
        self.export_audio_replacement_template_button.setToolTip(
            "Create a metadata-only folder or ZIP for every playable sound matching "
            "the current filters, or the exact shortlist while reviewing it. The pack "
            "contains no original audio or source-owned sound names."
        )
        self.export_audio_replacement_template_button.clicked.connect(
            self._export_audio_replacement_template
        )
        self.import_audio_replacement_pack_button = QPushButton(
            "Review replacement pack…"
        )
        self.import_audio_replacement_pack_button.setObjectName("primaryButton")
        self.import_audio_replacement_pack_button.setVisible(audio_mode)
        self.import_audio_replacement_pack_button.setEnabled(True)
        self.import_audio_replacement_pack_button.setToolTip('Load a supported APF game first for replacement packs.')
        self.import_audio_replacement_pack_button.setProperty("disableReason", 'Load a supported APF game first for replacement packs.')
        self.import_audio_replacement_pack_button.setAccessibleName(
            "Review APF audio replacement pack before applying it"
        )
        self.import_audio_replacement_pack_button.setToolTip(
            "Auto-detect a legacy XMA1 or exact PCM16 WAV pack, validate its complete "
            "manifest, source binding, slot shape, payloads, decode, and alias rules, "
            "then show exact would-change counts. Nothing is staged unless you "
            "explicitly choose Apply. PCM16 packs use your configured external encoder."
        )
        self.import_audio_replacement_pack_button.clicked.connect(
            self._import_audio_replacement_pack
        )
        self.cancel_audio_import_button = QPushButton(
            "Cancel pack check"
        )
        self.cancel_audio_import_button.setObjectName("dangerQuietButton")
        self.cancel_audio_import_button.setVisible(audio_mode)
        self.cancel_audio_import_button.setEnabled(False)
        self.cancel_audio_import_button.setAccessibleName(
            "Cancel the running APF audio replacement preview or apply"
        )
        self.cancel_audio_import_button.setToolTip(
            "Stop at a safe file boundary or interrupt a running user-supplied "
            "encoder. The import remains atomic: cancellation changes no project "
            "edit and adds no Undo action."
        )
        self.cancel_audio_import_button.clicked.connect(
            self._cancel_running_audio_import
        )
        replacement_pack_actions = QHBoxLayout()
        replacement_pack_actions.setSpacing(10)
        replacement_pack_actions.addWidget(self.audio_replacement_pack_input)
        replacement_pack_actions.addWidget(self.audio_replacement_pack_format)
        replacement_pack_actions.addWidget(
            self.export_audio_replacement_template_button
        )
        replacement_pack_actions.addWidget(self.import_audio_replacement_pack_button)
        replacement_pack_actions.addWidget(self.cancel_audio_import_button)
        replacement_pack_actions.addStretch(1)
        layout.addLayout(replacement_pack_actions)
        self.audio_replacement_pack_note = QLabel(
            "Batch replacement packs • Choose pre-encoded XMA1, or exact PCM16 WAV "
            "that the app will encode with your configured external XMA1 encoder. "
            "Review auto-detects both generations; legacy XMA1 packs need no encoder. "
            "FLAC and MP3 cannot be imported directly—convert them to an exact PCM16 "
            "WAV first. Missing files are skipped; unknown, conflicting, invalid, or "
            "unchanged-only packs never reach Apply. A fully validated count preview "
            "appears first, and Cancel changes nothing. Use "
            "only audio you created or have permission to modify and share; automated "
            "source-reuse checks are safety checks, not copyright clearance."
        )
        self.audio_replacement_pack_note.setObjectName("findingText")
        self.audio_replacement_pack_note.setWordWrap(True)
        self.audio_replacement_pack_note.setVisible(audio_mode)
        layout.addWidget(self.audio_replacement_pack_note)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.table = QTableWidget(
            0,
            6 if audio_mode else (4 if text_mode or roster_mode else 3),
        )
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(
            ("Sound", "Role", "Format", "Length", "Location", "Status")
            if audio_mode
            else ("Text", "Kind", "Context", "Status")
            if text_mode
            else ("Roster record", "Kind", "Context", "Roster status")
            if roster_mode
            else ("Decoded record", "Kind", "Context")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        if audio_mode:
            self.table.horizontalHeader().setSectionResizeMode(
                0, self.table.horizontalHeader().Stretch
            )
            for column in range(1, 5):
                self.table.horizontalHeader().setSectionResizeMode(
                    column, self.table.horizontalHeader().ResizeToContents
                )
            self.table.horizontalHeader().setSectionResizeMode(
                5, self.table.horizontalHeader().Stretch
            )
        elif text_mode or roster_mode:
            self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().Stretch)
            self.table.horizontalHeader().setSectionResizeMode(3, self.table.horizontalHeader().ResizeToContents)
        else:
            self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, self.table.horizontalHeader().Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        splitter.addWidget(self.table)
        detail = QFrame()
        detail.setObjectName("inspectorDetail")
        detail.setMinimumWidth(
            410 if roster_mode else 390 if text_mode else 370 if audio_mode else 330
        )
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(12, 10, 12, 10)
        self.detail_title = QLabel("Choose a decoded row")
        self.detail_title.setObjectName("panelTitle")
        self.detail_title.setTextFormat(Qt.PlainText)
        self.detail_subtitle = QLabel("")
        self.detail_subtitle.setObjectName("mutedLabel")
        self.detail_subtitle.setWordWrap(True)
        self.detail_subtitle.setTextFormat(Qt.PlainText)
        self.annotation_card = QFrame()
        self.annotation_card.setObjectName("audioAnnotationCard")
        self.annotation_card.setVisible(audio_mode and self._annotation_capable)
        annotation_layout = QVBoxLayout(self.annotation_card)
        annotation_layout.setContentsMargins(12, 10, 12, 10)
        annotation_layout.setSpacing(7)
        self.annotation_heading = QLabel("Your cue label & notes")
        self.annotation_heading.setObjectName("fieldLabel")
        self.annotation_help = QLabel(
            "Project metadata only — searchable and shareable, but never written "
            "into APF or counted as a build edit."
        )
        self.annotation_help.setObjectName("mutedLabel")
        self.annotation_help.setWordWrap(True)
        self.annotation_help.setTextFormat(Qt.PlainText)
        self.annotation_title_edit = QLineEdit()
        self.annotation_title_edit.setMaxLength(
            AUDIO_ANNOTATION_MAX_TITLE_CHARS
        )
        self.annotation_title_edit.setPlaceholderText(
            "Custom title, song name, call, crowd cue…"
        )
        self.annotation_title_edit.setAccessibleName(
            "Custom title for the selected APF audio cue"
        )
        self.annotation_title_count = QLabel(
            f"0 / {AUDIO_ANNOTATION_MAX_TITLE_CHARS:,}"
        )
        self.annotation_title_count.setObjectName("mutedLabel")
        self.annotation_title_count.setAlignment(Qt.AlignRight)
        self.annotation_note_edit = QPlainTextEdit()
        self.annotation_note_edit.setPlaceholderText(
            "What you heard, where it plays, replacement idea, or research note…"
        )
        self.annotation_note_edit.setMaximumHeight(104)
        self.annotation_note_edit.setAccessibleName(
            "Notes for the selected APF audio cue"
        )
        self.annotation_note_count = QLabel(
            f"0 / {AUDIO_ANNOTATION_MAX_NOTE_CHARS:,}"
        )
        self.annotation_note_count.setObjectName("mutedLabel")
        self.annotation_note_count.setAlignment(Qt.AlignRight)
        annotation_actions = QHBoxLayout()
        annotation_actions.setSpacing(7)
        self.save_annotation_button = QPushButton("Save label")
        self.save_annotation_button.setObjectName("primaryButton")
        self.save_annotation_button.setAccessibleName(
            "Save the custom title and notes for this APF audio cue"
        )
        self.clear_annotation_button = QPushButton("Clear")
        self.clear_annotation_button.setObjectName("dangerQuietButton")
        self.clear_annotation_button.setAccessibleName(
            "Clear the custom title and notes for this APF audio cue"
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
        self.base_ratings_panel = BaseRatingsPanel(self.facade)
        self.base_ratings_panel.applyRequested.connect(
            self._apply_player_base_rating
        )
        self.base_ratings_panel.revertRequested.connect(
            self._revert_player_base_rating
        )
        self.player_position_panel = PlayerPositionPanel(self.facade)
        self.player_position_panel.applyRequested.connect(
            self._apply_player_position
        )
        self.player_position_panel.revertRequested.connect(
            self._revert_player_position
        )
        self.detail_fields = QPlainTextEdit()
        self.detail_fields.setObjectName("decodedFields")
        self.detail_fields.setReadOnly(True)
        self.detail_fields.setLineWrapMode(QPlainTextEdit.NoWrap)
        if audio_mode:
            # Keep the technical identity useful at ordinary laptop heights.
            # Without a floor, the audio action stack can squeeze this editor
            # down to a single visible brace.
            self.detail_fields.setMinimumHeight(72)
        if text_mode or roster_mode:
            # Text and roster authors need room for the live value, allocation
            # warning, and actions. The decoded JSON remains available through
            # row export; repeating it here crowds the real editor at ordinary
            # laptop heights.
            self.detail_fields.setVisible(False)
        self.waveform_heading = QLabel("Waveform preview")
        self.waveform_heading.setObjectName("fieldLabel")
        self.waveform_heading.setVisible(audio_mode)
        self.waveform_preview = AudioWaveformPreview()
        self.waveform_preview.setVisible(audio_mode)
        self.load_waveform_button = QPushButton("Load waveform")
        self.load_waveform_button.setObjectName("secondaryButton")
        self.load_waveform_button.setVisible(audio_mode)
        # Never silent-gray at construction.
        _wf_boot = (
            "Load a supported APF game and select a playable sound first. "
            "Load waveform stays clickable so walls explain themselves."
        )
        self.load_waveform_button.setEnabled(True)
        self.load_waveform_button.setToolTip(_wf_boot)
        self.load_waveform_button.setProperty("disableReason", _wf_boot)
        self.load_waveform_button.clicked.connect(self._load_audio_waveform)
        self.export_audio_button = QPushButton("Export this sound…")
        self.export_audio_button.setObjectName("primaryButton")
        self.export_audio_button.setVisible(False)
        self.export_audio_button.setToolTip(
            "Save original XMA1, or publish WAV only after full decoder verification."
        )
        self.export_audio_button.clicked.connect(self._export_audio)
        self.play_audio_button = QPushButton("Play")
        self.play_audio_button.setObjectName("secondaryButton")
        self.play_audio_button.setVisible(audio_mode)
        _play_boot = "Load a supported APF game and select a playable sound first."
        self.play_audio_button.setEnabled(True)
        self.play_audio_button.setToolTip(_play_boot)
        self.play_audio_button.setProperty("disableReason", _play_boot)
        self.play_audio_button.setToolTip(
            "Decode a session-private, verified WAV and play it with ffplay, paplay, or aplay."
        )
        self.play_audio_button.clicked.connect(self._play_or_stop_audio)
        self.export_bank_button = QPushButton("Export complete bank…")
        self.export_bank_button.setObjectName("secondaryButton")
        self.export_bank_button.setVisible(False)
        self.export_bank_button.setToolTip(
            "Export every sound in this bounded bank as one all-or-nothing ZIP."
        )
        self.export_bank_button.clicked.connect(self._export_audio_bank)
        self.export_external_bank_button = QPushButton("Export original bank .bin…")
        self.export_external_bank_button.setObjectName("secondaryButton")
        self.export_external_bank_button.setVisible(False)
        self.export_external_bank_button.setEnabled(True)
        self.export_external_bank_button.setToolTip('Select an external bank row first.')
        self.export_external_bank_button.setProperty("disableReason", 'Select an external bank row first.')
        self.export_external_bank_button.setToolTip(
            "Copy this exact physical multi-cue XMA1 packet bank. It is not one playable sound."
        )
        self.export_external_bank_button.clicked.connect(
            self._export_external_audio_bank
        )
        self.export_matching_button = QPushButton("Export matching sounds…")
        self.export_matching_button.setObjectName("secondaryButton")
        self.export_matching_button.setVisible(audio_mode)
        self.export_matching_button.setEnabled(True)
        self.export_matching_button.setToolTip('Load a supported APF game first, then export matching sounds.')
        self.export_matching_button.setProperty("disableReason", 'Load a supported APF game first, then export matching sounds.')
        self.export_matching_button.setToolTip(
            "Narrow search, kind, role, and source to 1–256 playable sounds."
        )
        self.export_matching_button.clicked.connect(self._export_matching_audio)
        self.audio_authoring_heading = QLabel("Replace this sound")
        self.audio_authoring_heading.setObjectName("fieldLabel")
        self.audio_authoring_heading.setVisible(audio_mode)
        self.audio_replacement_drop_zone = AudioReplacementDropZone()
        self.audio_replacement_drop_zone.setVisible(audio_mode)
        self.audio_replacement_drop_zone.audioDropped.connect(
            self._replace_audio_drop
        )
        self.export_pcm_template_button = QPushButton(
            "Export PCM authoring template…"
        )
        self.export_pcm_template_button.setObjectName("secondaryButton")
        self.export_pcm_template_button.setVisible(audio_mode)
        self.export_pcm_template_button.setEnabled(True)
        self.export_pcm_template_button.setToolTip('Choose a playable sound first, then export its exact PCM template.')
        self.export_pcm_template_button.setProperty("disableReason", 'Choose a playable sound first, then export its exact PCM template.')
        self.export_pcm_template_button.setAccessibleName(
            "Export exact PCM authoring template for this APF sound"
        )
        self.export_pcm_template_button.setToolTip(
            "Export a retail-free, exact-length PCM16 silence WAV. Paint it with "
            "your sound editor, then return it with Replace from audio."
        )
        self.export_pcm_template_button.clicked.connect(
            self._export_audio_pcm_template
        )
        self.replace_pcm_audio_button = QPushButton("Replace from audio…")
        self.replace_pcm_audio_button.setObjectName("primaryButton")
        self.replace_pcm_audio_button.setVisible(audio_mode)
        self.replace_pcm_audio_button.setEnabled(True)
        self.replace_pcm_audio_button.setToolTip('Choose a playable sound first, then replace from ordinary audio.')
        self.replace_pcm_audio_button.setProperty("disableReason", 'Choose a playable sound first, then replace from ordinary audio.')
        self.replace_pcm_audio_button.setAccessibleName(
            "Replace this APF sound from an ordinary audio file"
        )
        self.replace_pcm_audio_button.setToolTip(
            "Convert WAV, MP3, FLAC, OGG, M4A or another supported audio file to "
            "this slot's exact PCM shape, encode it with your configured external "
            "XMA1 encoder, then stage it only after every exact-slot gate passes."
        )
        self.replace_pcm_audio_button.clicked.connect(
            self._replace_audio_from_pcm
        )
        self.cancel_pcm_encoding_button = QPushButton("Cancel PCM encoding")
        self.cancel_pcm_encoding_button.setObjectName("dangerQuietButton")
        self.cancel_pcm_encoding_button.setVisible(False)
        self.cancel_pcm_encoding_button.setEnabled(False)
        self.cancel_pcm_encoding_button.setAccessibleName(
            "Cancel the running PCM to XMA1 encoding operation"
        )
        self.cancel_pcm_encoding_button.setToolTip(
            "Stop the user-supplied encoder and discard its temporary output. "
            "Cancellation stages no project edit."
        )
        self.cancel_pcm_encoding_button.clicked.connect(
            self._cancel_running_pcm_encoding
        )
        self.configure_audio_encoder_button = QPushButton(
            "Configure XMA1 encoder…"
        )
        self.configure_audio_encoder_button.setObjectName("secondaryButton")
        self.configure_audio_encoder_button.setVisible(audio_mode)
        self.configure_audio_encoder_button.setEnabled(audio_mode)
        self.configure_audio_encoder_button.setAccessibleName(
            "Configure a user-supplied external XMA1 encoder"
        )
        self.configure_audio_encoder_button.setToolTip(
            "Choose an encoder already installed on this PC. Windows .exe tools "
            "can run through Wine. No encoder ships with Mod Studio, and its path "
            "is never saved in a mod project."
        )
        self.configure_audio_encoder_button.clicked.connect(
            self._configure_external_xma1_encoder
        )
        self.audio_encoder_status = QLabel("")
        self.audio_encoder_status.setObjectName("mutedLabel")
        self.audio_encoder_status.setWordWrap(True)
        self.audio_encoder_status.setVisible(audio_mode)
        self.audio_encoder_status.setAccessibleName(
            "External XMA1 encoder configuration status"
        )
        self.replace_audio_button = QPushButton("Replace with XMA1…")
        self.replace_audio_button.setObjectName("primaryButton")
        self.replace_audio_button.setVisible(audio_mode)
        self.replace_audio_button.setEnabled(True)
        self.replace_audio_button.setToolTip('Choose a playable sound first, then Replace with XMA1.')
        self.replace_audio_button.setProperty("disableReason", 'Choose a playable sound first, then Replace with XMA1.')
        self.replace_audio_button.setToolTip(
            "Choose a pre-encoded RIFF XMA1 file. It must exactly match the selected "
            "sound's channels, sample rate, encoded byte length, packet "
            "shape, and decoded duration. This remains the advanced bypass when you "
            "already have final XMA1."
        )
        self.replace_audio_button.clicked.connect(self._replace_audio)
        self.revert_audio_button = QPushButton("Revert sound")
        self.revert_audio_button.setObjectName("dangerQuietButton")
        self.revert_audio_button.setVisible(audio_mode)
        self.revert_audio_button.setEnabled(True)
        self.revert_audio_button.setToolTip('Choose a modified playable sound first to revert.')
        self.revert_audio_button.setProperty("disableReason", 'Choose a modified playable sound first to revert.')
        self.revert_audio_button.clicked.connect(self._revert_audio)
        self.audio_replace_note = QLabel(
            "PCM authoring bridge • Export an exact silence template, edit that WAV, "
            "and encode it with a tool you supply. No encoder ships with Mod Studio. "
            "Whether you start from WAV or pre-encoded XMA1, the final output must "
            "pass every exact-slot gate before the project changes."
        )
        self.audio_replace_note.setObjectName("findingText")
        self.audio_replace_note.setWordWrap(True)
        self.audio_replace_note.setVisible(audio_mode)
        self.shortlist_heading = QLabel("Audio shortlist")
        self.shortlist_heading.setObjectName("fieldLabel")
        self.shortlist_heading.setVisible(audio_mode)
        self.shortlist_hint = QLabel(
            "Collect sounds across searches, pages, and banks, then export one private bundle. "
            "The shortlist clears when the loaded game changes."
        )
        self.shortlist_hint.setObjectName("mutedLabel")
        self.shortlist_hint.setWordWrap(True)
        self.shortlist_hint.setVisible(audio_mode)
        # Never silent-gray shortlist actions at construction.
        _sl_boot = (
            "Load a supported APF game and select playable sounds first. "
            "Shortlist actions stay clickable so walls explain themselves."
        )
        self.shortlist_toggle_button = QPushButton("Add selected sound")
        self.shortlist_toggle_button.setObjectName("secondaryButton")
        self.shortlist_toggle_button.setVisible(audio_mode)
        self.shortlist_toggle_button.setEnabled(True)
        self.shortlist_toggle_button.setToolTip(_sl_boot)
        self.shortlist_toggle_button.setProperty("disableReason", _sl_boot)
        self.shortlist_toggle_button.clicked.connect(self._toggle_audio_shortlist)
        self.shortlist_page_button = QPushButton("Add this page")
        self.shortlist_page_button.setObjectName("secondaryButton")
        self.shortlist_page_button.setVisible(audio_mode)
        self.shortlist_page_button.setEnabled(True)
        self.shortlist_page_button.setToolTip(_sl_boot)
        self.shortlist_page_button.setProperty("disableReason", _sl_boot)
        self.shortlist_page_button.clicked.connect(self._add_visible_audio_to_shortlist)
        self.shortlist_matching_button = QPushButton("Add all matching")
        self.shortlist_matching_button.setObjectName("secondaryButton")
        self.shortlist_matching_button.setVisible(audio_mode)
        self.shortlist_matching_button.setEnabled(True)
        self.shortlist_matching_button.setAccessibleName(
            "Add every matching playable sound to the audio shortlist"
        )
        self.shortlist_matching_button.setAccessibleDescription(
            "Adds every playable sound matching the applied search and filters, "
            "in game catalog order. Sounds already selected are kept once."
        )
        self.shortlist_matching_button.setToolTip(_sl_boot)
        self.shortlist_matching_button.setProperty("disableReason", _sl_boot)
        self.shortlist_matching_button.clicked.connect(
            self._add_matching_audio_to_shortlist
        )
        self.shortlist_clear_button = QPushButton("Clear")
        self.shortlist_clear_button.setObjectName("dangerQuietButton")
        self.shortlist_clear_button.setAccessibleName("Clear audio shortlist")
        self.shortlist_clear_button.setVisible(audio_mode)
        self.shortlist_clear_button.setEnabled(True)
        self.shortlist_clear_button.setToolTip(_sl_boot)
        self.shortlist_clear_button.setProperty("disableReason", _sl_boot)
        self.shortlist_clear_button.clicked.connect(self._clear_audio_shortlist)
        self.shortlist_count = QLabel("Selected 0 / 256")
        self.shortlist_count.setObjectName("countPill")
        self.shortlist_count.setVisible(audio_mode)
        self.shortlist_review_button = QPushButton("Review selected")
        self.shortlist_review_button.setObjectName("secondaryButton")
        self.shortlist_review_button.setVisible(audio_mode)
        self.shortlist_review_button.setEnabled(True)
        self.shortlist_review_button.setToolTip(_sl_boot)
        self.shortlist_review_button.setProperty("disableReason", _sl_boot)
        self.shortlist_review_button.clicked.connect(self._toggle_audio_review)
        self.shortlist_move_up_button = QPushButton("Move up")
        self.shortlist_move_up_button.setObjectName("secondaryButton")
        self.shortlist_move_up_button.setVisible(audio_mode)
        self.shortlist_move_up_button.setEnabled(True)
        self.shortlist_move_up_button.setToolTip(_sl_boot)
        self.shortlist_move_up_button.setProperty("disableReason", _sl_boot)
        self.shortlist_move_up_button.clicked.connect(
            lambda: self._move_shortlisted_audio(-1)
        )
        self.shortlist_move_down_button = QPushButton("Move down")
        self.shortlist_move_down_button.setObjectName("secondaryButton")
        self.shortlist_move_down_button.setVisible(audio_mode)
        self.shortlist_move_down_button.setEnabled(True)
        self.shortlist_move_down_button.setToolTip(_sl_boot)
        self.shortlist_move_down_button.setProperty("disableReason", _sl_boot)
        self.shortlist_move_down_button.clicked.connect(
            lambda: self._move_shortlisted_audio(1)
        )
        self.export_shortlist_button = QPushButton("Export selected sounds…")
        self.export_shortlist_button.setObjectName("primaryButton")
        self.export_shortlist_button.setVisible(audio_mode)
        self.export_shortlist_button.setEnabled(True)
        self.export_shortlist_button.setToolTip(
            "Add up to 256 sounds from any search, page, or bank first."
        )
        self.export_shortlist_button.setProperty(
            "disableReason",
            "Add up to 256 sounds from any search, page, or bank first.",
        )
        self.export_shortlist_button.clicked.connect(self._export_shortlisted_audio)
        audio_actions = QHBoxLayout()
        audio_actions.setSpacing(7)
        audio_actions.addWidget(self.play_audio_button)
        audio_actions.addWidget(self.export_audio_button)
        audio_actions.addWidget(self.export_bank_button)
        audio_actions.addWidget(self.export_external_bank_button)
        pcm_audio_actions = QHBoxLayout()
        pcm_audio_actions.setSpacing(7)
        pcm_audio_actions.addWidget(self.export_pcm_template_button, 1)
        pcm_audio_actions.addWidget(self.replace_pcm_audio_button, 1)
        pcm_audio_actions.addWidget(self.cancel_pcm_encoding_button)
        audio_config_actions = QHBoxLayout()
        audio_config_actions.setSpacing(7)
        audio_config_actions.addWidget(self.configure_audio_encoder_button)
        audio_config_actions.addStretch(1)
        audio_edit_actions = QHBoxLayout()
        audio_edit_actions.setSpacing(7)
        audio_edit_actions.addWidget(self.replace_audio_button, 1)
        audio_edit_actions.addWidget(self.revert_audio_button)
        shortlist_actions = QHBoxLayout()
        shortlist_actions.setSpacing(7)
        shortlist_actions.addWidget(self.shortlist_toggle_button, 1)
        shortlist_actions.addWidget(self.shortlist_page_button, 1)
        shortlist_status = QHBoxLayout()
        shortlist_status.setSpacing(7)
        shortlist_status.addWidget(self.shortlist_clear_button)
        shortlist_status.addStretch(1)
        shortlist_status.addWidget(self.shortlist_count)
        shortlist_review_actions = QHBoxLayout()
        shortlist_review_actions.setSpacing(7)
        shortlist_review_actions.addWidget(self.shortlist_review_button, 1)
        shortlist_review_actions.addWidget(self.shortlist_move_up_button)
        shortlist_review_actions.addWidget(self.shortlist_move_down_button)
        self.text_editor_label = QLabel("Replacement text")
        self.text_editor_label.setObjectName("fieldLabel")
        self.text_editor = QPlainTextEdit()
        self.text_editor.setObjectName("textReplacementEditor")
        self.text_editor.setPlaceholderText(
            "Select an underlying pool allocation to edit it."
        )
        self.text_editor.setFixedHeight(68 if text_mode else 52)
        self.text_editor.setVisible(text_mode)
        self.text_editor_label.setVisible(text_mode)
        self.text_limit = QLabel("")
        self.text_limit.setObjectName("mutedLabel")
        self.text_limit.setWordWrap(True)
        self.text_limit.setVisible(text_mode)
        self.apply_text_button = QPushButton("Apply Text")
        self.apply_text_button.setObjectName("primaryButton")
        self.apply_text_button.setVisible(text_mode)
        _text_boot = (
            "Select an editable string allocation first. Apply/Revert stay clickable."
        )
        self.apply_text_button.setEnabled(True)
        self.apply_text_button.setToolTip(_text_boot)
        self.apply_text_button.setProperty("disableReason", _text_boot)
        self.revert_text_button = QPushButton("Revert Text")
        self.revert_text_button.setObjectName("dangerQuietButton")
        self.revert_text_button.setVisible(text_mode)
        self.revert_text_button.setEnabled(True)
        self.revert_text_button.setToolTip(_text_boot)
        self.revert_text_button.setProperty("disableReason", _text_boot)
        self.export_text_sheet_button = QPushButton("Export Text Sheet…")
        self.export_text_sheet_button.setObjectName("secondaryButton")
        self.export_text_sheet_button.setVisible(text_mode)
        # Never silent-gray: stay clickable; disableReason teaches Load game.
        _sheet_boot = (
            "Load a supported APF game first, then Export/Import Text Sheet."
        )
        self.export_text_sheet_button.setEnabled(True)
        self.export_text_sheet_button.setToolTip(_sheet_boot)
        self.export_text_sheet_button.setProperty("disableReason", _sheet_boot)
        self.import_text_sheet_button = QPushButton("Import Text Sheet…")
        self.import_text_sheet_button.setObjectName("secondaryButton")
        self.import_text_sheet_button.setVisible(text_mode)
        self.import_text_sheet_button.setEnabled(True)
        self.import_text_sheet_button.setToolTip(_sheet_boot)
        self.import_text_sheet_button.setProperty("disableReason", _sheet_boot)
        self.apply_text_button.clicked.connect(self._apply_text)
        self.revert_text_button.clicked.connect(self._revert_text)
        self.export_text_sheet_button.clicked.connect(self._export_text_sheet)
        self.import_text_sheet_button.clicked.connect(self._import_text_sheet)
        self.text_editor.textChanged.connect(self._text_editor_changed)
        text_actions = QHBoxLayout()
        text_actions.setSpacing(7)
        text_actions.addWidget(self.apply_text_button)
        text_actions.addWidget(self.revert_text_button)
        text_actions.addStretch(1)
        text_sheet_actions = QHBoxLayout()
        text_sheet_actions.setSpacing(7)
        text_sheet_actions.addWidget(self.export_text_sheet_button, 1)
        text_sheet_actions.addWidget(self.import_text_sheet_button, 1)
        self.roster_editor_label = QLabel("Roster identity field")
        self.roster_editor_label.setObjectName("fieldLabel")
        self.roster_editor_label.setVisible(roster_mode)
        self.roster_field_combo = QComboBox()
        self.roster_field_combo.setAccessibleName("Roster identity field")
        self.roster_field_combo.setVisible(roster_mode)
        self.roster_field_combo.setEnabled(False)
        self.roster_name_editor = QLineEdit()
        self.roster_name_editor.setObjectName("rosterNameEditor")
        self.roster_name_editor.setPlaceholderText(
            "Choose a player or team identity field to inspect its exact allocation."
        )
        self.roster_name_editor.setVisible(roster_mode)
        self.roster_name_editor.setEnabled(False)
        self.roster_allocation_note = QLabel("")
        self.roster_allocation_note.setObjectName("mutedLabel")
        self.roster_allocation_note.setWordWrap(True)
        self.roster_allocation_note.setVisible(roster_mode)
        self.roster_boundary_note = QLabel(ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE)
        self.roster_boundary_note.setObjectName("findingText")
        self.roster_boundary_note.setWordWrap(True)
        self.roster_boundary_note.setVisible(False)
        self.roster_aliases_button = QPushButton("View affected fields…")
        self.roster_aliases_button.setObjectName("secondaryButton")
        self.roster_aliases_button.setVisible(roster_mode)
        self.roster_aliases_button.setEnabled(True)
        self.roster_aliases_button.setToolTip('Select a roster identity field first.')
        self.roster_aliases_button.setProperty("disableReason", 'Select a roster identity field first.')
        self.roster_aliases_button.setAccessibleName(
            "Review every roster field affected by this shared name allocation"
        )
        self.roster_aliases_button.clicked.connect(
            self._show_roster_alias_owners
        )
        self.apply_roster_name_button = QPushButton("Replace Name")
        self.apply_roster_name_button.setObjectName("primaryButton")
        self.apply_roster_name_button.setVisible(roster_mode)
        _roster_boot = (
            "Select a roster identity field first. Replace/Revert stay clickable."
        )
        self.apply_roster_name_button.setEnabled(True)
        self.apply_roster_name_button.setToolTip(_roster_boot)
        self.apply_roster_name_button.setProperty("disableReason", _roster_boot)
        if roster_mode and not roster_writes_enabled:
            self.apply_roster_name_button.setToolTip(
                ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
        self.revert_roster_name_button = QPushButton("Revert Name")
        self.revert_roster_name_button.setObjectName("dangerQuietButton")
        self.revert_roster_name_button.setVisible(roster_mode)
        self.revert_roster_name_button.setEnabled(True)
        self.revert_roster_name_button.setToolTip(_roster_boot)
        self.revert_roster_name_button.setProperty("disableReason", _roster_boot)
        self.roster_field_combo.currentIndexChanged.connect(
            self._roster_field_changed
        )
        self.roster_name_editor.textChanged.connect(
            self._roster_editor_changed
        )
        self.apply_roster_name_button.clicked.connect(
            self._apply_roster_identity
        )
        self.revert_roster_name_button.clicked.connect(
            self._revert_roster_identity
        )
        roster_actions = QHBoxLayout()
        roster_actions.setSpacing(7)
        roster_actions.addWidget(self.apply_roster_name_button)
        roster_actions.addWidget(self.revert_roster_name_button)
        roster_actions.addWidget(self.roster_aliases_button)
        roster_actions.addStretch(1)
        detail_box.addWidget(self.detail_title)
        detail_box.addWidget(self.detail_subtitle)
        detail_box.addWidget(self.annotation_card)
        if roster_mode:
            self.roster_detail_tabs = QTabWidget()
            self.roster_detail_tabs.setObjectName("rosterEditorTabs")
            self.roster_detail_tabs.setAccessibleName(
                "Roster identity names, base ratings, and player position editors"
            )
            roster_identity_page = QWidget()
            roster_identity_layout = QVBoxLayout(roster_identity_page)
            roster_identity_layout.setContentsMargins(8, 8, 8, 8)
            roster_identity_layout.setSpacing(7)
            roster_identity_layout.addWidget(self.roster_editor_label)
            roster_identity_layout.addWidget(self.roster_field_combo)
            roster_identity_layout.addWidget(self.roster_name_editor)
            # The complete edit workflow must stay above the explanatory copy.
            # Long shared-allocation disclosures can scroll below without ever
            # hiding Replace, Revert, or the exact affected-fields review.
            roster_identity_layout.addLayout(roster_actions)
            roster_identity_layout.addWidget(self.roster_allocation_note)
            roster_identity_layout.addWidget(self.roster_boundary_note)
            roster_identity_layout.addStretch(1)
            roster_ratings_page = QWidget()
            roster_ratings_layout = QVBoxLayout(roster_ratings_page)
            roster_ratings_layout.setContentsMargins(8, 8, 8, 8)
            roster_ratings_layout.addWidget(self.base_ratings_panel)
            roster_ratings_layout.addStretch(1)
            roster_position_page = QWidget()
            roster_position_layout = QVBoxLayout(roster_position_page)
            roster_position_layout.setContentsMargins(8, 8, 8, 8)
            roster_position_layout.addWidget(self.player_position_panel)
            roster_position_layout.addStretch(1)
            self.roster_detail_tabs.addTab(
                roster_identity_page, "Identity & Names"
            )
            self.roster_detail_tabs.addTab(
                roster_ratings_page, "Base Ratings (31)"
            )
            self.roster_detail_tabs.addTab(
                roster_position_page, "Position (17)"
            )
            self.roster_detail_tabs.setTabEnabled(1, False)
            self.roster_detail_tabs.setTabEnabled(2, False)
            detail_box.addWidget(self.roster_detail_tabs, 1)
        else:
            self.roster_detail_tabs = None
            detail_box.addWidget(self.base_ratings_panel)
            detail_box.addWidget(self.player_position_panel)
        # Put the core audio actions before the technical JSON and optional
        # waveform/shortlist workspaces. Replace/Revert must be discoverable
        # without scrolling at ordinary laptop heights.
        detail_box.addLayout(audio_actions)
        detail_box.addWidget(self.audio_authoring_heading)
        detail_box.addWidget(self.audio_replacement_drop_zone)
        detail_box.addLayout(pcm_audio_actions)
        detail_box.addLayout(audio_config_actions)
        detail_box.addWidget(self.audio_encoder_status)
        detail_box.addLayout(audio_edit_actions)
        detail_box.addWidget(self.audio_replace_note)
        detail_box.addWidget(self.detail_fields, 1)
        detail_box.addWidget(self.waveform_heading)
        detail_box.addWidget(self.waveform_preview)
        detail_box.addWidget(self.load_waveform_button)
        detail_box.addWidget(self.text_editor_label)
        detail_box.addWidget(self.text_editor)
        detail_box.addWidget(self.text_limit)
        detail_box.addLayout(text_actions)
        detail_box.addLayout(text_sheet_actions)
        if not roster_mode:
            detail_box.addWidget(self.roster_editor_label)
            detail_box.addWidget(self.roster_field_combo)
            detail_box.addWidget(self.roster_name_editor)
            detail_box.addWidget(self.roster_allocation_note)
            detail_box.addWidget(self.roster_boundary_note)
            detail_box.addLayout(roster_actions)
        detail_box.addWidget(self.shortlist_heading)
        detail_box.addWidget(self.shortlist_hint)
        detail_box.addLayout(shortlist_review_actions)
        detail_box.addLayout(shortlist_actions)
        # This action owns a full-width row so its live count remains legible
        # in the 390 px audio detail pane instead of squeezing three buttons
        # into the selected/page action row.
        detail_box.addWidget(self.shortlist_matching_button)
        detail_box.addLayout(shortlist_status)
        detail_box.addWidget(self.export_shortlist_button)
        detail_box.addWidget(self.export_matching_button)
        if audio_mode or roster_mode:
            # Audio and roster/player details both contain purposeful vertical
            # workspaces. At ordinary laptop heights those controls scroll
            # instead of being compressed, clipped, or painted over the table.
            # Roster identity and ratings are separate tabs, so neither nested
            # editor has to be scrolled through to discover the other.
            minimum_detail_height = 600 if roster_mode else 620
            detail.setMinimumHeight(minimum_detail_height)
            self.detail_scroll = QScrollArea()
            self.detail_scroll.setObjectName(
                "rosterDetailScroll" if roster_mode else "audioDetailScroll"
            )
            self.detail_scroll.setWidgetResizable(True)
            self.detail_scroll.setFrameShape(QFrame.NoFrame)
            self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.detail_scroll.setMinimumWidth(430 if roster_mode else 390)
            self.detail_scroll.setWidget(detail)
            splitter.addWidget(self.detail_scroll)
        else:
            self.detail_scroll = None
            splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        footer = QHBoxLayout()
        self.findings = QLabel("Decoded models never modify the selected source game.")
        self.findings.setObjectName("findingText")
        self.findings.setWordWrap(True)
        self.previous = QPushButton("← Previous")
        self.next = QPushButton("Next →")
        self.page = QLabel("Page 0 of 0")
        self.page.setObjectName("mutedLabel")
        self.previous.clicked.connect(lambda: self._move(-PAGE_SIZE))
        self.next.clicked.connect(lambda: self._move(PAGE_SIZE))
        footer.addWidget(self.findings, 1)
        footer.addWidget(self.previous)
        footer.addWidget(self.page)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        layout.addSpacing(4)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _text: self._restart_filter())
        self.kind_filter.currentIndexChanged.connect(lambda _index: self._restart_filter())
        self.role_filter.currentIndexChanged.connect(lambda _index: self._restart_filter())
        self.source_filter.currentIndexChanged.connect(lambda _index: self._restart_filter())
        if audio_mode:
            self.labeled_only_filter.toggled.connect(
                lambda _checked: self._restart_filter()
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
        self.kind_shortcut = QShortcut(QKeySequence("Ctrl+Shift+K"), self)
        self.kind_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.kind_shortcut.activated.connect(self._focus_kind_filter)
        self.source_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        self.source_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.source_shortcut.activated.connect(self._focus_source_filter)
        self._audio_process = QProcess(self) if audio_mode else None
        self._stopping_audio = False
        self._audio_preview_generation = 0
        self._audio_preview_request: tuple[int, str, int] | None = None
        # Keep worker lifetime separate from UI ownership. A selection/source
        # change makes the request stale immediately, but its cooperative
        # decoder still owns the one preview worker until the completion signal
        # drains. Retaining that exact request/Event pair prevents a second Play
        # click from enqueueing another decode into the blocking task lane.
        self._audio_preview_job: (
            tuple[tuple[int, str, int], threading.Event] | None
        ) = None
        self._playing_audio_request: tuple[int, str, int] | None = None
        if self._audio_process is not None:
            self._audio_process.finished.connect(self._audio_finished)
            self._audio_process.errorOccurred.connect(self._audio_process_error)
        self._populate_annotation_editor(None)
        self._update_buttons()

    @staticmethod
    def _normalized_audio_bank_name(value: object) -> str:
        return "".join(
            character
            for character in str(value or "").casefold()
            if character.isalnum()
        )

    def _reset_audio_workspaces(self) -> None:
        if not self.audio_mode:
            return
        self._timer.stop()
        self._audio_review_mode = False
        self._audio_review_restore_offset = 0
        self._audio_review_restore_row_id = None
        self._soundtrack_album_mode = False
        self._soundtrack_album_restore_offset = 0
        self._soundtrack_album_restore_row_id = None
        self._soundtrack_album_rows = {}
        self._annotation_drafts.clear()
        self.labeled_only_filter.blockSignals(True)
        try:
            self.labeled_only_filter.setChecked(False)
        finally:
            self.labeled_only_filter.blockSignals(False)
        self._populate_annotation_editor(None)

    def _begin_audio_catalog_transition(self) -> None:
        """Invalidate page-wide actions before an audio model is replaced."""

        if not self.audio_mode:
            return
        self._timer.stop()
        self._audio_catalog_epoch += 1
        self._applied_audio_query_token = None
        self._applied_audio_offset = 0
        self._applied_audio_count_text = ""
        self._applied_audio_page_text = ""
        self._applied_audio_previous_available = False
        self._applied_audio_next_available = False
        self._matching_audio_cache_key = None
        self._matching_audio_cache = ()

    def _discard_audio_shortlist(self) -> None:
        """Irreversibly fence session-only row identities at a model boundary."""

        self._audio_shortlist.clear()
        self._cleared_audio_shortlist = ()

    @staticmethod
    def _audio_row_is_annotatable(row: InspectorRow | None) -> bool:
        """Only one logical playable cue may own a project label."""

        return bool(
            row is not None
            and row.kind in {"audo", "ausb_substream"}
            and row.export_identity is not None
            and row.external_bank_identity is None
        )

    def _labeled_audio_ids(self) -> frozenset[str]:
        if not self._annotation_capable:
            return frozenset()
        try:
            values = getattr(self.facade, "labeled_audio_asset_ids")
            if callable(values):
                values = values()
            return frozenset(str(value) for value in values)
        except Exception:
            # A broken optional metadata store must not hide the base game
            # inventory or crash Audio browsing.
            return frozenset()

    def _annotation_for(self, row_id: str) -> object | None:
        if not self._annotation_capable:
            return None
        getter = getattr(self.facade, "audio_annotation", None)
        if not callable(getter):
            return None
        value = getter(row_id)
        if value is None:
            return None
        cue_id = getattr(value, "cue_id", row_id)
        title = getattr(value, "title", None)
        note = getattr(value, "note", None)
        if cue_id != row_id or not isinstance(title, str) or not isinstance(note, str):
            raise ValueError(
                "The APF audio annotation store returned an invalid cue-label record."
            )
        return value

    @staticmethod
    def _annotation_text(value: object | None) -> tuple[str, str]:
        if value is None:
            return "", ""
        return str(getattr(value, "title")), str(getattr(value, "note"))

    def _populate_annotation_editor(self, row: InspectorRow | None) -> None:
        annotation = None
        draft: tuple[str, str] | None = None
        supported = self._annotation_capable and self._audio_row_is_annotatable(row)
        if supported and row is not None:
            draft = self._annotation_drafts.get(row.row_id)
            try:
                annotation = self._annotation_for(row.row_id)
            except Exception:
                supported = False
        title, note = self._annotation_text(annotation)
        if draft is not None:
            title, note = draft
        self._annotation_loading = True
        self.annotation_title_edit.blockSignals(True)
        self.annotation_note_edit.blockSignals(True)
        try:
            self.annotation_title_edit.setText(title)
            self.annotation_note_edit.setPlainText(note)
        finally:
            self.annotation_title_edit.blockSignals(False)
            self.annotation_note_edit.blockSignals(False)
            self._annotation_loading = False
        self._refresh_annotation_controls(force_supported=supported)

    def _annotation_fields_changed(self, *_args: object) -> None:
        if self._annotation_loading:
            return
        note = self.annotation_note_edit.toPlainText()
        if len(note) > AUDIO_ANNOTATION_MAX_NOTE_CHARS:
            self.annotation_note_edit.blockSignals(True)
            try:
                self.annotation_note_edit.setPlainText(
                    note[:AUDIO_ANNOTATION_MAX_NOTE_CHARS]
                )
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
        row = self._selected_row()
        if not self._audio_row_is_annotatable(row):
            return
        assert row is not None
        title = self.annotation_title_edit.text()
        note = self.annotation_note_edit.toPlainText()
        try:
            current = self._annotation_text(self._annotation_for(row.row_id))
        except Exception:
            self._annotation_drafts[row.row_id] = (title, note)
            return
        normalized = (title.strip(), note.strip())
        if normalized == current:
            self._annotation_drafts.pop(row.row_id, None)
        elif normalized == ("", "") and current == ("", ""):
            self._annotation_drafts.pop(row.row_id, None)
        else:
            self._annotation_drafts[row.row_id] = (title, note)

    def _refresh_annotation_controls(
        self, *, force_supported: bool | None = None
    ) -> None:
        row = self._selected_row()
        playable = self._audio_row_is_annotatable(row)
        supported = self._annotation_capable and playable
        existing = None
        if supported and row is not None:
            try:
                existing = self._annotation_for(row.row_id)
            except Exception:
                supported = False
        if force_supported is not None:
            supported = supported and force_supported
        enabled = bool(
            self.model is not None
            and supported
            and not self._audio_mutation_busy()
        )
        self.annotation_title_edit.setEnabled(enabled)
        self.annotation_note_edit.setEnabled(enabled)
        title = self.annotation_title_edit.text().strip()
        note = self.annotation_note_edit.toPlainText().strip()
        current = self._annotation_text(existing)
        changed = (title, note) != current
        drafted = bool(row is not None and row.row_id in self._annotation_drafts)
        self.save_annotation_button.setEnabled(
            enabled and bool(title or note) and changed
        )
        self.clear_annotation_button.setEnabled(
            enabled and existing is not None
        )
        self.annotation_title_count.setText(
            f"{len(self.annotation_title_edit.text()):,} / "
            f"{AUDIO_ANNOTATION_MAX_TITLE_CHARS:,}"
        )
        self.annotation_note_count.setText(
            f"{len(self.annotation_note_edit.toPlainText()):,} / "
            f"{AUDIO_ANNOTATION_MAX_NOTE_CHARS:,}"
        )
        self.annotation_help.setText(
            "Unsaved draft retained while you browse — choose Save label to "
            "write it into this project."
            if supported and drafted and changed
            else "Project metadata only — searchable and shareable, but never "
            "written into APF or counted as a build edit."
            if supported
            else "Custom labels are available only for individual AUDO sounds "
            "and exact playable AUSB substreams."
        )

    @staticmethod
    def _annotation_operation_changed(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return getattr(value, "changed", True) is not False

    def _annotation_operation_complete(self, row_id: str, value: object) -> None:
        self._annotation_drafts.pop(row_id, None)
        changed = self._annotation_operation_changed(value)
        if changed:
            # Annotation content participates in search, even when the set of
            # labeled IDs did not change. Bump the query epoch so every
            # aggregate action recomputes against the new metadata.
            self._audio_catalog_epoch += 1
            self._applied_audio_query_token = None
            self._matching_audio_cache_key = None
            self._matching_audio_cache = ()
        selected = self._selected_row()
        preserve = selected.row_id if selected is not None else row_id
        self.refresh(preserve)
        if changed:
            self.audioAnnotationChanged.emit(row_id)

    def _run_annotation_operation(
        self,
        label: str,
        row_id: str,
        operation: Callable[[Callable[[str, int, int], None]], object],
    ) -> None:
        if self._audio_mutation_busy():
            return
        self._audio_annotation_running = True
        self._refresh_annotation_controls()
        self._configure_audio_replacement(self._selected_row())

        def wrapped(progress: Callable[[str, int, int], None]) -> object:
            try:
                return operation(progress)
            finally:
                self.audioAnnotationWorkerFinished.emit()

        try:
            admitted = self.run_task(
                label,
                wrapped,
                lambda value: self._annotation_operation_complete(row_id, value),
                True,
            )
        except BaseException:
            self._audio_annotation_running = False
            self._refresh_annotation_controls()
            self._configure_audio_replacement(self._selected_row())
            raise
        if admitted is False:
            self._audio_annotation_running = False
            self._refresh_annotation_controls()
            self._configure_audio_replacement(self._selected_row())

    def _audio_annotation_worker_finished(self) -> None:
        if self._worker_idle_barrier_available:
            self._run_when_idle(self._audio_annotation_idle)
        else:
            self._audio_annotation_idle()

    def _audio_annotation_idle(self) -> None:
        self._audio_annotation_running = False
        self._refresh_annotation_controls()
        self._configure_audio_replacement(self._selected_row())

    def _save_selected_annotation(self) -> None:
        row = self._selected_row()
        method = getattr(self.facade, "set_audio_annotation", None)
        if (
            not self._audio_row_is_annotatable(row)
            or not callable(method)
            or not self.save_annotation_button.isEnabled()
        ):
            return
        assert row is not None
        row_id = row.row_id
        title = self.annotation_title_edit.text().strip()
        note = self.annotation_note_edit.toPlainText().strip()

        def save(progress: Callable[[str, int, int], None]) -> object:
            progress("Saving APF audio cue label", 0, 1)
            result = method(row_id, title, note)
            progress("APF audio cue label saved", 1, 1)
            return result

        self._run_annotation_operation(
            "Saving APF audio cue label",
            row_id,
            save,
        )

    def _clear_selected_annotation(self) -> None:
        row = self._selected_row()
        method = getattr(self.facade, "clear_audio_annotation", None)
        if (
            not self._audio_row_is_annotatable(row)
            or not callable(method)
            or not self.clear_annotation_button.isEnabled()
        ):
            return
        assert row is not None
        row_id = row.row_id

        def clear(progress: Callable[[str, int, int], None]) -> object:
            progress("Clearing APF audio cue label", 0, 1)
            result = method(row_id)
            progress("APF audio cue label cleared", 1, 1)
            return result

        self._run_annotation_operation(
            "Clearing APF audio cue label",
            row_id,
            clear,
        )

    @staticmethod
    def _waveform_row_is_playable(row: InspectorRow | None) -> bool:
        """Only individual AUDO/AUSB sounds own a playable waveform."""

        return bool(
            row is not None
            and row.kind in {"audo", "ausb_substream"}
            and row.export_identity is not None
            and row.external_bank_identity is None
        )

    @staticmethod
    def _audio_row_has_exact_slot_editor(row: InspectorRow | None) -> bool:
        """Individual standalone or banked sounds own bounded XMA1 writers."""

        return bool(
            row is not None
            and row.kind in {"audo", "ausb_substream"}
            and row.export_identity is not None
            and (
                (
                    row.export_identity.kind == "audo"
                    and row.export_identity.substream_index is None
                )
                or (
                    row.export_identity.kind == "ausb_substream"
                    and row.export_identity.substream_index is not None
                )
            )
            and row.external_bank_identity is None
        )

    def _external_xma1_encoder(self) -> ExternalXma1Encoder | None:
        """Recreate the adapter from PC-local settings, never project data."""

        settings = self._audio_settings
        if settings is None:
            return None
        encoder_value = str(
            settings.value("external_xma1_encoder/path", "") or ""
        ).strip()
        if not encoder_value:
            return None
        wine_value = str(
            settings.value("external_xma1_encoder/wine_path", "") or ""
        ).strip()
        arguments: tuple[str, ...] = ("{input}", "{output}")
        stored_arguments = str(
            settings.value("external_xma1_encoder/arguments_json", "") or ""
        ).strip()
        if stored_arguments:
            try:
                decoded_arguments = json.loads(stored_arguments)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Stored XMA1 encoder arguments are malformed; open Configure "
                    "and save them again"
                ) from exc
            if not (
                isinstance(decoded_arguments, list)
                and decoded_arguments
                and all(isinstance(value, str) for value in decoded_arguments)
            ):
                raise ValueError(
                    "Stored XMA1 encoder arguments are invalid; open Configure "
                    "and save one literal argument per line"
                )
            arguments = tuple(decoded_arguments)
        timeout_value = settings.value(
            "external_xma1_encoder/timeout_seconds", 600
        )
        try:
            timeout_seconds = int(timeout_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Stored XMA1 encoder timeout is invalid; open Configure and save it again"
            ) from exc
        if not 30 <= timeout_seconds <= 1800:
            raise ValueError(
                "Stored XMA1 encoder timeout must be 30–1800 seconds; open Configure and save it again"
            )
        return ExternalXma1Encoder(
            Path(encoder_value),
            arguments=arguments,
            wine_executable=Path(wine_value) if wine_value else None,
            timeout_seconds=timeout_seconds,
        )

    def _save_external_xma1_encoder(
        self, encoder: ExternalXma1Encoder
    ) -> None:
        settings = self._audio_settings
        if settings is None:
            raise RuntimeError("Audio encoder settings are unavailable")
        settings.setValue(
            "external_xma1_encoder/path", str(encoder.executable)
        )
        if encoder.wine_executable is None:
            settings.remove("external_xma1_encoder/wine_path")
        else:
            settings.setValue(
                "external_xma1_encoder/wine_path",
                str(encoder.wine_executable),
            )
        settings.setValue(
            "external_xma1_encoder/arguments_json",
            json.dumps(list(encoder.arguments), separators=(",", ":")),
        )
        settings.setValue(
            "external_xma1_encoder/timeout_seconds",
            int(encoder.timeout_seconds),
        )
        settings.sync()
        if settings.status() != QSettings.NoError:
            raise OSError(
                "The local application-settings file could not be updated"
            )

    def _update_audio_encoder_status(self) -> None:
        if not self.audio_mode:
            return
        try:
            encoder = self._external_xma1_encoder()
            if encoder is not None:
                encoder.validate()
        except Exception as exc:
            self.audio_encoder_status.setText(
                "XMA1 encoder: Needs attention • Open Configure and save a valid local setup."
            )
            self.audio_encoder_status.setToolTip(
                f"Stored encoder settings could not be loaded: {exc}\n\n"
                "No project data changed."
            )
            return
        if encoder is None:
            self.audio_encoder_status.setText(
                "XMA1 encoder: Not configured • Template export works now; "
                "choose Configure before returning an edited PCM WAV."
            )
            self.audio_encoder_status.setToolTip(
                "No XMA1 encoder ships with Mod Studio. Select your own local tool; "
                "its path stays in this PC's application settings and never enters a project."
            )
            return
        mode = "through Wine" if encoder.wine_executable is not None else "direct"
        argument_mode = (
            "custom arguments"
            if encoder.arguments != ("{input}", "{output}")
            else "standard arguments"
        )
        self.audio_encoder_status.setText(
            f"XMA1 encoder: {encoder.executable.name} • {mode} • {argument_mode} • "
            f"{int(encoder.timeout_seconds)}s timeout • local setting only; not included in projects"
        )
        detail = f"Encoder: {encoder.executable}"
        if encoder.wine_executable is not None:
            detail += f"\nWine: {encoder.wine_executable}"
        self.audio_encoder_status.setToolTip(
            detail
            + "\n\nThe encoder binary does not ship with Mod Studio. Every output "
            "must still pass the exact-slot validation gates."
        )

    def _configure_external_xma1_encoder(self) -> None:
        if not self.audio_mode or self._audio_mutation_busy():
            return
        encoder = self._run_xma1_encoder_setup_wizard()
        if encoder is None:
            return
        try:
            self._save_external_xma1_encoder(encoder)
        except OSError as exc:
            QMessageBox.information(
                self,
                "Encoder setting was not saved",
                f"{exc}. The mod project was not changed.",
            )
            return
        self._update_audio_encoder_status()
        QMessageBox.information(
            self,
            "XMA1 encoder ready",
            (
                f"Configured {encoder.executable.name} "
                f"{'through Wine' if encoder.wine_executable is not None else 'for direct use'}.\n\n"
                "No encoder was copied into Mod Studio or your project. Encoder "
                "output will be staged only after all exact-slot gates pass."
            ),
        )

    def _run_xma1_encoder_setup_wizard(self) -> ExternalXma1Encoder | None:
        """Open the guided encoder setup; return the accepted adapter or None.

        The wizard test-runs the encoder on a private one-second tone before
        it accepts, so a returned encoder is one the user has already seen
        work.  Saving to settings happens in the caller, never here.
        """

        try:
            current = self._external_xma1_encoder()
        except Exception:
            # Corrupt local preferences must never strand the Audio panel. A
            # fresh valid selection replaces them only after wizard validation.
            current = None
        wizard = Xma1EncoderSetupWizard(
            encoder_path=current.executable if current is not None else None,
            wine_path=(
                current.wine_executable if current is not None else None
            ),
            use_wine=bool(
                current is not None and current.wine_executable is not None
            ),
            arguments=(
                current.arguments
                if current is not None
                else XMA1_WIZARD_TEMPLATE_ARGUMENTS
            ),
            timeout_seconds=(
                int(current.timeout_seconds) if current is not None else 600
            ),
            parent=self,
        )
        if wizard.exec_() != QDialog.Accepted:
            return None
        return wizard.encoder

    def _audio_mutation_busy(self) -> bool:
        return bool(
            self._pcm_encoding_running
            or self._audio_import_running
            or self._direct_audio_replacement_running
            or self._audio_annotation_running
        )

    def _configure_audio_replacement(self, row: InspectorRow | None) -> None:
        if not self.audio_mode:
            return
        editable = self._audio_row_has_exact_slot_editor(row)
        mutation_busy = self._audio_mutation_busy()
        self._refresh_annotation_controls()
        self._update_audio_workspace_controls()
        drop_available = editable and not mutation_busy
        # Never silent-gray PCM/XMA replace actions — teach walls via disableReason.
        pcm_ready = editable and not mutation_busy
        self.export_pcm_template_button.setEnabled(True)
        self.export_pcm_template_button.setVisible(
            self.audio_mode and not self._pcm_encoding_running
        )
        self.replace_pcm_audio_button.setEnabled(True)
        self.replace_pcm_audio_button.setVisible(
            self.audio_mode and not self._pcm_encoding_running
        )
        self.cancel_pcm_encoding_button.setVisible(
            self.audio_mode and self._pcm_encoding_running
        )
        self.cancel_pcm_encoding_button.setEnabled(
            self._pcm_encoding_running and not self._pcm_encoding_cancel.is_set()
        )
        self.cancel_pcm_encoding_button.setText(
            "Cancelling safely…"
            if self._pcm_encoding_running and self._pcm_encoding_cancel.is_set()
            else "Cancel PCM encoding"
        )
        self._update_audio_encoder_status()
        modified_ids = frozenset(
            getattr(self.facade, "modified_asset_ids", frozenset())
        )
        modified = bool(row is not None and row.row_id in modified_ids)
        self.audio_replacement_drop_zone.set_available(
            drop_available,
            modified=modified,
        )
        self.configure_audio_encoder_button.setEnabled(
            not mutation_busy
        )
        self.replace_audio_button.setEnabled(True)
        self.replace_audio_button.setText(
            "Replace XMA1 again…" if editable and modified else "Replace with XMA1…"
        )
        self.revert_audio_button.setEnabled(True)
        self._update_audio_replacement_pack_actions()
        if editable and row is not None:
            banked = row.kind == "ausb_substream"
            size = int(
                row.fields.get("range_length", 0)
                if banked
                else row.fields.get("encoded_size", 0)
            )
            rate = int(row.fields.get("sample_rate", 0))
            channels = int(row.fields.get("derived_channel_count", 0))
            channel_label = "mono" if channels == 1 else "stereo" if channels == 2 else f"{channels} channels"
            state = "This sound has a staged replacement." if modified else "This sound is still original."
            family = "AUSB bank substream" if banked else "standalone AUDO sound"
            shared_ids = tuple(row.fields.get("shared_owner_asset_ids", ()))
            shared_note = (
                " This physical slot has multiple owners; all listed owner rows change together: "
                + ", ".join(str(value) for value in shared_ids)
                + "."
                if len(shared_ids) > 1
                else ""
            )
            decoder_note = (
                " Some valid retail AUSB streams exceed FFmpeg 6.1.1's decoder support, "
                "so the conservative complete-decode gate may reject an otherwise valid file."
                if banked
                else ""
            )
            self.audio_replace_note.setText(
                "PCM authoring bridge + exact-slot editor • "
                f"{family}. "
                f"Required: {_human_bytes(size)} encoded data, {rate:,} Hz, "
                f"{channel_label}. Export the exact PCM template for easy WAV authoring, "
                "or choose an ordinary WAV, MP3, FLAC, OGG, M4A, or other supported "
                "audio file and let Mod Studio conform it to this slot, "
                "or use Replace with XMA1 when you already have a finished stream. "
                f"No encoder ships with Mod Studio. {state} Every final XMA1 result "
                "must pass a complete decode, all packet checks, both source-audio "
                "fingerprint sets, and the exact slot shape. The project stores only "
                "the accepted replacement stream—not the encoder, input PCM, or a "
                "source-packet backup—"
                f"and leaves the source game untouched.{shared_note}{decoder_note}"
            )
            busy_tip = "Wait for the current audio mutation to finish."
            pcm_tip = (
                f"Export an exact {rate:,} Hz {channel_label} PCM16 silence WAV for "
                "this slot. The template contains no retail audio."
            )
            replace_pcm_tip = (
                "Choose WAV, MP3, FLAC, OGG, M4A, or another supported audio file. "
                f"Mod Studio conforms it privately to {rate:,} Hz {channel_label} "
                "PCM16 before your external encoder runs; the final output must fit exactly "
                f"{size:,} encoded bytes and pass every slot gate."
            )
            replace_xma_tip = (
                f"Import pre-encoded RIFF XMA1 with exactly {size:,} encoded bytes, "
                f"{rate:,} Hz, and {channel_label}; the same exact-slot gates still apply."
            )
            if mutation_busy:
                self.export_pcm_template_button.setToolTip(busy_tip)
                self.export_pcm_template_button.setProperty("disableReason", busy_tip)
                self.replace_pcm_audio_button.setToolTip(busy_tip)
                self.replace_pcm_audio_button.setProperty("disableReason", busy_tip)
                self.replace_audio_button.setToolTip(busy_tip)
                self.replace_audio_button.setProperty("disableReason", busy_tip)
                self.revert_audio_button.setToolTip(busy_tip)
                self.revert_audio_button.setProperty("disableReason", busy_tip)
            else:
                self.export_pcm_template_button.setToolTip(pcm_tip)
                self.export_pcm_template_button.setProperty("disableReason", "")
                self.replace_pcm_audio_button.setToolTip(replace_pcm_tip)
                self.replace_pcm_audio_button.setProperty("disableReason", "")
                self.replace_audio_button.setToolTip(replace_xma_tip)
                self.replace_audio_button.setProperty("disableReason", "")
                if modified:
                    self.revert_audio_button.setToolTip(
                        "Remove this one staged sound replacement and use the "
                        "untouched source audio."
                    )
                    self.revert_audio_button.setProperty("disableReason", "")
                else:
                    tip = "This sound has no staged replacement."
                    self.revert_audio_button.setToolTip(tip)
                    self.revert_audio_button.setProperty("disableReason", tip)
            return
        pick_tip = (
            "Choose one individual AUDO or AUSB sound. AUSB index rows and complete "
            "physical banks are containers, so they remain export-only."
        )
        self.replace_audio_button.setToolTip(pick_tip)
        self.replace_audio_button.setProperty("disableReason", pick_tip)
        self.export_pcm_template_button.setToolTip(
            "Choose one individual AUDO or AUSB sound before exporting its exact PCM template."
        )
        self.export_pcm_template_button.setProperty(
            "disableReason",
            "Choose one individual AUDO or AUSB sound before exporting its exact PCM template.",
        )
        self.replace_pcm_audio_button.setToolTip(
            "Choose one individual AUDO or AUSB sound before importing ordinary audio."
        )
        self.replace_pcm_audio_button.setProperty(
            "disableReason",
            "Choose one individual AUDO or AUSB sound before importing ordinary audio.",
        )
        self.revert_audio_button.setToolTip(
            "Choose a modified individual AUDO or AUSB sound first."
        )
        self.revert_audio_button.setProperty(
            "disableReason",
            "Choose a modified individual AUDO or AUSB sound first.",
        )
        self.audio_replace_note.setText(
            "Choose one individual sound row to replace it. All 2,261 standalone AUDO "
            "sounds and all 45,514 indexed AUSB soundtrack, commentary, speech, PA, and "
            "presentation substreams support strict pre-encoded XMA1 exact-slot input. "
            "Whole index rows and physical banks remain browse/export-only."
        )

    def _cancel_audio_waveform(self) -> None:
        if not self.audio_mode:
            return
        self._waveform_generation += 1
        if self._waveform_request is not None:
            self._waveform_request.cancel()

    def _configure_audio_waveform(self, row: InspectorRow | None) -> None:
        if not self.audio_mode:
            return
        self._waveform_selected_row_id = row.row_id if row is not None else None
        if self._waveform_request is not None:
            self.waveform_preview.set_empty(
                "The previous request was cancelled and is finishing privately. "
                "Browsing remains available."
            )
            self.load_waveform_button.setText("Canceling previous…")
            # Stay clickable so Cancel is never a silent gray no-op mid-cancel.
            self.load_waveform_button.setEnabled(True)
            tip = "Wait for the previous private decode cancel to finish."
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        self.load_waveform_button.setText("Load waveform")
        # Never silent-gray: button stays enabled; disableReason explains block.
        self.load_waveform_button.setEnabled(True)
        if row is None:
            self.waveform_preview.set_unavailable(
                "Choose an individual AUDO or AUSB sound."
            )
            tip = (
                "Select an individual AUDO/AUSB sound row first, then Load waveform. "
                "Click still explains this."
            )
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        if row.kind == "external_bank" or row.external_bank_identity is not None:
            self.waveform_preview.set_unavailable(
                "A physical external bank contains many packetized sounds and is not "
                "one playable waveform. Choose one of its AUSB substream rows."
            )
            tip = (
                "External banks are multi-sound packages. Expand and select one AUSB "
                "substream, then Load waveform."
            )
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        if row.kind == "ausb_bank":
            self.waveform_preview.set_unavailable(
                "This is a bank index, not one sound. Choose an individual substream."
            )
            tip = (
                "This row is a bank index. Choose an individual substream sound, "
                "then Load waveform."
            )
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        if not self._waveform_row_is_playable(row):
            self.waveform_preview.set_unavailable(
                "This decoded row has no verified playable WAV route."
            )
            tip = (
                "This row has no verified playable WAV route. Pick another sound "
                "or export raw for offline decode."
            )
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        self.waveform_preview.set_empty(
            "Waveforms are not loaded automatically. Click Load waveform to decode "
            "this sound privately; playback will not start."
        )
        self.load_waveform_button.setProperty("disableReason", "")
        self.load_waveform_button.setToolTip(
            "Read this sound through the verified session-private WAV path and draw a "
            "bounded waveform. This does not play, replace, or add audio to the project."
        )

    def _load_audio_waveform(self) -> None:
        if not self.audio_mode:
            return
        if self._waveform_request is not None:
            self._waveform_request.cancel()
            self.waveform_preview.set_empty(
                "Cancelling the private waveform decode. No audio will be published."
            )
            self.load_waveform_button.setText("Cancelling…")
            self.load_waveform_button.setEnabled(True)
            tip = "Cancel already requested — wait for the private decode to stop."
            self.load_waveform_button.setToolTip(tip)
            self.load_waveform_button.setProperty("disableReason", tip)
            return
        reason = str(self.load_waveform_button.property("disableReason") or "").strip()
        if reason and "Cancel" not in self.load_waveform_button.text():
            self.waveform_preview.set_unavailable(reason)
            return
        row = self._selected_row()
        if not self._waveform_row_is_playable(row):
            self._configure_audio_waveform(row)
            return
        assert row is not None and row.export_identity is not None
        identity = row.export_identity
        row_id = row.row_id
        request = WaveformRequest()
        self._waveform_request = request
        self._waveform_generation += 1
        generation = self._waveform_generation
        self.waveform_preview.set_loading(
            "Decoding only this selected sound to the private session cache…"
        )
        self.load_waveform_button.setText("Cancel waveform")
        self.load_waveform_button.setEnabled(True)
        self.load_waveform_button.setToolTip(
            "Stop this private waveform decode and discard its result."
        )

        def operation(
            progress: Callable[[str, int, int], None]
        ) -> tuple[str, object | None]:
            try:
                request.check()

                def guarded_progress(stage: str, completed: int, total: int) -> None:
                    request.check()
                    progress(stage, completed, total)

                path = self.facade.prepare_audio_preview(
                    identity,
                    guarded_progress,
                    cancel_requested=lambda: request.cancelled,
                )
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

        self.run_task(
            "Preparing selected APF waveform",
            operation,
            lambda result: self._audio_waveform_complete(
                request,
                generation,
                row_id,
                result,
            ),
            False,
        )

    def _audio_waveform_complete(
        self,
        request: WaveformRequest,
        generation: int,
        row_id: str,
        result: object,
    ) -> None:
        if self._waveform_request is request:
            self._waveform_request = None
        selected = self._selected_row()
        if (
            request.cancelled
            or generation != self._waveform_generation
            or selected is None
            or selected.row_id != row_id
        ):
            self._configure_audio_waveform(selected)
            return
        try:
            state, value = result  # type: ignore[misc]
        except (TypeError, ValueError):
            state, value = "error", "The waveform worker returned an invalid result"
        if state == "ready" and isinstance(value, WaveformEnvelope):
            self.waveform_preview.set_envelope(value)
            self.load_waveform_button.setText("Reload waveform")
            self.load_waveform_button.setEnabled(True)
            return
        if state == "cancelled":
            self._configure_audio_waveform(selected)
            return
        message = str(value or "The selected sound could not be decoded")
        self.waveform_preview.set_error(message)
        self.load_waveform_button.setText("Retry waveform")
        self.load_waveform_button.setEnabled(True)

    def _index_soundtrack_album(self) -> None:
        """Cache only the exact, inspector-proved 15-by-15 soundtrack pair."""

        self._soundtrack_album_rows = {}
        if not self.audio_mode or self.model is None:
            return
        grouped: dict[str, list[InspectorRow]] = {
            "jukeboxmusic": [],
            "jukebox22": [],
        }
        for row in self.model.rows:
            name = self._normalized_audio_bank_name(row.fields.get("bank_name"))
            if row.kind == "ausb_substream" and name in grouped:
                grouped[name].append(row)
        try:
            ordered = {
                name: tuple(
                    sorted(
                        rows,
                        key=lambda row: int(row.fields["substream_index"]),
                    )
                )
                for name, rows in grouped.items()
            }
            if any(len(rows) != 15 for rows in ordered.values()):
                return
            for name, rows in ordered.items():
                expected_pair = "jukebox22" if name == "jukeboxmusic" else "jukeboxmusic"
                expected_rate = 48_000 if name == "jukeboxmusic" else 22_050
                expected_channels = 2 if name == "jukeboxmusic" else 1
                if [int(row.fields["substream_index"]) for row in rows] != list(range(15)):
                    return
                if any(
                    row.export_identity is None
                    or int(row.fields.get("logical_track_number", 0)) != index + 1
                    or self._normalized_audio_bank_name(
                        row.fields.get("paired_bank_name")
                    )
                    != expected_pair
                    or int(row.fields.get("sample_rate", 0)) != expected_rate
                    or int(row.fields.get("derived_channel_count", 0))
                    != expected_channels
                    for index, row in enumerate(rows)
                ):
                    return
            for stereo, mono in zip(
                ordered["jukeboxmusic"], ordered["jukebox22"], strict=True
            ):
                stereo_duration = float(
                    stereo.fields["duration_seconds_candidate"]
                )
                mono_duration = float(mono.fields["duration_seconds_candidate"])
                if abs(stereo_duration - mono_duration) > 0.001:
                    return
        except (KeyError, TypeError, ValueError):
            return
        self._soundtrack_album_rows = ordered

    def _update_audio_workspace_controls(self) -> None:
        if not self.audio_mode:
            return
        loaded = self.model is not None
        special_view = self._audio_review_mode or self._soundtrack_album_mode
        browser_controls_enabled = loaded and not special_view
        self.search.setEnabled(browser_controls_enabled)
        self.kind_filter.setEnabled(browser_controls_enabled)
        self.role_filter.setEnabled(browser_controls_enabled)
        self.source_filter.setEnabled(browser_controls_enabled)
        self.labeled_only_filter.setEnabled(
            browser_controls_enabled
            and self._annotation_capable
            and not self._audio_mutation_busy()
        )
        self.export_rows_button.setEnabled(browser_controls_enabled)
        album_available = set(self._soundtrack_album_rows) == {
            "jukeboxmusic",
            "jukebox22",
        }
        self.soundtrack_album_button.setText(
            "Back to all audio"
            if self._soundtrack_album_mode
            else "Soundtrack album (15)"
            if album_available
            else "Soundtrack album"
        )
        album_ready = loaded and album_available and not self._audio_review_mode
        album_tip = (
            "Return to the complete audio browser with its filters, page, and selection intact."
            if self._soundtrack_album_mode
            else "Open the 15 bank-indexed soundtrack tracks; stereo masters are the default and mono companions remain one selector away."
            if album_available
            else (
                "Return to the audio browser first (exit shortlist review)."
                if self._audio_review_mode
                else "Load a supported APF game first."
                if not loaded
                else "This source does not expose the exact proved pair: 15 jukeboxmusic stereo streams and 15 jukebox22 mono companions."
            )
        )
        self.soundtrack_album_button.setEnabled(True)
        self.soundtrack_album_button.setToolTip(album_tip)
        self.soundtrack_album_button.setProperty(
            "disableReason", "" if album_ready else album_tip
        )
        show_album_context = self._soundtrack_album_mode and not self._audio_review_mode
        self.soundtrack_version.setVisible(show_album_context)
        self.soundtrack_version.setEnabled(show_album_context)
        self.soundtrack_album_note.setVisible(show_album_context)
        self.shortlist_hint.setText(
            "Review uses only decoded row identities in your exact insertion order. "
            "Move sounds to set bundle order, play or export them, or remove them; no project is modified."
            if self._audio_review_mode
            else "Collect sounds across searches, pages, and banks, then export one private bundle. "
            "The shortlist clears when the loaded game changes."
        )

    def set_loading(self, message: str) -> None:
        self._stop_audio()
        self._cancel_audio_waveform()
        self._waveform_selected_row_id = None
        self._reset_audio_workspaces()
        self._begin_audio_catalog_transition()
        self._discard_audio_shortlist()
        self.model = None
        self.summary.setText(message)
        self.count.setText("Loading…")
        self.table.setRowCount(0)
        self.detail_fields.setPlainText("")
        self.export_audio_button.setVisible(False)
        self.export_bank_button.setVisible(False)
        self.export_external_bank_button.setVisible(False)
        self.export_external_bank_button.setEnabled(True)
        self.export_external_bank_button.setToolTip('Select an external bank row first.')
        self.export_external_bank_button.setProperty("disableReason", 'Select an external bank row first.')
        tip = "Select a playable sound row first."
        self.play_audio_button.setEnabled(True)
        self.play_audio_button.setToolTip(tip)
        self.play_audio_button.setProperty("disableReason", tip)
        self._configure_audio_waveform(None)
        self._configure_audio_replacement(None)
        tip = "Load a supported APF game first, then export decoded inspector rows."

        self.export_rows_button.setEnabled(True)

        self.export_rows_button.setToolTip(tip)

        self.export_rows_button.setProperty("disableReason", tip)
        self.export_complete_audio_catalog_button.setEnabled(True)
        self.export_complete_audio_catalog_button.setToolTip('Load a supported APF game first, then export the complete audio catalog.')
        self.export_complete_audio_catalog_button.setProperty("disableReason", 'Load a supported APF game first, then export the complete audio catalog.')
        self.export_original_audio_banks_button.setEnabled(True)
        self.export_original_audio_banks_button.setToolTip('Load a supported APF game first, then export original banks.')
        self.export_original_audio_banks_button.setProperty("disableReason", 'Load a supported APF game first, then export original banks.')
        self.export_audio_replacement_template_button.setEnabled(True)
        self.export_audio_replacement_template_button.setToolTip('Load a supported APF game first for replacement templates.')
        self.export_audio_replacement_template_button.setProperty("disableReason", 'Load a supported APF game first for replacement templates.')
        self.import_audio_replacement_pack_button.setEnabled(True)
        self.import_audio_replacement_pack_button.setToolTip('Load a supported APF game first for replacement packs.')
        self.import_audio_replacement_pack_button.setProperty("disableReason", 'Load a supported APF game first for replacement packs.')
        self.cancel_audio_import_button.setEnabled(False)
        self.cancel_audio_export_button.setEnabled(False)
        self.export_matching_button.setEnabled(True)
        self.export_matching_button.setToolTip('Load a supported APF game first, then export matching sounds.')
        self.export_matching_button.setProperty("disableReason", 'Load a supported APF game first, then export matching sounds.')
        loading_tip = (
            "Text allocations are still loading. Wait for the text catalog, "
            "then Export/Import Text Sheet."
        )
        self.export_text_sheet_button.setEnabled(True)
        self.export_text_sheet_button.setToolTip(loading_tip)
        self.export_text_sheet_button.setProperty("disableReason", loading_tip)
        self.import_text_sheet_button.setEnabled(True)
        self.import_text_sheet_button.setToolTip(loading_tip)
        self.import_text_sheet_button.setProperty("disableReason", loading_tip)
        self._clear_text_editor("Loading text allocations…")
        self._roster_allocations = {}
        self._clear_roster_editor("Loading roster identity allocations…")
        self._update_audio_workspace_controls()
        self._update_audio_shortlist_actions()
        self._update_buttons()

    def set_unavailable(self, message: str) -> None:
        self._stop_audio()
        self._cancel_audio_waveform()
        self._waveform_selected_row_id = None
        self._reset_audio_workspaces()
        self._begin_audio_catalog_transition()
        self._discard_audio_shortlist()
        self.model = None
        self.summary.setText(message)
        self.count.setText("Unavailable")
        self.table.setRowCount(0)
        self.export_audio_button.setVisible(False)
        self.export_bank_button.setVisible(False)
        self.export_external_bank_button.setVisible(False)
        self.export_external_bank_button.setEnabled(True)
        self.export_external_bank_button.setToolTip('Select an external bank row first.')
        self.export_external_bank_button.setProperty("disableReason", 'Select an external bank row first.')
        tip = "Select a playable sound row first."
        self.play_audio_button.setEnabled(True)
        self.play_audio_button.setToolTip(tip)
        self.play_audio_button.setProperty("disableReason", tip)
        self._configure_audio_waveform(None)
        self._configure_audio_replacement(None)
        tip = "Load a supported APF game first, then export decoded inspector rows."

        self.export_rows_button.setEnabled(True)

        self.export_rows_button.setToolTip(tip)

        self.export_rows_button.setProperty("disableReason", tip)
        self.export_complete_audio_catalog_button.setEnabled(True)
        self.export_complete_audio_catalog_button.setToolTip('Load a supported APF game first, then export the complete audio catalog.')
        self.export_complete_audio_catalog_button.setProperty("disableReason", 'Load a supported APF game first, then export the complete audio catalog.')
        self.export_original_audio_banks_button.setEnabled(True)
        self.export_original_audio_banks_button.setToolTip('Load a supported APF game first, then export original banks.')
        self.export_original_audio_banks_button.setProperty("disableReason", 'Load a supported APF game first, then export original banks.')
        self.export_audio_replacement_template_button.setEnabled(True)
        self.export_audio_replacement_template_button.setToolTip('Load a supported APF game first for replacement templates.')
        self.export_audio_replacement_template_button.setProperty("disableReason", 'Load a supported APF game first for replacement templates.')
        self.import_audio_replacement_pack_button.setEnabled(True)
        self.import_audio_replacement_pack_button.setToolTip('Load a supported APF game first for replacement packs.')
        self.import_audio_replacement_pack_button.setProperty("disableReason", 'Load a supported APF game first for replacement packs.')
        self.cancel_audio_import_button.setEnabled(False)
        self.cancel_audio_export_button.setEnabled(False)
        self.export_matching_button.setEnabled(True)
        self.export_matching_button.setToolTip('Load a supported APF game first, then export matching sounds.')
        self.export_matching_button.setProperty("disableReason", 'Load a supported APF game first, then export matching sounds.')
        load_tip = (
            "Load a supported APF game first. Text Sheet export/import needs a "
            "loaded text catalog. Click still explains."
        )
        self.export_text_sheet_button.setEnabled(True)
        self.export_text_sheet_button.setToolTip(load_tip)
        self.export_text_sheet_button.setProperty("disableReason", load_tip)
        self.import_text_sheet_button.setEnabled(True)
        self.import_text_sheet_button.setToolTip(load_tip)
        self.import_text_sheet_button.setProperty("disableReason", load_tip)
        self._clear_text_editor("Load a supported game to edit text.")
        self._roster_allocations = {}
        self._clear_roster_editor("Load a supported game to edit roster names.")
        self.findings.setText("No write was attempted. The generic archive browser remains available below.")
        self._update_audio_workspace_controls()
        self._update_audio_shortlist_actions()
        self._update_buttons()

    def set_model(self, model: PagedModel, summary: str) -> None:
        self._stop_audio()
        self._cancel_audio_waveform()
        self._waveform_selected_row_id = None
        self._reset_audio_workspaces()
        self._begin_audio_catalog_transition()
        self._discard_audio_shortlist()
        self.model = model
        self._index_soundtrack_album()
        self._text_allocations = (
            {
                str(getattr(row, "asset_id")): row
                for row in self.facade.localization_text_allocations()
            }
            if self.text_mode
            else {}
        )
        self._roster_allocations = (
            {
                str(getattr(row, "asset_id")): row
                for row in self.facade.roster_identity_allocations()
            }
            if self.roster_mode
            else {}
        )
        self.offset = 0
        self.summary.setText(summary)
        self.kind_filter.blockSignals(True)
        self.kind_filter.clear()
        self.kind_filter.addItem("All decoded record kinds", None)
        for kind, count in model.kind_counts.items():
            self.kind_filter.addItem(f"{kind.replace('_', ' ').title()} ({count:,})", kind)
        self.kind_filter.blockSignals(False)
        self.role_filter.blockSignals(True)
        self.role_filter.clear()
        self.role_filter.addItem("All audio roles", None)
        role_labels = {
            str(row.fields.get("role_id")): str(row.fields.get("role_label"))
            for row in model.rows
            if row.fields.get("role_id") and row.fields.get("role_label")
        }
        for role_id, count in model.role_counts.items():
            label = role_labels.get(role_id, role_id.replace("_", " ").title())
            self.role_filter.addItem(f"{label} ({count:,})", role_id)
        self.role_filter.blockSignals(False)
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("All audio sources", None)
        for source_id, label, count in model.audio_sources:
            self.source_filter.addItem(f"{label} ({count:,})", source_id)
        self.source_filter.blockSignals(False)
        self.findings.setText("  •  ".join(model.findings))
        self.export_rows_button.setEnabled(True)
        if self.roster_mode:
            export_rtip = (
                "Export all 2,254 players and all 31 exact base ratings as one "
                "private CSV. It contains data derived from your game copy and "
                "never enters a shareable project."
            )
            import_rtip = (
                "Ctrl+Shift+I · Choose a private Mod Studio ratings CSV, validate "
                "every row without changing the project, then review replacements, "
                "source reverts, unchanged cells, conflicts, and errors before an "
                "explicit Apply."
            )
            self.export_ratings_sheet_button.setEnabled(True)
            self.export_ratings_sheet_button.setToolTip(export_rtip)
            self.export_ratings_sheet_button.setProperty("disableReason", "")
            self.import_ratings_sheet_button.setEnabled(True)
            self.import_ratings_sheet_button.setToolTip(import_rtip)
            self.import_ratings_sheet_button.setProperty("disableReason", "")
        else:
            rtip = "Ratings sheet actions are only available in the Roster workspace."
            self.export_ratings_sheet_button.setEnabled(True)
            self.export_ratings_sheet_button.setToolTip(rtip)
            self.export_ratings_sheet_button.setProperty("disableReason", rtip)
            self.import_ratings_sheet_button.setEnabled(True)
            self.import_ratings_sheet_button.setToolTip(rtip)
            self.import_ratings_sheet_button.setProperty("disableReason", rtip)
        self._update_bulk_audio_export_controls()
        if self.text_mode:
            export_tip = (
                "Create a private CSV containing every owned TXT/STRG allocation "
                "from your loaded game."
            )
            import_tip = (
                "Validate an APF Text Sheet completely, then apply every requested "
                "row as one Undo action."
            )
            self.export_text_sheet_button.setEnabled(True)
            self.export_text_sheet_button.setToolTip(export_tip)
            self.export_text_sheet_button.setProperty("disableReason", "")
            self.import_text_sheet_button.setEnabled(True)
            self.import_text_sheet_button.setToolTip(import_tip)
            self.import_text_sheet_button.setProperty("disableReason", "")
        else:
            tip = "Text Sheet actions are only available in the Text workspace."
            self.export_text_sheet_button.setEnabled(True)
            self.export_text_sheet_button.setToolTip(tip)
            self.export_text_sheet_button.setProperty("disableReason", tip)
            self.import_text_sheet_button.setEnabled(True)
            self.import_text_sheet_button.setToolTip(tip)
            self.import_text_sheet_button.setProperty("disableReason", tip)
        self.refresh()

    def _restart_filter(self) -> None:
        if self._audio_review_mode or self._soundtrack_album_mode:
            return
        self._timer.start()
        if not self.audio_mode:
            self.offset = 0
            return
        # Fast type/erase can return to the exact page already on screen.  In
        # that case there is no stale work to apply and controls recover now.
        if self._audio_query_controls_match_applied():
            self._timer.stop()
            self.offset = self._applied_audio_offset
            self._restore_applied_audio_query_presentation()
            return
        self.offset = 0
        self._mark_audio_query_pending()

    def _current_audio_query_token(
        self,
    ) -> tuple[int, str, str | None, str | None, str | None, bool]:
        def selected_data(widget: QComboBox) -> str | None:
            value = widget.currentData()
            return None if value is None else str(value)

        return (
            self._audio_catalog_epoch,
            self.search.text(),
            selected_data(self.kind_filter),
            selected_data(self.role_filter),
            selected_data(self.source_filter),
            self.labeled_only_filter.isChecked(),
        )

    def _audio_query_controls_match_applied(self) -> bool:
        return bool(
            self.audio_mode
            and self.model is not None
            and self._applied_audio_query_token is not None
            and self._applied_audio_query_token == self._current_audio_query_token()
        )

    def _audio_filtered_rows(
        self,
        *,
        model: PagedModel | None = None,
        search: str | None = None,
        kinds: str | Iterable[str] | None = None,
        roles: str | Iterable[str] | None = None,
        sources: str | Iterable[str] | None = None,
        labeled_only: bool | None = None,
    ) -> tuple[InspectorRow, ...]:
        """Apply one canonical base-plus-project-metadata Audio query."""

        selected_model = model or self.model
        if selected_model is None:
            return ()
        query = self.search.text() if search is None else search
        selected_kinds = self.kind_filter.currentData() if kinds is None else kinds
        selected_roles = self.role_filter.currentData() if roles is None else roles
        selected_sources = (
            self.source_filter.currentData() if sources is None else sources
        )
        only_labeled = (
            self.labeled_only_filter.isChecked()
            if labeled_only is None
            else labeled_only
        )
        candidates = selected_model.filtered_rows(
            search="",
            kinds=selected_kinds,
            roles=selected_roles,
            sources=selected_sources,
        )
        labeled_ids = self._labeled_audio_ids()
        terms = tuple(query.casefold().split())
        matching: list[InspectorRow] = []
        for row in candidates:
            labeled = row.row_id in labeled_ids
            if only_labeled and not labeled:
                continue
            annotation_haystack = ""
            if labeled:
                try:
                    title, note = self._annotation_text(
                        self._annotation_for(row.row_id)
                    )
                    annotation_haystack = f"{title} {note}".casefold()
                except Exception:
                    annotation_haystack = ""
            if terms and not all(
                row.matches(term) or term in annotation_haystack
                for term in terms
            ):
                continue
            matching.append(row)
        return tuple(matching)

    def _audio_catalog_query_is_current(self) -> bool:
        return bool(
            self._audio_query_controls_match_applied()
            and self.offset == self._applied_audio_offset
        )

    def _audio_page_actions_ready(self) -> bool:
        return bool(
            self.audio_mode
            and self.model is not None
            and not self._audio_review_mode
            and (
                self._soundtrack_album_mode
                or self._audio_catalog_query_is_current()
            )
        )

    def _audio_pagination_ready(self) -> bool:
        return bool(
            self.audio_mode
            and self.model is not None
            and (
                self._audio_review_mode
                or self._soundtrack_album_mode
                or self._audio_catalog_query_is_current()
            )
        )

    def _mark_audio_query_pending(self) -> None:
        """Fence the old page while retaining its exact selected-row actions."""

        self.count.setText("Updating audio results…")
        self.page.setText("Waiting for the new search and filters…")
        pending_tip = (
            "Wait for search/filters to finish updating results, then page."
        )
        for button in (self.previous, self.next):
            button.setEnabled(True)
            button.setToolTip(pending_tip)
            button.setProperty("disableReason", pending_tip)
        rows_tip = (
            "Wait for search/filters to finish updating results, then export "
            "decoded rows."
        )
        self.export_rows_button.setEnabled(True)
        self.export_rows_button.setToolTip(rows_tip)
        self.export_rows_button.setProperty("disableReason", rows_tip)
        self._update_matching_audio_action()
        self._update_audio_shortlist_actions()

    def _sync_inspector_pagination(
        self, *, previous_available: bool, next_available: bool, ready: bool
    ) -> None:
        """Never silent-gray Previous/Next — teach first/last/pending walls."""

        if not ready:
            tip = (
                "Wait for search/filters to finish updating results, then page."
                if self.audio_mode
                else "Load your APF game first, then page results."
            )
            for button in (self.previous, self.next):
                button.setEnabled(True)
                button.setToolTip(tip)
                button.setProperty("disableReason", tip)
            return
        if previous_available:
            self.previous.setEnabled(True)
            self.previous.setToolTip("Show the previous page of results.")
            self.previous.setProperty("disableReason", "")
        else:
            tip = "Already on the first page of matching results."
            self.previous.setEnabled(True)
            self.previous.setToolTip(tip)
            self.previous.setProperty("disableReason", tip)
        if next_available:
            self.next.setEnabled(True)
            self.next.setToolTip("Show the next page of results.")
            self.next.setProperty("disableReason", "")
        else:
            tip = "Already on the last page of matching results."
            self.next.setEnabled(True)
            self.next.setToolTip(tip)
            self.next.setProperty("disableReason", tip)

    def _restore_applied_audio_query_presentation(self) -> None:
        """Restore controls when fast type/erase returns to the shown query."""

        if self._applied_audio_count_text:
            self.count.setText(self._applied_audio_count_text)
        if self._applied_audio_page_text:
            self.page.setText(self._applied_audio_page_text)
        ready = self._audio_pagination_ready()
        self._sync_inspector_pagination(
            previous_available=self._applied_audio_previous_available,
            next_available=self._applied_audio_next_available,
            ready=ready,
        )
        self.export_rows_button.setEnabled(self.model is not None)
        self._update_matching_audio_action()
        self._update_audio_shortlist_actions()

    def _focus_search(self) -> None:
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def _focus_kind_filter(self) -> None:
        self.kind_filter.setFocus(Qt.ShortcutFocusReason)
        self.kind_filter.showPopup()

    def _focus_source_filter(self) -> None:
        if not self.audio_mode:
            return
        self.source_filter.setFocus(Qt.ShortcutFocusReason)
        self.source_filter.showPopup()

    def _toggle_soundtrack_album(self) -> None:
        reason = str(
            self.soundtrack_album_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot open soundtrack album yet",
                reason,
            )
            return
        if not self.audio_mode or self.model is None:
            return
        if self._soundtrack_album_mode:
            self._soundtrack_album_mode = False
            self.offset = self._soundtrack_album_restore_offset
            restore_row_id = self._soundtrack_album_restore_row_id
            self._soundtrack_album_restore_row_id = None
            self._update_audio_workspace_controls()
            self.refresh(restore_row_id)
            return
        if set(self._soundtrack_album_rows) != {"jukeboxmusic", "jukebox22"}:
            return
        selected = self._selected_row()
        self._soundtrack_album_restore_offset = self.offset
        self._soundtrack_album_restore_row_id = (
            selected.row_id if selected is not None else None
        )
        self._soundtrack_album_mode = True
        self.soundtrack_version.blockSignals(True)
        self.soundtrack_version.setCurrentIndex(
            self.soundtrack_version.findData("jukeboxmusic")
        )
        self.soundtrack_version.blockSignals(False)
        self.offset = 0
        target = self._soundtrack_album_rows["jukeboxmusic"][0].row_id
        if selected is not None and selected.fields.get("logical_track_number"):
            logical_track = int(selected.fields["logical_track_number"])
            target = self._soundtrack_album_rows["jukeboxmusic"][
                max(0, min(14, logical_track - 1))
            ].row_id
        self._update_audio_workspace_controls()
        self.refresh(target)

    def _soundtrack_version_changed(self, _index: int) -> None:
        if not self._soundtrack_album_mode or self._audio_review_mode:
            return
        selected = self._selected_row()
        logical_track = int(selected.fields.get("logical_track_number", 1)) if selected else 1
        bank_name = str(self.soundtrack_version.currentData() or "jukeboxmusic")
        rows = self._soundtrack_album_rows.get(bank_name, ())
        if not rows:
            return
        self.offset = 0
        self.refresh(rows[max(0, min(14, logical_track - 1))].row_id)

    def refresh(self, preserve_row_id: str | None = None) -> None:
        if self.model is None:
            self._update_audio_workspace_controls()
            self._update_buttons()
            return
        if self.audio_mode:
            # A shell-level Undo/Revert can change annotation content without
            # touching the filter widgets. Every explicit refresh therefore
            # invalidates only the aggregate result cache; row selections do
            # not call refresh and retain the fast path.
            self._matching_audio_cache_key = None
            self._matching_audio_cache = ()
        query_token = (
            self._current_audio_query_token()
            if self.audio_mode
            and not self._audio_review_mode
            and not self._soundtrack_album_mode
            else None
        )
        if query_token is not None:
            self._timer.stop()
        selected_before = self._selected_row()
        wanted_row_id = preserve_row_id or (
            selected_before.row_id if selected_before is not None else None
        )
        if self._audio_review_mode:
            active_model = PagedModel(self._shortlisted_audio_rows())
            page_arguments: dict[str, object] = {}
        elif self._soundtrack_album_mode:
            bank_name = str(
                self.soundtrack_version.currentData() or "jukeboxmusic"
            )
            active_model = PagedModel(
                self._soundtrack_album_rows.get(bank_name, ())
            )
            page_arguments = {}
        elif self.audio_mode:
            active_model = PagedModel(
                self._audio_filtered_rows(), self.model.findings
            )
            page_arguments = {}
        else:
            active_model = self.model
            page_arguments = {
                "search": self.search.text(),
                "kinds": self.kind_filter.currentData(),
                "roles": None,
                "sources": None,
            }
        page = active_model.page(
            **page_arguments,
            offset=self.offset,
            limit=PAGE_SIZE,
        )
        if page.total and self.offset >= page.total:
            self.offset = max(0, ((page.total - 1) // PAGE_SIZE) * PAGE_SIZE)
            page = active_model.page(
                **page_arguments,
                offset=self.offset,
                limit=PAGE_SIZE,
            )
        self._visible = {row.row_id: row for row in page.items}
        self.table.setRowCount(len(page.items))
        for index, row in enumerate(page.items):
            if self.audio_mode:
                values = self._decorated_audio_table_values(row)
            elif self.text_mode:
                allocation = self._text_allocations.get(row.row_id)
                modified = row.row_id in self.facade.modified_asset_ids
                title = (
                    self.facade.localization_text_value(row.row_id)
                    if allocation is not None
                    else row.title
                )
                status = (
                    "● Modified"
                    if modified
                    else "Editable"
                    if allocation is not None and bool(getattr(allocation, "editable"))
                    else "Protected allocation"
                    if allocation is not None
                    else "Read-only reference"
                )
                kind_label = {
                    "localization_pool_string": "TXT string",
                    "string_bank_pool_string": "STRG string",
                    "localization_record": "TXT reference",
                }.get(row.kind, row.kind.replace("_", " "))
                values = (
                    title,
                    kind_label,
                    row.subtitle,
                    status,
                )
            elif self.roster_mode:
                modified_count = self._roster_modified_count(row)
                rating_modified_count = self._player_rating_modified_count(row)
                mapped_fields = self._roster_identity_fields(row)
                modified_identity_ids = self._roster_modified_identity_asset_ids(row)
                editable_count = sum(
                    self._roster_field_product_editable(row, field_name)
                    for field_name, _asset_id, _metadata in mapped_fields
                )
                modified_editable_ids = {
                    asset_id
                    for field_name, asset_id, _metadata in mapped_fields
                    if asset_id in modified_identity_ids
                    and self._roster_field_product_editable(row, field_name)
                }
                locked_count = len(mapped_fields) - editable_count
                if row.kind == "player":
                    status_parts: list[str] = []
                    if modified_identity_ids:
                        identity_count = len(modified_identity_ids)
                        status_parts.append(
                            f"● Modified name allocation"
                            f"{'s' if identity_count != 1 else ''} ({identity_count})"
                        )
                    if rating_modified_count:
                        status_parts.append(
                            f"● Modified ratings ({rating_modified_count})"
                        )
                    if self._player_position_modified(row):
                        status_parts.append("● Modified position")
                    if status_parts:
                        status = " · ".join(status_parts)
                    else:
                        status = "Position + 31 base ratings editable · " + (
                            "Player names editable"
                            if editable_count
                            else "Player names locked"
                        )
                elif modified_count:
                    status = (
                        f"● Modified team-name allocation"
                        f"{'s' if len(modified_identity_ids) != 1 else ''} "
                        f"({len(modified_identity_ids)})"
                        if len(modified_editable_ids) == len(modified_identity_ids)
                        else f"● Legacy edit ({modified_count}) · Build locked"
                    )
                elif editable_count:
                    status = "Team name editable" + (
                        f" · {locked_count} mapped field"
                        f"{'s' if locked_count != 1 else ''} locked"
                        if locked_count
                        else ""
                    )
                elif mapped_fields:
                    status = f"Mapped names ({len(mapped_fields)}) · Runtime locked"
                else:
                    status = "Read-only"
                values = (
                    self._roster_display_title(row),
                    row.kind.replace("_", " "),
                    self._roster_display_subtitle(row),
                    status,
                )
            else:
                values = (
                    row.title,
                    row.kind.replace("_", " "),
                    row.subtitle,
                )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.row_id)
                tooltip = value
                if self.audio_mode and column == 0:
                    annotation = None
                    if self._audio_row_is_annotatable(row):
                        try:
                            annotation = self._annotation_for(row.row_id)
                        except Exception:
                            annotation = None
                    if annotation is not None:
                        custom_title, note = self._annotation_text(annotation)
                        tooltip = (
                            f"Custom title: {custom_title or '(game label retained)'}\n"
                            f"Game/catalog title: {row.title}\n"
                            f"Stable cue ID: {row.row_id}\n"
                            f"Note: {note or '(none)'}"
                        )
                item.setToolTip(_literal_tooltip(tooltip))
                self.table.setItem(index, column, item)
        total_pages = max(1, (page.total + PAGE_SIZE - 1) // PAGE_SIZE)
        current_page = min(total_pages, self.offset // PAGE_SIZE + 1)
        if self._audio_review_mode:
            self.count.setText(f"{page.total:,} shortlisted sounds")
        elif self._soundtrack_album_mode:
            version = (
                "stereo masters"
                if self.soundtrack_version.currentData() == "jukeboxmusic"
                else "mono companions"
            )
            self.count.setText(f"{page.total:,} soundtrack tracks · {version}")
        else:
            self.count.setText(f"{page.total:,} decoded rows")
        self.page.setText(f"Page {current_page} of {total_pages}")
        if (
            query_token is not None
            and query_token == self._current_audio_query_token()
        ):
            self._applied_audio_query_token = query_token
            self._applied_audio_offset = self.offset
            self._applied_audio_count_text = self.count.text()
            self._applied_audio_page_text = self.page.text()
            self._applied_audio_previous_available = page.previous_offset is not None
            self._applied_audio_next_available = page.next_offset is not None
        pagination_ready = not self.audio_mode or self._audio_pagination_ready()
        self._sync_inspector_pagination(
            previous_available=page.previous_offset is not None,
            next_available=page.next_offset is not None,
            ready=pagination_ready,
        )
        if self.audio_mode:
            rows_ready = bool(
                self.model is not None
                and (
                    self._audio_review_mode
                    or self._soundtrack_album_mode
                    or self._audio_catalog_query_is_current()
                )
            )
            # Never silent-gray: stay clickable; clear disableReason when ready.
            self.export_rows_button.setEnabled(True)
            if rows_ready:
                rows_tip = (
                    "Save every row matching the current search and filters as "
                    "useful JSON or CSV."
                )
                self.export_rows_button.setToolTip(rows_tip)
                self.export_rows_button.setProperty("disableReason", "")
            else:
                rows_tip = (
                    "Wait for search/filters to finish updating results, then "
                    "export decoded rows."
                    if self.model is not None
                    else "Load a supported APF game first, then export decoded "
                    "inspector rows."
                )
                self.export_rows_button.setToolTip(rows_tip)
                self.export_rows_button.setProperty("disableReason", rows_tip)
        self._update_matching_audio_action()
        self._update_audio_shortlist_actions()
        self._update_audio_workspace_controls()
        if page.items:
            selected_index = next(
                (
                    index
                    for index, row in enumerate(page.items)
                    if row.row_id == wanted_row_id
                ),
                0,
            )
            self.table.selectRow(selected_index)
            # Replacing the model underneath an already-selected table row may
            # not emit itemSelectionChanged. Always refresh the detail pane so
            # a filtered soundtrack row can never inherit stale AUDO details.
            self._selection_changed()
        else:
            self.detail_title.setText("No decoded rows match")
            self.detail_subtitle.setText("")
            self.detail_fields.setPlainText("")
            self._populate_annotation_editor(None)
            self.export_audio_button.setVisible(False)
            self.export_bank_button.setVisible(False)
            self.export_external_bank_button.setVisible(False)
            self.export_external_bank_button.setEnabled(True)
            self.export_external_bank_button.setToolTip('Select an external bank row first.')
            self.export_external_bank_button.setProperty("disableReason", 'Select an external bank row first.')
            tip = "Select a playable sound row first."
            self.play_audio_button.setEnabled(True)
            self.play_audio_button.setToolTip(tip)
            self.play_audio_button.setProperty("disableReason", tip)
            self._cancel_audio_waveform()
            self._configure_audio_waveform(None)
            self._configure_audio_replacement(None)
            self._clear_text_editor("No editable allocation is selected.")
            self._clear_roster_editor("No roster record is selected.")
            self._update_audio_shortlist_actions()

    @staticmethod
    def _audio_table_values(row: InspectorRow) -> tuple[str, ...]:
        fields = row.fields
        role = str(fields.get("role_label") or "Unclassified")
        if row.kind == "external_bank":
            linked_labels = fields.get("linked_role_labels", ())
            if isinstance(linked_labels, (list, tuple)) and linked_labels:
                role = " / ".join(str(value) for value in linked_labels)
            audio_format = "Raw external XMA1 bank"
            length = _human_bytes(int(fields.get("encoded_size", 0)))
            status = "Raw .bin export · not playable"
            location = f"O{int(fields.get('outer_table_index', 0))}"
        elif row.kind == "ausb_bank":
            audio_format = "AUSB → XMA1"
            length = f"{int(fields.get('substream_count', 0)):,} sounds"
            status = (
                "Bank ZIP available"
                if 0 < int(fields.get("substream_count", 0)) <= 256
                else "Individual export"
            )
            location = (
                f"O{int(fields.get('outer_table_index', 0))} / "
                f"I{int(fields.get('inner_file_index', 0))}"
            )
        else:
            rate = fields.get("sample_rate")
            channels = fields.get("derived_channel_count")
            rate_text = f"{float(rate) / 1000:g} kHz" if rate else "rate unknown"
            channel_text = (
                "mono"
                if channels == 1
                else "stereo"
                if channels == 2
                else "layout unknown"
            )
            audio_format = f"XMA1 · {rate_text} · {channel_text}"
            duration = fields.get(
                "duration_seconds", fields.get("duration_seconds_candidate")
            )
            length = _duration_text(duration)
            status = (
                "Editable · WAV/Play when verified"
                if row.kind == "audo"
                else "Editable · runtime unproved"
                if row.kind == "ausb_substream"
                else "XMA available · WAV/Play when verified"
            )
            location = (
                f"O{int(fields.get('outer_table_index', 0))}/"
                f"I{int(fields.get('inner_file_index', 0))}"
            )
        if fields.get("substream_index") is not None:
            location += f"/S{int(fields['substream_index']):05d}"
        sound_title = row.title
        if fields.get("logical_track_number") is not None:
            sound_title = f"Track {int(fields['logical_track_number']):02d}"
        return sound_title, role, audio_format, length, location, status

    def _decorated_audio_table_values(
        self, row: InspectorRow
    ) -> tuple[str, ...]:
        values = self._audio_table_values(row)
        annotation = None
        if self._audio_row_is_annotatable(row):
            try:
                annotation = self._annotation_for(row.row_id)
            except Exception:
                annotation = None
        if annotation is not None:
            custom_title, _note = self._annotation_text(annotation)
            values = (
                f"✎ {custom_title or values[0]}",
                *values[1:-1],
                f"✎ Labeled · {values[-1]}",
            )
        if row.row_id in frozenset(
            getattr(self.facade, "modified_asset_ids", frozenset())
        ):
            values = (*values[:-1], f"● Modified · {values[-1]}")
        if row.row_id in self._audio_shortlist:
            values = (*values[:-1], f"★ Selected · {values[-1]}")
        return values

    def _move(self, delta: int) -> None:
        button = self.previous if delta < 0 else self.next
        reason = str(button.property("disableReason") or "").strip()
        if reason:
            # Prefer status-style teach over modal hang risk under offscreen tests.
            self.page.setText(reason)
            self.page.setToolTip(reason)
            return
        if self.audio_mode and not self._audio_pagination_ready():
            return
        self.offset = max(0, self.offset + delta)
        self.refresh()

    def _selection_changed(self) -> None:
        self._stop_audio()
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self._populate_annotation_editor(None)
            self._update_audio_shortlist_actions()
            return
        item = self.table.item(rows[0].row(), 0)
        row = self._visible.get(item.data(Qt.UserRole)) if item else None
        if row is None:
            return
        if self.audio_mode and row.row_id != self._waveform_selected_row_id:
            self._cancel_audio_waveform()
            self._configure_audio_waveform(row)
        annotation = None
        if self.audio_mode and self._audio_row_is_annotatable(row):
            try:
                annotation = self._annotation_for(row.row_id)
            except Exception:
                annotation = None
        self._populate_annotation_editor(row if self.audio_mode else None)
        if self.text_mode:
            allocation = self._text_allocations.get(row.row_id)
            if allocation is not None:
                bank_type = str(row.fields.get("bank_type") or "Text bank")
                pool_index = int(row.fields.get("pool_index", 0))
                self.detail_title.setText(
                    f"{bank_type} allocation  •  pool {pool_index:,}"
                )
            else:
                self.detail_title.setText("Read-only TXT reference")
        else:
            if self.audio_mode and annotation is not None:
                custom_title, _annotation_note = self._annotation_text(annotation)
                self.detail_title.setText(custom_title or row.title)
            else:
                self.detail_title.setText(
                    self._roster_display_title(row)
                    if self.roster_mode
                    else row.title
                )
        self.detail_subtitle.setText(
            row.subtitle
            if self.text_mode
            else (
                f"{self._roster_display_subtitle(row)}\n{row.row_id}"
                if self.roster_mode
                else (
                    f"Game/catalog title: {row.title}\n{row.subtitle}\n{row.row_id}"
                    if self.audio_mode and annotation is not None
                    else f"{row.subtitle}\n{row.row_id}"
                )
            )
        )
        document: dict[str, object] = dict(row.fields)
        if self.audio_mode and annotation is not None:
            custom_title, annotation_note = self._annotation_text(annotation)
            document["project_audio_annotation"] = {
                "custom_title": custom_title,
                "note": annotation_note,
                "game_catalog_title": row.title,
                "stable_cue_id": row.row_id,
                "build_effect": "project_metadata_only",
            }
        if self.roster_mode:
            current_values = {
                field_name: self.facade.roster_identity_value(asset_id)
                for field_name, asset_id, _metadata in self._roster_identity_fields(
                    row
                )
            }
            if current_values:
                document["current_session_identity_values"] = current_values
        if row.export_identity is not None:
            document["export_identity"] = {
                "exporter": row.export_identity.exporter,
                "coordinates": row.export_identity.coordinates,
                "suggested_basename": row.export_identity.suggested_basename,
                "supported_extensions": row.export_identity.supported_extensions,
            }
        if row.external_bank_identity is not None:
            identity = row.external_bank_identity
            document["external_bank_identity"] = {
                "external_filename": identity.external_filename,
                "outer_table_index": identity.outer_table_index,
                "name_id": f"0x{identity.name_id:08x}",
                "encoded_size": identity.encoded_size,
                "raw_asset_id": identity.raw_asset_id,
                "descriptor_coordinates": [
                    owner.coordinates for owner in identity.owners
                ],
            }
        self.detail_fields.setPlainText(
            json.dumps(document, indent=2, ensure_ascii=False, default=str)
        )
        self.export_audio_button.setVisible(row.export_identity is not None)
        self.export_audio_button.setEnabled(row.export_identity is not None)
        owns_external_bank = row.external_bank_identity is not None
        self.play_audio_button.setVisible(self.audio_mode and not owns_external_bank)
        self._update_audio_preview_action()
        bank_identities = self._selected_bank_identities(row)
        self.export_bank_button.setVisible(bool(bank_identities))
        self.export_bank_button.setEnabled(bool(bank_identities))
        self.export_external_bank_button.setVisible(owns_external_bank)
        self.export_external_bank_button.setEnabled(owns_external_bank)
        self._set_text_selection(row)
        self._set_roster_selection(row)
        self._configure_audio_replacement(row)
        self._update_audio_shortlist_actions()

    @staticmethod
    def _roster_identity_fields(
        row: InspectorRow,
    ) -> tuple[tuple[str, str, dict[str, object]], ...]:
        if row.kind not in {"player", "team"}:
            return ()
        editors = row.fields.get("identity_editor")
        if not isinstance(editors, dict):
            return ()
        allowed = (
            ("first_name", "last_name")
            if row.kind == "player"
            else (
                "display_name",
                "abbreviation",
                "secondary_abbreviation",
            )
        )
        result: list[tuple[str, str, dict[str, object]]] = []
        for field_name in allowed:
            metadata = editors.get(field_name)
            if not isinstance(metadata, dict):
                continue
            asset_id = metadata.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id:
                continue
            result.append((field_name, asset_id, metadata))
        return tuple(result)

    def _roster_field_product_editable(
        self, row: InspectorRow, field_name: str
    ) -> bool:
        if not self.roster_writes_enabled:
            return False
        for candidate, asset_id, _metadata in self._roster_identity_fields(row):
            if candidate == field_name:
                return bool(
                    self.facade.roster_identity_is_product_editable(asset_id)
                )
        return False

    def _roster_field_edit_scope(
        self, row: InspectorRow, field_name: str
    ) -> str | None:
        for candidate, asset_id, _metadata in self._roster_identity_fields(row):
            if candidate == field_name:
                scope = self.facade.roster_identity_edit_scope(asset_id)
                return scope if scope in {"player_name", "team_display_name"} else None
        return None

    @staticmethod
    def _roster_scope_label(scope: str | None) -> str:
        return {
            "player_name": "Player Name",
            "team_display_name": "Team Name",
        }.get(scope, "Roster Name")

    @staticmethod
    def _roster_field_label(field_name: str) -> str:
        return {
            "first_name": "First name",
            "last_name": "Last name",
            "display_name": "Team display name",
            "abbreviation": "Team abbreviation",
            "secondary_abbreviation": "Secondary abbreviation",
        }.get(field_name, field_name.replace("_", " ").title())

    def _roster_current_values(self, row: InspectorRow) -> dict[str, str]:
        return {
            field_name: self.facade.roster_identity_value(asset_id)
            for field_name, asset_id, _metadata in self._roster_identity_fields(row)
        }

    def _roster_display_title(self, row: InspectorRow) -> str:
        if not self.roster_mode:
            return row.title
        values = self._roster_current_values(row)
        if row.kind == "player":
            name = f"{values.get('first_name', '')} {values.get('last_name', '')}".strip()
            return name or f"Unnamed player {int(row.fields.get('player_index', 0)):04d}"
        if row.kind == "team":
            return values.get("display_name") or row.title
        return row.title

    def _roster_display_subtitle(self, row: InspectorRow) -> str:
        if not self.roster_mode:
            return row.subtitle
        if row.kind == "player":
            player_index = row.fields.get("player_index")
            editor = row.fields.get("position_editor")
            if (
                isinstance(player_index, int)
                and not isinstance(player_index, bool)
                and isinstance(editor, dict)
                and isinstance(editor.get("choices"), (list, tuple))
            ):
                try:
                    code = self.facade.player_position_value(player_index)
                    choice = editor["choices"][code]
                    abbreviation = str(choice["abbreviation"])
                except (IndexError, KeyError, TypeError, ValueError):
                    pass
                else:
                    return f"#{player_index:04d} · {abbreviation}"
            return row.subtitle
        if row.kind != "team":
            return row.subtitle
        values = self._roster_current_values(row)
        abbreviation = values.get("abbreviation") or str(
            row.fields.get("abbreviation", "")
        )
        slot_kind = str(row.fields.get("slot_kind", "team"))
        return f"{abbreviation} · {slot_kind}"

    def _roster_modified_count(self, row: InspectorRow) -> int:
        return (
            self._player_rating_modified_count(row)
            + int(self._player_position_modified(row))
            + len(self._roster_modified_identity_asset_ids(row))
        )

    def _roster_modified_identity_asset_ids(
        self, row: InspectorRow
    ) -> frozenset[str]:
        """Count a shared name allocation once, however many fields own it."""

        modified = self.facade.modified_asset_ids
        return frozenset(
            asset_id
            for _field_name, asset_id, _metadata in self._roster_identity_fields(row)
            if asset_id in modified
        )

    def _player_rating_modified_count(self, row: InspectorRow) -> int:
        if row.kind != "player":
            return 0
        player_index = row.fields.get("player_index")
        ratings = row.fields.get("base_ratings")
        if (
            isinstance(player_index, bool)
            or not isinstance(player_index, int)
            or not isinstance(ratings, (list, tuple))
        ):
            return 0
        modified = self.facade.modified_asset_ids
        return sum(
            f"apf:player-rating:{player_index}:{rating.get('id')}" in modified
            for rating in ratings
            if isinstance(rating, dict) and isinstance(rating.get("id"), str)
        )

    def _player_position_modified(self, row: InspectorRow) -> bool:
        if row.kind != "player":
            return False
        player_index = row.fields.get("player_index")
        return (
            isinstance(player_index, int)
            and not isinstance(player_index, bool)
            and f"apf:player-position:{player_index}"
            in self.facade.modified_asset_ids
        )

    def _set_roster_selection(self, row: InspectorRow) -> None:
        if not self.roster_mode:
            return
        self.base_ratings_panel.set_player(row)
        self.player_position_panel.set_player(row)
        if self.roster_detail_tabs is not None:
            ratings_available = row.kind == "player"
            self.roster_detail_tabs.setTabEnabled(1, ratings_available)
            self.roster_detail_tabs.setTabEnabled(2, ratings_available)
            if not ratings_available:
                self.roster_detail_tabs.setCurrentIndex(0)
        fields = self._roster_identity_fields(row)
        self.roster_field_combo.blockSignals(True)
        self.roster_field_combo.clear()
        for field_name, asset_id, metadata in fields:
            label = self._roster_field_label(field_name)
            label += (
                " · Editable"
                if self._roster_field_product_editable(row, field_name)
                else " · Locked"
            )
            if asset_id in self.facade.modified_asset_ids:
                label = f"● {label}"
            self.roster_field_combo.addItem(label, field_name)
            item_index = self.roster_field_combo.count() - 1
            self.roster_field_combo.setItemData(
                item_index,
                (
                    f"{asset_id} · maximum "
                    f"{int(metadata.get('maximum_characters', 0))} characters"
                ),
                Qt.ToolTipRole,
            )
        self.roster_field_combo.blockSignals(False)
        self.roster_field_combo.setEnabled(bool(fields))

        if row.kind == "player":
            self.roster_boundary_note.setText(
                (
                    "This on-disc row editor handles names, all 31 native base "
                    "ratings, and 17 exact position choices in separate tabs. "
                    "Jersey number remains read-only in this on-disc row. For "
                    "raw Roster.ROS "
                    "or a verified STFS extraction, open Save Players: jersey "
                    "number, tier, abilities, depth, equipment/appearance, all "
                    "15 fixed-allocation text fields, and safe populated-slot "
                    "membership swaps are authorable there."
                )
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
            self.roster_boundary_note.setToolTip(
                "Dan CODEX rendered in player selection and the Star Card. The "
                "token-preserving Speed candidate also loaded normally, but APF "
                "showed stars rather than a numeric rating readout. Save Players "
                "uses the separate APFe/raw-save packed-record contract and emits "
                "a byte-verification receipt. No consumer-backed Overall formula "
                "is claimed."
            )
            self.roster_boundary_note.setVisible(True)
        elif row.kind == "team":
            self.roster_boundary_note.setText(
                (
                    f"Team display name · Editable. "
                    f"{TEAM_DISPLAY_NAME_EDIT_SCOPE_MESSAGE} Team abbreviation "
                    "and secondary abbreviation remain locked."
                )
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
            self.roster_boundary_note.setToolTip(
                "See docs/product/"
                "APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md"
            )
            self.roster_boundary_note.setVisible(True)
        else:
            boundary = (
                "Stadium rows are read-only; this bounded writer owns only "
                "player and team identity allocations."
                if row.kind == "stadium"
                else "Roster-membership rows are read-only; team assignment and "
                "depth-chart ownership are not mapped safely."
                if row.kind == "membership"
                else "This roster record is read-only."
            )
            self.roster_boundary_note.setText(boundary)
            self.roster_boundary_note.setToolTip("")
            self.roster_boundary_note.setVisible(True)

        if fields:
            self.roster_field_combo.setCurrentIndex(0)
            self._roster_field_changed()
        else:
            self.roster_name_editor.blockSignals(True)
            self.roster_name_editor.clear()
            self.roster_name_editor.blockSignals(False)
            self.roster_name_editor.setEnabled(False)
            self._selected_roster_alias_asset_id = None
            self._selected_roster_alias_labels = ()
            self.roster_allocation_note.setText(
                "No writable roster-name allocation belongs to this row."
            )
            tip = "No writable roster-name allocation belongs to this row."
            self.apply_roster_name_button.setEnabled(True)
            self.apply_roster_name_button.setToolTip(tip)
            self.apply_roster_name_button.setProperty("disableReason", tip)
            self.revert_roster_name_button.setEnabled(True)
            self.revert_roster_name_button.setToolTip(tip)
            self.revert_roster_name_button.setProperty("disableReason", tip)
            self.roster_aliases_button.setText("View affected fields…")
            self.roster_aliases_button.setToolTip("")
            self.roster_aliases_button.setEnabled(True)
            self.roster_aliases_button.setToolTip('Select a roster identity field first.')
            self.roster_aliases_button.setProperty("disableReason", 'Select a roster identity field first.')

    def _selected_roster_field(
        self,
    ) -> tuple[InspectorRow, str, str, object, dict[str, object]] | None:
        if not self.roster_mode:
            return None
        row = self._selected_row()
        field_name = self.roster_field_combo.currentData()
        if row is None or not isinstance(field_name, str):
            return None
        for candidate, asset_id, metadata in self._roster_identity_fields(row):
            if candidate != field_name:
                continue
            allocation = self._roster_allocations.get(asset_id)
            if allocation is None:
                return None
            return row, field_name, asset_id, allocation, metadata
        return None

    @staticmethod
    def _roster_alias_owner_labels(
        metadata: dict[str, object], allocation: object
    ) -> tuple[str, ...]:
        """Return every locally decoded owner label without truncating aliases."""

        described = metadata.get("known_alias_owners")
        if isinstance(described, (list, tuple)):
            labels = tuple(
                str(owner.get("label", "")).strip()
                for owner in described
                if isinstance(owner, dict) and str(owner.get("label", "")).strip()
            )
            if labels:
                return labels
        labels: list[str] = []
        for owner in tuple(getattr(allocation, "known_owners", ())):
            owner_id = getattr(owner, "owner_id", None)
            if isinstance(owner_id, str) and owner_id:
                labels.append(owner_id)
                continue
            entity_kind = str(getattr(owner, "entity_kind", "owner")).title()
            entity_index = getattr(owner, "entity_index", "?")
            field = str(getattr(owner, "field", "field")).replace("_", " ")
            labels.append(f"{entity_kind} {entity_index} · {field}")
        return tuple(labels)

    @staticmethod
    def _roster_locked_field_reason(
        row: InspectorRow,
        field_name: str,
        allocation: object,
    ) -> str:
        limit = int(getattr(allocation, "maximum_utf16_units"))
        if limit <= 0:
            return (
                "This source allocation has zero writable characters, so it "
                "cannot accept a replacement."
            )
        if field_name in {"abbreviation", "secondary_abbreviation"}:
            return (
                "Team abbreviations remain locked because neither abbreviation "
                "consumer has its own positive runtime spot check."
            )
        if row.kind == "player" and field_name in {"first_name", "last_name"}:
            return (
                "Only nonempty, positive-capacity player first/last-name "
                "allocations with exclusively player-name owners are editable."
            )
        return ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE

    def _roster_field_changed(self, _index: int = -1) -> None:
        if not self.roster_mode:
            return
        selected = self._selected_roster_field()
        if selected is None:
            self.roster_name_editor.blockSignals(True)
            self.roster_name_editor.clear()
            self.roster_name_editor.blockSignals(False)
            self.roster_name_editor.setEnabled(False)
            self._selected_roster_alias_asset_id = None
            self._selected_roster_alias_labels = ()
            self.roster_allocation_note.setText(
                "The selected field has no matching safe allocation; no write is available."
            )
            tip = (
                "The selected field has no matching safe allocation; no write is available."
            )
            self.apply_roster_name_button.setEnabled(True)
            self.apply_roster_name_button.setToolTip(tip)
            self.apply_roster_name_button.setProperty("disableReason", tip)
            self.revert_roster_name_button.setEnabled(True)
            self.revert_roster_name_button.setToolTip(tip)
            self.revert_roster_name_button.setProperty("disableReason", tip)
            self.roster_aliases_button.setText("View affected fields…")
            self.roster_aliases_button.setToolTip("")
            self.roster_aliases_button.setEnabled(True)
            self.roster_aliases_button.setToolTip('Select a roster identity field first.')
            self.roster_aliases_button.setProperty("disableReason", 'Select a roster identity field first.')
            return
        row, field_name, asset_id, allocation, metadata = selected
        current = self.facade.roster_identity_value(asset_id)
        editable = bool(getattr(allocation, "editable"))
        product_editable = self._roster_field_product_editable(row, field_name)
        edit_scope = self._roster_field_edit_scope(row, field_name)
        scope_label = self._roster_scope_label(edit_scope)
        limit = int(getattr(allocation, "maximum_utf16_units"))
        owner_count = int(getattr(allocation, "known_owner_count"))
        note = str(getattr(allocation, "note"))
        owner_labels = self._roster_alias_owner_labels(metadata, allocation)
        disclosed_count = len(owner_labels)
        self._selected_roster_alias_asset_id = asset_id
        self._selected_roster_alias_labels = owner_labels
        affected_label = "field" if disclosed_count == 1 else "fields"
        self.roster_aliases_button.setText(
            f"View {disclosed_count} affected {affected_label}…"
            if disclosed_count
            else "No affected fields mapped"
        )
        owner_tooltip = (
            f"Allocation {asset_id} affects these mapped roster fields:\n• "
            + "\n• ".join(owner_labels)
            if owner_labels
            else "No exact roster-field owners have been mapped for this allocation."
        )
        self.roster_aliases_button.setToolTip(owner_tooltip)
        self.roster_aliases_button.setEnabled(bool(owner_labels))
        self.roster_name_editor.blockSignals(True)
        self.roster_name_editor.setText(current)
        self.roster_name_editor.blockSignals(False)
        self.roster_name_editor.setEnabled(editable and limit > 0)
        self.roster_name_editor.setReadOnly(not product_editable)
        self.apply_roster_name_button.setText(
            f"Replace {scope_label}" if product_editable else "Replace (Locked)"
        )
        self.roster_editor_label.setText(
            (
                "Replacement "
                if product_editable
                else "Read-only "
            )
            + self._roster_field_label(field_name).casefold()
        )
        allocation_text = (
            f"Allocation {asset_id} · Maximum: {limit} UTF-16 characters · "
            f"Known affected fields: {disclosed_count}"
        )
        if owner_count != disclosed_count:
            allocation_text += f" of {owner_count} decoded owners"
        allocation_text += f". {note}"
        if disclosed_count > 1:
            allocation_text += (
                f"\nShared-allocation warning: one replacement changes all "
                f"{disclosed_count} affected fields together. Use the review "
                "button for the exact list."
            )
        if product_editable:
            allocation_text += (
                f"\nRuntime-proved {scope_label.casefold()} route; builds preserve "
                "the retail H7A token layout wherever it remains semantically valid."
            )
        else:
            allocation_text += "\n" + (
                self._roster_locked_field_reason(row, field_name, allocation)
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
        self.roster_allocation_note.setText(allocation_text)
        self.roster_allocation_note.setToolTip(
            allocation_text + "\n\n" + owner_tooltip
        )
        modified = asset_id in self.facade.modified_asset_ids
        self.revert_roster_name_button.setText(
            f"Revert {scope_label}"
            if edit_scope is not None
            else "Revert Locked Edit"
            if modified
            else "Revert (Locked)"
        )
        if modified:
            revert_tip = "Restore this one shared name allocation to the source value."
            revert_block = ""
        else:
            revert_tip = revert_block = "This name allocation is still original."
        self.revert_roster_name_button.setEnabled(True)
        self.revert_roster_name_button.setToolTip(revert_tip)
        self.revert_roster_name_button.setProperty("disableReason", revert_block)
        self._roster_editor_changed()

    def _build_roster_alias_dialog(self) -> QDialog:
        """Build a bounded, read-only disclosure of every known alias owner."""

        asset_id = self._selected_roster_alias_asset_id or "No allocation selected"
        owner_labels = self._selected_roster_alias_labels
        dialog = QDialog(self)
        dialog.setObjectName("rosterAliasOwnersDialog")
        dialog.setWindowTitle("Affected roster fields")
        dialog.setModal(True)
        dialog.resize(720, 580)
        dialog.setMinimumSize(620, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("Every field changed by this name allocation")
        title.setObjectName("panelTitle")
        explanation = QLabel(
            f"<b>{asset_id}</b> is shared by {len(owner_labels):,} mapped "
            f"roster {'field' if len(owner_labels) == 1 else 'fields'}. Replacing "
            "the name changes every item in this list together; Revert restores "
            "the whole shared allocation."
        )
        explanation.setTextFormat(Qt.RichText)
        explanation.setWordWrap(True)
        owners = QPlainTextEdit()
        owners.setObjectName("rosterAliasOwners")
        owners.setAccessibleName("Every roster field affected by this allocation")
        owners.setReadOnly(True)
        owners.setLineWrapMode(QPlainTextEdit.NoWrap)
        owners.setMinimumHeight(360)
        owners.setPlainText(
            "\n".join(owner_labels)
            if owner_labels
            else "No exact mapped roster fields are available."
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.setObjectName("rosterAliasOwnersButtons")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(owners, 1)
        layout.addWidget(buttons)
        return dialog

    def _show_roster_alias_owners(self) -> None:
        if not self._selected_roster_alias_labels:
            return
        dialog = self._build_roster_alias_dialog()
        dialog.exec_()
        dialog.deleteLater()

    def _clear_roster_editor(self, message: str) -> None:
        if not self.roster_mode:
            return
        self.base_ratings_panel.clear_player()
        self.player_position_panel.clear_player()
        self.roster_field_combo.blockSignals(True)
        self.roster_field_combo.clear()
        self.roster_field_combo.blockSignals(False)
        self.roster_field_combo.setEnabled(False)
        self.roster_name_editor.blockSignals(True)
        self.roster_name_editor.clear()
        self.roster_name_editor.blockSignals(False)
        self.roster_name_editor.setEnabled(False)
        self._selected_roster_alias_asset_id = None
        self._selected_roster_alias_labels = ()
        self.roster_allocation_note.setText(message)
        self.roster_boundary_note.clear()
        self.roster_boundary_note.setVisible(False)
        tip = (
            "Select a roster player/team identity field first. Replace/Revert "
            "stay clickable so blocked states explain themselves."
        )
        self.apply_roster_name_button.setEnabled(True)
        self.apply_roster_name_button.setToolTip(tip)
        self.apply_roster_name_button.setProperty("disableReason", tip)
        self.revert_roster_name_button.setEnabled(True)
        self.revert_roster_name_button.setToolTip(tip)
        self.revert_roster_name_button.setProperty("disableReason", tip)
        self.roster_aliases_button.setText("View affected fields…")
        self.roster_aliases_button.setToolTip("")
        self.roster_aliases_button.setEnabled(True)
        self.roster_aliases_button.setToolTip('Select a roster identity field first.')
        self.roster_aliases_button.setProperty("disableReason", 'Select a roster identity field first.')
        if self.roster_detail_tabs is not None:
            self.roster_detail_tabs.setCurrentIndex(0)
            self.roster_detail_tabs.setTabEnabled(1, False)
            self.roster_detail_tabs.setTabEnabled(2, False)

    def _roster_editor_changed(self, _value: str = "") -> None:
        if not self.roster_mode:
            return
        selected = self._selected_roster_field()
        if selected is None:
            tip = "Select a roster identity field first."
            self.apply_roster_name_button.setEnabled(True)
            self.apply_roster_name_button.setToolTip(tip)
            self.apply_roster_name_button.setProperty("disableReason", tip)
            return
        row, field_name, asset_id, allocation, _metadata = selected
        value = self.roster_name_editor.text()
        limit = int(getattr(allocation, "maximum_utf16_units"))
        error = ""
        try:
            units = len(value.encode("utf-16be")) // 2
        except UnicodeEncodeError:
            units = limit + 1
            error = "This name contains a Unicode value the game cannot store."
        if limit <= 0:
            error = (
                "This source allocation has zero writable characters; it "
                "cannot store a replacement."
            )
        elif "\0" in value:
            error = "Roster names cannot contain a NUL character."
        elif units > limit and not error:
            error = (
                f"This name needs {units} UTF-16 characters; the allocation limit "
                f"is {limit}."
            )
        current = self.facade.roster_identity_value(asset_id)
        product_editable = self._roster_field_product_editable(row, field_name)
        valid = (
            not error
            and bool(getattr(allocation, "editable"))
            and product_editable
        )
        if valid and value != current:
            tip = (
                f"Replace this {self._roster_field_label(field_name).casefold()} "
                f"using {units} of {limit} UTF-16 characters as one Undo step."
            )
            block = ""
        elif not product_editable:
            tip = block = (
                self._roster_locked_field_reason(row, field_name, allocation)
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
        elif error:
            tip = block = error
        else:
            tip = block = "No change from the current staged/source name."
        self.apply_roster_name_button.setEnabled(True)
        self.apply_roster_name_button.setToolTip(tip)
        self.apply_roster_name_button.setProperty("disableReason", block)
        color = "#39d98a" if valid else "#ffb65c" if not product_editable else "#ff6b7a"
        self.roster_editor_label.setText(
            (
                "Read-only "
                if not product_editable
                else "Replacement "
            )
            + f"{self._roster_field_label(field_name).casefold()} · "
            f"{units}/{limit} UTF-16 characters"
        )
        self.roster_editor_label.setStyleSheet(f"color: {color};")

    def _apply_roster_identity(self) -> None:
        reason = str(
            self.apply_roster_name_button.property("disableReason") or ""
        ).strip()
        if reason:
            # Teach via allocation note (tooltip already carries disableReason).
            # Avoid modal QMessageBox so headless tests and quick rejections stay snappy.
            self.roster_allocation_note.setText(reason)
            return
        selected = self._selected_roster_field()
        if selected is None:
            return
        row, field_name, asset_id, _allocation, _metadata = selected
        value = self.roster_name_editor.text()
        edit_scope = self._roster_field_edit_scope(row, field_name)
        scope_label = self._roster_scope_label(edit_scope).casefold()
        self.run_task(
            f"Replacing APF {scope_label}",
            lambda progress: self.facade.replace_roster_identity_text(
                asset_id, value, progress
            ),
            lambda _result: self._roster_mutation_complete(
                row.row_id, field_name
            ),
            True,
        )

    def _revert_roster_identity(self) -> None:
        reason = str(
            self.revert_roster_name_button.property("disableReason") or ""
        ).strip()
        if reason:
            self.roster_allocation_note.setText(reason)
            return
        selected = self._selected_roster_field()
        if selected is None:
            return
        row, field_name, asset_id, _allocation, _metadata = selected
        edit_scope = self._roster_field_edit_scope(row, field_name)
        scope_label = self._roster_scope_label(edit_scope).casefold()
        self.run_task(
            f"Reverting APF {scope_label}",
            lambda progress: self.facade.revert(asset_id, progress),
            lambda _result: self._roster_mutation_complete(
                row.row_id, field_name
            ),
            True,
        )

    def _roster_mutation_complete(self, row_id: str, field_name: str) -> None:
        self.refresh(row_id)
        # QTableWidget can retain the same selected index while every cell is
        # repopulated, in which case Qt emits no selection-change signal.  Run
        # the row binding explicitly so the detail title and current values
        # never lag behind the successful edit.
        self._selection_changed()
        index = self.roster_field_combo.findData(field_name)
        if index >= 0:
            self.roster_field_combo.setCurrentIndex(index)
            self._roster_field_changed()
        self.modifiedChanged.emit()

    def _apply_player_base_rating(
        self, player_index: int, field_id: str, value: int
    ) -> None:
        row = self._selected_row()
        if (
            row is None
            or row.kind != "player"
            or row.fields.get("player_index") != player_index
            or not 0 <= value <= 99
        ):
            return
        self.run_task(
            "Applying exact APF base rating",
            lambda progress: self.facade.replace_player_base_rating(
                player_index, field_id, value, progress
            ),
            lambda _result: self._player_rating_mutation_complete(
                row.row_id, field_id
            ),
            True,
        )

    def _revert_player_base_rating(
        self, player_index: int, field_id: str
    ) -> None:
        row = self._selected_row()
        if (
            row is None
            or row.kind != "player"
            or row.fields.get("player_index") != player_index
        ):
            return
        asset_id = f"apf:player-rating:{player_index}:{field_id}"
        if asset_id not in self.facade.modified_asset_ids:
            return
        self.run_task(
            "Reverting exact APF base rating",
            lambda progress: self.facade.revert(asset_id, progress),
            lambda _result: self._player_rating_mutation_complete(
                row.row_id, field_id
            ),
            True,
        )

    def _player_rating_mutation_complete(
        self, row_id: str, field_id: str
    ) -> None:
        self.refresh(row_id)
        # Rebinding is explicit because repopulating a QTableWidget may retain
        # the same row index without emitting itemSelectionChanged.
        self._selection_changed()
        self.base_ratings_panel.select_field(field_id)
        self.modifiedChanged.emit()

    def _apply_player_position(self, player_index: int, value: int) -> None:
        row = self._selected_row()
        if (
            row is None
            or row.kind != "player"
            or row.fields.get("player_index") != player_index
            or isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 16
        ):
            return
        self.run_task(
            "Applying exact APF player position",
            lambda progress: self.facade.replace_player_position(
                player_index, value, progress
            ),
            lambda _result: self._player_position_mutation_complete(
                row.row_id, value
            ),
            True,
        )

    def _revert_player_position(self, player_index: int) -> None:
        row = self._selected_row()
        asset_id = f"apf:player-position:{player_index}"
        if (
            row is None
            or row.kind != "player"
            or row.fields.get("player_index") != player_index
            or asset_id not in self.facade.modified_asset_ids
        ):
            return
        self.run_task(
            "Reverting exact APF player position",
            lambda progress: self.facade.revert(asset_id, progress),
            lambda _result: self._player_position_mutation_complete(
                row.row_id, None
            ),
            True,
        )

    def _player_position_mutation_complete(
        self, row_id: str, preserve_code: int | None
    ) -> None:
        self.refresh(row_id)
        self._selection_changed()
        self.player_position_panel.refresh_value(preserve_code)
        self.modifiedChanged.emit()

    def _set_text_selection(self, row: InspectorRow) -> None:
        if not self.text_mode:
            return
        allocation = self._text_allocations.get(row.row_id)
        if allocation is None:
            self._clear_text_editor(
                "Reference row. Select a Text Pool String to edit its "
                "shared underlying allocation."
            )
            return
        current = self.facade.localization_text_value(row.row_id)
        self.text_editor.blockSignals(True)
        self.text_editor.setPlainText(current)
        self.text_editor.blockSignals(False)
        editable = bool(getattr(allocation, "editable"))
        self.text_editor.setEnabled(editable)
        references = int(getattr(allocation, "reference_count"))
        limit = int(getattr(allocation, "maximum_utf16_units"))
        if editable:
            usage = (
                f"Used by {references} labels; one edit updates them all."
                if references > 1
                else "Used by one label."
                if references == 1
                else "No decoded record currently references this allocation."
            )
            self.text_limit.setText(f"{usage}  Maximum: {limit} UTF-16 units.")
        else:
            self.text_limit.setText("Protected allocation; this value is read-only.")
        self.text_limit.setToolTip(str(getattr(allocation, "note")))
        # Never silent-gray: Revert stays clickable; disableReason teaches
        # "still original" vs restore-one-allocation.
        staged = row.row_id in self.facade.modified_asset_ids
        if staged:
            revert_tip = "Restore this one string allocation to the source value."
            revert_block = ""
        else:
            revert_tip = revert_block = (
                "This allocation is still original — nothing staged to revert."
            )
        self.revert_text_button.setEnabled(True)
        self.revert_text_button.setToolTip(revert_tip)
        self.revert_text_button.setProperty("disableReason", revert_block)
        self._text_editor_changed()

    def _clear_text_editor(self, message: str) -> None:
        if not self.text_mode:
            return
        self.text_editor.blockSignals(True)
        self.text_editor.clear()
        self.text_editor.blockSignals(False)
        self.text_editor.setEnabled(False)
        self.text_limit.setText(message)
        tip = (
            "Select an editable string allocation first. Click still explains — "
            "Apply/Revert stay clickable."
        )
        self.apply_text_button.setEnabled(True)
        self.revert_text_button.setEnabled(True)
        self.apply_text_button.setToolTip(tip)
        self.revert_text_button.setToolTip(tip)
        self.apply_text_button.setProperty("disableReason", tip)
        self.revert_text_button.setProperty("disableReason", tip)

    def _text_editor_changed(self) -> None:
        if not self.text_mode:
            return
        row = self._selected_row()
        allocation = self._text_allocations.get(row.row_id) if row else None
        if allocation is None or not bool(getattr(allocation, "editable")):
            tip = (
                "Select an editable string allocation first. Non-editable rows "
                "are export/browse only."
            )
            self.apply_text_button.setEnabled(True)
            self.apply_text_button.setToolTip(tip)
            self.apply_text_button.setProperty("disableReason", tip)
            return
        value = self.text_editor.toPlainText()
        units = len(value.encode("utf-16be")) // 2
        limit = int(getattr(allocation, "maximum_utf16_units"))
        current = self.facade.localization_text_value(row.row_id)
        valid = "\0" not in value and units <= limit
        changed = value != current
        if valid and changed:
            tip = f"Apply {units} of {limit} UTF-16 units to this allocation."
            block = ""
        elif not valid:
            tip = block = (
                f"This text needs {units} UTF-16 units; the limit is {limit}."
                if units > limit
                else "Null characters are not allowed in this allocation."
            )
        else:
            tip = block = "No change from the current staged/source text."
        self.apply_text_button.setEnabled(True)
        self.apply_text_button.setToolTip(tip)
        self.apply_text_button.setProperty("disableReason", block)
        color = "#39d98a" if valid else "#ff6b7a"
        self.text_editor_label.setText(f"Replacement  •  {units}/{limit} UTF-16 units")
        self.text_editor_label.setStyleSheet(f"color: {color};")

    def _apply_text(self) -> None:
        reason = str(self.apply_text_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Cannot apply text yet",
                reason
                + "\n\nFix: select an editable string, stay under the UTF-16 unit "
                "limit, then Apply.",
            )
            return
        row = self._selected_row()
        if row is None or row.row_id not in self._text_allocations:
            return
        value = self.text_editor.toPlainText()
        self.run_task(
            "Applying APF text edit",
            lambda progress: self.facade.replace_localization_text(
                row.row_id, value, progress
            ),
            lambda _result: self._text_mutation_complete(row.row_id),
            True,
        )

    def _revert_text(self) -> None:
        reason = str(self.revert_text_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Nothing to revert",
                reason,
            )
            return
        row = self._selected_row()
        if row is None or row.row_id not in self._text_allocations:
            return
        self.run_task(
            "Reverting APF text edit",
            lambda progress: self.facade.revert(row.row_id, progress),
            lambda _result: self._text_mutation_complete(row.row_id),
            True,
        )

    def _export_text_sheet(self) -> None:
        reason = str(
            self.export_text_sheet_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export Text Sheet yet",
                reason,
            )
            return
        if not self.text_mode or self.model is None:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export private APF Text Sheet",
            str(Path.home() / "apf2k8-text-sheet.csv"),
            "APF Text Sheet (*.csv)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".csv")
        if path.suffix.casefold() != ".csv":
            QMessageBox.information(
                self,
                "Choose a CSV filename",
                "APF Text Sheets use the .csv extension.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Text Sheet exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting APF Text Sheet",
            lambda progress: self.facade.export_localization_text_sheet(
                path, progress
            ),
            self._text_sheet_export_complete,
            True,
        )

    def _text_sheet_export_complete(self, receipt: object) -> None:
        QMessageBox.information(
            self,
            "Text Sheet exported",
            (
                f"Saved {int(getattr(receipt, 'allocation_count')):,} allocations to:\n"
                f"{Path(getattr(receipt, 'destination'))}\n\n"
                "Edit replacement_text and leave its leading apostrophe in place. "
                "This CSV contains strings from your own game, so keep it private; "
                "share the replacement-only .apf2k8mod project instead."
            ),
        )

    def _import_text_sheet(self) -> None:
        reason = str(
            self.import_text_sheet_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot import Text Sheet yet",
                reason,
            )
            return
        if not self.text_mode or self.model is None:
            return
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import APF Text Sheet",
            str(Path.home()),
            "APF Text Sheet (*.csv)",
        )
        if not source:
            return
        selected = self._selected_row()
        preserve_row_id = selected.row_id if selected is not None else None
        self.run_task(
            "Validating and applying APF Text Sheet",
            lambda progress: self.facade.import_localization_text_sheet(
                Path(source), progress
            ),
            lambda receipt: self._text_sheet_import_complete(
                receipt, preserve_row_id
            ),
            True,
        )

    def _text_sheet_import_complete(
        self,
        receipt: object,
        preserve_row_id: str | None,
    ) -> None:
        self.refresh(preserve_row_id)
        changed = int(getattr(receipt, "changed_count"))
        if changed:
            self.modifiedChanged.emit()
        QMessageBox.information(
            self,
            "Text Sheet imported",
            (
                f"Validated {int(getattr(receipt, 'row_count')):,} rows.\n"
                f"Applied {int(getattr(receipt, 'replacement_count')):,} replacements and "
                f"{int(getattr(receipt, 'revert_count')):,} reverts.\n\n"
                f"{changed:,} active edits changed as one Undo action."
            ),
        )

    def _text_mutation_complete(self, asset_id: str) -> None:
        self.refresh()
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and item.data(Qt.UserRole) == asset_id:
                self.table.selectRow(row_index)
                break
        self.modifiedChanged.emit()

    def _selected_row(self) -> InspectorRow | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return self._visible.get(item.data(Qt.UserRole)) if item else None

    def _selected_bank_identities(
        self, row: InspectorRow | None = None
    ) -> tuple[ExportIdentity, ...]:
        selected = row or self._selected_row()
        if self.model is None or selected is None or selected.kind != "ausb_bank":
            return ()
        count = int(selected.fields.get("substream_count", 0))
        if not 1 <= count <= 256:
            return ()
        outer = int(selected.fields["outer_table_index"])
        inner = int(selected.fields["inner_file_index"])
        identities = tuple(
            candidate.export_identity
            for candidate in self.model.rows
            if candidate.kind == "ausb_substream"
            and candidate.export_identity is not None
            and candidate.export_identity.outer_table_index == outer
            and candidate.export_identity.inner_file_index == inner
        )
        return identities if len(identities) == count else ()

    def _matching_audio_rows(self) -> tuple[InspectorRow, ...]:
        if not self.audio_mode or self.model is None:
            return ()
        if self._audio_review_mode:
            return ()
        if self._soundtrack_album_mode:
            bank_name = str(
                self.soundtrack_version.currentData() or "jukeboxmusic"
            )
            cache_key: tuple[object, ...] = (
                "soundtrack-album",
                self._audio_catalog_epoch,
                bank_name,
            )
            if cache_key == self._matching_audio_cache_key:
                return self._matching_audio_cache
            matching = tuple(
                row
                for row in self._soundtrack_album_rows.get(bank_name, ())
                if row.export_identity is not None
            )
        else:
            if not self._audio_catalog_query_is_current():
                return ()
            cache_key = ("applied-query", self._applied_audio_query_token)
            if cache_key == self._matching_audio_cache_key:
                return self._matching_audio_cache
            matching = tuple(
                row
                for row in self._audio_filtered_rows()
                if row.export_identity is not None
            )
        self._matching_audio_cache_key = cache_key
        self._matching_audio_cache = matching
        return matching

    def cancel_pending_audio_reads(self) -> bool:
        """Cancel session-owned Audio read workers before source/session teardown."""

        if not self.audio_mode:
            return False
        had_read_worker = bool(
            self._audio_preview_job is not None
            or self._waveform_request is not None
        )
        # Playback itself is not a worker, but it consumes the same private WAV
        # cache and must stop before its loaded session is released.
        self._stop_audio()
        self._cancel_audio_waveform()
        return had_read_worker

    def _audio_replacement_template_rows(self) -> tuple[InspectorRow, ...]:
        """Return the exact UI-visible authoring set without any audio bytes."""

        if not self.audio_mode or self.model is None:
            return ()
        if self._audio_review_mode:
            return self._shortlisted_audio_rows()
        return self._matching_audio_rows()

    def _update_audio_replacement_pack_actions(self) -> None:
        if not self.audio_mode:
            return
        query_current = (
            self._audio_review_mode
            or self._soundtrack_album_mode
            or self._audio_catalog_query_is_current()
        )
        count = len(self._audio_replacement_template_rows())
        loaded = self.model is not None
        container = str(self.audio_replacement_pack_format.currentData() or "folder")
        input_kind = str(
            self.audio_replacement_pack_input.currentData() or "xma1"
        )
        container_label = "ZIP" if container == "zip" else "folder"
        input_label = "PCM16 WAV" if input_kind == "pcm16" else "XMA1"
        mutation_busy = self._audio_mutation_busy()
        self.export_audio_replacement_template_button.setEnabled(
            count > 0 and not mutation_busy
        )
        self.export_audio_replacement_template_button.setText(
            f"Create {input_label} {container_label} template ({count:,})…"
            if count
            else f"Create {input_label} {container_label} template…"
        )
        scope = "reviewed shortlist" if self._audio_review_mode else "current filters"
        input_contract = (
            "exact PCM16 WAV input; a configured external XMA1 encoder is required "
            "when this pack is imported"
            if input_kind == "pcm16"
            else "pre-encoded one-stream RIFF XMA1 input; no encoder is required"
        )
        self.export_audio_replacement_template_button.setToolTip(
            f"Create a metadata-only {container_label} for {count:,} sounds from the "
            f"{scope}, using {input_contract}. It contains coordinates and exact slot "
            "shape, never original audio or source-owned sound names."
            if count
            else "Updating results. This action unlocks when the visible page matches the search and filters."
            if loaded and not query_current
            else "Choose at least one playable sound through filters or the shortlist."
        )
        self.import_audio_replacement_pack_button.setEnabled(
            loaded and not mutation_busy
        )
        self.import_audio_replacement_pack_button.setText(
            "Review replacement ZIP…"
            if container == "zip"
            else "Review replacement folder…"
        )
        self.audio_replacement_pack_format.setEnabled(
            not mutation_busy
        )
        self.audio_replacement_pack_input.setEnabled(
            not mutation_busy
        )
        self.cancel_audio_import_button.setText(
            "Cancelling…"
            if self._audio_import_running and self._audio_import_cancel.is_set()
            else "Cancel pack check"
        )
        self.cancel_audio_import_button.setEnabled(
            self._audio_import_running and not self._audio_import_cancel.is_set()
        )

    def _update_matching_audio_action(self) -> None:
        if not self.audio_mode:
            return
        self._update_audio_replacement_pack_actions()
        # Never silent-gray: Export matching stays clickable; disableReason teaches walls.
        if self._audio_review_mode:
            tip = (
                "Review is already the exact hand-picked set. Use Export selected "
                "sounds, or return to the browser for a filtered export."
            )
            self.export_matching_button.setEnabled(True)
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setToolTip(tip)
            self.export_matching_button.setProperty("disableReason", tip)
            return
        if (
            not self._soundtrack_album_mode
            and not self._audio_catalog_query_is_current()
        ):
            tip = (
                "Updating results. This action unlocks when the visible page "
                "matches the search and filters."
            )
            self.export_matching_button.setEnabled(True)
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setToolTip(tip)
            self.export_matching_button.setProperty("disableReason", tip)
            return
        count = len(self._matching_audio_rows())
        enabled = 1 <= count <= 256
        if enabled:
            tip = (
                f"Export these {count} soundtrack tracks as one transactional XMA or verified-WAV ZIP."
                if self._soundtrack_album_mode
                else f"Export these {count} filtered sounds as one transactional XMA or verified-WAV ZIP."
            )
            self.export_matching_button.setText(
                f"Export soundtrack version ({count})…"
                if self._soundtrack_album_mode
                else f"Export matching sounds ({count})…"
            )
            self.export_matching_button.setEnabled(True)
            self.export_matching_button.setToolTip(tip)
            self.export_matching_button.setProperty("disableReason", "")
        else:
            tip = (
                "No playable sounds match."
                if count == 0
                else f"{count:,} playable sounds match; narrow search, kind, role, or source to 256 or fewer."
            )
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setEnabled(True)
            self.export_matching_button.setToolTip(tip)
            self.export_matching_button.setProperty("disableReason", tip)

    def _shortlisted_audio_rows(self) -> tuple[InspectorRow, ...]:
        return tuple(self._audio_shortlist.values())

    def _toggle_audio_review(self) -> None:
        if not self.audio_mode or self.model is None:
            return
        if self._audio_review_mode:
            self._leave_audio_review()
            return
        rows = self._shortlisted_audio_rows()
        if not rows:
            return
        self._timer.stop()
        selected = self._selected_row()
        self._audio_review_restore_offset = self.offset
        self._audio_review_restore_row_id = (
            selected.row_id if selected is not None else None
        )
        self._audio_review_mode = True
        self.offset = 0
        self._update_audio_workspace_controls()
        self.refresh(rows[0].row_id)

    def _leave_audio_review(self) -> None:
        if not self._audio_review_mode:
            return
        self._audio_review_mode = False
        self.offset = self._audio_review_restore_offset
        restore_row_id = self._audio_review_restore_row_id
        self._audio_review_restore_row_id = None
        self._update_audio_workspace_controls()
        self.refresh(restore_row_id)

    def _move_shortlisted_audio(self, delta: int) -> None:
        if not self._audio_review_mode or delta not in {-1, 1}:
            return
        selected = self._selected_row()
        if selected is None or selected.row_id not in self._audio_shortlist:
            return
        ordered = list(self._audio_shortlist.items())
        current_index = next(
            index for index, (row_id, _row) in enumerate(ordered) if row_id == selected.row_id
        )
        target_index = current_index + delta
        if not 0 <= target_index < len(ordered):
            return
        self._cleared_audio_shortlist = ()
        ordered[current_index], ordered[target_index] = (
            ordered[target_index],
            ordered[current_index],
        )
        self._audio_shortlist.clear()
        self._audio_shortlist.update(ordered)
        self.offset = (target_index // PAGE_SIZE) * PAGE_SIZE
        self.refresh(selected.row_id)

    def _visible_playable_audio_rows(self) -> tuple[InspectorRow, ...]:
        if not self.audio_mode:
            return ()
        return tuple(
            row for row in self._visible.values() if row.export_identity is not None
        )

    def _matching_audio_shortlist_additions(
        self,
        matching_rows: tuple[InspectorRow, ...] | None = None,
    ) -> tuple[InspectorRow, ...]:
        """Return new filtered sounds once, in stable product order."""

        seen = set(self._audio_shortlist)
        additions: list[InspectorRow] = []
        for row in (
            self._matching_audio_rows()
            if matching_rows is None
            else matching_rows
        ):
            if row.row_id in seen:
                continue
            seen.add(row.row_id)
            additions.append(row)
        return tuple(additions)

    def _update_audio_shortlist_badges(self) -> None:
        if not self.audio_mode:
            return
        for row_index in range(self.table.rowCount()):
            first = self.table.item(row_index, 0)
            row = self._visible.get(first.data(Qt.UserRole)) if first else None
            status = self.table.item(row_index, 5)
            if row is None or status is None:
                continue
            decorated = self._decorated_audio_table_values(row)[-1]
            status.setText(decorated)
            status.setToolTip(_literal_tooltip(decorated))

    def _update_audio_shortlist_actions(self) -> None:
        if not self.audio_mode:
            return
        count = len(self._audio_shortlist)
        cleared_count = len(self._cleared_audio_shortlist)
        selected = self._selected_row()
        selected_playable = bool(selected and selected.export_identity is not None)
        selected_is_shortlisted = bool(
            selected_playable and selected and selected.row_id in self._audio_shortlist
        )
        self.shortlist_count.setText(f"Selected {count} / 256")
        self.shortlist_clear_button.setEnabled(count > 0 or cleared_count > 0)
        self.shortlist_clear_button.setText(
            "Clear" if count else "Undo" if cleared_count else "Clear"
        )
        self.shortlist_clear_button.setAccessibleName(
            f"Clear {count} sounds from the audio shortlist"
            if count
            else f"Restore the {cleared_count} sounds cleared from the audio shortlist"
            if cleared_count
            else "Clear audio shortlist"
        )
        self.shortlist_clear_button.setToolTip(
            f"Clear these {count} selected sounds. You can undo this until the next shortlist change or game load."
            if count
            else f"Restore all {cleared_count} cleared sounds in their original order."
            if cleared_count
            else "Add sounds before clearing the shortlist."
        )
        self.shortlist_review_button.setText(
            "Back to audio browser"
            if self._audio_review_mode
            else f"Review selected ({count})"
            if count
            else "Review selected"
        )
        self.shortlist_review_button.setEnabled(
            self._audio_review_mode or count > 0
        )
        ordered_ids = tuple(self._audio_shortlist)
        selected_index = (
            ordered_ids.index(selected.row_id)
            if selected is not None and selected.row_id in self._audio_shortlist
            else -1
        )
        self.shortlist_move_up_button.setEnabled(
            self._audio_review_mode and selected_index > 0
        )
        self.shortlist_move_down_button.setEnabled(
            self._audio_review_mode
            and 0 <= selected_index < len(ordered_ids) - 1
        )
        self.export_shortlist_button.setEnabled(count > 0)
        self.export_shortlist_button.setText(
            f"Export selected sounds ({count})…"
            if count
            else "Export selected sounds…"
        )
        self.export_shortlist_button.setToolTip(
            f"Export these {count} hand-picked sounds as one transactional XMA or verified-WAV ZIP."
            if count
            else "Add up to 256 sounds from any search, page, or bank first."
        )

        self.shortlist_toggle_button.setText(
            "Remove selected sound"
            if selected_is_shortlisted
            else "Add selected sound"
            if selected_playable
            else "Choose a sound to shortlist"
        )
        self.shortlist_toggle_button.setEnabled(
            selected_playable and (selected_is_shortlisted or count < 256)
        )
        self.shortlist_toggle_button.setToolTip(
            "Remove this sound from the session shortlist."
            if selected_is_shortlisted
            else "The shortlist is full. Remove a sound before adding another."
            if selected_playable and count >= 256
            else "Add this sound to a session-only export shortlist."
            if selected_playable
            else "Choose a playable sound row first."
        )

        additions = tuple(
            row
            for row in self._visible_playable_audio_rows()
            if row.row_id not in self._audio_shortlist
        )
        self.shortlist_page_button.setText(
            "Add this page"
            if not self._audio_page_actions_ready()
            else f"Add this page ({len(additions)})"
            if additions
            else "Add this page"
        )
        self.shortlist_page_button.setEnabled(
            self._audio_page_actions_ready() and bool(additions) and count < 256
        )
        self.shortlist_page_button.setToolTip(
            "Return to the audio browser to add another page."
            if self._audio_review_mode
            else "Updating results. This action unlocks when the visible page matches the search and filters."
            if not self._audio_page_actions_ready()
            else f"This would exceed the 256-sound shortlist limit; {256 - count} spaces remain."
            if additions and count + len(additions) > 256
            else f"Add {len(additions)} playable sounds visible on this page."
            if additions
            else "Every playable sound on this page is already selected."
        )

        matching_ready = bool(
            self.model is not None
            and not self._audio_review_mode
            and (
                self._soundtrack_album_mode
                or self._audio_catalog_query_is_current()
            )
        )
        matching_rows = self._matching_audio_rows() if matching_ready else ()
        matching_additions = self._matching_audio_shortlist_additions(
            matching_rows
        )
        matching_count = len(matching_additions)
        matching_total = count + matching_count
        self.shortlist_matching_button.setText(
            f"Add all matching ({matching_count:,})"
            if matching_ready and matching_count
            else "Add all matching"
        )
        self.shortlist_matching_button.setEnabled(
            matching_ready and matching_count > 0 and count < 256
        )
        self.shortlist_matching_button.setAccessibleName(
            "Add all matching sounds unavailable in shortlist review"
            if self._audio_review_mode
            else "Add all matching sounds unavailable while audio results update"
            if self.model is not None and not matching_ready
            else f"Cannot add {matching_count:,} matching playable sounds; only {256 - count:,} shortlist spaces remain"
            if matching_count and matching_total > 256
            else f"Add all {matching_count:,} matching playable sounds to the audio shortlist"
            if matching_count
            else "No new matching sounds to add"
        )
        self.shortlist_matching_button.setAccessibleDescription(
            f"Selecting this control explains why {matching_count:,} new matching sounds cannot fit in the {256 - count:,} remaining shortlist spaces; no sounds will be added."
            if matching_count and matching_total > 256
            else "Adds every new playable sound matching the applied search and filters, in stable game catalog order. Existing shortlist sounds are kept once."
        )
        self.shortlist_matching_button.setToolTip(
            "Return to the audio browser to add its filtered sounds."
            if self._audio_review_mode
            else "Updating results. This action unlocks when the visible page matches the search and filters."
            if self.model is not None and not matching_ready
            else "Load an APF 2K8 game first."
            if self.model is None
            else "The shortlist is full. Remove a sound before adding another."
            if matching_count and count >= 256
            else f"Adding all {matching_count:,} new matching sounds would make {matching_total:,}, above the 256-sound limit; {256 - count:,} spaces remain."
            if matching_count and matching_total > 256
            else f"Add all {matching_count:,} new playable sounds in stable game catalog order."
            if matching_count
            else "Every matching playable sound is already selected."
            if matching_rows
            else "No playable sounds match the applied search and filters."
        )

    def _toggle_audio_shortlist(self) -> None:
        row = self._selected_row()
        if not self.audio_mode or row is None or row.export_identity is None:
            return
        if row.row_id in self._audio_shortlist:
            self._cleared_audio_shortlist = ()
            ordered_ids = tuple(self._audio_shortlist)
            removed_index = ordered_ids.index(row.row_id)
            del self._audio_shortlist[row.row_id]
            if self._audio_review_mode:
                remaining = self._shortlisted_audio_rows()
                if not remaining:
                    self._leave_audio_review()
                    return
                target = remaining[min(removed_index, len(remaining) - 1)]
                self.offset = (min(removed_index, len(remaining) - 1) // PAGE_SIZE) * PAGE_SIZE
                self.refresh(target.row_id)
                return
        elif len(self._audio_shortlist) >= 256:
            QMessageBox.information(
                self,
                "Audio shortlist is full",
                "A shortlist can contain up to 256 sounds. Remove one before adding another.",
            )
            return
        else:
            self._cleared_audio_shortlist = ()
            self._audio_shortlist[row.row_id] = row
        self._update_audio_shortlist_badges()
        self._update_audio_shortlist_actions()

    def _add_visible_audio_to_shortlist(self) -> None:
        if not self._audio_page_actions_ready():
            return
        additions = tuple(
            row
            for row in self._visible_playable_audio_rows()
            if row.row_id not in self._audio_shortlist
        )
        if not additions:
            return
        if len(self._audio_shortlist) + len(additions) > 256:
            QMessageBox.information(
                self,
                "Too many sounds for one shortlist",
                f"This page would bring the shortlist to "
                f"{len(self._audio_shortlist) + len(additions):,} sounds, above the 256-sound limit. "
                f"Remove sounds or add a narrower page; {256 - len(self._audio_shortlist)} spaces remain.",
            )
            return
        self._cleared_audio_shortlist = ()
        for row in additions:
            self._audio_shortlist[row.row_id] = row
        self._update_audio_shortlist_badges()
        self._update_audio_shortlist_actions()

    def _add_matching_audio_to_shortlist(self) -> None:
        """Append the complete applied filter set without project or worker work."""

        if (
            not self.audio_mode
            or self.model is None
            or self._audio_review_mode
            or (
                not self._soundtrack_album_mode
                and not self._audio_catalog_query_is_current()
            )
        ):
            return
        additions = self._matching_audio_shortlist_additions()
        if not additions:
            return
        current_count = len(self._audio_shortlist)
        total = current_count + len(additions)
        if total > 256:
            QMessageBox.information(
                self,
                "Too many sounds for one shortlist",
                f"Your shortlist already has {current_count:,} sounds. The applied "
                f"search and filters would add {len(additions):,} new sounds, making "
                f"{total:,}. The limit is 256, so no sounds were added; "
                f"{256 - current_count:,} spaces remain. Remove selected sounds or "
                "narrow the search and filters.",
            )
            return
        self._cleared_audio_shortlist = ()
        for row in additions:
            self._audio_shortlist[row.row_id] = row
        self._update_audio_shortlist_badges()
        self._update_audio_shortlist_actions()

    def _clear_audio_shortlist(self) -> None:
        if not self.audio_mode or self.model is None:
            return
        if not self._audio_shortlist:
            if not self._cleared_audio_shortlist:
                return
            restored = self._cleared_audio_shortlist
            self._audio_shortlist = dict(restored)
            self._cleared_audio_shortlist = ()
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()
            return
        self._cleared_audio_shortlist = tuple(self._audio_shortlist.items())
        self._audio_shortlist.clear()
        if self._audio_review_mode:
            self._leave_audio_review()
            return
        if hasattr(self, "shortlist_count"):
            self._update_audio_shortlist_badges()
            self._update_audio_shortlist_actions()

    def _play_or_stop_audio(self) -> None:
        process = self._audio_process
        if process is None:
            return
        if self._audio_preview_job is not None:
            _request, cancel_event = self._audio_preview_job
            if not cancel_event.is_set():
                cancel_event.set()
                self._update_audio_preview_action()
            return
        if process.state() != QProcess.NotRunning:
            self._stop_audio()
            return
        reason = str(self.play_audio_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot play yet", reason)
            return
        row = self._selected_row()
        if row is None or row.export_identity is None:
            return
        identity = row.export_identity
        self._audio_preview_generation += 1
        request = (
            self._audio_catalog_epoch,
            row.row_id,
            self._audio_preview_generation,
        )
        cancel_event = threading.Event()
        self._audio_preview_request = request
        self._audio_preview_job = (request, cancel_event)
        self._update_audio_preview_action()

        def prepare(
            progress: Callable[[str, int, int], None],
        ) -> tuple[bool, object]:
            try:
                result = self.facade.prepare_audio_preview(
                    identity,
                    progress,
                    cancel_requested=cancel_event.is_set,
                )
            except Exception as exc:
                if cancel_event.is_set():
                    return False, ""
                return False, str(exc).strip() or exc.__class__.__name__
            if cancel_event.is_set():
                return False, ""
            return True, result

        admitted = self.run_task(
            "Preparing private APF audio preview",
            prepare,
            lambda result, owned_request=request: self._complete_audio_preview(
                owned_request, result
            ),
            True,
        )
        # Product task runners return an explicit admission result. Keep None
        # compatible with small test/embedding runners written before that
        # contract existed, but unwind our optimistic button state when the
        # blocking lane rejects this request.
        if admitted is False:
            job = self._audio_preview_job
            if job is not None and job[0] == request:
                self._audio_preview_job = None
            if self._audio_preview_request == request:
                self._audio_preview_request = None
            self._update_audio_preview_action()

    def _audio_preview_request_is_current(
        self, request: tuple[int, str, int]
    ) -> bool:
        selected = self._selected_row()
        return bool(
            request == self._audio_preview_request
            and request[0] == self._audio_catalog_epoch
            and selected is not None
            and selected.row_id == request[1]
        )

    def _complete_audio_preview(
        self, request: tuple[int, str, int], result: object
    ) -> None:
        job = self._audio_preview_job
        if job is None or job[0] != request:
            return
        cancel_requested = job[1].is_set()
        self._audio_preview_job = None
        if not self._audio_preview_request_is_current(request):
            self._update_audio_preview_action()
            return
        ok, value = result  # type: ignore[misc]
        if cancel_requested:
            self._audio_preview_request = None
            self._update_audio_preview_action()
            return
        if ok:
            self._start_audio_preview(request, value)
            return
        self._audio_preview_request = None
        self._update_audio_preview_action()
        QMessageBox.warning(
            self,
            "Could not prepare audio",
            str(value),
        )

    def _start_audio_preview(
        self, request: tuple[int, str, int], result: object
    ) -> None:
        process = self._audio_process
        if process is None:
            return
        if not self._audio_preview_request_is_current(request):
            return
        self._audio_preview_request = None
        path = Path(result)
        try:
            executable, arguments = _audio_player_command(path)
        except RuntimeError as exc:
            self._update_audio_preview_action()
            QMessageBox.information(self, "Audio player unavailable", str(exc))
            return
        self._stopping_audio = False
        self._playing_audio_request = request
        process.setProgram(executable)
        process.setArguments(list(arguments))
        process.start()
        self._update_audio_preview_action()

    def _update_audio_preview_action(self) -> None:
        """Render the one truthful action for pending decode/playback state."""

        if not self.audio_mode:
            return
        job = self._audio_preview_job
        if job is not None:
            request, cancel_event = job
            cancelling = cancel_event.is_set()
            self.play_audio_button.setText(
                "Cancelling…" if cancelling else "Cancel preview"
            )
            self.play_audio_button.setEnabled(
                not cancelling and self._audio_preview_request_is_current(request)
            )
            self.play_audio_button.setToolTip(
                "Stopping the private preview decode. Play becomes available "
                "when its worker has exited."
                if cancelling
                else (
                    "Cancel this private preview decode without changing the "
                    "source or project."
                )
            )
            return
        if self._playing_audio_request is not None:
            self.play_audio_button.setText("Stop")
            self.play_audio_button.setEnabled(True)
            self.play_audio_button.setToolTip("Stop this local audio preview.")
            return
        selected = self._selected_row()
        self.play_audio_button.setText("Play")
        can_play = bool(
            selected
            and selected.export_identity is not None
            and selected.external_bank_identity is None
        )
        if can_play:
            tip = (
                "Decode a session-private, verified WAV and play it with "
                "ffplay, paplay, or aplay."
            )
            block = ""
        elif selected is None:
            tip = block = "Select a playable sound row first."
        elif selected.external_bank_identity is not None:
            tip = block = (
                "This is a multi-cue external bank. Choose a cue/substream row, "
                "not the bank container."
            )
        else:
            tip = block = (
                "This row has no playable export identity (metadata / unsupported)."
            )
        self.play_audio_button.setEnabled(True)
        self.play_audio_button.setToolTip(tip)
        self.play_audio_button.setProperty("disableReason", block)

    def _stop_audio(self) -> None:
        if self._audio_preview_job is not None:
            self._audio_preview_job[1].set()
        self._audio_preview_generation += 1
        self._audio_preview_request = None
        self._playing_audio_request = None
        process = self._audio_process
        if process is not None and process.state() != QProcess.NotRunning:
            self._stopping_audio = True
            process.kill()
        self._update_audio_preview_action()

    def _audio_finished(self, *_args: object) -> None:
        if self._playing_audio_request is None:
            self._stopping_audio = False
            return
        self._playing_audio_request = None
        self._stopping_audio = False
        self._update_audio_preview_action()

    def _audio_process_error(self, _error: object) -> None:
        if self._stopping_audio or self._playing_audio_request is None:
            return
        self._playing_audio_request = None
        self._update_audio_preview_action()
        QMessageBox.warning(
            self,
            "Could not play audio",
            "The local player could not start. The decoded preview remains private, and Export still works.",
        )

    def _external_audio_bank_identities(self) -> tuple[object, ...]:
        if not self.audio_mode or self.model is None:
            return ()
        return tuple(
            row.external_bank_identity
            for row in self.model.rows
            if row.external_bank_identity is not None
        )

    def _update_bulk_audio_export_controls(self) -> None:
        if not self.audio_mode:
            return
        bank_count = len(self._external_audio_bank_identities())
        loaded = self.model is not None
        # Never silent-gray bulk exports: teach load / busy walls via disableReason.
        # Ready-state tooltips keep the full honesty boundaries (47,814 / AUSB /
        # physical banks) that community docs and tests expect.
        catalog_ready_tip = (
            "Export every semantic audio row from the loaded game to one new ZIP. "
            "The manifest and searchable catalog.csv account for all 47,814 pinned "
            "rows; successful sounds also receive checksums and an ordered "
            "playlist.m3u8. The 20 AUSB index rows and 19 physical-bank rows are "
            "recorded as unsupported metadata, not cues."
        )
        banks_ready_tip = (
            "Copy every source-owned physical XMA1 bank—including the two "
            "soundtrack banks—into one private, checksummed ZIP. Raw banks are "
            "multi-cue containers; this does not make them playable or editable."
        )
        if loaded and not self._audio_export_running:
            cat_tip = catalog_ready_tip
            cat_block = ""
        elif self._audio_export_running:
            cat_tip = cat_block = (
                "An audio export is already running. Cancel it first, or wait."
            )
        else:
            cat_tip = cat_block = (
                "Load a supported APF game first, then export the complete audio catalog."
            )
        self.export_complete_audio_catalog_button.setEnabled(True)
        self.export_complete_audio_catalog_button.setToolTip(cat_tip)
        self.export_complete_audio_catalog_button.setProperty(
            "disableReason", cat_block
        )
        self.export_original_audio_banks_button.setText(
            f"Export all original banks ({bank_count})…"
            if bank_count
            else "Export all original banks…"
        )
        if bank_count > 0 and not self._audio_export_running:
            bank_tip = banks_ready_tip
            bank_block = ""
        elif self._audio_export_running:
            bank_tip = bank_block = (
                "An audio export is already running. Cancel it first, or wait."
            )
        elif bank_count == 0:
            bank_tip = bank_block = (
                "No original bank identities are available for this catalog yet."
            )
        else:
            bank_tip = bank_block = (
                "Load a supported APF game first, then export original banks."
            )
        self.export_original_audio_banks_button.setEnabled(True)
        self.export_original_audio_banks_button.setToolTip(bank_tip)
        self.export_original_audio_banks_button.setProperty(
            "disableReason", bank_block
        )
        self.cancel_audio_export_button.setText(
            "Cancelling…"
            if self._audio_export_running and self._audio_export_cancel.is_set()
            else "Cancel audio export"
        )
        self.cancel_audio_export_button.setEnabled(
            self._audio_export_running and not self._audio_export_cancel.is_set()
        )

    def _audio_export_started(self) -> None:
        self._audio_export_running = True
        self._update_bulk_audio_export_controls()

    def _audio_export_finished(self) -> None:
        self._audio_export_running = False
        self._audio_export_cancel.clear()
        self._update_bulk_audio_export_controls()

    def _cancel_running_audio_export(self) -> None:
        if not self._audio_export_running:
            return
        self._audio_export_cancel.set()
        self._update_bulk_audio_export_controls()

    def _run_cancellable_audio_export(
        self,
        label: str,
        operation: Callable[[Callable[[str, int, int], None]], object],
        on_success: Callable[[object], None],
    ) -> None:
        """Start one bulk read with a thread-safe, between-items cancel gate."""

        self._audio_export_cancel.clear()

        def wrapped(progress: Callable[[str, int, int], None]) -> object:
            self.audioExportStarted.emit()
            try:
                return operation(progress)
            finally:
                # PyQt queues this back to the browser's GUI thread when the
                # operation runs in the product worker pool.
                self.audioExportFinished.emit()

        self.run_task(label, wrapped, on_success, True)

    def _audio_import_started(self) -> None:
        self._audio_import_running = True
        self._update_audio_replacement_pack_actions()
        self._configure_audio_replacement(self._selected_row())

    def _audio_import_finished(self) -> None:
        if self._worker_idle_barrier_available:
            self._run_when_idle(self._audio_import_idle)
        else:
            self._audio_import_idle()

    def _audio_import_idle(self) -> None:
        self._audio_import_running = False
        self._audio_import_cancel.clear()
        self._update_audio_replacement_pack_actions()
        self._configure_audio_replacement(self._selected_row())

    def _cancel_running_audio_import(self) -> None:
        if not self._audio_import_running:
            return
        self._audio_import_cancel.set()
        self._update_audio_replacement_pack_actions()

    def _run_cancellable_audio_import(
        self,
        label: str,
        operation: Callable[[Callable[[str, int, int], None]], object],
        on_success: Callable[[object], None],
    ) -> None:
        """Start one project-atomic import with cooperative safe-point cancellation."""

        self._audio_import_cancel.clear()
        self._audio_import_running = True
        self._update_audio_replacement_pack_actions()
        self._configure_audio_replacement(self._selected_row())

        def wrapped(progress: Callable[[str, int, int], None]) -> object:
            self.audioImportStarted.emit()
            try:
                return operation(progress)
            finally:
                self.audioImportFinished.emit()

        # The product runner emits success before it unregisters its worker.
        # Its explicit idle barrier owns the continuation, so confirmation and
        # any follow-up Apply worker cannot race the preview worker's cleanup.
        admitted = self.run_task(
            label,
            wrapped,
            lambda result: self._run_when_idle(lambda: on_success(result)),
            True,
        )
        if admitted is False:
            self._audio_import_idle()
            QMessageBox.information(
                self,
                "Audio is still working",
                "Let the current Audio operation finish, then review the replacement "
                "pack again. Nothing was staged.",
            )

    def _export_audio_replacement_template(self) -> None:
        """Create a new retail-free folder or ZIP for the current authoring set."""

        if self._audio_mutation_busy():
            return
        rows = self._audio_replacement_template_rows()
        if not rows:
            return
        container = str(self.audio_replacement_pack_format.currentData() or "folder")
        input_kind = str(
            self.audio_replacement_pack_input.currentData() or "xma1"
        )
        is_zip = container == "zip"
        kind_slug = "pcm16" if input_kind == "pcm16" else "xma1"
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            (
                f"Create APF {kind_slug.upper()} audio replacement-template ZIP"
                if is_zip
                else f"Create APF {kind_slug.upper()} audio replacement-template folder"
            ),
            str(
                Path.home()
                / (
                    f"apf2k8-audio-{kind_slug}-replacements.zip"
                    if is_zip
                    else f"apf2k8-audio-{kind_slug}-replacements"
                )
            ),
            (
                "APF audio replacement template ZIP (*.zip)"
                if is_zip
                else "Replacement-template folder (*)"
            ),
        )
        if not destination:
            return
        path = Path(destination)
        if is_zip and not path.suffix:
            path = path.with_suffix(".zip")
        if is_zip and path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "ZIP audio templates need a filename ending in .zip.",
            )
            return
        if os.path.lexists(path):
            QMessageBox.information(
                self,
                "Choose a new template name",
                "Replacement templates never overwrite an existing path. Choose a new name and try again.",
            )
            return
        self.run_task(
            "Creating APF audio replacement template",
            lambda progress: self.facade.export_audio_replacement_template(
                rows,
                path,
                progress,
                container=container,
                input_kind=input_kind,
            ),
            self._audio_replacement_template_exported,
            True,
        )

    def _audio_replacement_template_exported(self, receipt: object) -> None:
        container = str(getattr(receipt, "container", "folder"))
        input_kind = str(getattr(receipt, "input_kind", "xma1"))
        if input_kind == "pcm16":
            handoff = (
                "Put exact-shape PCM16 WAV files at any listed pcm16/ paths, then "
                f"choose Review replacement {'ZIP' if container == 'zip' else 'folder'}. "
                "Review detects the PCM16 pack and runs your configured external XMA1 "
                "encoder before the same exact-slot validation. Missing files are skipped."
            )
            format_note = (
                "FLAC and MP3 cannot be imported directly. Convert them to the exact "
                "PCM16 WAV shape listed in this template before import."
            )
        else:
            handoff = (
                "Put pre-encoded, one-stream RIFF XMA1 files at any listed xma1/ paths, "
                f"then choose Review replacement {'ZIP' if container == 'zip' else 'folder'}. "
                "Review detects this legacy format and does not require a configured "
                "encoder. Missing files are skipped."
            )
            format_note = (
                "To start from FLAC or MP3, convert it to exact PCM16 WAV first and "
                "create a PCM16 WAV replacement template instead."
            )
        QMessageBox.information(
            self,
            "Audio replacement template created",
            (
                f"Created {int(getattr(receipt, 'entry_count')):,} exact sound targets at:\n"
                f"{Path(getattr(receipt, 'path'))}\n\n"
                "No original audio or source-owned sound names were exported. "
                f"{handoff}\n\n{format_note}\n\n"
                "Use only audio you created or have permission to modify and share. "
                "Automated source-reuse checks are not copyright clearance."
            ),
        )

    def _import_audio_replacement_pack(self) -> None:
        if (
            not self.audio_mode
            or self.model is None
            or self._audio_mutation_busy()
        ):
            return
        container = str(self.audio_replacement_pack_format.currentData() or "folder")
        if container == "zip":
            selected, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Choose APF audio replacement ZIP",
                str(Path.home()),
                "APF audio replacement pack ZIP (*.zip)",
            )
            if selected and Path(selected).suffix.casefold() != ".zip":
                QMessageBox.information(
                    self,
                    "Choose a ZIP file",
                    "APF audio replacement packs must have a .zip filename.",
                )
                return
        else:
            selected = QFileDialog.getExistingDirectory(
                self,
                "Choose APF audio replacement folder",
                str(Path.home()),
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
            )
        if not selected:
            return
        # Import owns schema detection. A missing or malformed local encoder
        # must not block a legacy XMA1 pack; the backend asks for one only after
        # it identifies a PCM16 pack and then returns configure-first guidance.
        try:
            encoder = self._external_xma1_encoder()
            if encoder is not None:
                encoder.validate()
        except (TypeError, ValueError):
            encoder = None
        current = self._selected_row()
        preserve_row_id = current.row_id if current is not None else None
        selected_path = Path(selected)
        self._run_cancellable_audio_import(
            "Checking APF audio replacement pack before Apply",
            lambda progress: self.facade.preview_audio_replacement_pack(
                selected_path,
                progress,
                encoder=encoder,
                cancel_requested=self._audio_import_cancel.is_set,
            ),
            lambda receipt: self._audio_replacement_pack_previewed(
                receipt,
                selected_path,
                encoder,
                preserve_row_id,
            ),
        )

    def _audio_replacement_pack_previewed(
        self,
        receipt: object,
        selected_path: Path,
        encoder: ExternalXma1Encoder | None,
        preserve_row_id: str | None,
    ) -> None:
        input_kind = str(getattr(receipt, "input_kind", "xma1"))
        supplied_label = (
            "PCM16 WAV files" if input_kind == "pcm16" else "XMA1 files"
        )
        if bool(getattr(receipt, "was_cancelled", False)):
            QMessageBox.information(
                self,
                "Audio replacement preview cancelled",
                (
                    f"Completed {supplied_label}: "
                    f"{int(getattr(receipt, 'validated_count')):,} of "
                    f"{int(getattr(receipt, 'supplied_count')):,}\n\n"
                    "No project edits changed, no Undo action was added, and preview-only "
                    "encoded payloads were discarded."
                ),
            )
            return
        would_change = int(getattr(receipt, "would_change_count"))
        summary = (
            f"Template targets: {int(getattr(receipt, 'template_entry_count')):,}\n"
            f"Supplied {supplied_label}: {int(getattr(receipt, 'supplied_count')):,}\n"
            f"Would change: {would_change:,}\n"
            f"Already current: {int(getattr(receipt, 'already_current_count')):,}\n"
            f"Missing and intentionally skipped: {int(getattr(receipt, 'missing_count')):,}\n"
            f"Modified audio now: {int(getattr(receipt, 'current_modified_audio_count')):,}\n"
            "Modified audio after Apply: "
            f"{int(getattr(receipt, 'resulting_modified_audio_count')):,}"
        )
        if would_change == 0:
            QMessageBox.information(
                self,
                "Audio replacement pack is already current",
                (
                    f"{summary}\n\n"
                    "The complete pack passed validation, but it would not change this "
                    "project. Apply is unavailable and no project state changed."
                ),
            )
            return
        confirmation_token = str(getattr(receipt, "confirmation_token", ""))
        if len(confirmation_token) != 64:
            raise RuntimeError(
                "The validated audio preview did not return a safe Apply token. "
                "Review the pack again."
            )
        answer = QMessageBox.question(
            self,
            "Apply validated audio changes?",
            (
                f"{summary}\n\n"
                "Nothing has been staged yet. Apply reopens the folder or ZIP, reruns "
                "the complete safety validation, and refuses if its exact authored "
                "files or this project's audio edits changed after this preview. All "
                "real changes become one Undo action.\n\n"
                "Choose Apply only if these counts match what you intended."
            ),
            QMessageBox.Apply | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Apply:
            return
        self._run_cancellable_audio_import(
            "Revalidating and applying APF audio replacement pack",
            lambda progress: self.facade.import_audio_replacement_pack(
                selected_path,
                progress,
                encoder=encoder,
                cancel_requested=self._audio_import_cancel.is_set,
                confirmation_token=confirmation_token,
            ),
            lambda applied: self._audio_replacement_pack_imported(
                applied,
                preserve_row_id,
            ),
        )

    def _audio_replacement_pack_imported(
        self,
        receipt: object,
        preserve_row_id: str | None,
    ) -> None:
        input_kind = str(getattr(receipt, "input_kind", "xma1"))
        supplied_label = (
            "PCM16 WAV files" if input_kind == "pcm16" else "XMA1 files"
        )
        if bool(getattr(receipt, "was_cancelled", False)):
            QMessageBox.information(
                self,
                "Audio replacement import cancelled",
                (
                    f"Completed {supplied_label}: "
                    f"{int(getattr(receipt, 'validated_count')):,} of "
                    f"{int(getattr(receipt, 'supplied_count')):,}\n\n"
                    "The cancel request was observed at a safe boundary or by the "
                    "user-supplied encoder. No project edits changed and no Undo "
                    "action was added."
                ),
            )
            return
        self.refresh(preserve_row_id)
        self._selection_changed()
        if int(getattr(receipt, "staged_count")):
            self.modifiedChanged.emit()
        QMessageBox.information(
            self,
            "Audio replacement pack imported",
            (
                f"Template targets: {int(getattr(receipt, 'template_entry_count')):,}\n"
                f"Supplied {supplied_label}: {int(getattr(receipt, 'supplied_count')):,}\n"
                f"Project edits changed: {int(getattr(receipt, 'staged_count')):,}\n"
                f"Already staged: {int(getattr(receipt, 'unchanged_count')):,}\n"
                f"Missing and intentionally skipped: {int(getattr(receipt, 'missing_count')):,}\n\n"
                "The full pack passed PCM shape and external encoding checks where "
                "applicable, plus source, slot-shape, packet, decode, source-reuse, "
                "and alias checks before any project edit changed. One Undo restores "
                "the exact edit set from before this import. Automated source-reuse "
                "checks are not copyright clearance."
            ),
        )

    def _export_complete_audio_catalog(self) -> None:
        """Publish every indexed semantic audio row to one private ZIP."""

        reason = str(
            self.export_complete_audio_catalog_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export complete audio catalog yet",
                reason,
            )
            return
        model = self.model
        if not self.audio_mode or model is None or not model.rows:
            return
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export complete APF audio catalog",
            str(Path.home() / "apf2k8-complete-audio-catalog.zip"),
            (
                "Original XMA1 audio catalog ZIP (*.zip);;"
                "Decoder-verified WAV audio catalog ZIP (*.zip)"
            ),
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "The complete audio catalog exports as one transactional .zip archive.",
            )
            return
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Complete audio-catalog exports never overwrite an existing path. "
                "Choose a new filename and try again.",
            )
            return
        rows = tuple(model.rows)
        output_extension = (
            ".wav" if selected_filter.startswith("Decoder") else ".xma"
        )
        self._run_cancellable_audio_export(
            "Exporting complete APF audio catalog",
            lambda progress: self.facade.export_audio_batch(
                rows,
                path,
                output_extension=output_extension,
                batch_name="APF 2K8 complete audio catalog",
                progress=progress,
                cancel_requested=self._audio_export_cancel.is_set,
            ),
            self._complete_audio_catalog_exported,
        )

    def _complete_audio_catalog_exported(self, receipt: object) -> None:
        requested = int(getattr(receipt, "requested"))
        succeeded = int(getattr(receipt, "succeeded"))
        failed = int(getattr(receipt, "failed"))
        unsupported = int(getattr(receipt, "unsupported"))
        cancelled = int(getattr(receipt, "cancelled"))
        was_cancelled = bool(getattr(receipt, "was_cancelled", cancelled > 0))
        payload_bytes = int(getattr(receipt, "payload_bytes", 0))
        catalog_count = int(
            getattr(receipt, "catalog_record_count", requested)
        )
        playlist_count = int(
            getattr(receipt, "playlist_record_count", succeeded)
        )
        QMessageBox.information(
            self,
            (
                "Complete audio catalog export cancelled"
                if was_cancelled
                else "Complete audio catalog exported"
            ),
            (
                f"Saved to:\n{Path(getattr(receipt, 'path'))}\n\n"
                f"Requested: {requested:,}\n"
                f"Success: {succeeded:,}\n"
                f"Failure: {failed:,}\n"
                f"Unsupported: {unsupported:,}\n"
                f"Cancelled: {cancelled:,}\n"
                f"Catalog CSV rows: {catalog_count:,}\n"
                f"Playlist entries: {playlist_count:,}\n"
                + (
                    f"Exact exported sound bytes: {_human_bytes(payload_bytes)}\n"
                    if payload_bytes > 0
                    else ""
                )
                + "\nThe ZIP manifest and catalog.csv account for every requested "
                "semantic row. Successful sounds carry exact byte sizes and SHA-256 "
                "checksums; playlist.m3u8 preserves their requested order. On the "
                "complete pinned catalog, 20 AUSB index rows and 19 physical-bank rows "
                "are expected under Unsupported because they are metadata or multi-cue "
                "containers, not individual sounds.\n\n"
                "This retail-derived export is private and is not stored in a shareable "
                "Mod Studio project."
            ),
        )

    def _export_all_original_audio_banks(self) -> None:
        """Copy every physical XMA1 bank to one private, accounted ZIP."""

        reason = str(
            self.export_original_audio_banks_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export original audio banks yet",
                reason,
            )
            return
        identities = self._external_audio_bank_identities()
        if not identities:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export all original APF audio banks",
            str(Path.home() / "apf2k8-original-audio-banks.zip"),
            "Original APF XMA1 bank bundle ZIP (*.zip)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "The complete original-bank set exports as one transactional .zip archive.",
            )
            return
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Original-bank bundles never overwrite an existing path. Choose a new filename and try again.",
            )
            return
        self._run_cancellable_audio_export(
            "Exporting all original APF audio banks",
            lambda progress: self.facade.export_external_audio_bank_bundle(
                identities,
                path,
                bundle_name="APF 2K8 original external audio banks",
                progress=progress,
                cancel_requested=self._audio_export_cancel.is_set,
            ),
            self._all_original_audio_banks_exported,
        )

    def _all_original_audio_banks_exported(self, receipt: object) -> None:
        requested = int(getattr(receipt, "requested"))
        succeeded = int(getattr(receipt, "succeeded"))
        failed = int(getattr(receipt, "failed"))
        cancelled = int(getattr(receipt, "cancelled"))
        was_cancelled = bool(getattr(receipt, "was_cancelled", cancelled > 0))
        exported_bytes = int(
            getattr(
                receipt,
                "encoded_bytes",
                getattr(
                    receipt,
                    "exported_bytes",
                    getattr(
                        receipt,
                        "payload_bytes",
                        getattr(receipt, "succeeded_bytes", 0),
                    ),
                ),
            )
        )
        QMessageBox.information(
            self,
            (
                "Original audio-bank export cancelled"
                if was_cancelled
                else "Original audio banks exported"
            ),
            (
                f"Saved to:\n{Path(getattr(receipt, 'path'))}\n\n"
                f"Requested banks: {requested:,}\n"
                f"Success: {succeeded:,}\n"
                f"Failure: {failed:,}\n"
                f"Cancelled: {cancelled:,}\n"
                + (
                    f"Exact bank bytes: {_human_bytes(exported_bytes)}\n"
                    if exported_bytes > 0
                    else ""
                )
                + "\nThe ZIP stores exact source-owned .bin containers and a "
                "manifest with bank checksums plus every AUSB descriptor owner. "
                "That includes the soundtrack banks when present. These raw "
                "multi-cue banks are not directly playable or replaceable.\n\n"
                "This retail-derived export is private and is not stored in a "
                "shareable Mod Studio project."
            ),
        )

    def _export_audio(self) -> None:
        row = self._selected_row()
        if row is None or row.export_identity is None:
            return
        identity = row.export_identity
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export APF audio from your game",
            str(Path.home() / f"{identity.suggested_basename}.xma"),
            "Original XMA1 (*.xma);;Decoder-verified WAV (*.wav)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".wav" if selected_filter.startswith("Decoder") else ".xma")
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting APF audio",
            lambda progress: self.facade.export_audio_identity(identity, path, progress),
            lambda result: QMessageBox.information(
                self,
                "Audio exported",
                f"Saved to:\n{Path(result)}\n\nThis file was exported from your own game copy.",
            ),
            True,
        )

    def _export_audio_pcm_template(self) -> None:
        reason = str(
            self.export_pcm_template_button.property("disableReason") or ""
        ).strip()
        if reason:
            self.audio_replace_note.setText(reason)
            return
        row = self._selected_row()
        if (
            self._audio_mutation_busy()
            or not self._audio_row_has_exact_slot_editor(row)
        ):
            return
        assert row is not None and row.export_identity is not None
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export exact PCM authoring template",
            str(
                Path.home()
                / f"{row.export_identity.suggested_basename}-authoring.wav"
            ),
            "PCM16 WAV authoring template (*.wav)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".wav")
        if path.suffix.casefold() != ".wav":
            QMessageBox.information(
                self,
                "Choose a WAV filename",
                "PCM authoring templates need a filename ending in .wav.",
            )
            return
        if os.path.lexists(path):
            QMessageBox.information(
                self,
                "Choose a new filename",
                "PCM authoring templates never overwrite an existing path. "
                "Choose a new filename and try again.",
            )
            return
        identity = row.export_identity
        self.run_task(
            "Exporting exact PCM authoring template",
            lambda progress: self.facade.export_audio_pcm_template(
                identity, path, progress
            ),
            self._audio_pcm_template_exported,
            True,
        )

    def _audio_pcm_template_exported(self, receipt: object) -> None:
        channels = int(getattr(receipt, "channels"))
        sample_rate = int(getattr(receipt, "sample_rate"))
        frame_count = int(getattr(receipt, "frame_count"))
        encoded_size = int(getattr(receipt, "encoded_size"))
        channel_label = "mono" if channels == 1 else "stereo"
        QMessageBox.information(
            self,
            "PCM authoring template exported",
            (
                f"Saved to:\n{Path(getattr(receipt, 'path'))}\n\n"
                f"Shape: {sample_rate:,} Hz • {channel_label} • "
                f"{frame_count:,} PCM frames\n"
                f"Final APF allocation: {_human_bytes(encoded_size)}\n\n"
                "This is an exact-length silence template containing no retail "
                "audio. Edit its samples without changing channel count, sample "
                "rate, or length, then choose Replace from audio."
            ),
        )

    def _pcm_encoding_started(self) -> None:
        self._pcm_encoding_running = True
        self._configure_audio_replacement(self._selected_row())

    def _pcm_encoding_finished(self) -> None:
        if self._worker_idle_barrier_available:
            self._run_when_idle(self._pcm_encoding_idle)
        else:
            self._pcm_encoding_idle()

    def _pcm_encoding_idle(self) -> None:
        self._pcm_encoding_running = False
        self._pcm_encoding_cancel.clear()
        self._configure_audio_replacement(self._selected_row())

    def _direct_audio_replacement_worker_finished(self) -> None:
        """Keep mutation controls fenced until the product runner is idle."""

        if self._worker_idle_barrier_available:
            self._run_when_idle(self._direct_audio_replacement_idle)
        else:
            # Standalone component tests and embedders have no worker registry.
            # Their TaskRunner owns completion synchronously.
            self._direct_audio_replacement_idle()

    def _direct_audio_replacement_idle(self) -> None:
        self._direct_audio_replacement_running = False
        self._configure_audio_replacement(self._selected_row())

    def _run_direct_audio_mutation(
        self,
        label: str,
        operation: Callable[[Callable[[str, int, int], None]], object],
        on_success: Callable[[object], None],
    ) -> bool:
        """Own one direct Audio mutation from submission through worker drain."""

        if self._audio_mutation_busy():
            return False
        self._direct_audio_replacement_running = True
        self._configure_audio_replacement(self._selected_row())

        def owned(progress: Callable[[str, int, int], None]) -> object:
            try:
                return operation(progress)
            finally:
                self.directAudioReplacementWorkerFinished.emit()

        try:
            admitted = self.run_task(label, owned, on_success, True)
        except BaseException:
            self._direct_audio_replacement_idle()
            raise
        if admitted is False:
            self._direct_audio_replacement_idle()
            QMessageBox.information(
                self,
                "Audio is still working",
                "Let the current Audio operation finish, then drop or choose the "
                "replacement again. Nothing was staged.",
            )
            return False
        return True

    def _cancel_running_pcm_encoding(self) -> None:
        if not self._pcm_encoding_running:
            return
        self._pcm_encoding_cancel.set()
        self._configure_audio_replacement(self._selected_row())

    def _run_cancellable_pcm_encoding(
        self,
        operation: Callable[[Callable[[str, int, int], None]], object],
        on_success: Callable[[object], None],
    ) -> None:
        self._pcm_encoding_cancel.clear()
        self._pcm_encoding_running = True
        self._configure_audio_replacement(self._selected_row())

        def wrapped(progress: Callable[[str, int, int], None]) -> object:
            self.pcmEncodingStarted.emit()
            try:
                return operation(progress)
            finally:
                self.pcmEncodingFinished.emit()

        admitted = self.run_task(
            "Encoding and validating exact-slot APF audio",
            wrapped,
            on_success,
            True,
        )
        if admitted is False:
            self._pcm_encoding_idle()
            QMessageBox.information(
                self,
                "Audio is still working",
                "Let the current Audio operation finish, then drop or choose the PCM "
                "replacement again. Nothing was staged.",
            )

    def _configured_audio_encoder_for_replace(
        self,
    ) -> ExternalXma1Encoder | None:
        """Resolve one valid local encoder, offering guided setup on first use.

        No XMA1 encoder ships with the editor, so the first time a user tries
        to replace a sound there is nothing configured.  Instead of a dead-end
        refusal, this offers the guided setup wizard; if the user declines or
        it is cancelled, nothing is staged and the refusal stays fail-closed.
        """

        try:
            encoder = self._external_xma1_encoder()
            if encoder is None:
                raise ValueError("No external XMA1 encoder is configured")
            encoder.validate()
        except Exception as exc:
            answer = QMessageBox.question(
                self,
                "Set up your XMA1 encoder now?",
                (
                    f"{exc}\n\n"
                    "APF audio is stored as XMA1, and no encoder ships with Mod "
                    "Studio. The guided setup finds what it can, explains the "
                    "two {input}/{output} placeholders, and test-runs your "
                    "encoder on a one-second tone before saving anything.\n\n"
                    "Start guided setup now? No project data changes either way."
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                wizard_encoder = self._run_xma1_encoder_setup_wizard()
                if wizard_encoder is not None:
                    try:
                        self._save_external_xma1_encoder(wizard_encoder)
                    except OSError as save_exc:
                        QMessageBox.information(
                            self,
                            "Encoder setting was not saved",
                            f"{save_exc}. The mod project was not changed.",
                        )
                        self._update_audio_encoder_status()
                        return None
                    self._update_audio_encoder_status()
                    return wizard_encoder
            self._update_audio_encoder_status()
            return None
        return encoder

    def _replace_audio_from_pcm(self) -> None:
        reason = str(
            self.replace_pcm_audio_button.property("disableReason") or ""
        ).strip()
        if reason:
            self.audio_replace_note.setText(reason)
            return
        row = self._selected_row()
        if (
            self._audio_mutation_busy()
            or not self._audio_row_has_exact_slot_editor(row)
        ):
            return
        assert row is not None and row.export_identity is not None
        encoder = self._configured_audio_encoder_for_replace()
        if encoder is None:
            return
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose your audio for this APF sound",
            str(Path.home()),
            audio_conform.file_dialog_filter(),
        )
        if not source:
            return
        self._replace_audio_pcm_path(row, Path(source), encoder)

    def _replace_audio_pcm_path(
        self,
        row: InspectorRow,
        path: Path,
        encoder: ExternalXma1Encoder,
    ) -> None:
        """Stage one captured row/path through the existing PCM bridge."""

        if self._audio_mutation_busy():
            return
        if not self._audio_row_has_exact_slot_editor(row):
            return
        assert row.export_identity is not None
        if not audio_conform.is_supported_suffix(path):
            QMessageBox.information(
                self,
                "Choose an audio file",
                "This authoring route accepts ordinary audio files - WAV, MP3, "
                "FLAC, OGG, M4A and similar - and converts them to this slot's "
                "exact shape before encoding. That file type is not one it can "
                "read.",
            )
            return
        if not audio_conform.conversion_available() and path.suffix.casefold() != ".wav":
            QMessageBox.information(
                self,
                "FFmpeg is required to convert audio",
                "Converting other audio formats to this slot's exact shape needs "
                "FFmpeg, which was not found. Install FFmpeg, or supply a PCM16 "
                "WAV already matching the slot's channels, sample rate and frame "
                "count.",
            )
            return
        identity = row.export_identity
        row_id = row.row_id
        self._run_cancellable_pcm_encoding(
            lambda progress: self.facade.replace_audio_from_pcm(
                identity,
                path,
                encoder,
                progress,
                cancel_requested=self._pcm_encoding_cancel.is_set,
            ),
            lambda _result: self._pcm_audio_mutation_complete(row_id),
        )

    def _replace_audio_drop(self, path: Path) -> None:
        """Route one dropped authoring file by type with no chooser dialog."""

        row = self._selected_row()
        if (
            not self._audio_row_has_exact_slot_editor(row)
            or self._audio_mutation_busy()
        ):
            return
        assert row is not None
        suffix = path.suffix.casefold()
        if suffix == ".xma":
            self._replace_audio_xma_path(row, path)
            return
        if audio_conform.is_supported_suffix(path):
            encoder = self._configured_audio_encoder_for_replace()
            if encoder is not None:
                self._replace_audio_pcm_path(row, path, encoder)
            return
        QMessageBox.information(
            self,
            "Drop an audio file",
            "This drop target accepts one local audio file - an already-encoded "
            ".xma, or ordinary audio such as WAV, MP3, FLAC, OGG or M4A, which "
            "is converted to this slot's exact shape first. Folders, links, and "
            "multiple files are not accepted.",
        )

    def _pcm_audio_mutation_complete(self, row_id: str) -> None:
        self._audio_mutation_complete(row_id)
        QMessageBox.information(
            self,
            "Audio replacement staged",
            (
                "The user-supplied encoder output passed the exact allocation, "
                "packet, complete-decode, duration, source-fingerprint, and shared-"
                "owner gates. The untouched source game was not modified.\n\n"
                "The encoder binary/path and input audio remain outside this shareable "
                "mod project; the project contains only the accepted replacement stream."
            ),
        )

    def _replace_audio(self) -> None:
        reason = str(
            self.replace_audio_button.property("disableReason") or ""
        ).strip()
        if reason:
            self.audio_replace_note.setText(reason)
            return
        row = self._selected_row()
        if (
            self._audio_mutation_busy()
            or not self._audio_row_has_exact_slot_editor(row)
        ):
            return
        assert row is not None and row.export_identity is not None
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import pre-encoded XMA1 for this exact APF sound slot",
            str(Path.home()),
            "RIFF XMA1 audio (*.xma)",
        )
        if not source:
            return
        self._replace_audio_xma_path(row, Path(source))

    def _replace_audio_xma_path(
        self,
        row: InspectorRow,
        path: Path,
    ) -> None:
        """Stage one captured row/path through the existing exact XMA1 writer."""

        if self._audio_mutation_busy():
            return
        if not self._audio_row_has_exact_slot_editor(row):
            return
        assert row.export_identity is not None
        if path.suffix.casefold() != ".xma":
            QMessageBox.information(
                self,
                "Choose an XMA file",
                "This advanced editor accepts a pre-encoded RIFF XMA1 .xma file. "
                "WAV, FLAC, WMA, and xWMA are not interchangeable with APF's XMA1 stream.",
            )
            return
        identity = row.export_identity
        row_id = row.row_id
        banked = identity.kind == "ausb_substream"
        self._run_direct_audio_mutation(
            (
                "Validating exact AUSB-bank XMA1 replacement"
                if banked
                else "Validating exact-slot APF XMA1 replacement"
            ),
            lambda progress: (
                self.facade.replace_ausb_exact_slot(identity, path, progress)
                if banked
                else self.facade.replace_audo_exact_slot(identity, path, progress)
            ),
            lambda _result: self._audio_mutation_complete(row_id),
        )

    def _revert_audio(self) -> None:
        reason = str(
            self.revert_audio_button.property("disableReason") or ""
        ).strip()
        if reason:
            self.audio_replace_note.setText(reason)
            return
        row = self._selected_row()
        if (
            self._audio_mutation_busy()
            or not self._audio_row_has_exact_slot_editor(row)
            or row is None
            or row.row_id
            not in frozenset(
                getattr(self.facade, "modified_asset_ids", frozenset())
            )
        ):
            return
        row_id = row.row_id
        self._run_direct_audio_mutation(
            "Reverting APF sound replacement",
            lambda progress: self.facade.revert(row_id, progress),
            lambda _result: self._audio_mutation_complete(row_id),
        )

    def _audio_mutation_complete(self, row_id: str) -> None:
        self.refresh(row_id)
        self._selection_changed()
        self.modifiedChanged.emit()

    def _export_external_audio_bank(self) -> None:
        row = self._selected_row()
        if row is None or row.external_bank_identity is None:
            return
        identity = row.external_bank_identity
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export original APF external audio bank",
            str(Path.home() / identity.external_filename),
            "Original external XMA1 bank (*.bin)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".bin")
        if path.suffix.casefold() != ".bin":
            QMessageBox.information(
                self,
                "Choose a BIN filename",
                "Physical APF external audio banks export as exact .bin files.",
            )
            return
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting original APF external audio bank",
            lambda progress: self.facade.export_external_audio_bank(
                identity, path, progress
            ),
            lambda result: QMessageBox.information(
                self,
                "External audio bank exported",
                f"Saved the exact multi-cue packet bank to:\n{Path(result)}\n\n"
                "This raw container is not one playable sound. Use its AUSB substream rows for Play or individual sound export.",
            ),
            True,
        )

    def _export_matching_audio(self) -> None:
        reason = str(
            self.export_matching_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export matching sounds yet",
                reason,
            )
            return
        rows = self._matching_audio_rows()
        if not 1 <= len(rows) <= 256:
            return
        if self._soundtrack_album_mode:
            bundle_name = f"APF soundtrack · {self.soundtrack_version.currentText()}"
        else:
            role = self.role_filter.currentText()
            kind = self.kind_filter.currentText()
            source = self.source_filter.currentText()
            search = self.search.text().strip()
            bundle_name = " · ".join(
                part for part in (
                    self.title_text,
                    source,
                    role,
                    kind,
                    "Labeled only" if self.labeled_only_filter.isChecked() else "",
                    search,
                ) if part
            )
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export matching APF sounds",
            str(Path.home() / "apf-matching-sounds-original-xma.zip"),
            "Original XMA1 sounds ZIP (*.zip);;Decoder-verified WAV sounds ZIP (*.zip)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "Matching sounds export transactionally as one .zip archive.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        extension = ".wav" if selected_filter.startswith("Decoder") else ".xma"
        self.run_task(
            "Exporting matching APF sounds",
            lambda progress: self.facade.export_audio_bundle(
                rows,
                path,
                bundle_name=bundle_name,
                output_extension=extension,
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Matching sounds exported",
                f"Saved {len(rows):,} sounds to:\n{Path(result)}\n\nThe ZIP was completed before publication; a failed WAV decode leaves no partial output.",
            ),
            True,
        )

    def _export_shortlisted_audio(self) -> None:
        rows = self._shortlisted_audio_rows()
        if not 1 <= len(rows) <= 256:
            return
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export selected APF sounds",
            str(Path.home() / "apf-selected-sounds-original-xma.zip"),
            "Original XMA1 sounds ZIP (*.zip);;Decoder-verified WAV sounds ZIP (*.zip)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "Selected sounds export transactionally as one .zip archive.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        extension = ".wav" if selected_filter.startswith("Decoder") else ".xma"
        self.run_task(
            "Exporting selected APF sounds",
            lambda progress: self.facade.export_audio_bundle(
                rows,
                path,
                bundle_name="APF audio shortlist",
                output_extension=extension,
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Selected sounds exported",
                f"Saved {len(rows):,} sounds to:\n{Path(result)}\n\n"
                "The ZIP was completed before publication; a failed WAV decode leaves no partial output.",
            ),
            True,
        )

    def _export_audio_bank(self) -> None:
        row = self._selected_row()
        identities = self._selected_bank_identities(row)
        if row is None or not identities:
            return
        bank_name = str(row.fields.get("name") or row.title)
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in bank_name
        ).strip("-") or "apf-audio-bank"
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export complete APF audio bank",
            str(Path.home() / f"{safe_name}-original-xma.zip"),
            "Original XMA1 bank ZIP (*.zip);;Decoder-verified WAV bank ZIP (*.zip)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".zip")
        if path.suffix.casefold() != ".zip":
            QMessageBox.information(
                self,
                "Choose a ZIP filename",
                "Complete banks export transactionally as one .zip archive.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        extension = ".wav" if selected_filter.startswith("Decoder") else ".xma"
        self.run_task(
            "Exporting complete APF audio bank",
            lambda progress: self.facade.export_audio_bank(
                identities,
                path,
                bank_name=bank_name,
                output_extension=extension,
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Audio bank exported",
                f"Saved to:\n{Path(result)}\n\nThe ZIP was completed before publication; a WAV decode failure leaves no partial output.",
            ),
            True,
        )

    def _export_rows(self) -> None:
        reason = str(self.export_rows_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export decoded rows yet",
                reason,
            )
            return
        model = self.model
        if model is None:
            return
        if self.audio_mode and not self._audio_catalog_query_is_current():
            tip = (
                "Updating results. Export decoded rows unlocks when the visible "
                "page matches the search and filters."
            )
            QMessageBox.information(self, "Cannot export decoded rows yet", tip)
            return
        safe_title = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in self.title_text.casefold()
        ).strip("_") or "decoded-rows"
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export decoded inspector rows",
            str(Path.home() / f"apf-{safe_title}.json"),
            "Structured JSON (*.json);;Spreadsheet CSV (*.csv)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(
                ".csv" if selected_filter.startswith("Spreadsheet") else ".json"
            )
        if path.suffix.casefold() not in {".json", ".csv"}:
            QMessageBox.information(
                self,
                "Choose JSON or CSV",
                "Decoded inspector rows export as .json or .csv. Choose one of those filename endings.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        search = self.search.text()
        kind = self.kind_filter.currentData()
        role = self.role_filter.currentData() if self.audio_mode else None
        source = self.source_filter.currentData() if self.audio_mode else None
        export_model = model
        if self.audio_mode and self._annotation_capable:
            selected_rows = self._audio_filtered_rows()
            overlay = getattr(self.facade, "annotated_audio_rows", None)
            if callable(overlay):
                selected_rows = tuple(overlay(selected_rows))
            export_model = PagedModel(selected_rows, model.findings)
            # The bounded model already embodies the exact metadata-aware UI
            # query. Reapplying the immutable base-row search would drop rows
            # found only through a custom title or note.
            search = ""
            kind = None
            role = None
            source = None
        self.run_task(
            "Exporting decoded inspector rows",
            lambda progress: self.facade.export_inspector_rows(
                export_model,
                path,
                search=search,
                kinds=kind,
                roles=role,
                sources=source,
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Decoded rows exported",
                f"Saved to:\n{Path(result)}\n\nOnly rows matching the current filters were exported from your own game copy.",
            ),
            True,
        )

    def _export_player_rating_sheet(self) -> None:
        reason = str(
            self.export_ratings_sheet_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export ratings sheet yet",
                reason,
            )
            return
        model = self.model
        if not self.roster_mode or model is None:
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export complete APF player ratings sheet",
            str(Path.home() / "apf2k8-player-ratings-private.csv"),
            "Spreadsheet CSV (*.csv)",
        )
        if not destination:
            return
        path = Path(destination)
        if not path.suffix:
            path = path.with_suffix(".csv")
        if path.suffix.casefold() != ".csv":
            QMessageBox.information(
                self,
                "Choose a CSV filename",
                "The complete player ratings sheet exports as one .csv file.",
            )
            return
        if path.exists():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Ratings exports never overwrite an existing file. Choose a new filename and try again.",
            )
            return
        self.run_task(
            "Exporting complete APF player ratings sheet",
            lambda progress: self.facade.export_player_rating_sheet(
                model,
                path,
                progress=progress,
            ),
            lambda result: QMessageBox.information(
                self,
                "Private ratings sheet exported",
                f"Saved all 2,254 players × 31 exact ratings to:\n{Path(result)}\n\n"
                "This CSV contains retail-derived names and values from your own game. "
                "Keep it private; share Mod Studio projects, not this sheet.",
            ),
            True,
        )

    def _import_player_rating_sheet(self) -> None:
        """Validate a private CSV first; never mutate from the file chooser."""

        reason = str(
            self.import_ratings_sheet_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot import ratings sheet yet",
                reason,
            )
            return
        if not self.roster_mode or self.model is None:
            return
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose private APF player ratings sheet",
            str(Path.home()),
            "APF Player Ratings Sheet (*.csv)",
        )
        if not source:
            return
        path = Path(source)
        if path.suffix.casefold() != ".csv":
            QMessageBox.information(
                self,
                "Choose a CSV ratings sheet",
                "APF player ratings sheets use the .csv extension. No project edit was made.",
            )
            return
        selected = self._selected_row()
        preserve_row_id = selected.row_id if selected is not None else None
        self.run_task(
            "Checking private APF ratings sheet",
            lambda progress: self.facade.preview_player_rating_sheet(
                path, progress
            ),
            lambda preview: self._rating_sheet_preview_complete(
                path, preview, preserve_row_id
            ),
            True,
        )

    def _rating_sheet_preview_complete(
        self,
        source: Path,
        preview: object,
        preserve_row_id: str | None,
    ) -> None:
        """Show the immutable plan and queue Apply only after explicit consent."""

        dialog = RatingSheetImportPreviewDialog(source, preview, self)
        accepted = dialog.exec_() == QDialog.Accepted
        allow_conflicts = dialog.allow_conflicts
        apply_enabled = dialog.apply_button.isEnabled()
        dialog.deleteLater()
        if not accepted or not apply_enabled:
            return
        # The preview worker is still registered while its success callback is
        # running. Queue the write so the product's normal blocking-operation
        # guard sees an idle worker set and cannot discard the explicit Apply.
        QTimer.singleShot(
            0,
            lambda: self._apply_player_rating_sheet_preview(
                preview,
                allow_conflicts=allow_conflicts,
                preserve_row_id=preserve_row_id,
            ),
        )

    def _apply_player_rating_sheet_preview(
        self,
        preview: object,
        *,
        allow_conflicts: bool,
        preserve_row_id: str | None,
    ) -> None:
        self.run_task(
            "Applying reviewed APF ratings sheet",
            lambda progress: self.facade.apply_player_rating_sheet(
                preview,
                allow_conflicts=allow_conflicts,
                progress=progress,
            ),
            lambda receipt: self._rating_sheet_import_complete(
                receipt, preserve_row_id
            ),
            True,
        )

    def _rating_sheet_import_complete(
        self,
        receipt: object,
        preserve_row_id: str | None,
    ) -> None:
        self.refresh(preserve_row_id)
        self._selection_changed()
        changed = int(getattr(receipt, "changed_count"))
        if changed:
            self.modifiedChanged.emit()
        replacements = int(getattr(receipt, "replacement_count"))
        reverts = int(getattr(receipt, "revert_count"))
        conflicts = int(getattr(receipt, "conflict_count"))
        undo_actions = int(getattr(receipt, "undo_action_count"))
        QMessageBox.information(
            self,
            "Ratings sheet applied" if changed else "Ratings sheet already matched",
            (
                f"Applied {changed:,} project changes: {replacements:,} replacements "
                f"and {reverts:,} source reverts."
                + (
                    f"\nExplicitly resolved {conflicts:,} conflicts with earlier project edits."
                    if conflicts
                    else ""
                )
                + (
                    "\n\nOne Undo restores the complete rating-edit set that existed before import."
                    if undo_actions == 1
                    else "\n\nNo Undo action was added because the project did not change."
                )
                + (
                    "\n\nThe private CSV was not added to this shareable project."
                )
            ),
        )

    def _update_buttons(self) -> None:
        self._sync_inspector_pagination(
            previous_available=False,
            next_available=False,
            ready=False,
        )
        self.page.setText("Page 0 of 0")
        if self.model is not None:
            rows_tip = (
                "Save every row matching the current search and filters as useful "
                "JSON or CSV."
            )
            self.export_rows_button.setEnabled(True)
            self.export_rows_button.setToolTip(rows_tip)
            self.export_rows_button.setProperty("disableReason", "")
        else:
            rows_tip = (
                "Load a supported APF game first, then export decoded inspector rows."
            )
            self.export_rows_button.setEnabled(True)
            self.export_rows_button.setToolTip(rows_tip)
            self.export_rows_button.setProperty("disableReason", rows_tip)
        ratings_ready = self.roster_mode and self.model is not None
        if ratings_ready:
            export_rtip = (
                "Export all 2,254 players and all 31 exact base ratings as one "
                "private CSV. It contains data derived from your game copy and "
                "never enters a shareable project."
            )
            import_rtip = (
                "Ctrl+Shift+I · Choose a private Mod Studio ratings CSV, validate "
                "every row without changing the project, then review replacements, "
                "source reverts, unchanged cells, conflicts, and errors before an "
                "explicit Apply."
            )
            self.export_ratings_sheet_button.setEnabled(True)
            self.export_ratings_sheet_button.setToolTip(export_rtip)
            self.export_ratings_sheet_button.setProperty("disableReason", "")
            self.import_ratings_sheet_button.setEnabled(True)
            self.import_ratings_sheet_button.setToolTip(import_rtip)
            self.import_ratings_sheet_button.setProperty("disableReason", "")
        else:
            rtip = (
                "Load a supported APF game first, then Export/Import ratings sheet."
                if self.roster_mode
                else "Ratings sheet actions are only available in the Roster workspace."
            )
            self.export_ratings_sheet_button.setEnabled(True)
            self.export_ratings_sheet_button.setToolTip(rtip)
            self.export_ratings_sheet_button.setProperty("disableReason", rtip)
            self.import_ratings_sheet_button.setEnabled(True)
            self.import_ratings_sheet_button.setToolTip(rtip)
            self.import_ratings_sheet_button.setProperty("disableReason", rtip)
        self._update_bulk_audio_export_controls()
        if self.model is None:
            tip = "Select a playable sound row first."
            self.play_audio_button.setEnabled(True)
            self.play_audio_button.setToolTip(tip)
            self.play_audio_button.setProperty("disableReason", tip)
            self.export_bank_button.setVisible(False)
            self.export_external_bank_button.setVisible(False)
            self.export_external_bank_button.setEnabled(True)
            self.export_external_bank_button.setToolTip('Select an external bank row first.')
            self.export_external_bank_button.setProperty("disableReason", 'Select an external bank row first.')
            self.export_matching_button.setEnabled(True)
            self.export_matching_button.setToolTip('Load a supported APF game first, then export matching sounds.')
            self.export_matching_button.setProperty("disableReason", 'Load a supported APF game first, then export matching sounds.')


InspectorLoader = Callable[[ApfInspectorService], tuple[str, PagedModel]]


class InspectorCategoryPage(QWidget):
    """A live semantic model and raw asset inventory in one category tab."""

    modifiedChanged = pyqtSignal()

    def __init__(
        self,
        facade: ApfStudioFacade,
        category: ApfCategory,
        run_task: TaskRunner,
        inspector_title: str,
        loader: InspectorLoader,
        *,
        run_when_idle: IdleRunner | None = None,
        include_assets: bool = True,
        packaged_findings: bool = False,
    ):
        super().__init__()
        self.facade = facade
        self.category = category
        self.run_task = run_task
        self.loader = loader
        self.include_assets = include_assets
        self.packaged_findings = packaged_findings
        self._requested_workspace = "primary"
        self._loaded_source: str | None = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(category))
        self.capabilities = CapabilityPanel(category)
        layout.addWidget(self.capabilities)
        self.inspector = InspectorBrowser(
            inspector_title,
            facade,
            run_task,
            run_when_idle=run_when_idle,
            audio_mode=category is ApfCategory.AUDIO,
            text_mode=category is ApfCategory.MENUS,
            roster_mode=category is ApfCategory.ROSTERS,
            roster_writes_enabled=category is ApfCategory.ROSTERS,
        )
        self.assets = (
            AssetBrowser(facade, category, run_task) if include_assets else None
        )
        self.roster_planner = (
            RosterReservePlanner(facade)
            if category is ApfCategory.ROSTERS
            else None
        )
        self.save_roster_players = (
            SaveRosterPlayersPanel(run_task)
            if category is ApfCategory.ROSTERS
            else None
        )
        self.save_playbooks = (
            SavePlaybookAssignmentsPanel(run_task)
            if category is ApfCategory.PLAYBOOKS
            else None
        )
        self.playbook_routes = (
            PlayAssignmentRoutePanel(facade, run_task)
            if category is ApfCategory.PLAYBOOKS
            else None
        )
        # Swapping whole books is a coarse control -- the book names in a save
        # collapse to a handful of real types -- so the product also edits which
        # plays a formation actually offers.
        self.playbook_membership = (
            ApfPlaybookMembershipPanel(facade, run_task)
            if category is ApfCategory.PLAYBOOKS
            else None
        )
        self.workspace_tabs: QTabWidget | None = None
        self.inspector.modifiedChanged.connect(self.modifiedChanged)
        self.inspector.audioAnnotationChanged.connect(
            lambda _row_id: self.modifiedChanged.emit()
        )
        if self.assets is not None:
            self.assets.modifiedChanged.connect(self.modifiedChanged)
        if self.playbook_routes is not None:
            self.playbook_routes.modifiedChanged.connect(self.modifiedChanged)
        if self.playbook_membership is not None:
            self.playbook_membership.modifiedChanged.connect(self.modifiedChanged)
        if not include_assets:
            layout.addWidget(self.inspector, 1)
        elif category in {
            ApfCategory.MENUS,
            ApfCategory.AUDIO,
            ApfCategory.ROSTERS,
            ApfCategory.PLAYBOOKS,
        }:
            # Authoring and audio action stacks need the full working height.
            # Dedicated raw-asset tabs keep universal coverage one click away
            # without squeezing or clipping controls.
            tabs = QTabWidget()
            tabs.setObjectName("workspaceTabs")
            self.workspace_tabs = tabs
            if category is ApfCategory.MENUS:
                tabs.addTab(self.inspector, "&Text Editor")
                tabs.addTab(self.assets, "&Raw Menu Assets")  # type: ignore[arg-type]
            elif category is ApfCategory.ROSTERS:
                # Avoid a second literal ampersand being interpreted as a Qt
                # mnemonic marker and visually eating the tab label.
                tabs.addTab(self.inspector, "Roster + Base Ratings")
                tabs.addTab(self.save_roster_players, "Save Players")  # type: ignore[arg-type]
                tabs.addTab(self.roster_planner, "53-player Planner")  # type: ignore[arg-type]
                tabs.addTab(self.assets, "&Raw Roster Assets")  # type: ignore[arg-type]
            elif category is ApfCategory.PLAYBOOKS:
                tabs.addTab(self.inspector, "PLAY / DRCT Inspector")
                tabs.addTab(self.playbook_membership, "Fine-tune Plays")  # type: ignore[arg-type]
                tabs.addTab(self.playbook_routes, "Assignment Routes")  # type: ignore[arg-type]
                tabs.addTab(self.save_playbooks, "Save Assignments")  # type: ignore[arg-type]
                tabs.addTab(self.assets, "Raw Playbook Assets")  # type: ignore[arg-type]
            else:
                tabs.addTab(self.inspector, "Audio Browser")
                tabs.addTab(self.assets, "Raw Audio Assets")  # type: ignore[arg-type]
            layout.addWidget(tabs, 1)
        else:
            splitter = QSplitter(Qt.Vertical)
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(5)
            splitter.addWidget(self.inspector)
            splitter.addWidget(self.assets)  # type: ignore[arg-type]
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            layout.addWidget(splitter, 1)

    def open_workspace(self, workspace: str) -> None:
        """Select a named inner workspace for deterministic startup and QA."""

        normalized = workspace.strip().casefold().replace("_", "-")
        self._requested_workspace = normalized or "primary"
        if normalized in {"", "primary", "inspector", "browser"}:
            target = 0
        elif normalized in {"save-players", "save-roster-players"} \
                and self.category is ApfCategory.ROSTERS:
            target = 1
        elif normalized == "roster-planner" and self.category is ApfCategory.ROSTERS:
            target = 2
        elif normalized in {"save-playbooks", "save-assignments"} \
                and self.category is ApfCategory.PLAYBOOKS:
            target = 2
        elif normalized in {"assignment-routes", "route-clone", "routes"} \
                and self.category is ApfCategory.PLAYBOOKS:
            target = 1
        elif normalized == "soundtrack" and self.category is ApfCategory.AUDIO:
            target = 0
        elif normalized == "raw-assets" and self.workspace_tabs is not None:
            target = self.workspace_tabs.count() - 1
        else:
            raise ValueError(
                f"Workspace {workspace!r} is not available in {self.category.title}"
            )
        if self.workspace_tabs is not None:
            self.workspace_tabs.setCurrentIndex(target)
        if (
            normalized == "soundtrack"
            and self.inspector.model is not None
            and not self.inspector._soundtrack_album_mode
        ):
            self.inspector._toggle_soundtrack_album()

    def set_context(self, service: ApfInspectorService | None) -> None:
        if self.facade.source_ready:
            count = (
                len(
                    self.facade.browse_assets(
                        category=self.category,
                        limit=len(self.facade.require_catalog().assets) + 1,
                    )
                )
                if self.assets is not None
                else 0
            )
            self.capabilities.set_cards(
                self.facade.capability_cards(self.category),
                catalog_ready=True,
                inventory_count=count,
            )
        else:
            self.capabilities.set_cards(())
        if self.assets is not None:
            self.assets.set_context()
        if self.roster_planner is not None and not self.facade.source_ready:
            self.roster_planner.set_context()
        source_sha = self.facade.source.source_sha256 if self.facade.source else None
        if service is None or source_sha is None:
            self._loaded_source = None
            self.inspector.set_unavailable("Load your APF game to decode this live model.")
            if self.playbook_routes is not None:
                self.playbook_routes.set_model(None)
            return
        if self._loaded_source == source_sha or self._loading:
            return
        self._loading = True
        self.inspector.set_loading(
            "Loading mapped product findings…"
            if self.packaged_findings
            else "Decoding the live model from your game…"
        )

        def operation(progress: Callable[[str, int, int], None]) -> tuple[bool, object]:
            progress(
                f"Loading {self.category.title} findings"
                if self.packaged_findings
                else f"Decoding {self.category.title}",
                0,
                0,
            )
            try:
                return True, self.loader(service)
            except Exception as exc:
                return False, str(exc)

        def complete(result: object) -> None:
            self._loading = False
            ok, value = result  # type: ignore[misc]
            if not ok:
                self.inspector.set_unavailable(str(value))
                return
            summary, model = value  # type: ignore[misc]
            self._loaded_source = source_sha
            self.inspector.set_model(model, summary)
            if self.playbook_routes is not None:
                self.playbook_routes.set_model(model)
            if (
                self._requested_workspace == "soundtrack"
                and not self.inspector._soundtrack_album_mode
            ):
                self.inspector._toggle_soundtrack_album()
            if self.roster_planner is not None:
                self.roster_planner.set_context()

        self.run_task(
            (
                f"Loading {self.category.title} findings"
                if self.packaged_findings
                else f"Decoding {self.category.title}"
            ),
            operation,
            complete,
            False,
        )

    def refresh(self) -> None:
        self.inspector.refresh()
        if self.roster_planner is not None:
            self.roster_planner.set_context()
        if self.assets is not None:
            self.assets.refresh()
        if self.playbook_routes is not None:
            self.playbook_routes.refresh()
        if self.playbook_membership is not None:
            # Without this the panel only ever loaded a book when the user
            # changed the dropdown, because its one construction-time
            # set_context() ran before a source existed. It also has to hear
            # about an opened project so it can show the edits that project
            # already carries.
            self.playbook_membership.set_context()


def _format_summary(values: dict[str, int] | object) -> str:
    if not isinstance(values, dict):
        values = dict(values)  # type: ignore[arg-type]
    return "  •  ".join(
        f"{str(key).replace('_', ' ').title()}: {int(value):,}"
        for key, value in values.items()  # type: ignore[union-attr]
    )


def _load_roster_inspector(service: ApfInspectorService) -> tuple[str, PagedModel]:
    snapshot = service.roster()
    return _format_summary(dict(snapshot.summary)), snapshot.model


def _text_allocation_row(
    allocation: object,
    *,
    txt_pool_ids: frozenset[str],
) -> InspectorRow:
    """Present one writer-owned TXT/STRG allocation as an editable UI row."""

    row_id = str(getattr(allocation, "asset_id"))
    outer_index = int(getattr(allocation, "outer_index"))
    inner_index = int(getattr(allocation, "inner_index"))
    pool_index = int(getattr(allocation, "pool_index"))
    table_name = str(getattr(allocation, "table_name"))
    text = str(getattr(allocation, "text"))
    bank_type = "TXT loc system" if row_id in txt_pool_ids else "STRG"
    kind = (
        "localization_pool_string"
        if bank_type == "TXT loc system"
        else "string_bank_pool_string"
    )
    fields: dict[str, object] = {
        "outer_index": outer_index,
        "inner_index": inner_index,
        "table_name": table_name,
        "bank_type": bank_type,
        "pool_index": pool_index,
        "text": text,
        "allocation_bytes": int(getattr(allocation, "allocation_bytes")),
        "maximum_utf16_units": int(
            getattr(allocation, "maximum_utf16_units")
        ),
        "reference_count": int(getattr(allocation, "reference_count")),
        "editable": bool(getattr(allocation, "editable")),
        "note": str(getattr(allocation, "note")),
    }
    subtitle = (
        f"{table_name} · {bank_type} · pool {pool_index:,} · "
        f"O{outer_index}/I{inner_index}"
    )
    search_text = " ".join(
        (
            row_id,
            kind,
            text,
            subtitle,
            json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str),
        )
    ).casefold()
    return InspectorRow(
        row_id=row_id,
        kind=kind,
        title=text,
        subtitle=subtitle,
        fields=fields,
        _search_text=search_text,
    )


def _load_text_inspector(
    service: ApfInspectorService,
    allocations: tuple[object, ...],
) -> tuple[str, PagedModel]:
    snapshot = service.localization()
    txt_pool_ids = frozenset(row.row_id for row in snapshot.pool.rows)
    allocation_rows = tuple(
        _text_allocation_row(allocation, txt_pool_ids=txt_pool_ids)
        for allocation in allocations
    )
    # Allocation rows supersede the old TXT-only pool rows.  Record rows retain
    # the useful text-ID ownership context without duplicating an editable ID.
    seen = {row.row_id for row in allocation_rows}
    reference_rows = tuple(
        row for row in snapshot.records.rows if row.row_id not in seen
    )
    editable_count = sum(
        bool(getattr(allocation, "editable")) for allocation in allocations
    )
    read_only_count = len(allocations) - editable_count
    txt_allocation_count = sum(
        str(getattr(allocation, "asset_id")) in txt_pool_ids
        for allocation in allocations
    )
    strg_allocation_count = len(allocations) - txt_allocation_count
    bank_ids = {
        (
            int(getattr(allocation, "outer_index")),
            int(getattr(allocation, "inner_index")),
        )
        for allocation in allocations
    }
    summary = {
        "text_banks": len(bank_ids),
        "pool_allocations": len(allocations),
        "editable_allocations": editable_count,
        "read_only_allocations": read_only_count,
        "reference_rows": int(snapshot.summary.get("records", len(reference_rows))),
    }
    model = PagedModel(
        allocation_rows + reference_rows,
        (
            f"{editable_count:,} editable allocations; {read_only_count:,} protected. Shared edits update every listed consumer.",
            f"{txt_allocation_count:,} TXT + {strg_allocation_count:,} STRG allocations across {len(bank_ids):,} banks; TXT references remain read-only context.",
        ),
    )
    return _format_summary(summary), model


def _load_play_inspector(service: ApfInspectorService) -> tuple[str, PagedModel]:
    snapshot = service.playbooks_directors()
    summary = {
        **{f"play_{key}": value for key, value in snapshot.playbook_summary.items()},
        **{f"director_{key}": value for key, value in snapshot.director_summary.items()},
    }
    model = PagedModel(
        snapshot.playbooks.rows + snapshot.directors.rows,
        snapshot.playbooks.findings + snapshot.directors.findings,
    )
    return _format_summary(summary), model


def _load_audio_inspector(service: ApfInspectorService) -> tuple[str, PagedModel]:
    snapshot = service.audio()
    model = PagedModel(
        snapshot.audo.rows
        + snapshot.ausb_banks.rows
        + snapshot.ausb_substreams.rows
        + snapshot.external_banks.rows,
        snapshot.audo.findings,
    )
    return _format_summary(dict(snapshot.summary)), model


def _load_selector_inspector(service: ApfInspectorService) -> tuple[str, PagedModel]:
    snapshot = service.uniform_selectors()
    return _format_summary(dict(snapshot.summary)), snapshot.model


def _load_gameplay_inspector(
    _service: ApfInspectorService,
) -> tuple[str, PagedModel]:
    snapshot = gameplay_snapshot()
    return _format_summary(dict(snapshot.summary)), snapshot.model


class GettingStartedPage(QWidget):
    chooseIso = pyqtSignal()
    chooseFolder = pyqtSignal()
    browseUniforms = pyqtSignal()

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(16)
        hero = QLabel("Make football history look like yours.")
        hero.setObjectName("heroTitle")
        subtitle = QLabel(
            "APF 2K8 Mod Studio turns the proved archive tools into one safe desktop workflow: "
            "load your own game, export a familiar file, replace it, and build a separate game folder."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(980)
        outer.addWidget(hero)
        outer.addWidget(subtitle)

        steps = QHBoxLayout()
        steps.setSpacing(12)
        for number, title, body in (
            ("01", "Load your own APF", "Choose the untouched USA ISO or extracted game folder. Recognition and indexing happen in the background."),
            ("02", "Export, then paint", "Start with a PNG from your copy. Edit it in GIMP or Photoshop while keeping the exact dimensions and channels."),
            ("03", "Replace or revert", "Drop the edited PNG into its panel. Every change gets a badge, individual Revert, and one-step Undo."),
            ("04", "Build and launch", "Create a complete separate game folder, then start that default.xex in your configured Xenia Canary."),
        ):
            card = QFrame()
            card.setObjectName("stepCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 15, 16, 15)
            number_label = QLabel(number)
            number_label.setObjectName("stepNumber")
            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")
            body_label = QLabel(body)
            body_label.setObjectName("cardBody")
            body_label.setWordWrap(True)
            box.addWidget(number_label)
            box.addWidget(title_label)
            box.addWidget(body_label, 1)
            steps.addWidget(card, 1)
        outer.addLayout(steps)

        callout = QFrame()
        callout.setObjectName("callout")
        callout_box = QHBoxLayout(callout)
        callout_box.setContentsMargins(20, 17, 20, 17)
        copy = QVBoxLayout()
        self.ready_title = QLabel("Start with an untouched game")
        self.ready_title.setObjectName("cardTitle")
        self.ready_body = QLabel(
            "The source is never modified. Builds go to a new folder, and shareable projects contain only your replacement PNGs, text, and metadata."
        )
        self.ready_body.setObjectName("cardBody")
        self.ready_body.setWordWrap(True)
        copy.addWidget(self.ready_title)
        copy.addWidget(self.ready_body)
        self.iso_button = QPushButton("Choose ISO")
        self.iso_button.setObjectName("primaryButton")
        self.folder_button = QPushButton("Choose extracted folder")
        self.folder_button.setObjectName("secondaryButton")
        self.uniform_button = QPushButton("Browse uniforms")
        self.uniform_button.setObjectName("secondaryButton")
        self.iso_button.clicked.connect(self.chooseIso)
        self.folder_button.clicked.connect(self.chooseFolder)
        self.uniform_button.clicked.connect(self.browseUniforms)
        callout_box.addLayout(copy, 1)
        callout_box.addWidget(self.uniform_button)
        callout_box.addWidget(self.folder_button)
        callout_box.addWidget(self.iso_button)
        outer.addWidget(callout)

        self.capabilities = CapabilityPanel(ApfCategory.GETTING_STARTED)
        cards = (
            CapabilityCard(
                "apf.product.source",
                "Read-only source contract",
                "The original ISO or extracted game is recognized but never modified.",
                ApfCategory.GETTING_STARTED,
                ApfStatus.EDITABLE,
                ("A failed build cannot publish a partial output folder.",),
            ),
            CapabilityCard(
                "apf.product.projects",
                "Retail-free projects",
                "Share only user-authored replacement PNGs, text, and metadata in .apf2k8mod files.",
                ApfCategory.GETTING_STARTED,
                ApfStatus.EDITABLE,
                ("No original textures or rollback preimages enter a project.",),
            ),
            CapabilityCard(
                "apf.product.coverage",
                "Universal archive browser",
                "All 10,464 indexed records remain browsable; rows distinguish decoded exports from raw-only bundles.",
                ApfCategory.GETTING_STARTED,
                ApfStatus.EXPORT_ONLY,
                ("Decoded inspectors can also export their filtered rows as JSON or CSV.",),
            ),
        )
        self.capabilities.set_cards(cards)
        outer.addWidget(self.capabilities)
        outer.addStretch(1)

    def set_context(self, facade: ApfStudioFacade) -> None:
        if not facade.source_ready:
            self.ready_title.setText("Start with an untouched game")
            self.ready_body.setText(
                "Choose the supported APF 2K8 USA ISO or its extracted folder. Your source is opened read-only."
            )
            tip = (
                "Load your APF game first (Choose ISO / extracted folder), then "
                "Browse uniforms. Click still explains — button stays clickable."
            )
            self.uniform_button.setEnabled(True)
            self.uniform_button.setToolTip(tip)
            self.uniform_button.setProperty("disableReason", tip)
            return
        catalog = facade.require_catalog()
        self.ready_title.setText("Your game is indexed and ready")
        self.ready_body.setText(
            f"{catalog.outer_count:,} outer records and {len(catalog.assets):,} total assets are visible. "
            f"{len(catalog.uniform_assets)} uniform textures, digital_font, and draft_logo are editable now."
        )
        self.uniform_button.setEnabled(True)
        self.uniform_button.setToolTip("Open the Uniforms workspace.")
        self.uniform_button.setProperty("disableReason", "")


class ApfStudioMainWindow(QMainWindow):
    """Flagship APF 2K8 desktop product window."""

    def __init__(
        self,
        facade: ApfStudioFacade | None = None,
        *,
        workspace_store: WorkspaceStateStore | None = None,
        offer_recovery: bool = False,
    ):
        super().__init__()
        self.facade = facade or ApfStudioFacade()
        self.workspace_store = workspace_store
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[_BackgroundTask] = set()
        self._blocking_workers: set[_BackgroundTask] = set()
        self._page_source: dict[ApfCategory, str] = {}
        self._pages: dict[ApfCategory, QWidget] = {}
        self._inspector_service: ApfInspectorService | None = None
        self._last_detail = ""
        self._active_project_path: Path | None = None
        self._active_project_identity: ProjectTargetIdentity | None = None
        self._document_dirty = False
        self._allow_close = False
        self._close_when_workers_finish = False
        self._idle_callbacks: list[Callable[[], None]] = []
        self._pending_source_load: tuple[
            Path, RecoveryCandidate | None, bool, bool
        ] | None = None
        self._source_load_resume_queued = False
        self._active_source_path: Path | None = None
        self._active_source_sha256: str | None = None
        self._workspace_revision = 0
        self._recovery_save_in_flight = False
        self._recovery_save_pending = False
        self._after_recovery_action: Callable[[], None] | None = None
        self._close_when_recovery_finishes = False
        self._queued_source_context: tuple[
            RecoveryCandidate | None, bool
        ] | None = None
        self._save_project_action: QAction | None = None
        self._save_project_as_action: QAction | None = None
        self._recent_source_menu: QMenu | None = None
        self._recent_project_menu: QMenu | None = None
        self._recover_action: QAction | None = None

        self.setObjectName("studioWindow")
        self.setWindowTitle(PRODUCT_NAME)
        icon = _window_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(1480, 920)
        # Its own content needs about 1,128 px, and a 1366-wide laptop must be
        # able to show the whole window rather than clip the footer actions.
        self.setMinimumSize(1040, 600)
        self._build_ui()
        self._build_menu()
        self._install_keyboard_shortcuts()
        self._apply_style()
        self._update_product_state()
        self._activate_page(0, force=True)
        # After the window is up, never during construction: a slow network must
        # not delay the app appearing.
        QTimer.singleShot(1200, self._start_automatic_update_check)
        if offer_recovery and self.workspace_store is not None:
            QTimer.singleShot(0, self._offer_startup_recovery)

    def _build_ui(self) -> None:
        root = QWidget()
        # The update strip sits above everything and stays hidden unless a
        # newer release exists, so the normal window is unchanged.
        shell = QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self._update_banner = update_ui.UpdateBanner()
        shell.addWidget(self._update_banner)
        body = QWidget()
        shell.addWidget(body, 1)
        root_layout = QHBoxLayout(body)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 16, 15, 15)
        sidebar_layout.setSpacing(10)
        brand = QHBoxLayout()
        mark = QLabel("2K8")
        mark.setObjectName("brandMark")
        titles = QVBoxLayout()
        brand_title = QLabel("APF MOD STUDIO")
        brand_title.setObjectName("brandTitle")
        release_label = __version__.replace("0.1.0-alpha.", "Alpha ")
        version = QLabel(f"{release_label} • retail-free")
        version.setObjectName("mutedLabel")
        titles.addWidget(brand_title)
        titles.addWidget(version)
        brand.addWidget(mark)
        brand.addLayout(titles, 1)
        sidebar_layout.addLayout(brand)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.setSelectionMode(QAbstractItemView.SingleSelection)
        self.navigation.setAccessibleName("Modding categories")
        self.navigation.setAccessibleDescription(
            "Choose an APF 2K8 modding workspace. Press Ctrl+1 to focus this list."
        )
        self.navigation.setToolTip(
            "Choose a modding workspace • Ctrl+1 focuses this list"
        )
        for category in APF_CATEGORY_ORDER:
            item = QListWidgetItem(category.title)
            item.setData(Qt.UserRole, category.value)
            item.setSizeHint(QSize(0, 38))
            self.navigation.addItem(item)
        sidebar_layout.addWidget(self.navigation, 1)
        safety = QLabel(
            "SOURCE SAFETY\n\nYour original ISO or game folder is never modified. "
            "Builds publish to a new folder; projects contain only user-authored replacements and metadata."
        )
        safety.setObjectName("safetyCard")
        safety.setWordWrap(True)
        safety.setAccessibleName("Source safety")
        safety.setAccessibleDescription(
            "The original APF ISO or game folder remains unchanged; builds use a new folder."
        )
        sidebar_layout.addWidget(safety)
        root_layout.addWidget(sidebar)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._build_header())
        self.pages = QStackedWidget()
        # The footer is built before the pages because it owns the status line
        # and progress bar every page's run_task writes to. A page constructed
        # against an already-loaded game starts work during construction, and
        # with the footer built afterwards that first status update raised
        # AttributeError and took the window down before it appeared.
        footer = self._build_footer()
        self._build_pages()
        workspace_layout.addWidget(self.pages, 1)
        workspace_layout.addWidget(footer)
        root_layout.addWidget(workspace, 1)

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.currentRowChanged.connect(self._activate_page)
        self.navigation.setCurrentRow(0)

    def _build_menu(self) -> None:
        """Expose standard document commands without crowding the header."""

        file_menu = self.menuBar().addMenu("&File")
        open_iso = file_menu.addAction("Open APF ISO…")
        open_iso.setShortcut("Ctrl+O")
        open_iso.triggered.connect(self._choose_iso)
        open_folder = file_menu.addAction("Open Extracted Game Folder…")
        open_folder.triggered.connect(self._choose_game_folder)
        open_project = file_menu.addAction("Open Project…")
        open_project.setShortcut("Ctrl+Shift+O")
        open_project.triggered.connect(self._open_project)
        self._recent_source_menu = file_menu.addMenu("Open Recent Game")
        self._recent_project_menu = file_menu.addMenu("Open Recent Project")
        file_menu.addSeparator()
        self._save_project_action = file_menu.addAction("Save Project")
        self._save_project_action.setShortcut("Ctrl+S")
        self._save_project_action.triggered.connect(self._save_project)
        self._save_project_as_action = file_menu.addAction("Save Project As…")
        self._save_project_as_action.setShortcut("Ctrl+Shift+S")
        self._save_project_as_action.triggered.connect(self._choose_save_project_as)
        self._recover_action = file_menu.addAction("Recover Unsaved Edits…")
        self._recover_action.triggered.connect(self._recover_from_menu)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self._refresh_recent_menus()
        self._install_help_menu()

    def _install_help_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        check_action = help_menu.addAction("Check for Updates…")
        check_action.triggered.connect(self._check_for_updates_now)
        self._auto_update_action = help_menu.addAction(
            "Check for updates automatically"
        )
        self._auto_update_action.setCheckable(True)
        self._auto_update_action.setChecked(update_ui.automatic_checks_enabled())
        self._auto_update_action.toggled.connect(
            update_ui.set_automatic_checks_enabled
        )
        help_menu.addSeparator()
        releases_action = help_menu.addAction("Downloads and release notes…")
        releases_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(update_check.RELEASES_PAGE))
        )

    def _check_for_updates_now(self) -> None:
        """A manual check always answers, even to say nothing changed."""

        update_ui.start_check(
            update_check.BUILD_RELEASE_TAG, self._manual_update_result
        )

    def _manual_update_result(self, status: object) -> None:
        update_ui.report_manual_check(self, status)
        banner = getattr(self, "_update_banner", None)
        if banner is not None and getattr(status, "available", False):
            banner.show_status(status)

    def _start_automatic_update_check(self) -> None:
        """Quiet on startup: only a genuinely newer release shows anything."""

        if not update_ui.automatic_checks_enabled():
            return
        banner = getattr(self, "_update_banner", None)
        if banner is None:
            return
        update_ui.explain_automatic_checks_once(self)
        update_ui.start_check(update_check.BUILD_RELEASE_TAG, banner.show_status)

    def _install_keyboard_shortcuts(self) -> None:
        """Expose the shell navigation even when focus is deep in an editor."""

        self.find_shortcut = QShortcut(QKeySequence.Find, self)
        self.find_shortcut.setContext(Qt.WindowShortcut)
        self.find_shortcut.activated.connect(self._focus_current_search)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.sidebar_shortcut.setContext(Qt.WindowShortcut)
        self.sidebar_shortcut.activated.connect(self._focus_category_navigation)
        # Escape clears the focused search box (or the page's studioSearch field).
        self.clear_search_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.clear_search_shortcut.setContext(Qt.WindowShortcut)
        self.clear_search_shortcut.activated.connect(self._clear_current_search)
        # Ctrl+/ shows a short keyboard cheat sheet in the status line.
        self.help_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        self.help_shortcut.setContext(Qt.WindowShortcut)
        self.help_shortcut.activated.connect(self._show_keyboard_hints)

    def _focus_category_navigation(self) -> None:
        self.navigation.setFocus(Qt.ShortcutFocusReason)
        self.operation_status.setText(
            "Categories focused • ↑↓ to move • Enter to open • Ctrl+F for search"
        )

    def _current_search_field(self) -> QLineEdit | None:
        page = self.pages.currentWidget()
        if page is None:
            return None
        fields = tuple(page.findChildren(QLineEdit))

        def available(field: QLineEdit) -> bool:
            # Several APF pages retain searches in inactive inner tabs.  A
            # window-level shortcut must target only the workspace the user
            # can currently operate.
            return field.isEnabled() and field.isVisibleTo(page)

        for field in fields:
            if available(field) and bool(field.property("studioSearch")):
                return field
        for field in fields:
            accessible_name = field.accessibleName().casefold()
            if available(field) and accessible_name.startswith(("search", "filter")):
                return field
        for field in fields:
            placeholder = field.placeholderText().strip().casefold()
            if available(field) and placeholder.startswith(("search", "filter")):
                return field
        return None

    def _focus_current_search(self) -> None:
        field = self._current_search_field()
        if field is None:
            self.operation_status.setText(
                "This workspace has no available search box • press Ctrl+1 for categories"
            )
            return
        field.setFocus(Qt.ShortcutFocusReason)
        field.selectAll()
        self.operation_status.setText(
            "Search ready • type to filter • Esc clears • tips: logo_l0, number_0_color, font_albedo"
        )

    def _clear_current_search(self) -> None:
        """Clear the workspace search when Escape is pressed on a search field."""

        focused = self.focusWidget()
        field = self._current_search_field()
        if isinstance(focused, QLineEdit) and focused.text():
            focused.clear()
            self.operation_status.setText("Search cleared")
            return
        if field is not None and field.text():
            field.clear()
            field.setFocus(Qt.ShortcutFocusReason)
            self.operation_status.setText("Search cleared")

    def _show_keyboard_hints(self) -> None:
        self.operation_status.setText(
            "Keys: Ctrl+F search · Esc clear search · Ctrl+1 categories · "
            "Ctrl+O load game · Ctrl+S save project · Ctrl+/ this help"
        )

    def _workspace_state(self) -> object | None:
        if self.workspace_store is None:
            return None
        try:
            return self.workspace_store.read()
        except Exception as exc:
            if hasattr(self, "operation_status"):
                self.operation_status.setText(
                    f"Recent-file state is unavailable: {str(exc).strip()}"
                )
            return None

    @staticmethod
    def _valid_recent_source(path: Path) -> bool:
        try:
            info = path.lstat()
        except (FileNotFoundError, OSError):
            return False
        return not path.is_symlink() and (path.is_file() or path.is_dir())

    @staticmethod
    def _valid_recent_project(path: Path) -> bool:
        try:
            info = path.lstat()
        except (FileNotFoundError, OSError):
            return False
        return (
            path.suffix.casefold() == PROJECT_EXTENSION
            and not path.is_symlink()
            and path.is_file()
            and info.st_nlink == 1
        )

    def _refresh_recent_menus(self) -> None:
        state = self._workspace_state()
        blocking = bool(self._blocking_workers)
        if self._recent_source_menu is not None:
            self._recent_source_menu.clear()
            sources = tuple(getattr(state, "recent_sources", ()))
            if not sources:
                empty = self._recent_source_menu.addAction("No recent games")
                empty.setEnabled(False)
            for value in sources:
                path = Path(value)
                action = self._recent_source_menu.addAction(path.name)
                action.setToolTip(str(path))
                action.setEnabled(self._valid_recent_source(path) and not blocking)
                action.triggered.connect(
                    lambda _checked=False, selected=path:
                    self.load_source_path(selected)
                )
        if self._recent_project_menu is not None:
            self._recent_project_menu.clear()
            projects = tuple(getattr(state, "recent_projects", ()))
            if not projects:
                empty = self._recent_project_menu.addAction("No recent projects")
                empty.setEnabled(False)
            for value in projects:
                path = Path(value)
                action = self._recent_project_menu.addAction(path.name)
                action.setToolTip(str(path))
                action.setEnabled(
                    self.facade.source_ready
                    and self._valid_recent_project(path)
                    and not blocking
                )
                action.triggered.connect(
                    lambda _checked=False, selected=path:
                    self._request_project_load(selected)
                )
        if self._recover_action is not None:
            candidate = None
            if self.workspace_store is not None:
                try:
                    candidate = self.workspace_store.recovery_candidate(
                        require_source=False
                    )
                except Exception:
                    candidate = None
            self._recover_action.setEnabled(candidate is not None and not blocking)

    def _prompt_recovery_decision(self, candidate: RecoveryCandidate) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Recover unsaved edits?")
        box.setText(
            "Mod Studio found an autosaved edit set from an interrupted session."
        )
        box.setInformativeText(
            f"Source: {candidate.source_path.name}\n"
            "The private recovery file contains user-authored replacements only."
        )
        recover = box.addButton("Recover Edits", QMessageBox.AcceptRole)
        later = box.addButton("Not Now", QMessageBox.RejectRole)
        discard = box.addButton("Discard Recovery", QMessageBox.DestructiveRole)
        box.setDefaultButton(recover)
        box.setEscapeButton(later)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is recover:
            return "recover"
        if clicked is discard:
            return "discard"
        return "later"

    def _offer_startup_recovery(self) -> None:
        if self.workspace_store is None:
            return
        try:
            candidate = self.workspace_store.recovery_candidate(require_source=True)
        except Exception as exc:
            self.operation_status.setText(
                f"Recovery state could not be checked: {str(exc).strip()}"
            )
            return
        if candidate is None:
            self._refresh_recent_menus()
            return
        decision = self._prompt_recovery_decision(candidate)
        if decision == "recover":
            self._recover_candidate(candidate)
        elif decision == "discard":
            self._clear_recovery_candidate(candidate)

    def _offer_matching_recovery_for_active_source(self) -> None:
        if self.workspace_store is None:
            return
        try:
            candidate = self.workspace_store.recovery_candidate(require_source=True)
        except Exception as exc:
            self.operation_status.setText(
                f"Recovery state could not be checked: {str(exc).strip()}"
            )
            return
        if candidate is None or not self._candidate_matches_active_source(candidate):
            self._refresh_recent_menus()
            return
        decision = self._prompt_recovery_decision(candidate)
        if decision == "recover":
            self._load_project_path(candidate.project_path, recovery=True)
        elif decision == "discard":
            self._clear_recovery_candidate(candidate)

    def _recover_from_menu(self, _checked: bool = False) -> None:
        if self.workspace_store is None:
            return
        try:
            candidate = self.workspace_store.recovery_candidate(require_source=False)
        except Exception as exc:
            self._show_error(f"Recovery state could not be read: {str(exc).strip()}")
            return
        if candidate is None:
            self.operation_status.setText("No unsaved recovery project is available.")
            self._refresh_recent_menus()
            return
        if not self._valid_recent_source(candidate.source_path):
            QMessageBox.warning(
                self,
                "Original source needed",
                "The recovery project is safe, but its original APF source is no "
                f"longer available at:\n\n{candidate.source_path}\n\n"
                "Put your legally dumped ISO or extracted game folder back at that "
                "path, then choose Recover Unsaved Edits again.",
            )
            return
        self._recover_candidate(candidate)

    def _candidate_matches_active_source(
        self, candidate: RecoveryCandidate
    ) -> bool:
        return (
            self.facade.source_ready
            and self._active_source_path == candidate.source_path
            and self._active_source_sha256 == candidate.source_sha256
        )

    def _recover_candidate(self, candidate: RecoveryCandidate) -> None:
        if self._candidate_matches_active_source(candidate):
            self._continue_after_unsaved(
                "Recovering the autosave",
                lambda _discarded: self._load_project_path(
                    candidate.project_path, recovery=True
                ),
            )
            return
        self._request_source_switch(candidate.source_path, recovery=candidate)

    def _clear_recovery_candidate(self, candidate: RecoveryCandidate) -> None:
        if self.workspace_store is None:
            return
        try:
            self.workspace_store.clear_recovery(expected=candidate)
        except Exception as exc:
            self.operation_status.setText(
                f"Recovery state could not be cleared: {str(exc).strip()}"
            )
        self._refresh_recent_menus()

    def _clear_recovery_for_source(
        self, source_path: Path | None, source_sha256: str | None
    ) -> None:
        if self.workspace_store is None:
            return
        try:
            self.workspace_store.clear_recovery_for_source(
                source_path, source_sha256
            )
        except Exception as exc:
            self.operation_status.setText(
                f"Recovery state could not be cleared: {str(exc).strip()}"
            )
        self._refresh_recent_menus()

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setMinimumHeight(72)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        # Plain QLabels reported their whole sentence as a hard minimum width,
        # so on a narrow window this row had to compress past what it could
        # give and the title rendered *underneath* the status pill. Eliding
        # labels shrink instead and keep the full text on hover.
        self.page_eyebrow = WordElidedLabel("ALL-PRO FOOTBALL 2K8 • MODDING WORKSPACE")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = WordElidedLabel(ApfCategory.GETTING_STARTED.title)
        self.page_title.setObjectName("pageTitle")
        for label in (self.page_eyebrow, self.page_title):
            label.setMinimumWidth(0)
            label.setSizePolicy(
                QSizePolicy.Ignored, label.sizePolicy().verticalPolicy()
            )
        titles.addWidget(self.page_eyebrow)
        titles.addWidget(self.page_title)
        # The titles absorb the slack themselves, so the header actions keep
        # their full width and nothing has to overlap to fit.
        layout.addLayout(titles, 1)
        self.source_pill = QLabel("●  No game loaded")
        self.source_pill.setObjectName("sourcePill")
        self.source_pill.setProperty("ready", False)
        self.source_pill.setAccessibleName("Loaded game status")
        self.source_pill.setToolTip(
            "Load your own APF ISO or extracted game folder to enable editing and builds."
        )
        self.source_pill.setAccessibleDescription(self.source_pill.toolTip())
        self.open_project_button = QPushButton("Open Project")
        self.open_project_button.setObjectName("secondaryButton")
        self.open_project_button.setToolTip(
            "Apply a retail-free .apf2k8mod project after loading your own game."
        )
        self.open_project_button.setAccessibleName("Open an APF Mod Studio project")
        self.open_project_button.setAccessibleDescription(
            self.open_project_button.toolTip()
        )
        self.save_project_button = QPushButton("Save Project")
        self.save_project_button.setObjectName("secondaryButton")
        self.save_project_button.setToolTip(
            "Save user-authored replacements and metadata only—never retail game data."
        )
        self.save_project_button.setAccessibleName("Save the current APF mod project")
        self.save_project_button.setAccessibleDescription(
            self.save_project_button.toolTip()
        )
        self.open_source_button = QToolButton()
        self.open_source_button.setObjectName("primaryButton")
        self.open_source_button.setText("Load APF Game")
        self.open_source_button.setToolTip(
            "Choose your legally dumped APF ISO or an extracted game folder."
        )
        self.open_source_button.setAccessibleName("Load an APF game")
        self.open_source_button.setAccessibleDescription(
            self.open_source_button.toolTip()
        )
        self.open_source_button.setPopupMode(QToolButton.InstantPopup)
        source_menu = QMenu(self.open_source_button)
        choose_iso = source_menu.addAction("Choose original ISO…")
        choose_folder = source_menu.addAction("Choose extracted game folder…")
        choose_iso.triggered.connect(self._choose_iso)
        choose_folder.triggered.connect(self._choose_game_folder)
        self.open_source_button.setMenu(source_menu)
        self.open_project_button.clicked.connect(self._open_project)
        self.save_project_button.clicked.connect(self._save_project)
        layout.addWidget(self.source_pill)
        layout.addWidget(self.open_project_button)
        layout.addWidget(self.save_project_button)
        layout.addWidget(self.open_source_button)
        return header

    def _build_pages(self) -> None:
        specialized: dict[ApfCategory, tuple[str, InspectorLoader]] = {
            ApfCategory.ROSTERS: ("Live roster model", _load_roster_inspector),
            ApfCategory.TEAM_IDENTITY: ("Team uniform-selector ownership", _load_selector_inspector),
            ApfCategory.MENUS: (
                "Live localization and string pools",
                lambda service: _load_text_inspector(
                    service,
                    self.facade.localization_text_allocations(),
                ),
            ),
            ApfCategory.AUDIO: ("Complete AUDO and AUSB identity model", _load_audio_inspector),
            ApfCategory.GAMEPLAY: (
                "Mapped sliders and retained draft lineage",
                _load_gameplay_inspector,
            ),
            ApfCategory.PLAYBOOKS: ("PLAY and DRCT structural inspector", _load_play_inspector),
        }
        for category in APF_CATEGORY_ORDER:
            if category is ApfCategory.GETTING_STARTED:
                page: QWidget = GettingStartedPage()
                page.chooseIso.connect(self._choose_iso)  # type: ignore[attr-defined]
                page.chooseFolder.connect(self._choose_game_folder)  # type: ignore[attr-defined]
                page.browseUniforms.connect(  # type: ignore[attr-defined]
                    lambda: self.navigation.setCurrentRow(
                        APF_CATEGORY_ORDER.index(ApfCategory.UNIFORMS)
                    )
                )
            elif category is ApfCategory.UNIFORMS:
                page = UniformStudioPage(self.facade, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            elif category is ApfCategory.STADIUMS:
                page = StadiumStudioPage(self.facade, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            elif category is ApfCategory.SCOREBUG:
                page = ScorebugStudioPage(self.facade, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
                # The scorebug's team-logo component is not an asset browser
                # row, so it hands itself over through the page instead.
                page.openWorkspaceRequested.connect(self._open_workspace_route)  # type: ignore[attr-defined]
            elif category is ApfCategory.FIELD_ART:
                page = FieldArtStudioPage(self.facade, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            elif category is ApfCategory.LOGOS:
                page = LogosStudioPage(self.facade, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            elif category in specialized:
                inspector_title, loader = specialized[category]
                page = InspectorCategoryPage(
                    self.facade,
                    category,
                    self._run_task,
                    inspector_title,
                    loader,
                    run_when_idle=self._run_when_idle,
                    include_assets=category is not ApfCategory.GAMEPLAY,
                    packaged_findings=category is ApfCategory.GAMEPLAY,
                )
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            else:
                page = CatalogCategoryPage(self.facade, category, self._run_task)
                page.modifiedChanged.connect(self._mark_document_changed)  # type: ignore[attr-defined]
            self._pages[category] = page
            self.pages.addWidget(self._wrap_scrollable_page(page))
        # Every asset browser on every page -- including the ones nested in
        # workspace tabs -- can hand a row to the workspace that owns its
        # writer.  Connecting them here keeps that one rule in one place.
        for page in self._pages.values():
            for browser in page.findChildren(AssetBrowser):
                browser.openWorkspaceRequested.connect(self._open_workspace_route)

    def _open_workspace_route(self, handoff: WorkspaceHandoff) -> None:
        """Open a browsed row in the workspace whose proved writer owns it."""

        route = handoff.route
        page = self._pages.get(route.category)
        focus = getattr(page, "focus_workspace_route", None)
        if page is None or focus is None:
            self.operation_status.setText(
                f"{handoff.asset_name} is edited in {route.destination}."
            )
            return
        self.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(route.category))
        image = Path(handoff.image) if handoff.image else None
        try:
            opened = bool(focus(route, image))
        except Exception:  # noqa: BLE001 - navigation must not take the shell down
            # The fallback below states where the row is edited, so a failed
            # preselect degrades to directions rather than to a crash.
            opened = False
        if opened:
            self.operation_status.setText(
                f"{handoff.asset_name} opened in {route.destination}"
                + (" with your image staged." if image is not None else ".")
            )
            return
        QMessageBox.information(
            self,
            f"Open {handoff.asset_name} in {route.destination}",
            f"{route.summary}\n\n"
            f"This build could not preselect it automatically — load your game "
            f"if you have not yet, then choose it in {route.destination}. Your "
            "original dump is never modified.",
        )

    def _wrap_scrollable_page(self, page: QWidget) -> QScrollArea:
        """Host a workspace page inside a resizable vertical scroll area.

        The stacked workspace previously inherited the tallest page's full
        content height as the window's minimum, which pushed the footer action
        bar (Configure Xenia / Build Game Folder / Launch in Xenia) off a 1080p
        screen.  Wrapping each page keeps the shell's minimum height bounded by
        :data:`WORKSPACE_PAGE_MIN_HEIGHT` while a taller page scrolls in place
        rather than growing the window.  The page keeps its own identity in
        ``self._pages`` so category dispatch and inspector wiring are unchanged.
        """

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        # QScrollArea.setWidget() force-enables autoFillBackground on the page
        # it adopts, which repainted every workspace page in the platform's
        # default light palette on top of the dark theme.  Undo it so pages
        # stay transparent over the shared #0b111c workspace background.
        page.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setMinimumHeight(WORKSPACE_PAGE_MIN_HEIGHT)
        return scroll

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setMinimumHeight(68)
        layout = QHBoxLayout(footer)
        # The action row needs about 800 px of its own; at the 1040-wide floor
        # the workspace column is 790, and the 10 px shortfall was clipping the
        # last button's label. Trim the gutters rather than the buttons.
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        status_box = QVBoxLayout()
        status_box.setSpacing(5)
        self.operation_status = QLabel("Load your APF game to begin.")
        self.operation_status.setObjectName("operationStatus")
        # A plain QLabel never elides, so a long status sentence would become a
        # hard minimum width for the footer and then for the window. Let it
        # shrink; the full text stays available on hover.
        self.operation_status.setSizePolicy(
            QSizePolicy.Ignored, self.operation_status.sizePolicy().verticalPolicy()
        )
        self.operation_status.setMinimumWidth(0)
        self.operation_status.setAccessibleName("Current operation status")
        self.operation_status.setAccessibleDescription(
            "Reports what the app is doing and whether an operation succeeded."
        )
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Current operation progress")
        self.progress.setAccessibleDescription(
            "Progress for indexing, exporting, replacing, saving, or building."
        )
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        status_box.addWidget(self.operation_status)
        status_box.addWidget(self.progress)
        layout.addLayout(status_box, 1)
        self.modified_count = QLabel("0 edits")
        self.modified_count.setObjectName("editCount")
        self.modified_count.setAccessibleName("Pending edit count")
        self.modified_count.setAccessibleDescription(
            "Edits included in the next modded game-folder build."
        )
        self.undo_button = QPushButton("Undo")
        self.undo_button.setObjectName("utilityButton")
        self.revert_all_button = QPushButton("Revert All")
        self.revert_all_button.setObjectName("dangerQuietButton")
        self.configure_xenia_button = QPushButton("Configure Xenia")
        self.configure_xenia_button.setObjectName("utilityButton")
        self.title_update_button = QPushButton("Title Update 1.1…")
        self.title_update_button.setObjectName("utilityButton")
        self.build_button = QPushButton("Build Game Folder")
        self.build_button.setObjectName("buildButton")
        self.launch_button = QPushButton("Launch in Xenia")
        self.launch_button.setObjectName("launchButton")
        self.undo_button.setToolTip("Undo the most recent edit in this project.")
        self.revert_all_button.setToolTip("Nothing to revert—there are no active edits.")
        self.configure_xenia_button.setToolTip("Choose Xenia Canary and its Wine launcher.")
        self.title_update_button.setToolTip(
            "Choose the Xbox 360 APF 2K8 title update 1.1 LIVE package. It is "
            "required on Xenia/Xbox and never shipped for PS3. Launch copies it "
            "into this session's isolated Xenia content folder."
        )
        self.build_button.setToolTip("Create a separate, verified modded game folder.")
        self.launch_button.setToolTip("Launch the most recently built game folder in Xenia.")
        self.undo_button.setAccessibleName("Undo the most recent project edit")
        self.undo_button.setAccessibleDescription(self.undo_button.toolTip())
        self.revert_all_button.setAccessibleName("Revert every project edit")
        self.revert_all_button.setAccessibleDescription(
            "Remove every pending edit after confirmation; the source game is untouched."
        )
        self.configure_xenia_button.setAccessibleName("Configure Xenia launch")
        self.configure_xenia_button.setAccessibleDescription(
            self.configure_xenia_button.toolTip()
        )
        self.title_update_button.setAccessibleName("Install APF title update 1.1")
        self.title_update_button.setAccessibleDescription(
            self.title_update_button.toolTip()
        )
        self.build_button.setAccessibleName("Build a separate modded game folder")
        self.build_button.setAccessibleDescription(self.build_button.toolTip())
        self.launch_button.setAccessibleName("Launch the latest build in Xenia")
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        self.undo_button.clicked.connect(self._undo)
        self.revert_all_button.clicked.connect(self._revert_all)
        self.configure_xenia_button.clicked.connect(self._configure_xenia)
        self.title_update_button.clicked.connect(self._configure_title_update)
        self.build_button.clicked.connect(self._build_game)
        self.launch_button.clicked.connect(self._launch_xenia)
        layout.addWidget(self.modified_count)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.revert_all_button)
        layout.addSpacing(4)
        layout.addWidget(self.configure_xenia_button)
        layout.addWidget(self.title_update_button)
        layout.addSpacing(4)
        layout.addWidget(self.build_button)
        layout.addWidget(self.launch_button)
        return footer

    def _run_task(
        self,
        label: str,
        operation: Callable[[Callable[[str, int, int], None]], Any],
        on_success: Callable[[Any], None] | None = None,
        blocking: bool = True, show_errors: bool = True, on_error: Callable[[str], None] | None = None,
    ) -> bool:
        if blocking and self._workers:
            self.operation_status.setText("Let the current operation finish, then try again.")
            return False
        worker = _BackgroundTask(operation)
        self._workers.add(worker)
        if blocking:
            self._blocking_workers.add(worker)
        worker.signals.progress.connect(self._task_progress)
        worker.signals.failed.connect(
            lambda message, detail, task=worker: self._task_failed(task, message, detail, show_errors, on_error)
        )

        def dispatch(result: object) -> None:
            if on_success is None:
                return
            try:
                on_success(result)
            except BaseException as exc:
                self._show_error(
                    str(exc).strip() or exc.__class__.__name__, traceback.format_exc()
                )

        worker.signals.succeeded.connect(dispatch)
        worker.signals.finished.connect(
            lambda task=worker: self._task_finished(task)
        )
        self.operation_status.setText(label)
        self.progress.setRange(0, 0)
        if blocking:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        self._update_product_state()
        self.thread_pool.start(worker)
        return True

    def _task_progress(self, stage: str, completed: int, total: int) -> None:
        self.operation_status.setText(stage)
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, max(0, int(completed * 1000 / total))))
        else:
            self.progress.setRange(0, 0)

    def _task_failed(self, _worker: _BackgroundTask, message: str, detail: str, show_errors: bool = True, on_error: Callable[[str], None] | None = None) -> None:
        on_error(message) if on_error is not None else None; hint = friendly_fix_hint(message); self._last_detail = f"{message} — {hint}" if hint else message; self.operation_status.setText(self._last_detail) if hasattr(self, "operation_status") else None
        if show_errors: self._show_error(message, detail)

    def _task_finished(self, worker: _BackgroundTask) -> None:
        was_blocking = worker in self._blocking_workers
        self._blocking_workers.discard(worker)
        self._workers.discard(worker)
        if was_blocking:
            QApplication.restoreOverrideCursor()
        if not self._workers:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            if self.facade.source_ready:
                self.operation_status.setText(
                    self._last_detail
                    or "Ready — your source remains untouched until you choose a separate build folder."
                )
            else:
                self.operation_status.setText(
                    self._last_detail or "Load your APF game to begin."
                )
            self._last_detail = ""
        self._update_product_state()
        if not self._workers and self._idle_callbacks:
            callbacks, self._idle_callbacks = self._idle_callbacks, []
            for callback in callbacks:
                QTimer.singleShot(0, callback)
        if not self._workers and self._close_when_workers_finish:
            QTimer.singleShot(0, self.close)

    def _run_when_idle(self, callback: Callable[[], None]) -> None:
        """Run a post-save continuation only after its worker is unregistered."""

        if self._workers:
            self._idle_callbacks.append(callback)
        else:
            QTimer.singleShot(0, callback)

    def _cancel_transient_audio_reads(self) -> bool:
        """Stop private Audio readers before their loaded session can close."""

        page = self._pages.get(ApfCategory.AUDIO)
        if not isinstance(page, InspectorCategoryPage):
            return False
        return page.inspector.cancel_pending_audio_reads()

    def _show_error(self, message: str, detail: str = "") -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle(f"{PRODUCT_NAME} could not finish that")
        hint = friendly_fix_hint(message)
        dialog.setText(message if hint is None else f"{message}\n\n{hint}")
        dialog.setInformativeText(
            "The original game was not modified. Correct the item described above and try again."
        )
        if detail:
            dialog.setDetailedText(detail)
        dialog.exec_()

    def _activate_page(self, row: int, *, force: bool = False) -> None:
        if not 0 <= row < len(APF_CATEGORY_ORDER):
            return
        category = APF_CATEGORY_ORDER[row]
        self.page_title.setText(category.title)
        page = self._pages[category]
        source_key = self.facade.source.source_sha256 if self.facade.source else "not-loaded"
        if not force and self._page_source.get(category) == source_key:
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
            elif isinstance(page, GettingStartedPage):
                page.set_context(self.facade)
            return
        if isinstance(page, GettingStartedPage):
            page.set_context(self.facade)
        elif isinstance(page, InspectorCategoryPage):
            page.set_context(self._inspector_service)
        else:
            set_context = getattr(page, "set_context", None)
            if callable(set_context):
                set_context()
        self._page_source[category] = source_key

    def _mark_document_changed(self) -> None:
        """Record an authored change independently from the active edit count."""

        self._workspace_revision += 1
        self._document_dirty = True
        self._refresh_after_mutation()
        self._save_recovery_snapshot()

    def _save_recovery_snapshot(self) -> None:
        """Coalesce a private, source-fenced replacement-only autosave."""

        store = self.workspace_store
        source_path = self._active_source_path
        source_sha256 = self._active_source_sha256
        if (
            store is None
            or not self._document_dirty
            or source_path is None
            or source_sha256 is None
        ):
            return
        try:
            existing = store.recovery_candidate(require_source=False)
        except Exception as exc:
            self.operation_status.setText(
                f"Edits are staged, but recovery state is unavailable: {str(exc).strip()}"
            )
            return
        if existing is not None and (
            existing.source_path != source_path
            or existing.source_sha256 != source_sha256
        ):
            # One private slot must never overwrite a postponed recovery from
            # another selected source. The user can recover or discard that
            # candidate explicitly from the File menu first.
            self.operation_status.setText(
                "Edits are staged, but autosave is paused because another APF "
                "source has a recovery. Use File → Recover Unsaved Edits first."
            )
            return
        if self._recovery_save_in_flight:
            self._recovery_save_pending = True
            return
        self._recovery_save_in_flight = True
        self._recovery_save_pending = False
        revision = self._workspace_revision
        recovery_path = store.recovery_path
        worker = _BackgroundTask(
            lambda progress: self.facade.save_recovery_project(
                recovery_path, source_sha256, progress
            )
        )
        self._workers.add(worker)

        def success(_result: object) -> None:
            if (
                not self._document_dirty
                or self._active_source_path != source_path
                or self._active_source_sha256 != source_sha256
            ):
                self._clear_recovery_for_source(source_path, source_sha256)
                return
            try:
                store.register_recovery(
                    source_path=source_path,
                    source_sha256=source_sha256,
                    project_path=recovery_path,
                )
            except Exception as exc:
                self.operation_status.setText(
                    "Edits are staged, but recovery metadata could not update: "
                    f"{str(exc).strip()}"
                )
            else:
                if revision == self._workspace_revision:
                    self.operation_status.setText(
                        "Autosaved unsaved edits • original game remains read-only"
                    )
                self._refresh_recent_menus()

        def failed(message: str, _detail: str) -> None:
            self.operation_status.setText(
                f"Edits are staged, but autosave could not update: {message}"
            )

        def finished() -> None:
            self._recovery_save_in_flight = False
            self._task_finished(worker)
            pending = self._recovery_save_pending
            self._recovery_save_pending = False
            action = self._after_recovery_action
            self._after_recovery_action = None
            if self._close_when_recovery_finishes:
                self._close_when_recovery_finishes = False
                self._document_dirty = False
                self._clear_recovery_for_source(source_path, source_sha256)
                self._allow_close = True
                QTimer.singleShot(0, self.close)
                return
            if action is not None:
                QTimer.singleShot(0, action)
            elif pending and self._document_dirty:
                QTimer.singleShot(0, self._save_recovery_snapshot)

        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(failed)
        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def _refresh_after_mutation(self) -> None:
        # Any edit after a build makes that launch target stale.
        self.facade.last_build = None
        self._update_product_state()
        category = APF_CATEGORY_ORDER[max(0, self.navigation.currentRow())]
        page = self._pages[category]
        if isinstance(page, GettingStartedPage):
            page.set_context(self.facade)
        else:
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()

    def _update_product_state(self) -> None:
        ready = self.facade.source_ready
        blocking = bool(self._blocking_workers)
        edit_count = int(getattr(self.facade, "modified_count", 0))
        metadata_count = int(
            getattr(self.facade, "project_metadata_count", 0)
        )
        annotation_count = int(
            getattr(self.facade, "annotation_count", metadata_count)
        )
        project_change_count = edit_count + metadata_count
        has_project_metadata = bool(
            getattr(self.facade, "has_project_metadata", metadata_count > 0)
        )
        has_project_changes = edit_count > 0 or has_project_metadata
        if self._active_project_path is not None:
            marker = "*" if self._document_dirty else ""
            self.setWindowTitle(
                f"{self._active_project_path.name}{marker} — {PRODUCT_NAME}"
            )
            save_tip = (
                f"Save current changes directly to {self._active_project_path.name}. "
                "The project contains user-authored replacements and metadata only."
            )
        elif self._document_dirty:
            self.setWindowTitle(f"Untitled* — {PRODUCT_NAME}")
            save_tip = (
                f"Name this retail-free edit set as a shareable {PROJECT_EXTENSION} project."
            )
        else:
            self.setWindowTitle(PRODUCT_NAME)
            save_tip = (
                "Save only user-authored replacements and metadata—never retail game data."
            )
        self.source_pill.setText(
            f"●  {self.facade.source_display_name}" if ready else "●  No game loaded"
        )
        self.source_pill.setProperty("ready", ready)
        self.source_pill.style().unpolish(self.source_pill)
        self.source_pill.style().polish(self.source_pill)
        if annotation_count:
            self.modified_count.setText(
                f"{edit_count} edit{'s' if edit_count != 1 else ''} • "
                f"{annotation_count} cue label"
                f"{'s' if annotation_count != 1 else ''}"
            )
        elif edit_count == 0 and self._document_dirty:
            self.modified_count.setText("0 edits • unsaved")
        else:
            self.modified_count.setText(
                f"{edit_count} edit{'s' if edit_count != 1 else ''}"
            )
        self.open_source_button.setEnabled(not blocking)
        self.open_project_button.setEnabled(ready and not blocking)
        can_save = ready and self._document_dirty and not blocking
        self.save_project_button.setEnabled(can_save)
        self.save_project_button.setToolTip(save_tip)
        if self._save_project_action is not None:
            self._save_project_action.setEnabled(can_save)
            self._save_project_action.setToolTip(save_tip)
        if self._save_project_as_action is not None:
            self._save_project_as_action.setEnabled(
                ready
                and not blocking
                and (
                    self._active_project_path is not None
                    or has_project_changes
                    or self._document_dirty
                )
            )
        self.undo_button.setEnabled(ready and self.facade.can_undo and not blocking)
        self.revert_all_button.setEnabled(
            ready and has_project_changes and not blocking
        )
        self.undo_button.setToolTip(
            "Undo the most recent edit in this project."
            if self.facade.can_undo
            else "Nothing to undo yet."
        )
        self.revert_all_button.setToolTip(
            (
                f"Revert all {edit_count} build edit"
                f"{'s' if edit_count != 1 else ''} and {metadata_count} project "
                f"metadata item{'s' if metadata_count != 1 else ''}."
            )
            if has_project_changes
            else "Nothing to revert—there are no active project changes."
        )
        self.configure_xenia_button.setEnabled(not blocking)
        self.configure_xenia_button.setText(
            "Xenia Configured"
            if self.facade.launcher.settings.configured
            else "Configure Xenia"
        )
        self.title_update_button.setEnabled(not blocking)
        tu_ready = self.facade.launcher.settings.title_update_path is not None
        self.title_update_button.setText(
            "Title Update 1.1 ready" if tu_ready else "Title Update 1.1…"
        )
        self.build_button.setEnabled(ready and not blocking)
        self.build_button.setToolTip(
            "Create a separate, verified modded game folder. Your source stays untouched."
            if ready
            else "Load your APF game before building."
        )
        # Never silent-gray: Launch stays clickable and names the one thing
        # that is missing. The button used to gray out while relabelling itself
        # "Configure Xenia to Launch" -- an instruction on a dead control.
        blocker = self.facade.xenia_blocker
        if blocking:
            blocker = blocker or "An operation is running • wait for it to finish."
        self.launch_button.setEnabled(not blocking)
        self.launch_button.setToolTip(
            blocker or "Launch the most recently built game folder in Xenia."
        )
        self.launch_button.setProperty("disableReason", blocker)
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        if self.facade.last_build is not None and not self.facade.launcher.settings.configured:
            self.launch_button.setText("Configure Xenia to Launch")
        else:
            self.launch_button.setText("Launch in Xenia")

    def _prompt_unsaved_decision(self, context: str) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Save your project changes?")
        box.setText("This project has changes that have not been saved.")
        box.setInformativeText(
            f"{context} can replace the current edit set. Save a retail-free "
            f"{PROJECT_EXTENSION} project, discard the changes, or cancel."
        )
        save = box.addButton("Save Project", QMessageBox.AcceptRole)
        discard = box.addButton("Discard Changes", QMessageBox.DestructiveRole)
        cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        if clicked is discard:
            return "discard"
        return "cancel"

    def _continue_after_unsaved(
        self,
        context: str,
        action: Callable[[bool], None],
    ) -> None:
        if not self._document_dirty:
            action(False)
            return
        decision = self._prompt_unsaved_decision(context)
        if decision == "discard":
            # Keep the current document dirty until the requested switch
            # actually succeeds. A failed source/project load preserves it.
            if self._recovery_save_in_flight:
                self._recovery_save_pending = False
                self._after_recovery_action = lambda: action(True)
            else:
                action(True)
        elif decision == "save":
            continuation = lambda: action(False)
            if self._recovery_save_in_flight:
                self._recovery_save_pending = False
                self._after_recovery_action = lambda: self._save_project(
                    after_success=continuation
                )
            else:
                self._save_project(after_success=continuation)

    def _choose_iso(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose your untouched APF 2K8 ISO",
            str(Path.home()),
            "Xbox disc image (*.iso *.xiso);;All files (*)",
        )
        if selected:
            self.load_source_path(Path(selected))

    def _choose_game_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose the extracted APF 2K8 game folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly,
        )
        if selected:
            self.load_source_path(Path(selected))

    def load_source_path(self, selected: Path) -> None:
        """Load an explicitly selected source; useful to the CLI and tests."""

        self._request_source_switch(selected)

    def _request_source_switch(
        self,
        selected: Path,
        *,
        recovery: RecoveryCandidate | None = None,
    ) -> None:
        self._continue_after_unsaved(
            "Loading a different APF game",
            lambda discarded: self._dispatch_source_switch(
                selected, recovery=recovery, discarded=discarded
            ),
        )

    def _dispatch_source_switch(
        self,
        selected: Path,
        *,
        recovery: RecoveryCandidate | None,
        discarded: bool,
    ) -> None:
        """Keep the one-argument load hook stable for CLI/test integrations."""

        context = (recovery, discarded)
        self._queued_source_context = context
        try:
            self._load_source_path(selected)
        finally:
            if self._queued_source_context == context:
                self._queued_source_context = None

    def _defer_source_load_until_idle(
        self,
        selected: Path,
        recovery: RecoveryCandidate | None,
        clear_previous_recovery: bool,
        offer_matching_recovery: bool,
    ) -> None:
        """Coalesce source requests while an owned worker drains safely."""

        self._pending_source_load = (
            selected,
            recovery,
            clear_previous_recovery,
            offer_matching_recovery,
        )
        self.operation_status.setText(
            "Cancelling private Audio reads, then opening the selected game…"
        )
        if self._source_load_resume_queued:
            return
        self._source_load_resume_queued = True
        self._run_when_idle(self._resume_pending_source_load)

    def _resume_pending_source_load(self) -> None:
        self._source_load_resume_queued = False
        request, self._pending_source_load = self._pending_source_load, None
        if request is None or self._close_when_workers_finish or self._allow_close:
            return
        selected, recovery, clear_previous_recovery, offer_matching_recovery = request
        self._load_source_path(
            selected,
            recovery=recovery,
            clear_previous_recovery=clear_previous_recovery,
            offer_matching_recovery=offer_matching_recovery,
        )

    def _load_source_path(
        self,
        selected: Path,
        *,
        recovery: RecoveryCandidate | None = None,
        clear_previous_recovery: bool = False,
        offer_matching_recovery: bool = False,
    ) -> None:
        if self._queued_source_context is not None:
            queued_recovery, queued_discard = self._queued_source_context
            self._queued_source_context = None
            if recovery is None:
                recovery = queued_recovery
            clear_previous_recovery = (
                clear_previous_recovery or queued_discard
            )
        self._cancel_transient_audio_reads()
        if self._workers:
            self._defer_source_load_until_idle(
                selected,
                recovery,
                clear_previous_recovery,
                offer_matching_recovery,
            )
            return
        self._pending_source_load = None
        previous_source_path = self._active_source_path
        previous_source_sha256 = self._active_source_sha256
        admitted = self._run_task(
            "Recognizing and indexing your APF game",
            lambda progress: self.facade.load_source(selected, progress),
            lambda catalog: self._source_loaded(
                catalog,
                recovery=recovery,
                clear_previous_recovery=clear_previous_recovery,
                previous_source_path=previous_source_path,
                previous_source_sha256=previous_source_sha256,
                offer_matching_recovery=offer_matching_recovery,
            ),
            True,
        )
        if admitted is False:
            self._defer_source_load_until_idle(
                selected,
                recovery,
                clear_previous_recovery,
                offer_matching_recovery,
            )

    def _source_loaded(
        self,
        catalog: object,
        *,
        recovery: RecoveryCandidate | None = None,
        clear_previous_recovery: bool = False,
        previous_source_path: Path | None = None,
        previous_source_sha256: str | None = None,
        offer_matching_recovery: bool = False,
    ) -> None:
        del catalog
        assert self.facade.source is not None
        self._inspector_service = self.facade.require_inspectors()
        self._page_source.clear()
        self._active_project_path = None
        self._active_project_identity = None
        self._document_dirty = False
        self._workspace_revision += 1
        source = self.facade.source
        self._active_source_path = source.selected_path.resolve(strict=True)
        self._active_source_sha256 = source.source_sha256
        if self.workspace_store is not None:
            try:
                self.workspace_store.record_source(
                    self._active_source_path, self._active_source_sha256
                )
                if clear_previous_recovery:
                    self.workspace_store.clear_recovery_for_source(
                        previous_source_path, previous_source_sha256
                    )
            except Exception as exc:
                self.operation_status.setText(
                    "Game opened, but recent-file state could not update: "
                    f"{str(exc).strip()}"
                )
        mode = "private ISO extraction" if source.extracted_from_iso else "extracted game folder"
        self.source_pill.setToolTip(
            f"{source.game_root}\nLoaded from {mode}.\nThe source is never modified."
        )
        self._last_detail = "Game recognized — all indexed assets are ready to browse."
        self._update_product_state()
        self._activate_page(self.navigation.currentRow(), force=True)
        self._refresh_recent_menus()
        if recovery is not None:
            if not self._candidate_matches_active_source(recovery):
                self._show_error(
                    "The selected APF game does not match the source identity bound "
                    "to this recovery project. The recovery file was kept."
                )
                return
            self._load_project_path(recovery.project_path, recovery=True)
        elif offer_matching_recovery:
            self._offer_matching_recovery_for_active_source()

    def _open_project(self, _checked: bool = False) -> None:
        if not self.facade.source_ready:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Open a retail-free APF Mod Studio project",
            str(Path.home()),
            f"APF 2K8 Mod Studio project (*{PROJECT_EXTENSION})",
        )
        if not selected:
            return
        self._request_project_load(Path(selected))

    def _request_project_load(self, path: Path) -> None:
        self._continue_after_unsaved(
            "Opening another project",
            lambda discarded: self._load_project_path(
                path, clear_previous_recovery=discarded
            ),
        )

    def _load_project_path(
        self,
        path: Path,
        *,
        recovery: bool = False,
        clear_previous_recovery: bool = False,
    ) -> None:
        self._run_task(
            "Opening retail-free project",
            lambda progress: self.facade.load_project(path, progress),
            lambda count: self._project_loaded(
                int(count),
                path,
                recovery=recovery,
                clear_previous_recovery=clear_previous_recovery,
            ),
            True,
        )

    def _project_loaded(
        self,
        count: int,
        path: Path,
        *,
        recovery: bool = False,
        clear_previous_recovery: bool = False,
    ) -> None:
        if recovery:
            self._active_project_path = None
            self._active_project_identity = None
            # An empty recovery means the user intentionally reverted every
            # replacement after the last named save, so it remains dirty.
            self._document_dirty = True
            self._workspace_revision += 1
            self._last_detail = (
                "Recovered the autosaved edits. Save Project to create a named, "
                "shareable copy."
            )
            self._refresh_after_mutation()
            self._refresh_recent_menus()
            return
        identity = self.facade.last_project_identity
        if identity is None or identity.path != path.resolve(strict=True):
            identity = project_target_identity(path)
        self._active_project_path = identity.path
        self._active_project_identity = identity
        self._document_dirty = False
        self._workspace_revision += 1
        self._last_detail = (
            f"Loaded {count} validated edit{'s' if count != 1 else ''} "
            f"from {identity.path.name}."
        )
        if self.workspace_store is not None:
            try:
                self.workspace_store.record_project(identity.path)
                # A successful explicit named load replaces the current edit
                # document. Only a recovery bound to this source is cleared.
                self.workspace_store.clear_recovery_for_source(
                    self._active_source_path, self._active_source_sha256
                )
            except Exception as exc:
                self.operation_status.setText(
                    "Project loaded, but recent-file state could not update: "
                    f"{str(exc).strip()}"
                )
        del clear_previous_recovery
        self._refresh_after_mutation()
        self._refresh_recent_menus()

    def _save_project(
        self,
        _checked: bool = False,
        *,
        after_success: Callable[[], None] | None = None,
    ) -> None:
        if not self.facade.source_ready or not self._document_dirty:
            return
        if (
            self._active_project_path is None
            or self._active_project_identity is None
        ):
            self._choose_save_project_as(after_success=after_success)
            return
        self._save_project_path(
            self._active_project_path,
            expected_target=self._active_project_identity,
            after_success=after_success,
        )

    def _choose_save_project_as(
        self,
        _checked: bool = False,
        *,
        after_success: Callable[[], None] | None = None,
    ) -> None:
        if (
            not self.facade.source_ready
            or not (
                self._active_project_path is not None
                or self.facade.modified_count > 0
                or self._document_dirty
            )
        ):
            return
        initial = self._active_project_path or (
            Path.home() / f"My APF 2K8 Mod{PROJECT_EXTENSION}"
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Save a shareable, retail-free project",
            str(initial),
            f"APF 2K8 Mod Studio project (*{PROJECT_EXTENSION})",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.casefold() != PROJECT_EXTENSION:
            path = path.with_name(path.name + PROJECT_EXTENSION)
        expected_target: ProjectTargetIdentity | None = None
        if os.path.lexists(path):
            try:
                expected_target = project_target_identity(path)
            except ProjectError as exc:
                self._show_error(str(exc), traceback.format_exc())
                return
            answer = QMessageBox.question(
                self,
                "Replace this project file?",
                f"A project named {path.name} already exists. Replace that project archive?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._save_project_path(
            path,
            expected_target=expected_target,
            after_success=after_success,
            inform=True,
        )

    def _save_project_path(
        self,
        path: Path,
        *,
        expected_target: ProjectTargetIdentity | None,
        after_success: Callable[[], None] | None = None,
        inform: bool = False,
    ) -> None:
        if self._recovery_save_in_flight:
            self._recovery_save_pending = False
            self._after_recovery_action = lambda: self._save_project_path(
                path,
                expected_target=expected_target,
                after_success=after_success,
                inform=inform,
            )
            self.operation_status.setText(
                "Finishing the private autosave, then saving your project…"
            )
            return
        self._run_task(
            "Saving retail-free project",
            lambda progress: self.facade.save_project(
                path,
                progress,
                replace=expected_target is not None,
                expected_target=expected_target,
            ),
            lambda result: self._project_saved(
                Path(result),
                after_success=after_success,
                inform=inform,
            ),
            True,
        )

    def _project_saved(
        self,
        path: Path,
        *,
        after_success: Callable[[], None] | None = None,
        inform: bool = False,
    ) -> None:
        identity = self.facade.last_project_identity
        if identity is None or identity.path != path.resolve(strict=True):
            identity = project_target_identity(path)
        self._active_project_path = identity.path
        self._active_project_identity = identity
        self._document_dirty = False
        self._workspace_revision += 1
        self._last_detail = (
            f"Project saved: {identity.path.name} "
            "(user-authored PNGs, text, and metadata only)."
        )
        if self.workspace_store is not None:
            try:
                self.workspace_store.record_project(identity.path)
                self.workspace_store.clear_recovery_for_source(
                    self._active_source_path, self._active_source_sha256
                )
            except Exception as exc:
                self.operation_status.setText(
                    "Project saved, but recent-file state could not update: "
                    f"{str(exc).strip()}"
                )
        self._update_product_state()
        self._refresh_recent_menus()
        if inform:
            QMessageBox.information(
                self,
                "Project saved",
                f"Saved to:\n{identity.path}\n\nThis project contains no original game files or original texture preimages.",
            )
        if after_success is not None:
            self._run_when_idle(after_success)

    def _undo(self) -> None:
        if not self.facade.can_undo:
            return
        self._run_task(
            "Undoing the last edit action",
            lambda progress: self.facade.undo(progress),
            lambda result: (
                self._mark_document_changed()
                if bool(result)
                else self._refresh_after_mutation()
            ),
            True,
        )

    def _revert_all(self) -> None:
        if not self.facade.modified_count:
            return
        answer = QMessageBox.question(
            self,
            "Revert every current edit?",
            f"Remove all {self.facade.modified_count} current edits from this project? You can Undo this action once.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_task(
            "Reverting all current edits",
            lambda progress: self.facade.revert_all(progress),
            lambda count: (
                self._mark_document_changed()
                if int(count) > 0
                else self._refresh_after_mutation()
            ),
            True,
        )

    def _build_game(self) -> None:
        if not self.facade.source_ready:
            return
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose the folder Xenia should load",
            str(Path.home()),
            QFileDialog.ShowDirsOnly,
        )
        if not chosen:
            return
        output = Path(chosen)
        source = getattr(self.facade, "source", None)
        source_root = getattr(source, "game_root", None)
        if source_root is not None:
            try:
                if output.resolve() == Path(source_root).resolve() or output.resolve().is_relative_to(
                    Path(source_root).resolve()
                ):
                    QMessageBox.information(
                        self,
                        "That is the source game",
                        "The build never writes into the loaded retail folder. "
                        "Choose the folder Xenia already loads, or an empty one.",
                    )
                    return
            except (OSError, ValueError):
                pass
        replace_existing = False
        if output.exists() and any(output.iterdir()):
            answer = QMessageBox.question(
                self,
                "Replace this folder's game files?",
                f"Build into:\n{output}\n\n"
                "The next build will replace the files in this folder so Xenia "
                "can keep the same path. The retail source stays untouched.\n\n"
                "Close Xenia first if it has this folder open.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
            replace_existing = True
        self._run_task(
            "Building a complete separate APF game folder",
            lambda progress, dest=output, replace=replace_existing: self.facade.build(
                dest, progress, replace_existing=replace
            ),
            self._build_complete,
            True,
        )

    def _build_complete(self, receipt: object) -> None:
        output = Path(receipt.output_game)  # type: ignore[attr-defined]
        changed = len(receipt.modified_assets)  # type: ignore[attr-defined]
        self._last_detail = f"Build complete: {output.name}"
        self._update_product_state()
        QMessageBox.information(
            self,
            "Modded game folder built",
            f"Wrote:\n{output}\n\n"
            f"Applied {changed} edit{'s' if changed != 1 else ''}. The complete output was verified and your source stayed untouched.\n\n"
            "Point Xenia at this folder. Rebuild into the same folder to keep that path.\n\n"
            "This folder contains your retail game data. Do not redistribute it; share the .apf2k8mod project instead.",
        )

    def _configure_xenia(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Xenia Canary",
            str(Path.home()),
            "Xenia Canary (xenia_canary.exe xenia.exe xenia*);;All files (*)",
        )
        if not selected:
            return
        executable = Path(selected)
        wine: Path | None = None
        if (
            executable.suffix.casefold() == ".exe"
            and not platform_compat.IS_WINDOWS
            and shutil.which("wine") is None
        ):
            # A ``.exe`` Xenia runs natively on Windows; only a *Unix host
            # needs a separate Wine loader for it.
            QMessageBox.information(
                self,
                "Wine is also required",
                "Xenia Canary is a Windows application. Choose your Wine executable next.",
            )
            selected_wine, _wine_filter = QFileDialog.getOpenFileName(
                self,
                "Choose the Wine executable",
                "/usr/bin",
                "Wine executable (wine);;All files (*)",
            )
            if not selected_wine:
                return
            wine = Path(selected_wine)
        try:
            self.facade.configure_xenia(executable, wine)
        except Exception as exc:
            self._show_error(str(exc), traceback.format_exc())
            return
        self._last_detail = "Xenia Canary is configured. Build a game folder, then click Launch."
        self._update_product_state()

    def _configure_title_update(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose APF 2K8 title update 1.1",
            str(Path.home()),
            "Xbox LIVE package (TU_* *);;All files (*)",
        )
        if not selected:
            return
        try:
            self.facade.configure_title_update(Path(selected))
        except Exception as exc:
            self._show_error(str(exc), traceback.format_exc())
            return
        self._last_detail = (
            "Title update 1.1 is pinned. Launch will copy it into this session's "
            "Xenia content folder. It never shipped for PS3."
        )
        self._update_product_state()

    def _launch_xenia(self) -> None:
        blocker = self.facade.xenia_blocker
        if blocker:
            # Clicking a blocked action must teach, and when the fix is
            # "tell me where Xenia is" it must also offer to do it.
            if "Configure Xenia" in blocker:
                answer = QMessageBox.question(
                    self,
                    "Xenia is not configured yet",
                    blocker + "\n\nChoose Xenia Canary now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    self._configure_xenia()
                return
            QMessageBox.information(self, "Cannot launch Xenia yet", blocker)
            return
        if self.facade.launcher.settings.title_update_path is None:
            answer = QMessageBox.question(
                self,
                "Title update 1.1 is not installed",
                "APF 2K8 title update 1.1 is required on Xbox and Xenia; it never "
                "shipped for PS3. This studio launches into an isolated Xenia "
                "content folder, so a TU installed in a standalone Xenia folder "
                "will not apply here.\n\n"
                "Choose the LIVE STFS package now (the same file Xenia's "
                "File → Install Content uses), or launch without it.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Yes:
                self._configure_title_update()
                if self.facade.launcher.settings.title_update_path is None:
                    return
        self._run_task(
            "Starting the last verified build in Xenia Canary",
            lambda _progress: self.facade.launch_xenia(),
            self._launch_complete,
            True,
        )

    def _launch_complete(self, receipt: object) -> None:
        pid = int(receipt.pid)  # type: ignore[attr-defined]
        log = Path(receipt.log_path)  # type: ignore[attr-defined]
        self._last_detail = f"Xenia started as process {pid}. Log: {log}"
        QMessageBox.information(
            self,
            "Xenia started",
            f"Xenia Canary started the verified modded default.xex.\n\nProcess: {pid}\nLog: {log}",
        )

    def _finish_close_after_save(self) -> None:
        if self._recovery_save_in_flight:
            self._close_when_recovery_finishes = True
            self._recovery_save_pending = False
            self.operation_status.setText(
                "Project saved • finishing private recovery cleanup…"
            )
            return
        self._allow_close = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._workers:
            self._cancel_transient_audio_reads()
            if (
                self._allow_close
                or not self._blocking_workers
            ):
                self._close_when_workers_finish = True
                self._pending_source_load = None
                self.operation_status.setText(
                    "Cancelling private reads before closing Mod Studio…"
                )
                event.ignore()
                return
            QMessageBox.information(
                self,
                "An operation is still running",
                "Let the current operation finish before closing Mod Studio. This prevents a partial export or build.",
            )
            event.ignore()
            return
        self._close_when_workers_finish = False
        if self._allow_close:
            self._cancel_transient_audio_reads()
            self.facade.close()
            event.accept()
            return
        if not self._document_dirty:
            self._cancel_transient_audio_reads()
            self.facade.close()
            event.accept()
            return
        decision = self._prompt_unsaved_decision("Closing Mod Studio")
        if decision == "discard":
            self._document_dirty = False
            self._workspace_revision += 1
            self._recovery_save_pending = False
            if self._recovery_save_in_flight:
                self._close_when_recovery_finishes = True
                self.operation_status.setText(
                    "Discarding the private recovery snapshot…"
                )
                event.ignore()
            else:
                self._clear_recovery_for_source(
                    self._active_source_path, self._active_source_sha256
                )
                self._cancel_transient_audio_reads()
                self.facade.close()
                event.accept()
        elif decision == "save":
            event.ignore()
            if self._recovery_save_in_flight:
                self._recovery_save_pending = False
                self._after_recovery_action = lambda: self._save_project(
                    after_success=self._finish_close_after_save
                )
            else:
                self._save_project(after_success=self._finish_close_after_save)
        else:
            event.ignore()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow#studioWindow, QWidget#workspace, QStackedWidget {
                background: #0b111c; color: #ecf2fb;
            }
            QWidget {
                color: #e8eef8; font-family: Inter, Noto Sans, DejaVu Sans;
                font-size: 12px;
            }
            QFrame#sidebar { background: #0f1827; border-right: 1px solid #26344a; }
            QLabel#brandMark {
                background: #f08a4b; color: #160d09; border-radius: 10px;
                padding: 8px 9px; font-size: 18px; font-weight: 900;
            }
            QLabel#brandTitle { color: #ffffff; font-size: 14px; font-weight: 850; letter-spacing: 1px; }
            QLabel#mutedLabel { color: #bec9d9; font-size: 11px; }
            QListWidget#navigation {
                background: transparent; border: 2px solid transparent;
                border-radius: 9px; outline: none;
            }
            QListWidget#navigation::item {
                color: #aab6c8; border-radius: 8px; padding: 7px 10px;
            }
            QListWidget#navigation:focus { border-color: #f08a4b; }
            QListWidget#navigation::item:hover { background: #172438; color: #ffffff; }
            QListWidget#navigation::item:selected {
                background: #263850; color: #ffb77e; border-left: 3px solid #f08a4b;
                font-weight: 750;
            }
            QLabel#safetyCard {
                background: #162438; border: 1px solid #364a64; border-radius: 9px;
                color: #ced9e8; padding: 13px 14px; font-size: 11px;
            }
            QFrame#header { background: #101827; border-bottom: 1px solid #26344a; }
            QLabel#eyebrow { color: #f29a62; font-size: 10px; font-weight: 850; letter-spacing: 1px; }
            QLabel#pageTitle { color: #ffffff; font-size: 21px; font-weight: 780; }
            QLabel#sourcePill {
                background: #172235; color: #91a0b5; border: 1px solid #2b3950;
                border-radius: 10px; padding: 7px 10px;
            }
            QLabel#sourcePill[ready="true"] { color: #4ee0a0; border-color: #287758; }
            QLabel#heroTitle { color: #ffffff; font-size: 35px; font-weight: 850; }
            QLabel#heroTitleSmall { color: #ffffff; font-size: 25px; font-weight: 820; }
            QLabel#heroSubtitle { color: #b5c1d2; font-size: 13px; padding-top: 2px; }
            QLabel#pageSummary {
                color: #c0ccdc; font-size: 12px; padding: 0 1px 2px 1px;
            }
            QFrame#stepCard, QFrame#capabilityCard, QFrame#panel {
                background: #121c2c; border: 1px solid #26354a; border-radius: 11px;
            }
            QFrame#stepCard:hover, QFrame#capabilityCard:hover { border-color: #405673; }
            QFrame#capabilityPanel { background: transparent; border: none; }
            QLabel#stepNumber { color: #f29a62; font-size: 13px; font-weight: 900; }
            QLabel#cardTitle, QLabel#panelTitle, QLabel#capabilityTitle {
                color: #f8faff; font-size: 15px; font-weight: 760;
            }
            QLabel#capabilityTitle { font-size: 11px; }
            QLabel#capabilitySummary { color: #c0ccdc; font-size: 11px; }
            QLabel#filterLabel {
                color: #aebdd0; font-size: 10px; font-weight: 800; letter-spacing: 1px;
            }
            QLabel#cardBody { color: #b2bfd1; font-size: 12px; padding-top: 2px; }
            QLabel#statusBadge {
                background: #101827; border: 1px solid #516079; border-radius: 7px;
                padding: 3px 7px; font-size: 10px; font-weight: 800;
            }
            QLabel#specPill {
                color: #c3cfe0; background: #16233a; border: 1px solid #33455f;
                border-radius: 7px; padding: 3px 8px; font-size: 10px;
                font-weight: 750;
            }
            QLabel#specPill[emphasis="true"] {
                color: #ffb77e; border-color: #7c4d2b; background: #201a16;
            }
            QLabel#findingText {
                color: #b0bed1; background: #0d1624; border-radius: 6px;
                padding: 8px 10px; font-size: 11px;
            }
            QLabel#metadataText { color: #bec9d9; font-size: 11px; padding-top: 1px; }
            QLabel#contractText {
                color: #c6d5e8; background: #142437; border-left: 3px solid #f08a4b;
                border-radius: 5px; padding: 9px 11px;
            }
            QFrame#callout {
                background: #182a3b; border: 1px solid #38526a; border-radius: 11px;
            }
            QPushButton, QToolButton {
                min-height: 36px; border-radius: 8px; padding: 0 14px;
                font-weight: 720;
            }
            QPushButton#primaryButton, QToolButton#primaryButton {
                background: #f08a4b; color: #1a0e08; border: none;
            }
            /* Keep the Load APF Game menu arrow inside the button instead of
               Qt's default bottom-right corner overhang. */
            QToolButton#primaryButton { padding-right: 26px; }
            QToolButton#primaryButton::menu-indicator {
                subcontrol-origin: padding; subcontrol-position: center right;
                right: 9px;
            }
            QPushButton#primaryButton:hover, QToolButton#primaryButton:hover { background: #ffab72; }
            QPushButton#primaryButton:disabled, QToolButton#primaryButton:disabled {
                background: #182235; color: #5f6c80; border: 1px solid #263148;
            }
            QPushButton#secondaryButton {
                background: #1a2940; color: #dae5f4; border: 1px solid #334661;
            }
            QPushButton#secondaryButton:hover { background: #243750; border-color: #4c6483; }
            QPushButton#secondaryButton:disabled {
                background: #182235; color: #5f6c80; border-color: #263148;
            }
            QPushButton#utilityButton {
                background: transparent; color: #c1cede; border: 1px solid #334258;
            }
            QPushButton#utilityButton:hover { background: #18263a; border-color: #4a607d; }
            QPushButton#utilityButton:disabled {
                background: transparent; color: #5f6c80; border-color: #263148;
            }
            QPushButton#dangerQuietButton {
                background: transparent; color: #f29da4; border: 1px solid #5b3741;
            }
            QPushButton#dangerQuietButton:hover { background: #351f2a; }
            QPushButton#dangerQuietButton:disabled {
                background: transparent; color: #5f6979; border-color: #2a3444;
            }
            QPushButton#buildButton {
                background: #3e73f2; color: white; border: none;
                min-height: 40px; padding: 0 18px; font-size: 12px;
            }
            QPushButton#buildButton:hover { background: #5b8cff; }
            QPushButton#buildButton:disabled {
                background: #1c2c55; color: #697997; border: none;
            }
            QPushButton#launchButton {
                background: #193f42; color: #68eadc; border: 1px solid #28706d;
                min-height: 40px; padding: 0 16px;
            }
            QPushButton#launchButton:hover { background: #225255; }
            QPushButton#launchButton:disabled {
                background: #182a2d; color: #597477; border-color: #263f42;
            }
            QPushButton:disabled, QToolButton:disabled {
                background: #182235; color: #5f6c80; border-color: #263148;
            }
            QPushButton:focus, QToolButton:focus,
            QPushButton#primaryButton:focus, QToolButton#primaryButton:focus,
            QPushButton#secondaryButton:focus,
            QPushButton#utilityButton:focus,
            QPushButton#dangerQuietButton:focus,
            QPushButton#buildButton:focus, QPushButton#launchButton:focus,
            QToolButton#clearSearchButton:focus {
                border: 2px solid #ffd0ad;
            }
            QMessageBox {
                background: #101827;
                color: #eef4ff;
            }
            QMessageBox QLabel {
                color: #eef4ff;
            }
            QMessageBox QPushButton {
                min-width: 84px;
                color: #eef4ff;
                background: #25354b;
                border: 1px solid #526984;
            }
            QMessageBox QPushButton:hover {
                background: #31445e;
                border-color: #7d94b1;
            }
            QMessageBox QPushButton:default {
                color: #111827;
                background: #f29a60;
                border-color: #f29a60;
            }
            QDialog#rosterAliasOwnersDialog {
                background: #101827; color: #eef4ff;
            }
            QDialog#rosterAliasOwnersDialog QLabel {
                background: transparent; color: #dce7f5;
            }
            QDialog#rosterAliasOwnersDialog QLabel#panelTitle {
                color: #ffffff; font-size: 16px; font-weight: 780;
            }
            QPlainTextEdit#rosterAliasOwners {
                background: #080f19; color: #dce8f5;
                border: 1px solid #40516a; border-radius: 8px;
                padding: 9px; font-family: DejaVu Sans Mono; font-size: 11px;
                selection-background-color: #31577c;
            }
            QDialog#rosterAliasOwnersDialog QDialogButtonBox QPushButton {
                min-width: 92px; color: #eef4ff; background: #25354b;
                border: 1px solid #526984;
            }
            QDialog#rosterAliasOwnersDialog QDialogButtonBox QPushButton:hover {
                background: #31445e; border-color: #7d94b1;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #101a2a; color: #f0f5fc; border: 1px solid #40516a;
                border-radius: 8px; min-height: 36px; padding: 0 10px;
            }
            QLineEdit { selection-background-color: #31577c; }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #f08a4b; }
            QSpinBox#baseRatingValueEditor {
                min-width: 76px; max-width: 88px; padding-right: 22px;
                font-size: 13px; font-weight: 800;
            }
            QToolButton#clearSearchButton {
                background: transparent; color: #b9c6d7; border: 1px solid #36465d;
                min-width: 30px; max-width: 30px; padding: 0; font-size: 16px;
            }
            QToolButton#clearSearchButton:hover { background: #1b2a40; color: #ffffff; }
            QComboBox QAbstractItemView, QMenu {
                background: #152136; color: #e5edf8; selection-background-color: #2c425e;
                border: 1px solid #34465f;
            }
            QListWidget#assetList {
                background: #0c1421; border: 1px solid #27364b; border-radius: 9px;
                outline: none;
            }
            QListWidget#assetList::item { color: #cad6e6; border-radius: 7px; padding: 7px 9px; }
            QListWidget#assetList::item:hover { background: #17263a; }
            QListWidget#assetList::item:selected {
                background: #263e57; color: #ffffff; border: 1px solid #486985;
            }
            QListWidget#assetList:focus, QTableWidget#assetTable:focus,
            QTreeWidget:focus, QPlainTextEdit:focus {
                border: 2px solid #f08a4b;
            }
            QTableWidget#assetTable, QTableWidget#fieldArtGroupTable,
            QTableWidget#scorebugGraphicsTable, QTableWidget#scorebugComponentTable {
                background: #0c1421; alternate-background-color: #101a2a;
                border: 1px solid #27364b; border-radius: 8px; gridline-color: #1e2b3e;
                selection-background-color: #29445f; selection-color: white; outline: none;
            }
            QHeaderView::section {
                background: #17253a; color: #91a3ba; border: none;
                border-bottom: 1px solid #2c3d55; padding: 7px; font-size: 11px;
                font-weight: 750;
            }
            QLabel#imagePreview {
                color: #a9b8cc; border: 1px dashed #4b607b;
                border-radius: 10px; padding: 12px; font-size: 11px;
            }
            QLabel#imagePreview:hover { border-color: #f08a4b; }
            QLabel#imagePreview[previewState="loading"] {
                color: #b6d5f4; border-color: #547aa4;
            }
            QLabel#imagePreview[previewState="error"] {
                color: #ffb0b5; border-color: #8b4652;
            }
            QLabel#imagePreview[previewState="ready"] {
                border-style: solid; border-color: #3f556f; padding: 8px;
            }
            QFrame#audioReplacementDropZone {
                background: #101b2b; border: 1px dashed #4b607b;
                border-radius: 8px;
            }
            QFrame#audioReplacementDropZone[dropReady="true"] {
                border-color: #4a9f7d; background: #10251f;
            }
            QFrame#audioReplacementDropZone:disabled {
                border-color: #2b394c; background: #101824;
            }
            QLabel#audioDropTitle { color: #d8f6e9; font-weight: 750; }
            QLabel#countPill, QLabel#editCount {
                color: #aab9cc; background: #19283d; border-radius: 8px; padding: 4px 8px;
            }
            QFrame#inspectorDetail { background: #0d1624; border-radius: 8px; }
            QFrame#audioAnnotationCard {
                background: #101b2b; border: 1px solid #2b3d55; border-radius: 8px;
            }
            QFrame#baseRatingsPanel {
                background: #101b2b; border: 1px solid #2b3d55; border-radius: 8px;
            }
            QTableWidget#baseRatingsTable {
                background: #09111d; alternate-background-color: #0d1827;
                color: #dce8f5; border: 1px solid #27384e; border-radius: 6px;
                gridline-color: #1d2c40; selection-background-color: #29445f;
                selection-color: white; outline: none;
            }
            QPlainTextEdit#textReplacementEditor {
                background: #080f19; color: #edf4fc; border: 1px solid #40516a;
                border-radius: 7px; padding: 6px; font-size: 11px;
            }
            QPlainTextEdit#textReplacementEditor:focus { border-color: #f08a4b; }
            QTabWidget#workspaceTabs::pane {
                background: #0f1827; border: 1px solid #27364b;
                border-radius: 8px; top: -1px;
            }
            QTabWidget#workspaceTabs::tab-bar { left: 12px; }
            /* The wide top-level tab treatment applies only to the workspace
               tab widget's own bar (child combinator).  Nested editor tab
               widgets style themselves smaller below so sub-tabs read as a
               level down in the hierarchy and never overflow into scroller
               arrows inside a narrow detail pane. */
            QTabWidget#workspaceTabs > QTabBar::tab {
                background: #142136; color: #9fb0c6; border: 1px solid #2d3e55;
                border-bottom: none; border-top-left-radius: 7px;
                border-top-right-radius: 7px; min-height: 34px;
                min-width: 190px; padding: 0 24px; margin-right: 6px;
                font-weight: 750;
            }
            QTabWidget#workspaceTabs > QTabBar::tab:selected {
                background: #21344d; color: #ffffff; border-color: #49627e;
            }
            QTabWidget#rosterEditorTabs::pane {
                background: #0f1827; border: 1px solid #27364b;
                border-radius: 8px; top: -1px;
            }
            QTabWidget#rosterEditorTabs::tab-bar { left: 8px; }
            QTabWidget#rosterEditorTabs > QTabBar::tab {
                background: #101b2c; color: #9fb0c6; border: 1px solid #2a3a51;
                border-bottom: none; border-top-left-radius: 6px;
                border-top-right-radius: 6px; min-height: 28px;
                padding: 0 16px; margin-right: 4px;
            }
            QTabWidget#rosterEditorTabs > QTabBar::tab:selected {
                background: #21344d; color: #ffffff; border-color: #49627e;
            }
            QTabWidget#rosterEditorTabs > QTabBar::tab:disabled {
                color: #5f6c80;
            }
            QPlainTextEdit#decodedFields {
                background: #080f19; color: #bcd0e6; border: 1px solid #27374d;
                border-radius: 7px; font-family: DejaVu Sans Mono; font-size: 10px;
            }
            QSplitter::handle { background: #1e2c40; }
            QSplitter::handle:horizontal { width: 5px; }
            QSplitter::handle:vertical { height: 5px; }
            QFrame#footer { background: #101827; border-top: 1px solid #26344a; }
            QFrame#reserveEditor {
                background: #111d2d; border: 1px solid #2b3d55; border-radius: 7px;
            }
            QLabel#operationStatus { color: #c1cddd; font-size: 12px; }
            QProgressBar { background: #202c40; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #f08a4b; border-radius: 2px; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #101827; width: 10px; margin: 2px; }
            QScrollBar::handle:vertical { background: #34455e; min-height: 28px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: #101827; height: 10px; margin: 2px; }
            QScrollBar::handle:horizontal { background: #34455e; min-width: 28px; border-radius: 4px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QToolTip {
                background: #192438; color: #edf3fc;
                border: 1px solid #3b4d68; padding: 6px;
            }
            """
        )


# Backwards-friendly product-shell name used by a few integration harnesses.
StudioMainWindow = ApfStudioMainWindow


def launch_studio(
    facade: ApfStudioFacade | None = None,
    *,
    initial_source: Path | None = None,
    initial_category: ApfCategory | None = None,
    initial_workspace: str | None = None,
    workspace_store: WorkspaceStateStore | None = None,
    offer_recovery: bool = True,
) -> int:
    """Create and run the desktop app only when explicitly called."""

    application = QApplication.instance()
    if application is None:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        application = QApplication([sys.argv[0]])
        # Only when this call owns the application: an embedded caller has its
        # own error handling and should not have it replaced. Installing the
        # hook is also what stops PyQt5 aborting the process, so an unexpected
        # error becomes a dialog instead of a window that simply disappears.
        crash_report.install(PRODUCT_NAME)
    application.setApplicationName(PRODUCT_NAME)
    application.setOrganizationName(PRODUCT_NAME)
    _application_icon = _window_icon()
    if _application_icon is not None:
        application.setWindowIcon(_application_icon)
    state_error = ""
    if workspace_store is None:
        try:
            workspace_store = WorkspaceStateStore()
        except Exception as exc:
            # State is a convenience/safety layer, never a condition for
            # opening the editor or accessing a user's source read-only.
            state_error = str(exc).strip()
            workspace_store = None
    # A positional CLI source is loaded first.  Its success callback offers
    # recovery only when the candidate is bound to that exact path and hash,
    # avoiding two competing QTimer(0) source flows or stacked dialogs.
    window = ApfStudioMainWindow(
        facade,
        workspace_store=workspace_store,
        offer_recovery=offer_recovery and initial_source is None,
    )
    window.show()
    setattr(application, "_apf2k8_mod_studio_window", window)
    if initial_category is not None:
        window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(initial_category))
        if initial_workspace is not None:
            page = window._pages.get(initial_category)
            if isinstance(page, InspectorCategoryPage):
                page.open_workspace(initial_workspace)
    if state_error:
        window.operation_status.setText(
            f"Private recovery is unavailable for this run: {state_error}"
        )
    if initial_source is not None:
        QTimer.singleShot(
            0,
            lambda: window._load_source_path(
                initial_source,
                offer_matching_recovery=offer_recovery,
            ),
        )
    return application.exec_()


__all__ = [
    "AUDIO_ANNOTATION_UI_CONTRACT",
    "AUDIO_DIRECT_DROP_CONTRACT",
    "AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT",
    "AudioReplacementDropZone",
    "ApfFieldArtPanel",
    "ApfStudioMainWindow",
    "ApfTeamLogoPanel",
    "AssetBrowser",
    "FIELD_ART_COVERED_TARGETS",
    "BaseRatingsPanel",
    "CatalogCategoryPage",
    "DigitalFontPanel",
    "FieldArtStudioPage",
    "GettingStartedPage",
    "ImageDropLabel",
    "InspectorBrowser",
    "InspectorCategoryPage",
    "LogosStudioPage",
    "PRODUCT_NAME",
    "RatingSheetImportPreviewDialog",
    "ScorebugComponentsPanel",
    "ScorebugGraphicsPanel",
    "ScorebugStudioPage",
    "StadiumStudioPage",
    "StudioMainWindow",
    "UniformStudioPage",
    "launch_studio",
]
