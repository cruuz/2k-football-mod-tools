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
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable
from uuid import uuid4
import weakref

from PyQt5.QtCore import (
    QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, QUrl, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QCloseEvent, QDesktopServices, QFont, QIcon, QImageReader,
    QKeySequence, QPainter, QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
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
from mod_editor.core.nfl2k5_stadium_cache import (
    ESTIMATED_PRIVATE_BYTES,
    ESTIMATED_SECONDS_HIGH,
    ESTIMATED_SECONDS_LOW,
)
from mod_editor.core.errors import ValidationError
from mod_editor.core import update_check
from mod_editor.core.texture_master import (
    AuthoringTransform,
    fit_transform as texture_master_fit_transform,
    snapshot_texture_master_source,
)
from mod_editor.gui import branding
from mod_editor.gui.ux_text import XEMU_LINE, Details, tab_title  # noqa: F401
from mod_editor.core import mod_build
from mod_editor.gui import crash_report
from mod_editor.gui import update_ui
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.nfl2k5_uniform_catalog import (
    ASSETS_PER_SET,
    Nfl2k5UniformCatalog,
    UniformAsset,
    UniformSet,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    ExtendedVisualAsset,
    Nfl2k5ExtendedVisualCatalog,
    VisualWriterRoute,
    load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_universal_asset_index import UniversalAssetRecord
from mod_editor.core.nfl2k5_stadium_studio import (
    EDITABLE as STADIUM_EDITABLE,
    StadiumGltfTextureWriteBack,
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
from mod_editor.gui.bump_panel_qt import BumpPanel
from mod_editor.gui.save_panel_qt import SavePanel
from mod_editor.gui.crib_panel_qt import CribPanel
from mod_editor.gui.gameplay_panel_qt import GameplayPanel
from mod_editor.gui.throw_tuning_panel_qt import ThrowTuningPanel
from mod_editor.gui.presentation_panel_qt import PresentationPanel
from mod_editor.gui.share_panel_qt import SharePanel
from mod_editor.gui.commentary_panel_qt import CommentaryPanel
from mod_editor.gui.sounds_panel_qt import SoundsPanel
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.models_panel_qt import ModelsPanel
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
from mod_editor.gui.gameplay_patches_panel_qt import TEXT_PATCHES, GameplayPatchesPanel
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
from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST
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

#: Shown on the Build button whenever it is usable.
BUILD_READY_MESSAGE = (
    "Make a separate modded disc from your project edits (art, text, audio). "
    "Your original game file is never changed."
)

CHECK_IMAGES_MESSAGE = (
    "Try every staged image against the exact slot it has to fit, and say "
    "which ones come through untouched, which lose colours, and which will "
    "not fit at all. Nothing is changed and no build is started."
)

#: What actually costs a replacement its palette. Said in the panel because the
#: intuitive fix -- shrink the image -- does nothing: the editor resizes to the
#: slot either way, and it is the number of distinct shades that has to fit.
CHECK_IMAGES_ADVICE = (
    "What costs palette here is the number of distinct shades in your art, not "
    "its resolution — the editor resizes to the slot either way. Flat team "
    "colours fit; photographic noise, dithering, and long smooth gradients are "
    "what force a reduction."
)

# Pillow normalizes these formats to the exact RGBA PNG the disc writer needs.
# Keep the file chooser and drag/drop admission on one list so neither path can
# regress to accepting only already-perfect PNGs.
IMAGE_IMPORT_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga",
})
IMAGE_IMPORT_FILTER = (
    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)"
)

# macOS writes a hidden AppleDouble twin (``._name``) next to a file copied off
# an archive or another volume.  The twin keeps the image's extension, so it
# passes the suffix check and then fails decoding with jargon; name it plainly.
APPLE_DOUBLE_DROP_REFUSAL = (
    "That is a macOS resource-fork file (._name), not the image. Drop the "
    "visible PNG instead."
)


def _is_apple_double_path(path: Path) -> bool:
    return Path(path).name.startswith("._")


# Plain-language "what to do next" for the writers' exact-slot refusals.  The
# fail-closed behaviour never changes -- the same bytes are still refused --
# but the GUI pairs each refusal with the fix a first-time modder should try.
_FIX_HINTS: tuple[tuple[str, str], ...] = (
    (
        "needs a PNG that is exactly",
        "Fix: use that asset's Replace button and drop any image — Mod Studio "
        "resizes it to the slot's exact size for you.",
    ),
    (
        "must stay",
        "Fix: that image has the wrong dimensions for this slot. Import it "
        "through its panel and let Mod Studio resize it to the exact slot size.",
    ),
    (
        "needs a PNG file",
        "Fix: choose an image file — PNG, JPEG, BMP, GIF, WebP or TGA. Any "
        "size works; the editor resizes it for you.",
    ),
    (
        "Live face/head textures must be fully opaque",
        "Fix: this portrait slot stores opaque pixels. Flatten the image's "
        "transparency, then try again.",
    ),
    (
        "is not a RIFF/WAVE file",
        "Fix: install FFmpeg and drop ordinary audio (MP3, FLAC, OGG, M4A) to "
        "have it converted, or supply a PCM16 WAV that already matches this "
        "slot's exact channels, sample rate and length.",
    ),
    (
        "WAV must be canonical",
        "Fix: this slot needs one exact shape. Install FFmpeg and drop ordinary "
        "audio to have it converted, or re-export the PCM authoring template.",
    ),
    (
        "WAV must contain exactly",
        "Fix: this slot needs one exact shape. Install FFmpeg and drop ordinary "
        "audio to have it converted, or re-export the PCM authoring template.",
    ),
)


def friendly_fix_hint(message: str) -> str | None:
    """Return the plain next-step for a known refusal, or None."""

    lowered = message.casefold()
    for needle, hint in _FIX_HINTS:
        if needle.casefold() in lowered:
            return hint
    return None


def _build_blocker_message(*, ready: bool, edit_count: int, busy: bool) -> str:
    """Explain why Build is unavailable, or describe it when it is.

    Build is disabled until a disc is loaded and at least one edit exists, which
    is correct -- but a disabled button with a fixed tooltip explains nothing, and
    pressing it produces no dialog and no status change.  A modder reported being
    unable to rebuild the XISO at all; the builder itself is fine (a real 6.3 GB
    source rebuilds and independently verifies), so the failure being reported is
    this silence.  Ordered most-blocking first, because that is the one the user
    has to clear next.
    """

    if busy:
        return (
            "Wait for the current operation to finish, then Build. "
            "Only one long operation runs at a time."
        )
    if not ready:
        return "Open your game disc first (top right). Make disc from project needs a disc to copy."
    if edit_count <= 0:
        return (
            "Add at least one project edit: Replace a PNG, edit a string, or pick "
            "a colour. For gameplay patches, use ★ Build & Share."
        )
    return BUILD_READY_MESSAGE


def _plain_launch_blocker(text: str) -> str:
    """The facade's launch blocker in the words the footer uses (Set up xemu…, Make a disc)."""

    if not text:
        return ""
    lowered = text.casefold()
    if "not found" in lowered:
        return "xemu was not found. Install it, or use Set up xemu… to tell the app where it is."
    if "not one yet" in lowered or "first" in lowered:
        return "Make a disc first. Play starts the most recently made disc."
    if "no longer at" in lowered:
        return text.replace("Build again, then launch.", "Make it again, then play.")
    return text


def _window_icon() -> QIcon | None:
    """Return the bundled application icon, or None if it is unavailable."""
    return branding.app_icon("2k5-mod-studio")


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

    @property
    def xemu_blocker(self) -> str: ...

    def configure_xemu(self, executable: Path) -> tuple[str, ...]: ...

    def load_source(self, source_xiso: Path, progress: ProgressSink) -> object: ...

    def preview_asset(self, asset: UniformAsset, progress: ProgressSink) -> Path: ...

    def export_asset(
        self, asset: UniformAsset, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def replace_asset(
        self, asset: UniformAsset, supplied_png: Path, progress: ProgressSink
    ) -> object: ...

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
        native_baseline_png: Path | None,
        progress: ProgressSink,
    ) -> Path: ...

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

    def uniform_colors(
        self, selector: str, progress: ProgressSink
    ) -> tuple[str, str, bool]: ...

    def set_uniform_colors(
        self, selector: str, facemask: str, turtleneck: str,
        progress: ProgressSink,
    ) -> tuple[str, str, bool]: ...

    def clear_uniform_colors(
        self, selector: str, progress: ProgressSink
    ) -> bool: ...

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

    def preflight_visual_edits(self, progress: ProgressSink) -> object: ...

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

    def export_playbook_link_table_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def export_playbook_package_map_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def export_g1_dime_from_nickel_package_map_pack(
        self,
        asset_id: str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def export_g2_ace_from_quads_link_table_pack(
        self,
        asset_id: str,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def copy_play_assignment_route(
        self,
        asset_id: str,
        target_play_index: int,
        target_slot_index: int,
        donor_play_index: int,
        donor_slot_index: int,
        progress: ProgressSink,
    ) -> object: ...

    def revert_play_assignment_route(
        self,
        asset_id: str,
        target_play_index: int,
        target_slot_index: int,
        progress: ProgressSink,
    ) -> object: ...

    def create_formation(
        self, asset_id: str, donor_formation_index: int, progress: ProgressSink,
    ) -> object: ...

    def create_play(
        self, asset_id: str, donor_play_index: int, progress: ProgressSink,
    ) -> object: ...

    def revert_formation_create(
        self, selector: str, progress: ProgressSink,
    ) -> object: ...

    def revert_play_create(
        self, selector: str, progress: ProgressSink,
    ) -> object: ...

    def create_formation_link(
        self, asset_id: str, formation_index: int, play_index: int,
        group: int | None = None, progress: ProgressSink = ...,
    ) -> object: ...

    def revert_formation_link(
        self, selector: str, progress: ProgressSink,
    ) -> object: ...

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

    def export_stadium_scene_gltf(
        self, scene_id: str, destination: Path, progress: ProgressSink,
    ) -> tuple[Path, Path]: ...

    def import_stadium_scene_gltf(
        self, scene_id: str, source: Path, progress: ProgressSink,
    ) -> object: ...

    def replace_stadium_textures_from_gltf(
        self, scene_id: str, source: Path, progress: ProgressSink,
    ) -> tuple[StadiumGltfTextureWriteBack, ...]: ...

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

    @property
    def modified_crib_model_scene_ids(self) -> Iterable[str]:
        return self._host.modified_crib_model_scene_ids

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

    def list_crib_model_scenes(self) -> Iterable[dict[str, object]]:
        return self._host.list_crib_model_scenes()

    def export_crib_model(
        self, scene_id: str, destination: Path, progress: ProgressSink
    ) -> tuple[Path, Path]:
        return self._host.export_crib_model(scene_id, destination, progress)

    def import_crib_model(
        self, scene_id: str, edited_gltf: Path, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "import a Crib model")
        return self._host.import_crib_model(scene_id, edited_gltf, progress)

    def revert_crib_model(
        self, scene_id: str, progress: ProgressSink
    ) -> object:
        self._require_mutation_admission(self._requester, "revert a Crib model")
        return self._host.revert_crib_model(scene_id, progress)


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
    xemu_blocker = (
        "The editing backend is not connected in this build, so there is "
        "nothing to launch. Browsing every catalog entry still works."
    )

    @staticmethod
    def _unavailable(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(
            "The editing backend is not connected in this build. "
            "You can still browse every catalog entry."
        )

    load_source = _unavailable
    preview_asset = _unavailable
    export_asset = _unavailable
    save_texture_authoring_master = _unavailable
    replace_asset = _unavailable
    revert_asset = _unavailable
    export_team_kit_sets = _unavailable
    export_team_kit = _unavailable
    import_team_kit = _unavailable
    uniform_colors = _unavailable
    set_uniform_colors = _unavailable
    clear_uniform_colors = _unavailable
    undo = _unavailable
    revert_all = _unavailable
    save_project = _unavailable
    save_recovery_project = _unavailable
    load_project = _unavailable
    resource_kinds = _unavailable
    browse_resources = _unavailable
    export_resource = _unavailable
    preflight_visual_edits = _unavailable
    export_gameplay_inspection = _unavailable
    export_main_menu_inspection = _unavailable
    browse_playbooks = _unavailable
    export_playbook = _unavailable
    export_playbook_link_table_copy = _unavailable
    export_playbook_package_map_copy = _unavailable
    export_g1_dime_from_nickel_package_map_pack = _unavailable
    export_g2_ace_from_quads_link_table_pack = _unavailable
    copy_play_assignment_route = _unavailable
    revert_play_assignment_route = _unavailable
    create_formation = _unavailable
    create_play = _unavailable
    revert_formation_create = _unavailable
    revert_play_create = _unavailable
    create_formation_link = _unavailable
    revert_formation_link = _unavailable
    playbook_raw_body = _unavailable
    stage_formation_selector = _unavailable
    create_authored_play = _unavailable
    playbook_teams = _unavailable
    load_playbook_pack = _unavailable
    preview_playbook_pack = _unavailable
    install_playbook_pack = _unavailable
    export_playbook_pack = _unavailable
    stadium_scenes = _unavailable
    stadium_details = _unavailable
    preview_stadium_texture = _unavailable
    export_stadium_texture = _unavailable
    export_stadium_scene_gltf = _unavailable
    import_stadium_scene_gltf = _unavailable
    replace_stadium_textures_from_gltf = _unavailable
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
    modified_crib_model_scene_ids: frozenset[str] = frozenset()
    preview_crib_asset = _unavailable
    export_crib_asset = _unavailable
    replace_crib_photo = _unavailable
    revert_crib_photo = _unavailable
    export_crib_model = _unavailable
    import_crib_model = _unavailable
    revert_crib_model = _unavailable
    modified_audio_asset_ids: frozenset[str] = frozenset()
    audio_editing_ready = False
    stadium_available = False
    playbook_available = False
    build_iso = _unavailable
    launch_xemu = _unavailable
    configure_xemu = _unavailable

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

    @staticmethod
    def list_crib_model_scenes() -> tuple[dict[str, object], ...]:
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
    status_pill: "_StatusPill"
    preview: "_PngDropPreview"
    help_label: QLabel
    export_button: QPushButton
    master_button: QPushButton
    edit_button: QPushButton
    replace_button: QPushButton
    revert_button: QPushButton
    selected_asset_id: str | None = None


@dataclass(frozen=True)
class _TextureMasterDraft:
    source_image: Path
    source_sha256: str
    native_baseline_png: Path
    transform: AuthoringTransform
    editor_transform: Mapping[str, object]
    native_canvas_edited: bool = False


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
    selected_scene_id: str | None = None
    scenes_loaded: bool = False
    scenes_loading: bool = False
    generation: int = 0
    editable_only: QCheckBox | None = None


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
    if category == ProductCategory.ROSTERS_PLAYERS:
        # display only: the catalog title stays "Rosters & Players"; the page edits names,
        # numbers and images, and a second page called Rosters confused people (RP-01)
        return "Names, Numbers & Faces"
    return catalog.section(category).title


# Capabilities that really do have controls somewhere in the app. Anything
# absent from this map and marked as a writer is honest about being
# command-line only, rather than showing an "Editable" pill over a page with
# nothing on it.
_WORKSPACE_CAPABILITIES = {
    "nfl2k5.uniforms.all_visual": "Uniform Sets",
    "nfl2k5.colors.unif_words": "Colours & Other Tools",
    # Team Select cards are three of the Team Kit's 39 per-set components
    # (uniform_card_256, helmet_card_256, helmet_card_128), so they are edited
    # in the same browser rather than from a command line.
    "nfl2k5.logos.team_select_cards": "Uniform Sets",
    "nfl2k5.portraits_faces.roster_portraits": "Portraits & Faces",
    "nfl2k5.portraits_faces.live_textures": "Portraits & Faces",
    "nfl2k5.stadiums.create_team_field_art": "Field Art & Create-Team Art",
    "nfl2k5.scorebug_presentation.inventory": "Presentation",
    "nfl2k5.crib.assets": "The Crib",
    "nfl2k5.audio.audo_wav": "Audio",
    # The Stadiums page exports the pinned scene to glTF, imports same-topology
    # vertex moves, and applies Blender-edited glTF textures back, so the card
    # points at that workspace instead of the command line.
    "nfl2k5.stadiums.geometry": "Stadiums",
    "nfl2k5.textures.all_p8": "All Textures",
}


def _suggested_png_name(identifier: str) -> str:
    """A save-dialog default that is a legal filename on every platform.

    Windows rejects <>:"/\\|?* outright, so an asset id containing any of them
    produced "The file name is not valid." the moment Export PNG opened. The
    All Textures ids are ``p8:<package>:<texture>`` and hit it immediately, but
    the rule is general: an identifier is not a filename, and only the id kinds
    that happened to be dot-separated were safe before.

    Trailing dots and spaces are also stripped, and the reserved DOS device
    names are prefixed, because Windows refuses those too.
    """
    cleaned = "".join(
        "-" if character in '<>:"/\\|?*' or ord(character) < 32 else character
        for character in identifier
    ).replace(".", "-").strip(" .")
    cleaned = cleaned or "asset"
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{digit}" for digit in range(1, 10)),
        *(f"LPT{digit}" for digit in range(1, 10)),
    }
    if cleaned.upper() in reserved:
        cleaned = f"_{cleaned}"
    return f"{cleaned}.png"


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
    if binding.status in {
        ProductStatus.COMING_SOON,
        ProductStatus.RESEARCH,
    } and isinstance(portme, list):
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
        ProductStatus.EVIDENCE: "#9aa8bd",
        ProductStatus.RESEARCH: "#91a0b5",
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
        self._replacement_enabled = True
        self.setMinimumSize(200, 200)
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
        if self._replacement_enabled:
            note = "drag an edited image here"
        else:
            note = "Preview / Export only"
        self.hint.setText(f"{image.width()} × {image.height()} PNG  •  {note}")
        return True

    def set_replacement_enabled(self, enabled: bool) -> None:
        """Keep drag/drop behavior and its on-screen promise in sync."""

        self._replacement_enabled = enabled
        self.setAcceptDrops(enabled)
        if enabled:
            self.hint.setText("Image preview  •  drag an edited image here to replace")
        else:
            self.hint.setText("Preview / Export only")

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
        if mime.hasUrls() and mime.urls():
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
        path = Path(url.toLocalFile())
        if _is_apple_double_path(path):
            QMessageBox.information(
                self,
                "That drop can't be used yet",
                APPLE_DOUBLE_DROP_REFUSAL,
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        if path.suffix.casefold() not in IMAGE_IMPORT_EXTENSIONS:
            QMessageBox.information(
                self,
                "That drop can't be used yet",
                "That file is not an image this panel can read. Drop a PNG, "
                "JPEG, BMP, GIF, WebP or TGA image — any size is fine, the "
                "editor resizes it for you.",
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        self.png_dropped.emit(path)
        event.acceptProposedAction()  # type: ignore[attr-defined]


class _StatusPill(QLabel):
    def __init__(self, text: str, color: str) -> None:
        super().__init__()
        self.setProperty("pill", True)
        self.set_status(text, color)

    def set_status(self, text: str, color: str) -> None:
        self.setText(text)
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
        # Where resized copies live for this session. Created lazily so a
        # user who never needs a resize never gets a temp directory.
        self._fit_dir: Path | None = None
        # Full-resolution source snapshots are private, session-lifetime files.
        # They are never embedded in .2k5mod v1 projects; an explicit export is
        # the only route into a shareable .2ktexmaster archive.
        self._texture_master_temp = tempfile.TemporaryDirectory(
            prefix="2k5-texture-masters-"
        )
        # QMainWindow wrappers can participate in Qt/Python reference cycles,
        # so relying on TemporaryDirectory.__del__ produces ResourceWarnings
        # and may leave full-resolution authoring snapshots around until a GC
        # pass.  This later-created finalizer runs first and calls the normal,
        # idempotent cleanup path even when a test or host drops the window
        # without delivering closeEvent.
        self._texture_master_finalizer = weakref.finalize(
            self, self._texture_master_temp.cleanup
        )
        self._texture_master_root = Path(self._texture_master_temp.name)
        self._texture_master_drafts: dict[str, _TextureMasterDraft] = {}
        self._universal_browser: _UniversalBrowserState | None = None
        self._stadium_browser: _StadiumBrowserState | None = None
        self._audio_panel: AudioPanel | None = None
        self._bump_panel: BumpPanel | None = None
        self._save_panel: SavePanel | None = None
        self._text_roster_panel: TextRosterPanel | None = None
        self._roster_panel: TextRosterPanel | None = None
        self._crib_panel: CribPanel | None = None
        self._playbooks_panel: PlaybooksPanel | None = None
        self._gameplay_panel: GameplayPanel | None = None
        self._throw_tuning_panel: ThrowTuningPanel | None = None
        self._gameplay_patches_panel: GameplayPatchesPanel | None = None
        self._edge_panel: GameplayPatchesPanel | None = None
        self._presentation_panel: PresentationPanel | None = None
        self._commentary_panel: CommentaryPanel | None = None
        self._build_panel: BuildPanel | None = None
        self._star_players_connected = False
        # E2: the open-disc hook.  A generation counter drops inspection results
        # of a disc that was superseded by a later open; the roster page loads
        # lazily on first entry so an edited roster is never reset by navigation.
        self._source_generation = 0
        self._source_inspect_pending = False
        self._roster_prefill_pending = False
        self._last_prefilled_source: Path | None = None
        self._share_panel: SharePanel | None = None
        self._sounds_panel: SoundsPanel | None = None
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
        # The shell now fits its own content at about 1,092 px wide, so the
        # floor no longer has to be 1,180. A 1366-wide laptop is a normal
        # machine for this audience and the window must fit on one.
        self.setMinimumSize(1040, 600)
        self.resize(1480, 920)
        self.setObjectName("studioWindow")
        self._build_ui()
        self._build_file_menu()
        self._install_keyboard_shortcuts()
        self._apply_style()
        self._populate_uniform_filters()
        self._filter_uniforms()
        self._refresh_edit_state()
        if bool(getattr(self.facade, "source_ready", False)):
            self._load_selected_unif_colors()
        # After the window is up, never during construction: a slow network
        # must not delay the app appearing.
        QTimer.singleShot(1200, self._start_automatic_update_check)
        if offer_recovery and self.workspace_store is not None:
            QTimer.singleShot(0, self._offer_startup_recovery)

    @property
    def sidebar_category_order(self) -> tuple[str, ...]:
        return sidebar_category_titles(self.product_catalog)

    def _build_file_menu(self) -> None:
        """Expose recent files and recovery without adding header clutter."""

        file_menu = self.menuBar().addMenu("&File")
        self._open_source_action = file_menu.addAction("Open game disc…")
        self._open_source_action.setShortcut("Ctrl+O")
        self._open_source_action.triggered.connect(self._choose_source)
        self._open_project_action = file_menu.addAction("Open project…")
        self._open_project_action.setShortcut("Ctrl+Shift+O")
        self._open_project_action.triggered.connect(self._choose_project)
        self._recent_source_menu = file_menu.addMenu("Recent discs")
        self._recent_project_menu = file_menu.addMenu("Recent projects")
        file_menu.addSeparator()
        self._save_project_action = file_menu.addAction("Save project")
        self._save_project_action.setShortcut("Ctrl+S")
        self._save_project_action.triggered.connect(self._save_project)
        self._save_project_as_action = file_menu.addAction("Save project as…")
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
        self._install_help_menu()

    def _install_help_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        check_action = help_menu.addAction("Check for Updates…")
        check_action.triggered.connect(self._check_for_updates_now)
        self._auto_update_action = help_menu.addAction(
            "Check for updates automatically"
        )
        self._auto_update_action.setCheckable(True)
        self._auto_update_action.setChecked(
            update_ui.automatic_checks_enabled()
        )
        self._auto_update_action.toggled.connect(
            update_ui.set_automatic_checks_enabled
        )
        help_menu.addSeparator()
        discord_action = help_menu.addAction("Join the Discord…")
        discord_action.setToolTip("Opens the community Discord invite in your browser.")
        discord_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(update_check.COMMUNITY_DISCORD))
        )
        releases_action = help_menu.addAction("Downloads and release notes…")
        releases_action.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(update_check.RELEASES_PAGE)
            )
        )

    def _check_for_updates_now(self) -> None:
        """A manual check always answers, even to say nothing changed."""

        self._set_status("Checking for updates…")
        update_ui.start_check(
            update_check.BUILD_RELEASE_TAG, self._manual_update_result
        )

    def _manual_update_result(self, status: object) -> None:
        self._set_status("")
        if getattr(status, "available", False):
            self._update_banner.show_status(status)
        update_ui.report_manual_check(self, status, self._update_banner)

    def _start_automatic_update_check(self) -> None:
        """Quiet on startup: only a genuinely newer release shows anything."""

        if not update_ui.automatic_checks_enabled():
            return
        update_ui.explain_automatic_checks_once(self)
        update_ui.start_check(
            update_check.BUILD_RELEASE_TAG, self._update_banner.show_status
        )

    def _install_keyboard_shortcuts(self) -> None:
        """Keep the two most-used navigation targets one keystroke away."""

        self.find_shortcut = QShortcut(QKeySequence.Find, self)
        self.find_shortcut.setContext(Qt.WindowShortcut)
        self.find_shortcut.activated.connect(self._focus_current_search)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.sidebar_shortcut.setContext(Qt.WindowShortcut)
        self.sidebar_shortcut.activated.connect(self._focus_category_navigation)
        self.clear_search_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.clear_search_shortcut.setContext(Qt.WindowShortcut)
        self.clear_search_shortcut.activated.connect(self._clear_current_search)
        self.help_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        self.help_shortcut.setContext(Qt.WindowShortcut)
        self.help_shortcut.activated.connect(self._show_keyboard_hints)

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
            else f"{owner} finished — project actions are available again."
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
        self._set_status(
            "Search ready • type to filter • Esc clears • Ctrl+/ keyboard help"
        )

    def _clear_current_search(self) -> None:
        """Clear the focused or page search field on Escape."""

        focused = self.focusWidget()
        field = self._current_search_field()
        if isinstance(focused, QLineEdit) and focused.text():
            focused.clear()
            self._set_status("Search cleared")
            return
        if field is not None and field.text():
            field.clear()
            field.setFocus(Qt.ShortcutFocusReason)
            self._set_status("Search cleared")

    def _show_keyboard_hints(self) -> None:
        self._set_status(
            "Keys: Ctrl+F search · Esc clear · Ctrl+1 categories · "
            "Ctrl+O open XISO · Ctrl+S save project · Ctrl+/ this help"
        )

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
                empty = self._recent_source_menu.addAction("No recent discs")
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
        # The update strip sits above everything and stays hidden unless a newer
        # release exists, so the normal window is unchanged.
        shell = QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self._update_banner = update_ui.UpdateBanner(product="2k5")
        shell.addWidget(self._update_banner)
        body = QWidget()
        shell.addWidget(body, 1)
        root_layout = QHBoxLayout(body)
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
            if category is ProductCategory.FIELD_ART_CREATE_TEAM:
                item.setToolTip("The field art of the game's own Create-a-Team teams (fictional logos by design). "
                                "Real NFL end zones and midfield art live under All Textures / Stadiums.")
            self.navigation.addItem(item)
        roster_item = QListWidgetItem("  ★ Rosters")
        roster_item.setData(Qt.UserRole, "rosters")
        roster_item.setSizeHint(QSize(210, 44))
        roster_item.setToolTip("Edit a disc roster or Xbox save: players, ratings, equipment, contracts and depth order.")
        self.navigation.addItem(roster_item)
        models_item = QListWidgetItem("  ★ Models")
        models_item.setData(Qt.UserRole, "models")
        models_item.setSizeHint(QSize(210, 44))
        models_item.setToolTip("Export a 3D model for Blender, check an edited one, and write it into a disc copy.")
        self.navigation.addItem(models_item)
        create_item = QListWidgetItem("  ★ Create a Play")
        create_item.setData(Qt.UserRole, "create_play")
        create_item.setSizeHint(QSize(210, 44))
        create_item.setToolTip("Five steps: pick a playbook, line up a formation, choose run or pass, draw routes, place the play.")
        self.navigation.addItem(create_item)
        build_item = QListWidgetItem("  ★ Build & Share")
        build_item.setData(Qt.UserRole, "build_share")
        build_item.setSizeHint(QSize(210, 44))
        build_item.setToolTip("Choose patches, make a disc copy, or export and install mod files.")
        self.navigation.addItem(build_item)
        side_layout.addWidget(self.navigation, 1)

        safety = QLabel(
            "ORIGINAL STAYS SAFE\nKeep your original disc. Check the destination "
            "before writing a copy."
        )
        safety.setObjectName("safetyCard")
        safety.setWordWrap(True)
        safety.setAccessibleName("Source safety")
        safety.setAccessibleDescription(
            "The original game disc is opened read-only; check the destination before writing a copy."
        )
        side_layout.addWidget(safety)
        root_layout.addWidget(sidebar)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._build_header())

        # The footer owns the status line, progress bar, and the Undo/Revert
        # controls that _refresh_action_states touches. Pages are built next,
        # and an embedded panel constructed against an already-loaded game
        # reports its state during construction -- which reached those widgets
        # before they existed and took the window down before it appeared.
        footer = self._build_footer()

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
                ProductCategory.TEXTURES: frozenset({
                    "p8_texture", "uniform_equipment_texture",
                }),
            }.get(category)
            if category == ProductCategory.UNIFORMS_EQUIPMENT:
                # The uniform browser is built around one capability
                # (nfl2k5.uniforms.all_visual). Every other capability filed
                # under Uniforms & Equipment -- the facemask/turtleneck packed
                # colours and the Team Select cards among them -- used to be
                # dropped on the floor here, so enabling one changed nothing a
                # modder could see and the only honest answer to "where is it?"
                # was "nowhere". They get their own tab, the same shape Rosters
                # & Players already uses for its two workspaces.
                uniform_tabs = QTabWidget()
                uniform_tabs.setObjectName("uniformsEquipmentTabs")
                uniform_tabs.setAccessibleName("Uniforms and equipment workspaces")
                uniform_tabs.addTab(self._build_uniform_page(section), tab_title("Uniform Sets"))
                uniform_tabs.addTab(
                    self._build_colors_page(section), tab_title("Colours & Other Tools")
                )
                self._bump_panel = BumpPanel(self.facade)
                uniform_tabs.addTab(self._bump_panel, "Bump Maps (advanced)")
                # The uniform browser is why people open this page; never let a
                # newly added tab take the landing position away from it.
                uniform_tabs.setCurrentIndex(0)
                page = uniform_tabs
            elif category == ProductCategory.TEXTURES:
                # This category shipped as a bare capability card with nothing
                # to click. It gets the same browser every other visual family
                # uses: search, preview, Export/Replace PNG, Revert.
                if visual_kinds is None:
                    raise RuntimeError("All Textures visual kinds are unavailable")
                page = self._build_visual_page(section, visual_kinds)
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
                self._connect_star_players()
                roster_tabs = QTabWidget()
                roster_tabs.setObjectName("rostersPlayersTabs")
                roster_tabs.setAccessibleName("Rosters and players workspaces")
                roster_tabs.addTab(self._roster_panel, tab_title("Names & Numbers"))
                roster_tabs.addTab(portrait_page, tab_title("Portraits & Faces"))
                # "Which face is this player?" had no answer in the app: faces
                # are found by a face_id buried in the roster record and filed
                # under a number, so the only method was scrolling 1,872
                # textures hoping a label matched.
                roster_tabs.addTab(self._build_player_assets_page(), "Find player images")
                page = roster_tabs
            elif category == ProductCategory.TEAM_IDENTITY:
                self._text_roster_panel = TextRosterPanel(
                    text_specialist_host,
                    view="text",
                    on_status=self._specialized_panel_status,
                    on_refresh=self._specialized_panel_refresh,
                )
                # The DE -> EDGE rename is a text patch (executable position
                # tables + the disc's text spans), so it lives with the other
                # text tools rather than under Gameplay.
                identity_tabs = QTabWidget()
                identity_tabs.setObjectName("teamIdentityTabs")
                identity_tabs.setAccessibleName("Text and team identity workspaces")
                identity_tabs.addTab(self._text_roster_panel, "Game Text")
                self._edge_panel = GameplayPatchesPanel(
                    self.facade, patches=TEXT_PATCHES, title="Position names",
                    intro="Change what the game calls positions and write one copy. "
                          "For presets and other changes, use ★ Build & Share.",
                    target_suffix="position names",
                )
                identity_tabs.addTab(self._edge_panel, "Position Names (EDGE)")
                identity_tabs.setCurrentIndex(0)
                page = identity_tabs
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
            elif category == ProductCategory.SCOREBUG_PRESENTATION:
                # Presentation = the scorebug texture inventory plus the two
                # writable presentation workspaces: the ESPN horizontal
                # scorebug/ticker re-layout and commentary line swaps.  Both
                # write a copy of the disc, never the source.
                if visual_kinds is None:
                    raise RuntimeError("Presentation visual kinds are unavailable")
                presentation_tabs = QTabWidget()
                presentation_tabs.setObjectName("presentationTabs")
                presentation_tabs.setAccessibleName("Presentation workspaces")
                presentation_tabs.addTab(self._build_visual_page(section, visual_kinds), "Scorebug Images")
                self._presentation_panel = PresentationPanel(self.facade)
                presentation_tabs.addTab(self._presentation_panel, "ESPN Scorebug && Ticker")
                self._commentary_panel = CommentaryPanel(self.facade)
                presentation_tabs.addTab(self._commentary_panel, "Commentary")
                presentation_tabs.setCurrentIndex(0)
                page = presentation_tabs
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
                self._audio_panel.setToolTip("Browse, preview, export and replace supported audio — drop any common file (MP3, WAV, FLAC, OGG, M4A); it is converted to the slot's exact shape when FFmpeg is available.")
                self._audio_panel.setAccessibleDescription("Audio workspace: searchable playable cues and ranges with replace support for exact-slot standalone and streaming-range sounds.")
                # Sounds: the rotating SFX banks (hits, whistles, crowd
                # reactions, QB cadence) and the standalone AUDO cues,
                # replaced through the soundbank/audo swap tools into a COPY
                # of the disc -- the same shape Presentation uses for its
                # copy-writing workspaces.
                audio_tabs = QTabWidget()
                audio_tabs.setObjectName("audioTabs")
                audio_tabs.setAccessibleName("Audio workspaces")
                audio_tabs.addTab(self._audio_panel, tab_title("Music & Sounds"))
                self._sounds_panel = SoundsPanel(self.facade)
                audio_tabs.addTab(self._sounds_panel, "Replace a Sound")
                audio_tabs.setCurrentIndex(0)
                page = audio_tabs
            elif category == ProductCategory.PLAYBOOKS_PLAYS:
                self._playbooks_panel = PlaybooksPanel(self.facade)
                page = self._playbooks_panel
            elif category == ProductCategory.SLIDERS_GAMEPLAY:
                # Throw Distance & Arc is the one writable workspace on this
                # page: two sliders over the game's own arm-strength curve
                # tables, written to a COPY of default.xbe (xemu-only), the
                # same contract Bump strength ships under.
                self._throw_tuning_panel = ThrowTuningPanel(self.facade)
                # Gameplay Patches: the executable caves (Catching/Interception
                # sliders, acceleration ramp, franchise draft AI) with their
                # explanations, written through mod_build.
                self._gameplay_patches_panel = GameplayPatchesPanel(self.facade)
                # The Xbox save editor (sliders + franchise year) is a gameplay tool, not a
                # uniform tool: one instance, moved here from Uniforms & Equipment (GP-02).
                self._save_panel = SavePanel(self.facade)
                self._gameplay_panel = GameplayPanel(
                    self.facade,
                    capability_page=self._build_capability_page(section),
                    extra_tabs=((self._gameplay_patches_panel, "Game Fixes"),
                                (self._throw_tuning_panel, "Throw Distance && Arc"),
                                (self._save_panel, tab_title("Saves & Sliders"))),
                )
                page = self._gameplay_panel
            else:
                page = self._build_capability_page(section)
            self._category_pages[category] = page
            self.pages.addWidget(self._page_scroll_host(page))
        self._roster_editor_panel = RosterEditorPanel(self.facade)
        self.pages.addWidget(self._page_scroll_host(self._roster_editor_panel))
        self._models_panel = ModelsPanel(self.facade)
        self.pages.addWidget(self._page_scroll_host(self._models_panel))
        self._create_play_page = self._build_create_play_page()
        self.pages.addWidget(self._page_scroll_host(self._create_play_page))
        self._build_share_page = self._build_build_share_page()
        self.pages.addWidget(self._page_scroll_host(self._build_share_page))
        workspace_layout.addWidget(self.pages, 1)
        workspace_layout.addWidget(footer)
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
        self.source_pill = QLabel("●  No disc open")
        self.source_pill.setObjectName("sourcePill")
        self.source_pill.setAccessibleName("Loaded game status")
        self.source_pill.setToolTip(
            "The game disc the app is reading. Click Open game disc… to change it."
        )
        self.source_pill.setAccessibleDescription(self.source_pill.toolTip())
        self.open_project_button = QPushButton("Open project…")
        self.open_project_button.setObjectName("secondaryButton")
        self.open_project_button.setToolTip(
            "Open a .2k5mod project saved earlier: your replacement images, text and "
            "audio, never game data. Open your game disc first."
        )
        self.open_project_button.setAccessibleName("Open a 2K5 Mod Studio project")
        self.open_project_button.setAccessibleDescription(
            self.open_project_button.toolTip()
        )
        self.open_project_button.clicked.connect(self._choose_project)
        self.save_project_button = QPushButton("Save project")
        self.save_project_button.setObjectName("secondaryButton")
        self.save_project_button.setToolTip(
            "Save the edits in this project as a .2k5mod file. ★ Rosters has separate save buttons."
        )
        self.save_project_button.setAccessibleName("Save the current mod project")
        self.save_project_button.setAccessibleDescription(
            self.save_project_button.toolTip()
        )
        self.save_project_button.clicked.connect(self._save_project)
        self.open_source_button = QPushButton("Open game disc…")
        self.open_source_button.setObjectName("openSourceButton")
        self.open_source_button.setToolTip(
            "Open your ESPN NFL 2K5 USA Xbox disc file (.iso). The source file is kept unchanged."
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
        self.navigation.currentRowChanged.connect(self._refresh_action_bar_for_page)
        return header

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 28, 34, 26)
        outer.setSpacing(16)
        hero = QLabel("Make NFL 2K5 yours.")
        hero.setObjectName("heroTitle")
        sub = QLabel(
            "Open your Xbox game disc file, choose patches or edit your roster, then "
            "save a new copy. You can also replace uniforms and artwork."
        )
        sub.setObjectName("heroSubtitle")
        sub.setWordWrap(True)
        sub.setMaximumWidth(820)
        outer.addWidget(hero)
        outer.addWidget(sub)

        steps = QHBoxLayout()
        steps.setSpacing(12)
        for number, title, body in (
            ("1", "Open your game", "Use your ESPN NFL 2K5 USA Xbox disc file (.iso), or open an Xbox save on ★ Rosters."),
            ("2", "Choose your changes", "Start with SOFTDRINK patches, edit players, or replace artwork."),
            ("3", "Save a copy", "Use the save or build button for that task. Your original is never changed."),
            ("4", "Play or share", "Open the disc copy in xemu, or export a mod file from Share."),
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
            body_label.setMinimumWidth(120)
            card.setMinimumWidth(150)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            card_layout.addWidget(number_label)
            card_layout.addWidget(title_label)
            card_layout.addWidget(body_label, 1)
            steps.addWidget(card, 1)
        outer.addLayout(steps)

        start = QFrame()
        start.setObjectName("callout")
        # Text on top, the buttons on their own row: four buttons beside a sentence
        # forced the page wider than a 1366-px window.
        start_layout = QVBoxLayout(start)
        start_layout.setContentsMargins(20, 15, 20, 15)
        start_layout.setSpacing(10)
        start_text = QVBoxLayout()
        start_text.setSpacing(2)
        ready = QLabel("Start here")
        ready.setObjectName("cardTitle")
        ready_sub = QLabel(
            "Open a game disc file for disc edits. To edit a roster save, go to ★ Rosters."
        )
        ready_sub.setObjectName("cardBody")
        self.welcome_ready = ready
        self.welcome_ready_sub = ready_sub
        start_text.addWidget(ready)
        start_text.addWidget(ready_sub)
        start_layout.addLayout(start_text)
        start_buttons = QHBoxLayout()
        start_buttons.setSpacing(10)
        # One obvious first click, then the two tasks most people came for.  The roster
        # route stays enabled without a disc: a Finn user opens an Xbox save there.
        open_button = QPushButton("Open game disc…")
        open_button.setObjectName("primaryButton")
        open_button.setToolTip("Open your ESPN NFL 2K5 USA Xbox disc file (.iso). The source file is kept unchanged.")
        open_button.clicked.connect(self._choose_source)
        softdrink_button = QPushButton("Start SOFTDRINK Basic  \u2192")
        softdrink_button.setObjectName("secondaryButton")
        softdrink_button.setToolTip("★ Build & Share with the Basic preset ticked: the 2004 game with the 2K5 fixes. "
                                    "Needs an open disc; you can untick anything before Make my disc.")
        softdrink_button.clicked.connect(lambda: self._go_to_build_share("softdrink_basic"))
        rosters_button = QPushButton("Edit rosters  \u2192")
        rosters_button.setObjectName("secondaryButton")
        rosters_button.setToolTip("★ Rosters: players, ratings, equipment, contracts and depth order, from the open disc or an Xbox save.")
        rosters_button.clicked.connect(self._go_to_rosters)
        browse_button = QPushButton("Browse uniforms")
        browse_button.setObjectName("secondaryButton")
        browse_button.clicked.connect(lambda: self.navigation.setCurrentRow(1))
        self.welcome_open_button = open_button
        self.welcome_task_buttons = (softdrink_button, rosters_button, browse_button)
        start_buttons.addWidget(open_button)
        start_buttons.addWidget(softdrink_button)
        start_buttons.addWidget(rosters_button)
        start_buttons.addWidget(browse_button)
        start_buttons.addStretch(1)
        start_layout.addLayout(start_buttons)
        outer.addWidget(start)
        discord = QLabel(
            f'Stuck? <a href="{update_check.COMMUNITY_DISCORD}">Ask on the Discord</a> '
            "(also under Help ▸ Join the Discord…)."
        )
        discord.setObjectName("cardBody")
        discord.setTextFormat(Qt.RichText)
        discord.setOpenExternalLinks(True)
        discord.setTextInteractionFlags(Qt.TextBrowserInteraction)
        discord.setAccessibleName("Community help link")
        outer.addWidget(discord)
        outer.addStretch(1)
        return page

    def _go_to_rosters(self) -> None:
        """Select ★ Rosters (Getting Started's Edit rosters button); works without a disc."""

        for row in range(self.navigation.count()):
            if self.navigation.item(row).data(Qt.UserRole) == "rosters":
                self.navigation.setCurrentRow(row)
                return

    def _go_to_build_share(self, preset: str | None = None) -> None:
        """Select ★ Build & Share; ``preset`` ticks a SOFTDRINK preset for a fresh selection.

        Only the Getting Started button asks for a preset.  It is applied after the disc has
        been inspected, and only when nothing is ticked yet: ordinary navigation and a set of
        choices the user already customised are left exactly as they are (BS-15).
        """

        for row in range(self.navigation.count()):
            if self.navigation.item(row).data(Qt.UserRole) == "build_share":
                self.navigation.setCurrentRow(row)
                break
        if not preset or self._build_panel is None:
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._build_panel.preset_note.setText(
                "Open your game disc first (top right); the Basic preset is ticked once the disc has been read.")
            self._build_panel.pending_preset = preset
            return
        if self._source_inspect_pending:
            self._build_panel.pending_preset = preset
            return
        self._build_panel.apply_preset_if_fresh(preset)

    def _build_uniform_page(self, section: ProductCategorySection) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(22, 14, 22, 18)
        page_layout.setSpacing(8)
        uniform_intro = QLabel(
            "Pick a team and a uniform, click a part, replace its image. Export PNG gives you a template to edit."
        )
        uniform_intro.setObjectName("mutedLabel")
        uniform_intro.setWordWrap(True)
        page_layout.addWidget(uniform_intro)
        body = QWidget()
        page_layout.addWidget(body, 1)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        browser = QFrame()
        browser.setObjectName("panel")
        browser.setFixedWidth(356)
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
        self.uniform_metadata = QLabel(
            "39 editable parts · 45 equipment textures"
        )
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
        team_kit_header = QVBoxLayout()
        team_kit_header.setSpacing(2)
        team_kit_title = QLabel("Whole kit (39 parts per uniform)")
        team_kit_title.setObjectName("cardTitle")
        self.team_kit_warning = QLabel(
            "This export includes game artwork for your own editing. Share your project (.2k5mod) instead."
        )
        self.team_kit_warning.setObjectName("teamKitWarning")
        self.team_kit_warning.setWordWrap(True)
        team_kit_header.addWidget(team_kit_title)
        team_kit_header.addWidget(self.team_kit_warning)
        team_kit_layout.addLayout(team_kit_header)
        team_kit_scope_note = (
            "All 45 socks, elbow pads, gloves, long sleeves, shoes and wristbands of the "
            "selected uniform use the same project and Make disc from project path."
        )

        equipment_browser_row = QHBoxLayout()
        equipment_browser_row.setSpacing(8)
        equipment_families = QLabel(
            "Socks • elbow pads • gloves • long sleeves • shoes • wristbands"
        )
        equipment_families.setObjectName("mutedLabel")
        equipment_families.setWordWrap(True)
        self.browse_uniform_equipment_button = QPushButton(
            "Equipment (socks, gloves, shoes…)"
        )
        self.browse_uniform_equipment_button.setToolTip(team_kit_scope_note)
        self.browse_uniform_equipment_button.setObjectName("secondaryButton")
        self.browse_uniform_equipment_button.setProperty(
            "teamKitAction", "browse-equipment"
        )
        self.browse_uniform_equipment_button.setAccessibleName(
            "Browse selected uniform set equipment textures"
        )
        self.browse_uniform_equipment_button.setToolTip(
            team_kit_scope_note + " Opens the All Textures browser filtered to this uniform's 45 "
            "equipment textures; Export, Edit, Replace and Revert work there as usual."
        )
        self.browse_uniform_equipment_button.clicked.connect(
            self._browse_selected_uniform_equipment
        )
        equipment_browser_row.addWidget(equipment_families, 1)
        equipment_browser_row.addWidget(self.browse_uniform_equipment_button)
        team_kit_layout.addLayout(equipment_browser_row)

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
        self.team_kit_container.addItem("Folder", "folder")
        self.team_kit_container.addItem("ZIP file", "zip")
        self.export_team_kit_button = QPushButton("Export whole kit…")
        self.export_team_kit_button.setObjectName("secondaryButton")
        self.export_team_kit_button.setProperty("teamKitAction", "export")
        self.export_team_kit_button.setAccessibleName("Export supported Team Kit")
        self.export_team_kit_button.setToolTip(
            "Export all 39 supported components per selected physical set."
        )
        self.import_team_kit_button = QPushButton("Import edited kit…")
        self.import_team_kit_button.setObjectName("primaryButton")
        self.import_team_kit_button.setProperty("teamKitAction", "import")
        self.import_team_kit_button.setAccessibleName("Import edited Team Kit")
        self.import_team_kit_button.setToolTip(
            "Validate every PNG first, then stage only pixel changes as one Undo action."
        )
        self.import_digit_sheet_button = QPushButton("Import number sheet 0–9…")
        self.import_digit_sheet_button.setObjectName("secondaryButton")
        self.import_digit_sheet_button.setProperty("teamKitAction", "digit-sheet")
        self.import_digit_sheet_button.setAccessibleName(
            "Import a complete zero through nine digit sheet"
        )
        self.import_digit_sheet_button.setToolTip(
            "Choose a horizontal or vertical 0–9 sheet at any resolution. "
            "Each cell is resized to that exact set's proved jersey, helmet, "
            "or arm-number dimensions before all ten digits are imported."
        )
        self.export_team_kit_button.clicked.connect(self._choose_team_kit_export)
        self.import_team_kit_button.clicked.connect(self._choose_team_kit_import)
        self.import_digit_sheet_button.clicked.connect(
            self._choose_digit_sheet_import
        )
        team_kit_controls.addWidget(self.team_kit_scope, 2)
        team_kit_controls.addWidget(self.team_kit_container, 1)
        team_kit_controls.addStretch(1)
        team_kit_layout.addLayout(team_kit_controls)
        team_kit_actions = QHBoxLayout()
        team_kit_actions.setSpacing(8)
        team_kit_actions.addWidget(self.export_team_kit_button)
        team_kit_actions.addWidget(self.import_team_kit_button)
        team_kit_actions.addWidget(self.import_digit_sheet_button)
        team_kit_actions.addStretch(1)
        team_kit_layout.addLayout(team_kit_actions)
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

    def _build_colors_page(self, section: ProductCategorySection) -> QWidget:
        """Per-uniform facemask/faceshield and HI_turtleneck controls."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 12)
        layout.setSpacing(10)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(10)
        title = QLabel("Facemask, faceshield and turtleneck colours")
        title.setObjectName("heroTitleSmall")
        blurb = QLabel(
            "Choose a team and uniform. Facemask and faceshield share a colour; turtleneck is "
            "separate. Add to project keeps the change for your next project build."
        )
        blurb.setObjectName("mutedLabel")
        blurb.setWordWrap(True)
        panel_layout.addWidget(title)
        panel_layout.addWidget(blurb)
        colours_details = Details("Details")
        colours_details.add_text(
            "Every physical uniform set owns its own two-word Unif record (per-set, not global). "
            "Word 0 jointly controls the facemask and faceshield (there is no independent visor colour); "
            "the visor type (None / Clear / "
            "Dark) is a per-player field on Names, Numbers & Faces, not a kit tint. Word 1 controls "
            "the HI_turtleneck. Failures stay inline here.", object_name="mutedLabel")
        panel_layout.addWidget(colours_details)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        self.unif_color_search = QLineEdit()
        self.unif_color_search.setObjectName("uniformColourSearch")
        _configure_search_field(
            self.unif_color_search,
            placeholder="Filter by team, set, or selector…",
            accessible_name="Filter uniform colour sets",
            tooltip="Filter the 634 physical uniform colour records by team or set.",
        )
        self.unif_color_set = QComboBox()
        self.unif_color_set.setObjectName("uniformColourSet")
        self.unif_color_set.setAccessibleName(
            "Physical uniform set for facemask and turtleneck colours"
        )
        self.unif_color_set.setAccessibleDescription(
            "Choose the exact HOME, AWAY, alternate, or throwback record to edit."
        )
        self.unif_color_set.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        selector_row.addWidget(self.unif_color_search, 2)
        selector_row.addWidget(self.unif_color_set, 3)
        panel_layout.addLayout(selector_row)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.facemask_button = QPushButton("Facemask / faceshield colour…")
        self.facemask_button.setObjectName("secondaryButton")
        self.turtleneck_button = QPushButton("Turtleneck colour…")
        self.turtleneck_button.setObjectName("secondaryButton")
        self.unif_color_apply = QPushButton("Add to project")
        self.unif_color_revert = QPushButton("Revert")
        self.unif_color_revert.setObjectName("dangerQuietButton")
        row.addWidget(self.facemask_button)
        row.addWidget(self.turtleneck_button)
        row.addStretch(1)
        row.addWidget(self.unif_color_apply)
        row.addWidget(self.unif_color_revert)
        panel_layout.addLayout(row)

        self.unif_color_status = QLabel(
            "Load your NFL 2K5 XISO to read this uniform's original colours — then pick facemask and turtleneck colours below."
        )
        self.unif_color_status.setObjectName("mutedLabel")
        self.unif_color_status.setWordWrap(True)
        self.unif_color_status.setToolTip("Status for the selected uniform's facemask/faceshield and HI_turtleneck colours; updates after each read, stage, or revert.")
        panel_layout.addWidget(self.unif_color_status)
        layout.addWidget(panel)

        self._pending_facemask = "FF000000"
        self._pending_turtleneck = "FF385AAF"
        self._unif_color_generation = 0
        self._unif_color_loaded_selector: str | None = None
        self._unif_color_loaded_pair: tuple[str, str] | None = None
        self._selected_unif_color_modified = False
        self._filter_unif_color_sets()
        self.unif_color_search.textChanged.connect(
            self._filter_unif_color_sets
        )
        self.unif_color_set.currentIndexChanged.connect(
            self._unif_color_selection_changed
        )
        self.facemask_button.clicked.connect(
            lambda: self._choose_unif_color("facemask")
        )
        self.turtleneck_button.clicked.connect(
            lambda: self._choose_unif_color("turtleneck")
        )
        self.unif_color_apply.clicked.connect(self._apply_unif_colors)
        self.unif_color_revert.clicked.connect(self._revert_unif_colors)
        self._refresh_unif_color_swatches()

        layout.addWidget(self._build_capability_page(section), 1)
        return page

    @staticmethod
    def _unif_color_set_label(uniform_set: UniformSet) -> str:
        owner = " / ".join(uniform_set.team_names) or (
            f"Asset {uniform_set.asset_code}"
        )
        return (
            f"{owner} — {uniform_set.style_label} "
            f"{uniform_set.side_name.title()} [{uniform_set.selector}]"
        )

    def _filter_unif_color_sets(self, query: str = "") -> None:
        """Filter the per-uniform selector without losing its current set."""
        if not hasattr(self, "unif_color_set"):
            return
        previous = self._selected_unif_color_selector()
        if previous is None and self._selected_set is not None:
            previous = self._selected_set.selector
        needle = query.strip().casefold()
        matches = tuple(
            uniform_set
            for uniform_set in self.uniform_catalog.uniform_sets
            if not needle or needle in uniform_search_text(uniform_set).casefold()
        )
        self.unif_color_set.blockSignals(True)
        self.unif_color_set.clear()
        for uniform_set in matches:
            self.unif_color_set.addItem(
                self._unif_color_set_label(uniform_set), uniform_set.selector
            )
        target = self.unif_color_set.findData(previous) if previous else -1
        if target >= 0:
            self.unif_color_set.setCurrentIndex(target)
        self.unif_color_set.blockSignals(False)
        # During page construction the footer actions do not exist yet.
        # Initial population is data-only; the normal post-build refresh owns
        # enablement, and a loaded facade is read explicitly after construction.
        if hasattr(self, "undo_button"):
            self._unif_color_selection_changed()

    def _selected_unif_color_selector(self) -> str | None:
        if not hasattr(self, "unif_color_set"):
            return None
        value = self.unif_color_set.currentData()
        return str(value) if value else None

    def _unif_color_selection_changed(self, _index: int = -1) -> None:
        """Read the selected set, discarding results from stale selections."""
        selector = self._selected_unif_color_selector()
        self._unif_color_generation += 1
        generation = self._unif_color_generation
        self._unif_color_loaded_selector = None
        self._unif_color_loaded_pair = None
        self._selected_unif_color_modified = False
        if selector is None:
            self.unif_color_status.setText(
                "No uniform set matches that filter. Clear the filter box to "
                "see every physical HOME/AWAY/alternate/throwback record."
            )
            # Never silent-gray: keep buttons clickable; refresh_action_states
            # sets disableReason (Load / clear filter / wait).
            for button in (
                self.facemask_button,
                self.turtleneck_button,
                self.unif_color_apply,
                self.unif_color_revert,
            ):
                button.setEnabled(True)
            self._refresh_action_states()
            return
        self.facemask_button.setEnabled(True)
        self.turtleneck_button.setEnabled(True)
        if not bool(getattr(self.facade, "source_ready", False)):
            self.unif_color_status.setText(
                f"Load your XISO to read {selector}'s retail colours. "
                "Nothing is staged until Apply."
            )
            self._refresh_action_states()
            return
        self.unif_color_status.setText(f"Reading {selector}'s colours…")

        def success(value: object) -> None:
            if generation != self._unif_color_generation:
                return
            if not isinstance(value, tuple) or len(value) != 3:
                self.unif_color_status.setText(
                    f"Could not read {selector}'s two-word colour record."
                )
                return
            facemask, turtleneck, modified = value
            self._pending_facemask = str(facemask)
            self._pending_turtleneck = str(turtleneck)
            self._unif_color_loaded_selector = selector
            self._unif_color_loaded_pair = (
                self._pending_facemask, self._pending_turtleneck
            )
            self._selected_unif_color_modified = bool(modified)
            self._refresh_unif_color_swatches()
            state = "Staged project edit" if modified else "Retail source"
            self.unif_color_status.setText(
                f"{state} for {selector} — facemask/faceshield "
                f"#{self._pending_facemask[2:]}, HI_turtleneck "
                f"#{self._pending_turtleneck[2:]}."
            )
            self._refresh_action_states()

        def error(message: str) -> None:
            if generation != self._unif_color_generation:
                return
            # Keep the failure inline on the colour panel — the Discord report
            # was a blocking popup that appeared as soon as the team was
            # selected. An inline status lets the user try another set or
            # reload without dismissing a modal.
            hint = friendly_fix_hint(message)
            detail = message.strip()
            if hint is not None:
                detail = f"{detail} — {hint}"
            self.unif_color_status.setText(
                f"Could not read {selector}: {detail} "
                f"Nothing was staged. Pick another set or reload your XISO."
            )
            self._refresh_action_states()

        self._start_task(
            lambda progress: self.facade.uniform_colors(selector, progress),
            success,
            label=f"Reading {selector} uniform colours",
            blocking=False,
            show_errors=False,
            on_error=error,
        )

    def _load_selected_unif_colors(self) -> None:
        if hasattr(self, "unif_color_set"):
            self._unif_color_selection_changed()

    @staticmethod
    def _argb_to_qcolor(value: str) -> QColor:
        """Parse AARRGGBB / #RRGGBB-like packed strings fail-closed."""

        raw = (value or "").strip().removeprefix("#").upper()
        if len(raw) == 8 and all(c in "0123456789ABCDEF" for c in raw):
            return QColor(int(raw[2:4], 16), int(raw[4:6], 16), int(raw[6:8], 16))
        if len(raw) == 6 and all(c in "0123456789ABCDEF" for c in raw):
            return QColor(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        return QColor(0, 0, 0)

    def _refresh_unif_color_swatches(self) -> None:
        for button, value in (
            (self.facemask_button, self._pending_facemask),
            (self.turtleneck_button, self._pending_turtleneck),
        ):
            colour = self._argb_to_qcolor(str(value))
            readable = "#101828" if colour.lightness() > 140 else "#edf3fc"
            button.setStyleSheet(
                f"background:{colour.name()};color:{readable};"
                "border:1px solid #2b3d5f;border-radius:8px;padding:8px 14px;"
            )

    def _choose_unif_color(self, which: str) -> None:
        button = (
            self.facemask_button if which == "facemask" else self.turtleneck_button
        )
        reason = str(button.property("disableReason") or "").strip()
        if reason:
            self.unif_color_status.setText(reason)
            return
        if self._selected_unif_color_selector() is None:
            self.unif_color_status.setText(
                "Pick a physical uniform set first (filter by team/HOME/AWAY), "
                "then choose a colour."
            )
            return
        current = (self._pending_facemask if which == "facemask"
                   else self._pending_turtleneck)
        initial = self._argb_to_qcolor(str(current))
        chosen = QColorDialog.getColor(
            initial, self, f"Choose the {which} colour"
        )
        if not chosen.isValid():
            return
        packed = f"FF{chosen.red():02X}{chosen.green():02X}{chosen.blue():02X}"
        if which == "facemask":
            self._pending_facemask = packed
        else:
            self._pending_turtleneck = packed
        self._refresh_unif_color_swatches()

    def _apply_unif_colors(self) -> None:
        reason = str(self.unif_color_apply.property("disableReason") or "").strip()
        if reason:
            self.unif_color_status.setText(reason)
            return
        selector = self._selected_unif_color_selector()
        if selector is None:
            self.unif_color_status.setText(
                "Pick a physical uniform set first (filter by team/HOME/AWAY)."
            )
            return
        facemask = self._pending_facemask
        turtleneck = self._pending_turtleneck
        if self._unif_color_loaded_selector != selector:
            self.unif_color_status.setText(
                "Wait for this uniform set's original colours to finish loading."
            )
            return
        previous_pair = self._unif_color_loaded_pair
        if previous_pair == (facemask, turtleneck):
            self.unif_color_status.setText(
                f"{selector} already uses those colours; nothing changed."
            )
            return

        def success(value: object) -> None:
            chosen = value if isinstance(value, tuple) else (
                facemask, turtleneck, True
            )
            if bool(chosen[2]):
                self.unif_color_status.setText(
                    f"Staged for {selector} — facemask/faceshield "
                    f"#{chosen[0][2:]}, HI_turtleneck #{chosen[1][2:]}. "
                    "Build Modded XISO to write them to a copy of your disc."
                )
            else:
                self.unif_color_status.setText(
                    f"Restored {selector}'s retail facemask/faceshield and "
                    "HI_turtleneck colours."
                )
            self._unif_color_loaded_pair = (str(chosen[0]), str(chosen[1]))
            self._selected_unif_color_modified = bool(chosen[2])
            if previous_pair != self._unif_color_loaded_pair:
                self._mark_workspace_changed()

        self._start_task(
            lambda progress: self.facade.set_uniform_colors(
                selector, facemask, turtleneck, progress
            ),
            success,
            label=f"Setting {selector} uniform colours",
            blocking=True,
        )

    def _revert_unif_colors(self) -> None:
        reason = str(
            self.unif_color_revert.property("disableReason") or ""
        ).strip()
        if reason:
            self.unif_color_status.setText(reason)
            return
        selector = self._selected_unif_color_selector()
        if selector is None:
            return

        def success(value: object) -> None:
            self.unif_color_status.setText(
                f"Reverted {selector} to its retail colours." if value
                else f"{selector} was already using its retail colours."
            )
            if value:
                self._mark_workspace_changed()
            self._load_selected_unif_colors()

        self._start_task(
            lambda progress: self.facade.clear_uniform_colors(
                selector, progress
            ),
            success,
            label=f"Reverting {selector} uniform colours",
            blocking=True,
        )

    def _build_player_assets_page(self) -> QWidget:
        """One player, and every texture the disc lets you edit for them."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        title = QLabel("Player Assets")
        title.setObjectName("heroTitleSmall")
        blurb = QLabel(
            "Search a player to see the face textures and portrait that belong "
            "to them. Faces are linked by the face_id stored in the player's own "
            "roster record; a portrait is matched by name, because nothing in "
            "the bytes ties a portrait number to a player — that is labelled so "
            "you know which is which."
        )
        blurb.setObjectName("mutedLabel")
        blurb.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(blurb)

        self.player_asset_search = QLineEdit()
        self.player_asset_search.setPlaceholderText(
            "Player name…  (open your game disc first)"
        )
        self.player_asset_search.setClearButtonEnabled(True)
        layout.addWidget(self.player_asset_search)

        self.player_asset_list = QListWidget()
        self.player_asset_list.setObjectName("panel")
        layout.addWidget(self.player_asset_list, 1)

        self.player_asset_detail = QLabel(
            "Open your game disc (top right), then type a player's name."
        )
        self.player_asset_detail.setObjectName("mutedLabel")
        self.player_asset_detail.setWordWrap(True)
        self.player_asset_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.player_asset_detail)

        equipment = QFrame()
        equipment.setObjectName("panel")
        equipment_layout = QVBoxLayout(equipment)
        equipment_layout.setContentsMargins(14, 12, 14, 12)
        equipment_layout.setSpacing(6)
        heading = QLabel("Shared equipment")
        heading.setObjectName("heroTitleSmall")
        equipment_layout.addWidget(heading)
        from mod_editor.core.nfl2k5_player_assets import (
            EQUIPMENT_NOTE, equipment_rows,
        )
        names = QLabel(
            "  •  ".join(label for _key, label in equipment_rows())
        )
        names.setWordWrap(True)
        note = QLabel(EQUIPMENT_NOTE)
        note.setObjectName("findingsNote")
        note.setWordWrap(True)
        equipment_layout.addWidget(names)
        equipment_layout.addWidget(note)
        layout.addWidget(equipment)

        self.player_asset_search.textChanged.connect(self._filter_player_assets)
        self.player_asset_list.currentItemChanged.connect(
            self._show_player_assets
        )
        self._player_asset_rows: tuple[object, ...] = ()
        return page

    def _player_asset_summaries(self) -> tuple[object, ...]:
        """Build the join lazily; it needs a loaded source to say anything."""
        if self._player_asset_rows:
            return self._player_asset_rows
        if not bool(getattr(self.facade, "source_ready", False)):
            return ()
        from mod_editor.core.nfl2k5_player_assets import build_player_assets

        try:
            catalog = self.facade.text_catalog_snapshot(lambda *_a: None)
        except Exception:  # noqa: BLE001 - an unloaded source simply has none
            return ()
        players = []
        for player in getattr(catalog, "players", ()) or ():
            players.append({
                # RosterPlayer already carries the face_id read out of the
                # player record at 0x06, which is the whole basis of the join.
                "player_index": player.player_index,
                "outer_index": player.outer_index,
                "name": player.display_name,
                "face_id": f"{int(player.face_id):04d}",
                "identity_asset_ids": (
                    player.first_name_asset_id, player.last_name_asset_id,
                ),
                "jersey_asset_id": player.jersey_number_asset_id,
            })
        if not players:
            return ()
        self._player_asset_rows = build_player_assets(
            players, self.extended_visual_catalog.assets
        )
        return self._player_asset_rows

    def _filter_player_assets(self, text: str = "") -> None:
        rows = self._player_asset_summaries()
        self.player_asset_list.clear()
        if not rows:
            self.player_asset_detail.setText(
                "Type a name above." if bool(getattr(self.facade, "source_ready", False))
                else "Open your game disc (top right), then type a player's name."
            )
            return
        needle = text.strip().casefold()
        shown = 0
        for row in rows:
            name = getattr(row, "name", "")
            if needle and needle not in name.casefold():
                continue
            item = QListWidgetItem(f"{name}  ·  face {row.face_id}")
            item.setData(Qt.UserRole, row.player_index)
            self.player_asset_list.addItem(item)
            shown += 1
            if shown >= 400:      # a search box, not a scroll-the-whole-roster list
                break

    def _show_player_assets(self, current: object, _previous: object = None) -> None:
        if current is None:
            return
        index = current.data(Qt.UserRole)
        rows = self._player_asset_summaries()
        row = next((r for r in rows if r.player_index == index), None)
        if row is None:
            return
        lines = [f"{row.name} — face_id {row.face_id}"]
        for asset in row.assets:
            origin = ("linked by the roster record"
                      if asset.link == "face_id" else "matched by name")
            lines.append(
                f"  • {asset.label}  ({asset.width}×{asset.height}, {origin})"
            )
        lines.extend(f"  · {note}" for note in row.notes)
        self.player_asset_detail.setText("\n".join(lines))

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
            (ProductStatus.EVIDENCE, section.counts.evidence),
            (ProductStatus.RESEARCH, section.counts.research),
            (ProductStatus.COMING_SOON, section.counts.coming_soon),
        ):
            if count:
                counts.addWidget(
                    _StatusPill(f"{count} {status.value}", _status_color(status))
                )
        counts.addStretch(1)
        layout.addLayout(counts)

        for note in section.findings_notes:
            notice = QLabel(note)
            notice.setObjectName("findingsBanner")
            notice.setWordWrap(True)
            notice.setToolTip("Why this section has its current status — from the registry's finding notes. Hover to keep it visible while reading capabilities below.")
            notice.setAccessibleDescription("Registry finding explaining the status shown for these field-art entries.")
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
        browser.setFixedWidth(356)
        browser_layout = QVBoxLayout(browser)
        browser_layout.setContentsMargins(16, 15, 16, 16)
        browser_layout.setSpacing(9)
        heading_row = QHBoxLayout()
        heading = QLabel(section.title)
        page_intro = {
            ProductCategory.FIELD_ART_CREATE_TEAM:
                "Create-a-Team midfield logos, end zones and goalpost pads. Select an image, then "
                "Replace PNG. For NFL fields, use Stadiums or All Textures.",
            ProductCategory.TEXTURES:
                f"Browse {len(assets):,} indexed textures. Select one marked Editable, then Replace PNG. "
                "Uniforms, fields and the Crib also have their own pages.",
            ProductCategory.SCOREBUG_PRESENTATION:
                "The scorebug's own images. Select one marked Editable, then Replace PNG; the one-line "
                "ESPN bar is the next tab.",
        }.get(section.category, "")
        heading.setObjectName("panelTitle")
        count_label = QLabel(f"{len(assets):,}")
        count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(count_label)
        browser_layout.addLayout(heading_row)
        if page_intro:
            intro_label = QLabel(page_intro)
            intro_label.setObjectName("mutedLabel")
            intro_label.setWordWrap(True)
            browser_layout.addWidget(intro_label)
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
        status_pill = _StatusPill(
            "Editable", _status_color(ProductStatus.EDITABLE)
        )
        title_row.addWidget(status_pill)
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
        master_button = QPushButton("Save high-resolution authoring master…")
        master_button.setObjectName("secondaryButton")
        # Never silent-gray at construction: teach Load/import walls.
        master_boot = (
            "Load your game and import/replace artwork first so an authoring "
            "master draft exists. Click still explains — button stays clickable."
        )
        master_button.setEnabled(True)
        master_button.setToolTip(master_boot)
        master_button.setProperty("disableReason", master_boot)
        replace_button = QPushButton("Replace PNG")
        replace_button.setObjectName("primaryButton")
        revert_button = QPushButton("Revert")
        revert_button.setObjectName("dangerQuietButton")
        # Editing in place removes the export/other-program/import round trip,
        # which is where size and alpha get lost. The canvas is the slot's exact
        # size and has no resize control, so what it saves always fits.
        edit_button = QPushButton("Edit…")
        edit_button.setObjectName("secondaryButton")
        edit_button.clicked.connect(
            lambda _checked=False, category=section.category: self._edit_visual_asset(category)
        )
        actions.addWidget(export_button)
        actions.addWidget(master_button)
        actions.addWidget(edit_button)
        actions.addWidget(replace_button)
        actions.addWidget(revert_button)
        detail_layout.addLayout(actions)
        outer.addWidget(detail, 1)

        state = _VisualBrowserState(
            section.category, kinds, assets, search, group_filter, asset_list,
            count_label, title, metadata, status_pill, preview, help_label, export_button,
            master_button,
            edit_button, replace_button, revert_button,
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
        master_button.clicked.connect(
            lambda _checked=False, category=section.category:
                self._save_visual_authoring_master(category)
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
        export_button.setEnabled(True)
        export_button.setToolTip(
            "Load your XISO and select a resource first. Click still explains."
        )
        export_button.setProperty(
            "disableReason",
            "Load your XISO and select a resource first.",
        )
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
        # Never silent-gray: page buttons stay clickable; boot tip until Load.
        page_boot = (
            "Load your NFL 2K5 XISO and open All Resources first. "
            "Previous/Next stay clickable so blocked states explain themselves."
        )
        for button in (previous_button, next_button):
            button.setEnabled(True)
            button.setToolTip(page_boot)
            button.setProperty("disableReason", page_boot)
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
        stadium_intro = QLabel(
            "Browse stadium scenes. Select a surface marked Editable, then Replace its image. "
            "3D exports open in Blender."
        )
        stadium_intro.setObjectName("mutedLabel")
        stadium_intro.setWordWrap(True)
        heading.setObjectName("panelTitle")
        count_label = QLabel("477")
        count_label.setObjectName("countPill")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(count_label)
        scenes_layout.addLayout(heading_row)
        scenes_layout.addWidget(stadium_intro)
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
        # Exactly one of the 477 indexed scenes carries catalog-pinned geometry
        # targets, and nothing in this list used to say which. Someone asking
        # whether stadium models work would open scene after scene, watch Import
        # stage nothing, and reasonably conclude they do not.
        editable_only = QCheckBox("Only scenes with editable geometry")
        editable_only.setObjectName("filterCheck")
        editable_only.setToolTip(
            "The bounded same-count position writer is pinned to one full "
            "Stadium scene. Tick this to list only that scene; untick to browse "
            "every indexed stadium scene for viewing and glTF export."
        )
        editable_only.setAccessibleName(
            "Show only stadium scenes with editable geometry"
        )
        scenes_layout.addWidget(editable_only)
        scene_list = QListWidget()
        scene_list.setObjectName("assetList")
        scene_list.setSpacing(2)
        scenes_layout.addWidget(scene_list, 1)
        export_scene_button = QPushButton("Export model (glTF)…")
        export_scene_button.setObjectName("secondaryButton")
        export_scene_button.setToolTip(
            "Save the selected stadium as a glTF you can open in Blender. "
            "The buffer is written beside it and is copied unchanged; the model "
            "carries a root scale so it arrives in metres instead of the "
            "centimetres the game authors in."
        )
        scenes_layout.addWidget(export_scene_button)
        import_scene_button = QPushButton("Import edited model…")
        import_scene_button.setObjectName("primaryButton")
        import_scene_button.setToolTip(
            "Import the matching glTF after moving vertices in Blender. Vertex "
            "count and faces must stay unchanged; Mod Studio keeps the game's "
            "original UV, material, collision, selector, and other stream bytes."
        )
        scenes_layout.addWidget(import_scene_button)
        apply_textures_button = QPushButton("Apply textures from glTF…")
        apply_textures_button.setObjectName("primaryButton")
        apply_textures_button.setToolTip(
            "Apply the textures you edited in Blender back into the game. Export "
            "embeds each stadium texture into the glTF; edit those images in "
            "Blender, re-export, and this writes them back through the bounded "
            "writer, matched by nfl2k5_texture_id or material name."
        )
        scenes_layout.addWidget(apply_textures_button)
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
        viewport.setMinimumSize(360, 300)
        view_layout.addWidget(viewport, 1)
        outer.addWidget(view_panel, 1)

        texture_panel = QFrame()
        texture_panel.setObjectName("panel")
        texture_panel.setFixedWidth(320)
        texture_layout = QVBoxLayout(texture_panel)
        texture_layout.setContentsMargins(14, 14, 14, 14)
        texture_layout.setSpacing(8)
        texture_heading = QLabel("Surface textures")
        texture_heading.setObjectName("panelTitle")
        texture_layout.addWidget(texture_heading)
        self._stadium_people_filter = QCheckBox(tab_title("People & sideline only"))
        self._stadium_people_filter.setObjectName("codeLabel")
        self._stadium_people_filter.setAccessibleName("Filter to people and sideline textures")
        self._stadium_people_filter.setToolTip(
            "Filter the texture list to people and sideline elements (fans, cheerleaders, coaches, officials, chain crew, cameras, ushers). Uncheck to show all surfaces."
        )
        texture_layout.addWidget(self._stadium_people_filter)
        texture_list = QListWidget()
        texture_list.setObjectName("assetList")
        texture_list.setMaximumHeight(180)
        texture_layout.addWidget(texture_list)
        texture_preview = _PngDropPreview()
        texture_preview.setMinimumSize(240, 180)
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
        state.editable_only = editable_only
        search.returnPressed.connect(lambda: self._load_stadium_scenes(force=True))
        search_button.clicked.connect(lambda: self._load_stadium_scenes(force=True))
        editable_only.toggled.connect(lambda _checked: self._populate_stadium_scenes())
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
        export_scene_button.clicked.connect(self._export_stadium_scene_gltf)
        import_scene_button.clicked.connect(self._import_stadium_scene_gltf)
        apply_textures_button.clicked.connect(self._apply_stadium_textures_from_gltf)
        replace_button.clicked.connect(self._choose_stadium_texture_replacement)
        revert_button.clicked.connect(self._revert_stadium_texture)
        # Never silent-gray texture export/replace/revert at construction either.
        tex_boot = (
            "Load your NFL 2K5 XISO, open Stadium Studio, and select a surface "
            "texture first. Buttons stay clickable so blocked states explain themselves."
        )
        for button in (export_button, replace_button, revert_button):
            button.setEnabled(True)
            button.setToolTip(tex_boot)
            button.setProperty("disableReason", tex_boot)
        # Model export/import/texture-apply stay clickable so blocked states are
        # never silent gray; tooltips + disableReason + click explain Load XISO /
        # pick scene.
        model_boot = (
            "Load your NFL 2K5 XISO and select a stadium scene first. "
            "These model tools stay clickable so blocked states explain themselves."
        )
        export_scene_button.setEnabled(True)
        export_scene_button.setToolTip(model_boot)
        export_scene_button.setProperty("disableReason", model_boot)
        import_scene_button.setEnabled(True)
        import_scene_button.setToolTip(model_boot)
        import_scene_button.setProperty("disableReason", model_boot)
        apply_textures_button.setEnabled(True)
        apply_textures_button.setToolTip(model_boot)
        apply_textures_button.setProperty("disableReason", model_boot)
        self._stadium_export_scene_button = export_scene_button
        self._stadium_import_scene_button = import_scene_button
        self._stadium_apply_textures_button = apply_textures_button
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
        # A card is a description with no controls on it. When the capability
        # is a writer, an "Editable" pill on a card with nothing to click reads
        # as a broken button -- a modder went looking for the facemask colour,
        # found this card, and reasonably reported it as a regression. Say
        # plainly where the workspace is, or that there isn't one yet and the
        # command line is the way in.
        workspace = _WORKSPACE_CAPABILITIES.get(binding.capability_id)
        backend = binding.capability.raw.get("backend") or {}
        if workspace is not None:
            where = QLabel(f"Edit this in the {workspace} workspace.")
            where.setObjectName("findingsNote")
            where.setWordWrap(True)
            layout.addWidget(where)
        elif backend.get("operation") == "write":
            where = QLabel(
                "No in-app workspace yet — this one runs from the command line:"
            )
            where.setObjectName("findingsNote")
            where.setWordWrap(True)
            layout.addWidget(where)
            command = QLabel(str(backend.get("command", "")))
            command.setObjectName("codeLabel")
            command.setWordWrap(True)
            command.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(command)
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
            getattr(self, "_pending_status", None)
            or "Open your game disc to start (top right), or browse what’s available."
        )
        self.operation_status.setObjectName("operationStatus")
        self.operation_status.setTextFormat(Qt.PlainText)
        # A plain QLabel never elides, so its full sentence became a hard
        # minimum width for the footer -- 509 px of it -- and the footer in turn
        # set the window's minimum to 1601 px. That is wider than a 1366-wide
        # laptop can show, which is why switching pages felt like the app no
        # longer fitted its own window. Let it shrink and elide; the full text
        # stays available as a tooltip.
        self.operation_status.setSizePolicy(
            QSizePolicy.Ignored, self.operation_status.sizePolicy().verticalPolicy()
        )
        self.operation_status.setMinimumWidth(0)
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
        self.edit_count = QLabel("No project edits")
        self.edit_count.setObjectName("editCount")
        self.edit_count.setToolTip("Art, text and audio edits that go into Make disc from project.")
        self.edit_count.setAccessibleName("Pending edit count")
        self.edit_count.setAccessibleDescription(self.edit_count.toolTip())
        self.undo_button = QPushButton("Undo")
        self.undo_button.setObjectName("secondaryButton")
        self.revert_all_button = QPushButton("Revert All")
        self.revert_all_button.setObjectName("dangerQuietButton")
        self.check_images_button = QPushButton("Check My Images")
        self.check_images_button.setObjectName("utilityButton")
        self.check_images_button.setToolTip(CHECK_IMAGES_MESSAGE)
        self.check_images_button.setAccessibleName(
            "Check staged images against their slots"
        )
        self.check_images_button.setAccessibleDescription(
            self.check_images_button.toolTip()
        )
        self.build_button = QPushButton("Make disc from project")
        self.build_button.setObjectName("buildButton")
        self.build_button.setToolTip(BUILD_READY_MESSAGE)
        self.configure_xemu_button = QPushButton("Set up xemu…")
        self.configure_xemu_button.setObjectName("utilityButton")
        self.configure_xemu_button.setToolTip(
            "Tell the app where xemu is. Only needed if Play latest disc in xemu "
            "can't find it by itself."
        )
        self.configure_xemu_button.setAccessibleName("Configure the xemu launcher")
        self.configure_xemu_button.setAccessibleDescription(
            self.configure_xemu_button.toolTip()
        )
        self.launch_button = QPushButton("Play latest disc in xemu")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.setToolTip("Make a disc first.")
        self.undo_button.setAccessibleName("Undo the most recent project edit")
        self.undo_button.setAccessibleDescription(
            "Undo one replacement, text edit, or other project change."
        )
        self.revert_all_button.setAccessibleName("Revert every project edit")
        self.revert_all_button.setAccessibleDescription(
            "Remove every project edit after confirmation; your original disc is untouched."
        )
        self.build_button.setAccessibleName("Build a separate modded XISO")
        self.build_button.setAccessibleDescription(self.build_button.toolTip())
        self.launch_button.setAccessibleName("Launch the latest build in xemu")
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        self.undo_button.clicked.connect(self._undo)
        self.revert_all_button.clicked.connect(self._revert_all)
        self.check_images_button.clicked.connect(self._check_staged_images)
        self.build_button.clicked.connect(self._choose_build_output)
        self.configure_xemu_button.clicked.connect(self._configure_xemu)
        self.launch_button.clicked.connect(self._launch_xemu)
        # On ★ Build & Share the project controls hide (they are about staged
        # art/text/audio edits); this caption says where those went instead of
        # leaving an unexplained gap (X-08).
        self.build_share_caption = QLabel(
            "This Build tab uses the changes selected here. Project edits use "
            "Make disc from project on the editing pages."
        )
        self.build_share_caption.setObjectName("buildShareCaption")
        self.build_share_caption.setToolTip(self.build_share_caption.text())
        self.build_share_caption.setSizePolicy(
            QSizePolicy.Ignored, self.build_share_caption.sizePolicy().verticalPolicy()
        )
        self.build_share_caption.setMinimumWidth(0)
        self.build_share_caption.hide()
        layout.addWidget(self.build_share_caption, 1)
        layout.addWidget(self.edit_count)
        layout.addWidget(self.undo_button)
        layout.addWidget(self.revert_all_button)
        layout.addSpacing(4)
        layout.addWidget(self.configure_xemu_button)
        layout.addSpacing(4)
        # Directly above Build, because this is the question a user has right
        # before they press it: will my art come through the way I drew it?
        layout.addWidget(self.check_images_button)
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
        route = (
            "view only (export)"
            if asset.writer_route is VisualWriterRoute.EXPORT_ONLY
            else f"{asset.width}×{asset.height} image"
        )
        state.metadata.setText(
            f"{asset.group} • {asset.width}×{asset.height} • {route}"
        )
        if asset.writer_route is VisualWriterRoute.EXPORT_ONLY:
            state.status_pill.set_status("Export only", "#91a0b5")
        else:
            state.status_pill.set_status(
                "Editable", _status_color(ProductStatus.EDITABLE)
            )
        route_note = ""
        if asset.writer_route is VisualWriterRoute.SCOREBUG:
            route_note = (
                " This texture now composes with uniforms, portraits, text, audio, "
                "and editable Crib textures in the same one-click XISO build."
            )
        # The note says what happens to a picture, not what the slot demands: any common image
        # file is resized to the slot for you; only a too-detailed one may not fit (FA-03 / AT-03).
        state.help_label.setText(
            f"Common image files are resized to {asset.width}×{asset.height} for you. If the image is "
            f"too detailed to fit, simplify it and try again.{route_note}"
        )
        state.help_label.setToolTip(asset.authoring_note or "")
        self._refresh_visual_action_states(state)
        if bool(getattr(self.facade, "source_ready", False)):
            self._load_visual_preview(asset, state.preview)
        else:
            state.preview.set_empty(
                f"{asset.label}\n{asset.width} × {asset.height} RGBA PNG\n\n"
                "Open your game disc to see this image."
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

        def failed(message: str) -> None:
            # Without this the panel sat on "Preparing ..." forever: the task
            # raised, show_errors=False swallowed it, and nothing replaced the
            # loading text. A preview that cannot be produced has to say so, or
            # the only symptom is a spinner that never resolves -- which is
            # exactly how the missing All Textures decoder presented.
            if generation != self._preview_generation:
                return
            preview.set_empty(f"Preview unavailable — {message}")
            self._set_status(f"Could not prepare {asset.label}: {message}")

        self._start_task(
            lambda progress: self.facade.preview_asset(asset, progress),
            success,
            label=f"Preparing {asset.label}",
            blocking=False,
            show_errors=False,
            on_error=failed,
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
        state, asset = selected
        reason = str(state.export_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        suggested = _suggested_png_name(asset.asset_id)
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

    def _fit_for_slot(
        self, path: Path, width: int, height: int, label: str, *,
        mode: str = "auto",
    ) -> Path | None:
        """Return a path that is exactly this slot's size, or None if declined.

        Dialog and drag/drop both call this path. When a resize is required and
        ``mode`` is ``auto``, the user chooses Contain, Cover, or Stretch.
        An already-correct RGBA PNG is returned untouched.
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
            self._show_error(f"That file could not be read as an image. {exc}")
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
                    self,
                    "How should this image fit the slot?",
                    f"{label} must be exactly {width}×{height}, and that image is "
                    f"{probe.source_width}×{probe.source_height}.\n\n"
                    "Choose Contain, Cover, or Stretch. Dialog and drag/drop "
                    "share this path. Your original file is not modified.",
                    labels,
                    0,
                    False,
                )
                if not accepted:
                    return None
                try:
                    chosen_mode = fit_mode_from_label(str(choice))
                except ValidationError as exc:
                    self._show_error(str(exc))
                    return None
            else:
                chosen_mode = "contain"  # exact size, PNG conversion only
        else:
            answer = QMessageBox.question(
                self,
                "Prepare this image?" if needs_png_conversion else "Resize this image?",
                f"{label} must be exactly {width}×{height}, and that image is "
                f"{probe.source_width}×{probe.source_height}.\n\n"
                f"Mod Studio will apply fit mode “{chosen_mode}”.\n\n"
                "Your original file is not modified — the prepared copy is used "
                "for this edit only.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return None
        try:
            if self._fit_dir is None:
                self._fit_dir = Path(tempfile.mkdtemp(prefix="2k5-fitted-"))
            staged = self._fit_dir / f"{_suggested_png_name(label)}"
            result = fit_to_png(path, width, height, staged, mode=chosen_mode)
        except ValidationError as exc:
            self._show_error(f"Could not resize that image. {exc}")
            return None
        verb = "Prepared" if needs_png_conversion else "Resized"
        self._set_status(f"{verb} for {label} — {result.describe()} ({chosen_mode}).")
        return staged

    def _discard_texture_master_draft(self, asset_id: str) -> None:
        draft = self._texture_master_drafts.pop(asset_id, None)
        if draft is not None:
            draft.source_image.unlink(missing_ok=True)
            if draft.native_baseline_png != draft.source_image:
                draft.native_baseline_png.unlink(missing_ok=True)

    def _clear_texture_master_drafts(self) -> None:
        for asset_id in tuple(self._texture_master_drafts):
            self._discard_texture_master_draft(asset_id)

    def _close_texture_master_workspace(self) -> None:
        """Remove private full-resolution snapshots after an accepted close."""

        self._clear_texture_master_drafts()
        if self._texture_master_finalizer.alive:
            self._texture_master_finalizer()

    def _prepare_texture_master_draft(
        self,
        asset: ExtendedVisualAsset,
        source: Path,
        compiled_native: Path,
    ) -> _TextureMasterDraft:
        """Preserve the exact import before any native-size resampling."""

        from mod_editor.core.image_fit import fit_image

        snapshot, source_sha256 = snapshot_texture_master_source(
            source,
            self._texture_master_root / f"{uuid4().hex}.source",
        )
        probe = fit_image(snapshot, asset.width, asset.height, mode="auto")
        fit_mode = "scale" if probe.action in {"exact", "scaled"} else "cover"
        transform = texture_master_fit_transform(
            probe.source_width,
            probe.source_height,
            asset.width,
            asset.height,
            mode=fit_mode,
            resample="lanczos",
        )
        native_baseline = snapshot
        try:
            if Path(source).resolve(strict=True) == Path(compiled_native).resolve(
                strict=True
            ):
                native_baseline = snapshot
            else:
                native_baseline, _native_sha256 = snapshot_texture_master_source(
                    compiled_native,
                    self._texture_master_root / f"{uuid4().hex}.native.png",
                )
            compiled_probe = fit_image(
                native_baseline, asset.width, asset.height, mode="scale"
            )
            if probe.rgba != compiled_probe.rgba:
                raise ValidationError(
                    "The image changed while Mod Studio was preparing its native "
                    "copy. Import it again; no replacement was staged."
                )
        except BaseException:
            snapshot.unlink(missing_ok=True)
            if native_baseline != snapshot:
                native_baseline.unlink(missing_ok=True)
            raise
        editor_transform = {
            "action": probe.action,
            "canvas_height": asset.height,
            "canvas_width": asset.width,
            "center_x": transform.center_x,
            "center_y": transform.center_y,
            "coordinate_space": "native-texture-pixels",
            "cropped_x": probe.cropped_x,
            "cropped_y": probe.cropped_y,
            "fit_mode": fit_mode,
            "height": transform.height,
            "operation": "nfl2k5-import-fit",
            "padded_x": probe.padded_x,
            "padded_y": probe.padded_y,
            "resample": "lanczos",
            "rotation_degrees": 0.0,
            "source_height": probe.source_height,
            "source_mode": probe.source_mode,
            "source_format": probe.source_format,
            "source_width": probe.source_width,
            "width": transform.width,
        }
        return _TextureMasterDraft(
            snapshot,
            source_sha256,
            native_baseline,
            transform,
            editor_transform,
        )

    def _save_visual_authoring_master(
        self, category: ProductCategory
    ) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        _state, asset = selected
        draft = self._texture_master_drafts.get(asset.asset_id)
        save = getattr(self.facade, "save_texture_authoring_master", None)
        if draft is None or not callable(save):
            self._show_error(
                "Import this texture in the current session before saving its "
                "full-resolution authoring master. Projects currently retain "
                "the exact native PNG only."
            )
            return
        choice, accepted = QInputDialog.getItem(
            self,
            "Authoring preview size",
            "Render the authoring preview directly from the preserved source at:",
            ("4× (recommended)", "2×"),
            0,
            False,
        )
        if not accepted:
            return
        scale = 4 if str(choice).startswith("4") else 2
        suggested = _suggested_png_name(asset.asset_id).removesuffix(".png")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save high-resolution authoring master",
            str(Path.home() / f"{suggested}.2ktexmaster"),
            "2K texture authoring master (*.2ktexmaster)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".2ktexmaster":
            destination = destination.with_suffix(".2ktexmaster")

        def success(result: object) -> None:
            self._set_status(
                f"Saved {asset.label} authoring master to {Path(result).name}. "
                "The game build still uses its exact native-size PNG."
            )

        self._start_task(
            lambda progress: save(
                asset,
                source_image=draft.source_image,
                source_sha256=draft.source_sha256,
                destination=destination,
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
            success,
            label=f"Saving {asset.label} authoring master",
            blocking=True,
        )

    def _edit_visual_asset(self, category: ProductCategory) -> None:
        """Open the built-in editor on the selected slot's current pixels."""
        selected = self._selected_visual(category)
        if selected is None:
            self._show_error("Choose an asset to edit.")
            return
        state, selected_asset = selected
        reason = str(state.edit_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        if not selected_asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before editing an asset.")
            return
        asset = selected_asset
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.image_fit import fit_image
        from mod_editor.gui.texture_editor import edit_texture

        try:
            current = self.facade.preview_asset(asset, lambda *_a: None)
            pixels = fit_image(Path(current), asset.width, asset.height).rgba
        except (ValidationError, OSError) as exc:
            self._show_error(f"Could not open {asset.label} for editing. {exc}")
            return

        edited = edit_texture(pixels, asset.width, asset.height, asset.label, self)
        if edited is None:
            return
        import sys as _sys

        tools = str(Path(__file__).resolve().parents[2] / "tools")
        if tools not in _sys.path:
            _sys.path.insert(0, tools)
        from nfl_txtr import encode_rgba_png

        if self._fit_dir is None:
            self._fit_dir = Path(tempfile.mkdtemp(prefix="2k5-fitted-"))
        staged = self._fit_dir / _suggested_png_name(f"{asset.asset_id}-edited")
        staged.write_bytes(encode_rgba_png(edited.width, edited.height, edited.rgba))
        changed_pixels = sum(
            pixels[offset:offset + 4] != edited.rgba[offset:offset + 4]
            for offset in range(0, len(pixels), 4)
        )
        # If this session already owns an external full-resolution import, keep
        # it and record this exact native-canvas raster edit as a composited
        # authoring layer. A retail-only Edit still cannot become a shareable
        # master because that would package source-derived game pixels.
        self._replace_visual_asset(
            state,
            asset,
            staged,
            native_canvas_edit={
                "changed_pixel_count_from_previous_canvas": changed_pixels,
                "operation": "native-canvas-raster-edit-after-import",
                "preview_composition": (
                    "nearest-native-pixel-edits-over-direct-master-render"
                ),
            },
        )

    def _choose_visual_replacement(self, category: ProductCategory) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        state, asset = selected
        reason = str(state.replace_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        if not asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, f"Replace {asset.label}", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga);;All files (*)",
        )
        if filename:
            self._replace_visual_asset(state, asset, Path(filename))

    def _replace_visual_from_drop(
        self, category: ProductCategory, supplied: object
    ) -> None:
        if _is_apple_double_path(Path(str(supplied))):
            self._show_error(APPLE_DOUBLE_DROP_REFUSAL)
            return
        selected = self._selected_visual(category)
        if selected is None:
            self._show_error("Choose an asset before dropping a PNG.")
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before replacing an asset.")
            return
        state, asset = selected
        if not asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return
        self._replace_visual_asset(state, asset, Path(supplied))

    def _replace_visual_asset(
        self,
        state: _VisualBrowserState,
        asset: ExtendedVisualAsset,
        path: Path,
        *,
        native_canvas_edit: Mapping[str, object] | None = None,
    ) -> None:
        if not asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return
        fitted = self._fit_for_slot(path, asset.width, asset.height, asset.label)
        if fitted is None:
            return
        existing_master = self._texture_master_drafts.get(asset.asset_id)
        pending_master: _TextureMasterDraft | None = None
        if native_canvas_edit is None:
            try:
                pending_master = self._prepare_texture_master_draft(
                    asset, path, fitted
                )
            except ValidationError as exc:
                self._show_error(
                    "The native import was not started because its full-resolution "
                    f"authoring source could not be preserved safely. {exc}"
                )
                return
        path = fitted

        def success(result: object) -> None:
            modified = bool(getattr(result, "modified", True))
            if native_canvas_edit is not None:
                if modified and existing_master is not None:
                    revision = int(
                        existing_master.editor_transform.get(
                            "native_canvas_edit_revision", 0
                        )
                    ) + 1
                    updated_editor_transform = dict(
                        existing_master.editor_transform
                    )
                    updated_editor_transform.update({
                        "native_canvas_edit": dict(native_canvas_edit),
                        "native_canvas_edit_revision": revision,
                    })
                    self._texture_master_drafts[asset.asset_id] = (
                        _TextureMasterDraft(
                            existing_master.source_image,
                            existing_master.source_sha256,
                            existing_master.native_baseline_png,
                            existing_master.transform,
                            updated_editor_transform,
                            True,
                        )
                    )
                elif not modified:
                    self._discard_texture_master_draft(asset.asset_id)
            elif modified and pending_master is not None:
                self._discard_texture_master_draft(asset.asset_id)
                self._texture_master_drafts[asset.asset_id] = pending_master
            else:
                if pending_master is not None:
                    pending_master.source_image.unlink(missing_ok=True)
                    pending_master.native_baseline_png.unlink(missing_ok=True)
                self._discard_texture_master_draft(asset.asset_id)
            self._set_status(_result_message(result, f"{asset.label} is ready to build."))
            state.selected_asset_id = asset.asset_id
            self._filter_visual_assets(state.category)
            self._mark_workspace_changed()
            self._load_visual_preview(asset, state.preview)

        def failed(_message: str) -> None:
            if pending_master is not None:
                pending_master.source_image.unlink(missing_ok=True)
                pending_master.native_baseline_png.unlink(missing_ok=True)

        self._start_task(
            lambda progress: self.facade.replace_asset(asset, path, progress),
            success,
            label=f"Checking and replacing {asset.label}",
            blocking=True,
            on_error=failed if pending_master is not None else None,
        )

    def _revert_visual_asset(self, category: ProductCategory) -> None:
        selected = self._selected_visual(category)
        if selected is None:
            return
        state, asset = selected
        reason = str(state.revert_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        if not asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return

        def success(result: object) -> None:
            self._discard_texture_master_draft(asset.asset_id)
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
        busy = self._blocking or self._embedded_operation_is_busy()
        asset = (
            self.extended_visual_catalog.get_asset(state.selected_asset_id)
            if state.selected_asset_id is not None
            else None
        )
        # Never silent-gray: keep actions clickable; disableReason teaches walls.
        if not ready:
            block = "Load your NFL 2K5 XISO first to export or edit this visual asset."
        elif not selected:
            block = "Select a visual asset from the list first."
        elif busy:
            block = "Wait for the current operation to finish."
        else:
            block = ""
        export_tip = block or "Export this visual asset as PNG from your private cache."
        state.export_button.setEnabled(True)
        state.export_button.setToolTip(export_tip)
        state.export_button.setProperty("disableReason", block)
        edit_ok = bool(
            ready and selected and not busy and asset is not None and asset.editable
        )
        if edit_ok:
            edit_block = ""
            edit_tip = "Edit or replace this editable visual texture (auto-resize on import)."
        elif block:
            edit_block = edit_tip = block
        elif asset is not None and not asset.editable:
            edit_block = edit_tip = (
                f"{asset.label} is export-only / not editable in this catalog. "
                "Use Export, or open a named writer workspace if one exists."
            )
        else:
            edit_block = edit_tip = "Select an editable visual asset first."
        for button, tip in (
            (state.edit_button, edit_tip),
            (state.replace_button, edit_tip),
        ):
            button.setEnabled(True)
            button.setToolTip(tip)
            button.setProperty("disableReason", edit_block)
        master_ok = bool(
            edit_ok
            and state.selected_asset_id in self._texture_master_drafts
            and callable(getattr(self.facade, "save_texture_authoring_master", None))
        )
        if master_ok:
            master_block = ""
            master_tip = "Save high-resolution authoring master for this texture."
        elif edit_block:
            master_block = master_tip = edit_block
        else:
            master_block = master_tip = (
                "Import/replace artwork first so an authoring master draft exists."
            )
        state.master_button.setEnabled(True)
        state.master_button.setToolTip(master_tip)
        state.master_button.setProperty("disableReason", master_block)
        can_revert = bool(edit_ok and state.selected_asset_id in modified)
        if can_revert:
            revert_block = ""
            revert_tip = "Revert staged replacement for this visual asset."
        elif edit_block:
            revert_block = revert_tip = edit_block
        else:
            revert_block = revert_tip = (
                "Nothing to revert—this visual asset is still original."
            )
        state.revert_button.setEnabled(True)
        state.revert_button.setToolTip(revert_tip)
        state.revert_button.setProperty("disableReason", revert_block)
        state.preview.set_replacement_enabled(edit_ok)

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
            busy = self._blocking or self._embedded_operation_is_busy()
            if busy:
                page_block = "Wait for the current operation to finish, then page."
            else:
                page_block = ""
            if page_block:
                prev_block = next_block = page_block
                prev_tip = next_tip = page_block
            else:
                if state.offset > 0:
                    prev_block, prev_tip = "", "Show the previous 250 indexed resources."
                else:
                    prev_block = prev_tip = "Already on the first page of indexed resources."
                if len(state.rows) == 250:
                    next_block, next_tip = "", "Show the next 250 indexed resources."
                else:
                    next_block = next_tip = "Already on the last page of matching resources."
            state.previous_button.setEnabled(True)
            state.previous_button.setToolTip(prev_tip)
            state.previous_button.setProperty("disableReason", prev_block)
            state.next_button.setEnabled(True)
            state.next_button.setToolTip(next_tip)
            state.next_button.setProperty("disableReason", next_block)
            # Never silent-gray export: empty page teaches select/load wall.
            if busy:
                exp_block = "Wait for the current operation to finish."
            elif not state.rows:
                exp_block = (
                    "No matching resources on this page. Broaden search or change FourCC."
                )
            else:
                exp_block = ""
            state.export_button.setEnabled(True)
            state.export_button.setToolTip(
                exp_block
                or "Export the exact raw game resource (wrapper + body) to a new file."
            )
            state.export_button.setProperty("disableReason", exp_block)

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
        button = state.previous_button if direction < 0 else state.next_button
        reason = str(button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
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
        ready = bool(getattr(self.facade, "source_ready", False))
        busy = self._blocking or self._embedded_operation_is_busy()
        if not ready:
            block = "Load your NFL 2K5 XISO first to export a raw resource."
        elif busy:
            block = "Wait for the current operation to finish."
        else:
            block = ""
        state.export_button.setEnabled(True)
        state.export_button.setToolTip(
            block or "Export the exact raw game resource (wrapper + body) to a new file."
        )
        state.export_button.setProperty("disableReason", block)

    def _export_universal_asset(self) -> None:
        state = self._universal_browser
        if state is None:
            return
        reason = str(state.export_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        current = state.asset_list.currentItem()
        if current is None:
            self._show_error(
                "Select a resource in the complete inventory list first, then Export."
            )
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
        # The first open of this tab for a given game DERIVES the stadium
        # assets: about 750 MB over ten to thirty minutes, once. Saying
        # "Loading…" and nothing else for half an hour is why this read as
        # broken to the first user who hit it on a cold cache.
        state.scene_metadata.setText(
            "Preparing private stadium assets from your own game.\n"
            f"First time only: about {ESTIMATED_PRIVATE_BYTES // (1024**2)} MB "
            f"and {ESTIMATED_SECONDS_LOW // 60}–{ESTIMATED_SECONDS_HIGH // 60} "
            "minutes. Later opens are instant."
        )
        state.count_label.setText("Preparing…")
        search = state.search.text().strip()

        def report(stage: str, completed: int, total: int) -> None:
            current = self._stadium_browser
            if current is None or current is not state:
                return
            if total > 1 and completed <= total:
                current.count_label.setText(f"{completed:,}/{total:,}")
                current.scene_metadata.setText(
                    f"{stage}…\n{completed:,} of {total:,} — first time only, "
                    "later opens are instant."
                )
            else:
                current.scene_metadata.setText(f"{stage}…")

        def success(result: object) -> None:
            state.scenes = tuple(result)  # type: ignore[arg-type]
            state.scenes_loaded = True
            state.scenes_loading = False
            self._populate_stadium_scenes()

        def failed(message: str) -> None:
            current = self._stadium_browser
            if current is None:
                return
            current.scenes_loading = False
            current.count_label.setText("Retry")
            current.scene_metadata.setText(
                f"Stadium assets could not be prepared: {message}\n"
                "Your game and projects are untouched. Reopen this tab to try "
                "again; completed scenes are kept and resumed."
            )

        self._start_task(
            lambda progress: self.facade.stadium_scenes(search, progress),
            success,
            label="Loading Stadium Studio",
            blocking=False,
            on_error=failed,
            on_progress=report,
        )

    def _populate_stadium_scenes(self) -> None:
        """Fill the scene list, marking the scenes whose geometry is writable.

        Only scenes carrying catalog-pinned geometry targets accept an edited
        glTF. Naming that in the row -- and offering a filter that hides the
        rest -- is the difference between "stadium models work" and a modder
        opening scenes at random until they give up.
        """

        state = self._stadium_browser
        if state is None:
            return
        checkbox = state.editable_only
        editable_only = checkbox is not None and checkbox.isChecked()
        editable = tuple(scene for scene in state.scenes if scene.geometry_targets)
        rows = editable if editable_only else state.scenes
        previous = state.selected_scene_id
        state.scene_list.blockSignals(True)
        state.scene_list.clear()
        selected_row = -1
        for index, scene in enumerate(rows):
            writable = bool(scene.geometry_targets)
            label = f"Outer {scene.outer_index} / chunk {scene.chunk_index}"
            if writable:
                label = (
                    f"✎ {label}\n{len(scene.geometry_targets)} editable meshes"
                )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, scene.scene_id)
            item.setToolTip(
                f"{scene.scene_id} • {scene.mesh_count} meshes • "
                f"{scene.vertex_count:,} vertices"
                + (
                    "\nEdited glTF positions can be imported for this scene."
                    if writable
                    else "\nView and glTF export only: no geometry target is "
                    "catalogued for this scene, so Import has nothing to write."
                )
            )
            item.setSizeHint(QSize(260, 56 if writable else 44))
            state.scene_list.addItem(item)
            if scene.scene_id == previous:
                selected_row = index
        state.scene_list.blockSignals(False)
        if checkbox is not None:
            checkbox.setText(
                f"Only scenes with editable geometry ({len(editable)})"
            )
        state.count_label.setText(
            f"{len(rows):,} / {len(state.scenes):,}"
            if editable_only
            else f"{len(rows):,}"
        )
        if not rows:
            state.selected_scene_id = None
            state.scene_label.setText("No matching stadium scenes")
            state.scene_metadata.setText("Try a broader outer/scene search.")
            state.viewport.set_model(None)
            return
        if selected_row < 0:
            # Land on a writable scene when the list holds one, so the first
            # thing a modder sees is the scene Import actually accepts.
            selected_row = next(
                (
                    index
                    for index, scene in enumerate(rows)
                    if scene.geometry_targets
                ),
                0,
            )
        # The list was cleared, so its current row is -1 and this assignment
        # always emits currentItemChanged -> _select_stadium_scene.
        state.scene_list.setCurrentRow(selected_row)

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
        state.selected_scene_id = scene_id
        button = getattr(self, "_stadium_export_scene_button", None)
        if button is not None:
            button.setEnabled(True)
        import_button = getattr(self, "_stadium_import_scene_button", None)
        if import_button is not None:
            import_button.setEnabled(True)
        apply_textures_button = getattr(self, "_stadium_apply_textures_button", None)
        if apply_textures_button is not None:
            apply_textures_button.setEnabled(True)
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
        scene = next((
            row for row in state.scenes
            if row.scene_id == state.selected_scene_id
        ), None)
        export_scene = getattr(self, "_stadium_export_scene_button", None)
        if export_scene is not None:
            # Stay clickable when blocked — never a silent gray Import/Export.
            export_scene.setEnabled(True)
            if not ready:
                tip = (
                    "Load your NFL 2K5 XISO and open Stadium Studio before exporting a model."
                )
            elif scene is None:
                tip = "Select a stadium scene in the list first, then export its glTF."
            else:
                tip = (
                    "Save the selected stadium as a glTF you can open in Blender. "
                    "The buffer is written beside it; edit positions only for re-import."
                )
            export_scene.setToolTip(tip)
            export_scene.setProperty(
                "disableReason", "" if (ready and scene is not None) else tip
            )
        import_scene = getattr(self, "_stadium_import_scene_button", None)
        if import_scene is not None:
            import_scene.setEnabled(True)
            if not ready:
                tip = (
                    "Load your NFL 2K5 XISO first — Import edited model needs a prepared "
                    "Stadium Studio scene. Topology must match the export."
                )
            elif scene is None:
                tip = (
                    "Select a stadium scene first. Import is same-topology position-only; "
                    "vertex count and faces must match the export."
                )
            else:
                tip = (
                    "Import the matching glTF after moving vertices in Blender. Vertex "
                    "count and faces must stay unchanged; Mod Studio keeps the game's "
                    "original UV, material, collision, selector, and other stream bytes."
                )
            import_scene.setToolTip(tip)
            import_scene.setProperty(
                "disableReason", "" if (ready and scene is not None) else tip
            )
        apply_textures = getattr(self, "_stadium_apply_textures_button", None)
        if apply_textures is not None:
            apply_textures.setEnabled(True)
            if not ready:
                tip = (
                    "Load your NFL 2K5 XISO first — Apply textures from glTF needs "
                    "a prepared Stadium Studio scene."
                )
            elif scene is None:
                tip = (
                    "Select a stadium scene first, then apply the textures you "
                    "edited in its exported glTF."
                )
            else:
                tip = (
                    "Apply the textures you edited in Blender back into the game. "
                    "Export embeds each stadium texture into the glTF; edit those "
                    "images, re-export, and this writes them back through the "
                    "bounded writer, matched by nfl2k5_texture_id or material name."
                )
            apply_textures.setToolTip(tip)
            apply_textures.setProperty(
                "disableReason", "" if (ready and scene is not None) else tip
            )
        # Never silent-gray texture export/replace/revert.
        if not ready:
            tex_block = "Load your NFL 2K5 XISO first (and wait for busy ops)."
        elif texture is None:
            tex_block = "Select a stadium surface texture first."
        else:
            tex_block = ""
        state.export_button.setEnabled(True)
        state.export_button.setToolTip(
            tex_block or "Export this stadium surface texture as PNG."
        )
        state.export_button.setProperty("disableReason", tex_block)
        editable = texture is not None and texture.access_status == STADIUM_EDITABLE
        if editable and ready:
            rep_block = ""
            rep_tip = "Replace this editable stadium texture (auto-resize on import)."
        elif tex_block:
            rep_block = rep_tip = tex_block
        elif texture is not None:
            rep_block = rep_tip = (
                f"Texture {texture.texture_index} is not editable "
                f"({texture.access_status}). Export only."
            )
        else:
            rep_block = rep_tip = "Select an editable stadium texture first."
        state.replace_button.setEnabled(True)
        state.replace_button.setToolTip(rep_tip)
        state.replace_button.setProperty("disableReason", rep_block)
        modified = set(getattr(self.facade, "modified_asset_ids", ()))
        can_revert = bool(
            ready and editable and texture is not None and texture.texture_id in modified
        )
        if can_revert:
            rev_block = ""
            rev_tip = "Revert staged stadium texture replacement."
        elif rep_block:
            rev_block = rev_tip = rep_block
        else:
            rev_block = rev_tip = "Nothing to revert—this texture is still original."
        state.revert_button.setEnabled(True)
        state.revert_button.setToolTip(rev_tip)
        state.revert_button.setProperty("disableReason", rev_block)
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
        reason = str(state.export_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
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

    def _export_stadium_scene_gltf(self) -> None:
        """Save the selected stadium model so it can be opened in Blender."""

        export_scene = getattr(self, "_stadium_export_scene_button", None)
        reason = ""
        if export_scene is not None:
            reason = str(export_scene.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Export stadium model", reason)
            return
        state = self._stadium_browser
        if state is None or state.selected_scene_id is None:
            QMessageBox.information(
                self,
                "Export stadium model",
                "Select a stadium scene in the list first, then export its glTF.",
            )
            return
        scene_id = state.selected_scene_id
        scene = next(
            (row for row in state.scenes if row.scene_id == scene_id), None
        )
        if scene is None:
            QMessageBox.information(
                self,
                "Export stadium model",
                "Select a stadium scene in the list first, then export its glTF.",
            )
            return

        suggested = f"stadium-{scene.outer_index}-{scene.chunk_index}.gltf"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export stadium model",
            str(Path.home() / suggested),
            "glTF model (*.gltf)",
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.casefold() != ".gltf":
            destination = destination.with_suffix(".gltf")

        def success(result: object) -> None:
            # Two files land, not one, and the second is the one people lose.
            # An export is an explicit action, so it gets an explicit answer
            # saying where both went and what to open.
            try:
                gltf_path, bin_path = result  # type: ignore[misc]
            except (TypeError, ValueError):
                self._set_status("Exported stadium model")
                return
            gltf_path = Path(gltf_path)
            bin_path = Path(bin_path)
            self._set_status(f"Exported {gltf_path.name}")
            box = QMessageBox(self)
            box.setWindowTitle("Stadium model exported")
            box.setIcon(QMessageBox.Information)
            box.setText(f"Saved to {gltf_path.parent}")
            box.setInformativeText(
                f"Open {gltf_path.name} in Blender.\n\n"
                f"{bin_path.name} holds the geometry and must stay in the same "
                "folder. Move or copy both together.\n\n"
                "The model is scaled to metres so it opens at a normal size. "
                "The game stores it in centimetres, which is why an unscaled "
                "export looks about a hundred times too big."
            )
            open_button = box.addButton("Open folder", QMessageBox.ActionRole)
            box.addButton("Close", QMessageBox.RejectRole)
            box.exec_()
            if box.clickedButton() is open_button:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(gltf_path.parent))
                )

        self._start_task(
            lambda progress: self.facade.export_stadium_scene_gltf(
                scene_id, destination, progress
            ),
            success,
            label="Exporting stadium model",
            blocking=True,
        )

    def _import_stadium_scene_gltf(self) -> None:
        """Stage a bounded vertex-only edit from the selected scene's glTF."""

        import_scene = getattr(self, "_stadium_import_scene_button", None)
        reason = ""
        if import_scene is not None:
            reason = str(import_scene.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Import edited model", reason)
            return
        state = self._stadium_browser
        if state is None or state.selected_scene_id is None:
            QMessageBox.information(
                self,
                "Import edited model",
                "Select a stadium scene first (same-topology position import).",
            )
            return
        scene = next((
            row for row in state.scenes
            if row.scene_id == state.selected_scene_id
        ), None)
        if scene is None or not scene.geometry_targets:
            self._show_error(
                "That Stadium model is export-only. Choose the full scene whose "
                "fixed position lanes are marked importable."
            )
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import edited stadium model",
            str(Path.home()),
            "glTF model (*.gltf)",
        )
        if not filename:
            return
        supplied = Path(filename)
        answer = QMessageBox.question(
            self,
            "Import edited stadium model?",
            "Mod Studio will accept moved vertices only. The model must keep the "
            "same meshes, vertex counts, and faces as the exported scene.\n\n"
            "UVs, materials, collision data, and all non-position game streams "
            "will stay byte-for-byte from your source copy.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        def success(result: object) -> None:
            self._set_status(_result_message(
                result, "Edited Stadium model staged."
            ))
            self._mark_workspace_changed()
            self._refresh_action_states()

        self._start_task(
            lambda progress: self.facade.import_stadium_scene_gltf(
                scene.scene_id, supplied, progress
            ),
            success,
            label="Importing edited stadium model",
            blocking=True,
        )

    def _apply_stadium_textures_from_gltf(self) -> None:
        """Write Blender-edited glTF images back to their stadium texture slots."""

        apply_textures = getattr(self, "_stadium_apply_textures_button", None)
        reason = ""
        if apply_textures is not None:
            reason = str(apply_textures.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Apply textures from glTF", reason)
            return
        state = self._stadium_browser
        if state is None or state.selected_scene_id is None:
            QMessageBox.information(
                self,
                "Apply textures from glTF",
                "Select a stadium scene first, then apply the textures you edited "
                "in its exported glTF.",
            )
            return
        scene_id = state.selected_scene_id
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Apply edited stadium textures from glTF",
            str(Path.home()),
            "glTF model (*.gltf)",
        )
        if not filename:
            return
        supplied = Path(filename)

        def success(result: object) -> None:
            receipts = result if isinstance(result, tuple) else ()
            lines = "\n".join(
                f"{receipt.texture_id}: "
                f"{_result_message(receipt.write_result, 'written')}"
                for receipt in receipts
            )
            box = QMessageBox(self)
            box.setWindowTitle("Stadium textures applied")
            box.setIcon(QMessageBox.Information)
            box.setText(
                f"Wrote {len(receipts)} edited stadium texture(s) through the "
                "bounded writer."
            )
            box.setInformativeText(lines)
            box.addButton("Close", QMessageBox.RejectRole)
            box.exec_()
            self._set_status(f"Applied {len(receipts)} edited stadium texture(s).")
            self._mark_workspace_changed()
            self._select_stadium_texture(state.texture_list.currentItem(), None)

        self._start_task(
            lambda progress: self.facade.replace_stadium_textures_from_gltf(
                scene_id, supplied, progress
            ),
            success,
            label="Applying edited stadium textures",
            blocking=True,
        )

    def _choose_stadium_texture_replacement(self) -> None:
        state = self._stadium_browser
        if state is None:
            return
        reason = str(state.replace_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
            return
        texture = self._stadium_texture(state.selected_texture_id)
        if texture is None or texture.access_status != STADIUM_EDITABLE:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an image for this stadium texture (any size or format)",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
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
                "that texture format back into the game. Fix: choose a texture "
                "listed as Editable and drop your image there instead."
            )
            return
        self._replace_stadium_texture(texture, Path(supplied))

    def _replace_stadium_texture(
        self, texture: StadiumTexture, supplied: Path
    ) -> None:
        state = self._stadium_browser
        assert state is not None
        # Stadium textures are exact-size too, so offer the same resize rather
        # than refusing an off-size PNG.
        width = getattr(texture, "width", None)
        height = getattr(texture, "height", None)
        if isinstance(width, int) and isinstance(height, int) and width and height:
            fitted = self._fit_for_slot(
                supplied, width, height, "This stadium texture"
            )
            if fitted is None:
                return
            supplied = fitted

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
        reason = str(state.revert_button.property("disableReason") or "").strip()
        if reason:
            self._show_error(reason)
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
            f"{uniform_set.style_label} · {uniform_set.side_name.title()} · "
            "39 editable parts · 45 equipment textures"
        )
        self.uniform_metadata.setToolTip(f"Uniform set {uniform_set.selector}")
        self._refresh_team_kit_scope_labels()
        self._populate_components(uniform_set)
        if hasattr(self, "unif_color_set"):
            self.unif_color_search.clear()
            index = self.unif_color_set.findData(uniform_set.selector)
            if index >= 0:
                self.unif_color_set.setCurrentIndex(index)

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

    def _browse_selected_uniform_equipment(self) -> None:
        """Open the canonical visual browser on one set's equipment records."""

        uniform_set = self._selected_set
        if uniform_set is None:
            self._show_error(
                "Choose a physical uniform set before browsing its equipment."
            )
            return
        state = self._visual_browsers.get(ProductCategory.TEXTURES)
        if state is None:
            self._show_error("The All Textures browser is unavailable.")
            return

        state.group_filter.setCurrentIndex(0)
        state.search.setText(f"{uniform_set.selector} equipment")
        self._filter_visual_assets(ProductCategory.TEXTURES)
        if state.asset_list.count() != 45:
            self._show_error(
                f"Expected 45 equipment textures for {uniform_set.selector}, "
                f"but found {state.asset_list.count()}."
            )
            return

        row = PRODUCT_CATEGORY_ORDER.index(ProductCategory.TEXTURES) + 1
        self.navigation.setCurrentRow(row)
        self._set_status(
            f"Showing all 45 package-local equipment textures for "
            f"{uniform_set.selector}. Refine the search with socks, gloves, "
            "shoes, sleeves, pads, or wristbands; the existing Export, Edit, "
            "Replace, Revert, project, and Build paths remain in use."
        )

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
            f"{asset.label}: this slot holds an exact {asset.width} × {asset.height} "
            "image. Drop or choose any image, in any size or format — Mod Studio "
            "resizes it to the slot for you before anything enters your project."
        )
        self._refresh_action_states()
        if bool(getattr(self.facade, "source_ready", False)):
            self._load_preview(asset)
        else:
            self.preview.set_empty(
                f"{asset.label}\n{asset.width} × {asset.height} RGBA PNG\n\n"
                "Open your game disc to see this image."
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
        if self._refuse_while_audio_busy("open another disc"):
            return
        state = self._workspace_state()
        recent_sources = tuple(getattr(state, "recent_sources", ()))
        initial = Path(recent_sources[0]).parent if recent_sources else Path.home()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open ESPN NFL 2K5 for Xbox (.iso)",
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
        if self._refuse_while_audio_busy("open another disc"):
            return
        self._continue_after_unsaved(
            "Opening another disc",
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
        if self._refuse_while_audio_busy("open another disc"):
            return
        if self._audio_panel is not None:
            self._audio_panel.invalidate_preview_for_source_change()

        def failed(_message: str) -> None:
            if self._audio_panel is not None:
                self._audio_panel.recover_after_source_change_failure()

        def success(result: object) -> None:
            self._clear_texture_master_drafts()
            display = str(getattr(self.facade, "source_display_name", "") or source.name)
            self.source_pill.setText(f"●  Disc: {display}")
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
            self._set_status(_result_message(result, "Disc opened — choose a task on the left."))
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
                self._load_selected_unif_colors()
                self._prefill_panels_from_source(self._active_source_path)

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

    def _choose_digit_sheet_import(self) -> None:
        """Split a 0–9 font sheet and import all ten exact slots atomically."""

        uniform_set = self._selected_set
        if uniform_set is None:
            self._show_error("Choose a physical uniform set before importing digits.")
            return
        if not bool(getattr(self.facade, "source_ready", False)):
            self._show_error("Load your NFL 2K5 XISO before importing digits.")
            return
        choices = (
            ("Jersey numbers", "jersey"),
            ("Helmet numbers", "helmet"),
            ("Arm / shoulder numbers", "arm"),
        )
        current_family = getattr(self._selected_asset, "family", None)
        current = next(
            (index for index, (_label, family) in enumerate(choices)
             if family == current_family),
            0,
        )
        label, accepted = QInputDialog.getItem(
            self,
            "Import a complete 0–9 digit sheet",
            "Which digit family should this sheet replace?",
            [row[0] for row in choices],
            current,
            False,
        )
        if not accepted:
            return
        family = dict(choices).get(str(label))
        if family is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose the {label.lower()} 0–9 sheet",
            str(Path.home()),
            IMAGE_IMPORT_FILTER,
        )
        if not filename:
            return
        targets = tuple(
            asset
            for asset in self.uniform_catalog.assets_for_set(uniform_set.selector)
            if asset.kind == "live_number_nameplate"
            and asset.family == family
            and asset.digit is not None
        )
        source = Path(filename)

        def operation(progress: ProgressSink) -> object:
            progress("Splitting the 0–9 sheet", 0, 12)
            outputs = split_digit_sheet(source, targets)
            with tempfile.TemporaryDirectory(prefix="2k5-digit-sheet-") as temporary:
                root = Path(temporary)
                kit = root / "team-kit"
                self.facade.export_team_kit_sets(
                    (uniform_set.selector,),
                    destination=kit,
                    container="folder",
                    progress=lambda _label, _completed, _total: None,
                )
                manifest_path = kit / TEAM_KIT_MANIFEST
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                rows = manifest.get("assets")
                if not isinstance(rows, list):
                    raise ValidationError("The private Team Kit manifest is incomplete.")
                files = {
                    str(row.get("asset_id")): str(row.get("path"))
                    for row in rows if isinstance(row, dict)
                }
                for index, output in enumerate(outputs, 1):
                    relative = files.get(output.asset_id)
                    if not relative:
                        raise ValidationError(
                            f"The Team Kit omitted digit {output.digit}."
                        )
                    destination = (kit / relative).resolve(strict=True)
                    try:
                        destination.relative_to(kit.resolve(strict=True))
                    except ValueError as exc:
                        raise ValidationError(
                            "The Team Kit digit path escapes its private folder."
                        ) from exc
                    destination.write_bytes(output.png)
                    progress(
                        f"Prepared {label} {output.digit} at "
                        f"{output.width}×{output.height}",
                        index,
                        12,
                    )
                progress("Validating all ten digits as one import", 11, 12)
                result = self.facade.import_team_kit(
                    kit, lambda _label, _completed, _total: None
                )
            progress("Digit sheet imported", 12, 12)
            return result

        def success(result: object) -> None:
            changed = int(getattr(result, "changed_count", 0))
            if changed:
                self._mark_workspace_changed(rebuild_components=True)
                if self._selected_asset is not None:
                    self._preview_selected_asset()
            else:
                self._refresh_edit_state(rebuild_components=True)
            self.team_kit_imported.emit(changed)
            QMessageBox.information(
                self,
                "Digit sheet import complete",
                f"{label} for {uniform_set.selector} were split into ten exact "
                f"game slots. {changed} changed digit"
                f"{'s were' if changed != 1 else ' was'} staged as one Undo action.\n\n"
                "The source XISO was not changed.",
            )

        self._start_task(
            operation,
            success,
            label=f"Importing {label.lower()} 0–9 sheet",
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
            # v1 projects intentionally contain compiled native PNGs only. A
            # loaded project therefore cannot honestly recreate an import-time
            # full-resolution master or transform.
            self._clear_texture_master_drafts()
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
                self._load_selected_unif_colors()

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
            IMAGE_IMPORT_FILTER,
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
        # Offer to resize here too.  _fit_for_slot was only wired into the
        # visual browser, so every import through this path -- the file dialog
        # and drag-and-drop both land here -- refused an off-size PNG outright
        # instead of offering to fit it, which is the one thing the resizer
        # exists to prevent.
        width = getattr(asset, "width", None)
        height = getattr(asset, "height", None)
        if isinstance(width, int) and isinstance(height, int) and width and height:
            fitted = self._fit_for_slot(
                path, width, height, getattr(asset, "label", "This asset")
            )
            if fitted is None:
                return
            path = fitted

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

    def _check_staged_images(self) -> None:
        """Say what the fixed slots will do to the staged art, before a build.

        The build's palette ladder is lossy and used to be silent: a jersey
        could come out with 16 colours instead of 255 and the only way to learn
        that was to look at the result. This answers the question first.
        """

        if self._refuse_while_audio_busy("check staged images"):
            return
        self._start_task(
            lambda progress: self.facade.preflight_visual_edits(progress),
            self._present_image_check,
            label="Checking your images against their slots",
            blocking=True,
        )

    def _present_image_check(self, result: object) -> None:
        from mod_editor.core import nfl2k5_import_preflight as preflight

        rows = tuple(result or ())
        if not rows:
            self._set_status("Nothing is staged, so there is nothing to check.")
            QMessageBox.information(
                self,
                "Nothing to check",
                "Replace at least one image before checking. This looks at the "
                "PNGs you have staged, not at the whole game.",
            )
            return

        refused = [row for row in rows if row.outcome == preflight.REFUSED]
        reduced = [row for row in rows if row.outcome == preflight.REDUCED]
        full = [row for row in rows if row.outcome == preflight.FULL]
        unmodelled = [row for row in rows if row.outcome == preflight.UNMODELLED]

        if refused:
            headline = (
                f"{len(refused)} of {len(rows)} will not fit and will stop the build."
            )
        elif reduced:
            headline = (
                f"{len(reduced)} of {len(rows)} will build, but lose colours to "
                "fit a fixed slot."
            )
        elif full and not unmodelled:
            headline = f"All {len(rows)} fit as authored, untouched."
        elif full:
            # Saying "all N fit" when some of them were never checked would be a
            # claim this cannot support. Count only what was actually predicted.
            headline = (
                f"{len(full)} of {len(rows)} fit as authored; "
                f"{len(unmodelled)} could not be checked here."
            )
        else:
            headline = (
                f"None of these {len(rows)} could be checked here — they will be "
                "decided at build time."
            )

        self._set_status(f"Image check — {headline}")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if refused else QMessageBox.Information)
        box.setWindowTitle("Image check")
        box.setText(headline)
        if refused or reduced:
            box.setInformativeText(CHECK_IMAGES_ADVICE)
        elif full and len(full) == len(rows):
            box.setInformativeText(
                "Nothing will be changed to make your art fit."
            )
        elif unmodelled:
            box.setInformativeText(
                "A slot is only predicted when its fixed size is known. The "
                "build still checks every one of them."
            )
        box.setDetailedText("\n".join(row.summary() for row in rows))
        box.exec_()

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

    def _configure_xemu(self) -> None:
        """Let the user point at their own xemu build."""

        chosen, _selected = QFileDialog.getOpenFileName(
            self,
            "Choose the xemu program",
            str(Path.home()),
            "All files (*)",
        )
        if not chosen:
            return
        try:
            command = self.facade.configure_xemu(Path(chosen))
        except Exception as exc:  # ValidationError and OS-level refusals
            self._show_error(str(exc))
            return
        self._set_status(f"xemu set to {command[0]}. Play latest disc in xemu is ready once a disc has been made.")
        self._refresh_action_states()

    def _launch_xemu(self) -> None:
        if self._refuse_while_audio_busy("launch xemu"):
            return
        blocker = str(getattr(self.facade, "xemu_blocker", "") or "")
        if blocker:
            # Clicking a blocked action must teach, and when the fix is
            # "tell me where xemu is" it must also offer to do it.
            if "Configure xemu" in blocker:
                answer = QMessageBox.question(
                    self,
                    "xemu is not set up yet",
                    blocker + "\n\nChoose the xemu program now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    self._configure_xemu()
                return
            QMessageBox.information(self, "Cannot launch xemu yet", blocker)
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
        on_progress: Callable[[str, int, int], None] | None = None,
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
        if on_progress is not None:
            # A non-blocking task does not own the footer progress strip, but it
            # can still be a long one -- the first stadium derivation runs for
            # ten to thirty minutes. Without this a caller had no way to report
            # progress at all, so that job showed a single static label for its
            # whole run and read as hung.
            worker.signals.progress.connect(
                lambda stage, done, total: on_progress(stage, done, total)
            )

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
        # Pages are built before the footer that owns this label, and a page
        # constructed against an already-loaded game can report status during
        # construction. Remember the message instead of raising: the window
        # appearing at all matters more than one early status line.
        status = getattr(self, "operation_status", None)
        if status is None:
            self._pending_status = message
            return
        status.setText(message)
        # The label elides to fit whatever width the footer has; the whole
        # sentence stays readable on hover rather than being lost.
        status.setToolTip(message)

    def _specialized_panel_status(self, message: str) -> None:
        """Forward embedded-panel status once the shared footer exists."""

        if hasattr(self, "operation_status"):
            self._set_status(message)

    def _specialized_panel_refresh(self) -> None:
        """Refresh global edit badges after an embedded panel changes state."""

        if hasattr(self, "edit_count"):
            self._mark_workspace_changed()

    # ------------------------------------------------------------ E2: the open-disc hook
    def _navigation_key(self, row: int) -> str:
        item = self.navigation.item(row)
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _prefill_panels_from_source(self, source: Path | None) -> None:
        """Feed the disc that was just opened to every page that has its own source field.

        The header said "Disc: …" while eleven pages still said "choose a disc".  Each page
        is filled through its own existing load / inspect path, off the UI thread where the
        page already works that way; nothing here writes a file, opens a chooser, or resets a
        roster somebody has edited.  A later open supersedes an earlier one (generation).
        """

        if source is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        source = Path(source)
        self._source_generation += 1
        generation = self._source_generation
        self._last_prefilled_source = source
        self._refresh_welcome_state()
        # 1. one inspection for Build, Game Fixes and Position names
        self._source_inspect_pending = True
        for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
            if panel is not None and hasattr(panel, "begin_reading"):
                panel.begin_reading(source)

        def inspected(state: object) -> None:
            if generation != self._source_generation:
                return
            self._source_inspect_pending = False
            if not isinstance(state, dict):
                return
            for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
                if panel is not None:
                    panel.apply_state(state)
            self._describe_source_pill(state)
            self._refresh_welcome_state()

        def inspect_failed(message: str) -> None:
            if generation != self._source_generation:
                return
            self._source_inspect_pending = False
            for panel in (self._build_panel, self._gameplay_patches_panel, self._edge_panel):
                if panel is not None and hasattr(panel, "reading_failed"):
                    panel.reading_failed(message)

        worker = _BackgroundTask(lambda progress: mod_build.inspect(source))
        self._workers.add(worker)
        worker.signals.result.connect(inspected)
        worker.signals.error.connect(inspect_failed)
        worker.signals.finished.connect(lambda: self._workers.discard(worker))
        self.thread_pool.start(worker)
        # 2. pages with their own background readers
        if self._throw_tuning_panel is not None:
            self._throw_tuning_panel.load_source(source, quiet=True)
        if self._presentation_panel is not None:
            self._presentation_panel.load_source(source)
        if self._commentary_panel is not None:
            self._commentary_panel.load_source(source)
        if self._sounds_panel is not None:
            self._sounds_panel.load_source(source)
        if self._bump_panel is not None:
            self._bump_panel.load_source(source)
        if self._models_panel is not None:
            self._models_panel.reload()
        # 3. Share: the export "Starting disc" only while no build owns the pair; the
        #    install "Your disc" whenever it is empty or still following the last disc
        if self._share_panel is not None:
            self._share_panel.follow_source(source)
        # 4. ★ Rosters: only an empty or auto-filled, unedited session follows the disc,
        #    and only when the page is entered (an edited roster is never reset)
        self._roster_prefill_pending = True
        if self._navigation_key(self.navigation.currentRow()) == "rosters":
            self._prefill_roster_if_pending()
        self._refresh_player_assets_hint()

    def _prefill_roster_if_pending(self) -> None:
        if not self._roster_prefill_pending:
            return
        panel = self._roster_editor_panel
        if panel is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        self._roster_prefill_pending = False
        if panel.document is not None and not (panel.auto_filled and not panel.is_dirty()):
            display = str(getattr(self.facade, "source_display_name", "") or "the disc")
            panel.note_other_source(display)
            return
        panel.load_from_facade()

    def _describe_source_pill(self, state: Mapping[str, object]) -> None:
        """Header pill: the disc's name, and only the classification the identity check found."""

        display = str(getattr(self.facade, "source_display_name", "") or "")
        if not display:
            return
        identity = state.get("disc_identity")
        kind = str(identity.get("kind", "")) if isinstance(identity, Mapping) else ""
        badge = {"retail-xiso": "original", "retail-raw": "original",
                 "repack": "repacked", "modified": "modified"}.get(kind, "")
        self.source_pill.setText(f"●  Disc: {display}" + (f" · {badge}" if badge else ""))
        line = str(state.get("disc_identity_line") or "")
        self.source_pill.setToolTip(
            (line + "\n\n" if line else "")
            + "The game disc the app is reading. Click Open game disc… to change it."
        )
        self.source_pill.setAccessibleDescription(self.source_pill.toolTip())

    def _refresh_welcome_state(self) -> None:
        """Getting Started says what is open and what to do next (GS-04)."""

        ready_label = getattr(self, "welcome_ready", None)
        sub_label = getattr(self, "welcome_ready_sub", None)
        if ready_label is None or sub_label is None:
            return
        if bool(getattr(self.facade, "source_ready", False)):
            display = str(getattr(self.facade, "source_display_name", "") or "your disc")
            ready_label.setText(f"Disc open: {display}")
            sub_label.setText("Next: choose SOFTDRINK patches or edit rosters.")
        else:
            ready_label.setText("Start here")
            sub_label.setText("Open a game disc file for disc edits. To edit a roster save, go to ★ Rosters.")
        for button in getattr(self, "welcome_task_buttons", ()):
            button.setEnabled(True)

    def _refresh_player_assets_hint(self) -> None:
        search = getattr(self, "player_asset_search", None)
        if search is None:
            return
        if bool(getattr(self.facade, "source_ready", False)):
            search.setPlaceholderText("Player name…")
            if not self.player_asset_list.count():
                self.player_asset_detail.setText("Type a name above.")
        else:
            search.setPlaceholderText("Player name…  (open your game disc first)")

    def _register_external_disc(self, path: str) -> None:
        """A disc written by ★ Rosters, ★ Models or Share is a disc Play latest can start (M09)."""

        if not path:
            return
        try:
            self.facade.register_external_build(Path(path))
        except Exception as exc:  # noqa: BLE001 - a missing file only means Play stays blocked
            self._set_status(str(exc))
            return
        self._refresh_action_states()
        self._set_status(f"Disc ready: {Path(path).name}. Play latest disc in xemu starts this copy.")

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
            self._close_texture_master_workspace()
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
            self._close_texture_master_workspace()
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
                self._close_texture_master_workspace()
                event.accept()
        elif decision == "save":
            event.ignore()
            self._save_project(after_success=self._finish_close_after_save)
        else:
            event.ignore()

    def _show_error(self, message: str) -> None:
        hint = friendly_fix_hint(message)
        body = message if hint is None else f"{message}\n\n{hint}"
        QMessageBox.warning(
            self,
            "Couldn't finish that",
            body + "\n\nYour original game disc was not changed.",
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
                f"Save this project's edits to {save_target} (a .2k5mod file: your "
                "replacements and text, never game data). ★ Rosters has separate save buttons."
            )
        elif self._workspace_dirty:
            self.setWindowTitle("Untitled* — 2K5 Mod Studio")
            save_tip = (
                "Save the edits in this project as a .2k5mod file you can reopen or share. "
                "★ Rosters has separate save buttons."
            )
        else:
            self.setWindowTitle("2K5 Mod Studio")
            save_tip = (
                "Save the edits in this project as a .2k5mod file. ★ Rosters has separate save buttons."
            )
        self.save_project_button.setToolTip(save_tip)
        if self._save_project_action is not None:
            self._save_project_action.setToolTip(save_tip)

    def _refresh_edit_state(self, *, rebuild_components: bool = False) -> None:
        count = int(getattr(self.facade, "modified_count", 0))
        metadata_count = int(getattr(self.facade, "project_metadata_count", 0))
        self.edit_count.setText(
            f"{count} project edit{'s' if count != 1 else ''} • "
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''}"
            if count and metadata_count else
            f"{metadata_count} cue label{'s' if metadata_count != 1 else ''} • "
            "no project edits"
            if metadata_count else
            "No project edits • unsaved"
            if count == 0 and self._workspace_dirty else
            "No project edits" if count == 0
            else f"{count} project edit{'s' if count != 1 else ''}"
        )
        ready = bool(getattr(self.facade, "source_ready", False))
        if ready:
            display = str(getattr(self.facade, "source_display_name", "NFL 2K5"))
            self.source_pill.setText(f"●  Disc: {display}")
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
            self.import_digit_sheet_button.setEnabled(
                ready and self._selected_set is not None and not global_busy
            )
            self.team_kit_scope.setEnabled(
                self._selected_set is not None and not global_busy
            )
            self.team_kit_container.setEnabled(not global_busy)
            self.browse_uniform_equipment_button.setEnabled(
                self._selected_set is not None and not global_busy
            )
        if hasattr(self, "unif_color_set"):
            has_colour_set = self._selected_unif_color_selector() is not None
            loaded_colour_set = (
                has_colour_set
                and self._unif_color_loaded_selector
                == self._selected_unif_color_selector()
            )
            colour_enabled = ready and loaded_colour_set and not global_busy
            self.unif_color_search.setEnabled(not global_busy)
            self.unif_color_set.setEnabled(not global_busy)
            # Keep colour buttons clickable so blocked states never look dead:
            # tooltips + disableReason explain Load XISO / pick set / wait.
            if not ready:
                colour_reason = (
                    "Load your NFL 2K5 XISO first to read this uniform's "
                    "facemask and turtleneck colours (per physical set)."
                )
            elif not has_colour_set:
                colour_reason = (
                    "No uniform set matches that filter. Clear the colour "
                    "search box to list every physical set."
                )
            elif not loaded_colour_set:
                colour_reason = (
                    "Pick a uniform set and wait for its original colours to "
                    "finish loading before editing."
                )
            elif global_busy:
                colour_reason = "Wait for the current operation to finish."
            else:
                colour_reason = ""
            for button in (
                self.facemask_button,
                self.turtleneck_button,
                self.unif_color_apply,
            ):
                button.setEnabled(True)
                if colour_reason:
                    button.setToolTip(colour_reason)
                button.setProperty("disableReason", colour_reason)
            # Revert: never silent-gray; explain when nothing staged.
            self.unif_color_revert.setEnabled(True)
            if colour_reason:
                revert_reason = colour_reason
            elif not self._selected_unif_color_modified:
                revert_reason = (
                    "Nothing to revert—this uniform set's colours are still original."
                )
            else:
                revert_reason = ""
            self.unif_color_revert.setToolTip(
                revert_reason
                or "Restore original facemask and turtleneck for this physical set."
            )
            self.unif_color_revert.setProperty("disableReason", revert_reason)
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
        # A disabled button that gives no reason reads as a broken one.  A modder
        # reported being unable to rebuild the XISO, and loading a disc then
        # pressing Build before making an edit does exactly nothing: no dialog, no
        # status change, and the only clue is a small edit-count chip several
        # widgets away.  Name the actual blocker instead.  Qt shows tooltips on
        # disabled widgets, and the launch button below already varies its own
        # text the same way.
        self.build_button.setToolTip(
            _build_blocker_message(
                ready=ready, edit_count=count, busy=global_busy
            )
        )
        self.build_button.setAccessibleDescription(self.build_button.toolTip())
        # Same gate as Build, and the same rule about naming the blocker: this
        # checks the staged edits, so with none there is nothing to check.
        self.check_images_button.setEnabled(ready and count > 0 and not global_busy)
        if not ready:
            check_blocker = "Open your game disc first."
        elif count <= 0:
            check_blocker = (
                "Replace at least one image first — this checks what you have "
                "staged."
            )
        elif global_busy:
            check_blocker = "An operation is running • wait for it to finish."
        else:
            check_blocker = ""
        self.check_images_button.setToolTip(check_blocker or CHECK_IMAGES_MESSAGE)
        self.check_images_button.setProperty("disableReason", check_blocker)
        self.check_images_button.setAccessibleDescription(
            self.check_images_button.toolTip()
        )
        # Never silent-gray: Launch stays clickable and names the one thing
        # that is actually missing, instead of graying out with a message that
        # covers two unrelated causes at once.
        blocker = _plain_launch_blocker(
            str(getattr(self.facade, "xemu_blocker", "") or "")
        )
        if not blocker and not bool(getattr(self.facade, "can_launch_xemu", False)):
            blocker = "Make a disc first, then use Set up xemu… if xemu is not found."
        if global_busy:
            blocker = blocker or "An operation is running • wait for it to finish."
        self.launch_button.setEnabled(not global_busy)
        latest = None
        try:
            latest = self.facade.last_build_output()
        except Exception:  # noqa: BLE001 - browse-only facades have no build
            latest = None
        self.launch_button.setToolTip(
            blocker or (
                f"Open the most recently made disc in xemu: {Path(str(latest)).name}"
                if latest else "Open the most recently made disc in xemu."
            )
        )
        self.launch_button.setProperty("disableReason", blocker)
        self.launch_button.setAccessibleDescription(self.launch_button.toolTip())
        self.navigation.setEnabled(not global_busy)
        audio_busy = self._embedded_audio_busy
        crib_busy = self._embedded_crib_busy
        for page in self._category_pages.values():
            owns_audio = page is self._audio_panel or (
                self._audio_panel is not None
                and page.isAncestorOf(self._audio_panel)
            )
            owns_crib = page is self._crib_panel or (
                self._crib_panel is not None
                and page.isAncestorOf(self._crib_panel)
            )
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

    def _build_create_play_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        title = QLabel("Create a Play")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(title)
        blurb = QLabel(
            "Five steps: pick a team, line up a formation, choose run or pass, draw supported routes, "
            "and place the play in the playbook. The editor checks the play's structure."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet("font-size: 15px;")
        layout.addWidget(blurb)
        button = QPushButton("Create a play  \u2192")
        button.setStyleSheet("font-size: 20px; font-weight: 600; padding: 14px 26px;")
        button.setMinimumHeight(60)
        button.clicked.connect(self._open_create_play_wizard)
        layout.addWidget(button, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_build_share_page(self) -> QWidget:
        """★ Build & Share: one copy with every patch (Build) and the .2k5patch exchange (Share)."""

        tabs = QTabWidget()
        tabs.setObjectName("buildShareTabs")
        tabs.setAccessibleName("Build and share workspaces")
        self._build_panel = BuildPanel(self.facade)
        self._connect_star_players()
        # ★ Rosters writes a roster-edits document; the Build tab carries it as the roster_edits step
        roster_editor = getattr(self, "_roster_editor_panel", None)
        if roster_editor is not None:
            roster_editor.roster_edits_changed.connect(self._build_panel.set_roster_edits)
            roster_editor.roster_edits_stale.connect(self._build_panel.mark_roster_edits_stale)
        tabs.addTab(self._build_panel, "Build")
        # Share: a .2k5patch (byte runs + the modder's own images/audio + recipe)
        # made from a patched copy, applied to somebody else's own disc copy.
        self._share_panel = SharePanel(self.facade)
        tabs.addTab(self._share_panel, "Share")
        self._build_panel.built.connect(self._share_panel.prefill_from_build)
        self._build_panel.built.connect(self._on_build_tab_built)
        self._share_panel.disc_written.connect(self._register_external_disc)
        if roster_editor is not None:
            roster_editor.disc_written.connect(self._register_external_disc)
        models_panel = getattr(self, "_models_panel", None)
        if models_panel is not None:
            models_panel.disc_written.connect(self._register_external_disc)
        tabs.setCurrentIndex(0)
        return tabs

    def _connect_star_players(self) -> None:
        """★ Star ticks in Rosters & Players are the Build tab's ``player_tags``.

        Either panel may be built first, so this runs after both and does nothing until the
        second one exists."""

        panel = getattr(self, "_roster_panel", None)
        build = getattr(self, "_build_panel", None)
        if panel is None or build is None or self._star_players_connected:
            return
        panel.star_players_changed.connect(build.set_star_players)
        build.set_star_players(panel.star_players(), panel.star_player_names())
        self._star_players_connected = True

    def _open_create_play_wizard(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            QMessageBox.information(self, "Create a Play", "Open your game disc first (the button at the top right).")
            return
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard

        wizard = CreatePlayWizard(self.facade, self)
        wizard.exec_()
        self._mark_workspace_changed()
        self._refresh_edit_state()

    def _refresh_entered_page(
        self, row: int, *, refresh_embedded: bool = True
    ) -> None:
        if self._navigation_key(row) == "rosters":
            self._prefill_roster_if_pending()
            return
        if row <= 0 or row - 1 >= len(PRODUCT_CATEGORY_ORDER):
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

    def _on_build_tab_built(self, receipt: object) -> None:
        """A Build & Share copy is the latest build: Launch Latest Build starts it."""

        target = ""
        if isinstance(receipt, dict):
            target = str(receipt.get("target") or "")
        if not target:
            return
        try:
            self.facade.register_external_build(Path(target))
        except Exception as exc:  # noqa: BLE001 - a missing file only means Launch stays blocked
            self._set_status(str(exc))
            return
        self._refresh_action_states()
        self._set_status(f"Disc ready: {Path(target).name}. Play latest disc in xemu starts this copy.")

    def _refresh_action_bar_for_page(self, row: int) -> None:
        """The bottom bar's texture-project controls make no sense on Build & Share.

        A user built a patched copy there and then stared at a greyed-out
        "Build Modded XISO" / "Check My Images" (both about staged texture edits)
        thinking the build had failed. On that page only xemu controls stay."""

        item = self.navigation.item(row)
        on_build_share = item is not None and item.data(Qt.UserRole) == "build_share"
        for widget in (self.edit_count, self.undo_button, self.revert_all_button,
                       self.check_images_button, self.build_button):
            widget.setVisible(not on_build_share)
        self.build_share_caption.setVisible(on_build_share)

    def _update_header_title(self, row: int) -> None:
        if row <= 0:
            self.page_title.setText("Getting Started")
            return
        if row - 1 >= len(PRODUCT_CATEGORY_ORDER):
            special = row - 1 - len(PRODUCT_CATEGORY_ORDER)
            titles = ("Rosters", "Models", "Create a Play", "Build & Share")
            self.page_title.setText(titles[special] if special < len(titles) else "")
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
             * QTabWidget had no rules at all, so it rendered in the platform
             * style: a light tab strip with near-invisible labels on this dark
             * surface.  Rosters & Players has used tabs since it shipped and
             * inherited the same defect; it became obvious only when Uniforms &
             * Equipment -- the page people open first -- gained a second tab.
             */
            QTabWidget::pane {
                border: 1px solid #1e2b45;
                border-radius: 10px;
                background: #0c1220;
                top: -1px;
            }
            /*
             * The bold weight sits on the bar (the widget's own font), never on the
             * ::tab subcontrol: Qt sizes each tab with the bar's font and paints it
             * with the subcontrol's, so a bold subcontrol clipped every multi-word
             * title on both ends ("Colours & Other Tool", "Structured inspecto").
             */
            QTabBar { background: transparent; font-weight: 600; }
            QTabBar::tab {
                background: #131c30;
                color: #9fb2cd;
                border: 1px solid #1e2b45;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 18px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0c1220;
                color: #6ee7c7;
                border-color: #2b3d5f;
            }
            QTabBar::tab:hover:!selected { color: #edf3fc; }
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
        # Only when this call owns the application: an embedded caller has its
        # own error handling and should not have it replaced. Installing the
        # hook is also what stops PyQt5 aborting the process, so an unexpected
        # error becomes a dialog instead of a window that simply disappears.
        crash_report.install("2K5 Mod Studio")
    app.setApplicationName("2K5 Mod Studio")
    app.setOrganizationName("2K5 Mod Studio")
    # Application-wide, not just per-window: dialogs and the taskbar group take
    # their picture from here, and a window that has one while its own message
    # boxes fall back to the Qt default looks half-finished.
    icon = _window_icon()
    if icon is not None:
        app.setWindowIcon(icon)
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
