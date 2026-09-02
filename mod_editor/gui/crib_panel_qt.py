"""Self-contained PyQt5 panel for NFL 2K5's Crib assets.

The panel deliberately knows nothing about the main window, project session,
or XISO builder.  :class:`CribPanelHost` is the complete integration boundary:
the root facade supplies metadata and callbacks, while this module owns
search, editable-first ordering, edit gating, PNG presentation, and progress/error
UI.

All 498 cataloged textures expose Replace/Revert through exact fixed-allocation
routes. Seven proved electronics scenes additionally expose bounded glTF model
position editing for ten meshes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable, Iterable, Protocol, runtime_checkable
from uuid import uuid4

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_crib import CribAsset, CribAssetStatus


ProgressSink = Callable[[str, int, int], None]
VALID_STATUS_FILTERS = (None, "editable", "modified")


CRIB_FINDINGS_PLAIN_TEXT = """\
All 498 Crib textures are editable now
The catalog contains 242 raw Team Item P8 textures (including all 128 Team
Photos), 68 standalone VC-LZ P8 textures, and 188 material/submesh-owned P8
surfaces across 36 SCNEs. Mod Studio regenerates every declared mip chain,
preserves special layouts such as reflection's source gap and ticker_src's
linear row order, and keeps each replacement inside its original allocation.
Edits sharing one SCNE are composed before that scene is recompressed once.

Safe compression boundary
Every replacement stays inside the original fixed pixel/palette and compressed
SCNE allocations. Extremely flat or heavily noisy/dithered art may be refused
with an actionable message. Textures can reskin an object but cannot change its
silhouette or add geometry.

Position-only model editing is available for 10 electronics meshes
Export any of the seven proved scenes to glTF, move existing vertices in
Blender, and import the edited glTF. Mod Studio requires exactly the original
vertex count and triangle topology, preserves UVs/materials/collision/indices
and every other vertex register, then proves the rebuilt scene still fits its
fixed allocation before staging it.

Arbitrary model swapping is not supported
Adding/removing faces, subdivision, welding, decimation, changing materials or
UVs, and replacing helmet/object topology are intentionally refused. Those
changes need a broader serializer and relocation contract than safe same-count
deformation.
"""


CRIB_FINDINGS_HTML = """
<h2>What can I change?</h2>
<h3 style="color:#62e6ad">All 498 Crib textures are editable now</h3>
<p>The catalog contains <b>242 raw Team Item P8 textures</b> (including all 128
Team Photos), <b>68 standalone VC-LZ P8 textures</b>, and <b>188 exact
material/submesh-owned P8 surfaces across 36 scenes</b>. Every declared mip is
regenerated. Special source layouts such as the reflection gap and ticker_src's
linear row order are preserved, and edits sharing a scene are composed before
that SCNE is recompressed once. Art outside the safe compression envelope is
refused clearly. A texture can reskin an object but cannot add geometry.</p>
<h3 style="color:#62e6ad">Bounded model editing is available now</h3>
<p>Crib SCNE resources couple nodes, shapes, submeshes, materials, pointers,
bounds, markers, and draw commands inside compressed fixed allocations. The
seven proved electronics scenes now support glTF export and same-count,
same-topology <b>position-only</b> import for ten exact meshes. Mod Studio keeps
UVs, materials, collision, indices, normals and all other registers as original
game bytes, and preflights the exact fixed compressed allocation before an edit
can be staged.</p>
<h3 style="color:#ffca80">Arbitrary model swapping — not supported</h3>
<p>Adding/removing faces, subdivision, welding, decimation, material/UV edits,
and general object replacement are refused until a broader serializer and
relocation contract is proved.</p>
"""


@dataclass(frozen=True, slots=True)
class CribBrowserResult:
    """Filtered, deterministically ordered metadata for one panel refresh."""

    assets: tuple[CribAsset, ...]
    catalog_total: int
    editable_total: int
    export_only_total: int

    @property
    def match_total(self) -> int:
        return len(self.assets)


@dataclass(frozen=True, slots=True)
class CribActionState:
    """Headless action gating shared by the widget and its tests."""

    can_preview: bool
    can_export: bool
    can_replace: bool
    can_revert: bool
    can_drop_png: bool


def crib_search_text(asset: CribAsset) -> str:
    """Return every product-facing metadata field searched by the browser."""

    return " ".join(
        (
            asset.asset_id,
            asset.selector,
            asset.label,
            asset.group,
            asset.status.value,
            asset.storage.value,
            asset.format_name,
            asset.scene_name or "",
            asset.asset_code or "",
            str(asset.variant) if asset.variant is not None else "",
            f"{asset.width}x{asset.height}",
            f"{asset.width}×{asset.height}",
            *asset.material_names,
        )
    ).replace("_", " ").casefold()


def _photo_sort(asset: CribAsset) -> tuple[int, int, int, str, str]:
    code = int(asset.asset_code) if asset.asset_code and asset.asset_code.isdigit() else 999
    variant = asset.variant if asset.variant is not None else 999
    return (
        0 if asset.editable else 1,
        code,
        variant,
        asset.group.casefold(),
        asset.label.casefold(),
    )


def crib_group_options(assets: Iterable[CribAsset]) -> tuple[str, ...]:
    """Return stable group choices with Team Photos deliberately first."""

    groups = set(asset.group for asset in assets)
    return tuple(sorted(groups, key=lambda value: (value != "Team Photos", value.casefold())))


def filter_crib_assets(
    assets: Iterable[CribAsset],
    *,
    search: str = "",
    status: str | None = None,
    group: str | None = None,
    modified_asset_ids: Iterable[str] = (),
) -> CribBrowserResult:
    """Filter the complete catalog without importing or touching Qt widgets."""

    if status not in VALID_STATUS_FILTERS:
        raise ValidationError(
            "Crib status filter must be All, Editable, or Modified"
        )
    rows = tuple(assets)
    modified = set(modified_asset_ids)
    words = tuple(
        word for word in search.replace("_", " ").casefold().split() if word
    )
    selected: list[CribAsset] = []
    for asset in rows:
        if group is not None and asset.group != group:
            continue
        if status == "editable" and not asset.editable:
            continue
        if status == "modified" and asset.asset_id not in modified:
            continue
        haystack = crib_search_text(asset)
        if words and not all(word in haystack for word in words):
            continue
        selected.append(asset)
    selected.sort(key=_photo_sort)
    return CribBrowserResult(
        assets=tuple(selected),
        catalog_total=len(rows),
        editable_total=sum(asset.editable for asset in rows),
        export_only_total=sum(not asset.editable for asset in rows),
    )


def crib_action_state(
    asset: CribAsset | None,
    *,
    source_ready: bool,
    busy: bool,
    modified: bool,
) -> CribActionState:
    """Compute controls without relying on widget state or visual inspection."""

    available = bool(asset is not None and source_ready and not busy)
    editable = bool(available and asset is not None and asset.editable)
    return CribActionState(
        can_preview=available,
        can_export=available,
        can_replace=editable,
        can_revert=editable and modified,
        can_drop_png=editable,
    )


@runtime_checkable
class CribPanelHost(Protocol):
    """The complete facade boundary consumed by :class:`CribPanel`."""

    @property
    def source_ready(self) -> bool: ...

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

    def revert_crib_photo(self, asset_id: str, progress: ProgressSink) -> object: ...

    @property
    def modified_crib_model_scene_ids(self) -> Iterable[str]: ...

    def list_crib_model_scenes(self) -> Iterable[dict[str, object]]: ...

    def export_crib_model(
        self, scene_id: str, destination: Path, progress: ProgressSink
    ) -> tuple[Path, Path]: ...

    def import_crib_model(
        self, scene_id: str, edited_gltf: Path, progress: ProgressSink
    ) -> object: ...

    def revert_crib_model(
        self, scene_id: str, progress: ProgressSink
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class CribPanelCallbacks:
    """Callables used to adapt the root facade without subclassing anything."""

    list_assets: Callable[[], Iterable[CribAsset]]
    is_source_ready: Callable[[], bool]
    modified_ids: Callable[[], Iterable[str]]
    preview: Callable[[str, ProgressSink], Path]
    export: Callable[[str, Path, ProgressSink], Path]
    replace: Callable[[str, Path, ProgressSink], object]
    revert: Callable[[str, ProgressSink], object]
    list_models: Callable[[], Iterable[dict[str, object]]] = lambda: ()
    modified_model_ids: Callable[[], Iterable[str]] = lambda: ()
    export_model: Callable[
        [str, Path, ProgressSink], tuple[Path, Path]
    ] = lambda _scene, _path, _progress: (_path, _path.with_suffix(".bin"))
    import_model: Callable[
        [str, Path, ProgressSink], object
    ] = lambda _scene, _path, _progress: None
    revert_model: Callable[
        [str, ProgressSink], object
    ] = lambda _scene, _progress: None


class CallbackCribPanelHost:
    """Thin structural adapter around :class:`CribPanelCallbacks`."""

    def __init__(self, callbacks: CribPanelCallbacks) -> None:
        self.callbacks = callbacks

    @property
    def source_ready(self) -> bool:
        return bool(self.callbacks.is_source_ready())

    @property
    def modified_crib_asset_ids(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.callbacks.modified_ids())

    def list_crib_assets(self) -> tuple[CribAsset, ...]:
        rows = tuple(self.callbacks.list_assets())
        if not all(isinstance(asset, CribAsset) for asset in rows):
            raise ValidationError("Crib panel host returned an invalid asset row")
        if len({asset.asset_id for asset in rows}) != len(rows):
            raise ValidationError("Crib panel host returned duplicate asset IDs")
        return rows

    def preview_crib_asset(self, asset_id: str, progress: ProgressSink) -> Path:
        return Path(self.callbacks.preview(asset_id, progress))

    def export_crib_asset(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path:
        return Path(self.callbacks.export(asset_id, destination, progress))

    def replace_crib_photo(
        self, asset_id: str, supplied_png: Path, progress: ProgressSink
    ) -> object:
        return self.callbacks.replace(asset_id, supplied_png, progress)

    def revert_crib_photo(self, asset_id: str, progress: ProgressSink) -> object:
        return self.callbacks.revert(asset_id, progress)

    @property
    def modified_crib_model_scene_ids(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.callbacks.modified_model_ids())

    def list_crib_model_scenes(self) -> tuple[dict[str, object], ...]:
        rows = tuple(dict(row) for row in self.callbacks.list_models())
        if len({str(row.get("scene_id")) for row in rows}) != len(rows):
            raise ValidationError("Crib panel host returned duplicate model scenes")
        return rows

    def export_crib_model(
        self, scene_id: str, destination: Path, progress: ProgressSink
    ) -> tuple[Path, Path]:
        return self.callbacks.export_model(scene_id, destination, progress)

    def import_crib_model(
        self, scene_id: str, edited_gltf: Path, progress: ProgressSink
    ) -> object:
        return self.callbacks.import_model(scene_id, edited_gltf, progress)

    def revert_crib_model(
        self, scene_id: str, progress: ProgressSink
    ) -> object:
        return self.callbacks.revert_model(scene_id, progress)


from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt5.QtGui import QImageReader, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


PYQT5_AVAILABLE = True

# The Crib writer accepts any standard PNG at the slot's exact size, and the
# panel fits any ordinary image to that size before staging -- so the chooser
# and the drop target both advertise the full set instead of only PNG.
CRIB_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga",
}
CRIB_IMAGE_FILTER = (
    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)"
)


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


class _PngDropPreview(QFrame):
    png_dropped = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._accepting = False
        self._pixmap: QPixmap | None = None
        self.setAcceptDrops(True)
        self.setObjectName("cribPreviewFrame")
        self.setMinimumHeight(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        self.image = QLabel("Select a Crib asset")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setWordWrap(True)
        self.image.setObjectName("cribPreviewImage")
        self.hint = QLabel("All 498 assets can be previewed and exported")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setObjectName("cribMuted")
        layout.addWidget(self.image, 1)
        layout.addWidget(self.hint)

    def set_accepting(self, accepting: bool, hint: str) -> None:
        self._accepting = accepting
        self.hint.setText(hint)

    def set_message(self, message: str) -> None:
        self._pixmap = None
        self.image.setPixmap(QPixmap())
        self.image.setText(message)

    def set_png(self, path: Path) -> bool:
        reader = QImageReader(str(path))
        reader.setDecideFormatFromContent(True)
        image = reader.read()
        if image.isNull():
            self.set_message("This PNG could not be previewed")
            return False
        self._pixmap = QPixmap.fromImage(image)
        self.image.clear()
        self._rescale()
        return True

    def _rescale(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        target = self.image.size()
        self.image.setPixmap(
            self._pixmap.scaled(
                max(1, target.width()),
                max(1, target.height()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._rescale()

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        mime = event.mimeData()  # type: ignore[attr-defined]
        urls = mime.urls() if mime.hasUrls() else []
        if not self._accepting:
            event.ignore()  # type: ignore[attr-defined]
            return
        if urls:
            # Accept the drag so an unusable drop can explain itself with a
            # plain message instead of silently bouncing off the preview.
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()  # type: ignore[attr-defined]
        if len(urls) != 1:
            QMessageBox.information(
                self,
                "That drop can't be used yet",
                "Drop one file at a time. Pick the single image you want to "
                "use and drop it here again.",
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        url = urls[0]
        if not url.isLocalFile() or url.host():
            QMessageBox.information(
                self,
                "That drop can't be used yet",
                "That drop is a link or a web address, not a file on this "
                "computer. Save or download the image first, then drop the "
                "real file here.",
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        supplied = Path(url.toLocalFile())
        if supplied.suffix.casefold() not in CRIB_IMAGE_EXTENSIONS:
            QMessageBox.information(
                self,
                "That drop can't be used yet",
                "That file is not an image this panel can read. Drop a PNG, "
                "JPEG, BMP, GIF, WebP or TGA image — any size is fine, the "
                "editor resizes it for you.",
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        self.png_dropped.emit(supplied)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class CribPanel(QWidget):
    """Editable-first browser for all 498 known NFL 2K5 Crib textures."""

    error_raised = pyqtSignal(str)
    operation_state_changed = pyqtSignal(bool)
    crib_modified = pyqtSignal(str)
    crib_reverted = pyqtSignal(str)

    def __init__(
        self,
        host: CribPanelHost,
        parent: QWidget | None = None,
        *,
        operation_admission: Callable[[], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(host, CribPanelHost):
            raise TypeError("Crib panel host does not implement CribPanelHost")
        self.host = host
        self._operation_admission = operation_admission
        self.browser = CribBrowserResult((), 0, 0, 0)
        self.selected_asset_id: str | None = None
        self._all_assets: tuple[CribAsset, ...] = ()
        self._model_scenes: tuple[dict[str, object], ...] = ()
        self._busy = False
        self._refresh_after_task = False
        self._preview_generation = 0
        self._tasks: set[_Task] = set()
        self._pool = QThreadPool(self)
        # Private exact-size copies prepared from ordinary images.  They serve
        # one edit and are removed with the panel, never entered into projects.
        self._fit_dir: Path | None = None
        self.destroyed.connect(self._cleanup_fitted_images)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._filters_changed)
        self.setObjectName("cribPanel")
        self._build_ui()
        self._apply_style()
        self._connect()
        self.refresh(keep_selection=False)

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
        title = QLabel("The Crib")
        title.setObjectName("cribTitle")
        subtitle = QLabel(
            "Put your own photos on the wall and inspect every collectible, "
            "room, and object texture."
        )
        subtitle.setObjectName("cribMuted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        self.count_label = QLabel("Loading 498 assets…")
        self.count_label.setObjectName("cribCountPill")
        header.addLayout(titles, 1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(
            "Search team photos, bobbleheads, room screens, materials…"
        )
        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", None)
        self.status_filter.addItem("Editable assets", "editable")
        self.status_filter.addItem("Modified", "modified")
        self.status_filter.setMinimumWidth(185)
        self.group_filter = QComboBox()
        self.group_filter.addItem("All collections", None)
        self.group_filter.setMinimumWidth(220)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.group_filter)
        root.addLayout(filters)

        splitter = QSplitter(Qt.Horizontal)
        browser_card = QFrame()
        browser_card.setObjectName("cribCard")
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Asset", "Collection", "Size", "Status"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        browser_layout.addWidget(self.table, 1)
        self.match_label = QLabel("0 matches")
        self.match_label.setObjectName("cribMuted")
        self.match_label.setContentsMargins(12, 7, 12, 9)
        browser_layout.addWidget(self.match_label)
        splitter.addWidget(browser_card)

        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(390)
        preview_tab = QWidget()
        detail_layout = QVBoxLayout(preview_tab)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(10)
        self.asset_title = QLabel("Select a Crib asset")
        self.asset_title.setObjectName("cribDetailTitle")
        self.asset_title.setWordWrap(True)
        self.status_label = QLabel("Editable assets are marked below")
        self.status_label.setObjectName("cribStatus")
        self.metadata_label = QLabel("")
        self.metadata_label.setObjectName("cribMuted")
        self.metadata_label.setWordWrap(True)
        self.preview = _PngDropPreview()
        self.note_label = QLabel(
            "Choose an asset to see its exact authoring and ownership status."
        )
        self.note_label.setObjectName("cribNote")
        self.note_label.setWordWrap(True)
        detail_layout.addWidget(self.asset_title)
        detail_layout.addWidget(self.status_label)
        detail_layout.addWidget(self.metadata_label)
        detail_layout.addWidget(self.preview, 1)
        detail_layout.addWidget(self.note_label)
        actions = QHBoxLayout()
        self.export_button = QPushButton("Export PNG")
        self.replace_button = QPushButton("Replace PNG")
        self.replace_button.setObjectName("cribPrimaryButton")
        self.revert_button = QPushButton("Revert")
        actions.addWidget(self.export_button)
        actions.addWidget(self.replace_button, 1)
        actions.addWidget(self.revert_button)
        detail_layout.addLayout(actions)
        self.tabs.addTab(preview_tab, "Preview & Edit")

        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)
        model_layout.setContentsMargins(18, 16, 18, 16)
        model_layout.setSpacing(12)
        model_title = QLabel("Electronics model positions")
        model_title.setObjectName("cribDetailTitle")
        model_intro = QLabel(
            "Export a proved scene to glTF, move its existing vertices, then "
            "import it. Vertex count and faces must stay identical."
        )
        model_intro.setObjectName("cribMuted")
        model_intro.setWordWrap(True)
        self.model_scene = QComboBox()
        self.model_scene.setMinimumWidth(260)
        self.model_details = QLabel("Load your NFL 2K5 XISO to list model scenes.")
        self.model_details.setObjectName("cribNote")
        self.model_details.setWordWrap(True)
        model_actions = QHBoxLayout()
        self.model_export_button = QPushButton("Export glTF")
        self.model_import_button = QPushButton("Import Edited glTF")
        self.model_import_button.setObjectName("cribPrimaryButton")
        self.model_revert_button = QPushButton("Revert Model")
        model_actions.addWidget(self.model_export_button)
        model_actions.addWidget(self.model_import_button, 1)
        model_actions.addWidget(self.model_revert_button)
        model_limit = QLabel(
            "Preserved as original game bytes: UVs, materials, collision, "
            "indices, normals and all non-position registers. Unsupported: "
            "add/remove faces, subdivision, welding, decimation or object swaps."
        )
        model_limit.setObjectName("cribMuted")
        model_limit.setWordWrap(True)
        model_layout.addWidget(model_title)
        model_layout.addWidget(model_intro)
        model_layout.addWidget(self.model_scene)
        model_layout.addWidget(self.model_details)
        model_layout.addLayout(model_actions)
        model_layout.addWidget(model_limit)
        model_layout.addStretch(1)
        self.tabs.addTab(model_tab, "Models")

        findings = QTextBrowser()
        findings.setObjectName("cribFindings")
        findings.setOpenExternalLinks(False)
        findings.setHtml(CRIB_FINDINGS_HTML)
        self.tabs.addTab(findings, "Findings & limits")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        root.addWidget(splitter, 1)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("cribMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch(1)
        progress_row.addWidget(self.progress_bar)
        root.addLayout(progress_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#cribPanel {
                background: #111823; color: #eaf0f8;
                font-family: Inter, "Noto Sans", sans-serif; font-size: 13px;
            }
            QLabel#cribTitle { color: #fff; font-size: 27px; font-weight: 750; }
            QLabel#cribDetailTitle { color: #fff; font-size: 20px; font-weight: 700; }
            QLabel#cribMuted { color: #91a0b5; }
            QLabel#cribCountPill, QLabel#cribStatus {
                color: #7ce8b2; background: #16352c; border: 1px solid #2a6751;
                border-radius: 10px; padding: 5px 10px; font-weight: 650;
            }
            QLabel#cribNote {
                color: #cbd6e4; background: #172130; border: 1px solid #28384d;
                border-radius: 8px; padding: 10px;
            }
            QFrame#cribCard, QFrame#cribPreviewFrame {
                background: #151f2c; border: 1px solid #28384d; border-radius: 10px;
            }
            QFrame#cribPreviewFrame { border-style: dashed; }
            QLabel#cribPreviewImage { color: #75859b; font-size: 14px; }
            QLineEdit, QComboBox {
                color: #eaf0f8; background: #151f2c; border: 1px solid #34475e;
                border-radius: 7px; padding: 8px 10px; min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #4f9cf9; }
            QTableWidget {
                color: #dce5f1; background: transparent;
                alternate-background-color: #182433; border: none;
                gridline-color: #26364a; selection-background-color: #244f76;
                selection-color: #fff;
            }
            QHeaderView::section {
                color: #91a0b5; background: #121b27; border: none;
                border-bottom: 1px solid #304158; padding: 8px; font-weight: 650;
            }
            QTabWidget::pane {
                background: #151f2c; border: 1px solid #28384d; border-radius: 8px;
            }
            QTabBar::tab {
                color: #9dabc0; background: #121b27; border: 1px solid #28384d;
                padding: 8px 14px;
            }
            QTabBar::tab:selected { color: #fff; background: #1b2b3e; }
            QTextBrowser#cribFindings {
                color: #d9e3ef; background: #151f2c; border: none; padding: 14px;
            }
            QPushButton {
                color: #dce8f7; background: #233247; border: 1px solid #3a506b;
                border-radius: 7px; padding: 8px 13px; font-weight: 600;
            }
            QPushButton:hover { background: #2a3d56; }
            QPushButton:pressed { background: #1c293a; }
            QPushButton:disabled { color: #68778b; background: #192330; }
            QPushButton#cribPrimaryButton {
                color: #07150e; background: #43d590; border-color: #43d590;
            }
            QPushButton#cribPrimaryButton:hover { background: #58e3a2; }
            QProgressBar {
                background: #172130; border: 1px solid #304158;
                border-radius: 4px; height: 7px;
            }
            QProgressBar::chunk { background: #43d590; border-radius: 3px; }
            """
        )

    def _connect(self) -> None:
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.status_filter.currentIndexChanged.connect(self._filters_changed)
        self.group_filter.currentIndexChanged.connect(self._filters_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.export_button.clicked.connect(self._export_selected)
        self.replace_button.clicked.connect(self._choose_replacement)
        self.revert_button.clicked.connect(self._revert_selected)
        self.preview.png_dropped.connect(self._replace_with_path)
        self.model_scene.currentIndexChanged.connect(self._model_scene_changed)
        self.model_export_button.clicked.connect(self._export_model)
        self.model_import_button.clicked.connect(self._import_model)
        self.model_revert_button.clicked.connect(self._revert_model)
        self.error_raised.connect(
            lambda message: QMessageBox.warning(self, "The Crib", message)
        )

    def refresh(self, *, keep_selection: bool = True) -> None:
        wanted = self.selected_asset_id if keep_selection else None
        try:
            self._all_assets = tuple(self.host.list_crib_assets())
            self._model_scenes = tuple(self.host.list_crib_model_scenes())
            self._refresh_model_choices()
            self._refresh_group_choices()
            modified = set(self.host.modified_crib_asset_ids)
            self.browser = filter_crib_assets(
                self._all_assets,
                search=self.search.text(),
                status=self.status_filter.currentData(),
                group=self.group_filter.currentData(),
                modified_asset_ids=modified,
            )
        except Exception as exc:
            self.error_raised.emit(str(exc).strip() or exc.__class__.__name__)
            return

        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(self.browser.assets))
        selected_row = -1
        for row, asset in enumerate(self.browser.assets):
            is_modified = asset.asset_id in modified
            status = (
                "Modified · Editable"
                if is_modified
                else "Editable"
                if asset.editable
                else "Unavailable · Catalog validation required"
            )
            values = (
                ("●  " if is_modified else "") + asset.label,
                asset.group,
                f"{asset.width}×{asset.height} · {asset.format_name}",
                status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, asset.asset_id)
                if column == 0:
                    item.setToolTip(asset.selector)
                self.table.setItem(row, column, item)
            if asset.asset_id == wanted:
                selected_row = row
        if selected_row < 0 and self.browser.assets:
            selected_row = 0
        if selected_row >= 0:
            self.table.selectRow(selected_row)
            self.selected_asset_id = self.browser.assets[selected_row].asset_id
            self._show_asset(self.browser.assets[selected_row])
        else:
            self.selected_asset_id = None
            self._show_asset(None)
        self.table.blockSignals(False)
        self.count_label.setText(
            f"{self.browser.catalog_total:,} assets  ·  "
            f"{self.browser.editable_total:,} editable"
        )
        self.match_label.setText(
            f"{self.browser.match_total:,} matching asset"
            f"{'s' if self.browser.match_total != 1 else ''} · Team Photos shown first"
        )
        self._model_scene_changed()

    def _refresh_model_choices(self) -> None:
        current = self.model_scene.currentData()
        self.model_scene.blockSignals(True)
        self.model_scene.clear()
        for row in self._model_scenes:
            scene_id = str(row["scene_id"])
            name = str(row.get("scene_name", scene_id)).replace("_", " ").title()
            count = int(row.get("target_count", 0))
            self.model_scene.addItem(
                f"{name} · {count} mesh{'es' if count != 1 else ''}", scene_id
            )
        selected = self.model_scene.findData(current)
        self.model_scene.setCurrentIndex(selected if selected >= 0 else 0)
        self.model_scene.blockSignals(False)

    def _selected_model_scene(self) -> dict[str, object] | None:
        scene_id = self.model_scene.currentData()
        return next(
            (row for row in self._model_scenes if row.get("scene_id") == scene_id),
            None,
        )

    def _model_scene_changed(self, *_args: object) -> None:
        row = self._selected_model_scene()
        if row is None:
            self.model_details.setText(
                "Load your NFL 2K5 XISO to list model scenes."
            )
        else:
            scene_id = str(row["scene_id"])
            names = ", ".join(str(value) for value in row.get("shape_names", ()))
            modified = scene_id in set(self.host.modified_crib_model_scene_ids)
            self.model_details.setText(
                ("Modified · " if modified else "")
                + f"{names}\n{int(row.get('target_count', 0))} fixed target(s) · "
                "same-count position-only import"
            )
        self._refresh_controls()

    def _refresh_group_choices(self) -> None:
        current = self.group_filter.currentData()
        groups = crib_group_options(self._all_assets)
        existing = tuple(
            self.group_filter.itemData(index)
            for index in range(1, self.group_filter.count())
        )
        if existing == groups:
            return
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All collections", None)
        for group in groups:
            self.group_filter.addItem(group, group)
        selected = self.group_filter.findData(current)
        self.group_filter.setCurrentIndex(selected if selected >= 0 else 0)
        self.group_filter.blockSignals(False)

    def _selected_asset(self) -> CribAsset | None:
        if self.selected_asset_id is None:
            return None
        return next(
            (
                asset
                for asset in self.browser.assets
                if asset.asset_id == self.selected_asset_id
            ),
            None,
        )

    def _selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.selected_asset_id = None
            self._show_asset(None)
            return
        item = self.table.item(rows[0].row(), 0)
        self.selected_asset_id = str(item.data(Qt.UserRole))
        self._show_asset(self._selected_asset())

    def _show_asset(self, asset: CribAsset | None) -> None:
        self._preview_generation += 1
        if asset is None:
            self.asset_title.setText("Select a Crib asset")
            self.status_label.setText("No asset selected")
            self.metadata_label.clear()
            self.note_label.setText(
                "Choose an asset to see its exact authoring and ownership status."
            )
            self.preview.set_message("No matching asset selected")
            self._refresh_controls()
            return
        modified = asset.asset_id in set(self.host.modified_crib_asset_ids)
        self.asset_title.setText(asset.label)
        self.status_label.setText(
            "Modified · Editable Crib texture"
            if modified
            else "Editable Crib texture"
            if asset.editable
            else "Unavailable · Catalog validation required"
        )
        location = (
            f"Scene {asset.scene_name} · texture {asset.texture_index}"
            if asset.scene_name is not None
            else asset.storage.value.replace("_", " ").title()
        )
        materials = (
            "\nMaterials: " + ", ".join(asset.material_names)
            if asset.material_names
            else ""
        )
        self.metadata_label.setText(
            f"{asset.group}\n{asset.width}×{asset.height} · {asset.format_name} · "
            f"{asset.mip_levels} mip level{'s' if asset.mip_levels != 1 else ''}\n"
            f"{location}{materials}\n{asset.selector}"
        )
        self.note_label.setText(asset.authoring_note)
        self._refresh_controls()
        if not self.host.source_ready:
            self.preview.set_message("Load your NFL 2K5 XISO to prepare this PNG")
            return
        self._load_preview(asset)

    def _refresh_controls(self) -> None:
        asset = self._selected_asset()
        modified = bool(
            asset and asset.asset_id in set(self.host.modified_crib_asset_ids)
        )
        actions = crib_action_state(
            asset,
            source_ready=self.host.source_ready,
            busy=self._busy,
            modified=modified,
        )
        self.export_button.setEnabled(actions.can_export)
        self.replace_button.setEnabled(actions.can_replace)
        self.revert_button.setEnabled(actions.can_revert)
        self.preview.set_accepting(
            actions.can_drop_png,
            (
                f"Drop any image here to replace this Crib texture — it is "
                f"resized to the exact {asset.width}×{asset.height} slot for you"
                if asset is not None and asset.editable
                else "This catalog row is unavailable because its writer contract failed validation"
            ),
        )
        self.table.setEnabled(not self._busy)
        self.search.setEnabled(not self._busy)
        self.status_filter.setEnabled(not self._busy)
        self.group_filter.setEnabled(not self._busy)
        model = self._selected_model_scene()
        scene_id = str(model["scene_id"]) if model is not None else ""
        model_available = bool(model and self.host.source_ready and not self._busy)
        self.model_scene.setEnabled(not self._busy and bool(self._model_scenes))
        # Keep export/import clickable so gray never means silent no-op:
        # click always works or explains the next step.
        export_tip = (
            "Export this Crib electronics scene as glTF (same-topology positions)."
            if model_available
            else (
                "Load your NFL 2K5 XISO and select a proved electronics scene first. "
                "Click still explains this — export needs a loaded source + scene."
                if not self.host.source_ready
                else "Select one of the proved electronics scenes in the Model list first."
            )
        )
        import_tip = (
            "Import a same-topology POSITION-only glTF for this scene "
            "(vertex count and triangles must match the export)."
            if model_available
            else (
                "Load your NFL 2K5 XISO and select a proved electronics scene first. "
                "Click still explains this. Import never mutates your original XISO."
                if not self.host.source_ready
                else "Select a proved electronics scene first, then import a same-topology glTF."
            )
        )
        self.model_export_button.setEnabled(not self._busy)
        self.model_import_button.setEnabled(not self._busy)
        self.model_export_button.setToolTip(export_tip)
        self.model_import_button.setToolTip(import_tip)
        self.model_export_button.setProperty(
            "disableReason", "" if model_available else export_tip
        )
        self.model_import_button.setProperty(
            "disableReason", "" if model_available else import_tip
        )
        self.model_revert_button.setEnabled(
            model_available
            and scene_id in set(self.host.modified_crib_model_scene_ids)
        )

    def _load_preview(self, asset: CribAsset) -> None:
        generation = self._preview_generation
        self.preview.set_message(f"Preparing {asset.label}…")

        def ready(value: object) -> None:
            if generation != self._preview_generation:
                return
            if not self.preview.set_png(Path(value)):  # type: ignore[arg-type]
                self.error_raised.emit("The prepared Crib PNG could not be displayed")
            else:
                self.progress_label.setText("PNG ready")

        self._run(
            lambda progress: self.host.preview_crib_asset(asset.asset_id, progress),
            ready,
        )

    def _filters_changed(self, *_args: object) -> None:
        if self._busy:
            return
        self.refresh(keep_selection=False)

    def _export_selected(self) -> None:
        asset = self._selected_asset()
        if asset is None:
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Crib PNG",
            asset.suggested_filename,
            "PNG image (*.png)",
        )
        if not selected:
            return
        destination = Path(selected)
        self._run(
            lambda progress: self.host.export_crib_asset(
                asset.asset_id, destination, progress
            ),
            lambda value: self.progress_label.setText(
                f"Exported {Path(value).name}"
            ),
        )

    def _choose_replacement(self) -> None:
        asset = self._selected_asset()
        if asset is None or not asset.editable:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose an image for this Crib texture (any size or format — "
            f"it is resized to {asset.width}×{asset.height} for you)",
            "",
            CRIB_IMAGE_FILTER,
        )
        if selected:
            self._replace_with_path(Path(selected))

    def _fit_crib_image(self, asset: CribAsset, supplied: Path) -> Path | None:
        """Return an exact-size PNG for this slot with Contain/Cover/Stretch.

        Dialog and drag/drop both call this path (same code as kit import).
        Any ordinary image is accepted: the fit layer resizes it to the slot's
        exact dimensions and writes an RGBA PNG. An already-exact image is
        returned untouched. Returns ``None`` when the file cannot be read or
        the user declines.
        """

        from mod_editor.core.errors import ValidationError as _ValidationError
        from mod_editor.core.image_fit import (
            fit_image,
            fit_mode_from_label,
            fit_mode_labels,
            fit_to_png,
        )

        try:
            probe = fit_image(supplied, asset.width, asset.height, mode="auto")
        except _ValidationError as exc:
            QMessageBox.information(
                self,
                "That file could not be read as an image",
                f"{exc}\n\nFix: choose or drop a PNG, JPEG, BMP, GIF, WebP or "
                "TGA image. Any size works -- the editor resizes it for you.",
            )
            return None

        needs_png_conversion = (
            probe.source_format != "PNG" or probe.source_mode != "RGBA"
        )
        if not probe.changed and not needs_png_conversion:
            return supplied

        if probe.changed:
            labels = fit_mode_labels()
            choice, accepted = QInputDialog.getItem(
                self,
                "How should this image fit the slot?",
                f"This Crib texture must be exactly {asset.width}×{asset.height}, "
                f"and that image is {probe.source_width}×{probe.source_height}.\n\n"
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
            except _ValidationError as exc:
                QMessageBox.information(
                    self, "Invalid fit mode", f"{exc}\n\nNo edit was staged."
                )
                return None
        else:
            chosen_mode = "contain"  # exact size; PNG conversion only

        if self._fit_dir is None:
            self._fit_dir = Path(tempfile.mkdtemp(prefix="2k5-crib-fitted-"))
        staged = self._fit_dir / f"crib-{uuid4().hex}.png"
        try:
            result = fit_to_png(
                supplied, asset.width, asset.height, staged, mode=chosen_mode
            )
        except _ValidationError as exc:
            QMessageBox.information(
                self,
                "Could not prepare that image",
                f"{exc}\n\nFix: try a different image. No edit was staged.",
            )
            return None
        self.progress_label.setText(
            f"Prepared image for {asset.label} -- {result.describe()} "
            f"({chosen_mode})."
        )
        return staged

    def _cleanup_fitted_images(self, *_args: object) -> None:
        import shutil

        root = self._fit_dir
        self._fit_dir = None
        if root is not None and root.name.startswith("2k5-crib-fitted-"):
            shutil.rmtree(root, ignore_errors=True)

    def _replace_with_path(self, supplied: Path) -> None:
        asset = self._selected_asset()
        if asset is None or not asset.editable:
            self.error_raised.emit(
                "Select an Editable Crib asset before replacing a PNG. Fix: "
                "choose one of the editable rows in the list, then drop or "
                "choose your image again."
            )
            return
        fitted = self._fit_crib_image(asset, Path(supplied))
        if fitted is None:
            return

        def complete(_value: object) -> None:
            self.crib_modified.emit(asset.asset_id)
            self.progress_label.setText("Crib replacement staged")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.replace_crib_photo(
                asset.asset_id, fitted, progress
            ),
            complete,
        )

    def _revert_selected(self) -> None:
        asset = self._selected_asset()
        if asset is None or not asset.editable:
            return

        def complete(_value: object) -> None:
            self.crib_reverted.emit(asset.asset_id)
            self.progress_label.setText("Original Crib texture restored")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.revert_crib_photo(asset.asset_id, progress),
            complete,
        )

    def _export_model(self) -> None:
        if not self.host.source_ready:
            QMessageBox.information(
                self,
                "Load a game first",
                "Crib model export needs your NFL 2K5 XISO loaded.\n\n"
                "Fix: load the XISO, open The Crib, pick a proved electronics "
                "scene, then export glTF.",
            )
            return
        row = self._selected_model_scene()
        if row is None:
            QMessageBox.information(
                self,
                "Select a proved electronics scene",
                "Choose one of the proved Crib electronics scenes in the Model "
                "list first, then export glTF.",
            )
            return
        scene_id = str(row["scene_id"])
        scene_name = str(row.get("scene_name", "crib_scene"))
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Crib model",
            f"{scene_name}.gltf",
            "glTF model (*.gltf)",
        )
        if not selected:
            return
        destination = Path(selected)
        self._run(
            lambda progress: self.host.export_crib_model(
                scene_id, destination, progress
            ),
            lambda value: self.progress_label.setText(
                f"Exported {Path(value[0]).name} and {Path(value[1]).name}"  # type: ignore[index]
            ),
        )

    def _import_model(self) -> None:
        if not self.host.source_ready:
            QMessageBox.information(
                self,
                "Load a game first",
                "Crib model import needs your NFL 2K5 XISO loaded.\n\n"
                "Fix: load the XISO, open The Crib, pick a proved electronics "
                "scene, export glTF, edit POSITION only, then import again.\n\n"
                "Import stages a copy — it never mutates your original disc/ISO.",
            )
            return
        row = self._selected_model_scene()
        if row is None:
            QMessageBox.information(
                self,
                "Select a proved electronics scene",
                "Choose one of the proved Crib electronics scenes in the Model "
                "list first, then import a same-topology POSITION-only glTF.",
            )
            return
        scene_id = str(row["scene_id"])
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose edited Crib glTF",
            "",
            "glTF model (*.gltf)",
        )
        if not selected:
            return

        def complete(_value: object) -> None:
            self.crib_modified.emit(f"{scene_id}.geometry")
            self.progress_label.setText("Edited Crib model staged")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.import_crib_model(
                scene_id, Path(selected), progress
            ),
            complete,
        )

    def _revert_model(self) -> None:
        row = self._selected_model_scene()
        if row is None:
            return
        scene_id = str(row["scene_id"])

        def complete(_value: object) -> None:
            self.crib_reverted.emit(f"{scene_id}.geometry")
            self.progress_label.setText("Original Crib model positions restored")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.revert_crib_model(scene_id, progress),
            complete,
        )

    def _run(
        self,
        operation: Callable[[ProgressSink], object],
        on_success: Callable[[object], None],
    ) -> None:
        if self._busy:
            return
        if self._operation_admission is not None:
            denial = self._operation_admission()
            if denial is not None:
                self.error_raised.emit(denial)
                return
        self._busy = True
        self.operation_state_changed.emit(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._refresh_controls()
        task = _Task(operation)
        self._tasks.add(task)
        task.signals.progress.connect(self._progress)
        task.signals.result.connect(on_success)
        task.signals.error.connect(self.error_raised.emit)

        def finished() -> None:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            if self._refresh_after_task:
                self._refresh_after_task = False
                self.refresh()
            else:
                self._refresh_controls()

        task.signals.finished.connect(finished)
        try:
            self._pool.start(task)
        except BaseException:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
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
    "CRIB_FINDINGS_HTML",
    "CRIB_FINDINGS_PLAIN_TEXT",
    "CallbackCribPanelHost",
    "CribActionState",
    "CribBrowserResult",
    "CribPanel",
    "CribPanelCallbacks",
    "CribPanelHost",
    "PYQT5_AVAILABLE",
    "crib_action_state",
    "crib_group_options",
    "crib_search_text",
    "filter_crib_assets",
]
