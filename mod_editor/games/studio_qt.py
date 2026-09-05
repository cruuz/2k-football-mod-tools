"""The game studio shell: one window per game, every page present and honest.

Core-owned and game-blind.  ``GameStudioDialog(module)`` opens *the* studio of
one game module: the label the core composes from the manifest, the module's
title and platform, and the fourteen pages of
:data:`~mod_editor.games.contract.PAGE_ORDER` in the Xbox studio's order.  A
game writes lanes; it never writes this window.  That is the whole point --
the part a maintainer's assistant cannot break is the part no game owns.

What a page is
--------------

* **A lane page** is the PS2 Disc Studio's ``LaneTab``, generalised.  Build
  catalogue (in a child process, with progress), a scope picker when the lane
  offers scopes, a searchable target table, an editor built from the target's
  own :class:`~mod_editor.games.contract.Field` list, Check (the lane's
  ``check_edit``, verbatim), Add to build, the staged list and the exact
  recipe the patcher will be handed.  A page hosting several lanes shows them
  as sub-tabs, as the Xbox studio does.  Optional protocols add controls and
  nothing else: :class:`~mod_editor.games.contract.ArtLane` gets preview,
  Export PNG, Import PNG and the PCSX2 replacement identity;
  :class:`~mod_editor.games.contract.AudioLane` gets Play and Export WAV;
  :class:`~mod_editor.games.contract.ReadOnlyLane` gets a table and no editor;
  :class:`~mod_editor.games.contract.CodePatchLane` gets the pnach preview.

* **An unavailable page** is a page whose lane does not exist yet, or exists
  and is classified ``unknown`` / ``unsafe/deferred``.  It is present, it has
  its title, and it says exactly why -- the core's sentence, the module's own
  ``page_notes`` sentence, and for a classified-but-not-offered lane the
  registry row's ``gui.reason``.  No controls.  Never a dead button, never a
  hidden page.

* **Build & Share** is the Disc Studio's build page over
  :class:`~mod_editor.games.studio_service.GameStudioService`: the destination
  must not exist, the volume is checked before anything is written, every lane
  with staged edits is one step, each step is verified before the previous
  intermediate is deleted, and one receipt names every step and every verdict.

Honesty is not a page: every writer page carries its registry classification
badge and, when the row is not ``runtime-proved``, upstream's exact
"Not yet tested in-game" qualifier.  The words come from the registry and from
:mod:`mod_editor.gui.ux_text`; this window invents none of them.

Qt is imported at module level here, as in ``chooser_qt``: this module *is*
the window, so a caller that imports it has already decided to draw one.  A
game package must still import it lazily (the boundary check enforces that).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mod_editor.gui.ux_text import NOT_TESTED

from .contract import PAGE_ORDER, ArtLane, AudioLane, CodePatchLane, ContractError, Edit, GameModule, Target, lane_page
from .studio_service import (
    CancelToken,
    Cancelled,
    GameStudioService,
    StudioError,
    is_read_only,
    lane_scopes,
    studio_action_state,
    suggested_destination,
)

BOUNDARY_NOTE = (
    "Your image is opened read-only; every edit lands in a new file. Nothing on "
    "a page changes anything until you build, and a build never writes over "
    "what you opened."
)

#: What a page says when the module has no lane for it yet.  The game's own
#: reason, if it has one, is added underneath from the manifest's ``page_notes``.
UNAVAILABLE_TEMPLATE = "No {title} lane in {studio} yet."

#: What a page says when the lane exists but its evidence does not let the
#: studio offer it.  The registry row's own reason follows.
WITHHELD_TEMPLATE = "{title} is classified {classification} in the capability registry, so this studio does not offer it yet."

#: Classifications a page may be drawn for.  Everything else is withheld with
#: the registry's own sentence rather than half-offered.
OFFERED_CLASSIFICATIONS = (
    "runtime-proved",
    "offline-writer-proved",
    "extract-only",
    "read-only-mapped",
)

_INVALID_COLOUR = "#ff7b84"
_MATCH_COLOUR = "#39d98a"
_WARN_COLOUR = "#e8c46a"
_MUTED_COLOUR = "#8391a8"

_BADGES = {
    "runtime-proved": "PROVED",
    "offline-writer-proved": "PROVED",
    "extract-only": "READ ONLY",
    "read-only-mapped": "READ ONLY",
    "unknown": "PORTME",
    "unsafe/deferred": "PORTME",
}

_REASONS: Optional[Dict[str, str]] = None


def classification_badge(classification: str) -> str:
    """The registry's own badge word for a classification, as the browser shows it."""

    try:
        from mod_editor.core.capabilities import Classification

        return Classification(classification).badge
    except Exception:
        return _BADGES.get(classification, "PORTME")


def honesty_line(classification: str) -> str:
    """The badge, the classification and -- unless runtime-proved -- the qualifier."""

    line = f"{classification_badge(classification)} — {classification}"
    return line if classification == "runtime-proved" else f"{line} · {NOT_TESTED}"


def registry_reasons() -> Dict[str, str]:
    """``capability id -> gui.reason`` from the canonical registry, loaded once.

    The reason a row is not offered is the registry's to state, not this
    window's; a studio that wrote its own would be a second opinion nobody
    checks.  A build without a readable registry still draws every page -- the
    reason line is simply absent.
    """

    global _REASONS
    if _REASONS is None:
        reasons: Dict[str, str] = {}
        try:
            from mod_editor.core.capabilities import CapabilityRegistryLoader

            registry = CapabilityRegistryLoader().load(check_files=False)
            for capability in registry.capabilities:
                gui = capability.raw.get("gui") if isinstance(capability.raw, dict) else None
                if isinstance(gui, dict) and str(gui.get("reason") or "").strip():
                    reasons[capability.capability_id] = str(gui["reason"]).strip()
        except Exception:  # a build without the registry still draws every page
            reasons = {}
        _REASONS = reasons
    return _REASONS


def is_offered(lane: Any) -> bool:
    """Whether a lane's evidence lets the studio draw controls for it."""

    return getattr(lane, "classification", "") in OFFERED_CLASSIFICATIONS


def _monospace() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(max(9, font.pointSize()))
    return font


# --------------------------------------------------------------------------
# Background work
# --------------------------------------------------------------------------

class _TaskSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    stage = pyqtSignal(str)
    finished = pyqtSignal()


class _Task(QRunnable):
    """One service operation off the Qt thread.

    A catalogue decodes for seconds to minutes and a build copies the whole
    source; inside a click handler either would mark the window unresponsive.
    ``signals`` is constructed on the Qt thread, so every emission from
    :meth:`run` arrives as a queued call.
    """

    def __init__(self, operation: Callable[[Callable[[str], None], Any], object], cancel: Any) -> None:
        super().__init__()
        self.operation = operation
        self.cancel = cancel
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.stage.emit, self.cancel)
        except BaseException as exc:  # noqa: BLE001 - the point is to report it
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


# --------------------------------------------------------------------------
# The target table
# --------------------------------------------------------------------------

class TargetTableModel(QAbstractTableModel):
    """A lane's catalogued targets, filtered by a search needle.

    Four columns every contract target has -- what it is, what it is on the
    source, and the fixed allocation it must fit.  The lane's own row is not
    spread across columns here: a shell that guessed at a game's columns would
    be inventing a schema the contract deliberately does not have.
    """

    COLUMNS = (
        ("Target", lambda target: target.label),
        ("Detail", lambda target: target.detail),
        ("Budget", lambda target: target.budget),
        ("Key", lambda target: target.key),
    )

    def __init__(self) -> None:
        super().__init__()
        self._all: List[Target] = []
        self._rows: List[Target] = []
        self._needle = ""

    def set_targets(self, targets: Sequence[Target]) -> None:
        self.beginResetModel()
        self._all = list(targets)
        self._rows = self._filtered()
        self.endResetModel()

    def set_filter(self, needle: str) -> None:
        self._needle = str(needle).strip().lower()
        self.beginResetModel()
        self._rows = self._filtered()
        self.endResetModel()

    def _filtered(self) -> List[Target]:
        if not self._needle:
            return list(self._all)
        words = self._needle.split()
        rows = []
        for row in self._all:
            haystack = f"{row.searchable} {row.key} {row.label} {row.detail}".lower()
            if all(word in haystack for word in words):
                rows.append(row)
        return rows

    def target_at(self, row: int) -> Optional[Target]:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: int, role: int = Qt.DisplayRole) -> object:  # noqa: N802
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self.COLUMNS[section][0]

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = self.target_at(index.row())
        if row is None:
            return None
        if role == Qt.ToolTipRole:
            return f"{row.detail}\n{row.budget}".strip()
        if role != Qt.DisplayRole:
            return None
        try:
            return str(self.COLUMNS[index.column()][1](row))
        except Exception:  # pragma: no cover - a malformed row must not crash the view
            return ""


# --------------------------------------------------------------------------
# The editor, built from Target.fields
# --------------------------------------------------------------------------

class FieldEditor(QWidget):
    """The controls for one target, one row per :class:`Field`.

    The kinds are the contract's, and the mapping is fixed here so every game
    reads the same: ``text`` and ``name_pick`` are a line (a picker when the
    field lists choices), ``int`` and ``float`` are bounded spinners, ``bool``
    a check box, ``choice`` a combo, ``colour_argb`` a hex field with a colour
    picker and a swatch, ``png`` and ``wav`` a file chooser, ``note`` a
    sentence with no control at all.

    A field is the *shape*.  Whether a value fits is the lane's answer and
    only the lane's: :meth:`values` hands back what the user typed and the page
    asks ``check_edit`` about it.
    """

    changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._widgets: Dict[str, Tuple[Any, QWidget]] = {}
        self._fields: Tuple[Any, ...] = ()

    def field_keys(self) -> Tuple[str, ...]:
        return tuple(self._widgets)

    def set_fields(self, fields: Sequence[Any]) -> None:
        """Rebuild the form for a newly selected target."""

        while self._form.rowCount():
            self._form.removeRow(0)
        self._widgets.clear()
        self._fields = tuple(fields)
        for item in self._fields:
            widget = self._make(item)
            if widget is None:
                continue
            label = item.label + (" (read-only)" if item.read_only else "")
            self._form.addRow(label, widget)
            self._widgets[item.key] = (item, widget)
            if item.help:
                widget.setToolTip(item.help)
                widget.setAccessibleDescription(item.help)
            widget.setAccessibleName(item.label)
            widget.setEnabled(not item.read_only)

    def _make(self, item: Any) -> Optional[QWidget]:
        kind = item.kind
        if kind == "note":
            note = QLabel(item.help or item.label)
            note.setWordWrap(True)
            note.setObjectName("mutedLabel")
            return note
        if kind == "bool":
            box = QCheckBox("")
            box.stateChanged.connect(lambda _state: self.changed.emit())
            return box
        if kind == "int":
            spin = QSpinBox()
            spin.setRange(int(item.minimum) if item.minimum is not None else -(1 << 30),
                          int(item.maximum) if item.maximum is not None else (1 << 30))
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            return spin
        if kind == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setSingleStep(1.0)
            spin.setRange(float(item.minimum) if item.minimum is not None else -1e9,
                          float(item.maximum) if item.maximum is not None else 1e9)
            spin.valueChanged.connect(lambda _value: self.changed.emit())
            return spin
        if kind == "choice" or (kind == "name_pick" and item.choices):
            combo = QComboBox()
            combo.setEditable(kind == "name_pick")
            for choice in item.choices:
                combo.addItem(str(choice), choice)
            combo.currentIndexChanged.connect(lambda _index: self.changed.emit())
            if combo.isEditable():
                combo.editTextChanged.connect(lambda _text: self.changed.emit())
            return combo
        if kind == "colour_argb":
            return _ColourField(self)
        if kind in ("png", "wav"):
            return _FileField(kind, self)
        line = QLineEdit()
        line.setPlaceholderText("leave blank to keep what is there")
        line.textChanged.connect(lambda _text: self.changed.emit())
        return line

    def values(self) -> Dict[str, Any]:
        """What the editor says, in the lane's ``values`` shape.

        A blank text, colour or file means *keep what is there*, so it is left
        out rather than sent as an empty string a lane would have to special-case.
        """

        out: Dict[str, Any] = {}
        for key, (item, widget) in self._widgets.items():
            if item.read_only or item.kind == "note":
                continue
            if isinstance(widget, QCheckBox):
                out[key] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                out[key] = int(widget.value())
            elif isinstance(widget, QDoubleSpinBox):
                out[key] = float(widget.value())
            elif isinstance(widget, QComboBox):
                if widget.isEditable():
                    text = widget.currentText().strip()
                    if text:
                        out[key] = text
                else:
                    out[key] = widget.currentData() if widget.currentData() is not None else widget.currentText()
            elif isinstance(widget, (_ColourField, _FileField)):
                text = widget.text().strip()
                if text:
                    out[key] = text
            elif isinstance(widget, QLineEdit):
                text = widget.text().strip()
                if text:
                    out[key] = text
        return out

    def set_value(self, key: str, value: str) -> None:
        row = self._widgets.get(key)
        if row is None:
            return
        widget = row[1]
        if isinstance(widget, (_ColourField, _FileField)):
            widget.set_text(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(value)

    def first_key_of_kind(self, kind: str) -> Optional[str]:
        for key, (item, _widget) in self._widgets.items():
            if item.kind == kind:
                return key
        return None

    def reset(self) -> None:
        self.set_fields(self._fields)


class _ColourField(QWidget):
    """A packed ARGB word: a hex box, a picker and a swatch that follows it."""

    def __init__(self, editor: FieldEditor) -> None:
        super().__init__(editor)
        self._editor = editor
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("#RRGGBB or AARRGGBB, or leave blank")
        self.edit.setMaxLength(9)
        self.pick = QPushButton("Pick…")
        self.swatch = QLabel("    ")
        self.swatch.setMinimumWidth(36)
        row.addWidget(self.edit, 1)
        row.addWidget(self.pick)
        row.addWidget(self.swatch)
        self.edit.textChanged.connect(lambda _text: self._refresh())
        self.edit.textChanged.connect(lambda _text: editor.changed.emit())
        self.pick.clicked.connect(self._choose)

    def _choose(self) -> None:
        colour = QColorDialog.getColor(parent=self, title="Choose the colour",
                                       options=QColorDialog.ShowAlphaChannel)
        if colour.isValid():
            self.edit.setText("%02X%02X%02X%02X" % (colour.alpha(), colour.red(),
                                                    colour.green(), colour.blue()))

    def _refresh(self) -> None:
        text = self.edit.text().strip().lstrip("#")
        if len(text) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in text):
            self.swatch.setStyleSheet(f"background: #{text[-6:]}; border: 1px solid #22304a;")
        else:
            self.swatch.setStyleSheet("")

    def text(self) -> str:
        return self.edit.text()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)


class _FileField(QWidget):
    """A path to a file the lane will read: a PNG or a WAV, chosen or typed."""

    FILTERS = {"png": "PNG images (*.png);;All files (*)",
               "wav": "WAV audio (*.wav);;All files (*)"}

    def __init__(self, kind: str, editor: FieldEditor) -> None:
        super().__init__(editor)
        self.kind = kind
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(f"choose a {kind.upper()} file, or leave blank to keep")
        self.browse = QPushButton("Browse…")
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse)
        self.edit.textChanged.connect(lambda _text: editor.changed.emit())
        self.browse.clicked.connect(self._choose)

    def _choose(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self, f"Choose a {self.kind.upper()} file", str(Path.home()),
            self.FILTERS.get(self.kind, "All files (*)"))
        if selected:
            self.edit.setText(selected)

    def text(self) -> str:
        return self.edit.text()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

class UnavailablePanel(QWidget):
    """A page with no controls and one honest paragraph saying why."""

    def __init__(self, title: str, sentences: Sequence[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.sentence = QLabel("\n\n".join(text for text in sentences if text))
        self.sentence.setObjectName("gameStudioUnavailable")
        self.sentence.setWordWrap(True)
        self.sentence.setTextFormat(Qt.PlainText)
        self.sentence.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sentence.setAccessibleName(f"Why {title} is not available")
        layout.addWidget(self.sentence)
        layout.addStretch(1)


class LanePage(QWidget):
    """One lane, whole: catalogue, targets, the editor, the recipe, the check.

    Everything here is the lane's own answer shown next to the control it is
    about.  Nothing is re-worded: the budget on screen is ``Target.budget``,
    the inline refusal is ``check_edit``'s sentence, the plan line is the dry
    run's, and Add is disabled while any of them stands.
    """

    def __init__(self, window: "GameStudioDialog", lane: Any) -> None:
        super().__init__(window)
        self.window = window
        self.lane = lane
        self.service = window.service
        self._staged: List[Edit] = []
        self._targets: Tuple[Target, ...] = ()
        self._current: Optional[Target] = None
        self._scopes = lane_scopes(lane)
        self._scope = self._scopes[0].id
        self._plan: Any = None
        self._plan_error: Optional[str] = None
        self.read_only = is_read_only(lane)
        self.setAccessibleName(f"{lane.title} lane")
        self._build_ui()
        self.source_changed()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.honesty = QLabel(honesty_line(self.lane.classification))
        self.honesty.setObjectName("gameStudioBadge")
        self.honesty.setAccessibleName(f"What is proved about {self.lane.title}")
        root.addWidget(self.honesty)

        reason = registry_reasons().get(self.lane.capability_id, "")
        if reason:
            rules = QLabel(reason)
            rules.setObjectName("caveatCard")
            rules.setWordWrap(True)
            rules.setTextFormat(Qt.PlainText)
            rules.setAccessibleName(f"{self.lane.title} rules from the registry")
            root.addWidget(rules)

        catalogue_row = QHBoxLayout()
        self.catalogue_label = QLabel("")
        self.catalogue_label.setWordWrap(True)
        self.catalogue_label.setTextFormat(Qt.PlainText)
        self.catalogue_label.setAccessibleName(f"{self.lane.title} catalogue status")
        catalogue_row.addWidget(self.catalogue_label, 1)
        self.scope_combo = QComboBox()
        self.scope_combo.setAccessibleName(f"{self.lane.title} catalogue scope")
        for scope in self._scopes:
            self.scope_combo.addItem(scope.label, scope.id)
            self.scope_combo.setItemData(self.scope_combo.count() - 1, scope.note, Qt.ToolTipRole)
        if len(self._scopes) < 2:
            self.scope_combo.hide()
        catalogue_row.addWidget(self.scope_combo)
        self.catalogue_button = QPushButton("Build catalogue")
        self.catalogue_button.setAccessibleName(f"Build the {self.lane.title} catalogue from your source")
        self.catalogue_button.setAccessibleDescription(
            "Runs the lane's own catalogue step in a separate process, read-only, and caches "
            "the result on this machine."
        )
        catalogue_row.addWidget(self.catalogue_button)
        root.addLayout(catalogue_row)

        splitter = QSplitter(Qt.Horizontal)
        picker = QWidget()
        picker_layout = QVBoxLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {self.lane.title.lower()} targets…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName(f"Search {self.lane.title} targets")
        picker_layout.addWidget(self.search)
        self.model = TargetTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName(f"{self.lane.title} targets")
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setStretchLastSection(True)
        picker_layout.addWidget(self.table, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("mutedLabel")
        picker_layout.addWidget(self.count_label)
        splitter.addWidget(picker)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.target_label = QLabel("Choose a target in the list.")
        self.target_label.setWordWrap(True)
        self.target_label.setTextFormat(Qt.PlainText)
        self.target_label.setAccessibleName("Selected target")
        side_layout.addWidget(self.target_label)
        self.budget_label = QLabel("")
        self.budget_label.setWordWrap(True)
        self.budget_label.setObjectName("mutedLabel")
        self.budget_label.setAccessibleName("Budget for the selected target")
        side_layout.addWidget(self.budget_label)

        self.extras = self._build_extras()
        if self.extras is not None:
            side_layout.addWidget(self.extras)

        self.editor_box = QGroupBox("Edit")
        editor_layout = QVBoxLayout(self.editor_box)
        self.editor = FieldEditor(self.editor_box)
        editor_layout.addWidget(self.editor)
        side_layout.addWidget(self.editor_box)
        if self.read_only:
            self.editor_box.hide()

        self.refusal_label = QLabel("")
        self.refusal_label.setObjectName("refusalLabel")
        self.refusal_label.setWordWrap(True)
        self.refusal_label.setTextFormat(Qt.PlainText)
        self.refusal_label.setAccessibleName("Why this edit cannot be added yet")
        side_layout.addWidget(self.refusal_label)
        self.add_button = QPushButton("Add to build")
        self.add_button.setAccessibleName(f"Add this {self.lane.title.lower()} edit to the build")
        side_layout.addWidget(self.add_button)
        if self.read_only:
            self.add_button.hide()
        side_layout.addStretch(1)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.recipe_box = QGroupBox("Staged for the build")
        recipe_layout = QHBoxLayout(self.recipe_box)
        staged_column = QVBoxLayout()
        self.staged_list = QListWidget()
        self.staged_list.setAccessibleName(f"Staged {self.lane.title} edits")
        staged_column.addWidget(self.staged_list, 1)
        staged_buttons = QHBoxLayout()
        self.remove_button = QPushButton("Remove")
        self.clear_button = QPushButton("Clear")
        self.check_button = QPushButton("Check this lane")
        self.check_button.setAccessibleDescription(
            "Runs the lane's own dry run against your source. Refusals appear here; nothing is written."
        )
        staged_buttons.addWidget(self.remove_button)
        staged_buttons.addWidget(self.clear_button)
        staged_buttons.addStretch(1)
        staged_buttons.addWidget(self.check_button)
        staged_column.addLayout(staged_buttons)
        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        self.plan_label.setTextFormat(Qt.PlainText)
        self.plan_label.setAccessibleName(f"{self.lane.title} check result")
        staged_column.addWidget(self.plan_label)
        recipe_layout.addLayout(staged_column, 3)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(_monospace())
        self.preview.setAccessibleName(f"{self.lane.title} recipe preview")
        self.preview.setAccessibleDescription("The exact recipe the lane's patcher will be handed.")
        self.preview.setPlaceholderText("The recipe appears here as you add edits.")
        recipe_layout.addWidget(self.preview, 2)
        self.recipe_box.setMaximumHeight(230)
        root.addWidget(self.recipe_box)
        if self.read_only:
            self.recipe_box.hide()

        self.catalogue_button.clicked.connect(self._build_catalogue)
        self.scope_combo.currentIndexChanged.connect(lambda _index: self._scope_changed())
        self.search.textChanged.connect(self.model.set_filter)
        self.search.textChanged.connect(lambda _text: self._refresh_count())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())
        self.editor.changed.connect(self._validate)
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self.clear_button.clicked.connect(self._clear)
        self.check_button.clicked.connect(lambda: self.window.check_lane(self.lane.lane_id))

    def _build_extras(self) -> Optional[QWidget]:
        """The controls the lane's optional protocols earn, and nothing else."""

        rows: List[QWidget] = []
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_image: Optional[QLabel] = None
        self.identity_label: Optional[QLabel] = None
        self.pnach_view: Optional[QPlainTextEdit] = None

        if isinstance(self.lane, ArtLane):
            self.preview_image = QLabel("")
            self.preview_image.setMinimumHeight(96)
            self.preview_image.setAlignment(Qt.AlignCenter)
            self.preview_image.setAccessibleName(f"{self.lane.title} art preview")
            layout.addWidget(self.preview_image)
            self.identity_label = QLabel("")
            self.identity_label.setObjectName("mutedLabel")
            self.identity_label.setWordWrap(True)
            self.identity_label.setAccessibleName("PCSX2 replacement identity")
            layout.addWidget(self.identity_label)
            buttons = QHBoxLayout()
            self.export_png_button = QPushButton("Export PNG…")
            self.export_png_button.setAccessibleDescription(
                "Writes this target's art from your own source as a PNG file you choose.")
            self.import_png_button = QPushButton("Import PNG…")
            self.import_png_button.setAccessibleDescription(
                "Offers a PNG to the lane. A size it cannot take is refused with the size it wanted.")
            self.pack_button = QPushButton("Write PCSX2 pack")
            self.pack_button.setAccessibleDescription(
                "The pack is written by the Build & Share page, from what you have staged here.")
            buttons.addWidget(self.export_png_button)
            buttons.addWidget(self.import_png_button)
            buttons.addWidget(self.pack_button)
            buttons.addStretch(1)
            layout.addLayout(buttons)
            self.export_png_button.clicked.connect(self._export_png)
            self.import_png_button.clicked.connect(self._import_png)
            self.pack_button.clicked.connect(lambda: self.window.select_page("build"))
            rows.append(holder)

        if isinstance(self.lane, AudioLane):
            buttons = QHBoxLayout()
            self.play_button = QPushButton("Play")
            self.play_button.setAccessibleDescription(
                "Plays this slot's sound decoded from your own source. Nothing is written.")
            self.export_wav_button = QPushButton("Export WAV…")
            self.export_wav_button.setAccessibleDescription(
                "Writes this slot's sound from your own source as a WAV file you choose.")
            buttons.addWidget(self.play_button)
            buttons.addWidget(self.export_wav_button)
            buttons.addStretch(1)
            layout.addLayout(buttons)
            self.play_button.clicked.connect(self._play_wav)
            self.export_wav_button.clicked.connect(self._export_wav)
            rows.append(holder)

        if isinstance(self.lane, CodePatchLane):
            self.pnach_view = QPlainTextEdit()
            self.pnach_view.setReadOnly(True)
            self.pnach_view.setFont(_monospace())
            self.pnach_view.setMaximumHeight(120)
            self.pnach_view.setAccessibleName("The pnach this lane would write")
            self.pnach_view.setPlaceholderText(
                "Choose a patch to see the .pnach lines it would write, or the reason it is not "
                "translated yet.")
            layout.addWidget(self.pnach_view)
            rows.append(holder)

        if self.read_only:
            note = QLabel(
                "This lane only reads. It names what is on your source with sizes and digests "
                "and never offers an edit."
            )
            note.setWordWrap(True)
            note.setObjectName("mutedLabel")
            note.setAccessibleName(f"{self.lane.title} is read-only")
            layout.addWidget(note)
            rows.append(holder)

        return holder if rows else None

    # -- state ---------------------------------------------------------

    def scope(self) -> str:
        return self._scope

    def staged(self) -> List[Edit]:
        return list(self._staged)

    def plan(self) -> Any:
        return self._plan

    def source_changed(self) -> None:
        self._staged.clear()
        self._plan = None
        self._plan_error = None
        self.plan_label.setText("")
        self.staged_list.clear()
        self.preview.setPlainText("")
        self.catalogue_changed()

    def catalogue_changed(self) -> None:
        self._current = None
        self._targets = ()
        built = False
        text = f"{self.lane.title}: open a source first."
        if self.service.is_open:
            state = self.service.catalogue_state(self.lane.lane_id, self._scope)
            built = state.built
            text = (f"{self.lane.title}: {state.headline}" if built else
                    f"{self.lane.title}: catalogue not built for this source yet — "
                    "choose Build catalogue.")
        self.catalogue_label.setText(text)
        if built:
            try:
                self._targets = self.service.targets(self.lane.lane_id, self._scope)
            except ContractError as exc:
                self.catalogue_label.setText(f"{self.lane.title}: {exc}")
        self.model.set_targets(self._targets)
        self._refresh_count()
        self.editor.set_fields(())
        self.target_label.setText("Choose a target in the list." if self._targets
                                  else "Build the catalogue to list this source's targets.")
        self.budget_label.setText("")
        self.refusal_label.setText("")
        self._refresh_recipe()
        self.window.refresh_controls()

    def plan_changed(self, plan: Any, error: Optional[str]) -> None:
        self._plan = plan
        self._plan_error = error
        if error:
            self.plan_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self.plan_label.setText(f"Refused: {error}")
        elif plan is not None:
            self.plan_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
            targets = len(getattr(plan, "target_keys", ()) or ())
            self.plan_label.setText(
                f"Checked against your source: {targets} target"
                f"{'' if targets == 1 else 's'} resolve, nothing was written.")
        else:
            self.plan_label.setStyleSheet("")
            self.plan_label.setText("")

    def refresh_controls(self, state: Any) -> None:
        busy = bool(getattr(state, "can_cancel", False))
        self.catalogue_button.setEnabled(bool(getattr(state, "can_build_catalogue", False)))
        self.scope_combo.setEnabled(not busy)
        live = bool(getattr(state, "can_edit", False)) and bool(self._targets)
        self.search.setEnabled(live)
        self.table.setEnabled(live)
        self.editor_box.setEnabled(live and self._current is not None and not self.read_only)
        self.check_button.setEnabled(bool(self._staged) and bool(getattr(state, "can_check", False)))
        self.remove_button.setEnabled(bool(self._staged) and not busy)
        self.clear_button.setEnabled(bool(self._staged) and not busy)
        if not live or self.read_only:
            self.add_button.setEnabled(False)

    # -- catalogue -----------------------------------------------------

    def _build_catalogue(self) -> None:
        self.window.build_catalogue(self.lane.lane_id, self._scope)

    def _scope_changed(self) -> None:
        self._scope = str(self.scope_combo.currentData() or self._scopes[0].id)
        self._staged.clear()
        self.staged_list.clear()
        self.plan_changed(None, None)
        self.catalogue_changed()
        self.window.recipe_changed(self.lane.lane_id)

    def _refresh_count(self) -> None:
        shown = self.model.rowCount()
        total = len(self._targets)
        self.count_label.setText(f"{shown:,} of {total:,} targets shown" if total else "")

    # -- editing -------------------------------------------------------

    def _selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        target = self.model.target_at(rows[0].row()) if rows else None
        self._current = target
        if target is None:
            self.target_label.setText("Choose a target in the list.")
            self.budget_label.setText("")
            self.editor.set_fields(())
        else:
            self.target_label.setText(f"{target.label}\n{target.detail}".strip())
            self.budget_label.setText(target.budget)
            self.editor.set_fields(target.fields)
        self.editor_box.setEnabled(target is not None and not self.read_only)
        self._refresh_extras(target)
        self._validate()

    def _refresh_extras(self, target: Optional[Target]) -> None:
        if self.identity_label is not None:
            identity = ""
            if target is not None:
                try:
                    identity = self.lane.replacement_identity(target) or ""
                except Exception as exc:  # a lane that cannot say is not a crash
                    identity = str(exc)
            self.identity_label.setText(
                f"PCSX2 replacement file: {identity}" if identity
                else "This target has no PCSX2 replacement name.")
        if self.preview_image is not None:
            self.preview_image.clear()
            data = self._decoded_png(target, quiet=True)
            if data:
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    self.preview_image.setPixmap(pixmap.scaledToHeight(96, Qt.SmoothTransformation))
        if self.pnach_view is not None:
            self.pnach_view.setPlainText(self._pnach_text(target))

    def _decoded_png(self, target: Optional[Target], *, quiet: bool = False) -> bytes:
        if target is None or not self.service.is_open:
            return b""
        try:
            return bytes(self.lane.decode_png(self.service.source_path, target) or b"")
        except Exception as exc:
            if not quiet:
                self.window.report(f"{self.lane.title}: {exc}")
            return b""

    def _pnach_text(self, target: Optional[Target]) -> str:
        if target is None:
            return ""
        try:
            patch = self.lane.translation(target.key, self.editor.values())
        except ContractError as exc:
            return str(exc)
        except Exception as exc:
            return f"{self.lane.title} could not translate {target.key}: {exc}"
        try:
            crc = str((self.service.identity().details or {}).get("elf_crc32", "")) if self.service.is_open else ""
            return self.lane.emit_pnach((patch,), crc)
        except Exception as exc:
            return f"{self.lane.title} could not write the pnach lines: {exc}"

    def _export_png(self) -> None:
        data = self._decoded_png(self._current)
        if not data:
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Save this target's art", str(Path.home() / f"{self._current.key}.png"),
            "PNG images (*.png)")
        if selected:
            Path(selected).write_bytes(data)
            self.window.report(f"Wrote {Path(selected).name}. Your source was not changed.")

    def _import_png(self) -> None:
        if self._current is None or not self.service.is_open:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Choose a PNG for this target", str(Path.home()), "PNG images (*.png)")
        if not selected:
            return
        try:
            encoded = self.lane.encode(self.service.source_path, self._current,
                                       Path(selected).read_bytes())
        except ContractError as exc:
            self.refusal_label.setText(str(exc))
            return
        except (OSError, ValueError) as exc:
            self.refusal_label.setText(f"{Path(selected).name} could not be read: {exc}")
            return
        key = self.editor.first_key_of_kind("png")
        if key is not None:
            self.editor.set_value(key, selected)
        note = getattr(encoded, "note", "")
        self.window.report(
            f"{Path(selected).name} accepted at {getattr(encoded, 'width', 0)}×"
            f"{getattr(encoded, 'height', 0)}." + (f" {note}" if note else ""))
        self._validate()

    def _decoded_wav(self) -> bytes:
        if self._current is None or not self.service.is_open:
            return b""
        try:
            return bytes(self.lane.decode_wav(self.service.source_path, self._current) or b"")
        except Exception as exc:
            self.window.report(f"{self.lane.title}: {exc}")
            return b""

    def _export_wav(self) -> None:
        data = self._decoded_wav()
        if not data:
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Save this slot's sound", str(Path.home() / f"{self._current.key}.wav"),
            "WAV audio (*.wav)")
        if selected:
            Path(selected).write_bytes(data)
            self.window.report(f"Wrote {Path(selected).name}. Your source was not changed.")

    def _play_wav(self) -> None:
        data = self._decoded_wav()
        if not data:
            return
        try:
            from PyQt5.QtMultimedia import QSound
        except ImportError:
            self.window.report(
                "This build has no audio playback (PyQt5's multimedia module is not "
                "installed); Export WAV writes the same sound to a file.")
            return
        handle = tempfile.NamedTemporaryFile(prefix="game-studio-", suffix=".wav", delete=False)
        handle.write(data)
        handle.close()
        self._sound = QSound(handle.name, self)
        self._sound.play()

    def _validate(self) -> None:
        if self.read_only:
            self.add_button.setEnabled(False)
            return
        target = self._current
        if target is None:
            self.refusal_label.setText("")
            self.add_button.setEnabled(False)
            return
        refusal = self.service.check_edit(self.lane.lane_id, target, self.editor.values())
        self.refusal_label.setText(refusal or "")
        self.add_button.setEnabled(refusal is None and not self.window.busy)
        if self.pnach_view is not None:
            self.pnach_view.setPlainText(self._pnach_text(target))

    def _add(self) -> None:
        if self._current is None:
            return
        try:
            edit = self.service.stage(self.lane.lane_id, self._current, self.editor.values())
        except ContractError as exc:
            self.refusal_label.setText(str(exc))
            self.add_button.setEnabled(False)
            return
        self._staged.append(edit)
        self.editor.reset()
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.lane_id)
        self._validate()

    def _remove(self) -> None:
        row = self.staged_list.currentRow()
        if not 0 <= row < len(self._staged):
            return
        del self._staged[row]
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.lane_id)
        self._validate()

    def _clear(self) -> None:
        if not self._staged:
            return
        self._staged.clear()
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.lane_id)
        self._validate()

    def _refresh_recipe(self) -> None:
        self.staged_list.clear()
        for edit in self._staged:
            values = ", ".join(f"{key}={value}" for key, value in sorted(edit.values.items()))
            item = QListWidgetItem(f"{edit.target_key}: {values}" if values else edit.target_key)
            item.setToolTip(item.text())
            self.staged_list.addItem(item)
        if not self._staged:
            self.preview.setPlainText("")
            return
        try:
            recipe = self.service.compose(self.lane.lane_id, self._staged)
        except ContractError as exc:
            self.preview.setPlainText(f"The recipe cannot be composed yet: {exc}")
            return
        self.preview.setPlainText(self.service.recipe_preview(recipe))


class BuildPage(QWidget):
    """The queue, the destination, the free-space check, the build, the receipt."""

    def __init__(self, window: "GameStudioDialog") -> None:
        super().__init__(window)
        self.window = window
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Every lane with staged edits runs as one step, in the module's own lane order, each "
            "step writing a new file from the previous one and verifying it before the previous "
            "intermediate is deleted. A lane that publishes files instead — an export — is run "
            "once from what you opened, into its own folder beside the destination."
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedLabel")
        root.addWidget(intro)

        self.queue = QTableWidget(0, 4)
        self.queue.setHorizontalHeaderLabels(("Lane", "Edits", "Checked", "What would change"))
        self.queue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue.setSelectionMode(QAbstractItemView.NoSelection)
        self.queue.setAlternatingRowColors(True)
        self.queue.verticalHeader().setVisible(False)
        self.queue.setAccessibleName("Build queue")
        self.queue.setAccessibleDescription(
            "One row per lane with staged edits: how many edits, whether its recipe has been "
            "checked against your source, and what the check said."
        )
        head = self.queue.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self.queue, 1)

        self.queue_label = QLabel("")
        self.queue_label.setWordWrap(True)
        self.queue_label.setTextFormat(Qt.PlainText)
        self.queue_label.setAccessibleName("Queue summary")
        root.addWidget(self.queue_label)

        destination_row = QHBoxLayout()
        caption = QLabel("New file:")
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("Choose a file name that does not exist yet…")
        self.destination.setAccessibleName("Destination for the new file")
        self.destination.setAccessibleDescription(
            "The new file is created here. It must not exist yet; what you opened is never written."
        )
        caption.setBuddy(self.destination)
        self.choose_button = QPushButton("Choose…")
        destination_row.addWidget(caption)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.choose_button)
        root.addLayout(destination_row)

        self.estimate_label = QLabel("")
        self.estimate_label.setWordWrap(True)
        self.estimate_label.setTextFormat(Qt.PlainText)
        self.estimate_label.setObjectName("discInfoCard")
        self.estimate_label.setAccessibleName("Free space check")
        root.addWidget(self.estimate_label)

        buttons = QHBoxLayout()
        self.check_button = QPushButton("Check everything")
        self.check_button.setAccessibleDescription(
            "Runs each lane's own dry run. Every refusal shows here before any file exists.")
        self.build_button = QPushButton("Build")
        self.build_button.setAccessibleDescription(
            "Writes a new file through each lane's patcher and verifies every step. What you "
            "opened is not changed.")
        self.open_folder_button = QPushButton("Open folder")
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.build_button)
        buttons.addWidget(self.open_folder_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.receipt_label = QLabel("")
        self.receipt_label.setObjectName("exportReceiptCard")
        self.receipt_label.setWordWrap(True)
        self.receipt_label.setTextFormat(Qt.PlainText)
        self.receipt_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.receipt_label.setAccessibleName("Build receipt")
        self.receipt_label.hide()
        root.addWidget(self.receipt_label)

        self.choose_button.clicked.connect(self.window.choose_destination)
        self.check_button.clicked.connect(self.window.check_everything)
        self.build_button.clicked.connect(self.window.build)
        self.open_folder_button.clicked.connect(self.window.open_destination_folder)
        self.destination.textChanged.connect(lambda _text: self.window.refresh_estimate())

    def refresh(self, pages: Mapping[str, LanePage], errors: Mapping[str, str]) -> None:
        rows = [(lane_id, page) for lane_id, page in pages.items() if page.staged()]
        self.queue.setRowCount(len(rows))
        for row, (lane_id, page) in enumerate(rows):
            if lane_id in errors:
                checked, what, colour = "refused", errors[lane_id], _INVALID_COLOUR
            elif page.plan() is not None:
                keys = len(getattr(page.plan(), "target_keys", ()) or ())
                checked, what, colour = "yes", f"{keys} target(s) resolve", _MATCH_COLOUR
            else:
                checked, what, colour = "not yet", "choose Check everything", _WARN_COLOUR
            for column, text in enumerate((page.lane.title, str(len(page.staged())), checked, what)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 2:
                    item.setForeground(QColor(colour))
                self.queue.setItem(row, column, item)
        self.queue_label.setText(queue_summary_text(pages, errors))


def queue_summary_text(pages: Mapping[str, LanePage], errors: Mapping[str, str]) -> str:
    """The line over the queue, in the user's terms and never a count of nothing."""

    staged = {lane_id: page for lane_id, page in pages.items() if page.staged()}
    if not staged:
        return "Nothing is staged yet. Add an edit on one of the pages."
    total = sum(len(page.staged()) for page in staged.values())
    unchecked = [lane_id for lane_id, page in staged.items()
                 if page.plan() is None or lane_id in errors]
    text = (f"{total} edit{'' if total == 1 else 's'} staged across {len(staged)} "
            f"lane{'' if len(staged) == 1 else 's'}")
    if unchecked:
        return text + (f"; {len(unchecked)} lane{'' if len(unchecked) == 1 else 's'} not checked "
                       "yet — choose Check everything before building.")
    return text + "; every lane checked clean, ready to build."


def receipt_text(receipt: Any) -> str:
    """The receipt card: per step what changed, what the verifier said, how long."""

    lines = [str(getattr(receipt, "message", ""))]
    for step in getattr(receipt, "steps", ()) or ():
        detail = (f"{step.declared_bytes:,} declared bytes in {step.declared_ranges} range(s)"
                  if step.declared_ranges else f"{len(step.artifacts)} file(s) published")
        lines.append(f"Step {step.index} · {step.title}: {detail}\n"
                     f"   {step.verdict_summary}\n"
                     f"   {step.seconds:.0f} s")
    for export in getattr(receipt, "exports", ()) or ():
        lines.append(f"Export: {export}")
    path = getattr(receipt, "receipt_path", None)
    if path:
        lines.append(f"Receipt: {path}")
    digest = getattr(receipt, "destination_sha256", "")
    if digest:
        lines.append(f"New file SHA-256: {digest}")
    return "\n".join(line for line in lines if line)


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

class GameStudioDialog(QDialog):
    """One game's studio: the composed label, the module's identity, 14 pages."""

    def __init__(
        self,
        module: GameModule,
        *,
        parent: Optional[QWidget] = None,
        initial_source: Optional[Path] = None,
        service: Optional[GameStudioService] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.module = module
        #: Whatever opened this studio handed it -- the Xbox studio passes its
        #: live session as ``facade`` so a side window that needs one can be
        #: offered here instead of only from the old File menu.
        self.context: Dict[str, Any] = dict(context or {})
        self.studio_label = module.manifest.studio_label
        self.service = service if service is not None else GameStudioService(module)
        self.initial_source = Path(initial_source) if initial_source else None
        self._pages: Dict[str, QWidget] = {}
        self.lane_pages: Dict[str, LanePage] = {}
        self._plan_errors: Dict[str, str] = {}
        self._receipt: Any = None
        self.busy = False
        self._busy_verb = ""
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._task: Optional[_Task] = None
        self._task_outcome: object = None
        self._task_error: Optional[str] = None
        self._task_done: Optional[Callable[[object], None]] = None
        self._task_title = ""
        self._task_note = ""
        self._cancel: Optional[CancelToken] = None
        #: Set the moment the window really closes.  Nothing may start work
        #: after that: a deferred open or a queued task result arriving at a
        #: closed window is a use-after-free, not a late refresh.
        self._closed = False
        self.setObjectName("gameStudioDialog")
        self.setWindowTitle(self.studio_label)
        self.setMinimumSize(940, 620)
        self._build_ui()
        self._apply_style()
        # The build page says what is staged, and "nothing yet" is a state it
        # has to say out loud before anyone has touched a page.
        self.refresh_queue()
        self.refresh_controls()
        # Owned by this window, so it dies with it.  A bare
        # ``QTimer.singleShot(0, lambda: ...)`` has no receiver and fires even
        # after the window has gone, which segfaults the moment its task lands.
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._open_initial_source)
        if self.initial_source is not None:
            self._initial_timer.start(0)

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.menu_bar = QMenuBar(self)
        self.windows_menu = self.menu_bar.addMenu("&Windows")
        self.windows_menu.setToolTipsVisible(True)
        self._install_windows_menu()
        layout.setMenuBar(self.menu_bar)

        self.header = QLabel(self.studio_label)
        self.header.setObjectName("gameStudioHeader")
        self.header.setAccessibleName("Studio")
        layout.addWidget(self.header)

        self.identity = QLabel(
            f"{self.module.identity.title} — {self.module.identity.platform} · "
            f"module {self.module.version} · {len(self.module.lanes)} lane(s)"
        )
        self.identity.setObjectName("gameStudioIdentity")
        self.identity.setAccessibleName("Game module identity")
        self.identity.setWordWrap(True)
        layout.addWidget(self.identity)

        source_row = QHBoxLayout()
        self.source = QLabel(
            f"Source: {self.initial_source.name}" if self.initial_source else "No source opened yet."
        )
        self.source.setObjectName("gameStudioSource")
        self.source.setAccessibleName("Open source")
        self.source.setWordWrap(True)
        self.source.setTextFormat(Qt.PlainText)
        source_row.addWidget(self.source, 1)
        self.open_button = QPushButton("Open…")
        self.open_button.setAccessibleName(f"Open a source for {self.studio_label}")
        self.open_button.setAccessibleDescription(
            "Choose your own file. It is opened read-only and identified; catalogues are built from it."
        )
        source_row.addWidget(self.open_button)
        layout.addLayout(source_row)

        body = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.setObjectName("gameStudioPages")
        self.navigation.setAccessibleName("Studio pages")
        self.navigation.setAccessibleDescription(
            "Every page this studio has. A page whose lane does not exist yet is still here and says why."
        )
        self.navigation.setSelectionMode(QAbstractItemView.SingleSelection)
        self.navigation.setMaximumWidth(240)
        body.addWidget(self.navigation)

        self.stack = QStackedWidget()
        self.stack.setObjectName("gameStudioStack")
        body.addWidget(self.stack, 1)
        layout.addLayout(body, 1)

        self.build_page: Optional[BuildPage] = None
        for page_id, title in PAGE_ORDER:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, page_id)
            self.navigation.addItem(item)
            widget = self._build_page(page_id, title)
            self._pages[page_id] = widget
            self.stack.addWidget(widget)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        note = QLabel(BOUNDARY_NOTE)
        note.setObjectName("gameStudioBoundaryNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        footer = QHBoxLayout()
        self.status_label = QLabel("Open a source to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Current operation status")
        footer.addWidget(self.status_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # the service reports stages, not a fraction
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setAccessibleName("Operation in progress")
        self.progress_bar.hide()
        footer.addWidget(self.progress_bar, 0)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAccessibleDescription(
            "Stops the running step. A part-written new file is deleted; what you opened is never touched.")
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button, 0)
        layout.addLayout(footer)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.open_button.clicked.connect(self._choose_source)
        self.cancel_button.clicked.connect(self._cancel_running)

    def _install_windows_menu(self) -> None:
        """Every window this module offers except the studio the user is in.

        The three PS2 side windows used to sit on the Xbox studio's File menu,
        which meant a user had to leave the game they were working on to reach
        them.  They live here instead, under the game whose windows they are.
        """

        others = [window for window in self.module.windows
                  if window.window_id != self.module.studio_window]
        if not others:
            action = self.windows_menu.addAction("No other windows in this studio")
            action.setEnabled(False)
            return
        for spec in others:
            action = self.windows_menu.addAction(spec.menu_label)
            action.setToolTip(spec.tooltip)
            if spec.needs_studio_session and self.context.get("facade") is None:
                # Offered, named and explained -- but not clickable, because the
                # window works on a session this studio was not handed.
                action.setEnabled(False)
                action.setToolTip(
                    f"{spec.tooltip}\n\n{spec.menu_label} works on the open Xbox project, so it "
                    "needs that studio's session; open it from there."
                )
                continue
            action.triggered.connect(lambda _checked=False, window_id=spec.window_id:
                                     self.open_module_window(window_id))

    def _build_page(self, page_id: str, title: str) -> QWidget:
        """One page: its lanes, the build page, or the honest sentence."""

        if page_id == "build":
            self.build_page = BuildPage(self)
            self.build_page.setObjectName(f"gameStudioPage_{page_id}")
            self.build_page.setAccessibleName(title)
            return self.build_page

        lanes = self.lanes_for_page(page_id)
        offered = [lane for lane in lanes if is_offered(lane)]
        if not offered:
            widget = UnavailablePanel(title, self.unavailable_sentences(page_id), self)
            widget.setObjectName(f"gameStudioPage_{page_id}")
            widget.setAccessibleName(title)
            return widget

        if len(offered) == 1:
            page = LanePage(self, offered[0])
            self.lane_pages[offered[0].lane_id] = page
            page.setObjectName(f"gameStudioPage_{page_id}")
            page.setAccessibleName(title)
            return page

        holder = QWidget(self)
        holder.setObjectName(f"gameStudioPage_{page_id}")
        holder.setAccessibleName(title)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.setAccessibleName(f"{title} lanes")
        for lane in offered:
            page = LanePage(self, lane)
            self.lane_pages[lane.lane_id] = page
            tabs.addTab(page, lane.title)
        holder_layout.addWidget(tabs)
        return holder

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#gameStudioDialog QLabel#gameStudioHeader { font-size: 17px; font-weight: 600; }
            QDialog#gameStudioDialog QLabel#mutedLabel { color: #91a0b5; }
            QDialog#gameStudioDialog QLabel#gameStudioBoundaryNote {
                background: #10261b; border: 1px solid #1f5a3a; border-radius: 6px;
                padding: 9px; color: #39d98a;
            }
            QDialog#gameStudioDialog QLabel#gameStudioBadge { font-weight: 600; }
            QDialog#gameStudioDialog QLabel#discInfoCard,
            QDialog#gameStudioDialog QLabel#exportReceiptCard,
            QDialog#gameStudioDialog QLabel#gameStudioUnavailable,
            QDialog#gameStudioDialog QLabel#caveatCard {
                background: #101827; border: 1px solid #22304a; border-radius: 6px; padding: 9px;
            }
            QDialog#gameStudioDialog QLabel#refusalLabel { color: %s; }
            """
            % (_INVALID_COLOUR,)
        )

    # -- pages ---------------------------------------------------------

    def page_ids(self) -> Tuple[str, ...]:
        """Every page this studio has, in the studio's order."""

        return tuple(page_id for page_id, _title in PAGE_ORDER)

    def page_widget(self, page_id: str) -> Optional[QWidget]:
        """The widget of one page, or None when the id is not a page."""

        return self._pages.get(page_id)

    def lanes_for_page(self, page_id: str) -> Tuple[Any, ...]:
        """The module's lanes that this page hosts, in the module's own order."""

        return tuple(lane for lane in self.module.lanes if lane_page(lane) == page_id)

    def unavailable_sentences(self, page_id: str) -> Tuple[str, ...]:
        """Every sentence an unavailable page shows, in the order it shows them.

        The core's first, then the game's own from ``page_notes``, then -- for
        a lane that exists but whose evidence does not let the studio offer it
        -- that row's classification and the registry's own reason.
        """

        title = dict(PAGE_ORDER).get(page_id, page_id)
        lanes = self.lanes_for_page(page_id)
        withheld = [lane for lane in lanes if not is_offered(lane)]
        out: List[str] = []
        if not lanes:
            out.append(UNAVAILABLE_TEMPLATE.format(title=title, studio=self.studio_label))
        note = self.module.manifest.page_note(page_id)
        if note:
            out.append(note)
        for lane in withheld:
            out.append(WITHHELD_TEMPLATE.format(title=lane.title, classification=lane.classification))
            reason = registry_reasons().get(lane.capability_id, "")
            if reason:
                out.append(reason)
        return tuple(out)

    def unavailable_sentence(self, page_id: str) -> str:
        """The core's sentence for a page with no lane, plus the game's own.

        Kept as one string because that is what the shell's first tests asked
        for and what a caller wanting "why is this page empty" wants; the
        page itself draws :meth:`unavailable_sentences` with the paragraphs apart.
        """

        title = dict(PAGE_ORDER).get(page_id, page_id)
        sentence = UNAVAILABLE_TEMPLATE.format(title=title, studio=self.studio_label)
        note = self.module.manifest.page_note(page_id)
        return f"{sentence} {note}".strip() if note else sentence

    def select_page(self, page_id: str) -> bool:
        """Show one page by id; False when the id is not a page."""

        for index, (candidate, _title) in enumerate(PAGE_ORDER):
            if candidate == page_id:
                self.navigation.setCurrentRow(index)
                return True
        return False

    def current_page_id(self) -> Optional[str]:
        item = self.navigation.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    # -- other windows ---------------------------------------------------

    def open_module_window(self, window_id: str) -> Optional[QWidget]:
        """Open one of this module's other windows, refusals inline."""

        try:
            spec = self.module.window(window_id)
            dialog = spec.factory(parent=self, **self.context)
        except ContractError as exc:
            self.report(str(exc))
            return None
        except Exception as exc:
            self.report(f"{self.module.window(window_id).menu_label} could not open "
                        f"({exc.__class__.__name__}: {exc}). Nothing was changed.")
            return None
        if hasattr(dialog, "exec_"):
            dialog.exec_()
            dialog.deleteLater()
        return dialog

    # -- background operations -------------------------------------------

    def _start(
        self, verb: str, title: str,
        operation: Callable[[Callable[[str], None], Any], object],
        done: Callable[[object], None],
        failure_note: str = "What you opened was not changed.",
    ) -> None:
        """Hand one service operation to the pool and settle when it lands."""

        if self._closed:
            return
        self.busy = True
        self._busy_verb = verb
        self._task_title = title
        self._task_note = failure_note
        self._task_done = done
        self._task_outcome = None
        self._task_error = None
        self._cancel = CancelToken()
        self.status_label.setStyleSheet("")
        self.report(f"{verb}…")
        self.progress_bar.show()
        self.cancel_button.show()
        self.refresh_controls()
        task = _Task(operation, self._cancel)
        self._task = task
        task.signals.stage.connect(self.report)
        task.signals.result.connect(self._task_succeeded)
        task.signals.error.connect(self._task_failed)
        task.signals.finished.connect(self._task_finished)
        self._pool.start(task)

    def _task_succeeded(self, result: object) -> None:
        self._task_outcome = result

    def _task_failed(self, message: str) -> None:
        self._task_error = message or f"{self._busy_verb} failed."

    def _task_finished(self) -> None:
        """Clear the busy state first, then report -- never a modal over a spinner."""

        if self._closed:
            # The window went while the task was in flight; there is nothing
            # left to report to and nothing this can safely touch.
            return
        outcome, error, done, title, note = (
            self._task_outcome, self._task_error, self._task_done, self._task_title, self._task_note,
        )
        cancelled = bool(self._cancel is not None and self._cancel.cancelled)
        self._task = None
        self._task_outcome = None
        self._task_error = None
        self._task_done = None
        self._cancel = None
        self.busy = False
        self.progress_bar.hide()
        self.cancel_button.hide()
        if error is not None:
            self.refresh_controls()
            self.status_label.setStyleSheet(f"color: {_WARN_COLOUR if cancelled else _INVALID_COLOUR};")
            self.report(error)
            if not cancelled:
                QMessageBox.warning(self, title, f"{error}\n\n{note}")
            return
        if done is not None:
            done(outcome)
        self.refresh_controls()

    def _cancel_running(self) -> None:
        if self.busy and self._cancel is not None:
            self._cancel.cancel()
            self.report(f"Cancelling {self._busy_verb.lower()}…")

    # -- opening ---------------------------------------------------------

    def _choose_source(self) -> None:
        if self.busy:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, f"Open a source for {self.studio_label}", str(Path.home()),
            self.service.open_filter)
        if selected:
            self.open_source(Path(selected))

    def _open_initial_source(self) -> None:
        """Open the source the caller handed us, once the window is on screen."""

        if self.initial_source is not None:
            self.open_source(self.initial_source)

    def open_source(self, path: Path) -> None:
        """Identify the user's file in the background; refusals land inline."""

        if self.busy or self._closed:
            return
        self._plan_errors.clear()
        self._receipt = None
        if self.build_page is not None:
            self.build_page.receipt_label.hide()
        self.source.setText(f"Reading {Path(path).name}…")
        self._start(
            "Opening the source", "That source could not be opened",
            lambda stage, _cancel: self.service.open(Path(path), stage),
            self._opened,
        )

    def _opened(self, identity: object) -> None:
        for page in self.lane_pages.values():
            page.source_changed()
        headline = str(getattr(identity, "headline", ""))
        self.source.setText(headline or f"Source: {self.service.source_path}")
        if self.build_page is not None:
            source = self.service.source_path or Path.home()
            self.build_page.destination.setText(
                str(source.parent / suggested_destination(source.name)))
        self.refresh_queue()
        self.status_label.setStyleSheet("")
        self.report(headline)

    # -- catalogues, called by a lane page --------------------------------

    def build_catalogue(self, lane_id: str, scope: str) -> None:
        if self.busy or not self.service.is_open:
            return
        lane = self.module.lane(lane_id)
        self._start(
            f"Building the {lane.title} catalogue",
            f"The {lane.title} catalogue could not be built",
            lambda stage, cancel: self.service.build_catalogue(lane_id, scope, stage, cancel),
            lambda _state: self._catalogue_built(lane_id),
            failure_note="Nothing was kept from the interrupted build; your source was not changed.",
        )

    def _catalogue_built(self, lane_id: str) -> None:
        page = self.lane_pages.get(lane_id)
        if page is not None:
            page.catalogue_changed()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self.report(f"{self.module.lane(lane_id).title} catalogue built from your source.")

    # -- recipes ---------------------------------------------------------

    def recipe_changed(self, lane_id: str) -> None:
        """A page added or removed an edit: its plan no longer describes the recipe."""

        page = self.lane_pages.get(lane_id)
        if page is not None:
            page.plan_changed(None, None)
        self._plan_errors.pop(lane_id, None)
        self._receipt = None
        if self.build_page is not None:
            self.build_page.receipt_label.hide()
        self.refresh_queue()
        self.refresh_controls()

    def staged_by_lane(self) -> Dict[str, List[Edit]]:
        return {lane_id: page.staged() for lane_id, page in self.lane_pages.items()}

    def scopes(self) -> Dict[str, str]:
        return {lane_id: page.scope() for lane_id, page in self.lane_pages.items()}

    def check_lane(self, lane_id: str) -> None:
        """One lane's dry run, from its own Check button."""

        if self.busy or not self.service.is_open:
            return
        page = self.lane_pages[lane_id]
        edits, scope = page.staged(), page.scope()
        lane = self.module.lane(lane_id)
        self._start(
            f"Checking the {lane.title} recipe", f"The {lane.title} recipe was refused",
            lambda stage, cancel: self.service.plan_lane(lane_id, edits, scope, stage, cancel),
            lambda outcome: self._planned(lane_id, outcome),
            failure_note="Nothing was written. Fix the edit the sentence above names and check again.",
        )

    def _planned(self, lane_id: str, outcome: object) -> None:
        self._plan_errors.pop(lane_id, None)
        page = self.lane_pages.get(lane_id)
        if page is not None:
            page.plan_changed(outcome, None)
        self.refresh_queue()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self.report(f"{self.module.lane(lane_id).title}: checked clean; nothing was written.")

    def check_everything(self) -> None:
        """Dry-run every lane with staged edits, one after another, in one task."""

        if self.busy or not self.service.is_open:
            return
        work = [(lane_id, page.staged(), page.scope())
                for lane_id, page in self.lane_pages.items() if page.staged()]
        if not work:
            self.report("Nothing is staged yet.")
            return
        service = self.service

        def operation(stage: Callable[[str], None], cancel: Any) -> Dict[str, Any]:
            outcomes: Dict[str, Any] = {}
            errors: Dict[str, str] = {}
            for lane_id, edits, scope in work:
                if cancel is not None and cancel.cancelled:
                    raise Cancelled("Checking was cancelled.")
                try:
                    outcomes[lane_id] = service.plan_lane(lane_id, edits, scope, stage, cancel)
                except ContractError as exc:
                    errors[lane_id] = str(exc).strip() or "refused"
            return {"outcomes": outcomes, "errors": errors}

        self._start("Checking every staged recipe", "The recipes could not be checked",
                    operation, self._checked_everything, failure_note="Nothing was written.")

    def _checked_everything(self, result: object) -> None:
        outcomes = dict(result.get("outcomes") or {}) if isinstance(result, dict) else {}
        errors = dict(result.get("errors") or {}) if isinstance(result, dict) else {}
        for lane_id, outcome in outcomes.items():
            self._plan_errors.pop(lane_id, None)
            page = self.lane_pages.get(lane_id)
            if page is not None:
                page.plan_changed(outcome, None)
        for lane_id, message in errors.items():
            self._plan_errors[lane_id] = message
            page = self.lane_pages.get(lane_id)
            if page is not None:
                page.plan_changed(None, message)
        self.refresh_queue()
        if errors:
            names = ", ".join(self.module.lane(lane_id).title for lane_id in errors)
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self.report(f"Refused: {names}. See the build queue and the lane's page for the sentence.")
        else:
            self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
            self.report("Every staged recipe checked clean against your source. Nothing was written.")

    def plans_ready(self) -> bool:
        staged = {lane_id for lane_id, page in self.lane_pages.items() if page.staged()}
        return bool(staged) and all(
            self.lane_pages[lane_id].plan() is not None and lane_id not in self._plan_errors
            for lane_id in staged
        )

    def refresh_queue(self) -> None:
        if self.build_page is not None:
            self.build_page.refresh(self.lane_pages, self._plan_errors)
        self.refresh_estimate()

    def refresh_estimate(self) -> None:
        if self.build_page is None:
            return
        if not self.service.is_open:
            self.build_page.estimate_label.setText("")
            return
        text = self.build_page.destination.text().strip()
        if not text:
            self.build_page.estimate_label.setText("Choose a destination to see the free-space check.")
            return
        steps = sum(1 for page in self.lane_pages.values() if page.staged()) or 1
        try:
            estimate = self.service.estimate(steps, Path(text))
        except ContractError as exc:
            self.build_page.estimate_label.setText(str(exc))
            return
        self.build_page.estimate_label.setText(estimate.sentence)

    # -- building --------------------------------------------------------

    def choose_destination(self) -> None:
        if self.busy or self.build_page is None:
            return
        current = self.build_page.destination.text().strip()
        source = self.service.source_path
        start = current or str(Path.home() / suggested_destination(source.name if source else "modded"))
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Name the new file", start, "All files (*)",
            options=QFileDialog.DontConfirmOverwrite)
        if selected:
            self.build_page.destination.setText(selected)

    def build(self) -> None:
        if self.busy or self.build_page is None or not self.service.is_open or not self.plans_ready():
            return
        text = self.build_page.destination.text().strip()
        if not text:
            self.report("Choose a destination for the new file first.")
            return
        staged = {lane_id: edits for lane_id, edits in self.staged_by_lane().items() if edits}
        scopes = self.scopes()
        self._receipt = None
        self.build_page.receipt_label.hide()
        self._start(
            "Building", "The new file could not be built",
            lambda stage, cancel: self.service.build(staged, Path(text), stage, cancel, scopes),
            self._built,
            failure_note=("Whatever the build had created has been removed. What you opened was "
                          "not changed."),
        )

    def _built(self, receipt: object) -> None:
        self._receipt = receipt
        if self.build_page is not None:
            self.build_page.receipt_label.setText(receipt_text(receipt))
            self.build_page.receipt_label.show()
        self.select_page("build")
        passed = bool(getattr(receipt, "all_verified", False))
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR if passed else _WARN_COLOUR};")
        self.report(str(getattr(receipt, "message", "Built.")))

    def open_destination_folder(self) -> None:
        if self._receipt is None:
            return
        folder = Path(getattr(self._receipt, "destination", Path.home())).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # -- shared ----------------------------------------------------------

    def action_state(self) -> Any:
        built_any = False
        if self.service.is_open:
            for lane_id, page in self.lane_pages.items():
                if self.service.catalogue_state(lane_id, page.scope()).built:
                    built_any = True
                    break
        return studio_action_state(
            source_open=self.service.is_open,
            busy=self.busy,
            catalogue_built=built_any,
            staged_count=sum(len(page.staged()) for page in self.lane_pages.values()),
            plans_ready=self.plans_ready(),
            built=self._receipt is not None,
        )

    def refresh_controls(self) -> None:
        state = self.action_state()
        self.open_button.setEnabled(state.can_open)
        if self.build_page is not None:
            self.build_page.check_button.setEnabled(state.can_check)
            self.build_page.build_button.setEnabled(state.can_build)
            self.build_page.open_folder_button.setEnabled(state.can_open_folder)
            self.build_page.destination.setEnabled(not self.busy)
            self.build_page.choose_button.setEnabled(not self.busy)
        for page in self.lane_pages.values():
            page.refresh_controls(state)

    def report(self, message: str) -> None:
        self.status_label.setText(str(message))
        self.status_label.setToolTip(str(message))

    def done(self, result: int) -> None:
        """Refuse to close while an operation is in flight."""

        if self.busy:
            self.report(f"{self._busy_verb} is still running. Cancel it first, or wait for it "
                        "to finish.")
            return
        self._closed = True
        self._initial_timer.stop()
        try:
            self.service.close()
        except Exception:  # pragma: no cover - closing must never block the window
            pass
        super().done(result)


__all__ = [
    "BOUNDARY_NOTE",
    "BuildPage",
    "FieldEditor",
    "GameStudioDialog",
    "LanePage",
    "OFFERED_CLASSIFICATIONS",
    "TargetTableModel",
    "UNAVAILABLE_TEMPLATE",
    "UnavailablePanel",
    "WITHHELD_TEMPLATE",
    "classification_badge",
    "honesty_line",
    "is_offered",
    "queue_summary_text",
    "receipt_text",
    "registry_reasons",
]
