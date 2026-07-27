"""Polished PyQt5 product shell for 2K5 Mod Studio.

The window is intentionally backend-agnostic.  It owns navigation, browsing,
preview, drag/drop, progress, and human-readable error presentation while a
small :class:`StudioFacade` owns source indexing, private originals, edits, and
atomic XISO builds.  This separation keeps every slow or retail-data-adjacent
operation out of the GUI thread and makes the product shell independently
testable.

No retail artwork or bytes are embedded here.  Before a source is loaded the
uniform browser shows metadata-only monograms generated from catalog labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence, runtime_checkable

from PyQt5.QtCore import (
    QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QCloseEvent, QFont, QIcon, QImageReader, QKeySequence, QPainter,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from mod_editor import __version__
from mod_editor.core.errors import ValidationError
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.nfl2k5_uniform_catalog import (
    ASSETS_PER_SET,
    Nfl2k5UniformCatalog,
    UniformAsset,
    UniformSet,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    ExtendedVisualAsset,
    Nfl2k5ExtendedVisualCatalog,
    VisualWriterRoute,
    load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_universal_asset_index import UniversalAssetRecord
from mod_editor.core.nfl2k5_stadium_studio import (
    EDITABLE as STADIUM_EDITABLE,
    StadiumScene,
    StadiumSceneDetails,
    StadiumTexture,
)
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    RosterNumberAsset,
    TextAsset,
)
from mod_editor.core.nfl2k5_crib import CribAsset
from mod_editor.gui.stadium_viewer import GltfWireframeModel, StadiumViewport
from mod_editor.gui.audio_panel_qt import AudioPanel
from mod_editor.gui.crib_panel_qt import CribPanel
from mod_editor.gui.gameplay_panel_qt import GameplayPanel
from mod_editor.gui.menus_panel_qt import MenusPanel
from mod_editor.gui.playbooks_panel_qt import PlaybooksPanel
from mod_editor.gui.text_rosters_panel import TextRosterPanel
from mod_editor.studio.facade import (
    collect_nfl2k5_gameplay_inspection,
    collect_nfl2k5_main_menu_inspection,
)
from mod_editor.studio.project_archive import (
    ProjectTargetIdentity,
    project_target_identity,
)
from mod_editor.studio.workspace_state import (
    RecoveryCandidate,
    WorkspaceStateStore,
)
from mod_editor.core.product_catalog import (
    PRODUCT_CATEGORY_ORDER,
    ProductCapability,
    ProductCatalog,
    ProductCategory,
    ProductCategorySection,
    ProductStatus,
    build_nfl2k5_product_catalog,
)


ProgressSink = Callable[[str, int, int], None]
EMBEDDED_AUDIO_TASK_CONTRACT = "global_action_guarded_until_drain"
EMBEDDED_OPERATION_TASK_CONTRACT = "audio_crib_mutually_exclusive_until_drain"

# Every workspace page is hosted in a scroll area so a tall page (Audio is the
# tallest at ~949 px of content) scrolls inside a short window instead of forcing
# the whole main window taller than a 1080p — or 768p — display can show.  The
# host keeps only a small vertical floor so the window can shrink well below any
# single page's natural minimum height.
PAGE_SCROLL_MIN_HEIGHT = 220


def _window_icon() -> QIcon | None:
    """Return the bundled application icon, or None if it is unavailable."""
    candidate = (
        Path(__file__).resolve().parents[2]
        / "packaging"
        / "2k5-mod-studio.svg"
    )
    try:
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    except Exception:
        pass
    return None


@runtime_checkable
class StudioFacade(Protocol):
    """Backend contract consumed by :class:`StudioMainWindow`.

    All methods may perform disk I/O and are therefore invoked on a Qt worker
    thread.  Implementations should report progress as ``(stage, completed,
    total)``.  ``completed`` and ``total`` may both be zero for indeterminate
    work.
    """

    @property
    def source_ready(self) -> bool: ...

    @property
    def source_display_name(self) -> str: ...

    @property
    def source_path(self) -> Path | None: ...

    @property
    def source_sha256(self) -> str | None: ...

    @property
    def modified_asset_ids(self) -> Iterable[str]: ...

    @property
    def modified_count(self) -> int: ...

    @property
    def can_undo(self) -> bool: ...

    @property
    def can_launch_xemu(self) -> bool: ...

    def load_source(self, source_xiso: Path, progress: ProgressSink) -> object: ...

    def preview_asset(self, asset: UniformAsset, progress: ProgressSink) -> Path: ...

    def export_asset(
        self, asset: UniformAsset, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def replace_asset(
        self, asset: UniformAsset, supplied_png: Path, progress: ProgressSink
    ) -> object: ...

    def revert_asset(self, asset: UniformAsset, progress: ProgressSink) -> object: ...

    def export_team_kit_sets(
        self,
        selectors: Sequence[str],
        destination: Path,
        *,
        container: str,
        progress: ProgressSink,
    ) -> object: ...

    def export_team_kit(
        self,
        *,
        asset_code: str,
        variant: int,
        sides: str,
        destination: Path,
        container: str,
        progress: ProgressSink,
    ) -> object: ...

    def import_team_kit(
        self, source: Path, progress: ProgressSink
    ) -> object: ...

    def undo(self, progress: ProgressSink) -> object: ...

    def revert_all(self, progress: ProgressSink) -> object: ...

    def save_project(
        self,
        destination: Path,
        progress: ProgressSink,
        *,
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
        allow_empty: bool = False,
    ) -> object: ...

    def save_recovery_project(
        self, destination: Path, expected_source_sha256: str,
        progress: ProgressSink,
    ) -> object: ...

    def load_project(self, source: Path, progress: ProgressSink) -> object: ...

    def resource_kinds(self, progress: ProgressSink) -> object: ...

    def browse_resources(
        self, *, search: str, kind: str | None, offset: int, limit: int,
        progress: ProgressSink,
    ) -> object: ...

    def export_resource(
        self, asset: UniversalAssetRecord | str, destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def inspect_gameplay(self, progress: ProgressSink) -> object: ...

    def export_gameplay_inspection(
        self, destination: Path, export_format: str, progress: ProgressSink,
    ) -> Path: ...

    def inspect_main_menu(self, progress: ProgressSink) -> object: ...

    def export_main_menu_inspection(
        self, destination: Path, export_format: str, progress: ProgressSink,
    ) -> Path: ...

    @property
    def playbook_available(self) -> bool: ...

    def browse_playbooks(self, search: str, progress: ProgressSink) -> object: ...

    def export_playbook(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    @property
    def stadium_available(self) -> bool: ...

    def stadium_scenes(self, search: str, progress: ProgressSink) -> object: ...

    def stadium_details(
        self, scene: StadiumScene | str, progress: ProgressSink,
    ) -> StadiumSceneDetails: ...

    def preview_stadium_texture(
        self, texture_id: str, progress: ProgressSink,
    ) -> Path: ...

    def export_stadium_texture(
        self, texture_id: str, destination: Path, progress: ProgressSink,
    ) -> Path: ...

    def replace_stadium_texture(
        self, texture_id: str, supplied_png: Path, progress: ProgressSink,
    ) -> object: ...

    def revert_stadium_texture(
        self, texture_id: str, progress: ProgressSink,
    ) -> object: ...

    def stadium_scene_people_texture_ids(
        self, scene_id: str, progress: ProgressSink,
    ) -> tuple[str, ...]: ...

    @property
    def modified_audio_asset_ids(self) -> Iterable[str]: ...

    @property
    def audio_editing_ready(self) -> bool: ...

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
    ) -> object: ...

    def prepare_audio(self, asset_id: str, progress: ProgressSink) -> Path: ...

    def export_audio(
        self, asset_id: str, destination: Path, progress: ProgressSink,
    ) -> Path: ...

    def export_audio_bank(
        self, asset_id: str, destination: Path, progress: ProgressSink,
    ) -> Path: ...

    def export_audio_range(
        self, asset_id: str, destination: Path, progress: ProgressSink,
    ) -> Path: ...

    def export_audio_range_wav(
        self, asset_id: str, destination: Path, progress: ProgressSink,
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

    def replace_audio(
        self, asset_id: str, supplied_wav: Path, progress: ProgressSink,
    ) -> object: ...

    def revert_audio(self, asset_id: str, progress: ProgressSink) -> object: ...

    def text_catalog_snapshot(
        self, progress: ProgressSink
    ) -> Nfl2k5TextCatalog: ...

    def text_value(self, asset: TextAsset | str) -> str: ...

    def number_value(self, asset: RosterNumberAsset | str) -> int: ...

    def replace_text(
        self, asset: TextAsset | str, value: str, progress: ProgressSink
    ) -> object: ...

    def replace_number(
        self, asset: RosterNumberAsset | str, value: int, progress: ProgressSink
    ) -> object: ...

    def revert_text(self, asset_id: str, progress: ProgressSink) -> object: ...

    def export_text(
        self, asset: TextAsset | str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_number(
        self, asset: RosterNumberAsset | str, destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    @property
    def modified_crib_asset_ids(self) -> Iterable[str]: ...

    def list_crib_assets(self) -> Iterable[CribAsset]: ...

    def preview_crib_asset(
        self, asset_id: str, progress: ProgressSink
    ) -> Path: ...

    def export_crib_asset(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def replace_crib_photo(
        self, asset_id: str, supplied_png: Path, progress: ProgressSink
    ) -> object: ...

    def revert_crib_photo(
        self, asset_id: str, progress: ProgressSink
    ) -> object: ...

    def build_iso(self, destination: Path, progress: ProgressSink) -> object: ...

    def launch_xemu(self, progress: ProgressSink) -> object: ...


class _EmbeddedOperationGuardedHost:
    """Delegate specialist reads while fencing their direct mutation boundary.

    Text/roster editors mutate synchronously and Crib mutates from its private
    worker.  Disabling their widgets is necessary for users, but Qt signals and
    direct method calls remain callable.  This adapter is therefore the final
    shared-session admission check immediately before either specialist reaches
    the real facade.
    """

    def __init__(
        self,
        host: StudioFacade,
        *,
        requester: str,
        require_mutation_admission: Callable[[str, str], None],
    ) -> None:
        self._host = host
        self._requester = requester
        self._require_mutation_admission = require_mutation_admission

    @property
    def source_ready(self) -> bool:
        return bool(self._host.source_ready)

    @property
    def modified_crib_asset_ids(self) -> Iterable[str]:
        return self._host.modified_crib_asset_ids

    def text_catalog_snapshot(
        self, progress: ProgressSink
    ) -> Nfl2k5TextCatalog:
        return self._host.text_catalog_snapshot(progress)

    def text_value(self, asset: TextAsset | str) -> str:
        return self._host.text_value(asset)

    def number_value(self, asset: RosterNumberAsset | str) -> int:
        return self._host.number_value(asset)

    def replace_text(
        self, asset: TextAsset | str, value: str, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "change text or a player")
        return self._host.replace_text(asset, value, progress)

    def replace_number(
        self, asset: RosterNumberAsset | str, value: int, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "change a jersey number")
        return self._host.replace_number(asset, value, progress)

    def revert_text(self, asset_id: str, progress: ProgressSink) -> object:
        self._require_mutation_admission(self._requester, "revert text or a player")
        return self._host.revert_text(asset_id, progress)

    def export_text(
        self, asset: TextAsset | str, destination: Path, progress: ProgressSink
    ) -> Path:
        return self._host.export_text(asset, destination, progress)

    def export_number(
        self,
        asset: RosterNumberAsset | str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path:
        return self._host.export_number(asset, destination, progress)

    def list_crib_assets(self) -> Iterable[CribAsset]:
        return self._host.list_crib_assets()

    def preview_crib_asset(
        self, asset_id: str, progress: ProgressSink
    ) -> Path:
        return self._host.preview_crib_asset(asset_id, progress)

    def export_crib_asset(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        return self._host.export_crib_asset(asset_id, destination, progress)

    def replace_crib_photo(
        self, asset_id: str, supplied_png: Path, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "replace a Crib texture")
        return self._host.replace_crib_photo(asset_id, supplied_png, progress)

    def revert_crib_photo(
        self, asset_id: str, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "revert a Crib texture")
        return self._host.revert_crib_photo(asset_id, progress)


class BrowseOnlyFacade:
    """Safe catalog-only fallback used before the product backend is wired."""

    source_ready = False
    source_display_name = "No game loaded"
    source_path: Path | None = None
    source_sha256: str | None = None
    modified_asset_ids: frozenset[str] = frozenset()
    modified_count = 0
    project_metadata_count = 0
    can_undo = False
    can_launch_xemu = False

    @staticmethod
    def _unavailable(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(
            "The editing backend is not connected in this build. "
            "You can still browse every catalog entry."
        )

    load_source = _unavailable
    preview_asset = _unavailable
    export_asset = _unavailable
    replace_asset = _unavailable
    revert_asset = _unavailable
    export_team_kit_sets = _unavailable
    export_team_kit = _unavailable
    import_team_kit = _unavailable
    undo = _unavailable
    revert_all = _unavailable
    save_project = _unavailable
    save_recovery_project = _unavailable
    load_project = _unavailable
    resource_kinds = _unavailable
    browse_resources = _unavailable
    export_resource = _unavailable
    export_gameplay_inspection = _unavailable
    export_main_menu_inspection = _unavailable
    browse_playbooks = _unavailable
    export_playbook = _unavailable
    stadium_scenes = _unavailable
    stadium_details = _unavailable
    preview_stadium_texture = _unavailable
    export_stadium_texture = _unavailable
    replace_stadium_texture = _unavailable
    revert_stadium_texture = _unavailable
    stadium_scene_people_texture_ids = _unavailable
    browse_audio = _unavailable
    prepare_audio = _unavailable
    export_audio = _unavailable
    export_audio_bank = _unavailable
    export_audio_range = _unavailable
    export_audio_range_wav = _unavailable
    export_audio_bundle = _unavailable
    export_audio_selection = _unavailable
    replace_audio = _unavailable
    revert_audio = _unavailable
    audio_affected_asset_ids = _unavailable
    audio_complete_pack_path = _unavailable
    audio_annotation = _unavailable
    set_audio_annotation = _unavailable
    clear_audio_annotation = _unavailable
    text_catalog_snapshot = _unavailable
    text_value = _unavailable
    number_value = _unavailable
    replace_text = _unavailable
    replace_number = _unavailable
    revert_text = _unavailable
    export_text = _unavailable
    export_number = _unavailable
    modified_crib_asset_ids: frozenset[str] = frozenset()
    preview_crib_asset = _unavailable
    export_crib_asset = _unavailable
    replace_crib_photo = _unavailable
    revert_crib_photo = _unavailable
    modified_audio_asset_ids: frozenset[str] = frozenset()
    audio_editing_ready = False
    stadium_available = False
    playbook_available = False
    build_iso = _unavailable
    launch_xemu = _unavailable

    @staticmethod
    def inspect_gameplay(progress: ProgressSink) -> object:
        progress("Reading mapped gameplay findings", 0, 1)
        value = collect_nfl2k5_gameplay_inspection()
        progress("Gameplay findings ready", 1, 1)
        return value

    @staticmethod
    def inspect_main_menu(progress: ProgressSink) -> object:
        progress("Reading named Main Menu findings", 0, 1)
        value = collect_nfl2k5_main_menu_inspection()
        progress("Main Menu findings ready", 1, 1)
        return value

    @staticmethod
    def list_crib_assets() -> tuple[CribAsset, ...]:
        """Keep the embedded Crib panel quiet until a source is loaded."""

        return ()


@dataclass(frozen=True)
class UniformFilter:
    query: str = ""
    side: str = "all"
    owner: str | None = None


@dataclass
class _VisualBrowserState:
    category: ProductCategory
    kinds: frozenset[str]
    assets: tuple[ExtendedVisualAsset, ...]
    search: QLineEdit
    group_filter: QComboBox
    asset_list: QListWidget
    count_label: QLabel
    title: QLabel
    metadata: QLabel
    preview: "_PngDropPreview"
    help_label: QLabel
    export_button: QPushButton
    replace_button: QPushButton
    revert_button: QPushButton
    selected_asset_id: str | None = None


@dataclass
class _UniversalBrowserState:
    search: QLineEdit
    kind_filter: QComboBox
    asset_list: QListWidget
    count_label: QLabel
    range_label: QLabel
    previous_button: QPushButton
    next_button: QPushButton
    export_button: QPushButton
    asset_id_label: QLabel
    detail_label: QLabel
    rows: tuple[UniversalAssetRecord, ...] = ()
    offset: int = 0
    total: int = 0
    kinds_loaded: bool = False
    kinds_loading: bool = False
    generation: int = 0


@dataclass
class _StadiumBrowserState:
    search: QLineEdit
    scene_list: QListWidget
    count_label: QLabel
    viewport: StadiumViewport
    scene_label: QLabel
    scene_metadata: QLabel
    texture_list: QListWidget
    texture_preview: "_PngDropPreview"
    texture_label: QLabel
    findings: QLabel
    export_button: QPushButton
    replace_button: QPushButton
    revert_button: QPushButton
    scenes: tuple[StadiumScene, ...] = ()
    details: StadiumSceneDetails | None = None
    selected_texture_id: str | None = None
    scenes_loaded: bool = False
    scenes_loading: bool = False
    generation: int = 0


def uniform_search_text(uniform_set: UniformSet) -> str:
    """Return the normalized metadata haystack used by product search."""

    return " ".join(
        (
            uniform_set.selector,
            uniform_set.label,
            uniform_set.asset_code,
            uniform_set.side_code,
            uniform_set.side_name,
            uniform_set.style_label,
            *uniform_set.team_names,
            *uniform_set.team_abbreviations,
            *uniform_set.historic_abbreviations,
        )
    ).casefold()


def filter_uniform_sets(
    uniform_sets: Iterable[UniformSet], criteria: UniformFilter
) -> tuple[UniformSet, ...]:
    """Filter uniform sets without touching Qt or user-derived game data."""

    words = tuple(word for word in criteria.query.casefold().split() if word)
    side = criteria.side.strip().lower()
    owner = criteria.owner
    result: list[UniformSet] = []
    for uniform_set in uniform_sets:
        if side in {"home", "h"} and uniform_set.side_code != "H":
            continue
        if side in {"away", "a"} and uniform_set.side_code != "A":
            continue
        if owner == "__unassigned__" and uniform_set.team_names:
            continue
        if owner not in {None, "", "__unassigned__"} and owner not in uniform_set.team_names:
            continue
        haystack = uniform_search_text(uniform_set)
        if words and not all(word in haystack for word in words):
            continue
        result.append(uniform_set)
    return tuple(result)


def category_display_title(
    catalog: ProductCatalog, category: ProductCategory
) -> str:
    """Return the visible title for a category with a specialized product page."""

    if category == ProductCategory.TEAM_IDENTITY:
        return "Text & Team Identity"
    return catalog.section(category).title


def specialized_panel_for_category(category: ProductCategory) -> str | None:
    """Identify categories mounted as dedicated panels instead of capability cards."""

    return {
        ProductCategory.ROSTERS_PLAYERS: "rosters_players",
        ProductCategory.TEAM_IDENTITY: "text_rosters",
        ProductCategory.CRIB: "crib",
        ProductCategory.AUDIO: "audio",
        ProductCategory.MENUS_UI: "menus",
        ProductCategory.SLIDERS_GAMEPLAY: "gameplay",
        ProductCategory.PLAYBOOKS_PLAYS: "playbooks",
    }.get(category)


def sidebar_category_titles(catalog: ProductCatalog) -> tuple[str, ...]:
    """Return and validate the exact product navigation order."""

    return tuple(
        category_display_title(catalog, category)
        for category in PRODUCT_CATEGORY_ORDER
    )


def capability_findings(binding: ProductCapability) -> tuple[str, ...]:
    """Choose concise product-facing findings for a capability card."""

    if binding.findings_notes:
        return binding.findings_notes
    raw = binding.capability.raw
    gui = raw.get("gui", {}) if isinstance(raw, dict) else {}
    reason = gui.get("reason") if isinstance(gui, dict) else None
    portme = raw.get("portme", ()) if isinstance(raw, dict) else ()
    notes: list[str] = []
    if isinstance(reason, str) and reason.strip():
        notes.append(" ".join(reason.split()))
    if binding.status == ProductStatus.COMING_SOON and isinstance(portme, list):
        for value in portme:
            if isinstance(value, str) and value.strip():
                cleaned = " ".join(value.split())
                if cleaned not in notes:
                    notes.append(cleaned)
                break
    return tuple(notes)


def _status_color(status: ProductStatus) -> str:
    return {
        ProductStatus.EDITABLE: "#39d98a",
        ProductStatus.PREVIEW: "#69a7ff",
        ProductStatus.EXPORT_ONLY: "#b69cff",
        ProductStatus.COMING_SOON: "#91a0b5",
    }[status]


def _result_message(result: object, fallback: str) -> str:
    if isinstance(result, str) and result.strip():
        return result.strip()
    message = getattr(result, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


def _configure_search_field(
    field: QLineEdit,
    *,
    placeholder: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Apply the same discoverable search affordances to every browser."""

    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    field.setAccessibleName(accessible_name)
    keyboard_hint = f"{tooltip} Press Ctrl+F to focus search from anywhere."
    field.setToolTip(keyboard_hint)
    field.setAccessibleDescription(keyboard_hint)
    field.setProperty("studioSearch", True)


class _TaskSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal()


class _BackgroundTask(QRunnable):
    """Run one facade operation without ever blocking Qt's event loop."""

    def __init__(self, operation: Callable[[ProgressSink], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.progress.emit)
        except BaseException as exc:  # Qt must receive failures, never lose them.
            message = str(exc).strip() or exc.__class__.__name__
            self.signals.error.emit(message)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class _PngDropPreview(QFrame):
    png_dropped = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pngPreview")
        self.setAcceptDrops(True)
        self.setMinimumSize(250, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pixmap: QPixmap | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 18)
        self.image = QLabel("Select a component to preview")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setWordWrap(True)
        self.image.setObjectName("previewImage")
        self.image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.hint = QLabel("PNG preview  •  drag an edited PNG here to replace")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setObjectName("mutedLabel")
        layout.addWidget(self.image, 1)
        layout.addWidget(self.hint)

    def set_loading(self, message: str = "Preparing preview…") -> None:
        self._pixmap = None
        self.image.setPixmap(QPixmap())
        self.image.setText(message)

    def set_empty(self, message: str) -> None:
        self._pixmap = None
        self.image.setPixmap(QPixmap())
        self.image.setText(message)

    def set_png(self, path: Path) -> bool:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.set_empty("This PNG could not be previewed.")
            return False
        self._pixmap = QPixmap.fromImage(image)
        self._render_pixmap()
        self.hint.setText(
            f"{image.width()} × {image.height()} PNG  •  drag an edited PNG here"
        )
        return True

    def _render_pixmap(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        target = self.image.size() - QSize(24, 24)
        scaled = self._pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image.setText("")
        self.image.setPixmap(scaled)

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._render_pixmap()

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        mime = event.mimeData()  # type: ignore[attr-defined]
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile() and \
                urls[0].toLocalFile().lower().endswith(".png"):
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        path = Path(event.mimeData().urls()[0].toLocalFile())  # type: ignore[attr-defined]
        self.png_dropped.emit(path)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class _StatusPill(QLabel):
    def __init__(self, text: str, color: str) -> None:
        super().__init__(text)
        self.setProperty("pill", True)
        self.setStyleSheet(
            "QLabel {"
            f"color: {color}; background: {color}20; border: 1px solid {color}55;"
            "border-radius: 9px; padding: 3px 8px; font-size: 11px;"
            "font-weight: 700; }"
        )


class StudioMainWindow(QMainWindow):
    """Flagship 2K5 Mod Studio product window."""

    team_kit_imported = pyqtSignal(int)

    def __init__(
        self,
        facade: StudioFacade | None = None,
        *,
        product_catalog: ProductCatalog | None = None,
        uniform_catalog: Nfl2k5UniformCatalog | None = None,
        extended_visual_catalog: Nfl2k5ExtendedVisualCatalog | None = None,
        workspace_store: WorkspaceStateStore | None = None,
        offer_recovery: bool = False,
    ) -> None:
        super().__init__()
        self.facade: StudioFacade = facade or BrowseOnlyFacade()
        self.product_catalog = product_catalog or build_nfl2k5_product_catalog(
            CapabilityRegistryLoader().load(
                allow_sample_fallback=False, check_files=False
            )
        )
        self.uniform_catalog = uniform_catalog or load_nfl2k5_uniform_catalog()
        self.extended_visual_catalog = (
            extended_visual_catalog or load_nfl2k5_extended_visual_catalog()
        )
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[_BackgroundTask] = set()
        self._blocking = False
        self._embedded_audio_busy = False
        self._embedded_crib_busy = False
        self._post_blocking_continuations: list[Callable[[], None]] = []
        self._selected_asset: Any | None = None
        self._selected_set: UniformSet | None = None
        self._component_items: dict[str, QTreeWidgetItem] = {}
        self._monogram_icons: dict[str, QIcon] = {}
        self._preview_generation = 0
        self._category_pages: dict[ProductCategory, QWidget] = {}
        self._visual_browsers: dict[ProductCategory, _VisualBrowserState] = {}
        self._universal_browser: _UniversalBrowserState | None = None
        self._stadium_browser: _StadiumBrowserState | None = None
        self._audio_panel: AudioPanel | None = None
        self._text_roster_panel: TextRosterPanel | None = None
        self._roster_panel: TextRosterPanel | None = None
        self._crib_panel: CribPanel | None = None
        self._playbooks_panel: PlaybooksPanel | None = None
        self._gameplay_panel: GameplayPanel | None = None
        self._menus_panel: MenusPanel | None = None
        self.workspace_store = workspace_store
        self._workspace_dirty = False
        self._workspace_revision = 0
        self._recovery_save_in_flight = False
        self._recovery_save_pending = False
        self._close_when_recovery_finishes = False
        self._allow_close = False
        self._active_source_path: Path | None = getattr(
            self.facade, "source_path", None
        )
        self._active_source_sha256: str | None = getattr(
            self.facade, "source_sha256", None
        )
        self._active_project_path: Path | None = None
        self._active_project_identity: ProjectTargetIdentity | None = None
        self._recent_source_menu: QMenu | None = None
        self._recent_project_menu: QMenu | None = None
        self._recover_action: QAction | None = None
        self._open_source_action: QAction | None = None
        self._open_project_action: QAction | None = None
        self._save_project_action: QAction | None = None
        self._save_project_as_action: QAction | None = None
        self._ps2_save_action: QAction | None = None

        self.setWindowTitle("2K5 Mod Studio")
        icon = _window_icon()
        if icon is not None:
            self.setWindowIcon(icon)
        # Width keeps the sidebar + a full workspace panel visible; the height
        # floor is deliberately low so the window fits a 1366x768 laptop after
        # the OS chrome.  Pages scroll (see _page_scroll_host), so a short window
        # never clips the header or the bottom build/launch action bar.
        self.setMinimumSize(1180, 640)
        self.resize(1480, 920)
        self.setObjectName("studioWindow")
        self._build_ui()
        self._build_file_menu()
        self._install_keyboard_shortcuts()
        self._apply_style()
        self._populate_uniform_filters()
        self._filter_uniforms()
        self._refresh_edit_state()
        if offer_recovery and self.workspace_store is not None:
            QTimer.singleShot(0, self._offer_startup_recovery)

    @property
    def sidebar_category_order(self) -> tuple[str, ...]:
        return sidebar_category_titles(self.product_catalog)

    def _build_file_menu(self) -> None:
        """Expose recent files and recovery without adding header clutter."""

        file_menu = self.menuBar().addMenu("&File")
        self._open_source_action = file_menu.addAction("Open NFL 2K5 XISO…")
        self._open_source_action.setShortcut("Ctrl+O")
        self._open_source_action.triggered.connect(self._choose_source)
        self._open_project_action = file_menu.addAction("Open Project…")
        self._open_project_action.setShortcut("Ctrl+Shift+O")
        self._open_project_action.triggered.connect(self._choose_project)
        self._recent_source_menu = file_menu.addMenu("Open Recent XISO")
        self._recent_project_menu = file_menu.addMenu("Open Recent Project")
        file_menu.addSeparator()
        self._save_project_action = file_menu.addAction("Save Project")
        self._save_project_action.setShortcut("Ctrl+S")
        self._save_project_action.triggered.connect(self._save_project)
        self._save_project_as_action = file_menu.addAction("Save Project As…")
        self._save_project_as_action.setShortcut("Ctrl+Shift+S")
        self._save_project_as_action.triggered.connect(
            self._choose_save_project_as
        )
        self._recover_action = file_menu.addAction("Recover Unsaved Edits…")
        self._recover_action.triggered.connect(self._recover_from_menu)
        file_menu.addSeparator()
        self._ps2_save_action = file_menu.addAction("PS2 Save Editor…")
        self._ps2_save_action.setToolTip(
            "Edit an ESPN NFL 2K5 PlayStation 2 memory-card save. This is "
            "separate from the Xbox game image you have open."
        )
        self._ps2_save_action.triggered.connect(self._open_ps2_save_editor)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        self._refresh_recent_menus()

    def _install_keyboard_shortcuts(self) -> None:
        """Keep the two most-used navigation targets one keystroke away."""

        self.find_shortcut = QShortcut(QKeySequence.Find, self)
        self.find_shortcut.setContext(Qt.WindowShortcut)
        self.find_shortcut.activated.connect(self._focus_current_search)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.sidebar_shortcut.setContext(Qt.WindowShortcut)
        self.sidebar_shortcut.activated.connect(self._focus_category_navigation)

    def _focus_category_navigation(self) -> None:
        self.navigation.setFocus(Qt.ShortcutFocusReason)

    def _audio_operation_state_changed(self, busy: bool) -> None:
        """Track Audio as one owner of the shared embedded-operation lane."""

        self._embedded_audio_busy = bool(busy)
        self._embedded_operation_state_changed("Audio", busy)

    def _crib_operation_state_changed(self, busy: bool) -> None:
        """Track Crib as one owner of the shared embedded-operation lane."""

        self._embedded_crib_busy = bool(busy)
        self._embedded_operation_state_changed("Crib", busy)

    def _embedded_operation_state_changed(self, owner: str, busy: bool) -> None:
        """Refresh one shared session fence after an embedded worker edge."""

        self._set_status(
            f"{owner} operation running • wait for it to finish"
            + (
                ", or use Cancel waveform in Audio when that button is available."
                if owner == "Audio" else "."
            )
            if busy
            else f"{owner} operation finished • global project actions are available."
        )
        self._refresh_recent_menus()
        self._refresh_action_states()
        if (
            not self._embedded_operation_is_busy()
            and self._recovery_save_pending
            and not self._recovery_save_in_flight
            and self._workspace_dirty
        ):
            QTimer.singleShot(0, self._save_recovery_snapshot)

    def _embedded_operation_is_busy(self) -> bool:
        """Use tracked edges for cheap UI gating of both embedded worker lanes."""

        return self._embedded_audio_busy or self._embedded_crib_busy

    def _embedded_operation_owners(self) -> tuple[str, ...]:
        """Include live panel properties so direct callers cannot miss an edge."""

        audio_busy = self._embedded_audio_busy or bool(
            self._audio_panel is not None
            and self._audio_panel.operation_in_progress
        )
        crib_busy = self._embedded_crib_busy or bool(
            self._crib_panel is not None
            and self._crib_panel.operation_in_progress
        )
        return tuple(
            name
            for name, active in (("Audio", audio_busy), ("Crib", crib_busy))
            if active
        )

    def _embedded_operation_denial(self, requester: str) -> str | None:
        """Return an actionable reason when another operation owns the session."""

        if self._blocking:
            return "Finish the current project operation before starting another task."
        competing = tuple(
            owner for owner in self._embedded_operation_owners()
            if owner.casefold() != requester.casefold()
        )
        if not competing:
            return None
        owner = " and ".join(competing)
        return f"Wait for {owner} to finish before starting {requester}."

    def _require_specialist_mutation_admission(
        self, requester: str, action: str
    ) -> None:
        """Fence direct/signal specialist writes without touching Qt from workers."""

        denial = self._embedded_operation_denial(requester)
        if denial is not None:
            raise ValidationError(f"Cannot {action} yet. {denial}")

    def _refuse_while_embedded_busy(self, action: str) -> bool:
        """Return true after explaining which embedded worker owns the session."""

        owners = self._embedded_operation_owners()
        if not owners:
            return False
        owner = " and ".join(owners)
        if owners == ("Audio",):
            message = (
                f"Audio is still working, so Mod Studio cannot {action} yet. Wait for "
                "the Audio operation to finish. If the Audio page shows Cancel "
                "waveform, press it to discard that preview at the next safe boundary, "
                "then try again."
            )
        else:
            message = (
                f"{owner} is still working, so Mod Studio cannot {action} yet. "
                f"Wait for the {owner} operation to finish, then try again."
            )
        self._set_status(message)
        QMessageBox.information(
            self,
            f"Wait for {owner} to finish",
            message,
        )
        return True

    def _refuse_while_audio_busy(self, action: str) -> bool:
        """Compatibility name for the now-shared Audio/Crib admission fence."""

        return self._refuse_while_embedded_busy(action)

    def _current_search_field(self) -> QLineEdit | None:
        page = self.pages.currentWidget()
        if page is None:
            return None
        fields = tuple(page.findChildren(QLineEdit))

        def available(field: QLineEdit) -> bool:
            # Specialist workspaces can keep several tab-specific searches in
            # the same page tree.  Ctrl+F must never focus a hidden tab's
            # field just because it was constructed first.
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
            self._set_status(
                "This page has no search box • press Ctrl+1 for modding categories"
            )
            return
        field.setFocus(Qt.ShortcutFocusReason)
        field.selectAll()
        self._set_status("Search ready • type to filter this page")

    def _workspace_state(self) -> object | None:
        if self.workspace_store is None:
            return None
        try:
            return self.workspace_store.read()
        except Exception as exc:
            if hasattr(self, "operation_status"):
                self._set_status(
                    f"Recent-file state is unavailable: {str(exc).strip()}"
                )
            return None

    def _refresh_recent_menus(self) -> None:
        state = self._workspace_state()
        if self._recent_source_menu is not None:
            self._recent_source_menu.clear()
            sources = tuple(getattr(state, "recent_sources", ()))
            if not sources:
                empty = self._recent_source_menu.addAction("No recent XISOs")
                empty.setEnabled(False)
            for value in sources:
                path = Path(value)
                action = self._recent_source_menu.addAction(path.name)
                action.setToolTip(str(path))
                action.setEnabled(
                    not self._embedded_operation_is_busy()
                    and path.is_file()
                    and not path.is_symlink()
                )
                action.triggered.connect(
                    lambda _checked=False, selected=path:
                    self._request_source_switch(selected)
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
                    bool(getattr(self.facade, "source_ready", False))
                    and not self._embedded_operation_is_busy()
                    and path.is_file() and not path.is_symlink()
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
            self._recover_action.setEnabled(
                candidate is not None and not self._embedded_operation_is_busy()
            )

    def _prompt_unsaved_decision(self, context: str) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Save your changes first?")
        box.setText("This workspace has changes that are not saved to its project.")
        box.setInformativeText(
            f"{context} can replace the current edit set. Save a retail-free "
            ".2k5mod project, discard these edits, or cancel."
        )
        save = box.addButton("Save Project", QMessageBox.AcceptRole)
        discard = box.addButton("Discard Edits", QMessageBox.DestructiveRole)
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
        """Run ``action`` after preserving or explicitly discarding edits."""

        if not self._workspace_dirty:
            action(False)
            return
        decision = self._prompt_unsaved_decision(context)
        if decision == "discard":
            action(True)
        elif decision == "save":
            self._save_project(
                after_success=lambda: action(False)
            )

    def _defer_until_blocking_task_finished(
        self, action: Callable[[], None]
    ) -> None:
        """Run a chained action only after the current worker releases the shell."""

        if self._blocking:
            self._post_blocking_continuations.append(action)
            return
        action()

    def _drain_post_blocking_continuations(self) -> None:
        """Drain in signal order after ``_set_busy(False)``, never by timer race."""

        pending = self._post_blocking_continuations
        self._post_blocking_continuations = []
        for index, action in enumerate(pending):
            if self._blocking:
                self._post_blocking_continuations.extend(pending[index:])
                return
            try:
                action()
            except Exception as exc:
                self._show_error(
                    "The first operation finished, but its next step could not "
                    f"start: {str(exc).strip() or exc.__class__.__name__}"
                )

    def _prompt_recovery_decision(self, candidate: RecoveryCandidate) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Recover unsaved edits?")
        box.setText("Mod Studio found an autosaved edit set from an interrupted session.")
        box.setInformativeText(
            f"Source: {candidate.source_path.name}\n"
            "The recovery file contains user-authored replacements only."
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
        if self._refuse_while_audio_busy("check recovery edits"):
            return
        if self.workspace_store is None:
            return
        try:
            candidate = self.workspace_store.recovery_candidate(require_source=True)
        except Exception as exc:
            self._set_status(f"Recovery state could not be checked: {str(exc).strip()}")
            return
        if candidate is None:
            self._refresh_recent_menus()
            return
        decision = self._prompt_recovery_decision(candidate)
        if decision == "recover":
            self._recover_candidate(candidate)
        elif decision == "discard":
            self._clear_recovery_safely()

    def _recover_from_menu(self, _checked: bool = False) -> None:
        if self._refuse_while_audio_busy("recover unsaved edits"):
            return
        if self.workspace_store is None:
            return
        try:
            candidate = self.workspace_store.recovery_candidate(require_source=False)
        except Exception as exc:
            self._show_error(f"Recovery state could not be read: {str(exc).strip()}")
            return
        if candidate is None:
            self._set_status("No unsaved recovery project is available.")
            self._refresh_recent_menus()
            return
        if not candidate.source_path.is_file() or candidate.source_path.is_symlink():
            QMessageBox.warning(
                self,
                "Original source needed",
                "The recovery project is safe, but its original XISO is no longer "
                f"available at:\n\n{candidate.source_path}\n\n"
                "Put your legally dumped source back at that path, then choose "
                "Recover Unsaved Edits again.",
            )
            return
        self._recover_candidate(candidate)

    def _open_ps2_save_editor(self, _checked: bool = False) -> None:
        """Open the PS2 memory-card save editor.

        PS2 saves are the user's own files and have nothing to do with the
        Xbox image this window may have loaded, so the editor is a
        self-contained dialog rather than a page in the project workspace.
        The import stays local because the PS2 modules put ``tools/`` on
        ``sys.path`` when they load.
        """

        if self._refuse_while_audio_busy("open the PS2 Save Editor"):
            return
        try:
            from .ps2_save_dialog_qt import Ps2SaveEditorDialog
        except Exception as exc:  # pragma: no cover - defensive import guard
            QMessageBox.warning(
                self,
                "PS2 Save Editor is unavailable",
                f"The PS2 save editor could not be loaded: {str(exc).strip()}\n\n"
                "Nothing was changed.",
            )
            return
        dialog = Ps2SaveEditorDialog(parent=self)
        dialog.exec_()
        dialog.deleteLater()
        self._set_status(
            "PS2 Save Editor closed • your Xbox project was not changed."
        )

    def _recover_candidate(self, candidate: RecoveryCandidate) -> None:
        if self._refuse_while_audio_busy("recover unsaved edits"):
            return
        current_sha = getattr(self.facade, "source_sha256", None)
        if bool(getattr(self.facade, "source_ready", False)) and (
            candidate.source_sha256 is None or current_sha == candidate.source_sha256
        ):
            self._continue_after_unsaved(
                "Recovering the autosave",
                lambda _discarded: self._load_project_path(
                    candidate.project_path, recovery=True
                ),
            )
            return
        self._request_source_switch(candidate.source_path, recovery=candidate)

    def _page_scroll_host(self, page: QWidget) -> QWidget:
        """Wrap a workspace page so it scrolls instead of stretching the window.

        The returned widget is what gets added to the ``pages`` stack; callers
        keep their own reference to ``page`` for behaviour wiring.  A page that
        is already a resizable ``QScrollArea`` is returned unwrapped (only its
        vertical floor is relaxed) so we never nest one scroll area inside
        another.
        """

        if isinstance(page, QScrollArea):
            page.setWidgetResizable(True)
            page.setMinimumHeight(PAGE_SCROLL_MIN_HEIGHT)
            return page
        host = QScrollArea()
        host.setObjectName("pageScrollHost")
        host.setWidgetResizable(True)
        host.setFrameShape(QFrame.NoFrame)
        host.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        host.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        host.setMinimumHeight(PAGE_SCROLL_MIN_HEIGHT)
        host.setWidget(page)
        return host

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 18, 16, 14)
        side_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("2K5")
        mark.setObjectName("brandMark")
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand_title = QLabel("MOD STUDIO")
        brand_title.setObjectName("brandTitle")
        release_candidate = __version__.rsplit("rc", 1)[-1]
        brand_subtitle = QLabel(f"v1.0 RC{release_candidate} • Xbox Edition")
        brand_subtitle.setObjectName("mutedLabel")
        brand.addWidget(brand_title)
        brand.addWidget(brand_subtitle)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand)
        brand_row.addStretch(1)
        side_layout.addLayout(brand_row)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFrameShape(QFrame.NoFrame)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.setSpacing(1)
        self.navigation.setSelectionMode(QAbstractItemView.SingleSelection)
        self.navigation.setAccessibleName("Modding categories")
        self.navigation.setAccessibleDescription(
            "Choose a modding workspace. Press Ctrl+1 to focus this list."
        )
        self.navigation.setToolTip(
            "Choose a modding workspace • Ctrl+1 focuses this list"
        )
        welcome_item = QListWidgetItem("  Getting Started")
        welcome_item.setData(Qt.UserRole, "welcome")
        welcome_item.setSizeHint(QSize(210, 38))
        self.navigation.addItem(welcome_item)
        for category in PRODUCT_CATEGORY_ORDER:
            display_title = category_display_title(self.product_catalog, category)
            item = QListWidgetItem(f"  {display_title}")
            item.setData(Qt.UserRole, category.value)
            item.setSizeHint(QSize(210, 40))
            item.setToolTip(display_title)
            self.navigation.addItem(item)
        side_layout.addWidget(self.navigation, 1)

        safety = QLabel(
            "ORIGINAL STAYS SAFE\nYour source XISO stays read-only. Every build "
            "is a new file."
        )
        safety.setObjectName("safetyCard")
        safety.setWordWrap(True)
        safety.setAccessibleName("Source safety")
        safety.setAccessibleDescription(
            "The original NFL 2K5 XISO remains read-only and every build uses a new file."
        )
        side_layout.addWidget(safety)
        root_layout.addWidget(sidebar)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._build_header())

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.welcome_page = self._build_welcome_page()
        self.pages.addWidget(self._page_scroll_host(self.welcome_page))
        text_specialist_host = _EmbeddedOperationGuardedHost(
            self.facade,
            requester="text",
            require_mutation_admission=self._require_specialist_mutation_admission,
        )
        crib_specialist_host = _EmbeddedOperationGuardedHost(
            self.facade,
            requester="crib",
            require_mutation_admission=self._require_specialist_mutation_admission,
        )
        for category in PRODUCT_CATEGORY_ORDER:
            section = self.product_catalog.section(category)
            visual_kinds = {
                ProductCategory.ROSTERS_PLAYERS: frozenset({
                    "player_portrait", "live_face",
                }),
                ProductCategory.FIELD_ART_CREATE_TEAM: frozenset({
                    "create_team_field_art",
                }),
                ProductCategory.SCOREBUG_PRESENTATION: frozenset({
                    "scorebug_texture",
                }),
            }.get(category)
            if category == ProductCategory.UNIFORMS_EQUIPMENT:
                page = self._build_uniform_page(section)
            elif category == ProductCategory.ROSTERS_PLAYERS:
                if visual_kinds is None:
                    raise RuntimeError("Rosters & Players visual kinds are unavailable")
                portrait_page = self._build_visual_page(section, visual_kinds)
                self._roster_panel = TextRosterPanel(
                    text_specialist_host,
                    view="rosters",
                    on_status=self._specialized_panel_status,
                    on_refresh=self._specialized_panel_refresh,
                )
                roster_tabs = QTabWidget()
                roster_tabs.setObjectName("rostersPlayersTabs")
                roster_tabs.setAccessibleName("Rosters and players workspaces")
                roster_tabs.addTab(self._roster_panel, "Players & Numbers")
                roster_tabs.addTab(portrait_page, "Portraits & Faces")
                page = roster_tabs
            elif category == ProductCategory.TEAM_IDENTITY:
                self._text_roster_panel = TextRosterPanel(
                    text_specialist_host,
                    view="text",
                    on_status=self._specialized_panel_status,
                    on_refresh=self._specialized_panel_refresh,
                )
                page = self._text_roster_panel
            elif category == ProductCategory.CRIB:
                self._crib_panel = CribPanel(
                    crib_specialist_host,
                    operation_admission=lambda: self._embedded_operation_denial(
                        "Crib"
                    ),
                )
                self._crib_panel.operation_state_changed.connect(
                    self._crib_operation_state_changed
                )
                if self._crib_panel.operation_in_progress:
                    self._crib_operation_state_changed(True)
                self._crib_panel.crib_modified.connect(
                    lambda _asset_id: self._specialized_panel_refresh()
                )
                self._crib_panel.crib_reverted.connect(
                    lambda _asset_id: self._specialized_panel_refresh()
                )
                page = self._crib_panel
            elif visual_kinds is not None:
                page = self._build_visual_page(section, visual_kinds)
            elif category == ProductCategory.MENUS_UI:
                raw_fallback = self._build_universal_asset_page(section)
                self._menus_panel = MenusPanel(
                    self.facade,
                    raw_fallback=raw_fallback,
                    capability_page=self._build_capability_page(section),
                )
                page = self._menus_panel
            elif category == ProductCategory.STADIUMS:
                page = self._build_stadium_page(section)
            elif category == ProductCategory.AUDIO:
                self._audio_panel = AudioPanel(
                    self.facade,
                    operation_admission=lambda: self._embedded_operation_denial(
                        "Audio"
                    ),
                )
                self._audio_panel.operation_state_changed.connect(
                    self._audio_operation_state_changed
                )
                self._audio_panel.audio_modified.connect(
                    lambda _asset_id: self._mark_workspace_changed()
                )
                self._audio_panel.audio_reverted.connect(
                    lambda _asset_id: self._mark_workspace_changed()
                )
                self._audio_panel.audio_batch_imported.connect(
                    lambda _changed_count: self._mark_workspace_changed()
                )
                self._audio_panel.audio_annotation_changed.connect(
                    lambda _asset_id: self._mark_workspace_changed()
                )
                page = self._audio_panel
            elif category == ProductCategory.PLAYBOOKS_PLAYS:
                self._playbooks_panel = PlaybooksPanel(self.facade)
                page = self._playbooks_panel
            elif category == ProductCategory.SLIDERS_GAMEPLAY:
                self._gameplay_panel = GameplayPanel(
                    self.facade,
                    capability_page=self._build_capability_page(section),
                )
                page = self._gameplay_panel
            else:
                page = self._build_capability_page(section)
            self._category_pages[category] = page
            self.pages.addWidget(self._page_scroll_host(page))
        workspace_layout.addWidget(self.pages, 1)
        workspace_layout.addWidget(self._build_footer())
        root_layout.addWidget(workspace, 1)

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.currentRowChanged.connect(self._refresh_entered_page)
        self.navigation.setCurrentRow(0)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setMinimumHeight(70)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.page_eyebrow = QLabel("NFL 2K5 • MODDING WORKSPACE")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel("Getting Started")
        self.page_title.setObjectName("pageTitle")
        title_box.addWidget(self.page_eyebrow)
        title_box.addWidget(self.page_title)
        layout.addLayout(title_box)
        layout.addStretch(1)
        self.source_pill = QLabel("●  No game loaded")
        self.source_pill.setObjectName("sourcePill")
        self.source_pill.setAccessibleName("Loaded game status")
        self.source_pill.setToolTip(
            "Load your own NFL 2K5 XISO to enable previews, replacements, and builds."
        )
        self.source_pill.setAccessibleDescription(self.source_pill.toolTip())
        self.open_project_button = QPushButton("Open Project")
        self.open_project_button.setObjectName("secondaryButton")
        self.open_project_button.setToolTip(
            "Apply a retail-free .2k5mod project after loading your own XISO."
        )
        self.open_project_button.setAccessibleName("Open a 2K5 Mod Studio project")
        self.open_project_button.setAccessibleDescription(
            self.open_project_button.toolTip()
        )
        self.open_project_button.clicked.connect(self._choose_project)
        self.save_project_button = QPushButton("Save")
        self.save_project_button.setObjectName("secondaryButton")
        self.save_project_button.setToolTip(
            "Save only your replacement files and metadata — never retail game data."
        )
        self.save_project_button.setAccessibleName("Save the current mod project")
        self.save_project_button.setAccessibleDescription(
            self.save_project_button.toolTip()
        )
        self.save_project_button.clicked.connect(self._save_project)
        self.open_source_button = QPushButton("Open NFL 2K5 XISO")
        self.open_source_button.setObjectName("openSourceButton")
        self.open_source_button.setToolTip(
            "Choose your legally dumped NFL 2K5 XISO. The app opens it read-only."
        )
        self.open_source_button.setAccessibleName("Open an NFL 2K5 XISO")
        self.open_source_button.setAccessibleDescription(
            self.open_source_button.toolTip()
        )
        self.open_source_button.clicked.connect(self._choose_source)
        layout.addWidget(self.source_pill)
        layout.addWidget(self.open_project_button)
        layout.addWidget(self.save_project_button)
        layout.addWidget(self.open_source_button)
        self.navigation.currentRowChanged.connect(self._update_header_title)
        return header

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 28, 34, 26)
        outer.setSpacing(16)
        hero = QLabel("Make NFL 2K5 yours.")
        hero.setObjectName("heroTitle")
        sub = QLabel(
            "Load your own game, replace artwork with familiar PNG files, and "
            "build a fresh XISO ready for xemu — no hex editor required."
        )
        sub.setObjectName("heroSubtitle")
        sub.setWordWrap(True)
        sub.setMaximumWidth(820)
        outer.addWidget(hero)
        outer.addWidget(sub)

        steps = QHBoxLayout()
        steps.setSpacing(12)
        for number, title, body in (
            ("01", "Load your XISO", "Choose your legally dumped USA Xbox copy. It is indexed once and never changed."),
            ("02", "Pick an asset", "Browse a team, uniform set, and exact component. Every part shows its required size."),
            ("03", "Drop in a PNG", "Export a template, edit it in GIMP or Photoshop, then Replace or drag it onto the preview."),
            ("04", "Save, build, play", "Share a retail-free .2k5mod project or create a separate XISO. Your original stays untouched."),
        ):
            card = QFrame()
            card.setObjectName("stepCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 15, 16, 15)
            card_layout.setSpacing(6)
            number_label = QLabel(number)
            number_label.setObjectName("stepNumber")
            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")
            body_label = QLabel(body)
            body_label.setObjectName("cardBody")
            body_label.setWordWrap(True)
            card_layout.addWidget(number_label)
            card_layout.addWidget(title_label)
            card_layout.addWidget(body_label, 1)
            steps.addWidget(card, 1)
        outer.addLayout(steps)

        start = QFrame()
        start.setObjectName("callout")
        start_layout = QHBoxLayout(start)
        start_layout.setContentsMargins(20, 15, 20, 15)
        start_layout.setSpacing(10)
        start_text = QVBoxLayout()
        start_text.setSpacing(2)
        ready = QLabel("Ready for your first uniform edit?")
        ready.setObjectName("cardTitle")
        ready_sub = QLabel(
            "Open the XISO now, or browse all 634 known uniform sets before loading it."
        )
        ready_sub.setObjectName("cardBody")
        start_text.addWidget(ready)
        start_text.addWidget(ready_sub)
        start_layout.addLayout(start_text)
        start_layout.addStretch(1)
        open_button = QPushButton("Choose XISO")
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self._choose_source)
        browse_button = QPushButton("Browse Uniforms")
        browse_button.setObjectName("secondaryButton")
        browse_button.clicked.connect(lambda: self.navigation.setCurrentRow(1))
        start_layout.addWidget(browse_button)
        start_layout.addWidget(open_button)
        outer.addWidget(start)
        outer.addStretch(1)
        return page

    def _build_uniform_page(self, section: ProductCategorySection) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        browser = QFrame()
        browser.setObjectName("panel")
        browser.setFixedWidth(376)
        browser_layout = QVBoxLayout(browser)
        browser_layout.setContentsMargins(16, 15, 16, 16)
        browser_layout.setSpacing(9)
        heading_row = QHBoxLayout()
        heading = QLabel("Uniform sets")
        heading.setObjectName("panelTitle")
        self.uniform_count_label = QLabel("634")
        self.uniform_count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(self.uniform_count_label)
        browser_layout.addLayout(heading_row)

        self.uniform_search = QLineEdit()
        _configure_search_field(
            self.uniform_search,
            placeholder="Search uniforms by team, style, or code…",
            accessible_name="Search uniform sets",
            tooltip="Type one or more words, such as ‘Giants away’. All words must match.",
        )
        self.uniform_search.textChanged.connect(self._filter_uniforms)
        browser_layout.addWidget(self.uniform_search)
        filters = QHBoxLayout()
        self.team_filter = QComboBox()
        self.team_filter.setMinimumWidth(176)
        self.team_filter.setAccessibleName("Filter uniforms by team")
        self.team_filter.setToolTip("Show every team or one team’s assigned uniform sets.")
        self.side_filter = QComboBox()
        self.side_filter.setAccessibleName("Filter uniforms by home or away")
        self.side_filter.setToolTip("Show both sides, home uniforms only, or away uniforms only.")
        self.side_filter.addItem("Home & away", "all")
        self.side_filter.addItem("Home only", "home")
        self.side_filter.addItem("Away only", "away")
        self.team_filter.currentIndexChanged.connect(self._filter_uniforms)
        self.side_filter.currentIndexChanged.connect(self._filter_uniforms)
        filters.addWidget(self.team_filter, 1)
        filters.addWidget(self.side_filter)
        browser_layout.addLayout(filters)

        self.uniform_list = QListWidget()
        self.uniform_list.setObjectName("assetList")
        self.uniform_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.uniform_list.setIconSize(QSize(36, 36))
        self.uniform_list.setSpacing(3)
        self.uniform_list.currentItemChanged.connect(self._select_uniform_set)
        self.uniform_list.itemSelectionChanged.connect(
            self._uniform_set_selection_changed
        )
        browser_layout.addWidget(self.uniform_list, 1)
        outer.addWidget(browser)

        detail = QFrame()
        detail.setObjectName("panel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(10)
        title_row = QHBoxLayout()
        detail_titles = QVBoxLayout()
        detail_titles.setSpacing(1)
        self.uniform_title = QLabel("Choose a uniform set")
        self.uniform_title.setObjectName("panelTitle")
        self.uniform_metadata = QLabel("39 components per set")
        self.uniform_metadata.setObjectName("mutedLabel")
        detail_titles.addWidget(self.uniform_title)
        detail_titles.addWidget(self.uniform_metadata)
        title_row.addLayout(detail_titles)
        title_row.addStretch(1)
        uniform_binding = next(
            (row for row in section.capabilities
             if row.capability_id == "nfl2k5.uniforms.all_visual"),
            None,
        )
        if uniform_binding is not None:
            title_row.addWidget(
                _StatusPill(uniform_binding.status.value, _status_color(uniform_binding.status))
            )
        detail_layout.addLayout(title_row)

        team_kit = QFrame()
        team_kit.setObjectName("teamKitBar")
        team_kit_layout = QVBoxLayout(team_kit)
        team_kit_layout.setContentsMargins(13, 10, 13, 11)
        team_kit_layout.setSpacing(7)
        team_kit_header = QHBoxLayout()
        team_kit_header.setSpacing(8)
        team_kit_title = QLabel("Complete Team Kit")
        team_kit_title.setObjectName("cardTitle")
        self.team_kit_warning = QLabel(
            "Private working export • may contain retail artwork • do not share it. "
            "Share the replacement-only .2k5mod project instead."
        )
        self.team_kit_warning.setObjectName("teamKitWarning")
        self.team_kit_warning.setWordWrap(True)
        team_kit_header.addWidget(team_kit_title)
        team_kit_header.addWidget(self.team_kit_warning, 1)
        team_kit_layout.addLayout(team_kit_header)

        team_kit_controls = QHBoxLayout()
        team_kit_controls.setSpacing(8)
        self.team_kit_scope = QComboBox()
        self.team_kit_scope.setObjectName("teamKitScope")
        self.team_kit_scope.setAccessibleName("Team Kit uniform sides")
        self.team_kit_scope.setToolTip(
            "Export only the selected physical set, its HOME or AWAY partner, "
            "or the complete paired HOME + AWAY kit."
        )
        self.team_kit_scope.addItem("Selected physical set(s)", "SELECTED")
        self.team_kit_scope.addItem("HOME kit", "HOME")
        self.team_kit_scope.addItem("AWAY kit", "AWAY")
        self.team_kit_scope.addItem("HOME + AWAY kit", "BOTH")
        self.team_kit_scope.setCurrentIndex(3)
        self.team_kit_container = QComboBox()
        self.team_kit_container.setObjectName("teamKitFormat")
        self.team_kit_container.setAccessibleName("Team Kit bundle format")
        self.team_kit_container.setToolTip(
            "Use an editable folder for GIMP work, or a deterministic ZIP for hand-off."
        )
        self.team_kit_container.addItem("Editable folder", "folder")
        self.team_kit_container.addItem("ZIP hand-off", "zip")
        self.export_team_kit_button = QPushButton("Export Team Kit")
        self.export_team_kit_button.setObjectName("secondaryButton")
        self.export_team_kit_button.setProperty("teamKitAction", "export")
        self.export_team_kit_button.setAccessibleName("Export complete Team Kit")
        self.export_team_kit_button.setToolTip(
            "Export all 39 supported components per selected physical set."
        )
        self.import_team_kit_button = QPushButton("Import Edited Kit")
        self.import_team_kit_button.setObjectName("primaryButton")
        self.import_team_kit_button.setProperty("teamKitAction", "import")
        self.import_team_kit_button.setAccessibleName("Import edited Team Kit")
        self.import_team_kit_button.setToolTip(
            "Validate every PNG first, then stage only pixel changes as one Undo action."
        )
        self.export_team_kit_button.clicked.connect(self._choose_team_kit_export)
        self.import_team_kit_button.clicked.connect(self._choose_team_kit_import)
        team_kit_controls.addWidget(self.team_kit_scope, 2)
        team_kit_controls.addWidget(self.team_kit_container, 1)
        team_kit_controls.addStretch(1)
        team_kit_controls.addWidget(self.export_team_kit_button)
        team_kit_controls.addWidget(self.import_team_kit_button)
        team_kit_layout.addLayout(team_kit_controls)
        detail_layout.addWidget(team_kit)

        split = QHBoxLayout()
        split.setSpacing(14)
        self.component_tree = QTreeWidget()
        self.component_tree.setObjectName("componentTree")
        self.component_tree.setHeaderLabels(("Component", "Size", "State"))
        self.component_tree.setRootIsDecorated(True)
        self.component_tree.setAlternatingRowColors(True)
        self.component_tree.setMinimumWidth(190)
        self.component_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.component_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.component_tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.component_tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.component_tree.currentItemChanged.connect(self._select_component)
        split.addWidget(self.component_tree, 5)

        preview_column = QVBoxLayout()
        self.preview = _PngDropPreview()
        self.preview.png_dropped.connect(self._replace_from_drop)
        preview_column.addWidget(self.preview, 1)
        self.component_help = QLabel(
            "Required dimensions and format will appear when you select a component."
        )
        self.component_help.setObjectName("mutedLabel")
        self.component_help.setWordWrap(True)
        preview_column.addWidget(self.component_help)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.export_button = QPushButton("Export PNG")
        self.export_button.setObjectName("secondaryButton")
        self.replace_button = QPushButton("Replace PNG")
        self.replace_button.setObjectName("primaryButton")
        self.revert_button = QPushButton("Revert")
        self.revert_button.setObjectName("dangerQuietButton")
        self.export_button.clicked.connect(self._export_selected)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.revert_button.clicked.connect(self._revert_selected)
        actions.addWidget(self.export_button)
        actions.addWidget(self.replace_button)
        actions.addWidget(self.revert_button)
        preview_column.addLayout(actions)
        split.addLayout(preview_column, 6)
        detail_layout.addLayout(split, 1)
        outer.addWidget(detail, 1)
        return page

    def _build_capability_page(self, section: ProductCategorySection) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(12)
        title = QLabel(section.title)
        title.setObjectName("heroTitleSmall")
        subtitle = QLabel(
            "Every known capability stays visible. Status updates unlock editing "
            "without changing this workspace."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        counts = QHBoxLayout()
        for status, count in (
            (ProductStatus.EDITABLE, section.counts.editable),
            (ProductStatus.PREVIEW, section.counts.preview),
            (ProductStatus.EXPORT_ONLY, section.counts.export_only),
            (ProductStatus.COMING_SOON, section.counts.coming_soon),
        ):
            counts.addWidget(_StatusPill(f"{count} {status.value}", _status_color(status)))
        counts.addStretch(1)
        layout.addLayout(counts)

        for note in section.findings_notes:
            notice = QLabel(note)
            notice.setObjectName("findingsBanner")
            notice.setWordWrap(True)
            layout.addWidget(notice)

        if section.capabilities:
            for binding in section.capabilities:
                layout.addWidget(self._capability_card(binding))
        else:
            empty = QFrame()
            empty.setObjectName("capabilityCard")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(18, 16, 18, 16)
            empty_layout.setSpacing(6)
            empty_title = QLabel("Shared capability surface")
            empty_title.setObjectName("cardTitle")
            empty_body = QLabel(
                "This tab is already connected to the registry. Its current "
                "features are supplied by a capability shared with another tab."
            )
            empty_body.setObjectName("cardBody")
            empty_body.setWordWrap(True)
            empty_layout.addWidget(empty_title)
            empty_layout.addWidget(empty_body)
            if section.related_capability_ids:
                related = QLabel(
                    "Registry link: " + ", ".join(section.related_capability_ids)
                )
                related.setObjectName("codeLabel")
                related.setWordWrap(True)
                empty_layout.addWidget(related)
            layout.addWidget(empty)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_visual_page(
        self, section: ProductCategorySection, kinds: frozenset[str]
    ) -> QWidget:
        assets = tuple(
            asset for asset in self.extended_visual_catalog.assets
            if asset.kind in kinds
        )
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        browser = QFrame()
        browser.setObjectName("panel")
        browser.setFixedWidth(376)
        browser_layout = QVBoxLayout(browser)
        browser_layout.setContentsMargins(16, 15, 16, 16)
        browser_layout.setSpacing(9)
        heading_row = QHBoxLayout()
        heading = QLabel(section.title)
        heading.setObjectName("panelTitle")
        count_label = QLabel(f"{len(assets):,}")
        count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(count_label)
        browser_layout.addLayout(heading_row)
        search = QLineEdit()
        _configure_search_field(
            search,
            placeholder="Search by player, asset ID, texture, or group…",
            accessible_name=f"Search {section.title}",
            tooltip="Filter this list by any visible name, ID, texture, or asset group.",
        )
        browser_layout.addWidget(search)
        group_filter = QComboBox()
        group_filter.setAccessibleName(f"Filter {section.title} by asset group")
        group_filter.setToolTip("Limit the list to one asset group.")
        group_filter.addItem("All asset groups", None)
        for group in sorted({asset.group for asset in assets}, key=str.casefold):
            group_filter.addItem(group, group)
        browser_layout.addWidget(group_filter)
        asset_list = QListWidget()
        asset_list.setObjectName("assetList")
        asset_list.setIconSize(QSize(36, 36))
        asset_list.setSpacing(3)
        browser_layout.addWidget(asset_list, 1)
        outer.addWidget(browser)

        detail = QFrame()
        detail.setObjectName("panel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(10)
        title_row = QHBoxLayout()
        detail_titles = QVBoxLayout()
        detail_titles.setSpacing(1)
        title = QLabel("Choose an asset")
        title.setObjectName("panelTitle")
        metadata = QLabel("Export a template or replace it with an exact-size PNG")
        metadata.setObjectName("mutedLabel")
        detail_titles.addWidget(title)
        detail_titles.addWidget(metadata)
        title_row.addLayout(detail_titles)
        title_row.addStretch(1)
        title_row.addWidget(_StatusPill("Editable", _status_color(ProductStatus.EDITABLE)))
        detail_layout.addLayout(title_row)
        preview = _PngDropPreview()
        detail_layout.addWidget(preview, 1)
        help_label = QLabel(
            "Choose an asset to see its authoring size and build-route note."
        )
        help_label.setObjectName("mutedLabel")
        help_label.setWordWrap(True)
        detail_layout.addWidget(help_label)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        export_button = QPushButton("Export PNG")
        export_button.setObjectName("secondaryButton")
        replace_button = QPushButton("Replace PNG")
        replace_button.setObjectName("primaryButton")
        revert_button = QPushButton("Revert")
        revert_button.setObjectName("dangerQuietButton")
        actions.addWidget(export_button)
        actions.addWidget(replace_button)
        actions.addWidget(revert_button)
        detail_layout.addLayout(actions)
        outer.addWidget(detail, 1)

        state = _VisualBrowserState(
            section.category, kinds, assets, search, group_filter, asset_list,
            count_label, title, metadata, preview, help_label, export_button,
            replace_button, revert_button,
        )
        self._visual_browsers[section.category] = state
        search.textChanged.connect(
            lambda _text, category=section.category: self._filter_visual_assets(category)
        )
        group_filter.currentIndexChanged.connect(
            lambda _index, category=section.category: self._filter_visual_assets(category)
        )
        asset_list.currentItemChanged.connect(
            lambda current, previous, category=section.category:
                self._select_visual_asset(category, current, previous)
        )
        preview.png_dropped.connect(
            lambda path, category=section.category:
                self._replace_visual_from_drop(category, path)
        )
        export_button.clicked.connect(
            lambda _checked=False, category=section.category:
                self._export_visual_asset(category)
        )
        replace_button.clicked.connect(
            lambda _checked=False, category=section.category:
                self._choose_visual_replacement(category)
        )
        revert_button.clicked.connect(
            lambda _checked=False, category=section.category:
                self._revert_visual_asset(category)
        )
        self._filter_visual_assets(section.category)
        return page

    def _build_universal_asset_page(
        self, _section: ProductCategorySection
    ) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        browser = QFrame()
        browser.setObjectName("panel")
        browser.setFixedWidth(410)
        layout = QVBoxLayout(browser)
        layout.setContentsMargins(16, 15, 16, 16)
        layout.setSpacing(9)
        heading_row = QHBoxLayout()
        heading = QLabel("All indexed game assets")
        heading.setObjectName("panelTitle")
        count_label = QLabel("Load XISO")
        count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(count_label)
        layout.addLayout(heading_row)
        note = QLabel(
            "Universal coverage: every resource found in your copy appears here, "
            "even when its format is not decoded yet."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search = QLineEdit()
        _configure_search_field(
            search,
            placeholder="Search asset ID, type, or archive entry…",
            accessible_name="Search all indexed game assets",
            tooltip="Search resource IDs, four-character format codes, and archive entries.",
        )
        search_button = QPushButton("Search")
        search_button.setObjectName("secondaryButton")
        search_row.addWidget(search, 1)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)
        kind_filter = QComboBox()
        kind_filter.setAccessibleName("Filter by resource type")
        kind_filter.setToolTip("Limit results to one decoded or unknown resource type.")
        kind_filter.addItem("All 41 resource kinds", None)
        layout.addWidget(kind_filter)
        asset_list = QListWidget()
        asset_list.setObjectName("assetList")
        asset_list.setSpacing(2)
        layout.addWidget(asset_list, 1)
        pager = QHBoxLayout()
        previous_button = QPushButton("Previous")
        previous_button.setObjectName("secondaryButton")
        range_label = QLabel("Load your XISO to browse")
        range_label.setObjectName("mutedLabel")
        range_label.setAlignment(Qt.AlignCenter)
        next_button = QPushButton("Next")
        next_button.setObjectName("secondaryButton")
        pager.addWidget(previous_button)
        pager.addWidget(range_label, 1)
        pager.addWidget(next_button)
        layout.addLayout(pager)
        outer.addWidget(browser)

        detail = QFrame()
        detail.setObjectName("panel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(12)
        title_row = QHBoxLayout()
        title = QLabel("Nothing hidden")
        title.setObjectName("panelTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(
            _StatusPill("Export-only", _status_color(ProductStatus.EXPORT_ONLY))
        )
        detail_layout.addLayout(title_row)
        explanation = QLabel(
            "Decoded editors live in their normal tabs. This complete inventory "
            "is the safety net for everything else: inspect metadata and export "
            "the exact resource wrapper/body for external research or archiving."
        )
        explanation.setObjectName("heroSubtitle")
        explanation.setWordWrap(True)
        detail_layout.addWidget(explanation)
        asset_id_label = QLabel("Choose a resource from the indexed list")
        asset_id_label.setObjectName("codeLabel")
        asset_id_label.setWordWrap(True)
        detail_layout.addWidget(asset_id_label)
        detail_label = QLabel(
            "The source XISO stays read-only. Raw exports are new files and do "
            "not imply that a safe replacement writer exists."
        )
        detail_label.setObjectName("findingsNote")
        detail_label.setWordWrap(True)
        detail_layout.addWidget(detail_label)
        detail_layout.addStretch(1)
        export_button = QPushButton("Export Raw Resource")
        export_button.setObjectName("primaryButton")
        export_button.setEnabled(False)
        detail_layout.addWidget(export_button, 0, Qt.AlignRight)
        outer.addWidget(detail, 1)

        state = _UniversalBrowserState(
            search, kind_filter, asset_list, count_label, range_label,
            previous_button, next_button, export_button, asset_id_label,
            detail_label,
        )
        self._universal_browser = state
        search.returnPressed.connect(lambda: self._query_universal_assets(reset=True))
        search_button.clicked.connect(lambda: self._query_universal_assets(reset=True))
        kind_filter.currentIndexChanged.connect(
            lambda _index: self._query_universal_assets(reset=True)
        )
        previous_button.clicked.connect(lambda: self._page_universal_assets(-1))
        next_button.clicked.connect(lambda: self._page_universal_assets(1))
        asset_list.currentItemChanged.connect(self._select_universal_asset)
        export_button.clicked.connect(self._export_universal_asset)
        previous_button.setEnabled(False)
        next_button.setEnabled(False)
        return page

    def _build_stadium_page(
        self, _section: ProductCategorySection
    ) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        scenes_panel = QFrame()
        scenes_panel.setObjectName("panel")
        scenes_panel.setFixedWidth(300)
        scenes_layout = QVBoxLayout(scenes_panel)
        scenes_layout.setContentsMargins(14, 14, 14, 14)
        scenes_layout.setSpacing(8)
        heading_row = QHBoxLayout()
        heading = QLabel("Stadium scenes")
        heading.setObjectName("panelTitle")
        count_label = QLabel("477")
        count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(count_label)
        scenes_layout.addLayout(heading_row)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search = QLineEdit()
        _configure_search_field(
            search,
            placeholder="Search stadium or scene ID…",
            accessible_name="Search stadium scenes",
            tooltip="Search the stadium archive name or its scene ID.",
        )
        search_button = QPushButton("Search")
        search_button.setObjectName("secondaryButton")
        search_row.addWidget(search, 1)
        search_row.addWidget(search_button)
        scenes_layout.addLayout(search_row)
        scene_list = QListWidget()
        scene_list.setObjectName("assetList")
        scene_list.setSpacing(2)
        scenes_layout.addWidget(scene_list, 1)
        scenes_note = QLabel(
            "Models are private glTF exports generated from the user's own game."
        )
        scenes_note.setObjectName("mutedLabel")
        scenes_note.setWordWrap(True)
        scenes_layout.addWidget(scenes_note)
        outer.addWidget(scenes_panel)

        view_panel = QFrame()
        view_panel.setObjectName("panel")
        view_layout = QVBoxLayout(view_panel)
        view_layout.setContentsMargins(14, 14, 14, 14)
        view_layout.setSpacing(8)
        view_title_row = QHBoxLayout()
        scene_titles = QVBoxLayout()
        scene_titles.setSpacing(1)
        scene_label = QLabel("Stadium Studio")
        scene_label.setObjectName("panelTitle")
        scene_metadata = QLabel(
            "Orbit • pan • zoom • click a surface to find its owning texture"
        )
        scene_metadata.setObjectName("mutedLabel")
        scene_titles.addWidget(scene_label)
        scene_titles.addWidget(scene_metadata)
        reset_button = QPushButton("Reset View")
        reset_button.setObjectName("secondaryButton")
        view_title_row.addLayout(scene_titles, 1)
        view_title_row.addWidget(reset_button)
        view_layout.addLayout(view_title_row)
        viewport = StadiumViewport()
        viewport.setMinimumSize(430, 300)
        view_layout.addWidget(viewport, 1)
        outer.addWidget(view_panel, 1)

        texture_panel = QFrame()
        texture_panel.setObjectName("panel")
        texture_panel.setFixedWidth(340)
        texture_layout = QVBoxLayout(texture_panel)
        texture_layout.setContentsMargins(14, 14, 14, 14)
        texture_layout.setSpacing(8)
        texture_heading = QLabel("Surface textures")
        texture_heading.setObjectName("panelTitle")
        texture_layout.addWidget(texture_heading)
        self._stadium_people_filter = QCheckBox("People & sideline only")
        self._stadium_people_filter.setObjectName("codeLabel")
        self._stadium_people_filter.setToolTip(
            "Show only fan, cheerleader, coach, official, chain-crew, "
            "camera, usher, and sideline textures in this scene."
        )
        texture_layout.addWidget(self._stadium_people_filter)
        texture_list = QListWidget()
        texture_list.setObjectName("assetList")
        texture_list.setMaximumHeight(180)
        texture_layout.addWidget(texture_list)
        texture_preview = _PngDropPreview()
        texture_preview.setMinimumSize(280, 210)
        texture_layout.addWidget(texture_preview, 1)
        texture_label = QLabel("Click a surface or choose a texture")
        texture_label.setObjectName("codeLabel")
        texture_label.setWordWrap(True)
        texture_layout.addWidget(texture_label)
        findings = QLabel(
            "Textures marked Editable can be replaced at their exact dimensions. "
            "Surfaces that share one material texture change together. Some highly "
            "detailed artwork may be too large for the game’s fixed storage space; "
            "the app will reject it safely and explain why. Other formats remain "
            "Preview/Export-only."
        )
        findings.setObjectName("findingsNote")
        findings.setWordWrap(True)
        texture_layout.addWidget(findings)
        texture_actions = QHBoxLayout()
        texture_actions.setSpacing(7)
        export_button = QPushButton("Export")
        export_button.setObjectName("secondaryButton")
        replace_button = QPushButton("Replace")
        replace_button.setObjectName("primaryButton")
        revert_button = QPushButton("Revert")
        revert_button.setObjectName("dangerQuietButton")
        texture_actions.addWidget(export_button)
        texture_actions.addWidget(replace_button)
        texture_actions.addWidget(revert_button)
        texture_layout.addLayout(texture_actions)
        outer.addWidget(texture_panel)

        state = _StadiumBrowserState(
            search, scene_list, count_label, viewport, scene_label,
            scene_metadata, texture_list, texture_preview, texture_label,
            findings, export_button, replace_button, revert_button,
        )
        self._stadium_browser = state
        search.returnPressed.connect(lambda: self._load_stadium_scenes(force=True))
        search_button.clicked.connect(lambda: self._load_stadium_scenes(force=True))
        self._stadium_people_filter.toggled.connect(
            lambda _checked: self._select_stadium_scene(
                self._stadium_browser.scene_list.currentItem()
                if self._stadium_browser is not None else None,
                None,
            )
        )
        scene_list.currentItemChanged.connect(self._select_stadium_scene)
        viewport.surfaceSelected.connect(self._select_stadium_surface)
        reset_button.clicked.connect(viewport.reset_view)
        texture_list.currentItemChanged.connect(self._select_stadium_texture)
        texture_preview.png_dropped.connect(self._replace_stadium_texture_drop)
        export_button.clicked.connect(self._export_stadium_texture)
        replace_button.clicked.connect(self._choose_stadium_texture_replacement)
        revert_button.clicked.connect(self._revert_stadium_texture)
        for button in (export_button, replace_button, revert_button):
            button.setEnabled(False)
        if not bool(getattr(self.facade, "stadium_available", False)):
            count_label.setText("Load XISO")
            scene_metadata.setText(
                "Load your XISO, then open this tab to prepare private stadium assets."
            )
        return page

    def _capability_card(self, binding: ProductCapability) -> QWidget:
        card = QFrame()
        card.setObjectName("capabilityCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(6)
        title_row = QHBoxLayout()
        title = QLabel(binding.title)
        title.setObjectName("cardTitle")
        title_row.addWidget(title, 1)
        title_row.addWidget(_StatusPill(binding.status.value, _status_color(binding.status)))
        layout.addLayout(title_row)
        summary = QLabel(binding.capability.summary)
        summary.setObjectName("cardBody")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        notes = capability_findings(binding)
        if notes:
            findings = QLabel("Why this status: " + "  ".join(notes))
            findings.setObjectName("findingsNote")
            findings.setWordWrap(True)
            layout.addWidget(findings)
        capability_id = QLabel(binding.capability_id)
        capability_id.setObjectName("codeLabel")
        layout.addWidget(capability_id)
        return card

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setMinimumHeight(70)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(8)
        status_box = QVBoxLayout()
        status_box.setSpacing(4)
        self.operation_status = QLabel(
            "Ready — load a game or browse what’s available"
        )
        self.operation_status.setObjectName("operationStatus")
        self.operation_status.setTextFormat(Qt.PlainText)
        self.operation_status.setAccessibleName("Current operation status")
        self.operation_status.setAccessibleDescription(
            "Reports what the app is doing and whether an operation succeeded."
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName("Current operation progress")
        self.progress_bar.setAccessibleDescription(
            "Progress for indexing, exporting, replacing, saving, or building."
        )
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.hide()
        status_box.addWidget(self.operation_status)
        status_box.addWidget(self.progress_bar)
        layout.addLayout(status_box, 1)
        self.edit_count = QLabel("No pending edits")
        self.edit_count.setObjectName("editCount")
        self.edit_count.setToolTip("Edits included in the next modded XISO build.")
        self.edit_count.setAccessibleName("Pending edit count")
        self.edit_count.setAccessibleDescription(self.edit_count.toolTip())
        self.undo_button = QPushButton("Undo")
        self.undo_button.setObjectName("secondaryButton")
        self.revert_all_button = QPushButton("Revert All")
        self.revert_all_button.setObjectName("dangerQuietButton")
        self.build_button = QPushButton("Build Modded XISO")
        self.build_button.setObjectName("buildButton")
        self.build_button.setToolTip(
            "Create a separate modded XISO. Your original game file is never changed."
        )
        self.launch_button = QPushButton("Launch Latest Build")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.setToolTip(
            "Build a modded XISO and configure xemu to enable one-click launch."
        )
        self.undo_button.setAccessibleName("Undo the most recent project edit")
        self.undo_button.setAccessibleDescription(
            "Undo one replacement, text edit, or other project change."
        )
        self.revert_all_button.setAccessibleName("Revert every project edit")
        self.revert_all_button.setAccessibleDescription(
            "Remove every pending edit after confirmation; the source XISO is untouched."
        )
        self.build_button.setAccessibleName("Build a separate modded XISO")
        self.build_button.setAccessibleDescription(self.build_button.toolTip())
        self.launch_button.setAccessibleName("Launch the latest build in xemu")
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        self.undo_button.clicked.connect(self._undo)
        self.revert_all_button.clicked.connect(self._revert_all)
        self.build_button.clicked.connect(self._choose_build_output)
        self.launch_button.clicked.connect(self._launch_xemu)
        layout.addWidget(self.edit_count)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.revert_all_button)
        layout.addWidget(self.build_button)
        layout.addWidget(self.launch_button)
        return footer

    def _populate_uniform_filters(self) -> None:
        owners = sorted(
            {name for uniform_set in self.uniform_catalog.uniform_sets
             for name in uniform_set.team_names},
            key=str.casefold,
        )
        self.team_filter.blockSignals(True)
        self.team_filter.addItem("All teams", None)
        for owner in owners:
            self.team_filter.addItem(owner, owner)
        self.team_filter.addItem("Unassigned / create-team", "__unassigned__")
        self.team_filter.blockSignals(False)

    def _filter_uniforms(self) -> None:
        if not hasattr(self, "uniform_list"):
            return
        selected = self._selected_set.selector if self._selected_set else None
        criteria = UniformFilter(
            query=self.uniform_search.text(),
            side=str(self.side_filter.currentData() or "all"),
            owner=self.team_filter.currentData(),
        )
        rows = filter_uniform_sets(self.uniform_catalog.uniform_sets, criteria)
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        self.uniform_list.blockSignals(True)
        self.uniform_list.clear()
        restore_row = -1
        for index, uniform_set in enumerate(rows):
            set_modified = bool(modified.intersection(uniform_set.asset_ids))
            prefix = "●  " if set_modified else ""
            item = QListWidgetItem(prefix + uniform_set.label)
            item.setData(Qt.UserRole, uniform_set.selector)
            item.setToolTip(
                f"{uniform_set.selector} • {uniform_set.uniform_package} • "
                f"{len(uniform_set.asset_ids)} components"
            )
            item.setSizeHint(QSize(330, 49))
            item.setIcon(self._uniform_icon(uniform_set))
            if set_modified:
                item.setForeground(QColor("#ffbe5c"))
            self.uniform_list.addItem(item)
            if uniform_set.selector == selected:
                restore_row = index
        self.uniform_list.blockSignals(False)
        self.uniform_count_label.setText(f"{len(rows):,}")
        if rows:
            self.uniform_list.setCurrentRow(restore_row if restore_row >= 0 else 0)
        else:
            self._selected_set = None
            self._selected_asset = None
            self.component_tree.clear()
            self.uniform_title.setText("No matching uniform sets")
            self.uniform_metadata.setText("Try a broader search or another filter.")
            self.preview.set_empty("No uniform set selected")
            self._refresh_team_kit_scope_labels()
            self._refresh_action_states()

    def _uniform_icon(self, uniform_set: UniformSet) -> QIcon:
        cached = self._monogram_icons.get(uniform_set.selector)
        if cached is not None:
            return cached
        abbreviation = (
            uniform_set.team_abbreviations[0]
            if uniform_set.team_abbreviations
            else uniform_set.asset_code
        )[:3].upper()
        seed = sum(uniform_set.selector.encode("utf-8"))
        colors = ("#3269d6", "#6b45c7", "#16857a", "#a34e66", "#a06427")
        pixmap = QPixmap(42, 42)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(colors[seed % len(colors)]))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(1, 1, 40, 40, 9, 9)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(12 if len(abbreviation) == 3 else 14)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, abbreviation)
        painter.end()
        icon = QIcon(pixmap)
        self._monogram_icons[uniform_set.selector] = icon
        return icon

    def _visual_icon(self, asset: ExtendedVisualAsset) -> QIcon:
        cached = self._monogram_icons.get(asset.asset_id)
        if cached is not None:
            return cached
        abbreviation = {
            "player_portrait": "P",
            "live_face": (asset.family or "F").upper(),
            "create_team_field_art": "50" if asset.logo_code is None else str(asset.logo_code),
            "scorebug_texture": "TV",
        }.get(asset.kind, "2K5")[:3]
        seed = sum(asset.asset_id.encode("utf-8"))
        colors = ("#3269d6", "#6b45c7", "#16857a", "#a34e66", "#a06427")
        pixmap = QPixmap(42, 42)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(colors[seed % len(colors)]))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(1, 1, 40, 40, 9, 9)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(12 if len(abbreviation) >= 3 else 15)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, abbreviation)
        painter.end()
        icon = QIcon(pixmap)
        self._monogram_icons[asset.asset_id] = icon
        return icon

    def _filter_visual_assets(self, category: ProductCategory) -> None:
        state = self._visual_browsers[category]
        words = tuple(
            word for word in state.search.text().casefold().split() if word
        )
        group = state.group_filter.currentData()
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        rows: list[ExtendedVisualAsset] = []
        for asset in state.assets:
            if group and asset.group != group:
                continue
            haystack = " ".join((
                asset.asset_id,
                asset.label,
                asset.group,
                asset.kind,
                asset.target_selector,
                *asset.search_terms,
            )).casefold()
            if words and not all(word in haystack for word in words):
                continue
            rows.append(asset)
        state.asset_list.blockSignals(True)
        state.asset_list.clear()
        restore_row = -1
        for index, asset in enumerate(rows):
            changed = asset.asset_id in modified
            item = QListWidgetItem(("●  " if changed else "") + asset.label)
            item.setData(Qt.UserRole, asset.asset_id)
            item.setToolTip(
                f"{asset.target_selector} • {asset.width}×{asset.height} • {asset.group}"
            )
            item.setSizeHint(QSize(330, 49))
            item.setIcon(self._visual_icon(asset))
            if changed:
                item.setForeground(QColor("#ffbe5c"))
            state.asset_list.addItem(item)
            if asset.asset_id == state.selected_asset_id:
                restore_row = index
        state.asset_list.blockSignals(False)
        state.count_label.setText(f"{len(rows):,}")
        if rows:
            state.asset_list.setCurrentRow(restore_row if restore_row >= 0 else 0)
        else:
            state.selected_asset_id = None
            state.title.setText("No matching assets")
            state.metadata.setText("Try a broader search or another group.")
            state.preview.set_empty("No asset selected")
            self._refresh_visual_action_states(state)

    def _select_visual_asset(
        self,
        category: ProductCategory,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        state = self._visual_browsers[category]
        asset_id = str(current.data(Qt.UserRole))
        asset = self.extended_visual_catalog.get_asset(asset_id)
        state.selected_asset_id = asset_id
        self._selected_asset = asset
        state.title.setText(asset.label)
        route = "Unified visual/data build"
        state.metadata.setText(
            f"{asset.group} • {asset.width}×{asset.height} • {route}"
        )
        route_note = ""
        if asset.writer_route is VisualWriterRoute.SCOREBUG:
            route_note = (
                " This texture now composes with uniforms, portraits, text, audio, "
                "and editable Crib textures in the same one-click XISO build."
            )
        state.help_label.setText(
            f"{asset.authoring_note or 'Use an exact-size RGBA PNG.'}{route_note}"
        )
        self._refresh_visual_action_states(state)
        if bool(getattr(self.facade, "source_ready", False)):
            self._load_visual_preview(asset, state.preview)
        else:
            state.preview.set_empty(
                f"{asset.label}\n{asset.width} × {asset.height} RGBA PNG\n\n"
                "Load your XISO to see the original."
            )

    def _load_visual_preview(
        self, asset: ExtendedVisualAsset, preview: _PngDropPreview
    ) -> None:
        self._preview_generation += 1
        generation = self._preview_generation
        preview.set_loading(f"Preparing {asset.label}…")

        def success(value: object) -> None:
            if generation != self._preview_generation:
                return
            if not preview.set_png(Path(value)):
                self._set_status("Preview unavailable — the asset was not changed.")

        self._start_task(
            lambda progress: self.facade.preview_asset(asset, progress),
            success,
            label=f"Preparing {asset.label}",
            blocking=False,
            show_errors=False,
        )

    def _selected_visual(
        self, category: ProductCategory
    ) -> tuple[_VisualBrowserState, ExtendedVisualAsset] | None:
        state = self._visual_browsers[category]
        if state.selected_asset_id is None:
            return None
        return state, self.extended_visual_catalog.get_asset(state.selected_asset_id)

    def _export_visual_asset(self, category: ProductCategory) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        _state, asset = selected
        suggested = asset.asset_id.replace(".", "-") + ".png"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", str(Path.home() / suggested), "PNG image (*.png)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".png":
            destination = destination.with_suffix(".png")

        def success(result: object) -> None:
            self._set_status(f"Exported {asset.label} to {Path(result).name}")

        self._start_task(
            lambda progress: self.facade.export_asset(asset, destination, progress),
            success,
            label=f"Exporting {asset.label}",
            blocking=True,
        )

    def _choose_visual_replacement(self, category: ProductCategory) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        state, asset = selected
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Replace {asset.label}", str(Path.home()), "PNG image (*.png)"
        )
        if filename:
            self._replace_visual_asset(state, asset, Path(filename))

    def _replace_visual_from_drop(
        self, category: ProductCategory, supplied: object
    ) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            self._show_error("Choose an asset before dropping a PNG.")
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before replacing an asset.")
            return
        state, asset = selected
        self._replace_visual_asset(state, asset, Path(supplied))

    def _replace_visual_asset(
        self,
        state: _VisualBrowserState,
        asset: ExtendedVisualAsset,
        path: Path,
    ) -> None:
        def success(result: object) -> None:
            self._set_status(_result_message(result, f"{asset.label} is ready to build."))
            state.selected_asset_id = asset.asset_id
            self._filter_visual_assets(state.category)
            self._mark_workspace_changed()
            self._load_visual_preview(asset, state.preview)

        self._start_task(
            lambda progress: self.facade.replace_asset(asset, path, progress),
            success,
            label=f"Checking and replacing {asset.label}",
            blocking=True,
        )

    def _revert_visual_asset(self, category: ProductCategory) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        state, asset = selected

        def success(result: object) -> None:
            self._set_status(_result_message(result, f"Reverted {asset.label}."))
            state.selected_asset_id = asset.asset_id
            self._filter_visual_assets(category)
            self._mark_workspace_changed()
            self._load_visual_preview(asset, state.preview)

        self._start_task(
            lambda progress: self.facade.revert_asset(asset, progress),
            success,
            label=f"Reverting {asset.label}",
            blocking=True,
        )

    def _refresh_visual_action_states(self, state: _VisualBrowserState) -> None:
        ready = bool(getattr(self.facade, "source_ready", False))
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        selected = state.selected_asset_id is not None
        enabled = (
            ready
            and selected
            and not self._blocking
            and not self._embedded_operation_is_busy()
        )
        state.export_button.setEnabled(enabled)
        state.replace_button.setEnabled(enabled)
        state.revert_button.setEnabled(
            enabled and state.selected_asset_id in modified
        )

    def _preview_selected_asset(self) -> None:
        asset = self._selected_asset
        if asset is None:
            return
        if isinstance(asset, ExtendedVisualAsset):
            for state in self._visual_browsers.values():
                if asset.kind in state.kinds:
                    self._load_visual_preview(asset, state.preview)
                    return
        else:
            self._load_preview(asset)

    def _ensure_universal_browser(self) -> None:
        state = self._universal_browser
        if state is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        if state.kinds_loaded:
            if not state.rows:
                self._query_universal_assets(reset=True)
            return
        if state.kinds_loading:
            return
        state.kinds_loading = True
        state.range_label.setText("Preparing all resource kinds…")

        def success(result: object) -> None:
            rows = tuple(result)  # type: ignore[arg-type]
            state.kind_filter.blockSignals(True)
            state.kind_filter.clear()
            state.kind_filter.addItem("All resource kinds", None)
            for kind, count in rows:
                state.kind_filter.addItem(f"{kind}  •  {int(count):,}", str(kind))
            state.kind_filter.blockSignals(False)
            state.kinds_loaded = True
            state.kinds_loading = False
            self._query_universal_assets(reset=True)

        self._start_task(
            lambda progress: self.facade.resource_kinds(progress),
            success,
            label="Preparing the complete asset browser",
            blocking=False,
        )

    def _query_universal_assets(self, *, reset: bool) -> None:
        state = self._universal_browser
        if state is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        if not state.kinds_loaded:
            self._ensure_universal_browser()
            return
        if reset:
            state.offset = 0
        state.generation += 1
        generation = state.generation
        search = state.search.text().strip()
        kind = state.kind_filter.currentData()
        state.range_label.setText("Loading asset page…")

        def success(result: object) -> None:
            if generation != state.generation:
                return
            rows_value, total_value = result  # type: ignore[misc]
            state.rows = tuple(rows_value)
            state.total = int(total_value)
            state.asset_list.blockSignals(True)
            state.asset_list.clear()
            for record in state.rows:
                item = QListWidgetItem(
                    f"{record.kind}  •  outer {record.outer_index} / chunk "
                    f"{record.chunk_index}  •  {record.raw_size:,} bytes"
                )
                item.setData(Qt.UserRole, record.asset_id)
                item.setToolTip(record.asset_id)
                item.setSizeHint(QSize(370, 42))
                state.asset_list.addItem(item)
            state.asset_list.blockSignals(False)
            state.count_label.setText(f"{state.total:,}")
            if state.rows:
                first = state.offset + 1
                last = state.offset + len(state.rows)
                state.range_label.setText(
                    f"{first:,}–{last:,} of {state.total:,} indexed"
                )
                state.asset_list.setCurrentRow(0)
            else:
                state.range_label.setText("No matching resources on this page")
                state.asset_id_label.setText("No resource selected")
                state.detail_label.setText(
                    "Try a broader search, another FourCC, or the previous page."
                )
            state.previous_button.setEnabled(
                state.offset > 0
                and not self._blocking
                and not self._embedded_operation_is_busy()
            )
            state.next_button.setEnabled(
                len(state.rows) == 250
                and not self._blocking
                and not self._embedded_operation_is_busy()
            )
            state.export_button.setEnabled(
                bool(state.rows)
                and not self._blocking
                and not self._embedded_operation_is_busy()
            )

        self._start_task(
            lambda progress: self.facade.browse_resources(
                search=search,
                kind=str(kind) if kind else None,
                offset=state.offset,
                limit=250,
                progress=progress,
            ),
            success,
            label="Loading a page of indexed assets",
            blocking=False,
        )

    def _page_universal_assets(self, direction: int) -> None:
        state = self._universal_browser
        if state is None or direction not in {-1, 1}:
            return
        state.offset = max(0, state.offset + direction * 250)
        self._query_universal_assets(reset=False)

    def _select_universal_asset(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        state = self._universal_browser
        if state is None or current is None:
            return
        asset_id = str(current.data(Qt.UserRole))
        record = next((row for row in state.rows if row.asset_id == asset_id), None)
        if record is None:
            return
        state.asset_id_label.setText(record.asset_id)
        state.detail_label.setText(
            f"FourCC: {record.kind}\n"
            f"Outer entry: {record.outer_index} ({record.outer_id}, {record.outer_head})\n"
            f"Chunk: {record.chunk_index}\n"
            f"Stored body: {record.stored_size:,} bytes\n"
            f"Exact raw export: {record.raw_size:,} bytes including its 0x20-byte wrapper\n\n"
            "Status: browsable and raw-exportable. Replacement remains disabled "
            "unless a named capability provides a bounded writer."
        )
        state.export_button.setEnabled(
            bool(getattr(self.facade, "source_ready", False))
            and not self._blocking
            and not self._embedded_operation_is_busy()
        )

    def _export_universal_asset(self) -> None:
        state = self._universal_browser
        if state is None:
            return
        current = state.asset_list.currentItem()
        if current is None:
            return
        asset_id = str(current.data(Qt.UserRole))
        record = next((row for row in state.rows if row.asset_id == asset_id), None)
        if record is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export exact raw game resource",
            str(Path.home() / record.suggested_filename),
            "Raw resource (*.bin);;All files (*)",
        )
        if not filename:
            return
        destination = Path(filename)

        def success(result: object) -> None:
            self._set_status(f"Exported {record.asset_id} to {Path(result).name}")

        self._start_task(
            lambda progress: self.facade.export_resource(
                record, destination, progress
            ),
            success,
            label=f"Exporting {record.kind} resource",
            blocking=True,
        )

    def _load_stadium_scenes(self, *, force: bool = False) -> None:
        state = self._stadium_browser
        if state is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        if not bool(getattr(self.facade, "stadium_available", False)):
            state.scene_metadata.setText(
                "Load your NFL 2K5 XISO before preparing private stadium assets."
            )
            return
        if state.scenes_loading or (state.scenes_loaded and not force):
            return
        state.scenes_loading = True
        state.scene_metadata.setText("Loading stadium scene catalog…")
        search = state.search.text().strip()

        def success(result: object) -> None:
            state.scenes = tuple(result)  # type: ignore[arg-type]
            state.scenes_loaded = True
            state.scenes_loading = False
            state.scene_list.blockSignals(True)
            state.scene_list.clear()
            for scene in state.scenes:
                item = QListWidgetItem(
                    f"Outer {scene.outer_index} / chunk {scene.chunk_index}"
                )
                item.setData(Qt.UserRole, scene.scene_id)
                item.setToolTip(
                    f"{scene.scene_id} • {scene.mesh_count} meshes • "
                    f"{scene.vertex_count:,} vertices"
                )
                item.setSizeHint(QSize(260, 44))
                state.scene_list.addItem(item)
            state.scene_list.blockSignals(False)
            state.count_label.setText(f"{len(state.scenes):,}")
            if state.scenes:
                state.scene_list.setCurrentRow(0)
            else:
                state.scene_label.setText("No matching stadium scenes")
                state.scene_metadata.setText("Try a broader outer/scene search.")
                state.viewport.set_model(None)

        self._start_task(
            lambda progress: self.facade.stadium_scenes(search, progress),
            success,
            label="Loading Stadium Studio",
            blocking=False,
        )

    def _select_stadium_scene(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        state = self._stadium_browser
        if state is None or current is None:
            return
        scene_id = str(current.data(Qt.UserRole))
        scene = next((row for row in state.scenes if row.scene_id == scene_id), None)
        if scene is None:
            return
        state.generation += 1
        generation = state.generation
        state.scene_label.setText(f"Outer {scene.outer_index} • Stadium scene")
        state.scene_metadata.setText("Preparing 3D geometry and surface ownership…")
        state.viewport.set_model(None)
        state.texture_list.clear()
        state.texture_preview.set_loading("Preparing texture ownership…")

        def operation(progress: ProgressSink) -> object:
            details = self.facade.stadium_details(scene, progress)
            progress("Building interactive stadium preview", 0, 1)
            model = GltfWireframeModel.load(
                details.scene.gltf_path, details.scene.bin_path
            )
            progress("Interactive stadium preview ready", 1, 1)
            return details, model

        def success(result: object) -> None:
            if generation != state.generation:
                return
            details, model = result  # type: ignore[misc]
            state.details = details
            state.viewport.set_model(model)
            state.scene_metadata.setText(
                f"{details.scene.mesh_count} meshes • "
                f"{details.scene.primitive_count} clickable surfaces • "
                f"{details.scene.vertex_count:,} vertices • "
                f"{len(details.textures)} owned textures"
            )
            state.texture_list.blockSignals(True)
            state.texture_list.clear()
            modified = set(getattr(self.facade, "modified_asset_ids", ()))
            textures = details.textures
            if self._stadium_people_filter.isChecked():
                people_ids = set(
                    self.facade.stadium_scene_people_texture_ids(
                        scene.scene_id
                    )
                )
                textures = tuple(
                    texture for texture in textures
                    if texture.texture_id in people_ids
                )
            for texture in textures:
                item = QListWidgetItem(
                    f"Texture {texture.texture_index} • {texture.width}×{texture.height} "
                    f"• {texture.access_status}"
                    + (" • Modified" if texture.texture_id in modified else "")
                )
                item.setData(Qt.UserRole, texture.texture_id)
                item.setToolTip(" / ".join(texture.mapped_material_names))
                state.texture_list.addItem(item)
            state.texture_list.blockSignals(False)
            if textures:
                state.texture_list.setCurrentRow(0)
            else:
                state.texture_preview.set_empty("No mapped embedded textures")
                state.texture_label.setText("This scene has no mapped texture occurrence")
            self._refresh_stadium_actions()

        self._start_task(
            operation,
            success,
            label="Opening the stadium in 3D",
            blocking=False,
        )

    def _stadium_texture(self, texture_id: str | None) -> StadiumTexture | None:
        state = self._stadium_browser
        if state is None or state.details is None or texture_id is None:
            return None
        return next(
            (row for row in state.details.textures if row.texture_id == texture_id),
            None,
        )

    def _select_stadium_surface(self, mesh_index: int, primitive_index: int) -> None:
        state = self._stadium_browser
        if state is None or state.details is None:
            return
        texture_id = None
        material_name = "Unresolved material"
        for material in state.details.materials:
            if any(
                owner.mesh_index == mesh_index
                and owner.primitive_index == primitive_index
                for owner in material.owners
            ):
                texture_id = material.texture_id
                material_name = material.name
                break
        if texture_id is None:
            state.texture_label.setText(
                f"Mesh {mesh_index} / surface {primitive_index} • {material_name}"
            )
            state.findings.setText(
                "This clicked surface has no resolved embedded-texture owner. "
                "The geometry remains inspectable; texture replacement is unavailable."
            )
            state.selected_texture_id = None
            self._refresh_stadium_actions()
            return
        for row in range(state.texture_list.count()):
            item = state.texture_list.item(row)
            if item.data(Qt.UserRole) == texture_id:
                state.texture_list.setCurrentItem(item)
                break

    def _select_stadium_texture(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        state = self._stadium_browser
        if state is None or current is None:
            return
        texture_id = str(current.data(Qt.UserRole))
        texture = self._stadium_texture(texture_id)
        if texture is None:
            return
        state.selected_texture_id = texture_id
        state.texture_label.setText(
            f"Texture {texture.texture_index} • {texture.format_name} • "
            f"{texture.width}×{texture.height}\n"
            + (" / ".join(texture.mapped_material_names) or "No material name")
        )
        state.findings.setText(texture.findings_note)
        self._refresh_stadium_actions()

        def success(result: object) -> None:
            if state.selected_texture_id == texture_id:
                state.texture_preview.set_png(Path(result))

        state.texture_preview.set_loading("Preparing embedded texture…")
        self._start_task(
            lambda progress: self.facade.preview_stadium_texture(
                texture_id, progress
            ),
            success,
            label="Preparing stadium texture",
            blocking=False,
            show_errors=False,
        )

    def _refresh_stadium_actions(self) -> None:
        state = self._stadium_browser
        if state is None:
            return
        texture = self._stadium_texture(state.selected_texture_id)
        ready = (
            bool(getattr(self.facade, "source_ready", False))
            and not self._blocking
            and not self._embedded_operation_is_busy()
        )
        state.export_button.setEnabled(ready and texture is not None)
        editable = texture is not None and texture.access_status == STADIUM_EDITABLE
        state.replace_button.setEnabled(ready and editable)
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        state.revert_button.setEnabled(
            ready and editable and texture.texture_id in modified  # type: ignore[union-attr]
        )
        current = state.texture_list.currentItem()
        if current is not None and texture is not None:
            current.setText(
                f"Texture {texture.texture_index} • {texture.width}×{texture.height} "
                f"• {texture.access_status}"
                + (" • Modified" if texture.texture_id in modified else "")
            )

    def _export_stadium_texture(self) -> None:
        state = self._stadium_browser
        if state is None:
            return
        texture = self._stadium_texture(state.selected_texture_id)
        if texture is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export stadium surface texture",
            str(Path.home() / f"stadium-texture-{texture.texture_index}.png"),
            "PNG image (*.png)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".png":
            destination = destination.with_suffix(".png")

        def success(result: object) -> None:
            self._set_status(f"Exported stadium texture to {Path(result).name}")

        self._start_task(
            lambda progress: self.facade.export_stadium_texture(
                texture.texture_id, destination, progress
            ),
            success,
            label="Exporting stadium texture",
            blocking=True,
        )

    def _choose_stadium_texture_replacement(self) -> None:
        state = self._stadium_browser
        if state is None:
            return
        texture = self._stadium_texture(state.selected_texture_id)
        if texture is None or texture.access_status != STADIUM_EDITABLE:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Replace stadium surface texture",
            str(Path.home()),
            "PNG image (*.png)",
        )
        if filename:
            self._replace_stadium_texture(texture, Path(filename))

    def _replace_stadium_texture_drop(self, supplied: object) -> None:
        state = self._stadium_browser
        if state is None:
            return
        texture = self._stadium_texture(state.selected_texture_id)
        if texture is None or texture.access_status != STADIUM_EDITABLE:
            self._show_error(
                "That stadium texture can be previewed and exported, but it cannot "
                "be replaced yet. Mod Studio can locate it, but cannot safely write "
                "that texture format back into the game."
            )
            return
        self._replace_stadium_texture(texture, Path(supplied))

    def _replace_stadium_texture(
        self, texture: StadiumTexture, supplied: Path
    ) -> None:
        state = self._stadium_browser
        assert state is not None

        def success(result: object) -> None:
            self._set_status(_result_message(result, "Stadium texture replaced."))
            self._mark_workspace_changed()
            self._select_stadium_texture(state.texture_list.currentItem(), None)

        self._start_task(
            lambda progress: self.facade.replace_stadium_texture(
                texture.texture_id, supplied, progress
            ),
            success,
            label="Replacing stadium texture",
            blocking=True,
        )

    def _revert_stadium_texture(self) -> None:
        state = self._stadium_browser
        if state is None:
            return
        texture = self._stadium_texture(state.selected_texture_id)
        if texture is None or texture.access_status != STADIUM_EDITABLE:
            return

        def success(result: object) -> None:
            self._set_status(_result_message(result, "Stadium texture reverted."))
            self._mark_workspace_changed()
            self._select_stadium_texture(state.texture_list.currentItem(), None)

        self._start_task(
            lambda progress: self.facade.revert_stadium_texture(
                texture.texture_id, progress
            ),
            success,
            label="Reverting stadium texture",
            blocking=True,
        )

    def _select_uniform_set(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        selector = current.data(Qt.UserRole)
        self._selected_set = self.uniform_catalog.get_uniform_set(str(selector))
        uniform_set = self._selected_set
        owner = " / ".join(uniform_set.team_names) or f"Asset {uniform_set.asset_code}"
        self.uniform_title.setText(owner)
        self.uniform_metadata.setText(
            f"{uniform_set.style_label} • {uniform_set.side_name.title()} • "
            f"set {uniform_set.selector} • 39 components"
        )
        self._refresh_team_kit_scope_labels()
        self._populate_components(uniform_set)

    def _selected_uniform_set_selectors(self) -> tuple[str, ...]:
        if not hasattr(self, "uniform_list"):
            return ()
        selectors = tuple(
            str(item.data(Qt.UserRole))
            for item in self.uniform_list.selectedItems()
            if item.data(Qt.UserRole)
        )
        if selectors:
            return selectors
        return (self._selected_set.selector,) if self._selected_set is not None else ()

    def _uniform_set_selection_changed(self) -> None:
        self._refresh_team_kit_scope_labels()
        self._refresh_action_states()

    def _refresh_team_kit_scope_labels(self) -> None:
        if not hasattr(self, "team_kit_scope"):
            return
        uniform_set = self._selected_set
        if uniform_set is None:
            labels = (
                "Selected physical set(s)",
                "HOME kit",
                "AWAY kit",
                "HOME + AWAY kit",
            )
        else:
            home = self.uniform_catalog.uniform_set_for(
                uniform_set.asset_code, "HOME", uniform_set.variant
            )
            away = self.uniform_catalog.uniform_set_for(
                uniform_set.asset_code, "AWAY", uniform_set.variant
            )
            explicit = self._selected_uniform_set_selectors()
            explicit_label = (
                f"Selected sets • {explicit[0]} + {len(explicit) - 1} more"
                if len(explicit) > 1 else
                f"Selected set • {explicit[0] if explicit else uniform_set.selector}"
            )
            labels = (
                explicit_label,
                f"HOME • {home.selector}",
                f"AWAY • {away.selector}",
                f"HOME + AWAY • {home.selector} + {away.selector}",
            )
        for index, label in enumerate(labels):
            self.team_kit_scope.setItemText(index, label)

    def _populate_components(self, uniform_set: UniformSet) -> None:
        assets = self.uniform_catalog.assets_for_set(uniform_set.selector)
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        self.component_tree.blockSignals(True)
        self.component_tree.clear()
        self._component_items.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        first: QTreeWidgetItem | None = None
        for asset in assets:
            parent = groups.get(asset.group)
            if parent is None:
                parent = QTreeWidgetItem((asset.group, "", ""))
                parent.setFirstColumnSpanned(True)
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                groups[asset.group] = parent
                self.component_tree.addTopLevelItem(parent)
            state = "● Modified" if asset.asset_id in modified else "Original"
            item = QTreeWidgetItem(
                parent, (asset.label, f"{asset.width}×{asset.height}", state)
            )
            item.setData(0, Qt.UserRole, asset.asset_id)
            if asset.asset_id in modified:
                item.setForeground(2, QColor("#ffbe5c"))
            self._component_items[asset.asset_id] = item
            first = first or item
        self.component_tree.expandAll()
        self.component_tree.blockSignals(False)
        if first is not None:
            self.component_tree.setCurrentItem(first)

    def _select_component(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None:
            return
        asset_id = current.data(0, Qt.UserRole)
        if not asset_id:
            return
        self._selected_asset = self.uniform_catalog.get_asset(str(asset_id))
        asset = self._selected_asset
        self.component_help.setText(
            f"{asset.label}: use an RGBA PNG exactly {asset.width} × {asset.height}. "
            "The app rejects the wrong dimensions before it can enter your project."
        )
        self._refresh_action_states()
        if bool(getattr(self.facade, "source_ready", False)):
            self._load_preview(asset)
        else:
            self.preview.set_empty(
                f"{asset.label}\n{asset.width} × {asset.height} RGBA PNG\n\n"
                "Load your XISO to see the original."
            )

    def _load_preview(self, asset: UniformAsset) -> None:
        self._preview_generation += 1
        generation = self._preview_generation
        self.preview.set_loading(f"Preparing {asset.label}…")

        def success(value: object) -> None:
            if generation != self._preview_generation:
                return
            path = Path(value)  # facade promises a path
            if not self.preview.set_png(path):
                self._set_status("Preview unavailable — the asset was not changed.")

        self._start_task(
            lambda progress: self.facade.preview_asset(asset, progress),
            success,
            label=f"Preparing {asset.label}",
            blocking=False,
            show_errors=False,
        )

    def _choose_source(self, _checked: bool = False) -> None:
        if self._refuse_while_audio_busy("open another XISO"):
            return
        state = self._workspace_state()
        recent_sources = tuple(getattr(state, "recent_sources", ()))
        initial = Path(recent_sources[0]).parent if recent_sources else Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open your NFL 2K5 Xbox XISO",
            str(initial),
            "Xbox XISO (*.iso *.xiso);;All files (*)",
        )
        if not filename:
            return
        self._request_source_switch(Path(filename))

    def _request_source_switch(
        self,
        source: Path,
        *,
        recovery: RecoveryCandidate | None = None,
    ) -> None:
        if self._refuse_while_audio_busy("open another XISO"):
            return
        self._continue_after_unsaved(
            "Opening another XISO",
            lambda discarded: self._load_source_path(
                source,
                recovery=recovery,
                clear_previous_recovery=discarded,
            ),
        )

    def _load_source_path(
        self,
        source: Path,
        *,
        recovery: RecoveryCandidate | None = None,
        clear_previous_recovery: bool = False,
    ) -> None:
        if self._refuse_while_audio_busy("open another XISO"):
            return
        if self._audio_panel is not None:
            self._audio_panel.invalidate_preview_for_source_change()

        def failed(_message: str) -> None:
            if self._audio_panel is not None:
                self._audio_panel.recover_after_source_change_failure()

        def success(result: object) -> None:
            display = str(getattr(self.facade, "source_display_name", "") or source.name)
            self.source_pill.setText(f"●  Ready • {display}")
            self.source_pill.setProperty("ready", True)
            self.source_pill.style().unpolish(self.source_pill)
            self.source_pill.style().polish(self.source_pill)
            active_path = getattr(self.facade, "source_path", None)
            self._active_source_path = (
                Path(active_path) if active_path is not None
                else source.resolve(strict=True)
            )
            self._active_source_sha256 = getattr(
                self.facade, "source_sha256", None
            )
            self._active_project_path = None
            self._active_project_identity = None
            self._workspace_dirty = False
            self._workspace_revision += 1
            if self.workspace_store is not None:
                try:
                    self.workspace_store.record_source(
                        self._active_source_path, self._active_source_sha256
                    )
                    if clear_previous_recovery and recovery is None:
                        self.workspace_store.clear_recovery()
                except Exception as exc:
                    self._set_status(
                        f"Game opened, but recent-file state could not update: "
                        f"{str(exc).strip()}"
                    )
            self._set_status(_result_message(result, "Game indexed — choose an asset to edit."))
            self._refresh_edit_state()

            def refresh_loaded_source() -> None:
                if self._audio_panel is not None:
                    self._audio_panel.reset_for_source()
                self._refresh_specialized_panels(
                    reset=True, include_crib=False
                )
                self._refresh_entered_page(
                    self.navigation.currentRow(), refresh_embedded=False
                )
                if self._selected_asset is not None:
                    self._preview_selected_asset()
                self._refresh_recent_menus()
                if self._crib_panel is not None:
                    self._crib_panel.refresh(keep_selection=False)

            if recovery is not None:
                if (
                    recovery.source_sha256 is not None
                    and self._active_source_sha256 != recovery.source_sha256
                ):
                    self._show_error(
                        "The selected XISO does not match the source identity bound "
                        "to this recovery project. The recovery file was kept."
                    )
                    self._defer_until_blocking_task_finished(
                        refresh_loaded_source
                    )
                    return
                self._defer_until_blocking_task_finished(
                    lambda: self._load_project_path(
                        recovery.project_path, recovery=True
                    )
                )
                return

            self._defer_until_blocking_task_finished(refresh_loaded_source)

        self._start_task(
            lambda progress: self.facade.load_source(source, progress),
            success,
            label="Opening your NFL 2K5 XISO",
            blocking=True,
            on_error=failed,
        )

    def _export_selected(self) -> None:
        asset = self._selected_asset
        if asset is None:
            return
        suggested = f"{asset.set_selector}-{asset.asset_id.rsplit('.', 1)[-1]}.png"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", str(Path.home() / suggested), "PNG image (*.png)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".png":
            destination = destination.with_suffix(".png")

        def success(result: object) -> None:
            path = Path(result)
            self._set_status(f"Exported {asset.label} to {path.name}")

        self._start_task(
            lambda progress: self.facade.export_asset(asset, destination, progress),
            success,
            label=f"Exporting {asset.label}",
            blocking=True,
        )

    def _team_kit_suggested_name(self, scope: str, container: str) -> str:
        uniform_set = self._selected_set
        if uniform_set is None:
            base = "NFL-2K5-Team-Kit"
        else:
            owner = (
                uniform_set.team_abbreviations[0]
                if uniform_set.team_abbreviations else uniform_set.asset_code
            )
            explicit = self._selected_uniform_set_selectors()
            selection = (
                (
                    explicit[0] if len(explicit) == 1 else f"{len(explicit)}-SETS"
                )
                if scope == "SELECTED" else scope.replace("BOTH", "HOME-AWAY")
            )
            base = f"{owner}-style-{uniform_set.variant}-{selection}-Team-Kit"
        return f"{base}.zip" if container == "zip" else base

    def _choose_team_kit_export(self) -> None:
        uniform_set = self._selected_set
        if uniform_set is None:
            self._show_error("Choose a physical uniform set before exporting a Team Kit.")
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before exporting a Team Kit.")
            return
        scope = str(self.team_kit_scope.currentData() or "BOTH")
        container = str(self.team_kit_container.currentData() or "folder")
        explicit_selectors = self._selected_uniform_set_selectors()
        answer = QMessageBox.warning(
            self,
            "Private working export",
            "A Team Kit export contains PNGs decoded from your own NFL 2K5 copy "
            "and may reproduce retail artwork. Keep it private. When your edit is "
            "ready to share, save a replacement-only .2k5mod project instead.",
            QMessageBox.Cancel | QMessageBox.Ok,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Ok:
            return
        suggested = self._team_kit_suggested_name(scope, container)
        title = (
            "Export a private Team Kit ZIP"
            if container == "zip" else
            "Create a private Team Kit editing folder"
        )
        file_filter = (
            "Team Kit ZIP (*.zip)" if container == "zip"
            else "Team Kit folder name (*)"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self, title, str(Path.home() / suggested), file_filter
        )
        if not filename:
            return
        destination = Path(filename)
        if container == "zip" and destination.suffix.casefold() != ".zip":
            destination = destination.with_suffix(".zip")

        def operation(progress: ProgressSink) -> object:
            if scope == "SELECTED":
                return self.facade.export_team_kit_sets(
                    explicit_selectors,
                    destination,
                    container=container,
                    progress=progress,
                )
            return self.facade.export_team_kit(
                asset_code=uniform_set.asset_code,
                variant=uniform_set.variant,
                sides=scope,
                destination=destination,
                container=container,
                progress=progress,
            )

        def success(result: object) -> None:
            output = Path(getattr(result, "path", destination))
            count = int(getattr(result, "asset_count", ASSETS_PER_SET))
            selectors = tuple(getattr(result, "set_selectors", (uniform_set.selector,)))
            self._set_status(_result_message(
                result,
                f"Exported {count} Team Kit components to {output.name}.",
            ))
            QMessageBox.information(
                self,
                "Private Team Kit exported",
                f"Exported {count} components for {', '.join(selectors)}:\n\n"
                f"{output}\n\n"
                "Keep this source-derived working bundle private. Share the "
                "replacement-only .2k5mod project after importing your edits.",
            )

        self._start_task(
            operation,
            success,
            label="Exporting the complete private Team Kit",
            blocking=True,
        )

    def _choose_team_kit_import(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before importing a Team Kit.")
            return
        container = str(self.team_kit_container.currentData() or "folder")
        if container == "zip":
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Import an edited Team Kit ZIP",
                str(Path.home()),
                "Team Kit ZIP (*.zip)",
            )
        else:
            filename = QFileDialog.getExistingDirectory(
                self,
                "Import an edited Team Kit folder",
                str(Path.home()),
            )
        if not filename:
            return
        source = Path(filename)

        def success(result: object) -> None:
            changed = int(getattr(result, "changed_count", 0))
            total = int(getattr(result, "asset_count", 0))
            selectors = tuple(getattr(result, "set_selectors", ()))
            self._set_status(_result_message(
                result,
                f"Imported {changed} changed Team Kit components.",
            ))
            if changed:
                self._mark_workspace_changed(rebuild_components=True)
                if self._selected_asset is not None:
                    self._preview_selected_asset()
            else:
                self._refresh_edit_state(rebuild_components=True)
            self.team_kit_imported.emit(changed)
            QMessageBox.information(
                self,
                "Team Kit import complete",
                (
                    f"Validated all {total} components for "
                    f"{', '.join(selectors) or 'the bundled physical set(s)'}.\n\n"
                    f"{changed} pixel-changed component"
                    f"{'s were' if changed != 1 else ' was'} staged together as "
                    "one Undo action.\n\nYour source XISO was not changed."
                    if changed else
                    f"Validated all {total} components. Their decoded pixels match "
                    "the export, so nothing was staged and no Undo action was added."
                ),
            )

        self._start_task(
            lambda progress: self.facade.import_team_kit(source, progress),
            success,
            label="Validating and importing the complete Team Kit",
            blocking=True,
        )

    def _save_project(
        self,
        _checked: bool = False,
        *,
        after_success: Callable[[], None] | None = None,
    ) -> None:
        """Save the named project directly, or ask for its first name."""

        if self._refuse_while_audio_busy("save the project"):
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
        if self._refuse_while_audio_busy("save the project"):
            return
        state = self._workspace_state()
        recent_projects = tuple(getattr(state, "recent_projects", ()))
        initial = (
            self._active_project_path
            if self._active_project_path is not None else
            Path(recent_projects[0]) if recent_projects
            else Path.home() / "My NFL 2K5 Mod.2k5mod"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save a shareable Mod Studio project",
            str(initial),
            "2K5 Mod Studio project (*.2k5mod)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".2k5mod":
            destination = destination.with_suffix(".2k5mod")

        self._save_project_path(destination, after_success=after_success)

    def _save_project_path(
        self,
        destination: Path,
        *,
        expected_target: ProjectTargetIdentity | None = None,
        after_success: Callable[[], None] | None = None,
    ) -> None:
        if self._refuse_while_audio_busy("save the project"):
            return
        was_dirty = self._workspace_dirty

        def success(result: object) -> None:
            identity = getattr(result, "project_identity", None)
            if not isinstance(identity, ProjectTargetIdentity):
                identity = project_target_identity(destination)
            self._active_project_path = identity.path
            self._active_project_identity = identity
            self._set_status(
                _result_message(result, f"Project saved — {destination.name}.")
            )
            self._workspace_dirty = False
            if self.workspace_store is not None:
                try:
                    self.workspace_store.record_project(destination)
                    if was_dirty:
                        self._clear_recovery_safely(only_for_active_source=True)
                except Exception as exc:
                    self._set_status(
                        f"Project saved, but recent-file state could not update: "
                        f"{str(exc).strip()}"
                    )
            self._refresh_recent_menus()
            self._refresh_edit_state()
            if after_success is not None:
                self._defer_until_blocking_task_finished(after_success)

        def operation(progress: ProgressSink) -> object:
            if expected_target is not None:
                return self.facade.save_project(
                    destination,
                    progress,
                    replace=True,
                    expected_target=expected_target,
                    allow_empty=True,
                )
            return self.facade.save_project(
                destination,
                progress,
                replace=destination.exists(),
                allow_empty=True,
            )

        self._start_task(
            operation,
            success,
            label="Saving a retail-free project",
            blocking=True,
        )

    def _choose_project(self, _checked: bool = False) -> None:
        if self._refuse_while_audio_busy("open another project"):
            return
        state = self._workspace_state()
        recent_projects = tuple(getattr(state, "recent_projects", ()))
        initial = Path(recent_projects[0]).parent if recent_projects else Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open a Mod Studio project",
            str(initial),
            "2K5 Mod Studio project (*.2k5mod)",
        )
        if not filename:
            return
        self._request_project_load(Path(filename))

    def _request_project_load(self, source: Path) -> None:
        if self._refuse_while_audio_busy("open another project"):
            return
        self._continue_after_unsaved(
            "Opening another project",
            lambda discarded: self._load_project_path(
                source, clear_previous_recovery=discarded
            ),
        )

    def _load_project_path(
        self,
        source: Path,
        *,
        recovery: bool = False,
        clear_previous_recovery: bool = False,
    ) -> None:
        if self._refuse_while_audio_busy("open another project"):
            return
        if self._audio_panel is not None:
            self._audio_panel.invalidate_audio_content()

        def success(result: object) -> None:
            if recovery:
                self._active_project_path = None
                self._active_project_identity = None
                self._set_status(
                    "Recovered the autosaved edits. Save Project when you want "
                    "a named, shareable copy."
                )
                # Even an empty recovery archive is meaningful: it records
                # that the user reverted every edit after the last named save.
                self._workspace_dirty = True
            else:
                identity = getattr(result, "project_identity", None)
                if not isinstance(identity, ProjectTargetIdentity):
                    identity = project_target_identity(source)
                self._active_project_path = identity.path
                self._active_project_identity = identity
                self._set_status(_result_message(result, "Project loaded."))
                self._workspace_dirty = False
                if self.workspace_store is not None:
                    try:
                        self.workspace_store.record_project(source)
                        if clear_previous_recovery:
                            self.workspace_store.clear_recovery()
                    except Exception as exc:
                        self._set_status(
                            f"Project loaded, but recent-file state could not update: "
                            f"{str(exc).strip()}"
                        )
            self._refresh_edit_state(rebuild_components=True)

            def refresh_loaded_project() -> None:
                if self._audio_panel is not None:
                    self._audio_panel.refresh()
                self._refresh_specialized_panels(
                    reset=False, include_crib=False
                )
                self._refresh_entered_page(
                    self.navigation.currentRow(), refresh_embedded=False
                )
                if self._selected_asset is not None:
                    self._preview_selected_asset()
                self._refresh_recent_menus()
                if self._crib_panel is not None:
                    self._crib_panel.refresh(keep_selection=True)

            self._defer_until_blocking_task_finished(refresh_loaded_project)

        self._start_task(
            lambda progress: self.facade.load_project(source, progress),
            success,
            label="Opening and validating the project",
            blocking=True,
        )

    def _choose_replacement(self) -> None:
        asset = self._selected_asset
        if asset is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"Replace {asset.label}",
            str(Path.home()),
            "PNG image (*.png)",
        )
        if filename:
            self._replace_asset(Path(filename))

    def _replace_from_drop(self, path: object) -> None:
        if self._selected_asset is None:
            self._show_error("Choose a component before dropping a PNG.")
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before replacing an asset.")
            return
        self._replace_asset(Path(path))

    def _replace_asset(self, path: Path) -> None:
        asset = self._selected_asset
        if asset is None:
            return

        def success(result: object) -> None:
            self._set_status(_result_message(result, f"{asset.label} is ready to build."))
            self._mark_workspace_changed(rebuild_components=True)
            self._load_preview(asset)

        self._start_task(
            lambda progress: self.facade.replace_asset(asset, path, progress),
            success,
            label=f"Checking and replacing {asset.label}",
            blocking=True,
        )

    def _revert_selected(self) -> None:
        if self._refuse_while_audio_busy("revert this asset"):
            return
        asset = self._selected_asset
        if asset is None:
            return

        def success(result: object) -> None:
            self._set_status(_result_message(result, f"Reverted {asset.label}."))
            self._mark_workspace_changed(rebuild_components=True)
            self._load_preview(asset)

        self._start_task(
            lambda progress: self.facade.revert_asset(asset, progress),
            success,
            label=f"Reverting {asset.label}",
            blocking=True,
        )

    def _undo(self) -> None:
        if self._refuse_while_audio_busy("undo the last edit"):
            return
        if self._audio_panel is not None:
            self._audio_panel.invalidate_audio_content()

        def success(result: object) -> None:
            self._set_status(_result_message(result, "Undid the last edit."))
            self._mark_workspace_changed(rebuild_components=True)
            self._defer_post_mutation_session_refresh()

        self._start_task(
            lambda progress: self.facade.undo(progress),
            success,
            label="Undoing the last edit",
            blocking=True,
        )

    def _revert_all(self) -> None:
        if self._refuse_while_audio_busy("revert every edit"):
            return
        count = int(getattr(self.facade, "modified_count", 0))
        metadata_count = int(getattr(self.facade, "project_metadata_count", 0))
        project_count = count + metadata_count
        if project_count <= 0:
            return
        scope = (
            f"{count} game edit{'s' if count != 1 else ''} and "
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''}"
            if count and metadata_count else
            f"{count} game edit{'s' if count != 1 else ''}"
            if count else
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''}"
        )
        answer = QMessageBox.question(
            self,
            "Revert every project change?",
            f"This removes {scope} from the current working session. "
            "Game originals remain untouched. You can undo this once.",
            QMessageBox.Cancel | QMessageBox.Yes,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        if self._audio_panel is not None:
            self._audio_panel.invalidate_audio_content()

        def success(result: object) -> None:
            self._set_status(
                _result_message(result, f"Reverted {project_count} project changes.")
            )
            self._mark_workspace_changed(rebuild_components=True)
            self._defer_post_mutation_session_refresh()

        self._start_task(
            lambda progress: self.facade.revert_all(progress),
            success,
            label="Reverting every edit",
            blocking=True,
        )

    def _defer_post_mutation_session_refresh(self) -> None:
        """Refresh mutation consumers only after the owning worker releases Qt."""

        def refresh_consumers() -> None:
            self._refresh_specialized_panels(
                reset=False, include_crib=False
            )
            self._refresh_entered_page(
                self.navigation.currentRow(), refresh_embedded=False
            )
            if self._selected_asset is not None:
                self._preview_selected_asset()
            if self._crib_panel is not None:
                self._crib_panel.refresh(keep_selection=True)

        self._defer_until_blocking_task_finished(refresh_consumers)

    def _choose_build_output(self) -> None:
        if self._refuse_while_audio_busy("build a modded XISO"):
            return
        preferred = Path.home() / "2K5 Mod Studio Builds"
        initial = (
            preferred / "NFL 2K5 Modded.xiso.iso"
            if preferred.is_dir()
            else Path.home() / "NFL 2K5 Modded.xiso.iso"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self, "Build a new modded XISO", str(initial), "Xbox XISO (*.iso)"
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".iso":
            destination = destination.with_suffix(".iso")

        def success(result: object) -> None:
            result_path = getattr(result, "output_xiso", getattr(result, "output", result))
            try:
                name = Path(result_path).name
            except TypeError:
                name = destination.name
            self._set_status(
                _result_message(result, f"Build complete — {name} is ready for xemu.")
            )
            QMessageBox.information(
                self,
                "Modded XISO ready",
                f"Your verified build is ready:\n\n{destination}\n\n"
                "Your source XISO was not changed.",
            )
            self._refresh_edit_state()

        self._start_task(
            lambda progress: self.facade.build_iso(destination, progress),
            success,
            label="Building a safe, separate modded XISO",
            blocking=True,
        )

    def _launch_xemu(self) -> None:
        if self._refuse_while_audio_busy("launch xemu"):
            return

        def success(result: object) -> None:
            self._set_status(
                _result_message(result, "xemu launched with your latest modded XISO.")
            )

        self._start_task(
            lambda progress: self.facade.launch_xemu(progress),
            success,
            label="Launching your latest build in xemu",
            blocking=True,
        )

    def _start_task(
        self,
        operation: Callable[[ProgressSink], object],
        on_success: Callable[[object], None],
        *,
        label: str,
        blocking: bool,
        show_errors: bool = True,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        if blocking and self._refuse_while_audio_busy(
            f"start {label.casefold()}"
        ):
            return
        if blocking and self._blocking:
            self._set_status("Finish the current operation before starting another.")
            return
        worker = _BackgroundTask(operation)
        self._workers.add(worker)
        if blocking:
            self._set_busy(True, label)
        worker.signals.result.connect(on_success)
        # Preview decoding also runs off-thread, but it must not take over the
        # global build/index progress strip or leave it visible after a quick
        # selection change. Blocking user operations own that progress UI.
        if blocking:
            worker.signals.progress.connect(self._task_progress)

        def error(message: str) -> None:
            if on_error is not None:
                on_error(message)
            self._set_status(f"Could not finish: {message}")
            if show_errors:
                self._show_error(message)
            elif self._selected_asset is not None:
                self.preview.set_empty("Preview unavailable. The asset was not changed.")

        worker.signals.error.connect(error)

        def finished() -> None:
            self._workers.discard(worker)
            if blocking:
                self._set_busy(False)
                self._drain_post_blocking_continuations()

        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def _task_progress(self, stage: str, completed: int, total: int) -> None:
        self.operation_status.setText(stage or "Working…")
        self.progress_bar.show()
        if total > 0:
            self.progress_bar.setRange(0, 1000)
            value = max(0, min(1000, int(completed * 1000 / total)))
            self.progress_bar.setValue(value)
        else:
            self.progress_bar.setRange(0, 0)

    def _set_busy(self, busy: bool, label: str = "") -> None:
        self._blocking = busy
        if busy:
            self.operation_status.setText(label)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
        else:
            self.progress_bar.hide()
            self.progress_bar.setRange(0, 100)
        self._refresh_action_states()

    def _set_status(self, message: str) -> None:
        self.operation_status.setText(message)

    def _specialized_panel_status(self, message: str) -> None:
        """Forward embedded-panel status once the shared footer exists."""

        if hasattr(self, "operation_status"):
            self._set_status(message)

    def _specialized_panel_refresh(self) -> None:
        """Refresh global edit badges after an embedded panel changes state."""

        if hasattr(self, "edit_count"):
            self._mark_workspace_changed()

    def _refresh_specialized_panels(
        self, *, reset: bool, include_crib: bool = True
    ) -> None:
        """Reload source-bound panels after a source or project session swap."""

        if not bool(getattr(self.facade, "source_ready", False)):
            return
        if self._text_roster_panel is not None:
            self._text_roster_panel.reload()
        if self._roster_panel is not None:
            self._roster_panel.reload()
        if include_crib and self._crib_panel is not None:
            self._crib_panel.refresh(keep_selection=not reset)
        if reset and self._playbooks_panel is not None:
            self._playbooks_panel.reset_for_source()

    def _mark_workspace_changed(self, *, rebuild_components: bool = False) -> None:
        """Mark an authored change and immediately queue a safe autosave."""

        self._workspace_revision += 1
        # Dirty means "different from the last named project save/load", not
        # "contains at least one replacement". Reverting the final edit is a
        # real document change that must remain saveable and recoverable.
        self._workspace_dirty = True
        self._refresh_edit_state(rebuild_components=rebuild_components)
        self._save_recovery_snapshot()

    def _save_recovery_snapshot(self) -> None:
        store = self.workspace_store
        if store is None or not self._workspace_dirty:
            return
        embedded_owners = self._embedded_operation_owners()
        if embedded_owners:
            self._recovery_save_pending = True
            owner = " and ".join(embedded_owners)
            self._set_status(
                f"Edits are staged safely • autosave will run when {owner} finishes."
            )
            return
        source_path = self._active_source_path or getattr(
            self.facade, "source_path", None
        )
        source_sha256 = self._active_source_sha256 or getattr(
            self.facade, "source_sha256", None
        )
        if source_path is None:
            self._set_status(
                "Edits are staged safely, but autosave needs the active source path."
            )
            return
        if self._recovery_save_in_flight:
            self._recovery_save_pending = True
            return
        self._recovery_save_in_flight = True
        self._recovery_save_pending = False
        revision = self._workspace_revision
        recovery_path = store.recovery_path

        def operation(progress: ProgressSink) -> object:
            bounded = getattr(self.facade, "save_recovery_project", None)
            if callable(bounded) and isinstance(source_sha256, str):
                return bounded(
                    recovery_path, source_sha256, progress
                )
            return self.facade.save_project(
                recovery_path, progress, replace=True
            )

        worker = _BackgroundTask(operation)
        self._workers.add(worker)

        def success(_result: object) -> None:
            if not self._workspace_dirty:
                self._clear_recovery_safely(only_for_active_source=True)
                return
            current_sha256 = getattr(self.facade, "source_sha256", None)
            if (
                isinstance(source_sha256, str)
                and current_sha256 != source_sha256
            ):
                # A completed snapshot remains a valid archive for its old
                # source, but it must not become the advertised recovery for a
                # newly loaded game. A pending save will publish the new set.
                return
            try:
                store.register_recovery(
                    source_path=Path(source_path),
                    source_sha256=(
                        source_sha256 if isinstance(source_sha256, str) else None
                    ),
                    project_path=recovery_path,
                )
            except Exception as exc:
                self._set_status(
                    f"Edits are staged, but recovery metadata could not update: "
                    f"{str(exc).strip()}"
                )
            else:
                if revision == self._workspace_revision:
                    self._set_status(
                        "Autosaved unsaved edits • source XISO remains read-only"
                    )
                self._refresh_recent_menus()

        def error(message: str) -> None:
            # The live session still owns the user-authored files. Avoid a
            # modal interruption, but make the reduced crash protection clear.
            self._set_status(
                f"Edits are staged, but autosave could not update: {message}"
            )

        def finished() -> None:
            self._workers.discard(worker)
            self._recovery_save_in_flight = False
            if self._close_when_recovery_finishes:
                self._close_when_recovery_finishes = False
                self._recovery_save_pending = False
                self._clear_recovery_safely(only_for_active_source=True)
                self._allow_close = True
                QTimer.singleShot(0, self.close)
                return
            pending = self._recovery_save_pending
            self._recovery_save_pending = False
            if pending and self._workspace_dirty:
                QTimer.singleShot(0, self._save_recovery_snapshot)

        worker.signals.result.connect(success)
        worker.signals.error.connect(error)
        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def _clear_recovery_safely(
        self, *, only_for_active_source: bool = False
    ) -> None:
        if self.workspace_store is None:
            return
        try:
            if only_for_active_source:
                candidate = self.workspace_store.recovery_candidate(
                    require_source=False
                )
                if candidate is not None:
                    active_sha = self._active_source_sha256 or getattr(
                        self.facade, "source_sha256", None
                    )
                    active_path = self._active_source_path or getattr(
                        self.facade, "source_path", None
                    )
                    if candidate.source_sha256 is not None:
                        if candidate.source_sha256 != active_sha:
                            return
                    elif active_path is None or (
                        candidate.source_path != Path(active_path)
                    ):
                        return
            self.workspace_store.clear_recovery()
        except Exception as exc:
            self._set_status(
                f"Recovery state could not be cleared: {str(exc).strip()}"
            )
        self._refresh_recent_menus()

    def _finish_close_after_save(self) -> None:
        if self._recovery_save_in_flight:
            self._close_when_recovery_finishes = True
            self._set_status("Project saved • finishing private recovery cleanup…")
            return
        self._allow_close = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._refuse_while_embedded_busy("close Mod Studio"):
            event.ignore()
            return
        if self._allow_close:
            event.accept()
            return
        if self._blocking:
            QMessageBox.information(
                self,
                "Finish the current operation",
                "Wait for the current index, save, or build operation to finish "
                "before closing Mod Studio.",
            )
            event.ignore()
            return
        if not self._workspace_dirty:
            event.accept()
            return
        decision = self._prompt_unsaved_decision("Closing Mod Studio")
        if decision == "discard":
            self._workspace_dirty = False
            self._workspace_revision += 1
            if self._recovery_save_in_flight:
                self._close_when_recovery_finishes = True
                self._recovery_save_pending = False
                self._set_status("Discarding the private recovery snapshot…")
                event.ignore()
            else:
                self._clear_recovery_safely(only_for_active_source=True)
                self._allow_close = True
                event.accept()
        elif decision == "save":
            event.ignore()
            self._save_project(after_success=self._finish_close_after_save)
        else:
            event.ignore()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "2K5 Mod Studio could not finish that",
            message + "\n\nNothing was changed in your source XISO.",
        )

    def _refresh_project_document_state(self) -> None:
        """Render project identity without adding another crowded header row."""

        if self._active_project_path is not None:
            marker = "*" if self._workspace_dirty else ""
            self.setWindowTitle(
                f"{self._active_project_path.name}{marker} — 2K5 Mod Studio"
            )
            save_target = self._active_project_path.name
            save_tip = (
                f"Save current changes directly to {save_target}. The project "
                "contains user replacements and metadata only."
            )
        elif self._workspace_dirty:
            self.setWindowTitle("Untitled* — 2K5 Mod Studio")
            save_tip = (
                "Name this replacement-only edit set as a shareable .2k5mod project."
            )
        else:
            self.setWindowTitle("2K5 Mod Studio")
            save_tip = (
                "Save only your replacement files and metadata — never retail game data."
            )
        self.save_project_button.setToolTip(save_tip)
        if self._save_project_action is not None:
            self._save_project_action.setToolTip(save_tip)

    def _refresh_edit_state(self, *, rebuild_components: bool = False) -> None:
        count = int(getattr(self.facade, "modified_count", 0))
        metadata_count = int(getattr(self.facade, "project_metadata_count", 0))
        self.edit_count.setText(
            f"{count} build edit{'s' if count != 1 else ''} • "
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''}"
            if count and metadata_count else
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''} • "
            "no build edits"
            if metadata_count else
            "No edits • unsaved"
            if count == 0 and self._workspace_dirty else
            "No pending edits" if count == 0
            else f"{count} pending edit{'s' if count != 1 else ''}"
        )
        ready = bool(getattr(self.facade, "source_ready", False))
        if ready:
            display = str(getattr(self.facade, "source_display_name", "NFL 2K5"))
            self.source_pill.setText(f"●  Ready • {display}")
            self.source_pill.setProperty("ready", True)
            self.source_pill.style().unpolish(self.source_pill)
            self.source_pill.style().polish(self.source_pill)
        if rebuild_components and self._selected_set is not None \
                and not isinstance(self._selected_asset, ExtendedVisualAsset):
            selected_id = self._selected_asset.asset_id if self._selected_asset else None
            self._populate_components(self._selected_set)
            if selected_id and selected_id in self._component_items:
                self.component_tree.setCurrentItem(self._component_items[selected_id])
            self._filter_uniforms()
        self._refresh_project_document_state()
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        ready = bool(getattr(self.facade, "source_ready", False))
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        count = int(getattr(self.facade, "modified_count", 0))
        metadata_count = int(getattr(self.facade, "project_metadata_count", 0))
        selected = self._selected_asset is not None
        global_busy = self._blocking or self._embedded_operation_is_busy()
        enabled = ready and selected and not global_busy
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(enabled)
            self.replace_button.setEnabled(enabled)
            self.revert_button.setEnabled(
                enabled and self._selected_asset.asset_id in modified  # type: ignore[union-attr]
            )
        if hasattr(self, "export_team_kit_button"):
            self.export_team_kit_button.setEnabled(
                ready and self._selected_set is not None and not global_busy
            )
            self.import_team_kit_button.setEnabled(ready and not global_busy)
            self.team_kit_scope.setEnabled(
                self._selected_set is not None and not global_busy
            )
            self.team_kit_container.setEnabled(not global_busy)
        self.open_source_button.setEnabled(not global_busy)
        self.open_project_button.setEnabled(ready and not global_busy)
        if self._open_source_action is not None:
            self._open_source_action.setEnabled(not global_busy)
        if self._open_project_action is not None:
            self._open_project_action.setEnabled(ready and not global_busy)
        if self._ps2_save_action is not None:
            # PS2 saves are independent of the Xbox source, so this needs no
            # loaded image -- only the guard against a running operation.
            self._ps2_save_action.setEnabled(not global_busy)
        if self._recent_source_menu is not None:
            self._recent_source_menu.setEnabled(not global_busy)
        if self._recent_project_menu is not None:
            self._recent_project_menu.setEnabled(ready and not global_busy)
        can_save = ready and self._workspace_dirty and not global_busy
        self.save_project_button.setEnabled(can_save)
        if self._save_project_action is not None:
            self._save_project_action.setEnabled(can_save)
        if self._save_project_as_action is not None:
            self._save_project_as_action.setEnabled(
                ready and self._workspace_dirty and not global_busy
            )
        self.undo_button.setEnabled(
            ready
            and bool(getattr(self.facade, "can_undo", False))
            and not global_busy
        )
        self.revert_all_button.setEnabled(
            ready and count + metadata_count > 0 and not global_busy
        )
        self.build_button.setEnabled(ready and count > 0 and not global_busy)
        can_launch = bool(getattr(self.facade, "can_launch_xemu", False))
        self.launch_button.setEnabled(can_launch and not global_busy)
        self.launch_button.setToolTip(
            "Launch the latest completed build in xemu."
            if can_launch
            else "Build a modded XISO and configure xemu to enable one-click launch."
        )
        self.navigation.setEnabled(not global_busy)
        audio_busy = self._embedded_audio_busy
        crib_busy = self._embedded_crib_busy
        for page in self._category_pages.values():
            owns_audio = page is self._audio_panel
            owns_crib = page is self._crib_panel
            page.setEnabled(
                not self._blocking
                and (
                    not (audio_busy or crib_busy)
                    or (audio_busy and not crib_busy and owns_audio)
                    or (crib_busy and not audio_busy and owns_crib)
                )
            )
        self.welcome_page.setEnabled(not global_busy)
        if self._audio_panel is not None:
            self._audio_panel.setEnabled(not self._blocking and not crib_busy)
        if self._crib_panel is not None:
            self._crib_panel.setEnabled(not self._blocking and not audio_busy)
        for state in self._visual_browsers.values():
            self._refresh_visual_action_states(state)
        self._refresh_stadium_actions()
        universal = self._universal_browser
        if universal is not None:
            universal.previous_button.setEnabled(
                ready and universal.offset > 0 and not global_busy
            )
            universal.next_button.setEnabled(
                ready and len(universal.rows) == 250 and not global_busy
            )
            universal.export_button.setEnabled(
                ready and universal.asset_list.currentItem() is not None
                and not global_busy
            )

    def _refresh_entered_page(
        self, row: int, *, refresh_embedded: bool = True
    ) -> None:
        if row <= 0:
            return
        category = PRODUCT_CATEGORY_ORDER[row - 1]
        if category in self._visual_browsers:
            self._filter_visual_assets(category)
            if category == ProductCategory.ROSTERS_PLAYERS \
                    and self._roster_panel is not None:
                if refresh_embedded and bool(
                    getattr(self.facade, "source_ready", False)
                ):
                    self._roster_panel.reload()
        elif category == ProductCategory.STADIUMS:
            self._load_stadium_scenes()
        elif category == ProductCategory.MENUS_UI:
            self._ensure_universal_browser()
        elif category == ProductCategory.TEAM_IDENTITY \
                and self._text_roster_panel is not None:
            if refresh_embedded and bool(getattr(self.facade, "source_ready", False)):
                self._text_roster_panel.reload()
        elif category == ProductCategory.CRIB and self._crib_panel is not None:
            if refresh_embedded and bool(getattr(self.facade, "source_ready", False)):
                self._crib_panel.refresh()
        elif category == ProductCategory.AUDIO and self._audio_panel is not None:
            if refresh_embedded and bool(
                getattr(self.facade, "source_ready", False)
            ):
                self._audio_panel.refresh()
        elif category == ProductCategory.PLAYBOOKS_PLAYS \
                and self._playbooks_panel is not None:
            if bool(getattr(self.facade, "source_ready", False)):
                self._playbooks_panel.refresh()

    def _update_header_title(self, row: int) -> None:
        if row <= 0:
            self.page_title.setText("Getting Started")
            return
        category = PRODUCT_CATEGORY_ORDER[row - 1]
        self.page_title.setText(
            category_display_title(self.product_catalog, category)
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow#studioWindow, QWidget {
                background: #0c1220;
                color: #edf3fc;
            }
            /*
             * The blanket QWidget rule above paints an opaque dark background on
             * every QLabel, which shows as a dark rectangle whenever a label sits
             * on a lighter card or frame.  Reset labels to transparent so they
             * inherit whatever surface they are placed on.  Labels that
             * intentionally carry their own background (brandMark, safetyCard,
             * sourcePill, countPill, editCount, findingsBanner, findingsNote and
             * the _StatusPill class) declare it through a higher-specificity ID
             * selector or their own stylesheet, so this reset never reaches them.
             */
            QLabel {
                background: transparent;
            }
            QWidget {
                font-family: Noto Sans, DejaVu Sans;
                font-size: 13px;
            }
            QFrame#sidebar {
                background: #101827;
                border-right: 1px solid #253249;
            }
            QLabel#brandMark {
                background: #32d5c6;
                color: #07131b;
                border-radius: 9px;
                font-size: 19px;
                font-weight: 900;
                padding: 7px 9px;
            }
            QLabel#brandTitle {
                color: #f8fbff;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#mutedLabel {
                color: #8e9db2;
                font-size: 12px;
            }
            QListWidget#navigation {
                background: transparent;
                border: 2px solid transparent;
                border-radius: 9px;
                outline: none;
            }
            QListWidget#navigation::item {
                color: #aab7c9;
                border-radius: 7px;
                padding: 7px 6px;
            }
            QListWidget#navigation:focus { border-color: #32d5c6; }
            QListWidget#navigation::item:hover {
                background: #17243a;
                color: #f5f8fd;
            }
            QListWidget#navigation::item:selected {
                background: #20344d;
                color: #65e4d8;
                border-left: 3px solid #32d5c6;
                font-weight: 700;
            }
            QLabel#safetyCard {
                background: #121f31;
                border: 1px solid #28394f;
                border-radius: 8px;
                color: #9aabc0;
                padding: 10px;
                font-size: 11px;
            }
            QFrame#header {
                background: #101827;
                border-bottom: 1px solid #253249;
            }
            QLabel#eyebrow {
                color: #65e4d8;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#pageTitle {
                color: #ffffff;
                font-size: 20px;
                font-weight: 800;
            }
            QLabel#sourcePill {
                background: #182337;
                color: #9aa8bc;
                border: 1px solid #2c3b53;
                border-radius: 9px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLabel#sourcePill[ready="true"] {
                background: #122d2a;
                color: #55dea2;
                border-color: #277557;
            }
            QLabel#heroTitle {
                color: #ffffff;
                font-size: 36px;
                font-weight: 800;
            }
            QLabel#heroTitleSmall {
                color: #ffffff;
                font-size: 28px;
                font-weight: 800;
            }
            QLabel#heroSubtitle {
                color: #a3b0c2;
                font-size: 14px;
            }
            QFrame#stepCard, QFrame#capabilityCard, QFrame#panel {
                background: #131d2d;
                border: 1px solid #29374d;
                border-radius: 10px;
            }
            QFrame#stepCard:hover, QFrame#capabilityCard:hover {
                border-color: #3c526e;
            }
            QLabel#stepNumber {
                color: #48dacc;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#cardTitle, QLabel#panelTitle {
                color: #f7faff;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#cardBody {
                color: #a2afc1;
                font-size: 12px;
            }
            QFrame#callout {
                background: #14283b;
                border: 1px solid #2e586c;
                border-radius: 10px;
            }
            QFrame#teamKitBar {
                background: #10273a;
                border: 1px solid #28566a;
                border-radius: 8px;
            }
            QLabel#teamKitWarning {
                color: #f0c879;
                font-size: 11px;
            }
            QPushButton {
                background: #1a2940;
                color: #dce6f3;
                border: 1px solid #354764;
                border-radius: 7px;
                min-height: 34px;
                padding: 0 13px;
                font-weight: 700;
            }
            QPushButton:hover:!disabled {
                background: #243650;
                border-color: #4b6282;
                color: #ffffff;
            }
            QPushButton:pressed:!disabled {
                background: #18263b;
            }
            QPushButton:focus {
                border: 2px solid #8ff2e9;
            }
            QPushButton#primaryButton {
                background: #32d5c6;
                color: #06151b;
                border-color: #32d5c6;
            }
            QPushButton#primaryButton:hover:!disabled {
                background: #61e5da;
                border-color: #61e5da;
            }
            QPushButton#openSourceButton {
                background: #193b3e;
                color: #75e7dc;
                border-color: #2c7773;
            }
            QPushButton#openSourceButton:hover:!disabled {
                background: #215053;
                border-color: #48a29a;
            }
            QPushButton#dangerQuietButton {
                background: transparent;
                color: #f0a0a6;
                border-color: #5a3a44;
            }
            QPushButton#dangerQuietButton:hover:!disabled {
                background: #34212b;
                border-color: #794853;
            }
            QPushButton#buildButton {
                background: #4778f4;
                color: #ffffff;
                border-color: #4778f4;
                min-height: 40px;
                padding: 0 20px;
                font-size: 14px;
            }
            QPushButton#buildButton:hover:!disabled {
                background: #5d89f8;
                border-color: #5d89f8;
            }
            QPushButton#launchButton {
                background: #172338;
                color: #cbd6e5;
                border-color: #3a4c68;
                min-height: 40px;
                padding: 0 17px;
            }
            QPushButton#launchButton:hover:!disabled {
                background: #1b343e;
                color: #71e3d7;
                border-color: #318079;
            }
            QPushButton:disabled,
            QPushButton#primaryButton:disabled,
            QPushButton#openSourceButton:disabled,
            QPushButton#dangerQuietButton:disabled,
            QPushButton#buildButton:disabled,
            QPushButton#launchButton:disabled {
                background: #141d2a;
                color: #647187;
                border: 1px solid #232f41;
            }
            QLineEdit, QComboBox {
                background: #0d1624;
                color: #e5ecf6;
                border: 1px solid #2c3c55;
                border-radius: 7px;
                min-height: 34px;
                padding: 0 10px;
                selection-background-color: #2b5165;
            }
            QLineEdit:hover, QComboBox:hover {
                border-color: #3d506e;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #4cded0;
            }
            QLineEdit:disabled, QComboBox:disabled {
                background: #121a27;
                color: #66748a;
                border-color: #222e40;
            }
            QComboBox QAbstractItemView {
                background: #162136;
                color: #e4ebf6;
                selection-background-color: #29445f;
                border: 1px solid #34455f;
                padding: 4px;
            }
            QListWidget#assetList {
                background: #0d1624;
                border: 1px solid #28374e;
                border-radius: 8px;
                outline: none;
            }
            QListWidget#assetList::item {
                color: #cbd6e5;
                border-radius: 6px;
                padding: 7px 9px;
            }
            QListWidget#assetList::item:hover {
                background: #17263c;
            }
            QListWidget#assetList::item:selected {
                background: #223e59;
                color: #ffffff;
                border: 1px solid #426989;
            }
            QListWidget#assetList:disabled {
                color: #68758a;
                background: #111925;
                border-color: #222e40;
            }
            QListWidget#assetList:focus, QTreeWidget#componentTree:focus {
                border: 2px solid #32d5c6;
            }
            QLabel#countPill, QLabel#editCount {
                color: #b2bfd0;
                background: #1b2940;
                border: 1px solid #2a3a52;
                border-radius: 8px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QTreeWidget#componentTree {
                background: #0d1624;
                alternate-background-color: #111b2b;
                border: 1px solid #28374e;
                border-radius: 8px;
                color: #ccd7e7;
                outline: none;
            }
            QTreeWidget#componentTree::item {
                min-height: 27px;
                padding: 2px;
            }
            QTreeWidget#componentTree::item:hover {
                background: #18283d;
            }
            QTreeWidget#componentTree::item:selected {
                background: #24445f;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #19263a;
                color: #9aa9bd;
                border: none;
                border-bottom: 1px solid #2a3a51;
                padding: 6px;
                font-size: 11px;
                font-weight: 700;
            }
            QFrame#pngPreview {
                background: #09111d;
                border: 1px dashed #3b526f;
                border-radius: 9px;
            }
            QFrame#pngPreview:hover {
                border-color: #4cded0;
            }
            QLabel#previewImage {
                color: #79889e;
                font-size: 13px;
            }
            QLabel#findingsBanner {
                background: #17263b;
                border-left: 3px solid #69a7ff;
                border-radius: 5px;
                color: #bfccdc;
                padding: 10px 12px;
            }
            QLabel#findingsNote {
                color: #a8b5c7;
                background: #0f1827;
                border-radius: 6px;
                padding: 8px 10px;
            }
            QLabel#codeLabel {
                color: #7d8da5;
                font-family: DejaVu Sans Mono;
                font-size: 10px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QFrame#footer {
                background: #101827;
                border-top: 1px solid #253249;
            }
            QLabel#operationStatus {
                color: #b8c4d4;
                font-size: 12px;
            }
            QProgressBar {
                background: #202c40;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #32d5c6;
                border-radius: 2px;
            }
            QScrollBar:vertical {
                background: #101827;
                width: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #35465f;
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #465c79;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: #101827;
                height: 10px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal {
                background: #35465f;
                min-width: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #465c79;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }
            QToolTip {
                background: #192438;
                color: #edf3fc;
                border: 1px solid #3b4d68;
                padding: 6px;
            }
            """
        )


def launch_studio(
    facade: StudioFacade | None = None,
    *,
    product_catalog: ProductCatalog | None = None,
    uniform_catalog: Nfl2k5UniformCatalog | None = None,
    extended_visual_catalog: Nfl2k5ExtendedVisualCatalog | None = None,
) -> int:
    """Launch 2K5 Mod Studio and return Qt's process exit code."""

    app = QApplication.instance()
    if app is None:
        # These attributes must be selected before Qt creates a GUI
        # application. Embedded callers may already have made that choice.
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QApplication([])
    app.setApplicationName("2K5 Mod Studio")
    app.setOrganizationName("2K5 Mod Studio")
    window = StudioMainWindow(
        facade,
        product_catalog=product_catalog,
        uniform_catalog=uniform_catalog,
        extended_visual_catalog=extended_visual_catalog,
        workspace_store=WorkspaceStateStore(),
        offer_recovery=True,
    )
    window.show()
    # Keep a Python reference when embedded in an existing QApplication.
    setattr(app, "_2k5_mod_studio_window", window)
    return app.exec_()


__all__ = [
    "BrowseOnlyFacade",
    "EMBEDDED_AUDIO_TASK_CONTRACT",
    "EMBEDDED_OPERATION_TASK_CONTRACT",
    "ProgressSink",
    "StudioFacade",
    "StudioMainWindow",
    "UniformFilter",
    "capability_findings",
    "category_display_title",
    "filter_uniform_sets",
    "launch_studio",
    "sidebar_category_titles",
    "specialized_panel_for_category",
    "uniform_search_text",
]
