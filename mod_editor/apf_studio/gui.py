"""Polished PyQt5 product shell for APF 2K8 Mod Studio.

The module is intentionally a view/controller layer.  It contains no game
assets and does not touch a user's source directly; every operation crosses the
``ApfStudioFacade`` boundary.  Importing this module never creates a
``QApplication`` or opens a window, which also keeps automated checks headless.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import traceback
from typing import Any, Callable, Iterable

from PyQt5.QtCore import (
    QObject,
    QProcess,
    QRunnable,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
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
from .audio_encoding import ExternalXma1Encoder
from .facade import (
    ApfStudioFacade,
    ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE,
    TEAM_DISPLAY_NAME_EDIT_SCOPE_MESSAGE,
)
from .field_art import (
    FieldArtInventory,
    FieldArtInventoryError,
    FieldArtKind,
    build_field_art_inventory,
)
from .inspectors import ApfInspectorService, ExportIdentity, InspectorRow, PagedModel
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
from .project import (
    ProjectError,
    ProjectTargetIdentity,
    RecoveryCandidate,
    WorkspaceStateStore,
    project_target_identity,
)
from .product_findings import gameplay_snapshot, presentation_snapshot
from .roster_workspace_qt import RosterReservePlanner
from .stadium import ApfStadiumPreview, ApfStadiumScene
from .stadium_material_findings import load_stadium_material_findings


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
    candidate = (
        Path(__file__).resolve().parents[2]
        / "packaging"
        / "apf2k8-mod-studio.svg"
    )
    try:
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    except Exception:
        pass
    return None

AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT = (
    "fully_validated_read_only_preview_then_explicit_apply"
)
AUDIO_DIRECT_DROP_CONTRACT = "selected_exact_slot_xma1_or_pcm16_wav"
AUDIO_ANNOTATION_UI_CONTRACT = "project_metadata_only_stable_logical_cue_id"
AUDIO_ANNOTATION_MAX_TITLE_CHARS = 120
AUDIO_ANNOTATION_MAX_NOTE_CHARS = 2_000


CATEGORY_BLURBS: dict[ApfCategory, str] = {
    ApfCategory.GETTING_STARTED: "Load your own game, make familiar PNG edits, then build a separate playable copy.",
    ApfCategory.UNIFORMS: "Edit all 96 mapped material-color textures and browse or export every one of the 408 indexed uniform and equipment records.",
    ApfCategory.ROSTERS: "Browse every mapped player and team, replace nonempty player first/last names and team display names under their exact source limits, choose any of 17 exact player positions, edit 28 native 0–99 base ratings per player, or safely export/import all 2,254 players through a private ratings CSV. Shared name allocations change every disclosed owner together; team abbreviations and roster structure remain locked.",
    ApfCategory.TEAM_IDENTITY: "Browse team-facing resources; more identity editing unlocks here as each field is proven safe.",
    ApfCategory.LOGOS: "Replace the shared 512×512 team-logo crest and the 128×128 draft logo, and browse every indexed logo and team-art record.",
    ApfCategory.SCOREBUG: "Edit the proved digital_font mask and inspect the rest of the broadcast presentation inventory.",
    ApfCategory.FIELD_ART: "Replace the six proven field textures — endzone layers, practice overlays, and the divot base — and browse the complete field-art inventory.",
    ApfCategory.STADIUMS: "Explore your game's stadium geometry in 3D; stadium textures stay export-only until material ownership is proven.",
    ApfCategory.MENUS: "Search menu, layout, font, and localized text structures across the complete archive.",
    ApfCategory.AUDIO: "Browse soundtrack, commentary, stadium, presentation, and standalone XMA1 audio; play verified WAV previews, export original XMA, author from PCM WAV with your own encoder, or batch-stage exact-slot replacements from a retail-free XMA1 or PCM16 WAV folder or ZIP.",
    ApfCategory.GAMEPLAY: "Inspect mapped sliders and follow gameplay research; nothing is offered as an edit until it is proven safe.",
    ApfCategory.PLAYBOOKS: "Inspect mapped PLAY and DRCT structures while route authoring semantics remain under study.",
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
    }[status]


def _status_text(status: ApfStatus) -> str:
    """Pair every capability color with a readable, non-color-only cue."""

    return {
        ApfStatus.EDITABLE: "✓ Editable",
        ApfStatus.PREVIEW: "◉ Preview",
        ApfStatus.EXPORT_ONLY: "↓ Export only",
        ApfStatus.COMING_SOON: "◷ Coming soon",
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
    return asset_action_binding(
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
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
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
    """Reference one read-only pack beside a staged volume without copying it.

    An APF index only parses under its own pack name and beside every sibling
    pack it declares, so chaining two writers over one volume needs those packs
    visible next to the intermediate copy.  A link is a reference, not a copy:
    no pack is duplicated, and the user's game is still never opened for
    writing.  Symlinks are tried first because they work across filesystems; a
    hard link is the fallback for platforms that restrict symlink creation.
    """

    failures: list[str] = []
    for linker in (os.symlink, os.link):
        try:
            linker(source, destination)
            return
        except (OSError, NotImplementedError, AttributeError) as exc:
            failures.append(f"{getattr(linker, '__name__', 'link')}: {exc}")
    raise RuntimeError(
        f"Could not reference the sibling pack {source.name} beside the staged "
        f"volume ({'; '.join(failures)}). This build needs the packs your game "
        "declares to be visible next to its own copy."
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


def build_team_logo_copied_volume(
    index_path: Path,
    staged_png: Path,
    out_volume: Path,
    package_manifest: Path,
    cache_manifest: Path,
    progress: Callable[[str, int, int], None],
    *,
    cache_catalog_index: int,
    siblings: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Run the two offline-proved team-logo writers over a copy of one 0A.

    One action, two proved writers.  The package write
    (``tools/apf_logo_patch.py``) lands in an intermediate copy; the cache write
    (``tools/apf_logocache_patch.py``) then reads that copy and produces the
    volume the author keeps, so the single delivered 0A carries both the
    ``uniform_logo_01`` package edit and the matching ``uniform_logocache``
    entry.  Either writer failing raises, and both writers remove their own
    partial outputs, so a failed build leaves nothing behind but the workspace
    this cleans up.  The retail source is never opened for writing.

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

    if siblings is None:
        siblings = _declared_sibling_packs(index_path)
    out_volume.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(
        tempfile.mkdtemp(
            prefix=".apf-team-logo-build-", dir=str(out_volume.parent)
        )
    )
    retained: Path | None = None
    try:
        # The cache writer re-parses its --index volume, and an APF index only
        # parses under its own pack name beside every sibling pack it declares.
        # Stage the intermediate that way and reference the siblings by link, so
        # no pack is copied and the retail source is still never opened for
        # writing.
        staged_volume = workspace / index_path.name
        for pack in siblings:
            _link_reference(index_path.parent / pack, workspace / pack)
        staged_manifest = workspace / "team_logo_package.json"
        run(
            tools / "apf_logo_patch.py",
            [
                "--index",
                str(index_path),
                "--png",
                str(staged_png),
                "--output-volume",
                str(staged_volume),
                "--manifest",
                str(staged_manifest),
            ],
            "Copying volume and writing the crest package through the proved writer",
        )
        run(
            tools / "apf_logocache_patch.py",
            [
                "--index",
                str(staged_volume),
                "--catalog-index",
                str(cache_catalog_index),
                "--png",
                str(staged_png),
                "--output-volume",
                str(out_volume),
                "--manifest",
                str(cache_manifest),
            ],
            "Writing the same crest into the prebuilt logo cache",
        )
        try:
            retained = _copy_new(staged_manifest, package_manifest)
        except OSError:
            # The volume and its cache manifest are already written and
            # verified; only the package-stage evidence copy failed.
            retained = None
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return {
        "volume": out_volume,
        "cache_manifest": cache_manifest,
        "package_manifest": retained,
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


class ImageDropLabel(QLabel):
    """Scaled preview that also accepts one local PNG replacement."""

    pngDropped = pyqtSignal(Path)

    def __init__(self, empty_text: str = "Preview appears here"):
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
        urls = mime.urls() if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith(".png"):
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:
        url = event.mimeData().urls()[0]  # type: ignore[attr-defined]
        self.pngDropped.emit(Path(url.toLocalFile()))
        event.acceptProposedAction()  # type: ignore[attr-defined]


class AudioReplacementDropZone(QFrame):
    """Accept one local XMA1 or PCM16 WAV for the selected exact sound slot."""

    audioDropped = pyqtSignal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("audioReplacementDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(58)
        self.setAccessibleName("Drop an audio replacement for the selected sound")
        self.setAccessibleDescription(
            "Accepts one pre-encoded RIFF XMA1 file, or one exact PCM16 WAV when "
            "a user-supplied XMA1 encoder is configured."
        )
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(2)
        self.title = QLabel("Drop .xma or exact PCM16 .wav here")
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
        return (
            path
            if regular and path.suffix.casefold() in {".xma", ".wav"}
            else None
        )

    def set_available(self, available: bool, *, modified: bool = False) -> None:
        self.setEnabled(available)
        self.setProperty("dropReady", bool(available))
        self.style().unpolish(self)
        self.style().polish(self)
        if available:
            self.title.setText(
                "Drop another .xma or exact PCM16 .wav here"
                if modified
                else "Drop .xma or exact PCM16 .wav here"
            )
            self.hint.setText(
                "WAV uses your configured encoder; XMA1 uses the advanced exact-slot route."
            )
            self.setToolTip(
                "Drop one local .xma or .wav file. It is validated for the currently "
                "selected sound; failures stage nothing."
            )
        else:
            self.title.setText("Select an Editable sound to drop audio")
            self.hint.setText(
                "Raw banks and index rows cannot accept one-sound replacements."
            )
            self.setToolTip(self.hint.text())

    def dragEnterEvent(self, event: object) -> None:
        path = (
            self.local_audio_path(event.mimeData())  # type: ignore[attr-defined]
            if self.isEnabled()
            else None
        )
        if path is None:
            event.ignore()  # type: ignore[attr-defined]
        else:
            event.acceptProposedAction()  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:
        path = self.local_audio_path(event.mimeData())  # type: ignore[attr-defined]
        if not self.isEnabled() or path is None:
            event.ignore()  # type: ignore[attr-defined]
            return
        self.audioDropped.emit(path)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class WordElidedLabel(QLabel):
    """One-line label that truncates at a word boundary and keeps full help."""

    def __init__(self, text: str):
        super().__init__()
        self._full_text = ""
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
            details = "\n\n".join(part for part in (summary, findings) if part)
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
        self._excluded_asset_ids: frozenset[str] = frozenset()
        self._included_asset_ids: frozenset[str] | None = None
        self.browse_export_only = browse_export_only
        self.action_lock_reason = action_lock_reason.strip()
        self._page = 0
        self._preview_token = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, type, class, or archive index…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Search the current category. Use the × inside this field to clear it.")
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
        self.preview = ImageDropLabel("Select a texture to generate a PNG preview.")
        self.preview.setAcceptDrops(False)
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
        self.replace_button.setToolTip("Choose a validated replacement PNG.")
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
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
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
        self.previous_button.setEnabled(self._page > 0)
        self.next_button.setEnabled(self._page + 1 < page_count)
        restored = False
        if preserve_asset_id:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.UserRole) == preserve_asset_id:
                    self.table.selectRow(row)
                    restored = True
                    break
        if not restored and rows:
            self.table.selectRow(0)
        elif not rows:
            self._clear_detail("No assets match those filters.")

    def _change_page(self, delta: int) -> None:
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
        notes = list(asset.notes)
        action = _asset_product_action(asset)
        if action is not None:
            notes.insert(0, action.authoring_note)
        if self.browse_export_only and self.action_lock_reason:
            notes.insert(0, self.action_lock_reason)
        notes.append(f"Export action: {asset.export_label}.")
        self.detail_notes.setText("\n".join(notes) or "This exact record can be exported from your own game.")
        self.export_button.setEnabled(True)
        editable_png = _is_editable_png_asset(asset) and not self.browse_export_only
        if self.browse_export_only:
            self.replace_button.setText("Replace locked")
            self.revert_button.setText("Revert locked")
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(False)
            self.revert_button.setVisible(True)
            self.revert_button.setEnabled(False)
            self.replace_button.setToolTip(self.action_lock_reason)
            self.revert_button.setToolTip(
                "There is no staged Field Art replacement to revert because replacement is locked."
            )
        else:
            self.replace_button.setText("Replace PNG…")
            self.revert_button.setText("Revert")
            self.replace_button.setVisible(editable_png)
            self.replace_button.setEnabled(editable_png)
            self.revert_button.setVisible(editable_png)
            self.revert_button.setEnabled(editable_png and modified)
        if not self.browse_export_only:
            self.revert_button.setToolTip(
                f"Restore the original {asset.name} texture."
                if modified
                else f"Nothing to revert—{asset.name} is still original."
            )
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
                if action is not None:
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
            else:
                self.preview.set_error(str(value))

        self.run_task("Preparing asset preview", operation, complete, False)

    def _clear_detail(self, message: str = "Choose an asset to inspect it.") -> None:
        self.detail_title.setText("Choose an asset")
        self.detail_status.setText("Every indexed record remains visible.")
        self.preview.set_message(message)
        self.detail_metadata.setText("")
        self.detail_notes.setText("")
        self.export_button.setEnabled(False)
        if self.browse_export_only:
            self.replace_button.setText("Replace locked")
            self.revert_button.setText("Revert locked")
            self.replace_button.setVisible(True)
            self.replace_button.setEnabled(False)
            self.revert_button.setVisible(True)
            self.revert_button.setEnabled(False)
            self.replace_button.setToolTip(self.action_lock_reason)
            self.revert_button.setToolTip(
                "There is no staged Field Art replacement to revert because replacement is locked."
            )
        else:
            self.replace_button.setVisible(False)
            self.revert_button.setVisible(False)
            self.revert_button.setToolTip("Nothing to revert—choose a modified editable asset first.")

    def _export_selected(self) -> None:
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

    def _replace_selected(self) -> None:
        asset = self._selected_asset()
        action = _asset_product_action(asset) if asset is not None else None
        if asset is None or action is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose edited {asset.name} PNG",
            str(Path.home()),
            "PNG image (*.png)",
        )
        if not path:
            return
        replace = getattr(self.facade, action.replace_method)
        self.run_task(
            f"Replacing {asset.name}",
            lambda progress: replace(Path(path), progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _revert_selected(self) -> None:
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
        self.search.setPlaceholderText("Search slots or linked teams…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Search uniform slots. Use Clear or the × inside this field to reset it.")
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
            "You can also drop an edited PNG here."
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
        self.replace_button.setToolTip("Choose an edited PNG or drop one onto the preview.")
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
        outer.addWidget(self.tabs, 1)
        self._clear_detail()

    def _search_changed(self, text: str) -> None:
        self.clear_search_button.setVisible(bool(text))
        self.refresh()

    def set_context(self) -> None:
        if not self.facade.source_ready:
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
        self._assets = self.facade.uniform_assets()
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
                "Load your game to browse and edit all 96 mapped slots."
            )

    def _selected_asset(self) -> UniformAsset | None:
        item = self.list.currentItem()
        return self._visible.get(item.data(Qt.UserRole)) if item else None

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
        self.contract.setText(f"PNG contract\n{asset.png_contract}")
        self.contract.setVisible(True)
        teams = ", ".join(asset.affected_teams) if asset.affected_teams else "No current team selector references this physical slot."
        self.teams.setText(f"Selector ownership\n{teams}")
        self.teams.setVisible(True)
        self.notes.setText("\n".join(asset.notes))
        self.notes.setVisible(bool(asset.notes))
        self.export_button.setEnabled(True)
        self.replace_button.setEnabled(True)
        self.revert_button.setEnabled(modified)
        self.revert_button.setToolTip(
            "Restore the original texture for this slot."
            if modified
            else "Nothing to revert—this texture is still original."
        )
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

        self.run_task(
            "Preparing uniform preview",
            lambda progress: self.facade.preview_uniform(asset.asset_id, progress),
            complete,
            False,
        )

    def _clear_detail(self, message: str = "Load your APF game to begin.") -> None:
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
        self.export_button.setEnabled(False)
        self.replace_button.setEnabled(False)
        self.revert_button.setEnabled(False)
        self.revert_button.setToolTip("Nothing to revert—choose a modified texture first.")

    def _export_selected(self) -> None:
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
        asset = self._selected_asset()
        if asset is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose edited {asset.width}×{asset.height} RGBA PNG",
            str(Path.home()),
            "RGBA PNG (*.png)",
        )
        if path:
            self._replace_path(Path(path))

    def _replace_path(self, path: Path) -> None:
        asset = self._selected_asset()
        if asset is None:
            return
        self.run_task(
            f"Replacing {asset.title}",
            lambda progress: self.facade.replace_uniform(asset.asset_id, path, progress),
            lambda _result: self._mutation_complete(asset.asset_id),
            True,
        )

    def _revert_selected(self) -> None:
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


class DigitalFontPanel(QFrame):
    """Focused editor for the proved 128×128 DXT5A score-digit mask."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
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
        title = QLabel("digital_font — score digit mask")
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
                    "The writer accepts exactly 128×128; any other size is "
                    "refused before it can enter your project."
                ),
            )
        )
        specs.addWidget(
            _spec_pill(
                "Alpha-only mask",
                tooltip=(
                    "The game reads only the alpha channel of this texture. "
                    "Keep RGB solid white and draw the digits in alpha."
                ),
            )
        )
        specs.addStretch(1)
        description = QLabel(
            "Export the mask, keep RGB solid white, and draw only in the alpha "
            "channel. Replace stores your original automatically; Revert removes "
            "only this edit."
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
        self.replace_button.setToolTip("Choose an edited 128×128 RGBA PNG or drop it onto the preview.")
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
        self.export_button.setEnabled(ready)
        self.replace_button.setEnabled(ready)
        self.revert_button.setEnabled(bool(modified))
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
            self.path_note.setText("No source loaded.")
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
        self.run_task(
            "Preparing digital_font preview",
            lambda progress: self.facade.preview_digital_font(progress),
            lambda result: self.preview.set_image(Path(result)),
            False,
        )

    def _export(self) -> None:
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
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose edited 128×128 RGBA digital_font PNG",
            str(Path.home()),
            "RGBA PNG (*.png)",
        )
        if path:
            self._replace_path(Path(path))

    def _replace_path(self, path: Path) -> None:
        if not self.facade.source_ready:
            return
        self.run_task(
            "Replacing digital_font",
            lambda progress: self.facade.replace_digital_font(path, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _revert(self) -> None:
        self.run_task(
            "Reverting digital_font",
            lambda progress: self.facade.revert(DIGITAL_FONT_EDIT_ID, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _mutation_complete(self) -> None:
        self.set_context()
        self.modifiedChanged.emit()


class ApfTeamLogoPanel(QFrame):
    """Focused editor for the offline-proved shared team-logo crest.

    This surface is intentionally self-contained.  It reads the loaded game's
    read-only ``0A`` to render a source-derived preview of ``uniform_logo_01``
    ``logo_l0`` (the shared team-logo texture that is the helmet crest), stages
    exactly one 512x512 RGBA PNG, and presents one "Team Logo" build that runs
    two offline-proved writers in sequence so the edit lands in both places the
    disc stores this crest:

    * ``apf2k8.logos_cards.team_logo`` (``tools/apf_logo_patch.py``) rewrites the
      crest base level inside the ``uniform_logo_01`` package, byte-preserving
      the packed mip tail and the sibling ``logo_l1`` layer;
    * ``apf2k8.logos_cards.team_logo_cache`` (``tools/apf_logocache_patch.py``)
      rewrites the matching catalog entry inside the prebuilt, runtime-resident
      ``uniform_logocache`` aggregate.

    The package write lands in an intermediate copy that the cache write then
    consumes, so the single delivered volume carries both edits.  Each writer
    byte-diffs the whole copied volume so only its own fixed extents change, each
    is paired with an independent verifier, and the retail source is never opened
    for writing.  Either writer failing fails the whole action.

    The panel never mutates the shared editing session, so it never marks
    unrelated project state modified, and it makes no in-game/runtime claim:
    which runtime surface reads which copy -- helmet crest, team-select grid, or
    scorebug -- is not statically recoverable and is unproved without a Xenia
    capture.
    """

    # tools/apf_logo_patch.py is the authority for these pins; the panel mirrors
    # them only for honest, read-only-safe labels and its 512x512 stage guard.
    _OUTER_INDEX = 36
    _INNER_INDEX = 1
    _WIDTH = 512
    _HEIGHT = 512
    _OUTER_NAME = "uniform_logo_01.iff"
    _INNER_NAME = "logo_l0"
    # uniform_logo_01 is catalog index 1 inside uniform_logocache, whose layers
    # are named 01_logo_l0 / 01_logo_l1.  tools/apf_logocache_patch.py re-checks
    # this against its pinned retail directory and payload and fails closed.
    _CACHE_CATALOG_INDEX = 1

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._staged_png: Path | None = None
        self._preview_dir: Path | None = None
        self.setObjectName("panel")
        box = QHBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(16)
        self.preview = ImageDropLabel(
            "Team logo crest · 512×512 RGBA PNG\nLoad your game to see the original."
        )
        self.preview.setFixedSize(220, 220)
        self.preview.pngDropped.connect(self._stage_path)
        box.addWidget(self.preview)

        content = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel("Team logo — shared crest")
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
                    "The writers accept exactly 512×512; any other size is "
                    "refused before anything is staged."
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
        specs.addWidget(
            _spec_pill(
                "Writes package + logo cache",
                tooltip=(
                    "One Team Logo build writes the crest into both places the "
                    "disc stores it: the uniform_logo_01 package (logo_l0) and "
                    "the matching entry of the prebuilt uniform_logocache "
                    "aggregate."
                ),
            )
        )
        specs.addStretch(1)

        slot_row = QHBoxLayout()
        slot_row.setSpacing(8)
        slot_label = QLabel("Team slot:")
        slot_label.setObjectName("metadataText")
        self.slot = QComboBox()
        self.slot.setObjectName("comboField")
        self.slot.addItem(
            "uniform_logo_01 — shared team logo / helmet crest (offline-proved)"
        )
        self.slot.setToolTip(
            "The offline-proved writers own exactly the shared uniform_logo_01 "
            "logo_l0 base level (outer 36 / inner 1) and its matching entry in "
            "the prebuilt logo cache. Additional per-team logo slots are not "
            "proved yet, so only this target is selectable."
        )
        slot_row.addWidget(slot_label)
        slot_row.addWidget(self.slot, 1)

        description = QLabel(
            "This is the shared team-logo texture that serves as the helmet "
            "crest. Drop or choose an exact 512×512 RGBA PNG — colors are stored "
            "at 4 bits per channel, and the build reports exactly how far "
            "quantization moved them. One build writes the crest into both "
            "places the disc stores it. Which screen reads which copy is not "
            "proved without a Xenia capture."
        )
        description.setObjectName("cardBody")
        description.setWordWrap(True)
        description.setToolTip(
            "Full contract: the offline-proved writers own outer 36 / inner 1 "
            "(logo_l0) and the matching uniform_logocache entry. The packed mip "
            "tail and the sibling logo_l1 layer are byte-preserved. Which "
            "runtime surface reads which copy — helmet crest, team-select grid, "
            "or scorebug — is not proved without a Xenia capture."
        )
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
        self.build_button = QPushButton("Build copied 0A (team logo)…")
        self.build_button.setObjectName("secondaryButton")
        self.export_button.setToolTip(
            "Export the current source-derived 512×512 RGBA crest PNG from your game."
        )
        self.replace_button.setToolTip(
            "Choose an edited 512×512 RGBA PNG or drop it onto the preview."
        )
        self.revert_button.setToolTip("Nothing to revert—no replacement is staged.")
        self.build_button.setToolTip(
            "Copy your 0A and write this crest into both the uniform_logo_01 "
            "package and the prebuilt logo cache through the offline-proved "
            "writers and their independent full-volume verifiers."
        )
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
        content.addWidget(description)
        content.addWidget(self.path_note)
        # Keep the edit workflow with its copy; spare height goes below.
        content.addLayout(actions)
        content.addStretch(1)
        box.addLayout(content, 1)
        self.set_context()

    def set_context(self) -> None:
        ready = self.facade.source_ready
        staged = self._staged_png is not None
        self.slot.setEnabled(ready)
        self.export_button.setEnabled(ready)
        self.replace_button.setEnabled(ready)
        self.build_button.setEnabled(ready and staged)
        self.revert_button.setEnabled(staged)
        self.revert_button.setToolTip(
            "Discard the staged replacement PNG and show your original crest again."
            if staged
            else "Nothing to revert—no replacement is staged."
        )
        self.build_button.setToolTip(
            "Copy your 0A and write this crest into both the uniform_logo_01 "
            "package and the prebuilt logo cache through the offline-proved "
            "writers and their independent full-volume verifiers."
            if (ready and staged)
            else "Load your game and stage a 512×512 RGBA PNG to build."
        )
        self.preview.setAcceptDrops(ready)
        if staged and ready:
            self.status.setText("● Staged")
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
                "Team logo crest · 512×512 RGBA PNG\n"
                "Load your game to see the original."
            )
            self.path_note.setText(
                "No game loaded yet — preview, export, and Replace unlock once "
                "your source is recognized."
            )
            return
        if staged:
            self.preview.set_image(self._staged_png)
            self.path_note.setText(
                "Current preview: your staged 512×512 RGBA replacement. Build copies "
                "your 0A and writes only the crest; your source game stays untouched."
            )
            return
        self.preview.set_loading("Decoding the original crest from your game…")
        self.path_note.setText(
            "Current preview: original crest decoded from your own game (read-only)."
        )
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

    def _choose_replacement(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose edited 512×512 RGBA team-logo PNG",
            str(Path.home()),
            "RGBA PNG (*.png)",
        )
        if path:
            self._stage_path(Path(path))

    def _stage_path(self, path: Path) -> None:
        if not self.facade.source_ready:
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.information(
                self,
                "Choose a PNG",
                "That file could not be read as a PNG. Choose a "
                f"{self._WIDTH}×{self._HEIGHT} RGBA PNG and try again.",
            )
            return
        if (pixmap.width(), pixmap.height()) != (self._WIDTH, self._HEIGHT):
            QMessageBox.information(
                self,
                "Wrong PNG size",
                f"The team-logo crest must be exactly {self._WIDTH}×{self._HEIGHT}. "
                f"That PNG is {pixmap.width()}×{pixmap.height()}. The offline-proved "
                "writer will also refuse any other size.",
            )
            return
        self._staged_png = Path(path)
        self.set_context()

    def _revert(self) -> None:
        self._staged_png = None
        self.set_context()

    def _build_copied_volume(self) -> None:
        source = self.facade.source
        if not self.facade.source_ready or source is None or self._staged_png is None:
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
        if (
            out_volume.exists()
            or package_manifest.exists()
            or cache_manifest.exists()
        ):
            QMessageBox.information(
                self,
                "Choose a new location",
                "The proved writers never overwrite existing files. Pick a folder and "
                "name that do not exist yet, then try again.",
            )
            return
        index_path = Path(source.index_0a)
        confirm = QMessageBox.question(
            self,
            "Build copied 0A (team logo)?",
            "This copies your entire ~1.1 GB 0A volume to the chosen path and "
            "replaces the shared team-logo crest in both places the disc stores "
            "it: the uniform_logo_01 package (logo_l0) and the matching entry in "
            "the prebuilt uniform_logocache aggregate. Both writes go through "
            "offline-proved writers; each byte-diffs the whole copied volume so "
            "only its own fixed extents change, and your source game is never "
            "modified.\n\n"
            "This writes only the 0A volume and only this team-logo edit — not other "
            "Mod Studio edits. Boot it alongside your own unmodified game packs.\n\n"
            "The two writes are chained through one intermediate copy, so the "
            "destination needs roughly twice the volume size free while it builds; "
            "the intermediate is removed when the build finishes.\n\n"
            f"Source (read-only): {index_path}\n"
            f"New copied 0A: {out_volume}\n"
            f"Manifests: {package_manifest.name}\n"
            f"           {cache_manifest.name}\n\n"
            "Which runtime surface reads which copy — helmet crest, team-select "
            "grid, or scorebug — is not proved without a Xenia capture.\n\n"
            "Proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        staged = self._staged_png

        def operation(progress: Callable[[str, int, int], None]) -> dict[str, object]:
            # One Team Logo action, two proved writers, through the shared
            # copied-volume builder the facade reuses.  Sibling resolution stays
            # a panel seam so this path keeps its declared-sibling behaviour.
            siblings = self._declared_sibling_packs(index_path)
            return build_team_logo_copied_volume(
                index_path,
                staged,
                out_volume,
                package_manifest,
                cache_manifest,
                progress,
                cache_catalog_index=self._CACHE_CATALOG_INDEX,
                siblings=siblings,
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
        package_manifest = report.get("package_manifest")
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
        evidence = f"Cache manifest:\n{cache_manifest}\n"
        if package_manifest is not None:
            evidence += f"Package manifest:\n{package_manifest}"
        else:
            evidence += (
                "Package manifest: the package-stage evidence copy could not be "
                "written; the copied volume and its cache manifest are unaffected."
            )
        QMessageBox.information(
            self,
            "Copied 0A built",
            "The offline-proved writers copied your 0A and wrote the same crest "
            "into both the uniform_logo_01 package and the prebuilt "
            "uniform_logocache aggregate, each verified against the whole "
            f"volume.\n\nCopied 0A:\n{volume}\n\n{evidence}{detail}\n\n"
            "The two manifests are the evidence chain: the package manifest "
            "covers your game → the intermediate copy, and the cache manifest "
            "covers that copy → this volume. Because this volume carries both "
            "edits, running a single-writer verifier straight from your game to "
            "this volume reports the other writer's extent as unexpected; that is "
            "the verifier's one-writer scope, not a fault in this volume.\n\n"
            "Which runtime surface reads which copy — helmet crest, team-select "
            "grid, or scorebug — is not proved without a Xenia capture.",
        )


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
        self.browser = AssetBrowser(facade, ApfCategory.LOGOS, run_task)
        # Browser edits (e.g. draft_logo) participate in the shared session and
        # mark the project modified; the standalone team-logo crest panel does not.
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        tabs.addTab(self.team_logo, "Team Logo")
        tabs.addTab(self.browser, "All Logo && Team Art")
        layout.addWidget(tabs, 1)

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
        self.browser.set_context()

    def refresh(self) -> None:
        self.team_logo.set_context()
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
        "Endzone base layer. The sibling endzone_l1 layer, the descriptor pad, "
        "and the packed mip tail all stay byte-identical.",
    ),
    _FieldArtTarget(
        6, 1, "endzone_l1", 2048, 512, "DXT1", False,
        "Endzone second layer. The sibling endzone_l0 layer, the descriptor pad, "
        "and the packed mip tail all stay byte-identical.",
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

    Only the six slots proved bit-exact offline are offered.  The deferred
    field-art families (``field_radiance`` and the ``divot_Grass*`` weather
    textures) and the SCNE/CurveAnim rows have no bounded writer and stay
    locked in the inventory browser below.

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
                "The writer accepts exactly this size for the selected texture; "
                "any other size is refused before anything is staged."
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
        self.slot = QComboBox()
        self.slot.setObjectName("comboField")
        for target in FIELD_ART_COVERED_TARGETS:
            self.slot.addItem(target.label)
        self.slot.setToolTip(
            "Only the field-art slots the offline writer proved bit-exact are "
            "selectable. field_radiance (DXT5A) and the divot_Grass* weather "
            "textures (5_6_5) are deferred codecs, and the SCNE/CurveAnim rows "
            "have no serializer, so none of them are offered here."
        )
        slot_row.addWidget(slot_label)
        slot_row.addWidget(self.slot, 1)

        self.description = QLabel("")
        self.description.setObjectName("cardBody")
        self.description.setWordWrap(True)
        self.lock_note = QLabel(
            "Locked for now: field_radiance and the weather divot textures use "
            "codecs that aren't proven yet, so they stay browse & export-only "
            "in the inventory below."
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
        self.set_context()

    def current_target(self) -> _FieldArtTarget:
        index = self.slot.currentIndex()
        if not 0 <= index < len(FIELD_ART_COVERED_TARGETS):
            return FIELD_ART_COVERED_TARGETS[0]
        return FIELD_ART_COVERED_TARGETS[index]

    def staged_path(self, target: _FieldArtTarget) -> Path | None:
        return self._staged.get(target.key)

    def _target_changed(self, _index: int = -1) -> None:
        self.set_context()

    def set_context(self) -> None:
        ready = self.facade.source_ready
        target = self.current_target()
        staged = self.staged_path(target)
        self.slot.setEnabled(ready)
        self.export_button.setEnabled(ready)
        self.replace_button.setEnabled(ready)
        self.build_button.setEnabled(ready and staged is not None)
        self.revert_button.setEnabled(staged is not None)
        self.export_button.setToolTip(
            f"Export the current source-derived {target.width}×{target.height} "
            f"RGBA {target.name} PNG from your game."
            if ready
            else "Load your game to export this texture."
        )
        self.replace_button.setToolTip(
            f"Choose an edited {target.width}×{target.height} RGBA PNG for "
            f"{target.name}, or drop it onto the preview."
            if ready
            else "Load your game to stage a replacement."
        )
        self.revert_button.setToolTip(
            f"Discard the staged replacement PNG and show your original "
            f"{target.name} again."
            if staged is not None
            else "Nothing to revert—no replacement is staged for this texture."
        )
        self.build_button.setToolTip(
            "Copy your 0A and write only this one field-art texture through the "
            "offline-proved writer and its independent verifier."
            if (ready and staged is not None)
            else (
                f"Load your game and stage a {target.width}×{target.height} RGBA "
                "PNG to build."
            )
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
            f"{lead}. Drop or choose an exact {target.width}×{target.height} "
            f"RGBA PNG — any other size is refused. {codec_sentence} Only this "
            "base level changes — the packed mip tail keeps its original bytes — "
            "and how the edit looks in play is not proved without a Xenia "
            "capture."
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
                "your source is recognized."
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
        self, target: _FieldArtTarget, progress: Callable[[str, int, int], None]
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
        else:
            self.preview.set_error(str(value))

    def _export_original(self) -> None:
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
            ok, value = self._decode_source_operation(target, progress)
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
        target = self.current_target()
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose edited {target.width}×{target.height} RGBA {target.name} PNG",
            str(Path.home()),
            "RGBA PNG (*.png)",
        )
        if path:
            self._stage_path(Path(path))

    def _stage_path(self, path: Path) -> None:
        if not self.facade.source_ready:
            return
        target = self.current_target()
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.information(
                self,
                "Choose a PNG",
                "That file could not be read as a PNG. Choose a "
                f"{target.width}×{target.height} RGBA PNG and try again.",
            )
            return
        if (pixmap.width(), pixmap.height()) != (target.width, target.height):
            QMessageBox.information(
                self,
                "Wrong PNG size",
                f"{target.name} must be exactly {target.width}×{target.height}. "
                f"That PNG is {pixmap.width()}×{pixmap.height()}. The "
                "offline-proved writer will also refuse any other size.",
            )
            return
        self._staged[target.key] = Path(path)
        self.set_context()

    def _revert(self) -> None:
        self._staged.pop(self.current_target().key, None)
        self.set_context()

    def _build_copied_volume(self) -> None:
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

    Authorship on this page is exactly the six base-texture slots the offline
    writer proved bit-exact; :class:`ApfFieldArtPanel` owns them and routes
    every write through ``tools/apf_field_art_patch.py``.  Everything else stays
    discovery: each semantic row below is still the original catalog identity
    consumed by :class:`AssetBrowser`, so preview and export keep using the
    existing bounded I/O path, and the page never manufactures selector,
    material, stadium, or team ownership.
    """

    modifiedChanged = pyqtSignal()

    ACTION_LOCK_REASON = (
        "This full Field Art inventory is browse and export-only. The six "
        "offline-proved base textures are edited in the Field Art editor above; "
        "here, archive-package co-location still does not prove the runtime "
        "field material or its team/stadium selector, and the deferred codecs "
        "(field_radiance, the divot_Grass* weather textures) and the "
        "SCNE/CurveAnim rows have no bounded writer at all."
    )

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
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
        semantic_header.addWidget(semantic_title)
        semantic_header.addWidget(self.summary_label)
        semantic_header.addStretch(1)
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
            "This inventory stays browse/export-only; only the six offline-proved "
            "base textures in the Field Art editor above are writable."
        )
        self.browser.set_included_asset_ids(None)

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

    def set_context(self) -> None:
        self.editor.set_context()
        if not self.facade.source_ready:
            self.capabilities.set_cards(())
            self._clear_semantic_view("Load a game to map Field Art")
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
    """Private APF stadium viewer with an explicit unresolved-material boundary."""

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
        self._preview: ApfStadiumPreview | None = None
        self._model: GltfWireframeModel | None = None
        self._scene_generation = 0
        self._texture_generation = 0
        self._source_sha256: str | None = None

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
        self.reset_view_button.setEnabled(False)
        self.export_scene_button.setEnabled(False)
        self.export_scene_button.setToolTip(
            "Export the private raw-coordinate glTF, binary buffer, and evidence manifest."
        )
        view_heading.addLayout(view_titles, 1)
        view_heading.addWidget(self.reset_view_button)
        view_heading.addWidget(self.export_scene_button)
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
        package_title = QLabel("Owning outer package")
        package_title.setObjectName("panelTitle")
        self.package_count = QLabel("0 records")
        self.package_count.setObjectName("countPill")
        package_heading.addWidget(package_title)
        package_heading.addStretch(1)
        package_heading.addWidget(self.package_count)
        self.package_list = QListWidget()
        self.package_list.setObjectName("assetList")
        self.package_list.setSpacing(1)
        self.package_list.setMaximumHeight(190)
        self.package_preview = ImageDropLabel(
            "Choose a package texture to prepare its private PNG preview."
        )
        self.package_preview.setAcceptDrops(False)
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
        self.export_package_button.setEnabled(False)
        self.replace_package_button.setEnabled(False)
        self.revert_package_button.setEnabled(False)
        unresolved = (
            "Coming Soon: surface/material/TXTR ownership and a bounded stadium texture writer are not proved."
        )
        self.replace_package_button.setToolTip(unresolved)
        self.revert_package_button.setToolTip(unresolved)
        package_actions.addWidget(self.export_package_button)
        package_actions.addWidget(self.replace_package_button)
        package_actions.addWidget(self.revert_package_button)
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
        self.export_package_button.clicked.connect(self._export_package_asset)

    def set_context(self) -> None:
        if not self.facade.source_ready:
            self._source_sha256 = None
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
            self._source_sha256 = source_sha
            self._preview = None
            self._model = None
            self._scenes = self.facade.stadium_scenes()
            self._apply_scene_filter()
        elif not self._scenes:
            self._scenes = self.facade.stadium_scenes()
            self._apply_scene_filter()

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
        self.viewport.set_model(None)
        self.scene_title.setText(f"Outer {scene.outer_index} • stadium SCNE")
        self.scene_metadata.setText(
            "Preparing private raw-coordinate geometry from your game…"
        )
        self.surface_identity.setText("No surface selected")
        self.surface_boundary.setText(
            "Texture ownership unresolved. Related package textures are candidates, not surface owners."
        )
        self.reset_view_button.setEnabled(False)
        self.export_scene_button.setEnabled(True)
        self._populate_package(self.facade.stadium_package_assets(scene))

        def operation(progress: Callable[[str, int, int], None]) -> tuple[ApfStadiumPreview, GltfWireframeModel]:
            preview = self.facade.prepare_stadium_scene(scene, progress)
            progress("Building the interactive stadium view", 0, 1)
            model = GltfWireframeModel.load(preview.gltf_path, preview.bin_path)
            progress("Interactive stadium view ready", 1, 1)
            return preview, model

        def complete(result: object) -> None:
            if generation != self._scene_generation:
                return
            preview, model = result  # type: ignore[misc]
            self._preview = preview
            self._model = model
            self.viewport.set_model(model)
            self.reset_view_button.setEnabled(True)
            self.scene_metadata.setText(
                f"{preview.mesh_count:,} meshes • {preview.vertex_count:,} vertices • "
                f"{preview.triangle_count:,} source triangles • "
                f"{preview.skipped_mesh_count:,} unsupported meshes skipped"
            )

        self.run_task("Opening APF Stadium Studio", operation, complete, False)

    def _clear_scene(self, message: str) -> None:
        self._scene_generation += 1
        self._texture_generation += 1
        self._preview = None
        self._model = None
        self.viewport.set_model(None)
        self.scene_title.setText("Choose a stadium scene")
        self.scene_metadata.setText(message)
        self.surface_identity.setText("No surface selected")
        self.reset_view_button.setEnabled(False)
        self.export_scene_button.setEnabled(False)
        self._populate_package(())

    def _surface_selected(self, mesh_index: int, primitive_index: int) -> None:
        model = self._model
        if model is None:
            return
        identity = model.surface_identity(mesh_index, primitive_index)
        if identity is None:
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
        self.surface_boundary.setText(
            "Surface selected, but APF draw/material/TXTR ownership is not decoded. "
            "No package texture was auto-selected and Replace/Revert remain disabled."
        )

    def _populate_package(self, assets: Iterable[ApfAsset]) -> None:
        values = tuple(assets)
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
            self.export_package_button.setEnabled(False)

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
        self.export_package_button.setEnabled(self.facade.source_ready)
        self.replace_package_button.setEnabled(False)
        self.revert_package_button.setEnabled(False)
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

        self.run_task("Preparing stadium package texture", operation, complete, False)

    def _export_scene(self) -> None:
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


class ScorebugStudioPage(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade: ApfStudioFacade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(PageHeading(ApfCategory.SCOREBUG))
        self.capabilities = CapabilityPanel(ApfCategory.SCOREBUG)
        layout.addWidget(self.capabilities)
        tabs = QTabWidget()
        tabs.setObjectName("workspaceTabs")
        self.presentation = InspectorBrowser(
            "Mapped field-scorebug semantics", facade, run_task
        )
        self.digital_font = DigitalFontPanel(facade, run_task)
        self.browser = AssetBrowser(facade, ApfCategory.SCOREBUG, run_task)
        self.digital_font.modifiedChanged.connect(self.modifiedChanged)
        self.browser.modifiedChanged.connect(self.modifiedChanged)
        tabs.addTab(self.presentation, "Presentation Map")
        tabs.addTab(self.digital_font, "Digital Font")
        tabs.addTab(self.browser, "Raw Presentation Assets")
        layout.addWidget(tabs, 1)

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
        self.digital_font.set_context()
        self.browser.set_context()

    def refresh(self) -> None:
        self.presentation.refresh()
        self.digital_font.set_context()
        self.browser.refresh()


class BaseRatingsPanel(QFrame):
    """Searchable exact-value editor for one player's 28 native rating bytes."""

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
        self.search.setPlaceholderText("Search 28 ratings…")
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
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_rating)
        self.revert_button = QPushButton("Revert Rating")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_button.setEnabled(False)
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
        if len(parsed) != 28:
            raise ValueError(f"Player exposes {len(parsed)} base ratings; expected 28")
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
        self.apply_button.setEnabled(False)
        self.revert_button.setEnabled(False)
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
            f"EDITABLE · {len(visible)} / 28"
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
            self.apply_button.setEnabled(False)
            self.revert_button.setEnabled(False)

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
            self.apply_button.setEnabled(False)
            self.revert_button.setEnabled(False)
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
        state = (
            "modified in this project"
            if self._asset_id(self._player_index, field_id)
            in self.facade.modified_asset_ids
            else "original source value"
        )
        self.selected_rating.setText(
            f"{label} · {field_id} · player byte {offset} · exact current "
            f"value {value} · {state}"
        )
        self.revert_button.setEnabled(
            self._asset_id(self._player_index, field_id)
            in self.facade.modified_asset_ids
        )
        self.revert_button.setToolTip(
            "Restore this one rating to the exact value in the loaded source."
            if self.revert_button.isEnabled()
            else "This rating still matches the loaded source."
        )
        self._editor_changed()

    def _editor_changed(self, _value: int = 0) -> None:
        rating = self._selected_rating()
        if rating is None:
            self.apply_button.setEnabled(False)
            return
        field_id = str(rating["id"])
        current = self._current_value(field_id)
        value = self.value_editor.value()
        valid = 0 <= value <= 99
        self.apply_button.setEnabled(valid and value != current)
        self.apply_button.setToolTip(
            "Choose a deliberate value from 0 to 99; native 100 is shown "
            "exactly but is source/revert-only."
            if not valid
            else "This exact value is already active."
            if value == current
            else f"Write exact native value {value} as one reversible project edit."
        )

    def _apply_rating(self) -> None:
        rating = self._selected_rating()
        if (
            rating is None
            or self._player_index is None
            or not self.apply_button.isEnabled()
        ):
            return
        self.applyRequested.emit(
            self._player_index,
            str(rating["id"]),
            self.value_editor.value(),
        )

    def _revert_rating(self) -> None:
        rating = self._selected_rating()
        if (
            rating is None
            or self._player_index is None
            or not self.revert_button.isEnabled()
        ):
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
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_position)
        self.revert_button = QPushButton("Revert Position")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_button.setEnabled(False)
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
        self.apply_button.setEnabled(False)
        self.revert_button.setEnabled(False)
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
            self.apply_button.setEnabled(False)
            self.revert_button.setEnabled(False)
            return
        selected = self.position.currentData()
        if isinstance(selected, bool) or not isinstance(selected, int):
            self.apply_button.setEnabled(False)
            self.apply_button.setToolTip(
                "Choose one of the 17 named positions; free-form codes are not accepted."
            )
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
        self.apply_button.setEnabled(selected != current)
        self.apply_button.setToolTip(
            "This position is already active."
            if selected == current
            else (
                f"Change only this player's position to code {selected} as one "
                "reversible project edit."
            )
        )
        self.revert_button.setEnabled(modified)
        self.revert_button.setToolTip(
            "Restore this player's exact source position."
            if modified
            else "This position still matches the loaded source."
        )

    def _apply_position(self) -> None:
        selected = self.position.currentData()
        if (
            self._player_index is None
            or isinstance(selected, bool)
            or not isinstance(selected, int)
            or not self.apply_button.isEnabled()
        ):
            return
        self.applyRequested.emit(self._player_index, selected)

    def _revert_position(self) -> None:
        if self._player_index is None or not self.revert_button.isEnabled():
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
        self.save_button.setEnabled(
            bool(encoder_value)
            and (
                not windows_encoder
                or (
                    self.use_wine_checkbox.isChecked()
                    and bool(self.wine_path.text().strip())
                )
            )
        )

    def _accept_configuration(self) -> None:
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
        self.export_ratings_sheet_button.setEnabled(False)
        self.export_ratings_sheet_button.setToolTip(
            "Export all 2,254 players and all 28 exact base ratings as one "
            "private CSV. It contains data derived from your game copy and "
            "never enters a shareable project."
        )
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
        self.import_ratings_sheet_button.setEnabled(False)
        self.import_ratings_sheet_button.setToolTip(
            "Ctrl+Shift+I · Choose a private Mod Studio ratings CSV, validate every row without "
            "changing the project, then review replacements, source reverts, "
            "unchanged cells, conflicts, and errors before an explicit Apply."
        )
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
            self.soundtrack_album_button.setEnabled(False)
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
        self.export_complete_audio_catalog_button.setEnabled(False)
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
        self.export_original_audio_banks_button.setEnabled(False)
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
        self.export_audio_replacement_template_button.setEnabled(False)
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
        self.import_audio_replacement_pack_button.setEnabled(False)
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
        self.load_waveform_button.setEnabled(False)
        self.load_waveform_button.setToolTip(
            "Explicitly decode this one sound to a verified session-private WAV, then "
            "draw it without playing it. No source or project data is written."
        )
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
        self.play_audio_button.setEnabled(False)
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
        self.export_external_bank_button.setEnabled(False)
        self.export_external_bank_button.setToolTip(
            "Copy this exact physical multi-cue XMA1 packet bank. It is not one playable sound."
        )
        self.export_external_bank_button.clicked.connect(
            self._export_external_audio_bank
        )
        self.export_matching_button = QPushButton("Export matching sounds…")
        self.export_matching_button.setObjectName("secondaryButton")
        self.export_matching_button.setVisible(audio_mode)
        self.export_matching_button.setEnabled(False)
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
        self.export_pcm_template_button.setEnabled(False)
        self.export_pcm_template_button.setAccessibleName(
            "Export exact PCM authoring template for this APF sound"
        )
        self.export_pcm_template_button.setToolTip(
            "Export a retail-free, exact-length PCM16 silence WAV. Paint it with "
            "your sound editor, then return it with Replace from PCM WAV."
        )
        self.export_pcm_template_button.clicked.connect(
            self._export_audio_pcm_template
        )
        self.replace_pcm_audio_button = QPushButton("Replace from PCM WAV…")
        self.replace_pcm_audio_button.setObjectName("primaryButton")
        self.replace_pcm_audio_button.setVisible(audio_mode)
        self.replace_pcm_audio_button.setEnabled(False)
        self.replace_pcm_audio_button.setAccessibleName(
            "Replace this APF sound from an exact PCM WAV"
        )
        self.replace_pcm_audio_button.setToolTip(
            "Encode an exact-shape PCM16 WAV with your configured external XMA1 "
            "encoder, then stage it only after every exact-slot gate passes."
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
        self.replace_audio_button.setEnabled(False)
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
        self.revert_audio_button.setEnabled(False)
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
        self.shortlist_toggle_button = QPushButton("Add selected sound")
        self.shortlist_toggle_button.setObjectName("secondaryButton")
        self.shortlist_toggle_button.setVisible(audio_mode)
        self.shortlist_toggle_button.setEnabled(False)
        self.shortlist_toggle_button.clicked.connect(self._toggle_audio_shortlist)
        self.shortlist_page_button = QPushButton("Add this page")
        self.shortlist_page_button.setObjectName("secondaryButton")
        self.shortlist_page_button.setVisible(audio_mode)
        self.shortlist_page_button.setEnabled(False)
        self.shortlist_page_button.clicked.connect(self._add_visible_audio_to_shortlist)
        self.shortlist_matching_button = QPushButton("Add all matching")
        self.shortlist_matching_button.setObjectName("secondaryButton")
        self.shortlist_matching_button.setVisible(audio_mode)
        self.shortlist_matching_button.setEnabled(False)
        self.shortlist_matching_button.setAccessibleName(
            "Add every matching playable sound to the audio shortlist"
        )
        self.shortlist_matching_button.setAccessibleDescription(
            "Adds every playable sound matching the applied search and filters, "
            "in game catalog order. Sounds already selected are kept once."
        )
        self.shortlist_matching_button.setToolTip(
            "Apply a search or filter to add all of its playable sounds at once."
        )
        self.shortlist_matching_button.clicked.connect(
            self._add_matching_audio_to_shortlist
        )
        self.shortlist_clear_button = QPushButton("Clear")
        self.shortlist_clear_button.setObjectName("dangerQuietButton")
        self.shortlist_clear_button.setAccessibleName("Clear audio shortlist")
        self.shortlist_clear_button.setVisible(audio_mode)
        self.shortlist_clear_button.setEnabled(False)
        self.shortlist_clear_button.clicked.connect(self._clear_audio_shortlist)
        self.shortlist_count = QLabel("Selected 0 / 256")
        self.shortlist_count.setObjectName("countPill")
        self.shortlist_count.setVisible(audio_mode)
        self.shortlist_review_button = QPushButton("Review selected")
        self.shortlist_review_button.setObjectName("secondaryButton")
        self.shortlist_review_button.setVisible(audio_mode)
        self.shortlist_review_button.setEnabled(False)
        self.shortlist_review_button.clicked.connect(self._toggle_audio_review)
        self.shortlist_move_up_button = QPushButton("Move up")
        self.shortlist_move_up_button.setObjectName("secondaryButton")
        self.shortlist_move_up_button.setVisible(audio_mode)
        self.shortlist_move_up_button.setEnabled(False)
        self.shortlist_move_up_button.clicked.connect(
            lambda: self._move_shortlisted_audio(-1)
        )
        self.shortlist_move_down_button = QPushButton("Move down")
        self.shortlist_move_down_button.setObjectName("secondaryButton")
        self.shortlist_move_down_button.setVisible(audio_mode)
        self.shortlist_move_down_button.setEnabled(False)
        self.shortlist_move_down_button.clicked.connect(
            lambda: self._move_shortlisted_audio(1)
        )
        self.export_shortlist_button = QPushButton("Export selected sounds…")
        self.export_shortlist_button.setObjectName("primaryButton")
        self.export_shortlist_button.setVisible(audio_mode)
        self.export_shortlist_button.setEnabled(False)
        self.export_shortlist_button.setToolTip(
            "Add up to 256 sounds from any search, page, or bank first."
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
        self.apply_text_button.setEnabled(False)
        self.revert_text_button = QPushButton("Revert Text")
        self.revert_text_button.setObjectName("dangerQuietButton")
        self.revert_text_button.setVisible(text_mode)
        self.revert_text_button.setEnabled(False)
        self.export_text_sheet_button = QPushButton("Export Text Sheet…")
        self.export_text_sheet_button.setObjectName("secondaryButton")
        self.export_text_sheet_button.setVisible(text_mode)
        self.export_text_sheet_button.setEnabled(False)
        self.export_text_sheet_button.setToolTip(
            "Create a private CSV containing every owned TXT/STRG allocation from your loaded game."
        )
        self.import_text_sheet_button = QPushButton("Import Text Sheet…")
        self.import_text_sheet_button.setObjectName("secondaryButton")
        self.import_text_sheet_button.setVisible(text_mode)
        self.import_text_sheet_button.setEnabled(False)
        self.import_text_sheet_button.setToolTip(
            "Validate an APF Text Sheet completely, then apply every requested row as one Undo action."
        )
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
        self.roster_aliases_button.setEnabled(False)
        self.roster_aliases_button.setAccessibleName(
            "Review every roster field affected by this shared name allocation"
        )
        self.roster_aliases_button.clicked.connect(
            self._show_roster_alias_owners
        )
        self.apply_roster_name_button = QPushButton("Replace Name")
        self.apply_roster_name_button.setObjectName("primaryButton")
        self.apply_roster_name_button.setVisible(roster_mode)
        self.apply_roster_name_button.setEnabled(False)
        if roster_mode and not roster_writes_enabled:
            self.apply_roster_name_button.setToolTip(
                ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
        self.revert_roster_name_button = QPushButton("Revert Name")
        self.revert_roster_name_button.setObjectName("dangerQuietButton")
        self.revert_roster_name_button.setVisible(roster_mode)
        self.revert_roster_name_button.setEnabled(False)
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
                roster_ratings_page, "Base Ratings (28)"
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
        try:
            current = self._external_xma1_encoder()
        except Exception:
            # Corrupt local preferences must never strand the Audio panel. A
            # fresh valid selection replaces them only after dialog validation.
            current = None
        dialog = ExternalXma1EncoderDialog(
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
                else ("{input}", "{output}")
            ),
            timeout_seconds=(
                int(current.timeout_seconds) if current is not None else 600
            ),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        encoder = dialog.encoder
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
        self.export_pcm_template_button.setEnabled(
            editable and not mutation_busy
        )
        self.export_pcm_template_button.setVisible(
            self.audio_mode and not self._pcm_encoding_running
        )
        self.replace_pcm_audio_button.setEnabled(
            editable and not mutation_busy
        )
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
        self.replace_audio_button.setEnabled(
            editable and not mutation_busy
        )
        self.replace_audio_button.setText(
            "Replace XMA1 again…" if editable and modified else "Replace with XMA1…"
        )
        self.revert_audio_button.setEnabled(
            editable and modified and not mutation_busy
        )
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
                "or use Replace with XMA1 when you already have a finished stream. "
                f"No encoder ships with Mod Studio. {state} Every final XMA1 result "
                "must pass a complete decode, all packet checks, both source-audio "
                "fingerprint sets, and the exact slot shape. The project stores only "
                "the accepted replacement stream—not the encoder, input PCM, or a "
                "source-packet backup—"
                f"and leaves the source game untouched.{shared_note}{decoder_note}"
            )
            self.export_pcm_template_button.setToolTip(
                f"Export an exact {rate:,} Hz {channel_label} PCM16 silence WAV for "
                "this slot. The template contains no retail audio."
            )
            self.replace_pcm_audio_button.setToolTip(
                f"Choose an exact {rate:,} Hz {channel_label} PCM16 WAV. Your external "
                "encoder runs privately; its final output must fit exactly "
                f"{size:,} encoded bytes and pass every slot gate."
            )
            self.replace_audio_button.setToolTip(
                f"Import pre-encoded RIFF XMA1 with exactly {size:,} encoded bytes, "
                f"{rate:,} Hz, and {channel_label}; the same exact-slot gates still apply."
            )
            self.revert_audio_button.setToolTip(
                "Remove this one staged sound replacement and use the untouched source audio."
                if modified
                else "This sound has no staged replacement."
            )
            return
        self.replace_audio_button.setToolTip(
            "Choose one individual AUDO or AUSB sound. AUSB index rows and complete "
            "physical banks are containers, so they remain export-only."
        )
        self.export_pcm_template_button.setToolTip(
            "Choose one individual AUDO or AUSB sound before exporting its exact PCM template."
        )
        self.replace_pcm_audio_button.setToolTip(
            "Choose one individual AUDO or AUSB sound before importing an authored PCM WAV."
        )
        self.revert_audio_button.setToolTip(
            "Choose a modified individual AUDO or AUSB sound first."
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
            self.load_waveform_button.setEnabled(False)
            return
        self.load_waveform_button.setText("Load waveform")
        if row is None:
            self.waveform_preview.set_unavailable(
                "Choose an individual AUDO or AUSB sound."
            )
            self.load_waveform_button.setEnabled(False)
            return
        if row.kind == "external_bank" or row.external_bank_identity is not None:
            self.waveform_preview.set_unavailable(
                "A physical external bank contains many packetized sounds and is not "
                "one playable waveform. Choose one of its AUSB substream rows."
            )
            self.load_waveform_button.setEnabled(False)
            return
        if row.kind == "ausb_bank":
            self.waveform_preview.set_unavailable(
                "This is a bank index, not one sound. Choose an individual substream."
            )
            self.load_waveform_button.setEnabled(False)
            return
        if not self._waveform_row_is_playable(row):
            self.waveform_preview.set_unavailable(
                "This decoded row has no verified playable WAV route."
            )
            self.load_waveform_button.setEnabled(False)
            return
        self.waveform_preview.set_empty(
            "Waveforms are not loaded automatically. Click Load waveform to decode "
            "this sound privately; playback will not start."
        )
        self.load_waveform_button.setEnabled(True)
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
            self.load_waveform_button.setEnabled(False)
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
        self.soundtrack_album_button.setEnabled(
            loaded and album_available and not self._audio_review_mode
        )
        self.soundtrack_album_button.setToolTip(
            "Return to the complete audio browser with its filters, page, and selection intact."
            if self._soundtrack_album_mode
            else "Open the 15 bank-indexed soundtrack tracks; stereo masters are the default and mono companions remain one selector away."
            if album_available
            else "This source does not expose the exact proved pair: 15 jukeboxmusic stereo streams and 15 jukebox22 mono companions."
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
        self.export_external_bank_button.setEnabled(False)
        self.play_audio_button.setEnabled(False)
        self._configure_audio_waveform(None)
        self._configure_audio_replacement(None)
        self.export_rows_button.setEnabled(False)
        self.export_complete_audio_catalog_button.setEnabled(False)
        self.export_original_audio_banks_button.setEnabled(False)
        self.export_audio_replacement_template_button.setEnabled(False)
        self.import_audio_replacement_pack_button.setEnabled(False)
        self.cancel_audio_import_button.setEnabled(False)
        self.cancel_audio_export_button.setEnabled(False)
        self.export_matching_button.setEnabled(False)
        self.export_text_sheet_button.setEnabled(False)
        self.import_text_sheet_button.setEnabled(False)
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
        self.export_external_bank_button.setEnabled(False)
        self.play_audio_button.setEnabled(False)
        self._configure_audio_waveform(None)
        self._configure_audio_replacement(None)
        self.export_rows_button.setEnabled(False)
        self.export_complete_audio_catalog_button.setEnabled(False)
        self.export_original_audio_banks_button.setEnabled(False)
        self.export_audio_replacement_template_button.setEnabled(False)
        self.import_audio_replacement_pack_button.setEnabled(False)
        self.cancel_audio_import_button.setEnabled(False)
        self.cancel_audio_export_button.setEnabled(False)
        self.export_matching_button.setEnabled(False)
        self.export_text_sheet_button.setEnabled(False)
        self.import_text_sheet_button.setEnabled(False)
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
        self.export_ratings_sheet_button.setEnabled(self.roster_mode)
        self.import_ratings_sheet_button.setEnabled(self.roster_mode)
        self._update_bulk_audio_export_controls()
        self.export_text_sheet_button.setEnabled(self.text_mode)
        self.import_text_sheet_button.setEnabled(self.text_mode)
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
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.export_rows_button.setEnabled(False)
        self._update_matching_audio_action()
        self._update_audio_shortlist_actions()

    def _restore_applied_audio_query_presentation(self) -> None:
        """Restore controls when fast type/erase returns to the shown query."""

        if self._applied_audio_count_text:
            self.count.setText(self._applied_audio_count_text)
        if self._applied_audio_page_text:
            self.page.setText(self._applied_audio_page_text)
        ready = self._audio_pagination_ready()
        self.previous.setEnabled(self._applied_audio_previous_available and ready)
        self.next.setEnabled(self._applied_audio_next_available and ready)
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
                        status = "Position + 28 base ratings editable · " + (
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
        self.previous.setEnabled(
            page.previous_offset is not None and pagination_ready
        )
        self.next.setEnabled(page.next_offset is not None and pagination_ready)
        if self.audio_mode:
            self.export_rows_button.setEnabled(
                self.model is not None
                and (
                    self._audio_review_mode
                    or self._soundtrack_album_mode
                    or self._audio_catalog_query_is_current()
                )
            )
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
            self.export_external_bank_button.setEnabled(False)
            self.play_audio_button.setEnabled(False)
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
            finding = row.fields.get("jersey_number_edit_status")
            finding = finding if isinstance(finding, dict) else {}
            result = str(
                finding.get(
                    "result",
                    "No consumer-backed jersey-number field has been mapped.",
                )
            )
            self.roster_boundary_note.setText(
                (
                    "Player names, all 28 native base ratings, and all 17 exact "
                    "position choices are editable in separate tabs. Position "
                    "changes do not move team membership or depth-chart slots. "
                    "Names keep their exact source limits; shared allocations "
                    "change every affected field together. Jersey number remains "
                    "read-only / unmapped."
                )
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
            self.roster_boundary_note.setToolTip(
                "Dan CODEX rendered in player selection and the Star Card. The "
                "token-preserving Speed candidate also loaded normally, but APF "
                "showed stars rather than a numeric rating readout. "
                f"{result} {finding.get('best_next_experiment', '')}"
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
            self.apply_roster_name_button.setEnabled(False)
            self.revert_roster_name_button.setEnabled(False)
            self.roster_aliases_button.setText("View affected fields…")
            self.roster_aliases_button.setToolTip("")
            self.roster_aliases_button.setEnabled(False)

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
            self.apply_roster_name_button.setEnabled(False)
            self.revert_roster_name_button.setEnabled(False)
            self.roster_aliases_button.setText("View affected fields…")
            self.roster_aliases_button.setToolTip("")
            self.roster_aliases_button.setEnabled(False)
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
        self.revert_roster_name_button.setEnabled(modified)
        self.revert_roster_name_button.setText(
            f"Revert {scope_label}"
            if edit_scope is not None
            else "Revert Locked Edit"
            if modified
            else "Revert (Locked)"
        )
        self.revert_roster_name_button.setToolTip(
            "Restore this one shared name allocation to the source value."
            if modified
            else "This name allocation is still original."
        )
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
        self.apply_roster_name_button.setEnabled(False)
        self.revert_roster_name_button.setEnabled(False)
        self.roster_aliases_button.setText("View affected fields…")
        self.roster_aliases_button.setToolTip("")
        self.roster_aliases_button.setEnabled(False)
        if self.roster_detail_tabs is not None:
            self.roster_detail_tabs.setCurrentIndex(0)
            self.roster_detail_tabs.setTabEnabled(1, False)
            self.roster_detail_tabs.setTabEnabled(2, False)

    def _roster_editor_changed(self, _value: str = "") -> None:
        if not self.roster_mode:
            return
        selected = self._selected_roster_field()
        if selected is None:
            self.apply_roster_name_button.setEnabled(False)
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
        self.apply_roster_name_button.setEnabled(valid and value != current)
        self.apply_roster_name_button.setToolTip(
            (
                self._roster_locked_field_reason(row, field_name, allocation)
                if self.roster_writes_enabled
                else ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE
            )
            if not product_editable
            else error
            or (
                f"Replace this {self._roster_field_label(field_name).casefold()} "
                f"using {units} of {limit} UTF-16 characters as one Undo step."
            )
        )
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
        selected = self._selected_roster_field()
        if selected is None or not self.apply_roster_name_button.isEnabled():
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
        selected = self._selected_roster_field()
        if selected is None or not self.revert_roster_name_button.isEnabled():
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
        self.revert_text_button.setEnabled(
            row.row_id in self.facade.modified_asset_ids
        )
        self.revert_text_button.setToolTip(
            "Restore this one string allocation to the source value."
            if self.revert_text_button.isEnabled()
            else "This allocation is still original."
        )
        self._text_editor_changed()

    def _clear_text_editor(self, message: str) -> None:
        if not self.text_mode:
            return
        self.text_editor.blockSignals(True)
        self.text_editor.clear()
        self.text_editor.blockSignals(False)
        self.text_editor.setEnabled(False)
        self.text_limit.setText(message)
        self.apply_text_button.setEnabled(False)
        self.revert_text_button.setEnabled(False)

    def _text_editor_changed(self) -> None:
        if not self.text_mode:
            return
        row = self._selected_row()
        allocation = self._text_allocations.get(row.row_id) if row else None
        if allocation is None or not bool(getattr(allocation, "editable")):
            self.apply_text_button.setEnabled(False)
            return
        value = self.text_editor.toPlainText()
        units = len(value.encode("utf-16be")) // 2
        limit = int(getattr(allocation, "maximum_utf16_units"))
        current = self.facade.localization_text_value(row.row_id)
        valid = "\0" not in value and units <= limit
        self.apply_text_button.setEnabled(valid and value != current)
        color = "#39d98a" if valid else "#ff6b7a"
        self.apply_text_button.setToolTip(
            f"Apply {units} of {limit} UTF-16 units to this allocation."
            if valid
            else f"This text needs {units} UTF-16 units; the limit is {limit}."
        )
        self.text_editor_label.setText(f"Replacement  •  {units}/{limit} UTF-16 units")
        self.text_editor_label.setStyleSheet(f"color: {color};")

    def _apply_text(self) -> None:
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
        if self._audio_review_mode:
            self.export_matching_button.setEnabled(False)
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setToolTip(
                "Review is already the exact hand-picked set. Use Export selected sounds, or return to the browser for a filtered export."
            )
            return
        if (
            not self._soundtrack_album_mode
            and not self._audio_catalog_query_is_current()
        ):
            self.export_matching_button.setEnabled(False)
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setToolTip(
                "Updating results. This action unlocks when the visible page matches the search and filters."
            )
            return
        count = len(self._matching_audio_rows())
        enabled = 1 <= count <= 256
        self.export_matching_button.setEnabled(enabled)
        if enabled:
            self.export_matching_button.setText(
                f"Export soundtrack version ({count})…"
                if self._soundtrack_album_mode
                else f"Export matching sounds ({count})…"
            )
            self.export_matching_button.setToolTip(
                f"Export these {count} soundtrack tracks as one transactional XMA or verified-WAV ZIP."
                if self._soundtrack_album_mode
                else f"Export these {count} filtered sounds as one transactional XMA or verified-WAV ZIP."
            )
        else:
            self.export_matching_button.setText("Export matching sounds…")
            self.export_matching_button.setToolTip(
                "No playable sounds match."
                if count == 0
                else f"{count:,} playable sounds match; narrow search, kind, role, or source to 256 or fewer."
            )

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
        self.play_audio_button.setEnabled(
            bool(
                selected
                and selected.export_identity is not None
                and selected.external_bank_identity is None
            )
        )
        self.play_audio_button.setToolTip(
            "Decode a session-private, verified WAV and play it with ffplay, paplay, or aplay."
        )

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
        self.export_complete_audio_catalog_button.setEnabled(
            loaded and not self._audio_export_running
        )
        self.export_original_audio_banks_button.setText(
            f"Export all original banks ({bank_count})…"
            if bank_count
            else "Export all original banks…"
        )
        self.export_original_audio_banks_button.setEnabled(
            bank_count > 0 and not self._audio_export_running
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
                "rate, or length, then choose Replace from PCM WAV."
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
        """Resolve one valid local encoder or explain the non-mutating refusal."""

        try:
            encoder = self._external_xma1_encoder()
            if encoder is None:
                raise ValueError("No external XMA1 encoder is configured")
            encoder.validate()
        except Exception as exc:
            QMessageBox.information(
                self,
                "Configure an XMA1 encoder first",
                (
                    f"{exc}\n\nChoose Configure XMA1 encoder, select your own "
                    "installed tool, and save it. No encoder ships with Mod Studio, "
                    "and no project data changed."
                ),
            )
            self._update_audio_encoder_status()
            return None
        return encoder

    def _replace_audio_from_pcm(self) -> None:
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
            "Choose your exact PCM WAV for this APF sound",
            str(Path.home()),
            "PCM16 WAV audio (*.wav)",
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
        if path.suffix.casefold() != ".wav":
            QMessageBox.information(
                self,
                "Choose a PCM WAV file",
                "This authoring route accepts PCM16 .wav files. FLAC, MP3, WMA, "
                "and xWMA are not accepted; convert them to the exact template "
                "shape first.",
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
        if suffix == ".wav":
            encoder = self._configured_audio_encoder_for_replace()
            if encoder is not None:
                self._replace_audio_pcm_path(row, path, encoder)
            return
        QMessageBox.information(
            self,
            "Drop an XMA or PCM WAV file",
            "This drop target accepts one local .xma or exact PCM16 .wav file. "
            "FLAC, MP3, WMA, folders, links, and multiple files are not accepted.",
        )

    def _pcm_audio_mutation_complete(self, row_id: str) -> None:
        self._audio_mutation_complete(row_id)
        QMessageBox.information(
            self,
            "PCM WAV replacement staged",
            (
                "The user-supplied encoder output passed the exact allocation, "
                "packet, complete-decode, duration, source-fingerprint, and shared-"
                "owner gates. The untouched source game was not modified.\n\n"
                "The encoder binary/path and input PCM remain outside this shareable "
                "mod project; the project contains only the accepted replacement stream."
            ),
        )

    def _replace_audio(self) -> None:
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
        model = self.model
        if model is None:
            return
        if self.audio_mode and not self._audio_catalog_query_is_current():
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
                f"Saved all 2,254 players × 28 exact ratings to:\n{Path(result)}\n\n"
                "This CSV contains retail-derived names and values from your own game. "
                "Keep it private; share Mod Studio projects, not this sheet.",
            ),
            True,
        )

    def _import_player_rating_sheet(self) -> None:
        """Validate a private CSV first; never mutate from the file chooser."""

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
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.page.setText("Page 0 of 0")
        self.export_rows_button.setEnabled(self.model is not None)
        self.export_ratings_sheet_button.setEnabled(
            self.roster_mode and self.model is not None
        )
        self.import_ratings_sheet_button.setEnabled(
            self.roster_mode and self.model is not None
        )
        self._update_bulk_audio_export_controls()
        if self.model is None:
            self.play_audio_button.setEnabled(False)
            self.export_bank_button.setVisible(False)
            self.export_external_bank_button.setVisible(False)
            self.export_external_bank_button.setEnabled(False)
            self.export_matching_button.setEnabled(False)


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
        self.workspace_tabs: QTabWidget | None = None
        self.inspector.modifiedChanged.connect(self.modifiedChanged)
        self.inspector.audioAnnotationChanged.connect(
            lambda _row_id: self.modifiedChanged.emit()
        )
        if self.assets is not None:
            self.assets.modifiedChanged.connect(self.modifiedChanged)
        if not include_assets:
            layout.addWidget(self.inspector, 1)
        elif category in {
            ApfCategory.MENUS,
            ApfCategory.AUDIO,
            ApfCategory.ROSTERS,
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
                tabs.addTab(self.roster_planner, "53-player Planner")  # type: ignore[arg-type]
                tabs.addTab(self.assets, "&Raw Roster Assets")  # type: ignore[arg-type]
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
        elif normalized == "roster-planner" and self.category is ApfCategory.ROSTERS:
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
            self.uniform_button.setEnabled(False)
            return
        catalog = facade.require_catalog()
        self.ready_title.setText("Your game is indexed and ready")
        self.ready_body.setText(
            f"{catalog.outer_count:,} outer records and {len(catalog.assets):,} total assets are visible. "
            f"{len(catalog.uniform_assets)} uniform textures, digital_font, and draft_logo are editable now."
        )
        self.uniform_button.setEnabled(True)


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
        self.setMinimumSize(1180, 720)
        self._build_ui()
        self._build_menu()
        self._install_keyboard_shortcuts()
        self._apply_style()
        self._update_product_state()
        self._activate_page(0, force=True)
        if offer_recovery and self.workspace_store is not None:
            QTimer.singleShot(0, self._offer_startup_recovery)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
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
        self._build_pages()
        workspace_layout.addWidget(self.pages, 1)
        workspace_layout.addWidget(self._build_footer())
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

    def _install_keyboard_shortcuts(self) -> None:
        """Expose the shell navigation even when focus is deep in an editor."""

        self.find_shortcut = QShortcut(QKeySequence.Find, self)
        self.find_shortcut.setContext(Qt.WindowShortcut)
        self.find_shortcut.activated.connect(self._focus_current_search)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.sidebar_shortcut.setContext(Qt.WindowShortcut)
        self.sidebar_shortcut.activated.connect(self._focus_category_navigation)

    def _focus_category_navigation(self) -> None:
        self.navigation.setFocus(Qt.ShortcutFocusReason)

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
            "Search ready • type to filter this workspace"
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
        self.page_eyebrow = QLabel("ALL-PRO FOOTBALL 2K8 • MODDING WORKSPACE")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel(ApfCategory.GETTING_STARTED.title)
        self.page_title.setObjectName("pageTitle")
        titles.addWidget(self.page_eyebrow)
        titles.addWidget(self.page_title)
        layout.addLayout(titles)
        layout.addStretch(1)
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
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(8)
        status_box = QVBoxLayout()
        status_box.setSpacing(5)
        self.operation_status = QLabel("Load your APF game to begin.")
        self.operation_status.setObjectName("operationStatus")
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
        self.build_button = QPushButton("Build Game Folder")
        self.build_button.setObjectName("buildButton")
        self.launch_button = QPushButton("Launch in Xenia")
        self.launch_button.setObjectName("launchButton")
        self.undo_button.setToolTip("Undo the most recent edit in this project.")
        self.revert_all_button.setToolTip("Nothing to revert—there are no active edits.")
        self.configure_xenia_button.setToolTip("Choose Xenia Canary and its Wine launcher.")
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
        self.build_button.setAccessibleName("Build a separate modded game folder")
        self.build_button.setAccessibleDescription(self.build_button.toolTip())
        self.launch_button.setAccessibleName("Launch the latest build in Xenia")
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        self.undo_button.clicked.connect(self._undo)
        self.revert_all_button.clicked.connect(self._revert_all)
        self.configure_xenia_button.clicked.connect(self._configure_xenia)
        self.build_button.clicked.connect(self._build_game)
        self.launch_button.clicked.connect(self._launch_xenia)
        layout.addWidget(self.modified_count)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.revert_all_button)
        layout.addSpacing(4)
        layout.addWidget(self.configure_xenia_button)
        layout.addSpacing(4)
        layout.addWidget(self.build_button)
        layout.addWidget(self.launch_button)
        return footer

    def _run_task(
        self,
        label: str,
        operation: Callable[[Callable[[str, int, int], None]], Any],
        on_success: Callable[[Any], None] | None = None,
        blocking: bool = True,
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
            lambda message, detail, task=worker: self._task_failed(task, message, detail)
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

    def _task_failed(self, _worker: _BackgroundTask, message: str, detail: str) -> None:
        self._last_detail = message
        self._show_error(message, detail)

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
        dialog.setText(message)
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
        self.build_button.setEnabled(ready and not blocking)
        self.launch_button.setEnabled(self.facade.can_launch_xenia and not blocking)
        self.build_button.setToolTip(
            "Create a separate, verified modded game folder. Your source stays untouched."
            if ready
            else "Load your APF game before building."
        )
        self.launch_button.setToolTip(
            "Launch the most recently built game folder in Xenia."
            if self.facade.can_launch_xenia
            else "Build a game folder and configure Xenia before launching."
        )
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
        parent = QFileDialog.getExistingDirectory(
            self,
            "Choose where the new modded game folder should be created",
            str(Path.home()),
            QFileDialog.ShowDirsOnly,
        )
        if not parent:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        parent_path = Path(parent)
        output = parent_path / f"APF2K8-Mod-{timestamp}"
        suffix = 2
        while output.exists():
            output = parent_path / f"APF2K8-Mod-{timestamp}-{suffix}"
            suffix += 1
        self._run_task(
            "Building a complete separate APF game folder",
            lambda progress: self.facade.build(output, progress),
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
            f"Created:\n{output}\n\n"
            f"Applied {changed} edit{'s' if changed != 1 else ''}. The complete output was verified and your source stayed untouched.\n\n"
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
        if executable.suffix.casefold() == ".exe" and shutil.which("wine") is None:
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

    def _launch_xenia(self) -> None:
        if not self.facade.can_launch_xenia:
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
            QTableWidget#assetTable, QTableWidget#fieldArtGroupTable {
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
    application.setApplicationName(PRODUCT_NAME)
    application.setOrganizationName(PRODUCT_NAME)
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
    "ScorebugStudioPage",
    "StadiumStudioPage",
    "StudioMainWindow",
    "UniformStudioPage",
    "launch_studio",
]
