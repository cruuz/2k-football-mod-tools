"""★ Rosters: the whole roster, editable -- the studio's answer to Flying Finn's GameSave Editor.

Finn's editor (Glen Leskinen, 2005-2016) is still the only way most people have ever edited an NFL
2K5 roster, and the reason is its layout: **team list -> player list -> attribute panel**, with the
player list doubling as the depth chart and every field on one modal.  This page keeps that shape and
adds the things his 2008 Delphi build could not: it works on the **disc** as well as on a save, it
has **undo/redo**, it marks what you changed, it shows you a **diff** of the whole edit before you
write anything, and it never touches your source file.

Layout, left to right:

* **Left** -- the 32 NFL clubs, the game's own extra squads (Pro Bowl, all-time, user teams), then
  Free Agents, the Draft Class and the leftover pools.  Selecting one fills the grid.
* **Middle** -- search (name, years pro or college), position chips, and the player grid: position
  badge, number, name, years pro, an OVR estimate and the depth slot, with ↑ ↓ that reorder the
  team's own pointer list -- which *is* the depth chart, exactly as Finn's arrows behave.
* **Right** -- the black header card (name, position, number, height, weight, age, years pro,
  college, contract) over the cards: **Athletic / Skills / Mental / Style / Appearance / Identity /
  Contract**.  A numeric card is a value plus a proportional bar: click or drag the bar to set it,
  ← → nudge by one, ↑ ↓ move to the next card.  Enum cards are dropdowns built from the tables lifted
  out of Finn's binary, so no value order is guessed.  The **Style** tab carries the three rating
  bytes that are style channels rather than scalars, with the controls the engine's own decoding
  implies: a Finesse / Balanced / Power segmented control over Power Run Style, a Signature release
  toggle that moves only the Scramble parity bit, and Kicking Style with its retail presets
  (EXPERIMENTAL -- no consumer proved).

The toolbar carries Finn's own one-shot passes -- Global Attribute Editor (with his "show affected
players" preview), Copy / Paste / Paste-attributes-only / Paste-photo, Advance Years Pro, Restore
Height/Weight/DOB -- plus a CSV twin that reads his semicolon export as well as ours, a validation
pass and the diff.

Writing: **nothing here writes to your source.**  "Save roster edits…" writes a small JSON document
that the Build & Share tab carries as the ``roster_edits`` step (and packs into a ``.2k5patch`` as an
asset); "Write a disc copy…" copies the loaded image first and edits the copy; a roster loaded from
an Xbox save writes a **re-signed** copy of the container beside the original, with every other
member byte for byte.

**Position scheme.**  A patched disc does not mean the retail 17 positions.  The page detects which
scheme the loaded source is on -- ``retail``, ``edge`` (the DE -> EDGE rename) or ``one_pool``
(EDGE / LB / interior, with OLB retired) -- from the disc's own patch states, falling back to the
roster records, and every label, chip, picker, CSV column and check follows it.  The selector on the
source row says what was detected and why, and lets you override it.  The **ratings never move**:
they are keyed by the position code the way the game keys them, so a one-pool LB is scored on the
linebacker card set and a one-pool EDGE on the defensive-end one.

Field credit: Flying Finn (Glen Leskinen) and Bad_AL, re-verified against the retail disc.  See
``mod_editor/core/nfl2k5_roster_records.py``.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_roster_records as rr

DISC_FILTER = "Disc images (*.iso *.xiso *.xiso.iso);;All files (*)"
SAVE_FILTER = "Xbox saves (*.zip SAVEGAME.DAT);;All files (*)"
EDITS_FILTER = "Roster edits (*.json);;All files (*)"
CSV_FILTER = "Spreadsheets (*.csv *.txt);;All files (*)"

# The studio's own sheet has no rule for a checked QToolButton, so a selected chip or segment would
# look identical to an unselected one.  Scope the rule to the buttons themselves.
TOGGLE_STYLE = (
    "QToolButton { border: 1px solid #24314f; border-radius: 4px; padding: 2px 8px; }"
    "QToolButton:checked { background: #f0b429; color: #0c1220; border-color: #f0b429;"
    " font-weight: bold; }"
)


# --------------------------------------------------------------------------------------------- undo
@dataclass
class UndoEntry:
    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]


class UndoStack:
    """A plain command stack.  Every edit on this page is reversible and says what it was."""

    def __init__(self, limit: int = 500, on_change: Callable[[], None] | None = None) -> None:
        self._done: list[UndoEntry] = []
        self._undone: list[UndoEntry] = []
        self._limit = limit
        self.on_change = on_change

    def push(self, entry: UndoEntry) -> None:
        self._done.append(entry)
        del self._done[: max(0, len(self._done) - self._limit)]
        self._undone.clear()
        if self.on_change is not None:
            self.on_change()

    def can_undo(self) -> bool:
        return bool(self._done)

    def can_redo(self) -> bool:
        return bool(self._undone)

    def undo(self) -> str:
        if not self._done:
            return ""
        entry = self._done.pop()
        entry.undo()
        self._undone.append(entry)
        return entry.label

    def redo(self) -> str:
        if not self._undone:
            return ""
        entry = self._undone.pop()
        entry.redo()
        self._done.append(entry)
        return entry.label

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()

    @property
    def depth(self) -> tuple[int, int]:
        return len(self._done), len(self._undone)


# --------------------------------------------------------------------------------------------- cards
class ValueBar(QWidget):
    """A proportional bar you can click or drag, the way Finn's slider row works.

    Keyboard: ← → nudge by one (his click-left / click-right), ↑ ↓ move to the next card.
    """

    valueChanged = pyqtSignal(int)
    focusMoved = pyqtSignal(int)

    def __init__(self, minimum: int, maximum: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = max(maximum, minimum + 1)
        self._value = minimum
        self.setMinimumHeight(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt naming
        clamped = max(self._minimum, min(self._maximum, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()
        self.valueChanged.emit(clamped)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802 - Qt naming
        self._minimum, self._maximum = minimum, max(maximum, minimum + 1)
        self.update()

    def _value_at(self, x: int) -> int:
        span = max(1, self.width() - 2)
        fraction = min(1.0, max(0.0, (x - 1) / span))
        return round(self._minimum + fraction * (self._maximum - self._minimum))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setFocus(Qt.MouseFocusReason)
        self.setValue(self._value_at(event.x()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.buttons() & Qt.LeftButton:
            self.setValue(self._value_at(event.x()))

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Minus):
            self.setValue(self._value - 1)
        elif key in (Qt.Key_Right, Qt.Key_Plus):
            self.setValue(self._value + 1)
        elif key == Qt.Key_Up:
            self.focusMoved.emit(-1)
        elif key == Qt.Key_Down:
            self.focusMoved.emit(1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#16203a"))
        span = self._maximum - self._minimum
        fraction = 0.0 if span <= 0 else (self._value - self._minimum) / span
        filled = int(round(fraction * (self.width() - 2)))
        if filled > 0:
            painter.fillRect(1, 1, filled, self.height() - 2, QColor("#f0b429"))
        if self.hasFocus():
            painter.setPen(QPen(QColor("#8fb8ff"), 1))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


class AttributeCard(QWidget):
    """One field: a caption, an editor (spin box or dropdown) and, for numbers, a bar."""

    changed = pyqtSignal(str, int)
    focusMoved = pyqtSignal(str, int)

    def __init__(self, name: str, caption: str, minimum: int, maximum: int,
                 choices: Sequence[str] | None = None, parent: QWidget | None = None, *,
                 segmented: bool = False, presets: Sequence[tuple[str, int]] = ()) -> None:
        super().__init__(parent)
        self.name = name
        self._quiet = False
        self.segments: list[QToolButton] = []
        self._presets: list[QToolButton] = []
        self.setObjectName("attributeCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        self.caption = QLabel(caption)
        self.caption.setWordWrap(True)
        font = self.caption.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        self.caption.setFont(font)
        layout.addWidget(self.caption)
        self.combo: QComboBox | None = None
        self.spin: QSpinBox | None = None
        self.bar: ValueBar | None = None
        # a dropdown whose row order is NOT the stored value (the Position picker under a scheme
        # that retired a code) carries its own value list; None means index == value
        self._values: list[int] | None = None
        if choices and segmented:
            # a three-state style control reads better as buttons than as a dropdown, and it is
            # how the game's own editor presents Finesse / Balanced / Power
            row = QHBoxLayout()
            row.setSpacing(2)
            for index, label in enumerate(choices):
                button = QToolButton()
                button.setText(label)
                button.setCheckable(True)
                button.setStyleSheet(TOGGLE_STYLE)
                button.setAccessibleName(f"{caption}: {label}")
                button.clicked.connect(lambda _c=False, i=index: self._segment_clicked(i))
                self.segments.append(button)
                row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
        elif choices:
            self.combo = QComboBox()
            self.combo.addItems(list(choices))
            self.combo.setAccessibleName(caption)
            self.combo.currentIndexChanged.connect(self._combo_changed)
            layout.addWidget(self.combo)
        else:
            self.spin = QSpinBox()
            self.spin.setRange(minimum, maximum)
            self.spin.setAccessibleName(caption)
            self.spin.valueChanged.connect(self._spin_changed)
            layout.addWidget(self.spin)
            self.bar = ValueBar(minimum, maximum)
            self.bar.valueChanged.connect(self._bar_changed)
            self.bar.focusMoved.connect(lambda step: self.focusMoved.emit(self.name, step))
            layout.addWidget(self.bar)
        if presets:
            preset_row = QHBoxLayout()
            preset_row.setSpacing(2)
            for label, number in presets:
                button = QToolButton()
                button.setText(label)
                button.setToolTip(f"{label}: {number}")
                button.setAccessibleName(f"{caption}: {label}")
                button.clicked.connect(lambda _c=False, v=number: self._preset_clicked(v))
                self._presets.append(button)
                preset_row.addWidget(button)
            preset_row.addStretch(1)
            layout.addLayout(preset_row)
        # a card carrying buttons needs room for their real labels, or Qt elides them to "Scr...ing";
        # ask the buttons themselves rather than guessing a width
        buttons = list(self.segments) + list(self._presets)
        # the size hints are taken before the studio's stylesheet adds its padding, so leave slack
        wanted = sum(button.sizeHint().width() + 14 for button in buttons) + 18
        self.setMinimumWidth(max(148, wanted))

    # ------------------------------------------------------------------ value
    def set_choices(self, labels: Sequence[str], values: Sequence[int] | None = None,
                    *, disabled: Sequence[int] = (), tooltips: Mapping[int, str] | None = None) -> None:
        """Rebuild a dropdown card.  ``values`` are the stored codes, ``disabled`` the ones the
        loaded scheme retired: a disabled row cannot be chosen from the list and the arrow keys step
        over it (asserted in the page's tests), so the picker cycles only live codes, while a record
        that already carries a retired one is still shown on it.  The panel refuses the write as
        well, so nothing depends on Qt's key handling alone."""

        if self.combo is None:
            return
        current = self.value()
        self._quiet = True
        try:
            self.combo.clear()
            self.combo.addItems(list(labels))
            self._values = list(values) if values is not None else None
            model = self.combo.model()
            for row in range(self.combo.count()):
                code = self._values[row] if self._values is not None else row
                item = model.item(row)
                if item is not None:
                    item.setEnabled(code not in set(disabled))
                    if tooltips and code in tooltips:
                        self.combo.setItemData(row, tooltips[code], Qt.ToolTipRole)
        finally:
            self._quiet = False
        self.set_value(current)

    def value(self) -> int:
        if self.segments:
            for index, button in enumerate(self.segments):
                if button.isChecked():
                    return index
            return 0
        if self.combo is not None:
            index = self.combo.currentIndex()
            if self._values is not None:
                return self._values[index] if 0 <= index < len(self._values) else 0
            return index
        assert self.spin is not None
        return self.spin.value()

    def set_value(self, value: int) -> None:
        self._quiet = True
        try:
            if self.segments:
                for index, button in enumerate(self.segments):
                    button.setChecked(index == int(value))
            elif self.combo is not None:
                if self._values is not None:
                    row = self._values.index(int(value)) if int(value) in self._values else -1
                    self.combo.setCurrentIndex(row)
                else:
                    self.combo.setCurrentIndex(max(0, min(self.combo.count() - 1, int(value))))
            else:
                assert self.spin is not None and self.bar is not None
                number = int(value)
                # a record can carry a value outside the sensible editing range (an empty draft-class
                # slot, or Finn's 0-127 "large attributes"); widen rather than lie about it
                if number < self.spin.minimum() or number > self.spin.maximum():
                    self.spin.setRange(min(self.spin.minimum(), number), max(self.spin.maximum(), number))
                    self.bar.setRange(self.spin.minimum(), self.spin.maximum())
                self.spin.setValue(number)
                self.bar.setValue(number)
        finally:
            self._quiet = False

    def set_dirty(self, dirty: bool) -> None:
        font = self.caption.font()
        font.setBold(dirty)
        self.caption.setFont(font)

    def focus_editor(self) -> None:
        target = self.bar or self.combo or self.spin or (self.segments[0] if self.segments else None)
        if target is not None:
            target.setFocus(Qt.TabFocusReason)

    # ------------------------------------------------------------------ signals
    def _segment_clicked(self, index: int) -> None:
        for position, button in enumerate(self.segments):
            button.setChecked(position == index)
        if not self._quiet:
            self.changed.emit(self.name, int(index))

    def _preset_clicked(self, value: int) -> None:
        self.set_value(value)
        self.changed.emit(self.name, int(value))

    def _combo_changed(self, index: int) -> None:
        if self._quiet or index < 0:
            return
        self.changed.emit(self.name, int(self.value()))

    def _spin_changed(self, value: int) -> None:
        if self.bar is not None:
            self.bar.blockSignals(True)
            self.bar.setValue(value)
            self.bar.blockSignals(False)
        if not self._quiet:
            self.changed.emit(self.name, int(value))

    def _bar_changed(self, value: int) -> None:
        if self.spin is not None and self.spin.value() != value:
            self.spin.setValue(value)      # routes through _spin_changed


# --------------------------------------------------------------------------------------------- global
def _target_label(name: str) -> str:
    """The caption for a global-edit target: a rating name, a field label, or a derived control."""

    if name in rr.RATING_LABELS:
        return rr.RATING_LABELS[name]
    if name == "power_run_style_bucket":
        return "Power Run Style (Finesse / Balanced / Power)"
    if name == "throw_style":
        return "Signature release (Scramble parity bit)"
    if name in rr.FIELD_BY_NAME:
        return rr.FIELD_BY_NAME[name].label
    return name.replace("_", " ").title()


class GlobalEditDialog(QDialog):
    """Finn's Global Attribute Editor: pick an attribute, a rule and a scope, preview, apply."""

    def __init__(self, panel: "RosterEditorPanel", parent: QWidget | None = None) -> None:
        super().__init__(parent or panel)
        self.setWindowTitle("Global Attribute Editor")
        self._panel = panel
        self.preview_rows: list[dict[str, Any]] = []
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.attribute = QComboBox()
        for name in rr.RATING_UI_ORDER:
            self.attribute.addItem(rr.RATING_LABELS[name], name)
        # the style channels, so a sweep can say "every QB with Speed >= 80 -> signature release"
        for name in ("power_run_style_bucket", "throw_style", "scramble", "kicking_style"):
            self.attribute.addItem(_target_label(name), name)
        for name in ("years_pro", "weight", "height", "contract_value", "contract_length",
                     "contract_remaining", "photo_id"):
            self.attribute.addItem(_target_label(name), name)
        top.addWidget(QLabel("Attribute"))
        top.addWidget(self.attribute, 1)
        self.mode = QComboBox()
        self.mode.addItem("Set equal to", "equal")
        self.mode.addItem("Add / subtract", "add")
        self.mode.addItem("Percent", "percent")
        top.addWidget(self.mode)
        self.value = QSpinBox()
        self.value.setRange(-999, 999)
        self.value.setValue(1)
        top.addWidget(self.value)
        layout.addLayout(top)

        limits = QHBoxLayout()
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 255)
        self.maximum = QSpinBox()
        self.maximum.setRange(0, 255)
        self.maximum.setValue(rr.RATING_MAX)
        self.large_values = QCheckBox("Large attribute values (0-127)")
        self.large_values.toggled.connect(
            lambda on: self.maximum.setValue(rr.RATING_MAX_LARGE if on else rr.RATING_MAX))
        self.rookies_only = QCheckBox("Rookies only")
        limits.addWidget(QLabel("Min"))
        limits.addWidget(self.minimum)
        limits.addWidget(QLabel("Max"))
        limits.addWidget(self.maximum)
        limits.addWidget(self.large_values)
        limits.addWidget(self.rookies_only)
        limits.addStretch(1)
        layout.addLayout(limits)

        scheme = panel.scheme
        scope = QGroupBox(f"Positions (none ticked = every position) — {rr.SCHEME_TITLES[scheme]}")
        scope_layout = QGridLayout(scope)
        # named in the loaded scheme, and a code the scheme retired is offered greyed out so a
        # sweep cannot be aimed at a pool no player is in
        self.positions: dict[str, QCheckBox] = {}
        for code in range(len(rr.POSITIONS)):
            label = rr.position_name(code, scheme)
            box = QCheckBox(label)
            box.setToolTip(f"{rr.position_long_name(code, scheme)} (code {code})")
            if rr.is_retired_position(code, scheme):
                box.setEnabled(False)
                box.setToolTip(f"{rr.position_long_name(code, scheme)} (code {code}) — retired on "
                               f"this roster; nobody carries it")
            self.positions[label] = box
            scope_layout.addWidget(box, code // 6, code % 6)
        layout.addWidget(scope)
        self.current_team_only = QCheckBox("This team only")
        layout.addWidget(self.current_team_only)

        where_row = QHBoxLayout()
        self.where_enabled = QCheckBox("Only where")
        where_row.addWidget(self.where_enabled)
        self.where_attribute = QComboBox()
        for name in list(rr.RATING_UI_ORDER) + ["scramble", "kicking_style", "throw_style",
                                                "power_run_style_bucket", "years_pro", "weight",
                                                "height", "position"]:
            self.where_attribute.addItem(_target_label(name), name)
        where_row.addWidget(self.where_attribute, 1)
        self.where_operator = QComboBox()
        for symbol in (">=", ">", "<=", "<", "==", "!="):
            self.where_operator.addItem(symbol, symbol)
        where_row.addWidget(self.where_operator)
        self.where_value = QSpinBox()
        self.where_value.setRange(0, 255)
        self.where_value.setValue(80)
        # "Position" compares the stored code, so name the codes of the loaded scheme rather than
        # leaving a bare number nobody can map
        self.where_value.setToolTip(
            "For Position the value is the roster code: "
            + ", ".join(f"{code} {name}" for code, name in enumerate(rr.position_names(scheme))))
        where_row.addWidget(self.where_value)
        layout.addLayout(where_row)

        self.preview_button = QPushButton("Show affected players")
        self.preview_button.clicked.connect(self.refresh_preview)
        layout.addWidget(self.preview_button)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(180)
        layout.addWidget(self.preview, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ behaviour
    def settings(self) -> dict[str, Any]:
        chosen = [name for name, box in self.positions.items() if box.isChecked()]
        where = None
        if self.where_enabled.isChecked():
            where = (str(self.where_attribute.currentData()), str(self.where_operator.currentData()),
                     int(self.where_value.value()))
        return {"attribute": str(self.attribute.currentData()),
                "mode": str(self.mode.currentData()), "value": float(self.value.value()),
                "positions": chosen, "rookies_only": self.rookies_only.isChecked(),
                "minimum": self.minimum.value(), "maximum": self.maximum.value(), "where": where,
                "current_team_only": self.current_team_only.isChecked()}

    def refresh_preview(self) -> list[dict[str, Any]]:
        self.preview_rows = self._panel.global_edit_preview(**self.settings())
        lines = [f"{row['name']} ({row['position']}): {row['before']} -> {row['after']}"
                 for row in self.preview_rows[:400]]
        if len(self.preview_rows) > 400:
            lines.append(f"... and {len(self.preview_rows) - 400} more")
        self.preview.setPlainText("\n".join(lines) or "No player would change.")
        return self.preview_rows

    def _apply(self) -> None:
        if not self.preview_rows:
            self.refresh_preview()
        count = self._panel.apply_global_edit(self.preview_rows, str(self.attribute.currentData()))
        self.preview.setPlainText(f"Applied to {count} players.")
        self.preview_rows = []


# --------------------------------------------------------------------------------------------- panel
class RosterEditorPanel(QWidget):
    """The ★ Rosters workspace."""

    roster_edits_changed = pyqtSignal(str)          # path of the saved roster-edits document

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self.document: rr.RosterDocument | None = None
        self._baseline: rr.RosterDocument | None = None
        self._source_path: Path | None = None
        self._source_kind = ""
        self._clipboard: rr.PlayerRecord | None = None
        self._dirty: set[tuple[str, int]] = set()
        self._rows: list[rr.Player] = []
        self._group: tuple[str, int] = ("team", 0)
        self._chip = "All"
        self._scheme = "retail"                 # what the labels follow right now
        self._scheme_choice = "auto"            # what the selector says: auto or a fixed scheme
        self._scheme_detection: dict[str, Any] = {}
        self._edits_path: Path | None = None
        self.undo_stack = UndoStack(on_change=self._refresh_actions)
        self.cards: dict[str, AttributeCard] = {}
        self._card_order: list[str] = []
        self._page_cards: dict[int, list[str]] = {}
        self._build()
        self._refresh_actions()

    @property
    def scheme(self) -> str:
        """Which position table the page is reading codes through (see rr.POSITION_SCHEMES)."""

        return self.document.scheme if self.document is not None else self._scheme

    # ------------------------------------------------------------------ construction
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Every player on the disc or in a save: names, position, number, all 28 rating bytes, "
            "every appearance and equipment slot, height, weight, date of birth, college, the "
            "play-by-play and portrait ids, the depth order and the contract. Your source is never written."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        source_row = QHBoxLayout()
        self.open_disc_button = QPushButton("Open a disc…")
        self.open_disc_button.clicked.connect(self._choose_disc)
        self.open_save_button = QPushButton("Open an Xbox save…")
        self.open_save_button.clicked.connect(self._choose_save)
        self.use_loaded_button = QPushButton("Use the loaded XISO")
        self.use_loaded_button.clicked.connect(self.load_from_facade)
        self.source_label = QLabel("No roster loaded.")
        self.source_label.setWordWrap(True)
        for widget in (self.open_disc_button, self.open_save_button, self.use_loaded_button):
            source_row.addWidget(widget)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        scheme_row = QHBoxLayout()
        scheme_row.addWidget(QLabel("Position scheme"))
        self.scheme_combo = QComboBox()
        self.scheme_combo.setAccessibleName("Position scheme")
        self.scheme_combo.addItem("Auto (detect)", "auto")
        for name in rr.POSITION_SCHEMES:
            self.scheme_combo.addItem(rr.SCHEME_TITLES[name], name)
        self.scheme_combo.setToolTip(
            "What a position CODE means on the loaded source. A disc says for itself (the EDGE "
            "rename and the one-pool position_pools patch report their own state); a save or a bare "
            "roster body can only be inferred from the records, and the EDGE rename is invisible "
            "there, so override it here if you know better.")
        self.scheme_combo.activated.connect(self._scheme_chosen)
        scheme_row.addWidget(self.scheme_combo)
        self.scheme_label = QLabel("Retail table until a roster is loaded.")
        self.scheme_label.setWordWrap(True)
        scheme_row.addWidget(self.scheme_label, 1)
        layout.addLayout(scheme_row)

        tools = QHBoxLayout()
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button = QPushButton("Redo")
        self.redo_button.clicked.connect(self.redo)
        self.global_button = QPushButton("Global Attribute Editor…")
        self.global_button.clicked.connect(self.open_global_editor)
        self.copy_button = QPushButton("Copy player")
        self.copy_button.clicked.connect(self.copy_player)
        self.paste_button = QToolButton()
        self.paste_button.setText("Paste ▾")
        self.paste_button.setPopupMode(QToolButton.InstantPopup)
        paste_menu = QMenu(self.paste_button)
        paste_menu.addAction("Paste player", lambda: self.paste_player("all"))
        paste_menu.addAction("Paste attributes only", lambda: self.paste_player("attributes"))
        paste_menu.addAction("Paste photo only", lambda: self.paste_player("photo"))
        self.paste_button.setMenu(paste_menu)
        self.passes_button = QToolButton()
        self.passes_button.setText("One-shot passes ▾")
        self.passes_button.setPopupMode(QToolButton.InstantPopup)
        passes_menu = QMenu(self.passes_button)
        passes_menu.addAction("Advance years pro (whole league)", lambda: self.advance_years_pro(False))
        passes_menu.addAction("Advance years pro (this list)", lambda: self.advance_years_pro(True))
        passes_menu.addAction("Restore height / weight / date of birth", self.restore_measurements)
        self.passes_button.setMenu(passes_menu)
        self.csv_button = QToolButton()
        self.csv_button.setText("CSV ▾")
        self.csv_button.setPopupMode(QToolButton.InstantPopup)
        csv_menu = QMenu(self.csv_button)
        csv_menu.addAction("Export this list…", lambda: self._export_csv(False))
        csv_menu.addAction("Export every player…", lambda: self._export_csv(True))
        csv_menu.addAction("Import a CSV…", self._import_csv)
        self.csv_button.setMenu(csv_menu)
        for widget in (self.undo_button, self.redo_button, self.global_button, self.copy_button,
                       self.paste_button, self.passes_button, self.csv_button):
            tools.addWidget(widget)
        tools.addStretch(1)
        self.save_edits_button = QPushButton("Save roster edits…")
        self.save_edits_button.setToolTip("Writes the edits as a small JSON document. Build & Share "
                                          "carries it as the roster_edits step and packs it into a "
                                          ".2k5patch, so the edit travels without the disc.")
        self.save_edits_button.clicked.connect(self._save_edits)
        self.write_button = QPushButton("Write a copy…")
        self.write_button.setToolTip("Disc: copies the image and edits the copy. Save: writes a "
                                     "re-signed container beside the original.")
        self.write_button.clicked.connect(self._write_copy)
        tools.addWidget(self.save_edits_button)
        tools.addWidget(self.write_button)
        layout.addLayout(tools)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_team_pane())
        splitter.addWidget(self._build_grid_pane())
        splitter.addWidget(self._build_editor_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 4)          # the cards are the widest thing on the page
        splitter.setSizes([220, 420, 720])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("Load a disc or a save to begin.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _build_team_pane(self) -> QWidget:
        pane = QWidget()
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(QLabel("Teams and pools"))
        self.team_list = QListWidget()
        self.team_list.setAccessibleName("Teams and pools")
        self.team_list.currentRowChanged.connect(self._team_changed)
        box.addWidget(self.team_list, 1)
        self.pool_label = QLabel("")
        self.pool_label.setWordWrap(True)
        box.addWidget(self.pool_label)
        return pane

    def _build_grid_pane(self) -> QWidget:
        pane = QWidget()
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, years pro or college")
        self.search.setAccessibleName("Search players")
        self.search.textChanged.connect(lambda _t: self.refresh_grid())
        box.addWidget(self.search)

        self.chip_row = QHBoxLayout()
        self.chip_row.setSpacing(2)
        self.chips: dict[str, QToolButton] = {}
        self._rebuild_chips()
        box.addLayout(self.chip_row)

        self.player_table = QTableWidget(0, 6)
        self.player_table.setHorizontalHeaderLabels(["POS", "#", "Player", "Yrs", "OVR", "Depth"])
        self.player_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.player_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.player_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.player_table.verticalHeader().setVisible(False)
        self.player_table.setAccessibleName("Players")
        self.player_table.currentCellChanged.connect(
            lambda row, _c, _pr, _pc: self._select_row(row))
        box.addWidget(self.player_table, 1)

        order = QHBoxLayout()
        self.up_button = QPushButton("↑ Move up")
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button = QPushButton("↓ Move down")
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        order.addWidget(self.up_button)
        order.addWidget(self.down_button)
        order.addStretch(1)
        self.count_label = QLabel("")
        order.addWidget(self.count_label)
        box.addLayout(order)
        return pane

    def _build_editor_pane(self) -> QWidget:
        pane = QWidget()
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setObjectName("playerHeaderCard")
        header.setFrameShape(QFrame.StyledPanel)
        header_box = QVBoxLayout(header)
        header_box.setContentsMargins(10, 8, 10, 8)
        header_box.setSpacing(2)
        self.header_name = QLabel("—")
        name_font = QFont()
        name_font.setPointSizeF(name_font.pointSizeF() + 3)
        name_font.setBold(True)
        self.header_name.setFont(name_font)
        self.header_stats = QLabel("")
        self.header_stats.setWordWrap(True)
        self.header_contract = QLabel("")
        self.header_profile = QLabel("")
        self.header_profile.setWordWrap(True)
        self.header_profile.setToolTip(
            "The game keys its per-position rating labels and getters off the position CODE, not "
            "off the name a patched disc prints, so renaming a position never changes which ratings "
            "matter: a one-pool LB is still read on the linebacker card set and a one-pool EDGE on "
            "the defensive-end one.")
        header_box.addWidget(self.header_name)
        header_box.addWidget(self.header_stats)
        header_box.addWidget(self.header_contract)
        header_box.addWidget(self.header_profile)
        box.addWidget(header)

        names = QHBoxLayout()
        self.first_field = QLineEdit()
        self.first_field.setPlaceholderText("First")
        self.first_field.setAccessibleName("First name")
        self.first_field.editingFinished.connect(lambda: self._name_committed("first"))
        self.last_field = QLineEdit()
        self.last_field.setPlaceholderText("Last")
        self.last_field.setAccessibleName("Last name")
        self.last_field.editingFinished.connect(lambda: self._name_committed("last"))
        self.college_combo = QComboBox()
        self.college_combo.setAccessibleName("College")
        self.college_combo.activated.connect(self._college_chosen)
        names.addWidget(QLabel("First"))
        names.addWidget(self.first_field, 1)
        names.addWidget(QLabel("Last"))
        names.addWidget(self.last_field, 1)
        names.addWidget(QLabel("College"))
        names.addWidget(self.college_combo, 1)
        box.addLayout(names)
        self.name_pool_label = QLabel("")
        self.name_pool_label.setWordWrap(True)
        box.addWidget(self.name_pool_label)

        self.tabs = QTabWidget()
        for group, fields in rr.ATTRIBUTE_CARDS.items():
            index = self.tabs.addTab(self._build_card_page(group, fields), group)
            self._page_cards[index] = list(fields)
        self.tabs.addTab(self._build_report_page(), "Checks")
        box.addWidget(self.tabs, 1)
        return pane

    def _build_card_page(self, group: str, fields: Sequence[str]) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(6)
        cards = []
        for name in fields:
            card = self._make_card(name)
            self.cards[name] = card
            self._card_order.append(name)
            card.changed.connect(self._card_changed)
            card.focusMoved.connect(self._move_card_focus)
            cards.append(card)
        # cards carrying buttons are wide; two of those fit the pane where three would force a
        # horizontal scrollbar, which is the one scroll direction nobody wants
        columns = 2 if any(card.minimumWidth() > 200 for card in cards) else 3
        for index, card in enumerate(cards):
            grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        grid.setRowStretch(grid.rowCount(), 1)
        area.setWidget(host)
        area.setObjectName(f"cards_{group.lower()}")
        return area

    STYLE_CAPTIONS = {
        "power_run_style_bucket": "Power Run Style",
        "power_run_style": "Power Run Style (raw byte)",
        "throw_style": "Signature release (unorthodox delivery)",
        "kicking_style": "Kicking Style (experimental)",
    }
    STYLE_TOOLTIPS = {
        "power_run_style_bucket":
            "Ball-carrier style. The game decodes +0x4D as Finesse below 33, Balanced below 66, Power "
            "above, and its own cycler writes 1 / 50 / 99. Gameplay reads the byte as a blend weight "
            "(value x 0.01), so the raw card below still works.",
        "power_run_style": "The raw +0x4D byte behind the Finesse / Balanced / Power control.",
        "throw_style":
            "The LOW BIT of Scramble (+0x4F). It is the only bit test on any rating byte in the whole "
            "executable (0x002D92B1) and it picks which family of directional animation sets the "
            "player uses. In the retail roster exactly three quarterbacks carry it: Michael Vick, "
            "Rich Gannon and Philip Rivers, the three unorthodox deliveries, so it reads as a hand-set "
            "signature-release flag. Changing it leaves the Scramble rating where it is. Unwitnessed "
            "in game.",
        "scramble":
            "A hidden rating the Player Card never prints, but the game's own roster editor does. "
            "Magnitude and parity are read separately: this slider moves the magnitude and preserves "
            "the throw-style bit. With Agility it also picks the mobile-QB animation family "
            "(0.01 x Scramble + 0.01 x Agility above 1.5).",
        "kicking_style":
            "EXPERIMENTAL. The game names +0x4B KICKING STYLE and holds it at 99 for every kicker, 1 "
            "for every punter and 49 for everyone else, but no consumer has been proved. Presets are "
            "the three retail values.",
        "hand": "Best Hand -- +0x18 bit 1, the row the game's own editor toggles. Not related to the "
                "Scramble parity bit: they do not correlate in retail data.",
    }

    def _make_card(self, name: str) -> AttributeCard:
        caption = self.STYLE_CAPTIONS.get(name) or rr.RATING_LABELS.get(name) or (
            rr.FIELD_BY_NAME[name].label if name in rr.FIELD_BY_NAME else name.replace("_", " ").title())
        choices = rr.ENUMS.get(name)
        if name == "position":
            choices = rr.position_names(self._scheme)
        presets: tuple[tuple[str, int], ...] = ()
        if name == "scramble":
            presets = tuple(rr.SCRAMBLE_PRESETS)
        elif name == "kicking_style":
            presets = tuple(rr.KICKING_STYLE_PRESETS)
        if name in rr.RATING_BYTE_ORDER:
            card = AttributeCard(name, caption, 0, rr.RATING_MAX_LARGE, presets=presets)
        elif choices is not None:
            card = AttributeCard(name, caption, 0, len(choices) - 1, choices,
                                 segmented=name in rr.VIRTUAL_FIELDS or name == "hand")
        else:
            low, high = rr.NUMERIC_LIMITS.get(name, (0, 255))
            card = AttributeCard(name, caption, low, high)
        tooltip = self.STYLE_TOOLTIPS.get(name) or (
            rr.FIELD_BY_NAME[name].note if name in rr.FIELD_BY_NAME else "")
        if tooltip:
            card.setToolTip(tooltip)
            card.caption.setToolTip(tooltip)
        return card

    def _build_report_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        row = QHBoxLayout()
        self.validate_button = QPushButton("Check this roster")
        self.validate_button.clicked.connect(self.run_validation)
        self.diff_button = QPushButton("Show my changes")
        self.diff_button.clicked.connect(self.refresh_diff)
        row.addWidget(self.validate_button)
        row.addWidget(self.diff_button)
        row.addStretch(1)
        box.addLayout(row)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setAccessibleName("Validation and diff report")
        box.addWidget(self.report, 1)
        return page

    # ------------------------------------------------------------------ position scheme
    def _rebuild_chips(self) -> None:
        """The position chips of the loaded scheme (one pool adds an EDGE chip of its own)."""

        order = rr.chip_order(self._scheme)
        while self.chip_row.count():
            item = self.chip_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.chips = {}
        if self._chip not in order:
            self._chip = "All"
        groups = rr.position_groups(self._scheme)
        for label in order:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setStyleSheet(TOGGLE_STYLE)
            if label == "All":
                button.setToolTip("Show every position")
            else:
                members = ", ".join(rr.position_name(code, self._scheme) for code in groups.get(label, ()))
                button.setToolTip(f"Show {label} only ({members})")
            button.setChecked(label == self._chip)
            button.clicked.connect(lambda _c=False, name=label: self._chip_clicked(name))
            self.chips[label] = button
            self.chip_row.addWidget(button)
        self.chip_row.addStretch(1)

    def _refresh_position_card(self) -> None:
        """Name the Position picker in the loaded scheme and grey out any code it retired."""

        card = self.cards.get("position")
        if card is None:
            return
        codes = list(range(len(rr.POSITIONS)))
        labels: list[str] = []
        tooltips: dict[int, str] = {}
        for code in codes:
            name = rr.position_name(code, self._scheme)
            retired = rr.is_retired_position(code, self._scheme)
            labels.append(f"{name} (retired)" if retired else name)
            tooltips[code] = (f"{rr.position_long_name(code, self._scheme)} — code {code}"
                              + (" — this roster's scheme retired it; the picker will not write it"
                                 if retired else ""))
        card.set_choices(labels, codes, disabled=rr.retired_position_codes(self._scheme),
                         tooltips=tooltips)

    def _scheme_chosen(self, _index: int) -> None:
        choice = str(self.scheme_combo.currentData())
        self._scheme_choice = choice
        detected = str(self._scheme_detection.get("scheme", "retail"))
        self.apply_scheme(detected if choice == "auto" else choice)

    def apply_scheme(self, scheme: str, *, refresh: bool = True) -> str:
        """Read every position code through ``scheme`` and relabel the whole page.

        ``refresh=False`` is for the load path, where the team list has not been rebuilt yet and
        the caller redraws the grid itself.
        """

        self._scheme = rr.normalise_scheme(scheme)
        if self.document is not None:
            self.document.set_scheme(self._scheme)
        self._rebuild_chips()
        self._refresh_position_card()
        self._refresh_scheme_label()
        if refresh and self.document is not None:
            self.refresh_grid()
            self._show_player(self.selected_player())
        return self._scheme

    def _refresh_scheme_label(self) -> None:
        detection = self._scheme_detection
        title = rr.SCHEME_TITLES[self._scheme]
        if not detection:
            self.scheme_label.setText(f"{title} — nothing loaded yet.")
            return
        detected = str(detection.get("scheme", "retail"))
        lead = (f"{title} — detected from the {detection.get('source', 'roster data')}"
                if self._scheme_choice == "auto"
                else f"{title} — chosen by you (detection said {rr.SCHEME_TITLES[detected]})")
        parts = [f"{lead}: {detection.get('why', '')}."]
        if detection.get("note"):
            parts.append(f"⚠ {detection['note']}.")
        if detection.get("confidence") == "low" and self._scheme_choice == "auto":
            parts.append("Low confidence — set it yourself if you know the disc.")
        self.scheme_label.setText(" ".join(parts))

    def detect_scheme(self, document: rr.RosterDocument, source: Path | None = None) -> dict[str, Any]:
        """What scheme this source is on: the disc's own patch states first, its records second."""

        try:
            return rr.detect_scheme(document, source=source)
        except Exception as exc:                                   # noqa: BLE001 - never fatal
            return {"scheme": "retail", "confidence": "low", "source": "fallback", "census": {},
                    "note": "", "why": f"detection failed ({type(exc).__name__}: {exc})"}

    # ------------------------------------------------------------------ loading
    def load_document(self, document: rr.RosterDocument, *, label: str = "",
                      source: Path | None = None, kind: str = "",
                      detection: dict[str, Any] | None = None) -> None:
        """Adopt a parsed roster (the tests and the studio both use this)."""

        self.document = document
        self._baseline = None
        self._source_path = source
        self._source_kind = kind
        self._dirty.clear()
        self.undo_stack.clear()
        self._clipboard = None
        self._scheme_detection = detection if detection is not None else self.detect_scheme(document)
        self.apply_scheme(str(self._scheme_detection["scheme"]) if self._scheme_choice == "auto"
                          else self._scheme_choice, refresh=False)
        summary = document.summary()
        self.source_label.setText(label or f"{summary['players']} players, {summary['teams']} teams")
        self.college_combo.blockSignals(True)
        self.college_combo.clear()
        self.college_combo.addItems(document.colleges)
        self.college_combo.blockSignals(False)
        self._populate_teams()
        self.refresh_grid()
        self._refresh_pool_label()
        self._set_status(
            f"{summary['players']} players · {summary['teams']} teams · {summary['free_agents']} free "
            f"agents · {summary['draft_class']} in the draft class · "
            f"{summary['names']['unique']} distinct names in a {summary['names']['capacity_bytes']}-byte pool"
            f" · {rr.SCHEME_TITLES[self._scheme]}")

    def load_from_facade(self) -> bool:
        """Load the roster out of whatever XISO the studio already has open."""

        source = getattr(self._facade, "source_path", None) or getattr(self._facade, "source", None)
        if not source:
            self._set_status("No XISO is loaded. Use File → Open XISO first, or Open a disc… here.")
            return False
        return self.load_disc(Path(str(source)))

    def load_disc(self, path: Path | str) -> bool:
        try:
            document = rr.load_image(path)
        except Exception as exc:  # noqa: BLE001 - one message for the status line
            self._set_status(f"Could not read the roster: {type(exc).__name__}: {exc}")
            return False
        state = "retail" if rr.resource_status(
            document.resource_header + bytes(document.body)) == "retail" else "already edited"
        # a disc can say which position scheme it is on: mod_build.inspect reads the EDGE rename and
        # the one-pool position_pools patch straight off its executable
        self.load_document(document, label=f"{Path(path).name} ({state})", source=Path(path),
                           kind="disc", detection=self.detect_scheme(document, Path(path)))
        return True

    def load_save(self, path: Path | str) -> bool:
        try:
            container = rr.SaveContainer.load(path)
            document = container.document()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Could not read the save: {type(exc).__name__}: {exc}")
            return False
        # a save carries no executable, so the scheme can only come from the records
        self.load_document(document, label=f"{Path(path).name} (signature verified)",
                           source=Path(path), kind="save", detection=self.detect_scheme(document))
        return True

    def _choose_disc(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Open an NFL 2K5 disc image", "", DISC_FILTER)
        if chosen:
            self.load_disc(chosen)

    def _choose_save(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Open an Xbox NFL 2K5 save", "", SAVE_FILTER)
        if chosen:
            self.load_save(chosen)

    # ------------------------------------------------------------------ team list
    def _populate_teams(self) -> None:
        self.team_list.blockSignals(True)
        self.team_list.clear()
        assert self.document is not None
        for team in self.document.teams:
            label = f"{team.abbreviation or team.nickname or f'Team {team.index}'} · {len(team.slots)}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, ("team", team.index))
            item.setToolTip(team.display)
            item.setSizeHint(QSize(200, 22))
            self.team_list.addItem(item)
        for key, caption in (("free_agent", "Free Agents"), ("draft_class", "Draft Class"),
                             ("pool", "Other pools")):
            count = len(self.document.group_players(key))
            item = QListWidgetItem(f"{caption} · {count}")
            item.setData(Qt.UserRole, (key, -1))
            item.setSizeHint(QSize(200, 22))
            self.team_list.addItem(item)
        self.team_list.blockSignals(False)
        self.team_list.setCurrentRow(0)
        self._group = ("team", 0)

    def _team_changed(self, row: int) -> None:
        item = self.team_list.item(row)
        if item is None:
            return
        self._group = tuple(item.data(Qt.UserRole))
        self.refresh_grid()

    def _chip_clicked(self, name: str) -> None:
        for label, button in self.chips.items():
            button.setChecked(label == name)
        self._chip = name
        self.refresh_grid()

    # ------------------------------------------------------------------ grid
    def visible_players(self) -> list[rr.Player]:
        if self.document is None:
            return []
        kind, index = self._group
        if kind == "team" and not 0 <= index < len(self.document.teams):
            return []
        players = self.document.team_players(index) if kind == "team" else self.document.group_players(kind)
        if self._chip != "All":
            # by CODE: a chip must not miss a player because the scheme renamed his position
            wanted = set(rr.position_groups(self._scheme).get(self._chip, ()))
            players = [p for p in players if p.record.values["position"] in wanted]
        needle = self.search.text().strip().casefold()
        if needle:
            players = [p for p in players
                       if needle in p.display.casefold()
                       or needle in p.college.casefold()
                       or needle == str(p.record.values["years_pro"])]
        return players

    def _depth_chart(self) -> dict[int, list[rr.Player]]:
        """This team's players grouped by position CODE in rank order -- the game's own chains."""

        kind, index = self._group
        if self.document is None or kind != "team" or not 0 <= index < len(self.document.teams):
            return {}
        return self.document.depth_chart(index)

    def _depth_note(self, chart: dict[int, list[rr.Player]], player: rr.Player) -> str:
        code = player.record.values["position"]
        group = chart.get(code, [])
        for position, candidate in enumerate(group):
            if candidate is player:
                return (f"{rr.position_long_name(code, self._scheme)} #{position + 1} of "
                        f"{len(group)} on this team (rank {player.record.values['depth_rank']}, "
                        f"side {player.record.values['depth_side']})")
        return ""

    def refresh_grid(self) -> None:
        players = self.visible_players()
        self._rows = players
        chart = self._depth_chart()
        self.player_table.blockSignals(True)
        self.player_table.setRowCount(len(players))
        for row, player in enumerate(players):
            record = player.record
            marker = "● " if (player.pool, player.index) in self._dirty else ""
            cells = (record.position_name, str(record.values["jersey"]), f"{marker}{player.display}",
                     str(record.values["years_pro"]), str(record.overall()),
                     f"{record.values['depth_rank']}/{record.values['depth_side']}"
                     + (" IR" if record.on_injured_reserve else ""))
            note = self._depth_note(chart, player) if chart else ""
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (1, 3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column == 0:
                    item.setToolTip(f"{record.position_long_name} (code {record.values['position']})")
                elif column == 5 and note:
                    item.setToolTip(note)
                self.player_table.setItem(row, column, item)
        self.player_table.resizeColumnsToContents()
        self.player_table.blockSignals(False)
        self.count_label.setText(f"{len(players)} shown · {len(self._dirty)} edited")
        if players:
            row = self.player_table.currentRow()
            self.player_table.setCurrentCell(min(row if row >= 0 else 0, len(players) - 1), 0)
            self._select_row(self.player_table.currentRow())
        else:
            self._show_player(None)
        self._refresh_actions()

    def selected_player(self) -> rr.Player | None:
        row = self.player_table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def select_player(self, player: rr.Player) -> bool:
        for row, candidate in enumerate(self._rows):
            if candidate is player:
                self.player_table.setCurrentCell(row, 0)
                return True
        return False

    def _select_row(self, row: int) -> None:
        self._show_player(self._rows[row] if 0 <= row < len(self._rows) else None)

    # ------------------------------------------------------------------ editor pane
    def _show_player(self, player: rr.Player | None) -> None:
        if player is None:
            self.header_name.setText("—")
            self.header_stats.setText("")
            self.header_contract.setText("")
            self.header_profile.setText("")
            self.first_field.setText("")
            self.last_field.setText("")
            for card in self.cards.values():
                card.setEnabled(False)
            self._refresh_actions()
            return
        record = player.record
        for card in self.cards.values():
            card.setEnabled(True)
        self.header_name.setText(player.display)
        birth = record.birth_date
        age = ""
        if birth is not None:
            age = f" · age {2004 - birth.year - ((9, 1) < (birth.month, birth.day))}"
        # the animation family the engine picks for this record (Scramble parity, then magnitude)
        family = ("signature release" if record.throw_style
                  else ("standard release, mobile family" if record.mobile_quarterback else "standard release"))
        self.header_stats.setText(
            f"{record.position_name} · #{record.values['jersey']} · {record.height_text} · "
            f"{record.weight} lb{age} · {record.values['years_pro']} yrs pro · {player.college or '—'} · "
            f"{rr.HANDS[record.values['hand']]} hand · "
            f"{rr.POWER_RUN_STYLES[record.power_run_style_bucket]} · {family}")
        code = record.values["position"]
        key = " · ".join(rr.RATING_LABELS.get(name, name) for name in rr.key_ratings(code))
        profile = rr.rating_profile(code)
        self.header_profile.setText(
            f"{record.position_long_name} (code {code})"
            + (f" · rated on the {profile} card set: {key}" if key else "")
            + (" · RETIRED on this roster's scheme"
               if rr.is_retired_position(code, self._scheme) else ""))
        self.header_contract.setText(
            f"Contract: {record.values['contract_length']} yrs ${record.contract_millions:.2f}m, "
            f"{record.values['contract_remaining']} remaining, "
            f"{rr.CONTRACT_TYPES[record.values['contract_type']]} with a "
            f"{rr.CONTRACT_BONUSES[record.values['contract_bonus']]} bonus "
            f"(penalty ${record.contract_penalty_millions:.2f}m, derived)")
        self.first_field.setText(player.first)
        self.last_field.setText(player.last)
        self.college_combo.blockSignals(True)
        self.college_combo.setCurrentIndex(player.college_index if player.college_index is not None else -1)
        self.college_combo.blockSignals(False)
        baseline = self._baseline_record(player)
        for name, card in self.cards.items():
            card.set_value(record.get(name))
            card.set_dirty(baseline is not None and baseline.get(name) != record.get(name))
        self._refresh_name_pool_label(player)
        self._refresh_actions()

    def _refresh_name_pool_label(self, player: rr.Player) -> None:
        assert self.document is not None
        pool = self.document.names
        shared = []
        for which, key in (("first", "first_name_pointer"), ("last", "last_name_pointer")):
            if not player.record.values[key]:
                continue
            offset = self.document._pointer_target(player.offset, key)
            users = self.document.name_refs.get(offset, 1)
            if users > 1:
                shared.append(f"{which} name shared with {users - 1} other player(s)")
        self.name_pool_label.setText(
            f"Name pool: {pool.free_bytes} of {pool.capacity_bytes} bytes free · "
            f"{len(pool.blocks)} strings. A longer name needs a free block or an existing string."
            + (" · " + "; ".join(shared) if shared else ""))

    def _baseline_record(self, player: rr.Player) -> rr.PlayerRecord | None:
        if self.document is None:
            return None
        raw = self.document.original[player.offset: player.offset + rr.PLAYER_SIZE]
        return rr.PlayerRecord.decode(raw, self.document.scheme)

    # ------------------------------------------------------------------ edits
    def _card_changed(self, name: str, value: int) -> None:
        player = self.selected_player()
        if player is None or self.document is None:
            return
        if name == "scramble":
            # magnitude and parity are independent in the engine; the slider must not disturb the bit
            value = (int(value) & ~1) | (player.record.values["scramble"] & 1)
        if name == "position":
            # never write a code the loaded scheme retired: on a reclassified roster enum 10 is a
            # filter row no team fills, so a player parked there disappears from every position list
            try:
                rr.check_position_code(int(value), self._scheme)
            except rr.RosterRecordError as exc:
                self._set_status(str(exc))
                card = self.cards.get("position")
                if card is not None:
                    card.set_value(player.record.values["position"])
                return
        before = player.record.get(name)
        if before == value:
            return
        self.set_field(player, name, value)

    def set_field(self, player: rr.Player, name: str, value: int) -> None:
        """Set one field with undo, dirty marking and a refreshed header."""

        before = player.record.get(name)
        if before == int(value):
            return

        def do(new: int = int(value)) -> None:
            player.record.set(name, new)
            self._after_edit(player, name)

        def undo(old: int = before) -> None:
            player.record.set(name, old)
            self._after_edit(player, name)

        do()
        self.undo_stack.push(UndoEntry(f"{player.display}: {name}", undo, do))

    def _after_edit(self, player: rr.Player, name: str = "") -> None:
        baseline = self._baseline_record(player)
        changed = baseline is not None and any(
            baseline.values[key] != player.record.values[key]
            for key in player.record.values if key not in rr.POINTER_FIELDS)
        key = (player.pool, player.index)
        if changed or self._name_changed(player):
            self._dirty.add(key)
        else:
            self._dirty.discard(key)
        if self.selected_player() is player:
            self._show_player(player)
        self._refresh_grid_row(player)
        self._refresh_actions()

    def _name_changed(self, player: rr.Player) -> bool:
        """True when this player's name or college text differs from the roster we loaded."""

        assert self.document is not None
        for which, pointer in (("first", "first_name_pointer"), ("last", "last_name_pointer")):
            field_offset = player.offset + rr.FIELD_BY_NAME[pointer].offset
            raw = int.from_bytes(self.document.original[field_offset: field_offset + 4], "little")
            if not raw:
                continue
            target = field_offset + (raw - (1 << 32) if raw >= (1 << 31) else raw) - 1
            if rr.read_utf16z(self.document.original, target)[0] != getattr(player, which):
                return True
        college_offset = player.offset + rr.FIELD_BY_NAME["college_pointer"].offset
        raw = int.from_bytes(self.document.original[college_offset: college_offset + 4], "little")
        if raw:
            target = college_offset + (raw - (1 << 32) if raw >= (1 << 31) else raw) - 1
            index = self.document.college_record_index.get(target)
            if index is not None and self.document.colleges[index] != player.college:
                return True
        return False

    def _refresh_grid_row(self, player: rr.Player) -> None:
        chart = self._depth_chart()
        for row, candidate in enumerate(self._rows):
            if candidate is player:
                record = player.record
                marker = "● " if (player.pool, player.index) in self._dirty else ""
                note = self._depth_note(chart, player) if chart else ""
                for column, text in enumerate((record.position_name, str(record.values["jersey"]),
                                               f"{marker}{player.display}",
                                               str(record.values["years_pro"]), str(record.overall()),
                                               f"{record.values['depth_rank']}/{record.values['depth_side']}")):
                    item = self.player_table.item(row, column)
                    if item is not None:
                        item.setText(text)
                        if column == 0:
                            item.setToolTip(f"{record.position_long_name} "
                                            f"(code {record.values['position']})")
                        elif column == 5:
                            item.setToolTip(note)
                break
        self.count_label.setText(f"{len(self._rows)} shown · {len(self._dirty)} edited")

    def _name_committed(self, which: str) -> None:
        player = self.selected_player()
        if player is None or self.document is None:
            return
        field = self.first_field if which == "first" else self.last_field
        wanted = field.text().strip()
        current = getattr(player, which)
        if wanted == current:
            return
        try:
            self.document.set_name(player, which, wanted)
        except rr.RosterRecordError as exc:
            field.setText(current)
            field.setToolTip(str(exc))
            self._set_status(str(exc))
            if self.isVisible():        # a modal would block an offscreen or background page
                QMessageBox.warning(self, "The name pool is full", str(exc))
            return

        def undo(old: str = current) -> None:
            assert self.document is not None
            self.document.set_name(player, which, old)
            self._after_edit(player)

        def redo(new: str = wanted) -> None:
            assert self.document is not None
            self.document.set_name(player, which, new)
            self._after_edit(player)

        self.undo_stack.push(UndoEntry(f"{player.display}: {which} name", undo, redo))
        self._after_edit(player)

    def _college_chosen(self, index: int) -> None:
        player = self.selected_player()
        if player is None or self.document is None or index < 0:
            return
        before = player.college_index
        if before == index:
            return

        def do(new: int = index) -> None:
            assert self.document is not None
            self.document.set_college(player, new)
            self._after_edit(player)

        def undo(old: int | None = before) -> None:
            assert self.document is not None
            if old is not None:
                self.document.set_college(player, old)
            self._after_edit(player)

        do()
        self.undo_stack.push(UndoEntry(f"{player.display}: college", undo, do))

    def move_selected(self, delta: int) -> bool:
        """Move the selected player up or down his team's list -- the depth chart itself."""

        player = self.selected_player()
        kind, team_index = self._group
        if player is None or self.document is None or kind != "team":
            return False
        team = self.document.teams[team_index]
        try:
            slot = team.slots.index(player.offset)
        except ValueError:
            return False
        if not self.document.move_in_depth(team_index, slot, delta):
            return False

        def undo(a: int = slot, b: int = slot + delta) -> None:
            assert self.document is not None
            self.document.move_in_depth(team_index, b, a - b)
            self.refresh_grid()

        def redo(a: int = slot, b: int = delta) -> None:
            assert self.document is not None
            self.document.move_in_depth(team_index, a, b)
            self.refresh_grid()

        self.undo_stack.push(UndoEntry(f"{player.display}: depth order", undo, redo))
        self.refresh_grid()
        self.select_player(player)
        return True

    def _move_card_focus(self, name: str, step: int) -> str:
        """Move the keyboard focus to the next card on this tab; returns the card it landed on."""

        order = self._page_cards.get(self.tabs.currentIndex()) or self._card_order
        if name not in order:
            return ""
        target = order[(order.index(name) + step) % len(order)]
        self.cards[target].focus_editor()
        return target

    # ------------------------------------------------------------------ undo
    def undo(self) -> str:
        label = self.undo_stack.undo()
        if label:
            self._set_status(f"Undid {label}")
            self.refresh_grid()
            self._show_player(self.selected_player())
        self._refresh_actions()
        return label

    def redo(self) -> str:
        label = self.undo_stack.redo()
        if label:
            self._set_status(f"Redid {label}")
            self.refresh_grid()
            self._show_player(self.selected_player())
        self._refresh_actions()
        return label

    # ------------------------------------------------------------------ passes
    def open_global_editor(self) -> GlobalEditDialog | None:
        if self.document is None:
            self._set_status("Load a roster first.")
            return None
        dialog = GlobalEditDialog(self, self)
        dialog.exec_()
        return dialog

    def global_edit_preview(self, *, attribute: str, mode: str, value: float,
                            positions: Sequence[str] = (), rookies_only: bool = False,
                            minimum: int = 0, maximum: int = rr.RATING_MAX,
                            where: tuple[str, str, int] | None = None,
                            current_team_only: bool = False) -> list[dict[str, Any]]:
        if self.document is None:
            return []
        scope = self.visible_players() if current_team_only else None
        return rr.global_edit_preview(self.document, attribute=attribute, mode=mode, value=value,
                                      positions=positions, rookies_only=rookies_only,
                                      minimum=minimum, maximum=maximum, where=where, players=scope)

    def apply_global_edit(self, preview: Sequence[dict[str, Any]], attribute: str) -> int:
        if self.document is None or not preview:
            return 0
        rows = [dict(row) for row in preview]
        by_key = {(p.pool, p.index): p for p in self.document.players}

        def do() -> None:
            assert self.document is not None
            rr.global_edit_apply(self.document, rows, attribute)
            for row in rows:
                player = by_key.get((row["pool"], row["index"]))
                if player is not None:
                    self._dirty.add((player.pool, player.index))
            self.refresh_grid()
            self._show_player(self.selected_player())

        def undo() -> None:
            for row in rows:
                player = by_key.get((row["pool"], row["index"]))
                if player is not None:
                    player.record.set(attribute, int(row["before"]))
                    self._after_edit(player)
            self.refresh_grid()

        do()
        self.undo_stack.push(UndoEntry(f"global edit: {attribute} on {len(rows)} players", undo, do))
        self._set_status(f"Global edit applied to {len(rows)} players.")
        return len(rows)

    def copy_player(self) -> bool:
        player = self.selected_player()
        if player is None:
            return False
        self._clipboard = player.record.copy()
        self._set_status(f"Copied {player.display}.")
        self._refresh_actions()
        return True

    def paste_player(self, mode: str = "all") -> int:
        player = self.selected_player()
        if player is None or self._clipboard is None:
            return 0
        before = player.record.copy()
        count = rr.copy_player(self._clipboard, player.record, mode=mode)
        if not count:
            return 0

        def undo(snapshot: rr.PlayerRecord = before) -> None:
            player.record.values.update(snapshot.values)
            self._after_edit(player)

        def redo(source: rr.PlayerRecord = self._clipboard, kind: str = mode) -> None:
            rr.copy_player(source, player.record, mode=kind)
            self._after_edit(player)

        self.undo_stack.push(UndoEntry(f"paste ({mode}) onto {player.display}", undo, redo))
        self._after_edit(player)
        self._set_status(f"Pasted {count} fields onto {player.display}.")
        return count

    def advance_years_pro(self, visible_only: bool = False) -> int:
        if self.document is None:
            return 0
        scope = self.visible_players() if visible_only else list(self.document.players)
        before = {(p.pool, p.index): p.record.values["years_pro"] for p in scope}

        def do() -> None:
            assert self.document is not None
            rr.advance_years_pro(self.document, scope)
            for player in scope:
                self._dirty.add((player.pool, player.index))
            self.refresh_grid()
            self._show_player(self.selected_player())

        def undo() -> None:
            for player in scope:
                player.record.values["years_pro"] = before[(player.pool, player.index)]
                self._dirty.discard((player.pool, player.index))
            self.refresh_grid()
            self._show_player(self.selected_player())

        do()
        self.undo_stack.push(UndoEntry(f"advance years pro ({len(scope)} players)", undo, do))
        self._set_status(f"Advanced years pro for {len(scope)} players.")
        return len(scope)

    def restore_measurements(self) -> int:
        """Finn's Restore Weight/Height: put back what the roster shipped with."""

        if self.document is None:
            return 0
        if self._baseline is None:
            self._baseline = rr.RosterDocument(self.document.original, base=self.document.base)
        scope = self.visible_players()
        snapshots = {(p.pool, p.index): dict(p.record.values) for p in scope}

        def do() -> None:
            assert self.document is not None and self._baseline is not None
            count = rr.restore_measurements(self.document, self._baseline, scope)
            self.refresh_grid()
            self._show_player(self.selected_player())
            self._set_status(f"Restored height, weight and date of birth on {count} players.")

        def undo() -> None:
            for player in scope:
                player.record.values.update(snapshots[(player.pool, player.index)])
                self._after_edit(player)
            self.refresh_grid()

        do()
        self.undo_stack.push(UndoEntry("restore height / weight / DOB", undo, do))
        for player in scope:
            self._after_edit(player)
        return len(scope)

    # ------------------------------------------------------------------ reports
    def run_validation(self) -> list[dict[str, Any]]:
        if self.document is None:
            return []
        findings = rr.validate(self.document, self.visible_players())
        lines = [f"[{item['level'].upper()}] {item['player'] or 'roster'} · {item['check']}: {item['detail']}"
                 for item in findings]
        self.report.setPlainText("\n".join(lines) or "Nothing to report.")
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        return findings

    def refresh_diff(self) -> list[dict[str, Any]]:
        if self.document is None:
            return []
        entries = self.document.diff()
        count = len(entries)
        lines: list[str] = [f"{count} player{'' if count == 1 else 's'} "
                            f"{'differs' if count == 1 else 'differ'} from the roster you loaded.", ""]
        for entry in entries:
            lines.append(f"{entry['name']} ({entry['pool']} #{entry['index']})")
            for key, (was, now) in sorted(entry["texts"].items()):
                lines.append(f"    {key}: {was!r} -> {now!r}")
            for key, (was, now) in sorted(entry["changes"].items()):
                caption = rr.RATING_LABELS.get(key) or rr.FIELD_BY_NAME[key].label
                if key == "position":
                    # a bare "10 -> 11" says nothing; name both ends in the loaded scheme
                    lines.append(f"    {caption}: {rr.position_name(was, self._scheme)} -> "
                                 f"{rr.position_name(now, self._scheme)}")
                else:
                    lines.append(f"    {caption}: {was} -> {now}")
        self.report.setPlainText("\n".join(lines))
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        return entries

    # ------------------------------------------------------------------ CSV
    def export_csv_text(self, everything: bool = False) -> str:
        if self.document is None:
            return ""
        players = None if everything else self.visible_players()
        return rr.export_csv(self.document, players)

    def import_csv_text(self, text: str) -> dict[str, Any]:
        if self.document is None:
            return {"rows": 0, "changed": 0, "fields": 0, "log": ["no roster loaded"]}
        snapshot = {(p.pool, p.index): dict(p.record.values) for p in self.document.players}
        receipt = rr.import_csv(self.document, text)
        for player in self.document.players:
            if dict(player.record.values) != snapshot[(player.pool, player.index)]:
                self._dirty.add((player.pool, player.index))

        def undo() -> None:
            assert self.document is not None
            for player in self.document.players:
                player.record.values.update(snapshot[(player.pool, player.index)])
            self.refresh_grid()
            self._show_player(self.selected_player())

        def redo(payload: str = text) -> None:
            assert self.document is not None
            rr.import_csv(self.document, payload)
            self.refresh_grid()
            self._show_player(self.selected_player())

        self.undo_stack.push(UndoEntry(f"CSV import ({receipt['changed']} players)", undo, redo))
        self.refresh_grid()
        self._show_player(self.selected_player())
        self._set_status(f"CSV: {receipt['rows']} rows matched, {receipt['changed']} players, {receipt['fields']} fields"
                         + (f", {len(receipt['log'])} notes" if receipt["log"] else ""))
        return receipt

    def _export_csv(self, everything: bool) -> None:
        if self.document is None:
            return
        chosen, _f = QFileDialog.getSaveFileName(self, "Export players as CSV", "roster.csv", CSV_FILTER)
        if not chosen:
            return
        Path(chosen).write_text(self.export_csv_text(everything), encoding="utf-8", newline="")
        self._set_status(f"Wrote {chosen}")

    def _import_csv(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Import a player CSV", "", CSV_FILTER)
        if not chosen:
            return
        receipt = self.import_csv_text(Path(chosen).read_text(encoding="utf-8"))
        if receipt["log"]:
            QMessageBox.information(self, "CSV import", "\n".join(receipt["log"][:20]))

    # ------------------------------------------------------------------ writing
    def edits_document(self) -> dict[str, Any]:
        if self.document is None:
            return {}
        return rr.edits_document(self.document, name=self._source_path.name if self._source_path else "")

    def save_edits_to(self, path: Path | str) -> dict[str, Any]:
        document = self.edits_document()
        Path(path).write_text(json.dumps(document, indent=1), encoding="utf-8", newline="\n")
        self._edits_path = Path(path)
        self.roster_edits_changed.emit(str(path))
        self._set_status(f"Wrote {len(document.get('edits', []))} player edits to {path}")
        return document

    def _save_edits(self) -> None:
        if self.document is None:
            return
        chosen, _f = QFileDialog.getSaveFileName(self, "Save roster edits", "roster_edits.json", EDITS_FILTER)
        if chosen:
            self.save_edits_to(chosen)

    def write_copy_to(self, target: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
        """Disc: copy the image and apply.  Save: write a re-signed container.  Never the source."""

        if self.document is None:
            raise rr.RosterRecordError("no roster is loaded")
        destination = Path(target)
        if self._source_kind == "save":
            return rr.save_document(self.document, destination, overwrite=overwrite)
        if self._source_path is None:
            raise rr.RosterRecordError("this roster did not come from a disc or a save")
        if destination.resolve() == self._source_path.resolve():
            raise rr.RosterRecordError("the target must not be the source disc")
        if self._source_path.is_dir():
            raise rr.RosterRecordError(
                "this roster was read from a loose pack folder, which has no image to copy. "
                "Use Save roster edits… and apply them from Build & Share, or load a disc image.")
        if destination.exists() and not overwrite:
            raise rr.RosterRecordError(f"{destination} exists")
        shutil.copyfile(self._source_path, destination)
        return rr.apply(destination, self.edits_document())

    def _write_copy(self) -> None:
        if self.document is None:
            return
        if self._source_kind == "save":
            chosen = QFileDialog.getExistingDirectory(self, "Write the re-signed save copy into")
        else:
            chosen, _f = QFileDialog.getSaveFileName(self, "Write a patched copy of the disc",
                                                     "roster-edited.xiso.iso", DISC_FILTER)
        if not chosen:
            return
        try:
            receipt = self.write_copy_to(chosen)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not write the copy", f"{type(exc).__name__}: {exc}")
            return
        self._set_status(f"Wrote {receipt.get('target', chosen)}")

    # ------------------------------------------------------------------ chrome
    def _refresh_pool_label(self) -> None:
        if self.document is None:
            self.pool_label.setText("")
            return
        summary = self.document.summary()["names"]
        self.pool_label.setText(
            f"Name pool {summary['capacity_bytes']} B · {summary['strings']} strings · "
            f"{summary['unique']} distinct · {summary['free_bytes']} B free")

    def _refresh_actions(self) -> None:
        loaded = self.document is not None
        selected = self.selected_player() is not None
        self.undo_button.setEnabled(self.undo_stack.can_undo())
        self.redo_button.setEnabled(self.undo_stack.can_redo())
        for widget in (self.global_button, self.passes_button, self.csv_button,
                       self.save_edits_button, self.write_button, self.validate_button,
                       self.diff_button):
            widget.setEnabled(loaded)
        self.copy_button.setEnabled(selected)
        self.paste_button.setEnabled(selected and self._clipboard is not None)
        self.up_button.setEnabled(selected and self._group[0] == "team")
        self.down_button.setEnabled(selected and self._group[0] == "team")
        if self.document is not None:
            self._refresh_pool_label()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)


__all__ = ["AttributeCard", "GlobalEditDialog", "RosterEditorPanel", "UndoEntry", "UndoStack", "ValueBar"]
