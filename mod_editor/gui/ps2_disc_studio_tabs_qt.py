"""The six lane tabs of the PS2 Disc Studio window.

Every tab has the same shape: the lane's one-line summary and its caveats in
plain words (with the registry row's rules one click away), the catalogue
status and its Build button, a picker over the catalogue (search plus a
table model over the in-memory rows -- 6,873 strings at most, so Qt only
asks for what is on screen), an editor for the selected target with the
budget on screen and the lane's inline refusal under it, Add to recipe, the
staged edits with Remove and Clear, the exact recipe JSON that will be
handed to the patcher, and Check this lane.

Nothing here decides a refusal.  The budget sentence, the inline refusal and
the plan refusal are the lane adapter's and the patcher's own; the tab only
shows them, next to the control they are about, and disables Add while one
stands.  The current text, colour words, roster names, book names and lane
geometry a tab shows are read from the user's own disc for display and go
nowhere else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontDatabase
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
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_disc_studio_lanes import (
    FACE_SHIELD_LABELS,
    MAX_CUSTOM_NAME_CHARS,
    Target,
    registry_rules,
    registry_scope,
)

_INVALID_COLOUR = "#ff7b84"
_MATCH_COLOUR = "#39d98a"
_WARN_COLOUR = "#e8c46a"
_MUTED_COLOUR = "#8391a8"


def _monospace() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(max(9, font.pointSize()))
    return font


# --------------------------------------------------------------------------
# Picker model
# --------------------------------------------------------------------------

class TargetTableModel(QAbstractTableModel):
    """The lane's catalogue rows, filtered by a search needle.

    ``columns`` is ``[(header, accessor)]``; the accessor takes a
    :class:`Target` and returns display text.  Rows the lane marks read-only
    are shown greyed with the reason as their tooltip, so the 215 read-only
    strings are visible without being offered.
    """

    def __init__(self, columns: Sequence) -> None:
        super().__init__()
        self._columns = list(columns)
        self._all: List[Target] = []
        self._rows: List[Target] = []
        self._needle = ""

    def set_targets(self, targets: Sequence[Target]) -> None:
        self.beginResetModel()
        self._all = list(targets)
        self._rows = self._filtered()
        self.endResetModel()

    def set_filter(self, needle: str) -> None:
        self._needle = needle.strip().lower()
        self.beginResetModel()
        self._rows = self._filtered()
        self.endResetModel()

    def _filtered(self) -> List[Target]:
        if not self._needle:
            return list(self._all)
        words = self._needle.split()
        return [row for row in self._all if all(word in row.search for word in words)]

    def target_at(self, row: int) -> Optional[Target]:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, key: str) -> int:
        for index, row in enumerate(self._rows):
            if row.key == key:
                return index
        return -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section: int, orientation: int, role: int = Qt.DisplayRole) -> object:  # noqa: N802
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self._columns[section][0]

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = self.target_at(index.row())
        if row is None:
            return None
        if role == Qt.ForegroundRole and not row.editable:
            return QColor(_MUTED_COLOUR)
        if role == Qt.ToolTipRole:
            return row.reason if not row.editable else f"{row.detail}\n{row.budget}"
        if role != Qt.DisplayRole:
            return None
        try:
            return str(self._columns[index.column()][1](row))
        except Exception:  # pragma: no cover - a malformed catalogue row must not crash the view
            return ""


# --------------------------------------------------------------------------
# Base tab
# --------------------------------------------------------------------------

class LaneTab(QWidget):
    """Common frame: caveats, catalogue, picker, editor, recipe, check."""

    #: Subclasses fill this: ``[(header, accessor)]`` for the picker.
    COLUMNS: Sequence = ()

    def __init__(self, window: Any, lane: Any) -> None:
        super().__init__(window)
        self.window = window
        self.host = window.host
        self.lane = lane
        self._staged: List[Any] = []
        self._targets: List[Target] = []
        self._current: Optional[Target] = None
        self._scope = lane.scopes()[0].id
        self._plan_outcome: Any = None
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(120)
        self._validate_timer.timeout.connect(self._validate)
        self.setAccessibleName(f"{lane.title} lane")
        self._build_ui()
        self.disc_changed()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        summary = QLabel(self.lane.summary)
        summary.setWordWrap(True)
        summary.setObjectName("mutedLabel")
        root.addWidget(summary)

        caveats = QLabel("\n".join(f"• {sentence}" for sentence in self.lane.caveats))
        caveats.setObjectName("caveatCard")
        caveats.setWordWrap(True)
        caveats.setTextFormat(Qt.PlainText)
        caveats.setAccessibleName(f"{self.lane.title} caveats")
        caveats.setAccessibleDescription("What is and is not proved about this lane, in plain words.")
        root.addWidget(caveats)

        rules_row = QHBoxLayout()
        self.rules_button = QPushButton("Show the rules from the registry")
        self.rules_button.setCheckable(True)
        self.rules_button.setAccessibleName(f"Show or hide the {self.lane.title} rules")
        rules_row.addWidget(self.rules_button)
        rules_row.addStretch(1)
        root.addLayout(rules_row)
        self.rules = QPlainTextEdit()
        self.rules.setReadOnly(True)
        self.rules.setAccessibleName(f"{self.lane.title} rules")
        self.rules.setMaximumHeight(150)
        rules = registry_rules(self.lane.id)
        scope = registry_scope(self.lane.id)
        self.rules.setPlainText("\n".join(f"• {rule}" for rule in rules) + (f"\n\n{scope}" if scope else ""))
        self.rules.hide()
        root.addWidget(self.rules)

        catalogue_row = QHBoxLayout()
        self.catalogue_label = QLabel("")
        self.catalogue_label.setWordWrap(True)
        self.catalogue_label.setTextFormat(Qt.PlainText)
        self.catalogue_label.setAccessibleName(f"{self.lane.title} catalogue status")
        catalogue_row.addWidget(self.catalogue_label, 1)
        self.scope_combo = QComboBox()
        self.scope_combo.setAccessibleName(f"{self.lane.title} catalogue scope")
        for item in self.lane.scopes():
            self.scope_combo.addItem(item.label, item.id)
            self.scope_combo.setItemData(self.scope_combo.count() - 1, item.note, Qt.ToolTipRole)
        if self.scope_combo.count() < 2:
            self.scope_combo.hide()
        catalogue_row.addWidget(self.scope_combo)
        self.catalogue_button = QPushButton("Build catalogue")
        self.catalogue_button.setAccessibleName(f"Build the {self.lane.title} catalogue from the disc")
        self.catalogue_button.setAccessibleDescription(
            "Runs the lane's catalogue tool over your disc image, read-only, and caches the result "
            "on this machine keyed by the disc."
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
        self.search.setProperty("studioSearch", True)
        picker_layout.addWidget(self.search)
        self.model = TargetTableModel(self.COLUMNS)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName(f"{self.lane.title} targets")
        self.table.setAccessibleDescription(
            f"Every {self.lane.title.lower()} target on this disc with its budget; greyed rows are read-only."
        )
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setStretchLastSection(True)
        picker_layout.addWidget(self.table, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("mutedLabel")
        picker_layout.addWidget(self.count_label)
        splitter.addWidget(picker)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.target_label = QLabel("Choose a target in the list.")
        self.target_label.setWordWrap(True)
        self.target_label.setTextFormat(Qt.PlainText)
        self.target_label.setAccessibleName("Selected target")
        editor_layout.addWidget(self.target_label)
        self.budget_label = QLabel("")
        self.budget_label.setWordWrap(True)
        self.budget_label.setObjectName("mutedLabel")
        self.budget_label.setAccessibleName("Budget for the selected target")
        editor_layout.addWidget(self.budget_label)
        self.editor_box = QGroupBox("Edit")
        self.editor_form = QFormLayout(self.editor_box)
        self._build_editor(self.editor_form)
        editor_layout.addWidget(self.editor_box)
        self.refusal_label = QLabel("")
        self.refusal_label.setObjectName("refusalLabel")
        self.refusal_label.setWordWrap(True)
        self.refusal_label.setTextFormat(Qt.PlainText)
        self.refusal_label.setAccessibleName("Why this edit cannot be added yet")
        editor_layout.addWidget(self.refusal_label)
        self.add_button = QPushButton("Add to recipe")
        self.add_button.setAccessibleName(f"Add this {self.lane.title.lower()} edit to the recipe")
        editor_layout.addWidget(self.add_button)
        editor_layout.addStretch(1)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        recipe_box = QGroupBox("Recipe")
        recipe_layout = QHBoxLayout(recipe_box)
        staged_column = QVBoxLayout()
        self.staged_list = QListWidget()
        self.staged_list.setAccessibleName(f"Staged {self.lane.title} edits")
        self.staged_list.setAccessibleDescription("The edits this lane will write, one per line.")
        staged_column.addWidget(self.staged_list, 1)
        staged_buttons = QHBoxLayout()
        self.remove_button = QPushButton("Remove")
        self.remove_button.setAccessibleName("Remove the selected staged edit")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setAccessibleName(f"Clear every staged {self.lane.title} edit")
        self.check_button = QPushButton("Check this lane")
        self.check_button.setAccessibleName(f"Check the {self.lane.title} recipe against the disc")
        self.check_button.setAccessibleDescription(
            "Runs the lane's own dry run. Refusals appear here; nothing is written."
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
        self.preview.setAccessibleDescription("The exact recipe the patcher will be handed.")
        self.preview.setPlaceholderText("The recipe appears here as you add edits.")
        recipe_layout.addWidget(self.preview, 2)
        recipe_box.setMaximumHeight(230)
        root.addWidget(recipe_box)

        time_note = QLabel(self.lane.time_note)
        time_note.setWordWrap(True)
        time_note.setObjectName("mutedLabel")
        root.addWidget(time_note)

        self.rules_button.toggled.connect(self.rules.setVisible)
        self.catalogue_button.clicked.connect(self._build_catalogue)
        self.scope_combo.currentIndexChanged.connect(lambda _index: self._scope_changed())
        self.search.textChanged.connect(self.model.set_filter)
        self.search.textChanged.connect(lambda _text: self._refresh_count())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self.clear_button.clicked.connect(self._clear)
        self.check_button.clicked.connect(lambda: self.window.check_lane(self.lane.id))

    def _build_editor(self, form: QFormLayout) -> None:
        raise NotImplementedError

    # -- hooks subclasses implement --------------------------------------

    def editor_values(self) -> dict:
        """What the editor currently says, in the lane's ``values`` shape."""
        raise NotImplementedError

    def editor_target_changed(self, target: Optional[Target]) -> None:
        """Prefill or reset the editor for a newly selected target."""

    def editor_reset(self) -> None:
        """Clear the editor after an edit was added."""

    def load_targets(self) -> List[Target]:
        return list(self.host.targets(self.lane.id, self._scope))

    def preview_text(self) -> str:
        if not self._staged:
            return ""
        try:
            return self.host.recipe_preview(self.host.compose(self.lane.id, self._staged, self._scope))
        except ValidationError as exc:
            return f"The recipe cannot be composed yet: {exc}"

    # -- state from the window -------------------------------------------

    def scope(self) -> str:
        return self._scope

    def staged(self) -> List[Any]:
        return list(self._staged)

    def disc_changed(self) -> None:
        self._staged.clear()
        self._plan_outcome = None
        self.plan_label.setText("")
        self.staged_list.clear()
        self.preview.setPlainText("")
        self.catalogue_changed()

    def catalogue_changed(self) -> None:
        self._current = None
        self._targets = []
        built = False
        text = f"{self.lane.title}: open a disc image first."
        if self.host.is_open:
            try:
                state = self.host.catalogue_state(self.lane.id, self._scope)
                built = bool(getattr(state, "built", False))
                text = (f"{self.lane.title}: {getattr(state, 'headline', '')}" if built
                        else f"{self.lane.title}: catalogue not built for this disc yet — choose Build catalogue.")
            except ValidationError as exc:
                text = f"{self.lane.title}: {exc}"
        self.catalogue_label.setText(text)
        if built:
            try:
                self._targets = self.load_targets()
            except ValidationError as exc:
                self.catalogue_label.setText(f"{self.lane.title}: {exc}")
        self.model.set_targets(self._targets)
        self._refresh_count()
        self.editor_target_changed(None)
        self.target_label.setText("Choose a target in the list." if self._targets else
                                  "Build the catalogue to list this disc's targets.")
        self.budget_label.setText("")
        self.refusal_label.setText("")
        self._refresh_recipe()
        self.window._refresh_controls()

    def plan_changed(self, outcome: Any, error: Optional[str]) -> None:
        self._plan_outcome = outcome
        if error:
            self.plan_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self.plan_label.setText(f"Refused: {error}")
        elif outcome is not None:
            self.plan_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
            self.plan_label.setText(f"Checked against your disc: {getattr(outcome, 'summary', '')}")
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
        self.editor_box.setEnabled(live and self._current is not None)
        self.check_button.setEnabled(bool(self._staged) and bool(getattr(state, "can_check", False)))
        self.remove_button.setEnabled(bool(self._staged) and not busy)
        self.clear_button.setEnabled(bool(self._staged) and not busy)
        if not live:
            self.add_button.setEnabled(False)

    # -- catalogue -----------------------------------------------------

    def _build_catalogue(self) -> None:
        self.window.build_catalogue(self.lane.id, self._scope)

    def _scope_changed(self) -> None:
        self._scope = str(self.scope_combo.currentData() or self.lane.scopes()[0].id)
        self._staged.clear()
        self.staged_list.clear()
        self.plan_changed(None, None)
        self.catalogue_changed()
        self.window.recipe_changed(self.lane.id)

    def _refresh_count(self) -> None:
        shown = self.model.rowCount()
        total = len(self._targets)
        editable = sum(1 for row in self._targets if row.editable)
        self.count_label.setText(f"{shown:,} of {total:,} targets shown · {editable:,} editable" if total else "")

    # -- editing -------------------------------------------------------

    def _selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        target = self.model.target_at(rows[0].row()) if rows else None
        self._current = target
        if target is None:
            self.target_label.setText("Choose a target in the list.")
            self.budget_label.setText("")
        else:
            self.target_label.setText(f"{target.label}\n{target.detail}")
            self.budget_label.setText(target.budget if target.editable else f"Read-only: {target.reason}")
        self.editor_target_changed(target)
        self.editor_box.setEnabled(target is not None)
        self._validate()

    def schedule_validate(self) -> None:
        self._validate_timer.start()

    def _validate(self) -> None:
        target = self._current
        if target is None:
            self.refusal_label.setText("")
            self.add_button.setEnabled(False)
            return
        try:
            values = self.editor_values()
        except ValidationError as exc:
            self.refusal_label.setText(str(exc))
            self.add_button.setEnabled(False)
            return
        refusal = self.host.check_edit(self.lane.id, target, values, self._staged)
        self.refusal_label.setText(refusal or "")
        self.add_button.setEnabled(refusal is None and not self.window._busy)

    def _add(self) -> None:
        target = self._current
        if target is None:
            return
        try:
            edit = self.host.stage(self.lane.id, target, self.editor_values(), self._staged)
        except ValidationError as exc:
            self.refusal_label.setText(str(exc))
            self.add_button.setEnabled(False)
            return
        self._staged.append(edit)
        self.editor_reset()
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.id)
        self._validate()

    def _remove(self) -> None:
        row = self.staged_list.currentRow()
        if not 0 <= row < len(self._staged):
            return
        del self._staged[row]
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.id)
        self._validate()

    def _clear(self) -> None:
        if not self._staged:
            return
        self._staged.clear()
        self.plan_changed(None, None)
        self._refresh_recipe()
        self.window.recipe_changed(self.lane.id)
        self._validate()

    def _refresh_recipe(self) -> None:
        self.staged_list.clear()
        for edit in self._staged:
            item = QListWidgetItem(str(getattr(edit, "summary", edit)))
            item.setToolTip(item.text())
            self.staged_list.addItem(item)
        self.preview.setPlainText(self.preview_text())


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------

class TextTab(LaneTab):
    COLUMNS = (
        ("String", lambda t: t.label),
        ("Bank", lambda t: t.data.get("bank_kind", "")),
        ("Current text", lambda t: t.data.get("_display_text", "")),
        ("Used / limit", lambda t: f"{t.data.get('used_code_units', 0)} / {max(0, int(t.data.get('allocation_bytes', 2)) // 2 - 1)}"),
        ("Used by", lambda t: str(t.data.get("reference_count", 1))),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        self.text_edit = QPlainTextEdit()
        self.text_edit.setAccessibleName("Replacement text")
        self.text_edit.setAccessibleDescription(
            "Type the new text. It may be shorter or the same length as the original, never longer; "
            "inline tokens such as |CROSS| must stay in place."
        )
        self.text_edit.setMaximumHeight(72)
        self.text_edit.textChanged.connect(self._text_changed)
        form.addRow("New text", self.text_edit)
        self.remaining_label = QLabel("")
        self.remaining_label.setAccessibleName("Characters left")
        form.addRow("", self.remaining_label)

    def load_targets(self) -> List[Target]:
        targets = list(self.host.targets(self.lane.id, self._scope))
        texts: Dict[str, str] = {}
        source = self.host.source_path
        if source is not None:
            try:
                texts = self.lane.read_display_texts(source, self.host.catalogue(self.lane.id, self._scope))
            except (ValidationError, OSError):
                texts = {}
        rows = []
        for target in targets:
            data = dict(target.data)
            data["_display_text"] = texts.get(target.key, "")
            rows.append(Target(target.key, target.label, target.detail, target.budget,
                               (target.search + " " + data["_display_text"].lower()).strip(),
                               target.editable, target.reason, target.group, data))
        return rows

    def editor_values(self) -> dict:
        return {"new_text": self.text_edit.toPlainText()}

    def editor_target_changed(self, target: Optional[Target]) -> None:
        self.text_edit.blockSignals(True)
        self.text_edit.setPlainText(target.data.get("_display_text", "") if target is not None else "")
        self.text_edit.blockSignals(False)
        self._text_changed()

    def editor_reset(self) -> None:
        self.editor_target_changed(self._current)

    def _text_changed(self) -> None:
        target = self._current
        if target is None:
            self.remaining_label.setText("")
        else:
            limit = max(0, int(target.data.get("allocation_bytes", 2)) // 2 - 1)
            used = len(self.text_edit.toPlainText().encode("utf-16le")) // 2
            left = limit - used
            self.remaining_label.setText(
                f"{used} of {limit} characters used · {left} left" if left >= 0
                else f"{used} of {limit} characters used · {-left} over the budget")
            self.remaining_label.setStyleSheet("" if left >= 0 else f"color: {_INVALID_COLOUR};")
        self.schedule_validate()


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------

def _argb_hex(word: Optional[int]) -> str:
    return "" if word is None else f"{word:08X}"


class ColoursTab(LaneTab):
    COLUMNS = (
        ("Selector", lambda t: t.key),
        ("Package", lambda t: t.label.split(" — ", 1)[-1]),
        ("Facemask now", lambda t: _argb_hex((t.data.get("_words") or (None, None))[0])),
        ("Turtleneck now", lambda t: _argb_hex((t.data.get("_words") or (None, None))[1])),
        ("Pack", lambda t: t.data.get("iso_path", "")),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        self.colour_edits: Dict[str, QLineEdit] = {}
        self.swatches: Dict[str, QLabel] = {}
        for name in ("facemask", "turtleneck"):
            row = QHBoxLayout()
            edit = QLineEdit()
            edit.setPlaceholderText("#RRGGBB or AARRGGBB, or leave blank")
            edit.setAccessibleName(f"New {name} colour")
            edit.setAccessibleDescription(
                f"A packed ARGB word of exactly 4 bytes for the {name}; leave blank to keep the current colour.")
            edit.setMaxLength(9)
            edit.textChanged.connect(lambda _t: self.schedule_validate())
            edit.textChanged.connect(lambda _t, n=name: self._refresh_swatch(n))
            pick = QPushButton("Pick…")
            pick.setAccessibleName(f"Pick the {name} colour")
            pick.clicked.connect(lambda _c=False, n=name: self._pick(n))
            swatch = QLabel("    ")
            swatch.setAccessibleName(f"{name} colour swatch")
            swatch.setMinimumWidth(36)
            row.addWidget(edit, 1)
            row.addWidget(pick)
            row.addWidget(swatch)
            holder = QWidget()
            holder.setLayout(row)
            form.addRow(name.capitalize(), holder)
            self.colour_edits[name] = edit
            self.swatches[name] = swatch
        self.current_label = QLabel("")
        self.current_label.setWordWrap(True)
        self.current_label.setAccessibleName("Current colours read from the disc")
        form.addRow("Now", self.current_label)

    def load_targets(self) -> List[Target]:
        targets = list(self.host.targets(self.lane.id, self._scope))
        words: Dict[str, Any] = {}
        source = self.host.source_path
        if source is not None:
            try:
                words = self.lane.read_current_words(source, self.host.catalogue(self.lane.id, self._scope))
            except (ValidationError, OSError):
                words = {}
        rows = []
        for target in targets:
            data = dict(target.data)
            data["_words"] = words.get(target.key)
            rows.append(Target(target.key, target.label, target.detail, target.budget, target.search,
                               target.editable, target.reason, target.group, data))
        return rows

    def editor_values(self) -> dict:
        values: Dict[str, Any] = {name: edit.text().strip() or None for name, edit in self.colour_edits.items()}
        if self._current is not None and self._current.data.get("_words"):
            values["_current"] = tuple(self._current.data["_words"])
        return values

    def editor_target_changed(self, target: Optional[Target]) -> None:
        for edit in self.colour_edits.values():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        words = target.data.get("_words") if target is not None else None
        if words:
            self.current_label.setText(f"facemask {_argb_hex(words[0])} · turtleneck {_argb_hex(words[1])}")
        else:
            self.current_label.setText("")
        for name in self.colour_edits:
            self._refresh_swatch(name)

    def editor_reset(self) -> None:
        self.editor_target_changed(self._current)

    def _pick(self, name: str) -> None:
        colour = QColorDialog.getColor(parent=self, title=f"Choose the {name} colour",
                                       options=QColorDialog.ShowAlphaChannel)
        if colour.isValid():
            self.colour_edits[name].setText("%02X%02X%02X%02X" % (colour.alpha(), colour.red(),
                                                                  colour.green(), colour.blue()))

    def _refresh_swatch(self, name: str) -> None:
        text = self.colour_edits[name].text().strip().lstrip("#")
        swatch = self.swatches[name]
        if len(text) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in text):
            rgb = text[-6:]
            swatch.setStyleSheet(f"background: #{rgb}; border: 1px solid #22304a;")
        else:
            words = self._current.data.get("_words") if self._current is not None else None
            if words:
                index = 0 if name == "facemask" else 1
                swatch.setStyleSheet(f"background: #{words[index] & 0xFFFFFF:06X}; border: 1px solid #22304a;")
            else:
                swatch.setStyleSheet("")


# --------------------------------------------------------------------------
# Roster
# --------------------------------------------------------------------------

class RosterTab(LaneTab):
    COLUMNS = (
        ("Player", lambda t: t.label),
        ("Pool", lambda t: t.data.get("pool", "").replace("_", " ")),
        ("Index", lambda t: str(t.data.get("index", ""))),
        ("First name budget", lambda t: str(max(0, (int(t.data.get("first_name_capacity", 0)) - 2) // 2))
         if t.data.get("first_name_writable") else "—"),
        ("Last name budget", lambda t: str(max(0, (int(t.data.get("last_name_capacity", 0)) - 2) // 2))
         if t.data.get("last_name_writable") else "—"),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        self.roster_combo = QComboBox()
        self.roster_combo.setAccessibleName("Roster to edit")
        self.roster_combo.setAccessibleDescription(
            "The boot roster the game starts from, or one of the historic rosters. Each roster is its own build step.")
        self.roster_combo.currentIndexChanged.connect(lambda _i: self._roster_changed())
        form.addRow("Roster", self.roster_combo)
        self.first_edit = QLineEdit()
        self.first_edit.setAccessibleName("New first name")
        self.first_edit.setPlaceholderText("leave blank to keep")
        self.last_edit = QLineEdit()
        self.last_edit.setAccessibleName("New last name")
        self.last_edit.setPlaceholderText("leave blank to keep")
        self.jersey_spin = QSpinBox()
        self.jersey_spin.setRange(-1, 99)
        self.jersey_spin.setSpecialValueText("keep")
        self.jersey_spin.setValue(-1)
        self.jersey_spin.setAccessibleName("New jersey number")
        self.jersey_spin.setAccessibleDescription("0 to 99, or keep.")
        self.shield_combo = QComboBox()
        self.shield_combo.setAccessibleName("Face shield")
        self.shield_combo.addItem("keep", None)
        for value, label in FACE_SHIELD_LABELS.items():
            self.shield_combo.addItem(label, value)
        for widget in (self.first_edit, self.last_edit):
            widget.textChanged.connect(lambda _t: self.schedule_validate())
        self.jersey_spin.valueChanged.connect(lambda _v: self.schedule_validate())
        self.shield_combo.currentIndexChanged.connect(lambda _i: self.schedule_validate())
        form.addRow("First name", self.first_edit)
        form.addRow("Last name", self.last_edit)
        form.addRow("Jersey", self.jersey_spin)
        form.addRow("Face shield", self.shield_combo)
        self._roster_key = "boot"

    def catalogue_changed(self) -> None:
        self.roster_combo.blockSignals(True)
        self.roster_combo.clear()
        if self.host.is_open:
            try:
                state = self.host.catalogue_state(self.lane.id, self._scope)
                if getattr(state, "built", False):
                    for roster in self.lane.rosters(self.host.catalogue(self.lane.id, self._scope)):
                        key = self.lane.roster_key(roster)
                        label = ("Boot roster (the one the game starts from)" if key == "boot"
                                 else f"Historic roster · outer entry {roster['outer_index']}")
                        if roster.get("compressed"):
                            label += " · compressed, not writable"
                        self.roster_combo.addItem(label, key)
            except ValidationError:
                pass
        self.roster_combo.blockSignals(False)
        self._roster_key = str(self.roster_combo.currentData() or "boot")
        super().catalogue_changed()

    def _roster_changed(self) -> None:
        self._roster_key = str(self.roster_combo.currentData() or "boot")
        self._current = None
        try:
            self._targets = self.load_targets()
            self.catalogue_label.setStyleSheet("")
        except ValidationError as exc:
            self._targets = []
            self.catalogue_label.setText(f"{self.lane.title}: {exc}")
        self.model.set_targets(self._targets)
        self._refresh_count()
        self.editor_target_changed(None)
        self._validate()

    def load_targets(self) -> List[Target]:
        source = self.host.source_path
        catalogue = self.host.catalogue(self.lane.id, self._scope)
        if self._roster_key == "boot" or source is None:
            players = list(catalogue.get("players", []))
        else:
            players = self.lane.decode_players(source, catalogue, self._roster_key)
        return self.lane.player_targets(self._roster_key, players)

    def editor_values(self) -> dict:
        return {
            "first_name": self.first_edit.text() or None,
            "last_name": self.last_edit.text() or None,
            "jersey_number": None if self.jersey_spin.value() < 0 else int(self.jersey_spin.value()),
            "face_shield": self.shield_combo.currentData(),
        }

    def editor_target_changed(self, target: Optional[Target]) -> None:
        for edit in (self.first_edit, self.last_edit):
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self.jersey_spin.blockSignals(True)
        self.jersey_spin.setValue(-1)
        self.jersey_spin.blockSignals(False)
        self.shield_combo.blockSignals(True)
        self.shield_combo.setCurrentIndex(0)
        self.shield_combo.blockSignals(False)
        if target is not None:
            self.first_edit.setPlaceholderText(f"now {target.data.get('first_name') or '(empty)'} · leave blank to keep")
            self.last_edit.setPlaceholderText(f"now {target.data.get('last_name') or '(empty)'} · leave blank to keep")
            self.first_edit.setEnabled(bool(target.data.get("first_name_writable")))
            self.last_edit.setEnabled(bool(target.data.get("last_name_writable")))

    def editor_reset(self) -> None:
        self.editor_target_changed(self._current)


# --------------------------------------------------------------------------
# Playbooks
# --------------------------------------------------------------------------

def _xbox_designers():
    """The Xbox lane's formation and play designers, when this build ships them.

    Both take a parsed book and its body and hand back the same mapping the
    PS2 recipe schema accepts, so they are reused as they are.  A build
    without them falls back to the bounded editors below.
    """
    try:
        from mod_editor.gui.play_designer_qt import FormationDesignerDialog, PlayDesignerDialog
    except Exception:
        return None, None
    return FormationDesignerDialog, PlayDesignerDialog


class _FormationTableDialog(QDialog):
    """Bounded fallback: donor formation, custom name, 11 slot positions in centimetres."""

    def __init__(self, book: Any, body: bytes, formation_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create a formation (clone and place)")
        self.setAccessibleName("Create a formation")
        self.result_payload: Optional[dict] = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_CUSTOM_NAME_CHARS)
        self.name_edit.setPlaceholderText(f"printable ASCII, up to {MAX_CUSTOM_NAME_CHARS}; blank keeps the donor's name")
        self.name_edit.setAccessibleName("Formation name")
        form.addRow("Name", self.name_edit)
        layout.addLayout(form)
        self.table = QTableWidget(11, 3)
        self.table.setHorizontalHeaderLabels(("Slot", "X (cm, + right)", "Depth (cm, − behind the line)"))
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Slot positions")
        self.table.setAccessibleDescription("Eleven slots, each an x and a depth in signed centimetres.")
        positions = self._donor_positions(body, formation_index)
        for slot in range(11):
            self.table.setItem(slot, 0, QTableWidgetItem(str(slot)))
            for column, value in ((1, positions[slot][0]), (2, positions[slot][1])):
                spin = QSpinBox()
                spin.setRange(-6000, 6000)
                spin.setValue(int(value))
                spin.setAccessibleName(f"Slot {slot} {'x' if column == 1 else 'depth'} in centimetres")
                self.table.setCellWidget(slot, column, spin)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Stage formation")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _donor_positions(body: bytes, formation_index: int) -> List[List[int]]:
        try:
            from mod_editor.core import nfl2k5_play_codec as codec
            from mod_editor.core.nfl2k5_playbook_inspector import FORMATION_BASE, FORMATION_SIZE

            offset = FORMATION_BASE + formation_index * FORMATION_SIZE
            record = codec.FormationRecord.from_bytes(body[offset:offset + FORMATION_SIZE])
            return [[int(slot.x[0]), int(slot.z[0])] for slot in record.slots]
        except Exception:
            return [[(slot - 5) * 120, 0] for slot in range(11)]

    def _accept(self) -> None:
        self.result_payload = {
            "custom_name": self.name_edit.text().strip() or None,
            "slot_positions": [[int(self.table.cellWidget(slot, 1).value()),
                                int(self.table.cellWidget(slot, 2).value())] for slot in range(11)],
            "category_index": None,
        }
        self.accept()


class PlaybooksTab(LaneTab):
    COLUMNS = (
        ("Book", lambda t: t.label),
        ("Formations", lambda t: f"{t.data.get('formations', 0)}/50"),
        ("Plays", lambda t: f"{t.data.get('plays', 0)}/270"),
        ("Nodes", lambda t: f"{t.data.get('nodes', 0):,}"),
        ("Headroom", lambda t: f"{t.data.get('formation_headroom', 0)} f · {t.data.get('play_headroom', 0)} p"
         + (" · AT THE PLAY CAP" if t.data.get("at_play_capacity") else "")),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        self._pending: Dict[str, List[dict]] = {"formations": [], "plays": [], "links": []}
        self._book: Any = None
        self._body: Optional[bytes] = None
        self.donor_formation = QComboBox()
        self.donor_formation.setAccessibleName("Donor formation")
        self.donor_play = QComboBox()
        self.donor_play.setAccessibleName("Donor play")
        form.addRow("Donor formation", self.donor_formation)
        form.addRow("Donor play", self.donor_play)
        buttons = QHBoxLayout()
        self.formation_button = QPushButton("Add formation…")
        self.formation_button.setAccessibleName("Design a formation cloned from the donor")
        self.play_button = QPushButton("Add play…")
        self.play_button.setAccessibleName("Design a play cloned from the donor")
        self.link_button = QPushButton("Add link…")
        self.link_button.setAccessibleName("Link a formation to a play by index")
        buttons.addWidget(self.formation_button)
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.link_button)
        holder = QWidget()
        holder.setLayout(buttons)
        form.addRow("Create", holder)
        self.pending_list = QListWidget()
        self.pending_list.setAccessibleName("Items to write into this book")
        self.pending_list.setMaximumHeight(110)
        form.addRow("For this book", self.pending_list)
        self.pending_clear = QPushButton("Discard these items")
        self.pending_clear.setAccessibleName("Discard the items designed for this book")
        form.addRow("", self.pending_clear)
        self.designer_note = QLabel("")
        self.designer_note.setWordWrap(True)
        self.designer_note.setObjectName("mutedLabel")
        form.addRow("", self.designer_note)
        self.formation_button.clicked.connect(self._add_formation)
        self.play_button.clicked.connect(self._add_play)
        self.link_button.clicked.connect(self._add_link)
        self.pending_clear.clicked.connect(self._discard_pending)
        formation_designer, play_designer = _xbox_designers()
        self.designer_note.setText(
            "Formations and plays are designed with the studio's own Play Designer, on this book read from your disc."
            if formation_designer is not None else
            "The Play Designer is not in this build; formations are placed from an 11-slot table and plays are clones of a donor.")

    def editor_values(self) -> dict:
        return {key: list(items) for key, items in self._pending.items() if items}

    def editor_target_changed(self, target: Optional[Target]) -> None:
        self._pending = {"formations": [], "plays": [], "links": []}
        self.pending_list.clear()
        self.donor_formation.clear()
        self.donor_play.clear()
        self._book, self._body = None, None
        if target is None or self.host.source_path is None:
            return
        try:
            self._book, self._body = self.lane.read_book(self.host.source_path, target.key)
        except ValidationError as exc:
            self.refusal_label.setText(str(exc))
            return
        for formation in self._book.formations:
            self.donor_formation.addItem(f"{formation.index}: {formation.name}", formation.index)
        for play in self._book.plays:
            self.donor_play.addItem(f"{play.index}: {play.name}", play.index)

    def editor_reset(self) -> None:
        self.editor_target_changed(self._current)

    def _pending_changed(self) -> None:
        self.pending_list.clear()
        for key, items in self._pending.items():
            for item in items:
                if key == "links":
                    text = f"link formation {item['formation_index']} → play {item['play_index']}"
                else:
                    text = f"{key[:-1]} from donor {item.get('donor_formation_index', item.get('donor_play_index'))}" \
                           f"{' named ' + repr(item['custom_name']) if item.get('custom_name') else ''}"
                self.pending_list.addItem(QListWidgetItem(text))
        self.schedule_validate()

    def _discard_pending(self) -> None:
        self._pending = {"formations": [], "plays": [], "links": []}
        self._pending_changed()

    def _add_formation(self) -> None:
        if self._book is None or self._body is None or self.donor_formation.currentData() is None:
            return
        donor = int(self.donor_formation.currentData())
        formation_designer, _play_designer = _xbox_designers()
        dialog_class = formation_designer or _FormationTableDialog
        dialog = dialog_class(self._book, self._body, donor, self)
        if dialog.exec_() == QDialog.Accepted and dialog.result_payload:
            payload = dict(dialog.result_payload)
            payload["donor_formation_index"] = donor
            self._pending["formations"].append(payload)
            self._pending_changed()

    def _add_play(self) -> None:
        if self._book is None or self._body is None or self.donor_play.currentData() is None:
            return
        donor = int(self.donor_play.currentData())
        _formation_designer, play_designer = _xbox_designers()
        if play_designer is None or self.donor_formation.currentData() is None:
            name, ok = _ask_name(self, "Name the cloned play")
            if not ok:
                return
            self._pending["plays"].append({"donor_play_index": donor, "custom_name": name or None})
        else:
            formation = int(self.donor_formation.currentData())
            dialog = play_designer(self._book, self._body, formation, donor, parent=self)
            if dialog.exec_() != QDialog.Accepted or not dialog.result_payload:
                return
            payload = dict(dialog.result_payload)
            link = payload.pop("link", False)
            payload["donor_play_index"] = donor
            self._pending["plays"].append({k: v for k, v in payload.items() if v is not None or k == "custom_name"})
            if link:
                # New plays are appended in order, so this play's index is the
                # book's play count plus its place among the pending additions.
                new_index = len(self._book.plays) + len(self._pending["plays"]) - 1
                self._pending["links"].append({"formation_index": formation, "play_index": new_index})
        self._pending_changed()

    def _add_link(self) -> None:
        if self._book is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Link a formation to a play")
        form = QFormLayout(dialog)
        formation_spin = QSpinBox()
        formation_spin.setRange(0, 49)
        formation_spin.setAccessibleName("Formation index")
        play_spin = QSpinBox()
        play_spin.setRange(0, 269)
        play_spin.setAccessibleName("Play index")
        form.addRow("Formation index", formation_spin)
        form.addRow("Play index", play_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec_() == QDialog.Accepted:
            self._pending["links"].append({"formation_index": int(formation_spin.value()),
                                           "play_index": int(play_spin.value())})
            self._pending_changed()


def _ask_name(parent: QWidget, title: str) -> "tuple[str, bool]":
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    form = QFormLayout(dialog)
    edit = QLineEdit()
    edit.setMaxLength(MAX_CUSTOM_NAME_CHARS)
    edit.setPlaceholderText("printable ASCII, blank keeps the donor's name")
    edit.setAccessibleName("Custom name")
    form.addRow("Name", edit)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    accepted = dialog.exec_() == QDialog.Accepted
    return edit.text().strip(), accepted


# --------------------------------------------------------------------------
# Stadium
# --------------------------------------------------------------------------

class StadiumTab(LaneTab):
    COLUMNS = (
        ("Lane", lambda t: t.label),
        ("Vertices", lambda t: str(t.data.get("position", {}).get("vertex_count", ""))),
        ("Shares span with", lambda t: str(int(t.data.get("payload_span_target_count", 1)) - 1) + " other"
         if int(t.data.get("payload_span_target_count", 1)) > 1 else "—"),
        ("Target id", lambda t: t.key),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        self.offsets: Dict[str, QDoubleSpinBox] = {}
        for axis, label in (("dx", "Move x by"), ("dy", "Move y by"), ("dz", "Move z by")):
            spin = QDoubleSpinBox()
            spin.setRange(-100000.0, 100000.0)
            spin.setDecimals(3)
            spin.setSingleStep(10.0)
            spin.setAccessibleName(f"{label} (scene units)")
            spin.setAccessibleDescription(
                "Added to every vertex of the lane; the result is rounded to the nearest binary32.")
            spin.valueChanged.connect(lambda _v: self.schedule_validate())
            form.addRow(label, spin)
            self.offsets[axis] = spin
        note = QLabel("Whether the recompressed scene fits its fixed span is decided during the build.")
        note.setWordWrap(True)
        note.setObjectName("mutedLabel")
        form.addRow("", note)

    def editor_values(self) -> dict:
        values: Dict[str, Any] = {axis: float(spin.value()) for axis, spin in self.offsets.items()}
        if self._current is not None:
            values["_row"] = self._current.data
        return values

    def editor_target_changed(self, target: Optional[Target]) -> None:
        for spin in self.offsets.values():
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)

    def editor_reset(self) -> None:
        self.editor_target_changed(self._current)

    def preview_text(self) -> str:
        # Composing a stadium recipe decodes the whole scene; the preview shows
        # the offsets instead and the exact recipe is built at Check.
        if not self._staged:
            return ""
        lines = [f"schema: {self.lane.recipe_schema}", f"catalog: pinned to the {self._scope} catalogue's digest"]
        for edit in self._staged:
            values = edit.values
            lines.append(f"{edit.target_key}: every vertex moved by "
                         f"({values.get('dx', 0)}, {values.get('dy', 0)}, {values.get('dz', 0)})")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------

class AudioTab(LaneTab):
    COLUMNS = (
        ("Sound", lambda t: t.label),
        ("Channels", lambda t: "stereo" if int(t.data.get("channels", 1)) == 2 else "mono"),
        ("Rate", lambda t: f"{t.data.get('sample_rate', '')} Hz"),
        ("Capacity", lambda t: f"{int(t.data.get('max_frames', 0)) / max(1, int(t.data.get('sample_rate', 1))):.2f} s"),
        ("Name unique", lambda t: "yes" if t.data.get("unique_name") else "no (shared)"),
        ("Slot id", lambda t: t.key),
    )

    def _build_editor(self, form: QFormLayout) -> None:
        row = QHBoxLayout()
        self.wav_edit = QLineEdit()
        self.wav_edit.setPlaceholderText("a strict 16-bit PCM WAV: fmt and data chunks only")
        self.wav_edit.setAccessibleName("Replacement WAV file")
        self.wav_edit.setAccessibleDescription(
            "16-bit PCM RIFF/WAVE with the slot's channel count; another sample rate is resampled to the slot's.")
        self.wav_edit.textChanged.connect(lambda _t: self._wav_changed())
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setAccessibleName("Choose a WAV file")
        self.browse_button.clicked.connect(self._browse)
        row.addWidget(self.wav_edit, 1)
        row.addWidget(self.browse_button)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("WAV", holder)
        self.fit_label = QLabel("")
        self.fit_label.setWordWrap(True)
        self.fit_label.setAccessibleName("How the WAV fits the slot")
        form.addRow("Fit", self.fit_label)

    def editor_values(self) -> dict:
        return {"wav": self.wav_edit.text().strip() or None}

    def editor_target_changed(self, target: Optional[Target]) -> None:
        self._wav_changed()

    def editor_reset(self) -> None:
        self.wav_edit.blockSignals(True)
        self.wav_edit.clear()
        self.wav_edit.blockSignals(False)
        self._wav_changed()

    def _browse(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(self, "Choose a replacement WAV", str(Path.home()),
                                                        self.host.WAV_FILTER)
        if selected:
            self.wav_edit.setText(selected)

    def _wav_changed(self) -> None:
        target = self._current
        text = self.wav_edit.text().strip()
        if target is None or not text:
            self.fit_label.setText("")
        else:
            try:
                info = self.lane.describe_wav(target, Path(text))
            except ValidationError as exc:
                self.fit_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
                self.fit_label.setText(str(exc))
            else:
                resampled = f" (resampled from {info['rate']} Hz)" if info["resampled"] else ""
                self.fit_label.setStyleSheet("" if info["fits"] else f"color: {_INVALID_COLOUR};")
                self.fit_label.setText(
                    f"Your WAV: {info['seconds']:.2f} s of {info['capacity_seconds']:.2f} s "
                    f"({info['frames']:,} of {target.data.get('max_frames'):,} frames at "
                    f"{target.data.get('sample_rate')} Hz){resampled}"
                    + ("" if info["fits"] else " — too long for this slot"))
        self.schedule_validate()


_MORE_TABS: Dict[str, type] = {"playbooks": PlaybooksTab, "stadium": StadiumTab, "audio": AudioTab}


def make_lane_tab(window: Any, lane: Any) -> LaneTab:
    """The tab class for a lane id."""
    classes: Dict[str, type] = {"text": TextTab, "colors": ColoursTab, "roster": RosterTab}
    classes.update(_MORE_TABS)
    try:
        return classes[lane.id](window, lane)
    except KeyError as exc:
        raise ValidationError(f"No tab is available for the {lane.title} lane in this build.") from exc


__all__ = [
    "AudioTab", "ColoursTab", "LaneTab", "PlaybooksTab", "RosterTab", "StadiumTab", "TargetTableModel",
    "TextTab", "make_lane_tab",
]
